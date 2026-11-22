# Đối soát số dòng, tổng kiểm tra nghiệp vụ và đối tượng INVALID sau di chuyển

Sau khi di chuyển Oracle Database bằng Data Pump, transportable tablespaces, RMAN hoặc phương pháp khác, công việc chưa kết thúc ở việc lệnh import trả về thành công. DBA và nhóm ứng dụng cần chứng minh rằng dữ liệu đích đầy đủ, đúng nội dung nghiệp vụ, metadata hợp lệ và ứng dụng có thể hoạt động bình thường.

Đối soát sau migration nên thực hiện theo nhiều lớp:

1. **Tính nhất quán của snapshot:** xác định dữ liệu source và target đang được so sánh thuộc cùng một mốc nghiệp vụ.
2. **Số dòng:** so sánh số lượng bản ghi theo bảng, partition và các nhóm nghiệp vụ.
3. **Tổng kiểm tra nghiệp vụ:** so sánh tổng tiền, số lượng, min/max, null counts, distinct counts và các control totals.
4. **Row-level reconciliation:** tìm bản ghi thiếu, thừa, trùng hoặc có giá trị khác nhau bằng khóa nghiệp vụ và phép so sánh hai chiều.
5. **Metadata và object status:** xác minh table, index, constraint, trigger, sequence, synonym, grant và các object INVALID.
6. **Kiểm thử ứng dụng:** xác nhận luồng giao dịch, báo cáo, job và hiệu năng sau chuyển đổi.

Không có một con số checksum duy nhất nào chứng minh toàn bộ database đúng. Row count giống nhau vẫn có thể che giấu dữ liệu sai; tổng tiền giống nhau vẫn có thể che giấu hai giao dịch bị hoán đổi; object status VALID cũng không chứng minh logic nghiệp vụ hoạt động đúng. Cần kết hợp các kiểm tra độc lập và lưu kết quả thành migration evidence.

## 1. Mục tiêu và phạm vi đối soát

### 1.1. Vì sao phải đối soát?

Migration có thể hoàn tất về mặt kỹ thuật nhưng vẫn còn các lỗi:

- Một số bảng không được export/import do filter hoặc quyền.
- Dữ liệu mới phát sinh sau thời điểm export chưa được đồng bộ.
- Một số dòng bị loại do lỗi conversion, constraint hoặc datatype.
- Character conversion làm thay đổi ký tự.
- Timestamp có timezone hiển thị hoặc chuyển đổi khác.
- Index/constraint/trigger bị disable hoặc INVALID.
- Stored procedure/view/package không compile do dependency hoặc feature khác biệt.
- Sequence/identity không đủ lớn, dẫn tới lỗi duplicate key sau cutover.
- Grants, synonyms, database links, Scheduler jobs hoặc directory objects bị thiếu.
- Dữ liệu được import đúng nhưng ứng dụng đang kết nối nhầm service/schema.

Đối soát giúp phát hiện các vấn đề này trước khi mở traffic production hoặc trước khi hết thời hạn rollback.

### 1.2. Các lớp kiểm tra

| Lớp | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Snapshot | Source và target có cùng phạm vi dữ liệu không? | SCN, thời điểm freeze, export log |
| Completeness | Có đủ bản ghi không? | Exact row counts, partition counts |
| Business correctness | Tổng và phân bố dữ liệu có đúng không? | Control totals, aggregates |
| Row correctness | Bản ghi nào thiếu/thừa/khác? | Key-based diff, mismatch report |
| Structural integrity | Schema và object có hợp lệ không? | Constraints, indexes, INVALID objects |
| Operational readiness | Ứng dụng chạy đúng không? | Smoke test, job test, application sign-off |

### 1.3. Phạm vi đối soát

Xác định rõ các schema, tablespace, table, partition, LOB, view, materialized view và object ngoài schema nằm trong phạm vi migration. Nếu dùng include/exclude filters, ghi lại danh sách dự kiến và so sánh với danh sách thực tế.

Không chỉ kiểm tra các bảng có dữ liệu lớn. Bảng cấu hình nhỏ, bảng mapping, bảng quyền nghiệp vụ và bảng trạng thái có thể quan trọng hơn đối với tính đúng đắn của ứng dụng.

### 1.4. Định nghĩa tiêu chí chấp nhận

Trước khi chạy migration, thống nhất:

- Bảng nào bắt buộc row count bằng nhau?
- Bảng nào có thể khác do dữ liệu phát sinh sau snapshot?
- Những aggregate nào phải khớp tuyệt đối?
- Những cột nào có quy tắc rounding hoặc timezone conversion?
- Có chấp nhận object INVALID tạm thời không? Nếu có, danh sách và thời hạn sửa là gì?
- Những constraint nào bắt buộc ENABLED và VALIDATED?
- Ai ký xác nhận nghiệp vụ và ai ký xác nhận kỹ thuật?

Không đặt tiêu chí sau khi đã thấy kết quả chênh lệch. Tiêu chí phải được thống nhất trước để tránh hợp thức hóa sai lệch.

## 2. Bảo đảm source và target cùng snapshot

### 2.1. Snapshot consistency

Một phép đối soát chỉ có ý nghĩa khi hai phía đại diện cho cùng một phạm vi thời gian. Nếu source tiếp tục nhận giao dịch trong lúc export/import, row count ở source tại thời điểm so sánh có thể cao hơn target dù migration không làm mất dữ liệu.

Các chiến lược thường dùng:

- Đóng băng ghi dữ liệu trong cửa sổ migration.
- Dùng Data Pump Flashback SCN hoặc Flashback Time để export từ một snapshot nhất quán.
- Dùng cơ chế CDC/replication hoặc delta export để bắt kịp thay đổi sau snapshot.
- Ghi watermark hoặc business cutoff để đối soát dữ liệu theo mốc.

### 2.2. Lấy SCN nguồn

Có thể lấy current SCN:

```sql
SELECT current_scn
FROM v$database;
```

Ghi lại SCN, timestamp, database identity và thời điểm chốt. SCN là mốc nhất quán trong một database; SCN của hai database độc lập không tự động có cùng ý nghĩa hoặc có thể so sánh trực tiếp.

### 2.3. Export với FLASHBACK_SCN

Ví dụ Data Pump Export:

```text
expdp system@SRCDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_snapshot_%U.dmp \
  logfile=app_snapshot_exp.log \
  parallel=4 \
  flashback_scn=123456789
```

Thay SCN bằng giá trị thực lấy từ source. Data Pump đọc dữ liệu tại snapshot SCN được chỉ định trong phạm vi hỗ trợ. Cần bảo đảm UNDO còn đủ để phục vụ consistent read trong suốt export; export kéo dài có thể gặp ORA-01555 nếu undo không đủ.

### 2.4. FLASHBACK_TIME

Có thể dùng FLASHBACK_TIME để chỉ định mốc thời gian; Data Pump chuyển thời gian thành SCN tương ứng. Khi cần tái lập chính xác, ghi lại SCN thực tế hoặc lấy SCN rõ ràng trước khi export.

### 2.5. DDL và dữ liệu thay đổi đồng thời

Flashback consistency cho dữ liệu không có nghĩa mọi thay đổi DDL đều được khóa thành snapshot theo cách DBA mong đợi. Trong cửa sổ migration, nên kiểm soát DDL, grants, triggers và schema changes. Ghi lại mọi thay đổi ngoài kế hoạch.

### 2.6. Đối soát khi source vẫn hoạt động

Nếu không thể freeze source trong toàn bộ migration:

1. Chọn mốc snapshot ban đầu.
2. Export dữ liệu tại snapshot đó.
3. Ghi nhận thay đổi phát sinh sau SCN bằng CDC, redo-based capture hoặc business watermark.
4. Áp dụng delta vào target.
5. Chốt write freeze hoặc cutover barrier.
6. Đối soát lại phần delta và control totals tại cutover.

Không so sánh row count target snapshot với source live rồi kết luận migration thiếu dữ liệu.

## 3. Kiểm kê bảng và metadata trước/sau

### 3.1. Danh sách bảng trong schema

Trên source và target, lấy danh sách table:

```sql
SELECT owner,
       table_name,
       partitioned,
       temporary,
       nested,
       iot_type
FROM dba_tables
WHERE owner = 'APP'
ORDER BY table_name;
```

So sánh hai danh sách để phát hiện bảng thiếu, thừa hoặc khác loại. Lưu ý DBA_TABLES không liệt kê mọi loại object; cần kiểm tra thêm views, materialized views, sequences, synonyms, triggers, packages và các metadata liên quan.

### 3.2. NUM_ROWS không phải exact row count

NUM_ROWS trong DBA_TABLES/ALL_TABLES/USER_TABLES đến từ optimizer statistics. Đây là ước lượng/giá trị được thu thập lần gần nhất, có thể stale hoặc NULL. Nó không tự động cập nhật theo từng DML và không phải phép đếm chính xác.

Ví dụ kiểm tra nhanh:

```sql
SELECT table_name, num_rows, last_analyzed, stale_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND object_type = 'TABLE'
ORDER BY table_name;
```

Dùng NUM_ROWS để rà soát sơ bộ, không dùng làm bằng chứng cuối cùng nếu tiêu chí yêu cầu số dòng chính xác.

### 3.3. Exact COUNT(*)

Đếm chính xác một bảng:

```sql
SELECT COUNT(*) AS row_count
FROM app.orders;
```

COUNT(*) đọc dữ liệu cần thiết để đếm và có thể tốn I/O/CPU trên bảng lớn. Chạy ở cả source và target tại snapshot nhất quán. Không dùng COUNT(column) thay thế vì COUNT(column) bỏ qua NULL.

### 3.4. Đếm theo nhóm nghiệp vụ

Một bảng có thể có tổng row count giống nhau nhưng phân bố sai. Đếm theo status hoặc business date:

```sql
SELECT order_status,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY order_status
ORDER BY order_status;
```

Đếm theo ngày:

```sql
SELECT TRUNC(created_at) AS business_day,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY TRUNC(created_at)
ORDER BY business_day;
```

Nếu created_at là TIMESTAMP WITH TIME ZONE, hãy xác định timezone nghiệp vụ trước khi TRUNC hoặc nhóm ngày. Không so sánh ngày theo session timezone khác nhau.

### 3.5. Đếm theo partition

Với bảng partitioned, kiểm tra số dòng theo partition:

```sql
SELECT partition_name,
       num_rows,
       last_analyzed
FROM dba_tab_partitions
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY partition_position;
```

Đây là partition statistics, không phải exact count. Nếu cần exact count, thực hiện COUNT(*) có predicate tương ứng với partition key hoặc tạo script đếm từng partition. Partition pruning giúp giảm phạm vi đọc nếu predicate phù hợp.

### 3.6. Tạo danh sách câu lệnh đếm

Có thể sinh câu lệnh để chạy lần lượt:

```sql
SELECT 'SELECT ''' || table_name ||
       ''' AS table_name, COUNT(*) AS row_count FROM APP."' ||
       REPLACE(table_name, '"', '""') || '";' AS count_sql
FROM dba_tables
WHERE owner = 'APP'
  AND temporary = 'N'
  AND nested = 'NO'
ORDER BY table_name;
```

Đây là script sinh SQL để DBA review và thực thi. Với tên object có ký tự đặc biệt, quoted identifier, table nằm trong cluster hoặc object đặc biệt, cần xử lý theo metadata thực tế. Không chạy dynamic SQL từ danh sách chưa được xác minh.

### 3.7. Temporary và external tables

Global temporary table có dữ liệu theo session/transaction và thường không được đối soát như bảng persistent. External table đọc dữ liệu từ file ngoài database; import metadata không đồng nghĩa file external đã được chuyển. Xác định riêng cách kiểm tra và chuyển dữ liệu của các object này.

### 3.8. Nested table và IOT

Nested table storage và index-organized table có cấu trúc khác heap table thông thường. Tránh đếm nhầm storage table nội bộ như một bảng nghiệp vụ độc lập. Dựa vào metadata và thiết kế schema để xác định đơn vị đối soát.

## 4. Row count: cách đọc và các trường hợp đặc biệt

### 4.1. COUNT(*) và COUNT(column)

- COUNT(*) đếm mọi row.
- COUNT(column) chỉ đếm row có giá trị column khác NULL.
- COUNT(DISTINCT column) đếm giá trị khác nhau, bỏ qua NULL.

Ba số này trả lời các câu hỏi khác nhau. Khi so sánh dữ liệu, nên ghi cả row count và null count của các cột quan trọng.

### 4.2. Bảng rỗng

COUNT(*) = 0 có thể là kết quả đúng nếu bảng thực sự không có dữ liệu tại snapshot. Kiểm tra thêm bảng có được import, có filter loại trừ hoặc có trigger/job làm thay đổi dữ liệu sau import hay không.

### 4.3. Bảng lớn

Đối với bảng hàng tỷ dòng:

- Đếm theo partition/key range để có tiến độ và khoanh vùng.
- Dùng parallel query có kiểm soát nếu tài nguyên cho phép.
- Chạy vào giờ phù hợp.
- Tránh tạo contention với workload production.
- Lưu kết quả từng partition và tổng hợp sau.

Ví dụ:

```sql
SELECT /*+ PARALLEL(o, 8) */
       COUNT(*) AS row_count
FROM app.orders o;
```

Degree 8 chỉ là ví dụ; phải cân nhắc CPU, I/O, Resource Manager và workload đồng thời.

### 4.4. Snapshot không giống thời điểm chạy query

COUNT(*) ở source lúc 10:00 và target lúc 10:30 không thể so sánh nếu source tiếp tục nhận DML. Cần freeze, flashback query ở SCN phù hợp hoặc đối soát theo watermark/CDC.

### 4.5. Row count và duplicate

Hai bảng có cùng row count nhưng một bảng có duplicate key và thiếu key khác vẫn có thể cho cùng số dòng. Do đó, kiểm tra:

- Unique/primary key duplicates.
- Missing keys.
- Unexpected extra keys.
- Null key nếu key nghiệp vụ cho phép NULL.
- Cardinality theo business dimensions.

### 4.6. Kiểm tra duplicate key

```sql
SELECT order_id,
       COUNT(*) AS occurrences
FROM app.orders
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;
```

Nếu primary key đã được ENABLED VALIDATED, duplicate không thể tồn tại theo constraint đó. Tuy nhiên, constraint có thể đang DISABLED hoặc NOVALIDATE, vì vậy vẫn phải kiểm tra metadata.

## 5. Tổng kiểm tra nghiệp vụ (business control totals)

### 5.1. Vì sao cần aggregate?

Row count chỉ đo số lượng. Business aggregate kiểm tra nội dung theo ý nghĩa nghiệp vụ. Ví dụ bảng ORDER có thể có đúng 1 triệu dòng nhưng một số amount bị NULL, đổi dấu hoặc gán sai status.

Các control totals phổ biến:

- Tổng số giao dịch.
- Tổng giá trị tiền.
- Tổng số lượng hàng.
- Số đơn theo trạng thái.
- Tổng thuế/chiết khấu.
- Số khách hàng hoặc tài khoản distinct.
- Giá trị min/max và khoảng ngày.
- Null count ở các cột bắt buộc.
- Số bản ghi theo chi nhánh, tenant, currency hoặc ngày nghiệp vụ.

### 5.2. Aggregate cơ bản

```sql
SELECT COUNT(*)                    AS row_count,
       COUNT(order_id)             AS nonnull_order_id,
       COUNT(DISTINCT customer_id) AS distinct_customers,
       SUM(total_amount)           AS sum_amount,
       MIN(total_amount)           AS min_amount,
       MAX(total_amount)           AS max_amount,
       SUM(tax_amount)             AS sum_tax
FROM app.orders;
```

So sánh từng metric giữa source và target. SUM bỏ qua NULL; nếu tất cả giá trị đều NULL, kết quả SUM là NULL. Không chuyển NULL thành zero trong một phía mà không có business rule rõ ràng.

### 5.3. Null counts

```sql
SELECT COUNT(*) AS total_rows,
       SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END)
           AS null_customer_id,
       SUM(CASE WHEN total_amount IS NULL THEN 1 ELSE 0 END)
           AS null_total_amount,
       SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END)
           AS null_created_at
FROM app.orders;
```

Null count có thể phát hiện conversion hoặc defaulting không mong muốn dù tổng row count và tổng amount gần như không đổi.

### 5.4. Tổng theo ngày và status

```sql
SELECT TRUNC(created_at) AS business_day,
       order_status,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total,
       SUM(tax_amount) AS tax_total
FROM app.orders
GROUP BY TRUNC(created_at), order_status
ORDER BY business_day, order_status;
```

Nếu ngày nghiệp vụ theo một timezone cụ thể, chuyển timestamp về timezone đó trước khi nhóm. Source và target phải dùng cùng quy tắc timezone.

### 5.5. Tổng theo currency

Không cộng các số tiền thuộc currency khác nhau thành một total duy nhất nếu chưa quy đổi theo tỷ giá và thời điểm thống nhất:

```sql
SELECT currency_code,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total
FROM app.orders
GROUP BY currency_code
ORDER BY currency_code;
```

### 5.6. Tổng theo tenant hoặc business unit

```sql
SELECT business_unit_id,
       COUNT(*) AS row_count,
       SUM(net_amount) AS net_total
FROM app.invoice
GROUP BY business_unit_id
ORDER BY business_unit_id;
```

Phân nhóm giúp khoanh vùng sai lệch theo một đơn vị nghiệp vụ thay vì chỉ biết tổng toàn schema khác nhau.

### 5.7. Rounding và numeric precision

Khi nghiệp vụ sử dụng rounding, phải xác định tổng được tính bằng:

- Tổng các giá trị đã làm tròn từng dòng.
- Làm tròn sau khi cộng tổng.
- Làm tròn theo currency scale.

Ba cách có thể tạo kết quả khác nhau. So sánh bằng quy tắc nghiệp vụ đã thống nhất; không tự dùng tolerance để che sai lệch.

### 5.8. Aggregate không chứng minh từng dòng đúng

Ví dụ source có hai amount 100 và 200, target có 150 và 150. Row count bằng nhau, SUM đều bằng 300, nhưng từng giao dịch khác nhau. Vì vậy aggregate là kiểm tra tổng quan; cần row-level diff cho các bảng trọng yếu.

## 6. Checksum và fingerprint dữ liệu

### 6.1. Checksum là gì?

Checksum/fingerprint là giá trị tính từ nội dung dữ liệu để hỗ trợ phát hiện khác biệt. Có thể tính theo từng row, từng partition hoặc một nhóm dữ liệu. Một checksum tốt cần biểu diễn nhất quán:

- Thứ tự cột.
- Kiểu dữ liệu.
- NULL.
- Character encoding.
- Date/time format và timezone.
- Precision/scale của NUMBER.
- LOB content.
- Quy tắc chuẩn hóa dữ liệu.

### 6.2. Vì sao checksum đơn giản có thể gây hiểu nhầm?

Không dùng một phép SUM đơn giản của cột số hoặc ORA_HASH làm bằng chứng tuyệt đối. Các phép tổng hợp có thể va chạm:

- Hoán đổi hai giá trị vẫn giữ nguyên SUM.
- Hai tập dữ liệu khác nhau có thể tạo cùng tổng hash.
- ORA_HASH có không gian giá trị hữu hạn và không phải cryptographic hash.
- Nối chuỗi không có delimiter/length prefix có thể tạo cùng chuỗi cho các tuple khác nhau.
- Format ngày/số phụ thuộc NLS có thể tạo fingerprint khác giữa hai database dù dữ liệu tương đương.

Checksum chỉ là một lớp kiểm tra và phải kết hợp với key-based comparison và business totals.

### 6.3. Canonical representation

Trước khi hash, chuyển từng giá trị về một representation ổn định:

- NUMBER: format rõ decimal separator, không phụ thuộc NLS_NUMERIC_CHARACTERS.
- DATE/TIMESTAMP: format rõ precision và timezone rule.
- Character: xác định Unicode normalization/encoding nếu ứng dụng có yêu cầu.
- NULL: biểu diễn riêng biệt, không nhập nhằng với chuỗi rỗng hoặc sentinel có thể xuất hiện thật.
- Các field: dùng length-prefix hoặc delimiter được escape an toàn.
- LOB: hash toàn bộ nội dung, không chỉ hash locator hoặc độ dài.

Không trim khoảng trắng, đổi chữ hoa/thường hoặc normalize Unicode nếu business contract không cho phép.

### 6.4. Hash theo từng row

Với các cột scalar, có thể tạo một chuỗi canonical theo primary key và nội dung rồi dùng cryptographic hash. Ví dụ minh họa cho một bảng đơn giản:

```sql
SELECT order_id,
       STANDARD_HASH(
           NVL(TO_CHAR(customer_id), '<NULL>') || '|' ||
           NVL(TO_CHAR(total_amount,
               'FM999999999999990D999999',
               'NLS_NUMERIC_CHARACTERS=''.,'''), '<NULL>') || '|' ||
           NVL(TO_CHAR(created_at,
               'YYYY-MM-DD"T"HH24:MI:SS'), '<NULL>') || '|' ||
           NVL(order_status, '<NULL>'),
           'SHA256'
       ) AS row_hash
FROM app.orders;
```

Đây chỉ là ví dụ minh họa, chưa phải canonical serializer tổng quát. Sentinel <NULL> có thể trùng dữ liệu thật; delimiter có thể xuất hiện trong chuỗi; TO_CHAR format cần phù hợp precision thực tế; TIMESTAMP WITH TIME ZONE cần xử lý timezone rõ ràng. Thiết kế production nên dùng length-prefix/type tags hoặc một hàm canonical serialization đã được kiểm thử.

### 6.5. STANDARD_HASH

STANDARD_HASH cung cấp hash algorithms như SHA1/SHA256/SHA384/SHA512 tùy release. Hàm không thay thế quy trình serialization. Nó có giới hạn datatype đầu vào; LOB không được xử lý trực tiếp như một expression VARCHAR2 thông thường trong mọi ngữ cảnh. Kiểm tra tài liệu release và dùng DBMS_CRYPTO hoặc hàm streaming phù hợp cho LOB.

### 6.6. DBMS_CRYPTO

DBMS_CRYPTO có thể tạo cryptographic hash từ RAW và LOB trong các overload được hỗ trợ. Quyền EXECUTE package và datatype/encoding cần được kiểm tra. Với CLOB, xác định rõ cách mã hóa ký tự thành bytes; với BLOB, hash bytes nguyên gốc.

Ví dụ ý tưởng PL/SQL cho một CLOB đã được canonicalize:

```sql
DECLARE
    l_hash RAW(32);
    l_text CLOB;
BEGIN
    -- l_text phải được tạo từ serialization có quy tắc ổn định.
    l_hash := DBMS_CRYPTO.HASH(
        src => l_text,
        typ => DBMS_CRYPTO.HASH_SH256
    );
    DBMS_OUTPUT.PUT_LINE(RAWTOHEX(l_hash));
END;
/
```

Đoạn code cần điều chỉnh theo overload DBMS_CRYPTO của release và cách tạo LOB. Không dùng một hàm nối chuỗi VARCHAR2 ngắn để hash dữ liệu lớn hoặc LOB bị truncate.

### 6.7. Hash theo partition hoặc chunk

Với bảng rất lớn, tạo fingerprint theo partition hoặc key range:

1. Chia dữ liệu thành các nhóm xác định được.
2. Tính row count và business totals cho mỗi nhóm.
3. Tính hash theo row/key trong nhóm nếu cần.
4. So sánh nhóm trước để khoanh vùng.
5. Chỉ chạy row-level diff sâu ở nhóm có mismatch.

Chunk phải có ranh giới ổn định, không dựa vào ROWNUM không có ORDER BY hoặc physical row order.

### 6.8. Hash không phải chữ ký bảo mật

Hash phục vụ phát hiện khác biệt dữ liệu. Nó không thay thế HMAC/signature để chứng minh nguồn gốc hoặc chống sửa đổi có chủ đích. Nếu cần bằng chứng integrity có tính bảo mật, thiết kế quy trình ký/hash với secret/key management riêng.

## 7. So sánh row-level giữa source và target

### 7.1. So sánh theo primary key

Khi hai database có database link, có thể so sánh target local với source remote. Ví dụ:

```sql
SELECT t.order_id,
       t.total_amount AS target_amount,
       s.total_amount AS source_amount
FROM app.orders t
FULL OUTER JOIN app.orders@SRC_LINK s
  ON s.order_id = t.order_id
WHERE t.order_id IS NULL
   OR s.order_id IS NULL
   OR NVL(t.total_amount, -999999999) <>
      NVL(s.total_amount, -999999999);
```

Ví dụ này chỉ minh họa một numeric column. Sentinel phải nằm ngoài miền giá trị hợp lệ; cách so sánh production nên xử lý NULL rõ ràng, so sánh tất cả cột quan trọng và có xử lý datatype/LOB riêng. Với nhiều cột, dùng DECODE hoặc biểu thức null-safe phù hợp.

### 7.2. So sánh null-safe

DECODE có semantics coi hai NULL là bằng nhau, có thể dùng cho các kiểu scalar được hỗ trợ:

```sql
SELECT t.order_id
FROM app.orders t
JOIN app.orders@SRC_LINK s
  ON s.order_id = t.order_id
WHERE DECODE(t.customer_id, s.customer_id, 0, 1) = 1
   OR DECODE(t.order_status, s.order_status, 0, 1) = 1
   OR DECODE(t.total_amount, s.total_amount, 0, 1) = 1;
```

DECODE có giới hạn datatype và không phải cách so sánh trực tiếp cho mọi LOB/object. Với TIMESTAMP WITH TIME ZONE, xác định có so sánh instant hay region semantics trước khi chọn phép so sánh.

### 7.3. Tìm key thiếu ở target

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders t
    WHERE t.order_id = s.order_id
);
```

### 7.4. Tìm key thừa ở target

```sql
SELECT t.order_id
FROM app.orders t
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders@SRC_LINK s
    WHERE s.order_id = t.order_id
);
```

### 7.5. MINUS hai chiều

Đối với các cột scalar có thể so sánh bằng set operators:

```sql
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders
MINUS
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders@SRC_LINK;

SELECT order_id, customer_id, order_status, total_amount
FROM app.orders@SRC_LINK
MINUS
SELECT order_id, customer_id, order_status, total_amount
FROM app.orders;
```

Chạy cả hai chiều để tìm row chỉ có ở một phía. MINUS loại bỏ duplicate rows và không hỗ trợ mọi datatype, đặc biệt LOB. Nếu multiplicity/duplicate quan trọng, dùng primary key hoặc GROUP BY tất cả cột có thể so sánh kèm COUNT(*).

### 7.6. So sánh theo hash

Có thể tính row hash ở hai phía rồi join theo primary key và tìm hash khác nhau. Cách này giảm lượng cột phải truyền qua database link nhưng vẫn cần canonical serialization thống nhất và bảo đảm hash được tính trên đúng snapshot.

### 7.7. Không dùng ROWID làm business key

ROWID có thể thay đổi sau export/import, table move, reorganization hoặc rebuild. Dùng primary key hoặc business key ổn định để đối soát.

### 7.8. Bảng không có primary key

Nếu bảng không có PK:

- Xác định business key từ nghiệp vụ.
- Kiểm tra duplicate theo key đó.
- Nếu không có key ổn định, so sánh multiset theo các cột có thể so sánh và số lần xuất hiện.
- Cân nhắc thêm staging identifier trước migration nếu được phép.

Không tự tạo khóa giả dựa trên ROW_NUMBER mà không có ORDER BY xác định duy nhất.

## 8. Đối soát duplicate, orphan và quan hệ

### 8.1. Duplicate key

```sql
SELECT customer_id,
       COUNT(*) AS occurrences
FROM app.customer
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Thực hiện cho các primary/unique/business keys trọng yếu ở cả source và target.

### 8.2. Orphan foreign keys

Ví dụ kiểm tra order tham chiếu customer không tồn tại:

```sql
SELECT o.order_id,
       o.customer_id
FROM app.orders o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM app.customer c
      WHERE c.customer_id = o.customer_id
  );
```

Kiểm tra trên target để phát hiện dữ liệu không nhất quán sau import, kể cả khi foreign key đang DISABLED.

### 8.3. Constraint status

```sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
```

ENABLE NOVALIDATE không tương đương ENABLE VALIDATE. Constraint NOVALIDATE có thể áp dụng cho DML mới nhưng chưa xác nhận dữ liệu cũ thỏa constraint. Migration sign-off cần quy định trạng thái nào được chấp nhận.

### 8.4. Constraint bị disable

Constraint disabled có thể làm ứng dụng ghi dữ liệu không hợp lệ. So sánh constraint definitions giữa source và target, không chỉ đếm số constraint.

### 8.5. Foreign key load order

Data Pump có thể import bảng và constraint theo thứ tự phù hợp, nhưng các filter, disable constraints hoặc lỗi object có thể để lại trạng thái chưa đúng. Sau import, kiểm tra lại ENABLED/VALIDATED và orphan rows.

## 9. Index, trigger và các object phụ thuộc

### 9.1. Index status

```sql
SELECT owner,
       index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       visibility
FROM dba_indexes
WHERE owner = 'APP'
ORDER BY table_name, index_name;
```

Index partitioned cần kiểm tra thêm DBA_IND_PARTITIONS và DBA_IND_SUBPARTITIONS vì index tổng thể có thể không thể hiện toàn bộ trạng thái từng partition.

### 9.2. Unusable indexes

Index hoặc index partition ở trạng thái UNUSABLE có thể làm truy vấn chậm hoặc DML lỗi tùy loại index. Xác định nguyên nhân và rebuild theo kế hoạch, đặc biệt với bitmap, function-based, domain và partitioned indexes.

### 9.3. Trigger status

```sql
SELECT owner,
       trigger_name,
       table_name,
       status,
       triggering_event
FROM dba_triggers
WHERE owner = 'APP'
ORDER BY table_name, trigger_name;
```

Trigger disabled có thể làm thiếu audit, sequence assignment, denormalization hoặc business processing. Không tự động enable tất cả trigger nếu migration có chủ đích disable; đối chiếu design và cutover plan.

### 9.4. Views và materialized views

Kiểm tra status của views, materialized views và refresh state. Materialized view có thể cần refresh sau import; fast refresh có thể không khả dụng nếu thiếu materialized view logs hoặc dependency.

### 9.5. Synonyms và database links

Kiểm tra synonym targets, database link definitions và credential dependencies. Object có thể VALID nhưng trỏ tới service/schema không tồn tại hoặc không thể kết nối từ target.

### 9.6. Grants và roles

So sánh system/object privileges, role grants, default roles và grants cho procedure/package. Data Pump có thể được cấu hình để include/exclude grants; kiểm tra thực tế thay vì giả định.

### 9.7. Scheduler jobs

Kiểm tra job metadata, enabled state, credential, destination, job class và next run date. Không enable các job gửi email, thanh toán, đồng bộ hoặc gọi hệ thống ngoài trước khi cutover được phê duyệt.

## 10. Đối tượng INVALID sau migration

### 10.1. INVALID object là gì?

Object INVALID là database object cần compile nhưng hiện không hợp lệ. Các object thường gặp:

- PACKAGE và PACKAGE BODY.
- PROCEDURE và FUNCTION.
- VIEW.
- TRIGGER.
- TYPE và TYPE BODY.
- MATERIALIZED VIEW.
- Một số Java/XML/feature-specific objects.

Object INVALID có thể do dependency thiếu, object được import trước dependency, privilege không đủ, datatype khác, feature/component chưa cài, synonym trỏ sai hoặc source code không tương thích release.

### 10.2. Liệt kê INVALID objects

```sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
ORDER BY object_type, object_name;
```

### 10.3. Đếm INVALID theo loại

```sql
SELECT object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
GROUP BY object_type
ORDER BY object_type;
```

### 10.4. Xem compile errors

```sql
SELECT owner,
       name,
       type,
       sequence,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP'
ORDER BY name, type, sequence;
```

DBA_ERRORS cho biết lỗi compile hiện có. Với object không có error rows nhưng status INVALID, kiểm tra dependency, object type và compile lại để lấy diagnostic.

### 10.5. Dependency

```sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP'
ORDER BY name, referenced_owner, referenced_name;
```

Dependency có thể trỏ tới object ngoài schema, synonym hoặc remote object. Xác định target object có tồn tại và quyền cần thiết.

### 10.6. Component registry

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Nếu component database chưa được cài hoặc ở trạng thái INVALID, nhiều object hệ thống/feature-dependent có thể không compile. Không xử lý bằng cách compile schema ứng dụng lặp đi lặp lại nếu gốc vấn đề là component registry.

## 11. Compile lại object INVALID

### 11.1. Compile một object

Procedure:

```sql
ALTER PROCEDURE app.refresh_summary COMPILE;
```

Package spec/body:

```sql
ALTER PACKAGE app.report_pkg COMPILE;
ALTER PACKAGE app.report_pkg COMPILE BODY;
```

View:

```sql
ALTER VIEW app.v_order_summary COMPILE;
```

Trigger:

```sql
ALTER TRIGGER app.trg_orders_audit COMPILE;
```

Sau compile, đọc lại DBA_OBJECTS và DBA_ERRORS. Compile command thành công ở mức SQL không có nghĩa mọi dependency đã được sửa.

### 11.2. DBMS_UTILITY.COMPILE_SCHEMA

Có thể compile object trong một schema:

```sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP',
        compile_all => FALSE
    );
END;
/
```

Compile schema có thể tạo tải CPU và dictionary activity. Chạy trong cửa sổ phù hợp và kiểm tra object errors sau khi hoàn tất.

### 11.3. UTL_RECOMP

Oracle cung cấp UTL_RECOMP để compile invalid objects theo thứ tự dependency. Ví dụ:

```sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP');
END;
/
```

Hoặc compile song song trong môi trường phù hợp:

```sql
BEGIN
    UTL_RECOMP.RECOMP_PARALLEL(
        degree  => 4,
        schema  => 'APP'
    );
END;
/
```

UTL_RECOMP thường được thực hiện bởi DBA/SYS theo quyền và hướng dẫn Oracle. Degree 4 chỉ là ví dụ; không chạy song song quá cao trên database đang chịu tải.

### 11.4. utlrp.sql

Sau database upgrade hoặc import lớn, Oracle có thể yêu cầu chạy script compile invalid objects:

```sql
@?/rdbms/admin/utlrp.sql
```

Script nằm trong Oracle Home và có hành vi phù hợp với release. Chạy trong đúng database/container và theo hướng dẫn upgrade. Trong CDB/PDB, cần xác định các container cần compile; một lần chạy ở root không nhất thiết thay thế mọi thao tác ở từng PDB.

### 11.5. Compile không sửa lỗi logic

Một object compile thành VALID vẫn có thể:

- Gọi nhầm synonym hoặc service.
- Có logic nghiệp vụ cũ.
- Thiếu grant ở runtime.
- Gây exception khi thực thi.
- Trả kết quả khác do NLS/timezone.

Vì vậy, sau compile vẫn cần smoke test và application tests.

### 11.6. Khi nào không nên compile tất cả?

Không compile tất cả object một cách mù quáng nếu:

- Có object intentionally invalid trong deployment.
- Dependency ngoài database chưa được dựng.
- Component registry chưa hợp lệ.
- Object đang được thay đổi bởi deployment khác.
- Compile có thể gây tải đáng kể.

Lập danh sách expected invalid và xử lý từng nhóm theo nguyên nhân.

## 12. Sequence và identity sau migration

### 12.1. Vì sao phải kiểm tra?

Sequence có thể không được đồng bộ với giá trị khóa lớn nhất đã import. Sau cutover, ứng dụng gọi NEXTVAL có thể sinh key đã tồn tại và gặp unique constraint violation.

### 12.2. Kiểm tra sequence metadata

```sql
SELECT sequence_owner,
       sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM dba_sequences
WHERE sequence_owner = 'APP'
ORDER BY sequence_name;
```

LAST_NUMBER có thể là giá trị cache/giá trị kế tiếp được ghi trong dictionary, không phải lúc nào cũng chính xác bằng NEXTVAL tiếp theo khi cache đang hoạt động. Không dùng LAST_NUMBER làm bằng chứng tuyệt đối về giá trị sẽ được cấp.

### 12.3. So sánh với MAX(primary key)

```sql
SELECT MAX(order_id) AS max_order_id
FROM app.orders;
```

Đối chiếu với sequence tương ứng và increment direction. Nếu sequence tăng, giá trị cấp tiếp theo phải vượt các key hiện có theo policy. Với sequence giảm, cycle hoặc sequence dùng chung nhiều bảng, cần phân tích riêng.

### 12.4. Không gọi NEXTVAL chỉ để kiểm tra

NEXTVAL làm sequence tiến lên và không thể rollback. Không dùng NEXTVAL tùy tiện trên production để xem thử. Có thể dùng một test sequence hoặc quy trình maintenance có ghi nhận giá trị tiêu thụ.

### 12.5. Identity columns

Kiểm tra:

```sql
SELECT owner,
       table_name,
       column_name,
       generation_type,
       sequence_name
FROM dba_tab_identity_cols
WHERE owner = 'APP'
ORDER BY table_name, column_name;
```

Identity column có sequence nội bộ; không quản lý như sequence ứng dụng thông thường nếu chưa hiểu cách Oracle gắn identity metadata. Kiểm tra behavior insert sau import và không giả định tên sequence nội bộ ổn định giữa các release.

## 13. LOB, index, constraint và dữ liệu đặc biệt

### 13.1. LOB columns

Kiểm tra bảng có CLOB/BLOB/NCLOB/BFILE:

```sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length
FROM dba_tab_columns
WHERE owner = 'APP'
  AND data_type IN ('CLOB', 'BLOB', 'NCLOB', 'BFILE')
ORDER BY table_name, column_id;
```

Đối soát LOB cần kiểm tra length và nội dung/hash; row count không đủ. BFILE chỉ lưu locator/path tới file ngoài database, không có nghĩa file đã được copy.

### 13.2. LOB segment metadata

DBA_LOBS và DBA_LOB_PARTITIONS có thể cho biết segment/tablespace và storage metadata. Xác minh SecureFiles/BasicFiles, compression, deduplication, encryption và tablespace mapping nếu migration có thay đổi.

### 13.3. Index status và usability

Index INVALID/UNUSABLE có thể ảnh hưởng truy vấn hoặc DML. Với partitioned index, kiểm tra từng partition/subpartition:

```sql
SELECT index_owner,
       index_name,
       partition_name,
       status
FROM dba_ind_partitions
WHERE index_owner = 'APP'
ORDER BY index_name, partition_position;
```

### 13.4. Constraint validation

Kiểm tra primary key, unique key, foreign key, check constraint và trạng thái ENABLED/VALIDATED. Một constraint tồn tại nhưng DISABLED không đảm bảo dữ liệu đúng.

### 13.5. Trigger side effects

Trigger có thể bị disable trong quá trình load để tăng tốc. Sau import, xác định trigger nào phải enable, trigger nào không được chạy lại trên dữ liệu cũ và trigger nào có thể tạo side effects khi enable.

### 13.6. Materialized view

Kiểm tra compile status, staleness, refresh mode và materialized view logs. Refresh có thể tạo tải lớn hoặc thay đổi kết quả; chỉ refresh sau khi xác định đúng dependency và business cutoff.

## 14. Tự động hóa đối soát

### 14.1. Manifest đối soát

Tạo manifest có một dòng cho mỗi bảng/đơn vị đối soát:

| Trường | Nội dung |
|---|---|
| Schema/table | Tên object |
| Snapshot ID | SCN hoặc business cutoff |
| Source count | Exact count |
| Target count | Exact count |
| Count delta | Target trừ source |
| Business totals | Các aggregate quan trọng |
| Checksum version | Quy tắc canonicalization/hash |
| Mismatch count | Số key/row khác |
| Status | PASS/FAIL/EXCEPTION |
| Evidence | Query ID, log path, timestamp |

Không ghi chỉ PASS/FAIL mà không giữ query, snapshot và evidence để tái lập.

### 14.2. Status semantics

- PASS: tất cả tiêu chí đã thống nhất đều đạt.
- FAIL: có mismatch chưa giải thích hoặc object không đạt yêu cầu.
- EXCEPTION: có sai lệch được nghiệp vụ chấp nhận bằng phê duyệt cụ thể.
- NOT_RUN: chưa thực hiện.

EXCEPTION phải có owner, lý do, impact, expiry và bằng chứng; không dùng exception để che một kiểm tra chưa chạy.

### 14.3. Chạy theo nhóm ưu tiên

Ưu tiên kiểm tra:

1. Bảng transaction trọng yếu.
2. Bảng master/configuration.
3. Bảng balance/ledger/financial control.
4. Bảng quan hệ và mapping.
5. Bảng audit/history lớn.
6. Bảng ít quan trọng hoặc dữ liệu có thể tái tạo.

Thứ tự ưu tiên giúp phát hiện vấn đề ảnh hưởng cutover sớm hơn.

### 14.4. Chạy song song có kiểm soát

Có thể chia bảng hoặc partition cho nhiều worker, nhưng phải tránh quá tải source/target. Cân nhắc:

- CPU và I/O capacity.
- Database link bandwidth.
- Undo/redo generation.
- Lock và concurrency.
- Resource Manager.
- Kích thước result set và temp usage.

### 14.5. Không so sánh trên dữ liệu đang thay đổi

Nếu source/target tiếp tục ghi, manifest có thể chứa số liệu từ các thời điểm khác nhau. Gắn snapshot ID vào mọi kết quả và không tổng hợp các metric không cùng snapshot thành một báo cáo PASS.

## 15. Quy trình đối soát end-to-end

### Giai đoạn A — Trước migration

1. Chốt schema/table/object scope.
2. Thu thập Oracle release, character set, timezone file và COMPATIBLE.
3. Ghi row counts/aggregates baseline.
4. Xác định primary/business keys.
5. Định nghĩa business control totals.
6. Lập danh sách object, grants, constraints, indexes, triggers, sequences.
7. Chọn snapshot/SCN và freeze/delta strategy.
8. Thống nhất acceptance criteria.

### Giai đoạn B — Trong migration

1. Chụp SCN hoặc chốt write freeze.
2. Chạy export và lưu log/parameter file.
3. Chuyển dump/datafiles qua kênh kiểm soát.
4. Chạy import/transport.
5. Lưu import log và mọi warning/error.
6. Áp dụng delta nếu có.
7. Giữ source trong trạng thái có thể rollback theo kế hoạch.

### Giai đoạn C — Đối soát kỹ thuật

1. So sánh object inventory.
2. Exact COUNT(*) theo bảng/partition.
3. So sánh aggregates theo business dimension.
4. So sánh keys và row values hai chiều.
5. Kiểm tra duplicates/orphans.
6. Kiểm tra LOB content/length.
7. Kiểm tra constraints/indexes/triggers.
8. Liệt kê INVALID objects và compile theo nguyên nhân.
9. Kiểm tra sequences/identity.
10. Kiểm tra grants, synonyms, database links và Scheduler jobs.

### Giai đoạn D — Kiểm thử ứng dụng

1. Smoke test login/connectivity.
2. Chạy luồng đọc/ghi trọng yếu.
3. Kiểm tra report và business totals.
4. Kiểm tra batch/Scheduler jobs.
5. Kiểm tra timestamp, timezone và Unicode.
6. Kiểm tra application errors và performance.

### Giai đoạn E — Cutover sign-off

1. Xác nhận mọi bảng trọng yếu PASS.
2. Giải thích mọi delta và exception.
3. Đóng các INVALID objects bắt buộc.
4. Xác nhận constraints/indexes/sequence state.
5. Nhận sign-off của DBA và business owner.
6. Mở traffic theo kế hoạch.
7. Theo dõi sau cutover.
8. Chỉ giải phóng source/backup/rollback path sau thời hạn được phê duyệt.

## 16. Ví dụ bộ truy vấn đối soát

### 16.1. Row count

Chạy trên source và target tại cùng snapshot:

```sql
SELECT COUNT(*) AS orders_count
FROM app.orders;
```

### 16.2. Business totals

```sql
SELECT currency_code,
       order_status,
       COUNT(*) AS row_count,
       SUM(total_amount) AS amount_total,
       SUM(tax_amount) AS tax_total,
       MIN(created_at) AS first_created,
       MAX(created_at) AS last_created
FROM app.orders
GROUP BY currency_code, order_status
ORDER BY currency_code, order_status;
```

### 16.3. Null counts

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(*) - COUNT(customer_id) AS null_customer_id,
       COUNT(*) - COUNT(total_amount) AS null_total_amount,
       COUNT(*) - COUNT(order_status) AS null_order_status
FROM app.orders;
```

### 16.4. Missing keys

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
WHERE NOT EXISTS (
    SELECT 1
    FROM app.orders t
    WHERE t.order_id = s.order_id
);
```

### 16.5. Different values

```sql
SELECT s.order_id
FROM app.orders@SRC_LINK s
JOIN app.orders t
  ON t.order_id = s.order_id
WHERE DECODE(t.customer_id, s.customer_id, 0, 1) = 1
   OR DECODE(t.order_status, s.order_status, 0, 1) = 1
   OR DECODE(t.total_amount, s.total_amount, 0, 1) = 1;
```

### 16.6. Invalid objects

```sql
SELECT object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE owner = 'APP'
  AND status = 'INVALID'
GROUP BY object_type
ORDER BY object_type;
```

### 16.7. Compile errors

```sql
SELECT name, type, line, position, text
FROM dba_errors
WHERE owner = 'APP'
ORDER BY name, type, sequence;
```

### 16.8. Constraints not enabled and validated

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP'
  AND (status <> 'ENABLED' OR validated <> 'VALIDATED')
ORDER BY table_name, constraint_name;
```

### 16.9. Unusable indexes

```sql
SELECT index_name, table_name, status
FROM dba_indexes
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY table_name, index_name;
```

### 16.10. Disabled triggers

```sql
SELECT trigger_name, table_name, status
FROM dba_triggers
WHERE owner = 'APP'
  AND status = 'DISABLED'
ORDER BY table_name, trigger_name;
```

## 17. Báo cáo mismatch và điều tra

### 17.1. Phân loại mismatch

Mỗi mismatch nên được phân loại:

- MISSING_TARGET: source có row nhưng target không có.
- EXTRA_TARGET: target có row nhưng source không có.
- VALUE_MISMATCH: cùng key nhưng nội dung khác.
- COUNT_MISMATCH: số dòng khác.
- AGGREGATE_MISMATCH: business total khác.
- METADATA_MISMATCH: thiếu hoặc khác object/constraint/index.
- INVALID_OBJECT: object compile không thành công.
- EXPECTED_DELTA: khác biệt đã được dự kiến theo snapshot/cutover.

### 17.2. Điều tra theo mức ảnh hưởng

Ưu tiên:

1. Financial totals hoặc ledger imbalance.
2. Missing transaction/master data.
3. Duplicate keys và orphan references.
4. Timestamp/character conversion.
5. Invalid code path và disabled triggers.
6. Index/statistics/performance issues.
7. Sai lệch ở bảng có thể tái tạo.

### 17.3. Ghi nhận root cause

Với mỗi mismatch, ghi:

- Object và key hoặc partition.
- Source/target snapshot.
- Giá trị source/target.
- Query tái hiện.
- Số lượng bị ảnh hưởng.
- Nguyên nhân gốc.
- Cách sửa/reload.
- Kết quả đối soát lại.
- Người phê duyệt nếu chấp nhận exception.

### 17.4. Không sửa target trước khi lưu evidence

Nếu phát hiện sai lệch, lưu kết quả và log trước khi sửa. Sau khi reload/correct, chạy lại đúng phép đối soát trên snapshot phù hợp. Không xóa mismatch report chỉ vì target đã được sửa.

## 18. Các bẫy thường gặp

### 18.1. Dùng NUM_ROWS thay COUNT(*)

NUM_ROWS có thể stale hoặc chỉ là statistics estimate. Dùng exact count cho bảng trọng yếu.

### 18.2. So sánh source live với target snapshot

Source có thể phát sinh DML sau export. Gắn snapshot SCN hoặc business watermark vào báo cáo.

### 18.3. Chỉ so sánh tổng row count

Một bảng có thể thiếu row và thừa row với cùng số lượng. Cần compare key và row content.

### 18.4. Chỉ so sánh SUM

Hai tập giá trị khác nhau có thể có cùng tổng. So sánh theo nhóm và row-level.

### 18.5. Dùng ORA_HASH như checksum tuyệt đối

ORA_HASH không phải cryptographic hash và có collision. Không dùng một tổng ORA_HASH để tuyên bố dữ liệu giống hoàn toàn.

### 18.6. MINUS trên bảng có duplicate

MINUS loại duplicate. Nếu multiplicity quan trọng, so sánh theo key hoặc GROUP BY kèm COUNT.

### 18.7. Bỏ qua NULL

SUM, COUNT(column), MIN/MAX có semantics bỏ qua NULL. Kiểm tra null counts riêng.

### 18.8. Không chuẩn hóa timezone

Hai timestamp có thể biểu diễn cùng instant nhưng hiển thị khác timezone; hoặc cùng local time nhưng biểu diễn instant khác. Xác định so sánh instant hay business-local time.

### 18.9. Hash chuỗi phụ thuộc NLS

TO_CHAR number/date không có format và NLS parameters rõ ràng có thể tạo hash khác giữa source/target.

### 18.10. Object VALID nhưng runtime fail

Object compile được vẫn có thể thiếu privilege, trỏ synonym sai hoặc gọi database link không tồn tại. Chạy application smoke tests.

### 18.11. INVALID object không được phân loại

Một số object có thể INVALID có chủ đích trong deployment; một số khác là lỗi thực sự. So sánh với baseline/expected list và ghi rõ ngoại lệ.

### 18.12. Sequence bị bỏ qua

Row counts và constraints có thể đều đúng nhưng sequence thấp hơn MAX(primary key). Kiểm tra trước khi mở write traffic.

## 19. Bài thực hành đối soát migration

Thực hiện trên hai schema lab có dữ liệu giống nhau, sau đó cố tình tạo một số mismatch nhỏ để luyện cách phát hiện. Không chạy DML thử nghiệm trên production.

### Bước 1 — Chuẩn bị bảng

Tạo bảng orders có primary key, customer_id, status, amount, currency và created_at. Nạp dữ liệu mẫu vào source rồi export/import sang target.

### Bước 2 — Chốt snapshot

Ghi current SCN của source hoặc dừng ghi dữ liệu trong lab. Ghi lại thời điểm và database identity.

### Bước 3 — Đếm exact rows

Chạy COUNT(*) trên source và target. Ghi kết quả vào manifest.

### Bước 4 — Đếm theo status/date

Chạy GROUP BY status và business date. Xác định group nào khác nếu có.

### Bước 5 — Tính business totals

So sánh SUM(amount), SUM(tax), COUNT(DISTINCT customer_id), null counts, MIN/MAX date theo currency.

### Bước 6 — Tạo mismatch có chủ đích

Trong target lab, sửa amount của một order, xóa một row và thêm một row khác. Giữ tổng row count bằng source nếu muốn mô phỏng trường hợp count tổng không phát hiện được sai lệch.

### Bước 7 — Tìm missing/extra keys

Chạy NOT EXISTS hai chiều hoặc FULL OUTER JOIN theo PK. Ghi missing và extra key.

### Bước 8 — Tìm value mismatch

Join theo PK và dùng null-safe comparison cho các cột scalar. Kiểm tra số row mismatch.

### Bước 9 — Kiểm tra duplicate/orphan

Tạo duplicate hoặc orphan có chủ đích trong lab khi constraint cho phép, rồi chạy query phát hiện. Khôi phục dữ liệu sau thử nghiệm.

### Bước 10 — Tạo INVALID object

Trong schema lab, tạo một view/procedure phụ thuộc object không tồn tại hoặc đổi dependency để object compile INVALID. Xem DBA_OBJECTS và DBA_ERRORS.

### Bước 11 — Compile và xác minh

Sửa dependency, compile object, kiểm tra status VALID và chạy thử logic. Không chỉ dựa vào status.

### Bước 12 — Kiểm tra sequence

So sánh MAX(primary key) với sequence policy. Không gọi NEXTVAL trên sequence nghiệp vụ nếu không cần.

### Bước 13 — Hoàn thiện manifest

Ghi source/target counts, aggregates, mismatch counts, invalid objects, exceptions và evidence.

## 20. Checklist migration sign-off

- [ ] Đã xác định chính xác scope schema/table/object.
- [ ] Đã ghi SCN hoặc business cutoff của snapshot.
- [ ] Source và target được so sánh trên cùng phạm vi thời gian.
- [ ] Exact COUNT(*) đã chạy cho bảng trọng yếu.
- [ ] Row counts đã so sánh theo partition/business dimensions.
- [ ] NUM_ROWS chỉ dùng làm thống kê tham khảo.
- [ ] Business totals đã được so sánh theo currency/status/date/tenant.
- [ ] Null counts và distinct counts đã được kiểm tra.
- [ ] Key-level missing/extra rows đã được kiểm tra hai chiều.
- [ ] Value mismatches đã được liệt kê và xử lý.
- [ ] Checksum có canonicalization/version được ghi nhận.
- [ ] Không dùng SUM/ORA_HASH đơn lẻ làm bằng chứng đầy đủ.
- [ ] Duplicate keys và orphan references đã được kiểm tra.
- [ ] Constraints ở trạng thái ENABLED/VALIDATED theo yêu cầu.
- [ ] Index và index partitions không còn UNUSABLE ngoài ngoại lệ đã duyệt.
- [ ] Trigger status phù hợp cutover plan.
- [ ] LOB content/length và BFILE external files đã được kiểm tra.
- [ ] Views/materialized views và dependencies đã được kiểm tra.
- [ ] INVALID objects đã được liệt kê, phân loại và compile/test.
- [ ] DBA_ERRORS không còn lỗi chưa giải thích ở object trọng yếu.
- [ ] DBA_REGISTRY components ở trạng thái yêu cầu.
- [ ] Sequences/identity không thấp hơn key range cần cấp.
- [ ] Grants, roles, synonyms, database links và directory objects đã được xác nhận.
- [ ] Scheduler jobs/credentials được enable đúng thời điểm.
- [ ] Application smoke tests và business tests đã pass.
- [ ] Mọi exception có owner, impact và phê duyệt.
- [ ] Có report/evidence và rollback decision được ký nhận.

## 21. Câu hỏi tự kiểm tra

1. Vì sao Data Pump import thành công chưa đủ để kết luận migration hoàn tất?
2. Snapshot consistency có ý nghĩa gì khi đối soát source và target?
3. FLASHBACK_SCN hỗ trợ Data Pump export như thế nào?
4. Vì sao SCN của hai database độc lập không thể so sánh trực tiếp?
5. NUM_ROWS khác COUNT(*) ở điểm nào?
6. COUNT(*) khác COUNT(column) ra sao?
7. Vì sao phải đếm theo partition và business dimension?
8. Row count giống nhau có thể che giấu những lỗi nào?
9. Business control totals nên gồm các metric nào?
10. Vì sao tổng tiền cần được nhóm theo currency?
11. Rounding từng dòng khác rounding sau tổng như thế nào?
12. Vì sao aggregate giống nhau không chứng minh row-level equality?
13. Checksum cần canonicalize những datatype nào?
14. Vì sao ORA_HASH không phải cryptographic checksum?
15. Vì sao delimiter và NULL sentinel có thể làm serialization nhập nhằng?
16. STANDARD_HASH và DBMS_CRYPTO có vai trò gì?
17. Khi nào cần hash LOB bằng cơ chế streaming?
18. Vì sao nên so sánh theo primary/business key thay vì ROWID?
19. MINUS hai chiều có giới hạn gì với duplicate và LOB?
20. Làm thế nào tìm missing key và extra key?
21. Vì sao cần kiểm tra duplicate và orphan foreign keys?
22. ENABLE NOVALIDATE khác ENABLE VALIDATE thế nào?
23. DBA_OBJECTS và DBA_ERRORS giúp tìm INVALID object ra sao?
24. DBA_REGISTRY liên quan gì đến compile failures?
25. DBMS_UTILITY.COMPILE_SCHEMA và UTL_RECOMP được dùng khi nào?
26. Vì sao compile thành VALID chưa đủ để sign-off?
27. Sequence LAST_NUMBER có phải NEXTVAL tiếp theo chính xác không?
28. Identity columns cần được kiểm tra thế nào sau import?
29. Những object nào ngoài table data cần xác nhận sau migration?
30. Một migration sign-off report cần giữ những evidence nào?

**Nguyên tắc cần nhớ:** Đối soát chỉ có giá trị khi source và target thuộc cùng snapshot hoặc có delta được kiểm soát. Exact row counts kiểm tra completeness; business totals kiểm tra phân bố và ý nghĩa dữ liệu; key-based diff tìm row thiếu/thừa/khác; metadata checks xác nhận constraint, index, trigger, sequence và object status. NUM_ROWS là statistics, SUM hoặc ORA_HASH đơn lẻ không phải bằng chứng đầy đủ. Hãy phân loại và sửa mọi mismatch, compile/test object INVALID, xác minh sequence trước khi mở ghi production, và lưu evidence cùng sign-off.

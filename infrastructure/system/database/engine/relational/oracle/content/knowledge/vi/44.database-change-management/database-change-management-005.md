# Mô hình mở rộng rồi thu hẹp để đổi schema tương thích ứng dụng

## 1. Vì sao cần mô hình expand-and-contract?

Trong hệ thống chạy liên tục, database schema và ứng dụng thường không thể được triển khai cùng một thời điểm. Một lần rolling deployment có thể khiến nhiều phiên bản ứng dụng cùng hoạt động: instance cũ chưa được thay thế, instance mới đã bắt đầu nhận request, worker nền vẫn đang chạy, batch job chưa được restart. Nếu schema bị đổi đột ngột theo cách chỉ một phiên bản hiểu được, một phần ứng dụng có thể lỗi ngay trong quá trình triển khai.

Mô hình **expand-and-contract** (mở rộng rồi thu hẹp) giải quyết vấn đề bằng cách chia thay đổi schema thành các bước tương thích ngược và tương thích xuôi:

1. **Expand:** thêm cấu trúc mới mà phiên bản ứng dụng cũ vẫn chạy được.
2. **Migrate:** chuyển dữ liệu và triển khai ứng dụng có thể làm việc với cả cấu trúc cũ lẫn mới.
3. **Switch:** chuyển việc đọc và ghi sang cấu trúc mới sau khi dữ liệu đã đồng bộ.
4. **Contract:** chỉ xóa cấu trúc cũ khi không còn phiên bản ứng dụng hoặc tiến trình nào phụ thuộc vào nó.

Mục tiêu là duy trì khả năng phục vụ trong lúc rolling deployment diễn ra, đồng thời có các điểm kiểm soát để dừng hoặc quay lại phiên bản trước nếu phát hiện vấn đề.

```text
Schema cũ
   |
   v
EXPAND: thêm cột/bảng/API mới, giữ cấu trúc cũ
   |
   v
MIGRATE: backfill dữ liệu, duy trì đồng bộ hai dạng
   |
   v
SWITCH: ứng dụng đọc cấu trúc mới, vẫn tương thích writer cũ
   |
   v
CONTRACT: gỡ bridge, xóa cấu trúc cũ sau khi hết phụ thuộc
   |
   v
Schema mới
```

Đây là một chiến lược triển khai schema theo nhiều lần release. Nó đặc biệt hữu ích với Oracle Database khi DDL có thể gây implicit commit và cần quản lý lock/metadata operation riêng với transaction nghiệp vụ.

## 2. Nguyên tắc tương thích giữa nhiều phiên bản ứng dụng

### 2.1. Schema phải hỗ trợ cả phiên bản cũ và mới trong giai đoạn chuyển tiếp

Giả sử bảng `CUSTOMERS` hiện có cột `CUSTOMER_NAME`, nhưng thiết kế mới muốn dùng `DISPLAY_NAME`.

Phiên bản ứng dụng cũ:

- Đọc `CUSTOMER_NAME`.
- Ghi `CUSTOMER_NAME`.
- Không biết cột `DISPLAY_NAME` tồn tại.

Phiên bản chuyển tiếp:

- Đọc `DISPLAY_NAME` sau khi dữ liệu đã được backfill.
- Ghi đồng thời `DISPLAY_NAME` và `CUSTOMER_NAME` để phiên bản cũ vẫn đọc được.

Phiên bản cuối:

- Chỉ đọc và ghi `DISPLAY_NAME`.
- Không còn tham chiếu `CUSTOMER_NAME`.

Trong giai đoạn rolling deployment, database phải cho phép các phiên bản này cùng tồn tại theo ma trận đã định nghĩa. Nếu thêm cột mới với `NOT NULL` mà không có default/giá trị tương thích, câu `INSERT` từ ứng dụng cũ có thể thất bại ngay. Vì vậy, bước expand thường thêm cột nullable trước.

### 2.2. Ma trận tương thích

| Phiên bản ứng dụng | Đọc | Ghi | Có thể chạy trên schema expand? |
|---|---|---|---|
| V1 cũ | `CUSTOMER_NAME` | `CUSTOMER_NAME` | Có, nếu cột cũ vẫn còn |
| V2 chuyển tiếp | `DISPLAY_NAME` | Cả hai cột | Có, sau khi cột mới và dữ liệu được chuẩn bị |
| V3 cuối | `DISPLAY_NAME` | `DISPLAY_NAME` | Có, sau khi mọi writer cũ đã được loại bỏ |

Không chỉ kiểm tra web/API instance. Cần liệt kê mọi thành phần có thể đọc hoặc ghi schema: batch job, scheduler, ETL, báo cáo, stored procedure, trigger, integration service, CDC pipeline, script vận hành và công cụ ad-hoc.

### 2.3. Tách triển khai ứng dụng khỏi thay đổi schema

Một release an toàn thường có các bước độc lập:

- Database migration mở rộng schema.
- Backfill dữ liệu theo batch.
- Deploy ứng dụng chuyển tiếp.
- Chuyển read path và quan sát.
- Deploy phiên bản cuối.
- Dọn schema cũ.

Không gộp tất cả vào một migration duy nhất rồi kỳ vọng rollback một lệnh là trở lại trạng thái cũ. Các bước DDL, DML backfill và deployment ứng dụng có lifecycle, transaction và khả năng rollback khác nhau.

## 3. Ví dụ thay tên cột CUSTOMER_NAME thành DISPLAY_NAME

### 3.1. Schema ban đầu

```sql
CREATE TABLE customers (
    customer_id   NUMBER(19) PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    created_at    TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);
```

Ứng dụng V1 đang sử dụng `CUSTOMER_NAME` trong câu SQL, entity mapping, stored procedure và báo cáo.

### 3.2. Bước expand: thêm cột mới

Thêm cột mới ở trạng thái nullable:

```sql
ALTER TABLE customers
ADD (display_name VARCHAR2(200));
```

Sau bước này:

- V1 vẫn đọc/ghi `CUSTOMER_NAME` như trước.
- `DISPLAY_NAME` tồn tại nhưng chưa có dữ liệu cho các dòng cũ.
- Không thay đổi tên hoặc xóa cột cũ.
- Không bật constraint bắt buộc trên cột mới trước khi backfill và xác nhận writer đã sẵn sàng.

Việc thêm cột là DDL. Oracle thực hiện implicit commit xung quanh DDL; không coi `ALTER TABLE` là một phần có thể rollback cùng transaction DML trước đó. Chạy migration trong quy trình riêng và xác nhận trạng thái trước/sau.

### 3.3. Giữ đồng bộ khi V1 vẫn đang ghi cột cũ

Trong lúc V1 còn hoạt động, các lệnh `INSERT`/`UPDATE` của nó chỉ biết `CUSTOMER_NAME`. Nếu V2 đọc `DISPLAY_NAME`, dữ liệu mới từ V1 phải được phản chiếu sang cột mới.

Có thể dùng trigger tương thích một chiều trong giai đoạn chuyển tiếp:

```sql
CREATE OR REPLACE TRIGGER customers_name_bridge_trg
BEFORE INSERT OR UPDATE OF customer_name ON customers
FOR EACH ROW
BEGIN
    :NEW.display_name := :NEW.customer_name;
END;
/
```

Trigger này lấy `CUSTOMER_NAME` làm nguồn cho `DISPLAY_NAME` khi insert hoặc khi câu lệnh cập nhật cột cũ. Điều kiện vận hành của ví dụ là phiên bản chuyển tiếp ghi cùng một giá trị vào cả hai cột; trigger sẽ giữ giá trị mới đồng nhất với cột cũ.

Trigger là một bridge tạm thời. Cần kiểm tra quyền sở hữu, trạng thái valid, compilation errors, thứ tự trigger hiện có và tác động hiệu năng. Nếu ứng dụng có trigger khác cập nhật hai cột, phải xác định rõ thứ tự và nguồn dữ liệu chuẩn để tránh ghi đè lẫn nhau.

Một lựa chọn khác là triển khai bridge ở application/service layer, nhưng cách đó chỉ an toàn nếu tất cả writer đã được nâng cấp trước khi phiên bản mới đọc cột mới. Khi V1 vẫn có thể ghi cột cũ, trigger hoặc một cơ chế đồng bộ database đáng tin cậy giúp tránh bỏ sót writer.

### 3.4. Backfill dữ liệu cũ theo batch

Sau khi bridge được cài đặt, copy dữ liệu hiện có:

```sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL
  AND customer_name IS NOT NULL;

COMMIT;
```

Với bảng nhỏ, một lệnh có thể đủ. Với bảng lớn, nên backfill theo batch để giảm thời gian giữ lock, lượng undo/redo mỗi transaction, áp lực archive log và ảnh hưởng tới workload đang chạy.

Ví dụ vòng lặp batch theo ROWID:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE customers c
        SET c.display_name = c.customer_name
        WHERE c.display_name IS NULL
          AND c.customer_name IS NOT NULL
          AND c.ROWID IN (
              SELECT x.ROWID
              FROM customers x
              WHERE x.display_name IS NULL
                AND x.customer_name IS NOT NULL
                AND ROWNUM <= 1000
          );

        l_rows := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
```

`1000` chỉ là kích thước batch minh họa. Chọn batch size theo kích thước dòng, tốc độ redo/undo, I/O, thời gian lock, mức tải và RTO. Có thể commit mỗi batch, ghi tiến độ và tiếp tục sau lỗi.

Backfill phải idempotent: chạy lại không làm hỏng dữ liệu đã chuyển. Điều kiện `DISPLAY_NAME IS NULL` giúp chỉ cập nhật các dòng chưa được điền, nhưng cần xem xét trường hợp `CUSTOMER_NAME` hợp lệ có giá trị NULL hoặc nghiệp vụ cho phép `DISPLAY_NAME` khác `CUSTOMER_NAME`. Khi đó cần thêm cờ migration hoặc quy tắc chuyển đổi chính xác thay vì dùng null như dấu hiệu duy nhất.

Trigger được cài trước khi backfill để các thay đổi mới từ writer cũ tiếp tục cập nhật cột mới trong khi batch chạy. Dù vậy, sau backfill vẫn cần chạy một lượt catch-up và kiểm tra dữ liệu để xác nhận không còn khoảng trống.

### 3.5. Kiểm tra dữ liệu sau backfill

Đếm các dòng chưa được chuyển:

```sql
SELECT COUNT(*) AS missing_display_name
FROM customers
WHERE customer_name IS NOT NULL
  AND display_name IS NULL;
```

So sánh các giá trị:

```sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE customer_name <> display_name
   OR (customer_name IS NULL AND display_name IS NOT NULL)
   OR (customer_name IS NOT NULL AND display_name IS NULL);
```

Nếu hai cột phải giống nhau hoàn toàn, `MISMATCH_COUNT` cần bằng 0 tại thời điểm xác nhận. Nếu chuyển đổi có quy tắc chuẩn hóa (ví dụ trim, đổi format hoặc ghép trường), hãy so sánh theo biểu thức chuyển đổi thay vì so sánh bằng trực tiếp.

Với bảng lớn, các truy vấn kiểm tra toàn bảng cũng có chi phí. Có thể chạy theo partition hoặc key range, theo dõi tiến độ và dùng snapshot nhất quán nếu cần so sánh chính xác trong lúc hệ thống vẫn ghi dữ liệu.

## 4. Bước migrate: triển khai ứng dụng chuyển tiếp

### 4.1. V2 đọc cột mới và ghi cả hai cột

Sau khi dữ liệu cũ đã được backfill và kiểm tra, triển khai V2:

- Đọc `DISPLAY_NAME`.
- Khi insert/update, ghi cùng giá trị vào `CUSTOMER_NAME` và `DISPLAY_NAME`.
- Không giả định V1 đã biến mất ngay khi bắt đầu rolling deployment.

Ví dụ SQL của V2:

```sql
INSERT INTO customers (
    customer_id,
    customer_name,
    display_name
)
VALUES (
    :customer_id,
    :display_name,
    :display_name
);
```

Update:

```sql
UPDATE customers
SET customer_name = :display_name,
    display_name  = :display_name
WHERE customer_id = :customer_id;
```

Trigger bridge tiếp tục bảo đảm writer V1 chỉ cập nhật `CUSTOMER_NAME` cũng làm mới `DISPLAY_NAME`. V2 ghi cả hai để các consumer cũ có thể tiếp tục đọc cột cũ.

Không để V2 đọc cột mới trước khi backfill hoàn tất hoặc trước khi có logic fallback an toàn. Nếu cần deploy code trước backfill vì lý do vận hành, feature flag có thể giữ read path cũ cho tới khi validation hoàn tất.

### 4.2. Tách read switch khỏi write switch

Có thể dùng feature flag để chuyển read path sau khi dữ liệu mới đã sẵn sàng:

```text
V2 deployed, read_old=true, write_both=true
        |
        v
Backfill + validation complete
        |
        v
read_new=true, write_both=true
        |
        v
Observe metrics and data consistency
```

Tách hai quyết định này giúp rollback dễ hơn. Nếu V2 đọc `DISPLAY_NAME` và phát hiện sai lệch, có thể chuyển read path về `CUSTOMER_NAME` trong khi vẫn tiếp tục ghi cả hai cột để sửa dữ liệu.

Feature flag không thay thế schema compatibility. V1 vẫn phải chạy được trên schema đã expand; V2 chỉ được bật đọc cột mới sau khi điều kiện dữ liệu được thỏa mãn.

### 4.3. Theo dõi trong giai đoạn mixed-version

Trong rolling deployment, quan sát:

- Số instance/worker còn chạy V1.
- Số request ghi qua V1 và V2.
- Trigger execution/error và invalid status.
- Số dòng `DISPLAY_NAME` còn thiếu hoặc lệch.
- Lỗi SQL như `ORA-00904` (invalid identifier), `ORA-01400` (cannot insert NULL) và lỗi constraint.
- Latency, lock wait, redo/undo generation và connection pool.

Không coi deployment V2 hoàn tất chỉ vì toàn bộ web instance đã được cập nhật. Batch job, scheduler, consumer và service ít được gọi có thể vẫn chạy binary cũ trong thời gian dài.

## 5. Bước switch: chuyển toàn bộ consumer sang schema mới

### 5.1. Xác nhận không còn consumer đọc cột cũ

Trước khi loại bỏ `CUSTOMER_NAME`, kiểm kê tất cả phụ thuộc:

- SQL trong source code và binary của mọi service.
- JPA/Hibernate mapping, native query, stored procedure, package và view.
- Trigger, materialized view, database link và synonym.
- ETL, BI/reporting, data warehouse, CDC/replication và data export.
- Scheduler, batch job, script triển khai và công cụ vận hành.
- Các consumer ngoài tổ chức hoặc nhóm khác dùng schema trực tiếp.

Oracle data dictionary có thể giúp tìm dependency của object database, ví dụ `DBA_DEPENDENCIES`, nhưng không thể phát hiện đầy đủ SQL động, SQL trong ứng dụng hoặc query do công cụ bên ngoài gửi. Cần kết hợp source search, inventory ứng dụng, monitoring SQL và xác nhận của owner từng integration.

### 5.2. Triển khai V3 chỉ dùng cột mới

Khi V1 đã được loại bỏ hoàn toàn, có thể triển khai V3:

- Chỉ đọc `DISPLAY_NAME`.
- Chỉ ghi `DISPLAY_NAME`.
- Không còn phụ thuộc `CUSTOMER_NAME`.

Trong lúc rolling V2 sang V3, cả hai phiên bản đều đọc `DISPLAY_NAME`. V2 vẫn ghi cả hai; V3 chỉ ghi cột mới. Trigger bridge chỉ đồng bộ từ cột cũ sang cột mới, vì vậy không ảnh hưởng tới giá trị mới được ghi bởi V3.

Đợi toàn bộ V2 instance/worker kết thúc và xác nhận không còn writer nào cần `CUSTOMER_NAME`. Chỉ khi đó mới lên kế hoạch contract.

### 5.3. Đặt constraint mới

Nếu `DISPLAY_NAME` cần `NOT NULL`, trước tiên xác nhận không còn dòng null:

```sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
```

Sau khi dữ liệu hợp lệ, có thể thêm constraint kiểm tra theo quy trình phù hợp với release và kích thước bảng. Oracle hỗ trợ các trạng thái constraint như `ENABLE NOVALIDATE` và `ENABLE VALIDATE` cho một số loại constraint:

```sql
ALTER TABLE customers
  ADD CONSTRAINT customers_display_name_nn
  CHECK (display_name IS NOT NULL)
  ENABLE NOVALIDATE;

ALTER TABLE customers
  ENABLE VALIDATE CONSTRAINT customers_display_name_nn;
```

`ENABLE NOVALIDATE` áp dụng kiểm tra cho dữ liệu mới nhưng chưa xác nhận toàn bộ dữ liệu cũ; `ENABLE VALIDATE` kiểm tra dữ liệu hiện có và có thể tốn thời gian/ảnh hưởng DDL locking. Cú pháp, khả năng online và cách chuyển check constraint thành `NOT NULL` phụ thuộc release. Không dùng NOVALIDATE như bằng chứng rằng dữ liệu cũ đã sạch.

Nếu cần cột thực sự có thuộc tính `NOT NULL` trong metadata, sau khi validate có thể dùng `ALTER TABLE ... MODIFY (DISPLAY_NAME NOT NULL)` theo kế hoạch đã kiểm thử. Kiểm tra constraint và trạng thái dictionary sau DDL.

## 6. Bước contract: loại bỏ schema cũ

### 6.1. Điều kiện trước khi drop

Chỉ contract khi tất cả điều kiện sau đã được xác nhận:

1. Không còn ứng dụng V1 đọc hoặc ghi `CUSTOMER_NAME`.
2. Không còn V2 dual-write hoặc job/consumer cần cột cũ.
3. Stored procedure, view, trigger, report, ETL, CDC và integration đã chuyển sang `DISPLAY_NAME`.
4. Dữ liệu `DISPLAY_NAME` đã được đối chiếu và không còn mismatch ngoài dự kiến.
5. Constraint/index mới đã được tạo và validate nếu nghiệp vụ yêu cầu.
6. Đã qua khoảng thời gian quan sát đủ dài để phát hiện consumer chạy theo lịch tuần/tháng.
7. Có backup/khả năng khôi phục và phương án xử lý nếu contract gây lỗi.

### 6.2. Gỡ trigger bridge

Khi không còn writer nào chỉ cập nhật cột cũ:

```sql
DROP TRIGGER customers_name_bridge_trg;
```

Xác nhận trigger đã được gỡ và không có trigger khác tham chiếu hai cột. DDL có implicit commit; không thể rollback bằng `ROLLBACK` nếu thao tác sau đó thất bại.

### 6.3. Xóa cột cũ

```sql
ALTER TABLE customers
DROP COLUMN customer_name;
```

Đây là bước contract không tương thích với V1/V2. Sau khi chạy, binary hoặc SQL còn tham chiếu `CUSTOMER_NAME` sẽ lỗi. Với bảng lớn hoặc yêu cầu giảm thời gian giữ lock, xem xét các tính năng Oracle phù hợp như `SET UNUSED` trước rồi drop vật lý trong cửa sổ riêng, hoặc các kỹ thuật online redefinition. Khả năng và chi phí phụ thuộc Oracle release, edition, loại object và cấu trúc bảng.

Không dùng `SET UNUSED` như thể cột đã biến mất khỏi mọi metadata; cột được đánh dấu không sử dụng và vẫn chiếm không gian cho tới khi được drop vật lý theo quy trình Oracle.

### 6.4. Xác nhận schema cuối

```sql
SELECT column_name,
       data_type,
       nullable,
       data_length
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
ORDER BY column_id;
```

Kiểm tra constraint, index, trigger và dependency liên quan. Chạy smoke test ứng dụng V3 và kiểm tra log SQL sau khi contract.

## 7. Rollback và khả năng quay lại phiên bản trước

### 7.1. Rollback trong giai đoạn expand/migrate

Trước contract, việc quay lại V1 thường dễ hơn vì cột cũ vẫn còn và bridge tiếp tục cập nhật dữ liệu. Có thể:

- Tắt feature flag đọc `DISPLAY_NAME`.
- Rollback application về V1.
- Giữ cột mới và trigger bridge để điều tra/sửa dữ liệu.
- Dừng backfill nếu phát hiện sai quy tắc, sau đó điều chỉnh và chạy lại idempotently.

Không cần drop cột mới ngay khi rollback ứng dụng. Giữ schema mở rộng thường an toàn hơn và cho phép thử lại sau.

### 7.2. Sau contract, rollback phức tạp hơn

Sau khi xóa `CUSTOMER_NAME`, không thể đơn giản rollback binary về V1. Cần phục hồi schema/data cũ hoặc triển khai một migration ngược tạo lại cột và tái tạo dữ liệu từ cột mới. Nếu phép chuyển đổi mất thông tin, không thể khôi phục nguyên trạng chỉ từ cột mới.

Vì vậy, contract nên được xem là điểm cam kết sau cùng. Trước khi contract, xác nhận owner ứng dụng, thời gian decommission và khả năng rollback đã được thống nhất.

### 7.3. Rollback không đồng nghĩa restore database

Rollback ứng dụng, rollback feature flag, migration ngược và RMAN restore là các thao tác khác nhau. Restore database có thể làm mất giao dịch phát sinh sau backup/SCN và ảnh hưởng nhiều ứng dụng khác. Không dùng restore toàn database để đảo một schema migration nhỏ nếu có cách migration ngược an toàn hơn.

## 8. Đặc thù Oracle cần tính đến

### 8.1. DDL có implicit commit

Oracle thực hiện commit ngầm trước và sau nhiều câu DDL. Ví dụ `ALTER TABLE`, `CREATE INDEX`, `CREATE TRIGGER` và `DROP COLUMN` không nằm trong cùng một transaction rollback với DML trước đó.

Do đó:

- Chạy DDL migration theo bước độc lập và lưu trạng thái migration.
- Không dựa vào `ROLLBACK` để hoàn tác DDL đã thành công.
- Kiểm tra object status và dữ liệu sau từng migration.
- Thiết kế migration ngược bằng DDL/DML riêng nếu có thể.

### 8.2. DDL lock và ảnh hưởng tới DML

DDL cần lock metadata/table theo thao tác. Nếu transaction khác đang sử dụng object hoặc giữ lock liên quan, DDL có thể phải chờ hoặc thất bại do lock timeout. Ngược lại, DDL có thể làm các session mới bị chặn trong khoảng thời gian lấy metadata lock.

Trước migration:

- Xác định transaction dài đang truy cập bảng.
- Chọn cửa sổ triển khai phù hợp và cấu hình DDL lock timeout nếu được hỗ trợ.
- Thử trên bản sao có dữ liệu/kích thước gần production.
- Theo dõi blocking session, wait event và thời gian DDL.
- Tránh chạy migration lớn đồng thời với batch nặng.

### 8.3. CREATE INDEX ONLINE và các thao tác online

Oracle hỗ trợ `ONLINE` cho một số thao tác index/DDL tùy release, loại object và điều kiện license/edition. Ví dụ:

```sql
CREATE INDEX customers_display_name_ix
ON customers(display_name)
ONLINE;
```

`ONLINE` có thể cho phép DML tiếp tục trong một phần quá trình tạo index, nhưng vẫn có các điểm cần lock và giới hạn riêng. Không giả định mọi DDL đều hỗ trợ online hoặc không gây blocking. Kiểm tra tài liệu Oracle đúng phiên bản, edition và loại bảng trước khi dùng.

### 8.4. Backfill tạo redo/undo và archive log

Update hàng triệu dòng tạo undo/redo và có thể làm tăng archive log, backup volume, replication lag hoặc ảnh hưởng Data Guard. Chạy theo batch, commit có kiểm soát, theo dõi FRA, archive destination, undo tablespace và standby apply lag.

Không giảm logging hoặc tắt archive chỉ để tăng tốc migration nếu chưa đánh giá tác động recovery và yêu cầu bảo vệ dữ liệu.

### 8.5. Statistics và execution plan

Thêm cột, backfill và tạo index có thể làm thay đổi cardinality/plan. Sau khi dữ liệu chuyển đổi, kiểm tra statistics và plan của query mới. Gather statistics theo chính sách DBA; không gather hoặc flush shared pool một cách máy móc trong giờ cao điểm.

### 8.6. Edition-Based Redefinition và DBMS_REDEFINITION

Oracle có các công cụ nâng cao cho thay đổi online:

- **Edition-Based Redefinition (EBR):** cho phép duy trì nhiều edition của PL/SQL objects và dùng editioning views để hỗ trợ nâng cấp ứng dụng theo edition. EBR phù hợp với thay đổi code/database object có hỗ trợ edition; nó không tự động biến mọi thay đổi bảng thành không cần migration.
- **DBMS_REDEFINITION:** hỗ trợ online redefinition cho một số thay đổi cấu trúc bảng bằng cách đồng bộ dữ liệu từ bảng trung gian rồi chuyển đổi object. Cần kiểm tra điều kiện eligibility, dependency, quyền, storage và giới hạn theo release.

Expand-and-contract là chiến lược phối hợp giữa application và schema; EBR/DBMS_REDEFINITION là các khả năng Oracle có thể dùng trong một số bước kỹ thuật. Chúng bổ sung cho nhau chứ không phải tên gọi thay thế nhau.

## 9. Thay đổi schema khác ngoài rename column

### 9.1. Thêm cột bắt buộc

Không nên thêm cột `NOT NULL` mà phiên bản cũ không gửi giá trị nếu không có default tương thích. Cách an toàn thường là:

1. Thêm cột nullable hoặc có default được kiểm chứng.
2. Deploy ứng dụng ghi giá trị mới.
3. Backfill các dòng cũ.
4. Kiểm tra không còn null/giá trị không hợp lệ.
5. Thêm và validate constraint.

### 9.2. Đổi kiểu dữ liệu

Thay đổi trực tiếp kiểu cột có thể làm câu SQL cũ lỗi hoặc làm mất dữ liệu. Với chuyển đổi lớn, cân nhắc thêm cột mới có kiểu đích, backfill bằng biểu thức chuyển đổi, kiểm tra dữ liệu không chuyển đổi được, dual-write trong thời gian chuyển tiếp rồi đổi consumer. Không dùng `TO_NUMBER`/`TO_DATE` trong backfill mà chưa xác định format và xử lý giá trị lỗi.

### 9.3. Tách một cột thành nhiều cột

Ví dụ `FULL_NAME` được tách thành `FIRST_NAME` và `LAST_NAME`. Bước expand thêm hai cột; backfill theo quy tắc tách tên đã thống nhất; ứng dụng chuyển tiếp có thể đọc hai cột mới nhưng tiếp tục ghi `FULL_NAME` để phiên bản cũ hoạt động. Nếu quy tắc tách không đảo ngược được, giữ cột gốc tới khi đã xác nhận dữ liệu và consumer cuối cùng chuyển xong.

### 9.4. Gộp nhiều bảng hoặc đổi quan hệ

Khi thay đổi quan hệ, khóa ngoại hoặc cấu trúc bảng, giữ đường đọc/ghi cũ trong giai đoạn chuyển tiếp. Có thể dùng view tương thích hoặc package API để che giấu schema mới. Chuyển dữ liệu theo batch, xác nhận khóa/unique constraint và chỉ xóa cấu trúc cũ khi mọi consumer đã chuyển.

### 9.5. Đổi tên bảng

Thay vì rename trực tiếp, có thể tạo bảng mới, đồng bộ dữ liệu, chuyển ứng dụng qua view/synonym hoặc API tương thích, rồi loại bỏ bảng cũ. Synonym chỉ giải quyết tên object trong một số trường hợp; nó không bảo đảm tương thích cột, quyền, DML behavior hoặc mọi dependency.

## 10. Kiểm thử migration trước khi production

### 10.1. Kiểm thử schema expand với phiên bản cũ

Sau khi thêm cột/trigger/index, chạy toàn bộ integration test của V1 trên schema mới. Mục tiêu là chứng minh V1 vẫn insert, update, select, batch và gọi stored procedure được.

### 10.2. Kiểm thử mixed-version

Chạy V1 và V2 đồng thời trên cùng database test:

- V1 insert/update cột cũ.
- V2 đọc cột mới.
- V2 insert/update cả hai cột.
- Kiểm tra trigger bridge và dữ liệu không lệch.
- Chạy batch job cũ trong khi backfill đang diễn ra.

### 10.3. Kiểm thử backfill và restart

Thử dừng backfill giữa chừng, chạy lại và xác nhận idempotent. Thử writer cập nhật trong lúc backfill; sau khi hoàn tất phải không còn missing/mismatch theo quy tắc chuyển đổi.

### 10.4. Kiểm thử contract

Trong môi trường staging, deploy V3 không còn tham chiếu cột cũ, xác nhận mọi test pass rồi mới drop cột. Cố ý chạy một câu SQL V1 để chứng minh dependency cũ đã được phát hiện trước khi production contract.

### 10.5. Kiểm thử tải và vận hành

Đo thời gian DDL, lock wait, redo/undo, archive generation, replication lag, query latency, connection pool và thời gian backfill. Kiểm thử rolling deployment, restart worker, rollback application và feature flag.

## 11. Checklist triển khai expand-and-contract

| Giai đoạn | Điều kiện cần xác nhận |
|---|---|
| Trước expand | Đã inventory mọi reader/writer; có backup, migration plan, owner và rollback strategy |
| Expand | Cấu trúc mới được thêm theo cách V1 vẫn hoạt động; DDL lock và thời gian thực thi được kiểm soát |
| Bridge | Trigger/service đồng bộ được kiểm thử; xác định rõ cột nguồn và thứ tự ưu tiên khi ghi |
| Backfill | Chạy batch idempotent; theo dõi tiến độ, undo/redo và không làm quá tải hệ thống |
| Validate | Không còn missing/mismatch; constraint/index mới sẵn sàng; dữ liệu được đối chiếu |
| Deploy V2 | V2 đọc schema mới và dual-write; V1 vẫn có thể chạy an toàn |
| Switch | Mọi reader đã chuyển; feature flag và metrics xác nhận read path mới ổn định |
| Deploy V3 | Không còn binary/job nào cần cột cũ; V3 chỉ dùng schema mới |
| Contract | Gỡ bridge, drop object cũ trong migration riêng; đã có kế hoạch xử lý nếu dependency bị bỏ sót |
| Sau contract | Smoke test, kiểm tra dependency/log/invalid object, backup và cập nhật runbook |

## 12. Những sai lầm thường gặp

### 12.1. Rename/drop ngay trong một lần release

Ứng dụng cũ đang chạy sẽ lỗi ngay khi query cột/tên bảng cũ. Rolling deployment khiến hai version cùng tồn tại; contract quá sớm phá vỡ tính tương thích.

### 12.2. Thêm cột mới rồi chuyển read ngay

Các dòng cũ có thể chưa được backfill và writer cũ tiếp tục chỉ cập nhật cột cũ. V2 sẽ đọc NULL hoặc dữ liệu stale. Phải có bridge, backfill và validation trước khi switch.

### 12.3. Chỉ dual-write trong ứng dụng mới

Nếu vẫn còn V1, V1 không biết cột mới và sẽ không dual-write. Cần một cơ chế bảo đảm mọi writer cũ cũng cập nhật dữ liệu mới, ví dụ trigger bridge hoặc nâng cấp tất cả writer trước khi switch.

### 12.4. Backfill một transaction khổng lồ

Update toàn bảng có thể tạo lượng undo/redo lớn, giữ lock lâu, tăng archive log và làm ảnh hưởng workload. Chia batch, commit theo tiến độ và có khả năng resume.

### 12.5. Dựa vào dependency view để khẳng định không còn consumer

SQL động, code Java, ETL ngoài database và query ad-hoc có thể không xuất hiện trong dependency view. Cần kết hợp kiểm tra source, deployment inventory, monitoring và xác nhận owner.

### 12.6. Coi DDL như transaction có thể rollback

Oracle DDL có implicit commit. Phải thiết kế migration ngược hoặc giữ cấu trúc cũ trong giai đoạn an toàn; `ROLLBACK` không hoàn tác `DROP COLUMN` đã thành công.

### 12.7. Không có khoảng quan sát trước contract

Job chạy hàng tuần có thể chưa xuất hiện trong ngày triển khai. Chờ đủ chu kỳ workload và xác nhận không có truy cập cột cũ trước khi xóa.

## 13. Nguyên tắc cần ghi nhớ

- Expand-and-contract chia schema change thành bước mở rộng tương thích, chuyển dữ liệu/ứng dụng và bước thu hẹp cuối cùng.
- Schema expand phải cho phép phiên bản cũ và mới cùng chạy trong rolling deployment.
- Thêm cột mới nullable trước; backfill và kiểm tra dữ liệu trước khi đặt constraint bắt buộc.
- Khi writer cũ vẫn tồn tại, phải có bridge bảo đảm dữ liệu mới được cập nhật; application dual-write đơn thuần không bao phủ writer cũ.
- Backfill theo batch, idempotent, có thể resume và theo dõi redo/undo/lock.
- Tách read switch khỏi write switch để dễ quan sát và rollback trước contract.
- Không drop cột/bảng cũ cho tới khi mọi service, job, report, trigger, stored procedure và integration đã chuyển.
- Oracle DDL có implicit commit; rollback ứng dụng và rollback DDL là hai việc khác nhau.
- Kiểm tra DDL lock, online operation, index, statistics, invalid object và replication lag theo release/edition.
- Contract là bước cam kết cuối; sau đó rollback về binary cũ có thể không còn khả thi nếu schema cũ đã bị xóa.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html)
- [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html)
- [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html)
- [Oracle Database 19c Development Guide — Edition-Based Redefinition](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/editions.html)
- [Oracle Database 19c Reference — DBA_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html)

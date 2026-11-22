# Backfill dữ liệu theo lô, kiểm soát redo/undo và khả năng chạy lại

Backfill là quá trình điền hoặc chuyển đổi dữ liệu đã tồn tại sau khi schema hoặc logic ứng dụng thay đổi. Ví dụ, hệ thống thêm cột `NORMALIZED_EMAIL` để lưu email đã chuẩn hóa, thêm `CUSTOMER_TIER` được tính từ dữ liệu cũ, hoặc chuyển một cột sang định dạng mới. Với bảng lớn, chạy một câu `UPDATE` duy nhất có thể tạo transaction rất dài, giữ row lock lâu, tiêu thụ nhiều undo, sinh lượng redo lớn và gây áp lực lên archive log hoặc Data Guard.

Giải pháp thường dùng là chia công việc thành các lô nhỏ (batches/chunks), commit theo ranh giới có kiểm soát, lưu checkpoint và thiết kế thao tác có thể chạy lại an toàn. Mục tiêu không chỉ là hoàn thành backfill nhanh mà còn phải biết công việc đã xử lý tới đâu, có thể tiếp tục sau lỗi, không ghi đè dữ liệu mới và không làm hệ thống đang phục vụ người dùng suy giảm ngoài ngưỡng cho phép.

## 1. Backfill trong một thay đổi schema

### 1.1. Backfill là gì?

Backfill cập nhật các bản ghi hiện có để đáp ứng cấu trúc hoặc quy tắc dữ liệu mới. Các trường hợp thường gặp:

- Thêm cột mới và tính giá trị cho dữ liệu cũ.
- Chuẩn hóa dữ liệu như email, mã vùng, trạng thái hoặc đơn vị đo.
- Chuyển dữ liệu từ cột cũ sang cột mới.
- Điền foreign key hoặc mã tham chiếu mới.
- Gán giá trị mặc định theo quy tắc nghiệp vụ mới.
- Chuyển dữ liệu sang partition hoặc bảng đích trong quá trình nâng cấp.
- Tạo dữ liệu dẫn xuất phục vụ tìm kiếm, báo cáo hoặc phân loại.

Backfill khác với migration DDL. DDL thay đổi cấu trúc như `ALTER TABLE ADD COLUMN`; backfill thay đổi dữ liệu từng hàng. Hai phần thường cần phối hợp trong một kế hoạch expand-and-contract để ứng dụng cũ và mới có thể cùng hoạt động trong thời gian chuyển tiếp.

### 1.2. Mô hình expand-and-contract

Một cách triển khai online an toàn thường gồm:

1. **Expand:** thêm cột/bảng mới ở trạng thái tương thích, thường cho phép `NULL` ban đầu.
2. **Deploy tương thích:** ứng dụng mới bắt đầu ghi cả cột cũ và cột mới, hoặc đọc cột mới rồi fallback sang cột cũ.
3. **Backfill:** điền dữ liệu cũ theo lô trong khi ứng dụng vẫn hoạt động.
4. **Validate:** kiểm tra số dòng, giá trị và các quy tắc nghiệp vụ.
5. **Switch:** chuyển ứng dụng sang dùng cột mới làm nguồn chính.
6. **Contract:** sau khi hết thời gian tương thích, loại bỏ đường đọc/ghi cũ và xóa cột cũ bằng migration riêng.

Không nên thêm cột mới, backfill, xóa cột cũ và deploy code phụ thuộc cột mới trong một thay đổi không có điểm dừng kiểm tra. Tách các bước giúp có thể triển khai dần, phát hiện lỗi và quay lui trước khi dữ liệu cũ bị loại bỏ.

### 1.3. Ví dụ nghiệp vụ

Giả sử bảng `CUSTOMERS` đang có `EMAIL`, và cần thêm `EMAIL_NORMALIZED` để tìm kiếm không phân biệt chữ hoa/chữ thường:

```sql
ALTER TABLE app.customers ADD (
    email_normalized VARCHAR2(320 CHAR)
);
```

Ứng dụng mới sẽ ghi đồng thời `EMAIL` và `EMAIL_NORMALIZED`. Các hàng cũ cần được backfill:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE email_normalized IS NULL;
```

Câu lệnh đơn giản trên có thể phù hợp với bảng nhỏ. Với bảng hàng triệu hoặc hàng trăm triệu dòng, chạy một lần có thể tạo transaction lớn và kéo dài. Bài học này tập trung vào cách chia công việc, kiểm soát tài nguyên và bảo đảm có thể tiếp tục sau gián đoạn.

## 2. Thiết kế phạm vi và điều kiện an toàn

### 2.1. Xác định tập dữ liệu cần backfill

Trước khi chạy, xác định:

- Bảng, partition và cột cần xử lý.
- Số dòng dự kiến và phân bố theo khóa.
- Biểu thức chuyển đổi và các trường hợp `NULL`/giá trị không hợp lệ.
- Khóa chính hoặc ROWID dùng để chia chunk.
- Cách nhận biết một hàng đã hoàn tất.
- Cách xử lý hàng được ứng dụng cập nhật trong lúc backfill.
- Những trigger, index, constraint, audit, materialized view log hoặc CDC phụ thuộc.
- Cửa sổ tải được phép và giới hạn redo/undo/lag.

Đếm sơ bộ số hàng cần xử lý:

```sql
SELECT COUNT(*) AS rows_to_backfill
FROM app.customers
WHERE email_normalized IS NULL;
```

Nếu bảng quá lớn, `COUNT(*)` cũng có thể tốn I/O. Có thể dùng statistics để ước tính ban đầu, nhưng cần ghi rõ đó là ước tính; khi lập kế hoạch chính xác, hãy dùng phương pháp đo phù hợp với bảng và workload.

### 2.2. Điều kiện hoàn tất phải rõ ràng

Không nên dùng `target_column IS NULL` làm dấu hiệu duy nhất nếu giá trị `NULL` là kết quả hợp lệ của phép chuyển đổi. Ví dụ, nếu `PHONE_NORMALIZED` có thể là `NULL` do số điện thoại nguồn không có, backfill sẽ không phân biệt được hàng đã xử lý với hàng chưa xử lý.

Có thể dùng một trong các cách:

- Cột trạng thái như `BACKFILL_DONE = 'Y'`.
- Bảng checkpoint lưu phạm vi khóa đã hoàn thành.
- Bảng work queue chứa khóa và trạng thái từng hàng.
- Version/migration marker gắn với từng bản ghi.
- Quy tắc xác định kết quả mới đã được điền và kiểm tra hợp lệ.

Chọn cách phù hợp với khả năng thay đổi schema, chi phí ghi thêm và yêu cầu truy vết. Không tạo cột marker chỉ để tiện lợi nếu nó làm tăng đáng kể chi phí trên mọi transaction production mà không có kế hoạch loại bỏ.

### 2.3. Không ghi đè thay đổi mới của ứng dụng

Khi backfill chạy đồng thời với ứng dụng, cùng một hàng có thể được cập nhật bởi cả hai. Giả sử backfill đọc giá trị email cũ, tính email chuẩn hóa rồi ghi vào cột mới. Trong lúc đó, người dùng đổi email và ứng dụng ghi giá trị mới. Nếu backfill dùng giá trị đã đọc từ trước, nó có thể ghi đè kết quả mới.

Các cách hạn chế:

- Tính giá trị từ cột nguồn ngay trong câu `UPDATE`, không đọc trước rồi ghi lại giá trị cũ.
- Dùng điều kiện `WHERE target_column IS NULL` hoặc marker chưa hoàn tất để tránh ghi đè giá trị đã được ứng dụng ghi.
- Nếu xử lý qua staging, kèm `ROW_VERSION`/`UPDATED_AT` và chỉ cập nhật khi phiên bản nguồn vẫn khớp.
- Triển khai dual-write trước khi backfill, để mọi ghi mới cập nhật cả hai cột.
- Có bước catch-up cuối cùng hoặc reconciliation trước khi chuyển đọc sang cột mới.

Ví dụ cập nhật có điều kiện:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND email_normalized IS NULL;
```

Điều kiện cuối giúp giữ giá trị đã được ứng dụng ghi trước đó. Điều này chỉ đúng khi `NULL` có nghĩa là chưa xử lý; nếu `NULL` là kết quả hợp lệ, hãy dùng marker riêng.

## 3. Chia công việc thành batch/chunk

### 3.1. Vì sao không UPDATE toàn bảng một lần?

Một transaction cập nhật hàng triệu dòng có thể:

- Giữ row lock trên nhiều hàng trong thời gian dài.
- Sinh lượng undo lớn để hỗ trợ rollback và consistent read.
- Sinh lượng redo lớn và làm archive log tăng nhanh.
- Tăng thời gian rollback nếu job thất bại gần cuối.
- Tăng nguy cơ tranh chấp với giao dịch ứng dụng.
- Làm query dài khác gặp áp lực undo và lỗi `ORA-01555`.
- Tạo tải I/O, CPU và buffer cache kéo dài.
- Làm Data Guard hoặc hệ thống downstream phải apply một lượng redo lớn.

Chia batch tạo ra các transaction nhỏ hơn. Mỗi batch có thể commit độc lập; nếu batch sau lỗi, các batch trước vẫn đã hoàn tất và có checkpoint để tiếp tục.

### 3.2. Chọn kích thước batch

Không có một kích thước batch đúng cho mọi bảng. Kích thước phù hợp phụ thuộc:

- Kích thước row và số cột được cập nhật.
- Số index phải duy trì.
- Trigger, constraint, audit và cascade.
- Mức độ cạnh tranh với ứng dụng.
- Tốc độ redo/undo và năng lực archive/storage.
- Latency commit và thời gian khóa hàng.
- Mức độ song song được phép.

Có thể bắt đầu thử với vài trăm hoặc vài nghìn hàng mỗi batch, sau đó đo thời gian, redo, undo, lock và độ trễ ứng dụng. Với row nhỏ, ít index, batch có thể lớn hơn; với row lớn, nhiều index/LOB hoặc bảng nóng, batch nhỏ hơn có thể an toàn hơn.

Mục tiêu là giữ thời gian mỗi transaction và lượng tài nguyên trong ngưỡng có thể kiểm soát. Đừng chọn batch chỉ theo số dòng; 5.000 hàng có nhiều LOB và index có thể nặng hơn 50.000 hàng nhỏ.

### 3.3. Chia theo primary key range

Nếu bảng có khóa chính số hoặc khóa có thứ tự ổn định, có thể chia thành các khoảng:

```text
Batch 1: customer_id > 0      AND customer_id <= 10000
Batch 2: customer_id > 10000  AND customer_id <= 20000
Batch 3: customer_id > 20000  AND customer_id <= 30000
...
```

Ví dụ SQL:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N';
```

Primary key range dễ ghi checkpoint và dễ tiếp tục sau lỗi. Tuy nhiên, nếu khóa bị phân bố lệch hoặc có khoảng trống lớn, số hàng mỗi batch có thể không đều. Hãy đo row count theo range và chia lại nếu cần.

### 3.4. Chia theo ROWID

ROWID có thể giúp chia bảng thành các vùng vật lý và thuận tiện cho xử lý song song. Oracle cung cấp `DBMS_PARALLEL_EXECUTE` để tạo chunk theo ROWID. Cần nhớ ROWID là địa chỉ vật lý của hàng trong segment; nó có thể thay đổi sau thao tác di chuyển hàng, move/redefinition hoặc một số thay đổi tổ chức bảng. Không dùng ROWID làm định danh nghiệp vụ lâu dài hoặc checkpoint xuyên qua các thao tác có thể làm thay đổi ROWID.

ROWID phù hợp khi tạo chunk cho một lần chạy có kiểm soát và bảng không bị tổ chức lại trong lúc đó. Nếu cần checkpoint lâu dài qua nhiều đợt triển khai, primary key hoặc một work queue bền vững thường dễ quản lý hơn.

### 3.5. Chia theo partition

Với bảng partition, có thể backfill từng partition hoặc subpartition:

- Bắt đầu từ partition cũ ít được truy cập.
- Xử lý partition theo tháng/quý hoặc phạm vi ngày.
- Đo tải và xác nhận từng partition trước khi sang partition tiếp theo.
- Theo dõi global index và local index trong suốt quá trình.

Partition pruning có thể giảm phạm vi đọc/ghi nếu điều kiện sử dụng partition key. Tuy nhiên, cập nhật partition key có thể làm hàng chuyển partition hoặc cần `ENABLE ROW MOVEMENT` tùy trường hợp; hãy đánh giá kỹ trước khi chạy.

## 4. Checkpoint và khả năng chạy lại

### 4.1. Checkpoint là gì?

Checkpoint ghi nhận tiến độ đã commit của công việc. Nếu tiến trình bị dừng, ứng dụng restart hoặc database session mất kết nối, worker đọc checkpoint và tiếp tục từ phần chưa hoàn tất.

Một bảng điều khiển đơn giản:

```sql
CREATE TABLE app.backfill_control (
    task_name       VARCHAR2(100) PRIMARY KEY,
    last_completed_id NUMBER,
    high_water_id   NUMBER,
    status          VARCHAR2(20) NOT NULL,
    updated_at      TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

Ví dụ một dòng:

```sql
INSERT INTO app.backfill_control (
    task_name, last_completed_id, high_water_id, status, updated_at
)
VALUES (
    'CUSTOMER_EMAIL_V1', 0, 9000000, 'RUNNING', SYSTIMESTAMP
);
COMMIT;
```

`high_water_id` cố định phạm vi dữ liệu của đợt backfill. Những hàng mới phát sinh sau thời điểm xác định phạm vi phải được xử lý bằng dual-write, CDC hoặc một vòng catch-up riêng. Không mặc định rằng mọi ID nhỏ hơn high-water đều đã commit và nhìn thấy tại cùng một snapshot nếu hệ thống còn transaction đang mở.

### 4.2. Cập nhật dữ liệu và checkpoint trong cùng transaction

Với worker tuần tự, nguyên tắc quan trọng là cập nhật dữ liệu của batch và tiến độ checkpoint trong cùng transaction:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email)),
    backfill_done = 'Y'
WHERE customer_id > :last_id
  AND customer_id <= :batch_end
  AND backfill_done = 'N';

UPDATE app.backfill_control
SET last_completed_id = :batch_end,
    updated_at = SYSTIMESTAMP
WHERE task_name = 'CUSTOMER_EMAIL_V1';

COMMIT;
```

Nếu transaction rollback, cả dữ liệu batch và checkpoint đều rollback. Nếu commit thành công, cả hai cùng bền vững. Tránh commit dữ liệu trước rồi mới cập nhật checkpoint trong transaction khác; nếu tiến trình dừng giữa hai bước, trạng thái có thể không rõ và phải chạy lại batch.

Nếu nhiều worker chạy đồng thời, một `last_completed_id` duy nhất không đủ để đại diện tiến độ từng worker. Dùng bảng chunk/work queue với trạng thái riêng cho mỗi chunk, hoặc dùng `DBMS_PARALLEL_EXECUTE` để theo dõi trạng thái chunk.

### 4.3. Xác định batch tiếp theo

Một cách chọn upper bound theo N khóa tiếp theo trong Oracle:

```sql
SELECT MAX(customer_id) AS batch_end
FROM (
    SELECT customer_id
    FROM app.customers
    WHERE customer_id > :last_id
      AND customer_id <= :high_water_id
    ORDER BY customer_id
)
WHERE ROWNUM <= :batch_size;
```

Kết quả `batch_end` là khóa lớn nhất trong tối đa N khóa tiếp theo. Sau đó worker xử lý khoảng `(last_id, batch_end]`. Nếu không còn hàng, `batch_end` là `NULL` và công việc đã hết phạm vi.

Truy vấn cần index phù hợp trên khóa chia chunk. Với bảng rất lớn, tránh dùng `OFFSET` tăng dần vì database có thể phải bỏ qua ngày càng nhiều dòng. Range theo khóa hoặc chunk metadata thường dễ mở rộng hơn.

### 4.4. Idempotency: chạy lại không gây sai dữ liệu

Một backfill idempotent có thể chạy lại trên cùng tập dữ liệu mà không làm sai kết quả. Ví dụ:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email))
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N';
```

Khi `backfill_done` đã là `Y`, chạy lại range sẽ bỏ qua hàng đã xử lý. Nhưng idempotency không chỉ là thêm điều kiện `IS NULL` hoặc marker. Cần xem:

- Biểu thức chuyển đổi có xác định và cho cùng kết quả với cùng input không?
- Input có thể đã thay đổi kể từ lần chạy trước không?
- Có trigger hoặc side effect bị chạy lại không?
- Có sequence được tăng hoặc gửi message/email trong transaction không?
- Batch có thể commit một phần hay không?
- Việc retry có thể tạo bản ghi trùng trong bảng phụ không?

Nếu backfill ghi sang bảng khác, dùng unique key/merge hoặc event ID để chống insert trùng. Nếu gọi dịch vụ ngoài database, cần outbox/idempotency key và không giả định rollback Oracle sẽ hoàn tác side effect bên ngoài.

### 4.5. Checkpoint theo chunk thay vì theo một con trỏ duy nhất

Với xử lý song song, bảng chunk có thể lưu:

| Cột | Mục đích |
|---|---|
| `TASK_NAME` | Định danh lần migration. |
| `CHUNK_ID` | Định danh chunk. |
| `LOW_KEY`, `HIGH_KEY` | Phạm vi dữ liệu của chunk. |
| `STATUS` | PENDING, RUNNING, DONE hoặc FAILED theo quy ước ứng dụng. |
| `ATTEMPT_COUNT` | Số lần thử. |
| `STARTED_AT`, `COMPLETED_AT` | Thời gian thực thi. |
| `ROWS_UPDATED` | Số hàng được cập nhật. |
| `ERROR_CODE`, `ERROR_MESSAGE` | Thông tin lỗi đã loại bỏ dữ liệu nhạy cảm. |

Worker claim một chunk, xử lý và đánh dấu hoàn tất. Nếu worker chết, lease hoặc timeout cho phép chunk được claim lại. Cần tránh hai worker cùng xử lý một chunk nếu thao tác không idempotent.

## 5. Ví dụ PL/SQL backfill theo lô

### 5.1. Mẫu worker tuần tự

Ví dụ dưới đây giả định:

- `CUSTOMER_ID` là khóa duy nhất và ổn định.
- `BACKFILL_DONE = 'N'` biểu thị chưa xử lý.
- Ứng dụng mới đã ghi `EMAIL_NORMALIZED` và đặt marker phù hợp cho hàng mới.
- `HIGH_WATER_ID` đã được ghi nhận trước khi chạy.

```sql
DECLARE
    l_last_id       NUMBER;
    l_high_water_id NUMBER;
    l_batch_end     NUMBER;
    l_batch_size    PLS_INTEGER := 2000;
    l_rows          PLS_INTEGER;
BEGIN
    SELECT last_completed_id, high_water_id
    INTO l_last_id, l_high_water_id
    FROM app.backfill_control
    WHERE task_name = 'CUSTOMER_EMAIL_V1'
    FOR UPDATE;

    LOOP
        SELECT MAX(customer_id)
        INTO l_batch_end
        FROM (
            SELECT customer_id
            FROM app.customers
            WHERE customer_id > l_last_id
              AND customer_id <= l_high_water_id
            ORDER BY customer_id
        )
        WHERE ROWNUM <= l_batch_size;

        EXIT WHEN l_batch_end IS NULL;

        UPDATE app.customers
        SET email_normalized = LOWER(TRIM(email)),
            backfill_done = 'Y'
        WHERE customer_id > l_last_id
          AND customer_id <= l_batch_end
          AND backfill_done = 'N';

        l_rows := SQL%ROWCOUNT;

        UPDATE app.backfill_control
        SET last_completed_id = l_batch_end,
            updated_at = SYSTIMESTAMP
        WHERE task_name = 'CUSTOMER_EMAIL_V1';

        COMMIT;

        DBMS_OUTPUT.PUT_LINE(
            'Completed through customer_id=' || l_batch_end ||
            ', rows updated=' || l_rows
        );

        l_last_id := l_batch_end;
    END LOOP;

    UPDATE app.backfill_control
    SET status = 'DONE', updated_at = SYSTIMESTAMP
    WHERE task_name = 'CUSTOMER_EMAIL_V1';
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Đây là skeleton để minh họa transaction/checkpoint; cần điều chỉnh tên cột, kiểu dữ liệu, batch size, logging và cách claim task theo hệ thống thật. `FOR UPDATE` giữ khóa dòng control trong suốt vòng lặp nên mẫu này chỉ phù hợp một worker điều khiển. Nếu nhiều worker, không dùng chung một dòng checkpoint theo cách này.

### 5.2. Giới hạn của high-water mark

`HIGH_WATER_ID` giới hạn tập khóa dự kiến của đợt backfill, nhưng không tự tạo snapshot nhất quán. Nếu một transaction đã lấy ID thấp hơn high-water nhưng chỉ commit sau khi worker đi qua range đó, hàng có thể bị bỏ sót. Sequence Oracle không bảo đảm thứ tự commit theo thứ tự ID.

Để bảo đảm không bỏ sót:

- Tạo baseline bằng snapshot/SCN phù hợp nếu yêu cầu một tập dữ liệu nhất quán.
- Hoặc phối hợp write freeze ngắn khi chụp high-water và xử lý transaction đang mở.
- Hoặc dùng CDC/change log để thu các thay đổi phát sinh trong khi backfill.
- Chạy catch-up/reconciliation cuối cùng trước khi chuyển ứng dụng sang dữ liệu mới.

Nếu backfill chỉ là cột dẫn xuất và ứng dụng dual-write mọi thay đổi mới, hãy xác nhận dual-write đã triển khai trên mọi writer: API, batch, integration, trigger và công cụ quản trị. Một writer bị bỏ sót có thể tạo dữ liệu chưa backfill sau khi job kết thúc.

## 6. Dùng DBMS_PARALLEL_EXECUTE

### 6.1. Khi nào nên dùng?

Oracle cung cấp `DBMS_PARALLEL_EXECUTE` để chia một tác vụ DML thành nhiều chunk và chạy các chunk bằng Scheduler worker. Package hỗ trợ tạo chunk theo ROWID hoặc theo khoảng giá trị cột số, theo dõi trạng thái và tiếp tục các chunk lỗi.

Nó phù hợp khi:

- Bảng đủ lớn để hưởng lợi từ nhiều worker.
- Phạm vi có thể chia độc lập.
- Câu DML có thể chạy an toàn trên từng chunk.
- DBA có quyền và tài nguyên Scheduler cần thiết.
- Có thể giới hạn parallel level để không gây quá tải hệ thống.

Không nên bật nhiều worker chỉ để rút ngắn thời gian nếu bảng nóng, storage đã bão hòa hoặc redo/archive đang là bottleneck. Song song hóa có thể làm tổng tải tăng mạnh và khiến ứng dụng production chậm hơn.

### 6.2. Tạo task và chunk theo ROWID

Ví dụ minh họa tạo task, chia bảng `APP.CUSTOMERS` thành chunk và chạy update:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.CREATE_TASK(
        task_name => 'CUSTOMER_EMAIL_BACKFILL'
    );

    DBMS_PARALLEL_EXECUTE.CREATE_CHUNKS_BY_ROWID(
        task_name   => 'CUSTOMER_EMAIL_BACKFILL',
        table_owner => 'APP',
        table_name  => 'CUSTOMERS',
        by_row      => TRUE,
        chunk_size  => 5000
    );

    DBMS_PARALLEL_EXECUTE.RUN_TASK(
        task_name      => 'CUSTOMER_EMAIL_BACKFILL',
        sql_stmt       => q'[
            UPDATE app.customers
            SET email_normalized = LOWER(TRIM(email)),
                backfill_done = 'Y'
            WHERE ROWID BETWEEN :start_id AND :end_id
              AND backfill_done = 'N'
        ]',
        language_flag  => DBMS_SQL.NATIVE,
        parallel_level => 4
    );
END;
/
```

`by_row => TRUE` yêu cầu chunk theo số hàng xấp xỉ; `chunk_size` là mục tiêu số hàng cho mỗi chunk. `parallel_level` giới hạn số worker chạy đồng thời theo cấu hình. Ví dụ dùng ROWID cho một lần backfill; nếu bảng có thể được move/reorganize trong thời gian task chạy, cần dừng thay đổi cấu trúc hoặc chọn chiến lược chunk ổn định hơn.

`DBMS_PARALLEL_EXECUTE` quản lý tiến độ chunk và commit theo từng chunk khi chạy task. Vì vậy, một số chunk có thể đã commit trong khi chunk khác thất bại. Câu SQL nên idempotent và có điều kiện chỉ xử lý hàng chưa hoàn tất để có thể resume an toàn.

### 6.3. Chia theo cột số

Nếu bảng có khóa số ổn định và muốn chunk theo key range, package hỗ trợ `CREATE_CHUNKS_BY_NUMBER_COL`. Cách này dễ gắn với checkpoint nghiệp vụ và ít phụ thuộc ROWID hơn. Chọn cột có phân bố phù hợp, thường là primary key hoặc một cột số duy nhất/được index.

Trước khi dùng, xác nhận chữ ký package theo phiên bản Oracle và quyền thực thi. Nếu key có khoảng trống hoặc skew, số hàng trong từng range có thể khác nhau; cần chọn chunk size/range dựa trên dữ liệu thực tế.

### 6.4. Theo dõi chunk và resume

Có thể xem task và chunk qua các view tương ứng:

```sql
SELECT task_name, status, table_owner, table_name, chunk_type
FROM user_parallel_execute_tasks
WHERE task_name = 'CUSTOMER_EMAIL_BACKFILL';
```

```sql
SELECT status, COUNT(*) AS chunk_count
FROM user_parallel_execute_chunks
WHERE task_name = 'CUSTOMER_EMAIL_BACKFILL'
GROUP BY status
ORDER BY status;
```

Nếu task có chunk lỗi, xem trạng thái và thông tin lỗi của từng chunk rồi sửa nguyên nhân trước khi tiếp tục. Package có thủ tục `RESUME_TASK` để chạy lại phần chưa hoàn tất:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.RESUME_TASK(
        task_name      => 'CUSTOMER_EMAIL_BACKFILL',
        parallel_level => 2
    );
END;
/
```

Khi task đã hoàn tất, xác nhận không còn chunk lỗi và kiểm tra dữ liệu. Sau khi lưu metadata cần thiết cho audit, có thể xóa task:

```sql
BEGIN
    DBMS_PARALLEL_EXECUTE.DROP_TASK(
        task_name => 'CUSTOMER_EMAIL_BACKFILL'
    );
END;
/
```

Tên view, cột trạng thái, quyền và chữ ký package cần xác nhận theo phiên bản. Không drop task khi vẫn cần resume hoặc điều tra lỗi.

### 6.5. Quyền và vận hành

`DBMS_PARALLEL_EXECUTE` sử dụng Scheduler và các quyền liên quan. Cần cấp quyền tối thiểu theo tài liệu Oracle, chẳng hạn quyền thực thi package và quyền tạo/chạy job phù hợp. Không cấp `DBA` chỉ để làm cho task chạy được.

Theo dõi cả số worker, session, CPU, I/O, undo, redo, archive destination và tải ứng dụng. Giới hạn parallel level ở mức có thể kiểm soát; có thể bắt đầu bằng 2–4 worker trong môi trường test rồi đo trước khi nâng.

## 7. Undo: vai trò và rủi ro khi backfill

### 7.1. Undo dùng để làm gì?

Oracle tạo undo để lưu thông tin cần thiết cho rollback và read consistency. Khi một transaction cập nhật row, Oracle giữ thông tin trước thay đổi trong undo segment. Một truy vấn khác có thể dùng undo để đọc phiên bản dữ liệu phù hợp với SCN của câu truy vấn.

Backfill update nhiều hàng tạo ra lượng undo đáng kể. Transaction càng lớn, lượng undo cần giữ để rollback càng lớn và thời gian khóa hàng càng dài. Commit theo batch giúp kết thúc transaction thường xuyên hơn, cho phép Oracle tái sử dụng undo khi không còn cần cho query/transaction khác theo quy tắc retention.

Commit không xóa ngay mọi undo block. Undo vẫn có thể cần cho consistent read, flashback và các mục đích khác cho tới khi đủ điều kiện tái sử dụng.

### 7.2. Undo retention và ORA-01555

`UNDO_RETENTION` đặt mục tiêu thời gian giữ undo, nhưng trong nhiều cấu hình nó không phải cam kết tuyệt đối nếu undo tablespace thiếu dung lượng. Một query chạy lâu có thể gặp `ORA-01555: snapshot too old` nếu undo cần cho consistent read đã bị ghi đè.

Các yếu tố ảnh hưởng:

- Tốc độ sinh undo của toàn hệ thống.
- Dung lượng undo tablespace và autoextend.
- Thời gian chạy query dài.
- Tần suất commit và workload đồng thời.
- `UNDO_RETENTION` và tùy chọn `RETENTION GUARANTEE`.
- Undo generation tăng đột biến trong thời gian backfill.

Không tăng `UNDO_RETENTION` một cách máy móc. Nếu không có đủ dung lượng, yêu cầu giữ lâu hơn có thể gây áp lực không gian và lỗi cấp phát. `RETENTION GUARANTEE` có thể bảo vệ undo khỏi bị ghi đè trong một số điều kiện nhưng cũng có thể khiến DML mới lỗi khi tablespace đầy. Chỉ bật sau khi DBA đánh giá dung lượng và tác động.

### 7.3. Theo dõi V$UNDOSTAT

`V$UNDOSTAT` cung cấp thống kê undo theo các khoảng thời gian, thường là bucket 10 phút:

```sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt,
       tuned_undoretention
FROM v$undostat
ORDER BY begin_time DESC;
```

Các cột hữu ích:

- `UNDOBLKS`: số undo block được sử dụng trong khoảng.
- `TXNCOUNT`: số transaction trong khoảng.
- `MAXQUERYLEN`: thời lượng query dài nhất được ghi nhận.
- `SSOLDERRCNT`: số lỗi snapshot too old trong khoảng.
- `NOSPACEERRCNT`: số lỗi do không đủ không gian undo.
- `TUNED_UNDORETENTION`: thời gian retention được Oracle điều chỉnh theo điều kiện thực tế.

Theo dõi xu hướng trước, trong và sau backfill. Nếu `UNDOBLKS` tăng mạnh, `NOSPACEERRCNT` khác 0 hoặc `SSOLDERRCNT` tăng, cần giảm tải, điều chỉnh batch hoặc xử lý dung lượng theo quyết định DBA.

### 7.4. Ước tính nhu cầu undo

Có thể ước tính sơ bộ dựa trên tốc độ sinh undo và thời gian cần giữ:

```text
Undo space gần đúng ≈ undo generation rate × retention interval
```

Đây chỉ là ước tính ban đầu; cần cộng overhead, concurrent workload, transaction dài, extent allocation và dung lượng an toàn. Dùng số liệu `V$UNDOSTAT` trong giờ cao điểm để tính gần thực tế hơn, không chỉ đo khi hệ thống nhàn rỗi.

## 8. Redo: kiểm soát lượng thay đổi được ghi log

### 8.1. DML backfill tạo redo

Oracle dùng redo để bảo đảm khả năng phục hồi sau sự cố. Một câu `UPDATE` thông thường tạo redo cho thay đổi dữ liệu và những thay đổi liên quan, bao gồm cả undo block cần thiết. Vì vậy, backfill update nhiều hàng có thể tạo redo lớn ngay cả khi không có người dùng khác ghi dữ liệu.

Redo không phải tùy chọn có thể tắt cho một câu `UPDATE` thông thường bằng cách đặt `NOLOGGING`. `NOLOGGING` chủ yếu ảnh hưởng một số thao tác direct-path hoặc bulk operation được hỗ trợ; nó không biến conventional DML thành thao tác không sinh redo.

### 8.2. Tác động tới online redo và archive log

Redo được ghi vào online redo log. Khi log switch xảy ra, ở chế độ `ARCHIVELOG`, Oracle archive log group cũ. Backfill sinh redo nhanh có thể làm:

- Log switch dày hơn.
- Archive destination tăng dung lượng nhanh.
- Archive process hoặc network tới standby bị quá tải.
- Data Guard transport/apply lag tăng.
- Storage I/O và backup/archive workload cạnh tranh với ứng dụng.
- Database gặp lỗi nếu archive destination đầy hoặc không thể ghi log.

Do đó, cần dự báo redo rate và kiểm tra dung lượng archive trước khi chạy. Một backfill có thể hoàn thành SQL nhưng làm hệ thống gặp sự cố vì archive destination không còn chỗ.

### 8.3. Theo dõi redo generation

Có thể xem các system statistic:

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'redo writes',
    'redo blocks written'
);
```

Các giá trị trong `V$SYSSTAT` là bộ đếm tích lũy từ lúc instance khởi động. Lấy snapshot trước/sau mỗi khoảng để tính delta và tốc độ redo/giây. Trong môi trường nhiều workload, số liệu này bao gồm toàn database, không chỉ backfill.

Theo dõi log switch:

```sql
SELECT first_time, thread#, sequence#
FROM v$log_history
WHERE first_time >= SYSDATE - 1
ORDER BY first_time DESC;
```

Với RAC, xem theo `THREAD#` vì mỗi redo thread có log riêng. Kiểm tra archive destination:

```sql
SELECT dest_id, status, error, destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE';
```

Và lượng archive log được tạo:

```sql
SELECT TRUNC(completion_time, 'HH24') AS hour_bucket,
       thread#,
       COUNT(*) AS archived_logs,
       SUM(blocks * block_size) AS bytes_archived
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND archived = 'YES'
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY hour_bucket DESC, thread#;
```

Các view có thể cần quyền catalog/dynamic performance view phù hợp. `V$ARCHIVED_LOG` có thể chứa nhiều bản ghi cho cùng sequence do nhiều destination/copy; cần lọc hoặc nhóm theo `DEST_ID`, `RESETLOGS_ID` và trạng thái phù hợp nếu muốn thống kê chính xác cho kiến trúc cụ thể.

### 8.4. NOLOGGING không phải giải pháp chung

`NOLOGGING` có thể giảm redo cho một số thao tác như direct-path insert, CTAS hoặc index build trong điều kiện phù hợp. Nhưng:

- Conventional `UPDATE` vẫn tạo redo.
- `FORCE LOGGING` ở database/tablespace có thể buộc ghi log bất kể thuộc tính `NOLOGGING` của đối tượng.
- Một số thao tác NOLOGGING có thể làm media recovery không tái tạo được block đã thay đổi nếu không có backup phù hợp.
- Data Guard/standby có thể bị ảnh hưởng bởi thao tác không ghi log tùy cấu hình và phiên bản.
- Bản backup cần thiết sau thao tác có thể phải được thực hiện theo hướng dẫn Oracle.

Không đổi tablespace/database sang NOLOGGING chỉ để tăng tốc backfill. Với một đợt cập nhật dữ liệu production, ưu tiên batch sizing, pacing, cửa sổ chạy, index strategy và giám sát redo. Nếu cân nhắc direct-path/NOLOGGING cho một thiết kế bulk load riêng, DBA phải đánh giá khả năng recovery, standby và backup trước.

### 8.5. Index và redo/undo

Khi cập nhật cột có index, Oracle còn phải duy trì index. Điều này có thể làm tăng redo, undo, logical I/O và thời gian DML. Trước backfill, xác định:

- Cột đích có index hay không.
- Có function-based index hoặc index composite phụ thuộc cột đó không.
- Có trigger/audit ghi thêm dữ liệu không.
- Có materialized view log hoặc replication capture phụ thuộc không.
- Có cần tạo index sau khi backfill thay vì duy trì index từng row hay không.

Không tự drop index/constraint trên production chỉ để tăng tốc. Nếu thay đổi cấu trúc index, phải đánh giá tác động tới query đang chạy, tính toàn vẹn, plan và thời gian rebuild; cần phê duyệt và phương án phục hồi.

## 9. Điều tiết tải và chọn mức song song

### 9.1. Pacing giữa các batch

Nếu batch chạy quá nhanh và tạo áp lực redo/undo, có thể:

- Giảm batch size.
- Giảm parallel level hoặc chuyển về một worker.
- Thêm khoảng nghỉ có kiểm soát giữa các batch.
- Chỉ chạy trong cửa sổ tải thấp.
- Tạm dừng khi CPU, I/O, archive lag hoặc latency ứng dụng vượt ngưỡng.
- Ưu tiên partition hoặc nhóm dữ liệu ít nóng.

Không thêm `DBMS_SESSION.SLEEP` vào mọi worker mà không đo. Khoảng nghỉ chỉ là công cụ điều tiết đơn giản; tốt hơn là dùng metrics và ngưỡng rõ ràng để điều chỉnh.

### 9.2. Chạy nhiều worker

Song song có thể tăng throughput nhưng cũng tăng:

- Concurrent row lock và block contention.
- Undo/redo generation rate.
- CPU và I/O.
- Số session và process.
- Archive log/standby apply pressure.
- Khả năng gặp deadlock nếu các chunk cập nhật nhiều bảng hoặc cùng khóa theo thứ tự khác nhau.

Chỉ tăng parallelism sau khi một worker chạy ổn định và đã đo được bottleneck. Chọn chunk không giao nhau; nếu các chunk có thể đụng cùng bảng phụ hoặc cùng khóa, cần thiết kế thứ tự và xử lý conflict.

### 9.3. SKIP LOCKED cho work queue

Nếu dùng bảng queue để nhiều worker claim các hàng cần xử lý, `FOR UPDATE SKIP LOCKED` có thể giúp worker lấy những task chưa bị worker khác khóa:

```sql
SELECT task_id
FROM app.backfill_queue
WHERE status = 'PENDING'
ORDER BY task_id
FOR UPDATE SKIP LOCKED;
```

Trong code thực tế, giới hạn số hàng mỗi lần claim bằng cú pháp phù hợp phiên bản Oracle, đánh dấu `RUNNING` và commit việc claim theo một transaction rõ ràng. `SKIP LOCKED` phù hợp cho queue; nó không tự bảo đảm một câu UPDATE tùy ý không bị tranh chấp hoặc không bỏ sót hàng. Cần lease/timeout để giải phóng task nếu worker chết sau khi claim.

### 9.4. Theo dõi session và transaction dài

Có thể tìm transaction đang mở và undo sử dụng:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
```

`USED_UBLK` và `USED_UREC` cho biết mức sử dụng undo của transaction. Dùng `MODULE`/`ACTION` để nhận diện session backfill, có thể thiết lập từ ứng dụng hoặc `DBMS_APPLICATION_INFO`.

Theo dõi thêm `V$SESSION_LONGOPS`, `V$SESSION`, wait event, blocking session và metrics từ hệ thống giám sát. Không kill session chỉ vì transaction chạy lâu; rollback transaction lớn cũng có thể tốn thời gian và tạo tác động đáng kể.

## 10. DML error logging và xử lý hàng lỗi

### 10.1. Khi nào cần error logging?

Trong một số backfill, một vài hàng có dữ liệu không hợp lệ có thể gây lỗi chuyển đổi hoặc constraint. Nếu yêu cầu cho phép xử lý các hàng hợp lệ và ghi lại hàng lỗi để sửa sau, Oracle DML error logging có thể hữu ích.

Tạo error table:

```sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'CUSTOMERS',
        err_log_table_name => 'ERR$_CUSTOMERS'
    );
END;
/
```

Sau đó thêm `LOG ERRORS` vào DML:

```sql
UPDATE app.customers
SET email_normalized = LOWER(TRIM(email)),
    backfill_done = 'Y'
WHERE customer_id > :low_id
  AND customer_id <= :high_id
  AND backfill_done = 'N'
LOG ERRORS INTO app.err$_customers ('EMAIL_BACKFILL_V1')
REJECT LIMIT UNLIMITED;
```

Ví dụ này cần điều chỉnh schema/owner và error table theo cách tạo thực tế. `LOG ERRORS` cho phép ghi nhận một số lỗi theo từng hàng thay vì hủy toàn bộ DML ngay khi gặp lỗi có thể log. Không phải mọi loại lỗi đều được error logging xử lý; lỗi statement-level hoặc các trường hợp không hỗ trợ vẫn có thể làm câu lệnh thất bại.

### 10.2. Không bỏ qua lỗi mà không có quy trình

Sau mỗi batch, phải thống kê error table theo tag, xác định nguyên nhân và quyết định:

- Sửa dữ liệu nguồn rồi chạy lại hàng lỗi.
- Đưa hàng vào quarantine để chủ dữ liệu xử lý.
- Chấp nhận bỏ qua theo quy tắc nghiệp vụ được phê duyệt.
- Dừng migration nếu tỷ lệ lỗi vượt ngưỡng.

Không đặt `REJECT LIMIT UNLIMITED` rồi coi job thành công là tất cả dữ liệu đã backfill. Hãy đối chiếu số hàng lỗi, số hàng cập nhật và số hàng còn pending.

## 11. Kiểm tra tiến độ và tác động trong khi chạy

### 11.1. Metrics ở cấp backfill

Ghi nhận mỗi batch:

- Task/chunk ID và khoảng khóa.
- Thời gian bắt đầu, kết thúc và thời lượng.
- Số hàng dự kiến, số hàng thực sự cập nhật và số hàng bỏ qua.
- Số lỗi và mã lỗi.
- Checkpoint đã commit.
- Batch size và parallel level.
- Redo/undo ước tính trong khoảng đo.

Không ghi nội dung nhạy cảm của từng row vào log. Có thể dùng `DBMS_APPLICATION_INFO.SET_MODULE` và `SET_ACTION` để nhận diện phiên:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'DATA_BACKFILL',
        action_name => 'CUSTOMER_EMAIL_V1'
    );
END;
/
```

Điều này giúp DBA liên hệ session với công việc trong `V$SESSION` và các công cụ giám sát.

### 11.2. Ngưỡng tạm dừng

Định nghĩa ngưỡng trước khi chạy, ví dụ:

- p95 latency ứng dụng vượt SLA trong một số khoảng liên tiếp.
- CPU hoặc storage latency vượt ngưỡng vận hành.
- Undo tablespace gần đầy hoặc `NOSPACEERRCNT` tăng.
- Archive destination thiếu dung lượng.
- Data Guard transport/apply lag vượt ngưỡng.
- Blocking session hoặc deadlock tăng.
- Error rate của backfill vượt mức chấp nhận.

Khi vượt ngưỡng, giảm parallelism hoặc dừng sau batch hiện tại. Tránh dừng giữa transaction nếu không cần thiết. Ghi checkpoint sau mỗi batch để việc tiếp tục rõ ràng.

### 11.3. Đánh giá redo/undo theo khoảng thời gian

Để ước tính redo rate, lấy hai snapshot `V$SYSSTAT` cách nhau một khoảng thời gian và tính chênh lệch `redo size` chia cho số giây. Để theo dõi undo, so sánh các bucket `V$UNDOSTAT`. Để xem archive pressure, theo dõi dung lượng filesystem/ASM, archive log rate và trạng thái destination.

Không quy toàn bộ redo/undo của database cho backfill nếu vẫn có workload ứng dụng. Dùng module/action, session, thời điểm và baseline trước khi chạy để phân tách tác động gần đúng.

## 12. Hoàn tất và xác nhận backfill

### 12.1. Đếm hàng còn pending

Nếu có marker:

```sql
SELECT backfill_done, COUNT(*) AS row_count
FROM app.customers
GROUP BY backfill_done
ORDER BY backfill_done;
```

Hoặc:

```sql
SELECT COUNT(*) AS rows_pending
FROM app.customers
WHERE backfill_done = 'N';
```

Không chỉ dựa vào checkpoint cuối. Một chunk có thể được đánh dấu hoàn tất nhưng có hàng bị bỏ qua do error logging hoặc điều kiện WHERE không khớp. Cần kiểm tra dữ liệu thực tế.

### 12.2. Kiểm tra chất lượng giá trị

Ví dụ kiểm tra email chuẩn hóa:

```sql
SELECT COUNT(*) AS invalid_normalized_values
FROM app.customers
WHERE backfill_done = 'Y'
  AND email IS NOT NULL
  AND email_normalized <> LOWER(TRIM(email));
```

Nếu quy tắc chuyển đổi phức tạp, dùng cùng một hàm/logic chuẩn hóa được định nghĩa thống nhất ở backfill và validation. Kiểm tra cả giá trị `NULL`, chuỗi rỗng, ký tự Unicode và các trường hợp ngoại lệ.

### 12.3. Kiểm tra index, constraint và statistics

Sau backfill:

- Xác nhận index ở trạng thái `VALID`.
- Xác nhận constraint được enable và validate theo yêu cầu.
- Gather statistics cho cột/index mới khi phù hợp với chính sách.
- Kiểm tra execution plan của truy vấn ứng dụng.
- Theo dõi redo/archive và Data Guard lag trở lại bình thường.
- Kiểm tra error table và xử lý mọi hàng lỗi.

Nếu cột mới được dùng trong predicate hoặc join, statistics có thể cần cập nhật để optimizer ước tính selectivity phù hợp. Không gather stats đồng loạt ngay sau backfill mà chưa đánh giá tải và plan.

### 12.4. Loại bỏ cơ chế chuyển tiếp

Chỉ sau khi backfill và validation đạt:

- Chuyển ứng dụng sang đọc cột mới.
- Theo dõi trong khoảng tương thích.
- Dừng dual-write khi mọi phiên bản ứng dụng đã chuyển.
- Thêm `NOT NULL`, constraint hoặc index nếu yêu cầu.
- Xóa marker/work queue và cột cũ trong migration riêng sau khi hết thời gian rollback.

Không xóa checkpoint hoặc error log trước khi lưu bằng chứng cần thiết. Giữ lại lịch sử migration theo chính sách audit.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Undo tablespace tăng nhanh | Batch quá lớn, nhiều worker hoặc workload đồng thời cao. | Giảm batch/parallelism, đo `V$UNDOSTAT`, đánh giá dung lượng. |
| `ORA-30036` | Không thể mở rộng undo segment do thiếu không gian. | Kiểm tra datafile/autoextend, undo usage và giảm tải; DBA xử lý dung lượng. |
| `ORA-01555` | Undo cần cho consistent read đã bị ghi đè. | Kiểm tra query duration, undo generation/retention và dung lượng; điều chỉnh workload. |
| Archive log tăng nhanh | Backfill sinh redo lớn hoặc archive destination chậm/đầy. | Theo dõi redo rate, log switch, archive destination và Data Guard lag; điều tiết batch. |
| `ORA-00257` | Archiver gặp vấn đề, thường liên quan archive destination. | Xử lý dung lượng/trạng thái archive theo runbook DBA trước khi tiếp tục ghi. |
| Ứng dụng bị block | Batch giữ row lock lâu hoặc cập nhật hàng nóng. | Giảm batch, đổi thứ tự/chia phạm vi, chọn cửa sổ thấp tải. |
| Backfill chạy lại ghi đè dữ liệu mới | Không có điều kiện marker/version hoặc biểu thức dùng dữ liệu cũ. | Dùng dual-write, conditional update, version check và catch-up. |
| Dữ liệu bị bỏ sót dù checkpoint đã tới cuối | High-water không bao gồm transaction commit muộn hoặc có writer bị bỏ sót. | Xem lại snapshot/SCN, CDC, write boundary và reconciliation. |
| Batch bị lặp tạo dữ liệu trùng | Thao tác không idempotent hoặc checkpoint không cùng transaction. | Dùng unique key/MERGE/event ID và transaction checkpoint nguyên tử. |
| DBMS_PARALLEL_EXECUTE có chunk lỗi | Dữ liệu đặc biệt, deadlock, quyền hoặc resource. | Xem chunk error, sửa nguyên nhân rồi `RESUME_TASK`; giữ SQL idempotent. |
| Data Guard lag tăng | Redo generation vượt tốc độ transport/apply. | Giảm parallelism, theo dõi standby và kiểm tra băng thông/storage. |

Không tự động tăng `UNDO_RETENTION`, chuyển NOLOGGING hoặc kill session để xử lý các lỗi này. Trước tiên xác định nguyên nhân và tác động tới khả năng phục hồi.

## 14. Runbook backfill mẫu

### Trước khi chạy

1. Xác định mục tiêu dữ liệu, biểu thức chuyển đổi và marker hoàn tất.
2. Kiểm tra khóa chia chunk, index, partition, trigger, constraint và writer hiện tại.
3. Xác nhận ứng dụng đã hỗ trợ dual-write hoặc có cơ chế catch-up.
4. Ghi nhận high-water/snapshot boundary phù hợp.
5. Đo baseline redo/undo, archive rate, Data Guard lag, CPU, I/O và latency ứng dụng.
6. Chọn batch size và parallel level ban đầu từ rehearsal.
7. Chuẩn bị checkpoint, error table, logging và lệnh resume.
8. Xác nhận backup/recovery và người trực DBA trong cửa sổ chạy.

### Trong khi chạy

1. Gắn module/action cho session backfill.
2. Claim một chunk hoặc xác định range tiếp theo.
3. Chạy DML có điều kiện để bỏ qua hàng đã hoàn tất.
4. Ghi số hàng cập nhật và lỗi.
5. Cập nhật checkpoint trong cùng transaction hoặc để framework chunk quản lý commit.
6. Commit theo batch.
7. Theo dõi thời lượng batch, redo/undo, archive, blocking và latency ứng dụng.
8. Giảm tốc hoặc tạm dừng khi vượt ngưỡng.
9. Khi lỗi, giữ checkpoint, phân tích batch lỗi và chỉ resume sau khi xác nhận retry an toàn.

### Sau khi chạy

1. Kiểm tra mọi chunk đã hoàn tất và không còn chunk lỗi chưa xử lý.
2. Đếm hàng pending và error.
3. Đối soát giá trị mới với quy tắc nghiệp vụ.
4. Kiểm tra index, constraint, statistics và execution plan.
5. Xác nhận archive/standby lag và tài nguyên trở lại bình thường.
6. Chuyển ứng dụng sang đọc dữ liệu mới theo kế hoạch.
7. Lưu báo cáo, checkpoint và error log theo chính sách.
8. Chỉ xóa marker/task cũ sau khi hết thời gian cần rollback và được phê duyệt.

## 15. Nguyên tắc cần nhớ

- Backfill bảng lớn nên chia thành transaction nhỏ có thể đo và tiếp tục.
- Chọn chunk theo khóa ổn định, ROWID hoặc partition tùy cấu trúc và thời gian sống của task.
- Checkpoint phải phản ánh dữ liệu đã commit; lý tưởng là cập nhật cùng transaction với batch.
- Thiết kế DML idempotent và bảo vệ thay đổi mới của ứng dụng khỏi bị ghi đè.
- High-water mark không tự tạo snapshot nhất quán; cần xử lý transaction đang mở và dữ liệu mới.
- Conventional `UPDATE` tạo redo và undo; `NOLOGGING` không tắt redo cho UPDATE thông thường.
- Theo dõi `V$UNDOSTAT`, `V$SYSSTAT`, log switch, archive destination và Data Guard lag.
- Commit theo batch để giới hạn transaction, lock và rollback cost; tránh commit từng hàng.
- Tăng parallelism từ từ và đo tác động lên ứng dụng đang chạy.
- Dùng `DBMS_PARALLEL_EXECUTE` khi cần chunk/job tracking; chỉ resume sau khi xác nhận SQL chạy lại an toàn.
- Error logging giúp cô lập một số hàng lỗi nhưng không thay thế reconciliation.
- Chỉ đánh dấu hoàn tất sau khi kiểm tra cả checkpoint, số hàng pending, error và chất lượng dữ liệu.

## Kết luận

Backfill an toàn là sự kết hợp của chunking, transaction boundary, checkpoint, idempotency và giám sát tài nguyên. Chia dữ liệu theo khóa, ROWID hoặc partition giúp giới hạn thời gian khóa và lượng undo trong mỗi transaction; checkpoint được commit cùng dữ liệu giúp tiếp tục sau gián đoạn mà không phải chạy lại toàn bộ. Oracle vẫn tạo redo cho DML thông thường, nên phải theo dõi redo rate, online/archive log, undo usage và Data Guard lag; `NOLOGGING` không phải cách tắt redo cho UPDATE. Với `DBMS_PARALLEL_EXECUTE`, mỗi chunk có trạng thái riêng và có thể resume, nhưng câu DML vẫn phải an toàn khi chạy lại. Cuối cùng, đối soát dữ liệu thực tế và xử lý hàng lỗi mới chứng minh backfill đã hoàn tất đúng yêu cầu.

# Khóa metadata và tác động đến DDL hoặc giao dịch dài

Khi một câu lệnh đọc hoặc ghi dữ liệu đang sử dụng một bảng, hệ quản trị cơ sở dữ liệu cần bảo đảm định nghĩa của bảng không bị thay đổi theo cách làm câu lệnh đó mất nhất quán. Cơ chế khóa metadata (metadata lock, thường viết tắt là **MDL**) bảo vệ phần định nghĩa này. Vì vậy, một giao dịch chỉ đọc dữ liệu cũng có thể khiến câu lệnh thay đổi cấu trúc bảng phải chờ.

Đây là nguyên nhân phổ biến khiến một lệnh `ALTER TABLE` tưởng như đơn giản bị treo lâu, hoặc khiến các truy vấn mới bất ngờ chậm theo sau một lệnh DDL đang chờ khóa. Để hiểu hiện tượng này, cần phân biệt khóa metadata với khóa hàng, biết thời điểm khóa được giữ và biết cách tìm giao dịch đang giữ khóa.

Các ví dụ SQL trong bài tập trung vào **MySQL**, đặc biệt là MySQL dùng InnoDB. MDL là cơ chế ở lớp máy chủ MySQL, còn khóa hàng là cơ chế của storage engine. Những hệ quản trị khác có cơ chế khóa metadata hoặc khóa quan hệ riêng; tên mode, thời hạn giữ khóa và câu lệnh chẩn đoán không thể áp dụng nguyên xi giữa các hệ.

## 1. Metadata là gì và vì sao cần khóa?

Metadata mô tả cấu trúc và cách truy cập đối tượng trong cơ sở dữ liệu. Với một bảng, metadata có thể bao gồm:

- Tên bảng, schema và loại đối tượng.
- Tên, kiểu dữ liệu, thứ tự và thuộc tính của các cột.
- Chỉ mục, khóa chính, khóa ngoại và các ràng buộc.
- Định nghĩa của view, trigger hoặc các đối tượng liên quan.

Khi thực thi `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE`, máy chủ cần diễn giải câu lệnh dựa trên định nghĩa của đối tượng. Nếu một phiên khác đồng thời đổi tên bảng, xóa cột hoặc thay thế định nghĩa bảng, câu lệnh đang chạy có thể tham chiếu đến một cấu trúc không còn tồn tại hoặc không còn giống cấu trúc mà nó đã chuẩn bị để sử dụng.

MDL phối hợp quyền truy cập metadata giữa các phiên. Một phiên lấy khóa phù hợp khi truy cập đối tượng; phiên muốn thay đổi định nghĩa phải lấy mode khóa tương thích với các khóa đang được giữ. Nếu hai yêu cầu không tương thích, một yêu cầu phải đợi.

Khóa metadata không khóa từng bản ghi. Một câu `SELECT` có thể không khóa bất kỳ hàng InnoDB nào theo nghĩa khóa hàng, nhưng vẫn giữ MDL trên bảng. Ngược lại, một giao dịch có thể chờ khóa hàng dù không có tranh chấp metadata. Hai cơ chế giải quyết hai loại xung đột khác nhau.

## 2. MDL được lấy và giải phóng khi nào?

MySQL tự động lấy MDL khi câu lệnh truy cập các đối tượng cần dùng. Ứng dụng thường không cần viết câu lệnh `LOCK METADATA` riêng. Thời gian giữ khóa phụ thuộc vào loại yêu cầu và ranh giới câu lệnh hoặc giao dịch.

### Chế độ autocommit

Với `autocommit=1` và không mở giao dịch tường minh, mỗi câu lệnh thường là một giao dịch riêng. Khi câu lệnh kết thúc và giao dịch tự động commit, MDL gắn với giao dịch đó được giải phóng. Một câu `SELECT` chạy trong vài mili giây vì thế thường chỉ giữ MDL trong khoảng thời gian ngắn.

```sql
SELECT id, status
FROM orders
WHERE id = 42;
-- Câu lệnh kết thúc; giao dịch autocommit kết thúc theo.
```

### Giao dịch tường minh

Khi ứng dụng mở giao dịch bằng `START TRANSACTION` hoặc `BEGIN`, MDL trên bảng đã truy cập có thể được giữ đến khi giao dịch kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Điều này vẫn đúng nếu câu `SELECT` đã trả kết quả và ứng dụng không còn chạy câu SQL nào trên bảng đó.

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 42;

-- Ứng dụng xử lý kết quả, gọi dịch vụ khác hoặc chờ người dùng.
-- Giao dịch vẫn mở nên MDL có thể vẫn được giữ.

COMMIT;
```

Đây là điểm dễ bị bỏ sót khi điều tra sự cố: **kết thúc câu truy vấn không đồng nghĩa với kết thúc giao dịch**. Nếu một giao dịch đọc mở trong nhiều phút rồi để kết nối ở trạng thái nhàn rỗi, nó vẫn có thể giữ MDL và cản trở DDL.

### Các thời hạn giữ khóa

Trong `performance_schema.metadata_locks`, cột `LOCK_DURATION` cho biết thời hạn của yêu cầu khóa. Các giá trị thường gặp gồm:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `STATEMENT` | Khóa gắn với thời gian thực thi câu lệnh. |
| `TRANSACTION` | Khóa được giữ đến khi giao dịch kết thúc. |
| `EXPLICIT` | Khóa có thời hạn do cơ chế khóa tường minh quản lý. |

Đây là thông tin chẩn đoán hữu ích. Khi tìm một MDL đang được giữ lâu, hãy xem cả `LOCK_DURATION`, trạng thái giao dịch và thời điểm bắt đầu giao dịch; đừng chỉ nhìn câu SQL cuối cùng trong process list.

## 3. Các mode khóa và tính tương thích

MDL có nhiều mode nội bộ, chẳng hạn `SHARED_READ`, `SHARED_WRITE`, `SHARED_UPGRADABLE`, `SHARED_NO_WRITE`, `SHARED_NO_READ_WRITE` và `EXCLUSIVE`. Tên mode cụ thể phụ thuộc loại câu lệnh và giai đoạn thực hiện. Không cần ghi nhớ toàn bộ danh sách để xử lý sự cố; điều quan trọng là hiểu hai nhóm hành vi:

- Các thao tác đọc hoặc ghi dữ liệu thường lấy shared metadata lock. Những yêu cầu shared tương thích theo quy tắc của MySQL nên nhiều phiên có thể cùng truy cập bảng.
- Thao tác thay đổi định nghĩa cần mode mạnh hơn; có giai đoạn cần khóa độc quyền (`EXCLUSIVE`). Khóa này xung đột với các MDL đang được giữ trên cùng đối tượng, nên DDL phải chờ các giao dịch liên quan kết thúc.

Ví dụ, `SELECT` và `UPDATE` có thể cùng truy cập một bảng theo các quy tắc khóa dữ liệu của engine. Tuy nhiên, `ALTER TABLE` thay đổi định nghĩa bảng phải phối hợp với các phiên đang sử dụng metadata của bảng đó. Việc không có hàng nào bị khóa không làm mất nhu cầu phối hợp này.

Không nên suy luận rằng mọi DDL giữ khóa độc quyền trong toàn bộ thời gian chạy. Mỗi loại DDL, storage engine, phiên bản MySQL và thuật toán thực hiện có thể dùng mode khác nhau ở các giai đoạn khác nhau. Một số thao tác cho phép DML tiếp tục trong phần lớn thời gian xử lý, nhưng vẫn cần lấy hoặc nâng cấp MDL ở giai đoạn bắt đầu hay hoàn tất.

## 4. Vì sao một giao dịch đọc có thể làm DDL bị chờ?

Xét ba phiên kết nối cùng làm việc với bảng `orders`.

**Phiên A — mở giao dịch và đọc bảng:**

```sql
START TRANSACTION;

SELECT id, status
FROM orders
WHERE id = 42;

-- Không commit hoặc rollback ngay.
```

Phiên A đã đọc xong nhưng giao dịch vẫn mở. MDL trên `orders` có thể tiếp tục được giữ.

**Phiên B — thay đổi cấu trúc bảng:**

```sql
ALTER TABLE orders
ADD COLUMN source VARCHAR(30);
```

Phiên B cần quyền khóa metadata mạnh hơn để thay đổi định nghĩa. Nếu MDL của phiên A chưa được giải phóng, yêu cầu DDL phải chờ.

**Phiên C — chạy một truy vấn mới:**

```sql
SELECT COUNT(*)
FROM orders;
```

Trong lúc yêu cầu khóa độc quyền của phiên B đang chờ, yêu cầu mới của phiên C cũng có thể bị xếp hàng phía sau yêu cầu DDL, tùy mode khóa và trạng thái hàng đợi. Điều này giúp tránh việc các yêu cầu shared mới liên tục vượt lên khiến DDL bị đói khóa. Kết quả là truy vấn C có thể chờ dù bản thân nó không cần thay đổi bảng và phiên A chỉ đang đọc.

Trình tự thường thấy:

```text
Phiên A                         Phiên B                         Phiên C
-------                         -------                         -------
START TRANSACTION
SELECT orders
  giữ MDL
                                ALTER TABLE orders
                                  chờ MDL
                                                                SELECT orders
                                                                  có thể chờ hàng đợi
COMMIT
  giải phóng MDL
                                ALTER TABLE tiếp tục
                                hoàn tất
                                                                SELECT tiếp tục
```

Hiện tượng nhiều phiên bị chặn dây chuyền này thường được gọi là **lock convoy** hoặc nghẽn hàng đợi khóa. Một giao dịch mở lâu có thể tạo ra tác động lớn hơn nhiều so với một truy vấn riêng lẻ: DDL chờ, các truy vấn đến sau cũng chờ, số kết nối đang hoạt động tăng và độ trễ của ứng dụng lan rộng.

## 5. Vì sao giao dịch dài thường là nguồn gốc của vấn đề?

Một giao dịch dài không nhất thiết phải cập nhật nhiều hàng. Nó có thể giữ MDL lâu chỉ vì ranh giới giao dịch chưa đóng. Những tình huống thường gặp gồm:

- Ứng dụng mở transaction trước khi gọi HTTP, RPC, gửi email hoặc chờ dịch vụ bên ngoài phản hồi.
- Luồng xử lý đọc dữ liệu rồi chờ thao tác của người dùng trước khi commit.
- Một nhánh xử lý gặp exception nhưng không rollback hoặc trả kết nối về pool trong trạng thái transaction còn mở.
- Batch job xử lý quá nhiều dữ liệu trong một transaction duy nhất.
- Kết nối `autocommit=0` thực hiện một câu đọc rồi để nhàn rỗi mà không commit hoặc rollback.
- Một truy vấn chạy rất lâu và chưa kết thúc, nên MDL gắn với câu lệnh vẫn còn hiệu lực.

Hãy phân biệt hai trường hợp: câu lệnh đang chạy lâu có thể giữ khóa trong suốt thời gian thực thi; giao dịch đã chạy xong câu lệnh nhưng chưa kết thúc có thể tiếp tục giữ khóa sau đó. Trường hợp thứ hai thường khó phát hiện hơn vì `PROCESSLIST_INFO` có thể trống trong khi transaction vẫn tồn tại.

## 6. Online DDL có loại bỏ được MDL không?

Không. Các thuật toán online DDL giảm thời gian hoặc mức độ chặn DML trong những thao tác được hỗ trợ, nhưng không có nghĩa là DDL không cần phối hợp metadata.

Trong MySQL, các tùy chọn như `ALGORITHM=INSTANT`, `ALGORITHM=INPLACE`, `ALGORITHM=COPY` và `LOCK=NONE` mô tả cách thực hiện hoặc mức độ cho phép truy cập đồng thời. Khả năng sử dụng phụ thuộc phiên bản, loại thay đổi, storage engine và cấu trúc bảng.

- `ALGORITHM=INSTANT` có thể thay đổi một số metadata mà không cần dựng lại toàn bộ dữ liệu bảng. Tuy vậy, câu lệnh vẫn cần lấy MDL thích hợp và có thể phải chờ giao dịch cũ.
- `ALGORITHM=INPLACE` cho phép một số thao tác thực hiện tại chỗ và có thể hỗ trợ DML đồng thời. Từng thao tác vẫn có yêu cầu khóa ở các giai đoạn nhất định.
- `ALGORITHM=COPY` thường phải tạo và sao chép dữ liệu sang cấu trúc mới, nên thời gian và mức độ ảnh hưởng có thể lớn hơn.
- `LOCK=NONE` yêu cầu thao tác hỗ trợ đọc và ghi đồng thời trong giai đoạn được áp dụng. Nó không có nghĩa là không cần MDL ở mọi giai đoạn.

Ví dụ sau chỉ dùng được nếu phiên bản MySQL và loại thay đổi hỗ trợ các tùy chọn đó:

```sql
ALTER TABLE orders
ADD COLUMN source VARCHAR(30),
ALGORITHM=INPLACE,
LOCK=NONE;
```

Nếu tổ hợp thuật toán và mức khóa không được hỗ trợ, MySQL có thể từ chối câu lệnh. Hãy kiểm tra tài liệu đúng phiên bản và thử trên cấu trúc dữ liệu tương đương trước khi triển khai. Đặc biệt, ngay cả DDL tức thời cũng có thể đứng chờ MDL do một giao dịch cũ đang mở.

Nhiều câu lệnh DDL trong MySQL còn gây implicit commit. Vì vậy, không nên đặt DDL giữa một chuỗi thao tác DML rồi giả định rằng toàn bộ chuỗi có thể rollback như một transaction thông thường. Hãy xác định hành vi commit của câu lệnh cụ thể theo tài liệu MySQL.

## 7. Phân biệt chờ MDL với chờ khóa hàng

Hai loại chờ có thể xuất hiện cùng lúc nhưng cần chẩn đoán bằng nguồn dữ liệu khác nhau.

| Dấu hiệu | Chờ metadata lock | Chờ khóa hàng InnoDB |
|---|---|---|
| Đối tượng tranh chấp | Metadata của bảng hoặc đối tượng | Bản ghi, khoảng khóa hoặc tài nguyên dữ liệu của InnoDB |
| Nguyên nhân thường gặp | DDL cần mode khóa không tương thích với phiên đang dùng bảng | Hai giao dịch xung đột khi đọc khóa hoặc cập nhật dữ liệu |
| Trạng thái process list | Có thể hiện `Waiting for table metadata lock` | Có thể hiện trạng thái chờ InnoDB lock hoặc trạng thái chờ khác |
| Nguồn chẩn đoán chính | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits` | `performance_schema.data_locks`, `performance_schema.data_lock_waits`, `information_schema.innodb_trx` |
| Cách xử lý thường gặp | Kết thúc giao dịch giữ MDL hoặc xử lý DDL đang chờ | Xử lý transaction giữ khóa hàng, giảm xung đột dữ liệu hoặc thay đổi thứ tự truy cập |

`innodb_lock_wait_timeout` điều chỉnh thời gian chờ khóa InnoDB; nó không phải biến chính để giới hạn thời gian chờ MDL. Với metadata lock, MySQL cung cấp biến `lock_wait_timeout`. Nhầm hai biến này có thể khiến việc cấu hình timeout không giải quyết đúng loại chờ.

## 8. Điều tra MDL đang chờ trong MySQL

### Bước 1: tìm phiên đang chờ

```sql
SHOW FULL PROCESSLIST;
```

Tìm phiên có trạng thái `Waiting for table metadata lock`. Ghi lại connection id, thời gian chờ, database, câu SQL và host của phiên đó. Câu SQL đang chờ thường là DDL, nhưng hãy kiểm tra thay vì mặc định.

### Bước 2: xem các MDL đang được giữ hoặc đang chờ

MySQL cung cấp `performance_schema.metadata_locks` để xem yêu cầu MDL. Truy vấn sau lọc các khóa đang chờ và các khóa trên bảng cần điều tra:

```sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_HOST AS host_name,
    t.PROCESSLIST_DB AS database_name,
    t.PROCESSLIST_TIME AS process_time_seconds,
    t.PROCESSLIST_STATE AS process_state,
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    t.PROCESSLIST_INFO AS current_sql
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
    ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
   OR (
       ml.OBJECT_SCHEMA = 'appdb'
       AND ml.OBJECT_NAME = 'orders'
   )
ORDER BY
    ml.LOCK_STATUS,
    t.PROCESSLIST_TIME DESC;
```

Thay `appdb` và `orders` bằng schema và bảng thực tế. `PENDING` là yêu cầu đang chờ; `GRANTED` là khóa đã được cấp. Hãy so sánh các dòng trên cùng đối tượng để tìm phiên đang giữ khóa không tương thích với phiên chờ. Cột `PROCESSLIST_INFO` có thể là `NULL` nếu kết nối đang nhàn rỗi; điều đó không chứng minh transaction đã kết thúc.

### Bước 3: tìm giao dịch mở lâu

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Đối chiếu `connection_id` với process list và `performance_schema.threads`. Một giao dịch có `trx_query` rỗng vẫn có thể đang mở và giữ MDL. Thời gian transaction mở thường có ý nghĩa hơn thời gian chạy của câu SQL cuối cùng.

### Bước 4: dùng view tổng hợp nếu có

Trên hệ thống có cài MySQL `sys` schema và các instrumentation cần thiết, view sau giúp xem quan hệ giữa phiên chờ và phiên chặn:

```sql
SELECT *
FROM sys.schema_table_lock_waits;
```

View này hữu ích để tìm nhanh `waiting` và `blocking` thread, tên đối tượng cùng thông tin khóa. Nếu view không tồn tại hoặc không trả dữ liệu, quay lại `performance_schema.metadata_locks` và kiểm tra cấu hình Performance Schema, quyền truy cập cũng như phiên bản máy chủ.

## 9. Cách giảm nguy cơ và xử lý khi xảy ra sự cố

### Thiết kế transaction ngắn

- Chỉ mở transaction ngay trước nhóm thao tác dữ liệu cần tính nhất quán.
- Commit hoặc rollback ngay sau khi hoàn tất nhóm thao tác đó.
- Không giữ transaction trong lúc gọi dịch vụ mạng, gửi thông báo, chờ người dùng hoặc thực hiện công việc không cần tính nguyên tử của cơ sở dữ liệu.
- Đặt timeout hợp lý cho các bước xử lý và bảo đảm mọi nhánh lỗi đều rollback hoặc đóng transaction.
- Với batch lớn, cân nhắc chia thành các lô nhỏ có ranh giới commit rõ ràng, đồng thời đánh giá yêu cầu nhất quán của nghiệp vụ.

### Chuẩn bị DDL

- Kiểm tra giao dịch mở lâu trước thời điểm chạy migration.
- Chạy DDL trong khung thời gian có thể theo dõi và xử lý khi cần.
- Xác nhận thuật toán DDL và mức khóa được hỗ trợ bởi đúng phiên bản, engine và cấu trúc bảng.
- Đặt thời gian chờ metadata lock phù hợp cho phiên chạy migration để một DDL không nằm chờ quá lâu ngoài dự kiến.
- Theo dõi cả thời gian chờ MDL lẫn thời gian thực thi DDL; chúng là hai khoảng thời gian khác nhau.

Ví dụ, có thể giới hạn thời gian chờ MDL cho riêng kết nối chạy migration:

```sql
SET SESSION lock_wait_timeout = 10;

ALTER TABLE orders
ADD COLUMN source VARCHAR(30);
```

Giá trị trên chỉ là ví dụ. Chọn timeout theo cửa sổ triển khai và cách hệ thống xử lý khi migration thất bại. Timeout giới hạn thời gian phiên này chờ khóa; nó không tự giải phóng giao dịch đang giữ khóa.

### Triển khai thay đổi schema theo nhiều bước

Với thay đổi có ảnh hưởng lớn, mô hình **expand-and-contract** giúp ứng dụng và schema chuyển đổi dần:

1. **Expand:** thêm cấu trúc mới theo cách tương thích với phiên bản ứng dụng đang chạy, ví dụ thêm cột mới có thể để trống.
2. **Deploy:** triển khai ứng dụng có thể làm việc với cả cấu trúc cũ và mới.
3. **Backfill:** cập nhật dữ liệu theo từng lô nhỏ, theo dõi tải và thời gian transaction.
4. **Switch:** chuyển luồng đọc/ghi sang cấu trúc mới sau khi dữ liệu đã sẵn sàng.
5. **Contract:** ở một lần triển khai riêng, loại bỏ cột hoặc cấu trúc cũ sau khi không còn phiên bản ứng dụng nào phụ thuộc vào nó.

Phương pháp này không loại bỏ MDL. Nó giảm phạm vi thay đổi cần thực hiện trong một lần và giúp tránh gắn migration nguy hiểm với một transaction dữ liệu kéo dài.

### Chọn hành động khi đang bị chặn

Khi phát hiện DDL chờ MDL, hãy xác định phiên giữ khóa, chủ sở hữu nghiệp vụ và trạng thái transaction trước khi can thiệp. Nếu phiên giữ khóa là ứng dụng hợp lệ, ưu tiên để ứng dụng kết thúc transaction hoặc phối hợp với chủ dịch vụ. Nếu cần hủy một DDL đang chờ, `KILL QUERY <connection_id>` có thể hủy câu lệnh của phiên chờ. Nếu cần kết thúc phiên đang giữ khóa, `KILL CONNECTION <connection_id>` sẽ đóng kết nối và khiến transaction cần rollback; rollback có thể mất thời gian.

Không chọn connection id chỉ dựa vào thời gian chạy hoặc trạng thái `Sleep`. Hãy đối chiếu đối tượng bị khóa, `LOCK_STATUS`, thời điểm bắt đầu transaction và tác động của việc rollback. Kết thúc nhầm phiên có thể làm mất công việc chưa commit hoặc gây thêm tải rollback.

## 10. Checklist khi một lệnh DDL bị treo

1. Xác nhận process list có phiên `Waiting for table metadata lock` hay không.
2. Xác định schema, bảng và câu DDL đang chờ.
3. Xem `performance_schema.metadata_locks` để tìm yêu cầu `PENDING` và các MDL `GRANTED` trên cùng đối tượng.
4. Đối chiếu thread với `information_schema.innodb_trx` để tìm transaction mở lâu, kể cả transaction đang nhàn rỗi.
5. Xác định chủ sở hữu phiên giữ khóa và lý do transaction chưa kết thúc.
6. Chọn cách xử lý có kiểm soát: chờ commit, yêu cầu ứng dụng đóng transaction, hủy DDL chờ hoặc kết thúc phiên chặn sau khi đánh giá rollback.
7. Sau khi xử lý, xác nhận DDL hoàn tất, các truy vấn phía sau được giải phóng và transaction không còn bị bỏ quên.

## 11. Tự kiểm tra

**Một câu `SELECT` đã chạy xong trong transaction tường minh. Vì sao `ALTER TABLE` ở phiên khác vẫn phải chờ?**

Vì transaction của phiên đọc chưa kết thúc. MDL có thể được giữ đến `COMMIT` hoặc `ROLLBACK`, dù câu `SELECT` đã trả kết quả và không khóa hàng nào.

**Vì sao truy vấn mới đôi khi cũng bị chặn trong khi DDL đang chờ?**

Yêu cầu DDL cần mode khóa mạnh hơn và có thể được ưu tiên trong hàng đợi. Những yêu cầu mới trên cùng đối tượng có thể xếp phía sau yêu cầu đang chờ, tạo nghẽn dây chuyền.

**`LOCK=NONE` có bảo đảm DDL không chờ khóa metadata không?**

Không. Tùy chọn này cho phép mức truy cập đồng thời mà thao tác hỗ trợ trong giai đoạn áp dụng. DDL vẫn cần phối hợp metadata và có thể chờ transaction cũ.

**Nên xem `innodb_lock_wait_timeout` hay `lock_wait_timeout` khi DDL chờ MDL?**

`lock_wait_timeout` là biến liên quan đến thời gian chờ metadata lock. `innodb_lock_wait_timeout` điều chỉnh thời gian chờ khóa InnoDB, thường là khóa dữ liệu.

**Một kết nối ở trạng thái `Sleep` có thể giữ MDL không?**

Có. Nếu kết nối đang ở trong transaction chưa commit hoặc rollback, nó có thể không chạy câu SQL nào nhưng vẫn giữ MDL đã lấy trước đó.

Khi đọc sự cố DDL, hãy lần theo ba dữ kiện: **đối tượng nào đang bị khóa, phiên nào đang giữ khóa và transaction đó kết thúc khi nào**. Ba dữ kiện này giúp phân biệt một DDL thực sự chạy lâu với một DDL chỉ đang chờ giao dịch cũ giải phóng metadata.

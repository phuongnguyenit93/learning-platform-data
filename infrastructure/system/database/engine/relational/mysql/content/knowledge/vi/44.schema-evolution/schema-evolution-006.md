# LOCK clause, metadata lock và khoảng chờ DDL

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này tập trung vào việc thay đổi schema an toàn khi hệ thống vẫn có truy cập: chọn mức khóa phù hợp cho DDL, hiểu metadata lock (MDL), tìm phiên đang chặn và kiểm soát thời gian chờ.

Một lệnh `ALTER TABLE` có thể được thiết kế để cho phép ứng dụng tiếp tục đọc và ghi trong phần lớn thời gian thực thi. Tuy nhiên, điều đó không có nghĩa DDL không cần khóa. MySQL vẫn cần metadata lock để bảo vệ định nghĩa bảng và thường cần quyền khóa mạnh hơn trong một số giai đoạn, đặc biệt khi bắt đầu hoặc hoàn tất thay đổi. Một transaction mở lâu có thể giữ MDL và khiến DDL chờ; DDL đang chờ cũng có thể làm các truy vấn mới xếp hàng phía sau. Vì vậy, triển khai schema cần kiểm tra cả thuật toán DDL, mức khóa, thời gian chờ và trạng thái transaction đang chạy.

## 1. Hai khái niệm khóa cần phân biệt

Khi điều tra một lệnh DDL bị chờ, cần phân biệt metadata lock với khóa dữ liệu của InnoDB.

| Loại khóa | Bảo vệ điều gì? | Ví dụ tình huống chờ | Công cụ kiểm tra chính |
|---|---|---|---|
| Metadata lock (MDL) | Metadata của database, table, view, routine và các đối tượng schema liên quan. | `ALTER TABLE` chờ transaction khác kết thúc vì transaction đó đang dùng bảng. | `performance_schema.metadata_locks`, `sys.schema_table_lock_waits`, process list. |
| InnoDB record/gap/next-key lock | Các bản ghi và phạm vi khóa trong index để điều phối transaction đồng thời. | `UPDATE` hoặc `SELECT ... FOR UPDATE` chờ transaction khác nhả khóa dòng. | `performance_schema.data_locks`, `performance_schema.data_lock_waits`, `SHOW ENGINE INNODB STATUS`. |

MDL không phải khóa dòng. Tăng `innodb_lock_wait_timeout` không giải quyết việc DDL chờ metadata lock. Ngược lại, `lock_wait_timeout` điều khiển thời gian chờ metadata lock, không thay thế timeout chờ khóa dòng InnoDB.

## 2. LOCK clause trong ALTER TABLE

Với nhiều thao tác `ALTER TABLE`, MySQL cho phép chỉ định mức truy cập đồng thời bằng `LOCK`. Tùy chọn này yêu cầu một mức khóa nhất định trong quá trình DDL. Khả năng thực hiện phụ thuộc storage engine, thao tác cụ thể, phiên bản MySQL và cấu trúc bảng.

| Giá trị | Ý nghĩa đối với truy cập đồng thời | Cách hiểu khi lập kế hoạch |
|---|---|---|
| `LOCK=DEFAULT` | Để MySQL chọn mức khóa mặc định cho thao tác và thuật toán được chọn. | Linh hoạt nhưng cần kiểm tra tài liệu và hành vi của phiên bản đang chạy. |
| `LOCK=NONE` | Cho phép đọc và ghi đồng thời trong phần thao tác hỗ trợ mức khóa này. | Thường phù hợp với thay đổi online, nhưng vẫn có thể cần MDL ngắn ở đầu/cuối. |
| `LOCK=SHARED` | Cho phép đọc đồng thời, chặn ghi đồng thời trong giai đoạn áp dụng khóa. | Hữu ích khi chấp nhận tạm dừng ghi nhưng vẫn cần đọc. |
| `LOCK=EXCLUSIVE` | Chặn cả đọc và ghi đồng thời trên đối tượng bị thay đổi. | Có thể gây gián đoạn; cần cửa sổ bảo trì và đánh giá thời gian thực thi. |

Ví dụ thêm secondary index cho bảng InnoDB:

```sql
ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

Lệnh yêu cầu MySQL dùng thuật toán INPLACE và mức khóa NONE. Nếu thao tác, engine hoặc cấu trúc bảng không hỗ trợ tổ hợp đó, MySQL sẽ báo lỗi thay vì âm thầm nâng lên một mức khóa gây gián đoạn lớn hơn. Đây là cách hữu ích để fail fast khi yêu cầu online là bắt buộc.

Không suy luận rằng `LOCK=NONE` có nghĩa không có khóa trong toàn bộ vòng đời DDL. MySQL vẫn cần MDL để đọc và thay đổi metadata. Ở các giai đoạn chuyển đổi metadata, DDL có thể phải chờ hoặc lấy MDL mạnh trong thời gian ngắn. Nếu transaction cũ đang giữ MDL tương thích, lệnh vẫn phải đợi transaction đó hoàn tất.

### ALGORITHM và LOCK giải quyết hai câu hỏi khác nhau

`ALGORITHM` quyết định cách MySQL thực hiện thay đổi cấu trúc; `LOCK` quy định mức truy cập đồng thời mà thao tác được phép sử dụng.

| ALGORITHM | Đặc điểm | Điều cần lưu ý |
|---|---|---|
| `INSTANT` | Thay đổi metadata mà không xây dựng lại toàn bộ dữ liệu bảng đối với các thao tác được hỗ trợ. | Chỉ áp dụng cho tập thao tác và điều kiện cụ thể của phiên bản/engine. Có thể thất bại nếu bảng đã đạt giới hạn row version hoặc không thỏa điều kiện. |
| `INPLACE` | Thực hiện thay đổi bằng cơ chế nội bộ của engine, tránh cách sao chép bảng tổng quát. | Không đồng nghĩa luôn không rebuild; một số thao tác INPLACE vẫn phải xây dựng lại dữ liệu và dùng nhiều I/O. |
| `COPY` | Tạo cấu trúc bảng mới và sao chép dữ liệu sang. | Có thể tốn thời gian, dung lượng và hạn chế ghi trong quá trình sao chép. |
| `DEFAULT` | Để MySQL chọn thuật toán phù hợp. | Kết quả có thể thay đổi theo phiên bản, engine và loại thay đổi. |

Ví dụ thêm cột nullable ở cuối bảng bằng INSTANT trên phiên bản/engine hỗ trợ:

```sql
ALTER TABLE orders
    ADD COLUMN source_tag VARCHAR(30) NULL,
    ALGORITHM=INSTANT;
```

Ví dụ này chỉ hợp lệ khi thao tác thêm cột đáp ứng điều kiện INSTANT của phiên bản MySQL đang dùng. Không phải mọi thay đổi kiểu dữ liệu, vị trí cột, khóa, biểu thức mặc định hay thay đổi partition đều có thể thực hiện bằng INSTANT. Kiểm tra tài liệu theo đúng phiên bản và thử trên bản sao có cấu trúc tương tự production.

Nếu ứng dụng yêu cầu không được chặn ghi, chỉ định `LOCK=NONE` cho thao tác có hỗ trợ và xác minh trên staging. Không tự động bỏ `LOCK=NONE` khi gặp lỗi vì việc đó có thể khiến cùng lệnh chạy với mức khóa mạnh hơn dự kiến.

## 3. Metadata lock được giữ trong bao lâu?

MySQL dùng MDL để ngăn định nghĩa đối tượng schema thay đổi trong khi câu lệnh hoặc transaction còn phụ thuộc vào metadata đó. Với bảng InnoDB, một câu lệnh truy cập bảng thường lấy metadata lock tương ứng. Trong transaction tường minh, MDL có thể được giữ đến khi transaction kết thúc, ngay cả khi câu lệnh `SELECT` đã chạy xong.

Ví dụ:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE order_id = 1001;

-- Ứng dụng để transaction mở, chưa COMMIT hoặc ROLLBACK.
```

Nếu session này vẫn giữ transaction mở, MDL trên `orders` có thể tiếp tục được giữ. Một session khác chạy `ALTER TABLE orders ...` cần MDL tương thích với thao tác DDL; nếu không thể lấy khóa, DDL phải chờ.

Điều này thường xuất hiện trong các tình huống:

- Ứng dụng bắt đầu transaction nhưng bị lỗi trước khi `COMMIT` hoặc `ROLLBACK`.
- Connection pool trả kết nối về pool khi transaction vẫn còn mở.
- Một transaction đọc nhiều bảng rồi chờ thao tác bên ngoài, giữ MDL lâu hơn dự kiến.
- Một truy vấn dài đang truy cập bảng mà DDL cần thay đổi.
- Một session dùng `LOCK TABLES` hoặc thao tác quản trị giữ khóa liên quan đến đối tượng.

Với autocommit bật và câu lệnh độc lập, MDL thường được giải phóng khi statement kết thúc. Nhưng nếu statement chạy trong transaction tường minh, cần kết thúc transaction để nhả khóa. Một session ở trạng thái `Sleep` vẫn có thể giữ transaction và MDL; không nên chỉ lọc process list theo truy vấn đang chạy.

## 4. DDL chờ có thể tạo hàng đợi truy vấn

Giả sử transaction A đã truy cập bảng `orders` và chưa kết thúc. DDL B yêu cầu MDL mạnh để thay đổi bảng nên phải chờ. Trong lúc B đang chờ, truy vấn C mới có thể bị xếp hàng tùy loại khóa và chính sách ưu tiên MDL. Một lệnh DDL tưởng như chỉ chờ một transaction vì thế có thể làm tăng độ trễ hoặc khiến nhiều truy vấn mới chờ theo.

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as ALTER TABLE B
    participant C as Query C
    A->>A: SELECT orders; giữ transaction mở
    B->>B: Yêu cầu metadata lock mạnh
    Note over B: Chờ A nhả MDL
    C->>C: Yêu cầu MDL để truy cập orders
    Note over B,C: C có thể phải xếp hàng sau yêu cầu DDL đang chờ
    A->>A: COMMIT hoặc ROLLBACK
    A-->>B: Nhả MDL
    B->>B: Thực hiện DDL và hoàn tất metadata transition
    B-->>C: Nhả MDL
    C->>C: Tiếp tục truy vấn
```

Đây là lý do không nên để một DDL chờ vô thời hạn trong giờ cao điểm. Khi phát hiện DDL bị chặn, cần xác định blocker, ước lượng số session đang xếp hàng và quyết định có tiếp tục chờ hay hủy DDL. Nếu DDL đã chờ lâu, việc chỉ theo dõi session DDL mà bỏ qua các truy vấn đang chờ phía sau có thể đánh giá thấp tác động đến ứng dụng.

## 5. Tìm session đang giữ hoặc chờ metadata lock

### Xem process list

```sql
SHOW FULL PROCESSLIST;
```

Tìm session có trạng thái như `Waiting for table metadata lock`. Ghi nhận connection ID, user, host, thời gian chạy, câu lệnh và database. Một session đang `Sleep` có thể vẫn là blocker nếu transaction chưa được kết thúc.

### Dùng sys.schema_table_lock_waits

Nếu schema `sys` có sẵn và tài khoản có quyền đọc, view `sys.schema_table_lock_waits` hiển thị mối quan hệ giữa session đang đợi và session đang chặn:

```sql
SELECT
    object_schema,
    object_name,
    waiting_pid,
    waiting_query,
    waiting_query_secs,
    blocking_pid,
    blocking_query,
    blocking_lock_duration
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
```

`waiting_pid` là connection đang chờ; `blocking_pid` là connection giữ khóa ngăn yêu cầu được cấp. `blocking_query` có thể rỗng nếu session blocker đang idle trong transaction. Khi đó, cần xem thêm transaction và process list.

### Kiểm tra trực tiếp Performance Schema

Có thể đọc các lock đang được cấp hoặc chờ từ `performance_schema.metadata_locks`:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_HOST,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_STATE,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = 'shop'
  AND ml.OBJECT_NAME = 'orders'
ORDER BY ml.LOCK_STATUS, th.PROCESSLIST_TIME DESC;
```

`LOCK_STATUS` thường có giá trị `GRANTED` hoặc `PENDING`. Dòng `PENDING` cho biết yêu cầu đang chờ; các dòng `GRANTED` trên cùng đối tượng là đầu mối để xác định session đang giữ lock. Cần kết hợp với `sys.schema_table_lock_waits` hoặc phân tích loại lock để xác định blocker chính xác. Performance Schema phải được bật và tài khoản cần đủ quyền đọc các bảng liên quan.

### Tìm transaction InnoDB mở lâu

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Kết quả cho thấy transaction InnoDB và connection ID tương ứng. `trx_query` có thể là `NULL` khi session đang idle nhưng transaction vẫn mở. Đối chiếu `connection_id` với process list và view chờ MDL để xác định session cần xử lý.

## 6. Kiểm soát thời gian chờ DDL

`lock_wait_timeout` là biến cấu hình thời gian tối đa chờ metadata lock, tính bằng giây. Giá trị mặc định trong MySQL thường rất lớn (31.536.000 giây, tương đương một năm), vì vậy DDL có thể chờ lâu nếu không đặt timeout phù hợp.

Trước khi chạy DDL có thể đặt timeout ngắn ở session:

```sql
SET SESSION lock_wait_timeout = 15;

ALTER TABLE orders
    ADD INDEX idx_orders_customer_id (customer_id),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

Nếu không lấy được metadata lock trong 15 giây, câu lệnh sẽ thất bại vì timeout và có thể được thử lại sau khi xử lý blocker. Đây là cách giới hạn thời gian một migration chiếm chỗ trong hàng đợi lock. Hãy chọn giá trị dựa trên cửa sổ triển khai và thời gian chấp nhận được của ứng dụng.

Phân biệt rõ hai biến:

| Biến | Điều khiển | Khi nào cần xem? |
|---|---|---|
| `lock_wait_timeout` | Thời gian chờ metadata lock. | `ALTER TABLE`, `CREATE TABLE`, `RENAME TABLE`, thao tác cần MDL. |
| `innodb_lock_wait_timeout` | Thời gian chờ khóa record/table của InnoDB trong transaction. | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` bị chặn bởi transaction khác. |

Giảm `lock_wait_timeout` không làm DDL chạy nhanh hơn; nó chỉ giúp DDL từ bỏ việc chờ sau thời hạn. Nếu nguyên nhân là transaction mở lâu, cần xử lý transaction hoặc lên lịch DDL lại. Cũng cần nhớ một DDL có thể chờ MDL ở đầu hoặc cuối thao tác dù phần lớn quá trình online đã hoàn tất.

## 7. Xử lý blocker an toàn

Khi xác định được session đang giữ MDL, không nên kill ngay mà chưa hiểu transaction và tác động nghiệp vụ.

1. **Xác định chủ sở hữu.** Đối chiếu connection ID với user, host, ứng dụng và service. Kiểm tra transaction bắt đầu lúc nào, đang thao tác trên những bảng nào và có câu lệnh đang chạy hay không.
2. **Đánh giá khả năng kết thúc bình thường.** Nếu ứng dụng có thể hoàn tất nhanh, yêu cầu session thực hiện `COMMIT` hoặc `ROLLBACK` theo đúng nghiệp vụ.
3. **Nếu cần can thiệp, chọn đúng phạm vi.** `KILL QUERY <id>` chỉ hủy statement hiện tại; nếu session vẫn giữ transaction mở, MDL có thể tiếp tục được giữ. `KILL CONNECTION <id>` đóng session và yêu cầu MySQL rollback transaction đang mở; rollback có thể mất thời gian với transaction lớn.
4. **Theo dõi sau xử lý.** Kiểm tra blocker đã nhả lock, DDL có tiếp tục hay đã timeout, và các truy vấn đang chờ có được giải phóng hay không.
5. **Ghi nhận nguyên nhân gốc.** Điều chỉnh transaction scope, connection pool, timeout ứng dụng hoặc quy trình migration để lỗi không lặp lại.

Không kill session chỉ dựa vào thời gian `Sleep`. Một session có thể đang giữ transaction hợp lệ cần được ứng dụng hoàn tất. Cũng không mặc định `KILL QUERY` sẽ giải phóng mọi MDL; nếu transaction vẫn mở, session vẫn có thể giữ khóa đến khi commit, rollback hoặc connection bị đóng.

## 8. Quy trình triển khai DDL an toàn

Trước khi chạy migration trên production:

1. **Xác minh thay đổi.** Xác định chính xác bảng, index, cột, ràng buộc và phụ thuộc của ứng dụng. Kiểm tra phiên bản MySQL và storage engine.
2. **Chọn ALGORITHM và LOCK.** Ưu tiên `INSTANT` khi thao tác thực sự được hỗ trợ; cân nhắc `INPLACE, LOCK=NONE` cho thao tác online phù hợp. Không giả định tên thuật toán phản ánh đầy đủ lượng I/O hoặc thời gian rebuild.
3. **Thử trên staging.** Dùng bản sao dữ liệu có kích thước và workload gần production. Đo thời gian, I/O, dung lượng tạm, ảnh hưởng ghi và thời gian lấy MDL cuối cùng.
4. **Kiểm tra transaction lâu.** Xem process list, `innodb_trx` và MDL waits trước khi bắt đầu. Xử lý transaction bất thường theo chủ sở hữu.
5. **Đặt timeout.** Đặt `lock_wait_timeout` theo ngân sách chờ của lần triển khai. Nếu timeout, dừng và điều tra; không tự động retry liên tục gây thêm hàng đợi.
6. **Theo dõi trong khi chạy.** Quan sát trạng thái DDL, thời gian chờ, tài nguyên, số kết nối chờ và lỗi ứng dụng.
7. **Xác minh sau DDL.** Kiểm tra cấu trúc bằng `SHOW CREATE TABLE`, index bằng `SHOW INDEX`, kiểm tra truy vấn và error log, rồi xác nhận ứng dụng hoạt động bình thường.

Với thay đổi lớn, cân nhắc chiến lược expand-contract: thêm cấu trúc mới trước, triển khai ứng dụng tương thích cả cấu trúc cũ và mới, backfill theo lô, chuyển đọc/ghi, sau đó mới loại bỏ cấu trúc cũ ở một đợt triển khai riêng. Cách này chia thay đổi thành các bước nhỏ, giúp kiểm soát rủi ro và dễ quay lui hơn.

### Online DDL vẫn có giới hạn tài nguyên

Ngay cả khi `LOCK=NONE` được hỗ trợ, DDL có thể tạo tải I/O, dùng dung lượng tạm, làm tăng redo/undo hoặc tạo online alter log để ghi nhận thay đổi đồng thời. Với InnoDB, `innodb_online_alter_log_max_size` giới hạn dung lượng log online alter. Nếu thay đổi dữ liệu trong lúc DDL quá nhiều và log vượt giới hạn, thao tác có thể thất bại. Do đó cần theo dõi write rate, dung lượng đĩa, thời gian rebuild và khả năng chịu tải của storage.

## 9. Tình huống thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `ALTER TABLE` ở trạng thái `Waiting for table metadata lock` | Transaction hoặc statement khác đang giữ MDL không tương thích. | Tìm blocker bằng `sys.schema_table_lock_waits`, metadata_locks và process list; xử lý transaction. |
| DDL đã chạy lâu nhưng ứng dụng tăng số truy vấn chờ | DDL đang đợi MDL và các yêu cầu mới có thể xếp hàng sau nó. | Giới hạn timeout, đánh giá tác động hàng đợi, hủy DDL nếu cần rồi chạy lại trong cửa sổ phù hợp. |
| `LOCK=NONE` bị từ chối | Thao tác hoặc engine/phiên bản không hỗ trợ mức khóa đó. | Kiểm tra khả năng online DDL; chọn phương án migration khác hoặc cửa sổ bảo trì có phê duyệt. |
| `ALGORITHM=INSTANT` thất bại | Thay đổi không được hỗ trợ hoặc bảng không thỏa điều kiện/version. | Xác minh tài liệu phiên bản; thử INPLACE/COPY trong staging và đánh giá rebuild. |
| `KILL QUERY` xong DDL vẫn chờ | Session blocker vẫn còn transaction mở và giữ MDL. | Xác minh transaction; yêu cầu COMMIT/ROLLBACK hoặc xử lý connection theo quy trình. |
| DDL thất bại vì online alter log vượt giới hạn | Lượng ghi đồng thời trong lúc DDL quá lớn hoặc thao tác kéo dài. | Giảm write pressure, chia nhỏ migration, điều chỉnh giới hạn sau khi đánh giá dung lượng và thử lại. |
| Tăng `innodb_lock_wait_timeout` nhưng DDL vẫn chờ | Đang chờ metadata lock, không phải row lock InnoDB. | Kiểm tra và điều chỉnh `lock_wait_timeout`, xử lý MDL blocker. |

## 10. Bài tập thực hành

Trên môi trường MySQL thử nghiệm, tạo bảng đơn hàng và hai session kết nối riêng. Mục tiêu là quan sát MDL và cách DDL chờ.

**Chuẩn bị bảng:**

```sql
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;
```

**Session A — giữ transaction mở:**

```sql
USE shop;
START TRANSACTION;
SELECT * FROM orders WHERE order_id = 1;
-- Tạm dừng ở đây, chưa COMMIT hoặc ROLLBACK.
```

**Session B — yêu cầu DDL với timeout ngắn:**

```sql
SET SESSION lock_wait_timeout = 15;

ALTER TABLE shop.orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

Trong khi Session B đang chờ, mở Session C và kiểm tra:

```sql
SELECT * FROM sys.schema_table_lock_waits;
SHOW FULL PROCESSLIST;
```

Ghi lại connection ID đang chờ, connection ID đang chặn, thời gian chờ và trạng thái session. Sau đó ở Session A chạy `COMMIT` hoặc `ROLLBACK`, quan sát DDL tiếp tục hay đã hết timeout. Lặp lại bài tập với một transaction ngắn và so sánh thời gian DDL phải đợi.

Cuối cùng, thử thay đổi mức khóa trong một thao tác được phiên bản MySQL hỗ trợ và quan sát khác biệt. Không chạy bài tập giữ transaction lâu, ngắt session hoặc kill connection trên production.

Sau bài tập, người học cần giải thích được vì sao `LOCK=NONE` vẫn có thể chờ MDL, vì sao một session `Sleep` có thể chặn DDL, vì sao `lock_wait_timeout` khác `innodb_lock_wait_timeout`, và cách xác định đúng blocker trước khi quyết định hủy migration hay kết thúc connection. Đây là nền tảng để thay đổi schema MySQL trong khi kiểm soát được thời gian gián đoạn và tác động đến ứng dụng.

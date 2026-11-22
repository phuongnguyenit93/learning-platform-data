# SELECT FOR UPDATE và khóa hàng theo phương ngữ

Hai nhân viên cùng mở màn hình xử lý đơn hàng. Cả hai thấy sản phẩm còn **5 chiếc** và mỗi người định giữ **4 chiếc** cho một đơn khác nhau. Nếu ứng dụng chỉ đọc tồn kho bằng `SELECT` thông thường, rồi tính toán và ghi lại sau đó, cả hai có thể hành động dựa trên một số liệu đã cũ. Kết quả có thể là **bán vượt tồn**, **ghi đè cập nhật của nhau** hoặc thực hiện một nghiệp vụ lẽ ra phải chờ người khác hoàn tất.

Trong nhiều hệ quản trị quan hệ, một cách điều phối là **đọc và đồng thời xin khóa hàng định sửa**. PostgreSQL và một số SQL dialect hỗ trợ cú pháp:

~~~sql
SELECT ...
FROM ...
WHERE ...
FOR UPDATE;
~~~

Ý nghĩa quan trọng không phải “biến SELECT thành UPDATE”. `SELECT FOR UPDATE` vẫn **đọc dữ liệu**; nó đặt một **khóa trên các hàng được chọn** để những giao dịch khác không tự do sửa hoặc giành khóa xung đột trên cùng hàng khi giao dịch hiện tại chưa kết thúc.

Bài học **Database SQL → Giao dịch SQL** giải thích chi tiết:

- Khóa hàng là gì, khác gì với một câu `SELECT` bình thường?
- Khóa được giữ **đến khi nào**, vì sao cần `BEGIN`, `COMMIT`, `ROLLBACK`?
- Hai phiên giao dịch tranh cùng một hàng sẽ **chờ**, **báo lỗi ngay** với `NOWAIT`, hay **bỏ qua hàng đang bị khóa** với `SKIP LOCKED`?
- Các mức khóa `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE` và `FOR KEY SHARE` của PostgreSQL khác nhau ra sao?
- Phải lựa chọn cách thay thế nào trên **MySQL, Oracle, SQL Server và SQLite**, nơi cú pháp hoặc cơ chế khóa khác PostgreSQL?

Các ví dụ thực hành chính dùng **PostgreSQL**. Để quan sát tranh chấp, bạn cần **hai kết nối/SQL Editor độc lập** trỏ đến **cùng một database**. Mỗi ví dụ đều chỉ rõ khi nào phải giữ transaction mở và cách kết thúc để tránh để lại khóa.

## 1. Tại sao SELECT thông thường chưa đủ?

Giả sử một sản phẩm có `stock_qty = 5`:

~~~text
  Thoi diem       Giao dich A                  Giao dich B
  ----------      ------------------------     ------------------------
  t1              SELECT stock_qty -> 5
  t2                                           SELECT stock_qty -> 5
  t3              tinh 5 - 4 = 1
  t4                                           tinh 5 - 4 = 1
  t5              UPDATE stock_qty = 1
  t6                                           UPDATE stock_qty = 1
  t7              COMMIT                       COMMIT
~~~

Nếu hai đơn đều được chấp nhận, hệ thống đã hứa bán **8 chiếc** khi thực tế ban đầu chỉ có **5 chiếc**. Cơ sở dữ liệu cuối cùng có thể vẫn hiển thị tồn 1 vì lần ghi sau **ghi đè giá trị** của lần trước. Hiện tượng này liên quan tới việc **đọc–sửa–ghi dựa trên trạng thái cũ** (*lost update / stale read–modify–write*, tùy cách triển khai).

Điều cần bảo vệ là một **quyết định gồm nhiều bước**:

1. Đọc hàng tồn kho hiện tại.
2. Kiểm tra còn đủ hàng.
3. Tạo bản ghi giữ hàng/đặt hàng nếu phù hợp.
4. Giảm tồn kho và hoàn thành giao dịch.

Nếu các bước ấy phải phản ánh **cùng một trạng thái được bảo vệ**, có thể sử dụng khóa hàng trong một transaction.

### 1.1. Khác nhau giữa SELECT và SELECT FOR UPDATE

| Cách đọc | Mục tiêu chính | Ảnh hưởng tới giao dịch khác trong PostgreSQL |
| --- | --- | --- |
| `SELECT ...` | Đọc dữ liệu theo quy tắc snapshot của transaction | Thường **không lấy khóa hàng để ngăn UPDATE**, nhờ MVCC |
| `SELECT ... FOR UPDATE` | Đọc **và khóa những hàng được chọn** với mức khóa mạnh | `UPDATE`/`DELETE` và yêu cầu khóa hàng xung đột trên các hàng đó phải chờ hoặc xử lý theo chính sách |
| `UPDATE ... WHERE ...` | Thay đổi hàng | Bản thân `UPDATE` cũng lấy khóa thích hợp trên hàng được cập nhật |

**Không phải mọi `SELECT` đều phải thêm `FOR UPDATE`.** Câu lệnh này dành cho trường hợp bạn **sắp đưa ra quyết định có ghi dữ liệu** và cần phối hợp nhiều câu lệnh trong cùng giao dịch. Dùng khóa quá rộng hoặc giữ quá lâu có thể gây chờ khóa, giảm khả năng xử lý đồng thời và làm tăng nguy cơ deadlock.

## 2. Chuẩn bị dữ liệu thực hành PostgreSQL

Chỉ chạy phần khởi tạo trong **database thử nghiệm** mà bạn được phép ghi dữ liệu, khi các bảng `lab_lock304_*` chưa tồn tại. Không sử dụng dữ liệu khách hàng hoặc tài khoản sản xuất để tập khóa.

### 2.1. Bảng tồn kho

~~~sql
CREATE TABLE lab_lock304_inventory (
    item_id INTEGER PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    product_name VARCHAR(80) NOT NULL,
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0),
    reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lab_lock304_inventory
    (item_id, sku, product_name, stock_qty, reserved_qty, unit_price)
VALUES
    (101, 'PEN',   'Bút bi',      12, 0, 12000.00),
    (102, 'NOTE',  'Sổ ghi chú',   7, 0, 35000.00),
    (103, 'MOUSE', 'Chuột có dây', 5, 0, 180000.00),
    (104, 'USB',   'USB 32 GB',    0, 0, 90000.00),
    (105, 'BAG',   'Ba lô',        3, 0, 260000.00);
~~~

Xem trạng thái ban đầu:

~~~sql
SELECT item_id, sku, stock_qty, reserved_qty, unit_price
FROM lab_lock304_inventory
ORDER BY item_id;
~~~

| item_id | sku | stock_qty | reserved_qty | unit_price |
| ---: | --- | ---: | ---: | ---: |
| 101 | PEN | 12 | 0 | 12000.00 |
| 102 | NOTE | 7 | 0 | 35000.00 |
| 103 | MOUSE | 5 | 0 | 180000.00 |
| 104 | USB | 0 | 0 | 90000.00 |
| 105 | BAG | 3 | 0 | 260000.00 |

`item_id` là khóa chính và không `NULL`. Ta sẽ dùng điều kiện `WHERE item_id = 101` để biết **chính xác hàng nào** được khóa trong các ví dụ đầu.

### 2.2. Bảng công việc để thử SKIP LOCKED

~~~sql
CREATE TABLE lab_lock304_jobs (
    job_id INTEGER PRIMARY KEY,
    job_type VARCHAR(30) NOT NULL,
    job_status VARCHAR(12) NOT NULL
        CHECK (job_status IN ('PENDING', 'RUNNING', 'DONE')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    claimed_at TIMESTAMPTZ
);

INSERT INTO lab_lock304_jobs
    (job_id, job_type, job_status)
VALUES
    (1, 'SEND_EMAIL',    'PENDING'),
    (2, 'BUILD_REPORT',  'PENDING'),
    (3, 'SYNC_STOCK',    'PENDING'),
    (4, 'CLEANUP',       'DONE'),
    (5, 'EXPORT_FILE',   'PENDING');
~~~

Bảng này là ví dụ **hàng đợi công việc** (*work queue*), nơi nhiều worker có thể cần lấy các job chưa được xử lý mà tránh giành cùng một job.

## 3. Khóa hàng tồn tại trong một transaction

Trong PostgreSQL, ví dụ đơn giản nhất:

~~~sql
BEGIN;

SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Tu day den khi giao dich ket thuc,
-- giao dich dang giu khoa hang 101.

ROLLBACK;
~~~

`BEGIN` mở transaction. `FOR UPDATE` yêu cầu khóa hàng `101`; khóa xung đột sẽ không được giao cho transaction khác cho đến khi giao dịch hiện tại kết thúc. `ROLLBACK` kết thúc transaction, hoàn tác những thay đổi dữ liệu trong giao dịch (nếu có) và giải phóng khóa do transaction giữ.

Trong ví dụ chỉ có `SELECT`, không có giá trị cột nào bị sửa. Tuy vậy, **khóa vẫn là một tác động của transaction**. Một số thao tác ở PostgreSQL có thể cần ghi metadata phục vụ khóa hàng ngay cả khi bạn không cập nhật giá trị nghiệp vụ.

### 3.1. Khi nào khóa được giải phóng?

| Tình huống | Điều xảy ra với khóa hàng của transaction |
| --- | --- |
| Transaction giữ mở sau `SELECT FOR UPDATE` | Khóa tiếp tục được giữ |
| `COMMIT` thành công | Transaction kết thúc, khóa được giải phóng |
| `ROLLBACK` | Transaction kết thúc, khóa được giải phóng |
| Connection bị ngắt và transaction bị hủy bởi server | Khóa được giải phóng khi transaction bị hủy |
| Chạy `SELECT FOR UPDATE` ở chế độ tự commit từng câu | Khóa thường chỉ sống đến khi **câu lệnh đó kết thúc**, không bảo vệ được bước ứng dụng chạy sau |

Vì vậy, nếu ứng dụng có chuỗi **đọc → quyết định → cập nhật**, các bước phải thuộc **cùng một transaction**. Không thể gọi `SELECT FOR UPDATE`, để công cụ SQL tự commit, rồi vài giây sau chạy `UPDATE` và cho rằng hàng vẫn đang bị khóa.

### 3.2. FOR UPDATE không tự cập nhật hàng

~~~sql
SELECT stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;
~~~

Sau câu lệnh này, `stock_qty` vẫn là 12 nếu không có ai sửa giá trị. `FOR UPDATE` không có nghĩa “tự trừ tồn”, “tự sửa giá”, “tự commit” hoặc “khóa cả bảng vĩnh viễn”.

Lệnh `UPDATE` cần được viết riêng và transaction phải được quản lý thích hợp nếu nghiệp vụ thật sự muốn thay đổi dữ liệu.

## 4. Thực hành hai phiên: một phiên giữ khóa, phiên kia phải chờ

Để kiểm chứng, mở **hai cửa sổ SQL hoặc hai kết nối độc lập** tới cùng database thử nghiệm:

- **Phiên A:** giữ khóa hàng `item_id = 101`.
- **Phiên B:** cố lấy khóa của cùng hàng.

Không chạy lẫn mã hai phiên trong **một kết nối duy nhất**: một transaction không tự xung đột với khóa do chính nó giữ theo cách hai transaction độc lập tranh khóa.

### 4.1. Phiên A: lấy khóa và để transaction mở

Trong **phiên A**:

~~~sql
BEGIN;

SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Giu transaction mo de quan sat phien B.
-- CHUA COMMIT HOAC ROLLBACK.
~~~

Phiên A đã giữ khóa `FOR UPDATE` trên hàng `101`.

### 4.2. Phiên B: xin cùng khóa

Trong **phiên B**, nếu chạy:

~~~sql
BEGIN;

SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;
~~~

truy vấn sẽ **chờ** vì hàng 101 đang bị phiên A giữ khóa xung đột. Thông thường, khi phiên A thực hiện:

~~~sql
ROLLBACK;
~~~

thì phiên B mới có thể nhận khóa và tiếp tục trả kết quả, nếu không có lỗi hoặc điều kiện khác can thiệp.

Khi phiên B đã nhận khóa và xem xong kết quả, nhớ kết thúc transaction của nó:

~~~sql
ROLLBACK;
~~~

Nếu câu `SELECT FOR UPDATE` của B đã được gửi và đang **chờ**, bạn không thể chạy một câu SQL mới trên **cùng kết nối B** cho đến khi truy vấn đó hoàn tất hoặc bị hủy. Để giải phóng khóa, hãy thao tác ở **kết nối A**.

### 4.3. Trình tự thời gian

~~~text
Thoi gian     Phien A                          Phien B
----------    ------------------------------   ------------------------------
t1            BEGIN
t2            SELECT ... id=101 FOR UPDATE
              -> lay duoc khoa hang 101
t3                                             BEGIN
t4                                             SELECT ... id=101 FOR UPDATE
                                               -> CHO khoa
t5            ROLLBACK
              -> nha khoa
t6                                             SELECT tiep tuc, lay duoc khoa
t7                                             ROLLBACK, nha khoa
~~~

Điểm mấu chốt là **khóa có thời gian sống theo transaction**, không theo thời gian người dùng đang nhìn màn hình kết quả. Nếu SQL Editor giữ transaction mở nhưng người dùng rời máy, những kết nối khác có thể bị chờ kéo dài.

## 5. SELECT thường có bị chặn bởi FOR UPDATE không?

Với PostgreSQL sử dụng MVCC (*multi-version concurrency control*), một **`SELECT` bình thường** thường **không phải chờ khóa hàng `FOR UPDATE`** chỉ để đọc dữ liệu phù hợp snapshot.

Thử lại:

**Phiên A:**

~~~sql
BEGIN;

SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Giu khoa.
~~~

**Phiên B:**

~~~sql
SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101;
~~~

Phiên B có thể đọc hàng 101 theo snapshot của câu truy vấn mà **không xin khóa `FOR UPDATE`**. Nếu A còn thực hiện một `UPDATE` nhưng chưa commit, B thường đọc **phiên bản đã commit trước đó**, chứ không thấy dữ liệu chưa được commit của A.

**Không được suy luận rằng đọc thành công nghĩa là có quyền sửa ngay.** Một `UPDATE` hoặc `SELECT ... FOR UPDATE` của B trên cùng hàng có thể phải chờ A.

### 5.1. Ví dụ A thay đổi nhưng chưa commit

**Phiên A**:

~~~sql
BEGIN;

SELECT stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

UPDATE lab_lock304_inventory
SET stock_qty = 10
WHERE item_id = 101;

-- CHUA COMMIT.
~~~

**Phiên B**, bằng một `SELECT` bình thường ở mức `READ COMMITTED`:

~~~sql
SELECT stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101;
~~~

Nếu giá trị ban đầu là 12 và không có thay đổi nào khác, B sẽ vẫn thấy **12**, không thấy giá trị chưa commit **10**. Nếu B cần sửa cùng hàng, B phải phối hợp với transaction A.

Kết thúc **A** bằng `ROLLBACK` để khôi phục 12 và giải phóng khóa. Đây là minh họa hành vi **PostgreSQL/MVCC**, không phải lời hứa mọi hệ quản trị đều cho các `SELECT` thường chạy không chặn trong mọi chế độ khóa và cô lập.

## 6. NOWAIT: không đứng chờ hàng đang bị khóa

Có những tình huống một thao tác cần trả lời nhanh, ví dụ nút “Nhận xử lý ngay” trong giao diện: nếu hàng đã được một người khác giữ thì báo “đang được xử lý”, thay vì khiến yêu cầu chờ lâu.

PostgreSQL hỗ trợ:

~~~sql
SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE NOWAIT;
~~~

`NOWAIT` nghĩa là **không chờ để lấy khóa hàng xung đột**. Nếu có transaction khác đang giữ khóa không tương thích, PostgreSQL báo lỗi khóa ngay thay vì chờ cho đến khi khóa được giải phóng.

### 6.1. Thử hai phiên với NOWAIT

**Phiên A:**

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Giu transaction mo.
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE NOWAIT;

-- Du kien loi vi A dang khoa hang 101.
~~~

Trong PostgreSQL, sau lỗi này, transaction của B có thể rơi vào trạng thái **aborted**: các lệnh SQL tiếp theo sẽ không chạy như bình thường cho đến khi rollback. Hãy kết thúc **phiên B**:

~~~sql
ROLLBACK;
~~~

Sau đó kết thúc **phiên A**:

~~~sql
ROLLBACK;
~~~

**NOWAIT không phải SKIP.** Với NOWAIT, nếu đụng hàng đang khóa, lệnh có thể **báo lỗi**, yêu cầu ứng dụng xử lý. Nó không tự chuyển sang hàng khác.

### 6.2. NOWAIT và khóa cấp bảng

Trong PostgreSQL, `NOWAIT`/`SKIP LOCKED` của locking clause tác động trực tiếp tới **khóa hàng**. Câu `SELECT FOR UPDATE` còn cần lấy một số **khóa cấp bảng** tương ứng. Nếu có xung đột cấp bảng (ví dụ một thao tác DDL đang giữ khóa rất mạnh), truy vấn vẫn có thể phải chờ ở phần khóa bảng.

Do vậy “`NOWAIT` luôn hoàn tất ngay dưới mọi hoàn cảnh” là phát biểu quá mạnh. Khi cần giới hạn thời gian chờ nói chung, có thể cân nhắc `lock_timeout` theo transaction, cùng cơ chế timeout của ứng dụng.

## 7. lock_timeout: giới hạn thời gian chờ một khóa trong PostgreSQL

Khác `NOWAIT` (không chờ khóa hàng), PostgreSQL có cấu hình `lock_timeout` để dừng một statement nếu phải **chờ để lấy khóa quá thời gian cho phép**.

Ví dụ thử ở **phiên B** khi **phiên A** đang giữ khóa hàng 101:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '1500ms';

SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Neu cho khoa qua 1,5 giay, PostgreSQL bao loi timeout.
-- Sau loi, can ROLLBACK transaction.
~~~

Sau khi nhận lỗi, chạy:

~~~sql
ROLLBACK;
~~~

`SET LOCAL` chỉ áp dụng cấu hình trong phạm vi transaction hiện tại. Với transaction A, nhớ `ROLLBACK` hoặc `COMMIT` để giải phóng khóa.

| Cơ chế | Khi gặp khóa hàng xung đột | Cách ứng dụng thường xử lý |
| --- | --- | --- |
| `FOR UPDATE` | **Chờ** cho đến khi có thể lấy khóa hoặc gặp lỗi/timeout | Tiếp tục thao tác khi có khóa |
| `FOR UPDATE NOWAIT` | **Báo lỗi ngay** về xung đột hàng | Báo bận, thử lại sau, hoặc chọn đối tượng khác |
| `FOR UPDATE SKIP LOCKED` | **Không lấy những hàng đang bị khóa xung đột** | Lấy các hàng khả dụng khác |
| `FOR UPDATE` + `lock_timeout` | Chờ nhưng có **giới hạn thời gian** | Bắt lỗi timeout, rollback/retry có kiểm soát |

`lock_timeout` là cấu hình PostgreSQL, không phải cú pháp chung của mọi hệ quản trị.

## 8. SKIP LOCKED: bỏ qua hàng đang bị khóa

Đây là lựa chọn phù hợp khi công việc có **nhiều hàng tương đương để xử lý**, ví dụ hàng đợi job:

> “Lấy một công việc chưa xử lý mà hiện chưa bị worker khác chiếm. Nếu job đầu tiên đang bị khóa, hãy thử job tiếp theo.”

Cú pháp PostgreSQL:

~~~sql
SELECT job_id, job_type
FROM lab_lock304_jobs
WHERE job_status = 'PENDING'
ORDER BY job_id
FOR UPDATE SKIP LOCKED;
~~~

Hàng đã bị khóa xung đột bởi transaction khác **không xuất hiện trong kết quả** của lệnh, dù nó có thể vẫn đáp ứng điều kiện `job_status = 'PENDING'` theo dữ liệu đã commit.

### 8.1. Thử hai phiên với job 1

**Phiên A:**

~~~sql
BEGIN;

SELECT job_id, job_status
FROM lab_lock304_jobs
WHERE job_id = 1
FOR UPDATE;

-- Giu khoa job 1, khong ket thuc giao dich.
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT job_id, job_type
FROM lab_lock304_jobs
WHERE job_status = 'PENDING'
ORDER BY job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;

ROLLBACK;
~~~

Trong điều kiện dữ liệu ban đầu, nếu A đã khóa job 1 và không ai khác giữ khóa, B sẽ lấy **job 2 và job 3**. Job 1 bị bỏ qua; job 4 đã DONE nên không đạt `WHERE`; job 5 vẫn có thể lấy nếu cần thêm.

Kết thúc **phiên A**:

~~~sql
ROLLBACK;
~~~

Đối chiếu:

- `NOWAIT` có thể **báo lỗi** khi gặp một hàng bị khóa.
- `SKIP LOCKED` **bỏ qua hàng ấy** và có thể tiếp tục với hàng khác.
- Không có tùy chọn nào tự động đánh dấu job đã RUNNING; chúng chỉ điều phối việc **lấy khóa hàng**.

### 8.2. Tại sao SKIP LOCKED không thích hợp cho mọi báo cáo?

PostgreSQL lưu ý `SKIP LOCKED` tạo một **cái nhìn không nhất quán với tập hàng đầy đủ** vì các hàng đang bị khóa bị bỏ qua. Điều này có thể có chủ đích đối với queue, nhưng **không thích hợp** để tính tổng doanh thu chính xác hay kiểm kê toàn bộ sản phẩm.

Ví dụ nếu dùng:

~~~sql
SELECT SUM(stock_qty)
FROM lab_lock304_inventory
FOR UPDATE SKIP LOCKED;
~~~

thì câu này **không hợp lệ** trong PostgreSQL vì `FOR UPDATE` không được dùng trực tiếp với truy vấn tổng hợp như vậy. Ngay cả khi thiết kế một truy vấn khác để khóa/chọn các hàng trước rồi tổng hợp ngoài, việc bỏ qua hàng bị khóa sẽ làm phép tổng **không còn đại diện toàn bộ tồn kho**. Đừng áp dụng `SKIP LOCKED` vào báo cáo cần đầy đủ dữ liệu.

### 8.3. SKIP LOCKED không đảm bảo công bằng

Nếu job 1 luôn bị khóa hoặc có lỗi kéo dài, các worker có thể liên tục bỏ qua job đó và xử lý những job khác. Thứ tự `ORDER BY job_id` chỉ thể hiện **ưu tiên các ứng viên còn lấy được khóa**, không bảo đảm mọi job sẽ được xử lý đúng thứ tự tuyệt đối hoặc không bị “bỏ đói” (*starvation*).

Đối với queue thực tế cần thêm trạng thái nhận job, thời hạn sở hữu (*lease*), retry, xử lý worker chết, quan sát job lỗi và bảo vệ việc thực hiện trùng. `SKIP LOCKED` là một mảnh của thiết kế đó, không phải toàn bộ hệ thống hàng đợi.

## 9. Nhận một job một cách nguyên tử bằng CTE + UPDATE

Chỉ `SELECT FOR UPDATE SKIP LOCKED` rồi **trả hàng cho ứng dụng, commit, sau đó mới UPDATE** có thể làm mất ý nghĩa khóa: khi commit, khóa được giải phóng và một worker khác có thể chọn cùng job trước khi trạng thái được đổi.

Một cách PostgreSQL thường dùng là **chọn job có khóa và đổi trạng thái trong cùng một câu lệnh, trong cùng transaction**:

~~~sql
BEGIN;

WITH picked AS (
    SELECT job_id
    FROM lab_lock304_jobs
    WHERE job_status = 'PENDING'
    ORDER BY job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE lab_lock304_jobs AS j
SET
    job_status = 'RUNNING',
    attempts = j.attempts + 1,
    claimed_at = CURRENT_TIMESTAMP
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING
    j.job_id,
    j.job_type,
    j.job_status,
    j.attempts,
    j.claimed_at;

ROLLBACK;
~~~

Ở dữ liệu ban đầu không có worker khác, câu `RETURNING` trả **job 1**, trạng thái RUNNING và `attempts = 1` trong transaction. `ROLLBACK` đưa bảng trở lại trạng thái ban đầu để thực hành lần sau.

### 9.1. Giải thích từng bước

1. CTE `picked` chỉ xét những job `PENDING`.
2. `ORDER BY job_id LIMIT 1` xác định ứng viên ưu tiên.
3. `FOR UPDATE SKIP LOCKED` xin khóa trên ứng viên có thể lấy được và bỏ qua hàng bị khóa.
4. `UPDATE ... FROM picked` sửa **chính job đã lấy khóa**.
5. `RETURNING` trả thông tin công việc được nhận để ứng dụng xử lý tiếp.
6. `COMMIT` (trong quy trình thật) lưu trạng thái RUNNING; `ROLLBACK` (trong bài) hủy thay đổi.

Đây là **một statement cập nhật nguyên tử** đối với việc chọn và đánh dấu job trong transaction, không phải hai thao tác không liên quan.

### 9.2. Không giữ transaction mở suốt tác vụ bên ngoài kéo dài

Giả sử gửi email mất nhiều giây hoặc một job có thể chạy vài phút. Nếu giữ transaction và khóa hàng mở trong suốt thời gian xử lý bên ngoài, bạn có thể gây tranh chấp khóa kéo dài.

Một thiết kế queue thường là:

1. Trong transaction ngắn: **claim job** và ghi trạng thái RUNNING cùng thông tin nhận job.
2. Commit.
3. Thực hiện công việc bên ngoài.
4. Trong transaction khác: xác nhận DONE, hoặc ghi lỗi/retry.

Muốn tránh job bị xử lý hai lần khi worker chết sau commit mà trước khi hoàn tất, cần cơ chế **lease/heartbeat/acknowledgement, ID công việc và idempotency**. Không thể dựa vào `FOR UPDATE` còn được giữ sau commit, vì khóa đã được giải phóng.

## 10. SELECT FOR UPDATE trong luồng đặt hàng an toàn

Trở lại bài toán tồn kho. Nếu cần kiểm tra tồn, tạo đơn và điều chỉnh nhiều bảng trong cùng một quyết định, một luồng transaction có thể là:

~~~sql
BEGIN;

-- 1. Doc va khoa dung san pham can su dung.
SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 103
FOR UPDATE;

-- 2. Ung dung kiem tra co du so luong hay khong.
-- Vi du muon giu 3 don vi, stock_qty ban dau la 5.

-- 3. Cap nhat co dieu kien ngay tai database.
UPDATE lab_lock304_inventory
SET
    stock_qty = stock_qty - 3,
    reserved_qty = reserved_qty + 3,
    updated_at = CURRENT_TIMESTAMP
WHERE item_id = 103
  AND stock_qty >= 3
RETURNING
    item_id, stock_qty, reserved_qty;

-- Trong giao dich thuc, con co the tao hang dat cho / don hang.
-- Xac minh thanh cong va quan he nghiep vu truoc khi COMMIT.

ROLLBACK;
~~~

Với dữ liệu ban đầu, hàng 103 chuyển tạm thời từ **5 còn 2**, `reserved_qty` từ **0 lên 3**. Sau `ROLLBACK`, hai giá trị trở lại 5 và 0.

### 10.1. Vì sao vẫn thêm stock_qty >= 3 trong UPDATE?

`SELECT FOR UPDATE` bảo vệ trạng thái sau khi lấy được khóa, nhưng điều kiện `WHERE stock_qty >= 3` ở chính `UPDATE` còn là **hàng rào ở database**:

- Không trừ tồn nếu hàng không đủ số lượng.
- Giảm nguy cơ lỗi khi chương trình áp dụng sai quy tắc kiểm tra hoặc thay đổi logic.
- Tạo một điều kiện rõ ràng để biết khi nào câu `UPDATE` không ảnh hưởng hàng nào.

Nếu `UPDATE ... RETURNING` **không trả hàng** vì không đủ tồn, ứng dụng phải xử lý đơn hàng là **không được giữ hàng** và rollback những thao tác có liên quan.

### 10.2. Có phải mọi thao tác trừ tồn đều cần SELECT FOR UPDATE trước?

**Không.** Nếu thao tác cần thực hiện chỉ là “trừ N đơn vị nếu còn đủ”, một câu `UPDATE` có điều kiện có thể đã là đủ và tránh một vòng đọc thêm:

~~~sql
BEGIN;

UPDATE lab_lock304_inventory
SET stock_qty = stock_qty - 3
WHERE item_id = 103
  AND stock_qty >= 3
RETURNING item_id, stock_qty;

ROLLBACK;
~~~

`UPDATE` tự lấy khóa phù hợp trên hàng mà nó sửa. Với PostgreSQL `READ COMMITTED`, khi gặp hàng bị cập nhật đồng thời, câu lệnh có thể chờ và **đánh giá lại điều kiện `WHERE` trên phiên bản hàng phù hợp** trước khi áp dụng cập nhật, giúp tránh phép trừ dựa trên kiểm tra điều kiện đã cũ trong mẫu này.

`SELECT FOR UPDATE` có giá trị đặc biệt khi quyết định cần **nhiều bước hoặc nhiều bảng**, hay khi ứng dụng phải đọc một số thuộc tính rồi thực hiện nghiệp vụ được bảo vệ trong cùng transaction. Đừng thêm nó vào tất cả các câu `SELECT` một cách máy móc.

### 10.3. Trường hợp hàng không tồn tại

Nếu chạy:

~~~sql
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 999
FOR UPDATE;
~~~

truy vấn không trả hàng, nên không có **hàng 999 đang tồn tại** để khóa. `FOR UPDATE` trong PostgreSQL **không tự “đặt chỗ” một khóa ID chưa tồn tại** để bảo đảm không ai có thể INSERT ID đó về sau.

Nếu nghiệp vụ là “chỉ một phiên được tạo bản ghi mới với khóa này”, cần ràng buộc `PRIMARY KEY`/`UNIQUE` và cách chèn nguyên tử như `INSERT ... ON CONFLICT` hoặc chiến lược giao dịch phù hợp, chứ không chỉ `SELECT FOR UPDATE` trên kết quả rỗng.

Hành vi khóa khoảng (*gap/next-key locking*) trong MySQL InnoDB có thể khác trong một số mức cô lập và điều kiện truy vấn; không nên coi cách PostgreSQL xử lý khóa trên hàng không tồn tại là quy tắc chung cho mọi dialect.

## 11. Bốn chế độ khóa hàng trong PostgreSQL

PostgreSQL cung cấp bốn dạng *row-level locking clause*:

~~~sql
FOR UPDATE
FOR NO KEY UPDATE
FOR SHARE
FOR KEY SHARE
~~~

Chúng khác nhau ở **mức xung đột** đối với thao tác của transaction khác:

| Mức khóa | Ý tưởng chính |
| --- | --- |
| `FOR UPDATE` | Khóa mạnh; ngăn các thao tác khóa hàng xung đột, kể cả những khóa chia sẻ khác |
| `FOR NO KEY UPDATE` | Khóa để sửa hàng nhưng không thay đổi những cột khóa liên quan tới khả năng tham chiếu; yếu hơn `FOR UPDATE` |
| `FOR SHARE` | Khóa đọc chia sẻ: nhiều transaction có thể cùng giữ, nhưng chặn các cập nhật hàng xung đột |
| `FOR KEY SHARE` | Khóa chia sẻ nhẹ hơn, bảo vệ hàng trước các thay đổi khóa/xóa gây xung đột; cho phép một số cập nhật không làm đổi khóa |

Một bảng rút gọn về xung đột giữa **hai yêu cầu khóa hàng** trên cùng một hàng trong PostgreSQL:

| Khóa đang giữ \ Khóa được xin | FOR KEY SHARE | FOR SHARE | FOR NO KEY UPDATE | FOR UPDATE |
| --- | :---: | :---: | :---: | :---: |
| **FOR KEY SHARE** | Không | Không | Không | **Có** |
| **FOR SHARE** | Không | Không | **Có** | **Có** |
| **FOR NO KEY UPDATE** | Không | **Có** | **Có** | **Có** |
| **FOR UPDATE** | **Có** | **Có** | **Có** | **Có** |

“**Có**” nghĩa là hai khóa **xung đột**: nếu một transaction đang giữ một khóa thì transaction khác có thể phải chờ hoặc báo lỗi khi xin khóa đối ứng. “Không” nghĩa là hai mức khóa này **tương thích về khóa hàng**, nhưng vẫn có thể chịu các điều kiện khác như khóa bảng, ràng buộc hoặc transaction.

### 11.1. FOR NO KEY UPDATE

Ví dụ:

~~~sql
BEGIN;

SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR NO KEY UPDATE;

ROLLBACK;
~~~

Trong PostgreSQL, một `UPDATE` không sửa các cột khóa mà cơ sở dữ liệu cần bảo vệ cho quan hệ khóa ngoại thường lấy mức khóa hàng tương đương **FOR NO KEY UPDATE**; những cập nhật ảnh hưởng tới các cột khóa phù hợp có thể cần mức mạnh hơn **FOR UPDATE**.

Không được hiểu rằng `FOR NO KEY UPDATE` “không cho phép cập nhật bất kỳ khóa nào trên toàn database”; tên gọi có ngữ nghĩa chính xác theo cơ chế xác định cột khóa được PostgreSQL áp dụng.

### 11.2. FOR SHARE

~~~sql
BEGIN;

SELECT item_id, unit_price
FROM lab_lock304_inventory
WHERE item_id = 101
FOR SHARE;

ROLLBACK;
~~~

Hai phiên cùng giữ `FOR SHARE` trên một hàng thường tương thích, nhưng một phiên muốn `UPDATE`/`DELETE` hàng đó có thể phải chờ cho đến khi các khóa chia sẻ được nhả.

Không nên dùng `FOR SHARE` để bảo vệ một luồng **đọc rồi sửa hàng** mà không hiểu khả năng cả hai phiên cùng đọc rồi cố nâng cấp khóa; nhiều giao dịch cùng giữ khóa chia sẻ và sau đó cùng muốn khóa mạnh hơn có thể tạo **deadlock**.

### 11.3. FOR KEY SHARE

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR KEY SHARE;

ROLLBACK;
~~~

Khóa này thích hợp cho một số tình huống cần bảo vệ **sự tồn tại/khóa tham chiếu** của hàng nhưng không muốn ngăn những cập nhật không ảnh hưởng khóa phù hợp. PostgreSQL cũng dùng cơ chế khóa liên quan khi kiểm tra khóa ngoại.

### 11.4. Mạnh hơn không phải lúc nào cũng tốt hơn

Sử dụng `FOR UPDATE` ở mọi nơi có thể làm các giao dịch khác phải chờ không cần thiết. Chọn mức khóa theo **bất biến nghiệp vụ cần bảo vệ**, loại thao tác dự kiến và khả năng các phiên thao tác đồng thời.

Với người mới học, `FOR UPDATE` là ví dụ dễ hiểu cho “đọc hàng trước khi sửa”, nhưng trong hệ thống lớn hãy cân nhắc đúng mức khóa và dùng ràng buộc/giao dịch thay vì tăng độ mạnh khóa vô điều kiện.

## 12. FOR UPDATE OF: chỉ khóa hàng của bảng được chỉ định khi JOIN

Truy vấn thực tế thường có `JOIN`. Ví dụ ta hiển thị sản phẩm cùng thông tin kế hoạch nhập hàng. Nếu không nói rõ, một `SELECT ... FOR UPDATE` trên phép nối có thể xin khóa các hàng từ **nhiều bảng lockable tham gia truy vấn**.

Giả sử có bảng kế hoạch tương ứng (bảng này **không được tạo** trong phần dữ liệu mẫu):

~~~sql
-- Minh hoa cau truc JOIN, can co bang lab_lock304_plan truoc khi chay.
SELECT
    i.item_id,
    i.stock_qty,
    p.target_qty
FROM lab_lock304_inventory AS i
JOIN lab_lock304_plan AS p
    ON p.item_id = i.item_id
WHERE i.item_id = 101
FOR UPDATE OF i;
~~~

`FOR UPDATE OF i` trong PostgreSQL có nghĩa **chỉ yêu cầu khóa các hàng của bảng bí danh `i`** (inventory) nằm trong kết quả phù hợp, không nhất thiết khóa hàng `p` của bảng kế hoạch với cùng mức FOR UPDATE.

Nếu muốn khóa cả hai bảng khi phù hợp:

~~~sql
-- Minh hoa khi hai bang ton tai va deu duoc phep khoa.
SELECT i.item_id, p.target_qty
FROM lab_lock304_inventory AS i
JOIN lab_lock304_plan AS p
    ON p.item_id = i.item_id
WHERE i.item_id = 101
FOR UPDATE OF i, p;
~~~

**Lưu ý**: khóa hàng trong JOIN có những giới hạn khi phía được khóa nằm ở phía **có thể không có hàng** của outer join; PostgreSQL có thể từ chối `FOR UPDATE` áp dụng trực tiếp lên phía nullable đó. Đừng cho rằng có thể khóa “một hàng không tồn tại” chỉ bằng thêm `FOR UPDATE` vào `LEFT JOIN`.

### 12.1. Ví dụ JOIN chạy được với bảng mẫu

Ta có thể tự nối inventory với chính nó để thấy cú pháp `OF` trên một truy vấn có hai bí danh:

~~~sql
BEGIN;

SELECT
    i.item_id,
    i.sku,
    peer.item_id AS peer_id,
    peer.sku AS peer_sku
FROM lab_lock304_inventory AS i
JOIN lab_lock304_inventory AS peer
    ON peer.item_id = 102
WHERE i.item_id = 101
FOR UPDATE OF i;

ROLLBACK;
~~~

`FOR UPDATE OF i` nhắm vào hàng với bí danh `i` (ID 101). Không được suy ra rằng tất cả các hàng từ bí danh `peer` (ở đây ID 102) cũng được khóa bằng `FOR UPDATE` chỉ vì tên bảng vật lý trùng nhau; danh sách `OF` chỉ rõ đối tượng khóa.

Trong hệ thống thật, nên dùng `OF` theo bí danh bảng ở `FROM` khi cần kiểm soát chính xác những hàng nào phải giữ khóa.

## 13. WHERE, ORDER BY và LIMIT ảnh hưởng tới hàng được khóa

### 13.1. Chọn đúng hàng bằng WHERE

~~~sql
BEGIN;

SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id IN (101, 102)
ORDER BY item_id
FOR UPDATE;

ROLLBACK;
~~~

Truy vấn xin khóa hai hàng phù hợp `101` và `102`. Khóa hàng **không** tự lan sang tất cả sản phẩm 103–105 chỉ vì cùng nằm trong một bảng.

Tuy nhiên, câu `SELECT FOR UPDATE` cũng lấy **khóa cấp bảng** liên quan, và chiến lược truy cập/khóa có thể chịu những chi tiết triển khai. “Chỉ khóa hai hàng” nên được hiểu ở **phạm vi row-level locks do truy vấn đòi hỏi**, không phải phủ nhận sự tồn tại của mọi khóa cấp bảng.

### 13.2. LIMIT không đồng nghĩa khóa toàn bộ các hàng thỏa WHERE

~~~sql
BEGIN;

SELECT job_id
FROM lab_lock304_jobs
WHERE job_status = 'PENDING'
ORDER BY job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;

ROLLBACK;
~~~

Trong một truy vấn trực tiếp như thế này của PostgreSQL, `LIMIT 2` giúp chỉ lấy **tối đa hai hàng kết quả** có thể được chọn/khóa theo chính sách SKIP LOCKED. Những truy vấn phức tạp với subquery, joins hoặc vị trí đặt locking clause có thể thay đổi phạm vi khóa thực tế, nên không được suy diễn quy tắc này cho mọi câu SQL tùy ý.

### 13.3. ORDER BY không phải lời hứa công bằng hoặc không bị đảo thứ tự do đồng thời

`ORDER BY job_id` diễn đạt tiêu chí ưu tiên trong truy vấn. Nhưng dưới tranh chấp khóa:

- `SKIP LOCKED` có thể bỏ qua job có ID nhỏ nhất vì nó đang bị khóa.
- Ở PostgreSQL `READ COMMITTED`, nếu truy vấn khóa hàng có `ORDER BY` và phải chờ trong khi giá trị cột sắp xếp bị thay đổi đồng thời, có những tình huống kết quả được trả theo thứ tự đã trở nên cũ so với giá trị sau khi chờ.

Vì vậy **thứ tự đầu ra được yêu cầu** và **đảm bảo xử lý công bằng tuyệt đối khi đồng thời** không phải một khái niệm.

### 13.4. FOR UPDATE không dùng trực tiếp cho mọi dạng SELECT

PostgreSQL giới hạn row-locking clause trong một số truy vấn mà hàng kết quả không thể liên hệ đơn giản với từng hàng bảng gốc, ví dụ truy vấn tổng hợp, `GROUP BY`, `DISTINCT` hoặc các phép toán tập hợp ở cấp truy vấn không phù hợp.

Ví dụ không hợp lệ:

~~~sql
-- KHONG CHAY: SUM tra hang tong hop, khong phai hang nguon de khoa.
SELECT SUM(stock_qty)
FROM lab_lock304_inventory
FOR UPDATE;
~~~

Nếu cần khóa các hàng nguồn rồi tính tổng có kiểm soát, phải thiết kế **các bước khóa và tính toán** đúng phạm vi transaction, không đơn giản gắn `FOR UPDATE` vào bất cứ `SELECT` nào.

## 14. Isolation level: khóa hàng và snapshot là hai cơ chế liên quan

Khóa hàng điều phối **ai có thể sửa/giữ khóa xung đột trên hàng**. Mức cô lập giao dịch điều phối **dữ liệu được nhìn thấy và những bất thường đồng thời nào được phép**.

### 14.1. READ COMMITTED của PostgreSQL

Ở mức `READ COMMITTED` mặc định phổ biến:

- Một `SELECT` thường thấy snapshot dữ liệu đã commit tại thời điểm câu lệnh bắt đầu.
- `SELECT FOR UPDATE` có thể phải chờ giao dịch khác đang cập nhật cùng hàng.
- Sau khi chờ một cập nhật được commit, PostgreSQL có thể lấy phiên bản phù hợp và **đánh giá lại điều kiện** trên hàng đó trước khi trả/khoá.

Ví dụ nếu B đang muốn khóa hàng có `stock_qty > 0`, trong khi A giảm số lượng từ 1 về 0 và commit, B có thể không còn thấy hàng đó thỏa điều kiện sau khi chờ.

### 14.2. REPEATABLE READ và SERIALIZABLE

Ở các mức cô lập mạnh hơn, những cập nhật đồng thời ảnh hưởng hàng mà transaction đọc hoặc muốn khóa có thể dẫn tới **lỗi serialization** thay vì chỉ chờ rồi lấy phiên bản cập nhật mới như `READ COMMITTED`. Ứng dụng cần sẵn sàng **rollback và retry cả transaction** khi gặp loại lỗi có thể thử lại.

Không nên giả định rằng nâng isolation level có nghĩa mọi `SELECT FOR UPDATE` đều hoạt động y hệt ở `READ COMMITTED`, chỉ “an toàn hơn”.

### 14.3. SELECT FOR UPDATE không khóa mọi điều kiện logic

Nếu nghiệp vụ là “trong hệ thống chỉ được tồn tại một đơn ACTIVE cho cùng mã khách hàng” và lúc truy vấn chưa có đơn nào, `SELECT ... FOR UPDATE` trên tập rỗng **không tạo ra một hàng để khóa**. Ngoài khóa hàng, có thể cần:

- Ràng buộc `UNIQUE` hoặc chỉ mục duy nhất có điều kiện, nếu phù hợp.
- Câu `INSERT` nguyên tử và cơ chế xung đột khóa.
- Mức cô lập `SERIALIZABLE` hoặc thiết kế khóa/transaction khác, với xử lý retry.

**Đúng bất biến nghiệp vụ quan trọng hơn việc thêm khóa vào tất cả truy vấn.**

## 15. Deadlock: hai transaction chờ khóa của nhau

Một vòng chờ có thể xuất hiện khi hai giao dịch cần nhiều hàng nhưng khóa theo thứ tự khác nhau:

~~~text
                    Hang 101                  Hang 102
Giao dich A        DA GIU khoa                muon lay khoa
Giao dich B        muon lay khoa              DA GIU khoa

A cho B nha hang 102
B cho A nha hang 101
=> deadlock
~~~

Ví dụ logic:

**Phiên A:**

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

-- Sau khi B da khoa 102:
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 102
FOR UPDATE;
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 102
FOR UPDATE;

-- Sau khi A da khoa 101:
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;
~~~

Hai phiên có thể chờ nhau. PostgreSQL có cơ chế **phát hiện deadlock** và sẽ hủy một transaction/lệnh thích hợp để phá vòng chờ. Một phía phải xử lý lỗi, rollback, và thường retry toàn bộ nghiệp vụ theo chính sách.

### 15.1. Cách giảm nguy cơ deadlock

- **Khóa theo thứ tự nhất quán** (ví dụ luôn theo `item_id` tăng dần) trong mọi đường đi của ứng dụng.
- Giữ transaction **ngắn**, không chờ người dùng nhập liệu trong khi giữ khóa.
- Chỉ khóa những hàng **thực sự cần thiết**.
- Dùng truy vấn `UPDATE` có điều kiện nguyên tử khi chỉ có một thay đổi đơn giản.
- Có cơ chế **retry giao dịch** cho lỗi deadlock/serialization phù hợp, với thao tác có tính lặp lại an toàn.

`NOWAIT` có thể giúp tránh chờ trong một số tình huống nhưng **không phải biện pháp thay thế toàn bộ thiết kế thứ tự khóa**. `SKIP LOCKED` phù hợp một số queue, không biến mọi bài toán nhiều hàng thành không thể deadlock.

## 16. Phạm vi khóa và chi phí vận hành

Khóa hàng không “miễn phí”. Khi nhiều giao dịch cùng thao tác dữ liệu:

1. **Thời gian giữ khóa** càng dài thì các phiên xung đột càng có thể phải chờ lâu.
2. **Số hàng khóa** càng nhiều thì phạm vi tranh chấp có thể càng rộng.
3. Những tác vụ không liên quan như gọi API, gửi email, ghi file trong lúc mở transaction có thể làm khóa bị giữ quá lâu.
4. Các mức khóa khác nhau có **khả năng tương thích khác nhau**; chọn mức mạnh nhất ở mọi nơi có thể làm giảm đồng thời không cần thiết.
5. Thêm khóa không làm thay thế ràng buộc `CHECK`, `UNIQUE`, `FOREIGN KEY` hoặc quy tắc nghiệp vụ.

### 16.1. Chỉ mục và chi phí tìm hàng

Trong bảng mẫu, `item_id` là `PRIMARY KEY` nên có chỉ mục để tìm hàng theo ID. Một truy vấn:

~~~sql
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;
~~~

có thể tìm nhanh hàng cần khóa. Nếu điều kiện không được hỗ trợ bởi chỉ mục và phải quét nhiều dữ liệu, chi phí truy vấn có thể tăng. Tuy nhiên **không có chỉ mục không đồng nghĩa PostgreSQL sẽ khóa tất cả các hàng chỉ vì phải quét bảng**; cần phân biệt số hàng được quét, số hàng đủ điều kiện và số hàng cuối cùng được khóa.

### 16.2. Xem kế hoạch mà không thực thi khóa

~~~sql
EXPLAIN
SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;
~~~

Trong PostgreSQL, `EXPLAIN` **không có `ANALYZE`** chỉ mô tả kế hoạch dự kiến; kế hoạch có thể bao gồm nút `LockRows`. Ngược lại, `EXPLAIN ANALYZE` **thực thi câu SELECT** và có thể lấy khóa thực tế. Không dùng `EXPLAIN ANALYZE SELECT ... FOR UPDATE` rồi nghĩ đó chỉ là cách xem kế hoạch không làm gì trên dữ liệu thật.

### 16.3. Quan sát transaction chờ khóa

Ở PostgreSQL, các công cụ quản trị như `pg_stat_activity`, `pg_locks` và hàm `pg_blocking_pids(...)` có thể giúp điều tra phiên đang chờ hoặc chặn phiên khác. Thông tin nhìn thấy phụ thuộc quyền và phiên bản.

Ví dụ chỉ đọc, **không tự hủy phiên nào**:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
~~~

Một truy vấn đang bị chặn bởi khóa có thể hiển thị `wait_event_type = 'Lock'`. Cần nhớ một transaction **idle in transaction** cũng có thể còn giữ khóa dù hiện không chạy câu SQL nào. Đừng tự ý dùng hàm chấm dứt backend hoặc can thiệp phiên khác trên production chỉ để giải quyết bài thực hành.

## 17. Khác biệt giữa các SQL dialect

**Cú pháp và mức khóa không hoàn toàn tương đương giữa PostgreSQL, MySQL, Oracle, SQL Server và SQLite.** Khi chuyển ví dụ, cần đọc tài liệu **đúng hệ quản trị và phiên bản**, nhất là với `NOWAIT`, `SKIP LOCKED`, isolation level, khóa khoảng, transaction và hint khóa.

### 17.1. PostgreSQL

Các dạng chính:

~~~sql
SELECT ... FOR UPDATE;
SELECT ... FOR UPDATE NOWAIT;
SELECT ... FOR UPDATE SKIP LOCKED;
SELECT ... FOR NO KEY UPDATE;
SELECT ... FOR SHARE;
SELECT ... FOR KEY SHARE;
SELECT ... FOR UPDATE OF alias_bang;
~~~

PostgreSQL có MVCC; `SELECT` thông thường không tự lấy khóa hàng FOR UPDATE. Khóa hàng `FOR UPDATE` được giữ tới khi transaction kết thúc; `NOWAIT`/`SKIP LOCKED` là tùy chọn xử lý xung đột khi chọn hàng.

### 17.2. MySQL (InnoDB)

MySQL với InnoDB hỗ trợ **locking read**:

~~~sql
-- MySQL 8.0+ minh hoa, gia dinh bang inventory da ton tai.
START TRANSACTION;

SELECT item_id, stock_qty
FROM inventory
WHERE item_id = 101
FOR UPDATE;

-- Xu ly cap nhat trong cung transaction neu can.
ROLLBACK;
~~~

Trong các phiên bản MySQL 8.0 hỗ trợ, có thể dùng:

~~~sql
SELECT item_id
FROM inventory
WHERE item_id = 101
FOR UPDATE NOWAIT;

SELECT item_id
FROM inventory
WHERE stock_qty > 0
FOR UPDATE SKIP LOCKED;
~~~

Nhưng **không suy luận rằng InnoDB chỉ khóa đúng những hàng được trả về trong mọi trường hợp**. Tùy **isolation level, điều kiện truy vấn, chỉ mục và kiểu truy cập**, InnoDB có thể dùng **record locks, gap locks hoặc next-key locks**, ảnh hưởng cả khả năng chèn vào khoảng khóa. Các đặc điểm này đặc biệt đáng chú ý trong `REPEATABLE READ` và truy vấn theo khoảng.

Locking read cần được dùng trong **transaction thích hợp**; nếu câu lệnh tự commit ngay, khóa không bảo vệ bước ứng dụng tiếp theo. Khả năng `NOWAIT`/`SKIP LOCKED` cũng phụ thuộc phiên bản MySQL và loại engine, không nên áp dụng cho mọi hệ thống gắn nhãn “MySQL”.

### 17.3. Oracle Database

Oracle có cú pháp `SELECT ... FOR UPDATE` và những tùy chọn:

~~~sql
-- Oracle SQL minh hoa, gia dinh bang INVENTORY.
SELECT item_id, stock_qty
FROM inventory
WHERE item_id = 101
FOR UPDATE;
~~~

~~~sql
SELECT item_id
FROM inventory
WHERE item_id = 101
FOR UPDATE NOWAIT;
~~~

~~~sql
SELECT item_id
FROM inventory
WHERE item_id = 101
FOR UPDATE WAIT 5;
~~~

~~~sql
SELECT item_id
FROM inventory
WHERE stock_qty > 0
FOR UPDATE SKIP LOCKED;
~~~

`WAIT 5` là ví dụ yêu cầu chờ khóa trong thời gian giới hạn theo cú pháp Oracle, **không phải cú pháp PostgreSQL** (PostgreSQL dùng `lock_timeout`). Oracle cũng hỗ trợ `FOR UPDATE OF ...` trong những truy vấn phù hợp; quy tắc xác định bảng/hàng bị khóa và hạn chế với view/join cần được kiểm tra theo phiên bản.

Không suy luận “trong PostgreSQL `SKIP LOCKED` ra 2 hàng thì Oracle cũng luôn ra đúng 2 hàng”, vì kế hoạch, thứ tự truy cập, hành vi truy vấn và xử lý khóa phụ thuộc hệ quản trị.

### 17.4. SQL Server: lock hints thay vì SELECT FOR UPDATE

SQL Server (T-SQL) không dùng nguyên cú pháp PostgreSQL `SELECT ... FOR UPDATE`. Nó có các **table hints** để điều chỉnh cách lấy khóa, ví dụ `UPDLOCK`, `ROWLOCK`, `READPAST`, `NOWAIT`:

~~~sql
-- T-SQL minh hoa, gia dinh dbo.Inventory ton tai.
BEGIN TRANSACTION;

SELECT item_id, stock_qty
FROM dbo.Inventory WITH (UPDLOCK, ROWLOCK)
WHERE item_id = 101;

-- Xu ly UPDATE neu phu hop.
ROLLBACK TRANSACTION;
~~~

`UPDLOCK` yêu cầu khóa dạng update trong quá trình đọc theo quy tắc SQL Server; các khóa đó có thể được giữ đến cuối transaction. `ROWLOCK` là **gợi ý** về độ hạt khóa, **không phải lời đảm bảo** máy chủ không bao giờ dùng khóa cấp khác, hoặc các yếu tố khác không ảnh hưởng truy vấn.

Một mẫu liên quan tới queue:

~~~sql
-- T-SQL minh hoa; can kiem tra isolation level va cac tuy chon
-- READ_COMMITTED_SNAPSHOT cua database.
BEGIN TRANSACTION;

SELECT TOP (1) job_id
FROM dbo.Jobs WITH (UPDLOCK, READPAST, ROWLOCK)
WHERE job_status = 'PENDING'
ORDER BY job_id;

-- Cap nhat job da chon trong cung transaction.
ROLLBACK TRANSACTION;
~~~

`READPAST` có thể bỏ qua **các hàng bị khóa** trong một số trường hợp, nhưng có những **giới hạn theo mức cô lập** và không hoàn toàn giống `SKIP LOCKED` PostgreSQL; ví dụ có khác biệt với khóa trang và cấu hình `READ_COMMITTED_SNAPSHOT`. `NOWAIT` hint có thể yêu cầu không chờ khi gặp khóa xung đột. Không nên sao chép máy móc `NOWAIT`/`SKIP LOCKED` thành các hint mà chưa xét điều kiện của T-SQL.

### 17.5. SQLite: không có row-level SELECT FOR UPDATE

SQLite **không hỗ trợ** câu lệnh:

~~~sql
-- KHONG HOP LE trong SQLite:
SELECT *
FROM inventory
WHERE item_id = 101
FOR UPDATE;
~~~

SQLite có mô hình đồng thời khác: một database SQLite thông thường chỉ cho phép **một writer tại một thời điểm**, với cơ chế khóa/giao dịch phụ thuộc journal mode, đặc biệt khác nhau giữa rollback journal và WAL.

Khi cần dành quyền ghi trước khi đọc–quyết định–sửa, có thể dùng transaction dạng `BEGIN IMMEDIATE`:

~~~sql
-- SQLite minh hoa, bang inventory da ton tai.
BEGIN IMMEDIATE;

SELECT stock_qty
FROM inventory
WHERE item_id = 101;

UPDATE inventory
SET stock_qty = stock_qty - 2
WHERE item_id = 101
  AND stock_qty >= 2;

COMMIT;
~~~

`BEGIN IMMEDIATE` bắt đầu transaction với ý định ghi và có thể chặn/không lấy được quyền ghi nếu writer khác đã chiếm; **nó không phải khóa hàng 101 riêng lẻ**. Trong WAL mode, reader có thể vẫn đọc song song với writer theo quy tắc snapshot. SQLite cũng có cơ chế busy timeout; ứng dụng phải xử lý lỗi `SQLITE_BUSY` phù hợp.

Vì vậy đừng cố “dịch cú pháp” `FOR UPDATE` sang SQLite; cần **thiết kế luồng transaction theo mô hình khóa thực tế của SQLite**.

### 17.6. Bảng so sánh nhanh

| Hệ quản trị | Khóa khi đọc để sửa | Không chờ | Bỏ qua hàng bị khóa | Điều cần chú ý |
| --- | --- | --- | --- | --- |
| **PostgreSQL** | `FOR UPDATE`, `FOR NO KEY UPDATE` | `NOWAIT` | `SKIP LOCKED` | MVCC, row-lock modes, transaction và table-level lock đi kèm |
| **MySQL InnoDB** | `FOR UPDATE` | `NOWAIT` ở phiên bản hỗ trợ | `SKIP LOCKED` ở phiên bản hỗ trợ | Khóa bản ghi/khoảng và isolation level |
| **Oracle** | `FOR UPDATE` | `NOWAIT`, `WAIT n` | `SKIP LOCKED` | Quy tắc NOWAIT/WAIT và hạn chế cú pháp của Oracle |
| **SQL Server** | Hint như `UPDLOCK` | Hint `NOWAIT` theo điều kiện | `READPAST` theo điều kiện | Hints, lock escalation, RCSI/isolation, row/page locks |
| **SQLite** | Không có `FOR UPDATE`; transaction ghi | Busy handling, cơ chế transaction | Không tương đương row-level | Một writer; `BEGIN IMMEDIATE` và journal mode |

**Không có một câu SQL `SELECT FOR UPDATE` duy nhất chạy giống nhau trên mọi hệ quản trị.**

## 18. Những lỗi thường gặp

| Lỗi hoặc suy luận | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Chạy `SELECT FOR UPDATE` rồi autocommit, sau đó mới `UPDATE` | Khóa đã giải phóng giữa hai bước | Giữ cùng một transaction tới khi quyết định và ghi xong |
| Coi `FOR UPDATE` là câu sửa dữ liệu | Nó chỉ đọc và xin khóa hàng | Dùng `UPDATE` riêng khi cần thay đổi |
| Coi mọi `SELECT` thường đều chờ khóa của FOR UPDATE | PostgreSQL MVCC thường cho đọc phiên bản đã commit | Phân biệt đọc snapshot với locking read/UPDATE |
| Chỉ mở hai editor tab nhưng thực ra dùng cùng connection | Không có hai transaction độc lập để quan sát tranh chấp | Dùng hai kết nối thực sự khác nhau |
| Quên `ROLLBACK` hoặc `COMMIT` trong phiên A | Transaction giữ khóa quá lâu, các phiên khác bị chờ | Kết thúc transaction ngay sau khi hoàn tất |
| `FOR UPDATE NOWAIT` bị lỗi nhưng vẫn chạy SQL trong transaction PostgreSQL | Transaction sau lỗi có thể ở trạng thái aborted | `ROLLBACK`, rồi bắt đầu giao dịch mới |
| Cho rằng `NOWAIT` bảo đảm không chờ bất kỳ khóa nào | PostgreSQL vẫn có khóa cấp bảng liên quan | Cân nhắc `lock_timeout` và các timeout phù hợp |
| Dùng `SKIP LOCKED` để kiểm kê tổng tồn kho | Hàng đang khóa bị bỏ qua, báo cáo thiếu dữ liệu | Dùng snapshot/báo cáo nhất quán, không skip tùy tiện |
| Cho rằng `SKIP LOCKED` luôn nhận job ID nhỏ nhất | Job ID nhỏ có thể đang khóa | Chấp nhận tính không tuyệt đối hoặc thiết kế chính sách fairness |
| Chọn job rồi commit trước khi đánh dấu RUNNING | Worker khác có thể chọn cùng job | Claim và UPDATE trạng thái cùng transaction |
| Giữ khóa job khi gửi email trong vài phút | Gây tranh chấp và transaction dài | Claim ngắn, commit, xử lý ngoài, hoàn tất ở transaction khác |
| Dùng `SELECT ... FOR UPDATE` trên hàng chưa tồn tại để ngăn INSERT khóa đó trong PostgreSQL | Không có hàng để khóa | `UNIQUE` + `INSERT ... ON CONFLICT` hoặc cơ chế khác |
| Cả A và B khóa hai hàng theo thứ tự đảo nhau | Có thể deadlock | Quy định thứ tự khóa nhất quán, retry |
| Dùng `FOR SHARE` rồi cả hai phiên cùng muốn nâng lên UPDATE | Có thể xung đột, thậm chí deadlock | Chọn mức khóa từ đầu theo luồng ghi |
| Không dùng `OF` khi JOIN rồi ngạc nhiên thấy khóa thêm bảng | Locking clause có thể nhắm nhiều bảng trong phép nối | Dùng `FOR UPDATE OF alias` phù hợp |
| Mang `FOR UPDATE` sang SQL Server/SQLite | Cú pháp/cơ chế khóa không tương đương | Dùng table hints hoặc transaction theo dialect |
| Cho rằng MySQL InnoDB chỉ khóa chính hàng hiển thị | Có thể có gap/next-key locks theo index/isolation | Xem query plan, kiểu khóa và mức cô lập |
| Dùng `EXPLAIN ANALYZE ... FOR UPDATE` vì nghĩ không thực thi | `ANALYZE` thực thi câu đọc có khóa | Dùng `EXPLAIN` không ANALYZE khi chỉ cần kế hoạch |
| Thêm `FOR UPDATE` vào `SELECT SUM(...)` | PostgreSQL không thể trực tiếp khóa hàng tổng hợp như vậy | Khóa hàng nguồn trong bước thích hợp, tổng hợp riêng |

## 19. Bài tập thực hành có đáp án

Các bài dùng hai bảng `lab_lock304_inventory` và `lab_lock304_jobs` của mục 2, trừ khi nêu rõ là ví dụ phương ngữ. Với bài yêu cầu hai phiên, bắt buộc mở **hai kết nối độc lập**. Mọi thao tác thử ghi sử dụng `ROLLBACK` để không làm sai kết quả bài sau.

### Bài 1 — Khóa một sản phẩm

**Yêu cầu:** trong PostgreSQL, đọc tồn kho của sản phẩm ID 103 và giữ khóa hàng cho tới khi transaction kết thúc.

**Đáp án:**

~~~sql
BEGIN;

SELECT item_id, sku, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 103
FOR UPDATE;

ROLLBACK;
~~~

Lệnh đọc trả sản phẩm **MOUSE** có tồn **5** nếu dữ liệu ban đầu chưa đổi. Khóa được giữ giữa `SELECT` và `ROLLBACK`. `FOR UPDATE` tự nó không thay đổi tồn kho.

### Bài 2 — Hai phiên cùng xin khóa một hàng

**Yêu cầu:** A giữ `FOR UPDATE` trên hàng 101; B cũng `FOR UPDATE` hàng 101. B sẽ xảy ra điều gì?

**Đáp án:** B **chờ** cho tới khi A nhả khóa hoặc xảy ra lỗi/timeout. Thực hành:

**A:**

~~~sql
BEGIN;
SELECT item_id FROM lab_lock304_inventory
WHERE item_id = 101 FOR UPDATE;
-- Giu mo transaction.
~~~

**B:**

~~~sql
BEGIN;
SELECT item_id FROM lab_lock304_inventory
WHERE item_id = 101 FOR UPDATE;
~~~

Sau đó A thực hiện `ROLLBACK`, B tiếp tục nhận khóa; kết thúc B bằng `ROLLBACK`.

### Bài 3 — NOWAIT khi hàng đang bị giữ

**Yêu cầu:** khi A đã khóa 101, B phải báo lỗi ngay nếu không lấy được khóa, không đợi.

**Đáp án (phiên B):**

~~~sql
BEGIN;
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE NOWAIT;
-- Du kien loi vi A dang giu khoa.
ROLLBACK;
~~~

Nếu công cụ SQL dừng thực thi cả khối khi câu `SELECT` lỗi, bạn cần chạy `ROLLBACK` riêng sau đó. Cuối cùng giải phóng khóa A. `NOWAIT` không tự chọn hàng khác.

### Bài 4 — SKIP LOCKED trả hàng nào?

**Tình huống:** A đang giữ `FOR UPDATE` trên `item_id = 101`; B chạy:

~~~sql
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id IN (101, 102, 103)
ORDER BY item_id
FOR UPDATE SKIP LOCKED;
~~~

**Đáp án:** nếu không còn khóa xung đột nào khác, B nhận **102 và 103**, bỏ qua 101. Đây **không** phải bằng chứng 101 đã bị xóa. B phải dùng transaction có quản lý phù hợp nếu định cập nhật các hàng vừa lấy.

### Bài 5 — Một SELECT thường có chờ không?

**Câu hỏi:** A giữ `FOR UPDATE` hàng 101 nhưng chưa sửa giá trị. B chạy:

~~~sql
SELECT stock_qty
FROM lab_lock304_inventory
WHERE item_id = 101;
~~~

**Đáp án:** trong PostgreSQL/MVCC với điều kiện thử thông thường, `SELECT` này **không cần chờ khóa hàng FOR UPDATE** để đọc giá trị đã commit. Nếu A còn sửa nhưng chưa commit, B không đọc được giá trị chưa commit của A; B thường thấy phiên bản cũ. Điều này **không cấp cho B quyền sửa mà không tranh khóa**.

### Bài 6 — Khóa trước khi giữ tồn kho

**Yêu cầu:** kiểm tra và giữ 2 chiếc của sản phẩm 105, tăng `reserved_qty` tương ứng. Đảm bảo không trừ tồn khi thiếu hàng.

**Đáp án:**

~~~sql
BEGIN;

SELECT item_id, stock_qty
FROM lab_lock304_inventory
WHERE item_id = 105
FOR UPDATE;

UPDATE lab_lock304_inventory
SET
    stock_qty = stock_qty - 2,
    reserved_qty = reserved_qty + 2
WHERE item_id = 105
  AND stock_qty >= 2
RETURNING item_id, stock_qty, reserved_qty;

ROLLBACK;
~~~

Trong transaction, số lượng từ **3 thành 1** và phần giữ từ **0 thành 2**. Sau `ROLLBACK`, dữ liệu trở về ban đầu.

### Bài 7 — Không cần SELECT FOR UPDATE trong trường hợp nào?

**Yêu cầu:** chỉ muốn trừ 2 sản phẩm ID 105 khi còn đủ, không có bước đọc ra ứng dụng rồi quyết định khác.

**Đáp án:**

~~~sql
BEGIN;

UPDATE lab_lock304_inventory
SET stock_qty = stock_qty - 2
WHERE item_id = 105
  AND stock_qty >= 2
RETURNING item_id, stock_qty;

ROLLBACK;
~~~

`UPDATE` tự thực hiện thao tác ghi có khóa hàng và điều kiện kiểm tra. Với nghiệp vụ chỉ gồm một thay đổi đơn giản, thêm `SELECT FOR UPDATE` riêng không phải lúc nào cũng cần.

### Bài 8 — Claim job bằng SKIP LOCKED

**Yêu cầu:** trong một câu SQL, lấy một job PENDING có thể khóa được rồi đặt thành RUNNING.

**Đáp án:**

~~~sql
BEGIN;

WITH picked AS (
    SELECT job_id
    FROM lab_lock304_jobs
    WHERE job_status = 'PENDING'
    ORDER BY job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE lab_lock304_jobs AS j
SET
    job_status = 'RUNNING',
    attempts = j.attempts + 1,
    claimed_at = CURRENT_TIMESTAMP
FROM picked AS p
WHERE j.job_id = p.job_id
RETURNING j.job_id, j.job_status, j.attempts;

ROLLBACK;
~~~

Khi không có worker khác giữ khóa, chọn **job 1**. Nếu job 1 bị khóa, một job PENDING khác có thể được chọn. `ROLLBACK` phục hồi bảng mẫu.

### Bài 9 — Tranh chấp khóa: chờ hay bỏ qua?

**Yêu cầu:** chọn cơ chế cho mỗi tình huống:

1. Cần xử lý **đúng đơn hàng 101** và sẵn sàng chờ.
2. Cần xử lý đúng hàng 101 nhưng **phải báo bận ngay**.
3. Cần nhận **bất kỳ một job PENDING nào chưa bị giữ**.

**Đáp án:**

| Tình huống | Lựa chọn PostgreSQL |
| --- | --- |
| 1 | `FOR UPDATE`, có thể thêm timeout phù hợp |
| 2 | `FOR UPDATE NOWAIT`, bắt lỗi và rollback khi cần |
| 3 | `FOR UPDATE SKIP LOCKED`, cùng bước đổi trạng thái job trong transaction |

Đặc biệt, không dùng `SKIP LOCKED` ở tình huống 1 rồi coi việc hàng 101 vắng khỏi kết quả là “đơn hàng không tồn tại”.

### Bài 10 — Khóa hai hàng và tránh deadlock

**Yêu cầu:** hai transaction đều cần sửa hàng 101 và 102. Nên quy định thứ tự khóa nào?

**Đáp án:** quy định **mọi luồng nghiệp vụ khóa theo cùng một thứ tự**, ví dụ `item_id ASC`:

~~~sql
BEGIN;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 101
FOR UPDATE;

SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 102
FOR UPDATE;

-- UPDATE cac hang neu nghiep vu yeu cau.
ROLLBACK;
~~~

Nếu mọi nơi thực hiện nhất quán 101 trước 102, giảm nguy cơ vòng chờ trong tình huống cụ thể này. Không khẳng định chỉ việc thêm `ORDER BY` vào một câu truy vấn phức tạp luôn giải quyết mọi deadlock.

### Bài 11 — FOR SHARE so với FOR UPDATE

**Câu hỏi:** hai transaction cùng `SELECT ... FOR SHARE` trên hàng 101 có xung đột với nhau không? Nếu A giữ `FOR SHARE`, B muốn `FOR UPDATE` thì sao?

**Đáp án:** hai khóa `FOR SHARE` trên cùng hàng **tương thích** trong PostgreSQL. Nhưng `FOR UPDATE` **xung đột với `FOR SHARE`**, nên B phải chờ A nhả khóa hoặc xử lý theo `NOWAIT`/timeout tương ứng. Chọn mức khóa phù hợp với việc chỉ đọc bảo vệ hay sắp sửa hàng.

### Bài 12 — FOR UPDATE OF trong JOIN

**Yêu cầu:** một truy vấn JOIN các bảng `orders AS o` và `customers AS c` cần khóa **hàng đơn hàng**, không muốn xin khóa FOR UPDATE trên khách hàng. Viết phần khóa cho PostgreSQL.

**Đáp án minh họa:**

~~~sql
-- Chi chay neu bang orders va customers ton tai.
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 1001
FOR UPDATE OF o;
~~~

`FOR UPDATE OF o` nhắm vào hàng của bảng bí danh `o`. Bảng `customers` vẫn được đọc để nối, nhưng không bị yêu cầu cùng mức khóa hàng FOR UPDATE chỉ vì tham gia JOIN.

### Bài 13 — Đổi cú pháp sang SQL Server

**Yêu cầu:** trong T-SQL, cách đọc chuẩn bị sửa hàng có thể viết thế nào khi không có `SELECT ... FOR UPDATE`?

**Đáp án minh họa:**

~~~sql
BEGIN TRANSACTION;

SELECT item_id, stock_qty
FROM dbo.Inventory WITH (UPDLOCK, ROWLOCK)
WHERE item_id = 101;

ROLLBACK TRANSACTION;
~~~

`UPDLOCK` là hint khóa update; `ROWLOCK` là gợi ý độ hạt. Không coi nó là bản sao hoàn toàn của PostgreSQL `FOR UPDATE`; cần kiểm tra mức cô lập, index, cấu hình database và khả năng tranh chấp thực tế.

### Bài 14 — SQLite có FOR UPDATE không?

**Câu hỏi:** nếu ứng dụng dùng SQLite, có thể chạy `SELECT ... FOR UPDATE NOWAIT` hay không? Nếu cần dành quyền ghi trước khi cập nhật, nên xem xét gì?

**Đáp án:** SQLite **không hỗ trợ cú pháp `FOR UPDATE`**. Có thể dùng transaction thích hợp như:

~~~sql
BEGIN IMMEDIATE;
SELECT stock_qty FROM inventory WHERE item_id = 101;
UPDATE inventory
SET stock_qty = stock_qty - 1
WHERE item_id = 101 AND stock_qty >= 1;
COMMIT;
~~~

`BEGIN IMMEDIATE` liên quan quyền ghi của database SQLite, **không** tạo khóa hàng riêng cho ID 101. Ứng dụng cần xử lý `SQLITE_BUSY`, transaction và chế độ WAL/journal phù hợp.

### Bài 15 — Vì sao SELECT FOR UPDATE không khóa được hàng chưa có?

**Tình huống:** hai phiên PostgreSQL cùng chạy:

~~~sql
SELECT item_id
FROM lab_lock304_inventory
WHERE item_id = 999
FOR UPDATE;
~~~

cả hai không thấy hàng. Có thể kết luận “chắc chắn không phiên nào có thể INSERT 999” không?

**Đáp án:** **không**. Vì chưa có hàng 999 để khóa, truy vấn này không bảo vệ độc quyền sự vắng mặt của khóa trong PostgreSQL. Muốn bảo đảm chỉ có một hàng với `item_id = 999`, cần `PRIMARY KEY`/`UNIQUE` và thao tác chèn/giải quyết xung đột nguyên tử, hoặc một chiến lược giao dịch khác phù hợp.

## 20. Ghi nhớ

| Nhu cầu | Cách tiếp cận tiêu biểu |
| --- | --- |
| Đọc một hàng để quyết định sửa trong cùng transaction | PostgreSQL: `SELECT ... FOR UPDATE` |
| Không đứng chờ hàng đã bị giữ | `FOR UPDATE NOWAIT`; ứng dụng bắt lỗi và rollback phù hợp |
| Chọn job chưa bị worker khác giữ | `FOR UPDATE SKIP LOCKED`, kết hợp UPDATE trạng thái trong cùng transaction |
| Chờ khóa nhưng có giới hạn thời gian | PostgreSQL: `SET LOCAL lock_timeout = '...'` trong transaction |
| Khóa nhẹ hơn để sửa không làm đổi khóa | `FOR NO KEY UPDATE` |
| Khóa đọc chia sẻ | `FOR SHARE` hoặc `FOR KEY SHARE` tùy bất biến cần bảo vệ |
| Chỉ khóa một bảng khi JOIN | `FOR UPDATE OF alias` |
| Giữ khóa qua nhiều câu lệnh | `BEGIN`, các thao tác liên quan, `COMMIT`/`ROLLBACK` |
| Chỉ giảm tồn nếu đủ mà không cần logic đọc thêm | `UPDATE ... SET stock_qty = stock_qty - n WHERE stock_qty >= n RETURNING ...` |
| Giảm deadlock | Khóa theo thứ tự thống nhất, transaction ngắn, retry khi cần |
| MySQL InnoDB | `FOR UPDATE` có thêm lưu ý về index, gap/next-key locks và isolation |
| Oracle | `FOR UPDATE`, `NOWAIT`, `WAIT n`, `SKIP LOCKED` theo cú pháp Oracle |
| SQL Server | Lock hints như `UPDLOCK`, `READPAST`, `NOWAIT` trong điều kiện phù hợp |
| SQLite | Không có row-level `FOR UPDATE`; sử dụng transaction như `BEGIN IMMEDIATE` theo mô hình một writer |

**Điểm cốt lõi:** `SELECT FOR UPDATE` không phải “câu SELECT mạnh hơn cho mọi hoàn cảnh”. Nó là công cụ để **đọc và giữ quyền thao tác trên những hàng liên quan trong một transaction**, tránh các quyết định ghi dựa trên trạng thái đã thay đổi đồng thời. Dùng `NOWAIT` khi cần báo bận nhanh, `SKIP LOCKED` khi các hàng có thể được xử lý thay thế cho nhau (như queue), và dùng mức khóa phù hợp với thao tác thật sự. Khi chuyển giữa các hệ quản trị, hãy chuyển **quy tắc đồng thời cần đạt được**, không chỉ chuyển từ khóa SQL.

# Khóa hàng hiện có và bảo vệ khoảng giá trị chưa có hàng

Khi một giao dịch khóa một hàng, DBMS có thể ngăn giao dịch khác sửa hoặc xóa chính hàng đó cho đến khi khóa được giải phóng. Nhưng nhiều quy tắc nghiệp vụ phụ thuộc vào **một tập hàng được xác định bằng điều kiện truy vấn**, kể cả những hàng chưa tồn tại.

Ví dụ, một giao dịch kiểm tra rằng chưa có đơn hàng nào trong khoảng số `1000` đến `1099`, rồi tạo đơn hàng `1050`. Nếu giao dịch khác cũng kiểm tra cùng khoảng trước khi giao dịch thứ nhất commit, cả hai có thể cùng thấy khoảng đó đang trống. Khóa những hàng hiện có không đủ bảo vệ trường hợp này vì trong khoảng đang trống không có hàng nào để khóa.

Để xử lý, một số cơ chế đồng thời bảo vệ cả **khoảng khóa (key range)** hoặc theo dõi **điều kiện đọc (predicate)**. Khi đó, DBMS có thể ngăn một giao dịch chèn giá trị mới vào khoảng đang được bảo vệ, hoặc phát hiện phụ thuộc nguy hiểm và hủy một giao dịch. Cách thực hiện khác nhau giữa các hệ quản trị.

## 1. Khóa hàng hiện có chưa bảo vệ được hàng sẽ được chèn

Giả sử bảng `Orders` có các hàng sau:

| order_no | status |
|---:|---|
| 1000 | CLOSED |
| 1020 | OPEN |
| 1100 | OPEN |

Giao dịch A cần kiểm tra và xử lý các đơn hàng có số từ `1030` đến `1090`. Trong khoảng này hiện chưa có hàng nào. Giao dịch B muốn chèn đơn hàng `1050`.

Nếu A chỉ khóa các hàng đã tìm thấy, A không khóa được `1050` vì hàng đó chưa tồn tại. B có thể chèn hàng mới trong khi A vẫn đang xử lý. Khi A truy vấn lại hoặc commit, tập hàng thỏa điều kiện có thể đã thay đổi.

```text
Trạng thái ban đầu của chỉ mục order_no:

       1000             1020                         1100
         |                |                            |
---------+----------------+----------------------------+---->
                          [ khoảng 1030..1090 ]
                          chưa có khóa hàng để khóa

Giao dịch A: đọc khoảng 1030..1090, thấy rỗng
Giao dịch B: chèn order_no = 1050
Giao dịch A: tiếp tục với giả định khoảng vẫn rỗng
```

Đây là một trường hợp của **phantom read**: cùng một truy vấn theo điều kiện có thể trả về tập hàng khác nhau trong một giao dịch vì giao dịch khác đã chèn hoặc xóa hàng thỏa điều kiện. Vấn đề không chỉ nằm ở giá trị của một hàng cụ thể; nó nằm ở sự thay đổi thành viên của tập kết quả.

Khóa hàng hiện có và bảo vệ khoảng giá trị giải quyết hai phạm vi khác nhau:

- **Khóa hàng (row lock):** bảo vệ một bản ghi đã tồn tại, thường thông qua bản ghi hoặc mục chỉ mục tương ứng.
- **Khóa khoảng (range/gap protection):** bảo vệ một đoạn trong thứ tự chỉ mục, bao gồm vị trí mà một giá trị mới có thể được chèn vào.

Không phải DBMS nào cũng dùng khóa khoảng chặn việc chèn. Một số hệ thống dùng khóa khoảng; PostgreSQL dùng cơ chế theo dõi predicate trong Serializable Snapshot Isolation để phát hiện xung đột mà không chặn mọi thao tác chèn ngay từ đầu.

## 2. Khoảng khóa được xác định như thế nào?

Khoảng khóa thường được hiểu dựa trên thứ tự của một chỉ mục. Giả sử chỉ mục có các khóa `10`, `20`, `30`. Các vị trí giữa những khóa này tạo thành những khoảng mà giá trị mới có thể xuất hiện:

```text
       gap          gap          gap          gap
        |            |            |            |
   -----+-----10-----+-----20-----+-----30-----+----->
      trước 10     (10,20)      (20,30)       sau 30
```

Đây là sơ đồ khái niệm. DBMS có thể biểu diễn biên khoảng bằng khóa chỉ mục, sentinel hoặc cấu trúc nội bộ riêng. Một khoảng có thể mở, đóng hoặc được xác định theo điều kiện truy vấn; cách xử lý giá trị bằng đúng biên phụ thuộc ngữ nghĩa so sánh và kế hoạch truy cập.

Ví dụ:

```sql
SELECT *
FROM Orders
WHERE order_no >= 1030
  AND order_no < 1090;
```

Truy vấn này xác định một khoảng theo `order_no`. Nếu có chỉ mục phù hợp trên cột đó, DBMS có thể xác định các mục chỉ mục và khoảng trống liên quan mà không cần xem toàn bộ bảng. Một giao dịch khác muốn chèn `order_no = 1050` sẽ đi vào khoảng mà giao dịch đọc đang bảo vệ, nếu cơ chế và mức cô lập của DBMS yêu cầu bảo vệ phantom.

Khoảng khóa không nhất thiết tương ứng với một đoạn byte liên tục trong tệp dữ liệu. Nó là phạm vi logic trong thứ tự chỉ mục. Hai hàng nằm gần nhau về thứ tự chỉ mục có thể nằm ở các trang vật lý khác nhau; ngược lại, nhiều hàng khác nhau có thể cùng nằm trên một trang vật lý.

## 3. Vì sao chỉ mục ảnh hưởng đến phạm vi khóa?

DBMS thường dùng chỉ mục để tìm các giá trị thỏa điều kiện và xác định vị trí cần bảo vệ. Do đó, chỉ mục được chọn có ảnh hưởng lớn đến phạm vi và số lượng khóa.

### 3.1. Chỉ mục phù hợp giúp giới hạn khoảng

Giả sử truy vấn thường xuyên kiểm tra đơn hàng theo `order_no`:

```sql
CREATE INDEX ix_orders_order_no ON Orders(order_no);
```

Khi thực hiện truy vấn khoảng trên `order_no`, DBMS có thể đi theo thứ tự của chỉ mục và xác định đoạn cần khóa hoặc theo dõi. Nếu không có chỉ mục phù hợp, DBMS có thể phải quét nhiều hàng. Phạm vi khóa thực tế có thể rộng hơn dự kiến, thậm chí tạo ra tranh chấp gần như trên toàn bảng tùy cơ chế của hệ quản trị.

### 3.2. Chỉ mục ghép và thứ tự từ điển

Với chỉ mục ghép:

```sql
CREATE INDEX ix_orders_status_created
ON Orders(status, created_at);
```

Thứ tự chỉ mục được sắp xếp theo `status` trước, rồi mới đến `created_at` trong cùng giá trị `status`. Truy vấn:

```sql
SELECT *
FROM Orders
WHERE status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00';
```

có thể sử dụng đoạn chỉ mục tương ứng với `status = 'OPEN'` và khoảng thời gian trong nhóm đó. Nếu điều kiện không khớp với thứ tự cột của chỉ mục, DBMS có thể phải quét phạm vi lớn hơn hoặc chọn chỉ mục khác.

Vì vậy, khi điều tra khóa khoảng, cần xem kế hoạch thực thi (`EXPLAIN` hoặc công cụ tương ứng), thứ tự cột trong chỉ mục và điều kiện lọc thực tế. Không thể kết luận phạm vi khóa chỉ từ câu SQL mà bỏ qua đường truy cập.

### 3.3. Chỉ mục không thay thế quy tắc đồng thời

Tạo chỉ mục giúp DBMS tìm phạm vi hiệu quả và có thể giảm số tài nguyên phải quét. Tuy nhiên, chỉ mục tự nó không bảo vệ phantom ở mọi mức cô lập. DBMS phải có quy tắc khóa hoặc phát hiện phụ thuộc phù hợp với mức cô lập đang dùng.

## 4. Khóa khoảng và phantom read

Phantom read xảy ra khi một giao dịch chạy lại truy vấn theo cùng điều kiện và nhận được tập hàng khác vì một giao dịch khác đã commit thay đổi làm hàng mới thỏa hoặc không còn thỏa điều kiện.

Ví dụ, giao dịch A kiểm tra số lượng đơn hàng `OPEN` trong một khoảng ngày:

```sql
SELECT COUNT(*)
FROM Orders
WHERE status = 'OPEN'
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01';
```

Trong khi A đang thực hiện nghiệp vụ, giao dịch B chèn một đơn hàng `OPEN` trong tháng 11. Nếu A chạy lại câu lệnh, số lượng có thể tăng. Việc khóa các hàng mà A đã tìm thấy không nhất thiết ngăn B chèn một hàng mới.

Khóa khoảng giải quyết vấn đề bằng cách bảo vệ phạm vi giá trị mà điều kiện truy vấn mô tả. Tùy DBMS, thao tác chèn có thể phải chờ khóa khoảng được giải phóng. Với cơ chế phát hiện xung đột, thao tác có thể chạy tiếp nhưng một giao dịch sẽ bị hủy khi DBMS xác định lịch không còn an toàn.

Điều cần bảo vệ là **tập kết quả của predicate**, chứ không chỉ các hàng đang nằm trong tập đó. Predicate có thể là điều kiện đơn giản như `order_no BETWEEN 1030 AND 1090`, hoặc điều kiện kết hợp nhiều cột như `status = 'OPEN' AND created_at >= ...`.

## 5. InnoDB: gap lock và next-key lock

InnoDB của MySQL dùng khóa bản ghi chỉ mục và, trong những tình huống phù hợp, khóa khoảng (gap lock) hoặc khóa next-key để ngăn phantom.

### 5.1. Gap lock

Gap lock bảo vệ khoảng nằm giữa các mục chỉ mục. Mục tiêu chính của nó là ngăn giao dịch khác chèn khóa chỉ mục mới vào khoảng đó. Nó không phải khóa một hàng đang tồn tại.

Ví dụ, chỉ mục có các giá trị `10`, `20`, `30`. Một giao dịch có thể giữ khóa trên khoảng `(10,20)` để ngăn giao dịch khác chèn `15` vào khoảng đó trong thời gian khóa còn hiệu lực.

### 5.2. Next-key lock

Next-key lock kết hợp khóa bản ghi chỉ mục với khoảng ngay trước bản ghi đó. Có thể hình dung:

```text
Next-key lock trên key 20:

       khoảng (10,20] được bảo vệ
   -----------[ 20 ]-------------------->
        gap       record
```

Trong InnoDB, khóa next-key là cơ chế quan trọng để khóa phạm vi khi thực hiện locking read, `UPDATE` hoặc `DELETE` theo điều kiện trong các mức cô lập phù hợp. Nó có thể bảo vệ cả bản ghi hiện có lẫn vị trí chèn liên quan trong thứ tự chỉ mục.

### 5.3. Ví dụ locking read

Với InnoDB, có thể thực hiện truy vấn khóa trong transaction:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM Orders
WHERE order_no >= 1030
  AND order_no < 1090
FOR UPDATE;

-- Kiểm tra trạng thái và thực hiện cập nhật liên quan.

COMMIT;
```

Trong `REPEATABLE READ`, InnoDB có thể dùng next-key/gap locks trên phạm vi chỉ mục được quét để bảo vệ khỏi phantom. Một giao dịch khác muốn chèn khóa chỉ mục nằm trong phạm vi bị khóa có thể phải chờ.

Phạm vi khóa phụ thuộc chỉ mục và kế hoạch truy cập. Nếu truy vấn không có chỉ mục phù hợp và phải quét nhiều hàng, số lượng tài nguyên bị khóa có thể lớn. Với tìm kiếm bằng điều kiện duy nhất trên một khóa duy nhất đã tồn tại, InnoDB thường chỉ cần khóa bản ghi tương ứng, không cần khóa gap trước bản ghi đó. Các trường hợp tìm kiếm không tìm thấy bản ghi, khóa phạm vi và điều kiện cô lập cần được xem xét theo đúng phiên bản và kế hoạch thực thi.

### 5.4. Ảnh hưởng của isolation level

Trong InnoDB, `REPEATABLE READ` là mức mặc định phổ biến của MySQL và dùng next-key locking cho nhiều thao tác khóa theo phạm vi. Ở `READ COMMITTED`, gap locking thường được tắt cho locking read, `UPDATE` và `DELETE`, ngoại trừ một số trường hợp như kiểm tra khóa ngoại và khóa trùng lặp. Vì vậy, thay đổi isolation level có thể làm thay đổi khả năng chèn vào khoảng đang được đọc.

Không nên suy luận rằng mọi `SELECT` thông thường đều khóa khoảng. Muốn thực hiện locking read, câu lệnh thường cần `FOR UPDATE` hoặc `FOR SHARE` theo mục đích và cú pháp phiên bản MySQL. Một truy vấn đọc snapshot thông thường dưới MVCC có hành vi khác với locking read.

## 6. SQL Server: key-range lock

SQL Server hỗ trợ khóa khoảng khóa (key-range lock) để ngăn phantom khi giao dịch chạy ở mức cô lập `SERIALIZABLE`. DBMS dùng chỉ mục để biểu diễn khoảng khóa và phối hợp với khóa trên các khóa chỉ mục.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT order_no, status
FROM dbo.Orders
WHERE order_no >= 1030
  AND order_no < 1090;

-- Thực hiện kiểm tra và thay đổi nghiệp vụ.

COMMIT TRANSACTION;
```

Nếu có chỉ mục phù hợp trên `order_no`, SQL Server có thể lấy các khóa khoảng trên đoạn chỉ mục liên quan. Một giao dịch khác cố chèn `order_no = 1050` có thể phải chờ đến khi giao dịch A kết thúc.

SQL Server có các chế độ key-range lock như `RangeS-S`, `RangeS-U` và các chế độ liên quan đến chèn. Tên chế độ cho biết cách DBMS phối hợp khóa khoảng với khóa trên khóa chỉ mục. Ở mức sử dụng ứng dụng, điều quan trọng là `SERIALIZABLE` bảo vệ cả hàng hiện có và khoảng có thể xuất hiện phantom.

`HOLDLOCK` là gợi ý có ngữ nghĩa tương đương `SERIALIZABLE` cho tham chiếu bảng trong câu lệnh tương ứng. Ví dụ:

```sql
BEGIN TRANSACTION;

SELECT order_no
FROM dbo.Orders WITH (HOLDLOCK)
WHERE order_no >= 1030
  AND order_no < 1090;

-- Công việc cần được bảo vệ...

COMMIT TRANSACTION;
```

Phạm vi khóa thực tế vẫn phụ thuộc chỉ mục, kế hoạch thực thi, các khóa khác và mức cô lập. Nếu không có chỉ mục thích hợp, SQL Server có thể phải dùng phạm vi khóa rộng hơn hoặc khóa nhiều tài nguyên hơn dự kiến. Có thể dùng `sys.dm_tran_locks` cùng các DMV liên quan để quan sát khóa trong môi trường kiểm thử.

## 7. PostgreSQL: predicate lock và SSI

PostgreSQL có cách tiếp cận khác. Ở mức cô lập `SERIALIZABLE`, PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để phát hiện các phụ thuộc đọc-ghi có thể làm lịch giao dịch không tuần tự hóa được.

PostgreSQL có predicate lock, thường hiển thị với mode `SIReadLock`, để ghi nhận vùng dữ liệu mà giao dịch serializable đã đọc. Các khóa này phục vụ theo dõi xung đột; chúng không hoạt động như khóa chặn thông thường và không trực tiếp ngăn giao dịch khác chèn vào khoảng đó.

Ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT order_no, status
FROM orders
WHERE order_no >= 1030
  AND order_no < 1090;

-- Kiểm tra và cập nhật dữ liệu liên quan.

COMMIT;
```

Giao dịch khác có thể chèn một hàng thỏa điều kiện trong khi giao dịch trên đang chạy. PostgreSQL theo dõi phụ thuộc giữa thao tác đọc và ghi. Nếu các phụ thuộc tạo ra cấu trúc nguy hiểm có thể vi phạm khả tuần tự, một giao dịch có thể bị hủy với lỗi serialization failure (`SQLSTATE 40001`). Ứng dụng cần retry toàn bộ transaction theo chính sách phù hợp.

Một điểm cần nhớ: `SELECT ... FOR UPDATE` trong PostgreSQL khóa các hàng được tìm thấy. Nó không tạo khóa gap theo cách của InnoDB để chặn mọi hàng chưa tồn tại trong khoảng. Muốn bảo đảm khả tuần tự cho quy tắc dựa trên predicate, cần dùng mức `SERIALIZABLE` và xử lý lỗi serialization theo hướng dẫn của PostgreSQL.

## 8. So sánh cách bảo vệ khoảng giữa các DBMS

| DBMS | Cơ chế điển hình | Cách xử lý thao tác chèn vào khoảng | Điều cần chú ý |
|---|---|---|---|
| MySQL InnoDB | Gap lock và next-key lock | Có thể chặn thao tác chèn vào gap đang bị khóa | Phụ thuộc isolation level, chỉ mục và kế hoạch truy cập; `READ COMMITTED` giảm phần lớn gap locking |
| SQL Server | Key-range lock ở `SERIALIZABLE` | Có thể chặn chèn vào khoảng được bảo vệ | Cần xem index và kế hoạch thực thi; phạm vi có thể rộng khi thiếu index phù hợp |
| PostgreSQL | Predicate lock và SSI ở `SERIALIZABLE` | Thường cho phép thao tác chạy, rồi phát hiện phụ thuộc và có thể hủy một transaction | Predicate lock dùng để theo dõi, không phải khóa chặn; ứng dụng phải retry lỗi serialization |

Không nên dùng các tên “gap lock”, “next-key lock”, “key-range lock” và “predicate lock” như thể chúng là một cơ chế giống hệt nhau. Chúng cùng hướng tới bảo vệ quy tắc phụ thuộc vào phạm vi dữ liệu, nhưng thời điểm và cách xử lý xung đột khác nhau.

## 9. Khóa hàng, khóa khoảng và ràng buộc UNIQUE

Một quy tắc đơn giản như “mỗi khách hàng chỉ có một hóa đơn cho một kỳ” thường nên được bảo vệ bằng ràng buộc duy nhất:

```sql
ALTER TABLE Invoice
ADD CONSTRAINT uq_invoice_customer_period
UNIQUE (customer_id, invoice_period);
```

Constraint `UNIQUE` là hàng rào dữ liệu do DBMS thực thi. Nếu hai giao dịch cùng chèn một cặp giá trị, tối đa một giao dịch có thể tạo bản ghi hợp lệ; giao dịch còn lại nhận lỗi trùng khóa hoặc kết quả tương ứng.

Khóa khoảng có phạm vi rộng hơn một khóa duy nhất cụ thể. Nó hữu ích khi nghiệp vụ phụ thuộc vào một tập điều kiện, ví dụ:

- Không được có hai đặt chỗ trùng thời gian cho cùng phòng.
- Không được chèn đơn hàng mới vào một dải số đang được chốt.
- Không được vượt quá giới hạn số bản ghi thỏa điều kiện trong một khoảng.
- Một giao dịch cần bảo đảm rằng tập kết quả truy vấn không thay đổi trước khi hoàn tất.

Một số DBMS hỗ trợ constraint mạnh hơn, chẳng hạn exclusion constraint của PostgreSQL cho các quy tắc không chồng lấn trên range. Nếu quy tắc có thể biểu diễn bằng constraint, đó thường là cơ chế bảo vệ đáng tin cậy vì nó áp dụng cho mọi đường ghi. Khóa khoảng và mức `SERIALIZABLE` là các công cụ kiểm soát giao dịch cho những quy tắc rộng hơn.

## 10. Tình huống minh họa: giới hạn số chỗ đặt

Giả sử một lớp học chỉ được có tối đa 20 học viên. Hai giao dịch cùng đọc số học viên hiện tại là 19, rồi mỗi giao dịch đăng ký thêm một người.

```text
Giao dịch A                         Giao dịch B
-----------                         -----------
Đếm học viên = 19                   Đếm học viên = 19
Thấy còn 1 chỗ                      Thấy còn 1 chỗ
Chèn học viên A                     Chèn học viên B
Commit                              Commit

Kết quả: 21 học viên (vượt giới hạn)
```

Nếu chỉ khóa các hàng học viên hiện có, hai giao dịch có thể cùng đọc 19 hàng và chèn hai hàng mới khác nhau. Khóa hàng riêng lẻ không nhất thiết bảo vệ điều kiện tổng số lượng.

Có một số cách xử lý:

1. Dùng mức `SERIALIZABLE` với cơ chế bảo vệ predicate phù hợp của DBMS để các giao dịch xung đột không thể cùng commit.
2. Tạo một hàng `ClassCapacity` cho lớp học và cập nhật số chỗ bằng một câu lệnh nguyên tử có điều kiện, ví dụ chỉ tăng `enrolled_count` nếu giá trị hiện tại nhỏ hơn 20. Hàng tổng hợp trở thành điểm đồng bộ rõ ràng.
3. Dùng một cơ chế khóa nghiệp vụ chung theo `class_id`, bảo đảm mọi luồng đăng ký đều lấy khóa trước khi kiểm tra và ghi. Constraint vẫn nên bảo vệ các quy tắc có thể biểu diễn trong schema.

Ví dụ cập nhật nguyên tử:

```sql
UPDATE ClassCapacity
SET enrolled_count = enrolled_count + 1
WHERE class_id = 7
  AND enrolled_count < capacity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu bằng 1, chỗ đã được giữ thành công; nếu bằng 0, lớp đã đủ chỗ hoặc không tồn tại. Việc tạo bản ghi đăng ký và tăng bộ đếm phải nằm trong cùng transaction để không tạo ra sai lệch giữa bộ đếm và danh sách học viên.

## 11. Cách kiểm tra hành vi khóa khoảng

Khi cần xác định một DBMS có bảo vệ khoảng hay không, nên dùng hai session độc lập trong môi trường thử nghiệm và một chỉ mục rõ ràng.

Một quy trình kiểm tra khái niệm:

1. Tạo bảng và chỉ mục trên cột được truy vấn theo khoảng.
2. Chèn một vài khóa nằm hai phía của khoảng kiểm tra, để khoảng ở giữa chưa có hàng.
3. Ở session A, bắt đầu transaction và thực hiện truy vấn với isolation level hoặc locking clause cần kiểm tra.
4. Giữ transaction A mở.
5. Ở session B, thử chèn một giá trị nằm trong khoảng.
6. Quan sát B bị chặn, được phép tiếp tục hay sau đó nhận lỗi serialization.
7. Commit/rollback session A và quan sát session B tiếp tục như thế nào.
8. Thử lại với isolation level khác và kế hoạch truy vấn khác để so sánh.

Khi đọc kết quả, cần phân biệt:

- B đang chờ một khóa dữ liệu hoặc khóa khoảng.
- B đã chèn thành công nhưng A có thể bị hủy khi commit.
- B bị từ chối do constraint như `UNIQUE`.
- B chờ do một khóa khác không liên quan trực tiếp đến predicate đang kiểm tra.

Các công cụ quan sát tùy DBMS. MySQL có thông tin lock wait và transaction của InnoDB; SQL Server có `sys.dm_tran_locks` và thông tin blocking; PostgreSQL có `pg_locks`, trong đó predicate lock có thể xuất hiện dưới dạng `SIReadLock`, cùng với log lỗi serialization. Không nên chỉ dựa vào thời gian truy vấn để kết luận loại khóa.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Khóa tất cả hàng tìm thấy là đủ để bảo vệ truy vấn theo điều kiện. | Hàng mới có thể được chèn vào khoảng và thỏa điều kiện; cần bảo vệ khoảng hoặc phát hiện phụ thuộc predicate. |
| Khoảng khóa là một hàng đặc biệt trong bảng. | Nó là phạm vi logic trong thứ tự chỉ mục, có thể bao gồm vị trí chưa có hàng. |
| Mọi DBMS đều dùng gap lock. | InnoDB có gap/next-key lock; SQL Server có key-range lock; PostgreSQL SSI theo dõi predicate bằng cơ chế khác. |
| PostgreSQL `FOR UPDATE` khóa cả khoảng. | Nó khóa các hàng được tìm thấy; bảo đảm predicate ở `SERIALIZABLE` dựa trên SSI và có thể hủy giao dịch. |
| Chỉ mục luôn làm phạm vi khóa nhỏ. | Chỉ mục phù hợp có thể thu hẹp phạm vi; chỉ mục không phù hợp hoặc full scan có thể làm phạm vi tranh chấp rộng hơn. |
| `READ COMMITTED` luôn ngăn phantom. | Nhiều DBMS cho phép phantom ở mức này; hành vi cụ thể tùy sản phẩm và cơ chế đọc. |
| Khóa khoảng và UNIQUE constraint thay thế được nhau. | UNIQUE bảo vệ một quy tắc duy nhất cụ thể; khóa khoảng bảo vệ một phạm vi hoặc predicate trong giao dịch. |
| PostgreSQL predicate lock sẽ chặn thao tác INSERT. | Predicate lock trong SSI chủ yếu ghi nhận phụ thuộc; xung đột có thể được xử lý bằng cách hủy một giao dịch. |

## 13. Cách lựa chọn cơ chế bảo vệ

Khi một nghiệp vụ phụ thuộc vào dữ liệu có thể chưa tồn tại, hãy xác định trước phạm vi điều kiện cần bảo vệ. Nếu quy tắc chỉ liên quan đến một hàng đã có, khóa hàng có thể phù hợp. Nếu quy tắc liên quan đến mọi giá trị trong một khoảng hoặc mọi hàng thỏa predicate, cần cơ chế bảo vệ khoảng hoặc phát hiện phụ thuộc tương ứng với DBMS và isolation level.

Sau đó, kiểm tra chỉ mục mà DBMS thực sự dùng. Chỉ mục quyết định thứ tự khóa và có thể làm thay đổi phạm vi tài nguyên được quét. Cuối cùng, xác định xung đột sẽ được xử lý bằng chờ khóa hay bằng cách hủy một giao dịch; ứng dụng phải có timeout, xử lý lỗi và retry toàn bộ transaction khi cần.

Khóa hàng bảo vệ bản ghi đang tồn tại. Khóa khoảng và cơ chế predicate mở rộng khả năng kiểm soát đến cả những giá trị chưa có hàng. Hiểu rõ sự khác biệt này giúp tránh phantom, thiết kế chỉ mục đúng với truy vấn và lựa chọn mức cô lập phù hợp cho từng quy tắc nghiệp vụ.

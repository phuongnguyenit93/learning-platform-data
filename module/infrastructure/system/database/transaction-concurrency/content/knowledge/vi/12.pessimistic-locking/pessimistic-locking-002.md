# Đọc kèm khóa để bảo vệ chuỗi đọc–kiểm tra–cập nhật

Một thao tác nghiệp vụ thường không chỉ gồm một câu lệnh ghi. Ứng dụng có thể phải **đọc trạng thái hiện tại, kiểm tra điều kiện, rồi mới cập nhật dữ liệu**. Ví dụ, trước khi trừ tồn kho để xác nhận đơn hàng, hệ thống phải đọc số lượng còn lại và kiểm tra rằng số lượng đó đủ đáp ứng yêu cầu.

Nếu hai giao dịch cùng thực hiện chuỗi thao tác này, cả hai có thể đọc cùng một giá trị cũ và cùng cho rằng điều kiện vẫn thỏa mãn. Khi đó, kết quả ghi cuối cùng có thể vi phạm quy tắc nghiệp vụ. Một cách bảo vệ là dùng **locking read (đọc kèm khóa)**: giao dịch lấy khóa trên dữ liệu cần kiểm tra ngay trong lúc đọc, giữ khóa trong suốt phần kiểm tra và cập nhật, rồi chỉ giải phóng khóa khi giao dịch kết thúc.

Trong SQL, cú pháp thường gặp là `SELECT ... FOR UPDATE`. Ý nghĩa và phạm vi khóa cụ thể phụ thuộc DBMS, isolation level và chỉ mục. Vì vậy, cần hiểu cả nguyên tắc lẫn cách hệ quản trị cơ sở dữ liệu triển khai.

## 1. Vấn đề: chuỗi đọc–kiểm tra–cập nhật có thể bị xen ngang

Giả sử bảng `inventory` lưu số lượng hàng có thể bán:

| product_id | available |
|---:|---:|
| 42 | 5 |

Hai khách hàng gần như đồng thời đặt mua 4 sản phẩm. Mỗi yêu cầu phải bảo đảm số lượng tồn kho không âm.

Một cách triển khai ngây thơ là:

1. Đọc `available`.
2. Kiểm tra `available >= quantity`.
3. Nếu đủ, ghi `available = available - quantity`.

Nếu cả hai giao dịch đọc giá trị `5` trước khi có giao dịch nào cập nhật, cả hai đều vượt qua bước kiểm tra. Sau đó, chúng có thể cùng xác nhận hai đơn hàng, dù tổng nhu cầu là 8 trong khi kho chỉ có 5.

Lịch thực thi minh họa:

```text
T1: đọc available = 5
T2: đọc available = 5
T1: kiểm tra 5 >= 4  → đạt
T2: kiểm tra 5 >= 4  → đạt
T1: ghi available = 1
T2: ghi theo giá trị đã đọc trước đó
```

Tùy cách câu lệnh cập nhật được viết và cơ chế concurrency control của DBMS, kết quả có thể là lost update, hai đơn cùng được xác nhận hoặc một giao dịch bị lỗi. Dù biểu hiện cụ thể ra sao, lỗi thiết kế nằm ở chỗ **quyết định nghiệp vụ được đưa ra từ một giá trị có thể đã lỗi thời trước khi cập nhật hoàn tất**.

## 2. Locking read là gì?

Một truy vấn đọc thông thường có thể chỉ lấy dữ liệu theo snapshot/MVCC mà không giữ khóa ngăn giao dịch khác cập nhật hàng đó. Một locking read yêu cầu DBMS đồng thời khóa những hàng được đọc theo chế độ khóa đã chỉ định.

Với câu lệnh:

```sql
SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;
```

giao dịch yêu cầu khóa phù hợp để bảo vệ hàng tồn kho khỏi các cập nhật xung đột trong lúc giao dịch đang xử lý. Một giao dịch khác muốn cập nhật hoặc lấy khóa xung đột trên hàng đó thường phải chờ cho đến khi khóa được giải phóng, hoặc nhận lỗi nếu truy vấn sử dụng chế độ không chờ.

Khóa được giữ ở cấp giao dịch. Việc câu lệnh `SELECT` kết thúc không có nghĩa khóa đã được nhả. Khóa thường được giải phóng khi giao dịch `COMMIT` hoặc `ROLLBACK` hoàn tất.

### Khác nhau giữa đọc thường và đọc kèm khóa

| Đặc điểm | Đọc thường | Đọc kèm khóa `FOR UPDATE` |
|---|---|---|
| Mục đích | Quan sát dữ liệu | Đọc dữ liệu để chuẩn bị thay đổi hoặc bảo vệ quyết định |
| Có yêu cầu khóa xung đột trên hàng được đọc? | Thường không theo cách ngăn ghi của giao dịch khác trong mô hình MVCC | Có, theo chế độ khóa của DBMS |
| Giao dịch ghi cùng hàng có thể bị chặn? | Không nhất thiết | Thường phải chờ khóa được giải phóng |
| Thời gian bảo vệ | Theo snapshot hoặc quy tắc đọc của DBMS | Thường kéo dài đến khi giao dịch kết thúc |

Không nên suy ra rằng mọi câu `SELECT` đều không dùng khóa hoặc mọi câu `SELECT ... FOR UPDATE` có hành vi giống nhau ở mọi DBMS. Bảng trên mô tả ý tưởng chung; chi tiết phụ thuộc hệ quản trị và isolation level.

## 3. Bảo vệ toàn bộ chuỗi đọc–kiểm tra–cập nhật

Một locking read chỉ có ích khi nó nằm trong cùng giao dịch với bước kiểm tra và bước cập nhật. Mẫu xử lý là:

1. Bắt đầu giao dịch.
2. Đọc hàng cần kiểm tra bằng locking read.
3. Kiểm tra điều kiện nghiệp vụ dựa trên giá trị được đọc trong khi khóa còn hiệu lực.
4. Nếu điều kiện đúng, cập nhật dữ liệu.
5. Commit để công bố kết quả và giải phóng khóa; nếu điều kiện sai hoặc có lỗi, rollback.

Ví dụ với PostgreSQL ở mức `READ COMMITTED`:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;

-- Ứng dụng đọc giá trị trả về.
-- Nếu available >= 4 thì thực hiện UPDATE.

UPDATE inventory
SET available = available - 4
WHERE product_id = 42;

COMMIT;
```

Đoạn SQL trên minh họa thứ tự thao tác; trong ứng dụng thực tế, câu `UPDATE` chỉ được chạy khi giá trị đã đọc đủ điều kiện. Nếu không đủ hàng, ứng dụng kết thúc giao dịch mà không trừ tồn kho.

Điểm quan trọng là `SELECT ... FOR UPDATE`, bước kiểm tra và `UPDATE` phải thuộc **cùng một transaction**. Nếu ứng dụng chạy `SELECT ... FOR UPDATE` trong một transaction rồi commit ngay, sau đó mở transaction khác để kiểm tra và cập nhật, khóa đã được giải phóng quá sớm và chuỗi thao tác lại có khoảng trống cạnh tranh.

### Hai giao dịch cùng đặt mua

Giả sử `available = 5`, `T1` và `T2` đều muốn đặt 4 sản phẩm.

| Thứ tự | Giao dịch T1 | Giao dịch T2 | Kết quả |
|---:|---|---|---|
| 1 | `BEGIN` | | |
| 2 | `SELECT ... FOR UPDATE` | | T1 lấy khóa trên hàng sản phẩm 42 |
| 3 | Đọc `available = 5` | `BEGIN` | |
| 4 | Kiểm tra `5 >= 4` | `SELECT ... FOR UPDATE` | T2 phải chờ khóa của T1 |
| 5 | Ghi `available = 1` | Đang chờ | |
| 6 | `COMMIT` | Đang chờ | T1 giải phóng khóa |
| 7 | | Được tiếp tục và đọc trạng thái hiện tại theo semantics của DBMS | T2 thấy `available = 1` trong trường hợp ví dụ này |
| 8 | | Kiểm tra `1 >= 4` không đạt; kết thúc giao dịch | T2 không xác nhận đơn hàng |

Nhờ khóa, hai giao dịch không thể đồng thời đưa ra quyết định dựa trên cùng trạng thái tồn kho rồi cùng sửa hàng đó. T1 hoàn tất trước; T2 tiếp tục sau và phải kiểm tra giá trị hiện tại.

Với PostgreSQL ở `READ COMMITTED`, một locking read chờ giao dịch khác cập nhật hàng sẽ khóa phiên bản hàng mới sau khi giao dịch kia kết thúc, nếu hàng vẫn thỏa điều kiện truy vấn. Ở isolation level hoặc DBMS khác, giao dịch có thể nhận lỗi serialization hoặc cần retry. Ứng dụng phải xử lý theo semantics cụ thể của hệ thống.

## 4. Ví dụ đầy đủ với xử lý điều kiện

Pseudocode sau thể hiện rõ nhánh nghiệp vụ. Nó không phải cú pháp PL/SQL hay một ngôn ngữ cụ thể; mục đích là làm rõ ranh giới transaction:

```text
BEGIN TRANSACTION

row = SELECT available
      FROM inventory
      WHERE product_id = 42
      FOR UPDATE

IF row không tồn tại:
    ROLLBACK
    báo sản phẩm không tồn tại

ELSE IF row.available < requested_quantity:
    ROLLBACK
    báo không đủ hàng

ELSE:
    UPDATE inventory
    SET available = available - requested_quantity
    WHERE product_id = 42

    INSERT INTO orders (...)
    COMMIT
```

Trong thực tế, thao tác trừ tồn kho và tạo đơn hàng thường phải nằm trong cùng transaction để tránh trạng thái chỉ trừ kho mà không có đơn, hoặc tạo đơn mà không trừ kho. Nếu bất kỳ bước nào thất bại, rollback sẽ hoàn tác các thay đổi trong transaction.

Nếu ứng dụng gọi dịch vụ bên ngoài, gửi email hoặc thực hiện thao tác không thể rollback trong khi đang giữ khóa, thời gian giữ khóa có thể kéo dài và làm giảm khả năng xử lý đồng thời. Nên giới hạn transaction vào phần công việc cơ sở dữ liệu cần bảo vệ; các side effect bên ngoài thường được xử lý bằng outbox hoặc cơ chế phù hợp khác sau khi transaction commit.

## 5. Khóa bảo vệ những hàng nào?

`SELECT ... FOR UPDATE` thường khóa các hàng thực tế được truy vấn và chọn theo cơ chế của DBMS. Nó không tự động có nghĩa là toàn bộ bảng hoặc mọi hàng có thể xuất hiện trong tương lai đều bị khóa.

Ví dụ:

```sql
SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;
```

Truy vấn này nhằm khóa hàng có `product_id = 42`. Một truy vấn khác trên `product_id = 99` có thể tiếp tục bình thường nếu không có khóa hoặc ràng buộc khác tạo xung đột.

### Điều kiện truy vấn không tìm thấy hàng

Giả sử ứng dụng muốn bảo đảm mỗi email chỉ được đăng ký một lần:

1. Đọc bảng để kiểm tra email chưa tồn tại.
2. Nếu không thấy hàng, chèn email mới.

Nếu truy vấn `SELECT ... FOR UPDATE` không trả về hàng nào, không thể mặc định rằng nó đã khóa được “vị trí trống” để giao dịch khác không thể chèn cùng email. Trong PostgreSQL, khóa hàng không khóa một hàng chưa tồn tại; trong InnoDB, gap/next-key locking có thể bảo vệ một khoảng khóa trong những điều kiện nhất định, phụ thuộc isolation level, chỉ mục và dạng truy vấn.

Đối với quy tắc duy nhất, nên dùng `UNIQUE` constraint/index làm hàng rào cuối cùng. Ứng dụng có thể thử chèn và xử lý lỗi vi phạm unique constraint. Nếu cần tuần tự hóa một quy trình rộng hơn, có thể khóa một hàng cha/guard đã tồn tại hoặc dùng cơ chế serializable phù hợp.

### Truy vấn trên một tập hàng hoặc một khoảng

Một điều kiện như:

```sql
SELECT *
FROM booking
WHERE room_id = 7
  AND start_time < :new_end
  AND end_time > :new_start
FOR UPDATE;
```

có thể dùng để khóa các lượt đặt phòng hiện có giao với khoảng thời gian mới. Nhưng nếu không có hàng nào được trả về, hoặc một giao dịch khác có thể chèn một hàng mới thỏa điều kiện, khóa các hàng hiện có chưa chắc đã bảo vệ được điều kiện “không có hai lượt đặt phòng trùng giờ”.

Đây là vấn đề khóa phạm vi/predicate và phantom. Tùy DBMS, có thể cần range/gap lock, exclusion constraint, khóa hàng đại diện cho phòng, hoặc Serializable Isolation. Phải kiểm tra cơ chế cụ thể thay vì giả định `FOR UPDATE` luôn khóa mọi hàng tương lai phù hợp với điều kiện.

## 6. Locking read và MVCC

Trong hệ thống dùng MVCC (Multi-Version Concurrency Control), truy vấn đọc thông thường thường lấy một phiên bản nhất quán mà không phải chờ khóa ghi của giao dịch khác. Điều này giúp tăng khả năng đọc đồng thời.

Locking read có mục đích khác: giao dịch đọc để ra quyết định cập nhật cần bảo vệ hàng mà nó vừa đọc khỏi thay đổi xung đột cho đến khi quyết định được hoàn tất. Vì vậy, `SELECT ... FOR UPDATE` thường là một dạng **current/locking read** theo semantics của DBMS, thay vì chỉ đọc một snapshot cũ không khóa.

Ví dụ về khác biệt:

- `SELECT` thông thường: đọc dữ liệu theo quy tắc snapshot/MVCC; giao dịch khác có thể cập nhật cùng hàng mà không nhất thiết phải chờ câu đọc.
- `SELECT ... FOR UPDATE`: yêu cầu khóa hàng; giao dịch khác muốn cập nhật hàng đó thường phải chờ hoặc giao dịch hiện tại phải xử lý xung đột.

MVCC và khóa không loại trừ nhau. Một DBMS có thể dùng MVCC cho đọc thường và vẫn dùng khóa để điều phối cập nhật, locking read, hoặc các ràng buộc khác.

## 7. Cú pháp và khác biệt giữa các DBMS

### PostgreSQL

Ví dụ:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;

UPDATE inventory
SET available = available - 4
WHERE product_id = 42;

COMMIT;
```

PostgreSQL hỗ trợ nhiều chế độ khóa hàng, bao gồm `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE` và `FOR KEY SHARE`. Chế độ phù hợp phụ thuộc loại thay đổi cần ngăn. `FOR UPDATE` là lựa chọn mạnh thường dùng khi chuẩn bị cập nhật hàng.

`NOWAIT` có thể yêu cầu truy vấn thất bại ngay nếu không lấy được khóa; `SKIP LOCKED` bỏ qua hàng đang bị khóa. Hai tùy chọn này hữu ích cho một số quy trình xử lý hàng đợi, nhưng không thay thế được việc bảo vệ một bất biến nghiệp vụ cần đọc đủ tập dữ liệu.

### MySQL với InnoDB

InnoDB hỗ trợ locking read trong transaction:

```sql
START TRANSACTION;

SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;

UPDATE inventory
SET available = available - 4
WHERE product_id = 42;

COMMIT;
```

InnoDB cũng hỗ trợ `FOR SHARE` cho locking read chia sẻ. Khóa hàng và khóa khoảng có thể được áp dụng khác nhau theo isolation level, chỉ mục và điều kiện tìm kiếm. Một truy vấn dùng chỉ mục phù hợp thường giúp DBMS khóa đúng phạm vi cần thiết và giảm số hàng bị khóa.

### SQL Server

SQL Server không dùng cú pháp `SELECT ... FOR UPDATE` theo cách của PostgreSQL/MySQL. Ứng dụng thường điều khiển hành vi khóa bằng table hints như `UPDLOCK`, đôi khi kết hợp `HOLDLOCK` hoặc isolation level phù hợp:

```sql
BEGIN TRANSACTION;

SELECT available
FROM dbo.inventory WITH (UPDLOCK, HOLDLOCK)
WHERE product_id = 42;

-- Kiểm tra điều kiện và cập nhật trong cùng transaction.

UPDATE dbo.inventory
SET available = available - 4
WHERE product_id = 42;

COMMIT TRANSACTION;
```

Đây là ví dụ định hướng, không phải công thức khóa áp dụng cho mọi truy vấn. Table hint thay đổi cách SQL Server lấy và giữ khóa; cần xác minh phạm vi khóa, isolation level và kế hoạch thực thi trên hệ thống thật.

## 8. NOWAIT và SKIP LOCKED

Hai tùy chọn này thay đổi cách truy vấn phản ứng khi hàng đang bị giao dịch khác khóa.

### NOWAIT

`NOWAIT` yêu cầu không chờ khóa. Nếu không lấy được khóa ngay, truy vấn trả lỗi để ứng dụng quyết định xử lý tiếp:

```sql
SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE NOWAIT;
```

Tùy chọn này phù hợp khi ứng dụng muốn phản hồi nhanh hoặc thử lại sau. Lỗi không lấy được khóa phải được xử lý ở cấp transaction; tùy DBMS, transaction có thể cần rollback trước khi tiếp tục.

### SKIP LOCKED

`SKIP LOCKED` bỏ qua những hàng hiện đang bị khóa:

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Mẫu này hữu ích khi nhiều worker lấy các công việc độc lập từ một hàng đợi: worker này có thể chọn một hàng khác thay vì chờ hàng mà worker kia đang xử lý.

Nhưng `SKIP LOCKED` không phù hợp khi nghiệp vụ yêu cầu đọc đầy đủ dữ liệu để kiểm tra một điều kiện tổng thể. Bỏ qua hàng đang bị khóa có thể khiến ứng dụng đưa ra quyết định dựa trên một tập dữ liệu thiếu. Ví dụ, không nên dùng nó để kiểm tra “còn ít nhất một nhân viên trực hay không” nếu những hàng bị bỏ qua có thể làm thay đổi kết luận.

## 9. Deadlock và thời gian giữ khóa

Locking read làm các giao dịch phối hợp chặt chẽ hơn, nhưng cũng có thể tạo ra chờ khóa và deadlock.

Ví dụ:

```text
T1: khóa hàng A
T2: khóa hàng B
T1: yêu cầu khóa hàng B → chờ T2
T2: yêu cầu khóa hàng A → chờ T1
```

Hai giao dịch tạo thành vòng chờ. DBMS có thể phát hiện deadlock và hủy một giao dịch làm nạn nhân. Ứng dụng cần rollback và, nếu phù hợp, retry toàn bộ transaction.

Một số nguyên tắc giảm rủi ro:

- Giữ transaction ngắn; không chờ người dùng hoặc gọi dịch vụ mạng khi đang giữ khóa.
- Nếu cần khóa nhiều hàng, lấy khóa theo một thứ tự nhất quán ở mọi luồng xử lý.
- Dùng điều kiện truy vấn và chỉ mục phù hợp để tránh khóa phạm vi rộng ngoài ý muốn.
- Chỉ khóa những hàng cần thiết để bảo vệ điều kiện nghiệp vụ.
- Xử lý deadlock, lock timeout và serialization failure như các lỗi có thể retry; retry toàn bộ transaction từ đầu để đọc và kiểm tra lại dữ liệu.

Không nên bắt mọi lỗi rồi lặp lại vô hạn. Cần giới hạn số lần retry, có backoff thích hợp và phân biệt lỗi tạm thời với lỗi nghiệp vụ như không đủ tồn kho.

## 10. Khi nào có thể dùng một câu UPDATE có điều kiện?

Không phải mọi chuỗi đọc–kiểm tra–cập nhật đều cần tách thành ba bước. Nếu điều kiện và thay đổi có thể biểu diễn trong một câu lệnh, một conditional update thường ngắn gọn và hiệu quả hơn:

```sql
UPDATE inventory
SET available = available - 4
WHERE product_id = 42
  AND available >= 4;
```

Sau câu lệnh, ứng dụng kiểm tra số hàng được cập nhật:

- `1` hàng: điều kiện còn đúng và đã trừ tồn kho thành công.
- `0` hàng: sản phẩm không tồn tại hoặc không đủ tồn kho; ứng dụng có thể phân biệt hai trường hợp bằng truy vấn phù hợp nếu nghiệp vụ cần.

DBMS điều phối cập nhật trên hàng theo cơ chế ghi của nó. Khi nhiều giao dịch cùng cập nhật một hàng, chúng không thể đồng thời ghi đè tùy ý lên cùng phiên bản; điều kiện `available >= 4` được đánh giá theo semantics của câu UPDATE và DBMS.

Conditional update phù hợp khi quy tắc có thể gói gọn trong một câu lệnh. Locking read phù hợp hơn khi ứng dụng phải đọc nhiều giá trị, áp dụng logic phức tạp hoặc cập nhật nhiều bảng dựa trên kết quả kiểm tra. Dù chọn cách nào, các thay đổi phải nằm trong transaction phù hợp nếu chúng cần thành công hoặc thất bại cùng nhau.

## 11. Locking read và optimistic concurrency control

Locking read là cách tiếp cận bi quan (pessimistic): giao dịch khóa dữ liệu trước khi quyết định thay đổi, dự đoán rằng có thể có giao dịch khác cạnh tranh.

Một cách khác là optimistic concurrency control (kiểm soát đồng thời lạc quan): đọc dữ liệu cùng phiên bản, rồi cập nhật có điều kiện theo phiên bản đó. Ví dụ:

```sql
UPDATE inventory
SET available = :new_available,
    version = version + 1
WHERE product_id = 42
  AND version = :version_read;
```

Nếu số hàng cập nhật bằng 0, phiên bản đã thay đổi hoặc hàng không còn phù hợp; ứng dụng phải đọc lại, kiểm tra lại và thử lại theo quy tắc nghiệp vụ.

| Tiêu chí | Locking read | Optimistic update |
|---|---|---|
| Thời điểm phát hiện cạnh tranh | Khi lấy khóa hoặc trong lúc chờ khóa | Khi câu UPDATE kiểm tra phiên bản/điều kiện |
| Khi có cạnh tranh | Giao dịch khác thường phải chờ hoặc nhận lỗi | Một giao dịch có thể cập nhật thất bại và phải đọc lại |
| Phù hợp khi | Xung đột tương đối thường xuyên hoặc logic đọc–kiểm tra phức tạp | Xung đột hiếm, transaction ngắn và có thể retry dễ dàng |
| Chi phí chính | Chờ khóa, deadlock, giảm song song | Retry và xử lý xung đột phiên bản |

Hai cách có thể kết hợp. Việc chọn lựa phụ thuộc tần suất cạnh tranh, độ phức tạp của quy tắc nghiệp vụ và khả năng retry.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc `FOR UPDATE` ngoài transaction hoặc commit ngay sau câu đọc | Khóa được giải phóng trước bước kiểm tra/cập nhật | Giữ câu đọc, kiểm tra và ghi trong cùng transaction |
| Chỉ khóa hàng định ghi nhưng điều kiện phụ thuộc nhiều hàng | Giao dịch khác có thể thay đổi hàng liên quan và phá điều kiện | Khóa toàn bộ phạm vi cần thiết, khóa hàng guard hoặc dùng Serializable |
| Giả định truy vấn không trả hàng đã khóa vị trí trống | Giao dịch khác vẫn có thể chèn hàng thỏa điều kiện | Dùng unique constraint, khóa hàng đại diện, range/predicate lock hoặc Serializable |
| Dùng `SKIP LOCKED` khi cần kiểm tra toàn bộ tập dữ liệu | Bỏ qua dữ liệu đang khóa và đưa ra quyết định sai | Chỉ dùng cho hàng đợi hoặc tác vụ cho phép bỏ qua hàng bận |
| Giữ khóa trong lúc gọi API hoặc chờ người dùng | Transaction lâu, tăng lock contention và timeout | Thu hẹp phần việc nằm trong transaction |
| Retry chỉ câu UPDATE sau deadlock/serialization failure | Quyết định có thể vẫn dựa trên dữ liệu cũ | Rollback và chạy lại toàn bộ transaction |
| Không kiểm tra số hàng được cập nhật | Ứng dụng có thể báo thành công dù điều kiện không thỏa | Kiểm tra affected row count hoặc kết quả trả về |

## 13. Tự kiểm tra

**Tình huống 1:** Tồn kho có 5 sản phẩm. `T1` và `T2` đều muốn đặt 4 sản phẩm. `T1` chạy `SELECT ... FOR UPDATE` và lấy được khóa. `T2` chạy cùng truy vấn. T2 có thể tiếp tục kiểm tra trên hàng đang bị T1 khóa không?

**Đáp án:** Thông thường T2 phải chờ hoặc nhận lỗi nếu dùng tùy chọn không chờ. Sau khi T1 commit và giải phóng khóa, T2 tiếp tục theo semantics của DBMS và phải kiểm tra trạng thái hiện tại trước khi quyết định.

**Tình huống 2:** Ứng dụng chạy `SELECT ... FOR UPDATE`, sau đó commit, rồi mới chạy câu UPDATE trong transaction khác. Chuỗi thao tác đã được bảo vệ chưa?

**Đáp án:** Chưa. Commit đã giải phóng khóa trước khi cập nhật. Một giao dịch khác có thể thay đổi dữ liệu trong khoảng thời gian giữa hai transaction.

**Tình huống 3:** Truy vấn `SELECT ... FOR UPDATE` không tìm thấy email cần kiểm tra. Có thể kết luận không giao dịch nào khác chèn email đó trước khi ta chèn không?

**Đáp án:** Không. Hàng chưa tồn tại có thể không được khóa. Dùng unique constraint/index để bảo vệ tính duy nhất; nếu cần tuần tự hóa quy trình rộng hơn, dùng khóa guard hoặc cơ chế phù hợp với DBMS.

**Tình huống 4:** Một worker dùng `SKIP LOCKED` để lấy một công việc từ hàng đợi. Vì sao cách này hợp lý với hàng đợi nhưng có thể sai khi kiểm tra tổng số nhân viên đang trực?

**Đáp án:** Hàng đợi cho phép worker bỏ qua công việc đang được worker khác xử lý để chọn công việc khác. Nhưng phép kiểm tra tổng thể cần xét đầy đủ dữ liệu; bỏ qua hàng đang khóa có thể làm kết quả kiểm tra sai.

**Tình huống 5:** Khi nào một conditional UPDATE có thể thay thế locking read?

**Đáp án:** Khi điều kiện kiểm tra và thay đổi có thể biểu diễn an toàn trong cùng một câu lệnh, chẳng hạn chỉ trừ tồn kho khi `available >= quantity`, rồi kiểm tra số hàng bị cập nhật. Nếu logic phụ thuộc nhiều truy vấn hoặc nhiều bảng, có thể cần transaction và locking read/Serializable phù hợp.

Khi thiết kế một chuỗi đọc–kiểm tra–cập nhật, hãy xác định chính xác dữ liệu nào tạo nên điều kiện nghiệp vụ, giao dịch nào có thể thay đổi dữ liệu đó, và khóa được giữ đến thời điểm nào. Đọc kèm khóa chỉ bảo vệ được quyết định khi phạm vi khóa bao phủ đúng dữ liệu liên quan và toàn bộ bước đọc, kiểm tra, cập nhật nằm trong cùng transaction.

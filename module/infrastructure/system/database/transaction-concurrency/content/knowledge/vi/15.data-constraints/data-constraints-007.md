# UPSERT nguyên tử và các điểm phụ thuộc cú pháp của hệ quản trị

Trong ứng dụng cơ sở dữ liệu, một thao tác thường gặp là **tạo bản ghi nếu chưa tồn tại, hoặc cập nhật bản ghi nếu đã tồn tại**. Cách làm này thường được gọi là UPSERT, ghép từ hai từ `UPDATE` và `INSERT`.

Ví dụ, một dịch vụ đồng bộ sản phẩm nhận dữ liệu từ hệ thống bên ngoài. Nếu mã sản phẩm chưa có trong bảng `Product`, dịch vụ cần tạo hàng mới. Nếu mã đó đã tồn tại, dịch vụ cần cập nhật tên và giá. Khi chỉ có một tiến trình ghi dữ liệu, cách kiểm tra rồi quyết định INSERT hoặc UPDATE có vẻ đơn giản. Nhưng khi nhiều giao dịch chạy đồng thời, cách làm đó có thể tạo ra race condition.

UPSERT nguyên tử cho phép DBMS xử lý việc cạnh tranh giữa INSERT và UPDATE trong một thao tác SQL theo cơ chế của hệ quản trị. Tuy nhiên, cú pháp và một số quy tắc khác nhau giữa PostgreSQL, MySQL, SQLite, SQL Server và Oracle. Muốn dùng đúng, cần hiểu cả ràng buộc duy nhất, phạm vi nguyên tử và giới hạn của từng cú pháp.

## 1. Vì sao cần UPSERT nguyên tử?

Giả sử bảng `Product` có cột `sku` là mã sản phẩm. Ứng dụng muốn bảo đảm mỗi SKU chỉ có một hàng.

Một cách triển khai ngây thơ là:

```sql
SELECT product_id
FROM Product
WHERE sku = 'SKU-100';

-- Nếu không tìm thấy:
INSERT INTO Product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000);

-- Nếu tìm thấy:
UPDATE Product
SET name = 'Keyboard', price = 500000
WHERE sku = 'SKU-100';
```

Vấn đề nằm giữa bước `SELECT` và bước ghi. Hai giao dịch A và B có thể cùng kiểm tra khi SKU chưa tồn tại:

```text
Transaction A                    Transaction B
     |                                 |
     | SELECT SKU-100                  |
     | không tìm thấy                  |
     |                                 | SELECT SKU-100
     |                                 | không tìm thấy
     | INSERT SKU-100                  |
     | thành công                      |
     |                                 | INSERT SKU-100
     |                                 | trùng khóa UNIQUE
```

Đây là race condition kiểu check-then-act. Nếu không có ràng buộc duy nhất, cả hai giao dịch có thể tạo hai hàng cùng SKU. Nếu có ràng buộc `UNIQUE`, dữ liệu được bảo vệ nhưng một giao dịch sẽ nhận lỗi trùng khóa thay vì tự động chuyển sang UPDATE.

UPSERT nguyên tử chuyển quyết định INSERT hay UPDATE vào một câu lệnh mà DBMS xử lý đồng bộ với cơ chế ràng buộc và khóa của nó. Giao dịch cạnh tranh cùng một khóa duy nhất sẽ được DBMS điều phối; một thao tác có thể chèn hàng, thao tác còn lại có thể cập nhật hàng vừa được tạo hoặc nhận kết quả xung đột tùy cú pháp và DBMS.

## 2. Ràng buộc UNIQUE là nền tảng của UPSERT

UPSERT cần một tiêu chí xác định hai bản ghi có đại diện cho cùng một thực thể hay không. Tiêu chí đó thường là khóa chính (PRIMARY KEY) hoặc ràng buộc duy nhất (UNIQUE).

Ví dụ:

```sql
CREATE TABLE Product (
    product_id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    CONSTRAINT uq_product_sku UNIQUE (sku)
);
```

Trong ví dụ này, `sku` là khóa nghiệp vụ. DBMS từ chối việc tạo hai hàng có cùng SKU. Nếu nhiều tenant có thể dùng cùng SKU, khóa nghiệp vụ có thể cần gồm cả tenant:

```sql
UNIQUE (tenant_id, sku)
```

Điều này quan trọng vì câu lệnh UPSERT phải nhắm đúng ràng buộc thể hiện danh tính của bản ghi. Nếu dùng nhầm một cột không duy nhất, hai giao dịch có thể vẫn tạo ra hai hàng. Nếu bảng có nhiều ràng buộc duy nhất, một giá trị đầu vào có thể xung đột với một hàng khác qua ràng buộc mà người viết câu lệnh không dự kiến.

### UNIQUE và NULL

Không nên mặc định mọi DBMS xử lý `NULL` trong unique key giống nhau. PostgreSQL, MySQL và SQLite thông thường cho phép nhiều hàng có `NULL` trong cột unique; SQL Server có quy tắc unique index khác; Oracle cũng có cách xử lý giá trị null riêng. Với khóa nghiệp vụ bắt buộc phải có giá trị, khai báo `NOT NULL` giúp tránh sự khác biệt này.

Nếu khóa duy nhất chỉ áp dụng cho một tập hàng, ví dụ chỉ các bản ghi chưa bị xóa mềm, có thể cần partial unique index hoặc filtered unique index. Cú pháp và khả năng suy luận conflict target phụ thuộc DBMS.

## 3. UPSERT nguyên tử có nghĩa gì?

Một câu lệnh UPSERT nguyên tử kết hợp việc xác định xung đột và hành động tương ứng trong một thao tác SQL. DBMS dùng chỉ mục/ràng buộc duy nhất cùng cơ chế đồng thời của nó để quyết định liệu hàng được chèn hay cập nhật.

Tính nguyên tử ở đây có nghĩa thao tác ghi của câu lệnh không để lại trạng thái nửa chừng: nếu câu lệnh thất bại theo quy tắc transaction của DBMS, thay đổi của câu lệnh được xử lý như một đơn vị. Nó không có nghĩa toàn bộ quy trình nghiệp vụ gồm gọi API, gửi email, phát thông điệp và cập nhật nhiều hệ thống trở thành một giao dịch nguyên tử duy nhất.

UPSERT cũng không tự động bảo đảm mọi quy tắc nghiệp vụ. Ví dụ, câu lệnh cập nhật một hàng theo SKU không tự bảo vệ quy tắc “tổng số lượng của tất cả kho không được vượt quá hạn mức”. Quy tắc liên quan nhiều hàng vẫn cần constraint, mức cô lập, khóa hoặc thiết kế giao dịch phù hợp.

### UPSERT khác với MERGE như thế nào?

`UPSERT` thường là tên gọi cho hành vi insert-or-update. Không có một cú pháp UPSERT duy nhất dùng nguyên trạng trên mọi DBMS. Nhiều hệ quản trị có cú pháp riêng như `ON CONFLICT`, `ON DUPLICATE KEY UPDATE` hoặc `MERGE`.

`MERGE` là câu lệnh kết hợp dữ liệu nguồn với dữ liệu đích rồi thực hiện các hành động khi khớp hoặc không khớp. Nó có thể hỗ trợ UPDATE, INSERT và trong một số hệ quản trị cả DELETE. `MERGE` linh hoạt hơn cho đồng bộ nhiều hàng, nhưng không nên giả định mọi triển khai `MERGE` có cùng bảo đảm đồng thời hoặc cùng hành vi với UPSERT chuyên biệt.

## 4. PostgreSQL: INSERT ... ON CONFLICT

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT` để xử lý xung đột trên unique constraint hoặc unique index.

### 4.1. ON CONFLICT DO UPDATE

Ví dụ cập nhật sản phẩm theo SKU:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
ON CONFLICT (sku)
DO UPDATE SET
    name = EXCLUDED.name,
    price = EXCLUDED.price;
```

Giải thích:

- `ON CONFLICT (sku)` chỉ ra khóa duy nhất dùng để nhận diện xung đột.
- `DO UPDATE` yêu cầu cập nhật hàng đang gây xung đột.
- `EXCLUDED` đại diện cho hàng được đề xuất chèn nhưng không được chèn vì xung đột.
- `product.name` hoặc `product.price` là giá trị hiện có trong hàng đích; `EXCLUDED.name` và `EXCLUDED.price` là giá trị mới từ câu lệnh INSERT.

Nếu SKU chưa tồn tại, DBMS chèn hàng. Nếu SKU đã tồn tại, DBMS cập nhật hàng đó. PostgreSQL bảo đảm một kết quả insert-or-update nguyên tử cho thao tác này, kể cả khi có giao dịch đồng thời cạnh tranh cùng khóa duy nhất.

### 4.2. ON CONFLICT DO NOTHING

Nếu bản ghi đã tồn tại và ứng dụng không cần cập nhật, có thể bỏ qua xung đột:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
ON CONFLICT (sku) DO NOTHING;
```

Đây là lựa chọn hữu ích cho thao tác tạo dữ liệu idempotent kiểu “đảm bảo bản ghi tồn tại”. Tuy nhiên, `DO NOTHING` không trả về hàng hiện có qua `RETURNING`; nếu cần ID của bản ghi hiện có, ứng dụng cần một truy vấn bổ sung hoặc một mẫu SQL phù hợp với yêu cầu.

### 4.3. RETURNING và điều kiện cập nhật

PostgreSQL hỗ trợ `RETURNING` để lấy dữ liệu hàng được chèn hoặc cập nhật:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
ON CONFLICT (sku)
DO UPDATE SET
    name = EXCLUDED.name,
    price = EXCLUDED.price
RETURNING product_id, sku, name, price;
```

Có thể thêm `WHERE` vào nhánh `DO UPDATE` để chỉ cập nhật khi điều kiện thỏa mãn:

```sql
INSERT INTO product (sku, name, price, source_version)
VALUES ('SKU-100', 'Keyboard', 500000, 12)
ON CONFLICT (sku)
DO UPDATE SET
    name = EXCLUDED.name,
    price = EXCLUDED.price,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > product.source_version;
```

Ví dụ này tránh ghi đè dữ liệu mới hơn bằng một thông điệp đồng bộ cũ. Nếu điều kiện `WHERE` không đúng, hàng xung đột không được cập nhật và cũng không xuất hiện trong kết quả `RETURNING` của nhánh cập nhật.

### 4.4. Conflict target và unique index

Conflict target có thể chỉ rõ cột hoặc biểu thức của unique index. Với partial unique index, điều kiện của index có thể cần được nêu để PostgreSQL suy luận đúng index:

```sql
CREATE UNIQUE INDEX uq_active_product_sku
ON product (sku)
WHERE deleted_at IS NULL;

INSERT INTO product (sku, name, deleted_at)
VALUES ('SKU-100', 'Keyboard', NULL)
ON CONFLICT (sku) WHERE deleted_at IS NULL
DO UPDATE SET name = EXCLUDED.name;
```

Khi dùng `ON CONFLICT DO UPDATE`, PostgreSQL không cho phép một câu lệnh tác động cập nhật cùng một hàng đích nhiều lần. Nếu dữ liệu nguồn chứa hai hàng có cùng khóa xung đột, câu lệnh có thể lỗi cardinality violation. Với UPSERT nhiều hàng, cần loại trùng hoặc gộp dữ liệu nguồn trước khi gửi vào câu lệnh.

PostgreSQL cũng có câu lệnh `MERGE`, nhưng `MERGE` và `INSERT ... ON CONFLICT` không thể xem là hai cú pháp hoàn toàn thay thế nhau. Nếu mục tiêu cụ thể là insert-or-update dựa trên unique key và cần bảo đảm atomic insert/update khi cạnh tranh, `ON CONFLICT` thường là lựa chọn trực tiếp hơn.

## 5. MySQL: INSERT ... ON DUPLICATE KEY UPDATE

MySQL dùng cú pháp `ON DUPLICATE KEY UPDATE`:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
AS incoming
ON DUPLICATE KEY UPDATE
    name = incoming.name,
    price = incoming.price;
```

Ở cú pháp MySQL 8.0.19 trở lên, alias hàng được đề xuất có thể được khai báo sau danh sách `VALUES` và dùng trong nhánh UPDATE. Cách viết này giúp tham chiếu giá trị đầu vào.

Trong các phiên bản cũ hơn, ví dụ thường dùng hàm `VALUES(column)`:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    price = VALUES(price);
```

Trong MySQL, `VALUES(column)` trong ngữ cảnh này đã bị đánh dấu deprecated từ MySQL 8.0.20. Với mã mới trên các phiên bản hỗ trợ, nên dùng row alias theo tài liệu phiên bản. MariaDB có lịch sử cú pháp và hỗ trợ riêng; không nên giả định mọi phiên bản MariaDB và MySQL có cùng trạng thái của alias hoặc `VALUES()`.

### 5.1. Khác biệt quan trọng: không chỉ định conflict target

Không giống PostgreSQL, `ON DUPLICATE KEY UPDATE` của MySQL không nhận danh sách cột làm conflict target. Nhánh UPDATE được kích hoạt khi INSERT vi phạm một `PRIMARY KEY` hoặc `UNIQUE` key.

Điều này đặc biệt quan trọng nếu bảng có nhiều unique index. Một dữ liệu đầu vào có thể trùng `sku` với hàng A nhưng lại trùng `external_id` với hàng B. Khi đó, MySQL có thể cập nhật hàng được xác định bởi một khóa duy nhất bị vi phạm; thiết kế như vậy dễ gây kết quả bất ngờ. Tài liệu MySQL khuyến cáo thận trọng với bảng có nhiều unique index khi dùng cú pháp này.

Nếu nghiệp vụ chỉ muốn upsert theo `sku`, hãy bảo đảm mô hình unique key và dữ liệu đầu vào không tạo ra xung đột chéo không mong muốn. Không thể viết `ON DUPLICATE KEY UPDATE` để chỉ định “chỉ khi trùng cột sku” như conflict target của PostgreSQL.

### 5.2. Số hàng bị ảnh hưởng

Giá trị affected rows của MySQL có thể khác theo nhánh thao tác và tùy chọn client:

- Hàng được chèn: thường là 1.
- Hàng hiện có được cập nhật: thường là 2.
- Nhánh UPDATE gán lại giá trị hiện tại, không tạo thay đổi: thường là 0; có thể báo 1 nếu client bật `CLIENT_FOUND_ROWS`.

Vì vậy, không nên dùng affected rows như một quy tắc chung để suy luận đơn giản rằng “1 là insert, 2 là update” nếu driver hoặc cấu hình client có thể thay đổi semantics. Nếu cần biết chính xác trạng thái nghiệp vụ, hãy thiết kế câu lệnh trả về hoặc truy vấn kết quả phù hợp với DBMS/driver.

## 6. SQLite: INSERT ... ON CONFLICT

SQLite hỗ trợ UPSERT với cú pháp gần với PostgreSQL:

```sql
INSERT INTO product (sku, name, price)
VALUES ('SKU-100', 'Keyboard', 500000)
ON CONFLICT (sku)
DO UPDATE SET
    name = excluded.name,
    price = excluded.price;
```

`excluded` đại diện cho hàng được đề xuất chèn. Có thể dùng `DO NOTHING` nếu chỉ muốn bỏ qua bản ghi trùng.

SQLite UPSERT được kích hoạt bởi xung đột trên `PRIMARY KEY`, `UNIQUE` constraint hoặc unique index. Nó không phải cơ chế xử lý mọi loại lỗi constraint: lỗi `NOT NULL`, `CHECK` hoặc foreign key không tự chuyển thành nhánh UPSERT theo cách tương tự.

SQLite cho phép nhiều nhánh `ON CONFLICT` trong một số phiên bản mới, nhưng cú pháp và khả năng cụ thể phụ thuộc phiên bản SQLite được nhúng trong ứng dụng. Cần kiểm tra phiên bản runtime thực tế, đặc biệt với ứng dụng di động hoặc desktop có SQLite đi kèm.

## 7. SQL Server: MERGE và mẫu UPDATE rồi INSERT

SQL Server không có cú pháp `INSERT ... ON CONFLICT` giống PostgreSQL. Hai cách phổ biến là `MERGE` hoặc kết hợp `UPDATE` và `INSERT` trong một transaction có khóa phù hợp.

### 7.1. Dùng MERGE

Ví dụ:

```sql
MERGE dbo.Product WITH (HOLDLOCK) AS target
USING (VALUES ('SKU-100', 'Keyboard', 500000))
    AS source (sku, name, price)
ON target.sku = source.sku
WHEN MATCHED THEN
    UPDATE SET
        name = source.name,
        price = source.price
WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, name, price)
    VALUES (source.sku, source.name, source.price);
```

`MERGE` so sánh nguồn với đích qua điều kiện `ON`. Nếu khớp, nhánh `WHEN MATCHED` được thực hiện; nếu không có hàng đích tương ứng, nhánh `WHEN NOT MATCHED BY TARGET` có thể chèn hàng.

Trong ví dụ, `HOLDLOCK` trên target yêu cầu ngữ nghĩa khóa tương đương `SERIALIZABLE` cho tham chiếu đó, giúp bảo vệ khoảng khóa và giảm race condition khi hai session đồng thời cùng thấy chưa có SKU rồi cùng chèn. Tuy nhiên, `MERGE` có nhiều chi tiết về trigger, nguồn trùng, hành động đồng thời và phiên bản SQL Server. Cần kiểm thử theo workload và đọc tài liệu phiên bản cụ thể.

Nếu nguồn có nhiều hàng cùng khớp một hàng đích, SQL Server có thể báo lỗi vì một hàng đích không được cập nhật nhiều lần trong cùng một câu lệnh `MERGE`. Hãy loại trùng khóa nguồn trước khi thực hiện.

### 7.2. Dùng UPDATE rồi INSERT trong transaction

Với thao tác upsert đơn giản theo một khóa duy nhất, một mẫu thường dễ kiểm soát là UPDATE trước, nếu không có hàng thì INSERT. Điều kiện quan trọng là transaction phải khóa phạm vi tìm kiếm để hai giao dịch không cùng vượt qua bước kiểm tra “không tìm thấy”.

```sql
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @updated int;

    UPDATE dbo.Product WITH (UPDLOCK, SERIALIZABLE)
    SET name = @name,
        price = @price
    WHERE sku = @sku;

    SET @updated = @@ROWCOUNT;

    IF @updated = 0
    BEGIN
        INSERT INTO dbo.Product (sku, name, price)
        VALUES (@sku, @name, @price);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
```

`UPDLOCK` yêu cầu khóa cập nhật khi đọc/định vị tài nguyên, còn `SERIALIZABLE` yêu cầu bảo vệ phạm vi tìm kiếm trong transaction. Với index phù hợp trên `sku`, DBMS có thể bảo vệ key range khi hàng chưa tồn tại. Ràng buộc `UNIQUE (sku)` vẫn cần có để bảo vệ dữ liệu ở mức cuối cùng.

Nếu thiếu index phù hợp, phạm vi khóa có thể rộng hơn và giảm tính đồng thời. Cũng cần lưu ý rằng mẫu này phải được kiểm thử với isolation, index, trigger và kế hoạch thực thi thực tế. `@@ROWCOUNT` phải được lưu ngay sau câu UPDATE vì các câu lệnh tiếp theo có thể thay đổi giá trị này.

### 7.3. Chọn MERGE hay UPDATE/INSERT?

`MERGE` phù hợp khi cần đồng bộ tập nguồn và có nhiều nhánh hành động dựa trên trạng thái khớp. Với một thao tác upsert đơn hàng, mẫu UPDATE/INSERT trong transaction có khóa rõ ràng có thể dễ hiểu và dễ kiểm soát hơn. Không nên chọn `MERGE` chỉ vì tên câu lệnh có vẻ diễn đạt đúng ý định; hãy xem xét concurrency, trigger, nguồn trùng, phiên bản SQL Server và cách kiểm thử.

## 8. Oracle: MERGE INTO

Oracle hỗ trợ `MERGE` để kết hợp dữ liệu nguồn với bảng đích:

```sql
MERGE INTO product target
USING (
    SELECT :sku AS sku,
           :name AS name,
           :price AS price
    FROM dual
) source
ON (target.sku = source.sku)
WHEN MATCHED THEN
    UPDATE SET
        target.name = source.name,
        target.price = source.price
WHEN NOT MATCHED THEN
    INSERT (sku, name, price)
    VALUES (source.sku, source.name, source.price);
```

`:sku`, `:name` và `:price` là bind variables do driver truyền vào. `dual` là bảng đặc biệt thường dùng trong Oracle để tạo một hàng nguồn từ các giá trị bind.

Oracle `MERGE` có quy tắc riêng:

- Điều kiện `ON` xác định hàng đích khớp với nguồn.
- Một câu lệnh `MERGE` không được cập nhật cùng một hàng đích nhiều lần. Nguồn trùng khóa có thể gây lỗi như `ORA-30926` trong các tình huống không ổn định.
- Cột được tham chiếu trong điều kiện `ON` có các hạn chế khi dùng trong nhánh UPDATE; cần kiểm tra tài liệu cú pháp Oracle khi thay đổi khóa khớp.
- `MERGE` là một câu lệnh DML, nhưng các giao dịch đồng thời vẫn có thể gặp unique constraint conflict nếu hai session cùng xác định chưa có hàng rồi cùng chèn. Ràng buộc duy nhất và xử lý lỗi/retry vẫn quan trọng.

Không chuyển nguyên cú pháp `MERGE` của Oracle sang SQL Server hoặc ngược lại chỉ bằng cách đổi tên bảng. Chi tiết alias, bind, hint, điều kiện và nhánh hành động phụ thuộc hệ quản trị.

## 9. So sánh cú pháp và điểm khác biệt

| DBMS | Cú pháp thường dùng | Chọn khóa xung đột | Giá trị hàng đầu vào trong nhánh UPDATE |
|---|---|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | Có thể nêu cột/index hoặc constraint | `EXCLUDED.column` |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` | Không nêu conflict target; bất kỳ PRIMARY/UNIQUE key bị vi phạm có thể kích hoạt | Row alias ở phiên bản mới; `VALUES(column)` ở mã cũ (deprecated từ 8.0.20) |
| SQLite | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | Nêu cột hoặc unique index target | `excluded.column` |
| SQL Server | `MERGE` hoặc UPDATE/INSERT trong transaction | Điều kiện `ON` của MERGE hoặc điều kiện UPDATE có khóa | Alias nguồn như `source.column` |
| Oracle | `MERGE INTO ... USING ... ON ...` | Điều kiện `ON` | Alias nguồn như `source.column` |

Các điểm cần nhớ khi chuyển ứng dụng giữa DBMS:

- Cú pháp conflict target không giống nhau. MySQL không cho chọn một unique key cụ thể trong `ON DUPLICATE KEY UPDATE`.
- Tên alias cho dữ liệu đề xuất khác nhau: `EXCLUDED`, `excluded`, alias nguồn hoặc biểu thức phiên bản.
- Cách lấy ID/hàng vừa ghi (`RETURNING`, `OUTPUT`, `RETURNING INTO`, hoặc truy vấn sau đó) khác nhau.
- Số hàng bị ảnh hưởng và cách driver báo kết quả có thể khác nhau.
- Hành vi với nhiều hàng nguồn trùng khóa khác nhau giữa các hệ quản trị.
- Mức cô lập, khóa khoảng, trigger và lỗi cạnh tranh không được chuẩn hóa chỉ bởi từ UPSERT.

## 10. UPSERT nhiều hàng và dữ liệu nguồn trùng khóa

UPSERT thường được dùng để nhập một lô dữ liệu:

```sql
INSERT INTO product (sku, name, price)
VALUES
    ('SKU-100', 'Keyboard', 500000),
    ('SKU-200', 'Mouse', 250000),
    ('SKU-300', 'Monitor', 3000000)
-- phần xử lý xung đột phụ thuộc DBMS
;
```

Trước khi gửi lô dữ liệu, cần xác định điều gì xảy ra nếu nguồn chứa cùng một khóa nhiều lần. Ví dụ, hai dòng cùng có `sku = 'SKU-100'` nhưng giá khác nhau. Ứng dụng cần quyết định giữ bản ghi mới nhất, tổng hợp dữ liệu, từ chối lô hay sắp xếp theo timestamp.

Không nên để thứ tự tình cờ của dữ liệu nguồn quyết định kết quả nghiệp vụ. PostgreSQL có thể báo cardinality violation nếu một câu lệnh `ON CONFLICT DO UPDATE` cố tác động cùng hàng đích nhiều lần. SQL Server `MERGE` cũng có thể lỗi nếu nhiều hàng nguồn cùng khớp một hàng đích. Các DBMS khác có quy tắc xử lý riêng.

Một cách an toàn là chuẩn hóa nguồn trước:

1. Xác thực khóa nghiệp vụ không rỗng.
2. Nhóm theo khóa duy nhất.
3. Chọn quy tắc ưu tiên rõ ràng, chẳng hạn timestamp lớn nhất hoặc version lớn nhất.
4. Từ chối những trường hợp có hai bản ghi cùng version nhưng nội dung khác nhau nếu nghiệp vụ không cho phép.
5. Gửi một hàng duy nhất cho mỗi khóa vào UPSERT.

## 11. UPSERT, tính idempotent và chính sách ghi đè

Một câu lệnh UPSERT có thể nguyên tử nhưng chưa chắc idempotent.

Ví dụ:

```sql
-- Gán giá trị tuyệt đối: gửi lại cùng payload thường cho cùng trạng thái cuối.
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-100', 10)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
```

Nếu gửi lại cùng payload, số lượng vẫn là 10. Đây thường là dạng đồng bộ trạng thái.

Ngược lại:

```sql
-- Cộng thêm số lượng: gửi lại payload có thể cộng lặp.
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-100', 10)
ON CONFLICT (sku)
DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity;
```

Nếu request bị timeout sau khi DB đã commit và ứng dụng gửi lại, số lượng có thể tăng thêm lần nữa. Đây là phép cộng, không idempotent theo payload. Nếu nghiệp vụ cần cộng một sự kiện đúng một lần, hãy lưu event ID với unique constraint và áp dụng cập nhật trong cùng transaction, hoặc dùng một cơ chế idempotency tương đương.

### Last writer wins và dữ liệu cũ

Nhánh `DO UPDATE SET column = incoming.column` thường mang semantics “người ghi sau ghi đè”. Điều này có thể không phù hợp nếu một hệ thống đồng bộ nhận sự kiện đến sai thứ tự. Có thể cần điều kiện version/timestamp:

```sql
INSERT INTO product (sku, name, source_version)
VALUES ('SKU-100', 'Keyboard', 12)
ON CONFLICT (sku)
DO UPDATE SET
    name = EXCLUDED.name,
    source_version = EXCLUDED.source_version
WHERE EXCLUDED.source_version > product.source_version;
```

Chính sách version phải được định nghĩa rõ: version tăng đơn điệu theo cùng nguồn hay theo toàn thực thể, xử lý hai nguồn ghi đồng thời ra sao, và điều gì xảy ra khi version bằng nhau nhưng payload khác nhau.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không có unique constraint trên khóa nghiệp vụ | Hai giao dịch có thể chèn hai hàng trùng nhau | Tạo PRIMARY KEY hoặc UNIQUE index đúng phạm vi nghiệp vụ |
| SELECT rồi mới INSERT mà không có cơ chế đồng thời | Race condition giữa kiểm tra và ghi | Dùng UPSERT phù hợp hoặc transaction/locking đúng cách |
| MySQL có nhiều unique key nhưng giả định chỉ một key kích hoạt | Có thể cập nhật nhầm hàng do conflict trên key khác | Thiết kế lại key hoặc kiểm tra mọi unique constraint có thể xung đột |
| Dùng `VALUES(column)` trên MySQL mới mà không xem phiên bản | Cú pháp deprecated hoặc cảnh báo | Dùng row alias theo phiên bản hỗ trợ |
| Dùng `MERGE` với nguồn trùng khóa | Lỗi hoặc kết quả không đúng quy tắc mong muốn | Deduplicate và xác thực nguồn trước khi MERGE |
| Gán giá trị mới mà không kiểm tra version | Ghi đè dữ liệu mới bằng payload cũ | Dùng điều kiện version hoặc timestamp có quy tắc rõ ràng |
| Retry phép cộng không idempotent | Cộng dữ liệu nhiều lần | Dùng event ID/unique constraint hoặc thiết kế idempotency |
| Dùng UPSERT cho quy tắc nhiều hàng | Có thể vi phạm invariant liên hàng | Dùng constraint, transaction, isolation hoặc khóa phù hợp |

## 13. Quy trình chọn cú pháp UPSERT

Khi triển khai UPSERT, có thể đi theo trình tự sau:

1. **Xác định danh tính bản ghi:** chọn khóa chính hoặc khóa nghiệp vụ thực sự duy nhất.
2. **Tạo ràng buộc ở DBMS:** khai báo `PRIMARY KEY`, `UNIQUE` và `NOT NULL` phù hợp. Không dựa vào kiểm tra ở tầng ứng dụng làm hàng rào duy nhất.
3. **Xác định chính sách khi trùng:** bỏ qua, ghi đè, cập nhật có điều kiện theo version, cộng dồn hay từ chối.
4. **Chọn cú pháp theo DBMS:** PostgreSQL/SQLite `ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE`, SQL Server/Oracle `MERGE` hoặc mẫu riêng theo hệ quản trị.
5. **Xác định kết quả cần trả về:** ID, hàng mới, số hàng bị ảnh hưởng hay trạng thái insert/update.
6. **Kiểm tra dữ liệu lô:** bảo đảm mỗi khóa đích có tối đa một hàng nguồn sau bước chuẩn hóa.
7. **Kiểm thử cạnh tranh:** chạy nhiều transaction đồng thời với cùng khóa và khóa khác nhau; xác nhận không có bản ghi trùng và chính sách ghi đè đúng.
8. **Thiết kế retry:** phân loại unique conflict, deadlock, serialization failure và lỗi kết nối; chỉ retry các lỗi có thể retry và bảo đảm thao tác idempotent.

UPSERT nguyên tử giúp xử lý cạnh tranh giữa tạo mới và cập nhật trên một khóa duy nhất, nhưng tính đúng đắn vẫn bắt đầu từ mô hình khóa nghiệp vụ và constraint của DBMS. Khi chuyển giữa các hệ quản trị, cần xem lại conflict target, alias giá trị đầu vào, cách trả kết quả, quy tắc nhiều hàng và hành vi đồng thời. Chọn đúng cú pháp cho hệ quản trị đang chạy sẽ giúp tránh race condition mà vẫn giữ được chính sách cập nhật mà nghiệp vụ yêu cầu.

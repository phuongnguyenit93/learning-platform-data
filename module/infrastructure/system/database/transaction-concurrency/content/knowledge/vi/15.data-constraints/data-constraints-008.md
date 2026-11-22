# Phân biệt UPSERT với chuỗi SELECT rồi INSERT hoặc UPDATE

Khi ứng dụng muốn tạo một bản ghi nếu bản ghi chưa tồn tại, hoặc cập nhật bản ghi nếu nó đã tồn tại, một cách viết dễ nghĩ tới là đọc trước bằng `SELECT`, sau đó quyết định chạy `INSERT` hay `UPDATE`. Cách làm này có thể đúng trong một luồng đơn, nhưng dễ phát sinh race condition khi nhiều giao dịch cùng chạy: hai giao dịch có thể cùng đọc thấy “chưa tồn tại” rồi cùng chèn, hoặc cùng đọc một giá trị cũ rồi ghi đè kết quả của nhau.

**UPSERT** kết hợp ý định chèn và xử lý xung đột thành một thao tác cơ sở dữ liệu. Khi được xây dựng trên khóa duy nhất phù hợp và cú pháp mà DBMS hỗ trợ, nó cho phép hệ quản trị điều phối việc chèn hoặc cập nhật tại điểm xung đột, tránh khoảng thời gian không được bảo vệ giữa bước kiểm tra và bước ghi.

UPSERT không phải một câu lệnh SQL chuẩn có cú pháp giống nhau ở mọi hệ quản trị. PostgreSQL, MySQL, SQLite, SQL Server và Oracle có các cơ chế khác nhau. Cần hiểu cả ngữ nghĩa, ràng buộc duy nhất, hành vi khi có cạnh tranh và khác biệt của từng sản phẩm trước khi chọn cách triển khai.

## 1. Bài toán insert-if-absent, update-if-present

Giả sử ứng dụng đồng bộ khách hàng từ một hệ thống CRM. Mỗi khách hàng có một mã ngoài `external_id` duy nhất. Khi nhận dữ liệu:

- Nếu `external_id` chưa có trong bảng, tạo khách hàng mới.
- Nếu `external_id` đã có, cập nhật tên hiển thị và thời điểm đồng bộ.

Một bảng đơn giản:

```sql
CREATE TABLE customer (
    customer_id  BIGINT PRIMARY KEY,
    external_id  VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);
```

Điểm quan trọng là `external_id` có ràng buộc `UNIQUE`. Đây là quy tắc dữ liệu đảm bảo mỗi mã ngoài chỉ ánh xạ đến tối đa một khách hàng. Nếu không có ràng buộc duy nhất, hai giao dịch vẫn có thể chèn hai dòng cùng mã, dù ứng dụng đã cố gắng kiểm tra trước.

UPSERT thường dựa vào khóa chính, unique constraint hoặc unique index để xác định xung đột. Nó không tự suy ra rằng hai dòng là “cùng một khách hàng” chỉ vì một số cột có giá trị giống nhau. Ứng dụng và schema phải định nghĩa rõ khóa nhận diện bản ghi.

## 2. Chuỗi SELECT rồi INSERT có race condition như thế nào?

Một cách triển khai thủ công thường gặp:

```sql
SELECT customer_id
FROM customer
WHERE external_id = 'crm-17';

-- Nếu không tìm thấy:
INSERT INTO customer (
    customer_id, external_id, display_name, updated_at
)
VALUES (
    101, 'crm-17', 'Lan', CURRENT_TIMESTAMP
);
```

Giữa câu `SELECT` và câu `INSERT`, một giao dịch khác có thể thay đổi dữ liệu. Hai câu lệnh riêng biệt tạo ra một khoảng thời gian mà quyết định dựa trên kết quả đọc chưa được bảo vệ.

### 2.1. Hai giao dịch cùng thấy bản ghi chưa tồn tại

Giả sử chưa có `external_id = 'crm-17'`. T1 và T2 cùng chạy logic trên:

```text
Thời gian ---------------------------------------------------->

T1: SELECT crm-17 -> không có dòng
                         |
T2:                     SELECT crm-17 -> không có dòng
                         |
T1:                     INSERT crm-17 -> thành công
                         |
T2:                     INSERT crm-17 -> xung đột
```

Kết quả phụ thuộc schema:

- Nếu không có unique constraint, cả hai `INSERT` có thể thành công và tạo hai khách hàng cho cùng một mã ngoài. Dữ liệu bị trùng.
- Nếu có unique constraint, chỉ một giao dịch có thể tạo khóa duy nhất đó. Giao dịch còn lại thường nhận lỗi duplicate key/unique violation hoặc phải xử lý lại theo chiến lược ứng dụng.

Unique constraint bảo vệ tính đúng đắn của dữ liệu, nhưng chuỗi `SELECT` rồi `INSERT` vẫn có thể khiến request thứ hai thất bại. Ứng dụng cần bắt lỗi đúng loại, đọc lại hoặc retry nếu nghiệp vụ yêu cầu “đảm bảo có một bản ghi sau thao tác”.

### 2.2. SELECT trước rồi UPDATE cũng có thể ghi đè dữ liệu mới

Nếu dòng đã tồn tại, hai giao dịch có thể cùng đọc một giá trị rồi tính toán từ giá trị đó:

```text
Ban đầu: stock = 10

T1: SELECT stock -> 10
T2: SELECT stock -> 10

T1: tính stock mới = 10 - 2 = 8
T2: tính stock mới = 10 - 3 = 7

T1: UPDATE stock = 8 -> COMMIT
T2: UPDATE stock = 7 -> COMMIT
```

Kết quả cuối là 7. Phần giảm 2 của T1 bị ghi đè; nếu nghiệp vụ yêu cầu cả hai lần xuất kho đều được tính thì giá trị đúng phải là 5. Đây là một dạng lost update do cập nhật dựa trên giá trị đã đọc trước đó.

Một câu `UPDATE` tính trực tiếp trên giá trị hiện tại trong database có thể tránh kiểu ghi đè này:

```sql
UPDATE inventory
SET stock = stock - 2
WHERE sku = 'A';
```

Khi nhiều giao dịch cùng cập nhật, DBMS phối hợp việc ghi trên dòng và thực hiện biểu thức trên phiên bản phù hợp theo cơ chế của nó. Nếu nghiệp vụ có điều kiện như `stock >= quantity`, hãy đưa điều kiện vào chính câu lệnh và kiểm tra số dòng được cập nhật:

```sql
UPDATE inventory
SET stock = stock - :quantity
WHERE sku = :sku
  AND stock >= :quantity;
```

Nếu không có dòng nào được cập nhật, ứng dụng biết rằng SKU không tồn tại hoặc lượng tồn không đủ và có thể phân biệt hai trường hợp bằng cách đọc tiếp nếu cần. Đây là ví dụ cho thấy không phải mọi bài toán đều cần UPSERT; đôi khi một câu `UPDATE` có điều kiện đã biểu đạt đúng thao tác nghiệp vụ.

## 3. UPSERT là gì?

UPSERT là cách ghép hai ý định:

1. Thử chèn một bản ghi mới.
2. Nếu thao tác chèn gặp xung đột trên khóa duy nhất được chỉ định hoặc được DBMS nhận diện, xử lý xung đột bằng cách cập nhật bản ghi hiện có, bỏ qua thao tác hoặc thực hiện hành động khác theo cú pháp của DBMS.

Luồng khái niệm:

```text
Ứng dụng gửi một UPSERT
          |
          v
DBMS kiểm tra khóa duy nhất
          |
          +---- Chưa có xung đột ----> INSERT
          |                              |
          |                              v
          |                           COMMIT
          |
          +---- Có xung đột ---------> Xử lý conflict
                                         |
                                         +--> UPDATE
                                         |       hoặc
                                         +--> DO NOTHING
                                                 |
                                                 v
                                              COMMIT
```

Điểm khác biệt quan trọng là việc quyết định chèn hay xử lý xung đột được thực hiện bên trong cơ chế ghi của database, gắn với unique constraint/index. Ứng dụng không phải tự tách một lần đọc kiểm tra và một lần ghi thành hai thao tác độc lập không được bảo vệ.

UPSERT thường được gọi là atomic upsert, nhưng cần hiểu chính xác phạm vi của tính nguyên tử: một câu lệnh được thực thi theo transaction semantics của DBMS; nó không tự bảo vệ mọi quy tắc nghiệp vụ ở các bảng khác, không tự biến nhiều câu lệnh thành một transaction và không tự ngăn mọi dạng lost update.

## 4. UPSERT trong PostgreSQL

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT`. Ứng dụng có thể chỉ rõ unique constraint/index nào được dùng làm conflict target.

### 4.1. ON CONFLICT DO UPDATE

```sql
INSERT INTO customer (
    external_id, display_name, updated_at
)
VALUES (
    'crm-17', 'Lan', CURRENT_TIMESTAMP
)
ON CONFLICT (external_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    updated_at = EXCLUDED.updated_at;
```

Nếu chưa có `external_id = 'crm-17'`, PostgreSQL chèn dòng mới. Nếu unique constraint trên `external_id` xung đột, nó cập nhật dòng đang tồn tại. `EXCLUDED` đại diện cho dòng đề xuất chèn nhưng không thể được chèn vì conflict.

Có thể trả về dòng được chèn hoặc cập nhật:

```sql
INSERT INTO customer (
    external_id, display_name, updated_at
)
VALUES (
    :external_id, :display_name, CURRENT_TIMESTAMP
)
ON CONFLICT (external_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    updated_at = EXCLUDED.updated_at
RETURNING customer_id, external_id, display_name;
```

### 4.2. ON CONFLICT DO NOTHING

Nếu yêu cầu chỉ là tạo bản ghi khi chưa có và bỏ qua bản ghi trùng:

```sql
INSERT INTO customer (external_id, display_name, updated_at)
VALUES ('crm-17', 'Lan', CURRENT_TIMESTAMP)
ON CONFLICT (external_id) DO NOTHING;
```

Lệnh này không cập nhật dữ liệu cũ. Nếu cần biết dòng nào được chèn, có thể dùng `RETURNING`; khi conflict dẫn đến `DO NOTHING`, không có dòng nào được trả về từ thao tác đó.

### 4.3. Cập nhật có điều kiện

Có thể chỉ cập nhật nếu dữ liệu mới thực sự mới hơn:

```sql
INSERT INTO customer (
    external_id, display_name, source_version, updated_at
)
VALUES (
    :external_id, :display_name, :source_version, CURRENT_TIMESTAMP
)
ON CONFLICT (external_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    source_version = EXCLUDED.source_version,
    updated_at = EXCLUDED.updated_at
WHERE customer.source_version < EXCLUDED.source_version;
```

Điều kiện trong `DO UPDATE ... WHERE` giúp tránh sự kiện đến trễ ghi đè dữ liệu có phiên bản cao hơn. Khi điều kiện không đúng, dòng xung đột không được cập nhật; trong trường hợp đó, dòng cũng không xuất hiện trong kết quả `RETURNING` của lệnh.

Với `INSERT ... ON CONFLICT DO UPDATE` không có điều kiện lọc ở nhánh update, PostgreSQL xử lý mỗi dòng được đề xuất bằng insert hoặc update, trừ khi có lỗi độc lập khác. Nếu có `DO UPDATE ... WHERE`, một dòng xung đột có thể không được cập nhật khi điều kiện không đúng; trường hợp đó cũng không xuất hiện trong `RETURNING`. Cơ chế này được thiết kế để xử lý cạnh tranh trên unique constraint/index, kể cả khi một giao dịch khác đang đồng thời tạo cùng khóa.

## 5. UPSERT trong MySQL và InnoDB

MySQL dùng `INSERT ... ON DUPLICATE KEY UPDATE`:

```sql
INSERT INTO customer (
    external_id, display_name, updated_at
)
VALUES (
    'crm-17', 'Lan', CURRENT_TIMESTAMP
)
ON DUPLICATE KEY UPDATE
    display_name = 'Lan',
    updated_at = CURRENT_TIMESTAMP;
```

Nếu thao tác insert vi phạm `PRIMARY KEY` hoặc một `UNIQUE` index, MySQL thực hiện phần `UPDATE`. Nếu không có xung đột, nó chèn dòng mới.

Từ MySQL 8.0.19, row alias có thể được dùng sau phần `INSERT ... VALUES` để tham chiếu giá trị được đề xuất chèn mà không phải lặp lại literal:

```sql
INSERT INTO customer (
    external_id, display_name, updated_at
)
VALUES (
    :external_id, :display_name, CURRENT_TIMESTAMP
) AS incoming
ON DUPLICATE KEY UPDATE
    display_name = incoming.display_name,
    updated_at = incoming.updated_at;
```

Row alias trong ví dụ yêu cầu phiên bản MySQL hỗ trợ cú pháp này. Cách dùng `VALUES(column)` trong phần update đã bị đánh dấu deprecated từ MySQL 8.0.20; với hệ thống cũ, hãy kiểm tra cú pháp theo đúng phiên bản đang triển khai.

### 5.1. Khác biệt quan trọng về conflict target

Khác với PostgreSQL, `ON DUPLICATE KEY UPDATE` không cho chỉ định một conflict target duy nhất theo cú pháp `(external_id)`. Nó phản ứng khi insert xung đột với một primary key hoặc unique index. Nếu bảng có nhiều unique index, cần cẩn thận vì xung đột có thể xảy ra trên khóa khác với khóa nghiệp vụ mà ứng dụng dự định dùng để nhận diện bản ghi.

Ví dụ bảng có cả `UNIQUE(external_id)` và `UNIQUE(email)`. Dữ liệu mới có `external_id` chưa tồn tại nhưng email đã thuộc về một khách hàng khác. `ON DUPLICATE KEY UPDATE` có thể cập nhật dòng gây ra unique conflict, vì vậy ứng dụng có thể sửa nhầm bản ghi nếu không thiết kế các unique key và dữ liệu đầu vào rõ ràng.

Hãy đảm bảo rằng các unique constraint trong bảng phản ánh những quan hệ nhận diện có thể cập nhật an toàn theo cùng một quy tắc, hoặc xử lý các trường hợp xung đột khác nhau bằng luồng riêng.

### 5.2. Giá trị trả về và auto-increment

MySQL có quy tắc affected rows riêng cho insert, update và trường hợp update không làm thay đổi giá trị; driver cũng có thể ảnh hưởng cách ứng dụng nhận số dòng bị tác động. Một thao tác UPSERT có thể tiêu thụ giá trị auto-increment ngay cả khi cuối cùng đi theo nhánh update. Không nên dựa vào số ID liên tiếp hoặc một cách diễn giải affected rows chung cho mọi driver.

## 6. UPSERT trong SQLite

SQLite hỗ trợ UPSERT theo cú pháp `ON CONFLICT`:

```sql
INSERT INTO customer (
    external_id, display_name, updated_at
)
VALUES (
    'crm-17', 'Lan', CURRENT_TIMESTAMP
)
ON CONFLICT(external_id)
DO UPDATE SET
    display_name = excluded.display_name,
    updated_at = excluded.updated_at;
```

`excluded` là tên dùng để tham chiếu giá trị của dòng đề xuất chèn. SQLite cũng hỗ trợ `DO NOTHING`:

```sql
INSERT INTO customer (external_id, display_name, updated_at)
VALUES ('crm-17', 'Lan', CURRENT_TIMESTAMP)
ON CONFLICT(external_id) DO NOTHING;
```

SQLite có thêm cú pháp cũ `INSERT OR REPLACE`, nhưng **REPLACE không đồng nghĩa với UPSERT update**. Khi xung đột, `REPLACE` có thể xóa dòng cũ rồi chèn dòng mới. Điều này có thể ảnh hưởng khóa ngoại, trigger, row identity và các cột không được cung cấp trong dòng mới. Nếu ý định là cập nhật một số cột trên dòng hiện có, nên dùng `ON CONFLICT ... DO UPDATE` thay vì mặc định chọn `OR REPLACE`.

## 7. SQL Server: MERGE và mẫu UPDATE rồi INSERT có bảo vệ

SQL Server không có cú pháp `ON CONFLICT` tương đương PostgreSQL. Hai cách thường được xem xét là `MERGE` hoặc một transaction gồm `UPDATE` rồi `INSERT` nếu chưa có dòng.

### 7.1. MERGE

`MERGE` cho phép mô tả nguồn dữ liệu và điều kiện khớp để chọn nhánh update hoặc insert:

```sql
MERGE dbo.Customer AS target
USING (
    SELECT
        @ExternalId AS ExternalId,
        @DisplayName AS DisplayName
) AS source
ON target.ExternalId = source.ExternalId
WHEN MATCHED THEN
    UPDATE SET
        DisplayName = source.DisplayName,
        UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (ExternalId, DisplayName, UpdatedAt)
    VALUES (source.ExternalId, source.DisplayName, SYSUTCDATETIME());
```

`MERGE` có thể biểu đạt logic insert/update trong một câu lệnh, nhưng không nên giả định rằng mọi cách dùng `MERGE` tự động loại bỏ mọi race condition hoặc phù hợp với mọi workload. Cần có unique constraint trên khóa nhận diện, xem xét locking/isolation, kiểm thử với nhiều transaction đồng thời và đọc hướng dẫn theo phiên bản SQL Server. Các tình huống cạnh tranh insert cùng khóa có thể vẫn cần chiến lược khóa hoặc xử lý lỗi duplicate key.

### 7.2. UPDATE rồi INSERT trong cùng transaction

Một mẫu thường dùng là khóa phạm vi khi tìm dòng, sau đó insert nếu không có:

```sql
BEGIN TRANSACTION;

UPDATE dbo.Customer WITH (UPDLOCK, HOLDLOCK)
SET
    DisplayName = @DisplayName,
    UpdatedAt = SYSUTCDATETIME()
WHERE ExternalId = @ExternalId;

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.Customer (
        ExternalId, DisplayName, UpdatedAt
    )
    VALUES (
        @ExternalId, @DisplayName, SYSUTCDATETIME()
    );
END;

COMMIT TRANSACTION;
```

`UPDLOCK` yêu cầu update lock khi tìm kiếm; `HOLDLOCK` yêu cầu ngữ nghĩa tương đương `SERIALIZABLE` cho tham chiếu bảng, giúp giữ khóa phạm vi phù hợp đến hết transaction. Một index phù hợp trên `ExternalId` giúp SQL Server bảo vệ khoảng cần thiết. Vẫn cần unique constraint để đảm bảo dữ liệu không có khóa trùng nếu có code path khác hoặc lỗi logic.

Mẫu này khác với chuỗi `SELECT` rồi `INSERT` không được bảo vệ: bước tìm và quyết định insert nằm trong cùng transaction với khóa phù hợp. Tuy nhiên, hint khóa có thể làm tăng lock wait hoặc deadlock; cần đo và xử lý retry khi SQL Server chọn transaction làm nạn nhân deadlock.

## 8. Oracle: MERGE

Oracle hỗ trợ `MERGE` để đồng bộ dữ liệu nguồn với bảng đích:

```sql
MERGE INTO customer target
USING (
    SELECT
        :external_id AS external_id,
        :display_name AS display_name
    FROM dual
) source
ON (target.external_id = source.external_id)
WHEN MATCHED THEN
    UPDATE SET
        target.display_name = source.display_name,
        target.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (external_id, display_name, updated_at)
    VALUES (source.external_id, source.display_name, SYSTIMESTAMP);
```

`MERGE` phù hợp cho thao tác đồng bộ theo nguồn dữ liệu. Nhưng nếu hai session đồng thời cùng thấy khóa chưa có và cùng đi vào nhánh insert, unique constraint vẫn là hàng rào cuối cùng. Một session có thể gặp lỗi unique violation khi session kia chèn trước. Nếu nghiệp vụ yêu cầu đảm bảo hoàn tất, ứng dụng cần xử lý lỗi và retry/đọc lại theo chiến lược phù hợp.

## 9. So sánh các cú pháp theo DBMS

| DBMS | Cú pháp thường dùng | Chỉ định conflict target | Điểm cần chú ý |
|---|---|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT ... DO UPDATE/DO NOTHING` | Có thể chỉ rõ constraint hoặc cột/index phù hợp | `EXCLUDED` chứa giá trị đề xuất; có `RETURNING`; xử lý cạnh tranh trên arbiter constraint/index |
| MySQL/InnoDB | `INSERT ... ON DUPLICATE KEY UPDATE` | Không chọn một target riêng theo kiểu PostgreSQL | Bất kỳ primary/unique key conflict nào cũng có thể kích hoạt nhánh update |
| SQLite | `INSERT ... ON CONFLICT ... DO UPDATE/DO NOTHING` | Có | Dùng `excluded`; tránh nhầm `OR REPLACE` với update tại chỗ |
| SQL Server | `MERGE` hoặc transaction `UPDATE` + `INSERT` có khóa phù hợp | Điều kiện `ON` trong `MERGE` hoặc predicate của `UPDATE` | Cần unique constraint, xem xét concurrency và locking; không dựa vào `MERGE` một cách máy móc |
| Oracle | `MERGE` | Điều kiện `ON` | Cạnh tranh insert vẫn có thể gặp unique violation; cần xử lý lỗi theo nghiệp vụ |

Tên gọi UPSERT mô tả mục đích chung, không phải cam kết rằng mọi DBMS có cùng cú pháp, cùng cách chọn conflict target, cùng giá trị trả về hay cùng hành vi khi nhiều unique index cùng tồn tại.

## 10. UPSERT có tự giải quyết lost update không?

Không phải lúc nào cũng vậy. UPSERT giúp giải quyết cạnh tranh giữa insert và unique conflict, nhưng phần `UPDATE` vẫn phải thể hiện đúng phép biến đổi nghiệp vụ.

Giả sử bảng đếm số sự kiện theo ngày. Ứng dụng nhận một sự kiện mới và muốn tăng `event_count` thêm 1:

```sql
INSERT INTO daily_counter (counter_date, event_count)
VALUES (CURRENT_DATE, 1)
ON CONFLICT (counter_date)
DO UPDATE SET
    event_count = daily_counter.event_count + EXCLUDED.event_count;
```

Trong PostgreSQL, nhánh update cộng thêm vào giá trị hiện tại của dòng đích. Hai sự kiện đồng thời không cùng đọc một số đếm cũ ở phía ứng dụng rồi ghi đè bằng hai giá trị tính sẵn. Mỗi lần UPSERT cập nhật giá trị đích theo biểu thức trong database.

Ngược lại, nếu viết:

```sql
ON CONFLICT (counter_date)
DO UPDATE SET event_count = EXCLUDED.event_count;
```

thì mỗi sự kiện có thể thay giá trị đếm bằng giá trị gửi vào, không phải tăng số đếm. Câu lệnh vẫn là UPSERT hợp lệ, nhưng sai với nghiệp vụ bộ đếm.

Nếu nghiệp vụ cần thay thế theo phiên bản, hãy dùng điều kiện version/timestamp như ví dụ `source_version` ở trên. Nếu cần áp dụng một phép cộng, trừ hoặc chuyển trạng thái, hãy viết phép biến đổi dựa trên giá trị đích hiện tại và thêm điều kiện bảo vệ cần thiết.

## 11. UPSERT không thay thế mọi transaction hoặc constraint

UPSERT giải quyết một quyết định ghi trên một khóa duy nhất. Nó không tự đảm bảo mọi bất biến liên quan đến nhiều dòng hoặc nhiều bảng.

Ví dụ, quy tắc nghiệp vụ yêu cầu một khách hàng chỉ có tối đa ba địa chỉ đang hoạt động. UPSERT một địa chỉ theo `(customer_id, address_code)` không tự bảo vệ tổng số địa chỉ của khách hàng. Hai giao dịch có thể cùng thấy đang có hai địa chỉ rồi chèn hai địa chỉ khác nhau. Để bảo vệ quy tắc tổng hợp, cần thiết kế transaction, constraint phù hợp, khóa trên đối tượng điều phối hoặc mức cô lập có thể ngăn anomaly.

Các trường hợp cần xử lý riêng:

- **Khóa nhận diện không duy nhất:** nếu conflict key không có unique constraint/index, UPSERT không có điểm đồng bộ đáng tin cậy.
- **Nhiều bảng:** nếu một thao tác phải cập nhật customer, address và audit record cùng nhau, hãy bao quanh các câu lệnh cần thiết trong một transaction.
- **Điều kiện nghiệp vụ:** chỉ update khi trạng thái cũ cho phép, ví dụ `WHERE status = 'PENDING'`; kiểm tra số dòng tác động.
- **Phiên bản lạc hậu:** dùng version, sequence hoặc timestamp đáng tin cậy để tránh sự kiện cũ ghi đè sự kiện mới.
- **Phantom và quy tắc theo tập:** UPSERT theo một unique key không bảo vệ một predicate tổng quát trên nhiều dòng.
- **Tác dụng phụ:** trigger, audit, message hoặc lời gọi dịch vụ ngoài có thể chạy theo nhánh insert/update khác nhau; cần hiểu semantics của DBMS và tránh phát sự kiện trước commit.

## 12. Khóa duy nhất, NULL và thiết kế conflict key

Unique constraint là cơ sở để DBMS xác định xung đột, nhưng cách xử lý `NULL` trong unique index có thể khác nhau giữa sản phẩm và cấu hình.

Trong PostgreSQL, unique constraint mặc định coi các giá trị `NULL` là khác nhau, nên có thể tồn tại nhiều dòng có `NULL` trong cột unique; PostgreSQL mới có tùy chọn `NULLS NOT DISTINCT` để thay đổi hành vi này. MySQL cũng cho phép nhiều giá trị `NULL` trong unique index theo quy tắc của nó. Vì vậy, nếu khóa nhận diện bắt buộc phải có giá trị, hãy khai báo `NOT NULL`.

Với khóa ghép, cần xác định chính xác cặp hoặc bộ cột nào đại diện cho một thực thể:

```sql
CREATE TABLE product_price (
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    currency   CHAR(3) NOT NULL,
    price      DECIMAL(12, 2) NOT NULL,
    CONSTRAINT uq_product_price
        UNIQUE (tenant_id, product_id, currency)
);
```

UPSERT theo `(tenant_id, product_id, currency)` đảm bảo mỗi tenant có tối đa một giá cho một sản phẩm và một loại tiền. Nếu bỏ `tenant_id` khỏi conflict key, dữ liệu của hai tenant có thể bị cập nhật nhầm vào cùng một dòng.

Khóa duy nhất còn chịu ảnh hưởng của collation, quy tắc so sánh chuỗi và chuẩn hóa dữ liệu. Ví dụ `ABC` và `abc` có thể được xem là bằng nhau hoặc khác nhau tùy collation. Hãy thống nhất cách chuẩn hóa mã ngoài/email trước khi ghi và để unique index bảo vệ cùng quy tắc đó.

## 13. UPSERT, idempotency và xử lý request gửi lặp

UPSERT thường hữu ích trong đồng bộ và ingest dữ liệu vì một request có thể được gửi lại sau timeout. Tuy nhiên, UPSERT không tự làm mọi thao tác trở thành idempotent.

Ví dụ, nếu mỗi lần nhận request đều chạy:

```sql
ON CONFLICT (counter_date)
DO UPDATE SET event_count = daily_counter.event_count + 1;
```

thì gửi lại cùng một request sẽ tăng bộ đếm thêm lần nữa. Đây là phép cộng có tính lặp, không phải thao tác idempotent.

Muốn chống xử lý lặp, có thể dùng `idempotency_key` duy nhất cho từng request/sự kiện:

```sql
CREATE TABLE processed_event (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    event_type      VARCHAR(80) NOT NULL,
    processed_at    TIMESTAMP NOT NULL
);
```

Trong một transaction, ứng dụng ghi nhận idempotency key bằng insert có xử lý conflict. Chỉ khi key được chèn mới, nó mới áp dụng tác dụng phụ trong database. Nếu key đã tồn tại, request được xem là đã xử lý và ứng dụng trả lại kết quả phù hợp.

Ví dụ theo PostgreSQL:

```sql
BEGIN;

INSERT INTO processed_event (idempotency_key, event_type, processed_at)
VALUES (:key, :event_type, CURRENT_TIMESTAMP)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING idempotency_key;

-- Nếu RETURNING có dòng: lần đầu xử lý, tiếp tục cập nhật nghiệp vụ.
-- Nếu không có dòng: key đã được xử lý, bỏ qua tác dụng phụ lặp.

COMMIT;
```

Phần kiểm tra kết quả `RETURNING` và cập nhật nghiệp vụ phải nằm trong cùng transaction để nếu cập nhật nghiệp vụ thất bại, bản ghi đánh dấu processed cũng rollback. Với tác dụng phụ ngoài database, hãy cân nhắc transactional outbox và idempotency ở phía consumer.

## 14. Chọn UPSERT hay SELECT rồi INSERT/UPDATE?

| Nhu cầu | Cách tiếp cận thường phù hợp |
|---|---|
| Tạo nếu chưa có, cập nhật nếu đã có theo một unique key | UPSERT native của DBMS |
| Chỉ tạo nếu chưa có, bỏ qua bản ghi trùng | UPSERT với `DO NOTHING` hoặc cơ chế tương đương |
| Cập nhật bộ đếm theo phép cộng/trừ | Một câu `UPDATE` nguyên tử hoặc UPSERT với biểu thức dựa trên giá trị đích |
| Cần quyết định nghiệp vụ dựa trên nhiều dữ liệu rồi ghi nhiều bảng | Transaction tường minh, constraint/lock/isolation phù hợp; không chỉ dựa vào UPSERT đơn lẻ |
| Cần phát hiện dữ liệu thay đổi từ lúc đọc | Optimistic version check hoặc khóa phù hợp |
| DBMS không có cú pháp UPSERT mong muốn | Dùng transaction với locking/range protection và unique constraint |
| Cần chống xử lý lại cùng request | Idempotency key duy nhất và ghi nhận cùng transaction với tác dụng phụ dữ liệu |

Chuỗi `SELECT` rồi `INSERT` hoặc `UPDATE` vẫn có chỗ dùng, chẳng hạn khi ứng dụng cần đọc nhiều dữ liệu để quyết định một quy trình phức tạp. Nhưng nếu dùng chuỗi đó để thực hiện thao tác insert-if-absent/update-if-present, phải bảo vệ khoảng giữa đọc và ghi bằng transaction cùng khóa hoặc isolation level phù hợp, đồng thời vẫn có unique constraint làm hàng rào cuối cùng.

## 15. Cách thiết kế một thao tác UPSERT an toàn

Khi thiết kế thao tác đồng bộ hoặc ghi dữ liệu có thể đến đồng thời, hãy trả lời lần lượt:

1. Khóa nghiệp vụ nào nhận diện duy nhất một bản ghi: ID nội bộ, mã ngoài, email hay khóa ghép?
2. Khóa đó đã có `PRIMARY KEY`/`UNIQUE` và `NOT NULL` phù hợp chưa?
3. DBMS đang dùng cú pháp UPSERT nào và conflict target được chọn ra sao?
4. Nhánh update sẽ thay thế giá trị, cộng dồn, cập nhật có điều kiện hay chỉ bỏ qua?
5. Nếu dữ liệu đến sai thứ tự, có version/timestamp để ngăn bản cũ ghi đè bản mới không?
6. Nếu có nhiều unique index, một conflict ngoài ý muốn có thể khiến nhánh update tác động nhầm dòng không?
7. Có bất biến liên quan nhiều dòng/bảng cần transaction hoặc mức cô lập cao hơn không?
8. Ứng dụng cần lấy ID/dòng kết quả bằng `RETURNING`, `OUTPUT` hay cách riêng của DBMS nào?
9. Retry khi duplicate key, deadlock, serialization failure hoặc timeout được xử lý ra sao?
10. Request gửi lặp có tạo tác dụng phụ lặp hay cần idempotency key?

## 16. Kết luận

Chuỗi `SELECT` rồi `INSERT` hoặc `UPDATE` tách quyết định và hành động thành nhiều bước. Nếu không có khóa hoặc cơ chế cô lập bảo vệ khoảng giữa các bước, nhiều giao dịch có thể cùng thấy một trạng thái cũ rồi đưa ra quyết định không còn đúng. Unique constraint ngăn dữ liệu trùng, nhưng ứng dụng vẫn phải xử lý lỗi cạnh tranh; còn cập nhật dựa trên giá trị đã đọc có thể gây lost update.

UPSERT đưa thao tác chèn và xử lý unique conflict vào cơ chế ghi của DBMS, giúp xử lý insert-if-absent/update-if-present an toàn hơn cho một khóa nhận diện cụ thể. Tuy nhiên, cần chọn đúng conflict key, viết đúng biểu thức update, hiểu khác biệt cú pháp theo DBMS và dùng transaction/constraint bổ sung cho quy tắc rộng hơn. Khi request có thể được gửi lặp, hãy kết hợp idempotency key thay vì cho rằng UPSERT tự bảo đảm idempotency.

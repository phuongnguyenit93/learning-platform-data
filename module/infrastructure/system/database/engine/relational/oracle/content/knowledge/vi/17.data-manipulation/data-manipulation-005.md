# MERGE để đồng bộ dữ liệu và điều kiện khớp nguồn/đích

Trong Oracle Database, `MERGE` kết hợp thao tác cập nhật và chèn dữ liệu trong một câu DML. Câu lệnh này thường được dùng để đồng bộ bảng đích từ bảng staging, nạp dữ liệu theo batch, cập nhật danh mục hoặc áp dụng dữ liệu mới từ một nguồn vào bảng đang phục vụ ứng dụng.

Ý tưởng cốt lõi là so sánh hàng nguồn với hàng đích bằng điều kiện `ON`:

- Nếu một hàng nguồn **khớp** với hàng đích, nhánh `WHEN MATCHED` có thể cập nhật hàng đích.
- Nếu một hàng nguồn **không khớp** với hàng đích, nhánh `WHEN NOT MATCHED` có thể chèn hàng mới.

Điều kiện `ON` quyết định ranh giới giữa “đã tồn tại” và “chưa tồn tại”. Đặt sai điều kiện khớp có thể khiến một hàng đã tồn tại bị coi là mới, dẫn đến chèn trùng khóa hoặc đồng bộ sai dữ liệu. Ngoài ra, nguồn phải được chuẩn hóa để không có nhiều hàng cùng cập nhật một hàng đích.

Bài học trình bày cú pháp `MERGE` của Oracle, cách thiết kế khóa khớp, sự khác nhau giữa `ON` và điều kiện `UPDATE WHERE`/`INSERT WHERE`, xử lý nguồn trùng, đồng bộ theo batch, các giới hạn quan trọng và cách kiểm chứng kết quả.

## 1. MERGE làm gì?

Một câu `MERGE` có hai nguồn:

- **Target (đích):** bảng cần được thay đổi.
- **Source (nguồn):** bảng, view hoặc subquery cung cấp các hàng cần đồng bộ.

Mỗi hàng nguồn được so khớp với hàng đích theo điều kiện `ON`. Tùy kết quả, Oracle thực hiện nhánh UPDATE hoặc INSERT được khai báo.

~~~text
                    SOURCE ROW
                         |
                         v
                  Evaluate ON condition
                    /           \
                 MATCH         NO MATCH
                   |              |
                   v              v
            WHEN MATCHED    WHEN NOT MATCHED
                   |              |
              UPDATE?          INSERT?
                   |              |
                   v              v
             TARGET ROW      NEW TARGET ROW
~~~

`MERGE` phù hợp với mô hình **upsert** (update nếu tồn tại, insert nếu chưa tồn tại). Tuy nhiên, nó không tự động đồng nghĩa với “làm cho hai bảng giống hệt nhau”: những hàng chỉ tồn tại ở target nhưng không có trong source sẽ không tự bị xóa.

## 2. Cú pháp MERGE cơ bản trong Oracle

~~~sql
MERGE INTO target_table t
USING source_table s
   ON (t.business_key = s.business_key)
WHEN MATCHED THEN
    UPDATE SET
        t.column_a = s.column_a,
        t.column_b = s.column_b
WHEN NOT MATCHED THEN
    INSERT (business_key, column_a, column_b)
    VALUES (s.business_key, s.column_a, s.column_b);
~~~

| Thành phần | Vai trò |
| --- | --- |
| `MERGE INTO target_table t` | Chọn bảng đích và alias `t` |
| `USING source_table s` | Chọn nguồn dữ liệu và alias `s` |
| `ON (...)` | Xác định hàng nguồn có khớp hàng đích hay không |
| `WHEN MATCHED THEN UPDATE` | Cập nhật hàng đích đã khớp |
| `WHEN NOT MATCHED THEN INSERT` | Chèn hàng nguồn chưa có hàng đích tương ứng |

Trong cú pháp Oracle, `WHEN MATCHED` là nhánh cập nhật; `WHEN NOT MATCHED` là nhánh chèn. Các nhánh có thể có điều kiện bổ sung. Oracle không dùng cú pháp `WHEN NOT MATCHED BY SOURCE` như một số hệ quản trị cơ sở dữ liệu khác.

## 3. Chuẩn bị dữ liệu lab nguồn và đích

Ta dùng ví dụ đồng bộ danh mục khách hàng. Bảng đích chứa thông tin ứng dụng đang sử dụng; bảng staging chứa dữ liệu nhận từ một batch bên ngoài.

Chạy các lệnh trong schema thực hành do bạn sở hữu, có quyền tạo bảng và quota tablespace.

### 3.1. Tạo bảng đích

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    email       VARCHAR2(200 CHAR),
    status      VARCHAR2(12 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    updated_at  TIMESTAMP,
    CONSTRAINT ck_lab_customers_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

`CUSTOMER_ID` là khóa chính và sẽ là khóa định danh dùng để khớp nguồn/đích.

### 3.2. Tạo bảng staging

~~~sql
CREATE TABLE lab_customer_stage (
    batch_id          NUMBER NOT NULL,
    source_row_id     NUMBER PRIMARY KEY,
    customer_id       NUMBER NOT NULL,
    full_name         VARCHAR2(100 CHAR) NOT NULL,
    email             VARCHAR2(200 CHAR),
    source_status     VARCHAR2(12 CHAR),
    source_updated_at TIMESTAMP NOT NULL
);
~~~

`SOURCE_ROW_ID` định danh một hàng nhận được từ nguồn. `CUSTOMER_ID` không unique ở staging trong thiết kế này: cùng một khách hàng có thể xuất hiện nhiều lần trong một batch do nguồn gửi bản ghi lặp hoặc nhiều phiên bản cập nhật. Trước khi MERGE, ta phải quyết định cách chọn một bản ghi có thẩm quyền.

### 3.3. Dữ liệu hiện có ở target

~~~sql
INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (1, 'An Nguyen', 'an.old@example.test', 'ACTIVE',
     TIMESTAMP '2024-01-01 09:00:00');

INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (2, 'Binh Tran', 'binh@example.test', 'ACTIVE',
     TIMESTAMP '2024-01-02 09:00:00');

INSERT INTO lab_customers
    (customer_id, full_name, email, status, updated_at)
VALUES
    (4, 'Dung Le', 'dung@example.test', 'INACTIVE',
     TIMESTAMP '2024-01-04 09:00:00');

COMMIT;
~~~

### 3.4. Dữ liệu nguồn của batch 100

~~~sql
INSERT INTO lab_customer_stage VALUES
    (100, 1001, 1, 'An Nguyen', 'an.new@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:00:00');

INSERT INTO lab_customer_stage VALUES
    (100, 1002, 2, 'Binh Tran', 'binh@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:05:00');

INSERT INTO lab_customer_stage VALUES
    (100, 1003, 3, 'Chi Pham', 'chi@example.test', 'ACTIVE',
     TIMESTAMP '2024-02-01 10:10:00');

COMMIT;
~~~

Trạng thái trước khi MERGE:

| CUSTOMER_ID | TARGET | SOURCE BATCH 100 | Kết quả mong muốn |
| ---: | --- | --- | --- |
| 1 | Có, email cũ | Có, email mới | UPDATE |
| 2 | Có, dữ liệu giống nhau | Có | Không cần UPDATE |
| 3 | Chưa có | Có | INSERT |
| 4 | Có, INACTIVE | Không có | Giữ nguyên |

Đây là đồng bộ theo batch: chỉ các khách hàng xuất hiện trong batch nguồn được xét để cập nhật hoặc chèn. Hàng target 4 không có trong source nên vẫn tồn tại.

## 4. MERGE cơ bản: khớp thì UPDATE, không khớp thì INSERT

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT
        customer_id,
        full_name,
        email,
        source_status,
        source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name  = s.full_name,
        t.email      = s.email,
        t.status     = s.source_status,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        full_name,
        email,
        status,
        updated_at
    )
    VALUES (
        s.customer_id,
        s.full_name,
        s.email,
        s.source_status,
        s.source_updated_at
    );
~~~

Kết quả mong muốn:

| CUSTOMER_ID | FULL_NAME | EMAIL | STATUS |
| ---: | --- | --- | --- |
| 1 | An Nguyen | an.new@example.test | ACTIVE |
| 2 | Binh Tran | binh@example.test | ACTIVE |
| 3 | Chi Pham | chi@example.test | ACTIVE |
| 4 | Dung Le | dung@example.test | INACTIVE |

Giải thích:

- ID 1 khớp theo `CUSTOMER_ID`, được UPDATE email và timestamp.
- ID 2 khớp, được gán lại cùng các giá trị nguồn. Dù dữ liệu không đổi, nhánh UPDATE vẫn được thực hiện vì không có điều kiện `UPDATE WHERE`.
- ID 3 không tìm thấy trong target, được INSERT.
- ID 4 không xuất hiện trong source nên MERGE không tác động.

Để chạy lại bài lab từ đầu, cần khôi phục dữ liệu target/stage hoặc dùng batch mới và điều chỉnh dữ liệu tương ứng. Không chạy lặp các lệnh INSERT ban đầu trên cùng bảng nếu khóa chính đã tồn tại.

## 5. Điều kiện ON: định nghĩa thế nào là cùng một bản ghi

`ON` là phần quan trọng nhất của MERGE. Nó xác định hàng nguồn có đại diện cho cùng một thực thể với hàng đích hay không.

### 5.1. Dùng khóa định danh ổn định

Ví dụ tốt:

~~~sql
ON (t.customer_id = s.customer_id)
~~~

Nếu `CUSTOMER_ID` là khóa chính ở target và là định danh do hệ thống nguồn cung cấp ổn định, đây là điều kiện khớp rõ ràng.

Không nên khớp theo tên hiển thị nếu tên có thể thay đổi hoặc không duy nhất:

~~~sql
ON (t.full_name = s.full_name)
~~~

Hai khách hàng khác nhau có thể cùng tên; một khách hàng có thể đổi tên. Dùng thuộc tính mô tả để định danh có thể làm một hàng nguồn ghép nhầm hàng đích hoặc không tìm thấy hàng cần cập nhật.

### 5.2. Khóa ghép (composite key)

Nếu định danh chỉ duy nhất khi kết hợp nhiều cột, phải đưa đủ thành phần vào ON:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_customer_id = s.external_customer_id
)
~~~

Chỉ dùng `EXTERNAL_CUSTOMER_ID` có thể ghép nhầm hai khách hàng ở hai tenant khác nhau. Điều kiện ON cần phản ánh đúng unique key nghiệp vụ, đồng thời target nên có unique constraint tương ứng để bảo vệ dữ liệu.

### 5.3. Chuẩn hóa khóa văn bản

Nếu quy tắc nghiệp vụ không phân biệt chữ hoa/thường hoặc khoảng trắng đầu/cuối, hai giá trị có thể cần được chuẩn hóa:

~~~sql
ON (
    UPPER(TRIM(t.external_code)) =
    UPPER(TRIM(s.external_code))
)
~~~

Chỉ dùng biểu thức chuẩn hóa khi đó là quy tắc định danh được thống nhất. Các lưu ý:

- `TRIM` không giải quyết mọi loại khoảng trắng Unicode hoặc mọi quy tắc chuẩn hóa.
- `UPPER` phụ thuộc ngữ nghĩa collation/NLS và bộ ký tự trong môi trường.
- Biểu thức trên có thể làm index thông thường khó được sử dụng; nếu cần, cân nhắc function-based index hoặc lưu một cột khóa chuẩn hóa.
- Target phải duy nhất theo chính quy tắc chuẩn hóa đó; nếu hai giá trị khác nhau sau lưu trữ trở thành cùng khóa chuẩn hóa, MERGE có thể ghép nhiều hàng.

### 5.4. NULL trong khóa khớp

Với:

~~~sql
ON (t.external_code = s.external_code)
~~~

nếu cả hai `EXTERNAL_CODE` đều NULL, phép so sánh vẫn là UNKNOWN chứ không phải TRUE. Vì vậy hai hàng có khóa NULL không được coi là khớp.

Nếu khóa là NOT NULL theo mô hình dữ liệu, đây là điều mong muốn. Nếu khóa nguồn có thể NULL, cần xác định cách xử lý:

- Từ chối hoặc quarantine hàng nguồn thiếu khóa.
- Dùng một khóa định danh khác.
- Chỉ khi nghiệp vụ quy định rõ, viết điều kiện NULL-safe có chủ đích.

Không dùng một sentinel như `NVL(key, -1)` hoặc `NVL(code, 'UNKNOWN')` nếu giá trị đó có thể là khóa thật hoặc tạo va chạm.

### 5.5. Không dùng điều kiện cập nhật làm điều kiện nhận diện

Giả sử target có khách hàng ID 4, trạng thái INACTIVE. Nếu viết:

~~~sql
ON (
    t.customer_id = s.customer_id
    AND t.status = 'ACTIVE'
)
~~~

thì hàng nguồn ID 4 sẽ không khớp target vì trạng thái target là INACTIVE. Oracle coi hàng nguồn là NOT MATCHED và đi vào nhánh INSERT. Nếu `CUSTOMER_ID` là primary key, thao tác INSERT có thể thất bại với `ORA-00001` do khóa đã tồn tại.

Thông thường, `ON` nên xác định **cùng thực thể** bằng khóa định danh. Nếu chỉ muốn cập nhật những target đang ACTIVE, đặt điều kiện ở nhánh UPDATE:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE t.status = 'ACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

Với target ID 4, ON vẫn khớp thực thể; UPDATE WHERE không cho cập nhật vì trạng thái inactive. Hàng đó **không chuyển sang nhánh INSERT**. Với ID mới 3, nhánh INSERT vẫn hoạt động.

## 6. Điều kiện WHERE trong các nhánh MERGE

Oracle cho phép điều kiện bổ sung trong nhánh UPDATE và INSERT. Chúng có vai trò khác điều kiện ON.

### 6.1. UPDATE WHERE: chỉ cập nhật khi cần

Một câu MERGE không điều kiện sẽ UPDATE cả hàng đã khớp, kể cả khi các cột không đổi. Có thể tránh DML không cần thiết:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 100
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE
        t.full_name <> s.full_name
        OR t.email <> s.email
        OR t.status <> s.source_status;
~~~

Đây là ví dụ cơ bản, nhưng có một vấn đề: phép so sánh `<>` không phát hiện thay đổi từ NULL sang giá trị hoặc từ giá trị sang NULL. Ví dụ `t.email` là NULL và `s.email` là chuỗi, `t.email <> s.email` là UNKNOWN chứ không phải TRUE.

### 6.2. So sánh NULL-safe trong UPDATE WHERE

Có thể viết rõ các trường hợp:

~~~sql
WHERE
       t.full_name <> s.full_name
    OR (t.full_name IS NULL AND s.full_name IS NOT NULL)
    OR (t.full_name IS NOT NULL AND s.full_name IS NULL)
    OR t.email <> s.email
    OR (t.email IS NULL AND s.email IS NOT NULL)
    OR (t.email IS NOT NULL AND s.email IS NULL)
    OR t.status <> s.source_status
    OR (t.status IS NULL AND s.source_status IS NOT NULL)
    OR (t.status IS NOT NULL AND s.source_status IS NULL)
~~~

Với `FULL_NAME` và `STATUS` được khai báo NOT NULL ở lab, các nhánh NULL-safe tương ứng là dư thừa nhưng cho thấy mẫu tổng quát. Có thể dùng `DECODE` của Oracle để so sánh hai giá trị có xử lý NULL:

~~~sql
WHERE
       DECODE(t.full_name, s.full_name, 0, 1) = 1
    OR DECODE(t.email, s.email, 0, 1) = 1
    OR DECODE(t.status, s.source_status, 0, 1) = 1
~~~

`DECODE` coi hai NULL là bằng nhau theo ngữ nghĩa riêng của hàm. Nếu dùng, hãy thống nhất kiểu dữ liệu và hiểu quy tắc implicit conversion của DECODE. Dạng điều kiện tường minh dễ đọc khi logic phức tạp; DECODE ngắn gọn khi so sánh các giá trị cùng kiểu.

### 6.3. INSERT WHERE: giới hạn hàng được chèn

Ví dụ chỉ chèn khách hàng có trạng thái nguồn hợp lệ:

~~~sql
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, full_name, email, status, updated_at
    )
    VALUES (
        s.customer_id, s.full_name, s.email,
        s.source_status, s.source_updated_at
    )
    WHERE s.source_status IN ('ACTIVE', 'INACTIVE')
~~~

Điều kiện ở INSERT WHERE chỉ quyết định hàng NOT MATCHED có được chèn hay không. Nó không biến một hàng MATCHED thành NOT MATCHED và không thay đổi kết quả so khớp ON.

## 7. Đồng bộ nguồn có nhiều hàng cho cùng một khóa

Một lỗi quan trọng của MERGE là source trả nhiều hàng cùng khớp một hàng target. Oracle yêu cầu MERGE có tính xác định: một hàng target không thể bị UPDATE nhiều lần trong cùng một câu MERGE.

### 7.1. Ví dụ nguồn bị trùng khóa

Giả sử staging có hai phiên bản cho cùng khách hàng:

~~~sql
INSERT INTO lab_customer_stage VALUES
    (200, 2001, 10, 'Mai Nguyen', 'mai.old@example.test', 'ACTIVE',
     TIMESTAMP '2024-03-01 09:00:00');

INSERT INTO lab_customer_stage VALUES
    (200, 2002, 10, 'Mai Nguyen', 'mai.new@example.test', 'ACTIVE',
     TIMESTAMP '2024-03-02 09:00:00');

COMMIT;
~~~

Hai hàng có cùng `CUSTOMER_ID = 10` nhưng email/timestamp khác nhau. Nếu MERGE trực tiếp batch 200:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = 200
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

Nếu ID 10 đã tồn tại ở target, hai hàng nguồn cùng nhắm tới một hàng đích. Oracle có thể báo `ORA-30926: unable to get a stable set of rows in the source tables` vì cùng một target row bị tác động nhiều lần. Nếu ID 10 chưa tồn tại, cả hai hàng có thể đi vào nhánh INSERT và đụng unique constraint. Vì vậy phải chuẩn hóa source trước MERGE, bất kể target hiện đang có hay chưa có khóa đó.

### 7.2. Chọn bản ghi mới nhất bằng ROW_NUMBER

Nếu quy tắc là “mỗi khách hàng chỉ lấy phiên bản nguồn mới nhất”, dùng analytic function để chọn đúng một hàng:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT
        customer_id,
        full_name,
        email,
        source_status,
        source_updated_at
    FROM (
        SELECT
            stg.customer_id,
            stg.full_name,
            stg.email,
            stg.source_status,
            stg.source_updated_at,
            ROW_NUMBER() OVER (
                PARTITION BY stg.customer_id
                ORDER BY
                    stg.source_updated_at DESC,
                    stg.source_row_id DESC
            ) AS rn
        FROM lab_customer_stage stg
        WHERE stg.batch_id = 200
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

`ROW_NUMBER` tạo một số thứ tự trong từng customer. `SOURCE_UPDATED_AT DESC` chọn bản mới nhất; `SOURCE_ROW_ID DESC` là tie-breaker để kết quả ổn định khi timestamp trùng nhau. Kết quả subquery chỉ còn tối đa một hàng cho mỗi `CUSTOMER_ID`.

Không chọn hàng mới nhất chỉ bằng `MAX(source_updated_at)` rồi join ngược nếu có thể có nhiều hàng cùng timestamp; cách đó vẫn có thể tạo nhiều hàng nguồn. Hãy có tie-breaker duy nhất hoặc quy tắc tổng hợp rõ ràng.

### 7.3. Khi nguồn là dữ liệu giao dịch, có thể phải aggregate

Không phải lúc nào nhiều hàng nguồn cũng là phiên bản trùng. Nếu source chứa nhiều giao dịch cần cộng dồn, hãy tổng hợp theo khóa đích:

~~~sql
USING (
    SELECT
        account_id,
        SUM(transaction_amount) AS batch_amount
    FROM staging_transactions
    WHERE batch_id = :batch_id
    GROUP BY account_id
) s
~~~

Kết quả subquery có một hàng mỗi account. Dùng `ROW_NUMBER` khi chọn một phiên bản; dùng `GROUP BY` khi nhiều dòng phải đóng góp vào một giá trị tổng hợp. Hai quy tắc không thay thế cho nhau.

## 8. Nguồn phải khớp đúng batch

Trong bảng staging, batch ID là một phần của phạm vi dữ liệu nguồn. Nếu bỏ điều kiện batch, MERGE có thể lấy lại dữ liệu của các lần nạp trước:

~~~sql
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
) s
~~~

Đây thường là lỗi nguy hiểm vì hàng nguồn cũ có thể ghi đè dữ liệu mới. Hãy lọc batch ngay trong source subquery:

~~~sql
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
~~~

Nếu source chứa nhiều hệ thống hoặc tenant, batch/source-system/tenant cũng có thể là một phần của phạm vi nguồn hoặc khóa ghép. Không đưa điều kiện lọc batch vào ON chỉ để thay thế lọc source; việc đó có thể làm thay đổi ý nghĩa MATCHED/NOT MATCHED.

## 9. Chỉ cập nhật khi dữ liệu nguồn mới hơn

Một quy tắc đồng bộ phổ biến là chỉ ghi đè target khi phiên bản nguồn mới hơn:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    WHERE s.source_updated_at > t.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

Điều kiện này ngăn một bản nguồn cũ ghi đè bản mới hơn. Nhưng phải quyết định rõ cách xử lý khi `T.UPDATED_AT` NULL:

- Nếu NULL nghĩa là target chưa từng được đồng bộ, có thể dùng `t.updated_at IS NULL OR s.source_updated_at > t.updated_at`.
- Nếu timestamp nguồn có thể NULL, phải từ chối hoặc quy định thứ tự riêng.
- Nếu đồng hồ của các hệ thống nguồn không đồng bộ, timestamp không phải lúc nào cũng là phiên bản đáng tin cậy; có thể cần sequence/version number từ hệ thống nguồn.

Ví dụ xử lý target timestamp NULL:

~~~sql
WHERE t.updated_at IS NULL
   OR s.source_updated_at > t.updated_at
~~~

## 10. MERGE có thể xóa hàng không?

Oracle hỗ trợ `DELETE WHERE` bên trong nhánh UPDATE:

~~~sql
MERGE INTO lab_customers t
USING (
    SELECT customer_id, full_name, email, source_status, source_updated_at
    FROM lab_customer_stage
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.full_name = s.full_name,
        t.email = s.email,
        t.status = s.source_status,
        t.updated_at = s.source_updated_at
    DELETE WHERE t.status = 'INACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, full_name, email, status, updated_at)
    VALUES (s.customer_id, s.full_name, s.email,
            s.source_status, s.source_updated_at);
~~~

Điểm cần nhớ:

- `DELETE WHERE` chỉ áp dụng cho các hàng đã được UPDATE bởi nhánh MATCHED.
- Điều kiện DELETE được đánh giá trên **giá trị sau UPDATE**.
- Hàng NOT MATCHED được INSERT không đi qua DELETE WHERE.
- Hàng target không có hàng source tương ứng cũng không bị xóa.

Ví dụ nếu source cập nhật trạng thái khách hàng từ ACTIVE thành INACTIVE, hàng target được cập nhật trước, sau đó có thể bị xóa do trạng thái sau cập nhật là INACTIVE. Đây là thao tác có tác động mạnh đến dữ liệu, cần dùng đúng khi quy tắc nghiệp vụ thật sự yêu cầu.

Nếu muốn xóa target khi **không còn xuất hiện trong một snapshot source**, `DELETE WHERE` trong MERGE không giải quyết yêu cầu đó. Cần một câu DELETE riêng với `NOT EXISTS` hoặc cơ chế đồng bộ snapshot có phạm vi rõ ràng:

~~~sql
DELETE FROM lab_customers t
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_customer_stage s
    WHERE s.batch_id = :complete_snapshot_batch
      AND s.customer_id = t.customer_id
);
~~~

Chỉ chạy kiểu DELETE này khi batch là **snapshot đầy đủ** của phạm vi dữ liệu cần đồng bộ. Nếu batch chỉ chứa thay đổi tăng dần (delta), một hàng không xuất hiện có thể đơn giản là không thay đổi; xóa nó sẽ làm mất dữ liệu. MERGE và DELETE nên được thiết kế trong cùng quy trình/transaction phù hợp, với khóa batch và quy tắc snapshot được kiểm soát.

## 11. MERGE và khóa chính/unique constraint

Điều kiện ON chỉ mô tả cách so khớp; nó không tự bảo vệ tính duy nhất của dữ liệu. Target nên có primary key hoặc unique constraint phù hợp với khóa khớp.

Ví dụ:

~~~sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_email
UNIQUE (email);
~~~

Chỉ thêm constraint này nếu nghiệp vụ bảo đảm email duy nhất và dữ liệu hiện tại không có vi phạm. Trong bài lab, email nullable; Oracle unique constraint cho phép nhiều hàng có NULL theo quy tắc của Oracle. Không dùng email làm khóa MERGE chỉ vì có unique constraint nếu email có thể thay đổi hoặc không phải định danh ổn định.

Các lớp bảo vệ nên gồm:

- Target primary key/unique constraint trên định danh thực thể.
- Unique constraint hoặc kiểm tra nguồn để bảo đảm một hàng source trên mỗi khóa đích.
- NOT NULL cho các thành phần bắt buộc của khóa.
- Foreign key/check constraint cho quy tắc dữ liệu liên quan.
- Quy trình xử lý hàng nguồn lỗi hoặc thiếu khóa trước khi MERGE.

## 12. MERGE là deterministic: tránh cập nhật cùng hàng đích nhiều lần

Oracle mô tả `MERGE` là deterministic: một câu MERGE không thể UPDATE cùng một hàng target nhiều hơn một lần. Nếu nhiều hàng nguồn cùng khớp một target row, câu lệnh có thể báo:

~~~text
ORA-30926: unable to get a stable set of rows in the source tables
~~~

Nếu nhiều hàng source không khớp cùng một target key, chúng có thể cùng đi vào nhánh INSERT và vi phạm unique constraint. Hai trường hợp đều bắt nguồn từ việc nguồn không có một hàng rõ ràng cho mỗi định danh đích.

Trước khi MERGE, kiểm tra:

~~~sql
SELECT customer_id, COUNT(*) AS source_rows
FROM lab_customer_stage
WHERE batch_id = :batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả hàng, phải quyết định quy tắc deduplicate/aggregate trước khi MERGE. Không dùng `DISTINCT` tùy tiện trên tất cả cột: hai phiên bản có cùng ID nhưng email khác nhau vẫn không bị DISTINCT loại, còn việc loại trùng các cột hiển thị không xác định được phiên bản nào đúng.

## 13. Điều kiện ON và giới hạn cập nhật cột khóa

Oracle không cho cập nhật cột target được tham chiếu trong điều kiện ON của cùng MERGE. Ví dụ:

~~~sql
MERGE INTO lab_customers t
USING source_customers s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_id = s.new_customer_id;
~~~

Đây là kiểu thiết kế không hợp lệ vì `CUSTOMER_ID` đang được dùng trong ON. Nếu cần thay đổi định danh, phải thiết kế thao tác riêng, có xét đến khóa ngoại, uniqueness, các bảng liên quan và quy tắc chuyển đổi danh tính. Đừng cố dùng MERGE để vừa nhận diện hàng bằng một khóa vừa thay đổi chính khóa đó trong cùng nhánh UPDATE.

## 14. Điều kiện nguồn/đích theo nhiều trạng thái

| Tình huống | ON | UPDATE WHERE | INSERT WHERE |
| --- | --- | --- | --- |
| Cùng khách hàng, dữ liệu đổi | Khớp theo ID | TRUE | Không áp dụng |
| Cùng khách hàng, dữ liệu không đổi | Khớp theo ID | FALSE nếu so sánh thay đổi | Không áp dụng |
| Cùng khách hàng nhưng target bị khóa/inactive | Vẫn khớp theo ID | FALSE nếu không được cập nhật | Không áp dụng; không INSERT |
| Khách hàng mới, nguồn hợp lệ | Không khớp | Không áp dụng | TRUE |
| Khách hàng mới, nguồn không hợp lệ | Không khớp | Không áp dụng | FALSE hoặc loại khỏi source |
| Khách hàng target không có trong source | Không có source row để so khớp | Không chạy | Không chạy |

Bảng này cho thấy ba điều kiện có ba nhiệm vụ riêng:

- `ON`: nhận diện cùng thực thể.
- `UPDATE WHERE`: quyết định có cập nhật hàng đã khớp không.
- `INSERT WHERE`: quyết định có chèn hàng chưa khớp không.

Nếu trộn cả ba thành một biểu thức ON, kết quả phân nhánh có thể sai.

## 15. Giao dịch, lỗi và đồng bộ đồng thời

`MERGE` là một câu lệnh DML. Các thao tác UPDATE/INSERT thuộc cùng câu lệnh và tuân theo tính nguyên tử của statement: nếu câu lệnh thất bại, các thay đổi của statement được rollback theo cơ chế Oracle. Tuy nhiên, transaction có thể còn những DML trước đó chưa commit.

Các điểm cần thiết kế:

1. **Không commit giữa chừng bên trong một câu MERGE.** Commit/rollback thuộc transaction của ứng dụng hoặc quy trình batch.
2. **Giữ unique constraint ở target.** Điều kiện ON không phải cơ chế thay thế ràng buộc.
3. **Xử lý cạnh tranh giữa nhiều session.** Hai session cùng MERGE một khóa chưa tồn tại có thể cùng đi đến nhánh INSERT; unique constraint bảo vệ dữ liệu, nhưng một session có thể nhận lỗi unique violation tùy thứ tự commit/khóa.
4. **Thiết kế retry có kiểm soát.** Nếu lỗi do cạnh tranh, ứng dụng có thể retry theo chính sách transaction phù hợp sau khi đọc trạng thái mới; không retry mù mọi lỗi.
5. **Gắn batch ID và lưu trạng thái xử lý.** Điều này giúp chạy lại có kiểm soát, điều tra hàng lỗi và tránh trộn dữ liệu nhiều lần nạp.
6. **Kiểm soát timestamp/version từ nguồn.** Không để dữ liệu cũ ghi đè dữ liệu mới khi batch đến trễ.

Một MERGE đơn lẻ không tự giải quyết mọi bài toán đồng bộ phân tán. Cần xác định nguồn là snapshot hay delta, thứ tự batch, khóa định danh, tính lặp an toàn (idempotency), và cách xử lý xung đột giữa các writer.

## 16. Kiểm tra dữ liệu trước và sau MERGE

### 16.1. Đếm nguồn theo batch

~~~sql
SELECT
    COUNT(*) AS source_rows,
    COUNT(DISTINCT customer_id) AS distinct_customers
FROM lab_customer_stage
WHERE batch_id = :batch_id;
~~~

Nếu hai số khác nhau, nguồn có customer ID lặp. Điều này không nhất thiết là lỗi nếu quy trình có quy tắc chọn phiên bản hoặc tổng hợp, nhưng phải xử lý trước MERGE.

### 16.2. Tìm khóa nguồn chưa có target

~~~sql
SELECT s.customer_id
FROM lab_customer_stage s
WHERE s.batch_id = :batch_id
  AND NOT EXISTS (
      SELECT 1
      FROM lab_customers t
      WHERE t.customer_id = s.customer_id
  );
~~~

Đây là tập khóa dự kiến đi vào nhánh INSERT nếu không bị điều kiện khác loại.

### 16.3. Tìm khóa nguồn đã có target

~~~sql
SELECT s.customer_id
FROM lab_customer_stage s
JOIN lab_customers t
  ON t.customer_id = s.customer_id
WHERE s.batch_id = :batch_id;
~~~

Đây là tập khóa dự kiến đi vào nhánh MATCHED. Điều kiện UPDATE WHERE có thể khiến một số hàng trong tập này không thực sự được cập nhật.

### 16.4. So sánh trạng thái sau đồng bộ

~~~sql
SELECT
    t.customer_id,
    t.full_name,
    t.email,
    t.status,
    t.updated_at
FROM lab_customers t
ORDER BY t.customer_id;
~~~

Đối chiếu kết quả với quy tắc batch, không chỉ dựa vào số hàng tổng. Một batch có thể UPDATE một số hàng, INSERT một số hàng, bỏ qua một số hàng và giữ nguyên target-only rows.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hàng đã có nhưng MERGE cố INSERT | ON có thêm điều kiện trạng thái/thuộc tính không phải khóa | Dùng ON theo khóa định danh; chuyển điều kiện cập nhật sang UPDATE WHERE |
| ORA-00001 ở nhánh INSERT | Hàng target tồn tại nhưng ON không nhận diện là MATCHED, hoặc có cạnh tranh đồng thời | Kiểm tra ON, unique key và concurrency |
| ORA-30926 | Nhiều hàng source cùng tác động một hàng target | Deduplicate bằng ROW_NUMBER hoặc aggregate theo quy tắc |
| MERGE chèn nhiều hàng trùng khóa | Source có nhiều hàng cùng key chưa tồn tại ở target | Chuẩn hóa source và giữ unique constraint |
| Dữ liệu target bị ghi đè bởi phiên bản cũ | Không lọc batch hoặc không so sánh version | Lọc batch và dùng timestamp/version có quy tắc |
| Thay đổi NULL không được phát hiện | Dùng `<>` đơn thuần trong UPDATE WHERE | So sánh NULL-safe bằng điều kiện tường minh hoặc DECODE |
| Hai khóa NULL không khớp | `NULL = NULL` là UNKNOWN | Bắt buộc khóa NOT NULL hoặc thiết kế null-safe có chủ đích |
| UPDATE WHERE false nhưng hàng vẫn không INSERT | Hàng đã MATCHED theo ON; UPDATE WHERE chỉ bỏ qua update | Đây là hành vi đúng; không có fallback sang INSERT |
| Hàng target không có trong source vẫn tồn tại | MERGE không tự xóa target-only rows | Dùng DELETE NOT EXISTS riêng theo quy tắc snapshot |
| DELETE WHERE không xóa target-only rows | DELETE WHERE chỉ áp dụng hàng matched đã update | Dùng DELETE NOT EXISTS riêng theo quy tắc snapshot |
| UPDATE khóa ON bị lỗi | Oracle không cho cập nhật cột target được tham chiếu trong ON | Thiết kế thay đổi định danh thành thao tác riêng |
| Chạy lại batch tạo kết quả khác | Source thay đổi hoặc quy tắc chọn bản ghi không xác định | Chốt snapshot/batch, tie-breaker và idempotency |

## 18. Bài tập thực hành

Sử dụng `LAB_CUSTOMERS` và `LAB_CUSTOMER_STAGE` trong mục 3. Hãy dự đoán nhánh MERGE trước khi chạy.

### Bài 1 — Upsert cơ bản

Viết MERGE cho batch 100: cập nhật khách hàng đã có theo CUSTOMER_ID và chèn khách hàng chưa có. Kiểm tra kết quả ID 1, 2, 3 và 4.

### Bài 2 — Chỉ UPDATE khi có thay đổi

Thêm UPDATE WHERE để tránh ghi lại hàng có dữ liệu giống nhau. Bắt đầu bằng so sánh `<>`, sau đó sửa để phát hiện cả chuyển đổi NULL sang giá trị và giá trị sang NULL.

### Bài 3 — Sai điều kiện ON

Thêm `AND t.status = 'ACTIVE'` vào ON. Quan sát target có ID 4 là INACTIVE. Giải thích vì sao hàng này bị coi là NOT MATCHED và vì sao INSERT có thể vi phạm primary key. Sửa bằng UPDATE WHERE.

### Bài 4 — Nguồn trùng khóa

Thêm hai hàng cho CUSTOMER_ID 10 vào batch 200. Chạy kiểm tra duplicate source. Viết MERGE sử dụng ROW_NUMBER để chỉ chọn phiên bản mới nhất, dùng SOURCE_ROW_ID làm tie-breaker.

### Bài 5 — Composite key

Giả sử bảng target có `TENANT_ID` và `EXTERNAL_CUSTOMER_ID`. Viết ON sử dụng cả hai cột. Giải thích rủi ro nếu chỉ dùng EXTERNAL_CUSTOMER_ID.

### Bài 6 — NULL trong khóa

Tạo hai hàng source và target có EXTERNAL_CODE NULL. Chạy điều kiện bằng `=` và giải thích vì sao không khớp. Đề xuất cách xử lý theo mô hình dữ liệu thay vì dùng sentinel tùy tiện.

### Bài 7 — Đồng bộ phiên bản

Chỉ UPDATE khi `SOURCE_UPDATED_AT` mới hơn `TARGET.UPDATED_AT`. Xử lý riêng trường hợp target timestamp NULL và giải thích vì sao timestamp nguồn không đáng tin nếu các hệ thống lệch đồng hồ.

### Bài 8 — Xóa theo snapshot

Phân biệt batch delta và snapshot đầy đủ. Viết DELETE NOT EXISTS chỉ cho trường hợp snapshot đầy đủ; giải thích vì sao không dùng nó với batch chỉ chứa thay đổi.

## 19. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn tất bài tập:

~~~sql
DROP TABLE lab_customer_stage PURGE;
DROP TABLE lab_customers PURGE;
~~~

Xóa staging trước target nếu sau này bổ sung foreign key hoặc quan hệ phụ thuộc. `PURGE` bỏ qua recycle bin; không chạy trên bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

`MERGE` nhận diện hàng bằng điều kiện `ON`, sau đó chọn UPDATE cho hàng MATCHED hoặc INSERT cho hàng NOT MATCHED. Hãy thiết kế `ON` dựa trên khóa định danh ổn định và đầy đủ; điều kiện quyết định **có cập nhật hay không** nên nằm trong `UPDATE WHERE`. Điều kiện giới hạn hàng chèn thuộc `INSERT WHERE`. Ba phần này có vai trò riêng và không nên trộn lẫn.

Source phải có tối đa một hàng có thẩm quyền cho mỗi khóa target. Nếu staging chứa nhiều phiên bản, chọn một hàng bằng `ROW_NUMBER` với tie-breaker xác định; nếu nguồn là các giao dịch cần cộng dồn, aggregate theo khóa trước. Duy trì primary key/unique constraint ở target, xử lý NULL trong khóa, lọc đúng batch và kiểm soát phiên bản để tránh ghi đè dữ liệu cũ. MERGE không tự xóa hàng target vắng mặt trong source; chỉ thực hiện DELETE riêng khi nguồn là snapshot đầy đủ và quy tắc nghiệp vụ cho phép.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — MERGE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html) — cú pháp MERGE, ON, UPDATE WHERE, INSERT WHERE và DELETE WHERE.
- [Oracle Database SQL Language Reference — MERGE (26ai)](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/MERGE.html) — đối chiếu cú pháp trên release mới hơn.
- [Oracle Database Error Messages — ORA-30926](https://docs.oracle.com/error-help/db/ora-30926/) — lỗi tập hàng nguồn không ổn định.
- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — ROW_NUMBER để chọn phiên bản nguồn theo thứ tự.
- [Oracle Database SQL Language Reference — Constraints (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html) — primary key, unique, foreign key và check constraints.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu SQL Language Reference đúng phiên bản, nhất là các nhánh điều kiện, giới hạn cập nhật cột trong ON và hành vi khi nguồn có nhiều hàng cùng khóa.

# Xử lý dữ liệu trùng bằng ràng buộc và thao tác có thể thực hiện lại trong Oracle

Một ứng dụng có thể gửi cùng một yêu cầu nhiều lần vì người dùng bấm nút hai lần, client timeout rồi retry, message broker phát lại message hoặc một batch phải chạy lại sau khi tiến trình bị dừng. Nếu mỗi lần chạy đều INSERT một hàng mới, dữ liệu có thể xuất hiện nhiều bản ghi đại diện cho cùng một khách hàng, đơn hàng hoặc sự kiện. Dữ liệu trùng cũng có thể được đưa vào từ file import, đồng bộ hệ thống ngoài hoặc thao tác thủ công.

Để xử lý đúng, cần phân biệt hai công việc:

1. **Ngăn dữ liệu trùng mới:** xác định khóa nghiệp vụ và dùng PRIMARY KEY, UNIQUE constraint hoặc unique index để database bảo vệ tính duy nhất.
2. **Làm thao tác có thể thực hiện lại (idempotent):** thiết kế câu lệnh và transaction sao cho cùng một yêu cầu được gửi lại không tạo thêm hiệu ứng ngoài ý muốn.

Khi dữ liệu đã trùng, cần tìm đúng bản ghi đại diện, quyết định quy tắc giữ dữ liệu, chuyển các tham chiếu liên quan và dọn các bản ghi dư trước khi bật ràng buộc. MERGE có thể hỗ trợ upsert, nhưng không tự giải quyết mọi vấn đề concurrency hoặc biến một quy trình bất kỳ thành idempotent.

Sau bài học, bạn có thể:

- Phân biệt hai hàng giống hệt nhau về nội dung với hai hàng trùng về ý nghĩa nghiệp vụ.
- Chọn natural/business key và thiết kế PRIMARY KEY/UNIQUE constraint.
- Dùng unique index, function-based unique index và NOT NULL đúng mục tiêu.
- Kiểm tra dữ liệu hiện có trước khi thêm ràng buộc.
- Chọn bản ghi chuẩn bằng ROW_NUMBER với thứ tự xác định, rồi dọn bản ghi trùng an toàn.
- Dùng MERGE cho thao tác insert-or-update và hiểu các giới hạn của nó.
- Thiết kế idempotency key cho API, batch và message consumer.
- Hiểu race condition giữa kiểm tra trước khi ghi và INSERT đồng thời.
- Xử lý ORA-00001, retry, transaction boundary và trường hợp cùng idempotency key nhưng payload khác.
- Kiểm soát nguồn dữ liệu trùng trước khi MERGE và kiểm tra kết quả sau khi chạy lại.

> Các ví dụ dùng tiền tố LAB_ và cần chạy trong schema thực hành có quyền tạo bảng/sequence. Quy tắc giữ bản ghi phải theo nghiệp vụ và được xác nhận trước khi xóa dữ liệu. Những câu DELETE trong bài là ví dụ có kiểm soát; hãy kiểm tra SELECT tương ứng và có phương án khôi phục trước khi chạy trên dữ liệu thật.

## 1. Dữ liệu trùng là gì?

Từ “trùng” có nhiều nghĩa. Hai hàng giống từng cột chưa chắc là hai bản ghi nghiệp vụ trùng; ngược lại, hai hàng khác tên hoặc email vẫn có thể đại diện cho cùng một khách hàng.

### 1.1. Trùng vật lý (exact duplicate)

Hai hàng có cùng giá trị ở tất cả các cột được xét:

| CUSTOMER_CODE | EMAIL | DISPLAY_NAME |
| --- | --- | --- |
| C100 | an@example.com | An Nguyen |
| C100 | an@example.com | An Nguyen |

Đây có thể là cùng một record bị import hai lần. Tuy nhiên, bảng thực tế thường có surrogate key hoặc timestamp khiến hai hàng không hoàn toàn giống nhau dù nội dung nghiệp vụ giống.

### 1.2. Trùng theo khóa nghiệp vụ (business duplicate)

Hai hàng được xem là cùng một thực thể theo quy tắc nghiệp vụ, dù một số thuộc tính khác nhau:

| SOURCE_SYSTEM | EXTERNAL_ID | EMAIL | DISPLAY_NAME |
| --- | --- | --- | --- |
| CRM_A | 9001 | an.old@example.com | An Nguyen |
| CRM_A | 9001 | an@example.com | Nguyen An |

Nếu quy tắc nói rằng (SOURCE_SYSTEM, EXTERNAL_ID) xác định một khách hàng duy nhất, hai hàng trên trùng về danh tính. Cần chọn dữ liệu nào là chuẩn, hoặc hợp nhất các thuộc tính theo quy tắc nghiệp vụ.

### 1.3. Trùng sau chuẩn hóa

Các chuỗi khác nhau về hoa/thường hoặc khoảng trắng có thể được xem là tương đương:

| EMAIL gốc | Khóa sau chuẩn hóa đơn giản |
| --- | --- |
| An@Example.com | AN@EXAMPLE.COM |
|  an@example.com  | AN@EXAMPLE.COM |

Nếu nghiệp vụ coi hai giá trị này là một, kiểm tra email = email thông thường chưa chắc tìm ra tất cả duplicate. Cần định nghĩa chuẩn hóa rõ ràng (trim, case folding, quy tắc Unicode, dấu, dấu chấm hoặc alias email nếu có) và áp dụng nhất quán khi ghi/đọc.

Không tự ý coi mọi email khác nhau về dấu chấm, dấu cộng hoặc ký tự Unicode là cùng một người. Đó là quy tắc nghiệp vụ riêng, không phải một phép chuẩn hóa an toàn cho mọi hệ thống.

### 1.4. Vì sao phải định nghĩa danh tính trước?

Nếu không có business key rõ ràng:

- UNIQUE constraint có thể bảo vệ nhầm cột hoặc bỏ sót duplicate.
- DISTINCT có thể xóa hai giao dịch hợp lệ chỉ vì giá trị measure giống nhau.
- ROW_NUMBER có thể giữ nhầm phiên bản cũ.
- MERGE có thể tạo thêm hàng do điều kiện ON không phản ánh danh tính thật.
- Retry có thể tạo nhiều hiệu ứng vì không có khóa nhận diện yêu cầu.

Trước khi viết SQL, hãy trả lời: **hai lần ghi nào phải được xem là cùng một đối tượng hoặc cùng một yêu cầu?**

## 2. Chọn khóa: PRIMARY KEY, UNIQUE và business key

### 2.1. PRIMARY KEY

PRIMARY KEY xác định duy nhất mỗi hàng trong bảng. Một bảng chỉ có một primary key constraint; khóa có thể gồm một hoặc nhiều cột. Mọi cột thuộc primary key đều NOT NULL và giá trị khóa không được lặp.

Ví dụ dùng ID nội bộ:

```sql
CREATE TABLE lab_customers (
    customer_id NUMBER(12)
        CONSTRAINT pk_lab_customers PRIMARY KEY,
    source_system VARCHAR2(30) NOT NULL,
    external_customer_id VARCHAR2(80) NOT NULL,
    email VARCHAR2(320),
    display_name VARCHAR2(160),
    updated_at TIMESTAMP
);
```

CUSTOMER_ID là surrogate key: ID kỹ thuật do hệ thống quản lý. Nó giúp tham chiếu ổn định trong các bảng khác, nhưng tự nó **không ngăn cùng một khách hàng ngoài hệ thống được insert nhiều lần**. Hai lần import có thể tạo hai CUSTOMER_ID khác nhau cho cùng EXTERNAL_CUSTOMER_ID.

### 2.2. UNIQUE constraint cho khóa nghiệp vụ

Nếu một khách hàng được nhận diện bởi hệ thống nguồn và ID bên nguồn, tạo khóa ghép:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

Từ đây database không cho hai hàng có cùng cặp (SOURCE_SYSTEM, EXTERNAL_CUSTOMER_ID) theo quy tắc uniqueness của Oracle. PRIMARY KEY và UNIQUE constraint có vai trò khác nhau:

| Ràng buộc | Mục tiêu |
| --- | --- |
| PRIMARY KEY | Danh tính hàng trong bảng; duy nhất và NOT NULL |
| UNIQUE | Bảo vệ một khóa thay thế hoặc khóa nghiệp vụ khỏi trùng |
| FOREIGN KEY | Bảo vệ quan hệ tham chiếu giữa các bảng |
| NOT NULL | Bắt buộc phải có giá trị ở cột |
| CHECK | Bảo vệ điều kiện hợp lệ trên giá trị hàng |

Một bảng có thể có nhiều UNIQUE constraints nhưng chỉ có một PRIMARY KEY.

### 2.3. UNIQUE không tự thay thế NOT NULL

Oracle cho phép NULL trong cột của UNIQUE constraint. Vì vậy, nếu business key bắt buộc phải có giá trị, hãy khai báo NOT NULL riêng:

Ví dụ MODIFY dưới đây dành cho bảng legacy đang cho phép NULL; bảng vừa tạo ở mục 2.1 đã khai báo hai cột này NOT NULL nên không cần chạy lại.

```sql
ALTER TABLE lab_customers MODIFY (
    source_system NOT NULL,
    external_customer_id NOT NULL
);
```

Với khóa ghép có NULL, quy tắc uniqueness của Oracle có chi tiết cần chú ý: các hàng có toàn bộ thành phần khóa NULL có thể cùng tồn tại; nếu một phần khóa NULL, các thành phần còn lại vẫn phải đáp ứng tính duy nhất theo quy tắc khóa ghép. Đừng dùng NULL để biểu diễn một business key bắt buộc. Khai báo NOT NULL cho từng thành phần nếu nghiệp vụ yêu cầu một định danh hoàn chỉnh.

### 2.4. UNIQUE constraint và unique index

Oracle thường dùng unique index để thực thi PRIMARY KEY/UNIQUE constraint. Có thể tạo unique index trực tiếp:

```sql
CREATE UNIQUE INDEX ux_lab_customers_source
ON lab_customers (source_system, external_customer_id);
```

Đây là lựa chọn thay thế cho việc thêm UNIQUE constraint ở mục 2.2 nếu mục tiêu chỉ là thực thi uniqueness bằng index. Không tạo cả hai index duy nhất trùng cùng tập cột một cách không cần thiết. Nếu muốn metadata có UNIQUE constraint nhưng đã có index phù hợp, có thể gắn constraint vào index đó:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id)
USING INDEX ux_lab_customers_source;
```

Unique index bảo vệ tính duy nhất ở mức index. UNIQUE constraint thể hiện quy tắc toàn vẹn dữ liệu trong metadata và dễ được công cụ quản trị/kiểm tra constraint nhận biết. Khi thiết kế schema nghiệp vụ, ưu tiên khai báo constraint; Oracle có thể dùng index phù hợp hoặc tạo index để thực thi.

Nếu đã có unique index phù hợp, có thể tạo constraint dùng index đó bằng cú pháp USING INDEX theo quy trình DDL thích hợp. Không cần tạo thêm một unique index trùng lặp nếu constraint đã được bảo vệ bằng index phù hợp.

### 2.5. Khóa ghép và thứ tự cột

Một UNIQUE constraint có thể gồm nhiều cột:

```sql
ALTER TABLE lab_order_lines
ADD CONSTRAINT uq_lab_order_line
UNIQUE (order_id, line_no);
```

Điều này bảo đảm mỗi dòng số LINE_NO trong một ORDER_ID chỉ xuất hiện một lần. Nó không bảo đảm LINE_NO duy nhất trên toàn bảng.

Chọn đúng tập cột. Nếu thêm UPDATED_AT vào khóa chỉ để cho phép nhiều phiên bản, bạn đang định nghĩa một danh tính khác; nếu bỏ SOURCE_SYSTEM, hai hệ thống nguồn có thể vô tình xung đột ID.

## 3. Chuẩn hóa business key trước khi áp dụng uniqueness

Một UNIQUE constraint trên EMAIL bảo vệ giá trị lưu trữ chính xác theo quy tắc so sánh của cột/collation. Nếu nghiệp vụ coi email không phân biệt hoa thường và bỏ khoảng trắng đầu/cuối, cần áp dụng quy tắc đó nhất quán.

### 3.1. Tìm duplicate theo khóa chuẩn hóa

```sql
SELECT
    UPPER(TRIM(email)) AS normalized_email,
    COUNT(*) AS row_count
FROM lab_customers
WHERE email IS NOT NULL
GROUP BY UPPER(TRIM(email))
HAVING COUNT(*) > 1
ORDER BY normalized_email;
```

Đây là phép kiểm tra duplicate theo một quy tắc đơn giản: bỏ khoảng trắng đầu/cuối và chuyển sang chữ hoa. UPPER(TRIM(...)) không phải chuẩn hóa email đầy đủ cho mọi ngôn ngữ/Unicode hay mọi collation; hãy thống nhất quy tắc với ứng dụng và dữ liệu nguồn.

### 3.2. Function-based unique index

Nếu muốn database bảo vệ giá trị đã chuẩn hóa, có thể tạo unique function-based index:

```sql
CREATE UNIQUE INDEX ux_lab_customers_email_norm
ON lab_customers (UPPER(TRIM(email)));
```

Từ đó An@Example.com và an@example.com (có khoảng trắng đầu/cuối) không thể cùng tồn tại nếu biểu thức chuẩn hóa của chúng giống nhau. Với email NULL, biểu thức index là NULL; Oracle B-tree index không lưu entry khi tất cả key columns là NULL, nên nhiều hàng NULL có thể tồn tại. Nếu email bắt buộc, dùng NOT NULL; nếu email tùy chọn nhưng các email có giá trị phải unique sau chuẩn hóa, mẫu này thường phù hợp.

Một cách khác là tạo virtual column chuẩn hóa rồi đặt UNIQUE constraint lên cột đó:

```sql
ALTER TABLE lab_customers ADD (
    email_normalized GENERATED ALWAYS AS (
        UPPER(TRIM(email))
    ) VIRTUAL
);

ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_email_norm
UNIQUE (email_normalized);
```

Virtual column giúp quy tắc chuẩn hóa có tên rõ trong schema và có thể được truy vấn. Hãy kiểm tra phiên bản Oracle, collation và quyền DDL trước khi dùng.

### 3.3. Chọn khóa theo nghiệp vụ, không theo tiện lợi

Không phải lúc nào email cũng là khóa định danh tốt:

- Email có thể thay đổi hoặc được chia sẻ.
- Một người có thể có nhiều email.
- Email có thể chưa được cung cấp.
- Hai hệ thống nguồn có thể chuẩn hóa khác nhau.

Nếu hệ thống nguồn cấp ID ổn định, cặp (SOURCE_SYSTEM, EXTERNAL_ID) thường phù hợp hơn. Email có thể là một UNIQUE key bổ sung nếu nghiệp vụ thực sự yêu cầu duy nhất.

## 4. Kiểm tra duplicate trước khi thêm ràng buộc

Nếu bảng đã chứa duplicate, câu lệnh thêm UNIQUE constraint hoặc tạo unique index sẽ thất bại. Hãy kiểm tra dữ liệu trước.

Các truy vấn ở mục 4–5 mô tả giai đoạn xử lý một bảng legacy trước khi ràng buộc uniqueness được bật. Nếu đã tạo UNIQUE constraint ở mục 2.2, database sẽ ngăn duplicate mới; khi thực hành dọn dữ liệu cũ, chạy các bước kiểm tra/dọn trên bản sao legacy hoặc trước khi thêm constraint.

### 4.1. Tìm khóa nghiệp vụ bị lặp

```sql
SELECT
    source_system,
    external_customer_id,
    COUNT(*) AS duplicate_count
FROM lab_customers
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1
ORDER BY source_system, external_customer_id;
```

Kết quả cho biết các nhóm khóa xuất hiện nhiều hơn một lần. COUNT(*) ở đây đếm hàng, không đếm giá trị cột.

### 4.2. Xem toàn bộ hàng thuộc nhóm trùng

```sql
SELECT c.*
FROM lab_customers c
JOIN (
    SELECT source_system, external_customer_id
    FROM lab_customers
    GROUP BY source_system, external_customer_id
    HAVING COUNT(*) > 1
) d
  ON d.source_system = c.source_system
 AND d.external_customer_id = c.external_customer_id
ORDER BY c.source_system,
         c.external_customer_id,
         c.updated_at DESC,
         c.customer_id DESC;
```

Đây là bước kiểm tra để hiểu các hàng khác nhau ở đâu. Đừng xóa ngay sau khi chỉ nhìn thấy COUNT(*) > 1.

### 4.3. Kiểm tra NULL và khóa thiếu

```sql
SELECT COUNT(*) AS missing_business_key_rows
FROM lab_customers
WHERE source_system IS NULL
   OR external_customer_id IS NULL;
```

Các hàng thiếu khóa không thể được ghép an toàn theo business key. Hãy quyết định sửa dữ liệu, đưa vào hàng chờ xử lý, hoặc giữ lại với trạng thái chưa định danh. Không gom tất cả NULL thành một thực thể khách hàng.

### 4.4. Lỗi thường gặp khi thêm UNIQUE

Nếu duplicate tồn tại, DDL có thể báo:

```text
ORA-02299: cannot validate (...) - duplicate keys found
```

Nếu một INSERT/UPDATE vi phạm unique constraint/index đang hoạt động, Oracle báo:

```text
ORA-00001: unique constraint (...) violated
```

Hai lỗi này nói về hai thời điểm khác nhau:

- ORA-02299 thường gặp khi xác thực/bật constraint trên dữ liệu đã có duplicate.
- ORA-00001 thường gặp khi một thao tác DML tạo ra khóa trùng với dữ liệu đã được bảo vệ.

### 4.5. Chuẩn bị dữ liệu trước khi tạo UNIQUE

Một quy trình triển khai thường gồm:

1. Xác định business key và quy tắc chuẩn hóa.
2. Thống kê duplicate, khóa NULL và các xung đột không thể tự hợp nhất.
3. Xác định canonical row và mapping các ID cũ.
4. Chuyển foreign key ở các bảng con sang canonical ID.
5. Xóa/đưa duplicate vào bảng lưu trữ theo chính sách retention.
6. Kiểm tra lại không còn duplicate.
7. Tạo unique index/constraint.
8. Cập nhật mọi luồng ghi để cung cấp đủ business key và xử lý duplicate key.

Trong lúc dọn dữ liệu, một luồng ghi đồng thời có thể chèn duplicate mới sau bước kiểm tra. Cần kiểm soát writer bằng maintenance window, khóa/điều phối quy trình ghi hoặc triển khai ràng buộc trong kế hoạch migration phù hợp. Đừng giả định rằng một SELECT kiểm tra sạch sẽ bảo đảm dữ liệu vẫn sạch đến lúc DDL chạy.

Oracle DDL như CREATE INDEX hoặc ALTER TABLE có implicit commit. Không xem chuỗi DML dọn dữ liệu và DDL tạo constraint như một transaction có thể rollback toàn bộ bằng ROLLBACK. Hãy tách kế hoạch migration, backup/restore và kiểm soát thời điểm chạy.

## 5. Chọn bản ghi chuẩn và dọn dữ liệu trùng

Khi một business key có nhiều hàng, cần quy tắc survivorship: hàng nào được giữ, cột nào cần hợp nhất, hàng nào phải chuyển tham chiếu. Một ví dụ phổ biến là giữ hàng cập nhật mới nhất; nếu thời gian bằng nhau, dùng khóa duy nhất làm tie-breaker.

Các ví dụ ROW_NUMBER/DELETE trong mục này giả định bảng legacy vẫn còn duplicate và chưa được bảo vệ bởi UNIQUE constraint trên business key. Chỉ bật constraint sau khi dọn dữ liệu và kiểm tra lại.

### 5.1. ROW_NUMBER xác định thứ tự trong mỗi nhóm

```sql
SELECT
    customer_id,
    source_system,
    external_customer_id,
    updated_at,
    ROW_NUMBER() OVER (
        PARTITION BY source_system, external_customer_id
        ORDER BY updated_at DESC NULLS LAST,
                 customer_id DESC
    ) AS rn
FROM lab_customers;
```

Ý nghĩa:

- PARTITION BY chia các hàng theo business key.
- Hàng có RN = 1 là hàng được chọn giữ theo thứ tự đã định nghĩa.
- Hàng có RN > 1 là ứng viên duplicate cần xử lý.
- CUSTOMER_ID DESC là tie-breaker để thứ tự xác định khi UPDATED_AT bằng nhau.

Không dựa vào ROW_NUMBER nếu ORDER BY không tạo thứ tự xác định. Nếu hai hàng có cùng timestamp và không có tie-breaker, lần chạy khác nhau có thể chọn hàng khác làm bản ghi chuẩn.

### 5.2. Xem trước các hàng sẽ bị loại

```sql
WITH ranked_customers AS (
    SELECT
        customer_id,
        source_system,
        external_customer_id,
        updated_at,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST,
                     customer_id DESC
        ) AS rn
    FROM lab_customers
)
SELECT *
FROM ranked_customers
WHERE rn > 1
ORDER BY source_system, external_customer_id, rn;
```

Chạy SELECT này trước khi DELETE. Đối chiếu các hàng bị đánh dấu với nghiệp vụ, quan hệ foreign key, lịch sử thay đổi và các cột không thể tự động hợp nhất.

### 5.3. Xóa duplicate bằng ROWID sau khi đã xác nhận

Khi đã xác nhận chỉ cần giữ hàng RN = 1, có thể xóa các hàng còn lại:

```sql
DELETE FROM lab_customers c
WHERE c.ROWID IN (
    SELECT rid
    FROM (
        SELECT
            ROWID AS rid,
            ROW_NUMBER() OVER (
                PARTITION BY source_system, external_customer_id
                ORDER BY updated_at DESC NULLS LAST,
                         customer_id DESC
            ) AS rn
        FROM lab_customers
        WHERE source_system IS NOT NULL
          AND external_customer_id IS NOT NULL
    )
    WHERE rn > 1
);
```

ROWID nhận diện vị trí hàng vật lý trong bảng theo cơ chế Oracle. Ở đây nó dùng làm locator tạm thời cho một lần dọn dữ liệu; **không dùng ROWID làm business key hoặc lưu làm định danh lâu dài**. Với bảng partitioned, clustered hoặc cấu trúc đặc biệt, hãy hiểu cách ROWID hoạt động và kiểm thử đúng đối tượng.

Ví dụ trên cố ý bỏ qua các hàng thiếu business key để không gom mọi NULL vào một nhóm duplicate. Sau khi kiểm tra số hàng bị xóa, xác minh lại:

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customers
WHERE source_system IS NOT NULL
  AND external_customer_id IS NOT NULL
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

Nếu không còn kết quả, dữ liệu thỏa tính duy nhất cho khóa đã kiểm tra tại thời điểm truy vấn.

### 5.4. Dữ liệu con tham chiếu tới hàng duplicate

Nếu bảng ORDERS hoặc CONTACTS đang tham chiếu CUSTOMER_ID, không thể tùy tiện xóa khách hàng duplicate trước khi chuyển foreign key:

1. Chọn CUSTOMER_ID chuẩn cho mỗi business key.
2. Tạo mapping duplicate_customer_id -> canonical_customer_id.
3. Cập nhật các bảng con để trỏ tới canonical ID.
4. Kiểm tra không còn tham chiếu tới ID sẽ xóa.
5. Xóa hàng duplicate.
6. Thêm/validate UNIQUE constraint để ngăn duplicate quay lại.

Ví dụ mapping tạm:

```sql
WITH ranked AS (
    SELECT
        customer_id,
        source_system,
        external_customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST, customer_id DESC
        ) AS rn,
        FIRST_VALUE(customer_id) OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY updated_at DESC NULLS LAST, customer_id DESC
        ) AS canonical_customer_id
    FROM lab_customers
    WHERE source_system IS NOT NULL
      AND external_customer_id IS NOT NULL
)
SELECT customer_id AS duplicate_customer_id,
       canonical_customer_id
FROM ranked
WHERE rn > 1;
```

Mapping phải được lưu lại trong bảng staging/audit nếu cần dùng để cập nhật nhiều bảng con. Trước khi chạy UPDATE, xác minh mỗi duplicate có đúng một canonical ID và kiểm tra các constraint/trigger có liên quan.

### 5.5. Hợp nhất thuộc tính khác nhau

Không phải lúc nào cũng đúng khi chỉ giữ hàng mới nhất. Có thể hàng cũ có số điện thoại còn hàng mới có email. Khi đó cần quy tắc merge cột:

- Lấy giá trị mới nhất theo nguồn đáng tin cậy.
- Ưu tiên giá trị không NULL.
- Ưu tiên một hệ thống nguồn theo thứ tự tin cậy.
- Ghi lịch sử thay đổi vào bảng audit.
- Đưa xung đột không thể tự quyết định vào hàng chờ người xử lý.

MAX(email) hoặc MAX(display_name) không phải quy tắc survivorship có ý nghĩa chỉ vì chúng giúp câu SQL chạy. Chọn dữ liệu chuẩn là quyết định nghiệp vụ; SQL chỉ thực thi quyết định đó.

## 6. Thao tác idempotent là gì?

Một thao tác được gọi là idempotent khi thực hiện một lần hay lặp lại nhiều lần với cùng một yêu cầu đều dẫn đến cùng trạng thái nghiệp vụ cuối cùng, không tạo thêm hiệu ứng ngoài ý muốn.

Ví dụ:

| Thao tác | Có thể idempotent? | Lý do |
| --- | --- | --- |
| Đặt trạng thái đơn hàng thành PAID | Có, nếu cùng điều kiện và không lặp side effect | Gán cùng một giá trị nhiều lần không đổi trạng thái cuối |
| Cộng thêm 100 vào số dư | Không | Mỗi lần chạy làm số dư tăng thêm 100 |
| Ghi nhận event có EVENT_ID duy nhất | Có, nếu database bảo vệ EVENT_ID và xử lý duplicate đúng | Cùng event không tạo hai hàng |
| Gửi email xác nhận mỗi lần API được retry | Không | Side effect được lặp dù dữ liệu database có thể không đổi |
| Upsert hồ sơ theo khóa nguồn | Có thể | Cần khóa duy nhất và UPDATE có quy tắc ổn định |

Idempotent không có nghĩa “câu SQL chạy thành công mọi lần”. Một lần chạy lại có thể gặp duplicate key và trả kết quả “đã xử lý”; điều quan trọng là trạng thái và hiệu ứng nghiệp vụ không bị nhân lên.

### 6.1. Phân biệt idempotency với uniqueness

- UNIQUE constraint bảo vệ rằng một khóa không xuất hiện ở nhiều hàng.
- Idempotency bảo vệ rằng lặp cùng một yêu cầu không lặp hiệu ứng.
- Một thao tác idempotent thường cần một khóa duy nhất để nhận diện lần yêu cầu, nhưng unique constraint đơn lẻ chưa đủ để xử lý mọi side effect.

Ví dụ, CUSTOMER_ID unique không ngăn hai lần gửi cùng yêu cầu tạo khách hàng nếu mỗi lần ứng dụng sinh một CUSTOMER_ID mới. Cần một business key hoặc idempotency key ổn định giữa các lần retry.

### 6.2. Không dùng sequence làm idempotency key

Sequence sinh giá trị mới mỗi lần gọi NEXTVAL. Nếu ứng dụng timeout sau khi INSERT nhưng không nhận được response, retry có thể lấy một ID mới và tạo thêm hàng. Sequence phù hợp làm surrogate primary key, nhưng không tự nhận diện cùng yêu cầu.

Hãy dùng một khóa ổn định được tạo trước khi gửi yêu cầu (ví dụ request UUID) hoặc business key do hệ thống nguồn cấp, rồi đặt UNIQUE/PRIMARY KEY trên khóa đó. Sequence có thể tiếp tục tạo ID nội bộ sau khi đã xác định request là mới.

## 7. INSERT an toàn: đừng chỉ SELECT trước rồi INSERT

Một mẫu dễ viết nhưng không an toàn dưới concurrency:

```sql
SELECT COUNT(*)
INTO l_count
FROM lab_customers
WHERE source_system = :source_system
  AND external_customer_id = :external_id;

IF l_count = 0 THEN
    INSERT INTO lab_customers (
        customer_id,
        source_system,
        external_customer_id
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        :source_system,
        :external_id
    );
END IF;
```

Giả sử hai session cùng chạy:

```text
Session A                         Session B
---------                         ---------
MERGE kiểm tra: chưa có            MERGE kiểm tra: chưa có
Đi vào NOT MATCHED                 Đi vào NOT MATCHED
INSERT hàng                        INSERT cùng business key
COMMIT                             Chờ khóa/kiểm tra uniqueness
                                  Nhận ORA-00001
```

Nếu không có UNIQUE constraint, cả hai hàng đều có thể được tạo. Nếu có UNIQUE constraint, một session sẽ thắng và session còn lại nhận duplicate key. Vì vậy, SELECT trước không thay thế được constraint; giữa SELECT và INSERT luôn có một khoảng thời gian mà trạng thái có thể thay đổi.

### 7.1. Dùng UNIQUE constraint làm hàng rào cuối cùng

Đặt khóa nghiệp vụ unique:

Nếu đã thêm constraint này ở mục 2.2 hoặc đã gắn constraint vào unique index ở mục 2.4, không chạy lại DDL bên dưới.

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

Sau đó ứng dụng có thể thử INSERT. Nếu nhận duplicate key đúng constraint dự kiến, đọc lại hàng hiện có và coi yêu cầu là đã được xử lý hoặc chuyển sang UPDATE theo quy tắc. Đừng bắt mọi lỗi database rồi bỏ qua; lỗi kết nối, lỗi NOT NULL hoặc lỗi constraint khác vẫn cần được báo.

### 7.2. Xử lý duplicate key trong PL/SQL

Một mẫu đơn giản:

```sql
DECLARE
    l_customer_id lab_customers.customer_id%TYPE;
BEGIN
    INSERT INTO lab_customers (
        customer_id,
        source_system,
        external_customer_id,
        display_name,
        updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        :source_system,
        :external_customer_id,
        :display_name,
        SYSTIMESTAMP
    )
    RETURNING customer_id INTO l_customer_id;

    DBMS_OUTPUT.PUT_LINE('CREATED=' || l_customer_id);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        SELECT customer_id
        INTO l_customer_id
        FROM lab_customers
        WHERE source_system = :source_system
          AND external_customer_id = :external_customer_id;

        DBMS_OUTPUT.PUT_LINE('ALREADY_EXISTS=' || l_customer_id);
END;
/
```

Đây là ví dụ xử lý duplicate trên đúng khóa nghiệp vụ trong môi trường lab. Trong hệ thống thật, DUP_VAL_ON_INDEX có thể được kích hoạt bởi bất kỳ unique constraint/index nào của bảng. Chỉ coi lỗi là “đã tồn tại” sau khi xác nhận đó là constraint dự kiến và tìm được hàng theo business key; nếu không tìm thấy, hãy phát sinh lại lỗi để không che lỗi khác.

Nếu ứng dụng dùng JDBC, cách xử lý tương đương là bắt lỗi unique violation, xác định constraint/SQL state phù hợp với driver, rồi đọc lại bằng khóa nghiệp vụ. Không dựa vào chuỗi thông báo lỗi đã được format theo ngôn ngữ session nếu có thể dùng thông tin lỗi có cấu trúc.

## 8. MERGE: insert-or-update theo khóa

MERGE kết hợp điều kiện so khớp với hành động UPDATE hoặc INSERT. Nó thường được dùng cho đồng bộ dữ liệu nguồn và upsert.

### 8.1. Cú pháp cơ bản

```sql
MERGE INTO target_table t
USING source_table s
ON (t.business_key = s.business_key)
WHEN MATCHED THEN
    UPDATE SET
        t.value_col = s.value_col
WHEN NOT MATCHED THEN
    INSERT (business_key, value_col)
    VALUES (s.business_key, s.value_col);
```

ON xác định hai hàng có cùng danh tính theo nghiệp vụ hay không:

- MATCHED: hàng target đã tồn tại; thực hiện UPDATE nếu có nhánh UPDATE.
- NOT MATCHED: chưa có hàng target; thực hiện INSERT nếu có nhánh INSERT.

### 8.2. Upsert khách hàng theo ID nguồn

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :email AS email,
        :display_name AS display_name
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        source_system,
        external_customer_id,
        email,
        display_name,
        updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL,
        s.source_system,
        s.external_customer_id,
        s.email,
        s.display_name,
        SYSTIMESTAMP
    );
```

Với cùng business key, lần đầu tạo hàng; lần sau cập nhật hàng đó thay vì tạo hàng mới. UNIQUE constraint trên (SOURCE_SYSTEM, EXTERNAL_CUSTOMER_ID) vẫn cần có để bảo vệ dữ liệu trước các writer khác và các đường ghi không dùng MERGE.

### 8.3. MERGE chỉ idempotent khi quy tắc UPDATE ổn định

Một MERGE có thể không idempotent về mặt hiệu ứng nếu mỗi lần chạy:

- Cộng số lượng vào cột hiện có (t.qty = t.qty + s.qty).
- Ghi timestamp mới làm thay đổi trạng thái dù payload không đổi.
- Tạo audit event hoặc gửi thông báo ở trigger mỗi lần matched.
- Ghi đè dữ liệu mới hơn bằng một payload cũ được retry muộn.

Nếu muốn “đồng bộ trạng thái theo snapshot”, UPDATE nên gán giá trị đích một cách xác định, không cộng lặp. Nếu muốn xử lý event delta, cần EVENT_ID duy nhất để cùng event không được áp dụng hai lần.

Ví dụ update chỉ khi payload mới thực sự khác:

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :email AS email,
        :display_name AS display_name
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
    WHERE DECODE(t.email, s.email, 0, 1) = 1
       OR DECODE(t.display_name, s.display_name, 0, 1) = 1
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        email, display_name, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.email,
        s.display_name, SYSTIMESTAMP
    );
```

DECODE ở đây so sánh cả NULL theo quy tắc của DECODE, giúp bỏ qua UPDATE khi hai cột không đổi. Cách viết này vẫn cần xem xét các cột khác, trigger và quy tắc timestamp thực tế; đừng giả định chỉ vì không đổi hai cột hiển thị thì toàn bộ side effect đã idempotent.

## 9. Concurrency khi MERGE và cách xử lý duplicate race

MERGE giúp viết logic matched/not matched trong một statement, nhưng không phải một cơ chế khóa độc quyền business key cho mọi session. Hai session có thể cùng đánh giá một khóa chưa tồn tại rồi cùng đi vào nhánh NOT MATCHED. Khi cả hai cùng INSERT, UNIQUE constraint sẽ ngăn hàng thứ hai và một session có thể nhận ORA-00001.

### 9.1. Minh họa race condition

Giả sử chưa có hàng (CRM_A, 9001):

```text
Session A                         Session B
---------                         ---------
MERGE kiểm tra: chưa có            MERGE kiểm tra: chưa có
Đi vào NOT MATCHED                 Đi vào NOT MATCHED
INSERT hàng                        INSERT cùng business key
COMMIT                             Chờ khóa/kiểm tra uniqueness
                                  Nhận ORA-00001
```

UNIQUE constraint bảo đảm dữ liệu cuối cùng không có hai hàng cùng khóa. Nó không bảo đảm cả hai MERGE đều trả về thành công. Ứng dụng phải xử lý cuộc đua này theo quy tắc: đọc lại hàng chuẩn, thử UPDATE nếu thích hợp, hoặc retry toàn bộ thao tác có giới hạn.

### 9.2. Mẫu xử lý duplicate race

Một chiến lược phổ biến:

1. Thử MERGE theo business key.
2. Nếu thành công, hoàn tất transaction.
3. Nếu nhận ORA-00001 từ đúng unique constraint của business key, đọc lại hàng theo khóa.
4. So sánh version/timestamp/payload theo quy tắc đồng bộ.
5. Nếu cần, thực hiện UPDATE có điều kiện; nếu không, coi yêu cầu đã được xử lý.
6. Nếu lỗi không đến từ constraint dự kiến hoặc không tìm thấy hàng, báo lỗi và ghi log.

Không retry vô hạn. Dùng số lần retry giới hạn, backoff có jitter ở tầng ứng dụng và ghi nhận lỗi cuối để tránh tạo vòng lặp tải cao khi hệ thống đang quá tải.

### 9.3. Tránh ghi đè dữ liệu mới bằng retry cũ

Giả sử event mới có version 12 đã cập nhật hồ sơ. Một message cũ version 11 được phát lại sau đó. Nếu MERGE luôn UPDATE, dữ liệu mới có thể bị ghi đè.

Có thể thêm điều kiện version:

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        :source_system AS source_system,
        :external_customer_id AS external_customer_id,
        :source_version AS source_version,
        :email AS email
    FROM dual
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.source_version = s.source_version,
        t.updated_at = SYSTIMESTAMP
    WHERE s.source_version > t.source_version
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        source_version, email, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.source_version,
        s.email, SYSTIMESTAMP
    );
```

Ví dụ cần bổ sung cột SOURCE_VERSION vào bảng lab trước khi chạy. So sánh version chỉ hợp lệ nếu hệ thống nguồn cấp version có thứ tự đáng tin cậy; nếu không, cần dùng timestamp có quy tắc, sequence từ nguồn hoặc cơ chế conflict resolution phù hợp.

## 10. Idempotency key cho API, batch và message consumer

Business key xác định một thực thể (ví dụ một khách hàng). Idempotency key xác định một **yêu cầu hoặc event cụ thể**. Một khách hàng có thể có hàng trăm yêu cầu cập nhật khác nhau, nên không dùng business key thay cho request key.

### 10.1. Thiết kế bảng lưu yêu cầu đã xử lý

Một bảng ledger có thể lưu khóa request, phạm vi client, hash payload và kết quả:

```sql
CREATE TABLE lab_request_ledger (
    client_id       VARCHAR2(80) NOT NULL,
    idempotency_key VARCHAR2(120) NOT NULL,
    request_hash    VARCHAR2(64) NOT NULL,
    result_code     NUMBER(3),
    result_body     CLOB,
    completed_at    TIMESTAMP,
    CONSTRAINT pk_lab_request_ledger
        PRIMARY KEY (client_id, idempotency_key)
);
```

Khóa ghép tránh xung đột giữa hai client độc lập có thể cùng sinh một chuỗi key. Tùy API, phạm vi key có thể là tenant + operation + key hoặc một scope tương đương.

REQUEST_HASH là hash của payload đã canonicalize (ví dụ JSON được chuẩn hóa thứ tự field và biểu diễn giá trị). Cùng một idempotency key nhưng payload khác phải được coi là xung đột, không trả lại response cũ như thể yêu cầu giống nhau.

### 10.2. Transaction xử lý request

Mẫu luồng trong một transaction database:

```text
BEGIN TRANSACTION
    1. INSERT (client_id, idempotency_key, request_hash)
       vào LAB_REQUEST_LEDGER.
    2. Áp dụng thay đổi nghiệp vụ trong cùng transaction.
    3. Lưu result_code, result_body và completed_at.
COMMIT

Nếu bất kỳ bước nào thất bại:
    ROLLBACK toàn bộ ledger row và thay đổi nghiệp vụ.
```

Điểm quan trọng là ledger row và thay đổi nghiệp vụ được commit cùng nhau. Nếu tiến trình chết trước COMMIT, cả hai cùng rollback; retry có thể thử lại. Nếu COMMIT thành công nhưng response bị mất trên đường truyền, retry gặp idempotency key đã tồn tại và có thể trả lại kết quả đã lưu.

Không commit ledger row ở một transaction riêng trước khi thực hiện business update nếu chưa có cơ chế lease/recovery. Nếu commit trạng thái PROCESSING rồi tiến trình chết, hệ thống cần biết cách phát hiện request bị kẹt và tiếp quản an toàn.

### 10.3. Quy tắc khi key đã tồn tại

Khi INSERT ledger gặp duplicate key:

- Đọc ledger theo (CLIENT_ID, IDEMPOTENCY_KEY).
- Nếu REQUEST_HASH giống và request đã hoàn tất, trả lại kết quả đã lưu.
- Nếu REQUEST_HASH khác, trả lỗi xung đột (ví dụ HTTP 409) vì cùng key được dùng cho payload khác.
- Nếu trạng thái đang xử lý trong một kiến trúc commit trạng thái riêng, áp dụng quy tắc chờ/kiểm tra lease; không chạy nghiệp vụ lần thứ hai.

Trong thiết kế một transaction duy nhất, transaction cạnh tranh với cùng key thường phải chờ transaction đầu commit/rollback. Sau khi transaction đầu commit, INSERT thứ hai nhận duplicate; sau đó đọc kết quả đã commit. Nếu transaction đầu rollback, transaction thứ hai có thể insert thành công và trở thành bên xử lý.

### 10.4. Idempotency cho event làm thay đổi số dư

Một ví dụ về thao tác cộng tiền không idempotent nếu chạy lặp:

```sql
UPDATE lab_accounts
SET balance = balance + :amount
WHERE account_id = :account_id;
```

Nếu message được phát lại, số dư bị cộng thêm lần nữa. Tạo bảng event đã xử lý với EVENT_ID unique:

```sql
CREATE TABLE lab_processed_events (
    event_id       VARCHAR2(120)
        CONSTRAINT pk_lab_processed_events PRIMARY KEY,
    account_id     NUMBER(12) NOT NULL,
    amount         NUMBER(14, 2) NOT NULL,
    processed_at   TIMESTAMP NOT NULL
);
```

Trong cùng transaction:

```sql
INSERT INTO lab_processed_events (
    event_id, account_id, amount, processed_at
)
VALUES (
    :event_id, :account_id, :amount, SYSTIMESTAMP
);

UPDATE lab_accounts
SET balance = balance + :amount
WHERE account_id = :account_id;

COMMIT;
```

Nếu INSERT event thành công, cập nhật số dư rồi commit. Nếu event_id đã tồn tại, duplicate key ngăn UPDATE được thực hiện nếu ứng dụng xử lý exception/rollback đúng. Cả hai thao tác phải ở cùng transaction để không có trường hợp event được đánh dấu đã xử lý nhưng số dư chưa cập nhật, hoặc số dư đã cập nhật mà event ledger bị rollback.

Đoạn SQL trên là phần thân transaction minh họa; ứng dụng/PLSQL cần bắt duplicate key tại đúng ranh giới và không tiếp tục chạy UPDATE khi INSERT event thất bại.

### 10.5. Side effect bên ngoài database và transactional outbox

Transaction Oracle không thể rollback email đã gửi, HTTP call tới dịch vụ thanh toán hoặc message đã publish ra broker. Nếu một request vừa cập nhật database vừa gọi dịch vụ ngoài, có thể xảy ra:

1. Database commit thành công.
2. Dịch vụ ngoài đã nhận yêu cầu.
3. Client timeout trước khi nhận response.
4. Retry gọi lại và dịch vụ ngoài nhận side effect lần hai.

Một mẫu phổ biến là transactional outbox:

- Trong transaction nghiệp vụ, cập nhật bảng chính và INSERT một outbox event có event key duy nhất.
- Commit cả hai cùng nhau.
- Worker đọc outbox, gửi message và đánh dấu đã gửi.
- Nếu worker retry, consumer hoặc dịch vụ nhận cũng cần deduplicate theo event key.

Outbox bảo đảm event được ghi cùng thay đổi database; việc giao message thường là at-least-once, vì vậy consumer vẫn cần idempotency. Không nhầm outbox với bảo đảm exactly-once end-to-end.

## 11. Làm sạch nguồn trước khi MERGE

MERGE cần một tập nguồn có ý nghĩa rõ ràng. Nếu nguồn chứa nhiều hàng cho cùng business key:

- Nếu target đã có một hàng tương ứng, nhiều source rows có thể cùng cố UPDATE một target row; Oracle có thể báo ORA-30926 vì không tạo được stable set of rows.
- Nếu target chưa có hàng, nhiều source rows cùng khóa có thể cùng đi vào nhánh INSERT và vi phạm UNIQUE constraint.
- Nếu các hàng nguồn có payload khác nhau, không có quy tắc nào tự biết hàng nào mới/đáng tin hơn.

### 11.1. Phát hiện source duplicate

Giả sử batch nhập vào bảng staging:

```sql
CREATE TABLE lab_customer_stage (
    stage_row_id NUMBER(12) PRIMARY KEY,
    batch_id     VARCHAR2(80) NOT NULL,
    source_system VARCHAR2(30),
    external_customer_id VARCHAR2(80),
    email        VARCHAR2(320),
    display_name VARCHAR2(160),
    source_version NUMBER(12),
    loaded_at    TIMESTAMP
);
```

Kiểm tra duplicate trong một batch:

```sql
SELECT
    source_system,
    external_customer_id,
    COUNT(*) AS source_rows
FROM lab_customer_stage
WHERE batch_id = :batch_id
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

Nếu staging có nhiều hàng cho cùng business key, quyết định xử lý trước khi MERGE: chọn version mới nhất, hợp nhất thuộc tính, hoặc chuyển xung đột sang bảng lỗi.

### 11.2. Chọn một source row có version cao nhất

```sql
WITH ranked_source AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY source_system, external_customer_id
            ORDER BY source_version DESC NULLS LAST,
                     loaded_at DESC NULLS LAST,
                     stage_row_id DESC
        ) AS rn
    FROM lab_customer_stage s
    WHERE batch_id = :batch_id
      AND source_system IS NOT NULL
      AND external_customer_id IS NOT NULL
)
SELECT *
FROM ranked_source
WHERE rn = 1;
```

Đây là quy tắc mẫu: version lớn hơn thắng; nếu bằng version thì hàng load mới hơn thắng; cuối cùng stage_row_id tạo thứ tự xác định. Chỉ dùng quy tắc này khi source_version có ý nghĩa nghiệp vụ. Nếu hai hàng cùng version nhưng payload xung đột, có thể tốt hơn là đánh dấu lỗi thay vì âm thầm chọn hàng mới hơn theo thời gian load.

### 11.3. MERGE từ nguồn đã deduplicate

```sql
MERGE INTO lab_customers t
USING (
    SELECT
        source_system,
        external_customer_id,
        email,
        display_name
    FROM (
        SELECT
            s.*,
            ROW_NUMBER() OVER (
                PARTITION BY source_system, external_customer_id
                ORDER BY source_version DESC NULLS LAST,
                         loaded_at DESC NULLS LAST,
                         stage_row_id DESC
            ) AS rn
        FROM lab_customer_stage s
        WHERE batch_id = :batch_id
          AND source_system IS NOT NULL
          AND external_customer_id IS NOT NULL
    )
    WHERE rn = 1
) s
ON (
    t.source_system = s.source_system
    AND t.external_customer_id = s.external_customer_id
)
WHEN MATCHED THEN
    UPDATE SET
        t.email = s.email,
        t.display_name = s.display_name,
        t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        customer_id, source_system, external_customer_id,
        email, display_name, updated_at
    )
    VALUES (
        lab_customer_seq.NEXTVAL, s.source_system,
        s.external_customer_id, s.email,
        s.display_name, SYSTIMESTAMP
    );
```

Nguồn của MERGE lúc này có tối đa một hàng cho mỗi business key trong batch. Target vẫn cần unique constraint; deduplicate source không bảo vệ trước session khác đang ghi đồng thời.

### 11.4. Không dùng DISTINCT để chọn tùy tiện một hàng

SELECT DISTINCT source_system, external_customer_id, email ... chỉ loại các hàng giống nhau trên toàn bộ cột được chọn. Nếu cùng business key có hai email khác nhau, cả hai hàng vẫn còn và MERGE vẫn gặp nhiều source rows cho một key.

DISTINCT không thể thay thế quy tắc survivorship. Dùng ROW_NUMBER với ORDER BY có ý nghĩa, GROUP BY với quy tắc tổng hợp rõ ràng, hoặc đưa xung đột vào quy trình xử lý thủ công.

## 12. Các phương án insert-if-absent và giới hạn của chúng

### 12.1. INSERT ... WHERE NOT EXISTS

Có thể viết:

```sql
INSERT INTO lab_customers (
    customer_id, source_system, external_customer_id, display_name
)
SELECT
    lab_customer_seq.NEXTVAL,
    :source_system,
    :external_customer_id,
    :display_name
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_customers c
    WHERE c.source_system = :source_system
      AND c.external_customer_id = :external_customer_id
);
```

Câu lệnh tránh INSERT nếu tại thời điểm statement nhìn thấy hàng đã tồn tại. Tuy nhiên, hai session đồng thời vẫn có thể cùng thấy NOT EXISTS và cùng thử INSERT. Vì vậy vẫn cần UNIQUE constraint và xử lý ORA-00001. NOT EXISTS ở đây là điều kiện logic, không phải khóa độc quyền.

### 12.2. MERGE so với INSERT-if-absent

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Chỉ tạo nếu chưa có, không cập nhật hàng hiện tại | INSERT-if-absent hoặc INSERT và bắt duplicate key |
| Tạo mới hoặc đồng bộ giá trị hiện tại | MERGE |
| Xử lý một event chỉ một lần | INSERT event ledger với EVENT_ID unique, rồi áp dụng hiệu ứng trong cùng transaction |
| Đồng bộ batch có nhiều hàng nguồn | Deduplicate/validate staging trước, sau đó MERGE |
| Cập nhật tăng/giảm theo event delta | Event key duy nhất + transaction; không chỉ dùng MERGE cộng dồn |

Chọn cú pháp theo ý nghĩa nghiệp vụ. Dù dùng cách nào, ràng buộc duy nhất ở database vẫn là lớp bảo vệ cuối cùng.

## 13. Quản lý transaction và lần chạy lại batch

Idempotency phụ thuộc vào ranh giới transaction. Cần xác định chính xác phần nào phải commit cùng nhau.

### 13.1. Commit business row và processed marker cùng nhau

Với một event database-only:

```text
BEGIN
    INSERT processed_event(event_id)   -- unique key
    UPDATE business_table             -- áp dụng event
    INSERT audit_row (nếu cần)
COMMIT
```

Nếu UPDATE thất bại, rollback cả processed_event. Nếu commit thành công, lần retry nhìn thấy processed_event và không áp dụng event lần nữa. Không tách hai thao tác thành hai transaction độc lập nếu không có cơ chế phục hồi tương ứng.

### 13.2. Savepoint khi xử lý nhiều record

Một batch có thể xử lý nhiều record trong một transaction hoặc commit theo chunk. Với mỗi record, có thể dùng SAVEPOINT để cô lập lỗi nghiệp vụ có thể phục hồi:

```sql
SAVEPOINT before_one_record;

-- Thử áp dụng một record ở đây.

-- Nếu record không hợp lệ và được phép bỏ qua:
ROLLBACK TO before_one_record;
```

SAVEPOINT chỉ rollback các thay đổi sau savepoint trong transaction hiện tại. Nó không thay thế idempotency key và không hoàn tác side effect ngoài database. Nếu record đã được commit ở chunk trước, lần chạy lại phải nhận diện record đó qua business/event key.

### 13.3. Batch có thể chạy lại

Một batch idempotent nên có:

- BATCH_ID hoặc nguồn xác định được lặp lại ổn định.
- Business key/event key duy nhất cho mỗi record nguồn.
- Staging được deduplicate và validate trước khi merge.
- Trạng thái từng record hoặc bảng audit để biết record thành công/lỗi.
- Transaction boundary rõ ràng (mỗi record, mỗi chunk hoặc cả batch).
- Cách tiếp tục từ record chưa hoàn tất mà không áp dụng lại hiệu ứng đã commit.

Không dựa vào “dòng thứ 500 trong file” làm định danh ổn định nếu thứ tự file có thể thay đổi. Dùng source record ID hoặc một khóa xác định từ dữ liệu nghiệp vụ.

### 13.4. Sequence có thể có khoảng trống

Oracle sequence không transactional theo nghĩa rollback giá trị NEXTVAL. Một lần INSERT thất bại hoặc transaction rollback vẫn có thể làm mất một số sequence value. Đây là hành vi bình thường; ID không cần liên tục để bảo đảm uniqueness.

Không tìm duplicate bằng cách giả định ID phải liền nhau, không tái sử dụng ID đã cấp và không dùng sequence value để suy ra số record đã commit. Idempotency phải dựa trên khóa request/event/business ổn định.

## 14. Kiểm tra ràng buộc trong Oracle

Sau khi tạo constraint, có thể xem metadata trong data dictionary.

### 14.1. Xem constraint của bảng

```sql
SELECT
    constraint_name,
    constraint_type,
    status,
    validated,
    deferrable,
    deferred
FROM user_constraints
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY constraint_name;
```

Một số loại constraint:

| CONSTRAINT_TYPE | Ý nghĩa |
| --- | --- |
| P | PRIMARY KEY |
| U | UNIQUE |
| R | FOREIGN KEY |
| C | CHECK (bao gồm NOT NULL được biểu diễn dưới dạng check metadata) |

STATUS cho biết constraint đang ENABLED hay DISABLED; VALIDATED cho biết dữ liệu hiện có đã được xác thực theo constraint hay chưa. Hãy kiểm tra cả hai, đừng chỉ nhìn thấy tên constraint trong schema rồi kết luận dữ liệu được bảo vệ đầy đủ.

### 14.2. Xem các cột của khóa ghép

```sql
SELECT
    constraint_name,
    column_name,
    position
FROM user_cons_columns
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY constraint_name, position;
```

Với khóa ghép, POSITION thể hiện thứ tự cột trong constraint. Đối chiếu danh sách cột với business key đã được thống nhất.

### 14.3. Xem index liên quan

```sql
SELECT
    index_name,
    uniqueness,
    status
FROM user_indexes
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name;
```

Có thể xem cột index:

```sql
SELECT
    index_name,
    column_name,
    column_position,
    descend
FROM user_ind_columns
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name, column_position;
```

Function-based index có biểu thức được thể hiện qua các view dictionary tương ứng (ví dụ USER_IND_EXPRESSIONS). Nếu dùng biểu thức chuẩn hóa, kiểm tra chính biểu thức thực thi thay vì chỉ nhìn tên index.

### 14.4. DEFERRABLE và thời điểm kiểm tra uniqueness

Mặc định, PRIMARY KEY/UNIQUE constraint được kiểm tra ngay trong statement. Constraint có thể được khai báo DEFERRABLE để trì hoãn kiểm tra đến cuối transaction (hoặc đặt trạng thái deferred theo cấu hình):

```sql
ALTER TABLE lab_example
ADD CONSTRAINT uq_lab_example_code
UNIQUE (code)
DEFERRABLE INITIALLY DEFERRED;
```

Điều này có thể hữu ích khi một transaction cần thay đổi nhiều hàng mà trạng thái trung gian tạm thời vi phạm uniqueness, nhưng trạng thái cuối phải hợp lệ. Nó không cho phép commit duplicate. Chỉ dùng khi nghiệp vụ cần; trì hoãn kiểm tra có thể làm lỗi xuất hiện muộn ở COMMIT và khiến xử lý lỗi khó hơn.

## 15. Kịch bản thực hành từ staging đến dữ liệu đích

### Bước 1 — Tạo bảng đích và sequence

```sql
CREATE TABLE lab_customers (
    customer_id NUMBER(12)
        CONSTRAINT pk_lab_customers PRIMARY KEY,
    source_system VARCHAR2(30) NOT NULL,
    external_customer_id VARCHAR2(80) NOT NULL,
    email VARCHAR2(320),
    display_name VARCHAR2(160),
    source_version NUMBER(12),
    updated_at TIMESTAMP
);

CREATE SEQUENCE lab_customer_seq START WITH 1 INCREMENT BY 1;

ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_source
UNIQUE (source_system, external_customer_id);
```

Trong ví dụ chạy độc lập, hãy chỉ tạo bảng/constraint một lần. Các đoạn DDL tương tự ở phần trước minh họa những cách lựa chọn; không chạy lại lệnh thêm cùng constraint nếu nó đã tồn tại.

### Bước 2 — Tạo staging và nạp một batch

Nếu chưa tạo bảng LAB_CUSTOMER_STAGE ở mục 11, chạy DDL ở đó. Sau đó nạp:

```sql
INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    1, 'BATCH-001', 'CRM_A', '9001',
    'an@example.com', 'An Nguyen', 1, SYSTIMESTAMP
);

INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    2, 'BATCH-001', 'CRM_A', '9001',
    'an.new@example.com', 'An Nguyen', 2, SYSTIMESTAMP
);

INSERT INTO lab_customer_stage (
    stage_row_id, batch_id, source_system,
    external_customer_id, email, display_name,
    source_version, loaded_at
)
VALUES (
    3, 'BATCH-001', 'CRM_B', '7002',
    'binh@example.com', 'Binh Tran', 1, SYSTIMESTAMP
);

COMMIT;
```

Hai hàng CRM_A có cùng business key nhưng version khác nhau. Quy tắc mẫu sẽ chọn version 2.

### Bước 3 — Kiểm tra duplicate trong batch

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customer_stage
WHERE batch_id = 'BATCH-001'
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;
```

Kết quả phải cho thấy CRM_A / 9001 có hai hàng. Không coi đó là hai khách hàng khác nhau.

### Bước 4 — MERGE từ một source row cho mỗi business key

Chạy truy vấn MERGE ở mục 11.3 với batch_id BATCH-001. Target sẽ có hai khách hàng: CRM_A / 9001 với version 2 và CRM_B / 7002 với version 1.

### Bước 5 — Chạy lại cùng batch

Chạy lại đúng MERGE với cùng batch_id. Không được tạo thêm hàng vì target đã có cùng business key. Các cột được gán lại theo payload nguồn. Nếu timestamp được gán SYSTIMESTAMP, timestamp có thể thay đổi; đó là side effect cần quyết định có chấp nhận hay không. Để batch hoàn toàn không thay đổi khi payload giống, thêm điều kiện UPDATE chỉ khi dữ liệu khác hoặc dùng version predicate.

### Bước 6 — Kiểm tra uniqueness và kết quả

```sql
SELECT source_system, external_customer_id, COUNT(*) AS row_count
FROM lab_customers
GROUP BY source_system, external_customer_id
HAVING COUNT(*) > 1;

SELECT *
FROM lab_customers
ORDER BY source_system, external_customer_id;
```

Truy vấn duplicate phải không trả hàng. Kiểm tra version và payload của bản ghi chuẩn đúng quy tắc.

## 16. Kiểm thử idempotency và concurrency

Một thao tác chỉ nên được gọi là idempotent sau khi kiểm tra nhiều đường chạy, không chỉ chạy một lần thành công.

### 16.1. Chạy cùng input hai lần

Ghi lại trạng thái trước, chạy batch/request lần thứ nhất, lưu số hàng và kết quả. Chạy lại đúng input với cùng business key/idempotency key, rồi so sánh:

- Số hàng business có tăng ngoài dự kiến không?
- Tổng tiền/số dư có bị cộng lại không?
- Audit/outbox event có bị nhân không?
- Timestamp/version có thay đổi theo chính sách mong muốn không?
- Response trả về có nhất quán không?

### 16.2. Thử cùng key nhưng payload khác

Gửi cùng idempotency key với payload khác. Hệ thống phải phát hiện conflict, không âm thầm trả kết quả cũ hoặc áp dụng payload thứ hai dưới cùng một request ID.

### 16.3. Thử hai session đồng thời

Mở hai session Oracle và gửi cùng business key gần như cùng lúc:

1. Xóa dữ liệu test hoặc chọn một key mới.
2. Chạy cùng MERGE/INSERT ở hai session.
3. Commit session đầu.
4. Quan sát session còn lại có chờ rồi nhận ORA-00001 hay không.
5. Xác nhận bảng đích vẫn chỉ có một hàng theo business key.
6. Kiểm tra ứng dụng xử lý duplicate race đúng và không lặp side effect.

Không kiểm thử concurrency trên production bằng cách tạo tải tùy tiện. Dùng schema và dữ liệu test có thể xóa/khôi phục.

### 16.4. Thử timeout quanh COMMIT

Mô phỏng các tình huống:

- Client mất kết nối trước khi database commit.
- Database commit thành công nhưng response không tới client.
- Worker chết sau khi đọc message nhưng trước khi commit.
- Worker commit thành công nhưng chết trước khi ack message.

Thiết kế phải phân biệt được “chưa commit” với “đã commit nhưng caller chưa nhận response”. Idempotency ledger/event key là cách để retry có thể tra lại trạng thái đã commit.

## 17. Các lỗi và bẫy thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| ORA-02299 khi thêm UNIQUE | Dữ liệu hiện có chứa duplicate | Phân nhóm, chọn canonical row, dọn dữ liệu rồi tạo constraint |
| ORA-00001 khi INSERT | Business key đã tồn tại hoặc writer đồng thời | Xác định constraint gây lỗi, đọc lại theo key và xử lý theo chính sách |
| ORA-00001 khi MERGE | Hai session cùng insert key mới hoặc nguồn có key xung đột | Giữ unique constraint; xử lý race và deduplicate source |
| ORA-30926 khi MERGE | Nhiều source rows tác động cùng target row hoặc source không ổn định | Chọn một source row/key hoặc tổng hợp nguồn trước |
| Dữ liệu vẫn trùng dù có PK | PK chỉ unique ID kỹ thuật, không unique business key | Thêm UNIQUE constraint trên business key |
| Unique email vẫn nhận biến thể hoa/thường | Constraint dùng giá trị gốc, chưa chuẩn hóa theo nghiệp vụ | Function-based unique index hoặc virtual normalized column |
| Có nhiều hàng NULL ở khóa unique | UNIQUE cho phép NULL theo quy tắc Oracle | Dùng NOT NULL nếu business key bắt buộc |
| Retry tạo thêm hàng | Mỗi lần retry sinh ID mới hoặc thiếu idempotency key | Dùng request/event key ổn định và unique constraint |
| Số dư bị cộng hai lần | UPDATE dạng delta chạy lại mà không có event ledger | Ghi EVENT_ID unique và cập nhật cùng transaction |
| MERGE ghi đè dữ liệu mới | Retry cũ không kiểm tra version | Dùng version/timestamp predicate và quy tắc conflict |
| Batch MERGE lỗi dù target chưa có key | Staging chứa nhiều hàng cho cùng key | Deduplicate hoặc xử lý xung đột nguồn trước MERGE |
| Xóa duplicate làm mất liên kết | Bảng con còn tham chiếu ID bị xóa | Chuyển FK sang canonical ID trước khi xóa |
| Batch chạy lại làm audit/outbox lặp | Side effect ngoài thao tác ghi chính chưa idempotent | Dùng event key, outbox và consumer dedup |
| ROLLBACK không khôi phục sequence | NEXTVAL không transactional | Chấp nhận khoảng trống; không dùng sequence để dedup |

## 18. Nguyên tắc thực hành tốt

1. **Định nghĩa business key trước khi viết SQL.** Đừng nhầm surrogate primary key với danh tính nghiệp vụ.
2. **Dùng UNIQUE constraint để database bảo vệ uniqueness.** Kiểm tra trước bằng SELECT không chống được race condition.
3. **Dùng NOT NULL cho thành phần khóa bắt buộc.** Không để NULL biểu diễn một định danh chưa biết nhưng vẫn mong uniqueness đầy đủ.
4. **Chuẩn hóa nhất quán.** Nếu trim/case-folding là quy tắc, áp dụng ở cả luồng ghi và ràng buộc database.
5. **Dọn dữ liệu theo survivorship rule xác định.** ROW_NUMBER cần ORDER BY có tie-breaker.
6. **Bảo toàn quan hệ tham chiếu.** Chuyển foreign key sang canonical ID trước khi xóa duplicate parent.
7. **Deduplicate nguồn trước MERGE.** Một source row cho mỗi business key trong một batch.
8. **Không giả định MERGE tự xử lý concurrency.** Giữ UNIQUE constraint và xử lý ORA-00001 từ đúng nguyên nhân.
9. **Thiết kế retry với key ổn định.** Không dùng sequence NEXTVAL làm idempotency key.
10. **Commit marker và business effect cùng transaction.** Nếu một bên commit còn bên kia không, retry có thể làm trạng thái sai.
11. **Kiểm tra payload khi key đã tồn tại.** Cùng key, khác payload là conflict cần xử lý rõ.
12. **Tách side effect ngoài database.** Dùng outbox và yêu cầu consumer/dịch vụ ngoài hỗ trợ dedup.
13. **Kiểm thử chạy lại và hai session đồng thời.** Chạy đơn lẻ một lần không chứng minh idempotency.
14. **Theo dõi constraint status và audit.** Đảm bảo ràng buộc thực sự ENABLED/VALIDATED theo mục tiêu.

## 19. Câu hỏi tự kiểm tra

1. Hai hàng giống nhau ở mọi cột hiển thị có nhất thiết là cùng một thực thể nghiệp vụ không?
2. Vì sao surrogate primary key không đủ để ngăn import cùng một khách hàng hai lần?
3. UNIQUE constraint khác PRIMARY KEY ở điểm nào?
4. Khi nào cần NOT NULL bên cạnh UNIQUE?
5. Function-based unique index với UPPER(TRIM(email)) bảo vệ điều gì?
6. Vì sao phải xác định quy tắc chuẩn hóa email với nghiệp vụ trước khi tạo index?
7. ORA-02299 khác ORA-00001 như thế nào?
8. Vì sao ROW_NUMBER cần tie-breaker duy nhất khi chọn canonical row?
9. Tại sao phải chuyển foreign key sang canonical customer trước khi xóa duplicate?
10. Idempotency khác uniqueness như thế nào?
11. Vì sao SELECT NOT EXISTS rồi INSERT vẫn có race condition?
12. MERGE xử lý MATCHED và NOT MATCHED ra sao?
13. Vì sao MERGE có thể vẫn nhận ORA-00001 khi hai session cùng insert business key mới?
14. ORA-30926 có thể xuất hiện khi staging có nhiều source rows cho một target key như thế nào?
15. Vì sao UPDATE balance = balance + amount không idempotent khi event bị phát lại?
16. Idempotency key nên được scope theo những thông tin nào?
17. Vì sao cùng idempotency key nhưng request hash khác phải được xem là conflict?
18. Tại sao ledger row và business update nên commit trong cùng transaction?
19. Transactional outbox giải quyết phần nào và vì sao consumer vẫn cần deduplicate?
20. Vì sao sequence có thể có khoảng trống sau rollback?

## 20. Mô hình ghi nhớ

```text
ĐỊNH NGHĨA DANH TÍNH
    │
    ├── Surrogate PK: nhận diện hàng trong database
    ├── Business UNIQUE: nhận diện thực thể nghiệp vụ
    └── Idempotency key: nhận diện request/event được retry
    │
    ▼
NGĂN DUPLICATE
    │
    ├── NOT NULL cho khóa bắt buộc
    ├── UNIQUE constraint / unique index
    └── Chuẩn hóa khóa nhất quán
    │
    ▼
DỌN DỮ LIỆU CŨ
    │
    ├── GROUP BY / HAVING để phát hiện
    ├── ROW_NUMBER để chọn canonical row
    ├── Chuyển FK và hợp nhất thuộc tính
    └── Xóa/archive hàng dư rồi xác thực constraint
    │
    ▼
GHI CÓ THỂ RETRY
    │
    ├── MERGE / INSERT theo business key
    ├── Deduplicate source trước MERGE
    ├── Xử lý ORA-00001 và concurrency race
    ├── Ledger + business update cùng transaction
    └── Outbox cho side effect bên ngoài
    │
    ▼
KIỂM CHỨNG
    ├── Chạy cùng input nhiều lần
    ├── Cùng key, payload khác
    ├── Hai session đồng thời
    └── Timeout trước/sau COMMIT
```

**Điểm cần nhớ:** UNIQUE constraint bảo vệ danh tính dữ liệu; idempotency key bảo vệ hiệu ứng khi cùng yêu cầu được gửi lại. MERGE hữu ích cho upsert nhưng không thay thế constraint, không tự giải quyết source duplicate và không bảo đảm mọi side effect chỉ xảy ra một lần. Hãy định nghĩa đúng business key, dọn duplicate theo quy tắc xác định, giữ marker và thay đổi nghiệp vụ trong cùng transaction, rồi kiểm thử cả retry lẫn concurrency.

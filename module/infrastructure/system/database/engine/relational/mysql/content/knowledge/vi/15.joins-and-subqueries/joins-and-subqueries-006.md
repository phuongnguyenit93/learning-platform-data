# Mô phỏng FULL OUTER JOIN và kiểm chứng dữ liệu trùng

`FULL OUTER JOIN` trả về mọi hàng của cả hai bảng: hàng khớp được ghép với nhau, hàng chỉ có ở bảng trái vẫn xuất hiện với các cột bảng phải là `NULL`, và hàng chỉ có ở bảng phải vẫn xuất hiện với các cột bảng trái là `NULL`. MySQL không cung cấp cú pháp `FULL OUTER JOIN` trực tiếp, vì vậy cần mô phỏng kết quả bằng các phép JOIN có sẵn.

Mẫu thường dùng là ghép một `LEFT JOIN` với phần hàng chỉ có ở bảng phải bằng `UNION ALL`. Khi dữ liệu khóa nối có giá trị trùng, kết quả có thể tăng thành nhiều cặp ghép. Đây thường là ngữ nghĩa đúng của phép JOIN, nhưng có thể làm báo cáo đếm hoặc tổng tiền bị nhân lên nếu người viết truy vấn giả định khóa là duy nhất. Bài học này hướng dẫn cách mô phỏng FULL OUTER JOIN, kiểm tra cardinality và duplicate key, phân biệt dữ liệu trùng với cặp ghép hợp lệ, đồng thời xác minh kết quả trước khi đưa vào báo cáo.

Trong module `DATABASE_MYSQL`, kỹ năng này hỗ trợ đối soát dữ liệu giữa hai hệ thống, đồng bộ danh mục, so sánh bản ghi khách hàng, kiểm tra dữ liệu import và phát hiện bản ghi chỉ tồn tại ở một phía. Điều quan trọng là phải xác định rõ khóa nối và ý nghĩa của NULL trước khi viết truy vấn.

## 1. FULL OUTER JOIN cần trả về những hàng nào?

Giả sử có hai tập dữ liệu A và B, nối theo `external_code`. Kết quả FULL OUTER JOIN gồm ba nhóm:

1. **MATCHED:** hàng A có ít nhất một hàng B thỏa điều kiện nối; mỗi cặp khớp được trả về.
2. **LEFT_ONLY:** hàng A không có hàng B tương ứng; các cột B là `NULL`.
3. **RIGHT_ONLY:** hàng B không có hàng A tương ứng; các cột A là `NULL`.

Minh họa:

```text
Tập A                    Tập B
+----+------+            +-----+------+
| id | code |            | id  | code |
+----+------+            +-----+------+
| 1  | A    |            | 101 | A    |
| 2  | B    |            | 102 | C    |
| 3  | D    |            | 103 | D    |
+----+------+            +-----+------+

FULL OUTER JOIN theo code:
+------+-------+--------+
| A.id | code  | B.id   |
+------+-------+--------+
| 1    | A     | 101    |  MATCHED
| 2    | B     | NULL   |  LEFT_ONLY
| 3    | D     | 103    |  MATCHED
| NULL | C     | 102    |  RIGHT_ONLY
+------+-------+--------+
```

Kết quả phải giữ lại hàng không khớp ở cả hai phía. Chỉ dùng `INNER JOIN` sẽ làm mất hàng lệch; chỉ dùng `LEFT JOIN` sẽ làm mất hàng chỉ có ở bảng phải.

## 2. MySQL không có cú pháp FULL OUTER JOIN trực tiếp

Trong MySQL, có thể mô phỏng FULL OUTER JOIN bằng hai nhánh:

- Nhánh thứ nhất: `A LEFT JOIN B`, lấy toàn bộ hàng A và các hàng B khớp.
- Nhánh thứ hai: `B LEFT JOIN A`, chỉ lấy những hàng B không tìm thấy hàng A tương ứng.
- Ghép hai nhánh bằng `UNION ALL`.

Mẫu tổng quát:

```sql
SELECT
    a.id AS a_id,
    a.join_key,
    a.value AS a_value,
    b.id AS b_id,
    b.value AS b_value
FROM table_a AS a
LEFT JOIN table_b AS b
    ON b.join_key = a.join_key

UNION ALL

SELECT
    a.id AS a_id,
    b.join_key,
    a.value AS a_value,
    b.id AS b_id,
    b.value AS b_value
FROM table_b AS b
LEFT JOIN table_a AS a
    ON a.join_key = b.join_key
WHERE a.id IS NULL;
```

`a.id` phải là cột định danh không NULL, thường là primary key. Điều kiện `WHERE a.id IS NULL` khi đó nhận diện chính xác những hàng B không có hàng A khớp. Không nên dùng chính cột nối làm dấu hiệu anti-join nếu cột nối có thể NULL.

`UNION ALL` là lựa chọn có chủ ý. Nó giữ nguyên số lần xuất hiện của từng cặp hàng, phù hợp với ngữ nghĩa bag/multiset của JOIN. Dùng `UNION` có bước loại hàng trùng và có thể làm thay đổi kết quả đối soát.

## 3. Tạo dữ liệu mẫu có khóa trùng và NULL

Để thấy rõ tác động của duplicate key, tạo hai bảng có primary key riêng nhưng `external_code` không unique:

```sql
CREATE TABLE source_a (
    id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(20) NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_source_a_external_code (external_code)
) ENGINE=InnoDB;

CREATE TABLE source_b (
    id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(20) NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_source_b_external_code (external_code)
) ENGINE=InnoDB;

INSERT INTO source_a (id, external_code, description)
VALUES
    (1, 'X', 'A-X-1'),
    (2, 'X', 'A-X-2'),
    (3, 'Y', 'A-Y'),
    (4, NULL, 'A-NULL');

INSERT INTO source_b (id, external_code, description)
VALUES
    (101, 'X', 'B-X-1'),
    (102, 'X', 'B-X-2'),
    (103, 'Z', 'B-Z'),
    (104, NULL, 'B-NULL');
```

Dữ liệu có các tình huống:

- Mã `X` xuất hiện hai lần trong A và hai lần trong B.
- Mã `Y` chỉ có ở A.
- Mã `Z` chỉ có ở B.
- Mỗi bảng có một hàng mà `external_code` là NULL.

Kiểm tra từng nguồn trước khi JOIN:

```sql
SELECT id, external_code, description
FROM source_a
ORDER BY id;

SELECT id, external_code, description
FROM source_b
ORDER BY id;
```

## 4. Viết truy vấn FULL OUTER JOIN mô phỏng

Với hai bảng trên, truy vấn hoàn chỉnh:

```sql
SELECT
    a.id AS a_id,
    COALESCE(a.external_code, b.external_code) AS external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description,
    CASE
        WHEN b.id IS NULL THEN 'LEFT_ONLY'
        ELSE 'MATCHED'
    END AS row_type
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code

UNION ALL

SELECT
    a.id AS a_id,
    COALESCE(a.external_code, b.external_code) AS external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description,
    'RIGHT_ONLY' AS row_type
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code = b.external_code
WHERE a.id IS NULL;
```

Nhánh thứ nhất giữ toàn bộ A. Nếu B không khớp, `b.id` NULL và `row_type` là `LEFT_ONLY`; nếu có ít nhất một cặp khớp, dòng mang loại `MATCHED`. Nhánh thứ hai chỉ thêm hàng B không tìm được A, tránh lặp lại các cặp đã xuất hiện ở nhánh đầu.

`COALESCE(a.external_code, b.external_code)` giúp lấy mã từ phía còn dữ liệu khi một bên không tồn tại. Nếu cả hai cột đều NULL, kết quả vẫn NULL. Với các cột khác, hãy chọn rõ nguồn cần hiển thị hoặc dùng biểu thức tương ứng.

Trong ví dụ dùng điều kiện `=`, hai giá trị NULL không khớp nhau. Vì vậy `A-NULL` là `LEFT_ONLY`, còn `B-NULL` là `RIGHT_ONLY`. Đây là hành vi SQL thông thường của phép so sánh bằng.

## 5. Vì sao khóa trùng làm số dòng tăng theo phép nhân?

Với một giá trị khóa `k`:

- Nếu A có `m` hàng mang khóa `k`.
- Nếu B có `n` hàng mang khóa `k`.
- Khi JOIN theo khóa đó, kết quả có `m × n` cặp.

Trong fixture, mã `X` có hai hàng ở A và hai hàng ở B, nên JOIN tạo bốn cặp:

```text
A-X-1  <->  B-X-1
A-X-1  <->  B-X-2
A-X-2  <->  B-X-1
A-X-2  <->  B-X-2
```

Đây không phải lỗi của `FULL OUTER JOIN` mô phỏng. Nó là ngữ nghĩa đúng khi điều kiện nối cho phép nhiều hàng ở mỗi phía. Các hàng còn lại tạo thêm:

- `A-Y`: một hàng LEFT_ONLY.
- `A-NULL`: một hàng LEFT_ONLY vì `NULL = NULL` là UNKNOWN.
- `B-Z`: một hàng RIGHT_ONLY.
- `B-NULL`: một hàng RIGHT_ONLY vì không có hàng A khớp theo dấu `=`.

Tổng số dòng kết quả là 8: bốn cặp MATCHED và bốn hàng chỉ có ở một phía. Số dòng kết quả có thể lớn hơn số hàng ở từng bảng; không được giả định mỗi hàng nguồn chỉ xuất hiện một lần.

### Khi nào phép nhân là đúng?

Nếu dữ liệu mô tả quan hệ nhiều-nhiều, nhiều hàng cùng khóa là hợp lệ. Ví dụ một mã sản phẩm có nhiều bản ghi giá theo khu vực và nhiều bản ghi tồn kho theo kho. JOIN theo mã sản phẩm sẽ tạo mọi cặp giá-kho; cần xem đó có đúng mục tiêu báo cáo không.

Nếu nghiệp vụ yêu cầu một-một hoặc nhiều-một, khóa phía được kỳ vọng duy nhất phải được kiểm tra và bảo vệ bằng unique constraint. Không dùng `DISTINCT` để che đi việc khóa không đáp ứng cardinality mong muốn.

## 6. Phát hiện duplicate key trước khi JOIN

Kiểm tra khóa trùng ở bảng A:

```sql
SELECT
    external_code,
    COUNT(*) AS row_count
FROM source_a
GROUP BY external_code
HAVING COUNT(*) > 1;
```

Kiểm tra tương tự ở bảng B:

```sql
SELECT
    external_code,
    COUNT(*) AS row_count
FROM source_b
GROUP BY external_code
HAVING COUNT(*) > 1;
```

`GROUP BY` gom các giá trị NULL vào cùng một nhóm, vì vậy truy vấn cũng có thể phát hiện nhiều hàng NULL. Nếu muốn chỉ kiểm tra khóa có giá trị:

```sql
SELECT external_code, COUNT(*) AS row_count
FROM source_a
WHERE external_code IS NOT NULL
GROUP BY external_code
HAVING COUNT(*) > 1;
```

Với khóa ghép, phải kiểm tra toàn bộ thành phần theo đúng điều kiện JOIN:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS row_count
FROM imported_customers
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Nếu điều kiện JOIN dùng `(tenant_id, external_code)` mà chỉ kiểm tra `external_code`, kết luận về tính duy nhất sẽ sai vì cùng mã có thể hợp lệ ở tenant khác nhau.

## 7. Đếm số cặp khớp và dự báo cardinality

Để hiểu mức tăng dòng, đếm số lần xuất hiện của từng khóa ở hai phía:

```sql
SELECT
    'A' AS source_name,
    external_code,
    COUNT(*) AS rows_per_key
FROM source_a
GROUP BY external_code

UNION ALL

SELECT
    'B' AS source_name,
    external_code,
    COUNT(*) AS rows_per_key
FROM source_b
GROUP BY external_code
ORDER BY external_code, source_name;
```

Với các khóa không NULL được nối bằng `=`, số cặp khớp của một khóa bằng số hàng A nhân số hàng B. Có thể tính riêng các khóa xuất hiện ở cả hai bảng:

```sql
SELECT
    a.external_code,
    a.rows_a,
    b.rows_b,
    a.rows_a * b.rows_b AS expected_match_pairs
FROM (
    SELECT external_code, COUNT(*) AS rows_a
    FROM source_a
    WHERE external_code IS NOT NULL
    GROUP BY external_code
) AS a
JOIN (
    SELECT external_code, COUNT(*) AS rows_b
    FROM source_b
    WHERE external_code IS NOT NULL
    GROUP BY external_code
) AS b
    ON b.external_code = a.external_code
ORDER BY a.external_code;
```

Truy vấn chỉ dự báo số cặp khớp cho khóa không NULL theo phép bằng thông thường. Nếu điều kiện JOIN có thêm tenant, trạng thái, khoảng thời gian hoặc biểu thức chuẩn hóa, phải đưa đầy đủ các điều kiện đó vào bước đếm.

## 8. Kiểm chứng kết quả mô phỏng

Đối soát nên kiểm tra ít nhất ba điều:

1. Mọi hàng A xuất hiện trong kết quả ít nhất một lần.
2. Mọi hàng B xuất hiện trong kết quả ít nhất một lần.
3. Hàng khớp được trả về theo từng cặp; hàng không khớp được gắn đúng loại LEFT_ONLY hoặc RIGHT_ONLY.

Có thể bọc truy vấn FULL OUTER JOIN mô phỏng thành CTE để thống kê:

```sql
WITH full_result AS (
    SELECT
        a.id AS a_id,
        COALESCE(a.external_code, b.external_code) AS external_code,
        b.id AS b_id,
        CASE WHEN b.id IS NULL THEN 'LEFT_ONLY'
             ELSE 'MATCHED' END AS row_type
    FROM source_a AS a
    LEFT JOIN source_b AS b
        ON b.external_code = a.external_code

    UNION ALL

    SELECT
        a.id AS a_id,
        COALESCE(a.external_code, b.external_code) AS external_code,
        b.id AS b_id,
        'RIGHT_ONLY' AS row_type
    FROM source_b AS b
    LEFT JOIN source_a AS a
        ON a.external_code = b.external_code
    WHERE a.id IS NULL
)
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT a_id) AS source_a_rows_represented,
    COUNT(DISTINCT b_id) AS source_b_rows_represented,
    SUM(row_type = 'MATCHED') AS matched_pairs,
    SUM(row_type = 'LEFT_ONLY') AS left_only_rows,
    SUM(row_type = 'RIGHT_ONLY') AS right_only_rows
FROM full_result;
```

Trong fixture, `source_a_rows_represented` và `source_b_rows_represented` đều bằng 4, `matched_pairs` bằng 4, `left_only_rows` bằng 2 và `right_only_rows` bằng 2; tổng output là 8. Các chỉ số distinct ID kiểm tra mức bao phủ hàng nguồn, còn `matched_pairs` đếm số cặp khớp. Hai khái niệm này khác nhau khi có duplicate key.

CTE yêu cầu MySQL 8.0 trở lên. Trên MySQL 5.7, có thể bọc UNION trong derived table rồi tính các aggregate ở truy vấn ngoài.

## 9. Chọn cột anti-join đúng cách

Trong nhánh thứ hai, mẫu phổ biến là:

```sql
WHERE a.id IS NULL
```

Điều này chỉ an toàn khi `a.id` không thể NULL ở hàng thật, ví dụ primary key. Nếu dùng `a.external_code IS NULL` để kiểm tra không có hàng A, một hàng A có `external_code` NULL có thể bị nhầm là không tìm thấy, đặc biệt khi điều kiện nối dùng `<=>` hoặc có logic phức tạp.

Một cách khác là dùng `NOT EXISTS` để lấy hàng B không có A tương ứng:

```sql
SELECT
    b.id,
    b.external_code,
    b.description
FROM source_b AS b
WHERE NOT EXISTS (
    SELECT 1
    FROM source_a AS a
    WHERE a.external_code = b.external_code
);
```

`NOT EXISTS` biểu đạt trực tiếp anti-join và không cần kiểm tra cột NULL từ phía A. Với phép bằng thông thường, hàng B có `external_code IS NULL` cũng không tìm thấy A vì `a.external_code = NULL` không TRUE; do đó hàng đó được trả về. Hãy chọn giữa `LEFT JOIN ... IS NULL` và `NOT EXISTS` bằng cách đo trên dữ liệu thực tế, không chỉ dựa vào kiểu viết.

## 10. NULL trong khóa nối: `=` hay `<=>`?

Với điều kiện:

```sql
ON a.external_code = b.external_code
```

hai NULL không khớp nhau. Đây là hành vi thông thường vì `NULL = NULL` trả về UNKNOWN.

Nếu nghiệp vụ muốn coi hai giá trị NULL là tương đương, MySQL có toán tử NULL-safe equality `<=>`:

```sql
ON a.external_code <=> b.external_code
```

Khi dùng `<=>`, NULL ở A có thể khớp NULL ở B. Tuy nhiên, nếu A có `m` hàng NULL và B có `n` hàng NULL, kết quả sẽ có `m × n` cặp NULL. Điều này có thể tạo ra lượng dòng lớn bất ngờ.

Nếu đổi sang `<=>`, phải dùng cùng điều kiện trong cả hai nhánh của mô phỏng FULL OUTER JOIN:

```sql
SELECT a.id AS a_id, b.id AS b_id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON a.external_code <=> b.external_code

UNION ALL

SELECT a.id AS a_id, b.id AS b_id
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code <=> b.external_code
WHERE a.id IS NULL;
```

Chỉ dùng cách này khi NULL thực sự đại diện cho cùng một giá trị có thể ghép. Trong nhiều hệ thống, NULL có nghĩa là “chưa biết mã”, nên hai hàng NULL không nên được coi là cùng một đối tượng. Hãy ghi rõ quy tắc NULL trong tài liệu đối soát.

## 11. Phân biệt duplicate source record và duplicate do JOIN

Có hai tình huống dễ bị gọi chung là “dữ liệu trùng”:

- **Duplicate ở nguồn:** một bảng có nhiều hàng cùng khóa hoặc nhiều bản ghi giống nhau theo tiêu chí nghiệp vụ.
- **Nhiều cặp ghép hợp lệ:** cả hai bảng đều có nhiều hàng cùng khóa; phép JOIN tạo tích Descartes trong từng nhóm khóa.

Ví dụ mã `X` có hai hàng ở A và hai hàng ở B. Bốn cặp ghép không nhất thiết là bốn bản ghi nguồn trùng hoàn toàn. Chúng là bốn tổ hợp giữa hai hàng A và hai hàng B.

Để xác định duplicate nguồn, cần định nghĩa grain (mức duy nhất) của từng bảng. Ví dụ:

- `source_a.id` là duy nhất vì primary key.
- `source_a.external_code` có thể không duy nhất nếu một mã có nhiều phiên bản.
- Nếu nghiệp vụ yêu cầu một `external_code` duy nhất trong từng tenant, khóa duy nhất phải là `(tenant_id, external_code)`.

Kiểm tra bản ghi giống nhau theo nhiều thuộc tính:

```sql
SELECT
    external_code,
    description,
    COUNT(*) AS duplicate_count
FROM source_a
GROUP BY external_code, description
HAVING COUNT(*) > 1;
```

Truy vấn này phát hiện các hàng trùng theo cặp thuộc tính được chọn, không chứng minh hai hàng trùng về mọi cột. Muốn loại bỏ duplicate, cần xác định hàng nào là bản chuẩn, lịch sử nào phải giữ và quy tắc hợp nhất dữ liệu.

## 12. Đừng dùng DISTINCT để che lỗi cardinality

Một cách xử lý sai thường gặp là thêm `DISTINCT` sau JOIN khi kết quả có quá nhiều hàng:

```sql
SELECT DISTINCT
    a.external_code,
    a.description,
    b.description
FROM source_a AS a
JOIN source_b AS b
    ON b.external_code = a.external_code;
```

`DISTINCT` chỉ loại những hàng trùng hoàn toàn trên các cột được SELECT. Nó không sửa điều kiện JOIN sai, không bảo đảm mỗi hàng nguồn chỉ xuất hiện một lần và có thể làm mất các cặp hợp lệ nếu projection không chứa khóa định danh của hai phía.

Nếu muốn một hàng đại diện từ B cho mỗi mã, hãy định nghĩa quy tắc chọn hàng trước khi JOIN, chẳng hạn bản cập nhật mới nhất theo `updated_at` với tie-breaker bằng primary key. Trên MySQL 8.0, có thể dùng `ROW_NUMBER()`:

```sql
WITH ranked_b AS (
    SELECT
        b.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_code
            ORDER BY updated_at DESC, id DESC
        ) AS rn
    FROM source_b AS b
)
SELECT
    a.id AS a_id,
    a.external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description
FROM source_a AS a
LEFT JOIN ranked_b AS b
    ON b.external_code = a.external_code
   AND b.rn = 1;
```

Đây là ví dụ `LEFT JOIN` chọn một hàng B theo quy tắc, không phải FULL OUTER JOIN hoàn chỉnh. Nếu cần mô phỏng FULL OUTER JOIN sau khi chọn bản ghi đại diện, phải dùng cùng tập `ranked_b` trong cả hai nhánh và viết anti-join cho phía B. Hãy quyết định quy tắc chọn bản ghi dựa trên nghiệp vụ, không tùy tiện chọn `MAX(id)` nếu ID không phản ánh thứ tự cập nhật.

## 13. Điều kiện JOIN và bộ lọc WHERE có thể làm mất hàng ngoài

Với OUTER JOIN, vị trí đặt điều kiện có ý nghĩa:

```sql
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code
   AND b.status = 'ACTIVE';
```

Điều kiện `b.status = 'ACTIVE'` trong `ON` giới hạn hàng B được phép khớp, nhưng vẫn giữ mọi hàng A; A không có B active sẽ có cột B NULL.

Nếu viết:

```sql
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code
WHERE b.status = 'ACTIVE';
```

`WHERE` loại các hàng mà `b.status` là NULL, khiến kết quả thực tế mất các hàng không khớp và hành xử gần như INNER JOIN đối với điều kiện đó.

Khi mô phỏng FULL OUTER JOIN, hãy quyết định điều kiện nào xác định “được phép khớp” và điều kiện nào lọc kết quả cuối. Nếu thêm filter cho bảng phải, áp dụng nhất quán ở đúng vị trí trong cả hai nhánh; nếu không, có thể làm sai tập LEFT_ONLY hoặc RIGHT_ONLY.

## 14. Chuẩn hóa khóa và tương thích kiểu dữ liệu

Hai cột nối nên có kiểu dữ liệu và quy tắc so sánh tương thích. Nếu một phía là số và phía kia là chuỗi, MySQL có thể thực hiện chuyển đổi ngầm; điều đó có thể làm kết quả bất ngờ và ảnh hưởng khả năng sử dụng index.

Ví dụ các vấn đề cần kiểm tra:

- `INT` nối với `VARCHAR` chứa mã có số 0 ở đầu.
- `CHAR` nối với `VARCHAR` có khoảng trắng cuối.
- Hai cột văn bản có character set hoặc collation khác nhau.
- Một phía phân biệt hoa/thường, phía kia không phân biệt.
- Mã nguồn có dấu cách đầu/cuối hoặc ký tự Unicode chuẩn hóa khác nhau.
- Khóa ghép thiếu tenant hoặc loại thực thể trong điều kiện JOIN.

Không dùng `TRIM()`, `LOWER()` hoặc `CAST()` tùy tiện ngay trên cột JOIN trong mọi truy vấn. Nếu cần chuẩn hóa, xác định quy tắc ở tầng nhập dữ liệu hoặc tạo cột chuẩn hóa riêng có index. Kiểm tra `EXPLAIN` để xem biểu thức có làm mất index lookup hay không.

## 15. Index và hiệu năng của mô phỏng FULL OUTER JOIN

Mẫu mô phỏng thực hiện hai nhánh JOIN, vì vậy mỗi bảng cần khả năng tra cứu theo khóa nối. Với fixture, đã tạo index:

```sql
KEY idx_source_a_external_code (external_code)
KEY idx_source_b_external_code (external_code)
```

Một số nguyên tắc:

- Tạo index trên cột dùng trong điều kiện JOIN, nếu workload và độ chọn lọc cho thấy có lợi.
- Với khóa ghép, index nên phản ánh thứ tự cột và điều kiện truy vấn, ví dụ `(tenant_id, external_code)`.
- Nếu khóa được kỳ vọng duy nhất, dùng `UNIQUE` sau khi làm sạch và xác minh dữ liệu.
- Tránh ép kiểu hoặc bọc hàm lên cột JOIN nếu muốn tận dụng index thông thường.
- Kiểm tra cả hai nhánh bằng `EXPLAIN`; optimizer có thể chọn access path khác nhau.
- Đánh giá số hàng ước lượng và thực tế, nhất là khi khóa có nhiều duplicate.

Ví dụ kiểm tra từng phía:

```sql
EXPLAIN
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code;

EXPLAIN
SELECT a.id, b.id
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code = b.external_code
WHERE a.id IS NULL;
```

`EXPLAIN ANALYZE` trên phiên bản hỗ trợ có thể thực thi truy vấn để đo số hàng thực tế và thời gian từng iterator. Chạy trên staging hoặc dữ liệu thử nghiệm nếu truy vấn có thể quét nhiều hàng.

## 16. Đối soát dữ liệu thực tế giữa hai hệ thống

Một quy trình đối soát thường gồm các bước:

1. Xác định grain của mỗi nguồn: một hàng đại diện cho thực thể nào?
2. Xác định khóa nối: một cột hay khóa ghép; có NULL hợp lệ không?
3. Kiểm tra kiểu dữ liệu, character set, collation và quy tắc chuẩn hóa của khóa.
4. Đếm duplicate key ở từng nguồn trước khi JOIN.
5. Ước lượng số cặp khớp bằng `count_A × count_B` theo từng khóa.
6. Chạy FULL OUTER JOIN mô phỏng với ID của cả hai phía và `row_type`.
7. Kiểm tra số hàng được đại diện ở mỗi nguồn bằng `COUNT(DISTINCT source_id)`.
8. Phân tích LEFT_ONLY, RIGHT_ONLY và MATCHED riêng biệt.
9. Xử lý duplicate theo quy tắc nghiệp vụ; không xóa bằng `DISTINCT` nếu chưa xác định bản ghi chuẩn.
10. Lưu truy vấn và số liệu đối soát để có thể chạy lại sau mỗi lần đồng bộ.

Ví dụ chỉ lấy các bản ghi lệch để điều tra:

```sql
WITH full_result AS (
    SELECT
        a.id AS a_id,
        a.external_code,
        a.description AS a_description,
        b.id AS b_id,
        b.description AS b_description,
        CASE WHEN b.id IS NULL THEN 'LEFT_ONLY'
             ELSE 'MATCHED' END AS row_type
    FROM source_a AS a
    LEFT JOIN source_b AS b
        ON b.external_code = a.external_code

    UNION ALL

    SELECT
        a.id AS a_id,
        b.external_code,
        a.description AS a_description,
        b.id AS b_id,
        b.description AS b_description,
        'RIGHT_ONLY' AS row_type
    FROM source_b AS b
    LEFT JOIN source_a AS a
        ON a.external_code = b.external_code
    WHERE a.id IS NULL
)
SELECT *
FROM full_result
WHERE row_type <> 'MATCHED'
ORDER BY row_type, external_code, a_id, b_id;
```

Truy vấn này tập trung vào bản ghi chỉ xuất hiện ở một nguồn. Nếu cần kiểm tra nội dung khác nhau giữa hai hàng có cùng khóa, giữ lại `MATCHED` và so sánh các cột nghiệp vụ bằng quy tắc NULL-safe phù hợp.

## 17. Kiểm tra khác biệt giữa các hàng đã khớp

JOIN chỉ chứng minh hai hàng thỏa điều kiện khóa; nó không chứng minh các thuộc tính khác giống nhau. Để tìm bản ghi có cùng mã nhưng khác mô tả:

```sql
SELECT
    a.id AS a_id,
    b.id AS b_id,
    a.external_code,
    a.description AS a_description,
    b.description AS b_description
FROM source_a AS a
JOIN source_b AS b
    ON b.external_code = a.external_code
WHERE NOT (a.description <=> b.description);
```

`<=>` là NULL-safe equality trong MySQL. `NOT (a.description <=> b.description)` tìm các cặp có mô tả khác nhau, bao gồm trường hợp một bên NULL và bên kia có giá trị; hai NULL được xem là giống nhau. Nếu muốn so sánh theo byte thay vì collation văn bản, cần dùng kiểu dữ liệu hoặc biểu thức nhị phân thích hợp.

Khi có duplicate key, truy vấn này so sánh mọi cặp cùng khóa. Nếu A có hai hàng và B có ba hàng cùng mã, nó kiểm tra sáu cặp. Để so sánh một-một, cần chọn hoặc ghép bản ghi theo khóa nghiệp vụ đầy đủ trước khi so sánh thuộc tính.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `LEFT JOIN` đơn lẻ và nghĩ đã có FULL OUTER JOIN | Mất hàng chỉ có ở bảng phải | Thêm nhánh anti-join từ B sang A. |
| Dùng `UNION` thay `UNION ALL` | Loại các hàng trùng hoàn toàn và thay đổi số lần xuất hiện | Dùng `UNION ALL` để giữ multiplicity. |
| Kiểm tra anti-join bằng cột nối nullable | Hàng thật có khóa NULL có thể bị nhận nhầm là không khớp | Kiểm tra primary key không NULL của phía được LEFT JOIN. |
| Bỏ qua duplicate key | Kết quả tăng theo `m × n` | Đếm số hàng mỗi khóa ở cả hai nguồn trước JOIN. |
| Thêm `DISTINCT` để giảm số dòng | Có thể xóa các cặp hợp lệ mà không sửa nguyên nhân | Xác định grain và cardinality; xử lý duplicate theo nghiệp vụ. |
| Dùng `=` nhưng mong NULL khớp NULL | Hàng NULL ở hai phía được coi là không khớp | Chỉ dùng `<=>` nếu NULL có ý nghĩa tương đương. |
| Dùng `<=>` với nhiều NULL mà không dự báo | Có thể tạo tích `m × n` giữa hai nhóm NULL | Quy định rõ semantics NULL và đo cardinality. |
| Đặt filter phía phải trong WHERE của LEFT JOIN | Làm mất hàng không khớp | Đưa điều kiện khớp vào ON nếu cần giữ hàng trái. |
| Chỉ kiểm tra mã mà bỏ qua tenant hoặc loại thực thể | Ghép nhầm các bản ghi khác phạm vi | Dùng đầy đủ khóa ghép theo nghiệp vụ. |
| Không kiểm tra kiểu/collation của khóa | Chuyển đổi ngầm, so sánh không như dự kiến hoặc giảm hiệu năng | Chuẩn hóa schema và xác minh bằng metadata/EXPLAIN. |

## 19. Bài tập thực hành

### Bài tập A — Mô phỏng FULL OUTER JOIN

1. Tạo `source_a` và `source_b` theo fixture.
2. Viết nhánh `A LEFT JOIN B`.
3. Viết nhánh `B LEFT JOIN A WHERE A.id IS NULL`.
4. Ghép bằng `UNION ALL` và thêm `row_type`.
5. Xác nhận các hàng MATCHED, LEFT_ONLY và RIGHT_ONLY.

### Bài tập B — Đo ảnh hưởng duplicate key

1. Đếm số hàng theo `external_code` ở mỗi nguồn.
2. Tính `rows_a × rows_b` cho từng khóa khớp.
3. Chạy JOIN và đếm số cặp thực tế.
4. Thêm một hàng nữa có mã `X` ở mỗi bảng và dự đoán số dòng tăng.
5. Giải thích vì sao kết quả tăng là hệ quả của cardinality chứ không nhất thiết là lỗi SQL.

### Bài tập C — Kiểm tra NULL key

1. Chạy mô phỏng với điều kiện `=`.
2. Xác nhận hai hàng NULL được trả về riêng ở hai phía.
3. Chạy lại với `<=>` trong cả hai nhánh.
4. Thêm nhiều hàng NULL ở mỗi bảng và đếm số cặp.
5. Viết chính sách nghiệp vụ xác định khi nào NULL được phép khớp.

### Bài tập D — Đối soát nội dung

1. Giữ lại ID của hai nguồn trong kết quả.
2. Dùng `COUNT(DISTINCT a_id)` và `COUNT(DISTINCT b_id)` để kiểm tra mức bao phủ.
3. Lọc `LEFT_ONLY` và `RIGHT_ONLY` để tìm bản ghi thiếu.
4. Lọc `MATCHED` nhưng dùng NULL-safe comparison để tìm thuộc tính khác nhau.
5. Ghi lại số liệu và các duplicate cần xử lý.

### Bài tập E — Tối ưu truy vấn

1. Tạo index trên hai cột khóa nối.
2. Chạy `EXPLAIN` cho từng nhánh.
3. Thử khóa ghép `(tenant_id, external_code)`.
4. So sánh kế hoạch khi cột khóa có kiểu/collation tương thích và khi phải ép kiểu.
5. Đánh giá kết quả trên dữ liệu có phân bố duplicate gần thực tế.

Bạn hoàn thành bài khi có thể mô phỏng đầy đủ ba nhóm hàng của FULL OUTER JOIN, dự báo số cặp do duplicate key, xác định semantics của NULL, kiểm tra mức bao phủ hai nguồn và giải thích vì sao `UNION ALL` phù hợp hơn `UNION` trong phép mô phỏng này.

## 20. Nguyên tắc cần ghi nhớ

- MySQL không có cú pháp `FULL OUTER JOIN` trực tiếp; mô phỏng bằng `LEFT JOIN` cộng phần anti-join của phía phải.
- Dùng `UNION ALL` để giữ đầy đủ các cặp và số lần xuất hiện của dữ liệu.
- Dùng primary key không NULL ở phía được LEFT JOIN để nhận diện hàng không khớp.
- Với khóa trùng, `m` hàng ở A và `n` hàng ở B tạo `m × n` cặp khớp cho khóa đó.
- Phân biệt duplicate ở nguồn với nhiều cặp ghép hợp lệ do quan hệ nhiều-nhiều.
- Kiểm tra duplicate và cardinality trước khi tổng hợp hoặc đối soát.
- `=` không ghép hai NULL; `<=>` ghép NULL với NULL và có thể làm tăng tích số hàng NULL.
- Không dùng `DISTINCT` để che lỗi khóa hoặc cardinality chưa được hiểu.
- Đặt điều kiện khớp trong `ON`; bộ lọc trong `WHERE` có thể loại các hàng ngoài của OUTER JOIN.
- Kiểm tra đầy đủ khóa ghép, kiểu dữ liệu, charset/collation và index bằng `EXPLAIN`.
- Đối soát bằng ID nguồn, `row_type`, số hàng distinct và kiểm tra nội dung của các cặp MATCHED.

Khi mô phỏng FULL OUTER JOIN đúng cách và kiểm chứng duplicate có hệ thống, bạn có thể đối soát hai nguồn mà không làm mất bản ghi lệch hoặc âm thầm nhân số liệu. Kết quả có thể giải thích được ở cấp từng hàng, từng cặp khớp và từng nhóm dữ liệu trùng.

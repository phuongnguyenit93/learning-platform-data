# Thứ tự nhánh, ELSE và kết quả khi không có nhánh phù hợp trong SQL

Trong SQL, **`CASE`** cho phép một biểu thức trả về **những giá trị khác nhau tùy điều kiện**. Bạn có thể dùng `CASE` để xếp loại điểm, hiển thị tên trạng thái, tính ưu đãi, gom dữ liệu theo nhóm, đặt thứ tự ưu tiên hoặc cập nhật giá trị theo quy tắc nghiệp vụ.

Điều làm `CASE` dễ gây nhầm lẫn không phải cú pháp `WHEN ... THEN`, mà là ba quy tắc:

1. **Các nhánh được xét theo thứ tự từ trên xuống.**
2. **Nhánh phù hợp đầu tiên quyết định kết quả; các nhánh phù hợp nằm sau không thay thế kết quả đó.**
3. **Nếu không có nhánh nào phù hợp, `ELSE` quyết định kết quả. Không có `ELSE` thì kết quả là `NULL`.**

Bài học thuộc chương **Rẽ nhánh trong SQL** của module Database SQL. Các ví dụ chạy với **PostgreSQL**, cùng các ghi chú về cách áp dụng trên MySQL, SQL Server, Oracle Database và SQLite.

## 1. CASE là biểu thức chọn giá trị, không phải câu lệnh điều khiển mọi dòng SQL

Mẫu thường gặp:

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    WHEN condition_3 THEN result_3
    ELSE fallback_result
END
```

Đây là **biểu thức**: nó tạo ra một giá trị. Vì vậy, nó có thể xuất hiện trong `SELECT`, `ORDER BY`, `GROUP BY`, `UPDATE ... SET` hoặc các biểu thức hợp lệ khác.

Ví dụ tự chứa, không cần bảng:

```sql
SELECT
    CASE
        WHEN 85 >= 90 THEN 'Xuất sắc'
        WHEN 85 >= 80 THEN 'Giỏi'
        WHEN 85 >= 65 THEN 'Đạt'
        ELSE 'Cần cải thiện'
    END AS classification;
```

Kết quả là `Giỏi` vì:

- `85 >= 90` là **FALSE**.
- `85 >= 80` là **TRUE**, nên chọn `'Giỏi'`.
- Không cần chọn tiếp `'Đạt'`, dù `85 >= 65` cũng đúng.

Lưu ý rằng `CASE` **không có `END IF`** trong cú pháp biểu thức SQL này. Một biểu thức `CASE` đóng bằng `END` và nếu là câu truy vấn SQL hoàn chỉnh, dấu `;` thường nằm **sau** câu truy vấn.

```text
CASE
  WHEN điều kiện A?
      TRUE  → giá trị A → END
      khác TRUE
  WHEN điều kiện B?
      TRUE  → giá trị B → END
      khác TRUE
  WHEN điều kiện C?
      TRUE  → giá trị C → END
      khác TRUE
  ELSE giá trị dự phòng → END
```

**Điều kiện “phù hợp” trong dạng `CASE WHEN` là điều kiện cho kết quả `TRUE`.** `FALSE` và `UNKNOWN` đều không chọn nhánh đó.

## 2. Thứ tự nhánh: nhánh đúng đầu tiên thắng

### 2.1. Khi các điều kiện chồng lấp nhau

Xét thang điểm:

- Từ 90 trở lên: `Xuất sắc`.
- Từ 80 trở lên: `Giỏi`.
- Từ 65 trở lên: `Đạt`.
- Dưới 65: `Chưa đạt`.

Một cách viết đúng:

```sql
SELECT
    score,
    CASE
        WHEN score >= 90 THEN 'Xuất sắc'
        WHEN score >= 80 THEN 'Giỏi'
        WHEN score >= 65 THEN 'Đạt'
        ELSE 'Chưa đạt'
    END AS grade
FROM (
    VALUES (95), (85), (70), (55)
) AS sample_scores(score);
```

Kết quả:

| score | grade |
|---:|---|
| 95 | Xuất sắc |
| 85 | Giỏi |
| 70 | Đạt |
| 55 | Chưa đạt |

Mỗi điểm cao cũng thỏa một hoặc nhiều điều kiện thấp hơn. Thứ tự **từ ngưỡng cao xuống thấp** giúp mỗi hàng được gán vào lớp đúng.

### 2.2. Đổi thứ tự có thể làm kết quả sai

```sql
SELECT
    score,
    CASE
        WHEN score >= 65 THEN 'Đạt'
        WHEN score >= 80 THEN 'Giỏi'
        WHEN score >= 90 THEN 'Xuất sắc'
        ELSE 'Chưa đạt'
    END AS grade
FROM (
    VALUES (95), (85), (70), (55)
) AS sample_scores(score);
```

Ở ví dụ này, cả 95, 85 và 70 đều nhận `Đạt`. Ngay khi điều kiện `score >= 65` đúng, nhánh đó đã được chọn. Hai nhánh sau **không có cơ hội trở thành kết quả** đối với bất kỳ điểm nào ≥ 65.

Đây là lỗi **thứ tự nhánh**, không phải lỗi cú pháp. DBMS vẫn chạy truy vấn và trả dữ liệu, nhưng kết quả khác yêu cầu nghiệp vụ.

### 2.3. Hai cách làm rõ điều kiện

**Cách 1 — Sắp xếp điều kiện từ riêng đến chung:**

```sql
CASE
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 80 THEN 'Giỏi'
    WHEN score >= 65 THEN 'Đạt'
    ELSE 'Chưa đạt'
END
```

**Cách 2 — Viết các khoảng không chồng nhau:**

```sql
CASE
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 80 AND score < 90 THEN 'Giỏi'
    WHEN score >= 65 AND score < 80 THEN 'Đạt'
    WHEN score < 65 THEN 'Chưa đạt'
    ELSE 'Chưa có điểm'
END
```

Cách 2 dài hơn nhưng minh họa rõ biên của mỗi khoảng. Đặc biệt, nhánh `ELSE 'Chưa có điểm'` còn dành cho `score IS NULL` trong trường hợp này.

Với các điều kiện **không chồng lấp** và cùng bao phủ miền dữ liệu, việc đổi thứ tự có thể không thay đổi kết quả. Tuy nhiên, thứ tự vẫn là một phần của ngữ nghĩa `CASE`; nên trình bày theo thứ tự ưu tiên mà người đọc dễ xác nhận.

## 3. ELSE hoạt động khi không nhánh nào được chọn

`ELSE` là **giá trị dự phòng** khi tất cả các điều kiện `WHEN` đều không `TRUE`.

```sql
SELECT
    CASE
        WHEN 42 >= 90 THEN 'Xuất sắc'
        WHEN 42 >= 65 THEN 'Đạt'
        ELSE 'Chưa đạt'
    END AS result;
```

Kết quả là `Chưa đạt`.

Nếu bỏ `ELSE`:

```sql
SELECT
    CASE
        WHEN 42 >= 90 THEN 'Xuất sắc'
        WHEN 42 >= 65 THEN 'Đạt'
    END AS result;
```

Kết quả là **`NULL`**, chứ không phải chuỗi rỗng, số 0 hoặc giá trị của nhánh cuối.

Về ý nghĩa, hai biểu thức dưới đây tương đương:

```sql
CASE
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 65 THEN 'Đạt'
END
```

```sql
CASE
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 65 THEN 'Đạt'
    ELSE NULL
END
```

### 3.1. Chọn ELSE theo ý nghĩa nghiệp vụ

Có ba tình huống khác nhau:

| Nhu cầu | `ELSE` hợp lý | Ý nghĩa |
|---|---|---|
| Mọi điểm dưới 65 đều là chưa đạt và cột điểm không NULL | `ELSE 'Chưa đạt'` | Phân loại đầy đủ miền điểm hợp lệ |
| Điểm có thể chưa được nhập | `WHEN score IS NULL THEN 'Chưa có điểm'` và `ELSE 'Chưa đạt'` | Phân biệt thiếu dữ liệu với điểm thấp |
| Không muốn gán kết quả khi không có quy tắc phù hợp | Bỏ `ELSE` hoặc `ELSE NULL` | Giữ trạng thái chưa xác định |

**Không có một giá trị `ELSE` “đúng” cho mọi bài toán.** Điều quan trọng là không đánh đồng “không có dữ liệu”, “không có trạng thái hợp lệ” và “rơi vào nhóm thấp nhất”.

### 3.2. ELSE không phải một điều kiện WHEN mới

`ELSE` không nhận điều kiện:

```sql
-- Không phải cú pháp CASE hợp lệ.
CASE
    WHEN score >= 65 THEN 'Đạt'
    ELSE score < 65 THEN 'Chưa đạt'
END
```

Viết đúng:

```sql
CASE
    WHEN score >= 65 THEN 'Đạt'
    ELSE 'Chưa đạt'
END
```

Nếu cần phân biệt trường hợp `score IS NULL`, thêm một `WHEN` trước `ELSE` thay vì viết điều kiện sau `ELSE`.

## 4. Không có ELSE: NULL xuất hiện thế nào?

`NULL` trong SQL thường thể hiện **không có giá trị xác định**, không phải chuỗi `'NULL'`.

Ví dụ:

```sql
SELECT
    CASE
        WHEN 10 < 0 THEN 'Số âm'
    END AS classification;
```

Không có điều kiện nào đúng, không có `ELSE` nên `classification` là `NULL`.

Để quan sát, trong PostgreSQL có thể dùng `IS NULL`:

```sql
SELECT
    (
        CASE
            WHEN 10 < 0 THEN 'Số âm'
        END
    ) IS NULL AS no_branch_matched;
```

Kết quả là `TRUE`.

Nếu biểu thức `CASE` nằm trong phép nối chuỗi hoặc tính toán, `NULL` có thể lan truyền:

```sql
SELECT
    'Kết quả: ' ||
    CASE
        WHEN 10 < 0 THEN 'Số âm'
    END AS display_text;
```

Trong PostgreSQL, kết quả `display_text` là `NULL`, vì `'Kết quả: ' || NULL` tạo `NULL`.

Một cách cung cấp nhãn dự phòng tại chỗ:

```sql
SELECT
    'Kết quả: ' ||
    CASE
        WHEN 10 < 0 THEN 'Số âm'
        ELSE 'Không phải số âm'
    END AS display_text;
```

Kết quả là `Kết quả: Không phải số âm`.

Bạn cũng có thể dùng `COALESCE` nếu muốn xử lý một biểu thức `CASE` có thể trả về `NULL`:

```sql
SELECT
    COALESCE(
        CASE
            WHEN 10 < 0 THEN 'Số âm'
        END,
        'Chưa có nhãn'
    ) AS classification;
```

Nhưng hãy cân nhắc: thêm `ELSE` trực tiếp trong `CASE` thường giúp mô tả quy tắc rõ hơn nếu giá trị dự phòng thuộc chính logic phân loại.

## 5. NULL và UNKNOWN trong điều kiện WHEN

Trong SQL, điều kiện có thể mang **ba giá trị logic**:

- `TRUE`: chọn nhánh.
- `FALSE`: bỏ qua nhánh.
- `UNKNOWN`: cũng bỏ qua nhánh.

`UNKNOWN` thường xuất hiện khi so sánh thông thường có `NULL`.

### 5.1. Điểm NULL không thỏa các phép so sánh

```sql
SELECT
    score,
    CASE
        WHEN score >= 80 THEN 'Cao'
        WHEN score < 80 THEN 'Thấp'
        ELSE 'Chưa xác định'
    END AS result
FROM (
    VALUES (90), (60), (NULL::INTEGER)
) AS t(score);
```

Kết quả:

| score | result |
|---:|---|
| 90 | Cao |
| 60 | Thấp |
| `NULL` | Chưa xác định |

Với hàng `NULL`, cả `score >= 80` và `score < 80` đều cho `UNKNOWN`; hai nhánh đó không được chọn.

**Đừng suy luận rằng vì giá trị không thuộc nhóm “cao” nên nó đương nhiên thuộc nhóm “thấp”.** Trong logic ba giá trị của SQL, dữ liệu chưa biết là trường hợp riêng.

### 5.2. Dùng IS NULL để có nhánh thiếu dữ liệu

```sql
CASE
    WHEN score IS NULL THEN 'Chưa có điểm'
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 80 THEN 'Giỏi'
    WHEN score >= 65 THEN 'Đạt'
    ELSE 'Chưa đạt'
END
```

Dù có thể đặt `WHEN score IS NULL` sau các phép so sánh nếu không có điều kiện chồng lấp, đặt ở đầu thường giúp độc giả nhận diện rõ **quy tắc xử lý dữ liệu thiếu**.

Không viết:

```sql
-- Không xác định được NULL bằng phép so sánh thông thường.
WHEN score = NULL THEN 'Chưa có điểm'
```

Viết:

```sql
WHEN score IS NULL THEN 'Chưa có điểm'
```

`NULL` không được so sánh như một giá trị bằng toán tử `=` thông thường.

## 6. Hai dạng CASE: searched CASE và simple CASE

SQL có hai dạng biểu thức `CASE` được dùng nhiều nhất.

### 6.1. Searched CASE — mỗi WHEN là một điều kiện

```sql
CASE
    WHEN score IS NULL THEN 'Chưa có điểm'
    WHEN score >= 90 THEN 'Xuất sắc'
    WHEN score >= 65 THEN 'Đạt'
    ELSE 'Chưa đạt'
END
```

Dạng này phù hợp khi nhánh chứa:

- Toán tử so sánh như `>`, `>=`, `<`, `<=`.
- Nhiều điều kiện với `AND`/`OR`.
- Kiểm tra `IS NULL` hoặc `IS NOT NULL`.
- `EXISTS`, `IN`, `BETWEEN`, `LIKE` và các điều kiện logic khác.

### 6.2. Simple CASE — so một biểu thức với các giá trị WHEN

```sql
CASE status_code
    WHEN 'APPROVED' THEN 'Đã duyệt'
    WHEN 'PENDING' THEN 'Đang chờ'
    WHEN 'REJECTED' THEN 'Đã từ chối'
    ELSE 'Chưa xác định'
END
```

Dạng này phù hợp khi so **cùng một biểu thức** `status_code` với nhiều giá trị cụ thể theo phép so sánh bằng.

Có thể hình dung:

```sql
CASE
    WHEN status_code = 'APPROVED' THEN 'Đã duyệt'
    WHEN status_code = 'PENDING' THEN 'Đang chờ'
    WHEN status_code = 'REJECTED' THEN 'Đã từ chối'
    ELSE 'Chưa xác định'
END
```

Hai biểu thức trên tương ứng về ý định khi các giá trị bình thường được so sánh bằng.

### 6.3. Simple CASE và NULL: điểm dễ nhầm

Thử:

```sql
SELECT
    CASE CAST(NULL AS VARCHAR(20))
        WHEN NULL THEN 'Khớp NULL'
        ELSE 'Không khớp'
    END AS simple_case_result;
```

Kết quả là `Không khớp` trong PostgreSQL, bởi vì phép so sánh `NULL = NULL` không cho `TRUE`.

Muốn kiểm tra `NULL`, dùng **searched CASE**:

```sql
SELECT
    CASE
        WHEN CAST(NULL AS VARCHAR(20)) IS NULL
            THEN 'Khớp NULL'
        ELSE 'Không khớp'
    END AS searched_case_result;
```

Kết quả là `Khớp NULL`.

Dạng simple `CASE expr WHEN value` không phải cú pháp để kiểm tra `NULL` bằng phép bằng an toàn. Khi yêu cầu có điều kiện thiếu dữ liệu, chọn searched `CASE` với `IS NULL`.

## 7. Chuẩn bị bảng thực hành

Tạo bảng chứa điểm đánh giá, trạng thái và số tiền. Ví dụ sau dành cho PostgreSQL, chỉ nên chạy trong database thực hành và thực hiện `CREATE TABLE`/`INSERT` một lần.

```sql
CREATE TABLE lesson152_applications (
    application_id INTEGER PRIMARY KEY,
    applicant_name VARCHAR(100) NOT NULL,
    score INTEGER,
    status_code VARCHAR(20),
    is_verified BOOLEAN,
    order_amount NUMERIC(12, 2),
    CONSTRAINT lesson152_score_range
        CHECK (score BETWEEN 0 AND 100)
);

INSERT INTO lesson152_applications (
    application_id,
    applicant_name,
    score,
    status_code,
    is_verified,
    order_amount
)
VALUES
    (1, 'An',   95, 'APPROVED', TRUE,  300000.00),
    (2, 'Bình', 85, 'APPROVED', FALSE,      0.00),
    (3, 'Chi',  75, 'PENDING',  TRUE,  120000.00),
    (4, 'Dũng', 60, 'REJECTED', FALSE,  50000.00),
    (5, 'Hà', NULL, 'PENDING',  NULL,       NULL),
    (6, 'Lan',  40, 'OTHER',    TRUE,  200000.00),
    (7, 'Minh', 90, NULL,       TRUE,  180000.00);
```

Bảng mẫu cố ý có:

- Điểm ở nhiều ngưỡng: 95, 90, 85, 75, 60, 40.
- Điểm thiếu: `score IS NULL`.
- Trạng thái được biết và không biết: `APPROVED`, `PENDING`, `REJECTED`, `OTHER`, `NULL`.
- Giá trị `order_amount = 0` và `order_amount IS NULL` là **hai tình huống khác nhau**.

Ràng buộc `CHECK (score BETWEEN 0 AND 100)` loại các điểm ngoài phạm vi nhưng, riêng nó, vẫn có thể chấp nhận `score NULL` do logic ba giá trị của `CHECK`. Đây là chủ đích của dữ liệu thực hành.

## 8. Thực hành thứ tự nhánh theo điểm

### 8.1. Xếp loại đầy đủ

```sql
SELECT
    application_id,
    applicant_name,
    score,
    CASE
        WHEN score IS NULL THEN 'Chưa có điểm'
        WHEN score >= 90 THEN 'Xuất sắc'
        WHEN score >= 80 THEN 'Giỏi'
        WHEN score >= 65 THEN 'Đạt'
        ELSE 'Chưa đạt'
    END AS grade
FROM lesson152_applications
ORDER BY application_id;
```

Kết quả:

| ID | Tên | Điểm | Xếp loại |
|---:|---|---:|---|
| 1 | An | 95 | Xuất sắc |
| 2 | Bình | 85 | Giỏi |
| 3 | Chi | 75 | Đạt |
| 4 | Dũng | 60 | Chưa đạt |
| 5 | Hà | `NULL` | Chưa có điểm |
| 6 | Lan | 40 | Chưa đạt |
| 7 | Minh | 90 | Xuất sắc |

Lưu ý **90 thuộc nhóm `Xuất sắc`** vì toán tử dùng là `>= 90`. Khi viết quy tắc theo ngưỡng, cần kiểm tra cả **giá trị nằm đúng ranh giới**.

### 8.2. Nếu bỏ ELSE

```sql
SELECT
    application_id,
    applicant_name,
    CASE
        WHEN score >= 90 THEN 'Xuất sắc'
        WHEN score >= 80 THEN 'Giỏi'
        WHEN score >= 65 THEN 'Đạt'
    END AS grade_without_else
FROM lesson152_applications
ORDER BY application_id;
```

Các hàng có điểm 60, 40 và `NULL` đều nhận **`NULL`** ở cột `grade_without_else`. Không phải vì cả ba có chung trạng thái nghiệp vụ, mà vì **không nhánh nào trả giá trị**.

Nếu sau đó dùng cột này để tổng hợp hoặc lọc, `NULL` có thể ảnh hưởng kết quả. Vì thế khi quy tắc nghiệp vụ muốn phân nhóm đầy đủ, nên khai báo `ELSE` rõ ràng hoặc có nhánh dành cho dữ liệu thiếu.

## 9. Thứ tự nhánh còn quyết định mức ưu tiên nghiệp vụ

Nhiều bài toán không chỉ phân loại bằng một cột, mà áp dụng **quy tắc ưu tiên**.

Giả sử ưu tiên xử lý như sau:

1. Đơn có `status_code = 'REJECTED'`: `Không xử lý`.
2. Đơn có `score >= 90`: `Ưu tiên rất cao`.
3. Đơn đã duyệt: `Ưu tiên chuẩn`.
4. Các đơn khác: `Chờ xem xét`.

```sql
SELECT
    application_id,
    applicant_name,
    status_code,
    score,
    CASE
        WHEN status_code = 'REJECTED'
            THEN 'Không xử lý'
        WHEN score >= 90
            THEN 'Ưu tiên rất cao'
        WHEN status_code = 'APPROVED'
            THEN 'Ưu tiên chuẩn'
        ELSE 'Chờ xem xét'
    END AS handling_priority
FROM lesson152_applications
ORDER BY application_id;
```

Nếu một hồ sơ vừa có `score >= 90` vừa có `status_code = 'APPROVED'`, nhánh điểm cao **nằm trước** nên quyết định giá trị.

Ví dụ khác: giả sử một hồ sơ có điểm 95 nhưng trạng thái `REJECTED`. Với thứ tự trên, nó sẽ là `Không xử lý`. Nếu chuyển nhánh `score >= 90` lên đầu, hồ sơ đó sẽ bị xếp `Ưu tiên rất cao`, trái quy tắc “đã từ chối thì không xử lý”.

**Với các điều kiện chồng lấp, thứ tự `WHEN` chính là thứ tự ưu tiên của chính sách.** Hãy ghi rõ điều kiện chặn hoặc ngoại lệ quan trọng trước các điều kiện chung.

## 10. CASE trong SELECT, ORDER BY và GROUP BY

### 10.1. SELECT: chuyển mã thành nhãn hiển thị

```sql
SELECT
    application_id,
    applicant_name,
    status_code,
    CASE status_code
        WHEN 'APPROVED' THEN 'Đã duyệt'
        WHEN 'PENDING' THEN 'Đang chờ'
        WHEN 'REJECTED' THEN 'Đã từ chối'
        ELSE 'Khác hoặc chưa có trạng thái'
    END AS status_label
FROM lesson152_applications
ORDER BY application_id;
```

`OTHER` và `NULL` đều đi vào `ELSE` trong ví dụ. Nếu nghiệp vụ cần phân biệt chúng, dùng searched `CASE`:

```sql
CASE
    WHEN status_code IS NULL THEN 'Chưa có trạng thái'
    WHEN status_code = 'APPROVED' THEN 'Đã duyệt'
    WHEN status_code = 'PENDING' THEN 'Đang chờ'
    WHEN status_code = 'REJECTED' THEN 'Đã từ chối'
    ELSE 'Trạng thái không nhận diện'
END
```

### 10.2. ORDER BY: sắp xếp theo mức ưu tiên

Giả sử muốn đưa `APPROVED` lên trước, rồi `PENDING`, rồi các trạng thái còn lại:

```sql
SELECT
    application_id,
    applicant_name,
    status_code,
    score
FROM lesson152_applications
ORDER BY
    CASE
        WHEN status_code = 'APPROVED' THEN 1
        WHEN status_code = 'PENDING' THEN 2
        ELSE 3
    END,
    score DESC NULLS LAST,
    application_id;
```

Biểu thức `CASE` ở đây trả **khóa sắp xếp số**, không phải nhãn hiển thị. Nhánh `ELSE 3` bảo đảm các trạng thái khác hoặc `NULL` vẫn có nhóm thứ tự rõ ràng.

`NULLS LAST` là cú pháp PostgreSQL (và một số DBMS khác), không hỗ trợ giống nhau trên mọi hệ quản trị. Nếu cần SQL đa hệ, hãy điều chỉnh cách xử lý `NULL` trong `ORDER BY`.

### 10.3. GROUP BY: nhóm theo kết quả CASE

Ví dụ đếm số hồ sơ theo nhóm điểm:

```sql
WITH categorized AS (
    SELECT
        application_id,
        CASE
            WHEN score IS NULL THEN 'Chưa có điểm'
            WHEN score >= 80 THEN 'Từ 80 trở lên'
            WHEN score >= 65 THEN 'Từ 65 đến dưới 80'
            ELSE 'Dưới 65'
        END AS score_group
    FROM lesson152_applications
)
SELECT
    score_group,
    COUNT(*) AS application_count
FROM categorized
GROUP BY score_group
ORDER BY score_group;
```

CTE `categorized` là một truy vấn trung gian trong **cùng câu SQL**, không tạo bảng tồn tại lâu dài. Việc tách như vậy giúp tránh lặp lại biểu thức `CASE` dài trong cả `SELECT` và `GROUP BY`.

**Chú ý:** Nếu bỏ `ELSE`, nhiều hàng không khớp điều kiện sẽ nhận `NULL`, và `GROUP BY` sẽ tạo một nhóm `NULL` thay vì nhóm mang nhãn rõ ràng. Điều đó không sai về cú pháp nhưng có thể không phù hợp cho báo cáo.

## 11. CASE trong thống kê và hàm tổng hợp

### 11.1. Đếm có điều kiện bằng SUM(CASE ...)

Một mẫu phổ biến:

```sql
SELECT
    COUNT(*) AS all_applications,
    SUM(
        CASE
            WHEN status_code = 'APPROVED' THEN 1
            ELSE 0
        END
    ) AS approved_count,
    SUM(
        CASE
            WHEN status_code = 'PENDING' THEN 1
            ELSE 0
        END
    ) AS pending_count
FROM lesson152_applications;
```

Với dữ liệu mẫu:

- `all_applications = 7`.
- `approved_count = 2`.
- `pending_count = 2`.

Ở đây, nhánh `ELSE 0` có vai trò **rất cụ thể**: mỗi dòng không thỏa điều kiện đóng góp 0 vào tổng.

Nếu bỏ `ELSE`:

```sql
SELECT
    SUM(
        CASE
            WHEN status_code = 'APPROVED' THEN 1
        END
    ) AS approved_count
FROM lesson152_applications;
```

Khi có ít nhất một hồ sơ đã duyệt, tổng vẫn là 2 vì `SUM` bỏ qua các giá trị `NULL`. **Nhưng nếu không có hồ sơ nào khớp**, kết quả có thể là `NULL` thay vì 0. Vì vậy, `ELSE 0` hoặc `COALESCE(SUM(...), 0)` thể hiện rõ ý định của báo cáo.

### 11.2. COUNT(CASE ...) và sự khác biệt của ELSE

`COUNT(expression)` đếm các kết quả **khác `NULL`**.

```sql
SELECT
    COUNT(
        CASE
            WHEN status_code = 'APPROVED' THEN 1
        END
    ) AS approved_count,
    COUNT(
        CASE
            WHEN status_code = 'APPROVED' THEN 1
            ELSE 0
        END
    ) AS count_every_row
FROM lesson152_applications;
```

Kết quả lần lượt là **2** và **7**:

- Biểu thức thứ nhất trả `1` cho 2 dòng đã duyệt và `NULL` cho những dòng còn lại, nên `COUNT` chỉ đếm 2.
- Biểu thức thứ hai trả `1` hoặc `0` cho mọi dòng; cả 1 và 0 đều **khác `NULL`**, nên `COUNT` đếm cả 7.

Đây là một lỗi thống kê rất phổ biến: **`ELSE 0` phù hợp khi dùng `SUM(CASE...)`, nhưng thường không phù hợp nếu muốn `COUNT(CASE...)` chỉ đếm nhánh đúng.**

PostgreSQL cũng cho phép:

```sql
SELECT
    COUNT(*) FILTER (
        WHERE status_code = 'APPROVED'
    ) AS approved_count
FROM lesson152_applications;
```

`FILTER` là một cách diễn đạt khác cho tổng hợp có điều kiện, nhưng cú pháp này không đồng nhất trên mọi DBMS. `CASE` vẫn hữu ích khi cần logic chọn giá trị phức tạp.

### 11.3. Tính trung bình có điều kiện

```sql
SELECT
    AVG(
        CASE
            WHEN status_code = 'APPROVED' THEN score
        END
    ) AS approved_average_score
FROM lesson152_applications;
```

Biểu thức `CASE` trả `score` cho hồ sơ đã duyệt, còn lại trả `NULL`. `AVG` bỏ qua `NULL`, nên chỉ lấy trung bình điểm của các hồ sơ đã duyệt.

Ngược lại:

```sql
SELECT
    AVG(
        CASE
            WHEN status_code = 'APPROVED' THEN score
            ELSE 0
        END
    ) AS different_average
FROM lesson152_applications;
```

Sẽ coi **mỗi dòng không được duyệt như điểm 0**, làm thay đổi mẫu số và ý nghĩa thống kê. Không thêm `ELSE 0` một cách máy móc trong mọi phép tổng hợp.

## 12. CASE trong WHERE: lọc bằng kết quả rẽ nhánh

`CASE` cũng có thể tạo điều kiện cho `WHERE`. Giả sử quy tắc chọn hồ sơ là:

- Nếu đã duyệt, chỉ lấy khi điểm ≥ 80.
- Nếu đang chờ, chỉ lấy khi đã xác minh.
- Những trạng thái khác không lấy.

Trong PostgreSQL:

```sql
SELECT
    application_id,
    applicant_name,
    status_code,
    score,
    is_verified
FROM lesson152_applications
WHERE CASE
    WHEN status_code = 'APPROVED'
        THEN score >= 80
    WHEN status_code = 'PENDING'
        THEN is_verified IS TRUE
    ELSE FALSE
END
ORDER BY application_id;
```

Biểu thức `CASE` ở đây trả giá trị logic. Khi `status_code = 'APPROVED'` nhưng `score IS NULL`, kết quả nhánh có thể là `UNKNOWN`; `WHERE` chỉ giữ những hàng có kết quả `TRUE`.

Tuy nhiên, nếu mục đích đơn thuần là lọc dữ liệu, cách viết điều kiện trực tiếp thường dễ đọc hơn:

```sql
SELECT
    application_id,
    applicant_name
FROM lesson152_applications
WHERE (
        status_code = 'APPROVED'
        AND score >= 80
      )
   OR (
        status_code = 'PENDING'
        AND is_verified IS TRUE
      )
ORDER BY application_id;
```

Trên dữ liệu mẫu, cả hai cách chọn **An, Bình và Chi**. Khi `CASE` chỉ làm nhiệm vụ viết lại các phép `AND`/`OR` đơn giản, hãy cân nhắc cách không dùng `CASE`; nó có thể diễn đạt điều kiện và hỗ trợ tối ưu hóa rõ hơn.

## 13. CASE trong UPDATE: chỉ đổi những hàng đúng điều kiện

`CASE` có thể dùng ở vế phải của `SET` để chọn giá trị mới dựa trên dữ liệu hiện tại. Ví dụ cập nhật trạng thái thử nghiệm theo điểm:

```sql
BEGIN;

UPDATE lesson152_applications
SET status_code = CASE
    WHEN score IS NULL THEN 'PENDING'
    WHEN score >= 80 THEN 'APPROVED'
    ELSE 'REJECTED'
END
WHERE application_id BETWEEN 1 AND 7;

SELECT
    application_id,
    applicant_name,
    score,
    status_code
FROM lesson152_applications
ORDER BY application_id;

ROLLBACK;
```

Đoạn này minh họa trong giao dịch PostgreSQL rồi **`ROLLBACK`** để không lưu kết quả cập nhật khi thực hành.

Chú ý:

- `CASE` chọn **giá trị sẽ ghi**.
- `WHERE` chọn **những hàng được phép cập nhật**.
- Nếu bỏ `WHERE`, `UPDATE` có thể tác động tới **toàn bộ bảng**.
- Nếu bỏ `ELSE` mà không có điều kiện nào khớp, biểu thức `CASE` có thể trả `NULL`. Nếu cột đích `NOT NULL`, câu lệnh có thể thất bại; nếu cột cho phép `NULL`, dữ liệu trước đó có thể bị thay bằng `NULL` ngoài ý muốn.

Khi cần **giữ nguyên giá trị cũ** nếu không điều kiện nào phù hợp, dùng `ELSE` để trả về chính cột đó:

```sql
UPDATE lesson152_applications
SET status_code = CASE
    WHEN score >= 90 THEN 'PRIORITY'
    ELSE status_code
END
WHERE application_id = 1;
```

Đoạn cuối thực sự cập nhật một hàng nếu chạy độc lập. Hãy dùng trong database thực hành hoặc đặt trong giao dịch và rollback nếu chỉ muốn quan sát. Không xem việc bỏ `ELSE` là cách tương đương với “giữ nguyên”.

## 14. Kiểu dữ liệu của các kết quả THEN và ELSE

`CASE` trả về **một giá trị có một kiểu dữ liệu SQL** theo quy tắc suy luận kiểu của DBMS. Vì thế các kết quả ở `THEN` và `ELSE` cần **tương thích hoặc chuyển đổi được** sang kiểu kết quả chung.

Ví dụ PostgreSQL:

```sql
SELECT
    CASE
        WHEN TRUE THEN 10
        ELSE 20
    END AS numeric_result,
    CASE
        WHEN FALSE THEN 'Đạt'
        ELSE 'Chưa đạt'
    END AS text_result;
```

Các nhánh thứ nhất đều là số, nhánh thứ hai đều là văn bản.

### 14.1. Trộn số và chuỗi có thể gây lỗi

```sql
-- Trong PostgreSQL, không phải một biểu thức hợp lệ
-- nếu nhánh văn bản không thể chuyển thành kiểu số được chọn.
SELECT
    CASE
        WHEN TRUE THEN 100
        ELSE 'Chưa có số'
    END AS mixed_result;
```

Ngay cả khi nhánh `ELSE` không được chọn ở thời gian chạy, DBMS vẫn cần xác định **kiểu kết quả** của biểu thức. Trong PostgreSQL, việc cố chuyển `'Chưa có số'` sang số có thể gây lỗi.

Nếu mục tiêu là **chuỗi hiển thị**, chủ động chuyển số sang văn bản:

```sql
SELECT
    CASE
        WHEN TRUE THEN CAST(100 AS TEXT)
        ELSE 'Chưa có số'
    END AS display_result;
```

Nếu mục tiêu là **kết quả số**, giữ nhánh còn lại là số hoặc `NULL` có kiểu phù hợp:

```sql
SELECT
    CASE
        WHEN FALSE THEN 100::NUMERIC
        ELSE NULL::NUMERIC
    END AS numeric_or_null;
```

Khi cần tính toán tiếp, tốt hơn nên giữ cột kết quả dạng số, không chuyển cả cột sang chuỗi chỉ để hiển thị thông báo. Phần trình bày ở ứng dụng có thể tự định dạng giá trị `NULL`.

### 14.2. ELSE NULL vẫn phải phù hợp với ngữ cảnh kiểu

Ví dụ:

```sql
SELECT
    CASE
        WHEN score >= 65 THEN score
        ELSE NULL
    END AS qualifying_score
FROM lesson152_applications;
```

Trong PostgreSQL, vì nhánh `THEN` trả `score INTEGER` nên nhánh `ELSE NULL` được xử lý theo kiểu thích hợp. Nếu biểu thức chỉ chứa các nhánh `NULL` hoặc xuất hiện trong một ngữ cảnh cần kiểu cụ thể, có thể dùng `CAST(NULL AS INTEGER)` hoặc `NULL::INTEGER` để thể hiện rõ ý định.

## 15. CASE có phải luôn chỉ đánh giá nhánh được chọn?

Về **kết quả logic**, searched `CASE` chọn nhánh `WHEN` đầu tiên có điều kiện `TRUE` và trả biểu thức `THEN` tương ứng. Đây thường được mô tả như hành vi “short-circuit”.

Tuy nhiên, **không nên dùng `CASE` như một cam kết rằng DBMS sẽ không bao giờ tính bất kỳ phần nào của nhánh không được chọn**. Bộ tối ưu hóa có thể:

- Tính trước các biểu thức hằng trong giai đoạn lập kế hoạch.
- Xử lý biểu thức tổng hợp trước biểu thức `CASE` bao ngoài.
- Áp dụng những phép biến đổi biểu thức được phép theo ngữ nghĩa SQL và quy tắc riêng của DBMS.

Ví dụ việc tránh chia cho 0 ở mức hàng trong PostgreSQL:

```sql
SELECT
    x,
    CASE
        WHEN x = 0 THEN NULL
        ELSE 100.0 / x
    END AS ratio
FROM (
    VALUES (0), (2), (5)
) AS sample(x);
```

Với `x = 0`, kết quả `ratio` là `NULL`; các giá trị còn lại cho 50 và 20.

Trong nhiều tình huống xử lý dữ liệu, có thể diễn đạt ngắn gọn hơn bằng `NULLIF`:

```sql
SELECT
    x,
    100.0 / NULLIF(x, 0) AS ratio
FROM (
    VALUES (0), (2), (5)
) AS sample(x);
```

`NULLIF(x, 0)` biến mẫu số bằng 0 thành `NULL`, tránh phép chia số thông thường cho 0.

**Lưu ý thực tế:** `CASE` không phải công cụ đáng tin cậy để kiểm soát **tác dụng phụ** của các hàm hoặc thứ tự thực thi chi tiết của mọi biểu thức trong mọi hệ quản trị. Nếu xử lý có thể phát sinh lỗi hoặc cần tuần tự hóa các bước, hãy dùng điều kiện dữ liệu rõ ràng, chuyển kiểu có kiểm soát và cơ chế thích hợp của DBMS. Không dựa vào việc một nhánh “không được chọn” để giấu biểu thức sai kiểu hoặc biểu thức hằng lỗi.

## 16. CASE lồng nhau và cách viết dễ đọc

Bạn có thể đặt một biểu thức `CASE` bên trong `THEN` hoặc `ELSE` của `CASE` khác:

```sql
SELECT
    application_id,
    applicant_name,
    CASE
        WHEN status_code = 'APPROVED' THEN
            CASE
                WHEN score >= 90 THEN 'Duyệt - ưu tiên cao'
                ELSE 'Duyệt - thông thường'
            END
        WHEN status_code = 'PENDING' THEN 'Đang chờ'
        ELSE 'Khác'
    END AS handling_group
FROM lesson152_applications
ORDER BY application_id;
```

Dạng lồng nhau hợp lệ nhưng khó đọc nếu có nhiều tầng. Nếu quy tắc có thể diễn đạt bằng **các nhánh searched CASE theo thứ tự ưu tiên**, thường có thể viết phẳng:

```sql
CASE
    WHEN status_code = 'APPROVED' AND score >= 90
        THEN 'Duyệt - ưu tiên cao'
    WHEN status_code = 'APPROVED'
        THEN 'Duyệt - thông thường'
    WHEN status_code = 'PENDING'
        THEN 'Đang chờ'
    ELSE 'Khác'
END
```

Ở đây nhánh `APPROVED` + điểm cao phải đứng **trước** nhánh `APPROVED` chung. Nếu đảo, hồ sơ điểm cao sẽ luôn vào nhánh thông thường.

Nên ưu tiên:

1. Nhánh ngoại lệ hoặc điều kiện cụ thể trước.
2. Nhánh tổng quát sau.
3. `ELSE` cuối cùng với ý nghĩa rõ ràng.
4. Tên bí danh thể hiện ý nghĩa kết quả, ví dụ `handling_group` hoặc `grade`.
5. Chú thích giải thích **quy tắc nghiệp vụ** thay vì chỉ mô tả lại cú pháp.

Nếu logic rẽ nhánh dài, thay đổi thường xuyên hoặc cần tái sử dụng ở nhiều dịch vụ, có thể cân nhắc bảng quy tắc (lookup/rules table), CTE hoặc lớp nghiệp vụ phù hợp, thay vì lặp lại một biểu thức `CASE` rất dài ở nhiều nơi.

## 17. Phân biệt CASE, COALESCE và NULLIF

Ba cấu trúc đều có thể liên quan đến `NULL`, nhưng phục vụ những mục đích khác nhau:

| Biểu thức | Công dụng | Ví dụ |
|---|---|---|
| `CASE WHEN ... THEN ... ELSE ... END` | Chọn giá trị theo **điều kiện tùy ý** và thứ tự ưu tiên | Xếp loại theo điểm và trạng thái |
| `COALESCE(a, b, c)` | Chọn **giá trị đầu tiên không NULL** | Ưu tiên email công việc, email cá nhân, nhãn mặc định |
| `NULLIF(a, b)` | Trả `NULL` nếu hai biểu thức bằng nhau; nếu không trả `a` | Đổi mẫu số bằng 0 thành `NULL` trước khi chia |

Ví dụ muốn hiển thị tên gọi thân mật nếu có, nếu thiếu thì dùng tên đầy đủ:

```sql
SELECT COALESCE(nickname, full_name) AS display_name
FROM members;
```

Đây là trường hợp `COALESCE` ngắn gọn hơn `CASE` (giả định bảng `members` tồn tại).

Nếu cần chọn tên thân mật **chỉ khi đã được duyệt**, `CASE` linh hoạt hơn:

```sql
SELECT
    CASE
        WHEN nickname_is_approved IS TRUE
             AND nickname IS NOT NULL
            THEN nickname
        ELSE full_name
    END AS display_name
FROM members;
```

`COALESCE` chỉ kiểm tra có `NULL` hay không; `CASE` diễn đạt được những điều kiện nghiệp vụ khác. Ngoài ra, `CASE` không tự coi chuỗi rỗng là `NULL`; muốn xử lý chuỗi rỗng như thiếu dữ liệu có thể kết hợp `NULLIF(TRIM(nickname), '')` theo DBMS.

## 18. Khác biệt giữa các hệ quản trị

**Biểu thức `CASE`** là cấu trúc quen thuộc trong SQL chuẩn và được hỗ trợ bởi PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite. Các quy tắc nền tảng “nhánh đầu tiên phù hợp” và “không có `ELSE` thì trả `NULL`” là nguyên tắc quan trọng có thể áp dụng rộng rãi.

Tuy nhiên, có những điểm khác nhau cần chú ý:

| Hệ quản trị | `CASE` trong biểu thức | Điểm cần kiểm tra thêm |
|---|---|---|
| PostgreSQL | Có searched/simple `CASE` | Logic `NULL`, suy luận kiểu, planner có thể tính trước một số biểu thức |
| MySQL | Có searched/simple `CASE` | Kiểu kết quả và quy tắc chuyển kiểu; phân biệt với các hàm/khối rẽ nhánh trong stored program |
| SQL Server | Có `CASE` expression | Quy tắc ưu tiên kiểu dữ liệu, giới hạn lồng nhau; `IIF` là cú pháp khác |
| Oracle Database | Có searched/simple `CASE` | Chuyển kiểu, cách xử lý chuỗi rỗng, và các hàm riêng như `DECODE` |
| SQLite | Có searched/simple `CASE` | Hệ thống kiểu động, quy tắc chuyển kiểu; `iif()` ở những phiên bản hỗ trợ |

### 18.1. SQL Server: IIF không thay thế mọi trường hợp CASE

SQL Server có hàm `IIF(condition, true_value, false_value)`:

```sql
SELECT IIF(85 >= 80, 'Đạt', 'Chưa đạt') AS result;
```

Với hai nhánh, cú pháp này có thể ngắn. Nhưng khi có **nhiều điều kiện theo thứ tự ưu tiên**, `CASE` thường rõ ràng và dễ chuyển đổi giữa DBMS hơn. `IIF` không phải cú pháp SQL chuẩn được mọi DBMS hỗ trợ giống nhau.

### 18.2. MySQL: IF và CASE có vai trò khác nhau

MySQL có hàm `IF(condition, value_if_true, value_if_false)`:

```sql
SELECT IF(85 >= 80, 'Đạt', 'Chưa đạt') AS result;
```

Trong stored program, MySQL còn có cú pháp điều khiển thủ tục với `IF ... THEN ... END IF` và câu lệnh `CASE ... END CASE`. **Câu lệnh điều khiển thủ tục** không phải lúc nào cũng cùng cú pháp hay cùng quy tắc kết quả với **biểu thức `CASE ... END`** đang học. Đặc biệt, câu lệnh `CASE` trong stored program có hành vi riêng khi không chọn nhánh và không có `ELSE`; đừng áp quy tắc “biểu thức trả `NULL`” lên mọi cấu trúc thủ tục cùng tên.

### 18.3. Oracle Database: chuỗi rỗng và NULL

Oracle Database thường xử lý chuỗi ký tự rỗng `''` như `NULL` trong nhiều ngữ cảnh kiểu chuỗi thông dụng. Điều này có thể khiến một biểu thức `CASE` liên quan đến chuỗi rỗng và `NULL` cho kết quả khác với PostgreSQL.

Khi cần phân biệt giá trị thiếu và chuỗi rỗng, nên hiểu quy tắc lưu trữ/so sánh của **DBMS đang dùng**, không chỉ nhìn mã `CASE`.

### 18.4. SQLite: kiểu dữ liệu kết quả có thể linh hoạt

SQLite sử dụng hệ thống kiểu linh hoạt hơn. Biểu thức `CASE` có thể trả giá trị có storage class tùy nhánh được chọn. Khi chuyển truy vấn sang PostgreSQL hoặc SQL Server, các nhánh trộn số và chuỗi có thể không còn hợp lệ do quy tắc chọn kiểu chặt chẽ hơn.

Vì vậy, với SQL đa hệ quản trị, hãy giữ các nhánh `THEN` và `ELSE` cùng kiểu dữ liệu về mặt ý nghĩa và sử dụng `CAST` khi cần.

## 19. Lỗi thường gặp

### Lỗi 1: Đặt điều kiện chung trước điều kiện riêng

```sql
-- Sai cho xếp loại điểm.
CASE
    WHEN score >= 60 THEN 'Đạt'
    WHEN score >= 90 THEN 'Xuất sắc'
    ELSE 'Chưa đạt'
END
```

Điểm 95 sẽ vào nhánh đầu tiên, nhận `Đạt`. Sửa bằng cách đặt `score >= 90` trước.

### Lỗi 2: Bỏ ELSE nhưng mong nhận nhãn mặc định

```sql
CASE
    WHEN status_code = 'APPROVED' THEN 'Đã duyệt'
END
```

Mọi trạng thái khác hoặc `NULL` trả `NULL`, không phải `'Chưa duyệt'`. Nếu nghiệp vụ cần nhãn mặc định, thêm `ELSE`.

### Lỗi 3: Dùng = NULL thay vì IS NULL

```sql
-- Không nhận diện được score NULL.
WHEN score = NULL THEN 'Thiếu điểm'
```

Đúng:

```sql
WHEN score IS NULL THEN 'Thiếu điểm'
```

### Lỗi 4: Dùng simple CASE để so NULL

```sql
CASE score
    WHEN NULL THEN 'Thiếu điểm'
    ELSE 'Có điểm'
END
```

Không khớp `NULL` theo phép so sánh bằng thông thường. Dùng searched `CASE WHEN score IS NULL THEN ...`.

### Lỗi 5: Dùng COUNT(CASE ... ELSE 0 END) để đếm nhánh đúng

```sql
COUNT(CASE WHEN status_code = 'APPROVED' THEN 1 ELSE 0 END)
```

Vì 0 vẫn không `NULL`, `COUNT` đếm cả hàng không khớp. Dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` hoặc `COUNT(CASE WHEN ... THEN 1 END)` theo yêu cầu.

### Lỗi 6: Trộn THEN số và ELSE chữ

```sql
CASE WHEN score >= 65 THEN score ELSE 'Chưa có' END
```

Có thể thất bại ở DBMS yêu cầu kiểu kết quả tương thích, hoặc bị chuyển kiểu ngoài mong muốn. Giữ cả biểu thức là số hoặc chủ động `CAST` kết quả sang văn bản nếu chỉ để hiển thị.

### Lỗi 7: Nghĩ CASE làm thay đổi mọi hàng khi dùng trong SELECT

```sql
SELECT CASE WHEN score >= 65 THEN 'Đạt' ELSE 'Chưa đạt' END
FROM lesson152_applications;
```

Biểu thức `CASE` ở `SELECT` chỉ tạo **giá trị trong kết quả truy vấn**. Nó không cập nhật cột nào của bảng. Muốn thay dữ liệu, phải dùng `UPDATE` đúng phạm vi và quyền hạn.

### Lỗi 8: Dùng CASE để che biểu thức không hợp lệ

`CASE` không bảo đảm mọi lỗi kiểu dữ liệu, biểu thức hằng hoặc thao tác tổng hợp của nhánh không được chọn sẽ không bị phát hiện khi lập kế hoạch/thực thi. Hãy chọn kiểu đúng, kiểm soát mẫu số và viết logic dữ liệu an toàn, thay vì dựa vào điều kiện `WHEN` như cơ chế xử lý ngoại lệ chung.

### Lỗi 9: Không định nghĩa rõ ELSE cho trạng thái lạ

Nếu ứng dụng nhận mã trạng thái mới như `SUSPENDED`, một `CASE` chỉ biết `APPROVED` và `PENDING` có thể đưa nó vào `ELSE` cùng với `NULL`. Nếu cần phân biệt “chưa biết trạng thái” và “trạng thái không được hỗ trợ”, hãy viết các nhánh riêng và theo dõi mã chưa được ánh xạ.

## 20. Bài tập tự kiểm tra

Các bài sử dụng PostgreSQL và bảng `lesson152_applications` ở phần 7 nếu có `FROM`. Hãy dự đoán kết quả trước khi đọc lời giải.

### Bài 1. Thứ tự nào được chọn?

```sql
SELECT
    CASE
        WHEN 92 >= 60 THEN 'Đạt'
        WHEN 92 >= 90 THEN 'Xuất sắc'
        ELSE 'Chưa đạt'
    END AS classification;
```

**Đáp án:** `Đạt`, vì nhánh `>= 60` là nhánh `TRUE` đầu tiên. Nếu yêu cầu là `Xuất sắc`, phải đặt điều kiện `>= 90` trước.

### Bài 2. Không có ELSE

```sql
SELECT
    CASE
        WHEN 40 >= 90 THEN 'Xuất sắc'
        WHEN 40 >= 65 THEN 'Đạt'
    END AS classification;
```

**Đáp án:** `NULL`. Không có nhánh phù hợp và không khai báo `ELSE`.

### Bài 3. Phân biệt NULL và điểm thấp

```sql
SELECT
    score,
    CASE
        WHEN score >= 65 THEN 'Đạt'
        WHEN score < 65 THEN 'Chưa đạt'
        ELSE 'Chưa có điểm'
    END AS result
FROM (VALUES (70), (40), (NULL::INTEGER)) AS scores(score);
```

**Đáp án:** 70 → `Đạt`; 40 → `Chưa đạt`; `NULL` → `Chưa có điểm`. Hai phép so sánh với `NULL` đều không là `TRUE`.

### Bài 4. Simple CASE khi đầu vào NULL

```sql
SELECT
    CASE CAST(NULL AS TEXT)
        WHEN NULL THEN 'Thiếu'
        ELSE 'Không khớp'
    END AS result;
```

**Đáp án:** `Không khớp`. Để xử lý giá trị `NULL`, dùng `WHEN expression IS NULL` trong searched `CASE`.

### Bài 5. Sửa biểu thức xếp loại

Yêu cầu:

- `score IS NULL` → `Chưa đánh giá`.
- `score >= 90` → `A`.
- `score >= 75` → `B`.
- `score >= 60` → `C`.
- Còn lại → `D`.

**Một lời giải:**

```sql
SELECT
    application_id,
    score,
    CASE
        WHEN score IS NULL THEN 'Chưa đánh giá'
        WHEN score >= 90 THEN 'A'
        WHEN score >= 75 THEN 'B'
        WHEN score >= 60 THEN 'C'
        ELSE 'D'
    END AS grade
FROM lesson152_applications
ORDER BY application_id;
```

Các nhánh chồng lấp được sắp theo ngưỡng giảm dần; `ELSE` áp dụng cho điểm dưới 60.

### Bài 6. SUM và COUNT khác nhau thế nào?

```sql
SELECT
    SUM(
        CASE WHEN status_code = 'APPROVED' THEN 1 ELSE 0 END
    ) AS a,
    COUNT(
        CASE WHEN status_code = 'APPROVED' THEN 1 END
    ) AS b,
    COUNT(
        CASE WHEN status_code = 'APPROVED' THEN 1 ELSE 0 END
    ) AS c
FROM lesson152_applications;
```

**Đáp án:** `a = 2`, `b = 2`, `c = 7`. `SUM` cộng 1/0; `COUNT` chỉ bỏ qua `NULL`, không bỏ qua số 0.

### Bài 7. Xếp ưu tiên xử lý

Yêu cầu: nếu `status_code = 'REJECTED'` thì trả `'Dừng'` **bất kể điểm**; nếu không, điểm ≥ 90 trả `'Ưu tiên cao'`; nếu không, trả `'Thông thường'`.

**Một lời giải:**

```sql
SELECT
    application_id,
    CASE
        WHEN status_code = 'REJECTED' THEN 'Dừng'
        WHEN score >= 90 THEN 'Ưu tiên cao'
        ELSE 'Thông thường'
    END AS priority
FROM lesson152_applications;
```

Nhánh `REJECTED` phải đứng **trước** nhánh điểm cao để đảm bảo quy tắc loại trừ được ưu tiên.

### Bài 8. Giữ nguyên dữ liệu trong UPDATE khi không khớp

Câu lệnh dưới đây có nguy cơ gì?

```sql
UPDATE lesson152_applications
SET status_code = CASE
    WHEN score >= 90 THEN 'PRIORITY'
END;
```

**Đáp án:** Những hàng có `score < 90` hoặc `score IS NULL` sẽ có biểu thức `CASE` trả `NULL`, và `UPDATE` có thể ghi `NULL` vào `status_code` (nếu cột cho phép). Câu lệnh còn thiếu `WHERE` nên tác động tất cả hàng.

Có thể sửa thành:

```sql
UPDATE lesson152_applications
SET status_code = CASE
    WHEN score >= 90 THEN 'PRIORITY'
    ELSE status_code
END
WHERE application_id = 1;
```

Hoặc đơn giản hơn trong trường hợp chỉ cần sửa hàng đạt điều kiện:

```sql
UPDATE lesson152_applications
SET status_code = 'PRIORITY'
WHERE score >= 90;
```

Hai câu sửa minh họa hai phạm vi cập nhật **khác nhau**; chọn theo yêu cầu nghiệp vụ, và chỉ thử trên dữ liệu thực hành.

### Bài 9. Kiểu kết quả CASE

Vì sao biểu thức sau không nên dùng nếu muốn dữ liệu số để tiếp tục tính toán?

```sql
CASE
    WHEN score IS NOT NULL THEN CAST(score AS TEXT)
    ELSE 'Chưa có điểm'
END
```

**Đáp án:** Kết quả là **văn bản** để hiển thị, không còn là cột số phù hợp cho các phép tính số học. Nếu còn cần tính `AVG`, `SUM` hoặc so sánh số, nên giữ `score` dưới kiểu số, trả thêm nhãn trạng thái hoặc định dạng ở ứng dụng.

### Bài 10. CASE lồng nhau hay một CASE phẳng?

Cho quy tắc:

1. Trạng thái `APPROVED`, điểm ≥ 90 → `Ưu tiên A`.
2. Trạng thái `APPROVED`, điểm khác → `Ưu tiên B`.
3. Trạng thái `PENDING` → `Đang chờ`.
4. Còn lại → `Khác`.

**Lời giải dạng phẳng:**

```sql
SELECT
    application_id,
    CASE
        WHEN status_code = 'APPROVED' AND score >= 90
            THEN 'Ưu tiên A'
        WHEN status_code = 'APPROVED'
            THEN 'Ưu tiên B'
        WHEN status_code = 'PENDING'
            THEN 'Đang chờ'
        ELSE 'Khác'
    END AS priority
FROM lesson152_applications
ORDER BY application_id;
```

Nhánh `APPROVED` + điểm cao đứng trước nhánh `APPROVED` chung. Nếu đảo thứ tự, không hàng `APPROVED` nào nhận `Ưu tiên A`.

## 21. Bảng ghi nhớ

| Tình huống | Quy tắc nên nhớ |
|---|---|
| Nhiều `WHEN` cùng đúng | **Chỉ giá trị của nhánh đúng đầu tiên** là kết quả |
| Không `WHEN` nào đúng và có `ELSE` | Lấy giá trị sau `ELSE` |
| Không `WHEN` nào đúng và không có `ELSE` | Kết quả là **`NULL`** |
| Điều kiện `WHEN` là `UNKNOWN` | Không chọn nhánh đó |
| Muốn nhận diện `NULL` | Dùng `IS NULL` trong searched `CASE` |
| Simple `CASE expr WHEN value` | So sánh một biểu thức với từng giá trị; `WHEN NULL` không khớp `NULL` theo phép bằng thông thường |
| Chấm điểm theo ngưỡng | Đặt ngưỡng **cao trước thấp** hoặc dùng khoảng không chồng nhau |
| Quy tắc ngoại lệ quan trọng | Đặt nhánh ngoại lệ **trước** nhánh tổng quát |
| Đếm nhánh đúng | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` hoặc `COUNT(CASE WHEN ... THEN 1 END)` |
| `COUNT(CASE ... ELSE 0 END)` | Có thể đếm cả các hàng không khớp vì 0 không phải `NULL` |
| Nhiều kiểu kết quả `THEN`/`ELSE` | Chọn kiểu chung phù hợp; `CAST` khi cần |
| `CASE` trong `UPDATE` | Chú ý cả `ELSE` và phạm vi `WHERE` |

**Kết luận:** `CASE` thực hiện lựa chọn theo **thứ tự ưu tiên**, không phải chọn “nhánh khớp tốt nhất” theo ý người đọc. Muốn viết đúng, hãy xác định **nhánh nào phải thắng khi các điều kiện chồng lấp**, **những giá trị nào có thể `NULL`**, và **đầu ra mong muốn khi không nhánh nào phù hợp**. Đặc biệt, nếu bỏ `ELSE`, hãy làm điều đó **có chủ đích** vì kết quả mặc định là `NULL` — một giá trị có thể ảnh hưởng đến thống kê, sắp xếp, hiển thị và cập nhật dữ liệu.


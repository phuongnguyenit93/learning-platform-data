# BOOLEAN/BOOL, TINYINT và kiểm tra miền giá trị đúng/sai

Trong MySQL, `BOOLEAN` và `BOOL` là tên viết tắt dễ đọc cho kiểu `TINYINT(1)`. Chúng không phải một kiểu boolean độc lập có miền giá trị chỉ gồm `TRUE` và `FALSE`. Về lưu trữ, MySQL vẫn dùng số nguyên nhỏ; nếu không có ràng buộc, cột boolean có thể chứa những giá trị như `2`, `-1` hoặc `17`.

Sự khác biệt giữa **giá trị được lưu**, **cách MySQL diễn giải biểu thức trong ngữ cảnh điều kiện** và **miền giá trị mà nghiệp vụ cho phép** rất quan trọng. Một cột tên `is_active` có thể được truy vấn như điều kiện đúng/sai, nhưng điều đó không tự bảo đảm dữ liệu chỉ là `0` hoặc `1`. Muốn bảo đảm miền giá trị, cần thiết kế `NOT NULL`, `DEFAULT` và `CHECK` phù hợp, đồng thời xác minh phiên bản MySQL thực sự thực thi constraint.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `BOOLEAN`, `BOOL`, `TINYINT(1)` và `TINYINT`.
- Phân biệt giá trị `0`, `1`, số khác không và `NULL` trong biểu thức điều kiện.
- Nhận biết vì sao `flag = TRUE` khác với `flag IS TRUE` khi dữ liệu có giá trị ngoài miền chuẩn.
- Thiết kế cột boolean với `NOT NULL`, `DEFAULT` và `CHECK`.
- Phát hiện dữ liệu boolean không hợp lệ trong bảng cũ và lập kế hoạch chuẩn hóa có kiểm soát.
- Tránh các lỗi thường gặp khi tổng hợp, lọc và đánh index cho cột boolean.

## 1. BOOLEAN và BOOL thực chất là gì?

MySQL định nghĩa `BOOL` và `BOOLEAN` là synonym của `TINYINT(1)`. Giá trị `TRUE` được hiểu là `1`, còn `FALSE` được hiểu là `0`.

```sql
SELECT
    TRUE AS true_value,
    FALSE AS false_value,
    TRUE + 0 AS true_as_number,
    FALSE + 0 AS false_as_number;
```

Kết quả tương ứng là `1`, `0`, `1` và `0`. Bạn có thể dùng `TRUE`/`FALSE` trong câu lệnh SQL để biểu đạt ý nghĩa rõ hơn:

```sql
CREATE TABLE feature_setting (
    setting_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    feature_name VARCHAR(80) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (setting_id)
);

INSERT INTO feature_setting (feature_name, is_enabled)
VALUES ('new_checkout', TRUE),
       ('legacy_report', FALSE);

SELECT setting_id, feature_name, is_enabled
FROM feature_setting;
```

Trong kết quả truy vấn, giá trị thường hiển thị dưới dạng số `1` hoặc `0`, bởi kiểu lưu trữ thực tế là `TINYINT(1)`. Khi xem `SHOW CREATE TABLE`, bạn cũng có thể thấy MySQL biểu diễn cột `BOOLEAN` dưới dạng `tinyint(1)`.

## 2. TINYINT và miền giá trị số

`TINYINT` là kiểu số nguyên có kích thước một byte. Nếu không khai báo `UNSIGNED`, miền giá trị là:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|
| `TINYINT` | -128 | 127 |
| `TINYINT UNSIGNED` | 0 | 255 |

`TINYINT(1)` vẫn có miền số nguyên như `TINYINT`; số `1` trong ngoặc là display width (độ rộng hiển thị lịch sử), không phải giới hạn số chữ số hay số lượng giá trị. Vì vậy, `TINYINT(1)` có thể lưu `2`, `10` hoặc `-1` nếu giá trị nằm trong miền của kiểu và không có constraint ngăn cản. Display width cho kiểu số nguyên đã bị deprecated từ MySQL 8.0.17; không nên dựa vào nó để xác thực dữ liệu.

Ví dụ tạo cột `TINYINT(1)` không có constraint:

```sql
CREATE TABLE boolean_without_check (
    id INT NOT NULL PRIMARY KEY,
    enabled TINYINT(1) NOT NULL
);

INSERT INTO boolean_without_check (id, enabled)
VALUES (1, 0), (2, 1), (3, 2), (4, -1);

SELECT id, enabled
FROM boolean_without_check
ORDER BY id;
```

Các giá trị `2` và `-1` vẫn nằm trong miền `TINYINT` có dấu, nên có thể được lưu. Việc đặt tên cột là `enabled` hoặc khai báo `TINYINT(1)` không tự giới hạn miền dữ liệu về `0` và `1`.

Với giá trị vượt miền kiểu số, hành vi còn phụ thuộc SQL mode. Trong strict mode, MySQL thường từ chối giá trị ngoài miền; ở chế độ không strict, một số trường hợp có thể bị ép về giá trị biên và phát cảnh báo. Constraint kiểm tra miền boolean vẫn cần thiết ngay cả khi dùng strict mode, vì `2` và `-1` vốn nằm trong miền số của `TINYINT`.

## 3. MySQL diễn giải giá trị đúng/sai như thế nào?

Trong ngữ cảnh boolean của MySQL, số `0` được xem là false và mọi số khác `0` được xem là true. Điều này áp dụng cho điều kiện `WHERE`, `IF()` và nhiều biểu thức logic.

```sql
SELECT
    IF(0, 'TRUE', 'FALSE') AS zero_result,
    IF(1, 'TRUE', 'FALSE') AS one_result,
    IF(2, 'TRUE', 'FALSE') AS two_result,
    IF(-1, 'TRUE', 'FALSE') AS negative_result;
```

Kết quả lần lượt là `FALSE`, `TRUE`, `TRUE`, `TRUE`. Vì vậy, nếu cột cũ chứa `2` hoặc `-1`, câu truy vấn sau vẫn xem các hàng đó là đúng:

```sql
SELECT id, enabled
FROM boolean_without_check
WHERE enabled;
```

### 3.1. `= TRUE` khác `IS TRUE`

Đây là điểm dễ gây lỗi khi dữ liệu có giá trị ngoài miền chuẩn:

```sql
SELECT
    enabled,
    enabled = TRUE AS equals_true,
    enabled IS TRUE AS is_true,
    enabled = FALSE AS equals_false,
    enabled IS FALSE AS is_false
FROM boolean_without_check
ORDER BY id;
```

`TRUE` là hằng số số `1`, `FALSE` là hằng số số `0`. Vì vậy, `enabled = TRUE` chỉ khớp giá trị bằng `1`; `enabled IS TRUE` kiểm tra giá trị có được xem là true hay không, tức là khác `0` và không phải `NULL`. Tương tự, `enabled = FALSE` và `enabled IS FALSE` kiểm tra giá trị false theo quy tắc truth test.

| Giá trị lưu | `value = TRUE` | `value IS TRUE` | `value = FALSE` | `value IS FALSE` |
|---:|---:|---:|---:|---:|
| `0` | 0 | 0 | 1 | 1 |
| `1` | 1 | 1 | 0 | 0 |
| `2` | 0 | 1 | 0 | 0 |
| `-1` | 0 | 1 | 0 | 0 |
| `NULL` | `NULL` | 0 | `NULL` | 0 |

Nếu schema đã bảo đảm chỉ có `0` và `1`, hai cách kiểm tra `= TRUE` và `IS TRUE` cho kết quả tương ứng như mong đợi. Khi chưa chắc dữ liệu có sạch hay không, hãy dùng điều kiện rõ ràng và kiểm tra miền giá trị trước khi kết luận.

### 3.2. NULL tạo ra trạng thái UNKNOWN

SQL dùng logic ba giá trị: `TRUE`, `FALSE` và `UNKNOWN`. Khi biểu thức liên quan đến `NULL`, kết quả thường là `UNKNOWN` (được hiển thị như `NULL`). Ví dụ:

```sql
SELECT
    NULL = TRUE AS null_equals_true,
    NULL = FALSE AS null_equals_false,
    NULL IS TRUE AS null_is_true,
    NULL IS FALSE AS null_is_false,
    NULL IS UNKNOWN AS null_is_unknown;
```

Kết quả hai phép so sánh `=` là `NULL`; `IS TRUE` và `IS FALSE` trả về `0`; `IS UNKNOWN` trả về `1`. Trong `WHERE`, hàng có điều kiện `UNKNOWN` không được chọn.

`NULL` không đồng nghĩa với `FALSE`. Nếu một trường có thể ở trạng thái chưa biết, chẳng hạn kết quả xác minh chưa được cập nhật, cần quyết định rõ có muốn lưu `NULL` hay dùng một trạng thái nghiệp vụ riêng. Không nên tự động đổi mọi `NULL` thành `0` nếu điều đó làm mất ý nghĩa “chưa xác định”.

## 4. Thiết kế cột boolean bảo đảm miền 0/1

Một cột biểu diễn đúng/sai thường cần ba quyết định:

1. Cột có bắt buộc phải có giá trị không? Nếu có, khai báo `NOT NULL`.
2. Giá trị mặc định khi không truyền vào là gì? Dùng `DEFAULT TRUE` hoặc `DEFAULT FALSE` theo nghiệp vụ.
3. Database có cần từ chối mọi giá trị ngoài `0` và `1` không? Dùng `CHECK`.

Ví dụ:

```sql
CREATE TABLE account_preference (
    account_id BIGINT UNSIGNED NOT NULL,
    email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
    marketing_consent BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_email_notifications_boolean
        CHECK (email_notifications IN (0, 1)),
    CONSTRAINT chk_marketing_consent_boolean
        CHECK (marketing_consent IN (0, 1))
) ENGINE = InnoDB;
```

Hai constraint buộc giá trị phải thuộc tập `0` hoặc `1`. `NOT NULL` ngăn giá trị chưa xác định; `DEFAULT` chỉ được áp dụng khi câu lệnh bỏ qua cột hoặc yêu cầu `DEFAULT`, chứ không tự thay thế một giá trị `NULL` được truyền tường minh.

### 4.1. Vì sao cần cả NOT NULL và CHECK?

Trong MySQL, biểu thức `CHECK` được xem là đạt nếu kết quả là `TRUE` hoặc `UNKNOWN`; chỉ kết quả `FALSE` mới vi phạm constraint. Do đó, chỉ viết:

```sql
CHECK (marketing_consent IN (0, 1))
```

không ngăn được `NULL` nếu cột cho phép null. Khi `marketing_consent` là `NULL`, biểu thức `IN` cho kết quả `UNKNOWN`, nên `CHECK` không từ chối. Nếu nghiệp vụ yêu cầu đúng một trong hai trạng thái, cần kết hợp `NOT NULL`.

Nếu `NULL` có ý nghĩa nghiệp vụ thực sự, có thể cho phép null và dùng constraint để chỉ chấp nhận `NULL`, `0`, `1`; khi đó hãy ghi rõ ý nghĩa của ba trạng thái và xử lý chúng nhất quán trong truy vấn.

### 4.2. Phiên bản MySQL có thực thi CHECK

MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16. Các phiên bản MySQL cũ hơn có thể chấp nhận cú pháp nhưng bỏ qua việc kiểm tra. Vì vậy, trước khi dựa vào `CHECK` để bảo vệ miền boolean, kiểm tra phiên bản:

```sql
SELECT VERSION();
```

Sau khi tạo bảng, kiểm tra định nghĩa constraint:

```sql
SHOW CREATE TABLE account_preference;
```

Trên phiên bản có metadata `ENFORCED`, có thể kiểm tra trạng thái constraint trực tiếp:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.ENFORCED,
    cc.CHECK_CLAUSE
FROM information_schema.table_constraints AS tc
JOIN information_schema.check_constraints AS cc
    ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = DATABASE()
  AND tc.TABLE_NAME = 'account_preference'
  AND tc.CONSTRAINT_TYPE = 'CHECK';
```

Đối với MySQL 8.0.16 trở lên, cần xác nhận constraint có trong định nghĩa và `ENFORCED = 'YES'`. Nếu đang dùng phiên bản cũ không thực thi `CHECK`, hãy nâng cấp hoặc áp dụng cơ chế xác thực tương đương theo kiến trúc của hệ thống; không coi cú pháp được chấp nhận là bằng chứng constraint hoạt động.

## 5. Thực hành kiểm tra dữ liệu hợp lệ và không hợp lệ

Chạy ví dụ trong database sandbox:

```sql
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES
    (101, TRUE, FALSE),
    (102, FALSE, TRUE),
    (103, 1, 0),
    (104, 0, 1);

SELECT *
FROM account_preference
ORDER BY account_id;
```

Các cách ghi `TRUE`/`FALSE` và `1`/`0` đều được lưu dưới dạng `1` hoặc `0`.

Các lệnh sau được thiết kế để chạy riêng lẻ và dự kiến bị từ chối:

```sql
-- Giá trị 2 không thuộc miền 0/1
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (105, 2, 0);

-- Giá trị -1 không thuộc miền 0/1
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (106, -1, 0);

-- NULL vi phạm NOT NULL
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (107, NULL, 0);
```

Hai lệnh đầu vi phạm `CHECK`; lệnh thứ ba vi phạm `NOT NULL`. Hãy đọc thông báo lỗi và xác minh constraint đã được thực thi. Nếu giá trị `2` hoặc `-1` vẫn được chấp nhận, hãy kiểm tra phiên bản MySQL, định nghĩa bảng và trạng thái enforcement của constraint.

Kiểm tra các hàng có giá trị true và false:

```sql
SELECT account_id
FROM account_preference
WHERE marketing_consent IS TRUE;

SELECT account_id
FROM account_preference
WHERE marketing_consent IS FALSE;
```

Vì miền giá trị đã được ràng buộc, mỗi hàng có giá trị đều thuộc một trong hai nhóm. Nếu cột cho phép `NULL`, cần truy vấn nhóm chưa xác định riêng:

```sql
SELECT account_id
FROM account_preference
WHERE marketing_consent IS NULL;
```

## 6. BOOL/BOOLEAN hay TINYINT?

Vì `BOOL` và `BOOLEAN` là alias của `TINYINT(1)`, ba khai báo này không tạo ra ba kiểu lưu trữ khác nhau. Khác biệt chính là ý nghĩa mà người đọc hiểu từ schema.

| Khai báo | Ý nghĩa nên dùng | Lưu ý |
|---|---|---|
| `BOOLEAN` | Trường đúng/sai | Dễ đọc nhất khi miền nghiệp vụ là boolean |
| `BOOL` | Tương đương `BOOLEAN` | Hợp lệ nhưng ít phổ biến hơn trong schema mới |
| `TINYINT` | Số nguyên nhỏ có nhiều trạng thái số | Dùng khi cần miền số rộng hơn boolean |
| `TINYINT(1)` | Alias lưu trữ thường thấy sau khi khai báo boolean | `(1)` không giới hạn giá trị vào 0/1 |
| `TINYINT UNSIGNED` | Số nguyên nhỏ không âm | Phù hợp với số lượng nhỏ hoặc mã trạng thái số, cần constraint riêng nếu có miền hữu hạn |

Nếu cột biểu diễn một thuộc tính đúng/sai, dùng `BOOLEAN` giúp schema thể hiện ý định. Nếu cột lưu một trạng thái có nhiều giá trị, ví dụ `PENDING`, `APPROVED`, `REJECTED`, không nên ép chúng vào một cột boolean hoặc mã số mà không có quy ước rõ ràng. Hãy dùng `VARCHAR` với `CHECK`, `ENUM` khi phù hợp, hoặc bảng tham chiếu trạng thái nếu cần mở rộng và quản trị trạng thái.

## 7. NULL, DEFAULT và ý nghĩa nghiệp vụ

Không phải mọi cột boolean đều nên có mặc định `FALSE`. Hãy xác định ý nghĩa của việc không truyền giá trị:

| Trường hợp | Thiết kế gợi ý |
|---|---|
| Không truyền giá trị đồng nghĩa chưa bật | `BOOLEAN NOT NULL DEFAULT FALSE` |
| Không truyền giá trị đồng nghĩa bật theo chính sách | `BOOLEAN NOT NULL DEFAULT TRUE` |
| Chưa biết trạng thái và cần giữ khác biệt với false | `BOOLEAN NULL` cùng quy tắc xử lý null rõ ràng |
| Có ba trạng thái nghiệp vụ rõ ràng | Cân nhắc `status` với các giá trị có tên, chẳng hạn `PENDING`, `YES`, `NO` |

Ví dụ về một cờ xác minh:

```sql
CREATE TABLE customer_verification (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_verified BOOLEAN NULL,
    CONSTRAINT chk_customer_is_verified
        CHECK (is_verified IN (0, 1))
);
```

Trong thiết kế này, `NULL` có thể biểu thị chưa có kết quả xác minh; `0` là đã xác minh và kết luận không đạt; `1` là đã xác minh và đạt. Nếu quy tắc nghiệp vụ cần phân biệt thêm trạng thái đang chờ, bị từ chối, hết hạn hoặc cần bổ sung hồ sơ, một cột `verification_status` với tập trạng thái có tên thường dễ hiểu hơn một boolean nullable.

## 8. Lọc, tổng hợp và thống kê boolean

Khi miền giá trị được bảo đảm là `0` và `1`, có thể dùng các phép tổng hợp số:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(marketing_consent) AS rows_with_known_value,
    SUM(marketing_consent) AS consented_rows,
    SUM(marketing_consent = TRUE) AS consented_rows_by_comparison,
    SUM(marketing_consent IS FALSE) AS declined_rows
FROM account_preference;
```

`COUNT(*)` đếm tất cả hàng; `COUNT(column)` bỏ qua `NULL`; `SUM(boolean_column)` cộng giá trị số được lưu. Nếu cột chứa `2` hoặc `-1`, tổng có thể không còn mang nghĩa số lượng hàng true. Với dữ liệu nullable, `SUM()` cũng bỏ qua `NULL` và có thể trả về `NULL` nếu không có giá trị phù hợp; dùng `COALESCE` nếu báo cáo cần hiển thị số `0`.

Để đếm rõ số hàng có truth value true kể cả khi dữ liệu cũ có số khác không:

```sql
SELECT COUNT(*) AS truthy_rows
FROM boolean_without_check
WHERE enabled IS TRUE;
```

Đối với truy vấn nghiệp vụ trên cột đã chuẩn hóa, dùng điều kiện tường minh như `is_enabled = TRUE`, `is_enabled IS TRUE` hoặc `is_enabled = 1` theo quy ước của nhóm. Điều quan trọng là schema phải bảo đảm miền giá trị để truy vấn không phụ thuộc vào dữ liệu bất thường.

### 8.1. Có nên tạo index riêng cho boolean?

Cột boolean thường chỉ có hai giá trị nên độ phân biệt (cardinality) thấp. Một index riêng trên cột chỉ có `0` và `1` có thể không giúp ích nếu mỗi giá trị khớp với phần lớn bảng. Bộ tối ưu có thể chọn quét bảng vì đọc nhiều hàng qua index rồi truy cập dữ liệu vẫn tốn chi phí.

Nếu truy vấn thường lọc theo boolean kết hợp với một cột khác, có thể đánh giá index ghép theo thứ tự điều kiện truy vấn thực tế, ví dụ `(is_enabled, created_at)`. Hãy dùng `EXPLAIN`, dữ liệu có quy mô gần thực tế và đo thời gian trước/sau; không thêm index chỉ vì một cột xuất hiện trong `WHERE`.

## 9. Phát hiện và chuẩn hóa dữ liệu boolean trong bảng cũ

Một hệ thống có thể đã dùng `TINYINT(1)` từ lâu mà không có `CHECK`. Trước khi thêm constraint, hãy thống kê toàn bộ giá trị:

```sql
SELECT enabled, COUNT(*) AS row_count
FROM legacy_feature
GROUP BY enabled
ORDER BY enabled;
```

Tìm những hàng nằm ngoài miền mong muốn, đồng thời kiểm tra `NULL` riêng:

```sql
SELECT id, enabled
FROM legacy_feature
WHERE enabled IS NULL
   OR enabled NOT IN (0, 1);
```

Không chỉ dùng `enabled NOT IN (0,1)` để tìm dữ liệu lỗi nếu cột có thể chứa `NULL`: phép so sánh với `NULL` trả về `UNKNOWN`, nên hàng null không được chọn bởi `WHERE`.

Trước khi sửa dữ liệu, xác định ý nghĩa của từng giá trị cũ với chủ sở hữu nghiệp vụ. Ví dụ, `2` có thể từng được dùng cho “đang chờ”, còn `-1` có thể mang nghĩa “không áp dụng”. Không tự động đổi tất cả giá trị khác `0` thành `1`, vì như vậy có thể làm mất thông tin trạng thái.

Một quy trình migration an toàn:

1. Thống kê số lượng từng giá trị, số hàng null và phạm vi bản ghi bị ảnh hưởng.
2. Xác định quy tắc ánh xạ giá trị cũ sang `0`, `1` hoặc trạng thái mới với người phụ trách nghiệp vụ.
3. Sao lưu và thử migration trên bản sao dữ liệu.
4. Chạy cập nhật theo lô hoặc trong cửa sổ thay đổi phù hợp, kiểm tra số hàng trước và sau.
5. Xác minh không còn giá trị ngoài miền; chỉ thêm constraint sau khi dữ liệu đạt yêu cầu.
6. Kiểm tra ứng dụng, báo cáo, API và job nền có gửi giá trị ngoài miền hay không.

Sau khi dữ liệu đã được làm sạch và cột phải có giá trị:

```sql
ALTER TABLE legacy_feature
    MODIFY enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT chk_legacy_feature_enabled
        CHECK (enabled IN (0, 1));
```

Chỉ dùng `DEFAULT FALSE` nếu nghiệp vụ xác nhận giá trị mặc định là false. Nếu `NULL` có ý nghĩa, không thêm `NOT NULL` trước khi có quy tắc xử lý và backfill phù hợp. Thao tác `ALTER TABLE` có thể dựng lại bảng hoặc gây khóa tùy phiên bản, engine, kích thước và loại thay đổi; hãy đánh giá thời gian, tài nguyên và cửa sổ triển khai trước khi áp dụng trên production.

## 10. Những lỗi thường gặp

- Nghĩ `BOOLEAN` là kiểu riêng chỉ nhận `TRUE` hoặc `FALSE`; thực tế MySQL dùng `TINYINT(1)`.
- Nghĩ `TINYINT(1)` chỉ lưu được một chữ số hoặc hai giá trị; display width không giới hạn miền số.
- Dùng `WHERE flag` rồi giả định dữ liệu chỉ có `1`; mọi số khác `0` đều được xem là true trong ngữ cảnh điều kiện.
- Dùng `flag = TRUE` khi muốn kiểm tra mọi giá trị truthy; phép so sánh này tương đương so với `1`.
- Dùng `CHECK` nhưng quên `NOT NULL`, khiến `NULL` vẫn được chấp nhận do biểu thức constraint có thể là `UNKNOWN`.
- Dựa vào `CHECK` trên MySQL trước 8.0.16, nơi constraint chưa được thực thi.
- Tự động đổi mọi giá trị khác `0` thành `1` mà chưa xác minh ý nghĩa nghiệp vụ.
- Dùng boolean để biểu diễn một quy trình có nhiều trạng thái như chờ duyệt, đã duyệt, từ chối và hết hạn.
- Tạo index riêng trên cột boolean có độ chọn lọc thấp mà chưa đo bằng `EXPLAIN`.

## 11. Checklist thiết kế và kiểm tra boolean

- Đã xác nhận cột thực sự chỉ có hai trạng thái hay cần nhiều trạng thái nghiệp vụ.
- Đã chọn `BOOLEAN`/`BOOL` cho ý nghĩa đúng/sai hoặc `TINYINT` khi cần miền số nhỏ rộng hơn.
- Đã hiểu `BOOLEAN` là alias của `TINYINT(1)` và display width không giới hạn giá trị.
- Đã quyết định rõ `NULL` có ý nghĩa hay không.
- Đã đặt `NOT NULL` khi chỉ cho phép đúng hai trạng thái.
- Đã chọn `DEFAULT TRUE` hoặc `DEFAULT FALSE` theo quy tắc nghiệp vụ.
- Đã thêm `CHECK (column IN (0,1))` nếu phiên bản MySQL thực thi constraint.
- Đã kiểm tra phiên bản, `SHOW CREATE TABLE` và trạng thái `ENFORCED`.
- Đã rà soát dữ liệu legacy trước khi thêm constraint hoặc thay đổi kiểu.
- Đã kiểm thử truy vấn với `0`, `1`, số khác không và `NULL`.
- Đã đánh giá index boolean dựa trên độ chọn lọc và truy vấn thực tế.

Trong MySQL, tên kiểu `BOOLEAN` giúp schema dễ hiểu nhưng không tự bảo đảm dữ liệu đúng/sai. `TINYINT(1)` vẫn có thể chứa nhiều số nguyên, còn điều kiện SQL xem mọi số khác không là true. Kết hợp `NOT NULL`, `DEFAULT` và `CHECK` đúng phiên bản, đồng thời kiểm tra dữ liệu cũ trước khi migration, sẽ giúp miền giá trị boolean rõ ràng và nhất quán từ database đến ứng dụng.

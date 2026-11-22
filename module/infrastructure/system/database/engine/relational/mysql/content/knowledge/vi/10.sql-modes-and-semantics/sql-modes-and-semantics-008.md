# Quy tắc phép chia, tràn số và dữ liệu ngày giờ không hợp lệ

MySQL không chỉ kiểm tra kiểu dữ liệu khi tạo bảng. Trong lúc chạy câu lệnh, server còn phải xử lý phép tính, chuyển đổi kiểu và xác minh giá trị có nằm trong miền hợp lệ hay không. Một phép chia cho 0, một phép cộng vượt miền BIGINT hoặc một ngày không tồn tại có thể trả NULL, phát sinh warning, bị từ chối bằng error hoặc được điều chỉnh tùy theo ngữ cảnh và SQL mode.

SQL mode là tập hợp các chế độ thay đổi cách MySQL phân tích và xử lý SQL. Chúng có thể ảnh hưởng đến phép chia cho 0, giá trị số ngoài phạm vi, ngày giờ không hợp lệ, dữ liệu thiếu hoặc sai định dạng. Vì vậy, cùng một câu lệnh có thể cho kết quả khác nhau giữa hai môi trường nếu cấu hình SQL mode khác nhau.

Bài viết tập trung vào MySQL 8.x và storage engine InnoDB. Khi vận hành hệ thống thực tế, hãy kiểm tra phiên bản server, SQL mode của đúng session và kiểu dữ liệu đích trước khi kết luận về hành vi.

## 1. SQL mode điều khiển ngữ nghĩa thực thi

SQL mode là danh sách các chế độ được bật cho server hoặc cho một session. Một số mode ảnh hưởng cú pháp, một số ảnh hưởng kiểm tra dữ liệu và cách xử lý lỗi.

Hai phạm vi thường gặp:

- **GLOBAL**: giá trị mặc định mà các kết nối mới nhận khi tạo session.
- **SESSION**: giá trị đang áp dụng cho kết nối hiện tại.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

Hoặc:

~~~sql
SHOW SESSION VARIABLES LIKE 'sql_mode';
~~~

Khi thay đổi GLOBAL, các kết nối đang mở không tự động đổi session mode. Điều này đặc biệt quan trọng với connection pool: một kết nối có thể giữ SQL mode đã nhận lúc được tạo hoặc đã được ứng dụng thay đổi.

Có thể thiết lập cho session kiểm thử:

~~~sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO';
~~~

Lệnh trên thay toàn bộ danh sách mode của session bằng đúng hai mode được nêu. Trong ứng dụng thực tế, không nên sao chép ví dụ này một cách máy móc vì có thể vô tình bỏ các mode khác đang cần. Hãy đọc giá trị hiện tại, xác định chính sách mong muốn và quản lý cấu hình nhất quán giữa môi trường phát triển, kiểm thử và sản xuất.

## 2. Phép chia cho 0

### 2.1. Phép chia thông thường

MySQL hỗ trợ phép chia /, chia lấy phần nguyên DIV và phép lấy phần dư MOD(). Khi mẫu số bằng 0, phép toán không thể tạo ra một kết quả số hữu hạn theo quy tắc thông thường.

Ví dụ:

~~~sql
SELECT 10 / 0;
SELECT 10 DIV 0;
SELECT MOD(10, 0);
~~~

Trong MySQL, phép chia cho 0 thường cho kết quả NULL và có thể phát sinh warning. Việc có warning hay error phụ thuộc SQL mode và ngữ cảnh câu lệnh. Với câu SELECT, kết quả thường là NULL cùng warning khi ERROR_FOR_DIVISION_BY_ZERO được bật; nếu mode này không bật, phép toán có thể trả NULL mà không có warning.

ERROR_FOR_DIVISION_BY_ZERO đã được đánh dấu deprecated trong các dòng MySQL hiện đại. Dù vẫn có thể xuất hiện trong cấu hình tương thích và mặc định của một số bản phát hành, hãy kiểm tra tài liệu đúng phiên bản và dựa vào strict mode cùng kiểm tra dữ liệu rõ ràng cho chính sách mới.

Kiểm tra ngay sau câu lệnh:

~~~sql
SHOW WARNINGS;
SELECT @@warning_count;
~~~

Hãy chạy SHOW WARNINGS ngay sau câu lệnh cần kiểm tra vì một câu lệnh tiếp theo có thể thay đổi danh sách warning hiện tại.

### 2.2. Khi phép chia nằm trong INSERT hoặc UPDATE

Phép chia cho 0 trong câu lệnh ghi dữ liệu cần được xem xét cùng SQL mode:

- Khi ERROR_FOR_DIVISION_BY_ZERO được bật, MySQL có thể phát warning cho phép chia cho 0.
- Khi kết hợp với strict mode, phép chia cho 0 trong INSERT hoặc UPDATE có thể khiến câu lệnh thất bại.
- Với INSERT IGNORE hoặc UPDATE IGNORE, một số lỗi được hạ thành warning và câu lệnh có thể tiếp tục với giá trị thay thế hoặc NULL tùy biểu thức, cột đích và ràng buộc.

Ví dụ trên bảng kiểm thử:

~~~sql
CREATE TEMPORARY TABLE division_demo (
    numerator   DECIMAL(12, 2) NOT NULL,
    denominator DECIMAL(12, 2) NOT NULL,
    result      DECIMAL(12, 4) NULL
);

INSERT INTO division_demo (numerator, denominator, result)
VALUES (10, 0, 10 / 0);
~~~

Kết quả của INSERT phụ thuộc SQL mode hiện tại. Nếu câu lệnh thất bại, hãy xem error trả về và SQL mode của session. Nếu câu lệnh thành công nhưng có warning, kiểm tra giá trị thực tế trong bảng và warning ngay sau đó.

Không nên dựa vào hành vi ngầm của MySQL để quyết định kết quả nghiệp vụ khi mẫu số bằng 0. Ứng dụng nên xác định rõ đó là dữ liệu không hợp lệ, kết quả không xác định hay một trường hợp cần bỏ qua.

### 2.3. Chặn mẫu số bằng 0 bằng NULLIF

Một cách an toàn để tránh phép chia cho 0 là dùng NULLIF:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM division_demo;
~~~

NULLIF(a, b) trả về NULL nếu hai giá trị bằng nhau; nếu khác nhau, nó trả về a. Vì vậy, khi denominator bằng 0, mẫu số trở thành NULL và phép chia trả về NULL thay vì thực hiện phép chia cho 0.

Nếu nghiệp vụ cần một giá trị mặc định, có thể dùng COALESCE, nhưng phải chọn mặc định có ý nghĩa:

~~~sql
SELECT COALESCE(
    numerator / NULLIF(denominator, 0),
    0
) AS ratio_or_zero
FROM division_demo;
~~~

Chỉ dùng 0 nếu nghiệp vụ thực sự định nghĩa mẫu số bằng 0 tương đương tỷ lệ bằng 0. Trong nhiều trường hợp, NULL có nghĩa “không xác định” và khác hoàn toàn với số 0.

Một cách khác là CASE:

~~~sql
SELECT
    CASE
        WHEN denominator = 0 THEN NULL
        ELSE numerator / denominator
    END AS ratio
FROM division_demo;
~~~

### 2.4. Phân biệt /, DIV và MOD

| Biểu thức | Ý nghĩa | Ví dụ với 10 và 3 |
|---|---|---|
| 10 / 3 | Chia số học, có phần thập phân | 3.3333... |
| 10 DIV 3 | Chia lấy phần nguyên | 3 |
| MOD(10, 3) | Phần dư | 1 |

Độ scale của kết quả phép chia / còn chịu ảnh hưởng của biến div_precision_increment:

~~~sql
SHOW SESSION VARIABLES LIKE 'div_precision_increment';
~~~

Giá trị mặc định thường là 4. Nó điều khiển số chữ số thập phân được cộng thêm vào scale của kết quả chia; nếu nghiệp vụ cần độ chính xác cụ thể, hãy ép kiểu hoặc làm tròn có chủ đích thay vì dựa vào mặc định.

Ví dụ:

~~~sql
SELECT
    10 / 3 AS default_division,
    CAST(10 / 3 AS DECIMAL(12, 4)) AS fixed_scale,
    ROUND(10 / 3, 2) AS rounded_value;
~~~

ROUND() làm tròn kết quả theo số chữ số được chỉ định. Không nên nhầm việc hiển thị ít chữ số với việc lưu trữ chính xác số thập phân.

## 3. Tràn số và giá trị ngoài phạm vi

### 3.1. Miền giá trị của kiểu số nguyên

Kiểu số nguyên có giới hạn cụ thể. Thuộc tính UNSIGNED chuyển miền giá trị sang không âm và tăng giới hạn dương.

| Kiểu | Signed nhỏ nhất | Signed lớn nhất | Unsigned lớn nhất |
|---|---:|---:|---:|
| TINYINT | -128 | 127 | 255 |
| SMALLINT | -32.768 | 32.767 | 65.535 |
| MEDIUMINT | -8.388.608 | 8.388.607 | 16.777.215 |
| INT | -2.147.483.648 | 2.147.483.647 | 4.294.967.295 |
| BIGINT | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | 18.446.744.073.709.551.615 |

Nếu giá trị được gán vượt miền cột đích, MySQL xử lý khác nhau theo strict mode, IGNORE và ngữ cảnh chuyển đổi.

### 3.2. Strict mode và cột số

Với bảng InnoDB, strict mode thường khiến INSERT hoặc UPDATE có giá trị ngoài phạm vi bị từ chối thay vì âm thầm điều chỉnh. Khi strict mode không được bật, MySQL có thể ép giá trị về giới hạn gần nhất và phát warning.

Ví dụ:

~~~sql
CREATE TEMPORARY TABLE tinyint_demo (
    value TINYINT NOT NULL
);

INSERT INTO tinyint_demo (value) VALUES (200);
~~~

200 lớn hơn giới hạn của TINYINT signed là 127. Trong strict mode, INSERT thường thất bại với lỗi out of range. Khi không strict, server có thể lưu giá trị biên 127 và phát warning. Hãy kiểm tra giá trị thực tế thay vì giả định rằng dữ liệu đã được lưu nguyên vẹn.

Với câu lệnh nhiều hàng, strict mode và storage engine cũng ảnh hưởng phạm vi rollback. InnoDB là transactional engine nên khi một hàng khiến câu lệnh thất bại, toàn bộ statement có thể được rollback. Với storage engine không transactional, một phần hàng có thể đã được ghi trước khi lỗi xảy ra, tùy strict mode và thứ tự xử lý.

### 3.3. IGNORE thay đổi cách báo lỗi

INSERT IGNORE và UPDATE IGNORE có thể chuyển một số lỗi dữ liệu thành warning để câu lệnh tiếp tục. Điều này không có nghĩa giá trị ngoài phạm vi được lưu nguyên trạng. MySQL có thể điều chỉnh giá trị hoặc dùng NULL/default tùy tình huống.

Ví dụ:

~~~sql
INSERT IGNORE INTO tinyint_demo (value)
VALUES (200);

SHOW WARNINGS;

SELECT value FROM tinyint_demo;
~~~

Hãy dùng IGNORE chỉ khi nghiệp vụ chấp nhận chính sách bỏ qua hoặc điều chỉnh dữ liệu. Không dùng nó để che lỗi xác thực đầu vào hoặc làm cho migration “chạy qua” mà không kiểm tra kết quả.

## 4. Tràn số trong biểu thức tính toán

Tràn số có thể xuất hiện ngay trong biểu thức SELECT, trước khi kết quả được gán vào cột. Ví dụ, phép toán trên giá trị UNSIGNED có thể tạo kết quả âm hoặc vượt miền biểu diễn.

~~~sql
SELECT CAST(0 AS UNSIGNED) - 1;
~~~

Mặc định, phép trừ có toán hạng UNSIGNED có thể được xử lý theo số học unsigned. Nếu kết quả âm, MySQL có thể báo lỗi giá trị unsigned ngoài phạm vi.

SQL mode NO_UNSIGNED_SUBTRACTION thay đổi hành vi phép trừ: kết quả phép trừ có toán hạng unsigned được xử lý theo hướng signed để có thể biểu diễn số âm khi phù hợp.

~~~sql
SET SESSION sql_mode =
    CONCAT_WS(',', @@SESSION.sql_mode, 'NO_UNSIGNED_SUBTRACTION');

SELECT CAST(0 AS UNSIGNED) - 1;
~~~

Đoạn SET trên bổ sung mode vào danh sách hiện tại của session. Nếu session đã có mode này, chuỗi có thể chứa tên lặp; khi cấu hình sản xuất, hãy quản lý danh sách mode một cách rõ ràng.

NO_UNSIGNED_SUBTRACTION ảnh hưởng đến ngữ nghĩa phép trừ, không làm cột UNSIGNED chấp nhận số âm. Nếu kết quả âm được ghi vào cột UNSIGNED, thao tác vẫn có thể thất bại hoặc bị điều chỉnh tùy SQL mode.

### 4.1. Tràn số trong DECIMAL

DECIMAL dùng số học thập phân chính xác và phù hợp với dữ liệu tiền tệ. MySQL hỗ trợ precision tối đa 65 chữ số và scale tối đa 30 chữ số. Khi kết quả hoặc giá trị gán vượt precision/scale của kiểu đích, server có thể báo lỗi hoặc phát warning và điều chỉnh tùy strict mode, phép toán và ngữ cảnh.

Ví dụ:

~~~sql
CREATE TEMPORARY TABLE decimal_demo (
    amount DECIMAL(5, 2) NOT NULL
);

INSERT INTO decimal_demo (amount)
VALUES (12345.67);
~~~

DECIMAL(5,2) chỉ có tổng cộng 5 chữ số, trong đó 2 chữ số sau dấu thập phân; phần nguyên tối đa có 3 chữ số. Giá trị 12345.67 không thể biểu diễn trong cột này.

Khi thiết kế cột tiền tệ, cần tính phạm vi giá trị tối đa và số chữ số thập phân theo nghiệp vụ. Không nên chọn DECIMAL(10,2) chỉ vì đó là một ví dụ phổ biến.

### 4.2. FLOAT và DOUBLE

FLOAT và DOUBLE dùng biểu diễn dấu phẩy động gần đúng. Chúng có miền giá trị và đặc tính làm tròn khác DECIMAL. Các phép toán có thể tạo sai số biểu diễn dù không xảy ra overflow.

Ví dụ:

~~~sql
SELECT
    0.1 + 0.2 AS approximate_result,
    CAST(0.1 AS DECIMAL(3, 1))
      + CAST(0.2 AS DECIMAL(3, 1)) AS decimal_result;
~~~

Khi cần số tiền, tỷ lệ cần quy tắc làm tròn rõ ràng hoặc phép so sánh chính xác theo chữ số thập phân, ưu tiên DECIMAL. FLOAT/DOUBLE phù hợp hơn với dữ liệu khoa học hoặc phép tính chấp nhận sai số gần đúng.

## 5. Phép toán trên số UNSIGNED

UNSIGNED hữu ích cho số đếm, mã định danh và số lượng không âm. Tuy nhiên, phép toán trên UNSIGNED có thể gây bất ngờ khi kết quả trung gian cần âm.

Ví dụ tồn kho:

~~~sql
CREATE TEMPORARY TABLE inventory_demo (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity   INT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id)
);

INSERT INTO inventory_demo VALUES (1, 3);

UPDATE inventory_demo
SET quantity = quantity - 5
WHERE product_id = 1;
~~~

Nếu phép trừ tạo kết quả âm, MySQL có thể báo lỗi out of range. Không nên trông chờ cột UNSIGNED tự chuyển số âm thành 0.

Một cách bảo vệ nghiệp vụ là đặt điều kiện ngay trong UPDATE:

~~~sql
UPDATE inventory_demo
SET quantity = quantity - 5
WHERE product_id = 1
  AND quantity >= 5;
~~~

Sau UPDATE, ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu bằng 0, có thể không tìm thấy sản phẩm hoặc không đủ tồn kho; cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

Một cách khác là khóa và kiểm tra tồn kho trong transaction, sau đó cập nhật có điều kiện. Điều kiện trong UPDATE vẫn hữu ích vì nó thực hiện kiểm tra và thay đổi trong cùng một statement, giảm nguy cơ race condition so với đọc số lượng rồi cập nhật vô điều kiện.

## 6. Dữ liệu ngày giờ không hợp lệ

MySQL kiểm tra giá trị ngày giờ theo kiểu dữ liệu, SQL mode và ngữ cảnh. Một chuỗi có hình dạng giống ngày không nhất thiết là ngày hợp lệ trên lịch.

Ví dụ:

- 2026-02-30: tháng và ngày nằm trong giới hạn số học nhưng ngày không tồn tại trong lịch.
- 2026-13-01: tháng nằm ngoài phạm vi.
- 2026-00-15: tháng bằng 0.
- 0000-00-00: zero date.
- 2026-04-31: tháng 4 không có ngày 31.

Các trường hợp này không hoàn toàn giống nhau. SQL mode có thể cho phép một số dạng ngày không đầy đủ hoặc không hợp lệ, nhưng ứng dụng không nên dùng những giá trị đó làm dữ liệu nghiệp vụ bình thường.

### 6.1. Strict mode

Hai mode strict thường gặp:

- **STRICT_TRANS_TABLES**: bật kiểm tra nghiêm ngặt cho các bảng transactional như InnoDB; với bảng nontransactional, cách xử lý statement nhiều hàng có thể có giới hạn.
- **STRICT_ALL_TABLES**: áp dụng strict behavior rộng hơn cho mọi storage engine; với engine nontransactional, một phần dữ liệu vẫn có thể đã được ghi trước khi lỗi xảy ra.

Trong strict mode, giá trị ngày giờ không hợp lệ trong INSERT hoặc UPDATE thường khiến statement thất bại. Nếu không strict, server có thể điều chỉnh giá trị và phát warning. Kết quả cụ thể còn phụ thuộc mode ngày giờ và thao tác đang thực hiện.

Kiểm tra:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### 6.2. NO_ZERO_DATE và NO_ZERO_IN_DATE

Hai mode liên quan đến zero date:

- **NO_ZERO_DATE** kiểm soát việc chấp nhận toàn bộ giá trị 0000-00-00.
- **NO_ZERO_IN_DATE** kiểm soát giá trị có năm khác 0 nhưng tháng hoặc ngày bằng 0, chẳng hạn 2026-00-15.

Khi kết hợp với strict mode, các giá trị bị cấm thường gây lỗi trong thao tác ghi. Nếu strict mode không bật, server có thể chỉ phát warning và điều chỉnh dữ liệu.

Trong MySQL 8.0, NO_ZERO_DATE và NO_ZERO_IN_DATE đã được đánh dấu deprecated. Hành vi chính xác còn phụ thuộc phiên bản và SQL mode đang dùng. Không nên xây dựng thiết kế mới dựa vào việc bật/tắt riêng hai mode này để cho phép ngày không hợp lệ.

### 6.3. ALLOW_INVALID_DATES

ALLOW_INVALID_DATES nới lỏng kiểm tra đầy đủ tính hợp lệ của ngày đối với DATE và DATETIME. MySQL vẫn kiểm tra tháng trong khoảng 1–12 và ngày trong khoảng 1–31, nhưng không kiểm tra đầy đủ sự kết hợp tháng/ngày theo lịch.

Ví dụ, với mode này, một giá trị như 2026-02-30 có thể được chấp nhận cho DATE hoặc DATETIME dù ngày đó không tồn tại trong lịch. Mode này không áp dụng cho TIMESTAMP; TIMESTAMP vẫn yêu cầu giá trị ngày hợp lệ.

ALLOW_INVALID_DATES thường không phù hợp với ứng dụng nghiệp vụ. Nó có thể hữu ích trong một số quy trình nhập dữ liệu cần giữ nguyên thành phần ngày đã nhận, nhưng phải có bước xác thực và làm sạch riêng trước khi dùng dữ liệu.

### 6.4. Zero date không phải NULL

Zero date 0000-00-00 là một giá trị đặc biệt, không giống NULL:

- NULL biểu thị không có giá trị hoặc chưa biết theo ngữ nghĩa cột.
- Zero date là một giá trị ngày đặc biệt có thể bị cấm bởi SQL mode.
- Các phép so sánh, hàm ngày giờ và chuyển đổi có thể xử lý hai trường hợp khác nhau.

Nếu ngày chưa biết, dùng NULL nếu nghiệp vụ cho phép. Nếu cần phân biệt “chưa nhập”, “không áp dụng” và “đang chờ xác nhận”, hãy dùng trạng thái nghiệp vụ riêng.

## 7. Giá trị ngày giờ ngoài miền kiểu dữ liệu

Ngoài ngày không tồn tại trên lịch, giá trị còn có thể vượt miền của kiểu dữ liệu:

| Kiểu | Miền thông thường trong MySQL 5.7, 8.0 và 8.4 |
|---|---|
| DATE | 1000-01-01 đến 9999-12-31 |
| DATETIME | 1000-01-01 00:00:00 đến 9999-12-31 23:59:59 |
| TIMESTAMP | 1970-01-01 00:00:01 đến 2038-01-19 03:14:07 UTC |

Ví dụ:

~~~sql
CREATE TEMPORARY TABLE temporal_demo (
    date_value      DATE,
    datetime_value  DATETIME,
    timestamp_value TIMESTAMP
);

INSERT INTO temporal_demo (date_value)
VALUES ('10000-01-01');
~~~

Giá trị năm 10000 vượt miền DATE. Tương tự, TIMESTAMP không thể lưu một thời điểm vượt giới hạn trên của kiểu, dù DATETIME có thể biểu diễn năm đó trong miền hỗ trợ của nó.

Khi nhận dữ liệu từ API, hãy xác thực phạm vi ngày trước khi gửi xuống database. Không nên dùng TIMESTAMP cho dữ liệu tương lai rất xa như lịch bảo trì dài hạn, ngày đáo hạn hoặc sự kiện có thể sau năm 2038.

## 8. Cách SQL mode ảnh hưởng đến kết quả ghi

Một cách tư duy hữu ích là phân biệt ba kết quả:

1. **Statement thành công, không warning:** giá trị được chấp nhận theo quy tắc hiện tại.
2. **Statement thành công, có warning:** server đã điều chỉnh hoặc chấp nhận giá trị theo một chế độ cho phép; phải đọc warning và dữ liệu thực tế.
3. **Statement thất bại:** server từ chối thao tác. Với InnoDB, statement bị lỗi được rollback; transaction bao quanh có thể vẫn mở và ứng dụng cần quyết định rollback transaction.

Ví dụ kiểm tra warning:

~~~sql
INSERT IGNORE INTO tinyint_demo (value)
VALUES (200);

SHOW WARNINGS;

SELECT value
FROM tinyint_demo
ORDER BY value;
~~~

Không nên chỉ kiểm tra mã trả về của câu lệnh ở tầng ứng dụng rồi bỏ qua warning. Nếu server chấp nhận dữ liệu sau khi điều chỉnh, ứng dụng có thể lưu một giá trị khác với đầu vào ban đầu.

### 8.1. IGNORE không phải chế độ strict an toàn

IGNORE thay đổi cách một số lỗi được báo cáo, thường chuyển error thành warning và cho phép statement tiếp tục. Điều này hữu ích trong các quy trình import có chủ đích bỏ qua một số hàng, nhưng có thể nguy hiểm nếu dùng cho thao tác nghiệp vụ cần bảo đảm chính xác.

Với dữ liệu số hoặc ngày giờ, hãy xác minh:

- Giá trị nào được lưu sau khi điều chỉnh?
- Hàng nào bị bỏ qua?
- Warning nào được phát ra?
- Có làm mất dữ liệu hoặc thay đổi ý nghĩa nghiệp vụ không?

Nếu không có chính sách xử lý warning rõ ràng, hãy tránh IGNORE cho các thao tác ghi quan trọng.

## 9. Quan sát lỗi và warning

Khi kiểm tra hành vi SQL mode, dùng các lệnh sau ngay trong cùng session:

~~~sql
SELECT @@SESSION.sql_mode;
SELECT @@warning_count;
SHOW WARNINGS;
SHOW ERRORS;
~~~

SHOW WARNINGS liệt kê warning, note và error gần nhất còn được lưu cho session. SHOW ERRORS chỉ hiển thị error. Các lệnh này hữu ích trong SQL client và kiểm thử thủ công.

Trong ứng dụng, driver thường cung cấp SQLState, vendor error code và warning chain. Hãy ghi nhận các thông tin đó cùng câu lệnh và phiên bản MySQL khi điều tra sự cố. Không ghi dữ liệu nhạy cảm hoặc thông tin bí mật trong log.

### 9.1. Kiểm tra cấu hình giữa các môi trường

Chạy cùng truy vấn trên development, test và production:

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone;
~~~

Nếu SQL mode khác nhau, cùng một dữ liệu đầu vào có thể bị từ chối ở môi trường này nhưng được điều chỉnh ở môi trường khác. Hãy đưa SQL mode vào cấu hình triển khai và kiểm thử migration với cấu hình gần production.

## 10. Ví dụ kiểm thử tổng hợp

Ví dụ sau tạo các bảng tạm để kiểm tra phép chia, overflow và ngày không hợp lệ. Chạy trong session kiểm thử:

~~~sql
CREATE TEMPORARY TABLE numeric_check (
    id       INT NOT NULL AUTO_INCREMENT,
    amount   TINYINT NOT NULL,
    ratio    DECIMAL(8, 4) NULL,
    PRIMARY KEY (id)
);

CREATE TEMPORARY TABLE date_check (
    id         INT NOT NULL AUTO_INCREMENT,
    event_date DATE NULL,
    event_time DATETIME NULL,
    PRIMARY KEY (id)
);

-- Kiểm tra phép chia cho 0
SELECT 10 / 0;
SHOW WARNINGS;

-- Kiểm tra chia an toàn
SELECT 10 / NULLIF(0, 0) AS safe_ratio;

-- Kiểm tra giá trị số vượt miền TINYINT
INSERT INTO numeric_check (amount) VALUES (200);
SHOW WARNINGS;

-- Kiểm tra ngày không tồn tại
INSERT INTO date_check (event_date) VALUES ('2026-02-30');
SHOW WARNINGS;

-- Xem dữ liệu thực tế đã được lưu
SELECT * FROM numeric_check;
SELECT * FROM date_check;
~~~

Kết quả có thể khác theo SQL mode. Để so sánh strict và non-strict, hãy chạy trên hai session kiểm thử riêng, thiết lập SQL mode có chủ đích và ghi lại cả lỗi, warning lẫn dữ liệu được lưu. Không dùng bảng production để thử các giá trị biên hoặc dữ liệu không hợp lệ.

## 11. Quy trình thiết kế và xử lý dữ liệu an toàn

Khi xây dựng tính năng có phép tính hoặc dữ liệu ngày giờ, hãy làm theo quy trình:

1. Xác định miền giá trị nghiệp vụ trước khi chọn kiểu cột.
2. Chọn kiểu số đủ phạm vi; dùng DECIMAL cho giá trị cần độ chính xác thập phân.
3. Kiểm tra mẫu số trước phép chia hoặc dùng NULLIF để xử lý mẫu số bằng 0.
4. Kiểm tra phép toán trên UNSIGNED, đặc biệt là phép trừ có thể tạo số âm.
5. Chọn DATE, DATETIME hoặc TIMESTAMP theo ý nghĩa ngày lịch, giờ địa phương hay instant.
6. Bật strict mode phù hợp và kiểm tra SQL mode thực tế của từng session.
7. Không dùng IGNORE để che lỗi dữ liệu nếu chưa có chính sách rõ ràng.
8. Kiểm tra warning ngay sau thao tác và xác minh giá trị thực tế được lưu.
9. Kiểm thử giá trị sát giới hạn kiểu dữ liệu, ngày không hợp lệ và dữ liệu ngoài miền.
10. Đồng bộ SQL mode giữa các môi trường và kiểm tra hành vi sau khi nâng cấp MySQL.

## 12. Những nhầm lẫn thường gặp

**“Chia cho 0 luôn làm toàn bộ transaction rollback.”** Không nhất thiết. Kết quả phụ thuộc câu lệnh, SQL mode, IGNORE và kiểu dữ liệu đích. Một SELECT có thể chỉ trả NULL và warning; một INSERT hoặc UPDATE có thể thất bại trong strict mode.

**“Nếu INSERT thành công thì giá trị đã được lưu đúng như đầu vào.”** Không. Trong non-strict mode hoặc với IGNORE, MySQL có thể điều chỉnh dữ liệu và phát warning.

**“UNSIGNED chỉ là cách biểu diễn số dương lớn hơn.”** Nó còn ảnh hưởng ngữ nghĩa phép toán, đặc biệt là phép trừ có thể tạo kết quả âm.

**“DECIMAL không bao giờ overflow.”** DECIMAL là số thập phân chính xác trong giới hạn precision và scale hữu hạn. Giá trị hoặc kết quả vượt giới hạn vẫn có thể bị từ chối hoặc điều chỉnh.

**“ALLOW_INVALID_DATES làm mọi kiểu ngày giờ chấp nhận mọi chuỗi.”** Không. Mode này chỉ nới lỏng một phần kiểm tra cho DATE và DATETIME; tháng và ngày vẫn phải nằm trong phạm vi số học, còn TIMESTAMP vẫn cần ngày hợp lệ.

**“Zero date giống NULL.”** Không. NULL biểu thị không có giá trị; zero date là giá trị ngày đặc biệt và có thể bị SQL mode cấm.

**“SQL mode GLOBAL thay đổi ngay mọi kết nối.”** Không. Các session đang mở giữ giá trị SESSION riêng cho đến khi được thay đổi.

## Kết luận

Phép chia cho 0, tràn số và dữ liệu ngày giờ không hợp lệ đều chịu ảnh hưởng của kiểu dữ liệu, SQL mode và ngữ cảnh câu lệnh. SELECT có thể trả NULL cùng warning; thao tác ghi trong strict mode có thể bị từ chối; IGNORE có thể chuyển một số lỗi thành warning và làm dữ liệu được điều chỉnh. Phép toán trên UNSIGNED cần được chú ý vì kết quả trung gian có thể không biểu diễn được số âm.

Hãy kiểm tra SQL mode của đúng session, xác thực đầu vào, chọn kiểu dữ liệu đủ miền, bảo vệ phép chia bằng NULLIF hoặc CASE và đọc warning sau thao tác. Kiểm thử cả kết quả, lỗi và dữ liệu thực tế được lưu giúp ứng dụng giữ đúng ngữ nghĩa nghiệp vụ trên các môi trường MySQL khác nhau.

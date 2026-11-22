# CAST, CONVERT và kiểm soát chuyển đổi tường minh

Trong MySQL, một biểu thức có thể chứa nhiều kiểu dữ liệu khác nhau: số, chuỗi, ngày giờ và giá trị `NULL`. Khi các kiểu không giống nhau, MySQL đôi khi tự chuyển đổi (implicit conversion) để thực hiện phép tính hoặc so sánh. Việc chuyển đổi ngầm tiện trong câu SQL ngắn, nhưng cũng có thể làm sai ý nghĩa so sánh, phát sinh warning hoặc khiến truy vấn khó tận dụng index.

`CAST()` và `CONVERT()` cho phép người viết chỉ rõ kiểu dữ liệu hoặc character set cần dùng. Trong module **DATABASE_MYSQL**, cần biết khi nào nên ép kiểu, khi nào cần chuyển mã ký tự, cách kiểm tra warning và cách giữ điều kiện truy vấn thân thiện với index.

## 1. Chuyển đổi kiểu dữ liệu là gì?

Chuyển đổi kiểu dữ liệu là biến một giá trị từ kiểu này sang kiểu khác để phù hợp với phép tính, so sánh, lưu trữ hoặc định dạng kết quả.

Ví dụ:

- Chuỗi `'125.50'` được chuyển thành `DECIMAL` để tính tiền.
- Chuỗi ngày ISO `'2026-11-19'` được chuyển thành `DATE`.
- Số `123` được chuyển thành chuỗi `'123'` để ghép với nội dung văn bản.
- Một chuỗi được chuyển sang character set `utf8mb4` để xử lý Unicode thống nhất.

MySQL có thể tự chuyển kiểu trong nhiều biểu thức. Ví dụ, khi so sánh một cột số với literal dạng chuỗi, server có thể chuyển chuỗi sang số. Nếu không hiểu quy tắc này, câu lệnh vẫn có thể chạy nhưng cho kết quả bất ngờ.

Chuyển đổi tường minh nghĩa là chỉ rõ phép chuyển đổi ngay trong SQL:

```sql
SELECT CAST('125.50' AS DECIMAL(10,2)) AS amount;
SELECT CONVERT('2026-11-19', DATE) AS order_date;
```

Ép kiểu làm rõ ý định, nhưng không tự xác thực dữ liệu nguồn. Nếu đầu vào không hợp lệ hoặc vượt miền đích, kết quả vẫn có thể bị cắt, làm tròn, trả giá trị đặc biệt hoặc phát warning tùy kiểu và ngữ cảnh.

## 2. CAST và CONVERT có những dạng nào?

MySQL cung cấp hai cách chuyển đổi kiểu tương đương:

```sql
CAST(expression AS target_type)
CONVERT(expression, target_type)
```

Ví dụ hai câu sau có cùng mục đích:

```sql
SELECT CAST('42' AS UNSIGNED) AS quantity;
SELECT CONVERT('42', UNSIGNED) AS quantity;
```

`CAST()` thường được dùng khi muốn nhấn mạnh đây là phép ép kiểu. `CONVERT(expr, type)` là cú pháp tương đương và hữu ích khi đã quen với tên hàm `CONVERT`.

`CONVERT()` còn có một dạng khác để chuyển character set:

```sql
CONVERT(expression USING target_character_set)
```

Ví dụ:

```sql
SELECT CONVERT('Tiếng Việt' USING utf8mb4);
```

Hai dạng `CONVERT()` không có cùng mục tiêu:

| Cú pháp | Mục đích |
|---|---|
| `CONVERT(expr, type)` | Chuyển giá trị sang kiểu SQL đích |
| `CAST(expr AS type)` | Chuyển giá trị sang kiểu SQL đích |
| `CONVERT(expr USING charset)` | Chuyển chuỗi sang character set đích |

Không viết `CONVERT(expr, utf8mb4)` để chuyển character set; hãy dùng từ khóa `USING`.

## 3. Các kiểu đích thường dùng

Trong các bài thực hành, những kiểu đích thường gặp gồm:

| Kiểu đích | Mục đích | Ví dụ |
|---|---|---|
| `SIGNED` / `UNSIGNED` | Chuyển thành số nguyên có dấu/không dấu | `CAST('120' AS UNSIGNED)` |
| `DECIMAL(M,D)` | Chuyển thành số thập phân chính xác với precision/scale chỉ định | `CAST('123.45' AS DECIMAL(10,2))` |
| `CHAR` | Chuyển thành chuỗi ký tự | `CAST(123 AS CHAR)` |
| `BINARY` | Chuyển thành chuỗi byte để xử lý theo dạng nhị phân | `CAST('ABC' AS BINARY)` |
| `DATE` | Chuyển thành ngày lịch | `CAST('2026-11-19' AS DATE)` |
| `TIME` | Chuyển thành giờ hoặc lượng thời gian | `CAST('14:30:00' AS TIME)` |
| `DATETIME` | Chuyển thành ngày giờ không gắn timezone | `CAST('2026-11-19 14:30:00' AS DATETIME)` |
| `JSON` | Chuyển văn bản JSON hợp lệ thành giá trị JSON | `CAST('{"active": true}' AS JSON)` |

Có thể chỉ định character set khi ép sang `CHAR`:

```sql
CAST(expression AS CHAR CHARACTER SET utf8mb4)
```

Nếu kết quả cần một collation cụ thể, có thể chỉ định thêm `COLLATE`:

```sql
SELECT
    CAST('Nguyen' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci AS normalized_name;
```

Kiểu đích và các biến thể cú pháp được hỗ trợ có thể phụ thuộc phiên bản MySQL. Hãy kiểm tra tài liệu đúng phiên bản trước khi dùng kiểu ít phổ biến trong migration.

## 4. Chuyển đổi chuỗi sang số

Khi dữ liệu được import từ CSV hoặc nhận từ API, giá trị số đôi khi đang ở dạng chuỗi. Có thể chuyển kiểu rõ ràng trước khi tính toán:

```sql
SELECT
    CAST('125.50' AS DECIMAL(10,2)) AS unit_price,
    CAST('3' AS UNSIGNED) AS quantity,
    CAST('125.50' AS DECIMAL(10,2)) *
        CAST('3' AS UNSIGNED) AS line_total;
```

Kết quả `line_total` là `376.50`. Với tiền tệ, nên dùng `DECIMAL` thay cho `FLOAT`/`DOUBLE` để tránh sai số biểu diễn nhị phân của số thực.

### Chuyển đổi không đồng nghĩa với kiểm tra hợp lệ

Ví dụ đầu vào có ký tự không phải số:

```sql
SELECT CAST('12abc' AS UNSIGNED) AS parsed_value;
SHOW WARNINGS;
```

MySQL có thể chuyển phần số hợp lệ ở đầu chuỗi và phát warning về phần dữ liệu không hợp lệ. Với chuỗi hoàn toàn không phải số, phép chuyển đổi có thể trả về 0 kèm warning. Hành vi cụ thể còn phụ thuộc biểu thức, kiểu đích và phiên bản.

Vì vậy, không dùng `CAST()` như một bộ kiểm tra dữ liệu đầu vào. Trước khi ghi dữ liệu, ứng dụng nên xác thực chuỗi theo định dạng nghiệp vụ; sau câu SQL, kiểm tra warning nếu quy trình cần phát hiện chuyển đổi không sạch.

### Làm tròn và mất độ chính xác

Khi chuyển một giá trị sang `DECIMAL(M,D)`, MySQL áp dụng scale `D`. Phần thập phân vượt quá scale có thể được làm tròn:

```sql
SELECT CAST('12.345' AS DECIMAL(5,2)) AS rounded_value;
```

Kết quả thông thường là `12.35`. Nếu giá trị vượt precision hoặc miền kiểu đích, MySQL có thể báo lỗi hoặc warning tùy ngữ cảnh và SQL mode. Luôn chọn `M` và `D` theo giới hạn nghiệp vụ, không chỉ theo một vài mẫu dữ liệu.

## 5. Chuyển đổi số sang chuỗi

Khi cần ghép số với văn bản hoặc định dạng kết quả, chuyển số thành chuỗi tường minh:

```sql
SELECT CONCAT(
    'Order #',
    CAST(order_id AS CHAR)
) AS order_label
FROM orders;
```

`CAST(order_id AS CHAR)` làm rõ rằng `order_id` được chuyển sang chuỗi trước khi ghép. Với dữ liệu trình bày, có thể định dạng thêm bằng hàm phù hợp hoặc ở tầng Java.

Không chuyển số thành chuỗi trong cột lưu trữ chỉ để giữ số 0 đầu nếu giá trị đó thực chất là đại lượng số. Nếu `00125` là mã định danh, không phải số để tính toán, hãy lưu nó bằng `CHAR`/`VARCHAR` ngay từ đầu.

## 6. Chuyển đổi ngày giờ

`CAST()` có thể chuyển chuỗi theo định dạng ngày giờ MySQL nhận diện:

```sql
SELECT
    CAST('2026-11-19' AS DATE) AS order_date,
    CAST('14:30:00' AS TIME) AS opening_time,
    CAST('2026-11-19 14:30:00' AS DATETIME) AS scheduled_at;
```

Nếu chuỗi nguồn dùng định dạng riêng như `19/11/2026`, hãy dùng `STR_TO_DATE()` để chỉ rõ mẫu phân tích:

```sql
SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS order_date;
```

Không giả định `CAST('19/11/2026' AS DATE)` sẽ hiểu đúng thứ tự ngày/tháng. Dùng định dạng ISO `YYYY-MM-DD` cho dữ liệu trao đổi nếu có thể; với định dạng khác, chỉ rõ format bằng `STR_TO_DATE()`.

`CAST(... AS DATETIME)` không tự gắn timezone vào giá trị. Nếu nguồn là một instant có offset, ứng dụng cần phân tích offset đúng cách và quy đổi theo quy ước lưu trữ của hệ thống. Đừng bỏ offset rồi xem chuỗi ngày giờ còn lại như UTC một cách mặc định.

## 7. CONVERT và chuyển character set

Chuyển character set là chuyển cách mã hóa văn bản giữa các bộ ký tự. Ví dụ:

```sql
SELECT CONVERT('Tiếng Việt 😀' USING utf8mb4) AS unicode_text;
```

`CONVERT(... USING utf8mb4)` chuyển chuỗi sang character set `utf8mb4`. Kết quả collation được xác định theo mặc định của character set đích, trừ khi tiếp tục chỉ định collation.

Có thể kiểm tra character set và collation của biểu thức:

```sql
SELECT
    CHARSET(CONVERT('Tiếng Việt' USING utf8mb4)) AS result_charset,
    COLLATION(CONVERT('Tiếng Việt' USING utf8mb4)) AS result_collation;
```

Hoặc ép kiểu ký tự và chỉ định charset ngay trong `CAST`:

```sql
SELECT CAST('Tiếng Việt' AS CHAR CHARACTER SET utf8mb4);
```

### Chuyển character set không sửa được byte đã hỏng

`CONVERT(... USING charset)` giả định MySQL biết character set hiện tại của biểu thức và chuyển ký tự sang charset đích. Nếu dữ liệu ban đầu đã được ghi bằng byte sai nhưng metadata khai báo sai charset, việc chuyển đổi có thể giữ nguyên nội dung sai hoặc làm hỏng thêm. Trước khi sửa dữ liệu mojibake, cần xác định byte gốc, charset nguồn thực tế và charset đích.

Nếu character set đích không biểu diễn được một số ký tự nguồn, chuyển đổi có thể làm mất thông tin hoặc phát warning. `utf8mb4` là lựa chọn phù hợp cho Unicode đầy đủ trong phần lớn ứng dụng mới; không chuyển sang một charset hẹp hơn nếu không có yêu cầu tương thích rõ ràng.

## 8. Phân biệt CAST với COLLATE

`CAST()` đổi kiểu dữ liệu. `COLLATE` chọn quy tắc so sánh cho biểu thức chuỗi. Hai thao tác có thể được kết hợp nhưng không thay thế nhau.

```sql
SELECT
    CAST('café' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci =
    CAST('cafe' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci AS equal_ignoring_accent;
```

Với collation `utf8mb4_0900_ai_ci`, hai chuỗi được so sánh không phân biệt dấu và hoa/thường. Nếu dùng collation phân biệt dấu, kết quả có thể khác.

`COLLATE` chỉ áp dụng cho biểu thức có character set tương thích. Nếu hai biểu thức dùng charset khác nhau, hãy xử lý character set trước rồi chọn collation tương ứng. Không dùng `COLLATE` để chuyển byte từ charset này sang charset khác.

## 9. NULL trong phép chuyển đổi

Chuyển đổi không làm `NULL` trở thành một giá trị mặc định. Ví dụ:

```sql
SELECT
    CAST(NULL AS DECIMAL(10,2)) AS amount,
    CONVERT(NULL, CHAR) AS label;
```

Cả hai biểu thức đều trả về `NULL`. Nếu cần thay giá trị thiếu bằng một giá trị khác, hãy thể hiện riêng quy tắc đó bằng `COALESCE()` hoặc `IFNULL()`:

```sql
SELECT COALESCE(CAST(NULL AS DECIMAL(10,2)), 0.00) AS amount;
```

Kết quả là `0.00`, nhưng đây là hành vi của `COALESCE()`, không phải của `CAST()`. Khi so sánh, `NULL = NULL` không trả về true; hãy dùng `IS NULL` hoặc `IS NOT NULL` để kiểm tra giá trị rỗng.

## 10. Chuyển đổi ngầm và những kết quả dễ gây bất ngờ

MySQL tự chuyển kiểu trong một số phép so sánh và biểu thức. Ví dụ:

```sql
SELECT
    '00123' = 123 AS numeric_comparison,
    '00123' = '123' AS string_comparison;
```

Trong ngữ cảnh so sánh chuỗi với số, MySQL có thể chuyển chuỗi sang số; do đó `'00123' = 123` có thể cho kết quả đúng. Trong so sánh chuỗi với chuỗi, các ký tự được so sánh theo collation và `'00123'` khác `'123'`.

Điều này đặc biệt nguy hiểm với mã định danh. Mã khách hàng `'00123'` và `'123'` có thể là hai mã khác nhau về nghiệp vụ, nhưng nếu so sánh trong ngữ cảnh số, chúng có thể bị xem là cùng giá trị.

### Tránh trộn kiểu không chủ ý

Không nên viết:

```sql
SELECT *
FROM external_codes
WHERE code = 123;
```

Nếu `code` là `VARCHAR` và chứa mã định danh, hãy so sánh với chuỗi:

```sql
SELECT *
FROM external_codes
WHERE code = '00123';
```

Nếu đầu vào là tham số bind và cần ép kiểu, hãy ép tham số thay vì bọc cột được đánh index:

```sql
SELECT *
FROM external_codes
WHERE code = CAST(? AS CHAR);
```

Việc giữ kiểu của cột và giá trị so sánh tương thích giúp ngữ nghĩa rõ ràng và tạo điều kiện để MySQL sử dụng index.

## 11. CAST/CONVERT và khả năng sử dụng index

Một nguyên tắc tối ưu quan trọng là tránh áp dụng hàm hoặc phép ép kiểu lên cột được đánh index trong điều kiện lọc, trừ khi có functional index phù hợp và đã kiểm tra kế hoạch.

Giả sử `orders.order_id` có index:

```sql
-- Có thể làm giảm khả năng dùng index range trên order_id
SELECT *
FROM orders
WHERE CAST(order_id AS CHAR) = '105';
```

Thay vào đó, chuyển giá trị đầu vào sang kiểu của cột:

```sql
SELECT *
FROM orders
WHERE order_id = CAST('105' AS UNSIGNED);
```

Với truy vấn thực tế, nên bind parameter có kiểu phù hợp từ JDBC; không cần CAST nếu driver đã gửi đúng kiểu.

Ví dụ lọc theo thời gian, giữ nguyên cột `created_at`:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= CAST(? AS DATETIME)
  AND created_at <  CAST(? AS DATETIME);
```

Nếu `created_at` có index, cách viết này giữ cột ở dạng trực tiếp trong điều kiện range. Tuy vậy, vẫn cần kiểm tra `EXPLAIN` vì khả năng dùng index phụ thuộc cấu trúc truy vấn, kiểu tham số và thống kê.

## 12. SQL mode, warning và dữ liệu không hợp lệ

Chuyển đổi tường minh không bỏ qua các quy tắc kiểm tra dữ liệu của MySQL. SQL mode có thể ảnh hưởng cách server xử lý dữ liệu không hợp lệ trong `INSERT`, `UPDATE` và một số biểu thức.

Kiểm tra mode của session:

```sql
SELECT @@SESSION.sql_mode;
```

Các mode strict như `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES` giúp từ chối nhiều giá trị không hợp lệ khi ghi dữ liệu thay vì tự điều chỉnh trong một số trường hợp. Tuy nhiên, không nên suy luận rằng mọi `CAST()` trong một câu `SELECT` sẽ biến warning thành error chỉ vì strict mode đang bật. Hãy kiểm tra kết quả và warning thực tế của biểu thức trên phiên bản server đang chạy.

Sau phép chuyển đổi cần kiểm tra warning ngay:

```sql
SELECT CAST('12abc' AS UNSIGNED);
SHOW WARNINGS;
```

`SHOW WARNINGS` trả thông tin warning/error của các câu lệnh gần nhất trong session. Chạy một câu lệnh khác trước khi kiểm tra có thể làm thay đổi danh sách cần xem.

Không dùng giá trị trả về sau chuyển đổi lỗi như dữ liệu hợp lệ. Hãy xác thực đầu vào trong Java, dùng kiểu parameter phù hợp, áp dụng constraint ở database và ghi nhận lỗi chuyển đổi trong quy trình import.

## 13. Dùng CAST/CONVERT trong Java và JDBC

Trong ứng dụng Java, nên ưu tiên bind parameter với kiểu Java tương ứng thay vì ghép chuỗi SQL hoặc ép kiểu mọi giá trị ở phía database.

Ví dụ bind số tiền bằng `BigDecimal`:

```java
String sql = "INSERT INTO payments (amount) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBigDecimal(1, new BigDecimal("125.50"));
    statement.executeUpdate();
}
```

Ví dụ bind ngày:

```java
String sql = "SELECT order_id FROM orders WHERE order_date = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, LocalDate.of(2026, 11, 19));
    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
        }
    }
}
```

Các ví dụ giả định đã import JDBC classes và `java.math.BigDecimal`, `java.time.LocalDate`; `connection` là một JDBC connection đang mở. Khi bind đúng kiểu, câu SQL thường không cần `CAST()`.

Nếu dữ liệu nguồn bắt buộc là chuỗi, có thể ép tham số ở SQL:

```sql
SELECT order_id
FROM orders
WHERE order_id = CAST(? AS UNSIGNED);
```

Không dùng `CAST()` để thay thế `PreparedStatement`. Bind parameter vẫn cần thiết để tách dữ liệu khỏi cấu trúc SQL và ngăn SQL injection.

## 14. Checklist chọn CAST hay CONVERT

| Nhu cầu | Cách dùng |
|---|---|
| Chuyển chuỗi thành số/ngày/giờ | `CAST(expr AS type)` hoặc `CONVERT(expr, type)` |
| Chuyển số thành chuỗi | `CAST(expr AS CHAR)` |
| Chuyển chuỗi sang character set khác | `CONVERT(expr USING charset)` |
| Chỉ định quy tắc so sánh chuỗi | `expr COLLATE collation_name` sau khi charset tương thích |
| Phân tích chuỗi ngày theo format tùy chỉnh | `STR_TO_DATE(expr, format)` |
| Dùng giá trị ứng dụng trong truy vấn | Bind parameter bằng kiểu Java phù hợp; chỉ CAST tham số khi cần |

Trước khi đưa phép chuyển đổi vào truy vấn, hãy tự hỏi:

1. Kiểu nguồn là gì và kiểu đích cần là gì?
2. Chuyển đổi có làm mất phần thập phân, ký tự, số 0 đầu hoặc thông tin timezone không?
3. Giá trị không hợp lệ sẽ tạo warning, lỗi hay kết quả bị cắt?
4. Có thể bind tham số đúng kiểu thay vì chuyển đổi ở SQL không?
5. Phép chuyển đổi có đang bọc cột được index trong `WHERE` không?
6. Nếu chuyển character set, byte nguồn có thực sự được giải mã theo charset đã khai báo không?
7. Kết quả có collation đúng với quy tắc nghiệp vụ không?

## 15. Bài tập thực hành

1. Chuyển `'125.50'` thành `DECIMAL(10,2)` và tính tổng cho số lượng `3`.
2. Chuyển số `123` thành `CHAR` rồi ghép thành nhãn đơn hàng.
3. Chuyển chuỗi ISO thành `DATE` và chuỗi `dd/mm/yyyy` bằng `STR_TO_DATE()`.
4. Chạy `CAST('12abc' AS UNSIGNED)` và xem `SHOW WARNINGS`; giải thích vì sao ép kiểu không thay thế xác thực.
5. So sánh `CONVERT(expr, type)` với `CONVERT(expr USING utf8mb4)` và kiểm tra `CHARSET()`/`COLLATION()` của kết quả.
6. So sánh `'00123' = 123` với `'00123' = '123'`; giải thích nguy cơ khi mã định danh bị so sánh như số.
7. Dùng `EXPLAIN` để so sánh điều kiện `CAST(order_id AS CHAR) = ...` với điều kiện ép kiểu tham số và giữ nguyên cột `order_id`.
8. Viết một truy vấn JDBC dùng `PreparedStatement` và `setBigDecimal()` hoặc `setObject()` để truyền giá trị đúng kiểu.

Bạn hoàn thành bài khi phân biệt được ép kiểu dữ liệu với chuyển character set, nhận diện được chuyển đổi ngầm, biết đọc warning và chọn vị trí CAST hợp lý để giữ ngữ nghĩa cũng như khả năng sử dụng index. Hãy xác định kiểu dữ liệu đúng từ đầu; dùng chuyển đổi tường minh tại ranh giới dữ liệu khi thật sự cần.

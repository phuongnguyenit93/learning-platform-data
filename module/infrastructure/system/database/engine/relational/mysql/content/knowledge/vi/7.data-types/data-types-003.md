# DECIMAL so với FLOAT/DOUBLE và độ chính xác dữ liệu tiền tệ

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt kiểu số chính xác `DECIMAL` với kiểu số dấu phẩy động gần đúng `FLOAT` và `DOUBLE`.
- Giải thích vì sao nhiều số thập phân, chẳng hạn `0.1`, không được biểu diễn chính xác bằng số nhị phân dấu phẩy động.
- Chọn precision và scale cho cột tiền tệ, số lượng, thuế và tỷ giá.
- Tính toán, làm tròn và tổng hợp số tiền với quy tắc nhất quán trong MySQL.
- Ánh xạ `DECIMAL` sang `BigDecimal` trong Java và tránh đưa sai số dấu phẩy động vào dữ liệu tài chính.
- Lập kế hoạch chuyển cột `FLOAT`/`DOUBLE` sang `DECIMAL` mà không che giấu sai lệch dữ liệu cũ.

## 1. Vì sao kiểu dữ liệu số quan trọng với tiền tệ?

Một hệ thống bán hàng có thể tính giá sản phẩm, chiết khấu, thuế, phí vận chuyển, thanh toán và hoàn tiền. Những phép tính này thường được cộng dồn qua hàng nghìn hoặc hàng triệu giao dịch. Sai số rất nhỏ trong một phép tính có thể tích lũy hoặc làm kết quả lệch ở bước đối soát.

MySQL cung cấp hai nhóm kiểu số thường gặp:

- **Số chính xác (exact-value):** `INTEGER`, `BIGINT`, `DECIMAL` và các kiểu tương ứng. `DECIMAL` lưu số theo chữ số thập phân với precision/scale xác định.
- **Số gần đúng (approximate-value):** `FLOAT` và `DOUBLE`. Chúng dùng biểu diễn dấu phẩy động nhị phân, phù hợp với dải giá trị rộng và phép tính khoa học, nhưng nhiều phân số thập phân không thể biểu diễn chính xác.

Đối với số dư tài khoản, giá bán, số tiền hóa đơn, thuế hoặc số tiền thanh toán, thông thường nên dùng `DECIMAL` hoặc một cách biểu diễn số nguyên theo đơn vị tiền nhỏ nhất. `FLOAT`/`DOUBLE` phù hợp hơn cho dữ liệu đo lường, mô phỏng và tính toán khoa học chấp nhận sai số.

## 2. DECIMAL, FLOAT và DOUBLE khác nhau thế nào?

| Kiểu | Cách biểu diễn | Đặc tính | Trường hợp thường dùng |
|---|---|---|---|
| `DECIMAL(M,D)` | Số thập phân chính xác với tổng số chữ số và số chữ số phần lẻ được chỉ định | Lưu và tính toán theo giá trị thập phân; không gặp sai số biểu diễn nhị phân của các phân số thập phân thông thường | Tiền tệ, thuế, tỷ lệ cần quy tắc chính xác, số liệu kế toán |
| `FLOAT` | Số dấu phẩy động nhị phân độ chính xác đơn | Gần đúng, độ chính xác hữu hạn, dung lượng thường nhỏ hơn DOUBLE | Dữ liệu đo lường hoặc mô hình khoa học cần dải giá trị rộng |
| `DOUBLE` | Số dấu phẩy động nhị phân độ chính xác kép | Gần đúng, thường có độ chính xác cao hơn FLOAT nhưng vẫn không biểu diễn chính xác mọi số thập phân | Tính toán khoa học, thống kê, dữ liệu có sai số chấp nhận được |

Trong MySQL, `FLOAT` thường chiếm 4 byte và `DOUBLE` thường chiếm 8 byte. `DECIMAL` dùng biểu diễn thập phân đóng gói, dung lượng phụ thuộc precision và scale. Không nên chọn kiểu chỉ dựa vào số byte; cần xét yêu cầu chính xác, miền giá trị và workload.

### 2.1. Precision và scale của DECIMAL

Cú pháp:

```sql
DECIMAL(M, D)
```

- `M` (*precision*) là tổng số chữ số tối đa, gồm cả phần nguyên và phần thập phân.
- `D` (*scale*) là số chữ số tối đa ở bên phải dấu thập phân.
- Phần nguyên có tối đa `M - D` chữ số.
- Trong MySQL, precision tối đa của `DECIMAL` là 65 chữ số; scale tối đa là 30 và không thể lớn hơn precision.

Ví dụ:

| Kiểu | Chữ số phần nguyên tối đa | Chữ số phần lẻ | Giá trị dương lớn nhất |
|---|---:|---:|---:|
| `DECIMAL(8,2)` | 6 | 2 | `999999.99` |
| `DECIMAL(12,2)` | 10 | 2 | `9999999999.99` |
| `DECIMAL(19,4)` | 15 | 4 | `999999999999999.9999` |
| `DECIMAL(10,6)` | 4 | 6 | `9999.999999` |

Chọn `M` theo giá trị lớn nhất nghiệp vụ có thể đạt tới, có tính đến tổng số tiền, số dư, số lượng và mức tăng trưởng trong tương lai. Chọn `D` theo độ chính xác cần lưu. `DECIMAL(19,2)` không có nghĩa là 19 chữ số phần nguyên; nó có 17 chữ số phần nguyên và 2 chữ số phần lẻ.

### 2.2. Vì sao FLOAT/DOUBLE có sai số?

Máy tính biểu diễn `FLOAT` và `DOUBLE` theo cơ số 2. Một số phân số thập phân có biểu diễn nhị phân vô hạn tuần hoàn, giống như (1/3) có biểu diễn thập phân `0.3333...`. Hệ thống phải lưu một số bit hữu hạn, nên giá trị được làm tròn tới số nhị phân gần nhất có thể biểu diễn.

Ví dụ minh họa trong MySQL:

```sql
SELECT
    CAST('0.1' AS DOUBLE) + CAST('0.2' AS DOUBLE) AS approximate_sum,
    CAST('0.1' AS DECIMAL(3,1)) + CAST('0.2' AS DECIMAL(3,1)) AS exact_sum;
```

Kết quả ở cột `approximate_sum` có thể hiển thị một giá trị rất gần `0.3`, chẳng hạn `0.30000000000000004`, tùy cách định dạng kết quả. Cột `exact_sum` giữ kết quả thập phân chính xác `0.3` trong miền precision/scale của biểu thức.

Trong MySQL, literal thập phân như `0.1` được xem là giá trị chính xác; literal dùng ký pháp số mũ như `0.1E0` là giá trị gần đúng. Khi kiểm tra hành vi, cần chú ý kiểu của toán hạng và không chỉ nhìn cách client định dạng số.

```sql
-- Giá trị literal thập phân chính xác
SELECT 0.1 + 0.2 AS exact_literal_sum;

-- Literal dạng số mũ là giá trị gần đúng
SELECT 0.1E0 + 0.2E0 AS approximate_literal_sum;
```

Không nên dùng phép so sánh bằng tuyệt đối (`=`) cho kết quả FLOAT/DOUBLE khi nghiệp vụ cần kiểm tra số gần nhau. Nếu kiểu gần đúng là cần thiết, hãy xác định sai số chấp nhận được và so sánh theo tolerance. Với tiền tệ, giải pháp tốt hơn thường là lưu và tính bằng kiểu chính xác ngay từ đầu.

## 3. Chọn DECIMAL cho dữ liệu tiền tệ

### 3.1. Xác định đơn vị tiền và số chữ số phần lẻ

Không phải mọi loại tiền đều có cùng số chữ số phần lẻ. Một số đồng tiền dùng 0 chữ số thập phân theo đơn vị nhỏ nhất, nhiều đồng dùng 2, và một số dùng 3. Ngoài ra, hệ thống có thể cần lưu giá trị trung gian hoặc tỷ giá với độ chính xác cao hơn số tiền thanh toán cuối cùng.

Trước khi thiết kế cột, hãy xác định:

1. Tiền được lưu theo đơn vị chính (ví dụ USD) hay đơn vị nhỏ nhất (ví dụ cent)?
2. Hệ thống hỗ trợ những currency code nào và quy tắc số chữ số phần lẻ của từng đồng tiền là gì?
3. Giá đơn vị, tỷ giá, thuế và số tiền cuối cùng cần bao nhiêu chữ số phần lẻ?
4. Phép tính được làm tròn ở cấp dòng, hóa đơn hay tổng thanh toán?
5. Giá trị tối đa của một dòng, một hóa đơn, số dư tài khoản và tổng giao dịch là bao nhiêu?

Với hệ thống chỉ xử lý tiền có 2 chữ số phần lẻ, có thể bắt đầu bằng `DECIMAL(19,2)` cho số tiền. Nếu phải lưu tỷ giá hoặc giá trị trung gian nhiều chữ số hơn, dùng scale lớn hơn, ví dụ `DECIMAL(20,10)` cho tỷ giá, sau đó áp dụng quy tắc làm tròn khi chuyển thành số tiền phải thanh toán. Đây là ví dụ thiết kế; precision/scale thực tế phải dựa trên giới hạn nghiệp vụ.

### 3.2. Lưu currency code cùng số tiền

Một số tiền không có ý nghĩa đầy đủ nếu thiếu loại tiền. `100.00` có thể là 100 USD, 100 EUR hoặc 100 đơn vị tiền khác. Vì vậy, lưu currency code rõ ràng bên cạnh amount:

```sql
CREATE TABLE payments (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    currency_code CHAR(3) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (payment_id),
    KEY idx_currency_created (currency_code, created_at)
) ENGINE = InnoDB;
```

Ví dụ dữ liệu:

```sql
INSERT INTO payments (currency_code, amount, created_at)
VALUES
    ('USD', 125.50, '2026-01-10 09:00:00'),
    ('EUR', 89.99, '2026-01-10 09:05:00');
```

Không cộng trực tiếp các khoản tiền khác currency như thể chúng cùng đơn vị. Muốn tổng hợp, cần nhóm theo currency hoặc chuyển đổi bằng tỷ giá được xác định rõ, kèm thời điểm và nguồn tỷ giá.

### 3.3. Lựa chọn giữa DECIMAL và số nguyên đơn vị nhỏ nhất

Một cách khác là lưu số tiền bằng số nguyên theo đơn vị nhỏ nhất. Ví dụ, `12345` biểu thị 123.45 USD nếu quy ước đơn vị là cent.

| Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|
| `DECIMAL(19,2)` | Dễ đọc, biểu diễn trực tiếp số tiền; SQL có thể tính toán theo số thập phân chính xác | Phải chọn scale và quy tắc làm tròn rõ ràng |
| `BIGINT` đơn vị nhỏ nhất | Phép cộng/trừ số nguyên chính xác và đơn giản; hữu ích với currency có số chữ số phần lẻ cố định | Phải biết số chữ số phần lẻ của currency; phép nhân/chia và tỷ giá cần xử lý scale riêng; có nguy cơ tràn số nguyên |

Nếu hệ thống hỗ trợ nhiều currency, số chữ số phần lẻ khác nhau hoặc cần tính toán trung gian, `DECIMAL` thường dễ biểu đạt hơn. Nếu chọn số nguyên, phải lưu hoặc xác định chắc chắn quy ước đơn vị của từng currency; không giả định mọi currency đều chia 100.

## 4. Thiết kế precision/scale cho giá, số lượng, thuế và tỷ giá

Các trường dữ liệu có mục đích khác nhau nên không nhất thiết dùng cùng scale.

| Đại lượng | Ví dụ kiểu dữ liệu | Lý do |
|---|---|---|
| Số tiền thanh toán theo currency 2 chữ số lẻ | `DECIMAL(19,2)` | Lưu số tiền cuối cùng theo đơn vị nhỏ nhất thông dụng |
| Giá đơn vị có thể có nhiều chữ số lẻ | `DECIMAL(19,4)` hoặc scale theo nghiệp vụ | Tránh làm tròn giá đơn vị quá sớm |
| Số lượng hàng hóa có phần lẻ | `DECIMAL(12,3)` | Hỗ trợ kg, lít hoặc đơn vị đo có phần thập phân |
| Tỷ lệ phần trăm | `DECIMAL(9,6)` | Giữ đủ chữ số cho tỷ lệ, tùy miền giá trị |
| Tỷ giá quy đổi | `DECIMAL(20,10)` | Giữ độ chính xác cao hơn số tiền cuối cùng |
| Tiền thuế cuối cùng | Scale theo currency, ví dụ `DECIMAL(19,2)` | Làm tròn theo quy tắc thuế và currency |

Không sao chép nguyên các kiểu ví dụ vào mọi hệ thống. Một giá đơn vị rất nhỏ, số lượng lớn hoặc tỷ giá đặc thù có thể cần precision khác. Hãy tính giá trị tối đa của biểu thức trung gian, không chỉ giá trị tối đa của một cột.

Ví dụ schema đơn giản dưới đây giả định currency được lưu trong `line_total` có 2 chữ số phần lẻ. Nếu hỗ trợ currency có quy tắc scale khác, cần lưu quy tắc theo currency và điều chỉnh scale/rounding ở bước tính số tiền cuối cùng.

```sql
CREATE TABLE invoice_lines (
    line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    currency_code CHAR(3) NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    tax_rate DECIMAL(9,6) NOT NULL,
    line_total DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (line_id),
    KEY idx_currency (currency_code)
) ENGINE = InnoDB;
```

Trong mô hình này, `unit_price`, `quantity` và `tax_rate` là dữ liệu đầu vào tính toán; `line_total` là số tiền đã được làm tròn theo chính sách currency. Hệ thống thực tế có thể cần lưu riêng subtotal, discount, tax amount, total và rounding adjustment để có thể giải thích cách tạo ra số cuối cùng.

## 5. Tính toán và làm tròn trong MySQL

### 5.1. Giữ phép tính ở kiểu chính xác

MySQL xử lý phép tính trên giá trị exact và approximate theo quy tắc kiểu dữ liệu. Khi toán hạng là `DECIMAL` hoặc số nguyên, kết quả của nhiều phép tính tiếp tục là giá trị chính xác, trong giới hạn precision/scale mà MySQL hỗ trợ. Khi đưa `FLOAT`/`DOUBLE` vào biểu thức, kết quả có thể trở thành gần đúng.

Ví dụ tính tổng tiền một dòng:

```sql
SELECT
    CAST('19.99' AS DECIMAL(10,2)) * 3 AS exact_line_amount,
    CAST('19.99' AS DOUBLE) * 3 AS approximate_line_amount;
```

Hãy giữ các giá trị tiền tệ ở kiểu `DECIMAL` xuyên suốt luồng tính toán. Không chuyển sang `DOUBLE` chỉ để thực hiện phép nhân hoặc tính tổng.

### 5.2. Quy định điểm làm tròn

Làm tròn là quyết định nghiệp vụ. Ví dụ, hệ thống có thể làm tròn từng dòng hàng rồi cộng lại, hoặc cộng các giá trị chưa làm tròn rồi làm tròn một lần ở cấp hóa đơn. Hai cách có thể cho tổng khác nhau.

Giả sử ba dòng có số tiền chưa làm tròn lần lượt là 0.335, 0.335 và 0.335, với currency có 2 chữ số phần lẻ:

- Làm tròn từng dòng: 0.34 + 0.34 + 0.34 = 1.02.
- Cộng trước rồi làm tròn: 0.335 + 0.335 + 0.335 = 1.005, sau đó làm tròn thành 1.01 theo quy tắc half away from zero của giá trị exact trong MySQL.

Kết quả khác nhau một đơn vị nhỏ nhất. Hệ thống phải chọn và áp dụng một chính sách nhất quán, phù hợp hợp đồng, quy định kế toán/thuế và yêu cầu đối soát.

### 5.3. ROUND và TRUNCATE

Ví dụ:

```sql
SELECT
    ROUND(CAST('12.345' AS DECIMAL(8,3)), 2) AS rounded_value,
    TRUNCATE(CAST('12.349' AS DECIMAL(8,3)), 2) AS truncated_value;
```

- `ROUND(value, d)` làm tròn tới `d` chữ số phần lẻ.
- `TRUNCATE(value, d)` cắt phần chữ số vượt quá scale được chỉ định, không làm tròn lên.

Với giá trị exact, MySQL làm tròn các trường hợp đúng giữa hai giá trị theo hướng xa số 0 (*half away from zero*). Với giá trị approximate, kết quả phụ thuộc thư viện toán của nền tảng và có thể khác. Vì vậy, nếu chính sách tài chính yêu cầu quy tắc xác định, hãy đưa vào `DECIMAL` trước khi làm tròn và kiểm thử cả số dương lẫn số âm.

### 5.4. Kiểm tra số chữ số khi ghi vào cột

Khi lưu giá trị có nhiều chữ số phần lẻ hơn scale của cột, MySQL chuyển giá trị về scale của cột theo quy tắc làm tròn. Ví dụ cột `DECIMAL(8,2)` chỉ lưu 2 chữ số phần lẻ:

```sql
CREATE TABLE decimal_rounding_demo (
    amount DECIMAL(8,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO decimal_rounding_demo (amount)
VALUES (12.345);

SELECT amount
FROM decimal_rounding_demo;
```

Giá trị được lưu theo scale 2. Đối với giá trị vượt miền precision, kết quả có thể là lỗi hoặc cảnh báo tùy SQL mode và ngữ cảnh. Hãy kiểm tra `SHOW WARNINGS`, `@@sql_mode` và thử các biên dữ liệu trước khi nạp khối lượng lớn.

```sql
-- Chạy ngay sau INSERT/UPDATE/DDL cần kiểm tra cảnh báo
SHOW WARNINGS;

-- Xem chế độ SQL của phiên hiện tại
SELECT @@SESSION.sql_mode;
```

Không dùng việc MySQL tự làm tròn khi ghi cột như một chính sách tài chính ngầm. Hãy làm tròn tường minh ở đúng bước nghiệp vụ, ghi nhận quy tắc và kiểm tra kết quả trước khi lưu.

### 5.5. SUM và AVG với DECIMAL

MySQL trả về kiểu `DECIMAL` cho `SUM()` và `AVG()` khi đối số là kiểu exact-value; nếu đối số là `FLOAT` hoặc `DOUBLE`, kết quả là kiểu gần đúng. Điều này là một lý do quan trọng để lưu amount bằng `DECIMAL` ngay từ đầu.

```sql
SELECT
    currency_code,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount
FROM payments
GROUP BY currency_code;
```

Truy vấn nhóm theo currency để tránh cộng các đơn vị tiền khác nhau. Khi cần báo cáo ở scale cụ thể, hãy áp dụng `CAST` hoặc `ROUND` tường minh sau khi đã xác định chính sách làm tròn.

## 6. Làm việc với DECIMAL trong Java

Trong Java, kiểu phù hợp để biểu diễn SQL `DECIMAL` là `java.math.BigDecimal`. `BigDecimal` hỗ trợ số thập phân chính xác và scale rõ ràng. Tránh dùng `float` hoặc `double` làm trung gian cho số tiền.

### 6.1. Tạo BigDecimal đúng cách

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = BigDecimal.valueOf(3);

BigDecimal subtotal = price.multiply(quantity);
BigDecimal total = subtotal.setScale(2, RoundingMode.HALF_UP);

System.out.println(total); // 59.97
```

Ưu tiên constructor nhận chuỗi hoặc `BigDecimal.valueOf(long)` khi đầu vào là số nguyên. `BigDecimal.valueOf(double)` có thể hữu ích khi phải nhận một giá trị `double` đã tồn tại, nhưng nó không biến một phép tính dấu phẩy động gần đúng thành phép tính tiền tệ chính xác. Không viết:

```java
BigDecimal unsafe = new BigDecimal(0.1);
```

Constructor nhận `double` giữ chính xác giá trị nhị phân gần đúng mà `double` đang chứa; nó không khôi phục ý định thập phân ban đầu là `0.1`. Dùng:

```java
BigDecimal safe = new BigDecimal("0.1");
```

### 6.2. Chia và làm tròn

Phép chia thập phân có thể tạo ra chuỗi vô hạn, chẳng hạn 1 chia 3. `BigDecimal.divide()` không có scale hoặc rounding mode sẽ ném `ArithmeticException` nếu kết quả không có biểu diễn thập phân hữu hạn.

```java
BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("3");

BigDecimal converted = amount.divide(
    rate,
    2,
    RoundingMode.HALF_UP
);
```

`HALF_UP` chỉ là ví dụ. Tùy chính sách, có thể dùng `HALF_EVEN`, `DOWN`, `CEILING` hoặc quy tắc khác. Không chọn rounding mode theo thói quen của lập trình viên; hãy thống nhất với yêu cầu nghiệp vụ.

### 6.3. So sánh BigDecimal

`BigDecimal.equals()` so sánh cả giá trị và scale. Vì vậy, `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả về `false`, dù hai số có cùng giá trị số học. Dùng `compareTo()` khi muốn so sánh giá trị:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

boolean sameNumericValue = a.compareTo(b) == 0;
```

Nếu scale có ý nghĩa trong nghiệp vụ hoặc định dạng tiền tệ, hãy kiểm tra scale riêng. Không nhầm so sánh số học với so sánh biểu diễn.

### 6.4. Đọc và ghi DECIMAL qua JDBC

Dùng `setBigDecimal()` để ghi và `getBigDecimal()` để đọc:

```java
String sql = "INSERT INTO payments (currency_code, amount, created_at) "
           + "VALUES (?, ?, NOW())";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "USD");
    statement.setBigDecimal(2, new BigDecimal("125.50"));
    statement.executeUpdate();
}

try (var statement = connection.prepareStatement(
        "SELECT amount FROM payments WHERE payment_id = ?")) {
    statement.setLong(1, paymentId);
    try (var result = statement.executeQuery()) {
        if (result.next()) {
            BigDecimal amountFromDb = result.getBigDecimal("amount");
        }
    }
}
```

Prepared statement giúp truyền giá trị theo kiểu phù hợp và tránh nối chuỗi SQL. Không đọc `DECIMAL` bằng `getDouble()` nếu ứng dụng cần giữ chính xác số tiền.

## 7. Tránh sai số khi tính tổng và chuyển đổi currency

Một luồng xử lý thanh toán nên xác định rõ các bước:

1. Đọc giá và số lượng từ kiểu chính xác.
2. Tính subtotal, discount và tax bằng `DECIMAL`/`BigDecimal` với precision đủ lớn.
3. Chọn thời điểm làm tròn theo quy tắc nghiệp vụ.
4. Lưu amount cuối cùng cùng currency code.
5. Nếu chuyển currency, lưu tỷ giá, nguồn tỷ giá, thời điểm áp dụng và số tiền sau quy đổi.

Ví dụ cấu trúc lưu giao dịch quy đổi:

```sql
CREATE TABLE currency_conversions (
    conversion_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_currency CHAR(3) NOT NULL,
    target_currency CHAR(3) NOT NULL,
    source_amount DECIMAL(19,2) NOT NULL,
    exchange_rate DECIMAL(20,10) NOT NULL,
    target_amount DECIMAL(19,2) NOT NULL,
    rate_at DATETIME NOT NULL,
    rate_source VARCHAR(100) NOT NULL,
    PRIMARY KEY (conversion_id)
) ENGINE = InnoDB;
```

Schema này lưu tỷ giá và kết quả quy đổi để có thể kiểm tra lại giao dịch. Cần quy định tỷ giá được hiểu là bao nhiêu đơn vị target cho một đơn vị source hay ngược lại, cũng như cách làm tròn target amount. Không thể chỉ nhìn hai currency code và rate mà suy ra chiều quy đổi.

Tránh các lỗi phổ biến:

- Cộng số tiền của nhiều currency mà không quy đổi.
- Dùng `DOUBLE` cho amount rồi chuyển sang `DECIMAL` ở cuối.
- Làm tròn giá đơn vị quá sớm trước khi nhân số lượng.
- Làm tròn cả dòng và hóa đơn theo hai quy tắc khác nhau mà không chủ ý.
- Dùng tỷ giá hiện tại để tính lại một giao dịch lịch sử thay vì tỷ giá đã áp dụng lúc giao dịch.
- Dùng kiểu không đủ precision khiến tổng nhiều dòng vượt miền giá trị.

## 8. Tìm và sửa thiết kế đang dùng FLOAT/DOUBLE cho tiền

Nếu hệ thống hiện tại lưu tiền bằng `FLOAT` hoặc `DOUBLE`, không nên chỉ chạy `ALTER TABLE ... MODIFY amount DECIMAL(...)` rồi cho rằng dữ liệu gốc đã được phục hồi chính xác. Các giá trị nhị phân cũ có thể đã mất thông tin về số thập phân ban đầu; ép kiểu chỉ chuyển giá trị đang lưu sang dạng decimal theo quy tắc chuyển đổi.

Quy trình đánh giá:

1. Xác định tất cả cột và biểu thức đang dùng `FLOAT`/`DOUBLE` cho giá, thuế, phí, số dư hoặc thanh toán.
2. Lấy mẫu các giá trị thực tế, gồm số âm, số rất nhỏ, giá trị lớn, giá trị có nhiều chữ số lẻ và trường hợp biên.
3. Đối chiếu với nguồn dữ liệu gốc như đơn hàng, hóa đơn, file thanh toán hoặc log giao dịch nếu còn.
4. Xác định scale và rounding mode theo nghiệp vụ; không suy ra scale chỉ từ số chữ số đang hiển thị.
5. Tạo cột `DECIMAL` mới hoặc bảng đích thử nghiệm; chuyển đổi theo quy tắc đã duyệt.
6. So sánh giá trị trước/sau, tổng hợp theo ngày/currency và kiểm tra các giao dịch trọng yếu.
7. Chuyển ứng dụng sang đọc/ghi `BigDecimal`, kiểm thử, rồi mới cutover và loại bỏ cột cũ theo quy trình migration.

Ví dụ minh họa chuyển dữ liệu thử nghiệm sang cột mới:

```sql
ALTER TABLE legacy_payments
ADD COLUMN amount_decimal DECIMAL(19,2) NULL;

UPDATE legacy_payments
SET amount_decimal = ROUND(amount_double, 2)
WHERE amount_decimal IS NULL;
```

Đây chỉ là ví dụ kỹ thuật. `ROUND(amount_double, 2)` không khôi phục chính xác giá trị người dùng từng nhập nếu dữ liệu gốc đã được lưu dưới dạng nhị phân gần đúng. Chỉ dùng cách chuyển này sau khi đã quyết định rằng làm tròn hai chữ số là chính sách đúng và đã đối soát với nguồn có thẩm quyền.

Sau khi kiểm tra, có thể xác nhận các giá trị chuyển đổi:

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(amount_decimal IS NULL) AS missing_converted_amounts,
    MIN(amount_decimal) AS min_amount,
    MAX(amount_decimal) AS max_amount,
    SUM(amount_decimal) AS total_amount
FROM legacy_payments;
```

Đối chiếu tổng theo cùng currency và cùng tập giao dịch. Không so tổng các currency khác nhau hoặc so dữ liệu được lấy ở những thời điểm có giao dịch mới mà không có snapshot nhất quán.

## 9. Kiểm tra precision, scale và giới hạn

Trước khi tạo cột, tính toán miền giá trị tối đa. Ví dụ nếu số tiền có thể lên tới 12 chữ số phần nguyên và cần 2 chữ số phần lẻ, `DECIMAL(14,2)` có đủ 14 chữ số tổng. Nếu cần thêm khoảng tăng trưởng, chọn precision cao hơn nhưng vẫn nằm trong giới hạn MySQL.

Kiểm tra kiểu và metadata của cột:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'payments'
  AND COLUMN_NAME = 'amount';
```

Kiểm tra SQL mode để hiểu cách server xử lý dữ liệu ngoài miền hoặc phép chuyển đổi:

```sql
SELECT @@SESSION.sql_mode;
```

Không dựa vào việc server có thể phát cảnh báo hoặc tự điều chỉnh giá trị để bỏ qua kiểm tra đầu vào ở ứng dụng. Validate dữ liệu ở tầng ứng dụng, dùng kiểu cột đủ miền và giám sát lỗi ghi.

### 9.1. Tránh tràn số ở biểu thức trung gian

Một cột có thể vừa đủ miền nhưng phép nhân hoặc tổng nhiều dòng có thể tạo ra kết quả lớn hơn. Ví dụ, giá đơn vị nhân số lượng lớn hoặc tổng hàng triệu giao dịch có thể vượt precision dự kiến.

Hãy tính giới hạn của:

- Giá trị lớn nhất của một dòng.
- Số lượng tối đa nhân với giá đơn vị tối đa.
- Tổng số tiền trong một hóa đơn.
- Tổng số dư hoặc doanh thu toàn hệ thống.
- Tỷ giá và kết quả quy đổi.

Kiểm tra kiểu trả về của biểu thức và aggregate trong phiên bản MySQL đang dùng. Nếu cần, dùng `CAST(... AS DECIMAL(p,s))` tường minh tại ranh giới tính toán, đồng thời chọn precision đủ lớn cho kết quả trước khi làm tròn về scale lưu trữ cuối cùng.

### 9.2. Index trên cột DECIMAL

`DECIMAL` có thể được index như các kiểu cột phù hợp khác của InnoDB. Ví dụ:

```sql
CREATE INDEX idx_payments_currency_amount
ON payments (currency_code, amount);
```

Index hữu ích nếu truy vấn lọc theo currency và khoảng amount. Tuy nhiên, không tạo index chỉ vì cột có kiểu `DECIMAL`; hãy dựa trên điều kiện lọc, thứ tự sắp xếp và workload thực tế. Tránh bọc cột index trong hàm hoặc ép kiểu không cần thiết ở điều kiện lọc nếu điều đó khiến optimizer không sử dụng được index.

## 10. Checklist thiết kế dữ liệu tiền tệ

- [ ] Số tiền dùng `DECIMAL` hoặc số nguyên theo đơn vị nhỏ nhất đã được quy ước.
- [ ] Mỗi amount gắn với currency code rõ ràng.
- [ ] Precision đủ cho giá trị tối đa và tổng cộng dồn.
- [ ] Scale phản ánh quy tắc currency và độ chính xác cần thiết của giá, tỷ giá, thuế.
- [ ] Quy tắc làm tròn và thời điểm làm tròn đã được xác định.
- [ ] Không chuyển amount sang `FLOAT`/`DOUBLE` trong SQL hoặc Java.
- [ ] Ứng dụng Java dùng `BigDecimal`, JDBC `setBigDecimal()` và `getBigDecimal()`.
- [ ] Phép chia có rounding mode và scale tường minh.
- [ ] Tổng hợp không cộng lẫn nhiều currency.
- [ ] Có kiểm tra giá trị biên, overflow, SQL mode và dữ liệu migration.
- [ ] Nếu chuyển từ FLOAT/DOUBLE, đã đối chiếu với nguồn dữ liệu gốc và không coi phép CAST là khôi phục giá trị ban đầu.

## 11. Kết luận

`DECIMAL` biểu diễn số thập phân chính xác trong precision và scale được khai báo, phù hợp với số tiền và dữ liệu tài chính. `FLOAT` và `DOUBLE` dùng biểu diễn nhị phân gần đúng, thích hợp cho nhiều bài toán khoa học nhưng có thể tạo sai số khi biểu diễn và cộng dồn số thập phân.

Hãy chọn precision/scale dựa trên miền giá trị và quy tắc currency, lưu currency code cùng amount, quy định rõ điểm làm tròn và dùng `BigDecimal` trong Java. Nếu dữ liệu tiền cũ đang nằm trong FLOAT/DOUBLE, cần đối soát với nguồn có thẩm quyền trước khi chuyển đổi vì kiểu DECIMAL mới không thể tự khôi phục những chữ số đã mất trong quá trình lưu gần đúng.

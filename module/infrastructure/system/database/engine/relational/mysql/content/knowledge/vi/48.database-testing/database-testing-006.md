# Kiểm thử độ chính xác số, UNSIGNED và ánh xạ Java

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này hướng dẫn kiểm thử các kiểu số giữa MySQL và Java, tập trung vào `DECIMAL`, `BigDecimal`, kiểu integer `UNSIGNED`, giới hạn miền giá trị, làm tròn và chuyển đổi qua JDBC/JPA.

Lỗi số học thường khó phát hiện vì ứng dụng vẫn chạy và dữ liệu vẫn được ghi. Một số tiền có thể lệch một đơn vị nhỏ sau nhiều phép tính; một giá trị `BIGINT UNSIGNED` có thể vượt giới hạn `long` của Java; một phép ép kiểu có thể làm tròn hoặc mất dữ liệu mà test thông thường không phát hiện. Cần kiểm thử ở biên miền giá trị, kiểm tra round-trip và dùng đúng MySQL trong integration test.

## 1. Chọn kiểu số theo ý nghĩa dữ liệu

MySQL cung cấp kiểu số nguyên, số thập phân chính xác và số dấu phẩy động gần đúng. Mỗi nhóm có cách biểu diễn và giới hạn khác nhau.

| Nhóm | Kiểu MySQL | Đặc điểm | Ví dụ sử dụng |
|---|---|---|---|
| Số nguyên | `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, `BIGINT` | Lưu số nguyên trong miền giá trị xác định; có thể dùng `UNSIGNED` cho miền không âm rộng hơn. | ID, số lượng, bộ đếm, số lần thử. |
| Số thập phân chính xác | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Lưu giá trị thập phân với precision và scale được chỉ định. | Tiền, thuế, tỷ lệ cần quy tắc chính xác, số đo có scale cố định. |
| Số dấu phẩy động | `FLOAT`, `DOUBLE` | Lưu giá trị gần đúng theo biểu diễn nhị phân; một số số thập phân không thể biểu diễn chính xác. | Tính toán khoa học, mô hình hóa, đo lường chấp nhận sai số. |

Không chọn `DOUBLE` chỉ vì nó chứa được nhiều chữ số hơn `DECIMAL`. Nếu nghiệp vụ yêu cầu giá trị thập phân chính xác, ví dụ số tiền, dùng `DECIMAL` ở MySQL và `BigDecimal` ở Java. Nếu dữ liệu là phép đo gần đúng, `FLOAT`/`DOUBLE` có thể phù hợp nhưng test phải dùng sai số cho phép thay vì so sánh bằng tuyệt đối.

## 2. Precision và scale của DECIMAL

Cú pháp `DECIMAL(p,s)` có hai tham số:

- `p` (precision): tổng số chữ số tối đa, cả phần nguyên và phần thập phân.
- `s` (scale): số chữ số ở bên phải dấu thập phân.

Ví dụ `DECIMAL(12,2)` có tối đa 12 chữ số, trong đó 2 chữ số thập phân và 10 chữ số phần nguyên. Miền giá trị signed là từ `-9999999999.99` đến `9999999999.99`. Với `DECIMAL(12,2) UNSIGNED`, miền giá trị bắt đầu từ 0 và kết thúc tại `9999999999.99`.

MySQL hỗ trợ precision tối đa 65 chữ số và scale tối đa 30 chữ số cho `DECIMAL`. Scale không được lớn hơn precision. Khi thiết kế cột, hãy xác định cả giá trị lớn nhất, số chữ số thập phân hợp lệ và quy tắc làm tròn của nghiệp vụ.

```sql
CREATE TABLE invoice_line (
    id BIGINT NOT NULL AUTO_INCREMENT,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    line_total DECIMAL(20,4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Không mặc định `DECIMAL(10,2)` phù hợp cho mọi khoản tiền. Một hệ thống có thể cần lưu tỷ giá với 8 chữ số thập phân, số lượng với 3 chữ số hoặc giá trị tài chính lớn hơn giới hạn của 10 chữ số. Thiết kế precision/scale từ yêu cầu miền dữ liệu và kiểm tra tổng số chữ số trong mọi phép tính trung gian.

## 3. BigDecimal trong Java

Java `BigDecimal` biểu diễn số thập phân bằng giá trị nguyên không giới hạn cố định cùng scale. Nó phù hợp để ánh xạ với MySQL `DECIMAL`.

Tạo BigDecimal từ chuỗi để tránh đưa sai số của `double` vào giá trị:

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("3.000");
BigDecimal total = price.multiply(quantity);
```

Tránh:

```java
BigDecimal wrong = new BigDecimal(0.1);
```

`0.1` không có biểu diễn nhị phân hữu hạn trong `double`, nên constructor trên chuyển giá trị gần đúng của `double` sang BigDecimal. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` nếu dữ liệu đầu vào thực sự đến từ double và không thể thay đổi nguồn.

### Scale và cách so sánh

`BigDecimal.equals()` so sánh cả giá trị lẫn scale:

```java
new BigDecimal("10.0").equals(new BigDecimal("10.00")); // false
```

`compareTo()` so sánh giá trị số:

```java
new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0; // true
```

Trong test, chọn phép so sánh theo hợp đồng dữ liệu:

- Nếu chỉ cần bằng nhau về giá trị số, dùng `compareTo() == 0` hoặc assertion so sánh theo giá trị.
- Nếu scale là một phần của hợp đồng, ví dụ mọi khoản tiền phải có đúng 2 chữ số thập phân, kiểm tra thêm `scale()`.
- Nếu cần xác minh database giữ nguyên scale cột, đọc lại giá trị và kiểm tra cả giá trị lẫn scale.

Chuẩn hóa scale rõ ràng trước khi tính hoặc persist:

```java
BigDecimal amount = new BigDecimal("125.5")
        .setScale(2, RoundingMode.HALF_UP);
```

Không gọi `setScale()` mà bỏ qua giá trị trả về vì `BigDecimal` immutable. Nếu scale thay đổi mà không chỉ định `RoundingMode` và giá trị có chữ số dư, Java có thể ném `ArithmeticException`; đây có thể là hành vi mong muốn để phát hiện dữ liệu không hợp lệ.

## 4. Kiểm thử làm tròn Java và MySQL

Làm tròn cần được quy định ở cấp nghiệp vụ. Ví dụ `HALF_UP` làm tròn điểm giữa ra xa số 0; `HALF_EVEN` chọn số chẵn gần nhất ở trường hợp đúng giữa.

```java
BigDecimal value = new BigDecimal("1.005");

BigDecimal halfUp = value.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = value.setScale(2, RoundingMode.HALF_EVEN);

// halfUp  = 1.01
// halfEven = 1.00
```

Với số âm, `HALF_UP` cũng làm tròn điểm giữa ra xa số 0: `-1.005` thành `-1.01`.

MySQL `ROUND()` trên giá trị exact như `DECIMAL` dùng quy tắc làm tròn điểm giữa ra xa số 0. Với giá trị approximate như `DOUBLE`, kết quả có thể phụ thuộc nền tảng và cách biểu diễn nhị phân. Vì vậy, test tiền tệ phải truyền `BigDecimal` và kiểm tra trên cột `DECIMAL`, không thay bằng `double`.

Ví dụ kiểm tra trong MySQL:

```sql
SELECT
    ROUND(CAST('1.005' AS DECIMAL(10,3)), 2) AS positive_half,
    ROUND(CAST('-1.005' AS DECIMAL(10,3)), 2) AS negative_half;
```

Khi ghi giá trị có nhiều chữ số thập phân hơn scale cột, MySQL có thể làm tròn để phù hợp scale. Đừng mặc định rằng `STRICT_TRANS_TABLES` sẽ từ chối mọi trường hợp có scale dư. Hãy test riêng hành vi làm tròn, overflow và warning trên phiên bản MySQL cùng `sql_mode` production.

## 5. Miền giá trị của integer UNSIGNED

`UNSIGNED` loại bỏ miền âm và mở rộng miền dương của kiểu integer. Các miền giá trị quan trọng:

| Kiểu MySQL | Signed | Unsigned |
|---|---|---|
| `TINYINT` | -128 đến 127 | 0 đến 255 |
| `SMALLINT` | -32.768 đến 32.767 | 0 đến 65.535 |
| `MEDIUMINT` | -8.388.608 đến 8.388.607 | 0 đến 16.777.215 |
| `INT` | -2.147.483.648 đến 2.147.483.647 | 0 đến 4.294.967.295 |
| `BIGINT` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | 0 đến 18.446.744.073.709.551.615 |

Một số kiểu `UNSIGNED` vừa với kiểu Java có dấu rộng hơn; `BIGINT UNSIGNED` thì không vừa với `long` ở toàn bộ miền giá trị. Không chỉ dựa vào việc dữ liệu hiện tại nhỏ hơn giới hạn; cần xác định invariant và kiểm thử giới hạn thực tế.

| MySQL | Kiểu Java có thể chứa toàn miền unsigned | Lưu ý |
|---|---|---|
| `TINYINT UNSIGNED` | `short` hoặc `int` | `byte` có dấu không chứa được 128–255. |
| `SMALLINT UNSIGNED` | `int` | `short` có dấu không chứa được 32.768–65.535. |
| `MEDIUMINT UNSIGNED` | `int` | Miền unsigned vẫn nằm trong `Integer.MAX_VALUE`. |
| `INT UNSIGNED` | `long` | `int` có dấu không chứa được phần trên miền. |
| `BIGINT UNSIGNED` | `BigInteger` | `long` có dấu không chứa được giá trị lớn hơn `Long.MAX_VALUE`. |

Nếu ứng dụng Java dùng `Long` làm ID, cột MySQL `BIGINT` signed thường phù hợp và tránh chênh lệch miền giá trị. Nếu bắt buộc dùng `BIGINT UNSIGNED` toàn miền, cần ánh xạ sang `BigInteger` hoặc một biểu diễn an toàn khác và kiểm thử driver/provider cụ thể.

## 6. Ánh xạ số qua JDBC

Với `DECIMAL`, dùng `PreparedStatement.setBigDecimal()` và `ResultSet.getBigDecimal()`:

```java
String sql = "INSERT INTO payment (amount) VALUES (?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("123456789012.3400"));
    ps.executeUpdate();
}

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM payment WHERE id = ?")) {
    ps.setLong(1, paymentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
```

Không dùng `getDouble()` cho cột `DECIMAL` nếu cần giữ chính xác giá trị. `getDouble()` chuyển giá trị sang số dấu phẩy động gần đúng.

### Đọc BIGINT UNSIGNED lớn hơn Long.MAX_VALUE

Không dùng `ResultSet.getLong()` để đọc toàn miền `BIGINT UNSIGNED`. Đọc dưới dạng `BigDecimal`, sau đó chuyển sang `BigInteger` chính xác:

```java
BigDecimal raw = rs.getBigDecimal("unsigned_counter");
BigInteger value = raw.toBigIntegerExact();
```

`toBigIntegerExact()` phát hiện nếu giá trị có phần thập phân. Với cột integer, đây là cách chuyển đổi có kiểm tra. Có thể dùng `getObject()` nhưng kiểu Java trả về có thể phụ thuộc Connector/J và phiên bản; nếu dùng, hãy kiểm tra `DatabaseMetaData`, kiểu runtime và boundary trong integration test.

Để ghi giá trị `BIGINT UNSIGNED` lớn hơn `Long.MAX_VALUE`, dùng biểu diễn `BigInteger` rồi chuyển sang `BigDecimal` khi bind:

```java
BigInteger maxUnsignedBigint = new BigInteger("18446744073709551615");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO unsigned_value (value) VALUES (?)")) {
    ps.setBigDecimal(1, new BigDecimal(maxUnsignedBigint));
    ps.executeUpdate();
}
```

Kiểm thử cách bind này với đúng phiên bản Connector/J và MySQL đang triển khai. Nếu dùng JPA/Hibernate, mapping `BigInteger` với cột `BIGINT UNSIGNED` cũng phải được xác minh qua DDL, dialect và driver; không giả định annotation `@Column` tự bảo đảm toàn miền unsigned.

## 7. Ánh xạ DECIMAL trong JPA/Hibernate

Với giá trị thập phân chính xác, dùng `BigDecimal` và khai báo precision/scale:

```java
@Column(name = "amount", precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

DDL nên được quản lý bằng migration:

```sql
CREATE TABLE payment (
    id BIGINT NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Đừng chỉ kiểm tra entity có thể persist. Kiểm tra schema thực tế bằng `SHOW CREATE TABLE payment`, metadata JDBC và test round-trip. Nếu Hibernate sinh schema, kiểm tra DDL do dialect phát ra. Trong production, ưu tiên migration có kiểm soát và `ddl-auto=validate` thay cho `ddl-auto=update`.

### BIGINT UNSIGNED với JPA

Nếu cần lưu toàn miền `BIGINT UNSIGNED`, Java `BigInteger` là kiểu phù hợp về mặt miền giá trị. Tuy nhiên, cách Hibernate dialect ánh xạ `BigInteger` sang JDBC numeric và cách Connector/J trả dữ liệu phải được xác minh trên stack thực tế. Có thể dùng `columnDefinition = "bigint unsigned"` để mô tả DDL trong một số cấu hình, nhưng điều này không tự giải quyết mọi khác biệt về JDBC type hoặc schema validation.

Nếu không có yêu cầu dùng phần miền vượt `Long.MAX_VALUE`, chọn `BIGINT` signed và Java `Long` thường đơn giản hơn. Nếu yêu cầu thực sự cần unsigned toàn miền, viết integration test cho các giá trị sát `Long.MAX_VALUE`, lớn hơn `Long.MAX_VALUE` và sát `18446744073709551615`.

## 8. SQL mode ảnh hưởng đến lỗi dữ liệu số

Khi giá trị vượt miền cột, hành vi MySQL phụ thuộc `sql_mode`. Trong strict mode, giá trị out-of-range thường bị từ chối với lỗi. Trong chế độ không strict, MySQL có thể điều chỉnh về giá trị biên và phát warning. Điều này có thể khiến dữ liệu sai được ghi mà ứng dụng không nhận ra nếu chỉ kiểm tra số dòng update.

Kiểm tra chế độ đang dùng:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

Global mode và session mode có thể khác nhau. Test phải kiểm tra session của chính connection được dùng để chạy câu lệnh.

Ví dụ giá trị vượt miền `INT UNSIGNED`:

```sql
CREATE TABLE unsigned_probe (
    value INT UNSIGNED NOT NULL
) ENGINE=InnoDB;

INSERT INTO unsigned_probe (value) VALUES (4294967295);
```

Giá trị `4294967295` là biên hợp lệ. Giá trị `4294967296` vượt miền. Chạy test trên một transaction hoặc bảng riêng để không làm bẩn dữ liệu.

Sau câu lệnh có thể phát warning, kiểm tra ngay:

```sql
SHOW WARNINGS;
```

`SHOW WARNINGS` phải chạy ngay sau statement cần kiểm tra vì statement khác có thể thay thế danh sách warning. Không giả định mọi warning đều biến thành exception ở tầng JDBC; cấu hình strict mode và kiểm tra exception/warning theo chính sách ứng dụng.

### CHECK constraint cho quy tắc nghiệp vụ

Từ MySQL 8.0.16, `CHECK` constraint được thực thi. Ví dụ:

```sql
CREATE TABLE product_stock (
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    CONSTRAINT chk_stock_quantity CHECK (quantity >= 0),
    CONSTRAINT chk_stock_price CHECK (unit_price >= 0),
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`UNSIGNED` thể hiện miền không âm ở mức kiểu dữ liệu; `CHECK` thể hiện điều kiện nghiệp vụ. Có thể cần cả hai hoặc chỉ một tùy yêu cầu. Nếu hỗ trợ phiên bản cũ hơn 8.0.16, đừng giả định CHECK được thực thi; xác minh phiên bản MySQL đích.

## 9. Thiết kế bộ kiểm thử biên

Với mỗi cột số, xây dựng test case theo bốn vùng:

1. **Giá trị bình thường:** giá trị thường gặp trong nghiệp vụ.
2. **Giá trị biên hợp lệ:** nhỏ nhất, lớn nhất, zero, số âm nếu cho phép và giá trị có scale tối đa.
3. **Giá trị ngay ngoài biên:** nhỏ hơn min một đơn vị hoặc lớn hơn max một đơn vị ở độ chính xác lưu trữ.
4. **Giá trị chuyển đổi:** có scale dư, precision dư, giá trị lớn hơn kiểu Java hẹp hơn và giá trị null nếu cột cho phép.

Ví dụ ma trận cho `DECIMAL(8,2)`:

| Ca kiểm thử | Giá trị | Kết quả mong đợi |
|---|---:|---|
| Zero | `0.00` | Được lưu và đọc lại chính xác. |
| Số dương thường | `125.50` | Được lưu và đọc lại chính xác. |
| Giá trị lớn nhất | `999999.99` | Được lưu. |
| Giá trị nhỏ nhất signed | `-999999.99` | Được lưu nếu cột không UNSIGNED. |
| Vượt precision | `1000000.00` | Bị từ chối trong strict mode. |
| Có scale dư | `1.005` | Kiểm tra quy tắc làm tròn đến `1.01` trên MySQL exact DECIMAL. |
| Số âm ở cột UNSIGNED | `-0.01` | Bị từ chối trong strict mode; kiểm tra warning nếu không strict. |

Với `INT UNSIGNED`, test `0`, `1`, `2147483647`, `2147483648`, `4294967295` và `4294967296`. Với `BIGINT UNSIGNED`, test `9223372036854775807`, `9223372036854775808` và `18446744073709551615` bằng chuỗi thập phân hoặc `BigInteger`, không dùng literal `long` cho các giá trị vượt giới hạn.

## 10. Ví dụ integration test với Spring JDBC và JUnit

Test cần chạy trên MySQL thật, tốt nhất dùng cùng major/minor version với môi trường production. Ví dụ dùng `JdbcTemplate` để kiểm tra round-trip DECIMAL:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class DecimalMappingTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void decimalRoundTripPreservesValueAndScale() {
        BigDecimal input = new BigDecimal("1234567890123.4500");

        jdbc.update("INSERT INTO payment_probe(amount) VALUES (?)", input);

        BigDecimal actual = jdbc.queryForObject(
            "SELECT amount FROM payment_probe ORDER BY id DESC LIMIT 1",
            BigDecimal.class
        );

        assertThat(actual).isNotNull();
        assertThat(actual.compareTo(input)).isZero();
        assertThat(actual.scale()).isEqualTo(4);
    }
}
```

Fixture `payment_probe` cần được tạo bởi migration test hoặc `@Sql`:

```sql
CREATE TABLE payment_probe (
    id BIGINT NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Nếu dùng `@JdbcTest`, Spring Boot có thể thay datasource bằng database embedded khi cấu hình mặc định. Để kiểm tra MySQL semantics, dùng Testcontainers MySQL hoặc datasource test MySQL và cấu hình `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`.

### Test rounding và boundary

```java
@Test
void mysqlRoundsExactDecimalAtColumnScale() {
    jdbc.update("INSERT INTO decimal_probe(amount) VALUES (?)",
        new BigDecimal("1.005"));

    BigDecimal actual = jdbc.queryForObject(
        "SELECT amount FROM decimal_probe ORDER BY id DESC LIMIT 1",
        BigDecimal.class
    );

    assertThat(actual).isEqualByComparingTo("1.01");
}
```

Test này cần cột `DECIMAL(...,2)` và MySQL thật. Nó kiểm tra hành vi chuyển scale của MySQL, không thay thế test quy tắc làm tròn ở domain Java. Nên có test riêng cho `RoundingMode` trong service.

### Test UNSIGNED qua JDBC

```java
@Test
void readsUnsignedBigintAboveLongMaxValue() throws Exception {
    BigInteger expected = new BigInteger("9223372036854775808");

    jdbc.update(
        "INSERT INTO unsigned_probe_bigint(value) VALUES (?)",
        new BigDecimal(expected)
    );

    BigDecimal raw = jdbc.queryForObject(
        "SELECT value FROM unsigned_probe_bigint ORDER BY id DESC LIMIT 1",
        BigDecimal.class
    );

    assertThat(raw.toBigIntegerExact()).isEqualTo(expected);
}
```

Fixture:

```sql
CREATE TABLE unsigned_probe_bigint (
    id BIGINT NOT NULL AUTO_INCREMENT,
    value BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Test này chứng minh đường đi từ Java `BigInteger` qua `BigDecimal`/JDBC đến MySQL và đọc lại. Hãy bổ sung test sát giá trị tối đa unsigned và test lỗi nếu code vô tình dùng `getLong()`.

## 11. Kiểm tra metadata và ánh xạ runtime

Ngoài giá trị, kiểm tra kiểu cột mà MySQL thực sự tạo:

```sql
SHOW CREATE TABLE payment;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'payment'
ORDER BY ORDINAL_POSITION;
```

`COLUMN_TYPE` thể hiện chi tiết như `bigint unsigned`; `NUMERIC_PRECISION` và `NUMERIC_SCALE` giúp kiểm tra DECIMAL. Trong JDBC, có thể dùng `DatabaseMetaData.getColumns()` để kiểm tra `TYPE_NAME`, `COLUMN_SIZE` và `DECIMAL_DIGITS`. So sánh metadata với hợp đồng entity/migration để phát hiện schema drift.

Với Connector/J, kiểm tra kiểu thực tế từ `ResultSetMetaData` hoặc `ResultSet.getObject()` trên phiên bản driver đã khóa trong dependency management. Không viết code production phụ thuộc vào kiểu runtime chưa được kiểm thử khi driver được nâng cấp.

## 12. Kiểm thử với MySQL thật thay vì chỉ H2

H2 và MySQL có thể khác nhau về:

- Hỗ trợ và miền giá trị `UNSIGNED`.
- Hành vi `DECIMAL` khi làm tròn, overflow và phát warning.
- Cách áp dụng `sql_mode` và strict mode.
- Kiểu JDBC được trả về cho integer unsigned.
- DDL, constraint và schema validation của Hibernate dialect.
- Kiểu JSON, generated column và hàm riêng của MySQL.

Unit test có thể dùng H2 cho logic Java thuần, ví dụ phép tính `BigDecimal` và validation miền giá trị. Integration test về DECIMAL, UNSIGNED, JDBC mapping, strict mode và DDL phải chạy trên MySQL. Dùng Testcontainers giúp tạo một MySQL disposable có version được chỉ định, đồng thời tránh phụ thuộc vào database dùng chung.

Không chỉ kiểm thử một phiên bản MySQL bất kỳ. Nếu production đang chạy MySQL 8.4, test container nên dùng cùng nhánh và cấu hình `sql_mode` gần tương đương. Nếu nâng cấp MySQL hoặc Connector/J, chạy lại bộ test biên để phát hiện thay đổi mapping.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Số tiền lệch sau khi lưu | Dùng `double`, scale không rõ hoặc làm tròn ở nhiều tầng. | Dùng `BigDecimal`/`DECIMAL`, xác định một quy tắc rounding và test round-trip. |
| Test BigDecimal thất bại dù giá trị hiển thị giống nhau | `BigDecimal.equals()` phân biệt scale. | Dùng `compareTo()` cho so sánh số; kiểm tra `scale()` riêng nếu đó là yêu cầu. |
| `BIGINT UNSIGNED` bị âm hoặc lỗi khi đọc | Dùng `getLong()`/`Long` vượt `Long.MAX_VALUE`. | Dùng `getBigDecimal()` rồi chuyển `toBigIntegerExact()`; hoặc đổi schema sang signed BIGINT nếu phù hợp. |
| Giá trị vượt miền vẫn được ghi | Session không ở strict mode và MySQL điều chỉnh giá trị kèm warning. | Kiểm tra `@@SESSION.sql_mode`, `SHOW WARNINGS` và cấu hình strict mode. |
| Entity BigInteger không tương thích cột unsigned | Hibernate dialect/driver ánh xạ JDBC type khác dự kiến. | Kiểm tra DDL và metadata, viết integration test trên đúng Hibernate/Connector/J/MySQL. |
| Giá trị DECIMAL bị làm tròn khi insert | Scale cột nhỏ hơn scale đầu vào. | Xác định scale nghiệp vụ, chuẩn hóa trước khi persist và test đúng điểm làm tròn. |
| H2 pass nhưng MySQL fail | Hành vi kiểu số, UNSIGNED hoặc SQL mode khác nhau. | Chạy integration test trên MySQL thật hoặc Testcontainers. |

## 14. Bài tập thực hành

Một dịch vụ bán hàng lưu giá sản phẩm, số lượng tồn, tổng hóa đơn và một bộ đếm đồng bộ. Hãy thiết kế và kiểm thử trên MySQL:

1. Tạo `unit_price DECIMAL(19,4)`, `quantity INT UNSIGNED`, `invoice_total DECIMAL(20,4)` và `sync_counter BIGINT UNSIGNED`.
2. Ánh xạ `unit_price` và `invoice_total` sang `BigDecimal`; xác định kiểu Java phù hợp cho quantity và sync counter.
3. Viết service tính tổng bằng `BigDecimal`, chỉ rõ scale và `RoundingMode` ở từng bước nghiệp vụ.
4. Kiểm tra giá trị bình thường, zero, giá trị lớn nhất, giá trị âm, scale dư và precision overflow.
5. Kiểm tra miền `INT UNSIGNED` tại `0`, `2147483647`, `2147483648`, `4294967295` và `4294967296`.
6. Kiểm tra `BIGINT UNSIGNED` tại `Long.MAX_VALUE`, `Long.MAX_VALUE + 1` và giá trị tối đa bằng `BigInteger`.
7. Ghi và đọc dữ liệu qua JDBC, kiểm tra `BigDecimal`/`BigInteger` round-trip và metadata cột.
8. Chạy cùng test với strict mode và cấu hình không strict trong môi trường thử nghiệm; ghi nhận lỗi, warning và giá trị thực tế.
9. Chạy integration test trên MySQL thật cùng phiên bản production; so sánh kết quả với unit test logic Java.
10. Viết tài liệu hợp đồng cho từng field gồm miền giá trị, precision/scale, kiểu Java, cách làm tròn, nullability và hành vi khi vượt biên.

Sau bài tập, người học cần giải thích được vì sao tiền dùng `DECIMAL`/`BigDecimal`, vì sao `BigDecimal.equals()` có thể làm test sai, vì sao `BIGINT UNSIGNED` không thể ánh xạ toàn miền sang `long`, và vì sao strict mode cùng integration test trên MySQL là một phần của kiểm thử dữ liệu số. Đây là nền tảng để bảo đảm giá trị số không bị âm thầm thay đổi giữa Java, JDBC và MySQL.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual: Fixed-Point Types (Exact Value)](https://dev.mysql.com/doc/refman/8.4/en/fixed-point-types.html)
- [MySQL 8.4 Reference Manual: Integer Types](https://dev.mysql.com/doc/refman/8.4/en/integer-types.html)
- [MySQL 8.4 Reference Manual: Out-of-Range and Overflow Handling](https://dev.mysql.com/doc/refman/8.4/en/out-of-range-and-overflow.html)
- [MySQL 8.4 Reference Manual: SQL Modes](https://dev.mysql.com/doc/refman/8.4/en/sql-mode.html)
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [JDBC ResultSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Spring Boot Reference: Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)

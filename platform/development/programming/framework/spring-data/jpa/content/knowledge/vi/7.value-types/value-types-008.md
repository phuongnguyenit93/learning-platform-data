# Ánh xạ giá trị tiền tệ, mã nghiệp vụ và thời gian có quy tắc riêng trong Spring Data JPA

Nhiều thuộc tính nghiệp vụ không chỉ là String, BigDecimal hay LocalDate đơn giản. Một khoản tiền gồm số tiền và đơn vị tiền tệ; mã đơn hàng cần đúng định dạng; kỳ thanh toán có thể là YearMonth; khung giờ hoạt động có quy tắc mở cửa và đóng cửa. Nếu lưu các giá trị này như kiểu nguyên thủy ở khắp nơi, quy tắc dễ bị lặp lại và dữ liệu có thể không hợp lệ.

Spring Data JPA dựa trên JPA để ánh xạ mô hình Java xuống database. Ta có thể dùng kiểu cơ bản, @Embeddable để lưu value object trên nhiều cột, hoặc AttributeConverter để chuyển kiểu Java tùy chỉnh thành kiểu database cơ bản. Bài học này giải thích cách chọn chiến lược và xây dựng ví dụ tiền tệ, mã nghiệp vụ và kiểu thời gian có quy tắc riêng.

## 1. Value object và giá trị nghiệp vụ

Value object là đối tượng mô tả một giá trị theo ý nghĩa nghiệp vụ. Nó thường được so sánh theo giá trị thay vì định danh riêng, chứa các quy tắc hợp lệ và nên bất biến hoặc hạn chế thay đổi sau khi được tạo.

| Giá trị | Kiểu Java | Quy tắc thường gặp |
|---|---|---|
| Giá tiền | Money gồm BigDecimal và Currency | Không trộn tiền tệ, scale và làm tròn |
| Mã đơn hàng | OrderNumber | Đúng tiền tố, độ dài, ký tự và duy nhất |
| Mã ISBN | Isbn | Chuẩn hóa, kiểm tra định dạng/check digit |
| Kỳ thanh toán | YearMonth | Một tháng lịch, không có ngày hoặc giờ |
| Khung giờ mở cửa | BusinessHours | Giờ mở/đóng hợp lệ, có thể qua nửa đêm |
| Khoảng ngày | DateRange | Ngày bắt đầu trước ngày kết thúc |

Không phải mọi value object đều cần bảng riêng hoặc entity riêng. Nếu nó không có vòng đời và định danh độc lập, có thể ánh xạ nó thành thuộc tính của entity sở hữu.

## 2. Các chiến lược ánh xạ chính

**Kiểu cơ bản được JPA hỗ trợ:** dùng trực tiếp String, BigDecimal, LocalDate, LocalDateTime, Instant, Boolean hoặc enum. Đây là cách đơn giản nhất khi một thuộc tính tương ứng một cột.

~~~java
@Column(name = "unit_price", precision = 19, scale = 4, nullable = false)
private BigDecimal unitPrice;
~~~

**@Embeddable và @Embedded:** dùng khi value object gồm nhiều thuộc tính và lưu trên nhiều cột của cùng bảng.

~~~java
@Embeddable
public class Money {
    private BigDecimal amount;
    private String currencyCode;
}

@Entity
public class Product {
    @Embedded
    private Money price;
}
~~~

**AttributeConverter:** dùng khi kiểu Java tùy chỉnh có thể biểu diễn bằng một kiểu cơ bản của database, ví dụ OrderNumber thành VARCHAR hoặc YearMonth thành CHAR(7).

~~~java
@Converter
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {
    // Chuyển đổi hai chiều.
}
~~~

| Chiến lược | Số cột | Khi phù hợp | Ví dụ |
|---|---:|---|---|
| Basic mapping | Một cột | Kiểu JPA hỗ trợ trực tiếp | BigDecimal, LocalDate |
| @Embeddable | Một hoặc nhiều cột | Value object nhiều thành phần | Money, BusinessHours |
| AttributeConverter | Một kiểu database cơ bản | Kiểu tùy chỉnh có biểu diễn đơn giản | OrderNumber, YearMonth |
| Custom Hibernate type | Phụ thuộc | Kiểu JDBC/provider đặc thù | Kiểu riêng của DB |

Ưu tiên mapping chuẩn JPA để ứng dụng ít phụ thuộc Hibernate và dễ đổi database. Chỉ dùng custom Hibernate type khi basic mapping, embeddable và converter không đáp ứng được yêu cầu.

## 3. Ánh xạ tiền tệ: BigDecimal chưa đủ

BigDecimal phù hợp để lưu số thập phân chính xác hơn float hoặc double. Tuy nhiên, BigDecimal chỉ biểu diễn con số; nó không cho biết đó là USD, VND hay EUR. Không dùng double hoặc float cho giá tiền, số dư hay thuế vì phép tính dấu phẩy động nhị phân có thể tạo sai số.

Một giá trị tiền tệ thường cần amount (BigDecimal), currency (mã ISO 4217 như USD, EUR, VND) và quy tắc scale/làm tròn phù hợp nghiệp vụ. Không có một scale cố định đúng cho mọi tiền tệ và mọi nghiệp vụ. VND thường được biểu diễn với 0 chữ số thập phân trong giao dịch thông thường, USD thường 2 và một số tiền tệ có 3. Thuế, tỷ giá hoặc kế toán có thể yêu cầu precision riêng. Currency.getDefaultFractionDigits() chỉ là thông tin tham khảo, không thay thế chính sách làm tròn của nghiệp vụ.

## 4. Tạo Money value object bằng @Embeddable

Dùng cách này khi muốn lưu amount và currency ở hai cột riêng, đồng thời giữ chúng thành một giá trị thống nhất trong Java.

File Money.java:

~~~java
package com.example.shop.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Embeddable;

@Embeddable
public class Money {

    @Column(name = "amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal amount;

    @Convert(converter = CurrencyConverter.class)
    @Column(name = "currency_code", length = 3, nullable = false)
    private Currency currency;

    protected Money() {
    }

    public Money(BigDecimal amount, Currency currency) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);
        if (amount.scale() > 4) {
            throw new IllegalArgumentException(
                    "Amount supports at most 4 decimal places");
        }
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Currency getCurrency() {
        return currency;
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Cannot combine different currencies");
        }
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof Money other)) return false;
        return amount.compareTo(other.amount) == 0
                && currency.equals(other.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount.stripTrailingZeros(), currency);
    }
}
~~~

Money bảo vệ quy tắc cơ bản: amount và currency không được null, amount không vượt scale mà schema ví dụ hỗ trợ, và phép cộng/trừ chỉ thực hiện giữa cùng tiền tệ. Việc làm tròn chưa được tự động thực hiện; nghiệp vụ phải chọn rõ scale và RoundingMode.

### Chuyển Currency thành mã ISO trong database

Currency được chuyển thành mã chuỗi ba ký tự bằng AttributeConverter.

~~~java
package com.example.shop.domain;

import java.util.Currency;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class CurrencyConverter
        implements AttributeConverter<Currency, String> {

    @Override
    public String convertToDatabaseColumn(Currency currency) {
        return currency == null ? null : currency.getCurrencyCode();
    }

    @Override
    public Currency convertToEntityAttribute(String code) {
        return code == null ? null : Currency.getInstance(code);
    }
}
~~~

Currency.getInstance("USD") được lưu thành "USD"; khi đọc, converter tạo lại Currency. Nếu database chứa mã không hợp lệ, Currency.getInstance báo lỗi. Cần kiểm tra hoặc migration dữ liệu cũ trước khi bật converter.

### Nhúng Money vào entity

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "amount",
            column = @Column(name = "price_amount",
                precision = 19, scale = 4, nullable = false)),
        @AttributeOverride(name = "currency",
            column = @Column(name = "price_currency",
                length = 3, nullable = false))
    })
    private Money price;

    protected Product() {
    }

    public Product(String name, Money price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

Bảng products có các cột price_amount và price_currency. Hai cột cùng thuộc một Money trong entity. @AttributeOverrides cho phép đổi tên/cấu hình cột khi dùng cùng embeddable ở nhiều vị trí. Không cần @OneToOne hoặc bảng riêng vì Money không có identity độc lập.

## 5. Quy tắc tính toán và làm tròn tiền

BigDecimal hỗ trợ phép tính thập phân chính xác, nhưng phép chia có thể không cho kết quả thập phân hữu hạn. Cần chọn scale và RoundingMode rõ ràng.

~~~java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.10");

BigDecimal tax = subtotal
        .multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal total = subtotal.add(tax);

System.out.println(tax);
System.out.println(total);
~~~

Output:

~~~text
2.00
21.99
~~~

Nguyên tắc:

- Tạo BigDecimal từ chuỗi như new BigDecimal("19.99"), tránh new BigDecimal(19.99).
- Xác định scale theo nghiệp vụ: giá niêm yết, thuế, tỷ giá hoặc thanh toán.
- Chọn RoundingMode có chủ đích: HALF_UP, HALF_EVEN, DOWN, UP hoặc chế độ phù hợp khác.
- Không tự động làm tròn trong converter nếu điều đó làm mất dữ liệu.
- Khi cộng/trừ Money, kiểm tra currency giống nhau.
- Khi đổi tiền, cần tỷ giá, thời điểm áp dụng, nguồn tỷ giá và quy tắc làm tròn rõ ràng.

Database precision/scale là giới hạn lưu trữ; quy tắc làm tròn là quy tắc nghiệp vụ.

## 6. Ánh xạ mã nghiệp vụ bằng AttributeConverter

Mã đơn hàng là value object một cột. Ứng dụng muốn tránh truyền String tùy ý và bảo đảm định dạng ngay khi tạo đối tượng.

File OrderNumber.java:

~~~java
package com.example.shop.domain;

import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderNumber {

    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{8}");

    private final String value;

    public OrderNumber(String value) {
        Objects.requireNonNull(value);
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Order number must match ORD- followed by 8 digits");
        }
        this.value = value;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object object) {
        return object instanceof OrderNumber other
                && value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

OrderNumber là lớp bất biến: giá trị được kiểm tra trong constructor và không có setter. Nếu mã cần chuẩn hóa chữ hoa/thường, khoảng trắng hoặc dấu phân cách, hãy thực hiện nhất quán trước khi kiểm tra và lưu.

Converter:

~~~java
package com.example.shop.domain;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {

    @Override
    public String convertToDatabaseColumn(OrderNumber attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public OrderNumber convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new OrderNumber(dbData);
    }
}
~~~

Entity sử dụng converter:

~~~java
@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderNumberConverter.class)
    @Column(name = "order_number", nullable = false, unique = true, length = 12)
    private OrderNumber orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderNumber orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public OrderNumber getOrderNumber() {
        return orderNumber;
    }
}
~~~

Khi lưu PurchaseOrder, JPA gọi converter để ghi OrderNumber thành VARCHAR. Khi tải entity, JPA gọi converter để tạo lại OrderNumber. Constructor bảo vệ định dạng kể cả khi dữ liệu đến từ database.

Nên có unique constraint ở database cho mã cần duy nhất. Kiểm tra trùng trong Java trước khi insert không đủ để chống hai request đồng thời cùng tạo một mã; database constraint mới là lớp bảo vệ cuối cùng.

## 7. Dùng autoApply hay @Convert tường minh?

Có thể bật converter tự động:

~~~java
@Converter(autoApply = true)
public class OrderNumberConverter
        implements AttributeConverter<OrderNumber, String> {
    // Phần chuyển đổi như ví dụ trên.
}
~~~

Khi autoApply=true, converter được áp dụng cho các thuộc tính có kiểu Java phù hợp trong persistence unit theo quy tắc JPA. Cách này tiện khi mọi thuộc tính OrderNumber luôn có cùng biểu diễn database.

Nên dùng @Convert tường minh nếu chỉ một số trường cần converter, cùng một kiểu Java có nhiều cách biểu diễn, hoặc muốn thấy mapping ngay tại thuộc tính:

~~~java
@Convert(converter = OrderNumberConverter.class)
@Column(name = "order_number", length = 12)
private OrderNumber orderNumber;
~~~

Không nên bật autoApply cho kiểu có ý nghĩa rộng nhưng cần cách lưu khác nhau. Converter có giới hạn áp dụng theo đặc tả JPA; ví dụ không tự động chuyển các thuộc tính định danh, version, quan hệ hoặc thuộc tính đã xử lý bằng @Enumerated/@Temporal theo quy tắc tương ứng. Khi mapping phức tạp, kiểm tra đặc tả và hành vi của provider đang dùng.

## 8. Ánh xạ kiểu thời gian có quy tắc riêng bằng YearMonth

YearMonth biểu diễn một tháng lịch, ví dụ 2026-11. Nó không có ngày cụ thể hoặc giờ, phù hợp cho kỳ hóa đơn, kỳ lương và báo cáo tháng.

Chuyển YearMonth thành chuỗi ISO yyyy-MM:

~~~java
package com.example.shop.persistence;

import java.time.YearMonth;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class YearMonthConverter
        implements AttributeConverter<YearMonth, String> {

    @Override
    public String convertToDatabaseColumn(YearMonth attribute) {
        return attribute == null ? null : attribute.toString();
    }

    @Override
    public YearMonth convertToEntityAttribute(String dbData) {
        return dbData == null ? null : YearMonth.parse(dbData);
    }
}
~~~

Áp dụng trong entity:

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = YearMonthConverter.class)
    @Column(name = "billing_month", length = 7, nullable = false)
    private YearMonth billingMonth;

    protected Invoice() {
    }

    public Invoice(YearMonth billingMonth) {
        this.billingMonth = billingMonth;
    }

    public Long getId() {
        return id;
    }

    public YearMonth getBillingMonth() {
        return billingMonth;
    }
}
~~~

Cột billing_month có thể dùng CHAR(7) hoặc VARCHAR(7), tùy migration. Chuỗi ISO yyyy-MM sắp xếp từ điển theo thứ tự thời gian tăng dần nếu luôn dùng đúng định dạng và độ rộng.

## 9. Ánh xạ khung giờ có quy tắc bằng @Embeddable

Một cửa hàng có giờ mở cửa và đóng cửa. Chỉ lưu hai LocalTime là chưa đủ; cần quy tắc xác định khung giờ có thể qua nửa đêm hay không và khoảng đóng/mở được tính thế nào.

~~~java
package com.example.shop.domain;

import java.time.LocalTime;
import java.util.Objects;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class BusinessHours {

    @Column(name = "opens_at", nullable = false)
    private LocalTime opensAt;

    @Column(name = "closes_at", nullable = false)
    private LocalTime closesAt;

    @Column(name = "crosses_midnight", nullable = false)
    private boolean crossesMidnight;

    protected BusinessHours() {
    }

    public BusinessHours(
            LocalTime opensAt,
            LocalTime closesAt,
            boolean crossesMidnight) {
        this.opensAt = Objects.requireNonNull(opensAt);
        this.closesAt = Objects.requireNonNull(closesAt);
        this.crossesMidnight = crossesMidnight;

        if (opensAt.equals(closesAt)) {
            throw new IllegalArgumentException(
                    "Opening and closing times must differ");
        }

        boolean actuallyCrosses = closesAt.isBefore(opensAt);
        if (actuallyCrosses != crossesMidnight) {
            throw new IllegalArgumentException(
                    "crossesMidnight does not match the time range");
        }
    }

    public boolean contains(LocalTime time) {
        Objects.requireNonNull(time);
        if (crossesMidnight) {
            return !time.isBefore(opensAt) || time.isBefore(closesAt);
        }
        return !time.isBefore(opensAt) && time.isBefore(closesAt);
    }

    public LocalTime getOpensAt() {
        return opensAt;
    }

    public LocalTime getClosesAt() {
        return closesAt;
    }

    public boolean isCrossesMidnight() {
        return crossesMidnight;
    }
}
~~~

Entity sử dụng:

~~~java
@Entity
@Table(name = "stores")
public class Store {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Embedded
    private BusinessHours businessHours;

    protected Store() {
    }

    public Store(String name, BusinessHours businessHours) {
        this.name = name;
        this.businessHours = businessHours;
    }

    public boolean isOpenAt(LocalTime time) {
        return businessHours.contains(time);
    }
}
~~~

Ví dụ:

~~~java
BusinessHours daytime = new BusinessHours(
        LocalTime.of(8, 0), LocalTime.of(17, 0), false);
BusinessHours overnight = new BusinessHours(
        LocalTime.of(22, 0), LocalTime.of(6, 0), true);

System.out.println(daytime.contains(LocalTime.of(12, 0)));
System.out.println(overnight.contains(LocalTime.of(2, 0)));
~~~

Output:

~~~text
true
true
~~~

Ví dụ quy ước khoảng mở cửa bao gồm thời điểm bắt đầu và không bao gồm thời điểm đóng cửa. BusinessHours chỉ mô tả giờ trên đồng hồ; nếu cửa hàng hoạt động ở vùng có DST hoặc nhiều timezone, cần kết hợp thêm ngày và ZoneId để xác định instant thực tế.

## 10. Truy vấn repository với value object

Với OrderNumber được converter ánh xạ vào thuộc tính entity, có thể khai báo query method:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(OrderNumber orderNumber);

    boolean existsByOrderNumber(OrderNumber orderNumber);
}
~~~

Spring Data phân tích tên phương thức theo thuộc tính entity. Khi truy vấn thuộc tính đã được converter ánh xạ, JPA provider áp dụng conversion tương ứng khi bind tham số cho truy vấn JPQL/criteria theo mapping.

Với Money là embeddable, có thể truy vấn thuộc tính con:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    List<Product> findByPrice_CurrencyAndPrice_AmountGreaterThan(
            Currency currency,
            BigDecimal minimumAmount);
}
~~~

Dấu gạch dưới làm rõ đường dẫn thuộc tính lồng nhau: price.currency và price.amount. Cần lọc theo currency khi so sánh amount; 100 USD và 100 VND không phải cùng giá trị kinh tế.

JPQL cũng truy cập được thuộc tính embeddable:

~~~java
@Query("""
       select p
       from Product p
       where p.price.currency = :currency
         and p.price.amount >= :minimum
       """)
List<Product> findAtLeast(
        @Param("currency") Currency currency,
        @Param("minimum") BigDecimal minimum);
~~~

Với native query, SQL dùng tên cột thực tế như price_amount và price_currency. Việc chuyển đổi tham số native query có thể phụ thuộc provider và kiểu kết quả; cần kiểm tra với Hibernate/database đang triển khai, không giả định mọi native query xử lý converter giống JPQL.

## 11. Chọn @Embeddable, AttributeConverter hay entity

- Dùng @Embeddable khi value object gồm nhiều thuộc tính cần lưu ở nhiều cột, cần query từng thành phần hoặc muốn dùng @AttributeOverride.
- Dùng AttributeConverter khi kiểu Java chuyển thành một giá trị cơ bản duy nhất, ví dụ OrderNumber thành VARCHAR, YearMonth thành CHAR(7), Currency thành mã ISO.
- Dùng kiểu cơ bản nếu JPA đã hỗ trợ và không cần thêm quy tắc miền.
- Dùng @ElementCollection khi cần lưu tập hợp value object không có identity riêng; collection thường được lưu ở bảng phụ.
- Dùng entity riêng khi đối tượng có identity, vòng đời, quan hệ hoặc được quản lý độc lập.
- Dùng custom Hibernate type khi cần tích hợp kiểu JDBC/provider đặc thù và chấp nhận phụ thuộc Hibernate.

Không nên dùng converter cho object nhiều thành phần nếu phải nhồi dữ liệu vào chuỗi tự chế khó truy vấn. Cũng không nên tạo entity cho mọi value object, vì sẽ làm mô hình persistence phức tạp không cần thiết.

## 12. Null, validation và dữ liệu cũ

AttributeConverter nên xử lý null ở cả hai chiều. Nếu thuộc tính entity null, converter trả null; nếu database trả null, converter trả null. Ràng buộc nullable đặt ở entity mapping và schema theo đúng nghiệp vụ.

Các điểm cần kiểm tra:

- Value object từ chối giá trị sai ngay khi tạo, không đợi đến lúc lưu.
- Converter không chứa logic nghiệp vụ thay đổi dữ liệu âm thầm.
- Khi đọc dữ liệu cũ không hợp lệ, converter có thể ném exception; cần kế hoạch migration.
- Đặt unique constraint cho mã nghiệp vụ cần duy nhất.
- Dùng CHECK constraint khi database hỗ trợ và quy tắc có thể biểu diễn ở SQL.
- Giữ đồng nhất quy tắc chuẩn hóa ở API, domain và database.
- Với embedded value, xác định rõ toàn bộ value object có thể null hay mọi thành phần đều bắt buộc.

Không nên dùng converter để che giấu dữ liệu sai bằng cách trả về giá trị mặc định. Cách đó có thể khiến dữ liệu hỏng tiếp tục đi qua hệ thống mà không được phát hiện.

## 13. Migration và schema database

Mapping entity mô tả cách JPA nhìn dữ liệu. Trong ứng dụng thực tế, schema nên được quản lý bằng Flyway hoặc Liquibase thay vì dựa hoàn toàn vào Hibernate ddl-auto=update.

Ví dụ migration SQL minh họa:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price_amount DECIMAL(19, 4) NOT NULL,
    price_currency CHAR(3) NOT NULL,
    CONSTRAINT chk_price_amount_nonnegative
        CHECK (price_amount >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(12) NOT NULL UNIQUE
);

CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    billing_month CHAR(7) NOT NULL
);
~~~

Cú pháp identity có thể cần điều chỉnh theo database. Ví dụ này minh họa schema; hãy viết migration theo dialect thật của PostgreSQL, MySQL hoặc H2 mà dự án sử dụng.

Kiểm tra precision/scale của DECIMAL, độ dài currency_code, unique constraint của order_number, định dạng yyyy-MM của billing_month và tên cột embedded. Trong production, cấu hình Hibernate ddl-auto=validate hoặc none tùy quy trình migration; tránh để ứng dụng tự thay đổi schema ngoài kiểm soát.

## 14. Kiểm thử value object và converter

Kiểm thử domain object độc lập với database:

~~~java
@Test
void moneyRejectsDifferentCurrencies() {
    Money usd = new Money(
            new BigDecimal("10.00"), Currency.getInstance("USD"));
    Money eur = new Money(
            new BigDecimal("10.00"), Currency.getInstance("EUR"));

    assertThatThrownBy(() -> usd.add(eur))
            .isInstanceOf(IllegalArgumentException.class);
}

@Test
void orderNumberRejectsInvalidFormat() {
    assertThatThrownBy(() -> new OrderNumber("wrong"))
            .isInstanceOf(IllegalArgumentException.class);
}
~~~

Kiểm thử converter:

~~~java
@Test
void orderNumberConverterRoundTrips() {
    OrderNumberConverter converter = new OrderNumberConverter();
    OrderNumber original = new OrderNumber("ORD-12345678");

    String stored = converter.convertToDatabaseColumn(original);
    OrderNumber restored = converter.convertToEntityAttribute(stored);

    assertThat(stored).isEqualTo("ORD-12345678");
    assertThat(restored).isEqualTo(original);
}
~~~

Kiểm thử tích hợp JPA với @DataJpaTest:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void persistsMoneyAsAmountAndCurrency() {
        Money price = new Money(
                new BigDecimal("125.50"), Currency.getInstance("USD"));

        Product saved = repository.save(new Product("Keyboard", price));
        Product loaded = repository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getPrice()).isEqualTo(price);
        assertThat(loaded.getPrice().getCurrency().getCurrencyCode())
                .isEqualTo("USD");
    }
}
~~~

Test thực tế nên kiểm tra round-trip của value object, unique constraint, dữ liệu null, scale tiền tệ và derived query. Nếu dùng native query hoặc kiểu SQL đặc thù, chạy test với đúng database đích; H2 không bảo đảm tái hiện mọi khác biệt của PostgreSQL hoặc MySQL.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Converter không được gọi | Thiếu @Convert hoặc converter không được phát hiện | Kiểm tra annotation, package scan và persistence unit |
| Mã nghiệp vụ sai định dạng | Validation chỉ có ở API | Kiểm tra trong constructor/factory |
| Tiền mất độ chính xác | Dùng double/float hoặc scale SQL quá nhỏ | Dùng BigDecimal và DECIMAL phù hợp |
| Cộng Money khác currency | Không kiểm tra currency | Kiểm tra cùng mã tiền tệ hoặc chuyển đổi có tỷ giá |
| Currency không đọc được | Database chứa mã không hợp lệ | Làm sạch dữ liệu và kiểm tra mã ISO |
| YearMonth parse lỗi | Dữ liệu không theo yyyy-MM | Chuẩn hóa và migration dữ liệu |
| Cột embedded trùng tên | Nhiều embeddable dùng tên mặc định giống nhau | Dùng @AttributeOverride |
| Derived query không tạo được | Sai đường dẫn thuộc tính lồng nhau | Kiểm tra tên thuộc tính và dấu gạch dưới |
| Native query không map đúng | Tên cột/kiểu kết quả khác mapping | Kiểm tra SQL, alias và mapping |
| Dữ liệu sai lọt vào database | Chỉ validate ở Java | Thêm NOT NULL, UNIQUE, CHECK constraint |

## 16. Nguyên tắc thiết kế thực tế

- Đặt quy tắc hợp lệ trong value object để mọi luồng tạo dữ liệu đều được bảo vệ.
- Dùng @Embeddable cho giá trị nhiều thành phần cần lưu và truy vấn theo từng cột.
- Dùng AttributeConverter cho giá trị tùy chỉnh có biểu diễn database đơn giản.
- Chỉ bật autoApply khi cùng một kiểu Java luôn cần một cách lưu nhất quán.
- Không dùng double/float cho tiền tệ; xác định precision, scale và làm tròn theo nghiệp vụ.
- Lưu currency code cùng amount nếu dữ liệu có thể chứa nhiều tiền tệ.
- Dùng mã nghiệp vụ có validation và unique constraint ở database.
- Với thời gian có quy tắc riêng, biểu diễn rõ kiểu dữ liệu và timezone; không giấu quy tắc trong converter.
- Quản lý schema bằng migration và kiểm thử với database thực tế.
- Giữ converter đơn giản, xác định, có thể kiểm thử và không phụ thuộc request/session.

## 17. Checklist tự đánh giá

- [ ] Giải thích được value object và vì sao không phải mọi value object đều là entity.
- [ ] Phân biệt basic mapping, @Embeddable và AttributeConverter.
- [ ] Xây dựng Money bằng BigDecimal và Currency.
- [ ] Bảo đảm phép cộng/trừ tiền chỉ áp dụng cho cùng currency.
- [ ] Chọn precision, scale và RoundingMode theo quy tắc nghiệp vụ.
- [ ] Ánh xạ mã nghiệp vụ thành VARCHAR bằng converter.
- [ ] Biết khi nào bật autoApply và khi nào dùng @Convert tường minh.
- [ ] Ánh xạ YearMonth thành chuỗi yyyy-MM.
- [ ] Mô hình hóa khung giờ với @Embeddable và kiểm tra quy tắc qua nửa đêm.
- [ ] Truy vấn thuộc tính embedded bằng derived query hoặc JPQL.
- [ ] Thiết kế migration có NOT NULL, UNIQUE, CHECK và precision phù hợp.
- [ ] Kiểm thử domain object, converter và round-trip qua JPA.

## 18. Kết luận

Giá trị nghiệp vụ như tiền tệ, mã đơn hàng và kỳ thời gian cần được mô hình hóa cùng quy tắc của chúng. @Embeddable phù hợp với value object gồm nhiều thành phần như Money hoặc BusinessHours; AttributeConverter phù hợp với kiểu một cột như OrderNumber hoặc YearMonth. Kiểu cơ bản của JPA vẫn là lựa chọn tốt khi không cần lớp miền riêng.

Khi chọn chiến lược ánh xạ, hãy cân nhắc cấu trúc dữ liệu, khả năng truy vấn, tính di động giữa database và nơi đặt validation. Value object giữ quy tắc trong Java, converter/embeddable xác định cách lưu, còn constraint và migration bảo vệ dữ liệu ở database. Kết hợp đúng các lớp này giúp mô hình domain rõ ràng và dữ liệu nhất quán.

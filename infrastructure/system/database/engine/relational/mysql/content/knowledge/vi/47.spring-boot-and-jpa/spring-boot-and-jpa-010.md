# Ánh xạ JSON, enum, LOB, giá trị tiền tệ và thời gian

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này tập trung vào cách ánh xạ những kiểu dữ liệu thường gây sai lệch giữa MySQL và Java khi dùng Spring Boot, Spring Data JPA và Hibernate: JSON, enum, dữ liệu lớn (LOB), tiền tệ và thời gian.

Ánh xạ kiểu dữ liệu không chỉ là chọn annotation để ứng dụng chạy được. Cần bảo đảm kiểu Java diễn đạt đúng ý nghĩa nghiệp vụ, kiểu cột có đủ độ chính xác và dung lượng, JDBC driver chuyển đổi đúng, và dữ liệu vẫn giữ nguyên ý nghĩa khi đọc lại trên môi trường có timezone hoặc phiên bản khác. Các ví dụ dưới đây hướng tới Spring Boot 3.x, Jakarta Persistence và Hibernate ORM 6.x. Hãy kiểm tra tài liệu đúng phiên bản Hibernate, Spring Boot và MySQL Connector/J đang dùng trước khi áp dụng.

## 1. Nguyên tắc thiết kế ánh xạ entity

Khi thiết kế entity, hãy xác định trước bốn điều:

1. **Ý nghĩa dữ liệu:** giá trị là văn bản, byte thô, tài liệu JSON, trạng thái, số tiền hay một thời điểm tuyệt đối?
2. **Kiểu lưu trữ MySQL:** `JSON`, `VARCHAR`, `DECIMAL`, `DATE`, `DATETIME`, `TIMESTAMP`, `TEXT` hoặc `BLOB` có giới hạn và cách chuyển đổi khác nhau.
3. **Kiểu Java:** chọn `String`, enum, `BigDecimal`, `Instant`, `LocalDateTime`, `byte[]` hoặc kiểu miền nghiệp vụ tương ứng.
4. **Quy tắc chuyển đổi:** xác định timezone, scale, mã enum, encoding, null và hành vi khi giá trị không hợp lệ.

Không nên để Hibernate tự suy luận mọi kiểu cột trong production mà không kiểm tra DDL. Có thể dùng migration tool như Flyway hoặc Liquibase để quản lý schema; đặt `spring.jpa.hibernate.ddl-auto=validate` để Hibernate kiểm tra một phần tương thích giữa entity và schema lúc khởi động.

## 2. Ánh xạ JSON vào MySQL JSON

MySQL có kiểu `JSON` native. Khi ghi, MySQL kiểm tra cú pháp JSON và lưu dữ liệu ở định dạng nội bộ hỗ trợ truy cập thành phần. Nếu lưu JSON dưới dạng `TEXT`, MySQL chỉ xem đó là chuỗi văn bản, trừ khi ứng dụng tự kiểm tra hoặc dùng constraint/hàm JSON.

Với Hibernate 6, có thể dùng `@JdbcTypeCode(SqlTypes.JSON)` để yêu cầu Hibernate xử lý thuộc tính như JSON:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.Map;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preferences", columnDefinition = "json")
    private Map<String, Object> preferences;
}
```

Hibernate cần một JSON format mapper tương thích, thường được cung cấp bởi Jackson hoặc JSON-B tùy cấu hình và dependency của ứng dụng. Với Spring Boot, Jackson thường có sẵn khi dùng starter web, nhưng ứng dụng không dùng starter đó cần kiểm tra dependency thực tế. `columnDefinition = "json"` mô tả kiểu cột trong DDL do provider tạo; nếu schema do migration quản lý, migration vẫn phải tạo đúng cột JSON.

Có thể dùng một lớp Java rõ cấu trúc thay cho `Map`:

```java
public record CustomerPreferences(
    String language,
    boolean marketingOptIn,
    java.util.List<String> interests
) {}
```

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "preferences", columnDefinition = "json")
private CustomerPreferences preferences;
```

Kiểu cụ thể cần được JSON format mapper hỗ trợ. Lớp có cấu trúc giúp kiểm soát tên trường và kiểu dữ liệu tốt hơn `Map<String, Object>`, đặc biệt khi payload được dùng trong nhiều service.

### Lưu ý khi thay đổi cấu trúc JSON

- Xem JSON là một hợp đồng dữ liệu. Khi đổi tên hoặc xóa key, cần xem xét dữ liệu cũ và các phiên bản ứng dụng cùng đọc bảng.
- Không giả định mọi JSON đều có cùng shape. Dùng version field nếu schema JSON thay đổi theo thời gian.
- Trường được truy vấn thường xuyên nên cân nhắc generated column hoặc functional index thay vì quét toàn bộ JSON.
- Phân biệt SQL `NULL`, JSON literal `null` và object JSON không có key. Chúng có ngữ nghĩa khác nhau trong truy vấn.
- Không serialize dữ liệu nhạy cảm vào JSON nếu quyền đọc cả cột rộng hơn quyền đọc từng thuộc tính.

Ví dụ truy vấn một thuộc tính:

```sql
SELECT
    id,
    JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language')) AS language
FROM customer_profile
WHERE JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language')) = 'vi';
```

Nếu truy vấn theo `language` thường xuyên, có thể tạo generated column có index:

```sql
ALTER TABLE customer_profile
    ADD COLUMN preferred_language VARCHAR(10)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language'))
        ) STORED,
    ADD INDEX idx_customer_preferred_language (preferred_language);
```

Kiểm tra khả năng tạo generated column/index trên phiên bản MySQL đích và đo tác động DDL trên dữ liệu thật trước khi triển khai.

## 3. Ánh xạ enum an toàn

Enum Java phù hợp với tập trạng thái có số lượng hữu hạn, ví dụ trạng thái đơn hàng:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### Dùng EnumType.STRING

```java
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;

@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 24)
private OrderStatus status;
```

`EnumType.STRING` lưu tên enum như `PENDING` hoặc `SHIPPED`. Đây thường là lựa chọn an toàn hơn `EnumType.ORDINAL`, vì ordinal lưu vị trí số của phần tử. Nếu thêm một phần tử vào giữa danh sách enum, ordinal cũ có thể bị diễn giải thành trạng thái khác.

Tuy vậy, `EnumType.STRING` vẫn gắn dữ liệu database với tên hằng Java. Nếu đổi `SHIPPED` thành `DISPATCHED`, dữ liệu cũ có thể không còn chuyển đổi được. Không đổi tên enum một cách tùy tiện khi đã có dữ liệu production.

### Dùng AttributeConverter để lưu mã ổn định

Nếu hệ thống cần mã lưu trữ độc lập với tên hằng Java, dùng `AttributeConverter`:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        throw new IllegalArgumentException("Unknown order status code: " + code);
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus value) {
        return value == null ? null : value.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String value) {
        return value == null ? null : OrderStatus.fromCode(value);
    }
}
```

Áp dụng converter:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
```

Không đặt đồng thời `@Enumerated` và `@Convert` trên cùng thuộc tính. Khi thêm mã trạng thái mới, cần triển khai tương thích theo thứ tự: mở rộng schema hoặc constraint nếu có, triển khai code có thể đọc mã mới, sau đó mới ghi mã mới. Khi xóa mã cũ, xác nhận không còn bản ghi hoặc consumer phụ thuộc.

MySQL cũng có kiểu cột `ENUM`, nhưng việc dùng `@Enumerated` của JPA không có nghĩa ứng dụng tự động dùng đúng native enum theo ý muốn. Nếu chọn MySQL `ENUM`, cần quản lý DDL và mapping theo Hibernate dialect/version, đồng thời kiểm tra cách thêm giá trị và tương thích giữa các phiên bản ứng dụng. Với hệ thống cần thay đổi trạng thái thường xuyên, `VARCHAR` cùng validation ở domain thường dễ tiến hóa hơn.

## 4. Ánh xạ LOB: TEXT/CLOB và BLOB

LOB (Large Object) là dữ liệu lớn như nội dung bài viết, tài liệu, ảnh hoặc file đính kèm. Trong MySQL, văn bản thường dùng `TEXT`, `MEDIUMTEXT`, `LONGTEXT`; dữ liệu nhị phân dùng `BLOB`, `MEDIUMBLOB`, `LONGBLOB`.

Ví dụ entity:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;

@Lob
@Column(name = "body", columnDefinition = "LONGTEXT")
private String body;

@Lob
@Column(name = "file_content", columnDefinition = "LONGBLOB")
private byte[] fileContent;
```

`@Lob` biểu thị thuộc tính có ngữ nghĩa large object; `columnDefinition` chỉ định kiểu DDL cụ thể cho MySQL trong ví dụ. Hãy xác minh DDL được sinh bởi đúng Hibernate dialect và schema migration. MySQL không có kiểu CLOB riêng giống một số hệ quản trị khác; Hibernate dialect ánh xạ CLOB/BLOB sang kiểu MySQL tương ứng.

### Tránh tải LOB lớn ngoài nhu cầu

Một entity chứa `byte[]` có thể khiến toàn bộ nội dung được nạp vào heap khi thuộc tính được đọc. `@Basic(fetch = FetchType.LAZY)` trên basic/LOB là gợi ý cho provider và không phải lúc nào cũng được thực thi nếu ứng dụng chưa bật bytecode enhancement hoặc provider không hỗ trợ trường hợp đó.

```java
@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "file_content", columnDefinition = "LONGBLOB")
private byte[] fileContent;
```

Không dựa vào annotation LAZY mà bỏ qua kiểm thử SQL thực tế. Hãy bật SQL logging trong môi trường phát triển hoặc dùng Hibernate statistics để xác minh thời điểm cột LOB được tải.

Với file lớn, cân nhắc tách metadata và nội dung thành hai entity/bảng để truy vấn danh sách không kéo theo LOB:

```sql
CREATE TABLE attachment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    content_length BIGINT UNSIGNED NOT NULL,
    sha256 BINARY(32) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE attachment_content (
    attachment_id BIGINT UNSIGNED NOT NULL,
    content LONGBLOB NOT NULL,
    PRIMARY KEY (attachment_id),
    CONSTRAINT fk_attachment_content
        FOREIGN KEY (attachment_id) REFERENCES attachment(id)
) ENGINE=InnoDB;
```

Ứng dụng chỉ đọc metadata trong danh sách; chỉ tải bảng `attachment_content` khi người dùng thật sự tải file. Với file rất lớn, cân nhắc object storage và lưu URI/object key, checksum, MIME type cùng kích thước trong MySQL.

### LOB qua JPA hay JDBC stream?

`@Lob` tiện lợi cho các nội dung vừa phải, nhưng không bảo đảm Hibernate luôn truyền hoặc đọc theo stream mà không materialize toàn bộ giá trị. Khi cần xử lý file lớn với bộ nhớ giới hạn, có thể dùng JDBC `PreparedStatement.setBinaryStream()` / `setCharacterStream()` và `ResultSet.getBinaryStream()` / `getCharacterStream()` thông qua `JdbcTemplate` hoặc JDBC thuần.

Giữ stream và connection mở đến khi thao tác hoàn tất; tránh giữ transaction lâu trong khi client tải file qua mạng chậm. Cân nhắc giới hạn `max_allowed_packet`, timeout, redo/undo, binary log, replication lag và dung lượng backup.

## 5. Lưu tiền tệ bằng BigDecimal và DECIMAL

Không dùng `float` hoặc `double` cho số tiền cần tính toán chính xác. Các kiểu dấu phẩy động biểu diễn nhiều số thập phân bằng giá trị nhị phân gần đúng, có thể tạo sai số khi cộng, trừ hoặc so sánh.

Trong Java, dùng `BigDecimal`; trong MySQL, dùng `DECIMAL(p,s)`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("125000.75");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);
```

Tạo entity:

```java
@Column(name = "amount", precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

`precision` là tổng số chữ số; `scale` là số chữ số ở phần thập phân. Với `DECIMAL(19,4)`, có tối đa 19 chữ số, trong đó 4 chữ số ở phần thập phân. Chọn precision/scale theo giới hạn nghiệp vụ, không sao chép một con số cho mọi hệ thống.

### Quy tắc tiền tệ cần xác định rõ

- Lưu mã tiền tệ riêng, ví dụ `VND`, `USD`, `JPY`; không suy ra currency chỉ từ số tiền.
- Không mặc định mọi loại tiền có hai chữ số thập phân. Scale và quy tắc làm tròn phụ thuộc currency và nghiệp vụ.
- Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(double)` nếu buộc phải nhận số double; tránh `new BigDecimal(0.1)` vì constructor đó giữ giá trị nhị phân gần đúng của double.
- Xác định thời điểm làm tròn: mỗi dòng, tổng hóa đơn, thuế hay chỉ khi ghi sổ. Kết quả khác nhau nếu làm tròn ở các giai đoạn khác nhau.
- Kiểm tra overflow và scale trước khi persist; không dựa vào việc database tự làm tròn theo cách ngầm định.

Ví dụ bảng:

```sql
CREATE TABLE payment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Nếu nghiệp vụ chỉ cần số nguyên đơn vị nhỏ nhất (minor units), có thể lưu bằng `BIGINT` cùng mã currency, nhưng phải xử lý đúng số chữ số lẻ theo từng currency và không trộn các đơn vị khác nhau trong cùng phép tính.

## 6. Ánh xạ ngày và thời gian

Java cung cấp nhiều kiểu thời gian vì chúng biểu diễn những khái niệm khác nhau. Chọn sai kiểu có thể gây lệch giờ khi ứng dụng chạy ở nhiều timezone hoặc khi có chuyển đổi giờ mùa hè (DST).

| Kiểu Java | Ý nghĩa | Kiểu MySQL thường dùng |
|---|---|---|
| `LocalDate` | Ngày lịch, không có giờ và timezone. | `DATE` |
| `LocalTime` | Giờ trong ngày, không có ngày và timezone. | `TIME` |
| `LocalDateTime` | Ngày giờ địa phương, không chứa offset/timezone. | `DATETIME(6)` |
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC. | Thường dùng `TIMESTAMP(6)` hoặc `DATETIME(6)` theo quy ước UTC của ứng dụng. |
| `OffsetDateTime` | Ngày giờ kèm UTC offset. | MySQL không có kiểu lưu offset như một phần giá trị; cần quy ước chuyển đổi và lưu offset riêng nếu phải giữ nguyên. |
| `ZonedDateTime` | Ngày giờ cùng ZoneId như `Asia/Ho_Chi_Minh`. | Thường lưu instant và ZoneId riêng nếu cần khôi phục múi giờ gốc. |

### TIMESTAMP và DATETIME khác nhau

- `TIMESTAMP` được MySQL chuyển đổi từ timezone session sang UTC khi lưu và từ UTC sang timezone session khi đọc. Nó biểu diễn một instant, nhưng có giới hạn phạm vi ngày hẹp hơn `DATETIME` (trên MySQL phổ biến đến năm 2038).
- `DATETIME` lưu thành phần ngày/giờ như được cung cấp và không tự chuyển đổi theo timezone session. Nó phù hợp với thời gian địa phương như giờ mở cửa hoặc lịch hẹn tại một địa điểm, nếu ứng dụng quản lý timezone riêng.
- Cả hai hỗ trợ fractional seconds; `DATETIME(6)` và `TIMESTAMP(6)` lưu đến microsecond. Java `Instant` có độ chính xác nano giây, nên cần chấp nhận việc MySQL/JDBC có thể làm tròn hoặc cắt xuống độ chính xác cột.

### Lưu thời điểm sự kiện bằng Instant

Với `createdAt`, `paidAt` hoặc thời điểm một sự kiện xảy ra, dùng `Instant` để biểu diễn một thời điểm tuyệt đối:

```java
import java.time.Instant;

@Column(name = "created_at", nullable = false,
        columnDefinition = "timestamp(6)")
private Instant createdAt;
```

Đặt quy ước UTC thống nhất cho Hibernate và Connector/J. Ví dụ cấu hình Spring Boot:

```yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.com:3306/shop?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate.jdbc.time_zone: UTC
```

`connectionTimeZone`, `forceConnectionTimeZoneToSession` và `preserveInstants` là thuộc tính Connector/J; hãy dùng phiên bản driver hỗ trợ chúng. `hibernate.jdbc.time_zone` hướng dẫn Hibernate/JDBC dùng timezone chỉ định khi bind/extract các giá trị thời gian phù hợp. Xác minh `@@session.time_zone`, `@@global.time_zone` và giá trị runtime trên kết nối thật.

MySQL `TIMESTAMP` có giới hạn trên năm 2038 trong các phiên bản phổ biến. Nếu nghiệp vụ cần lưu thời điểm xa hơn, ví dụ lịch dự kiến nhiều thập kỷ trong tương lai, cân nhắc `DATETIME(6)` theo quy ước UTC rõ ràng hoặc lưu epoch cùng quy tắc miền nghiệp vụ.

### Lưu thời gian địa phương bằng LocalDateTime

Với lịch hẹn hoặc thời gian mở cửa, `LocalDateTime` cùng `DATETIME(6)` có thể phù hợp:

```java
import java.time.LocalDateTime;

@Column(name = "appointment_at", nullable = false,
        columnDefinition = "datetime(6)")
private LocalDateTime appointmentAt;
```

Nếu thời gian gắn với một địa điểm, lưu thêm ZoneId như `Asia/Ho_Chi_Minh`:

```java
@Column(name = "appointment_zone", nullable = false, length = 64)
private String appointmentZone;
```

Một `LocalDateTime` như `2026-11-19T09:00` tự nó không xác định được một instant. Nếu hệ thống cần gửi nhắc lịch chính xác qua nhiều timezone, phải kết hợp ngày giờ với ZoneId và quy tắc xử lý DST.

### OffsetDateTime và ZonedDateTime

MySQL `TIMESTAMP` và `DATETIME` không lưu nguyên UTC offset hoặc ZoneId như `+07:00` hay `Asia/Ho_Chi_Minh`. Hibernate có thể chuẩn hóa thời điểm khi ghi, tùy cấu hình `hibernate.timezone.default_storage` và kiểu SQL được chọn, nhưng không nên giả định offset ban đầu sẽ được khôi phục chính xác.

Nếu cần bảo toàn cả thời điểm và timezone gốc, lưu hai thông tin: instant (UTC) và ZoneId/offset riêng. ZoneId có giá trị hơn offset cố định khi cần áp dụng quy tắc timezone lịch sử hoặc tương lai.

## 7. Kết hợp các kiểu trong một entity

Ví dụ entity đơn hàng minh họa enum, JSON, tiền tệ và thời gian:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "currency", nullable = false, length = 3)
    private String currency;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "attributes", columnDefinition = "json")
    private Map<String, Object> attributes;

    @Column(name = "created_at", nullable = false,
            columnDefinition = "timestamp(6)")
    private Instant createdAt;
}
```

Ví dụ này dùng `EnumType.STRING` cho dễ đọc. Nếu chọn mã trạng thái ổn định, thay `@Enumerated` bằng `@Convert` như phần enum ở trên. Không đặt cả hai trên cùng field.

DDL tương ứng có thể được quản lý bằng migration:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    attributes JSON NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Kiểu `BIGINT UNSIGNED` trong MySQL có miền giá trị lớn hơn `Long` Java có dấu. Nếu dùng `Long` làm ID, hãy bảo đảm giá trị không vượt `Long.MAX_VALUE`, hoặc chọn kiểu/chiến lược ID tương thích với miền giá trị của ứng dụng.

## 8. Schema migration và tương thích entity

Trong production, tránh để nhiều instance ứng dụng cùng tự động thay đổi schema bằng `ddl-auto=update`. Dùng migration có kiểm soát để thay đổi kiểu cột, độ dài, precision/scale và index.

Một thay đổi enum nên theo hướng mở rộng trước:

1. Cho phép code mới đọc cả giá trị cũ và mới.
2. Cập nhật constraint hoặc dữ liệu cần thiết bằng migration.
3. Triển khai ứng dụng ghi giá trị mới.
4. Xác nhận mọi consumer đã hiểu giá trị mới.
5. Chỉ loại bỏ giá trị cũ sau khi không còn bản ghi hoặc instance dùng nó.

Với JSON, nếu đổi cấu trúc payload, có thể ghi thêm `schemaVersion` trong tài liệu. Khi đọc, ứng dụng xử lý các version cũ hoặc migration chuyển đổi dữ liệu theo lô.

Với tiền tệ, thay đổi precision/scale có thể làm migration thất bại hoặc thay đổi giá trị. Trước khi tăng/giảm scale, thống kê giá trị lớn nhất, số chữ số thập phân đang dùng và quy tắc làm tròn.

Với thời gian, thay đổi `DATETIME` sang `TIMESTAMP` không chỉ là đổi kiểu cột. Cần xác định timezone của dữ liệu cũ, timezone session trong quá trình migration và cách chuyển đổi để không dịch chuyển thời điểm.

## 9. Kiểm thử round-trip và các trường hợp biên

Kiểm thử mapping phải ghi dữ liệu bằng ứng dụng rồi đọc lại bằng ứng dụng và SQL. Không chỉ kiểm tra entity được persist mà không có exception.

| Nhóm dữ liệu | Ca kiểm thử cần có | Điều cần xác minh |
|---|---|---|
| JSON | Object rỗng, key thiếu, array lồng nhau, Unicode, JSON null, SQL NULL, payload version cũ. | Cấu trúc và kiểu giá trị được giữ đúng; MySQL từ chối JSON sai cú pháp. |
| Enum | Mỗi trạng thái, null nếu cho phép, mã không được biết, thêm trạng thái mới. | Không bị diễn giải nhầm ordinal; converter xử lý mã lạ theo chính sách rõ ràng. |
| LOB | File rỗng, file lớn, byte 0x00, Unicode, file có checksum đã biết. | Byte không đổi; không bị cắt; bộ nhớ JVM không tăng tuyến tính ngoài dự kiến. |
| Tiền tệ | Số có nhiều chữ số thập phân, giá trị sát giới hạn, số âm nếu nghiệp vụ cho phép, nhiều currency. | Precision/scale và quy tắc làm tròn đúng; không có sai số floating point. |
| Thời gian | UTC, timezone khác, DST gap/overlap, microsecond, ngày xa trong tương lai. | Instant không đổi; LocalDateTime giữ đúng giờ địa phương; độ chính xác phù hợp cột. |

Nên chạy test trên MySQL thật cùng phiên bản gần production. H2 hoặc database in-memory khác có thể có hành vi JSON, enum, LOB, decimal và timezone khác MySQL.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hibernate không ghi được JSON | Thiếu JSON format mapper, sai `@JdbcTypeCode` hoặc schema không phải kiểu JSON. | Kiểm tra Hibernate version/dependency, mapping và DDL; chạy test persist/read trên MySQL. |
| Đổi tên enum làm lỗi đọc dữ liệu | `EnumType.STRING` tìm hằng Java theo tên cũ. | Dùng converter mã ổn định hoặc migration dữ liệu có kế hoạch tương thích. |
| Enum lưu ordinal sai sau khi thêm phần tử | Entity dùng `EnumType.ORDINAL`. | Chuyển sang STRING hoặc converter; migration dữ liệu trước khi đổi mapping. |
| LOB làm tăng heap hoặc response chậm | Hibernate materialize `byte[]`/`String`, truy vấn tải LOB không cần thiết. | Tách bảng nội dung, chỉ tải khi cần hoặc dùng JDBC stream cho file lớn. |
| Tiền bị lệch vài đơn vị nhỏ | Dùng `double`/`float`, scale không thống nhất hoặc làm tròn ở sai bước. | Dùng `BigDecimal`, DECIMAL và quy tắc làm tròn nghiệp vụ rõ ràng. |
| Thời gian lệch giờ sau deploy | JVM, Connector/J, Hibernate hoặc MySQL session dùng timezone khác nhau. | Thống nhất UTC cho instant, kiểm tra session timezone và cấu hình driver/Hibernate. |
| Mất offset sau khi đọc OffsetDateTime | MySQL không lưu offset/ZoneId trong TIMESTAMP hoặc DATETIME. | Lưu instant và offset/ZoneId riêng nếu cần giữ nguyên thông tin ban đầu. |
| Migration thay DATETIME/TIMESTAMP làm dịch chuyển dữ liệu | Dữ liệu cũ được hiểu theo timezone khác với giả định migration. | Xác định timezone nguồn, chụp backup và chuyển đổi trên staging trước khi áp dụng. |

## 11. Bài tập thực hành

Xây dựng một Spring Boot service quản lý đơn hàng và tài liệu đính kèm trên MySQL. Thực hiện các yêu cầu:

1. Tạo entity `OrderEntity` có trạng thái enum, tổng tiền `BigDecimal`, mã currency, thuộc tính JSON và thời điểm tạo `Instant`.
2. Tạo migration MySQL dùng `VARCHAR`, `DECIMAL`, `JSON` và `TIMESTAMP(6)` tương ứng; cấu hình Hibernate `ddl-auto=validate`.
3. Persist và đọc JSON lồng nhau; thử truy vấn một key và đánh giá generated column/index cho trường thường lọc.
4. Thêm enum trạng thái mới; kiểm tra `EnumType.STRING` hoặc converter mã ổn định và lập kế hoạch triển khai tương thích.
5. Ghi số tiền có nhiều scale, kiểm tra rounding, overflow và dữ liệu nhiều currency.
6. Ghi một sự kiện với `Instant`, đổi timezone JVM/session để đọc lại và xác minh instant không thay đổi.
7. Lưu lịch hẹn bằng `LocalDateTime` cùng ZoneId, kiểm thử trường hợp DST gap/overlap ở timezone có áp dụng DST.
8. Lưu file PDF bằng LOB; kiểm tra checksum sau khi đọc lại. So sánh cách JPA materialize LOB với JDBC streaming trên file lớn.
9. Chạy test round-trip trên MySQL thật, ghi lại SQL, kiểu cột thực tế và mọi khác biệt so với schema mong đợi.
10. Viết tài liệu mapping cho từng field: kiểu Java, kiểu MySQL, precision/scale hoặc timezone, nullability, quy tắc chuyển đổi và chiến lược migration.

Sau bài tập, người học cần giải thích được vì sao JSON nên dùng kiểu JSON native, vì sao enum ordinal dễ gây lỗi dữ liệu, vì sao LOB lớn cần chiến lược streaming hoặc tách bảng, vì sao tiền tệ dùng `BigDecimal`/`DECIMAL`, và vì sao phải phân biệt instant với thời gian địa phương. Đây là nền tảng để dữ liệu giữa Spring Boot, Hibernate và MySQL giữ đúng ý nghĩa trong suốt vòng đời ứng dụng.

## Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide: Basic Types and JSON mapping](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Spring Boot Reference: Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [MySQL 8.4 Reference Manual: The JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
- [MySQL 8.4 Reference Manual: Date and Time Data Types](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-types.html)
- [MySQL 8.4 Reference Manual: Fixed-Point Types](https://dev.mysql.com/doc/refman/8.4/en/fixed-point-types.html)

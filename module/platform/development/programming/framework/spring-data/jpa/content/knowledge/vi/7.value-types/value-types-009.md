# Lựa chọn kiểu chuẩn JPA hoặc kiểu đặc thù nhà cung cấp

Khi ánh xạ thuộc tính Entity, nhà phát triển cần chọn kiểu Java và cách ánh xạ phù hợp với dữ liệu nghiệp vụ, database và JPA provider. Có hai hướng chính: dùng kiểu và annotation được Jakarta Persistence chuẩn hóa để tăng khả năng di chuyển giữa các hệ quản trị, hoặc dùng kiểu/annotation riêng của nhà cung cấp như Hibernate để khai thác tính năng đặc thù của database.

Lựa chọn này ảnh hưởng đến schema, cách JDBC đọc/ghi dữ liệu, khả năng chạy trên nhiều database, truy vấn, migration và chi phí bảo trì. Nguyên tắc thực tế là **ưu tiên mapping chuẩn JPA cho dữ liệu thông thường; chỉ dùng mapping đặc thù khi có yêu cầu rõ ràng và đã kiểm thử trên database mục tiêu**.

## 1. Kiểu dữ liệu trong Entity đi qua những lớp nào?

Một thuộc tính Entity không được ghi thẳng từ Java xuống database. JPA provider chuyển giá trị Java sang biểu diễn JDBC và SQL phù hợp với database.

Luồng tổng quát:

~~~text
Thuộc tính trong Entity (Java)
          |
          v
JPA mapping / AttributeConverter
          |
          v
Hibernate hoặc JPA provider
          |
          v
JDBC type và PreparedStatement
          |
          v
Kiểu cột và giá trị trong database
~~~

Ví dụ, thuộc tính Java BigDecimal có thể được ánh xạ thành DECIMAL hoặc NUMERIC. Thuộc tính LocalDate thường được lưu dưới dạng kiểu DATE. Kiểu vật lý và chi tiết chuyển đổi còn phụ thuộc dialect, JDBC driver và schema thực tế.

Cần phân biệt ba khái niệm:

- **Kiểu Java:** kiểu được khai báo trong Entity, ví dụ String, BigDecimal, LocalDate hoặc UUID.
- **Kiểu JDBC:** kiểu mà driver dùng để truyền/nhận giá trị, ví dụ VARCHAR, DECIMAL, DATE hoặc BINARY.
- **Kiểu SQL:** kiểu cột được định nghĩa trong database, ví dụ VARCHAR(100), NUMERIC(12,2), DATE, JSONB hoặc BYTEA.

Tên và khả năng của ba lớp này có liên quan nhưng không phải lúc nào cũng giống nhau. Một kiểu Java có thể được ánh xạ thành nhiều kiểu SQL tùy database và provider.

## 2. Thế nào là mapping chuẩn JPA?

Mapping chuẩn JPA sử dụng các kiểu Java, annotation và API được quy định bởi Jakarta Persistence. Các mapping này thường dễ chuyển đổi giữa Hibernate và provider khác, hoặc giữa các hệ quản trị database được hỗ trợ.

Một số nhóm kiểu cơ bản thường dùng:

| Nhóm dữ liệu | Kiểu Java thường dùng | Ý nghĩa |
|---|---|---|
| Văn bản | String, Character, char | Chuỗi hoặc ký tự |
| Số nguyên | Byte, Short, Integer, Long và primitive tương ứng | Số nguyên |
| Số thực | Float, Double | Số dấu phẩy động |
| Số thập phân chính xác | BigDecimal, BigInteger | Tiền tệ, số cần độ chính xác |
| Logic | Boolean, boolean | Đúng/sai |
| Ngày giờ | LocalDate, LocalTime, LocalDateTime, OffsetDateTime, Instant và các kiểu được JPA hỗ trợ | Ngày, giờ, thời điểm |
| Nhị phân | byte[], Byte[] | Dữ liệu byte |
| Enum | Kiểu enum Java | Tập giá trị hữu hạn |
| Định danh | UUID trong các phiên bản JPA hỗ trợ | Mã định danh |

Danh sách và chi tiết hỗ trợ phụ thuộc phiên bản Jakarta Persistence. Ví dụ, hỗ trợ UUID như basic type và chiến lược sinh UUID được chuẩn hóa trong Jakarta Persistence 3.1. Dự án cũ có thể phụ thuộc vào khả năng riêng của provider.

Ví dụ Entity sử dụng các kiểu phổ biến:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    private LocalDate invoiceDate;

    private OffsetDateTime createdAt;

    @Enumerated(EnumType.STRING)
    private InvoiceStatus status;

    protected Invoice() {
    }
}

enum InvoiceStatus {
    DRAFT,
    ISSUED,
    PAID,
    CANCELLED
}
~~~

Các kiểu trên diễn tả rõ ý nghĩa nghiệp vụ và có hỗ trợ chuẩn trong các phiên bản JPA phù hợp. Provider vẫn quyết định chi tiết ánh xạ SQL theo dialect.

## 3. Khi nào nên ưu tiên kiểu chuẩn JPA?

Nên ưu tiên mapping chuẩn khi:

- Ứng dụng có khả năng chuyển từ PostgreSQL sang MySQL, Oracle hoặc database khác.
- Dự án muốn đổi JPA provider hoặc giảm phụ thuộc vào Hibernate.
- Thuộc tính chỉ cần biểu diễn dữ liệu thông thường như số, chuỗi, ngày giờ, enum hoặc UUID.
- Schema được quản lý bằng migration và cần giữ tính nhất quán giữa môi trường.
- Nhiều nhóm cùng phát triển và cần cách ánh xạ dễ đọc, dễ review.

Ví dụ, dùng LocalDate cho ngày hóa đơn giúp biểu diễn đúng ý nghĩa ngày lịch, không gắn với múi giờ. Dùng BigDecimal cho tiền giúp tránh sai số nhị phân của double. Dùng EnumType.STRING giúp lưu tên trạng thái dễ đọc hơn ordinal.

Mapping chuẩn không có nghĩa mọi database sẽ có cùng giới hạn, hiệu năng hay kiểu SQL vật lý. Nó giúp chuẩn hóa hợp đồng ở tầng JPA, còn schema và hành vi vẫn cần được kiểm tra trên database đích.

## 4. Ánh xạ số chính xác với BigDecimal

Với dữ liệu tiền tệ hoặc đại lượng cần độ chính xác thập phân, nên dùng BigDecimal thay cho double hoặc float.

~~~java
@Column(precision = 14, scale = 2, nullable = false)
private BigDecimal amount;
~~~

- precision là tổng số chữ số được lưu.
- scale là số chữ số ở phần thập phân.
- precision = 14, scale = 2 cho phép tối đa 12 chữ số ở phần nguyên và 2 chữ số ở phần thập phân theo định nghĩa kiểu DECIMAL/NUMERIC.

Ví dụ:

~~~java
BigDecimal price = new BigDecimal("1250.50");
BigDecimal tax = new BigDecimal("100.00");
BigDecimal total = price.add(tax);

System.out.println(total);
~~~

Stdout:

~~~text
1350.50
~~~

Không nên tạo BigDecimal từ literal double như new BigDecimal(0.1), vì giá trị double đã có biểu diễn nhị phân xấp xỉ. Dùng chuỗi hoặc BigDecimal.valueOf(...) khi phù hợp.

Precision và scale trong @Column chủ yếu cung cấp metadata cho mapping/DDL. Chúng không thay thế validation nghiệp vụ. Hãy kiểm tra giá trị đầu vào, làm tròn theo quy tắc tiền tệ và xử lý trường hợp vượt giới hạn cột.

## 5. Ánh xạ ngày giờ bằng kiểu Java hiện đại

Với dự án mới, nên ưu tiên các kiểu java.time có ý nghĩa rõ ràng:

- LocalDate: ngày lịch, không có giờ hoặc múi giờ, ví dụ ngày sinh hoặc ngày hóa đơn.
- LocalTime: giờ trong ngày, không có ngày.
- LocalDateTime: ngày và giờ địa phương, không chứa offset hoặc timezone.
- OffsetDateTime: ngày giờ kèm UTC offset.
- Instant: một thời điểm trên dòng thời gian UTC.

Ví dụ:

~~~java
@Column(nullable = false)
private LocalDate dueDate;

private LocalDateTime scheduledAt;

private OffsetDateTime submittedAt;
~~~

Không nên dùng LocalDateTime để thay thế một thời điểm toàn cầu nếu nghiệp vụ cần xác định chính xác một instant. LocalDateTime không chứa thông tin múi giờ; cùng một giá trị có thể đại diện cho các thời điểm khác nhau ở những vùng khác nhau.

Với dữ liệu thời điểm sự kiện, một lựa chọn phổ biến là lưu Instant hoặc OffsetDateTime theo quy ước UTC của hệ thống. Cần xác định cách database và Hibernate xử lý timezone, độ chính xác timestamp và cấu hình JDBC. Việc lưu offset có được giữ nguyên hay chuẩn hóa phụ thuộc kiểu cột và provider.

Các kiểu java.util.Date hoặc Calendar trong mapping cũ có thể cần @Temporal. Không dùng @Temporal cho LocalDate, LocalTime hoặc LocalDateTime; các kiểu java.time được ánh xạ theo hỗ trợ JPA tương ứng.

## 6. Enum: dùng STRING hay ORDINAL?

JPA cung cấp @Enumerated để ánh xạ enum. Nếu không chỉ định, mặc định truyền thống là EnumType.ORDINAL, nghĩa là lưu vị trí số của hằng enum.

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    SHIPPED,
    CANCELLED
}
~~~

Ánh xạ ordinal:

~~~java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
~~~

Ví dụ NEW có thể lưu thành 0, PROCESSING thành 1. Nếu thêm hoặc sắp xếp lại hằng enum, ý nghĩa của các số đã lưu có thể thay đổi. Điều này gây nguy cơ đọc sai dữ liệu cũ.

Thường nên dùng STRING:

~~~java
@Enumerated(EnumType.STRING)
@Column(nullable = false, length = 30)
private OrderStatus status;
~~~

Database lưu tên hằng như NEW hoặc PROCESSING. Cách này dễ đọc và không bị đổi ý nghĩa chỉ vì thứ tự enum thay đổi.

Tuy nhiên, đổi tên một hằng enum cũng ảnh hưởng dữ liệu đã lưu. Nếu đổi PROCESSING thành IN_PROGRESS, cần migration dữ liệu hoặc chiến lược tương thích khi đọc. Nếu cần giá trị lưu ổn định độc lập với tên hằng Java, hãy dùng AttributeConverter để ánh xạ enum sang mã nghiệp vụ tường minh.

## 7. UUID và mức hỗ trợ theo phiên bản

UUID là lựa chọn phù hợp khi cần ID phân tán, có thể tạo ở nhiều service mà không phải hỏi database để lấy số tăng tuần tự.

Với Jakarta Persistence 3.1 trở lên, UUID là kiểu cơ bản được hỗ trợ và có thể dùng chiến lược sinh UUID:

~~~java
import jakarta.persistence.*;
import java.util.UUID;

@Entity
public class ApiToken {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    private String description;

    protected ApiToken() {
    }
}
~~~

Repository:

~~~java
public interface ApiTokenRepository
        extends JpaRepository<ApiToken, UUID> {
}
~~~

Nếu dự án dùng JPA cũ, khả năng mapping UUID có thể đến từ Hibernate hoặc provider cụ thể. Kiểu SQL vật lý có thể là binary hoặc dạng ký tự tùy dialect và cấu hình. Hãy xác nhận schema, index và cách driver truyền UUID trên database đích.

UUID giúp tạo ID độc lập, nhưng thường dài hơn số nguyên và có thể ảnh hưởng kích thước index, locality của index nếu dùng UUID ngẫu nhiên. Cân nhắc UUID được sắp xếp theo thời gian hoặc chiến lược ID khác nếu workload yêu cầu, đồng thời kiểm tra hỗ trợ thực tế của provider.

## 8. AttributeConverter: mở rộng kiểu Java mà vẫn dùng mapping chuẩn

Khi domain model có kiểu riêng nhưng database chỉ cần lưu một kiểu cơ bản, JPA cung cấp AttributeConverter<X, Y>.

- X là kiểu thuộc tính trong Entity.
- Y là kiểu dữ liệu được chuyển sang database, thường là một kiểu cơ bản được JPA hỗ trợ.

Ví dụ domain type EmailAddress:

~~~java
public final class EmailAddress {

    private final String value;

    public EmailAddress(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        this.value = value;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EmailAddress that)) return false;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Converter:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String value) {
        return value == null ? null : new EmailAddress(value);
    }
}
~~~

Dùng converter trên Entity:

~~~java
import jakarta.persistence.*;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    @Column(nullable = false, unique = true, length = 320)
    private EmailAddress email;
}
~~~

Converter giúp Entity diễn đạt đúng kiểu nghiệp vụ EmailAddress trong khi database lưu chuỗi. Việc chuyển đổi có thể áp dụng riêng từng thuộc tính bằng @Convert hoặc tự động bằng @Converter(autoApply = true).

Một converter cần xử lý null theo quy ước, chuyển đổi hai chiều nhất quán và không thực hiện truy vấn database trong quá trình convert. Kiểu Y phải được provider hỗ trợ. AttributeConverter không tự tạo một kiểu SQL tùy ý; nó chuyển đổi về kiểu mà JDBC/provider biết cách ghi và đọc.

Không nên dùng Java native serialization để lưu object tùy ý nếu có thể biểu diễn bằng kiểu cơ bản, JSON có kiểm soát hoặc schema rõ ràng. Dữ liệu serialize khó truy vấn, khó migration và có thể tạo rủi ro bảo mật khi deserialize dữ liệu không tin cậy.

## 9. Kiểu đặc thù của Hibernate và database

Khi kiểu chuẩn JPA không diễn đạt được tính năng cần thiết, có thể dùng extension của Hibernate hoặc kiểu riêng database. Ví dụ phổ biến là JSON, PostgreSQL JSONB, array, enum native, spatial data hoặc kiểu thời gian đặc thù.

Ví dụ Hibernate 6 ánh xạ JSON cho PostgreSQL:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.util.Map;

@Entity
@Table(name = "event_records")
public class EventRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> payload;
}
~~~

Trong ví dụ này:

- @JdbcTypeCode và SqlTypes.JSON là API đặc thù của Hibernate 6.
- columnDefinition = "jsonb" chỉ định kiểu SQL dùng trong DDL cho PostgreSQL.
- Database cần hỗ trợ JSONB và dialect/driver phải tương thích.
- Nếu chuyển sang MySQL, kiểu cột JSON và cấu hình có thể khác; không thể giữ nguyên jsonb.

Cần phân biệt annotation điều khiển JDBC type với columnDefinition. columnDefinition chủ yếu ảnh hưởng DDL do provider sinh ra; nó không tự đảm bảo toàn bộ cách bind/extract dữ liệu được cấu hình đúng. Hãy kiểm tra cả schema lẫn câu lệnh JDBC thực tế.

### Khi nào đáng dùng extension?

Một mapping đặc thù có thể hợp lý nếu:

- Cần truy vấn JSON theo path hoặc dùng index JSONB của PostgreSQL.
- Cần kiểu array hoặc spatial của database.
- Cần tận dụng khả năng nén, tìm kiếm hoặc kiểu dữ liệu riêng.
- Có yêu cầu hiệu năng hoặc nghiệp vụ mà mapping chuẩn không đáp ứng.

Đổi lại, entity sẽ phụ thuộc vào provider hoặc database. Điều đó làm việc chuyển provider, chuyển database, chạy test trên H2 hoặc tái sử dụng module khó hơn. Hãy cô lập mapping đặc thù ở module persistence và ghi rõ database/phiên bản yêu cầu.

## 10. So sánh lựa chọn chuẩn và đặc thù

| Tiêu chí | Mapping chuẩn JPA | Mapping đặc thù provider/database |
|---|---|---|
| Tính di động | Thường cao hơn | Phụ thuộc provider hoặc database |
| Cú pháp | Annotation/API chuẩn | Annotation/API riêng |
| Kiểu dữ liệu | Các kiểu cơ bản, enum, date/time, converter | JSONB, array, spatial, native enum và kiểu riêng |
| DDL | Provider tạo theo dialect | Có thể cần columnDefinition hoặc type riêng |
| Kiểm thử | Dễ dùng nhiều database hơn, nhưng vẫn phải kiểm tra khác biệt | Nên test trên đúng database/provider |
| Bảo trì | Dễ chuyển đổi và chia sẻ | Cần quản lý phiên bản và giới hạn phụ thuộc |
| Khả năng khai thác tính năng riêng | Có giới hạn | Có thể tận dụng sâu tính năng database |

Không phải cứ mapping chuẩn là hiệu năng tốt hơn, và không phải cứ dùng extension là tối ưu hơn. Hãy đo bằng truy vấn thực tế, dữ liệu thực tế và workload thực tế.

## 11. Những lỗi thường gặp khi lựa chọn kiểu

**Dùng kiểu Java không được provider hỗ trợ**

- Kiểm tra phiên bản Jakarta Persistence, Hibernate và JDBC driver.
- Dùng AttributeConverter để chuyển kiểu domain về kiểu cơ bản được hỗ trợ.
- Nếu dùng extension, kiểm tra API đúng với phiên bản Hibernate hiện tại.

**DDL sinh ra khác với dự kiến**

- Kiểm tra dialect và schema thực tế.
- Kiểm tra annotation chuẩn, columnDefinition và migration.
- Không coi việc ứng dụng khởi động thành công là bằng chứng kiểu SQL đã đúng với yêu cầu.

**Dùng columnDefinition để sửa mọi vấn đề mapping**

- columnDefinition chủ yếu mô tả kiểu SQL cho DDL.
- Nó không thay thế JDBC type mapping, converter hoặc custom type.
- Nếu cần kiểu JDBC riêng, dùng API phù hợp của provider và kiểm thử trên database đích.

**Enum ordinal gây sai dữ liệu sau khi thay đổi thứ tự enum**

- Ưu tiên EnumType.STRING nếu phù hợp.
- Nếu cần mã lưu ổn định, dùng AttributeConverter.
- Khi đổi mã hoặc tên enum đã lưu, tạo migration dữ liệu.

**Dùng double cho tiền hoặc BigDecimal không chuẩn hóa**

- Dùng BigDecimal cho số thập phân cần độ chính xác.
- Xác định precision, scale và quy tắc làm tròn.
- Kiểm tra giá trị đầu vào vượt giới hạn cột.

**Giả định H2 giống database production**

- Test nhanh trên H2 có ích, nhưng không xác nhận được mọi kiểu riêng, hàm SQL, JSON, collation hoặc migration của database khác.
- Với mapping đặc thù, chạy integration test trên cùng engine và phiên bản gần với production.

## 12. Quy trình chọn kiểu cho một thuộc tính Entity

Khi thêm một thuộc tính mới, hãy đi theo các bước:

1. Xác định ý nghĩa nghiệp vụ: văn bản, tiền, ngày lịch, thời điểm, enum, UUID, JSON, dữ liệu nhị phân hay value object.
2. Chọn kiểu Java biểu đạt đúng ý nghĩa, ví dụ LocalDate cho ngày lịch, Instant cho thời điểm, BigDecimal cho tiền.
3. Kiểm tra kiểu đó có được Jakarta Persistence phiên bản dự án hỗ trợ trực tiếp hay không.
4. Nếu là kiểu domain riêng, xem xét AttributeConverter để chuyển về kiểu cơ bản.
5. Chỉ dùng extension provider/database khi cần tính năng cụ thể mà mapping chuẩn không đáp ứng.
6. Xác định kiểu SQL và giới hạn cột trên database mục tiêu.
7. Tạo migration có phiên bản và kiểm tra DDL/schema.
8. Viết integration test cho lưu, đọc, cập nhật, truy vấn và các trường hợp biên.
9. Nếu cần hỗ trợ nhiều database, chạy test trên từng engine được hỗ trợ; không suy luận tính di động chỉ từ việc code dùng annotation chuẩn.

## 13. Kết luận

Kiểu chuẩn JPA là lựa chọn tốt cho phần lớn thuộc tính thông thường vì giúp giảm phụ thuộc vào provider và database. Khi domain model cần kiểu riêng, AttributeConverter thường là cầu nối rõ ràng về kiểu cơ bản. Extension của Hibernate hoặc kiểu SQL đặc thù phù hợp khi cần tính năng cụ thể như JSONB, array hay spatial, nhưng phải chấp nhận phụ thuộc và kiểm thử trên đúng môi trường. Quyết định nên dựa trên ý nghĩa dữ liệu, khả năng tương thích, schema và hiệu năng đã đo được.

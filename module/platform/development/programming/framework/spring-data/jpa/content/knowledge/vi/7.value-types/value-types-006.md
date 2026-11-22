# Chuyển đổi dữ liệu bằng AttributeConverter và @Convert

JPA ánh xạ thuộc tính Java của entity với cột trong cơ sở dữ liệu. Thông thường, provider như Hibernate đã biết cách lưu các kiểu cơ bản như String, Integer, BigDecimal, LocalDate và enum theo những quy tắc mặc định. Tuy nhiên, ứng dụng đôi khi dùng một kiểu Java riêng để biểu diễn giá trị nghiệp vụ, trong khi database cần lưu một kiểu đơn giản hơn. JPA cung cấp **AttributeConverter** để chuyển đổi hai dạng dữ liệu này tại ranh giới persistence.

Bài học này giải thích hợp đồng của AttributeConverter, cách viết converter, cách gắn converter bằng @Convert, cách dùng autoApply, các trường hợp áp dụng cho embedded attribute và collection, cũng như những giới hạn cần lưu ý. Ví dụ chính dùng enum OrderStatus trong Java và lưu mã ngắn vào cột VARCHAR/CHAR.

## 1. Vì sao cần AttributeConverter?

Giả sử ứng dụng biểu diễn trạng thái đơn hàng bằng enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Nếu dùng @Enumerated(EnumType.STRING), database lưu các chuỗi NEW, PAID và CANCELLED. Cách này dễ đọc, nhưng tên enum trở thành một phần của dữ liệu lưu trữ. Nếu đổi tên hằng số trong Java, dữ liệu cũ có thể không còn khớp.

Nếu dùng @Enumerated(EnumType.ORDINAL), database lưu số thứ tự 0, 1, 2. Cách này ngắn hơn nhưng nguy hiểm khi thêm hoặc sắp xếp lại hằng số: ordinal của giá trị có thể thay đổi và dữ liệu cũ bị diễn giải sai.

Trong một hệ thống nghiệp vụ, database có thể cần lưu mã ổn định:

| Giá trị Java | Mã lưu trong database |
|---|---|
| NEW | N |
| PAID | P |
| CANCELLED | C |

Ta muốn code Java vẫn làm việc với OrderStatus, trong khi database chỉ lưu mã. AttributeConverter thực hiện chuyển đổi:

~~~text
OrderStatus.NEW
      |
      | convertToDatabaseColumn(...)
      v
     "N"
      |
      v
VARCHAR / CHAR column

VARCHAR / CHAR column
      |
      | convertToEntityAttribute(...)
      v
     "N"
      |
      v
OrderStatus.NEW
~~~

Converter giúp tách cách biểu diễn trong domain khỏi cách lưu trữ. Nó đặc biệt hữu ích với enum có mã nghiệp vụ, value object, kiểu tiền tệ có quy tắc riêng hoặc dữ liệu legacy có định dạng khác với kiểu Java.

## 2. Hợp đồng của AttributeConverter

Jakarta Persistence định nghĩa interface tổng quát:

~~~java
public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);
    X convertToEntityAttribute(Y dbData);
}
~~~

Hai tham số kiểu có ý nghĩa:

- **X** là kiểu thuộc tính trong entity hoặc embeddable, tức kiểu Java mà code nghiệp vụ sử dụng.
- **Y** là kiểu biểu diễn tương ứng trong database, thường là một kiểu basic mà JPA provider và JDBC driver hỗ trợ.

Hai phương thức có hướng chuyển đổi ngược nhau:

| Phương thức | Hướng chuyển đổi | Khi nào được dùng |
|---|---|---|
| convertToDatabaseColumn(X) | Java → database | Khi ghi hoặc đồng bộ giá trị thuộc tính xuống database |
| convertToEntityAttribute(Y) | database → Java | Khi đọc giá trị cột để tạo hoặc nạp entity |

Ví dụ với enum:

- Java OrderStatus.PAID được chuyển thành chuỗi "P" trước khi lưu.
- Chuỗi "P" đọc từ database được chuyển lại thành OrderStatus.PAID.

Converter chỉ xử lý giá trị thuộc tính. Nó không thay thế entity, repository, transaction hay mapping quan hệ. Nó cũng không tự tạo bảng, cột, khóa ngoại hoặc migration.

## 3. Viết một converter cho enum

Trước tiên, định nghĩa enum có mã database ổn định:

~~~java
package example.domain;

public enum OrderStatus {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return switch (code) {
            case "N" -> NEW;
            case "P" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status code: " + code
            );
        };
    }
}
~~~

Mỗi enum hằng số giữ mã được dùng để lưu trữ. Phương thức fromDatabaseCode() chuyển mã đọc từ database thành enum tương ứng. Giá trị không hợp lệ được báo lỗi rõ ràng để dữ liệu sai không bị âm thầm biến thành một trạng thái khác.

Tiếp theo, tạo converter:

~~~java
package example.persistence;

import example.domain.OrderStatus;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.databaseCode();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null
            ? null
            : OrderStatus.fromDatabaseCode(dbData);
    }
}
~~~

Giải thích:

- **@Converter** đánh dấu class là JPA converter để provider phát hiện và sử dụng.
- **autoApply = false** nghĩa là converter chỉ được áp dụng ở nơi khai báo tường minh.
- **AttributeConverter<OrderStatus, String>** cho biết thuộc tính Java là OrderStatus và giá trị database là String.
- **convertToDatabaseColumn()** trả mã N, P hoặc C.
- **convertToEntityAttribute()** khôi phục enum từ mã database.

Hai phương thức xử lý null để không gọi phương thức trên giá trị null. Với các thuộc tính được khai báo NOT NULL, validation và constraint vẫn cần được đặt ở những tầng phù hợp; converter không thay thế constraint database.

Không nên trả về một trạng thái mặc định khi gặp mã không biết. Nếu database chứa giá trị không hợp lệ, ném lỗi rõ ràng giúp phát hiện dữ liệu cũ hoặc migration bị thiếu. Nếu hệ thống cần tương thích ngược trong một giai đoạn triển khai, hãy định nghĩa rõ chính sách cho mã cũ và kiểm thử chính sách đó.

## 4. Gắn converter bằng @Convert

Tạo entity sử dụng converter:

~~~java
package example.domain;

import example.persistence.OrderStatusConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "status_code", nullable = false, length = 1)
    @Convert(converter = OrderStatusConverter.class)
    private OrderStatus status;

    protected PurchaseOrder() {
        // Constructor phục vụ JPA.
    }

    public PurchaseOrder(OrderStatus status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

Điểm quan trọng:

- @Convert chỉ định converter áp dụng cho thuộc tính status.
- @Column mô tả tên và constraint của cột.
- Kiểu Java của field vẫn là OrderStatus.
- Giá trị được lưu qua converter là String, không phải ordinal hay tên enum.

Với mapping này, cột status_code có thể được khai báo là CHAR(1) hoặc VARCHAR(1), tùy hệ quản trị và schema của dự án. Ví dụ SQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status_code CHAR(1) NOT NULL,
    CONSTRAINT chk_purchase_orders_status
        CHECK (status_code IN ('N', 'P', 'C'))
);
~~~

Cú pháp tạo identity column khác nhau giữa các database. DDL trên minh họa cấu trúc; hãy dùng cú pháp phù hợp với PostgreSQL, MySQL, H2 hoặc hệ quản trị đang chạy. Constraint CHECK ở database bảo vệ tập mã hợp lệ ngay cả khi dữ liệu được ghi từ một ứng dụng khác.

## 5. @Converter(autoApply = true)

Nếu một converter phù hợp với mọi thuộc tính có cùng kiểu Java trong persistence unit, có thể bật autoApply:

~~~java
@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {
    // Hai phương thức chuyển đổi giữ nguyên như ví dụ trước.
}
~~~

Khi autoApply = true, JPA provider tự áp dụng converter cho các mapped attribute có kiểu OrderStatus trong persistence unit. Khi đó entity không cần khai báo @Convert trên field:

~~~java
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
~~~

Chỉ dùng autoApply khi cùng một kiểu Java luôn có cùng quy tắc lưu trữ. Nếu một enum được lưu bằng mã N/P/C ở bảng này nhưng lưu bằng chuỗi đầy đủ ở bảng khác, autoApply sẽ quá rộng; hãy dùng converter tường minh tại từng thuộc tính.

Không nên khai báo nhiều converter auto-apply cùng nhắm đến một kiểu thuộc tính trong cùng persistence unit. Nếu provider không thể xác định converter phù hợp duy nhất, metadata mapping có thể không hợp lệ.

### 5.1. Tắt auto-apply cho một thuộc tính

Nếu converter auto-apply đang có hiệu lực nhưng một thuộc tính cần giữ mapping khác, có thể dùng:

~~~java
@Convert(disableConversion = true)
private OrderStatus status;
~~~

Điều này yêu cầu provider không áp dụng converter tự động cho thuộc tính đó. Chỉ dùng khi đã xác định rõ kiểu lưu trữ mong muốn và kiểm tra mapping database tương ứng.

### 5.2. Chọn explicit hay auto-apply

| Tiêu chí | @Convert tường minh | autoApply = true |
|---|---|---|
| Phạm vi | Một thuộc tính hoặc phạm vi được chỉ định | Các mapped attribute phù hợp trong persistence unit |
| Tính rõ ràng | Nhìn vào entity biết converter nào được dùng | Cần tìm converter toàn cục để hiểu mapping |
| Tái sử dụng | Lặp annotation ở các field cần dùng | Tự áp dụng ở nhiều entity |
| Phù hợp khi | Quy tắc khác nhau theo cột hoặc entity | Một kiểu Java có một quy tắc lưu trữ thống nhất |
| Rủi ro | Quên gắn @Convert ở field mới | Ảnh hưởng ngoài dự kiến đến field cùng kiểu |

Với dữ liệu có ý nghĩa nghiệp vụ quan trọng, ưu tiên quy tắc dễ đọc và dễ kiểm tra. Auto-apply giúp giảm annotation nhưng làm phạm vi ảnh hưởng rộng hơn.

## 6. Các trường hợp JPA không áp dụng converter

AttributeConverter được thiết kế cho thuộc tính basic. Theo quy tắc của Jakarta Persistence, converter không được áp dụng cho các trường hợp sau:

- Thuộc tính khóa chính được ánh xạ bằng @Id.
- Thuộc tính version được ánh xạ bằng @Version.
- Thuộc tính quan hệ được ánh xạ bằng @OneToOne, @OneToMany, @ManyToOne hoặc @ManyToMany.
- Thuộc tính được ánh xạ bằng @Enumerated.
- Thuộc tính được ánh xạ bằng @Temporal.

Vì vậy, không dùng converter để biến một entity association thành khóa ngoại. Quan hệ entity phải được ánh xạ bằng annotation quan hệ và khóa ngoại do mapping quan hệ quản lý.

Với enum, chọn một trong hai cách:

- Dùng @Enumerated(EnumType.STRING) nếu muốn lưu tên enum.
- Dùng AttributeConverter nếu muốn lưu mã hoặc định dạng riêng.

Không đặt @Enumerated và @Convert cùng lúc trên một thuộc tính. Chúng mô tả hai chiến lược chuyển đổi khác nhau và không nên được kết hợp.

## 7. Chuyển đổi thuộc tính trong Embeddable

Một entity có thể chứa object @Embeddable, và object đó có các thuộc tính basic cần chuyển đổi riêng.

Ví dụ, địa chỉ có mã vùng được lưu theo định dạng legacy:

~~~java
package example.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    private String street;
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String postalCode) {
        this.street = street;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Giả sử Java dùng PostalCode value type nhưng database lưu String. Có thể đặt converter trên thuộc tính được nhúng bằng attributeName:

~~~java
@Embedded
@Convert(
    attributeName = "postalCode",
    converter = PostalCodeConverter.class
)
private Address address;
~~~

**attributeName** chỉ ra thuộc tính bên trong embeddable cần chuyển đổi. Với embeddable lồng nhau, có thể dùng đường dẫn thuộc tính phân tách bằng dấu chấm, ví dụ address.postalCode ở phạm vi mapping phù hợp.

Nếu một embeddable có nhiều thuộc tính cần converter khác nhau, có thể dùng @Converts để khai báo nhiều @Convert:

~~~java
@Embedded
@Converts({
    @Convert(
        attributeName = "postalCode",
        converter = PostalCodeConverter.class
    ),
    @Convert(
        attributeName = "countryCode",
        converter = CountryCodeConverter.class
    )
})
private Address address;
~~~

Tên attributeName phải khớp tên thuộc tính Java theo access strategy của mapping, không phải tên cột SQL. Khi dùng property access, hãy xác định tên property được ánh xạ.

Không dùng AttributeConverter để biến toàn bộ một embeddable nhiều cột thành một giá trị đơn nếu mục tiêu là lưu từng thành phần vào các cột riêng. Hãy dùng @Embeddable và chuyển đổi từng thuộc tính basic.

## 8. Chuyển đổi phần tử của ElementCollection

@ElementCollection ánh xạ collection của basic value hoặc embeddable value. Converter có thể áp dụng cho phần tử basic của collection.

Ví dụ, hệ thống lưu một tập mã nhãn:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag_code")
    @Convert(converter = TagCodeConverter.class)
    private Set<TagCode> tags = new HashSet<>();
}
~~~

Ở đây converter chuyển mỗi TagCode thành giá trị database tương ứng. Nó không chuyển toàn bộ Set thành một chuỗi duy nhất. Bảng customer_tags có một hàng cho mỗi phần tử collection và khóa ngoại đến customer.

Nếu collection chứa embeddable, hãy áp dụng converter vào thuộc tính basic bên trong embeddable bằng attributeName theo quy tắc mapping.

Với Map, giá trị và khóa có thể cần quy tắc riêng. Jakarta Persistence có @MapKeyConvert để chuyển đổi kiểu của map key. Đừng nhầm converter của map key với converter áp dụng cho map value hoặc collection element.

## 9. Converter và JPQL / Spring Data Repository

JPQL làm việc với tên entity và thuộc tính Java. Với thuộc tính status đã chuyển đổi, truy vấn vẫn có thể diễn đạt theo kiểu Java:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Hoặc khai báo JPQL:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.status = :status
    """)
List<PurchaseOrder> findByStatus(@Param("status") OrderStatus status);
~~~

Ở đây tham số là OrderStatus.PAID, không phải chuỗi "P". Provider sử dụng mapping của thuộc tính để chuyển giá trị sang dạng database khi tạo SQL.

Khi viết native SQL, bạn đang làm việc trực tiếp với tên cột và biểu diễn database. Ví dụ điều kiện SQL sẽ so sánh status_code với 'P'. Nếu trả về scalar hoặc DTO từ native query, đừng mặc định converter của entity sẽ tự động được áp dụng cho mọi kết quả tùy biến; hãy xác định rõ kiểu kết quả và kiểm thử với provider đang dùng.

Đối với query update/delete JPQL dạng bulk, các thao tác này tác động trực tiếp lên database và không đồng bộ từng entity đang được quản lý như thao tác thay đổi object thông thường. Nếu dùng bulk query với thuộc tính converted, cần kiểm tra kiểu tham số, mapping và persistence context sau khi thực thi.

## 10. Quy tắc thiết kế converter tốt

Một converter đáng tin cậy nên tuân thủ các nguyên tắc:

1. **Hai chiều nhất quán**: giá trị hợp lệ chuyển Java → database → Java phải giữ nguyên ý nghĩa.
2. **Xử lý null có chủ đích**: không gọi method trên null và không tự biến null thành giá trị nghiệp vụ khác nếu không có quy tắc rõ ràng.
3. **Báo lỗi dữ liệu sai**: không âm thầm chuyển mã không biết thành giá trị mặc định.
4. **Stateless**: không lưu trạng thái theo request hoặc entity trong field của converter.
5. **Không phụ thuộc môi trường ngầm**: tránh đọc file, gọi API mạng hoặc truy cập database bên trong converter.
6. **Không nhét nghiệp vụ phức tạp vào converter**: converter chỉ chuyển biểu diễn, không thực hiện quy trình nghiệp vụ.
7. **Kiểu database rõ ràng**: chọn Y là kiểu basic được provider và JDBC hỗ trợ.
8. **Tương thích dữ liệu cũ**: thay đổi mã lưu trữ phải có migration hoặc kế hoạch tương thích.
9. **Kiểm thử cả hai chiều**: kiểm tra mã lưu, giá trị đọc lại, null và dữ liệu không hợp lệ.

Converter thường được provider quản lý và có thể được dùng ở nhiều thao tác persistence. Vì vậy, không nên giả định mỗi entity có một instance converter riêng hoặc converter chỉ được gọi một lần. Hãy viết converter như một thành phần không trạng thái, an toàn khi được gọi lặp lại.

## 11. Những giới hạn của AttributeConverter

AttributeConverter phù hợp khi một thuộc tính Java ánh xạ thành một giá trị database. Nó không phải công cụ tổng quát để thay đổi cấu trúc persistence.

Một số giới hạn quan trọng:

- **Không chuyển một object thành nhiều cột**: Y là một kiểu database cho một giá trị thuộc tính. Nếu cần nhiều cột, dùng @Embeddable hoặc mapping phù hợp.
- **Không thay thế quan hệ entity**: quan hệ phải được khai báo bằng @ManyToOne, @OneToMany hoặc annotation tương ứng.
- **Không thay thế schema migration**: converter thay đổi giá trị ở ranh giới Java/database; nó không tự sửa dữ liệu cũ hoặc thay đổi kiểu cột.
- **Không thay thế validation**: converter có thể từ chối dữ liệu không hợp lệ, nhưng quy tắc đầu vào vẫn nên được kiểm tra ở tầng phù hợp và database vẫn cần constraint.
- **Không phải cơ chế mã hóa bảo mật hoàn chỉnh**: nếu chuyển đổi có mã hóa, cần thiết kế quản lý khóa, rotation, tìm kiếm, index và tương thích dữ liệu; không đặt secret cố định trong converter.
- **Không nên dùng cho mọi kiểu đã được provider hỗ trợ tốt**: chuyển đổi không cần thiết có thể làm mất metadata hoặc semantics vốn có của kiểu Java.

Nếu cần chuyển một giá trị domain thành cấu trúc nhiều cột, hãy cân nhắc embeddable. Nếu cần ánh xạ kiểu database đặc thù, truy vấn tùy chỉnh hoặc hành vi provider-specific, hãy xem xét API mở rộng của provider sau khi hiểu rõ tính phụ thuộc.

## 12. Thay đổi converter và dữ liệu đang tồn tại

Converter là một phần của hợp đồng giữa mã Java và dữ liệu database. Nếu thay đổi mã:

| Thay đổi | Rủi ro |
|---|---|
| Đổi mã N thành NEW | Dữ liệu cũ không còn được đọc đúng nếu converter không hỗ trợ mã cũ |
| Xóa một enum hằng số | Bản ghi đang lưu mã tương ứng có thể gây lỗi khi đọc |
| Đổi kiểu database String thành Integer | Schema và dữ liệu cần migration đồng bộ |
| Bật autoApply | Các thuộc tính cùng kiểu trong persistence unit có thể đổi cách lưu |
| Đổi converter class | Mapping và các query liên quan cần được kiểm tra lại |

Ví dụ, nếu mã PAID đổi từ P sang S, cần quyết định cách xử lý bản ghi đang chứa P. Có thể triển khai converter tạm thời đọc cả P và S nhưng chỉ ghi S, sau đó migration dữ liệu và loại bỏ hỗ trợ mã cũ ở một phiên bản sau. Quy trình này cần được kiểm thử với dữ liệu thực tế và rollback plan.

Không nên triển khai thay đổi converter mà không kiểm tra schema, dữ liệu, JPQL, native SQL, báo cáo và các ứng dụng khác cùng đọc bảng.

## 13. Kiểm thử AttributeConverter

### 13.1. Unit test cho hai phương thức

Có thể kiểm thử converter trực tiếp mà không cần khởi tạo Spring:

~~~java
import example.domain.OrderStatus;
import example.persistence.OrderStatusConverter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderStatusConverterTest {

    private final OrderStatusConverter converter =
        new OrderStatusConverter();

    @Test
    void convertsEnumToDatabaseCode() {
        assertEquals(
            "P",
            converter.convertToDatabaseColumn(OrderStatus.PAID)
        );
    }

    @Test
    void convertsDatabaseCodeToEnum() {
        assertEquals(
            OrderStatus.PAID,
            converter.convertToEntityAttribute("P")
        );
    }

    @Test
    void preservesNull() {
        assertNull(converter.convertToDatabaseColumn(null));
        assertNull(converter.convertToEntityAttribute(null));
    }

    @Test
    void rejectsUnknownDatabaseCode() {
        assertThrows(
            IllegalArgumentException.class,
            () -> converter.convertToEntityAttribute("Z")
        );
    }
}
~~~

Các test này kiểm tra quy tắc chuyển đổi thuần Java. Chúng không xác minh provider có phát hiện converter, tạo schema đúng hoặc gọi converter trong thao tác persistence.

### 13.2. Integration test với JPA provider

Cần thêm test tích hợp để xác minh toàn bộ mapping:

1. Khởi tạo persistence unit hoặc Spring context dùng provider thật.
2. Persist PurchaseOrder có status PAID.
3. Flush và kiểm tra giá trị cột status_code là P.
4. Clear persistence context để không đọc lại cùng object đang được quản lý.
5. Tìm lại entity từ database.
6. Xác minh status đọc được là OrderStatus.PAID.
7. Kiểm tra query repository với tham số OrderStatus.PAID.
8. Kiểm tra dữ liệu database không hợp lệ và cách ứng dụng báo lỗi.

Việc clear persistence context rất quan trọng: nếu chỉ đọc lại cùng object đang được quản lý, kết quả có thể đến từ bộ nhớ thay vì chuyển đổi database → Java.

Ngoài ra, kiểm tra DDL hoặc migration để xác nhận kiểu cột, độ dài và constraint phù hợp với mã converter.

## 14. Lỗi thường gặp và cách khắc phục

**1. Converter không được áp dụng**

Kiểm tra class có @Converter hay chưa, entity attribute có @Convert hay converter có autoApply = true không. Đảm bảo converter thuộc persistence unit và package/class được provider phát hiện theo cấu hình đang dùng.

**2. Dữ liệu ghi xuống database không đúng**

Kiểm tra kiểu Y, logic convertToDatabaseColumn(), tên cột, độ dài và mapping. Đọc giá trị trực tiếp từ database để phân biệt lỗi converter với lỗi query hoặc cache.

**3. Không đọc được dữ liệu cũ**

Kiểm tra convertToEntityAttribute() có hỗ trợ tất cả mã đang tồn tại không. Kiểm tra dữ liệu legacy, viết migration hoặc triển khai giai đoạn tương thích có kiểm soát.

**4. Enum bị lưu ordinal dù đã có converter**

Kiểm tra @Enumerated còn tồn tại trên field/property không. Không kết hợp @Enumerated với @Convert trên cùng thuộc tính.

**5. Converter tự động ảnh hưởng field không mong muốn**

Kiểm tra @Converter(autoApply = true) và tất cả mapped attribute cùng kiểu trong persistence unit. Nếu quy tắc chỉ áp dụng cục bộ, chuyển sang autoApply = false và khai báo @Convert tường minh.

**6. JPQL hoạt động nhưng native SQL sai**

JPQL dùng thuộc tính Java; native SQL dùng biểu diễn cột database. Kiểm tra tham số và literal native query có dùng mã lưu trữ đúng không.

**7. Lỗi khi đọc dữ liệu không hợp lệ**

Kiểm tra stack trace để xác định converter ném lỗi ở convertToEntityAttribute(). Không che giấu lỗi bằng giá trị mặc định nếu điều đó làm sai ý nghĩa nghiệp vụ.

**8. Converter cố gắng chuyển nhiều cột**

Một AttributeConverter không phải mapping nhiều cột. Dùng @Embeddable, nhiều thuộc tính basic hoặc giải pháp mapping chuyên biệt.

## 15. Quy trình triển khai một converter

Khi cần bổ sung converter trong dự án, hãy đi theo trình tự:

1. Xác định kiểu Java và biểu diễn database hiện tại.
2. Xác định các giá trị hợp lệ và quy tắc xử lý null.
3. Kiểm tra dữ liệu cũ và schema thực tế.
4. Thiết kế hai hàm chuyển đổi ngược nhau.
5. Quyết định dùng @Convert hay autoApply.
6. Kiểm tra các giới hạn: id, version, relationship, @Enumerated và @Temporal.
7. Viết unit test cho chuyển đổi và dữ liệu không hợp lệ.
8. Viết integration test persist/read/query với provider thật.
9. Chuẩn bị migration nếu format hoặc schema thay đổi.
10. Triển khai theo cách tương thích với dữ liệu đang tồn tại.

## 16. Checklist tự đánh giá

- [ ] Tôi giải thích được AttributeConverter<X, Y> và ý nghĩa của X, Y.
- [ ] Tôi phân biệt được convertToDatabaseColumn() và convertToEntityAttribute().
- [ ] Tôi có thể viết converter cho enum dùng mã database ổn định.
- [ ] Tôi biết gắn converter bằng @Convert.
- [ ] Tôi hiểu phạm vi của @Converter(autoApply = true).
- [ ] Tôi biết khi nào dùng @Converts và attributeName.
- [ ] Tôi hiểu converter cho element collection và map key.
- [ ] Tôi biết các thuộc tính id, version, relationship, @Enumerated và @Temporal không được converter áp dụng.
- [ ] Tôi không kết hợp @Enumerated và @Convert trên cùng field.
- [ ] Tôi kiểm thử null, mã hợp lệ và mã không hợp lệ.
- [ ] Tôi hiểu vì sao integration test cần flush và clear persistence context.
- [ ] Tôi biết converter không thay thế migration, validation hoặc mapping nhiều cột.

## 17. Câu hỏi ôn tập

**1. AttributeConverter<X, Y> có ý nghĩa gì?**

X là kiểu Java của thuộc tính domain; Y là kiểu database được dùng để lưu giá trị. Converter cung cấp hai hàm chuyển đổi giữa hai kiểu.

**2. @Convert khác @Converter thế nào?**

@Converter đánh dấu class triển khai converter và có thể khai báo autoApply. @Convert gắn converter vào một thuộc tính cụ thể hoặc chỉ định chuyển đổi cho một thuộc tính bên trong embedded mapping.

**3. Khi nào nên bật autoApply?**

Khi mọi mapped attribute cùng kiểu Java trong persistence unit đều cần chung một quy tắc chuyển đổi. Nếu quy tắc khác nhau theo field, nên dùng @Convert tường minh.

**4. Có nên dùng AttributeConverter cho khóa ngoại không?**

Không. Quan hệ entity và khóa ngoại được quản lý bằng mapping quan hệ. Converter dành cho giá trị thuộc tính basic.

**5. Vì sao converter không nên tự thay giá trị không hợp lệ thành mặc định?**

Vì điều đó có thể che giấu dữ liệu sai và làm thay đổi ý nghĩa nghiệp vụ. Nên báo lỗi rõ ràng hoặc triển khai chính sách tương thích ngược có kiểm soát.

**6. Vì sao phải clear persistence context trong integration test?**

Để lần đọc tiếp theo thực sự lấy dữ liệu qua provider từ database và kiểm tra chiều convertToEntityAttribute(), thay vì chỉ nhận lại object đang nằm trong bộ nhớ.

Khi sử dụng AttributeConverter đúng cách, domain model có thể giữ kiểu Java rõ nghĩa trong khi database tiếp tục dùng biểu diễn lưu trữ ổn định và phù hợp với schema của hệ thống.
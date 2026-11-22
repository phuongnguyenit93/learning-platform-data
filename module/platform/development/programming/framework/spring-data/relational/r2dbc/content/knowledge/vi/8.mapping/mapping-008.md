# Ánh xạ đối tượng lồng nhau và giới hạn theo phiên bản

Trong mô hình Java, một entity thường chứa các object con để biểu diễn giá trị nghiệp vụ. Ví dụ, `Customer` có thể chứa `Address`, `Order` có thể chứa danh sách `OrderLine`, hoặc một hồ sơ có thể chứa object `Preferences`. Tuy nhiên, việc một object được lồng trong object khác ở Java không tự quyết định dữ liệu của nó sẽ được lưu như thế nào trong cơ sở dữ liệu quan hệ.

Với Spring Data R2DBC, cần chọn rõ chiến lược ánh xạ cho từng kiểu dữ liệu lồng nhau. Một value object có thể được nhúng vào cùng hàng dữ liệu bằng `@Embedded`; một collection thuộc aggregate có thể được lưu ở bảng riêng bằng `@MappedCollection`; một aggregate khác thường được tham chiếu bằng định danh; còn dữ liệu cần lưu nguyên cấu trúc JSON có thể cần custom converter phụ thuộc driver. Những cách này có ý nghĩa khác nhau và không thể thay thế tùy ý cho nhau.

## 1. Chọn chiến lược lưu trữ cho object lồng nhau

Trước khi viết annotation, hãy xác định object con thuộc trường hợp nào:

| Mô hình trong Java | Cách ánh xạ thường phù hợp | Cấu trúc dữ liệu quan hệ |
|---|---|---|
| Value object thuộc về entity, không có định danh độc lập | `@Embedded` | Các trường của object con trở thành các cột trong cùng hàng với entity cha. |
| Các phần tử thuộc aggregate root, có thể có nhiều phần tử | `@MappedCollection` | Các phần tử được lưu ở bảng riêng và liên kết về aggregate root bằng cột định danh. |
| Tham chiếu đến aggregate độc lập | Lưu ID hoặc dùng `AggregateReference` | Bảng của aggregate hiện tại giữ khóa tham chiếu; aggregate kia được tải bằng truy vấn riêng khi cần. |
| Giá trị cần lưu nguyên cấu trúc JSON | Custom conversion và kiểu dữ liệu JSON mà driver hỗ trợ | Một cột JSON/JSONB hoặc kiểu tương ứng của database. |
| Dữ liệu đọc tổng hợp từ nhiều bảng | SQL join và projection/DTO | Câu truy vấn trả về các cột cần thiết; ứng dụng ánh xạ thành read model. |

Ví dụ, địa chỉ giao hàng thường là value object của đơn hàng. Nó không cần vòng đời độc lập và có thể được lưu ngay trong hàng `purchase_order`. Ngược lại, một đơn hàng tham chiếu đến khách hàng là aggregate khác; việc lưu toàn bộ object `Customer` lồng bên trong `PurchaseOrder` có thể làm mờ ranh giới aggregate và gây khó kiểm soát cập nhật.

## 2. Nhúng value object vào cùng bảng bằng @Embedded

`@Embedded` cho Spring Data Relational biết rằng thuộc tính là một object được ánh xạ vào cùng hàng với entity chứa nó. Các thuộc tính của object con trở thành các cột riêng trong bảng cha. Cách này phù hợp với value object như địa chỉ, khoảng thời gian, thông tin tiền tệ hoặc một nhóm giá trị có ý nghĩa nghiệp vụ.

Ví dụ, một đơn hàng chứa địa chỉ giao hàng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

import static org.springframework.data.relational.core.mapping.Embedded.OnEmpty.USE_NULL;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @Embedded(prefix = "shipping_", onEmpty = USE_NULL)
    private Address shippingAddress;
}

public class Address {
    private String street;
    private String city;
    private String postalCode;
}
```

Với prefix `shipping_`, các thuộc tính của `Address` được ánh xạ vào các cột tương ứng trong bảng `purchase_order`, chẳng hạn:

| Thuộc tính Java | Cột trong bảng `purchase_order` |
|---|---|
| `id` | `id` |
| `orderNumber` | `order_number` (theo quy tắc đặt tên mặc định) |
| `shippingAddress.street` | `shipping_street` |
| `shippingAddress.city` | `shipping_city` |
| `shippingAddress.postalCode` | `shipping_postal_code` |

Tên cột thực tế còn phụ thuộc naming strategy và `@Column` được khai báo. Prefix giúp tránh trùng tên khi entity cha và nhiều object nhúng có thuộc tính giống nhau. Có thể chọn prefix khác cho từng thuộc tính, ví dụ `billing_` và `shipping_` cho hai địa chỉ cùng kiểu `Address`.

### 2.1 Ý nghĩa của prefix và @Column

`prefix` được thêm vào tên các cột của object nhúng. Nó không tạo bảng mới và cũng không tạo quan hệ khóa ngoại. Các trường vẫn nằm trong cùng một hàng dữ liệu với entity cha.

Nếu cần tên cột cụ thể, có thể đặt `@Column` trên thuộc tính của value object:

```java
public class Address {
    @Column("street_name")
    private String street;

    private String city;
}
```

Khi kết hợp với prefix, hãy kiểm tra tên cột cuối cùng theo quy tắc ánh xạ của phiên bản đang dùng và đối chiếu với schema. Không nên tự giả định rằng tên cột trong database luôn giống chính xác tên field Java.

### 2.2 Xử lý object nhúng rỗng hoặc null

Khi đọc một hàng, Spring Data cần quyết định cách tạo thuộc tính `Address` nếu tất cả cột của object nhúng đều có giá trị `NULL`. Thuộc tính `onEmpty` điều khiển hành vi này trong API `@Embedded` hiện hành:

- `USE_NULL`: nếu tất cả cột của object nhúng đều rỗng, ánh xạ thuộc tính thành `null`.
- `USE_EMPTY`: tạo một instance của object nhúng ngay cả khi tất cả các cột của nó đều rỗng.

Ví dụ:

```java
@Embedded(prefix = "billing_", onEmpty = USE_NULL)
private Address billingAddress;

@Embedded(prefix = "contact_", onEmpty = Embedded.OnEmpty.USE_EMPTY)
private ContactDetails contactDetails;
```

Chọn `USE_NULL` khi object chỉ có ý nghĩa nếu ít nhất một trường được lưu. Chọn `USE_EMPTY` khi domain model yêu cầu thuộc tính luôn có một object, kể cả khi các trường thành phần chưa có giá trị. Cần bảo đảm kiểu object có thể được Spring Data khởi tạo theo constructor/property access đã cấu hình.

Các cột của một object nhúng có thể đều `NULL` khi dữ liệu chưa được nhập hoặc khi ứng dụng chủ động lưu object rỗng. Vì vậy, quyết định `onEmpty` là một phần của mô hình dữ liệu, không chỉ là tùy chọn trình bày object Java.

## 3. Object lồng nhau trong aggregate: @MappedCollection

Không phải object con nào cũng phù hợp với `@Embedded`. Khi aggregate root chứa một collection gồm nhiều phần tử, thường cần lưu các phần tử trong bảng riêng. `@MappedCollection` mô tả collection thuộc aggregate và cột liên kết các hàng con về aggregate root.

Ví dụ, một đơn hàng có nhiều dòng hàng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;
import java.util.List;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

@Table("order_line")
public class OrderLine {
    private String productCode;
    private int quantity;
}
```

Với mapping này, `purchase_order` lưu aggregate root, còn các phần tử được lưu trong `order_line`. Cột `order_id` ở bảng con liên kết mỗi dòng hàng với đơn hàng tương ứng. Khi Spring Data lưu aggregate root, các phần tử thuộc collection được xử lý theo mapping của aggregate.

Nếu collection có thứ tự, có thể cần cột lưu chỉ số để khôi phục thứ tự phần tử. `@MappedCollection` hỗ trợ khai báo `keyColumn` cho trường hợp cần lưu key/index của collection:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_position")
private List<OrderLine> lines;
```

Schema phải có các cột tương ứng. Với `Map`, key column có thể lưu khóa của từng phần tử. Tên bảng, cột ID và cột key cần thống nhất với migration của dự án.

`@MappedCollection` diễn tả quan hệ bên trong aggregate. Nó không biến mọi association giữa các entity thành quan hệ được quản lý tự động như trong ORM đầy đủ. Cần giữ collection trong phạm vi aggregate root và tránh dùng nó để tải một đồ thị object lớn không có ranh giới rõ ràng.

## 4. Tham chiếu aggregate khác bằng định danh

Khi một entity cần tham chiếu đến aggregate độc lập, cách thiết kế phổ biến là lưu ID của aggregate kia. Ví dụ, `PurchaseOrder` lưu `customerId` thay vì nhúng toàn bộ `Customer` vào object graph.

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private Long customerId;
}
```

Spring Data Relational cũng cung cấp `AggregateReference` để thể hiện rõ một tham chiếu đến aggregate khác:

```java
import org.springframework.data.relational.core.mapping.AggregateReference;

@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
```

`AggregateReference<Customer, Long>` biểu diễn định danh của aggregate `Customer` có kiểu ID là `Long`. Nó giúp mô hình domain thể hiện rằng thuộc tính là một tham chiếu đến aggregate khác. Nó không tự tải `Customer`, không tạo lazy proxy và không tự đồng bộ object khách hàng khi đơn hàng được lưu.

Khi cần tên khách hàng hoặc dữ liệu chi tiết, ứng dụng thực hiện truy vấn riêng hoặc viết SQL join cho use case đọc. Cách làm này giữ ranh giới cập nhật giữa các aggregate rõ ràng và tránh phụ thuộc vào việc framework tự duyệt object graph.

## 5. Lưu object lồng nhau dưới dạng JSON

Có trường hợp object con là một cấu trúc linh hoạt, ít cần truy vấn theo từng thuộc tính, hoặc schema của nó thay đổi thường xuyên. Khi database hỗ trợ JSON/JSONB, ứng dụng có thể chọn lưu object vào một cột JSON.

Không nên mặc định rằng mọi POJO được khai báo thành một thuộc tính sẽ tự động được tuần tự hóa thành JSON. Cần có conversion phù hợp giữa kiểu Java và kiểu dữ liệu mà R2DBC driver cung cấp. Kiểu nguồn/đích cụ thể phụ thuộc database và driver; ví dụ PostgreSQL R2DBC cung cấp kiểu `Json` riêng trong driver.

Ví dụ minh họa converter cho PostgreSQL:

```java
import io.r2dbc.postgresql.codec.Json;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class PreferencesWriteConverter
        implements Converter<Preferences, Json> {

    private final ObjectMapper objectMapper;

    public PreferencesWriteConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Json convert(Preferences source) {
        try {
            return Json.of(objectMapper.writeValueAsString(source));
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot serialize preferences", ex);
        }
    }
}

@ReadingConverter
public class PreferencesReadConverter
        implements Converter<Json, Preferences> {

    private final ObjectMapper objectMapper;

    public PreferencesReadConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Preferences convert(Json source) {
        try {
            return objectMapper.readValue(source.asString(), Preferences.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot deserialize preferences", ex);
        }
    }
}
```

Đây là ví dụ theo kiểu JSON của PostgreSQL driver; các import, constructor và converter cần được điều chỉnh theo phiên bản dependency của ứng dụng. Đăng ký converter đọc/ghi trong custom conversions của Spring Data R2DBC để mapping context sử dụng chúng. Schema cũng cần khai báo cột có kiểu JSON/JSONB phù hợp.

JSON giúp lưu cấu trúc linh hoạt trong một cột, nhưng có những đánh đổi:

- Các trường bên trong object không còn là các cột quan hệ độc lập theo mapping thông thường.
- Truy vấn, index và cập nhật một phần JSON phụ thuộc khả năng của hệ quản trị cơ sở dữ liệu.
- Ràng buộc dữ liệu và kiểm tra kiểu có thể ít chặt chẽ hơn so với các cột quan hệ được chuẩn hóa.
- Converter cần xử lý lỗi tuần tự hóa, thay đổi schema JSON và tương thích dữ liệu đã lưu từ phiên bản ứng dụng cũ.

Chọn JSON khi cấu trúc dữ liệu phù hợp với kiểu lưu trữ này, không chỉ vì muốn tránh khai báo các cột quan hệ.

## 6. Truy vấn nhiều bảng và ánh xạ vào DTO lồng nhau

Một trường hợp khác là ứng dụng cần hiển thị dữ liệu tổng hợp từ nhiều bảng. Đây thường là nhu cầu đọc, không nhất thiết là một aggregate cần được lưu dưới dạng object graph. Có thể viết SQL join và trả về projection hoặc DTO chứa đúng dữ liệu cần dùng.

Ví dụ, màn hình danh sách đơn hàng cần mã đơn, tên khách hàng và thành phố giao hàng:

```java
public record OrderListRow(
    Long orderId,
    String orderNumber,
    String customerName,
    String shippingCity
) {}

@Query("""
    SELECT o.id AS orderId,
           o.order_number AS orderNumber,
           c.name AS customerName,
           o.shipping_city AS shippingCity
    FROM purchase_order o
    JOIN customer c ON c.id = o.customer_id
    ORDER BY o.id
    """)
Flux<OrderListRow> findOrderList();
```

DTO phẳng thường đơn giản và rõ ràng cho truy vấn tổng hợp. Nếu API cần object lồng nhau như `OrderView` chứa `CustomerView` và `AddressView`, có thể ánh xạ từ projection phẳng sang object trả về ở tầng ứng dụng, hoặc sử dụng row mapping tùy chỉnh khi cần kiểm soát kết quả chi tiết.

Không nên giả định rằng SQL join sẽ tự động nạp toàn bộ quan hệ thành object graph giống lazy/eager fetching của JPA. Câu SQL quyết định những cột được trả về, còn cách xây dựng DTO lồng nhau cần được thể hiện rõ trong mapping hoặc trong code chuyển đổi.

## 7. Giới hạn của ánh xạ object lồng nhau

Spring Data R2DBC cung cấp object mapping, nhưng phạm vi của nó gắn với mô hình Spring Data Relational. Cần lưu ý các giới hạn sau:

### 7.1 Embedded không phải quan hệ bảng riêng

`@Embedded` chỉ trải các thuộc tính của value object vào cùng hàng dữ liệu. Nó không tạo bảng con, khóa ngoại hay một entity có định danh riêng. Nếu object có vòng đời độc lập, được nhiều aggregate tham chiếu hoặc cần truy vấn/cập nhật độc lập, hãy cân nhắc mô hình bảng riêng và tham chiếu bằng ID.

### 7.2 Không có lazy loading tự động cho object lồng nhau

Spring Data R2DBC không dùng proxy để tải object con khi getter được gọi. `@Embedded` được đọc từ các cột của cùng hàng; `@MappedCollection` được tải theo thao tác đọc aggregate; aggregate reference chỉ giữ định danh. Khi cần dữ liệu khác, ứng dụng thực hiện truy vấn reactive tương ứng.

### 7.3 Không tự đồng bộ mọi object trong object graph

Không có persistence context kiểu JPA để theo dõi thay đổi của mọi object con. Ứng dụng cần gọi thao tác lưu phù hợp trên aggregate root hoặc repository tương ứng. Cần thiết kế transaction nếu nhiều thao tác lưu phải cùng thành công hoặc thất bại.

### 7.4 Không tự suy luận JSON cho mọi kiểu dữ liệu

Kiểu Java phức tạp cần conversion mà driver và Spring Data hiểu được. Nếu database dùng kiểu JSON riêng, cần converter hoặc codec tương thích. Chỉ thêm thuộc tính kiểu POJO vào entity không bảo đảm framework sẽ serialize nó theo định dạng mong muốn.

### 7.5 Không phải mọi projection đều tạo được object graph tùy ý

Khi truy vấn join, kết quả SQL là các cột và hàng. Nếu cấu trúc trả về có nhiều tầng object, hãy xác định rõ alias, DTO, converter hoặc row mapper. Không nên dựa vào việc framework tự suy ra quan hệ lồng nhau từ tên cột trong mọi trường hợp.

## 8. Khác biệt API giữa các phiên bản Spring Data Relational

Các ví dụ mapping cần khớp với phiên bản Spring Data Relational mà ứng dụng đang sử dụng. API cho embedded object đã thay đổi giữa các thế hệ phiên bản, vì vậy một ví dụ lấy từ tài liệu cũ có thể không biên dịch trong dự án mới.

Một khác biệt đáng chú ý là cách khai báo null/empty cho `@Embedded`:

| Dòng phiên bản | Cách khai báo thường gặp |
|---|---|
| Spring Data Relational 2.x | Có thể gặp các annotation lồng như `@Embedded.Nullable` và `@Embedded.Empty`, kèm `prefix`. |
| Spring Data Relational 3.x trở lên | Dùng `@Embedded(prefix = "...", onEmpty = USE_NULL)` hoặc `onEmpty = USE_EMPTY`. |

Ví dụ theo API cũ có thể có dạng:

```java
@Embedded.Nullable(prefix = "address_")
private Address address;
```

Trong API mới, cách diễn đạt tương ứng được tập trung vào thuộc tính `onEmpty`:

```java
@Embedded(prefix = "address_", onEmpty = USE_NULL)
private Address address;
```

Không trộn cú pháp của hai thế hệ API trong cùng một dự án. Nếu nâng cấp Spring Data Relational, cần cập nhật import, annotation và cách cấu hình embedded object theo tài liệu của phiên bản đích.

Ngoài `@Embedded`, cần kiểm tra phiên bản của các thành phần liên quan như `@MappedCollection`, custom conversions, driver R2DBC và kiểu JSON. Khả năng mapping một kiểu dữ liệu còn phụ thuộc driver: cùng một cột database có thể được biểu diễn bằng kiểu Java khác nhau giữa các driver.

Spring Boot thường quản lý các phiên bản Spring Data thông qua dependency management/BOM. Khi dùng Spring Boot, nên để bộ phiên bản được quản lý đồng bộ, tránh nâng riêng một module Spring Data lên major version khác với các module còn lại. Khi không dùng Spring Boot, cần kiểm tra ma trận tương thích giữa Spring Framework, Spring Data Relational, Spring Data R2DBC và driver.

Nếu một ví dụ trên mạng không biên dịch, hãy kiểm tra theo thứ tự: phiên bản Spring Data Relational thực tế, import của annotation, chữ ký API trong Javadoc tương ứng, rồi đến kiểu dữ liệu mà driver trả về. Không nên sửa code bằng cách đổi annotation ngẫu nhiên mà chưa xác định phiên bản API.

## 9. Ví dụ thiết kế kết hợp nhiều chiến lược

Một mô hình đơn hàng có thể kết hợp value object, collection thuộc aggregate và tham chiếu đến aggregate khác:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private AggregateReference<Customer, Long> customer;

    @Embedded(prefix = "shipping_", onEmpty = USE_NULL)
    private Address shippingAddress;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_position")
    private List<OrderLine> lines;
}

public class Address {
    private String street;
    private String city;
    private String postalCode;
}

@Table("order_line")
public class OrderLine {
    private String productCode;
    private int quantity;
}
```

Trong mô hình này:

- `shippingAddress` là value object, được lưu bằng các cột `shipping_*` ngay trong `purchase_order`.
- `lines` là collection các phần tử thuộc aggregate `PurchaseOrder`, được lưu trong bảng `order_line` và liên kết bằng `order_id`.
- `customer` là tham chiếu đến aggregate `Customer`, được biểu diễn bằng định danh và không tự tải toàn bộ khách hàng.

Schema tương ứng phải được tạo bằng migration và khớp với các tên bảng/cột trong mapping. Ví dụ chỉ minh họa cấu trúc domain và annotation; constructor, getter/setter, import và cách tạo instance được bổ sung theo phong cách code của dự án.

## 10. Cách chọn và kiểm tra mapping trong dự án

Khi thiết kế một thuộc tính object lồng nhau, hãy trả lời lần lượt:

1. Object đó có định danh và vòng đời độc lập không? Nếu có, cân nhắc entity/aggregate riêng và tham chiếu bằng ID.
2. Object đó có phải một phần giá trị không thể tách khỏi entity cha không? Nếu có, `@Embedded` thường phù hợp.
3. Object đó là một phần tử trong collection thuộc aggregate root không? Nếu có, xem xét `@MappedCollection` và bảng con.
4. Dữ liệu cần lưu dưới dạng JSON vì tính linh hoạt hoặc yêu cầu của database không? Nếu có, khai báo custom converter/codec tương ứng với driver.
5. Object lồng nhau chỉ phục vụ một màn hình đọc? Nếu có, SQL join cùng projection/DTO có thể rõ ràng hơn việc mở rộng aggregate.
6. Phiên bản Spring Data Relational của dự án hỗ trợ cú pháp annotation nào? Kiểm tra BOM và Javadoc trước khi dùng ví dụ.

Sau khi chọn mapping, cần đồng bộ entity với schema migration, kiểm tra tên cột sau khi áp dụng prefix, kiểm tra trường hợp object nhúng toàn `NULL`, và chạy truy vấn đọc/ghi trên đúng driver đang dùng. Với JSON, cần kiểm tra cả hai chiều serialize/deserialize và dữ liệu cũ. Với collection, cần kiểm tra khóa liên kết và thứ tự phần tử nếu thứ tự có ý nghĩa nghiệp vụ.

Ánh xạ object lồng nhau trong Spring Data R2DBC hiệu quả nhất khi cấu trúc Java phản ánh đúng mô hình lưu trữ: value object được nhúng vào cùng hàng, collection thuộc aggregate được lưu trong bảng con, aggregate độc lập được tham chiếu bằng ID, còn dữ liệu tổng hợp được đọc qua query và projection. Chọn đúng chiến lược và dùng cú pháp phù hợp với phiên bản Spring Data Relational giúp tránh kỳ vọng sai về khả năng ORM và giữ cho mapping ổn định khi ứng dụng phát triển.

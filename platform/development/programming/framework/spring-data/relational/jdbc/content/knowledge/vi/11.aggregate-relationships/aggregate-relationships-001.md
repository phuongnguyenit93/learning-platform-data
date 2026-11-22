# Ánh xạ quan hệ một-một có sở hữu trong aggregate

Trong **Spring Data Relational JDBC**, một aggregate root là điểm vào để đọc và ghi một nhóm đối tượng có cùng vòng đời nghiệp vụ. Bên trong aggregate, root có thể sở hữu một entity con theo quan hệ **một-một (one-to-one)**: ví dụ một đơn hàng có một bộ thông tin giao hàng, một hồ sơ khách hàng có một phần thông tin định danh, hoặc một thiết bị có một cấu hình riêng.

Điều quan trọng là phân biệt ba cách lưu dữ liệu:

- **Entity con có bảng riêng:** root giữ một thuộc tính tham chiếu đến đúng một entity con; bảng con chứa khóa ngoại trỏ về root. Đây là quan hệ một-một có sở hữu trong aggregate.
- **Value object nhúng (embedded):** thuộc tính là một phần giá trị của root và các cột của nó nằm ngay trong bảng root.
- **Tham chiếu sang aggregate khác:** root chỉ lưu định danh của aggregate khác, thường dùng `AggregateReference`. Aggregate kia có vòng đời và quyền sở hữu độc lập.

Spring Data JDBC hỗ trợ tham chiếu entity con một-một trong aggregate. Khi tham chiếu được xem là một phần aggregate, root quản lý vòng đời của entity con. Bài học này dùng PostgreSQL và Spring Data JDBC để trình bày mapping, schema, thao tác repository và các ràng buộc cần có.

## 1. Aggregate root và quan hệ một-một có sở hữu

Giả sử hệ thống bán hàng có mô hình:

```text
PurchaseOrder (aggregate root)
       │
       │ sở hữu 0..1
       ▼
ShippingDetails (entity con)

PurchaseOrder
  ├── id
  ├── orderNumber
  └── shippingDetails
        ├── recipientName
        ├── street
        └── phone
```

`PurchaseOrder` là aggregate root vì các thao tác nghiệp vụ với đơn hàng bắt đầu từ nó. `ShippingDetails` là entity con vì nó thuộc về một đơn hàng cụ thể, không được chia sẻ giữa nhiều đơn hàng và không có vòng đời độc lập.

Quan hệ "có sở hữu" thể hiện qua các quy tắc:

1. Mỗi bộ `ShippingDetails` thuộc về đúng một `PurchaseOrder`.
2. Một đơn hàng có thể chưa có hoặc có một bộ thông tin giao hàng.
3. Không tạo repository riêng để quản lý `ShippingDetails` như một aggregate root độc lập.
4. Thêm, thay đổi hoặc bỏ thông tin giao hàng được thực hiện thông qua thao tác trên `PurchaseOrder`.
5. Khi tham chiếu con bị loại khỏi aggregate, entity con cũ được xem là không còn thuộc aggregate và bị xóa theo quy tắc persistence của Spring Data JDBC.

Trong ví dụ này, cardinality ở phía domain là **0..1**: một đơn hàng có thể chưa được gán địa chỉ giao hàng. Nếu nghiệp vụ bắt buộc mỗi đơn hàng phải có địa chỉ, cần kiểm tra invariant đó khi tạo/cập nhật đơn hàng.

## 2. Mapping entity con trong một bảng riêng

Spring Data JDBC nhận diện một property kiểu entity tham chiếu đến entity khác là quan hệ một-một hoặc embedded type theo mapping model. Khi muốn entity con được lưu trong **bảng riêng**, khai báo property trên aggregate root và có thể dùng `@MappedCollection` để chỉ định tên cột khóa ngoại ở bảng con.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "purchase_order_id")
    private ShippingDetails shippingDetails;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber, ShippingDetails shippingDetails) {
        this.orderNumber = orderNumber;
        this.shippingDetails = shippingDetails;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public ShippingDetails getShippingDetails() {
        return shippingDetails;
    }

    public void changeShippingDetails(ShippingDetails details) {
        this.shippingDetails = details;
    }
}

@Table("shipping_details")
public class ShippingDetails {

    private String recipientName;
    private String street;
    private String phone;

    protected ShippingDetails() {
    }

    public ShippingDetails(String recipientName, String street, String phone) {
        this.recipientName = recipientName;
        this.street = street;
        this.phone = phone;
    }

    public String getRecipientName() {
        return recipientName;
    }

    public String getStreet() {
        return street;
    }

    public String getPhone() {
        return phone;
    }
}
```

Ở đây:

- `@Table("purchase_order")` xác định bảng của aggregate root.
- `@Id` đánh dấu khóa chính của root.
- `shippingDetails` là một property đơn, không phải collection.
- `@MappedCollection(idColumn = "purchase_order_id")` đặt tên cột back-reference trong bảng entity con.
- `ShippingDetails` không cần có `@Id` riêng trong ví dụ này. Với quan hệ một-một, entity con có thể có hoặc không có property ID; nếu không có, khóa ngoại của root thường được dùng làm định danh duy nhất trong schema.

Spring Data JDBC không dùng annotation JPA `@OneToOne` ở đây. Không thêm `@OneToOne`, `@JoinColumn` hoặc `cascade = ...` từ JPA vào entity Spring Data JDBC với kỳ vọng chúng điều khiển mapping này.

## 3. Schema database và ràng buộc one-to-one

Một schema PostgreSQL tương ứng:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE shipping_details (
    purchase_order_id BIGINT PRIMARY KEY
        REFERENCES purchase_order(id),
    recipient_name VARCHAR(120) NOT NULL,
    street VARCHAR(255) NOT NULL,
    phone VARCHAR(30)
);
```

Ở bảng `shipping_details`, `purchase_order_id` vừa là khóa chính vừa là khóa ngoại:

- Khóa ngoại bảo đảm entity con không tham chiếu tới đơn hàng không tồn tại.
- Khóa chính bảo đảm mỗi đơn hàng xuất hiện tối đa một lần trong bảng con.
- Một đơn hàng chưa có thông tin giao hàng được biểu diễn bằng việc chưa có hàng tương ứng trong `shipping_details`.

Đây là cách biểu diễn quan hệ **0..1 từ root tới child**. Một khóa ngoại đơn thuần chưa bảo đảm mọi đơn hàng đều có một hàng con. Nếu nghiệp vụ yêu cầu **chính xác 1..1**, hãy bảo đảm invariant đó trong domain/service và transaction tạo đơn hàng; hoặc cân nhắc lưu các trường giao hàng dưới dạng embedded trong cùng bảng nếu chúng thực sự là một phần bắt buộc của hàng root.

Nếu muốn entity con có ID riêng, có thể thiết kế:

```sql
CREATE TABLE shipping_details (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL UNIQUE
        REFERENCES purchase_order(id),
    recipient_name VARCHAR(120) NOT NULL,
    street VARCHAR(255) NOT NULL,
    phone VARCHAR(30)
);
```

Khi đó class `ShippingDetails` khai báo thêm `@Id private Long id;`. Ràng buộc `UNIQUE(purchase_order_id)` vẫn cần thiết để database bảo đảm một đơn hàng không có nhiều hàng con. Việc có ID riêng hữu ích nếu cần định danh kỹ thuật cho hàng con, nhưng không làm nó tự động trở thành aggregate root độc lập.

### 3.1. Vì sao phải có UNIQUE hoặc PRIMARY KEY trên khóa ngoại?

Nếu chỉ tạo:

```sql
purchase_order_id BIGINT REFERENCES purchase_order(id)
```

thì nhiều hàng `shipping_details` có thể cùng trỏ tới một `purchase_order`. Database khi đó đang cho phép một đơn hàng có nhiều bộ thông tin giao hàng, tức quan hệ một-nhiều ở tầng dữ liệu.

Muốn quan hệ một-một, cần ràng buộc duy nhất ở phía bảng con:

```sql
ALTER TABLE shipping_details
    ADD CONSTRAINT uq_shipping_details_order
    UNIQUE (purchase_order_id);
```

Ràng buộc domain trong Java giúp code diễn đạt ý định; ràng buộc database bảo vệ dữ liệu kể cả khi có script SQL, batch job hoặc service khác ghi trực tiếp vào DB.

## 4. Tùy chỉnh tên khóa ngoại bằng @MappedCollection

Nếu không khai báo tên cột, Spring Data JDBC dùng `NamingStrategy` để xác định back-reference dựa trên tên bảng/kiểu entity tham chiếu. Trong schema đã tồn tại hoặc khi muốn tên dễ hiểu, chỉ định rõ `idColumn`:

```java
@Table("purchase_order")
class PurchaseOrder {
    @Id
    private Long id;

    @MappedCollection(idColumn = "purchase_order_id")
    private ShippingDetails shippingDetails;
}
```

`idColumn` là tên cột nằm ở **bảng con**, dùng để tham chiếu ID của aggregate root. Nó không phải tên property Java của root và cũng không phải cột khóa chính của bảng root.

Với một property con đơn, không cần `keyColumn`. `keyColumn` dành cho các cấu trúc như `List` hoặc `Map`, nơi database cần thêm cột lưu vị trí phần tử hoặc map key.

Nếu đổi tên bảng bằng `@Table` hoặc thay naming strategy, hãy xác nhận tên back-reference thực tế. Đừng suy ra tên khóa ngoại chỉ từ tên class; mapping context, annotation và chiến lược đặt tên đều có thể ảnh hưởng kết quả.

## 5. Lưu aggregate qua repository

Repository được tạo cho **aggregate root**:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Tạo đơn hàng cùng thông tin giao hàng:

```java
ShippingDetails details = new ShippingDetails(
        "Nguyen An",
        "12 Nguyen Trai, District 1",
        "0900000000"
);

PurchaseOrder order = new PurchaseOrder("PO-2026-001", details);
PurchaseOrder saved = purchaseOrderRepository.save(order);
```

Khi lưu root, Spring Data JDBC xử lý các entity thuộc aggregate theo mapping. Root và entity con được ghi trong cùng hoạt động persistence của aggregate; ID của root được dùng để điền back-reference ở bảng con. Không cần tự lấy ID root rồi chạy thêm một lệnh insert riêng cho child.

Đọc lại:

```java
Optional<PurchaseOrder> result =
        purchaseOrderRepository.findById(saved.getId());

result.ifPresent(found -> {
    ShippingDetails shipping = found.getShippingDetails();
    if (shipping != null) {
        System.out.println(shipping.getRecipientName());
    }
});
```

Spring Data JDBC nạp aggregate theo mapping của nó; không cần khai báo một repository riêng cho `ShippingDetails` chỉ để đọc phần con. Tùy dialect và mapping, việc nạp các phần của aggregate có thể cần nhiều câu SQL; đừng giả định quan hệ luôn được tải bằng một câu JOIN duy nhất.

### 5.1. Thay đổi thông tin con

Thay đổi địa chỉ thông qua aggregate root:

```java
PurchaseOrder order = purchaseOrderRepository.findById(orderId)
        .orElseThrow();

order.changeShippingDetails(new ShippingDetails(
        "Tran B",
        "45 Le Loi, District 1",
        "0911111111"
));

purchaseOrderRepository.save(order);
```

Root vẫn là đối tượng được lưu. Spring Data JDBC quản lý entity con như một phần của aggregate khi persistence root. Vì vậy, không nên giữ một service/repository độc lập để cập nhật `ShippingDetails` rồi bỏ qua aggregate root.

### 5.2. Bỏ thông tin con

Nếu đơn hàng được phép bỏ địa chỉ giao hàng:

```java
PurchaseOrder order = purchaseOrderRepository.findById(orderId)
        .orElseThrow();

order.changeShippingDetails(null);
purchaseOrderRepository.save(order);
```

Khi tham chiếu owned child bị loại khỏi aggregate, Spring Data JDBC xem entity con cũ là không còn thuộc aggregate và xóa hàng tương ứng theo cơ chế lưu aggregate. Đây là khác biệt quan trọng với một ID tham chiếu tới aggregate khác: bỏ một owned reference có thể xóa entity con; bỏ một external reference không có nghĩa xóa aggregate được tham chiếu.

Nếu ứng dụng có bảng khác hoặc hệ thống ngoài tham chiếu trực tiếp tới hàng `shipping_details`, cần xem lại ranh giới aggregate. Một entity con bị xóa theo vòng đời root không nên bị coi là tài nguyên dùng chung.

## 6. Entity con có ID riêng hay dùng khóa ngoại làm định danh?

Spring Data JDBC cho phép entity tham chiếu một-một không có property `@Id` riêng. Lựa chọn phụ thuộc ý nghĩa domain và schema:

| Thiết kế | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Không có ID riêng; FK là PK | Child chỉ tồn tại cùng root, mỗi root tối đa một child | Value-like child có hàng riêng nhưng không cần định danh độc lập |
| Có ID riêng và FK UNIQUE | Child có khóa kỹ thuật, vẫn chỉ thuộc một root | Cần ID nội bộ cho tích hợp, audit hoặc khóa kỹ thuật |
| `@Embedded` | Không có bảng con; field trở thành cột trong bảng root | Value object nhỏ, không cần hàng riêng |
| `AggregateReference` | Lưu ID của một aggregate độc lập | Đối tượng được tham chiếu có vòng đời và quyền sở hữu riêng |

Đừng thêm ID riêng chỉ vì mọi bảng khác đều có ID. Nếu child chỉ là thành phần của root, dùng FK làm PK có thể diễn đạt quan hệ sở hữu rõ ràng hơn. Ngược lại, nếu cần ID cho một quy trình tích hợp hoặc khóa ngoại riêng, ID riêng là lựa chọn hợp lệ; vẫn phải giữ UNIQUE trên FK nếu quan hệ là một-một.

## 7. Phân biệt entity con một-một với @Embedded

Một object lồng trong entity không phải lúc nào cũng cần bảng riêng. Nếu nó là **value object** và dữ liệu có thể nằm ngay trên cùng hàng, dùng `@Embedded`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @Embedded.Nullable(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}

public record ShippingAddress(
        String recipientName,
        String street,
        String phone
) {}
```

Với prefix `shipping_`, các property của value object được ánh xạ thành các cột cùng bảng, ví dụ:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    shipping_recipient_name VARCHAR(120),
    shipping_street VARCHAR(255),
    shipping_phone VARCHAR(30)
);
```

`@Embedded` không tạo foreign key hay hàng ở bảng khác. Tùy `onEmpty`, nếu các cột nhúng đều `NULL` thì property có thể được materialize thành `null` hoặc một object rỗng. `@Embedded.Nullable` là cách viết tắt cho chế độ coi object là null khi tất cả các cột của nó rỗng.

So sánh:

| Tiêu chí | Entity con một-một trong bảng riêng | Value object `@Embedded` |
| --- | --- | --- |
| Số bảng | Root và child có bảng riêng | Chỉ bảng root |
| Khóa ngoại | Có back-reference từ child tới root | Không có |
| ID child | Có thể có hoặc không | Không cần ID riêng |
| Vòng đời | Thuộc aggregate root | Là một phần giá trị của root |
| Phù hợp | Child có cấu trúc/lưu trữ riêng hoặc nhiều thuộc tính | Nhóm giá trị thuần, không cần hàng riêng |

Không dùng `@Embedded` nếu bạn muốn một bảng con có khóa ngoại. Ngược lại, không tạo bảng con chỉ để biểu diễn một nhóm vài giá trị không có vòng đời riêng nếu embedded mapping đáp ứng tốt hơn.

## 8. Phân biệt owned one-to-one với AggregateReference

Giả sử một đơn hàng thuộc về một khách hàng. Khách hàng có thể tạo nhiều đơn hàng và tồn tại độc lập với từng đơn hàng. `Customer` vì vậy là aggregate root khác, không phải entity con được sở hữu bên trong `PurchaseOrder`.

Mô hình tham chiếu:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
```

`AggregateReference` lưu định danh của aggregate khác và thể hiện ranh giới giữa hai aggregate. Spring Data JDBC không tải toàn bộ `Customer` như một entity con thuộc đơn hàng chỉ vì có reference này, và xóa đơn hàng không có nghĩa xóa khách hàng.

| Thuộc tính | Owned one-to-one child | AggregateReference |
| --- | --- | --- |
| Ranh giới | Cùng aggregate | Aggregate khác |
| Lưu trong domain object | Object con thực tế | ID được bọc bởi `AggregateReference` |
| Bảng dữ liệu | Child table có FK quay về root | Root lưu ID tham chiếu; aggregate kia có bảng/lifecycle riêng |
| Vòng đời | Root quản lý child | Mỗi aggregate được lưu/xóa độc lập |
| Bỏ tham chiếu | Entity con cũ bị loại khỏi aggregate và bị xóa theo persistence | Không xóa aggregate đích |
| Ví dụ | Đơn hàng và địa chỉ giao hàng riêng của đơn đó | Đơn hàng và khách hàng |

Nếu nhiều đơn hàng cùng tham chiếu một khách hàng, không nhúng object `Customer` vào từng đơn hàng như owned child. Hãy dùng ID/`AggregateReference` để không tạo ra quan hệ sở hữu sai.

## 9. Transaction và tính nhất quán

Tạo một root và child thường là một thao tác nghiệp vụ. Nếu root được insert nhưng child insert thất bại, hệ thống không nên để lại một aggregate dở dang nếu domain yêu cầu chúng phải được tạo cùng nhau.

Với Spring, có thể đặt thao tác ở service và dùng `@Transactional`:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder createOrder(
            String orderNumber,
            ShippingDetails shippingDetails) {
        PurchaseOrder order =
                new PurchaseOrder(orderNumber, shippingDetails);
        return repository.save(order);
    }
}
```

Transaction manager phù hợp với `DataSource` sẽ quản lý commit/rollback. Khi có thêm thao tác nghiệp vụ khác cần cùng transaction, giữ chúng trong cùng transaction boundary. Không tự mở một JDBC connection khác bằng `DriverManager` trong service và kỳ vọng nó tự tham gia transaction của Spring.

Ràng buộc database vẫn quan trọng ngay cả khi có transaction:

- FK ngăn child trỏ tới root không tồn tại.
- PK/UNIQUE trên back-reference ngăn nhiều child cho cùng root.
- NOT NULL trên các cột bắt buộc bảo vệ dữ liệu con.
- Validation/domain invariant ngăn tạo root thiếu child khi nghiệp vụ yêu cầu.

Transaction bảo đảm các câu lệnh trong transaction cùng commit hoặc rollback; nó không tự tạo ra ràng buộc cardinality nếu schema không khai báo.

## 10. Lỗi thường gặp và cách xác định nguyên nhân

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Table shipping_details does not exist` | Chưa tạo bảng child hoặc tên bảng không khớp mapping | Kiểm tra migration và `@Table` |
| `Column purchase_order_id does not exist` | Back-reference column thiếu hoặc `idColumn` sai | Đối chiếu `@MappedCollection` và DDL |
| Một đơn hàng có nhiều dòng child | FK không có UNIQUE/PRIMARY KEY | Thêm constraint duy nhất và xử lý dữ liệu trùng trước migration |
| Lưu root nhưng không có child | Property child null, mapping không đúng hoặc schema/SQL lỗi | Kiểm tra object trước save, mapping metadata và SQL |
| Xóa child nhưng hàng vẫn còn | Đang thao tác ngoài aggregate, mapping sai hoặc không gọi save root | Kiểm tra ranh giới aggregate và thao tác repository |
| Xóa root bị FK violation | Còn hàng tham chiếu hoặc thứ tự xóa/schema constraint không phù hợp | Xác định dependent rows và quy trình xóa |
| Muốn dùng repository cho child | Đang coi entity con là aggregate root độc lập | Thao tác qua root; nếu child có lifecycle độc lập, xem lại aggregate boundary |
| Dùng `@OneToOne` nhưng không hoạt động | Mang annotation JPA sang Spring Data JDBC | Dùng mapping relational của Spring Data JDBC |
| H2 test thành công nhưng PostgreSQL lỗi | Khác biệt dialect, DDL hoặc constraint | Chạy integration test trên PostgreSQL cùng migration |

Khi debug, kiểm tra cả ba lớp: mapping Java, schema database và SQL/exception thực tế. Đừng chỉ nhìn class có property con rồi kết luận bảng và khóa ngoại đã được tạo.

## 11. Quy trình thiết kế quan hệ một-một có sở hữu

Khi thêm một child một-một vào aggregate:

1. **Xác định ownership:** child có thuộc vòng đời của root không, có được chia sẻ hay truy cập độc lập không?
2. **Chọn cách lưu:** bảng riêng với property entity con, hay cùng bảng qua `@Embedded`?
3. **Khai báo Java mapping:** root có property đơn; dùng `@MappedCollection(idColumn = "...")` nếu cần tên back-reference cụ thể; child có `@Table` tương ứng.
4. **Thiết kế schema:** tạo FK từ child về root và PK/UNIQUE trên FK để bảo đảm cardinality một-một.
5. **Quy định optional/mandatory:** nếu 0..1, property có thể null; nếu 1..1, kiểm tra invariant trong domain/service.
6. **Lưu qua root:** tạo, cập nhật và loại bỏ child thông qua aggregate root repository.
7. **Kiểm thử trên database mục tiêu:** kiểm tra insert, read, update, remove, constraint và transaction với đúng dialect.

## 12. Bài tập thực hành

**Bài 1 — Một đơn hàng có địa chỉ giao hàng.** Tạo hai bảng `purchase_order` và `shipping_details`. Dùng `@MappedCollection(idColumn = "purchase_order_id")` cho property đơn của root. Lưu root cùng child, đọc lại và kiểm tra dữ liệu ở cả hai bảng.

**Bài 2 — Ràng buộc một-một.** Thử bỏ UNIQUE/PRIMARY KEY khỏi `shipping_details.purchase_order_id` rồi insert hai hàng cùng trỏ về một đơn hàng. Quan sát database cho phép tạo quan hệ một-nhiều. Thêm lại constraint và thử lần nữa.

**Bài 3 — Optional child.** Lưu đơn hàng không có `shippingDetails`, sau đó gắn child và lưu lại. Tiếp tục đặt property về `null`, lưu root và xác nhận hàng con được loại khỏi aggregate.

**Bài 4 — Embedded hay bảng riêng?** Chuyển `ShippingDetails` sang `@Embedded.Nullable(prefix = "shipping_")`. So sánh DDL, SQL và cách biểu diễn dữ liệu với phương án bảng riêng.

**Bài 5 — Ranh giới aggregate.** Thêm `Customer` được nhiều đơn hàng tham chiếu. Dùng `AggregateReference<Customer, Long>` trong `PurchaseOrder` và xác nhận xóa một đơn hàng không xóa khách hàng.

### Tài liệu tham khảo

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity references, one-to-one, back references, `@MappedCollection` và `@Embedded`.

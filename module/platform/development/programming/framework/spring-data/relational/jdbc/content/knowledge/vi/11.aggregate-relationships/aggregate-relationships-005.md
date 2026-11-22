# Cấu hình `@MappedCollection` với `idColumn` và `keyColumn`

Trong **Spring Data Relational JDBC**, `@MappedCollection` mô tả cách một collection thuộc về aggregate root được lưu trong bảng quan hệ. Hai thuộc tính `idColumn` và `keyColumn` quyết định tên cột trong bảng của các phần tử được tham chiếu:

- **`idColumn`** là cột chứa ID của entity sở hữu collection — thường là aggregate root. Đây là khóa ngoại nối hàng con về hàng cha.
- **`keyColumn`** là cột chứa khóa của `Map` hoặc vị trí của phần tử trong `List`. Với `Set`, không có khóa/vị trí collection cần lưu nên thường không khai báo thuộc tính này.

Hai cột có vai trò khác nhau. `idColumn` trả lời “hàng này thuộc aggregate nào?”, còn `keyColumn` trả lời “hàng này là phần tử nào trong collection của aggregate đó?”. `keyColumn` không thay thế khóa chính của bảng con; `idColumn` cũng không phải ID riêng của entity con.

## 1. `@MappedCollection` biểu diễn quan hệ sở hữu trong aggregate

Spring Data JDBC tổ chức dữ liệu quanh **aggregate root**. Một collection được khai báo bằng `@MappedCollection` là quan hệ sở hữu: các phần tử thuộc aggregate của root và được lưu cùng vòng đời aggregate đó.

Ví dụ một đơn hàng có nhiều dòng:

```text
PurchaseOrder (aggregate root)
  id = 101
  lines
    [0] OrderLine (id = 501, productId = 10, quantity = 2)
    [1] OrderLine (id = 502, productId = 15, quantity = 1)
```

Trong database, các dòng nằm ở bảng riêng và có cột trỏ về đơn hàng:

```text
purchase_order
┌─────┐
│ id  │
├─────┤
│ 101 │
└─────┘

order_line
┌─────┬──────────┬─────────┬────────────┬──────────┐
│ id  │ order_id │ line_no │ product_id │ quantity │
├─────┼──────────┼─────────┼────────────┼──────────┤
│ 501 │ 101      │ 0       │ 10         │ 2        │
│ 502 │ 101      │ 1       │ 15         │ 1        │
└─────┴──────────┴─────────┴────────────┴──────────┘
```

Trong ví dụ:

- `order_id` là **`idColumn`**: cả hai dòng đều thuộc `PurchaseOrder.id = 101`.
- `line_no` là **`keyColumn`**: lưu vị trí của mỗi phần tử trong `List<OrderLine>`.
- `order_line.id` là khóa chính riêng của entity con, hoàn toàn khác `order_id` và `line_no`.

`@MappedCollection` không tự biến một quan hệ giữa hai aggregate root thành quan hệ sở hữu. Nó dành cho phần tử nằm trong aggregate. Nếu `OrderLine` tham chiếu một `Product` là aggregate root độc lập, thường lưu `productId` hoặc `AggregateReference<Product, Long>` trong dòng hàng; không nhúng cả aggregate `Product` vào collection của đơn hàng.

## 2. Ý nghĩa của `idColumn`

`idColumn` là tên cột trong **bảng được tham chiếu** dùng để lưu ID của entity chứa property collection. Với `PurchaseOrder.lines`, cột `order_id` ở bảng `order_line` giữ giá trị `PurchaseOrder.id`.

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
```

Ở đây Spring Data JDBC hiểu rằng các hàng `OrderLine` được gắn với `PurchaseOrder` thông qua cột `order_id`. Property `order_id` không cần xuất hiện như một field thông thường trong class `OrderLine`; framework quản lý cột liên kết theo metadata collection.

### Các điều cần giữ đúng cho `idColumn`

1. Cột phải nằm trong bảng được dùng để lưu các phần tử của collection.
2. Kiểu dữ liệu của cột phải tương thích với kiểu ID của entity sở hữu. Nếu `PurchaseOrder.id` là `BIGINT`, `order_line.order_id` cũng nên là `BIGINT`.
3. Cột phải có tên khớp với schema thật, kể cả khi naming strategy của ứng dụng dùng quy tắc khác.
4. Với schema có ràng buộc quan hệ, cột thường nên có foreign key tham chiếu đến khóa chính của root.
5. Nếu entity con có collection riêng, `idColumn` của collection con trỏ đến ID của entity sở hữu trực tiếp collection đó, không mặc định trỏ về root ở cấp trên cùng.

`idColumn` không phải tên cột ID của chính child. Ví dụ `order_line.id` vẫn có thể là khóa chính, còn `order_line.order_id` là khóa ngoại về `purchase_order.id`.

## 3. Ý nghĩa của `keyColumn`

`keyColumn` lưu thông tin định vị phần tử trong collection khi kiểu collection có thứ tự hoặc có khóa:

| Kiểu property | Giá trị được lưu trong `keyColumn` | Có cần `keyColumn` không? |
|---|---|---|
| `List<T>` | Chỉ số/vị trí của phần tử trong danh sách | Có ích để lưu và khôi phục thứ tự |
| `Map<K, V>` | Key `K` tương ứng với value `V` | Có, để khôi phục cặp key/value |
| `Set<T>` | Không có key hoặc vị trí ổn định theo hợp đồng của `Set` | Thường không |

Tên `keyColumn` được cấu hình trên property collection. Ví dụ:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
```

Trong bảng `order_line`, cột `line_no` lưu vị trí phần tử. Nếu không chỉ định `keyColumn`, Spring Data Relational sử dụng quy tắc đặt tên mặc định của `NamingStrategy`; nếu schema do nhóm phát triển tự quản lý hoặc cần tên cột ổn định, nên cấu hình tường minh.

Đối với `Map`, key được lưu ở cột riêng. Ví dụ một đơn hàng có các thuộc tính mở rộng theo tên:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")
private Map<String, OrderAttribute> attributes = new LinkedHashMap<>();
```

`attribute_name` chứa key như `"giftMessage"`, còn các property của `OrderAttribute` được ánh xạ thành các cột dữ liệu khác trong bảng con.

**Lưu ý:** không dùng tên cột chung chung như `key` nếu database có thể coi đó là từ khóa hoặc nếu khó phân biệt với khóa chính. Các tên như `line_no`, `attribute_name`, `locale_code` thường diễn đạt rõ ý nghĩa hơn.

## 4. Ví dụ đầy đủ với `List<OrderLine>`

### Aggregate root

```java
package com.example.sales;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(Long productId, int quantity) {
        if (productId == null || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        lines.add(new OrderLine(productId, quantity));
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public Long getId() {
        return id;
    }
}
```

### Entity con

```java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    @Column("product_id")
    private Long productId;

    private int quantity;

    protected OrderLine() {}

    public OrderLine(Long productId, int quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public Long getProductId() { return productId; }
    public int getQuantity() { return quantity; }
}
```

`OrderLine` không khai báo property `orderId`. `@MappedCollection` ở root đã nói với Spring Data JDBC cách lưu khóa ngoại và vị trí danh sách. Nếu thêm property `orderId` thông thường vào child mà không có mapping rõ ràng, có nguy cơ tạo một cột dữ liệu thứ hai hoặc khiến mapping không còn phản ánh đúng ownership.

### Repository

```java
package com.example.sales;

import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}
```

Sử dụng repository qua aggregate root:

```java
PurchaseOrder order = new PurchaseOrder();
order.addLine(10L, 2);
order.addLine(15L, 1);

PurchaseOrder saved = purchaseOrderRepository.save(order);

PurchaseOrder loaded = purchaseOrderRepository.findById(saved.getId())
        .orElseThrow();

List<OrderLine> lines = loaded.getLines();
```

Khi lưu root, Spring Data JDBC dùng mapping collection để ghi các dòng cùng aggregate. Khi tải root, framework dùng `order_id` để tìm các hàng con và `line_no` để khôi phục thứ tự `List`.

## 5. Schema SQL tương ứng

Ví dụ DDL cho PostgreSQL:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(id),
    CONSTRAINT uk_order_line_position
        UNIQUE (order_id, line_no)
);

CREATE INDEX idx_order_line_order_id
    ON order_line(order_id);
```

Các thành phần khớp với annotation:

| Annotation | Cột SQL | Vai trò |
|---|---|---|
| `idColumn = "order_id"` | `order_line.order_id` | ID của `PurchaseOrder` sở hữu collection |
| `keyColumn = "line_no"` | `order_line.line_no` | Vị trí phần tử trong `List<OrderLine>` |
| `@Id` của `OrderLine` | `order_line.id` | Khóa chính riêng của child |
| `@Column("product_id")` | `order_line.product_id` | Giá trị thuộc tính `productId` |

Ràng buộc `UNIQUE(order_id, line_no)` giúp một đơn không có hai phần tử cùng vị trí. Đây là ràng buộc schema minh họa; hãy chọn constraint phù hợp với quy tắc dữ liệu và database thực tế. Nếu có nhiều transaction sửa cùng aggregate, transaction và optimistic locking ở root vẫn cần được thiết kế riêng.

`@MappedCollection` **không tạo bảng hoặc migration**. Schema phải được quản lý bằng migration (Flyway/Liquibase) hoặc script phù hợp. Annotation mô tả cách ánh xạ; DDL phải thực sự có các cột được khai báo.

## 6. Ví dụ `Map<String, OrderAttribute>` với `keyColumn`

`Map` lưu cả ID của root và key của entry. Ví dụ đơn hàng có metadata theo tên:

```java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_attribute")
public class OrderAttribute {

    @Id
    private Long id;

    private String value;

    protected OrderAttribute() {}

    public OrderAttribute(String value) {
        this.value = value;
    }

    public Long getId() { return id; }
    public String getValue() { return value; }
}
```

Trong root:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")
private Map<String, OrderAttribute> attributes = new LinkedHashMap<>();
```

Ví dụ dữ liệu:

```text
PurchaseOrder.id = 101

attributes:
  "giftMessage" -> OrderAttribute(value = "Happy birthday")
  "channel"     -> OrderAttribute(value = "web")
```

Bảng `order_attribute` có thể có dạng:

| id | order_id | attribute_name | value |
|---:|---:|---|---|
| 801 | 101 | `giftMessage` | `Happy birthday` |
| 802 | 101 | `channel` | `web` |

DDL minh họa:

```sql
CREATE TABLE order_attribute (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    attribute_name VARCHAR(100) NOT NULL,
    value VARCHAR(500),
    CONSTRAINT uk_order_attribute_name UNIQUE (order_id, attribute_name)
);
```

Ở đây `attribute_name` là key của `Map`, không phải property `value` của `OrderAttribute`. Nếu key là một enum, cần xác định cách biểu diễn enum trong database (thường là tên chuỗi hoặc converter) và chọn kiểu cột tương ứng.

## 7. `Set` không cần `keyColumn`

Nếu collection không cần thứ tự hoặc key, dùng `Set` và chỉ khai báo `idColumn`:

```java
@MappedCollection(idColumn = "order_id")
private Set<OrderTag> tags = new LinkedHashSet<>();
```

Ví dụ bảng `order_tag`:

```sql
CREATE TABLE order_tag (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    tag_name VARCHAR(80) NOT NULL,
    UNIQUE (order_id, tag_name)
);
```

Không nên khai báo `keyColumn` cho `Set` với kỳ vọng nó tạo thứ tự ổn định. `Set` không có index; nếu thứ tự có ý nghĩa nghiệp vụ, hãy dùng `List` và một `keyColumn` thích hợp. Nếu cần key có tên, dùng `Map`.

## 8. Collection lồng nhau: `idColumn` trỏ đến entity sở hữu trực tiếp

Một aggregate có thể chứa nhiều cấp entity con:

```text
PurchaseOrder (id = 101)
  └── OrderLine (id = 501)
        └── LineNote (id = 901)
```

Khi `OrderLine` sở hữu `List<LineNote>`, collection `notes` được ánh xạ theo ID của `OrderLine`, không phải ID của `PurchaseOrder`:

```java
@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_line_id", keyColumn = "note_no")
    private List<LineNote> notes = new ArrayList<>();
}
```

DDL tương ứng:

```sql
CREATE TABLE line_note (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_line_id BIGINT NOT NULL REFERENCES order_line(id),
    note_no INTEGER NOT NULL,
    text VARCHAR(500) NOT NULL,
    UNIQUE (order_line_id, note_no)
);
```

`order_line_id` nối note với `OrderLine.id`. Việc note gián tiếp thuộc đơn hàng thông qua `OrderLine` không làm thay đổi quan hệ trực tiếp của collection này. Quy tắc này rất quan trọng khi đặt tên FK trong aggregate nhiều tầng.

## 9. Quy tắc đặt tên mặc định và khi nào cần khai báo tường minh

Nếu bỏ qua `idColumn` hoặc `keyColumn`, Spring Data Relational sử dụng `NamingStrategy` để suy ra tên cột theo mapping metadata. Quy tắc cụ thể có thể được tùy biến trong cấu hình. Vì vậy:

- Nếu schema được tạo theo quy ước mặc định của ứng dụng, có thể để framework suy ra tên.
- Nếu schema được quản lý độc lập, đã tồn tại từ trước hoặc dùng tên cột nghiệp vụ rõ ràng, khai báo `idColumn`/`keyColumn` tường minh để tránh lệch tên.
- Nếu dùng `NamingStrategy` tùy chỉnh, cần hiểu cách nó đặt tên collection FK và key column; annotation tường minh giúp thể hiện contract ở property.
- Tên cột trong annotation phải là **identifier SQL** phù hợp database. Không truyền tên bảng, tên property Java hoặc một biểu thức SQL vào đó.

Ví dụ tốt:

```java
@MappedCollection(idColumn = "purchase_order_id", keyColumn = "line_position")
private List<OrderLine> lines;
```

Ví dụ cần tránh:

```java
// Tên mơ hồ, dễ đụng reserved word hoặc khó hiểu schema
@MappedCollection(idColumn = "id", keyColumn = "key")
private List<OrderLine> lines;
```

`idColumn = "id"` chỉ đúng nếu bảng child thật sự có cột `id` dùng để tham chiếu root. Trong phần lớn schema có khóa chính child riêng, cột FK nên có tên riêng như `order_id`.

## 10. Thay đổi thứ tự `List` và tính ổn định của key

Với `List`, `keyColumn` lưu vị trí phần tử. Nếu thêm phần tử vào giữa hoặc sắp xếp lại list, vị trí của các phần tử sau có thể thay đổi khi aggregate được lưu. Do đó:

- Không coi `line_no` là ID ổn định của `OrderLine`.
- Không dùng index của list làm định danh bên ngoài hoặc làm khóa tham chiếu từ aggregate khác.
- Nếu một dòng hàng cần được tham chiếu ổn định, dùng `OrderLine.id`.
- Nếu thứ tự có ý nghĩa nghiệp vụ, cập nhật list thông qua root để thay đổi thứ tự một cách có chủ đích.
- Nếu cần số thứ tự hiển thị không thay đổi khi thêm/xóa dòng, đó có thể là một property domain riêng (`displaySequence`) chứ không phải vị trí collection.

`keyColumn` lưu cấu trúc collection, không tự động thể hiện mọi khái niệm thứ tự nghiệp vụ. Hãy phân biệt index nội bộ với số thứ tự do người dùng nhìn thấy.

## 11. Các lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SQL báo không tìm thấy `order_id` | `idColumn` không khớp cột FK thực tế | Kiểm tra DDL bảng child và annotation trên property collection |
| FK có giá trị sai hoặc không khớp root | Kiểu cột hoặc mapping ID không phù hợp | Kiểm tra ID của root, kiểu dữ liệu FK và quan hệ schema |
| List tải về sai thứ tự | Thiếu/sai `keyColumn`, hoặc cột index không đúng | Dùng `keyColumn` trỏ đến cột lưu vị trí; kiểm tra dữ liệu hiện hữu |
| Map mất key hoặc không khôi phục được entry | Cột key không tồn tại hoặc mapping sai kiểu | Cấu hình `keyColumn`, kiểm tra kiểu key và converter nếu cần |
| Có hai phần tử trùng vị trí/key | Thiếu constraint duy nhất hoặc dữ liệu bị ghi sai | Cân nhắc `UNIQUE(idColumn, keyColumn)` cho List/Map theo schema |
| Child có thêm cột parent không cần thiết | Vừa dùng `@MappedCollection` vừa tự mapping property parent | Chọn một cơ chế sở hữu rõ ràng; thường để framework quản lý FK collection |
| `Set` có thứ tự không như mong muốn | Dùng collection không có semantics thứ tự | Dùng `List` với `keyColumn` nếu cần thứ tự |
| Collection lồng nhau nối sai root | Dùng ID của root cấp cao thay vì ID của owner trực tiếp | Đặt `idColumn` theo entity sở hữu property collection đó |
| Schema migration chạy được nhưng save lỗi | Annotation và DDL đã lệch nhau | Đồng bộ tên, kiểu, nullability, FK và constraint |

Khi gặp lỗi, hãy kiểm tra theo thứ tự: property collection trong root → `@MappedCollection` → tên bảng child → cột FK/key trong DDL → kiểu ID → dữ liệu/constraint. Log SQL ở môi trường phát triển cũng giúp xác định cột nào Spring Data đang dùng.

## 12. Quan sát SQL và kiểm thử mapping

Có thể bật log JDBC trong môi trường development/test:

```yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
```

Sau khi lưu đơn hàng có hai dòng, truy vấn kiểm tra:

```sql
SELECT id, order_id, line_no, product_id, quantity
FROM order_line
WHERE order_id = :orderId
ORDER BY line_no;
```

Kết quả cần chứng minh:

- Tất cả hàng child có `order_id` bằng ID của aggregate root.
- Các giá trị `line_no` cho phép khôi phục thứ tự list.
- `id` của child là khóa riêng, không bị nhầm với `order_id` hay `line_no`.
- Dữ liệu được đọc lại qua repository giữ đúng phần tử và thứ tự dự kiến.

Một integration test nên lưu root, đọc lại root và xác nhận list/map được khôi phục. Nếu dùng `@DataJdbcTest`, đảm bảo schema test có đầy đủ cột `idColumn`, `keyColumn`, khóa ngoại và constraint tương ứng. Khi production dùng PostgreSQL/MySQL/Oracle, nên chạy test bằng cùng engine qua Testcontainers; H2 không luôn phản ánh khác biệt SQL, identifier và constraint của database thật.

## 13. Chọn `idColumn` và `keyColumn` theo từng trường hợp

| Nhu cầu domain | Khai báo gợi ý | Cấu trúc bảng child |
|---|---|---|
| Root sở hữu danh sách dòng có thứ tự | `@MappedCollection(idColumn = "order_id", keyColumn = "line_no")` | `order_id` + `line_no` + các cột của line |
| Root sở hữu map theo tên thuộc tính | `@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")` | `order_id` + `attribute_name` + các cột value |
| Root sở hữu tập phần tử không có thứ tự | `@MappedCollection(idColumn = "order_id")` | `order_id` + các cột của phần tử |
| Child sở hữu một list cấp sâu hơn | `@MappedCollection(idColumn = "order_line_id", keyColumn = "note_no")` | `order_line_id` + `note_no` + nội dung note |
| Tham chiếu một aggregate root độc lập | Dùng ID/`AggregateReference`, không dùng `@MappedCollection` | Cột ID tham chiếu root kia; vòng đời độc lập |

Khi thiết kế schema, có thể dùng một quy ước đặt tên nhất quán: `<owner>_id` cho `idColumn`, `<child>_position` hoặc tên nghiệp vụ cho `keyColumn`. Quy ước giúp người đọc SQL hiểu quan hệ ngay cả khi không mở Java class.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping collection, entity và quan hệ aggregate.
- [Spring Data Relational — `MappedCollection` API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/MappedCollection.html): ý nghĩa `idColumn` và `keyColumn`.
- [Spring Data JDBC — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cách Spring Data JDBC lưu aggregate và các entity được sở hữu.
- [Spring Data Relational — `NamingStrategy` API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/NamingStrategy.html): quy tắc suy ra tên bảng/cột.

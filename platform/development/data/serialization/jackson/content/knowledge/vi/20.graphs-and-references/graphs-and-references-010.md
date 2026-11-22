# Tránh để cấu trúc lưu trữ nội bộ quyết định toàn bộ JSON công khai

Một hệ thống Java thường lưu dữ liệu dưới dạng một đồ thị đối tượng có nhiều quan hệ. Ví dụ, `Order` tham chiếu tới `Customer`, chứa nhiều `OrderLine`; mỗi `OrderLine` lại tham chiếu tới `Product`, còn `Product` có thể tham chiếu ngược tới các đơn hàng hoặc danh mục. Đồ thị này phản ánh cách ứng dụng quản lý dữ liệu và quan hệ trong bộ nhớ hoặc cơ sở dữ liệu.

JSON công khai phục vụ một mục đích khác: cung cấp đúng thông tin mà một client hoặc hệ thống tích hợp cần để thực hiện một use case. Nếu trả trực tiếp entity hoặc serialize toàn bộ object graph bằng Jackson, cấu trúc lưu trữ nội bộ có thể vô tình trở thành hợp đồng API. Kết quả thường là JSON quá sâu, lặp dữ liệu, vòng tham chiếu, tải quan hệ lazy ngoài ý muốn, lộ field nội bộ và thay đổi API mỗi khi schema persistence thay đổi.

Nguyên tắc thiết kế quan trọng là **xác định ranh giới của JSON theo nhu cầu sử dụng, rồi ánh xạ từ đồ thị domain/persistence sang một cấu trúc đầu ra có chủ đích**. Jackson có các annotation để xử lý quan hệ hai chiều và object identity, nhưng chúng là công cụ định dạng/ánh xạ. Chúng không thay thế việc thiết kế hợp đồng công khai độc lập với mô hình lưu trữ.

## 1. Object graph trong Java không giống một JSON document

Một object graph có thể chứa tham chiếu lặp lại và chu trình. Ví dụ:

```text
Customer
   ^
   | customer
   |
Order ---------> OrderLine ---------> Product
   ^                 |                    |
   |                 | order              | category
   +-----------------+                    v
                                      Category
```

Trong mô hình trên:

- `Order` tham chiếu tới `Customer`.
- `Order` chứa nhiều `OrderLine`.
- Mỗi `OrderLine` tham chiếu ngược về `Order`.
- Mỗi dòng đơn hàng tham chiếu tới `Product`.
- `Product` có thể tham chiếu tới `Category`, còn category có thể giữ danh sách product.

JSON biểu diễn dữ liệu dạng cây: một object chứa property, property có thể chứa object hoặc array, và các node cuối cùng là giá trị scalar/null. JSON không có cú pháp tham chiếu bộ nhớ chung để biểu diễn trực tiếp một chu trình object như `Order -> OrderLine -> Order`.

Nếu serializer đi theo mọi getter mà không có chính sách tham chiếu, nó có thể lặp vô hạn qua quan hệ hai chiều hoặc phát sinh lỗi về độ sâu lồng nhau. Ngay cả khi không có chu trình, việc mở rộng mọi quan hệ có thể tạo một document khổng lồ, lặp lại cùng một customer/product nhiều lần.

## 2. Ví dụ entity có quan hệ hai chiều

Một mô hình persistence dùng JPA có thể khai báo quan hệ như sau:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
public class OrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;
    private String publicStatus;
    private BigDecimal total;
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLineEntity> lines = new ArrayList<>();

    // Getter/setter và helper methods.
}

@Entity
public class OrderLineEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private OrderEntity order;

    @ManyToOne(fetch = FetchType.LAZY)
    private ProductEntity product;

    private int quantity;
    private BigDecimal unitPrice;

    // Getter/setter.
}
```

Quan hệ `OrderEntity.lines` và `OrderLineEntity.order` là hai phía của cùng một quan hệ. Khi Java object được nối đầy đủ, mỗi line giữ tham chiếu tới order chứa nó.

Nếu trả `OrderEntity` trực tiếp từ controller, Jackson có thể duyệt `order.getLines()`, sau đó `line.getOrder()`, rồi lại duyệt `order.getLines()`... Tùy cấu hình và module, kết quả có thể là lỗi vòng lặp/độ sâu, dữ liệu lặp hoặc một biểu diễn không phù hợp với client.

Ngoài ra, entity có thể chứa field phục vụ lưu trữ như ID kỹ thuật, trạng thái nội bộ, audit metadata, thông tin phân quyền, ghi chú vận hành hoặc quan hệ không cần công bố. Getter công khai khiến những field đó có thể trở thành property mà Jackson nhận diện.

## 3. Vì sao serialize trực tiếp entity thường tạo hợp đồng kém ổn định?

Khi JSON được tạo trực tiếp từ entity, thay đổi trong mô hình lưu trữ có thể làm thay đổi response dù use case công khai không đổi.

### 3.1. Vòng tham chiếu và cấu trúc lặp

Quan hệ hai chiều thường tạo chu trình. Một `Order` chứa `OrderLine`, mỗi `OrderLine` lại tham chiếu về `Order`. JSON không thể biểu diễn chu trình đó như một đồ thị tham chiếu bộ nhớ thông thường.

### 3.2. Mở rộng quan hệ ngoài nhu cầu

Một response chỉ cần tên khách hàng và tổng tiền có thể kéo theo địa chỉ, danh sách đơn hàng cũ, lịch sử thanh toán, danh mục sản phẩm và nhiều quan hệ khác nếu serializer đi theo toàn bộ getter.

### 3.3. Lặp dữ liệu

Nếu nhiều order cùng tham chiếu một customer, serialize từng entity có thể lặp lại toàn bộ customer ở nhiều vị trí. Document lớn hơn và client phải tự suy luận rằng các bản sao đó cùng đại diện một thực thể.

### 3.4. Lazy loading và truy vấn ngoài dự kiến

Các quan hệ JPA thường dùng `FetchType.LAZY`. Khi serializer gọi getter của một quan hệ chưa được tải, ORM có thể chạy thêm truy vấn. Điều này có thể gây N+1 query, độ trễ khó dự đoán hoặc `LazyInitializationException` nếu persistence context đã đóng. Kết quả còn phụ thuộc trạng thái session, cách fetch, proxy và module Jackson/Hibernate được đăng ký.

### 3.5. Lộ dữ liệu nội bộ

Entity có thể có getter cho password hash, internal note, moderation status, tenant ID hoặc các thuộc tính chỉ dành cho service. Một thay đổi entity vô tình có thể mở rộng JSON công khai nếu endpoint serialize trực tiếp object đó.

### 3.6. API phụ thuộc vào database schema

Đổi tên cột, tách bảng hoặc thay quan hệ entity không nên buộc client API thay đổi. Nếu JSON phản chiếu trực tiếp persistence model, việc tái cấu trúc database có thể trở thành breaking change ở tầng công khai.

## 4. Thiết kế response theo use case thay vì theo toàn bộ đồ thị lưu trữ

Giả sử màn hình chi tiết đơn hàng chỉ cần:

- Mã đơn hàng và trạng thái công khai.
- Tên khách hàng.
- Danh sách sản phẩm, số lượng và đơn giá tại thời điểm mua.
- Tổng tiền và thời điểm tạo.

Client không cần toàn bộ `CustomerEntity`, `ProductEntity` hay tham chiếu ngược về `OrderEntity`. Hãy tạo DTO phản ánh đúng nhu cầu:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderResponse(
        String orderNumber,
        String status,
        String customerName,
        List<OrderLineResponse> lines,
        BigDecimal total,
        Instant createdAt
) {
}

public record OrderLineResponse(
        String productCode,
        String productName,
        int quantity,
        BigDecimal unitPrice
) {
}
```

JSON công khai chỉ chứa dữ liệu đã chọn:

```json
{
  "orderNumber": "ORD-2026-0042",
  "status": "CONFIRMED",
  "customerName": "An Nguyen",
  "lines": [
    {
      "productCode": "KB-01",
      "productName": "Mechanical Keyboard",
      "quantity": 1,
      "unitPrice": 1250000.00
    },
    {
      "productCode": "MS-03",
      "productName": "Wireless Mouse",
      "quantity": 2,
      "unitPrice": 350000.00
    }
  ],
  "total": 1950000.00,
  "createdAt": "2026-11-12T09:00:00Z"
}
```

DTO không có tham chiếu `line.order`, không có toàn bộ customer, không có quan hệ product ngược và không có field nội bộ. Cấu trúc JSON được quyết định bởi use case chi tiết đơn hàng.

### 4.1. Ánh xạ entity sang DTO một cách tường minh

```java
import java.util.List;

public final class OrderResponseMapper {
    private OrderResponseMapper() {
    }

    public static OrderResponse toResponse(OrderEntity order) {
        List<OrderLineResponse> lines = order.getLines().stream()
                .map(line -> new OrderLineResponse(
                        line.getProduct().getProductCode(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPrice()
                ))
                .toList();

        return new OrderResponse(
                order.getOrderNumber(),
                order.getPublicStatus(),
                order.getCustomer().getDisplayName(),
                lines,
                order.getTotal(),
                order.getCreatedAt()
        );
    }
}
```

Mapping tường minh cho thấy chính xác quan hệ nào được đọc và field nào được đưa ra. Trong ví dụ, `getLines()`, `getProduct()` và `getCustomer()` có thể truy cập quan hệ lazy. Vì vậy, cần bảo đảm dữ liệu cần thiết đã được tải bằng query/fetch plan phù hợp trước khi mapper chạy, thường trong phạm vi transaction/service. Không nên để Jackson tự kích hoạt việc tải cả đồ thị khi serialize response.

### 4.2. DTO có thể phẳng hơn hoặc lồng nhau hơn entity

Không cần giữ nguyên cấu trúc quan hệ JPA trong DTO. Một màn hình có thể cần `customerName` phẳng; màn hình khác có thể cần object `customer` gồm `displayName` và `loyaltyTier`; một export có thể chỉ cần `customerCode`.

Các hình dạng sau đều có thể hợp lý cho những use case khác nhau:

```json
{
  "orderNumber": "ORD-2026-0042",
  "customerName": "An Nguyen"
}
```

```json
{
  "orderNumber": "ORD-2026-0042",
  "customer": {
    "displayName": "An Nguyen",
    "loyaltyTier": "GOLD"
  }
}
```

```json
{
  "orderNumber": "ORD-2026-0042",
  "customerId": "cus-8a91"
}
```

Chọn cấu trúc dựa trên cách consumer dùng dữ liệu, mức độ ổn định của hợp đồng và lượng thông tin cần truyền. Không để quan hệ entity tự quyết định nested JSON.

## 5. Chọn giữa embed object, tham chiếu ID và link tài nguyên

Khi một object có quan hệ tới object khác, JSON công khai có thể biểu diễn theo nhiều cách.

### 5.1. Embed một phần dữ liệu liên quan

Phù hợp khi client luôn cần một phần nhỏ thông tin và dữ liệu đó có ý nghĩa trong ngữ cảnh hiện tại:

```json
{
  "orderNumber": "ORD-2026-0042",
  "customer": {
    "displayName": "An Nguyen"
  }
}
```

Chỉ embed các field cần thiết. Không đưa toàn bộ customer graph vào order response.

### 5.2. Chỉ công bố ID hoặc business key

Phù hợp khi client đã có thể truy vấn tài nguyên riêng hoặc không cần nội dung liên quan ngay:

```json
{
  "orderNumber": "ORD-2026-0042",
  "customerId": "cus-8a91"
}
```

ID công khai nên được chọn có chủ đích. Không nhất thiết phải lộ primary key số nguyên của database nếu API có mã định danh công khai/opaque ID riêng. Nếu công bố ID, hãy định nghĩa tính ổn định và quyền truy cập khi client dùng ID đó để gọi endpoint khác.

### 5.3. Công bố link hoặc URI

Một số API dùng link để chỉ tài nguyên liên quan:

```json
{
  "orderNumber": "ORD-2026-0042",
  "customer": {
    "href": "/api/customers/cus-8a91"
  }
}
```

Link giúp tách representation khỏi cấu trúc nội bộ, nhưng phải ổn định và có chính sách authorization phù hợp. Không đưa URL nội bộ, tên host riêng hoặc đường dẫn database vào response.

### 5.4. Tránh embed vô hạn

Nếu order embed customer, customer không cần embed lại tất cả orders của mình. Nếu product xuất hiện trong line, product không cần embed danh sách mọi order đã mua nó. Xác định chiều dữ liệu và giới hạn độ sâu theo use case.

## 6. DTO giúp tránh chu trình, nhưng không phải mọi DTO đều tự động an toàn

DTO cũng có thể tạo vòng tham chiếu nếu thiết kế hai chiều:

```java
class ParentResponse {
    List<ChildResponse> children;
}

class ChildResponse {
    ParentResponse parent;
}
```

Nếu không có lý do rõ ràng, hãy tránh đưa tham chiếu ngược vào response. Child thường chỉ cần `parentId`, `parentCode` hoặc không cần thông tin parent vì parent đã là ngữ cảnh của array.

```java
public record ParentResponse(
        String id,
        List<ChildResponse> children
) {
}

public record ChildResponse(
        String id,
        String name
) {
}
```

Trong JSON, parent chứa children; child không lặp lại toàn bộ parent. Đây là cấu trúc cây dễ hiểu và không có chu trình.

## 7. Jackson có công cụ xử lý quan hệ hai chiều

Khi một hệ thống có lý do chính đáng để serialize entity hoặc một graph đã được giới hạn, Jackson cung cấp một số annotation để kiểm soát tham chiếu. Các annotation này hữu ích cho những trường hợp cụ thể, nhưng cần hiểu chính xác JSON mà chúng tạo ra.

### 7.1. `@JsonManagedReference` và `@JsonBackReference`

Hai annotation này thường dùng cho quan hệ parent-child hai chiều. Phía parent được đánh dấu `@JsonManagedReference`; phía child trỏ ngược lại được đánh dấu `@JsonBackReference`.

```java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

public class Parent {
    private String id;

    @JsonManagedReference
    private List<Child> children = new ArrayList<>();

    // Getter/setter.
}

public class Child {
    private String id;

    @JsonBackReference
    private Parent parent;

    // Getter/setter.
}
```

Khi serialize parent, Jackson ghi `children` nhưng không ghi property `parent` ở mỗi child. JSON có dạng cây:

```json
{
  "id": "parent-1",
  "children": [
    {"id": "child-1"},
    {"id": "child-2"}
  ]
}
```

Trong quá trình deserialization, Jackson có thể thiết lập tham chiếu ngược tương ứng cho child khi đọc thông qua managed reference. Cơ chế này được thiết kế cho cặp quan hệ có chiều rõ ràng; back reference thường là một property đơn ở phía child, không phải collection/map/array.

Nếu một lớp có nhiều quan hệ parent-child, hãy đặt tên reference riêng bằng thuộc tính `value`, ví dụ `@JsonManagedReference("order-lines")` và `@JsonBackReference("order-lines")`, để Jackson ghép đúng cặp.

**Giới hạn:** cơ chế này phù hợp với quan hệ hai chiều đơn giản. Nó không phải giải pháp tổng quát cho mọi object graph có nhiều đường tham chiếu, nhiều parent hoặc yêu cầu chia sẻ cùng một object ở nhiều nhánh. Nó cũng không quyết định field nào được phép công khai ngoài việc bỏ chiều back reference.

### 7.2. `@JsonIdentityInfo`

Khi cần biểu diễn object identity và các tham chiếu lặp lại, có thể dùng `@JsonIdentityInfo`. Jackson ghi một object đầy đủ ở lần xuất hiện đầu tiên và dùng ID cho những lần tham chiếu sau.

```java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class GraphNode {
    private String id;
    private String name;
    private GraphNode parent;
    private List<GraphNode> children = new ArrayList<>();

    // Getter/setter.
}
```

Một biểu diễn có thể chứa object đầy đủ ở lần đầu và ID ở các lần tham chiếu tiếp theo:

```json
{
  "id": "node-1",
  "name": "Root",
  "children": [
    {
      "id": "node-2",
      "name": "Child",
      "parent": "node-1",
      "children": []
    }
  ]
}
```

Hình thức cụ thể phụ thuộc hướng duyệt và thứ tự serializer gặp object. Khi object đã được định danh, các tham chiếu tiếp theo có thể được ghi bằng giá trị ID thay vì lặp lại object.

`@JsonIdentityInfo` có thể giúp round-trip graph có chia sẻ tham chiếu hoặc chu trình, nhưng JSON lúc này chứa semantics object identity riêng của Jackson. Consumer không biết Jackson có thể không hiểu tại sao một property vốn là object lại đôi khi là ID scalar. Vì vậy, chỉ dùng nếu hợp đồng JSON công khai chấp nhận rõ quy ước tham chiếu bằng ID.

### 7.3. `@JsonIdentityReference(alwaysAsId = true)`

Nếu một property tham chiếu luôn nên được xuất thành ID, có thể kết hợp `@JsonIdentityReference(alwaysAsId = true)` với cơ chế identity đã cấu hình:

```java
@JsonIdentityReference(alwaysAsId = true)
private Customer customer;
```

Khi đó, property có thể được ghi dưới dạng ID thay vì embed customer object. Cần bảo đảm kiểu được tham chiếu có identity metadata phù hợp và consumer hiểu ID đó. Không dùng annotation này như một thay thế cho việc chọn public identifier và thiết kế endpoint tài nguyên.

### 7.4. `@JsonIgnore`

Nếu một chiều tham chiếu không cần xuất ra JSON, có thể đánh dấu:

```java
@JsonIgnore
private OrderEntity order;
```

Điều này loại property khỏi ánh xạ JSON theo quy tắc annotation. Cách làm đơn giản cho một số model, nhưng có thể ảnh hưởng cả chiều serialization/deserialization tùy cách áp dụng. Nếu client cần parent ID, hãy tạo field DTO rõ ràng thay vì bỏ quan hệ rồi hy vọng client suy ra được.

## 8. So sánh các annotation tham chiếu

| Cơ chế | Cách biểu diễn | Phù hợp khi | Hạn chế chính |
|---|---|---|---|
| DTO riêng | Chỉ đưa field được chọn vào cây JSON | Hầu hết API công khai | Cần viết mapping. |
| `@JsonManagedReference` / `@JsonBackReference` | Ghi phía forward, bỏ chiều back | Quan hệ parent-child hai chiều đơn giản | Không xử lý mọi graph tùy ý. |
| `@JsonIdentityInfo` | Object đầy đủ lần đầu, ID ở tham chiếu sau | Cần giữ object identity trong graph | Consumer phải hiểu reference semantics. |
| `@JsonIdentityReference(alwaysAsId = true)` | Luôn ghi reference dưới dạng ID | Property liên quan nên chỉ là ID | Cần identity metadata và ID ổn định. |
| `@JsonIgnore` | Không ghi property bị bỏ qua | Quan hệ không thuộc JSON contract | Có thể làm mất dữ liệu ở chiều đọc hoặc tạo hợp đồng thiếu field. |
| `@JsonIgnoreProperties` | Bỏ qua một nhóm property | Kiểu có một số property kỹ thuật cần loại | Không định nghĩa cấu trúc response theo use case. |

Đối với API public, DTO riêng thường tạo ranh giới rõ nhất. Annotation tham chiếu phù hợp khi một kiểu Java thực sự cần được tuần tự hóa theo graph và quy ước JSON identity đã được chấp nhận.

## 9. Lazy loading: đừng để serializer quyết định query database

Giả sử controller trả entity:

```java
@GetMapping("/{id}")
public OrderEntity getOrder(@PathVariable Long id) {
    return orderRepository.findById(id).orElseThrow();
}
```

Jackson có thể gọi getter cho `customer`, `lines`, `product` và các quan hệ khác trong lúc ghi response. Nếu quan hệ lazy chưa được tải, ORM có thể chạy truy vấn mới. Khi lặp qua nhiều order, mỗi lần truy cập một quan hệ có thể tạo thêm truy vấn, dẫn đến N+1.

Tác động phụ thuộc transaction/session, query plan, Hibernate proxy, module Jackson Hibernate và cách framework serialize response. Một số cấu hình có thể bỏ qua lazy property; cấu hình khác có thể cố tải nó hoặc phát sinh lỗi khi session đã đóng. Không nên để chính sách fetch database phụ thuộc ngẫu nhiên vào getter mà Jackson gọi.

### 9.1. Tải đúng dữ liệu cần cho DTO

Service/query nên lấy đúng các field cần cho response. Có thể dùng:

- JPQL projection hoặc constructor expression để lấy trực tiếp DTO.
- Spring Data projection interface/record phù hợp với truy vấn.
- `join fetch` hoặc `EntityGraph` để tải một tập quan hệ đã xác định.
- Query riêng cho summary thay vì tải toàn bộ entity graph.

Ví dụ JPQL projection:

```java
public record OrderSummaryRow(
        String orderNumber,
        String customerName,
        BigDecimal total
) {
}
```

```java
@Query("""
       select new com.example.api.OrderSummaryRow(
           o.orderNumber,
           c.displayName,
           o.total
       )
       from OrderEntity o
       join o.customer c
       where o.id = :id
       """)
Optional<OrderSummaryRow> findSummaryById(@Param("id") Long id);
```

Projection chỉ lấy dữ liệu cần thiết cho summary. Jackson serialize DTO/record mà không cần đi qua toàn bộ entity graph.

### 9.2. Map trong ranh giới service phù hợp

Nếu mapper DTO đọc quan hệ entity, hãy thực hiện mapping khi dữ liệu cần thiết còn sẵn trong persistence context hoặc dùng projection không cần lazy traversal. Đừng chuyển entity ra khỏi transaction rồi để Jackson gọi getter sau đó.

Một nguyên tắc hữu ích là: **service quyết định dữ liệu cần truy xuất; mapper quyết định field nào vào DTO; Jackson chỉ serialize DTO đã hoàn chỉnh**.

## 10. Không dùng Hibernate proxy như một phần của public JSON contract

Proxy ORM là chi tiết triển khai phục vụ lazy loading. Các property kỹ thuật như `hibernateLazyInitializer` hoặc `handler` không phải dữ liệu công khai. Một số dự án dùng:

```java
@JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
```

để tránh một số property kỹ thuật của proxy xuất hiện. Tuy nhiên, annotation này không giải quyết:

- Quan hệ hai chiều và chu trình object.
- N+1 query hoặc việc truy cập lazy ngoài session.
- Field nhạy cảm trong entity.
- JSON quá sâu hoặc lặp dữ liệu.
- Sự phụ thuộc giữa public API và persistence schema.

Jackson Hibernate module có thể cung cấp serializer/deserializer chuyên biệt cho proxy và collection lazy, nhưng đó là lựa chọn tích hợp ORM. Nó không thay thế DTO hoặc query projection cho API công khai.

## 11. Đồ thị lưu trữ và đồ thị JSON có thể có hình dạng khác nhau

Một đồ thị entity được tối ưu cho thao tác nghiệp vụ và lưu trữ có thể có nhiều quan hệ hai chiều. JSON cho từng use case có thể chọn một lát cắt khác nhau của đồ thị.

Ví dụ cùng một `OrderEntity`:

### Màn hình danh sách đơn hàng

```json
{
  "orderNumber": "ORD-2026-0042",
  "customerName": "An Nguyen",
  "lineCount": 2,
  "total": 1950000.00
}
```

### Màn hình chi tiết đơn hàng

```json
{
  "orderNumber": "ORD-2026-0042",
  "customer": {
    "displayName": "An Nguyen"
  },
  "lines": [
    {
      "productCode": "KB-01",
      "productName": "Mechanical Keyboard",
      "quantity": 1
    }
  ],
  "total": 1950000.00
}
```

### Message event

```json
{
  "eventId": "evt-42",
  "eventType": "ORDER_CONFIRMED",
  "orderNumber": "ORD-2026-0042",
  "customerId": "cus-8a91",
  "occurredAt": "2026-11-12T09:00:00Z"
}
```

### Export báo cáo

```json
{
  "order_number": "ORD-2026-0042",
  "customer_code": "CUS-00891",
  "line_count": 2,
  "total_amount": 1950000.00,
  "created_date": "2026-11-12"
}
```

Mỗi representation phục vụ một consumer. Không cần tạo một JSON graph duy nhất rồi dùng annotation để cắt bớt theo từng nơi; DTO riêng thường rõ ràng hơn và giúp hợp đồng không phụ thuộc cấu trúc persistence.

## 12. Chọn ranh giới aggregate và giới hạn độ sâu

Khi thiết kế response, hãy quyết định object nào là root của use case và những dữ liệu liên quan nào cần được embed.

Ví dụ, `OrderResponse` có thể embed `OrderLineResponse`, nhưng mỗi line chỉ embed một `ProductSummary`, không embed toàn bộ product cùng danh sách category, inventory, suppliers và các order khác.

```java
public record ProductSummary(
        String productCode,
        String name
) {
}

public record OrderLineResponse(
        ProductSummary product,
        int quantity,
        BigDecimal unitPrice
) {
}
```

Hãy giữ chiều biểu diễn có chủ đích:

```text
OrderResponse
  ├── CustomerSummary
  └── List<OrderLineResponse>
         └── ProductSummary
```

Không cần có đường tham chiếu ngược từ `ProductSummary` về `OrderResponse`. Nếu client cần dữ liệu product đầy đủ, cung cấp endpoint riêng hoặc một use case khác với DTO riêng.

## 13. Public identifier và database identifier

Entity thường có primary key phục vụ join và quản lý nội bộ. Public JSON không nhất thiết phải công bố trực tiếp primary key đó.

Có thể dùng:

- Business key như `orderNumber` nếu nó ổn định và không tiết lộ thông tin không mong muốn.
- Opaque ID được sinh riêng cho API.
- URI/resource link nếu hợp đồng định hướng tài nguyên.

Nếu dùng `@JsonIdentityInfo(generator = PropertyGenerator.class, property = "id")`, hãy cân nhắc rằng ID đó trở thành một phần của JSON reference semantics. Chọn ID duy nhất trong phạm vi identity resolver và có ý nghĩa ổn định đối với consumer. Không dùng ID tuần tự dễ đoán như cơ chế kiểm soát quyền; authorization phải được kiểm tra độc lập mỗi lần truy cập tài nguyên.

## 14. Tách request DTO khỏi entity khi ghi dữ liệu

Vấn đề object graph không chỉ xuất hiện ở chiều response. Nếu nhận JSON trực tiếp thành entity, client có thể gửi các property liên quan hoặc field nội bộ mà ứng dụng không muốn cho phép cập nhật.

Ví dụ, không nên nhận trực tiếp một `OrderEntity` có `customer`, `lines`, `status`, `createdBy` và các quan hệ nội bộ rồi merge toàn bộ object graph từ JSON. Hãy dùng request DTO chỉ chứa các lựa chọn mà client được phép cung cấp:

```java
public record CreateOrderRequest(
        String customerId,
        List<CreateOrderLineRequest> lines
) {
}

public record CreateOrderLineRequest(
        String productCode,
        int quantity
) {
}
```

Service xác thực customer/product, tính giá, tạo quan hệ entity và thiết lập trạng thái theo quy tắc nghiệp vụ. Client không được quyết định `createdBy`, `total`, trạng thái thanh toán hoặc các quan hệ persistence chỉ bằng cách gửi thêm property JSON.

## 15. Vai trò của các annotation khác

Một số annotation có thể giúp điều chỉnh JSON ở cấp property, nhưng nên dùng đúng mục đích:

| Annotation | Tác dụng | Có thay DTO riêng không? |
|---|---|---|
| `@JsonIgnore` | Bỏ qua property cụ thể | Không; chỉ loại một property. |
| `@JsonIgnoreProperties` | Bỏ qua danh sách property | Không; không xác định toàn bộ public projection. |
| `@JsonManagedReference` / `@JsonBackReference` | Điều khiển cặp tham chiếu parent-child | Không; chỉ xử lý một dạng quan hệ hai chiều. |
| `@JsonIdentityInfo` | Dùng object ID cho tham chiếu lặp | Không; làm thay đổi representation theo identity semantics. |
| `@JsonView` | Chọn nhóm property theo view | Không; view vẫn dựa trên một lớp có nhiều field. |
| `@JsonFilter` | Lọc property động | Không; filter cần được kiểm soát và không tự xác định authorization. |
| `@JsonProperty` | Đổi tên hoặc định nghĩa property | Không; chỉ điều chỉnh property. |

Các annotation rất hữu ích cho một kiểu JSON có chủ đích. Chúng trở nên khó kiểm soát nếu được dùng để biến một entity lớn thành nhiều API khác nhau bằng cách bật/tắt field tùy request.

## 16. Kiểm thử hợp đồng JSON và giới hạn graph

DTO giúp kiểm soát đầu ra, nhưng cần kiểm thử để bảo đảm thay đổi entity không làm lộ field hoặc mở rộng response ngoài dự kiến.

Ví dụ kiểm thử response:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class OrderResponseTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    @Test
    void responseContainsOnlyTheOrderView() throws Exception {
        OrderResponse response = new OrderResponse(
                "ORD-2026-0042",
                "CONFIRMED",
                "An Nguyen",
                List.of(new OrderLineResponse(
                        "KB-01",
                        "Mechanical Keyboard",
                        1,
                        new BigDecimal("1250000.00")
                )),
                new BigDecimal("1250000.00"),
                Instant.parse("2026-11-12T09:00:00Z")
        );

        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

        assertEquals("ORD-2026-0042", json.path("orderNumber").asText());
        assertEquals("An Nguyen", json.path("customerName").asText());
        assertTrue(json.path("lines").isArray());
        assertFalse(json.has("customerEntity"));
        assertFalse(json.has("passwordHash"));
        assertFalse(json.path("lines").get(0).has("order"));
    }
}
```

Với endpoint lấy danh sách, nên kiểm thử cả kích thước response và số truy vấn trong tình huống có nhiều bản ghi. Một test chỉ xác nhận JSON parse được sẽ không phát hiện N+1 query hoặc response vô tình embed hàng nghìn object.

Các kiểm thử hữu ích khác:

- Response không chứa field nội bộ hoặc secret.
- Quan hệ không cần thiết không xuất hiện.
- Một parent có nhiều child không tạo vòng lặp.
- JSON có giới hạn độ sâu và số phần tử theo hợp đồng.
- DTO vẫn giữ cấu trúc ổn định khi entity thêm field hoặc quan hệ mới.
- Query/fetch plan lấy đúng dữ liệu cần và không gây N+1 ngoài dự kiến.
- Authorization quyết định đúng DTO/field được phép xuất.

## 17. Quy trình thiết kế JSON từ một object graph

Khi một entity có nhiều quan hệ, có thể thiết kế response theo trình tự:

1. **Xác định use case và consumer:** màn hình danh sách, chi tiết, event, export hay audit?
2. **Chọn root của response:** object nào là trung tâm của tài liệu JSON?
3. **Liệt kê dữ liệu thật sự cần:** mỗi field phục vụ quyết định hoặc thao tác nào?
4. **Chọn cách biểu diễn quan hệ:** embed summary, ID, link hay bỏ qua?
5. **Giới hạn chiều sâu:** tránh tham chiếu ngược và lặp toàn bộ graph.
6. **Tạo DTO allowlist:** chỉ chứa field được phép công bố.
7. **Thiết kế query/fetch plan:** tải đúng dữ liệu để map DTO, tránh lazy loading trong serializer.
8. **Chọn annotation Jackson nếu cần:** chỉ dùng reference/identity annotation khi representation yêu cầu rõ semantics đó.
9. **Kiểm tra bảo mật và hiệu năng:** field nhạy cảm, số query, kích thước payload và authorization.
10. **Kiểm thử hợp đồng:** xác nhận JSON đầu ra độc lập với thay đổi persistence.

## 18. Chọn kỹ thuật theo tình huống

| Tình huống | Cách tiếp cận nên ưu tiên | Lý do |
|---|---|---|
| REST API công khai trả dữ liệu từ entity có nhiều quan hệ | DTO riêng theo use case | Kiểm soát field và hình dạng JSON. |
| Quan hệ parent-child hai chiều đơn giản trong một model cần serialize | `@JsonManagedReference` / `@JsonBackReference` | Loại chiều tham chiếu ngược. |
| Cần giữ identity và tham chiếu lặp trong graph JSON | `@JsonIdentityInfo` | Biểu diễn object đầy đủ và ID tham chiếu. |
| Một quan hệ chỉ cần ID công khai | DTO chứa ID hoặc link; cân nhắc identity reference khi hợp đồng yêu cầu | Không embed toàn bộ object liên quan. |
| Chỉ cần summary hoặc một số cột từ nhiều bảng | Query projection/DTO projection | Tránh tải entity graph không cần thiết. |
| Entity có proxy và quan hệ lazy | Fetch plan rõ ràng, map DTO trong service | Không để Jackson quyết định truy vấn. |
| JSON đầu vào có thể thay đổi entity graph | Request DTO và mapping/validation | Không cho client điều khiển quan hệ persistence tùy ý. |

Đồ thị đối tượng nội bộ được thiết kế để lưu trữ và thực hiện nghiệp vụ; JSON công khai được thiết kế để phục vụ consumer. Hai cấu trúc không cần giống nhau. Hãy tạo DTO theo use case, chọn rõ dữ liệu liên quan nào được embed hoặc chỉ tham chiếu bằng ID/link, và giới hạn chiều sâu để tránh vòng lặp, dữ liệu lặp hoặc response quá lớn. `@JsonManagedReference`, `@JsonBackReference` và `@JsonIdentityInfo` có thể giải quyết một số trường hợp graph cụ thể, nhưng DTO allowlist cùng query/fetch plan rõ ràng thường tạo ranh giới ổn định hơn. Khi Jackson chỉ serialize một representation đã được chuẩn bị có chủ đích, thay đổi entity và database ít có khả năng làm thay đổi hợp đồng JSON hoặc gây truy vấn ngoài ý muốn.

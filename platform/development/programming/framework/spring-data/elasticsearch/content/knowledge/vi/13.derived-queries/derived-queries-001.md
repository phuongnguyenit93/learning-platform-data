# Cấu trúc tên phương thức và phân giải đường dẫn thuộc tính

Spring Data Elasticsearch có thể tạo truy vấn từ tên phương thức repository. Thay vì viết Query DSL cho từng điều kiện đơn giản, ta khai báo một phương thức như `findByStatusAndTotalGreaterThan`; Spring Data phân tích tên, tìm các property tương ứng trong entity và tạo query phù hợp.

Cơ chế này được gọi là *query derivation*. Để dùng đúng, cần hiểu hai việc riêng biệt:

1. **Phân tích cấu trúc tên phương thức:** Spring Data nhận diện phần mở đầu, dấu phân cách `By`, điều kiện, toán tử và thứ tự sắp xếp.
2. **Phân giải đường dẫn thuộc tính:** Spring Data xác định mỗi phần tên đang trỏ tới property trực tiếp hay property lồng bên trong một object khác.

Phân giải sai hoặc tên property mơ hồ có thể khiến ứng dụng tìm nhầm field, tạo query không như mong muốn hoặc không khởi động được repository. Bài học này tập trung vào quy tắc đặt tên, cách parser tìm property, cách xử lý tên lồng nhau và cách chẩn đoán lỗi trong Spring Data Elasticsearch.

## 1. Cơ chế query derivation

Một derived query thường có dạng:

~~~text
findBy<Property><Operator><Value>
~~~

Ví dụ:

~~~java
List<Product> findByCategory(String category);
~~~

Spring Data đọc tên phương thức và nhận ra:

- `find` là phần mở đầu biểu thị thao tác truy vấn.
- `By` đánh dấu bắt đầu phần predicate.
- `Category` là property cần so khớp.
- Tham số `category` cung cấp giá trị cho điều kiện.

Với phương thức có nhiều điều kiện:

~~~java
List<Product> findByCategoryAndPriceLessThan(
    String category,
    Double maxPrice
);
~~~

Parser nhận diện hai điều kiện được nối bằng `And`:

- `Category` so khớp với tham số thứ nhất.
- `PriceLessThan` so sánh giá nhỏ hơn tham số thứ hai.

Spring Data sử dụng metadata entity để tìm property và kiểu dữ liệu. Sau đó, Spring Data Elasticsearch chuyển biểu diễn query sang request phù hợp với Elasticsearch.

Tên phương thức là một ngôn ngữ khai báo có quy tắc. Nó không phải một đoạn Java được thực thi bằng cách phân tích chuỗi tùy ý, cũng không phải tên endpoint hoặc tên field JSON viết trực tiếp.

## 2. Các phần của tên phương thức

Có thể hình dung cấu trúc phổ biến như sau:

~~~text
findDistinctTop10ByStatusAndTotalGreaterThanOrderByCreatedAtDesc
|----subject----|By|----------predicate----------|---ordering---|
~~~

Tên phương thức có ba phần chính:

| Phần | Vai trò |
|---|---|
| Subject | Cho biết loại thao tác hoặc giới hạn kết quả |
| `By` | Phân cách subject và predicate |
| Predicate | Xác định property, toán tử và giá trị cần kiểm tra |
| `OrderBy` | Phần tùy chọn chỉ định thứ tự sắp xếp |

`OrderBy` nằm bên trong phần tên sau predicate, nhưng có thể xem như một phần riêng vì nó mô tả thứ tự kết quả thay vì điều kiện lọc.

### Subject: phần mở đầu

Các từ mở đầu thường gặp trong Spring Data gồm:

- `findBy`
- `readBy`
- `getBy`
- `queryBy`
- `searchBy`
- `streamBy`

Spring Data Elasticsearch hỗ trợ một tập phương thức và kiểu trả về cụ thể theo phiên bản. Vì vậy, hãy xem các từ trên là những dạng mở đầu thường gặp của Spring Data repository và xác nhận dạng được hỗ trợ trong release train đang dùng.

Một số phương thức có thể dùng subject để giới hạn hoặc mô tả kết quả:

~~~java
List<Product> findTop10ByCategory(String category);

Optional<Product> findFirstBySku(String sku);

long countByCategory(String category);

boolean existsBySku(String sku);
~~~

`Top` và `First` có thể giới hạn số kết quả. Con số theo sau cho biết giới hạn, ví dụ `Top10`. `countBy` và `existsBy` thể hiện mục tiêu đếm hoặc kiểm tra sự tồn tại nếu phiên bản repository hỗ trợ phương thức đó.

Không nên nhầm subject với tên property. Trong `findDistinctTop10ByCategory`, `Distinct` và `Top10` là modifier của subject; property bắt đầu sau `By`.

### Predicate: phần điều kiện

Predicate bắt đầu ngay sau `By` và chứa property cùng toán tử:

~~~java
findByStatus(String status)
findByPriceGreaterThan(Double price)
findByCreatedAtBetween(Instant from, Instant to)
findByNameContaining(String text)
~~~

Một predicate có thể gồm nhiều điều kiện:

~~~java
findByStatusAndCategory(String status, String category)
findByStatusOrCategory(String status, String category)
~~~

Thứ tự tham số phải tương ứng với thứ tự các điều kiện trong tên phương thức. Nếu đổi thứ tự property mà không đổi thứ tự tham số, query có thể dùng nhầm giá trị.

### Ordering: phần sắp xếp

Có thể khai báo thứ tự cố định bằng `OrderBy`:

~~~java
List<Product> findByCategoryOrderByPriceAsc(String category);

List<Product> findByCategoryOrderByCreatedAtDesc(
    String category
);
~~~

`Asc` chỉ định tăng dần; `Desc` chỉ định giảm dần. Khi cần sort động theo request, thường nên nhận `Pageable` hoặc `Sort` thay vì tạo nhiều method cho từng thứ tự.

## 3. Toán tử trong predicate

Spring Data nhận diện các keyword toán tử đặt sau property. Một số dạng thường dùng:

| Keyword trong tên | Ý nghĩa dự kiến | Ví dụ |
|---|---|---|
| Không có hậu tố, `Is`, `Equals` | So khớp bằng | `findByStatus` |
| `Not`, `IsNot` | Không bằng | `findByStatusNot` |
| `GreaterThan` | Lớn hơn | `findByPriceGreaterThan` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `findByPriceGreaterThanEqual` |
| `LessThan` | Nhỏ hơn | `findByPriceLessThan` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `findByPriceLessThanEqual` |
| `Between` | Nằm trong khoảng | `findByPriceBetween` |
| `In` | Thuộc một tập giá trị | `findByStatusIn` |
| `NotIn` | Không thuộc tập giá trị | `findByStatusNotIn` |
| `Like` | So khớp theo dạng pattern được hỗ trợ | `findByNameLike` |
| `Containing` | Tìm nội dung chứa chuỗi theo semantics được hỗ trợ | `findByNameContaining` |
| `StartingWith` | Bắt đầu bằng chuỗi | `findByCodeStartingWith` |
| `EndingWith` | Kết thúc bằng chuỗi | `findByCodeEndingWith` |
| `True`, `False` | Kiểm tra boolean | `findByActiveTrue` |
| `IsNull`, `IsNotNull` | Kiểm tra giá trị null | `findByDeletedAtIsNull` |

Đây là các keyword quen thuộc trong hệ sinh thái Spring Data. Không phải mọi keyword đều được hỗ trợ hoặc có semantics giống nhau trong mọi phiên bản Spring Data Elasticsearch. Hãy kiểm tra reference documentation của phiên bản dự án trước khi dùng một keyword ít phổ biến.

Đặc biệt, các từ như `Containing`, `Like`, `StartingWith` và `EndingWith` không nên được hiểu theo SQL một cách máy móc. Elasticsearch có analyzer, token và Query DSL riêng. Kiểu field, analyzer và query được tạo ra sẽ ảnh hưởng đến kết quả.

### Ví dụ với entity sản phẩm

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    private Boolean active;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByPriceGreaterThan(Double price);

    List<Product> findByPriceBetween(
        Double minPrice,
        Double maxPrice
    );

    List<Product> findBySkuIn(Collection<String> skus);

    List<Product> findByActiveTrue();
}
~~~

Mỗi method sử dụng tên property Java: `category`, `price`, `sku` và `active`. Spring Data tra cứu property trong entity rồi dựa vào mapping metadata để biết field Elasticsearch tương ứng có kiểu gì.

## 4. Kết hợp điều kiện bằng And và Or

Một predicate có thể kết hợp nhiều điều kiện bằng `And` hoặc `Or`:

~~~java
List<Product> findByCategoryAndActive(
    String category,
    Boolean active
);

List<Product> findByCategoryOrName(
    String category,
    String name
);
~~~

Có thể đọc lần lượt như:

- `findByCategoryAndActive`: category thỏa điều kiện và active thỏa điều kiện.
- `findByCategoryOrName`: category thỏa điều kiện hoặc name thỏa điều kiện.

Khi trộn `And` và `Or`, cần đặc biệt chú ý cách parser nhóm điều kiện. Spring Data phân tách các nhóm OR; những điều kiện nối bằng AND nằm trong cùng một nhóm. Ví dụ:

~~~java
findByStatusAndCategoryOrFeaturedTrue(
    String status,
    String category
)
~~~

Có thể đọc theo cấu trúc:

~~~text
(status = ?0 AND category = ?1) OR (featured = true)
~~~

Đừng đặt tên method dài với nhiều `And` và `Or` nếu người đọc khó xác định cách nhóm điều kiện. Khi cần nhóm logic nhiều tầng, dùng query builder tường minh sẽ dễ hiểu và ít gây nhầm hơn.

### Không giả định thứ tự And/Or giống cách đọc tự nhiên

Nếu nghiệp vụ yêu cầu:

~~~text
status = ACTIVE AND (category = BOOK OR category = MUSIC)
~~~

thì một tên derived query đơn giản có thể không biểu đạt được nhóm ngoặc theo cách mong muốn. Hãy cân nhắc `In` nếu hai category là một tập giá trị:

~~~java
List<Product> findByStatusAndCategoryIn(
    String status,
    Collection<String> categories
);
~~~

Hoặc dùng `CriteriaQuery`/`NativeQuery` để tạo nhóm boolean đúng cấu trúc.

## 5. Property path là gì?

Property path là đường đi từ entity gốc qua một hoặc nhiều property lồng nhau.

Ví dụ mô hình đơn hàng:

~~~java
public class PurchaseOrder {

    private String orderNumber;
    private Customer customer;
    private Address shippingAddress;
    private Double total;
}

public class Customer {

    private String name;
    private String email;
    private String customerCode;
}

public class Address {

    private String city;
    private String postalCode;
}
~~~

Từ entity `PurchaseOrder` có thể truy cập các property:

- `orderNumber`
- `customer.name`
- `customer.email`
- `shippingAddress.city`
- `shippingAddress.postalCode`
- `total`

Một phương thức repository có thể biểu diễn đường dẫn lồng nhau:

~~~java
List<PurchaseOrder> findByCustomerEmail(String email);

List<PurchaseOrder> findByShippingAddressCity(String city);
~~~

Spring Data phải phân tích chuỗi `CustomerEmail` thành đường dẫn `customer.email` và `ShippingAddressCity` thành `shippingAddress.city`.

Tên property path trong derived query dựa trên mô hình Java và persistent metadata. Nó không đơn giản là chuỗi tên field trong JSON.

## 6. Quy tắc phân giải property path

Khi gặp một chuỗi như `ShippingAddressCity`, Spring Data cần quyết định đó là:

- Một property trực tiếp tên `shippingAddressCity`, hay
- Property `shippingAddress` rồi tới property `city`.

Cơ chế phân giải property path cố gắng tìm property trực tiếp trước. Nếu không tìm được, nó thử tách chuỗi theo ranh giới chữ hoa để tìm đường dẫn lồng nhau.

Có thể mô tả đơn giản như sau:

1. Chuyển phần đầu của tên thành tên property theo quy ước Java, ví dụ `ShippingAddressCity` thành `shippingAddressCity`.
2. Thử tìm property trực tiếp đó trên entity hiện tại.
3. Nếu không có, thử chia chuỗi tại ranh giới camel case, bắt đầu từ vị trí tách gần cuối.
4. Kiểm tra phần đầu có phải property của entity hiện tại không.
5. Nếu tìm thấy, tiếp tục phân giải phần còn lại trên kiểu của property đó.
6. Nếu không tìm được đường đi hợp lệ, Spring Data báo lỗi không có property tương ứng.

Ví dụ:

~~~text
PurchaseOrder
    |
    +-- customer
    |      |
    |      +-- name
    |      +-- email
    |      +-- customerCode
    |
    +-- shippingAddress
    |      |
    |      +-- city
    |      +-- postalCode
    |
    +-- total
~~~

Tên `findByShippingAddressCity` được phân giải thành:

~~~text
shippingAddress.city
~~~

Tên `findByCustomerEmail` được phân giải thành:

~~~text
customer.email
~~~

### Ưu tiên property trực tiếp có thể tạo ra sự mơ hồ

Giả sử entity có cả hai property:

~~~java
public class PurchaseOrder {

    private String customerEmail;
    private Customer customer;
}
~~~

và class Customer có property `email`.

Tên `findByCustomerEmail` có thể được hiểu theo hai cách:

~~~text
customerEmail
customer.email
~~~

Parser ưu tiên thử property trực tiếp trước. Nếu property trực tiếp tồn tại, nó có thể được chọn thay vì đường dẫn lồng nhau.

Nếu muốn chắc chắn truy vấn `customer.email`, hãy dùng dấu gạch dưới để đánh dấu ranh giới:

~~~java
List<PurchaseOrder> findByCustomer_Email(String email);
~~~

Dấu gạch dưới làm rõ đường dẫn:

~~~text
customer.email
~~~

Đây là cách quan trọng để giải quyết các trường hợp có tên property trùng với một đoạn của property path.

## 7. Dùng dấu gạch dưới để chỉ rõ ranh giới

Trong property path của Spring Data, dấu gạch dưới `_` được dùng làm dấu phân tách rõ ràng giữa các phần của đường dẫn.

Ví dụ:

~~~java
findByShippingAddress_City(String city);
findByCustomer_CustomerCode(String code);
findByCustomer_Email(String email);
~~~

Các đường dẫn tương ứng:

| Method fragment | Property path |
|---|---|
| `ShippingAddress_City` | `shippingAddress.city` |
| `Customer_CustomerCode` | `customer.customerCode` |
| `Customer_Email` | `customer.email` |

Nên dùng underscore khi:

- Entity có property trực tiếp với tên dài có thể gây nhầm.
- Một property path có nhiều cấp lồng nhau.
- Tên method cần thể hiện rõ ranh giới giữa object cha và property con.
- Parser có thể phân giải theo nhiều cách.

Ví dụ ba cấp:

~~~java
public class PurchaseOrder {
    private Customer customer;
}

public class Customer {
    private Address primaryAddress;
}

public class Address {
    private String postalCode;
}
~~~

Có thể viết:

~~~java
List<PurchaseOrder> findByCustomer_PrimaryAddress_PostalCode(
    String postalCode
);
~~~

Đường dẫn được chỉ rõ:

~~~text
customer.primaryAddress.postalCode
~~~

Không nên dùng dấu gạch dưới trong tên property Java nếu có thể tránh, vì ký tự này được Spring Data dành cho việc phân tách property path. Nên tuân theo quy ước camelCase thông thường của Java.

## 8. Tên property Java khác tên field trong Elasticsearch

Một entity có thể dùng tên Java dễ đọc trong khi mapping trên Elasticsearch dùng tên khác:

~~~java
@Document(indexName = "orders")
public class PurchaseOrder {

    @Field(name = "order_number", type = FieldType.Keyword)
    private String orderNumber;

    @Field(name = "customer_name", type = FieldType.Text)
    private String customerName;
}
~~~

Trong repository, derived query dùng property Java:

~~~java
List<PurchaseOrder> findByOrderNumber(String number);

List<PurchaseOrder> findByCustomerName(String name);
~~~

Không nên viết:

~~~java
// Không dùng tên field Elasticsearch làm property path Java
findByOrder_number(String number);
findByCustomer_name(String name);
~~~

Spring Data dùng persistent metadata để ánh xạ property Java sang tên field Elasticsearch. `@Field(name = "...")` mô tả tên field trong index; nó không thay đổi tên property mà parser query derivation cần tìm.

Phân biệt hai lớp tên:

| Lớp | Ví dụ |
|---|---|
| Java property | `customerName` |
| Elasticsearch field | `customer_name` |
| Derived query | `findByCustomerName` |
| Query DSL sau mapping | Truy vấn field `customer_name` |

Điều này cũng áp dụng cho multi-field. Nếu property Java `name` có subfield `keyword`, derived query bắt đầu từ property Java. Việc tham chiếu subfield cụ thể trong query có thể cần `@Query`, Criteria hoặc NativeQuery tùy khả năng của phiên bản.

## 9. Property path và kiểu mapping Elasticsearch

Phân giải property path và loại field Elasticsearch là hai vấn đề liên quan nhưng không đồng nhất.

Giả sử entity có:

~~~java
public class PurchaseOrder {

    private Customer customer;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}
~~~

Spring Data phải xác định đường dẫn Java như `customer.email` hoặc `lines.productCode`. Sau đó mapping metadata cho biết field tương ứng được lưu như object, nested hay kiểu field khác.

Một property path hợp lệ không tự đảm bảo query có đúng semantics của nested query. Với dữ liệu khai báo `FieldType.Nested`, Elasticsearch có yêu cầu truy vấn trong nested context để giữ quan hệ giữa các object con. Khả năng derived query tạo đúng nested query phụ thuộc hỗ trợ của Spring Data Elasticsearch ở phiên bản đang dùng và kiểu query được tạo.

Khi cần truy vấn nested phức tạp hoặc cần kiểm soát rõ nested path, nên dùng `NativeQuery` với nested Query DSL qua `ElasticsearchOperations`. Kiểm tra request thực tế hoặc integration test để xác nhận query được đặt đúng nested context.

### Ví dụ nested object

~~~java
public class OrderLine {

    private String productCode;
    private Integer quantity;
}

@Document(indexName = "orders")
public class PurchaseOrder {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}
~~~

Một tên method như:

~~~java
List<PurchaseOrder> findByLines_ProductCode(String code);
~~~

cho biết property path Java là `lines.productCode`. Nhưng nếu cần bảo đảm hai điều kiện cùng khớp trên một nested object cụ thể, hãy dùng nested query rõ ràng thay vì dựa vào việc parser tự suy ra ý nghĩa nghiệp vụ.

## 10. Quy tắc với Id và các phương thức repository kế thừa

Spring Data repository có một số phương thức được định nghĩa sẵn, ví dụ `findById`. Đây là phương thức dành cho identifier của entity, không đơn giản chỉ là derived query trên property có tên `id`.

Ví dụ:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String customerKey;

    private String id;
}
~~~

Với class như trên:

- `findById(id)` là phương thức kế thừa dùng identifier được đánh dấu `@Id`.
- Nếu muốn tìm theo property thông thường tên `id`, cần đặt một derived method có tên khác biệt rõ ràng, ví dụ `findCustomerById`, và xác nhận cách phân tích trong phiên bản dự án.
- `findByCustomerKey` là query theo property Java `customerKey`; cần phân biệt với phương thức kế thừa tìm theo ID.

Trong thực tế, nên đặt tên property được đánh dấu `@Id` rõ nghĩa như `customerId` hoặc `documentId` để tránh nhầm với property nghiệp vụ khác cũng tên `id`.

## 11. Phân biệt tên method hợp lệ với query được hỗ trợ

Một tên phương thức có thể đúng cú pháp parser nhưng query tương ứng chưa chắc được Spring Data Elasticsearch hỗ trợ theo cách bạn kỳ vọng.

Có ba tầng cần xem xét:

1. **Parser:** Spring Data có nhận diện được subject, predicate, operator và property path không?
2. **Query creator:** Spring Data Elasticsearch có chuyển phần predicate đó thành query tương ứng không?
3. **Mapping và Elasticsearch:** field thực tế có kiểu phù hợp với query và mapping trên cluster không?

Ví dụ `findByNameContaining` có thể được parser nhận diện, nhưng semantics tìm chuỗi phụ thuộc loại field và cách Spring Data Elasticsearch triển khai query. Nếu `name` là `text`, analyzer có thể tách nội dung thành token. Nếu `name` là `keyword`, chuỗi được giữ nguyên như một term. Không nên suy luận rằng `Containing` luôn tương đương SQL `LIKE '%value%'`.

Tương tự, một method có property path hợp lệ nhưng field không tồn tại trong mapping thực tế vẫn có thể cho kết quả rỗng hoặc lỗi khi chạy query.

Vì vậy, khi một derived query cho kết quả bất ngờ, hãy kiểm tra lần lượt parser, query được tạo, mapping và dữ liệu đã index.

## 12. Quy tắc đặt tên dễ đọc và dễ bảo trì

Một số quy tắc giúp repository method rõ ràng hơn:

**Dùng tên property Java nhất quán.** Tên method nên phản ánh property trong entity, không dùng tên snake_case của Elasticsearch.

**Giữ method ngắn.** Nếu tên method có nhiều điều kiện, nhiều cấp nested path hoặc nhiều operator, cân nhắc query builder.

**Dùng underscore ở nơi cần làm rõ đường dẫn.** Đừng bắt người đọc phải đoán parser sẽ chọn property trực tiếp hay property lồng nhau.

**Dùng kiểu tham số đúng với property.** Nếu field là `Double`, tránh truyền chuỗi; nếu field là ngày, dùng kiểu thời gian phù hợp với mapping và converter.

**Đặt thứ tự tham số nhất quán.** Thứ tự tham số phải theo thứ tự điều kiện xuất hiện trong tên method.

**Dùng Pageable cho sort động.** Tránh tạo nhiều method gần giống nhau chỉ khác `OrderBy`.

**Đừng dựa vào tên method để thay thế Query DSL phức tạp.** Nếu cần ngoặc logic, nested query, script, aggregation hoặc nhiều tùy chọn Search API, dùng Operations.

### Ví dụ method dễ đọc

~~~java
public interface PurchaseOrderRepository
        extends ElasticsearchRepository<PurchaseOrder, String> {

    List<PurchaseOrder> findByOrderNumber(String orderNumber);

    List<PurchaseOrder> findByCustomer_Email(String email);

    List<PurchaseOrder> findByShippingAddress_City(String city);

    Page<PurchaseOrder> findByStatusOrderByCreatedAtDesc(
        String status,
        Pageable pageable
    );

    long countByStatus(String status);
}
~~~

Mỗi method mô tả một điều kiện hoặc mục tiêu rõ ràng. Những property path lồng nhau dùng underscore để làm rõ ranh giới.

## 13. Các lỗi thường gặp khi phân giải property path

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `No property 'X' found for type 'Y'` | Property không tồn tại hoặc viết sai tên | Đối chiếu entity và tên Java property |
| Repository không khởi động được | Query method được phân tích nhưng property path không hợp lệ | Kiểm tra phần tên sau `By` và nested path |
| Query dùng nhầm property trực tiếp | Tên property dài xung đột với đường dẫn lồng nhau | Dùng underscore để chỉ rõ ranh giới |
| Tên method compile nhưng query không đúng | Parser hợp lệ nhưng semantics operator không như mong muốn | Xem query thực tế, mapping và operator hỗ trợ |
| Query nested không giữ quan hệ object | Derived query không tạo nested context như use case yêu cầu | Dùng nested query rõ ràng qua Operations |
| Field Elasticsearch không được tìm thấy | Nhầm tên field trong mapping với Java property | Dùng property Java trong method; kiểm tra `@Field(name=...)` |
| Tìm theo ID cho kết quả khác dự kiến | Nhầm phương thức kế thừa `findById` với derived property | Phân biệt identifier `@Id` và property nghiệp vụ |
| Query trả rỗng với `Containing` hoặc `Like` | Hiểu operator theo SQL trong khi field là text/keyword | Kiểm tra analyzer và query được sinh |

### Lỗi No property found

Ví dụ entity:

~~~java
public class Customer {
    private String emailAddress;
}
~~~

Repository viết:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Nếu entity không có property `email`, Spring Data không tự đoán rằng `email` có nghĩa là `emailAddress`. Hãy đổi thành:

~~~java
Optional<Customer> findByEmailAddress(String emailAddress);
~~~

Tên property phải khớp với mô hình Java.

### Lỗi property lồng nhau bị hiểu sai

Entity:

~~~java
public class Customer {
    private String addressCity;
    private Address address;
}

public class Address {
    private String city;
}
~~~

Nếu muốn tìm `address.city`, dùng:

~~~java
List<Customer> findByAddress_City(String city);
~~~

Dấu gạch dưới làm rõ đường dẫn cần truy cập và tránh việc parser ưu tiên `addressCity`.

### Lỗi query khác với kỳ vọng do analyzer

Giả sử `name` được mapping thành `text` với analyzer chuẩn. Một query `Containing` có thể hoạt động theo semantics token của Elasticsearch thay vì so khớp chuỗi con từng ký tự. Nếu yêu cầu là tìm prefix hoặc substring theo cách cụ thể, hãy thiết kế analyzer/multi-field phù hợp và dùng query DSL tương ứng. Không đổi tên method để cố ép semantics khác với kiểu field.

## 14. Cách kiểm tra query derivation khi debug

Khi repository method không tạo kết quả mong muốn, hãy kiểm tra theo thứ tự:

1. Đọc lại method name và đánh dấu subject, `By`, predicate, operator, `OrderBy`.
2. Liệt kê các tham số theo đúng thứ tự điều kiện.
3. Mở entity và xác nhận từng property tồn tại.
4. Với đường dẫn lồng nhau, viết đường dẫn dạng chấm như `customer.email`.
5. Nếu có khả năng mơ hồ, thêm underscore để chỉ rõ ranh giới.
6. Kiểm tra `@Field(name = "...")`, kiểu field và analyzer.
7. Xác nhận query method và operator được phiên bản Spring Data Elasticsearch hỗ trợ.
8. Quan sát query/request được gửi tới Elasticsearch nếu kết quả vẫn không đúng.
9. Chạy query tương đương trong Elasticsearch Dev Tools trên cùng index.
10. Dùng integration test để kiểm tra hành vi với mapping thực tế.

Có thể bật logging phù hợp trong môi trường phát triển để quan sát request. Tên logger và mức log phụ thuộc client/transport và phiên bản Spring Data. Tránh log dữ liệu nhạy cảm hoặc toàn bộ document trong môi trường production.

### Kiểm thử repository method

Một integration test nên kiểm tra cả dữ liệu trực tiếp và đường dẫn lồng nhau:

~~~java
@DataElasticsearchTest
class PurchaseOrderRepositoryTests {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void findsOrdersByNestedCustomerEmail() {
        // Chuẩn bị document có customer.email đã biết.
        // Lưu document vào index kiểm thử.
        // Gọi findByCustomer_Email(...)
        // Xác nhận đúng document được trả về.
    }
}
~~~

Đây là skeleton minh họa. Annotation test, cấu hình Elasticsearch và cách tạo index phụ thuộc phiên bản Spring Boot/Spring Data của dự án. Test nên chạy trên Elasticsearch tương thích với môi trường ứng dụng và dùng mapping giống use case thực tế.

## 15. Khi nào tên phương thức không còn là công cụ phù hợp?

Derived query phù hợp khi điều kiện ngắn, tên property rõ và query semantics đơn giản. Hãy chuyển sang `ElasticsearchOperations` khi:

- Tên method quá dài hoặc có nhiều tầng property path.
- Cần nhóm điều kiện logic phức tạp với ngoặc rõ ràng.
- Cần nested query nhiều tầng hoặc nested correlation.
- Cần Query DSL chuyên biệt như function score, geo, script hoặc rescore.
- Cần aggregation, highlight, collapse hoặc search_after.
- Cần chọn index/alias động bằng `IndexCoordinates`.
- Cần kết hợp query, sort, source filtering và các tùy chọn Search API.
- Cần kiểm soát chính xác semantics mà derived operator không biểu đạt được.

Ví dụ thay vì một tên method rất dài:

~~~java
findByStatusAndCustomer_Address_CityAndTotalGreaterThanOrPriorityTrue(...)
~~~

có thể tạo query bằng builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .filter(f -> f.term(t -> t
                .field("status")
                .value("ACTIVE")
            ))
            .filter(f -> f.term(t -> t
                .field("customer.address.city")
                .value("Hanoi")
            ))
            .filter(f -> f.range(r -> r
                .number(n -> n
                    .field("total")
                    .gt(100.0)
                )
            ))
        )
    )
    .build();

SearchHits<PurchaseOrder> hits =
    operations.search(query, PurchaseOrder.class);
~~~

Đây là minh họa về khả năng biểu diễn query tường minh. Cú pháp builder và nested query cần được điều chỉnh theo kiểu mapping, Java API Client và phiên bản Spring Data thực tế. Nếu `customer.address` là nested field, cần dùng nested query đúng path thay vì chỉ truy vấn field path như object thông thường.

Operations không thay thế repository cho mọi thao tác. Repository vẫn phù hợp với CRUD và các truy vấn đơn giản; Operations dành cho những use case cần điều khiển query và response chi tiết.

## 16. Checklist trước khi thêm một derived query method

- [ ] Phần mở đầu của method có đúng dạng repository được hỗ trợ không?
- [ ] `By` có đánh dấu đúng điểm bắt đầu predicate không?
- [ ] Mỗi property trong predicate có tồn tại trên entity không?
- [ ] Tên property đang dùng là tên Java hay vô tình dùng tên JSON/Elasticsearch?
- [ ] Có property path lồng nhau cần phân tách bằng underscore không?
- [ ] Có property trực tiếp nào gây mơ hồ với đường dẫn lồng nhau không?
- [ ] Các operator có được Spring Data Elasticsearch của phiên bản dự án hỗ trợ không?
- [ ] Thứ tự tham số có khớp thứ tự điều kiện không?
- [ ] `And`/`Or` có tạo đúng nhóm logic mong muốn không?
- [ ] `OrderBy`, `Top` hoặc `First` có phù hợp với yêu cầu kết quả không?
- [ ] Mapping field và analyzer có phù hợp với semantics của operator không?
- [ ] Nếu field là nested, query có cần nested context rõ ràng không?
- [ ] Query có phức tạp đến mức nên dùng CriteriaQuery hoặc NativeQuery không?

Tên phương thức repository là một cách khai báo truy vấn ngắn gọn, nhưng nó dựa vào quy tắc phân tích tên và metadata entity rất cụ thể. Khi nắm được subject, predicate, operator và cách phân giải property path, ta có thể viết derived query dễ đọc, tránh xung đột tên và xác định nhanh lỗi. Khi cấu trúc điều kiện vượt quá khả năng biểu đạt của tên method, hãy dùng Operations để xây dựng query tường minh và giữ cho repository tập trung vào các thao tác dữ liệu phổ biến.


# Phân biệt nhúng đối tượng và tham chiếu bằng định danh

Khi một object Java chứa tham chiếu tới object khác, JSON có thể biểu diễn quan hệ đó theo hai cách chính. Cách thứ nhất là **nhúng object**: ghi toàn bộ dữ liệu của object liên quan ngay tại vị trí property. Cách thứ hai là **tham chiếu bằng định danh**: chỉ ghi một ID để chỉ ra object được nhắc tới. Hai cách tạo ra JSON có cấu trúc khác nhau và dẫn đến cách Jackson serialize, deserialize cũng khác nhau.

Ví dụ, một đơn hàng thuộc về khách hàng. Dạng nhúng có thể ghi toàn bộ khách hàng bên trong đơn hàng:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": {
    "id": "CUS-42",
    "name": "An"
  }
}
```

Dạng tham chiếu chỉ ghi ID khách hàng:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": "CUS-42"
}
```

Dạng nhúng thuận tiện khi consumer cần một snapshot dữ liệu đầy đủ và quan hệ có cấu trúc cây đơn giản. Dạng tham chiếu gọn hơn khi nhiều object cùng trỏ đến một thực thể hoặc khi cần tránh lặp dữ liệu. Với Jackson, `@JsonIdentityInfo` khai báo cơ chế định danh object; `@JsonIdentityReference` điều khiển việc một property được ghi dưới dạng ID. Việc chọn đúng mô hình phụ thuộc vào hợp đồng JSON, vòng đời object và cách consumer giải quyết ID.

## 1. Nhúng object: biểu diễn dữ liệu theo cấu trúc cây

Trong JSON lồng nhau, property có thể chứa trực tiếp một object khác. Java DTO phản ánh cấu trúc này bằng field có kiểu class:

```java
public class Customer {
    private String id;
    private String name;

    public Customer() {
    }

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

public class Order {
    private String id;
    private BigDecimal total;
    private Customer customer;

    // Getter và setter
}
```

Jackson serialize một instance `Order` theo cấu trúc object của các property:

```java
ObjectMapper mapper = new ObjectMapper();

Customer customer = new Customer("CUS-42", "An");
Order order = new Order();
order.setId("ORD-100");
order.setTotal(new BigDecimal("250000"));
order.setCustomer(customer);

String json = mapper.writeValueAsString(order);
```

Kết quả có property `customer` là object JSON:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": {
    "id": "CUS-42",
    "name": "An"
  }
}
```

Khi deserialize vào `Order.class`, Jackson tạo một object `Customer` mới từ nội dung bên trong `customer`. Consumer không cần thực hiện bước tra cứu riêng để biết tên khách hàng vì dữ liệu đã nằm trong payload.

### 1.1. Ưu điểm của nhúng object

- Payload tự chứa: consumer nhận đủ dữ liệu cần thiết trong một lần đọc.
- Cấu trúc JSON phản ánh trực tiếp quan hệ giữa các DTO.
- Không cần object ID resolver để khôi phục quan hệ.
- Phù hợp với response DTO, snapshot hoặc dữ liệu có quan hệ nhỏ và ít dùng chung.
- Dễ đọc và kiểm tra thủ công khi payload có kích thước vừa phải.

### 1.2. Hạn chế của nhúng object

Nếu nhiều đơn hàng cùng thuộc một khách hàng, mỗi đơn có thể lặp lại toàn bộ thông tin khách hàng:

```json
[
  {
    "id": "ORD-100",
    "customer": {
      "id": "CUS-42",
      "name": "An"
    }
  },
  {
    "id": "ORD-101",
    "customer": {
      "id": "CUS-42",
      "name": "An"
    }
  }
]
```

JSON không thể hiện rằng hai object `customer` trong tài liệu chính là cùng một instance Java. Khi deserialize, Jackson có thể tạo hai object `Customer` riêng biệt dù chúng có cùng giá trị `id`.

Điều đó có thể dẫn tới:

- Payload lớn hơn do dữ liệu lặp.
- Consumer phải tự hợp nhất các object có cùng ID nếu cần identity chung.
- Thay đổi dữ liệu khách hàng có thể tạo nhiều bản sao không đồng nhất trong cùng một payload.
- Quan hệ hai chiều có nguy cơ đệ quy vô hạn khi object A chứa B và B lại chứa A.

Nhúng object phù hợp khi cần một cây dữ liệu độc lập. Khi mô hình là đồ thị có chia sẻ object hoặc có vòng tham chiếu, cần một cách biểu diễn khác.

## 2. Tham chiếu bằng định danh: chỉ truyền ID

Thay vì nhúng toàn bộ object, JSON có thể chứa một giá trị định danh:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": "CUS-42"
}
```

Ở đây, `customer` là scalar ID chứ không phải object. Điều này giảm lặp dữ liệu, nhưng consumer cần biết cách tìm object tương ứng với `CUS-42`.

Một cách thiết kế API tường minh là dùng property `customerId` trong DTO:

```java
public class OrderRequest {
    private String id;
    private BigDecimal total;
    private String customerId;

    // Getter và setter
}
```

Sau khi deserialize, service dùng `customerId` để tra cứu khách hàng:

```java
OrderRequest request = mapper.readValue(json, OrderRequest.class);
Customer customer = customerRepository.findById(request.getCustomerId())
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy khách hàng"));

Order order = createOrder(request, customer);
```

Đây là mô hình tham chiếu ở tầng API/domain: JSON chứa ID và ứng dụng chủ động giải quyết quan hệ. Nó thường dễ hiểu với consumer và làm rõ ranh giới giữa parsing dữ liệu với truy xuất persistence.

Jackson cũng có thể giữ field Java là `Customer` nhưng serialize property đó thành ID bằng object identity. Đây là mục đích của `@JsonIdentityInfo` kết hợp `@JsonIdentityReference`.

## 3. @JsonIdentityInfo khai báo identity cho object

`@JsonIdentityInfo` cho Jackson biết cách tạo hoặc lấy một object ID để nhận diện object trong quá trình serialize và deserialize. Annotation thường được đặt trên class hoặc kiểu cần có identity.

Với Jackson 2.x, annotation thuộc package `com.fasterxml.jackson.annotation`:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;

    // Getter và setter
}
```

Các thuộc tính quan trọng:

- `generator`: cách tạo hoặc lấy object ID.
- `property`: tên property chứa ID khi dùng `PropertyGenerator`.
- `scope`: phạm vi định danh; mặc định là kiểu object rộng nhất theo cấu hình annotation, có thể chỉ định rõ để phân tách các nhóm ID.

Với `ObjectIdGenerators.PropertyGenerator`, Jackson dùng giá trị của property `id` đã có trên object. Vì vậy, class cần một property định danh phù hợp và giá trị phải có sẵn khi serialize object.

### 3.1. PropertyGenerator: dùng ID nghiệp vụ có sẵn

Đây thường là lựa chọn tự nhiên với entity có khóa ổn định:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;

    public Customer() {
    }

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Property `id` vừa là dữ liệu thông thường của object vừa là object identity. Khi Jackson gặp một object `Customer` lần đầu trong tài liệu, nó serialize object đầy đủ. Khi gặp lại cùng identity, Jackson có thể ghi ID thay cho toàn bộ object.

### 3.2. IntSequenceGenerator: tạo ID cho tài liệu

Nếu class không có ID nghiệp vụ, Jackson có thể tạo object ID tuần tự:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.IntSequenceGenerator.class,
        property = "@id"
)
public class GraphNode {
    private String label;
    private GraphNode next;

    // Getter và setter
}
```

Với generator này, Jackson tạo ID cho các object trong phạm vi serialization. Tên property `@id` là nơi ghi ID khi object được phát đầy đủ. Những lần tham chiếu tiếp theo có thể được ghi thành giá trị ID.

ID tuần tự hữu ích cho đồ thị tạm thời trong một tài liệu. Nó không phải ID bền vững của database và không nên được xem là định danh có thể dùng giữa nhiều request hoặc nhiều file khác nhau.

### 3.3. UUIDGenerator và generator tùy chỉnh

Jackson cũng cung cấp generator như `UUIDGenerator`. Khi cần quy tắc định danh riêng, có thể triển khai `ObjectIdGenerator` tùy chỉnh. Tuy nhiên, nếu entity đã có khóa nghiệp vụ ổn định, dùng `PropertyGenerator` thường dễ tích hợp hơn và tránh phát sinh một loại ID phụ.

Không nên chọn generator chỉ vì tên nó thuận tiện. Hãy xác định ID có cần ổn định qua nhiều tài liệu, có cần tra cứu ngoài hệ thống, và consumer có biết cách diễn giải ID đó không.

## 4. Hành vi mặc định: lần đầu nhúng đầy đủ, lần sau tham chiếu ID

Chỉ bật `@JsonIdentityInfo` chưa có nghĩa mọi property tham chiếu sẽ luôn là scalar ID. Mặc định, Jackson thường serialize lần xuất hiện đầu tiên của object dưới dạng đầy đủ kèm ID, sau đó dùng ID cho những lần xuất hiện tiếp theo của cùng object identity.

Ví dụ:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;
    // Getter/setter
}

public class Order {
    private String id;
    private Customer customer;
    // Getter/setter
}
```

Nếu một graph chứa cùng một instance `Customer` ở nhiều vị trí, lần đầu có thể xuất hiện:

```json
{
  "id": "CUS-42",
  "name": "An"
}
```

Lần sau có thể chỉ xuất hiện:

```json
"CUS-42"
```

Hành vi này giúp Jackson tránh lặp dữ liệu và hỗ trợ object graph có tham chiếu lặp. Kết quả cụ thể phụ thuộc thứ tự traversal: vị trí nào được serialize trước sẽ chứa object đầy đủ; các vị trí sau có thể trở thành ID reference.

Điều này khác với việc luôn xuất ID. Muốn property luôn được ghi thành ID, kể cả lần xuất hiện đầu tiên tại property đó, dùng `@JsonIdentityReference(alwaysAsId = true)`.

## 5. @JsonIdentityReference(alwaysAsId = true)

`@JsonIdentityReference` điều khiển cách một object đã có identity được biểu diễn tại một vị trí. Với `alwaysAsId = true`, Jackson dùng ID thay cho object đầy đủ.

Ví dụ:

```java
public class Order {
    private String id;
    private BigDecimal total;

    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    // Getter và setter
}
```

Kết hợp với `@JsonIdentityInfo` trên `Customer`:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;

    // Getter và setter
}
```

Khi serialize `Order`, property `customer` được ghi bằng ID:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": "CUS-42"
}
```

Dữ liệu `name` của khách hàng không xuất hiện trong property này. Consumer cần có nguồn khác để giải quyết `CUS-42`, hoặc object đầy đủ phải được định nghĩa ở nơi khác trong cùng JSON graph.

### 5.1. Identity annotation và reference annotation có trách nhiệm khác nhau

| Annotation | Trách nhiệm |
|---|---|
| `@JsonIdentityInfo` | Khai báo cách object có ID và Jackson nhận diện object |
| `@JsonIdentityReference(alwaysAsId = true)` | Yêu cầu property dùng ID thay cho object đầy đủ |
| `@JsonProperty` | Đặt tên property JSON |
| `@JsonTypeInfo` | Chọn subtype polymorphic; không phải cơ chế object identity |

`@JsonIdentityReference` cần một identity mechanism có thể dùng được cho kiểu được tham chiếu. Nếu chỉ gắn `alwaysAsId = true` mà kiểu đích không có identity metadata hoặc resolver phù hợp, Jackson không có cơ sở để biết ID nào đại diện cho object.

### 5.2. Dùng annotation ở property hoặc kiểu

Có thể đặt `@JsonIdentityReference` trên property cụ thể nếu chỉ một quan hệ cần ID. Điều này giữ những quan hệ khác ở dạng nhúng.

Nếu đặt trên kiểu, ảnh hưởng có thể rộng hơn đối với các vị trí dùng kiểu đó. Trong DTO tích hợp, đặt tại property thường làm rõ chính xác quan hệ nào là reference.

## 6. Ví dụ hoàn chỉnh: Order nhúng dữ liệu và tham chiếu Customer bằng ID

Giả sử response cần chứa thông tin đơn hàng và các dòng hàng, nhưng chỉ cần ID khách hàng:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;

    public Customer() {
    }

    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

public class OrderLine {
    private String sku;
    private int quantity;

    // Getter và setter
}

public class Order {
    private String id;
    private BigDecimal total;

    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    private List<OrderLine> lines;

    // Getter và setter
}
```

Với một instance customer đã có ID:

```java
Customer customer = new Customer("CUS-42", "An");

Order order = new Order();
order.setId("ORD-100");
order.setTotal(new BigDecimal("250000"));
order.setCustomer(customer);
order.setLines(List.of(new OrderLine("SKU-1", 2)));
```

JSON có dạng:

```json
{
  "id": "ORD-100",
  "total": 250000,
  "customer": "CUS-42",
  "lines": [
    {
      "sku": "SKU-1",
      "quantity": 2
    }
  ]
}
```

Các dòng hàng vẫn được nhúng đầy đủ; khách hàng được tham chiếu bằng ID. Đây là một hợp đồng hỗn hợp: embedded object cho dữ liệu cần có trong response, ID reference cho quan hệ mà consumer có thể tra cứu riêng.

Điểm cần lưu ý: deserialize JSON trên thành `Order` không tự truy vấn database để lấy `Customer`. Nếu ID `CUS-42` chưa được đăng ký như object identity trong tài liệu hoặc resolver, Jackson không thể tự tạo ra object Customer có tên `An`.

## 7. Tham chiếu đã được định nghĩa và tham chiếu chỉ có ID

Object identity trong Jackson có thể được giải quyết khi object đầy đủ đã xuất hiện ở một vị trí khác trong cùng tài liệu. Ví dụ:

```json
{
  "customer": {
    "id": "CUS-42",
    "name": "An"
  },
  "orders": [
    {
      "id": "ORD-100",
      "customer": "CUS-42"
    },
    {
      "id": "ORD-101",
      "customer": "CUS-42"
    }
  ]
}
```

Nếu kiểu `Customer` có `@JsonIdentityInfo(property = "id")`, Jackson có thể đăng ký object customer khi đọc phần `customer`, sau đó giải quyết hai reference `CUS-42` trong danh sách đơn hàng về cùng object identity.

Ngược lại, nếu tài liệu chỉ có:

```json
{
  "id": "ORD-100",
  "customer": "CUS-42"
}
```

thì payload không chứa object `Customer` đầy đủ. Jackson không có dữ liệu để tự tạo object có tên và các thuộc tính khác. Nếu không có custom resolver hoặc cơ chế giải quyết ngoài Jackson, reference có thể không được giải quyết và gây lỗi unresolved object ID.

Đây là khác biệt nền tảng:

- **Reference tới object đã xuất hiện trong tài liệu:** Jackson có thể tra cứu object đã đăng ký bằng ID.
- **Reference tới object chỉ tồn tại trong database hoặc hệ thống khác:** cần ứng dụng cung cấp cơ chế lookup; Jackson không tự biết repository nào cần gọi.

## 8. ObjectIdResolver và giới hạn của việc tra cứu ID

Khi deserialize object identity, Jackson sử dụng `ObjectIdResolver` để lưu và tìm object theo ID. Resolver mặc định phục vụ việc liên kết ID với object trong quá trình đọc tài liệu. Nó không tự động kết nối database, HTTP service hoặc cache của ứng dụng.

Một custom resolver có thể được dùng khi ứng dụng muốn cung cấp cách giải quyết ID riêng. Hợp đồng resolver gồm các thao tác như:

- Tạo resolver mới cho lần deserialize.
- Kiểm tra resolver có thể được tái sử dụng cho scope hiện tại không.
- Bind object với object ID khi object đầy đủ được đọc.
- Resolve ID thành object đã biết.

Ví dụ khung triển khai:

```java
public class CustomerResolver implements ObjectIdResolver {
    private final Map<ObjectIdGenerator.IdKey, Object> items = new HashMap<>();

    @Override
    public void bindItem(ObjectIdGenerator.IdKey id, Object pojo) {
        Object previous = items.putIfAbsent(id, pojo);
        if (previous != null && previous != pojo) {
            throw new IllegalStateException("Duplicate object id: " + id.key);
        }
    }

    @Override
    public Object resolveId(ObjectIdGenerator.IdKey id) {
        return items.get(id);
    }

    @Override
    public ObjectIdResolver newForDeserialization(Object context) {
        return new CustomerResolver();
    }

    @Override
    public boolean canUseFor(ObjectIdResolver resolverType) {
        return resolverType != null
                && resolverType.getClass() == getClass();
    }
}
```

Đây là resolver theo map trong bộ nhớ cho một lần deserialize, minh họa hợp đồng cơ bản. Để tích hợp repository, cần quyết định rõ transaction, cache, lỗi không tìm thấy ID và việc resolver có được gọi nhiều lần hay không. Không nên gọi database một cách ngầm định trong resolver nếu việc đó làm Jackson binding phụ thuộc vào side effect khó kiểm soát.

Có thể gắn resolver vào annotation:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id",
        resolver = CustomerResolver.class
)
public class Customer {
    // ...
}
```

Trong triển khai thực tế, resolver phải xử lý đúng scope và vòng đời. Một resolver mới thường được tạo theo context deserialize; không dùng map static toàn cục nếu không muốn ID từ tài liệu này ảnh hưởng tài liệu khác.

## 9. Đồ thị có vòng tham chiếu và object dùng chung

Một object graph có thể là cây, đồ thị có chia sẻ node hoặc đồ thị có chu trình.

### 9.1. Cây không có tham chiếu ngược

Ví dụ `Order` chứa `OrderLine`, mỗi line chứa các giá trị đơn giản. Không có object nào trỏ ngược về `Order`. Nhúng object là tự nhiên:

```json
{
  "id": "ORD-100",
  "lines": [
    {"sku": "SKU-1", "quantity": 2},
    {"sku": "SKU-2", "quantity": 1}
  ]
}
```

### 9.2. Đồ thị có object được chia sẻ

Hai order cùng tham chiếu một Customer. Nếu nhúng, customer có thể bị lặp trong payload và thành hai instance sau deserialize. Nếu identity được cấu hình, Jackson có thể ghi object một lần và tham chiếu các lần sau bằng ID.

### 9.3. Chu trình hai chiều

Ví dụ:

```text
Customer
   |
   | orders
   v
 Order
   |
   | customer
   +----------> Customer
```

Nếu serialize thuần bằng embedded object, Jackson có thể đi từ Customer sang Order rồi quay lại Customer, tiếp tục lặp đệ quy. Có thể xảy ra `JsonMappingException: Infinite recursion` hoặc lỗi tương tự.

Object identity giúp Jackson nhận ra object đã được xử lý và dùng ID để biểu diễn lần tham chiếu tiếp theo:

```json
{
  "id": "CUS-42",
  "name": "An",
  "orders": [
    {
      "id": "ORD-100",
      "total": 250000,
      "customer": "CUS-42"
    }
  ]
}
```

Cách này giữ được quan hệ hai chiều trong graph mà không lặp toàn bộ object vô hạn.

## 10. So sánh @JsonIdentityInfo với @JsonManagedReference/@JsonBackReference

Jackson còn có `@JsonManagedReference` và `@JsonBackReference` để xử lý quan hệ hai chiều phổ biến như parent-child. Chúng thường bị nhầm với object ID reference, nhưng mục đích khác nhau.

Ví dụ parent-child:

```java
public class Parent {
    private String id;

    @JsonManagedReference
    private List<Child> children;

    // Getter/setter
}

public class Child {
    private String id;

    @JsonBackReference
    private Parent parent;

    // Getter/setter
}
```

Khi serialize Parent, Jackson ghi danh sách children; property back reference `parent` bị bỏ khỏi JSON để tránh quay lại Parent. Khi deserialize, Jackson thiết lập quan hệ ngược theo cơ chế managed/back reference.

| Tiêu chí | Object identity | Managed/back reference |
|---|---|---|
| Annotation | `@JsonIdentityInfo`, có thể thêm `@JsonIdentityReference` | `@JsonManagedReference`, `@JsonBackReference` |
| JSON biểu diễn | Object đầy đủ và ID reference | Ghi phía managed, bỏ phía back |
| Giữ object identity dùng chung | Có | Không phải mục đích chính |
| Reference có ID rõ ràng trên wire | Có thể có | Không |
| Nhiều quan hệ/đồ thị phức tạp | Linh hoạt hơn nếu ID được quản lý đúng | Chủ yếu cho cặp quan hệ cha-con |
| Consumer khác ngôn ngữ | Có thể hiểu reference qua ID nếu contract rõ | Thấy một phía bị lược bỏ |
| Lookup ngoài tài liệu | Cần resolver hoặc ứng dụng tra cứu | Không cung cấp cơ chế ID lookup |

Dùng managed/back reference nếu chỉ cần bỏ một cạnh tham chiếu ngược trong JSON và quan hệ cha-con rõ ràng. Dùng object identity khi cần giữ các tham chiếu dùng chung hoặc biểu diễn ID trên wire.

Không gắn cả hai cơ chế một cách tùy tiện trên cùng quan hệ. Hãy xác định JSON contract cần giữ quan hệ như thế nào trước khi chọn annotation.

## 11. Dùng ID reference ở một property nhưng vẫn nhúng object ở nơi khác

Một graph có thể cần cả hai cách. Ví dụ một response danh sách khách hàng muốn trả object customer đầy đủ, nhưng mỗi order bên trong chỉ cần customer ID để tránh lặp:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;
    private List<Order> orders;

    // Getter/setter
}

public class Order {
    private String id;

    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    // Getter/setter
}
```

Nếu response root là Customer, JSON có thể chứa customer đầy đủ và order tham chiếu về ID:

```json
{
  "id": "CUS-42",
  "name": "An",
  "orders": [
    {
      "id": "ORD-100",
      "customer": "CUS-42"
    }
  ]
}
```

Tại đây:

- Root customer là embedded object đầy đủ.
- Orders được nhúng trong danh sách.
- Property `Order.customer` luôn dùng ID.
- Không cần phát lại tên và dữ liệu customer ở từng order.

Đây là pattern hữu ích cho aggregate response. Tuy nhiên, khi deserialize, reference ID cần được giải quyết trong cùng graph hoặc bằng resolver đã được thiết kế.

## 12. Identity generator và yêu cầu về ID

Chọn generator ảnh hưởng trực tiếp tới wire format và khả năng đọc lại.

| Generator | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| `PropertyGenerator` | Dùng property có sẵn trên object | Entity có ID ổn định |
| `IntSequenceGenerator` | Tạo số tuần tự trong phạm vi generator | Graph tạm thời trong một tài liệu |
| `UUIDGenerator` | Tạo UUID làm object ID | Object không có ID nghiệp vụ nhưng cần identity trong tài liệu |
| Generator tùy chỉnh | Theo quy tắc ứng dụng | Hệ thống có quy ước định danh riêng |

### 12.1. PropertyGenerator cần ID có giá trị

Với:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
```

Jackson lấy ID từ property `id`. Nếu object mới chưa được cấp ID, serialize có thể thất bại hoặc không tạo được identity như mong đợi. Vì vậy, hãy bảo đảm ID được gán trước khi serialize.

Không dùng một field tạm thời hoặc giá trị dễ trùng làm identity. Hai object khác nhau có cùng ID trong cùng scope có thể tạo xung đột hoặc làm consumer liên kết sai object.

### 12.2. ID phải duy nhất trong scope

Nếu `Customer` và `Order` đều dùng ID dạng `"100"`, cần cân nhắc scope hoặc namespace để không lẫn identity. Scope giúp phân tách object identity theo kiểu/phạm vi. Trong wire contract, cũng có thể dùng ID có namespace rõ ràng như `CUS-100` và `ORD-100`.

Không nên coi ID là duy nhất toàn cục nếu hệ thống chỉ bảo đảm duy nhất trong từng loại entity hoặc tenant.

### 12.3. ID tuần tự không phải khóa bền vững

`IntSequenceGenerator` tạo ID phục vụ tham chiếu trong quá trình serialize một graph. Một lần serialize khác có thể tạo chuỗi ID khác. Không lưu các ID này làm khóa lâu dài, không dùng chúng để tra cứu database và không giả định ID 1 của tài liệu này liên quan đến ID 1 của tài liệu khác.

## 13. Forward reference và thứ tự xuất hiện

Một ID reference có thể xuất hiện trước object đầy đủ tương ứng trong JSON. Đây là forward reference.

Ví dụ:

```json
{
  "order": {
    "id": "ORD-100",
    "customer": "CUS-42"
  },
  "customer": {
    "id": "CUS-42",
    "name": "An"
  }
}
```

Jackson có thể hỗ trợ một số trường hợp forward reference bằng cách giữ tham chiếu chưa giải quyết rồi hoàn tất khi object có ID được đọc sau đó. Khả năng này phụ thuộc loại property và cách object được tạo. Với setter/mutable property, Jackson có thể trì hoãn việc gán; với creator parameter hoặc cấu trúc đặc biệt, hành vi có thể bị giới hạn.

Để contract dễ xử lý và dễ tương thích giữa các consumer, thường nên phát object đầy đủ trước các reference phụ thuộc vào nó. Nếu thứ tự không thể bảo đảm, hãy kiểm thử rõ forward-reference behavior với đúng kiểu DTO và Jackson version.

Một ID chỉ xuất hiện mà không có object đầy đủ trong tài liệu là trường hợp khác: đó là external reference. Jackson cần resolver hoặc ứng dụng tra cứu; việc reorder JSON không giải quyết được.

## 14. Phạm vi của object identity và vòng đời resolver

Object identity trong Jackson gắn với quá trình serialize hoặc deserialize cụ thể và scope của generator/resolver. Không nên mặc định một lần đọc JSON sẽ chia sẻ object cache với lần đọc JSON khác.

Ví dụ hai file:

```json
{"id":"CUS-42","name":"An"}
```

và:

```json
{"orderId":"ORD-100","customer":"CUS-42"}
```

Nếu đọc từng file bằng hai lần `readValue()` độc lập, ID được đăng ký khi đọc file đầu không tự động có mặt trong context đọc file thứ hai. Resolver mặc định không phải session cache toàn ứng dụng.

Nếu cần liên kết object qua nhiều tài liệu hoặc request, hãy xử lý ở tầng ứng dụng:

1. Deserialize ID thành DTO/reference token.
2. Tra cứu entity qua repository/service.
3. Kiểm tra quyền truy cập và tenant.
4. Gắn entity vào domain object.
5. Xử lý trường hợp ID không tồn tại hoặc không được phép tham chiếu.

Cách này làm rõ boundary và tránh dùng Jackson như một ORM.

## 15. Dùng DTO ID rõ ràng hay giữ field kiểu object?

Có hai cách thiết kế Java khi JSON chứa ID.

### 15.1. DTO có property ID

```java
public class OrderRequest {
    private String customerId;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }
}
```

Ưu điểm:

- Hợp đồng JSON rõ ràng.
- Deserialize không cần object identity resolver.
- Service chủ động tra cứu entity.
- Dễ validate ID, tenant và quyền truy cập.
- Không phụ thuộc Jackson-specific annotation.

Đây thường là lựa chọn đơn giản cho request/command từ client.

### 15.2. DTO có property kiểu object và identity reference

```java
public class OrderRequest {
    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    // Getter/setter
}
```

Ưu điểm:

- Java model giữ quan hệ kiểu `Customer`.
- Có thể dùng object identity khi graph chứa object đầy đủ và reference lặp.
- Hữu ích khi serialize/deserialise một graph trong cùng tài liệu.

Hạn chế:

- ID-only input không tự biến thành entity từ database.
- Cần `@JsonIdentityInfo` và resolver phù hợp.
- Consumer phải hiểu identity semantics của Jackson nếu wire format phụ thuộc annotation.

### 15.3. Quy tắc lựa chọn

| Nhu cầu | Cách phù hợp |
|---|---|
| API nhận `customerId` rồi service tra cứu | DTO có `customerId` |
| Một JSON document chứa object đầy đủ và các reference tới cùng object | `@JsonIdentityInfo` |
| Một property luôn phải phát ID dù object chưa xuất hiện trước đó | `@JsonIdentityReference(alwaysAsId = true)` kết hợp identity definition |
| Cần bỏ cạnh back-reference trong quan hệ parent-child | `@JsonManagedReference` / `@JsonBackReference` |
| Cần một snapshot tự chứa cho consumer | Embedded DTO |
| Payload cần chia sẻ object và giữ graph identity | Object identity hoặc một schema reference rõ ràng |

## 16. Những lỗi thường gặp

**Chỉ dùng @JsonIdentityReference mà không khai báo identity.** Jackson cần biết ID lấy từ đâu và cách resolve. Hãy cấu hình `@JsonIdentityInfo` trên kiểu được tham chiếu hoặc cung cấp cơ chế tương ứng.

**Cho rằng alwaysAsId tự truy vấn database.** Annotation chỉ điều khiển cách biểu diễn ID. Jackson không tự gọi repository hoặc HTTP service để lấy entity.

**Dùng ID null hoặc chưa được gán.** Với `PropertyGenerator`, ID phải có sẵn và có ý nghĩa. Hãy cấp ID trước khi serialize.

**Dùng ID trùng nhau trong cùng scope.** Consumer có thể liên kết nhầm object hoặc Jackson gặp xung đột object identity. Đảm bảo uniqueness theo phạm vi đã thiết kế.

**Cho rằng lần đầu luôn là ID khi dùng JsonIdentityInfo.** Mặc định, lần xuất hiện đầu tiên thường là object đầy đủ kèm ID; những lần sau mới là reference. Muốn một property luôn dùng ID, đặt `alwaysAsId = true`.

**Cho rằng ID-only JSON luôn deserialize được.** Nếu object chưa xuất hiện trong tài liệu và resolver không biết ID, Jackson không có dữ liệu để tạo object.

**Nhầm object identity với polymorphic type id.** Identity trả lời “đây là object nào?”; type discriminator trả lời “object thuộc subtype nào?”. Một payload có thể cần cả hai nhưng chúng giải quyết hai vấn đề khác nhau.

**Dùng identity reference để thay thế mọi embedded object.** Nếu consumer cần dữ liệu đầy đủ và không có dịch vụ tra cứu, ID-only payload không tự chứa đủ thông tin.

**Dùng managed/back reference khi cần ID trên wire.** Cặp annotation này chủ yếu loại bỏ một phía quan hệ khỏi JSON, không phát scalar ID để consumer tham chiếu.

**Giả định identity cache tồn tại giữa nhiều readValue().** Mặc định, object ID mapping thuộc context xử lý tài liệu. Muốn liên kết qua request, phải có resolver hoặc tầng ứng dụng quản lý.

## 17. Kiểm thử embedded object và ID reference

Nên kiểm thử cấu trúc JSON thực tế, không chỉ kiểm tra object sau deserialize.

### 17.1. Kiểm tra embedded object

```java
@Test
void shouldSerializeCustomerAsNestedObject() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Order order = orderWithCustomer(
            new Customer("CUS-42", "An")
    );

    JsonNode json = mapper.readTree(mapper.writeValueAsString(order));

    assertTrue(json.path("customer").isObject());
    assertEquals("CUS-42", json.path("customer").path("id").asText());
}
```

### 17.2. Kiểm tra alwaysAsId

```java
@Test
void shouldSerializeCustomerPropertyAsId() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Order order = orderWithCustomer(
            new Customer("CUS-42", "An")
    );

    JsonNode json = mapper.readTree(mapper.writeValueAsString(order));

    assertTrue(json.path("customer").isTextual());
    assertEquals("CUS-42", json.path("customer").asText());
}
```

Test này giả định `Customer` có `@JsonIdentityInfo(generator = PropertyGenerator.class, property = "id")` và property `Order.customer` có `@JsonIdentityReference(alwaysAsId = true)`.

### 17.3. Kiểm tra reference đã được định nghĩa trong cùng document

Dùng một DTO graph có cả object customer đầy đủ và order tham chiếu cùng ID. Sau deserialize, kiểm tra hai property trỏ về cùng object instance:

```java
assertSame(result.getCustomer(), result.getOrders().get(0).getCustomer());
```

Điều này kiểm tra identity semantics, không chỉ kiểm tra hai object có cùng giá trị field.

### 17.4. Kiểm tra external ID không được resolve

Nếu payload chỉ chứa ID mà không có object đầy đủ, viết test xác nhận hành vi mong muốn:

- Jackson báo unresolved object ID; hoặc
- custom resolver tìm được object từ nguồn đã cấu hình; hoặc
- DTO nhận ID scalar và service xử lý lookup riêng.

Không để test vô tình phụ thuộc vào dữ liệu static hoặc resolver dùng chung giữa các test.

### 17.5. Kiểm tra chu trình và object dùng chung

Tạo graph có quan hệ hai chiều và xác nhận serialization hoàn tất, không đệ quy vô hạn. Đồng thời kiểm tra JSON có đúng ID ở các cạnh tham chiếu và không lặp payload ngoài ý muốn.

## 18. Ví dụ tổng hợp: graph Customer và Order

Định nghĩa Customer có identity:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;
    private List<Order> orders = new ArrayList<>();

    // Getter và setter
}
```

Order nhúng các dữ liệu của chính nó nhưng tham chiếu Customer bằng ID:

```java
public class Order {
    private String id;
    private BigDecimal total;

    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    // Getter và setter
}
```

Tạo graph:

```java
Customer customer = new Customer();
customer.setId("CUS-42");
customer.setName("An");

Order first = new Order();
first.setId("ORD-100");
first.setTotal(new BigDecimal("250000"));
first.setCustomer(customer);

Order second = new Order();
second.setId("ORD-101");
second.setTotal(new BigDecimal("125000"));
second.setCustomer(customer);

customer.setOrders(List.of(first, second));
```

Serialize root customer:

```java
String json = mapper.writeValueAsString(customer);
```

JSON minh họa:

```json
{
  "id": "CUS-42",
  "name": "An",
  "orders": [
    {
      "id": "ORD-100",
      "total": 250000,
      "customer": "CUS-42"
    },
    {
      "id": "ORD-101",
      "total": 125000,
      "customer": "CUS-42"
    }
  ]
}
```

JSON chỉ chứa thông tin customer đầy đủ một lần. Hai order đều tham chiếu về cùng ID. Khi deserialize toàn bộ root graph, Jackson có thể liên kết các reference về object Customer đã được đọc. Nếu chỉ lấy riêng một order JSON có `customer: "CUS-42"`, ứng dụng cần cung cấp cách giải quyết ID.

## 19. Lựa chọn mô hình theo ranh giới API

Thiết kế embedded/reference nên dựa trên nhu cầu consumer và ranh giới dữ liệu:

- **Response tự chứa:** nhúng các object mà consumer cần hiển thị ngay, tránh buộc consumer gọi thêm API.
- **Request tạo quan hệ:** thường gửi `customerId`, `productId` hoặc ID tương tự; service kiểm tra và tra cứu entity.
- **Graph nội bộ trong một document:** object identity giúp giữ quan hệ chia sẻ và vòng tham chiếu.
- **Event message:** ưu tiên ID ổn định và snapshot cần thiết; không phát toàn bộ object graph persistence nếu consumer không cần.
- **Dữ liệu có quyền truy cập:** ID reference vẫn phải được kiểm tra quyền và tenant ở service; biết ID không có nghĩa người gọi được phép truy cập entity.
- **Consumer đa ngôn ngữ:** schema ID scalar tường minh thường dễ hiểu hơn phụ thuộc vào annotation-specific object identity semantics.

Không nên tối ưu payload bằng cách chuyển tất cả object thành ID nếu consumer phải gọi thêm nhiều request để dựng lại một view đơn giản. Ngược lại, không nên nhúng toàn bộ entity graph nếu dữ liệu bị lặp lớn hoặc chứa field không cần công khai.

## 20. Kết luận

Nhúng object biểu diễn quan hệ bằng cấu trúc JSON lồng nhau và phù hợp khi consumer cần dữ liệu đầy đủ trong cùng payload. Tham chiếu bằng định danh biểu diễn quan hệ bằng ID, giảm lặp dữ liệu và hỗ trợ object graph có node dùng chung hoặc chu trình. Với Jackson, `@JsonIdentityInfo` khai báo identity của object; `@JsonIdentityReference(alwaysAsId = true)` yêu cầu một property luôn phát ID thay cho object.

Cần phân biệt ID reference trong cùng JSON document với ID của entity nằm ngoài tài liệu. Jackson có thể giải quyết object đã được đăng ký trong graph, nhưng không tự truy vấn database cho một ID rời. Nếu contract chỉ cần gửi ID để service tra cứu, DTO có property như `customerId` thường rõ ràng hơn. Chọn embedded, identity reference hoặc managed/back reference theo đúng hình dạng graph và nhu cầu consumer sẽ giúp payload dễ đọc, không lặp dữ liệu không cần thiết và giữ quan hệ object nhất quán.

## Tài liệu tham khảo

- [Jackson Annotations — JsonIdentityInfo API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html)
- [Jackson Annotations — JsonIdentityReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityReference.html)
- [Jackson Annotations — ObjectIdGenerators API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/ObjectIdGenerators.html)
- [Jackson Annotations — ObjectIdResolver API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/ObjectIdResolver.html)
- [Jackson Annotations — JsonManagedReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html)
- [Jackson Annotations — JsonBackReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html)


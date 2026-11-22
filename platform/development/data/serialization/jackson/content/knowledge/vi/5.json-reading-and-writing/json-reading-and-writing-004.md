# Đọc ghi đối tượng lồng nhau và mảng dữ liệu

JSON thường biểu diễn dữ liệu theo cấu trúc phân cấp: một đối tượng có thể chứa đối tượng khác, một mảng có thể chứa nhiều đối tượng, và mỗi phần tử lại có thể chứa các mảng hoặc đối tượng con. Khi làm việc với Jackson Databind, ObjectMapper có thể chuyển toàn bộ cấu trúc đó thành các lớp Java tương ứng và ghi ngược lại thành JSON.

Điểm quan trọng là mô hình Java cần phản ánh đúng hình dạng dữ liệu. Thuộc tính JSON dạng object thường ánh xạ thành một thuộc tính có kiểu lớp Java; thuộc tính dạng array thường ánh xạ thành mảng Java hoặc collection như List. Với collection có generic type, cần cung cấp đủ thông tin kiểu cho Jackson vì Java xóa phần lớn generic type ở runtime.

## 1. JSON lồng nhau tương ứng với mô hình Java như thế nào?

Xét JSON mô tả một đơn hàng, trong đó có thông tin khách hàng và danh sách sản phẩm:

~~~json
{
  "orderId": 501,
  "customer": {
    "id": 12,
    "name": "Mai"
  },
  "items": [
    {
      "productId": "P01",
      "name": "Keyboard",
      "quantity": 2
    },
    {
      "productId": "P02",
      "name": "Mouse",
      "quantity": 1
    }
  ]
}
~~~

Cấu trúc này có ba cấp dữ liệu:

- Đối tượng gốc là đơn hàng.
- Thuộc tính customer là một đối tượng lồng nhau.
- Thuộc tính items là một mảng các đối tượng sản phẩm.

Có thể biểu diễn bằng các lớp Java:

~~~java
public class Customer {
    private Long id;
    private String name;

    public Customer() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

~~~java
public class OrderItem {
    private String productId;
    private String name;
    private int quantity;

    public OrderItem() {
    }

    public String getProductId() {
        return productId;
    }

    public void setProductId(String productId) {
        this.productId = productId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

~~~java
public class Order {
    private Long orderId;
    private Customer customer;
    private List<OrderItem> items;

    public Order() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }
}
~~~

Jackson có thể đọc JSON vào Order và tự tiếp tục ánh xạ customer thành Customer, từng phần tử trong items thành OrderItem. Không cần tự gọi readValue riêng cho từng đối tượng con.

~~~java
ObjectMapper mapper = new ObjectMapper();

Order order = mapper.readValue(json, Order.class);

System.out.println(order.getCustomer().getName());
System.out.println(order.getItems().get(0).getName());
~~~

Khi ghi, Jackson đi theo cấu trúc thuộc tính của đối tượng Java và tạo lại JSON lồng nhau:

~~~java
String output = mapper.writeValueAsString(order);
~~~

Jackson xử lý đệ quy các thuộc tính có kiểu đối tượng và các phần tử trong collection. Điều kiện là từng kiểu dữ liệu phải có cách tạo và chuyển đổi phù hợp, chẳng hạn constructor, getter/setter, annotation hoặc serializer/deserializer đã đăng ký.

## 2. Ánh xạ đối tượng con (nested object)

Một thuộc tính JSON có dấu ngoặc nhọn là object. Trong Java, khai báo thuộc tính bằng kiểu lớp tương ứng:

~~~json
{
  "id": 1001,
  "shippingAddress": {
    "street": "12 Nguyen Hue",
    "city": "Ho Chi Minh City"
  }
}
~~~

~~~java
public class Address {
    private String street;
    private String city;

    public Address() {
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class Shipment {
    private Long id;
    private Address shippingAddress;

    public Shipment() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(Address shippingAddress) {
        this.shippingAddress = shippingAddress;
    }
}
~~~

Đọc dữ liệu:

~~~java
Shipment shipment = mapper.readValue(json, Shipment.class);

String city = shipment.getShippingAddress().getCity();
~~~

Jackson nhận diện shippingAddress là một thuộc tính kiểu Address, sau đó ánh xạ object JSON bên trong vào instance Address. Cấu trúc có thể lồng nhiều cấp; mỗi cấp chỉ cần được khai báo đúng kiểu:

~~~text
Company
  └── Department
        └── Manager
              └── Contact
~~~

Khi ghi, các đối tượng con được chuyển thành object JSON tương ứng. Nếu thuộc tính đối tượng con là null, cách xuất ra phụ thuộc chính sách inclusion, chẳng hạn có giữ lại trường với giá trị null hay bỏ trường đó.

## 3. Ánh xạ mảng JSON vào Java array

JSON array được đặt trong dấu ngoặc vuông. Nếu số lượng phần tử là dữ liệu cố định hoặc muốn dùng cấu trúc mảng, có thể ánh xạ vào Java array:

~~~json
[
  {
    "code": "A01",
    "price": 120.0
  },
  {
    "code": "A02",
    "price": 250.0
  }
]
~~~

~~~java
public class Product {
    private String code;
    private double price;

    public Product() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public double getPrice() {
        return price;
    }

    public void setPrice(double price) {
        this.price = price;
    }
}
~~~

Đọc thành mảng:

~~~java
Product[] products = mapper.readValue(json, Product[].class);

for (Product product : products) {
    System.out.println(product.getCode());
}
~~~

Jackson tạo một mảng Product với số phần tử tương ứng và ánh xạ từng object JSON thành một Product. Có thể ghi mảng trở lại JSON bằng cùng ObjectMapper:

~~~java
String jsonArray = mapper.writeValueAsString(products);
~~~

Mảng kiểu nguyên thủy cũng được hỗ trợ:

~~~java
int[] scores = mapper.readValue("[8, 9, 10]", int[].class);
String output = mapper.writeValueAsString(scores);
~~~

Java array có kích thước cố định sau khi tạo. Nếu cần thêm hoặc xóa phần tử trong quá trình xử lý, collection như List thường thuận tiện hơn.

## 4. Ánh xạ mảng JSON vào List

Trong ứng dụng, List thường được dùng cho danh sách có số lượng phần tử thay đổi. Nếu JSON gốc là một mảng các Product, có thể đọc vào List<Product>:

~~~java
List<Product> products = mapper.readValue(
    json,
    new TypeReference<List<Product>>() {}
);
~~~

TypeReference giữ thông tin generic type tại runtime thông qua anonymous subclass. Nhờ đó Jackson biết phần tử của List là Product thay vì chỉ biết kiểu raw List.

Có thể dùng List trong thuộc tính của lớp như ví dụ Order.items ở phần đầu. Khi Jackson đã biết kiểu thuộc tính là List<OrderItem>, nó có đủ thông tin để tạo danh sách và ánh xạ từng phần tử.

So sánh hai cách khai báo:

| Java type | Cách khai báo kiểu cho readValue |
|---|---|
| Mảng Product | Product[].class |
| List<Product> | new TypeReference<List<Product>>() {} |
| List<String> | new TypeReference<List<String>>() {} |
| List<OrderItem> | new TypeReference<List<OrderItem>>() {} |

Ghi một List thành JSON cũng tương tự ghi mảng:

~~~java
String json = mapper.writeValueAsString(products);
~~~

Jackson tạo một JSON array và ghi lần lượt từng phần tử theo serializer tương ứng. Kiểu khai báo của biến Java không làm JSON trở thành một object bọc bên ngoài; nếu ghi trực tiếp List, kết quả mặc định là một mảng ở root.

## 5. Collection lồng nhau và mảng nhiều chiều

JSON có thể chứa mảng bên trong mảng:

~~~json
[
  [1, 2, 3],
  [4, 5, 6]
]
~~~

Có thể ánh xạ vào mảng hai chiều:

~~~java
int[][] matrix = mapper.readValue(json, int[][].class);
~~~

Hoặc vào List lồng nhau:

~~~java
List<List<Integer>> matrix = mapper.readValue(
    json,
    new TypeReference<List<List<Integer>>>() {}
);
~~~

Với mảng các object, cấu trúc lồng nhau cũng tương tự:

~~~json
[
  [
    {"code": "A01"},
    {"code": "A02"}
  ],
  [
    {"code": "B01"}
  ]
]
~~~

~~~java
List<List<Product>> groups = mapper.readValue(
    json,
    new TypeReference<List<List<Product>>>() {}
);
~~~

Jackson đọc từng cấp theo generic type đã khai báo: cấp ngoài là List, cấp tiếp theo là List<Product>, còn từng object được chuyển thành Product. Khi ghi, cấu trúc collection lồng nhau được chuyển lại thành các mảng JSON lồng nhau.

## 6. Đọc mảng ở root và object bọc danh sách

Hai cấu trúc JSON dưới đây khác nhau:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Binh"}
]
~~~

~~~json
{
  "users": [
    {"id": 1, "name": "An"},
    {"id": 2, "name": "Binh"}
  ],
  "total": 2
}
~~~

Trường hợp thứ nhất có array ở root, vì vậy kiểu đích là User[] hoặc List<User>. Trường hợp thứ hai có object ở root với thuộc tính users là array và total là số; cần một lớp bao:

~~~java
public class User {
    private Long id;
    private String name;

    public User() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

public class UserPage {
    private List<User> users;
    private int total;

    public UserPage() {
    }

    public List<User> getUsers() {
        return users;
    }

    public void setUsers(List<User> users) {
        this.users = users;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }
}
~~~

Đọc object bọc:

~~~java
UserPage page = mapper.readValue(json, UserPage.class);
List<User> users = page.getUsers();
~~~

Không nên dùng List<User> làm kiểu đích cho JSON object bọc danh sách. Kiểu đích phải khớp với hình dạng root của JSON. Jackson không tự bỏ qua lớp bao để lấy riêng thuộc tính users.

## 7. Đọc và ghi Map có cấu trúc lồng nhau

Khi JSON có cấu trúc linh hoạt hoặc chưa có lớp Java cố định, có thể ánh xạ object thành Map:

~~~json
{
  "customer": {
    "name": "Mai",
    "vip": true
  },
  "tags": ["new", "online"]
}
~~~

Đọc thành Map:

~~~java
Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
~~~

Giá trị object con thường được biểu diễn thành Map lồng nhau, còn array thường thành List. Có thể truy cập:

~~~java
Map<String, Object> customer =
    (Map<String, Object>) data.get("customer");

String name = (String) customer.get("name");

List<String> tags = (List<String>) data.get("tags");
~~~

Vì kiểu Object không giữ thông tin cấu trúc cụ thể tại thời điểm biên dịch, thao tác ép kiểu cần thận trọng. Với dữ liệu nghiệp vụ ổn định, DTO có kiểu rõ ràng thường an toàn và dễ bảo trì hơn Map.

Nếu cần ghi Map thành JSON, có thể dùng:

~~~java
String json = mapper.writeValueAsString(data);
~~~

Jackson duyệt Map, List và các giá trị lồng nhau để tạo object hoặc array JSON tương ứng.

## 8. Generic type lồng nhau: TypeReference và JavaType

Java type erasure khiến biểu thức List.class chỉ thể hiện kiểu List, không thể hiện phần tử là User, Product hay một kiểu khác. Vì vậy, đoạn sau không cung cấp đủ thông tin generic cho Jackson:

~~~java
List<User> users = mapper.readValue(json, List.class);
~~~

Jackson chỉ biết kiểu raw List; các phần tử thường được tạo thành kiểu tổng quát như LinkedHashMap thay vì User. Khi lấy phần tử và ép kiểu sang User, ứng dụng có thể gặp ClassCastException.

### Dùng TypeReference

Với kiểu generic được biết ngay tại thời điểm viết mã, TypeReference là cách trực tiếp:

~~~java
List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);

Map<String, List<User>> usersByGroup = mapper.readValue(
    groupedJson,
    new TypeReference<Map<String, List<User>>>() {}
);
~~~

TypeReference có thể mô tả nhiều cấp generic, ví dụ Map<String, List<User>> hoặc List<Map<String, Product>>.

### Dùng JavaType khi kiểu được xây dựng động

Khi kiểu phần tử được xác định lúc chạy, có thể tạo JavaType qua TypeFactory:

~~~java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, userListType);
~~~

Với Map có giá trị là List<User>:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory
    .constructCollectionType(List.class, User.class);

JavaType groupedUsersType = typeFactory
    .constructMapType(
        Map.class,
        typeFactory.constructType(String.class),
        userListType
    );

Map<String, List<User>> groupedUsers =
    mapper.readValue(groupedJson, groupedUsersType);
~~~

JavaType hữu ích khi lớp bao hoặc kiểu phần tử được truyền vào như tham số, chẳng hạn một hàm tiện ích đọc JSON tổng quát:

~~~java
public <T> List<T> readList(String json, Class<T> elementType)
        throws JsonProcessingException {
    JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, elementType);

    return mapper.readValue(json, listType);
}
~~~

Hàm này có thể đọc List<User>, List<Product> hoặc một danh sách kiểu khác mà không cần viết riêng một TypeReference cho từng kiểu.

## 9. Generic wrapper chứa dữ liệu lồng nhau

Một API thường trả về một object bao quanh payload:

~~~json
{
  "success": true,
  "data": {
    "id": 12,
    "name": "Mai"
  }
}
~~~

Có thể mô hình hóa bằng generic class:

~~~java
public class ApiResponse<T> {
    private boolean success;
    private T data;

    public ApiResponse() {
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
~~~

Khi đọc, cần cung cấp kiểu đầy đủ ApiResponse<User>:

~~~java
ApiResponse<User> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<User>>() {}
);
~~~

Nếu data là một danh sách, kiểu cần đọc là ApiResponse<List<User>>:

~~~java
ApiResponse<List<User>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<List<User>>>() {}
);
~~~

Với kiểu động, dùng JavaType để kết hợp các cấp:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory
    .constructCollectionType(List.class, User.class);

JavaType responseType = typeFactory
    .constructParametricType(ApiResponse.class, userListType);

ApiResponse<List<User>> response =
    mapper.readValue(json, responseType);
~~~

Quy tắc chung là xây dựng JavaType từ trong ra ngoài: tạo kiểu phần tử, tạo collection chứa phần tử, rồi dùng kiểu collection làm tham số của wrapper.

## 10. Xử lý null, trường thiếu và mảng rỗng

Khi đọc dữ liệu lồng nhau, cần phân biệt các trạng thái JSON có ý nghĩa khác nhau:

~~~json
{
  "customer": null,
  "items": []
}
~~~

Ở đây customer hiện diện nhưng có giá trị null; items hiện diện và là mảng rỗng. Một JSON khác có thể bỏ hẳn thuộc tính customer hoặc items.

| JSON đầu vào | Kết quả thường gặp với DTO thông thường |
|---|---|
| Không có thuộc tính customer | Thuộc tính Java giữ giá trị mặc định, thường là null nếu chưa được khởi tạo. |
| "customer": null | Thuộc tính customer được gán null. |
| "customer": {} | Jackson tạo Customer, các thuộc tính con không có trong JSON giữ giá trị mặc định. |
| Không có thuộc tính items | List thường giữ null nếu chưa được khởi tạo. |
| "items": null | List được gán null. |
| "items": [] | List được tạo nhưng không có phần tử. |

Sự khác biệt giữa null và collection rỗng có thể quan trọng trong nghiệp vụ. Ví dụ, null có thể biểu thị dữ liệu chưa được cung cấp, còn [] biểu thị đã biết danh sách hiện không có phần tử.

Nếu muốn thuộc tính danh sách mặc định là rỗng khi JSON không truyền trường đó, có thể khởi tạo trong DTO:

~~~java
public class Order {
    private List<OrderItem> items = new ArrayList<>();

    public List<OrderItem> getItems() {
        return items;
    }

    public void setItems(List<OrderItem> items) {
        this.items = items;
    }
}
~~~

Với cách này, trường items bị thiếu thường giữ danh sách rỗng đã khởi tạo; nếu JSON truyền rõ items: null, setter vẫn có thể nhận null. Nếu muốn chuẩn hóa cả trường hợp null, cần xử lý trong setter, constructor hoặc tầng nghiệp vụ theo yêu cầu của ứng dụng.

## 11. Đổi tên thuộc tính và annotation trong cấu trúc lồng nhau

Tên thuộc tính của các lớp con cũng tuân theo quy tắc ánh xạ của Jackson. Ví dụ JSON dùng snake_case:

~~~json
{
  "order_id": 501,
  "shipping_address": {
    "postal_code": "700000"
  }
}
~~~

Có thể dùng naming strategy chung:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Các thuộc tính orderId, shippingAddress và postalCode có thể được ánh xạ với order_id, shipping_address và postal_code. Quy tắc này áp dụng trong quá trình khám phá thuộc tính cho các kiểu con được Jackson xử lý.

Nếu chỉ một thuộc tính có tên khác, dùng @JsonProperty:

~~~java
public class Order {
    @JsonProperty("order_id")
    private Long orderId;

    // Các thuộc tính khác
}
~~~

Nếu API có nhiều tên cũ cho cùng một trường khi đọc, có thể dùng @JsonAlias:

~~~java
public class Customer {
    @JsonAlias({"customer_name", "full_name"})
    private String name;

    // Getter và setter
}
~~~

@JsonAlias chấp nhận các tên thay thế khi đọc; khi ghi, Jackson vẫn sử dụng tên thuộc tính chính theo quy tắc ánh xạ hiện tại.

## 12. Đối tượng bất biến và record lồng nhau

DTO không nhất thiết phải có setter. Với lớp bất biến, có thể dùng @JsonCreator và @JsonProperty để chỉ rõ constructor mà Jackson dùng:

~~~java
public class Coordinates {
    private final double latitude;
    private final double longitude;

    @JsonCreator
    public Coordinates(
            @JsonProperty("latitude") double latitude,
            @JsonProperty("longitude") double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public double getLatitude() {
        return latitude;
    }

    public double getLongitude() {
        return longitude;
    }
}
~~~

Lớp cha có thể chứa Coordinates như một thuộc tính bình thường:

~~~java
public class Place {
    private String name;
    private Coordinates coordinates;

    public Place() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Coordinates getCoordinates() {
        return coordinates;
    }

    public void setCoordinates(Coordinates coordinates) {
        this.coordinates = coordinates;
    }
}
~~~

Với Jackson 2.12 trở lên, Java record được hỗ trợ trực tiếp trong các phiên bản phù hợp:

~~~java
public record Coordinates(double latitude, double longitude) {
}

public record Place(String name, Coordinates coordinates) {
}
~~~

Jackson ánh xạ các thành phần record theo tên component. Khi dự án dùng phiên bản Jackson cũ hoặc có cấu hình đặc biệt, cần kiểm tra khả năng hỗ trợ record và cách Jackson chọn creator tương ứng.

## 13. Mảng và collection chứa kiểu đa hình

Một mảng có thể chứa các đối tượng thuộc những lớp con khác nhau của cùng một kiểu cha. Khi đó, chỉ khai báo List<Payment> có thể chưa đủ để Jackson biết phải tạo lớp con nào nếu JSON không có thông tin phân biệt.

Ví dụ mô hình:

~~~java
public abstract class Payment {
    private double amount;

    public double getAmount() {
        return amount;
    }

    public void setAmount(double amount) {
        this.amount = amount;
    }
}

public class CardPayment extends Payment {
    private String cardLast4;

    public String getCardLast4() {
        return cardLast4;
    }

    public void setCardLast4(String cardLast4) {
        this.cardLast4 = cardLast4;
    }
}

public class CashPayment extends Payment {
    private String currency;

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Có thể dùng @JsonTypeInfo và @JsonSubTypes để thêm discriminator:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "type"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = CashPayment.class, name = "cash")
})
public abstract class Payment {
    // Các thuộc tính chung
}
~~~

JSON:

~~~json
[
  {
    "type": "card",
    "amount": 120.0,
    "cardLast4": "1234"
  },
  {
    "type": "cash",
    "amount": 50.0,
    "currency": "VND"
  }
]
~~~

Khi đọc vào List<Payment>, discriminator type cho biết lớp con cần tạo cho từng phần tử:

~~~java
List<Payment> payments = mapper.readValue(
    json,
    new TypeReference<List<Payment>>() {}
);
~~~

Thông tin subtype phải được thiết kế có kiểm soát và phù hợp với dữ liệu tin cậy của ứng dụng. Không nên bật cơ chế nhận diện kiểu đa hình rộng theo tên lớp tùy ý từ JSON bên ngoài.

## 14. Dùng JsonNode khi cấu trúc chưa cố định

Nếu chưa biết trước cấu trúc hoặc chỉ cần đọc một phần của JSON lồng nhau, có thể dùng tree model:

~~~java
JsonNode root = mapper.readTree(json);

JsonNode customerName = root.path("customer").path("name");
if (!customerName.isMissingNode() && !customerName.isNull()) {
    System.out.println(customerName.asText());
}

JsonNode items = root.path("items");
if (items.isArray()) {
    for (JsonNode item : items) {
        System.out.println(item.path("name").asText());
    }
}
~~~

JsonNode cho phép duyệt object bằng tên thuộc tính và duyệt array bằng vòng lặp hoặc chỉ số. Phương thức path trả về MissingNode khi đường dẫn không tồn tại, giúp tránh lỗi null khi truy cập từng cấp. Khi cấu trúc đã rõ, có thể chuyển node sang kiểu Java:

~~~java
JsonNode root = mapper.readTree(json);
Order order = mapper.treeToValue(root, Order.class);
~~~

Tree model phù hợp với dữ liệu linh hoạt, thao tác một vài trường hoặc xử lý JSON có schema thay đổi. DTO có kiểu rõ ràng phù hợp hơn khi cấu trúc ổn định và cần kiểm soát kiểu dữ liệu ở compile time.

## 15. Đọc mảng lớn theo từng phần tử

Khi JSON chứa mảng rất lớn, đọc toàn bộ thành List có thể tiêu tốn nhiều bộ nhớ vì toàn bộ object và collection cùng tồn tại trong heap. Jackson cung cấp ObjectReader và MappingIterator để đọc tuần tự từng phần tử:

~~~java
ObjectReader productReader = mapper.readerFor(Product.class);

try (MappingIterator<Product> iterator =
         productReader.readValues(inputStream)) {
    while (iterator.hasNextValue()) {
        Product product = iterator.nextValue();
        process(product);
    }
}
~~~

Ví dụ này giả định inputStream chứa chuỗi các giá trị JSON mà reader có thể đọc tuần tự, thường là một JSON array khi dùng cấu hình mặc định phù hợp. MappingIterator cho phép xử lý từng phần tử mà không cần giữ toàn bộ danh sách trong bộ nhớ.

Nếu ứng dụng chỉ cần ghi nhiều phần tử ra output mà không cần tạo một collection lớn, có thể dùng JsonGenerator để ghi từng phần tử theo luồng. Đây là cách tiếp cận streaming ở tầng parser/generator, phù hợp với dữ liệu lớn hoặc pipeline xử lý tuần tự.

## 16. Lựa chọn kiểu Java theo cấu trúc JSON

| Cấu trúc JSON | Kiểu Java thường dùng | Ví dụ kiểu đích |
|---|---|---|
| Object | Một lớp DTO | Order.class |
| Object lồng nhau | DTO có thuộc tính kiểu DTO khác | Shipment.class |
| Array các giá trị đơn | Array hoặc List | int[].class, List<String> |
| Array các object | Array hoặc List có kiểu phần tử | Product[].class, List<Product> |
| Array lồng nhau | Mảng nhiều chiều hoặc collection lồng nhau | int[][].class, List<List<Integer>> |
| Object với key động | Map | Map<String, Object> |
| Generic wrapper | TypeReference hoặc JavaType đầy đủ | ApiResponse<User> |
| Cấu trúc chưa biết trước | JsonNode | JsonNode.class |
| Mảng rất lớn cần xử lý tuần tự | MappingIterator | ObjectReader cho kiểu phần tử |

Khi đọc, kiểu đích phải khớp với cấu trúc ở root. Nếu root là array, dùng array hoặc collection; nếu root là object có thuộc tính chứa array, dùng DTO hoặc Map tương ứng. Với generic lồng nhau, truyền TypeReference hoặc JavaType để Jackson biết chính xác kiểu phần tử ở từng cấp.

## 17. Một ví dụ hoàn chỉnh đọc và ghi dữ liệu lồng nhau

Ví dụ sau kết hợp object con, List phần tử và generic type khi cần đọc response:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

public class OrderExample {

    public static void main(String[] args) throws Exception {
        String json = """
            {
              "orderId": 501,
              "customer": {
                "id": 12,
                "name": "Mai"
              },
              "items": [
                {
                  "productId": "P01",
                  "name": "Keyboard",
                  "quantity": 2
                },
                {
                  "productId": "P02",
                  "name": "Mouse",
                  "quantity": 1
                }
              ]
            }
            """;

        ObjectMapper mapper = new ObjectMapper();

        Order order = mapper.readValue(json, Order.class);

        System.out.println(order.getCustomer().getName());
        System.out.println(order.getItems().size());

        String outputJson = mapper
            .writerWithDefaultPrettyPrinter()
            .writeValueAsString(order);

        System.out.println(outputJson);

        String itemArrayJson = mapper.writeValueAsString(order.getItems());
        List<OrderItem> items = mapper.readValue(
            itemArrayJson,
            new TypeReference<List<OrderItem>>() {}
        );

        System.out.println(items.get(0).getProductId());
    }
}
~~~

Trong ví dụ:

1. Order.class mô tả object ở root.
2. Thuộc tính customer cho Jackson biết kiểu Customer của object con.
3. Thuộc tính items khai báo List<OrderItem>, cho biết kiểu của từng phần tử trong array.
4. writerWithDefaultPrettyPrinter() tạo JSON có định dạng dễ đọc mà không phải thay đổi cấu hình dùng chung của mapper.
5. Khi đọc riêng JSON array thành List<OrderItem>, TypeReference giữ thông tin generic type để Jackson tạo đúng kiểu phần tử.

Với cấu trúc lồng nhau, Jackson thực hiện việc chuyển đổi theo kiểu Java đã khai báo. Thiết kế DTO phản ánh đúng object và array ở từng cấp, đồng thời cung cấp đầy đủ thông tin generic, là nền tảng để đọc và ghi JSON một cách rõ ràng và ổn định.

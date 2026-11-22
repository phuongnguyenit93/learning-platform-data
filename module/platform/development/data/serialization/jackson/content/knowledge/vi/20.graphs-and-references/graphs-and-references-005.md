# Biểu diễn định danh đối tượng bằng JsonIdentityInfo

Một đồ thị object Java có thể chứa nhiều tham chiếu đến cùng một instance, hoặc có quan hệ vòng lặp giữa các object. Ví dụ, một User có nhiều Order, mỗi Order lại tham chiếu về User sở hữu nó. Nếu serialize theo cách bean thông thường, Jackson có thể lặp lại dữ liệu hoặc gặp vòng tham chiếu không thể kết thúc.

Jackson cung cấp annotation @JsonIdentityInfo để biểu diễn định danh của object trong JSON. Khi một object được gặp lần đầu, Jackson ghi đầy đủ object cùng định danh của nó. Khi cùng object được tham chiếu lại, Jackson có thể ghi một giá trị ID thay cho toàn bộ object. Khi deserialize, Jackson dùng ID để liên kết các tham chiếu về cùng một instance.

Cơ chế này hữu ích khi cần giữ cấu trúc đồ thị, xử lý quan hệ hai chiều hoặc tránh lặp dữ liệu trong payload. Tuy nhiên, object identity trong Jackson là cơ chế liên kết object trong quá trình serialize/deserialize; nó không tự truy vấn database, không thay thế khóa chính của ORM và cũng không tự định nghĩa hợp đồng liên kết giữa nhiều tài liệu JSON độc lập.

## 1. Object graph và vấn đề tham chiếu lặp

Một object graph là tập hợp object có liên kết tham chiếu với nhau. Các liên kết có thể tạo thành cây, đồ thị có chia sẻ node hoặc đồ thị có chu trình.

Ví dụ mô hình User và Order:

~~~java
public class User {
    public Long id;
    public String name;
    public List<Order> orders = new ArrayList<>();
}

public class Order {
    public Long id;
    public String number;
    public User owner;
}
~~~

Một User có thể sở hữu nhiều Order. Mỗi Order giữ tham chiếu ngược đến chính User đó.

Đồ thị trong bộ nhớ:

~~~text
User#1
  |
  +---- orders ----> Order#101
  |                    |
  |                    +---- owner ----+
  |                                    |
  +------------------------------------+
                       |
                       +----> Order#102
                                |
                                +---- owner ----> User#1
~~~

Đây là đồ thị có chu trình. Nếu Jackson serialize User rồi đi vào orders, nó serialize Order. Khi đi tới owner, lại gặp User ban đầu. Nếu không có chính sách xử lý tham chiếu vòng, serializer có thể tiếp tục đi sâu, lặp dữ liệu hoặc báo lỗi self-reference tùy cấu trúc và cấu hình.

Một vấn đề khác là cùng một object có thể được tham chiếu từ nhiều nơi mà không tạo chu trình. Nếu mỗi lần gặp đều serialize toàn bộ object, JSON sẽ lặp dữ liệu và khi đọc lại có thể tạo nhiều instance độc lập thay vì một instance được chia sẻ.

## 2. @JsonIdentityInfo giải quyết điều gì?

@JsonIdentityInfo đánh dấu kiểu object có định danh. Jackson dùng một object ID để nhận diện instance trong quá trình serialize và deserialize.

Mô hình tổng quát:

~~~text
Lần đầu gặp object
       |
       v
Ghi object đầy đủ + object ID
       |
       v
Gặp lại cùng object
       |
       v
Ghi giá trị ID thay cho object
       |
       v
Deserialize: tra ID và liên kết về instance
~~~

Ví dụ JSON có thể được biểu diễn như sau:

~~~json
{
  "id": 1,
  "name": "An",
  "orders": [
    {
      "id": 101,
      "number": "ORD-101",
      "owner": 1
    }
  ]
}
~~~

User được ghi đầy đủ ở lần đầu. Khi Order.owner tham chiếu lại User đã được ghi, Jackson chỉ ghi ID 1.

Lợi ích:

- Ngăn việc mở rộng đệ quy vô hạn trong đồ thị có chu trình.
- Giảm lặp dữ liệu khi nhiều property tham chiếu cùng một object.
- Có thể giữ quan hệ identity khi deserialize.
- Biểu diễn được object graph phức tạp hơn cây JSON thông thường.

@JsonIdentityInfo không làm JSON trở thành một định dạng tham chiếu tự mô tả độc lập. Consumer phải hiểu rằng một giá trị ID tại vị trí được định nghĩa là tham chiếu tới object đã có định danh tương ứng.

## 3. Dùng PropertyGenerator với ID có sẵn

Nếu object đã có thuộc tính định danh như id, có thể dùng ObjectIdGenerators.PropertyGenerator.

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = User.class
)
public class User {
    public Long id;
    public String name;
    public List<Order> orders = new ArrayList<>();
}
~~~

Order cũng có thể có identity riêng:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Order.class
)
public class Order {
    public Long id;
    public String number;
    public User owner;
}
~~~

Với dữ liệu:

~~~java
User user = new User();
user.id = 1L;
user.name = "An";

Order order = new Order();
order.id = 101L;
order.number = "ORD-101";
order.owner = user;

user.orders.add(order);
~~~

Serialize User:

~~~java
String json = mapper.writeValueAsString(user);
~~~

Một biểu diễn điển hình:

~~~json
{
  "id": 1,
  "name": "An",
  "orders": [
    {
      "id": 101,
      "number": "ORD-101",
      "owner": 1
    }
  ]
}
~~~

PropertyGenerator lấy giá trị từ property đã có. Property được chỉ định phải tồn tại trong mô hình Jackson nhìn thấy và phải có giá trị định danh ổn định khi cần tạo tham chiếu.

### 3.1. ID phải duy nhất trong phạm vi identity

Nếu hai object khác nhau cùng có ID 1 nhưng được xem là cùng một identity namespace, Jackson có thể liên kết sai hoặc phát hiện xung đột tùy quá trình xử lý.

Vì vậy:

- ID phải duy nhất trong phạm vi object type/scope đã chọn.
- Không dùng null làm ID cho các object cần tham chiếu.
- Không tái sử dụng ID cho hai instance khác nhau trong cùng graph.
- Giá trị ID cần ổn định trong suốt quá trình serialize/deserialize.
- Property ID phải được serialize hoặc được cung cấp theo hợp đồng để consumer có thể giải quyết tham chiếu.

Với entity có khóa database, PropertyGenerator thường tự nhiên vì id đã là một phần của mô hình. Nhưng uniqueness trong database và uniqueness trong JSON identity scope cần được hiểu đúng. Nếu nhiều loại entity dùng chung một generator và scope, hãy phân tách scope hoặc namespace.

### 3.2. Dùng scope để tách không gian ID

Thuộc tính scope của @JsonIdentityInfo giúp xác định phạm vi identity. Mặc định là Object.class. Có thể đặt scope theo kiểu:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = User.class
)
public class User {
    public Long id;
}
~~~

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Order.class
)
public class Order {
    public Long id;
}
~~~

Điều này đặc biệt hữu ích khi User#1 và Order#1 có cùng giá trị số nhưng là hai object khác nhau.

Không nên tùy tiện đặt cùng scope cho nhiều loại object có thể dùng chung giá trị ID. Thiết kế namespace rõ ràng giúp tránh tham chiếu nhầm.

## 4. Dùng ID do Jackson sinh ra

Không phải object nào cũng có khóa định danh sẵn. Jackson có thể sinh object ID bằng generator.

Ví dụ dùng IntSequenceGenerator:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.IntSequenceGenerator.class,
    property = "objectId"
)
public class GraphNode {
    public String label;
    public GraphNode next;
}
~~~

JSON có thể chứa ID do Jackson tạo:

~~~json
{
  "objectId": 1,
  "label": "A",
  "next": {
    "objectId": 2,
    "label": "B",
    "next": 1
  }
}
~~~

ID sinh ra phục vụ việc nhận diện object trong lần serialize đó. Nó không phải ID database và không nên được xem là mã định danh lâu dài giữa nhiều lần xuất dữ liệu.

Một số generator thường dùng:

| Generator | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| PropertyGenerator | Dùng property có sẵn trên object | Entity/value object đã có ID |
| IntSequenceGenerator | Sinh ID số theo sequence | Đồ thị tạm thời không có ID tự nhiên |
| UUIDGenerator | Sinh UUID | Cần ID khó trùng trong graph |
| StringIdGenerator | Sinh ID dạng chuỗi theo cơ chế generator | Hợp đồng yêu cầu string identifier |

Khi dùng generator sinh ID, property được chọn làm nơi ghi ID có thể là metadata được Jackson thêm vào output. Hãy kiểm tra JSON thực tế và thống nhất tên property với consumer.

Nếu cần deserialize lại payload, ID được sinh phải có mặt trong JSON và các reference phải dùng đúng giá trị đó. Không lấy sequence ID trong một document làm khóa để tra cứu entity ở lần gọi API sau.

## 5. Object ID được ghi như thế nào?

Mặc định, khi object được serialize lần đầu, Jackson ghi đầy đủ object cùng ID. Khi gặp lại object đã được nhận diện, nó ghi ID thay cho object.

Ví dụ cùng một Address được tham chiếu từ hai đơn hàng:

~~~java
Address sharedAddress = new Address();
sharedAddress.id = 55L;
sharedAddress.city = "Hanoi";

Order first = new Order();
first.id = 101L;
first.shippingAddress = sharedAddress;

Order second = new Order();
second.id = 102L;
second.shippingAddress = sharedAddress;
~~~

Nếu Address dùng @JsonIdentityInfo với PropertyGenerator, JSON có thể biểu diễn:

~~~json
[
  {
    "id": 101,
    "shippingAddress": {
      "id": 55,
      "city": "Hanoi"
    }
  },
  {
    "id": 102,
    "shippingAddress": 55
  }
]
~~~

Địa chỉ được ghi đầy đủ lần đầu. Lần tham chiếu thứ hai chỉ cần ID.

Điều này có thể giảm kích thước payload đáng kể khi object dùng chung xuất hiện ở nhiều vị trí. Nó cũng giúp deserializer liên kết các vị trí về cùng một instance thay vì tạo các bản sao độc lập, miễn là tham chiếu được giải quyết trong cùng quá trình binding.

### 5.1. Identity dựa trên object graph, không phải equals()

Cần phân biệt object identity với equals/hashCode.

Hai instance có thể có cùng dữ liệu và equals() trả true, nhưng vẫn là hai object khác nhau trong bộ nhớ. Ngược lại, cùng một instance có thể xuất hiện ở nhiều property.

Jackson dùng cơ chế object ID để quản lý tham chiếu theo generator và ID được cấu hình. Không nên dựa vào equals() để suy luận rằng hai object sẽ tự động được gộp thành một identity.

Nếu tạo hai instance User riêng biệt nhưng cùng ID 1, đó là xung đột định danh trong graph chứ không phải cách hợp lệ để biểu diễn hai object độc lập. Hãy bảo đảm mỗi ID đại diện duy nhất cho một object trong scope.

## 6. Dùng @JsonIdentityReference(alwaysAsId = true)

@JsonIdentityInfo quy định object có identity. @JsonIdentityReference có thể thay đổi cách một property tham chiếu object đó được serialize.

Khi đặt alwaysAsId = true, property luôn được biểu diễn bằng ID, kể cả khi object chưa được ghi đầy đủ tại vị trí đó.

Ví dụ:

~~~java
public class OrderSummary {
    public Long id;

    @JsonIdentityReference(alwaysAsId = true)
    public Customer customer;
}
~~~

Customer cần có @JsonIdentityInfo:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Customer.class
)
public class Customer {
    public Long id;
    public String name;
}
~~~

OrderSummary có thể serialize thành:

~~~json
{
  "id": 101,
  "customer": 7
}
~~~

Thay vì nhúng toàn bộ Customer.

### 6.1. Chỉ dùng alwaysAsId khi consumer có thể giải quyết ID

Khi alwaysAsId = true, payload có thể chỉ chứa một ID mà không có object definition đầy đủ ở nơi khác trong document.

Điều đó có nghĩa deserializer cần có object tương ứng đã được đăng ký trong cùng graph hoặc có resolver tùy chỉnh có khả năng tìm object. Nếu không có definition hoặc resolver phù hợp, Jackson không thể tự đoán Customer#7 là ai.

Không nên bật alwaysAsId trên mọi property chỉ để JSON ngắn hơn. Hãy bảo đảm hợp đồng chỉ rõ nguồn cung cấp object definition và cơ chế resolve.

### 6.2. Mặc định và alwaysAsId khác nhau

| Cách dùng | Lần đầu gặp object | Tham chiếu lặp |
|---|---|---|
| Chỉ @JsonIdentityInfo | Ghi object đầy đủ và ID | Ghi ID |
| @JsonIdentityReference(alwaysAsId = true) | Ghi ID | Ghi ID |
| Không dùng identity | Ghi object theo property thông thường | Có thể lặp dữ liệu hoặc gặp vòng tham chiếu |

@JsonIdentityReference có thể đặt trên property cụ thể để một quan hệ luôn là ID, trong khi các vị trí khác vẫn có thể ghi object đầy đủ lần đầu.

## 7. Deserialize object và tham chiếu ID

Khi đọc JSON có identity, Jackson phải thực hiện hai việc:

1. Khi gặp object đầy đủ, tạo instance và đăng ký object ID.
2. Khi gặp giá trị ID ở vị trí tham chiếu, tìm instance đã đăng ký và gán vào property.

Ví dụ JSON:

~~~json
{
  "id": 1,
  "name": "An",
  "orders": [
    {
      "id": 101,
      "number": "ORD-101",
      "owner": 1
    }
  ]
}
~~~

Code:

~~~java
User user = mapper.readValue(json, User.class);

Order order = user.orders.get(0);

assertSame(user, order.owner);
~~~

assertSame kiểm tra hai tham chiếu trỏ tới đúng cùng một instance Java. Đây là điều khác với assertEquals, vốn chỉ kiểm tra equality theo equals().

Nếu identity được cấu hình đúng và reference được giải quyết trong cùng quá trình deserialize, Order.owner trỏ lại User đã tạo ở root.

### 7.1. Tham chiếu phải có object definition

Một JSON chỉ có:

~~~json
{
  "customer": 7
}
~~~

không đủ để tạo Customer nếu không có object definition hoặc resolver cung cấp Customer#7.

Jackson có thể báo lỗi unresolved object ID khi không tìm được ID tương ứng. Đây là hành vi đúng: một tham chiếu không có đích không thể trở thành object hợp lệ một cách tự động.

Nếu API chỉ muốn truyền customerId để service truy vấn database, hãy dùng DTO có field customerId thay vì giả định @JsonIdentityInfo sẽ tự tải entity.

### 7.2. Tham chiếu xuất hiện trước object definition

Một số cấu trúc graph có thể gặp reference trước object đầy đủ. Jackson có hỗ trợ cơ chế deferred resolution cho một số forward reference trong quá trình databind, nhưng khả năng xử lý phụ thuộc ngữ cảnh property/container và resolver.

Không nên dựa vào forward reference một cách tùy tiện. Cách đơn giản và dễ tương thích hơn là serialize object definition trước các reference đến nó. Nếu hợp đồng bắt buộc cho phép thứ tự tùy ý, hãy viết test cho đúng cấu trúc và phiên bản Jackson đang sử dụng.

Nếu ID vẫn chưa được định nghĩa khi quá trình deserialize hoàn tất, lỗi unresolved reference có thể xảy ra.

## 8. ObjectIdResolver và phạm vi giải quyết ID

Jackson dùng ObjectIdResolver để quản lý việc liên kết ID với object trong quá trình deserialize.

Resolver mặc định thường phù hợp với object graph trong một lần đọc JSON. Nó không phải repository và không tự gọi database.

Một resolver có thể:

- Lưu mapping từ object ID đến instance đã tạo.
- Kiểm tra ID trùng.
- Tra cứu tham chiếu trong phạm vi deserialize.
- Định nghĩa chính sách bind/resolve theo hợp đồng.

@JsonIdentityInfo cho phép chỉ định resolver:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    resolver = SimpleObjectIdResolver.class,
    scope = Customer.class
)
public class Customer {
    public Long id;
    public String name;
}
~~~

Trong phần lớn trường hợp, resolver mặc định đủ dùng. Chỉ triển khai resolver riêng khi có yêu cầu rõ ràng, chẳng hạn liên kết với một identity map được quản lý trong một phiên xử lý.

### 8.1. Vì sao resolver không phải ORM?

Giả sử JSON chứa customer ID 7. ObjectIdResolver mặc định không có nghĩa là Jackson sẽ gọi:

~~~java
customerRepository.findById(7L)
~~~

Jackson không biết repository, transaction hay quy tắc authorization của ứng dụng. Identity resolver chỉ giải quyết mối liên hệ giữa ID và object theo cơ chế Jackson được cấu hình.

Nếu muốn ID trong JSON tham chiếu tới entity đã lưu, hãy dùng DTO chứa ID rồi thực hiện lookup ở service:

~~~java
public record OrderRequest(Long customerId, List<OrderLineRequest> lines) {}
~~~

Service có thể kiểm tra quyền truy cập và tìm Customer:

~~~java
Customer customer = customerRepository.findById(request.customerId())
    .orElseThrow(CustomerNotFoundException::new);
~~~

Cách này giữ database access và authorization ở tầng nghiệp vụ.

## 9. Identity trong nhiều loại object

Khi graph có nhiều loại entity cùng dùng ID số, hãy định nghĩa identity namespace rõ ràng.

Ví dụ:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Customer.class
)
public class Customer {
    public Long id;
    public String name;
}

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Product.class
)
public class Product {
    public Long id;
    public String sku;
}
~~~

Customer#10 và Product#10 là hai object khác nhau. Scope giúp phân biệt hai không gian định danh.

Trong một hierarchy kế thừa, cần quyết định identity được định nghĩa ở base class hay từng subtype. Nếu mọi subtype chia sẻ một ID namespace, có thể dùng scope chung. Nếu mỗi subtype có ID riêng, hãy thiết kế scope và generator tương ứng.

Không nên gắn identity annotations tùy tiện ở cả base và subtype với các quy tắc xung đột. Hãy kiểm tra chính xác kiểu khai báo của property và kiểu runtime của instance trong test.

## 10. Identity và quan hệ hai chiều trong domain model

Một ví dụ thường gặp là Parent có danh sách Child, Child có tham chiếu ngược Parent.

Không có identity, object graph có chu trình:

~~~text
Parent
  |
  +---- children ----> Child
                         |
                         +---- parent ----> Parent
~~~

Với identity:

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Parent.class
)
public class Parent {
    public Long id;
    public String name;
    public List<Child> children = new ArrayList<>();
}

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id",
    scope = Child.class
)
public class Child {
    public Long id;
    public String name;
    public Parent parent;
}
~~~

JSON có thể là:

~~~json
{
  "id": 1,
  "name": "Parent A",
  "children": [
    {
      "id": 11,
      "name": "Child A",
      "parent": 1
    },
    {
      "id": 12,
      "name": "Child B",
      "parent": 1
    }
  ]
}
~~~

Parent được ghi đầy đủ ở root. Mỗi Child ghi đầy đủ ở lần đầu; parent của child là ID 1.

Cơ chế này giữ được liên kết ngược mà không cần lặp toàn bộ Parent bên trong từng Child.

## 11. So sánh @JsonIdentityInfo với managed/back reference

Jackson còn có @JsonManagedReference và @JsonBackReference để xử lý quan hệ hai chiều dạng parent-child.

| Cơ chế | Cách biểu diễn | Giữ shared identity tổng quát? | JSON reference bằng ID? |
|---|---|---:|---:|
| @JsonIdentityInfo | Object đầy đủ lần đầu, sau đó tham chiếu bằng ID | Có | Có |
| @JsonManagedReference / @JsonBackReference | Serialize phía managed, bỏ phía back | Không phải mục tiêu chính | Không |
| @JsonIgnore | Bỏ property được đánh dấu | Không | Không |
| DTO chỉ chứa ID | Ứng dụng tự thiết kế liên kết | Tùy mô hình | Có thể |

Managed/back reference phù hợp với một quan hệ cha-con có hướng: parent chứa children, còn child không cần serialize parent ngược lại. Khi deserialize, Jackson có thể gán lại liên kết back reference.

@JsonIdentityInfo phù hợp hơn khi cần giữ nhiều tham chiếu, object dùng chung ở nhiều vị trí hoặc graph có chu trình phức tạp hơn.

@JsonIgnore đơn giản nhất nếu quan hệ ngược không cần xuất hiện trong API. DTO có ID tường minh thường dễ kiểm soát nhất cho API công khai, vì consumer không phải hiểu quy tắc object identity của Jackson.

## 12. Identity không phải cách thay thế DTO API

Có thể dùng @JsonIdentityInfo trên JPA entity để tránh lặp dữ liệu, nhưng điều đó không có nghĩa entity graph là hợp đồng API tốt.

Một entity có thể chứa:

- Lazy collection.
- Proxy do ORM tạo.
- Quan hệ nội bộ không được phép công khai.
- Field nhạy cảm.
- Quan hệ rất lớn hoặc có thể tải vô hạn.
- Vòng đời gắn với persistence context.

Serialize trực tiếp entity có identity vẫn có thể kích hoạt lazy loading, lộ field hoặc tạo payload quá lớn. Jackson không thay thế việc thiết kế DTO và kiểm soát dữ liệu được phép công bố.

Với API công khai, thường nên:

1. Chọn dữ liệu được phép trả về.
2. Tạo DTO response.
3. Dùng ID scalar cho quan hệ cần liên kết.
4. Chỉ dùng @JsonIdentityInfo nếu consumer thực sự cần object graph có identity trong cùng payload.

## 13. Identity và tham chiếu giữa nhiều JSON document

Mặc định, object ID được quản lý trong phạm vi một lần serialize/deserialize và resolver/context tương ứng. Không nên giả định một ID trong file A sẽ tự động tham chiếu tới object được khai báo trong file B.

Ví dụ hai payload độc lập:

File A:
~~~json
{
  "id": 7,
  "name": "An"
}
~~~

File B:
~~~json
{
  "customer": 7
}
~~~

Nếu đọc File B trong một lần deserialize riêng, Jackson không tự biết Customer#7 từ File A. Muốn giải quyết tham chiếu liên tài liệu, ứng dụng phải có một cơ chế ngoài như:

- DTO chứa customerId rồi service tra cứu.
- Registry/identity map được quản lý theo phiên.
- Custom ObjectIdResolver với lifecycle và nguồn dữ liệu rõ.
- API trả đầy đủ object ở nơi cần thiết.

Đừng coi @JsonIdentityInfo là cơ chế liên kết toàn cục giữa các request hoặc giữa các file.

## 14. Khi nào dùng generator tự sinh và khi nào dùng property ID?

| Nhu cầu | Lựa chọn |
|---|---|
| Entity đã có khóa ổn định | PropertyGenerator |
| DTO graph tạm thời không có ID | IntSequenceGenerator hoặc UUIDGenerator |
| Consumer cần tham chiếu lại object trong cùng payload | @JsonIdentityInfo |
| Consumer chỉ cần database key để gọi API khác | DTO chứa ID scalar |
| ID trùng giữa các loại object | Đặt scope/namespace riêng |
| Cần object luôn xuất thành ID | @JsonIdentityReference(alwaysAsId = true) với resolver/definition rõ |
| Cần tham chiếu giữa nhiều document | Resolver hoặc lookup do ứng dụng quản lý |

PropertyGenerator thường phù hợp với entity có ID ổn định. Generator tự sinh phù hợp khi chỉ cần ID nội bộ cho một lần serialize. Nếu ID được consumer lưu lại hoặc dùng qua nhiều API, cần mã định danh ổn định do hợp đồng quản lý.

## 15. Những lỗi thường gặp khi dùng JsonIdentityInfo

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Không tìm thấy object ID khi deserialize | Có reference nhưng không có object definition hoặc resolver | Đưa definition vào graph hoặc cung cấp resolver phù hợp |
| Hai object bị liên kết nhầm | ID trùng trong cùng scope | Bảo đảm ID duy nhất và tách scope |
| ID property không được tìm thấy | Sai tên property hoặc property không được Jackson nhìn thấy | Kiểm tra tên, getter/field và annotation |
| Reference xuất hiện trước definition gây lỗi | Forward reference không được giải quyết trong ngữ cảnh đó | Sắp xếp definition trước hoặc test resolver/context |
| JSON có scalar ID nhưng consumer mong object | Hợp đồng reference chưa được thể hiện trong DTO | Dùng identity-aware base type hoặc DTO chứa ID |
| Payload chỉ có ID nhưng không có object | alwaysAsId được bật mà không có resolver/definition | Chỉ dùng khi consumer có nguồn resolve |
| ID sequence thay đổi giữa các lần export | Generator sinh ID tạm thời | Dùng property ID ổn định nếu cần persistence |
| Entity graph tải quá nhiều dữ liệu | Serialize trực tiếp entity/proxy | Dùng DTO và kiểm soát fetch |
| @JsonIdentityInfo không giải quyết tham chiếu liên file | Resolver mặc định chỉ có phạm vi context | Dùng lookup hoặc resolver có lifecycle rõ |
| Vòng lặp vẫn xảy ra ở kiểu khác | Chỉ một số type có identity | Xác định mọi type trong chu trình cần identity hoặc dùng DTO |

## 16. Kiểm thử serialization và object identity

Không chỉ kiểm tra JSON có đúng nội dung. Cần kiểm tra object reference sau deserialize có trỏ về cùng instance hay không.

Ví dụ:

~~~java
@Test
void preservesBackReferenceUsingObjectIdentity() throws Exception {
    User user = new User();
    user.id = 1L;
    user.name = "An";

    Order order = new Order();
    order.id = 101L;
    order.number = "ORD-101";
    order.owner = user;

    user.orders.add(order);

    String json = mapper.writeValueAsString(user);

    User restored = mapper.readValue(json, User.class);

    assertEquals(1L, restored.id);
    assertEquals(1, restored.orders.size());
    assertSame(restored, restored.orders.get(0).owner);
}
~~~

assertSame là kiểm tra quan trọng: nó xác nhận Jackson đã liên kết Order.owner về đúng instance User ở root.

### 16.1. Test ID được ghi đúng

~~~java
@Test
void writesObjectIdAndReference() throws Exception {
    User user = new User();
    user.id = 1L;
    user.name = "An";

    Order order = new Order();
    order.id = 101L;
    order.owner = user;

    user.orders = List.of(order);

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(user)
    );

    assertEquals(1, json.path("id").asInt());
    assertEquals(
        1,
        json.path("orders").get(0).path("owner").asInt()
    );
}
~~~

Test này xác nhận reference được biểu diễn bằng scalar ID theo hợp đồng đã chọn.

### 16.2. Test ID trùng và reference không tồn tại

Nên kiểm thử:

- Hai object khác nhau dùng cùng ID trong một scope.
- Reference trỏ tới ID không được định nghĩa.
- ID null hoặc thiếu khi dùng PropertyGenerator.
- Cùng ID ở hai scope khác nhau.
- Forward reference nếu hợp đồng cho phép.
- Identity trong List và Map.
- alwaysAsId khi object definition xuất hiện ở vị trí khác.
- Resolver tùy chỉnh nếu có.

### 16.3. Test round-trip chưa đủ

Một bài test serialize rồi deserialize thành công chưa chứng minh payload phù hợp với client. Hãy kiểm tra JSON literal hoặc cấu trúc JsonNode:

- Lần đầu object được ghi đầy đủ.
- Reference sau đó là ID.
- Tên property ID đúng.
- Giá trị ID có kiểu mong muốn.
- Không có field nội bộ bị xuất ra ngoài.
- Các quan hệ được liên kết lại bằng assertSame.

## 17. Quy trình thiết kế object identity cho một graph

1. Xác định graph có chu trình hoặc nhiều property dùng chung một object không.
2. Xác định consumer có cần giữ shared identity sau deserialize không.
3. Nếu chỉ cần liên kết bằng database key, cân nhắc DTO chứa ID thay vì object graph.
4. Chọn ID property ổn định hoặc generator tạm thời.
5. Đặt @JsonIdentityInfo trên các kiểu cần nhận diện.
6. Chọn scope phù hợp để tránh trùng ID giữa các loại object.
7. Xác định reference mặc định hay luôn là ID bằng @JsonIdentityReference.
8. Xác định object definition xuất hiện ở đâu và cách resolve reference.
9. Chọn resolver mặc định hoặc custom resolver theo lifecycle rõ ràng.
10. Test chu trình, shared reference, missing ID, duplicate ID và forward reference.
11. Kiểm tra payload có phù hợp với schema công khai và giới hạn dữ liệu được phép xuất không.

## 18. Nguyên tắc nên giữ

- Dùng @JsonIdentityInfo khi cần biểu diễn object identity trong một graph JSON.
- PropertyGenerator phù hợp khi object có ID ổn định và duy nhất.
- Generator sequence/UUID tạo ID phục vụ graph serialize, không tự trở thành khóa database.
- Scope giúp phân biệt các không gian ID.
- Lần đầu object xuất hiện thường được ghi đầy đủ; tham chiếu sau có thể được ghi bằng ID.
- @JsonIdentityReference(alwaysAsId = true) ép một property luôn xuất ID; consumer phải có nguồn resolve.
- Deserialize cần object definition hoặc resolver cho mỗi reference.
- Resolver mặc định không tự truy vấn database và không liên kết nhiều document độc lập.
- Dùng assertSame để kiểm tra identity sau deserialize.
- So sánh với managed/back reference, @JsonIgnore và DTO có ID trước khi chọn cơ chế.
- Không serialize trực tiếp toàn bộ entity graph chỉ vì đã có identity annotation.
- Xem tên và kiểu ID là một phần hợp đồng JSON nếu client nhìn thấy chúng.

@JsonIdentityInfo giúp Jackson biểu diễn một đồ thị object có chia sẻ tham chiếu hoặc chu trình bằng cách gắn ID cho object và dùng ID đó ở các lần tham chiếu tiếp theo. Cơ chế này phù hợp khi consumer cần giữ liên kết giữa các object trong cùng payload. Hãy chọn ID và scope rõ ràng, bảo đảm mọi reference có thể được resolve, và phân biệt identity của Jackson với khóa persistence hoặc ID dùng để tra cứu qua nhiều request.


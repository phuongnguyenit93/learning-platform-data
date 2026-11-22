# Giữ quan hệ bằng @Reference và đánh giá số lần đọc phát sinh

Trong **Spring Data Redis**, một thực thể được đánh dấu `@RedisHash` thường được lưu dưới dạng dữ liệu Redis theo khóa của thực thể. Khi một đối tượng liên quan cần tồn tại độc lập, annotation **`@Reference`** cho phép một thực thể lưu **tham chiếu đến thực thể Redis khác**, thay vì nhúng toàn bộ dữ liệu của đối tượng đó vào bản ghi cha.

Lựa chọn này giúp tránh sao chép nhiều lần cùng một đối tượng, nhưng đánh đổi bằng việc **phải đọc thêm dữ liệu khi khôi phục quan hệ**. Với một danh sách nhiều thực thể, số lần đọc phát sinh có thể lớn hơn nhiều so với số thực thể ban đầu. Vì vậy, cần xem xét `@Reference` cùng với mô hình truy cập dữ liệu, kích thước quan hệ, thời gian đáp ứng và vòng đời của các khóa.

## 1. Quan hệ trong Redis khác quan hệ trong cơ sở dữ liệu quan hệ

Trong cơ sở dữ liệu quan hệ, bảng `orders` có thể chứa `customer_id` trỏ tới bảng `customers`. Hệ quản trị cơ sở dữ liệu có thể dùng khóa ngoại để kiểm tra tính hợp lệ và thực hiện `JOIN` theo kế hoạch truy vấn.

Redis là kho dữ liệu key-value, không tự cung cấp `JOIN` hay ràng buộc khóa ngoại kiểu SQL cho các Redis Hash. Spring Data Redis hỗ trợ ánh xạ đối tượng để ứng dụng thao tác với thực thể dễ hơn, nhưng những annotation đó **không biến Redis thành một ORM quan hệ**.

Có ba cách phổ biến để thể hiện một quan hệ:

| Cách biểu diễn | Dữ liệu trong thực thể cha | Cách đọc | Phù hợp khi |
|---|---|---|---|
| **Nhúng đối tượng (embedded)** | Các thuộc tính của đối tượng con được ánh xạ cùng aggregate cha | Thường lấy cùng lần đọc dữ liệu cha | Đối tượng con thuộc vòng đời cha, nhỏ và ít được chia sẻ |
| **`@Reference`** | Thông tin tham chiếu tới khóa của thực thể khác | Framework cần phân giải và đọc thực thể được tham chiếu | Đối tượng đích có danh tính và vòng đời độc lập, cần truy cập như một đối tượng |
| **Chỉ lưu ID** | `customerId`, `productIds` hoặc các giá trị khóa tương tự | Ứng dụng quyết định có đọc đích hay không, khi nào đọc và có gom đọc hay không | Danh sách lớn, màn hình chỉ cần dữ liệu tóm tắt, cần kiểm soát hiệu năng |

**Quy tắc thiết kế aggregate:** Nếu một đối tượng luôn được tạo, thay đổi và xóa cùng cha, nhúng nó thường đơn giản hơn. Nếu đối tượng có danh tính riêng và được chia sẻ giữa nhiều aggregate, tham chiếu hoặc lưu ID có thể phù hợp hơn.

## 2. `@Reference` làm gì khi lưu và khi đọc?

Giả sử một khách hàng có nhiều đơn hàng. Mỗi đơn hàng cần biết khách hàng tương ứng, nhưng thông tin khách hàng được duy trì độc lập.

### 2.1. Mô hình Java dùng Spring Data Redis Repositories

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String displayName;

    // Constructor, getter và setter được lược bớt để tập trung vào mapping.
}
```

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.mapping.Reference;

@RedisHash("orders")
public class Order {
    @Id
    private String id;
    private String status;

    @Reference
    private Customer customer;

    // Constructor, getter và setter được lược bớt.
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository extends CrudRepository<Customer, String> {
}

public interface OrderRepository extends CrudRepository<Order, String> {
}
```

Trong ví dụ này:

- `Customer` là một thực thể Redis có khóa định danh riêng, chẳng hạn `customers:c42`.
- `Order` là một thực thể khác, chẳng hạn `orders:o900`.
- Trường `customer` gắn `@Reference` báo cho bộ ánh xạ rằng đây là quan hệ tới **một thực thể Redis đã được lưu độc lập**.
- Khi lưu `Order`, thông tin liên kết tới khóa của `Customer` được ghi trong dữ liệu của `Order`. Nội dung khách hàng không được nhúng toàn bộ như một value object thông thường.
- Khi đọc và ánh xạ `Order`, Spring Data Redis có thể phải đọc thêm khóa của `Customer` để xây dựng thuộc tính `customer`.

Sơ đồ khái niệm:

```text
Java: Order(id=o900)
      |
      +-- status = "CREATED"
      |
      +-- customer ----> Customer(id=c42, displayName="Lan")

Redis (mô tả ý nghĩa, không phải wire format cố định):

orders:o900
   status   = CREATED
   customer = reference tới customers:c42
                                |
                                v
customers:c42
   displayName = Lan
```

Cách Spring Data Redis mã hóa trường tham chiếu trong Redis là chi tiết của bộ ánh xạ và có thể thay đổi theo phiên bản. **Không tự ghi một chuỗi `"customers:c42"` vào field rồi kỳ vọng nó luôn tương đương biểu diễn nội bộ của `@Reference`.**

### 2.2. Thực thể đích phải được lưu riêng

```java
Customer customer = new Customer();
// Giả sử đã có setter hoặc constructor thích hợp.
customer.setId("c42");
customer.setDisplayName("Lan");
customerRepository.save(customer);

Order order = new Order();
order.setId("o900");
order.setStatus("CREATED");
order.setCustomer(customer);
orderRepository.save(order);

Order loaded = orderRepository.findById("o900").orElseThrow();
Customer loadedCustomer = loaded.getCustomer();
```

`@Reference` **không tạo cơ chế cascade-save kiểu JPA**. Việc `orderRepository.save(order)` không đồng nghĩa với việc framework tự bảo đảm `Customer` đã được lưu. Ứng dụng cần quản lý việc tạo, cập nhật và xóa đối tượng tham chiếu theo vòng đời riêng.

Tương tự, xóa `Order` không mặc nhiên xóa `Customer`. Xóa `Customer` có thể làm các đơn hàng còn lại chứa tham chiếu không còn đích. Redis cũng không tự kiểm tra ràng buộc khóa ngoại để chặn thao tác đó.

Các đoạn mã trên minh họa cấu trúc; trong dự án thực tế cần khai báo constructor, accessor, kiểu ID và repository phù hợp với mô hình entity của ứng dụng.

## 3. Chi phí đọc phát sinh từ `@Reference`

Xét lệnh:

```java
Order order = orderRepository.findById("o900").orElseThrow();
```

Nhìn từ phía mã Java chỉ có **một lời gọi repository**, nhưng việc khôi phục `Order` có thể yêu cầu:

1. Tìm và đọc dữ liệu của khóa đơn hàng.
2. Phát hiện trường `customer` được ánh xạ bằng `@Reference`.
3. Đọc thông tin từ khóa khách hàng được tham chiếu.
4. Chuyển đổi dữ liệu khách hàng thành đối tượng `Customer` và gắn vào `Order`.

Như vậy, **một lời gọi repository không đồng nghĩa với một thao tác đọc Redis**.

Các quan hệ thông qua `@Reference` thường được giải quyết trong quá trình ánh xạ đối tượng; không nên mặc nhiên kỳ vọng hành vi lazy-loading giống proxy của JPA. Tùy đường đọc, phiên bản thư viện và cấu trúc entity, số lệnh Redis thực tế có thể khác với sơ đồ tối giản. Điều cần đánh giá là **bao nhiêu thực thể phải được truy xuất để phục vụ một yêu cầu** và **bao nhiêu lượt mạng phát sinh**.

### 3.1. Ước lượng số lượt đọc theo quan hệ

Giả sử một màn hình cần đọc `N` đơn hàng. Mỗi đơn hàng tham chiếu một khách hàng và một nhân viên bán hàng. Nếu mỗi quan hệ đều được phân giải độc lập và không có cache hoặc khử trùng lặp, số lần đọc thực thể về mặt logic xấp xỉ:

```text
Số đọc thực thể = N lần đọc Order
                + N lần đọc Customer
                + N lần đọc Salesperson
                = N × (1 + 2)
```

Với `N = 200`:

```text
200 Order
+ 200 Customer
+ 200 Salesperson
-----------------
~600 lần đọc thực thể
```

Đây là **mô hình ước lượng**, không phải cam kết một lần đọc thực thể luôn tương đương đúng một lệnh Redis hay một round-trip. Việc tìm danh sách ID, đọc index phụ, chuyển đổi quan hệ và sử dụng pipeline có thể làm số lệnh hoặc số lượt mạng khác đi.

| Tình huống | Số thực thể gốc | Tham chiếu mỗi thực thể | Ước lượng truy xuất thực thể |
|---|---:|---:|---:|
| Xem chi tiết một đơn hàng | 1 | 1 | 2 |
| Danh sách 50 đơn hàng | 50 | 1 | 100 |
| Danh sách 200 đơn hàng | 200 | 2 | 600 |
| Danh sách 1.000 đơn hàng | 1.000 | 3 | 4.000 |

Các con số trong bảng giả định từng reference đều được tải và không có kết quả đọc trùng được tái sử dụng. Chúng giúp nhận ra **quy mô tải tiềm năng** trước khi quyết định dùng `@Reference` cho đường đọc danh sách.

### 3.2. Quan hệ lồng sâu làm tăng chi phí

Ví dụ:

```text
Order
  └── @Reference Customer
        └── @Reference AccountManager
              └── @Reference Team
```

Một lần đọc `Order` có thể kéo theo cả chuỗi đọc khác. Nếu mỗi nút lại tham chiếu tới nhiều nút con, lượng truy xuất có thể tăng rất nhanh theo độ sâu của đồ thị.

Đừng tự tạo quan hệ vòng như `Order → Customer → Orders → Customer` rồi giả định framework sẽ tự cắt vòng hoặc cache tất cả đối tượng đã đọc. Quan hệ vòng, đồ thị lớn hoặc dữ liệu có nhiều nhánh cần được thiết kế rõ ràng, hạn chế độ sâu và kiểm chứng hành vi của bộ ánh xạ trong phiên bản đang chạy.

### 3.3. Nhiều đơn hàng cùng trỏ tới một khách hàng

Giả sử 200 đơn hàng chỉ thuộc 20 khách hàng. Nếu mỗi lần phân giải `@Reference` đều tạo một lượt truy xuất riêng, ứng dụng vẫn có nguy cơ đọc khách hàng nhiều lần.

```text
200 Orders ──> 20 Customer IDs duy nhất

Tải trực tiếp từng reference:
  ~200 lượt tìm Customer

Nếu ứng dụng gom ID và đọc mỗi Customer một lần:
  ~20 lượt tìm Customer
```

Việc lặp khóa đích rất phổ biến ở trang liệt kê, báo cáo và API tổng hợp. **Không mặc định giả định Spring Data Redis có identity map hoặc cơ chế khử trùng lặp xuyên suốt một lần trả danh sách.** Hiệu quả thực tế phải đo tại ranh giới Redis.

## 4. N+1 trong Redis: phát hiện bằng tình huống sử dụng

Trong SQL, N+1 thường là một truy vấn danh sách rồi thêm N truy vấn liên quan. Trong Redis, hiện tượng tương tự xảy ra khi một yêu cầu đọc N thực thể cha khiến hệ thống phải đọc tiếp N hoặc nhiều hơn các khóa tham chiếu.

```text
HTTP GET /orders?limit=100
          |
          v
Tìm 100 order IDs
          |
          v
Đọc 100 Order
          |
          +--> Order 1 -> đọc Customer 1
          +--> Order 2 -> đọc Customer 2
          +--> Order 3 -> đọc Customer 3
          ...
          +--> Order 100 -> đọc Customer 100
          |
          v
Trả JSON cho client
```

Mỗi lệnh Redis có thể rất nhanh, nhưng hàng trăm hoặc hàng nghìn lệnh nối tiếp vẫn tiêu thụ thời gian mạng, CPU mã hóa/giải mã, bộ nhớ và tải Redis. Hiện tượng này rõ hơn khi ứng dụng và Redis ở hai vùng mạng khác nhau, lúc Redis bận, hoặc khi một đối tượng còn tham chiếu thêm nhiều đối tượng khác.

Điểm cần chú ý là **mẫu truy cập của màn hình**. Trang chi tiết một đơn hàng có thể hưởng lợi từ `@Reference` rõ ràng và thuận tiện. Trang tổng quan chỉ hiển thị `orderId`, trạng thái và tổng tiền có thể **không cần tải đối tượng Customer** nào cả.

Vì vậy, một mapping hợp lệ về mặt chức năng vẫn có thể không phù hợp cho mọi luồng đọc.

## 5. Khi nào nên nhúng và khi nào nên dùng `@Reference`?

Không nên lựa chọn `@Reference` chỉ vì trong Java có một trường thuộc kiểu class khác. Cần xem thực thể con thuộc aggregate nào, có bị chia sẻ hay không và API cần dữ liệu gì.

### 5.1. Nhúng value object cùng vòng đời

```java
public class ShippingAddress {
    private String street;
    private String city;
    private String postalCode;

    // Getter/setter...
}

@RedisHash("orders")
public class Order {
    @Id
    private String id;
    private ShippingAddress shippingAddress;
}
```

Địa chỉ giao hàng chụp tại thời điểm đặt đơn thường phải lưu **như một snapshot của đơn hàng**. Nếu địa chỉ mặc định hiện tại của khách hàng thay đổi, dữ liệu lịch sử của đơn hàng không nên đổi theo. Nhúng dữ liệu cũng giúp tránh lần đọc thêm để phân giải quan hệ.

Nhược điểm là dữ liệu được sao chép: nếu một value object được chia sẻ và phải cập nhật đồng loạt, nhúng ở hàng nghìn bản ghi sẽ làm thao tác cập nhật tốn kém. Nhưng đối với snapshot lịch sử, sự độc lập đó thường là yêu cầu nghiệp vụ.

### 5.2. Tham chiếu thực thể có danh tính riêng

```java
@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Reference
    private Customer customer;
}
```

Cách này hợp lý nếu xử lý một đơn hàng thường cần lấy thông tin khách hàng đang được quản lý riêng, đồ thị quan hệ nhỏ và chi phí đọc có thể chấp nhận được.

Tuy nhiên, `@Reference` không tự giải quyết tình huống khách hàng bị xóa, đổi keyspace, thay đổi ID hoặc hết hạn trước đơn hàng.

### 5.3. Lưu ID khi cần chủ động quyết định tải quan hệ

```java
@RedisHash("orders")
public class OrderSummary {
    @Id
    private String id;
    private String customerId;
    private String status;
    private long totalAmountInCents;

    // Getter/setter...
}
```

`customerId` là một trường scalar của aggregate. Khi đọc `OrderSummary`, Spring Data Redis không cần tự phân giải một `Customer` để ánh xạ trường đó.

Đường đọc danh sách có thể chỉ lấy đơn hàng. Đường xem chi tiết mới gọi repository khách hàng hoặc một dịch vụ truy xuất quan hệ. Nhờ vậy, số lần đọc phát sinh tương ứng với **dữ liệu thực sự cần cho response**.

Không tồn tại một cách duy nhất đúng cho tất cả quan hệ: cùng một domain có thể dùng snapshot nhúng cho địa chỉ giao hàng, `@Reference` cho vài liên kết nhỏ và chỉ lưu ID cho danh sách hoặc đồ thị lớn.

## 6. Giảm đọc trùng bằng cách lưu ID và gom dữ liệu

Giả sử API hiển thị 200 đơn hàng, tên khách hàng của mỗi đơn và có nhiều đơn cùng khách hàng.

Nếu dùng `@Reference` trực tiếp trên entity được tải cho mọi dòng, phần ánh xạ có thể phát sinh đọc khách hàng lặp lại. Một lựa chọn khác là **lưu ID trong đơn hàng rồi gom các ID khách hàng duy nhất**.

### 6.1. Ví dụ đọc theo hai giai đoạn

Giả sử `OrderSummary` chứa các trường `id`, `customerId` và `status`; `Customer` chứa `id` và `displayName`, các class có getter phù hợp.

```java
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class OrderQueryService {

    private final OrderSummaryRepository orders;
    private final CustomerRepository customers;

    public OrderQueryService(
            OrderSummaryRepository orders,
            CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public List<OrderListItem> load(Collection<String> orderIds) {
        List<OrderSummary> orderList = StreamSupport
                .stream(orders.findAllById(orderIds).spliterator(), false)
                .toList();

        Set<String> customerIds = orderList.stream()
                .map(OrderSummary::getCustomerId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, Customer> byId = new HashMap<>();
        customers.findAllById(customerIds).forEach(customer ->
                byId.put(customer.getId(), customer));

        return orderList.stream()
                .map(order -> {
                    Customer customer = byId.get(order.getCustomerId());
                    return new OrderListItem(
                            order.getId(),
                            order.getStatus(),
                            order.getCustomerId(),
                            customer == null ? null : customer.getDisplayName());
                })
                .toList();
    }

    public record OrderListItem(
            String orderId,
            String status,
            String customerId,
            String customerName) {
    }
}
```

Repository tương ứng:

```java
import org.springframework.data.repository.CrudRepository;

public interface OrderSummaryRepository
        extends CrudRepository<OrderSummary, String> {
}
```

Trình tự thực hiện:

1. Đọc các đơn hàng cần hiển thị.
2. Thu thập những `customerId` khác nhau.
3. Đọc mỗi khách hàng cần thiết thông qua repository.
4. Ghép dữ liệu trong bộ nhớ thành DTO trả cho client.
5. Quy định cách xử lý khi tham chiếu khách hàng không còn tồn tại; ví dụ `customerName = null` và vẫn giữ `customerId` để điều tra.

Ví dụ 200 đơn hàng trỏ tới 20 khách hàng duy nhất có thể giảm số **thực thể khách hàng cần truy xuất về mặt logic** từ khoảng 200 xuống 20, nếu trước đó mỗi reference bị đọc riêng.

**Giới hạn quan trọng:** `CrudRepository.findAllById(...)` không tự bảo đảm Redis chỉ nhận một lệnh hay một round-trip mạng. Nó giúp ứng dụng xác định tập ID cần đọc và bỏ các ID trùng. Muốn thật sự tối ưu round-trip, phải đánh giá cơ chế thực thi repository hoặc chủ động thiết kế pipeline/batch ở lớp Redis thích hợp.

### 6.2. Pipelining: giảm round-trip, không biến nhiều khóa thành một đối tượng

Redis pipelining cho phép gửi nhiều lệnh mà không chờ kết quả từng lệnh trước khi gửi lệnh tiếp theo. Khi cần đọc nhiều Redis Hash độc lập, pipelining có thể giảm độ trễ mạng so với các lệnh tuần tự.

Nhưng cần phân biệt:

| Kỹ thuật | Giảm số đối tượng logic phải đọc? | Giảm số lệnh Redis? | Có thể giảm số lượt chờ mạng? |
|---|---|---|---|
| Lọc bỏ quan hệ không cần trong DTO | Có | Có | Có |
| Khử trùng lặp theo ID | Có, nếu nhiều tham chiếu cùng ID | Có trong luồng đọc được khử trùng lặp | Có |
| Pipelining | Không | Không nhất thiết | Có |
| Cache kết quả truy xuất đối tượng đích | Có khi cache hit | Có | Có |
| Nhúng snapshot | Tránh đọc khóa tham chiếu riêng | Có đối với luồng đọc cha | Có |

Nếu dùng `RedisTemplate.executePipelined(...)`, phải bảo đảm keyspace và serializer đúng với dữ liệu đã lưu, đồng thời chuyển đổi Hash qua mapping phù hợp. Không nên đọc thô rồi giả định dữ liệu Hash của `@RedisHash` là JSON string. Việc chuyển từ repository sang pipeline có thể đòi hỏi thiết kế read model riêng; đổi lại, ứng dụng có quyền kiểm soát rõ ràng các thao tác đọc.

`MGET` hoạt động với **các khóa string value**, không phải một lệnh đọc hàng loạt Redis Hash bất kỳ. Không dùng `MGET` thay cho `HGETALL` đối với các entity đang được repository lưu dạng Hash.

## 7. Không phải quan hệ nào cũng nên tải khi trả API

Cùng một entity có thể được dùng bởi nhiều màn hình:

| Luồng sử dụng | Dữ liệu thực sự cần | Hướng xử lý |
|---|---|---|
| Xem chi tiết đơn hàng | Đơn hàng và một số thông tin khách hàng | `@Reference` có thể đủ nếu đồ thị nhỏ |
| Liệt kê 100 đơn hàng | ID, trạng thái, tổng tiền | Read model chỉ gồm scalar, tránh tải quan hệ |
| Báo cáo doanh thu theo khách hàng | Nhiều đơn hàng, nhóm theo khách hàng | Lưu ID, gom theo khóa; cân nhắc mô hình tổng hợp riêng |
| Kiểm tra khách hàng còn hoạt động | Trạng thái mới nhất của khách hàng | Đọc nguồn phù hợp, không dựa vào snapshot cũ |
| Lịch sử giao hàng | Địa chỉ tại thời điểm đặt | Nhúng snapshot trong đơn hàng |

Một API list thường nên dùng DTO và truy vấn đúng nhu cầu. Nếu lớp repository luôn phân giải các `@Reference` trước khi ứng dụng chuyển thành DTO, thao tác bỏ trường trên JSON **không lấy lại được chi phí Redis đã phát sinh**. Muốn tránh đọc, cần thay đổi cách lấy dữ liệu từ trước giai đoạn mapping hoặc dùng mô hình lưu/đọc khác.

## 8. TTL, dữ liệu bị xóa và quan hệ không còn đích

Redis có cơ chế hết hạn khóa. Hai thực thể liên kết bằng `@Reference` không có vòng đời tự động đồng bộ chỉ nhờ annotation.

Ví dụ:

```text
orders:o900 (TTL: 7 ngày)
   |
   +--> tham chiếu customers:c42 (TTL: 30 phút)

Sau 30 phút:
orders:o900 còn tồn tại
customers:c42 có thể đã hết hạn
```

Lúc này dữ liệu của `Order` còn tồn tại nhưng đối tượng được tham chiếu có thể không tải được. Cách framework thể hiện tham chiếu không còn đích trong object cần được kiểm chứng với phiên bản và cấu hình cụ thể; **đừng xây dựng nghiệp vụ dựa trên giả định quan hệ luôn tồn tại**.

Một số hướng xử lý:

- **Căn chỉnh vòng đời:** các thực thể lâu dài không nên trỏ trực tiếp đến khóa cache quá ngắn hạn nếu cần phân giải chúng suốt thời gian sống của cha.
- **Lưu định danh dự phòng:** giữ `customerId` dưới dạng scalar nếu cần biết đã tham chiếu ai ngay cả khi bản ghi đích không còn.
- **Snapshot tối thiểu:** lưu những thuộc tính lịch sử phải giữ, như tên nhận hàng hoặc địa chỉ khi chốt đơn.
- **Quy trình xóa có kiểm soát:** khi xóa khách hàng, xác định cần ngăn xóa, ẩn thông tin, hủy liên kết hay giữ bản ghi lịch sử theo nghiệp vụ.
- **Version và migration:** thay đổi tiền tố keyspace, cấu trúc ID hoặc lớp entity có thể khiến tham chiếu cũ không còn phân giải như trước. Cần thiết kế migration hoặc tương thích ngược.
- **Phản hồi rõ khi mất đích:** trong luồng dùng ID, quyết định trả `null`, báo lỗi nghiệp vụ hay đọc từ nguồn phục hồi dữ liệu.

Lưu ý rằng cập nhật hai Redis Hash liên quan bằng hai lệnh lưu riêng không mặc nhiên là một transaction nhất quán cho toàn bộ aggregate. `@Reference` không cung cấp ràng buộc toàn vẹn tham chiếu kiểu foreign key.

## 9. Đánh giá chi phí thật: số lệnh, độ trễ và tải Redis

Không nên kết luận chỉ từ số dòng mã Java. Hãy đo trên **một use case cụ thể** với bộ dữ liệu đủ giống môi trường thực tế.

### 9.1. Đặt giả thuyết chi phí trước khi đo

Ví dụ một endpoint trả 100 đơn hàng, mỗi đơn có hai reference. Ghi lại:

```text
Tải đầu vào:          100 đơn hàng / request
Reference/đơn:        2
Số ID đích duy nhất:  35 khách hàng, 8 nhân viên
Số đọc logic gần đúng nếu phân giải độc lập: 100 + 200 = 300
Số đọc logic khi gom ID:                 100 + 35 + 8 = 143
```

Các số `300` và `143` là **giả thuyết logic để so sánh thiết kế**. Kết quả đo số lệnh, round-trip và thời gian xử lý có thể không trùng số đó.

Đặc biệt, hãy đo cả **p95/p99** chứ không chỉ thời gian trung bình: một request tình cờ chứa nhiều khóa chưa có trong cache hoặc nhiều quan hệ sâu có thể chậm hơn rất nhiều.

### 9.2. Đo những gì?

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Tổng lệnh Redis theo endpoint | Một request khiến bao nhiêu lệnh được gửi? |
| Số lệnh đọc Hash hoặc key liên quan | Có nhiều lần đọc riêng cho cùng ID không? |
| Số round-trip và độ trễ Redis | Lệnh có chạy tuần tự hay được gom pipeline? |
| Độ trễ endpoint p50/p95/p99 | N+1 có làm trải nghiệm xấu đi khi danh sách dài? |
| CPU và băng thông Redis | Nhiều Hash và serializer có làm hệ thống nghẽn? |
| Bộ nhớ ứng dụng và thời gian mapping | Đồ thị đối tượng có quá lớn so với DTO cần trả? |
| Số tham chiếu không còn đích | TTL/xóa dữ liệu có làm quan hệ hỏng không? |

Với hệ thống sử dụng Lettuce, có thể cấu hình thu thập độ trễ lệnh và tích hợp telemetry phù hợp với stack quan sát của ứng dụng. Nếu có Micrometer/Actuator, bổ sung timer cho tầng service và dashboard gắn với endpoint. Cần đo cả **công việc do mapper và repository phát sinh**, không chỉ đoạn mã đọc quan hệ do developer viết tay.

Ở Redis, các lệnh quan sát sau hỗ trợ nhận biết xu hướng tổng thể:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

- `INFO commandstats` phản ánh thống kê lệnh theo loại ở **toàn Redis instance**, nên cần tính chênh lệch theo khoảng đo và tách nhiễu từ các request khác.
- `SLOWLOG` cho biết những lệnh có thời gian xử lý phía Redis vượt ngưỡng; nó **không** liệt kê đầy đủ những lệnh nhanh nhưng lặp lại hàng nghìn lần, cũng không bao gồm toàn bộ thời gian mạng.
- `MONITOR` có thể hỗ trợ điều tra ở môi trường thử nghiệm nhỏ, nhưng tạo thêm tải và có thể làm lộ dữ liệu lệnh; tránh bật trên Redis production bận rộn để đo toàn bộ request.

Để gắn số lệnh chính xác với một request, có thể dùng instrumentation có giới hạn thời gian tại lớp client Redis và một scenario tải riêng biệt. Thống kê tổng của Redis không đủ để kết luận một endpoint có đúng bao nhiêu lần đọc reference.

### 9.3. Cách so sánh hai thiết kế

Thử cùng một bộ dữ liệu, cùng số đơn hàng, cùng mức đồng thời:

1. **Thiết kế A:** `@Reference Customer` và các reference liên quan trên entity trả về.
2. **Thiết kế B:** lưu ID, gom ID duy nhất và dựng DTO theo nhu cầu.
3. Nếu còn nghẽn, thử **thiết kế C:** B kết hợp pipeline hoặc read model chuyên biệt.
4. So sánh lượng dữ liệu trả về, số lệnh Redis, thời gian mapping và độ trễ end-to-end.
5. Kiểm tra cả khi khách hàng trùng nhiều và khi gần như tất cả ID đều khác nhau.

Đừng quy toàn bộ chênh lệch hiệu năng cho `@Reference` nếu hai thiết kế dùng kích thước Hash, serializer hoặc chiến lược cache khác nhau. Thử trên cấu hình tương đương và quan sát nguyên nhân.

## 10. Những tình huống dễ gây sai lệch thiết kế

### 10.1. Dùng `@Reference` cho danh sách không giới hạn

```java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Reference
    private List<Order> orders;
}
```

Nếu một khách hàng có hàng chục nghìn đơn hàng, thao tác đọc khách hàng có nguy cơ kéo theo một đồ thị lớn. Danh sách này còn khó phân trang tại thuộc tính entity. Với quan hệ một-nhiều lớn, thường nên lưu quan hệ theo **ID hoặc chỉ mục truy vấn có phân trang**, rồi lấy một trang đơn hàng riêng.

### 10.2. Dùng tham chiếu cho dữ liệu lịch sử cần bất biến

Nếu đơn hàng phải giữ nguyên tên và địa chỉ người nhận tại thời điểm thanh toán, việc chỉ tham chiếu tới hồ sơ khách hàng hiện tại không thể hiện đúng lịch sử. Hãy lưu snapshot quan trọng vào đơn hàng; có thể giữ thêm `customerId` để biết khách hàng gốc.

### 10.3. Coi `@Reference` là khóa ngoại bảo đảm tồn tại

Ghi một tham chiếu không bảo đảm khóa đích tồn tại mãi. Redis không tự kiểm tra foreign key. Cần kiểm soát tồn tại, TTL, xóa và thay đổi ID bằng nghiệp vụ.

### 10.4. Mong chờ repository tự tối ưu tất cả truy xuất

Repository giúp ánh xạ entity và xây dựng API dữ liệu thuận tiện. Không vì gọi `findAllById` hay `findById` mà kết luận framework đã gom các reference trùng, pipeline mọi truy vấn hoặc lazy-load khi cần. Những giả định này phải được chứng minh bằng đo đạc trong ứng dụng thật.

### 10.5. Chỉ đo số request HTTP

Một request HTTP có thể phát sinh vài lệnh Redis hoặc hàng nghìn lệnh Redis. Khi tối ưu, cần quan sát số đọc Redis và độ trễ ở tầng truy cập dữ liệu.

## 11. Bài toán hoàn chỉnh: màn hình quản lý đơn hàng

Một hệ thống quản lý có 10.000 đơn hàng, 800 khách hàng và 40 nhân viên. Trang quản trị hiển thị 100 đơn hàng mỗi lần, kèm tên khách hàng và tên nhân viên.

### Thiết kế ban đầu

```java
@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Reference
    private Customer customer;

    @Reference
    private Salesperson salesperson;

    // Các thuộc tính khác...
}
```

Với trang 100 đơn, mô hình đọc đơn giản là 100 thực thể đơn hàng và có thể thêm 200 lần phân giải reference. Số lượt thực tế còn phụ thuộc cách Spring Data Redis thực thi, mức cache và ID trùng.

### Thiết kế điều chỉnh

```java
@RedisHash("orders")
public class OrderListRecord {
    @Id
    private String id;
    private String customerId;
    private String salespersonId;
    private String status;
    private long totalAmountInCents;
}
```

Quy trình truy xuất:

```text
Nhận yêu cầu trang 100 OrderListRecord
                   |
                   v
           Đọc 100 order
                   |
                   v
     Lấy tập customerId duy nhất
     Lấy tập salespersonId duy nhất
                   |
                   v
     Đọc các thực thể đích cần thiết
        (có thể gom/pipeline)
                   |
                   v
          Ghép dữ liệu thành DTO
                   |
                   v
               Trả API
```

Giả sử 100 đơn của trang này chỉ trỏ đến 28 khách hàng và 7 nhân viên:

- Theo mô hình mỗi reference được đọc riêng: khoảng **100 + 100 + 100 = 300** truy xuất thực thể.
- Sau khi khử trùng lặp theo ID: khoảng **100 + 28 + 7 = 135** truy xuất thực thể.
- Nếu trang không hiển thị tên khách hàng và nhân viên, read model chỉ cần **100 đơn**, không phải phân giải hai quan hệ.

Nếu màn hình chi tiết đơn hàng lại cần object `Customer` đầy đủ và chỉ đọc một đơn mỗi lần, dùng `@Reference` ở mô hình thích hợp vẫn có thể là lựa chọn đơn giản. Có thể tồn tại **write model và read model khác nhau** cho cùng nghiệp vụ; điều kiện là ứng dụng có cách đồng bộ chúng rõ ràng.

## 12. Checklist lựa chọn quan hệ

Trước khi thêm `@Reference` vào một Redis entity, hãy trả lời:

1. Đối tượng đích có ID và vòng đời riêng không, hay thực ra chỉ là value object thuộc aggregate cha?
2. Khi đọc cha, **có luôn cần** dữ liệu đầy đủ của đối tượng đích không?
3. Một request có thể đọc tối đa bao nhiêu cha, mỗi cha có bao nhiêu tham chiếu và độ sâu là bao nhiêu?
4. Nhiều cha có trỏ tới **cùng một ID** không? Có thể gom các ID trùng hay không?
5. Nếu đối tượng đích bị xóa hoặc TTL hết hạn trước cha, hành vi nghiệp vụ phải thế nào?
6. Tên keyspace, kiểu ID và mô hình mapping có khả năng thay đổi khi triển khai/migration không?
7. Đã đo số lệnh Redis, độ trễ p95/p99 và chi phí mapping trên một luồng đọc thực tế chưa?

**Kết luận kỹ thuật:** `@Reference` là công cụ biểu diễn quan hệ giữa những thực thể Redis độc lập. Nó giúp mô hình Java diễn đạt liên kết trực tiếp và tránh nhúng dữ liệu dùng chung, nhưng quan hệ cần được phân giải khi đọc sẽ làm tăng số truy xuất. Với đường đọc một thực thể và đồ thị nhỏ, lợi ích về tính rõ ràng có thể lớn hơn chi phí. Với danh sách, quan hệ nhiều-nhiều, reference trùng hoặc đồ thị sâu, nên cân nhắc lưu ID, read model riêng, khử trùng lặp và pipeline phù hợp. Quyết định cuối cùng dựa trên **số lần đọc Redis thực tế của use case**, cùng yêu cầu nhất quán và vòng đời của dữ liệu.


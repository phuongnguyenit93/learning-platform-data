# Giới hạn join, truy vấn tùy ý và tìm kiếm toàn văn

Spring Data Redis giúp ứng dụng Java thao tác với Redis bằng `RedisTemplate`, các cấu trúc dữ liệu Redis và **Redis Repository**. Khi dùng `@RedisHash`, một đối tượng Java có thể được lưu dưới dạng Redis Hash; khi đánh dấu thuộc tính bằng `@Indexed`, framework còn quản lý các chỉ mục phụ phục vụ một số truy vấn dựa trên thuộc tính.

Tuy nhiên, **Redis Repository không phải một bộ máy truy vấn quan hệ tổng quát**. Việc khai báo một repository và một vài annotation không tự mang lại `JOIN`, `GROUP BY`, `LIKE '%keyword%'`, truy vấn đa điều kiện tùy ý hoặc tìm kiếm toàn văn có xếp hạng mức độ liên quan như các hệ quản trị cơ sở dữ liệu và công cụ tìm kiếm chuyên dụng.

Bài học đặt ra ba câu hỏi thiết kế:

1. Khi dữ liệu nằm ở nhiều Redis Hash, ứng dụng kết hợp các thực thể như thế nào nếu không có phép JOIN của SQL?
2. Với `@Indexed` và truy vấn Repository, đâu là ranh giới của những điều kiện có thể thực thi hiệu quả?
3. Khi cần tìm kiếm từ khóa, ngôn ngữ tự nhiên hoặc xếp hạng kết quả, nên dùng Redis Search/Query Engine hay một hệ thống tìm kiếm riêng?

## 1. Hiểu chính xác các lớp truy cập dữ liệu trong Spring Data Redis

Redis là một hệ thống dữ liệu hỗ trợ nhiều kiểu cấu trúc như String, Hash, Set, Sorted Set, List và Stream. Hầu hết các thao tác cơ bản được thiết kế để truy cập key hoặc thao tác trên một cấu trúc dữ liệu đã biết. Redis không tự biến mọi Hash thành một bảng SQL có khả năng truy vấn bất kỳ cột nào.

Spring Data Redis cung cấp những lớp trừu tượng khác nhau:

| Cách truy cập | Nguồn sức mạnh | Giới hạn quan trọng |
| --- | --- | --- |
| `RedisTemplate` / `StringRedisTemplate` | Thao tác trực tiếp với các lệnh và kiểu dữ liệu Redis | Ứng dụng phải tự tổ chức key, quan hệ và truy vấn |
| `CrudRepository` cho `@RedisHash` | Ánh xạ entity; tìm theo ID; hỗ trợ các truy vấn theo thuộc tính đã được lập chỉ mục | Không có SQL JOIN hoặc ngôn ngữ truy vấn tùy ý đầy đủ |
| `@Indexed` của Spring Data Redis | Duy trì Redis Set ánh xạ giá trị thuộc tính sang ID thực thể | Chủ yếu phục vụ truy vấn index được hỗ trợ; không phải full-text index |
| Redis Search / Redis Query Engine | Lập chỉ mục và thực thi truy vấn tìm kiếm trên những kiểu dữ liệu được hỗ trợ | Cần Redis có chức năng tương ứng, khai báo schema và dùng API/command thích hợp |
| Công cụ tìm kiếm bên ngoài | Truy vấn văn bản, phân tích ngôn ngữ, ranking và aggregation theo khả năng từng sản phẩm | Phải đồng bộ dữ liệu giữa nơi ghi chính và hệ thống tìm kiếm |

Một nguyên tắc rất quan trọng: **những cách truy cập này không tự thay thế nhau**. Ví dụ, lưu JSON bằng `opsForValue().set(...)` không tự tạo secondary index của Redis Repository; thêm `@Indexed` cũng không tự tạo chỉ mục `FT.SEARCH`.

## 2. JOIN trong SQL khác gì quan hệ giữa các Redis Hash?

Trong cơ sở dữ liệu quan hệ, hai bảng có thể liên kết bằng khóa ngoại:

~~~sql
SELECT c.id, c.name, o.id AS order_id, o.total_amount
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE c.id = 'c-101';
~~~

Bộ máy SQL biết cách lập kế hoạch truy vấn, dùng chỉ mục phù hợp và nối các hàng của hai bảng.

Với Redis Hash, nếu chúng ta lưu:

~~~text
customers:c-101
  id = c-101
  name = Nguyễn Lan

orders:o-9001
  id = o-9001
  customerId = c-101
  totalCents = 125000

orders:o-9002
  id = o-9002
  customerId = c-101
  totalCents = 87000
~~~

thì Redis không tự có một câu lệnh `JOIN customers ON orders.customerId = customers.id`. Ứng dụng phải có cách **tìm ra ID của đơn hàng thuộc khách hàng** rồi tải các thực thể liên quan.

Sơ đồ luồng truy vấn:

~~~text
            API: GET /customers/c-101/orders
                           |
                           v
                 CustomerOrderService
                    /           \
                   v             v
      CustomerRepository     OrderRepository
       findById("c-101")    findByCustomerId("c-101")
                   |             |
                   v             v
            Hash khách hàng    Secondary index
                                  |
                                  v
                            ID các đơn hàng
                                  |
                                  v
                             Hash đơn hàng
                   \             /
                    v           v
                   Ghép kết quả trong Java
                           |
                           v
                      Response DTO
~~~

Đây là **application-side join**, nghĩa là mã Java kết hợp các kết quả đã đọc. Cách này phù hợp khi quan hệ rõ ràng và số lượng thực thể liên quan nằm trong phạm vi có thể kiểm soát, nhưng không có những tính chất và công cụ tối ưu hóa JOIN mà SQL thường cung cấp.

### `@Reference` không biến Redis thành SQL

Spring Data Redis có `@Reference` để biểu diễn một tham chiếu tới thực thể được lưu riêng. Nó có thể hỗ trợ giải quyết tham chiếu khi ánh xạ đối tượng, nhưng **không cung cấp phép JOIN tổng quát** và không tự tạo chỉ mục cho các thuộc tính nằm trong thực thể được tham chiếu.

Ví dụ, giả sử đơn hàng có một tham chiếu `customer`. Điều đó không có nghĩa repository tự hiểu truy vấn kiểu:

~~~text
Tìm mọi Order mà order.customer.address.city = "Hà Nội"
~~~

như một SQL JOIN đi qua `Order → Customer → Address`. Với truy vấn này, ứng dụng cần thiết kế chỉ mục thích hợp, truy vấn theo nhiều bước, sao chép một số thuộc tính vào mô hình đọc hoặc dùng một hệ thống truy vấn đáp ứng yêu cầu.

## 3. Ví dụ cụ thể: truy vấn khách hàng và đơn hàng

Để hỗ trợ tìm đơn hàng theo khách hàng mà không quét mọi Hash, ta lưu `customerId` trong `Order` và lập chỉ mục cho thuộc tính đó.

**`Customer.java`**

~~~java
package com.example.redis.query;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Indexed
    private String email;

    private String name;

    public Customer() {
    }

    public Customer(String id, String email, String name) {
        this.id = id;
        this.email = email;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getName() {
        return name;
    }
}
~~~

**`Order.java`**

~~~java
package com.example.redis.query;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Indexed
    private String customerId;

    private String status;

    private long totalCents;

    public Order() {
    }

    public Order(String id, String customerId,
                 String status, long totalCents) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getStatus() {
        return status;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

**Repository**:

~~~java
package com.example.redis.query;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByCustomerId(String customerId);
}
~~~

Trong một dự án Java thật, mỗi `public interface` nên đặt ở tệp riêng cùng tên. Chúng được trình bày cạnh nhau để làm rõ quan hệ giữa hai repository.

**Service kết hợp hai kết quả**:

~~~java
package com.example.redis.query;

import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;

@Service
public class CustomerOrderQueryService {
    private final CustomerRepository customers;
    private final OrderRepository orders;

    public CustomerOrderQueryService(CustomerRepository customers,
                                     OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    public CustomerOrders loadCustomerOrders(String customerId) {
        Customer customer = customers.findById(customerId)
            .orElseThrow(() -> new NoSuchElementException(
                "Customer does not exist: " + customerId
            ));

        List<Order> customerOrders =
            orders.findByCustomerId(customerId);

        return new CustomerOrders(customer, customerOrders);
    }

    public record CustomerOrders(Customer customer, List<Order> orders) {
    }
}
~~~

Thử lưu dữ liệu:

~~~java
customers.save(new Customer(
    "c-101", "lan@example.test", "Nguyễn Lan"
));

orders.save(new Order("o-9001", "c-101", "PAID", 125000));
orders.save(new Order("o-9002", "c-101", "NEW", 87000));

CustomerOrderQueryService.CustomerOrders result =
    service.loadCustomerOrders("c-101");

System.out.println(result.customer().getName()); // Nguyễn Lan
System.out.println(result.orders().size());      // 2
~~~

Điều kiện quan trọng để `findByCustomerId` hoạt động trong Redis Repository là `customerId` đã được đánh dấu `@Indexed` và các bản ghi đã đi qua đường ghi tạo chỉ mục. Nếu thêm annotation sau khi dữ liệu cũ đã tồn tại, cần có kế hoạch xây dựng lại index cho dữ liệu cũ.

### Application-side join có những giới hạn nào?

- **Nhiều lần đọc:** Có ít nhất một lượt tìm khách hàng và một lượt tìm tập đơn hàng, sau đó có thể phải đọc nhiều Hash.
- **Độ lớn kết quả:** Nếu khách hàng có hàng trăm nghìn đơn hàng, tải toàn bộ vào `List<Order>` là tốn bộ nhớ và thời gian.
- **Tính nhất quán:** Khách hàng có thể bị sửa hoặc xóa giữa hai bước đọc. Kết quả ghép không mặc nhiên là một snapshot giao dịch.
- **Giới hạn điều kiện:** Nếu muốn lọc đơn hàng theo `status`, sắp xếp `totalCents` và phân trang, một index theo `customerId` chưa chắc đủ.
- **Tái sử dụng:** Mỗi kiểu kết hợp dữ liệu có thể cần mã truy vấn riêng; Redis Repository không tự tối ưu hóa cây JOIN.

Vì thế, chỉ nên thực hiện kiểu join này cho các quan hệ và kích thước kết quả đã biết rõ.

## 4. Những truy vấn Repository có thể và không thể giải quyết

`@Indexed` trong Spring Data Redis tạo chỉ mục phụ dựa trên Redis Set, thường ánh xạ **giá trị thuộc tính → tập ID thực thể**.

Ví dụ:

~~~text
customers:email:lan@example.test → { c-101 }
orders:customerId:c-101          → { o-9001, o-9002 }
~~~

Đối với truy vấn so khớp chính xác theo một thuộc tính đã lập chỉ mục, framework có thể lấy tập ID tương ứng và nạp thực thể. Một số tổ hợp điều kiện được hỗ trợ bởi Redis Repository có thể tận dụng thao tác trên tập ID.

Điều đó **không có nghĩa mọi từ khóa derived query của Spring Data ở các database khác đều hoạt động trong Redis**. Khả năng phân tích tên phương thức và thực thi toán tử tùy thuộc store module. Không thể lấy một phương thức JPA bất kỳ, đổi repository thành Redis rồi kỳ vọng có cùng ngữ nghĩa.

| Nhu cầu truy vấn | Spring Data Redis Repository với chỉ mục phụ | Gợi ý |
| --- | --- | --- |
| Tìm theo ID | Phù hợp | Dùng `findById` |
| Tìm bằng email chính xác | Phù hợp nếu email được lập chỉ mục | `@Indexed` và derived query được hỗ trợ |
| Tìm theo một thuộc tính trạng thái | Có thể phù hợp | Đánh giá số lượng kết quả |
| Kết hợp một số điều kiện trên field đã index | Phụ thuộc toán tử được Redis Repository hỗ trợ | Kiểm thử truy vấn cụ thể |
| JOIN nhiều loại entity | Không có JOIN SQL tự động | Ghép ở ứng dụng hoặc thiết kế read model |
| Tìm theo thuộc tính của entity được `@Reference` trỏ đến | Không tự trở thành JOIN | Lập chỉ mục ở entity đang truy vấn hoặc truy vấn nhiều bước |
| Tìm tên chứa chuỗi bất kỳ | Không mặc nhiên có tìm chuỗi con toàn văn | Search index/công cụ tìm kiếm |
| Tìm có lỗi chính tả, stemming, relevance ranking | Không phải chức năng của `@Indexed` | Search engine thích hợp |
| Phân trang/sắp xếp linh hoạt trên dữ liệu lớn | Không tương đương SQL query planner | Thiết kế index/read model theo thứ tự truy cập |
| Aggregate như nhóm và tính tổng tùy ý | Không phải truy vấn tổng quát của Redis Repository | Tính trước số liệu hoặc dùng nơi lưu phù hợp |

### Tránh suy diễn từ kiểu trả về của phương thức

Việc viết:

~~~java
List<Order> findByCustomerIdOrderByTotalCentsDesc(String customerId);
~~~

không tự tạo được một cơ chế sắp xếp hiệu quả theo `totalCents` trong Redis. Trước khi dựa vào một derived method có nhiều toán tử hoặc sắp xếp, phải xác nhận Redis Repository của phiên bản đang dùng thực sự hỗ trợ truy vấn đó. Nếu không, cần một cấu trúc truy vấn khác, chẳng hạn Sorted Set được ứng dụng quản lý.

Tương tự, khai báo một tham số `Pageable` không tự bảo đảm rằng Redis có thể lấy page thứ `N` theo nhiều điều kiện và thứ tự tùy ý mà không phải duyệt một tập dữ liệu lớn.

## 5. Truy vấn tùy ý: vì sao quét toàn bộ key thường là lựa chọn tồi?

Một cách xử lý ngây thơ là:

1. Lấy mọi key có prefix `orders:*`.
2. Đọc từng Hash.
3. Dùng Java `stream().filter(...)` lọc điều kiện.
4. Sắp xếp và cắt trang trong bộ nhớ.

Ví dụ tư duy:

~~~java
// Pseudo-code minh họa anti-pattern, không nên chạy trên dữ liệu lớn:
List<Order> results = loadAllOrdersFromRedis()
    .stream()
    .filter(o -> "PAID".equals(o.getStatus()))
    .filter(o -> o.getTotalCents() >= 100_000)
    .sorted((a, b) -> Long.compare(
        b.getTotalCents(), a.getTotalCents()))
    .toList();
~~~

Điểm yếu là lượng công việc thường tăng theo **tổng số đối tượng đang lưu**, chứ không theo số đối tượng khớp kết quả. Trên Redis production, kiểu truy vấn này dễ tạo tải mạng, CPU, memory và tăng độ trễ.

### Vì sao không dùng `KEYS orders:*` để giải quyết?

Lệnh `KEYS` phải duyệt không gian key và có thể chặn Redis lâu khi số lượng key lớn. `SCAN` hỗ trợ duyệt tăng dần theo cursor, phù hợp hơn cho tác vụ quản trị/duyệt có kiểm soát, nhưng:

- `SCAN` **không** biến việc quét thành chỉ mục truy vấn theo thuộc tính.
- Một vòng `SCAN` vẫn phải đi qua không gian key tương ứng để tìm hết dữ liệu.
- Trong lúc dữ liệu thay đổi, kết quả lặp hoặc thay đổi giữa các lượt là điều cần tính tới.
- `SCAN` không tự hỗ trợ `JOIN`, tính relevance hoặc sorting theo các field.

Nên dùng `SCAN` cho các tác vụ duyệt, bảo trì hoặc di chuyển dữ liệu có chủ đích; không xem nó là nền tảng mặc định cho endpoint tìm kiếm được gọi thường xuyên.

## 6. Thiết kế truy vấn chuyên biệt bằng Redis Set và Sorted Set

Khi truy vấn thường xuyên vượt quá khả năng repository nhưng vẫn có cấu trúc cố định, ứng dụng có thể chủ động duy trì một **read model** bằng các kiểu dữ liệu Redis.

### 6.1. Set cho quan hệ và bộ lọc theo giá trị chính xác

Ví dụ lưu tập đơn hàng thuộc một khách hàng:

~~~redis
SADD customer:orders:c-101 o-9001 o-9002
SMEMBERS customer:orders:c-101
~~~

Hoặc lưu tập đơn hàng theo trạng thái:

~~~redis
SADD orders:status:PAID o-9001 o-9008
SADD orders:customer:c-101 o-9001 o-9002
SINTER orders:status:PAID orders:customer:c-101
~~~

`SINTER` cho ra các ID nằm đồng thời trong hai Set, ví dụ các đơn hàng đã thanh toán của khách hàng `c-101`.

Đây là một **quy ước key thủ công**. Ứng dụng phải đảm bảo khi đơn hàng đổi chủ sở hữu, đổi trạng thái hoặc bị xóa thì membership được cập nhật tương ứng. Nó không tự đồng bộ với các index do Redis Repository quản lý nếu hai hệ thống lưu song song.

### 6.2. Sorted Set cho xếp hạng hoặc truy vấn theo score

Giả sử giao diện cần hiển thị đơn hàng mới nhất của khách hàng. Có thể dùng Sorted Set với score là timestamp:

~~~redis
ZADD customer:orders:recent:c-101 1732000000 o-9001
ZADD customer:orders:recent:c-101 1732010000 o-9002
ZREVRANGE customer:orders:recent:c-101 0 19
~~~

Kết quả gồm tối đa 20 ID theo score từ cao xuống thấp. Sau đó ứng dụng tải nội dung các đơn hàng theo ID.

Nếu cần lọc thêm `status=PAID`, phải thiết kế cách kết hợp kết quả và thứ tự hoặc duy trì một Sorted Set riêng cho dạng truy vấn phổ biến, ví dụ `customer:paid-orders:recent:c-101`. Không có bảo đảm rằng một bộ sưu tập Set/Sorted Set tùy ý sẽ hỗ trợ hiệu quả mọi tổ hợp điều kiện như SQL.

Với phân trang ổn định khi có dữ liệu mới liên tục, cursor dựa trên score và một tie-breaker phù hợp có thể hữu ích hơn phân trang bằng offset; ứng dụng vẫn phải xử lý trường hợp nhiều phần tử trùng score và dữ liệu cập nhật giữa các trang.

### 6.3. Read model và chi phí đồng bộ

Mô hình truy vấn chuyên biệt tối ưu đường đọc nhưng tạo nghĩa vụ cập nhật:

~~~text
              Command: create/update order
                           |
                           v
                      Ghi Order
                           |
              +------------+------------+
              |                         |
              v                         v
       cập nhật Set status        cập nhật Sorted Set thời gian
              |                         |
              +------------+------------+
                           |
                           v
               Read model sẵn cho endpoint
~~~

Khi một lệnh cập nhật nhiều key, cần xác định mức bảo đảm nhất quán. Redis transaction hoặc Lua script có thể hỗ trợ cập nhật nguyên tử trong phạm vi lệnh và topology phù hợp, nhưng không được mặc định mọi thao tác Java gọi tuần tự là một giao dịch duy nhất. Với Redis Cluster, lệnh đa key và Lua chịu ràng buộc về hash slot.

Nếu chọn cập nhật bất đồng bộ qua sự kiện, read model có thể **eventually consistent**: kết quả tìm kiếm có thể chậm hơn dữ liệu gốc một khoảng thời gian. Tùy nghiệp vụ, cần thiết kế retry, idempotency, thứ tự sự kiện và cơ chế tái xây dựng index khi có lỗi.

## 7. Denormalization: đổi một phần chi phí ghi lấy tốc độ đọc

Để tránh phải đọc `Customer` trong mỗi danh sách đơn hàng, có thể lưu thêm vài thuộc tính cần hiển thị vào `OrderSummary`:

~~~java
public record OrderSummary(
    String orderId,
    String customerId,
    String customerNameSnapshot,
    String status,
    long totalCents
) {
}
~~~

Lúc tạo đơn hàng, ứng dụng lấy `customerNameSnapshot` từ dữ liệu khách hàng và đưa vào read model. Endpoint liệt kê đơn hàng có thể đọc đủ thông tin mà không cần join liên tục.

Nhưng phải lựa chọn rõ **ngữ nghĩa dữ liệu**:

- Nếu tên khách hàng trên hóa đơn cần giữ nguyên tại thời điểm mua, `customerNameSnapshot` là dữ liệu lịch sử có chủ đích.
- Nếu màn hình phải luôn hiển thị tên hiện tại, dữ liệu sao chép cần được cập nhật khi khách hàng đổi tên hoặc phải truy xuất từ nguồn chính.

Denormalization phù hợp khi các mẫu truy vấn được biết trước và tần suất đọc đủ cao để biện minh cho chi phí cập nhật. Nếu liên tục sao chép nhiều thuộc tính động vào mọi thực thể liên quan, chi phí đồng bộ và nguy cơ lệch dữ liệu sẽ tăng mạnh.

## 8. Tìm kiếm toàn văn khác gì tìm bằng `@Indexed`?

**Tra cứu chính xác theo thuộc tính** và **tìm kiếm toàn văn** trả lời các loại câu hỏi khác nhau.

Ví dụ một sản phẩm có:

~~~text
id          = p-501
title       = Hướng dẫn Spring Data Redis
description = Xây dựng cache, repository và tìm kiếm dữ liệu trong Java
category    = programming
price       = 250000
~~~

| Nhu cầu | Ví dụ câu hỏi | Cơ chế phù hợp |
| --- | --- | --- |
| So khớp chính xác | Category bằng `programming`? | Secondary index hoặc TAG index |
| So khớp nhiều từ | Title chứa các từ `Spring` và `Redis`? | Full-text index |
| Tìm từ gần nghĩa/biến thể | `caching` so với `cache`? | Analyzer/stemming theo hỗ trợ của search engine |
| Tìm bất chấp lỗi gõ | Người dùng nhập từ sai một vài ký tự | Fuzzy query nếu search engine hỗ trợ |
| Xếp hạng | Bài nào liên quan nhất với truy vấn? | Scoring/ranking |
| Lọc và tìm văn bản | Từ `Redis` trong title, category `programming`, giá từ 100k đến 300k | Search query với TEXT, TAG, NUMERIC |

`@Indexed` trong Redis Repository không xây dựng inverted index cho các từ nằm trong `title` hoặc `description`. Nó là cơ chế ánh xạ giá trị thuộc tính sang ID, có thiết kế và giới hạn riêng.

**Không thể giải quyết nhu cầu full-text search chỉ bằng cách thêm `@Indexed` cho một `String` dài.** Việc tìm theo toàn bộ chuỗi bằng đúng giá trị vẫn khác tìm theo từ xuất hiện bên trong văn bản.

## 9. Redis Search / Redis Query Engine cho truy vấn nội dung

Khi bản phân phối và phiên bản Redis đang chạy hỗ trợ **Redis Search / Redis Query Engine**, ứng dụng có thể tạo search index và sử dụng các lệnh như `FT.CREATE`, `FT.SEARCH`. Chức năng này tồn tại trong những môi trường Redis có thành phần tìm kiếm tương ứng, ví dụ Redis Stack hoặc các bản Redis mới tích hợp Query Engine; cần kiểm tra khả năng thực tế của server và nhà cung cấp Redis đang sử dụng.

### 9.1. Tạo search index từ Hash

Giả sử ứng dụng ghi các Hash với key prefix `product:`:

~~~redis
HSET product:p-501 title "Spring Data Redis thực hành" description "Cache và repository trong Java" category "programming" price 250000
HSET product:p-502 title "Spring Security cơ bản" description "Xác thực và phân quyền ứng dụng" category "programming" price 180000
HSET product:p-503 title "Nấu ăn mỗi ngày" description "Các món ăn gia đình" category "cooking" price 120000
~~~

Tạo chỉ mục tìm kiếm:

~~~redis
FT.CREATE idx:products ON HASH PREFIX 1 "product:" SCHEMA title TEXT WEIGHT 3 description TEXT category TAG price NUMERIC SORTABLE
~~~

Ý nghĩa các thành phần:

| Thành phần | Công dụng |
| --- | --- |
| `idx:products` | Tên search index |
| `ON HASH` | Lập chỉ mục trên các Redis Hash |
| `PREFIX 1 "product:"` | Chỉ lấy key bắt đầu bằng prefix này |
| `title TEXT WEIGHT 3` | Field văn bản, tăng trọng số khi đánh giá mức liên quan |
| `description TEXT` | Field văn bản có thể tìm từ |
| `category TAG` | Field nhãn phù hợp cho lọc chính xác |
| `price NUMERIC SORTABLE` | Field số cho lọc theo khoảng giá và khả năng sắp xếp |

Lệnh tạo index phía trên **độc lập với annotation `@Indexed`** của Spring Data Redis. `FT.CREATE` là lệnh của Query Engine và duy trì một hệ thống chỉ mục tìm kiếm riêng.

### 9.2. Thực hiện truy vấn tìm kiếm

Tìm tài liệu có từ `Redis` trong tiêu đề:

~~~redis
FT.SEARCH idx:products "@title:Redis"
~~~

Kết hợp tìm từ, bộ lọc category và khoảng giá:

~~~redis
FT.SEARCH idx:products "(@title:Redis | @description:Redis) @category:{programming} @price:[100000 300000]" LIMIT 0 20
~~~

Cú pháp có các ý nghĩa:

- `@title:Redis`: tìm từ trên field `title`.
- Dấu `|`: biểu diễn phép OR trong biểu thức tìm kiếm.
- `@category:{programming}`: lọc giá trị Tag `programming`.
- `@price:[100000 300000]`: lọc khoảng giá bao gồm hai đầu.
- `LIMIT 0 20`: lấy một phần kết quả, giới hạn số bản ghi trả về.

Đây là truy vấn **tìm kiếm trên dữ liệu đã index**, khác với việc Spring Data Redis Repository tự phân tích tên phương thức `findBy...`. Tùy client, ứng dụng Java có thể cần dùng thư viện hỗ trợ Redis Query Engine hoặc gửi các command tìm kiếm qua API Redis phù hợp. Không thể giả định mọi phiên bản `RedisTemplate` đều cung cấp trực tiếp một repository API với đầy đủ DSL `FT.SEARCH`.

### 9.3. Lưu ý khi tìm kiếm tiếng Việt

Tìm kiếm tiếng Việt có dấu và từ ghép không đơn thuần là tìm chuỗi con. Cần quan tâm tới:

- **Phân tách từ:** Tiếng Việt dùng khoảng trắng giữa các âm tiết, trong khi một từ có thể gồm nhiều âm tiết; chiến lược tokenizer ảnh hưởng kết quả.
- **Dấu và Unicode:** Quy tắc chuẩn hóa Unicode, giữ hay bỏ dấu và cách xử lý chữ hoa/chữ thường cần được quyết định rõ.
- **Từ dừng, từ đồng nghĩa, stemming:** Không phải analyzer của mọi search engine đều phù hợp hoặc hỗ trợ tiếng Việt đầy đủ.
- **Lỗi chính tả:** Một số dạng fuzzy search có thể cải thiện khả năng chịu lỗi nhưng vẫn cần đo precision và recall.
- **Xếp hạng:** Trọng số `title` và `description`, field boost và dữ liệu click có thể ảnh hưởng chất lượng kết quả.

Không nên giả định chỉ cần tạo `TEXT` index là có ngay tách từ tiếng Việt, hiểu ngữ nghĩa hoặc tìm đồng nghĩa đạt chất lượng. Với hệ thống tìm kiếm tiếng Việt lớn, hãy xây dựng tập truy vấn mẫu và đánh giá analyzer/engine theo dữ liệu thực tế.

### 9.4. Search index không tạo JOIN tùy ý

Có search index không đồng nghĩa có SQL JOIN. Search Query Engine cho phép tìm và lọc dữ liệu được index theo schema và tập khả năng của nó; quan hệ giữa các entity vẫn cần được thiết kế. Có thể đưa những thuộc tính quan trọng của nhiều entity vào một **search document** phục vụ use case cụ thể.

Ví dụ để tìm đơn hàng theo tên khách hàng và trạng thái, tạo một document:

~~~text
search:order:o-9001
  orderId      = o-9001
  customerId   = c-101
  customerName = Nguyễn Lan
  status       = PAID
  totalCents   = 125000
~~~

Đây là **denormalized search document**. Khi khách hàng đổi tên, search document có thể cần cập nhật. Cơ chế phân phối và đồng bộ cập nhật phải được thiết kế riêng; search engine không tự suy ra quan hệ chỉ từ `customerId`.

## 10. Khi nào dùng công cụ tìm kiếm riêng?

Nếu Redis chủ yếu là cache hoặc nơi lưu trạng thái có TTL, còn dữ liệu chính nằm trong hệ quản trị khác, cần cân nhắc để **cơ sở dữ liệu chính** hoặc **search engine chuyên dụng** xử lý những truy vấn không phù hợp với Redis Repository.

Ví dụ kiến trúc đọc/ghi:

~~~text
                        Application
                            |
                +-----------+-----------+
                |                       |
                v                       v
           Command Service         Search API
                |                       |
                v                       v
       Database nguồn chính       Search Engine
                |                       ^
                v                       |
          Change Event / Outbox / CDC --+
                |
                v
       Redis cache cho hot keys
~~~

Tùy use case, công cụ tìm kiếm có thể là Redis Query Engine hoặc một hệ thống riêng như OpenSearch/Elasticsearch. Khi đồng bộ bất đồng bộ từ database nguồn chính sang search index, phải chấp nhận một khoảng trễ có thể quan sát được giữa ghi và tìm kiếm.

Những bài toán nên cân nhắc công cụ chuyên dụng:

- Tìm kiếm toàn văn đa trường, nhiều loại dữ liệu, phân tích ngôn ngữ sâu.
- Tìm có mức độ liên quan, autocomplete, fuzzy matching, typo tolerance.
- Điều kiện lọc biến thiên liên tục theo nhiều field; sorting/faceting/aggregation phức tạp.
- Search dashboard, analytic query và truy vấn trên số lượng tài liệu lớn.
- Cần kiểm soát riêng chất lượng relevance, schema và vòng đời reindex.

Ngược lại, nếu chỉ cần tra cứu `customerId` để lấy đơn hàng và kết quả nhỏ, một Redis Set hoặc `@Indexed` có thể đơn giản, hiệu quả hơn.

## 11. Cơ chế đồng bộ và tính nhất quán của truy vấn

Chọn thêm index hoặc read model đồng nghĩa dữ liệu có thể tồn tại dưới nhiều hình thức:

~~~text
Nguồn dữ liệu gốc
   |
   +-- Redis Hash
   |
   +-- Redis Repository secondary index (Set)
   |
   +-- Read model thủ công (Set / Sorted Set)
   |
   +-- Search document / search index
~~~

Nếu các nhánh được cập nhật độc lập, một thao tác có thể thay đổi dữ liệu gốc nhưng chưa cập nhật các index liên quan. Ví dụ:

1. Đơn hàng `o-9001` đổi trạng thái từ `NEW` sang `PAID`.
2. Hash được cập nhật thành công.
3. Sự kiện cập nhật search index gặp lỗi hoặc chưa được xử lý.
4. Một người dùng tìm đơn hàng `PAID` và tạm thời không thấy `o-9001`.

Thiết kế cần trả lời:

| Câu hỏi | Ý nghĩa thiết kế |
| --- | --- |
| Nơi nào là nguồn dữ liệu chính? | Quyết định dữ liệu nào được dùng để khôi phục khi index lệch |
| Ghi index đồng bộ hay bất đồng bộ? | Đánh đổi độ trễ ghi và tính nhất quán kết quả |
| Nếu cập nhật một phần bị lỗi thì sao? | Retry, idempotency và cơ chế hòa giải dữ liệu |
| Bản ghi cũ được index lại thế nào? | Backfill/rebuild index có checkpoint, tránh bỏ sót thay đổi |
| Xóa hoặc TTL hết hạn có xóa index không? | Tránh membership mồ côi hoặc search document lỗi thời |
| Kết quả tìm kiếm có được xem là dữ liệu nghiệp vụ cuối cùng không? | Có thể cần tải lại và xác thực trạng thái gốc trước hành động quan trọng |

### Không mặc định Redis Repository thực thi một giao dịch quan hệ

Từ ngữ `Repository` trong Spring Data biểu diễn một abstraction truy cập dữ liệu. Nó **không bảo đảm** cùng tính chất transaction, khóa ngoại, JOIN hoặc isolation của JPA.

Khi cần ràng buộc xuyên nhiều key, phải thiết kế theo phạm vi atomicity của các lệnh Redis và topology triển khai. Các thao tác trên Redis Cluster còn chịu giới hạn hash slot đối với nhiều lệnh đa key. Một số bài toán có thể giải quyết bằng Lua script/transaction đúng phạm vi, nhưng những quy trình trải qua Redis và một hệ lưu trữ khác thường cần cơ chế nhất quán ở cấp ứng dụng.

### TTL và những bản ghi chỉ mục còn sót

Redis Hash có thể hết hạn mà tập chỉ mục phụ chưa được dọn tức thì nếu quá trình nhận keyspace notification hoặc logic cleanup không hoạt động đúng. Spring Data Redis có cơ chế hỗ trợ xử lý expiration events, nhưng không nên mặc định mọi môi trường đều nhận được sự kiện đầy đủ, đặc biệt khi listener tạm ngừng.

Nếu index còn ID của Hash đã hết hạn, truy vấn có thể phải bỏ qua kết quả thiếu thực thể và một quá trình dọn dẹp riêng có thể cần thiết. Với search document được tạo từ dữ liệu có TTL, phải xác định rõ liệu document tìm kiếm cũng hết hạn, được xóa bằng sự kiện, hay cần một job đối soát.

## 12. Kiểm thử các ranh giới quan trọng

Các bài kiểm thử không nên chỉ chứng minh rằng `save` và `findById` hoạt động. Cần thể hiện được hành vi của chính kiến trúc truy vấn.

Ví dụ một integration test Spring Data Redis cho đường kết hợp hai repository:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CustomerOrderQueryIntegrationTest {

    @Autowired CustomerRepository customers;
    @Autowired OrderRepository orders;
    @Autowired CustomerOrderQueryService service;

    @Test
    void loadsOrdersThroughIndexedCustomerId() {
        String suffix = UUID.randomUUID().toString();
        String customerId = "c-" + suffix;
        String orderId = "o-" + suffix;

        try {
            customers.save(new Customer(
                customerId, suffix + "@example.test", "Nguyễn Lan"
            ));
            orders.save(new Order(
                orderId, customerId, "PAID", 125000
            ));

            CustomerOrderQueryService.CustomerOrders result =
                service.loadCustomerOrders(customerId);

            assertThat(result.customer().getId())
                .isEqualTo(customerId);
            assertThat(result.orders())
                .extracting(Order::getId)
                .contains(orderId);
        } finally {
            orders.deleteById(orderId);
            customers.deleteById(customerId);
        }
    }
}
~~~

Kiểm thử cần chạy trong ngữ cảnh Spring Boot có Redis Repository được kích hoạt và kết nối tới Redis test thật, chẳng hạn Redis do Testcontainers cung cấp. Đoạn mã trên giả định hạ tầng kết nối Redis test đã được cấu hình; không chạy với Redis sản xuất.

Ngoài trường hợp thành công, những kịch bản cần có bằng chứng phù hợp ở tầng tích hợp hoặc hệ thống là:

- Đổi `customerId` hoặc `status` rồi xác nhận kết quả truy vấn theo index phản ánh cập nhật.
- Xóa bản ghi hoặc cho TTL hết hạn rồi quan sát cách hệ thống xử lý index hoặc read model.
- Thêm index mới trên tập dữ liệu đã tồn tại, thực hiện backfill và xác nhận dữ liệu cũ có thể tìm được.
- Thử một truy vấn chỉ dùng toán tử/field được Redis Repository hỗ trợ; kiểm tra lỗi cấu hình hoặc truy vấn không được hỗ trợ ngay khi khởi tạo/chạy.
- Với search engine, xác minh tài liệu mới/cập nhật/xóa xuất hiện hoặc biến mất trong khoảng thời gian nhất quán mà hệ thống chấp nhận.
- Với tính năng tiếng Việt, dùng tập dữ liệu có dấu, không dấu và từ nhiều âm tiết để đo kết quả thực tế.

Nếu bài toán cần lọc hàng chục nghìn kết quả, ngoài tính đúng còn phải đo thời gian truy vấn, số lệnh Redis, dung lượng bộ nhớ và số lượng key/index trong một môi trường dữ liệu đại diện. Một test chỉ có hai bản ghi không nói được nhiều về chi phí trong sản xuất.

## 13. Các sai lầm thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Mong `@Reference` tự JOIN nhiều entity | Tham chiếu chỉ hỗ trợ mô hình hóa quan hệ ở tầng mapping | Truy vấn nhiều bước hoặc thiết kế read model |
| Mong `@Indexed` tìm chuỗi con trong văn bản | Redis Repository secondary index không phải full-text index | Dùng search index/công cụ tìm kiếm phù hợp |
| Viết derived query giống JPA rồi nhận lỗi hoặc kết quả không đúng | Redis Repository chỉ hỗ trợ tập toán tử/truy vấn riêng | Kiểm tra khả năng hỗ trợ của store module |
| Lấy toàn bộ Hash rồi lọc trên Java | Không có index phù hợp với câu hỏi | Thiết kế lookup key, Set/Sorted Set hoặc công cụ query |
| Dùng `KEYS` cho endpoint tìm kiếm | Quét toàn bộ không gian key | Tránh `KEYS` trên production path; xây dựng index |
| Dữ liệu Hash đúng nhưng lookup theo field sai | Secondary index bị thiếu, cũ hoặc đã bị bỏ qua khi sửa trực tiếp | Đồng bộ đường ghi; có kế hoạch rebuild |
| Sau khi thêm `@Indexed`, dữ liệu cũ không tìm thấy | Annotation không tự backfill | Reindex/backfill có kiểm soát |
| Kết quả phân trang thay đổi giữa các lần đọc | Tập dữ liệu thay đổi, index/order không ổn định | Định nghĩa thứ tự, cursor và mức nhất quán |
| Tạo `FT.CREATE` nhưng repository không dùng search index | Hai cơ chế lập chỉ mục khác nhau | Truy vấn qua API Search/Query Engine tương ứng |
| Kết quả tiếng Việt không như mong muốn | Tokenizer/analyzer/chuẩn hóa chưa phù hợp | Chọn và đánh giá chiến lược phân tích tiếng Việt |
| Kết quả tìm kiếm chậm phản ánh dữ liệu mới | Đồng bộ index bất đồng bộ | Thiết kế SLA cho index lag, retry và đối soát |
| Tốn nhiều bộ nhớ Redis sau khi thêm index | Mỗi field và mỗi giá trị phân biệt sinh thêm cấu trúc index | Chỉ index theo truy vấn cần thiết, theo dõi memory |

## 14. Chọn chiến lược nào cho từng nhu cầu?

| Nhu cầu chính | Chiến lược ưu tiên | Khi cần mở rộng |
| --- | --- | --- |
| Lấy entity bằng ID | `findById` / key lookup | Cache/đọc theo batch nếu cần |
| Tìm email hoặc trạng thái bằng giá trị chính xác | `@Indexed` cho Redis Repository | Chuyển read model nếu tổ hợp điều kiện phức tạp |
| Tìm các đơn hàng của một khách hàng | Index trên `customerId` hoặc Set quan hệ | Sorted Set nếu cần thứ tự/range thường xuyên |
| Hiển thị tên khách hàng trong danh sách đơn hàng | Application-side join với số lượng nhỏ | Denormalized read model khi đường đọc nóng |
| Tìm đơn hàng theo nhiều bộ lọc linh hoạt | Read model dựa trên truy vấn chủ đạo | Query engine hoặc nơi lưu truy vấn linh hoạt |
| Tìm sản phẩm theo từ khóa, độ liên quan và khoảng giá | Redis Search/Query Engine nếu hạ tầng hỗ trợ | Search engine chuyên dụng nếu yêu cầu phức tạp |
| Báo cáo nhóm/tổng hợp trên dữ liệu lớn | Tính trước số liệu, hệ OLAP hoặc database phù hợp | Không quét mọi Redis key theo mỗi request |
| Search tiếng Việt nhiều từ, autocomplete, fuzzy | Engine có analyzer và query phù hợp | Đánh giá chất lượng thực tế trước triển khai |

Không có một chỉ mục nào tối ưu cho mọi truy vấn. Hãy bắt đầu từ **câu hỏi mà người dùng thật sự cần trả lời**, tần suất truy vấn, số lượng bản ghi, thứ tự sắp xếp, độ trễ chấp nhận được và yêu cầu nhất quán; từ đó chọn mô hình dữ liệu và index.

## 15. Tổng kết

Spring Data Redis Repository phù hợp với truy xuất theo ID và một số truy vấn dựa trên thuộc tính đã lập chỉ mục. Nó không có SQL JOIN tổng quát, không mặc nhiên hỗ trợ mọi điều kiện truy vấn tùy ý và không tự tạo full-text index từ `@Indexed`.

Khi dữ liệu trải qua nhiều thực thể, ứng dụng có thể **kết hợp ở tầng service** hoặc tạo **read model/denormalized document** phù hợp với use case. Khi cần thứ tự và xếp hạng có thể dự đoán, Redis Set và Sorted Set hỗ trợ những mẫu truy cập được thiết kế trước. Với tìm kiếm văn bản, lọc phức tạp, scoring hoặc phân tích ngôn ngữ, cần đánh giá Redis Search/Query Engine hoặc hệ thống tìm kiếm chuyên dụng.

Giới hạn cốt lõi không chỉ nằm ở cú pháp truy vấn: **mọi chỉ mục và dữ liệu sao chép đều có vòng đời**, gồm tạo mới, cập nhật, xóa, hết hạn, backfill và đối soát khi có lỗi. Một thiết kế tốt chọn đúng công cụ theo câu hỏi nghiệp vụ và định nghĩa rõ ai chịu trách nhiệm giữ các hình thức dữ liệu đó nhất quán.

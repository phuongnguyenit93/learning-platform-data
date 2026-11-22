# Kết hợp điều kiện truy vấn và đối chiếu khả năng hỗ trợ

## 1. Bài toán: tìm dữ liệu theo nhiều điều kiện trong Redis

Giả sử một ứng dụng Spring Boot lưu thông tin đơn hàng trong Redis. Người dùng muốn tìm:

- Đơn có **trạng thái PAID** và thuộc **kênh WEB**.
- Đơn có **trạng thái PAID** hoặc thuộc **kênh MOBILE**.
- Đơn **đang hoạt động**, có **tổng tiền lớn hơn 500.000 đồng**, sắp xếp từ mới đến cũ.
- Đơn có trạng thái PAID và **địa điểm giao hàng gần** một vị trí.

Các yêu cầu trên đều là “truy vấn kết hợp điều kiện”, nhưng chúng không có cùng mức hỗ trợ trong Spring Data Redis. Sự khác biệt đến từ cách Redis lưu dữ liệu và cách Spring Data Redis xây dựng truy vấn.

Trong cơ sở dữ liệu quan hệ, ta quen với:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
  AND channel = 'WEB'
ORDER BY created_at DESC;
~~~

Redis thông thường không có cơ chế thực thi SQL như trên cho các Redis Hash của Repository. **Spring Data Redis Repository** giải quyết một số truy vấn bằng **chỉ mục phụ (secondary indexes)**, thường được biểu diễn bằng các Redis Set chứa định danh thực thể. Các điều kiện đơn giản như bằng nhau, `AND` và `OR` có thể quy về các phép toán tập hợp. Các loại điều kiện khác đòi hỏi đối chiếu khả năng hỗ trợ cụ thể.

Mục tiêu của bài học thuộc chương **Chỉ mục và truy vấn** là biết khi nào có thể ghép điều kiện bằng Repository, khi nào không nên suy diễn từ cú pháp của Spring Data nói chung, và cách chọn giải pháp phù hợp khi Redis Repository chưa đáp ứng được.

## 2. Nền tảng: chỉ mục phụ liên kết giá trị với tập ID

### 2.1. Thực thể được lưu dưới dạng Redis Hash

Ta dùng thực thể minh họa:

~~~java
package com.example.orders;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orders")
public class Order {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String channel;

    @Indexed
    private Boolean active;

    private long totalAmount;
    private Instant createdAt;

    public Order() {
    }

    public Order(
            String id,
            String status,
            String channel,
            Boolean active,
            long totalAmount,
            Instant createdAt) {
        this.id = id;
        this.status = status;
        this.channel = channel;
        this.active = active;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getChannel() {
        return channel;
    }

    public void setChannel(String channel) {
        this.channel = channel;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }

    public long getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(long totalAmount) {
        this.totalAmount = totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Trong trường hợp này:

- `@RedisHash("orders")` xác định không gian khóa của thực thể.
- `@Id` xác định định danh.
- `@Indexed` trên `status`, `channel` và `active` yêu cầu Spring Data Redis duy trì các chỉ mục tương ứng.
- `totalAmount` và `createdAt` vẫn được lưu trong thực thể, nhưng **chưa có chỉ mục để thực hiện truy vấn theo giá trị của chúng**.

Với một số đơn hàng, dữ liệu logic có thể là:

| ID | Status | Channel | Active | Total amount |
|---|---|---|---|---:|
| o-101 | PAID | WEB | true | 700000 |
| o-102 | PAID | MOBILE | true | 400000 |
| o-103 | PENDING | WEB | true | 300000 |
| o-104 | CANCELLED | STORE | false | 900000 |
| o-105 | PAID | WEB | false | 200000 |

Khi `repository.save(order)` được gọi, Spring Data Redis lưu thực thể và cập nhật những khóa chỉ mục phụ đã cấu hình. Một mô hình minh họa của các Set là:

~~~text
orders:status:PAID      = {o-101, o-102, o-105}
orders:status:PENDING   = {o-103}
orders:status:CANCELLED = {o-104}

orders:channel:WEB      = {o-101, o-103, o-105}
orders:channel:MOBILE   = {o-102}
orders:channel:STORE    = {o-104}

orders:active:1         = {o-101, o-102, o-103}
orders:active:0         = {o-104, o-105}
~~~

Tên khóa ví dụ thể hiện quy ước chỉ mục cơ bản của Spring Data Redis; cách biểu diễn giá trị và metadata có thể khác theo kiểu thuộc tính, bộ chuyển đổi và phiên bản thư viện. Những Set này chứa **ID**, không chứa toàn bộ đối tượng `Order`.

Nếu chương trình chỉ lưu JSON qua `RedisTemplate.opsForValue().set(...)` mà không sử dụng cơ chế Repository, `@Indexed` **không tự tạo** các tập chỉ mục trên.

### 2.2. Một phép tìm bằng nhau thực chất là đọc tập ID

Muốn tìm đơn có `status = PAID`:

~~~text
Truy vấn: status = PAID
           |
           v
Set: orders:status:PAID
           |
           v
{o-101, o-102, o-105}
           |
           v
Đọc các Hash orders:o-101, orders:o-102, orders:o-105
           |
           v
Danh sách đối tượng Order
~~~

Đây là cơ sở để kết hợp nhiều điều kiện: xử lý **tập ID ứng viên** trước rồi dựng lại các thực thể.

## 3. Điều kiện AND: lấy giao của các tập chỉ mục

Yêu cầu: lấy đơn có `status = PAID` **và** `channel = WEB`.

Gọi:

~~~text
A = {o-101, o-102, o-105}     (status = PAID)
B = {o-101, o-103, o-105}     (channel = WEB)

A ∩ B = {o-101, o-105}
~~~

Trong Redis, phép giao tập hợp tương ứng với `SINTER`:

~~~redis
SINTER orders:status:PAID orders:channel:WEB
~~~

Trong **Redis Repository**, có thể biểu diễn điều kiện bằng phương thức truy vấn suy ra từ tên (derived query method):

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByStatusAndChannel(
            String status,
            String channel
    );
}
~~~

Cách gọi:

~~~java
List<Order> paidWebOrders =
        repository.findByStatusAndChannel("PAID", "WEB");
~~~

Tên phương thức có thể được hiểu là:

~~~text
findBy + Status + And + Channel
         equality      equality
~~~

**Điều kiện tiên quyết:** cả `status` lẫn `channel` phải có chỉ mục Redis Repository phù hợp. Nếu chỉ đánh chỉ mục `status`, việc thêm `AndChannel` trong tên hàm không tự tạo khả năng tìm theo `channel`.

Ở cấp độ dữ liệu, phép giao làm giảm tập ID cần nạp. Đó là khác biệt đáng kể so với cách lấy toàn bộ đơn `PAID` rồi đọc từng Hash và kiểm tra `channel` bằng Java.

## 4. Điều kiện OR: lấy hợp của các tập chỉ mục

Yêu cầu: tìm đơn có `status = PAID` **hoặc** `channel = WEB`.

~~~text
A = {o-101, o-102, o-105}     (status = PAID)
B = {o-101, o-103, o-105}     (channel = WEB)

A ∪ B = {o-101, o-102, o-103, o-105}
~~~

Redis có phép hợp `SUNION`:

~~~redis
SUNION orders:status:PAID orders:channel:WEB
~~~

Repository có thể khai báo:

~~~java
List<Order> findByStatusOrChannel(
        String status,
        String channel
);
~~~

Ví dụ:

~~~java
List<Order> orders =
        repository.findByStatusOrChannel("PAID", "WEB");
~~~

Một ID nằm trong cả hai Set chỉ xuất hiện **một lần** trong kết quả tập hợp Redis. Tuy nhiên, hãy nhớ rằng tập hợp không có thứ tự nghiệp vụ mặc định. Nếu cần thứ tự cụ thể, phải xem xét cơ chế sắp xếp riêng.

Về ý nghĩa:

| Điều kiện | Phép toán tập hợp | Kết quả ví dụ |
|---|---|---|
| `status = PAID AND channel = WEB` | Giao: `SINTER` | `o-101, o-105` |
| `status = PAID OR channel = WEB` | Hợp: `SUNION` | `o-101, o-102, o-103, o-105` |

Điều kiện `OR` thường làm **rộng** tập kết quả. Một truy vấn có hai điều kiện nhưng dùng `OR` vẫn có thể trả rất nhiều bản ghi và tiêu tốn đáng kể bộ nhớ, thời gian tải thực thể.

## 5. Đối chiếu chính xác từ khóa hỗ trợ

### 5.1. Không thể suy ra Redis hỗ trợ mọi từ khóa của Spring Data

Spring Data Commons cung cấp cú pháp tổng quát để phân tích tên phương thức, nhưng **cú pháp được bộ phân tích nhận diện không đồng nghĩa Redis Repository có thể thực thi truy vấn ấy**.

Ví dụ, ở những mô-đun lưu trữ khác, người học có thể gặp:

~~~java
findByTotalAmountGreaterThan(...)
findByCreatedAtBetween(...)
findByCustomerNameContaining(...)
findByStatusNot(...)
findByStatusIn(...)
~~~

Không nên mặc định các phương thức này hoạt động như ở Spring Data JPA. Cần tham khảo **bảng khả năng hỗ trợ riêng của Spring Data Redis** đúng phiên bản đang dùng.

Với Spring Data Redis 3.5, các nhóm từ khóa truy vấn được tài liệu Redis-specific liệt kê trực tiếp gồm:

| Nhóm | Ví dụ phương thức | Cơ chế hoặc ý nghĩa |
|---|---|---|
| Bằng nhau | `findByStatus(...)` | Tìm theo chỉ mục của một giá trị |
| `Is`, `Equals` | `findByStatusIs(...)`, `findByStatusEquals(...)` | Các cách diễn đạt điều kiện bằng nhau |
| `And` | `findByStatusAndChannel(...)` | Giao các tập ID được đánh chỉ mục |
| `Or` | `findByStatusOrChannel(...)` | Hợp các tập ID được đánh chỉ mục |
| `IsTrue` | `findByActiveIsTrue()` | Tìm theo chỉ mục thuộc tính boolean có giá trị true |
| `IsFalse` | `findByActiveIsFalse()` | Tìm theo chỉ mục thuộc tính boolean có giá trị false |
| `Top`, `First` | `findFirst10ByStatus(...)` | Giới hạn số phần tử kết quả theo khả năng của Repository |

Các từ khóa như `GreaterThan`, `LessThan`, `Between`, `Containing`, `Like`, `Regex`, `Not`, `In` **không nằm trong bảng từ khóa truy vấn cơ bản của Redis Repository 3.5**. Trước khi dùng, phải xác nhận hỗ trợ thực tế của đúng phiên bản và cơ chế dữ liệu; nếu không có, hãy chọn cách truy vấn khác.

Không nên kết luận quá mức rằng Redis nói chung “không thể” lọc khoảng giá trị hoặc tìm kiếm toàn văn. Redis có các kiểu dữ liệu/lệnh chuyên biệt và có thể có Redis Query Engine (trước đây thường được gọi là RediSearch). Chỉ là **Spring Data Redis Repository dựa trên chỉ mục Set thông thường không tự biến mọi phép toán ấy thành truy vấn được hỗ trợ**.

### 5.2. Ví dụ điều kiện boolean

Khai báo:

~~~java
List<Order> findByActiveIsTrue();

List<Order> findByActiveIsFalse();
~~~

Cách gọi:

~~~java
List<Order> activeOrders = repository.findByActiveIsTrue();
List<Order> inactiveOrders = repository.findByActiveIsFalse();
~~~

Với `@Indexed private Boolean active;`, giá trị boolean được ánh xạ vào cơ chế chỉ mục tương ứng. Mẫu truy vấn này phù hợp khi muốn tra cứu theo một cờ cụ thể.

Nếu muốn kết hợp boolean với các điều kiện khác, nên kiểm tra chính xác phương thức được Spring Data Redis tạo ra. Cách an toàn để giải thích truy vấn hai thuộc tính đã đánh chỉ mục là dùng điều kiện bằng nhau tường minh, ví dụ:

~~~java
List<Order> findByStatusAndActive(
        String status,
        Boolean active
);
~~~

### 5.3. Bảng quyết định theo nhu cầu nghiệp vụ

| Nhu cầu | Redis Repository với chỉ mục thông thường | Điều cần kiểm tra |
|---|---|---|
| `status = PAID` | Có, nếu đã đánh chỉ mục | Giá trị chỉ mục và dữ liệu thực thể nhất quán |
| `status = PAID AND channel = WEB` | Có, qua `And` | Cả hai thuộc tính có chỉ mục |
| `status = PAID OR channel = WEB` | Có, qua `Or` | Kích thước tập kết quả |
| `active = true` | Có, qua `IsTrue` | Boolean được đánh chỉ mục |
| `totalAmount > 500000` | Không được bảo đảm bởi bảng từ khóa cơ bản | Cần cấu trúc/trình xử lý khác cho điều kiện khoảng |
| `createdAt BETWEEN a AND b` | Không được bảo đảm bởi bảng từ khóa cơ bản | Cần chỉ mục theo thời gian và truy vấn khoảng phù hợp |
| `name CONTAINING 'abc'` | Không nên mặc định có | Tìm kiếm văn bản cần giải pháp phù hợp |
| `status != CANCELLED` | Không nên suy ra có `Not` | Cần định nghĩa tập ứng viên và phép loại trừ |
| Lọc theo tọa độ gần | Có đường truy vấn địa lý riêng với `@GeoIndexed` | Không tự kết hợp `near`/`within` với điều kiện khác |
| Lọc rồi sắp xếp theo thời gian | Có phương thức sắp xếp | Thứ tự có thể được tính ở phía ứng dụng sau khi tải kết quả |
| Lọc có phân trang | Có khả năng hỗ trợ paging ở Repository | Chi phí lấy và sắp xếp tập ứng viên |

Điểm mấu chốt là **đối chiếu từng phép toán với khả năng thực thi của Redis và Spring Data Redis**, thay vì chỉ nhìn tên phương thức có vẻ hợp lệ.

## 6. Kết hợp nhiều AND/OR và giới hạn của diễn đạt bằng tên phương thức

Đối với điều kiện hai thuộc tính, `And` và `Or` tương đối dễ hiểu. Nhưng truy vấn nghiệp vụ thường phức tạp hơn:

~~~text
(status = PAID AND channel = WEB)
OR
(status = PENDING AND channel = MOBILE)
~~~

Hoặc:

~~~text
status = PAID
AND
(channel = WEB OR channel = MOBILE)
~~~

Về toán học, có thể biểu diễn:

~~~text
(A ∩ B) ∪ (C ∩ D)

A ∩ (B ∪ C)
~~~

Redis Set cho phép kết hợp phép giao và hợp về mặt dữ liệu. Tuy nhiên, cách phân tích biểu thức kết hợp trong **tên phương thức Repository dài** có thể có quy tắc ưu tiên riêng, và bản thân API không có cú pháp đặt ngoặc trực tiếp như SQL.

Không nên tự suy luận rằng:

~~~java
findByStatusAndChannelOrActive(...)
~~~

luôn khớp với cách đặt ngoặc mà nghiệp vụ mong muốn. Khi điều kiện vượt ra ngoài những dạng đơn giản, hãy viết rõ **bảng chân trị** hoặc biểu thức tập hợp mong muốn và chọn cách triển khai có thể kiểm chứng.

Ví dụ tập hợp:

~~~text
A = status:PAID
B = channel:WEB
C = channel:MOBILE

Cần: A ∩ (B ∪ C)
~~~

Có thể tách thành hai truy vấn Repository đơn giản rồi gộp theo ID tại lớp dịch vụ **nếu tập kết quả được kiểm soát về kích thước**:

~~~java
public List<Order> paidWebOrMobile(
        OrderRepository repository) {

    List<Order> web =
            repository.findByStatusAndChannel("PAID", "WEB");
    List<Order> mobile =
            repository.findByStatusAndChannel("PAID", "MOBILE");

    Map<String, Order> unique = new LinkedHashMap<>();

    for (Order order : web) {
        unique.put(order.getId(), order);
    }
    for (Order order : mobile) {
        unique.put(order.getId(), order);
    }

    return new ArrayList<>(unique.values());
}
~~~

Các `import` cần thiết cho đoạn phương thức trên là:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
~~~

Ví dụ này thể hiện **logic kết hợp rõ ràng** và loại bỏ ID trùng. Nó phù hợp để học hoặc xử lý tập nhỏ. Với tập dữ liệu lớn, cách gọi hai truy vấn rồi tải mọi đối tượng vào bộ nhớ có thể trở nên tốn kém. Khi đó, nên tìm cách kết hợp **ID bằng tập hợp ở Redis**, hoặc thay đổi mô hình chỉ mục.

## 7. Kết hợp ID bằng Redis Set và đọc lại thực thể

Giả sử đã có hai tập chỉ mục:

~~~redis
SMEMBERS orders:status:PAID
SMEMBERS orders:channel:WEB
~~~

Với điều kiện `status = PAID AND channel = WEB`:

~~~redis
SINTER orders:status:PAID orders:channel:WEB
~~~

Với điều kiện `status = PAID OR channel = WEB`:

~~~redis
SUNION orders:status:PAID orders:channel:WEB
~~~

Để minh họa thao tác thủ công, ta có thể dùng `StringRedisTemplate` khi biết chắc các khóa chỉ mục chứa ID chuỗi theo cách cấu hình hiện tại:

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class IndexedOrderLookup {

    private final StringRedisTemplate redis;
    private final OrderRepository orders;

    public IndexedOrderLookup(
            StringRedisTemplate redis,
            OrderRepository orders) {
        this.redis = redis;
        this.orders = orders;
    }

    public List<Order> findPaidWebOrders() {
        Set<String> ids = redis.opsForSet().intersect(
                "orders:status:PAID",
                "orders:channel:WEB"
        );

        if (ids == null || ids.isEmpty()) {
            return List.of();
        }

        List<Order> result = new ArrayList<>();
        orders.findAllById(ids).forEach(result::add);
        return result;
    }
}
~~~

Luồng hoạt động:

~~~text
SINTER index-A index-B
           |
           v
     các ID giao nhau
           |
           v
 repository.findAllById(ids)
           |
           v
     các Order tương ứng
~~~

Cần hiểu những điểm sau:

- Đây là **ví dụ minh họa chỉ mục Set**. Tên khóa chỉ mục mặc định, cách mã hóa ID và metadata do Spring Data Redis quản lý có thể thay đổi theo cấu hình. Nếu dự án tùy biến keyspace hoặc serializer, phải lấy quy ước phù hợp thay vì sao chép cứng các tên khóa.
- `findAllById` không bảo đảm thứ tự giống thứ tự tập ID. Redis Set không có thứ tự ổn định.
- Có thể tồn tại một thời điểm ID vẫn trong tập chỉ mục nhưng thực thể đã bị xóa/hết hạn. Ứng dụng phải chấp nhận tình huống truy xuất không còn đối tượng.
- `SINTER` và `SUNION` có thể phải xử lý và trả về tập ID rất lớn. Chuyển việc kết hợp sang Redis không đồng nghĩa truy vấn có chi phí nhỏ.
- Khi cần truy vấn tùy biến, Spring Data Redis còn có cơ chế `RedisCallback` hoặc truy cập qua `RedisTemplate`/`RedisConnection`. Chúng cho phép điều khiển trực tiếp lệnh Redis, nhưng phần duy trì nhất quán chỉ mục vẫn phải được thiết kế cẩn thận.

Trong ví dụ, lựa chọn **Repository `findByStatusAndChannel`** thường đơn giản hơn. Chỉ đi xuống mức Set thủ công khi có nhu cầu rõ ràng mà Repository không biểu diễn được.

## 8. Sắp xếp và Top/First không có nghĩa Redis tự tạo chỉ mục sắp xếp

### 8.1. Sắp xếp kết quả truy vấn

Spring Data Redis Repository hỗ trợ cú pháp sắp xếp như:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByStatusOrderByCreatedAtDesc(String status);

    List<Order> findByStatus(String status, Sort sort);
}
~~~

Cách gọi:

~~~java
List<Order> newestPaid =
        repository.findByStatusOrderByCreatedAtDesc("PAID");

List<Order> oldestPaid = repository.findByStatus(
        "PAID",
        Sort.by(Sort.Direction.ASC, "createdAt")
);
~~~

Theo cơ chế Redis Repository, các tập chỉ mục không cung cấp thứ tự theo `createdAt`. Vì vậy, Spring Data Redis có thể dựng `Comparator` để **sắp xếp kết quả ở phía ứng dụng** sau khi tải các thực thể phù hợp.

Điều này khác với truy vấn dùng chỉ mục được sắp xếp ở hệ quản trị cơ sở dữ liệu quan hệ. Khi có hàng trăm nghìn đơn phù hợp, việc đọc dữ liệu rồi sắp xếp có thể tốn CPU và bộ nhớ.

Một điểm dễ nhầm: `@Indexed` trên `status` là chỉ mục dùng để **lọc**, không biến `createdAt` thành chỉ mục thời gian hay làm cho `ORDER BY` được Redis thực hiện miễn phí.

### 8.2. Giới hạn số kết quả

Spring Data Redis còn hỗ trợ dạng `Top` hoặc `First` trong tên phương thức, ví dụ:

~~~java
List<Order> findFirst10ByStatus(String status);

List<Order> findTop5ByChannel(String channel);
~~~

Các tên trên yêu cầu giới hạn số phần tử trả về. Tuy nhiên:

- Số lượng giới hạn không bảo đảm kết quả là “10 bản ghi mới nhất” nếu chưa định nghĩa thứ tự.
- Giới hạn phần tử không đồng nghĩa Redis chỉ cần đọc đúng chừng đó ID hoặc đối tượng trong toàn bộ quá trình truy vấn.
- Nếu có sắp xếp, cần xét nơi thực hiện sắp xếp và lượng dữ liệu phải tải trước khi giới hạn.

Với nhu cầu **“10 đơn mới nhất có status = PAID”** trên tập lớn, một Sorted Set riêng theo timestamp (ví dụ `ZADD` với điểm số là thời gian tạo) hoặc cơ chế tìm kiếm có chỉ mục phù hợp thường đáng xem xét hơn.

### 8.3. Phân trang có thể có chi phí ẩn

Spring Data Redis Repository có hỗ trợ truy vấn trả về bộ sưu tập thực thể với phân trang. Ví dụ dạng API:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Order> findByStatus(String status, Pageable pageable);
~~~

Nhưng `Pageable` không tự biến một Redis Set thành danh sách đã sắp xếp theo nhiều thuộc tính. Lúc dùng phân trang và sắp xếp, cần xem xét:

- Tổng số phần tử ứng viên theo chỉ mục.
- Chi phí dựng lại thực thể.
- Chi phí sắp xếp ở phía ứng dụng.
- Việc xác định tổng số phần tử cho `Page`.
- Dữ liệu thay đổi giữa các lần yêu cầu trang; không phải một ảnh chụp nhất quán.

Nếu ứng dụng liên tục cần trang thứ `N` theo `createdAt` trong một tập rất lớn, việc có `Pageable` trong chữ ký phương thức không đủ để bảo đảm thời gian phản hồi tốt.

## 9. Điều kiện khoảng giá trị và văn bản: nên chọn cấu trúc khác

### 9.1. Truy vấn khoảng số hoặc thời gian

Ví dụ:

~~~text
totalAmount >= 500000
createdAt nằm trong [start, end]
~~~

Chỉ mục `@Indexed` thông thường dựa trên **giá trị bằng nhau**; nó không tự tạo cấu trúc được sắp theo số tiền hoặc thời gian để tìm một khoảng liên tục.

Một Redis Sorted Set (ZSET) có thể phù hợp khi cần truy vấn theo điểm số:

~~~redis
ZADD orders:by-created-at 1760000000 o-101
ZADD orders:by-created-at 1760000300 o-102
ZADD orders:by-created-at 1760000600 o-103

ZRANGE orders:by-created-at 1760000000 1760000500 BYSCORE
~~~

Ví dụ trên dùng epoch seconds làm score và truy vấn hai mốc thời gian. Trong ứng dụng thực tế, cần xử lý độ chính xác của thời gian, ID trùng, cập nhật và xóa khỏi ZSET.

Với khoảng tiền:

~~~redis
ZADD orders:by-amount 700000 o-101
ZADD orders:by-amount 400000 o-102
ZADD orders:by-amount 300000 o-103

ZRANGE orders:by-amount 500000 +inf BYSCORE
~~~

Tuy nhiên, đây là **chỉ mục tùy chỉnh** do ứng dụng quản lý. Chỉ đặt `@Indexed` trên `totalAmount` và viết `findByTotalAmountGreaterThan` không tự bảo đảm được truy vấn ZSET như trên.

Kết hợp `status = PAID` với khoảng tiền có thể cần phép giao giữa tập ID chỉ mục trạng thái và danh sách ID theo điểm số, hoặc thiết kế một cấu trúc truy vấn khác. Chi phí triển khai/tính nhất quán phải được tính trước.

### 9.2. Truy vấn văn bản

Nhu cầu:

~~~text
Tìm đơn có ghi chú chứa "giao gấp"
Tìm sản phẩm có tên gần giống "tai nghe"
Tìm theo nhiều trường và xếp hạng độ phù hợp
~~~

Một Redis Set chỉ mục bằng nhau không tự làm được truy vấn chứa chuỗi, truy vấn gần đúng hoặc tìm kiếm toàn văn. Những bài toán này thường cần cơ chế lập chỉ mục văn bản chuyên dụng, chẳng hạn Redis Query Engine khi triển khai có hỗ trợ, hoặc một hệ thống tìm kiếm khác.

Cũng phải phân biệt **Spring Data Redis** với các thư viện khác dựa trên Redis Query Engine, chẳng hạn Redis OM Spring. Cùng dùng Redis và cú pháp Repository nhưng **tập toán tử được hỗ trợ không mặc nhiên giống nhau**.

## 10. Truy vấn địa lý: có hỗ trợ riêng nhưng không tùy ý kết hợp

Spring Data Redis hỗ trợ kiểu chỉ mục địa lý `@GeoIndexed` cho thuộc tính tọa độ thích hợp.

Minh họa một thực thể có địa điểm:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.GeoIndexed;

@RedisHash("stores")
public class Store {

    @Id
    private String id;

    @GeoIndexed
    private Point location;

    public Store() {
    }

    public Store(String id, Point location) {
        this.id = id;
        this.location = location;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Point getLocation() {
        return location;
    }

    public void setLocation(Point location) {
        this.location = location;
    }
}
~~~

Repository tìm theo vị trí:

~~~java
import java.util.List;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.repository.CrudRepository;

public interface StoreRepository
        extends CrudRepository<Store, String> {

    List<Store> findByLocationNear(
            Point point,
            Distance distance
    );

    List<Store> findByLocationWithin(Circle area);
}
~~~

Điểm cần nhớ từ tài liệu Spring Data Redis: **không thể tùy ý kết hợp `Near` và `Within` với các tiêu chí khác** trong những truy vấn Repository này.

Chẳng hạn, không nên mặc định một chữ ký như:

~~~java
// Không nên coi đây là truy vấn được Redis Repository hỗ trợ sẵn.
List<Store> findByLocationNearAndStatus(
        Point location,
        Distance distance,
        String status
);
~~~

sẽ được dịch thành “địa điểm gần **và** status phù hợp”. Nếu yêu cầu cần cả lọc địa lý và trạng thái, có thể phải dùng cấu trúc chỉ mục/truy vấn tùy chỉnh, hoặc một bộ máy truy vấn hỗ trợ phối hợp điều kiện đó.

**Nguyên tắc:** một hệ thống hỗ trợ từng điều kiện riêng lẻ không có nghĩa nó tự hỗ trợ mọi phép kết hợp của các điều kiện ấy.

## 11. Điều kiện trên thuộc tính lồng nhau và giới hạn tham chiếu

Một thực thể có thể chứa thuộc tính lồng nhau:

~~~java
public class ShippingAddress {

    @Indexed
    private String city;

    // Constructor, getter, setter...
}
~~~

Khi `Order` có trường `shippingAddress` và Spring Data Redis ánh xạ đối tượng lồng nhau, chỉ mục có thể tương ứng với đường dẫn như:

~~~text
orders:shippingAddress.city:HaNoi
~~~

Khi đó, phương thức truy vấn dạng:

~~~java
List<Order> findByShippingAddressCity(String city);
~~~

phải được hiểu theo đường dẫn thuộc tính và quy tắc ánh xạ của thực thể. Khi tên thuộc tính dễ gây nhập nhằng, Spring Data hỗ trợ dấu gạch dưới trong tên phương thức để định hướng việc phân tách đường dẫn, nhưng cú pháp cuối cùng vẫn phải phù hợp với mô hình dữ liệu.

Điều kiện quan trọng: **chỉ mục cho thuộc tính lồng nhau được hỗ trợ trong các trường hợp thích hợp, nhưng không thể tự giải quyết chỉ mục xuyên qua mọi kiểu tham chiếu đối tượng**. Theo tài liệu Spring Data Redis về secondary indexes, chỉ mục không được phân giải trên các tham chiếu (`references`).

Do đó, một mô hình lưu quan hệ dưới dạng tham chiếu không đồng nghĩa ta có thể truy vấn xuyên nhiều thực thể như phép `JOIN` trong SQL.

## 12. Tính nhất quán của chỉ mục khi truy vấn kết hợp

Redis Repository duy trì chỉ mục phụ khi lưu, xóa và xử lý vòng đời đối tượng qua cơ chế của nó. Nếu ứng dụng thay đổi dữ liệu mà **bỏ qua Repository**, chỉ mục có thể lỗi thời.

Ví dụ: một lệnh Redis trực tiếp đổi field `status`:

~~~redis
HSET orders:o-101 status CANCELLED
~~~

nhưng chỉ mục trạng thái vẫn chứa `o-101` trong:

~~~text
orders:status:PAID
~~~

thì truy vấn:

~~~java
repository.findByStatusAndChannel("PAID", "WEB");
~~~

có thể tìm ra ID không còn phản ánh dữ liệu thực tế. Việc đọc Hash cuối cùng có thể cho thấy `status = CANCELLED`; kết quả gây khó hiểu vì chỉ mục và thực thể không còn nhất quán.

Điều này nhắc ta rằng chỉ mục phụ trong Redis Repository là **dữ liệu được duy trì**, không phải công thức tự động tính lại mỗi lần truy vấn.

Đặc biệt cần xem xét:

1. **Thay đổi thuộc tính đã đánh chỉ mục:** cập nhật bằng đường ghi có quản lý chỉ mục.
2. **Xóa khóa bằng lệnh trực tiếp:** cân nhắc phần chỉ mục còn sót.
3. **TTL và sự kiện hết hạn:** phân biệt vòng đời Hash chính và chỉ mục phụ; cấu hình thông báo hết hạn có thể ảnh hưởng cách làm sạch.
4. **Nhiều tiến trình ghi cùng lúc:** tránh giả định toàn bộ chuỗi cập nhật Hash và mọi Set chỉ mục là một giao dịch nguyên tử xuyên nhiều khóa.
5. **Thay đổi cấu hình index sau khi đã có dữ liệu:** việc gắn `@Indexed` vào thuộc tính không bảo đảm mọi dữ liệu cũ đã được tái tạo chỉ mục. Có thể cần quy trình xây lại chỉ mục.
6. **Dữ liệu chuyển đổi từ JSON:** lưu cùng nội dung bằng `RedisTemplate.opsForValue()` không tự làm cho đối tượng xuất hiện trong các chỉ mục Repository.

## 13. Khi nào cần tránh quét toàn bộ khóa hoặc lọc thủ công?

Một cách triển khai ban đầu có thể là:

~~~java
// Không phù hợp để truy vấn thường xuyên trên Redis lớn:
Set<String> keys = redisTemplate.keys("orders:*");
~~~

Sau đó, ứng dụng đọc từng khóa, lọc `status`, `channel`, `createdAt` và tự sắp xếp.

Cách này có nhiều vấn đề:

- `KEYS` phải quét không gian khóa và có thể cản trở các yêu cầu khác.
- Mẫu `orders:*` còn có thể khớp **khóa chỉ mục phụ**, không chỉ Hash thực thể.
- Tải và giải mã hàng loạt đối tượng tiêu tốn băng thông, CPU và bộ nhớ phía ứng dụng.
- Dữ liệu đang thay đổi khiến kết quả kiểm kê không phải ảnh chụp nhất quán.
- Việc truy vấn lặp lại có tải cao có thể làm Redis trở thành điểm nghẽn.

`SCAN` phù hợp hơn `KEYS` cho tác vụ **duyệt quản trị** được chia thành các lượt, nhưng nó vẫn là quét chứ không phải chỉ mục truy vấn nghiệp vụ. Thay `KEYS` bằng `SCAN` không tự biến cách “tìm mọi khóa rồi lọc bằng Java” thành giải pháp tìm kiếm hiệu quả.

Nếu một điều kiện thường xuyên xuất hiện trong API, hãy cân nhắc chỉ mục được thiết kế theo chính điều kiện đó.

## 14. Lựa chọn giải pháp theo mức độ truy vấn

### 14.1. Trường hợp A — Nhiều điều kiện bằng nhau đơn giản

Yêu cầu:

~~~text
status = PAID AND channel = WEB
~~~

Cách phù hợp: đánh chỉ mục cho `status` và `channel`, dùng:

~~~java
List<Order> findByStatusAndChannel(String status, String channel);
~~~

Điều kiện bắt buộc: mỗi thuộc tính được hỗ trợ chỉ mục, các chỉ mục được duy trì nhất quán và số kết quả phù hợp với khả năng xử lý.

### 14.2. Trường hợp B — Nhiều nhóm điều kiện AND/OR có cấu trúc rõ ràng

Yêu cầu:

~~~text
(status = PAID AND channel = WEB)
OR
(status = PENDING AND channel = MOBILE)
~~~

Các phương án có thể cân nhắc:

- Dùng hai truy vấn đơn giản, kết hợp và loại ID trùng nếu tập nhỏ.
- Kết hợp Set ở Redis khi có chỉ mục phù hợp và biết rõ chi phí trả kết quả.
- Duy trì một chỉ mục tổng hợp cho truy vấn phổ biến, ví dụ trạng thái–kênh, nếu chi phí cập nhật chấp nhận được.

Không nên viết tên phương thức ngày càng dài mà không xác định lại biểu thức logic thực sự cần thực thi.

### 14.3. Trường hợp C — Có khoảng số, thời gian, thứ tự và phân trang lớn

Yêu cầu:

~~~text
status = PAID
AND createdAt >= start
ORDER BY createdAt DESC
LIMIT 20
~~~

Cần xem xét Sorted Set theo thời gian hoặc cấu trúc truy vấn chuyên biệt. Chỉ mục bằng nhau thông thường không đủ để tìm **khoảng** hay lấy **20 phần tử mới nhất** một cách tối ưu từ hàng triệu bản ghi.

### 14.4. Trường hợp D — Tìm kiếm văn bản, địa lý kết hợp với nhiều điều kiện

Nếu truy vấn gồm nhiều kiểu toán tử khó phối hợp như full-text, khoảng số, địa lý và nhiều bộ lọc, nên đánh giá Redis Query Engine với client/thư viện tương ứng, hoặc một hệ thống tìm kiếm phù hợp hơn.

Đây là một quyết định về khả năng truy vấn và mô hình dữ liệu, không phải chỉ cần đổi từ tên phương thức `findBy...` sang một tên khác.

## 15. Bài thực hành: lập bảng khả năng trước khi viết API

Với năm đơn hàng trong mục 2, hãy xác định kết quả và công cụ truy vấn:

| Yêu cầu | Biểu thức | Cách tiếp cận |
|---|---|---|
| Đơn PAID qua WEB | `status = PAID AND channel = WEB` | `findByStatusAndChannel` |
| Đơn PAID hoặc qua MOBILE | `status = PAID OR channel = MOBILE` | `findByStatusOrChannel` |
| Đơn active | `active = true` | `findByActiveIsTrue` |
| Đơn có tiền trên 500.000 | `totalAmount > 500000` | Không suy ra được từ chỉ mục bằng nhau; cân nhắc ZSET hoặc giải pháp tìm kiếm khác |
| Đơn PAID mới nhất | `status = PAID ORDER BY createdAt DESC` | Có thể dùng phương thức sort, nhưng cần kiểm tra chi phí; với tập lớn cân nhắc chỉ mục thời gian |

**Đáp án về ID, dựa trên bảng dữ liệu minh họa:**

1. `PAID AND WEB` → `o-101` và `o-105`.
2. `PAID OR MOBILE` → `o-101`, `o-102` và `o-105`.
3. `active = true` → `o-101`, `o-102` và `o-103`.
4. `totalAmount > 500000` → `o-101` và `o-104`. Đây là **kết quả logic của dữ liệu ví dụ**, không có nghĩa Redis Repository tự hỗ trợ `GreaterThan`.
5. `PAID` được lọc theo chỉ mục; để chọn đơn mới nhất cần có thuộc tính `createdAt` và cơ chế sắp xếp phù hợp. Bảng ví dụ chưa cung cấp thời điểm, nên không thể kết luận ID nào mới nhất.

### Bài tập mở rộng

Giả sử ứng dụng cần:

~~~text
(status = PAID OR status = PENDING)
AND channel = WEB
AND createdAt >= 2026-01-01
ORDER BY createdAt DESC
LIMIT 20
~~~

Hãy trả lời trước khi viết mã:

1. Những trường nào đang có chỉ mục bằng nhau?
2. Phần nào của truy vấn có thể biểu diễn bằng giao/hợp Redis Set?
3. Điều kiện nào cần chỉ mục khoảng hoặc cơ chế tìm kiếm khác?
4. Nếu kết quả có 500.000 ID, việc tải rồi sort trong Java có phù hợp không?
5. Ai chịu trách nhiệm cập nhật chỉ mục khi đơn hàng đổi trạng thái hoặc thời gian?
6. Kết quả cần nhất quán tại một thời điểm hay chấp nhận thay đổi giữa các request?
7. Bản triển khai có cần hỗ trợ Redis Cluster hoặc dữ liệu phân tán giữa các node không?

Trả lời được các câu hỏi này sẽ giúp lựa chọn API và thiết kế dữ liệu đúng ngay từ đầu.

## 16. Ghi nhớ

- Trong Spring Data Redis Repository, `@Indexed` thường tạo các Redis Set chứa ID thực thể cho **truy vấn bằng nhau**.
- `And` và `Or` trong truy vấn suy ra từ tên phương thức có thể tương ứng với **giao `SINTER`** và **hợp `SUNION`** của các tập chỉ mục.
- **Bảng từ khóa của Spring Data Commons là bảng tổng quát**; không được mặc định Redis Repository hỗ trợ mọi toán tử như `GreaterThan`, `Between`, `Like` hay `In`.
- `Top`, `First`, sắp xếp và phân trang cần được xem xét cùng chi phí đọc thực thể; sắp xếp có thể được thực hiện ở phía ứng dụng.
- Chỉ mục địa lý `@GeoIndexed` hỗ trợ truy vấn `Near`/`Within` riêng; không tự kết hợp các truy vấn này với mọi điều kiện khác.
- Khi điều kiện phức tạp hơn khả năng Repository, có thể dùng phép toán Set, ZSET, chỉ mục tùy chỉnh hoặc công cụ tìm kiếm phù hợp; mỗi lựa chọn đều có chi phí duy trì tính nhất quán.
- Việc trả lời câu hỏi **“Redis hỗ trợ được điều kiện gì, bằng cấu trúc nào, với chi phí nào?”** quan trọng hơn việc cố viết một tên phương thức dài.

### Tài liệu tham khảo

- [Spring Data Redis 3.5 — Redis-specific Query Methods](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/queries.html).
- [Spring Data Redis 3.5 — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/indexes.html).
- [Spring Data Redis — Repository Query Keywords](https://docs.spring.io/spring-data/redis/reference/repositories/query-keywords-reference.html).
- [Spring Data Redis — Defining Query Methods](https://docs.spring.io/spring-data/redis/reference/repositories/query-methods-details.html).
- [Redis — SINTER](https://redis.io/docs/latest/commands/sinter/) và [SUNION](https://redis.io/docs/latest/commands/sunion/).
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/).

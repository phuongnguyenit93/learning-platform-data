# Định danh thực thể bằng @Id trong Spring Data Redis

## 1. Vai trò của định danh khi ánh xạ thực thể vào Redis

Redis là hệ lưu trữ key–value. Để lưu một đối tượng Java thành dữ liệu có thể tìm lại, ứng dụng cần trả lời câu hỏi: **Đối tượng này nằm dưới Redis key nào?** Trong Spring Data Redis Repository, `@Id` đánh dấu thuộc tính định danh của thực thể (entity), còn `@RedisHash` xác định không gian khóa (keyspace) để lưu thực thể đó.

Giả sử ứng dụng quản lý khách hàng có mã `c-1001`:

~~~java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String displayName;
}
~~~

Khi lưu một `Customer` có `id = "c-1001"`, Redis Repository thường biểu diễn thực thể bằng một Redis Hash dưới khóa:

~~~text
customers:c-1001
~~~~~~~~~ ~~~~~~
keyspace   ID
~~~

Có hai khái niệm phải phân biệt:

- **`@Id`**: cho Spring Data biết trường nào là danh tính của một bản ghi; Repository dùng nó để xác định đối tượng cần tìm, lưu, cập nhật hoặc xóa.
- **`@RedisHash("customers")`**: chọn tên keyspace, tức phần tiền tố của khóa trong Redis.

Phần sau dấu `:` không phải tên class Java, cũng không phải khóa riêng mà bạn truyền trực tiếp cho Redis. Đó là giá trị của thuộc tính `@Id` sau khi được Spring Data chuyển đổi thành dạng dùng trong khóa.

Ví dụ hai entity có thể có cùng ID nhưng thuộc hai keyspace khác nhau:

~~~text
customers:c-1001
orders:c-1001
~~~

Chúng là hai Redis key khác nhau. Ngược lại, hai object của cùng loại, cùng keyspace và cùng ID sẽ hướng tới **cùng một định danh lưu trữ**, nên thao tác lưu sau có thể ghi đè nội dung của đối tượng trước.

> **Ý chính:** `@Id` định danh một thực thể trong keyspace của Spring Data Redis. Nó không tự tạo ràng buộc unique cho mọi thuộc tính nghiệp vụ, không cung cấp khóa ngoại và không tự biến Redis thành cơ sở dữ liệu quan hệ.

## 2. Chọn đúng annotation

Import dành cho Redis Repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
~~~

Không nhầm `org.springframework.data.annotation.Id` với `jakarta.persistence.Id` thường dùng trong JPA.

| Annotation | Vai trò |
| --- | --- |
| `@Id` | Khai báo thuộc tính dùng làm định danh cho Spring Data |
| `@RedisHash` | Khai báo entity được ánh xạ thành Redis Hash; có thể đặt keyspace và TTL mặc định |
| `@Indexed` | Yêu cầu tạo secondary index hỗ trợ tra cứu theo thuộc tính |
| `@TimeToLive` | Biểu diễn thời gian sống còn lại của entity theo cơ chế Repository |

Một thuộc tính như `email` có `@Indexed` vẫn **không thay thế** `@Id`. ID là địa chỉ chính của entity; secondary index chỉ hỗ trợ truy vấn theo các giá trị khác.

Trong mô hình đơn giản, đặt `@Id` trên một field là cách dễ đọc và dễ bảo trì nhất. Nếu dùng property access qua getter hoặc cấu hình mapping đặc biệt, hãy thống nhất cách ánh xạ trong toàn bộ entity.

## 3. Ví dụ hoàn chỉnh với Spring Boot và Redis Repository

Ứng dụng minh họa cần dependency `spring-boot-starter-data-redis`. Spring Boot thường tự cấu hình kết nối Redis và Redis Repositories khi có starter tương ứng. Nếu cấu hình thủ công, có thể dùng `@EnableRedisRepositories` và chỉ rõ phạm vi package cần quét.

### 3.1. Cấu hình kết nối

Ví dụ `application.yml` cho Redis chạy trên máy phát triển:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Trong ứng dụng thực tế, địa chỉ, TLS, xác thực và topology phụ thuộc môi trường triển khai. Chúng không làm thay đổi ý nghĩa của `@Id`.

### 3.2. Entity `Customer`

~~~java
package example.redis.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String displayName;
    private String email;

    public Customer() {
        // Dành cho cơ chế tạo đối tượng khi đọc dữ liệu.
    }

    public Customer(String id, String displayName, String email) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Các điểm quan trọng:

1. `id` là thuộc tính định danh; trong ví dụ này nó có kiểu `String` để dễ trao đổi với Redis và API.
2. `displayName`, `email` là dữ liệu thông thường của thực thể.
3. Prefix `customers` là một phần hợp đồng lưu trữ. Đổi nó sẽ làm Repository tìm ở bộ Redis key khác.
4. Constructor không tham số và các setter giúp ví dụ dễ tương thích với cơ chế mapping. Spring Data còn hỗ trợ những kiểu khởi tạo khác, nhưng cách này phù hợp để học `@Id`.

### 3.3. Repository dùng đúng kiểu ID

~~~java
package example.redis.customer;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
~~~

Khai báo generic thứ hai, `String`, phải phù hợp với kiểu thuộc tính `@Id` trong `Customer`.

Nhờ `CrudRepository`, ta có các thao tác phổ biến:

~~~java
repository.save(customer);
repository.findById("c-1001");
repository.existsById("c-1001");
repository.deleteById("c-1001");
~~~

Không cần tự ghép chuỗi `"customers:" + id` khi gọi các phương thức này; Repository dùng metadata của entity để xác định keyspace và khóa vật lý.

### 3.4. Service tạo, tìm, cập nhật và xóa

~~~java
package example.redis.customer;

import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String displayName, String email) {
        String id = UUID.randomUUID().toString();
        Customer customer = new Customer(id, displayName, email);
        return repository.save(customer);
    }

    public Optional<Customer> find(String id) {
        return repository.findById(id);
    }

    public Optional<Customer> rename(String id, String newDisplayName) {
        return repository.findById(id).map(customer -> {
            customer.setDisplayName(newDisplayName);
            return repository.save(customer);
        });
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

Các phương thức này minh họa một nguyên tắc nhất quán: khi tạo mới, gán một ID; khi cập nhật, **giữ nguyên ID** và thay đổi các trường dữ liệu.

Ở mức API, ID trả về từ `create` cần được client giữ lại để gọi `find` hoặc `rename`. Đây là định danh ổn định để truy xuất thực thể, không phụ thuộc vào việc tên hoặc email thay đổi.

## 4. Redis key được tạo từ @Id như thế nào?

Xét entity:

~~~java
Customer customer = new Customer(
    "c-1001",
    "Nguyen An",
    "an@example.test"
);

customerRepository.save(customer);
~~~

Ánh xạ ở mức khái niệm:

~~~text
Java object
+------------------------+
| Customer               |
| id          = c-1001   | --+
| displayName = Nguyen An|   |
| email       = ...      |   |
+------------------------+   |
                             v
           @RedisHash("customers") + @Id
                             |
                             v
                     Redis Hash
                 key: customers:c-1001
                 fields: displayName, email,
                         metadata ánh xạ (nếu có)
~~~

Trong cách lưu mặc định của Redis Repository, Redis key chứa ID; converter ánh xạ những thuộc tính còn lại thành các trường của Redis Hash. Cấu trúc chi tiết có thể có trường metadata kiểu dữ liệu, chẳng hạn `_class`. Không nên coi layout vật lý này là hợp đồng cố định để thao tác bằng lệnh Redis thô khi ứng dụng vẫn sử dụng Repository.

Spring Data Redis Repository cũng có thể duy trì các cấu trúc phụ để hỗ trợ liệt kê entity và secondary indexes. Vì vậy, lưu/xóa trực tiếp một Redis Hash bằng `HSET`/`DEL` **không tương đương hoàn toàn** với `repository.save`/`repository.deleteById`.

### Quan sát qua Redis CLI

Sau khi chạy `repository.save` với ID `c-1001`, có thể quan sát:

~~~bash
redis-cli TYPE customers:c-1001
redis-cli HGETALL customers:c-1001
redis-cli EXISTS customers:c-1001
redis-cli SCAN 0 MATCH 'customers:*' COUNT 100
~~~

Kết quả `TYPE` thường là `hash`. `HGETALL` hiển thị dữ liệu của Hash; tên trường và metadata thực tế phụ thuộc cách mapping. `SCAN` chỉ dùng để xem khóa theo prefix; nó không phải một phần của contract Repository và không thay thế truy vấn theo ID.

Ví dụ một phần dữ liệu có thể được hiển thị như sau:

~~~text
1) "_class"
2) "example.redis.customer.Customer"
3) "displayName"
4) "Nguyen An"
5) "email"
6) "an@example.test"
~~~

Đây là **minh họa**, không phải mẫu output bắt buộc. Điểm cần ghi nhớ là ID xuất hiện trong **Redis key**, còn entity được ánh xạ thành Hash ở bên trong.

## 5. ID là danh tính, không phải thuộc tính được phép tùy tiện đổi

Giả sử Redis đã có:

~~~text
customers:c-1001  ->  {displayName: "Nguyen An"}
~~~

Sau đó ứng dụng sửa cả ID của object và gọi `save`:

~~~java
Customer customer = repository.findById("c-1001").orElseThrow();

customer.setId("c-2002");
repository.save(customer);
~~~

Lúc này Repository xác định đích lưu theo **ID mới** `c-2002`. Nó không có nghĩa vụ xem thao tác đó là lệnh “đổi tên Redis key và tự dọn key cũ”. Tùy dữ liệu trước đó, khóa `customers:c-1001` vẫn có thể tồn tại, dẫn đến hai bản ghi mà ứng dụng từng coi là một khách hàng.

Thiết kế an toàn hơn là:

- Xem ID là **bất biến về mặt nghiệp vụ** sau khi tạo entity.
- Nếu phải thay đổi định danh, viết một quy trình migration có chủ đích: xác nhận ID mới chưa sử dụng, tạo dữ liệu mới, cập nhật các tham chiếu liên quan, loại bỏ bản ghi cũ và giải quyết lỗi giữa các bước.
- Nếu chỉ muốn thay tên/email, chỉ cập nhật đúng những trường đó và giữ ID ban đầu.

Không nên dùng email hoặc số điện thoại làm ID chỉ vì chúng có vẻ duy nhất. Chúng có thể thay đổi, chứa thông tin cá nhân và cần quy tắc chuẩn hóa riêng. Định danh tổng hợp ổn định như UUID thường đơn giản hơn.

## 6. Tạo ID: tự gán, UUID và định danh nghiệp vụ

Có ba hướng lựa chọn thường gặp.

| Cách chọn ID | Ví dụ | Khi phù hợp | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| UUID do ứng dụng tạo | `e3f1...` | Nhiều instance cùng tạo entity | Khó đọc bằng mắt, dài |
| ID nghiệp vụ ổn định | `customer-2026-001` | Đã có hệ thống cấp mã chuẩn | Cần cơ chế bảo đảm không trùng |
| ID từ hệ thống khác | `crm-84291` | Redis là bản sao/cache của dữ liệu gốc | Phải bảo toàn namespace và nguồn cấp |

### Gán UUID tường minh

~~~java
String id = UUID.randomUUID().toString();

Customer customer = new Customer(
    id,
    "Tran Binh",
    "binh@example.test"
);

Customer saved = repository.save(customer);
System.out.println(saved.getId());
~~~

Việc gán trước khi gọi `save` làm rõ nguồn sinh ID và giúp service có định danh để gắn log, trả về API hoặc nối dữ liệu ở hệ thống khác.

Một số cơ chế Spring Data có hỗ trợ sinh định danh khi thuộc tính ID chưa được gán, nhưng chi tiết phụ thuộc adapter, kiểu ID và phiên bản thư viện. **Đừng mặc định mọi kiểu ID đều được Redis Repository tự sinh theo cách ứng dụng mong muốn.** Nếu tính duy nhất và dạng ID là một yêu cầu nghiệp vụ, hãy định nghĩa quy tắc cấp ID rõ ràng trong ứng dụng.

### Thế nào là “duy nhất”?

Cần phân biệt:

- **Duy nhất trong keyspace**: hai khách hàng khác nhau không được nhận cùng ID nếu cùng lưu trong `customers`.
- **Duy nhất toàn hệ thống**: không nhất thiết cần; ID `42` có thể xuất hiện hợp lệ ở `customers:42` và `orders:42`.
- **Duy nhất của thuộc tính khác**: `@Id` không bảo đảm email hay số điện thoại không bị lặp.

Nếu phải dùng một định danh ngắn và tăng dần, có thể thiết kế bộ cấp mã riêng, chẳng hạn dựa trên `INCR` hoặc cơ sở dữ liệu nghiệp vụ. Cần tính đến nhiều instance, reset dữ liệu, môi trường chạy và cách tránh xung đột. `@Id` chỉ tiêu thụ định danh đã được cấp; nó không giải quyết toàn bộ bài toán cấp mã.

## 7. @Id và @Indexed khác nhau thế nào?

ID là tuyến truy cập chính:

~~~java
repository.findById("c-1001");
~~~

Nhưng nếu muốn tìm khách hàng theo email:

~~~java
repository.findByEmail("an@example.test");
~~~

thì Redis không có khái niệm “quét mọi field của mọi Hash như SQL” tự động. Spring Data Redis Repository có thể tạo **secondary index** cho property được đánh dấu `@Indexed`.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String displayName;

    @Indexed
    private String email;

    // Constructors, getters và setters tương tự ví dụ trước.
}
~~~

Repository thêm phương thức tra cứu:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
~~~

So sánh:

| Thuộc tính | `@Id` | `@Indexed` |
| --- | --- | --- |
| Mục tiêu | Xác định danh tính của entity | Hỗ trợ truy vấn theo giá trị |
| Tác động đến Redis key chính | Có | Không |
| Ví dụ API | `findById(id)` | `findByEmail(email)` |
| Có thể có nhiều trên entity? | Một định danh logic | Có thể có nhiều field đánh index |
| Đảm bảo uniqueness? | Cần cơ chế cấp ID không trùng trong keyspace | Không mặc nhiên tạo ràng buộc unique |

Một khách hàng có ID `c-1001` vẫn là cùng entity khi email đổi. Index cần được duy trì qua các thao tác Repository. Nếu tự sửa Hash bằng Redis CLI trong khi Repository còn quản lý index, hệ thống có thể xuất hiện index không khớp dữ liệu.

## 8. Khi save một entity có ID đã tồn tại

Giả sử hai đối tượng có ID giống nhau:

~~~java
Customer first = new Customer(
    "c-1001",
    "Nguyen An",
    "an@example.test"
);

Customer second = new Customer(
    "c-1001",
    "Ten Moi",
    "new@example.test"
);

repository.save(first);
repository.save(second);
~~~

Cả hai lần lưu nhắm tới `customers:c-1001`. Thao tác thứ hai cập nhật dữ liệu tương ứng với cùng định danh, chứ không tạo “hai hàng” cùng khóa như một bảng có khóa chính bị trùng.

**Không được xem `save` là cơ chế bảo đảm tạo mới duy nhất.** Nếu nghiệp vụ yêu cầu “chỉ tạo khi chưa tồn tại”, việc kiểm tra `existsById` rồi `save` chưa đủ an toàn trong môi trường nhiều luồng:

~~~java
if (!repository.existsById(id)) {
    repository.save(customer); // Một request khác vẫn có thể chen vào.
}
~~~

Giữa hai thao tác, một instance khác có thể đã tạo entity cùng ID. Khi yêu cầu tính nguyên tử, hãy chọn một cơ chế có điều kiện phù hợp (ví dụ `SET ... NX` hoặc Lua script trên Redis đối với dữ liệu và cấu trúc khóa đã thiết kế, hay giao dịch/ràng buộc unique trên nguồn dữ liệu bền vững) và cân nhắc cách duy trì index của Repository. Đừng thay thế máy móc `repository.save` bằng `SET NX` trên cùng khóa vì Repository còn có ánh xạ Hash và metadata.

## 9. Tìm kiếm, tồn tại và xóa thông qua ID

Với kiểu ID `String`:

~~~java
String id = "c-1001";

Optional<Customer> customer = repository.findById(id);
boolean exists = repository.existsById(id);

repository.deleteById(id);
~~~

Các thao tác này đều bắt đầu từ một ID logic; Repository sẽ xác định Redis key theo keyspace và converter.

### ID không tồn tại

Nếu không có entity dưới khóa tương ứng, `findById` trả về `Optional.empty()`. Trong REST API, trường hợp này thường được ánh xạ thành HTTP 404; trong nghiệp vụ batch, có thể bỏ qua hoặc ghi nhận tùy yêu cầu.

Không nên dùng kết quả `existsById` làm cam kết rằng `findById` ngay sau đó chắc chắn thành công, vì một tiến trình khác hoặc TTL có thể xóa khóa giữa hai lệnh.

### Xóa theo ID

`deleteById` biểu đạt ý định xóa thực thể do Repository quản lý. Nó hữu ích hơn việc đoán Redis key rồi gọi `DEL`, đặc biệt khi có secondary indexes hoặc các cấu trúc phụ.

Nếu dùng `redisTemplate.delete("customers:" + id)` trực tiếp, Redis có thể xóa Hash chính nhưng những cấu trúc mà Repository duy trì có nguy cơ không được cập nhật tương ứng. Khi đã chọn Redis Repository, nên nhất quán dùng Repository cho vòng đời entity.

## 10. @Id có liên quan thế nào đến TTL?

`@Id` giải thích **entity nào** đang được truy cập; TTL giải thích **entity còn hiệu lực bao lâu**. Hai cơ chế độc lập nhưng cùng tham gia vòng đời lưu trữ.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "login-sessions", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    // Constructors, getters, setters...
}
~~~

Ý nghĩa:

- `login-sessions` là keyspace.
- `id` là định danh của session.
- `timeToLive = 1800` khai báo thời hạn mặc định 1.800 giây theo cơ chế Redis Repository.

Một session có ID `s-42` sẽ tương ứng với một Redis key dạng `login-sessions:s-42`. Khi khóa hết hạn, `findById("s-42")` không còn trả về thực thể.

**Hết hạn không tự tạo ID mới.** Nếu ứng dụng cần làm mới session, phải quyết định giữ hay đổi ID theo quy tắc bảo mật và nghiệp vụ. Việc tái sử dụng một ID đã hết hạn có thể gây nhầm giữa phiên cũ và phiên mới trong những hệ thống có listener hoặc tác vụ bất đồng bộ; có thể dùng session ID mới hoặc generation riêng.

Khi dùng tính năng Repository như TTL và secondary indexes, nên để Repository quản lý việc lưu/xóa nhằm giữ sự nhất quán tốt nhất có thể trong giới hạn của Redis notification.

## 11. ID của entity gốc và ID của object lồng nhau

Trong một aggregate được lưu dưới một Redis key, `@Id` của **thực thể gốc** xác định địa chỉ lưu trữ. Các object con không nhất thiết là các entity độc lập chỉ vì trong Java chúng có thuộc tính tên `id`.

Ví dụ:

~~~java
@RedisHash("orders")
public class Order {

    @Id
    private String id;

    private ShippingAddress shippingAddress;

    // Constructors, getters, setters...
}

public class ShippingAddress {
    private String city;
    private String street;

    // Constructors, getters, setters...
}
~~~

Về mặt khái niệm, `orders:o-10` lưu các trường của `Order` và dữ liệu địa chỉ được ánh xạ bên trong. `ShippingAddress` trong ví dụ không có Repository hay Redis key độc lập như `shipping-addresses:...`.

Nếu `ShippingAddress` cần vòng đời, tra cứu và cập nhật riêng, hãy thiết kế nó như một aggregate độc lập với `@RedisHash` và `@Id` riêng, rồi quyết định cách lưu tham chiếu giữa hai aggregate. Redis Repository không tự cung cấp toàn bộ hành vi khóa ngoại, cascade và join của JPA.

## 12. Đổi keyspace hoặc đổi kiểu ID có tác động gì?

Định danh lưu trữ phụ thuộc đồng thời vào:

~~~text
Redis key = keyspace + dấu phân tách + ID đã chuyển đổi
~~~

Vì vậy có hai thay đổi cần xem như **thay đổi lược đồ lưu trữ**.

### Đổi keyspace

Trước:

~~~java
@RedisHash("customers")
~~~

Sau:

~~~java
@RedisHash("customer-profiles")
~~~

Cùng ID `c-1001` nhưng key vật lý khác nhau:

~~~text
customers:c-1001
customer-profiles:c-1001
~~~

Nếu không migration dữ liệu, ứng dụng mới có thể không tìm thấy entity cũ. Redis vẫn giữ key cũ cho đến khi được xóa hoặc hết TTL.

### Đổi kiểu ID

Trước:

~~~java
@Id
private String id;
~~~

Sau:

~~~java
@Id
private Long id;
~~~

Việc đổi kiểu Java có thể thay đổi cách chuyển đổi ID, cách parse dữ liệu, kiểu generic của Repository và định dạng API. Không nên tự động coi một Redis key cũ là tương thích với model mới. Phải kiểm tra format ID, đường đọc dữ liệu cũ và phương án migration.

Ngay cả khi chỉ đổi quy tắc tạo ID từ chuỗi `"0012"` sang số `12`, hai dạng này có thể đại diện cho các key khác nhau. Không nên chuyển ID thành số nếu số 0 ở đầu mang ý nghĩa.

## 13. Lỗi thường gặp và cách nhận biết

| Biểu hiện | Nguyên nhân khả dĩ | Cách tiếp cận |
| --- | --- | --- |
| `findById` luôn rỗng dù thấy dữ liệu trong Redis | Keyspace, ID, DB hoặc cách lưu dữ liệu khác với Repository | So sánh `@RedisHash`, kiểu ID và Redis key thực tế |
| Thay email rồi bị tạo bản ghi mới | Ứng dụng dùng email làm ID và đã thay đổi ID | Dùng ID bất biến và email là property |
| Hai request tạo khách hàng đè lên nhau | Bộ cấp ID trùng, `save` cùng ID | Sinh ID không trùng; dùng thao tác tạo có điều kiện khi cần |
| Có Hash nhưng query theo index không ra | Dữ liệu được ghi trực tiếp bằng Redis command, không cập nhật index | Dùng Repository hoặc xây lại index nhất quán |
| Xóa qua `DEL` nhưng kết quả Repository bất thường | Cấu trúc phụ/secondary index không được cập nhật | Dùng `deleteById` để quản lý vòng đời |
| Không nhận diện được ID sau đổi kiểu | ID conversion và repository generic không đồng bộ | Giữ kiểu nhất quán, migration dữ liệu cũ |
| Không tìm thấy entity sau đổi tên `@RedisHash` | Tiền tố Redis key đã thay đổi | Lập kế hoạch migration keyspace |
| `findById` từng có kết quả rồi trở thành rỗng | TTL hết hạn hoặc tiến trình khác đã xóa | Phân biệt ID với thời hạn tồn tại |

### Nhầm annotation của JPA

Ví dụ này nên tránh trong một Redis entity nếu bạn định dùng cơ chế Spring Data Redis Repository:

~~~java
import jakarta.persistence.Id; // Annotation dành cho mô hình JPA.
~~~

Hãy khai báo rõ:

~~~java
import org.springframework.data.annotation.Id;
~~~

Nếu cùng một class được dùng cho nhiều cơ chế persistence, các annotation và cấu hình mapping có thể chồng chéo. Thường nên có model phù hợp với từng storage thay vì giả định một annotation sẽ có cùng ngữ nghĩa ở mọi nơi.

### Nhầm giữa ID và Redis key đầy đủ

Không truyền key vật lý đã có prefix như một ID thông thường:

~~~java
repository.findById("customers:c-1001"); // Sai nếu ID thực tế là "c-1001".
~~~

Đúng là:

~~~java
repository.findById("c-1001");
~~~

Repository tự ghép keyspace. Nếu cố gán giá trị `"customers:c-1001"` cho `@Id`, ứng dụng có thể tạo ra khóa kiểu `customers:customers:c-1001`, khiến việc tìm dữ liệu trở nên rối rắm.

## 14. Khi nào cần dùng Repository, khi nào dùng RedisTemplate?

`@Id` có ý nghĩa trong **mô hình ánh xạ entity của Spring Data**. Nếu code chỉ dùng `StringRedisTemplate` hoặc `RedisTemplate` để thao tác khóa thô, annotation `@Id` trên class Java không tự động tham gia.

So sánh:

| Công việc | Redis Repository | RedisTemplate |
| --- | --- | --- |
| Lưu một entity Java | `repository.save(customer)` | Tự chọn key, serializer và cấu trúc |
| Tra cứu bằng ID | `repository.findById(id)` | Tự ghép Redis key và đọc dữ liệu |
| Định danh bằng `@Id` | Có | Không tự kích hoạt chỉ vì object có annotation |
| Keyspace bằng `@RedisHash` | Có | Tự quản lý |
| Secondary indexes của Repository | Có, khi cấu hình phù hợp | Tự thiết kế và duy trì |
| Điều khiển lệnh Redis đặc thù | Trừu tượng hóa qua Repository | Linh hoạt hơn |

Nếu ứng dụng chủ yếu thao tác với domain entity (khách hàng, phiên đăng nhập, giỏ hàng), Redis Repository giúp chuẩn hóa định danh và giảm việc tự ghép key.

Nếu ứng dụng chỉ cần một counter, lock, list hoặc cache key–value đơn giản, `RedisTemplate` có thể phù hợp hơn. Nhưng khi dùng nó, định danh và cách đặt tên khóa là trách nhiệm của code, không phải `@Id`.

## 15. Bài thực hành nhỏ

Mục tiêu: quan sát rằng **giữ ID thì cập nhật cùng entity; đổi ID thì trỏ đến Redis key khác**.

Chuẩn bị Redis và ví dụ `Customer`/`CustomerRepository` ở phần 3. Từ một đoạn code chạy trong ứng dụng:

~~~java
Customer first = repository.save(
    new Customer("demo-1", "Tên ban đầu", "first@example.test")
);

Customer loaded = repository.findById("demo-1").orElseThrow();
loaded.setDisplayName("Tên sau cập nhật");
repository.save(loaded);

System.out.println(
    repository.findById("demo-1")
              .orElseThrow()
              .getDisplayName()
);
// Tên sau cập nhật

Customer another = repository.save(
    new Customer("demo-2", "Khách hàng khác", "second@example.test")
);

System.out.println(repository.existsById("demo-1")); // true
System.out.println(repository.existsById("demo-2")); // true
~~~

Xem các key:

~~~bash
redis-cli TYPE customers:demo-1
redis-cli TYPE customers:demo-2
redis-cli HGETALL customers:demo-1
redis-cli HGETALL customers:demo-2
~~~

Trong ví dụ này, `demo-1` và `demo-2` độc lập vì ID khác nhau; thay `displayName` không đổi ID.

Sau khi quan sát, dọn dữ liệu bằng Repository:

~~~java
repository.deleteById("demo-1");
repository.deleteById("demo-2");
~~~

Việc dọn bằng Repository giúp đi cùng các bước quản lý dữ liệu của chính cơ chế repository.

## 16. Các câu hỏi thường gặp

**Nếu không đặt `@Id` thì sao?**

Spring Data có thể nhận diện thuộc tính định danh theo quy ước ở một số trường hợp, nhưng khai báo tường minh `@Id` giúp loại bỏ mơ hồ và làm rõ ý định của mô hình. Với tài liệu và code mẫu, nên dùng annotation rõ ràng.

**`@Id` có bắt buộc là kiểu `String` không?**

Không nhất thiết. Tuy nhiên, `String` thuận tiện cho ví dụ và API. Khi chọn kiểu khác, cần xét hỗ trợ chuyển đổi ID của Spring Data, tính ổn định của chuỗi key và khả năng tương thích dữ liệu đang lưu.

**Có thể dùng `Long` tăng dần như khóa chính SQL không?**

Có thể thiết kế ứng dụng dùng ID số, nhưng `@Id` tự nó không tương đương `@GeneratedValue(strategy = IDENTITY)` của JPA. Cần có chiến lược cấp ID phù hợp, đặc biệt với nhiều instance.

**Có thể có hai field `@Id` trên cùng một entity không?**

Không nên. Một Redis aggregate cần một định danh logic rõ ràng. Nếu nghiệp vụ có khóa ghép, hãy thiết kế một kiểu/chuỗi ID ổn định và quy tắc mã hóa rõ ràng, thay vì kỳ vọng Redis Repository tự hỗ trợ composite primary key như SQL.

**Có cần lưu ID thành một field trong Redis Hash nữa không?**

Trong mô hình Repository, ID đã tham gia vào Redis key chính. Hãy để converter quyết định cách biểu diễn entity trong Hash. Chỉ lưu thêm trường ID nghiệp vụ nếu có lý do riêng; tránh tạo hai nguồn thông tin có thể mâu thuẫn.

**Đổi `@Id` có tự động đổi Redis key cũ không?**

Không nên coi việc đổi giá trị ID là thao tác rename. Tạo ID mới đồng nghĩa chọn địa chỉ lưu mới; nếu muốn migration, phải xử lý dữ liệu cũ và các tham chiếu một cách chủ động.

**Dùng `@Id` có bảo đảm không bị ghi đè bởi request đồng thời không?**

Không. ID giúp hai request tìm cùng thực thể; kiểm soát ghi đồng thời, tạo mới có điều kiện và nhất quán nghiệp vụ cần thêm cơ chế thích hợp.

**Xóa khóa Redis bằng TTL thì ID còn giá trị không?**

Giá trị ID trong client vẫn là một chuỗi, nhưng nó không còn trỏ đến entity còn tồn tại. `findById` sẽ không tìm thấy dữ liệu sau khi khóa đã hết hạn.

## 17. Ghi nhớ khi thiết kế entity

- Đặt `@Id` từ `org.springframework.data.annotation.Id` trên thuộc tính mang danh tính ổn định.
- Dùng `@RedisHash("...")` để chọn keyspace nhất quán; hiểu Redis key thường có dạng `keyspace:id`.
- Trong `CrudRepository<Entity, IdType>`, kiểu `IdType` phải khớp kiểu `@Id`.
- Cấp ID theo quy tắc rõ ràng; UUID tạo trong ứng dụng là một phương án đơn giản.
- Cập nhật dữ liệu thì giữ ID; đổi ID cần được xem là chuyển sang định danh lưu trữ mới.
- Phân biệt `@Id` với `@Indexed`, TTL, unique constraint và cơ chế kiểm soát đồng thời.
- Khi dùng Repository, ưu tiên Repository để lưu/xóa entity nhằm duy trì các cấu trúc ánh xạ liên quan.
- Cân nhắc migration trước khi đổi keyspace, kiểu ID hoặc quy ước mã hóa ID.

## Tài liệu tham khảo

- [Spring Data Redis – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis – Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Commons – Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html)
- [Spring Data Commons – Core Concepts (Repositories)](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)

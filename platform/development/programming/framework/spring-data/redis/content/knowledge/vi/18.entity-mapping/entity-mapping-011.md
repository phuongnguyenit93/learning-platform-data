# Phân biệt ánh xạ Hash của Repository với JSON qua RedisTemplate

## 1. Cùng là lưu đối tượng Java vào Redis nhưng dữ liệu có thể rất khác nhau

Giả sử ứng dụng Spring Boot có đối tượng khách hàng:

~~~java
Customer customer = new Customer(
        "c-101",
        "linh@example.com",
        "Nguyễn Linh",
        new Address("Hà Nội")
);
~~~

Ta có thể lưu đối tượng này vào Redis theo hai cách phổ biến:

1. Dùng **Spring Data Redis Repository** với `@RedisHash` và `CrudRepository`. Spring Data Redis ánh xạ các thuộc tính của thực thể thành **các trường trong Redis Hash**.
2. Dùng **RedisTemplate** đã cấu hình bộ tuần tự hóa JSON (JSON serializer), rồi gọi `opsForValue().set(...)`. Redis lưu **một giá trị kiểu String** có nội dung là JSON biểu diễn toàn bộ đối tượng.

Cả hai đều có thể cho phép chương trình đọc lại một đối tượng `Customer`, nhưng cách lưu, lệnh Redis, truy vấn và việc cập nhật dữ liệu hoàn toàn khác nhau.

~~~text
                  Đối tượng Java Customer
                           |
             +-------------+--------------+
             |                            |
             v                            v
  Redis Repository                 RedisTemplate<String, Customer>
  @RedisHash + save(...)           + JSON value serializer
             |                            |
     Ánh xạ từng thuộc tính         Chuyển cả đối tượng thành JSON
             |                            |
             v                            v
       Redis HASH                    Redis STRING
  key: customers:c-101          key: customer:json:c-101
  field email -> ...            value: {"id":"c-101", ...}
  field fullName -> ...
  field address.city -> ...
             |                            |
       HGET / HGETALL                  GET / SET
~~~

**Điểm quan trọng:** tên lớp `RedisTemplate` không quyết định dữ liệu là Hash hay JSON. **Lệnh/thao tác được gọi** quyết định kiểu dữ liệu Redis; **serializer** quyết định cách chuyển đối tượng và giá trị giữa Java và byte.

## 2. Hai khái niệm khác nhau: ánh xạ đối tượng và tuần tự hóa

Redis là kho dữ liệu khóa–giá trị với nhiều kiểu dữ liệu như String, Hash, Set, List và Sorted Set.

- **Ánh xạ đối tượng (object mapping):** xác định mỗi thuộc tính Java tương ứng với trường nào trong Redis, đối tượng có khóa gì, thuộc tính nào là định danh, chỉ mục nào cần duy trì và cách dựng lại đối tượng khi đọc.
- **Tuần tự hóa (serialization):** chuyển một giá trị Java thành dãy byte để lưu và giải mã dãy byte thành giá trị Java khi đọc. Ví dụ, một serializer JSON chuyển `Customer` thành văn bản JSON dưới dạng byte.
- **Kiểu dữ liệu Redis:** xác định những lệnh có thể dùng với khóa. Hash dùng `HSET`, `HGET`, `HGETALL`; String dùng `SET`, `GET`. Dù nội dung String là JSON thì Redis vẫn xem nó là String.

Một Redis Hash có thể chứa nhiều cặp `field → value`:

~~~text
customers:c-101            (Redis HASH)
  email          -> "linh@example.com"
  fullName       -> "Nguyễn Linh"
  address.city   -> "Hà Nội"
  _class         -> "com.example.Customer"  (metadata nếu cấu hình mapping dùng)
~~~

Một Redis String có thể chứa JSON:

~~~json
{
  "id": "c-101",
  "email": "linh@example.com",
  "fullName": "Nguyễn Linh",
  "address": {
    "city": "Hà Nội"
  }
}
~~~

Trong ví dụ JSON, cả khối văn bản trên là **một giá trị duy nhất** tại khóa `customer:json:c-101`. Redis không tự coi `email` hay `address.city` là các trường Hash có thể truy cập bằng `HGET`.

> Cần phân biệt JSON nằm trong Redis String với **RedisJSON**, một kiểu dữ liệu và tập lệnh riêng khi hệ thống có mô-đun RedisJSON. Lưu JSON bằng `opsForValue().set(...)` không tự động tạo dữ liệu RedisJSON và không tự mở ra khả năng dùng `JSON.GET` hay `JSON.SET`.

## 3. Cách 1 — Repository ánh xạ thực thể thành Redis Hash

### 3.1. Khai báo thực thể với @RedisHash

Trong Spring Data Redis, `@RedisHash` đánh dấu lớp dùng cơ chế ánh xạ thực thể cho Redis Repository. Giá trị `"customers"` là **keyspace** — tiền tố logic của các khóa thuộc loại thực thể này.

~~~java
package com.example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String fullName;
    private Address address;

    public Customer() {
    }

    public Customer(
            String id,
            String email,
            String fullName,
            Address address) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

Lớp `Address` là một đối tượng giá trị được lồng trong `Customer`:

~~~java
package com.example.redis;

public class Address {

    private String city;

    public Address() {
    }

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Trong đoạn mã:

- `@Id` đánh dấu định danh dùng để xây dựng khóa Redis cho thực thể.
- `@RedisHash("customers")` chỉ định keyspace của thực thể.
- `@Indexed` yêu cầu cơ chế Repository quản lý chỉ mục phụ cho trường `email`, phục vụ một số truy vấn theo thuộc tính.
- `address` là đối tượng lồng nhau; bộ ánh xạ Hash mặc định của Spring Data Redis có thể trải phẳng các thuộc tính thành các đường dẫn trường như `address.city`.

Cách biểu diễn chính xác của trường, metadata `_class`, cấu trúc lồng nhau và tập khóa phụ có thể phụ thuộc phiên bản Spring Data Redis, kiểu thuộc tính và các bộ chuyển đổi tùy chỉnh. Đừng coi hình minh họa các field là một hợp đồng định dạng byte bất biến.

### 3.2. Repository lưu và truy xuất thực thể

~~~java
package com.example.redis;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
~~~

Khai báo bật Redis Repository khi dự án chưa cấu hình tự động phù hợp:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(basePackageClasses = CustomerRepository.class)
public class RedisRepositoryConfiguration {
}
~~~

Giả sử ứng dụng đã có `RedisConnectionFactory` từ cấu hình Spring Boot và các dependency Spring Data Redis thích hợp, mã sử dụng có thể là:

~~~java
Customer saved = repository.save(new Customer(
        "c-101",
        "linh@example.com",
        "Nguyễn Linh",
        new Address("Hà Nội")
));

Customer loaded = repository.findById("c-101")
        .orElseThrow();

List<Customer> foundByEmail =
        repository.findByEmail("linh@example.com");
~~~

`save(...)` giao cho Spring Data Redis trách nhiệm chuyển đối tượng sang các trường Hash. `findById(...)` tìm Hash tương ứng và dựng lại `Customer`. Với `@Indexed`, `findByEmail(...)` có thể sử dụng chỉ mục phụ do Repository duy trì; không có nghĩa Redis tự hỗ trợ truy vấn tùy ý như cơ sở dữ liệu quan hệ.

### 3.3. Dữ liệu vật lý trông như thế nào?

Với cấu hình ánh xạ thông thường, khóa chính có dạng minh họa:

~~~text
customers:c-101
~~~

Kiểm tra bằng Redis CLI:

~~~redis
TYPE customers:c-101
HGETALL customers:c-101
~~~

Lệnh `TYPE` sẽ trả về `hash` nếu khóa này được Repository lưu dưới dạng Redis Hash thông thường. `HGETALL` hiển thị các trường được ánh xạ, ví dụ:

~~~text
email         -> linh@example.com
fullName      -> Nguyễn Linh
address.city  -> Hà Nội
_class        -> com.example.redis.Customer
~~~

Ví dụ chỉ diễn tả cấu trúc; dữ liệu thật có thể có thêm trường `id`, thông tin kiểu hoặc tên trường khác tùy cách ánh xạ.

Ngoài khóa Hash chính, Repository có thể duy trì **Set chứa định danh của keyspace**, **Set phục vụ chỉ mục phụ** và metadata khác. Vì vậy, một lần `repository.save(...)` có thể tác động lên nhiều khóa Redis chứ không chỉ một Hash.

Điều này giúp `findAll()` và truy vấn theo thuộc tính đã được đánh chỉ mục, nhưng cũng làm tăng chi phí lưu trữ, cập nhật và dọn dữ liệu khi cần.

### 3.4. Vì sao Repository phù hợp với mô hình thực thể?

Repository cung cấp cách lập trình xoay quanh thực thể:

~~~java
repository.save(customer);
repository.findById("c-101");
repository.deleteById("c-101");
repository.findByEmail("linh@example.com");
~~~

Chương trình làm việc với kiểu Java và định danh, còn Spring Data Redis quản lý cơ chế lưu Hash, metadata và chỉ mục của Repository.

Tuy nhiên, đây **không phải ORM quan hệ thu nhỏ**: Redis Repository không tự cung cấp mọi kiểu lọc, sắp xếp, nối bảng, tổng hợp hoặc giao dịch như SQL. Chỉ mục và khả năng truy vấn phải được thiết kế theo những gì Spring Data Redis thực sự hỗ trợ.

## 4. Cách 2 — RedisTemplate lưu cả đối tượng thành JSON

### 4.1. Cấu hình serializer cụ thể

`RedisTemplate` là API thao tác Redis linh hoạt. Khi muốn lưu một đối tượng Java dưới dạng JSON trong **Redis String**, ta cấu hình serializer cho khóa và giá trị.

Ví dụ cho Spring Data Redis 3.x:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class CustomerJsonRedisConfiguration {

    @Bean("customerJsonRedisTemplate")
    public RedisTemplate<String, Customer> customerJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Customer> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(Customer.class)
        );

        template.afterPropertiesSet();
        return template;
    }
}
~~~

`StringRedisSerializer` giúp tên khóa hiển thị dưới dạng chuỗi dễ đọc. `Jackson2JsonRedisSerializer<Customer>` ghi các đối tượng `Customer` thành JSON và đọc JSON về kiểu `Customer`.

Tên lớp serializer và cách khởi tạo có thể thay đổi theo phiên bản Spring Data Redis/Jackson. Nếu dùng phiên bản khác 3.x, cần đối chiếu API của phiên bản ấy. Ý tưởng cốt lõi vẫn là **cấu hình bộ tuần tự hóa phù hợp với dữ liệu và kiểu Java cần đọc**.

Không nên mặc định `RedisTemplate` nào cũng lưu JSON: một `RedisTemplate` chưa cấu hình rõ có thể sử dụng cơ chế tuần tự hóa Java/JDK cho giá trị, tạo dữ liệu nhị phân khó đọc và khó trao đổi giữa các hệ thống.

### 4.2. Ghi và đọc bằng ValueOperations

~~~java
package com.example.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerJsonCache {

    private final RedisTemplate<String, Customer> redis;

    public CustomerJsonCache(
            @Qualifier("customerJsonRedisTemplate")
            RedisTemplate<String, Customer> redis) {
        this.redis = redis;
    }

    public void save(Customer customer) {
        String key = "customer:json:" + customer.getId();

        redis.opsForValue().set(
                key,
                customer,
                Duration.ofMinutes(30)
        );
    }

    public Customer findById(String id) {
        return redis.opsForValue().get("customer:json:" + id);
    }

    public void deleteById(String id) {
        redis.delete("customer:json:" + id);
    }
}
~~~

Dùng `opsForValue()` nghĩa là thao tác với **Redis String**, không phải Redis Hash. Với serializer JSON, luồng xử lý là:

~~~text
customer Java
    |
    | Jackson2JsonRedisSerializer
    v
byte JSON: {"id":"c-101","email":"linh@example.com",...}
    |
    | SET customer:json:c-101 <bytes> EX <ttl>
    v
Redis STRING
    |
    | GET customer:json:c-101
    v
byte JSON
    |
    | Jackson2JsonRedisSerializer
    v
customer Java
~~~

Dù lớp `Customer` ở ví dụ trước có `@RedisHash` và `@Indexed`, việc gọi `opsForValue().set(...)` **không kích hoạt** cơ chế Repository để tự tạo Redis Hash hay cập nhật chỉ mục `@Indexed`. Đó là hai đường truy cập độc lập.

### 4.3. Quan sát dữ liệu trong Redis

Sau khi gọi `CustomerJsonCache.save(...)`, có thể kiểm tra:

~~~redis
TYPE customer:json:c-101
GET customer:json:c-101
TTL customer:json:c-101
~~~

Kết quả điển hình:

~~~text
TYPE -> string

GET  -> {"id":"c-101","email":"linh@example.com",
         "fullName":"Nguyễn Linh","address":{"city":"Hà Nội"}}

TTL  -> một số giây còn lại
~~~

`GET` đọc **cả giá trị JSON**. Không thể dùng:

~~~redis
HGET customer:json:c-101 email
~~~

vì khóa đang có kiểu Redis String, không phải Hash; Redis sẽ trả lỗi kiểu dữ liệu (`WRONGTYPE`).

Ngược lại:

~~~redis
GET customers:c-101
~~~

cũng không đọc được Hash do Repository lưu. Phải dùng thao tác Hash phù hợp, hoặc để Repository dựng lại đối tượng Java.

## 5. RedisTemplate cũng có thể dùng Hash: đừng nhầm tên API với cách lưu

Có ít nhất ba tình huống cần phân biệt rõ:

| Cách truy cập | API Java điển hình | Kiểu dữ liệu Redis | Cơ chế chuyển đổi |
|---|---|---|---|
| **Redis Repository** | `repository.save(entity)` | Hash cho thực thể gốc | Bộ ánh xạ thực thể của Spring Data Redis; có quản lý định danh và chỉ mục |
| **RedisTemplate + JSON** | `template.opsForValue().set(key, entity)` | String | Bộ tuần tự hóa JSON đã cấu hình cho giá trị |
| **RedisTemplate + HashOperations** | `template.opsForHash().put(key, field, value)` | Hash | Chương trình tự quyết định field; serializer Hash key/value theo cấu hình |

Ví dụ thao tác Hash thủ công:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;

public void saveSomeFields(StringRedisTemplate redis) {
    String key = "customer:manual:c-101";

    redis.opsForHash().put(key, "email", "linh@example.com");
    redis.opsForHash().put(key, "fullName", "Nguyễn Linh");

    Object email = redis.opsForHash().get(key, "email");
    System.out.println(email);
}
~~~

`StringRedisTemplate` dùng chuỗi cho khóa, field và giá trị. Đoạn này tạo một **Redis Hash**, nhưng **không phải** lời gọi Repository: nó không tự động dựng `Customer`, không tự tạo chỉ mục `@Indexed` và không áp dụng toàn bộ quy tắc ánh xạ của `@RedisHash`.

Do đó, câu “RedisTemplate lưu JSON, Repository lưu Hash” chỉ đúng khi ta đang so sánh **một RedisTemplate đã cấu hình JSON và dùng `opsForValue()`** với **Repository có ánh xạ Redis Hash**. Bản thân RedisTemplate không bị giới hạn ở JSON.

## 6. So sánh theo những quyết định thực tế

| Tiêu chí | Repository + @RedisHash | RedisTemplate + JSON qua opsForValue |
|---|---|---|
| **Đơn vị dữ liệu vật lý** | Nhiều field trong một Hash của thực thể | Một String chứa JSON của toàn đối tượng |
| **Đọc theo ID** | `findById(id)` dựng đối tượng từ Hash | `GET` rồi giải mã JSON |
| **Ghi đối tượng** | `save(entity)` theo cơ chế ánh xạ, quản lý khóa phụ nếu có | `SET key json`, thường ghi đè giá trị của khóa |
| **Đọc một thuộc tính** | Có thể dùng `HGET` trên Hash vật lý nếu hiểu mapping; Repository thường trả thực thể | Không thể `HGET` thuộc tính bên trong JSON String; phải đọc và phân tích JSON hoặc đổi mô hình dữ liệu |
| **Cập nhật một field bằng lệnh Redis** | Hash hỗ trợ `HSET`; cần thận trọng khi trộn với Repository | `SET` thường thay thế toàn bộ String |
| **Chỉ mục theo thuộc tính** | Có cơ chế `@Indexed` và chỉ mục phụ được hỗ trợ | Không được tạo tự động; phải tự duy trì nếu cần |
| **TTL** | `@RedisHash(timeToLive = ...)`, `@TimeToLive` và cấu hình Repository | Dùng `set(key, value, Duration)`, `expire(...)` hoặc thao tác TTL khác |
| **Cấu trúc lồng nhau** | Thường ánh xạ thành các đường dẫn field, có thể tùy chỉnh converter | JSON giữ cấu trúc object/array dạng văn bản |
| **Khả năng trao đổi giữa ứng dụng** | Phải hiểu quy ước field, metadata và mapping | JSON thường dễ đọc và trao đổi hơn nếu các bên thống nhất schema |
| **Lưu trữ và hiệu năng** | Phụ thuộc số lượng/độ dài field, mã hóa Hash, index và cách truy cập | Phụ thuộc kích thước JSON, serializer, số lần giải mã và cách cập nhật |
| **Rủi ro chính** | Khóa/chỉ mục phụ lệch nếu sửa trực tiếp; mapping phải tương thích | Ghi đè toàn giá trị, thiếu chỉ mục, cạnh tranh khi đọc–sửa–ghi |

Không có kết luận “Hash luôn nhanh hơn JSON” hoặc “JSON luôn gọn hơn Hash”. Một Hash nhỏ có thể tận dụng biểu diễn bộ nhớ hiệu quả của Redis, nhưng nhiều trường và chỉ mục phụ cũng tạo chi phí. JSON có thể dễ trao đổi và debug hơn, nhưng việc đọc một thuộc tính thường vẫn phải tải và giải mã cả đối tượng.

Khi thiết kế, nên đo với kích thước đối tượng, mẫu truy cập và tải thực tế của ứng dụng.

## 7. Đi sâu vào thay đổi thuộc tính và chỉ mục

### 7.1. Repository quản lý quan hệ giữa thực thể và chỉ mục

Ví dụ có:

~~~java
@Indexed
private String email;
~~~

Giả sử ta lưu khách hàng với email `linh@example.com`, sau đó dùng Repository sửa thành `linh.new@example.com`:

~~~java
Customer c = repository.findById("c-101").orElseThrow();
c.setEmail("linh.new@example.com");
repository.save(c);
~~~

Khi dùng đúng API Repository, Spring Data Redis có cơ chế cập nhật các chỉ mục phụ liên quan đến những thuộc tính đã được đánh chỉ mục.

Nhưng nếu một tác vụ khác sửa thẳng field bằng:

~~~redis
HSET customers:c-101 email "linh.new@example.com"
~~~

thì trường trong Hash đã đổi, còn các tập chỉ mục do Repository duy trì **có thể vẫn phản ánh email cũ**. Kết quả là `findById(...)` và `findByEmail(...)` có nguy cơ cho thấy trạng thái không nhất quán.

**Quy tắc:** nếu Redis Hash thuộc quyền quản lý của Repository, ưu tiên cập nhật thông qua Repository hoặc cơ chế cập nhật có hiểu metadata/chỉ mục. Đừng tùy tiện gọi `HSET` trên cùng keyspace chỉ vì thao tác đó dễ thực hiện.

### 7.2. JSON không có chỉ mục Repository tự động

Dù trong JSON có thuộc tính `email`, lời gọi:

~~~java
jsonTemplate.opsForValue().set("customer:json:c-101", customer);
~~~

không khiến Redis tự hiểu cần tạo chỉ mục cho email. `@Indexed` trên lớp Java cũng không tự có tác dụng khi lưu bằng đường `opsForValue()`.

Nếu nghiệp vụ cần tìm theo email, các lựa chọn là:

- Duy trì ánh xạ riêng, chẳng hạn `customer:by-email:<email> -> <id>`, và xử lý cập nhật/xóa cho nhất quán.
- Chọn Repository khi kiểu truy vấn phù hợp với chỉ mục mà Spring Data Redis hỗ trợ.
- Dùng một hệ thống truy vấn/chỉ mục thích hợp khác nếu yêu cầu lọc, sắp xếp và tìm kiếm phức tạp.

Không nên coi việc gọi `KEYS customer:json:*`, lấy mọi JSON rồi lọc bằng Java là chiến lược truy vấn thường xuyên: nó đòi hỏi quét lượng lớn khóa và giải mã nhiều đối tượng.

### 7.3. Cập nhật một thuộc tính có phải lúc nào cũng rẻ hơn với Hash?

Ở mức lệnh Redis, một Hash hỗ trợ:

~~~redis
HSET customers:c-101 fullName "Linh Nguyễn"
~~~

trong khi JSON String lưu bằng `SET` không cho phép dùng `HSET` để cập nhật một trường JSON.

Tuy nhiên, khi ứng dụng thao tác thông qua `repository.save(entity)`, bộ Repository có thể ghi lại nhiều field hoặc cập nhật metadata liên quan. **Đừng suy luận rằng `save(...)` luôn chỉ phát sinh một `HSET` cho field đã thay đổi.**

Nếu cần tối ưu cập nhật từng trường, cần cân nhắc API thích hợp và yêu cầu đồng bộ metadata. Còn nếu giá trị JSON là một đối tượng nhỏ chủ yếu được đọc/ghi như một đơn vị, `GET`/`SET` có thể đơn giản và phù hợp.

## 8. Cạnh tranh cập nhật: tránh mất thay đổi

Giả sử hai request cùng đọc JSON:

~~~text
T1: GET customer:json:c-101 -> {fullName:"Linh", city:"Hà Nội"}
T2: GET customer:json:c-101 -> {fullName:"Linh", city:"Hà Nội"}

T1: sửa fullName -> "Nguyễn Linh"
T2: sửa city -> "Đà Nẵng"

T1: SET toàn JSON {fullName:"Nguyễn Linh", city:"Hà Nội"}
T2: SET toàn JSON {fullName:"Linh", city:"Đà Nẵng"}
                                     ^
                           Thay đổi fullName của T1 mất
~~~

Một lệnh `SET` đơn lẻ là thao tác nguyên tử tại Redis, nhưng **chuỗi GET → sửa Java → SET không tự động nguyên tử**. Nếu dữ liệu là trạng thái quan trọng có ghi đồng thời, cần cơ chế kiểm soát tranh chấp như `WATCH`/giao dịch phù hợp, Lua script, phiên bản dữ liệu hoặc thiết kế khác đáp ứng yêu cầu.

Với Redis Hash, `HSET key fullName ...` và `HSET key city ...` trên **hai field độc lập** có thể tránh dạng ghi đè toàn tài liệu ở ví dụ này. Nhưng những ràng buộc xuyên field, việc ghi nhiều lệnh và cập nhật chỉ mục Repository vẫn đòi hỏi chiến lược nhất quán riêng.

Một lời gọi `repository.save(...)` không đồng nghĩa toàn bộ hoạt động ghi Hash, metadata và chỉ mục phụ được thực hiện như một giao dịch ACID duy nhất. Tùy luồng thực thi và cấu hình, có thể có nhiều lệnh Redis.

## 9. Serializer là một phần của hợp đồng dữ liệu

Trong `RedisTemplate`, các loại serializer có mục đích khác nhau:

| Serializer | Vai trò |
|---|---|
| `keySerializer` | Mã hóa khóa Redis |
| `valueSerializer` | Mã hóa giá trị trong `opsForValue()` |
| `hashKeySerializer` | Mã hóa tên field khi dùng `opsForHash()` |
| `hashValueSerializer` | Mã hóa giá trị field khi dùng `opsForHash()` |

Các serializer này **không tự thay đổi kiểu dữ liệu Redis**. Ví dụ, cấu hình JSON cho `hashValueSerializer` rồi gọi `opsForHash().put(...)` sẽ tạo Hash có field chứa JSON, chứ không biến toàn bộ khóa thành String JSON.

Ví dụ:

~~~java
// Redis Hash: field "settings" có thể chứa JSON nếu hashValueSerializer là JSON.
template.opsForHash().put("customer:hash:c-101", "settings", settings);

// Redis String: value là JSON nếu valueSerializer là JSON.
template.opsForValue().set("customer:json:c-101", customer);
~~~

Vì cách đọc phụ thuộc vào serializer, một ứng dụng ghi JSON nhưng ứng dụng khác đọc bằng JDK serializer hoặc ngược lại có thể giải mã thất bại dù khóa tồn tại.

Với dữ liệu cần chia sẻ giữa dịch vụ, nên thống nhất:

- Tên khóa và cách đặt namespace.
- Kiểu Redis của từng nhóm khóa.
- Định dạng giá trị và mã hóa ký tự.
- Trường bắt buộc/tùy chọn, thay đổi schema và hành vi khi thiếu trường.
- Có hay không có metadata kiểu Java trong JSON, và quy tắc xử lý kiểu dữ liệu.

Một số JSON serializer mang thông tin kiểu như `_class` để hỗ trợ đa hình; một số serializer định kiểu cụ thể không cần làm vậy. Không nên coi cấu trúc JSON quan sát từ một serializer là mặc định của mọi `RedisTemplate`.

## 10. Những lỗi thường gặp khi trộn hai cơ chế

### Lỗi 1: Dùng GET để đọc khóa do Repository quản lý

~~~java
// Repository đã lưu tại "customers:c-101" dưới dạng Hash.
Customer customer = repository.findById("c-101").orElseThrow();

// Lệnh này sử dụng GET, không phải HGETALL.
Customer wrong = jsonTemplate.opsForValue().get("customers:c-101");
~~~

Dòng thứ hai gửi lệnh GET tới Redis Hash và có thể nhận `WRONGTYPE`. Thay serializer sẽ không sửa được lỗi kiểu dữ liệu vật lý.

### Lỗi 2: SET JSON đè lên khóa Hash

~~~java
// Không làm điều này với khóa mà Repository đang quản lý.
jsonTemplate.opsForValue().set("customers:c-101", customer);
~~~

`SET` có thể **thay thế giá trị hiện có của khóa**, kể cả khi giá trị trước đó là Hash. Sau đó Repository có thể không đọc được khóa vì kiểu dữ liệu đã thành String, đồng thời những khóa chỉ mục phụ có thể còn lại và trở nên không nhất quán.

Đây là lý do phải dùng **namespace rõ ràng** nếu hai cách lưu cùng tồn tại:

~~~text
customers:c-101          -> Repository / HASH
customer:json:c-101      -> RedisTemplate + JSON / STRING
~~~

### Lỗi 3: Cho rằng @RedisHash tự cấu hình RedisTemplate

~~~java
@RedisHash("customers")
class Customer {
    // ...
}
~~~

Annotation này giúp bộ ánh xạ Repository biết cách lưu thực thể. Nó không tự chọn serializer JSON cho mọi bean `RedisTemplate<Customer>`, không đổi `opsForValue()` thành `opsForHash()` và không tự cài đặt TTL cho mọi khóa do Template ghi.

### Lỗi 4: Dùng HSET trực tiếp nhưng vẫn trông chờ @Indexed

Nếu Repository duy trì chỉ mục email, sửa field email thẳng bằng `HSET` có thể làm chỉ mục lỗi thời. Cần thống nhất ai là chủ sở hữu dữ liệu và cách cập nhật.

### Lỗi 5: Gọi JSON là RedisJSON

JSON lưu bằng Redis String có thể đọc qua `GET`. Còn lệnh `JSON.GET`/`JSON.SET` thuộc cơ chế RedisJSON, yêu cầu khả năng tương ứng phía Redis. Chúng không tự hoạt động trên Redis String chứa JSON thuần.

### Lỗi 6: Đánh đồng tốc độ với số byte của một đối tượng mẫu

So sánh cần tính tới khối lượng chỉ mục, kích thước Hash, độ sâu đối tượng, tần suất thay đổi từng field, chi phí tuần tự hóa và số lượt mạng. Một thử nghiệm chỉ ghi/đọc một đối tượng nhỏ không đủ kết luận cho tất cả trường hợp.

## 11. TTL và vòng đời dữ liệu

Cả hai cơ chế đều lưu được dữ liệu có hạn sử dụng, nhưng cách khai báo khác nhau.

**Repository:**

~~~java
@RedisHash(value = "customers", timeToLive = 1800)
public class Customer {
    // ...
}
~~~

`timeToLive` ở đây tính bằng giây theo cơ chế annotation. Cũng có thể khai báo một thuộc tính `@TimeToLive` khi cần thời hạn linh hoạt theo từng thực thể.

Spring Data Redis có thể cần cơ chế theo dõi hết hạn và bản sao phụ phục vụ sự kiện hết hạn tùy cấu hình; do đó TTL của Repository không nhất thiết chỉ là một lời gọi `EXPIRE` đơn giản khi xét toàn bộ vòng đời metadata.

**RedisTemplate + JSON:**

~~~java
jsonTemplate.opsForValue().set(
        "customer:json:c-101",
        customer,
        java.time.Duration.ofMinutes(30)
);
~~~

Ở đây TTL là tham số ghi giá trị vào Redis. Nếu gọi `opsForValue().set(key, value)` không có TTL trên cùng khóa, lệnh `SET` thông thường sẽ làm mất TTL đang tồn tại trừ khi dùng cơ chế giữ TTL phù hợp.

Nếu cần duy trì thời hạn theo quy tắc nghiệp vụ, hãy làm rõ lúc nào TTL bắt đầu, được gia hạn, hoặc bị giữ nguyên khi cập nhật. Quy tắc đó độc lập với quyết định lưu Hash hay String JSON.

## 12. Thực hành kiểm chứng hai cách lưu

Dùng Redis dành cho môi trường phát triển, tạo một khách hàng với cùng dữ liệu:

~~~java
Customer c = new Customer(
        "c-101",
        "linh@example.com",
        "Nguyễn Linh",
        new Address("Hà Nội")
);

repository.save(c);
customerJsonCache.save(c);
~~~

Sau đó trong Redis CLI:

~~~redis
TYPE customers:c-101
TYPE customer:json:c-101

HGETALL customers:c-101
GET customer:json:c-101

TTL customers:c-101
TTL customer:json:c-101
~~~

Quan sát mong đợi:

1. `TYPE customers:c-101` là `hash`; `TYPE customer:json:c-101` là `string`.
2. `HGETALL` đọc được các cặp trường/giá trị của Hash; `GET` đọc chuỗi JSON.
3. TTL ở hai khóa có thể khác nhau: trong mã Repository đầu tiên chưa cấu hình TTL, còn đường JSON đã đặt hạn sử dụng 30 phút.
4. Kết quả của `repository.findByEmail(...)` phụ thuộc chỉ mục `@Indexed` do Repository duy trì; nó không tự truy vấn `customer:json:c-101`.

Có thể dùng thêm các lệnh kiểm tra kích thước:

~~~redis
HLEN customers:c-101
STRLEN customer:json:c-101

MEMORY USAGE customers:c-101
MEMORY USAGE customer:json:c-101
~~~

`HLEN` đo số field trong Hash; `STRLEN` đo chiều dài byte của Redis String; `MEMORY USAGE` ước tính bộ nhớ Redis phân bổ cho từng khóa. Các phép đo này không bao gồm mọi chi phí của toàn bộ mô hình ứng dụng, đặc biệt là những chỉ mục phụ Repository tạo ngoài khóa Hash chính.

Không nên chuyển thẳng số liệu của một đối tượng mẫu thành kết luận hiệu năng production.

## 13. Chọn cách nào cho từng yêu cầu?

### Tình huống A: Quản lý một loại thực thể, cần truy xuất bằng ID và vài thuộc tính được đánh chỉ mục

Ví dụ: đối tượng phiên làm việc hoặc hồ sơ đơn giản có truy vấn theo một số trường cố định.

Repository là lựa chọn đáng xem xét nếu những truy vấn cần thiết được Redis Repository hỗ trợ. Nó giúp giữ mã CRUD ở mức thực thể, nhưng vẫn cần hiểu giới hạn chỉ mục, dữ liệu phụ và cách cập nhật an toàn.

### Tình huống B: Lưu kết quả tính toán hoặc phản hồi API vào cache

Ví dụ: JSON của thông tin sản phẩm được tính sẵn, truy xuất bằng mã sản phẩm, ít khi sửa từng field.

`RedisTemplate` với serializer JSON và `opsForValue()` thường đơn giản: truy cập trực tiếp một khóa, đọc/ghi toàn bộ đối tượng, đặt TTL khi ghi. Không cần tạo một bộ Repository chỉ để lưu một giá trị cache ngắn hạn.

### Tình huống C: Cập nhật riêng vài bộ đếm, cờ hoặc trường độc lập

Nếu nghiệp vụ thực chất cần thao tác từng field và không cần ánh xạ một aggregate bằng Repository, `HashOperations` trực tiếp hoặc các lệnh Redis chuyên biệt có thể phù hợp hơn. Việc chọn Redis Hash ở đây là một lựa chọn thiết kế, không bắt buộc phải có `@RedisHash`.

### Tình huống D: Tìm kiếm phức tạp nhiều điều kiện và phân trang ổn định

Không nên mặc định Redis Repository hay JSON String tự đáp ứng. Hãy kiểm tra khả năng đánh chỉ mục/truy vấn, yêu cầu tính nhất quán, thứ tự và phân trang; có thể cần hệ thống dữ liệu hoặc công cụ chỉ mục chuyên dụng.

### Tình huống E: Nhiều dịch vụ bằng nhiều ngôn ngữ cần đọc chung dữ liệu

JSON với schema thống nhất thường dễ trao đổi giữa các nền tảng. Repository Hash vẫn có thể đọc được từ dịch vụ khác nếu công bố quy ước keyspace, field, metadata và mã hóa; tuy nhiên, cách ánh xạ nội bộ của Spring Data Redis không tự là một giao thức liên dịch vụ ổn định.

## 14. Nếu muốn chuyển từ Repository Hash sang JSON thì sao?

Không thể chỉ đổi serializer rồi đọc lại các khóa Hash cũ dưới dạng JSON. Cần xem đây là **chuyển đổi dữ liệu**, vì kiểu Redis khác nhau.

Một phương án chuyển đổi an toàn về mặt thiết kế:

1. Định nghĩa namespace mới, chẳng hạn `customer:json:<id>`, cùng schema JSON rõ ràng.
2. Đọc thực thể cũ qua Repository hoặc cơ chế đọc Hash tương thích.
3. Ghi dữ liệu mới qua RedisTemplate JSON và kiểm tra đọc lại.
4. Xác định cách xử lý các thay đổi đồng thời trong thời gian chuyển đổi: ghi kép có kiểm soát, cơ chế đồng bộ hoặc cửa sổ bảo trì tùy yêu cầu.
5. Chuyển luồng đọc của ứng dụng sang khóa mới sau khi đã kiểm tra đủ điều kiện.
6. Đặt kế hoạch hết hạn/dọn dữ liệu cũ, gồm Hash, tập keyspace và chỉ mục phụ nếu Repository đã tạo.

Nếu dữ liệu cache không quan trọng và có thể tái tạo, đôi khi dễ hơn là đổi namespace rồi để các khóa cũ hết hạn theo TTL. Với dữ liệu trạng thái nghiệp vụ, phải đánh giá kỹ việc giữ tính nhất quán trong lúc chuyển đổi.

Tránh vừa xóa vừa ghi đè trên namespace của Repository khi vẫn còn các luồng cũ đang hoạt động.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Lớp `Customer` có `@RedisHash`. Nếu dùng `RedisTemplate<String, Customer>` với JSON serializer và gọi `opsForValue().set(...)` thì Redis lưu Hash hay String?

**Trả lời:** Redis String. `@RedisHash` không tự chuyển `ValueOperations` thành cơ chế Repository. JSON serializer quyết định nội dung byte của giá trị String.

**Câu 2.** Đã lưu `customers:c-101` bằng Repository. Có thể dùng `GET customers:c-101` để lấy JSON hay không?

**Trả lời:** Không. Khóa này thường là Redis Hash; `GET` dành cho String và sẽ gặp `WRONGTYPE` nếu dùng trên Hash.

**Câu 3.** Có thể dùng `RedisTemplate` để lưu Hash không?

**Trả lời:** Có. Sử dụng `opsForHash()` và cấu hình serializer phù hợp. Nhưng thao tác Hash thủ công không đồng nghĩa được hưởng ánh xạ/metadata/chỉ mục của Repository.

**Câu 4.** JSON có trường `email`, vậy `@Indexed` có tự giúp `opsForValue()` tìm theo email không?

**Trả lời:** Không. `@Indexed` thuộc cơ chế ánh xạ và chỉ mục Repository, không tự áp dụng cho Redis String JSON do Template ghi.

**Câu 5.** Muốn đổi email của thực thể Repository, có nên dùng trực tiếp `HSET` vào khóa Hash không?

**Trả lời:** Cần rất thận trọng. Nếu field được đánh chỉ mục, chỉnh Hash trực tiếp có thể bỏ qua cập nhật chỉ mục phụ. Nên cập nhật thông qua cơ chế có quản lý mapping và chỉ mục.

**Câu 6.** Nếu chỉ lưu cache JSON theo ID, không cần truy vấn theo thuộc tính, tại sao RedisTemplate có thể phù hợp hơn?

**Trả lời:** Vì ứng dụng chỉ cần `SET`/`GET` và TTL trên một khóa đã biết; JSON cung cấp biểu diễn toàn đối tượng đơn giản, không cần quản lý thêm cơ chế Repository và chỉ mục cho nhu cầu đó.

## 16. Điều cần ghi nhớ

- `@RedisHash` + **Redis Repository** là cơ chế ánh xạ thực thể thành Redis Hash, kèm định danh, metadata và chỉ mục phụ khi cấu hình.
- `RedisTemplate` + **JSON value serializer** + `opsForValue()` lưu một JSON trong Redis String. RedisTemplate vẫn có thể làm việc với Hash, Set, List và các kiểu dữ liệu khác.
- **Kiểu dữ liệu Redis** quyết định dùng `GET` hay `HGET`. **Serializer** quyết định cách dữ liệu trở lại thành đối tượng Java. Hai khái niệm này không thay thế nhau.
- Repository và Template có thể kết hợp trong cùng ứng dụng, nhưng cần phân biệt namespace và quyền sở hữu dữ liệu để tránh `WRONGTYPE`, ghi đè khóa và chỉ mục không nhất quán.
- Chọn phương án lưu theo **cách truy cập và cập nhật thực tế**, yêu cầu truy vấn, TTL, tính nhất quán, khả năng chia sẻ dữ liệu và chi phí vận hành.

### Tài liệu tham khảo

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/).
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/).

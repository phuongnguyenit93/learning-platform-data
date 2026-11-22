# Ánh xạ đối tượng sang Redis Hash trong Spring Data Redis

## 1. Mục tiêu bài học

Khi dùng Redis làm nơi lưu trữ đối tượng Java, một lựa chọn phổ biến là biểu diễn mỗi đối tượng bằng một **Redis Hash**: một key Redis chứa tập hợp các cặp `field → value`. Spring Data Redis cung cấp cơ chế chuyển đổi qua lại giữa đối tượng và cấu trúc này, giúp ứng dụng thao tác bằng Java mà vẫn tận dụng được các lệnh Hash của Redis.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa **Redis key**, **hash field** và **giá trị của field**.
- Dùng `@RedisHash`, `@Id` và Redis Repository để lưu/đọc đối tượng.
- Dự đoán cách trường đơn giản, đối tượng lồng nhau, danh sách và map được biểu diễn trong Redis Hash.
- Phân biệt mapping mặc định của Repository với cách dùng `HashOperations` hoặc `HashMapper`.
- Tùy biến chuyển đổi dữ liệu, xử lý chỉ mục, TTL, tham chiếu và cập nhật một phần.
- Nhận diện các vấn đề khi ghi đè toàn bộ hash, thay đổi cấu trúc lớp Java hoặc cập nhật đồng thời.

## 2. Redis Hash lưu trữ đối tượng như thế nào?

Giả sử ứng dụng có một khách hàng:

~~~java
Customer customer = new Customer(
    "c-101",
    "lan@example.com",
    "Lan",
    new Address("Hà Nội", "VN")
);
~~~

Ta có thể biểu diễn đối tượng ấy trong Redis bằng **một key** tên `customers:c-101` và nhiều **field**:

~~~text
Redis key: customers:c-101
Redis type: hash

id              -> c-101
email           -> lan@example.com
displayName     -> Lan
address.city    -> Hà Nội
address.country -> VN
_class          -> com.example.redis.domain.Customer
~~~

Ở đây:

| Thành phần | Ý nghĩa |
|---|---|
| `customers:c-101` | Key của bản ghi trong Redis, thường được ghép từ *keyspace* và ID. |
| `id`, `email`, `address.city` | Các field bên trong hash; mỗi field có tên riêng. |
| `c-101`, `lan@example.com`, `Hà Nội` | Các giá trị Redis lưu cho từng field. |
| `_class` | Metadata về kiểu Java để bộ chuyển đổi có thể dựng lại đối tượng. |

Có thể hình dung luồng dữ liệu:

~~~text
Customer (Java)
    |
    | MappingRedisConverter / RedisConverter
    v
Map<field, byte[]> -- ghi vào --> Redis Hash "customers:c-101"
    ^
    | đọc và chuyển đổi ngược
    |
Customer (Java)
~~~

**Redis Hash không phải JSON document.** Với Hash, `address.city` là một tên field của Redis, không phải toán tử truy cập JSON. Redis chỉ biết các field và giá trị dạng byte; Spring Data Redis chịu trách nhiệm diễn giải tên field, kiểu Java và cách dựng lại đối tượng.

Nếu tự quản lý dữ liệu bằng `StringRedisTemplate`, bạn cũng có thể tạo hash trực tiếp:

~~~redis
HSET customers:c-101 id c-101 email lan@example.com displayName Lan
HGET customers:c-101 email
HGETALL customers:c-101
TYPE customers:c-101
~~~

Những lệnh này minh họa cấu trúc Hash. Đối với dữ liệu do Repository quản lý, nên dùng Repository để ghi nhằm giữ đồng bộ các chỉ mục và metadata liên quan.

## 3. Hai tầng cần phân biệt

Spring Data Redis hỗ trợ nhiều con đường làm việc với Hash:

| Cách dùng | Thành phần chính | Mức độ tự động | Tình huống phù hợp |
|---|---|---|---|
| **Redis Repository** | `@RedisHash`, `CrudRepository`, `MappingRedisConverter` | Tự quản lý keyspace, ID, mapping và chỉ mục được cấu hình. | Lưu các thực thể Java với thao tác CRUD. |
| **Thao tác Hash trực tiếp** | `RedisTemplate` / `StringRedisTemplate`, `HashOperations` | Ứng dụng tự chọn key, field, serialization và vòng đời dữ liệu. | Cache theo field, ghi/đọc từng field, dữ liệu có cấu trúc đơn giản. |
| **HashMapper + HashOperations** | `HashMapper`, `ObjectHashMapper`, `JacksonHashMapper` | Mapper chuyển đối tượng sang map; ứng dụng tự gọi Redis. | Muốn kiểm soát định dạng Hash mà không dùng Repository. |

Ba cách trên có thể cùng tồn tại trong một dự án, nhưng **không nên tùy tiện ghi vào cùng một key bằng nhiều cơ chế**. Chúng có thể sử dụng serializer, metadata và cách quản lý chỉ mục khác nhau.

Phần tiếp theo tập trung vào cơ chế **Object-to-Hash Mapping của Redis Repository**.

## 4. Ví dụ hoàn chỉnh với Redis Repository

### 4.1. Chuẩn bị

Một dự án Spring Boot cần dependency `spring-boot-starter-data-redis`. Nếu dùng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Nếu dự án sử dụng Spring Boot BOM/parent, hãy để BOM quản lý phiên bản của các thư viện Spring Data; tránh ghép tùy ý các phiên bản không tương thích.

Chạy một Redis cục bộ, ví dụ:

~~~bash
docker run --rm --name redis-mapping-demo -p 6379:6379 redis:7-alpine
~~~

Cấu hình kết nối trong `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Spring Boot thường tự cấu hình Redis connection, template và hỗ trợ repository khi dependency và cấu trúc package phù hợp. Với cấu hình Spring thuần hoặc repository nằm ngoài vùng quét, cần cấu hình `@EnableRedisRepositories` tương ứng.

### 4.2. Khai báo lớp lồng nhau

Tệp `Address.java`:

~~~java
package com.example.redis.domain;

public class Address {
    private String city;
    private String country;

    public Address() {
    }

    public Address(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }
}
~~~

`Address` không cần có `@RedisHash`: ở đây nó là một phần lồng bên trong `Customer`, được ánh xạ vào các field của hash chứa khách hàng.

### 4.3. Khai báo thực thể Redis

Tệp `Customer.java`:

~~~java
package com.example.redis.domain;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;
    private Address address;
    private List<String> tags = new ArrayList<>();

    public Customer() {
    }

    public Customer(String id, String email, String displayName, Address address) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
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

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Ý nghĩa của các annotation:

- `@RedisHash("customers")` chọn **keyspace** `customers`. Redis key của thực thể sẽ có dạng `customers:<id>`.
- `@Id` (thuộc `org.springframework.data.annotation`) chỉ ra trường nhận dạng. Nếu ID là `null` khi lưu bằng Repository, Spring Data có thể sinh ID; nếu cung cấp sẵn như `c-101`, ID đó được dùng để tạo key.
- `@Indexed` yêu cầu tạo **secondary index** cho `email`, hỗ trợ các truy vấn Repository dựa trên giá trị của trường này.
- `displayName`, `address` và `tags` là thuộc tính thông thường, được ánh xạ theo quy tắc mặc định.

Lưu ý `@RedisHash` không phải annotation `@Entity` của JPA. Redis Repository sử dụng cơ chế mapping riêng và không tạo bảng SQL.

### 4.4. Khai báo Repository

Tệp `CustomerRepository.java`:

~~~java
package com.example.redis.repository;

import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import com.example.redis.domain.Customer;

public interface CustomerRepository extends CrudRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
}
~~~

`CrudRepository<Customer, String>` định nghĩa loại thực thể và kiểu ID. Method `findByEmail` dựa trên chỉ mục đã khai báo bằng `@Indexed`. Redis không tự tạo secondary index như cơ sở dữ liệu quan hệ; nếu bỏ annotation chỉ mục mà vẫn yêu cầu truy vấn theo email, không thể mặc nhiên trông chờ truy vấn ấy hoạt động.

### 4.5. Ghi và đọc một đối tượng

Ví dụ `CommandLineRunner` đặt trong lớp được Spring Boot quét:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import com.example.redis.domain.Address;
import com.example.redis.domain.Customer;
import com.example.redis.repository.CustomerRepository;

@SpringBootApplication
public class RedisMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerRepository repository) {
        return args -> {
            Customer customer = new Customer(
                "c-101",
                "lan@example.com",
                "Lan",
                new Address("Hà Nội", "VN")
            );
            customer.setTags(List.of("vip", "newsletter"));

            repository.save(customer);

            repository.findById("c-101")
                .ifPresent(found -> System.out.println(found.getDisplayName()));

            repository.findByEmail("lan@example.com")
                .ifPresent(found -> System.out.println(found.getId()));
        };
    }
}
~~~

Lưu một thực thể bằng `save` sẽ chuyển trạng thái Java thành các field trong Hash. `findById` thực hiện chiều ngược lại, đọc Hash rồi tái dựng `Customer`, bao gồm `Address` và `tags`. Nếu dữ liệu được đọc trong Redis đã bị sửa thủ công theo định dạng không phù hợp, bước ánh xạ ngược có thể thất bại hoặc trả về dữ liệu không mong muốn.

### 4.6. Quan sát kết quả bằng Redis CLI

Trong Redis CLI, chạy:

~~~redis
TYPE customers:c-101
HGETALL customers:c-101
HGET customers:c-101 address.city
HGET customers:c-101 email
SMEMBERS customers:email:lan@example.com
~~~

Bỏ qua thứ tự field trong kết quả của `HGETALL`, bạn có thể thấy các cặp giá trị có dạng:

~~~text
_class          = com.example.redis.domain.Customer
id              = c-101
email           = lan@example.com
displayName     = Lan
address.city    = Hà Nội
address.country = VN
tags.[0]        = vip
tags.[1]        = newsletter
~~~

Tên `_class` được ghi theo cấu hình mapping kiểu Java; phần bên dưới sẽ giới thiệu cách đổi thành alias. `SMEMBERS customers:email:lan@example.com` minh họa một Set dùng làm secondary index chứa ID `c-101`. Ngoài hash chính, Repository có thể tạo thêm các key phục vụ quản lý keyspace, chỉ mục hoặc TTL.

**Không dùng `KEYS *` để dò dữ liệu trên Redis production lớn.** Khi cần tìm key theo mẫu để chẩn đoán, ưu tiên `SCAN` với phạm vi kiểm soát.

## 5. Quy tắc ánh xạ mặc định của RedisConverter

Redis Repository dùng `RedisConverter`, thường là `MappingRedisConverter`, để chuyển thuộc tính Java thành cặp tên field và giá trị dạng byte. Các quy tắc tiêu biểu:

| Kiểu thuộc tính trong Java | Ví dụ | Các field có thể xuất hiện trong Redis Hash |
|---|---|---|
| Giá trị đơn giản | `String name = "Lan"` | `name = Lan` |
| Số, boolean, enum | `int age = 30` | `age = 30` sau bước chuyển đổi sang dữ liệu Redis |
| Mảng byte | `byte[] avatar` | Field `avatar` với giá trị nhị phân |
| Đối tượng lồng nhau | `address.city = "Hà Nội"` | `address.city = Hà Nội` |
| Danh sách giá trị đơn giản | `tags = ["vip", "new"]` | `tags.[0] = vip`; `tags.[1] = new` |
| Map giá trị đơn giản | `labels = {"tier": "gold"}` | `labels.[tier] = gold` |
| Danh sách đối tượng | `addresses[0].city` | `addresses.[0].city = Hà Nội` |
| Map chứa đối tượng | `places["home"].city` | `places.[home].city = Hà Nội` |

Các tên field trên phản ánh **đường dẫn thuộc tính** (property path), dùng dấu chấm và ngoặc vuông theo quy ước mapping. Map key khi được ánh xạ phẳng cần thuộc nhóm kiểu đơn giản phù hợp, chẳng hạn String hoặc Number.

Một số điểm cần nhớ:

1. Các ví dụ hiển thị giá trị ở dạng dễ đọc. Bên dưới, Redis lưu dãy byte, nên kết quả cụ thể còn phụ thuộc converter và serializer.
2. Thuộc tính `null` không có ý nghĩa như một “giá trị null” mặc định trong Redis Hash; thông thường không có field tương ứng. Khi đọc lại, cần quan tâm giá trị mặc định của Java và logic nghiệp vụ.
3. Với interface hoặc kiểu trừu tượng lồng nhau, Spring Data có thể cần metadata `_class` bổ sung để xác định kiểu cụ thể.
4. Thứ tự các field của một Redis Hash không phải thứ tự thuộc tính trong lớp Java; không viết code phụ thuộc vào thứ tự `HGETALL`.
5. Đổi tên field Java hoặc kiểu thuộc tính có thể khiến dữ liệu Hash đã lưu trước đó không còn ánh xạ đúng. Cần thiết kế chiến lược tương thích khi nâng cấp schema.

### Vì sao không chỉ dùng một field JSON?

Có hai cách biểu diễn cùng một dữ liệu:

~~~text
Cách A — Redis Hash, trải phẳng:
    address.city    = Hà Nội
    address.country = VN

Cách B — Một field chứa JSON:
    address = {"city":"Hà Nội","country":"VN"}
~~~

Cách A phù hợp với cơ chế mapping mặc định của Repository và có thể truy cập theo hash field khi biết quy ước đặt tên. Cách B giữ đối tượng con thành một giá trị độc lập, nhưng muốn đọc/sửa nội dung bên trong thì phải có logic JSON hoặc converter thích hợp. Không nên coi hai cách này là cùng một định dạng lưu trữ.

## 6. Tùy biến tên kiểu và chuyển đổi dữ liệu

### 6.1. Rút gọn metadata kiểu bằng `@TypeAlias`

Mặc định, field `_class` có thể chứa tên class đầy đủ:

~~~text
_class = com.example.redis.domain.Customer
~~~

Để tránh lưu tên package dài trong dữ liệu, thêm:

~~~java
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
@TypeAlias("customer")
public class Customer {
    // Các thuộc tính và constructor như ví dụ trước.
}
~~~

Khi Spring Data nhận biết alias này trong mapping context, dữ liệu có thể được ghi thành:

~~~text
_class = customer
~~~

Alias là một phần hợp đồng dữ liệu: cần giữ ổn định hoặc có kế hoạch chuyển đổi nếu thay đổi alias, cấu hình quét entity hay cấu trúc class. Không tùy tiện xóa `_class` vì converter có thể cần thông tin kiểu để đọc lại đối tượng, nhất là với các kiểu đa hình.

### 6.2. `RedisCustomConversions`

Nếu muốn biến một kiểu phức tạp thành một field nhị phân duy nhất, có thể đăng ký cặp converter ghi/đọc. Ví dụ thay vì trải phẳng `address.city` và `address.country`, ta biểu diễn `Address` dưới dạng chuỗi JSON UTF-8 trong một field `address`.

Mã minh họa (sử dụng Jackson `ObjectMapper` đã được cấu hình phù hợp với ứng dụng):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class AddressToBytes implements Converter<Address, byte[]> {
    private final ObjectMapper objectMapper;

    public AddressToBytes(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public byte[] convert(Address address) {
        try {
            return objectMapper.writeValueAsBytes(address);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Cannot serialize Address", exception);
        }
    }
}

@ReadingConverter
public class BytesToAddress implements Converter<byte[], Address> {
    private final ObjectMapper objectMapper;

    public BytesToAddress(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Address convert(byte[] bytes) {
        try {
            return objectMapper.readValue(bytes, Address.class);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Cannot deserialize Address", exception);
        }
    }
}
~~~

Đăng ký cả hai converter vào `RedisCustomConversions` trong cấu hình của Repository, chẳng hạn:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@Configuration
public class RedisConversionConfiguration {

    @Bean
    RedisCustomConversions redisCustomConversions(ObjectMapper objectMapper) {
        return new RedisCustomConversions(List.of(
            new AddressToBytes(objectMapper),
            new BytesToAddress(objectMapper)
        ));
    }
}
~~~

Đoạn minh họa cần các import ứng với `Address` và Jackson `ObjectMapper` của dự án. Với ứng dụng có cấu hình Redis tùy chỉnh, hãy bảo đảm bean `RedisCustomConversions` thực sự được `MappingRedisConverter` đang dùng tiếp nhận.

Kết quả dạng logic:

~~~text
Trước khi tùy biến:
    address.city    = Hà Nội
    address.country = VN

Sau khi tùy biến Address <-> byte[]:
    address = {"city":"Hà Nội","country":"VN"}
~~~

Các converter nhận/trả `Map<String, byte[]>` còn cho phép kiểm soát nhiều hash field cùng lúc. Khi chọn cách tùy biến này, cần đặc biệt chú ý tính ổn định của tên field và khả năng đọc lại dữ liệu cũ.

**Chú ý về chỉ mục:** cơ chế phát hiện secondary index của Spring Data không tự động thay đổi theo một custom converter. Việc ghi một đối tượng thành một field duy nhất không có nghĩa là mọi thuộc tính con vẫn truy vấn được theo cách trước đó.

## 7. Dùng HashOperations khi muốn thao tác từng field

Repository phù hợp khi đơn vị nghiệp vụ là **một thực thể**. Nếu chỉ muốn lưu vài field độc lập, `StringRedisTemplate` và `HashOperations` đơn giản hơn.

~~~java
import java.util.Map;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerCache {

    private final StringRedisTemplate redis;

    public CustomerCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String id, String email, String displayName) {
        redis.opsForHash().putAll(
            "customer-cache:" + id,
            Map.of("email", email, "displayName", displayName)
        );
    }

    public String findEmail(String id) {
        Object value = redis.opsForHash().get("customer-cache:" + id, "email");
        return value == null ? null : value.toString();
    }

    public void rename(String id, String displayName) {
        redis.opsForHash().put("customer-cache:" + id, "displayName", displayName);
    }
}
~~~

Đây là cơ chế **thủ công**: bạn chủ động đặt key `customer-cache:<id>`, chọn field, không tự có `@Indexed` hay `@RedisHash`. Dùng namespace riêng giúp tránh xung đột với các key do Repository quản lý.

`opsForHash().put(...)` thường tương ứng với thao tác ghi một field; `opsForHash().entries(...)` đọc tất cả field. Nếu key có rất nhiều field hoặc giá trị lớn, việc đọc toàn bộ Hash có thể tốn mạng và bộ nhớ; hãy chọn lệnh theo nhu cầu.

## 8. HashMapper là gì và khác RedisConverter ra sao?

`HashMapper<T, K, V>` là hợp đồng chuyển một đối tượng Java sang `Map<K, V>` và ngược lại:

~~~java
Map<K, V> toHash(T object);
T fromHash(Map<K, V> hash);
~~~

Một số lựa chọn theo phiên bản Spring Data Redis:

- `ObjectHashMapper`: ánh xạ đối tượng thành map có field/value dạng byte.
- `BeanUtilsHashMapper`: dựa trên JavaBean và các thuộc tính được hỗ trợ.
- `JacksonHashMapper`: dùng Jackson 3, có tùy chọn biểu diễn cấu trúc lồng nhau hoặc làm phẳng.
- `Jackson2HashMapper`: dùng Jackson 2; các dòng Spring Data Redis mới đánh dấu deprecated, nên kiểm tra tài liệu và phiên bản dự án trước khi chọn.

Ví dụ ý tưởng với `ObjectHashMapper`:

~~~java
HashMapper<Object, byte[], byte[]> mapper = new ObjectHashMapper();

Map<byte[], byte[]> hash = mapper.toHash(customer);

// HashOperations với hash key/value serializer tương ứng
hashOperations.putAll("mapped-customers:c-101", hash);

Map<byte[], byte[]> saved = hashOperations.entries("mapped-customers:c-101");
Customer restored = (Customer) mapper.fromHash(saved);
~~~

Ở đây `hashOperations` cần được khai báo với kiểu và serializer tương thích với `byte[]`; đoạn mã nhằm làm rõ vai trò của mapper. Với `HashMapper`, bạn **tự quản lý** key Redis, TTL và chỉ mục, trong khi Redis Repository tích hợp các chức năng này theo cấu hình entity.

Đặc biệt, **RedisConverter của Repository không đồng nghĩa với JacksonHashMapper**. Cả hai cùng xử lý bài toán đối tượng ↔ Hash nhưng có cấu trúc dữ liệu và cách tích hợp khác nhau. Không thể mặc định đổi một mapper bất kỳ rồi đọc được mọi Hash do Repository đã ghi.

### 8.1. Làm phẳng với JacksonHashMapper

Giả sử một lớp có thuộc tính `address`. Khi dùng Jackson mapper không làm phẳng, Hash có thể chứa:

~~~text
address = {"city":"Hà Nội","country":"VN"}
~~~

Khi bật chế độ flatten, có thể thành:

~~~text
address.city    = Hà Nội
address.country = VN
~~~

Chế độ flatten của Jackson mapper có giới hạn đối với tên thuộc tính hoặc map key chứa dấu chấm, ngoặc vuông vì chúng có thể xung đột với đường dẫn JSON. Nếu chọn flatten, hãy thiết kế tên field phù hợp và thử khả năng ánh xạ ngược trong phiên bản thư viện đang sử dụng.

## 9. Ánh xạ liên kết giữa các thực thể với `@Reference`

Không phải đối tượng lồng nào cũng nên sao chép toàn bộ field vào Hash chính. Nếu một khách hàng tham chiếu một tài khoản khác đã được lưu độc lập, có thể khai báo:

~~~java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Reference
    private Customer referredBy;

    // Constructor và accessor tương ứng.
}
~~~

Thay vì sao chép toàn bộ đối tượng `referredBy`, hash lưu tham chiếu khóa Redis có dạng:

~~~text
referredBy = customers:c-077
~~~

Khi đọc đối tượng, Spring Data có thể phân giải tham chiếu để dựng liên kết. Tuy nhiên:

- Lưu đối tượng cha **không tự động lưu** thay đổi của đối tượng được tham chiếu; cần lưu thực thể được tham chiếu riêng.
- Đây không phải foreign key có ràng buộc toàn vẹn như trong cơ sở dữ liệu quan hệ.
- Chỉ mục của các thuộc tính thuộc thực thể được tham chiếu không được tự động giải quyết như chỉ mục của thuộc tính trực tiếp.

Vì vậy, hãy cân nhắc giữa **nhúng (embedding)** và **tham chiếu (reference)** theo chu kỳ cập nhật và cách đọc dữ liệu.

## 10. Chỉ mục `@Indexed` liên quan thế nào đến mapping?

Redis không cung cấp truy vấn tùy ý trên các field của Hash theo kiểu `SELECT ... WHERE`. Spring Data Redis hỗ trợ một số truy vấn thông qua **secondary index** được duy trì bên ngoài Hash chính.

Ví dụ:

~~~java
@RedisHash("customers")
public class Customer {
    @Id private String id;
    @Indexed private String email;
}
~~~

Khi lưu khách hàng có email `lan@example.com`, ngoài hash `customers:c-101`, cơ chế repository có thể lưu quan hệ tương đương:

~~~redis
SADD customers:email:lan@example.com c-101
~~~

`findByEmail("lan@example.com")` dựa vào index để tìm ID rồi đọc thực thể. Tương tự, một số thuộc tính lồng nhau có thể được đánh dấu index nếu phù hợp.

Các điểm quan trọng:

- `@Indexed` tạo thêm Redis Set và chi phí cập nhật; chỉ lập chỉ mục cho các trường cần truy vấn.
- Chỉ mục thường được cập nhật khi ứng dụng ghi/xóa thông qua Repository. Nếu sửa Hash bằng `HSET` trực tiếp, phần chỉ mục có thể không phản ánh thay đổi ấy.
- Một Set index không tự bảo đảm giá trị duy nhất. `@Indexed` không tương đương `UNIQUE` constraint.
- Cần đánh giá tính nhất quán, phục hồi index và hành vi khi key hết hạn trước khi dùng Redis Repository như nguồn dữ liệu chính cho hệ thống cần ràng buộc mạnh.

## 11. Thời gian sống (TTL) của thực thể Hash

Một Hash có thể tự hết hạn. Trong Repository, cách đơn giản là khai báo TTL cố định trên lớp:

~~~java
@RedisHash(value = "sessions", timeToLive = 3600)
public class SessionInfo {
    @Id
    private String id;
    private String username;
}
~~~

`3600` ở đây là số **giây**. Sau khi lưu, có thể kiểm tra:

~~~redis
TTL sessions:s-101
~~~

Với TTL thay đổi theo từng thực thể, có thể dùng một trường được đánh dấu `@TimeToLive`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionInfo {
    @Id
    private String id;

    @TimeToLive
    private Long secondsRemaining;

    // Constructor, getter và setter tương ứng.
}
~~~

Không đặt `@TimeToLive` đồng thời trên một method và một property của cùng lớp. Khi đọc dữ liệu, giá trị TTL có thể phản ánh thời gian còn lại thay vì thời lượng ban đầu đã cấu hình. Việc dọn dẹp index và phát sự kiện hết hạn còn phụ thuộc cơ chế expiration/keyspace notification và cấu hình Redis.

Nếu trộn thao tác ghi thủ công với Repository, hãy kiểm tra liệu thao tác đó có giữ lại TTL dự kiến không. Tùy lệnh Redis được sử dụng, cập nhật field và thay thế cả key có thể có hành vi khác nhau về TTL.

## 12. Cập nhật một phần và rủi ro ghi đè

Một điểm dễ bỏ qua: **ghi một đối tượng bằng cơ chế Object-to-Hash của Redis Repository có thể xóa nội dung Hash cũ rồi dựng lại từ trạng thái đối tượng mới**. Các field do hệ thống khác thêm vào nhưng không thuộc mapping sẽ bị mất.

Ví dụ:

~~~text
Hash trước khi save:
    id           = c-101
    displayName  = Lan
    legacyFlag   = keep-me

Đối tượng Java không có thuộc tính legacyFlag.

Sau repository.save(customer):
    id           = c-101
    displayName  = Lan
    (legacyFlag không còn)
~~~

Vì vậy:

- Không dùng key Repository làm nơi lưu các field ngoài mapping trừ khi có cơ chế quản trị rõ ràng.
- Nếu nhiều tiến trình cập nhật những field khác nhau, thao tác đọc → sửa → `save` có thể ghi đè thay đổi đến từ tiến trình khác.
- `save` không phải phép “merge tất cả field chưa đụng tới” và cũng không tự tạo cơ chế optimistic locking như JPA.

Khi chỉ muốn sửa một thuộc tính, Spring Data có `PartialUpdate` thông qua `RedisKeyValueTemplate`:

~~~java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

public void updateCustomerName(RedisKeyValueTemplate template) {
    PartialUpdate<Customer> update =
        new PartialUpdate<Customer>("c-101", Customer.class)
            .set("displayName", "Lan Nguyễn")
            .set("address.city", "Đà Nẵng");

    template.update(update);
}
~~~

`PartialUpdate` hỗ trợ `set`, `del` và tùy chọn cập nhật TTL. Nó phù hợp cho những thay đổi có phạm vi nhỏ, nhưng cập nhật cấu trúc phức tạp (collection, map, object) vẫn có thể cần nhiều thao tác Redis; đường dẫn vào thuộc tính được custom converter xử lý thành một field có thể không hỗ trợ cập nhật sâu như `address.city`.

**Một cập nhật từng field không tự giải quyết mọi xung đột đồng thời.** Khi tính đúng đắn phụ thuộc vào kiểm tra rồi ghi hoặc nhiều key phải đổi nhất quán, hãy thiết kế giao thức đồng bộ tương ứng, ví dụ Redis transaction có `WATCH` hoặc Lua script, và xác định rõ phạm vi nhất quán cần bảo đảm.

## 13. Chọn chiến lược mapping phù hợp

| Yêu cầu | Gợi ý |
|---|---|
| CRUD theo ID của thực thể Java, cần Repository và chỉ mục được quản lý | `@RedisHash` + `CrudRepository` |
| Chỉ cần cập nhật một vài field của Hash, tự quản lý key | `StringRedisTemplate.opsForHash()` |
| Muốn ánh xạ Java object thành Map trước khi ghi | `HashMapper` + `HashOperations` |
| Muốn lưu đối tượng con trong một field nhị phân/JSON | `RedisCustomConversions` hoặc HashMapper tương ứng |
| Muốn tra cứu theo một thuộc tính ngoài ID | Xem xét `@Indexed` và chi phí index |
| Muốn giới hạn thời gian tồn tại | `@RedisHash(timeToLive=...)` hoặc `@TimeToLive` |
| Muốn quan hệ giữa các thực thể lưu độc lập | Cân nhắc `@Reference` và việc quản lý đối tượng được tham chiếu |

Khi chọn Redis làm nơi lưu thực thể, cần xét thêm khả năng khôi phục dữ liệu, độ bền cấu hình Redis, thay đổi schema, yêu cầu truy vấn, tính nhất quán của index và mức độ quan trọng của dữ liệu. Object-to-Hash Mapping giúp ứng dụng dễ đọc/ghi hơn; nó không biến Redis thành cơ sở dữ liệu quan hệ.

## 14. Lỗi thường gặp và cách xử lý

### 14.1. `findById` trả về rỗng dù nhìn thấy key

Kiểm tra key thực tế có đúng dạng `keyspace:id` hay không, Redis database được kết nối, kiểu Redis key (`TYPE` phải là `hash`) và serializer của key. Một chuỗi nhìn giống nhau trong CLI chưa chắc có cùng byte representation với key mà template khác tạo ra.

### 14.2. Không truy vấn được theo email

Kiểm tra thuộc tính có `@Indexed`, dữ liệu đã được lưu thông qua Repository sau khi bật index, và index có được tạo trong Redis hay không. Việc thêm annotation vào code không tự bảo đảm index của mọi bản ghi cũ đã tồn tại.

### 14.3. Đọc đối tượng con bị lỗi sau khi đổi tên field

Ví dụ bản cũ lưu `address.city`, bản mới đổi thành `address.town`. Converter không tự biết hai tên đó tương đương. Cần chuyển đổi dữ liệu cũ, hỗ trợ cách đọc tương thích hoặc có chính sách xóa và tái tạo cache.

### 14.4. Field tự thêm biến mất sau `save`

Nguyên nhân thường là Repository ghi lại toàn bộ nội dung Hash từ các thuộc tính được ánh xạ. Giải pháp là bổ sung field vào mô hình mapping nếu hợp lý, hoặc chuyển dữ liệu do thành phần khác sở hữu sang một key riêng.

### 14.5. Hash đọc được trong CLI nhưng không deserialize được thành Java object

Kiểm tra field `_class`, converter tùy chỉnh, package/class đã được thay đổi, kiểu dữ liệu của field và khả năng tạo đối tượng (constructor, property accessor). Việc dùng khác nhau giữa JDK serialization, JSON serializer và mapping Hash là nguyên nhân phổ biến của sự không tương thích.

### 14.6. TTL hoặc secondary index hoạt động không như mong muốn

Kiểm tra `TTL` của key chính, chỉ mục phụ và cấu hình keyspace notifications. Các key phục vụ chỉ mục và hết hạn có hành vi riêng; không nên giả định sửa trực tiếp một field bằng Redis CLI sẽ kích hoạt toàn bộ quy trình bảo trì chỉ mục của Repository.

## 15. Bài thực hành có hướng dẫn

Xây dựng một tính năng lưu khách hàng với `Customer`, `Address` và `CustomerRepository` ở phần 4.

1. Chạy Redis, khởi động ứng dụng và lưu một khách hàng với ID `c-101`, email `lan@example.com`, địa chỉ `Hà Nội` và hai tag.
2. Dùng `TYPE` và `HGETALL` xác nhận bản ghi là Redis Hash; quan sát các field `address.city`, `tags.[0]` và `_class`.
3. Gọi `findById("c-101")` và `findByEmail("lan@example.com")` để so sánh tìm theo ID và tìm qua secondary index.
4. Thay `address.city` thành `Đà Nẵng` bằng `PartialUpdate`; đọc lại object qua Repository.
5. Dùng Redis CLI thêm field `debugFlag` vào hash; sau đó gọi `repository.save(customer)` để quan sát quy tắc ghi lại toàn bộ.
6. Thử `@TypeAlias("customer")` với dữ liệu thử nghiệm mới và quan sát field `_class`. Lưu ý cách đọc dữ liệu đã tồn tại khi thay cấu hình type metadata.
7. Nếu dùng bản sao Redis riêng cho thực hành, thêm TTL ngắn vào một entity thử nghiệm rồi xem `TTL` giảm theo thời gian.

Câu hỏi tự đánh giá:

- `customers:c-101` và `address.city` khác nhau ở cấp độ nào của Redis?
- Vì sao `@Indexed` không tương đương với ràng buộc unique?
- Trường hợp nào nên dùng `HashOperations` thay cho `CrudRepository`?
- Vì sao thêm field bằng `HSET` rồi gọi `save` có thể làm field đó biến mất?
- Khi nào nên nhúng một đối tượng con, và khi nào nên dùng `@Reference`?
- Một custom converter lưu toàn bộ `Address` trong field `address` ảnh hưởng thế nào đến việc truy cập `address.city`?

## 16. Ghi nhớ

- **Redis key** xác định Hash của thực thể; **hash field** xác định từng thuộc tính bên trong.
- `@RedisHash` xác định keyspace, `@Id` xác định ID, `MappingRedisConverter` ánh xạ hai chiều Java ↔ Redis Hash.
- Thuộc tính phức tạp, collection và map thường được trải thành tên field theo đường dẫn. Metadata `_class` giúp tái dựng kiểu Java.
- `@Indexed` dùng các cấu trúc Redis bổ sung để hỗ trợ tra cứu; việc bảo trì chỉ mục gắn với cơ chế Repository.
- `save` có thể ghi lại toàn bộ Hash; dùng `PartialUpdate` hoặc API Hash trực tiếp khi cần cập nhật chọn lọc, đồng thời xem xét tính nhất quán.
- `HashMapper` và `RedisConverter` phục vụ các cách tích hợp khác nhau. Serializer và định dạng Hash phải nhất quán giữa lúc ghi và lúc đọc.

### Tài liệu tham khảo chính thức

- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Redis Repositories: Usage](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — Hash Mapping / HashMapper](https://docs.spring.io/spring-data/redis/reference/redis/hash-mappers.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)

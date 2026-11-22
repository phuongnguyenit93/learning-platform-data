# MappingRedisConverter và RedisCustomConversions trong Spring Data Redis

Khi sử dụng Spring Data Redis Repository, lập trình viên thao tác với các thực thể Java thay vì tự viết từng lệnh `HSET`, `HGETALL` hay tự chuyển đổi dữ liệu thành byte. Để làm được điều đó, Spring Data Redis cần một cơ chế **ánh xạ đối tượng Java thành Redis Hash** và dựng lại đối tượng từ Hash. `MappingRedisConverter` là thành phần thực hiện công việc này; `RedisCustomConversions` cho phép thay đổi cách chuyển đổi các kiểu dữ liệu cụ thể.

Hai thành phần giải quyết hai câu hỏi khác nhau:

- **`MappingRedisConverter`:** Một entity có các thuộc tính, đối tượng lồng nhau và metadata sẽ được biểu diễn thành những field/value nào trong Redis Hash? Khi đọc Hash, làm sao dựng lại entity?
- **`RedisCustomConversions`:** Nếu quy tắc ánh xạ mặc định không phù hợp cho một kiểu giá trị như `Address`, `Money` hay một đối tượng có định dạng nhị phân riêng, cần đăng ký những bộ chuyển đổi nào để ghi và đọc?

Bài học tập trung vào ngữ cảnh **ánh xạ thực thể (entity mapping)** với Redis Repositories. Đây là cơ chế khác với việc trực tiếp dùng `RedisTemplate.opsForValue()` cùng serializer để lưu cả một đối tượng dưới dạng một giá trị Redis String.

## 1. Redis Hash và cách ánh xạ thực thể mặc định

Redis lưu dữ liệu theo các kiểu cấu trúc như String, Hash, List và Set. Với Redis Repository, một entity thường được lưu thành **một Redis Hash** có tên key ghép từ keyspace và id:

```text
Entity Java
    |
    v
Redis Repository / RedisKeyValueTemplate
    |
    v
MappingRedisConverter
    |
    v
RedisData: metadata + các field/value dạng byte[]
    |
    v
RedisKeyValueAdapter
    |
    v
Redis Hash, ví dụ customer-profiles:42
```

Ví dụ entity dùng trong bài:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customer-profiles")
public class CustomerProfile {

    @Id
    private String id;
    private String displayName;
    private Address address;

    protected CustomerProfile() {
        // Dành cho việc khởi tạo entity khi đọc dữ liệu.
    }

    public CustomerProfile(String id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }
}
```

Đối tượng giá trị lồng bên trong có thể khai báo bằng Java record:

```java
public record Address(String city, String country) {
}
```

Giả sử lưu một hồ sơ:

```java
CustomerProfile customer = new CustomerProfile(
        "42",
        "Minh Anh",
        new Address("Da Nang", "Viet Nam")
);

customerRepository.save(customer);
```

Với quy tắc mặc định, dạng biểu diễn dễ đọc của dữ liệu Redis có thể như sau (giá trị thực tế được gửi dưới dạng byte):

```text
Redis key: customer-profiles:42
Redis type: hash

_class          = com.example.CustomerProfile
id              = 42
displayName     = Minh Anh
address.city    = Da Nang
address.country = Viet Nam
```

`@RedisHash("customer-profiles")` đặt **keyspace**; `@Id` xác định định danh. Khi dùng repository, tên Redis key thường là `<keyspace>:<id>`. Field `_class` chứa thông tin kiểu giúp Spring Data nhận biết loại đối tượng, đặc biệt khi cần ánh xạ các kiểu đa hình. Đây là metadata của cơ chế mapping, không phải field nghiệp vụ.

### Các quy tắc flattening phổ biến

`MappingRedisConverter` biểu diễn cấu trúc lồng nhau bằng đường dẫn thuộc tính (property path). Ví dụ:

| Kiểu thuộc tính Java | Ví dụ | Field trong Redis Hash |
|---|---|---|
| `String` | `name = "Mai"` | `name` |
| `int` | `age = 28` | `age` |
| Đối tượng lồng nhau | `address.city = "Hue"` | `address.city` |
| `List<String>` | `tags = ["vip", "new"]` | `tags.[0]`, `tags.[1]` |
| `Map<String, String>` | `flags["email"] = "ok"` | `flags.[email]` |
| Danh sách đối tượng | `addresses[0].city` | `addresses.[0].city` |

Tên field và cách lưu có thể khác khi đăng ký custom converter. Map key phải có khả năng biểu diễn ổn định dưới dạng tên đường dẫn; các kiểu đơn giản như `String` hoặc số là lựa chọn thông thường. Các trường hợp lồng nhau phức tạp cần cân nhắc vì Redis Hash là cấu trúc phẳng, không phải JSON document.

**Điểm vận hành quan trọng:** khi lưu lại entity bằng Redis Repository, Spring Data Redis có thể xóa nội dung Hash cũ rồi tạo lại từ những thuộc tính đã mapping. Các field bạn ghi thủ công vào cùng Hash nhưng không nằm trong mô hình mapping có nguy cơ bị mất ở lần save tiếp theo. Không nên coi Hash do repository quản lý là kho chứa tự do để nhiều thành phần tùy ý ghi field riêng.

## 2. MappingRedisConverter thực hiện việc gì?

`MappingRedisConverter` nằm trong package:

```text
org.springframework.data.redis.core.convert.MappingRedisConverter
```

Đây là hiện thực mặc định của giao diện `RedisConverter`. Nó sử dụng các thành phần quan trọng sau:

| Thành phần | Vai trò |
|---|---|
| `RedisMappingContext` | Mô tả entity, thuộc tính, id, annotation và thông tin ánh xạ |
| `MappingRedisConverter` | Biến entity thành dạng `RedisData` và chuyển ngược lại |
| `RedisData` | Vật chứa dữ liệu trung gian gồm keyspace/id/field-value và thông tin phụ trợ |
| `ConversionService` | Hạ tầng chuyển đổi các kiểu giá trị đơn giản và converter đã đăng ký |
| `RedisCustomConversions` | Danh sách converter tùy chỉnh và quy tắc lựa chọn chiều đọc/ghi |
| `RedisTypeMapper` | Quản lý thông tin kiểu khi ghi/đọc (ví dụ field `_class`) |
| `RedisKeyValueAdapter` | Làm việc với Redis thông qua lệnh và cấu trúc key/value thực tế |

Luồng ghi:

```text
CustomerProfile
    |
    | 1. Đọc metadata từ RedisMappingContext
    | 2. Xác định id và keyspace
    | 3. Duyệt các thuộc tính
    | 4. Áp dụng custom writing converter nếu có
    v
RedisData (các hash field/value byte[])
    |
    v
RedisKeyValueAdapter --> ghi Hash xuống Redis
```

Luồng đọc:

```text
Redis Hash
    |
    v
RedisKeyValueAdapter --> RedisData
    |
    | 1. Xác định kiểu entity và metadata
    | 2. Đọc thuộc tính/field theo đường dẫn
    | 3. Áp dụng custom reading converter nếu có
    | 4. Khởi tạo entity và gán dữ liệu
    v
CustomerProfile
```

Về mặt API, `MappingRedisConverter` có các phương thức điển hình:

```java
void write(Object source, RedisData sink);
<R> R read(Class<R> type, RedisData source);
void setCustomConversions(CustomConversions conversions);
```

Các chữ ký trên minh họa ý nghĩa của API. Thông thường ứng dụng gọi `CrudRepository.save(...)` và `findById(...)`; hạ tầng repository gọi converter bên dưới. Không cần tự tạo `RedisData` hay gọi `write/read` trong logic nghiệp vụ.

## 3. RedisCustomConversions giải quyết giới hạn nào?

Nếu để mặc định, `Address` là đối tượng phức hợp nên các thuộc tính được tách thành `address.city` và `address.country`. Nhưng có lúc hệ thống muốn lưu nó thành **một field duy nhất**:

```text
Mặc định:
address.city    = Da Nang
address.country = Viet Nam

Với custom converter Address -> byte[]:
address = {"city":"Da Nang","country":"Viet Nam"}
```

Lúc này cần hai hướng chuyển đổi:

- `@WritingConverter` + `Converter<Address, byte[]>`: biến `Address` thành dữ liệu nhị phân để ghi.
- `@ReadingConverter` + `Converter<byte[], Address>`: đọc byte của field và dựng lại `Address`.

Hai chiều cần thống nhất định dạng. Nếu chỉ khai báo chiều ghi, dữ liệu có thể lưu thành công nhưng việc dựng lại kiểu `Address` không thực hiện được theo ý định. Nếu chỉ khai báo chiều đọc, dữ liệu ghi vẫn có thể theo cấu trúc mặc định khác với định dạng mà converter đọc đang mong đợi.

`RedisCustomConversions` thuộc package:

```text
org.springframework.data.redis.core.convert.RedisCustomConversions
```

Đây là đối tượng cấu hình tập hợp converter đăng ký cho cơ chế mapping Redis. Có thể khởi tạo bằng danh sách:

```java
new RedisCustomConversions(List.of(
    new AddressToBytesConverter(mapper),
    new BytesToAddressConverter(mapper)
));
```

Nó không trực tiếp lưu dữ liệu xuống Redis. Khi được nối vào `MappingRedisConverter`, các quy tắc của nó sẽ được xem xét lúc converter xử lý từng thuộc tính.

### Vì sao cần @WritingConverter và @ReadingConverter?

Spring Conversion Service có thể suy luận nhiều kiểu chuyển đổi từ generic `Converter<S, T>`. Tuy nhiên, các kiểu nguồn/đích chung như `String`, `byte[]` hay `Map` có thể dùng ở nhiều hướng và trong nhiều ngữ cảnh. Annotation `@WritingConverter` / `@ReadingConverter` giúp khai báo rõ ý định và tránh đăng ký một chuyển đổi theo chiều không mong muốn.

Chúng đến từ:

```java
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.convert.ReadingConverter;
```

## 4. Ví dụ đầy đủ: lưu Address thành một field JSON nhị phân

Ví dụ dưới đây dùng `Address` và `CustomerProfile` như ở mục đầu. Thêm thư viện Spring Data Redis và Jackson (phiên bản được quản lý theo BOM của Spring Boot):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

### 4.1. Bộ chuyển đổi ghi

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AddressToBytesConverter implements Converter<Address, byte[]> {

    private final ObjectMapper mapper;

    public AddressToBytesConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public byte[] convert(Address source) {
        try {
            return mapper.writeValueAsBytes(source);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot serialize Address", ex);
        }
    }
}
```

Converter này chỉ biết cách đổi một `Address` thành `byte[]`. Nó không biết Redis key sẽ có tên gì và cũng không gọi `HSET`. Việc gắn giá trị vừa tạo vào field `address` là trách nhiệm của cơ chế mapping.

### 4.2. Bộ chuyển đổi đọc

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class BytesToAddressConverter implements Converter<byte[], Address> {

    private final ObjectMapper mapper;

    public BytesToAddressConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Address convert(byte[] source) {
        try {
            return mapper.readValue(source, Address.class);
        } catch (IOException ex) {
            throw new IllegalArgumentException("Cannot deserialize Address", ex);
        }
    }
}
```

Khi Redis trả về các byte từ field `address`, reading converter dùng đúng định dạng JSON mà writing converter tạo ra. Với Java record `Address(String city, String country)`, Jackson trong môi trường phù hợp có thể dựng record qua constructor thành phần. Nếu dùng các loại value object khác, phải bảo đảm cách tạo instance được thư viện chuyển đổi hỗ trợ.

### 4.3. Đăng ký RedisCustomConversions

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@Configuration
public class RedisMappingConfiguration {

    @Bean("redisCustomConversions")
    public RedisCustomConversions redisCustomConversions(ObjectMapper mapper) {
        return new RedisCustomConversions(List.of(
                new AddressToBytesConverter(mapper),
                new BytesToAddressConverter(mapper)
        ));
    }
}
```

Ví dụ giả định ứng dụng đã có một `ObjectMapper` bean (chẳng hạn thông qua cấu hình JSON của Spring Boot). Nếu không có, cần khai báo ObjectMapper tương thích với dữ liệu và phiên bản Jackson đang sử dụng. Không nhất thiết phải tự tạo một `MappingRedisConverter` mới: trong cấu hình Redis Repository tiêu chuẩn, hạ tầng có thể dùng bean `redisCustomConversions` để cấu hình converter của repository.

Đây là cấu hình cho **Redis Repository object-to-hash mapping**. Nó không tự đổi serializer của một `RedisTemplate` được dùng trực tiếp với `opsForValue()`.

### 4.4. Repository và thao tác ghi/đọc

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {
}
```

Ví dụ sử dụng tại một service:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile createExample() {
        CustomerProfile profile = new CustomerProfile(
                "42",
                "Minh Anh",
                new Address("Da Nang", "Viet Nam")
        );
        return repository.save(profile);
    }

    public CustomerProfile find(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Customer profile not found: " + id
                ));
    }
}
```

Sau khi ghi, Redis Hash có dạng minh họa:

```text
Key: customer-profiles:42

_class       = com.example.CustomerProfile
id           = 42
displayName  = Minh Anh
address      = {"city":"Da Nang","country":"Viet Nam"}
```

Không còn hai field `address.city`, `address.country` trong cách biểu diễn mới vì một custom converter đã thay cách ghi kiểu `Address`. Dù ví dụ JSON dễ nhìn bằng Redis CLI, Redis vẫn lưu value của Hash dưới dạng chuỗi byte; một converter khác có thể tạo dữ liệu nhị phân không đọc được như văn bản.

Để quan sát dữ liệu trực tiếp:

```redis
TYPE customer-profiles:42
# hash

HGETALL customer-profiles:42
# Các cặp field/value của entity đã lưu

HGET customer-profiles:42 address
# {"city":"Da Nang","country":"Viet Nam"}
```

Khi gọi `repository.findById("42")`, Redis Repository đọc Hash, converter nhận ra field `address` cần chuyển thành `Address`, rồi dựng lại `CustomerProfile`.

## 5. Converter sang byte[] và converter sang Map<String, byte[]> khác nhau thế nào?

Spring Data Redis hỗ trợ hai hướng cấu hình custom mapping thường gặp:

| Kiểu chuyển đổi | Mức điều khiển | Trường hợp sử dụng |
|---|---|---|
| `Converter<ValueObject, byte[]>` | Lưu một giá trị phức hợp thành byte tại một field trong Hash | JSON của một Address, mã nhị phân của Money, dữ liệu mã hóa |
| `Converter<byte[], ValueObject>` | Khôi phục value object từ field nhị phân | Đọc dữ liệu đã ghi bằng converter tương ứng |
| `Converter<EntityOrValue, Map<String, byte[]>>` | Chủ động tạo bộ field/value cho Hash | Định dạng field đặc thù, schema cũ, quy tắc flatten riêng |
| `Converter<Map<String, byte[]>, EntityOrValue>` | Khôi phục đối tượng từ một map field/value | Đọc định dạng Hash đã tùy chỉnh hoàn toàn |

Ví dụ minh họa cách tự tạo các field cho một `Address`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AddressToMapConverter
        implements Converter<Address, Map<String, byte[]>> {

    @Override
    public Map<String, byte[]> convert(Address source) {
        return Map.of(
                "city_name", source.city().getBytes(StandardCharsets.UTF_8),
                "country_code", source.country().getBytes(StandardCharsets.UTF_8)
        );
    }
}
```

Với Map converter, các tên field do bạn cung cấp là một phần của schema lưu trữ; cần phối hợp nhất quán với converter chiều đọc. Ví dụ trên chỉ minh họa **chiều ghi** nên không thay thế cặp converter đầy đủ ở mục 4. Đặc biệt, custom Map converter có mức can thiệp rộng hơn và có nguy cơ trùng tên field hoặc làm lệch biểu diễn so với mapping mặc định; chỉ nên dùng khi thực sự cần kiểm soát cấu trúc Hash.

**Lưu ý về index:** custom conversion không tự thay đổi cách Spring Data Redis xác định secondary index. Nếu entity có `@Indexed`, index resolver vẫn dựa trên metadata và quy tắc riêng. Không suy ra rằng một Hash field mới do Map converter ghi sẽ tự động trở thành một secondary index có thể truy vấn bằng repository.

## 6. Phân biệt mapping converter, serializer và type mapper

Ba khái niệm này thường bị nhầm vì cùng liên quan đến chuyển đổi dữ liệu:

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| `MappingRedisConverter` | Entity Java ↔ cấu trúc Redis Hash | `CustomerProfile` ↔ field `displayName`, `address`, `_class` |
| `RedisCustomConversions` | Cách mã hóa/giải mã một kiểu giá trị hoặc một cấu trúc Hash | `Address` ↔ JSON `byte[]` |
| `RedisSerializer` | Cách RedisTemplate mã hóa key/value/hash key/hash value ở ranh giới thao tác Redis | `StringRedisSerializer`, `GenericJackson2JsonRedisSerializer` |
| `RedisTypeMapper` | Cách lưu và đọc metadata kiểu Java của entity | `_class` chứa tên lớp hoặc type alias |

Xét hai cách sử dụng:

```java
// Repository: ánh xạ entity thành Redis Hash.
repository.save(profile);

// RedisTemplate: dùng serializer của template cho value.
redisTemplate.opsForValue().set("customer:42", profile);
```

Lời gọi thứ hai chỉ hợp lệ nếu template đã được cấu hình serializer phù hợp với đối tượng. Nó lưu **một value** theo cơ chế của `opsForValue()`; không phải tự động đi qua object-to-hash mapping giống repository. Vì thế, tạo `RedisCustomConversions` sẽ không đột nhiên làm mọi thao tác `RedisTemplate` sử dụng cách ánh xạ mới.

### Type alias cũng khác custom conversion

Mặc định metadata kiểu có thể là tên lớp đầy đủ:

```text
_class = com.example.CustomerProfile
```

Có thể dùng `@TypeAlias` để cung cấp tên ngắn ổn định:

```java
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.redis.core.RedisHash;

@TypeAlias("customer-profile")
@RedisHash("customer-profiles")
public class CustomerProfile {
    // Các field như ví dụ trước
}
```

Khi đó `_class` có thể ghi `customer-profile` thay cho tên Java đầy đủ. Alias là cấu hình **metadata kiểu**, không quyết định `Address` sẽ được flatten hay lưu JSON. Muốn can thiệp sâu hơn vào type metadata, Spring Data Redis hỗ trợ `RedisTypeMapper` (thường thông qua `DefaultRedisTypeMapper`/`TypeInformationMapper` và cấu hình `MappingRedisConverter`).

Khi thay đổi alias hoặc chiến lược type mapping, hãy xét khả năng đọc dữ liệu **đã tồn tại**. Không nên tùy tiện bỏ field metadata hoặc đổi alias nếu ứng dụng từng lưu các subtype cần phân biệt.

## 7. Các lưu ý khi cấu hình trong ứng dụng thực tế

### 7.1. Đăng ký converter đúng hạ tầng

Trong mô hình repository thông thường, bean có tên `redisCustomConversions` được hạ tầng Redis Repository tham chiếu khi tạo `redisConverter`. Nếu bạn tự cấu hình `RedisKeyValueAdapter`, `RedisKeyValueTemplate` hoặc `MappingRedisConverter`, phải chắc chắn chính converter mà adapter sử dụng được thiết lập đúng custom conversions. **Chỉ khai báo class có `@WritingConverter` không đủ để bảo đảm nó được đăng ký vào Redis Repository.**

Ví dụ khi cần tự tạo converter ở cấu hình nâng cao:

```java
MappingRedisConverter converter =
        new MappingRedisConverter(redisMappingContext);
converter.setCustomConversions(redisCustomConversions);
converter.afterPropertiesSet();
```

Đây là minh họa cách thiết lập khi *bạn sở hữu vòng đời đối tượng*. Với ứng dụng dùng Spring container, hãy để bean được khởi tạo và gọi lifecycle tự động. Không nên tùy ý thay toàn bộ converter mặc định chỉ để thêm hai converter cho một value object, bởi các chức năng index, reference và hạ tầng repository có thể cần cấu hình đi kèm.

### 7.2. Định dạng dữ liệu là một hợp đồng lâu dài

Sau khi hệ thống bắt đầu ghi `address` dưới dạng JSON, dữ liệu cũ có thể vẫn dùng `address.city` và `address.country`. Reading converter chỉ biết đọc JSON không thể tự tái dựng những bản ghi cũ bằng định dạng mới. Trước khi thay đổi schema, cần chọn chiến lược:

- Chuyển đổi toàn bộ dữ liệu cũ sang schema mới bằng migration có kiểm soát.
- Hỗ trợ đọc cả schema cũ lẫn mới trong thời gian chuyển tiếp.
- Nếu là cache có TTL ngắn và có thể tái tạo, cho cache cũ hết hạn và làm mới có chủ đích.

Tương tự, nếu thay JSON bằng một định dạng nhị phân khác, nên quy định phiên bản cho payload và cách xử lý các phiên bản cũ. Converter không tự giải quyết vấn đề tương thích dữ liệu.

### 7.3. Chú ý null, lỗi dữ liệu và charset

Converter cần xác định cách xử lý byte rỗng, JSON sai định dạng, dữ liệu null và các thuộc tính không hợp lệ. Với dữ liệu văn bản, sử dụng charset tường minh như `StandardCharsets.UTF_8`. Nếu payload là dữ liệu từ nguồn không tin cậy, tránh cơ chế deserialize cho phép dựng tùy ý lớp Java không được phép. Nên giới hạn kiểu mục tiêu và kiểm tra đầu vào.

Trong ví dụ, lỗi chuyển đổi được ném ra dưới dạng `IllegalArgumentException` kèm nguyên nhân. Ở production, có thể dùng exception phù hợp hơn với tầng domain/serialization, đồng thời ghi log có ngữ cảnh nhưng không làm lộ dữ liệu nhạy cảm.

### 7.4. Đừng bỏ qua metadata và chỉ mục

Converter chỉ xử lý biểu diễn dữ liệu. Những khả năng như `@Id`, `@Indexed`, `@Reference`, `@TimeToLive` vẫn có quy tắc riêng trong Redis mapping và repository:

- `@Id` xác định identity, không phải một JSON field tùy ý.
- `@Indexed` cần metadata/index resolver tương ứng; đổi tên field bằng converter không đồng nghĩa tự đổi chỉ mục.
- `@Reference` có ngữ nghĩa tham chiếu đến đối tượng khác, không chỉ là một POJO lồng nhau.
- `@TimeToLive` liên quan thời hạn sống của key do Redis quản lý; dữ liệu của field TTL không tương đương việc tự serialize thời hạn vào JSON.

Khi custom converter nhắm vào toàn bộ entity hoặc cấu trúc Hash, cần cân nhắc đặc biệt các thông tin mà hạ tầng dựa vào. Với bài toán thông thường, custom converter ở phạm vi một value object là hướng dễ kiểm soát hơn.

## 8. Các lỗi thường gặp và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Lưu được nhưng đọc ra không dựng được `Address` | Chưa đăng ký `Converter<byte[], Address>` hoặc định dạng không khớp | Có cặp đọc/ghi tương thích; kiểm tra bean `redisCustomConversions` |
| Hash vẫn có `address.city`, `address.country` | Writing converter chưa được áp dụng | Kiểm tra converter registration và repository infrastructure |
| `ClassCastException` hoặc lỗi kiểu dữ liệu khi đọc | Byte/Map không đúng kiểu mà reading converter mong đợi | Xác định kiểu nguồn, đích và schema thực tế |
| Một số record cũ không đọc được sau khi thay converter | Schema lưu trữ đã đổi | Migration hoặc cơ chế đọc tương thích |
| Dùng `RedisTemplate.opsForValue()` nhưng custom converter không chạy | Nhầm cơ chế RedisTemplate serializer với Repository mapping | Cấu hình serializer cho template hoặc dùng repository theo đúng ý định |
| `@Indexed` query không ra bản ghi dù field Hash tồn tại | Quy tắc index khác với field do converter tùy chỉnh | Kiểm tra metadata index và chiến lược tạo/rebuild index |
| Lưu entity mất field tự thêm bằng CLI | Repository ghi lại Hash theo thuộc tính đã mapping | Tránh trộn field tự quản với Hash do repository sở hữu |
| Field `_class` thay đổi làm đọc dữ liệu cũ lỗi | Đổi type alias hoặc cấu hình type mapper | Giữ tương thích với metadata kiểu đã lưu |

Để quan sát dữ liệu Redis, có thể kiểm tra những thông tin cơ bản bằng CLI:

```redis
TYPE customer-profiles:42
HKEYS customer-profiles:42
HGETALL customer-profiles:42
TTL customer-profiles:42
```

Hãy so sánh dữ liệu thực tế với contract đọc/ghi do converter định nghĩa. Đừng kết luận converter không chạy chỉ vì nhìn thấy dữ liệu nhị phân không giống văn bản: `byte[]` có thể là JSON, định dạng nén hoặc một codec nhị phân khác.

## 9. Gợi ý thực hành

**Bài thực hành 1 — Quan sát mapping mặc định.** Tạo entity `CustomerProfile` có `Address` nhưng chưa đăng ký custom converter, lưu một bản ghi bằng `CrudRepository` rồi xem `HGETALL`. Ghi nhận những field thuộc dạng `address.*`.

**Bài thực hành 2 — Thay cách biểu diễn Address.** Đăng ký cặp `AddressToBytesConverter` và `BytesToAddressConverter`, ghi một bản ghi mới rồi xem `HGETALL`. Quan sát field `address` chứa JSON. Đọc lại bằng repository và kiểm tra `city`/`country` được khôi phục.

**Bài thực hành 3 — Suy nghĩ về dữ liệu cũ.** Giả sử 100.000 bản ghi đang ở schema `address.city`/`address.country`. Thiết kế lộ trình chuyển đổi để phiên bản mới đọc được dữ liệu trong lúc triển khai nhiều instance và xác định khi nào được phép bỏ hỗ trợ schema cũ.

## 10. Kết luận

`MappingRedisConverter` là thành phần trung tâm chuyển đổi giữa **entity Java** và **Redis Hash** trong Spring Data Redis Repository. Nó dựa vào metadata của `RedisMappingContext`, quy tắc kiểu và converter để đọc/ghi những thuộc tính, kể cả đối tượng lồng nhau.

`RedisCustomConversions` là điểm mở rộng để đăng ký **cách biểu diễn riêng cho một kiểu dữ liệu**: có thể lưu một value object thành `byte[]` hoặc chủ động tạo field/value qua `Map<String, byte[]>`. Cần định nghĩa đủ hai chiều đọc/ghi, gắn converter đúng hạ tầng repository và quản lý khả năng tương thích với dữ liệu đã lưu.

Khi chọn cách cấu hình, luôn phân biệt **object-to-hash mapping của Redis Repository**, **serializer của RedisTemplate** và **type metadata như `_class`**. Chúng có liên hệ nhưng không thay thế lẫn nhau.

## Tài liệu tham khảo

- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): quy tắc flattening, chuyển đổi sang `byte[]` và `Map<String, byte[]>`, type mapping.
- [Spring Data Redis API — MappingRedisConverter](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/convert/MappingRedisConverter.html): API `read`, `write`, `setCustomConversions` và vòng đời converter.
- [Spring Data Redis API — RedisCustomConversions](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/convert/RedisCustomConversions.html): cách khởi tạo và đăng ký custom converter.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): phạm vi hỗ trợ repository, entity và các cơ chế liên quan.

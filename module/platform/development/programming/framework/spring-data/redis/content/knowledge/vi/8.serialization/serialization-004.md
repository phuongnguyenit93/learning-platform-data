# Tuần tự hóa nhị phân Java và rủi ro khi đọc dữ liệu không đáng tin cậy

Trong **Spring Data Redis**, Java object không được gửi nguyên trạng qua mạng. Redis lưu và trả về các dãy byte; phía ứng dụng phải quyết định cách chuyển **object → byte[]** khi ghi và **byte[] → object** khi đọc. Việc lựa chọn serializer ảnh hưởng đến định dạng dữ liệu, khả năng chia sẻ giữa service, tương thích khi cập nhật phiên bản, hiệu năng và đặc biệt là **ranh giới tin cậy khi giải tuần tự hóa**.

Một lựa chọn có sẵn là `JdkSerializationRedisSerializer`, sử dụng cơ chế **Java native serialization** thông qua `ObjectOutputStream` và `ObjectInputStream`. Cơ chế này tiện để lưu object Java, nhưng deserialization một stream không đáng tin cậy có thể kích hoạt hành vi trong các class có trên classpath, không đơn thuần là “đọc vài field”. Vì vậy nó không thích hợp làm định dạng nhập liệu cho dữ liệu do tác nhân không tin cậy kiểm soát.

Bài viết trình bày cách cơ chế đó hoạt động, nó xuất hiện ở đâu trong Spring Data Redis, các rủi ro cần nhận diện và cách chuyển sang cấu trúc dữ liệu an toàn, dễ kiểm soát hơn.

> **Ngữ cảnh kỹ thuật:** Ví dụ sử dụng Java 21, Spring Boot 3.3.x và Spring Data Redis 3.3.x. Chữ “an toàn hơn” trong bài luôn đi kèm điều kiện về nguồn dữ liệu, loại parser, class được phép, kiểm tra đầu vào và cấu hình triển khai. Không có một serializer nào tự bảo đảm mọi dữ liệu đầu vào đều an toàn.

## 1. Redis lưu byte, còn Java thao tác với object

Giả sử ứng dụng có đối tượng:

~~~java
public record ProductCacheValue(
        String id,
        String name,
        long version
) {
}
~~~

Ta muốn lưu nó vào key `catalog:product:42`. Đường đi tổng quát:

~~~mermaid
flowchart LR
    A["ProductCacheValue trong JVM"] --> B["RedisSerializer.serialize()"]
    B --> C["byte[]"]
    C --> D["Redis SET catalog:product:42"]
    D --> E["Redis giữ binary-safe value"]
    E --> F["Redis GET"]
    F --> G["byte[] trả về JVM"]
    G --> H["RedisSerializer.deserialize()"]
    H --> I["ProductCacheValue hoặc lỗi"]
~~~

Redis không tự biết `ProductCacheValue`, không tải Java class và không chạy `readObject()` để lưu value. Các công việc Java serialization/deserialization diễn ra ở **client Java** trước khi gửi hoặc sau khi nhận bytes. Redis hỗ trợ các key/value nhị phân, nên cùng một Redis server có thể chứa giá trị do Java, Python, Node.js hoặc công cụ dòng lệnh ghi.

Điều này tạo ra một yêu cầu quan trọng: **mọi client đọc cùng một key phải hiểu cùng định dạng bytes**. Nếu service A ghi Java serialized object, service B dùng JSON parser để đọc thì chúng không thể trao đổi dữ liệu chỉ vì trỏ đến cùng một địa chỉ Redis.

### 1.1. Hai chiều của serializer

Spring Data Redis sử dụng abstraction `RedisSerializer<T>`, về ý tưởng có hai thao tác:

~~~java
byte[] serialize(T value);
T deserialize(byte[] bytes);
~~~

Khi gọi:

~~~java
redisTemplate.opsForValue().set("catalog:product:42", product);
~~~

template sẽ sử dụng key serializer và value serializer để biến cả key và value thành bytes. Với những kiểu Redis như HASH, còn có hash-key serializer và hash-value serializer.

Khi gọi:

~~~java
ProductCacheValue product =
        redisTemplate.opsForValue().get("catalog:product:42");
~~~

template lấy bytes từ Redis rồi đưa vào value serializer theo chiều `deserialize`. Nếu bytes bị ghi sai định dạng hoặc bị sửa, lỗi xảy ra ở bước này trước khi business logic xử lý object.

### 1.2. “Nhị phân” không đồng nghĩa mã hóa bảo mật

Java binary serialization tạo ra **một định dạng có cấu trúc dành cho JVM**. Nó không tự mã hóa bí mật, không xác minh nguồn gốc bytes và không cung cấp chữ ký chống sửa đổi.

Nếu ứng dụng đưa token, thông tin người dùng hoặc dữ liệu nhạy cảm vào serialized object, việc payload không đọc được bằng mắt qua `redis-cli` **không có nghĩa nội dung đã được bảo mật**. Quyền truy cập Redis, mã hóa đường truyền TLS, quản lý secret và chính sách lưu trữ phải được xử lý độc lập.

## 2. Java native serialization hoạt động thế nào?

Java Serialization API được xây dựng quanh các lớp `java.io.ObjectOutputStream` và `java.io.ObjectInputStream`.

Một lớp Java có thể cho phép cơ chế serialization mặc định bằng cách triển khai marker interface `Serializable`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class LegacyProduct implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String id;
    private final String name;

    public LegacyProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Khi ghi, `ObjectOutputStream` mô tả graph object gồm kiểu, field, reference và thông tin cần để tái tạo theo giao thức serialization của Java.

Ví dụ tạo bytes cục bộ:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.ObjectOutputStream;

LegacyProduct product = new LegacyProduct("42", "Keyboard");

ByteArrayOutputStream output = new ByteArrayOutputStream();

try (ObjectOutputStream stream =
             new ObjectOutputStream(output)) {
    stream.writeObject(product);
}

byte[] serialized = output.toByteArray();
System.out.println("Byte count = " + serialized.length);
~~~

Đây là thao tác **serialization đầu ra** từ object do ứng dụng tạo. Nó không cần đọc bytes không đáng tin cậy.

Trong định dạng Java Object Serialization, phần header của một stream thông thường bắt đầu bằng các byte hex:

~~~text
AC ED 00 05 ...
~~~

Các byte tiếp theo có thể chứa descriptor của class, tên class, `serialVersionUID`, giá trị field và metadata graph. Khi xem bằng công cụ text, một số đoạn có thể in được và nhiều đoạn không đọc được. Header này giúp **nhận diện khả năng** đó là Java serialized stream, nhưng **không chứng minh stream đáng tin cậy hoặc hợp lệ**.

### 2.1. Những thành phần được lưu

| Thành phần | Cách xử lý phổ biến | Ý nghĩa |
|---|---|---|
| Field instance thông thường | Có thể được ghi theo cơ chế serialization của class | Phục hồi trạng thái object |
| Field `static` | Không thuộc trạng thái serialized instance thông thường | Giá trị static thuộc class tại JVM hiện tại |
| Field `transient` | Không được ghi bởi cơ chế serialization mặc định | Dùng khi không muốn field tham gia biểu diễn mặc định |
| `serialVersionUID` | Định danh phiên bản serialization của class | Hỗ trợ kiểm tra tương thích giữa mô tả class và stream |
| Reference trong object graph | Được biểu diễn để hỗ trợ graph và chia sẻ reference | Không chỉ là cấu trúc phẳng kiểu JSON thông thường |
| `readObject` / `readResolve` / `writeObject` | Hook tùy class theo cơ chế Java | Có thể thay đổi cách ghi/khôi phục và thực thi logic |

Nếu object tham chiếu các object khác, các object nằm trong graph được serialize theo quy tắc tương ứng; không phải chỉ field ngoài cùng được ghi. Các lớp triển khai `Externalizable` còn có cơ chế đọc/ghi tùy chỉnh riêng.

### 2.2. Vì sao `readObject()` khác việc parse dữ liệu đơn giản?

Lệnh:

~~~java
Object value = objectInputStream.readObject();
~~~

không chỉ tạo một map chứa key/value. Nó có thể:

1. Đọc mô tả class được ghi trong stream.
2. Tìm class tương ứng trong classpath/class loader.
3. Tái tạo object graph và áp dụng logic deserialization của các class liên quan.
4. Gọi các hook Java serialization trong quá trình khôi phục nếu class định nghĩa chúng.
5. Trả object cuối cùng hoặc ném lỗi khi stream, kiểu và quy tắc không hợp lệ.

Trong các trường hợp nhất định, **hành vi phụ hoặc mã trong hook của class có thể chạy trước khi caller ép kiểu hoặc kiểm tra object trả về**. Đây là nền tảng của rủi ro insecure deserialization.

## 3. `JdkSerializationRedisSerializer` nằm ở đâu trong Spring Data Redis?

### 3.1. Cách serializer này liên kết với RedisTemplate

Spring Data Redis có `org.springframework.data.redis.serializer.JdkSerializationRedisSerializer` để chuyển object Java thành Java serialized stream và ngược lại.

Ví dụ khai báo một template dùng Java serialization **chỉ nhằm minh họa**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class LegacyRedisSerializationConfig {

    @Bean("legacyRedisTemplate")
    RedisTemplate<String, Object> legacyRedisTemplate(
            RedisConnectionFactory factory
    ) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        template.setKeySerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());

        JdkSerializationRedisSerializer jdk =
                new JdkSerializationRedisSerializer();
        template.setValueSerializer(jdk);
        template.setHashValueSerializer(jdk);

        return template;
    }
}
~~~

Trong cấu hình này, key `catalog:product:42` được encode như text UTF-8, nhưng value là Java binary stream. Vì vậy `redis-cli GET catalog:product:42` có thể trả dữ liệu nhìn như ký tự lạ. Redis vẫn lưu nó dưới kiểu Redis `string`; “Java object” là ý nghĩa tại client, không phải một kiểu dữ liệu mới của Redis.

**Không nên sao chép cấu hình trên cho key nhận dữ liệu từ nguồn không đáng tin cậy.** Nó được đưa ra để nhận diện một hệ thống đang dùng định dạng Java serialization.

### 3.2. Các mặc định dễ bị bỏ qua

Khi dùng Spring Data Redis, cần phân biệt:

| Công cụ | Key serializer thông dụng | Value serializer thông dụng |
|---|---|---|
| `RedisTemplate` mặc định chưa tùy biến | Java serialization theo cấu hình mặc định của template | `JdkSerializationRedisSerializer` |
| `StringRedisTemplate` | `StringRedisSerializer` | `StringRedisSerializer` |
| `RedisCacheConfiguration.defaultCacheConfig()` | `StringRedisSerializer` | `JdkSerializationRedisSerializer` |
| `RedisTemplate` tự cấu hình | Do ứng dụng quyết định | Do ứng dụng quyết định |

Với `RedisTemplate`, generic type `RedisTemplate<String, MyDto>` **không tự biến bytes thành JSON**. Generic chỉ giúp Java compiler kiểm tra một phần kiểu của API; cách encode bytes vẫn do serializer thực tế quyết định.

Với Spring Cache, nếu `RedisCacheManager` sử dụng cấu hình mặc định không thay serializer, value của cache Redis có thể đang dùng Java native serialization ngay cả khi business service không gọi trực tiếp `RedisTemplate`.

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public ProductCacheValue find(String id) {
    // Ví dụ phương thức đọc nguồn dữ liệu gốc.
    return repository.findById(id);
}
~~~

Chỉ nhìn thấy `@Cacheable` không đủ để biết bytes trong Redis là gì. Phải xem `CacheManager` nào thực sự được dùng, `RedisCacheConfiguration` được cấu hình ra sao và serializer nào dành cho từng cache.

### 3.3. Nhận diện dữ liệu Java serialized hiện có

Khi đã biết rõ môi trường/key được phép kiểm tra, có thể khảo sát metadata mà không cần deserialize:

~~~bash
redis-cli TYPE catalog:product:42
redis-cli STRLEN catalog:product:42
redis-cli TTL catalog:product:42
~~~

`TYPE` trả `string` cho value dùng Java serialized stream vì Redis không biết lớp Java; `STRLEN` trả kích thước value theo byte. `TTL` giúp hiểu vòng đời khóa.

Trường hợp cần xem bytes, hãy dùng một công cụ phù hợp với dữ liệu nhị phân trong môi trường thử nghiệm, tránh log thẳng toàn bộ serialized payload hoặc gửi payload sang dịch vụ không cần thiết. Việc thấy header `AC ED 00 05` là dấu hiệu của định dạng, **không phải lời mời đọc object đó bằng `ObjectInputStream`**.

## 4. Dữ liệu nào được xem là không đáng tin cậy?

Có một hiểu lầm phổ biến: “Redis nằm trong mạng nội bộ nên mọi bytes trong Redis đều đáng tin.” Trên thực tế, **ranh giới tin cậy nằm ở quyền kiểm soát quá trình ghi dữ liệu**, không chỉ ở vị trí máy chủ.

Các nguồn dữ liệu cần đánh giá gồm:

- Một REST/API endpoint nhận giá trị do người dùng cung cấp rồi ghi vào Redis.
- Job import, message consumer hoặc dịch vụ bên thứ ba đưa bytes vào Redis.
- Redis dùng chung bởi nhiều application/team với quyền ghi chưa được tách biệt.
- Key do phiên bản ứng dụng cũ hoặc một service khác ghi bằng serializer khác.
- Cache được khôi phục từ backup hoặc sao chép từ môi trường chưa xác minh.
- Redis account, mạng hoặc công cụ quản trị bị lộ quyền ghi.
- Trường hợp ứng dụng được phép chọn key tùy ý và đọc nhầm key của một nguồn khác.

Không phải mỗi trường hợp đều là tấn công. Một service sai serializer có thể tạo **dữ liệu không tương thích** dù không độc hại. Tuy nhiên, nếu một tác nhân kiểm soát được serialized byte stream được ứng dụng đọc bằng `JdkSerializationRedisSerializer`, đó có thể là một điểm vào cần xử lý như **insecure deserialization**.

### 4.1. Đường đi của rủi ro

~~~mermaid
flowchart TD
    A["Nguồn có thể ghi bytes vào Redis"] --> B["Key được ứng dụng tin là cache object"]
    B --> C["String/RedisTemplate hoặc Redis Cache đọc bytes"]
    C --> D["JdkSerializationRedisSerializer.deserialize()"]
    D --> E["ObjectInputStream khôi phục object graph"]
    E --> F["Hook và hành vi của class trên classpath"]
    F --> G["Tác động phụ / lỗi / quá tải tùy nội dung và class"]
    G --> H["Business code mới nhận object hoặc exception"]
~~~

Điểm quan trọng: việc ép kiểu như `(Product) value` hoặc kiểm tra `instanceof Product` sau khi deserialize không phải chốt chặn đủ sớm. Nếu object graph không an toàn đã được xử lý trong `readObject()`, lỗi `ClassCastException` sau đó không xóa được tác động đã xảy ra.

### 4.2. Những hậu quả có thể xảy ra

| Rủi ro | Cơ chế ở mức khái niệm | Điều kiện cần lưu ý |
|---|---|---|
| **Thực thi hành vi ngoài ý muốn** | Class có hook hoặc chuỗi gọi phương thức trong quá trình deserialize | Phụ thuộc class/gadget khả dụng trên classpath và khả năng tác nhân kiểm soát bytes |
| **Remote Code Execution (RCE)** trong trường hợp nghiêm trọng | Chuỗi gadget nguy hiểm bị kích hoạt khi tái tạo graph | Không phải mọi stream Java đều gây RCE; cần đường khai thác phù hợp |
| **Denial of Service (DoS)** | Graph lớn/sâu, nhiều phần tử/reference hoặc dữ liệu gây xử lý tốn CPU/RAM | Có thể xảy ra ngay cả khi không có gadget RCE |
| **Hành vi bất thường của ứng dụng** | Class không còn tồn tại, mô tả stream không tương thích, object nhận sai kiểu | Có thể là sự cố vận hành, không cần tác nhân cố ý tấn công |
| **Sai lệch dữ liệu nghiệp vụ** | Đọc nhầm key/serializer hoặc diễn giải object từ version cũ | Gây cache miss, exception hoặc kết quả sai nếu ứng dụng xử lý không chặt |

Java Serialization không mặc nhiên “chạy bất kỳ class nào người gửi muốn”: class phải phù hợp và khả dụng ở phía ứng dụng, còn nhiều giới hạn môi trường khác cũng quyết định hậu quả. Tuy nhiên, **chỉ cần classpath thay đổi hoặc thêm dependency có gadget phù hợp, bề mặt tấn công có thể thay đổi** mà không cần sửa dòng code đọc Redis.

### 4.3. Vì sao chuỗi gadget đáng lo?

Trong Java, nhiều thư viện có các phương thức xử lý lifecycle, comparator, collection, proxy hoặc custom serialization. Một số loại object có thể kích hoạt các phương thức khác nhau trong quá trình deserialize. Nếu các hành vi này liên kết thành một chuỗi có tác động không mong muốn, người tấn công có thể lợi dụng nó.

Để hiểu bài học, không cần dựng payload hay liệt kê chuỗi gadget cụ thể. Quy tắc đủ quan trọng là: **không bao giờ coi một byte stream được bên không tin cậy kiểm soát là Java object hợp lệ chỉ vì nó có thể được đưa vào `ObjectInputStream`**.

## 5. Rủi ro tính tương thích khi nâng phiên bản

Ngay cả khi Redis chỉ nhận dữ liệu từ ứng dụng của chính bạn, Java binary serialization vẫn khiến dữ liệu phụ thuộc đáng kể vào cấu trúc class trong JVM.

### 5.1. `serialVersionUID` giúp kiểm tra phiên bản, không phải schema migration

Với một class `Serializable`, `serialVersionUID` được dùng để so khớp phiên bản mô tả serialized class khi deserialize. Nếu class phía đọc có serialVersionUID không tương thích với stream, có thể xuất hiện `InvalidClassException`.

Ví dụ:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class CachedAccount implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private String id;
    private String tier;
}
~~~

Một lần deploy sau, code đổi cấu trúc class, tên package hoặc ý nghĩa field. Giữ nguyên `serialVersionUID = 1L` **không tự biến đổi dữ liệu cũ thành schema mới đúng nghiệp vụ**.

Đặc biệt:

- Thêm/bỏ field có một số quy tắc tương thích của Java Serialization, nhưng business code có thể không chấp nhận các default value sau deserialize.
- Đổi tên package/class có thể khiến JVM không tìm thấy class cũ.
- Một field đổi kiểu hoặc lớp liên quan không serializable có thể làm quá trình đọc/ghi lỗi.
- Một version mới có thể thêm dependency/hook làm rủi ro deserialization khác đi.
- Khi nhiều service dùng version class khác nhau, cùng một payload có thể deserialize được ở service này nhưng thất bại ở service kia.

**Không nên dùng việc giữ nguyên serialVersionUID làm chiến lược migration dữ liệu duy nhất.**

### 5.2. Các lỗi thường gặp khi đọc cache cũ

| Lỗi Java/Spring có thể gặp | Giải thích điển hình | Hành động điều tra |
|---|---|---|
| `InvalidClassException` | Class stream và class hiện tại không tương thích theo quy tắc serialization | So sánh version, UID, thay đổi cấu trúc class |
| `ClassNotFoundException` | Client không có class được mô tả trong stream | Xem package/class đã đổi, dependency/classloader |
| `StreamCorruptedException` | Bytes không phù hợp định dạng stream mong đợi | Xem serializer của bên ghi, key collision, dữ liệu hỏng |
| `ClassCastException` | Object sau khi đọc không đúng kiểu caller chờ | Kiểm tra key schema/serializer và đổi định dạng |
| Spring `SerializationException` | Lớp adapter bọc lỗi serialize/deserialize bên dưới | Đọc cause gốc, đừng chỉ retry cùng payload vô hạn |
| Lỗi bộ nhớ/độ trễ tăng | Payload quá lớn, graph phức tạp hoặc logic deserialize tốn tài nguyên | Xem giới hạn kích thước, key ownership, nguồn dữ liệu |

Một fallback “cứ đọc JDK serialization nếu JSON thất bại” có thể vô tình **mở lại bề mặt tấn công cũ**. Nếu dữ liệu là cache có thể tạo lại, cách phục hồi thường dễ kiểm soát hơn là xóa hoặc đổi namespace của cache cũ và ghi lại bằng format mới.

### 5.3. Không phù hợp khi chia sẻ giữa ngôn ngữ khác nhau

Java Serialization là định dạng đặc thù Java. Một service Go hoặc Python không thể mặc nhiên đọc trực tiếp object từ `JdkSerializationRedisSerializer` như một JSON object thông thường.

Nếu Redis là lớp trao đổi giữa nhiều service hoặc nhiều ngôn ngữ, nên chọn một schema được thống nhất, ví dụ JSON DTO với field cụ thể, Protocol Buffers hoặc một định dạng binary có schema và parser phù hợp. Khi đó **versioning của schema** phải được quản lý độc lập với tên Java class và version JVM.

## 6. Phương án đơn giản nhất: chỉ lưu String khi đủ dùng

Không phải dữ liệu nào trong Redis cũng cần nguyên object graph. Với token, counter, flag, ID hoặc một số trạng thái nhỏ, `StringRedisTemplate` thường đủ và dễ kiểm soát.

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class FeatureFlagStore {

    private final StringRedisTemplate redis;

    public FeatureFlagStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String flagId, boolean enabled) {
        redis.opsForValue().set(
                "feature:v1:" + flagId,
                Boolean.toString(enabled),
                Duration.ofMinutes(10)
        );
    }

    public boolean isEnabled(String flagId) {
        String raw = redis.opsForValue().get(
                "feature:v1:" + flagId
        );
        return "true".equalsIgnoreCase(raw);
    }
}
~~~

Ở đây, value được xử lý như chuỗi và không gọi Java Object Serialization. Điều đó loại bỏ **con đường JDK deserialization cụ thể**, nhưng vẫn cần kiểm soát input (ví dụ ID, độ dài chuỗi, format và quyền ghi key). Ví dụ đơn giản này coi giá trị không có hoặc sai định dạng là false; với nghiệp vụ quan trọng, cần xác định rõ hành vi lỗi thay vì mặc định false.

Với số đếm, có thể dùng `opsForValue().increment(key)` trên giá trị số theo quy ước chuỗi phù hợp. Đừng serialize cả một object chỉ để đọc một số nguyên.

## 7. Lưu object dưới JSON với DTO có kiểu cố định

Khi cần lưu object, một cách thường dễ vận hành hơn là dùng **DTO có schema rõ** và JSON serializer được cấu hình theo kiểu đích.

### 7.1. DTO cho cache

~~~java
public record ProductCacheValue(
        String id,
        String name,
        long version
) {
}
~~~

DTO trên chỉ có những field cần thiết cho cache. Nó không chứa entity JPA đang gắn session, object proxy, connection, Java exception hay các reference phức tạp không liên quan.

Ví dụ JSON mong đợi:

~~~json
{
  "id": "42",
  "name": "Keyboard",
  "version": 3
}
~~~

JSON giúp dễ quan sát, nhưng **JSON không tự động an toàn**. Điều quyết định là parser chỉ tạo kiểu được cho phép, giới hạn kích thước/độ sâu hợp lý và không xử lý type metadata không đáng tin cậy theo kiểu mở.

### 7.2. Tạo một template typed JSON

Ví dụ cho Spring Boot 3.3.x / Spring Data Redis 3.3.x:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean("productRedisTemplate")
    RedisTemplate<String, ProductCacheValue> productRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        RedisTemplate<String, ProductCacheValue> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);

        StringRedisSerializer text = new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductCacheValue> json =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        ProductCacheValue.class
                );

        template.setKeySerializer(text);
        template.setHashKeySerializer(text);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        return template;
    }
}
~~~

Bean được đặt tên `productRedisTemplate` để chỉ rõ mục đích. Nó sử dụng serializer JSON theo **kiểu cụ thể `ProductCacheValue`**. Những thao tác dùng template này phải phù hợp kiểu DTO đó; không dùng chung template typed cho mọi loại object không liên quan.

Spring Boot thường cung cấp `ObjectMapper` khi ứng dụng có Jackson và cấu hình Jackson phù hợp. Code dựa trên ObjectMapper đã cấu hình của ứng dụng; nếu hệ thống bật Jackson polymorphic default typing rộng hoặc dùng custom deserializer nguy hiểm, phải đánh giá và sửa cấu hình đó. **Chỉ thay `JdkSerializationRedisSerializer` bằng một JSON serializer tự động dựng class tùy ý chưa chắc là phương án an toàn.**

### 7.3. Service dùng template rõ ràng

~~~java
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheStore {

    private final RedisTemplate<String, ProductCacheValue> redis;

    public ProductCacheStore(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductCacheValue> redis
    ) {
        this.redis = redis;
    }

    public void put(ProductCacheValue product) {
        redis.opsForValue().set(
                "catalog:product:v2:" + product.id(),
                product,
                Duration.ofMinutes(20)
        );
    }

    public Optional<ProductCacheValue> find(String id) {
        ProductCacheValue value = redis.opsForValue().get(
                "catalog:product:v2:" + id
        );
        return Optional.ofNullable(value);
    }

    public void evict(String id) {
        redis.delete("catalog:product:v2:" + id);
    }
}
~~~

Sử dụng prefix `v2` là một cách tránh việc code JSON mới cố đọc bytes Java serialization tại key cũ `catalog:product:42`. Khi TTL của key cũ hết hoặc hệ thống thực hiện dọn dẹp có kiểm soát, dữ liệu cũ có thể biến mất mà không cần đưa stream cũ qua đường deserialize mới.

Điều vẫn cần làm ở lớp ứng dụng: validate `id`, độ dài và nội dung DTO, quyền truy cập, TTL và cách xử lý cache miss. Nếu payload lấy từ Redis không đúng JSON/type mong đợi, serializer nên báo lỗi thay vì thử deserialize tiếp bằng JDK một cách ngầm định.

### 7.4. Chọn JSON serializer có kiểu đích thay vì polymorphic tùy ý

Với Spring Data Redis, các lựa chọn thường gặp là:

| Serializer | Ý tưởng | Điều cần cẩn trọng |
|---|---|---|
| `StringRedisSerializer` | String ↔ UTF-8 bytes | Chỉ thích hợp cho dữ liệu có dạng text rõ |
| `Jackson2JsonRedisSerializer<T>` | JSON cho một kiểu Java xác định | Kiểm tra ObjectMapper, custom deserializer, kiểu đích và giới hạn đầu vào |
| `GenericJackson2JsonRedisSerializer` | JSON cho nhiều loại object với cơ chế type information | Cần đặc biệt xem xét type metadata/default typing khi đọc dữ liệu không tin cậy |
| `JdkSerializationRedisSerializer` | Java native binary object graph | Không deserialize dữ liệu không đáng tin cậy |
| `RedisSerializer.byteArray()` / raw bytes | Giữ bytes như dữ liệu thô | Caller phải tự định nghĩa và kiểm tra schema khi giải mã |

Không nên kết luận rằng một serializer có tên “JSON” đồng nghĩa **không có bất kỳ rủi ro deserialization nào**. Ví dụ, Jackson có các cơ chế polymorphic type handling; khi cho phép loại class được quyết định từ metadata của payload mà không giới hạn đủ chặt, lại xuất hiện bề mặt rủi ro khác. Khi bạn kiểm soát được schema, **DTO cụ thể với các field cho phép** thường dễ đánh giá hơn cấu hình mở cho “bất kỳ Object nào”.

## 8. Spring Cache phải được xem xét riêng

Một ứng dụng có thể không dùng `RedisTemplate` trực tiếp nhưng vẫn dùng Redis thông qua Spring Cache:

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public ProductCacheValue findById(String id) {
    return loadProductFromDatabase(id);
}
~~~

Khi sử dụng `RedisCacheManager` với default `RedisCacheConfiguration`, value serializer mặc định sử dụng Java serialization. Vì vậy việc chuyển một service thủ công sang typed JSON template **không tự đổi serializer của `@Cacheable`**.

Ví dụ cấu hình **một cache chỉ chứa `ProductCacheValue`** với JSON typed:

~~~java
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration(proxyBeanMethods = false)
public class RedisCacheSerializationConfig {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper
    ) {
        Jackson2JsonRedisSerializer<ProductCacheValue> serializer =
                new Jackson2JsonRedisSerializer<>(
                        objectMapper,
                        ProductCacheValue.class
                );

        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(20))
                        .serializeValuesWith(
                                RedisSerializationContext
                                        .SerializationPair
                                        .fromSerializer(serializer)
                        );

        return RedisCacheManager.builder(connectionFactory)
                .withInitialCacheConfigurations(
                        Map.of("productById", productCache)
                )
                .disableCreateOnMissingCache()
                .build();
    }
}
~~~

Trong ví dụ, cache tên `productById` được cấu hình theo DTO cụ thể. `disableCreateOnMissingCache()` giúp tránh việc một tên cache không được khai báo tự động sinh ra với **default value serializer** khác với cache đã định nghĩa.

Đây là cấu hình mẫu cho trường hợp chỉ có một cache typed. Nếu ứng dụng có nhiều cache chứa các kiểu DTO khác nhau, cần khai báo serializer phù hợp cho từng cache và kiểm soát việc cache nào được tạo. Không dùng serializer của `ProductCacheValue` để deserialize kết quả `List<Product>`, `Customer` hoặc đối tượng khác mà không có schema phù hợp.

Khi đổi định dạng cache, hãy đánh giá luôn **key prefix** và dữ liệu đang còn trong Redis. Chuyển từ JDK binary sang JSON nhưng giữ nguyên keyspace cũ có thể khiến lần đọc đầu tiên của ứng dụng mới ném lỗi vì gặp bytes không đúng format.

## 9. Nếu bắt buộc duy trì JDK serialization trong hệ thống cũ

Đôi khi một hệ thống cũ còn dùng Java serialization và chưa thể chuyển ngay. Trong trường hợp đó, ưu tiên **không nhận bytes từ nguồn không đáng tin cậy**, thu hẹp những key có thể được đọc, tách biệt quyền ghi và lập kế hoạch loại bỏ định dạng cũ. Các bộ lọc deserialization chỉ là lớp bảo vệ bổ sung.

### 9.1. Java ObjectInputFilter: giới hạn class và tài nguyên

Java hỗ trợ cơ chế serialization filtering qua `java.io.ObjectInputFilter`, được giới thiệu trong JEP 290 và bổ sung cơ chế filter factory/context-specific ở JEP 415.

Filter có thể quyết định chấp nhận, từ chối hoặc chưa xác định đối với class/array và một số giới hạn của object graph, ví dụ:

- Độ sâu graph (`maxdepth`).
- Số reference (`maxrefs`).
- Dung lượng stream theo byte (`maxbytes`).
- Kích thước array (`maxarray`).
- Những class/package/module được phép hoặc bị cấm theo pattern.

Một **mẫu minh họa** cho tiến trình JVM cần đọc dữ liệu cũ:

~~~text
-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.cache.dto.*;java.base/java.lang.*;java.base/java.util.*;!*
~~~

Đây **không phải cấu hình có thể áp dụng nguyên xi cho mọi ứng dụng**:

- `com.example.cache.dto.*` chỉ là tên package ví dụ; cần xác định các class thực sự được phép.
- Các package Java cơ sở có thể rộng hơn nhu cầu và vẫn chứa nhiều class; cần thu hẹp khi khả thi.
- Cú pháp pattern, thứ tự các pattern, array/class graph và các giới hạn phải được hiểu đúng theo JDK đang dùng.
- Filter JVM toàn cục có thể ảnh hưởng các cơ chế deserialize Java khác trong cùng process, không chỉ Redis.
- Filter cần được cấu hình **trước khi** dữ liệu bị deserialize; không thể kiểm tra object sau khi đã tạo để thay thế việc lọc đầu vào.
- Một filter có thể giảm rủi ro nhưng không bảo đảm an toàn trước mọi hành vi của class đã được cho phép.

Nếu đưa option `-D...` vào câu lệnh shell, dấu `;` phải được quote/escape đúng với shell đang sử dụng; các dấu đó là phần của **giá trị property**, không phải các câu lệnh độc lập.

`ObjectInputFilter` giúp kiểm soát những loại object được khôi phục và một số mức sử dụng tài nguyên. Nó **không thay thế việc xác thực nguồn dữ liệu, loại bỏ gadget nguy hiểm hoặc chuyển sang định dạng với schema rõ**. Một số hành vi lọc cũng phụ thuộc JDK, filter factory và cách tạo `ObjectInputStream`, nên phải quan sát kết quả thực tế khi vận hành.

### 9.2. Không dựa vào ép kiểu sau deserialization

Mẫu suy luận sau không đủ an toàn:

~~~java
Object deserialized = /* ObjectInputStream.readObject() */;
if (!(deserialized instanceof LegacyProduct)) {
    throw new IllegalArgumentException("Wrong type");
}
~~~

Kiểm tra `instanceof` chỉ diễn ra **sau** quá trình đọc object graph. Nếu bytes có thể được kiểm soát bởi tác nhân không tin cậy, việc kiểm tra kiểu lúc này không chặn được những hành vi đã xảy ra trong deserialization.

Phòng vệ cần nằm **trước hoặc bên trong** quá trình đọc: chặn nguồn ghi không tin cậy, không dùng Java deserialization cho dữ liệu của họ, và dùng filter/giới hạn khi chưa thể loại bỏ định dạng cũ.

### 9.3. Giới hạn Redis ACL và đường ghi

Dữ liệu cache vẫn có thể trở thành nguồn đầu vào nguy hiểm nếu một service khác được quyền ghi vào cùng keyspace.

Nên xác định:

1. Service nào được quyền **ghi** và **đọc** nhóm key dùng Java serialization.
2. Redis account/ACL và key pattern nào được phép truy cập.
3. Redis có nằm trong mạng riêng, dùng TLS và quản lý credential phù hợp hay không.
4. Có service/worker/debug tool nào có khả năng sửa trực tiếp bytes tại các key đó.
5. Khi lỗi deserialize xảy ra, ứng dụng sẽ loại bỏ key, báo lỗi hay fallback theo quy tắc nào mà không deserialize lại vô hạn.

Redis ACL có thể hạn chế command/key mà một tài khoản truy cập, nhưng không tự kiểm tra rằng bytes được ghi là một serialized DTO hợp lệ, cũng không biến Redis thành nguồn dữ liệu có độ tin cậy tuyệt đối.

### 9.4. Giới hạn tài nguyên khi đọc cache

Ngoài class filter, còn cần suy nghĩ về:

- Kích thước tối đa của value mà ứng dụng chấp nhận và số lượng key được đọc mỗi request.
- Timeout của Redis command và ngân sách latency của request.
- Khả năng nhiều request cùng đọc payload lớn khiến JVM tăng heap/GC.
- Cách xử lý lỗi đối với một key bị hỏng mà không tạo vòng lặp retry liên tục.
- Monitoring số lỗi serializer/deserializer, kích thước payload, tần suất cache miss và các dấu hiệu bất thường.

TTL không tự giải quyết một payload nguy hiểm trong lúc key còn tồn tại; eviction cũng không phải biện pháp bảo mật.

## 10. Migration từ Java serialization sang định dạng mới

Một thay đổi serializer không giống việc đổi cách hiển thị dữ liệu. Nó là **thay đổi giao thức dữ liệu lưu trong Redis**. Nếu ứng dụng cũ ghi bytes JDK và phiên bản mới cố parse JSON trên cùng key, việc đọc có thể thất bại ngay.

Một phương án migration với dữ liệu cache có thể tạo lại:

~~~text
Trước:
  catalog:product:42  → bytes Java serialization (legacy)

Sau:
  catalog:product:v2:42 → JSON DTO typed (new)
~~~

Luồng chuyển đổi:

1. Chọn schema mới và version keyspace, ví dụ `catalog:product:v2:<id>`.
2. Phiên bản ứng dụng mới chỉ ghi/đọc key `v2` bằng serializer mới.
3. Khi cache miss ở `v2`, đọc lại từ **nguồn dữ liệu chuẩn** (database/API đáng tin) rồi populate cache mới.
4. Để các key cũ tự hết TTL, hoặc dọn theo quy trình được phép và có kiểm soát.
5. Khi mọi consumer đã chuyển, loại bỏ code và dependency còn dùng JDK serialization nếu không còn nhu cầu.

Cách này tránh phải deserialize dữ liệu cũ chỉ để chuyển định dạng. Nó cũng tách hai định dạng nên không lẫn bytes cũ và mới dưới cùng tên key.

Với dữ liệu mà Redis là **nơi duy nhất đang giữ** và không thể tái tạo từ nguồn chuẩn, cần một migration được kiểm soát khác: kiểm tra nguồn gốc payload, cô lập môi trường đọc legacy, giới hạn class/tài nguyên, ghi kết quả theo schema mới, đối soát số lượng/hash và chuẩn bị phương án phục hồi. Không nên để hệ thống production tự “thử JDK rồi thử JSON” trên mọi request trong thời gian vô hạn.

### 10.1. Chiến lược versioning

Khi thiết kế serializer mới, có thể kết hợp:

- **Key version:** `product:v2:42`.
- **Schema version trong payload:** `"schemaVersion": 2` nếu cần quản lý biến thể cấu trúc.
- **DTO rõ ràng:** field có kiểu, nullable và default được mô tả rõ.
- **TTL:** cache cũ được loại bỏ trong một khoảng thời gian hợp lý nếu nghiệp vụ cho phép.
- **Source of truth:** có đường tái tạo giá trị khi cache miss hoặc khi payload sai định dạng.

Đừng phụ thuộc vào tên Java class như một định danh giao thức trao đổi dữ liệu giữa nhiều service. Nếu class Java đổi tên nhưng schema JSON không đổi, consumer phù hợp vẫn có thể đọc được.

## 11. Phân biệt lỗi dữ liệu không tương thích với dấu hiệu an ninh

Khi `GET` từ Redis thất bại ở bước deserialize, nguyên nhân có thể là:

~~~mermaid
flowchart TD
    A["Đọc Redis trả byte[]"] --> B{"Đúng serializer của key?"}
    B -->|Không| C["Sai định dạng / phiên bản / key collision"]
    B -->|Có| D{"Payload hợp lệ với schema?"}
    D -->|Không| E["Dữ liệu hỏng, thiếu class, field/type sai"]
    D -->|Có| F{"Nguồn bytes đáng tin?"}
    F -->|Không hoặc chưa rõ| G["Không deserialize kiểu Java tùy ý; xử lý theo ranh giới tin cậy"]
    F -->|Có| H["Tiếp tục validate logic và resource limits"]
~~~

Một lỗi `StreamCorruptedException` không tự chứng minh bị tấn công; nó có thể đến từ việc service khác ghi JSON vào một key mà code lại đọc bằng JDK serializer. Ngược lại, **deserialization thành công không chứng minh bytes an toàn**. Việc điều tra cần kết hợp lịch sử deploy, producer/consumer, quyền ghi Redis, key prefix và log stack trace.

Khi log lỗi:

- Ghi **tên key đã được che thông tin nhạy cảm** hoặc nhóm key pattern thay vì in giá trị thật.
- Ghi loại serializer, version schema, ứng dụng producer nếu biết, kích thước payload và exception class.
- Không log toàn bộ serialized bytes, credential hay object chứa dữ liệu cá nhân.
- Tránh retry vô hạn cùng một value bị hỏng.
- Xác định có nên coi lỗi cache là cache miss và tái tạo từ nguồn dữ liệu chuẩn hay phải trả lỗi có kiểm soát; điều đó phụ thuộc tính chất dữ liệu.

## 12. Bảng quyết định serializer theo trường hợp sử dụng

| Dữ liệu trong Redis | Hướng lựa chọn | Lý do |
|---|---|---|
| Counter, flag, token định dạng đơn giản | `StringRedisTemplate` / String serializer | Đơn giản, không cần object graph Java |
| Cache một DTO xác định, đọc lại từ database | Typed JSON serializer với DTO cố định | Dễ quan sát, versioning và hạn chế phụ thuộc Java class |
| Dữ liệu trao đổi giữa Java, Go, Node.js | JSON/Protobuf hoặc format có schema thỏa thuận | Tương thích liên ngôn ngữ |
| Dữ liệu do bên ngoài/không tin cậy ghi | Parser theo schema, validate và giới hạn đầu vào | Không cho bytes tự quyết định Java class cần khởi tạo |
| Cache Spring `@Cacheable` | Cấu hình `RedisCacheManager` và serializer theo từng cache | Tránh vô tình dùng value serializer JDK mặc định |
| Dữ liệu Java serialization tồn tại từ hệ thống cũ | Cô lập và lập kế hoạch loại bỏ, filter như lớp phụ | Giảm bề mặt rủi ro trong giai đoạn chuyển đổi |
| Dữ liệu nghiệp vụ quan trọng, không thể mất | CSDL/thiết kế persistence phù hợp; Redis theo vai trò được xác định | Serializer không tự bảo đảm durability hoặc transaction |

Không nên chọn serializer chỉ theo độ ngắn của đoạn cấu hình. Dạng bytes đó có thể tồn tại lâu hơn vòng đời một phiên bản application và trở thành hợp đồng trao đổi dữ liệu giữa các service.

## 13. Các sai lầm dễ gặp

**Sai lầm 1: “Redis ở private subnet nên JDK deserialization an toàn.”**

Một service khác được phép ghi, một job import hoặc credential bị lộ vẫn có thể đưa bytes vào Redis. Ranh giới tin cậy phải được xem xét theo đường **ghi → lưu → đọc**, không chỉ theo địa chỉ mạng.

**Sai lầm 2: “Ép kiểu về DTO ngay sau khi `get()` là đủ.”**

Nếu serializer đã gọi `ObjectInputStream.readObject()`, việc tạo object graph diễn ra trước khi ép kiểu. Kiểm tra business type sau đó không thay thế việc kiểm soát deserialization.

**Sai lầm 3: “Đã dùng `RedisTemplate<String, Product>` thì chắc chắn lưu JSON.”**

Generic type không quyết định serializer. Có thể template vẫn dùng `JdkSerializationRedisSerializer` cho key/value nếu không cấu hình rõ.

**Sai lầm 4: “Dữ liệu binary không đọc được là dữ liệu đã mã hóa.”**

Java serialization không cung cấp confidentiality hoặc integrity. Cần TLS, kiểm soát truy cập, secret và các cơ chế bảo vệ phù hợp yêu cầu.

**Sai lầm 5: “Đặt `serialVersionUID` cố định thì version nào cũng đọc được.”**

UID chỉ là một phần quy tắc tương thích. Tên class, field, kiểu dữ liệu và logic khôi phục có thể vẫn thay đổi theo cách không còn hợp lệ.

**Sai lầm 6: “Đổi serializer của một RedisTemplate là đã chuyển toàn hệ thống.”**

`StringRedisTemplate`, RedisTemplate khác, Redis Repositories và Spring Cache có thể sử dụng các serializer/configuration khác nhau. Cần xác định đường đọc/ghi thực tế của mỗi keyspace.

**Sai lầm 7: “JSON luôn an toàn bất kể cấu hình.”**

JSON với polymorphic type metadata không giới hạn hoặc custom deserializer nguy hiểm vẫn có rủi ro. Ưu tiên DTO cố định, schema rõ, validate và parser được cấu hình có kiểm soát.

**Sai lầm 8: “Thử JSON, lỗi thì tự động fallback về Java deserialization.”**

Nếu dữ liệu đến từ nguồn không tin cậy, fallback đó duy trì đường vào nguy hiểm. Tốt hơn là xác định version keyspace và migration tường minh.

## 14. Nguyên tắc thiết kế cần mang theo

1. **Biết serializer thật đang chạy.** Xem cấu hình của `RedisTemplate`, `StringRedisTemplate` và `RedisCacheManager`, không suy đoán từ annotation hoặc generic type.
2. **Không gọi Java native deserialization trên bytes có thể bị tác nhân không tin cậy kiểm soát.** Đây là biện pháp quan trọng nhất để tránh lớp rủi ro insecure deserialization của Java.
3. **Chọn định dạng theo hợp đồng dữ liệu.** Với cache đơn giản, string hoặc typed DTO JSON thường dễ quản lý hơn object graph Java.
4. **Không mở type resolution tùy ý.** Nếu dùng JSON, kiểm soát polymorphism, custom deserializer và class được phép khởi tạo.
5. **Áp giới hạn tài nguyên và phân quyền.** Chặn nguồn ghi trái phép, giới hạn kích thước payload, độ sâu cấu trúc, timeout và quyền Redis.
6. **Với legacy JDK serialization, filter chỉ là lớp bổ sung.** JEP 290/JEP 415 giảm một số rủi ro nhưng không thay thế việc bỏ định dạng nguy hiểm ở ranh giới không tin cậy.
7. **Version dữ liệu và migration rõ ràng.** Đổi keyspace hoặc schema khi thay định dạng; tránh đọc nhầm JDK bytes thành JSON và ngược lại.
8. **Giữ nguồn dữ liệu chuẩn có khả năng tái tạo cache.** Khi payload cache sai định dạng hoặc không đáng tin, nhiều trường hợp an toàn nhất là loại bỏ cache và xây dựng lại từ nguồn đáng tin cậy.

Spring Data Redis giúp việc chuyển đổi giữa object và bytes trở nên thuận tiện, nhưng chính sự thuận tiện đó có thể che mất việc **deserialize đang thực thi logic Java trong JVM**. Khi hiểu ranh giới này, bạn có thể thiết kế bộ nhớ đệm có schema rõ, thay đổi version ít rủi ro hơn và tránh để dữ liệu Redis trở thành điểm vào cho object graph không đáng tin cậy.

## Tài liệu tham khảo

- [Spring Data Redis — Serializers và RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Java 21 — Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html)
- [Java 21 — ObjectInputFilter API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html)
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [CWE-502 — Deserialization of Untrusted Data](https://cwe.mitre.org/data/definitions/502.html)

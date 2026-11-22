# Phân biệt Redis Server, trình điều khiển và Spring Data Redis

Khi một ứng dụng Java lưu hoặc đọc dữ liệu từ Redis, ba tên gọi thường xuất hiện cùng lúc: **Redis Server**, **trình điều khiển Redis (Redis client/driver)** và **Spring Data Redis**. Chúng thuộc ba tầng có trách nhiệm khác nhau. Hiểu đúng ranh giới này giúp chọn thư viện, cấu hình kết nối, đọc lỗi và thiết kế cách sử dụng Redis trong Spring Boot.

Điểm cốt lõi:

- **Redis Server** là tiến trình hoặc dịch vụ thực sự nhận lệnh, quản lý dữ liệu và thực thi thao tác trên Redis.
- **Trình điều khiển** là thư viện phía ứng dụng nói chuyện với Redis Server qua mạng, chẳng hạn **Lettuce** hoặc **Jedis** trong Java.
- **Spring Data Redis** là tầng tích hợp của hệ sinh thái Spring, cung cấp API, ánh xạ dữ liệu và các tiện ích Spring ở phía ứng dụng; nó **dùng một trình điều khiển ở bên dưới** để kết nối Redis Server.

## 1. Nhìn từ kiến trúc tổng thể

Giả sử một dịch vụ Spring Boot lưu mã xác thực tạm thời vào Redis:

~~~text
                       BÊN TRONG ỨNG DỤNG SPRING BOOT

    Controller / Service / Business Logic
                    |
                    v
      Spring Data Redis: StringRedisTemplate
                    |
                    v
             RedisConnectionFactory
                    |
                    v
       Redis driver: Lettuce hoặc Jedis
                    |
                    | Lệnh Redis qua TCP/TLS, giao thức RESP
                    v
       +----------------------------------+
       |           Redis Server           |
       |   Keys, values, TTL, dữ liệu,    |
       |   cấu hình, persistence...       |
       +----------------------------------+
                    ^
                    |
          redis-cli / ứng dụng khác
~~~

Sơ đồ này thể hiện **một con đường truy cập phổ biến**, không phải ba dịch vụ bắt buộc phải triển khai độc lập:

1. Redis Server chạy riêng trên máy phát triển, container, máy chủ hoặc dịch vụ Redis được quản lý.
2. Driver và Spring Data Redis là **thư viện chạy bên trong tiến trình ứng dụng Java**.
3. Spring Data Redis giúp mã nghiệp vụ không phải trực tiếp viết các thao tác kết nối hay lời gọi của Lettuce/Jedis cho các nhu cầu thông dụng.
4. Một ứng dụng Java **không dùng Spring** vẫn có thể gọi Lettuce/Jedis trực tiếp để truy cập cùng Redis Server.

## 2. Redis Server: nơi dữ liệu và lệnh Redis thực sự tồn tại

**Redis Server** là thành phần phía máy chủ của Redis. Nó lắng nghe kết nối từ client, nhận lệnh, thực thi lệnh và trả kết quả. Redis thường lưu dữ liệu đang hoạt động trong bộ nhớ; tùy cấu hình và yêu cầu hệ thống, nó có thể sử dụng các cơ chế lưu bền như RDB snapshot hoặc AOF.

Redis hỗ trợ nhiều cấu trúc dữ liệu, không chỉ một chuỗi key-value đơn giản:

| Cấu trúc | Một ví dụ sử dụng | Lệnh tiêu biểu |
|---|---|---|
| String | Mã xác thực, bộ đếm, chuỗi JSON | GET, SET, INCR |
| Hash | Thuộc tính của một đối tượng | HSET, HGET |
| List | Danh sách có thứ tự, hàng đợi đơn giản | LPUSH, LRANGE |
| Set | Tập giá trị duy nhất | SADD, SMEMBERS |
| Sorted Set | Bảng xếp hạng có điểm số | ZADD, ZRANGE |
| Stream | Luồng sự kiện và nhóm consumer | XADD, XREADGROUP |

Ví dụ, người dùng có thể gửi lệnh qua công cụ dòng lệnh Redis:

~~~bash
redis-cli PING
# PONG

redis-cli SET lesson:message "Xin chao Redis" EX 300
# OK

redis-cli GET lesson:message
# "Xin chao Redis"

redis-cli TTL lesson:message
# Số giây còn lại trước khi key hết hạn
~~~

Trong ví dụ này:

- **Redis Server** lưu key có tên **lesson:message**, chuỗi giá trị tương ứng và thời gian hết hạn.
- Tùy chọn **EX 300** đặt TTL 300 giây ngay khi ghi. Khi hết hạn, key không còn được xem là tồn tại.
- **redis-cli** chỉ là một chương trình client gửi lệnh; nó không phải Redis Server.
- Cổng TCP mặc định thường là **6379**, nhưng triển khai thực tế có thể dùng cổng khác, TLS, xác thực và topology khác.

Redis Server còn chịu trách nhiệm về các hành vi thuộc phía máy chủ như quản lý bộ nhớ, chính sách loại bỏ key khi chịu áp lực bộ nhớ, nhân bản dữ liệu và các phương án high availability hoặc clustering theo cấu hình triển khai. **TTL** và **eviction** là hai cơ chế khác nhau: TTL cho key hết hạn theo thời gian; eviction loại bỏ key theo chính sách khi Redis chạm giới hạn bộ nhớ.

Đổi từ Lettuce sang Jedis hoặc từ Java thuần sang Spring Data Redis **không thay thế Redis Server**, cũng không tự di chuyển dữ liệu khỏi máy chủ Redis.

## 3. Trình điều khiển Redis: cầu nối mạng giữa Java và Redis Server

### 3.1. Driver làm gì?

Một **Redis client/driver** là thư viện phía ứng dụng hiểu cách giao tiếp với Redis Server. Với Java, hai lựa chọn phổ biến là **Lettuce** và **Jedis**.

Các công việc điển hình của driver gồm:

- Tạo và quản lý kết nối TCP/TLS đến Redis Server, xác thực nếu cần.
- Chuyển lời gọi API Java thành lệnh theo giao thức Redis (**RESP — Redis Serialization Protocol**), gửi lệnh qua mạng và đọc phản hồi.
- Cung cấp các kiểu truy cập mà thư viện hỗ trợ, như đồng bộ, bất đồng bộ hoặc reactive.
- Xử lý những vấn đề ở tầng kết nối, ví dụ timeout, đóng kết nối, kết nối lại hoặc quản lý connection pool theo thiết kế và cấu hình cụ thể.

Driver **không phải một cơ sở dữ liệu**. Nó có thể giữ bộ đệm hoặc trạng thái kết nối trong ứng dụng, nhưng không biến JVM thành Redis Server.

### 3.2. Ví dụ gọi Lettuce trực tiếp, không cần Spring

Giả sử chương trình có dependency **io.lettuce:lettuce-core** và một Redis Server đang chạy ở localhost:6379:

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;

public class LettuceExample {
    public static void main(String[] args) {
        RedisClient client = RedisClient.create("redis://localhost:6379");

        try (StatefulRedisConnection<String, String> connection = client.connect()) {
            String result = connection.sync()
                    .set("lesson:driver", "Hello from Lettuce");

            String value = connection.sync()
                    .get("lesson:driver");

            System.out.println(result); // OK
            System.out.println(value);  // Hello from Lettuce
        } finally {
            client.shutdown();
        }
    }
}
~~~

Dòng xử lý thực tế:

1. Ứng dụng tạo **RedisClient**.
2. **client.connect()** thiết lập kết nối đến Redis Server.
3. Lời gọi **connection.sync().set(...)** được Lettuce chuyển thành lệnh Redis và gửi đi.
4. Redis Server thực thi **SET**, trả kết quả **OK**.
5. Lettuce chuyển phản hồi thành giá trị Java và trả cho chương trình.

Đây là mô hình truy cập trực tiếp. Lập trình viên làm việc với API của Lettuce và tự quản lý vòng đời client/connection; với ứng dụng thực tế, cách tạo và chia sẻ các đối tượng này cần theo hướng dẫn của phiên bản driver đang dùng.

### 3.3. Lettuce và Jedis khác Spring Data Redis ở đâu?

Lettuce và Jedis là **hai lựa chọn cùng tầng driver**. Cả hai giao tiếp với Redis Server, nhưng khác nhau về API, mô hình kết nối và các khả năng cụ thể tùy phiên bản.

| Khía cạnh | Lettuce | Jedis |
|---|---|---|
| Vai trò | Redis client cho Java | Redis client cho Java |
| Trải nghiệm API | Hỗ trợ các kiểu sử dụng đồng bộ, bất đồng bộ và reactive | API Java trực tiếp, thường gặp trong mã thao tác đồng bộ |
| Kết nối | Có mô hình kết nối dựa trên Netty; lựa chọn sử dụng/chia sẻ kết nối tùy kiểu thao tác | Có mô hình kết nối và pool phù hợp với API của Jedis |
| Spring Data Redis | Có thể làm driver bên dưới | Có thể làm driver bên dưới |

**Không cần viết cả hai driver** để truy cập Redis từ một ứng dụng. Spring Boot với starter Spring Data Redis thường sử dụng Lettuce theo cấu hình dependency mặc định; Jedis có thể được chọn khi cấu hình dependencies và connection factory tương ứng.

## 4. Spring Data Redis: tầng trừu tượng và tích hợp với Spring

### 4.1. Spring Data Redis làm thêm điều gì?

**Spring Data Redis** là một dự án của Spring Data. Nó xây dựng các API hướng Spring trên một Redis driver để chương trình thao tác dữ liệu thuận tiện và nhất quán hơn với hệ sinh thái Spring.

Các thành phần thường gặp:

| Thành phần Spring Data Redis | Chức năng |
|---|---|
| **RedisConnectionFactory** | Cung cấp kết nối Redis cho các thành phần Spring; triển khai dựa trên driver đã chọn |
| **RedisTemplate<K, V>** | API thao tác key/value và các cấu trúc Redis, kết hợp serializer được cấu hình |
| **StringRedisTemplate** | Biến thể thuận tiện cho key và value dạng chuỗi, dùng serializer chuỗi |
| **ValueOperations / HashOperations / ListOperations / SetOperations / ZSetOperations** | Các nhóm thao tác tương ứng cấu trúc dữ liệu Redis |
| **RedisCacheManager** | Kết nối Redis với Spring Cache abstraction |
| **Redis repositories** | Ánh xạ một số đối tượng Java thành dữ liệu Redis thông qua repository và annotation |
| **ReactiveRedisTemplate** | API truy cập Redis theo mô hình reactive khi dùng driver và cấu hình tương thích |

Spring Data Redis giúp quản lý bean, inject dependency, cấu hình serializer, tích hợp transaction/callback, cache abstraction, publish/subscribe và các tiện ích khác tùy nhu cầu. Tuy nhiên, không phải mọi khả năng của Redis Server đều luôn được phơi bày giống hệt API gốc của từng driver.

Quan trọng: **RedisConnectionFactory không phải Redis Server**. Đây là abstraction bên trong ứng dụng dùng để tạo hoặc cung cấp kết nối đến máy chủ.

### 4.2. Ví dụ dùng Spring Data Redis qua Spring Boot

Một ứng dụng Spring Boot 3.x có thể khai báo dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter này đưa các thư viện tích hợp Redis vào ứng dụng và thường chọn Lettuce làm driver mặc định. **Starter không cài đặt hay tự khởi chạy Redis Server**. Redis Server vẫn phải tồn tại và có thể kết nối được.

Cấu hình kết nối ví dụ trong **application.yml**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Khi dependency, điều kiện auto-configuration và kết nối phù hợp, Spring Boot có thể cấu hình **RedisConnectionFactory** và các template để inject vào service.

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GreetingStore {
    private final StringRedisTemplate redis;

    public GreetingStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String userId, String message) {
        String key = "greeting:" + userId;

        redis.opsForValue()
                .set(key, message, Duration.ofMinutes(5));
    }

    public String find(String userId) {
        return redis.opsForValue()
                .get("greeting:" + userId);
    }
}
~~~

Trong đoạn mã:

- **GreetingStore** chỉ biết **StringRedisTemplate**, không phải tự khởi tạo **RedisClient** hay quản lý socket.
- **opsForValue().set(...)** biểu diễn thao tác trên Redis String, có TTL 5 phút.
- Ở phía dưới, template dùng connection factory rồi driver gửi lệnh đến Redis Server.
- Redis Server mới là nơi thực thi thao tác và quản lý vòng đời key.
- **StringRedisTemplate** thích hợp khi cả key lẫn value là chuỗi. Với object, cần chủ động thiết kế cách serialize.

Đây là giá trị cốt lõi của Spring Data Redis: tầng ứng dụng dùng các abstraction ổn định và cấu hình theo Spring, trong khi Redis driver lo giao tiếp mạng.

### 4.3. Serializer: một ranh giới dễ nhầm

Khi gọi một template, đối tượng Java phải được chuyển sang dữ liệu mà Redis có thể lưu/truyền. Spring Data Redis có các **RedisSerializer** để quyết định dạng bytes của key và value.

Ví dụ:

- **StringRedisTemplate** dùng serializer chuỗi cho cả key và value, nên nội dung text thường dễ quan sát bằng **redis-cli**.
- **RedisTemplate<String, SomeObject>** cần serializer phù hợp với dữ liệu thực tế. Cấu hình mặc định của RedisTemplate ở nhiều phiên bản dùng Java serialization, có thể tạo dữ liệu nhị phân khó đọc và ràng buộc vào lớp Java.
- Nếu nhiều hệ thống hoặc nhiều ngôn ngữ phải đọc chung key, thường cần thống nhất định dạng như JSON, schema dữ liệu và tên key, đồng thời cân nhắc tương thích phiên bản.

**RESP** là giao thức mà driver dùng để trao đổi lệnh và phản hồi với Redis Server; **RedisSerializer** là cách Spring Data Redis chuyển key/value của ứng dụng thành bytes. Hai thuật ngữ này có chữ “serialization” nhưng giải quyết hai vấn đề khác nhau.

## 5. Một thao tác SET đi qua ba tầng ra sao?

Xét lời gọi:

~~~java
redis.opsForValue().set("session:42", "active");
~~~

Luồng xử lý khái niệm:

~~~text
Service
   |
   | 1. set("session:42", "active")
   v
StringRedisTemplate
   |
   | 2. Dùng StringRedisSerializer, lấy Redis connection
   v
RedisConnectionFactory
   |
   | 3. Cung cấp kết nối dựa trên Lettuce/Jedis
   v
Driver Redis
   |
   | 4. Gửi lệnh SET theo RESP qua mạng
   v
Redis Server
   |
   | 5. Ghi key/value và trả phản hồi
   v
Driver -> Spring Data Redis -> Service
~~~

Điều gì sẽ xảy ra khi thay đổi một tầng?

| Thay đổi | Điều thay đổi chủ yếu | Điều vẫn giữ nguyên về mặt vai trò |
|---|---|---|
| Chuyển Redis Server từ localhost lên dịch vụ managed | Host, port, TLS, xác thực, topology và vận hành | Ứng dụng vẫn cần client kết nối và gửi lệnh |
| Chuyển Lettuce sang Jedis | Driver, cách cấu hình và khả năng dùng API native | Redis Server vẫn nhận lệnh Redis; Spring Data Redis vẫn là tầng abstraction nếu được giữ lại |
| Chuyển từ gọi Lettuce trực tiếp sang StringRedisTemplate | API phía ứng dụng, dependency injection, serializer và cách cấu hình | Dữ liệu vẫn ở Redis Server và vẫn cần driver thực hiện kết nối |
| Dùng Spring Cache thay cho thao tác template trực tiếp | Ứng dụng thể hiện chính sách cache qua annotation/cache abstraction | Redis Server vẫn là backend nếu RedisCacheManager được chọn |

## 6. Spring Data Redis, Spring Cache và Redis Repository có phải một thứ?

**Không.** Đây là những khả năng liên quan nhưng khác mục đích:

### 6.1. RedisTemplate: chủ động viết lệnh lưu/đọc

~~~java
redis.opsForValue().set("otp:user-7", "123456", Duration.ofMinutes(2));
String otp = redis.opsForValue().get("otp:user-7");
~~~

Code quyết định **khi nào** ghi, đọc, xóa key và TTL. Đây là lựa chọn phù hợp cho token, counter, rate limiting đơn giản, trạng thái tạm thời hoặc dữ liệu cần điều khiển ở mức lệnh Redis.

### 6.2. Spring Cache: khai báo việc cache kết quả phương thức

Spring Cache abstraction cung cấp annotation **@Cacheable**, **@CachePut**, **@CacheEvict**. Redis chỉ là một trong các backend cache có thể sử dụng.

Để kết quả phương thức thực sự được cache ở Redis, ứng dụng phải bật caching và có **CacheManager** phù hợp, ví dụ:

~~~java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration config =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .cacheDefaults(config)
                .build();
    }
}
~~~

Sau đó có thể khai báo một phương thức:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @Cacheable(cacheNames = "greetings", key = "#name")
    public String buildGreeting(String name) {
        // Trong thực tế, giá trị trả về có thể đến từ tác vụ tốn kém.
        return "Xin chao, " + name;
    }
}
~~~

Khi phương thức được gọi qua Spring proxy và key chưa có trong cache, Spring thực thi phương thức rồi ghi kết quả vào cache. Khi có cache hit hợp lệ, Spring trả dữ liệu đã cache theo cấu hình. **@Cacheable không có nghĩa Redis sẽ tự động được sử dụng**: cần bật caching và chọn đúng CacheManager. Các quy tắc của Spring AOP như self-invocation cũng có thể ảnh hưởng việc annotation được áp dụng.

### 6.3. Redis repositories: ánh xạ đối tượng

Spring Data Redis còn hỗ trợ repository và annotation như **@RedisHash** để lưu và truy vấn các aggregate theo mô hình được Spring Data Redis hỗ trợ.

Repository giúp giảm code thao tác key/hash thủ công trong một số trường hợp, nhưng **không biến Redis thành cơ sở dữ liệu quan hệ**, không tự cung cấp JOIN SQL, và có giới hạn về cách lập chỉ mục/truy vấn. Khi cần tận dụng cấu trúc Redis cụ thể hoặc các lệnh chuyên biệt, template hoặc driver trực tiếp có thể rõ ràng hơn.

## 7. So sánh trách nhiệm theo từng lớp

| Câu hỏi | Redis Server | Driver (Lettuce/Jedis) | Spring Data Redis |
|---|---|---|---|
| Nằm ở đâu? | Tiến trình/dịch vụ phía server | Thư viện trong JVM ứng dụng | Thư viện trong JVM ứng dụng Spring |
| Ai sở hữu dữ liệu Redis? | **Có** | Không | Không |
| Ai thực thi SET, GET, HSET? | **Redis Server** | Gửi lệnh và nhận phản hồi | Cung cấp API để yêu cầu thao tác |
| Ai mở kết nối mạng? | Nhận kết nối từ client | **Driver** thiết lập/điều khiển kết nối phía client | Dùng factory và driver |
| Ai biết API Spring/DI? | Không | Không bắt buộc | **Có** |
| Ai cấu hình serialize object Java cho template? | Không | Có codec/kiểu chuyển đổi ở tầng client tùy API | **RedisSerializer** và cấu hình template |
| Ai xử lý lưu bền RDB/AOF? | **Redis Server** | Không | Không |
| Ai cung cấp @Cacheable tích hợp với Redis? | Không | Không | Spring Cache kết hợp RedisCacheManager của Spring Data Redis |
| Có thể sử dụng độc lập? | Có thể chạy như dịch vụ | Có thể dùng trong Java thuần cùng Redis Server | Cần môi trường Spring và driver phù hợp; vẫn phải có Redis Server |

Ghi nhớ thêm: thao tác trên Redis có thể **atomic ở mức từng lệnh** như INCR, nhưng điều đó không tự bảo đảm toàn bộ chuỗi nhiều lệnh ở service có tính atomic. Khi nghiệp vụ đòi hỏi phối hợp nhiều thao tác, phải lựa chọn cơ chế phù hợp như lệnh atomic, Lua scripting hay transaction theo ngữ nghĩa Redis; đổi sang Spring Data Redis không làm các chuỗi lệnh tự động trở thành một transaction toàn cục.

## 8. Chọn cách sử dụng nào trong dự án?

**Trường hợp A — Java thuần, không dùng Spring:** dùng Lettuce hoặc Jedis trực tiếp. Bạn phụ trách khởi tạo driver, kết nối, đóng tài nguyên và định dạng dữ liệu. Redis Server phải được triển khai hoặc cấp sẵn.

**Trường hợp B — Ứng dụng Spring Boot cần lưu key/value, TTL, hash, list, set:** thường bắt đầu từ **spring-boot-starter-data-redis** và **StringRedisTemplate/RedisTemplate**. Spring quản lý bean, cấu hình kết nối và tích hợp tiện ích; driver thực hiện giao tiếp.

**Trường hợp C — Ứng dụng Spring Boot muốn cache kết quả phương thức:** sử dụng **Spring Cache** với **RedisCacheManager** và cấu hình TTL, cache key, serialization, chính sách xóa/invalidate cache cho đúng nghiệp vụ.

**Trường hợp D — Cần thao tác Redis rất đặc thù hoặc dùng API mới chưa được abstraction hỗ trợ:** cân nhắc API RedisConnection/native connection hoặc gọi driver trực tiếp, đồng thời kiểm soát tài nguyên và tính tương thích. Việc dùng Spring Data Redis không cấm truy cập driver, nhưng nên duy trì một chiến lược truy cập nhất quán.

**Trường hợp E — Muốn đổi Redis Server thành Redis Cluster hoặc dịch vụ managed:** quyết định thuộc kiến trúc triển khai. Cần kiểm tra driver, cách cấu hình connection factory, TLS/auth, routing và khả năng hỗ trợ topology tương ứng; việc chỉ sửa host không phải lúc nào cũng đủ.

## 9. Phân tích lỗi theo đúng tầng

Đặt đúng trách nhiệm giúp tránh sửa nhầm code:

| Hiện tượng | Kiểm tra trước tiên |
|---|---|
| Connection refused hoặc không đến được host/port | Redis Server có chạy, bind đúng địa chỉ, mở cổng và network route/firewall có cho phép không? |
| Timeout kết nối hoặc thao tác | Mạng, độ trễ máy chủ, timeout và cách driver quản lý connection |
| NOAUTH / WRONGPASS | Redis Server yêu cầu xác thực gì và ứng dụng truyền đúng thông tin chưa? |
| Spring Boot không inject được StringRedisTemplate | Dependency, auto-configuration và cấu hình bean/RedisConnectionFactory |
| Ghi bằng template nhưng redis-cli thấy bytes khó đọc | Serializer của key/value; có dùng RedisTemplate với serializer nhị phân không? |
| @Cacheable không tạo cache hit như mong đợi | @EnableCaching, CacheManager, cách gọi qua proxy, cache key và TTL |
| Key biến mất sớm | TTL, lệnh xóa/invalidation, hoặc eviction/policy bộ nhớ trên Redis Server |
| Lỗi chỉ xuất hiện khi thay đổi topology | Driver và connection factory đã cấu hình cho cluster/Sentinel/TLS phù hợp chưa? |

Về bảo mật, thông tin xác thực nên đi qua biến môi trường, secret manager hoặc cơ chế cấu hình an toàn thay vì ghi password cố định trong mã nguồn. Redis Server cần giới hạn truy cập mạng phù hợp với môi trường chạy.

## 10. Những nhầm lẫn thường gặp

**“Thêm spring-boot-starter-data-redis là có Redis Server.”** Không đúng. Starter cung cấp thư viện phía ứng dụng; Redis Server phải được chạy hoặc cung cấp riêng.

**“Spring Data Redis thay thế Lettuce/Jedis.”** Không đúng. Spring Data Redis thường **sử dụng** Lettuce hoặc Jedis ở dưới; hai tầng làm việc cùng nhau.

**“Ứng dụng Spring Boot phải tự tạo RedisClient.”** Thông thường không cần nếu đã sử dụng Spring Data Redis với auto-configuration phù hợp. Có thể inject template hoặc connection factory.

**“Redis chỉ dùng được làm cache.”** Không đúng. Redis là data store hỗ trợ nhiều cấu trúc và kiểu ứng dụng; cache chỉ là một trường hợp phổ biến. Việc nên dùng Redis làm nguồn dữ liệu chính hay dữ liệu tạm phụ thuộc yêu cầu độ bền, phục hồi và vận hành.

**“Cứ có RedisTemplate thì @Cacheable tự ghi vào Redis.”** Không đúng. RedisTemplate và Spring Cache là hai cách tương tác khác nhau; annotation cache cần caching infrastructure/CacheManager.

**“Trình điều khiển và serializer là một.”** Không đúng. Driver đóng vai trò giao tiếp mạng/protocol, còn serializer quyết định cách biểu diễn dữ liệu Java trước khi gửi hoặc sau khi đọc.

**“Redis Server nằm trong cùng JVM với Spring Boot.”** Trong mô hình thông thường, Redis Server là tiến trình hoặc dịch vụ riêng; JVM chứa driver và Spring Data Redis. Chạy cả hai trên cùng máy cũng không khiến chúng trở thành cùng một tiến trình.

## 11. Tự kiểm tra hiểu biết qua một tình huống

Giả sử đội phát triển có một ứng dụng Spring Boot và một Redis Server được quản lý trên cloud. Service cần ghi trạng thái **order:123 = processing** trong 15 phút, còn dashboard đọc lại giá trị đó.

Một cách thực hiện:

~~~java
redis.opsForValue().set(
        "order:123",
        "processing",
        Duration.ofMinutes(15)
);

String status = redis.opsForValue().get("order:123");
~~~

Hãy xác định trách nhiệm:

1. **Ai thực thi lệnh SET và theo dõi TTL?** Redis Server trên cloud.
2. **Ai gửi lệnh từ JVM qua mạng?** Driver Redis được ứng dụng chọn, ví dụ Lettuce.
3. **Ai cung cấp API opsForValue() và tích hợp dependency injection?** Spring Data Redis.
4. **Nếu thay StringRedisTemplate bằng gọi Lettuce trực tiếp, Redis Server có biến mất không?** Không; chỉ đổi cách ứng dụng tạo và gửi yêu cầu.
5. **Nếu chuyển Redis từ localhost lên cloud, service có nhất thiết phải viết lại thao tác set/get không?** Thường không; chủ yếu thay cấu hình kết nối, bảo mật và topology, miễn client tương thích.
6. **Nếu dashboard dùng Python thay vì Java, nó có bắt buộc dùng Spring Data Redis không?** Không. Nó dùng Redis client phù hợp với Python và vẫn truy cập cùng Redis Server.

### Mô hình cần nhớ

~~~text
Redis Server     = NƠI dữ liệu được lưu và lệnh được thực thi
Redis driver     = CÁCH chương trình Java giao tiếp với Redis Server
Spring Data Redis = API + tích hợp Spring DỰA TRÊN driver đó

Spring Service
    -> RedisTemplate / Spring Cache / Redis Repository
    -> RedisConnectionFactory
    -> Lettuce hoặc Jedis
    -> Redis Server
~~~

Khi đọc ví dụ hoặc xử lý lỗi Redis trong Spring Boot, hãy hỏi **“đây là vấn đề của máy chủ, kết nối client hay abstraction Spring?”**. Câu hỏi đó dẫn đến đúng nơi cần cấu hình và đúng công cụ cần kiểm tra.

# Trách nhiệm của RedisConnectionFactory và RedisConnection

Trong Spring Data Redis, **RedisConnectionFactory** và **RedisConnection** là hai abstraction ở tầng kết nối giữa mã Spring và Redis driver (thường là Lettuce hoặc Jedis). Chúng dễ bị nhầm vì đều chứa chữ “Connection”, nhưng đóng hai vai trò khác nhau:

- **RedisConnectionFactory** là thành phần **cung cấp kết nối**. Nó biết ứng dụng phải kết nối Redis theo cấu hình nào và tạo/cấp phát đối tượng **RedisConnection** khi một thành phần Spring cần làm việc với Redis.
- **RedisConnection** là giao diện **thực hiện các lệnh Redis** qua kết nối đã được factory cung cấp. Nó đại diện cho phiên làm việc ở tầng Spring Data Redis và có vòng đời sử dụng/giải phóng riêng.

Thông thường, lập trình viên nghiệp vụ dùng **RedisTemplate**, **StringRedisTemplate** hoặc Spring Cache. Các abstraction này sử dụng **RedisConnectionFactory** và **RedisConnection** ở bên dưới, nên không nhất thiết phải thao tác trực tiếp với chúng.

## 1. Vị trí của hai thành phần trong kiến trúc

~~~text
                  ỨNG DỤNG SPRING BOOT

   OrderService, TokenService, CacheService...
                       |
                       | thao tác set/get/incr...
                       v
      RedisTemplate / StringRedisTemplate
          RedisCacheManager / repository
                       |
                       | yêu cầu kết nối
                       v
             RedisConnectionFactory
          (LettuceConnectionFactory hoặc
             JedisConnectionFactory)
                       |
                       | getConnection()
                       v
                 RedisConnection
                       |
                       | thực thi Redis commands
                       v
                Lettuce / Jedis
                       |
                       | TCP/TLS + Redis protocol
                       v
                   Redis Server
                       |
                       v
            dữ liệu, TTL, trạng thái key
~~~

Sơ đồ diễn tả **ranh giới trách nhiệm**, không nhất thiết là một đối tượng Java mới được tạo ở mọi ô hoặc một kết nối TCP mới được mở cho mỗi lệnh. Tùy factory và driver, nhiều **RedisConnection** của Spring có thể dùng chung một native connection bên dưới hoặc sử dụng pool.

Ba tầng cần tách bạch:

1. **Spring Data Redis** định nghĩa và điều phối các abstraction như RedisConnectionFactory, RedisConnection, RedisTemplate.
2. **Driver Redis** quản lý việc gửi/nhận lệnh với Redis Server qua mạng.
3. **Redis Server** thực sự xử lý lệnh, lưu key/value và thực thi TTL.

RedisConnectionFactory và RedisConnection đều **sống trong tiến trình ứng dụng Java**. Không thành phần nào trong hai thành phần này tự biến thành Redis Server.

## 2. RedisConnectionFactory: nguồn cung cấp kết nối cho Spring

### 2.1. Factory chịu trách nhiệm gì?

**RedisConnectionFactory** là một interface của Spring Data Redis. Lời gọi cơ bản nhất là:

~~~java
RedisConnection connection = connectionFactory.getConnection();
~~~

Các trách nhiệm chính:

| Trách nhiệm | Ý nghĩa |
|---|---|
| Cung cấp kết nối | Trả về đối tượng RedisConnection để code Spring Data Redis dùng thực hiện lệnh |
| Đóng gói lựa chọn driver | Ứng dụng có thể dùng factory triển khai dựa trên Lettuce hoặc Jedis |
| Mang cấu hình kết nối | Host, port, xác thực, TLS, database hoặc cluster/Sentinel theo khả năng của factory và cấu hình |
| Điều phối tài nguyên phía client | Tích hợp cơ chế kết nối của driver, có thể gồm tái sử dụng native connection hoặc pool |
| Phục vụ hệ sinh thái Spring | Được RedisTemplate, cache infrastructure, repository và các thành phần Redis khác tham chiếu |
| Hỗ trợ chuyển đổi ngoại lệ | Tích hợp với cơ chế ánh xạ ngoại lệ truy cập dữ liệu của Spring |

**Factory không chứa dữ liệu key/value của Redis** và không trực tiếp “lưu bản ghi” thay Redis Server. Factory cũng không tự quyết định nghiệp vụ nên dùng key nào, TTL bao nhiêu hay lưu đối tượng theo JSON nào; những lựa chọn đó thuộc code sử dụng template/serializer hoặc các tầng ứng dụng khác.

### 2.2. Các implementation phổ biến

Trong ứng dụng Java, thường gặp:

- **LettuceConnectionFactory**: triển khai RedisConnectionFactory dựa trên **Lettuce**.
- **JedisConnectionFactory**: triển khai RedisConnectionFactory dựa trên **Jedis**.

Hai factory này đều cung cấp abstraction Spring Data Redis, nhưng dựa trên driver với cơ chế kết nối khác nhau. Việc đổi implementation cần kiểm tra dependency, cấu hình, capability và vận hành; không nên suy luận rằng cách chia sẻ connection, pooling hay xử lý thread là giống hệt nhau.

Ví dụ Spring Boot thường dùng Lettuce qua starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Cấu hình kết nối cho Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Khi điều kiện auto-configuration được đáp ứng, Spring Boot cấu hình một bean **RedisConnectionFactory** phù hợp và các bean template cần thiết. Giá trị kết nối có thể được lấy từ cấu hình ứng dụng hoặc môi trường triển khai. **Starter chỉ cung cấp thư viện client**: Redis Server phải được khởi chạy hoặc được cấp riêng.

Nếu tự định nghĩa bean factory, ứng dụng đang nhận trách nhiệm cấu hình mà Spring Boot có thể đã tự làm:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ExplicitRedisConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(server);
    }
}
~~~

Đây là ví dụ **tùy chọn**, hữu ích để nhìn thấy quan hệ giữa interface và implementation. Trong ứng dụng Boot đơn giản, dùng auto-configuration thường gọn hơn. Nếu cần password, TLS, Sentinel, Cluster hoặc cấu hình pooling/timeout chuyên biệt, phải cấu hình đúng với môi trường thực tế, thay vì sao chép bean mẫu chỉ có host/port.

### 2.3. Factory có tạo một TCP connection mới cho mỗi lần gọi không?

**Không thể khẳng định chỉ từ lời gọi getConnection().** Kết quả của factory là một **đối tượng RedisConnection ở tầng Spring**; vòng đời của **native connection** do implementation/driver quyết định.

Ví dụ điển hình với **LettuceConnectionFactory**:

- Factory có thể cấp các RedisConnection wrapper khác nhau cho các lời gọi.
- Với cấu hình mặc định phổ biến, một native connection của Lettuce có thể được **chia sẻ** cho các thao tác thông thường không ở trạng thái transaction hoặc blocking.
- Các thao tác cần connection chuyên biệt, ví dụ một số thao tác blocking hoặc transaction, có thể sử dụng connection khác; cấu hình và phiên bản driver ảnh hưởng hành vi thực tế.
- Khi bật cơ chế pooling phù hợp, pool quyết định cách cấp/trả các kết nối vật lý tương ứng.

Vì vậy, cần phân biệt ba thứ:

| Khái niệm | Bản chất |
|---|---|
| RedisConnectionFactory | Bean/factory dùng để cấp kết nối |
| RedisConnection | Wrapper/abstraction kết nối mà mã Spring Data Redis sử dụng |
| Native connection | Kết nối hoặc đối tượng kết nối thực tế do Lettuce/Jedis quản lý |

Không nên thiết kế tài nguyên dựa trên giả định rằng **số lần gọi getConnection() bằng số socket TCP mới**.

## 3. RedisConnection: nơi thực thi các Redis command

### 3.1. RedisConnection cung cấp những gì?

**RedisConnection** là interface đại diện cho khả năng thao tác với Redis ở tầng Spring Data Redis. Nó cung cấp nhóm lệnh tương ứng các cấu trúc dữ liệu/công việc Redis.

Ví dụ các nhóm lệnh thường gặp:

| Nhóm API | Lệnh tiêu biểu | Nhu cầu |
|---|---|---|
| **stringCommands()** | GET, SET, INCR | Chuỗi, counter |
| **keyCommands()** | DEL, EXPIRE, TTL | Quản lý key và thời hạn |
| **hashCommands()** | HGET, HSET | Redis Hash |
| **listCommands()** | LPUSH, LRANGE | Danh sách |
| **setCommands()** | SADD, SMEMBERS | Tập hợp |
| **zSetCommands()** | ZADD, ZRANGE | Tập hợp có điểm số |
| **connectionCommands()** | PING và lệnh về connection | Quan sát kết nối |
| **scriptingCommands()** | Thực thi script | Nghiệp vụ cần script tại Redis |

Các API cụ thể và lệnh hỗ trợ phụ thuộc phiên bản Spring Data Redis, driver và Redis Server. Mã nghiệp vụ cấp cao thường dễ hiểu hơn khi thao tác qua **opsForValue()**, **opsForHash()** và các API của RedisTemplate.

Ngoài lệnh dữ liệu, RedisConnection hỗ trợ các thao tác mức thấp liên quan đến **pipeline**, **transaction**, **subscription** và truy cập **native connection**, tùy driver/topology và tình huống sử dụng.

### 3.2. RedisConnection làm gì khi gửi GET?

Giả sử cần đọc key có tên **profile:42**:

~~~text
Ứng dụng
   |
   | connection.stringCommands().get(keyBytes)
   v
RedisConnection
   |
   | gọi tới driver phù hợp
   v
Lettuce / Jedis
   |
   | gửi lệnh GET profile:42
   v
Redis Server
   |
   | trả dữ liệu hoặc nil nếu key không tồn tại
   v
Driver -> RedisConnection -> byte[] hoặc null -> Ứng dụng
~~~

RedisConnection **không tự thực thi Redis GET trong JVM**. Phần lệnh được xử lý ở Redis Server; RedisConnection chuyển yêu cầu từ abstraction Spring đến driver và đưa phản hồi về caller.

Ở API mức thấp, key/value thường được biểu diễn bằng **byte[]**. Điều này khác với **StringRedisTemplate**, nơi serializer chuyển chuỗi Java thành bytes và ngược lại.

### 3.3. Ví dụ trực tiếp với RedisConnection

Đây là ví dụ đọc/ghi **chuỗi UTF-8** thông qua factory, không đi qua RedisTemplate:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class RawRedisStore {

    private final RedisConnectionFactory connectionFactory;

    public RawRedisStore(RedisConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public void save(String key, String value) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);
        byte[] valueBytes = value.getBytes(StandardCharsets.UTF_8);

        try (RedisConnection connection = connectionFactory.getConnection()) {
            connection.stringCommands().set(keyBytes, valueBytes);
        }
    }

    public String read(String key) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        try (RedisConnection connection = connectionFactory.getConnection()) {
            byte[] result = connection.stringCommands().get(keyBytes);

            return result == null
                    ? null
                    : new String(result, StandardCharsets.UTF_8);
        }
    }
}
~~~

Đọc code theo trách nhiệm:

1. **connectionFactory** là dependency do Spring cấp vào service.
2. **getConnection()** cung cấp RedisConnection để thực hiện thao tác hiện tại.
3. **stringCommands().set/get** yêu cầu thực thi lệnh Redis.
4. **UTF-8** là lựa chọn mã hóa của ví dụ; Spring Data Redis không tự serialize object Java khi gọi RedisConnection mức thấp theo cách RedisTemplate làm.
5. Khối **try-with-resources** bảo đảm RedisConnection được đóng/giải phóng sau thao tác, kể cả khi có lỗi.

Mẫu này có ích khi cần điều khiển API thấp, nhưng code phải tự xử lý bytes và vòng đời tài nguyên. Vì vậy, phần lớn nghiệp vụ thông thường nên sử dụng template.

## 4. Khác biệt quan trọng: tạo/cấp kết nối và sử dụng kết nối

| Tiêu chí | RedisConnectionFactory | RedisConnection |
|---|---|---|
| Kiểu thành phần | Factory, được quản lý như bean trong Spring | Interface kết nối/thực thi lệnh |
| Trách nhiệm chính | Cung cấp kết nối theo cấu hình | Gửi Redis command, nhận phản hồi |
| API điển hình | **getConnection()** | **stringCommands().get/set**, **keyCommands()**, **multi/exec** |
| Ai thường sử dụng? | RedisTemplate, cache, repositories, code cần lấy connection | RedisTemplate callback hoặc code mức thấp |
| Quản lý cấu hình host/port/TLS | Chủ yếu qua factory/driver config | Dùng kết nối được factory cấp |
| Vòng đời | Thường sống theo Spring application context | Gắn với một phạm vi thao tác, callback hoặc transaction |
| Có chứa dữ liệu Redis không? | Không | Không |
| Có nên chia sẻ cho nhiều request? | Bean factory thường dùng chung | Không nên tự giữ/chia sẻ RedisConnection giữa nhiều thread/request |
| Khi hoàn thành thao tác | Không đóng bean factory mỗi request | Giải phóng RedisConnection đúng cách |

Nhầm lẫn phổ biến là nghĩ **factory chính là một connection** hoặc **RedisConnection là một bean singleton nên có thể lưu vào field của service để dùng mãi**. Factory là tài nguyên dài hạn; RedisConnection thường là đối tượng làm việc ngắn hạn với trạng thái/vòng đời riêng.

## 5. RedisTemplate điều phối hai thành phần như thế nào?

Spring Data Redis khuyến khích dùng template cho thao tác thông thường bởi vì nó xử lý nhiều chi tiết thay người gọi:

- Lấy RedisConnection qua factory.
- Chuyển key/value sang dạng dữ liệu được driver gửi đi nhờ serializer.
- Thực thi callback/lệnh Redis.
- Chuyển kết quả nhận được thành kiểu Java phù hợp.
- Giải phóng kết nối theo cơ chế của Spring, bao gồm các trường hợp kết nối đang được bind cho transaction.

Ví dụ sử dụng **StringRedisTemplate**:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStateService {

    private final StringRedisTemplate redis;

    public SessionStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void markActive(String sessionId) {
        redis.opsForValue().set(
                "session:" + sessionId,
                "active",
                Duration.ofMinutes(15)
        );
    }

    public String getState(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }
}
~~~

Luồng khái niệm của lời gọi **markActive("42")**:

~~~text
SessionStateService
    |
    | redis.opsForValue().set("session:42", "active", 15 phút)
    v
StringRedisTemplate
    |-- serialize key/value thành bytes
    |-- lấy RedisConnection thông qua RedisConnectionFactory
    |-- chạy SET với thời hạn 15 phút qua driver
    |-- xử lý phản hồi
    '-- giải phóng RedisConnection theo vòng đời phù hợp
    |
    v
Redis Server: quản lý key session:42 và TTL
~~~

Ưu điểm của template so với tự gọi factory ở mọi service:

1. **Ít mã tài nguyên lặp lại**: không phải mở/đóng connection trong từng hàm.
2. **Một chính sách serialization có thể cấu hình thống nhất**.
3. **Tích hợp cơ chế Spring**: exception translation, transaction-bound resources, callback và các khả năng khác.
4. **Dễ duy trì ranh giới nghiệp vụ**: service mô tả ý định lưu dữ liệu hơn là chi tiết kết nối.

Một **RedisTemplate** đã cấu hình xong được thiết kế để dùng lại giữa nhiều luồng. Điều này **không có nghĩa** RedisConnection mà nó tạo ra cũng an toàn để chia sẻ thủ công giữa các thread.

### 5.1. Dùng RedisCallback khi cần API kết nối thấp

Khi vẫn muốn Spring quản lý connection nhưng cần gọi một API RedisConnection trực tiếp, có thể dùng **RedisTemplate.execute(RedisCallback)**:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LowLevelLookup {

    private final RedisTemplate<String, String> template;

    public LowLevelLookup(RedisTemplate<String, String> template) {
        this.template = template;
    }

    public byte[] findRawBytes(String key) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);

        RedisCallback<byte[]> callback =
                connection -> connection.stringCommands().get(keyBytes);

        return template.execute(callback);
    }
}
~~~

**RedisCallback** nhận RedisConnection do template cung cấp. Template chịu trách nhiệm lấy và giải phóng resource; **không tự đóng connection trong callback**.

Với callback dùng bytes thủ công, lập trình viên cần bảo đảm **cách mã hóa key trùng với key serializer** mà nơi ghi đã dùng. Nếu các phần khác của ứng dụng dùng serializer khác UTF-8, việc tự chuyển key thành UTF-8 như trên có thể đọc nhầm namespace key. Ví dụ này có chủ đích minh họa ranh giới API thấp, không thay thế các thao tác **opsForValue()** khi chúng đã đủ.

## 6. Vòng đời kết nối và ý nghĩa của close()

### 6.1. Vòng đời ứng dụng

~~~text
Spring Boot start
  -> tạo/configure LettuceConnectionFactory (hoặc JedisConnectionFactory)
  -> inject vào RedisTemplate/RedisCacheManager/Service
  -> ứng dụng nhận request
       -> template hoặc code lấy RedisConnection
       -> thực hiện command
       -> giải phóng RedisConnection
  -> request khác tiếp tục dùng factory
Spring Boot shutdown
  -> Spring đóng tài nguyên/lifecycle của factory và driver
~~~

**RedisConnectionFactory** thường tồn tại cùng application context; không khởi tạo factory mới cho mỗi request. **RedisConnection** được lấy và dùng trong một phạm vi phù hợp (một thao tác, một callback hoặc transaction) rồi trả lại/đóng đúng quy tắc.

### 6.2. close() có ngắt socket Redis hay không?

Lời gọi **connection.close()** thể hiện rằng **caller không tiếp tục dùng RedisConnection đó**. Kết quả tác động lên socket gốc **không đồng nhất ở mọi implementation**:

- Nếu native connection được chia sẻ hoặc pool quản lý, việc close ở tầng wrapper có thể chỉ giải phóng/trả resource, không đóng socket vật lý.
- Nếu connection sở hữu một native connection riêng, cơ chế đóng có thể tác động trực tiếp đến native connection.
- Khi factory bị hủy theo vòng đời ứng dụng, nó có trách nhiệm dọn dẹp các tài nguyên mà nó quản lý.

Không nên bỏ qua close vì tin rằng driver luôn chia sẻ socket; cũng không nên dựa vào close như một cách buộc toàn bộ socket đến Redis Server ngừng hoạt động.

### 6.3. Ai đóng connection trong từng cách sử dụng?

| Cách dùng | Ai chịu trách nhiệm giải phóng? |
|---|---|
| Gọi trực tiếp **factory.getConnection()** | Code gọi, thường dùng try-with-resources |
| **RedisTemplate.opsForValue()** hoặc opsForHash() | RedisTemplate/cơ chế quản lý resource của Spring |
| **RedisTemplate.execute(RedisCallback)** | Template; callback không tự close |
| RedisConnection được bind với transaction qua utility Spring | Cơ chế binding/release của Spring; không đóng tùy tiện giữa transaction |
| Sử dụng API Lettuce/Jedis trực tiếp bên ngoài Spring | Code phải tuân thủ lifecycle của driver tương ứng |

Spring Data Redis cung cấp tiện ích **RedisConnectionUtils** để lấy và giải phóng kết nối có xét đến resource binding của Spring, đặc biệt khi dùng transaction support. Khi sử dụng tầng template, nên để template điều phối thay vì tự gọi utility nếu không có yêu cầu chuyên biệt.

## 7. RedisConnection và native connection: tại sao cần phân biệt?

Spring Data Redis định nghĩa các interface độc lập tương đối với driver. Driver lại có API riêng và cách quản lý network riêng.

~~~text
                       Spring abstraction
              +-------------------------------+
              | RedisConnectionFactory        |
              |   -> RedisConnection          |
              +-------------------------------+
                             |
                             v
                    Driver implementation
                   +-------------------+
                   | Lettuce or Jedis  |
                   +-------------------+
                             |
                             v
                   Native connection/socket
                             |
                             v
                        Redis Server
~~~

RedisConnection có thể cung cấp khả năng truy cập **getNativeConnection()** khi cần tính năng đặc thù của driver. Nhưng khi gọi API native:

- Code sẽ phụ thuộc vào **loại driver** và có thể cần ép kiểu.
- Cơ chế timeout, luồng và lifecycle phải được hiểu theo tài liệu của driver đó.
- Không nên đóng native connection do Spring quản lý một cách tùy tiện.
- Đổi từ Lettuce sang Jedis có thể buộc phải sửa code truy cập native.

Chỉ dùng native connection khi RedisConnection/RedisTemplate không có API đáp ứng yêu cầu cụ thể. Với thao tác Redis thông thường, giữ API Spring giúp code ít phụ thuộc nhà cung cấp driver.

## 8. Thread safety và chia sẻ connection

Một factory thường được inject vào nhiều bean và phục vụ nhiều request cùng lúc. Song cần phân biệt tính chia sẻ của các đối tượng:

**RedisConnectionFactory:** thường là một bean dài hạn có thể phục vụ nhiều luồng để cấp RedisConnection. Việc sử dụng đồng thời và quản lý connection thực tế do implementation đảm nhận.

**RedisTemplate:** an toàn để sử dụng đồng thời **sau khi đã cấu hình hoàn chỉnh**; không nên sửa serializer hoặc các thiết lập của cùng template trong lúc request đang chạy.

**RedisConnection:** không nên tự động xem là thread-safe. Tài liệu Spring Data Redis cảnh báo connection không được thiết kế để chia sẻ giữa nhiều thread; nó có thể chứa trạng thái như pipeline, transaction hoặc subscription.

**Native Lettuce connection:** một số loại connection Lettuce có thể thread-safe và được factory chia sẻ. Điều này **không suy ra** một RedisConnection wrapper của Spring cũng thread-safe.

Ví dụ chống lại kiểu thiết kế sau:

~~~java
// Tránh giữ một RedisConnection làm field dùng mãi cho mọi request.
@Service
public class SharedConnectionAntiPattern {
    private final RedisConnection connection;

    public SharedConnectionAntiPattern(RedisConnectionFactory factory) {
        this.connection = factory.getConnection();
    }

    // Nhiều thread có thể cùng dùng connection có state này.
}
~~~

Thay vào đó, inject **StringRedisTemplate/RedisTemplate** cho nghiệp vụ thông thường; hoặc inject factory và lấy/giải phóng RedisConnection trong phạm vi ngắn.

## 9. RedisConnection với transaction, pipeline và Pub/Sub

Những tác vụ này cho thấy vì sao không thể xem RedisConnection như một đối tượng gửi lệnh vô trạng thái ở mọi tình huống.

### 9.1. Redis transaction: MULTI / EXEC

Redis hỗ trợ nhóm lệnh như **MULTI**, **EXEC**, **DISCARD**, **WATCH**. Trong transaction kiểu Redis, trạng thái xếp lệnh liên quan đến **connection**. Các thao tác giữa MULTI và EXEC phải dùng đúng connection đang ở transaction; dùng connection độc lập có thể làm mất ngữ cảnh.

Luồng khái niệm:

~~~text
RedisConnection A:
    MULTI
    SET balance:1 100    (được xếp vào queue)
    INCR counter         (được xếp vào queue)
    EXEC                 (Redis thực thi transaction)

RedisConnection B:
    GET balance:1        (không tự trở thành lệnh trong A)
~~~

Spring Data Redis có thể tích hợp transaction-bound connection thông qua RedisTemplate khi **transaction support được bật và cấu hình đúng**. Không nên suy luận rằng chỉ cần đặt annotation **@Transactional** lên một hàm là mọi thao tác RedisTemplate mặc nhiên chạy trong Redis MULTI/EXEC. Redis transaction cũng không có cùng semantics rollback như transaction trong cơ sở dữ liệu quan hệ.

### 9.2. Pipeline: gom nhiều lệnh theo một luồng gửi/nhận

Pipeline cho phép client gửi nhiều lệnh mà không phải đợi phản hồi sau từng lệnh theo mô hình thông thường. Nó có thể giảm round trips cho khối lượng lệnh phù hợp; nó **không biến các lệnh thành transaction atomic**.

Spring Data Redis hỗ trợ phương thức **executePipelined(...)** của RedisTemplate. Khi dùng callback với pipeline, các giá trị phản hồi có thể được thu thập và trả về sau khi pipeline hoàn tất, thay vì có kết quả đầy đủ ngay tại mỗi lời gọi lệnh trong callback.

Cần quan tâm:

- Các lệnh pipeline chạy trong ngữ cảnh connection phù hợp.
- Không dùng đồng thời một RedisConnection có state pipeline giữa các request khác nhau.
- Pipeline hiệu quả hay không còn phụ thuộc số lệnh, payload, topology và chi phí xử lý ở Redis Server.

### 9.3. Publish/Subscribe

Trong Redis Pub/Sub, client subscribe nhận message theo mô hình kết nối có trạng thái và kéo dài. Không nên mượn tùy tiện RedisConnection phục vụ request đồng bộ rồi giữ mãi cho subscribe.

Trong Spring Data Redis, có thể dùng **RedisMessageListenerContainer** để quản lý listener và hạ tầng đăng ký kênh, hoặc các API chuyên biệt tương ứng nhu cầu. Đây là ví dụ cho thấy abstraction Spring ở trên factory giúp tổ chức lifecycle phức tạp hơn so với tự giữ connection trong từng service.

## 10. Cấu hình RedisConnectionFactory thay đổi theo topology

Factory là nơi tích hợp cách ứng dụng kết nối với Redis deployment. Redis Server có thể chạy theo nhiều kiểu:

| Mô hình Redis | Vấn đề cần cấu hình ở tầng kết nối |
|---|---|
| Standalone | Host, port, thông tin xác thực, database, timeout |
| Sentinel | Các địa chỉ Sentinel, tên master, cấu hình xác thực phù hợp |
| Cluster | Danh sách node/seed, xử lý Redis Cluster routing và redirect, tùy driver |
| Managed Redis qua TLS | TLS, chứng chỉ hoặc chính sách kiểm tra kết nối, thông tin xác thực |

Đối với Redis Cluster, không nên mặc nhiên dùng nguyên cấu hình standalone rồi chỉ thay một host. Factory/driver phải hiểu topology và cách định tuyến key/redirect. Với Redis Sentinel, factory/driver cần biết cách tìm master thích hợp.

**RedisConnectionFactory định nghĩa cách lấy kết nối**, còn việc thiết lập replication, persistence, failover và chính sách bộ nhớ là trách nhiệm của Redis deployment. Factory không tự biến một Redis standalone server thành cluster chỉ vì trong ứng dụng có nhiều bean.

## 11. RedisConnectionFactory và serializer: hai trách nhiệm tách biệt

Một nguồn lỗi phổ biến là cấu hình kết nối đúng nhưng đọc ra dữ liệu “lạ” hoặc không tìm thấy key do mã hóa khác nhau.

| Thành phần | Trách nhiệm |
|---|---|
| RedisConnectionFactory | Cung cấp kết nối đến Redis |
| RedisConnection | Thực hiện lệnh với bytes/lệnh tương ứng |
| RedisSerializer | Chuyển key/value giữa đối tượng Java và bytes |
| RedisTemplate | Phối hợp serializer, connection và lệnh Redis |
| Redis Server | Lưu bytes và áp dụng semantics của các lệnh Redis |

Ví dụ **StringRedisTemplate** mã hóa key và value thành chuỗi. Nếu một RedisTemplate khác dùng kiểu serializer không tương thích để ghi key, StringRedisTemplate có thể không đọc được cùng dữ liệu dù cả hai đang sử dụng **cùng một RedisConnectionFactory**.

Điều này có nghĩa: đổi RedisConnectionFactory **không tự giải quyết vấn đề serializer**, cũng như đổi serializer **không sửa được kết nối sai host/port**.

Nếu nhiều microservice cùng truy cập Redis, nên thống nhất tên key/namespace, cấu trúc payload, serializer, TTL và chiến lược tương thích phiên bản.

## 12. Những lỗi thường gặp và nơi kiểm tra

| Hiện tượng | Tầng cần kiểm tra trước | Hướng điều tra |
|---|---|---|
| Lỗi khi tạo hoặc lấy connection | Factory, driver, Redis Server, network | Host/port, server đang chạy, kết nối TLS, password, firewall |
| **RedisConnectionFailureException** | Driver và kết nối đến server | Mạng, khả năng truy cập, server availability, connection configuration |
| Read/Write timeout | Driver/Redis Server/mạng | Timeout, độ trễ, tải server, blocking command |
| **No qualifying bean of type RedisConnectionFactory** | Spring configuration | Starter/dependency, bean tùy biến, điều kiện auto-configuration |
| **WRONGPASS/NOAUTH** | Cấu hình authentication của client và Redis Server | Username/password, ACL và secret |
| Dùng template nhưng key không đọc được | Serializer và cách tạo key | So sánh key/value bytes, namespace, serializer |
| Connection bị giữ lâu và tài nguyên tăng | Code sử dụng connection hoặc pool | Có đóng connection lấy trực tiếp không, có giữ connection trong singleton không |
| Transaction/pipeline có hành vi bất ngờ | Cách bind connection, lifecycle và semantics Redis | Connection có được dùng đúng phạm vi không, có dùng API template phù hợp không |
| Đổi driver rồi lỗi khi ép kiểu native connection | Code phụ thuộc driver | getNativeConnection() và API native cụ thể |
| Kết nối standalone được nhưng cluster không hoạt động đúng | Factory/driver theo topology | Cấu hình cluster, routing, node addresses |

Một lỗi như **RedisConnectionFailureException** không có nghĩa factory đang lưu dữ liệu sai; nó thường biểu thị không tạo/duy trì được kết nối theo cách mong muốn. Còn trường hợp **đọc ra byte[] không đúng định dạng** có thể là vấn đề serializer, dù kết nối hoàn toàn bình thường.

## 13. Đồng bộ và reactive có cùng interface không?

Spring Data Redis có hai họ abstraction tương ứng hai mô hình lập trình:

| Mô hình | Factory | Connection | Template |
|---|---|---|---|
| Đồng bộ (imperative) | **RedisConnectionFactory** | **RedisConnection** | **RedisTemplate**, **StringRedisTemplate** |
| Reactive | **ReactiveRedisConnectionFactory** | **ReactiveRedisConnection** | **ReactiveRedisTemplate**, **ReactiveStringRedisTemplate** |

Reactive API trả về các kiểu như **Mono**/**Flux**, phù hợp khi ứng dụng sử dụng reactive stack và driver được hỗ trợ. Không nên coi việc có RedisConnectionFactory đồng bộ là bằng chứng rằng mọi lời gọi của ứng dụng đã non-blocking.

Đối với ứng dụng MVC hoặc service đồng bộ thông thường, template đồng bộ có thể đáp ứng tốt. Với luồng WebFlux reactive, nên cân nhắc template/factory reactive tương ứng để không đưa thao tác blocking vào chuỗi reactive.

## 14. Khi nào cần làm việc trực tiếp với factory/connection?

**Nghiệp vụ CRUD key/value và TTL:** ưu tiên StringRedisTemplate hoặc RedisTemplate. Code tập trung vào key, data và TTL; Spring quản lý phần kết nối.

**Bộ nhớ đệm kết quả phương thức:** cân nhắc Spring Cache với RedisCacheManager. Cache abstraction sử dụng RedisConnectionFactory thông qua hạ tầng Spring Data Redis; code thường không cần trực tiếp mở connection.

**Lệnh thấp hoặc command đặc thù:** có thể dùng RedisTemplate.execute(RedisCallback) để chạy với RedisConnection do Spring quản lý.

**Tích hợp driver trực tiếp:** chỉ nên dùng getNativeConnection() hoặc driver API nếu tính năng đòi hỏi và đã hiểu rõ dependency/lifecycle.

**Viết hạ tầng/framework tích hợp Redis:** RedisConnectionFactory là dependency thích hợp khi một component cần tự nhận connection để xây dựng abstraction khác. Khi đó phải xác định rõ ai quản lý vòng đời và trạng thái connection.

## 15. Tình huống thực hành: hai cách ghi cùng một key

Yêu cầu: một service ghi **cart:42 = OPEN** để service khác đọc qua Redis.

**Cách 1 — Dùng template (khuyến nghị cho nghiệp vụ phổ biến):**

~~~java
stringRedisTemplate.opsForValue().set("cart:42", "OPEN");

String state = stringRedisTemplate.opsForValue().get("cart:42");
~~~

Spring Data Redis làm các công việc ở tầng dưới: dùng serializer phù hợp, lấy kết nối từ factory, thực thi lệnh bằng RedisConnection qua driver, giải phóng tài nguyên.

**Cách 2 — Dùng RedisConnection trực tiếp:**

~~~java
byte[] key = "cart:42".getBytes(StandardCharsets.UTF_8);
byte[] value = "OPEN".getBytes(StandardCharsets.UTF_8);

try (RedisConnection conn = connectionFactory.getConnection()) {
    conn.stringCommands().set(key, value);
    byte[] readBack = conn.stringCommands().get(key);
    System.out.println(new String(readBack, StandardCharsets.UTF_8));
}
~~~

Ở cách 2, code tự lựa chọn encoding và đóng RedisConnection. Hai cách vẫn gọi tới **cùng Redis Server** nếu factory/template được cấu hình trỏ tới cùng nơi. Tuy nhiên, không nên mặc nhiên khẳng định các key được serialize thành bytes giống nhau nếu serializer của template đã bị tùy biến.

Giải thích vai trò của từng dòng:

1. **connectionFactory.getConnection()**: “Hãy cho tôi một RedisConnection phù hợp với cấu hình ứng dụng.”
2. **conn.stringCommands().set(...)**: “Hãy thực thi lệnh SET với key/value này.”
3. **Driver Lettuce/Jedis**: chuyển thao tác thành giao tiếp với Redis Server.
4. **Redis Server**: ghi key và trả phản hồi.
5. **conn.close()** khi ra khỏi khối try: giải phóng RedisConnection theo quy ước của factory/driver.

## 16. Câu hỏi củng cố

**1. Một ứng dụng có thể có một RedisConnectionFactory và rất nhiều thao tác RedisConnection không?**

Có. Factory thường là bean sống lâu. Nhiều thao tác lấy connection qua factory/template theo thời gian. Không suy luận số lượng socket vật lý từ số đối tượng RedisConnection.

**2. Vì sao RedisTemplate nhận RedisConnectionFactory thay vì chỉ nhận host/port?**

Vì nó cần một abstraction cung cấp connection, tách logic thao tác/serialize khỏi cách driver kết nối Redis. Factory cho phép Spring quản lý cấu hình và lifecycle tập trung.

**3. Factory có chịu trách nhiệm đặt TTL cho key không?**

Không. TTL được yêu cầu bằng lệnh Redis từ template/connection, rồi Redis Server thực thi. Factory chỉ giúp có connection để gửi lệnh.

**4. Có thể tạo RedisConnection một lần và dùng chung cho mọi thread không?**

Không nên. RedisConnection không được xem là thread-safe; transaction, pipeline và subscription có trạng thái gắn với connection. Nên dùng template thread-safe đã cấu hình hoặc tạo connection đúng phạm vi.

**5. Vì sao close() ở RedisConnection không nhất thiết làm mất TCP socket?**

Vì implementation có thể chia sẻ hoặc pool native connection. Đóng wrapper/return connection là hành động quản lý tài nguyên ở tầng Spring; socket gốc thuộc cơ chế của factory/driver.

**6. Dùng @Transactional có làm mọi lời gọi Redis tự động thuộc MULTI/EXEC không?**

Không mặc định. RedisTemplate cần transaction support và cơ chế binding/configuration phù hợp; cần hiểu semantics transaction Redis trước khi sử dụng.

**7. Đọc/ghi bằng RedisConnection thành công nhưng StringRedisTemplate không đọc cùng dữ liệu thì sao?**

Kiểm tra bytes của key, namespace và serializer trước khi đổ lỗi cho factory. Hai API có thể sử dụng biểu diễn key khác nhau.

## Ghi nhớ

~~~text
RedisConnectionFactory
    = CẤP PHÁT / CUNG CẤP RedisConnection
    = giữ cấu hình kết nối và phối hợp cơ chế driver
    = thường là bean dùng lại suốt vòng đời ứng dụng

RedisConnection
    = THỰC HIỆN các Redis command ở tầng Spring Data Redis
    = có vòng đời và trạng thái cần quản lý đúng cách
    = chuyển thao tác xuống Lettuce/Jedis

RedisTemplate
    = LẤY kết nối từ factory, serialize và điều phối lệnh
    = tự quản lý việc giải phóng connection cho thao tác thông thường

Lettuce/Jedis
    = GIAO TIẾP MẠNG với Redis Server

Redis Server
    = XỬ LÝ LỆNH, LƯU DỮ LIỆU, QUẢN LÝ TTL
~~~

Khi thiết kế hoặc chẩn đoán một ứng dụng Spring Data Redis, hãy xác định vấn đề thuộc **cấu hình/cấp phát connection**, **cách sử dụng RedisConnection**, **serializer/template**, **driver/mạng** hay **Redis Server**. Phân biệt đúng trách nhiệm giúp code dễ bảo trì và tránh lỗi tài nguyên, thread safety hoặc kết nối.

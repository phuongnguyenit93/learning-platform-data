# Phân loại lỗi kết nối, thời gian chờ, lệnh và tuần tự hóa

Khi một ứng dụng Spring Boot làm việc với Redis, một lỗi quan sát được ở tầng service có thể xuất phát từ nhiều nơi: không tạo được kết nối TCP/TLS, kết nối đang dùng bị đứt, một lệnh chạy quá thời hạn chờ, Redis từ chối lệnh vì sai kiểu dữ liệu hoặc quyền truy cập, hoặc ứng dụng không chuyển đổi được object Java sang dạng byte lưu trong Redis. Các tình huống này **không nên được xử lý bằng một lệnh `catch (Exception) { retry(); }` chung**, vì mỗi loại có nguyên nhân, mức độ chắc chắn và cách khôi phục khác nhau.

Spring Data Redis cung cấp `RedisTemplate`, `StringRedisTemplate`, API reactive và tầng repository/cache trên các Redis driver như **Lettuce** hoặc **Jedis**. Exception ở tầng ứng dụng không nhất thiết có đúng tên exception của driver: Spring có thể **dịch ngoại lệ (exception translation)** sang nhóm `DataAccessException`, trong khi lỗi serializer có thể đi qua một nhánh khác. Vì vậy, một hệ thống vận hành tốt cần quan sát **chuỗi nguyên nhân (cause chain)**, ngữ cảnh thao tác và dữ liệu đo đạc trước khi kết luận.

Bài học tập trung vào bốn nhóm lỗi: **connection**, **timeout**, **command** và **serialization**. Ngoài cách nhận diện, bài còn đề xuất cách log/metric, chính sách retry có giới hạn, xử lý Redis như cache best-effort, phân biệt trong Reactor và ví dụ kiểm thử thực tế. Những đoạn mã sử dụng Java 21, Spring Boot 3.x và Spring Data Redis; phiên bản driver hoặc Spring khác có thể tạo exception cụ thể khác, nên không dựa hoàn toàn vào một tên class duy nhất.

## 1. Nhìn lỗi theo các tầng của đường gọi Redis

Một request từ ứng dụng có thể đi qua những bước:

~~~text
Controller / Scheduled job / Consumer
                  |
                  v
             Business service
                  |
                  v
     RedisTemplate / RedisCache / Repository
                  |
                  v
           Serializer / Mapper
                  |
                  v
        RedisConnectionFactory
                  |
                  v
             Lettuce / Jedis
                  |
           DNS, TCP, TLS, ACL
                  |
                  v
              Redis server
                  |
        Nhận command và thực thi
                  |
                  v
             Redis response
                  |
                  v
          Deserialize kết quả
                  |
                  v
            Business service
~~~

Tùy vị trí thất bại, biểu hiện khác nhau:

- Không kết nối được tới Redis: thường là **connection failure**.
- Đã gửi lệnh nhưng hết thời gian chờ phản hồi: thường là **command timeout**, nhưng chưa biết server đã chạy lệnh hay chưa.
- Redis nhận lệnh rồi trả `-ERR WRONGTYPE` hoặc `NOPERM`: là **command execution error**; reconnect đơn thuần không sửa được payload hoặc ACL.
- Redis trả byte hợp lệ nhưng Java không đọc được object vì serializer/schema sai: là **deserialization error**.

Một lỗi có thể liên quan tới nhiều tầng. Ví dụ Redis failover gây mất connection, lời gọi đang chờ kết thúc bằng timeout, còn command sau đó nhận `READONLY` do client vẫn trỏ tới replica cũ. Vì thế **phân loại là công cụ quyết định hành động**, không phải một giả định rằng mọi sự cố chỉ có đúng một nguyên nhân.

## 2. Bảng phân loại nhanh

| Nhóm | Dấu hiệu điển hình | Nguyên nhân thường gặp | Hành động ưu tiên |
| --- | --- | --- | --- |
| **Kết nối** | Không mở được socket, connection refused/reset, DNS/TLS lỗi | Redis down, firewall, sai host/port, pool cạn, failover | Kiểm tra endpoint, TLS, kết nối và topology; retry có giới hạn nếu lỗi tạm thời |
| **Thời gian chờ** | Command không trả về trong deadline; request hủy do timeout | Network latency, Redis quá tải, lệnh chậm, command queue, pool wait | Đo giai đoạn chờ, loại lệnh và khả năng đã thực thi; không retry lệnh không lũy đẳng một cách mù quáng |
| **Lệnh** | `WRONGTYPE`, `READONLY`, `NOAUTH`, `NOPERM`, `CROSSSLOT`, `ERR` | Sai dữ liệu, sai command, thiếu quyền, stale topology, giới hạn server | Sửa key/schema/ACL/routing; chỉ retry khi phân tích thấy lỗi tạm thời |
| **Tuần tự hóa** | Không encode/decode được key/value, lỗi JSON/class/version | Serializer khác nhau, schema thay đổi, dữ liệu bị hỏng | Kiểm tra serializer/schema/payload; sửa dữ liệu hoặc migration, tránh retry liên tục |

Ví dụ chẩn đoán:

~~~text
GET cache:product:42
  |
  +-- Connection refused --------> CONNECTIVITY
  |
  +-- Command timed out ---------> TIMEOUT
  |
  +-- WRONGTYPE -----------------> COMMAND
  |
  +-- Byte trả về nhưng JSON lỗi -> SERIALIZATION
  |
  +-- Redis trả nil -------------> CACHE MISS, KHÔNG PHẢI LỖI
~~~

Điểm cuối rất quan trọng: **key không tồn tại không phải exception**. Với `StringRedisTemplate.opsForValue().get(key)`, một key thiếu thường trả `null`; với `ReactiveStringRedisTemplate`, thao tác có thể complete bằng `Mono.empty()`. Chỉ nên xem đó là lỗi nếu **nghiệp vụ** của ứng dụng yêu cầu key phải tồn tại, chứ không phải lỗi Redis connection hoặc command.

## 3. Những lớp exception thường gặp

Khi dùng Spring Data Redis, có hai nhóm exception nên biết:

1. **Spring abstraction**, thường xuất hiện từ API template hoặc repository sau khi exception translation.
2. **Redis driver**, thường thấy trong `cause` hoặc khi gọi Lettuce/Jedis trực tiếp.

Một số class đáng chú ý:

| Class / nhóm | Tầng | Thường biểu thị |
| --- | --- | --- |
| `org.springframework.data.redis.RedisConnectionFailureException` | Spring Data Redis | Không thiết lập hoặc sử dụng được Redis connection |
| `org.springframework.dao.QueryTimeoutException` | Spring DAO | Tác vụ dữ liệu vượt timeout đã áp dụng |
| `org.springframework.data.redis.RedisSystemException` | Spring Data Redis | Lỗi Redis không được ánh xạ vào một ngoại lệ DAO chuyên biệt |
| `org.springframework.dao.InvalidDataAccessApiUsageException` | Spring DAO | Sử dụng API/lệnh không hợp lệ theo tình huống |
| `org.springframework.data.redis.serializer.SerializationException` | Spring Data Redis | Lỗi tuần tự hóa hoặc giải tuần tự hóa |
| `org.springframework.dao.DataAccessException` | Spring DAO | Lớp cha của nhiều ngoại lệ truy cập dữ liệu đã được dịch |
| `io.lettuce.core.RedisConnectionException` | Lettuce | Lỗi thiết lập/sử dụng kết nối ở driver |
| `io.lettuce.core.RedisCommandTimeoutException` | Lettuce | Lệnh Redis vượt timeout ở driver |
| `io.lettuce.core.RedisCommandExecutionException` | Lettuce | Server trả lỗi khi thực thi command |

Đây là **các ví dụ thường gặp**, không phải bảng ánh xạ một-một bắt buộc. Tùy đường gọi, phiên bản Spring Data Redis/Jedis/Lettuce và loại lỗi cụ thể, lỗi từ server có thể được dịch thành `RedisSystemException` hoặc một subclass `DataAccessException` khác, với exception driver nằm bên trong.

### Exception translation không đồng nghĩa đổi bản chất lỗi

Ví dụ cấu trúc cause chain:

~~~text
RedisSystemException
  └── RedisCommandExecutionException
        └── message: WRONGTYPE Operation against a key
                    holding the wrong kind of value
~~~

Ở một ứng dụng khác, cùng một sự cố có thể được wrap bằng lớp khác. Nếu chỉ kiểm tra:

~~~java
if (error.getClass() == RedisSystemException.class) {
    // Tất cả đều là lỗi hệ thống tạm thời?
}
~~~

thì rất dễ phân loại sai một lỗi `WRONGTYPE` thành hỏng hạ tầng và retry mãi. Thay vào đó, cần dùng **kiểu exception cấp cao, cause chain và Redis error code/message đáng tin cậy** để nhận diện.

Không nên parsing stack trace dạng chuỗi tự do làm cách duy nhất để phân loại: message có thể thay đổi theo phiên bản server/driver, bị wrap hoặc được rút gọn. Với thông báo lỗi chuẩn từ Redis như `WRONGTYPE` và `NOPERM`, có thể dùng nó như **tín hiệu bổ sung** sau khi đã xem cause type.

## 4. Lỗi kết nối: Redis không thể giao tiếp ổn định

### 4.1. Những tình huống thường gặp

- Redis process chưa chạy hoặc đang restart.
- Sai hostname, DNS không phân giải được, sai port, firewall hoặc network policy chặn.
- Kết nối TCP bị reset vì Redis/client/proxy đóng socket.
- Sai TLS mode hoặc chứng chỉ khi môi trường yêu cầu TLS.
- Redis failover: primary cũ chết, replica được thăng cấp, client đang dùng endpoint/connection cũ.
- Pool không có connection khả dụng hoặc ứng dụng tạo quá nhiều connection, đôi khi biểu hiện như timeout lúc lấy connection.
- Môi trường Sentinel/Cluster công bố địa chỉ Redis mà ứng dụng không kết nối tới được qua NAT/container network.

Một lỗi connection điển hình có thể được Spring biểu diễn bằng:

~~~text
org.springframework.data.redis.RedisConnectionFailureException:
Unable to connect to Redis
Caused by: io.lettuce.core.RedisConnectionException:
Unable to connect to redis.internal:6379
~~~

Thông tin `Unable to connect` xác nhận tầng truy cập Redis thất bại, nhưng **chưa chứng minh Redis server đang down**. Cần phân biệt server down với DNS, routing, TLS, ACL và client resource exhaustion.

### 4.2. Cách chẩn đoán không phá dữ liệu

Từ chính môi trường **nơi ứng dụng chạy**, kiểm tra:

~~~bash
# Tên miền có phân giải được không?
nslookup redis.internal

# Chỉ để kiểm tra Redis sẵn sàng nhận lệnh nếu được cấp quyền.
redis-cli -h redis.internal -p 6379 PING

# Nếu triển khai TLS, dùng cách kết nối TLS đúng cấu hình:
redis-cli --tls -h redis.internal -p 6379 PING
~~~

Lệnh chỉ minh họa: dùng đúng port, TLS/ACL và công cụ sẵn có của môi trường. Không ghi mật khẩu trong command line hoặc đưa credential lên log chung; ưu tiên secret manager và cách xác thực an toàn của hạ tầng.

Ở phía Redis, xem log server, tình trạng node, số lượng client, giới hạn kết nối và các metric. Nếu chạy Sentinel/Cluster, kiểm tra **role và topology hiện tại**, không chỉ kiểm tra một Redis host cũ có phản hồi hay không.

### 4.3. Có nên retry?

Một lỗi kết nối tạm thời có thể hồi phục sau reconnect, nhưng retry phải có:

- Số lần thử hoặc deadline hữu hạn.
- Backoff và jitter để nhiều instance không cùng dồn lệnh sau Redis restart.
- Timeout riêng cho mỗi lần thử và cho toàn request/job.
- Tính lũy đẳng của thao tác được gửi lại.
- Metric để phân biệt “đã retry và thành công” với “từng có sự cố”.

Không được tự chuyển mọi lỗi kết nối thành “cache miss”. Nếu Redis là nơi lưu số dư hoặc khóa điều phối, mất kết nối có thể đòi **fail closed**: từ chối thao tác thay vì bỏ qua dữ liệu quan trọng. Nếu Redis chỉ là cache có thể tái tạo, một fallback có kiểm soát tới database có thể phù hợp.

## 5. Lỗi thời gian chờ: chưa chắc command đã thất bại ở server

Timeout là một **ranh giới quan sát**: phía gọi không nhận được kết quả trong thời gian quy định. Điều đó không nhất thiết có nghĩa Redis chưa thực hiện command.

Cần phân biệt ít nhất bốn loại thời gian chờ:

| Loại | Đang chờ cái gì? | Triệu chứng và hướng đo |
| --- | --- | --- |
| **Connect timeout** | Thiết lập TCP/TLS/connection tới Redis | Kiểm tra network, DNS, TLS và endpoint |
| **Command timeout** | Lệnh đã được driver gửi/xếp hàng nhưng không có kết quả kịp thời | Kiểm tra Redis latency, command, driver queue và mạng |
| **Pool acquisition timeout** | Đợi lấy một connection từ pool | Kiểm tra pool size, số request đồng thời, connection bị giữ lâu |
| **Application deadline** | Một chuỗi thao tác hoặc HTTP request vượt SLA | Kiểm tra tổng chi phí và timeout từng tầng |

Trong Spring, `QueryTimeoutException` có thể đại diện cho command timeout sau translation. Ở Lettuce, có thể thấy `RedisCommandTimeoutException` trong cause. Nếu truy cập driver trực tiếp, lỗi có thể xuất hiện mà không đi qua Spring DAO translation.

### Timeout không có một nguyên nhân duy nhất

Ví dụ:

~~~text
GET cache:big-value
        |
        +-- Driver chờ trong command queue
        |
        +-- Network bị delay
        |
        +-- Redis đang chạy command khác tốn thời gian
        |
        +-- Redis tạo phản hồi lớn, output buffer bị dồn
        |
        +-- Client đọc/deserialize phản hồi chậm
        |
        v
   Deadline hết trước khi có kết quả
~~~

Đừng tăng timeout từ 1 giây lên 60 giây ngay khi thấy một lỗi. Nếu Redis bị nghẽn do một lệnh có độ phức tạp cao, quá nhiều pipeline hoặc bộ nhớ thấp, tăng timeout có thể chỉ khiến nhiều request chờ lâu hơn và làm tình trạng quá tải nghiêm trọng hơn.

### Spring Boot timeout configuration

Một cấu hình minh họa:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

`connect-timeout` kiểm soát thời gian thiết lập connection, còn `timeout` là timeout thao tác Redis theo cấu hình Spring Boot/driver tương ứng. Giá trị trên chỉ là ví dụ; lựa chọn thực tế phụ thuộc network, loại command và SLA của ứng dụng.

Với Lettuce, có thể cấu hình command timeout trong Java:

~~~java
import java.time.Duration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .commandTimeout(Duration.ofSeconds(3))
        .build();
~~~

Đoạn này là cấu hình client, cần kết hợp với `RedisStandaloneConfiguration`, `RedisSentinelConfiguration` hoặc loại connection factory thích hợp. Nếu đã có Spring Boot auto-configuration, không tự tạo bean connection factory thứ hai không nhất quán.

### Hệ quả nguy hiểm khi retry

Giả sử:

~~~text
Client gửi INCR orders:count
          |
          v
Redis tăng từ 40 → 41
          |
          v
Phản hồi bị mất / đến sau deadline
          |
          v
Client thấy timeout
          |
          v
Client retry INCR → 42
~~~

Kết quả cuối tăng **hai lần**, dù ý định nghiệp vụ chỉ có một lượt. Vì thế, khi timeout sau khi command có thể đã gửi, cần coi trạng thái là **không xác định** và đánh giá tính lũy đẳng.

Nếu yêu cầu là “chỉ đánh dấu một job đã xử lý”, nên dùng idempotency key, ràng buộc unique hoặc thao tác điều kiện ở nơi dữ liệu được lưu. `retry(3)` không tự bảo đảm điều này.

## 6. Lỗi thực thi lệnh: Redis có phản hồi nhưng từ chối thao tác

Redis có thể trả một **error reply** cho command hợp lệ về mặt truyền thông nhưng không được thực thi thành công. Ở Lettuce, một số lỗi kiểu này được biểu diễn bằng `RedisCommandExecutionException`.

Những lỗi cần nhận diện:

| Thông báo Redis điển hình | Ngữ cảnh | Hướng xử lý |
| --- | --- | --- |
| `WRONGTYPE` | Gọi list/hash/set operation trên key đang lưu kiểu khác | Kiểm tra quy ước key, namespace và cấu trúc dữ liệu; không retry mù |
| `ERR unknown command` | Command không được Redis/version/plugin hỗ trợ | Kiểm tra phiên bản Redis/module và cách dùng API |
| `ERR wrong number of arguments` | Gửi sai tham số command | Sửa cách tạo command hoặc compatibility |
| `NOAUTH` / `WRONGPASS` | Chưa xác thực hoặc xác thực sai | Sửa credential/cấu hình; không retry vô hạn |
| `NOPERM` | ACL không cho user thực hiện command/key | Cấp đúng quyền theo least privilege; không bypass ACL |
| `READONLY` | Ghi tới replica không nhận write | Kiểm tra role và Sentinel/Cluster routing sau failover |
| `CROSSSLOT` | Multi-key command trên các slot khác nhau trong Cluster | Thiết kế hash slot/key layout phù hợp |
| `MOVED` / `ASK` | Cluster cần redirect sang node/slot khác | Kiểm tra driver cluster-aware và refresh topology |
| `BUSY` | Redis đang thực hiện script hoặc tác vụ có giới hạn | Điều tra script/tải; tránh retry dồn dập |
| `OOM` | Redis từ chối write do giới hạn bộ nhớ/policy | Kiểm tra memory, eviction policy và dữ liệu |
| `NOSCRIPT` | Script SHA chưa có trong script cache của node | Dùng cơ chế script evaluation có fallback phù hợp |

Phân biệt **lỗi command có thể khắc phục sau thay đổi topology** (ví dụ `READONLY` khi failover) với **lỗi cần sửa dữ liệu hoặc cấu hình** (`WRONGTYPE`, `NOPERM`). Nhiều lần retry cùng lệnh sai chỉ làm tăng tải và che nguyên nhân.

### 6.1. Ví dụ `WRONGTYPE`

Một key đã được lưu dạng String:

~~~redis
SET demo:wrongtype "hello"
~~~

Nhưng ứng dụng đọc như Redis List:

~~~redis
LLEN demo:wrongtype
~~~

Redis trả lỗi dạng:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Trong Spring Data Redis:

~~~java
redis.opsForValue().set("demo:wrongtype", "hello");
Long size = redis.opsForList().size("demo:wrongtype");
~~~

Lỗi không phải do DNS hay Redis quá chậm; key hiện có **kiểu String**, còn `LLEN` chỉ làm việc trên List. Phải làm rõ vì sao hai thành phần cùng dùng một key name nhưng mong đợi data type khác nhau.

Cách phòng tránh:

- Đặt namespace theo loại dữ liệu, ví dụ `cache:product:42` và `queue:invoice:pending`.
- Không dùng một key cho hai cấu trúc Redis khác nhau.
- Định nghĩa serializer và hợp đồng schema giữa các producer/consumer.
- Khi migration, thực hiện bước chuyển key/version có kiểm soát thay vì ghi đè cùng key bằng type khác.

### 6.2. Lỗi `READONLY` và failover

Nếu ứng dụng ghim host cũ làm primary nhưng Sentinel đã thăng cấp node khác, một lệnh `SET` trên node cũ giờ là replica có thể bị từ chối. Hướng xử lý là **cập nhật discovery/topology và reconnect tới primary mới**, không phải xóa key hay thay serializer.

Với Redis Cluster, client cần hỗ trợ `MOVED`/`ASK` để định tuyến đúng hash slot. Một `RedisStandaloneConfiguration` trỏ vào một node tùy ý không thay thế được cluster-aware configuration.

### 6.3. ACL và xác thực

`NOAUTH` hoặc `NOPERM` là lỗi cấu hình bảo mật/quyền truy cập. Không nên tự fallback sang tài khoản Redis có quyền cao hơn để “giữ cho hệ thống chạy” khi không có phê duyệt bảo mật. Cần xác định đúng Redis user, key pattern và command category cần thiết.

Trong log chỉ nên ghi **mã nhóm lỗi, command family và endpoint đã được xử lý an toàn**. Không ghi password, token, payload chứa dữ liệu cá nhân hoặc connection URI có credential.

### 6.4. Lỗi Redis script và transaction

Một script hoặc command có lỗi có thể đã thực hiện một số thay đổi trước khi gặp lỗi, tùy nội dung script. Lua script được chạy theo thứ tự độc quyền trên Redis trong lúc thực thi, nhưng Redis **không tự rollback những lệnh ghi trước lỗi trong script**. Tương tự, transaction Redis `MULTI/EXEC` không tương đương transaction rollback kiểu relational database cho mọi lỗi runtime.

Không nên kết luận mọi command error có nghĩa dữ liệu hoàn toàn không đổi. Khi một thao tác nhiều bước thất bại, cần đánh giá idempotency, đối soát trạng thái và cách bù trừ.

## 7. Lỗi tuần tự hóa (serialization/deserialization)

Redis lưu key và value dưới dạng byte. Spring Data Redis dùng `RedisSerializer` để chuyển đối tượng Java thành byte trước khi gửi lệnh và chuyển byte trả về thành đối tượng Java sau khi đọc.

Ví dụ hai hệ thống có cùng Redis key nhưng dùng serializer khác nhau:

~~~text
Service A:
  StringRedisTemplate
  "cache:user:42" → bytes UTF-8 của chuỗi JSON

Service B:
  RedisTemplate<String, User>
  Value serializer là JDK serialization
  Đọc cùng key → không thể deserialize thành Java object
~~~

Không có lỗi kết nối hoặc command Redis ở đây; server trả về **đúng byte đã lưu**, nhưng client B **hiểu sai định dạng**.

### Các nguyên nhân phổ biến

1. Một service dùng `StringRedisSerializer`, service khác dùng `JdkSerializationRedisSerializer` hoặc JSON serializer cho cùng namespace.
2. Schema JSON đã thay đổi: đổi tên field, kiểu dữ liệu, enum hoặc định dạng thời gian mà không có migration.
3. Dữ liệu cũ không chứa metadata cần thiết cho serializer hiện tại.
4. Class Java đã đổi tên package hoặc không còn tương thích với giá trị JDK-serialized trước đó.
5. Key serializer thay đổi làm ứng dụng truy vấn **một byte key khác**, biểu hiện như cache miss chứ không nhất thiết ném exception.
6. Một producer ghi payload sai encoding hoặc dữ liệu byte không còn khớp với hợp đồng schema.
7. Jackson/ObjectMapper thiếu module cho một kiểu dữ liệu chuyên biệt, hoặc cấu hình polymorphic type không tương thích.

Với nhiều serializer Spring Data Redis, lỗi có thể được biểu diễn bằng `org.springframework.data.redis.serializer.SerializationException`, có cause từ Jackson, Java serialization hoặc bộ mã hóa khác. Nếu code service tự parse JSON ngoài RedisTemplate, ngoại lệ có thể là loại của thư viện JSON, không nhất thiết thuộc Spring Data Redis.

### 7.1. Key serializer và value serializer là hai quyết định riêng

Một cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

@Bean
RedisTemplate<String, Object> jsonRedisTemplate(
        RedisConnectionFactory factory) {
    RedisTemplate<String, Object> template = new RedisTemplate<>();
    template.setConnectionFactory(factory);
    template.setKeySerializer(new StringRedisSerializer());
    template.setHashKeySerializer(new StringRedisSerializer());
    template.setValueSerializer(
        new GenericJackson2JsonRedisSerializer()
    );
    template.setHashValueSerializer(
        new GenericJackson2JsonRedisSerializer()
    );
    template.afterPropertiesSet();
    return template;
}
~~~

Ví dụ dùng JSON serializer để minh họa định dạng key/value; với môi trường production cần chọn cách lưu metadata type, allowlist các kiểu dữ liệu, namespace version và chính sách migration phù hợp. Không bật cơ chế deserialize kiểu tùy ý đối với payload đến từ nguồn không tin cậy.

Đừng dùng cấu hình JSON mới để đọc tùy ý hàng triệu key cũ từng được lưu dạng JDK serialization mà không có kế hoạch chuyển đổi. Redis **không biết schema Java**, nên tương thích dữ liệu là trách nhiệm của ứng dụng.

### 7.2. Ví dụ xử lý cache value không đọc được

Nếu Redis chỉ là cache có thể làm mới từ database, có thể chọn một chiến lược cụ thể:

~~~text
GET cache:user:v2:42
        |
        v
Redis trả bytes
        |
        +-- Decode OK → dùng dữ liệu
        |
        +-- SerializationException
                   |
                   v
          Ghi metric + log mã key an toàn
                   |
                   v
          Xác định đây có phải cache
          có thể tái tạo hoàn toàn?
                /          \
              Có            Không
               |              |
               v              v
       Loại bỏ key hỏng    Báo lỗi và xử lý
       có kiểm soát        migration/incident
               |
               v
        Tải dữ liệu nguồn và cache lại
~~~

Không nên tự động xóa mọi key ngay khi gặp deserialization error. Với Redis là **nguồn dữ liệu chính** hoặc payload cần được điều tra, xóa key có thể gây mất bằng chứng hoặc dữ liệu không thể tái tạo. Cần phân biệt cache best-effort và persistent business state.

### 7.3. Migration bằng namespace theo version

Một cách giảm va chạm giữa schema cũ/mới:

~~~text
cache:user:v1:42   ← JSON format cũ
cache:user:v2:42   ← JSON format mới
~~~

Khi chuyển đổi:

1. Ứng dụng mới đọc/ghi `v2` theo serializer nhất quán.
2. Nếu cần migration, một job riêng đọc `v1` bằng serializer cũ rồi chuyển có kiểm soát sang `v2`.
3. Dùng TTL hoặc chính sách xóa sau khi xác nhận không còn consumer của `v1`.
4. Giám sát số deserialize errors và cache miss để phát hiện ảnh hưởng sau triển khai.

Đối với dữ liệu cache, namespace version thường đơn giản hơn cố đọc cả hai định dạng trên cùng một key. Với dữ liệu business quan trọng, migration cần thêm đối soát và tính toàn vẹn.

## 8. Phân loại lỗi ở tầng ứng dụng bằng cause chain

Không phải mọi ứng dụng đều cần một hệ thống phân loại phức tạp. Nhưng với service có yêu cầu retry, fallback và metric khác nhau, một class nhỏ giúp việc xử lý nhất quán hơn thay vì so sánh chuỗi error message trong từng method.

Ví dụ dưới dùng Spring Data Redis và **Lettuce**. Nếu dự án dùng Jedis, cần thay phần nhận diện driver-specific bằng các loại exception tương ứng; phần `DataAccessException` của Spring vẫn có ích.

~~~java
package com.example.redis.error;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import io.lettuce.core.RedisCommandExecutionException;
import io.lettuce.core.RedisCommandTimeoutException;
import io.lettuce.core.RedisConnectionException;
import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Component;

@Component
public final class RedisFailureClassifier {

    public enum Kind {
        CONNECTION,
        TIMEOUT,
        COMMAND,
        SERIALIZATION,
        UNKNOWN
    }

    public Kind classify(Throwable error) {
        if (hasCause(error, SerializationException.class)) {
            return Kind.SERIALIZATION;
        }
        if (hasCause(error, QueryTimeoutException.class)
                || hasCause(
                    error, RedisCommandTimeoutException.class)) {
            return Kind.TIMEOUT;
        }
        if (hasCause(error, RedisConnectionFailureException.class)
                || hasCause(error, RedisConnectionException.class)) {
            return Kind.CONNECTION;
        }
        if (hasCause(
                    error, RedisCommandExecutionException.class)
                || hasCause(
                    error, InvalidDataAccessApiUsageException.class)) {
            return Kind.COMMAND;
        }
        return Kind.UNKNOWN;
    }

    private static boolean hasCause(
            Throwable error, Class<? extends Throwable> type) {
        Set<Throwable> visited = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );

        for (Throwable current = error;
             current != null && visited.add(current);
             current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

### Những điều class này cố tình không làm

- Không coi **mọi** `RedisSystemException` là lỗi command: lớp này có thể bọc nhiều tình huống cần quan sát cause.
- Không coi **mọi** `RuntimeException` là lỗi Redis: `NullPointerException` do code ứng dụng sai không phải Redis timeout.
- Không tự động retry theo `Kind`: bản chất lỗi và **loại operation** đều quan trọng.
- Không phân biệt mọi lỗi TLS/DNS/pool theo subtype: để làm việc đó cần thêm context kết nối và logs của driver/hạ tầng.
- Không cố phát hiện lỗi JSON do business code tự gọi ObjectMapper khi exception không thuộc serializer của Spring; tầng thực hiện JSON parse cần có chính sách phân loại riêng.
- Không sử dụng error message như hợp đồng API ổn định; khi cần nhận diện `WRONGTYPE`/`NOPERM` ở tầng command, có thể trích mã lỗi sau khi xác định `RedisCommandExecutionException`.

Việc dùng `IdentityHashMap` trong `hasCause` tránh một vòng lặp vô hạn nếu một exception bất thường có cause chain tham chiếu lại chính nó. Đây chỉ là tiện ích đọc exception, không thay đổi hay nuốt lỗi.

### Timeout ở giai đoạn connect hay command?

Nếu một exception từ driver cho biết kết nối thất bại kèm nguyên nhân timeout, cách phân loại tự động có thể không đủ để biết **thời điểm** hỏng. Vì vậy, log cần có `operation=connect` hoặc `operation=GET`, tên cache/service, timeout đã cấu hình và endpoint/topology được ẩn thông tin nhạy cảm.

Không nên ra quyết định retry một lệnh ghi chỉ vì bộ phân loại trả `TIMEOUT`. Một lệnh có thể đã hoàn thành trước khi response bị mất.

## 9. Chính sách xử lý theo loại thao tác và độ quan trọng dữ liệu

**Phân loại exception** và **ra quyết định nghiệp vụ** là hai bước khác nhau.

Ví dụ Redis đang giữ cache sản phẩm:

- Connection failure: có thể đọc thẳng database nếu cache là best-effort.
- Command timeout: có thể fallback, nhưng cần hạn chế lượng request đổ xuống database.
- `WRONGTYPE`: cần sửa key naming/schema, không retry mãi.
- Serialization error: có thể sửa/migrate key cache, nhưng không được xóa dữ liệu nghiệp vụ quan trọng một cách âm thầm.

Ví dụ Redis đang giữ một bộ đếm đơn hàng dùng làm nguồn sự thật:

- Connection error: không có giá trị tin cậy để trả.
- Command timeout khi gửi `INCR`: không biết counter đã tăng chưa.
- Sai kiểu key: lỗi schema cần can thiệp, không tự reset counter.
- Serialization error: phải bảo vệ dữ liệu và điều tra, không coi như key trống.

Một bảng policy:

| Loại dữ liệu | CONNECTION / TIMEOUT | COMMAND | SERIALIZATION |
| --- | --- | --- | --- |
| Cache có thể tái tạo | Có thể fallback có giới hạn và ghi metric | Điều tra schema/role; chỉ fallback nếu được phép | Cân nhắc evict key hỏng có kiểm soát |
| Session/authentication | Cần fail-safe theo chính sách bảo mật; tránh tự cấp quyền khi Redis lỗi | Kiểm tra ACL, role và key schema | Không coi decode lỗi là session hợp lệ |
| Counter/ledger nghiệp vụ | Có thể phải báo kết quả chưa xác định và đối soát | Dừng thao tác sai thay vì tự sửa dữ liệu | Bảo toàn dữ liệu, sửa migration |
| Distributed lock | Không được xem timeout là “chắc chắn chưa lấy khóa” | Kiểm tra primary/ACL/script | Token encoding phải nhất quán |
| Queue/Stream consumer | Giữ trạng thái retry/ACK theo contract; không ACK mù | Điều tra group, key type, ACL, slot | Không ACK message chưa xử lý được |

Không có một fallback chung đúng cho mọi Redis usage. Có ứng dụng Redis là **cache có thể mất**, có ứng dụng Redis lại là **cấu phần quan trọng để điều phối**. Policy cần dựa trên yêu cầu bảo toàn dữ liệu và tính đúng đắn nghiệp vụ.

## 10. Xử lý lỗi trong service đồng bộ

Ví dụ một service cache-aside dùng `StringRedisTemplate`. Nếu Redis không truy cập được hoặc timeout, nó tải dữ liệu từ nguồn gốc. Nếu lỗi command hoặc serialization xảy ra, service **không che lỗi bằng một cache miss giả**:

~~~java
package com.example.redis.error;

import java.util.Objects;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
        LoggerFactory.getLogger(ProductReadService.class);

    private final StringRedisTemplate redis;

    public ProductReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getOrLoad(
            String id, Supplier<String> loadFromDatabase) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(loadFromDatabase);

        String key = "cache:product:v2:" + id;

        try {
            String hit = redis.opsForValue().get(key);
            if (hit != null) {
                return hit;
            }
        } catch (RedisConnectionFailureException
                 | QueryTimeoutException error) {
            log.warn(
                "Redis cache unavailable for product lookup, type={}",
                error.getClass().getSimpleName()
            );
            // Redis là cache best-effort, không phải nguồn chính.
        }

        return Objects.requireNonNull(loadFromDatabase.get());
    }
}
~~~

Ví dụ cố ý chỉ **đọc cache** và fallback, chưa ghi lại cache. Nếu cần ghi cache sau khi tải dữ liệu, hãy bao riêng lỗi ghi Redis để tránh một sự cố cache làm mất phản hồi thành công của database, nhưng **chỉ** trong nghiệp vụ cho phép cache best-effort.

### Vì sao không viết `catch (Exception)`?

~~~java
// Anti-pattern: che cả lỗi lập trình hoặc dữ liệu.
try {
    return redis.opsForValue().get(key);
} catch (Exception error) {
    return database.get(key);
}
~~~

Đoạn này có thể che lỗi schema, `WRONGTYPE`, null pointer do code, serializer không tương thích hoặc Redis ACL sai. Khi lỗi kéo dài, database có thể chịu toàn bộ tải mà không ai biết cache đã hỏng vì nguyên nhân cần sửa.

Mặt khác, chỉ bắt hai loại exception ở ví dụ trên không bao phủ mọi driver/version. Trong ứng dụng nhiều loại lỗi, có thể dùng `RedisFailureClassifier` ở lớp adapter riêng và chỉ fallback cho những `Kind` được phép, sau khi đã kiểm chứng cách driver translate lỗi của hệ thống thật. **Không nên mở rộng catch một cách mù quáng** chỉ vì muốn mọi lỗi đều “được xử lý”.

### Lỗi xảy ra khi ghi: đừng làm mất kết quả của nguồn chính

Giả sử một request đã cập nhật database thành công rồi ghi cache:

~~~java
database.updateProduct(product);
redis.opsForValue().set(cacheKey, serializedProduct);
~~~

Nếu Redis timeout, response HTTP có thể thất bại dù database đã commit. Client retry cả HTTP request có thể tạo side effect trùng, tùy nghiệp vụ. Cần xác định **database commit và cache write là hai tài nguyên độc lập**:

- Với cache-aside có thể vô hiệu hóa cache hoặc ghi lại best-effort sau commit.
- Có thể dùng outbox/event để cập nhật cache bất đồng bộ nếu yêu cầu nhất quán cần cơ chế bền vững.
- Không coi thao tác `set` vào Redis là một phần tự động rollback cùng JDBC transaction chỉ vì chúng nằm trong cùng Java method.

## 11. Lỗi trong Reactive Redis: error, empty và timeout của Reactor

API `ReactiveStringRedisTemplate` trả `Mono`/`Flux`. Exception được phát dưới dạng tín hiệu `onError` khi publisher được subscribe, thay vì nhất thiết ném ngay tại thời điểm tạo publisher.

Ví dụ:

~~~java
Mono<String> cached =
    reactiveRedis.opsForValue().get("cache:product:42");
~~~

Tại thời điểm gán `cached`, Redis chưa nhất thiết được truy cập. Nếu API reactive trả `Mono.empty()` khi key không tồn tại, đó **không phải** `onError`. Các operator cần phân biệt:

| Kết quả | Ý nghĩa | Operator thích hợp |
| --- | --- | --- |
| `onNext(value)` | Key có giá trị | `map`, `flatMap` |
| `onComplete` không có `onNext` | Key không tồn tại | `switchIfEmpty` hoặc `defaultIfEmpty` |
| `onError(connectionError)` | Không truy cập được Redis | `onErrorResume` theo policy |
| `onError(timeoutError)` | Tác vụ vượt timeout | Cân nhắc deadline, retry/fallback |
| `onError(serializationError)` | Không giải mã được dữ liệu | Báo lỗi/migration có kiểm soát |

### 11.1. Fallback chỉ cho lỗi được chấp nhận

Ví dụ một service reactive đọc cache, nguồn dữ liệu chính là JDBC đồng bộ. Phần JDBC được đưa tới `Schedulers.boundedElastic()` để không chặn event-loop:

~~~java
package com.example.redis.error;

import java.util.Objects;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReactiveProductReadService {

    private final ReactiveStringRedisTemplate redis;
    private final RedisFailureClassifier classifier;
    private final ProductDatabaseReader database;

    public ReactiveProductReadService(
            ReactiveStringRedisTemplate redis,
            RedisFailureClassifier classifier,
            ProductDatabaseReader database) {
        this.redis = redis;
        this.classifier = classifier;
        this.database = database;
    }

    public Mono<String> load(String id) {
        Objects.requireNonNull(id);
        String key = "cache:product:v2:" + id;

        Mono<String> source = Mono.fromCallable(
                () -> database.loadProductJson(id)
            )
            .subscribeOn(Schedulers.boundedElastic());

        return redis.opsForValue()
            .get(key)
            .onErrorResume(error -> {
                RedisFailureClassifier.Kind kind =
                    classifier.classify(error);

                if (kind == RedisFailureClassifier.Kind.CONNECTION
                        || kind == RedisFailureClassifier.Kind.TIMEOUT) {
                    return source;
                }
                return Mono.error(error);
            })
            .switchIfEmpty(source);
    }
}
~~~

`ProductDatabaseReader` ở ví dụ là interface/service nghiệp vụ có method `String loadProductJson(String id)`, không phải API có sẵn trong Spring Data Redis. Nếu method này trả `null`, `Mono.fromCallable` sẽ complete rỗng; hợp đồng service nên quy định rõ dữ liệu không tồn tại thay vì tùy tiện coi đó là lỗi Redis.

Hai nhánh `onErrorResume` và `switchIfEmpty` chỉ subscribe `source` khi cần. Mặc dù được khai báo ở biến, `Mono.fromCallable` là publisher lạnh: việc gọi database được hoãn tới thời điểm subscription.

Đoạn code không tự ghi lại Redis sau fallback. Nếu muốn bổ sung cache write, cần xem đó là bước best-effort hoặc có policy riêng, không dùng `then` làm mất giá trị dữ liệu khi chưa muốn.

### 11.2. Timeout của Reactor không nhất thiết là Redis command timeout

~~~java
Mono<String> value = reactiveRedis.opsForValue()
    .get("cache:key")
    .timeout(java.time.Duration.ofMillis(800));
~~~

`Mono.timeout(...)` đặt deadline tại tầng **Reactor pipeline**. Khi hết deadline, Reactor có thể phát `java.util.concurrent.TimeoutException`. Đây không nhất thiết là `RedisCommandTimeoutException` của Lettuce hoặc `QueryTimeoutException` của Spring.

Hai loại timeout có thể khác nhau:

~~~text
Lettuce command timeout = 3 giây
Reactor Mono.timeout   = 800 mili giây

T0      Subscriber bắt đầu GET
T0+800  Reactor ngừng chờ và phát TimeoutException
T0+...  Command phía Redis có thể vẫn đã chạy
~~~

Huỷ subscription hoặc phát timeout ở HTTP layer **không có bảo đảm rollback** cho lệnh đã được gửi. Đặc biệt, khi thực hiện một lệnh ghi như `INCR` hoặc `XADD`, không retry một cách mù quáng chỉ vì Reactor timeout.

Nếu ứng dụng muốn coi timeout Reactor như một loại deadline riêng, bổ sung `java.util.concurrent.TimeoutException` vào bộ phân loại với tên rõ như `APPLICATION_TIMEOUT`, thay vì gộp mọi ngữ cảnh vào Redis command timeout.

### 11.3. Retry reactive có bộ lọc theo loại thao tác

Với một thao tác **đọc cache**, có thể áp dụng một số lượt retry có backoff:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<String> read = reactiveRedis.opsForValue()
    .get("cache:product:v2:42")
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(80))
            .maxBackoff(Duration.ofMillis(400))
            .filter(error -> {
                var kind = classifier.classify(error);
                return kind == RedisFailureClassifier.Kind.CONNECTION
                    || kind == RedisFailureClassifier.Kind.TIMEOUT;
            })
    )
    .switchIfEmpty(Mono.just("(missing)"));
~~~

`Retry.backoff(2, ...)` cho phép tối đa hai lần retry **sau lần thử ban đầu**. Nó có jitter/backoff và không retry lỗi command/serialization theo classifier. Nếu các lần thử đều thất bại, luồng tiếp tục phát lỗi; service có thể bổ sung fallback ngoài `retryWhen` nếu nghiệp vụ cho phép.

Mẫu này phù hợp hơn với `GET` có side effect thấp. Đừng sao chép y nguyên cho `INCR`, `LPUSH` hoặc `XADD` không có bảo vệ idempotency.

Trong WebFlux Controller, nên **trả `Mono` cho framework** để framework subscribe; tránh gọi `block()` trên event-loop hoặc `subscribe()` thủ công rồi tách lỗi ra khỏi vòng đời HTTP request.

## 12. Tái thử: loại command quan trọng hơn tên exception

Giả sử mỗi timeout được phân loại là `TIMEOUT`. Ta vẫn không thể áp dụng một policy retry chung cho các command:

| Operation | Retry khi mất phản hồi | Lý do |
| --- | --- | --- |
| `GET key` | Thường có thể retry hữu hạn | Đọc lại không tự tăng/ghi trạng thái, nhưng kết quả có thể đã đổi |
| `EXISTS key` | Thường có thể retry | Trạng thái key có thể đổi giữa các lượt |
| `SET key value` | Chỉ an toàn theo điều kiện | Ghi cùng giá trị có thể idempotent nhưng vẫn ảnh hưởng TTL/ghi đè thay đổi mới hơn |
| `DEL key` | Thường ổn nếu mục tiêu là xóa key | Số lượng key xóa trả về có thể khác |
| `SADD key member` | Lũy đẳng theo membership | Kết quả số phần tử mới thêm có thể khác |
| `INCR` / `DECR` | Không retry mù | Lệnh đầu có thể đã thay đổi counter |
| `LPUSH` / `RPUSH` | Không retry mù | Có thể tạo phần tử trùng |
| `XADD stream * ...` | Không retry mù | Có thể tạo entry khác Stream ID cho cùng event logic |
| `SET key token NX PX ttl` | Cần policy khóa riêng | Timeout có thể xảy ra sau khi khóa đã được tạo |
| `MULTI/EXEC` | Cần đối soát nghiệp vụ | Connection timeout có thể xảy ra tại ranh giới kết quả không xác định |
| Lua có side effect | Phụ thuộc nội dung script | Lua atomic về thực thi script, không tự có retry idempotency |

### Idempotency key cho nghiệp vụ

Với thao tác “ghi nhận một sự kiện đã xử lý”, một `eventId` ổn định qua retry và ràng buộc duy nhất tại nơi lưu side effect có thể ngăn áp dụng trùng.

~~~text
eventId = evt-2001
      |
      +--> Redis command timeout
      |
      +--> Worker thử lại
               |
               v
        Kiểm tra eventId ở nơi cập nhật nghiệp vụ
               |
         +-----+------+
         |            |
       Đã xử lý    Chưa xử lý
         |            |
         v            v
       Bỏ qua     Áp dụng + ghi marker nguyên tử
~~~

Nếu marker idempotency nằm ở Redis còn side effect nằm ở PostgreSQL, hai thao tác không tự atomically commit cùng nhau. Với nghiệp vụ quan trọng, hãy đặt marker cùng transaction với side effect trong database, hoặc dùng một giao thức/outbox phù hợp.

Không nên xem “đã gửi lại thành công” là chứng minh lần gửi đầu chắc chắn không chạy. Đây là lý do policy retry phải được review theo từng **semantic operation**, không chỉ theo class exception.

## 13. Tách tín hiệu kết quả bình thường khỏi tín hiệu lỗi

Không phải mọi kết quả “không được như kỳ vọng” đều là exception. Redis trả nhiều giá trị có ngữ nghĩa bình thường nhưng ứng dụng dễ hiểu nhầm:

| API / lệnh | Kết quả | Ý nghĩa thường gặp |
| --- | --- | --- |
| `opsForValue().get(missingKey)` | `null` trong API đồng bộ | Key không tồn tại |
| Reactive `get(missingKey)` | `Mono.empty()` | Không có giá trị để phát |
| `setIfAbsent(key, value)` | `Boolean.FALSE` | Key đã tồn tại, điều kiện `NX` không được thỏa |
| `delete(key)` | `0` | Không xóa được key nào, có thể key đã vắng mặt |
| `getExpire(key)` | `-1` | Key tồn tại nhưng không có TTL |
| `getExpire(key)` | `-2` | Key không tồn tại |
| `convertAndSend(channel, payload)` | Có thể trả `0` | Không có subscriber theo ngữ nghĩa publish; không phải lệnh lỗi |
| Redis List `pop` trên list trống | Giá trị vắng mặt | Không có phần tử để lấy |

Ví dụ một phân nhánh đúng cho khóa phân tán:

~~~java
Boolean acquired = redis.opsForValue().setIfAbsent(
    "lock:job:daily",
    "owner-token",
    java.time.Duration.ofSeconds(30)
);

if (Boolean.TRUE.equals(acquired)) {
    // Lấy khóa thành công.
} else if (Boolean.FALSE.equals(acquired)) {
    // Khóa có người sở hữu; đây là trạng thái cạnh tranh bình thường.
} else {
    // Trong một số chế độ thực thi đặc biệt như pipeline/transaction,
    // API có thể chưa cung cấp kết quả ngay.
    // Không tự xem null là đã lấy được khóa.
}
~~~

Mã trên chỉ minh họa cách phân biệt kết quả; lock thực tế còn cần owner token riêng cho từng lần acquire và giải phóng có kiểm tra token. Khi dùng pipeline hoặc transaction, cách giải thích `null` phải tuân theo hợp đồng API tương ứng, không dùng cùng logic như một lời gọi trực tiếp bình thường.

Một lỗi khác là phân loại bất kỳ `Mono.empty()` nào thành “Redis down”. Khi `GET` không có dữ liệu, publisher complete bình thường; `onErrorResume` không chạy. Nếu cần tải dữ liệu thay thế:

~~~java
Mono<String> value = reactiveRedis.opsForValue()
    .get("cache:product:42")
    .switchIfEmpty(Mono.defer(() -> loadFromDatabaseReactive("42")));
~~~

`loadFromDatabaseReactive` là phương thức nghiệp vụ minh họa trả `Mono<String>`. `Mono.defer` hoãn việc tạo publisher nguồn dự phòng cho đến khi upstream thực sự empty; nếu Redis lỗi, lỗi vẫn đi qua `onError` trừ khi được xử lý riêng.

## 14. Chẩn đoán bằng Redis CLI và metrics có kiểm soát

Khi sự cố xảy ra, hãy thu thập bằng chứng theo chiều từ application tới Redis thay vì thử ngẫu nhiên các lệnh thay đổi dữ liệu. Một số lệnh **chỉ đọc thông tin** hữu ích:

~~~bash
# Kiểm tra Redis instance có phản hồi:
redis-cli -h redis.internal -p 6379 PING

# Trạng thái server và client:
redis-cli -h redis.internal -p 6379 INFO server
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO memory

# Thông tin về lệnh và độ trễ:
redis-cli -h redis.internal -p 6379 INFO commandstats
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
redis-cli -h redis.internal -p 6379 LATENCY LATEST
~~~

Các lệnh trên cần quyền phù hợp. `SLOWLOG GET` có thể chứa thông tin liên quan command hoặc tham số; phải giới hạn người được xem kết quả và tránh đưa dữ liệu nhạy cảm vào log/ticket công khai. Không chạy `MONITOR` liên tục trên production vì nó có thể tạo overhead lớn và phơi bày command payload.

Đối với một key test hoặc key đã được phép điều tra:

~~~redis
TYPE cache:product:v2:42
TTL cache:product:v2:42
PTTL cache:product:v2:42
EXISTS cache:product:v2:42
~~~

`TYPE` giúp chẩn đoán `WRONGTYPE`. `TTL` và `PTTL` giúp chẩn đoán key không có thời hạn hoặc đã hết hạn. `EXISTS` chỉ là snapshot tại thời điểm lệnh chạy; key có thể đổi ngay sau đó.

### Quan sát chỉ số nào cho từng nhóm lỗi?

| Nhóm | Metric/log cần xem | Câu hỏi |
| --- | --- | --- |
| Kết nối | Connection failures, reconnects, TCP resets, DNS/TLS errors | Có lỗi ở network, driver hay Redis server? |
| Timeout | Command latency p50/p95/p99, queue depth, pool wait, timeout rate | Tắc ở kết nối, command, queue hay toàn request? |
| Lệnh | Redis error code, command family, key namespace, Redis role/ACL | Lệnh có sai kiểu, quyền hoặc topology? |
| Serializer | Decode failure count, schema version, serializer ID, payload source | Hai component có cùng hợp đồng bytes/schema không? |

Các metric phía ứng dụng còn cần phân loại theo **tên tính năng/cache và loại thao tác**, không chỉ nhìn tổng số lỗi Redis. Nếu `GET` cache timeout tăng nhưng `SET` của queue vẫn bình thường, nguyên nhân có thể tập trung ở workload đọc lớn hoặc cách xây dựng pipeline.

### Có nên xem trực tiếp dữ liệu key?

Chỉ khi có quyền và dữ liệu không nhạy cảm. Nhiều value Redis chứa session, access token, dữ liệu người dùng, hoặc byte payload không thể in an toàn. Khi cần điều tra serializer, nên tạo một **key thử nghiệm** với payload không nhạy cảm, hoặc ghi lại schema version/hash và metadata đã được redaction thay vì dump toàn bộ value.

## 15. Log và metric có thể hành động được

Một thông báo “Redis error” không đủ để phân biệt bốn nhóm lỗi. Mỗi record nên có thông tin tối thiểu:

- `failure_kind`: connection, timeout, command, serialization, unknown.
- `operation`: GET, SET, HGET, XREADGROUP, EVAL... hoặc command family.
- `cache_name` / `module` / `feature`: khu vực nghiệp vụ.
- `key_namespace`: ví dụ `cache:product:v2`, **không phải mọi ID cá nhân**.
- `driver`, `redis_mode`: Lettuce/Jedis, standalone/Sentinel/Cluster.
- `elapsed_ms`, timeout configured, attempt index và result.
- Correlation ID hoặc trace ID để ghép với HTTP/job logs.
- Exception class ngoài cùng và nguyên nhân thấp nhất phù hợp; stack trace khi cần.

Ví dụ log theo cách không in payload:

~~~java
RedisFailureClassifier.Kind kind =
    classifier.classify(error);

log.warn(
    "Redis failure kind={} operation={} cache={} elapsedMs={} exception={}",
    kind,
    "GET",
    "product-v2",
    elapsedMs,
    error.getClass().getSimpleName(),
    error
);
~~~

Biến `log` đại diện cho SLF4J logger đã khai báo, `elapsedMs` là thời gian đo trong service. Bản ghi không đưa toàn bộ key chứa user ID hoặc value có dữ liệu cá nhân vào message. Nếu stack trace có thể chứa Redis URI/credential trong một driver/version cụ thể, cần redaction và chính sách lưu log.

Với Micrometer có thể theo dõi:

~~~text
redis.operation.failures{kind="timeout",operation="GET",cache="product"}
redis.operation.duration{operation="GET",cache="product"}
redis.fallback.count{reason="connection",cache="product"}
redis.retry.attempts{operation="GET",outcome="exhausted"}
redis.serialization.failures{cache="product",schema="v2"}
~~~

Đây là tên metric minh họa; chúng không tự xuất hiện chỉ vì có Spring Data Redis. Ứng dụng hoặc hệ thống quan sát phải instrument chúng. Không tạo nhãn theo key ID hoặc exception message nguyên văn vì cardinality và lượng dữ liệu nhạy cảm có thể tăng không kiểm soát.

### Cần biết thời gian thực thi không luôn bằng thời gian Redis xử lý

Một `elapsedMs` đo từ service có thể bao gồm serialization, chờ pool/connection, command queue, network và deserialization. Nó không nhất thiết phản ánh thời gian Redis server trực tiếp xử lý command.

Khi phân tích timeout, hãy so sánh:

1. Latency từ ứng dụng nhìn thấy.
2. Redis slow log/latency event.
3. Driver queue hoặc pool wait nếu có metric.
4. Network latency và packet loss.
5. Kích thước payload request/response.

Nếu server slow log không cho thấy command chậm nhưng application timeout tăng, cần kiểm tra những giai đoạn **ngoài thời gian CPU thực thi command trên Redis**.

## 16. Kiểm thử phân loại lỗi và hành vi với Redis thật

Để kiểm thử bộ phân loại, nên tách:

- **Unit test**: tạo exception có kiểu xác định và kiểm tra classifier, không cần Redis.
- **Integration test**: sử dụng Redis thật để phát sinh lỗi lệnh hoặc test cache miss; không mock Redis server nếu muốn kiểm tra command semantics.
- **Fault-injection test có kiểm soát**: gây network timeout, ngắt kết nối, failover bằng hạ tầng riêng khi cần; tránh chạy trên Redis dùng chung.

### 16.1. Unit test bộ phân loại

~~~java
package com.example.redis.error;

import io.lettuce.core.RedisCommandExecutionException;
import io.lettuce.core.RedisCommandTimeoutException;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.serializer.SerializationException;

import static org.assertj.core.api.Assertions.assertThat;

class RedisFailureClassifierTest {

    private final RedisFailureClassifier classifier =
        new RedisFailureClassifier();

    @Test
    void classifiesConnectionFailure() {
        assertThat(classifier.classify(
            new RedisConnectionFailureException("connection refused")
        )).isEqualTo(
            RedisFailureClassifier.Kind.CONNECTION
        );
    }

    @Test
    void classifiesNestedCommandTimeout() {
        RuntimeException wrapped = new IllegalStateException(
            "redis operation failed",
            new RedisCommandTimeoutException("command timed out")
        );

        assertThat(classifier.classify(wrapped)).isEqualTo(
            RedisFailureClassifier.Kind.TIMEOUT
        );
    }

    @Test
    void classifiesWrongTypeCommandError() {
        RuntimeException wrapped = new IllegalStateException(
            "redis operation failed",
            new RedisCommandExecutionException(
                "WRONGTYPE Operation against a key"
            )
        );

        assertThat(classifier.classify(wrapped)).isEqualTo(
            RedisFailureClassifier.Kind.COMMAND
        );
    }

    @Test
    void classifiesSerializationFailure() {
        assertThat(classifier.classify(
            new SerializationException("invalid serialized value")
        )).isEqualTo(
            RedisFailureClassifier.Kind.SERIALIZATION
        );
    }

    @Test
    void unknownErrorIsNotAutomaticallyRedisFailure() {
        assertThat(classifier.classify(
            new IllegalStateException("business rule violation")
        )).isEqualTo(
            RedisFailureClassifier.Kind.UNKNOWN
        );
    }
}
~~~

Những unit test trên kiểm tra trực tiếp luật phân loại kiểu/cause, **không chứng minh** Spring Data Redis sẽ dịch mọi lỗi server trong mọi phiên bản sang chính xác một class.

### 16.2. Integration test `WRONGTYPE` và cache miss

Dependencies Gradle Groovy (Spring Boot quản lý các phiên bản tương thích):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Ví dụ với Redis 7.2 trong Testcontainers:

~~~java
package com.example.redis.error;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(classes = RedisErrorIntegrationTest.TestApp.class)
class RedisErrorIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void missingKeyIsNotAnException() {
        String key = "it:missing:" + UUID.randomUUID();

        assertThat(redis.opsForValue().get(key)).isNull();
    }

    @Test
    void wrongTypeIsACommandFailure() {
        String key = "it:wrongtype:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "plain-string");

            assertThatThrownBy(
                () -> redis.opsForList().size(key)
            ).isInstanceOf(RuntimeException.class);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Trong test thứ hai, key đã được lưu dưới dạng Redis String; lệnh tính độ dài List không phù hợp nên Redis sẽ trả lỗi command. Assertion chỉ kiểm tra exception runtime ở tầng ứng dụng vì subtype có thể khác theo translator/driver. Muốn kiểm chứng classifier trên cấu hình thực tế, có thể bắt exception và kiểm tra `RedisFailureClassifier` cùng cause trong đúng version dự án sử dụng.

Test không chạy `FLUSHDB`/`FLUSHALL`, chỉ dọn key có UUID riêng. Máy chạy test cần Docker hoặc môi trường container tương thích.

### 16.3. Kiểm thử lỗi serializer mà không cần Redis server

Nếu muốn chứng minh Java deserializer từ chối payload sai format, có thể thử trực tiếp:

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SerializerFailureTest {

    @Test
    void rejectsBytesThatAreNotJavaSerializedObject() {
        byte[] jsonBytes = """
            {"id":42,"name":"Example"}
            """.getBytes(StandardCharsets.UTF_8);

        JdkSerializationRedisSerializer serializer =
            new JdkSerializationRedisSerializer();

        assertThatThrownBy(() -> serializer.deserialize(jsonBytes))
            .isInstanceOf(SerializationException.class);
    }
}
~~~

Test này xác nhận sự khác nhau giữa byte JSON và Java object serialization, không khuyên dùng JDK serialization để lưu dữ liệu từ nguồn không tin cậy. Với hệ thống thật, nên chọn serializer có hợp đồng schema/version rõ ràng và kiểm soát được kiểu dữ liệu.

### 16.4. Không nên tạo timeout bằng `Thread.sleep` trong test

Một unit test không thể chứng minh lệnh Redis đã timeout ở network/driver chỉ bằng cách `Thread.sleep` trong Java. Nếu cần thử lỗi kết nối và command timeout:

- Dùng một Redis test độc lập và công cụ proxy/network fault injection (ví dụ Toxiproxy) với điều kiện kiểm soát.
- Đặt connect timeout/command timeout phù hợp với kịch bản.
- Giả lập mất kết nối hoặc delay có giới hạn để kiểm tra nhánh retry/fallback.
- Dùng polling với timeout để xác nhận trạng thái phục hồi, tránh kết luận từ đúng một thời điểm chờ cứng.
- Với các lệnh ghi, xác minh trạng thái nghiệp vụ sau timeout; không mặc định command chắc chắn chưa chạy.

Không thực hiện những thao tác cố tình chặn Redis hoặc gây failover trên server production chỉ để tái hiện lỗi học tập.

## 17. Quy trình xử lý sự cố trong production

Khi một cảnh báo Redis xuất hiện, nên đi theo một quy trình có thể lặp lại thay vì thử sửa nhiều tham số cùng lúc.

### Bước 1 — Xác định phạm vi và mức ảnh hưởng

- Lỗi chỉ xuất hiện ở một chức năng hay toàn bộ request liên quan Redis?
- Chỉ một pod bị lỗi hay mọi instance?
- Chỉ có thao tác `GET`, hay cả `SET`, `EVAL`, `XREADGROUP`?
- Sự cố bắt đầu sau deploy, Redis failover, đổi ACL hoặc đổi cấu hình serializer không?
- Redis là cache phụ trợ hay nơi lưu dữ liệu/khóa điều phối quan trọng?

Phạm vi sự cố giúp xác định hành động cần ưu tiên. Một lỗi decode chỉ xảy ra với key namespace `cache:user:v1` ngay sau deploy thường khác bản chất với lỗi connection trên mọi lệnh sau khi Redis primary bị restart.

### Bước 2 — Phân loại theo bằng chứng

~~~text
                    Có Redis failure
                           |
                           v
              Kiểm tra exception/cause
                           |
          +----------------+-----------------+
          |                |                 |
          v                v                 v
      Connection        Timeout         Command error
          |                |                 |
          v                v                 v
     DNS/TCP/TLS/     Lệnh nào?       WRONGTYPE/ACL/
     server/role?     chờ ở đâu?     READONLY/CROSSSLOT?
          |                |                 |
          +--------+-------+--------+--------+
                   |                |
                   v                v
         Xem log/metrics       Có được retry?
                   |
                   v
          Nếu byte decode lỗi
                   |
                   v
         Serialization/schema/serializer
~~~

Nếu không xác định được nhóm từ exception type và cause, ghi nhận **UNKNOWN** và bổ sung bằng chứng. Không tự xếp một lỗi lạ vào connection rồi retry vô hạn.

### Bước 3 — Chẩn đoán đúng tầng

**Với connection:**

1. Từ chính nơi ứng dụng chạy, kiểm tra DNS, route, TCP/TLS, Redis endpoint và credential.
2. Nếu dùng Sentinel/Cluster, hỏi đúng topology và role hiện tại.
3. Quan sát Redis client count, connection resets và driver reconnect.
4. Xác định có failover/deploy/network policy change ngay thời điểm lỗi không.

**Với timeout:**

1. Xác định connect timeout, command timeout, pool wait hay application deadline.
2. Đo p95/p99 latency, queue depth, payload size và số request đồng thời.
3. So sánh latency phía ứng dụng với `SLOWLOG`/`LATENCY` từ server.
4. Đánh giá tác động của retry trên từng command, nhất là lệnh ghi không lũy đẳng.

**Với command:**

1. Lấy Redis error code và command family.
2. Kiểm tra `TYPE` của key test, ACL, role, phiên bản server, slot routing hoặc Lua script.
3. Sửa nguyên nhân tại schema/config/code thay vì lặp command đã sai.
4. Nếu lỗi do topology tạm thời, cần khám phá primary/slot mới trước khi thử lại.

**Với serialization:**

1. Xác định key/value/hash serializer ở cả bên ghi và bên đọc.
2. So sánh schema version của bản cũ và mới.
3. Thử decode một payload test không nhạy cảm theo serializer thực tế.
4. Nếu là cache tái tạo được, cân nhắc version namespace hoặc invalidation có kiểm soát; nếu là dữ liệu nguồn, bảo toàn dữ liệu để migration.

### Bước 4 — Khôi phục với phạm vi nhỏ nhất

Ví dụ:

- Redis down tạm thời, chỉ phục vụ cache: fallback có giới hạn, giảm tải Redis và phục hồi cache dần.
- `WRONGTYPE` chỉ trên một namespace: sửa schema/key naming, không xóa toàn Redis.
- ACL bị thay đổi: cấp đúng quyền cần thiết, không dùng một tài khoản superuser để né chính sách.
- Driver stale topology sau failover: kiểm tra Sentinel/Cluster-aware configuration và reconnect.
- Dữ liệu cache cũ không decode: dùng namespace `v2` hoặc migration, không `FLUSHALL` như biện pháp mặc định.

### Bước 5 — Đối soát trạng thái nếu thao tác ghi có kết quả không chắc chắn

Đối với lệnh chỉ đọc, việc thử lại thường đơn giản hơn. Đối với `INCR`, `XADD`, `SET NX`, cập nhật tồn kho, token lease hoặc các workflow gồm nhiều lệnh, cần biết:

- Redis có thể đã thực hiện lệnh trước timeout không?
- Có idempotency key để nhận diện lệnh trùng không?
- Có transaction/unique constraint tại nơi ghi side effect không?
- Có thể đọc lại trạng thái thật để xác nhận kết quả không?
- Nếu không thể biết, giao diện ứng dụng có cần trả trạng thái “chưa xác định” và chuyển sang đối soát không?

Đây là bước giúp tránh tình huống hệ thống phục hồi về mặt kết nối nhưng dữ liệu bị xử lý hai lần.

## 18. Bảng tình huống thường gặp

| Triệu chứng | Chẩn đoán ưu tiên | Điều không nên làm |
| --- | --- | --- |
| `Unable to connect to Redis` | Endpoint, DNS, port, firewall, TLS, role và Redis health | Kết luận ngay Redis server chết mà chưa kiểm tra từ pod ứng dụng |
| `RedisCommandTimeoutException` | Command latency, network, queue, payload và driver timeout | Retry mọi lệnh ghi với thời gian chờ bằng 0 |
| `WRONGTYPE` với `opsForList()` | Key thật đang là String/Hash/Set? | Xóa key production mà không hiểu owner và schema |
| `READONLY You can't write against a read only replica` | Kết nối stale sau failover hoặc cấu hình replica | Tăng timeout mà không cập nhật routing |
| `NOPERM` | Redis ACL key pattern/command category | Tự đổi sang tài khoản quản trị quyền rộng |
| `NOAUTH` / `WRONGPASS` | Credential, ACL, secret rotation và TLS | Ghi password/URI vào log để debug |
| `CROSSSLOT` | Redis Cluster và hash slot của multi-key command | Gửi lại nguyên command lên một node ngẫu nhiên |
| `NOSCRIPT` | Script cache của node mới hoặc sau restart | Coi là hỏng serializer |
| `OOM command not allowed` | Redis maxmemory, eviction policy, data size | Tiếp tục tăng số retry để đẩy thêm tải |
| JSON deserialize failure | Key bytes, serializer, class/schema version | Retry đọc cùng bytes vô hạn |
| Sau deploy ứng dụng đọc cache toàn miss | Có thể key serializer hoặc namespace đã đổi | Xem mọi miss là Redis connection failure |
| `Mono.empty()` từ Redis GET | Key không tồn tại | Bắt như exception hoặc tạo giá trị `null` trong Reactor |
| Client timeout sau `INCR` | Trạng thái command có thể không chắc chắn | Retry tăng tiếp khi chưa có bảo vệ idempotency |
| Publisher Pub/Sub trả `0` | Không có subscriber đang nhận theo ngữ nghĩa Redis | Kết luận Redis server hỏng |
| Redis failover đã xong nhưng API vẫn lỗi | Driver reconnect/topology, endpoint NAT/ACL | Chỉ nhìn trạng thái Sentinel và bỏ qua lỗi phía ứng dụng |
| Redis connection ổn nhưng API p99 cao | Serialize lớn, pool wait, downstream hoặc command queue | Chỉ đo ping Redis rồi kết luận không có vấn đề |

## 19. Một chính sách lỗi mẫu cho ứng dụng nhiều chức năng

Giả sử một dịch vụ vừa dùng Redis làm cache sản phẩm, vừa dùng Redis Streams để đọc event và Redis lock để tránh chạy job trùng. Không thể dùng một `RedisExceptionHandler` chung với hành vi “nếu lỗi thì bỏ qua Redis”.

Một phân chia policy hợp lý:

~~~text
                         Redis access
                              |
                              v
                        Classify failure
                              |
          +-------------------+--------------------+
          |                   |                    |
          v                   v                    v
    Product Cache         Streams Consumer       Distributed Lock
          |                   |                    |
          v                   v                    v
   Connection/timeout   Lỗi trước commit?     Acquire/renew không rõ?
          |                   |                    |
          v                   v                    v
   Fallback có giới hạn  Không ACK mù          Không tự coi đã
   + cache rebuild      + pending recovery     có hoặc mất lease
          |                   |                    |
          v                   v                    v
   Wrongtype/schema?     Lỗi payload?          Timeout sau SET NX?
          |                   |                    |
          v                   v                    v
   Sửa key/migration    DLQ / schema policy   Dùng token/đối soát
   thay vì retry         trước khi ACK         + fencing khi cần
~~~

Với cache, một lỗi mạng có thể chỉ làm giảm hiệu năng nếu có nguồn dữ liệu thay thế. Với Streams, lỗi trước khi side effect thành công phải giữ lại khả năng xử lý lại, không ACK như thể thành công. Với lock, một lệnh acquire timeout có thể đã tạo key; xử lý sai trạng thái ownership có thể làm xuất hiện hai worker cùng thao tác.

Do đó, **classifier cung cấp nhãn**, còn **business policy quyết định hành vi**. Cấu trúc tốt thường có:

1. Một adapter Redis nhận diện và gắn metric lỗi theo nhóm.
2. Một policy riêng cho cache, queue/stream, lock và các dữ liệu quan trọng.
3. Cơ chế retry hữu hạn theo operation, có jitter và giới hạn concurrency.
4. Chỗ lưu dấu idempotency hoặc ràng buộc transaction cho side effect không được lặp.
5. Tài liệu runbook để đội vận hành biết khi nào fallback, khi nào fail closed và khi nào cần migration.

## 20. Kết luận

Phân loại lỗi Redis theo **kết nối, thời gian chờ, lệnh và tuần tự hóa** giúp ứng dụng Spring Data Redis tránh cách xử lý quá đơn giản “Redis lỗi thì retry”. Bốn nhóm cần hành động khác nhau:

- **Connection:** kiểm tra endpoint, network, TLS, pool và topology; chỉ retry có giới hạn khi phù hợp.
- **Timeout:** nhận diện bước nào hết hạn, đo latency/queue và chấp nhận rằng lệnh ghi có thể **đã thực thi** dù client chưa nhận kết quả.
- **Command:** đọc error code như `WRONGTYPE`, `NOPERM`, `READONLY` hay `CROSSSLOT`; sửa dữ liệu, quyền hoặc routing thay vì thử lại mãi.
- **Serialization:** kiểm tra serializer, schema, dữ liệu cũ và migration; không biến payload không đọc được thành cache miss một cách thiếu kiểm soát.

Với Spring Data Redis, exception translation có thể bọc exception của Lettuce/Jedis trong `DataAccessException` hoặc exception khác. Hãy quan sát **cause chain, operation và bối cảnh nghiệp vụ**, không phụ thuộc tuyệt đối vào một tên exception. Trong reactive code, cần tách `Mono.empty()` khỏi `onError` và hiểu rằng `Mono.timeout()` không chứng minh Redis đã rollback command.

Cuối cùng, **loại thao tác** quan trọng không kém **loại lỗi**: retry `GET` khác hoàn toàn retry `INCR` hoặc `XADD`. Khi policy lỗi được kết hợp với idempotency, metrics, kiểm thử có kiểm soát và các ranh giới nhất quán phù hợp, ứng dụng có thể phục hồi sau sự cố Redis mà không đánh đổi tính đúng đắn dữ liệu.

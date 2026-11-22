# Xác thực bằng mật khẩu hoặc ACL username/password trong Spring Data Redis

## 1. Xác thực Redis giải quyết vấn đề gì?

Một ứng dụng Spring Boot thường kết nối đến Redis qua mạng để đọc cache, cập nhật bộ đếm, lưu dữ liệu ngắn hạn hoặc xử lý cấu trúc dữ liệu Redis. Nếu Redis yêu cầu xác thực, client phải chứng minh mình được phép sử dụng kết nối **trước khi thực hiện các lệnh nghiệp vụ**. Khi Redis dùng ACL (Access Control List), client còn cần có quyền đối với từng lệnh, khóa và đôi khi cả kênh Pub/Sub.

Trong Spring Data Redis, nhiệm vụ này thuộc **cấu hình kết nối**: ứng dụng truyền thông tin đăng nhập cho thư viện Redis client, chẳng hạn Lettuce, thông qua Spring Boot hoặc một **RedisConnectionFactory** do lập trình viên tự cấu hình. Các thao tác như **StringRedisTemplate.opsForValue().get(...)** sau đó sử dụng những kết nối đã được thiết lập.

Cần phân biệt hai loại xác thực:

- **Xác thực người dùng ứng dụng**: ví dụ một khách hàng đăng nhập vào website bằng email và mật khẩu.
- **Xác thực dịch vụ tới Redis**: chính ứng dụng Spring Boot đăng nhập Redis bằng một tài khoản Redis được cấp quyền.

Redis không tự biết người dùng HTTP nào đang gọi API. Một Spring Boot service thường dùng một danh tính Redis cho các kết nối của mình, trừ khi kiến trúc cố ý triển khai mô hình khác.

Các triệu chứng cho thấy kết nối đang gặp vấn đề xác thực hoặc phân quyền gồm **NOAUTH**, **WRONGPASS**, **NOPERM**, hoặc exception liên quan Redis connection khi ứng dụng khởi tạo hay thực hiện lệnh.

## 2. Hai mô hình thường gặp: mật khẩu mặc định và ACL username/password

### 2.1. Xác thực bằng một mật khẩu: default user

Trong các hướng dẫn Redis đơn giản, server được cấu hình một mật khẩu chung. Client chỉ cần gửi mật khẩu, không cung cấp tên người dùng riêng:

~~~text
AUTH <password>
~~~

Từ Redis 6 trở lên, cơ chế **ACL** đưa vào khái niệm user; cách đăng nhập chỉ có mật khẩu về mặt tương thích được hiểu là xác thực cho user **default**. Tùy cấu hình server, mật khẩu của default user có thể được thiết lập bằng cấu hình **requirepass** truyền thống hoặc bằng ACL.

Ví dụ cấu hình server dành cho môi trường thử nghiệm:

~~~conf
# Một đoạn cấu hình redis.conf, không phải application.yml
requirepass REPLACE_WITH_A_STRONG_SECRET
~~~

Điều này thiết lập phía **Redis Server**. Nó khác với cấu hình password phía Spring Boot. Đặt **spring.data.redis.password** ở ứng dụng không làm Redis Server tự bật xác thực.

Với mô hình mật khẩu mặc định:

- Client có thể gửi một mật khẩu mà không chỉ định username.
- Redis 6+ cũng có thể xác thực dưới tên user **default** nếu user này được cấu hình tương ứng.
- Các ứng dụng dùng cùng mật khẩu thường chia sẻ cùng danh tính Redis; khó giới hạn quyền riêng cho từng ứng dụng chỉ bằng cách phát chung một mật khẩu.
- Có mật khẩu **không đồng nghĩa** với việc dữ liệu truyền trên mạng đã được mã hóa.

### 2.2. Xác thực bằng ACL user

Redis 6 trở lên hỗ trợ tạo những **user có tên**, mỗi user có thể có thông tin đăng nhập và quyền riêng. Cú pháp xác thực bằng username/password là:

~~~text
AUTH <username> <password>
~~~

Ví dụ về sự phân tách trách nhiệm:

| User Redis | Mục đích | Phạm vi mong muốn |
| --- | --- | --- |
| **spring_cache** | Ứng dụng đọc/ghi cache | Những lệnh và key thuộc namespace cache |
| **event_consumer** | Dịch vụ đọc Redis Streams | Những lệnh Stream và key được phép |
| **redis_admin** | Người hoặc hệ thống vận hành | Quản trị ACL, cấu hình và chẩn đoán cần thiết |

ACL giúp tổ chức theo nguyên tắc **ít quyền nhất**. Có thể giới hạn:

1. **Command**: user có thể chạy GET/SET nhưng không có quyền CONFIG hoặc FLUSHALL.
2. **Key pattern**: chỉ được thao tác những key có tên phù hợp, chẳng hạn **spring:cache:***.
3. **Pub/Sub channel**: khi ứng dụng sử dụng Pub/Sub, quyền đối với channel được quản lý riêng với key.

Không phải mọi Redis deployment đều cho phép ứng dụng tự tạo ACL user. Với Redis managed service, người vận hành có thể phải tạo user từ giao diện quản trị hoặc API của nhà cung cấp.

### 2.3. Bảng so sánh

| Đặc điểm | Mật khẩu cho default user | ACL username/password |
| --- | --- | --- |
| Client truyền gì? | Password; username thường bỏ trống | Username và password |
| Cú pháp AUTH | AUTH password | AUTH username password |
| Danh tính Redis | Thường là **default** | User có tên, ví dụ **spring_cache** |
| Quyền truy cập | Quyền gắn với default user | Có thể cấp riêng cho từng user |
| Trường hợp hay dùng | Môi trường đơn giản, cấu hình kế thừa | Nhiều service hoặc yêu cầu phân quyền rõ ràng |
| Khả năng thay đổi quyền | Thay đổi quyền default ảnh hưởng các client dùng user đó | Có thể điều chỉnh user riêng |

Điểm chính: Redis không có hai hệ thống xác thực hoàn toàn tách biệt trong các phiên bản hiện đại; **cách mật khẩu đơn giản thường là đường tương thích cho default user của ACL**.

## 3. Luồng xác thực trong ứng dụng Spring Boot

~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Client as Lettuce / RedisConnectionFactory
    participant Redis as Redis Server
    App->>Client: Yêu cầu thao tác StringRedisTemplate
    Client->>Redis: Mở kết nối TCP hoặc TLS
    Client->>Redis: AUTH hoặc bước handshake có xác thực
    Redis-->>Client: Xác thực thành công hoặc lỗi
    Client->>Redis: GET / SET theo quyền của user
    Redis-->>Client: Giá trị hoặc NOPERM
    Client-->>App: Trả kết quả / exception
~~~

Trong thực tế, client có thể dùng các lệnh bắt tay hoặc xác thực kết hợp tùy phiên bản giao thức và thư viện; sơ đồ diễn tả **ý nghĩa** của quá trình, không yêu cầu thư viện phải gửi đúng một câu lệnh AUTH riêng biệt trong mọi trường hợp.

Một **RedisConnectionFactory** biết cách tạo hoặc cung cấp kết nối. **RedisTemplate**, **StringRedisTemplate** và những thành phần truy cập Redis dùng factory đó. Nếu kết nối được dùng lại hoặc lấy từ pool, ứng dụng không cần tự gọi AUTH ở mỗi method nghiệp vụ.

**Thứ tự xử lý quan trọng:** kết nối được xác thực trước; sau đó Redis mới kiểm tra quyền của user trên từng lệnh và từng key. Vì vậy **đăng nhập thành công vẫn có thể nhận NOPERM**.

## 4. Cấu hình Spring Boot khi Redis chỉ cần mật khẩu

Với Spring Boot 3.x và starter Spring Data Redis, thêm dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Giả sử Redis Server có mật khẩu cho **default user**. Cấu hình trong **application.yml**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
~~~

Biến môi trường **REDIS_PASSWORD** phải được cung cấp khi ứng dụng khởi chạy. Không ghi mật khẩu thực vào file cấu hình commit lên Git.

Trong trường hợp này, **không cần username**. Nếu bạn chủ động cấu hình user **default** trên Redis và muốn dùng username rõ ràng, Redis 6+ cũng có thể chấp nhận cặp default/password tương ứng. Tuy nhiên, đối với cách cấu hình legacy chỉ có mật khẩu, bỏ trường username thường dễ hiểu nhất.

Phân biệt các trường:

- **host** và **port**: nơi Redis đang lắng nghe.
- **password**: bí mật để Redis xác thực danh tính client.
- **connect-timeout**: giới hạn thời gian thiết lập kết nối.
- **timeout**: giới hạn thời gian thực hiện lệnh theo cấu hình client.

Đặt timeout không giải quyết được lỗi mật khẩu. Khi Redis trả WRONGPASS, tăng timeout hoặc kích thước pool không làm thông tin đăng nhập trở nên hợp lệ.

**Lưu ý về phiên bản:** các ví dụ dùng namespace cấu hình **spring.data.redis** thường gặp ở Spring Boot 3.x. Một số dự án Spring Boot cũ sử dụng **spring.redis**. Khi bảo trì dự án cũ, cần đối chiếu đúng phiên bản Spring Boot đang chạy.

## 5. Cấu hình Spring Boot với ACL username/password

Giả sử Redis đã có user tên **spring_cache** và một mật khẩu tương ứng. Cấu hình ứng dụng:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
~~~

Trong môi trường chạy, hai biến cần có giá trị hợp lệ:

~~~text
REDIS_USERNAME=spring_cache
REDIS_PASSWORD=<secret-cua-user-spring_cache>
~~~

Đây là **ví dụ về tên biến**, không phải yêu cầu in mật khẩu ra terminal hoặc commit một file chứa bí mật. Nên cung cấp biến qua cơ chế quản lý bí mật phù hợp với môi trường vận hành.

Khi Spring Boot đã tự tạo connection factory từ starter, code dùng Redis không phải tự truyền user và password:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CacheProbeService {

    private final StringRedisTemplate redis;

    public CacheProbeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String roundTrip() {
        String key = "spring:cache:demo";
        redis.opsForValue().set(key, "connected", Duration.ofMinutes(1));
        return redis.opsForValue().get(key);
    }
}
~~~

Với cấu hình kết nối và quyền Redis hợp lệ, **roundTrip()** trả về **connected**. Dữ liệu được lưu với TTL 1 phút. Phương thức không chứa lệnh AUTH vì client đã thực hiện xác thực ở tầng kết nối.

Nếu user chỉ có quyền **GET** nhưng không có quyền **SET**, bước ghi trong roundTrip sẽ thất bại với lỗi phân quyền. Nếu user được phép SET nhưng không được thao tác key có tiền tố **spring:cache:**, Redis cũng có thể từ chối lệnh.

### Khi ứng dụng tự cấu hình ConnectionFactory

Trong trường hợp dự án không dựa vào auto-configuration mặc định hoặc cần thay đổi sâu kết nối, có thể tạo **RedisStandaloneConfiguration**, đặt username/password rồi đưa vào **LettuceConnectionFactory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class CustomRedisConnectionConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory(
            @Value("${app.redis.host}") String host,
            @Value("${app.redis.port}") int port,
            @Value("${app.redis.username:}") String username,
            @Value("${app.redis.password}") String password) {

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(host, port);

        if (username != null && !username.isBlank()) {
            config.setUsername(username);
        }
        config.setPassword(RedisPassword.of(password));

        return new LettuceConnectionFactory(config);
    }
}
~~~

Các thuộc tính **app.redis.*** trong ví dụ là namespace tự đặt, chẳng hạn:

~~~yaml
app:
  redis:
    host: localhost
    port: 6379
    username: ${REDIS_USERNAME:}
    password: ${REDIS_PASSWORD}
~~~

Chỉ tạo factory tùy chỉnh khi có lý do rõ ràng. Nếu ứng dụng vừa tự định nghĩa một factory vừa kỳ vọng auto-configuration của Spring Boot quản lý mọi kết nối giống trước, có thể xảy ra khác biệt về timeout, TLS, pooling và những cấu hình khác. Phần code này minh họa **cách gắn credentials vào connection factory**; nếu hệ thống dùng TLS hoặc Redis Cluster/Sentinel, cần cấu hình client tương ứng với topology thực tế.

## 6. Tạo và giới hạn ACL user trên Redis

Để giải thích phần server, giả sử người quản trị đã đăng nhập Redis bằng một danh tính có quyền quản lý ACL. Trong **chế độ tương tác của redis-cli** trên môi trường thử nghiệm, lệnh ví dụ:

~~~text
ACL SETUSER spring_cache reset on >REPLACE_WITH_A_STRONG_SECRET ~spring:cache:* +get +set +del +exists +ttl +pttl +type +ping
~~~

Ý nghĩa từng phần:

| Thành phần | Giải thích |
| --- | --- |
| **ACL SETUSER spring_cache** | Tạo hoặc cập nhật ACL user tên spring_cache. |
| **reset** | Khởi tạo lại những quyền/quy tắc quan trọng về trạng thái mặc định bị giới hạn, tránh vô tình giữ đặc quyền cũ. |
| **on** | Bật user để có thể xác thực. |
| **>REPLACE_WITH_A_STRONG_SECRET** | Thêm mật khẩu cho user. Phần **>** là cú pháp của ACL. |
| **~spring:cache:\*** | Chỉ cho phép truy cập key khớp mẫu này. |
| **+get +set +del ...** | Cấp từng lệnh Redis được phép sử dụng. |

**Chú ý quan trọng:** ký tự **>** trong cú pháp ACL có thể bị shell diễn giải thành chuyển hướng output nếu gõ trực tiếp trong một lệnh shell không được escape. Ví dụ trên dành cho giao diện **redis-cli tương tác**, không phải một câu lệnh có thể dán nguyên văn sau **redis-cli** ở terminal hệ điều hành. Câu lệnh cấu hình ACL cũng chứa mật khẩu dạng rõ trong input của terminal; với môi trường thực, hãy sử dụng cơ chế cấp phát secret/ACL an toàn của tổ chức hoặc dịch vụ Redis.

Đây là một user minh họa cho thao tác **GET, SET, DEL, EXISTS, TTL, PTTL, TYPE, PING** với các key có tiền tố spring:cache:. User đó không mặc nhiên được chạy HGETALL, CONFIG, FLUSHALL hoặc lệnh admin. Nếu ứng dụng dùng thêm cấu trúc dữ liệu khác, pool cần lệnh khởi tạo bổ sung, hoặc cache manager cần xóa cả vùng cache, phải cấp quyền tương ứng theo nhu cầu thực tế.

Ví dụ **RedisCacheManager** có thể dùng tiền tố khóa dạng **cacheName::key** và lệnh **KEYS/SCAN** khi thực hiện một số thao tác xóa cache hàng loạt. Nếu ACL chỉ cho phép **spring:cache:*** và vài lệnh cơ bản trong ví dụ, những luồng đó có thể bị từ chối. Cần xác định **key prefix thực** của ứng dụng, những lệnh nó phát ra và mức quyền phù hợp trước khi cấp quyền.

Redis ACL quản lý quyền đối với **Redis command/key/channel**, không tự thay cho kiểm tra quyền nghiệp vụ của từng người dùng HTTP trong ứng dụng.

### 6.1. Xem cấu hình và nhật ký lỗi ACL

Với tài khoản quản trị được cấp quyền, một số lệnh hữu ích:

~~~text
ACL GETUSER spring_cache
ACL LIST
ACL LOG 10
~~~

- **ACL GETUSER** xem trạng thái và quyền của user.
- **ACL LIST** liệt kê định nghĩa các user; output có thể chứa thông tin cấu hình nhạy cảm, cần hạn chế chia sẻ.
- **ACL LOG 10** xem một số sự kiện bị từ chối liên quan ACL, hữu ích khi phân biệt thiếu quyền command hay key.

Redis cũng có **ACL WHOAMI** để hỏi danh tính đang được xác thực; khả năng gọi lệnh phụ thuộc quyền của user. Không nên mặc định tài khoản ứng dụng bị giới hạn có quyền tự đọc hoặc thay đổi toàn bộ cấu hình ACL.

### 6.2. User được tạo ra có tồn tại sau khi restart không?

**ACL SETUSER** thay đổi trạng thái ACL trên Redis Server đang chạy. Cách lưu bền phụ thuộc cấu hình:

- Nếu Redis sử dụng **ACL file** được cấu hình thích hợp, người quản trị có thể lưu các thay đổi vào đó bằng cơ chế quản lý ACL tương ứng, ví dụ **ACL SAVE** khi khả dụng.
- Nếu user/ACL được cấp qua **redis.conf**, pipeline cấu hình hoặc dịch vụ được quản lý, cần cập nhật nguồn cấu hình đó theo cách hỗ trợ.
- Không giả định việc tạo user một lần bằng CLI luôn còn hiệu lực qua mọi lần restart hoặc thay đổi môi trường.

Trong production, user và quyền nên được quản lý bằng quy trình vận hành có kiểm soát; tài khoản ứng dụng thường **không cần quyền ACL SETUSER**.

## 7. Kiểm tra kết nối bằng redis-cli

Việc thử đăng nhập bằng CLI giúp tách vấn đề ở Redis Server khỏi vấn đề cấu hình Spring Boot.

### 7.1. Mật khẩu của default user

Từ terminal hệ điều hành:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --askpass
~~~

redis-cli sẽ hỏi mật khẩu tương tác. Khi đã xác thực:

~~~text
PING
SET spring:cache:probe ok EX 60
GET spring:cache:probe
TTL spring:cache:probe
~~~

Nếu kết nối yêu cầu xác thực nhưng chưa cung cấp, Redis có thể trả **NOAUTH Authentication required**. Không dùng tùy chọn dòng lệnh **-a** với mật khẩu thật trong ví dụ chia sẻ hoặc script dễ lộ lịch sử; **--askpass** giúp tránh đặt secret trên dòng lệnh.

### 7.2. ACL username/password

Từ terminal hệ điều hành:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --user spring_cache --askpass
~~~

Nhập mật khẩu của chính user **spring_cache** khi CLI yêu cầu. Sau đó thử:

~~~text
PING
SET spring:cache:probe "hello" EX 60
GET spring:cache:probe
TYPE spring:cache:probe
TTL spring:cache:probe
~~~

Với ACL ví dụ ở mục 6, các lệnh này nằm trong phạm vi đã cấp. Nếu thử truy cập key ngoài namespace:

~~~text
GET another-service:private
~~~

Redis có thể trả **NOPERM** vì user không được phép truy cập key đó. NOPERM không có nghĩa là username/password sai; xác thực có thể đã thành công nhưng ACL từ chối thao tác.

Trong CLI tương tác cũng tồn tại hai dạng:

~~~text
AUTH <password>
AUTH <username> <password>
~~~

Đây là **cú pháp minh họa**; không nhập cả hai dòng hay sao chép dấu **< >** như giá trị thật. Vì nhập mật khẩu vào CLI tương tác có thể để lại dấu vết trong lịch sử hoặc log, nên ưu tiên **--askpass** khi thử đăng nhập.

## 8. Tạo kết nối có TLS: xác thực không đồng nghĩa mã hóa

Mật khẩu và ACL quyết định **ai được phép truy cập**. TLS bảo vệ **đường truyền** giữa Spring Boot và Redis nếu cả hai đầu hỗ trợ và cấu hình đúng.

Không dùng TLS trên mạng không đáng tin cậy khiến dữ liệu và thông tin xác thực có thể bị lộ qua kênh truyền. Với Redis Server cung cấp endpoint TLS, ví dụ trong Spring Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      host: redis.example.internal
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
~~~

Port ở trên chỉ minh họa: endpoint TLS của nhà cung cấp có thể sử dụng cổng khác. Bật **ssl.enabled** ở Spring không tự bật TLS trên Redis Server. Cần có server hỗ trợ TLS và cấu hình trust/certificate đúng theo hệ thống.

Ngoài TLS, nên áp dụng giới hạn mạng, Redis ACL có quyền tối thiểu, cập nhật bí mật định kỳ và tránh lộ credential qua URL, log hoặc file build.

## 9. Xác thực liên quan thế nào đến connection pool?

Trong mô hình **Lettuce** thường dùng với Spring Data Redis, nhiều thao tác thông thường có thể dùng chung một kết nối native thread-safe khi cấu hình cho phép. Kết nối có pool thường được cân nhắc cho những thao tác/kiến trúc cần connection riêng, chẳng hạn blocking operation, transaction hoặc yêu cầu tối ưu cụ thể.

Dù dùng kết nối chung hay nhiều kết nối trong pool, **mỗi kết nối TCP/TLS mới tới Redis cần hoàn thành quá trình xác thực hợp lệ** trước khi thực hiện lệnh. Quyền gắn với danh tính Redis đã xác thực cho kết nối đó.

Ví dụ cấu hình pool Lettuce khi ứng dụng có nhu cầu và đã thêm thư viện pooling phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
}
~~~

~~~yaml
spring:
  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      host: localhost
      port: 6379
      lettuce:
        pool:
          max-active: 8
          max-idle: 8
          min-idle: 0
          max-wait: 2s
~~~

Những giá trị pool chỉ minh họa, không phải thông số tối ưu mặc định cho mọi hệ thống. Không nhất thiết phải bật pool để sử dụng Spring Data Redis; cần xác định loại thao tác, độ đồng thời và hành vi của client.

Một số hệ quả quan trọng:

- Tăng **max-active** không sửa lỗi WRONGPASS hoặc NOPERM.
- Một user bị thu hồi quyền có thể làm các thao tác trên kết nối đang tồn tại thất bại, ngay cả khi ứng dụng từng đăng nhập thành công.
- Khi đổi password, kết nối mới phải dùng secret mới; với pool/kết nối dùng lại, cần có phương án cập nhật cấu hình và khởi tạo lại những kết nối cũ khi cần.
- Nếu username/password được cấu hình nhầm ở nhiều profile, thêm pool chỉ làm xuất hiện thêm lỗi kết nối được tạo bằng cùng cấu hình sai.

### 9.1. Đổi mật khẩu không gián đoạn: điểm cần tính trước

Tùy cơ chế quản lý ACL, có thể bố trí một khoảng chuyển tiếp chấp nhận nhiều secret hợp lệ rồi cập nhật tất cả service, sau đó thu hồi secret cũ. Cần chú ý:

1. Đảm bảo Redis Server chấp nhận secret mới.
2. Cập nhật secret cho ứng dụng và các bản triển khai đang chạy.
3. Tạo lại hoặc kiểm tra các kết nối/pool để chắc chắn kết nối mới dùng secret mới.
4. Thu hồi secret cũ sau khi xác nhận ứng dụng và tác vụ nền đã chuyển sang secret mới.

Không nên thay mật khẩu một cách đột ngột trên môi trường nhiều instance khi chưa biết cách từng instance nạp lại configuration hoặc credential.

## 10. Phân biệt lỗi xác thực, phân quyền và kết nối

| Lỗi / dấu hiệu | Ý nghĩa thường gặp | Kiểm tra tiếp theo |
| --- | --- | --- |
| **NOAUTH Authentication required** | Client chưa xác thực nhưng Redis yêu cầu | Xem username/password có được truyền không; kiểm tra connection factory và profile đang chạy. |
| **WRONGPASS invalid username-password pair or user is disabled** | Credential không khớp hoặc ACL user bị tắt | Kiểm tra đúng username, secret, trạng thái ACL và endpoint Redis. |
| **NOPERM this user has no permissions...** | Đã xác thực nhưng không có quyền lệnh, key hoặc channel | Xem chính xác lệnh, key prefix, quyền ACL; dùng ACL LOG khi có quyền quản trị. |
| **Connection refused** | Không kết nối được socket tới host/port | Kiểm tra Redis chạy chưa, DNS, port, firewall, mạng container. |
| **Timeout** | Thiết lập kết nối hoặc lệnh không hoàn thành đúng hạn | Kiểm tra mạng, Redis load, pool, TLS, cấu hình timeout. |
| **TLS/SSL handshake failure** | Không thống nhất giao thức hoặc không tin cậy certificate | Kiểm tra endpoint TLS, cổng, truststore và cấu hình SSL hai phía. |
| **AUTH failed khi Redis không yêu cầu mật khẩu** | Client gửi AUTH nhưng server không cấu hình credential theo cách đó | Kiểm tra cấu hình phía server và bỏ credential không cần thiết trong môi trường tương ứng. |

Không có một thông báo lỗi duy nhất cho mọi phiên bản Redis client. Trong Spring Boot, lỗi Redis thường được đóng gói qua exception của Spring Data Redis hoặc Lettuce; cần đọc **root cause** để tìm nguyên nhân thật.

### Quy trình chẩn đoán có thứ tự

**Bước 1 — Kiểm tra endpoint.** Xác minh host, port, topology standalone/Sentinel/Cluster và việc sử dụng TLS. Một app kết nối nhầm Redis khác có thể trả WRONGPASS dù secret đúng ở môi trường dự định.

**Bước 2 — Kiểm tra loại thông tin đăng nhập.** Môi trường dùng default password hay ACL user có tên? Nếu dùng ACL, cả username lẫn password phải khớp. Một số dịch vụ managed Redis yêu cầu thiết lập user theo phương thức riêng.

**Bước 3 — Thử bằng redis-cli.** Dùng **--askpass** và **--user** khi cần. Nếu CLI không đăng nhập được vào cùng endpoint, phải giải quyết phía Redis/credential trước.

**Bước 4 — Kiểm tra quyền trên đúng key và command.** Nếu CLI đăng nhập thành công nhưng GET/SET bị NOPERM, dùng quyền admin để xem ACL user và các sự kiện bị từ chối. Đừng cấp **+@all** chỉ để làm lỗi biến mất.

**Bước 5 — Kiểm tra cấu hình Spring.** Xem profile, environment variables, secret injection, file application.yml, factory tự định nghĩa và các Redis URL đang được dùng. Không log giá trị password để debug.

**Bước 6 — Kiểm tra kết nối cũ và pool.** Nếu vừa rotate secret, xem ứng dụng có nạp lại cấu hình, reconnect hoặc rebuild pool chưa.

## 11. Những hiểu nhầm phổ biến

**“Chỉ thêm password vào Spring Boot là Redis đã an toàn?”** Không. Server cũng cần cấu hình xác thực, giới hạn mạng, TLS thích hợp và các quyền truy cập phù hợp. Cấu hình credential phía client chỉ bảo client dùng bí mật nào.

**“Nếu dùng ACL, mọi service vẫn nên dùng default user?”** Không cần. ACL hữu ích khi mỗi service có user với phạm vi quyền rõ ràng. Chia sẻ cùng default user cho mọi dịch vụ khiến việc thu hồi hoặc giới hạn quyền riêng khó khăn.

**“Kết nối thành công thì GET/SET luôn chạy được?”** Không. ACL có thể cho user đăng nhập nhưng cấm command hoặc key cụ thể.

**“Redis username giống tài khoản đăng nhập website?”** Không. Username ACL đại diện cho client/service kết nối Redis, không phải danh tính người dùng cuối trong hệ thống.

**“Chỉ cần cấu hình pool lớn là tránh được lỗi Redis?”** Không. Pool liên quan quản lý và tái sử dụng kết nối; authentication, ACL, TLS, hiệu năng và độ tin cậy là những vấn đề riêng cần xử lý theo nguyên nhân.

**“Bật TLS là đủ để phân quyền?”** Không. TLS bảo vệ kết nối; ACL kiểm soát Redis user có thể làm gì. Nên dùng kết hợp theo yêu cầu hạ tầng.

**“Một ACL user có +get +set là dùng được toàn bộ Spring Cache?”** Chưa chắc. Cần xét các lệnh xóa, TTL, prefix, serialization, thao tác quản lý cache và các lệnh khởi tạo của Redis client.

## 12. Ví dụ theo dõi toàn bộ luồng

Giả sử dịch vụ Spring Boot cần lưu cache tên sản phẩm trong Redis và Redis đã có ACL user:

~~~text
Username: spring_cache
Key được phép: spring:cache:*
Command được phép: GET, SET, DEL, EXISTS, TTL, PTTL, TYPE, PING
~~~

Ứng dụng có cấu hình:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

Service ghi cache:

~~~java
redis.opsForValue().set(
    "spring:cache:product:42",
    "Spring Data Redis",
    Duration.ofSeconds(90));
~~~

Người học có thể đăng nhập Redis bằng user đó và kiểm chứng:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 --user spring_cache --askpass
~~~

Sau khi vào redis-cli:

~~~text
PING
TYPE spring:cache:product:42
GET spring:cache:product:42
TTL spring:cache:product:42
~~~

Kết quả cần hiểu là key thuộc kiểu **string**, giá trị là **Spring Data Redis** và TTL sẽ giảm dần từ khoảng 90 giây. Nếu dịch vụ gọi xóa key (chẳng hạn khi cập nhật sản phẩm), **EXISTS spring:cache:product:42** sẽ trả 0. Nếu gõ key ngoài namespace được cấp, Redis có thể trả NOPERM.

Mô hình tương tự áp dụng cho các ví dụ khác của Spring Data Redis: **connection factory chịu trách nhiệm credential**, Redis Server chịu trách nhiệm **xác thực và kiểm tra ACL**, còn lớp service chỉ thực hiện các thao tác dữ liệu đã được cho phép.

## 13. Những nguyên tắc cần giữ khi triển khai

1. **Biết Redis yêu cầu kiểu xác thực nào**: password của default user hay username/password của ACL user.
2. **Dùng cấu hình kết nối chuẩn của Spring Boot** khi đủ nhu cầu; chỉ tạo ConnectionFactory tùy chỉnh khi có yêu cầu đặc biệt.
3. **Không đưa secret vào source code, ví dụ Git, log hoặc URL chia sẻ.** Sử dụng cơ chế quản lý secret của môi trường.
4. **Cấp quyền theo những lệnh và key thực tế ứng dụng dùng**; tính cả Spring Cache, key prefix, các lệnh cache clear và Pub/Sub/Streams nếu có.
5. **Bảo vệ kênh mạng**, dùng TLS khi cần, kết hợp network policy và ACL.
6. **Tách vấn đề authentication khỏi pooling và connectivity**: WRONGPASS, NOPERM, timeout, Connection refused không có cùng cách sửa.
7. **Có quy trình rotate secret**, tính tới các instance và connection/pool đang tồn tại.

**Ghi nhớ:** Spring Data Redis hỗ trợ cả hai cách xác thực phổ biến: **password cho default user** và **ACL username/password**. Spring Boot truyền credentials qua cấu hình cho Redis client; Redis Server quyết định client có được đăng nhập và thực hiện lệnh trên key hay không. Hiểu rõ ranh giới này giúp cấu hình đúng, chẩn đoán lỗi hiệu quả và cấp quyền phù hợp cho từng dịch vụ.

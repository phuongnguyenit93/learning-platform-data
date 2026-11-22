# Cấu hình máy chủ, cổng, logical database và URL kết nối

Khi ứng dụng Spring Boot sử dụng Spring Data Redis, mỗi thao tác đọc/ghi đều phải đi đến **đúng Redis server**, qua **đúng cổng**, và trong trường hợp Redis standalone còn phải sử dụng **đúng logical database**. Các tham số này có thể được khai báo riêng bằng `host`, `port`, `database` hoặc gộp một phần vào `url`. Việc chọn sai một tham số có thể tạo ra những biểu hiện rất khác nhau: không kết nối được, kết nối thành công nhưng không tìm thấy khóa, hoặc ứng dụng vô tình ghi dữ liệu vào môi trường khác.

Bài này tập trung vào cấu hình kết nối trong **Spring Boot 3.3.x và Spring Data Redis 3.3.x**, với **Lettuce** là driver mặc định khi dùng starter. Mục đích là hiểu giá trị nào được Spring Boot đọc, giá trị nào thực sự được truyền đến `RedisConnectionFactory` và cách kiểm tra cấu hình đang có hiệu lực. Các ví dụ YAML dành cho Boot 3.x; nếu dùng Boot 2.x hoặc 4.x, phải đối chiếu lại prefix và API tương ứng.

## 1. Bốn thành phần quan trọng của một kết nối Redis

Xem một lệnh đọc đơn giản:

~~~text
Spring Service
    │
    ▼
StringRedisTemplate
    │
    ▼
RedisConnectionFactory
    │
    ├── Host: redis.internal.example
    ├── Port: 6379
    ├── Logical DB: 2
    └── Authentication/TLS nếu được cấu hình
    │
    ▼
Redis server → database 2 → key "app:product:42"
~~~

| Thành phần | Vai trò | Ví dụ | Lỗi thường thấy khi sai |
|---|---|---|---|
| **Host** | Địa chỉ IP hoặc tên DNS của Redis | `localhost`, `redis`, `redis.example.internal` | DNS không phân giải, kết nối bị từ chối, timeout |
| **Port** | Cổng TCP Redis đang lắng nghe hoặc cổng được publish tới client | `6379`, `6380` | Kết nối đến sai dịch vụ, bị từ chối hoặc timeout |
| **Logical database** | Chọn không gian khóa bằng chỉ số trong một Redis standalone | `0`, `2` | Lệnh thành công nhưng không thấy khóa đã ghi trong DB khác |
| **URL** | Biểu diễn endpoint kết nối và có thể bao gồm thông tin xác thực | `redis://redis.example:6379` | URL ghi đè các trường riêng; có thể trỏ sai endpoint |

**Host và port chỉ tới Redis server; logical database chọn tập khóa bên trong server đó.** Một URI có dạng `redis://...` là Redis URI, không phải địa chỉ HTTP. Kết nối đến port Redis cần giao thức Redis và driver như Lettuce/Jedis; trình duyệt web không thể gửi HTTP GET để truy vấn khóa Redis.

Các ví dụ kết nối mặc định thường dùng cổng `6379`, nhưng đây không phải cổng bắt buộc. Trong hạ tầng thật, cổng do Redis server, nhà cung cấp dịch vụ hoặc cấu hình chuyển tiếp mạng quyết định.

## 2. Bắt đầu bằng cấu hình Spring Boot

### 2.1. Dependency tối thiểu

Với dự án Gradle sử dụng plugin/dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter cung cấp Spring Data Redis và Lettuce trong cấu hình thông thường. Khi classpath, cấu hình và điều kiện bean phù hợp, Spring Boot tự tạo `RedisConnectionFactory` cùng các template Redis mặc định. Vì vậy không cần tự tạo factory chỉ để thay `localhost` bằng tên máy Redis khác.

### 2.2. Khai báo rõ host, port và database

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
~~~

Các thuộc tính chính:

| Thuộc tính Spring Boot 3.x | Giá trị mặc định thông dụng | Ý nghĩa |
|---|---|---|
| `spring.data.redis.host` | `localhost` | Host Redis trong kết nối standalone |
| `spring.data.redis.port` | `6379` | Cổng Redis trong kết nối standalone |
| `spring.data.redis.database` | `0` | Chỉ số logical database được chọn |
| `spring.data.redis.url` | Không đặt | URL kết nối; có quy tắc ưu tiên so với các trường endpoint riêng |
| `spring.data.redis.username` | Không đặt | Username Redis ACL khi cần |
| `spring.data.redis.password` | Không đặt | Password Redis khi cần |
| `spring.data.redis.connect-timeout` | Tùy default thư viện/phiên bản | Timeout khi thiết lập kết nối |
| `spring.data.redis.timeout` | Tùy default thư viện/phiên bản | Timeout đọc/thao tác theo cách driver và factory hỗ trợ |
| `spring.data.redis.ssl.enabled` | `false` | Bật TLS cho kết nối khi endpoint yêu cầu |

Các con số timeout ở ví dụ là **lựa chọn minh họa**, không phải cấu hình chuẩn cho mọi hệ thống. Timeout ngắn có thể gây lỗi giả ở đường mạng chậm; timeout quá dài có thể khiến request ứng dụng bị giữ quá lâu.

Với cấu hình trên, Spring Data Redis sử dụng một `RedisConnectionFactory` nhằm kết nối `localhost:6379` và chọn database `0`. Dù đã khai báo YAML, **Redis server phải tồn tại và có thể truy cập từ tiến trình ứng dụng**; starter không tự khởi động một server Redis trên mạng.

### 2.3. Ví dụ truy cập bằng `StringRedisTemplate`

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisNoteService {

    private final StringRedisTemplate redis;

    public RedisNoteService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String noteId, String text) {
        redis.opsForValue().set(
                "note:" + noteId,
                text,
                Duration.ofMinutes(15)
        );
    }

    public String load(String noteId) {
        return redis.opsForValue().get("note:" + noteId);
    }
}
~~~

Không có `host` hoặc `port` trong service. Template nhận factory do Spring quản lý, và factory sử dụng endpoint từ cấu hình hiệu lực. Đây là lý do nên đặt thông số kết nối bên ngoài business logic.

Dữ liệu lưu qua đoạn code trên sẽ nằm trong logical database mà connection factory đang chọn. Nếu chạy hai bản ứng dụng với `database: 0` và `database: 2`, cùng lệnh `GET note:1` có thể trả hai kết quả khác nhau ngay cả khi cả hai cùng truy cập một Redis server.

## 3. `host` và `port`: địa chỉ nhìn từ nơi ứng dụng chạy

### 3.1. `localhost` luôn chỉ máy/container của tiến trình client

Đây là nguyên nhân phổ biến gây lỗi khi chuyển từ môi trường phát triển sang Docker hoặc Kubernetes.

Giả sử Redis chạy trên một máy developer và ứng dụng Spring Boot cũng chạy trực tiếp trên máy đó:

~~~yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6379
~~~

Cấu hình hợp lý vì `127.0.0.1` trỏ về chính máy đang chạy ứng dụng.

Nhưng nếu Spring Boot chạy trong **container**, `localhost` trỏ vào chính container ứng dụng, **không** trỏ đến máy host hay container Redis ở bên cạnh. Khi hai service nằm trong cùng Docker Compose network, dùng service name làm DNS:

~~~yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"

  app:
    build: .
    environment:
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: "6379"
    depends_on:
      - redis
~~~

Giả sử file này được dùng trong dự án có Dockerfile hợp lệ và cả hai service thuộc cùng mạng Compose:

- **Spring Boot chạy trong service `app`:** kết nối đến `redis:6379`.
- **Spring Boot chạy trực tiếp trên máy host:** có thể dùng `localhost:6380`, vì Compose đã publish cổng `6380` của host tới cổng `6379` trong container Redis.
- **Một máy khác trên mạng:** chỉ có thể truy cập nếu host, firewall, cấu hình publish và chính sách mạng cho phép; không tự động truy cập được qua `localhost` của máy đó.

`depends_on` trong cấu hình cơ bản quyết định thứ tự khởi động container; nó không bảo đảm Redis đã sẵn sàng nhận lệnh ngay thời điểm Spring Boot kết nối. Nếu cần chờ service sẵn sàng, hãy dùng health check và chiến lược retry/readiness phù hợp.

### 3.2. Phân biệt port server, container port và host port

~~~text
Máy host                            Docker network
┌─────────────────────┐            ┌───────────────────────────┐
│ Spring Boot (host)  │            │ Redis container           │
│ localhost:6380      │ ─────────► │ redis:6379                │
└─────────────────────┘  mapping   └───────────────────────────┘
                                        ▲
                                        │ TCP redis:6379
                                  ┌─────┴───────────┐
                                  │ Spring Boot app │
                                  │ container       │
                                  └─────────────────┘
~~~

Trong ví dụ `6380:6379`, **bên trái là cổng host**, **bên phải là cổng container**. Spring Boot ở container khác thường sử dụng cổng bên phải, không sử dụng cổng đã publish trên host.

Điều tương tự áp dụng cho Kubernetes: pod ứng dụng thường kết nối bằng DNS của Service và port của Service, không bằng `localhost` trừ khi Redis thực sự chạy trong cùng network namespace và thiết kế yêu cầu như vậy.

### 3.3. Hostname và mạng không phải cấu hình bảo mật

Chọn đúng host/port chưa đủ để xác định kết nối an toàn. Redis server có thể giới hạn địa chỉ lắng nghe, protected mode, ACL, firewall hoặc private network. Không mở Redis ra Internet chỉ để xử lý lỗi kết nối từ ứng dụng; thay vào đó xác minh đường mạng, DNS, route, service discovery và TLS/authentication của môi trường triển khai.

## 4. Logical database: cách chọn `database` chính xác

### 4.1. Logical database là gì?

Redis standalone có thể cung cấp nhiều logical database được đánh số nguyên không âm. Với cấu hình Redis OSS thường gặp, server mặc định có **16 logical database**, từ `0` đến `15`, và mặc định client chọn `0`. Số lượng thực tế phụ thuộc cấu hình server/nhà cung cấp; không phải Redis nào cũng cho phép dùng các chỉ số này.

~~~text
Cùng Redis server localhost:6379
┌────────────────────────────────────────┐
│ db0:  key "profile:1"  → "Alice"       │
│ db1:  key "profile:1"  → "Bob"         │
│ db2:  key "profile:1"  → "Carol"       │
│ ...                                    │
└────────────────────────────────────────┘
~~~

Các khóa trùng tên có thể tồn tại ở các logical database khác nhau mà không đè lên nhau. Một client chọn `db2` và đọc `profile:1` sẽ không thấy giá trị ở `db0`. Vì vậy **kết nối thành công nhưng `GET` trả null** có thể là dấu hiệu client đang chọn sai logical database.

Redis dùng lệnh `SELECT` để đổi database hiện tại trên kết nối trong chế độ hỗ trợ logical database:

~~~bash
redis-cli -h localhost -p 6379 -n 2
~~~

Sau khi vào Redis CLI:

~~~text
127.0.0.1:6379[2]> SET lesson:greeting "Xin chao"
OK
127.0.0.1:6379[2]> GET lesson:greeting
"Xin chao"
127.0.0.1:6379[2]> SELECT 0
OK
127.0.0.1:6379> GET lesson:greeting
(nil)
~~~

Ví dụ trên giả sử server cho phép DB 2 và không bật cơ chế xác thực bắt buộc. `(nil)` ở DB 0 không có nghĩa lệnh `SET` ban đầu thất bại; khóa đã được ghi trong DB 2.

Dùng cấu hình Spring Boot tương ứng:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
~~~

### 4.2. Logical database không phải cơ chế cô lập tài nguyên

Các database trong cùng một Redis server vẫn chia sẻ tiến trình, tài nguyên CPU/RAM, giới hạn `maxmemory`, chính sách eviction, lịch persistence và phần lớn điều kiện vận hành. Đây **không** phải các Redis instance vật lý độc lập và không thay thế các biện pháp phân quyền hay cô lập tenant.

Một số hệ quả thực tế:

- DB 1 không có “RAM riêng” tách khỏi DB 0. Một nhóm khóa lớn có thể gây áp lực tài nguyên cho cả server.
- Lệnh `FLUSHDB` tác động đến database hiện tại, còn `FLUSHALL` tác động đến mọi database trên instance; các lệnh này nguy hiểm nếu dùng nhầm môi trường.
- TTL, eviction và lỗi disk/server vẫn liên quan đến tài nguyên chung.
- Redis ACL không nên được hiểu là quyền truy cập được cô lập theo số DB; nếu cần cách ly an toàn, hãy thiết kế instance/deployment và quy tắc quyền tương ứng.
- Khi quét hoặc kiểm tra khóa, phải xác nhận client đang ở database cần quan sát.

Trong ứng dụng thực, thường nên đặt **key prefix có chủ đích** như `dev:catalog:42`, `cache:product:42` và xác định rõ instance/môi trường. Prefix giúp tổ chức khóa nhưng cũng **không phải ranh giới bảo mật**.

### 4.3. Redis Cluster không hỗ trợ nhiều logical database

Một giới hạn nền tảng: **Redis Cluster chỉ hỗ trợ database 0**. Lệnh `SELECT` để chọn DB khác không khả dụng trong Redis Cluster. Vì vậy không thể dùng `spring.data.redis.database: 3` như phương pháp phân chia dữ liệu khi ứng dụng chuyển từ standalone sang Cluster.

~~~yaml
# Minh họa kết nối Redis Cluster; không đặt database khác 0
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1:6379
          - redis-node-2:6379
          - redis-node-3:6379
      database: 0
~~~

Các endpoint là ví dụ; chỉ dùng khi cụm Redis tương ứng tồn tại. Với Redis Cluster, cách phân chia dữ liệu thường dựa trên quy ước key, Redis ACL và các cụm/instance riêng khi cần cô lập thật sự.

**Redis Sentinel không đồng nghĩa Redis Cluster.** Sentinel giám sát và chuyển đổi primary/replica; Redis standalone do Sentinel quản lý vẫn có ngữ nghĩa logical database theo cấu hình của Redis server đó. Đừng suy luận khả năng dùng DB số khác chỉ từ tên “Redis cluster” trong tài liệu hạ tầng; cần biết dịch vụ thực sự sử dụng Redis Cluster, Sentinel hay dịch vụ managed có các giới hạn riêng.

### 4.4. Không đổi DB trên kết nối do framework đang quản lý một cách tùy ý

Spring Data Redis cấu hình database tại `RedisConnectionFactory`. Tránh lấy connection từ template/pool rồi tự gửi `SELECT 2` để phục vụ một request và quên trả về trạng thái ban đầu. Kết nối có thể được tái sử dụng, nên thay đổi trạng thái kết nối có thể gây đọc/ghi sai DB ở request kế tiếp.

Nếu ứng dụng thực sự phải truy cập nhiều logical database, nên xác định connection factory/template riêng theo DB và inject theo tên/`@Qualifier`. Nếu nhiều logical database chỉ dùng để mô phỏng các môi trường như dev/test/prod, cách ly bằng **Redis instance/deployment riêng** thường rõ ràng và an toàn hơn.

## 5. Cấu hình `url`: khi nào dùng và ghi đè những gì?

### 5.1. Dạng Redis URI thường gặp

Một Redis URI standalone thông thường:

~~~text
redis://<host>:<port>
redis://:<password>@<host>:<port>
redis://<username>:<password>@<host>:<port>
rediss://<host>:<port>
~~~

Ví dụ không chứa thông tin bí mật:

~~~yaml
spring:
  data:
    redis:
      url: "redis://redis.example.internal:6379"
      database: 0
~~~

URI có thể chứa username và password theo quy ước user information. Ví dụ `redis://app-user:secret@redis.example:6379` chỉ minh họa **cú pháp**; không đưa mật khẩu thật vào Git, log, URL hiển thị trên dashboard hay tài liệu.

Một số URI trong hệ sinh thái Redis dùng path `/2` để biểu thị logical database. **Không mặc nhiên cho rằng mọi driver/framework đều diễn giải phần path đó giống nhau.** Với Spring Boot 3.3, cách rõ ràng là cấu hình database qua `spring.data.redis.database` riêng và xác nhận bằng thao tác đọc/ghi ở DB mong muốn.

### 5.2. Quy tắc ưu tiên trong Spring Boot 3.x

Khi `spring.data.redis.url` được khai báo, nó được dùng làm nguồn thông tin endpoint và **ghi đè những trường `host`, `port`, `username`, `password` riêng lẻ** cho kết nối standalone theo cơ chế Redis auto-configuration của Boot.

Ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: redis-a.internal
      port: 6379
      url: "redis://redis-b.internal:6380"
      database: 2
~~~

Với factory mặc định được Boot tạo, endpoint kết nối sẽ đến `redis-b.internal:6380` theo `url`; không đến `redis-a.internal:6379`. Phần `database: 2` vẫn được dùng làm lựa chọn logical database trong cấu hình standalone phù hợp.

Sự khác nhau này giải thích tình huống người phát triển sửa `host` nhưng ứng dụng vẫn kết nối sang server cũ: một `url` đến từ YAML khác, environment variable, config server hay profile đang có hiệu lực.

**Quy tắc đơn giản:** Chọn **một** kiểu khai báo endpoint cho mỗi môi trường. Hoặc dùng `host + port + username/password`, hoặc dùng `url`. Tránh duy trì cả hai với giá trị mâu thuẫn.

### 5.3. TLS: `redis://` và `rediss://`

Theo quy ước Redis URI, `redis://` thể hiện kết nối thông thường; `rediss://` thể hiện kết nối bảo vệ bằng TLS. Khi sử dụng Spring Boot, nên khai báo rõ cấu hình SSL/TLS tương ứng với endpoint:

~~~yaml
spring:
  data:
    redis:
      url: "rediss://redis.secure.example:6380"
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 5s
~~~

Khả năng nhận biết scheme, cấu hình truststore và TLS certificate còn phụ thuộc phiên bản driver/framework và môi trường. **TLS được bật thành công không có nghĩa mọi chứng chỉ đều hợp lệ**; chứng chỉ server, tên host, CA và chính sách xác minh phải phù hợp. Với Redis managed service, dùng cổng TLS do nhà cung cấp công bố thay vì mặc định đoán `6380` luôn là TLS.

Không nên tắt kiểm tra chứng chỉ để “sửa” lỗi môi trường production. Nếu có lỗi handshake, hãy kiểm tra server certificate, trust chain, DNS và thiết lập TLS trước.

### 5.4. Username, password và ký tự đặc biệt trong URL

Redis 6+ hỗ trợ ACL user/password. Nếu dùng tài khoản ACL:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

Nếu hệ thống chỉ dùng default user với password, thuộc tính `username` có thể không cần khai báo; hãy dùng thông số xác thực thực tế do server cung cấp.

Với URL, ký tự đặc biệt trong username/password như `@`, `:`, `/`, `?`, `#` có vai trò cú pháp trong URI và cần được encode đúng theo URI parser đang dùng. Một mật khẩu có `@` không nên được chèn nguyên văn vào phần userinfo. Cần lưu ý thêm khả năng decode của từng driver; kiểm tra kết nối thật thay vì tự phỏng đoán chuỗi bị encode một hay hai lần.

Sử dụng secrets và tham chiếu môi trường thường dễ quản lý hơn việc viết trực tiếp `redis://user:password@host` trong source:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: 0
~~~

Ở đây `REDIS_URL` là environment variable do runtime cung cấp. Tránh ghi nguyên URL có credentials vào log, command history hoặc báo cáo chẩn đoán có thể bị chia sẻ.

### 5.5. URL không thay thế mọi cấu hình topology

Một URL `redis://host:port` điển hình mô tả endpoint standalone. Nó không tự động biểu diễn đầy đủ các cơ chế tìm primary qua Sentinel hoặc danh sách node của Redis Cluster.

Ví dụ cấu hình Redis Sentinel:

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
~~~

Những tên host trong ví dụ là placeholder. Khi hệ thống dùng Sentinel, cần kết nối đến Sentinel endpoints và chọn master name đúng; khi dùng Redis Cluster, cần cấu hình cluster nodes. Không nên dùng đồng thời URL standalone và topology khác nhau mà không đọc rõ quy tắc ưu tiên của Spring Boot cho phiên bản đang chạy.

## 6. Quản lý cấu hình giữa local, test, staging và production

### 6.1. Ưu tiên giá trị ngoài source cho endpoint thay đổi theo môi trường

Có thể dùng một YAML chung và đưa endpoint qua environment variables:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      database: ${REDIS_DATABASE:0}
      connect-timeout: 2s
      timeout: 3s
~~~

Cú pháp `${REDIS_HOST:localhost}` là cơ chế placeholder của Spring: nếu biến môi trường tồn tại thì lấy giá trị đó, nếu không dùng `localhost`. Trong cấu hình Spring Boot có thể dùng tên property môi trường theo quy tắc relaxed binding trực tiếp, ví dụ:

~~~text
SPRING_DATA_REDIS_HOST=redis
SPRING_DATA_REDIS_PORT=6379
SPRING_DATA_REDIS_DATABASE=2
~~~

Nếu khai báo `SPRING_DATA_REDIS_URL` đồng thời với `host` và `port`, quy tắc ưu tiên của URL vẫn cần được chú ý. Đặt environment variable không bảo đảm giá trị đó được dùng nếu có một property nguồn ưu tiên cao hơn hoặc ứng dụng đã tự cung cấp connection factory.

### 6.2. Dùng profile cho khác biệt có chủ đích

Ví dụ `application-local.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
~~~

Ví dụ `application-prod.yml`:

~~~yaml
spring:
  data:
    redis:
      host: redis.production.internal
      port: 6379
      database: 0
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
~~~

Kích hoạt profile khi khởi chạy:

~~~bash
java -jar app.jar --spring.profiles.active=local
~~~

Không cần đổi Java service khi thay đổi profile. Đây là điểm lợi của đưa endpoint vào `application*.yml` và để Spring Boot wiring factory tự động.

Đối với production, **tách Redis deployment** khỏi Redis dev/test vẫn là ranh giới quan trọng nhất. Dùng các số DB khác nhau trên cùng instance không thể bảo vệ dữ liệu production trước lệnh `FLUSHALL`, lỗi server hay sự cố tài nguyên chung.

### 6.3. Cấu hình trực tiếp bằng biến môi trường

Nếu hạ tầng cấp sẵn một URL, có thể bỏ hoàn toàn cặp host/port trong cấu hình ứng dụng:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: ${REDIS_DATABASE:0}
~~~

Khi chọn cách này, nên thống nhất trong nhóm vận hành: URL phải trỏ đến Redis standalone đúng môi trường, có scheme phù hợp, có thông tin xác thực cần thiết, và lựa chọn DB phải được cấu hình/kiểm chứng rõ. Trong các dịch vụ cloud, endpoint Redis có thể thay đổi sau failover hoặc được cung cấp qua DNS; đừng thay DNS bằng IP cố định nếu nhà cung cấp yêu cầu client theo tên dịch vụ.

## 7. Quan hệ giữa endpoint, connection factory và connection pool

Spring Data Redis không đọc `application.yml` lại mỗi khi gọi `GET`. Trong cấu hình thông thường, Spring Boot liên kết properties, khởi tạo `LettuceConnectionFactory`, rồi inject factory đó vào `StringRedisTemplate` và các template khác.

~~~mermaid
flowchart LR
    A["application.yml / env"] --> B["RedisProperties"]
    B --> C["LettuceConnectionFactory"]
    C --> D["StringRedisTemplate"]
    C --> E["RedisTemplate"]
    D --> F["GET / SET"]
    E --> F
    F --> G["Redis server / logical DB"]
~~~

Nếu ứng dụng khai báo **bean `RedisConnectionFactory` của riêng mình**, auto-configuration tạo factory mặc định có thể nhường quyền. Lúc đó các trường `spring.data.redis.host`, `port`, `database` và `url` **không nhất thiết được áp tự động** vào custom factory; mã tự cấu hình của bạn phải đọc và sử dụng chúng nếu mong muốn.

### 7.1. Có pool thì chọn database ở đâu?

Một connection pool quản lý vòng đời/tái sử dụng kết nối, nhưng không nên được xem là nơi quyết định mỗi request chạy trong DB nào. **Kết nối lấy từ pool phải được khởi tạo phù hợp factory, endpoint và logical database đã cấu hình.**

Khi dùng Lettuce, không phải mọi thao tác đều cần một physical TCP connection riêng. Lettuce có thể dùng kết nối được chia sẻ cho các thao tác thông thường, còn một số chế độ hoặc nhu cầu đồng thời đòi hỏi kết nối khác. Pool là lựa chọn cần đo tải và hiểu cơ chế driver, không phải bắt buộc chỉ vì ứng dụng có nhiều thread.

Ví dụ các thuộc tính pool khi **đã thêm dependency hỗ trợ pool** và thực sự muốn sử dụng:

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
      host: redis.internal
      port: 6379
      database: 1
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 0
          max-wait: 1s
~~~

Đây là ví dụ về hình thức cấu hình, không phải thông số được khuyến nghị chung. Dung lượng pool cần dựa trên số kết nối cần thiết, hành vi Lettuce, độ trễ và giới hạn client trên Redis server.

**Pool không tạo thêm logical database** và không giúp “lách” giới hạn Redis server. Nếu một app dùng hai database/endpoint khác nhau, cần thiết kế factory hoặc template riêng có chủ đích, thay vì đổi `SELECT` ngay trên connection đang được pool quản lý.

### 7.2. Khi nào cần tự tạo factory?

Thông thường chỉ cần `spring.data.redis.*`. Tạo bean thủ công khi có nhu cầu không thể hiện được qua properties/customizer hoặc cần nhiều kết nối tách biệt.

Ví dụ minh họa một factory standalone riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class SpecialRedisConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("redis.internal", 6379);
        server.setDatabase(2);
        return new LettuceConnectionFactory(server);
    }
}
~~~

Đây là factory **hard-code** endpoint để minh họa API, không phải cấu hình nên sao chép nguyên vào production. Sau khi sở hữu factory, người viết phải quyết định cách nhận credentials, TLS, timeout, topology và các property liên quan; đừng giả định Boot sẽ áp tất cả YAML vào object đã tạo. Khi chỉ cần chỉnh một tùy chọn Lettuce, xem xét customizer thay vì viết lại toàn bộ factory.

## 8. Xác nhận kết nối đang đến đúng host, port và DB

### 8.1. Kiểm tra server từ đúng môi trường chạy ứng dụng

Nếu Redis local không có xác thực:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

Kết quả mong đợi khi server cho phép lệnh là `PONG`.

Nếu ứng dụng chạy trong Docker Compose, chạy lệnh tương đương từ môi trường có cùng network với ứng dụng (hoặc thông qua một client container cùng mạng). Chạy `redis-cli` trên laptop thành công không chứng minh container ứng dụng có thể phân giải tên `redis` hoặc truy cập được port tương ứng.

Đối với TLS, Redis CLI hỗ trợ `--tls` và các tùy chọn CA/chứng chỉ cần thiết tùy triển khai. Với Redis yêu cầu xác thực, dùng phương thức cấp credentials an toàn phù hợp thay vì đặt password trực tiếp sau `-a` hoặc trong URI trên command line vì có thể lộ qua lịch sử lệnh hoặc danh sách tiến trình.

### 8.2. Kiểm tra logical database bằng khóa thử có tên rõ ràng

Chỉ thực hiện trên môi trường thử nghiệm được phép ghi:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 2 SET lesson:db-check "database-two"
redis-cli -h 127.0.0.1 -p 6379 -n 2 GET lesson:db-check
redis-cli -h 127.0.0.1 -p 6379 -n 0 GET lesson:db-check
redis-cli -h 127.0.0.1 -p 6379 -n 2 DEL lesson:db-check
~~~

Kỳ vọng trong một Redis standalone hỗ trợ DB 0 và 2:

- `GET` tại DB 2 trả `database-two`.
- `GET` tại DB 0 trả nil nếu trước đó không có khóa trùng tên.
- `DEL` cuối chỉ xóa khóa thử tại DB 2.

Để quan sát thống kê số khóa theo DB có thể dùng:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
~~~

Ví dụ phần kết quả có thể có `db0:keys=...` và `db2:keys=...`. Đây là thống kê toàn instance cho các DB có khóa, không chứng minh chính xác một client Spring đang chọn DB nào. Muốn kiểm tra client Spring, hãy ghi/đọc một khóa thử bằng chính `StringRedisTemplate` của app, rồi quan sát bằng Redis CLI ở database dự kiến.

### 8.3. Phân biệt báo lỗi khi Spring chạy

| Biểu hiện | Kiểm tra trước tiên | Điều cần hiểu |
|---|---|---|
| `Connection refused` | Host/port, tiến trình Redis, cổng publish hoặc Redis bind | Tới được điểm đích nhưng không có listener chấp nhận trên cổng đó |
| `UnknownHostException` / không resolve DNS | DNS/service name theo network của app | Tên Redis không phân giải được từ môi trường client |
| Connection timeout | Firewall, routing, service không phản hồi, connect-timeout | Không chắc Redis đã nhận yêu cầu; cần kiểm tra đường mạng |
| Lỗi `NOAUTH` / `WRONGPASS` | Username, password, ACL user, URL precedence | Có giao tiếp với Redis nhưng xác thực không đạt |
| TLS handshake/certificate error | Scheme, SSL enabled, truststore, CA, hostname | Thiết lập kênh bảo mật thất bại |
| `GET` trả null, không có exception | `database`, key prefix, TTL, endpoint trỏ tới môi trường khác | Redis có thể hoạt động bình thường nhưng không có khóa ở vị trí đang đọc |
| `ERR DB index is out of range` | Chỉ số DB thực tế được server hỗ trợ | Logical database yêu cầu không tồn tại |
| Lỗi `SELECT` trong Cluster | Topology Redis Cluster | Cluster không cho dùng logical DB khác 0 |
| Chỉnh `host` nhưng vẫn truy cập server cũ | `url` có đang được đặt không, profile, env overrides | URL/nguồn cấu hình ưu tiên đang có hiệu lực |
| Custom factory bỏ qua YAML | Bean `RedisConnectionFactory` tự định nghĩa | Boot đã nhường quyền tạo factory cho ứng dụng |

**Không nên xử lý mọi vấn đề bằng cách tăng timeout.** Lỗi chọn sai host, port, username hoặc database không biến mất khi chờ lâu hơn.

### 8.4. Chẩn đoán properties đang có hiệu lực

Để biết Spring Boot đã nạp bean gì, có thể bật condition report:

~~~bash
java -jar app.jar --debug
~~~

Nhìn các phần về `RedisAutoConfiguration`, `LettuceConnectionConfiguration` hoặc `JedisConnectionConfiguration` để biết auto-configuration có tạo factory/template hay nhường quyền cho bean của ứng dụng.

Để biết endpoint thực tế, kiểm tra theo thứ tự:

1. Profile đang active và các file `application*.yml` tương ứng.
2. Environment variables, command-line arguments, external config và secrets do môi trường cấp.
3. `spring.data.redis.url` có tồn tại không; nếu có, endpoint riêng có thể không còn tác dụng.
4. Có cấu hình `RedisConnectionFactory` tự định nghĩa, Lettuce customizer hoặc topology Sentinel/Cluster hay không.
5. Network namespace nơi ứng dụng chạy có phân giải host và truy cập port đích được không.
6. Khi Redis trả kết quả đọc rỗng, kiểm tra chính xác DB và key prefix trước khi kết luận ghi dữ liệu thất bại.

Hạn chế log toàn bộ `RedisProperties` hoặc URI vì có thể chứa password. Báo cáo cấu hình nên che credentials và chỉ hiển thị các trường không nhạy cảm cần thiết cho debug.

## 9. Hai cấu hình hoàn chỉnh để hình dung đường đi thực tế

### Kịch bản A: ứng dụng học tập chạy trên máy developer

Redis chạy tại máy local với cấu hình standalone hỗ trợ DB 2:

~~~yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      database: 2
      connect-timeout: 2s
      timeout: 3s
~~~

Khi `RedisNoteService.save("42", "hello")` được gọi:

~~~text
StringRedisTemplate
    → LettuceConnectionFactory (127.0.0.1:6379, DB 2)
    → SET note:42 hello EX 900
    → Redis logical database 2
~~~

`RedisNoteService.load("42")` dùng cùng template/factory nên đọc lại DB 2. Nếu mở `redis-cli` ở DB 0 mà không thấy khóa, đó là hành vi đúng của logical database.

### Kịch bản B: ứng dụng nhận URL Redis từ môi trường triển khai

Hạ tầng quản lý endpoint và credentials qua secret `REDIS_URL`:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: 0
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 5s
~~~

Ví dụ giá trị secret về hình thức có thể là `rediss://user:password@managed-redis.example:6380`; **đây chỉ là chuỗi minh họa, không dùng làm thông tin truy cập thật**.

Ở kịch bản này, ứng dụng đọc endpoint từ `REDIS_URL`, sử dụng DB 0 nếu topology hỗ trợ và kết nối qua TLS theo cấu hình. Trong vận hành cần xác nhận URL có đúng scheme/cổng mà nhà cung cấp yêu cầu, certificate được tin cậy và user có quyền trên các khóa ứng dụng cần thao tác.

Hai kịch bản dùng cùng một lớp service Spring Data Redis. Khác biệt nằm ở **factory và giá trị cấu hình mà factory nhận**, không nằm ở code gọi `opsForValue()`.

## 10. Nguyên tắc cần nhớ trước khi học pool và các topology nâng cao

1. **Xác nhận điểm nhìn của client:** `localhost` là chính máy hoặc container chạy ứng dụng; hostname Docker Compose/Kubernetes chỉ có ý nghĩa trong mạng phù hợp.
2. **Phân biệt port Redis và port được chuyển tiếp:** `6380:6379` nghĩa là host dùng `6380`, service Redis trong mạng container vẫn nghe `6379`.
3. **Chọn logical database rõ ràng:** `spring.data.redis.database` mặc định là 0; DB khác chỉ có ý nghĩa khi server/topology cho phép, và không phải ranh giới cô lập bảo mật.
4. **Đừng dùng DB khác 0 với Redis Cluster:** thiết kế keyspace và deployment thay thế.
5. **Không trộn nhiều nguồn endpoint không cần thiết:** trong Boot 3.x, `url` ghi đè `host`, `port`, `username`, `password` trong cấu hình standalone do Boot quản lý.
6. **Giữ credentials và TLS đúng môi trường:** secret không nằm trong source/log; endpoint TLS cần cấu hình certificate/trust phù hợp.
7. **Ưu tiên cấu hình qua Boot properties:** tự khai báo `RedisConnectionFactory` chỉ khi thực sự cần, vì factory do ứng dụng sở hữu có thể không còn áp các property mặc định.
8. **Chỉ xem kết nối thành công là một phần của kiểm tra:** cần xác nhận Redis server, DB và keyspace thực sự đúng, đặc biệt khi đọc trả null.
9. **Pool là lớp quản lý kết nối:** pool không đổi quy tắc chọn host/port/database và không tạo isolation giữa logical database.

Khi đã hiểu **ứng dụng đang kết nối Redis nào, qua cổng nào, bằng cách xác thực nào và chọn logical database nào**, việc học pool, timeout, failover hay Redis Cluster sẽ có một nền tảng rõ ràng. Các vấn đề về connection pool thường chỉ được chẩn đoán chính xác sau khi cấu hình endpoint và database đã được xác nhận.

## Tài liệu tham khảo để tìm hiểu thêm

- [Spring Boot 3.3 — Working with NoSQL Technologies: Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Data Redis — Redis Support](https://docs.spring.io/spring-data/redis/reference/redis.html)
- [Spring Data Redis — Redis Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html)
- [Redis — SELECT command](https://redis.io/docs/latest/commands/select/)
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)

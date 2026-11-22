# Cấu hình số kết nối, thời gian chờ và kiểm tra kết nối

## 1. Vì sao cấu hình kết nối Redis quan trọng?

Trong ứng dụng Spring Boot sử dụng Spring Data Redis, một lệnh đọc key có thể rất nhanh khi thử trên máy cá nhân nhưng lại chậm hoặc thất bại lúc nhiều request chạy đồng thời. Nguyên nhân không nhất thiết nằm ở lệnh **GET** hay **SET**. Request còn phụ thuộc vào việc client có kết nối đến Redis không, kết nối có sẵn để sử dụng không, hệ thống có đang đợi tài nguyên trong pool không, và ứng dụng được phép chờ bao lâu.

Ba nhóm cấu hình cần phân biệt:

1. **Số kết nối và connection pool:** giới hạn tài nguyên mạng được phép mở hoặc mượn để xử lý công việc.
2. **Thời gian chờ:** quy định thời hạn thiết lập kết nối, lấy kết nối từ pool và chờ kết quả của lệnh Redis.
3. **Kiểm tra kết nối:** phát hiện Redis không truy cập được, kết nối bị hỏng, hoặc hệ thống chưa sẵn sàng phục vụ request.

Các nhóm này liên quan với nhau nhưng không thay thế nhau. Ví dụ, tăng pool từ 8 lên 64 không chữa được một Redis server đang xử lý lệnh chậm. Ngược lại, đặt command timeout 100 ms không giải quyết việc toàn bộ pool đang bị giữ bởi các thao tác blocking.

Trong Spring Data Redis, lựa chọn driver đặc biệt quan trọng. **Lettuce** hỗ trợ kết nối thread-safe và I/O bất đồng bộ; trong cấu hình phổ biến, nhiều thao tác có thể dùng chung một native connection. **Jedis** sử dụng mô hình thao tác đồng bộ và thường cần quản lý kết nối qua pool cho các request đồng thời. Vì thế, không thể chỉ nhìn vào một thuộc tính tên **max-active** rồi suy ra chính xác số kết nối Redis mà mọi ứng dụng đang sử dụng.

## 2. Đường đi của một lệnh từ Spring đến Redis

~~~text
HTTP / Scheduler / Message Consumer
              |
              v
        Application Service
              |
              v
   StringRedisTemplate / RedisTemplate
              |
              v
       RedisConnectionFactory
              |
       +------+-------+
       |              |
       v              v
     Lettuce         Jedis
  shared/dedicated   pool/connection
       |              |
       +------+-------+
              |
              v
         TCP / TLS
              |
              v
         Redis server
~~~

**RedisConnectionFactory** là abstraction tạo và cung cấp connection cho Spring Data Redis. **RedisTemplate** triển khai các operations cấp cao và điều phối sử dụng connection; thông thường service chỉ inject template thay vì tự mở và đóng socket.

Một lần gọi Redis có thể trải qua những giai đoạn:

~~~text
Chờ tài nguyên client / pool (nếu có)
             |
             v
Mở TCP/TLS đến Redis (nếu chưa có kết nối phù hợp)
             |
             v
Gửi lệnh
             |
             v
Redis xử lý và phản hồi
             |
             v
Spring chuyển response thành giá trị Java
~~~

Do đó, lỗi tại các giai đoạn khác nhau cần cách xử lý khác nhau. Ví dụ:

- Không thể thiết lập socket: xem **connect timeout**, DNS, route mạng, firewall, TLS hoặc Redis endpoint.
- Không lấy được tài nguyên pool: xem **pool size**, **max-wait**, số thao tác concurrent và connection có bị giữ lâu không.
- Lệnh gửi đi nhưng trả kết quả quá muộn: xem **command timeout**, network latency, tốc độ xử lý Redis và hàng đợi công việc phía client.
- Redis trả lỗi từ chối: xem xác thực, quyền ACL, số kết nối server đã chạm giới hạn hoặc command/data type không phù hợp.

## 3. Lettuce và Jedis: pooling không có cùng ý nghĩa

### 3.1. Lettuce: kết nối dùng chung trong cấu hình phổ biến

Spring Boot thường sử dụng **Lettuce** làm Redis client mặc định. **LettuceConnectionFactory** mặc định có thể chia sẻ một native connection thread-safe cho những thao tác Redis thông thường. Một connection Lettuce có thể phục vụ nhiều command đang được gửi bất đồng bộ theo khả năng của driver và Redis.

Vì vậy:

> Với Lettuce, số HTTP request đồng thời không mặc nhiên tương ứng với số socket Redis, và cấu hình pool không mặc nhiên buộc mỗi lệnh GET/SET phải mượn một connection riêng.

Những thao tác yêu cầu connection riêng hoặc có trạng thái khác, ví dụ **blocking command** và **transaction**, có thể cần dedicated connection. Khi bật pooling, pool có thể quản lý các connection dạng này theo cấu hình của connection factory. Nếu ứng dụng tùy chỉnh **shareNativeConnection** hoặc cách cấp phát connection, hành vi thực tế cũng thay đổi.

Lettuce vẫn có thể bị nghẽn dù số kết nối mở ít: một connection dùng chung có thể chứa nhiều lệnh đang chờ kết quả; lệnh quá nặng, client quá tải hoặc Redis xử lý chậm đều có thể làm độ trễ tăng. Cần quan sát cả số connection và latency, không chỉ tăng pool.

### 3.2. Jedis: đặc trưng của client đồng bộ

Với **Jedis**, thao tác Redis đồng bộ thường mượn một connection từ pool trong thời gian lệnh hoạt động, sau đó trả lại. Khi nhiều request cần dùng Redis cùng lúc, kích thước pool có ảnh hưởng trực tiếp tới số request có thể tiến hành đồng thời mà không đợi connection.

Nếu pool có tối đa 16 connection đang hoạt động mà 16 tác vụ đã giữ connection, tác vụ thứ 17 phải chờ, bị từ chối hoặc thất bại khi hết thời gian chờ, tùy cấu hình.

Tuy nhiên, tăng quá nhiều connection cũng không đồng nghĩa throughput tăng tuyến tính. Redis và hệ điều hành phải quản lý thêm socket, TLS, memory, scheduler và traffic. Cần chọn pool size dựa trên workload và hạ tầng thực tế.

### 3.3. Bảng so sánh

| Vấn đề | Lettuce | Jedis |
|---|---|---|
| Kiểu truy cập chính | Async/non-blocking ở tầng driver, có API synchronous qua Spring Data | Chủ yếu synchronous |
| Connection dùng chung | Native connection có thể được chia sẻ cho lệnh thông thường | Connection thường được mượn từ pool cho thao tác |
| Pool có bắt buộc cho mọi GET/SET? | Không, phụ thuộc cách dùng factory/driver | Thường là cách quản lý concurrent access |
| Trường hợp cần quan sát kỹ | Pending commands, latency, dedicated connections, blocking operations | Active/idle/waiting connections, pool exhaustion |
| Ý nghĩa max-active | Giới hạn số connection được pool quản lý khi pool thực sự được dùng | Giới hạn số connection hoạt động của pool |

**Kết luận thiết kế:** trước khi chỉnh các con số, xác định ứng dụng đang dùng **Lettuce hay Jedis**, Spring có đang sử dụng pool hay không, và những thao tác Redis nào dùng shared hoặc dedicated connection.

## 4. Các tham số connection pool cần hiểu

Khi dùng pool dựa trên **Apache Commons Pool 2**, các tham số thường gặp là:

| Tham số | Ý nghĩa | Khi cấu hình không phù hợp |
|---|---|---|
| **max-active** | Số connection tối đa có thể được pool cấp phát/đang hoạt động | Quá thấp: request phải chờ; quá cao: nhiều socket và tài nguyên Redis |
| **max-idle** | Số connection nhàn rỗi tối đa được pool giữ lại | Quá thấp: tốn chi phí tạo lại kết nối; quá cao: giữ socket dư |
| **min-idle** | Số connection nhàn rỗi mục tiêu pool cố duy trì khi cơ chế duy trì idle hoạt động | Quá cao: giữ nhiều socket không cần thiết |
| **max-wait** | Thời gian tối đa chờ mượn connection khi pool hết tài nguyên | Quá ngắn: từ chối nhanh dưới tải tăng đột biến; quá dài: request bị treo lâu |
| **time-between-eviction-runs** | Chu kỳ chạy tác vụ kiểm tra/loại bỏ connection idle trong pool | Cần cân bằng chi phí kiểm tra và tốc độ loại bỏ connection cũ |

Ví dụ một pool có:

~~~text
max-active = 12
max-idle   = 6
min-idle   = 2
max-wait   = 300 ms
~~~

Nếu 12 connection đang được mượn, thao tác thứ 13 cần connection từ pool sẽ đợi tối đa khoảng 300 ms để có connection trả lại. Nếu không có connection trong thời gian đó, thao tác có thể thất bại vì pool exhaustion. **300 ms này không phải thời gian tối đa để chính lệnh Redis thực thi**; nó là thời gian lấy tài nguyên từ pool.

**max-idle = 6** không có nghĩa pool chỉ được mở sáu connection. Khi tải tăng, nó vẫn có thể cấp phát tới mức **max-active = 12**. Khi connection được trả về, pool có thể thu gọn lượng idle theo chính sách của nó.

**min-idle = 2** là mục tiêu duy trì idle, không phải cam kết pool luôn có hai connection ở mọi thời điểm. Cơ chế khởi tạo/duy trì connection nhàn rỗi phụ thuộc cấu hình pool, tải và khả năng kết nối thực tế.

Trong một số cấu hình, **max-wait** âm thể hiện chờ vô hạn. Đây thường không phải lựa chọn tốt cho HTTP request cần thời gian phản hồi có giới hạn; việc request chờ lâu có thể khiến hệ thống tích tụ tác vụ khi Redis không phục vụ kịp.

## 5. Ba loại timeout dễ nhầm nhất

### 5.1. Connect timeout

**Connect timeout** giới hạn thời gian thiết lập kết nối đến Redis endpoint. Nó liên quan đến các bước như TCP connection và các giai đoạn kết nối mà driver xử lý.

Ví dụ Redis host không thể truy cập do lỗi route hoặc firewall, ứng dụng không nên chờ tùy ý mãi; cấu hình connect timeout giúp kết thúc nỗ lực kết nối có kiểm soát.

Connect timeout không tự giới hạn thời gian command **GET** chạy sau khi đã có socket.

### 5.2. Command timeout

**Command timeout** hoặc timeout chờ phản hồi là khoảng thời gian client cho phép một lệnh Redis hoàn thành. Nó có thể phát sinh khi mạng chậm, Redis bận, một command dài chạy trước đó, client bị ùn lệnh hoặc connection gặp sự cố.

Đặt timeout quá thấp so với độ trễ thực tế sẽ tạo lỗi giả dưới tải hoặc ở vùng mạng xa. Đặt quá cao sẽ kéo dài thời gian giữ tài nguyên và tăng độ trễ phục vụ request.

Một lỗi timeout **không chứng minh Redis chưa chạy lệnh**. Ví dụ client gửi **INCR** và timeout trước khi nhận response; Redis có thể đã tăng counter. Retry tùy tiện có thể tăng hai lần. Bất kỳ thao tác ghi nào cần retry đều phải xét tính idempotent hoặc có request ID chống xử lý trùng.

### 5.3. Pool max-wait

**Pool max-wait** giới hạn thời gian chờ có connection để mượn từ pool. Nó khác với command timeout. Một request có thể chờ pool trước, rồi lại chờ command sau; tổng thời gian quan sát từ HTTP có thể lớn hơn từng timeout riêng lẻ.

Ví dụ:

~~~text
Pool wait:     250 ms
Connect:       80 ms  (nếu phải mở connection)
Command:      400 ms
Mapping:       10 ms
-----------------------
Tổng gần:     740 ms
~~~

Các giai đoạn không phải lúc nào cũng xuất hiện, có thể chồng lấn tùy driver, và con số trên chỉ để minh họa. Nhưng nó cho thấy vì sao cần **ngân sách thời gian (latency budget) đầu-cuối**, không nên cấu hình mọi thành phần bằng cùng một số timeout rồi cho rằng HTTP request luôn kết thúc trước số đó.

### 5.4. Không nhầm các loại thời hạn

| Loại thời hạn | Điều gì hết hạn? | Ví dụ |
|---|---|---|
| **Connect timeout** | Nỗ lực mở kết nối | Không tới được Redis endpoint |
| **Command timeout** | Thời gian chờ kết quả command | GET trả lời quá chậm |
| **Pool max-wait** | Thời gian chờ mượn connection | Pool đang hết connection |
| **HTTP request timeout** | Thời gian request được xử lý | Gateway hủy request chậm |
| **Redis key TTL** | Tuổi thọ dữ liệu trong Redis | Session tự hết hạn sau 30 phút |
| **Shutdown timeout** | Thời gian client/driver có thể dành cho đóng tài nguyên | Ứng dụng dừng và giải phóng connection |

**TTL của key không phải timeout kết nối**. Một key có TTL 60 giây không khiến lệnh đọc key tự timeout sau 60 giây.

## 6. Cấu hình Spring Boot với Lettuce

### 6.1. Dependency

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

- **spring-boot-starter-data-redis** tích hợp Spring Data Redis và Lettuce trong cấu hình phổ biến.
- **commons-pool2** cung cấp cơ chế pool khi cấu hình pooling với driver/hạ tầng có hỗ trợ.
- **spring-boot-starter-actuator** cung cấp health indicator và các endpoint quan sát được cấu hình.

Không nhất thiết mọi ứng dụng Lettuce đều phải dùng pool. Nếu chỉ thực hiện các lệnh không blocking trên shared native connection, bật pool không tự đem lại lợi ích tỷ lệ thuận với kích thước pool.

### 6.2. Ví dụ application.yml

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: localhost
      port: 6379
      connect-timeout: 1s
      timeout: 2s
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
          time-between-eviction-runs: 30s

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Đây là **bộ giá trị minh họa**, không phải cấu hình chuẩn cho mọi workload:

- **client-type: lettuce** cho biết driver được chọn.
- **connect-timeout: 1s** đặt ngân sách thiết lập kết nối.
- **timeout: 2s** đặt ngân sách chờ command theo cơ chế client/Spring Boot tương ứng.
- **pool.enabled: true** yêu cầu sử dụng pooling khi hạ tầng có điều kiện hỗ trợ và có dependency cần thiết.
- **max-active: 16** là giới hạn của pool khi connection thực sự được quản lý qua pool.
- **max-wait: 300ms** giúp request không chờ pool vô hạn.
- **time-between-eviction-runs: 30s** cấu hình chu kỳ kiểm tra idle connection; một số hành vi còn phụ thuộc chính sách mặc định của Commons Pool.

Trong ứng dụng có shared connection của Lettuce, **max-active không có nghĩa 16 GET song song là giới hạn cứng**. Phải kiểm tra behavior của **LettuceConnectionFactory** và nhu cầu dedicated connection.

Nếu kết nối Redis ở môi trường khác, nên chuyển các giá trị như host, port và credential qua environment/config server. Không đặt mật khẩu thật vào tài liệu, repository hoặc log. Khi dùng Redis qua TLS, Sentinel hoặc Cluster, phải cấu hình topology và endpoint thực tế thay vì sao chép host local.

### 6.3. Không nhất thiết tự định nghĩa connection factory

Trong cấu hình phổ biến, Spring Boot tạo bean **LettuceConnectionFactory** và **StringRedisTemplate/RedisTemplate** dựa trên dependency cùng thuộc tính **spring.data.redis**. Service có thể inject trực tiếp template:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisCounterService {
    private final StringRedisTemplate redis;

    public RedisCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String counterName) {
        return redis.opsForValue().increment("counter:" + counterName);
    }
}
~~~

Không tạo một **LettuceConnectionFactory** mới trong mỗi request. Làm vậy bỏ qua lifecycle, cấu hình và tài nguyên client do Spring Boot quản lý, đồng thời có thể mở socket không cần thiết.

Nếu ứng dụng tự định nghĩa **RedisConnectionFactory**, hãy xác định rõ rằng auto-configuration của Spring Boot có thể lùi lại theo điều kiện bean. Khi đó cấu hình pool và timeout tùy biến phải được áp dụng vào factory do bạn tạo, không nên giả định mọi thuộc tính YAML vẫn tự động điều khiển một bean tự tạo.

## 7. Cấu hình với Jedis có gì khác?

Nếu chủ động sử dụng **Jedis**, ứng dụng cần dependency tương ứng và chọn client type phù hợp với phiên bản Spring Boot đang dùng.

Ví dụ các thuộc tính:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      connect-timeout: 1s
      timeout: 2s
      jedis:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
~~~

Khác biệt quan trọng nằm ở prefix **jedis.pool** so với **lettuce.pool**, và việc Jedis thường dựa trực tiếp hơn vào connection pool cho các thao tác synchronous.

Để chọn Jedis, project cần thực sự có driver **redis.clients:jedis** tương thích với bộ dependency của Spring Boot. Chỉ sửa YAML thành **client-type: jedis** khi classpath không có Jedis sẽ không tự tải driver và tạo một client mới.

Khi nhiều module cùng kết nối một Redis deployment, nên cộng ngân sách connection của toàn bộ instance, không chỉ nhìn riêng một service. Redis server có giới hạn client connection; vượt giới hạn này có thể khiến những kết nối mới bị từ chối.

## 8. Tính ngân sách kết nối trước khi chọn max-active

Giả sử một dịch vụ được chạy thành **6 instance** và mỗi instance có **pool max-active = 20**. Trong mô hình pool chuyên dụng, khả năng sử dụng tối đa của pool là:

\[
6 \times 20 = 120 \text{ pooled connections}
\]

Con số **120** chỉ là ngân sách lý thuyết của pool. Server còn phải phục vụ các kết nối khác như health checks, monitoring, administrative clients, pub/sub, connection không thuộc pool và những service khác. Với Lettuce có shared native connection, số socket thực tế không thể suy ra chỉ bằng tích này.

Một cách lập ngân sách:

~~~text
Connection budget toàn Redis deployment
    >= kết nối của service A
     + kết nối của service B
     + kết nối của background workers
     + monitoring/health/admin
     + phần dự phòng cho rollout và failover
~~~

Nếu có Redis Cluster, cần tính theo node/endpoint và topology, không coi mọi connection đều dồn vào một Redis process. Trong đợt rolling deployment, số pod/instance có thể tăng tạm thời vì phiên bản cũ và mới cùng hoạt động.

### Có nên đặt max-active càng lớn càng tốt?

Không. Một pool quá nhỏ tạo queue phía client, trong khi pool quá lớn tăng số socket và có thể đẩy lượng công việc vào Redis nhanh hơn khả năng xử lý. Một cấu hình phù hợp phải xem:

- Số request đồng thời thực sự truy cập Redis.
- Thời gian giữ một pooled connection của mỗi operation.
- Tỷ lệ command blocking, transaction hoặc Lua script nặng.
- Redis CPU, network, I/O, command latency và số connection còn được phép.
- Latency budget của ứng dụng và khả năng chịu tải khi Redis chậm.
- Số instance/pod hoạt động cùng lúc, kể cả khi scale-out và rollout.

Với pool cấp connection cho tác vụ synchronous, có thể dùng ước lượng ban đầu theo quan hệ:

\[
\text{Concurrency cần phục vụ} \approx
\text{requests/second} \times \text{thời gian giữ connection (giây)}
\]

Ví dụ một loại operation cần **200 request/giây**, mỗi request giữ connection trung bình **20 ms**:

\[
200 \times 0.020 = 4 \text{ connections trung bình}
\]

Đây là ước lượng trung bình, **không phải kích thước pool tối ưu**: phải thêm headroom cho burst, p95/p99 latency, chênh lệch workload và failover. Công thức cũng không dùng để tính trực tiếp số connection cho Lettuce shared-native-connection, vì nhiều command có thể chia sẻ một socket.

## 9. Kiểm tra Redis còn kết nối được không?

### 9.1. PING: kiểm tra liên lạc cơ bản

Redis hỗ trợ **PING**, thường trả **PONG** khi command được xử lý bình thường:

~~~text
Client  -> Redis: PING
Redis   -> Client: PONG
~~~

Đây là một phép kiểm tra đơn giản:

~~~bash
redis-cli -h localhost -p 6379 PING
~~~

Khi thành công:

~~~text
PONG
~~~

Nếu thất bại, cần phân biệt lỗi DNS, TCP, TLS, authentication, Redis server không chạy hoặc timeout. Lệnh **PING** chỉ chứng minh một đường kết nối và command cơ bản hoạt động ở thời điểm kiểm tra. Nó **không chứng minh** rằng mọi key có thể đọc, quyền ACL cho các lệnh nghiệp vụ là đúng, serializer tương thích, cluster topology ổn định hay Redis còn đủ năng lực xử lý tải.

Không chạy PING thủ công trước **mỗi** thao tác GET/SET. Cách đó thêm round trip và vẫn có khoảng thời gian giữa PING với command thực tế: Redis có thể hỏng sau PING hoặc lệnh thật vẫn bị timeout.

### 9.2. Kiểm tra bằng Spring Data Redis

Khi cần một phép kiểm tra thủ công ở cấp ứng dụng:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisConnectivityProbe {
    private final StringRedisTemplate redis;

    public RedisConnectivityProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean canPing() {
        try {
            String reply = redis.execute(
                (RedisCallback<String>) connection -> connection.ping()
            );
            return "PONG".equalsIgnoreCase(reply);
        } catch (DataAccessException ex) {
            return false;
        }
    }
}
~~~

Đoạn này dùng **RedisTemplate.execute(RedisCallback)** để Spring quản lý lấy/trả connection cho callback. Nếu tự gọi **connectionFactory.getConnection()** trực tiếp, phải quản lý vòng đời connection theo đúng contract; không được giữ mãi connection qua các request.

Probe có thể được dùng ở điểm kiểm tra được quản lý, nhưng không nên biến nó thành điều kiện bắt buộc trước từng truy vấn. Cũng không nên trả chi tiết exception, host nội bộ hoặc credential ra HTTP health endpoint công khai.

### 9.3. Dùng Spring Boot Actuator health

Với **spring-boot-starter-actuator** và cấu hình Redis phù hợp, Spring Boot có thể tự đăng ký Redis health indicator để kiểm tra Redis thông qua connection factory. Endpoint:

~~~text
GET /actuator/health
~~~

Ví dụ kết quả tổng quát:

~~~json
{
  "status": "UP"
}
~~~

Khi health indicator Redis có mặt và không truy cập được Redis, trạng thái tổng hợp có thể chuyển thành **DOWN**, tùy những indicator khác và cách cấu hình health groups. Không suy luận rằng mọi ứng dụng sẽ luôn có trường **redis** trong response công khai: điều đó phụ thuộc điều kiện auto-configuration, exposure và **show-details**.

Điều cần quan tâm là ý nghĩa của health endpoint đối với môi trường triển khai:

- **Liveness:** tiến trình ứng dụng còn sống và không bị kẹt không hồi phục. Không nên phụ thuộc trực tiếp vào tình trạng Redis bên ngoài nếu làm vậy khiến Kubernetes liên tục khởi động lại ứng dụng khi Redis tạm thời hỏng.
- **Readiness:** ứng dụng có đủ khả năng nhận traffic yêu cầu hay không. Nếu mọi API quan trọng bắt buộc cần Redis, readiness có thể bao gồm Redis health; nếu Redis chỉ là cache tùy chọn, readiness có thể vẫn **UP** và service sử dụng fallback.
- **Startup:** kiểm tra giai đoạn khởi động theo chính sách deploy; không nhất thiết đồng nhất với readiness/liveness.

Ví dụ Spring Boot bật các health probe dành cho môi trường orchestration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis
~~~

Đây là ví dụ cho ứng dụng **phụ thuộc Redis để xử lý request** và có Redis health indicator hợp lệ. Việc thêm **redis** vào readiness group là một quyết định vận hành, không phải thiết lập bắt buộc cho mọi service. Không thêm Redis vào liveness một cách máy móc.

## 10. Kiểm tra connection pool có đang khỏe không

**PING thành công không đồng nghĩa pool đang hoạt động tốt.** Redis có thể trả PONG nhưng hàng trăm request vẫn đợi mượn connection từ pool của ứng dụng.

Những tín hiệu nên quan sát:

| Tín hiệu | Điều có thể suy ra |
|---|---|
| **Active connections** gần max-active trong thời gian dài | Pool có thể đang bị dùng hết |
| **Idle connections** bằng 0 liên tục | Không còn connection dự trữ; cần xem wait time và tải |
| **Threads/request waiting for connection** tăng | Pool contention hoặc connection bị giữ quá lâu |
| **Borrow wait time** p95/p99 tăng | Độ trễ phát sinh trước cả khi gửi Redis command |
| **Redis command latency** tăng | Redis, driver hoặc mạng đang chậm |
| **Redis connected_clients** tăng bất thường | Có thể mở quá nhiều socket hoặc không quản lý lifecycle tốt |
| **Redis blocked_clients** tăng | Có nhiều client dùng blocking command; cần hiểu workload |
| **Error/timeout rate** tăng | Cần phân loại pool timeout, connect timeout, command timeout, Redis error |

Tính sẵn có của từng metric phụ thuộc driver, thư viện pool, Micrometer/Actuator và cách instrument ứng dụng. Không được giả định cứ thêm starter Actuator là mọi giá trị active/idle/pending đều tự xuất hiện dưới một tên metric cố định. Nếu cần đánh giá pool, hãy kiểm tra hệ đo của phiên bản đang dùng và bổ sung instrumentation tại connection pool/driver khi cần.

Một Redis instance có thể quản lý nhiều connection từ nhiều ứng dụng. Thao tác đọc các chỉ số server hữu ích:

~~~bash
redis-cli INFO clients
redis-cli CLIENT LIST
~~~

Kết quả **INFO clients** có các trường như **connected_clients**, **blocked_clients** (tùy Redis version). **CLIENT LIST** cho biết danh sách connection đang kết nối và một số metadata. Các command quản trị có thể cần quyền ACL; không bật quyền rộng cho application chỉ để dashboard đọc được chúng.

Để phân tích command bị chậm, có thể xem:

~~~bash
redis-cli SLOWLOG GET 10
~~~

**SLOWLOG** giúp thấy thời gian thực thi một số command phía Redis, nhưng **không phản ánh đầy đủ độ trễ mạng, chờ pool hoặc thời gian xếp hàng phía ứng dụng**. Vì vậy cần đối chiếu telemetry giữa service và Redis.

## 11. Khi nào kết nối bị giữ lâu?

Một điểm dễ bỏ qua là **thời gian giữ connection** có thể dài hơn thời gian Redis xử lý một lệnh đơn giản.

### 11.1. Blocking commands

Các lệnh như **BLPOP** hoặc những thao tác blocking khác có thể giữ một dedicated connection trong lúc chờ dữ liệu xuất hiện. Nếu nhiều consumer đồng thời sử dụng kết nối từ pool, chúng có thể chiếm phần lớn pool dù Redis không có CPU cao.

Khi dùng blocking command, xác định:

- Bao nhiêu consumer có thể đang chờ?
- Lệnh blocking có timeout ở Redis hay không?
- Chúng có chia sẻ pool với request thông thường không?
- Khi ứng dụng shutdown/cancel, connection có được giải phóng đúng cách không?

Đôi khi tách workload blocking khỏi workload request-response hoặc cấu hình connection factory riêng phù hợp sẽ dễ kiểm soát hơn việc chỉ tăng chung **max-active**.

### 11.2. Transaction

**MULTI/EXEC** và **WATCH** yêu cầu duy trì tính nhất quán của phiên kết nối khi thực hiện các bước liên quan. Nếu một transaction giữ connection trong lúc ứng dụng làm tính toán lâu hoặc gọi HTTP service khác, pool có thể bị chiếm giữ quá mức.

Giữ đoạn transaction ngắn, tránh chờ I/O bên ngoài giữa những bước cần cùng một connection và không để logic nghiệp vụ nặng nằm trong thời gian giữ tài nguyên Redis.

### 11.3. Pub/Sub

Kết nối dùng cho **Redis Pub/Sub** có vòng đời và cách sử dụng khác với lệnh GET/SET ngắn. Subscription có thể sống trong thời gian dài. Không nên gộp mọi loại kết nối vào cùng một phép tính “mỗi request dùng một connection”.

### 11.4. Slow Lua script và command lớn

Một Lua script chạy dài hoặc command duyệt dữ liệu lớn có thể khiến Redis phản hồi chậm cho những client khác. Tăng pool không làm script nhanh hơn. Nếu vấn đề ở thời gian Redis thực thi, cần tối ưu command, dữ liệu và cách chia workload.

## 12. Xử lý lỗi và retry sao cho an toàn

Trong Spring Data Redis, lỗi kết nối hoặc timeout thường được chuyển thành exception trong hệ thống Spring DataAccessException, với nguyên nhân gốc do driver hoặc Redis cung cấp. Cần ghi lại loại lỗi và nguyên nhân để phân biệt những đường xử lý:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class FeatureFlagReader {
    private final StringRedisTemplate redis;

    public FeatureFlagReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean isEnabled(String feature) {
        try {
            return "on".equals(
                redis.opsForValue().get("feature:" + feature)
            );
        } catch (DataAccessException ex) {
            // Giả định tính năng được phép fallback về OFF khi Redis lỗi.
            return false;
        }
    }
}
~~~

Ví dụ chỉ phù hợp khi business chấp nhận fallback **OFF**. Với dữ liệu thanh toán, quyền truy cập hoặc tồn kho, nuốt lỗi rồi thay bằng giá trị mặc định có thể tạo hành vi sai nghiêm trọng. Service phải đưa ra chính sách lỗi theo tính chất dữ liệu.

Khi dự định retry, phân loại command:

| Loại thao tác | Có thể retry tùy tiện? | Lý do |
|---|---|---|
| **GET** | Thường có thể theo chính sách giới hạn retry | Không làm thay đổi dữ liệu |
| **SET key fixedValue** | Có thể idempotent theo ngữ nghĩa đơn giản, nhưng còn phụ thuộc TTL/điều kiện | Việc ghi lại có thể đổi thời điểm hết hạn hoặc ghi đè thay đổi khác |
| **INCR** | Không | Retry có thể tăng hai lần nếu command đầu đã chạy |
| **LPUSH** | Không | Có thể thêm phần tử trùng |
| **SET NX EX** | Phải xét kết quả điều kiện và token | Lần retry không nhất thiết cho kết quả giống lần đầu |
| **Lua nghiệp vụ** | Phụ thuộc thiết kế idempotency của script | Script có thể đã thay đổi dữ liệu trước khi client timeout |

Tăng thời gian timeout không bảo đảm lệnh chỉ thực hiện một lần. Cần xác định request ID/idempotency key hoặc cơ chế kiểm soát tác dụng phụ nếu nghiệp vụ có retry tự động.

Khi Redis mất kết nối trong thời gian dài, hệ thống còn có thể tích tụ queue ở client. Giới hạn concurrency, dùng timeout hợp lý và có chính sách từ chối sớm giúp ngăn một Redis dependency chậm kéo theo cạn kiệt thread và memory của toàn bộ ứng dụng.

## 13. Chẩn đoán theo triệu chứng

### Tình huống A: Ứng dụng vừa khởi động đã không kết nối được

Những khả năng cần xét:

1. Host/port sai, DNS không phân giải được hoặc Redis chưa chạy.
2. Firewall/security group chặn kết nối.
3. Mismatch TLS hoặc xác thực/ACL.
4. Không đúng topology Redis Cluster/Sentinel.
5. Connect timeout quá thấp so với độ trễ mạng, hoặc endpoint thực sự không đáp ứng.

Hướng quan sát: log lỗi gốc, thử **PING** từ cùng môi trường mạng với ứng dụng, xem cấu hình endpoint và xác thực, đối chiếu tình trạng Redis server. Tăng pool sẽ không giải quyết các nguyên nhân này.

### Tình huống B: Tải thấp chạy tốt, tải cao báo hết pool

Những khả năng cần xét:

1. **max-active** quá thấp cho workload dùng dedicated connections.
2. Có blocking command, transaction hoặc tác vụ giữ connection lâu.
3. Connection không được trả đúng lifecycle do code sử dụng cấp thấp.
4. Redis command chậm làm thời gian giữ connection tăng.
5. Số request đến vượt mức hệ thống có thể phục vụ.

Hướng quan sát: active/idle/waiting connections, borrow wait p95/p99, số thao tác blocking, command latency và traffic rate. Chỉ tăng **max-active** sau khi xác định Redis server còn capacity và giới hạn connection tổng thể vẫn an toàn.

### Tình huống C: PING bình thường nhưng API vẫn timeout

Những khả năng cần xét:

- PING là command rất nhẹ, trong khi API gọi script hoặc đọc dữ liệu lớn.
- Ứng dụng chờ mượn pool trước khi tới Redis.
- Một số request chạy trong transaction/blocking connection.
- Serializer, mapping hoặc xử lý nghiệp vụ ở service tốn thời gian.
- Lệnh có thể đang xếp hàng phía client hoặc Redis.

Hướng quan sát: tracing từng giai đoạn, log/metrics pool, command latency, Redis SLOWLOG, số pending commands theo driver.

### Tình huống D: Thường xuyên gặp timeout sau khi Redis failover

Các khả năng:

- Client cần thời gian phát hiện endpoint/leader mới và tái kết nối.
- Lệnh gửi đúng thời điểm failover có kết quả không rõ ở phía client.
- Endpoint discovery hoặc DNS cập nhật chậm.
- Kết nối cũ bị đóng, trong khi pool/client đang tái thiết lập session.

Hướng xử lý: xác định topology/driver setup, thời gian phục hồi chấp nhận được, kiểm soát retry và idempotency. Không bảo đảm mọi write đều được thực thi đúng một lần chỉ bằng auto-reconnect.

## 14. Sơ đồ lựa chọn cách kiểm tra

~~~text
Redis operation chậm hoặc lỗi
             |
             v
Có lỗi thiết lập connection? ---- Có ----> Kiểm tra network, host, TLS,
             |                             auth, connect-timeout
            Không
             |
             v
Có đợi pool / hết connection? -- Có ----> Kiểm tra active, idle, waiters,
             |                             blocking/transaction, pool size
            Không
             |
             v
Command chờ response quá lâu? -- Có ----> Redis CPU, slow commands,
             |                             network, pending commands,
            Không                         command-timeout
             |
             v
Kiểm tra serializer, Redis data type,
quyền command, key/TTL và business logic
~~~

Sơ đồ chỉ là cách khoanh vùng ban đầu. Một lỗi có thể có nhiều nguyên nhân đồng thời: chẳng hạn command chậm làm connection bị giữ lâu hơn, khiến pool đầy, rồi request sau lại bị timeout trong khi chờ pool.

## 15. Kịch bản điều chỉnh cấu hình có kiểm soát

Giả sử một ứng dụng có 4 pod, dùng Jedis với:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      timeout: 2s
      connect-timeout: 1s
      jedis:
        pool:
          enabled: true
          max-active: 8
          max-idle: 8
          min-idle: 1
          max-wait: 100ms
~~~

Trong giờ cao điểm, một phần request trả lỗi vì không mượn được connection trong 100 ms, nhưng Redis server còn tài nguyên và command latency tương đối thấp.

Đây là tình huống **có thể** thử điều chỉnh pool: quan sát số connection active, thời gian giữ connection và mức tải cao nhất; sau đó thử tăng **max-active** có giới hạn hoặc giảm thời gian giữ connection của các thao tác. Nếu vẫn có nhiều connection idle hoặc command chậm, tăng pool có thể không phải hướng giải quyết.

Ví dụ ứng dụng scale lên 10 pod trong đợt rollout, mỗi pod có pool tối đa 16 connection. Ngân sách pool lý thuyết tăng thành **160 connection**, chưa tính kết nối phụ. Khi điều chỉnh, cần đối chiếu với giới hạn server và các dịch vụ khác cùng kết nối.

Với Lettuce shared connection, thao tác tính toán trên chỉ dùng để kiểm tra **pool được cấp phát thật sự**, không thay thế quan sát số socket thực tế tại Redis.

### Quy trình thử nghiệm hợp lý

1. Chọn workload mô phỏng giống hệ thống thực: tỷ lệ đọc/ghi, payload, command, thời gian giữ connection và số instance.
2. Ghi nhận baseline: p50/p95/p99 latency, error rate, timeout theo loại, active/idle/waiting connections và tài nguyên Redis.
3. Thay đổi **một nhóm tham số có mục đích**: pool size, max-wait hoặc command timeout; ghi rõ giả thuyết cần kiểm tra.
4. Quan sát cả latency phía client lẫn Redis server khi tải tăng, tải ổn định và sau khi hạ tải.
5. Kiểm tra tình huống Redis chậm, Redis tạm ngắt hoặc failover để thấy giới hạn retry, queue và cách health probe phản ứng.
6. Chọn cấu hình đáp ứng ngân sách thời gian và tài nguyên; giám sát lại khi số pod, topology hoặc workload thay đổi.

Không có một bộ **max-active/max-idle/timeout** tối ưu áp dụng cho tất cả ứng dụng. Một giá trị hợp lý cho service chỉ đọc key nhỏ trong cùng datacenter có thể hoàn toàn không phù hợp với service dùng blocking pop hoặc Redis ở mạng xa.

## 16. Những sai lầm phổ biến

**Sai lầm 1 — “Mỗi request cần một connection”.** Điều này không đúng cho mọi driver và mọi cấu hình Lettuce; native connection có thể được chia sẻ giữa các command thông thường.

**Sai lầm 2 — “Pool càng lớn càng nhanh”.** Pool lớn không cải thiện command chậm hoặc Redis quá tải và có thể gây thêm áp lực socket/memory.

**Sai lầm 3 — “Timeout nghĩa là command chắc chắn chưa chạy”.** Command ghi có thể đã thành công ở Redis khi client chưa nhận được phản hồi.

**Sai lầm 4 — “PING thành công là hệ thống khỏe”.** PING chỉ kiểm tra liên lạc cơ bản; không đo hết khả năng phục vụ nghiệp vụ, pool contention hay permission của command khác.

**Sai lầm 5 — “Có Actuator thì khỏi giám sát pool”.** Health endpoint và metric là hai loại tín hiệu khác nhau. Health indicator có thể UP trong khi borrow wait p99 tăng mạnh.

**Sai lầm 6 — “Bật pooling trong YAML chắc chắn thay đổi mọi connection”.** Hành vi phụ thuộc driver, factory, dependency và loại thao tác. Với Lettuce shared connection, pool có thể không nằm trên đường đi của mọi GET/SET.

**Sai lầm 7 — “Tăng command timeout để hết mọi lỗi”.** Nếu Redis đang quá tải hoặc pool đã hết connection, tăng timeout có thể khiến queue tích tụ và HTTP response chậm hơn.

**Sai lầm 8 — “Health readiness và liveness là một”.** Nếu liveness phụ thuộc một Redis dùng chung đang lỗi, orchestrator có thể khởi động lại hàng loạt pod dù chính ứng dụng không bị kẹt.

## 17. Bài tập suy luận

### Bài 1: Phân loại timeout

Một request mất 350 ms chờ pool, sau đó Redis trả lời trong 20 ms. Nếu **pool max-wait = 200 ms**, request sẽ gặp lỗi ở giai đoạn nào?

**Giải thích:** Request có thể thất bại ngay khi chờ pool vì vượt **max-wait**, trước khi command được gửi tới Redis. Việc Redis có thể xử lý command trong 20 ms không giúp request lấy được connection.

### Bài 2: Lettuce max-active = 8

Một service có 100 request GET đồng thời qua **StringRedisTemplate** dùng Lettuce mặc định. Có thể khẳng định chỉ tám GET được gửi tới Redis trong cùng thời điểm vì **max-active = 8** không?

**Giải thích:** Không. Các lệnh GET thông thường có thể dùng shared native connection, không mặc nhiên mượn connection từ pool cho từng request. Cần kiểm tra cấu hình factory và connection thực tế trước khi diễn giải **max-active**.

### Bài 3: Redis báo PONG, API báo chậm

Redis trả PONG trong vài mili giây nhưng endpoint lấy dữ liệu vẫn timeout. Bước chẩn đoán nào hữu ích hơn: tăng pool ngay hay đo thời gian chờ pool và độ trễ command?

**Giải thích:** Đo các giai đoạn trước. Sự khác biệt giữa PING và API có thể do pool, command, dữ liệu, serializer hoặc xử lý nghiệp vụ. Chỉ thay đổi pool khi có bằng chứng tài nguyên pool là nút nghẽn.

### Bài 4: Timeout sau INCR

Client gửi **INCR orders:count** nhưng gặp command timeout. Có nên retry ngay không?

**Giải thích:** Không nên retry mù vì lệnh đầu có thể đã được Redis thực thi, dẫn đến tăng hai lần. Nếu yêu cầu nghiệp vụ cần đúng một lần cho mỗi đơn hàng, phải thiết kế idempotency hoặc thao tác nguyên tử dựa trên ID duy nhất.

### Bài 5: Chọn health dependency

Một service dùng Redis chỉ để cache; khi Redis lỗi, service vẫn đọc dữ liệu từ database chính. Có nên đưa Redis vào liveness probe?

**Giải thích:** Thường không. Redis không khả dụng không đồng nghĩa ứng dụng đã chết. Nếu cache có fallback và service vẫn phục vụ được, readiness cũng có thể không cần phụ thuộc Redis. Quyết định tùy mức độ bắt buộc của Redis đối với API.

## 18. Ghi nhớ khi triển khai

Một thiết kế kết nối Redis đáng tin cậy không bắt đầu bằng một con số pool “thường dùng”, mà bằng **đặc điểm driver, vòng đời connection, loại command và ngân sách thời gian của nghiệp vụ**.

**Reactive/non-blocking, shared connection, pooling và command atomicity là các khái niệm khác nhau.** Với Lettuce, nhiều lệnh thông thường có thể dùng chung kết nối; với Jedis, pool thường ảnh hưởng trực tiếp hơn đến concurrency. **Connect timeout**, **command timeout** và **pool max-wait** giải quyết những giai đoạn chờ khác nhau, còn **PING/Actuator health** là tín hiệu kiểm tra khả năng truy cập ở một thời điểm cụ thể.

Khi phát sinh lỗi, hãy xác định request đang **chờ kết nối, chờ mượn pool hay chờ kết quả command**, đối chiếu metric phía client và Redis, rồi mới điều chỉnh cấu hình. Cách tiếp cận này giúp tránh tăng tài nguyên không cần thiết, giảm request bị treo lâu và phát hiện sự cố kết nối một cách có cơ sở.

# Chọn trình điều khiển theo mô hình đồng bộ, phản ứng và topology

Khi ứng dụng Java kết nối Redis qua Spring Data Redis, lựa chọn **Redis driver** ảnh hưởng đến cách ứng dụng quản lý kết nối, thực thi lệnh, xử lý đồng thời và kết nối tới các cụm Redis. Hai driver phổ biến trong hệ sinh thái Spring Data Redis là **Lettuce** và **Jedis**.

Không có một lựa chọn tối ưu cho mọi hệ thống. Cần xem xét đồng thời ba yếu tố:

1. **Mô hình lập trình:** ứng dụng đang thao tác Redis theo kiểu đồng bộ (imperative/blocking) hay phản ứng (reactive/non-blocking)?
2. **Topology của Redis:** ứng dụng kết nối một máy Redis, một cụm primary–replica có Sentinel, hay một Redis Cluster phân mảnh dữ liệu?
3. **Đặc tính vận hành:** số lượng kết nối, độ trễ, khả năng failover, timeout, bảo mật, tải đồng thời và mức độ phù hợp với Spring Boot/Spring Data Redis đang sử dụng.

Bài học này tập trung vào cách ra quyết định và cấu hình đúng driver trong **Spring Data Redis**, bao gồm ví dụ Java, cấu hình Spring Boot và những khác biệt dễ nhầm trong thực tế.

## 1. Phân biệt Redis server, driver và Spring Data Redis

Cùng một thao tác đọc giá trị từ Redis đi qua nhiều lớp:

~~~text
Controller / Service của ứng dụng
          |
          v
StringRedisTemplate / RedisTemplate
hoặc ReactiveRedisTemplate
          |
          v
RedisConnectionFactory
hoặc ReactiveRedisConnectionFactory
          |
          v
Lettuce / Jedis (Redis driver)
          |
          v
Giao thức Redis qua TCP / TLS
          |
          v
Redis standalone / Sentinel-managed Redis / Redis Cluster
~~~

- **Redis server** lưu trữ dữ liệu và thực thi lệnh Redis.
- **Driver** triển khai giao thức kết nối với Redis, gửi lệnh, nhận kết quả, quản lý tài nguyên mạng và xử lý các đặc điểm của topology.
- **Spring Data Redis** cung cấp các abstraction và template để ứng dụng thao tác dữ liệu qua driver.
- **Spring Boot** hỗ trợ cấu hình và tự tạo các bean kết nối khi dependency và cấu hình phù hợp có mặt.

Driver **không quyết định** ứng dụng dùng Redis String, Hash, List hay Sorted Set: các cấu trúc đó thuộc Redis. Driver cũng không quyết định cách đối tượng Java được serialize thành dữ liệu Redis; serializer là lựa chọn ở tầng Spring Data Redis.

Ví dụ, cùng một service gọi `StringRedisTemplate.opsForValue().get("session:42")` có thể sử dụng Lettuce hoặc Jedis ở phía dưới mà không cần thay đổi câu lệnh đọc. Sự khác biệt thể hiện ở mô hình kết nối, khả năng reactive và vận hành.

## 2. Hai driver: Lettuce và Jedis

### 2.1. Lettuce

**Lettuce** là Redis client dựa trên Netty, hỗ trợ các kiểu API đồng bộ, bất đồng bộ và reactive. Spring Data Redis sử dụng Lettuce cho cả API imperative và reactive; trong Spring Boot, Lettuce thường là lựa chọn mặc định của starter Redis.

Những đặc điểm nổi bật:

- **Hỗ trợ reactive:** tích hợp với Spring Data Redis qua `ReactiveRedisConnectionFactory` và các reactive template.
- **I/O không chặn ở tầng mạng:** dùng Netty và mô hình xử lý sự kiện cho kết nối, đồng thời vẫn cung cấp API đồng bộ nếu code gọi theo kiểu imperative.
- **Kết nối native có thể được dùng chung trong những trường hợp phù hợp:** Lettuce thiết kế kết nối thông thường để nhiều luồng sử dụng, giúp giảm số lượng kết nối TCP cần duy trì.
- **Hỗ trợ Redis Standalone, Sentinel và Cluster:** bao gồm các cơ chế khám phá node, chuyển hướng và cập nhật topology tùy cấu hình.
- **Có tùy chọn pooling:** hữu ích khi các thao tác cần kết nối riêng hoặc cần giới hạn tài nguyên; không có nghĩa mọi ứng dụng dùng Lettuce đều phải bật pool.

**Lưu ý:** “Lettuce dùng Netty” không có nghĩa mọi lời gọi qua `RedisTemplate` đều non-blocking. Một lời gọi imperative như `get()` vẫn chờ kết quả rồi mới trả về. Muốn có giao diện reactive từ tầng ứng dụng, phải dùng đúng reactive API.

### 2.2. Jedis

**Jedis** là Redis client lâu đời, cung cấp cách làm việc đồng bộ rất trực tiếp. Trong Spring Data Redis, tích hợp Jedis phục vụ **mô hình imperative**; các reactive template của Spring Data Redis không chạy trên `JedisConnectionFactory`.

Những đặc điểm nổi bật:

- **API đồng bộ đơn giản**, dễ hiểu khi ứng dụng dùng Spring MVC hoặc các service chạy trên thread thông thường.
- **Hỗ trợ topology Redis phổ biến**, gồm kết nối độc lập, Sentinel và Cluster, với cấu hình tương ứng.
- **Cần quản lý việc chia sẻ kết nối cẩn thận:** một kết nối Jedis riêng lẻ không nên được tùy ý dùng đồng thời bởi nhiều luồng. Pool hoặc cơ chế mượn/trả kết nối của factory thường phù hợp với ứng dụng nhiều request.
- **Không phải lựa chọn cho reactive Spring Data Redis:** nếu service cần `ReactiveRedisTemplate`, hãy sử dụng Lettuce.

Các phiên bản Jedis có thể tự phát triển thêm API riêng, nhưng **quyết định chọn driver trong Spring Data Redis phải dựa trên abstraction mà phiên bản Spring Data Redis đang hỗ trợ**, không chỉ dựa trên tên phương thức có trong thư viện Jedis độc lập.

### 2.3. Bảng so sánh để chọn nhanh

| Tiêu chí | Lettuce | Jedis |
|---|---|---|
| Sử dụng với `RedisTemplate` và `StringRedisTemplate` | Có | Có |
| Sử dụng với `ReactiveRedisTemplate` | Có | Không qua tích hợp Spring Data Redis |
| Phong cách phổ biến | Imperative, asynchronous, reactive | Imperative |
| Nền tảng I/O | Netty, hướng sự kiện | Kết nối đồng bộ |
| Chia sẻ native connection giữa các luồng | Thường hỗ trợ trong điều kiện phù hợp | Cần mượn/trả kết nối; không chia sẻ một connection tùy tiện |
| Connection pool | Tùy nhu cầu | Thường quan trọng với tải đồng thời |
| Standalone | Có | Có |
| Sentinel | Có | Có |
| Cluster | Có | Có |
| Lựa chọn mặc định thực tế cho ứng dụng Spring Boot mới | Thường ưu tiên | Khi có nhu cầu tương thích/vận hành cụ thể |

**Nguyên tắc chọn:** Nếu không có ràng buộc đặc biệt, Lettuce là điểm khởi đầu hợp lý vì hỗ trợ cả imperative lẫn reactive. Jedis phù hợp khi ứng dụng sử dụng imperative và đã có lý do rõ ràng để chuẩn hóa theo Jedis.

## 3. Chọn theo mô hình đồng bộ (imperative)

Trong mô hình imperative, lời gọi đọc/ghi Redis chỉ trả về sau khi nhận được kết quả hoặc xảy ra lỗi/timeout.

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounterService {

    private final StringRedisTemplate redis;

    public VisitCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long incrementViews(String articleId) {
        Long count = redis.opsForValue()
                .increment("article:" + articleId + ":views");

        if (count == null) {
            throw new IllegalStateException("Redis did not return a counter");
        }

        return count;
    }
}
~~~

Đây là mã imperative vì `increment(...)` trả về kết quả trực tiếp. Mã này phù hợp với Spring MVC, scheduled jobs, batch processing hoặc service thiết kế xoay quanh các thread thông thường.

Với workload này, **cả Lettuce và Jedis đều có thể hoạt động**. Quyết định tiếp theo dựa trên cấu hình hiện tại và đặc điểm khai thác:

- Dùng **Lettuce** nếu muốn một client chung cho nhiều loại service, hoặc có khả năng bổ sung thành phần reactive trong tương lai.
- Dùng **Jedis** nếu hệ thống đã chuẩn hóa cơ chế Jedis và có các quy ước pooling, timeout, quan sát và vận hành rõ ràng.
- Với một request gồm nhiều lời gọi Redis liên tiếp, việc đổi từ Jedis sang Lettuce **không tự động biến request thành bất đồng bộ**: service vẫn đang thực thi các lời gọi imperative.

### 3.1. Vì sao connection pool vẫn quan trọng?

Một request HTTP có thể tạo nhiều lời gọi Redis. Nếu mỗi request cần một kết nối độc lập, pool giúp giới hạn và tái sử dụng số kết nối TCP thay vì liên tục mở kết nối mới.

Với Lettuce, các thao tác bình thường có thể tận dụng kết nối được chia sẻ. Tuy nhiên, không nên mặc định rằng **mọi lệnh** an toàn/chính xác khi dùng chung một kết nối. Lệnh blocking, transaction, pipeline hoặc các yêu cầu cách ly trạng thái có thể cần kết nối riêng và cách quản lý riêng.

Với Jedis, pooling đặc biệt hữu ích để nhiều request mượn connection độc lập, sau đó trả lại pool. Pool nhỏ quá dễ gây chờ kết nối; pool quá lớn có thể tăng chi phí bộ nhớ, socket và áp lực lên Redis server.

Các đại lượng cần theo dõi gồm: số connection đang dùng, số connection đang chờ, timeout lấy connection, timeout lệnh, Redis latency và số request đồng thời.

## 4. Chọn theo mô hình reactive

Ứng dụng reactive xử lý công việc bằng các publisher như Reactor `Mono` và `Flux`. Khi làm việc với Spring Data Redis reactive, chọn **Lettuce**.

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveVisitCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveVisitCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> incrementViews(String articleId) {
        return redis.opsForValue()
                .increment("article:" + articleId + ":views");
    }
}
~~~

Hàm trả về `Mono<Long>` để cho pipeline quyết định thời điểm subscription và cách xử lý kết quả/lỗi. Việc giao tiếp Redis được thực hiện qua reactive connection của Lettuce.

### 4.1. Reactive đem lại điều gì?

Reactive có thể hữu ích khi ứng dụng duy trì nhiều thao tác I/O đồng thời mà không muốn giữ một platform thread chỉ để chờ mỗi kết quả. Mô hình này đặc biệt phù hợp với các service dựa trên Spring WebFlux và Reactor.

Tuy nhiên, reactive không bảo đảm mọi workload nhanh hơn. Redis thường có độ trễ lệnh thấp, và lợi ích phụ thuộc vào số request đang chờ I/O, cách xâu chuỗi thao tác và nguồn lực của toàn bộ pipeline.

Những nguyên tắc quan trọng:

- **Không chèn lời gọi Redis imperative vào event loop:** việc gọi `StringRedisTemplate` bên trong một chuỗi Reactor có thể chặn thread xử lý reactive.
- **Không dùng `.block()` trong luồng xử lý reactive:** điều này làm mất phần lớn lợi ích non-blocking và có thể gây lỗi trong những thread không cho phép blocking.
- **Không cho rằng `Mono` đồng nghĩa với thao tác tức thời:** lỗi mạng, timeout, retries và backpressure vẫn phải được thiết kế có chủ đích.
- **Không cho rằng mọi thành phần xung quanh đã reactive:** gọi API JDBC đồng bộ hoặc thư viện blocking từ cùng pipeline vẫn có thể làm nghẽn hệ thống.

Spring Data Redis reactive cung cấp API cho nhiều cấu trúc Redis, nhưng phạm vi toán tử và hành vi transaction/pipeline có thể khác với imperative. Hãy chọn API trực tiếp theo nghiệp vụ thay vì chuyển tên phương thức một cách máy móc.

### 4.2. Imperative trên Lettuce khác Reactive trên Lettuce

~~~text
Imperative service
  -> StringRedisTemplate
  -> LettuceConnectionFactory
  -> chờ kết quả trả về

Reactive service
  -> ReactiveStringRedisTemplate
  -> ReactiveRedisConnectionFactory (Lettuce)
  -> Mono / Flux chuyển tín hiệu kết quả
~~~

**Cùng driver, hai hợp đồng lập trình khác nhau.** Quyết định imperative/reactive cần thống nhất ở mức service hoặc request pipeline, không chỉ ở file cấu hình driver.

## 5. Chọn theo topology Redis

Topology mô tả Redis được triển khai thành những node nào và các node đảm nhiệm vai trò gì.

| Topology | Bản chất | Lựa chọn driver | Điều cần đặc biệt chú ý |
|---|---|---|---|
| **Standalone** | Một địa chỉ Redis chính để đọc/ghi | Lettuce hoặc Jedis cho imperative; Lettuce cho reactive | Host, port, timeout, TLS, bảo mật |
| **Primary–replica** | Primary nhận ghi, replica sao chép dữ liệu | Lettuce hoặc Jedis, tùy cấu hình topology | Độ trễ replica, chuyển vai trò và read consistency |
| **Sentinel** | Sentinel giám sát và giúp tìm primary hiện hành | Lettuce hoặc Jedis cho imperative; Lettuce cho reactive | Sentinel nodes, tên master, discovery và failover |
| **Redis Cluster** | Dữ liệu phân chia theo hash slot trên các node | Lettuce hoặc Jedis cho imperative; Lettuce cho reactive | Cluster-aware client, MOVED/ASK, slot, multi-key |
| **Managed Redis qua proxy** | Nhà cung cấp che một phần topology sau endpoint/proxy | Theo giao thức và hướng dẫn của dịch vụ | Tương thích lệnh, discovery, TLS, failover, endpoint |

### 5.1. Standalone: kết nối đơn giản nhất

Ở Standalone, ứng dụng thường biết host và port của một Redis node.

~~~text
Spring Boot ---- Lettuce/Jedis ---- Redis:6379
~~~

Các vấn đề chính là độ tin cậy kết nối, timeout, bộ nhớ, persistence và phương án xử lý khi node không khả dụng.

Lựa chọn:

- Spring MVC/imperative: Lettuce hoặc Jedis.
- Spring WebFlux/reactive: Lettuce.
- Nhu cầu đơn giản, chưa có yêu cầu đặc biệt: bắt đầu bằng Lettuce như cấu hình mặc định Spring Boot.

### 5.2. Primary–replica và Sentinel: tính sẵn sàng cao

Replica sao chép dữ liệu từ primary, nên có thể được dùng cho đọc trong một số chiến lược. Nhưng replication thường **bất đồng bộ**, do đó đọc từ replica có thể thấy dữ liệu cũ ngay sau khi ghi vào primary.

Sentinel cung cấp cơ chế giám sát và hỗ trợ tự động chuyển vai trò primary khi lỗi xảy ra. Ứng dụng muốn theo dõi primary hiện hành phải cấu hình driver có khả năng **Sentinel discovery** thay vì ghim mãi một địa chỉ primary cũ.

~~~text
          +--> Sentinel A
Ứng dụng -+--> Sentinel B ---> phát hiện primary mới
          +--> Sentinel C

             Redis primary
                    |
             Redis replica(s)
~~~

Sentinel và replication **không phân mảnh dữ liệu**: các replica vẫn giữ bản sao của tập dữ liệu do primary quản lý. Sentinel giải quyết bài toán failover; không thay thế Cluster khi cần phân phối keyspace qua nhiều shard.

Khi chọn driver cho Sentinel, cần kiểm tra:

- Client hỗ trợ Sentinel và nhận đúng **tên master** do Sentinel quản lý.
- Danh sách endpoint Sentinel đủ để kết nối nếu một Sentinel mất kết nối.
- Xác thực Sentinel và xác thực Redis node có thể là **hai bộ thông tin khác nhau**.
- Timeout và chiến lược retry không khiến ứng dụng chờ vô hạn khi failover.
- Cách đọc từ replica, nếu bật, phải chấp nhận khả năng lag so với primary.

### 5.3. Redis Cluster: phân mảnh theo hash slot

Redis Cluster tổ chức keyspace thành **16.384 hash slot**. Mỗi khóa ánh xạ vào một slot và slot được một primary node của cluster chịu trách nhiệm. Driver cluster-aware phải khám phá topology và xử lý chỉ dẫn chuyển hướng của Redis như `MOVED` và `ASK`.

~~~text
                         Redis Cluster
                         16.384 slots
                                |
                  +-------------+-------------+
                  |             |             |
               Primary A     Primary B     Primary C
               slots ...     slots ...     slots ...
                  |             |             |
               Replica A     Replica B     Replica C
~~~

Một kết nối trực tiếp bằng client chỉ hiểu Standalone không đủ để hoạt động ổn định với Redis Cluster. Ứng dụng cần cấu hình đúng **cluster nodes** và để client theo dõi topology.

**Điểm khác biệt quan trọng với ứng dụng:** không phải mọi thao tác qua nhiều khóa đều được phép khi các khóa nằm ở các slot khác nhau.

Ví dụ:

~~~redis
MSET cart:42 "..." profile:42 "..."
~~~

Trong Redis Cluster, lệnh multi-key đòi hỏi các key cùng slot có thể gặp lỗi `CROSSSLOT` nếu điều kiện không được đáp ứng.

Dùng **hash tag** để cố ý đặt các khóa liên quan vào cùng slot khi nghiệp vụ thật sự cần thao tác multi-key:

~~~text
cart:{user-42}
profile:{user-42}
preferences:{user-42}
~~~

Phần nằm trong dấu ngoặc nhọn, ở đây là `user-42`, được dùng để tính hash slot của các khóa đó. Không cần đặt mọi khóa của hệ thống vào chung một hash tag vì sẽ làm mất lợi ích phân tán tải của Cluster.

Redis Cluster cũng chỉ hỗ trợ logical database số 0; không thiết kế cơ chế shard bằng cách đổi chỉ số `SELECT` như ở Standalone.

### 5.4. Vì sao chọn driver không đủ khi đổi topology?

Giả sử ứng dụng trước đây sử dụng Lettuce với Standalone và chuyển sang Cluster. Tên driver vẫn là Lettuce, nhưng địa chỉ khởi tạo, topology discovery, slot routing và nhiều thao tác multi-key đều cần được xem lại.

Tương tự, chuyển từ Standalone sang Sentinel không chỉ là thay hostname thành hostname Sentinel. Ứng dụng cần biết **master name** và danh sách Sentinel nodes. Đây là cấu hình topology, tách biệt với lựa chọn Lettuce/Jedis.

## 6. Cấu hình Spring Boot với Lettuce

Các ví dụ tiếp theo dùng nhánh cấu hình `spring.data.redis` của Spring Boot 3.x. Chúng minh họa cách cấu hình driver và topology; khóa/giá trị đăng nhập thực tế nên được nạp từ biến môi trường hoặc secret manager.

### 6.1. Dependency mặc định và Standalone

Trong dự án Gradle dùng Spring Boot starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter này thường đưa Lettuce vào classpath và Boot tự cấu hình factory tương ứng. Ví dụ `application.yml`:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

- `connect-timeout` giới hạn thời gian thiết lập kết nối.
- `timeout` đặt giới hạn thời gian thao tác Redis theo cấu hình được hỗ trợ.
- Thực tế cần điều chỉnh timeout theo độ trễ mạng và SLO của ứng dụng, tránh đặt giá trị quá thấp hoặc quá cao.

Nếu Redis bật TLS, cấu hình SSL cần phù hợp với endpoint và chứng chỉ server, ví dụ:

~~~yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
~~~

Không bật SSL chỉ vì hệ thống triển khai trên cloud; phải kiểm tra endpoint Redis có thực sự yêu cầu TLS hay không.

### 6.2. Kết nối Sentinel

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.internal:26379
          - sentinel-2.example.internal:26379
          - sentinel-3.example.internal:26379
      connect-timeout: 2s
      timeout: 3s
~~~

Tên `mymaster` phải khớp tên nhóm primary được Sentinel quản lý. Các địa chỉ trên chỉ minh họa. Nếu môi trường yêu cầu mật khẩu/TLS khác nhau giữa Sentinel và Redis node, cấu hình riêng theo khả năng được phiên bản Spring Boot và Spring Data Redis hỗ trợ.

Để kết nối Sentinel thành công, các node phải trả về địa chỉ Redis mà ứng dụng **thực sự truy cập được**; tên host đúng trong mạng nội bộ Redis nhưng không thể định tuyến từ ứng dụng vẫn dẫn đến lỗi.

### 6.3. Kết nối Redis Cluster

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-1.example.internal:6379
          - redis-2.example.internal:6379
          - redis-3.example.internal:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
~~~

Các node chỉ là điểm khởi tạo khám phá cluster. Sau khi kết nối, driver phải biết node nào đang phục vụ từng hash slot.

Cluster thay đổi topology khi node failover hoặc slot di chuyển. Lettuce có khả năng **cluster topology refresh**; các tùy chọn làm mới theo chu kỳ hoặc theo tín hiệu thích ứng cần được đặt phù hợp với phiên bản thư viện, tốc độ failover và cấu hình mạng. Nếu dùng node address không truy cập được từ ứng dụng, việc liệt kê seed node ban đầu chưa chắc đã giải quyết vấn đề.

Cần phân biệt:

- **Sentinel nodes** là địa chỉ để hỏi primary của một nhóm replication.
- **Cluster nodes** là địa chỉ seed để khám phá các shard của Redis Cluster.

Hai cách cấu hình phục vụ hai topology khác nhau và không nên được ghép tùy tiện trong cùng một factory.

## 7. Cấu hình Spring Boot với Jedis

Khi chủ động chọn Jedis cho Spring Data Redis imperative, thêm thư viện Jedis và có thể loại Lettuce khỏi starter để classpath nhất quán.

Ví dụ với Gradle Groovy:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-data-redis') {
        exclude group: 'io.lettuce', module: 'lettuce-core'
    }

    implementation 'redis.clients:jedis'
}
~~~

Với Spring Boot quản lý dependency versions, thông thường không cần tự ghi phiên bản Jedis. Cấu hình chọn client:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Các thuộc tính topology như `sentinel.master`, `sentinel.nodes` hoặc `cluster.nodes` vẫn mô tả Redis tương ứng. Điều quan trọng là driver có trên classpath và Spring Boot tạo đúng `JedisConnectionFactory`.

**Không đưa `ReactiveRedisTemplate` vào cấu hình Jedis-only.** Ứng dụng reactive nên dùng Lettuce và factory reactive của Spring Data Redis.

### 7.1. Pooling với Jedis

Nếu dùng pool qua cơ chế auto-configuration, cấu hình có thể dùng nhóm `spring.data.redis.jedis.pool`. Ví dụ:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      jedis:
        pool:
          max-active: 32
          max-idle: 16
          min-idle: 2
          max-wait: 2s
~~~

Các thuộc tính pool cần dependency pooling phù hợp (thường là Apache Commons Pool 2) và phải được kiểm tra trên phiên bản Boot đang dùng. Các số trong ví dụ là giá trị minh họa, **không phải cấu hình chuẩn cho mọi môi trường**.

Khi pool cạn, request có thể chờ connection hoặc gặp lỗi timeout. Nếu ứng dụng đang xử lý 200 request đồng thời, không thể suy ra ngay rằng cần pool 200 connections: còn phụ thuộc thời gian giữ connection, số lệnh mỗi request và cách dùng pipeline.

## 8. Factory, template và serializer: phạm vi trách nhiệm

Một ứng dụng thường không tạo trực tiếp Lettuce/Jedis connection ở mọi service, mà sử dụng các bean Spring.

| Thành phần | Vai trò |
|---|---|
| `LettuceConnectionFactory` | Tạo/quản lý kết nối Spring Data Redis bằng Lettuce; hỗ trợ ngữ cảnh imperative và reactive |
| `JedisConnectionFactory` | Cung cấp kết nối imperative bằng Jedis |
| `RedisTemplate<K, V>` | Thao tác imperative với key/value và serializer tự chọn |
| `StringRedisTemplate` | Biến thể imperative tiện lợi cho dữ liệu chuỗi |
| `ReactiveRedisTemplate<K, V>` | Thao tác Redis bằng Reactor |
| `ReactiveStringRedisTemplate` | Reactive template cho dữ liệu chuỗi |

Ví dụ service imperative dùng `StringRedisTemplate` có thể hoạt động với bất kỳ factory imperative tương thích nào. Nhưng nếu service cần `ReactiveStringRedisTemplate`, cấu hình phải cung cấp `ReactiveRedisConnectionFactory` phù hợp.

Nếu tự khai báo bean `RedisConnectionFactory`, cấu hình đó có thể thay thế hoặc ảnh hưởng tới auto-configuration của Spring Boot. Chỉ tự xây factory khi thật sự cần tùy chỉnh sâu như read preference, client options, topology refresh hoặc quản lý kết nối đặc thù.

**Serializer độc lập với driver.** Thay Jedis bằng Lettuce không làm Redis tự biến JSON String thành Redis Hash, và không tự sửa dữ liệu đã serialize bằng codec khác. Khi chuyển driver, nên giữ chiến lược serializer nhất quán để không tạo dữ liệu khó đọc hoặc khác định dạng giữa các phiên bản service.

## 9. Cách ra quyết định có hệ thống

Có thể đi theo cây quyết định sau:

~~~mermaid
flowchart TD
    A[Ứng dụng cần truy cập Redis] --> B{Spring Data Redis reactive?}
    B -->|Có| C[Chọn Lettuce]
    B -->|Không| D{Có ràng buộc Jedis hiện hữu?}
    D -->|Không| C
    D -->|Có| E[Chọn Jedis cho imperative]
    C --> F{Redis triển khai theo topology nào?}
    E --> F
    F -->|Standalone| G[Cấu hình host và port]
    F -->|Sentinel| H[Cấu hình master và Sentinel nodes]
    F -->|Cluster| I[Cấu hình cluster nodes và kiểm tra hash slots]
    G --> J[Thiết lập timeout và quan sát]
    H --> J
    I --> J
~~~

Thứ tự này tránh một sai lầm phổ biến: quyết định “Jedis hay Lettuce” rồi cho rằng topology sẽ tự hoạt động theo mọi dạng Redis. **Driver và topology là hai quyết định liên quan nhưng khác nhau.**

### 9.1. Tình huống A: Spring MVC và Redis cache đơn giản

Ứng dụng Spring MVC dùng Redis để cache thông tin sản phẩm và session. Redis chạy một node, nghiệp vụ không yêu cầu reactive.

**Lựa chọn đề xuất:** Lettuce mặc định với `StringRedisTemplate` hoặc `RedisTemplate`, timeout rõ ràng và TTL theo nghiệp vụ. Không cần bật pool chỉ vì nhiều request nếu kết nối chia sẻ của Lettuce đáp ứng được cách sử dụng.

### 9.2. Tình huống B: API Spring WebFlux có nhiều thao tác Redis đồng thời

API WebFlux dùng `Mono`/`Flux`, muốn đọc nhiều key và phối hợp kết quả mà không chặn event loop.

**Lựa chọn đề xuất:** Lettuce + `ReactiveRedisTemplate` / `ReactiveStringRedisTemplate`. Kiểm tra cả các dependency khác trong request pipeline để không vô tình đưa lời gọi blocking vào event loop.

### 9.3. Tình huống C: Batch Java hiện có đang dùng Jedis

Một batch imperative lâu năm đã dùng Jedis với pool và cơ chế giám sát ổn định. Không có nhu cầu reactive.

**Lựa chọn có cơ sở:** tiếp tục Jedis nếu nó đáp ứng nhu cầu, đồng thời quản lý pool, timeout và topology. Không cần thay driver chỉ vì một thư viện khác có API reactive.

### 9.4. Tình huống D: Redis chuyển sang Sentinel

Ứng dụng trước đây cấu hình host của primary cố định. Môi trường mới dùng Sentinel để failover.

**Thay đổi cần thiết:** chọn driver hỗ trợ Sentinel, cấu hình master name và các Sentinel nodes, thiết lập timeout thích hợp, kiểm tra xác thực và việc ứng dụng nhận đúng địa chỉ primary sau failover. Chỉ đổi host thành địa chỉ Sentinel là chưa đủ.

### 9.5. Tình huống E: Redis Cluster phục vụ quy mô lớn

Hệ thống phân phối dữ liệu qua nhiều primary, cần client chuyển hướng đúng khi slot thay đổi.

**Lựa chọn đề xuất:** Lettuce cho hệ thống mới, hoặc Jedis nếu đã được chuẩn hóa cho imperative; cả hai phải dùng cấu hình cluster-aware. Kiểm tra các lệnh multi-key, hash tag, cách định tuyến đến node và việc topology refresh.

## 10. Những nhầm lẫn cần tránh

### “Lettuce là reactive, Jedis là synchronous”

Đây là cách nói thiếu chính xác. **Lettuce hỗ trợ cả imperative lẫn reactive**, còn **Spring Data Redis dùng Jedis cho imperative**. Driver Lettuce không tự động làm mọi method trở thành non-blocking.

### “Dùng WebFlux thì mọi thao tác Redis đều reactive”

Sai nếu ứng dụng vẫn inject `StringRedisTemplate` và gọi lệnh blocking trong event loop. Reactive phải được thể hiện bằng API/luồng thực thi đúng từ service tới client.

### “Bật connection pool càng lớn càng nhanh”

Pool quá lớn có thể lãng phí tài nguyên và làm quá tải Redis. Pool chỉ giúp quản lý kết nối; nó không giảm độ phức tạp của lệnh Redis và không thay thế tối ưu hóa số round-trip.

### “Sentinel chính là Cluster”

Sentinel phục vụ giám sát và failover cho topology replication. Cluster phân mảnh keyspace theo slot. Một hệ thống có replica không mặc nhiên là Redis Cluster.

### “Redis Cluster hoạt động như một Redis Standalone lớn”

Cluster có quy tắc slot, chuyển hướng, multi-key và hạn chế về logical database. Các lệnh nghiệp vụ cần phù hợp với những quy tắc này.

### “Đã có replica thì đọc sau ghi luôn nhất quán”

Replication có thể trễ. Nếu nghiệp vụ đòi hỏi ngay sau ghi phải đọc thấy dữ liệu mới nhất, cần cân nhắc routing về primary hoặc thiết kế nhất quán riêng.

### “Driver chịu trách nhiệm bảo đảm không mất dữ liệu”

Driver quyết định cách kết nối và gửi lệnh. Khả năng persistence, replication, failover và mức độ chấp nhận mất dữ liệu phụ thuộc vào Redis server, cấu hình triển khai và kiến trúc nghiệp vụ. Retry ở client cũng không mặc nhiên an toàn cho mọi lệnh có side effect.

## 11. Vận hành và xử lý sự cố theo lựa chọn driver

Lựa chọn driver nên đi kèm mục tiêu quan sát và chính sách xử lý lỗi.

| Triệu chứng | Câu hỏi nên kiểm tra | Hướng xử lý |
|---|---|---|
| Không tạo được kết nối | Host/port, TLS, ACL, firewall, DNS, kết nối tới đúng endpoint? | Xác minh mạng và xác thực trước khi đổi driver |
| Request chờ lâu | Có blocking command, thiếu timeout, pool cạn hay Redis latency cao? | Đo thời gian từng lớp; rà soát pool/timeout |
| `MOVED` hoặc `ASK` bất thường | Client có chạy chế độ Cluster và nhận đúng node address? | Cấu hình cluster-aware, topology refresh, routing |
| `CROSSSLOT` | Lệnh nhiều key có nằm ở cùng hash slot? | Điều chỉnh thao tác, đặt hash tag khi thật sự cần |
| Failover Sentinel không phục hồi | Master name, Sentinel nodes, auth, địa chỉ primary mới có đúng? | Kiểm tra discovery và tính truy cập được của node mới |
| Đọc thấy dữ liệu cũ | Có đọc từ replica, replication lag? | Xem lại read preference và yêu cầu nhất quán |
| WebFlux chậm hoặc báo blocking | Có gọi Redis imperative trên event loop? | Dùng reactive API của Lettuce; kiểm tra cả pipeline |
| Tăng số connection bất thường | Đã cấu hình pool hoặc tạo factory/client quá nhiều lần? | Tái sử dụng factory, giới hạn kết nối và quan sát pool |

### 11.1. Timeout và retry cần phản ánh nghiệp vụ

Có ít nhất ba khoảng thời gian khác nhau cần phân biệt:

1. **Thời gian tạo kết nối:** phát hiện endpoint không kết nối được.
2. **Thời gian thực thi lệnh:** giới hạn thời gian chờ phản hồi từ Redis.
3. **Thời gian chờ connection trong pool:** giới hạn khi toàn bộ connection đã được mượn.

Một timeout có thể xảy ra sau khi server thực tế đã xử lý lệnh nhưng trước khi client nhận được phản hồi. Vì vậy, retry một lệnh **ghi có tác động** như tăng bộ đếm hoặc trừ tồn kho phải cân nhắc tính idempotent. Không thể giả định “timeout nghĩa là Redis chưa chạy lệnh”.

### 11.2. Những chỉ số vận hành hữu ích

- Độ trễ lệnh Redis, tỷ lệ lỗi và tỷ lệ timeout.
- Số connections đang mở, pool active/idle/waiters nếu dùng pool.
- Số lần reconnect và các đợt failover.
- Redis CPU, memory, eviction, replication lag và số client đang kết nối.
- Phân bố key/slot, độ trễ node và chuyển slot nếu dùng Redis Cluster.
- Thời gian phản hồi của API ở tầng ứng dụng, không chỉ latency tại Redis.

Các chỉ số này giúp quyết định khi nào cần chỉnh timeout/pool, xem lại topology, hoặc tối ưu số lệnh mỗi request. Chỉ thay driver không sửa được mọi điểm nghẽn.

## 12. Ghi nhớ khi áp dụng vào dự án Spring Data Redis

Một lựa chọn driver tốt phải **phù hợp với mô hình lập trình và topology Redis thực tế**:

- **Imperative:** Lettuce và Jedis đều có thể dùng. Lettuce thường là lựa chọn mặc định hợp lý; Jedis hữu ích khi có ràng buộc sử dụng rõ ràng.
- **Reactive:** dùng Lettuce qua `ReactiveRedisConnectionFactory` và reactive template; tránh gọi Redis imperative trên event loop.
- **Standalone:** cấu hình host/port, timeout và bảo mật.
- **Sentinel:** cấu hình tên master và các Sentinel nodes, quan tâm đến discovery, failover và tính nhất quán khi đọc replica.
- **Cluster:** dùng client cluster-aware, hiểu slot, xử lý topology changes và hạn chế của lệnh multi-key.

Sau khi chọn driver, ứng dụng vẫn cần sử dụng đúng Redis template, serializer, timeout, connection strategy và cơ chế quan sát. **Lettuce hay Jedis là lựa chọn ở tầng kết nối; mô hình đồng bộ/phản ứng và kiến trúc Redis quyết định cách lựa chọn đó được vận hành hiệu quả.**

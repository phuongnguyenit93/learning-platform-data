# Ranh giới giữa Spring Cache, Spring Session và Spring Data Redis

Trong một ứng dụng Spring Boot, cả **Spring Cache**, **Spring Session** và **Spring Data Redis** đều có thể sử dụng cùng một Redis server. Vì vậy, người mới học dễ nhầm rằng ba thư viện có cùng nhiệm vụ, hoặc chỉ cần thêm dependency Redis là Spring tự động lưu cache, session và mọi đối tượng vào Redis.

Thực chất, mỗi thư viện làm việc ở **một ranh giới trách nhiệm khác nhau**:

- **Spring Cache** quản lý việc *tái sử dụng kết quả tính toán hoặc truy vấn* thông qua một API cache thống nhất.
- **Spring Session** quản lý *vòng đời và trạng thái phiên làm việc* (session) của người dùng, thay thế nơi lưu session mặc định của máy chủ web.
- **Spring Data Redis** cung cấp *cách ứng dụng kết nối và thao tác với Redis*: gửi lệnh, xử lý key/value, cấu trúc dữ liệu, Redis repository, và các thành phần tích hợp để những thư viện khác dùng Redis làm nơi lưu trữ.

**Một Redis server là hạ tầng; cache, session và dữ liệu Redis là ba mục đích sử dụng.** Việc chúng có thể cùng lưu key vào Redis không làm thay đổi hợp đồng API, chính sách hết hạn, tính nhất quán hoặc cách xử lý lỗi của từng thành phần.

## 1. So sánh nhanh ba phạm vi

| Tiêu chí | Spring Cache | Spring Session | Spring Data Redis |
|---|---|---|---|
| Câu hỏi chính | "Có thể dùng lại kết quả của phương thức này không?" | "Làm sao nhận diện và duy trì phiên của người dùng qua các HTTP request?" | "Làm sao đọc, ghi và khai thác cấu trúc dữ liệu Redis?" |
| Abstraction trung tâm | `Cache`, `CacheManager`, interceptor cho phương thức | `Session`, `SessionRepository`, `HttpSession`/`WebSession` tích hợp | `RedisConnectionFactory`, `RedisTemplate`, `StringRedisTemplate`, Redis repositories |
| Đường vào phổ biến | `@Cacheable`, `@CachePut`, `@CacheEvict` | `HttpSession`, session cookie, Spring Security session | `opsForValue()`, `opsForHash()`, `opsForZSet()`, `@RedisHash` |
| Redis có bắt buộc không? | Không; có thể dùng Caffeine, ConcurrentMap, v.v. | Không; có thể lưu session bằng JDBC hoặc công nghệ khác | Có; mục tiêu của module là giao tiếp với Redis |
| Redis được dùng qua đâu? | `RedisCacheManager` là một implementation của `CacheManager` | Redis-backed `SessionRepository` do Spring Session cung cấp | Các API Redis trực tiếp và các adapter Redis |
| Loại dữ liệu điển hình | Kết quả truy vấn danh mục, cấu hình ít thay đổi | Giỏ hàng trong phiên, thuộc tính session, security context khi dùng session | Counter, leaderboard, rate limiting, marker tạm thời, dữ liệu domain phù hợp Redis |
| Hết hạn | TTL của **từng cache entry**, theo cấu hình cache | Thời gian **không hoạt động của session** và cơ chế expiration của session | Ứng dụng chủ động đặt TTL, hoặc tự quyết định không đặt |
| Ai quyết định key? | Cache name + key do cache operation tạo | Session repository quản lý session ID và key nội bộ | Mã ứng dụng/repository thiết kế key |
| Khi giá trị biến mất | Thường có thể tính/truy vấn lại từ nguồn dữ liệu chuẩn | Phiên có thể hết hạn; người dùng mất trạng thái phiên, có thể phải đăng nhập lại | Tùy nghĩa nghiệp vụ của key: có thể chỉ mất số đếm tạm, hoặc mất dữ liệu quan trọng |
| Dữ liệu nhất quán với DB? | Cần thiết kế invalidation/TTL | Không phải cơ chế đồng bộ dữ liệu nghiệp vụ với DB | Do ứng dụng tự thiết kế; Redis không tự đồng bộ DB |
| Việc không giải quyết | Không tạo session phân tán | Không làm cache cho mọi phương thức nghiệp vụ | Không tự gắn `@Cacheable` hoặc thay thế session của web server |

Có thể hiểu ba thư viện qua ba câu lệnh khác nhau:

~~~java
// Spring Cache: hỏi cache trước khi chạy phương thức nghiệp vụ
@Cacheable(cacheNames = "products", key = "#id")
public ProductView getProduct(long id) { ... }

// Spring Session: truy cập trạng thái phiên bằng API HTTP
httpSession.setAttribute("language", "vi");

// Spring Data Redis: thao tác Redis theo ý đồ nghiệp vụ
stringRedisTemplate.opsForValue().increment("metrics:page-views");
~~~

Cả ba đoạn mã **có thể cùng tạo key trong Redis**, nhưng cơ chế sở hữu các key đó khác nhau.

## 2. Vị trí trong kiến trúc Spring

~~~text
                        ỨNG DỤNG SPRING BOOT
 +--------------------------------------------------------------------+
 |                                                                    |
 |  Gọi phương thức nghiệp vụ             HTTP request / session       |
 |                 |                               |                  |
 |                 v                               v                  |
 |     Spring Cache abstraction          Spring Session               |
 |     @Cacheable / @CacheEvict           SessionRepositoryFilter      |
 |                 |                       SessionRepository           |
 |                 v                               |                  |
 |         RedisCacheManager              Redis-backed repository      |
 |                 |                               |                  |
 |                 +---------------+---------------+                  |
 |                                 |                                  |
 |  Mã nghiệp vụ ──> StringRedisTemplate / RedisTemplate / Repositories|
 |                                 |                                  |
 |                                 v                                  |
 |                      RedisConnectionFactory                       |
 |                           (ví dụ Lettuce)                         |
 +---------------------------------+----------------------------------+
                                   |
                                   v
                        Redis server / Sentinel / Cluster
~~~

Sơ đồ thể hiện việc **chia sẻ lớp kết nối**, không có nghĩa các thành phần gọi lẫn nhau:

- `@Cacheable` không yêu cầu Spring Session và không đi qua `SessionRepository`.
- Spring Session không cần `@Cacheable` hay `RedisCacheManager` để lưu phiên.
- Gọi `RedisTemplate` trực tiếp không làm Spring Cache tự nhận ra một phương thức cần cache; cũng không làm Spring Session tự sinh session.
- `RedisCacheManager` và Redis-backed `SessionRepository` đều có thể tận dụng `RedisConnectionFactory` do Spring Boot cấu hình. Mỗi thành phần vẫn có định dạng key, serializer và quy tắc hết hạn riêng.

Lưu ý: Redis Cache thường thao tác qua `RedisCacheWriter` và Redis connection. Không nên giả định rằng chỉnh serializer của một bean `RedisTemplate` bất kỳ cũng sẽ tự động thay đổi định dạng cache hoặc session.

## 3. Spring Cache: ranh giới của việc lưu kết quả phương thức

### 3.1. Spring Cache là abstraction

Spring Cache hướng tới mã nghiệp vụ: trước khi thực thi một phương thức, Spring kiểm tra xem kết quả theo một **cache key** đã tồn tại chưa.

~~~text
Client gọi CatalogService.getProduct(42)
                    |
                    v
              Cache interceptor
                    |
              Có key 42 không?
               /           \
              Có           Không
              |              |
         Trả kết quả     Gọi phương thức thật
         từ cache        -> truy vấn DB/API
                              |
                              v
                         Ghi kết quả
                         vào cache
                              |
                              v
                         Trả kết quả
~~~

Spring Cache cung cấp một hợp đồng thống nhất; nơi lưu thật có thể là bộ nhớ trong một JVM hoặc Redis. Khi chọn Redis, Spring dùng một `CacheManager` thích hợp, thường là `RedisCacheManager` trong ứng dụng Spring Boot sử dụng Spring Data Redis.

### 3.2. Ví dụ @Cacheable và @CacheEvict

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final ProductRepository productRepository;

    public CatalogService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Cacheable(cacheNames = "catalogProducts", key = "#id")
    public ProductView getProduct(Long id) {
        Product product = productRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Not found: " + id));

        return new ProductView(product.getId(), product.getName());
    }

    @CacheEvict(cacheNames = "catalogProducts", key = "#id")
    public void renameProduct(Long id, String newName) {
        Product product = productRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Not found: " + id));
        product.setName(newName);
        productRepository.save(product);
    }
}
~~~

Trong ví dụ, `ProductRepository`, `Product` và `ProductView` là các kiểu nghiệp vụ giả định. Luồng mong đợi:

1. Lần đầu gọi `getProduct(42)`: cache miss, chạy truy vấn repository và cache kết quả.
2. Lần tiếp theo với cùng key: có thể lấy kết quả từ cache mà không gọi lại repository.
3. Sau `renameProduct(42, ...)`: entry `catalogProducts` cho key `42` bị xóa; lần đọc tiếp theo có thể tải tên mới.

Nếu repository đọc dữ liệu từ hệ thống khác hoặc nếu có đường ghi bỏ qua `renameProduct`, cache **không tự biết** dữ liệu nguồn đã thay đổi. Cần thiết kế TTL, eviction, versioned key hoặc cơ chế phát sự kiện invalidation thích hợp.

### 3.3. Những annotation liên quan

| Annotation | Tác dụng | Điều cần chú ý |
|---|---|---|
| `@Cacheable` | Đọc cache trước, chạy phương thức nếu miss, sau đó có thể lưu kết quả | Áp dụng cho đường gọi đi qua Spring proxy/interceptor |
| `@CachePut` | Luôn thực thi phương thức rồi cập nhật cache với kết quả | Không dùng như một cách thay thế chung cho `@Cacheable` |
| `@CacheEvict` | Xóa một entry hoặc nhiều entry trong cache | Có thể dùng `allEntries = true` khi cần xóa toàn cache; phải cân nhắc chi phí |
| `@Caching` | Gom nhiều thao tác cache trên một phương thức | Hữu ích khi phải xóa nhiều cache name |
| `@CacheConfig` | Khai báo cấu hình cache dùng chung cho một class | Không tự bật cơ chế cache |

Có thể điều khiển cache condition với `condition` và quyết định có lưu kết quả hay không với `unless`. Ví dụ:

~~~java
@Cacheable(
    cacheNames = "catalogProducts",
    key = "#id",
    unless = "#result == null"
)
public ProductView getProduct(Long id) {
    // ...
}
~~~

**Một số ranh giới kỹ thuật quan trọng:**

- Trong chế độ proxy mặc định, một phương thức của bean gọi trực tiếp phương thức `@Cacheable` khác trong **chính đối tượng đó** (*self-invocation*) có thể đi vòng qua interceptor, vì vậy annotation không phát huy tác dụng.
- `@EnableCaching` cần có để kích hoạt cơ chế cache bằng annotation. Chỉ khai báo dependency cache chưa đủ.
- Redis Cache dùng TTL riêng theo cấu hình của CacheManager. TTL này **không phải** thời gian tồn tại của HTTP session.
- Cache không tự động tham gia giao dịch của database. Nếu xóa cache trước khi transaction DB commit rồi transaction rollback, có thể tạo cửa sổ bất nhất. Cần phối hợp thời điểm invalidation với giao dịch theo thiết kế ứng dụng.
- Khi Redis không truy cập được, lời gọi cache có thể ném exception theo `CacheErrorHandler` hiện hành. Không nên mặc định rằng cache lỗi thì hệ thống chắc chắn sẽ tự truy vấn DB.

### 3.4. Khi nào Spring Cache là đúng công cụ?

Phù hợp khi giá trị **có thể tái tạo** từ nguồn đáng tin cậy: danh mục sản phẩm, cấu hình hiển thị, thông tin tham khảo, kết quả truy vấn đắt, kết quả tính toán lặp lại.

Không nên coi cache entry là nguồn dữ liệu chuẩn duy nhất cho đơn hàng, số dư tài khoản hay nhật ký nghiệp vụ quan trọng. Nếu entry bị hết hạn hoặc bị xóa, ứng dụng phải biết khôi phục hoặc chấp nhận mất giá trị đó.

## 4. Spring Session: ranh giới của trạng thái phiên HTTP

### 4.1. Vấn đề khi không có session tập trung

Trong ứng dụng web servlet truyền thống, session thường do servlet container quản lý. Nếu lưu trong bộ nhớ của một instance, session có thể không có ở instance khác.

~~~text
                Browser
            Cookie session ID
                    |
                Load balancer
                 /        \
                v          v
          Spring App A   Spring App B
          memory A       memory B

   Request 1 đến A -> lưu session trên A
   Request 2 đến B -> B không thấy session của A
~~~

Có thể dùng sticky session tại load balancer để giảm một phần vấn đề, nhưng vẫn phụ thuộc instance và việc khôi phục trạng thái khi instance mất. Spring Session cho phép đặt trạng thái phiên vào kho chia sẻ, ví dụ Redis:

~~~text
                Browser
            Cookie session ID
                    |
                Load balancer
                 /        \
                v          v
          Spring App A   Spring App B
                 \        /
                  \      /
                Spring Session
                       |
                       v
                  Shared Redis
                  Session store
~~~

Cả hai app instance có thể truy xuất cùng session khi chúng dùng chung cấu hình Spring Session và nhận cùng session ID hợp lệ.

### 4.2. Spring Session thay đổi điều gì?

Spring Session tích hợp vào pipeline của web framework, ví dụ qua `SessionRepositoryFilter` trong ứng dụng Servlet. Code controller vẫn có thể dùng `HttpSession` như trước:

~~~java
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profile")
public class ProfileController {

    @GetMapping("/language")
    public String language(HttpSession session) {
        String language = (String) session.getAttribute("language");
        return language == null ? "vi" : language;
    }

    @GetMapping("/language/en")
    public String chooseEnglish(HttpSession session) {
        session.setAttribute("language", "en");
        return "saved";
    }
}
~~~

Controller không cần biết session được lưu trong memory, Redis hay JDBC. Khi cài Redis-backed Spring Session và cấu hình phù hợp, việc lấy/lưu session được chuyển cho `SessionRepository`.

Trình tự khái quát:

1. Browser gửi cookie chứa session ID.
2. Spring Session đọc ID, tìm bản ghi session trong Redis và cung cấp `HttpSession` tương ứng.
3. Controller hoặc Spring Security đọc/ghi thuộc tính session.
4. Session repository lưu lại thay đổi theo chế độ lưu được cấu hình.
5. Khi session bị vô hiệu hóa hoặc quá thời gian không hoạt động, session không còn có giá trị.

Spring Session thường có thể lưu **Spring Security context** nếu ứng dụng dùng xác thực dựa trên HTTP session. Nhưng Spring Session **không tự làm login, phân quyền hay phát hành JWT**; đây là trách nhiệm của Spring Security và giao thức xác thực mà ứng dụng chọn.

### 4.3. Dữ liệu thuộc session và TTL

Session chứa dữ liệu gắn với **phiên của một client**, chẳng hạn lựa chọn ngôn ngữ, giỏ hàng phiên, các thuộc tính cần duy trì giữa request hoặc trạng thái đăng nhập khi dùng session authentication.

Thời hạn của session thường dựa vào **max inactive interval**: sau thời gian không hoạt động nhất định, session bị xem là hết hạn. Việc lưu TTL và chỉ mục expiration trong Redis là trách nhiệm của implementation Spring Session, có thể khác nhau theo repository mode hoặc phiên bản.

Khác với cache một kết quả truy vấn:

- Cache entry có thể được thay mới theo policy của từng cache.
- Session gắn với một ID và có thao tác `invalidate()`, tạo session, đổi session ID và quản lý vòng đời.
- Xóa cache của `catalogProducts` **không** tự xóa session đang đăng nhập.
- Gọi `session.invalidate()` **không** tự xóa các kết quả `@Cacheable` liên quan tới người dùng.

Nếu dùng WebFlux reactive, Spring Session làm việc với `WebSession` và các thành phần reactive phù hợp. Các ví dụ `HttpSession` ở đây dành cho ứng dụng Spring MVC/Servlet.

### 4.4. Tính bảo mật và độ tin cậy

- Session ID là một **credential** để tham chiếu tới session; cần bảo vệ cookie bằng HTTPS, `Secure`, `HttpOnly` và chính sách `SameSite` phù hợp.
- Không ghi session ID, nội dung xác thực hoặc dữ liệu nhạy cảm ra log không kiểm soát.
- Cần cấu hình serialization cho các thuộc tính được lưu. Việc đưa object tùy ý vào session có thể gây lỗi khi deploy phiên bản ứng dụng mới hoặc khi deserialize.
- Redis bị lỗi có thể làm request cần session thất bại. Redis bị evict key session có thể khiến người dùng mất session trước thời hạn mong đợi.
- Có session chung trong Redis **không có nghĩa** mọi request vẫn thành công không gián đoạn khi failover Redis, và cũng không bảo đảm tuyệt đối không mất trạng thái mới nhất.

Trong hệ thống dùng JWT hoàn toàn **stateless** mà server không giữ phiên, Spring Session có thể không cần thiết. Nếu ứng dụng dùng `HttpSession` hoặc stateful authentication, Spring Session giải quyết một bài toán khác với token tự chứa.

## 5. Spring Data Redis: ranh giới của thao tác Redis

### 5.1. Tầng Redis API

Spring Data Redis không quyết định sẵn một key là cache, session hay dữ liệu nghiệp vụ. Nó cung cấp công cụ để ứng dụng dùng Redis:

- `RedisConnectionFactory` tạo và quản lý cơ chế kết nối qua driver như **Lettuce**.
- `RedisTemplate<K, V>` cung cấp API thực thi thao tác Redis, kèm serializers.
- `StringRedisTemplate` là RedisTemplate tối ưu cho key và value dạng chuỗi.
- `opsForValue()`, `opsForHash()`, `opsForList()`, `opsForSet()`, `opsForZSet()` tương ứng các nhóm cấu trúc dữ liệu Redis.
- Hỗ trợ Pub/Sub, Redis Streams, Lua scripts, pipelines và một số tính năng transaction tùy API.
- Redis repositories với `@RedisHash` cung cấp cách ánh xạ object vào Redis theo mô hình repository trong những trường hợp phù hợp.

Sử dụng Spring Data Redis trực tiếp là lựa chọn thích hợp khi nghiệp vụ cần **cấu trúc dữ liệu hoặc lệnh Redis cụ thể**, chẳng hạn sorted set cho leaderboard, counter, marker có TTL, hàng đợi dựa trên Redis Streams hoặc kênh publish/subscribe.

### 5.2. Ví dụ thao tác trực tiếp

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class MetricsService {

    private final StringRedisTemplate redis;

    public MetricsService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long recordProductView(long productId) {
        String key = "metrics:product-views:" + productId;
        return redis.opsForValue().increment(key);
    }

    public void rememberLastViewed(long userId, long productId) {
        String key = "user:last-viewed:" + userId;
        redis.opsForValue().set(
                key,
                Long.toString(productId),
                Duration.ofHours(24)
        );
    }
}
~~~

Ở đây:

- `increment` gọi thao tác Redis phù hợp với giá trị số.
- `set(..., Duration)` ghi một value cùng TTL do **ứng dụng quyết định**.
- Cả hai key **không tự trở thành Spring Cache entry**.
- Cả hai key **không trở thành HTTP session** và không được Spring Session quản lý vòng đời.

Các số đếm như trên thích hợp cho số liệu có thể chấp nhận rủi ro mất dữ liệu theo đặc tính Redis đang triển khai. Nếu nghiệp vụ yêu cầu số liệu chính xác, kiểm toán được hoặc giao dịch xuyên database, cần kiến trúc lưu trữ và đồng bộ chặt chẽ hơn.

### 5.3. Redis repositories có phải Spring Cache không?

Không. Ví dụ một entity Redis:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("tempCart")
public class TempCart {

    @Id
    private String id;

    private String ownerId;

    // Constructors, getters và setters
}
~~~

Repository cho entity này, nếu được cấu hình đúng, có thể là một interface:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface TempCartRepository
        extends CrudRepository<TempCart, String> {
}
~~~

Đây là **lưu trữ object theo mô hình repository**, không phải việc Spring tự cache kết quả của một phương thức bất kỳ. Nếu muốn xóa bản ghi, thay đổi TTL hoặc bảo đảm dữ liệu theo quy tắc nghiệp vụ, trách nhiệm vẫn thuộc thiết kế repository và ứng dụng.

Nếu trộn cả `CrudRepository<TempCart, String>` lẫn `@Cacheable` trên một phương thức trả về TempCart, ta có **hai tầng lưu trữ khác nhau**: Redis repository là nơi lấy bản ghi, còn cache có thể lưu thêm kết quả phương thức. Dùng cả hai cần mục đích rõ ràng để tránh dữ liệu trùng và invalidation phức tạp.

### 5.4. Không nhầm RedisTemplate với CacheManager

Một lỗi cấu hình thường gặp là thay đổi serializer của `RedisTemplate` rồi cho rằng cache và session cũng chuyển sang JSON.

Trên thực tế:

- `RedisTemplate` có serializers do template đó cấu hình.
- `RedisCacheManager` dùng `RedisCacheConfiguration`/`RedisCacheWriter`, có serialization và prefix riêng.
- Spring Session Redis sử dụng serializer và mô hình lưu session của Spring Session; nếu muốn tùy chỉnh, có cơ chế cấu hình serializer riêng, ví dụ bean được đặt tên `springSessionDefaultRedisSerializer` trong cấu hình hỗ trợ tương ứng.

Do đó, ba thành phần **có thể cùng chia sẻ kết nối nhưng không tự chia sẻ chính sách serialization**. Khi thay cấu trúc dữ liệu JSON/JDK serialization, cần xét khả năng đọc key cũ và kế hoạch migration.

## 6. Ví dụ một ứng dụng Spring Boot dùng cả ba

Một ứng dụng bán hàng có:

- API đọc danh mục: cache kết quả từ cơ sở dữ liệu.
- Web UI lưu lựa chọn ngôn ngữ và trạng thái session.
- Chức năng số đếm lượt xem dùng trực tiếp Redis.

Cả ba có thể dùng chung Redis connection trong một ứng dụng Spring Boot nhưng vẫn được tổ chức theo ba API khác nhau.

### 6.1. Các dependency chính

Ví dụ Maven (phần `<dependencies>` trong dự án Spring Boot):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
</dependencies>
~~~

Trong hệ sinh thái Spring Boot 3.x được quản lý phiên bản bởi Spring Boot BOM/parent, thông thường không cần khai báo version riêng cho các dependency trên.

Phân vai dependency:

- `spring-boot-starter-data-redis`: kết nối Redis và các API Spring Data Redis.
- `spring-boot-starter-cache`: hạ tầng cache abstraction; khi có Redis và cấu hình tương ứng, ứng dụng có thể dùng RedisCacheManager.
- `spring-session-data-redis`: repository session dùng Redis; với ứng dụng web và auto-configuration phù hợp, Spring Boot có thể cấu hình Spring Session.
- `spring-boot-starter-web`: minh họa ứng dụng Servlet dùng `HttpSession`.

Khi chỉ cần một tính năng, không bắt buộc kéo cả ba dependency. Ví dụ một REST API cache sản phẩm bằng Redis không cần `spring-session-data-redis` chỉ vì nó có cache.

### 6.2. Cấu hình minh họa

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379

  cache:
    type: redis
    cache-names:
      - catalogProducts
    redis:
      time-to-live: 10m
      cache-null-values: false

  session:
    timeout: 30m
    redis:
      namespace: shop:session
~~~

Ví dụ sử dụng namespace riêng cho session, TTL của cache là 10 phút và thời gian không hoạt động của session là 30 phút. Hai khoảng thời gian không can thiệp lẫn nhau.

Đây là các thuộc tính minh họa cho cấu hình Spring Boot 3.x; hãy đối chiếu cấu hình hỗ trợ trong phiên bản Boot/Spring Session thực tế khi triển khai. Trong dự án thật có thể bổ sung username/password, ACL, TLS hoặc cấu hình Sentinel/Cluster ở phần kết nối Redis.

Để bật annotation caching:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {
}
~~~

Không cần gắn `@EnableCaching` lên controller. Đây là cấu hình của application context. Spring Session được bật theo cơ chế auto-configuration phù hợp của Spring Boot khi đã thêm starter/module session và web stack; nếu tự khai báo enable annotation hoặc bean repository, cần hiểu cơ chế override cấu hình mặc định để tránh tạo cấu hình xung đột.

### 6.3. Ba request trong cùng ứng dụng

**Request A — đọc sản phẩm:**

~~~text
GET /products/42
 -> CatalogService.getProduct(42)
 -> Spring Cache kiểm tra catalogProducts::42
 -> Nếu miss: đọc DB và lưu cache 10 phút
 -> Trả ProductView
~~~

**Request B — cập nhật lựa chọn ngôn ngữ:**

~~~text
GET /profile/language/en
 Cookie: SESSION=<session-id>

 -> Spring Session tìm session theo session ID
 -> ProfileController gọi session.setAttribute("language", "en")
 -> Spring Session lưu session theo chính sách của nó
 -> Lần truy cập sau có thể đọc lại "en"
~~~

Tên cookie ở đây minh họa Spring Session Servlet với cookie resolver mặc định thường dùng `SESSION`; tên và thuộc tính cookie có thể được cấu hình lại.

**Request C — đếm lượt xem:**

~~~text
POST /metrics/products/42/view
 -> MetricsService.recordProductView(42)
 -> StringRedisTemplate INCR metrics:product-views:42
 -> Trả giá trị counter
~~~

Ba request có thể ghi xuống cùng Redis server, nhưng:

- A chịu trách nhiệm cho cache invalidation và TTL cache.
- B chịu trách nhiệm cho session ID, session expiry và security context.
- C chịu trách nhiệm cho key schema, TTL và tính đúng đắn của counter.

**Không có việc tự động đồng bộ chéo** giữa ba keyspace. Một request logout không tự xóa key counter; một thao tác `@CacheEvict` không tự xóa session; gọi `RedisTemplate.delete()` với một key bất kỳ không thông báo cho các abstraction khác cập nhật trạng thái nội bộ.

## 7. Keyspace, serializer và TTL: ba ranh giới dễ bị bỏ quên

### 7.1. Phân vùng key theo trách nhiệm

Ví dụ các key có thể thấy trong Redis:

~~~text
catalogProducts::42                 # Spring Cache (minh họa key mặc định)
shop:session:sessions:<session-id>  # Spring Session (minh họa keyspace)
metrics:product-views:42            # Spring Data Redis trực tiếp
~~~

Tên key chính xác có thể khác tùy cache prefix, namespace, kiểu repository, Spring Session implementation và version. Không nên xây logic nghiệp vụ dựa vào định dạng nội bộ của Spring Session.

Gợi ý quy ước:

| Chủ sở hữu key | Ví dụ prefix | Ai được phép quản lý vòng đời? |
|---|---|---|
| Spring Cache | `cache:catalogProducts:` | CacheManager, cache operations, chính sách invalidation |
| Spring Session | `shop:session:` | Spring Session |
| Redis trực tiếp | `shop:metrics:`, `shop:ranking:` | Component nghiệp vụ tương ứng |

Sử dụng prefix riêng giảm nguy cơ key trùng nhau và giúp theo dõi số lượng key, TTL, bộ nhớ. **Prefix không tạo ra cơ chế cách ly bảo mật hoặc tài nguyên**: nếu cần bảo đảm tài nguyên khác nhau, hãy cân nhắc Redis deployment riêng.

### 7.2. Mỗi tầng tự cấu hình serializer

Ví dụ, cache có thể dùng JSON để lưu DTO, session có thể dùng serializer dành riêng cho session attributes, còn `StringRedisTemplate` lưu chuỗi UTF-8. Không nên kỳ vọng cùng một key/value có thể được cả ba tầng đọc lẫn nhau.

Một số vấn đề cần dự kiến:

- Nếu dùng JDK serialization, việc đổi class, `serialVersionUID` hoặc dependency có thể gây lỗi deserialize giữa các phiên bản ứng dụng.
- Nếu dùng JSON, phải xác định cách biểu diễn type, ngày giờ, polymorphism và mức độ tin cậy của dữ liệu đầu vào.
- Với Spring Session, session attributes cần tương thích giữa các app instance và giữa các đợt deploy cuốn chiếu.
- Nếu thay serializer, key cũ vẫn tồn tại đến khi hết TTL hoặc bị xóa; reader mới có thể không hiểu dữ liệu cũ.

Để thay đổi định dạng dữ liệu an toàn, cần coi đó là migration dữ liệu hoặc thay key namespace có kiểm soát, không đơn thuần chỉ sửa một bean.

### 7.3. TTL có ý nghĩa khác nhau

Giả sử tại cùng thời điểm Redis có ba giá trị:

| Key | TTL | Lý do hết hạn |
|---|---|---|
| `catalogProducts::42` | 10 phút | Cache chấp nhận dùng lại kết quả trong một khoảng thời gian |
| Session có ID `abc` | 30 phút không hoạt động | Session hết giá trị nếu người dùng không tiếp tục tương tác |
| `user:last-viewed:7` | 24 giờ | Quy tắc của tính năng lưu sản phẩm xem gần đây |

Một request đọc sản phẩm không tự gia hạn session. Một request dùng session cũng không tự gia hạn TTL của cache sản phẩm. Một lệnh Redis trực tiếp muốn đặt TTL phải dùng lệnh/API tương ứng hoặc tự thiết kế policy.

TTL của session còn có thể gắn với các key phục vụ expiration/index bên trong Spring Session; không nên suy ra trực tiếp rằng chỉ cần chạy `EXPIRE` trên một key theo mẫu là thay đổi được toàn bộ chính sách session.

## 8. Trách nhiệm khi dữ liệu thay đổi hoặc Redis gặp lỗi

| Sự kiện | Spring Cache | Spring Session | Spring Data Redis trực tiếp |
|---|---|---|---|
| DB sửa tên sản phẩm | Cần cập nhật/xóa cache hoặc chờ TTL | Không tự thay đổi session | Key tự quản chỉ thay đổi nếu code ghi |
| Người dùng logout | Cache sản phẩm vẫn có thể giữ nguyên | Session cần invalidate theo flow xác thực | Counter/leaderboard không tự bị xóa |
| Key bị hết TTL | Lần đọc tiếp theo là cache miss | Session hết hạn hoặc bị coi vô hiệu | Giá trị không còn; ứng dụng quyết định cách phục hồi |
| Redis mất kết nối | Cache call có thể lỗi hoặc dùng chiến lược fallback riêng | Các request cần session có thể lỗi | Redis operations có thể lỗi/timeout |
| Redis failover | Lệnh cache có thể gián đoạn, retry theo cấu hình | Có thể ảnh hưởng phiên và các request đang chạy | Phải đánh giá idempotency, retry và khả năng mất ghi |
| Deploy version mới đổi model | Cached DTO có thể deserialize lỗi | Session attribute cũ có thể deserialize lỗi | Phụ thuộc định dạng key/value đã tự quy ước |

### 8.1. Tại sao không gộp cache và session tùy tiện?

Cache thường có mục tiêu hiệu năng: nếu cache miss, hệ thống có thể đọc lại từ nguồn dữ liệu chuẩn. Vì thế cache thường được thiết kế với TTL và bộ nhớ giới hạn, chấp nhận eviction.

Session có thể mang trạng thái xác thực và luồng công việc: nếu bị evict ngoài ý muốn, người dùng có thể phải đăng nhập lại hoặc mất trạng thái giỏ hàng phiên. Vì vậy:

- Không dùng chính sách eviction dành cho cache như một giả định an toàn cho session production.
- Giám sát `used_memory`, `evicted_keys`, lỗi mạng, latency, số lượng session và thời gian failover.
- Khi yêu cầu độ sẵn sàng cao và mức độ ảnh hưởng khác biệt lớn, có thể tách Redis instance/cluster cho **session** khỏi Redis phục vụ **cache và dữ liệu tạm**.
- Nếu vẫn dùng chung Redis, cần kiểm soát dung lượng, TTL, eviction policy, namespace, quyền truy cập và đặc tính failover của cả ba nhóm.

### 8.2. Cache fallback không giống session fallback

Nếu Redis cache bị lỗi, ứng dụng đôi khi có thể chấp nhận **bỏ qua cache và gọi DB**. Nhưng cơ chế đó phải được thiết kế, cấu hình và kiểm thử; mặc định không phải mọi lỗi cache đều biến thành cache miss.

Nếu Redis session bị lỗi, không thể tùy tiện tạo session trống rồi coi như người dùng còn đăng nhập. Điều đó thay đổi hợp đồng xác thực và có thể ảnh hưởng tính an toàn. Cần quy định rõ hành vi timeout, retry, hiển thị lỗi hoặc yêu cầu đăng nhập lại.

Nếu thao tác Redis trực tiếp bị lỗi, phải xét lệnh đã được thực thi ở Redis trước khi client timeout hay chưa. Thực thi lại `INCR` có thể tăng hai lần; gọi lại một lệnh ghi bất kỳ không mặc nhiên an toàn.

## 9. Những nhầm lẫn thường gặp

### Nhầm lẫn 1 — "Thêm spring-boot-starter-data-redis là @Cacheable tự chạy"

Sai. Spring Data Redis tạo khả năng kết nối và thao tác Redis. Để dùng annotation cache, cần có Spring Cache infrastructure, bật `@EnableCaching` và lựa chọn `CacheManager` phù hợp.

### Nhầm lẫn 2 — "Đã có RedisTemplate thì session tự nằm trong Redis"

Sai. `RedisTemplate` chỉ là công cụ thao tác Redis. Redis-backed session cần tích hợp Spring Session và repository thích hợp. Một ứng dụng dùng RedisTemplate vẫn có thể đang giữ HTTP session trong bộ nhớ container.

### Nhầm lẫn 3 — "Có Spring Session thì không cần Spring Security"

Sai. Spring Session cung cấp nơi lưu và vòng đời session. Spring Security giải quyết xác thực, phân quyền và các biện pháp bảo mật của tầng web.

### Nhầm lẫn 4 — "Spring Cache lưu dữ liệu vĩnh viễn"

Sai. Cache được thiết kế để có thể bị xóa, hết TTL hoặc miss. Mặc dù có thể thiết lập TTL rất dài hay không hết hạn, không nên mặc định xem cache là hệ thống lưu trữ nghiệp vụ chuẩn.

### Nhầm lẫn 5 — "Chỉnh serializer của RedisTemplate là chỉnh toàn bộ Redis"

Sai. Serializer thuộc cấu hình của từng thành phần: RedisTemplate, RedisCacheManager và session repository có vòng đời, mô hình key và serializer riêng.

### Nhầm lẫn 6 — "Đăng xuất sẽ xóa hết dữ liệu cache có liên quan đến người dùng"

Sai. Session invalidation và cache invalidation là các thao tác khác nhau. Nếu cache có chứa dữ liệu riêng tư theo người dùng, ứng dụng phải thiết kế key, quyền truy cập, TTL và xóa cache theo nghiệp vụ; không dựa vào logout để mặc định làm sạch cache.

### Nhầm lẫn 7 — "Cache, session và Redis repository cùng dùng Redis nên chung một TTL"

Sai. TTL là thuộc tính của từng key hoặc chính sách của từng tầng. Cache entry TTL, session inactivity timeout và TTL của key nghiệp vụ không gắn với nhau.

### Nhầm lẫn 8 — "Dùng chung Redis nghĩa là chi phí vận hành như nhau"

Sai. Cùng server vẫn có thể có yêu cầu tài nguyên khác nhau: cache sinh nhiều key ngắn hạn, session sinh key cần duy trì ổn định, leaderboard hoặc Streams có mô hình tăng trưởng riêng. Cần lập kế hoạch về bộ nhớ, persistence, eviction và dự phòng dựa theo vai trò của từng dữ liệu.

## 10. Cách kiểm tra ranh giới trong một dự án thực tế

Khi đọc code Spring Boot sử dụng Redis, có thể lần theo bốn câu hỏi sau.

**1. Ai sở hữu API đang được gọi?**

~~~text
@Cacheable / CacheManager          -> Spring Cache
HttpSession / SessionRepository    -> Spring Session
RedisTemplate / RedisRepository    -> Spring Data Redis
~~~

**2. Ai quyết định key và thời gian hết hạn?**

- Cache: cache name, key expression, CacheManager, cache TTL.
- Session: session ID, SessionRepository, inactive timeout.
- Direct Redis: key convention, các lệnh và TTL do feature quy định.

**3. Nếu Redis mất toàn bộ dữ liệu, điều gì xảy ra?**

- Cache: người dùng chịu độ trễ do hệ thống phải tải lại dữ liệu.
- Session: người dùng có thể mất phiên và cần đăng nhập lại hoặc tái tạo trạng thái phiên.
- Dữ liệu trực tiếp: tác động phụ thuộc từng feature; có key tái tạo được, có key làm sai số liệu hoặc mất trạng thái quan trọng.

**4. Có chính sách invalidation và retry tương ứng không?**

- Cache cần cập nhật sau khi dữ liệu nguồn thay đổi.
- Session cần vòng đời chính xác và bảo vệ thông tin xác thực.
- Redis operations trực tiếp cần quy tắc nhất quán, tính nguyên tử và idempotency thích hợp với lệnh cụ thể.

Nhìn vào **mục đích của dữ liệu** và **abstraction sở hữu vòng đời** luôn đáng tin cậy hơn việc nhìn thấy một key được lưu trong Redis rồi gọi tất cả là “cache”.

## 11. Bài tập tư duy: chọn API đúng

| Yêu cầu | Thành phần chính nên dùng | Vì sao? |
|---|---|---|
| Phương thức lấy cấu hình sản phẩm từ DB rất chậm và kết quả chấp nhận cũ 5 phút | Spring Cache + RedisCacheManager | Cache kết quả phương thức; dữ liệu nguồn vẫn ở DB |
| Hai instance Spring Boot cần dùng chung session đăng nhập | Spring Session + Redis | SessionRepository chia sẻ phiên giữa các instance |
| Lưu lựa chọn ngôn ngữ của người dùng trong phiên hiện tại | `HttpSession` do Spring Session quản lý | Giá trị gắn với vòng đời phiên |
| Đếm lượt xem video theo key | `StringRedisTemplate` và `INCR` | Ứng dụng trực tiếp quyết định counter, không phải cache một kết quả phương thức |
| Tạo bảng xếp hạng theo điểm | `RedisTemplate.opsForZSet()` | Cần sorted set và thứ tự theo score |
| Đọc product theo ID có cache nhưng mọi cập nhật phải truy vấn DB chuẩn | Spring Cache + tầng repository DB | Phân rõ cache từ dữ liệu nguồn |
| Lưu object Redis dạng CRUD theo ID | Spring Data Redis repository | Cần ánh xạ object/key trực tiếp, không nhất thiết là cache |
| Cấp quyền API bằng Bearer JWT không có session server-side | Spring Security resource server; không mặc định cần Spring Session | Xác thực token stateless không đòi hỏi repository phiên |

## 12. Tổng kết theo trách nhiệm kiến trúc

~~~text
                 "Tôi cần dùng lại kết quả phương thức"
                                  |
                                  v
                             SPRING CACHE
                         Cache / CacheManager
                                  |
                        RedisCacheManager (nếu chọn Redis)
                                  |
                                  v
                                 Redis

               "Tôi cần giữ phiên HTTP qua nhiều request"
                                  |
                                  v
                            SPRING SESSION
                       SessionRepository / HttpSession
                                  |
                      Redis-backed SessionRepository
                                  |
                                  v
                                 Redis

               "Tôi cần lệnh Redis hoặc cấu trúc Redis"
                                  |
                                  v
                           SPRING DATA REDIS
                       RedisTemplate / Repositories
                                  |
                                  v
                                 Redis
~~~

Spring Cache quyết định **kết quả nào được tái sử dụng**. Spring Session quyết định **phiên của ai đang tồn tại và khi nào hết hạn**. Spring Data Redis cung cấp **cơ chế làm việc với Redis** cho ứng dụng và cho các adapter khác.

Khi thiết kế ứng dụng Spring, hãy xác định trước dữ liệu thuộc cache, session hay dữ liệu nghiệp vụ tự quản; sau đó mới chọn dependency, API, key namespace, serializer, TTL, chiến lược xử lý lỗi và yêu cầu vận hành tương ứng.

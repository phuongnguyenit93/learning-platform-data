# Lộ trình học và kiến thức cần chuẩn bị cho Spring Data Redis

Spring Data Redis là mô-đun thuộc hệ sinh thái Spring Data, giúp ứng dụng Java/Spring giao tiếp với Redis theo những cách quen thuộc: thao tác trực tiếp qua `RedisTemplate`, sử dụng cache qua Spring Cache, ánh xạ một số đối tượng bằng Redis Repository, và xử lý các khả năng khác như Pub/Sub hoặc Redis Streams. Để học hiệu quả, cần hiểu **Redis hoạt động như thế nào** trước khi quyết định **Spring nên dùng Redis để giải quyết bài toán gì**.

Bài này đưa ra thứ tự học, kiến thức đầu vào, môi trường thực hành, bài tập theo chặng và tiêu chí tự đánh giá. Người mới có thể bắt đầu với Redis chạy cục bộ rồi tiến tới ứng dụng Spring Boot có cache, kiểm thử và vận hành cơ bản.

## 1. Đích đến của lộ trình

Sau khi hoàn thành, người học nên làm được những việc sau:

1. Giải thích Redis là gì, vì sao tốc độ truy cập thấp độ trễ, và những giới hạn của việc giữ dữ liệu chủ yếu trong bộ nhớ.
2. Phân biệt Redis dùng làm **cache**, **kho dữ liệu cấu trúc khóa–giá trị**, **bộ đếm**, **bộ lưu trạng thái tạm thời** hay **hệ thống trao đổi sự kiện**.
3. Chọn cấu trúc dữ liệu phù hợp: String, Hash, List, Set, Sorted Set, Stream; biết đặt tên key và thời hạn tồn tại (TTL).
4. Cấu hình kết nối Spring Boot với Redis; dùng `StringRedisTemplate` hoặc `RedisTemplate` để đọc/ghi dữ liệu.
5. Sử dụng `@Cacheable`, `@CachePut`, `@CacheEvict` khi bài toán phù hợp với Spring Cache; hiểu trường hợp cần thao tác Redis trực tiếp.
6. Hiểu các lựa chọn tuần tự hóa dữ liệu, rủi ro thay đổi cấu trúc đối tượng, cache miss, dữ liệu cũ và chiến lược xóa cache.
7. Viết kiểm thử tích hợp với Redis thực, quan sát key/TTL và xác nhận ứng dụng hoạt động khi cache có dữ liệu hoặc chưa có dữ liệu.
8. Nhận diện vấn đề trong môi trường triển khai: bảo mật, bộ nhớ, key quá lớn, tắc nghẽn khi cache đồng loạt hết hạn, Redis gián đoạn và giám sát.

**Giới hạn cần nhớ:** Redis không tự động thay thế cơ sở dữ liệu quan hệ. Đối với dữ liệu nghiệp vụ cần giao dịch, ràng buộc và truy vấn phức tạp, nhiều hệ thống vẫn dùng PostgreSQL/MySQL làm nguồn dữ liệu chính, còn Redis giữ thông tin truy cập nhanh hoặc trạng thái có vòng đời ngắn.

## 2. Những kiến thức cần chuẩn bị

### 2.1. Kiến thức bắt buộc ở mức nền tảng

| Nhóm | Cần biết trước khi bắt đầu | Tự kiểm tra nhanh |
| --- | --- | --- |
| Java | Class, object, interface, collection, generics, ngoại lệ và `null`; hiểu cách gọi method | Tự viết service Java nhận tham số và trả về đối tượng |
| Spring / Spring Boot | Bean, Dependency Injection, `@Service`, `@Configuration`; cấu hình bằng `application.yml` hoặc `application.properties` | Giải thích cách Spring đưa dependency vào constructor |
| REST và JSON | Request/response, mã trạng thái HTTP, JSON cơ bản | Viết API `GET /products/{id}` và đọc kết quả |
| Build và dependency | Biết chạy ứng dụng bằng Maven hoặc Gradle; hiểu ý nghĩa của starter | Thêm một starter và khởi động ứng dụng |
| Dữ liệu | Khái niệm key/value, đọc/ghi, độ trễ, dữ liệu cần lưu bền vững | Nêu ví dụ dữ liệu nào được phép hết hạn |
| Công cụ | Terminal, biến môi trường, log; Docker là lựa chọn thuận tiện | Chạy lệnh và đọc log lỗi kết nối |

Ví dụ trong bài hướng tới **Spring Boot 3.x, Java 17 trở lên** và các dependency được Spring Boot quản lý phiên bản. Nếu dùng Spring Boot/Spring Data Redis phiên bản khác, cần đối chiếu tên thuộc tính cấu hình, API và yêu cầu Java tương ứng; không nên ghép tùy tiện các phiên bản.

Không cần học thuộc toàn bộ Spring Framework, Redis Cluster hay lập trình bất đồng bộ trước khi bắt đầu. Người mới chỉ cần đủ khả năng tạo một ứng dụng Spring Boot đơn giản và hiểu vòng đời request → service → dữ liệu → response.

### 2.2. Kiến thức nên có để học nhanh hơn

- **Cơ sở dữ liệu SQL:** biết primary key, chỉ mục, transaction và lý do một truy vấn có thể chậm. Kiến thức này giúp xác định chỗ nên đặt cache.
- **Mạng căn bản:** biết `localhost`, host, port, TCP, timeout; phân biệt dịch vụ chạy trên máy thật và trong container.
- **Đồng thời (concurrency):** biết nhiều request có thể truy cập cùng một dữ liệu; hiểu sơ bộ race condition và thao tác nguyên tử.
- **Kiểm thử:** đã dùng JUnit và Spring Boot Test ở mức cơ bản; quen khái niệm unit test và integration test.
- **Vận hành:** biết Docker Compose, log, health check và biến môi trường là một lợi thế.

### 2.3. Tự đánh giá mức sẵn sàng

Trước khi sang phần Spring Data Redis, hãy thử trả lời:

1. `@Service` và constructor injection giải quyết điều gì?
2. Tại sao dữ liệu JSON trả qua HTTP không nhất thiết giống dạng byte lưu bên trong Redis?
3. Nếu API phải đọc thông tin sản phẩm 1.000 lần, nhưng sản phẩm chỉ thay đổi một lần, cache có thể giúp ở điểm nào?
4. Nếu cache bị mất toàn bộ dữ liệu, ứng dụng lấy lại dữ liệu chính từ đâu?
5. Vì sao giá trị tồn tại 5 phút cần cách xử lý khác giá trị phải giữ nhiều năm?

Chưa trả lời được câu 1–2 thì nên ôn Spring/JSON. Với câu 3–5, chỉ cần có suy nghĩ ban đầu; lộ trình phía dưới sẽ giúp hoàn thiện.

## 3. Bản đồ khái niệm: Redis, client và Spring Data Redis

Một cách hình dung kiến trúc thường gặp:

~~~text
HTTP Client
    |
    v
Spring Controller -> Spring Service
                          |
             +------------+-------------+
             |                          |
             v                          v
       Spring Data Redis          JPA/JDBC/DAO
             |                          |
          Lettuce/Jedis                  |
             |                          |
             v                          v
        Redis Server             Database chính
~~~

Spring Data Redis ở phía ứng dụng: nó không phải là Redis Server. Lettuce là client được dùng phổ biến và là lựa chọn mặc định của Spring Boot trong nhiều cấu hình; Jedis cũng là một lựa chọn. Redis Server xử lý lệnh và quản lý dữ liệu; Spring cung cấp API, cấu hình, chuyển đổi dữ liệu và tích hợp với cơ chế quản lý bean.

| Cách sử dụng | API/khái niệm chính | Khi nên học và dùng |
| --- | --- | --- |
| Thao tác theo lệnh và cấu trúc dữ liệu | `StringRedisTemplate`, `RedisTemplate`, các `opsForValue()`, `opsForHash()`, `opsForSet()`… | Bộ đếm, trạng thái phiên, key đặc thù, TTL tùy biến |
| Cache kết quả hàm | Spring Cache: `@EnableCaching`, `@Cacheable`, `@CacheEvict`, `CacheManager` | Tăng tốc truy vấn có thể tái sử dụng và chịu được dữ liệu cũ có kiểm soát |
| Lưu đối tượng dạng tài liệu theo key | Spring Data Redis Repository, `@RedisHash`, `@Id` | Mô hình dữ liệu tương đối đơn giản, cần API repository; phải hiểu giới hạn truy vấn |
| Gửi/nhận thông điệp | Pub/Sub, Redis Streams | Khi đã vững CRUD/cache và hiểu yêu cầu độ tin cậy của thông điệp |
| Phối hợp tác vụ phân tán | Lệnh nguyên tử, cơ chế lease/lock phù hợp | Nội dung nâng cao: cần xét thời gian sống, lỗi và tính đúng đắn |

**Hai đường đi đặc biệt dễ nhầm:**

- **Spring Cache** xác định *khi nào* lưu hoặc xóa kết quả method; Redis chỉ là một trong các backend có thể dùng. Annotation tiện lợi nhưng không tự giải quyết bài toán dữ liệu cũ.
- **RedisTemplate** cho phép chọn *lệnh Redis và kiểu dữ liệu* cụ thể. Nó linh hoạt hơn nhưng ứng dụng phải tự quản lý key, TTL, tuần tự hóa và thời điểm xóa.

## 4. Làm quen Redis trước khi tích hợp Spring

### 4.1. Môi trường thực hành tối thiểu

Chuẩn bị JDK, IDE, Maven/Gradle, Docker (hoặc một Redis cục bộ khác) và chương trình `redis-cli`. Có thể chạy một Redis thử nghiệm trên máy cá nhân bằng Docker:

~~~bash
docker run --name redis-learning -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-learning redis-cli PING
~~~

Lệnh `PING` thành công trả về `PONG`. Cổng ở ví dụ này chỉ bind vào loopback của máy thực hành. Đó là thiết lập phục vụ học tập; khi triển khai thực tế cần cơ chế bảo vệ kết nối, quyền truy cập, cấu hình mạng và quản lý secret.

Nếu Redis nằm trong Docker Compose cùng ứng dụng, hostname thường là **tên service Redis**, không phải `localhost` bên trong container ứng dụng. Nếu ứng dụng chạy trực tiếp trên máy cá nhân với lệnh Docker trên, có thể kết nối tới `localhost:6379`.

### 4.2. Những lệnh nên hiểu bằng tay

Mở CLI:

~~~bash
docker exec -it redis-learning redis-cli
~~~

Sau đó thực hiện lần lượt:

~~~redis
SET demo:greeting "xin chao" EX 60
GET demo:greeting
TTL demo:greeting
TYPE demo:greeting

HSET demo:user:42 name "Lan" level "beginner"
HGETALL demo:user:42

SADD demo:tags redis spring java
SMEMBERS demo:tags

ZADD demo:leaderboard 100 alice 120 bob
ZREVRANGE demo:leaderboard 0 -1 WITHSCORES

INCR demo:page:views
DEL demo:page:views
SCAN 0 MATCH demo:* COUNT 100
~~~

Điều cần quan sát: `SET` với `EX 60` tạo key có thời hạn; `TTL` trả thời gian còn lại (khi key tồn tại); `INCR` là thao tác tăng số nguyên theo lệnh Redis; Hash lưu nhiều field dưới một key; Set không lưu phần tử trùng; Sorted Set duy trì điểm số để xếp hạng.

**Không dùng `KEYS *` để dò key trên hệ thống lớn hoặc môi trường production** vì có thể gây ảnh hưởng đến khả năng phản hồi. `SCAN` duyệt dần theo cursor; ví dụ trên chỉ trả một lượt, cần lặp với cursor được trả về đến khi cursor trở lại 0 mới hoàn tất vòng quét. Tránh thử `FLUSHDB`/`FLUSHALL` trên nơi có dữ liệu thật.

### 4.3. Sáu khái niệm Redis cần nắm

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Key và namespace | Key có duy nhất, dễ tìm và tránh đụng nhau không? | `shop:product:42` |
| Kiểu dữ liệu | Cần một giá trị, nhiều field, tập hợp hay xếp hạng? | String cho mã OTP, Hash cho thuộc tính ngắn, ZSet cho bảng xếp hạng |
| TTL và expiration | Dữ liệu hết hạn khi nào và ai chịu trách nhiệm khôi phục? | OTP 5 phút, cache danh mục 10 phút |
| Persistence | Có cần phục hồi dữ liệu Redis sau khi khởi động lại? | RDB/AOF là các lựa chọn cần tìm hiểu; độ bền phụ thuộc cấu hình và tình huống lỗi |
| Eviction | Khi đạt giới hạn bộ nhớ, Redis được phép loại bỏ key nào? | Chính sách `maxmemory-policy` phụ thuộc mục đích hệ thống |
| Atomicity | Một lệnh có đảm bảo trạng thái nhất quán khi nhiều client gọi? | `INCR` phù hợp hơn đọc số rồi cộng ở phía Java |

Không nên suy luận rằng Redis “hoàn toàn không mất dữ liệu” chỉ vì bật persistence; mức độ bền vững còn phụ thuộc chính sách ghi, sao lưu, failover và cách ứng dụng xử lý lỗi.

## 5. Lộ trình học theo chặng

Thời lượng dưới đây là **gợi ý tương đối** cho người đã biết Java và Spring Boot cơ bản; có thể điều chỉnh theo tốc độ cá nhân. Mỗi chặng nên kết thúc bằng một kết quả chạy được hoặc một câu hỏi kỹ thuật đã trả lời được.

| Chặng | Nội dung trọng tâm | Bài thực hành/đầu ra | Thời lượng gợi ý |
| --- | --- | --- | --- |
| 0. Ôn nền tảng | Java, DI, cấu hình Spring Boot, REST, Maven/Gradle | API GET đơn giản chưa sử dụng Redis | 2–4 giờ nếu cần |
| 1. Redis căn bản | String/Hash/Set/ZSet/List, key, TTL, `redis-cli` | Tự thử các lệnh và mô tả loại dữ liệu thích hợp | 3–5 giờ |
| 2. Kết nối Spring Data Redis | Starter, cấu hình kết nối, `StringRedisTemplate`, xử lý lỗi | Service tăng lượt xem bằng lệnh `INCR` | 3–5 giờ |
| 3. Thiết kế dữ liệu | Key prefix, serialization, TTL, read/write, kiểm tra key | Lưu một đối tượng nhỏ và đọc lại đúng kiểu | 4–6 giờ |
| 4. Cache với Spring | `@Cacheable`, `@CacheEvict`, cache hit/miss, stale data | API đọc sản phẩm giảm số lần truy vấn DB | 4–6 giờ |
| 5. Repository và tính năng mở rộng | `@RedisHash`, TTL đối tượng, chỉ mục; tổng quan Pub/Sub/Streams | So sánh Repository với Template; thử một use case | 3–6 giờ |
| 6. Kiểm thử và hiệu năng | Integration test, Redis thực, đo hit ratio, TTL, lỗi kết nối | Test cache miss/hit/invalidation; số liệu đo trước/sau | 4–6 giờ |
| 7. Sẵn sàng triển khai | Bảo mật, memory, persistence, monitoring, topology, recovery | Checklist vận hành và bài tập mô phỏng Redis ngắt | 4–6 giờ |

### Chặng 0 — Nắm vòng đời request trong Spring Boot

Hãy tạo một API trả về sản phẩm theo ID, ban đầu lấy từ một repository giả lập hoặc database quen thuộc:

~~~text
GET /products/42
  -> ProductController
  -> ProductService
  -> ProductRepository
  -> ProductDto (JSON)
~~~

Hiểu nơi thực thi logic đọc dữ liệu và tại sao service được Spring quản lý. Đây sẽ là điểm chèn cache sau này. Nếu chưa hiểu được luồng này, thêm Redis quá sớm dễ che khuất lỗi kiến trúc.

### Chặng 1 — Chọn đúng kiểu dữ liệu và TTL

Thử tự thiết kế ba use case:

1. **Đếm lượt xem bài viết:** key String với lệnh `INCR`, có thể không cần TTL nếu số liệu mang tính dài hạn; khi cần số liệu bền vững, phải quyết định cách đồng bộ/sao lưu.
2. **Mã xác thực ngắn hạn:** String có TTL; phải tính cả điều kiện dùng một lần và rủi ro truy cập đồng thời.
3. **Bảng xếp hạng theo điểm:** Sorted Set với score; thêm, cập nhật và truy xuất top N.

Sau đó giải thích vì sao không nên chỉ dùng một kiểu String JSON cho mọi bài toán. Redis có những phép toán chuyên dụng giúp tránh tải toàn bộ đối tượng về Java để sửa một trường hoặc một con số.

### Chặng 2 — Kết nối Spring Boot với Redis

Ví dụ Maven với dependency được Spring Boot quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
</dependencies>
~~~

Đây là phần `dependencies` của dự án Spring Boot, không phải một file `pom.xml` hoàn chỉnh. Có thể dùng Gradle tương đương. Với Spring Boot 3.x chạy trên máy chủ cục bộ như ở phần 4:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Tách thông số theo môi trường; không đưa mật khẩu máy chủ thật vào repository. Trong mạng triển khai, cân nhắc TLS, ACL, secret manager và timeout phù hợp.

Tạo một service thao tác String để ghi nhận lượt xem:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArticleViewService {
    private final StringRedisTemplate redis;

    public ArticleViewService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long recordView(String articleId) {
        String key = "demo:article:views:" + articleId;
        Long count = redis.opsForValue().increment(key);
        if (count == null) {
            throw new IllegalStateException("Redis did not return a count");
        }
        return count;
    }
}
~~~

Khi gọi `recordView("42")` liên tiếp, Redis thực hiện tăng bằng lệnh chuyên dụng; không cần đọc giá trị về Java rồi ghi lại. Ví dụ giả định `articleId` là định danh đã được kiểm tra ở tầng gọi và Redis đã kết nối thành công. Nếu đây là bộ đếm kinh doanh quan trọng, vẫn cần thiết kế yêu cầu lưu bền vững/khôi phục khi Redis gặp sự cố.

Kiến thức cần rút ra:

- `StringRedisTemplate` phù hợp với key/value dạng chuỗi; Redis tự xử lý lệnh tăng trên giá trị là số hợp lệ.
- `RedisTemplate<K,V>` có nhiều nhóm operation và có thể tùy chỉnh serializer.
- Timeout, lỗi mạng, xác thực và Redis không sẵn sàng là tình huống cần xử lý theo mức quan trọng của tính năng.
- Dùng connection pool, SSL/TLS hoặc cấu hình kết nối nâng cao khi thực sự có yêu cầu; không tự ý điều chỉnh hàng loạt thông số khi chưa đo đạc.

### Chặng 3 — Thiết kế key, giá trị và thời hạn sống

Nên hình thành một quy ước key trước khi dữ liệu tăng nhiều:

~~~text
<application>:<entity>:<id>[:<attribute>]
shop:product:42
shop:product:42:views
shop:session:opaque-session-id
~~~

Một key tốt cần tránh va chạm giữa môi trường và tính năng, có độ dài hợp lý, không chứa mật khẩu hoặc thông tin nhạy cảm dễ lộ, và cho phép xác định ai sở hữu vòng đời dữ liệu. Prefix có thể gồm tên môi trường khi các môi trường dùng chung hạ tầng, nhưng tách hẳn tài nguyên vẫn dễ quản trị hơn.

Khi lưu object, phải chọn serializer rõ ràng:

| Lựa chọn | Ưu điểm | Điều cần cân nhắc |
| --- | --- | --- |
| Chuỗi và giá trị đơn giản | Dễ đọc bằng CLI, dễ chia sẻ giữa các ngôn ngữ | Phải tự tổ chức cấu trúc |
| JSON | Quan sát và trao đổi dễ, ít phụ thuộc bytecode Java | Cần chính sách tương thích khi đổi schema và xử lý type |
| Serializer nhị phân/JDK | Có thể thuận tiện trong hệ thống Java sẵn có | Khó đọc thủ công, có rủi ro tương thích và an toàn; tránh dữ liệu không đáng tin |
| Redis Hash | Đọc/ghi các field riêng lẻ | Không tự mang ngữ nghĩa quan hệ, kiểu dữ liệu phải được quy ước |

Tránh phụ thuộc mặc định serializer khi dữ liệu cần tồn tại qua nhiều phiên bản ứng dụng. Hãy xác định dữ liệu nào được phép xóa, cần migration ra sao, và cách kiểm soát dung lượng.

TTL giải quyết một phần vòng đời dữ liệu, nhưng không thay thế quy tắc cập nhật. Ví dụ, cache sản phẩm TTL 10 phút vẫn có thể trả giá cũ trong 10 phút nếu không xóa cache sau khi cập nhật. Với nhiều key hết hạn cùng thời điểm, cần cân nhắc phân tán TTL (jitter) và hạn chế nhiều request cùng tải lại dữ liệu.

### Chặng 4 — Dùng Spring Cache đúng tình huống

Khi cần cache kết quả truy vấn, trước tiên hỏi: **có thể tính lại kết quả từ nguồn chính không, cho phép cũ bao lâu, và lúc cập nhật sẽ xóa cache nào?**

Spring Cache thường được kích hoạt bằng `@EnableCaching` trong cấu hình ứng dụng. Khi muốn backend Redis, đưa `spring-boot-starter-data-redis` và `spring-boot-starter-cache` vào classpath, rồi cấu hình cache phù hợp. Ví dụ cấu hình thời hạn sống cho cache Redis trong Spring Boot 3.x:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
~~~

Phần sau minh họa cách đặt annotation ở **service method**. `ProductRepository` và `ProductDto` đại diện cho thành phần nghiệp vụ đã có ở chặng 0:

~~~java
@Service
public class ProductQueryService {
    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductDto getById(Long id) {
        return products.findDtoById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }

    @CacheEvict(cacheNames = "productById", key = "#id")
    public void changePrice(Long id, BigDecimal newPrice) {
        products.updatePrice(id, newPrice);
    }
}
~~~

Đây là **đoạn minh họa tích hợp**, không phải class độc lập có thể biên dịch khi chưa khai báo repository, DTO, exception và các import tương ứng. Trong hệ thống thực, thao tác cập nhật cần tuân thủ transaction và quy tắc tính nhất quán của nguồn chính. Nếu có nhiều cache liên quan một sản phẩm, phải xác định tất cả vị trí cần vô hiệu hóa.

Quan sát luồng cơ bản:

~~~text
Lần gọi đầu:  Service -> Cache miss -> Repository -> Cache put -> Response
Lần gọi sau:  Service -> Cache hit --------------------------> Response
Cập nhật:     Service -> Ghi nguồn chính -> Evict cache
Lần kế tiếp:  Service -> Cache miss -> Repository -> ...
~~~

Những điểm dễ sai:

- Method được cache phải đi qua Spring proxy. Một lời gọi từ method này sang method khác trong **cùng bean** thường không kích hoạt annotation cache theo cơ chế proxy mặc định.
- Cache key phải phân biệt đúng đầu vào tạo ra kết quả; nếu dữ liệu phụ thuộc người dùng, vai trò hoặc tenant, không được dùng chung key thiếu ngữ cảnh.
- Cache hit không có nghĩa dữ liệu luôn mới; eviction và TTL là quyết định nghiệp vụ.
- Không nên cache các kết quả có dữ liệu nhạy cảm khi chưa kiểm soát quyền truy cập và khả năng chia sẻ cache.
- Đo số lần repository được gọi hoặc metric cache hit/miss; đừng kết luận cache “đã nhanh hơn” chỉ vì đã thêm annotation.

### Chặng 5 — Hiểu Redis Repository và khả năng mở rộng

Spring Data Redis cung cấp mô hình ánh xạ cho những đối tượng phù hợp lưu theo key. Có thể gặp `@RedisHash`, `@Id`, `@Indexed` và `@TimeToLive`. Hãy thực hành một entity đơn giản, đọc lại theo ID và quan sát key mà framework sinh ra. Sau đó thử thay đổi TTL và tìm hiểu giới hạn truy vấn.

Repository Redis không có đầy đủ tính chất của JPA: không mặc định có join, foreign key, SQL query hay transaction quan hệ. Truy vấn theo field có thể cần chỉ mục thứ cấp và cấu trúc dữ liệu phụ trợ; hãy hiểu chi phí cập nhật chỉ mục và xử lý hết hạn trước khi chọn làm nguồn lưu trữ chính.

Chỉ sau khi nắm được đọc/ghi và cache mới nên mở rộng:

- **Pub/Sub:** thích hợp với thông báo tức thời cho subscriber đang online; subscriber offline không có cơ chế đọc lại bản tin đã bỏ lỡ chỉ nhờ Pub/Sub.
- **Redis Streams:** có log sự kiện và consumer group, phù hợp hơn khi cần theo dõi xử lý và đọc tiếp; ứng dụng vẫn phải lo xác nhận, retry, idempotency và tăng trưởng dữ liệu.
- **Pipeline/batch:** giảm số vòng trao đổi mạng cho nhiều lệnh, nhưng không đồng nghĩa tất cả lệnh trở thành một giao dịch nguyên tử.
- **Lua/transaction và khóa phân tán:** là chủ đề nâng cao, yêu cầu hiểu điều kiện tranh chấp, timeout, failover và biện pháp bảo vệ tính đúng đắn.
- **Reactive Redis:** chỉ cần ưu tiên nếu ứng dụng đang dùng Spring WebFlux và đã có kiến thức reactive streams; không phải điều kiện để học bản đồng bộ.

### Chặng 6 — Viết kiểm thử và đo kết quả

Một bài làm không hoàn tất ở thời điểm “chạy được trên máy tôi”. Cần quan sát giá trị thực bên Redis và hành vi API khi điều kiện thay đổi.

Các tình huống kiểm thử thực hành:

1. **Ghi/đọc:** ghi dữ liệu qua service rồi đọc lại; xác nhận định dạng và key.
2. **TTL:** tạo key ngắn hạn, đọc TTL trước và sau; xác minh key không còn sau khi hết hạn, tránh phụ thuộc vào mốc thời gian quá sát gây test không ổn định.
3. **Cache miss/hit:** gọi API hai lần với cùng key và xác minh số lần truy cập repository giảm.
4. **Invalidation:** cập nhật dữ liệu nguồn, gọi lại API và xác minh kết quả mới.
5. **Key cách ly:** hai ID, tenant hoặc quyền truy cập khác nhau không vô tình dùng chung kết quả.
6. **Redis ngắt kết nối:** mô tả hoặc kiểm thử chính sách lỗi: trả lỗi, bỏ qua cache và đọc nguồn chính, hay từ chối request tùy loại dữ liệu.
7. **Serialization:** dữ liệu được tạo ở phiên bản ứng dụng cũ còn đọc được khi thay đổi DTO hoặc quy tắc serializer hay không.

Testcontainers có thể tạo Redis container phục vụ integration test, giúp kiểm tra lệnh/TTL/serializer với Redis thật. Unit test bằng mock vẫn hữu ích cho logic nghiệp vụ, nhưng không thay thế kiểm thử tích hợp những hành vi phụ thuộc Redis Server.

Đo hiệu năng theo một cấu hình có thể lặp lại: cùng tập dữ liệu, cùng mức tải, ghi nhận độ trễ (đặc biệt p95/p99 khi có tải), request/giây, tỷ lệ cache hit, lượng truy vấn DB và mức sử dụng memory Redis. So sánh trước/sau với cả trường hợp hit lẫn miss, bởi cache miss thêm một lần truy cập Redis trước khi đọc nguồn chính.

### Chặng 7 — Tối thiểu cần biết để triển khai an toàn

| Chủ đề | Cần quyết định/quan sát |
| --- | --- |
| Bảo mật | Redis chỉ truy cập qua mạng cần thiết; dùng ACL/xác thực, TLS khi phù hợp; không public port ra Internet |
| Bộ nhớ | Giới hạn memory, chính sách eviction, dung lượng mỗi key, key tăng mãi không có TTL |
| Persistence và backup | Dữ liệu nào được phép mất, RDB/AOF cần cấu hình ra sao, có cần backup/restore và thử khôi phục không |
| Sẵn sàng và failover | Redis standalone, Sentinel hoặc Cluster khác nhau thế nào; ứng dụng phản ứng ra sao khi chuyển node |
| Monitoring | Connection, latency, timeout, memory, evicted keys, expired keys, keyspace, hit/miss, tải DB |
| Schema/key | Quy ước prefix, serialize, version dữ liệu, migration và dọn key cũ |
| Giới hạn tài nguyên | Tránh key khổng lồ, truy vấn quét nặng, truy cập hot key và nhiều lệnh liên tiếp qua mạng |
| Tính nhất quán | Nguồn dữ liệu chính là gì, khi nào invalidate, xử lý stale data và khôi phục sau mất cache |

Những cấu hình như Redis Cluster và Sentinel không nên học theo kiểu chỉ đổi host. Chúng ảnh hưởng đến kết nối, định tuyến key, failover và một số thao tác nhiều key. Ví dụ, với Redis Cluster, các lệnh nhiều key có thể bị giới hạn bởi hash slot. Khi tiến tới production, đọc tài liệu tương ứng đúng phiên bản Redis, Spring Boot và client đang dùng.

## 6. Lịch học mẫu trong bốn tuần

Nếu dành khoảng 6–8 giờ mỗi tuần, có thể phân bổ như sau:

| Tuần | Trọng tâm | Bằng chứng đã học |
| --- | --- | --- |
| 1 | Ôn Spring Boot, Redis CLI, kiểu dữ liệu và TTL | Tạo được các key mẫu và giải thích từng lệnh |
| 2 | Spring Data Redis, Template, key naming, serialization | API tăng bộ đếm và lưu/đọc dữ liệu từ Redis |
| 3 | Spring Cache, cập nhật dữ liệu, Repository, integration test | API sản phẩm có cache; kiểm thử miss/hit/eviction |
| 4 | Đo hiệu năng, lỗi Redis, bảo mật, quan sát, bài tập tổng hợp | Demo có số liệu và mô tả chính sách fallback |

Nếu đã vững Java/Spring Boot, có thể bỏ qua phần ôn; nếu mới học Dependency Injection hoặc HTTP, dành thêm thời gian cho chặng 0. Các chủ đề Redis Streams, lock phân tán và reactive có thể học sau khi dự án đầu tiên đã chạy ổn định.

## 7. Dự án cuối lộ trình: API danh mục sản phẩm có cache

**Bài toán:** một cửa hàng có endpoint xem chi tiết sản phẩm. Cơ sở dữ liệu giữ tên, giá và số lượng tồn. Sản phẩm được đọc nhiều lần nhưng cập nhật ít hơn. Hệ thống cần cải thiện truy cập đọc, không được để một bản cache cũ tồn tại vô hạn khi giá thay đổi.

### 7.1. Thiết kế tối thiểu

~~~text
GET /products/{id}
    -> Cache Redis (productById)
         | hit  -> trả ProductDto
         | miss -> đọc DB -> lưu cache có TTL -> trả ProductDto

PATCH /products/{id}/price
    -> cập nhật DB thành công
    -> xóa cache liên quan
    -> lần GET sau tải lại từ DB
~~~

Quy tắc dữ liệu: **database là nguồn chính cho sản phẩm**; Redis chỉ giữ bản sao có thể tạo lại. TTL là giới hạn thời gian tồn tại của bản cache, còn việc xóa cache khi thay đổi giá giải quyết nhu cầu cập nhật sớm hơn TTL. Trình tự cập nhật DB và xóa cache cần được thiết kế phù hợp transaction và tình huống nhiều request đồng thời.

### 7.2. Phần việc nên làm

1. Tạo `ProductController`, `ProductService` và repository đọc/ghi từ nguồn chính (database hoặc kho giả lập cho giai đoạn đầu).
2. Thêm `spring-boot-starter-data-redis` và `spring-boot-starter-cache`; kết nối Redis cục bộ.
3. Áp dụng `@Cacheable` cho thao tác đọc và `@CacheEvict` cho thao tác đổi giá.
4. Định nghĩa TTL và mô tả vì sao chọn TTL đó; kiểm tra key, dung lượng và serializer.
5. Viết kiểm thử cho ba trường hợp: miss, hit, cập nhật rồi đọc lại.
6. Ghi nhận thời gian phản hồi hoặc số lần gọi repository trước/sau khi có cache; thử cache lạnh và cache nóng.
7. Mô phỏng Redis dừng; quyết định hệ thống nên trả lỗi hay tiếp tục đọc DB trong tình huống này.
8. Nếu còn thời gian, thêm bộ đếm lượt xem bằng `StringRedisTemplate` để so sánh truy cập lệnh Redis trực tiếp với Spring Cache.

### 7.3. Tiêu chí hoàn thành bài thực hành

- Có thể mô tả bằng lời dữ liệu nào ở DB, dữ liệu nào ở Redis và điều gì xảy ra khi Redis trống.
- Chứng minh được ít nhất một cache hit mà không truy cập lại repository.
- Sau khi sửa giá sản phẩm, đường đọc tiếp theo cho kết quả đúng theo quy tắc đã chọn.
- Key có tên và TTL hợp lý; không có dữ liệu nhạy cảm trong key hoặc file cấu hình được commit.
- Có kiểm thử tích hợp kiểm tra hành vi Redis, đồng thời có log hoặc metric đủ để điều tra khi dữ liệu cũ xuất hiện.
- Có tài liệu ngắn mô tả cách chạy, dừng, dọn môi trường thử nghiệm và khôi phục sau lỗi kết nối.

Nếu làm được những việc này, bạn đã hiểu phần lõi Spring Data Redis đủ để bắt đầu một tính năng thật dưới sự giám sát kỹ thuật phù hợp.

## 8. Những hiểu lầm và lỗi thường gặp

| Hiểu lầm/thói quen | Hậu quả | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| “Có Redis thì mọi API sẽ nhanh hơn” | Thêm network hop và chi phí duy trì, đặc biệt khi cache miss nhiều | Chọn điểm nóng dựa trên số liệu và tỷ lệ đọc/ghi |
| “Cứ đặt TTL là dữ liệu luôn đúng” | Có thể trả giá/trạng thái cũ trước khi hết hạn | Xác định quy tắc invalidation và mức stale chấp nhận |
| Dùng một key cho nhiều người dùng/tenant | Rò rỉ hoặc trộn dữ liệu | Đưa đủ ngữ cảnh truy cập vào thiết kế key |
| Lưu mọi object bằng serializer mặc định | Khó debug, khó nâng cấp/migration | Chọn định dạng rõ ràng, kiểm tra tương thích |
| Dùng Redis làm nguồn chính mà không xét persistence | Mất dữ liệu hoặc không đáp ứng yêu cầu nghiệp vụ | Đánh giá độ bền, backup và transaction trước khi chọn |
| Đọc rồi cộng ở Java rồi ghi lại | Lost update khi nhiều request cạnh tranh | Ưu tiên `INCR` hoặc thao tác nguyên tử phù hợp |
| Dùng Pub/Sub cho hàng đợi yêu cầu phát lại chắc chắn | Subscriber offline bỏ lỡ thông điệp | Cân nhắc Streams hoặc hệ thống message broker chuyên dụng |
| Tự viết distributed lock chỉ bằng `SETNX` | Có thể quên timeout, giải phóng nhầm lock hoặc thiếu cơ chế bảo đảm đúng đắn | Học rõ lease, token sở hữu, failure mode và thư viện đã được kiểm chứng |
| Xóa toàn bộ cache khi cập nhật một sản phẩm | Tạo lượng miss lớn và tăng tải DB | Đặt key và vùng cache để xóa đúng đối tượng |
| Không đặt memory limit, không theo dõi evictions | Redis dùng nhiều RAM hoặc loại bỏ key ngoài mong đợi | Cấu hình theo loại dữ liệu và quan sát chỉ số |

**Cache stampede:** nhiều request cùng thấy cache miss rồi đồng loạt truy vấn DB cho một key nóng. Đây là lý do cần tìm hiểu TTL có jitter, gom lần tải (request coalescing), cache warming hoặc cơ chế chống stampede tùy quy mô. Không nên áp dụng khóa phân tán cho mọi cache miss nếu chưa xác định được chi phí và tính đúng đắn.

## 9. Thứ tự tìm hiểu sâu sau khi đã nắm nền tảng

Chọn nhánh dựa trên sản phẩm đang làm:

- **Ứng dụng web nhiều truy vấn đọc:** Spring Cache → cache key/TTL/invalidation → cache metrics → stampede và chiến lược làm mới.
- **Bộ đếm, xếp hạng, trạng thái phiên:** Redis String/Hash/Set/ZSet → thao tác nguyên tử → quản lý TTL → memory và persistence.
- **Xử lý sự kiện:** Pub/Sub vs Streams → consumer group → ack/retry → idempotency → quan sát backlog.
- **Hệ thống phân tán:** concurrent updates → tính đúng đắn và giới hạn lệnh nguyên tử → lock/lease → failover và phục hồi.
- **Hiệu năng hoặc quy mô lớn:** profile tải → pipelining/batching → tối ưu key → Redis Cluster → theo dõi latency, memory và hot key.

Các nhánh đều bắt đầu từ câu hỏi nghiệp vụ: cần độ trễ thấp, giảm tải database, lưu trạng thái có TTL, hay trao đổi sự kiện? Câu trả lời quyết định API Spring Data Redis cần dùng; không nhất thiết phải học hết các API trước khi giải một bài toán thực tế.

## 10. Bộ câu hỏi tự ôn trước khi chuyển sang bài học chuyên sâu

1. Redis Server, Redis client và Spring Data Redis khác nhau ở vai trò nào?
2. Cache-aside hoạt động ra sao khi key đã tồn tại và khi key chưa tồn tại?
3. `@Cacheable` khác `StringRedisTemplate.opsForValue().get()` ở mức điều khiển nào?
4. Trường hợp nào dùng String, Hash, Set hoặc Sorted Set sẽ hợp lý hơn lưu một JSON lớn?
5. Vì sao TTL không thay thế được việc xóa cache sau cập nhật?
6. Điều gì xảy ra nếu lời gọi method có `@Cacheable` được thực hiện từ cùng một instance thay vì đi qua Spring proxy?
7. Vì sao không nên dùng `KEYS *` khi Redis đang phục vụ tải lớn?
8. Làm sao kiểm tra được lần GET thứ hai là cache hit thay vì chỉ nhìn kết quả HTTP giống nhau?
9. Khi Redis ngắt kết nối, tính năng nào có thể bỏ qua cache và tính năng nào cần báo lỗi?
10. Với dữ liệu chỉ còn ở Redis, ứng dụng phải đặt ra những câu hỏi gì về persistence, backup, memory và failover?

**Mốc kiến thức quan trọng nhất:** tự xây được một luồng đọc dữ liệu có cache, chứng minh được cache hit, xử lý được invalidation sau thay đổi và giải thích được giới hạn về tính nhất quán. Đó là nền tảng để tiếp tục học chuyên sâu Spring Data Redis mà không bị phụ thuộc vào việc nhớ từng annotation hay câu lệnh riêng lẻ.

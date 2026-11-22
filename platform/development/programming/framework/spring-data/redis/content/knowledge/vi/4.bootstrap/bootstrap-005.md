# Cơ chế tự cấu hình của Spring Boot và điều kiện tạo bean

Khi bắt đầu dùng **Spring Data Redis**, bạn thường chỉ thêm `spring-boot-starter-data-redis`, khai báo địa chỉ Redis rồi tiêm `StringRedisTemplate` vào một service. Spring Boot có thể tạo sẵn các bean cần thiết, nhưng việc đó **không xảy ra vô điều kiện**. Mỗi bean được tạo hay bị bỏ qua theo những điều kiện cụ thể về thư viện, các bean đang có, cấu hình và khả năng chọn đúng dependency.

Bài này giải thích đường đi từ dependency đến `RedisConnectionFactory` và các Redis template, cách Spring Boot quyết định nhường quyền cho cấu hình của ứng dụng, và cách đọc báo cáo điều kiện khi bean không xuất hiện như mong đợi.

> **Phạm vi phiên bản:** Các tên lớp, annotation và ví dụ cấu hình bên dưới bám theo **Spring Boot 3.3.x / Spring Data Redis 3.3.x**. Ở phiên bản khác, đặc biệt khi nâng major version, cần đối chiếu API, package và tên auto-configuration tương ứng; cơ chế tổng quát của conditional auto-configuration vẫn là nền tảng để đọc tài liệu.

## 1. Hiểu đúng “tự cấu hình”

**Auto-configuration** là cơ chế Spring Boot xem các thư viện có trong classpath và trạng thái của `ApplicationContext`, rồi đăng ký một số bean mặc định khi các điều kiện được thỏa mãn.

Điều đó khác với ba hoạt động thường bị nhầm lẫn:

| Hoạt động | Spring làm gì? | Ví dụ với Redis |
|---|---|---|
| Dependency management / starter | Mang thư viện cần thiết vào classpath | `spring-boot-starter-data-redis` thêm Spring Data Redis và driver mặc định |
| Auto-configuration | Đọc điều kiện rồi đăng ký bean | Tạo `RedisConnectionFactory`, `RedisTemplate`, `StringRedisTemplate` nếu phù hợp |
| Dependency injection | Cấp bean đã có cho đối tượng cần nó | Constructor nhận `StringRedisTemplate` |
| Giao tiếp Redis thật | Mở/khai thác kết nối và gửi lệnh | `redis.opsForValue().get("k")` |

**Có bean trong context không đồng nghĩa Redis đang chạy hoặc xác thực thành công.** Việc kết nối có thể xảy ra khi khởi tạo bean hoặc tại một thao tác thực tế, tùy driver, cấu hình lifecycle, health check và đường chạy ứng dụng. Auto-configuration chứng minh rằng Spring tạo được cấu trúc bean; độ sẵn sàng của Redis phải được kiểm chứng riêng.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Thêm starter Redis"] --> B["Classpath có Spring Data Redis và driver"]
    B --> C["Spring Boot xét RedisAutoConfiguration"]
    C --> D{"Điều kiện phù hợp?"}
    D -->|Không| E["Bỏ qua auto-configuration"]
    D -->|Có| F["Tạo RedisConnectionFactory nếu chưa có"]
    F --> G{"Có một factory ứng viên phù hợp?"}
    G -->|Có| H["Tạo template mặc định nếu chưa bị bean người dùng thay thế"]
    G -->|Không| I["Không thể tự chọn factory để tạo template"]
    H --> J["Ứng dụng inject template và gọi Redis"]
    J --> K["Driver thực hiện kết nối/lệnh; lỗi mạng vẫn có thể xảy ra"]
~~~

Spring Boot nạp danh sách auto-configuration được khai báo bởi các thư viện, đánh giá `@Conditional...` và sắp xếp cấu hình để các bean do ứng dụng tự định nghĩa có cơ hội thay thế cấu hình mặc định. Vì vậy có thể xem auto-configuration là **cấu hình mặc định có điều kiện**.

## 2. Khởi tạo dự án Redis tối thiểu

### 2.1. Thêm starter

Với Spring Boot dùng Gradle và dependency management của Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter này tập hợp Spring Data Redis và driver **Lettuce** theo mặc định. Đây là cách thông thường để có các lớp dùng trong điều kiện tự cấu hình. Chỉ thêm một thư viện tùy ý có tên “redis” không nhất thiết thỏa mãn tất cả điều kiện Boot cần.

Một ứng dụng có thể thêm `spring-boot-starter-data-redis-reactive` khi muốn thể hiện rõ mục đích dùng API Reactive; Spring Boot 3.3 cũng hỗ trợ các API Reactive trong starter Redis thông thường khi đủ classpath và connection factory tương thích.

### 2.2. Đặt thuộc tính kết nối

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

Ở Boot 3.x, `spring.data.redis.*` được gắn vào lớp `RedisProperties`. Nếu không cấu hình khác, Boot thử địa chỉ `localhost:6379`. Thuộc tính này **không khởi chạy một Redis server**; cần có Redis thực tế ở nơi ứng dụng truy cập được.

Bạn cũng có thể cấu hình bằng URL:

~~~yaml
spring:
  data:
    redis:
      url: redis://localhost:6379
~~~

Khi đặt `url`, các thuộc tính `host`, `port`, `username` và `password` riêng lẻ không còn là nguồn quyết định kết nối như trong cấu hình host/port thông thường. Đừng khai báo đồng thời nhiều kiểu rồi suy đoán kiểu nào được chọn.

Trong môi trường triển khai thực tế, thông tin xác thực nên lấy từ secret/environment phù hợp thay vì đưa thẳng mật khẩu vào tài liệu hoặc source.

### 2.3. Sử dụng bean do Boot cấp

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {

    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String articleId) {
        return redis.opsForValue().increment("views:" + articleId);
    }

    public String get(String articleId) {
        return redis.opsForValue().get("views:" + articleId);
    }
}
~~~

Ứng dụng không cần tự viết `@Bean StringRedisTemplate` cho trường hợp đơn giản nếu các điều kiện auto-configuration đã thỏa. `StringRedisTemplate` dùng kiểu chuỗi và các serializer chuỗi phù hợp với use case này.

Nếu constructor được inject thành công, ta chỉ biết bean tồn tại và Spring chọn được nó. Khi gọi `increment()`, thao tác vẫn có thể ném lỗi do Redis mất kết nối, timeout, sai credentials hoặc lệnh bị Redis từ chối.

## 3. Những annotation điều kiện quyết định việc tạo bean

Các annotation sau là chìa khóa để đọc auto-configuration:

| Annotation | Ý nghĩa | Hệ quả thường gặp |
|---|---|---|
| `@ConditionalOnClass(X.class)` | Chỉ áp dụng khi class yêu cầu có trên classpath | Thiếu Spring Data Redis thì Redis auto-configuration không kích hoạt |
| `@ConditionalOnMissingBean` | Chỉ tạo bean mặc định nếu chưa tồn tại bean phù hợp với điều kiện | Bean tự định nghĩa khiến Boot nhường quyền |
| `@ConditionalOnBean(X.class)` | Cần có bean kiểu `X` trước khi cấu hình tiếp | Repository config cần connection factory |
| `@ConditionalOnSingleCandidate(X.class)` | Có đúng một ứng viên để inject, hoặc nhiều ứng viên nhưng có một ứng viên chính (`@Primary`) | Hai Redis factory không có ứng viên ưu tiên có thể làm template mặc định không được tạo |
| `@ConditionalOnProperty` | Dựa vào cấu hình property, giá trị và mặc định đã quy định | Có thể bật/tắt Redis repositories |
| `@AutoConfiguration(after = ...)` | Định thứ tự auto-configuration liên quan | Tạo connection factory trước khi xét các bean phụ thuộc nó |

Điểm cần phân biệt là **theo tên bean** và **theo kiểu bean**. `@ConditionalOnMissingBean(name = "redisTemplate")` hỏi có bean *tên chính xác* là `redisTemplate` hay không, trong khi `@ConditionalOnMissingBean` không chỉ định tên ở một phương thức trả về `StringRedisTemplate` thông thường sẽ xét việc đã có bean thuộc kiểu liên quan hay chưa.

Khi đọc annotation, phải xem nó nằm trên **cả class cấu hình** hay trên **phương thức `@Bean`**: điều kiện cấp class có thể ngăn cả nhóm bean được đăng ký; điều kiện cấp method chỉ ảnh hưởng bean của method đó.

## 4. Boot 3.3 tạo những bean Redis nào?

### 4.1. `RedisAutoConfiguration` là điểm khởi đầu

Trong Spring Boot 3.3, lớp `org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration` có:

- `@AutoConfiguration`: cho phép Boot nạp như cấu hình tự động.
- `@ConditionalOnClass(RedisOperations.class)`: yêu cầu API Spring Data Redis hiện diện.
- `@EnableConfigurationProperties(RedisProperties.class)`: liên kết các thuộc tính `spring.data.redis.*`.
- `@Import(...)`: đưa cấu hình factory cho **Lettuce** và **Jedis** vào quá trình đánh giá.

Cú pháp sau là **mã rút gọn để diễn giải điều kiện**, không phải bản sao nguyên văn source của Boot:

~~~java
@AutoConfiguration
@ConditionalOnClass(RedisOperations.class)
@EnableConfigurationProperties(RedisProperties.class)
@Import({
    LettuceConnectionConfiguration.class,
    JedisConnectionConfiguration.class
})
class RedisAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "redisTemplate")
    @ConditionalOnSingleCandidate(RedisConnectionFactory.class)
    RedisTemplate<Object, Object> redisTemplate(
            RedisConnectionFactory connectionFactory) {
        // Khởi tạo template mặc định
        return /* template được cấu hình bằng connectionFactory */;
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnSingleCandidate(RedisConnectionFactory.class)
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }
}
~~~

Mục đích của đoạn rút gọn là giúp thấy cấu trúc điều kiện. Đoạn `return /* ... */` là ký hiệu minh họa và **không dùng để biên dịch**. Khi cần mã chạy, dùng các ví dụ `@Configuration` ở phần sau.

### 4.2. `RedisConnectionFactory`: bean nền tảng

`RedisConnectionFactory` là abstraction mà Spring Data Redis sử dụng để tạo kết nối tới Redis. Hai triển khai phổ biến:

- `LettuceConnectionFactory` với Lettuce, driver mặc định của starter Boot.
- `JedisConnectionFactory` khi chọn Jedis và dependency tương ứng.

Cấu hình Lettuce/Jedis của Boot chỉ đăng ký factory mặc định khi các điều kiện classpath, lựa chọn client và điều kiện chưa có `RedisConnectionFactory` thỏa mãn. Vì vậy, một factory do bạn tự khai báo là cách Boot hiểu rằng ứng dụng đã nhận trách nhiệm cấu hình kết nối.

~~~text
Classpath có RedisOperations
         │
         ▼
RedisAutoConfiguration
         │
         ├── Lettuce có sẵn và được chọn?
         │        └── Có, chưa có factory → LettuceConnectionFactory
         │
         └── Jedis có sẵn và được chọn?
                  └── Có, chưa có factory → JedisConnectionFactory
                              │
                              ▼
                     RedisConnectionFactory
                              │
                   ┌──────────┴──────────┐
                   ▼                     ▼
             RedisTemplate       StringRedisTemplate
~~~

Nếu bạn dùng cấu hình mặc định, Lettuce thường là lựa chọn đơn giản nhất. Khi cần Jedis, có thể thay dependency Lettuce bằng Jedis; khi cả hai driver có trên classpath, xác định rõ lựa chọn client bằng `spring.data.redis.client-type` để tránh dựa vào suy đoán.

Ví dụ Gradle thay driver:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-data-redis') {
        exclude group: 'io.lettuce', module: 'lettuce-core'
    }
    implementation 'redis.clients:jedis'
}
~~~

Đây là lựa chọn có chủ đích: nếu cần API reactive Redis, không thể mặc nhiên kỳ vọng Jedis cung cấp một `ReactiveRedisConnectionFactory` tương đương Lettuce.

### 4.3. `RedisTemplate` và `StringRedisTemplate` có điều kiện khác nhau

Hai bean đồng bộ (imperative) quan trọng nhất có quy tắc:

| Bean mặc định | Điều kiện cần | Điều kiện nhường quyền |
|---|---|---|
| `redisTemplate`, kiểu `RedisTemplate<Object, Object>` | Có một ứng viên `RedisConnectionFactory` xác định được | **Không** có bean tên `redisTemplate` |
| `stringRedisTemplate`, kiểu `StringRedisTemplate` | Có một ứng viên `RedisConnectionFactory` xác định được | **Không** có bean kiểu `StringRedisTemplate` phù hợp |

Hệ quả:

**Trường hợp 1 — Ứng dụng chưa khai báo template:** Nếu Boot tạo được một `RedisConnectionFactory` thích hợp, nó thường tạo cả `redisTemplate` và `stringRedisTemplate`.

**Trường hợp 2 — Ứng dụng khai báo `@Bean("redisTemplate")`:** Bean đó chiếm tên chuẩn, nên Boot không tạo `redisTemplate` mặc định. Việc này không tự động tắt `StringRedisTemplate`.

**Trường hợp 3 — Ứng dụng khai báo `@Bean("customRedisTemplate")` kiểu `RedisTemplate`:** Vì tên `redisTemplate` vẫn trống, Boot có thể tiếp tục tạo bean mặc định tên `redisTemplate`. Khi inject trực tiếp theo kiểu `RedisTemplate`, ứng dụng có thể gặp nhiều ứng viên; nên dùng `@Qualifier`, `@Primary` hoặc thiết kế bean rõ ràng.

**Trường hợp 4 — Ứng dụng đã có `StringRedisTemplate` dù đặt tên khác:** Điều kiện thiếu bean theo kiểu không còn thỏa, nên `stringRedisTemplate` mặc định thường không được tạo.

**Trường hợp 5 — Có hai factory mà không có ứng viên chính:** `@ConditionalOnSingleCandidate(RedisConnectionFactory.class)` không thỏa, các template mặc định có thể vắng mặt. Đây là cơ chế tránh việc Boot đoán factory nào là đúng.

`RedisTemplate<Object, Object>` là template tổng quát; không nên mặc định rằng nó serialize mọi object ra JSON. Serializer mặc định của RedisTemplate có các lựa chọn tương thích với Java serialization; với giao thức trao đổi hoặc format dùng chung, hãy cấu hình serializer có chủ đích.

### 4.4. Khi nào reactive template xuất hiện?

`RedisReactiveAutoConfiguration` của Boot 3.3 được áp dụng sau `RedisAutoConfiguration` và có điều kiện classpath chứa:

- `ReactiveRedisConnectionFactory`,
- `ReactiveRedisTemplate`,
- Reactor `Flux`.

Hai phương thức cấu hình reactive yêu cầu thêm một bean `ReactiveRedisConnectionFactory`:

| Bean | Điều kiện riêng |
|---|---|
| `reactiveRedisTemplate` | Có reactive factory, chưa có bean tên `reactiveRedisTemplate` |
| `reactiveStringRedisTemplate` | Có reactive factory, chưa có bean tên `reactiveStringRedisTemplate` |

Lettuce cung cấp khả năng reactive phù hợp qua `LettuceConnectionFactory`. Sự hiện diện của `ReactiveRedisTemplate` **không đòi hỏi cả ứng dụng phải là WebFlux**; đây là điều kiện về API và factory, không phải chỉ là điều kiện “ứng dụng web reactive”.

Ví dụ một service reactive:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String key) {
        return redis.opsForValue().increment("counter:" + key);
    }
}
~~~

Giá trị `Mono<Long>` mô tả một thao tác bất đồng bộ; việc thực thi phụ thuộc subscription trong luồng reactive. Đừng dùng `block()` tùy tiện trong pipeline non-blocking.

### 4.5. Redis repositories là nhánh tự cấu hình riêng

Không phải có `RedisTemplate` là Boot luôn tạo Redis repository cho mọi interface. `RedisRepositoriesAutoConfiguration` có các điều kiện riêng:

- Classpath có `EnableRedisRepositories`.
- Context có `RedisConnectionFactory`.
- `spring.data.redis.repositories.enabled` có giá trị `true` hoặc không khai báo (mặc định bật).
- Chưa có `RedisRepositoryFactoryBean` phù hợp khiến auto-configuration phải nhường quyền.

Khi đủ điều kiện, Boot import registrar để tổ chức cấu hình các Redis repository theo quy tắc quét của Spring Data.

~~~yaml
spring:
  data:
    redis:
      repositories:
        enabled: false
~~~

Cấu hình này chỉ tắt việc **tự cấu hình Redis repositories**. `RedisConnectionFactory`, `RedisTemplate` hoặc `StringRedisTemplate` vẫn có thể tồn tại để ứng dụng thao tác trực tiếp.

Ví dụ repository nếu ứng dụng chọn mô hình này:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.repository.CrudRepository;

@RedisHash("session")
public class SessionRecord {
    @Id
    private String id;
    private String owner;

    // Constructors, getters và setters phù hợp
}

public interface SessionRepository
        extends CrudRepository<SessionRecord, String> {
}
~~~

Ví dụ tập trung vào loại bean và annotation mapping; để vận hành cần định nghĩa hoàn chỉnh entity và quyết định chính sách TTL/indexing phù hợp. `@RedisHash` không tương đương với việc bật Hibernate/JPA cho Redis.

### 4.6. Redis cache manager có phải luôn được tạo không?

**Không.** Spring Cache là một lớp cơ chế khác. `RedisCacheManager` phụ thuộc việc ứng dụng bật và thỏa điều kiện auto-configuration của Spring Cache, ví dụ dùng `@EnableCaching` và có `RedisConnectionFactory` để chọn Redis làm cache provider.

Sự hiện diện của Redis starter **không** đồng nghĩa mọi method gắn `@Cacheable` sẽ có cache hoạt động với Redis. Cần phân biệt ba thứ:

1. **Redis template** để gọi lệnh Redis trực tiếp.
2. **Redis repositories** để thao tác entity theo abstraction repository.
3. **Redis cache manager** để hỗ trợ abstraction Spring Cache.

Ba nhánh có điều kiện và quy tắc cấu hình riêng. Đây là lý do không thể chỉ nhìn thấy `RedisConnectionFactory` rồi khẳng định toàn bộ tính năng Redis của ứng dụng đã sẵn sàng.

## 5. Tự định nghĩa bean để Boot nhường quyền đúng chỗ

### 5.1. Cấu hình một `RedisTemplate` với serializer chủ động

Nếu dữ liệu của ứng dụng dùng key/value chuỗi và muốn có template kiểu rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class RedisTemplateConfiguration {

    @Bean("redisTemplate")
    RedisTemplate<String, String> redisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        StringRedisSerializer serializer = new StringRedisSerializer();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(serializer);
        template.setValueSerializer(serializer);
        template.setHashKeySerializer(serializer);
        template.setHashValueSerializer(serializer);

        return template;
    }
}
~~~

Bean này tên `redisTemplate`, nên Boot không tạo thêm bean tổng quát cùng tên. Factory vẫn có thể do Boot tự tạo. Bean `StringRedisTemplate` mặc định vẫn có thể được tạo vì đây là kiểu khác.

Nên đặt tên bean chuẩn nếu mục tiêu thật sự là thay thế bean Boot mặc định. Nếu muốn bổ sung thêm template độc lập, hãy dùng tên riêng và `@Qualifier` tại chỗ inject.

**Lưu ý về kiểu generic:** `RedisTemplate<String, String>` cho phép API Java rõ hơn, nhưng không có nghĩa Redis server biết đến kiểu Java. Serializer mới quyết định bytes được gửi lên Redis và phải nhất quán với dữ liệu cũ cũng như các client khác.

### 5.2. Tự khai báo `RedisConnectionFactory`

Khi có yêu cầu kết nối không đáp ứng được bằng properties/customizer, ứng dụng có thể sở hữu factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class RedisConnectionConfiguration {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(server);
    }
}
~~~

Khi bean kiểu `RedisConnectionFactory` này được phát hiện, cấu hình tạo factory mặc định của Boot sẽ nhường quyền; các template mặc định có thể **tiếp tục** được sinh từ factory tùy chỉnh nếu chúng thỏa điều kiện.

Đây là ví dụ đơn giản cho thấy cơ chế, không phải khuyến nghị chuyển host/port từ YAML vào source. Sau khi tự tạo factory, **đừng giả định mọi `spring.data.redis.*` vẫn tự áp vào factory đó**: bạn đã chịu trách nhiệm truyền cấu hình, credentials, timeout, SSL hoặc các tùy chọn cần thiết.

Nếu chỉ cần tinh chỉnh Lettuce mà vẫn muốn giữ cơ chế Boot, hãy ưu tiên bean `LettuceClientConfigurationBuilderCustomizer` hoặc `ClientResourcesBuilderCustomizer` khi phù hợp. Với Jedis có `JedisClientConfigurationBuilderCustomizer`. Những extension point này cho phép tùy biến mà không phải thay hẳn factory.

### 5.3. Có hai `RedisConnectionFactory`: chuyện gì xảy ra?

Giả sử ứng dụng truy cập hai Redis khác nhau, mỗi nơi có factory riêng:

~~~java
@Configuration(proxyBeanMethods = false)
public class TwoRedisConnections {

    @Bean("cacheRedisConnectionFactory")
    RedisConnectionFactory cacheFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("cache-redis", 6379));
    }

    @Bean("sessionRedisConnectionFactory")
    RedisConnectionFactory sessionFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("session-redis", 6379));
    }
}
~~~

Hai tên host trong ví dụ chỉ là tên minh họa; môi trường thực tế phải cung cấp DNS/endpoint tương ứng.

Cả hai bean có cùng kiểu `RedisConnectionFactory`. Nếu không có một ứng viên được chọn làm chính, điều kiện `@ConditionalOnSingleCandidate` cho template mặc định sẽ không thỏa. Constructor inject `StringRedisTemplate` có thể báo thiếu bean.

Có hai cách thiết kế tùy mục đích:

- Nếu muốn một factory mặc định dùng chung và các factory khác dùng khi chỉ định, đánh dấu đúng một factory bằng `@Primary`. Auto-configuration có thể sử dụng factory chính.
- Nếu muốn hai kết nối độc lập, khai báo template riêng với `@Qualifier` để không phụ thuộc vào lựa chọn ngầm.

Ví dụ template gắn đúng factory cache:

~~~java
@Bean("cacheStringRedisTemplate")
StringRedisTemplate cacheStringRedisTemplate(
        @Qualifier("cacheRedisConnectionFactory")
        RedisConnectionFactory factory) {
    return new StringRedisTemplate(factory);
}
~~~

Đoạn trên là một method cần đặt trong lớp `@Configuration` và import `@Bean`, `@Qualifier`, `StringRedisTemplate`, `RedisConnectionFactory` tương ứng. Mỗi template cụ thể nên có quy ước đặt tên rõ ràng để service nhận đúng kết nối.

Nếu bean theo kiểu `StringRedisTemplate` do người dùng tạo trước, auto-configuration thường sẽ nhường quyền cho bean đó. Tránh phụ thuộc vào việc Boot tự tạo một `stringRedisTemplate` thứ hai khi bạn đã chủ động định nghĩa template.

### 5.4. Không dùng `@Primary` để che giấu cấu hình chưa rõ

`@Primary` giải quyết việc chọn ứng viên mặc định cho dependency injection; nó không tự phân vùng dữ liệu, không tự chuyển request tới Redis phù hợp, và không bảo đảm các repository/cache sẽ dùng đúng template. Với nhiều Redis có vai trò khác nhau, nên chỉ định kết nối theo tên cho từng nhóm chức năng và xem cả cấu hình repository/cache.

Trong hệ thống lớn, “hai RedisConnectionFactory + một template ngầm” thường dễ gây lỗi hơn “mỗi Redis có template và repository configuration minh bạch”.

## 6. Đọc kết quả điều kiện thay vì đoán

### 6.1. Khởi động với báo cáo điều kiện

Chạy ứng dụng Spring Boot ở chế độ debug:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể in **Condition Evaluation Report**, trong đó có những nhóm điều kiện phù hợp và không phù hợp. Tìm các tên:

~~~text
RedisAutoConfiguration
LettuceConnectionConfiguration
JedisConnectionConfiguration
RedisReactiveAutoConfiguration
RedisRepositoriesAutoConfiguration
~~~

Ví dụ cách diễn giải log (minh họa, không phải output cố định):

~~~text
RedisAutoConfiguration matched:
  @ConditionalOnClass found RedisOperations

RedisAutoConfiguration#redisTemplate did not match:
  @ConditionalOnMissingBean found bean named 'redisTemplate'
~~~

Ý nghĩa: Spring Data Redis có mặt nên lớp cấu hình được xét, nhưng phương thức tạo `redisTemplate` mặc định đã nhường quyền vì ứng dụng có bean tên đó. **“Did not match” không nhất thiết là lỗi**; có thể đó chính là kết quả mong muốn.

Nếu đã dùng Spring Boot Actuator và cấu hình cho phép, endpoint `/actuator/conditions` cũng cung cấp báo cáo bằng JSON. Ví dụ chỉ nên bật exposure ở môi trường quản trị phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Endpoint điều kiện có thể tiết lộ cấu trúc nội bộ ứng dụng, cần được bảo vệ bởi cấu hình mạng/bảo mật của hệ thống. Không mặc nhiên công khai endpoint chỉ để debug production.

### 6.2. Kiểm tra bean thực sự có trong context

Có thể viết một bean quan sát nhỏ để xem các ứng viên tại thời điểm khởi động:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

@Component
public class RedisBeanInspector implements ApplicationRunner {

    private final ApplicationContext context;

    public RedisBeanInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("Factories: " + Arrays.toString(
                context.getBeanNamesForType(RedisConnectionFactory.class)));
        System.out.println("Redis templates: " + Arrays.toString(
                context.getBeanNamesForType(RedisTemplate.class)));
        System.out.println("String templates: " + Arrays.toString(
                context.getBeanNamesForType(StringRedisTemplate.class)));
    }
}
~~~

Đây là đoạn quan sát tạm thời cho môi trường học/lập trình; không cần duy trì `System.out.println` trong ứng dụng production. Kiểm tra này giải đáp **bean đã đăng ký hay chưa**, chưa xác thực một lệnh Redis thực sự thành công.

Nếu kiểm tra connectivity, phải thực hiện một thao tác có kiểm soát và phân biệt rõ lỗi mạng, lỗi xác thực, timeout với lỗi thiếu bean. Có thể xem Redis health indicator của Actuator khi đã cấu hình.

### 6.3. Sơ đồ tra cứu nhanh khi inject thất bại

~~~mermaid
flowchart TD
    A["Inject StringRedisTemplate thất bại"] --> B{"RedisOperations có trong classpath?"}
    B -->|Không| C["Kiểm tra starter/dependency"]
    B -->|Có| D{"Có RedisConnectionFactory?"}
    D -->|Không| E["Kiểm tra driver, cấu hình factory, condition report"]
    D -->|Có| F{"Có nhiều factory không rõ ứng viên chính?"}
    F -->|Có| G["Dùng @Primary hoặc template riêng + @Qualifier"]
    F -->|Không| H{"Đã có StringRedisTemplate do người dùng tạo?"}
    H -->|Có| I["Kiểm tra tên, type, qualifier và phạm vi context"]
    H -->|Không| J["Đọc condition của RedisAutoConfiguration#stringRedisTemplate"]
~~~

Khi trace một lỗi, nên bắt đầu từ **bean thiếu cụ thể**, sau đó lần ngược đến dependency của nó. Một message kiểu “No qualifying bean of type StringRedisTemplate” là câu chuyện về context và điều kiện; “RedisConnectionFailureException” hoặc timeout trong lúc chạy là câu chuyện về kết nối.

## 7. Các lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân đáng kiểm tra | Cách suy luận |
|---|---|---|
| Không inject được `StringRedisTemplate` | Thiếu starter, auto-config bị exclude, thiếu factory, nhiều factory | Tìm `RedisAutoConfiguration#stringRedisTemplate` trong condition report |
| Boot tạo `redisTemplate` dù đã có template tự định nghĩa | Bean tự định nghĩa đặt tên khác `redisTemplate` | Điều kiện của default `redisTemplate` xét **tên** |
| Không có bean `stringRedisTemplate` đúng tên nhưng có một `StringRedisTemplate` khác | Bean kiểu này do ứng dụng cung cấp khiến Boot nhường quyền | Đọc kết quả `@ConditionalOnMissingBean` theo kiểu |
| Inject `RedisConnectionFactory` bị mơ hồ | Hai factory không có lựa chọn rõ | Dùng `@Qualifier` hoặc chủ động thiết kế `@Primary` |
| Redis repositories không được đăng ký | `repositories.enabled=false`, thiếu classpath, thiếu factory hoặc scanning không phù hợp | Kiểm tra `RedisRepositoriesAutoConfiguration` và phạm vi quét |
| Chỉ có template đồng bộ, không có reactive template | Thiếu reactive API/factory hoặc đang dùng driver không hỗ trợ | Xem `RedisReactiveAutoConfiguration` và `ReactiveRedisConnectionFactory` |
| Ứng dụng khởi động được nhưng lệnh Redis lỗi | Redis không chạy, sai host, credentials, network, timeout | Kiểm tra connectivity độc lập với bean registration |
| Thay YAML nhưng kết nối vẫn dùng địa chỉ cũ | Đã tự tạo factory không đọc các thuộc tính Boot | Xem định nghĩa factory trong ứng dụng |
| Thuộc tính Redis không có hiệu lực | Sai prefix với dòng Spring Boot đang chạy hoặc profile ghi đè | Với Boot 3.x kiểm tra `spring.data.redis.*` và effective configuration |

Một trường hợp dễ bỏ qua là **đặt nhầm tên bean**. Nếu tạo bean bất kỳ tên `redisTemplate` nhưng kiểu không tương thích, Boot vẫn có thể xem tên đó là đã chiếm, khiến template mong muốn không được tạo. Không nên dùng tên bean chuẩn cho đối tượng không cùng ý nghĩa.

Một trường hợp khác là ứng dụng dùng nhiều `ApplicationContext` (parent/child) hoặc tự import/exclude auto-configuration. Điều kiện bean được đánh giá trong bối cảnh context và quy tắc tìm bean của annotation; khi cấu hình phức tạp, log điều kiện chính xác hơn việc chỉ đếm số lớp trên classpath.

## 8. Bốn thí nghiệm tư duy về quy tắc tạo bean

Để xác định chính xác kết quả, hãy giả sử classpath có Spring Data Redis và Lettuce, cấu hình Redis của Boot không bị exclude.

**Thí nghiệm 1: Không khai báo `@Bean` Redis nào.**

Boot có thể tự cấu hình một `LettuceConnectionFactory` và từ đó tạo `redisTemplate`, `stringRedisTemplate`. Nếu reactive API/factory thỏa điều kiện, các reactive template cũng có thể xuất hiện. Dù vậy Redis server thật vẫn có thể chưa sẵn sàng.

**Thí nghiệm 2: Tạo bean tên `redisTemplate`.**

Boot giữ bean của bạn và bỏ qua method tạo `redisTemplate` mặc định. `StringRedisTemplate` không bị tắt chỉ vì đã có `RedisTemplate` thường, vì điều kiện của nó kiểm tra kiểu riêng.

**Thí nghiệm 3: Tạo hai `RedisConnectionFactory`, không đánh dấu `@Primary`.**

Boot không thể chọn một factory duy nhất cho các method có `@ConditionalOnSingleCandidate`, nên không nên mong đợi default template được tạo. Hãy đánh dấu một ứng viên chính hoặc khai báo template với `@Qualifier` cho từng factory.

**Thí nghiệm 4: Đặt `spring.data.redis.repositories.enabled=false`.**

Nhánh repository tự động dừng hoạt động, nhưng factory và các template vẫn có thể được Boot tạo bình thường. Tắt repository không đồng nghĩa tắt Redis.

Những thí nghiệm này giúp hiểu ba tầng ra quyết định: **thư viện có mặt → bean nền tảng có thể tạo → bean phụ thuộc được phép tạo**.

## 9. Nguyên tắc áp dụng khi bắt đầu một module Spring Data Redis

1. **Chỉ thêm starter và cấu hình `spring.data.redis.*` trước khi tự viết factory.** Cách này giúp Spring Boot quản lý phần cấu hình chung và dễ quan sát các bean mặc định.
2. **Chọn API theo nhu cầu:** `StringRedisTemplate` cho dữ liệu chuỗi, `RedisTemplate` có serializer rõ ràng cho kiểu khác, reactive template khi cần pipeline reactive.
3. **Nhìn annotation trên từng bean:** `redisTemplate` mặc định kiểm tra *tên*, `StringRedisTemplate` kiểm tra *kiểu*, cả hai cần một factory ứng viên phù hợp trong Boot 3.3.
4. **Chỉ ghi đè phần thực sự cần:** customizer khi cần tinh chỉnh driver, bean template riêng khi cần serializer khác, factory riêng khi cơ chế kết nối đã vượt khả năng properties.
5. **Với nhiều factory, cấu hình minh bạch:** tên bean, `@Qualifier`, `@Primary` và kết nối của mỗi repository/cache phải rõ ràng.
6. **Phân biệt lỗi auto-configuration với lỗi Redis runtime:** có bean không có nghĩa server đã kết nối; đọc `ConditionEvaluationReport` trước khi thay dependency theo phỏng đoán.
7. **Không quên hiệu ứng phiên bản:** tên property, điều kiện và package có thể thay đổi giữa các dòng Spring Boot; dùng tài liệu cùng dòng phiên bản với ứng dụng.

Cơ chế tự cấu hình của Spring Boot giúp ta khởi tạo Redis bằng rất ít mã, nhưng sức mạnh của nó đến từ **các điều kiện có thể kiểm tra được**. Khi hiểu `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnSingleCandidate` và các nhánh auto-configuration Redis, bạn có thể dự đoán bean nào xuất hiện, thay thế đúng bean mặc định và truy được nguyên nhân khi cấu hình không khớp.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Working with NoSQL Technologies: Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring Boot 3.3 API — RedisAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisAutoConfiguration.html)
- [Spring Boot 3.3 API — RedisReactiveAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisReactiveAutoConfiguration.html)
- [Spring Boot 3.3 API — RedisRepositoriesAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/data/redis/RedisRepositoriesAutoConfiguration.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 Actuator — Conditions Evaluation Report](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)

# Chính sách null và cơ chế thích nghi giá trị của nhà cung cấp trong Spring Cache

## 1. Mục tiêu và câu hỏi thiết kế

Khi một phương thức được đánh dấu `@Cacheable` trả về `null`, Spring phải quyết định liệu **“không có giá trị nghiệp vụ”** có nên trở thành một **cache entry hợp lệ** hay không. Vấn đề không đơn giản là đưa `null` vào một `Map`: nhiều cache store như `ConcurrentHashMap` và Caffeine native cache **không cho phép lưu Java null trực tiếp**. Spring Cache có một lớp thích nghi (value adaptation) giúp biểu diễn cached null bằng một marker nội bộ, rồi chuyển marker trở lại `null` khi đọc.

Ba câu hỏi phải được phân biệt:

1. **Có tồn tại entry hay không?** Cache miss nghĩa là chưa có mapping cho key, hoặc entry đã hết hạn/bị xóa. Cache hit với giá trị `null` nghĩa là **mapping có tồn tại nhưng nội dung nghiệp vụ là null**.
2. **Có chấp nhận cache null không?** Chính sách tùy `CacheManager`/`Cache` implementation và cấu hình. `@Cacheable(unless = "#result == null")` là một cách **không ghi kết quả null**, khác hoàn toàn với việc provider **từ chối** lưu null.
3. **Provider cất dữ liệu như thế nào?** Spring có thể thay `null` bằng `NullValue.INSTANCE` hoặc một biểu diễn được provider/serializer hỗ trợ. Ứng dụng thông thường phải làm việc qua abstraction `Cache`, không tự giả định native cache chứa raw Java null.

Bài học thuộc nhóm **Dữ liệu và vòng đời**: tập trung vào chính sách nhận/lưu/đọc `null`, cơ chế thích nghi giá trị tại provider, vòng đời cached null, cách kiểm thử và các lỗi tích hợp. Không dùng bài này để thay thế hướng dẫn thiết kế key, transaction hay chiến lược TTL đầy đủ; các chủ đề đó chỉ được nhắc tới nơi chúng trực tiếp ảnh hưởng tính đúng đắn của cached null.

## 2. Ba trạng thái khác nhau: miss, hit-null, hit-value

Tại tầng API, phải phân biệt các trạng thái sau cho cùng key `k`:

| Trạng thái logic | Key có mapping? | `Cache.get(k)` | `Cache.ValueWrapper.get()` nếu có |
| --- | --- | --- | --- |
| **Miss** | Không | `null` | Không có wrapper |
| **Hit với null** | Có, nếu provider hỗ trợ | `ValueWrapper` **khác null** | `null` |
| **Hit với giá trị khác null** | Có | `ValueWrapper` **khác null** | Giá trị nghiệp vụ |

Đây là contract của `Cache.get(Object)`. Câu `cache.get(k) == null` có nghĩa **không có entry**; còn `cache.get(k).get() == null` (sau khi kiểm tra wrapper khác null) có nghĩa **entry có mặt và lưu null**. Điều này giải quyết sự nhập nhằng mà `ConcurrentHashMap` tự thân không xử lý được.

Ví dụ đúng khi dùng Cache API trực tiếp:

~~~java
Cache.ValueWrapper wrapper = cache.get(key);
if (wrapper == null) {
    // Cache miss: có thể gọi nguồn và put giá trị mới
} else {
    Object businessValue = wrapper.get();
    // Cache hit: businessValue có thể là null!
}
~~~

Đây là snippet yêu cầu biến `Cache cache` và `Object key` được định nghĩa trước, không phải một file Java độc lập.

**Cẩn thận với overload `get(key, Class<T>)`:** dạng typed get trả trực tiếp `T` hoặc `null`. Theo contract Spring, nó **không phân biệt** được “cache miss” và “hit-null”, bởi cả hai đều có thể cho giá trị trả về `null`. Khi logic yêu cầu phân biệt, hãy dùng `get(key)` và kiểm tra `ValueWrapper`.

Một ví dụ ngữ nghĩa:

~~~text
get("id-1") == null                       => không có entry (miss)
get("id-2") != null
get("id-2").get() == null                 => entry lưu null (hit-null)
get("id-3") != null
get("id-3").get().equals("active")        => entry lưu "active" (hit-value)
~~~

Ba dòng cuối là biểu diễn logic, không phải lệnh Java đầy đủ; code thực phải kiểm tra null trước khi gọi `get()` hoặc `equals()`.

## 3. Cơ chế thích nghi: vì sao NullValue tồn tại?

Spring cung cấp lớp `org.springframework.cache.support.AbstractValueAdaptingCache`, là base class của một số implementation như `ConcurrentMapCache`, `CaffeineCache` và `JCacheCache`. Vai trò của nó là chuyển **giá trị ở tầng ứng dụng** sang **giá trị có thể lưu trong store**:

- `toStoreValue(userValue)`: chuyển từ giá trị nghiệp vụ sang representation trong native store.
- `fromStoreValue(storeValue)`: giải mã representation từ native store về giá trị nghiệp vụ.
- `toValueWrapper(storeValue)`: chuyển raw store value thành `Cache.ValueWrapper` (thường là `SimpleValueWrapper`), sau khi thực hiện value adaptation.
- `isAllowNullValues()`: cho biết instance cache có cho phép thích nghi giá trị `null` hay không.

Khi cấu hình cho phép cached null, với những cache dùng lớp này, `toStoreValue(null)` thay null bằng marker nội bộ `org.springframework.cache.support.NullValue.INSTANCE`. Native cache thực sự lưu một object **khác null**. Khi đọc lại, `fromStoreValue(NullValue.INSTANCE)` trả `null` cho phía sử dụng abstraction. Marker này là **chi tiết triển khai của Spring**; không nên trả `NullValue.INSTANCE` từ business method hoặc truyền marker đó qua API/domain như một giá trị đặc biệt.

~~~mermaid
flowchart LR
    A[Method trả Java null] --> B[Spring Cache put]
    B --> C{allowNullValues?}
    C -- Có --> D[toStoreValue: NullValue marker]
    D --> E[Native store ghi object khác null]
    E --> F[Native store lookup hit]
    F --> G[fromStoreValue: Java null]
    G --> H[Cache.ValueWrapper.get = null]
    C -- Không --> I[Không thể put null theo API/provider]
~~~

Trong trường hợp không cho phép null, attempt `Cache.put(key, null)` có thể bị từ chối bằng exception; **không** nên suy ra việc tắt `allowNullValues` sẽ tự động “bỏ qua null một cách êm ái”. Nếu mong muốn skip null thì phải quyết định tại cache operation, chẳng hạn dùng `unless`.

### Vì sao không lưu null trực tiếp vào ConcurrentHashMap?

`ConcurrentHashMap` không cho null value. Ngoài lý do đồng bộ, native API trả `null` khi không tìm thấy mapping. Nếu value cũng có thể là null, người dùng khó phân biệt không tồn tại với đã lưu một null. Spring dùng marker object để lưu mapping và dùng wrapper ở tầng abstraction để giữ được khác biệt này.

**Không đồng nhất internal marker với biểu diễn trên Redis hoặc JCache:** mỗi provider có cách convert/serialize riêng. Một Redis adapter có thể serialize marker thành bytes phù hợp với codec; một implementation không kế thừa `AbstractValueAdaptingCache` có thể có chính sách hoàn toàn khác. Hợp đồng quan trọng là hành vi của `Cache`, không phải class object nhìn thấy trong native store.

## 4. Chính sách ở các provider phổ biến

| Provider / Spring adapter | Chính sách null đáng chú ý | Cách cấu hình |
| --- | --- | --- |
| `ConcurrentMapCache` / `ConcurrentMapCacheManager` | Manager **mặc định cho phép null** dù `ConcurrentHashMap` không hỗ trợ; dùng holder nội bộ | `manager.setAllowNullValues(false)` để không chấp nhận cached null |
| `CaffeineCache` / `CaffeineCacheManager` | Manager **mặc định cho phép null** qua holder của Spring; **native Caffeine không hỗ trợ Java null** | `manager.setAllowNullValues(false)`; với async mode Spring khuyến nghị vô hiệu hóa null để đơn giản hóa semantics |
| Spring Data Redis `RedisCacheManager` | `RedisCacheConfiguration.defaultCacheConfig()` **mặc định có cache null**; representation trên Redis phụ thuộc serializer | Dùng `RedisCacheConfiguration.defaultCacheConfig().disableCachingNullValues()` để tắt |
| JCache / provider JSR-107 | Phụ thuộc adapter, provider và cấu hình, không giả định giống ConcurrentMap | Kiểm tra contract, provider-specific null policy và test integration |
| `NoOpCacheManager` | Không lưu entry, nên không có cached-null hit thực sự | Hữu ích khi muốn vô hiệu hóa caching, không phải một negative-cache store |

Bảng mô tả các mặc định theo tài liệu của **Spring Framework/Spring Data Redis tương ứng**, không phải các bảo đảm chung của mọi framework integration hoặc mọi hệ thống đã cấu hình. Spring Boot auto-configuration có thể tạo `CacheManager` và áp dụng các property/customizer khác, làm thay đổi hành vi cuối. Phải xem bean được sử dụng trong ứng dụng thật.

### ConcurrentMapCacheManager

~~~java
@Bean
CacheManager cacheManager() {
    var manager = new ConcurrentMapCacheManager("products", "missingProducts");
    manager.setAllowNullValues(false);
    return manager;
}
~~~

Snippet này cần Spring configuration class, imports và bean tương ứng. `setAllowNullValues(false)` quyết định manager **không chấp nhận null** trong những `ConcurrentMapCache` do nó quản lý. Không tự suy ra các method trả null sẽ bị Spring bỏ qua: nếu Spring cố `put(null)` vào một cache không cho phép null, operation có thể ném `IllegalArgumentException`. Phải sử dụng `unless` khi cần tránh put null.

Lưu ý từ Javadoc: thay đổi cấu hình null sau khi cache đã được tạo có thể **reset/recreate các cache**, không phải chỉ thay một biến mà không ảnh hưởng dữ liệu. Nên cấu hình trước khi hệ thống bắt đầu sử dụng cache.

### CaffeineCacheManager

~~~java
@Bean
CacheManager caffeineManager() {
    var manager = new CaffeineCacheManager("products");
    manager.setAllowNullValues(false);
    manager.setCacheSpecification("maximumSize=10000,expireAfterWrite=10m");
    return manager;
}
~~~

Đây là snippet yêu cầu dependency Caffeine và loại cache phù hợp; mốc size/TTL chỉ là ví dụ. Native Caffeine không nhận null, còn Spring Caffeine adapter có thể dùng marker nếu bật allow-null. Ở async cache mode, Spring lưu ý việc disallow null giúp semantics của future-based retrieval đơn giản và hiệu quả hơn. **Không dùng các con số trên như cấu hình production chung** nếu chưa tính hit rate, memory, cardinality, invalidation.

### RedisCacheConfiguration

~~~java
RedisCacheConfiguration config =
        RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(2))
            .disableCachingNullValues();

RedisCacheManager manager = RedisCacheManager
        .builder(redisConnectionFactory)
        .cacheDefaults(config)
        .build();
~~~

Snippet này cần Spring Data Redis, `RedisConnectionFactory redisConnectionFactory` và imports. Khi cấu hình Redis **không cache null**, một lệnh put với value null theo cache API sẽ bị từ chối, **không có nghĩa tự động xóa key cũ**. Đặc biệt, Javadoc của `disableCachingNullValues()` cảnh báo: nếu put null, lệnh sẽ error, không ghi gì và **một key đã có sẵn vẫn giữ nguyên nội dung cũ**. Nếu null có nghĩa “bản ghi đã bị xóa”, hãy chủ động `evict` key cũ thay vì mong một put-null trong chế độ disabled sẽ clear.

Mặc định RedisCacheConfiguration có cache null, key prefix theo cache name và serializer mặc định riêng; việc chuyển từ local cache sang Redis có thể thay đổi representation, TTL và cách phát hiện lỗi. Không sử dụng native Redis `GET` như tiêu chuẩn duy nhất để suy luận Spring cache hit/miss.

## 5. Chính sách annotation: cho phép, bỏ qua, và cập nhật null

### 5.1. Cho phép lưu kết quả null: negative caching

~~~java
@Cacheable(cacheNames = "productsById", key = "#p0")
public Product findProduct(String id) {
    return repository.findByIdOrNull(id);
}
~~~

Nếu `findByIdOrNull(id)` trả null, provider hỗ trợ cached null và không có veto, Spring có thể lưu mapping key → null. Lần sau với cùng key, cached-null **là hit**, method không được gọi lại. Đây là **negative caching**: ghi nhớ tạm thời kết quả “không tìm thấy”.

Điều này hữu ích khi những ID không tồn tại bị hỏi lặp lại nhiều lần, ví dụ chống DB query trùng hoặc các lookup có tỷ lệ miss cao. Nhưng khi bản ghi mới xuất hiện, cached null có thể khiến kết quả tiếp tục là null đến lúc TTL hết hoặc bị evict.

### 5.2. Không lưu null bằng unless

~~~java
@Cacheable(
    cacheNames = "productsById",
    key = "#p0",
    unless = "#result == null"
)
public Product findProduct(String id) {
    return repository.findByIdOrNull(id);
}
~~~

`unless` được đánh giá **sau khi method đã chạy trên nhánh cần ghi**. Nếu `#result == null`, Spring **không put**. Nhờ vậy cấu hình cache provider không hỗ trợ null vẫn có thể dùng method đó an toàn đối với nhánh null, miễn không có operation khác đưa null vào cùng cache.

Lưu ý: `unless` không loại bỏ entry cũ đã có. Nếu trước đó key chứa một giá trị không null và method được gọi trong một đường đi khác, “skip put null” không đồng nghĩa xóa entry cũ. Khi dữ liệu nguồn bị xóa hoặc trạng thái đổi từ có sang không, phải có invalidation tường minh bằng `@CacheEvict` hoặc một cơ chế tương đương.

### 5.3. Condition khác unless

| Thuộc tính | Khi nào đánh giá | Có `#result`? | Ví dụ |
| --- | --- | --- | --- |
| `@Cacheable(condition = ...)` | Trước cache lookup/call method, dựa trên input | Không | `condition="#p0 != null"` |
| `@Cacheable(unless = ...)` | Sau khi method đã tạo result cần cache | Có | `unless="#result == null"` |

Không sử dụng `condition="#result != null"` trên `@Cacheable` vì lúc đó method chưa được gọi. `condition` có thể giúp bỏ cache cho input quá động, nhưng không phải cách kiểm tra output null.

### 5.4. CachePut, CacheEvict và giá trị null

`@CachePut` dùng để **ghi kết quả** của method vào cache. Nếu method trả null và provider không nhận null, nó có thể gặp lỗi put; `unless="#result == null"` giúp veto. Nhưng khi “null” có nghĩa bản ghi đã biến mất, việc chỉ veto put có thể để lại một giá trị cache cũ. Hãy xóa entry tương ứng:

~~~java
@CacheEvict(cacheNames = "productsById", key = "#p0")
public void deleteProduct(String id) {
    repository.deleteById(id);
}
~~~

Snippet này dùng trong Spring bean và không phải file Java độc lập. `@CacheEvict` mặc định chạy sau method hoàn tất bình thường; với ứng dụng có transaction cần kiểm tra thời điểm commit và cơ chế transaction-aware cache.

**Không có thuộc tính `unless` trên `@CacheEvict`**. Với eviction có thể dùng `condition`. Việc đặt cả `@CachePut` và `@CacheEvict` trên cùng method cần xác định rõ thứ tự và đối tượng bị thay đổi; thường nên tách command/query đơn giản để dễ test.

## 6. Optional.empty, null, và kết quả wrapper

Spring Cache hỗ trợ Java `Optional<T>`. Với method:

~~~java
@Cacheable(cacheNames = "users", key = "#p0")
public Optional<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Spring unwrap wrapper được hỗ trợ để xử lý cache:

- `Optional.of(user)` → giá trị nghiệp vụ `user` được cache.
- `Optional.empty()` → được xem là giá trị nghiệp vụ **`null`** tại tầng cache.
- Trong `unless`, `#result` tham chiếu **`User` hoặc `null`**, **không phải** `Optional<User>`.
- Khi cache hit với cached null cho một method trả `Optional<User>`, Spring thích nghi kết quả cho caller thành `Optional.empty()`.

Ví dụ khi không muốn negative caching:

~~~java
@Cacheable(cacheNames = "users", key = "#p0",
           unless = "#result == null")
public Optional<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Không nên viết `unless="#result.isEmpty()"`: `#result` không phải Optional, có thể null. Khi cần kiểm tra property của `User`, dùng safe navigation SpEL `#result?.disabled() == true` và quyết định riêng xem null có bị veto hay không: `unless="#result == null || #result?.disabled() == true"`.

### Empty collection không phải null

`Collections.emptyList()`, `List.of()`, chuỗi rỗng `""`, `0` và `false` **không phải** Java null. Một expression `unless="#result == null"` vẫn cho phép cache chúng. Nếu nghiệp vụ không muốn cache danh sách rỗng:

~~~java
@Cacheable(cacheNames = "searchResults",
           unless = "#result == null || #result.isEmpty()")
public List<Product> search(String query) {
    return repository.search(query);
}
~~~

Snippet này giả định method có kiểu `List<Product>` (không phải `Optional<List<Product>>`) và không trả null trong call `isEmpty` do vế đầu dùng short-circuit. Nếu dùng Optional wrapper của list, `#result` là list hoặc null, vẫn phải xử lý tương tự.

**Exception không phải null result:** một method ném lỗi không có kết quả thành công để put theo đường đi thông thường. Không “cache exception dưới dạng null” trừ khi code của bạn chủ động catch exception rồi trả null. Phân biệt “không tìm thấy” với “lookup backend lỗi” để tránh negative caching những lỗi hệ thống tạm thời.

## 7. Ví dụ runnable Java 17+: null được cache, null bị veto và marker trong native store

Ví dụ Spring Framework này kiểm tra bốn hiện tượng: cache null khi manager cho phép; `unless` loại bỏ null; `Optional.empty()` được cache qua adaptation; và `Cache.ValueWrapper` phân biệt hit-null với miss. Ngoài ra dùng một `ConcurrentMapCache` riêng không cho phép null để thấy **put-null bị từ chối**, chứ không bị âm thầm bỏ qua.

Yêu cầu: JDK 17+, Maven. Dùng `spring-context` 7.0.9, là một phiên bản Spring Framework với cache abstraction. Code không cần Redis, Caffeine hay database ngoài.

### 7.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-cache-null-policy</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>7.0.9</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 7.2. src/main/java/demo/NullPolicyDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.Optional;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.support.NullValue;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class NullPolicyDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        CacheManager cacheManager() {
            var manager = new ConcurrentMapCacheManager(
                    "allowed", "skipped", "optional");
            manager.setAllowNullValues(true);
            return manager;
        }

        @Bean
        LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private int allowedLoads;
        private int skippedLoads;
        private int optionalLoads;

        @Cacheable(cacheNames = "allowed", key = "#p0")
        public String allowMissing(String id) {
            System.out.println("source allowed #" + (++allowedLoads));
            return null;
        }

        @Cacheable(cacheNames = "skipped", key = "#p0",
                   unless = "#result == null")
        public String skipMissing(String id) {
            System.out.println("source skipped #" + (++skippedLoads));
            return null;
        }

        @Cacheable(cacheNames = "optional", key = "#p0")
        public Optional<String> optionalMissing(String id) {
            System.out.println("source optional #" + (++optionalLoads));
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(LookupService.class);
            System.out.println("allow1=" + service.allowMissing("x"));
            System.out.println("allow2=" + service.allowMissing("x"));
            System.out.println("skip1=" + service.skipMissing("x"));
            System.out.println("skip2=" + service.skipMissing("x"));
            System.out.println("optional1=" + service.optionalMissing("x"));
            System.out.println("optional2=" + service.optionalMissing("x"));

            CacheManager manager = context.getBean(CacheManager.class);
            ConcurrentMapCache allowed = (ConcurrentMapCache)
                    Objects.requireNonNull(manager.getCache("allowed"));

            Cache.ValueWrapper absent = allowed.get("never");
            Cache.ValueWrapper presentNull = allowed.get("x");
            System.out.println("absent wrapper=" + (absent == null));
            System.out.println("present-null wrapper=" + (presentNull != null));
            System.out.println("wrapped value null="
                    + (presentNull != null && presentNull.get() == null));
            System.out.println("typed value=" + allowed.get("x", String.class));

            // Chỉ để quan sát implementation của ConcurrentMapCache!
            System.out.println("native uses marker="
                    + (allowed.getNativeCache().get("x") == NullValue.INSTANCE));

            ConcurrentMapCache denied = new ConcurrentMapCache("denied", false);
            try {
                denied.put("x", null);
                System.out.println("unexpected: null accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("direct null rejected=true");
            }
        }
    }
}
~~~

Class `LookupService` không implement interface nên Spring có thể dùng class-based proxy để chặn các method public non-final. `context.getBean(LookupService.class)` là bean được Spring quản lý, giúp cache annotation có hiệu lực. Các field counter nằm trên target và chỉ tăng khi business method thực sự chạy.

### 7.3. Cách chạy và stdout

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullPolicyDemo
~~~

Các dòng do chương trình tự in, không tính log phụ của Maven/Spring:

~~~text
source allowed #1
allow1=null
allow2=null
source skipped #1
skip1=null
source skipped #2
skip2=null
source optional #1
optional1=Optional.empty
optional2=Optional.empty
absent wrapper=true
present-null wrapper=true
wrapped value null=true
typed value=null
native uses marker=true
direct null rejected=true
~~~

**Giải thích từng nhánh:**

1. `allowMissing("x")` lần đầu trả null, manager cho phép cache null nên lưu marker; lần hai hit và vẫn trả null. Do đó chỉ có `source allowed #1`.
2. `skipMissing("x")` có `unless="#result == null"` nên hai lần gọi đều không put; counter tăng từ 1 lên 2.
3. `optionalMissing("x")` trả `Optional.empty()`. Cache infrastructure unwrap thành null và lưu theo chính sách allowed; lần hai hit, caller vẫn nhận `Optional.empty()`. Counter không tăng thêm.
4. `allowed.get("never")` trả `null` wrapper: miss. `allowed.get("x")` trả wrapper không null mà nội dung wrapper là null: hit-null. `allowed.get("x", String.class)` chỉ trả null, không phân biệt miss/hit-null.
5. Native map của **đúng ConcurrentMapCache** chứa `NullValue.INSTANCE` cho key `x`. Đây là quan sát để học adapter, **không phải API tích hợp được khuyến nghị**.
6. Cache instance `denied` không cho phép null; `put("x", null)` gây `IllegalArgumentException`, không phải một cache eviction.

**Giới hạn ví dụ:** đây là minh họa trên JVM với `ConcurrentMapCacheManager`, không có TTL, không có Redis, transaction hoặc serializer mạng. Chương trình minh họa không được chạy thực tế trong tài liệu này; output là kết quả dự kiến theo contract Spring. Đối với production, cần chạy test với dependency/version thật.

## 8. Thay chính sách allowNullValues lúc runtime có thể làm mất cache cũ

Với `ConcurrentMapCacheManager`, `setAllowNullValues(boolean)` thường được thiết kế như cấu hình **cho toàn bộ cache do manager tạo**. Javadoc ghi rằng thay đổi setting này sẽ **reset các cache đang tồn tại** để khởi tạo lại chúng theo chính sách mới.

Các hệ quả:

- Không coi chuyển `true → false` là một toggle đơn thuần giữ nguyên mọi cached entry.
- Không dùng việc đổi setting runtime làm cách “xóa các cached null” nếu điều đó còn xóa các giá trị tốt, gây tải đột biến.
- Cấu hình chính sách null **trước khi traffic đến**; nếu migrate, chuẩn bị kế hoạch warm-up và theo dõi hit ratio.
- Với cache phân tán, update cấu hình Spring ở một instance không tự thay cấu hình ở các instance khác. Trong rolling deployment, khác biệt null policy có thể gây kết quả không đồng nhất hoặc lỗi put ở một số node.
- Nếu serializer/schema của cached null thay đổi, version cache name/prefix khi cần. Đừng chia sẻ một vùng Redis giữa những ứng dụng giải mã marker theo quy ước không tương thích.

Thay chính sách cache null có thể còn thay đổi hành vi người dùng: một lookup từng được negative-cache sẽ bắt đầu query database nhiều lần, hoặc ngược lại. Đánh giá cả correctness lẫn tải hệ thống.

## 9. Vòng đời của cached null và negative caching

Khi hệ thống cache một kết quả “không tìm thấy”, entry đó có vòng đời giống entry thường: có thể hết hạn theo TTL, bị evict, bị clear, bị thay thế bởi `@CachePut` hoặc được làm mới theo chính sách provider.

Ví dụ một sản phẩm `P42` chưa tồn tại lúc 09:00:

1. Request `find("P42")` đọc database và nhận null.
2. Cache lưu `P42 → cached null` trong 2 phút.
3. Lúc 09:30 có tiến trình tạo `P42`.
4. Nếu không evict, lần đọc trước khi cached null hết hạn có thể tiếp tục trả “không có sản phẩm”.
5. Sau TTL hoặc `@CacheEvict`, lần đọc mới có thể nhìn thấy sản phẩm.

Ở đây **09:30** chỉ là ví dụ nếu TTL được hiểu theo phút; trong ứng dụng thật, phải xác định thời điểm/TTL nhất quán. Mục tiêu là thấy cached null có thể **stale**, chứ không phải mặc định an toàn vì “nó không chứa dữ liệu”.

Một chính sách negative caching hợp lý có thể dựa trên:

- **Tính ổn định của kết quả miss:** ID không bao giờ hợp lệ hay entity có thể được tạo ngay sau đó?
- **Chi phí truy vấn nguồn:** request lặp lại cho ID sai có gây tải đáng kể không?
- **Tần suất update/delete:** nếu entity được tạo mới, ai đảm nhiệm eviction đúng key?
- **TTL riêng:** negative entry thường cần TTL phù hợp rủi ro stale; có thể ngắn hơn positive entry.
- **Multi-tenant/authorization:** “không thấy” vì không có quyền có thể khác với “không tồn tại”. Cache key phải có scope thích hợp hoặc không cache những kết quả phụ thuộc quyền.
- **Monitoring:** phân biệt hit-null, miss, hit-value, load success/error trong metric nếu implementation hỗ trợ.

**Không biến lỗi hệ thống thành negative cache:** nếu downstream timeout, không nên tự bắt tất cả exception rồi trả null để cache, vì đó là trạng thái “không lấy được dữ liệu” khác với “không tồn tại”. Trường hợp lỗi cần xử lý bằng retry, circuit breaker, error propagation hoặc một mô hình trạng thái domain rõ ràng.

## 10. Khi provider không cho phép null: ba lựa chọn thiết kế

Không có một câu trả lời cho mọi trường hợp. Chọn rõ một trong ba chiến lược:

| Chiến lược | Dùng khi | Đánh đổi |
| --- | --- | --- |
| **Cho phép cache null qua adapter** | Có nhiều lookup không tồn tại, provider hỗ trợ và TTL/invalidation phù hợp | Nguy cơ stale negative entries, phụ thuộc codec/config null marker |
| **Không cache null bằng `unless`** | Null chỉ là miss tạm thời hoặc không muốn negative caching | Mỗi lần miss phải gọi nguồn; dễ tăng tải khi ID sai phổ biến |
| **Domain result kiểu rõ ràng** như `LookupResult.NotFound` | Cần phân biệt NotFound, Forbidden, Timeout, Deleted, Pending… | Thiết kế/serialization phức tạp hơn; phải quy định TTL từng trạng thái |

Với domain result có trạng thái, hãy tránh dùng \`null\` để đại diện cho mọi loại thất bại. Khi dùng sealed interface, enum hoặc record, serializer/backward compatibility cần được kiểm soát khi cache phân tán.

**Đặc biệt với cấu hình disallow null:** đừng chỉ thay manager setting rồi kỳ vọng mọi method `@Cacheable` từng trả null sẽ tự chạy bình thường. Đảm bảo chúng có `unless` thích hợp hoặc trả một result không null theo contract; thêm test cho nhánh null.

## 11. Serializer, native store và cache data compatibility

Một lý do khiến cơ chế value adaptation cần được hiểu là cache provider không nhất thiết lưu Java object trực tiếp.

- **ConcurrentMap:** native store ở cùng JVM, `NullValue.INSTANCE` là object sentinel. Khi inspection raw map, bạn có thể thấy marker, nhưng code nghiệp vụ không nên phụ thuộc vào nó.
- **Caffeine:** Spring adapter có thể dùng holder tương tự. Native Caffeine tự thân không nhận null value. Với async mode, Spring có thêm semantics future-based retrieval, nên null policy cần được test riêng.
- **Redis:** dữ liệu trên mạng là bytes; Spring Data Redis dùng `RedisCacheConfiguration`/`SerializationPair` để serialize key/value. Default serialization có thể khác hoàn toàn cache trong memory. Một null marker sẽ cần representation phù hợp serializer. Đừng giả định raw Redis value bằng một chuỗi `"null"` hoặc rằng xóa/ghi null hoạt động như `Map.put`.
- **JCache:** adapter tuân theo provider SPI và cấu hình của nó. Không đánh đồng JCache, Spring Caffeine và native Redis với một kiểu dữ liệu raw thống nhất.

Không tự put `NullValue.INSTANCE` làm giá trị business, vì sẽ làm rò rỉ marker vào domain và có nguy cơ phá conversion. Không trộn nhiều serializer hoặc phiên bản ứng dụng trong cùng vùng cache mà không có kế hoạch tương thích; một node có thể giải mã cached null sai hoặc lỗi deserialize.

Việc chọn store-by-reference/store-by-value cũng quan trọng: `ConcurrentMapCacheManager` mặc định store-by-reference; nếu bật store-by-value cần giá trị có thể serialize. Điều này không biến Java `null` thành giá trị native hợp lệ; cached null vẫn dùng adaptation phù hợp khi được cho phép.

## 12. API get, get(key, Callable) và retrieve bất đồng bộ

Bên cạnh các method đã học, `Cache` còn có:

- `get(key, Callable<T> valueLoader)`: nếu miss, gọi loader để tạo giá trị; provider có thể đồng bộ các lần load cùng key nếu hỗ trợ. Exception từ loader có thể được bọc thành `Cache.ValueRetrievalException`. Null value do loader trả cần tương thích với null policy của cache; không mặc định được bỏ qua.
- `retrieve(key)` và `retrieve(key, Supplier<CompletableFuture<T>>)` trong các cache hỗ trợ async: cách biểu diễn hit/miss/null phức tạp hơn vì có thể có `CompletableFuture` và đôi khi `ValueWrapper` lồng bên trong. Javadoc phân biệt **early-determined miss** (có thể trả null trực tiếp), **late-determined miss** (future hoàn thành null) và nullable cached value.
- `@Cacheable(sync=true)`: yêu cầu provider phối hợp load theo key khi có concurrent miss, tùy khả năng thực hiện của provider. Nó **không hỗ trợ `unless`**, nên không thể dựa vào `unless="#result == null"` trong operation synchronized này.

Đừng suy ra các quy tắc của `get(key)` đồng nhất với `retrieve(key)` trong mọi implementation. Với async/reactive, cần integration test đặc biệt cho completed future null, missing entry và cancellation/error propagation.

### Reactive/CompletableFuture và null

Spring Framework từ 6.1 có thể thích nghi `CompletableFuture`, Reactor `Mono` và `Flux` trong cache annotations, nhưng các loại này **không đồng nhất** với Java `Optional`. Một `Mono.empty()` không đơn giản là “`Optional.empty()` được cache như null” trong mọi backend hay version. Kiểm tra chính xác publisher semantics, cache retrieval mode, serializer và hành vi khi không phát phần tử. Khi kết quả không tồn tại là một trạng thái nghiệp vụ quan trọng, hãy viết test có cả cache hit/miss, empty publisher và completion exceptional.

## 13. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — Dùng typed get để kiểm tra entry có tồn tại.** `cache.get(key, Product.class) == null` không phân biệt miss với hit-null. Dùng `Cache.ValueWrapper wrapper = cache.get(key)`.

**Lỗi 2 — Cho rằng “provider không hỗ trợ null” nghĩa là Spring cũng không thể cache null.** Với `ConcurrentMapCacheManager` và `CaffeineCacheManager`, Spring mặc định có thể thích nghi qua holder. Kiểm tra cấu hình thực tế thay vì nhìn native provider.

**Lỗi 3 — Nghĩ `allowNullValues=false` tương đương `unless="#result == null"`.** Không đúng: setting provider từ chối put-null, còn `unless` tránh việc put. Nếu tắt support mà vẫn put null, có thể ném exception.

**Lỗi 4 — Trả `Optional.empty()` nhưng viết `unless="#result.isEmpty()"`.** `#result` là value bên trong hoặc null; dùng `#result == null`.

**Lỗi 5 — Không evict cached null khi entity được tạo mới.** Reader vẫn thấy negative cache. Thêm invalidation theo key và TTL phù hợp.

**Lỗi 6 — Đổi `CacheManager.setAllowNullValues` trong runtime rồi cho rằng cache cũ không đổi.** Manager có thể reset cache; dự liệu làm nóng lại và tác động tải nguồn.

**Lỗi 7 — Cho phép cache null với serializer không tương thích.** Redis/remote store có thể lỗi encode/decode, khiến cache hit không trả đúng. Test end-to-end và version schema.

**Lỗi 8 — Dùng raw native cache APIs để đánh giá đúng/sai của Spring Cache.** Adapter tạo marker có thể khiến raw map/Redis hiển thị giá trị khác `null`. Dùng API `Cache` và chú ý contract wrapper.

**Lỗi 9 — Coi empty collection, false, zero là null.** `unless="#result == null"` không loại các giá trị này. Viết policy đúng theo domain.

**Lỗi 10 — Biến timeout/upstream 500 thành null rồi cache dài hạn.** Khi đó hệ thống có thể phục vụ “không tồn tại” giả. Phân biệt business NotFound và lỗi hệ thống.

**Lỗi 11 — Nghĩ null put vào Redis disabled sẽ xóa key cũ.** Theo contract disableCachingNullValues, put-null bị lỗi và key cũ vẫn giữ nguyên. Dùng eviction thật.

**Lỗi 12 — Negative cache thiếu scope phân quyền.** “Không có kết quả” cho user A không nhất thiết đúng với user B. Thiết kế cache key/partition theo tenant và quyền khi chúng ảnh hưởng kết quả.

## 14. Checklist QA trước production

- Method có thể trả `null`, `Optional.empty()`, collection rỗng hay exception? Mỗi trường hợp được phân loại chính xác chưa?
- Với provider đang chạy, null support đang **bật hay tắt**? Có auto-config của Spring Boot/Redis/Caffeine thay đổi default không?
- Với `@Cacheable`, dùng `unless` hay chấp nhận negative caching? Có nhầm `condition` với `unless` không?
- Khi có cache hit-null, client có nhận đúng giá trị `null`/`Optional.empty()` không? Lần đọc thứ hai có thực sự không gọi DB không?
- Code sử dụng `Cache.get(key)` khi cần phân biệt **miss** với **hit-null**, hay nhầm typed get?
- Khi ghi `null` vào cache không cho phép, hệ thống xử lý exception ra sao? Có unintended API failure không?
- Khi một entity được tạo mới hoặc xóa, có invalidation đúng key/cache name và transaction timing không?
- Cached null có TTL/size policy thích hợp không? Có nguy cơ cache stampede nếu bỏ negative caching không?
- Serialization và deployment nhiều node/version có nhất quán không? Có trộn các dạng marker cũ/mới?
- Có test cả `ConcurrentMapCache`, Caffeine/Redis thực tế nếu production dùng chúng, cùng các nhánh null/empty/exception/async không?

## 15. Tài liệu chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `unless`, `Optional` unwrapping, đồng bộ và future/reactive.
- [Spring Framework — Cache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): `Cache.get(Object)`, `ValueWrapper`, typed get, loading và async retrieval.
- [AbstractValueAdaptingCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/AbstractValueAdaptingCache.html): `allowNullValues`, `toStoreValue`, `fromStoreValue`, `NullValue.INSTANCE`.
- [NullValue Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NullValue.html): marker nội bộ thay thế Java null.
- [ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html): default allow-null và cơ chế reset khi thay setting.
- [CaffeineCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html): null holder, async cache mode và config.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html) và [RedisCacheConfiguration Javadoc](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheConfiguration.html): default/null policy, TTL, serializer và disableCachingNullValues.

**Tóm tắt:** `null` trong Spring Cache có thể là **một giá trị đã được cache**, không nhất thiết là **cache miss**. `Cache.ValueWrapper` phân biệt hai trường hợp; `AbstractValueAdaptingCache` và các provider adapters có thể dùng `NullValue` làm marker trong store; còn `allowNullValues` cùng `unless` quyết định khi nào null được chấp nhận hay bị loại. Thiết kế phải gắn với TTL/invalidation, serializer, provider thật và test đúng vòng đời dữ liệu.
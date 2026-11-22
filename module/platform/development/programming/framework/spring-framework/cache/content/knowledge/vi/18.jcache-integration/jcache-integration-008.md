# Nhận diện khi cần Spring Cache hay hợp đồng JCache (JSR-107)

> **Spring Framework – Cache Abstraction · Nhóm: JCache.** Bài học hướng dẫn cách lựa chọn giữa **Spring Cache** và **JCache (JSR-107)** theo nhu cầu thật của hệ thống: mức phụ thuộc framework, tính di động giữa cache provider, giao diện annotation, khả năng tùy biến và cách duy trì key/invalidation nhất quán. Đặc biệt, **chọn annotation JCache không đồng nghĩa bắt buộc dùng backend JCache**.

## 1. Tóm tắt quyết định

**Chọn Spring Cache** khi ứng dụng chủ yếu chạy trong Spring/Spring Boot, cần khai báo cache theo method bằng `@Cacheable`, `@CachePut`, `@CacheEvict`, cần SpEL `key`, `condition`, `unless`, `@Caching` hoặc đang có hạ tầng `CacheManager`/`CacheResolver` ổn định.

**Cân nhắc hợp đồng JCache (JSR-107)** khi một library/module cần sử dụng API cache tiêu chuẩn **không gắn trực tiếp với Spring**, khi tổ chức quy định cache provider phải cung cấp giao diện `javax.cache`, hoặc khi cần các tính năng được mô hình hóa bởi JSR-107 như `CachingProvider`, typed `Cache<K,V>`, `ExpiryPolicy`, entry processor, event listener hay annotation `@CacheResult`.

Không có lựa chọn nào bảo đảm dữ liệu luôn mới hoặc provider nào cũng có cùng hiệu năng. Cả hai là **các hợp đồng trừu tượng**, còn TTL, bộ nhớ, phân tán, tính nhất quán, serialization và transaction phụ thuộc cấu hình/backend.

### Câu hỏi định hướng

1. Code có **chạy bên ngoài Spring** không? Nếu có, Java-standard JCache API có thể là hợp đồng tốt hơn.
2. Ứng dụng có cần **SpEL và các annotation đặc trưng của Spring** không? Nếu có, Spring Cache thường tiện hơn.
3. Có yêu cầu tất cả cache provider phải **tuân JSR-107** không? Nếu có, cần chọn một JCache provider thật, không chỉ thêm annotation JCache.
4. Đang dùng Spring Cache với backend có sẵn và chỉ muốn chuyển annotation sang chuẩn JSR-107? Có thể giữ backend cũ nhờ **Spring hỗ trợ JCache annotations**.
5. Phương thức cập nhật và phương thức đọc có đang **dùng cùng key** không? Chỉ chuyển annotation mà quên key generator dễ gây stale cache.

## 2. Spring Cache và JCache thực chất là gì?

### 2.1. Spring Cache Abstraction

Spring cung cấp các API chính:

- `org.springframework.cache.Cache` và `org.springframework.cache.CacheManager`: lớp trừu tượng truy cập và quản lý vùng cache.
- `org.springframework.cache.annotation.Cacheable`, `CachePut`, `CacheEvict`, `Caching`, `CacheConfig`: khai báo hành vi cache.
- `@EnableCaching` và caching interceptor: kích hoạt cách xử lý annotation trong Spring-managed beans.

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String findProduct(String productId) {
    return repository.findName(productId);
}
~~~

Đây là **đoạn method minh họa** cần một service có `repository` thật, `@EnableCaching` và một `CacheManager` hợp lệ.

Spring Cache **không phải một sản phẩm lưu trữ cache riêng**. Nó có adapter cho nhiều backend như Caffeine, Redis (qua Spring Data), `ConcurrentMapCache` và provider JCache. Đổi backend có thể ít tác động đến annotation nghiệp vụ nếu cache names, keys, serialization và các chính sách vận hành được rà soát.

### 2.2. JCache / JSR-107

**JCache** là tiêu chuẩn Java về caching, còn gọi là **JSR-107 / Java Temporary Caching API**. Trong Spring Framework 6.2, namespace chuẩn vẫn là **`javax.cache`**, không tự đổi thành `jakarta.cache` chỉ vì nhiều API khác đã chuyển sang Jakarta.

JCache định nghĩa:

- `javax.cache.Cache<K,V>`: API cache có key/value kiểu xác định.
- `javax.cache.CacheManager`: quản lý các vùng cache theo tên và cấu hình.
- `javax.cache.Caching` và `javax.cache.spi.CachingProvider`: bootstrap một implementation JSR-107.
- `javax.cache.configuration.MutableConfiguration` và `javax.cache.expiry.ExpiryPolicy`: một số chính sách tiêu chuẩn.
- Các annotation `javax.cache.annotation.CacheResult`, `CachePut`, `CacheRemove`, `CacheRemoveAll`, `CacheDefaults`, `CacheKey`, `CacheValue`.
- Những extension point như `CacheLoader`, `CacheWriter`, event listener và `EntryProcessor` trong phạm vi JCache API.

JCache là **đặc tả hợp đồng**, không phải cache engine. Chỉ thêm `javax.cache:cache-api` vào classpath **không cung cấp một cache backend chạy được**. Nếu dùng trực tiếp `Caching.getCachingProvider()`, ứng dụng cần một **JSR-107 provider** phù hợp trên classpath, cộng cấu hình cache của provider đó.

JCache cũng không yêu cầu ứng dụng phải dùng Spring. Đây là lý do một thư viện muốn ít phụ thuộc Spring có thể cân nhắc tiêu chuẩn này.

## 3. Hai trục lựa chọn độc lập: annotation và backend

Đây là điểm mấu chốt của bài học. Cần phân biệt:

**Trục A – Annotation/caching interception ở tầng ứng dụng:**

- Spring: `@Cacheable`, `@CacheEvict`, `@CachePut` từ `org.springframework.cache.annotation`.
- JSR-107: `@CacheResult`, `@CacheRemove`, `@CachePut` từ `javax.cache.annotation`.

**Trục B – Nơi lưu dữ liệu cache thực tế:**

- Spring provider adapter: `ConcurrentMapCacheManager`, `CaffeineCacheManager`, RedisCacheManager hoặc adapter khác.
- JCache-compliant provider: implementation cho `javax.cache.CacheManager`, dùng trực tiếp hoặc qua adapter `JCacheCacheManager` của Spring.

Ma trận:

| Annotation được dùng | Backend thực tế | Có thể không? | Lưu ý |
| --- | --- | --- | --- |
| Spring `@Cacheable` | Caffeine qua `CaffeineCacheManager` | Có | Spring quản lý interception, Caffeine lưu entry |
| Spring `@Cacheable` | JSR-107 provider qua `JCacheCacheManager` | Có | Spring Cache abstraction chạy trên backend JCache |
| JSR-107 `@CacheResult` | Spring `ConcurrentMapCacheManager` | Có trong Spring | Spring JCache annotation support chuyển operation sang Spring Cache |
| JSR-107 `@CacheResult` | JSR-107 provider | Có | Có thể dùng trong Spring hoặc môi trường có JCache interception tương ứng |

**Kết luận:** “Dùng JCache annotation” và “dùng JCache provider” là **hai quyết định khác nhau**. Để kiểm tra một ứng dụng thực, hãy xem **import annotation**, **CacheManager được đăng ký** và **provider đang chạy**, thay vì đoán từ tên cache.

Spring Framework hỗ trợ JSR-107 annotations khi có API chuẩn và module hỗ trợ đúng trên classpath. Vì vậy một dự án đã dùng Spring Cache có thể chọn annotation JSR-107 nhưng giữ storage hiện tại. Ngược lại, backend JSR-107 vẫn có thể được truy cập bằng annotation Spring.

## 4. So sánh annotation Spring và JSR-107

| Nhu cầu | Spring Cache | JCache (JSR-107) | Điều cần lưu ý |
| --- | --- | --- | --- |
| Cache kết quả method | `@Cacheable` | `@CacheResult` | Hai API đều có hit/miss nhưng key/exception khác nhau |
| Ghi giá trị vào cache | `@CachePut` | `@CachePut` | Cùng tên annotation, **khác semantics** |
| Xóa một entry | `@CacheEvict` theo key | `@CacheRemove` | Cần đồng nhất key với bên đọc |
| Xóa toàn cache | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` | Không xóa cả vùng khi chỉ một record thay đổi |
| Cấu hình chung cấp class | `@CacheConfig` | `@CacheDefaults` | Phạm vi và thuộc tính không hoàn toàn giống |
| Key tùy chỉnh | SpEL `key`, Spring `KeyGenerator` | `@CacheKey`, JCache `CacheKeyGenerator` | Default keys không chắc cùng object/`equals` |
| Điều kiện theo tham số | `condition`, `unless` theo Spring | Không có bản sao SpEL tương đương 1:1 | Chọn API theo nhu cầu thực |
| Cache exception | Không có một lựa chọn annotation trực tiếp tương đương toàn bộ JCache | `@CacheResult` hỗ trợ `cachedExceptions`, `nonCachedExceptions`, `exceptionCacheName` | Phải hiểu tuổi thọ exception cache |
| Bắt method luôn chạy | `@CachePut` hoặc thiết kế phù hợp | `@CacheResult(skipGet=true)` | Không đánh đồng các cách viết |
| Nhóm nhiều cache operation | `@Caching` hỗ trợ nhiều operation | JCache annotation chuẩn có mô hình khác | Spring thuận tiện khi một method tác động nhiều vùng |

### 4.1. @Cacheable và @CacheResult

Spring:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String find(String isbn) {
    return repository.findName(isbn);
}
~~~

JSR-107:

~~~java
@CacheResult(cacheName = "books")
public String find(@CacheKey String isbn) {
    return repository.findName(isbn);
}
~~~

Cả hai là **đoạn code tích hợp minh họa**, cần repository và caching interception. Chúng giống nhau về **mục tiêu** cache kết quả method, nhưng cách xây key mặc định là khác hệ thống. JCache `@CacheKey` giúp chỉ định những tham số được đưa vào key khi có nhiều tham số.

JCache `@CacheResult` có `skipGet`: có thể bỏ qua lookup trước khi method chạy theo hợp đồng của annotation, phù hợp các trường hợp cần ép method thực thi. Nó còn hỗ trợ chính sách cache exceptions được chọn lọc; tính năng này cần cân nhắc đặc biệt vì một lỗi thoáng qua không nên bị cache quá lâu.

Spring `@Cacheable` có SpEL linh hoạt, ví dụ:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public String find(String isbn) {
    return repository.findName(isbn);
}
~~~

Đoạn này minh họa Spring method có repository thật. `condition` được kiểm tra để quyết định caching operation; `unless` đánh giá sau kết quả, có thể từ chối lưu. JSR-107 không cung cấp cùng cú pháp SpEL `condition`/`unless`.

### 4.2. Hai annotation có cùng tên @CachePut nhưng khác nghĩa

Spring:

~~~java
@org.springframework.cache.annotation.CachePut(
    cacheNames = "books", key = "#p0"
)
public String update(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
    return newTitle;
}
~~~

Spring **luôn gọi method** và đưa **giá trị trả về của method** vào cache. Đây là đoạn code minh họa giả định value cache đúng là chuỗi title.

JSR-107:

~~~java
@javax.cache.annotation.CachePut(cacheName = "books")
public void update(
        @CacheKey String isbn,
        @CacheValue String newTitle
) {
    repository.rename(isbn, newTitle);
}
~~~

Ở đây JCache dùng **đối số được đánh dấu `@CacheValue`** làm value để put; không phải dùng kết quả trả về giống Spring. Nó hỗ trợ cấu hình thời điểm put trước/sau invocation theo hợp đồng. Khi migration, không thể thay mỗi import `CachePut` và kỳ vọng semantics giữ nguyên.

### 4.3. Xóa một key và xóa toàn vùng

Spring thường dùng:

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

JSR-107 dùng:

~~~java
@CacheRemove(cacheName = "books")
public void rename(@CacheKey String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

Hai đoạn minh họa cần repository. Về ý định, chúng đều xóa key ISBN sau thao tác cập nhật thành công theo cấu hình mặc định, nhưng chính sách liên quan exception và các cấu hình trước/sau invocation của JCache không trùng hoàn toàn với Spring.

Muốn xóa toàn vùng, Spring dùng `@CacheEvict(allEntries=true)`; JCache dùng `@CacheRemoveAll`. Không áp một conversion tự động không kiểm tra behavior.

## 5. Key generation: nơi migration dễ xảy ra lỗi nhất

Đúng **tên cache** chưa đủ. Một bản ghi chỉ được tìm hoặc evict nếu key **trùng nhau về type và phép so sánh** mà cache provider sử dụng.

### 5.1. Spring mặc định

Spring `SimpleKeyGenerator` thường chọn:

- Không có đối số → `SimpleKey.EMPTY`.
- Một đối số không null → chính đối số đó.
- Nhiều đối số → một `SimpleKey` từ các tham số.

Ví dụ `find(String isbn)` có một đối số thì Spring có thể dùng chính chuỗi `"BK-1"` làm key nếu không có biểu thức/key generator khác.

### 5.2. JCache mặc định

JCache `CacheKeyGenerator` mặc định dựa trên các đối số được chọn. Nếu không đánh dấu `@CacheKey`, thường **mọi đối số hợp lệ** tham gia. Nếu có một hoặc nhiều `@CacheKey`, chỉ các đối số có annotation tham gia, theo hợp đồng JCache.

Một implementation JCache có thể tạo **generated key object** (chẳng hạn wrapper) ngay cả khi có một đối số. Vì vậy, đừng giả định default Spring key `"BK-1"` sẽ bằng JCache generated key cho cùng ISBN.

### 5.3. Bẫy khi trộn annotation trên một cache chung

Ví dụ:

~~~java
// Reader theo Spring: key logic là chuỗi isbn.
@Cacheable(cacheNames = "books", key = "#p0")
public String read(String isbn) {
    return repository.findName(isbn);
}

// Writer theo JCache: key do JCache generator tạo.
@CacheRemove(cacheName = "books")
public void rename(@CacheKey String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

Đây là hai đoạn method tích hợp minh họa. Tuy cùng cache name `"books"`, **chưa thể khẳng định** `@CacheRemove` xóa entry mà `@Cacheable` đã ghi, do **hai chiến lược key khác nhau**. Nếu không khớp, dữ liệu cũ có thể tiếp tục được trả.

**Cách xử lý:**

1. Ưu tiên **một phong cách annotation nhất quán trong cùng một cache region**.
2. Khi buộc phải trộn vì migration, ghi rõ cache name, key type và cách `equals()/hashCode()`/serialization hoạt động.
3. Cấu hình `KeyGenerator` hoặc `CacheKeyGenerator` thích hợp, đảm bảo hai phía tạo cùng key.
4. Viết integration test trên backend thực: gọi đọc → update → xác nhận entry cũ bị xóa → đọc lại nhận nguồn mới.
5. Không đánh giá kết quả chỉ bằng bộ đếm trong một method nếu cache có nhiều tenant hoặc nhiều key biến thể.

**Không gắn đồng thời `@Cacheable` và `@CacheResult` trên cùng một method** trừ khi có lý do rất đặc biệt và test chính xác advice ordering. Dùng mỗi annotation một nơi có chủ đích sẽ dễ bảo trì và tránh caching operation chồng nhau.

## 6. Ví dụ Java 17+ chạy được: hai annotation, một backend Spring Cache

Mục tiêu của ví dụ: **không cần một JCache provider** nhưng vẫn dùng annotation `@CacheResult`/`@CacheRemove` của JSR-107 cạnh `@Cacheable`/`@CacheEvict` của Spring. Spring vận hành caching advice cho cả hai nhóm annotation, còn storage là `ConcurrentMapCacheManager`.

Ví dụ chạy với **Java 17+**, **Spring Framework 6.2.14**, `javax.cache:cache-api:1.1.1`. Đây là phiên bản minh họa cho Spring 6.2; trong dự án thật, quản lý dependency đồng bộ và test phiên bản đang dùng.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-context-support:6.2.14'
    implementation 'javax.cache:cache-api:1.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SpringVsJCacheDemo'
}
~~~

**Tệp `src/main/java/demo/SpringVsJCacheDemo.java`:**

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheResult;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringVsJCacheDemo {

    public static class BookStore {
        private final Map<String, String> values =
                new ConcurrentHashMap<>(Map.of(
                        "S", "Spring-v1",
                        "J", "JCache-v1"
                ));

        public String find(String id) {
            return values.get(id);
        }

        public void rename(String id, String name) {
            values.put(id, name);
        }
    }

    public static class SpringService {
        private final BookStore store;
        private int loads;

        public SpringService(BookStore store) {
            this.store = store;
        }

        @Cacheable(cacheNames = "springBooks", key = "#p0")
        public String read(String id) {
            loads++;
            return store.find(id);
        }

        @CacheEvict(cacheNames = "springBooks", key = "#p0")
        public void rename(String id, String newName) {
            store.rename(id, newName);
        }

        public int loads() {
            return loads;
        }
    }

    public static class StandardService {
        private final BookStore store;
        private int loads;

        public StandardService(BookStore store) {
            this.store = store;
        }

        @CacheResult(cacheName = "jcacheBooks")
        public String read(@CacheKey String id) {
            loads++;
            return store.find(id);
        }

        @CacheRemove(cacheName = "jcacheBooks")
        public void rename(@CacheKey String id, String newName) {
            store.rename(id, newName);
        }

        public int loads() {
            return loads;
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "springBooks", "jcacheBooks"
            );
        }

        @Bean
        public BookStore bookStore() {
            return new BookStore();
        }

        @Bean
        public SpringService springService(BookStore store) {
            return new SpringService(store);
        }

        @Bean
        public StandardService standardService(BookStore store) {
            return new StandardService(store);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            SpringService spring = context.getBean(SpringService.class);
            StandardService standard = context.getBean(StandardService.class);

            System.out.println("spring first: " + spring.read("S"));
            System.out.println("spring again: " + spring.read("S"));
            System.out.println("spring loads: " + spring.loads());

            spring.rename("S", "Spring-v2");
            System.out.println("spring updated: " + spring.read("S"));
            System.out.println("spring loads final: " + spring.loads());

            System.out.println("jcache first: " + standard.read("J"));
            System.out.println("jcache again: " + standard.read("J"));
            System.out.println("jcache loads: " + standard.loads());

            standard.rename("J", "JCache-v2");
            System.out.println("jcache updated: " + standard.read("J"));
            System.out.println("jcache loads final: " + standard.loads());
        }
    }
}
~~~

Chạy với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến của chương trình** (không tính log Gradle):

~~~text
spring first: Spring-v1
spring again: Spring-v1
spring loads: 1
spring updated: Spring-v2
spring loads final: 2
jcache first: JCache-v1
jcache again: JCache-v1
jcache loads: 1
jcache updated: JCache-v2
jcache loads final: 2
~~~

### Vì sao kết quả như vậy?

1. `Config` dùng một `ConcurrentMapCacheManager` của Spring, với hai cache regions độc lập. Không có `javax.cache.spi.CachingProvider` trong ví dụ này.
2. `SpringService.read("S")` được Spring `@Cacheable` intercept; lần đầu miss rồi lần hai hit, nên bộ đếm source load của service là 1.
3. `SpringService.rename("S", "Spring-v2")` cập nhật `BookStore` rồi `@CacheEvict` xóa key chuỗi `"S"` khỏi `springBooks`. Lần đọc sau miss và load lại, bộ đếm thành 2.
4. `StandardService.read("J")` dùng annotation JSR-107 `@CacheResult`, được Spring nhận diện khi có `cache-api` cùng `spring-context-support`. Lần đầu miss, lần hai hit; bộ đếm là 1.
5. `StandardService.rename(@CacheKey "J", "JCache-v2")` dùng `@CacheRemove`. Annotate `@CacheKey` bảo đảm chỉ ID được chọn làm thành phần key ở cả read và write trong **cùng phong cách JCache**. Lần đọc kế tiếp miss, load V2, bộ đếm thành 2.
6. Vì hai cache names khác nhau, ví dụ **không khẳng định** key Spring và JCache mặc định có cùng representation; ngược lại, nó chủ động tránh trộn key trong một region.

**Điều kiện hoạt động:** các service là Spring-managed beans, method public, không final; caller lấy bean từ `ApplicationContext` rồi gọi qua proxy. Gọi trực tiếp `this.read(id)` từ method khác trong cùng target có thể bỏ qua caching advice ở proxy mode.

**Giới hạn:** đây là ứng dụng đơn JVM, không có transaction hoặc database. Output là suy luận từ code và contract của Spring/JCache cho cấu hình trên; cần chạy integration test ở dự án thật nếu provider, interceptor hoặc dependency khác đi.

## 7. Nếu cần dùng backend JCache thật thì cấu hình thế nào?

Khi yêu cầu là **hợp đồng provider JSR-107**, Spring có adapter `org.springframework.cache.jcache.JCacheCacheManager` bọc một `javax.cache.CacheManager` từ provider.

Dòng tích hợp điển hình:

~~~text
Spring @Cacheable / @CacheEvict
            |
Spring CacheManager: JCacheCacheManager
            |
javax.cache.CacheManager (provider thật)
            |
    JCache-compliant cache backend
~~~

Ví dụ cấu hình Spring:

~~~java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JCacheProviderConfig {

    @Bean
    public javax.cache.CacheManager jCacheManager() {
        CachingProvider provider = Caching.getCachingProvider();
        return provider.getCacheManager();
    }

    @Bean
    public org.springframework.cache.CacheManager cacheManager(
            javax.cache.CacheManager jCacheManager
    ) {
        return new JCacheCacheManager(jCacheManager);
    }
}
~~~

**Đây là ví dụ cấu hình tích hợp**, không phải chương trình độc lập. Ngoài `javax.cache:cache-api`, dự án phải thêm **implementation JCache provider** và thiết lập vùng cache của provider. `Caching.getCachingProvider()` không làm việc chỉ với API jar nếu không có provider khả dụng; nếu nhiều provider, phải chọn đúng bằng cấu hình hoặc cơ chế bootstrap cụ thể.

**Sự khác biệt tên lớp quan trọng:**

- `javax.cache.CacheManager`: manager theo **đặc tả JCache**.
- `org.springframework.cache.CacheManager`: manager theo **Spring Cache Abstraction**.
- `JCacheCacheManager`: adapter Spring bọc JCache manager. Tên tương tự nhưng không cùng interface.

Có thể sử dụng Spring annotation với adapter này. Có thể sử dụng JSR-107 annotation thông qua Spring caching interception với adapter này, nhưng nên chọn cách annotation và key strategy rõ ràng.

### Truy cập JCache trực tiếp, không đi qua Spring Cache

Một module Java thuần có thể dùng:

~~~java
javax.cache.spi.CachingProvider provider =
        javax.cache.Caching.getCachingProvider();
javax.cache.CacheManager manager = provider.getCacheManager();
javax.cache.Cache<String, String> cache =
        manager.getCache("books", String.class, String.class);

if (cache == null) {
    throw new IllegalStateException("Required JCache cache 'books' missing");
}
cache.put("BK-1", "Java Basics");
String title = cache.get("BK-1");
~~~

Đây là đoạn code tích hợp cần provider thật đã cấu hình một typed cache tên `books`. Nó không yêu cầu một Spring `ApplicationContext`. Nếu ứng dụng dùng JCache API trực tiếp thì logic lifecycle, close, serialization, expiry và exception handling phải tuân thủ contract/provider.

**Không nhầm JCache với cache phân tán.** Một JCache provider có thể dùng bộ nhớ cục bộ hoặc hỗ trợ phân tán. Tuân JSR-107 không tự bảo đảm cluster replication, consistency giữa instance hay khả năng chống mất dữ liệu.

## 8. Khi nào lựa chọn nào hợp lý hơn?

### Trường hợp A: dự án Spring Boot thuần, muốn cache repository read

**Ưu tiên Spring Cache.** Nhóm đã dùng `@EnableCaching`/Boot caching auto-configuration, có `@Cacheable`, key SpEL và `@CacheEvict`. Thêm JSR-107 annotations không mang lại lợi ích rõ ràng nếu không có yêu cầu tiêu chuẩn hóa liên framework.

Ví dụ: API tra sản phẩm theo SKU, cần bỏ cache khi đổi tên, có tenant ID trong key, yêu cầu cache null riêng và điều kiện `unless`. Spring annotations giúp mô tả khá trực tiếp.

### Trường hợp B: một thư viện Java dùng bởi Spring lẫn ứng dụng Java SE khác

**Cân nhắc JCache standard contract** ở module chung. `javax.cache.Cache`/`CacheManager` cho phép thư viện nói chuyện với một provider chuẩn mà không import `org.springframework.cache`. Tuy nhiên, lớp dùng annotation JSR-107 vẫn cần **một môi trường hỗ trợ interception** nếu muốn annotation tự động chạy; annotation không tự kích hoạt chỉ vì JVM thấy nó.

Thêm adapter ở rìa ứng dụng nếu Spring cần dùng thư viện. Tránh cho library biết đồng thời chi tiết Spring Cache và JCache nếu không cần.

### Trường hợp C: doanh nghiệp yêu cầu đổi giữa nhiều JCache-compliant providers

**Hợp đồng JCache** có thể là lựa chọn cho tầng provider. Cần test portability thật: khả năng cấu hình TTL/expiry, store-by-value so với reference, serialization, entry processor, transactions, monitoring và hiệu năng có thể khác nhau.

Nếu ứng dụng vẫn cần SpEL thì **Spring annotations + JCacheCacheManager** là kết hợp hợp lệ; không nhất thiết chuyển toàn bộ source annotation sang JSR-107.

### Trường hợp D: dự án Spring đã dùng Caffeine, nhưng muốn API annotation JSR-107

Có thể dùng **JSR-107 annotations được Spring hỗ trợ**, trong khi tiếp tục dùng `CaffeineCacheManager`. Điều cần làm là thêm JCache API/module Spring cần thiết và **đảm bảo key/cache names giữ nguyên về hành vi**. Đừng tự kết luận phải tìm một Caffeine JCache provider chỉ vì import `@CacheResult`.

### Trường hợp E: cần cache exceptions theo annotation

JCache `@CacheResult` có tính năng cache một số exception theo `cachedExceptions` và vùng exception cache riêng. Đây có thể là tiêu chí chọn JCache annotations, nhưng cần phân biệt **lỗi vĩnh viễn** (ví dụ ID không hợp lệ) và **lỗi tạm thời** (network timeout). Cache lỗi tạm thời không có TTL thích hợp có thể khuếch đại sự cố.

### Trường hợp F: hệ thống cần async/reactive caching, multi-cache operation hoặc SpEL phức tạp

**Spring Cache** thường hợp hơn khi application boundary nằm trong Spring và cần API/annotation của Spring. Tuy nhiên, hỗ trợ async/reactive phụ thuộc **phiên bản Spring và cache provider**, không nên suy ra mọi cache đều đáp ứng giống nhau. Xác minh đường trả `CompletableFuture`/reactive type, lookup, TTL và thread behavior ở backend thực.

### Trường hợp G: nhóm đang migration từ Spring sang thư viện độc lập

Không chỉ thay annotation. Hãy đánh giá:

- API Spring nào đang được dùng ở domain code.
- Những chức năng nào của Spring `@Cacheable` chưa có bản tương đương trong JCache.
- Trình tạo key và behavior exception.
- Cách chạy interceptors và quản lý provider khi không còn Spring.
- Test để chứng minh caching vẫn đúng trước/sau migration.

**Nguyên tắc:** chọn **mức hợp đồng thấp nhất đủ dùng** cho module. Nếu một ứng dụng hoàn toàn phụ thuộc Spring, không cần thêm một tầng tiêu chuẩn mới chỉ để có tên annotation khác. Nếu một library yêu cầu độc lập Spring, nên giữ Spring integration ở rìa, không rải `org.springframework.cache` khắp public API.

## 9. Các vấn đề không được giải quyết chỉ bằng việc chọn API

### 9.1. Caching không tự bảo đảm dữ liệu mới sau update

Cả Spring Cache lẫn JCache đều có thể trả dữ liệu stale nếu app sửa nguồn mà không invalidation đúng key. `@CacheEvict` hoặc `@CacheRemove` giúp vô hiệu hóa entry nhưng không tự theo dõi database, batch job hay service khác.

Nếu update nằm trong transaction, kiểm tra **thời điểm commit** và thời điểm eviction; method trả thành công chưa chắc transaction đã commit. Với nhiều reader concurrent có thể xảy ra race nơi một reader load dữ liệu cũ rồi put sau eviction.

### 9.2. Provider-specific behavior và tính di động

JSR-107 chuẩn hóa giao diện, **không chuẩn hóa mọi chi tiết vận hành**. Ví dụ:

- Expiry/TTL có thể có cấu hình tiêu chuẩn nhưng default và tính năng nâng cao phụ thuộc provider.
- Phân tán, replication, consistency và quản lý memory ngoài JVM không được bảo đảm chỉ bởi interface.
- `storeByValue`/`storeByReference`, serialization và typed cache cần kiểm tra với implementation đã chọn.
- Metrics, management, event listener và cache loader phải kiểm tra theo backend và cấu hình.
- Một thay đổi giữa providers có thể làm khác hit ratio, latency, thứ tự event hoặc cách xử lý lỗi.

Spring Cache cũng vậy: đổi từ local map sang Redis có thể yêu cầu thiết kế key serialization và null handling mới dù annotation không đổi.

### 9.3. Proxy, self-invocation và interception

Trong Spring proxy mode mặc định, annotation Spring và JSR-107 được Spring tích hợp đều yêu cầu lời gọi đi qua caching interceptor. Một method gắn annotation được gọi từ chính target bằng `this.find("BK-1")` thường **bỏ qua advice**. Tách service hoặc gọi qua proxy đúng cách.

Nếu dùng JCache annotations ngoài Spring, cần một triển khai interceptors tương ứng. Bản thân annotation là metadata, không có khả năng tự thực thi cache.

### 9.4. Dữ liệu null, object mutable và rò rỉ tenant

Không dựa vào tên chuẩn API để kết luận null luôn được cache hoặc một object sẽ được copy sâu. Chính sách null và store-by-value phụ thuộc Spring adapter/provider.

Đặc biệt, key phải tính đủ thành phần ảnh hưởng đến dữ liệu như tenant, locale, currency hoặc permission context khi những yếu tố đó làm kết quả khác nhau. Không chia sẻ một entry cho nhiều tenant chỉ vì cùng một ID.

DTO bất biến hoặc value object rõ hợp đồng thường phù hợp hơn JPA entity mutable/lazy proxy làm cache value. Đừng dùng JCache hay Spring Cache như giải pháp thay thế access control.

## 10. Checklist ra quyết định trong dự án

| Câu hỏi | Nếu câu trả lời là “Có” | Hướng đi |
| --- | --- | --- |
| Toàn bộ module hoạt động bên trong Spring? | Có | Bắt đầu với Spring Cache |
| Cần SpEL `condition`/`unless`/nhiều cache annotations? | Có | Spring annotations thường rõ hơn |
| Library phải chạy không cần Spring? | Có | Xem JCache API hoặc interface trung lập của domain |
| Provider bắt buộc tuân JSR-107? | Có | Chọn JCache provider thật, kiểm tra SPI |
| Chỉ muốn dùng annotation JSR-107 trong Spring? | Có | Dùng Spring JCache annotation support, không bắt buộc đổi provider |
| Cần cache một số exception theo chuẩn? | Có | Đánh giá `@CacheResult`, exception cache và TTL |
| Có nhiều annotation style trên cùng region? | Có | Test và thống nhất key generator trước khi rollout |
| Backend mới có semantics khác (TTL/null/serialize)? | Có | Viết integration test trên backend thực |

**Cách triển khai an toàn:**

1. Ghi rõ **trục annotation** và **trục provider** trong tài liệu thiết kế.
2. Định nghĩa cache names, key schema, TTL/invalidation, null policy và mức nhất quán chấp nhận được.
3. Chọn Spring annotations hoặc JSR-107 annotations theo contract mà team phải duy trì.
4. Tránh trộn style trong cùng region; nếu buộc phải trộn, chuẩn hóa key và viết test interoperability.
5. Test với backend thật: hit/miss, eviction sau update, exception, concurrency, serialization, transaction boundary.
6. Giám sát hit/miss ratio, stale read, load error, eviction rate và memory footprint sau khi deploy.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “Đã dùng `@CacheResult` thì backend bắt buộc phải là JCache” | Spring hỗ trợ annotation JSR-107 trên cache abstraction của mình | Tách annotation và storage provider |
| “Có `javax.cache:cache-api` là cache chạy được” | API jar không chứa provider implementation | Thêm JCache provider khi bootstrap bằng JCache SPI |
| “Spring 6 phải import `jakarta.cache`” | JSR-107 trong Spring 6.2 vẫn dùng `javax.cache` | Dùng đúng namespace theo artifact JCache |
| “`@CachePut` cùng tên nên có semantics giống nhau” | Spring dùng return value, JCache dùng `@CacheValue` argument | Review method signature và giá trị put |
| “Đọc Spring, xóa JCache cùng tên region chắc chắn trúng key” | Default key generation có thể khác type/equals | Dùng chiến lược key chung và test |
| “JCache provider luôn là distributed cache” | Tiêu chuẩn API không bảo đảm topology | Kiểm tra triển khai, replication/consistency |
| “Chỉ đổi annotations là migration xong” | Interceptor, dependency, key, exception policy vẫn khác | Migration plan kèm integration tests |
| “Annotation hoạt động khi gọi `this.read(id)`” | Proxy mode bỏ qua self-invocation | Gọi qua bean proxy phù hợp |
| “Lỗi service cũng nên cache lâu như kết quả” | Exception tạm thời không giống lỗi vĩnh viễn | Chọn cachedExceptions cẩn trọng và TTL phù hợp |
| “Đổi backend không cần test” | Serialization, null và expiry behavior có thể khác | Chạy contract/integration test trên provider mới |

## 12. Bài tập tự kiểm tra

**Bài 1.** Một ứng dụng Spring Boot chỉ cần cache kết quả repository, muốn `unless = "#result == null"` và key SpEL. Chọn gì?

**Đáp án:** Thường chọn **Spring Cache annotations** vì có các tính năng trực tiếp này. Chọn backend theo tải hệ thống và chính sách dữ liệu riêng.

**Bài 2.** Một library Java SE độc lập Spring cần giao diện cache chuẩn do nhiều provider cùng triển khai. Lựa chọn nào hợp lý?

**Đáp án:** Cân nhắc **JCache `javax.cache`** cùng JSR-107 provider. Vẫn phải kiểm tra tương thích thực tế, đặc biệt phần ngoài chuẩn.

**Bài 3.** Đã dùng `@CacheResult` trên một Spring service. Có nhất thiết phải thay Caffeine bằng Ehcache/JCache provider không?

**Đáp án:** Không. Với Spring JSR-107 annotation support phù hợp, annotation có thể chạy qua Spring CacheManager hiện tại.

**Bài 4.** Tại sao reader Spring `key = "#p0"` và writer JCache `@CacheKey` cùng ID vẫn có thể không invalidation trúng entry?

**Đáp án:** Key generator có thể tạo key object khác type hoặc representation. Cần test sự bằng nhau, serialization và đồng nhất strategy.

**Bài 5.** Cùng tên `@CachePut` của hai hệ sinh thái; khác biệt chính là gì?

**Đáp án:** Spring đưa **return value** vào cache; JCache lấy **parameter gắn `@CacheValue`** để ghi.

**Bài 6.** Dùng JCacheCacheManager có tự đảm bảo cache phân tán, strong consistency và TTL phù hợp không?

**Đáp án:** Không. Adapter chỉ nối Spring với JCache manager; các thuộc tính vận hành do provider và cấu hình quyết định.

**Bài 7.** Một method có cả `@Cacheable` và `@CacheResult` để “an toàn gấp đôi”. Có nên không?

**Đáp án:** Không nên mặc định làm vậy. Hai interception models có thể chồng nhau, gây lookup/put không như dự kiến; chọn một style và kiểm chứng hành vi.

## 13. Ghi nhớ và tài liệu chính thức

**Điểm nhớ nhanh:**

- **Spring Cache** là abstraction tích hợp Spring, có annotation/key SpEL và nhiều provider adapters.
- **JCache (JSR-107)** là standard Java API/annotation contract thuộc namespace **`javax.cache`**, yêu cầu provider thật nếu truy cập qua JCache SPI.
- **Annotation và backend là hai trục khác nhau.** Spring hỗ trợ JSR-107 annotations trên Spring CacheManager; Spring CacheManager cũng có adapter sang provider JCache.
- **Cùng tên annotation không đồng nghĩa cùng semantics**: đặc biệt `@CachePut`.
- **Key generation mặc định khác nhau**; muốn trộn annotation hoặc migration phải chuẩn hóa cache key trước.
- Lựa chọn API **không thay thế** kiểm tra TTL, null, serialization, transaction, concurrency và thông tin tenant.

**Tài liệu chính thức để đối chiếu:**

- [Spring Framework – JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework 6.2 – Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html)
- [Spring Framework – Configuring Cache Storage / JSR-107](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework 6.2 – JCacheCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html)
- [JSR-107 JCache API 1.1.1](https://javadoc.io/doc/javax.cache/cache-api/1.1.1/index.html)

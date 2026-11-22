# Dùng annotation Spring trên kho tuân thủ JCache (JSR-107)

## 1. Bài toán: giữ annotation Spring nhưng thay backing cache bằng JCache

Spring Framework cung cấp hai thứ có tên gần giống nhưng **không đồng nhất**:

- **Spring Cache abstraction:** các interface `org.springframework.cache.Cache`, `org.springframework.cache.CacheManager` và các annotation `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, `@CacheConfig`. Các annotation này thuộc `org.springframework.cache.annotation`.
- **JCache (JSR-107):** API chuẩn về caching của Java với `javax.cache.Cache`, `javax.cache.CacheManager`, `javax.cache.spi.CachingProvider` và bộ annotation chuẩn như `javax.cache.annotation.CacheResult`, `CachePut`, `CacheRemove`, `CacheRemoveAll`.

Đề bài **“Dùng annotation Spring trên kho tuân thủ JCache”** có nghĩa: **giữ `@Cacheable`, `@CachePut` và `@CacheEvict` của Spring trên business methods**, nhưng cấu hình Spring `CacheManager` bằng một **`JCacheCacheManager` adapter** trỏ tới một `javax.cache.CacheManager` thực sự, do provider tuân thủ JSR-107 tạo ra.

Ví dụ tên provider: **Ehcache 3** hoặc **Caffeine JCache**. Cả hai cung cấp implementation `javax.cache.*`; trong nội dung này ta chọn Caffeine JCache để ví dụ không cần Redis, file XML hay một server ngoài. JCache là **hợp đồng API**, không phải tên một cache server duy nhất.

Mục tiêu sau khi học:

1. Phân biệt rõ hai namespace Spring và `javax.cache`; biết adapter nằm ở đâu.
2. Chuẩn bị provider, `javax.cache.CacheManager` và cache name trước khi khởi tạo Spring caching infrastructure.
3. Sử dụng annotation Spring để đọc cache, cập nhật và xóa dữ liệu trên native JCache store.
4. Kiểm tra cache hit/miss, key, `unless`, null, expiry và đặc tính provider.
5. Tránh nhầm lẫn annotation Spring với annotation JCache; hiểu giới hạn interoperability của chúng.
6. Chạy ví dụ Java 17+, Maven và Spring context; biết cách kiểm thử backend thật.

## 2. Sơ đồ kiến trúc: hai lớp CacheManager

~~~mermaid
flowchart TD
    Caller[Caller gọi Spring-managed bean qua proxy] --> Interceptor[Spring CacheInterceptor]
    Interceptor --> Operation[Phân tích @Cacheable / @CachePut / @CacheEvict]
    Operation --> SpringManager[Spring CacheManager: JCacheCacheManager]
    SpringManager --> Adapter[Spring JCacheCache adapter]
    Adapter --> JManager[javax.cache.CacheManager]
    JManager --> JCache[javax.cache.Cache theo cache name]
    JCache --> Provider[JCache CachingProvider]
    Provider --> Store[Native store: Caffeine / Ehcache / vendor khác]
~~~

Đường đi chính:

- Annotation Spring phát sinh một **cache operation** dựa trên method, tham số, SpEL và kết quả.
- `CacheInterceptor` gọi Spring `CacheManager` để lấy một Spring `Cache` theo `cacheNames`.
- `org.springframework.cache.jcache.JCacheCacheManager` trả về Spring `JCacheCache` adapter cho cache JSR-107 tương ứng.
- Adapter gọi `javax.cache.Cache<K,V>` dưới quyền quản lý của JCache provider.
- Provider chịu trách nhiệm storage, eviction theo size/expiry, key/value type, store-by-value và các đặc tính vendor.

**Hai interface `CacheManager` khác package dù cùng tên.** Đừng import nhầm hoặc đăng ký `javax.cache.CacheManager` rồi cho rằng `@EnableCaching` tự động biến nó thành Spring `CacheManager` trong ứng dụng tự cấu hình. Nếu không dùng auto-configuration đặc biệt, cần khai báo **một bean Spring `CacheManager`** (chẳng hạn `JCacheCacheManager`) như ví dụ phía dưới.

### Nhìn bằng kiểu Java

~~~java
javax.cache.CacheManager nativeJCacheManager = provider.getCacheManager();

org.springframework.cache.CacheManager springCacheManager =
        new org.springframework.cache.jcache.JCacheCacheManager(
                nativeJCacheManager);
~~~

Snippet này cần biến `provider` có kiểu `javax.cache.spi.CachingProvider`. Không cast hai manager cho nhau; chúng là hai contract khác nhau, được **nối bằng adapter**.

## 3. Dependency, tên package và phiên bản

Để dùng Spring annotations trên kho JCache, thường cần:

| Thành phần | Vai trò |
| --- | --- |
| `spring-context` | Caching abstraction, annotation và infrastructure chính của Spring |
| `spring-context-support` | `JCacheCacheManager`, `JCacheCache` và hỗ trợ tích hợp provider |
| `javax.cache:cache-api` | Interface JSR-107, `javax.cache.CacheManager` và `CachingProvider` |
| JCache implementation, ví dụ `com.github.ben-manes.caffeine:jcache` | Provider thật cung cấp storage và implementation JCache |
| Spring-managed bean với `@EnableCaching` | Kích hoạt cache interception cho Spring annotations |

Dùng `spring-context` và `spring-context-support` **cùng dòng phiên bản**; với Spring Boot nên để BOM/Dependency Management quyết định phiên bản Spring thay vì trộn thủ công.

**Lưu ý namespace:** JCache 1.1 (JSR-107) sử dụng `javax.cache.*` ngay cả khi dự án sử dụng các thư viện Jakarta EE như `jakarta.persistence.*` hoặc `jakarta.servlet.*`. Đừng tự đổi import sang `jakarta.cache` nếu provider và API bạn đang dùng là `javax.cache:cache-api:1.1.1`.

Chỉ thêm `javax.cache:cache-api` **không đủ** để có cache chạy: phải có một **CachingProvider** khả dụng và đúng cấu hình. Ngược lại, chỉ thêm native Caffeine cache `com.github.ben-manes.caffeine:caffeine` cũng không tự tạo JCache provider; để demo JSR-107 cần artifact `jcache`.

JCache chọn provider qua `ServiceLoader`. Khi classpath có **nhiều provider**, `Caching.getCachingProvider()` không có tham số có thể trở nên không rõ ràng. Nên chọn provider bằng tên implementation khi muốn ví dụ/test có kết quả ổn định:

~~~java
CachingProvider provider = Caching.getCachingProvider(
    "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
~~~

Đây là snippet cho **Caffeine JCache**. Với Ehcache 3, class provider là `org.ehcache.jsr107.EhcacheCachingProvider`. Đừng gán class provider của hãng A cho artifact của hãng B.

## 4. Khởi tạo native JCache trước khi Spring cache annotations chạy

Quy trình cấu hình thủ công chuẩn:

1. Chọn `CachingProvider`.
2. Lấy `javax.cache.CacheManager` qua provider.
3. Tạo các cache JSR-107 bằng `createCache(cacheName, MutableConfiguration)` hoặc cấu hình vendor (XML, programmatic).
4. Bọc native manager bằng `org.springframework.cache.jcache.JCacheCacheManager`.
5. Đăng ký Spring manager như bean `cacheManager` hoặc cung cấp `CachingConfigurer` nếu có nhiều Spring managers.
6. Bật `@EnableCaching` và gọi business bean qua Spring proxy.

Ví dụ cấu hình rút gọn:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfiguration {

    @Bean(destroyMethod = "close")
    javax.cache.CacheManager jCacheManager() {
        CachingProvider provider = Caching.getCachingProvider(
            "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
        javax.cache.CacheManager manager = provider.getCacheManager();

        if (manager.getCache("books") == null) {
            MutableConfiguration<String, String> config =
                new MutableConfiguration<String, String>()
                    .setTypes(String.class, String.class)
                    .setStoreByValue(false);
            manager.createCache("books", config);
        }

        return manager;
    }

    @Bean
    org.springframework.cache.CacheManager cacheManager(
            javax.cache.CacheManager jCacheManager) {
        JCacheCacheManager adapter = new JCacheCacheManager(jCacheManager);
        adapter.setAllowNullValues(false);
        return adapter;
    }
}
~~~

Đây là **snippet cấu hình**: phải có import Spring/JCache hợp lệ, Java class thích hợp và dependency từ mục 3. `destroyMethod="close"` giúp Spring gọi `close()` trên JCache manager khi context ngừng; quản lý vòng đời provider cần dựa vào application topology. Ví dụ hoàn chỉnh ở mục 6 có đủ imports.

Các điểm cần biết:

- `getCache("books") == null` trước khi gọi `createCache`: chưa có cache đúng tên.
- `setTypes(String.class,String.class)` chọn kiểu key/value native; nếu Spring key expression trả `SimpleKey` hoặc `Long` thay vì String, provider có thể ném `ClassCastException` hay `CacheException` lúc truy cập.
- `setStoreByValue(false)` chọn **reference semantics** cho ví dụ local. Đối với production, cấu hình store-by-value, serializer, mutability, expiry và topology phải được xét theo provider, không tự copy setting này.
- Không viết bean chỉ trả `javax.cache.CacheManager` rồi bỏ qua bean Spring `CacheManager` trừ khi framework auto-config thực sự đã tạo adapter tương ứng.
- `@EnableCaching` chỉ kích hoạt advice; nếu không có bean Spring `CacheManager` phù hợp hoặc cache name không tồn tại, runtime sẽ báo lỗi thay vì tự tạo mọi native cache theo ý mình.
- Với ứng dụng nhiều provider, hãy đặt rõ provider class/cache URI/classloader để tránh các cache “trùng tên” nhưng thuộc manager khác nhau.

## 5. Giữ nguyên annotation Spring: logic nghiệp vụ không phụ thuộc vendor

Một service đã dùng:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public String findTitle(String isbn) {
    return repository.findTitle(isbn);
}

@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

Đây là snippet: cần repository và Spring-managed bean. Không có import `javax.cache.annotation.*` trong method. Annotation giữ nguyên của Spring; **chỉ cấu hình CacheManager thay đổi**.

Quy trình:

- Lần đầu gọi `findTitle("ISBN-A")` qua proxy: Spring tìm cache `books`, tạo key qua SpEL `#p0`, JCache adapter đọc native cache. Nếu miss, chạy method, rồi Spring put kết quả vào JCache.
- Lần hai cùng key: hit, Spring lấy value từ JCache adapter và trả ngay; repository không bị gọi.
- `rename("ISBN-A", "...")` return bình thường: Spring `@CacheEvict` yêu cầu xóa entry key `"ISBN-A"` trong cache `books`.
- Lần đọc sau: miss, method đọc nguồn để lấy title mới.
- Nếu method trả null, `unless="#result == null"` bỏ ghi kết quả null. Trong JCache, null support có điều kiện nên chính sách này rõ ràng, dễ kiểm thử hơn việc giả định default provider.

**Không cần đổi `@Cacheable` thành `@CacheResult` chỉ vì storage dùng JCache.** Đây chính là lợi ích lớn nhất của Spring caching abstraction: doanh nghiệp có thể đổi implementation phía sau mà giữ phần lớn annotation của service.

## 6. Ví dụ hoàn chỉnh: Spring @Cacheable/@CachePut/@CacheEvict trên Caffeine JCache

Chương trình sử dụng **JDK 17+**, Maven, Spring Framework **6.2.19**, API `javax.cache` 1.1.1 và **Caffeine JCache 3.2.4**. Đây là một JCache provider local trong JVM; không cần Redis, server hay XML.

Ba annotation Spring được sử dụng:

- `@Cacheable`: đọc từ cache khi có, nếu miss mới chạy `findTitle`.
- `@CachePut`: luôn chạy method, rồi ghi kết quả mới vào entry.
- `@CacheEvict`: sau khi method cập nhật dữ liệu nguồn thành công, xóa entry cũ.

### 6.1. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotations-jcache-provider</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>jcache</artifactId>
            <version>3.2.4</version>
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

Đây là **đầy đủ dependency trực tiếp** của ví dụ. `spring-context-support` là nơi có `JCacheCacheManager`. Không sử dụng `CaffeineCacheManager` trong ví dụ: class đó là adapter native Caffeine riêng của Spring, không phải `JCacheCacheManager` của JSR-107.

### 6.2. Tệp src/main/java/demo/SpringJCacheDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.spi.CachingProvider;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringJCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean(destroyMethod = "close")
        public javax.cache.CacheManager jCacheManager() {
            CachingProvider provider = Caching.getCachingProvider(
                "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
            javax.cache.CacheManager manager = provider.getCacheManager();

            if (manager.getCache("books") == null) {
                MutableConfiguration<String, String> config =
                    new MutableConfiguration<String, String>()
                        .setTypes(String.class, String.class)
                        .setStoreByValue(false);
                manager.createCache("books", config);
            }
            return manager;
        }

        @Bean
        public org.springframework.cache.CacheManager cacheManager(
                javax.cache.CacheManager jCacheManager) {
            JCacheCacheManager adapter = new JCacheCacheManager(jCacheManager);
            adapter.setAllowNullValues(false);
            return adapter;
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private final Map<String, String> database =
                new ConcurrentHashMap<>(Map.of("ISBN-A", "Ban cu"));
        private int sourceReads = 0;

        @Cacheable(cacheNames = "books", key = "#p0",
                   unless = "#result == null")
        public String findTitle(String isbn) {
            System.out.println("DB read #" + (++sourceReads));
            return database.get(isbn);
        }

        @CacheEvict(cacheNames = "books", key = "#p0")
        public void renameAndInvalidate(String isbn, String title) {
            database.put(isbn, title);
        }

        @CachePut(cacheNames = "books", key = "#p0")
        public String replaceAndRefresh(String isbn, String title) {
            database.put(isbn, title);
            return title;
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            BookService service = context.getBean(BookService.class);
            javax.cache.CacheManager nativeManager =
                    context.getBean(javax.cache.CacheManager.class);
            javax.cache.Cache<String, String> nativeBooks =
                    nativeManager.getCache(
                        "books", String.class, String.class);

            System.out.println("first=" + service.findTitle("ISBN-A"));
            System.out.println("second=" + service.findTitle("ISBN-A"));
            System.out.println("native hit="
                    + nativeBooks.containsKey("ISBN-A"));

            service.renameAndInvalidate("ISBN-A", "Ban moi");
            System.out.println("native after evict="
                    + nativeBooks.containsKey("ISBN-A"));
            System.out.println("after evict="
                    + service.findTitle("ISBN-A"));

            service.replaceAndRefresh("ISBN-A", "Ban cap nhat");
            System.out.println("native after put="
                    + nativeBooks.get("ISBN-A"));
            System.out.println("after put="
                    + service.findTitle("ISBN-A"));

            System.out.println("missing1="
                    + service.findTitle("NONE"));
            System.out.println("missing2="
                    + service.findTitle("NONE"));
            System.out.println("native missing="
                    + nativeBooks.containsKey("NONE"));
        }
    }
}
~~~

**Các yếu tố bảo đảm mẫu đúng phạm vi:**

- Cả ba annotation đều import `org.springframework.cache.annotation.*`, **không** import `javax.cache.annotation.*`.
- Hai manager tồn tại đồng thời nhưng khác interface; bean Spring `cacheManager` làm adapter.
- Native cache `books` được **tạo trước** và có key/value String tương thích `key="#p0"`.
- `BookService` là Spring bean, các method public/non-final, caller gọi qua object lấy từ context nên caching advice chặn được.
- `unless="#result == null"` tránh put-null vào cache được cấu hình `allowNullValues(false)`.
- Hai lần đọc đầu và sau `@CachePut` chứng minh hit; `@CacheEvict` làm mất mapping và lần đọc sau phải tải lại nguồn.
- Native `javax.cache.Cache<String,String>` được đọc **chỉ để quan sát** cùng underlying store, không dùng trực tiếp làm repository.

### 6.3. Lệnh chạy

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringJCacheDemo
~~~

### 6.4. Output dự kiến

Các dòng do chương trình in, không tính log của Maven/provider:

~~~text
DB read #1
first=Ban cu
second=Ban cu
native hit=true
native after evict=false
DB read #2
after evict=Ban moi
native after put=Ban cap nhat
after put=Ban cap nhat
DB read #3
missing1=null
DB read #4
missing2=null
native missing=false
~~~

Giải thích theo thứ tự:

1. Lần đầu `findTitle("ISBN-A")` miss nên có `DB read #1`, trả `Ban cu` và Spring lưu qua `JCacheCacheManager`.
2. Lần hai hit và không in thêm `DB read`.
3. `nativeBooks.containsKey("ISBN-A")` trả true: dữ liệu thực sự nằm trong **javax.cache store** đã cấu hình, không phải một map cache riêng do Spring tự tạo.
4. `renameAndInvalidate` chạy cập nhật nguồn và `@CacheEvict` xóa key; `containsKey` thành false.
5. Lần tìm sau eviction miss và in `DB read #2`, lấy `Ban moi` rồi cache.
6. `replaceAndRefresh` chạy method dù cache có sẵn; `@CachePut` ghi `Ban cap nhat` vào native entry. Lần `findTitle` sau đó hit, không in thêm `DB read`.
7. `findTitle("NONE")` trả null; `unless` chặn ghi. Vì vậy cả hai lần đều chạy nguồn (`#3` và `#4`); native cache không có key `NONE`.

**Độ tin cậy:** ví dụ không phụ thuộc một database ngoài; kết quả được suy luận từ contract Spring và code, nhưng source **không được biên dịch/chạy thật trong bản Knowledge này**. Khi học, chạy lệnh trong môi trường Maven/JDK 17 với đúng dependency đã khai báo để xác nhận provider version và runtime. Nếu một provider khác thay đổi hành vi, cần kiểm chứng lại.

## 7. Đọc API Spring Cache và JCache native cùng lúc

Hai con đường hợp lệ khi cần kiểm tra:

~~~java
// Spring abstraction, dùng với annotation và mọi Spring CacheManager.
org.springframework.cache.Cache springBooks =
    springManager.getCache("books");
org.springframework.cache.Cache.ValueWrapper wrapped =
    springBooks.get("ISBN-A");

// Native JSR-107, chỉ khi provider là JCache.
javax.cache.Cache<String, String> nativeBooks =
    jCacheManager.getCache("books", String.class, String.class);
String value = nativeBooks.get("ISBN-A");
~~~

Đây là snippet cần biến `springManager` và `jCacheManager` đã có. Cùng tên cache `books` trong đúng manager trỏ tới cùng underlying store.

Chú ý khác biệt contract:

| Vấn đề | Spring Cache API | Native JCache API |
| --- | --- | --- |
| Manager | `org.springframework.cache.CacheManager` | `javax.cache.CacheManager` |
| Cache | `org.springframework.cache.Cache` | `javax.cache.Cache<K,V>` |
| Đọc key | `get(key)` trả `Cache.ValueWrapper` hoặc null | `get(key)` trả V hoặc null |
| Kiểm tra key tồn tại | Phân biệt wrapper null / wrapper chứa null | `containsKey(key)` |
| Ghi | `put(key,value)` | `put(K,V)` |
| Eviction theo key | `evict(key)` | `remove(key)` |
| Xóa toàn cache | `clear()` | `removeAll()` (hoặc provider API phù hợp) |
| Key typed | Spring nhận Object, provider quyết định | Native cache có khai báo kiểu K/V, có thể kiểm tra runtime |
| Lifetime | Tùy Spring cache manager và cache instance | Tùy native manager, `Configuration` và provider |

JCache `get(key) == null` không luôn chứng minh không có mapping nếu một adapter lưu null marker theo cơ chế Spring, nhưng ở JCache API gốc việc lưu Java null không được hỗ trợ. Sử dụng `containsKey` để phân biệt trạng thái tồn tại khi thực sự cần. Tránh phụ thuộc native marker/serializer của Spring trong business logic.

**Không trộn hai bộ manager như hai kho cache độc lập.** Nếu Spring manager A bọc JCache manager X nhưng code truy vấn native manager Y, kết quả sẽ không phản ánh cùng cache dù cache name giống nhau. Cần kiểm tra provider, URI, classloader và lifecycle, nhất là khi có nhiều JCache providers trên classpath.

## 8. Annotation Spring và annotation chuẩn JCache: hai câu hỏi khác nhau

Bài này dùng **Spring annotations** với **JCache storage**. Đừng nhầm với lựa chọn **JSR-107 annotations trên Spring infrastructure**; Spring cũng hỗ trợ hướng ngược lại nếu có API JCache và `spring-context-support`.

| Ý định | Annotation | Hạ tầng điều phối | Kho dữ liệu |
| --- | --- | --- | --- |
| Giữ API Spring, đổi provider sang JCache | `@Cacheable` / `@CachePut` / `@CacheEvict` | Spring caching infrastructure | `JCacheCacheManager` bọc provider JSR-107 |
| Dùng annotation chuẩn JCache | `@CacheResult` / `@CachePut` / `@CacheRemove` / `@CacheRemoveAll` | Spring hỗ trợ JCache annotation semantics nếu dependency phù hợp | **Có thể là** provider JCache hoặc một Spring CacheManager khác |
| Dùng JCache native thủ công | Không cần annotation | Java code tự gọi `javax.cache.Cache` | Provider JCache |
| Dùng Caffeine native qua Spring | Spring annotations | `CaffeineCacheManager` | Native Caffeine, **không cần JCache adapter** |

Các annotation không có mapping 1-1 hoàn toàn:

- Spring `@Cacheable` và JCache `@CacheResult` tương tự, nhưng JCache `@CacheResult` có lựa chọn lưu **exception cache** và `skipGet`.
- Spring `@CachePut` cập nhật cache bằng **return value**. JCache `javax.cache.annotation.CachePut` thường sử dụng argument đánh dấu `@CacheValue`; cùng tên annotation nhưng khác ngữ nghĩa.
- Spring `@CacheEvict` tương ứng gần nhất với `@CacheRemove`; JCache có quy tắc riêng để xử lý exception.
- Spring `@CacheEvict(allEntries=true)` tương ứng gần nhất với JCache `@CacheRemoveAll`.
- `@CacheConfig` (Spring) và `@CacheDefaults` (JSR-107) cùng phục vụ cấu hình mặc định theo các contract khác nhau.

Khi chuyển annotation giữa hai chuẩn, **không chỉ sửa import và giữ nguyên arguments**. Phải xem lại key generation, điều kiện, exception semantics, return/argument value và các cache name.

## 9. Key generation: nguồn lỗi phổ biến khi dùng chung một JCache store

Dù có cùng provider, hai operation vẫn có thể **không trỏ cùng entry** nếu key được tạo khác nhau.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String load(String isbn, boolean includeOutOfPrint) { ... }

@CacheEvict(cacheNames = "books", key = "#p0")
public void invalidate(String isbn) { ... }
~~~

Đây là snippet không độc lập. Theo SpEL, cả hai dùng key là String `isbn`. Điều này phù hợp nếu mọi biến thể `includeOutOfPrint` thật sự không làm thay đổi kết quả, **nhưng sai** nếu boolean làm thay đổi value: hai lời gọi business khác nhau đè chung key và có thể trả sai.

**Một điểm dễ nhầm khác:** nếu bỏ `key` trong Spring, `SimpleKeyGenerator` mặc định dùng toàn bộ method arguments theo quy tắc riêng; không luôn là String. Với JCache cache đã khai báo `setTypes(String.class, String.class)`, một `SimpleKey` hoặc argument kiểu không phù hợp có thể bị native provider từ chối.

Trong khi đó, với annotation JCache `@CacheResult`, JCache key generator tuân theo JSR-107; mặc định dùng các tham số không bị loại hoặc những tham số được đánh dấu `@CacheKey`. Hai key generator **không được mặc định coi là tương đương**. Nếu các method dùng hai bộ annotation cùng tác động cache `books`, phải thiết kế cách tạo key nhất quán, hoặc tách cache names.

Các khuyến nghị:

1. Dùng SpEL `key = "#p0"` khi khóa nghiệp vụ thật sự chỉ là tham số đầu.
2. Khi key tổng hợp, dùng kiểu immutable, `equals/hashCode` ổn định và tương thích provider (store-by-value có thể serialize key).
3. Thống nhất các method `@Cacheable`, `@CachePut`, `@CacheEvict` về cùng cache name/key schema.
4. Nếu có tenant/locale/security scope hoặc query filter làm thay đổi output, đưa vào key hoặc không cache tại phạm vi chung.
5. Kiểm thử trực tiếp native `javax.cache.Cache<K,V>` có nhận kiểu key/value mà Spring interceptor tạo ra hay không.
6. Không giả định kiểu khóa Java giống nhau ở mọi vendor; một provider có thể áp dụng serialization/typing/expiry khác.

## 10. Cấu hình JCache provider: expiry, size, type và store-by-value

`MutableConfiguration<K,V>` của `javax.cache` cho phép cấu hình tối thiểu như kiểu key/value, store-by-value, statistics, management, expiry policy và listener. Ví dụ đổi expiry:

~~~java
MutableConfiguration<String, String> config =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setStoreByValue(false)
        .setExpiryPolicyFactory(
            CreatedExpiryPolicy.factoryOf(
                new Duration(TimeUnit.MINUTES, 5)));
~~~

Đây là snippet yêu cầu import `javax.cache.expiry.CreatedExpiryPolicy`, `javax.cache.expiry.Duration` và `java.util.concurrent.TimeUnit`. Thời hạn 5 phút chỉ là ví dụ; không coi là chính sách mặc định cho mọi dữ liệu.

**Đừng gán TTL cho `@Cacheable` của Spring nếu annotation không có thuộc tính đó.** Expiry/maximum size thuộc cấu hình cache provider. Để cấu hình dung lượng, off-heap/disk, persistence, cluster replication hoặc eviction policy, phải dùng tính năng native của provider hoặc file cấu hình hỗ trợ; JCache specification chỉ chuẩn hóa một tập cơ bản.

Đặc biệt:

- **Store-by-value:** provider có thể copy giá trị khi put/get thay vì giữ cùng object reference. Một DTO cần tuân theo serialization/copying mechanism thực tế của vendor. Ví dụ String bất biến là an toàn cho phần lớn case.
- **Store-by-reference:** caller có thể thấy mutation trên object có thể thay đổi; cache correctness khó đảm bảo. Tránh trả mutable object có thể bị chỉnh trực tiếp bởi consumer.
- **Type safety:** nếu định nghĩa cache `<String, String>`, đừng đưa `Long` hoặc `SimpleKey` làm key; sẽ gây lỗi hoặc lookup sai.
- **Expiry:** lần thứ hai ngoài TTL có thể là miss dù annotation/proxy đúng; muốn test hit ổn định hãy giữ thời gian ngắn và TTL đủ dài hoặc dùng cấu hình không expiry cho demo.
- **Concurrency và eviction:** tùy provider, method có thể throw provider-specific `CacheException` hoặc có semantics về write-through/loader riêng.

## 11. Null, Optional.empty và cache exceptions

JCache chuẩn **không hỗ trợ null key hoặc null value** theo cách một Map có thể cho phép. Spring `JCacheCacheManager` lại có khả năng **thích nghi null** thông qua holder nội bộ khi `allowNullValues=true` (default của manager Spring trong các phiên bản được tài liệu hóa). Nghĩa là **Spring may wrap null** thành marker thay vì đưa raw Java null vào native JCache store.

Nhưng **không tự giả định mọi provider chấp nhận serialize marker** như nhau, nhất là cache có store-by-value, serializer giới hạn kiểu value hoặc persistence. Nếu không muốn cache null, nên rõ ràng:

~~~java
@Cacheable(cacheNames = "books",
           key = "#p0",
           unless = "#result == null")
public Book find(String isbn) {
    return repository.findOrNull(isbn);
}
~~~

Snippet này cần `Book` và repository thực tế.

- `unless` được Spring đánh giá khi đã có result, giúp **không put** null.
- `JCacheCacheManager#setAllowNullValues(false)` nghĩa là **từ chối** put null ở adapter; nó không tự biến mọi put-null thành skip mà không báo lỗi.
- Nếu method trả `Optional<Book>`, `#result` trong `unless` của Spring là `Book` bên trong hoặc `null` khi `Optional.empty()`; không gọi `#result.isEmpty()` như trên kiểu Optional.
- Bắt exception rồi trả null sẽ làm Spring tưởng đây là một business miss; nếu bỏ `unless` có thể negative-cache lỗi mạng/backend. Hãy phân biệt NotFound với Timeout/ServiceUnavailable.

### Còn exception caching?

JSR-107 annotation `@CacheResult` có tính năng **cache một số exception** theo contract của nó. Spring `@Cacheable` **không tự động** có cùng semantics chỉ vì backing store là JCache. Storage provider chỉ là tầng lưu trữ, không “mang theo” thuộc tính của annotation JCache vào Spring annotation. Nếu cần caching exception, hãy thiết kế chính sách lỗi/tính bất biến và infrastructure riêng, hoặc cân nhắc JCache annotations theo đúng spec.

## 12. Cập nhật, eviction và consistency khi backend là JCache

`@CacheEvict(cacheNames="books", key="#p0")` dùng Spring Cache API `evict` sau khi method hoàn tất bình thường (mặc định `beforeInvocation=false`), rồi adapter gọi removal tương ứng trên JCache. **Không** có nghĩa database và cache là một transaction nguyên tử.

Một race có thể xảy ra:

~~~text
T1  Transaction cập nhật DB nhưng chưa commit
T2  Cache entry bị evict
T3  Một reader khác cache miss; DB vẫn trả value cũ
T4  Reader đưa value cũ vào JCache
T5  DB commit value mới
T6  Reader tiếp theo vẫn có thể hit value cũ
~~~

Đây là tình huống minh họa, phụ thuộc AOP advice order, transaction propagation, provider consistency và network. Để hạn chế, có thể chọn **invalidation sau commit** thông qua Spring transaction-aware cache decorator/manager hoặc transactional event. Nhưng phải test với JCache adapter, transaction manager, callback và cache vendor thật; không suy từ `@Transactional` rằng cache tự động evict sau commit.

**Nếu update thất bại:** với `beforeInvocation=false`, exception thoát khỏi method khiến eviction của annotation không chạy. Nếu dữ liệu nguồn đã được thay đổi ngoài transaction trước khi ném exception, entry có thể stale. Cần ranh giới commit đúng, outbox hoặc cơ chế invalidation đáng tin cậy.

**Nếu provider lỗi:** native JCache có thể ném `javax.cache.CacheException`, và Spring caching advice có thể truyền lỗi đến caller theo `CacheErrorHandler` mặc định. Cần logging/metric và chính sách degrade phù hợp; bỏ qua lỗi eviction có thể để lại dữ liệu stale.

## 13. Proxy boundary vẫn áp dụng dù storage theo JSR-107

Thay store không thay cơ chế kích hoạt Spring annotation:

~~~java
@Service
public class BookFacade {
    public String readTwice(String isbn) {
        return findCached(isbn); // gọi nội bộ trong cùng instance
    }

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findCached(String isbn) {
        return repository.find(isbn);
    }
}
~~~

Đây là snippet, chưa có repository/import đầy đủ. Trong proxy mode mặc định, lời gọi `this.findCached(...)` bên trong target **bypass Spring caching proxy** nên annotation có thể không chạy. JCache provider hoàn toàn không biết annotation trên method Java được gọi nội bộ; nó chỉ thực hiện thao tác khi adapter gửi request.

Nên:

- Đặt method cached trong bean riêng và gọi qua Spring-managed reference, hoặc gọi public cached method trực tiếp từ caller ngoài proxy.
- Không tạo service bằng `new` khi cần AOP.
- Đặt annotation trên implementation method public, tránh private/final bị loại khỏi class-based proxy.
- Kiểm tra `@EnableCaching`, loại proxy, \`AopUtils.isAopProxy(bean)\`, `cacheNames`, key và đúng Spring manager.
- Đừng coi provider storage chuyển sang JCache là “tự sửa lỗi proxy”.

## 14. Spring Boot: tự cấu hình khác với cấu hình thuần Spring

Với Spring Boot có caching starter và JCache provider trên classpath, Boot có thể **tự phát hiện JCache** và tạo Spring `CacheManager` tương ứng tùy phiên bản, properties và các bean ứng dụng đã khai báo. Với cấu hình thuần Spring trong mục 6, chúng ta **tự tạo hai manager** để toàn bộ pipeline minh bạch.

Không trộn cấu hình thủ công với auto-configuration một cách vô thức: nếu có nhiều Spring `CacheManager`, Spring không tự biết manager nào dành cho method của bạn. Hãy sử dụng bean được chọn rõ ràng, `CachingConfigurer`, tên cache manager hoặc `@Cacheable(cacheManager="...")` khi thực sự cần nhiều vùng.

Một số property Boot liên quan JCache, như `spring.cache.jcache.config` hoặc `spring.cache.type=jcache`, phụ thuộc Boot version và provider được hỗ trợ. Phải đọc tài liệu phiên bản đang chạy; một cấu hình Boot được đưa vào project Spring thuần sẽ không tự tạo cache.

**Boot provider preference không thay đổi bài học cốt lõi:** business methods vẫn dùng `@Cacheable` của Spring; Spring `CacheManager` adapter được kết nối tới `javax.cache.CacheManager` của vendor.

## 15. Chuyển provider từ ConcurrentMap/Ehcache sang JCache: kế hoạch an toàn

Khi chuyển một service từ `ConcurrentMapCacheManager` của Spring sang `JCacheCacheManager`, hoặc đổi JCache provider từ Ehcache sang Caffeine:

1. **Liệt kê cache names và key contract** của tất cả method `@Cacheable`, `@CachePut`, `@CacheEvict`. Đừng chỉ chuyển tên dependency.
2. **Chọn JCache provider** và loại bỏ provider không dùng trên classpath để tránh discovery không rõ ràng.
3. **Tạo/cache config**: khởi tạo vùng cache đúng name, đúng key/value types, expiry, capacity, store-by-reference/value và serialization.
4. **Cấu hình adapter**: kiểm tra bean Spring `CacheManager` và JCache native manager cùng trỏ đúng store.
5. **Kiểm thử null/Optional**: default `allowNullValues` hoặc custom serializer có thể khác provider trước.
6. **Kiểm thử hit/evict/put**: cùng key phải dùng chung entry, và nhận giá trị đúng sau mutation.
7. **Đánh giá concurrency**: cache loader, expiry, stale refresh, transaction commit và provider exception handling.
8. **Theo dõi metrics**: native JCache statistics/management có thể cần bật; đừng nhầm Spring cache hit rate với DB query rate.
9. **Rollout**: chú ý cold cache, cache stampede, classloader/URI và việc cache cùng tên ở nhiều node có thể là local, không phải shared distributed store.
10. **Rollback plan**: nếu provider mới không đáp ứng latency/correctness/serialization, phải có cách quay về manager cũ mà không dùng nhầm dữ liệu cache incompatible.

Đừng chỉ test `context.getBean("cacheManager") instanceof JCacheCacheManager` rồi coi migration thành công. Kiểm tra **các lần gọi method thực tế**, native cache mapping, key/value typing và đường cập nhật/xóa.

## 16. Các lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có cache nào được tìm thấy | Chưa `createCache("books", ...)` trong native manager | Tạo cache trước, hoặc cấu hình provider đúng cache name |
| `@Cacheable` không có hiệu lực | Quên `@EnableCaching`, bean không qua proxy, self-invocation | Bật infrastructure và gọi Spring bean qua proxy |
| Class `JCacheCacheManager` không resolve | Thiếu `spring-context-support` | Thêm module Spring cùng version |
| `javax.cache.Caching` không tồn tại | Thiếu `javax.cache:cache-api` | Thêm API JSR-107 1.1.x |
| Không tìm được provider | Chỉ có API, chưa có provider jar; sai provider class | Thêm đúng artifact JCache provider |
| Có nhiều CachingProvider | ServiceLoader discovery mơ hồ | Chọn provider rõ FQCN, rà soát dependency tree |
| Native cache không có dữ liệu dù Spring báo hit | Đang truy vấn một javax.cache.CacheManager khác | Kiểm tra provider/URI/classloader và Spring adapter |
| Key type mismatch | Spring tạo `SimpleKey`/`Long`, native cache yêu cầu `String` | Thống nhất SpEL key hoặc cấu hình key type đúng |
| Cache miss liên tục | TTL quá ngắn, key thay đổi, `condition=false`/`unless=true` | Kiểm tra annotation, key, expiry và source-read counter |
| Cache trả dữ liệu cũ sau update | Thiếu `@CacheEvict`, sai cache name/key, transaction race | Kiểm tra eviction path và after-commit semantics |
| Exception khi put null | JCache không nhận raw null; adapter disallow null/serialization | Dùng `unless` hoặc cấu hình adaptation có test |
| Đổi annotation sang JCache nhưng behavior khác | `@CachePut`/`@CacheResult` không tương đương 1-1 | Xem lại result/argument, key và exception semantics |
| Hit local nhưng node khác miss | Provider chỉ là local cache, không có shared cluster | Chọn topology đúng, không giả định JCache đồng nghĩa distributed |
| Lỗi khi tắt ứng dụng | Native cache manager/provider lifecycle không được quản lý | Rà soát `close()`/destroy method và owner của provider |

## 17. Checklist kiểm thử trước production

Một bộ integration test có giá trị nên bao gồm:

- [ ] Test Spring `@Cacheable` gọi hai lần cùng key: repository chỉ chạy một lần khi cache hit.
- [ ] Test `@CachePut` ghi result mới: gọi lại `@Cacheable` nhận giá trị mới không đọc nguồn.
- [ ] Test `@CacheEvict`: method cập nhật return thành công thì native `containsKey` false; lần đọc sau tải lại.
- [ ] Test exception khi update: sau-invocation eviction không chạy, và transaction rollback đúng ranh giới.
- [ ] Test missing value: `unless="#result == null"` không ghi null; provider disallow null không làm hỏng lời gọi.
- [ ] Test đúng key type/value type ở native JCache, đặc biệt khi dùng key mặc định nhiều argument.
- [ ] Test cùng key/tenant/locale/permission scope, không trả nhầm dữ liệu qua người dùng khác.
- [ ] Test expiry, eviction theo size, store-by-value và serializer theo vendor.
- [ ] Test khi provider không khả dụng hoặc ném `CacheException`: logging, fallback, error handler.
- [ ] Test self-invocation và proxy type; annotation không chạy khi bypass Spring AOP.
- [ ] Test migration có nhiều provider trên classpath, URI/classloader và cache names trùng.
- [ ] Test concurrency và cache consistency với topology (local/distributed) thực tế.
- [ ] Test lifecycle cleanup: đóng `javax.cache.CacheManager` và tài nguyên provider an toàn.

**Chốt QA:** nếu native cache được khởi tạo, Spring adapter hoạt động, có cache hit thực sự, cập nhật/evict đúng key và chính sách lỗi/expiry được test, thì annotation Spring có thể dùng hiệu quả trên store JCache mà không cần viết lại business service thành annotation JSR-107.

## 18. Tài liệu tham khảo

- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html): cấu hình `JCacheCacheManager` từ `javax.cache.CacheManager`; Ehcache 3 dùng JSR-107.
- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html): phân biệt hai bộ annotation, key/exception semantics và cách Spring hỗ trợ JCache annotation.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, SpEL key, proxy và `unless`.
- [Spring JCacheCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html): manager adapter và chính sách `allowNullValues`.
- [Spring JCacheCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCache.html): wrapper giữa Spring `Cache` và native JCache.
- [Ehcache 3 — JSR-107 Provider](https://www.ehcache.org/documentation/3.9/107.html): API `CachingProvider`/`CacheManager` và cấu hình provider.
- [Caffeine — JCache Provider](https://www.javadoc.io/doc/com.github.ben-manes.caffeine/jcache/3.2.4/index.html): provider tuân thủ JSR-107 cho Caffeine, class `CaffeineCachingProvider`.
- [Maven Central — Caffeine JCache](https://central.sonatype.com/artifact/com.github.ben-manes.caffeine/jcache/3.2.4): tọa độ dependency và transitive JCache API.

**Điểm cần ghi nhớ:** **Spring annotations + JCache store** = dùng `@Cacheable`/`@CachePut`/`@CacheEvict` của Spring, đăng ký `org.springframework.cache.jcache.JCacheCacheManager` bọc `javax.cache.CacheManager` của provider. Đây là hai lớp API có thể kết hợp mà không thay đổi annotation business; phần phải kiểm tra kỹ là **cache name, key/type, provider setup, null/expiry, lifecycle và proxy boundary**.
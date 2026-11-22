# JSR-107, nhà cung cấp và JCacheCacheManager trong Spring Framework

## 1. JCache là gì?

**JCache**, tên chuẩn **JSR-107**, là đặc tả Java định nghĩa một API cache thống nhất và một Service Provider Interface (SPI) để các thư viện cache triển khai. Ứng dụng sử dụng các kiểu chuẩn như `Cache`, `CacheManager` và `CachingProvider`; nhà cung cấp quyết định cache được lưu ở đâu, cách quản lý bộ nhớ và những tính năng vận hành nào được hỗ trợ.

JCache là **đặc tả**, không phải một thư viện lưu trữ độc lập. Dependency `cache-api` chỉ cung cấp interface. Ứng dụng vẫn cần một provider thực thi API, chẳng hạn Ehcache 3, Hazelcast hoặc Infinispan có hỗ trợ JSR-107.

Trong Spring Framework, hai lớp cầu nối cần phân biệt:

- `JCacheCache`: adapter của **một vùng cache**, bọc `javax.cache.Cache` và trình bày nó theo Spring `org.springframework.cache.Cache`.
- `JCacheCacheManager`: adapter của **toàn bộ cache manager**, bọc `javax.cache.CacheManager` và triển khai Spring `org.springframework.cache.CacheManager`.

```text
Service / Controller
       |
       v
Spring CacheInterceptor
       |
       v
org.springframework.cache.CacheManager
       |
       v
JCacheCacheManager
       |
       v
javax.cache.CacheManager
       |
       v
JCache provider (Ehcache / Hazelcast / Infinispan / ...)
       |
       v
Native cache storage
```

Nhờ adapter, code dùng annotation Spring như `@Cacheable` hoặc API `Cache` của Spring có thể chạy trên provider JCache. Spring cũng hỗ trợ annotation chuẩn JCache như `@CacheResult` và `@CacheRemove`. Hai bộ annotation có thể cùng tồn tại nếu key, null policy và vòng đời cache được thống nhất.

## 2. Các thành phần trong chuẩn JSR-107

| Thành phần | Package | Trách nhiệm |
| --- | --- | --- |
| `CachingProvider` | `javax.cache.spi` | Điểm vào để lấy cache manager; mỗi vendor cung cấp implementation |
| `CacheManager` | `javax.cache` | Tạo, tìm, liệt kê và đóng các cache |
| `Cache<K,V>` | `javax.cache` | Kho key-value có kiểu key và value |
| `MutableConfiguration<K,V>` | `javax.cache.configuration` | Cấu hình kiểu, store-by-value, expiry, loader/writer, listener và statistics |
| `ExpiryPolicy` | `javax.cache.expiry` | Quy định entry hết hạn theo sự kiện tạo, đọc hoặc cập nhật |
| `CacheLoader` / `CacheWriter` | `javax.cache.integration` | Tích hợp nạp hoặc ghi dữ liệu với nguồn ngoài |
| `CacheEntryListener` | `javax.cache.event` | Nhận sự kiện tạo, cập nhật, xóa hoặc hết hạn entry |
| Spring `CacheManager` | `org.springframework.cache` | Abstraction manager mà Spring annotation và interceptor sử dụng |

Cẩn thận vì hai kiểu có cùng tên ngắn `CacheManager` nhưng thuộc hai package khác nhau:

```java
javax.cache.CacheManager nativeManager;
org.springframework.cache.CacheManager springManager;
```

`nativeManager` làm việc với JSR-107 và provider. `springManager` là abstraction của Spring; khi dùng JCache, object thực tế thường là `JCacheCacheManager`.

Một cache tên `products` là một **region**; bên trong region, mỗi key ánh xạ tới một value. Cache name không phải key, và key không phải tên provider. Hai cache cùng tên nhưng thuộc hai manager khác nhau vẫn có thể là hai kho độc lập.

## 3. Provider và cơ chế khám phá qua SPI

### 3.1. Provider không phải CacheManager

Một `CachingProvider` tạo hoặc truy xuất `javax.cache.CacheManager`. Manager sau đó tạo các `Cache`:

```text
CachingProvider
   |
   +-- getCacheManager(URI, ClassLoader, Properties)
             |
             v
       CacheManager
             |
             +-- createCache("products", configuration)
             +-- getCache("products")
             +-- destroyCache("products")
```

Provider thường được phát hiện qua Java Service Provider mechanism, bằng metadata `META-INF/services/javax.cache.spi.CachingProvider` trong JAR. Nhờ vậy ứng dụng có thể dùng API chung mà không tự khởi tạo implementation class ở mọi nơi.

### 3.2. Lấy provider mặc định

```java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

CachingProvider provider = Caching.getCachingProvider();
javax.cache.CacheManager manager = provider.getCacheManager();
```

Cách này phù hợp khi classpath chỉ có **một provider JCache**. Nếu có nhiều provider, lời gọi mặc định có thể báo lỗi vì không xác định được implementation. Hãy chỉ định class provider:

```java
CachingProvider provider = Caching.getCachingProvider(
    "org.ehcache.jsr107.EhcacheCachingProvider"
);
```

Tên class trên là provider của Ehcache 3. Khi đổi vendor, tên implementation cũng đổi; nên đặt việc chọn provider ở cấu hình khởi tạo thay vì lớp nghiệp vụ.

### 3.3. URI, ClassLoader và vòng đời

`CachingProvider` có các overload nhận `URI`, `ClassLoader` và `Properties` để chọn cấu hình manager và phạm vi class loading. Với Ehcache, URI có thể trỏ đến XML định nghĩa cache aliases, heap, expiry và tier.

Cache manager là tài nguyên dùng chung của ứng dụng. Không tạo và đóng manager trong mỗi request. Khi Spring context kết thúc, đóng manager/provider theo vòng đời phù hợp; có thể dùng `@Bean(destroyMethod = "close")` để container thực hiện.

## 4. Tạo cache bằng API chuẩn

### 4.1. MutableConfiguration

Ví dụ tạo cache tên `products`:

```java
import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;

MutableConfiguration<String, Product> config =
        new MutableConfiguration<String, Product>()
            .setTypes(String.class, Product.class)
            .setStoreByValue(false);

Cache<String, Product> products =
        cacheManager.createCache("products", config);
```

Đây là mảnh minh họa khi đã có `cacheManager` và kiểu `Product`. `createCache` thường báo lỗi nếu tên đã tồn tại; nếu cần dùng lại, hãy gọi `getCache` hoặc kiểm tra trước khi tạo.

### 4.2. Các thao tác chính

```java
products.put("P1", new Product("P1", "Bút"));
Product product = products.get("P1");

boolean exists = products.containsKey("P1");
products.remove("P1");
products.removeAll();
```

| API | Ý nghĩa |
| --- | --- |
| `get(key)` / `getAll(keys)` | Đọc một hoặc nhiều value |
| `put(key, value)` / `putAll(map)` | Ghi mới hoặc thay value |
| `getAndPut(key, value)` | Trả value cũ và ghi value mới |
| `putIfAbsent(key, value)` | Chỉ thêm khi key chưa có |
| `remove(key)` | Xóa một key |
| `remove(key, oldValue)` | Xóa có điều kiện theo value |
| `replace(key, value)` | Thay value khi key đã tồn tại |
| `invoke(key, EntryProcessor, args...)` | Thực thi thao tác trên entry theo hỗ trợ provider |
| `iterator()` | Duyệt các entry |
| `clear()` | Xóa entry nhưng giữ cấu trúc cache |
| `close()` | Đóng cache |

JCache dùng generic type nhưng provider có thể kiểm tra kiểu ở runtime theo cấu hình. Không tạo cache khai báo key `Long` rồi ghi key `String`, hoặc ghi value không tương thích.

### 4.3. Store-by-value và store-by-reference

`MutableConfiguration` mặc định theo chuẩn là store-by-value. Provider copy key/value theo cơ chế của nó; điều này tránh việc caller sửa object mutable làm thay đổi dữ liệu đã lưu, nhưng đòi hỏi object phù hợp với cách copy/serialization.

Có thể chọn:

```java
config.setStoreByValue(false);
```

Store-by-reference giữ tham chiếu theo semantics provider. Ví dụ thực hành ở mục 9 chọn `false` để dùng record `Product` không cần triển khai `Serializable`. Đây là quyết định có chủ đích, không phải lựa chọn đúng cho mọi ứng dụng.

Với cache phân tán hoặc off-heap, provider có thể cần serializer/copier riêng. Kiểm tra yêu cầu của vendor và version thay vì suy luận chỉ từ generic type.

## 5. Expiry, loader, writer và statistics

### 5.1. Expiry policy

JCache định nghĩa các policy tiêu chuẩn:

- `CreatedExpiryPolicy`: tính thời hạn từ lúc entry được tạo.
- `AccessedExpiryPolicy`: làm mới thời hạn khi entry được đọc.
- `ModifiedExpiryPolicy`: làm mới khi entry được tạo hoặc cập nhật.
- `TouchedExpiryPolicy`: làm mới khi entry được tạo, đọc hoặc cập nhật.
- `EternalExpiryPolicy`: không hết hạn theo thời gian.

Ví dụ entry sống 10 phút kể từ lúc tạo:

```java
config.setExpiryPolicyFactory(
    CreatedExpiryPolicy.factoryOf(
        new Duration(TimeUnit.MINUTES, 10)
    )
);
```

Các policy thuộc chuẩn JCache, nhưng thời điểm cleanup vật lý, độ chính xác timer và cách kết hợp với tier vẫn có thể khác giữa provider.

### 5.2. Loader và writer

`CacheLoader<K,V>` hỗ trợ nạp value từ nguồn ngoài khi cache được yêu cầu; `CacheWriter<K,V>` hỗ trợ ghi-through hoặc write-behind tùy cấu hình/provider. Chúng khác Spring `@Cacheable`:

- `@Cacheable` là interception ở method Spring.
- `CacheLoader`/`CacheWriter` tích hợp cache với nguồn dữ liệu ở tầng provider.

Không cấu hình hai đường nạp/ghi cùng gọi repository mà không có hợp đồng rõ ràng, vì có thể tạo side effect hoặc truy vấn lặp.

### 5.3. Statistics và management

`MutableConfiguration` có thể bật statistics và management:

```java
config.setStatisticsEnabled(true);
config.setManagementEnabled(true);
```

Provider có thể công bố số liệu/quản trị qua JMX hoặc cơ chế riêng. Bật cờ không tự đảm bảo metrics đã được bind vào Micrometer/Actuator; cần xác minh khả năng provider và cấu hình monitoring.

## 6. Spring JCacheCacheManager và JCacheCache

### 6.1. JCacheCacheManager làm adapter cho Spring

`org.springframework.cache.jcache.JCacheCacheManager` nhận một `javax.cache.CacheManager` và đưa các cache native thành Spring `Cache`. Khi interceptor cần region `products`, adapter tìm cache cùng tên trong native manager rồi bọc bằng `JCacheCache`.

```java
@Bean
org.springframework.cache.CacheManager cacheManager(
        javax.cache.CacheManager nativeManager) {

    JCacheCacheManager manager =
            new JCacheCacheManager(nativeManager);

    manager.setAllowNullValues(false);
    return manager;
}
```

Đây là đoạn cấu hình Spring; `nativeManager` cần được tạo từ provider JCache ở bean khác. `JCacheCacheManager` là bean có kiểu Spring `CacheManager` mà `@EnableCaching` dùng.

### 6.2. JCacheCache là adapter của từng vùng

`JCacheCache` bọc một `javax.cache.Cache` cụ thể và chuyển tiếp các thao tác Spring:

- `getName()` trả tên region.
- `getNativeCache()` trả native JCache cache.
- `get(key)` trả Spring `Cache.ValueWrapper`.
- `put`, `putIfAbsent`, `evict` và `clear` chuyển tiếp sang native cache.
- `get(key, Callable)` dùng callback nạp khi thiếu theo hỗ trợ của implementation.

Ví dụ truy cập adapter:

```java
org.springframework.cache.Cache springCache =
        springManager.getCache("products");

if (springCache == null) {
    throw new IllegalStateException("Missing products cache");
}

Object nativeCache = springCache.getNativeCache();
System.out.println(springCache.getName()); // products
```

Đây là mảnh minh họa cần có `springManager`. Không cast mọi `Cache` thành `JCacheCache` nếu ứng dụng có nhiều provider.

### 6.3. Cache names phải có trong native manager

Cách thông thường là tạo cache trước trên `javax.cache.CacheManager`, rồi để Spring adapter nhìn thấy các tên đã có. Nếu cache không tồn tại, `getCache(name)` có thể không resolve được region và annotation không thể dùng cache đó.

Quy trình khởi tạo:

1. Chọn provider.
2. Tạo native `javax.cache.CacheManager`.
3. Tạo cache names và cấu hình tương ứng.
4. Bọc native manager bằng `JCacheCacheManager`.
5. Đăng ký Spring `CacheManager` bean và bật `@EnableCaching`.
6. Kiểm thử tất cả cache names annotation sử dụng.

## 7. JCache annotations ở tầng method

Spring Framework hỗ trợ annotation JSR-107 từ Spring 4.1. Khi classpath có JCache API và module `spring-context-support`, `@EnableCaching` tự đăng ký cơ chế xử lý annotation JCache cùng annotation Spring.

Các annotation JCache nằm trong `javax.cache.annotation`:

| Annotation JCache | Tác dụng | Gần tương đương trong Spring |
| --- | --- | --- |
| `@CacheResult` | Tra cache trước; miss thì chạy method và cache kết quả | `@Cacheable` |
| `@CachePut` | Lấy tham số `@CacheValue` và ghi vào cache | `@CachePut` |
| `@CacheRemove` | Xóa entry theo key sinh từ tham số | `@CacheEvict` |
| `@CacheRemoveAll` | Xóa toàn bộ entry trong một cache | `@CacheEvict(allEntries=true)` |
| `@CacheDefaults` | Cấu hình mặc định ở cấp class | `@CacheConfig` |
| `@CacheKey` | Đánh dấu tham số tham gia key | Chọn tham số trong SpEL |
| `@CacheValue` | Đánh dấu tham số được ghi vào cache | Không có tương đương trực tiếp |

### 7.1. `@CacheResult`

`@CacheResult` tương tự `@Cacheable`: cache được kiểm tra trước khi chạy method. Nếu có entry, method có thể được bỏ qua và giá trị cache được trả lại.

Một số điểm riêng:

- `skipGet=true` yêu cầu thực thi method thay vì dùng cache hit.
- `exceptionCacheName` cùng `cachedExceptions`/`nonCachedExceptions` cho phép cấu hình cache exception theo JSR-107.
- Key được sinh bằng `CacheKeyGenerator`; mặc định các tham số được chọn theo quy tắc `@CacheKey`/`@CacheValue`.

```java
@CacheResult(cacheName = "products")
public Product find(@CacheKey String id) {
    return repository.find(id);
}
```

Đây là mảnh minh họa của service đã có repository. Nếu method có nhiều tham số và không đánh dấu `@CacheKey`, mặc định các tham số đủ điều kiện có thể tham gia key. Khi có một hoặc nhiều `@CacheKey`, chỉ các tham số được đánh dấu được dùng.

### 7.2. `@CachePut` và `@CacheValue`

JCache `@CachePut` khác Spring `@CachePut`. Chuẩn JCache yêu cầu method có tham số `@CacheValue`; đó là value đưa vào cache.

```java
@CachePut(cacheName = "products")
public void update(
        @CacheKey String id,
        @CacheValue Product product) {

    repository.save(product);
}
```

Mặc định `@CachePut` ghi cache **sau khi method chạy thành công**. Có thể đặt `afterInvocation=false` để ghi trước khi method chạy, nhưng value có thể được cache dù method thất bại. Các thuộc tính `cacheFor`/`noCacheFor` điều khiển xử lý exception trong trường hợp ghi sau invocation.

Tham số `@CacheValue` tự được loại khỏi tập key mặc định. Nếu có `@CacheKey`, chỉ các tham số đó được dùng làm key; ví dụ `id` là key còn `product` là value.

### 7.3. `@CacheRemove` và `@CacheRemoveAll`

`@CacheRemove` xóa một entry theo key:

```java
@CacheRemove(cacheName = "products")
public void delete(@CacheKey String id) {
    repository.delete(id);
}
```

Mặc định xóa sau khi method hoàn tất thành công. `evictFor` và `noEvictFor` cho phép điều khiển việc xóa khi method ném exception. `afterInvocation=false` làm thao tác xóa diễn ra trước method.

`@CacheRemoveAll` xóa cả region:

```java
@CacheRemoveAll(cacheName = "products")
public void reloadCatalog() {
    repository.reload();
}
```

Không dùng xóa toàn bộ cache cho mọi cập nhật một bản ghi nếu chỉ cần evict một key; việc xóa rộng có thể tạo nhiều cache miss và tăng tải nguồn.

### 7.4. `@CacheDefaults`

`@CacheDefaults` đặt mặc định cho các annotation JCache trong class:

```java
@CacheDefaults(cacheName = "products")
public class ProductService {

    @CacheResult
    public Product find(@CacheKey String id) {
        return repository.find(id);
    }

    @CacheRemove
    public void delete(@CacheKey String id) {
        repository.delete(id);
    }
}
```

Các method vẫn cần annotation operation; chỉ gắn `@CacheDefaults` không tự cache mọi method. Ngoài cache name, annotation có thể cấu hình `cacheKeyGenerator` và `cacheResolverFactory`.

## 8. So sánh JCache annotations và Spring annotations

Hai bộ annotation có tên gần giống nhưng semantics không đồng nhất:

| Chủ đề | Spring | JCache |
| --- | --- | --- |
| Cache trước khi chạy method | `@Cacheable` | `@CacheResult` |
| Cập nhật cache sau method | `@CachePut` dùng result trả về | `@CachePut` dùng tham số `@CacheValue` |
| Xóa một key | `@CacheEvict` | `@CacheRemove` |
| Xóa cả region | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` |
| Mặc định class-level | `@CacheConfig` | `@CacheDefaults` |
| Chọn key | SpEL `key` hoặc `KeyGenerator` | `@CacheKey` và `CacheKeyGenerator` |
| Chọn cache | Một operation Spring có thể khai báo nhiều cache names | JCache resolver chọn một cache |
| Cache exception | Không có cơ chế tương đương trực tiếp trong annotation Spring thông thường | `@CacheResult` có thể cache exception theo cấu hình |

Khác biệt quan trọng về key:

- Spring default key generator dùng một tham số trực tiếp nếu chỉ có một tham số, hoặc `SimpleKey` nếu có nhiều tham số.
- JCache default generator tạo một `GeneratedCacheKey` dựa trên tập tham số được chọn.
- Nếu dùng cả hai annotation trên cùng cache, key có thể **khác nhau** dù method nhận cùng chuỗi ID.

Ví dụ Spring:

```java
@org.springframework.cache.annotation.Cacheable(
    cacheNames = "products",
    key = "#p0"
)
public Product findSpring(String id) {
    return repository.find(id);
}
```

Ví dụ JCache:

```java
@javax.cache.annotation.CacheResult(cacheName = "products")
public Product findStandard(@javax.cache.annotation.CacheKey String id) {
    return repository.find(id);
}
```

Hai đoạn trên không tự động chia sẻ cùng entry chỉ vì cùng tên region và cùng tham số. Muốn tương tác qua cùng cache, phải thiết kế key generator/representation tương thích hoặc chỉ dùng một phong cách annotation cho region đó.

## 9. Ví dụ chạy được: Spring 6.2.9 + JCache 1.1.1 + Ehcache 3.10.8

Ví dụ sử dụng JCache annotations thông qua Spring, với Ehcache 3 làm provider. Nó minh họa:

1. Khởi tạo provider bằng SPI và tạo native JCache manager.
2. Tạo cache region `products` bằng cấu hình JCache.
3. Bọc native manager bằng Spring `JCacheCacheManager`.
4. Dùng `@CacheResult` để đọc, `@CachePut` để cập nhật, `@CacheRemove` để xóa một key và `@CacheRemoveAll` để xóa toàn vùng.
5. Đếm số lần repository chạy và số entry còn lại.

### 9.1. Dependency Maven

**JDK 17+**, Spring Framework 6.2.9, JCache API 1.1.1 và Ehcache 3.10.8:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jcache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>org.ehcache</groupId>
            <artifactId>ehcache</artifactId>
            <version>3.10.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` chứa các adapter tích hợp JCache và cơ chế xử lý annotation JCache của Spring. `cache-api` chỉ là API; `ehcache` cung cấp provider thực thi.

### 9.2. Tệp `src/main/java/JCacheDemo.java`

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.TimeUnit;

import javax.cache.Caching;
import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.CreatedExpiryPolicy;
import javax.cache.expiry.Duration;
import javax.cache.spi.CachingProvider;
import javax.cache.annotation.CacheDefaults;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.jcache.JCacheCache;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class JCacheDemo {

    @Bean(destroyMethod = "close")
    CachingProvider cachingProvider() {
        return Caching.getCachingProvider(
                "org.ehcache.jsr107.EhcacheCachingProvider");
    }

    @Bean(destroyMethod = "close")
    CacheManager nativeCacheManager(CachingProvider provider) {
        CacheManager manager = provider.getCacheManager();

        MutableConfiguration<Object, Product> config =
                new MutableConfiguration<Object, Product>()
                    .setTypes(Object.class, Product.class)
                    .setStoreByValue(false)
                    .setExpiryPolicyFactory(
                        CreatedExpiryPolicy.factoryOf(
                            new Duration(TimeUnit.MINUTES, 10)
                        )
                    );

        manager.createCache("products", config);
        return manager;
    }

    @Bean
    org.springframework.cache.CacheManager cacheManager(
            CacheManager nativeCacheManager) {
        JCacheCacheManager manager =
                new JCacheCacheManager(nativeCacheManager);

        // JCache không nhận null key/value; demo dùng kết quả không-null.
        manager.setAllowNullValues(false);
        return manager;
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String id, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Bút"));
        }

        public Product find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public void save(Product product) {
            data.put(product.id(), product);
        }

        public void delete(String id) {
            data.remove(id);
        }

        public void clear() {
            data.clear();
        }

        public int reads() {
            return reads.get();
        }
    }

    @CacheDefaults(cacheName = "products")
    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @CacheResult
        public Product find(@CacheKey String id) {
            return repository.find(id);
        }

        @CachePut
        public void update(
                @CacheKey String id,
                @CacheValue Product product) {
            if (!id.equals(product.id())) {
                throw new IllegalArgumentException("ID does not match product");
            }
            repository.save(product);
        }

        @CacheRemove
        public void delete(@CacheKey String id) {
            repository.delete(id);
        }

        @CacheRemoveAll
        public void clear() {
            repository.clear();
        }
    }

    private static int countEntries(Cache<?, ?> cache) {
        int count = 0;
        for (Cache.Entry<?, ?> entry : cache) {
            count++;
        }
        return count;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(JCacheDemo.class)) {

            ProductService service = context.getBean(ProductService.class);
            ProductRepository repository =
                    context.getBean(ProductRepository.class);
            CacheManager nativeManager =
                    context.getBean(CacheManager.class);

            Cache<Object, Product> nativeProducts =
                    nativeManager.getCache(
                            "products", Object.class, Product.class);

            System.out.println("first: " + service.find("P1"));
            System.out.println("second: " + service.find("P1"));
            System.out.println("source reads after repeat: "
                    + repository.reads());

            service.update("P1", new Product("P1", "Bút xanh"));
            System.out.println("after update: " + service.find("P1"));
            System.out.println("source reads after update: "
                    + repository.reads());

            service.update("P2", new Product("P2", "Sổ"));
            service.delete("P1");
            System.out.println("entries after remove P1: "
                    + countEntries(nativeProducts));

            service.clear();
            System.out.println("entries after removeAll: "
                    + countEntries(nativeProducts));

            org.springframework.cache.Cache springCache =
                    context.getBean(org.springframework.cache.CacheManager.class)
                            .getCache("products");
            System.out.println("Spring adapter: "
                    + (springCache instanceof JCacheCache));
        }
    }
}
```

### 9.3. Chạy và kết quả

Từ thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=JCacheDemo
```

Các dòng do chương trình in ra (không tính log Maven/SLF4J phụ thuộc môi trường):

```text
first: Product[id=P1, name=Bút]
second: Product[id=P1, name=Bút]
source reads after repeat: 1
after update: Product[id=P1, name=Bút xanh]
source reads after update: 1
entries after remove P1: 1
entries after removeAll: 0
Spring adapter: true
```

Giải thích:

1. `find("P1")` lần đầu là cache miss, repository trả `Product(P1, "Bút")`.
2. Lần hai dùng cùng JCache key nên `@CacheResult` trả entry có sẵn; số lần đọc nguồn vẫn là 1.
3. `update("P1", product)` luôn chạy repository và `@CachePut` ghi product mới vào key sinh từ `@CacheKey String id`.
4. Lần `find("P1")` sau nhận `Bút xanh` từ cache; repository không tăng lượt đọc.
5. `update("P2", ...)` thêm entry khác. `delete("P1")` chạy repository rồi `@CacheRemove` xóa key P1; còn P2 nên số entry là 1.
6. `clear()` chạy repository và `@CacheRemoveAll` xóa toàn vùng; số entry còn 0.
7. `instanceof JCacheCache` xác nhận Spring manager đang trả adapter bọc native JCache cache.

**Vì sao key type là `Object.class`?** JCache annotation mặc định tạo `GeneratedCacheKey` từ tham số `@CacheKey`, chứ không nhất thiết dùng raw String `"P1"`. Cấu hình `Object.class` cho phép cache nhận key được sinh theo chuẩn. Nếu chỉ định key type `String.class`, provider có thể từ chối generated key dù method chỉ có một tham số String.

Ví dụ chọn `setStoreByValue(false)` để lưu record `Product` theo tham chiếu, tránh yêu cầu record triển khai `Serializable`. Nếu đổi sang store-by-value, hãy bảo đảm kiểu key/value và copier/serializer đáp ứng provider.

## 10. Cấu hình nâng cao và phần mở rộng vendor

### 10.1. Những gì MutableConfiguration chuẩn hóa

`MutableConfiguration` hỗ trợ các thuộc tính chung như key/value types, store-by-value, expiry policy, loader/writer, listener, statistics và management. Đây là phần có tính portable giữa các provider tương thích.

### 10.2. Những gì phụ thuộc nhà cung cấp

Không phải mọi tính năng vận hành đều có cấu hình thống nhất trong JCache. Ví dụ:
- Giới hạn heap entry hoặc memory weight.
- Off-heap, disk tier, persistence directory.
- Cluster replication và distributed topology.
- Serializer/copier chuyên biệt.
- Eviction algorithm và resilience policy.
- Connection, endpoint hoặc client mode.

Với Ehcache, các cấu hình nâng cao có thể được định nghĩa trong `ehcache.xml` hoặc qua Ehcache native builder rồi bọc bằng `Eh107Configuration`. Khi dùng extension, phần cấu hình đó không còn portable hoàn toàn sang provider khác.

### 10.3. Ví dụ Ehcache XML

Đây là **mảnh cấu hình tùy chọn** cho Ehcache 3, không phải file được chương trình mục 9 sử dụng:

```xml
<config xmlns="http://www.ehcache.org/v3">
    <cache alias="products">
        <key-type>java.lang.Object</key-type>
        <value-type>JCacheDemo$Product</value-type>
        <expiry>
            <ttl unit="minutes">10</ttl>
        </expiry>
        <heap unit="entries">1000</heap>
    </cache>
</config>
```

Khi dùng XML, tạo native manager bằng URI tới resource và class loader phù hợp, sau đó lấy cache alias `products`. Không gọi `createCache("products", ...)` lần nữa trên cùng manager nếu XML đã tạo cache đó.

### 10.4. Đổi provider không đồng nghĩa giữ nguyên mọi hành vi

JCache chuẩn hóa API, nhưng provider vẫn khác về performance, persistence, expiry timing, eviction, loader/writer, transaction, serialization và cluster. Khi đổi vendor, chạy lại test cho kiểu key/value, null handling, cache names, concurrency, invalidation và khả năng sống sót sau restart.

## 11. Null, transaction và key compatibility

### 11.1. JCache không lưu Java null trực tiếp

JSR-107 không cho phép key hoặc value Java null trong thao tác cache chuẩn. Spring `JCacheCacheManager` mặc định cho phép null ở lớp Spring bằng cách chuyển null thành một holder/sentinel nội bộ trước khi ghi native cache. Có thể tắt:

```java
JCacheCacheManager manager = new JCacheCacheManager(nativeManager);
manager.setAllowNullValues(false);
```

Khi cache cấu hình value type chặt như `Product.class`, cách an toàn là không lưu null. Nếu bật sentinel adaptation, native JCache provider sẽ nhìn thấy holder object chứ không phải Java null; type restriction hoặc thao tác native trực tiếp có thể không tương thích với giả định ứng dụng.

Với Spring annotation, có thể dùng `unless="#result == null"` trên `@Cacheable` để bỏ kết quả null. JCache `@CacheResult` không có thuộc tính SpEL `unless` tương đương; hãy thiết kế return value không-null hoặc mô hình “không tìm thấy” riêng.

### 11.2. Store-by-value và object mutable

Nếu provider lưu by value, object có thể được copy/serialize; nếu by reference, caller và cache có thể cùng nhìn một object mutable. Không sửa DTO đã cache tại chỗ mà không có chiến lược rõ ràng. Ưu tiên immutable value hoặc copy object trước khi cập nhật.

### 11.3. Transaction không tự động bao trùm database và cache

`JCacheCacheManager` có hỗ trợ transaction-aware qua lớp quản lý cache của Spring, nhưng điều đó không tự biến mọi provider thành XA transaction hay đảm bảo atomic commit với database.

Nếu transaction rollback, cần biết cache put/evict đã thực hiện trước hay sau commit. Với dữ liệu quan trọng, thiết kế invalidation sau commit, outbox/event hoặc cơ chế consistency riêng. Test cả đường lỗi và rollback; không dùng cache làm source of truth.

### 11.4. Key phải thống nhất giữa hai API

Nếu một method Spring dùng `key="#p0"` tạo key String, còn method JCache dùng `@CacheResult` tạo `GeneratedCacheKey`, hai operation có thể ghi vào hai entry khác nhau trong cùng region. Hãy chọn một bộ annotation cho mỗi region, hoặc cấu hình custom `KeyGenerator`/`CacheKeyGenerator` có semantics tương thích. Kiểm thử đọc/ghi/xóa chéo qua cả hai API nếu ứng dụng dùng đồng thời.

## 12. Programmatic API và Spring API có thể cùng tồn tại

JCache API trực tiếp:

```java
javax.cache.Cache<Object, Product> nativeCache =
        nativeManager.getCache("products", Object.class, Product.class);

nativeCache.put("manual-key", new Product("P9", "Thước"));
Product product = nativeCache.get("manual-key");
nativeCache.remove("manual-key");
```

Spring API:

```java
org.springframework.cache.Cache springCache =
        springManager.getCache("products");

springCache.put("manual-key", new Product("P9", "Thước"));
Product product = springCache.get("manual-key", Product.class);
springCache.evict("manual-key");
```

Cả hai có thể chạm cùng native cache vì `JCacheCache` là adapter. Tuy nhiên cách tạo key và null adaptation có thể khác. Key String ở API trực tiếp không bằng `GeneratedCacheKey` do JCache annotation sinh ra.

Không dùng native API để bypass những chính sách quan trọng đang đặt ở Spring adapter như transaction-aware decoration hoặc null conversion. Khi cần provider-specific capability, lấy native cache qua `getNativeCache()` có chủ đích và ghi rõ phần code phụ thuộc vendor.

## 13. Lỗi thường gặp

1. **Chỉ thêm `cache-api` rồi nghĩ đã có cache.** Đây là API; cần provider thật trên classpath.
2. **Nhầm JCache `CacheManager` với Spring `CacheManager`.** Dùng nhầm import làm wiring sai; đặt tên biến native/spring rõ ràng.
3. **Thiếu `spring-context-support`.** Spring cần module này cho JCache adapter và annotation support.
4. **Có nhiều provider nhưng gọi `Caching.getCachingProvider()` mặc định.** Chỉ định provider class khi classpath có nhiều implementation.
5. **Dùng cache name chưa được tạo.** Tạo region trong native manager trước khi Spring adapter cần resolve.
6. **Nhầm `@CachePut` của Spring và JCache.** JCache yêu cầu tham số `@CacheValue`; Spring dùng result của method.
7. **Không đánh dấu `@CacheKey` khi method có nhiều tham số.** Tham số không liên quan có thể vô tình tham gia key.
8. **Dùng key type quá hẹp.** JCache annotation tạo `GeneratedCacheKey`; cache chỉ chấp nhận `String.class` có thể từ chối key đó.
9. **Trộn Spring key và JCache key.** Cùng region và cùng ID không đảm bảo cùng entry; kiểm tra equality và key generator.
10. **Giả định JCache lưu null.** Native JCache không nhận null; Spring có sentinel adaptation nhưng phải cân nhắc value type.
11. **Đóng manager quá sớm.** Cache manager là tài nguyên dùng chung; đóng trong request sẽ làm request khác lỗi.
12. **Tưởng JCache bảo đảm cluster semantics giống nhau ở mọi provider.** Chuẩn API không chuẩn hóa toàn bộ topology, replication, TTL và persistence.
13. **Gọi createCache nhiều lần với cùng tên.** Có thể nhận exception; quản lý vòng đời tạo/tìm cache nhất quán.
14. **Bỏ qua proxy.** JCache annotations trong Spring vẫn cần infrastructure interception; self-invocation ở proxy mode mặc định không chạy interceptor.
15. **Coi transaction-aware adapter là XA.** Cache và database vẫn có thể lệch nếu rollback, timeout hoặc invalidation sai thời điểm.

## 14. Checklist triển khai và kiểm thử

| Nhóm | Câu hỏi cần xác nhận |
| --- | --- |
| API | Đang dùng `javax.cache`/JCache 1.1 hay API khác? Có nhầm Jakarta namespace không? |
| Provider | Provider nào được SPI chọn? Có nhiều provider trên classpath? |
| Manager | Native manager dùng URI/ClassLoader nào và đóng ở đâu? |
| Region | Mọi cache name annotation dùng đã được tạo chưa? |
| Types | Key/value types có khớp key generator và object thực tế? |
| Storage | Store-by-value hay by-reference? Có yêu cầu serialization/copy? |
| Expiry | TTL/expiry policy đúng vòng đời dữ liệu? |
| Null | Có cho phép null qua Spring adapter không? Native cache có chấp nhận không? |
| Annotation | Đã phân biệt @CacheResult/@CachePut/@CacheRemove với Spring annotations? |
| Keys | Các đường đọc, ghi và xóa tạo key tương thích? |
| Transaction | Put/evict xảy ra trước hay sau commit? Rollback xử lý thế nào? |
| Operations | Có metrics, listener, management, eviction và memory limit phù hợp? |
| Lifecycle | Context shutdown đóng manager/provider đúng thứ tự? |

Các ca kiểm thử tối thiểu:

1. Gọi cùng key hai lần và xác nhận lần hai không gọi repository.
2. Gọi `@CachePut` rồi `@CacheResult` cùng key và xác nhận đọc được value mới.
3. Gọi `@CacheRemove` rồi xác nhận entry không còn.
4. Gọi `@CacheRemoveAll` rồi xác nhận toàn region rỗng.
5. Kiểm tra key generated khi có một, nhiều và một số tham số được đánh dấu `@CacheKey`.
6. Thử provider không cho null và xác nhận ứng dụng xử lý kết quả thiếu đúng.
7. Khởi tạo context nhiều lần để kiểm tra cache đã tồn tại, manager lifecycle và provider cleanup.
8. Test cùng dữ liệu qua Spring API và native JCache API nếu ứng dụng dùng cả hai.
9. Nếu chạy nhiều JVM, test đúng provider/topology thay vì suy luận từ một tiến trình.
10. Giả lập provider lỗi, serialization lỗi, expiry và transaction rollback.

## 15. Khi nào nên chọn JCache?

JCache phù hợp khi tổ chức cần API vendor-neutral, nhiều module cùng dùng cache hoặc muốn giảm phụ thuộc vào API riêng của một thư viện. Nó cũng hữu ích khi hệ sinh thái đã sử dụng JSR-107 annotations hoặc provider tương thích.

Dùng API native của provider có thể hợp lý khi ứng dụng cần tính năng không có trong JCache chuẩn, như topology, tiering, eviction hoặc loader đặc thù. Đổi lại, code phụ thuộc vendor nhiều hơn.

Trong Spring có thể chọn:

- Spring annotations + `JCacheCacheManager`: dùng abstraction và SpEL của Spring trên provider JCache.
- JCache annotations + `@EnableCaching`: dùng chuẩn `javax.cache.annotation`; Spring xử lý interception.
- Native JCache API: chủ động gọi `CachingProvider`, `CacheManager` và `Cache` trong code.
- Kết hợp có kiểm soát: chỉ khi key, null policy, lifecycle và semantics của các đường truy cập đã thống nhất.

**Nguyên tắc lựa chọn:** chuẩn hóa API không xóa khác biệt giữa provider. Hãy quyết định rõ ai sở hữu cache lifecycle, cách tạo key, expiry/size, null policy, invalidation và khả năng vận hành nhiều node.

## Tài liệu chính thức

- Spring Framework 6.2 — JCache (JSR-107) Annotations: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/jsr-107.html
- Spring Framework 6.2.8 — `org.springframework.cache.jcache` package Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/cache/jcache/package-summary.html
- Spring Framework — `JCacheCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html
- JCache API 1.1.1 — `javax.cache.annotation`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/package-summary.html
- JSR-107 specification project: https://github.com/jsr107/jsr107spec
- Ehcache 3 — JSR-107 provider documentation: https://www.ehcache.org/documentation/3.9/107.html
- Ehcache 3.10.8 artifact: https://central.sonatype.com/artifact/org.ehcache/ehcache/3.10.8

# Phân biệt javax.cache.Cache với org.springframework.cache.Cache

## 1. Hai interface cùng tên nhưng thuộc hai hợp đồng

Trong dự án Java có Spring và JCache, hai import thường gặp là:

```java
import javax.cache.Cache;
import org.springframework.cache.Cache;
```

Cả hai đều mô tả một vùng lưu dữ liệu theo key, nhưng mục tiêu khác nhau:

- `javax.cache.Cache<K,V>` thuộc **JCache (JSR-107)**, một API chuẩn cho cache provider. Nó có kiểu key/value, các thao tác quản lý entry, loader, listener, cấu hình và lifecycle.
- `org.springframework.cache.Cache` thuộc **Spring Cache Abstraction**. Đây là hợp đồng thống nhất để Spring annotations và code ứng dụng làm việc với nhiều backend khác nhau.

Spring có adapter `JCacheCache` để bọc một native JCache instance và `JCacheCacheManager` để bọc native `javax.cache.CacheManager`. Nhờ vậy, một cache JCache có thể được truy cập qua cả hai API mà không nhất thiết tạo ra hai kho dữ liệu riêng.

Bài học này giúp bạn phân biệt package, kiểu dữ liệu, method, null semantics, loader, lifecycle, cache manager, cách kết nối hai API và các lỗi thường gặp. Cuối bài có ví dụ Java 17+ dùng Ehcache 3 làm JCache provider và Spring làm lớp adapter.

## 2. Nhận diện package và vai trò

| Tiêu chí | `javax.cache.Cache<K,V>` | `org.springframework.cache.Cache` |
| --- | --- | --- |
| Nguồn gốc | JCache / JSR-107 | Spring Framework |
| Namespace | `javax.cache` | `org.springframework.cache` |
| Generic | Có kiểu `K` và `V` | Không generic; key/value nhận dạng `Object` |
| Ai cung cấp | JCache provider qua `javax.cache.CacheManager` | Spring implementation hoặc adapter |
| Mục tiêu | Hợp đồng cache chuẩn, có cấu hình và tính năng JSR-107 | Hợp đồng cache chung cho Spring annotations và ứng dụng |
| Cách lấy | `getCache(name, keyType, valueType)` | `getCache(name)` |
| Null key/value | JCache không cho phép null key hoặc value | Có thể hỗ trợ null tùy implementation/cấu hình |
| API đặc trưng | `getAll`, `loadAll`, `invoke`, listeners, `unwrap`, `close` | `ValueWrapper`, typed get, `Callable` loader, `getNativeCache` |
| Phạm vi | Có thể dùng ngoài Spring | Gắn với hệ sinh thái Spring |

**Không suy ra backend từ tên interface.** `org.springframework.cache.Cache` không phải một storage cụ thể; nó có thể được hiện thực bởi ConcurrentMap, Caffeine, Redis, JCache adapter hoặc provider khác. `javax.cache.Cache` cũng không đồng nghĩa cache chỉ nằm trong RAM; provider quyết định storage, expiration, clustering và các tính năng bổ sung.

JCache 1.1.1 vẫn sử dụng package `javax.cache.*`. Trong dự án Spring Boot 3 / Spring Framework 6, đừng tự đổi namespace này thành `jakarta.cache.*`.

## 3. So sánh các thao tác quan trọng

### 3.1. Đọc và kiểm tra key

JCache:

```java
javax.cache.Cache<String, String> cache = ...;

String value = cache.get("SKU-1");
boolean exists = cache.containsKey("SKU-1");
```

Spring:

```java
org.springframework.cache.Cache cache = ...;

org.springframework.cache.Cache.ValueWrapper wrapper =
        cache.get("SKU-1");

if (wrapper == null) {
    System.out.println("MISS");
} else {
    System.out.println("HIT: " + wrapper.get());
}
```

Khác biệt:
- JCache trả trực tiếp kiểu `V`. Vì JCache không cho lưu null value, `get(key) == null` biểu thị không có giá trị được cache. Nếu cache cấu hình read-through, thao tác miss có thể kích hoạt loader.
- Spring `get(key)` trả `Cache.ValueWrapper` hoặc null. Wrapper null là miss; wrapper tồn tại có thể chứa giá trị nghiệp vụ null nếu implementation hỗ trợ null.
- Spring có thêm `get(key, Class<T>)` để lấy value trực tiếp; overload này không phân biệt cached-null với miss.
- JCache có `containsKey(key)` để kiểm tra mapping mà không cần lấy value. Khi read-through được cấu hình, `containsKey` chỉ kiểm tra cache, không gọi loader.

### 3.2. Ghi, thay thế và xóa

| Nhu cầu | JCache `javax.cache.Cache` | Spring `org.springframework.cache.Cache` |
| --- | --- | --- |
| Ghi hoặc thay thế | `put(key, value)` | `put(key, value)` |
| Chỉ ghi nếu chưa có | `putIfAbsent(key, value)` trả boolean | `putIfAbsent(key, value)` trả ValueWrapper cũ hoặc null |
| Lấy nhiều key | `getAll(keys)` | Không có method tương đương trong core interface |
| Ghi nhiều key | `putAll(map)` | Không có method tương đương trong core interface |
| Lấy và ghi | `getAndPut(key, value)` | Không có method cùng tên |
| Xóa một key | `remove(key)` trả boolean | `evict(key)`; `evictIfPresent(key)` ở các phiên bản hỗ trợ |
| Xóa nhiều key | `removeAll(keys)` | Không có method tương đương trong core interface |
| Xóa toàn bộ | `removeAll()` hoặc `clear()` | `clear()`; `invalidate()` ở các phiên bản hỗ trợ |

Tên method giống nhau không có nghĩa kiểu trả về và semantics giống nhau. JCache `putIfAbsent` trả boolean; Spring `putIfAbsent` trả wrapper của giá trị cũ hoặc null nếu thao tác đã đăng ký value. Khi code, cần đọc đúng kiểu trả về của package đang import.

Một khác biệt khác: JCache `removeAll()` có thể thông báo listener và gọi CacheWriter đối với từng mapping; `clear()` xóa nội dung mà không thông báo listener hoặc CacheWriter. Đừng mặc định hai method này tương đương. Spring abstraction có `clear()` cho thao tác xóa toàn vùng; chi tiết thực hiện phụ thuộc provider.

### 3.3. Nạp dữ liệu khi cache miss

JCache có thể cấu hình read-through với `CacheLoader`:

```java
javax.cache.Cache<String, String> cache = ...;
String value = cache.get("SKU-1");
```

Nếu cache được cấu hình read-through, việc đọc key chưa có có thể gọi loader do provider quản lý. JCache còn có `loadAll(keys, replaceExistingValues, completionListener)` để yêu cầu nạp nhiều key theo cơ chế bất đồng bộ của provider.

Spring Cache có overload loader theo từng lời gọi:

```java
String value = cache.get("SKU-1", () -> repository.load("SKU-1"));
```

Spring nhận một `Callable<T>` ngay tại call site. Nếu có thể, implementation nên đồng bộ loading để cùng key không bị tính lặp khi nhiều thread miss đồng thời; mức hỗ trợ cụ thể phụ thuộc implementation.

Hai cơ chế có mục đích gần nhau nhưng cách cấu hình khác:
- JCache thường gắn loader vào cấu hình cache/provider.
- Spring abstraction nhận loader theo từng lời gọi qua `Callable`.
- Không thể chuyển nguyên một `CacheLoader` JCache sang `Callable` của Spring mà không xét lifecycle, exception và concurrency semantics.

### 3.4. Cấu hình, quan sát và lifecycle

JCache có các khả năng chuẩn hóa mà core Spring Cache interface không cung cấp trực tiếp:
- `registerCacheEntryListener(...)` và `deregisterCacheEntryListener(...)`.
- `getConfiguration(...)` để đọc cấu hình cache.
- `invoke(key, EntryProcessor, ...)` để xử lý một entry qua API entry processor của provider.
- `unwrap(Class<T>)` để truy cập implementation cụ thể.
- `getCacheManager()`, `isClosed()` và `close()` cho lifecycle.

Spring Cache tập trung vào các thao tác phổ biến phục vụ abstraction. Nó có `getName()` và `getNativeCache()`; method sau là điểm truy cập về provider cụ thể. Khi dùng native API qua `getNativeCache()`, code sẽ phụ thuộc implementation và giảm tính portable của abstraction.

## 4. Null semantics: khác biệt dễ gây lỗi nhất

### 4.1. JCache không chấp nhận null key hoặc null value

Theo JCache 1.1.1, thao tác dùng null key hoặc null value sẽ ném `NullPointerException`. Native cache không có trạng thái “key tồn tại với value null” theo hợp đồng chuẩn.

```java
javax.cache.Cache<String, String> nativeCache = ...;

nativeCache.put("missing", null); // NullPointerException theo JCache
nativeCache.get(null);            // NullPointerException theo JCache
```

Do null value không hợp lệ, `nativeCache.get(key) == null` có thể dùng để biểu thị không có entry (hoặc read-through loader không tạo được value). Nếu nghiệp vụ cần lưu kết quả “không tìm thấy”, hãy dùng sentinel hoặc DTO biểu diễn trạng thái not-found.

### 4.2. Spring abstraction có thể biểu diễn cached-null

Spring Cache được thiết kế cho method Java có thể trả null. `Cache.ValueWrapper` giúp phân biệt:

```java
Cache.ValueWrapper wrapper = springCache.get("user:42");

if (wrapper == null) {
    // Không có entry.
} else if (wrapper.get() == null) {
    // Có entry, giá trị nghiệp vụ là null.
}
```

Khả năng lưu null thực tế phụ thuộc implementation và cấu hình. Một số cache dùng marker nội bộ để lưu null dù native store không hỗ trợ null.

### 4.3. Khi Spring dùng JCache adapter

Spring cung cấp `JCacheCache` và `JCacheCacheManager`. `JCacheCacheManager` mặc định cho phép Spring chuyển null nghiệp vụ thành một holder nội bộ trước khi ghi xuống JCache; JCache native vẫn không nhận null trực tiếp theo JSR-107.

Nếu cùng một cache được truy cập cả bằng Spring wrapper lẫn JCache API:
- Cân nhắc `JCacheCacheManager.setAllowNullValues(false)` để giữ hợp đồng null của JCache.
- Nếu để hỗ trợ null ở Spring wrapper, không đọc/ghi tùy tiện các entry null-adapted bằng native API. Giá trị lưu native có thể là holder của Spring, không phải null JCache.
- Không cache null nếu backend/provider không hỗ trợ cách chuyển đổi hoặc type constraint của cache không tương thích.
- Với negative caching, xác định TTL và eviction khi bản ghi xuất hiện để tránh trả “không tìm thấy” quá lâu.

Đây là khác biệt thiết kế cần quyết định sớm, đặc biệt khi nhiều module dùng hai API cùng truy cập một region.

## 5. Hai CacheManager cũng là hai interface khác nhau

Tên `CacheManager` cũng bị trùng:

| API | Interface | Trách nhiệm chính |
| --- | --- | --- |
| JCache | `javax.cache.CacheManager` | Tạo, tra cứu, liệt kê và hủy cache native; quản lý provider và lifecycle |
| Spring | `org.springframework.cache.CacheManager` | Cung cấp cache theo tên cho Spring abstraction và cache interceptor |

JCache manager có những thao tác như `createCache(name, configuration)`, `getCache(name)`, `destroyCache(name)`, `getCacheNames()` và `close()`. Spring manager chủ yếu cung cấp `getCache(name)` và `getCacheNames()`.

Spring có adapter để kết nối hai hệ thống:

```text
JCache provider
     |
javax.cache.CacheManager
     |
javax.cache.Cache<K,V>
     |
     v
JCacheCacheManager  (Spring adapter)
     |
JCacheCache         (Spring wrapper)
     |
org.springframework.cache.Cache
     |
Spring @Cacheable / @CacheEvict / application code
```

Cụ thể:
- `JCacheCache` hiện thực `org.springframework.cache.Cache` trên một instance `javax.cache.Cache`.
- `JCacheCacheManager` hiện thực `org.springframework.cache.CacheManager` dựa trên một `javax.cache.CacheManager`.
- `springCache.getNativeCache()` cho phép truy cập cache JCache gốc mà wrapper đang sử dụng.

Khi dùng adapter, **không nhất thiết có hai kho cache độc lập**. Spring Cache wrapper và JCache native có thể là hai mặt API của cùng một cache instance.

## 6. Chọn API nào cho từng tình huống?

| Tình huống | Lựa chọn hợp lý |
| --- | --- |
| Service dùng `@Cacheable`/`@CacheEvict`, muốn code không phụ thuộc provider | `org.springframework.cache.Cache` qua Spring CacheManager |
| Ứng dụng Java cần chuẩn JSR-107, không phụ thuộc Spring | `javax.cache.Cache<K,V>` |
| Cần EntryProcessor, CacheEntryListener, read-through/write-through hoặc thao tác JCache đặc thù | Native JCache API |
| Đã có JCache provider và muốn tích hợp vào Spring | `JCacheCacheManager` và `JCacheCache` adapter |
| Cần chia sẻ cùng region giữa native code và Spring annotations | Dùng adapter, thống nhất cache name, key type, key generation và null policy |
| Chỉ cần abstraction cơ bản, có thể đổi backend | Spring Cache abstraction |
| Cần tính năng riêng của provider | Lấy native cache có kiểm soát qua `getNativeCache()` |

**Khuyến nghị:** giữ code nghiệp vụ ở Spring abstraction nếu không cần tính năng đặc thù. Chỉ truy cập JCache native ở những adapter/service có lý do rõ ràng, để phần còn lại của ứng dụng không bị phụ thuộc provider.

### 6.1. Cẩn thận với key generation

JCache native có thể khai báo kiểu key/value, ví dụ `Cache<String, Product>`. Spring abstraction nhận key kiểu `Object` và annotation có thể sinh key mặc định từ nhiều tham số.

Nếu Spring method ghi key `SimpleKey(productId, locale)` nhưng native code đọc key kiểu String `productId`, hai bên đang truy cập **hai mapping khác nhau** dù cùng cache name.

Khi chia sẻ region:
- Chọn một quy tắc key chung.
- Dùng `@Cacheable(key = "#p0")` hoặc KeyGenerator phù hợp nếu native API sử dụng cùng key.
- Đảm bảo kiểu key/value tương thích cấu hình JCache.
- Thống nhất serialization, tenant prefix, version và null policy.
- Test cả đọc từ Spring sau khi ghi native và đọc native sau khi Spring ghi.

### 6.2. Cẩn thận với cùng tên annotation

Spring và JCache cũng có annotation cùng tên nhưng khác package và semantics. Ví dụ:
- Spring `@Cacheable` tương tự JCache `@CacheResult`.
- Spring `@CachePut` và JCache `@CachePut` có khác biệt: JCache yêu cầu tham số `@CacheValue` để chỉ giá trị ghi; Spring thường ghi kết quả method.
- Spring `@CacheEvict` tương tự JCache `@CacheRemove`; xóa toàn bộ gần với `@CacheRemoveAll`.
- Spring `@CacheConfig` gần với JCache `@CacheDefaults`.

Spring Framework hỗ trợ các annotation JCache khi JCache API và module `spring-context-support` có trên classpath. Có thể dùng JCache annotations với Spring caching abstraction mà không nhất thiết đổi cache store. Nếu nhiều annotation cùng tác động một region, cần thống nhất key generation và cache name.

## 7. Ví dụ Java 17+ chạy được: một JCache native, hai cách truy cập

Ví dụ sử dụng Ehcache 3 làm JCache provider, Spring Cache làm lớp adapter và một service dùng `@Cacheable`. Mục đích là chứng minh:
1. Native JCache có thể đọc/ghi cache trực tiếp.
2. Spring Cache wrapper nhìn thấy entry được ghi qua JCache.
3. Native JCache nhìn thấy entry được ghi qua Spring wrapper.
4. Annotation Spring vẫn dùng cùng vùng JCache thông qua `JCacheCacheManager`.

### 7.1. Cấu trúc dự án

```text
jcache-spring-bridge/
  settings.gradle
  build.gradle
  src/main/java/demo/jcache/JCacheBridgeDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'jcache-spring-bridge'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.ehcache:ehcache:3.10.8'
    implementation 'javax.cache:cache-api:1.1.1'
}

application {
    mainClass = 'demo.jcache.JCacheBridgeDemo'
}
```

Ehcache 3 có JCache provider; `javax.cache:cache-api` cung cấp JSR-107 interfaces. Spring Boot starter cache cung cấp Spring cache support, trong đó có module hỗ trợ JCache. Ví dụ dùng Java 17+ và không cần HTTP server hay database.

### 7.2. Mã nguồn Java đầy đủ

Tệp `src/main/java/demo/jcache/JCacheBridgeDemo.java`:

```java
package demo.jcache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JCacheBridgeDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean(destroyMethod = "close")
        CacheManager nativeJCacheManager() {
            CacheManager manager = Caching.getCachingProvider(
                    "org.ehcache.jsr107.EhcacheCachingProvider")
                    .getCacheManager();

            if (manager.getCache("products") == null) {
                MutableConfiguration<String, String> configuration =
                        new MutableConfiguration<String, String>()
                                .setTypes(String.class, String.class);

                manager.createCache("products", configuration);
            }
            return manager;
        }

        @Bean
        org.springframework.cache.CacheManager cacheManager(
                CacheManager nativeJCacheManager) {
            JCacheCacheManager adapter =
                    new JCacheCacheManager(nativeJCacheManager);

            // Giữ semantics JCache: native JCache không cho phép null value.
            adapter.setAllowNullValues(false);
            return adapter;
        }

        @Bean
        ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String load(String sku) {
            return sku + "-load-" + calls.incrementAndGet();
        }

        public int callCount() {
            return calls.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CacheManager nativeManager =
                    context.getBean("nativeJCacheManager", CacheManager.class);

            org.springframework.cache.CacheManager springManager =
                    context.getBean(org.springframework.cache.CacheManager.class);

            Cache<String, String> nativeCache =
                    nativeManager.getCache(
                            "products", String.class, String.class);

            org.springframework.cache.Cache springCache =
                    Objects.requireNonNull(
                            springManager.getCache("products"));

            System.out.println("sameNativeCache="
                    + (springCache.getNativeCache() == nativeCache));

            // Ghi bằng JCache native, đọc bằng Spring Cache.
            nativeCache.put("native-key", "from-jcache");
            System.out.println("nativeContains="
                    + nativeCache.containsKey("native-key"));
            System.out.println("nativeGet="
                    + nativeCache.get("native-key"));
            System.out.println("springReadsNative="
                    + springCache.get("native-key", String.class));

            // Ghi bằng Spring Cache, đọc bằng JCache native.
            springCache.put("spring-key", "from-spring");
            System.out.println("jcacheReadsSpring="
                    + nativeCache.get("spring-key"));

            // Spring annotation dùng cùng cache region.
            ProductService service = context.getBean(ProductService.class);
            System.out.println("first=" + service.load("SKU-1"));
            System.out.println("second=" + service.load("SKU-1"));
            System.out.println("methodCalls=" + service.callCount());
        }
    }
}
```

Chạy tại thư mục dự án với JDK 17+ và Gradle:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper, dùng `./gradlew run --quiet`; trên Windows dùng `gradlew.bat run --quiet`.

Các dòng do ứng dụng in ra (không tính log của Gradle/framework):

```text
sameNativeCache=true
nativeContains=true
nativeGet=from-jcache
springReadsNative=from-jcache
jcacheReadsSpring=from-spring
first=SKU-1-load-1
second=SKU-1-load-1
methodCalls=1
```

### 7.3. Giải thích kết quả

1. `sameNativeCache=true`: Spring `JCacheCache` đang bọc đúng native JCache instance được lấy từ `javax.cache.CacheManager`.
2. `nativeContains=true` và `nativeGet=from-jcache`: ghi và đọc trực tiếp qua JCache API thành công.
3. `springReadsNative=from-jcache`: Spring adapter nhìn thấy dữ liệu native đã ghi, vì cả hai dùng cùng region và key.
4. `jcacheReadsSpring=from-spring`: native JCache đọc được dữ liệu mà Spring Cache wrapper ghi.
5. `first=SKU-1-load-1` và `second=SKU-1-load-1`: service được gọi hai lần cùng key, nhưng `@Cacheable` hit ở lần hai nên body chỉ chạy một lần.
6. `methodCalls=1` xác nhận Spring caching interceptor hoạt động. Service được lấy từ Spring context; nếu tự tạo `new ProductService()` hoặc self-invocation, proxy cache có thể không được áp dụng.

Ví dụ dùng chuỗi String làm key/value để hai API có kiểu tương thích. Trong ứng dụng thực tế, cần kiểm tra serializer, key generator, null adaptation và provider configuration trước khi trộn hai API.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Import nhầm `Cache` | Hai package có cùng tên interface | Import rõ package hoặc dùng fully qualified name |
| Import nhầm `CacheManager` | JCache và Spring đều có interface này | Dùng fully qualified name cho một trong hai |
| JCache `put(key, null)` ném exception | JSR-107 không cho null key/value | Dùng sentinel/DTO hoặc chính sách Spring null adapter rõ ràng |
| Spring wrapper lưu null nhưng native code đọc lỗi | Spring có thể dùng holder nội bộ để thích nghi null | Đặt `allowNullValues=false` khi cần tương thích native hoặc không đọc entry null qua native |
| Spring và native đọc ra hai giá trị khác nhau | Key generation, key type, cache name hoặc serializer không giống | Chuẩn hóa key/name/type/serialization |
| `getNativeCache()` không cast được | Native provider khác dự đoán hoặc wrapper khác | Kiểm tra đúng cache manager và kiểu native |
| `getCache(name)` trả null | Region chưa được tạo hoặc tên sai | Tạo cache bằng JCache manager trước khi dùng hoặc cấu hình provider tạo on-demand |
| Annotation không có tác dụng | Chưa bật `@EnableCaching`, bean không do Spring quản lý hoặc self-invocation | Kiểm tra ApplicationContext và proxy |
| Cache provider không tìm thấy | Thiếu JCache provider hoặc có nhiều provider gây mơ hồ | Thêm đúng provider; chọn rõ provider class nếu cần |
| Runtime type exception | Key/value không khớp cấu hình generic của JCache | Dùng kiểu phù hợp và test trực tiếp với provider |
| Đóng manager làm cache không dùng được | Dùng cache sau khi native manager đã close | Quản lý lifecycle theo Spring container |

### 8.1. Tránh hai manager không cùng một native store

Một lỗi kiến trúc là tạo:
- Một `javax.cache.CacheManager` cho code JCache native.
- Một `JCacheCacheManager` khác lại tự khởi tạo một native manager độc lập.

Dù hai manager dùng cùng provider và cùng tên region, chúng có thể có URI, classloader hoặc cấu hình khác nhau. Khi muốn chia sẻ entry, hãy tạo **một native JCache manager** rồi inject nó vào Spring `JCacheCacheManager` adapter như ví dụ.

### 8.2. Cẩn thận với key mặc định của Spring

Spring có thể sinh `SimpleKey` từ nhiều tham số. Native JCache cache lại có thể được cấu hình `Cache<String, Product>`. Nếu key Spring không phải String, provider có thể ném ClassCastException hoặc hai API nhìn thấy hai entry khác nhau.

Hãy dùng explicit key tương thích, ví dụ `@Cacheable(cacheNames="products", key="#p0")` khi native code dùng chính product ID làm String key.

## 9. Checklist lựa chọn và kiểm thử

Trước khi tích hợp hai API:

1. **Xác định hợp đồng chính:** module nghiệp vụ phụ thuộc Spring Cache hay JCache native?
2. **Xác định provider:** Ehcache, Hazelcast, Infinispan hay implementation JCache khác; kiểm tra phiên bản và tính năng thực tế.
3. **Dùng adapter đúng:** `JCacheCacheManager` phải bọc đúng native `javax.cache.CacheManager` cần chia sẻ.
4. **Chuẩn hóa region name:** tên cache trong annotation phải trùng tên native region.
5. **Chuẩn hóa key:** kiểu và giá trị key từ Spring phải tương thích native JCache configuration.
6. **Quyết định null:** native JCache cấm null; Spring adapter có thể chuyển đổi null bằng holder. Đặt policy rõ ràng.
7. **Kiểm tra lifecycle:** native manager chỉ đóng sau khi các service và cache wrapper không còn sử dụng.
8. **Kiểm tra cache miss/hit:** ghi native rồi đọc Spring; ghi Spring rồi đọc native.
9. **Kiểm tra annotation:** gọi qua bean Spring proxy và đo số lần body chạy.
10. **Kiểm tra provider features:** TTL, listener, read-through/write-through, statistics, serialization và multi-node consistency.
11. **Kiểm tra lỗi:** provider unavailable, cache name sai, key/value type sai, manager closed.
12. **Kiểm tra performance:** native API đặc thù có thể tối ưu một use case nhưng làm code phụ thuộc provider; giữ boundary rõ ràng.

## 10. Câu hỏi tự kiểm tra

**Q1.** `javax.cache.Cache<K,V>` và `org.springframework.cache.Cache` có phải cùng interface được đổi package không?

**Đáp:** Không. JCache là chuẩn JSR-107 với generic key/value và API provider; Spring Cache là abstraction riêng cho Spring integration.

**Q2.** Vì sao JCache `get(key)` trả null có nghĩa khác Spring `get(key)` trả null?

**Đáp:** JCache không cho null value, nên null thường biểu thị miss. Spring trả null wrapper khi miss, còn wrapper khác null có thể chứa giá trị nghiệp vụ null.

**Q3.** Có thể dùng một native JCache cache cho Spring `@Cacheable` không?

**Đáp:** Có. Dùng `JCacheCacheManager` để bọc `javax.cache.CacheManager`; Spring sẽ dùng `JCacheCache` adapter cho region tương ứng.

**Q4.** `getNativeCache()` có tác dụng gì?

**Đáp:** Trả về native cache provider mà Spring wrapper đang bọc, cho phép dùng API đặc thù nhưng khiến code phụ thuộc provider.

**Q5.** JCache `putIfAbsent` và Spring `putIfAbsent` có cùng kiểu trả về không?

**Đáp:** Không. JCache trả boolean; Spring trả ValueWrapper cũ hoặc null theo hợp đồng của Spring Cache.

**Q6.** Vì sao không nên dùng key mặc định của Spring nếu native JCache yêu cầu key String?

**Đáp:** Spring có thể tạo SimpleKey từ nhiều tham số; native cache yêu cầu key tương thích type. Hai bên phải thống nhất key generator và kiểu key.

**Q7.** JCache không cho null, vậy Spring adapter có thể cache null không?

**Đáp:** Spring JCache adapter có thể chuyển null thành holder nội bộ khi cho phép; native API không nhận null trực tiếp. Nếu trộn hai API, cần đặt null policy rõ ràng.

## 11. Ghi nhớ

- `javax.cache.Cache<K,V>` là **JCache/JSR-107 native API**, generic, có loader, listener, EntryProcessor và lifecycle.
- `org.springframework.cache.Cache` là **Spring abstraction**, không generic, hỗ trợ wrapper, typed get và Callable loader.
- `JCacheCache` bọc một JCache native cache; `JCacheCacheManager` bọc native JCache CacheManager.
- JCache không cho null key/value; Spring abstraction có thể hỗ trợ null theo implementation và cấu hình.
- Khi dùng hai API trên cùng region, phải thống nhất **cache name, key, type, serialization và null policy**.
- Dùng Spring abstraction cho tính portable; truy cập JCache native khi thật sự cần các tính năng JSR-107.

### Tài liệu tham khảo chính thức

- [JCache 1.1.1 — javax.cache.Cache Javadoc](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/Cache.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework — Configuring the Cache Storage / JCache](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — JCacheCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCache.html)
- [Spring Framework — JCacheCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)

# Cấu hình chuẩn so với mở rộng riêng của nhà cung cấp

**JCache (JSR-107)** là một bộ API thống nhất để thao tác với cache Java. Nó giải quyết việc ứng dụng gọi cache qua các interface chuẩn, nhưng **không yêu cầu mọi cache provider hỗ trợ cùng tính năng lưu trữ, hiệu năng, eviction policy hay topology**. Khi làm việc với Spring Cache, phải phân biệt ba tầng: **Spring Cache Abstraction**, **JCache API** và **cấu hình của provider** như Caffeine hoặc Ehcache.

Câu hỏi quan trọng: phần nào nên viết bằng **javax.cache.configuration.MutableConfiguration** để dễ chuyển provider; phần nào nên dùng extension riêng để bảo đảm dung lượng, độ trễ, TTL, đo lường và hiệu năng? Bài học này có code Java 17 + Spring 6.1 + Caffeine JCache, một bài kiểm thử tích hợp và checklist chuyển provider.

## 1. Phân lớp để tránh nhầm trách nhiệm

~~~text
  Service nghiệp vụ: @Cacheable / @CacheResult
                         |
              Spring Cache Abstraction
                         |
              JCacheCacheManager adapter
                         |
 javax.cache.CacheManager / Cache / Configuration
                         |
                JCache CachingProvider
                         |
        Caffeine JCache / Ehcache / provider khác
                         |
        Bộ nhớ, eviction, IO, serialization
~~~

- **Spring Cache**: **@Cacheable**, **@CachePut**, **@CacheEvict**, CacheResolver, KeyGenerator và proxy/interceptor quyết định phương thức nghiệp vụ có chạy khi hit/miss. Spring có thể dùng **CaffeineCacheManager** trực tiếp hoặc **JCacheCacheManager** để đi qua JSR-107.
- **JCache chuẩn**: **javax.cache.Caching**, **javax.cache.CacheManager**, **javax.cache.Cache**, **MutableConfiguration**, **ExpiryPolicy**, CacheLoader, CacheWriter, listener... cung cấp hợp đồng API chung. Chỉ thêm **cache-api** không tạo ra một cache store thật.
- **Provider**: thi hành lưu trữ, giới hạn bộ nhớ, xử lý expiration, thống kê, persistence, cluster, và các extension. Thay provider không có nghĩa các thuộc tính vendor-specific tự chuyển theo.

**Hai khái niệm phải tách:** lựa chọn **JCache API** là quyết định về interface; lựa chọn **Caffeine/Ehcache** là quyết định về implementation và vận hành. Spring annotation là một lựa chọn khác nữa.

## 2. Cấu hình portable bằng MutableConfiguration

**MutableConfiguration<K,V>** thuộc chuẩn JCache. Ví dụ (đoạn minh họa nằm trong một phương thức khởi tạo có import và classpath phù hợp):

~~~java
import java.util.concurrent.TimeUnit;

import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.Duration;
import javax.cache.expiry.ModifiedExpiryPolicy;

CacheManager manager = Caching.getCachingProvider(
        "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider")
    .getCacheManager();

MutableConfiguration<String, String> config =
        new MutableConfiguration<String, String>()
            .setTypes(String.class, String.class)
            .setStoreByValue(false)
            .setExpiryPolicyFactory(ModifiedExpiryPolicy.factoryOf(
                    new Duration(TimeUnit.MINUTES, 5)))
            .setStatisticsEnabled(true);

Cache<String, String> cache =
        manager.createCache("productNames", config);

cache.put("P01", "Green tea");
String name = cache.get("P01");
~~~

Các **kiểu** của cache, chính sách copy, ExpiryPolicy và thao tác **get/put** là phần chuẩn. Chuỗi **Caching.getCachingProvider(...)** ở đây chỉ định class của Caffeine để chọn triển khai khi runtime; nếu chuyển sang Ehcache thì thay dependency và provider selector, đồng thời kiểm chứng hợp đồng. Không nên gọi **Caching.getCachingProvider()** mà không chỉ định khi ứng dụng có nhiều provider cùng ở classpath, vì lựa chọn có thể không rõ ràng hoặc thất bại.

**setStoreByValue(false)** là một tùy chọn chuẩn, không phải đặc tính chỉ Caffeine có. Mặc định **MutableConfiguration** thường bật **store-by-value**: cache có thể copy đối tượng tại ranh giới API. Store-by-reference có thể chia sẻ cùng object mutable giữa các caller, ảnh hưởng tới thread safety và data isolation. Với một provider cụ thể, hãy kiểm tra **OptionalFeature.STORE_BY_REFERENCE**, serialize/copy semantics và hỗ trợ thực tế. Demo dùng **String bất biến** để tránh nhập nhằng.

### Các phần thuộc hợp đồng JCache

| API/thuộc tính | Mức chuẩn hóa | Vai trò |
| --- | --- | --- |
| CachingProvider, Caching, CacheManager, Cache | **JCache chuẩn** | Tạo/tra cache, đọc, ghi, xóa |
| MutableConfiguration#setTypes | **Chuẩn** | Kiểu key và value |
| setStoreByValue | **Chuẩn** | Copy giá trị hoặc tham chiếu |
| setExpiryPolicyFactory | **Chuẩn** | Quy tắc expiration dựa vào create/update/read |
| setCacheLoaderFactory, setReadThrough | **Chuẩn** | Khai báo read-through |
| setCacheWriterFactory, setWriteThrough | **Chuẩn** | Khai báo write-through |
| CacheEntryListenerConfiguration | **Chuẩn** | Quan sát sự kiện |
| setStatisticsEnabled, setManagementEnabled | **Chuẩn** | Điều khiển chức năng thống kê/quản trị |
| Cache.get, put, remove, invoke | **Chuẩn** | Thao tác và EntryProcessor |
| maximumSize, native weigher, cache tiers | **Không có thuộc tính chung** | Cần provider-specific options |
| refreshAfterWrite async, native ticker, scheduler | **Không phải JCache config chung** | Provider/loader riêng |
| Persistence, disk, replication, cluster topology | **Không được chuẩn hóa ở cùng mức** | Phụ thuộc thiết kế provider |

**Có trong chuẩn ≠ hành vi hiệu năng giống nhau.** Hai provider có thể hỗ trợ cùng MutableConfiguration nhưng có serializer, clock, mức độ đồng bộ, metrics và tradeoff khác nhau.

## 3. Đặc biệt dễ nhầm: JCache ExpiryPolicy và Caffeine TTL

JCache có những ExpiryPolicy sau:

| ExpiryPolicy chuẩn | Tuổi bắt đầu | Sự kiện đặt lại tuổi |
| --- | --- | --- |
| **CreatedExpiryPolicy** | Tạo entry | Không reset khi update hoặc read |
| **ModifiedExpiryPolicy** | Tạo entry | Update entry |
| **AccessedExpiryPolicy** | Tạo entry | Access/read; không coi update là access |
| **TouchedExpiryPolicy** | Tạo entry | Read **hoặc** update |
| **EternalExpiryPolicy** | Không hết hạn theo timer | Không áp dụng |

**CreatedExpiryPolicy không phải bản sao của expireAfterWrite.** Với Caffeine, **expireAfterWrite** tính tuổi từ lúc tạo hoặc thay value; còn CreatedExpiryPolicy tính tuổi từ lần tạo đầu tiên, update không reset expiry. **ModifiedExpiryPolicy** gần hơn với expireAfterWrite, vì tính lại thời hạn sau update.

Ví dụ chuẩn:

~~~java
MutableConfiguration<String, String> config =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setExpiryPolicyFactory(
            ModifiedExpiryPolicy.factoryOf(
                new javax.cache.expiry.Duration(
                    java.util.concurrent.TimeUnit.MINUTES, 5)));
~~~

Caffeine native API lại nhận kiểu **java.time.Duration**:

~~~java
Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(java.time.Duration.ofMinutes(5));
~~~

**Không trộn hai kiểu Duration:** JCache dùng **javax.cache.expiry.Duration**, còn Caffeine native dùng **java.time.Duration**. Dùng sai import có thể làm code không biên dịch.

ExpiryPolicy chỉ quyết định *hết hạn*; không phải job tự nạp lại cache. Khi entry expired, lookup thường miss và một method **@Cacheable** có thể phải chạy để tải dữ liệu. **refreshAfterWrite** là cơ chế riêng, không tương đương ModifiedExpiryPolicy.

## 4. Cấu hình riêng của Caffeine JCache

Caffeine cung cấp module JCache và class **com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration**. Class này hỗ trợ các thuộc tính JCache và bổ sung tùy chọn Caffeine.

~~~java
import java.util.OptionalLong;
import javax.cache.configuration.MutableConfiguration;
import com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration;

MutableConfiguration<String, String> portable =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setStoreByValue(false);

CaffeineConfiguration<String, String> vendorConfig =
    new CaffeineConfiguration<>(portable)
        .setMaximumSize(OptionalLong.of(100));

manager.createCache("boundedProducts", vendorConfig);
~~~

**setMaximumSize** là phương thức của **CaffeineConfiguration**, không tồn tại trên MutableConfiguration. Bạn vẫn có thể đọc ghi cache thông qua **javax.cache.Cache**: extension chỉ xuất hiện ở **nơi tạo cache**, không phải ở code nghiệp vụ.

Caffeine còn có các tùy chọn như **maximumWeight/weigher**, expireAfterWrite/Access native, ticker, executor, scheduler, native statistics và refreshAfterWrite. Các tùy chọn này chỉ có ý nghĩa với provider/phiên bản phù hợp; cấu hình refresh cần loader/read-through đúng cách và không tự biến annotation Spring thành job định kỳ.

**Caffeine JCache khác Caffeine native:** 

- Nếu dùng trực tiếp **Caffeine.newBuilder()**, bạn tạo native Caffeine Cache.
- Nếu dùng **CaffeineConfiguration** trong JCache, bạn vẫn tạo cache bằng **javax.cache.CacheManager**.
- Nếu dùng **Spring CaffeineCacheManager**, Spring adapter trực tiếp Caffeine native, không có một JCache provider trung gian.
- Nếu dùng **Spring JCacheCacheManager**, Spring adapter của JCache làm việc với javax.cache.CacheManager của provider.

Những con đường này có thể dùng cùng engine nhưng **không tự chia sẻ cùng instance cache**, key, config hay entry. Không nên chỉ thấy từ “Caffeine” rồi mặc định mọi CacheManager đều trỏ cùng cache.

### Mở rộng bằng cấu hình provider

Caffeine JCache cũng có các tên option riêng trong HOCON, ví dụ dạng minh họa:

~~~hocon
caffeine.jcache {
  boundedProducts {
    maximum {
      size = 100
    }
  }
}
~~~

Đây **không phải định dạng cấu hình JCache chung**. Cần kiểm tra đúng tên cache, vị trí application.conf, classloader, nguồn config và precedence của provider đang chạy. Không cấu hình cùng một cache qua nhiều nguồn xung đột rồi cho rằng thứ tự áp dụng luôn cố định.

## 5. Ehcache và provider phân tán cũng có extension

**Ehcache** có hướng cấu hình bằng XML/builder và resource pools như heap/off-heap/disk tùy phiên bản/chế độ. Nếu bạn chuyển cache JCache từ Caffeine sang Ehcache, **cache.get**, **cache.put** và MutableConfiguration có thể giữ phần lớn hình thức, nhưng giới hạn 100 entry phải được cấu hình bằng cơ chế Ehcache, không phải setMaximumSize.

**Hazelcast, Infinispan hoặc provider phân tán** có các tùy chọn cluster membership, near-cache, partition, failover, persistence và consistency theo tài liệu riêng. JCache không có một thuộc tính portable đảm bảo cache tự chạy trên nhiều node hay transaction nhiều cache nguyên tử.

Cần phân biệt tiêu chí **“tương thích API JCache”** với tiêu chí **“thực hiện cùng SLA tải/latency/correctness”**. Provider mới có thể khác về serialization, TTL maintenance, eviction ordering, caching null, statistics, listener và timeouts. Chỉ compile thành công chưa đủ để chứng minh migration đúng.

## 6. Spring annotation và JCache annotation không hoàn toàn giống nhau

Spring Framework hỗ trợ hai bộ annotation nhưng semantics không đồng nhất:

| Spring annotation | JSR-107 annotation | Cần lưu ý |
| --- | --- | --- |
| **@Cacheable** | **@CacheResult** | JCache có skipGet và cache exception |
| **@CachePut** | **@CachePut** | Spring put **kết quả trả về**, JCache dùng tham số **@CacheValue** |
| **@CacheEvict** | **@CacheRemove** | Điều kiện xóa trước/sau lời gọi khác nhau |
| **@CacheEvict(allEntries = true)** | **@CacheRemoveAll** | Xóa cả cache |
| **@CacheConfig** | **@CacheDefaults** | Cấu hình cache mặc định ở class |
| **key = "#p0"** | **@CacheKey / CacheKeyGenerator** | Kiểu key có thể khác |

Ví dụ minh họa hai cách viết:

~~~java
// Dùng Spring annotation:
@org.springframework.cache.annotation.Cacheable(
        cacheNames = "books", key = "#p0")
public String findSpring(String isbn) {
    return repository.load(isbn);
}

// Dùng JCache annotation:
@javax.cache.annotation.CacheResult(cacheName = "books")
public String findJcache(@javax.cache.annotation.CacheKey String isbn) {
    return repository.load(isbn);
}
~~~

Đây là các snippet **không độc lập để javac**, bởi chúng cần bean/repository và class chủ. Quan trọng hơn, **Spring SpEL key #p0 là String ISBN**; key do JCache CacheKeyGenerator mặc định có thể là **GeneratedCacheKey object**. Nếu cả hai method dùng chung cache name, chúng có thể không hit chung một entry, hoặc xung đột với ràng buộc **setTypes(String.class, ...)**. Muốn phối hợp, cần thiết kế key generation thống nhất và test chính xác.

Dù dùng Spring 6/Jakarta ở các API khác, **JSR-107 phiên bản 1.1.1 vẫn nằm trong javax.cache**, không tự đổi sang **jakarta.cache**. Spring hỗ trợ JCache annotations nếu có cache API, spring-context-support và annotation support tương ứng trên classpath.

## 7. Demo Java 17 + Spring Framework: standard config và extension

Đây là ví dụ đầy đủ: hai cache được tạo qua cùng **Caffeine JCache provider**, một bằng **MutableConfiguration** thuần JCache, một bằng **CaffeineConfiguration** bổ sung giới hạn 100 entry. Spring dùng **JCacheCacheManager** và hai method **@Cacheable**; kiểm thử chứng minh hai cache hoạt động độc lập và Spring + javax.cache cùng thấy đúng entry.

**Công nghệ:** Java 17, Spring Framework 6.1.14, Caffeine JCache 3.1.8, JCache API 1.1.1, JUnit 5.10.2.

Cấu trúc project:

~~~text
spring-jcache-standard-vendor/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/JCacheConfigDemo.java
└── src/test/java/demo/cache/JCacheConfigDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-jcache-standard-vendor'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-context-support:6.1.14'
    implementation 'javax.cache:cache-api:1.1.1'
    implementation 'com.github.ben-manes.caffeine:jcache:3.1.8'

    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.JCacheConfigDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/JCacheConfigDemo.java**

~~~java
package demo.cache;

import java.util.OptionalLong;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.Duration;
import javax.cache.expiry.ModifiedExpiryPolicy;
import javax.cache.spi.CachingProvider;

import com.github.benmanes.caffeine.jcache.configuration.CaffeineConfiguration;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class JCacheConfigDemo {

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean(destroyMethod = "close")
        public javax.cache.CacheManager jcacheManager() {
            CachingProvider provider = Caching.getCachingProvider(
                    "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
            javax.cache.CacheManager manager = provider.getCacheManager();

            MutableConfiguration<String, String> standard =
                    new MutableConfiguration<String, String>()
                        .setTypes(String.class, String.class)
                        .setStoreByValue(false)
                        .setExpiryPolicyFactory(
                            ModifiedExpiryPolicy.factoryOf(
                                new Duration(TimeUnit.MINUTES, 5)));

            manager.createCache("standardCatalog", standard);

            CaffeineConfiguration<String, String> extended =
                    new CaffeineConfiguration<>(standard)
                        .setMaximumSize(OptionalLong.of(100));

            manager.createCache("extendedCatalog", extended);
            return manager;
        }

        @Bean
        public org.springframework.cache.CacheManager cacheManager(
                javax.cache.CacheManager jcacheManager) {
            return new JCacheCacheManager(jcacheManager);
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger standardLoads = new AtomicInteger();
        private final AtomicInteger extendedLoads = new AtomicInteger();

        @Cacheable(cacheNames = "standardCatalog", key = "#p0")
        public String standard(String id) {
            return "std:" + id + ":load"
                    + standardLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "extendedCatalog", key = "#p0")
        public String extended(String id) {
            return "ext:" + id + ":load"
                    + extendedLoads.incrementAndGet();
        }

        public String loads() {
            return "std=" + standardLoads.get()
                    + ",ext=" + extendedLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                Config.class)) {
            CatalogService service = ctx.getBean(CatalogService.class);
            javax.cache.CacheManager manager =
                    ctx.getBean(javax.cache.CacheManager.class);

            System.out.println("standardFirst="
                    + service.standard("P01"));
            System.out.println("standardHit="
                    + service.standard("P01"));

            System.out.println("extendedFirst="
                    + service.extended("P01"));
            System.out.println("extendedHit="
                    + service.extended("P01"));

            System.out.println("directStandard="
                    + manager.getCache("standardCatalog",
                        String.class, String.class).get("P01"));
            System.out.println("directExtended="
                    + manager.getCache("extendedCatalog",
                        String.class, String.class).get("P01"));

            System.out.println("beforeRemove=" + service.loads());

            manager.getCache("standardCatalog",
                    String.class, String.class).remove("P01");
            System.out.println("standardAfterRemove="
                    + service.standard("P01"));
            System.out.println("afterRemove=" + service.loads());
        }
    }
}
~~~

Chạy tại thư mục project với Gradle/JDK 17 hoặc wrapper tương thích:

~~~bash
gradle run --quiet
~~~

Những dòng do **System.out.println** in ra theo đúng thứ tự:

~~~text
standardFirst=std:P01:load1
standardHit=std:P01:load1
extendedFirst=ext:P01:load1
extendedHit=ext:P01:load1
directStandard=std:P01:load1
directExtended=ext:P01:load1
beforeRemove=std=1,ext=1
standardAfterRemove=std:P01:load2
afterRemove=std=2,ext=1
~~~

**Giải thích:** Hai lần đọc liên tiếp cùng key chỉ chạy thân method lần đầu. Đọc trực tiếp qua **javax.cache.Cache.get("P01")** trả cùng dữ liệu mà Spring cache interceptor đã ghi: cả hai tầng dùng chung cache store thật của provider. Lệnh **remove** qua JCache chỉ xóa một key trong **standardCatalog**, nên lần gọi Spring tiếp theo tạo miss và tăng count lên 2; extendedCatalog độc lập vẫn có count 1.

**Phạm vi được kiểm chứng:** cache được tạo bằng cấu hình chuẩn và mở rộng vẫn đọc/ghi bằng cùng JCache API, Spring adapter dùng đúng vùng và key. Demo **không cố chứng minh eviction sau đúng 100 entry, TTL đúng mốc năm phút hay hiệu năng production**; các ca đó cần test riêng với fake ticker/load test.

### JUnit 5 integration test

**src/test/java/demo/cache/JCacheConfigDemoTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(JCacheConfigDemo.Config.class)
class JCacheConfigDemoTest {

    @Autowired
    JCacheConfigDemo.CatalogService service;

    @Autowired
    javax.cache.CacheManager nativeManager;

    @Test
    void standardAndVendorCachesShareTheJCacheApi() {
        assertEquals("std:P01:load1", service.standard("P01"));
        assertEquals("std:P01:load1", service.standard("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("std=1,ext=1", service.loads());

        var standard = nativeManager.getCache(
                "standardCatalog", String.class, String.class);
        var extended = nativeManager.getCache(
                "extendedCatalog", String.class, String.class);

        assertNotNull(standard);
        assertNotNull(extended);
        assertEquals("std:P01:load1", standard.get("P01"));
        assertEquals("ext:P01:load1", extended.get("P01"));

        assertTrue(standard.remove("P01"));
        assertNull(standard.get("P01"));

        assertEquals("std:P01:load2", service.standard("P01"));
        assertEquals("ext:P01:load1", service.extended("P01"));
        assertEquals("std=2,ext=1", service.loads());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng: một test JUnit thành công khi dependency và runtime phù hợp. Test lấy bean từ ApplicationContext; nếu dùng **new CatalogService()** thì không có Spring AOP proxy để áp dụng @Cacheable. Chưa có bài test TTL ở đây vì không chờ thời gian thực; test expiration nên dùng ticker của provider/clock giả lập khi có thể.

## 8. Những rủi ro khi chuyển provider

**Thay Caffeine bằng Ehcache**, code dùng **javax.cache.Cache<K,V>** có thể giữ nguyên chữ ký nhưng những phần sau cần xem lại:

1. **CaffeineConfiguration** không còn dùng được: đổi sang XML hoặc builder của Ehcache cho resource pools, size hoặc tiers.
2. **Store by value/reference**: default và hỗ trợ copy có thể khác; với object mutable cần kiểm tra isolation.
3. **Cache names và key types**: key string vs GeneratedCacheKey do JCache annotation tạo có thể khác.
4. **Expiry semantics**: Created/Modified/Accessed/Touched phải được test ở cùng các mốc create/update/read.
5. **Statistics và JMX**: cờ chuẩn không bảo đảm cùng hệ metrics hay overhead.
6. **CacheLoader/Writer**: phải thử fail/retry và ứng xử khi backend lỗi; không nên bật read-through khi chưa có loader.
7. **Concurrency/transaction**: get/put/xóa không tự biến thành một distributed transaction.
8. **Multi-node**: cache local với shared cache có ngữ nghĩa khác, dù method gọi vẫn là Cache.get.
9. **Exception/null**: type restriction và provider null support có thể khác; không giả định có thể cache null.
10. **Lifecycle**: khi provider/manager close, các entry/handle không còn dùng được; phải quản lý startup/shutdown.

**Chỉ đổi dependency cho app compile là chưa đủ** để xác nhận business semantics hoặc SLA. Cần chạy lại contract tests.

## 9. Tách module cấu hình theo ranh giới rõ

Một cấu trúc có thể tổ chức như sau:

~~~text
domain/
  CatalogService.java             # Không import package Caffeine/Ehcache
cache-contract/
  CacheNames.java                 # Tên và key semantics
infra-jcache/
  StandardJCacheConfig.java       # MutableConfiguration, ExpiryPolicy
infra-jcache-caffeine/
  CaffeineJCacheConfig.java       # CaffeineConfiguration, size, ticker
infra-jcache-ehcache/
  EhcacheConfig.java              # Cấu hình riêng khi cần chuyển
tests/
  CatalogCacheContractTest.java   # Chạy được theo provider hỗ trợ
~~~

Cố gắng giữ phần **business service** không phụ thuộc vendor. Nếu cần native unwrap hoặc một policy quá đặc thù, đặt nó sau một interface/configuration adapter và ghi rõ giới hạn portability. Không phải mọi extension đều xấu: nếu một tính năng như maximumSize giúp không tràn heap, sử dụng extension có kiểm thử sẽ tốt hơn việc “thuần JCache” nhưng không kiểm soát bộ nhớ.

**Quy trình quyết định:**

- Ưu tiên API chuẩn cho key/value, expiry policy cơ bản, event, loader/writer nếu đủ.
- Thêm extension khi yêu cầu **đo được**: memory cap, disk persistence, advanced refresh, latency, cluster.
- Ghi rõ policy nào chỉ đúng với provider và version hiện hành.
- Chọn provider tường minh và verify cache names at startup.
- Kiểm thử TTL, store-by-value, concurrency, errors, eviction, lifecycle trên implementation thật.
- Dùng metrics phản ánh **freshness và correctness**, không chỉ hit ratio.

## 10. Checklist QA và lỗi phổ biến

| Nội dung cần xác minh | Cách kiểm tra |
| --- | --- |
| CachingProvider đúng | Truyền class name vào Caching.getCachingProvider, kiểm tra provider thực tế |
| Có provider runtime | Không chỉ thêm javax.cache:cache-api |
| Cache tồn tại và đúng type | CacheManager.getCache(name, K.class, V.class) |
| Spring JCache adapter hoạt động | Test @Cacheable qua Spring-managed bean, so sánh JCache.get |
| ExpiryPolicy thực sự áp dụng | Test create, update, access, expired read ở mốc biên |
| Size bound hoạt động | Tạo đủ key, chạy cleanup/maintenance rồi quan sát eviction theo policy |
| Copy/serialization | Với mutable object, kiểm tra store-by-value/reference |
| Key JCache annotations | Đối chiếu GeneratedCacheKey với Spring SpEL key |
| Loader và writer | Test đọc/ghi nguồn, lỗi và retry |
| Thay provider | Chạy cùng bộ contract tests với provider thay thế |

Những lỗi hay gặp:

- **Nhầm Spring CacheManager với javax.cache.CacheManager**: cần JCacheCacheManager làm adapter nếu đi qua JSR-107.
- **Chỉ cài API mà không có provider**: không có triển khai cache thật.
- **Dùng nhiều provider mà không chỉ định tên provider**: khó dự đoán provider được chọn.
- **Coi maximumSize là method trên MutableConfiguration**: nó không thuộc JCache API chuẩn.
- **Nhầm CreatedExpiryPolicy với expireAfterWrite**: Created không reset vì update; Modified mới gần hơn.
- **Dùng java.time.Duration cho javax.cache.expiry.Duration**: sai API.
- **Giữ key của Spring và JCache annotation khác nhau trong cùng cache**: cache miss ngoài ý muốn.
- **Cho rằng có JCache API là cache phân tán**: phải chọn provider/network architecture riêng.
- **Bật store-by-value hoặc read-through mà không kiểm tra copy/loader**: dễ phát sinh lỗi runtime.
- **Tin rằng refreshAfterWrite luôn tự chạy đúng giờ**: còn phụ thuộc loader và request.
- **Chỉ test happy path, bỏ qua eviction, failure, concurrency, transaction**.

## 11. Câu hỏi tự kiểm tra

1. Phần nào là API chuẩn của JCache, phần nào là mở rộng riêng của Caffeine?
2. Vì sao **MutableConfiguration** không có setMaximumSize?
3. **CreatedExpiryPolicy** khác **ModifiedExpiryPolicy** ra sao khi ghi đè entry?
4. **AccessedExpiryPolicy** khác **TouchedExpiryPolicy** thế nào?
5. Vì sao dùng **Spring @Cacheable** với JCacheCacheManager không đồng nghĩa sử dụng JCache @CacheResult?
6. Nếu hai annotation family dùng key khác kiểu, chuyện gì xảy ra khi chúng chung một cache?
7. Tại sao **storeByValue(false)** cần được cân nhắc kỹ với mutable object?
8. Khi chuyển từ Caffeine JCache sang Ehcache, phần nào của code giữ được và phần nào phải thay?
9. Bật read-through mà không có CacheLoader hợp lệ gây vấn đề gì?
10. Vì sao compile/test đơn giản chưa đủ xác nhận SLA của distributed provider?

**Kết luận:** JCache chuẩn hóa hợp đồng đọc/ghi cache và các chính sách cơ bản; provider mở rộng khả năng bộ nhớ, persistence, refresh, metrics và distributed cache. Trong Spring, dùng **JCacheCacheManager** để nối hai tầng khi cần. Hãy **để code nghiệp vụ độc lập provider**, dùng **MutableConfiguration** cho phần portable, cô lập **vendor-specific configuration** tại tầng hạ tầng và có contract tests khi đổi implementation.

### Tài liệu tham khảo

- Spring Framework — JCache (JSR-107) annotations: https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html
- Spring Framework — Store configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — JCacheCacheManager API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html
- JCache — ExpiryPolicy API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/expiry/ExpiryPolicy.html
- JCache — CreatedExpiryPolicy API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/expiry/CreatedExpiryPolicy.html
- Caffeine — JCache provider overview: https://github.com/ben-manes/caffeine/wiki/JCache
- Caffeine — CaffeineConfiguration: https://github.com/ben-manes/caffeine/blob/master/jcache/src/main/java/com/github/benmanes/caffeine/jcache/configuration/CaffeineConfiguration.java
- Caffeine — JCache reference.conf: https://github.com/ben-manes/caffeine/blob/master/jcache/src/main/resources/reference.conf
- Ehcache — JCache provider: https://www.ehcache.org/documentation/3.0/107.html

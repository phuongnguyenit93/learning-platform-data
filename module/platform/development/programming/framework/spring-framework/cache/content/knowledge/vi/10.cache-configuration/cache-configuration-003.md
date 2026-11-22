# Thứ tự ưu tiên giữa cấu hình toàn cục, lớp và phương thức trong Spring Cache

## Mục tiêu học tập

Spring Cache có nhiều nơi cấu hình: hạ tầng chung của ứng dụng, annotation **@CacheConfig** trên lớp và thuộc tính trực tiếp của **@Cacheable**, **@CachePut**, **@CacheEvict** trên từng phương thức. Khi cùng một lựa chọn được khai báo ở nhiều cấp, cần xác định **cấu hình cuối cùng của cache operation** chứ không chỉ nhìn một annotation.

Sau bài này, bạn sẽ:
1. Giải thích thứ tự ưu tiên **toàn cục → lớp → phương thức** và lý do *cấp gần operation hơn có quyền ghi đè mặc định*.
2. Xác định chính xác **cacheNames**, **key/keyGenerator** và **cacheManager/cacheResolver** có hiệu lực đối với mỗi lời gọi.
3. Phân biệt **ghi đè một thuộc tính** với **thay thế toàn bộ cấu hình lớp**, và phân biệt **override hợp lệ** với cặp thuộc tính loại trừ nhau trên cùng operation.
4. Hiểu vai trò của **@EnableCaching**, **CachingConfigurer**, **@CacheConfig** và những gì thuộc về cache provider.
5. Chạy ví dụ Java 17 + Maven để thấy cache hit/miss khác nhau khi chuyển từ global sang class rồi method.

Phạm vi: Spring Framework Cache Abstraction, dùng annotation-driven caching với proxy mặc định. Ví dụ chọn Spring Framework 6.2.x (Java 17+), không phụ thuộc Spring Boot, Redis hay Caffeine. Nếu dùng Spring Boot, lớp auto-configuration có thể dựng hạ tầng, nhưng **không đảo ngược quy tắc ưu tiên** của các cache annotation.

## 1. Bức tranh ba tầng

~~~text
    TẦNG TOÀN CỤC (global infrastructure defaults)
    @EnableCaching + CachingConfigurer / hạ tầng CacheManager,
    CacheResolver, KeyGenerator mặc định
                   |
                   v
    TẦNG LỚP (class defaults)
    @CacheConfig(cacheNames=..., keyGenerator=...,
                 cacheManager=..., cacheResolver=...)
                   |
                   v
    TẦNG PHƯƠNG THỨC (operation customization)
    @Cacheable(...), @CachePut(...), @CacheEvict(...)
    cacheNames, key/keyGenerator, cacheManager/cacheResolver ...
                   |
                   v
         Cache operation thực tế
         -> chọn nơi lưu -> tính key -> đọc/ghi/xóa
~~~

Quy tắc tổng quát: **mặc định toàn cục áp dụng nếu một thiết lập cụ thể chưa được chọn ở cấp lớp hay phương thức; @CacheConfig cung cấp mặc định cho các operation trong lớp; khai báo trực tiếp trên operation được ưu tiên cao nhất**.

Đây không phải cơ chế "gộp ba cấu hình thành một chuỗi", cũng không phải "annotation trên class tự tạo cache entry". Spring xây dựng cấu hình có hiệu lực **cho từng cache operation** từ các thuộc tính đã khai báo và những mặc định còn thiếu.

Ví dụ:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable
    public String find(String id) {
        return load(id);
    }

    @Cacheable(cacheNames = "premiumProducts")
    public String findPremium(String id) {
        return loadPremium(id);
    }
}
~~~

Đây là đoạn minh họa cần có import, lớp và các method load do ứng dụng cung cấp. Kết quả lựa chọn:
- **find** không khai báo cacheNames riêng → kế thừa **products** từ @CacheConfig.
- **findPremium** có cacheNames ở method → dùng **premiumProducts**, **không tự cộng thêm products**.
- Phải có @EnableCaching và lời gọi đi qua Spring cache interceptor thì annotation mới tác động đến cache.

Một cache operation còn có thể có điều kiện SpEL, key cụ thể hoặc chính sách riêng. **@CacheConfig chỉ cho mặc định bốn nhóm thuộc tính được nó hỗ trợ**, không phải toàn bộ thuộc tính của @Cacheable hay @CachePut.

## 2. Tầng toàn cục: hạ tầng được dùng khi chưa có override

Trong Spring, hạ tầng chung quyết định:
- **CacheManager** nào quản lý các cache.
- **CacheResolver** nào xác định tập cache cho một operation.
- **KeyGenerator** mặc định tạo key khi operation không có SpEL key hoặc generator cụ thể.
- **CacheErrorHandler** xử lý lỗi cache; đây cũng là một tùy biến hạ tầng nhưng không có thuộc tính tương ứng trên @CacheConfig.
- Proxy/cơ chế AOP cho phép interception khi annotation caching được bật.

Cấu hình tối thiểu:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructure {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "prices");
    }
}
~~~

Đoạn minh họa không độc lập vì chưa ghi đầy đủ import và các service; nó định nghĩa một cache manager in-memory. Khi không có tùy biến khác, Spring thường dùng **SimpleKeyGenerator** và một **SimpleCacheResolver** dựa trên CacheManager mặc định. Mặc định hạ tầng không tự chỉ định cache name cụ thể cho **mọi** operation; tên cache cần có từ operation/@CacheConfig hoặc được CacheResolver tùy biến quyết định.

### Tùy biến mặc định bằng CachingConfigurer

Một cách khai báo chính thức cho annotation-driven caching là implement **org.springframework.cache.annotation.CachingConfigurer** trong @Configuration:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructure implements CachingConfigurer {
    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return (target, method, params) ->
            "GLOBAL:" + String.valueOf(params[0]);
    }
}
~~~

Đây là ví dụ định hướng, chưa gồm import. Dùng @Bean cho những phương thức cung cấp bean hạ tầng; nó cho phép Spring quản lý vòng đời. Generator ví dụ giả định operation có ít nhất một tham số; **không dùng nguyên xi cho method không tham số**. Trong project thực tế, nếu triển khai CachingConfigurer, cần tránh khởi tạo sớm các phụ thuộc phức tạp hoặc vòng phụ thuộc do hạ tầng caching được khởi tạo sớm.

Nếu một method không ghi key/keyGenerator và class không đặt keyGenerator mặc định, Spring sử dụng **global KeyGenerator** được cấu hình. Nếu class hay method đặt chiến lược riêng, chúng có thể thay thế generator mặc định cho operation đó.

**Không nhầm hai loại "toàn cục":**
- **Global của Spring Cache**: KeyGenerator và CacheManager/CacheResolver được cung cấp cho interceptor.
- **Thuộc tính Spring Boot/provider**: ví dụ cấu hình Redis, Caffeine, TTL, kích thước cache, cách serialize. Các giá trị đó tác động cách cache vận hành, **không biến thành thuộc tính @CacheConfig** và không tự quyết định cách override annotation method.

## 3. Tầng lớp: @CacheConfig là bộ mặc định dùng chung

Annotation **@CacheConfig** đặt trên một class và hỗ trợ đúng bốn nhóm chính:

| Thuộc tính của @CacheConfig | Vai trò |
| --- | --- |
| **cacheNames** | Tên cache mặc định cho các operation trong class |
| **keyGenerator** | Tên bean KeyGenerator mặc định của class |
| **cacheManager** | Tên bean CacheManager được dùng để xây default CacheResolver khi không có resolver hiệu lực |
| **cacheResolver** | Tên bean CacheResolver mặc định của class |

Ví dụ:

~~~java
@CacheConfig(
    cacheNames = "catalog",
    keyGenerator = "catalogKeyGenerator",
    cacheManager = "catalogManager"
)
public class CatalogService {

    @Cacheable
    public String get(String sku) {
        return load(sku);
    }
}
~~~

Đây là đoạn minh họa. Với **get**, Spring sử dụng cache **catalog**, bean **catalogKeyGenerator** và bean **catalogManager** nếu không có thiết lập ghi đè trên chính operation. Các bean theo tên đó phải thực sự tồn tại trong ApplicationContext, đúng kiểu.

**@CacheConfig không kích hoạt caching và không tạo operation.** Nếu chỉ có @CacheConfig trên class mà không có @Cacheable/@CachePut/@CacheEvict thích hợp, nó không tự ghi dữ liệu. @EnableCaching hoặc cơ chế tương đương phải kích hoạt infrastructure; lời gọi method còn phải đi qua proxy hoặc weaving phù hợp.

### Mặc định của lớp không áp dụng theo kiểu "copy nguyên khối"

Trong cùng CatalogService, một method có thể ghi đè **cacheNames**, method khác ghi đè **key**, và method khác không ghi đè gì. Mỗi operation được xử lý độc lập.

~~~java
// Các method minh họa trong class đã có @CacheConfig ở trên.
@Cacheable
public String a(String sku) { return load(sku); }

@Cacheable(cacheNames = "catalogDetails")
public String b(String sku) { return loadDetail(sku); }

@Cacheable(key = "#p0")
public String c(String sku) { return load(sku); }
~~~

- **a** dùng class cache name, class generator, class cache manager.
- **b** dùng **catalogDetails** từ method, nhưng nếu không đặt key/keyGenerator hay manager/resolver, vẫn kế thừa **catalogKeyGenerator** và **catalogManager** từ class.
- **c** dùng **SpEL #p0** thay cho class keyGenerator, trong khi **cacheNames=catalog** và **cacheManager=catalogManager** vẫn kế thừa.

Như vậy, một override **không xóa hết** mặc định khác trên class.

## 4. Tầng phương thức: cấu hình gần operation nhất được ưu tiên

Có ba nhóm quan trọng cần xét **riêng từng nhóm**, không dùng một luật chung mơ hồ.

### 4.1. cacheNames: method thay danh sách mặc định của class

~~~java
@CacheConfig(cacheNames = {"items", "lookup"})
public class ItemService {
    @Cacheable
    public String find(String id) { return fromStore(id); }

    @Cacheable(cacheNames = "oneOff")
    public String findSpecial(String id) { return fromSpecialStore(id); }
}
~~~

Cả hai method đều là ví dụ chưa độc lập. Trường hợp:
- **find** dùng tập cacheNames mặc định **items, lookup**.
- **findSpecial** dùng **oneOff**. Tập method không tự động được gộp với items/lookup.

Nếu muốn một method tra hai cache, khai báo rõ ngay tại method hoặc dùng class default có nhiều tên thích hợp. Lưu ý nhiều cache trên @Cacheable làm thay đổi semantics tra cứu/put và có thể gây khác biệt với provider bất đồng bộ; chỉ dùng khi hiểu rõ mục đích.

**Không có danh sách cacheNames toàn cục bắt buộc** được @CacheConfig thừa kế từ @EnableCaching. Khi dùng CacheResolver tùy chỉnh, tên cache có thể do resolver quyết định theo bối cảnh, nhưng đó là trách nhiệm của resolver chứ không phải tự động lấy tên từ class.

### 4.2. key và keyGenerator: chiến lược được chọn theo ưu tiên

**key** là biểu thức Spring Expression Language (SpEL) ngay trên operation. **keyGenerator** là tên bean Java triển khai KeyGenerator. Hai cách này có cùng mục đích tạo key nhưng cách viết khác nhau.

Thứ tự lựa chọn điển hình:

~~~text
Có key = "biểu thức SpEL" trên operation?
   Có -> dùng biểu thức SpEL
   Không -> có keyGenerator = "beanName" trên operation?
             Có -> dùng bean đó
             Không -> @CacheConfig có keyGenerator?
                       Có -> dùng bean cấp class
                       Không -> dùng KeyGenerator mặc định toàn cục
~~~

Nếu chưa tùy biến generator, mặc định là **SimpleKeyGenerator**. Với một tham số String bình thường, key mặc định thường là chính String đó; với nhiều tham số, Spring có SimpleKey bao các tham số. Một object nghiệp vụ làm key cần equals()/hashCode() hợp lệ, và trạng thái tham gia equality không nên thay đổi khi cache đang giữ entry.

Điểm hay gây nhầm:

~~~java
@CacheConfig(keyGenerator = "normalizedKeyGenerator")
public class ProductService {

    @Cacheable(cacheNames = "products", key = "#p0")
    public String findExact(String sku) {
        return load(sku);
    }
}
~~~

**Hợp lệ.** Dù class có default keyGenerator, method ghi rõ **key = "#p0"**; Spring **bỏ qua default keyGenerator của @CacheConfig** với operation này. Đây là **override giữa hai cấp**, không phải khai báo đồng thời hai chiến lược trên cùng operation.

Ngược lại:

~~~java
// SAI: cùng một cache operation khai báo cả hai khác rỗng.
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    keyGenerator = "normalizedKeyGenerator"
)
public String find(String sku) { return load(sku); }
~~~

**Không hợp lệ:** key và keyGenerator **mutually exclusive** ở operation level. Spring sẽ báo lỗi thay vì ưu tiên âm thầm một trong hai. Quy tắc "method ưu tiên class" không hợp thức hóa việc đặt **hai thuộc tính xung đột trên chính method**.

### 4.3. cacheManager và cacheResolver: chọn nơi cache được giải quyết

- **cacheManager**: tên bean CacheManager; theo cơ chế thông thường, Spring tạo/áp dụng một SimpleCacheResolver dựa trên manager đó.
- **cacheResolver**: tên bean CacheResolver; có thể quyết định tập cache động dựa vào operation và đối số.

Một operation **không được đồng thời cấu hình cả cacheManager và cacheResolver** dưới dạng hai lựa chọn khác rỗng. Tương tự key/keyGenerator, đây là hai cách điều hướng loại trừ nhau trên cùng operation.

Lược đồ ưu tiên hữu ích:

~~~text
Operation ghi cacheResolver? -> dùng resolver của operation
  nếu không, operation ghi cacheManager? -> dùng manager của operation
  nếu không, class có @CacheConfig.cacheResolver? -> dùng class resolver
  nếu không, class có @CacheConfig.cacheManager? -> dùng class manager
  nếu không -> dùng resolver/manager mặc định toàn cục
~~~

Lược đồ giả định cấu hình không mâu thuẫn ở cùng cấp. Cần nhớ **cacheResolver có quyền quyết định cache đích**; một số resolver tùy chỉnh thậm chí không cần cacheNames trên annotation. Nếu dùng SimpleCacheResolver, cacheNames có hiệu lực theo tên do operation cung cấp.

Ví dụ override chỉ manager:

~~~java
@CacheConfig(
    cacheNames = "profiles",
    keyGenerator = "profileKeys",
    cacheManager = "primaryManager"
)
public class ProfileService {

    @Cacheable(cacheManager = "secondaryManager")
    public String find(String userId) { return load(userId); }
}
~~~

Method **find** vẫn có cacheNames=profiles và keyGenerator=profileKeys, nhưng sử dụng **secondaryManager**, không phải primaryManager. Lưu ý secondaryManager phải có khả năng resolve cache **profiles**, nếu không operation có thể lỗi khi Spring tìm cache tương ứng.

### Bảng tổng hợp từng nhóm thuộc tính

| Nhóm thuộc tính | Mặc định toàn cục | @CacheConfig lớp | Annotation operation |
| --- | --- | --- | --- |
| **cacheNames** | Không có tên chung bắt buộc; tùy resolver | Danh sách tên mặc định | Danh sách ghi rõ tại method thay mặc định lớp |
| **key / keyGenerator** | SimpleKeyGenerator hoặc global custom | Bean keyGenerator mặc định | key SpEL hoặc keyGenerator bean ghi đè |
| **cacheManager / cacheResolver** | CacheManager/CacheResolver của infrastructure | Bean mặc định lớp | Bean được chỉ rõ tại method |
| **condition, unless** | Không dùng CachingConfigurer để đặt mặc định per operation | @CacheConfig không có các thuộc tính này | Đặt riêng tại @Cacheable/@CachePut/@CacheEvict theo khả năng của annotation |
| **sync (trên @Cacheable)** | Không phải thuộc tính @CacheConfig | Không được đặt tại lớp bằng @CacheConfig | Đặt tại operation và tuân thủ ràng buộc sync |

**Ưu tiên theo từng thuộc tính** là cách chính xác để hiểu bảng này. Nếu method chỉ sửa cacheNames, mọi thuộc tính còn thiếu tiếp tục thừa kế hoặc dùng global default tương ứng.

## 5. Ví dụ Java 17 + Spring Cache có thể chạy để kiểm chứng ba tầng

Dự án minh họa **ba nơi đặt rule**:
- **Global**: CachingConfigurer cung cấp CacheManager và KeyGenerator chuẩn hóa thành "G:SKU".
- **Class**: @CacheConfig thay đổi mặc định sang classManager, classKeyGenerator tạo "C:SKU" và cacheNames="classLookup".
- **Method**: một method đặt cacheNames, cacheManager và SpEL key riêng; một method chỉ đặt key để chứng minh **các thuộc tính class còn lại vẫn có hiệu lực**.

Các lời gọi dùng hai biến thể String " sku-7 " và "SKU-7". Generator global/class chuẩn hóa chúng về cùng khóa; SpEL **#p0** tại method giữ nguyên chuỗi thô nên coi là hai khóa khác nhau.

### Cấu trúc thư mục

~~~text
spring-cache-precedence/
├── pom.xml
└── src/main/java/demo/CachePrecedenceDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-precedence</artifactId>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/CachePrecedenceDemo.java

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class CachePrecedenceDemo {

    private static String normalize(String sku) {
        return sku.trim().toUpperCase(Locale.ROOT);
    }

    // Không có @CacheConfig: dùng global defaults.
    public static class GlobalService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "globalLookup")
        public String find(String sku) {
            return "global-load-" + loads.incrementAndGet();
        }
    }

    // Lớp có mặc định khác global.
    @CacheConfig(
        cacheNames = "classLookup",
        keyGenerator = "classKeyGenerator",
        cacheManager = "classManager"
    )
    public static class LayeredService {
        private final AtomicInteger classLoads = new AtomicInteger();
        private final AtomicInteger methodLoads = new AtomicInteger();
        private final AtomicInteger keyOnlyLoads = new AtomicInteger();

        // Không đặt thuộc tính nào -> nhận defaults từ @CacheConfig.
        @Cacheable
        public String fromClass(String sku) {
            return "class-load-" + classLoads.incrementAndGet();
        }

        // Đặt rõ cacheNames, cacheManager, key -> override tại method.
        @Cacheable(
            cacheNames = "methodLookup",
            cacheManager = "methodManager",
            key = "#p0"
        )
        public String fromMethod(String sku) {
            return "method-load-" + methodLoads.incrementAndGet();
        }

        // Chỉ ghi đè key; cacheNames và manager vẫn của @CacheConfig.
        @Cacheable(key = "#p0")
        public String keyOnlyOverride(String sku) {
            return "keyonly-load-" + keyOnlyLoads.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config implements CachingConfigurer {

        @Bean("globalManager")
        @Override
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("globalLookup");
        }

        @Bean("globalKeyGenerator")
        @Override
        public KeyGenerator keyGenerator() {
            return (target, method, params) ->
                "G:" + normalize((String) params[0]);
        }

        @Bean("classManager")
        public CacheManager classManager() {
            return new ConcurrentMapCacheManager("classLookup");
        }

        @Bean("methodManager")
        public CacheManager methodManager() {
            return new ConcurrentMapCacheManager("methodLookup");
        }

        @Bean("classKeyGenerator")
        public KeyGenerator classKeyGenerator() {
            return (target, method, params) ->
                "C:" + normalize((String) params[0]);
        }

        @Bean
        public GlobalService globalService() {
            return new GlobalService();
        }

        @Bean
        public LayeredService layeredService() {
            return new LayeredService();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            GlobalService global = ctx.getBean(GlobalService.class);
            LayeredService layered = ctx.getBean(LayeredService.class);

            System.out.println(global.find(" sku-7 "));
            System.out.println(global.find("SKU-7"));

            System.out.println(layered.fromClass(" sku-7 "));
            System.out.println(layered.fromClass("SKU-7"));

            System.out.println(layered.fromMethod(" sku-7 "));
            System.out.println(layered.fromMethod("SKU-7"));

            System.out.println(layered.keyOnlyOverride(" sku-7 "));
            System.out.println(layered.keyOnlyOverride(" sku-7 "));
            System.out.println(layered.keyOnlyOverride("SKU-7"));

            CacheManager gm = ctx.getBean(
                "globalManager", CacheManager.class);
            CacheManager cm = ctx.getBean(
                "classManager", CacheManager.class);
            CacheManager mm = ctx.getBean(
                "methodManager", CacheManager.class);

            System.out.println("global-key="
                + gm.getCache("globalLookup").get("G:SKU-7", String.class));
            System.out.println("class-key="
                + cm.getCache("classLookup").get("C:SKU-7", String.class));
            System.out.println("method-key="
                + mm.getCache("methodLookup").get("SKU-7", String.class));
            System.out.println("class-raw-key="
                + cm.getCache("classLookup").get("SKU-7", String.class));
        }
    }
}
~~~

### Chạy chương trình

Yêu cầu JDK 17+ và Maven đã cài đặt. Trong thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CachePrecedenceDemo
~~~

**Stdout do các lệnh println của demo tạo ra** (bỏ qua log riêng của Maven hay thư viện):

~~~text
global-load-1
global-load-1
class-load-1
class-load-1
method-load-1
method-load-2
keyonly-load-1
keyonly-load-1
keyonly-load-2
global-key=global-load-1
class-key=class-load-1
method-key=method-load-2
class-raw-key=keyonly-load-2
~~~

Lý giải chính xác theo từng nhóm:

1. **GlobalService.find** chỉ ghi cacheNames. Vì không có @CacheConfig hoặc key ở method, interceptor dùng global KeyGenerator. Hai SKU trở thành cùng **"G:SKU-7"**, lời gọi thứ hai hit, output "global-load-1".
2. **LayeredService.fromClass** không ghi cấu hình operation riêng. Nó lấy **cacheNames=classLookup**, **classManager**, **classKeyGenerator** từ @CacheConfig. Hai biến thể SKU thành cùng **"C:SKU-7"**, output "class-load-1" cả hai.
3. **LayeredService.fromMethod** khai báo rõ **methodLookup**, **methodManager** và SpEL **#p0**. Với hai String không equals nhau, phương thức thật chạy hai lần, output "method-load-1" và "method-load-2". Nó không dùng classKeyGenerator.
4. **LayeredService.keyOnlyOverride** chỉ đặt **key = "#p0"**, do đó cache name và manager **vẫn lấy từ class**. Hai lần cùng chuỗi " sku-7 " hit cùng entry; lần "SKU-7" dùng key khác và chạy lần hai.
5. Ba dòng **global-key**, **class-key**, **method-key** kiểm tra trực tiếp entry được lưu trong đúng cache manager đã dự kiến. Dòng cuối **class-raw-key** chứng minh method chỉ override key nhưng vẫn ghi vào classManager.

Trong demo, ConcurrentMapCacheManager được khởi tạo với danh sách cache tên cố định ở mỗi manager, tránh mơ hồ: **globalLookup**, **classLookup** và **methodLookup** không phải ba tên trên cùng một manager. Vì vậy, khác biệt manager được kiểm chứng bằng getCache đúng bean và key đúng.

**Giới hạn ví dụ:** Đây là cache trong bộ nhớ của một tiến trình Java; không mô phỏng transaction, TTL, dữ liệu phân tán hoặc serialization. Các chuỗi demo được dùng để đếm số lần chạy method thật. Chương trình giả định các hàm được gọi qua Spring proxy bằng bean lấy từ AnnotationConfigApplicationContext, không dùng self-invocation.

## 6. Đọc một cấu hình thực tế theo từng thuộc tính

Đặt giả thiết ứng dụng có global KeyGenerator **globalKeys** và global CacheManager **globalManager**. Class áp dụng:

~~~java
@CacheConfig(
    cacheNames = "orders",
    keyGenerator = "orderKeys",
    cacheManager = "orderManager"
)
public class OrderService {
    @Cacheable
    public String get(String orderId) { return fromStore(orderId); }

    @Cacheable(key = "#p0")
    public String getExact(String orderId) {
        return fromStore(orderId);
    }

    @CachePut(cacheNames = "orderSnapshots")
    public String save(String orderId) { return updateStore(orderId); }

    @CacheEvict(key = "#p0", cacheManager = "archiveManager")
    public void invalidateArchive(String orderId) {
        updateArchiveIndex(orderId);
    }
}
~~~

Đây là class minh họa, không chạy độc lập (thiếu imports và các phương thức nghiệp vụ). Không dùng nó như một thiết kế hoàn chỉnh: bốn operation có thể đụng key hoặc stale data nếu không có quy ước rõ. Mục tiêu là **tính ra cấu hình hiệu lực**:

| Operation | cacheNames | Cách tạo key | Cache manager/resolver |
| --- | --- | --- | --- |
| get | orders (class) | orderKeys (class) | orderManager (class) |
| getExact | orders (class) | SpEL #p0 (method) | orderManager (class) |
| save | orderSnapshots (method) | orderKeys (class) | orderManager (class) |
| invalidateArchive | orders (class) | SpEL #p0 (method) | archiveManager (method) |

Đặc biệt, **save** ghi một cache name mới nhưng **không đổi class manager**. Để chạy được, bean orderManager phải resolve được cả orders **và orderSnapshots**. **invalidateArchive** chọn archiveManager nhưng vẫn dùng cacheNames=orders từ class; bean archiveManager phải chứa cache orders, hoặc có chính sách tạo cache động phù hợp. Nếu thiếu, lỗi thường đến từ resolver/manager chứ không liên quan thứ tự ưu tiên.

Nếu muốn các operation đọc/ghi/xóa cùng một entry, phải bảo đảm **cache name, manager/resolver và key logic cùng khớp**, thay vì chỉ dựa vào việc chúng cùng nằm trong một class.

## 7. Không phải mọi thuộc tính đều có ba cấp tùy biến

Một điểm quan trọng của kiến trúc annotation: **@CacheConfig không có condition, unless, sync, beforeInvocation, allEntries**. Vì thế, không có khái niệm @CacheConfig.class.condition hay "global condition" tự động thừa kế cho mọi @Cacheable.

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "prices",
    condition = "#p1",
    unless = "#result == null"
)
public String price(String sku, boolean allowCaching) {
    return loadPrice(sku);
}
~~~

Đây là method minh họa. condition và unless chỉ thuộc operation theo quy tắc của annotation đó. Mặc định class **không tự lấp** condition hay unless khi method bỏ trống. Muốn áp dụng một chính sách điều kiện xuyên nhiều method, cần giải pháp thiết kế khác (ví dụ annotation tổng hợp được tạo đúng cách và test), chứ không đưa condition vào @CacheConfig.

### @CacheConfig không xử lý cấu hình provider

Các ví dụ sau thuộc **cache implementation**, không thuộc cơ chế override annotation:
- TTL hoặc time-to-idle của từng cache.
- Giới hạn số entry / chiến lược eviction của Caffeine.
- Serializer, prefix và TTL cho Redis.
- Transaction awareness của CacheManager.
- Chính sách null value hoặc cách đặt tên namespace trong hệ thống phân tán.

Chẳng hạn method có **@Cacheable(cacheNames = "shortTtl")** sẽ chọn cache mang tên shortTtl. Nhưng method **không mặc nhiên "override TTL"** từ annotation này; TTL phải được cấu hình trong provider/cache manager tương ứng. Đổi tên cache có thể làm method chọn một cache có TTL khác, song bản thân annotation không mang thuộc tính ttl.

## 8. Xung đột khác với override hợp lệ

Bảng so sánh để tránh nhầm:

| Cấu hình | Kết luận |
| --- | --- |
| Global keyGenerator + @CacheConfig(keyGenerator="classKeys") | Hợp lệ; class override mặc định global |
| Class keyGenerator="classKeys" + method key="#p0" | Hợp lệ; method dùng SpEL thay class generator |
| Class cacheManager="classManager" + method cacheManager="methodManager" | Hợp lệ; method dùng manager chỉ định |
| Class cacheNames={"a","b"} + method cacheNames="c" | Hợp lệ; method thay danh sách class bằng c |
| Method key="#p0", keyGenerator="classKeys" | **Sai:** xung đột ngay trên operation |
| Method cacheManager="x", cacheResolver="y" | **Sai:** xung đột ngay trên operation |
| Method keyGenerator="missingBean" | **Sai cấu hình tại runtime:** bean không tồn tại/không đúng kiểu |
| Chỉ có @CacheConfig mà không có operation | Không có cache operation tự động |
| Annotation có nhưng không có @EnableCaching và không được cấu hình tương đương | Không có caching interceptor như kỳ vọng |
| @Cacheable gọi từ method khác trong cùng instance | Thường không được proxy intercept trong proxy mode mặc định |

**Lưu ý về xung đột class-level:** Nếu cấu hình class đặt một cacheResolver tùy chỉnh và method chọn cacheManager cụ thể, theo nguyên tắc operation customization, lựa chọn method được ưu tiên; tuy vậy nên giữ thiết kế rõ ràng, tránh khai báo đồng thời các lựa chọn loại trừ nhau **ngay tại một operation**. Khi tự viết CacheResolver động, xác nhận cách nó xử lý cacheNames.

### Không nên tìm "một thứ tự ưu tiên duy nhất" cho mọi trường hợp

Ví dụ "method ghi cacheNames mới" chỉ chọn tên cache, không có nghĩa method đã thay tất cả key/manager. Trái lại "method đặt key" làm **class keyGenerator bị bỏ qua** vì chúng là hai chiến lược loại trừ nhau của **cùng nhóm tạo khóa**. Khi debug, phải xét **nhóm thuộc tính** và **operation**, không chỉ cấp nào xuất hiện cuối trong file Java.

## 9. Cách xác định cấu hình có hiệu lực khi debug

Đối với một cache operation bất kỳ, làm lần lượt:

1. **Xác định operation thực sự:** @Cacheable, @CachePut hay @CacheEvict trên method nào? Có nhiều operation gom bằng @Caching hoặc annotation tổng hợp không? Cơ chế thực thi của mỗi operation có thể khác nhau.
2. **Xác định cacheNames:** method có khai báo không? Nếu không, @CacheConfig có cung cấp không? Nếu không, resolver có thể quyết định tên cache thế nào?
3. **Xác định cơ chế tạo key:** method có key SpEL không? Nếu không, keyGenerator method/class/global nào được áp dụng? Đầu vào đã được chuẩn hóa như thế nào?
4. **Xác định nơi lưu:** method có cacheManager/cacheResolver không? Nếu không, class chọn gì? Nếu class không chọn thì global resolver/manager nào đang hiệu lực?
5. **Kiểm tra bean theo tên:** keyGenerator, cacheManager, cacheResolver là **tên bean trong container**. Tên viết đúng nhưng bean không nằm trong context hoặc sai kiểu thì operation không thể chạy đúng.
6. **Kiểm tra proxy:** bean có thực sự được container quản lý và lời gọi từ bên ngoài đi qua proxy không? Nếu tự new service hoặc self-invocation, annotation có thể không thực thi.
7. **Quan sát behavior:** ghi log method thật, cấu hình cache, key và kết quả hit/miss ở một số cặp input. Không suy luận hit/miss từ tên annotation.
8. **So sánh các operation có liên quan:** @CachePut hoặc @CacheEvict có cùng manager, cacheName và chiến lược key với @Cacheable không?

Một kỹ thuật hữu ích: với ví dụ đang chạy trong môi trường thử nghiệm, đọc entry từ cache đúng bean CacheManager bằng **getCache(cacheName).get(key)**. Trong hệ thống thật, chỉ log khóa/metadata **đã được khử thông tin nhạy cảm**, tránh đưa token, userId nhạy cảm hoặc dữ liệu mật vào log.

### Phân biệt chồng lớp và bean visibility

Khi ứng dụng có nhiều ApplicationContext (ví dụ root/child context), bean @EnableCaching và service annotated cần được cấu hình ở context phù hợp. Một keyGenerator nằm ở context khác hoặc bị che khuất bởi bean cùng tên có thể khiến hành vi khác dự kiến. Các thuộc tính "ưu tiên" không vượt qua quy tắc resolve bean và phạm vi ApplicationContext. Nếu dùng Spring Boot, hãy kiểm tra bean do auto-configuration tạo ra khi có nhiều CacheManager/KeyGenerator, không đoán rằng "bean đặt tên cacheManager" luôn thắng mọi cấu hình CachingConfigurer explicit.

## 10. Tình huống thực tế: thay đổi cấu hình nhưng phát sinh cache miss

### Tình huống A: Global key chuẩn hóa, method chuyển sang key thô

Hạ tầng global trước kia tạo key **"SKU-7"**. Một method mới khai báo **key="#p0"** trong khi tham số có thể là " sku-7 ". Dù cùng cacheName, method dùng key String thô và miss entry cũ.

Giải pháp: thống nhất chuẩn hóa ở mọi operation, sử dụng SpEL chuẩn hóa có chủ đích hoặc một KeyGenerator chung. Đừng chỉ sửa method find mà quên @CacheEvict.

### Tình huống B: Class manager ghi cache local, một method đổi sang Redis

Class dùng localManager, nhưng method chỉ định redisManager. Cùng cacheNames và cùng key logic **vẫn là hai kho khác nhau**. Người gọi method theo cấu hình cũ không đọc được entry trên manager mới. Nếu thay đổi môi trường production, cần một chiến lược migration/warmup/invalidation thích hợp.

### Tình huống C: Method đổi cacheNames nhưng class manager không có cache đó

Class @CacheConfig(cacheManager="fixedManager", cacheNames="known") dùng manager với tập cache tĩnh. Method ghi cacheNames="newName". Vì method **không đổi manager**, fixedManager vẫn được dùng và có thể không tìm ra cache newName. Đây là lỗi tương thích giữa **tên cache hiệu lực** và **manager hiệu lực**, không phải lỗi Spring bỏ qua thứ tự ưu tiên.

### Tình huống D: Tưởng @CacheConfig tự bật cache

Lớp có @CacheConfig và @Cacheable nhưng không có hạ tầng caching annotation, hoặc service được khởi tạo bằng new và không đi qua proxy. Method chạy mỗi lần, không phải do chọn sai cấp keyGenerator. Khắc phục: kích hoạt @EnableCaching và lấy bean từ container; tránh self-invocation trong proxy mode.

### Tình huống E: @CachePut và @CacheEvict không thống nhất override

Một phương thức đọc dùng cacheName lớp **products** và keyGenerator lớp; một phương thức cập nhật ghi cacheName mới **productsV2** và key SpEL riêng. Tưởng chúng cập nhật/xóa cùng cache nhưng thực tế nằm ở hai entry hoặc hai cache khác nhau. Cần lập bảng từng operation theo ba nhóm: cacheName, key, manager/resolver; bảo đảm chúng cùng một danh tính cache khi nghiệp vụ cần.

## 11. Kiểm thử và checklist review cấu hình

| Bài kiểm tra | Kết quả mong đợi |
| --- | --- |
| Class không có @CacheConfig, operation không custom key | Global KeyGenerator được dùng |
| Class có @CacheConfig(keyGenerator="classKeys"), operation bỏ trống | Class generator được dùng |
| Method trong class trên đặt key="#p0" | Method SpEL thắng class generator |
| Method chỉ đổi cacheNames | KeyGenerator và manager từ class tiếp tục có hiệu lực |
| Method chỉ đổi cacheManager | key/cacheNames từ class còn hiệu lực |
| Method có key và keyGenerator đều khác rỗng | Bị từ chối; không im lặng chọn một |
| Method có cacheManager và cacheResolver đều khác rỗng | Bị từ chối; không im lặng chọn một |
| CacheName mới không tồn tại trong manager tĩnh | Có thể lỗi resolve cache, phải bổ sung cache hoặc đổi manager |
| Method có @Cacheable được gọi qua Spring proxy | Có thể quan sát hit/miss thực tế |
| @CacheConfig đơn độc, không có @Cacheable/@CachePut/@CacheEvict | Không có hành động cache tự động |

Nếu có nhiều service, nên viết **integration test** dùng ApplicationContext để xác minh từng operation. Unit test KeyGenerator chỉ kiểm tra thuật toán tạo key, **không chứng minh Spring đang chọn đúng generator đó theo thứ tự ưu tiên**. Muốn khẳng định lựa chọn thực sự, phải gọi bean đã được proxy và/hoặc quan sát entry đúng CacheManager.

Nên bổ sung test cho các trường hợp phương thức đọc và cập nhật cùng dữ liệu: trong một ứng dụng, **nhất quán giữa read/write/evict** quan trọng không kém việc từng method hoạt động đúng đơn lẻ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Global KeyGenerator là globalKeys, lớp đặt @CacheConfig(keyGenerator="classKeys") và method đặt @Cacheable(cacheNames="products"). KeyGenerator nào dùng?

**Đáp:** **classKeys**; vì method không đặt key hay keyGenerator riêng, và class override mặc định global.

**Câu 2.** Lớp đặt @CacheConfig(keyGenerator="classKeys"), method đặt @Cacheable(key="#p0"). Có bị lỗi khai báo hai chiến lược key không?

**Đáp:** **Không**. Method dùng key SpEL; classKeyGenerator chỉ là mặc định và bị bỏ qua đối với operation này. Xung đột thực sự là đặt cả **key** và **keyGenerator** khác rỗng trực tiếp trên **cùng operation**.

**Câu 3.** Lớp đặt cacheNames={"a","b"}, method đặt cacheNames="c". Có tra cả ba cache không?

**Đáp:** **Không tự động**. Danh sách method **c** thay mặc định lớp cho operation này.

**Câu 4.** Lớp chọn classManager và classKeys, method chỉ chọn cacheManager="otherManager". Key nào được tạo?

**Đáp:** Vẫn dùng **classKeys** nếu không có key SpEL hay keyGenerator khác ở method. Chỉ manager bị thay đổi.

**Câu 5.** Method khai báo cacheManager="x", cacheResolver="y" đồng thời. Có phải Spring chọn một theo thứ tự ưu tiên?

**Đáp:** **Không**. Đây là hai lựa chọn loại trừ nhau trên một cache operation; cấu hình không hợp lệ.

**Câu 6.** Lớp có @CacheConfig(cacheNames="orders") nhưng không có @Cacheable hoặc annotation cache operation khác. Có tự lưu dữ liệu không?

**Đáp:** **Không**. @CacheConfig chỉ thiết lập mặc định; cần operation cụ thể và hạ tầng cache annotation được kích hoạt.

**Câu 7.** Một method đổi cacheName từ "orders" sang "orderPreview" nhưng không đổi cacheManager. Đã chắc chắn hoạt động chưa?

**Đáp:** **Chưa**. Manager hoặc resolver vẫn phải resolve được cache có tên **orderPreview**; nếu không, sẽ có lỗi cache resolution.

## Tổng kết

- Thứ tự tùy biến mặc định là **global < @CacheConfig lớp < annotation operation**, xét **theo từng nhóm thuộc tính**.
- **@CacheConfig** có bốn nhóm mặc định: **cacheNames**, **keyGenerator**, **cacheManager**, **cacheResolver**; nó **không tự bật caching**.
- Một method đặt **key SpEL** có thể ghi đè **keyGenerator mặc định cấp lớp** một cách hợp lệ. Nhưng đặt **key và keyGenerator cùng trên operation** là sai; **cacheManager và cacheResolver cùng trên operation** cũng sai.
- Khi method chỉ override một thứ, các mặc định khác của class/global vẫn có thể được áp dụng; **đừng coi override là xóa sạch mọi cấu hình lớp**.
- Muốn debug chính xác, luôn xác định **cache name thực tế, key thực tế, resolver/manager thực tế và đường đi qua Spring proxy**.
- Dù ưu tiên cấu hình chính xác, dữ liệu cache vẫn có thể sai nếu **các operation đọc, ghi và xóa không thống nhất nơi lưu cùng quy tắc key**.

### Tài liệu tham khảo chính thức

- Spring Framework 6.2 – Annotation-driven caching và thứ tự cấu hình: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework – @CacheConfig API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework – CachingConfigurer API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Framework – @EnableCaching API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework – CacheResolver API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html

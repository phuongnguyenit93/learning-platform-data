# Giới hạn sử dụng cache trong constructor hoặc @PostConstruct

## 1. Vấn đề cần hiểu

Trong Spring Framework, thêm `@Cacheable` vào một phương thức **không** làm mọi lời gọi tới phương thức đó tự động được cache. Với chế độ **Spring AOP proxy** mặc định, lời gọi phải đi **qua Spring-managed proxy** để `CacheInterceptor` có cơ hội tra cache, quyết định hit/miss và lưu kết quả.

Điều này đặc biệt quan trọng ở hai thời điểm:

1. **Trong constructor:** đối tượng đang được tạo, chưa hoàn thành dependency injection/khởi tạo và chưa sẵn sàng để các lời gọi đi qua proxy cache cuối cùng.
2. **Trong `@PostConstruct` của chính bean:** callback khởi tạo thường chạy trên bean đích trước khi bean được hoàn tất quá trình post-processing/proxying; một lời gọi `this.load(...)` vẫn là **self-invocation**, không đi qua proxy.

Vì vậy, việc gọi một phương thức có `@Cacheable` từ constructor hoặc từ `@PostConstruct` cùng bean **không phải cách đáng tin cậy để làm nóng cache**. Đoạn code vẫn có thể thực thi nghiệp vụ và trả về kết quả, khiến chương trình tưởng như hoạt động, nhưng cơ chế cache không được kích hoạt.

**Thông điệp chính:** *Có annotation* không đồng nghĩa *lời gọi đã được intercept*. Muốn dùng cache annotation trong giai đoạn khởi động, hãy tổ chức **một bean khác gọi bean đã được proxy đầy đủ ở thời điểm phù hợp**, hoặc sử dụng `CacheManager`/`Cache` trực tiếp khi cần nạp cache có chủ đích.

### Kết quả học tập

Sau bài này, bạn có thể:

- Mô tả thời điểm constructor, dependency injection, `@PostConstruct` và AOP proxy tham gia vào vòng đời Spring bean.
- Giải thích vì sao cache miss lặp lại trong constructor/`@PostConstruct` dù phương thức có `@Cacheable`.
- Phân biệt lời gọi nội bộ `this.cachedMethod()` với lời gọi từ bean khác thông qua Spring proxy.
- Xác định các rủi ro tương tự với `@CachePut` và `@CacheEvict`.
- Áp dụng giải pháp khởi động an toàn bằng `SmartInitializingSingleton`, Spring Boot `ApplicationRunner` hoặc gọi qua bean khác sau khi bean đích sẵn sàng.
- Kiểm chứng bằng demo Java 17 đầy đủ, không nhầm số lần thực thi thân phương thức với số lần lấy kết quả.

## 2. Nền tảng: @Cacheable thực sự hoạt động như thế nào?

Giả sử có:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String code) {
    return repository.load(code);
}
~~~

Đây là snippet minh họa; `repository` cần được định nghĩa bởi ứng dụng.

Khi một caller gọi `find("A")` **qua proxy**, Spring Cache thực hiện logic tương đương:

~~~text
Caller
  |
  v
Spring proxy -> CacheInterceptor
                     |
                     v
          Resolve Cache("catalog")
                     |
                     v
                 key = "A"
                     |
                     v
            Cache.get("A")
               /       \
             HIT       MISS
              |          |
              v          v
         Trả kết quả  Chạy find("A") trên target
                         |
                         v
                Cache.put("A", result)
                         |
                         v
                    Trả kết quả
~~~

Với cùng một key và entry chưa hết hạn, hai lời gọi liên tiếp thường tạo dấu vết:

~~~text
find("A") lần 1 -> MISS -> chạy repository.load -> lưu kết quả
find("A") lần 2 -> HIT  -> KHÔNG chạy repository.load
~~~

Tuy nhiên, nếu code gọi trực tiếp phương thức trên **target**:

~~~text
target.find("A")
     |
     v
Chạy thẳng thân find("A")
Không qua CacheInterceptor
Không tra Cache.get và không Cache.put
~~~

Lúc này không nên gọi đây là một *cache miss* đúng nghĩa: **cache lookup chưa hề xảy ra**. Đó là **bypass advice**. Việc thân phương thức chạy không chứng minh Spring đã thử tra cache.

Cơ chế này áp dụng cho proxy mode thông dụng của `@EnableCaching`. AspectJ weaving là một cơ chế khác, có thể xử lý một số giới hạn self-invocation, nhưng **không biến constructor và vòng đời bean chưa hoàn tất thành môi trường khởi tạo cache an toàn**.

## 3. Vòng đời bean: vì sao thời điểm khởi tạo lại quan trọng?

Một mô hình đơn giản hóa với singleton bean và các BeanPostProcessor thông dụng:

~~~text
Spring tạo bean
    |
    v
[1] Constructor
    |
    v
[2] Gán dependency / property
    |
    v
[3] BeanPostProcessor trước initialization
    |       |
    |       +-- xử lý @PostConstruct (nếu được đăng ký)
    v
[4] InitializingBean / init-method (nếu có)
    |
    v
[5] BeanPostProcessor sau initialization
    |       |
    |       +-- có thể tạo AOP proxy cho bean
    v
[6] Bean sẵn sàng trong container với proxy hoàn chỉnh
    |
    v
[7] Hoàn tất quá trình tạo các singleton thông thường
    |
    v
[8] SmartInitializingSingleton.afterSingletonsInstantiated()
    |
    v
Các giai đoạn sự kiện/khởi động cao hơn
(ví dụ ContextRefreshedEvent; ApplicationRunner trong Spring Boot)
~~~

Sơ đồ này diễn đạt **quy trình phổ biến**, không phải một lời khẳng định rằng mọi BeanPostProcessor hoặc proxy đều có đúng một thứ tự duy nhất trong mọi cấu hình nâng cao. Với Spring AOP proxy mode, điều cần nhớ là Spring khuyến nghị **không dựa vào các cache annotation trong initialization code như `@PostConstruct`**, vì proxy phải được khởi tạo đầy đủ.

### Điều gì đã tồn tại ở từng thời điểm?

| Thời điểm | Trạng thái quan trọng | Có nên trông chờ @Cacheable từ chính bean? |
| --- | --- | --- |
| Constructor | Đối tượng đang xây dựng; dependency qua field/setter có thể chưa inject | **Không** |
| `@PostConstruct` | Dependency của bean thông thường đã được inject, nhưng bean còn trong quy trình initialize/proxy | **Không** nếu tự gọi method của chính nó |
| Sau khi singleton bean đã được proxy và được lấy từ context | Caller bên ngoài có thể đi qua proxy | **Có**, nếu đáp ứng cấu hình AOP/caching |
| `SmartInitializingSingleton` ở **bean khởi động riêng** | Các singleton thường đã được tạo | **Có thể**, khi gọi một bean cộng tác đã được proxy |
| Spring Boot `ApplicationRunner` gọi service qua bean injected | Context Boot đã hoàn thành khởi tạo tương ứng | **Có thể**, với bean được proxy và lời gọi qua proxy |

**Không đánh đồng “dependency đã inject” với “proxy của chính bean đã hoàn thành”.** `@PostConstruct` là một lifecycle callback, không phải tín hiệu rằng mọi advice của chính bean sẽ được áp dụng cho các lời gọi nội bộ.

## 4. Giới hạn trong constructor

### 4.1. Một phương thức @Cacheable được gọi từ constructor

Ví dụ:

~~~java
public class CatalogService {
    public CatalogService() {
        String value = find("A"); // lời gọi nội bộ trong constructor
        System.out.println(value);
    }

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String code) {
        return "item-" + code;
    }
}
~~~

Đây là snippet minh họa, **không phải mẫu thiết kế nên dùng**. Lời gọi `find("A")` từ constructor gọi trực tiếp một phương thức trên object đang được tạo; proxy cuối cùng chưa tham gia. Annotation không làm lookup/put cache cho lời gọi này.

### 4.2. Các rủi ro không chỉ liên quan đến cache

Trong constructor của một Java object:

- Các field được gán bởi constructor injection có thể đã có khi đến phần thân constructor, nhưng **field injection / setter injection** do Spring thực hiện thường chưa xong.
- Gọi phương thức có thể override từ constructor là một anti-pattern Java: hành vi của subclass có thể chạy trước khi subclass được khởi tạo đầy đủ.
- Một phương thức chạm vào database, network hoặc cache ở thời điểm này có thể thất bại vì dependency, tài nguyên hoặc transaction chưa sẵn sàng.
- Thay đổi thứ tự khởi tạo bean hoặc cấu hình proxy có thể làm bug xuất hiện/tạm biến mất.

**Khuyến nghị:** constructor nên tập trung thiết lập invariant và gán dependency. Không dùng constructor như nơi gọi method `@Cacheable` để pre-populate cache.

### 4.3. Trường hợp tự gọi hai lần

~~~text
constructor -> this.find("A") -> chạy thân phương thức
constructor -> this.find("A") -> chạy thân phương thức lần nữa
~~~

Hai lần trên không tạo cache hit chỉ vì annotation có mặt. Thay vì ghi được entry, chúng có thể tạo hai database query độc lập.

## 5. Giới hạn trong @PostConstruct

`@PostConstruct` đến từ `jakarta.annotation.PostConstruct` ở các phiên bản Spring hiện đại. Spring hỗ trợ nó qua `CommonAnnotationBeanPostProcessor`. Callback được gọi sau dependency injection cơ bản nhưng **trong pha khởi tạo của bean**.

### 5.1. Tình huống thường gặp

~~~java
public class CatalogService {
    @PostConstruct
    public void warmUp() {
        find("A");
        find("A");
    }

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String code) {
        return repository.load(code);
    }
}
~~~

Snippet minh họa, không độc lập vì thiếu `repository` và cấu hình Spring. Dù hàm `warmUp()` mang `@PostConstruct` và `find(...)` mang `@Cacheable`, lời gọi vẫn là:

~~~text
@PostConstruct trên target
       |
       v
this.find("A") -> target.find("A")
       |
       v
this.find("A") -> target.find("A")
       |
       v
Không đi qua proxy, không có hit/miss theo cache annotation
~~~

Việc method trả cùng một giá trị ở cả hai lần **không chứng minh** nó được cache. Phải quan sát số lần chạy thân method hoặc entry trong `CacheManager`.

### 5.2. Tự gắn @Cacheable lên phương thức @PostConstruct thì sao?

Một lifecycle callback được container gọi trong quá trình initialize, không tương đương một caller bên ngoài gọi qua proxy. Việc thêm cache annotation vào phương thức callback **không phải phương án đáng tin** để làm nó được advice. Hơn nữa, phương thức `@PostConstruct` thông thường trả `void`, nên `@Cacheable` không mang ý nghĩa dùng kết quả trả về để cache.

### 5.3. Phải phân biệt lời gọi trong cùng bean và lời gọi tới bean khác

Câu “`@PostConstruct` không bao giờ dùng được cache” là **quá rộng**.

Ví dụ một bean `StartupBean` có dependency là **một bean khác** `CatalogService`. Nếu `CatalogService` đã được khởi tạo và inject dưới dạng proxy đầy đủ, `StartupBean.@PostConstruct` gọi `catalogService.find("A")` **có thể đi qua proxy của CatalogService**. Tuy nhiên, đây là cấu trúc phụ thuộc vào thứ tự khởi tạo và không nên dựa vào một bootstrap phức tạp/circular dependency để đạt được caching.

Điểm cần phân biệt:

- `this.find(...)` trong `CatalogService.@PostConstruct`: **self-invocation**, bỏ qua proxy.
- `catalogService.find(...)` từ **một bean khác**, sau khi `CatalogService` đã được proxy: lời gọi **có thể** được cache.
- Cách ổn định hơn là đặt công việc warm-up ở một lifecycle hook **sau** giai đoạn dựng singleton thông thường, tách khỏi bean có method cần cache.

## 6. Các annotation cache khác cũng bị ảnh hưởng

Không chỉ có `@Cacheable`. Khi self-invocation bỏ qua proxy, cả các hoạt động cache khác cũng không chạy như mong đợi:

| Annotation | Nếu lời gọi đi qua proxy | Nếu gọi nội bộ trong constructor/@PostConstruct |
| --- | --- | --- |
| `@Cacheable` | Lookup key, hit hoặc miss; có thể put kết quả | Không chạy cache advice; thân method được gọi trực tiếp |
| `@CachePut` | Chạy method và put kết quả theo key | Thân method chạy nhưng không có put qua annotation |
| `@CacheEvict` | Chạy method và evict trước/sau theo cấu hình | Thân method chạy nhưng không có evict qua annotation |
| `@Caching` | Tổng hợp các operation cache | Các operation cũng không có hiệu lực nếu advice bị bypass |

Ví dụ:

~~~java
@PostConstruct
public void initialize() {
    invalidateOldCache(); // cùng bean: KHÔNG đảm bảo @CacheEvict chạy
}

@CacheEvict(cacheNames = "catalog", allEntries = true)
public void invalidateOldCache() {
    // không cần body
}
~~~

Đây là snippet minh họa. Nếu `@PostConstruct` gọi trực tiếp `invalidateOldCache()` trên chính đối tượng, việc xóa cache do annotation khai báo **không xảy ra**. Nếu thực sự cần xóa entry trong lúc khởi tạo, dùng một luồng khởi động phù hợp và có trách nhiệm rõ ràng; hoặc gọi API `Cache.clear()`/`Cache.evict(key)` trực tiếp sau khi xác định đúng cache.

Tương tự, một phương thức mang cả `@Transactional` và `@Cacheable` có thể bị bypass cả hai advice khi gọi nội bộ (tùy cấu hình AOP), nên không nên suy ra rằng Spring đã mở transaction hay tra cache chỉ vì annotation xuất hiện trong code.

## 7. Demo đầy đủ Java 17: constructor và @PostConstruct không làm nóng cache

Demo này dùng **Spring Framework 6.2.19**, Java 17, Maven, `ConcurrentMapCacheManager` và `jakarta.annotation.PostConstruct`. Không cần Spring Boot, Redis hay database bên ngoài.

Mục tiêu kiểm chứng:

1. Constructor gọi method có `@Cacheable`: body vẫn chạy.
2. `@PostConstruct` gọi lại method đó hai lần: body tiếp tục chạy.
3. Một **bean khác** triển khai `SmartInitializingSingleton` gọi service sau khi các singleton thông thường đã tạo: lần đầu miss và populate cache; lần sau hit.
4. Caller trong `main` gọi qua proxy: hit.
5. Method trong cùng service gọi `this.cachedMethod(...)` **ngay cả sau khi bean đã sẵn sàng**: body vẫn chạy vì self-invocation.

### 7.1. Cấu trúc project

~~~text
spring-cache-lifecycle/
├── pom.xml
└── src/main/java/demo/CacheLifecycleDemo.java
~~~

### 7.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-lifecycle</artifactId>
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
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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

`jakarta.annotation-api` cần có trên classpath để dùng `@PostConstruct` với Java 17; package này không còn được cung cấp như phần mặc định của JDK hiện đại. `spring-context` kéo theo các thành phần cần thiết cho cấu hình cache/AOP cơ bản trong demo. Nếu dự án đã dùng Spring Boot, hãy dùng bộ phiên bản phụ thuộc do BOM của Boot quản lý thay vì ghép thủ công không tương thích.

### 7.3. File src/main/java/demo/CacheLifecycleDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheLifecycleDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        public CacheWarmup cacheWarmup(
                CatalogService catalogService,
                CacheManager cacheManager) {
            return new CacheWarmup(catalogService, cacheManager);
        }
    }

    public static class CatalogService {
        private final AtomicInteger bodyCalls = new AtomicInteger();

        public CatalogService() {
            System.out.println("CONSTRUCTOR");

            // Chỉ để minh họa giới hạn; KHÔNG làm vậy trong app thật.
            System.out.println("ctor=" + find("A"));
        }

        @PostConstruct
        public void initialize() {
            System.out.println("POST_CONSTRUCT");
            System.out.println("init1=" + find("A"));
            System.out.println("init2=" + find("A"));
        }

        @Cacheable(cacheNames = "catalog", key = "#p0")
        public String find(String sku) {
            int n = bodyCalls.incrementAndGet();
            System.out.println("FIND_BODY " + sku + " #" + n);
            return "product-" + sku;
        }

        public void selfCallTwice() {
            System.out.println("SELF_CALL");
            System.out.println("self1=" + find("A"));
            System.out.println("self2=" + find("A"));
        }

        public int bodyCalls() {
            return bodyCalls.get();
        }
    }

    // Bean RIÊNG: nhận CatalogService thông qua Spring.
    // Callback diễn ra sau khi các singleton thông thường đã tạo.
    public static class CacheWarmup
            implements SmartInitializingSingleton {

        private final CatalogService catalogService;
        private final CacheManager cacheManager;

        public CacheWarmup(
                CatalogService catalogService,
                CacheManager cacheManager) {
            this.catalogService = catalogService;
            this.cacheManager = cacheManager;
        }

        @Override
        public void afterSingletonsInstantiated() {
            Cache cache = Objects.requireNonNull(
                    cacheManager.getCache("catalog"));

            System.out.println("WARMUP");
            System.out.println("cacheBefore="
                    + (cache.get("A") != null));

            System.out.println("warm1=" + catalogService.find("A"));
            System.out.println("warm2=" + catalogService.find("A"));

            System.out.println("cacheAfter="
                    + (cache.get("A") != null));
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {

            CatalogService service = context.getBean(
                    CatalogService.class);

            System.out.println("MAIN");
            System.out.println("main1=" + service.find("A"));

            // Gọi method KHÔNG được cache trên proxy;
            // bên trong method lại gọi find qua "this".
            service.selfCallTwice();

            System.out.println("main2=" + service.find("A"));
            System.out.println("bodyCalls=" + service.bodyCalls());
        }
    }
}
~~~

**Tại sao demo không thay bằng `new CatalogService()` trong `main`?** Vì như vậy Spring không quản lý object và không tạo proxy caching cho nó. Ở đây `catalogService` được tạo qua `@Bean` trong context, `@EnableCaching` kích hoạt caching advisor và `CatalogService` có method công khai có thể được proxy.

**Tại sao `CacheWarmup` là bean riêng?** Vì callback trên bean này giữ một dependency là `CatalogService` đã hoàn thành giai đoạn khởi tạo/proxy thông thường. Khi `CacheWarmup.afterSingletonsInstantiated()` gọi `catalogService.find(...)`, lời gọi đi qua bean reference có advice, chứ không phải `this.find(...)` trong chính `CatalogService`.

### 7.4. Biên dịch và chạy

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheLifecycleDemo
~~~

Stdout dự kiến từ các `System.out.println` của chương trình (không tính log riêng của Maven/JVM):

~~~text
CONSTRUCTOR
FIND_BODY A #1
ctor=product-A
POST_CONSTRUCT
FIND_BODY A #2
init1=product-A
FIND_BODY A #3
init2=product-A
WARMUP
cacheBefore=false
FIND_BODY A #4
warm1=product-A
warm2=product-A
cacheAfter=true
MAIN
main1=product-A
SELF_CALL
FIND_BODY A #5
self1=product-A
FIND_BODY A #6
self2=product-A
main2=product-A
bodyCalls=6
~~~

### 7.5. Đọc kết quả

| Pha | Gọi `find("A")` | Vì sao thân method chạy hoặc không chạy? |
| --- | --- | --- |
| Constructor | Lần 1 | Direct call trên target chưa hoàn thành khởi tạo/proxy; body chạy (`#1`) |
| `@PostConstruct` | Lần 1 và 2 | Self-invocation, không qua cache advice; body chạy (`#2` và `#3`) |
| Trước warm-up đúng cách | `cacheBefore=false` | Không có entry từ các lời gọi khởi tạo ở trên |
| `SmartInitializingSingleton` trong bean khác | Lần 1 | Proxy nhận lời gọi, cache miss, chạy body (`#4`), put entry |
| `SmartInitializingSingleton` | Lần 2 | Proxy nhận lời gọi, cache hit, body không chạy |
| `main` gọi từ bên ngoài | `main1` | Hit, body không chạy |
| `selfCallTwice` bên trong target | Hai lần | Mỗi lần `this.find` bypass proxy, body chạy (`#5`, `#6`) |
| `main` gọi lại | `main2` | Hit, body không chạy |
| Tổng body calls | `6` | 3 lần trước proxy + 1 miss thật + 2 self-invocations |

Quan trọng nhất: **`cacheBefore=false`** sau ba lần body chạy ở constructor/`@PostConstruct`. Nếu chỉ nhìn giá trị trả về `product-A`, rất dễ tưởng cache đã hoạt động. Kiểm chứng số lần gọi và trạng thái entry mới cho thấy sự khác biệt.

Lưu ý về `SmartInitializingSingleton`: callback này được gọi sau giai đoạn pre-instantiation của các **singleton thông thường**; không mặc nhiên áp dụng cho prototype hoặc singleton được khởi tạo lazy sau đó. Ví dụ chỉ dùng các bean singleton không lazy, nên luồng khởi động xác định được.

## 8. Các cách làm đúng khi cần warm-up cache

### Cách 1 — Bean khởi động riêng gọi service qua proxy sau khi các singleton đã sẵn sàng

Dùng `SmartInitializingSingleton` trong Spring Framework thuần (như demo) khi muốn chạy công việc đồng bộ sau giai đoạn tạo singleton thông thường. Bean khởi động phải được Spring quản lý, và **service cần cache phải là dependency đã được proxy**.

Nguyên tắc:

~~~text
Service đích @Cacheable  -> được Spring tạo và proxy
                   |
                   v
Bean khởi động riêng nhận service proxy
                   |
                   v
Sau khi singleton khởi tạo -> gọi service.cachedMethod()
                   |
                   v
CacheInterceptor -> miss -> load -> put -> hit ở các lần sau
~~~

Không để callback của chính `CatalogService` gọi `this.find(...)` rồi hy vọng annotation có hiệu lực.

### Cách 2 — Spring Boot: ApplicationRunner hoặc CommandLineRunner

Trong một dự án **Spring Boot** có dependency Boot tương ứng, có thể tạo một runner riêng:

~~~java
// Snippet dành cho Spring Boot, KHÔNG chạy độc lập nếu thiếu Boot.
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {
    private final CatalogService catalogService;

    public CatalogWarmupRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.find("A"); // gọi qua bean được Spring inject
    }
}
~~~

`ApplicationRunner` chạy ở giai đoạn khởi động của Spring Boot sau khi application context được chuẩn bị cho runner. Không dùng snippet này trong project Spring Framework thuần ở mục 7 vì nó yêu cầu các thư viện Spring Boot và định nghĩa `CatalogService` phù hợp.

Nếu tải dữ liệu khởi động có thể mất lâu, cân nhắc chính sách timeout, readiness, giới hạn số key, kiểm soát lỗi và yêu cầu khởi động dịch vụ. Đừng vô tình biến warm-up toàn bộ dữ liệu thành lý do ứng dụng không bao giờ sẵn sàng.

### Cách 3 — Listener nhận sự kiện sau khi context được refresh

Một bean riêng có thể lắng nghe `ContextRefreshedEvent` rồi gọi service qua proxy. Lưu ý context có thể được refresh lại hoặc có nhiều context trong cùng ứng dụng, nên cần xử lý chạy lặp/đúng context, đặc biệt với ứng dụng web có context cha–con.

Ví dụ mang tính thiết kế:

~~~java
// Snippet minh họa, cần import Spring, đăng ký bean và service.
@EventListener(ContextRefreshedEvent.class)
public void onContextReady() {
    catalogService.find("A");
}
~~~

Không đặt listener trong chính `CatalogService` rồi gọi `this.find(...)`; như vậy vẫn là self-invocation dù event xảy ra muộn hơn. Khi cần chạy đúng một lần, quản lý cờ/idempotency và lifecycle một cách minh bạch.

### Cách 4 — Chủ động thao tác với Cache API

Đôi khi yêu cầu không phải “gọi `@Cacheable`” mà là **chủ động populate một cache** từ dữ liệu đã có. Lúc này có thể dùng `CacheManager`:

~~~java
// Snippet minh họa, manager/value đến từ cấu hình ứng dụng.
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("catalog"));

String value = repository.load("A");
cache.put("A", value);
~~~

Đây là **đường thao tác trực tiếp với cache**, không cần `@Cacheable` intercept. Nhưng phải giữ đúng cache name, key format, serialization, TTL, null policy và không vô tình cache dữ liệu chưa commit. Việc dùng cache API trong `@PostConstruct` chỉ nên xem xét khi các dependency liên quan đã sẵn sàng và có lý do thiết kế rõ ràng; nó không sửa được self-invocation của annotation.

### Cách 5 — Không warm-up nếu không cần

Cache là cơ chế tối ưu. Nhiều hệ thống có thể dùng **lazy population**: request đầu tiên miss rồi populate, các request sau hit. Warm-up chỉ đáng làm khi đã đo được lợi ích thực tế cho tập key quan trọng (ví dụ danh mục cấu hình nhỏ, dữ liệu đọc nhiều) so với chi phí startup và nguy cơ tạo burst tới database.

## 9. Những cách “sửa” dễ gây hiểu lầm

### 9.1. Thêm @EnableCaching là đủ?

`@EnableCaching` **cần thiết** để kích hoạt cơ chế annotation trong cấu hình thích hợp, nhưng **không làm lời gọi từ constructor hoặc `this.method()` tự đi qua proxy**. Bật caching và có proxy đúng vẫn không giải quyết self-invocation.

### 9.2. Thêm sync=true?

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0", sync = true)
public String find(String code) {
    return repository.load(code);
}
~~~

`sync=true` yêu cầu provider phối hợp việc nạp giá trị khi nhiều caller cùng miss, theo các điều kiện giới hạn của Spring Cache. Nó **không** tạo interception cho lời gọi bỏ qua proxy. Do đó, không dùng `sync=true` như giải pháp cho constructor/`@PostConstruct`.

### 9.3. Dùng @Lazy, @DependsOn hoặc đổi thứ tự bean?

Các công cụ này kiểm soát **thời điểm tạo bean hoặc phụ thuộc** chứ không thay đổi bản chất self-invocation. `@DependsOn` có thể đảm bảo một dependency được tạo trước, nhưng không biến `this.find(...)` thành lời gọi qua proxy.

### 9.4. Lấy proxy của chính mình từ ApplicationContext ngay trong @PostConstruct?

Đây là một giải pháp vòng vo, có thể dẫn đến circular creation, early bean reference hoặc hành vi thay đổi theo cấu hình proxy. Không nên thiết kế bean phải tự tìm proxy của chính nó trong quá trình initialization chỉ để gọi method cache. Tách bean khởi động riêng là cách dễ hiểu và kiểm thử hơn.

### 9.5. Dùng AspectJ mode để cho phép self-invocation?

Spring có tùy chọn `@EnableCaching(mode = AdviceMode.ASPECTJ)` khi cấu hình weaving thích hợp. Cách này có thể xử lý lời gọi nội bộ khác với proxy mode vì advice được weave vào bytecode. Tuy nhiên:

- Cần cấu hình và dependency AspectJ/weaving đúng; không chỉ đổi một annotation là xong.
- Không biến các dependency chưa inject trong constructor thành sẵn sàng.
- Không đảm bảo ứng dụng nên tải dữ liệu/phát sinh side effect khi object chưa được xây dựng đầy đủ.
- Không nên chuyển cơ chế AOP toàn hệ thống chỉ để tránh thiết kế warm-up đúng lifecycle.

**Giải pháp mặc định nên ưu tiên:** tách lời gọi có cache ra một bean khác và gọi khi service đã sẵn sàng.

### 9.6. Method visibility, final và kiểu proxy

Ngay cả sau khi initialization hoàn tất, method phải đủ điều kiện để proxy intercept. Để các ví dụ rõ và portable, nên đặt `@Cacheable` trên **public method** của Spring-managed bean, không gắn lên `private`/`final` method rồi giả định caching sẽ chạy. Với JDK dynamic proxy, lời gọi phải đi qua interface được proxy; với class-based proxy, final method cũng không được override/advice theo cách thông thường. Nếu lời gọi không được intercept, đổi thời điểm warm-up **chưa đủ**; phải sửa cả thiết kế method và bean.

## 10. Lỗi quan sát và cách kiểm tra thực tế

### 10.1. “Chạy hai lần mà kết quả giống nhau, vậy đã cache”

Không đúng. Method có thể trả cùng một kết quả vì dữ liệu gốc không đổi. Phải chứng minh bằng số lần thực thi body, cache entry hoặc log CacheInterceptor/provider (tránh bật log nhạy cảm trên production).

Ví dụ:

~~~text
Kết quả:
  call #1 -> "product-A"
  call #2 -> "product-A"

Điều này CHƯA đủ kết luận hit:
  - có thể thân method chạy 2 lần và đều trả "product-A";
  - hoặc method chạy 1 lần rồi lần 2 hit.
~~~

### 10.2. “@PostConstruct chạy sau inject nên mọi interceptor đã sẵn sàng”

Không đúng. Injection hoàn thành **không tương đương** việc toàn bộ proxy của chính bean đã hoàn tất. Khi chính target gọi method của nó, self-invocation vẫn bypass advice.

### 10.3. “Tôi gọi service từ một bean khác trong @PostConstruct mà cache vẫn có tác dụng — vậy quy tắc trên sai?”

Không nhất thiết. Nếu dependency được inject là một bean **đã proxied hoàn chỉnh**, lời gọi **từ bean khác** có thể qua proxy. Quy tắc trọng tâm là *đường đi của lời gọi*; dù vậy, code khởi tạo tổng thể vẫn cần chú ý thứ tự bean và sự sẵn sàng của hệ thống. Tốt hơn hết, tổ chức warm-up ở một giai đoạn rõ ràng sau khởi tạo.

### 10.4. “Mọi lần đều miss sau khi ứng dụng đã khởi động”

Có thể **không liên quan đến lifecycle**, mà do:

- Mỗi lời gọi có key khác (`key`/`SimpleKeyGenerator`/đối số mutable).
- `condition` bypass cache hoặc `unless` từ chối lưu kết quả.
- Entry bị evict, hết TTL hoặc lưu ở cache manager/provider khác.
- Method gọi từ nội bộ thay vì qua proxy.
- Lời gọi đi đến object tạo bằng `new`, bean không được Spring quản lý.
- Method private/final hoặc kiểu proxy khiến advice không áp dụng.
- Cache backend có lỗi hoặc nhiều instance dùng cache cục bộ khác nhau.

Nên phân biệt **không qua interceptor** với **interceptor xử lý nhưng lookup miss**; hai tình huống cần cách chữa khác nhau.

### 10.5. Checklist debug theo thứ tự

1. Xác nhận `@EnableCaching` được bật ở đúng application context.
2. Xác nhận caller đang giữ một **Spring bean**, không phải object tự tạo.
3. Kiểm tra method cache có thể được proxy/advice trong cấu hình hiện tại.
4. Vẽ chuỗi gọi thực tế: `caller -> proxy -> target` hay `target -> this.method()`?
5. Xác định lời gọi xảy ra trong constructor/`@PostConstruct` hay sau khi bean đã ready.
6. Dùng một bean khởi động riêng gọi qua dependency đã proxied, rồi so sánh body-call counter.
7. Kiểm tra cache name, key, `condition`, `unless`, expiration và eviction.
8. Với cache phân tán, kiểm tra instance, serialization, transactions và thời điểm invalidation.
9. Nếu câu trả lời vẫn không rõ, dùng integration test với Spring context thật thay vì unit test khởi tạo bằng `new`.

## 11. Kiểm thử caching liên quan đến lifecycle

Một unit test chỉ có:

~~~java
CatalogService service = new CatalogService();
service.find("A");
service.find("A");
~~~

**không** kiểm thử `@Cacheable`, vì không có container/proxy. Với constructor mẫu ở mục 7, việc tự tạo này thậm chí còn chạy code “warm-up sai” trong constructor. Để kiểm thử annotation:

- Tạo `ApplicationContext` với `@EnableCaching` và `CacheManager` cho test.
- Lấy bean bằng `context.getBean(CatalogService.class)`.
- Lặp lời gọi cache qua bean proxy, đo số lần thân method chạy.
- Kiểm tra key thực sự có trong cache nếu cần.
- Cố ý so sánh với self-invocation để chứng minh khác biệt.

Trong Spring Test, có thể kiểm tra proxy bằng `AopUtils.isAopProxy(bean)` khi phù hợp, nhưng **proxy tồn tại không tự chứng minh mỗi lời gọi có qua advice**. Vì thế kiểm chứng kết quả + counter/cache entry vẫn cần thiết.

### Tình huống kiểm thử tối thiểu

| Tình huống | Kỳ vọng trong proxy mode thông dụng |
| --- | --- |
| Constructor của chính bean gọi method cache 2 lần | Body có thể chạy cả hai lần; không dựa vào annotation cache |
| `@PostConstruct` của chính bean gọi `this.find(...)` 2 lần | Bỏ qua cache advice; body chạy 2 lần |
| Một bean khởi động riêng gọi service proxied sau khởi tạo | Lần đầu miss, lần sau hit nếu entry được lưu |
| Caller bình thường gọi hai lần cùng key sau warm-up | Có thể hit cả hai lần |
| Một method thông thường trong cùng bean gọi `this.find(...)` | Vẫn self-invocation, dù context đã ready |
| Method `@CacheEvict` được gọi từ `this.invalidate(...)` | Không có eviction qua annotation |
| Method được gọi bằng `new` ngoài Spring | Không có proxy interception |

Với ví dụ production, đừng viết test quá chặt về nội bộ số lượng BeanPostProcessor hoặc class name của CGLIB proxy; hãy test **hành vi công khai** như số lần tải dữ liệu, trạng thái cache và độ mới của dữ liệu.

## 12. Lưu ý vận hành khi làm nóng cache đúng thời điểm

Đưa việc warm-up sang giai đoạn sau initialization giải quyết vấn đề proxy, nhưng chưa giải quyết mọi bài toán vận hành:

- **Phạm vi key:** Chỉ làm nóng những key thật sự cần, tránh scan toàn bộ bảng dữ liệu lớn chỉ để cache.
- **Tải cùng lúc:** Nhiều replica có thể warm-up cùng lúc, gây truy vấn trùng và tăng tải nguồn.
- **TTL/eviction:** Cache có thể hết hạn ngay sau startup tùy chính sách provider; warm-up không bảo đảm entry còn mãi.
- **Nhất quán dữ liệu:** Nếu dữ liệu gốc đang được cập nhật, warm-up có thể nạp bản cũ; phối hợp invalidation sau commit khi cần.
- **Dữ liệu nhạy cảm:** Với hệ thống nhiều tenant, chọn đúng cache và key theo tenant, không warm-up chung dữ liệu của các tenant.
- **Thất bại khi khởi động:** Quyết định rõ lỗi warm-up khiến ứng dụng fail-fast, degrade hay retry; tránh loop vô hạn.
- **Readiness:** Không đánh dấu dịch vụ sẵn sàng nếu một tập dữ liệu bắt buộc chưa được nạp thành công; ngược lại, không kéo dài startup vô ích vì dữ liệu tùy chọn.
- **Thread context:** Nếu warm-up chạy async, tenant/security/transaction context không tự động chuyển qua thread khác.
- **Đo lường:** Ghi nhận thời gian warm-up, hit ratio, miss rate, số lần nạp backend và timeout; đừng dựa vào cảm giác.

Một phương thức không đòi hỏi caching có thể vẫn được gọi trong `@PostConstruct` để khởi tạo **trạng thái nội bộ** hợp lệ của bean, nhưng không nên nhầm nó với việc thực thi một cache operation thông qua annotation.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong constructor, `this.find("A")` gọi method có `@Cacheable`; phương thức được thực thi có nghĩa cache đã được dùng không?

**Trả lời:** Không. Trong proxy mode, lời gọi trực tiếp lúc object đang được khởi tạo không đi qua proxy caching cuối cùng. Thân method có thể chạy mà không tra hoặc lưu entry.

**Câu 2.** Tại sao `@PostConstruct` không phải thời điểm mặc định để gọi `@Cacheable` trên chính bean?

**Trả lời:** Vì bean vẫn trong vòng đời initialization và lời gọi nội bộ `this.method()` bypass proxy. Spring yêu cầu proxy được khởi tạo đầy đủ để cache advice hoạt động như mong đợi.

**Câu 3.** Nếu gọi `catalogService.find("A")` từ `ApplicationRunner` riêng trong Spring Boot, điều gì giúp cache hoạt động?

**Trả lời:** Runner nhận một dependency là Spring-managed service đã được proxy, và gọi từ bên ngoài thông qua reference đó khi context đã khởi tạo. Điều kiện còn lại là caching được bật, method có thể được advice và key/provider hợp lệ.

**Câu 4.** `SmartInitializingSingleton` trong chính `CatalogService` gọi `this.find("A")` có tự khắc phục self-invocation không?

**Trả lời:** Không. Dù callback xảy ra muộn hơn, `this.find(...)` vẫn là lời gọi nội bộ. Demo dùng một **bean khác** nắm reference đến service proxy.

**Câu 5.** Có thể dùng `@CacheEvict` trong `@PostConstruct` để xóa cache thông qua `this.clearCache()` không?

**Trả lời:** Không nên kỳ vọng. Cùng giới hạn proxy áp dụng cho `@CacheEvict`. Dùng lời gọi qua proxy đúng thời điểm hoặc API `Cache` trực tiếp nếu thiết kế cho phép.

**Câu 6.** Dùng `sync=true`, `@Lazy` hoặc `@DependsOn` có tự giải quyết sự cố không?

**Trả lời:** Không. Chúng không biến self-invocation thành lời gọi đi qua interceptor. Cần thay đổi đường gọi và/hoặc thời điểm hoạt động.

**Câu 7.** Sau khi chuyển warm-up sang bean khác, có chắc hệ thống sẽ hit mọi lúc không?

**Trả lời:** Không. Hit còn phụ thuộc key, cache name, `condition`/`unless`, TTL, eviction, backend, instance và trạng thái dữ liệu. Giải pháp trên chỉ giải quyết khả năng cache advice được gọi.

## 14. Kết luận

Giới hạn khi sử dụng Spring Cache trong **constructor hoặc `@PostConstruct`** xuất phát từ **vòng đời bean và cơ chế proxy**, không phải vì annotation cache “chỉ hoạt động khi ứng dụng có HTTP request”. Những điểm quan trọng nhất:

1. Trong constructor, object chưa sẵn sàng cho Spring proxy caching cuối cùng; không dùng constructor để làm nóng `@Cacheable`.
2. Trong `@PostConstruct` của cùng bean, `this.cachedMethod()` bypass proxy; thân method vẫn chạy nhưng cache advice không chạy.
3. Tách logic warm-up sang **một bean riêng**, gọi service qua dependency Spring đã proxied sau khi singleton sẵn sàng (ví dụ `SmartInitializingSingleton` hoặc Boot `ApplicationRunner`).
4. Cùng giới hạn tự gọi ảnh hưởng `@CachePut` và `@CacheEvict`, không chỉ `@Cacheable`.
5. Kiểm thử bằng Spring context thật, số lần thực thi body và cache entry — không kết luận từ việc kết quả của hai lời gọi giống nhau.

**Quy tắc thực hành:** *Spring cache annotation được áp dụng theo đường đi qua advice/proxy, không chỉ theo vị trí annotation trong source code.*

## 15. Tài liệu chính thức

- Spring Framework — Declarative Annotation-based Caching (proxy/self-invocation và lưu ý `@PostConstruct`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Bean Lifecycle / Customizing Bean Nature: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html

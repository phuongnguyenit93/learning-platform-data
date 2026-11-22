# Hết hạn khác với làm mới dữ liệu

Trong **Spring Framework Cache**, “entry đã hết hạn” và “entry đã được làm mới” là **hai trạng thái/hành động khác nhau**. Một kết quả cache có **TTL** 5 phút không có nghĩa Spring cứ năm phút lại hỏi database. TTL chủ yếu quy định **đến khi nào một bản sao cache không còn hợp lệ để đọc**; việc **refresh** đòi hỏi lấy lại dữ liệu từ nguồn và ghi một giá trị mới. Hai việc có thể được thực hiện độc lập, kết hợp, hoặc được điều khiển bởi những thành phần khác nhau của hệ thống.

Ví dụ: giá sản phẩm **P01** được cache lúc 10:00 là 100. Đến 10:03, giá nguồn thành 120 nhưng entry chưa hết TTL nên vẫn có thể trả 100. Đến 10:05, entry hết hạn; **lần đọc tiếp theo** mới tạo cache miss và chạy phương thức nạp giá 120. Ngược lại, nếu **refresh lúc 10:04**, cache có thể được thay thành giá 120 trước TTL ban đầu, và mốc thời gian sau lần cập nhật cache cũng có thể được tính lại.

Mục tiêu bài học: hiểu đúng **expiration**, **eviction**, **refresh**, phân biệt các chính sách **expireAfterWrite**, **expireAfterAccess**, **refreshAfterWrite**, sử dụng **@Cacheable / @CachePut / @CacheEvict** đúng vai trò và kiểm thử vòng đời bằng **Java 17 + Spring + Caffeine**.

## 1. Bốn khái niệm khác nhau

| Thuật ngữ | Diễn ra điều gì? | Có tự nạp dữ liệu mới không? | Điều người đọc thường quan sát |
| --- | --- | --- | --- |
| **Expiration / TTL** | Entry trở nên không hợp lệ khi quá tuổi quy định | **Không** | Lần đọc sau có thể miss và phải tải lại |
| **Eviction / invalidation** | Entry bị loại do lệnh, cập nhật nghiệp vụ, giới hạn dung lượng… | **Không** | Lần đọc sau miss |
| **Refresh** | Một loader/method đọc nguồn và thay giá trị cache | **Có quá trình nạp**, do caller/provider/scheduler khởi động | Giá trị mới xuất hiện khi refresh hoàn tất; một số mô hình tạm trả stale |
| **Prewarming** | Nạp trước những key dự đoán sẽ được truy cập | **Có**, theo kế hoạch của ứng dụng | Request sau có thể hit ngay |

**Expiration là quy tắc tuổi thọ; refresh là hoạt động tạo value mới.** Một entry có thể được refresh nhiều lần mà chưa từng expire. Một entry cũng có thể expire rồi nằm đó về mặt vật lý cho tới khi provider dọn dẹp, trong khi lookup phải coi nó là hết hạn.

Đừng nhầm “expire” với “evict”: cả hai có thể làm kết quả bị bỏ qua khi đọc, nhưng **nguyên nhân** khác nhau. Eviction còn có thể do số lượng entry, giới hạn bộ nhớ hoặc người quản trị, không chỉ do thời gian.

## 2. Điều gì xảy ra khi gọi @Cacheable?

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.load(id);
}
~~~

Dòng xử lý điển hình:

~~~text
find("P01")
    |
    v
Tra cache "products" theo key "P01"
    |
    +---- HIT, entry hợp lệ ---> trả value, KHÔNG chạy method
    |
    +---- MISS / expired -----> chạy repository.load("P01")
                                  |
                                  v
                              lưu value mới
                                  |
                                  v
                               trả value
~~~

Khi cache chưa có value, **@Cacheable** xử lý miss bằng cách chạy method. Nhưng Spring Cache Abstraction **không tự quy định TTL mặc định** cho mọi provider. Bạn phải cấu hình CacheManager và cache store cụ thể. Ví dụ **ConcurrentMapCacheManager** đơn giản là cache map trong JVM và không cung cấp TTL tự động; **Caffeine** hoặc **Redis** có chính sách riêng.

Giả sử provider áp dụng TTL 5 phút: một entry expire lúc 10:05. Nếu sau đó không có request nào, **Spring không tự gọi lại phương thức find** chỉ vì đồng hồ đã vượt mốc. Bản mới thường xuất hiện khi có lần đọc tạo miss hoặc có hành động refresh chủ động.

## 3. expireAfterWrite và expireAfterAccess không giống nhau

### expireAfterWrite: tuổi tính từ lần ghi/cập nhật

~~~java
// Cấu hình Caffeine builder trong ứng dụng có dependency Caffeine.
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(java.time.Duration.ofMinutes(5));
~~~

Nếu một key được tạo lúc 10:00 thì đến khoảng 10:05 nó không còn hợp lệ. **Các lần đọc cache hit trong thời gian đó không đặt lại tuổi write.** Nếu có **put/refresh** thành công lúc 10:04, mốc write của value mới được cập nhật; entry mới có thể còn hợp lệ tới khoảng 10:09.

Chính sách này hữu ích khi muốn giới hạn tuổi bản sao, nhưng nó **không bảo đảm dữ liệu luôn giống nguồn trong suốt năm phút**. Nguồn thay đổi ngay sau 10:00 vẫn có thể làm value cache stale.

### expireAfterAccess: tuổi tính từ lần truy cập cuối

~~~java
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterAccess(java.time.Duration.ofMinutes(5));
~~~

Trong chính sách này, một hot key được đọc liên tục có thể kéo dài thời gian sống rất lâu. **Truy cập thường xuyên không đồng nghĩa dữ liệu được cập nhật từ DB**; key hot vẫn có thể stale nếu không có invalidation hoặc refresh khác.

**Quy tắc lựa chọn:** expireAfterWrite thiên về giới hạn tuổi của bản sao; expireAfterAccess thường phù hợp để thu hồi dữ liệu **ít sử dụng**. Cả hai không thay thế yêu cầu về freshness, phân quyền và tính nhất quán giao dịch.

## 4. Refresh chủ động bằng @CachePut

Spring phân biệt đọc cache và chủ động ghi cache. Ví dụ hai phương thức cùng dùng cache name/key:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.load(id);
}

@CachePut(cacheNames = "products", key = "#p0")
public Product refresh(String id) {
    return repository.load(id);
}
~~~

**@Cacheable** có thể trả value hiện có mà bỏ qua method. **@CachePut** chạy method để tạo kết quả, sau đó ghi **kết quả trả về** vào cache (tuân theo condition/unless nếu được cấu hình). Vì vậy có thể refresh một key **trước khi TTL hết hạn**.

Tuy nhiên:

- **@CachePut không tự lập lịch**. Nếu không ai gọi **refresh**, không có refresh chỉ nhờ annotation.
- **Method phải thực sự đọc dữ liệu nguồn mới**. @CachePut không tự biết DB có gì thay đổi.
- **Cache name và key phải khớp** với phương thức đọc. Nếu key khác, entry cũ vẫn có thể được dùng.
- **Phải gọi qua Spring proxy**; tự gọi **this.refresh(...)** trong cùng bean ở chế độ proxy thông thường có thể bỏ qua cache advice.
- Nếu giá trị trả về **null**, phải hiểu quy tắc lưu null và **unless = "#result == null"** của method, nhất là khi provider không cho phép null.

Với **@CachePut**, một lệnh nạp nguồn và cập nhật cache có thể xảy ra lúc TTL vẫn còn. Đó là điểm khác biệt cốt lõi so với chờ **expiration → miss → load**.

## 5. @CacheEvict: loại entry không phải làm mới entry

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String id) {
    // Không có thao tác lấy dữ liệu mới.
}
~~~

**invalidate("P01")** loại entry P01. Sau đó **find("P01")** mới có thể phải tải lại. Nếu không có lần đọc tiếp theo, không có gì bảo đảm dữ liệu được nạp sẵn.

Mặc định **@CacheEvict** thực hiện eviction sau khi method kết thúc bình thường; **beforeInvocation = true** xóa trước lời gọi, kể cả khi method sau đó thất bại. Trong ứng dụng có transaction, phải quan tâm thời điểm eviction so với **commit**, tránh request khác cache miss rồi tải giá trị DB chưa commit.

Ví dụ khi đổi giá, có thể chọn **cập nhật DB rồi evict key** (để lần đọc sau lấy giá mới), hoặc **refresh/put value đã được xác nhận sau cập nhật**. Cần kiểm thử hành vi race và failure của phương án đã chọn.

## 6. Caffeine refreshAfterWrite: “đủ điều kiện” không phải “đúng giờ tự chạy”

Caffeine hỗ trợ **refreshAfterWrite** cho cache có loader, ví dụ **LoadingCache** (mã minh họa, cần backend thực và import Caffeine/LoadingCache):

~~~java
LoadingCache<String, Product> cache = Caffeine.newBuilder()
    .maximumSize(10_000)
    .refreshAfterWrite(java.time.Duration.ofMinutes(2))
    .expireAfterWrite(java.time.Duration.ofMinutes(15))
    .build(key -> backend.load(key));
~~~

Ý nghĩa chính xác:

1. Sau **hai phút từ write**, entry **đủ điều kiện** refresh.
2. Caffeine thông thường **khởi động refresh khi có lần đọc đầu tiên tới entry đã đủ điều kiện**, không phải tự chạy nền trên tất cả key đúng mỗi hai phút.
3. Refresh thực hiện nạp lại **bất đồng bộ**. Trong lúc chờ, **giá trị cũ có thể tiếp tục được trả**, giúp giảm spike latency; khi reload thành công, value mới thay thế.
4. Nếu refresh thất bại, Caffeine thường giữ value cũ và ghi nhận lỗi; cần quan sát lỗi và quyết định giới hạn stale chấp nhận được.
5. **expireAfterWrite** là chính sách **hết hạn cứng** độc lập; entry không được truy cập khi đã đủ điều kiện refresh vẫn có thể expire.
6. Refresh cần **CacheLoader / AsyncCacheLoader** phù hợp. Cấu hình mỗi **@Cacheable** không tự biến method thành loader cho chính sách **refreshAfterWrite**.

Khi dùng **CaffeineCacheManager** trong Spring, cần kiểm tra cách tạo **LoadingCache**, CacheLoader được đăng ký và hành vi adapter. Không suy diễn rằng chỉ thêm thuộc tính **refreshAfterWrite** vào builder là mỗi key sẽ tự chạy một method Spring theo lịch.

| Chính sách Caffeine | Khi qua mốc thời gian | Lần read tiếp theo | Có thể trả stale không? |
| --- | --- | --- | --- |
| **expireAfterWrite(5m)** | Entry quá tuổi write, bị coi không hợp lệ | Miss/load mới | Không theo expiration policy |
| **expireAfterAccess(5m)** | Entry hết hạn nếu không được truy cập đủ lâu | Miss nếu idle hết hạn | Không theo expiration policy |
| **refreshAfterWrite(2m)** | Entry đủ điều kiện refresh | Thường kích hoạt async reload | **Có thể**, khi reload đang chạy |

**Refresh không đồng nghĩa strong consistency.** Nếu nghiệp vụ không được phép trả stale dù chỉ trong vài giây, cần chính sách đồng bộ và đọc nguồn thích hợp; không thể tự dùng stale-while-revalidate mà bỏ qua yêu cầu đó.

## 7. Demo Spring + Caffeine + Java 17: kiểm chứng bằng đồng hồ mô phỏng

Ví dụ đầy đủ này dùng **Spring Framework 6.1.14**, **Caffeine 3.1.8**, **Java 17** và Gradle. Nó có một **source** giả lập version v1/v2/v3/v4 và một **MutableTicker** để tiến đồng hồ cache theo phút mà không dùng Thread.sleep. Spring dùng CaffeineCacheManager với **expireAfterWrite(5 phút)**.

Mục tiêu test một timeline có **hai key P01 và P02**:

- Phút **0**: đọc P01, P02, cả hai được cache với v1.
- Nguồn chuyển **v2**, nhưng các entry còn hạn vẫn trả v1.
- Phút **4**: **refresh(P01)** bằng @CachePut tạo v2 và đặt lại tuổi write P01.
- Phút **6**: P01 mới 2 phút tuổi nên hit v2; P02 đã 6 phút tuổi và hết TTL nên nạp lại v2.
- Phút **11**: nguồn đã v3; P01 đã 7 phút kể từ refresh phút 4 nên hết hạn, nạp lại v3.
- Nguồn chuyển **v4**; **invalidate(P01)** xóa entry P01 mới vừa nạp, rồi lần đọc tiếp theo nạp v4.

**settings.gradle**

~~~groovy
rootProject.name = 'spring-expiry-refresh-demo'
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
    implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'
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
    mainClass = 'demo.cache.ExpiryRefreshDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/ExpiryRefreshDemo.java**

~~~java
package demo.cache;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class ExpiryRefreshDemo {

    public static final class MutableTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            nanos.addAndGet(duration.toNanos());
        }
    }

    public static final class Source {
        private final AtomicInteger version = new AtomicInteger(1);

        public String read(String id) {
            return id + ":v" + version.get();
        }

        public void bump() {
            version.incrementAndGet();
        }
    }

    @Bean
    public MutableTicker ticker() {
        return new MutableTicker();
    }

    @Bean
    public Source source() {
        return new Source();
    }

    @Bean
    public CacheManager cacheManager(MutableTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .expireAfterWrite(Duration.ofMinutes(5))
                .ticker(ticker));
        return manager;
    }

    @Bean
    public ProductService productService(Source source) {
        return new ProductService(source);
    }

    public static class ProductService {
        private final Source source;
        private final AtomicInteger loads = new AtomicInteger();

        public ProductService(Source source) {
            this.source = source;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String id) {
            loads.incrementAndGet();
            return source.read(id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public String refresh(String id) {
            loads.incrementAndGet();
            return source.read(id);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void invalidate(String id) {
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                ExpiryRefreshDemo.class)) {
            Source source = ctx.getBean(Source.class);
            MutableTicker clock = ctx.getBean(MutableTicker.class);
            ProductService service = ctx.getBean(ProductService.class);

            System.out.println("t0-P01=" + service.find("P01"));
            System.out.println("t0-P02=" + service.find("P02"));

            source.bump();
            System.out.println("source=" + source.read("P01"));
            System.out.println("beforeExpiry=" + service.find("P01"));

            clock.advance(Duration.ofMinutes(4));
            System.out.println("t4-beforeRefresh=" + service.find("P01"));
            System.out.println("t4-refresh=" + service.refresh("P01"));

            clock.advance(Duration.ofMinutes(2));
            System.out.println("t6-P01=" + service.find("P01"));
            System.out.println("t6-P02=" + service.find("P02"));

            source.bump();
            clock.advance(Duration.ofMinutes(5));
            System.out.println("t11-P01=" + service.find("P01"));

            source.bump();
            service.invalidate("P01");
            System.out.println("afterEvict-P01=" + service.find("P01"));
            System.out.println("loads=" + service.loadCount());
        }
    }
}
~~~

**Cấu trúc thư mục** cần có hai file Gradle ở root, class main tại **src/main/java/demo/cache/ExpiryRefreshDemo.java** và test tại **src/test/java/demo/cache/ExpiryRefreshDemoTest.java**.

Chạy bằng Gradle cài sẵn hoặc wrapper của project đã tạo, trong thư mục dự án:

~~~bash
gradle run --quiet
~~~

Những dòng **System.out.println** dự kiến:

~~~text
t0-P01=P01:v1
t0-P02=P02:v1
source=P01:v2
beforeExpiry=P01:v1
t4-beforeRefresh=P01:v1
t4-refresh=P01:v2
t6-P01=P01:v2
t6-P02=P02:v2
t11-P01=P01:v3
afterEvict-P01=P01:v4
loads=6
~~~

Số lần thực thi thân **find/refresh** là 6: hai lần miss ban đầu; một lần refresh P01; một lần P02 hết hạn tại phút 6; một lần P01 hết hạn tại phút 11; một lần P01 miss sau evict. Những lần đọc khác đều hit và không làm tăng bộ đếm.

### Kiểm thử JUnit 5 có thể chạy

**src/test/java/demo/cache/ExpiryRefreshDemoTest.java**

~~~java
package demo.cache;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ExpiryRefreshDemo.class)
class ExpiryRefreshDemoTest {

    @Autowired
    ExpiryRefreshDemo.MutableTicker ticker;

    @Autowired
    ExpiryRefreshDemo.Source source;

    @Autowired
    ExpiryRefreshDemo.ProductService service;

    @Autowired
    CacheManager manager;

    @Test
    void distinguishesExpireRefreshAndInvalidate() {
        assertEquals("P01:v1", service.find("P01"));
        assertEquals("P02:v1", service.find("P02"));
        assertEquals(2, service.loadCount());

        source.bump();
        assertEquals("P01:v2", source.read("P01"));
        assertEquals("P01:v1", service.find("P01"));

        ticker.advance(Duration.ofMinutes(4));
        assertEquals("P01:v1", service.find("P01"));
        assertEquals("P01:v2", service.refresh("P01"));
        assertEquals(3, service.loadCount());

        ticker.advance(Duration.ofMinutes(2));
        assertEquals("P01:v2", service.find("P01"));
        assertEquals("P02:v2", service.find("P02"));
        assertEquals(4, service.loadCount());

        source.bump();
        ticker.advance(Duration.ofMinutes(5));
        assertEquals("P01:v3", service.find("P01"));
        assertEquals(5, service.loadCount());

        source.bump();
        // P01 vừa được load ở phút 11 nên còn entry trước eviction.
        assertNotNull(manager.getCache("products").get("P01"));
        service.invalidate("P01");
        assertNull(manager.getCache("products").get("P01"));
        assertEquals("P01:v4", service.find("P01"));
        assertEquals(6, service.loadCount());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** một bài test thành công với cấu hình Java/Spring/Caffeine trên. Không cần ngủ năm phút thật; **MutableTicker** tăng giờ của CaffeineCache và assertion có thể chứng minh đúng hạn/refresh/evict. Các lệnh Gradle là hướng dẫn tái hiện; chúng không phải stdout chắc chắn ngoài chương trình.

**Giới hạn:** demo này sử dụng **@CachePut để refresh chủ động** cộng với **expireAfterWrite**. Nó *không* sử dụng tự động **refreshAfterWrite** của LoadingCache; cơ chế đó có semantics bất đồng bộ khác như ở mục 6. Ví dụ dùng Spring bean qua ApplicationContext, tránh gọi **new ProductService(...)** khi cần kiểm tra AOP interceptor.

## 8. Cấu hình trong Spring Boot và Redis

### Spring Boot + Caffeine

Với Spring Boot có cache starter/Caffeine và đã bật caching, cấu hình minh họa:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productList
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=300s
~~~

**expireAfterWrite=300s** là expiration khoảng năm phút sau write; không phải lệnh Spring cứ năm phút tự chạy method tải dữ liệu. Chú ý ứng dụng dùng Spring Boot cần dependency **spring-boot-starter-cache** và thư viện Caffeine tương thích; ở dự án Spring Framework thuần, cần **spring-context-support** cho CaffeineCacheManager.

Nếu muốn **refreshAfterWrite**, phải kiểm tra cách Boot đăng ký CacheLoader và underlying LoadingCache. Đừng chỉ thêm refreshAfterWrite vào spec rồi tuyên bố mọi method **@Cacheable** sẽ được chạy lại tự động theo lịch.

### Spring Data Redis TTL

Ví dụ ở tầng cấu hình Spring Data Redis (không phải Java class độc lập):

~~~java
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl(java.time.Duration.ofMinutes(5));
~~~

Khi một key đã hết TTL và Redis không trả được value, **@Cacheable** trong ứng dụng có thể chạy method để tải lại theo request. Redis không tự biết phương thức Java nào sẽ được gọi để refresh. Cần xác minh cache prefix, serializer, null handling, TTL theo từng cache và đặc tính nhiều instance; một shared cache không tự giải quyết mọi race cache miss đồng thời.

### ConcurrentMapCache đơn giản

Nếu dùng **ConcurrentMapCacheManager**, không nên gán một TTL mặc định tưởng tượng: cache map trong JVM không có chính sách expireAfterWrite sẵn như Caffeine. Entry có thể còn cho tới khi được thay/xóa hoặc ứng dụng kết thúc. Chọn provider và cấu hình phù hợp với nhu cầu vòng đời.

## 9. Scheduler có phải là refresh không?

Nếu nghiệp vụ cần nạp lại một số key nóng **theo lịch**, phải có logic gọi refresh thật sự. Ví dụ đoạn minh họa trong ứng dụng đã cấu hình **@EnableScheduling**, có Spring bean service với phương thức **@CachePut**:

~~~java
@Component
public class HotProductWarmer {
    private final ProductService productService;

    public HotProductWarmer(ProductService productService) {
        this.productService = productService;
    }

    @Scheduled(fixedDelay = 120000)
    public void refreshP01() {
        productService.refresh("P01");
    }
}
~~~

Import **@Component** từ org.springframework.stereotype và **@Scheduled** từ org.springframework.scheduling.annotation. Code trên là đoạn ghép vào ứng dụng đầy đủ, **không nằm trong project chạy ở mục 7**. Nó gọi qua **bean khác** để Spring cache proxy áp dụng **@CachePut**. Khi triển khai nhiều replica, mỗi instance có thể cùng chạy job; cần xác định một scheduler duy nhất/coordination nếu không muốn nhân tải.

Scheduler **khác** expiration/refreshAfterWrite: nó thực sự có lịch nạp lại được xác định bởi ứng dụng; nhưng vẫn phải biết key nào cần nạp, xử lý lỗi và tránh công việc quá nhiều. Refresh tất cả key cứ vài giây có thể còn đắt hơn để cache tự miss.

## 10. Race, lỗi refresh và bảo đảm độ mới

### 10.1. Refresh đang chạy, nguồn dữ liệu đồng thời thay đổi

~~~text
t0: Thread A đọc v1 để refresh P01 (loader chậm).
t1: Thread B cập nhật DB lên v2 và evict P01.
t2: Thread A kết thúc muộn, ghi lại v1 vào cache.
t3: Request C cache hit v1, dù DB đã là v2.
~~~

TTL ngắn không tự giải quyết race này: value v1 có thể được ghi mới **sau** eviction. Cần chính sách phù hợp như versioned key/value, kiểm tra revision, invalidation after-commit hoặc thiết kế cache-aside có ordering.

### 10.2. Stampede khi expiration

Khi một hot key hết TTL, nhiều request có thể cùng cache miss và gọi DB. **@Cacheable(sync = true)** khi provider hỗ trợ có thể phối hợp loader cùng key; nó không phải **TTL**, không phải refresh và không tự đảm bảo cluster-wide single-flight. Với nhiều key hết hạn cùng lúc, có thể dùng TTL jitter, proactive refresh, giới hạn concurrency và bulkhead.

### 10.3. Refresh lỗi

- **@CachePut:** method refresh phải chạy và có kết quả; exception có thể khiến put không hoàn thành.
- **Caffeine LoadingCache refresh:** cơ chế async có thể giữ giá trị cũ nếu reload lỗi; cần giám sát exception và giới hạn tuổi stale.
- **Expiration:** key đã hết hạn thường không được dùng như hit dù backend đang lỗi, trừ khi ứng dụng thiết kế cơ chế fallback/stale riêng.
- **Redis/cache phân tán:** phải test lỗi mạng, serialization và cách app fallback nếu CacheManager không truy cập được.

Một chiến lược stale-while-revalidate rất hữu ích với dữ liệu cho phép cũ ngắn hạn, nhưng **không được áp dụng máy móc** cho thông tin đòi nhất quán nghiêm ngặt như số dư hoặc trạng thái quyền truy cập.

## 11. Tiêu chí lựa chọn

| Nhu cầu | Lựa chọn thường phù hợp | Giới hạn |
| --- | --- | --- |
| Cache dữ liệu ít thay đổi, chấp nhận stale vài phút | **expireAfterWrite** | Request sau TTL có thể chờ nạp lại |
| Thu hồi key ít được đọc | **expireAfterAccess** | Hot key không tự cập nhật nguồn |
| Giảm độ trễ của hot key | **refreshAfterWrite** + loader | Có thể trả stale trong lúc async reload |
| Làm mới ngay sau sự kiện nguồn đổi | **@CachePut** hoặc event-driven update | Tốn một lượt nạp nguồn và cần xử lý race |
| Không muốn đọc bản cũ sau cập nhật | **@CacheEvict** và policy consistency | Request kế tiếp phải chịu cache miss |
| Nạp sẵn key theo kế hoạch | Scheduler/warmup có kiểm soát | Chi phí nạp dù chưa có request |
| Muốn kết quả luôn rất mới và đúng | Versioning, invalidation sau commit, hoặc không cache | Phức tạp hoặc latency cao hơn |
| Nhiều replica, backend đắt | Kết hợp per-key coordination và chiến lược TTL/refresh | Cần kiểm chứng provider/lock ở cấp cluster |

Cần xác định **freshness SLA**: dữ liệu có thể cũ tối đa bao lâu, sau khi chính người dùng cập nhật có cần thấy ngay không, lúc nguồn lỗi có được trả stale không, và độ trễ p95/p99 chấp nhận bao nhiêu. **Hit ratio không đủ**: cache có hit cao nhưng dữ liệu quá cũ vẫn sai về nghiệp vụ.

## 12. Checklist kiểm thử vòng đời dữ liệu

| Ca kiểm thử | Cách thiết lập | Điều kiện đạt |
| --- | --- | --- |
| Trước TTL | Đọc cùng key nhiều lần | Method @Cacheable chỉ chạy một lần |
| Nguồn đổi trong TTL | Đổi version nguồn, không evict/refresh | Cache vẫn trả bản đã lưu nếu chưa hết hạn |
| TTL hết | Tiến clock vượt expireAfterWrite | Lần đọc sau miss và lấy version mới |
| Refresh sớm | @CachePut trước TTL | Value mới được ghi; tuổi write đặt lại theo provider |
| Hai key có lịch khác nhau | Refresh P01, để P02 cũ | P01/P02 hết hạn ở hai mốc khác nhau |
| Eviction | Đảm bảo entry đang tồn tại rồi @CacheEvict | Entry biến mất; read sau mới load |
| refreshAfterWrite | LoadingCache có loader và fake clock | Chỉ entry đủ điều kiện và được đọc mới trigger reload |
| Async refresh | Cố ý làm chậm reload | Xác minh old/stale và value mới sau completion |
| Loader lỗi | Source ném exception | Kiểm tra stale/error policy, không retry vô hạn |
| Nhiều luồng miss | Burst một hot key | Không tăng backend load ngoài mức chấp nhận |
| Nhiều replica | Chạy qua cluster/local cache | Hiểu đúng ranh giới consistency |
| DB commit + cache update | Kịch bản race | Không tạo lại stale entry sau invalidation |

**Không nên dùng Thread.sleep(300000)** cho unit/integration test TTL nếu provider hỗ trợ ticker/clock giả lập. Với Redis, clock được quản lý ở phía server nên cần test bằng môi trường tương ứng; thay Clock Java đơn thuần không đổi TTL của Redis.

## 13. Lỗi phổ biến và câu hỏi tự kiểm tra

- **Nghĩ TTL là lịch refresh:** expire không tự gọi repository.
- **Nghĩ Spring @Cacheable tự có TTL mặc định:** thực tế phụ thuộc store.
- **Dùng expireAfterAccess để giới hạn tuổi tuyệt đối:** hot key có thể giữ dữ liệu cũ.
- **Nhầm refreshAfterWrite với job chạy nền đúng giờ:** Caffeine thường đợi truy cập vào entry đủ điều kiện.
- **Chỉ cấu hình refreshAfterWrite nhưng không có loader phù hợp:** không có cơ chế nạp đúng như kỳ vọng.
- **Gọi @CacheEvict rồi khẳng định cache được refresh:** entry chỉ bị xóa.
- **Gọi this.refresh(...) trong cùng bean:** proxy có thể không intercept.
- **Làm mới key không chứa tenant/currency:** có nguy cơ thay dữ liệu sai ngữ cảnh.
- **Cho rằng TTL ngắn loại bỏ race:** refresh hoàn thành muộn vẫn có thể ghi stale sau evict.
- **Bỏ qua trường hợp nguồn lỗi:** cần có giới hạn stale, timeout và chính sách fallback.
- **Tăng refresh tần suất vô hạn:** có thể tiêu tốn tài nguyên backend hơn cả cache miss.

Tự trả lời:

1. Nếu entry expire sau 5 phút nhưng không ai đọc lại, Spring có tự chạy method tải nguồn không?
2. Vì sao expireAfterAccess có thể giữ một hot key cũ rất lâu?
3. Với @CachePut, điều gì bắt buộc xảy ra trước khi cache nhận value mới?
4. Vì sao một lần @CacheEvict không đồng nghĩa đã refresh?
5. Khi refreshAfterWrite đủ hai phút, điều kiện nào thường kích hoạt Caffeine reload?
6. Tại sao lần đọc kích hoạt refresh async có thể nhận value cũ?
7. Trong demo, tại sao P01 còn hạn phút 6 nhưng P02 phải nạp lại?
8. Vì sao invalidation và refresh chồng nhau có thể đưa v1 cũ trở lại cache?
9. Nếu cần luôn đọc mới sau transaction commit, TTL có đủ không?

**Kết luận:** **Hết hạn** quy định khi bản cache không còn hợp lệ. **Làm mới** là đọc lại nguồn và cập nhật value. Trong Spring, annotation mô tả lookup, put và evict; provider quyết định policy thời gian, còn lịch refresh và mức nhất quán phải được thiết kế rõ. Hãy kiểm thử thời điểm, giá trị, key, lỗi và race thay vì đánh đồng hai khái niệm.

### Tài liệu tham khảo

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cấu hình cache store: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — @Cacheable, @CachePut và @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching và cấu hình Caffeine: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Refresh wiki: https://github.com/ben-manes/caffeine/wiki/Refresh
- Caffeine — Expiration wiki: https://github.com/ben-manes/caffeine/wiki/Expiration
- Spring Data Redis — Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html

# Thiết lập hết hạn theo lần ghi hoặc lần truy cập

Khi tích hợp **Caffeine** với **Spring Framework Cache**, hai lựa chọn rất dễ bị nhầm là **expireAfterWrite** và **expireAfterAccess**. Chúng đều loại bỏ khả năng sử dụng một entry quá hạn, nhưng **đồng hồ đo tuổi được đặt lại bởi các sự kiện khác nhau**:

- **expireAfterWrite:** entry hết hạn sau một khoảng thời gian kể từ khi nó **được tạo hoặc được cập nhật giá trị thành công**. Chỉ đọc lại entry **không** đặt lại đồng hồ hết hạn.
- **expireAfterAccess:** entry hết hạn sau một khoảng thời gian **không được truy cập**. Một lần đọc hoặc ghi thành công đối với entry có thể bắt đầu lại khoảng thời gian chờ. Key được đọc liên tục có thể ở lại cache rất lâu.

Hai chính sách này ảnh hưởng tới tính mới của dữ liệu, tỷ lệ hit, dung lượng bộ nhớ và áp lực lên backend. Quan trọng hơn, **hết hạn không phải là làm mới dữ liệu**: một key expired thường được nạp lại **khi một lời gọi tiếp theo tạo miss**, chứ Caffeine không tự gọi method **@Cacheable** theo lịch.

Bài học tập trung vào cấu hình chính xác hai chính sách trên, cách gắn chúng vào **CaffeineCacheManager**, khả năng kết hợp các quy tắc, và cách viết bài kiểm thử có **ticker giả lập** để không phải chờ nhiều phút thật.

## 1. Định nghĩa từ góc nhìn của một entry

Giả sử hai cache độc lập đều có duration là **5 phút**, và cả hai nhận value mới lúc **10:00**.

| Sự kiện | expireAfterWrite(5 phút) | expireAfterAccess(5 phút) |
| --- | --- | --- |
| 10:00: ghi value lần đầu | Mốc tính từ 10:00 | Mốc tính từ 10:00 |
| 10:03: đọc thành công | Không đổi mốc write; hạn vẫn khoảng 10:05 | Đổi mốc last access thành 10:03; hạn khoảng 10:08 |
| 10:05: đọc key | Entry theo write đã hết hạn: miss | Entry theo access vẫn hợp lệ: hit, kéo hạn tới khoảng 10:10 |
| 10:09: lại đọc key (nếu không có lượt truy cập khác sau 10:05) | Value đã được nạp lại ở miss 10:05, có tuổi write mới | Hit theo access nếu vẫn chưa quá 5 phút kể từ 10:05 |
| Không ai đọc trong 20 phút | Sẽ bị coi là hết hạn khi được kiểm tra | Sẽ bị coi là hết hạn khi được kiểm tra |

Mỗi hàng của bảng giả định không có sự kiện khác ngoài những sự kiện đã nêu. Với một cache được ghi lại lúc 10:05, **expireAfterWrite** tính tuổi từ lần ghi **mới**, không phải giữ lại hạn 10:05 của value cũ.

**Tư duy ngắn gọn:** expireAfterWrite là **thời gian sống kể từ lần ghi**, còn expireAfterAccess là **thời gian rảnh tối đa kể từ lần truy cập**.

## 2. Tại sao phải chọn đúng?

### 2.1. Dữ liệu đổi theo thời gian

Giả sử nguồn báo giá thay đổi từ **100** thành **120** ở phút 2 nhưng cache vẫn đang giữ **100**. Với **expireAfterWrite(5m)**, lần đọc sau phút 5 thường tạo miss và tải lại giá mới. Điều này đặt một giới hạn thời gian cho tuổi của **entry được lưu**, không bảo đảm snapshot lúc tải luôn đồng nhất với nguồn.

Với **expireAfterAccess(5m)**, nếu người dùng cứ gọi mỗi phút, mỗi lượt hit có thể dời mốc hết hạn; entry **100** có thể được trả trong nhiều giờ dù nguồn là **120**. Đây không phải lỗi Caffeine: chính sách được thiết kế để **dọn những entry không dùng**, chứ không phải ràng buộc tuổi dữ liệu tối đa.

**Khi nội dung phải đủ mới**, hãy cân nhắc expireAfterWrite, invalidation khi nguồn đổi, hoặc chính sách refresh/versioning phù hợp. Với dữ liệu chỉ cần giảm footprint, expireAfterAccess có thể hợp lý hơn.

### 2.2. Tài nguyên và hit ratio

expireAfterWrite sẽ buộc hot key hết hạn dù rất nhiều người vẫn đang dùng. Việc phải tải lại hot key có thể tạo thêm backend calls và độ trễ, nhưng tránh việc giữ một entry mãi chỉ vì có truy cập liên tục.

expireAfterAccess giữ lại hot key lâu, giảm tải lại những item đang phổ biến và dọn item ít dùng. Tuy nhiên, nếu dữ liệu nguồn đổi thường xuyên, hit ratio cao có thể che giấu lỗi **stale data**.

### 2.3. Expiration khác eviction và refresh

- **Expiration**: hết hạn theo policy thời gian; lookup sau hạn không nên trả như entry đang hợp lệ.
- **Size-based eviction**: loại entry vì ràng buộc dung lượng, ví dụ **maximumSize(10_000)**.
- **Explicit invalidation**: xóa có chủ đích khi dữ liệu nguồn đổi, thông qua **@CacheEvict**, **cache.invalidate(key)** hoặc cơ chế khác.
- **Refresh**: thực sự tải và thay một giá trị mới. Ví dụ Spring **@CachePut** chạy method để lấy kết quả mới; hoặc Caffeine **refreshAfterWrite** với **LoadingCache** hỗ trợ reload.

Một lần **invalidate** không tự động gọi DB. Một entry **expired** không nhất thiết được tải lại nếu chưa có lần đọc. Đọc cache **hit** không tương đương với việc refresh value từ nguồn.

## 3. Cấu hình Caffeine builder thuần Java

Hai cấu hình độc lập, chỉ khác chính sách thời gian:

~~~java
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;

// Mã minh họa: tạo hai cache với chính sách riêng.
var writeCache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .build();

var accessCache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterAccess(Duration.ofMinutes(5))
        .build();
~~~

Trong dự án Java 17 thực tế, bạn nên chỉ định kiểu generic cho các cache (ví dụ **Cache<String, Product>**) để compiler kiểm tra giá trị. Code ở trên chỉ minh họa cấu hình; ví dụ Spring **có thể chạy đầy đủ** ở phần sau sử dụng CacheManager, dependency và các file cụ thể.

**Duration** phải là khoảng thời gian hợp lệ. Với Spring/Caffeine theo quy định của version đang dùng, thử các giá trị biên (0, negative, giá trị rất lớn) bằng test thay vì tự dự đoán. Thực tế thường chọn duration dương có ý nghĩa cho nghiệp vụ.

**maximumSize** là giới hạn dung lượng theo thuật toán eviction dựa trên số entry, **không** phải TTL. Một entry có thể bị loại trước khi hết hạn vì áp lực bộ nhớ.

### Có thể kết hợp expireAfterWrite và expireAfterAccess không?

Có thể cấu hình cả hai trên cùng cache:

~~~java
Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(30))
    .expireAfterAccess(Duration.ofMinutes(5));
~~~

Trong trường hợp này, một entry sẽ hết hạn khi **một trong những điều kiện expiration áp dụng** đã được thỏa mãn: quá 30 phút từ lần ghi/cập nhật, hoặc không được truy cập trong 5 phút. Hot key được truy cập liên tục có thể tránh hết hạn do idle nhưng vẫn hết hạn theo **write age**. Đây là cách kết hợp giới hạn tuổi cứng và dọn dữ liệu ít dùng.

Không nhầm điều này với việc muốn “chỉ hết hạn khi cả hai điều kiện đều đúng”. Khi cần semantics đặc biệt theo giá trị của mỗi entry, Caffeine còn có **Expiry** tùy biến (expireAfterCreate/Update/Read), nhưng chỉ nên dùng khi yêu cầu thực sự cần và phải kiểm thử kỹ.

## 4. Gắn Caffeine vào Spring Framework Cache

Spring Cache là một abstraction. **@Cacheable** nói khi nào đọc/ghi giá trị; **CaffeineCacheManager** và Caffeine builder nói entry sống bao lâu.

Ví dụ cấu hình một cache hết hạn sau khi ghi:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }
}
~~~

Các import quan trọng: **@Configuration**, **@Bean** từ Spring context, **@EnableCaching** từ Spring cache annotation, **CacheManager** từ Spring cache, **CaffeineCacheManager** từ **spring-context-support** và **Caffeine** từ thư viện Caffeine.

Phương thức service:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product loadProduct(String id) {
    return repository.findById(id);
}
~~~

Sau một lần miss, Spring thực thi **loadProduct**, đưa value vào cache. Đọc lại trước hạn sẽ hit, không chạy method. Đọc sau hạn tạo miss và nạp lại, **không cần một cron job mới**.

Muốn chính sách expireAfterAccess, thay cấu hình builder thành:

~~~java
manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterAccess(Duration.ofMinutes(5)));
~~~

**Không nên chỉ thêm @Cacheable rồi chờ Spring tự expire:** nếu provider đang là **ConcurrentMapCacheManager**, cache map local không có TTL mặc định của Caffeine. Cấu hình phải thật sự dùng **CaffeineCacheManager** và dependency phù hợp.

### Các cache cần TTL khác nhau

Một **CaffeineCacheManager** được cấu hình chung thường áp dụng cùng builder cho những cache do nó quản lý. Nếu **products** cần expireAfterWrite 5m còn **sessionHints** cần expireAfterAccess 5m, có thể dùng **hai CacheManager bean** với tên riêng hoặc quản lý các native cache riêng theo API của version.

Ở ví dụ chạy được bên dưới, ta sử dụng **hai CacheManager bean** và chỉ định **cacheManager = "writeManager"** / **cacheManager = "accessManager"** trực tiếp trong annotation để tránh nhập nhằng. Không cần dựa vào may mắn Spring chọn đúng CacheManager khi có hơn một bean.

## 5. Ví dụ thực tế: một key, hai đồng hồ khác nhau

Ta dùng hai cache độc lập, mỗi cache bắt đầu với value **v1** ở **t=0**. Nguồn dữ liệu sau đó đổi version, nhưng cache không biết cho tới khi có miss.

| Thời điểm | Nguồn | Cache expireAfterWrite(5m) | Cache expireAfterAccess(5m) |
| --- | --- | --- | --- |
| **t0** | v1 | Miss, nạp v1; lần ghi đầu | Miss, nạp v1 |
| **t3** | đổi thành v2 | Hit v1; chỉ đọc, mốc write vẫn t0 | Hit v1; đặt mốc access thành t3 |
| **t5** | v2 | Entry t0 hết hạn, nạp v2 | Hit v1 vì mới 2 phút từ t3; mốc access thành t5 |
| **t9** | v2 | Hit v2 vì mới 4 phút từ write t5 | Hit v1 vì mới 4 phút từ access t5; mốc access thành t9 |
| **t15** | đổi thành v3 | Entry được ghi ở t5 đã quá 5 phút: nạp v3 | Đã 6 phút từ access t9: nạp v3 |

**Đây là cùng một key "P01"**, nhưng hai cache có chính sách khác nhau nên source loads khác nhau. Ví dụ cố tình làm dữ liệu nguồn đổi ở t3 để chứng minh **expireAfterAccess có thể trả stale lâu hơn expireAfterWrite**.

Bộ đếm dự kiến sau t15: **write loads = 3**, **access loads = 2**. Chúng chỉ đếm khi thân method **@Cacheable** thực thi, không đếm những lần cache hit.

## 6. Dự án Java 17 + Spring 6.1 + Caffeine chạy được

Dự án **Spring Framework 6.1.14**, **Caffeine 3.1.8**, **JUnit Jupiter 5.10.2** và Gradle sử dụng **ticker giả lập**. Không cần database thật hay đợi 5 phút bằng **Thread.sleep**; ta chủ động tiến đồng hồ cache.

Cấu trúc:

~~~text
caffeine-expiration-policies/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/ExpiryPolicyDemo.java
└── src/test/java/demo/cache/ExpiryPolicyDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'caffeine-expiration-policies'
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
    mainClass = 'demo.cache.ExpiryPolicyDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/ExpiryPolicyDemo.java**

~~~java
package demo.cache;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.Ticker;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ExpiryPolicyDemo {

    public static final class MutableTicker implements Ticker {
        private final AtomicLong nanos = new AtomicLong();

        @Override
        public long read() {
            return nanos.get();
        }

        public void advance(Duration duration) {
            if (duration.isNegative()) {
                throw new IllegalArgumentException("Clock cannot go back");
            }
            nanos.addAndGet(duration.toNanos());
        }
    }

    public static final class DataSource {
        private final AtomicInteger revision = new AtomicInteger(1);

        public String value(String id) {
            return id + ":v" + revision.get();
        }

        public void nextRevision() {
            revision.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public MutableTicker ticker() {
            return new MutableTicker();
        }

        @Bean
        public DataSource dataSource() {
            return new DataSource();
        }

        @Bean("writeManager")
        public CacheManager writeManager(MutableTicker ticker) {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("byWrite");
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofMinutes(5))
                    .ticker(ticker));
            return manager;
        }

        @Bean("accessManager")
        public CacheManager accessManager(MutableTicker ticker) {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("byAccess");
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterAccess(Duration.ofMinutes(5))
                    .ticker(ticker));
            return manager;
        }

        @Bean
        public ProductService productService(DataSource source) {
            return new ProductService(source);
        }
    }

    public static class ProductService {
        private final DataSource source;
        private final AtomicInteger writeLoads = new AtomicInteger();
        private final AtomicInteger accessLoads = new AtomicInteger();

        public ProductService(DataSource source) {
            this.source = source;
        }

        @Cacheable(
            cacheManager = "writeManager",
            cacheNames = "byWrite",
            key = "#p0"
        )
        public String byWrite(String id) {
            int loadNumber = writeLoads.incrementAndGet();
            return "W:" + source.value(id) + ":load" + loadNumber;
        }

        @Cacheable(
            cacheManager = "accessManager",
            cacheNames = "byAccess",
            key = "#p0"
        )
        public String byAccess(String id) {
            int loadNumber = accessLoads.incrementAndGet();
            return "A:" + source.value(id) + ":load" + loadNumber;
        }

        public String counts() {
            return "write=" + writeLoads.get()
                    + ",access=" + accessLoads.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                Config.class)) {
            ProductService service =
                    context.getBean(ProductService.class);
            DataSource source = context.getBean(DataSource.class);
            MutableTicker clock = context.getBean(MutableTicker.class);

            System.out.println("t0-write=" + service.byWrite("P01"));
            System.out.println("t0-access=" + service.byAccess("P01"));

            source.nextRevision(); // Nguồn từ v1 lên v2.
            clock.advance(Duration.ofMinutes(3));
            System.out.println("t3-write=" + service.byWrite("P01"));
            System.out.println("t3-access=" + service.byAccess("P01"));

            clock.advance(Duration.ofMinutes(2));
            System.out.println("t5-write=" + service.byWrite("P01"));
            System.out.println("t5-access=" + service.byAccess("P01"));

            clock.advance(Duration.ofMinutes(4));
            System.out.println("t9-write=" + service.byWrite("P01"));
            System.out.println("t9-access=" + service.byAccess("P01"));

            source.nextRevision(); // Nguồn từ v2 lên v3.
            clock.advance(Duration.ofMinutes(6));
            System.out.println("t15-write=" + service.byWrite("P01"));
            System.out.println("t15-access=" + service.byAccess("P01"));

            System.out.println("loads=" + service.counts());
        }
    }
}
~~~

Trong đoạn code này, **@Bean("writeManager")** và **@Bean("accessManager")** tạo hai CaffeineCacheManager riêng, dùng **cùng ticker nhưng hai cache độc lập**. **cacheManager = ...** trên từng annotation buộc Spring chọn đúng chính sách cho method. Lời gọi vào **ProductService** được lấy từ **ApplicationContext**, nên proxy/advice cache thực sự có cơ hội hoạt động. Nếu tự viết **new ProductService(source)**, annotation không tự kích hoạt trong một object thường.

### Chạy và hiểu stdout

Tại thư mục **caffeine-expiration-policies**, dùng Gradle cài sẵn tương thích Java 17 hoặc wrapper sẵn có:

~~~bash
gradle run --quiet
~~~

Các dòng **System.out.println** dự kiến, theo đúng thứ tự:

~~~text
t0-write=W:P01:v1:load1
t0-access=A:P01:v1:load1
t3-write=W:P01:v1:load1
t3-access=A:P01:v1:load1
t5-write=W:P01:v2:load2
t5-access=A:P01:v1:load1
t9-write=W:P01:v2:load2
t9-access=A:P01:v1:load1
t15-write=W:P01:v3:load3
t15-access=A:P01:v3:load2
loads=write=3,access=2
~~~

Cách đọc:

1. Ở t0, cả hai cache chưa có P01 nên mỗi method chạy một lần và trả v1.
2. Nguồn chuyển v2 tại t3. Hai cache vẫn còn hạn, vì vậy vẫn trả v1. Đặc biệt, lần đọc access cache kéo mốc expiration tới khoảng t8.
3. Tại t5, write cache **đã đủ 5 phút kể từ t0**, nạp lại v2 và đặt mốc write thành t5. Access cache chỉ mới **2 phút kể từ lượt đọc t3**, vì vậy vẫn hit v1, dời mốc lần truy cập thành t5.
4. Tại t9, write cache mới 4 phút từ write t5 nên hit v2. Access cache mới 4 phút từ access t5 nên hit v1, dời mốc đến t9.
5. Tại t15, write cache quá 5 phút tính từ lần ghi t5, access cache quá 5 phút tính từ lần đọc t9. Cả hai miss và nạp version mới v3. Bộ đếm cuối **write=3, access=2**.

**Điểm quan trọng:** cache **byAccess** giữ nguyên v1 suốt từ t0 tới t15 dù nguồn đã chuyển v2 ở t3, chỉ vì các hit ở t3, t5, t9 liên tục kéo tuổi truy cập. Đây chính là sự đánh đổi khi chọn expireAfterAccess cho dữ liệu có yêu cầu freshness.

## 7. Kiểm thử JUnit 5 với clock giả lập

**src/test/java/demo/cache/ExpiryPolicyDemoTest.java**

~~~java
package demo.cache;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ExpiryPolicyDemo.Config.class)
class ExpiryPolicyDemoTest {

    @Autowired
    ExpiryPolicyDemo.MutableTicker ticker;

    @Autowired
    ExpiryPolicyDemo.DataSource source;

    @Autowired
    ExpiryPolicyDemo.ProductService service;

    @Test
    void readHitExtendsAccessButNotWriteExpiration() {
        assertEquals("W:P01:v1:load1", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=1,access=1", service.counts());

        source.nextRevision();
        ticker.advance(Duration.ofMinutes(3));
        assertEquals("W:P01:v1:load1", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=1,access=1", service.counts());

        ticker.advance(Duration.ofMinutes(2));
        assertEquals("W:P01:v2:load2", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));
        assertEquals("write=2,access=1", service.counts());

        ticker.advance(Duration.ofMinutes(4));
        assertEquals("W:P01:v2:load2", service.byWrite("P01"));
        assertEquals("A:P01:v1:load1", service.byAccess("P01"));

        source.nextRevision();
        ticker.advance(Duration.ofMinutes(6));
        assertEquals("W:P01:v3:load3", service.byWrite("P01"));
        assertEquals("A:P01:v3:load2", service.byAccess("P01"));
        assertEquals("write=3,access=2", service.counts());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** một bài test JUnit thành công. Test không dựa vào tốc độ máy hoặc ngủ 5 phút; **MutableTicker** điều khiển đồng hồ của Caffeine cho cả hai policy. Assertions quan sát **giá trị trả về và bộ đếm thân method**, không chỉ kiểm tra một value tồn tại trong cache. Điều đó xác minh rằng các lần hit không làm chạy lại method, còn expiration tạo miss và nạp nguồn mới.

**Phạm vi demo:** minh họa hai kiểu expiration, không phải **refreshAfterWrite**. Tất cả diễn ra trong **một JVM** với Caffeine và Spring proxy. Lệnh Gradle là lệnh hướng dẫn tái hiện; các dòng stdout là kết quả dự kiến của chương trình, không phải log build đã được chạy sẵn.

### Điều cần tránh khi viết test expiration

- **Không dùng Thread.sleep(300000)** để chờ TTL: test chậm, dễ biến động. Dùng ticker của provider như trên.
- **Không so sánh đúng một mốc biên rồi suy diễn mọi trường hợp**: test nên có trước hạn, tại/sau hạn, và nhiều lần hit.
- **Không truy cập cache phụ ngoài test rồi quên nó có thể đặt lại access time**: mỗi lần **get** từ access cache có thể dời mốc hết hạn.
- **Không gộp hai policy vào cùng một cache cho bài test so sánh độc lập**: mỗi policy cần một cache riêng để quan sát.
- **Không bỏ qua proxy**: nếu gọi trực tiếp đối tượng bằng **new**, annotation cache không chạy nên counter sẽ tăng mỗi lần.
- **Không quên reset state giữa các test**: ví dụ hiện chỉ có một test; nếu thêm test mới trong cùng Spring context, cần clear cache, reset clock, revision và counter hoặc tạo context riêng để các ca độc lập.

## 8. Cấu hình Spring Boot: chọn một hay nhiều cache policy

Nếu dùng Spring Boot có **spring-boot-starter-cache** và dependency Caffeine, có thể dùng cùng một cấu hình cho các cache do Boot tạo:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,productSummary
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=5m
~~~

Đây là **TTL sau write** cho các cache tương ứng; **không** phải lịch tự chạy lại phương thức Spring mỗi năm phút. Muốn policy sau access:

~~~properties
spring.cache.type=caffeine
spring.cache.caffeine.spec=maximumSize=10000,expireAfterAccess=5m
~~~

Hai block properties là **hai phương án độc lập**; không áp dụng cả hai block rồi mặc định mỗi cache tự có một loại khác nhau. Nếu từng cache cần chính sách riêng, cấu hình các CacheManager/cache cụ thể trong Java (như demo), hoặc sử dụng cấu hình native per-cache nếu version hỗ trợ.

Trong cấu hình ứng dụng thực tế, **cache name** và **key** trong @Cacheable phải trùng những cache mà CaffeineCacheManager quản lý. Nếu annotation tham chiếu sai cache name hoặc sai CacheManager, TTL bạn đã đặt có thể không áp dụng lên đường đọc đó.

## 9. expireAfterWrite, refreshAfterWrite và @CachePut khác nhau

Rất dễ nghe chữ “write” trong ba tên rồi coi chúng như nhau:

- **expireAfterWrite(5m):** qua năm phút tính từ lần ghi cuối, entry không còn hợp lệ. Không tự nạp trước hạn.
- **refreshAfterWrite(5m):** với **Caffeine LoadingCache/AsyncLoadingCache có loader**, khi entry đã đủ tuổi, lần đọc tiếp theo có thể kích hoạt **reload bất đồng bộ**, thường vẫn trả value cũ trong lúc chờ. Không tương đương expiration cứng.
- **@CachePut:** Spring chạy method được gọi và cập nhật value; nó không phải timer và không được kích hoạt chỉ vì có dòng cấu hình TTL.

Ví dụ Caffeine LoadingCache thuần Java (minh họa trong ứng dụng có repository):

~~~java
LoadingCache<String, Product> cache = Caffeine.newBuilder()
    .refreshAfterWrite(Duration.ofMinutes(5))
    .expireAfterWrite(Duration.ofMinutes(30))
    .build(id -> repository.load(id));
~~~

Một entry **đủ điều kiện** refresh sau năm phút không đồng nghĩa đã được refresh ngay đúng mốc. Nếu không có lời gọi đọc, Caffeine thường không kích hoạt reload. Khi reload chạy, có thể vẫn nhận value cũ một thời gian. Với Spring **CaffeineCacheManager**, cần đăng ký Loader phù hợp và kiểm tra underlying cache; chỉ thêm **@Cacheable** không tự biến method thành loader cho refreshAfterWrite.

Có thể dùng **@CacheEvict** khi dữ liệu đổi để xóa entry cũ và cho lần đọc sau nạp lại; nhưng invalidate **không tự tải** value mới. Nếu cần chủ động nạp, gọi một service **@CachePut** qua proxy, prewarm theo sự kiện, hoặc thiết kế refresh riêng.

## 10. Kết hợp thời gian sống với an toàn và tính nhất quán

### 10.1. Hot key và stale data

Nếu giá, quyền truy cập hoặc trạng thái giao dịch thay đổi trong DB, chọn expireAfterAccess chỉ vì hit ratio cao có thể nguy hiểm: một key được truy cập liên tục có thể tồn tại lâu hơn mức cũ được phép.

Hãy xác định **freshness SLA**: dữ liệu có thể cũ tối đa bao lâu sau nguồn đổi? Có cần read-your-writes không? Dữ liệu có ảnh hưởng bảo mật không? Không nên thay permission check bằng TTL hoặc cache key có tenant.

Nếu cần giới hạn tuổi tuyệt đối của bản cache, thường nghiêng về **expireAfterWrite**, hoặc kết hợp nó với **expireAfterAccess** để dọn dữ liệu ít dùng. Nhưng ngay cả expireAfterWrite cũng không tự bảo đảm đồng bộ tuyệt đối với DB trong mọi trường hợp transaction/race.

### 10.2. Expiration và race khi update

~~~text
t0: Luồng A thấy entry hết hạn và bắt đầu nạp giá v1.
t1: Luồng B cập nhật DB lên v2 rồi evict key đó.
t2: Luồng A kết thúc muộn và ghi lại v1 vào cache.
t3: Request tiếp theo hit v1 dù DB đã là v2.
~~~

TTL ngắn chưa loại bỏ race giữa load và update. Khi cần consistency mạnh, xem xét versioned keys, ordering theo revision, invalidation sau commit hoặc đọc nguồn phù hợp. Dùng **@Cacheable(sync = true)** với provider hỗ trợ có thể giảm trùng loader trên cùng key, nhưng không tự giải quyết mọi race read/write hay đảm bảo single-flight giữa nhiều replica.

### 10.3. Hết hạn đồng loạt và áp lực tải

Nếu hàng nghìn key được ghi gần như cùng lúc và có cùng expireAfterWrite 5m, chúng có thể đồng loạt miss sau năm phút, tạo **cache avalanche**. Nếu nhiều request cùng miss **một hot key**, có thể xuất hiện **cache stampede**. Các lựa chọn giảm tải gồm TTL jitter (khi có thể cấu hình), prewarm, refresh có giới hạn, bulkhead và điều phối per-key. expireAfterAccess có thể phân tán một số mốc theo hành vi truy cập nhưng **không phải bảo đảm** tránh mọi spike.

### 10.4. Caffeine là cache trong JVM

Một CaffeineCacheManager thường giữ cache local theo từng application instance. Nếu có ba replica, mỗi replica có last-access/write timestamps và entries riêng. Đừng nhầm cấu hình một cache local với TTL thống nhất trong Redis hoặc shared cache. Nhu cầu nhất quán nhiều node có thể cần một provider tập trung hoặc invalidation được phát tán.

## 11. Khi nào nên dùng policy nào?

| Nhu cầu nghiệp vụ | Ưu tiên cân nhắc | Điều cần kiểm tra |
| --- | --- | --- |
| Sản phẩm/giá phải có giới hạn tuổi cache rõ | **expireAfterWrite** | Tốc độ thay đổi nguồn, stale window, áp lực nạp lại |
| Cache lookup/reference data rất ít đổi và truy cập không đều | **expireAfterAccess** | Có chấp nhận entry hot tồn tại lâu không? |
| Cần vừa loại key idle, vừa giới hạn tuổi dữ liệu | **Kết hợp write + access expiration** | Điều kiện nào khiến entry hết hạn trước? |
| Dữ liệu thay ngay sau thao tác ghi DB | **@CacheEvict** hoặc **@CachePut** có thứ tự phù hợp | Quy tắc key, transaction commit và race |
| Hot key cần latency ổn định khi gần hết hạn | **refreshAfterWrite** với loader thích hợp | Có thể trả stale? Reload lỗi thì sao? |
| Muốn giới hạn bộ nhớ | **maximumSize/maximumWeight** | Eviction do size độc lập với expiration |
| Dữ liệu quá nhạy cảm để cho phép stale | Chính sách consistency chặt hoặc không cache | Phân quyền, transaction, versioning |

Không có policy thắng trong mọi trường hợp. **expireAfterWrite** thuận tiện để giữ tuổi bản sao có giới hạn; **expireAfterAccess** tối ưu việc dọn key nhàn rỗi và giữ hot key; kết hợp cả hai cho phép cân bằng. Quyết định cuối phải dựa vào tính đúng đắn nghiệp vụ, không chỉ benchmark hit ratio.

## 12. Kiểm thử và giám sát khi triển khai

| Kịch bản | Hành động | Kỳ vọng |
| --- | --- | --- |
| Cache lạnh | Đọc key lần đầu | Miss, method chạy |
| Hit trước hạn | Đọc cùng key sau một khoảng ngắn | Không chạy method |
| expireAfterWrite | Đọc liên tục nhưng tăng clock vượt write TTL | Cuối cùng vẫn miss |
| expireAfterAccess | Đọc trước mỗi idle TTL | Entry vẫn có thể hit dù qua nhiều write-age |
| Idle vượt ngưỡng | Không truy cập một key rồi đọc lại | Miss với access expiration |
| Cập nhật value | Ghi mới key trong cache | Cần tính lại tuổi từ thời điểm update |
| Hai policy cùng một cache | Hết hạn theo một trong hai điều kiện | Không hiểu nhầm là yêu cầu cả hai đồng thời |
| Eviction theo size | Tạo nhiều key hơn capacity | Có thể bị loại trước TTL |
| Refresh policy | Dùng LoadingCache có loader | Xác nhận reload/old-value behavior |
| Concurrency | Burst miss trên hot key | Đo loader counts, backend requests, p95/p99 |
| Nhiều instance | Truy cập qua các replica | Hiểu rõ cache local khác shared |
| Nguồn lỗi | Load thất bại sau expiration | Có exception/fallback đúng SLA |

Nên theo dõi **cache hit/miss**, số lần gọi backend, **load duration**, eviction/expiration events (nếu provider hỗ trợ quan sát), latency p95/p99, stale age, dung lượng, số entry và lỗi cache load. Không chỉ đo hit ratio: nếu dữ liệu stale quá lâu, cache vẫn có thể “hiệu quả” về số lượt hit nhưng thất bại về correctness.

Một kỹ thuật QA quan trọng là dùng **ticker ảo** trong unit/integration test. Với Caffeine, có thể truyền **.ticker(fakeTicker)** vào builder. Với cache phân tán như Redis, TTL do server quản lý nên chỉ thay Java Clock không đủ; cần test với provider hoặc môi trường giả lập phù hợp.

## 13. Lỗi phổ biến

1. **Nói “expireAfterAccess giới hạn tuổi của dữ liệu”**: không chính xác với entry nóng được đọc liên tục.
2. **Nói “expireAfterWrite bị kéo dài bởi get”**: sai; chỉ write/update reset tuổi write, không phải read hit.
3. **Nhầm expire với refresh**: expiration tạo cơ hội miss/load ở lần đọc sau, không phải lịch refresh.
4. **Gắn @Cacheable mà không cấu hình CaffeineCacheManager thật**: có thể đang chạy ConcurrentMapCache không TTL.
5. **Dùng chung một CaffeineCacheManager với một policy rồi tưởng từng cache có policy khác nhau**: phải cấu hình đúng từng manager/cache.
6. **Nhầm maximumSize với expiration**: size eviction có thể xảy ra bất kỳ lúc nào theo capacity.
7. **Đọc access cache trong test để kiểm tra mà quên đã kéo hạn**: các lần cache.get cũng là access.
8. **Dựa vào Thread.sleep vài mili-giây để test TTL nhiều phút**: không ổn định, dễ flaky.
9. **Cho rằng expired nghĩa là entry lập tức biến mất vật lý**: maintenance có thể trì hoãn dọn bộ nhớ; lookup vẫn phải tôn trọng expiration.
10. **Tưởng refreshAfterWrite là cron job**: thường chỉ trigger khi đọc entry đủ điều kiện với loader.
11. **Thay TTL để sửa race dữ liệu cũ**: load muộn sau eviction vẫn có thể ghi stale.
12. **Thiếu ngữ cảnh tenant/locale/currency trong key**: hai lời gọi khác nghĩa có thể dùng chung dữ liệu, bất kể TTL nào.
13. **Không test trên cùng provider với production**: serializer, TTL semantics và multi-instance behavior có thể khác.

## 14. Tự kiểm tra kiến thức

1. Ở t0 một entry được ghi và tại t3 nó được đọc. Với **expireAfterWrite(5m)**, t5 lookup là hit hay miss? Vì sao?
2. Với **expireAfterAccess(5m)**, nếu các lượt truy cập diễn ra mỗi 4 phút thì entry có tự hết hạn chỉ vì đã tồn tại 40 phút không?
3. Một cache có cả expireAfterWrite(30m) và expireAfterAccess(5m). Nếu không có lượt đọc nào sau t0, mốc nào xảy ra trước?
4. Đọc cache hit có khiến method **@Cacheable** thực thi không? Có đặt lại access age của Caffeine không?
5. Vì sao **@CacheEvict** không phải refresh? Khi nào source được gọi sau eviction?
6. **refreshAfterWrite** cần loại cache/loader nào và thường được kích hoạt ở thời điểm nào?
7. Vì sao demo cần hai CacheManager bean và chỉ định **cacheManager** trong hai annotation?
8. Vì sao dùng MutableTicker chính xác hơn **Thread.sleep(300000)** trong test expiration?
9. Khi ứng dụng có nhiều replica với cache local, một lần invalidation tại replica A có tự xóa entry ở B không?
10. Khi dữ liệu có giới hạn stale nghiêm ngặt, vì sao expireAfterAccess một mình có thể không phù hợp?

**Tóm tắt:** Trong Caffeine, **expireAfterWrite** đo thời gian từ lần ghi/cập nhật value và không được kéo dài bởi read hit; **expireAfterAccess** đo thời gian rảnh kể từ lần truy cập thành công và có thể giữ hot key lâu. Đặt policy tại builder/CacheManager, không kỳ vọng @Cacheable tự tạo TTL; dùng ticker giả lập để kiểm tra đúng từng mốc và chọn theo SLA độ mới của dữ liệu.

### Tài liệu chính thức và hướng dẫn kỹ thuật

- Caffeine Wiki — Expiration: https://github.com/ben-manes/caffeine/wiki/Expiration
- Caffeine Wiki — Refresh: https://github.com/ben-manes/caffeine/wiki/Refresh
- Caffeine API — Caffeine builder: https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cấu hình cache store: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — @Cacheable và @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching (Caffeine): https://docs.spring.io/spring-boot/reference/io/caching.html

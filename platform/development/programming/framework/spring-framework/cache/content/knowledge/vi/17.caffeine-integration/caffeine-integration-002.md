# Khai báo cấu hình Caffeine bằng builder hoặc chuỗi đặc tả trong Spring Cache

## Mục tiêu bài học

Khi dùng **Spring Framework Cache Abstraction** cùng **Caffeine**, bạn có thể cấu hình dung lượng, thời hạn entry và thống kê theo hai hướng phổ biến:

1. **Builder API**: viết Java với **Caffeine.newBuilder()**, truyền builder vào **CaffeineCacheManager.setCaffeine(...)**.
2. **Specification string**: khai báo chuỗi như **maximumSize=1000,expireAfterWrite=10m,recordStats** rồi đưa vào **CaffeineCacheManager.setCacheSpecification(...)**; có thể parse thành **CaffeineSpec** và gọi **setCaffeineSpec(...)**.

Cả hai cùng tạo chính sách cho native Caffeine cache; khác nhau ở mức diễn đạt, tính linh hoạt, khả năng kiểm tra và nguồn cấu hình. Bài học giúp bạn chọn cách phù hợp, chạy ví dụ Java 17, phân biệt cấu hình Caffeine với annotation Spring Cache, và tránh một số sai lầm rất thường gặp.

**Ngữ cảnh kỹ thuật:** Spring Framework **6.2.19**, Caffeine **3.2.4**, Java **17+**. Dự án runnable sử dụng Spring Framework thuần, không cần Spring Boot. Phần Spring Boot trình bày riêng vì cơ chế auto-configuration có thứ tự lựa chọn khác với việc tự viết nhiều setter trên một CacheManager.

## 1. Ba lớp trong tích hợp Spring Cache – Caffeine

~~~text
Ứng dụng gọi Spring bean @Cacheable / @CachePut / @CacheEvict
                      |
                      v
           Spring CacheInterceptor
              cacheName + key
                      |
                      v
       Spring CacheManager (CaffeineCacheManager)
                      |
              getCache("products")
                      |
                      v
          Spring CaffeineCache adapter
                      |
                      v
        Caffeine native cache trong JVM
    maximumSize / expiry / stats / eviction
~~~

- **@Cacheable, @CachePut, @CacheEvict** định nghĩa **operation** đọc, ghi hoặc xóa và thường xác định cache name, key và điều kiện.
- **CaffeineCacheManager** là adapter cấp manager cho Spring. Nó tạo/đăng ký các **CaffeineCache** và chọn cache theo tên.
- **Caffeine.newBuilder()** hoặc **CaffeineSpec** định nghĩa **chính sách của native cache**: giới hạn số entry, thời điểm hết hạn, thu thập thống kê, v.v.
- **CaffeineCache** nối giao diện **org.springframework.cache.Cache** với implementation native của Caffeine.

Sự phân tầng này quan trọng vì một dòng **@Cacheable(cacheNames="products")** **không** có chỗ đặt **maximumSize** hay **expireAfterWrite** trực tiếp. TTL, kích thước và listener được cấu hình ở **cache manager/native cache**, không phải thêm như thuộc tính vào @Cacheable.

### Trước khi cấu hình, phải có hai thư viện

Trong Spring Framework thuần, **spring-context** mang hạ tầng annotation caching, còn adapter **org.springframework.cache.caffeine.CaffeineCacheManager** nằm trong **spring-context-support**. Thư viện Caffeine thực sự là artifact **com.github.ben-manes.caffeine:caffeine**.

Không thể chỉ thêm Caffeine rồi mong Spring tự tạo CaffeineCacheManager; và ngược lại, có spring-context-support nhưng thiếu artifact Caffeine sẽ không sử dụng được adapter native Caffeine đúng cách.

Spring Boot có **spring-boot-starter-cache** hỗ trợ cấu hình tự động, nhưng cũng cần **Caffeine trên classpath** để chọn provider theo auto-configuration.

## 2. Cách 1: Dùng Caffeine.newBuilder() để cấu hình bằng Java

Builder cho phép gọi phương thức fluent theo kiểu Java, có gợi ý từ IDE và cấu trúc rõ:

~~~java
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

Caffeine<Object, Object> builder = Caffeine.newBuilder()
    .initialCapacity(64)
    .maximumSize(1_000)
    .expireAfterWrite(Duration.ofMinutes(10))
    .recordStats();
~~~

Đây là **đoạn minh họa**, không phải class chạy độc lập. Những tham số chính:

| Builder API | Ý nghĩa |
| --- | --- |
| **initialCapacity(64)** | Gợi ý dung lượng ban đầu cho các cấu trúc lưu trữ; không phải giới hạn cứng |
| **maximumSize(1000)** | Giới hạn số entry theo kích thước; Caffeine áp dụng chính sách eviction |
| **expireAfterWrite(Duration.ofMinutes(10))** | Entry hết hạn 10 phút kể từ khi được tạo/ghi đè, theo semantics của Caffeine |
| **expireAfterAccess(Duration.ofMinutes(5))** | Hết hạn theo thời gian không được truy cập |
| **recordStats()** | Thu thập thống kê cache: hit, miss, eviction và các số liệu liên quan |
| **scheduler(...)** | Cho phép chính sách lập lịch phù hợp khi có chức năng cần scheduler |
| **removalListener(...)** | Callback nhận thông báo về việc entry bị loại bỏ |
| **expireAfter(Expiry<K,V>)** | Thời hạn tùy biến theo từng entry và ngữ cảnh cập nhật/truy cập |
| **weigher(...) + maximumWeight(...)** | Giới hạn theo trọng số tùy biến thay vì số entry |

**maximumSize** và **maximumWeight** là hai cách giới hạn kích thước không được cấu hình đồng thời. **initialCapacity** không phải maximumSize; nó chỉ giúp gợi ý allocation ban đầu.

### Truyền builder vào CaffeineCacheManager

~~~java
import org.springframework.cache.caffeine.CaffeineCacheManager;

CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeine(
    Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterWrite(Duration.ofMinutes(10))
        .recordStats()
);
manager.setCacheNames(java.util.List.of("products", "categories"));
~~~

Đây là đoạn minh họa trong một method tạo CacheManager; các import Duration, Caffeine và List cần có. **setCaffeine(...)** đặt builder dùng cho các cache được tạo theo **cấu hình chung** của manager. **setCacheNames(...)** xác định các tên cache trong **static mode**; lúc đó manager không tự tạo thêm một tên tùy ý ngoài danh sách.

Với cùng một builder cấu hình chung, **products** và **categories** là **hai cache region riêng**: key `"P1"` trong products không va chạm với key `"P1"` trong categories. Cả hai chia sẻ **policy chung** (maximumSize, TTL, stats), **không chia sẻ toàn bộ entries** hoặc một giới hạn 1.000 entry cộng dồn. Mỗi native cache áp dụng policy cho vùng cache riêng của nó.

### Khi nào builder vượt trội?

Builder phù hợp khi:
- Cần **custom Expiry**, **removalListener**, **weigher**, **Ticker**, **Executor** hoặc thành phần Java tùy biến khác không thể viết bằng một chuỗi đặc tả đơn giản.
- Cần cấu hình điều kiện, chẳng hạn TTL đọc từ một object cấu hình có validate.
- Muốn tái sử dụng typed configuration với IDE, test unit và refactoring.
- Muốn khai báo riêng nhiều Caffeine native cache có đặc tính khác nhau.

Với builder, hãy tránh tự tạo **Caffeine.newBuilder().build()** trong từng service nếu toàn hệ thống đang dùng Spring Cache abstraction: việc tạo nhiều cache độc lập dễ dẫn đến sai cacheName và khó thống nhất cấu hình.

## 3. Cách 2: Dùng chuỗi đặc tả CaffeineSpec

**CaffeineSpec** là cách biểu diễn một tập builder setting bằng **chuỗi key=value**, cách nhau bởi dấu phẩy:

~~~properties
maximumSize=1000,expireAfterWrite=10m,recordStats
~~~

Giá trị:
- **maximumSize=1000**: giới hạn khoảng 1.000 entry theo chính sách của Caffeine.
- **expireAfterWrite=10m**: hết hạn 10 phút sau khi ghi.
- **recordStats**: bật thống kê, **không cần =true** trong cú pháp CaffeineSpec.
- Không cần đưa khoảng trắng, dấu ngoặc Java hoặc dấu nháy vào phần string được parse.

Cách dùng trong Spring:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "initialCapacity=64,maximumSize=1000,"
        + "expireAfterWrite=10m,recordStats"
);
manager.setCacheNames(java.util.List.of("products"));
~~~

Ở đây phép nối Java chỉ nhằm định dạng source nhiều dòng; chuỗi cuối cùng vẫn là một specification hợp lệ. Khác builder, **setCacheSpecification(String)** chấp nhận cấu hình do bạn đọc từ properties/environment mà không cần dựng lần lượt nhiều lời gọi fluent.

### CaffeineSpec.parse và setCaffeineSpec

Có thể parse chuỗi thành object CaffeineSpec trước khi truyền cho manager:

~~~java
import com.github.benmanes.caffeine.cache.CaffeineSpec;

CaffeineSpec spec = CaffeineSpec.parse(
    "maximumSize=1000,expireAfterWrite=10m,recordStats");

CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeineSpec(spec);
manager.setCacheNames(java.util.List.of("products"));
~~~

**setCaffeineSpec(spec)** và **setCacheSpecification(string)** đều nhằm mô tả **common Caffeine policy**, nhưng nhận **hai kiểu đối số khác nhau**. Không cần gọi cả hai lên cùng manager. Khi đã có CaffeineSpec object từ cấu hình được parse/validate, dùng setCaffeineSpec là tự nhiên; nếu có chuỗi đơn giản, dùng setCacheSpecification.

### Các key được CaffeineSpec hỗ trợ

Trong Caffeine 3.x, specification bao gồm những nhóm thông dụng:

| Key / flag | Ví dụ | Ghi chú |
| --- | --- | --- |
| **initialCapacity** | initialCapacity=64 | Dung lượng khởi tạo |
| **maximumSize** | maximumSize=1000 | Giới hạn số entry |
| **maximumWeight** | maximumWeight=100000 | Giới hạn trọng số; dùng với weigher nếu cần chính sách trọng số tùy chỉnh |
| **expireAfterWrite** | expireAfterWrite=10m | Hết hạn từ lần ghi |
| **expireAfterAccess** | expireAfterAccess=5m | Hết hạn sau khoảng không truy cập |
| **refreshAfterWrite** | refreshAfterWrite=1m | Chính sách refresh, **phải xem điều kiện loader hỗ trợ** |
| **recordStats** | recordStats | Bật thống kê |
| **weakKeys** | weakKeys | Weak reference cho key |
| **weakValues** | weakValues | Weak reference cho value |
| **softValues** | softValues | Soft reference cho value |

Duration trong chuỗi thông dụng có hậu tố **s**, **m**, **h**, **d** và CaffeineSpec còn có thể hỗ trợ dạng duration ISO-8601; dùng đúng syntax tương ứng phiên bản thư viện.

**Không được phối hợp**:
- **maximumSize** với **maximumWeight**.
- **weakValues** với **softValues**.

Nếu chuỗi có khóa không được hỗ trợ hoặc giá trị không hợp lệ, **CaffeineSpec.parse(...) / Caffeine.from(...) có thể ném IllegalArgumentException trong giai đoạn cấu hình**. Bạn nên kiểm tra sớm khi khởi động ứng dụng, không nuốt exception rồi dùng cache không giới hạn.

### Chuỗi đặc tả không phải ngôn ngữ lập trình

Không thể nhét lambda hoặc callback vào specification. Ví dụ sau **không phải syntax hợp lệ**:

~~~properties
removalListener=(key,value,cause)->logger.info(key)
weigher=(key,value)->value.size()
~~~

Để dùng **removalListener**, **weigher**, custom **Expiry**, **Ticker**, **Scheduler**, v.v., hãy dùng **Java builder**. Nếu chỉ cần maximumSize và TTL đơn giản, specification dễ cấu hình theo môi trường hơn.

## 4. So sánh builder với specification theo nhu cầu

| Tiêu chí | **Builder API** | **CaffeineSpec / chuỗi** |
| --- | --- | --- |
| Dạng khai báo | Java fluent API | Text cấu hình cách nhau bằng dấu phẩy |
| IDE/type checking | Method names được kiểm tra lúc compile | Cú pháp được kiểm tra lúc parse/configure |
| TTL, kích thước, stats cơ bản | Có | Có |
| Listener và callback tùy biến | Có | Không cho callback object tùy ý |
| Custom per-entry expiry | Có qua Expiry | Không mô tả lambda/object Expiry |
| Đọc từ application.properties/YAML | Cần bind dữ liệu rồi tạo builder | Rất thuận tiện |
| Sử dụng tại Spring Framework thuần | setCaffeine(builder) | setCaffeineSpec(spec) hoặc setCacheSpecification(string) |
| Kiểm thử | Test builder/policy bằng Java | Test parse spec + policy của native cache |
| Quản lý config động | Có thể tạo lại manager/cache theo thiết kế | Có thể đổi string nhưng phải xem cache đã tạo |
| Độ rõ ràng | Tốt cho chính sách phức tạp | Tốt cho policy đơn giản, cấu hình ngoài code |

**Hai cấu hình tương đương về mục đích**:

~~~java
// Builder
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterAccess(Duration.ofMinutes(10))
    .recordStats();
~~~

~~~properties
# CaffeineSpec
maximumSize=500,expireAfterAccess=10m,recordStats
~~~

Cả hai cùng diễn đạt chính sách "tối đa 500 entry, expire sau 10 phút không truy cập, thu thập stats". Chúng **không biến @Cacheable thành công cụ phân tán**, không tạo transaction hay thay thế invalidation khi nguồn thay đổi.

### Chọn expireAfterWrite hay expireAfterAccess?

- **expireAfterWrite**: freshness dựa vào **lúc ghi**, thích hợp khi không muốn entry tồn tại quá lâu chỉ vì liên tục được đọc.
- **expireAfterAccess**: thời hạn được làm mới theo **truy cập**, hữu ích với dữ liệu ít dùng nhưng có thể cho entry hot sống lâu nếu liên tục hit.
- Không có TTL nào bảo đảm ngay sau khi database update cache đã mới; cần phối hợp @CachePut, @CacheEvict hoặc chiến lược nhất quán khác.
- Caffeine có thể xử lý maintenance/expiry theo thao tác truy cập hoặc task scheduler; đừng suy từ expireAfterWrite=10m rằng có một thread luôn xóa đúng từng mili giây, kể cả khi cache nhàn rỗi.

## 5. Tạo CaffeineCacheManager trong một ứng dụng Spring thực tế

Trong Spring Framework thuần, **@EnableCaching** bật annotation-driven interception. Đăng ký CaffeineCacheManager dưới dạng bean bằng **@Configuration + @Bean**:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofMinutes(15))
                .recordStats()
        );
        manager.setCacheNames(List.of("products", "categories"));
        return manager;
    }
}
~~~

Đây là class minh họa, thiếu import; có thể tham khảo ví dụ runnable đầy đủ ở phần 8. **@EnableCaching** và cache manager giải quyết **hai việc khác nhau**:
- @EnableCaching tạo hạ tầng Spring AOP xử lý caching annotation.
- CacheManager cung cấp vùng cache theo tên, với policy Caffeine đã xác định.

Nếu chỉ dùng programmatic **Cache API**, có thể không cần @EnableCaching; nhưng nếu có @Cacheable/@CachePut/@CacheEvict, phải bật annotation caching (hoặc cơ chế tương đương) và gọi method qua Spring proxy.

### Chế độ tạo cache động và tĩnh

**Dynamic mode**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "maximumSize=1000,expireAfterWrite=10m");
Cache discovered = manager.getCache("newName");
~~~

Với constructor không tên và không giới hạn cacheNames, CaffeineCacheManager có thể **tạo cache theo tên khi được yêu cầu**, cho nên lỗi đánh máy trong cacheName đôi khi tạo một cache mới thay vì báo lỗi.

**Static mode**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "maximumSize=1000,expireAfterWrite=10m");
manager.setCacheNames(List.of("products", "categories"));
Cache unknown = manager.getCache("typo");
~~~

Đoạn trên trả **null** khi hỏi tên **typo** không nằm trong danh sách static (trừ các cache tùy chỉnh được đăng ký). Static mode hữu ích khi muốn kiểm soát namespace và phát hiện lỗi cấu hình sớm.

**Lưu ý:** setCacheNames(null) có nghĩa trở về dynamic mode trong API Spring; không dùng để biểu diễn một danh sách cache tĩnh rỗng.

### Các cache trong manager có chung chính sách, không chung dữ liệu

Khi setCaffeine(builder) hoặc setCacheSpecification(spec) trên một CaffeineCacheManager, các cache **được manager tạo theo cấu hình chung** có policy cùng cấu trúc. Nhưng **products** và **categories** vẫn có namespace key riêng, mỗi cache có thống kê/dung lượng/eviction riêng.

Nếu muốn **products** expire sau 10 phút còn **categories** expire sau 1 giờ, không nên đặt hai tên vào cùng manager và mong Caffeine tự chia TTL theo cacheName. Có thể sử dụng manager khác, hoặc **registerCustomCache** với chính sách per-cache.

## 6. Cấu hình riêng cho từng cache: registerCustomCache

Spring hỗ trợ đăng ký một native Caffeine Cache riêng bằng **registerCustomCache**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeine(
    Caffeine.newBuilder()
        .maximumSize(1000)
        .expireAfterWrite(Duration.ofMinutes(10))
);

manager.registerCustomCache(
    "shortLived",
    Caffeine.newBuilder()
        .maximumSize(100)
        .expireAfterWrite(Duration.ofSeconds(30))
        .build()
);

manager.registerCustomCache(
    "longLived",
    Caffeine.newBuilder()
        .maximumSize(2000)
        .expireAfterWrite(Duration.ofHours(1))
        .build()
);
~~~

Đoạn Java này minh họa cấu hình **manager**; cần import và bọc trong class/method phù hợp. Hai cache **shortLived** và **longLived** dùng **native cache custom** đã truyền vào, không dùng policy chung theo cách cache thông thường mới được manager tạo. Những tên khác do manager tạo (khi dynamic mode) dùng chính sách **maximumSize=1000, expireAfterWrite=10 phút**.

Có thể dùng registerCustomCache bên cạnh danh sách cacheNames tĩnh, nhưng cần kiểm tra tên và vòng đời khi thay đổi cấu hình. **Không nhầm registerCustomCache với register một listener chung**; nó đăng ký một cache instance native riêng.

Cần lưu ý:
- Caffeine **Cache<K,V> native** là khác với **org.springframework.cache.Cache adapter**.
- Nếu cache custom dùng listener hoặc Expiry riêng, quản lý lifecycle và test chính sách riêng của nó.
- Các thao tác reset/reconfigure manager có thể có ảnh hưởng lên các cache thông thường; đọc Javadoc của version thực tế trước khi đổi cấu hình khi ứng dụng đang phục vụ request.
- Nếu một provider dùng cache đã có entries rồi bị thay bằng cache mới, dữ liệu warm cache cũ có thể mất; không xem việc đổi setter như thay TTL "nóng" không có rủi ro.

## 7. Cách cấu hình Spring Boot: lưu ý thứ tự ưu tiên

Với Spring Boot có auto-configuration caching, thông thường thêm **spring-boot-starter-cache** và dependency **caffeine** rồi bật caching trong ứng dụng. Boot có thể tự tạo **CaffeineCacheManager** khi provider phù hợp được phát hiện.

Ví dụ **application.properties**:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,categories
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=10m,recordStats
~~~

Tương đương bằng **application.yaml**:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: products,categories
    caffeine:
      spec: "maximumSize=500,expireAfterWrite=10m,recordStats"
~~~

Những property này là **cấu hình của Spring Boot**, không phải key trong @Cacheable. Để annotation thực thi, ứng dụng cần bật caching phù hợp, thường bằng **@EnableCaching**.

### Thứ tự lựa chọn khi Boot tự cấu hình Caffeine

Tài liệu Spring Boot liệt kê các nguồn tùy chỉnh được xem xét **theo thứ tự**:

1. **spring.cache.caffeine.spec** (property) nếu có.
2. Bean **CaffeineSpec** nếu có mà không có nguồn ưu tiên hơn.
3. Bean **Caffeine** builder nếu không có hai nguồn trên.

Vì vậy, nếu ứng dụng **đồng thời** có property **spring.cache.caffeine.spec** và bean **Caffeine** builder, không nên giả định bean builder sẽ tự thắng property. Trong trường hợp auto-configuration thông thường, Boot ưu tiên **property spec** theo danh sách trên.

Điều này **khác** với việc bạn tự tạo một CaffeineCacheManager rồi gọi các setter thủ công. Hãy chọn một nguồn cấu hình rõ ràng thay vì cố dựa vào "setter nào chạy cuối". Khi tự khai báo CacheManager bean, Spring Boot có thể không tạo manager tương đương như trước, nên property auto-configuration **không nhất thiết** đang điều khiển bean custom bạn tạo.

### CaffeineSpec bean trong Boot

~~~java
@Bean
CaffeineSpec caffeineSpec() {
    return CaffeineSpec.parse(
        "maximumSize=500,expireAfterWrite=10m,recordStats");
}
~~~

Đây là snippet của một class @Configuration hoặc cơ chế bean registration tương đương; chưa đủ import. Nó hữu ích nếu muốn parse một cấu hình dùng chung trước khi đưa cho Boot. Nhưng nếu đã khai báo **spring.cache.caffeine.spec**, nguồn property đó có thể được chọn trước bean.

### Builder bean trong Boot

~~~java
@Bean
Caffeine<Object, Object> caffeineBuilder() {
    return Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(Duration.ofMinutes(10))
        .recordStats();
}
~~~

Đây là snippet minh họa. Bean builder được Boot phát hiện khi không có nguồn ưu tiên cao hơn. Bạn vẫn nên xác nhận bằng **integration test hoặc native cache policy**, không chỉ nhìn thấy bean trong ApplicationContext rồi kết luận cấu hình đã áp dụng.

### Bẫy của CacheLoader bean

Boot có thể nhận một bean **CacheLoader<Object,Object>** để áp dụng cho các cache được manager quản lý; việc đặt loader toàn cục không tương đương với cacheName-specific loader. Nếu mỗi cache cần logic load khác nhau, tự thiết kế custom cache/manager theo nhu cầu và kiểm thử thay vì để một loader không phân biệt key tải nhầm loại dữ liệu.

## 8. Ví dụ đầy đủ Java 17: hai cách cấu hình hoạt động giống nhau

Đây là chương trình chạy được với **Spring Framework thuần** (không Spring Boot). Ta tạo **hai CaffeineCacheManager bean** riêng để so sánh:
- **builderManager**: setCaffeine(Caffeine.newBuilder()...).
- **specManager**: setCacheSpecification("...").
- Mỗi manager có một cache và phương thức @Cacheable tương ứng.
- Không đợi TTL hết hạn, vì thời gian thực và scheduling khiến output không ổn định; ta kiểm tra cả **hit behavior** và native **policy**.

Để Spring có default CacheManager khi có nhiều bean, **builderManager** được đánh dấu **@Primary**. Hai method @Cacheable còn chỉ định rõ cacheManager theo tên, vì vậy không phụ thuộc default trong demo này.

### 8.1. Cấu trúc

~~~text
caffeine-config-ways/
├── pom.xml
└── src/main/java/demo/CaffeineConfigWaysDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>caffeine-config-ways</artifactId>
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
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.4</version>
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

### 8.3. src/main/java/demo/CaffeineConfigWaysDemo.java

~~~java
package demo;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CaffeineConfigWaysDemo {

    public static class PriceService {
        private final AtomicInteger builderLoads = new AtomicInteger();
        private final AtomicInteger specLoads = new AtomicInteger();

        @Cacheable(
            cacheNames = "byBuilder",
            cacheManager = "builderManager",
            key = "#p0"
        )
        public String byBuilder(String sku) {
            return "builder-" + builderLoads.incrementAndGet();
        }

        @Cacheable(
            cacheNames = "bySpec",
            cacheManager = "specManager",
            key = "#p0"
        )
        public String bySpec(String sku) {
            return "spec-" + specLoads.incrementAndGet();
        }

        public int builderLoads() {
            return builderLoads.get();
        }

        public int specLoads() {
            return specLoads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean("builderManager")
        @Primary
        public CaffeineCacheManager builderManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAllowNullValues(false);
            manager.setCaffeine(
                Caffeine.newBuilder()
                    .initialCapacity(16)
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofMinutes(10))
                    .recordStats()
            );
            manager.setCacheNames(List.of("byBuilder"));
            return manager;
        }

        @Bean("specManager")
        public CaffeineCacheManager specManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAllowNullValues(false);
            manager.setCacheSpecification(
                "initialCapacity=16,maximumSize=100,"
                    + "expireAfterWrite=10m,recordStats"
            );
            manager.setCacheNames(List.of("bySpec"));
            return manager;
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            PriceService service = ctx.getBean(PriceService.class);

            System.out.println("builder-first="
                + service.byBuilder("SKU-1"));
            System.out.println("builder-second="
                + service.byBuilder("SKU-1"));
            System.out.println("spec-first="
                + service.bySpec("SKU-1"));
            System.out.println("spec-second="
                + service.bySpec("SKU-1"));

            System.out.println("builder-loads="
                + service.builderLoads());
            System.out.println("spec-loads="
                + service.specLoads());

            CaffeineCacheManager builderManager = ctx.getBean(
                "builderManager", CaffeineCacheManager.class);
            CaffeineCacheManager specManager = ctx.getBean(
                "specManager", CaffeineCacheManager.class);

            CaffeineCache builderCache = (CaffeineCache)
                Objects.requireNonNull(
                    builderManager.getCache("byBuilder"));
            CaffeineCache specCache = (CaffeineCache)
                Objects.requireNonNull(
                    specManager.getCache("bySpec"));

            System.out.println("builder-max="
                + builderCache.getNativeCache()
                    .policy().eviction().orElseThrow().getMaximum());
            System.out.println("spec-max="
                + specCache.getNativeCache()
                    .policy().eviction().orElseThrow().getMaximum());

            System.out.println("builder-expiry-policy="
                + builderCache.getNativeCache()
                    .policy().expireAfterWrite().isPresent());
            System.out.println("spec-expiry-policy="
                + specCache.getNativeCache()
                    .policy().expireAfterWrite().isPresent());

            System.out.println("unknown-cache="
                + (builderManager.getCache("typo") == null));
        }
    }
}
~~~

**Tại sao ví dụ biên dịch và chạy theo cấu trúc này?**
- CaffeineCacheManager và CaffeineCache có trong **spring-context-support**; @Cacheable/@EnableCaching trong **spring-context**.
- **caffeine** là dependency native thực sự.
- **Caffeine.newBuilder()** có các method maximumSize, expireAfterWrite, recordStats; **CaffeineSpec** hiểu chuỗi tương ứng.
- Spring method được gọi trên **PriceService bean lấy từ context**, nên lời gọi đi qua cache interceptor thay vì tự new instance để gọi.
- @Primary làm rõ default manager khi có nhiều CacheManager; đồng thời mỗi @Cacheable ghi tên manager tường minh.
- **Objects.requireNonNull** bảo vệ trường hợp cấu hình cacheName sai trước khi inspect native policy.
- Native Caffeine Policy API cho phép kiểm tra bounded maximum và sự tồn tại của expireAfterWrite, không cần chờ 10 phút.

### 8.4. Chạy

Cần JDK 17+ và Maven, tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CaffeineConfigWaysDemo
~~~

**Stdout kỳ vọng của các System.out.println** (không bao gồm thông báo riêng của Maven/thư viện):

~~~text
builder-first=builder-1
builder-second=builder-1
spec-first=spec-1
spec-second=spec-1
builder-loads=1
spec-loads=1
builder-max=100
spec-max=100
builder-expiry-policy=true
spec-expiry-policy=true
unknown-cache=true
~~~

Diễn giải:
1. **builder-first=builder-1** vì cache byBuilder ban đầu rỗng; @Cacheable miss và chạy method thật.
2. **builder-second=builder-1** vì key SKU-1 đã có trong byBuilder, @Cacheable hit và không tăng bộ đếm.
3. **spec-first/spec-second** tương tự nhưng dùng manager và cache riêng; chứng minh cấu hình specification cũng hoạt động.
4. **builder-loads=1/spec-loads=1** xác nhận hai method thật chỉ chạy một lần cho cùng key ở mỗi cache.
5. **builder-max=100/spec-max=100**: cả hai native cache có chính sách maximumSize 100 entry.
6. **...expiry-policy=true**: native cache có chính sách expireAfterWrite; test này **không đo TTL thật đã trôi đủ 10 phút hay chưa**.
7. **unknown-cache=true**: builderManager đang static mode chỉ khai báo byBuilder, nên không tự tạo region tên typo.

**Không kết luận** rằng hai cache phải có cùng cache hits, số entries hoặc thống kê thực tế trong mọi ứng dụng. Chúng độc lập, chỉ có cùng chính sách tối đa/expiry ở đây. Trong môi trường thực, TTL và eviction có thể làm kết quả khác nếu thời gian chạy đủ dài.

## 9. Đọc và kiểm chứng chính sách Caffeine native

Để xác minh cấu hình thực sự đã áp dụng, đừng chỉ nhìn property hoặc bean. Có thể xem native cache:

~~~java
import org.springframework.cache.caffeine.CaffeineCache;
import com.github.benmanes.caffeine.cache.Policy;

CaffeineCache springCache = (CaffeineCache)
    Objects.requireNonNull(cacheManager.getCache("products"));

com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
    springCache.getNativeCache();

long max = nativeCache.policy()
    .eviction().orElseThrow().getMaximum();
boolean hasWriteExpiry =
    nativeCache.policy().expireAfterWrite().isPresent();
~~~

Đây là code minh họa cần có biến **cacheManager**, **Objects** import và cache "products" đã cấu hình. Với cache có maximumSize, Policy.eviction() thường có mặt. Nếu không đặt eviction policy, **Optional** có thể rỗng; gọi orElseThrow khi không có policy sẽ gây lỗi.

**recordStats()** làm Caffeine thu thập thống kê, có thể đọc qua:

~~~java
var stats = nativeCache.stats();
System.out.println("hitCount=" + stats.hitCount());
System.out.println("missCount=" + stats.missCount());
~~~

Không đưa một con số stats cố định ở đây vì quá trình lookup/debug hoặc chương trình có thể sinh thêm lượt đọc; statistics là dữ liệu chạy thật và sẽ thay đổi theo workload. Nếu chưa gọi **recordStats()**, Caffeine thường dùng bộ đếm thống kê không theo dõi, khiến bạn hiểu nhầm rằng cache chưa hoạt động. **Không bật recordStats và cũng không kiểm tra metric** là hai vấn đề riêng.

### Không kiểm thử TTL bằng Thread.sleep ngẫu nhiên

Để test expiry chính xác và nhanh:
- Với builder, có thể cấu hình **Ticker** kiểm soát thời gian, nếu provider dùng đúng ticker ấy.
- Dùng policy API/virtual time khi có thể thay vì để test chờ 10 phút.
- Sau khi advance thời gian giả lập, thực hiện thao tác cache phù hợp để quan sát expiry, không giả định maintenance scheduler hoạt động tức thời trên cache nhàn rỗi.
- Với specification không có chỗ biểu diễn Ticker object, nếu cần fake time trong test thì dùng builder.

Một test chỉ chờ Thread.sleep(10_000) rồi kết luận TTL chính xác có thể flaky do scheduling, GC và clock; đồng thời **10 giây khác 10 phút**. Khuyến nghị tách **test policy config** và **test hành vi expiry**.

## 10. Các lỗi thường gặp

### Lỗi 1: Thiếu spring-context-support

Bạn thêm dependency Caffeine + spring-context, nhưng Java báo không tìm thấy **org.springframework.cache.caffeine.CaffeineCacheManager**.

**Giải pháp:** thêm **org.springframework:spring-context-support** đúng phiên bản Spring Framework, cùng artifact **com.github.ben-manes.caffeine:caffeine** phù hợp. Ví dụ pom.xml ở mục 8 có đủ.

### Lỗi 2: Viết một specification không hợp lệ

~~~properties
maximumSize: 1000; expireAfterWrite: 10 minutes
~~~

Đây là cú pháp kiểu người đọc được, **không phải** chuỗi CaffeineSpec. Specification dùng danh sách key=value phân cách bằng dấu phẩy:

~~~properties
maximumSize=1000,expireAfterWrite=10m,recordStats
~~~

Tự viết validator đơn giản nếu cấu hình đến từ hệ thống bên ngoài; ít nhất hãy gọi CaffeineSpec.parse ở startup để phát hiện sai sớm.

### Lỗi 3: Trộn maximumSize và maximumWeight

~~~properties
maximumSize=1000,maximumWeight=100000
~~~

Đây là cấu hình không hợp lệ. Chọn một loại giới hạn. Nếu muốn trọng số domain riêng, cần dùng builder với **weigher** và **maximumWeight**.

### Lỗi 4: Tưởng initialCapacity là giới hạn bộ nhớ

~~~java
Caffeine.newBuilder().initialCapacity(100);
~~~

Đặt initialCapacity không ngăn cache tăng lên ngoài 100. Để giới hạn entries dùng maximumSize; để giới hạn theo cost tương ứng dùng maximumWeight/weigher. Với reference cache trong JVM, một cache không có giới hạn/expiry có thể giữ entry quá lâu và ảnh hưởng bộ nhớ.

### Lỗi 5: Đặt TTL trong @Cacheable

~~~java
// Không có thuộc tính ttl trong annotation @Cacheable của Spring.
@Cacheable(cacheNames = "products")
public Product find(String id) { return repository.find(id); }
~~~

Đây là minh họa, chưa chạy độc lập. **@Cacheable chỉ chọn operation/cacheName**. Caffeine TTL đặt ở manager/native cache được dùng. Nếu cần cacheNames có TTL riêng, dùng nhiều manager hoặc registerCustomCache.

### Lỗi 6: Chạy builder và specification cùng lúc, kỳ vọng tự gộp

~~~java
manager.setCaffeine(Caffeine.newBuilder().maximumSize(1000));
manager.setCacheSpecification("expireAfterWrite=10m");
~~~

Đoạn trên **không** nên xem là "maximumSize từ builder + expiry từ specification" một cách an toàn. Hai setter đều thiết lập nguồn tạo common native cache; **đừng giả định hai policy được hợp nhất**. Chọn một kiểu cấu hình hoàn chỉnh; nếu cần maximumSize và expiry thì đặt **cả hai trong builder** hoặc **cả hai trong spec**. Việc reconfigure manager sau khi cache đã được tạo còn có thể thay cache và dữ liệu warm cache.

### Lỗi 7: Đổi specification ở runtime rồi kỳ vọng entry cũ giữ nguyên

Bạn gọi setCacheSpecification với chuỗi mới trong khi traffic đang chạy. Spring CaffeineCacheManager có hành vi refresh/recreate common caches tùy phương thức và phiên bản; không thể xem đó là chỉnh một TTL per-entry atomically trên native cache đang hoạt động. Cần kế hoạch rollout, test và theo dõi hit/miss/cache warmup.

**Nếu muốn thay đổi policy động**, hãy thiết kế một mechanism phù hợp (ví dụ xây lại cache có kiểm soát, feature rollout hoặc hỗ trợ native policy API trong phạm vi được provider cho phép), thay vì gọi setter tùy ý trên manager chia sẻ cho nhiều thread.

### Lỗi 8: Cache name không đúng trong static mode

~~~java
manager.setCacheNames(List.of("products"));
Cache cache = manager.getCache("product"); // Sai tên.
~~~

**getCache("product")** trả null với static mode khi không có cache đó. Tên gần giống không phải alias. Kiểm tra cacheNames tại cả @Cacheable và manager.

### Lỗi 9: Chỉ thêm caffeine dependency rồi tin rằng mọi @Cacheable sẽ cache

Cần **@EnableCaching** (hoặc hạ tầng annotation caching tương đương), bean CacheManager hợp lệ và lời gọi **qua Spring proxy**. Self-invocation trong cùng bean thường bỏ qua cache advice ở proxy mode mặc định.

### Lỗi 10: Cho rằng recordStats bật sẵn

Caffeine không tự bật collection thống kê đầy đủ ở mọi cache mới. Nếu muốn quan sát hit/miss qua Caffeine stats, bật **recordStats** trên builder/spec và kiểm tra đúng cache. Metric Spring Boot Micrometer có thể cần thêm dependency/binder và cấu hình quan sát tương ứng; không suy từ recordStats rằng dashboard tự xuất hiện.

### Lỗi 11: Nhầm Caffeine local cache là distributed cache

Caffeine cache thường là **local memory per JVM**. Có hai instance ứng dụng thì mỗi instance có cache entries, TTL và stats riêng. Builder/spec không tạo sự kiện invalidation liên node. Nếu dữ liệu cần nhất quán khi update giữa nhiều node, phải thiết kế sự kiện, versioning hoặc dùng kho cache chia sẻ phù hợp.

### Lỗi 12: Đưa refreshAfterWrite vào spec mà không xét loader

**refreshAfterWrite** là chính sách refresh của loading cache, không chỉ là TTL thông thường. Cần xác định cách loader được cung cấp và semantics của refresh. Không xem **refreshAfterWrite=1m** là lệnh tự tải lại mọi entry trong một cache không có loading mechanism.

### Lỗi 13: Thiết lập allowNullValues không khớp giá trị nghiệp vụ

Caffeine native cache không lưu **Java null value** theo cách một map thông thường có thể biểu diễn. Spring CaffeineCacheManager có thể dùng adapter để cho phép **cached-null** theo chính sách **setAllowNullValues**; ở demo chúng ta **chọn false** để đơn giản hóa contract. Nếu method @Cacheable trả null trong khi manager không cho phép, có thể phát sinh lỗi cache put. Đặt chính sách dựa trên domain và kiểm tra với provider; không nhầm absence với cached-null.

## 11. Chọn một cấu hình cho production

Trước khi chọn builder hay spec, xác định:
1. Dữ liệu có thể stale bao lâu? Chọn expireAfterWrite/Access phù hợp và cơ chế invalidation khi update.
2. Số key tối đa theo mỗi region là bao nhiêu? Đặt maximumSize/Weight có cơ sở từ tải và bộ nhớ.
3. Có cần load lại khi miss, hoặc refresh background không? Caffeine CacheLoader/AsyncCacheLoader có thể ảnh hưởng cách Spring Cache truy cập.
4. Có cần removalListener, weigher hoặc custom Expiry không? Nếu có, thường chọn **builder**.
5. Có muốn Dev/Staging/Prod dùng các policy khác nhau mà không sửa code không? **spec property** thuận tiện.
6. Có bao nhiêu cache với TTL khác nhau? Dùng nhiều manager/custom caches, không áp một thông số duy nhất cho mọi cache một cách vô thức.
7. Có cần đo hit rate/eviction? Bật recordStats và cấu hình observability phù hợp.
8. Nhiều instance có cần đồng bộ invalidation không? Caffeine local cache không tự giải quyết.
9. Có cần bảo vệ bộ nhớ không? Caffeine không nhất thiết có maximumSize mặc định; thiết lập giới hạn có chủ đích.
10. Thay cấu hình trong production có gây cache cold, stampede hoặc memory spike không? Chuẩn bị monitoring và rollback.
11. Có nơi nào đặt CaffeineSpec property đồng thời với builder bean hoặc manager custom không? Kiểm tra **cấu hình thực tế có hiệu lực**.
12. Kiểm thử trên đúng version provider và JDK, không chỉ sao chép đoạn snippet từ phiên bản khác.

Một ví dụ chọn **spec** khi chỉ có chính sách cơ bản:

~~~properties
spring.cache.caffeine.spec=maximumSize=2000,expireAfterWrite=15m,recordStats
~~~

Một ví dụ chọn **builder** khi chính sách cần Java callback:

~~~java
Caffeine.newBuilder()
    .maximumSize(2000)
    .expireAfterWrite(Duration.ofMinutes(15))
    .recordStats()
    .removalListener((key, value, cause) -> {
        // Log/metric hoặc cleanup an toàn; listener cần thiết kế
        // sao cho không làm nghẽn đường cache.
    });
~~~

**Cảnh báo:** Snippet listener là minh họa, cần import và type context phù hợp. Listener thường chạy trong điều kiện concurrency của provider; code trong listener không nên gây block kéo dài, tạo vòng gọi cache hoặc lộ dữ liệu nhạy cảm.

## 12. Câu hỏi tự kiểm tra

**1.** Spring Cache với Caffeine muốn giới hạn 500 entry và expire sau 10 phút kể từ khi ghi. Có thể dùng những hai cách nào?

**Đáp:** Builder **Caffeine.newBuilder().maximumSize(500).expireAfterWrite(Duration.ofMinutes(10))** hoặc spec **maximumSize=500,expireAfterWrite=10m**, đưa vào CaffeineCacheManager qua API tương ứng.

**2.** Đặt **initialCapacity(500)** có giới hạn cache chỉ 500 entry không?

**Không.** Đó là gợi ý dung lượng ban đầu, không thay thế **maximumSize(500)**.

**3.** Có đặt **removalListener** bằng chuỗi CaffeineSpec thông thường được không?

**Không.** CaffeineSpec chỉ hỗ trợ một tập option text được định nghĩa; callback/lambda phải cấu hình qua builder.

**4.** Có thể đưa chung **maximumSize=100,maximumWeight=1000** vào spec không?

**Không.** Hai giới hạn này loại trừ nhau.

**5.** Nếu Spring Boot đã có **spring.cache.caffeine.spec**, và app cũng có bean Caffeine builder, nguồn nào thường được ưu tiên trong auto-configuration?

**Spec property** được xét trước CaffeineSpec bean và Caffeine builder bean, theo tài liệu Spring Boot.

**6.** @Cacheable(cacheNames="products") có tự động áp TTL từ class Java không?

**Không.** TTL do CaffeineCacheManager/native cache được chọn cung cấp. Nếu manager không có TTL, @Cacheable không tự thiết lập một thời hạn.

**7.** Với CaffeineCacheManager đặt static cacheNames=["products"], gọi getCache("product") trả gì?

**Thường là null** khi "product" không có trong danh sách và không được đăng ký riêng.

**8.** Hai cache names trên một CaffeineCacheManager có chia chung maximumSize=1000 tổng cộng không?

**Không.** Chúng là hai native cache regions riêng; mỗi region nhận cấu hình common của manager.

**9.** Vì sao chương trình Maven cần spring-context-support?

Vì **CaffeineCacheManager** của Spring được cung cấp qua module **spring-context-support**. Caffeine native artifact là dependency riêng.

**10.** Khi dùng setCacheSpecification sau khi đã setCaffeine, hai cấu hình có được tự hợp nhất không?

**Không nên giả định.** Cả hai là cách cấu hình common cache policy; chọn một nguồn đầy đủ và test policy thực tế.

**11.** Dùng expireAfterAccess=10m cho key được đọc liên tục có đảm bảo key hết hạn 10 phút sau lần ghi cuối không?

**Không.** Access có thể gia hạn thời gian sống, khác expireAfterWrite.

**12.** recordStats có tự tạo dashboard production không?

**Không.** Nó cho Caffeine thu thập thống kê; xuất metric ra hệ thống quan sát cần tích hợp thêm (ví dụ qua Actuator/Micrometer trong Spring Boot nếu được cấu hình).

## Kết luận

- **Builder** là lựa chọn mạnh khi cần Java callback, Expiry/Weigher/Listener tùy biến và kiểm soát policy bằng code.
- **CaffeineSpec hoặc specification string** phù hợp với cấu hình **maximumSize, expiry, recordStats** bằng properties/YAML và thay đổi theo môi trường.
- Với **Spring Framework thuần**, dùng **CaffeineCacheManager.setCaffeine(builder)** hoặc **setCaffeineSpec(spec)** / **setCacheSpecification(string)**; không giả định các nguồn này được tự gộp.
- Với **Spring Boot auto-configuration**, nắm rõ thứ tự chọn **spring.cache.caffeine.spec → CaffeineSpec bean → Caffeine builder bean** và việc tự khai báo CacheManager có thể thay đổi nhánh cấu hình.
- Dù chọn kiểu nào, cần thống nhất **cacheName/key**, cấu hình **maximumSize/TTL** có chủ đích, kiểm tra policy thực tế trên native Caffeine cache và đo behavior qua **@Cacheable** trên bean proxy.

### Tài liệu chính thức

- Spring Framework 6.2 – CaffeineCacheManager Javadoc, các setter và registerCustomCache: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2 – CaffeineCache Javadoc và getNativeCache: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework – Annotation-driven caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Caffeine Wiki – Specification string: https://github.com/ben-manes/caffeine/wiki/Specification
- Caffeine Wiki – Eviction (size, time và reference policies): https://github.com/ben-manes/caffeine/wiki/Eviction
- Spring Boot Reference – Caffeine configuration và thứ tự các nguồn customizations: https://docs.spring.io/spring-boot/reference/io/caching.html
- Maven Central – caffeine artifact: https://central.sonatype.com/artifact/com.github.ben-manes.caffeine/caffeine/3.2.4

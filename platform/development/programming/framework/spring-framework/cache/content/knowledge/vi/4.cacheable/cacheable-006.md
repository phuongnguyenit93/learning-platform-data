# @Cacheable: Phương thức có tham số và phương thức không tham số

Khi đánh dấu một phương thức bằng **@Cacheable**, Spring có thể lưu kết quả thực thi để các lần gọi tiếp theo đọc lại từ cache. Điểm quyết định một lần gọi có được dùng chung kết quả đã lưu hay không là **cache name + cache key**. Số lượng và giá trị tham số của phương thức ảnh hưởng trực tiếp đến cách Spring tạo key mặc định. Một phương thức không có tham số vẫn cache được, nhưng tất cả lần gọi của nó mặc định dùng cùng một key trong cache đã chọn.

Bài học này tập trung vào cách **@Cacheable** hoạt động với phương thức không tham số, một tham số và nhiều tham số; cách chọn key khi tham số không phản ánh đầy đủ dữ liệu; và các lỗi có thể làm trả sai kết quả.

## 1. Từ lời gọi phương thức đến cache key

Mỗi lần một lời gọi đi qua Spring cache interceptor:

1. Spring xác định cache dựa trên **cacheNames/value** (hoặc cấu hình cache resolver).
2. Spring tính key: dùng thuộc tính **key**, **keyGenerator**, hoặc **SimpleKeyGenerator** mặc định.
3. Nếu cache chứa key đó (**hit**), Spring trả giá trị đã lưu mà không chạy thân phương thức.
4. Nếu chưa có (**miss**), Spring chạy phương thức, nhận kết quả rồi lưu vào cache, trừ khi có điều kiện ngăn lưu hoặc provider không thể lưu.
5. Các lần gọi sau với cùng cache name và cùng key có thể tái sử dụng kết quả, kể cả khi dữ liệu bên ngoài đã thay đổi nếu chưa có invalidation/expiration.

~~~text
Gọi service.method(args)
          |
          v
     Spring proxy
          |
          v
  Chọn cache name + tạo key
          |
          +---- HIT  ------> Trả kết quả cache
          |
          +---- MISS ------> Chạy method ------> Lưu cache ------> Trả kết quả
~~~

**@Cacheable không tạo cache engine riêng.** Spring cung cấp abstraction và interceptor; cách lưu, TTL, dung lượng, chia sẻ giữa các instance và chính sách lỗi phụ thuộc **CacheManager** cùng provider (ConcurrentMap, Caffeine, Redis...). Do đó ví dụ về key dưới đây áp dụng cho cơ chế mặc định của Spring, còn thời gian sống của entry phải được thiết kế riêng.

## 2. Quy tắc key mặc định theo số tham số

Spring mặc định dùng **org.springframework.cache.interceptor.SimpleKeyGenerator**:

| Chữ ký phương thức | Lời gọi ví dụ | Key mặc định |
| --- | --- | --- |
| Không tham số | **loadConfig()** | **SimpleKey.EMPTY** |
| Một tham số | **findById("P01")** | Giá trị **"P01"** |
| Nhiều tham số | **findByRegion("P01", "vi")** | **SimpleKey("P01", "vi")** |
| Hai lời gọi nhiều tham số khác thứ tự | **findByRegion("P01", "vi")** và **findByRegion("vi", "P01")** | Hai tổ hợp key khác nhau |
| Một tham số nhưng là đối tượng phức tạp | **findByFilter(filter)** | Phụ thuộc cách đối tượng được dùng làm key và tính đúng đắn của **equals/hashCode** |

Đây là quy tắc thường dùng. Trong triển khai **SimpleKeyGenerator**, trường hợp tham số duy nhất là **null** hoặc kiểu mảng được xử lý đặc biệt thay vì luôn trả trực tiếp đối tượng tham số; không nên dựa vào suy luận đơn giản rằng mọi lời gọi một tham số đều có key đúng bằng đối tượng đó.

**Cache name cũng là một phần của phạm vi tra cứu.** Key **"P01"** trong cache **products** không tự va chạm với key **"P01"** trong cache **productPrices**. Ngược lại, **Spring không tự ghép tên phương thức hoặc tên class vào key mặc định**. Hai phương thức dùng cùng một cache name và sinh cùng key có thể dùng nhầm kết quả của nhau.

Ví dụ: **findProduct("P01")** và **findPrice("P01")** đều trỏ tới cache **shared** sẽ cùng key **"P01"**. Nếu một phương thức lưu **Product**, phương thức khác cần **Price**, kết quả có thể sai hoặc phát sinh lỗi ép kiểu. Hãy dùng cache name phù hợp với kiểu và ý nghĩa dữ liệu, hoặc thiết kế key có namespace rõ ràng.

## 3. Phương thức không tham số: mọi lời gọi có chung key

~~~java
@Cacheable(cacheNames = "homepageStatistics")
public HomepageStatistics loadHomepageStatistics() {
    return statisticsRepository.calculate();
}
~~~

Lời gọi đầu tiên đi qua Spring proxy thường là cache miss: phương thức tính thống kê và kết quả được lưu dưới key **SimpleKey.EMPTY** trong cache **homepageStatistics**. Các lời gọi tiếp theo tới cùng cache/key được trả từ cache, bất kể gọi ở thời điểm nào, cho đến khi entry bị evict, hết hạn hoặc thay thế.

### Khi nào có ích?

- Kết quả là một bộ cấu hình dùng chung cho toàn ứng dụng, không thay đổi theo người gọi.
- Snapshot thống kê toàn cục có thể chấp nhận độ trễ cập nhật.
- Dữ liệu tham chiếu toàn cục được tải tốn kém nhưng ít thay đổi.

Ưu điểm thường thấy: chỉ **một key** cho phương thức đó trong cache; dễ làm nóng và không tạo thêm entry vì các tham số khác nhau.

### Rủi ro cần thấy trước

**Không tham số không có nghĩa là kết quả bất biến.** Thân phương thức có thể đọc thời gian, database, biến môi trường, tenant hiện tại, locale hoặc thông tin đăng nhập. Ví dụ:

~~~java
@Cacheable(cacheNames = "dashboard")
public DashboardData dashboardForCurrentUser() {
    String userId = securityContext.currentUserId();
    return repository.findDashboard(userId);
}
~~~

Cách viết này **sai về thiết kế cache** nếu nhiều người dùng gọi cùng một cache: mỗi người có thể nhận kết quả của người dùng đầu tiên vì mọi lời gọi dùng **SimpleKey.EMPTY**. Hướng sửa là đưa định danh người dùng vào tham số và đưa nó vào key:

~~~java
@Cacheable(cacheNames = "dashboardByUser", key = "#p0")
public DashboardData dashboardForUser(String userId) {
    return repository.findDashboard(userId);
}
~~~

Định danh tenant, quyền truy cập và các yếu tố quyết định nội dung đầu ra cũng phải được xét trong key. Caching không thay thế kiểm tra phân quyền. Các method ở trên là **mã minh họa trong ứng dụng Spring có repository và security context thực tế**, không phải chương trình Java độc lập.

### Hai phương thức không tham số dùng chung cache

~~~java
@Cacheable(cacheNames = "systemInformation")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "systemInformation")
public String deploymentRegion() { return regionProvider.region(); }
~~~

Hai phương thức đều tính **SimpleKey.EMPTY** trong **systemInformation**. Đây là xung đột: lời gọi thứ hai có thể lấy kết quả của phương thức đầu tiên.

Có hai cách hợp lý:

~~~java
// Cách A: tách cache theo ý nghĩa dữ liệu.
@Cacheable(cacheNames = "appVersion")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "deploymentRegion")
public String deploymentRegion() { return regionProvider.region(); }
~~~

~~~java
// Cách B: giữ một cache nhưng đặt khóa hằng khác nhau.
@Cacheable(cacheNames = "systemInformation", key = "'version'")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "systemInformation", key = "'region'")
public String deploymentRegion() { return regionProvider.region(); }
~~~

Trong **key = "'version'"**, cặp dấu nháy đơn là cú pháp chuỗi literal của **Spring Expression Language (SpEL)**; Spring tạo key là chuỗi **version**, không phải tên biến.

## 4. Phương thức một tham số: một key cho mỗi giá trị

~~~java
@Cacheable(cacheNames = "products")
public Product findById(String id) {
    return productRepository.findById(id).orElse(null);
}
~~~

Ví dụ:

~~~text
findById("P01") -> miss -> đọc nguồn và lưu dưới key "P01"
findById("P01") -> hit  -> dùng lại kết quả
findById("P02") -> miss -> key "P02" khác
~~~

Nếu phương thức nhận **Long id**, key mặc định là giá trị **Long**; nếu nhận **String id**, key là **String**. Không nên tự cho rằng cùng ký tự **"42"** và số **42L** là một khóa. Key do Spring tạo còn có thể được provider chuyển đổi/serialize theo quy tắc riêng, nên cần kiểm tra khi đổi provider hoặc loại tham số.

Nếu tham số là đối tượng có **equals()/hashCode()** dựa trên địa chỉ object, hai đối tượng biểu diễn cùng yêu cầu có thể tạo hai cache entry. Một lựa chọn dễ kiểm soát là dùng thuộc tính ổn định:

~~~java
@Cacheable(cacheNames = "products", key = "#p0.id")
public Product findByQuery(ProductQuery query) {
    return productRepository.findByQuery(query);
}
~~~

**Chỉ dùng key này khi query.id đủ quyết định kết quả.** Nếu còn trường currency, tenant, includeInactive hoặc thời điểm hiệu lực làm thay đổi dữ liệu, chỉ lấy **id** sẽ khiến hai yêu cầu khác nhau dùng chung bản ghi. Với object làm key, ưu tiên giá trị bất biến (như Java **record**) hoặc biểu thức key dựa trên các thành phần ổn định và đủ phân biệt.

## 5. Phương thức nhiều tham số: key là một tổ hợp có thứ tự

~~~java
@Cacheable(cacheNames = "translatedProducts")
public ProductView findView(String productId, String language) {
    return productRepository.findLocalizedView(productId, language);
}
~~~

Các lời gọi:

~~~text
findView("P01", "vi") -> SimpleKey("P01", "vi") -> miss lần đầu
findView("P01", "en") -> SimpleKey("P01", "en") -> key khác
findView("P01", "vi") -> cùng key lần đầu   -> hit
~~~

**SimpleKey** bảo toàn sự phân biệt và thứ tự các thành phần; hai danh sách tham số phải tương đương theo ngữ nghĩa so sánh của từng thành phần mới có thể dùng chung entry.

### Mặc định đưa tất cả tham số vào key

Xét:

~~~java
@Cacheable(cacheNames = "prices")
public Price lookup(String sku, String currency, boolean includeTax) {
    return pricingService.lookup(sku, currency, includeTax);
}
~~~

Cả ba tham số ảnh hưởng đến kết quả, nên mặc định tạo key từ cả ba thường đúng. Nếu chỉ lấy **sku**, giá VND/USD hoặc giá đã/chưa bao gồm thuế có thể bị nhầm.

Ngược lại:

~~~java
@Cacheable(cacheNames = "productNames")
public String loadName(String productId, String traceId) {
    return productRepository.loadName(productId);
}
~~~

**traceId** chỉ dùng để ghi log và không ảnh hưởng kết quả. Key mặc định chứa cả **productId** lẫn **traceId** làm cho cùng một sản phẩm có thể tạo nhiều entry vô ích. Khi đã xác minh **traceId không ảnh hưởng nội dung trả về**, ta có thể dùng:

~~~java
@Cacheable(cacheNames = "productNames", key = "#p0")
public String loadName(String productId, String traceId) {
    return productRepository.loadName(productId);
}
~~~

Như vậy, mọi lời gọi cùng **productId** có thể chia sẻ kết quả. Đây là quyết định dựa trên **phụ thuộc dữ liệu thật**, không phải mẹo để tăng hit ratio bằng mọi giá.

## 6. Thiết kế key có chủ đích bằng SpEL hoặc KeyGenerator

Một số cú pháp có ích trong annotation:

| Cú pháp | Ý nghĩa |
| --- | --- |
| **#p0** hoặc **#a0** | Tham số thứ nhất (chỉ số bắt đầu từ 0) |
| **#p1** hoặc **#a1** | Tham số thứ hai |
| **#root.args[0]** | Tham số thứ nhất qua metadata lời gọi |
| **#root.methodName** | Tên phương thức đang được gọi |
| **#p0.id** | Thuộc tính **id** của tham số thứ nhất |
| **'fixed-key'** | Khóa chuỗi hằng, hữu ích cho phương thức không tham số |

Với Java, **#p0** thường bền vững hơn **#productId** khi project chưa biên dịch với thông tin tên tham số (**-parameters**). Spring có thể nhận tên tham số khi metadata khả dụng, nhưng không nên mặc định mọi build đều có sẵn tên.

~~~java
// Chọn khóa theo productId vì phần còn lại chỉ dùng cho tracing.
@Cacheable(cacheNames = "products", key = "#p0")
public Product load(String productId, String requestId) { /* ... */ }

// Dành key hằng cho dữ liệu duy nhất trong một cache.
@Cacheable(cacheNames = "exchangeRateSnapshot", key = "'latest'")
public RateSnapshot latestRates() { /* ... */ }

// Phân biệt các phương thức trong cùng một cache bằng namespace.
@Cacheable(cacheNames = "sharedText", key = "#root.methodName + ':' + #p0")
public String describe(String id) { /* ... */ }
~~~

**Lưu ý khi nối chuỗi để tạo key:** phải đảm bảo cách mã hóa không nhập nhằng; chẳng hạn hai cặp **("a:b", "c")** và **("a", "b:c")** đều thành **a:b:c** nếu ghép đơn thuần bằng dấu hai chấm. Khi nhiều trường cần phân biệt chính xác, dùng kiểu key có cấu trúc (record/SimpleKey) hoặc một **KeyGenerator** chuẩn hóa thay vì nối chuỗi tùy tiện.

Ví dụ một generator có namespace theo class và tên method để tránh dùng chung key ngoài ý muốn:

~~~java
// NamedMethodKeyGenerator.java – mã component dùng trong ứng dụng Spring.
package demo.cache;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.cache.interceptor.KeyGenerator;

public class NamedMethodKeyGenerator implements KeyGenerator {
    @Override
    public Object generate(Object target, Method method, Object... params) {
        return new MethodCallKey(
                target.getClass().getName(),
                method.getName(),
                Arrays.asList(params.clone()));
    }

    public record MethodCallKey(
            String className, String methodName, java.util.List<Object> args) {}
}
~~~

Code trên minh họa tạo key có cấu trúc; trong ứng dụng thật cần xem xét **overload** (nếu các chữ ký khác nhau có thể nhận giá trị nhìn giống nhau), mảng/đối tượng mutable, chi phí lưu và serializer của provider phân tán. **target.getClass()** có thể là class proxy tùy cơ chế; nếu key phải ổn định xuyên các môi trường/provider, nên dùng namespace nghiệp vụ tường minh thay vì dựa vào tên lớp runtime. **key** và **keyGenerator** là hai lựa chọn loại trừ nhau trên cùng annotation.

~~~java
@Cacheable(cacheNames = "profiles", keyGenerator = "businessKeyGenerator")
public Profile profile(String tenantId, String userId) {
    return profileRepository.load(tenantId, userId);
}
~~~

Ở đây Spring cần bean **businessKeyGenerator** thực sự tồn tại. Các đoạn trong mục này minh họa cách cấu hình, không phải các tệp có thể chạy đơn lẻ.

## 7. Ví dụ Spring đầy đủ: xem hit/miss với 0, 1 và 2 tham số

Dưới đây là ứng dụng tối giản dùng **Spring Framework 6.1.x**, **Java 17+** và **ConcurrentMapCacheManager** để thấy trực tiếp phương thức có chạy lại hay không. Không cần database; biến đếm tăng **chỉ khi thân method được thực thi**.

Tạo cấu trúc:

~~~text
spring-cache-keys-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/cache/CacheKeysDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-cache-keys-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.CacheKeysDemo'
}
~~~

**src/main/java/demo/cache/CacheKeysDemo.java**:

~~~java
package demo.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheKeysDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("users", "translations", "version");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(CacheKeysDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.user("u1"));
            System.out.println(service.user("u1"));
            System.out.println(service.user("u2"));

            System.out.println(service.translation("hello", "vi"));
            System.out.println(service.translation("hello", "en"));
            System.out.println(service.translation("hello", "vi"));

            System.out.println(service.version());
            System.out.println(service.version());
        }
    }

    public static class CatalogService {
        private int userLoads;
        private int translationLoads;
        private int versionLoads;

        @Cacheable(cacheNames = "users")
        public String user(String id) {
            return "user:" + id + ":load=" + ++userLoads;
        }

        @Cacheable(cacheNames = "translations")
        public String translation(String text, String language) {
            return "text:" + text + ":" + language
                    + ":load=" + ++translationLoads;
        }

        @Cacheable(cacheNames = "version")
        public String version() {
            return "version:load=" + ++versionLoads;
        }
    }
}
~~~

Chạy tại thư mục project bằng một Gradle có sẵn (hoặc dùng Gradle wrapper nếu project đã được tạo wrapper):

~~~bash
gradle run --quiet
~~~

Các dòng **System.out.println** dự kiến, theo đúng thứ tự (không tính thông báo riêng của công cụ build/runtime nếu có):

~~~text
user:u1:load=1
user:u1:load=1
user:u2:load=2
text:hello:vi:load=1
text:hello:en:load=2
text:hello:vi:load=1
version:load=1
version:load=1
~~~

Giải thích:

- **user("u1")** lần đầu miss, lần hai hit nên **userLoads** vẫn là 1; **user("u2")** có key mới và tăng lên 2.
- **translation("hello", "vi")** khác **translation("hello", "en")** vì key gồm hai tham số; lặp lại **("hello", "vi")** hit và không tăng **translationLoads**.
- **version()** không có tham số, cả hai lời gọi dùng **SimpleKey.EMPTY** trong cache **version**, nên **versionLoads** chỉ tăng một lần.
- Bean được lấy qua **ApplicationContext**, vì vậy lời gọi tới **CatalogService** đi qua proxy do **@EnableCaching** cấu hình. Nếu tự khởi tạo bằng **new CatalogService()** rồi gọi trực tiếp, Spring sẽ không can thiệp.
- **ConcurrentMapCacheManager** thích hợp để minh họa nhanh key/hit/miss; bản thân nó không cung cấp TTL/size eviction như một cache production được cấu hình chuyên biệt.

Đây là **ứng dụng Spring thực sự**, khác với đoạn mã minh họa từng method ở trên. Spring 6.1.x yêu cầu Java 17 trở lên; ví dụ sử dụng một phiên bản thư viện cụ thể để chạy nhất quán. Nếu môi trường đã dùng Spring Boot/Gradle chung của dự án, chỉ lấy phần cấu hình cache và service phù hợp, không cần thêm project mẫu song song.

## 8. Invalidation: xóa đúng key của cùng phương thức

Các key được dùng khi đọc phải khớp với key khi xóa:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String id) {
    return repository.load(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, UpdateProductCommand command) {
    repository.update(id, command);
}
~~~

**@CacheEvict** mặc định thực hiện eviction sau khi method hoàn tất bình thường. Cả hai annotation ở đây dùng key **id**. Nếu phương thức cập nhật có hai tham số mà không chỉ định **key**, thuật toán mặc định sẽ tạo **SimpleKey(id, command)**, không khớp với **id** của **getProduct**; entry cũ có thể vẫn còn.

Tương tự với method không tham số dùng key hằng:

~~~java
@Cacheable(cacheNames = "globalSettings", key = "'active'")
public Settings currentSettings() {
    return repository.loadSettings();
}

@CacheEvict(cacheNames = "globalSettings", key = "'active'")
public void changeSettings(Settings newSettings) {
    repository.saveSettings(newSettings);
}
~~~

Vì **currentSettings()** dùng key hằng **active**, phương thức ghi cũng phải evict **active** dù nó nhận **Settings newSettings** làm tham số. Tách cache name hoặc dùng **allEntries = true** chỉ khi thật sự cần xóa toàn bộ entries của cache.

**Độ mới và transaction:** Nếu update DB nằm trong transaction, thời điểm xóa cache so với lúc transaction commit cần được kiểm soát. Evict quá sớm có thể khiến một luồng khác miss và nạp dữ liệu DB chưa commit, rồi giữ bản cũ. Với nhiều instance, local cache của mỗi node cũng cần một cách invalidation phù hợp. TTL là chính sách provider, không phải thuộc tính mặc định của **@Cacheable**.

## 9. Điều kiện cache và phạm vi của tham số

**condition** được đánh giá trước khi gọi method, nên có thể dựa vào tham số; **unless** quyết định có lưu kết quả sau khi method chạy hay không.

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

Ví dụ này chỉ cho phép caching khi id khác null và không lưu kết quả null. Với các phương thức không tham số, **condition** vẫn có thể dựa trên metadata của lời gọi nhưng không thể phân biệt người dùng bằng tham số nếu không truyền thông tin người dùng vào method. **#result** không khả dụng để tính key của **@Cacheable** trước khi gọi; dùng **unless** để kiểm tra kết quả sau khi chạy.

Lưu ý **@Cacheable(sync = true)** có thể giảm nhiều phép tính trùng nhau cho cùng một key khi nhiều luồng miss đồng thời **nếu provider hỗ trợ**, nhưng hành vi và hạn chế phụ thuộc cache implementation; nó không thay thế cơ chế khóa phân tán. Không kết hợp tùy tiện **sync = true** với **unless** vì Spring có hạn chế cho chế độ đồng bộ.

## 10. Bảng đối chiếu thiết kế: nên dùng cách nào?

| Tình huống | Cách tiếp cận | Vì sao |
| --- | --- | --- |
| Một kết quả dùng chung, phương thức không tham số | **@Cacheable("globalSnapshot")** | Mặc định một key **SimpleKey.EMPTY** cho cache đó |
| Hai phương thức không tham số khác ý nghĩa | Hai cache name khác nhau hoặc key hằng riêng | Tránh xung đột **SimpleKey.EMPTY** |
| Một tham số duy nhất đủ xác định kết quả | Key mặc định | Đơn giản, dễ đọc, ít cấu hình |
| Một tham số DTO có nhiều trường không liên quan | Key theo các trường thật sự quyết định kết quả | Tránh nhiều bản sao vô ích |
| Hai hoặc nhiều tham số cùng ảnh hưởng kết quả | Key mặc định **SimpleKey(...)** | Phân biệt tổ hợp tham số |
| Một tham số chỉ để trace/log | Key tùy chỉnh bỏ trace/log | Tăng tái sử dụng mà không làm sai dữ liệu |
| Kết quả phụ thuộc tenant/user/locale nhưng chữ ký chưa nhận các giá trị đó | Sửa hợp đồng method để truyền thông tin cần thiết và đưa vào key | Tránh rò rỉ hoặc dùng chéo kết quả |
| Nhiều method dùng chung cache name | Namespace method/business key hoặc tách cache | Tránh va chạm dù tham số giống nhau |
| Method ghi cập nhật một đối tượng | **@CacheEvict** với đúng key đọc, tính tới commit | Tránh trả bản cũ |
| Kết quả phải luôn mới tại thời điểm giao dịch | Đọc/kiểm tra lại nguồn dữ liệu ở quyết định quan trọng | Cache không bảo đảm nhất quán giao dịch |

## 11. Lỗi phổ biến và cách kiểm tra

**1. Quên bật Spring caching.** Annotation chỉ có tác dụng khi bật **@EnableCaching** (hoặc cấu hình tương đương của ứng dụng), có **CacheManager**, và lời gọi được chặn bởi Spring proxy/aspect.

**2. Tự gọi method trong cùng bean (self-invocation).** Ví dụ method **run()** gọi **this.findById("P01")** không đi qua proxy trong chế độ proxy thông thường, nên **@Cacheable** ở **findById** có thể không được áp dụng. Tách method sang bean khác rồi gọi qua bean Spring hoặc chọn cơ chế interception phù hợp.

**3. Cùng cache name, cùng key, khác ý nghĩa.** Một method không tham số và một method khác không tham số thường đều có **SimpleKey.EMPTY**. Tách cache hoặc đặt key rõ ràng.

**4. Bỏ tham số có ảnh hưởng đến kết quả.** Dùng **key = "#p0"** cho **loadPrice(sku, currency)** khiến giá ở những currency khác nhau cùng key, là lỗi dữ liệu chứ không chỉ lỗi hiệu năng.

**5. Dùng tham số không liên quan trong key.** **traceId**, correlation id, request timestamp có thể làm mỗi request thành một key mới, tỷ lệ hit thấp và tốn bộ nhớ.

**6. Key được tạo từ object mutable.** Nếu object thay đổi các trường tham gia **equals/hashCode** trong khi đang là key, việc tra cứu hoặc eviction có thể khó dự đoán. Ưu tiên key bất biến/canonical.

**7. Cho rằng cùng tham số luôn trả dữ liệu mới nhất.** Cache có thể phục vụ bản trước khi DB đổi. Cần eviction, update cache, TTL hoặc xác nhận tại nguồn theo yêu cầu nghiệp vụ.

**8. Đọc và xóa bằng key khác nhau.** **get(id)** cache theo **id**, còn **update(id, command)** evict mặc định theo cả hai tham số; kết quả là bản cũ không bị xóa. Viết biểu thức **key** đối xứng.

**9. Không kiểm tra provider.** Local cache mỗi instance là độc lập; Redis có serializer và chuyển đổi key riêng. Đừng mặc định key Java phức tạp sẽ có cùng định dạng và cùng hiệu quả ở mọi provider.

**10. Dùng cache cho kết quả phụ thuộc trạng thái ẩn.** Với current user, tenant, locale, đồng hồ hoặc feature flag, hãy xác định yếu tố nào làm thay đổi giá trị trả về và đảm bảo chúng được biểu diễn đúng trong key hoặc chọn không cache.

Khi test, hãy gọi cùng method với: (a) tham số giống nhau hai lần; (b) tham số khác nhau; (c) không tham số hai lần; (d) hai method cùng cache; (e) sau một cập nhật nguồn; và (f) lời gọi từ bên trong cùng bean. Quan sát số lần thân method chạy, entry trong cache và tính đúng đắn của kết quả. Không chỉ đo **hit ratio**.

## 12. Tự kiểm tra

1. Vì sao **loadConfig()** được cache dù không có tham số? Key mặc định của nó là gì?
2. Vì sao **find("P01", "vi")** và **find("P01", "en")** có hai key khác nhau?
3. Khi nào bỏ **traceId** khỏi key là hợp lý? Khi nào việc bỏ **currency** là lỗi?
4. Hai method không tham số dùng cùng cache name sẽ xảy ra chuyện gì? Nêu hai cách sửa.
5. Vì sao **@CacheEvict** trên **update(id, command)** cần biểu thức key nếu method đọc chỉ nhận **id**?
6. Vì sao **@Cacheable** có thể không chạy khi dùng **new Service()** hoặc self-invocation?

Nếu trả lời đúng, người học đã nắm điều quan trọng nhất: **cache key phải phản ánh đúng tập yếu tố quyết định kết quả, còn cache name phải phản ánh phạm vi và ý nghĩa dữ liệu**. Không có tham số là một trường hợp đặc biệt của quy tắc đó, chứ không phải ngoại lệ của **@Cacheable**.

### Tài liệu tham khảo

- Spring Framework — Declarative Annotation-based Caching, Default Key Generation và SpEL: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Spring AOP proxy semantics: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html

# Nguy cơ va chạm giữa nhiều phương thức dùng chung vùng cache

Khi hai hay nhiều phương thức Spring dùng chung một vùng cache (cùng **cache name**), chúng có thể vô tình tạo **cùng cache key** dù kết quả trả về có ý nghĩa hoàn toàn khác nhau. Phương thức được gọi sau nhận lại kết quả của phương thức đã ghi cache trước đó, thay vì thực thi thân phương thức của mình. Đây là lỗi **đúng sai dữ liệu**: có thể hiển thị sai nội dung, gây lỗi kiểu dữ liệu, hoặc làm lộ dữ liệu của ngữ cảnh khác nếu key thiếu thông tin tenant/người dùng.

Trong Spring Cache, **@Cacheable** không mặc định gắn tên class hay tên method vào key. Vì thế, đặt nhiều method vào cùng cache name là một quyết định thiết kế cần xét cả **không gian khóa (key space)** và **kiểu/ý nghĩa giá trị (value space)**.

## 1. Va chạm xảy ra ở đâu?

Hãy xét hai phương thức cùng nhận **productId** và cùng dùng cache **catalog**:

~~~java
@Cacheable(cacheNames = "catalog")
public String productName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "catalog")
public String productCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

Với **SimpleKeyGenerator** mặc định, một tham số kiểu **String** thường trở thành chính chuỗi đó. Hai lời gọi:

~~~text
productName("P01")      -> cache "catalog", key "P01"
productCategory("P01")  -> cache "catalog", key "P01"
~~~

cùng tra cứu **một entry**. Nếu **productName("P01")** được gọi đầu tiên, nó ghi, ví dụ, **"Máy pha cà phê"**; lần sau **productCategory("P01")** có thể trả chính **"Máy pha cà phê"** thay vì **"Thiết bị gia dụng"**. Phương thức tải category thậm chí không được chạy, vì Spring đã gặp cache hit.

~~~text
                   cacheName = catalog
productName(P01)  ─┐
                    ├─> key = "P01" ─> value = "Máy pha cà phê"
productCategory(P01)┘       ^
                            └── category() vô tình đọc value của name()
~~~

Tình huống dễ bị bỏ sót vì cả hai phương thức cùng trả **String**, không gây ngoại lệ ngay. Nếu một method mong đợi **Integer** hay một DTO khác, cache hit sai có thể dẫn tới **ClassCastException** tại bước trả kết quả hoặc ở mã gọi, nhưng không nên chờ tới khi có exception mới nhận ra lỗi.

**Quy tắc quan trọng:** Về logic, một entry được nhận diện bằng **(vùng cache, key)**. Cả vùng lẫn key phải dẫn đến **duy nhất một ý nghĩa dữ liệu hợp lệ**. Cùng key ở **hai vùng cache khác nhau** không đương nhiên va chạm, dù nhà cung cấp cache có thể có cách ánh xạ khóa vật lý riêng.

## 2. Vì sao key mặc định dễ trùng giữa các method?

Spring dùng **SimpleKeyGenerator** khi không có cấu hình **key** hoặc **keyGenerator** khác:

| Chữ ký | Key mặc định theo Spring | Rủi ro khi nhiều method cùng cache |
| --- | --- | --- |
| **getVersion()** | **SimpleKey.EMPTY** | Mọi method không tham số cùng cache đều trùng key |
| **findName("P01")** | Giá trị **"P01"** | Trùng với method khác cũng nhận **"P01"** |
| **findPrice("P01", "VND")** | **SimpleKey("P01", "VND")** | Trùng với method khác có cùng bộ tham số |
| **find(query)** | Dựa trên **query** nếu chỉ có một tham số thông thường | Lệ thuộc cách đối tượng biểu diễn identity và **equals/hashCode** |

Ở trường hợp một tham số duy nhất là **null** hoặc là mảng, **SimpleKeyGenerator** có xử lý riêng thay vì luôn trả đối tượng nguyên trạng; không nên suy diễn cách biểu diễn key từ kiểu dữ liệu bằng một quy tắc quá đơn giản.

Những thông tin **không tự được đưa vào key mặc định**:

- Tên class chứa phương thức.
- Tên phương thức.
- Kiểu trả về.
- Tên tham số trong mã Java.
- Vai trò nghiệp vụ của kết quả, chẳng hạn **name** hay **category**.
- Tenant, người đăng nhập, locale hoặc permission nếu chúng không nằm trong tham số tham gia tạo key.

Do đó, hai method hoàn toàn khác nhau vẫn có thể dùng chung một entry nếu chúng dùng cùng cache và sinh key bằng nhau.

### Hai phương thức không tham số còn dễ va chạm hơn

~~~java
@Cacheable("systemInfo")
public String appVersion() { return buildInfo.version(); }

@Cacheable("systemInfo")
public String deploymentRegion() { return environment.region(); }
~~~

Cả hai lời gọi đều dùng key **SimpleKey.EMPTY** trong vùng **systemInfo**. Nếu phương thức **appVersion()** ghi trước, **deploymentRegion()** sẽ có thể nhận phiên bản ứng dụng thay vì tên vùng triển khai. Điều này cũng đúng nếu hai method nằm ở **hai bean khác nhau** nhưng cùng dùng cache name đó và cùng CacheManager.

Việc thay thứ tự gọi có thể làm thay đổi giá trị sai được trả về. Lỗi vì vậy thường xuất hiện không ổn định ở môi trường có nhiều request đồng thời.

### Va chạm thực sự khác với trùng hash code

Trong cache lưu bằng cấu trúc map của Java, hai key có **hashCode** giống nhau chưa đủ để khẳng định chúng là cùng một key: map còn dùng so sánh **equals** để phân biệt. Vấn đề ở đây là hai lời gọi **tạo ra key thực sự bằng nhau về logic/so sánh**, chứ không chỉ tình cờ có hash code trùng.

Spring hiện đại dùng **SimpleKey** cho nhiều tham số để tính khóa tổ hợp có xét các thành phần, tránh kiểu tạo key chỉ từ hash code của các tham số trong phiên bản cũ. Tuy vậy, **SimpleKey** không tự phân biệt tên method.

## 3. Các hậu quả thực tế

| Tình huống | Hậu quả có thể xảy ra |
| --- | --- |
| Hai method trả cùng kiểu **String** nhưng khác ý nghĩa | Trả dữ liệu sai nhưng vẫn chạy êm |
| Một method trả **Product**, method kia trả **Price** | Có thể lỗi ép kiểu hoặc xử lý DTO sai |
| Hai endpoint dùng key **id** nhưng khác tenant | Có nguy cơ sử dụng chéo dữ liệu giữa tenant nếu cùng namespace cache |
| Method đầu trả snapshot cũ, method sau cần dữ liệu cập nhật | Một loại dữ liệu nhận kết quả và vòng đời của loại kia |
| Hai nhóm nghiệp vụ chia sẻ cache có TTL/eviction không phù hợp | Entry quan trọng bị đẩy ra hoặc được giữ quá lâu |
| Cache cập nhật bằng **@CachePut** dùng key trùng với vùng khác | Ghi đè entry của method khác |
| Cache xóa bằng **@CacheEvict** dùng key trùng | Xóa nhầm entry mà method khác đang sử dụng |

Không phải mọi sự trùng key đều sai: hai method thực sự có cùng hợp đồng dữ liệu, cùng kiểu, cùng cách tính và cùng yêu cầu độ mới **có thể chủ đích chia sẻ entry**. Nhưng trường hợp này phải được thiết kế, ghi nhận và kiểm thử; đừng mặc định những method có cùng tham số là tương đương.

## 4. Ví dụ Spring chạy được: tái hiện va chạm và cách sửa

Ví dụ sử dụng **Java 17+**, **Spring Framework 6.1.x** và **ConcurrentMapCacheManager**. Nó minh họa chính xác trường hợp hai method cùng cache, cùng key nhưng trả hai ý nghĩa khác nhau. Một bộ đếm trong thân method cho biết Spring có thực sự chạy nó hay không.

Cấu trúc thư mục:

~~~text
spring-cache-collision-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/cache/CacheCollisionDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-cache-collision-demo'
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
    mainClass = 'demo.cache.CacheCollisionDemo'
}
~~~

**src/main/java/demo/cache/CacheCollisionDemo.java**:

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
public class CacheCollisionDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "shared", "sharedNoArg", "safe", "safeNoArg");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheCollisionDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.name("P01"));
            System.out.println(service.category("P01"));
            System.out.println(service.category("P02"));
            System.out.println(service.name("P02"));

            System.out.println(service.version());
            System.out.println(service.region());

            System.out.println(service.safeName("P01"));
            System.out.println(service.safeCategory("P01"));
            System.out.println(service.safeName("P01"));

            System.out.println(service.safeVersion());
            System.out.println(service.safeRegion());
        }
    }

    public static class CatalogService {
        private int nameLoads;
        private int categoryLoads;
        private int versionLoads;
        private int regionLoads;
        private int safeNameLoads;
        private int safeCategoryLoads;
        private int safeVersionLoads;
        private int safeRegionLoads;

        // LỖI: Hai method chia sẻ cả cache name và key mặc định.
        @Cacheable(cacheNames = "shared")
        public String name(String id) {
            return "name:" + id + ":" + ++nameLoads;
        }

        @Cacheable(cacheNames = "shared")
        public String category(String id) {
            return "category:" + id + ":" + ++categoryLoads;
        }

        // LỖI: Hai method không tham số cùng SimpleKey.EMPTY.
        @Cacheable(cacheNames = "sharedNoArg")
        public String version() {
            return "version:" + ++versionLoads;
        }

        @Cacheable(cacheNames = "sharedNoArg")
        public String region() {
            return "region:" + ++regionLoads;
        }

        // SỬA: Hai method vẫn cùng cache, nhưng namespace khác nhau.
        @Cacheable(cacheNames = "safe", key = "'name:' + #p0")
        public String safeName(String id) {
            return "safe-name:" + id + ":" + ++safeNameLoads;
        }

        @Cacheable(cacheNames = "safe", key = "'category:' + #p0")
        public String safeCategory(String id) {
            return "safe-category:" + id + ":" + ++safeCategoryLoads;
        }

        // SỬA: Không tham số nhưng mỗi method có key hằng riêng.
        @Cacheable(cacheNames = "safeNoArg", key = "'version'")
        public String safeVersion() {
            return "safe-version:" + ++safeVersionLoads;
        }

        @Cacheable(cacheNames = "safeNoArg", key = "'region'")
        public String safeRegion() {
            return "safe-region:" + ++safeRegionLoads;
        }
    }
}
~~~

Chạy trong thư mục dự án bằng Gradle tương thích với JDK 17:

~~~bash
gradle run --quiet
~~~

Các dòng được in bởi **System.out.println** theo đúng thứ tự:

~~~text
name:P01:1
name:P01:1
category:P02:1
category:P02:1
version:1
version:1
safe-name:P01:1
safe-category:P01:1
safe-name:P01:1
safe-version:1
safe-region:1
~~~

Đọc kết quả:

1. **name("P01")** chạy trước và ghi **name:P01:1** dưới key **"P01"** trong cache **shared**.
2. **category("P01")** đáng lẽ trả chuỗi bắt đầu bằng **category** nhưng lại nhận **name:P01:1**; thân **category** chưa chạy.
3. **category("P02")** miss, trả **category:P02:1**. **name("P02")** sau đó bị hit nhầm và trả lại cùng chuỗi.
4. **version()** lưu **version:1** dưới **SimpleKey.EMPTY**. **region()** cũng nhận **version:1**, cho thấy va chạm không tham số.
5. **safeName("P01")** và **safeCategory("P01")** dùng chung vùng **safe**, nhưng key lần lượt là **"name:P01"** và **"category:P01"**, nên không trùng. Lần gọi thứ ba **safeName("P01")** hit đúng entry.
6. **safeVersion()** và **safeRegion()** dùng hai key hằng khác nhau nên nhận đúng giá trị.

**Vì sao annotation có tác dụng?** **@EnableCaching** bật interceptor, **CatalogService** là bean do Spring quản lý và được lấy qua ApplicationContext. Lời gọi từ **main** đi qua proxy. Nếu tạo đối tượng trực tiếp bằng **new CatalogService()** rồi gọi các method, cơ chế **@Cacheable** sẽ không được áp dụng theo cách này.

**Giới hạn ví dụ:** **ConcurrentMapCacheManager** chủ yếu phục vụ minh họa, không cung cấp eviction theo TTL/dung lượng như Caffeine hoặc Redis được cấu hình riêng. Mã không dùng database, không trình diễn transaction hoặc cache phân tán. Các bộ đếm là công cụ để quan sát method có chạy; ứng dụng thực tế cần metrics/test tương ứng.

## 5. Cách sửa ưu tiên: tách cache name theo ý nghĩa dữ liệu

Nếu hai method trả dữ liệu khác kiểu, có vòng đời khác hoặc thuộc hai nghiệp vụ độc lập, cách dễ hiểu nhất là tạo **hai cache name**:

~~~java
@Cacheable(cacheNames = "productNames")
public String findName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "productCategories")
public String findCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

Cùng **productId = "P01"** vẫn an toàn về mặt định danh vì chúng được tra trong hai cache khác nhau. Hơn nữa, cache name khác nhau giúp quản lý riêng **TTL, kích thước, eviction, metrics** khi provider hỗ trợ.

~~~text
("productNames",      "P01") -> "Máy pha cà phê"
("productCategories", "P01") -> "Thiết bị gia dụng"
~~~

Lưu ý: Trong cache phân tán, phải kiểm tra cách nhà cung cấp ánh xạ **logical cache name** thành **physical key/namespace**. Ví dụ cấu hình Redis cache thường dùng tiền tố theo tên cache; nếu đội ngũ tắt cơ chế prefix hoặc tự tạo cùng namespace vật lý cho nhiều vùng logic, cần kiểm tra lại nguy cơ xung đột.

**Không nên gộp cache chỉ để giảm số lượng tên.** Số cache name ít không phải mục tiêu hiệu năng tự thân. Chọn ranh giới dựa trên kiểu dữ liệu, vòng đời, bảo mật, khả năng quan sát và chính sách cập nhật.

## 6. Khi bắt buộc dùng chung cache: đặt namespace vào key

Một số hệ thống chủ đích dùng chung cache để chia sẻ ngân sách và vòng đời. Khi đó, key phải thể hiện **loại dữ liệu**:

~~~java
@Cacheable(cacheNames = "catalog", key = "'name:' + #p0")
public String findName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "catalog", key = "'category:' + #p0")
public String findCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

Trong SpEL, **'name:'** là chuỗi hằng; **#p0** là tham số thứ nhất. Đặt namespace khác nhau khiến hai method không dùng chung key dù nhận cùng ID.

Có thể dùng **#root.methodName** để giảm lặp:

~~~java
@Cacheable(cacheNames = "shared", key = "#root.methodName + ':' + #p0")
public String findName(String productId) { /* ... */ }
~~~

Đây chỉ là phương án đơn giản. **#root.methodName** không tự phân biệt **các class khác nhau có method cùng tên** hoặc **overload có cùng chuỗi key đầu ra**. Đổi tên method cũng đổi cache key, khiến dữ liệu cũ không còn được tra cứu bằng key mới. Khi cần tính ổn định lâu dài, đặc biệt với Redis/cache dùng giữa nhiều service, nên dùng namespace nghiệp vụ có phiên bản, ví dụ **"catalog:name:v1:"** và **"catalog:category:v1:"**.

### Tránh nối chuỗi nhập nhằng

Cách ghép **tenant + ":" + id** có thể trùng giữa các cặp dữ liệu khác nhau:

~~~text
tenant="a:b", id="c" -> "a:b:c"
tenant="a",   id="b:c" -> "a:b:c"
~~~

Nếu ID có thể chứa dấu phân cách, hãy sử dụng key có cấu trúc, mã hóa length-prefix hoặc escape có quy ước rõ ràng; không chỉ thêm dấu **":"** rồi mặc định duy nhất. Với cache trong JVM, một **record** bất biến biểu diễn khóa ghép có thể phù hợp; với Redis, phải xác định cách serialize sang khóa vật lý và kiểm thử tương ứng.

Ví dụ định nghĩa key nghiệp vụ (dùng trong code Java, không phụ thuộc provider cụ thể):

~~~java
public record ProductCacheKey(
        String namespace, String tenantId, String productId) {}
~~~

Một ứng dụng có thể xây dựng cùng kiểu key tại **KeyGenerator** hoặc helper khi dùng Cache API trực tiếp. Đừng đưa DTO tùy biến vào Redis trước khi xác minh serializer hỗ trợ và format key ổn định xuyên các phiên bản ứng dụng.

## 7. Dùng KeyGenerator khi nhiều phương thức phải theo cùng một quy tắc

Nếu hàng chục method cần namespace và định dạng key nhất quán, một **KeyGenerator** có thể tập trung quy tắc. Ví dụ tạo key có chứa định danh method và bộ tham số:

~~~java
// Mã cấu hình dùng trong ứng dụng Spring, không phải chương trình độc lập.
package demo.cache;

import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheKeyConfiguration {

    @Bean("methodAwareKeyGenerator")
    public KeyGenerator methodAwareKeyGenerator() {
        return (target, method, params) -> new SimpleKey(
                method.getDeclaringClass().getName(),
                method.toGenericString(),
                new SimpleKey(params));
    }
}
~~~

Khai báo sử dụng:

~~~java
@Cacheable(
    cacheNames = "shared",
    keyGenerator = "methodAwareKeyGenerator"
)
public ProductView findView(String id, String locale) {
    return repository.loadView(id, locale);
}
~~~

**Ý nghĩa:** key mang thông tin method và danh sách tham số, giúp giảm va chạm giữa các method trong cùng cache. **SimpleKey** thực hiện so sánh tổ hợp thay vì ghép chuỗi tùy tiện.

**Nhưng đây không phải key chuẩn cho mọi môi trường:** **method.getDeclaringClass()**, tên lớp, chữ ký generic hoặc interface/proxy có thể thay đổi khi refactor hay thay cách tạo bean; dạng key Java cũng phụ thuộc serializer nếu dùng cache phân tán. Nếu cần ổn định giữa các deployment/service, hãy định nghĩa **namespace nghiệp vụ và phiên bản key** tường minh, rồi kiểm thử round-trip serialization. **key** và **keyGenerator** là hai thuộc tính loại trừ nhau trên cùng một annotation.

Đối với nhiều tham số, key còn phải chứa **tất cả yếu tố thực sự làm thay đổi kết quả**. Không thể sửa va chạm giữa method bằng namespace rồi vô tình bỏ qua **tenantId**, **currency**, **language** hoặc quyền truy cập.

## 8. Đối xứng khóa đọc, ghi và xóa

Giả sử dùng chung vùng **catalog** với hai namespace. Phương thức đọc:

~~~java
@Cacheable(cacheNames = "catalog", key = "'name:' + #p0")
public String findName(String productId) {
    return repository.loadName(productId);
}
~~~

Khi cập nhật tên sản phẩm, khóa cần xóa phải **chính xác cùng biểu thức**:

~~~java
@CacheEvict(cacheNames = "catalog", key = "'name:' + #p0")
public void changeName(String productId, String newName) {
    repository.changeName(productId, newName);
}
~~~

Nếu bỏ **key** ở **changeName(productId, newName)**, Spring mặc định tạo một **SimpleKey(productId, newName)**, không phải **"name:P01"**. Entry tên cũ sẽ không bị xóa. Tương tự, nếu **@CachePut** ghi lại dữ liệu, nó phải dùng đúng định dạng key đọc để cập nhật đúng entry và không ghi đè namespace khác.

~~~java
// Cùng cache, cùng namespace => ghi đè đúng entry của findName().
@CachePut(cacheNames = "catalog", key = "'name:' + #p0")
public String renameAndReturnName(String productId, String newName) {
    repository.changeName(productId, newName);
    return newName;
}
~~~

Ví dụ **@CachePut** giả định **newName** chính là giá trị cuối cùng cần cache sau khi cập nhật thành công. Nếu DB chuẩn hóa hoặc biến đổi tên, cần trả giá trị thực tế đã ghi. Khi có transaction, phải xét **thời điểm commit** so với cache eviction/update: ghi DB và thay cache theo hai thời điểm không đồng bộ có thể sinh race condition. Đặt **@CachePut** và **@Cacheable** trên cùng method nói chung không nên vì một annotation luôn chạy method, còn một annotation có thể bỏ qua lời gọi.

**@CacheEvict(allEntries = true)** xóa toàn bộ vùng; đây là lựa chọn hợp lệ khi thật sự muốn invalidation toàn vùng, nhưng dùng thường xuyên để chữa key sai sẽ khiến nhiều method khác bị mất cache và tăng tải nguồn.

### Đừng sửa bằng cách chỉ đổi TTL

TTL ngắn có thể làm lỗi xuất hiện trong thời gian ngắn hơn nhưng **không chữa va chạm**: ngay sau khi một entry được nạp, method khác với cùng key vẫn có thể nhận giá trị sai. Cần sửa logic định danh key hoặc tách cache.

## 9. Nhiều bean, tenant và quyền truy cập

### Nhiều bean dùng cùng CacheManager

**@CacheConfig(cacheNames = "shared")** giúp khai báo cache name ở cấp class nhưng không tự bổ sung namespace class vào key. Nếu hai bean đều trỏ tới **shared** và tạo key **"A"**, chúng vẫn có thể xung đột. Tương tự, hai method có tên khác nhau nhưng cùng tham số không được Spring tự cách ly chỉ vì ở hai service.

### Tenant/user/locale không nằm trong tham số

~~~java
@Cacheable(cacheNames = "reports", key = "#p0")
public Report report(String reportId) {
    String tenantId = tenantContext.currentTenant();
    return repository.loadReport(tenantId, reportId);
}
~~~

Nếu tenant **A** và **B** có cùng **reportId**, kết quả có thể bị dùng chung sai. Cách thiết kế rõ ràng hơn là truyền tenant như một tham số nghiệp vụ:

~~~java
@Cacheable(cacheNames = "reports", key = "#p0 + ':' + #p1")
public Report report(String tenantId, String reportId) {
    return repository.loadReport(tenantId, reportId);
}
~~~

Biểu thức chuỗi này chỉ là ví dụ khi **tenantId/reportId** có cấu trúc bảo đảm không nhập nhằng; trong thực tế nên dùng key ghép có cấu trúc hoặc encoding chuẩn khi định danh có thể chứa dấu phân cách.

Đảm bảo caller không thể tự ý yêu cầu tenant khác: **phân quyền phải được kiểm tra độc lập trước khi sử dụng dữ liệu**, kể cả khi request hit cache. Đưa tenant vào key tránh va chạm nhưng tự nó không chứng minh user được phép truy cập tenant đó. Nguy cơ dữ liệu chéo người dùng có mức nghiêm trọng cao hơn va chạm giữa hai chuỗi hiển thị.

### Object làm key

Khi dùng DTO làm tham số duy nhất, **equals/hashCode** phải tương thích với nội dung thực sự quyết định kết quả, tốt nhất dựa trên dữ liệu bất biến. Dùng object mutable làm key có thể khiến việc tra cứu/eviction không ổn định; bỏ một trường quan trọng khỏi key có thể gây trùng dù DTO là hai đối tượng khác nhau. Với dữ liệu phân tán, còn phải xác định serializer và chuẩn hóa key.

## 10. Hệ quả khi dùng local cache, Redis hoặc nhiều cấp cache

| Cấu hình | Khả năng va chạm | Điều cần kiểm tra |
| --- | --- | --- |
| **ConcurrentMapCacheManager** | Cùng cache name + key bằng nhau sẽ dùng chung entry trong một instance | Hành vi có thể thấy qua demo và test |
| **Caffeine** trong JVM | Cùng cache name/key vẫn trùng; thêm giới hạn dung lượng/TTL không giải quyết key logic | Namespace, key object, capacity và eviction |
| **RedisCacheManager** | Cache name thường tham gia tiền tố khóa Redis theo cấu hình mặc định | Kiểm tra prefix, chuyển đổi key và cấu hình chia sẻ Redis |
| **Nhiều replica với cache local** | Lỗi có thể xảy ra riêng ở mỗi JVM, theo thứ tự request từng node | Test trên nhiều replica và đường invalidation |
| **Cache nhiều tầng** | Có thể trùng ở tầng local lẫn shared nếu quy tắc key không nhất quán | Đồng bộ naming, key encoding và invalidation |

Phân biệt **vùng cache Spring** với **key vật lý ở provider**. Ở local map, key là object Java; ở Redis, key thường được chuyển thành dạng lưu trữ trên server. Hai Java key không bằng nhau vẫn cần thử serialize khi đổi cấu hình vì quy tắc chuyển đổi có thể ảnh hưởng key vật lý.

Ngoài ra, nhiều method cùng cache có thể chia sẻ chung **capacity**, **TTL**, cơ chế refresh và thống kê. Ngay cả khi key đã có prefix, hai nhóm dữ liệu có kích thước và vòng đời khác nhau có thể làm nhau bị evict hoặc dùng chính sách hết hạn không phù hợp. Cân nhắc tách cache nếu chính sách vận hành khác nhau.

## 11. Kiểm thử để phát hiện va chạm trước khi phát hành

Một bài test đơn giản chỉ gọi **findName("P01")** hai lần rồi thấy cache hit là **chưa đủ**. Phải kiểm tra lời gọi **chéo giữa các method**.

Các bước nên có trong test tích hợp Spring:

1. Khởi tạo **CacheManager** sạch trước từng test; dùng bean service từ **ApplicationContext** để lời gọi đi qua proxy.
2. Gọi **method A** với key **K**, kiểm tra kết quả đúng và số lần thực thi thân method.
3. Gọi **method B** với cùng tham số **K**, kiểm tra nó vẫn trả dữ liệu đúng theo hợp đồng. Với cache dùng chung không chủ đích, đây là bước bắt lỗi.
4. Đảo thứ tự: gọi **B trước A**. Kết quả có thể khác khi method ghi entry trước thay đổi.
5. Thử method không tham số, method overload, các bean khác nhau cùng cache, và cùng ID ở hai tenant.
6. Thử **@CachePut/@CacheEvict** sau cập nhật nguồn; xác minh chỉ entry dự định được thay/xóa và không giữ dữ liệu cũ.
7. Chạy test với provider thực tế (đặc biệt khi key serialization/cấu hình prefix khác local cache) và kiểm tra cold start, concurrency, nhiều replica.

Ví dụ tình huống lỗi cần test:

~~~text
Given: cache "catalog" trống
When:  findName("P01") trả "Máy pha cà phê"
And:   findCategory("P01") được gọi
Then:  findCategory("P01") phải trả "Thiết bị gia dụng"
       và tuyệt đối không trả "Máy pha cà phê".
~~~

Sau khi đổi key, kiểm tra trực tiếp hoặc qua spy số lần method chạy. Nếu hệ thống có metrics, theo dõi hit/miss **theo từng cache**, và bổ sung log có kiểm soát cho **cache name + key type + namespace**. Tránh log giá trị key chứa dữ liệu nhạy cảm, email, token hoặc định danh người dùng ở nơi không được phép.

### Khi đổi key format ở môi trường đã có dữ liệu

Một sửa đổi từ key **"P01"** sang **"name:P01"** có thể khiến ứng dụng tạo entry mới; entry cũ **"P01"** có thể tiếp tục tồn tại tới khi bị eviction/expiration. Nếu nhiều phiên bản ứng dụng đang cùng chạy, phiên bản cũ vẫn có thể ghi key sai vào vùng cache chung.

Vì vậy, khi triển khai cần xét **tương thích giữa bản cũ và bản mới**: có thể đổi sang cache name mới, dùng versioned namespace, làm sạch có kiểm soát các key cũ, hoặc phối hợp rollout để mọi replica cùng dùng quy tắc mới. Việc xóa toàn bộ cache đang phục vụ production cần dự tính tải miss tới nguồn.

## 12. Checklist thiết kế key an toàn

Trước khi cho hai phương thức chia sẻ cache name, hãy trả lời:

- **Giá trị có cùng ý nghĩa không?** Cùng kiểu Java chưa chắc cùng hợp đồng nghiệp vụ.
- **Các method có bao giờ tạo cùng key không?** Thử cả trường hợp không tham số và các tổ hợp tham số thực tế.
- **Key có thể phân biệt method/domain/tenant cần thiết không?** Không dựa vào tên method mặc định.
- **Các trường làm thay đổi kết quả đã có trong key chưa?** Ví dụ locale, currency, policy, user và phiên bản dữ liệu.
- **Key có ổn định và không nhập nhằng không?** Cân nhắc equals/hashCode, immutable value, cách encode và version.
- **Ghi/xóa có dùng cùng cache và key với đọc không?** So khớp **@Cacheable**, **@CachePut**, **@CacheEvict**.
- **Mọi bên dùng cùng provider/serializer có quy ước tương thích không?** Đặc biệt Redis hoặc cache đa service.
- **TTL, dung lượng, loại giá trị và security boundary có tương thích để dùng chung một vùng không?**

Nếu không thể chứng minh tính tương thích, chọn **cache name riêng theo loại dữ liệu** là mặc định dễ kiểm soát hơn. Nếu cần dùng chung, đặt namespace đủ phân biệt, nhất quán giữa đọc/ghi/xóa và có test chéo method.

## 13. Câu hỏi tự kiểm tra

1. Vì sao **getVersion()** và **getRegion()** có thể trùng key khi cùng **@Cacheable("systemInfo")**, dù hai method có tên khác nhau?
2. Tại sao hai method cùng trả **String** vẫn có thể gây lỗi nghiêm trọng mà không phát sinh **ClassCastException**?
3. Phân biệt **hai key có cùng hashCode** với **hai key thực sự bằng nhau** trong cache dạng map.
4. Khi nào nên tách **cacheNames**, khi nào dùng **namespace trong key**?
5. Vì sao **key = "#root.methodName + ':' + #p0"** chưa chắc đủ để phân biệt hai method của hai bean?
6. Nếu đọc dùng key **"name:P01"**, còn xóa cache dùng key mặc định của **changeName("P01", "Tên mới")**, chuyện gì xảy ra?
7. Vì sao đổi TTL không sửa được xung đột key?
8. Khi cache chứa dữ liệu theo tenant, đưa tenant vào key có thay thế kiểm tra phân quyền hay không?

Tư duy cần giữ: **tên cache + khóa phải xác định đúng một loại giá trị cho đúng ngữ cảnh, trên mọi đường đọc, ghi và xóa**. Chỉ khi chứng minh được sự tương đương về dữ liệu mới nên chủ đích cho nhiều method tái sử dụng một entry.

### Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Default Key Generation, Custom Key, SpEL, @Cacheable, @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Spring AOP proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Data Redis — Redis Cache configuration and prefix behavior: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html

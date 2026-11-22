# Phân biệt cấu hình ứng dụng với cấu hình riêng của kho cache trong Spring Framework

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích **cấu hình ứng dụng** kiểm soát điều gì, **cấu hình hạ tầng Spring Cache** kết nối các thành phần ra sao, và **cấu hình từng kho cache** quyết định chính sách lưu trữ thế nào. Bạn cũng có thể xác định đúng nơi đặt TTL, giới hạn dung lượng, cách chọn provider, cách ánh xạ tên cache, và cách kiểm tra một cấu hình có thực sự được áp dụng hay không.

Phạm vi: Spring Framework Cache Abstraction (bộ API cache độc lập với nhà cung cấp), có đối chiếu riêng với Spring Boot khi dùng tính năng tự cấu hình. Bài không mặc định rằng mọi dự án Spring Framework đều dùng Spring Boot.

## 1. Ba lớp cấu hình trong kiến trúc

Một ứng dụng có thể chứa nhiều kho cache có tên khác nhau. Ví dụ: dữ liệu sản phẩm ít thay đổi, còn tỷ giá cập nhật nhanh. Cùng sử dụng annotation của Spring, nhưng hai cache cần chính sách hết hạn và dung lượng khác nhau.

| Lớp | Quyết định điều gì? | Ví dụ | Đối tượng chịu trách nhiệm |
| --- | --- | --- | --- |
| **Cấu hình ứng dụng** | Môi trường chạy, kết nối hệ thống, các giới hạn nghiệp vụ, bật hoặc tắt chiến lược cache theo yêu cầu ứng dụng | Endpoint dịch vụ, profile, biến môi trường, feature flag, chính sách có được phép cache thông tin nhạy cảm hay không | Ứng dụng và người vận hành |
| **Cấu hình hạ tầng Spring Cache** | Bật xử lý annotation; chọn CacheManager, CacheResolver, KeyGenerator, ErrorHandler; xác định cách gọi phương thức đi qua proxy | @EnableCaching, bean CacheManager, @CachingConfigurer hoặc cấu hình tương đương | Spring container và mã cấu hình tích hợp |
| **Cấu hình kho cache (provider / từng cache)** | Dữ liệu được giữ ở đâu, trong bao lâu, tối đa bao nhiêu mục, bị loại bỏ khi nào, có chia sẻ giữa các instance hay không, cách serialize | products: TTL 5 phút, tối đa 500 mục; rates: TTL 30 giây, tối đa 100 mục | Caffeine, Redis, Ehcache hoặc provider khác |

Trong giao tiếp thường ngày, hai lớp đầu có thể cùng được gọi là “cấu hình ứng dụng”. Khi thiết kế hoặc tìm lỗi, nên tách rõ **cấu hình chung của ứng dụng**, **cấu hình tích hợp Spring Cache**, và **chính sách thực thi của kho cache** để không đặt tham số sai tầng.

Luồng xử lý đơn giản khi gọi phương thức có @Cacheable:

~~~text
Caller bên ngoài bean
  -> Spring AOP proxy / CacheInterceptor
  -> xác định cache name + key (qua CacheResolver / KeyGenerator nếu cần)
  -> CacheManager lấy Cache tương ứng
      -> HIT: trả dữ liệu đã lưu
      -> MISS: gọi phương thức thật rồi ghi kết quả vào Cache
  -> provider quản lý TTL, dung lượng, loại bỏ mục và lưu trữ
~~~

**Chốt ranh giới:** annotation @Cacheable chọn thao tác, tên cache và khóa; bản thân nó **không** tự tạo chính sách TTL, dung lượng hoặc mô hình lưu trữ phân tán.

## 2. Cấu hình ứng dụng: ý định sử dụng và quy tắc chung

Cấu hình ứng dụng mô tả cách hệ thống hoạt động trong từng môi trường. Ví dụ, ứng dụng dùng dịch vụ tra cứu sản phẩm và cho phép cache kết quả tra cứu công khai trong thời gian ngắn. Các thuộc tính do ứng dụng tự định nghĩa có thể được đặt trong file cấu hình, biến môi trường hoặc hệ thống quản lý cấu hình.

~~~yaml
# Ví dụ thuộc tính do ứng dụng tự thiết kế;
# Spring Framework thuần không tự hiểu hay tự áp dụng nhóm app.*.
app:
  catalog:
    endpoint: "https://catalog.example.test"
  features:
    catalog-cache-enabled: true
~~~

Muốn các thuộc tính trên phát huy tác dụng, **mã ứng dụng phải đọc và sử dụng chúng**, chẳng hạn qua Environment, @Value hoặc một bean cấu hình được bind bởi thư viện thích hợp. Đặt một khóa tùy ý vào YAML không làm Spring Cache tự bật hoặc thay đổi TTL.

Ví dụ về quyết định ở cấp ứng dụng:
- Cache loại dữ liệu nào và không cache loại nào (thông tin cá nhân, token, kết quả phụ thuộc quyền người dùng cần đặc biệt thận trọng).
- Cache để giảm tải cho thao tác đọc nào, giới hạn mức dữ liệu cũ chấp nhận được là bao nhiêu.
- Khi nào dữ liệu thay đổi và thao tác nghiệp vụ nào phải hủy hoặc cập nhật mục tương ứng.
- Trong mỗi môi trường, chọn lưu cục bộ hay dùng kho chia sẻ giữa nhiều instance.

Những quyết định này **dẫn tới** lựa chọn chính sách cache, nhưng chỉ có hiệu lực lưu trữ khi được ánh xạ thành cấu hình cụ thể ở provider.

### Bật Spring Cache và nối các thành phần

Trong một ứng dụng Spring Framework dùng annotation, thường có:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructureConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "rates");
    }
}
~~~

Đây là **đoạn minh họa tích hợp**, chưa phải chương trình Java độc lập. Các import tương ứng gồm @Configuration, @EnableCaching, @Bean, CacheManager và ConcurrentMapCacheManager của Spring.

- @EnableCaching kích hoạt xử lý annotation cache bằng cơ chế Spring AOP (mặc định là proxy).
- Bean CacheManager cho Spring biết tìm đối tượng Cache ở đâu theo tên.
- Các tên products/rates ở đây là **tên kho logic**, không phải TTL hay số lượng tối đa.
- ConcurrentMapCacheManager dựa trên bộ nhớ trong tiến trình, phù hợp thử nghiệm hoặc trường hợp đơn giản; nó **không cung cấp TTL hay hợp đồng loại bỏ theo dung lượng** như một cache provider chuyên dụng.

Trong Spring Framework thuần, khai báo một file application.yml **không đủ** để tự sinh CacheManager. Spring Boot có lớp auto-configuration riêng, được giải thích ở mục 6.

## 3. Cấu hình kho cache: quy tắc lưu trữ thực tế

**Kho cache** là một không gian lưu các cặp key/value. **CacheManager** quản lý và cung cấp các kho đó; tên trên @Cacheable cần được resolve tới kho tồn tại hoặc có thể tạo theo cơ chế của manager.

Những thông số thường thuộc cấu hình kho cache/provider:

| Thông số | Ý nghĩa | Hệ quả cần biết |
| --- | --- | --- |
| **TTL / expireAfterWrite** | Thời hạn một entry kể từ lúc ghi/cập nhật | Tránh giữ dữ liệu quá cũ; đến hạn không đồng nghĩa luôn bị xóa vật lý ngay lập tức |
| **expireAfterAccess** | Hết hạn sau khoảng không được truy cập | Những mục được truy cập liên tục có thể tồn tại lâu hơn expireAfterWrite |
| **maximumSize / capacity** | Giới hạn ước lượng số entry có thể giữ | Provider chọn entry để loại bỏ khi cần; không phải giới hạn số request |
| **Eviction policy** | Cách chọn mục bị loại khi đầy | Khác với expiration do thời gian; tùy provider |
| **Serialization / key prefix** | Biểu diễn key/value, định danh namespace | Cần nhất quán giữa phiên bản ứng dụng khi dùng kho từ xa |
| **Store topology** | Local per process, distributed/shared, persistence | Ảnh hưởng đến đồng bộ giữa instance, triển khai, restart và latency |
| **Null values / failure behavior** | Có chấp nhận null, xử lý lỗi cache ra sao | Phụ thuộc Cache implementation, CacheManager và chính sách ứng dụng |

**Không có một bộ tham số TTL, max-size dùng chung cho mọi CacheManager.** Spring Cache là abstraction; mỗi provider có API và phạm vi cấu hình riêng. Ví dụ, Caffeine quản lý cache trong JVM; Redis có thể giữ dữ liệu trên server chung nhưng yêu cầu cấu hình kết nối, TTL và serialization thích hợp.

Cùng một ứng dụng có thể cần:
- **products**: dữ liệu công khai, biến động vừa phải; hết hạn sau 5 phút, giữ tối đa 500 mục.
- **rates**: dữ liệu nhạy với thời gian; hết hạn sau 30 giây, giữ tối đa 100 mục.

Đây là **hai chính sách cho hai cache khác nhau**. Nếu cấu hình một CaffeineCacheManager với một cấu hình chung (ví dụ setCaffeine hoặc setCacheSpecification), cấu hình ấy áp dụng cho các cache do manager tạo theo cơ chế đó. Để hai tên có chính sách khác nhau, hãy tạo từng Cache với builder riêng rồi đăng ký vào SimpleCacheManager, hoặc dùng cơ chế per-cache chính thức của provider/manager đang chọn.

### Cấu hình từng cache bằng Caffeine

Mô hình Java rõ ràng là:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCache products = new CaffeineCache(
        "products",
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5))
            .build()
    );

    CaffeineCache rates = new CaffeineCache(
        "rates",
        Caffeine.newBuilder()
            .maximumSize(100)
            .expireAfterWrite(Duration.ofSeconds(30))
            .build()
    );

    SimpleCacheManager manager = new SimpleCacheManager();
    manager.setCaches(List.of(products, rates));
    return manager;
}
~~~

Đây là **đoạn trích cấu hình**; chương trình độc lập đầy đủ ở mục tiếp theo. CaffeineCache bọc cache thực của thư viện Caffeine và phơi bày nó qua giao diện Spring Cache. SimpleCacheManager giữ danh sách các cache đã đăng ký; tên @Cacheable phải khớp products hoặc rates.

Lưu ý: Caffeine là cache **cục bộ trong từng JVM**. Nếu có ba instance ứng dụng, mỗi instance sẽ có dữ liệu cache riêng. Thiết lập thời hạn 30 giây giống nhau không biến ba cache cục bộ thành một cache chung.

## 4. Ví dụ Java 17 chạy được: cùng một ứng dụng, hai chính sách riêng

Ví dụ dưới đây dùng **Spring Framework thuần, không cần Spring Boot**, Maven và Java 17+. Nó chứng minh đồng thời: Spring chỉ gọi phương thức thật khi cache miss, hai tên cache trỏ tới hai bộ chính sách khác nhau, và @CacheEvict làm dữ liệu được tính lại.

Cấu trúc dự án:

~~~text
spring-cache-scope-demo/
├── pom.xml
└── src/main/java/demo/CacheDemo.java
~~~

**pom.xml** (hai artifact Spring dùng cùng phiên bản):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-scope-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>${spring.version}</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/CacheDemo.java**:

~~~java
package demo;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheDemo {
    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            CaffeineCache products = new CaffeineCache(
                "products",
                Caffeine.newBuilder()
                    .maximumSize(500)
                    .expireAfterWrite(Duration.ofMinutes(5))
                    .build()
            );
            CaffeineCache rates = new CaffeineCache(
                "rates",
                Caffeine.newBuilder()
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofSeconds(30))
                    .build()
            );

            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(products, rates));
            return manager;
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger rateLoads = new AtomicInteger();

        @Cacheable(cacheNames = "products")
        public String product(String id) {
            int n = productLoads.incrementAndGet();
            return "product-" + id + "/load-" + n;
        }

        @Cacheable(cacheNames = "rates")
        public String rate(String currency) {
            int n = rateLoads.incrementAndGet();
            return "rate-" + currency + "/fetch-" + n;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void invalidateProduct(String id) {
            // Nguồn dữ liệu thực tế sẽ được cập nhật ở nơi phù hợp.
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.product("42"));
            System.out.println(service.product("42"));
            System.out.println(service.rate("USD"));
            System.out.println(service.rate("USD"));

            service.invalidateProduct("42");
            System.out.println(service.product("42"));
        }
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheDemo
~~~

Năm dòng do chương trình ghi ra **stdout** (không kể log của công cụ chạy nếu có):

~~~text
product-42/load-1
product-42/load-1
rate-USD/fetch-1
rate-USD/fetch-1
product-42/load-2
~~~

Giải thích lần lượt:
1. Lần đầu đọc sản phẩm 42 là cache miss; phương thức thực chạy và tăng productLoads lên 1.
2. Lần thứ hai là cache hit; trả lại chuỗi cũ, không gọi phương thức thật.
3. Lần đầu đọc tỷ giá USD là miss của **cache rates độc lập**.
4. Lần thứ hai đọc USD là hit.
5. invalidateProduct("42") xóa key tương ứng trong products, nên lần đọc tiếp theo tải lại và tăng productLoads lên 2.

Với một tham số String, key mặc định của Spring là chính tham số đó; vì vậy key "#p0" trong @CacheEvict khớp entry do @Cacheable tạo. @Cacheable và @CacheEvict được gọi **từ bên ngoài qua Spring bean proxy**. Chương trình không đợi quá 30 giây hoặc 5 phút; nó kiểm tra hit và invalidation, còn quy tắc hết hạn là do hai builder Caffeine khai báo.

### Thí nghiệm mở rộng

Có thể thử thay đổi **chỉ** maximumSize hoặc expireAfterWrite của products, giữ nguyên rates, rồi quan sát hành vi khi chờ vượt thời hạn hoặc phát sinh nhiều key. Đây là thử nghiệm cấu hình **một kho**, không yêu cầu sửa annotation @Cacheable ở phương thức rate. Không nên dùng việc “sau đúng N giây entry đã biến mất khỏi bộ nhớ vật lý” làm tiêu chí; expiration được kiểm tra theo hoạt động và chính sách bảo trì của provider.

## 5. Phạm vi cấu hình khác nhau, kết quả khác nhau

### 5.1 Một provider, chính sách chung

Nếu mục tiêu là mọi cache dùng **cùng** thời hạn và dung lượng, có thể cấu hình CaffeineCacheManager với một Caffeine builder chung:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager =
        new CaffeineCacheManager("products", "rates");
    manager.setCaffeine(
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5))
    );
    return manager;
}
~~~

Đây là **phương án thay thế**, không dùng cùng lúc với bean cacheManager trong ví dụ đầy đủ. Ở đây cả products **và** rates cùng chính sách. Việc đặt hai tên vào constructor chỉ xác định hai cache được quản lý; nó không tạo hai TTL riêng.

### 5.2 Phân biệt tên cache, khóa và TTL

Ba khái niệm thường bị nhầm:
- **cacheNames**: nơi lưu logic, ví dụ products. Nó giúp Spring định vị Cache qua CacheManager.
- **key** hoặc KeyGenerator: định danh một entry trong cache; mặc định dựa trên các tham số phương thức. Có thể dùng SpEL như "#p0", và phải bảo đảm khóa không nhầm dữ liệu giữa tenant/người dùng.
- **TTL/maximumSize**: chính sách sống và dung lượng của các entry, nằm ở provider.

Thay @Cacheable(cacheNames = "products") thành @Cacheable(cacheNames = "rates") khiến phương thức sử dụng **kho khác**; thao tác này không tự thay đổi cấu hình kho đã tồn tại. Ngược lại, đổi TTL của products tại provider thường không cần sửa annotation của từng phương thức đang dùng products.

### 5.3 Cấu hình default, theo class, theo method

Spring cho phép khai báo mặc định tích hợp ở cấp CacheManager/CacheResolver/KeyGenerator; @CacheConfig có thể gom một số thiết lập thường dùng ở **cấp class**; annotation trên **method** có thể chọn cacheNames, key, cacheManager hoặc cacheResolver cụ thể. Ví dụ:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductReader {
    @Cacheable(key = "#p0")
    public Product find(String id) {
        // mã nghiệp vụ (đoạn minh họa, không chạy độc lập)
        return loadProduct(id);
    }
}
~~~

**@CacheConfig không có thuộc tính đặt TTL hay maximumSize**. Nó giúp giảm lặp cấu hình *liên kết operation với cache*, không thay thế cấu hình lưu trữ. Đoạn trên minh họa cấu trúc; Product và loadProduct cần được ứng dụng tự định nghĩa.

Nếu ứng dụng có nhiều CacheManager, lựa chọn manager bằng cách cấu hình rõ ràng hoặc dùng thuộc tính cacheManager tại operation khi cần. Không cấu hình đồng thời cacheManager và cacheResolver trên cùng một operation vì chúng là hai cách lựa chọn cache loại trừ nhau.

## 6. Spring Framework thuần và Spring Boot: nơi khai báo khác nhau

**Spring Framework** cung cấp interface và annotation như CacheManager, Cache, @EnableCaching, @Cacheable. Bạn chủ động đăng ký các bean cấu hình cần thiết.

**Spring Boot** bổ sung cơ chế auto-configuration và hỗ trợ các thuộc tính chuẩn nếu dependency, provider và điều kiện tự cấu hình phù hợp. Ví dụ khi sử dụng Boot với Caffeine và để Boot tạo CacheManager:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: "products,rates"
    caffeine:
      spec: "maximumSize=500,expireAfterWrite=300s"
~~~

Trong ví dụ Boot này, **cả hai cache dùng cùng spec Caffeine**. Đây không phải cấu hình TTL riêng cho rates. Nếu cần hai TTL khác nhau, bạn phải dùng cơ chế tạo cache riêng tương ứng, như ví dụ SimpleCacheManager ở mục 4, hoặc customizer/cơ chế thích hợp với phiên bản/provider.

Phải đặc biệt lưu ý:
- Thuộc tính spring.cache.* là **cơ chế của Spring Boot**, không phải đặc tính tự có của Spring Framework thuần.
- Khi ứng dụng đã tự cung cấp CacheManager bean, cơ chế tự cấu hình mặc định của Boot có thể không tạo hoặc không điều chỉnh manager như bạn nghĩ. Kiểm tra bean thực tế trong ApplicationContext và điều kiện auto-configuration.
- @EnableCaching vẫn là bước kích hoạt xử lý annotation; có CacheManager hoặc cấu hình properties mà không bật annotation caching thì @Cacheable chưa chắc được áp dụng.
- Khi đổi provider (Caffeine -> Redis), đừng giả định thuộc tính expireAfterWrite hoặc maximumSize áp dụng giống nhau. Phải kiểm tra API của provider mới.

## 7. Ví dụ quyết định kiến trúc thực tế

Giả sử hệ thống có ba loại dữ liệu:

| Dữ liệu | Mức chấp nhận dữ liệu cũ | Đề xuất kỹ thuật | Cần quyết định ở tầng nào? |
| --- | --- | --- | --- |
| Danh mục sản phẩm công khai | Chấp nhận vài phút | Cache products, TTL khoảng 5 phút, giới hạn dung lượng, invalidate khi sửa sản phẩm | Nghiệp vụ chọn mức stale chấp nhận được; provider thực thi TTL |
| Tỷ giá hiển thị | Chấp nhận rất ngắn | Cache rates, TTL khoảng 30 giây; nguồn phải chịu được miss | Nghiệp vụ ấn định freshness; provider thực thi |
| Quyền truy cập từng người dùng | Rất nhạy cảm | Thường tránh cache tùy tiện; nếu buộc phải cache cần key chứa đúng ngữ cảnh, TTL ngắn và invalidation chắc chắn | Quy tắc bảo mật ở ứng dụng; khóa và vòng đời ở cả hai tầng |

Các con số chỉ là **giả định bài tập**, phải được đánh giá theo tải, SLA, thay đổi dữ liệu và yêu cầu nhất quán thực tế.

Với nhiều instance:
- **Caffeine** là kho cục bộ từng process. Xóa entry ở instance A không tự xóa entry tương tự ở instance B.
- **Redis** thường được chọn khi cần kho chia sẻ giữa các instance, nhưng cần tính latency mạng, mất kết nối, cấu hình prefix/key, serializer và version dữ liệu. “Chung cache” không tự đảm bảo nghiệp vụ đồng bộ hoàn hảo.
- Thay đổi cấu hình provider (TTL, key prefix, serializer) có thể ảnh hưởng dữ liệu cũ; nên lập kế hoạch chuyển đổi và quan sát sau triển khai.

Phân biệt thêm: **expiration** làm entry mất hiệu lực theo thời gian; **eviction** loại entry vì chính sách dung lượng; **invalidation** là hành động xóa/cập nhật có chủ đích khi dữ liệu gốc đổi. Không nên coi ba cơ chế là một.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng / nhầm lẫn | Nguyên nhân có thể | Cách kiểm chứng hoặc khắc phục |
| --- | --- | --- |
| Gắn @Cacheable nhưng phương thức vẫn chạy mỗi lần | Chưa @EnableCaching, gọi từ self-invocation, bean không qua Spring proxy, phương thức không được proxy hỗ trợ | Lấy bean từ ApplicationContext, gọi từ bean khác; kiểm tra @EnableCaching và luồng gọi |
| Đặt cacheNames mà không thấy TTL | Tên cache không định nghĩa chính sách hết hạn | Đọc cấu hình Cache provider/CacheManager và lấy cache thật bằng getCache(name) |
| Cấu hình một spec Caffeine nhưng tưởng mỗi cache khác nhau | Dùng cùng builder/spec của manager cho toàn bộ cache | Tạo từng CaffeineCache với builder riêng hoặc dùng hỗ trợ per-cache của provider |
| YAML spring.cache.* không có hiệu lực | Dùng Spring Framework thuần, hoặc Boot custom CacheManager đã thay auto-configuration | Xác định framework, bean CacheManager đang chạy và configuration report tương ứng |
| Thấy cache hit nhưng vẫn trả dữ liệu cũ sau khi cập nhật DB | Thiếu @CacheEvict/@CachePut, key không khớp, invalidation chưa lan giữa instance | Truy vết sự kiện ghi dữ liệu, key, tên cache và khả năng vô hiệu hóa ở provider |
| Entry biến mất sớm hoặc không xuất hiện ở instance khác | Cache có giới hạn size, hết hạn theo thời gian hoặc lưu cục bộ mỗi JVM | Xem chính sách eviction/TTL và topology thực tế |
| Trả nhầm dữ liệu giữa người dùng/tenant | Key chỉ chứa id dữ liệu, bỏ qua tenant hoặc quyền truy cập | Thiết kế key phân vùng đầy đủ; tránh cache kết quả nhạy cảm khi chưa có ranh giới bảo mật đúng |
| Không có cache name mong đợi | Manager chỉ đăng ký tên cố định, nhưng annotation dùng tên khác | Đối chiếu cacheNames với danh sách CacheManager.getCacheNames() |

Cách kiểm tra theo thứ tự có thể lặp lại:
1. **Xác nhận hành vi mong muốn:** dữ liệu nào, mức độ stale được chấp nhận, trường hợp cần invalidation.
2. **Xác nhận cơ chế Spring:** @EnableCaching, CacheManager bean thực tế, proxy, cacheNames và key.
3. **Xác nhận provider và policy:** TTL, capacity, serialization, cấu hình từng tên cache, local hay distributed.
4. **Đo runtime:** gọi cùng key hai lần để kiểm tra hit; cập nhật dữ liệu rồi kiểm tra invalidation; quan sát metrics hit/miss/eviction nếu provider và hệ thống metrics có hỗ trợ.
5. **Kiểm tra nhiều instance khi cần:** cùng key trên các instance khác nhau; đừng suy từ một JVM ra tính nhất quán toàn hệ thống.

## 9. Tự kiểm tra

**Tình huống A:** ApplicationContext có bean CacheManager quản lý products và rates, nhưng hai cache đều dùng cùng cấu hình Caffeine expireAfterWrite(5 phút). Thêm @Cacheable("rates") có khiến rates tự hết hạn sau 30 giây không?

**Không.** Annotation chỉ định tên cache được dùng; TTL vẫn là 5 phút cho cả hai theo chính sách chung. Phải tạo cấu hình riêng cho rates ở provider.

**Tình huống B:** Đổi TTL products từ 5 phút xuống 1 phút, trong khi method đang dùng @Cacheable(cacheNames = "products"). Cần sửa annotation không?

**Thông thường không.** Nếu giữ nguyên tên và manager, chỉ thay chính sách của products. Cần kiểm tra thay đổi được nạp lại như thế nào và vòng đời các entry hiện có khi triển khai.

**Tình huống C:** Một Spring Framework thuần có application.yml ghi spring.cache.caffeine.spec. Nó tự bật @Cacheable và tự tạo CaffeineCacheManager chứ?

**Không thể kết luận như vậy.** Đó là property convention của Spring Boot; Spring Framework thuần cần cấu hình bean và bật cache annotation rõ ràng.

## 10. Ghi nhớ

- **Cấu hình ứng dụng** nêu mục tiêu, môi trường và ràng buộc nghiệp vụ.
- **Cấu hình tích hợp Spring Cache** bật xử lý annotation và nối operation tới CacheManager/Cache.
- **Cấu hình từng kho cache** nêu chính sách lưu trữ thật: TTL, dung lượng, eviction, serializer, topology.
- **Cache name khác key và khác TTL.** Muốn mỗi kho có chính sách riêng, phải dùng đúng khả năng per-cache của provider.
- Luôn xác minh **bean đang chạy và hành vi runtime**, đặc biệt khi Spring Boot tự cấu hình, nhiều provider hoặc nhiều instance.

### Tài liệu tra cứu chính thức

- Spring Framework – Caching annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Configuring cache storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Boot – Caching auto-configuration (chỉ áp dụng nếu dự án dùng Boot): https://docs.spring.io/spring-boot/reference/io/caching.html

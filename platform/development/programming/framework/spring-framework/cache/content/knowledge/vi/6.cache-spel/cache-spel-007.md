# Phân biệt key với keyGenerator và lỗi khi khai báo cả hai trong Spring Cache

## Mục tiêu bài học

Sau bài này, bạn có thể: (1) phân biệt thuộc tính **key** viết bằng Spring Expression Language (SpEL) với thuộc tính **keyGenerator** chỉ định bean Java; (2) chọn đúng cách tạo khóa cho từng phương thức cache; (3) giải thích vì sao khai báo cả hai ngay trên cùng một cache operation là lỗi; (4) phân biệt xung đột thực sự với việc phương thức ghi đè cấu hình mặc định ở **@CacheConfig**; và (5) tạo, chạy, kiểm tra được ví dụ Spring Cache bằng Java 17+.

Bài tập trung vào tính năng annotation caching của **Spring Framework**. Spring Boot cũng sử dụng các annotation này nhưng cơ chế tự cấu hình bean của Boot là một tầng khác. Nội dung chỉ dùng tên và ngữ nghĩa API Spring Cache, không phụ thuộc một cache provider cụ thể.

## 1. Vì sao Spring cần một khóa cache?

Mỗi cache là một kho lưu trữ các cặp **key → value**. Khi một phương thức được đánh dấu @Cacheable được gọi từ bên ngoài qua proxy phù hợp, Spring cần xác định **khóa** để kiểm tra cache trước khi gọi phương thức thật.

~~~text
Caller
  -> Spring Cache interceptor
      -> chọn cache (cacheNames / CacheResolver)
      -> tạo key (SpEL key hoặc KeyGenerator)
      -> tìm entry trong cache
            HIT  -> trả giá trị đã cache
            MISS -> chạy method thật -> ghi value bằng key đã tính
~~~

**Cache name** và **cache key** khác nhau. Ví dụ cache có tên prices chứa các key như "SKU-01" và "SKU-02". Đổi cacheNames là đổi nơi tra cứu; đổi key là đổi danh tính entry bên trong nơi đó.

Annotation có ba cách tạo khóa thường gặp:

~~~java
// Đoạn minh họa, không phải chương trình Java hoàn chỉnh.
@Cacheable(cacheNames = "prices")
public Price findPrice(String sku) { ... } // dùng KeyGenerator mặc định

@Cacheable(cacheNames = "prices", key = "#p0")
public Price findBySku(String sku) { ... } // SpEL chọn tham số đầu

@Cacheable(cacheNames = "prices", keyGenerator = "skuKeyGenerator")
public Price findNormalized(String sku) { ... } // dùng bean Java theo tên
~~~

Cả ba trường hợp đều lưu trong cache logic prices, nhưng quy tắc tính key có thể khác. Giá trị **key** là một **biểu thức SpEL**; giá trị **keyGenerator** là **tên bean triển khai KeyGenerator**, không phải một biểu thức SpEL.

## 2. Thuộc tính key: SpEL tính khóa cho một operation

Cú pháp thường gặp:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) { ... }
~~~

Đây là đoạn minh họa signature; Product và phần thân ứng dụng cần được định nghĩa. Biểu thức **#p0** trỏ tới tham số thứ nhất (chỉ số 0). Spring đánh giá biểu thức trong ngữ cảnh lời gọi, rồi dùng **kết quả đánh giá** làm object key. Nhờ vậy, có thể chọn tham số, thuộc tính tham số, ghép nhiều thành phần hoặc gọi phương thức chuẩn hóa.

Một số biểu thức phù hợp:

| Biểu thức key | Ý nghĩa | Điều kiện/lưu ý |
| --- | --- | --- |
| **#p0** hoặc **#a0** | Lấy đối số thứ nhất | Không phụ thuộc tên tham số Java |
| **#root.args[0]** | Cũng lấy đối số thứ nhất từ root object | Dùng khi cần nhìn rõ cấu trúc context |
| **#p0.id** | Lấy thuộc tính id của đối số thứ nhất | Object không null và truy cập được thuộc tính |
| **#p0.trim().toUpperCase(T(java.util.Locale).ROOT)** | Chuẩn hóa mã trước khi tạo key | Đối số là String không null; phải phù hợp nghiệp vụ |
| **#root.methodName + ':' + #p0** | Thêm tên phương thức vào key | Hữu ích khi nhiều method chung một cache nhưng khác ý nghĩa |
| **#tenant + ':' + #code** | Ghép hai tham số theo tên | Phải có metadata tên tham số và tránh va chạm do delimiter |

Các biến **#p0**, **#a0** và **#root.args[0]** thường đáng tin cậy hơn việc mặc định cho rằng Spring luôn nhìn thấy tên như **#tenant** hoặc **#code**. Tên tham số cần thông tin từ compiler (ví dụ biên dịch với **-parameters**) hoặc cơ chế cung cấp metadata tương thích.

### Ví dụ dùng key để chọn trường thực sự quyết định kết quả

~~~java
// Pseudo service: chỉ minh họa chú thích, chưa chạy độc lập.
@Cacheable(cacheNames = "productNames", key = "#p0")
public String productName(String productId, boolean traceEnabled) {
    // traceEnabled chỉ chi phối ghi log; không thay đổi giá trị trả về.
    return repository.findName(productId);
}
~~~

Vì traceEnabled không ảnh hưởng giá trị trả về, hai lời gọi cùng productId được phép chia sẻ entry dù cờ ghi log khác nhau. Ngược lại, nếu một boolean thật sự thay đổi kết quả nghiệp vụ, **loại nó khỏi key sẽ gây cache hit sai**.

Biểu thức key nên có tính chất: **cùng dữ liệu logic → cùng key; dữ liệu làm thay đổi kết quả → key khác**. Không dùng số ngẫu nhiên hoặc thời gian hiện tại làm key nếu mục tiêu là tái sử dụng kết quả.

### Cú pháp SpEL không phải cú pháp Java

Đây là lỗi phổ biến:

~~~java
// Sai mục đích: Spring sẽ hiểu "sku" là một biểu thức SpEL,
// không tự hiểu nó là biến Java trong method.
@Cacheable(cacheNames = "products", key = "sku")

// Đúng khi muốn lấy tham số đầu:
@Cacheable(cacheNames = "products", key = "#p0")

// Đúng khi chủ ý dùng một khóa hằng là chuỗi "sku":
@Cacheable(cacheNames = "products", key = "'sku'")
~~~

Ba dòng trên là các đoạn annotation **minh họa tách rời**, không đặt liên tiếp lên cùng method. Khóa hằng chỉ phù hợp khi dữ liệu không phụ thuộc tham số; dùng một key hằng cho nhiều đầu vào có thể trả kết quả sai.

Lưu ý thêm: **#result** chưa tồn tại khi @Cacheable cần tính key để **tra cứu trước khi gọi phương thức**. Không thiết kế @Cacheable(key = "...#result...") để định danh lookup. @Cacheable có **unless** để đánh giá điều kiện sau khi thực hiện và có thể xét kết quả; đó là mục đích khác với key.

## 3. Thuộc tính keyGenerator: gọi bean Java để tạo khóa

Trong Spring, **org.springframework.cache.interceptor.KeyGenerator** là một functional interface. Phương thức cần triển khai:

~~~java
Object generate(Object target, java.lang.reflect.Method method, Object... params);
~~~

Đây là khai báo signature rút gọn. Spring đưa cho generator object đích, phương thức đang được cache và tập đối số thực tế. Generator trả về **một object làm khóa**; đó có thể là String chuẩn hóa, record bất biến hoặc giá trị tổng hợp có equals()/hashCode() hợp lệ.

Ví dụ bean:

~~~java
@Bean("skuKeyGenerator")
public KeyGenerator skuKeyGenerator() {
    return (target, method, params) ->
        ((String) params[0]).trim()
            .toUpperCase(java.util.Locale.ROOT);
}
~~~

Đây là đoạn bean trong class @Configuration, sử dụng **org.springframework.cache.interceptor.KeyGenerator** và **org.springframework.context.annotation.Bean**. Ví dụ giả định method có đối số thứ nhất là String khác null; với phương thức có cấu trúc tham số khác, cần kiểm tra hoặc dùng generator riêng.

Sử dụng bean bằng **tên**:

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public Product find(String sku) { ... }
~~~

String **"skuKeyGenerator"** là tên bean được tìm trong ApplicationContext. Nó **không** phải Java method name, **không** phải SpEL, và không phải nội dung key trả về. Muốn đặt tên bằng @Bean, @Component hoặc cấu hình tương đương, tên thực tế phải khớp giá trị của keyGenerator.

### Khi nào nên dùng keyGenerator?

- Nhiều phương thức cùng dùng một quy tắc chuẩn hóa phức tạp, cần quản lý tại một nơi.
- Muốn tạo một **value object bất biến** chứa tenantId, productId, locale, version và đảm bảo quy tắc equality.
- Cần quy ước key nhất quán ở nhiều class, có bộ kiểm thử riêng cho thuật toán.
- Cần phân biệt tên phương thức hoặc namespace theo một chính sách đã thống nhất.

Ưu điểm của keyGenerator là logic Java dễ kiểm thử, tái sử dụng và refactor. Đổi lại, nó tạo thêm bean và có thể gây khó hiểu nếu thuật toán phụ thuộc vào thứ tự/type của params mà không được định nghĩa rõ.

**Không trả null** từ KeyGenerator. Spring Cache yêu cầu key hợp lệ khi thực hiện thao tác. Nếu dùng object key trong cache Java in-memory, object cần có equals()/hashCode() đúng và không đổi trạng thái làm key bị lệch trong thời gian lưu trữ.

## 4. Bảng so sánh key, keyGenerator và cấu hình mặc định

| Tiêu chí | **key** | **keyGenerator** |
| --- | --- | --- |
| Kiểu giá trị trong annotation | Chuỗi **SpEL** | Chuỗi **tên bean KeyGenerator** |
| Cơ chế xử lý | Spring đánh giá expression theo invocation context | Spring lấy bean và gọi generate(target, method, params) |
| Hợp với | Một phương thức cần chọn/biến đổi vài tham số rõ ràng | Thuật toán Java phức tạp hoặc dùng chung |
| Có truy cập method/target? | Có qua các biến trong SpEL context như #root.methodName, #root.target | Có trực tiếp qua target, Method, params |
| Cần định nghĩa thêm bean? | Không, nếu expression chỉ dùng input/API có sẵn | Có, trừ khi bean đã được ứng dụng cấu hình |
| Test chủ yếu | Kiểm tra biểu thức bằng hit/miss theo đầu vào thực | Unit test generator và integration test với cache |
| Khai báo ở method | key = "#p0" | keyGenerator = "myGenerator" |
| Khai báo cả hai trên cùng operation | **Không hợp lệ** | **Không hợp lệ** |

Nếu **không khai báo cả hai**, Spring dùng generator đang có hiệu lực theo cấu hình mặc định. Với cấu hình thường gặp, đó là **SimpleKeyGenerator**: không đối số → SimpleKey.EMPTY; một đối số không null và không phải array → đối số đó; nhiều đối số → SimpleKey chứa các đối số. Tên cache và tên method không tự động được thêm vào khóa mặc định.

**Điểm quan trọng:** Không có nguyên tắc "ưu tiên key trước keyGenerator" khi **cả hai đều được đặt trực tiếp trên cùng một operation**. Cấu hình này là **sai**, Spring báo lỗi; đừng trông chờ một thuộc tính được im lặng bỏ qua.

## 5. Lỗi khi khai báo cả key và keyGenerator

Ví dụ **cố ý sai**:

~~~java
// SAI: ví dụ để nhận diện cấu hình lỗi, không thêm vào project chạy được.
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    keyGenerator = "skuKeyGenerator"
)
public String find(String sku) {
    return "value";
}
~~~

Vấn đề: cùng một cache operation lại đưa ra **hai cách tính khóa**. Spring không thể coi đó là lựa chọn hợp lệ. Theo tài liệu Spring Framework, **key và keyGenerator là mutually exclusive**, operation thiết lập cả hai sẽ phát sinh exception trong quá trình xử lý cấu hình/operation. Thời điểm chính xác lỗi lộ ra có thể phụ thuộc cơ chế khởi tạo bean và thời điểm Spring phân tích metadata; không nên gắn cứng một tên exception hoặc thông điệp cho mọi phiên bản.

Cách sửa 1 — chỉ sử dụng SpEL:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return "value";
}
~~~

Cách sửa 2 — chỉ sử dụng bean:

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public String find(String sku) {
    return "value";
}
~~~

Cách sửa 3 — nếu không có logic đặc biệt, bỏ cả hai để dùng key mặc định:

~~~java
@Cacheable(cacheNames = "products")
public String find(String sku) {
    return "value";
}
~~~

Ba cách sửa là **ba phương án độc lập**, không đặt cả ba annotation lên cùng method. Chọn một phương án phù hợp với danh tính nghiệp vụ.

### Nhìn kỹ trường hợp chuỗi rỗng

Trong annotation, **key** và **keyGenerator** có giá trị mặc định là chuỗi rỗng. Điều kiện xung đột cần hiểu theo **thuộc tính có cấu hình khác rỗng**, không phải hai tên thuộc tính cùng tồn tại trong định nghĩa annotation. Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", keyGenerator = "")
public String find(String sku) { return "value"; }
~~~

Đoạn trên là minh họa: keyGenerator rỗng **không chỉ định một bean cụ thể**; key SpEL được chọn. Dù không nhất thiết gây xung đột, việc khai báo tường minh keyGenerator = "" không mang giá trị học tập trong code thực tế nên nên bỏ đi.

### Lỗi thứ hai: bean không tồn tại hoặc sai kiểu

~~~java
@Cacheable(cacheNames = "products", keyGenerator = "missingGenerator")
public String find(String sku) { return "value"; }
~~~

Nếu không có bean tên missingGenerator với kiểu KeyGenerator phù hợp, Spring không thể resolve nó khi operation được thực hiện. Đây là **lỗi lựa chọn bean**, khác với lỗi khai báo đồng thời key và keyGenerator.

## 6. Ngoại lệ quan trọng: @CacheConfig mặc định và method override

@CacheConfig đặt một số thông số **mặc định ở cấp class**, bao gồm cacheNames, keyGenerator, cacheManager, cacheResolver. Một customization ở **cấp method** có độ ưu tiên cao hơn default cấp class. Điều này không đồng nghĩa với việc method đã khai báo hai chiến lược xung đột.

Ví dụ **hợp lệ**:

~~~java
@CacheConfig(keyGenerator = "skuKeyGenerator")
public class ProductReader {

    @Cacheable(cacheNames = "products", key = "#p0")
    public String findExact(String sku) {
        return findFromSource(sku);
    }

    @Cacheable(cacheNames = "productsByNormalizedSku")
    public String findNormalized(String sku) {
        return findFromSource(sku);
    }
}
~~~

Đây là class minh họa, cần các import và định nghĩa findFromSource trong dự án thực. Hai method chọn cache name khác nhau để tránh trộn loại dữ liệu và giúp thấy rõ chiến lược khóa:

- **findExact** có key = "#p0" cấp method. Spring ưu tiên **SpEL key** này và **không áp dụng default keyGenerator** cấp @CacheConfig cho operation đó.
- **findNormalized** không đặt key hoặc keyGenerator riêng. Nó có thể kế thừa **skuKeyGenerator** của @CacheConfig và dùng logic chuẩn hóa.
- @CacheConfig **tự nó không bật caching** và cũng không tự tạo cache entry. Vẫn cần @Cacheable/@CachePut/@CacheEvict ở operation thích hợp và hạ tầng kích hoạt như @EnableCaching.

Vì vậy, cần phân biệt:

| Khai báo | Hợp lệ? | Chiến lược dùng |
| --- | --- | --- |
| @Cacheable(key = "#p0") | Có | SpEL |
| @Cacheable(keyGenerator = "skuKeyGenerator") | Có nếu bean tồn tại, phù hợp | Bean KeyGenerator |
| @Cacheable(key = "#p0", keyGenerator = "skuKeyGenerator") | **Không** | Phát sinh lỗi cấu hình operation |
| @CacheConfig(keyGenerator = "skuKeyGenerator") + method @Cacheable(key = "#p0") | **Có** | SpEL ở method ghi đè default của class |
| @CacheConfig(keyGenerator = "skuKeyGenerator") + method @Cacheable | Có nếu hạ tầng đầy đủ | Kế thừa KeyGenerator cấp class |
| Không có custom strategy | Có | KeyGenerator mặc định |

Cũng có thể đặt generator mặc định cho toàn ứng dụng qua cơ chế cấu hình Spring (chẳng hạn CachingConfigurer) rồi ghi đè ở class hoặc operation. Quy tắc tổng quát là **global default → @CacheConfig class → annotation operation**, nhưng **không dùng quy tắc ưu tiên này để hợp thức hóa hai thuộc tính được đặt đồng thời trên cùng một annotation operation**.

## 7. Ví dụ Java 17+ chạy được: so sánh ba chiến lược key

Ví dụ sau dùng **Spring Framework 6.1.x, Maven, Java 17+** và ConcurrentMapCacheManager. Nó kiểm chứng ba cách:
1. SpEL tự chuẩn hóa SKU;
2. KeyGenerator Java tự chuẩn hóa SKU;
3. KeyGenerator mặc định giữ nguyên String argument, nên hai chuỗi khác nhau sẽ là hai entry.

Cấu trúc thư mục:

~~~text
spring-cache-key-choice/
├── pom.xml
└── src/main/java/demo/CacheKeyChoiceDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-key-choice</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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

**src/main/java/demo/CacheKeyChoiceDemo.java**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheKeyChoiceDemo {

    public static class CatalogService {
        private final AtomicInteger spelLoads = new AtomicInteger();
        private final AtomicInteger generatorLoads = new AtomicInteger();
        private final AtomicInteger defaultLoads = new AtomicInteger();

        @Cacheable(
            cacheNames = "bySpel",
            key = "#p0.trim().toUpperCase(T(java.util.Locale).ROOT)"
        )
        public String bySpel(String sku) {
            return "spel-load-" + spelLoads.incrementAndGet();
        }

        @Cacheable(
            cacheNames = "byGenerator",
            keyGenerator = "normalizingKeyGenerator"
        )
        public String byGenerator(String sku) {
            return "generator-load-" + generatorLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "byDefault")
        public String byDefault(String sku) {
            return "default-load-" + defaultLoads.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "bySpel", "byGenerator", "byDefault"
            );
        }

        @Bean("normalizingKeyGenerator")
        public KeyGenerator normalizingKeyGenerator() {
            return (target, method, params) ->
                ((String) params[0]).trim().toUpperCase(Locale.ROOT);
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = ctx.getBean(CatalogService.class);

            System.out.println(service.bySpel(" sku-7 "));
            System.out.println(service.bySpel("SKU-7"));

            System.out.println(service.byGenerator(" sku-7 "));
            System.out.println(service.byGenerator("SKU-7"));

            System.out.println(service.byDefault(" sku-7 "));
            System.out.println(service.byDefault("SKU-7"));
        }
    }
}
~~~

Chạy bằng Maven tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyChoiceDemo
~~~

**Stdout do chính Java in ra** (không tính log Maven nếu môi trường có in thêm):

~~~text
spel-load-1
spel-load-1
generator-load-1
generator-load-1
default-load-1
default-load-2
~~~

Giải thích kết quả:

- **bySpel(" sku-7 ")** tạo key "SKU-7" bằng SpEL, method thật chạy lần 1. **bySpel("SKU-7")** tạo cùng key và hit, nên vẫn trả "spel-load-1".
- **byGenerator(...)** cũng tạo key "SKU-7" nhưng thuật toán được thực hiện bởi bean KeyGenerator; lời gọi thứ hai hit cache byGenerator.
- **byDefault(...)** giữ nguyên đối số String của từng lời gọi làm key. Hai chuỗi " sku-7 " và "SKU-7" không equals(), nên đều miss và đếm đến 2.
- Ba method sử dụng **ba cacheName khác nhau** để tránh va chạm dữ liệu, giúp quan sát độc lập chiến lược khóa.
- @EnableCaching và lấy CatalogService từ ApplicationContext làm cho lời gọi đi qua Spring proxy. Nếu tự tạo new CatalogService() ngoài Spring, không thể trông chờ @Cacheable hoạt động.

Nếu đưa ví dụ khai báo **cả key và keyGenerator cùng trên method** vào ứng dụng này, cấu hình sẽ trở nên không hợp lệ. Không thêm lỗi cố ý ấy vào file demo chạy được; dùng ví dụ riêng ở mục 5 để nhận diện và sửa.

## 8. Tạo key đúng khi có nhiều tham số

Lựa chọn giữa key và keyGenerator phải dựa vào **danh tính logic của kết quả**, không phải thói quen dùng annotation nào. Ví dụ giá sản phẩm phụ thuộc productId và currency:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0 + ':' + #p1")
public String price(String productId, String currency) {
    return lookupPrice(productId, currency);
}
~~~

Đây là đoạn minh họa, không phải chương trình đầy đủ. Cách ghép String bằng dấu hai chấm có thể bị **đụng khóa** nếu thành phần chứa delimiter:

~~~text
productId = "ab:c", currency = "d"   -> "ab:c:d"
productId = "ab",   currency = "c:d" -> "ab:c:d"
~~~

Với biểu thức đơn giản, có thể chọn một đối tượng key có cấu trúc ổn định, hoặc dùng generator trả về record bất biến:

~~~java
record PriceKey(String productId, String currency) {}

@Bean("priceKeyGenerator")
KeyGenerator priceKeyGenerator() {
    return (target, method, params) ->
        new PriceKey((String) params[0], (String) params[1]);
}
~~~

Đây là ví dụ **đặt trong class cấu hình**. Phải khai báo bean đúng tên, đảm bảo method có hai String theo thứ tự đã quy định, và kiểm tra null/chuẩn hóa nếu nghiệp vụ yêu cầu. Record trên Java 17 có equals() và hashCode() dựa trên component; nó phù hợp làm khóa cho cache Java in-memory khi component bất biến.

Nếu dùng cache phân tán như Redis, object key còn phải được **serialize** thành bytes. Đừng giả định một record có equals/hashCode đúng đồng nghĩa mọi instance tự tạo đúng cùng bytes key; serializer và quy ước namespace phải nhất quán.

### Đồng bộ khóa khi cập nhật hoặc xóa cache

Một lỗi tinh vi là dùng keyGenerator chuẩn hóa khi @Cacheable nhưng dùng key thô ở @CacheEvict:

~~~java
// Hai annotation minh họa thuộc hai operation khác nhau.
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
public String find(String sku) { return load(sku); }

@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidate(String sku) { }
~~~

Nếu find(" sku-7 ") lưu bằng key "SKU-7" nhưng invalidate(" sku-7 ") xóa key có khoảng trắng, entry gốc có thể còn nguyên. Đây là **lỗi không thống nhất danh tính key**, dù mỗi annotation **đều hợp lệ riêng**.

Hãy thống nhất một trong hai phương án: dùng cùng generator ở cả operation, hoặc dùng biểu thức key cho thao tác xóa tạo chính xác cùng key đã lưu. @CachePut cũng cần cùng quy ước khi cập nhật entry. Nếu tên cache khác nhau hoặc key được tính với context khác, cần thiết kế key rõ ràng cho từng operation.

## 9. Quy trình chọn chiến lược và kiểm thử

**Chọn key SpEL** khi:
- Bạn chỉ cần chọn 1–2 tham số hoặc một thuộc tính, ví dụ #p0, #p0.id.
- Cách chuẩn hóa ngắn và dễ đọc, không gây lặp ở nhiều phương thức.
- Người bảo trì có thể hiểu toàn bộ khóa từ annotation trên method.

**Chọn keyGenerator** khi:
- Logic cần nhiều bước, nhiều nhánh kiểm tra hoặc quy tắc chuẩn hóa dùng chung.
- Key là object có cấu trúc, cần kiểm thử equals/hashCode, định dạng và vòng đời.
- Các method phải tuân thủ cùng một quy ước key và có thể triển khai thành thư viện nội bộ.

**Giữ default** khi các đối số đã mang danh tính thích hợp và equals/hashCode ổn định. Đừng thêm custom code không cần thiết.

Bài kiểm tra tối thiểu cho mỗi phương thức cache:

1. **Cùng input logic:** gọi hai lần bằng input tương đương; method thật chỉ chạy một lần nếu cache có hit.
2. **Input làm thay đổi kết quả:** thay tenant/currency/locale hoặc tham số liên quan; phải tạo entry khác.
3. **Trường được bỏ qua:** xác minh rõ rằng trường ấy thật sự không ảnh hưởng dữ liệu trả về.
4. **Eviction và put:** dùng cùng cache name, quy tắc key và chuẩn hóa giữa read/write/delete.
5. **Validation cấu hình:** tìm các @Cacheable/@CachePut/@CacheEvict đặt đồng thời key và keyGenerator; sửa để chỉ còn một nguồn tạo key trên từng operation.
6. **Bean resolution:** nếu dùng keyGenerator, xác minh bean tên tương ứng tồn tại, là KeyGenerator, và sinh key không null.
7. **AOP proxy:** kiểm thử qua bean trong Spring container, không chỉ gọi object Java tự tạo.
8. **Cache provider:** kiểm tra cách provider đối chiếu key và khả năng serialize khi triển khai cache từ xa.

### Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Exception khi Spring xử lý cache operation | Cùng method đặt key và keyGenerator khác rỗng | Chọn đúng **một** chiến lược ở operation |
| Không tìm được generator đã khai báo | Nhầm tên method/tên class với tên bean, bean chưa đăng ký | Kiểm tra tên bean, package scan, @Bean và kiểu KeyGenerator |
| Cache hit sai giữa hai tenant | Biểu thức chỉ chọn productId, bỏ tenantId | Mở rộng định danh key và kiểm thử phân vùng dữ liệu |
| Hai phương thức dùng chung cache nhưng trả sai loại dữ liệu | Trùng cacheName và key dù kết quả khác nghiệp vụ | Phân vùng tên cache hoặc thêm namespace key có kiểm soát |
| Xóa cache không có hiệu quả | @Cacheable và @CacheEvict tính key khác nhau | Đồng bộ chiến lược key ở các operation |
| key dùng tên tham số bị lỗi SpEL | Thiếu metadata tên tham số | Dùng #p0/#a0 hoặc bật biên dịch với -parameters phù hợp |
| KeyGenerator chạy nhưng không hit | Trả key không ổn định, object mutable hoặc equals/hashCode sai | Dùng key bất biến và kiểm thử equality |
| Tưởng @CacheConfig và key method là lỗi trùng khai báo | Nhầm default cấp class với cấu hình operation | Method-level key override keyGenerator mặc định cấp class |
| key = "'fixed'" trả sai dữ liệu | Key hằng dùng cho các tham số thực sự khác kết quả | Dùng key phụ thuộc các tham số quyết định kết quả |

## 10. Tự kiểm tra

**Câu 1.** Hai annotation dưới đây có tương đương không?

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
@Cacheable(cacheNames = "products", keyGenerator = "skuKeyGenerator")
~~~

**Đáp:** Không nhất thiết. Cái thứ nhất dùng đối số thứ nhất trực tiếp. Cái thứ hai gọi bean skuKeyGenerator, có thể chuẩn hóa hoặc biến đổi key. Hai dòng minh họa hai lựa chọn độc lập, không đặt chồng lên một method.

**Câu 2.** Trên một method có @Cacheable(key = "#p0", keyGenerator = "skuKeyGenerator"). Spring tự ưu tiên key?

**Đáp:** Không. Đây là cấu hình **không hợp lệ** vì hai thuộc tính loại trừ nhau trên cùng operation. Phải loại bỏ một thuộc tính.

**Câu 3.** Class đặt @CacheConfig(keyGenerator = "skuKeyGenerator"), còn method đặt @Cacheable(cacheNames = "products", key = "#p0"). Đây có phải lỗi đồng thời key và keyGenerator?

**Đáp:** Không. key ở cấp operation ghi đè default keyGenerator ở cấp class. Method dùng SpEL.

**Câu 4.** Vì sao @Cacheable(key = "#result.id") không phù hợp để tra cứu?

**Đáp:** Cần tạo key để kiểm tra cache **trước** khi thực hiện method; khi đó kết quả chưa có. Đừng phụ thuộc vào #result trong lookup key của @Cacheable.

**Câu 5.** Khi một project có nhiều operation cần cùng cách chuẩn hóa SKU, nên chọn gì?

**Đáp:** Thường nên dùng một KeyGenerator có tên rõ ràng, kiểm thử riêng; bảo đảm @Cacheable/@CachePut/@CacheEvict đều tính cùng key khi làm việc với cùng entry.

## Kết luận

- **key** là một biểu thức SpEL tạo khóa tại operation.
- **keyGenerator** là tên bean Java triển khai chiến lược tạo khóa.
- **Không khai báo đồng thời cả hai thuộc tính khác rỗng trên cùng một cache operation**: Spring phát sinh exception, không tự chọn một bên.
- **@CacheConfig(keyGenerator=...) chỉ là default cấp class**; method có **key** riêng có thể ghi đè default ấy một cách hợp lệ.
- Tính đúng của cache phụ thuộc vào **key thực tế được sinh ra**, sự nhất quán giữa các operation và cách provider lưu/truy xuất key.

### Tài liệu chính thức

- Spring Framework – Annotation-based caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Custom key generation và chú thích mutually exclusive: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – SpEL: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Framework – KeyGenerator interface: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html
- Spring Framework – @CacheConfig: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html

# Chế độ proxy và lời gọi đi qua bean Spring trong Spring Cache

## Mục tiêu

Trong Spring Framework Cache Abstraction, viết **@Cacheable**, **@CachePut** hay **@CacheEvict** chưa đủ để phương thức tự có caching. Ở chế độ mặc định, Spring sử dụng **AOP proxy**: hành vi cache chỉ được áp dụng khi lời gọi **đi qua đối tượng proxy do Spring quản lý**. Vì vậy, hai câu lệnh gọi cùng một method có thể cho kết quả khác nhau chỉ vì đường đi của lời gọi khác nhau.

Sau bài học, bạn có thể:
1. Giải thích **proxy mode** của @EnableCaching và chuỗi caller → proxy → cache interceptor → target method.
2. Phân biệt **bean Spring được lấy từ ApplicationContext** với object tự tạo bằng new, và phân biệt **gọi từ bean khác** với **self-invocation** qua this.
3. Hiểu khi nào Spring dùng **JDK dynamic proxy** hoặc **class-based proxy**, tác động của **proxyTargetClass** và giới hạn với final/private/static method.
4. Nhận diện trường hợp annotation không có tác dụng do proxy chưa được kích hoạt, lời gọi sai đường, quá trình khởi tạo bean hoặc scope ApplicationContext.
5. Chạy ví dụ Java 17 + Spring Framework minh họa cache hit, cache miss và **self-invocation không được intercept**; chọn cách refactor an toàn.

Ngữ cảnh: **Spring Framework 6.2.x**, cấu hình Java annotation-based caching; ví dụ dùng **ConcurrentMapCacheManager** và không cần Spring Boot. Các nguyên tắc proxy vẫn áp dụng khi dùng Caffeine, Redis hoặc provider khác, nhưng chúng **không** thay thế cấu hình kết nối, TTL hoặc quy tắc key riêng của provider.

## 1. Spring Cache dùng proxy để làm gì?

Spring Cache là một dạng **cross-cutting concern**: việc kiểm tra, cập nhật hoặc xóa cache được thêm quanh lời gọi phương thức nghiệp vụ mà không cần viết thao tác Cache.get/put/evict ở mọi method.

Khi bật annotation caching với **@EnableCaching**, Spring tạo hạ tầng nhận diện các cache operation và gắn **cache interceptor** vào những bean phù hợp. Trong proxy mode, Spring có thể trao cho các caller một đối tượng proxy đứng trước target.

~~~text
Caller (Controller / Service / Job / Test)
       |
       | gọi qua tham chiếu bean đã nhận từ Spring
       v
Spring AOP proxy
       |
       v
CacheInterceptor
       |
       +-- @Cacheable: tạo key -> xem cache
       |      HIT  -> trả kết quả, không gọi target method
       |      MISS -> gọi target -> đưa result vào cache
       |
       +-- @CachePut: gọi target -> put result (theo điều kiện)
       |
       +-- @CacheEvict: gọi target -> evict theo thời điểm cấu hình
       |
       v
Target object chứa logic nghiệp vụ
~~~

Sơ đồ mô tả hành vi đồng bộ điển hình. Annotation cụ thể có thể dùng condition, unless, key/keyGenerator, cacheResolver và các tùy chọn khác; thứ tự các bước chi tiết còn phụ thuộc loại cache operation.

**Proxy không phải cache.** Proxy là cổng chặn lời gọi; **CacheManager/Cache** mới lưu entry. Proxy thực thi phần logic cache nhờ interceptor và chuyển lời gọi xuống target khi cần.

Hai trường hợp thường bị nhầm:
- **@Cacheable** có cache hit → có thể không gọi target method.
- **@CachePut** không dùng cache hit để bỏ qua target method; phương thức vẫn thực thi và Spring có thể put result.
- **@CacheEvict** có thể xóa sau invocation (mặc định) hoặc trước invocation nếu beforeInvocation=true.

Điểm chung của cả ba: nếu lời gọi hoàn toàn **không đi qua cơ chế interception**, các annotation này không tự thực hiện chức năng cache.

## 2. @EnableCaching mặc định chọn AdviceMode.PROXY

Annotation **org.springframework.cache.annotation.EnableCaching** có thuộc tính **mode**. Giá trị mặc định là **AdviceMode.PROXY**.

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfig {
    // Các @Bean cho CacheManager/KeyGenerator nếu cần.
}
~~~

Đây là đoạn cấu hình minh họa; một project đầy đủ cần CacheManager hoặc hạ tầng có thể resolve cache. Ví dụ runnable ở phần sau có bean CacheManager rõ ràng.

Có thể viết tường minh chế độ mặc định:

~~~java
import org.springframework.context.annotation.AdviceMode;

@EnableCaching(mode = AdviceMode.PROXY)
~~~

Dòng thứ hai là **annotation minh họa** đặt lên một class @Configuration; chỉ dùng nó trong ngữ cảnh class cấu hình phù hợp.

**Ý nghĩa thực tế của PROXY:**
1. Spring tìm các bean được quản lý và các phương thức cache-annotated tương ứng.
2. Một proxy được tạo khi bean đủ điều kiện; caller thường nhận **bean reference đã được proxy** từ container.
3. Cache advice chỉ kích hoạt trên lời gọi **đi từ ngoài vào qua proxy**.
4. Lời gọi bên trong target bằng **this.method()** không đi qua proxy đó.
5. Việc đặt annotation lên method **không biến mọi lời gọi Java** thành interception: Java không tự hiểu annotation caching.

Với Spring Boot, auto-configuration có thể hỗ trợ kích hoạt/cache infrastructure, nhưng bạn vẫn cần xác minh caching đã được bật trong ứng dụng cụ thể. Dùng Spring Framework thuần, cách rõ ràng là @EnableCaching và bean CacheManager.

### Tại sao cache không hoạt động ngay khi viết annotation?

Annotation chỉ là metadata. Việc có thực thi theo annotation hay không phụ thuộc:
- **Có hạ tầng caching annotation đang hoạt động không?**
- **Method có nằm trên một Spring bean được quản lý không?**
- **Đường gọi có qua proxy không?**
- **Method có thể được proxy/intercept trong cấu hình hiện tại không?**
- **Cache name, key và cache manager có hợp lệ không?**

Chỉ khi các điều kiện liên quan thỏa mãn, cache interceptor mới có cơ hội xử lý invocation.

## 3. Đường gọi đúng: lấy bean từ Spring và gọi từ bên ngoài

Cách dùng thông thường:

~~~java
// Minh họa trong một Spring-managed controller/facade.
public final class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service; // Spring inject bean, không tự new.
    }

    public String get(String id) {
        return service.load(id); // Lời gọi từ đối tượng khác qua bean.
    }
}
~~~

Đây là ví dụ ý tưởng; cần đăng ký ProductController và ProductService làm bean, cũng như khai báo ProductService tương ứng. Trong project thật, bạn có thể dùng constructor injection với @Service/@Component hoặc @Bean.

Cùng nội dung nhưng gọi **trực tiếp một object tự tạo**:

~~~java
// KHÔNG được Spring quản lý:
ProductService service = new ProductService();
service.load("P-01");
service.load("P-01");
~~~

Hai lời gọi trên là Java thông thường, **không tự đi qua Spring AOP proxy**. Dù method load có @Cacheable, annotation không được Spring áp dụng cho instance này. Trên các lần gọi, logic thực thi theo code Java gốc; không có cache interceptor của Spring can thiệp.

**Phân biệt ba đối tượng:**
- **Bean definition**: metadata để Spring tạo/quản lý object.
- **Target**: instance thực thi logic nghiệp vụ.
- **Proxy bean reference**: object caller nhận từ Spring có thể bao bọc target và thực hiện advice.

Bạn không nên dựa vào giả định **target == proxy**. Với proxy dựa trên subclass hay interface, class/type hiển thị có thể khác class gốc. Quan trọng là caller nhận và sử dụng đúng bean reference do Spring cung cấp.

## 4. Self-invocation: lỗi kinh điển của proxy mode

Self-invocation là việc một method trong chính object target gọi một method khác **trên cùng object**, thường qua **this** hoặc gọi ngầm không ghi this.

~~~java
public class ProductService {

    @Cacheable(cacheNames = "products")
    public String load(String id) {
        return expensiveQuery(id);
    }

    public String loadTwice(String id) {
        String first = this.load(id);
        String second = load(id);   // Tương đương this.load(id).
        return first + "|" + second;
    }
}
~~~

Đây là đoạn minh họa, chưa chạy độc lập. Khi bên ngoài gọi **proxy.load("P-01")**, Spring có cơ hội intercept @Cacheable. Nhưng nếu bên ngoài gọi **proxy.loadTwice("P-01")**, lời gọi đầu tiên chuyển xuống **target.loadTwice**; từ đó **this.load(...)** gọi trực tiếp target method, không quay trở lại proxy. Hai lần load trong loadTwice đều không được cache interceptor chặn theo proxy mode mặc định.

~~~text
CÁCH 1: caller -> proxy.load(id)
                     |
                     +--> CacheInterceptor --> Cache HIT / MISS
                                                  |
                                          (MISS) target.load(id)

CÁCH 2: caller -> proxy.loadTwice(id)
                     |
                     v
                 target.loadTwice(id)
                     |
                     +--> this.load(id) ---------> target.load(id)
                     +--> this.load(id) ---------> target.load(id)
                         (không qua interceptor)
~~~

**Quan trọng:** Self-invocation bypass proxy **ngay cả khi method được gọi là public và có @Cacheable**. Đổi proxyTargetClass từ false sang true **không tự sửa** vấn đề this-call; cả interface proxy và class proxy vẫn có proxy boundary.

Điều này không chỉ ảnh hưởng @Cacheable. Self-invocation đối với @CachePut hoặc @CacheEvict cũng bỏ qua hành vi put/evict nếu các annotation đó chỉ được áp dụng qua Spring AOP proxy.

### Dấu hiệu nhận biết trong thực tế

Giả sử bạn thấy @Cacheable dùng từ Controller cho hiệu quả, nhưng trong cùng Service gọi lại @Cacheable method thì truy vấn database vẫn chạy mỗi lần. Đây thường là **đường gọi không qua proxy** chứ không phải lỗi TTL. Cần theo dõi call path, thay vì tăng TTL hoặc thay provider trước.

## 5. JDK dynamic proxy và class-based proxy

Spring AOP có hai họ proxy chủ yếu trong Java:

| Tiêu chí | **JDK dynamic proxy** | **Class-based proxy (CGLIB)** |
| --- | --- | --- |
| Cơ chế | Proxy triển khai các interface được expose | Proxy là subclass của target class |
| Thường dùng khi | Bean có interface phù hợp và không buộc class proxy | Bean không có interface phù hợp hoặc cấu hình ép class proxy |
| Kiểu bean nên inject | Interface | Có thể dùng concrete class nếu các giới hạn proxy cho phép |
| Method được proxy | Những method được expose qua interface/proxy | Những instance method có thể override/advice |
| Giới hạn nổi bật | Không expose tùy tiện mọi method riêng chỉ có ở concrete class | Không proxy được final class; final method không được override để advice |
| Self-invocation qua this | **Không được intercept** | **Không được intercept** |
| Phụ thuộc vào cache provider? | Không | Không |

Khi chọn **@EnableCaching(proxyTargetClass = false)** (giá trị mặc định), Spring Framework AOP thông thường ưu tiên JDK proxy khi target có interface và dùng class-based proxy khi không có interface để proxy. Vì vậy, **false không đảm bảo luôn có JDK proxy** nếu class không khai báo interface.

~~~java
@EnableCaching(proxyTargetClass = true)
~~~

Dòng trên là **annotation minh họa** trên @Configuration. Ở chế độ PROXY, true yêu cầu class-based proxies. Nếu mode=ASPECTJ, thuộc tính proxyTargetClass không còn vai trò lựa chọn proxy.

### Interface proxy và kiểu injection

Ví dụ interface:

~~~java
public interface CatalogApi {
    String find(String sku);
}

public class CatalogService implements CatalogApi {
    @Override
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        return lookup(sku);
    }
}
~~~

Đây là ví dụ tách rời; lookup và các import cần được bổ sung. Với JDK proxy, caller nên inject **CatalogApi**, không mặc định yêu cầu CatalogService concrete:

~~~java
// Constructor minh họa:
public CatalogController(CatalogApi api) {
    this.api = api;
}
~~~

Trong trường hợp bean thực sự là JDK proxy, cố ép kiểu bean thành CatalogService có thể gây lỗi vì đối tượng proxy **chỉ implements interface**. Với class-based proxy, subclass của CatalogService có thể assign được sang CatalogService.

Đối với cache annotation, đặt trên **concrete class/method** thường rõ ràng và dễ kiểm soát hơn đặt trên interface, đặc biệt nếu dự án có thể chuyển sang AspectJ weaving. Tài liệu Spring cảnh báo annotation trên interface không được kế thừa theo cơ chế Java và có giới hạn đối với weaving-based mode.

### Public, private, final, static

- **Public instance method** trên Spring bean là lựa chọn khuyến nghị cho @Cacheable, @CachePut và @CacheEvict trong proxy mode; an toàn nhất khi cần hỗ trợ cả JDK và class-based proxy.
- **Private method** không thể là điểm interception thông thường qua Spring AOP proxy; annotation trên private method thường không có tác dụng.
- **Final instance method** không thể bị class-based proxy override để thêm advice; không nên kỳ vọng @Cacheable hoạt động ở method này với class proxy.
- **Final class** không thể làm target cho CGLIB subclass proxy; nếu dùng class-based proxy bắt buộc sẽ gặp giới hạn của Java inheritance.
- **Static method** không phải một instance invocation đi qua AOP bean proxy; không dùng @Cacheable trên static method rồi kỳ vọng Spring Cache intercept.
- **Protected/package-private method** có thể có khác biệt theo cơ chế proxy, phiên bản Spring và hạ tầng AOP; với annotation caching hãy **ưu tiên public method** như hướng dẫn chính thức để tránh phụ thuộc triển khai.
- **Constructor** và những lời gọi trong giai đoạn target chưa được proxy đầy đủ cũng không phải nơi an toàn để dựa vào annotation caching.

**Đừng biến mọi lỗi cache thành vấn đề public/private.** Trước tiên xác minh có proxy và lời gọi thực sự qua proxy hay chưa; sau đó mới xem visibility và proxy type.

## 6. Ví dụ hoàn chỉnh Java 17 + Spring Framework: external, self, cross-bean và new

Đây là demo **chạy được trong project Maven** bằng Java 17. Ta chỉ dùng một cache trong bộ nhớ để dễ kiểm chứng số lần target method chạy, không dùng database hay TTL. Ví dụ cho thấy:

1. Gọi **CatalogService.fetch** từ bean lấy trong ApplicationContext → cache hit ở lần thứ hai.
2. Gọi **CatalogService.internalFetch** rồi nó gọi **this.fetch** → hai lần đều chạy method thật, không ghi entry cho B.
3. Một **OrderingService khác** gọi CatalogService bean đã inject → đi qua proxy, hit ở lần gọi thứ hai.
4. Tạo **new CatalogService()** ngoài Spring → không có proxy/interceptor.

### 6.1. Cấu trúc dự án

~~~text
spring-cache-proxy-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCacheProxyDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-proxy-demo</artifactId>
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

Spring-context kéo theo các module Spring cần thiết cho annotation caching và Spring AOP trong demo này. Việc thực thi dùng một JVM, không yêu cầu Redis hoặc Caffeine.

### 6.3. src/main/java/demo/SpringCacheProxyDemo.java

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.atomic.AtomicInteger;

public class SpringCacheProxyDemo {

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "catalog")
        public String fetch(String sku) {
            return "load-" + loads.incrementAndGet();
        }

        public String internalFetch(String sku) {
            return this.fetch(sku); // Không quay lại Spring proxy.
        }

        public int targetCalls() {
            return loads.get();
        }
    }

    public static class OrderingService {
        private final CatalogService catalog;

        public OrderingService(CatalogService catalog) {
            this.catalog = catalog; // Bean do Spring inject.
        }

        public String fetchThroughOtherBean(String sku) {
            return catalog.fetch(sku); // Đi qua proxy.
        }
    }

    @Configuration
    @EnableCaching
    public static class AppConfig {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public CatalogService catalogService() {
            return new CatalogService();
        }

        @Bean
        public OrderingService orderingService(CatalogService catalog) {
            return new OrderingService(catalog);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogService catalog = context.getBean(CatalogService.class);
            OrderingService ordering =
                context.getBean(OrderingService.class);

            System.out.println("isProxy="
                + AopUtils.isAopProxy(catalog));

            System.out.println("externalA1=" + catalog.fetch("A"));
            System.out.println("externalA2=" + catalog.fetch("A"));

            System.out.println("selfB1=" + catalog.internalFetch("B"));
            System.out.println("selfB2=" + catalog.internalFetch("B"));

            System.out.println("otherBeanB1="
                + ordering.fetchThroughOtherBean("B"));
            System.out.println("otherBeanB2="
                + ordering.fetchThroughOtherBean("B"));

            System.out.println("targetCalls=" + catalog.targetCalls());

            CatalogService plain = new CatalogService();
            System.out.println("newC1=" + plain.fetch("C"));
            System.out.println("newC2=" + plain.fetch("C"));
        }
    }
}
~~~

Chương trình định nghĩa hai service được container quản lý. CatalogService **không implement interface**, nên cấu hình Spring AOP mặc định vẫn có thể tạo **class-based proxy** cho nó. Các phương thức có thể được override, đều public và instance-based.

### 6.4. Biên dịch và chạy

Trong thư mục **spring-cache-proxy-demo**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringCacheProxyDemo
~~~

Stdout do những lệnh **System.out.println** trong ví dụ in ra, không tính log riêng Maven hoặc thư viện:

~~~text
isProxy=true
externalA1=load-1
externalA2=load-1
selfB1=load-2
selfB2=load-3
otherBeanB1=load-4
otherBeanB2=load-4
targetCalls=4
newC1=load-1
newC2=load-2
~~~

### 6.5. Vì sao output như vậy?

| Lời gọi | Đường đi | Trạng thái cache | Phương thức fetch thật chạy? |
| --- | --- | --- | --- |
| catalog.fetch("A") lần 1 | External qua proxy | MISS, lưu key A | Có, loads=1 |
| catalog.fetch("A") lần 2 | External qua proxy | HIT A | Không |
| catalog.internalFetch("B") lần 1 | External vào internalFetch, rồi this.fetch | **Bypass interceptor** cho fetch | Có, loads=2 |
| catalog.internalFetch("B") lần 2 | Tương tự | **Bypass interceptor** cho fetch | Có, loads=3 |
| ordering.fetchThroughOtherBean("B") lần 1 | OrderingService → injected catalog proxy | MISS B, lưu key B | Có, loads=4 |
| ordering.fetchThroughOtherBean("B") lần 2 | Tương tự | HIT B | Không |
| plain.fetch("C") lần 1 | new CatalogService ngoài Spring | Không có proxy | Có, loads=1 riêng |
| plain.fetch("C") lần 2 | Tương tự | Không có proxy | Có, loads=2 riêng |

**isProxy=true** chứng minh biến catalog lấy từ context là AOP proxy. Việc CatalogService không có interface không ngăn Spring tạo subclass proxy trong cấu hình thường dùng. Mặt khác, **CatalogService plain** được new riêng có bộ đếm loads độc lập và không có cache interceptor.

Chi tiết quan trọng: lời gọi **catalog.internalFetch** cũng đi qua proxy ở ranh giới đầu. Nhưng vì **internalFetch không có cache operation**, proxy chỉ chuyển xuống target. Bên trong target, **this.fetch** không đi lại qua proxy; vì thế @Cacheable của fetch không được áp dụng. Việc một method khởi đầu từ bean proxy **không có nghĩa mọi lời gọi lồng nhau tự được intercept**.

### 6.6. Thử một biến thể để tự hiểu cơ chế

Nếu đổi thứ tự, gọi **ordering.fetchThroughOtherBean("B")** trước để cache B, rồi mới gọi **catalog.internalFetch("B")**, các lời gọi this.fetch vẫn chạy target, mặc dù cache B đã có entry. Lý do không phải do cache miss; lý do là **interceptor không có cơ hội tra cache**.

Do đó, việc nhìn thấy entry đã tồn tại trong cache nhưng method vẫn chạy không đủ để kết luận @Cacheable sai key: cần kiểm tra liệu lời gọi có qua proxy hay không.

## 7. Cách khắc phục self-invocation khuyến nghị: tách thành bean cộng tác

Giải pháp thiết kế rõ ràng nhất trong nhiều ứng dụng là **đưa method được cache sang một bean riêng** rồi inject bean này vào lớp gọi.

~~~text
OrderFacade (Spring bean)
     |
     | injected CatalogReader bean reference
     v
CatalogReader proxy
     |
     v
@Cacheable CatalogReader.find(sku)
     |
     +-- cache HIT -> trả về
     +-- cache MISS -> target CatalogReader.find(sku)
~~~

Một minh họa cách tổ chức:

~~~java
@Service
public class CatalogReader {

    @Cacheable(cacheNames = "catalog", key = "#p0")
    public String find(String sku) {
        return repositoryLookup(sku);
    }
}

@Service
public class OrderFacade {
    private final CatalogReader catalogReader;

    public OrderFacade(CatalogReader catalogReader) {
        this.catalogReader = catalogReader;
    }

    public String createOrder(String sku) {
        String product = catalogReader.find(sku);
        return "order-for-" + product;
    }
}
~~~

Đây là **mã cấu trúc minh họa**; repositoryLookup, import và triển khai nghiệp vụ cần bổ sung, nên không coi nó là chương trình độc lập. Lợi ích:
- Đường gọi từ **OrderFacade** tới **CatalogReader** đi qua bean proxy được inject.
- Trách nhiệm đọc dữ liệu và phối hợp nghiệp vụ rõ ràng.
- Dễ viết integration test thực sự đi qua ApplicationContext.
- Không cần tạo vòng phụ thuộc bean, không phụ thuộc AopContext hoặc cơ chế exposeProxy.

Không nhất thiết phải tách mọi phương thức thành một class. Chỉ tách phần có chính sách caching riêng hoặc phần thường bị gọi nội bộ và cần được intercept.

### Alternative: inject proxy của chính mình

Một số dự án dùng **self-injection** hoặc tra cứu proxy từ container để gọi lại phương thức qua proxy. Về mặt kỹ thuật có thể khắc phục bypass, nhưng dễ sinh vòng phụ thuộc, khó kiểm thử và coupling với container. Từ Spring Boot mới, circular reference thường bị hạn chế theo cấu hình mặc định. Chỉ chọn khi thực sự hiểu lifecycle và có lý do rõ; **tách bean** thường đơn giản, an toàn hơn.

### Alternative: AopContext.currentProxy()

Có thể cấu hình exposeProxy rồi lấy proxy hiện tại qua AopContext. Cách này trói code nghiệp vụ với Spring AOP, chỉ hoạt động trong context advice phù hợp và cần cấu hình bổ sung; không nên dùng mặc định chỉ để cứu một self-invocation. **@EnableCaching(proxyTargetClass=true) đơn thuần không bật exposeProxy**.

### Alternative: AdviceMode.ASPECTJ

Nếu bắt buộc caching phải hoạt động cả với self-invocation theo kiểu bytecode, Spring hỗ trợ chế độ weaving:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.cache.annotation.EnableCaching;

@EnableCaching(mode = AdviceMode.ASPECTJ)
~~~

Đây là **đoạn cấu hình minh họa** trên class cấu hình, không phải ứng dụng chạy độc lập. AspectJ caching đòi hỏi **spring-aspects** và **compile-time weaving hoặc load-time weaving** được thiết lập đúng. Chỉ đổi mode trong annotation mà không có dependency/weaver phù hợp không làm chương trình tự vận hành theo AspectJ.

Ở chế độ ASPECTJ, Spring có thể áp dụng advice cho các lời gọi nội bộ theo cơ chế weaving (không còn phụ thuộc ranh giới proxy Java như PROXY). Đổi lại, build/deployment phức tạp hơn và cần kiểm thử cẩn thận. **proxyTargetClass** không có vai trò điều khiển loại proxy ở mode ASPECTJ.

## 8. Cách kiểm chứng bean thực sự là proxy

Khi kiểm tra lỗi, trước tiên lấy bean đã được container quản lý:

~~~java
CatalogService service =
    applicationContext.getBean(CatalogService.class);
~~~

Đây là đoạn minh họa với biến applicationContext đã được cung cấp. Với JDK proxy, bạn có thể cần lấy bean theo **interface** thay vì concrete class.

Kiểm tra Spring AOP mà không dựa vào tên class có ký hiệu proxy:

~~~java
import org.springframework.aop.support.AopUtils;

boolean isProxy = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean classProxy = AopUtils.isCglibProxy(service);
~~~

Đây là đoạn minh họa, chưa là chương trình độc lập; AopUtils nằm trong module spring-aop. **isAopProxy** giúp xác minh có proxy ở reference hiện tại. **isJdkDynamicProxy** và **isCglibProxy** giúp nhận diện họ proxy. Không phải mọi proxy đều do caching tạo: @Transactional, security, retry hoặc advice khác cũng có thể tạo proxy. **isAopProxy=true chỉ chứng minh object là Spring AOP proxy, không tự chứng minh @Cacheable của method cụ thể đang được intercept**.

Cần thêm kiểm thử hành vi: cùng input gọi hai lần qua bean proxy, quan sát số lần target method thực thi và entry đã ghi. Nếu cache miss mỗi lần dù có proxy, tiếp tục xem cache name, key, condition, unless, TTL, eviction hoặc cấu hình hạ tầng.

### Tránh suy đoán từ tên class trong log

JDK proxy có thể in tên dạng jdk.proxy...; class proxy có thể xuất hiện ký hiệu subclass/enhancer. Những tên cụ thể phụ thuộc runtime và phiên bản, không nên hard-code vào kiểm thử. Dùng AopUtils và hành vi gọi phương thức thay vì so chuỗi class name.

## 9. Những nơi proxy mode dễ bị bỏ qua

### 9.1. Phương thức nội bộ gọi qua this hoặc gọi ngầm

~~~java
@Cacheable("catalog")
public String find(String sku) { return query(sku); }

public String refreshView(String sku) {
    return find(sku); // self-invocation, không đi qua proxy.
}
~~~

Đây là minh họa. Dù refreshView được gọi từ controller qua proxy, lời gọi find trong thân target là gọi nội bộ. Nếu refreshView cũng có annotation cache riêng, Spring chỉ có thể áp dụng **operation trên refreshView ở ranh giới proxy**, không tự thêm interception cho find bên trong.

### 9.2. Object không do container quản lý

~~~java
var service = new CatalogService();
service.find("A");
~~~

Không có Spring bean proxy; @Cacheable không tự hiệu lực. Với class được đăng ký bằng @Bean hoặc @Component/@Service và inject đúng, hạ tầng caching mới có thể áp dụng.

### 9.3. Khởi tạo trong constructor hoặc @PostConstruct

Trong lúc object đang khởi tạo, bean proxy có thể chưa hoàn chỉnh hoặc chưa được trao cho caller. Nếu @PostConstruct gọi method cache-annotated trên this, đừng kỳ vọng caching advice hoạt động. Spring cũng khuyến nghị không phụ thuộc cache proxy trong initialization logic.

Cần warmup cache sau khi context sẵn sàng thì gọi qua **bean proxy** từ một thành phần khác ở thời điểm thích hợp, thay vì gọi method cache-annotated ngay trong constructor.

### 9.4. Bean ở ApplicationContext khác

Trong Spring MVC truyền thống có thể có **root ApplicationContext** cho services và **child WebApplicationContext** cho controllers. Nếu @EnableCaching chỉ được khai báo ở child context nhưng service nằm ở root context, cache annotation trên service có thể không được xử lý theo kỳ vọng.

Hãy đặt caching infrastructure trong context quản lý các bean cần cache, hoặc cấu hình phù hợp kiến trúc context. Không suy luận rằng một @EnableCaching trong toàn bộ ứng dụng luôn quét tự động mọi context độc lập.

### 9.5. Chọn bean theo concrete type khi dùng JDK proxy

Nếu class implement interface và bean là JDK dynamic proxy, inject theo class có thể không assign được. Hãy inject interface phù hợp hoặc cấu hình class-based proxy có chủ đích và hiểu giới hạn final class/final methods.

### 9.6. Nhiều advice và thứ tự áp dụng

@Cacheable có thể kết hợp @Transactional, @Async, security hoặc advice khác. Lời gọi vẫn cần đi qua proxy, nhưng **thứ tự advice** có thể ảnh hưởng transaction boundary, exception, thread và thời điểm cache update. Thuộc tính **order** của @EnableCaching điều khiển thứ tự advisor caching trong ngữ cảnh AOP; không nên giả định mọi advice tự có thứ tự tối ưu cho mọi nghiệp vụ.

Khi cache dữ liệu thay đổi trong transaction, cần phân biệt **method trả về** và **transaction đã commit**. Cache được put hoặc evict sai thời điểm có thể gây stale/dirty visibility. Đây là bài toán phối hợp cache và transaction, không tự được khắc phục bằng cách chuyển JDK proxy sang class proxy.

## 10. Debug theo trình tự thay vì đổi cache provider ngay

Khi @Cacheable dường như "không hoạt động", kiểm tra từng bước:

| Bước | Kiểm tra | Nếu không đúng |
| --- | --- | --- |
| 1 | Có @EnableCaching hoặc tương đương, CacheManager hợp lệ? | Bổ sung hạ tầng; kiểm tra bean/config active |
| 2 | Object là bean do Spring quản lý? | Không dùng new cho service cần interception |
| 3 | Đang gọi reference từ ApplicationContext/injection đúng kiểu? | Dùng bean proxy thay vì target/raw instance |
| 4 | Có self-invocation thông qua this? | Tách thành bean cộng tác, gọi qua injected proxy |
| 5 | Method public, không bị hạn chế bởi final/private/static? | Dùng public instance method có thể được advice |
| 6 | Class có interface và JDK proxy được inject đúng type? | Inject interface hoặc chọn class proxy phù hợp |
| 7 | AopUtils.isAopProxy(reference) đúng? | Xem context/auto-proxy configuration |
| 8 | Cache name tồn tại, key tạo đúng, condition/unless không chặn? | Test key và operation thực tế |
| 9 | TTL/eviction/provider có làm entry mất ngay? | Kiểm tra chính sách lưu trữ, không vội đổ lỗi proxy |
| 10 | Có advice khác làm thay đổi thứ tự/transaction/thread? | Kiểm tra thứ tự advisor và test tích hợp |

**Một quy trình quan sát tối thiểu:**
1. Dùng một bộ đếm **targetCalls** trong method thực.
2. Gọi hai lần cùng input qua injected service bean.
3. So sánh kết quả và số lần target method chạy.
4. Gọi tương tự qua một method nội bộ dùng this.
5. So sánh và kiểm tra cache bằng CacheManager đúng bean.

Với @Cacheable và một cache không hết hạn, kết quả kỳ vọng: qua proxy thì lần hai hit; self-invocation thì target method vẫn chạy. Nếu một lời gọi có exception hoặc provider gặp lỗi, hành vi còn tùy CacheErrorHandler và annotation; không nên khẳng định mọi lần gọi đều thành công.

## 11. Phân biệt đường gọi với thiết kế khóa cache

Có proxy nhưng key không nhất quán vẫn có thể miss mọi lần:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0")
public String find(String sku) {
    return repository.findName(sku);
}
~~~

Đây là minh họa. Nếu caller lần 1 truyền " A " và lần 2 truyền "A", key String khác nhau. Cache miss **dù proxy hoạt động đúng**. Tương tự, khi return value được phủ quyết bằng unless, điều kiện condition false, cache manager không dùng đúng cache hoặc bị evict bởi operation khác, biểu hiện có thể là method chạy nhiều lần.

Vì vậy, phân loại nguyên nhân thành hai nhánh:
- **Interceptor không chạy:** do self-invocation, raw new, thiếu @EnableCaching, bean/context/proxy không phù hợp.
- **Interceptor chạy nhưng cache không hit:** do key, condition, unless, cacheName, TTL, eviction hoặc provider.

Phân biệt này giúp tránh "sửa" vấn đề bằng cách thay hashCode(), tăng TTL hay đổi Redis trong khi nguyên nhân là **method hoàn toàn không đi qua proxy**.

## 12. Câu hỏi tự kiểm tra

**1.** @Cacheable trên public method, người gọi dùng new Service().find("A"). Method có được Spring Cache intercept không?

**Không.** Object không được quản lý/proxy bởi Spring; annotation không tự biến thành logic cache trong lời gọi Java trực tiếp.

**2.** Controller inject ProductService và gọi productService.find("A") qua Spring bean. Đây có phải đường gọi phù hợp cho proxy caching?

**Có**, nếu @EnableCaching/cache infrastructure hoạt động và method có thể được advice. Đường gọi từ bên ngoài đi qua reference bean proxy tạo điều kiện cho caching interceptor.

**3.** Trong ProductService.refresh(), có this.find("A") và find có @Cacheable. Cách gọi này có hit cache theo PROXY không?

**Không do annotation trên find**, vì self-invocation bỏ qua proxy; nếu muốn caching cho find, hãy chuyển sang gọi một bean khác được inject hoặc dùng cơ chế phù hợp.

**4.** Đặt @EnableCaching(proxyTargetClass=true) có khiến this.find đi qua proxy không?

**Không.** Thuộc tính này chọn class-based proxy; nó **không** tự thay đổi đường gọi nội bộ this.

**5.** Vì sao BeanService có interface nhưng inject theo concrete class đôi khi thất bại?

Vì với JDK proxy, bean proxy triển khai interface và không bắt buộc là subclass của concrete class. Inject theo interface là lựa chọn tương thích với JDK proxy.

**6.** Có phải chỉ cần isAopProxy(bean)=true là mọi cache annotation đều hoạt động?

**Không.** Proxy có thể được tạo vì advice khác; annotation cụ thể vẫn có thể không hợp lệ, method không được intercept, hoặc cache operation bị điều kiện/key/provider ảnh hưởng.

**7.** Muốn áp dụng cache cho self-invocation mà không refactor sang bean khác thì có lựa chọn nào?

Có thể dùng AspectJ weaving với spring-aspects và cấu hình compile-time/load-time weaving phù hợp; đây là lựa chọn nâng cao, cần kiểm thử và chấp nhận phức tạp build/runtime.

**8.** Có cần public method và Spring-managed bean để minh họa Spring Cache an toàn trong proxy mode không?

**Nên có**. Public instance method trên một Spring bean được gọi qua proxy là mô hình dễ hiểu, dễ test và phù hợp khuyến nghị Spring.

## Tóm tắt

- **@EnableCaching mặc định dùng AdviceMode.PROXY**.
- Cache advice có hiệu lực khi caller **đi qua proxy bean Spring**; object tự new và self-invocation qua this thường **bỏ qua** cache interceptor.
- **proxyTargetClass** chọn họ proxy, không giải quyết tự động self-invocation. JDK dynamic proxy dựa trên interface; class-based proxy dựa trên subclass và bị giới hạn bởi final class/final methods.
- Khi cần một method cache-annotated được gọi từ logic nội bộ, **tách nó sang bean cộng tác và inject bean đó** là lựa chọn dễ bảo trì.
- Chỉ chuyển sang **AdviceMode.ASPECTJ** khi có nhu cầu interception bên trong class và đã cấu hình đủ **spring-aspects + weaving**.
- Khi debug, phân biệt rõ **interceptor chưa được gọi** với **interceptor có chạy nhưng cache miss**.

### Tài liệu chính thức

- Spring Framework 6.2 – Annotation-based caching (enabling, proxy mode, self-invocation và method visibility): https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- @EnableCaching API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring AOP – Proxying mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring AOP – Understanding AOP proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html#_understanding_aop_proxies
- @Cacheable API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/Cacheable.html

# Kiểm tra bean nghiệp vụ được Spring quản lý để Spring Cache hoạt động

## 1. Mục tiêu

Trong Spring Framework, một phương thức có `@Cacheable` chưa chắc được caching. Annotation chỉ mô tả ý định; Spring phải **quản lý đối tượng nghiệp vụ như một bean**, bật hạ tầng caching và đưa lời gọi qua cơ chế advice tương ứng. Khi gặp tình huống “đã thêm `@Cacheable` nhưng lần nào cũng truy vấn dữ liệu”, bước thiết lập quan trọng đầu tiên là kiểm tra **đối tượng đang được gọi đến từ đâu**.

Sau bài này, bạn có thể:

1. Xác minh service/repository/bean nghiệp vụ thật sự có mặt trong `ApplicationContext` đang chạy.
2. Phân biệt **được Spring quản lý** với **được proxy để áp dụng cache** và **đang có cache hit thật sự**.
3. Kiểm tra bean theo tên, kiểu, proxy và cache advice bằng các API của Spring.
4. Chẩn đoán các lỗi cấu hình như package scan sai, nhiều context, tự tạo object bằng `new`, tự gọi method (`self-invocation`), method không được proxy, hoặc thiếu `@EnableCaching`.
5. Chạy một ví dụ Java 17+ có đối chứng giữa bean do Spring trả về và object thông thường.

**Tiêu chí quan trọng:** Lời gọi phải đi qua reference của bean được Spring cung cấp, thường là **AOP proxy**, chứ không chỉ tồn tại một class có gắn `@Service` và `@Cacheable`.

## 2. Bean do Spring quản lý là gì?

`ApplicationContext` là container chứa các `BeanDefinition`, chịu trách nhiệm tạo, cấu hình, tiêm dependency và quản lý vòng đời bean. Một *business bean* có thể là service xử lý nghiệp vụ, repository, client adapter hoặc component thực hiện truy xuất dữ liệu. Với caching thông qua Spring AOP mặc định, Spring thường tạo một **proxy** đại diện cho bean phù hợp; client phải gọi qua proxy để caching advice có cơ hội hoạt động.

Các cách đăng ký business bean phổ biến:

| Cách đăng ký | Ví dụ | Điều kiện để có trong context |
| --- | --- | --- |
| Component scanning | `@Service`, `@Component`, `@Repository` | Class thuộc phạm vi `@ComponentScan` hoặc scan mặc định của Spring Boot; không bị filter/profile/condition loại trừ. |
| Java configuration | `@Bean PriceService priceService()` | `@Configuration` chứa phương thức `@Bean` phải được đăng ký/import vào context. |
| Import/configuration khác | `@Import`, XML, đăng ký bean bằng API | Bean definition thực sự được nạp vào context hiện tại. |

`@Service` là một specialization của `@Component`, nên component scanner có thể nhận diện nó. Nhưng **chỉ viết `@Service` trên class chưa khiến class tự động xuất hiện trong mọi context**.

Ví dụ mã cấu hình của một ứng dụng dùng component scan:

~~~java
@Configuration
@ComponentScan(basePackages = "com.example.catalog")
@EnableCaching
public class CatalogConfig {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

~~~java
package com.example.catalog.service;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String sku) {
        return "product-" + sku;
    }
}
~~~

**Lưu ý:** Hai đoạn trên minh họa cấu hình của một dự án có dependency Spring phù hợp, không phải toàn bộ chương trình độc lập. Phạm vi scan `com.example.catalog` bao gồm package con `com.example.catalog.service`. Nếu class `ProductService` nằm ở một package khác ngoài scan, bean sẽ không được tự động đăng ký.

Với Spring Boot, `@SpringBootApplication` bao gồm component scanning mặc định từ package chứa class ứng dụng xuống các package con. `@EnableCaching` vẫn là bước kích hoạt xử lý annotation caching, có thể đặt trên một class cấu hình phù hợp.

### “Spring quản lý” không đồng nghĩa “đã cache”

Ba mệnh đề cần kiểm tra riêng:

- **Bean được quản lý:** Container tìm được bean tương ứng và trả về reference khi gọi `getBean(...)`/dependency injection.
- **Bean được AOP proxy:** Reference có thể là proxy được tạo bởi Spring AOP, nhưng proxy đó có thể chỉ chứa transaction/security advice, chưa chắc có caching advice.
- **Cache hoạt động:** Lời gọi qua proxy tới method được áp dụng `@Cacheable`, key/condition/cache backend hợp lệ, và lần gọi lặp lại có thể trả từ cache mà không thực thi business method.

Sơ đồ quan hệ:

~~~mermaid
flowchart TD
    A[Business class] --> B{Đã đăng ký trong ApplicationContext?}
    B -->|Không| C[Sửa scan, Bean config, profile hoặc context]
    B -->|Có| D{Caching được bật và có cache operation?}
    D -->|Không| E[Kiểm tra EnableCaching và annotation]
    D -->|Có| F{Lời gọi qua cache AOP proxy?}
    F -->|Không| G[Kiểm tra new, self-invocation, proxy limits]
    F -->|Có| H[Kiểm tra key, cache, condition và hit/miss]
~~~

## 3. Bước 1 — xác minh business bean có mặt trong đúng context

Giả sử cần kiểm tra một `ProductService` trong `ApplicationContext context`. Các lệnh sau là **đoạn minh họa bên trong code đã có biến `context` và class `ProductService`**:

~~~java
// Kiểm tra theo tên bean (tên mặc định của @Service thường là productService):
boolean existsByName = context.containsBean("productService");

// Kiểm tra theo kiểu; thành công khi chỉ có một bean phù hợp:
ProductService service = context.getBean(ProductService.class);

// Liệt kê tên bean phù hợp với kiểu:
String[] names = context.getBeanNamesForType(ProductService.class);
System.out.println(Arrays.toString(names));
~~~

### Cách diễn giải kết quả

- `context.containsBean("productService") == true`: container nhận ra bean theo **tên đó** (có thể tính cả bean ở parent context). **Không chứng minh caching advice có trên bean**.
- `context.containsBean("productService") == false`: tên đó không tồn tại; **chưa thể kết luận loại bean này không được quản lý**, vì tên có thể đã được chỉ định khác, có alias, hoặc proxy được đăng ký theo kiểu khác.
- `getBean(ProductService.class)` thành công: container cung cấp được một bean theo kiểu yêu cầu. Nếu không có bean, Spring thường ném `NoSuchBeanDefinitionException`; nếu có nhiều ứng viên không phân giải được, ném `NoUniqueBeanDefinitionException`.
- `getBeanNamesForType(...)` trả tên các ứng viên theo kiểu và giúp phát hiện trùng đăng ký. Trong hệ thống có JDK dynamic proxy, **kiểu triển khai cụ thể** có thể không phải kiểu proxy expose; hãy ưu tiên kiểm tra theo interface mà client inject.
- `context.getBean("productService")` trả reference mà ứng dụng nên sử dụng. Đối chiếu reference này với object đang được gọi thực tế để phát hiện code tự tạo instance.

API tên bean và kiểu có những giới hạn cần biết. `containsBeanDefinition(name)` (trên `BeanFactory` phù hợp) kiểm tra definition đăng ký **cục bộ** ở factory đó; khác với `containsBean(name)`, có thể tìm lên parent. Một số thao tác truy vấn bean theo kiểu có thể kích hoạt khởi tạo bean hoặc `FactoryBean` trong quá trình chẩn đoán; không lạm dụng quét tất cả bean ở request path.

### Kiểm tra Spring Boot nhanh

Trong môi trường Boot có `ApplicationContext` được inject, có thể viết một kiểm tra lúc khởi động hoặc integration test:

~~~java
@Component
public class BeanPresenceCheck {
    private final ApplicationContext context;

    public BeanPresenceCheck(ApplicationContext context) {
        this.context = context;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void report() {
        System.out.println(
            "service present = " + context.containsBean("productService")
        );
    }
}
~~~

Đây là **đoạn minh họa cho ứng dụng Spring Boot**, cần thêm import tương ứng của `ApplicationContext`, `Component`, `EventListener`, `ApplicationReadyEvent` và có bean `productService` thực sự. Sự kiện `ApplicationReadyEvent` cho phép kiểm tra sau khi ứng dụng Boot khởi động; không đặt test cache trong constructor hoặc `@PostConstruct` rồi suy ra proxy đã sẵn sàng.

## 4. Bước 2 — xác minh proxy và cache advice

Spring Cache ở chế độ mặc định `@EnableCaching(mode = AdviceMode.PROXY)` sử dụng proxy của Spring AOP. Nếu code gọi bean theo đúng reference do context trả về, bạn có thể xem một số dấu hiệu:

~~~java
Object bean = context.getBean("productService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

Các lệnh trên là **đoạn minh họa**, cần các import `org.springframework.aop.support.AopUtils` và context phù hợp.

| Kết quả | Ý nghĩa |
| --- | --- |
| `AopUtils.isAopProxy(bean) == false` | Reference không phải Spring AOP proxy; có thể do không có applicable advisor, caching chưa được bật hoặc bean đã được lấy/tạo theo cách khác. |
| `isJdkDynamicProxy(bean) == true` | Proxy dựa trên interface; code nên inject/gọi theo interface, tránh ép về implementation class. |
| `isCglibProxy(bean) == true` | Proxy dạng subclass của target class; class `final` hoặc method `final` có giới hạn proxy. |
| `getTargetClass(bean)` | Giúp thấy class business đích khi tên class của proxy có suffix do runtime sinh ra. |

**Quan trọng:** Proxy có thể tồn tại vì `@Transactional`, logging hoặc một advice khác. Vì thế `isAopProxy == true` **không đủ để chứng minh đã gắn caching interceptor**.

### Kiểm tra có `CacheInterceptor` trong advisor

Với Spring AOP proxy có thể truy cập dưới interface `Advised`:

~~~java
Object bean = context.getBean("productService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getAdvice().getClass().getName());
    }
}
~~~

Import minh họa: `org.springframework.aop.framework.Advised` và `org.springframework.aop.Advisor`. Một cache advisor điển hình của annotation-based caching dùng advice `org.springframework.cache.interceptor.CacheInterceptor`.

Bạn có thể kiểm tra cụ thể bằng:

~~~java
boolean hasCacheAdvice =
    bean instanceof Advised advised &&
    Arrays.stream(advised.getAdvisors())
          .anyMatch(advisor ->
              advisor.getAdvice() instanceof CacheInterceptor);
~~~

Đây là **phép kiểm tra chẩn đoán**, không phải một cam kết API cho mọi cách triển khai advice: proxy có thể được cấu hình opaque hoặc phương thức được áp dụng qua cơ chế AspectJ weaving. Có `CacheInterceptor` trên proxy vẫn chưa chứng minh **method đang gọi** khớp pointcut/cache operation; phải kiểm tra hành vi.

### Đường đi mong muốn

~~~text
Controller / job / message listener
    -> Spring-injected reference của ProductService
    -> Spring AOP proxy
    -> CacheInterceptor (nếu method có cache operation phù hợp)
    -> Cache / business method theo hit-miss
~~~

Trong `proxy mode`, các lời gọi trực tiếp qua `this.method()` từ cùng object đi vào target mà không quay lại proxy. Ngược lại, gọi method public trên bean do container cấp từ một bean khác là cách dễ dự đoán nhất.

## 5. Bước 3 — xác nhận cache infrastructure và hành vi thật

Sau khi xác minh bean hiện diện và có proxy, kiểm tra cấu hình caching:

1. Có `@EnableCaching` trong đúng `ApplicationContext` chứa business bean hay không?
2. Có ít nhất một `CacheManager` phù hợp (hoặc `CacheResolver` tự cấu hình), và cache name được resolve đúng hay không?
3. Method đang gọi có một cache operation, ví dụ `@Cacheable("products")`, với key, condition và visibility phù hợp hay không?
4. Caller có lấy reference từ dependency injection/`getBean` thay vì `new ProductService()` hoặc `this.find()` hay không?
5. Khi gọi hai lần với **cùng key**, số lần thực hiện business method có giảm từ hai xuống một hay không?

Ví dụ kiểm tra cache name (minh họa có `context`):

~~~java
CacheManager manager = context.getBean(CacheManager.class);
Cache products = manager.getCache("products");

System.out.println("cache resolved = " + (products != null));
~~~

Import: `org.springframework.cache.CacheManager` và `org.springframework.cache.Cache`. `getCache("products") != null` chỉ chứng minh cache có thể được resolve, **không khẳng định method đã qua advice hoặc cache đang chứa giá trị**. Một số manager tạo cache lazily khi được yêu cầu, trong khi manager cấu hình tên cố định sẽ không nhận tên khác.

Cách đáng tin hơn để kiểm tra caching là đếm lần business method chạy. Nếu gọi hai lần với cùng argument mà method thực thi một lần, rồi thêm thao tác evict để method thực thi lại, bạn có bằng chứng hành vi của advice. Cần kiểm soát các yếu tố làm sai kết luận: `condition`, `unless`, TTL, eviction, concurrent calls, target tự memoize và dữ liệu đã được cache trước đó.

## 6. Ví dụ Java 17+ chạy độc lập với Maven

Ví dụ này đăng ký `PriceService` bằng `@Bean`, vì vậy không phụ thuộc package scanning; sau đó xác nhận **bean được quản lý**, **proxy chứa `CacheInterceptor`**, **cache name được resolve** và **hai lời gọi trùng key chỉ tính một lần**. Cuối cùng, đối chứng với một instance tự tạo bằng `new`.

Sử dụng Java 17+, Maven và Spring Framework **7.0.9** (phiên bản phát hành đã có trên Maven repositories). Tạo cấu trúc:

~~~text
managed-bean-cache/
├── pom.xml
└── src/main/java/demo/ManagedBeanCacheDemo.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>managed-bean-cache</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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

**File `src/main/java/demo/ManagedBeanCacheDemo.java`:**

~~~java
package demo;

import java.util.Arrays;

import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheInterceptor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ManagedBeanCacheDemo {

    @Configuration
    @EnableCaching(proxyTargetClass = true)
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    // Business object. Bean @Bean bên trên được Spring quản lý và proxy.
    public static class PriceService {
        private int invocations;

        @Cacheable(cacheNames = "prices", key = "#p0")
        public String price(String sku) {
            invocations++;
            System.out.println("compute " + sku + " #" + invocations);
            return "price-" + sku + "-" + invocations;
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Object bean = context.getBean("priceService");
            PriceService service = context.getBean(PriceService.class);

            System.out.println("registered = " +
                context.containsBean("priceService"));
            System.out.println("same bean by type = " + (bean == service));
            System.out.println("is AOP proxy = " + AopUtils.isAopProxy(bean));
            System.out.println("is CGLIB proxy = " + AopUtils.isCglibProxy(bean));

            boolean hasCacheAdvice =
                bean instanceof Advised advised &&
                Arrays.stream(advised.getAdvisors())
                      .anyMatch(advisor ->
                          advisor.getAdvice() instanceof CacheInterceptor);

            System.out.println("cache advice = " + hasCacheAdvice);
            System.out.println("cache exists = " +
                (context.getBean(CacheManager.class)
                        .getCache("prices") != null));

            System.out.println("first = " + service.price("SKU-1"));
            System.out.println("second = " + service.price("SKU-1"));

            PriceService plain = new PriceService();
            System.out.println("plain first = " + plain.price("SKU-1"));
            System.out.println("plain second = " + plain.price("SKU-1"));
        }
    }
}
~~~

Chạy tại thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.ManagedBeanCacheDemo"
~~~

**Dòng do chương trình in ra, bỏ qua log phụ thuộc vào Maven/môi trường:**

~~~text
registered = true
same bean by type = true
is AOP proxy = true
is CGLIB proxy = true
cache advice = true
cache exists = true
compute SKU-1 #1
first = price-SKU-1-1
second = price-SKU-1-1
compute SKU-1 #1
plain first = price-SKU-1-1
compute SKU-1 #2
plain second = price-SKU-1-2
~~~

Giải thích:

- `Config` là Spring configuration, có `@EnableCaching` và cung cấp `CacheManager` cùng bean `priceService`. Dù trong factory method có câu `new PriceService()`, **instance được trả về từ `@Bean` vẫn do Spring container quản lý** và có thể được bọc proxy sau bước khởi tạo.
- `getBean("priceService")` và `getBean(PriceService.class)` trả cùng **reference proxy** của bean (ví dụ dùng class-based proxy một cách chủ đích).
- `isAopProxy`, `isCglibProxy` và phép duyệt advisors chứng minh bean có proxy caching trong cấu hình này.
- Lần `service.price("SKU-1")` đầu tiên cache miss: business method in `compute ... #1`. Lần thứ hai cùng key là hit, nên không in thêm `compute`.
- Instance `plain` được gọi trực tiếp, chưa từng qua Spring container: cả hai lần đều thực thi thân method và bộ đếm tăng.
- `ConcurrentMapCacheManager` chỉ là cache bộ nhớ phù hợp demo. Nó không cung cấp sự chia sẻ giữa nhiều tiến trình hoặc tính bền vững sau khi tắt ứng dụng.

**Phạm vi tính runnable:** Đây là chương trình Spring Core đầy đủ (không yêu cầu Spring Boot hay database). Khi chuyển sang ứng dụng thực tế, để dependency injection lấy đúng service proxy, bạn cần giữ nguyên nguyên tắc “bean trong context + gọi qua proxy” và thay manager phù hợp môi trường.

## 7. Biến thể có `@Service` và component scanning

Trong dự án thực tế, cách đăng ký phổ biến hơn là:

~~~java
// File: src/main/java/com/example/catalog/service/PriceService.java
package com.example.catalog.service;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    @Cacheable(cacheNames = "prices", key = "#p0")
    public String price(String sku) {
        return "price-" + sku;
    }
}
~~~

~~~java
// File: src/main/java/com/example/catalog/CatalogConfig.java
package com.example.catalog;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "com.example.catalog")
@EnableCaching
public class CatalogConfig {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("prices");
    }
}
~~~

Đây là **cặp class minh họa** cho một ứng dụng cấu hình dựa trên package, chưa kèm `main()`. `@ComponentScan` quét `com.example.catalog` và package con; `PriceService` được đăng ký với tên mặc định `priceService`. Nếu config nằm ở `com.example.app` mà chỉ scan package đó, service ở `com.example.catalog.service` có thể bị bỏ sót. Khi cần, thay đổi base package hoặc `@Import`/`@Bean` rõ ràng.

Để phát hiện trường hợp bean trùng kiểu, kiểm tra `context.getBeanNamesForType(PriceService.class)` và cấu hình `@Primary`/`@Qualifier` khi có nhiều ứng viên. Tuy nhiên nếu runtime dùng JDK proxy dựa trên interface, nên truy vấn theo **interface** được inject thay vì mặc định implementation class luôn là kiểu có thể lookup.

## 8. Vì sao bean đã tồn tại mà `@Cacheable` vẫn không chạy?

### 8.1. Tạo object ở ngoài container

~~~java
PriceService unmanaged = new PriceService();
unmanaged.price("SKU-1"); // Gọi trực tiếp; không có caching proxy
~~~

Đối tượng này không được đăng ký và không có cache advice. Ngoại lệ về mặt khái niệm là câu `new` nằm trong factory method `@Bean` rồi **instance được trả về cho container**, như ví dụ chính; việc Spring quản lý phụ thuộc **reference sử dụng trong lời gọi**.

**Cách sửa:** Inject `PriceService` vào bean khác qua constructor hoặc lấy đúng bean từ `ApplicationContext`. Không dùng `new` để gọi service đã được thiết kế cho Spring AOP.

### 8.2. Self-invocation

~~~java
@Service
public class ProductService {
    public String loadSummary(String sku) {
        return find(sku); // this.find(sku), không qua proxy
    }

    @Cacheable("products")
    public String find(String sku) {
        // ...
        return "product-" + sku;
    }
}
~~~

Đây là snippet minh họa trong ứng dụng có `@EnableCaching` và cache manager. Nếu client gọi `loadSummary` trên proxy, phần thân của `loadSummary` được thực thi trên target; lời gọi tiếp tới `find` bằng `this` không đi qua caching proxy. Có bean, thậm chí có cache advisor, nhưng path này vẫn bỏ qua `@Cacheable`.

**Cách sửa:** Tách method cacheable ra một Spring bean chuyên trách và inject bean đó vào caller; hoặc thiết kế lại đường gọi qua proxy. Đừng coi `AopUtils.isAopProxy(service)` là bằng chứng mọi lời gọi bên trong sẽ được chặn.

### 8.3. Annotation thiếu hoặc sai chỗ

- Có `@Service` nhưng quên `@Cacheable` trên method cần cache: bean được quản lý, không có cache operation cho method đó.
- Có `@Cacheable` nhưng chưa bật `@EnableCaching` trong context chứa service: Spring không thiết lập advice cần thiết.
- Annotate method `private`, `final` hoặc class `final` trong tình huống dùng class-based proxy: hạn chế của proxy khiến advice không áp dụng như mong đợi.
- Đặt annotation lên interface rồi dùng cấu hình weaving khác với proxy mode: cần xem lại nơi khai báo. Cách ít bất ngờ là đặt annotation trên method public của class thực thi.

### 8.4. Sai context

Trong hệ thống có **parent/child `ApplicationContext`**, hoặc cấu hình Spring MVC/Boot test slice, bean service có thể nằm ở context khác với cấu hình `@EnableCaching`. Caching processor chỉ áp dụng cho những bean trong phạm vi context mà nó xử lý. Một request từ web context không nhất thiết có thể suy luận cấu hình cache của root context từ việc nhìn thấy một controller.

Cần xác minh: class config nào được nạp, context chứa service thuộc cấp nào, `@EnableCaching` được đặt ở đâu, và reference thực tế được inject tới controller/job là bean nào. `@WebMvcTest` thường chỉ tải một phần ứng dụng; nếu cần chứng minh service caching thực tế, dùng integration test nạp đầy đủ các bean liên quan hoặc `@Import` rõ ràng.

### 8.5. Có proxy nhưng cache vẫn miss

Những lý do cần kiểm tra tiếp:

- Argument hoặc key khác nhau giữa các lần gọi; custom `KeyGenerator` không ổn định.
- `condition` trả false, `unless` ngăn ghi kết quả; giá trị null hoặc provider policy gây khác biệt.
- Cache bị xóa do `@CacheEvict`, bị thay bởi `@CachePut` hoặc hết TTL do provider.
- Cache đặt sai tên, manager/resolver sai hoặc nhiều instance backend không chia sẻ dữ liệu.
- Hai request đồng thời cùng miss trước khi một request hoàn thành việc ghi cache.
- Method gọi qua reference trực tiếp tới target object dù bean có proxy trong context.

Sau khi xác nhận bean đã được quản lý, cần chuyển kiểm tra sang **đường gọi, cache key và cache backend**, thay vì chỉ thêm `@Service` lần nữa.

## 9. Quy trình debug thực tế theo thứ tự

| Quan sát | Kiểm tra đầu tiên | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Package scanning, `@Bean`/`@Import`, profile, condition, parent/child context | Đăng ký đúng bean trong context; tránh tạo thủ công để “chữa cháy”. |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng type | Dùng `@Qualifier`/`@Primary` hoặc xóa đăng ký trùng có chủ đích. |
| `containsBean` false nhưng code chạy | Tên bean có thể khác, có object `new` nằm ngoài container | Kiểm tra tên/type, reference inject thực tế. |
| Bean tồn tại, `isAopProxy` false | `@EnableCaching`, operation annotation, advice có match không | Kiểm tra config đúng context và method eligible. |
| `isAopProxy` true, không có `CacheInterceptor` | Có thể chỉ có AOP advice khác | Kiểm tra hạ tầng cache/annotation và inspect advisors. |
| Có `CacheInterceptor`, business method vẫn chạy mỗi lần | self-invocation, khác key, `condition`/`unless`, TTL/evict | Đếm invocation, in key và kiểm tra cache hiệu lực. |
| Lúc chạy app thì cache hoạt động, nhưng unit test không | Test khởi tạo object trực tiếp hoặc slice không bật caching | Test với context phù hợp, inject bean từ Spring. |
| Chỉ một số method cache được | Method visibility/final, proxy interface, call path | Thiết kế public eligible method và gọi qua proxy. |

### Checklist kiểm tra nhanh

1. **Đúng bean?** `getBean(...)` thành công, reference đúng instance đang được caller sử dụng.
2. **Đúng context?** `@EnableCaching` được nạp trong phạm vi bean nghiệp vụ.
3. **Đúng advisor?** `AopUtils.isAopProxy`, sau đó kiểm tra cache advice nếu cần.
4. **Đúng method?** Có `@Cacheable`/operation phù hợp trên method public được gọi qua proxy.
5. **Đúng cache/key?** `CacheManager` resolve tên cache, key của hai lần gọi giống nhau.
6. **Đúng hành vi?** Lần hai cùng key không chạy thân method; khi clear/evict thì lần kế tiếp chạy lại.

Nếu năm kiểm tra đầu đạt mà test vẫn sai, bổ sung integration test có đường gọi giống production; quan sát số lần business method chạy và thống kê cache hit/miss của provider, rồi mới tối ưu hoặc thay đổi cấu hình.

## 10. Lưu ý vận hành và kiểm thử

- **Tránh khẳng định bằng tên class proxy:** `bean.getClass() == ProductService.class` có thể false dù bean hoàn toàn hợp lệ vì proxy có class sinh động. `AopUtils.getTargetClass(...)` có giá trị chẩn đoán hơn.
- **Không đặt probe cache trong constructor hoặc `@PostConstruct` của chính bean:** ở đó proxy có thể chưa sẵn sàng. Thử từ caller bean hoặc sau khi context hoàn tất khởi động.
- **Nên kiểm tra business outcome:** Bản thân `CacheInterceptor` xuất hiện trong danh sách advisors không đủ chứng minh caching chính xác cho method/key đang thử.
- **Không xem `isAopProxy == false` là kết luận tuyệt đối trong mọi mode:** `mode = ASPECTJ` dùng weaving thay vì proxy; bài tập kiểm tra ở đây hướng tới proxy mode phổ biến.
- **Quản lý scope và concurrency:** Singleton, prototype hoặc scoped proxy có hành vi vòng đời khác nhau; đừng lẫn số instance với số lần cache hit. TTL và việc phân tán cache thuộc provider, không nằm trong tính “bean được quản lý”.
- **Không bật class-based proxy tùy tiện:** `proxyTargetClass = true` hữu ích cho ví dụ kiểm tra theo implementation, nhưng với ứng dụng dùng interface, JDK proxy thường phù hợp. Những class/method `final` và ranh giới Java module cũng ảnh hưởng khả năng proxy.
- **Giữ cấu hình test giống runtime:** `Mockito.mock(...)` hoặc `new` không tự nhận advice; với test cần cache thật, lấy bean từ Spring context. Nếu test chỉ tập trung logic nghiệp vụ, không cần bật cache cho một unit test thuần.

## 11. Tài liệu chính thức

- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): `@Service`, `@ComponentScan`, cách đăng ký bean.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, method cache annotation, self-invocation và phạm vi context.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxy, CGLIB, method `final` và lời gọi qua `this`.
- [AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): API kiểm tra Spring AOP proxy và target class.
- [ApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContext.html): tìm bean theo tên và kiểu.

Một lần kiểm tra hoàn chỉnh cần xác minh ba lớp độc lập: **bean tồn tại trong đúng `ApplicationContext` → bean được áp dụng caching advice theo cơ chế đã cấu hình → lần gọi business đi qua advice và tạo cache hit/miss đúng kỳ vọng**.
# JDK proxy, proxy dựa trên lớp và `proxyTargetClass` trong Spring Cache

## 1. Mục tiêu và bức tranh tổng thể

Spring Cache dựa trên **Spring AOP** để áp dụng hành vi của `@Cacheable`, `@CachePut`, `@CacheEvict` và `@Caching` khi một lời gọi phương thức đi **qua Spring proxy**. Vì vậy, cùng một annotation có thể hoạt động hoặc bị bỏ qua tùy đường đi lời gọi, interface của bean, loại proxy, tính `final`, phạm vi truy cập phương thức và cấu hình `proxyTargetClass`.

Ba khái niệm cốt lõi:

- **JDK dynamic proxy (interface-based proxy):** đối tượng proxy được tạo nhờ cơ chế proxy chuẩn của JDK và **triển khai các interface** mà Spring chọn để expose. Nó không phải subclass của implementation class.
- **Class-based proxy (CGLIB):** Spring tạo subclass ở runtime từ implementation class. Proxy là một instance thuộc kiểu class đích, có thể chặn phương thức có thể override và đáp ứng các ràng buộc AOP.
- **`proxyTargetClass`:** một tùy chọn chọn chiến lược proxy. Trong caching proxy mode, `@EnableCaching(proxyTargetClass = true)` yêu cầu dùng class-based proxy; `false` là mặc định của **Spring Framework** và thường ưu tiên JDK proxy khi target có interface.

Đừng đồng nhất **proxy mode** với **proxy type**. Proxy mode (`AdviceMode.PROXY`) có nghĩa advice chạy tại ranh giới proxy; trong mode đó, JDK hay CGLIB là cách tạo object proxy. Còn `AdviceMode.ASPECTJ` sử dụng weaving (cấu hình riêng), **không phải** một phiên bản “mạnh hơn” của CGLIB.

### Câu hỏi thực tế

Giả sử `ProductServiceImpl` triển khai `ProductService`:

~~~java
public interface ProductService {
    Product get(long id);
}

public class ProductServiceImpl implements ProductService {
    @Override
    @Cacheable(cacheNames = "products", key = "#p0")
    public Product get(long id) {
        return repository.find(id);
    }

    @Cacheable(cacheNames = "stats", key = "#p0")
    public String internalStats(long id) {
        return repository.stats(id);
    }
}
~~~

Đây là **snippet minh họa**: cần `Product`, `repository`, Spring bean và `@EnableCaching`. Trong JDK proxy, caller thông thường chỉ có thể gọi API thuộc interface `ProductService` qua proxy; `internalStats` không nằm trên interface, nên không được expose trên JDK proxy. Với class-based proxy, caller có thể dùng kiểu `ProductServiceImpl` và gọi phương thức public `internalStats` qua proxy, nếu nó đủ điều kiện được advice.

Điều quan trọng không phải “annotation có xuất hiện trong source hay không”, mà là **lời gọi vào phương thức được Spring interceptor chặn hay không**.

## 2. Spring chọn loại proxy theo quy tắc nào?

Trong Spring AOP proxying thông thường, lựa chọn khái quát:

| Target bean | `proxyTargetClass=false` | `proxyTargetClass=true` |
| --- | --- | --- |
| Có ít nhất một interface phù hợp để proxy | Thường tạo JDK dynamic proxy | Tạo class-based proxy bằng CGLIB |
| Không có interface để proxy | Vẫn tạo class-based proxy (không thể dùng JDK interface proxy) | Tạo class-based proxy |
| Class `final` có interface | Có thể dùng JDK proxy cho phương thức interface được hỗ trợ | Không thể subclass class `final` bằng CGLIB |
| Method `final` trên class không `final` | Method thuộc interface có thể được intercept ở lớp JDK proxy | Không thể override method `final` để advice bằng CGLIB |
| Không có cache/advisor áp dụng | Không nhất thiết tạo proxy | Không nhất thiết tạo proxy; `true` không biến mọi bean thành proxied bean |

**Quy tắc “false = JDK proxy” không tuyệt đối.** Nếu bean không có interface để Spring expose, class-based proxy vẫn là lựa chọn khả thi khi bật caching proxy mode. Các thành phần auto-proxy khác, cấu hình toàn cục, Spring Boot và phiên bản framework cũng có thể ảnh hưởng kết quả cuối. Hãy **kiểm tra object proxy thực tế**, đừng kết luận chỉ từ một annotation.

## 3. JDK dynamic proxy: dựa trên interface

JDK dynamic proxy được JVM tạo ra để implement một hoặc nhiều interface. Một lời gọi:

~~~text
Caller
  |
  v
JDK proxy implements ProductService
  |
  v
Spring CacheInterceptor / AOP advice
  |
  +--> cache hit: trả kết quả
  |
  +--> cache miss: gọi target ProductServiceImpl.get(id)
~~~

Vì JDK proxy **không extends `ProductServiceImpl`**, những đặc điểm sau là quan trọng:

1. Có thể inject và gọi bằng **interface type** (`ProductService`), là cách tổ chức ít phụ thuộc implementation.
2. Không cast JDK proxy về `ProductServiceImpl` dù target bên dưới đúng là class này. `proxy instanceof ProductServiceImpl` là `false`.
3. Method public tồn tại **chỉ trên implementation** nhưng không nằm trong proxy interface không phải API để gọi trên JDK proxy. Nếu cần expose method đó, cân nhắc đưa nó vào interface hoặc chọn class-based proxy.
4. Annotation `@Cacheable` đặt trên **implementation method** là lựa chọn ổn định khi có khả năng thay đổi proxy strategy; Spring có thể tìm cache operation từ target method. Đừng đặt mọi annotation chỉ ở interface và giả định mọi mode/weaving/version có hành vi y hệt.
5. JDK proxy có thể làm việc với implementation class `final` vì nó **không subclass** class ấy. Tuy nhiên, việc intercept vẫn bị giới hạn bởi những method được expose qua interface.
6. Vấn đề **self-invocation** vẫn tồn tại: một method trên target gọi `this.get(id)` không đi ngược qua JDK proxy.

Ví dụ tiêm dependency:

~~~java
@Service
class ReportService {
    private final ProductService productService; // ổn với JDK proxy

    ReportService(ProductService productService) {
        this.productService = productService;
    }
}
~~~

Đoạn trên là snippet cần interface, annotation import và Spring context. Nếu chuyển constructor parameter thành `ProductServiceImpl` trong khi bean thực tế là JDK proxy, việc inject theo concrete class có thể thất bại vì proxy không phải subtype của class đó.

### Không nên dựa vào tên class runtime

Tên như `jdk.proxy2.$Proxy...` hay các hậu tố generated class thay đổi theo JDK, runtime, Spring version. Dùng:

~~~java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
~~~

Thư viện `org.springframework.aop.support.AopUtils` cung cấp các helper này. Kiểm tra boolean/kiểu phù hợp sẽ vững hơn so với kiểm tra tên class bằng regex.

## 4. Class-based proxy: CGLIB subclass

Khi class-based proxy được chọn, Spring tạo subclass của target class (CGLIB được đóng gói trong `spring-core`). Proxy có thể override những method có thể kế thừa và override, chèn advice rồi delegate tới target khi cần:

~~~text
Caller gọi ProductServiceImpl
          |
          v
ProductServiceImpl$$SpringCGLIB$$... (subclass)
          |
          v
Spring CacheInterceptor
          |
          v
ProductServiceImpl target method (nếu cần chạy)
~~~

Ưu điểm:

- Proxy **là subtype** của implementation, nên caller có thể inject/cast theo concrete type (nếu không có vấn đề khác trong cấu hình).
- Có thể expose những method public trên class mà không nằm trong một business interface.
- Có thể sử dụng cho bean **không implement interface**.

Hạn chế cần nhớ:

- **`final class` không thể được subclass**; vì thế class-based proxy không áp dụng được cho class ấy. Java `record` mặc định là final, cũng không nên chọn làm class chứa các cache-advised business methods cần subclass proxy.
- **`final method` không thể bị override**, nên CGLIB không thể advice method ấy bằng subclass interception.
- **`private method` không thể bị override**, nên không thể được CGLIB advice. Method không nhìn thấy từ subclass (ví dụ package-private ở superclass khác package) cũng có thể không được advice.
- Với module path của Java Platform Module System, subclass proxy có thể gặp giới hạn truy cập package/module và cần cấu hình module phù hợp. Không dùng `--add-opens` tùy tiện như một giải pháp mặc định.
- CGLIB có thể được tạo thông qua Objenesis để tránh gọi constructor target lần thứ hai; không nên viết business logic phụ thuộc số lần constructor được gọi bởi proxy implementation.
- Trong Kotlin, class/method mặc định final; các plugin hỗ trợ “open” cho Spring có thể cần thiết. Nhưng không phải cứ bật `proxyTargetClass=true` là mọi class Kotlin sẽ trở thành proxy hợp lệ.

**CGLIB không phải giải pháp cho self-invocation.** Sau khi một lời gọi đã vào target object, `this.someCacheableMethod()` vẫn là lời gọi nội bộ và có thể bypass proxy advice. Vấn đề thuộc **ranh giới proxy**, không thuộc công nghệ tạo proxy.

### Public/non-public trong caching

Để mã nguồn dễ chuyển đổi giữa JDK/CGLIB và giữa các phiên bản Spring, **ưu tiên cache annotations trên public method** của Spring-managed bean. Một số cơ chế AOP dựa trên subclass có thể chặn method protected/package-visible về mặt bytecode, nhưng điều đó không tự bảo đảm cache annotation sẽ được xử lý trong mọi cấu hình. Method private/final vẫn có hạn chế rõ ràng; khi thực sự cần non-public interception, hãy xác minh chính sách annotation và thử nghiệm thực tế.

## 5. `@EnableCaching(proxyTargetClass = ...)` nghĩa là gì?

Cấu hình Spring Framework (không phụ thuộc Spring Boot):

~~~java
@Configuration
@EnableCaching(proxyTargetClass = false)
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

Đây là cấu hình minh họa cần imports tương ứng. Với `false`, khi bean có interface thích hợp, Spring thường dùng JDK dynamic proxy; khi không có interface, Spring vẫn có thể tạo CGLIB proxy.

Để **ép class-based proxy** trong proxy mode:

~~~java
@Configuration
@EnableCaching(proxyTargetClass = true)
public class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

Đoạn cấu hình trên có cùng tên class chỉ để so sánh **hai lựa chọn độc lập**; trong một ứng dụng bạn chọn cấu hình thích hợp thay vì khai báo hai class cùng tên.

### Hai cờ có tên gần giống nhưng khác hoàn toàn

| Cấu hình | Tác động |
| --- | --- |
| `@EnableCaching(proxyTargetClass=true)` | Chọn class-based proxy cho **caching advice** trong proxy mode |
| `@EnableCaching(mode=AdviceMode.PROXY)` | Chọn caching qua proxy (mặc định) |
| `@EnableCaching(mode=AdviceMode.ASPECTJ)` | Chọn AspectJ weaving, yêu cầu setup weaving và `spring-aspects`; `proxyTargetClass` không còn là cờ có ý nghĩa trong mode này |
| `@Configuration(proxyBeanMethods=false)` | Vô hiệu hóa kiểu proxy của **các lời gọi `@Bean` method trong configuration class**; không phải cờ chọn JDK/CGLIB cho service cache |
| `spring.aop.proxy-target-class=false` của Spring Boot | Tác động tới Spring AOP auto-configuration trong Boot, có thể dẫn tới interface-based proxy khi không bị cấu hình khác ghi đè |

**Tính toàn cục:** `proxyTargetClass=true` không nhất thiết chỉ ảnh hưởng riêng một bean. Spring có thể hợp nhất cấu hình nhiều auto-proxy creator; cấu hình bắt buộc class-based của một nơi có thể ảnh hưởng những bean dùng `@Transactional`, Spring AOP khác trong cùng context. Vì vậy, thay đổi cờ này có thể làm test kiểu proxy và cách inject bean ở chỗ khác thay đổi.

**Spring Boot khác Spring Framework thuần:** Tài liệu Spring Boot AOP ghi rằng auto-configuration của Boot mặc định dùng CGLIB và có thể chuyển về JDK bằng `spring.aop.proxy-target-class=false`. Ngược lại, thuộc tính `proxyTargetClass` mặc định của `@EnableCaching` trong core Spring Framework là `false`. Đừng suy luận loại proxy cuối chỉ từ một giá trị mặc định; hãy kiểm tra property, các advisor đã cấu hình và object nhận được từ context.

**Theo phiên bản:** Spring Framework 7.0 có `@Proxyable` để chọn proxy interface/class tại cấp bean trong những cấu hình hỗ trợ; đây là tính năng riêng theo version, không phải công cụ tương đương với `@EnableCaching(proxyTargetClass=true)` trên tất cả phiên bản Spring.

## 6. Những method nào có thể được cache advice?

| Trường hợp | JDK interface proxy | Class-based proxy |
| --- | --- | --- |
| Public method trên interface và được implementation cache-annotated | Có thể được advice nếu gọi qua proxy | Có thể được advice nếu method không final và cấu hình phù hợp |
| Public method chỉ ở implementation | Không phải method có trên JDK proxy interface | Có thể được advice nếu overridable |
| Private method | Không expose trên interface để invoke qua proxy như business method | Không thể override/advice bằng subclass |
| Final method trên implementation | Có thể được advice qua lời gọi interface proxy, vì advice chạy ngoài target | Không thể override để advice |
| Final class có interface | Có thể proxy interface | Không thể subclass final class |
| Self-invocation từ `this` | Bypass proxy advice | Bypass proxy advice |
| Object do `new` tạo thay vì lấy từ context | Không được Spring bọc proxy | Không được Spring bọc proxy |
| Method trong `@PostConstruct` gọi nội bộ | Không nên dựa vào proxy chưa hoàn tất khởi tạo | Không nên dựa vào proxy chưa hoàn tất khởi tạo |

Cột “có thể” khác với “chắc chắn”: còn cần annotation được phát hiện đúng, bean eligible cho advisor, proxy tồn tại, đúng cache manager/resolver, và lời gọi thực sự đi qua proxy.

**Đặc biệt với final:** câu nói “`final` luôn khiến `@Cacheable` không chạy” là quá rộng. Giới hạn final là vấn đề subclass override của CGLIB. Một JDK proxy có thể intercept lời gọi qua interface trước khi delegate tới target có method final. Tuy nhiên, điều này không phải lý do để xây hệ thống cache dựa vào final implementation; cần kiểm tra proxy thực tế.

## 7. Ví dụ Java 17+ chạy độc lập: hai context, hai proxy type

Ví dụ dưới đây dùng cùng một interface và implementation nhưng chạy trong **hai `AnnotationConfigApplicationContext` độc lập**. Mỗi context có `CacheManager` riêng, tránh ảnh hưởng cấu hình toàn cục. Một `GreetingServiceImpl` có:

- `greet(name)`: có trên interface, được `@Cacheable`.
- `extra(name)`: public method **chỉ có trên implementation**, cũng được `@Cacheable`.

Trong JDK proxy, caller gọi `greet` qua interface; proxy không thể cast thành implementation để gọi `extra`. Trong CGLIB proxy, caller cast sang implementation và gọi được cả hai method; hai lời gọi cùng key chỉ chạy target một lần.

### 7.1. Maven `pom.xml`

Dùng JDK 17+ và Spring Framework 7.0.9; không cần Spring Boot hoặc database.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-proxy-types</artifactId>
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
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 7.2. Tệp `src/main/java/demo/CacheProxyTypesDemo.java`

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

public final class CacheProxyTypesDemo {

    private CacheProxyTypesDemo() {}

    public interface GreetingService {
        String greet(String name);
    }

    public static class GreetingServiceImpl implements GreetingService {
        private int greetLoads;
        private int extraLoads;

        @Override
        @Cacheable(cacheNames = "greetings", key = "#p0")
        public String greet(String name) {
            System.out.println("load greet " + (++greetLoads));
            return "Hello, " + name;
        }

        // Method không có trên GreetingService interface.
        @Cacheable(cacheNames = "extras", key = "#p0")
        public String extra(String name) {
            System.out.println("load extra " + (++extraLoads));
            return "Extra, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(proxyTargetClass = false)
    public static class JdkConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("greetings", "extras");
        }

        @Bean
        GreetingService greetingService() {
            return new GreetingServiceImpl();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching(proxyTargetClass = true)
    public static class ClassConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("greetings", "extras");
        }

        @Bean
        GreetingService greetingService() {
            return new GreetingServiceImpl();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {
            Object bean = context.getBean("greetingService");
            System.out.println(
                    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
            System.out.println(
                    "JDK instanceof impl: "
                    + (bean instanceof GreetingServiceImpl));

            GreetingService service = (GreetingService) bean;
            System.out.println("JDK call 1: " + service.greet("Linh"));
            System.out.println("JDK call 2: " + service.greet("Linh"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(ClassConfig.class)) {
            Object bean = context.getBean("greetingService");
            System.out.println(
                    "CGLIB proxy: " + AopUtils.isCglibProxy(bean));
            System.out.println(
                    "CGLIB instanceof impl: "
                    + (bean instanceof GreetingServiceImpl));

            GreetingServiceImpl service = (GreetingServiceImpl) bean;
            System.out.println("CGLIB call 1: " + service.greet("Linh"));
            System.out.println("CGLIB call 2: " + service.greet("Linh"));
            System.out.println("Extra call 1: " + service.extra("Linh"));
            System.out.println("Extra call 2: " + service.extra("Linh"));
        }
    }
}
~~~

Các class configuration để `proxyBeanMethods=false` nhằm không dùng interception riêng cho lời gọi `@Bean` method; lựa chọn **proxy của cache** chỉ do `@EnableCaching(proxyTargetClass=...)` trong từng context quyết định.

### 7.3. Chạy và kết quả

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheProxyTypesDemo
~~~

Các dòng do chương trình in theo đúng thứ tự (không tính log Maven/framework):

~~~text
JDK proxy: true
JDK instanceof impl: false
load greet 1
JDK call 1: Hello, Linh
JDK call 2: Hello, Linh
CGLIB proxy: true
CGLIB instanceof impl: true
load greet 1
CGLIB call 1: Hello, Linh
CGLIB call 2: Hello, Linh
load extra 1
Extra call 1: Extra, Linh
Extra call 2: Extra, Linh
~~~

**Tại sao output như vậy?**

1. JDK config có `proxyTargetClass=false`, target implements `GreetingService`. Bean là JDK proxy, implement interface nhưng không phải `GreetingServiceImpl`.
2. `greet("Linh")` lần đầu miss và in `load greet 1`, lần hai hit nên không tăng counter.
3. Đóng context JDK và mở context class-based tạo cache/bean mới; counter của target mới lại bắt đầu từ 0.
4. CGLIB config yêu cầu subclass proxy; object là instance của `GreetingServiceImpl`, nên cast sang implementation hợp lệ.
5. `extra("Linh")` là method public, không final và có annotation; CGLIB proxy expose nó và cache hit ở lần thứ hai.

Nếu trong khối JDK cố gọi `((GreetingServiceImpl) bean).extra("Linh")`, chương trình sẽ ném `ClassCastException`. Ví dụ không chủ động ném lỗi này để output ổn định, nhưng bạn có thể kiểm thử có chủ đích.

Ví dụ là một project Maven tự chứa về mặt **source**. Kết quả trên được suy ra từ các cache operations và luồng gọi; khi đưa vào hệ thống thật cần chạy để xác nhận dependency/plugin version và cấu hình runtime.

## 8. Self-invocation: đổi sang CGLIB vẫn không cứu được

Xét:

~~~java
@Service
public class ProductServiceImpl {
    public Product fetchViaHelper(long id) {
        return get(id); // implicit this.get(id)
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product get(long id) {
        return repository.find(id);
    }
}
~~~

Snippet này yêu cầu `Product` và repository. Nếu caller gọi `fetchViaHelper` **qua proxy**, lời gọi đầu có thể đi qua proxy, nhưng lời gọi nội bộ `this.get(id)` do target thực hiện sẽ không vòng ngược lại qua proxy. Vì vậy `@Cacheable` trên `get` không được áp dụng cho lời gọi nội bộ đó; `get` chạy trực tiếp dù cache đã có entry. Điều này đúng về bản chất với cả JDK và CGLIB proxy mode.

Các cách xử lý:

- **Ưu tiên tách bean:** đặt method `get` được cache vào `CachedProductReader`, inject bean đó vào service điều phối và gọi qua reference do Spring quản lý. Không cần thủ thuật proxy internals.
- **Tổ chức lại public API:** caller ngoài bean gọi trực tiếp cached method thông qua proxy.
- **Self-injection hoặc `AopContext.currentProxy()`:** có thể hoạt động trong những điều kiện cụ thể nhưng tạo sự phụ thuộc vào AOP/khả năng expose proxy, dễ gây nhầm; không phải lựa chọn mặc định.
- **AspectJ weaving:** có thể xử lý invocation nội bộ vì dùng bytecode weaving, nhưng cần cấu hình `spring-aspects`, load-time hoặc compile-time weaving; đây là một chiến lược khác hẳn proxyTargetClass.

Tương tự, object được tạo bằng `new ProductServiceImpl()` thay vì lấy từ `ApplicationContext` không tự có Spring caching advice.

## 9. Annotation trên interface hay implementation?

Spring khuyến nghị đặt `@Cacheable`, `@CacheEvict`, `@CachePut` trên **concrete implementation class/method** để tránh các khác biệt về kế thừa annotation Java và cơ chế discovery giữa interface proxy, class proxy và AspectJ.

Ví dụ được ưu tiên:

~~~java
public interface CatalogService {
    Item find(String sku);
}

@Service
public class CatalogServiceImpl implements CatalogService {
    @Override
    @Cacheable(cacheNames = "items", key = "#p0")
    public Item find(String sku) {
        return repository.find(sku);
    }
}
~~~

Đây là snippet chưa có `Item`/repository. Interface mô tả hợp đồng nghiệp vụ; caching là chính sách của implementation. Annotation đặt chỉ ở interface có thể hoạt động trong một vài setup nhưng không nên giả định nguyên vẹn khi đổi proxy type/AspectJ hoặc nâng version. Nếu bắt buộc đặt annotation trên interface, hãy viết test integration cho đúng mode.

## 10. Cấu hình và phiên bản: những “bẫy” khó thấy

### 10.1. Cờ cấu hình có tính toàn cục

Spring có thể hợp nhất nhiều auto-proxy creator; một cấu hình yêu cầu class-based proxy có thể khiến cả bean được `@Transactional` hoặc advisor khác bọc bằng subclass proxy, không chỉ bean có cache annotation. Khi bật `proxyTargetClass=true`, rà soát nơi inject bằng class, test mock, generic interface và các class `final` trước khi coi đây là chỉnh sửa cục bộ.

### 10.2. Spring Boot có thể chọn mặc định khác

Spring Boot auto-configures Spring AOP theo lựa chọn riêng và tài liệu Boot cho biết class-based proxy (CGLIB) là mặc định của AOP auto-configuration; property `spring.aop.proxy-target-class=false` có thể chuyển về JDK. Nếu app đồng thời có `@EnableCaching`, `@EnableAspectJAutoProxy`, transaction advice hoặc cấu hình khác, kết quả phụ thuộc cách chúng được hợp nhất. **Đo kiểu proxy bằng `AopUtils` thay vì đoán dựa vào tên starter.**

### 10.3. Spring Framework 7 và @Proxyable

Spring Framework 7 giới thiệu `@Proxyable` nhằm chọn proxy strategy ở mức bean trong những tình huống hỗ trợ. Đây là khả năng theo version, không áp dụng ngược cho mọi ứng dụng Framework 6. Không dùng `@Proxyable` như lời khuyên mặc định nếu chưa xác định framework đang chạy và các auto-proxy processor liên quan.

### 10.4. Native image và module path

Class-based proxy cần subclass động hoặc proxy metadata được chuẩn bị phù hợp khi AOT/native image. Java module access có thể tạo giới hạn cho việc sinh subclass. Khởi động thành công trên JVM thông thường không đủ để chứng minh tương thích native packaging; hãy test theo đúng chế độ build/deploy.

### 10.5. Tránh tối ưu hóa sớm dựa trên tốc độ proxy

Sự khác biệt hiệu năng giữa JDK proxy và CGLIB không nên là yếu tố duy nhất. Đối với caching, cache hit/miss, serializer, backend/network, transaction và độ nặng của method thường quan trọng hơn. Chọn proxy type chủ yếu theo **hợp đồng method, khả năng inject, hạn chế class và cấu hình AOP**.

## 11. Debug khi @Cacheable không hoạt động

Một quy trình chẩn đoán theo thứ tự:

1. **Có `@EnableCaching` trong đúng application context không?** Annotation đứng một mình không bật caching infrastructure.
2. **Bean có được Spring quản lý không?** Nếu tạo bằng `new`, không có auto-proxy.
3. **Bean có thực sự là proxy không?** Kiểm tra `AopUtils.isAopProxy(bean)`, rồi phân loại `isJdkDynamicProxy`/ `isCglibProxy`.
4. **Đường gọi có đi qua proxy không?** Nếu self-invocation/`this.method()`, hãy refactor.
5. **Với JDK proxy, method có trong interface proxy không?** Nếu chỉ ở implementation, client qua JDK proxy không thể gọi method đó.
6. **Với CGLIB, class/method có `final` hoặc `private` không?** Không thể subclass final class hoặc override private/final method.
7. **Annotation được phát hiện ở target implementation chưa?** Đừng chỉ dựa vào annotation đặt ở interface hoặc method không đủ điều kiện.
8. **`cacheNames`, key, `condition`, `unless`, manager/resolver có đúng không?** Proxy hợp lệ chưa bảo đảm lần gọi thứ hai phải hit nếu key khác hoặc condition không thỏa.
9. **Có advisor khác can thiệp không?** `@Transactional`, `@Async`, security, retry và auto-proxy configuration có thể làm thay đổi loại proxy, order hoặc đường đi.
10. **Test bằng counter.** Gọi cùng một phương thức qua Spring bean hai lần với cùng key và kiểm tra target method được thực thi bao nhiêu lần.

Ví dụ quan sát runtime (snippet cần Spring AOP trên classpath):

~~~java
Object bean = context.getBean("greetingService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
~~~

Không parse tên proxy generated class để chọn xử lý; test theo **API contract và số lần business method chạy** sẽ đáng tin hơn.

## 12. Các lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Nghĩ `proxyTargetClass=false` luôn là JDK | Bean không có interface vẫn thành CGLIB, gây khó hiểu | Kiểm tra interface và loại proxy runtime |
| Inject implementation type khi bean là JDK proxy | Không tương thích kiểu; injection/cast thất bại | Inject qua interface hoặc thiết kế class proxy khi thực sự cần |
| Nghĩ CGLIB proxy chạy được mọi method | Final/private method không thể advice | Dùng public non-final method qua proxy |
| Cho rằng class `final` luôn dùng được với CGLIB | Không tạo được subclass proxy | Thiết kế interface + JDK proxy hoặc bỏ final nếu phù hợp |
| Nghĩ CGLIB xử lý self-invocation | Cache annotation trên method tự gọi bị bypass | Tách bean và gọi qua proxy |
| Đặt cache annotation chỉ trên interface | Kém ổn định qua mode/version | Ưu tiên annotation trên implementation |
| Chỉ test bằng `new ServiceImpl()` | Không có advice dù annotation đúng | Lấy bean từ Spring context |
| Nhầm `@Configuration(proxyBeanMethods=false)` với `proxyTargetClass=false` | Đọc sai cấu hình | Phân biệt proxy cho configuration với AOP service |
| Bật `proxyTargetClass=true` mà không xét advisor khác | Các bean transaction/AOP khác có thể đổi proxy type | Kiểm tra cấu hình hợp nhất và integration tests |
| Không tính đến Spring Boot auto-AOP | Giả định proxy type mặc định sai | Kiểm tra property, context và `AopUtils` |
| Cho rằng cache miss là do loại proxy | Key, TTL, condition, unless, self-invocation cũng gây miss | Đo counter và trace cache operations |

## 13. Checklist thiết kế

Khi quyết định dùng JDK proxy hay class-based proxy cho Spring Cache:

- API nghiệp vụ có interface không? Caller có thể phụ thuộc interface thay vì concrete class không?
- Có public method cần advice nhưng không nằm trong interface? Có đáng đưa method đó vào interface thay vì ép class proxy không?
- Class hoặc method có `final`, `private` hay module access restriction không?
- Có sử dụng `@EnableCaching(proxyTargetClass=...)`, Spring Boot AOP property hoặc các advisor khác với cấu hình proxy type mạnh hơn không?
- Tất cả lời gọi cacheable có đi qua Spring-managed proxy không? Có `this.method()` hoặc `new` làm bypass không?
- `@Cacheable`/ `@CacheEvict` được đặt ở implementation, dùng đúng cache name/key và điều kiện không?
- Code/test có cast/inject implementation class hoặc giả định tên generated proxy không?
- Đã có integration test trong **chính runtime mode** của ứng dụng để xác nhận `AopUtils`, hit/miss, method visibility và self-invocation chưa?

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK dynamic proxy, CGLIB, giới hạn final/private, self-invocation và cấu hình proxy type.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, `proxyTargetClass`, proxy vs AspectJ, annotation discovery và cách kích hoạt caching.
- [Spring Framework — EnableCaching Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/EnableCaching.html): hợp đồng thuộc tính `proxyTargetClass`, `mode`, `order`.
- [Spring Framework — AopUtils Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): các API kiểm tra loại proxy.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): lựa chọn class-based proxy trong Boot và property `spring.aop.proxy-target-class`.

**Kết luận:** JDK proxy đại diện cho **interface**, CGLIB tạo **subclass của implementation**, còn `proxyTargetClass` quyết định ưu tiên chiến lược proxy trong cấu hình tương ứng. Cả hai đều không tự khắc phục self-invocation; để cache chạy đúng, phải gọi qua proxy, chọn method đủ điều kiện và kiểm chứng bằng hành vi runtime.
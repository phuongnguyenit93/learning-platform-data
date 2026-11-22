# Đặt cấu hình Spring Cache trong đúng ApplicationContext

## Mục tiêu của bài học

Một ứng dụng Spring có thể có **một hoặc nhiều `ApplicationContext`**. Khai báo `@Cacheable` trên service là chưa đủ: cơ chế phát hiện annotation và tạo proxy cache phải được bật tại **context sở hữu bean service**. Đây là nguyên nhân điển hình khiến code vẫn chạy và luôn trả kết quả, nhưng phương thức được đánh dấu `@Cacheable` vẫn thực thi ở mọi lần gọi.

Sau bài này, bạn có thể:
- Phân biệt root context và context con của `DispatcherServlet`; hiểu phạm vi của `@EnableCaching`.
- Đặt `@EnableCaching`, `CacheManager` và service đúng chỗ trong Spring Framework hoặc Spring Boot.
- Tự xác minh proxy và hành vi cache bằng ví dụ Java 17+.
- Chẩn đoán tình huống cache không hoạt động khi cấu hình nằm nhầm context.

## 1. Nguyên tắc: cấu hình cache có phạm vi context

Spring Cache xử lý `@Cacheable`, `@CachePut`, `@CacheEvict` và `@Caching` bằng cơ chế advice/AOP. Trong cấu hình thường dùng, `@EnableCaching` đăng ký hạ tầng để Spring xem xét các bean **được tạo và xử lý trong cùng `ApplicationContext`** rồi áp dụng proxy cho phương thức phù hợp.

Không phải mọi ứng dụng đều có cây context. Spring Boot web thông thường thường dùng một application context chứa cả controller, service và infrastructure. Nhưng một ứng dụng Spring MVC truyền thống có thể có hai tầng:

```text
Root WebApplicationContext (PARENT)
  ├─ CatalogService       <-- @Cacheable trên phương thức
  ├─ CatalogRepository
  ├─ CacheConfiguration   <-- @EnableCaching ở đây
  └─ CacheManager
          |
          | Child có thể tra cứu bean của Parent
          v
DispatcherServlet WebApplicationContext (CHILD)
  ├─ CatalogController
  ├─ HandlerMapping
  └─ WebMvcConfig
```

**Điều then chốt:** Bean nằm ở parent có thể được child sử dụng theo cơ chế lookup kế thừa. Tuy nhiên, việc child nhìn thấy bean parent **không đồng nghĩa** hạ tầng tạo proxy của child chạy lại trên các bean đã được tạo ở parent. Một `BeanPostProcessor`/advisor được đăng ký trong child không tự động biến một service của parent thành proxy có cache.

Đặt `@EnableCaching` trong **child** của `DispatcherServlet` mà service sống trong **root** sẽ khiến child xử lý các bean của chính child (thường là controller), còn service ở root có thể vẫn là đối tượng không được tư vấn cache.

Quy tắc định vị:

| Bean/phần tử | Context nên sở hữu trong mô hình MVC hai tầng | Vì sao |
| --- | --- | --- |
| Service có `@Cacheable` | Root | Nghiệp vụ dùng chung cho các servlet. |
| `@EnableCaching` / cấu hình caching | Root | Cho phép xử lý proxy cho service ở root. |
| `CacheManager`, `CacheResolver` phục vụ service root | Root, hoặc context mà hạ tầng service truy cập được | Root không tra cứu bean chỉ tồn tại ở child. |
| Controller, MVC mapping, view resolver | Child `DispatcherServlet` | Hạ tầng web theo servlet. |
| Service chỉ được đăng ký trong child | Child | Nếu thật sự dùng service ở child, phải bật caching tại child tương ứng. |

Đây là hướng dẫn cho mô hình **root/child thông thường**, không phải quy tắc buộc mọi cache nằm ở root. Hãy xác định **context thực sự tạo bean có annotation**, sau đó bật tính năng cache trong chính context đó.

## 2. Những thứ cần có để cache hoạt động

1. **Dependency:** Spring Cache API/AOP phải có trên classpath. Với Spring Boot, `spring-boot-starter-cache` cung cấp thiết lập cơ bản.
2. **Bật xử lý annotation:** Có `@EnableCaching` trong một `@Configuration` được nạp vào đúng context, hoặc cấu hình XML `<cache:annotation-driven/>` trong context tương ứng.
3. **Cache storage:** Có `CacheManager` hoặc `CacheResolver` phù hợp mà cache advice của context đó có thể sử dụng. Spring Boot có thể tự cấu hình provider nếu tính năng caching được bật; Spring Framework thuần thường cần khai báo trực tiếp.
4. **Bean được Spring quản lý:** Service phải do Spring khởi tạo/đăng ký, và được xử lý bởi infrastructure của context đó.
5. **Lời gọi đi qua proxy:** Ở chế độ `proxy` (mặc định), lời gọi từ bean khác đi qua Spring proxy mới được intercept. `this.find(...)` gọi nội bộ trong cùng object không kích hoạt cache.

Một `CacheManager` tồn tại trong ứng dụng **không tự bật** `@Cacheable`. Ngược lại, bật `@EnableCaching` ở một context nhưng đặt cache manager duy nhất trong context **con** có thể làm parent không tìm thấy manager khi tạo hoặc dùng cache advisor.

## 3. Sai ở child, đúng ở root: ví dụ tự chạy với Java 17+

Ví dụ dưới đây tự tạo parent và child bằng `AnnotationConfigApplicationContext`. Ta không cần chạy web server, vì mục tiêu là tái hiện **cùng quy tắc phạm vi context** mà các ứng dụng Spring MVC nhiều context gặp phải.

Dùng Java 17+ và Gradle 8.x. Tạo dự án với cấu trúc:

```text
context-cache-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/cache/ContextPlacementDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'context-cache-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.cache.ContextPlacementDemo'
}
```

Tệp `src/main/java/demo/cache/ContextPlacementDemo.java` (mã đầy đủ, một file):

```java
package demo.cache;

import org.springframework.aop.support.AopUtils;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class ContextPlacementDemo {

    public static void main(String[] args) {
        run("SAI", RootWithoutCaching.class, ChildCachingOnly.class);
        run("DUNG", RootWithCaching.class, ChildWebOnly.class);
    }

    private static void run(String label,
                            Class<?> rootConfig,
                            Class<?> childConfig) {
        try (AnnotationConfigApplicationContext root =
                     new AnnotationConfigApplicationContext(rootConfig);
             AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

            child.setParent(root);
            child.register(childConfig);
            child.refresh();

            DataService service = child.getBean(DataService.class);
            String first = service.find("A");
            String second = service.find("A");

            System.out.printf("%s | proxy=%s | %s | %s | executions=%d%n",
                    label, AopUtils.isAopProxy(service),
                    first, second, service.executions());
        }
    }

    // Bean này sẽ được tạo ở root context trong cả hai kịch bản.
    public static class DataService {
        private int executions;

        @Cacheable(cacheNames = "records")
        public String find(String id) {
            return id + "-load-" + ++executions;
        }

        public int executions() {
            return executions;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ServiceBeans {
        @Bean
        DataService dataService() {
            return new DataService();
        }
    }

    // Kịch bản sai: root tạo service nhưng chưa bật caching.
    @Configuration(proxyBeanMethods = false)
    @Import(ServiceBeans.class)
    public static class RootWithoutCaching {
    }

    // Cache infrastructure ở child không xử lý lại bean của root.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class ChildCachingOnly {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("records");
        }
    }

    // Kịch bản đúng: root có cả service và hạ tầng caching.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    @Import(ServiceBeans.class)
    public static class RootWithCaching {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("records");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildWebOnly {
    }
}
```

Chạy trong thư mục dự án bằng `gradle run --quiet`, hoặc `./gradlew run --quiet` khi đã có Gradle Wrapper (Windows: `.\gradlew.bat run --quiet`). Các dòng do chương trình in ra:

```text
SAI | proxy=false | A-load-1 | A-load-2 | executions=2
DUNG | proxy=true | A-load-1 | A-load-1 | executions=1
```

Phân tích:
- Ở lần `SAI`: `ServiceBeans` được import vào root nên `DataService` cũng do root tạo. `@EnableCaching` chỉ có ở child. Child lấy được bean parent qua `getBean()` nhưng bean đó **không được cache-proxy**; hai lần gọi thật tạo hai chuỗi khác nhau.
- Ở lần `DUNG`: `@EnableCaching` cùng scope với bean service trong root, nên bean được cache-proxy. Lần thứ hai dùng lại cache entry có key `"A"`, phương thức chỉ thực thi một lần.
- Mỗi kịch bản tạo context mới và `ConcurrentMapCacheManager` mới; vì vậy bộ đếm/entry cache không rò giữa hai kịch bản.
- `AopUtils.isAopProxy()` giúp nhận diện proxy nhưng **proxy=true chưa đủ để chứng minh cache chạy đúng** (bean có thể được proxy do advice khác). Cần xác nhận số lần thực thi và dữ liệu trả về như ví dụ.

Đây là mô hình tối giản của vấn đề ApplicationContext; các lớp `RootWithoutCaching` và `ChildCachingOnly` là **cấu hình cố ý sai để so sánh**, không nên sao chép vào hệ thống thực tế.

## 4. Áp dụng cho Spring MVC có root + DispatcherServlet con

Với ứng dụng Spring MVC dùng `AbstractAnnotationConfigDispatcherServletInitializer`, phần root config và servlet config thường được khai báo riêng:

```java
public class ShopInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return new Class<?>[] { RootConfig.class, CacheConfig.class };
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebMvcConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}

@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan("demo.shop.service")
class RootConfig {
}

@Configuration(proxyBeanMethods = false)
@EnableWebMvc
@ComponentScan("demo.shop.web")
class WebMvcConfig {
}
```

Đây là **đoạn minh họa cấu hình**, cần đặt trong dự án Spring MVC có dependency/import và các lớp thật tương ứng; không phải chương trình độc lập. `demo.shop.service` chứa bean service có `@Cacheable("catalog")`. Cấu hình `CacheConfig` được nạp qua `getRootConfigClasses()` nên ở cùng context với service. `WebMvcConfig` có nhiệm vụ MVC ở child.

Nếu chuyển `CacheConfig.class` từ root sang `getServletConfigClasses()` mà không thay đổi nơi tạo service, sẽ phát sinh đúng lỗi phạm vi như ví dụ trước. Khi có nhiều `DispatcherServlet`, đặt service và cache hạ tầng dùng chung ở root giúp tránh tạo nhiều bean/cache độc lập vô ý.

Tương đương với XML, hãy nạp phần sau trong file cấu hình **root context** nếu service ở root:

```xml
<cache:annotation-driven cache-manager="cacheManager"/>
<bean id="cacheManager"
      class="org.springframework.cache.concurrent.ConcurrentMapCacheManager">
    <constructor-arg>
        <list><value>catalog</value></list>
    </constructor-arg>
</bean>
```

Đoạn XML minh họa chỉ là phần nội dung trong file cấu hình có khai báo đúng namespace/schema `cache` và `beans`; nó cần được thêm vào cấu hình root đang sử dụng. Trong Spring Framework, `@EnableCaching` và `<cache:annotation-driven/>` là hai cách khai báo cho cùng mục tiêu bật cache annotation.

## 5. Áp dụng cho Spring Boot: thường một context, vẫn phải chọn đúng scope

Trong ứng dụng Spring Boot servlet thông thường, `@SpringBootApplication` mở context chính và component scan. Khi các controller, service, cấu hình `CacheManager` đều nằm trong context này, vấn đề root/child thường không xuất hiện.

Cách tổ chức dễ kiểm soát:

```java
// demo/shop/ShopApplication.java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}

// demo/shop/config/CacheConfiguration.java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}

// demo/shop/service/CatalogService.java
@Service
public class CatalogService {
    @Cacheable("catalog")
    public String getTitle(long id) {
        return "Item #" + id;
    }
}
```

Đây là **ba file minh họa** (mỗi phần có package/import phù hợp), không phải một file Java có thể chép nguyên xi. Vì cả `config` và `service` nằm dưới package gốc `demo.shop`, chúng được scan vào context của ứng dụng chính. Boot tự cấu hình `CacheManager` nếu chưa có manager/resolver và provider phù hợp; ở đây bean do chúng ta khai báo sẽ thay thế nhu cầu auto-configure tương ứng.

Spring Boot khuyến nghị tách `@EnableCaching` ra một lớp cấu hình riêng thay vì gắn cứng trên main application class: làm vậy dễ kiểm soát phạm vi khi dùng slice test hoặc muốn tắt cache trong một bài kiểm thử.

**Lưu ý package scanning:** Bean `CacheConfiguration` sẽ không tự xuất hiện nếu package chứa nó nằm ngoài vùng component scan và cũng không được `@Import`. Hãy kiểm tra việc nạp configuration thực tế thay vì chỉ kiểm tra file có annotation.

Khi một hệ thống Boot dùng `SpringApplicationBuilder.parent(...).child(...)`, nhiều context riêng, hoặc khởi tạo `DispatcherServlet` với child context tự cấu hình, hãy áp dụng lại quy tắc ở mục 1: xác định context tạo service và cấu hình cache tại đó.

## 6. Phân biệt “đặt đúng context” với các lỗi cấu hình khác

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xác minh |
| --- | --- | --- |
| `@Cacheable` luôn chạy body dù key giống nhau | `@EnableCaching` ở child, service ở parent; hoặc cache chưa bật | Đọc cây context, bean owner, `AopUtils.isAopProxy()`, số lần thực thi |
| Service không tìm thấy `CacheManager` | Manager chỉ khai báo ở child, hoặc thiếu bean tương thích | Kiểm tra bean manager ở cùng context và parent mà advisor tra được |
| Có proxy nhưng cache vẫn không hit | Key khác, `condition`, `unless`, TTL, provider, hoặc gọi sai bean | Log key/cache name và xác minh lần chạy body |
| `this.method()` không cache | Self-invocation không đi qua proxy mặc định | Gọi từ bean khác qua proxy Spring |
| Chỉ controller được cache, service không cache | Bật annotation processing tại servlet child | Chuyển cấu hình cache vào service context |
| Một số endpoint thấy giá trị cũ, số khác không | Context có service/cache khác nhau, cache bị nhân bản hoặc invalidation sai | Kiểm tra identity của service/manager, key và vùng cache |
| Test chạy khác runtime | Test dựng context khác/slice khác production | Xác minh context được load, `@Import` và cấu hình bật cache |
| Nhiều `CacheManager` gây mơ hồ | Không xác định bean mặc định hoặc thiếu resolver | Dùng cấu hình mặc định rõ ràng hay chỉ định `cacheManager` trên operation |

**Root và child là hai chiều tra cứu khác nhau.** Child có thể tham chiếu bean của parent, nhưng parent không tự thấy bean chỉ tồn tại ở child. Nếu bắt buộc dùng nhiều cache manager, xác định chúng thuộc context nào và cách resolve (ví dụ `@Cacheable(cacheManager="...")` hoặc `CachingConfigurer`) một cách chủ ý.

**Đừng lạm dụng `@EnableCaching` ở mọi lớp config.** Điều này không sửa được sai phạm vi nếu bean đã được tạo tại context khác; nó còn làm khó kiểm soát hạ tầng/proxy khi nhiều context cùng có bản sao cấu hình. Cần khai báo ở đúng context sở hữu bean có annotation; chỉ bật tại nhiều context khi thật sự muốn xử lý các bean riêng của từng context.

**Không nhầm proxy với nơi lưu cache.** Proxy là wrapper để can thiệp lời gọi; `CacheManager` quản lý các `Cache`. Đặt manager đúng scope là cần thiết, nhưng manager không thay thế việc bật cache advice tại context tạo bean. Với Redis, các context có thể cùng trỏ tới một Redis server mà vẫn khác nhau về việc proxy có tồn tại hay không.

**Không nhầm scope context với transaction/TTL.** `@EnableCaching` đặt đúng context chỉ giải quyết khả năng annotation được xử lý. TTL, consistency, thời điểm evict và chính sách backend là các quyết định khác.

## 7. Checklist triển khai và kiểm chứng

Trước khi kết luận cache hoạt động, xác minh theo trình tự:

1. **Vẽ hoặc log cây context**: bao nhiêu context được tạo? Context nào là root, context nào là child `DispatcherServlet`?
2. **Xác định chủ sở hữu service**: bean service được đăng ký bằng `@Service`, `@Bean` hay `@Import` ở context nào? Nếu trùng bean name/type giữa parent và child, xác định instance thực tế được controller dùng.
3. **Kiểm tra nơi nạp `@EnableCaching`**: cấu hình phải được đăng ký và xử lý ở đúng service context. Với XML, kiểm tra file chứa `<cache:annotation-driven/>` được nạp vào context nào.
4. **Kiểm tra cache manager/resolver**: cache name tồn tại; bean được lookup được từ cache infrastructure trong context liên quan.
5. **Kiểm tra đường đi lời gọi**: service lấy qua dependency injection từ Spring; method public và được gọi qua proxy, không đi qua `this.method()`.
6. **Đo cache hit/miss**: gọi hai lần cùng key, so sánh số lần body thực thi; kiểm tra thay đổi key và thao tác evict.
7. **Kiểm thử đúng cấu trúc context**: một unit test gọi method trực tiếp hoặc một `@WebMvcTest` chỉ load MVC slice không thể thay thế integration test của service + caching. Dùng context test thật với cấu hình cần thiết.

Bạn có thể thêm log khi debug:

```properties
logging.level.org.springframework.cache=TRACE
logging.level.org.springframework.cache.interceptor=TRACE
```

Các mức log này hỗ trợ quan sát xử lý cache tùy phiên bản/configuration. Không xem log là chứng cứ duy nhất: test quan sát kết quả, call count và proxy thực tế vẫn có giá trị hơn.

Một kiểm tra ngắn trong Spring test (minh họa, cần context và assertions framework của dự án):

```java
DataService service = applicationContext.getBean(DataService.class);
assertThat(AopUtils.isAopProxy(service)).isTrue();

String a = service.find("A");
String b = service.find("A");
assertThat(b).isEqualTo(a);
assertThat(service.executions()).isEqualTo(1);
```

Tất cả phép kiểm tra phải dùng **chính bean lấy từ context đang được kiểm thử**, và mỗi test nên có cache rỗng/được kiểm soát trước khi đo call count.

## 8. Câu hỏi tự kiểm tra

**Q1.** Service có `@Cacheable` nằm ở root; `@EnableCaching` đặt trong `WebMvcConfig` của `DispatcherServlet` child. Dù child inject được service, vì sao cache có thể không chạy?

**Đáp:** Child nhìn thấy bean của parent qua lookup, nhưng hạ tầng xử lý AOP/cache của child không post-process lại bean đã khởi tạo ở parent. Cần bật caching trong context sở hữu service.

**Q2.** Có `CacheManager` ở root, nhưng service cùng context vẫn luôn chạy. Bổ sung manager khác có giải quyết chắc chắn không?

**Đáp:** Không. Cần xác nhận `@EnableCaching` được nạp và method được gọi qua cache proxy, sau đó mới xét cache name/key/provider.

**Q3.** Service chỉ tồn tại trong child, root đã bật `@EnableCaching`. Có tự tạo proxy cache cho service child không?

**Đáp:** Không mặc định: infrastructure root không tự post-process các bean được khởi tạo tại child. Cần bật xử lý cache ở child nếu đó thực sự là nơi service sống.

**Q4.** Spring Boot thường không có cây root/child tường minh; có cần quan tâm phạm vi context?

**Đáp:** Có. Đa số ứng dụng Boot một context chỉ cần một cấu hình caching được scan đúng phạm vi. Nhưng custom parent/child context, test slice, multiple context và package scan sai vẫn gây hiện tượng tương tự.

## 9. Ghi nhớ

- `@EnableCaching` là **cấu hình theo ApplicationContext**, không phải công tắc tự động áp dụng trên toàn bộ mọi context của JVM.
- Hãy đặt cache infrastructure tại **context tạo bean có cache annotations**; trong Spring MVC root/child điển hình, service root thì bật cache tại root.
- Bean ở parent có thể được child dùng, nhưng **post-processor/advisor của child không xử lý hồi tố bean parent**.
- `CacheManager` đúng chỗ, proxy đúng chỗ và lời gọi đi qua proxy là **ba điều kiện cần được kiểm chứng riêng**.
- Với Spring Boot một context, dùng lớp `@Configuration @EnableCaching` riêng, trong phạm vi component scan của ứng dụng.

### Tài liệu tham khảo chính thức

- [Spring Framework – Enabling Caching Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-enable)
- [Spring Framework – Context Hierarchy trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/context-hierarchy.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

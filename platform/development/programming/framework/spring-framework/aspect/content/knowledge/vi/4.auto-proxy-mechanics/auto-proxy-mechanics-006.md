# Thống nhất cấu hình khi nhiều cơ chế Spring cùng yêu cầu proxy

## 1. Tại sao cần thống nhất auto-proxy trong Spring?

Một Spring bean có thể đồng thời chịu tác động của nhiều khả năng dựa trên AOP proxy:
- `@Aspect` với `@Before` hoặc `@Around` để quan sát lời gọi phương thức.
- `@Transactional`, được Spring gắn với `TransactionInterceptor` khi bật transaction management theo `AdviceMode.PROXY`.
- `@Cacheable`, `@CacheEvict` hoặc `@CachePut`, được Spring xử lý bằng cache interceptor khi bật caching theo chế độ proxy.
- Một số khả năng proxy khác, ví dụ `@Async`, có đường đăng ký hạ tầng riêng tùy phiên bản.

Ví dụ một method `placeOrder()` vừa có `@Transactional`, vừa khớp logging aspect. Nếu Spring tạo proxy mà không phối hợp các tính năng, mỗi cấu hình có thể cạnh tranh cách bọc bean, kiểu proxy hoặc vị trí chạy advice.

**Trong Spring Framework 6.x, các cấu hình proxy tiêu chuẩn như `@EnableAspectJAutoProxy`, `@EnableTransactionManagement` và `@EnableCaching` ở `AdviceMode.PROXY` dùng hạ tầng auto-proxy creator có khả năng hợp nhất trong cùng một `ApplicationContext`.** Các cơ chế vẫn giữ advisor riêng nhưng có thể cùng được áp dụng cho Spring proxy của bean. Đặc biệt, yêu cầu `proxyTargetClass=true` từ một cấu hình có thể quyết định kiểu proxy chung, ngay cả khi cấu hình khác chỉ định `false`.

Phạm vi của bài này là **Spring AOP theo proxy và Spring IoC**. Ta sẽ đi từ hạ tầng auto-proxy creator, quy tắc áp dụng tùy chọn, chuỗi advisor, ví dụ có thể chạy, đến cách kiểm tra khi Spring AOP cùng hoạt động với caching, transaction và async.

## 2. Ba thành phần cần phân biệt rõ

### 2.1. Auto-proxy creator: thành phần tạo proxy khi khởi tạo bean

Auto-proxy creator là một loại `BeanPostProcessor`. Khi container tạo Spring bean, nó kiểm tra các advisor phù hợp rồi trả về proxy nếu bean cần được advice. Trong hạ tầng chuẩn, Spring sử dụng tên bean nội bộ `org.springframework.aop.config.internalAutoProxyCreator` để phối hợp các đăng ký auto-proxy.

Các implementation thường gặp:
- `InfrastructureAdvisorAutoProxyCreator` xử lý infrastructure advisors.
- `AspectJAwareAdvisorAutoProxyCreator` bổ sung các quy tắc có liên quan đến AspectJ advisor.
- `AnnotationAwareAspectJAutoProxyCreator` có khả năng nhận diện các bean khai báo `@Aspect` rồi tạo advisor.

Khi một tính năng khác yêu cầu auto-proxy creator có năng lực cao hơn, Spring thực hiện cơ chế **escalation**: dùng implementation đáp ứng yêu cầu cao hơn cho hạ tầng chia sẻ. Vì thế, một auto-proxy creator có thể xử lý cả advisor của Spring transaction/cache và các advisor sinh từ `@Aspect`.

**Auto-proxy creator là bean hạ tầng**, không phải proxy của `ProductService`. Việc có một auto-proxy creator trong context và việc bao nhiêu Spring bean cần proxy là hai câu hỏi khác nhau.

### 2.2. Advisor và interceptor: logic từng tính năng

Một advisor thường liên kết điều kiện áp dụng (pointcut/method matching) với advice/interceptor. Các tính năng vẫn có hành vi độc lập:

| Cơ chế | Kích hoạt | Thành phần AOP tiêu biểu | Ý nghĩa khi method được gọi |
| --- | --- | --- | --- |
| Spring `@AspectJ` | `@EnableAspectJAutoProxy` hoặc AOP auto-configuration tương ứng | Advisor/advice được tạo từ `@Aspect` | Advice chạy khi method match pointcut và đi qua proxy |
| Transaction | `@EnableTransactionManagement` ở `PROXY` | Transaction advisor + `TransactionInterceptor` | Mở/tham gia/kết thúc transaction theo cấu hình |
| Caching | `@EnableCaching` ở `PROXY` | Cache advisor + `CacheInterceptor` | Cache miss gọi tiếp target, cache hit có thể trả luôn kết quả |
| Async trong Spring 6.1 | `@EnableAsync` ở `PROXY` | `AsyncAnnotationBeanPostProcessor` + `AsyncAnnotationAdvisor` | Thực hiện method qua task executor khi lời gọi qua proxy |

Không thể suy ra từ **một auto-proxy creator dùng chung** rằng cả caching, transaction và logging được thực hiện bởi cùng một interceptor. Chúng là các advisor/advice riêng, được chọn khi thích hợp cho method cụ thể.

### 2.3. Proxy thực tế: nơi client gọi method

```text
Một ApplicationContext
   |
   +-- @EnableAspectJAutoProxy --> Spring @Aspect advisors
   +-- @EnableCaching ----------> cache advisor/interceptor
   +-- @EnableTransactionManagement --> transaction advisor/interceptor
   |
   +-- Spring auto-proxy infrastructure dùng chung
          |
          +-- tạo bean OrderService
          +-- tìm các advisor phù hợp với bean/method
          +-- tạo proxy khi có advisor thích hợp
                           |
Client ----> Spring AOP proxy
                 |
                 +-- advice A (nếu match)
                 +-- advice B (nếu match)
                 +-- advice C (nếu match)
                 |
                 +-- target method (nếu chuỗi tiếp tục)
```

Một proxy có thể giữ nhiều advisor, nhưng **không phải mọi advisor đều chạy cho mọi method**. Spring tính chuỗi interceptor dựa trên method hiện được gọi, target class và điều kiện runtime khi cần.

Ngược lại, nếu một bean không khớp advisor nào thì `proxyTargetClass=true` chưa đủ lý do để Spring tạo AOP proxy cho bean ấy.

## 3. Tại sao `proxyTargetClass=true` có tác dụng trên nhiều cơ chế?

### 3.1. Những annotation cùng quyết định cấu hình

Giả sử một context đăng ký:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(proxyTargetClass = true)
@EnableTransactionManagement(proxyTargetClass = false)
public class InfrastructureConfig {
    // Đây chỉ là đoạn minh họa lựa chọn proxy type.
    // Để cache/transaction thật sự hoạt động, cần đăng ký
    // CacheManager và TransactionManager phù hợp.
}
```

Mặc dù AspectJ AOP và transaction đặt `false`, caching đặt `true`. Spring áp dụng **yêu cầu proxy mạnh hơn**, tức class-based proxy, cho việc auto-proxy trong context. `false` nghĩa là không ép proxy theo lớp, chứ không phải yêu cầu tuyệt đối “cấm class-based proxy”.

| `@EnableAspectJAutoProxy` | `@EnableCaching` | `@EnableTransactionManagement` | Khuynh hướng kiểu proxy chung |
| --- | --- | --- | --- |
| `false` | `false` | `false` | JDK proxy khi bean có interface phù hợp; class proxy vẫn có thể cần nếu thiếu interface |
| `true` | `false` | `false` | Class-based proxy khi bean cần được proxy |
| `false` | `true` | `false` | Class-based proxy, kể cả bean được advise bởi aspect |
| `false` | `false` | `true` | Class-based proxy, kể cả bean chỉ có caching hoặc aspect advisor |
| `true` | `true` | `false` | Class-based proxy |
| `false` | `true` | `true` | Class-based proxy |

Bảng áp dụng khi các cấu hình nói trên cùng hoạt động ở **proxy mode và trong cùng context**, trong Spring Framework 6.x. Nếu có hạ tầng proxy tùy chỉnh hoặc framework version khác, cần kiểm tra runtime.

### 3.2. Class-based proxy và interface-based proxy không tương đương

- **JDK dynamic proxy** triển khai interface của target. Khi client lấy bean qua interface thì hợp lý; khi lấy theo lớp triển khai, có thể thất bại vì JDK proxy không là subclass của lớp đó.
- **Class-based proxy (CGLIB)** kế thừa lớp target, do đó thường có thể lấy bằng kiểu class. Tuy nhiên, class `final` không thể subclass để proxy, method `final` không thể override, method `private` không thể advice theo phương thức proxy này.
- **Self-invocation** `this.otherMethod()` trên target vẫn bỏ qua Spring AOP proxy, bất kể JDK hay CGLIB.

Không nên bật class-based proxy toàn cục chỉ để giải quyết một method nội bộ: bản chất self-invocation không được proxy tự động sửa.

### 3.3. `exposeProxy` cũng liên quan hạ tầng, nhưng có mục đích khác

`@EnableAspectJAutoProxy` còn có:

```java
@EnableAspectJAutoProxy(
    proxyTargetClass = true,
    exposeProxy = true
)
```

Khi `exposeProxy=true`, mã đang thực thi trong một lời gọi qua AOP proxy có thể truy cập proxy hiện hành qua `AopContext.currentProxy()`. Đó là cơ chế hỗ trợ đặc biệt, thường thông qua `ThreadLocal`. Nó **không khiến self-invocation đi qua proxy tự động**; lập trình viên phải chủ động thay đổi cách gọi và chấp nhận phụ thuộc Spring AOP.

Các lựa chọn bật thêm khả năng như class-based proxy/expose proxy có thể được tích hợp vào cấu hình auto-proxy chung trong context. Đừng nhầm `exposeProxy` với một lựa chọn thay đổi số lượng aspect bean, phạm vi transaction hay loại cache.

## 4. Unified auto-proxy creator không có nghĩa thứ tự advice được tự giải quyết

Một lời gọi đến `OrderService.place(...)` có thể khớp cả logging, transaction và cache advisor.

```text
Caller
  |
  v
proxy.place(...)
  |
  +-- logging @Around?           (thứ tự phụ thuộc @Order)
  +-- TransactionInterceptor?    (thứ tự phụ thuộc transaction order)
  +-- CacheInterceptor?          (thứ tự phụ thuộc caching order)
  |
  +-- target.place(...)          (chỉ chạy nếu chuỗi được tiếp tục)
```

Nếu `CacheInterceptor` đứng **ngoài** `TransactionInterceptor` và gặp cache hit, nó có thể trả kết quả trước khi đi tới transaction interceptor. Nếu transaction interceptor đứng **ngoài** cache, một transaction vẫn có thể được bắt đầu ngay cả khi cache hit.

Tương tự, một aspect dùng `@Before` đứng ngoài cache interceptor có thể log mọi lời gọi, kể cả cache hit. Nếu advice nằm sau cache interceptor trong chain, cache hit có thể trả kết quả trước khi advice được thực thi.

**Thứ tự annotation trên `@Configuration` không quyết định advice order.** Cần dùng `@Order`/`Ordered` cho aspect và tham số `order` của từng tính năng.

Ví dụ cấu hình precedence:

```java
@Aspect
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceAspect {

    @Before("execution(* com.example.service..*.*(..))")
    public void beforeCall() {
        // Ưu tiên cao, có thể nằm ngoài advisor thấp hơn.
    }
}
```

```java
@EnableCaching(order = Ordered.LOWEST_PRECEDENCE)
```

Mã trên là snippet minh họa (cần import, bean registration và service thật nếu đưa vào project). Advisor có số `order` **nhỏ hơn** thường có precedence cao hơn; advice ở phía ngoài được vào trước và thoát sau khi chuỗi tiếp tục bình thường. Khi nhiều advisor có cùng precedence hoặc có cấu hình đặc biệt, cần xác minh thứ tự thực tế bằng integration test.

### Ba sự thật khác nhau

1. **Auto-proxy creator được thống nhất:** Spring phối hợp hạ tầng để tạo proxy.
2. **Các advisor được tổng hợp:** Một proxy có thể chứa nhiều advisor tương ứng những tính năng khác nhau.
3. **Kết quả invocation phụ thuộc thứ tự:** Advice nào chạy, việc có gọi target không và exception đi theo đường nào còn phụ thuộc pointcut, order và cách interceptor gọi tiếp chain.

Không dùng việc nhìn thấy `AopUtils.isAopProxy(bean) == true` để khẳng định cả ba tính năng đã thực thi đúng.

## 5. Ví dụ chạy được: kết hợp `@Aspect` và `@Cacheable`

Ví dụ này cô lập hai cơ chế Spring thường cùng tạo proxy, dùng **Java 17, Spring Framework 6.1.14 và Gradle**. Không dùng Spring Boot nên ta chủ động chỉ định chính xác các lựa chọn `proxyTargetClass`.

Mục tiêu kiểm tra:
- `@EnableAspectJAutoProxy(proxyTargetClass=false)` không phủ quyết `@EnableCaching(proxyTargetClass=true)`.
- Bean triển khai interface vẫn trở thành **class-based AOP proxy**.
- Aspect logging có precedence cao có thể quan sát hai lời gọi, trong khi cache làm target chạy một lần.

### 5.1. Tạo project

```text
spring-aop-combined/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/combined/
    ├── CatalogApi.java
    ├── CatalogService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-combined'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.combined.DemoApp'
}
```

Ở đây `spring-context` cung cấp `ApplicationContext`, cache API và `ConcurrentMapCacheManager`; `spring-aop` cung cấp proxying; `aspectjweaver` cung cấp các thành phần cần thiết để xử lý biểu thức trong `@Aspect`.

### 5.2. Interface và target

`src/main/java/demo/combined/CatalogApi.java`:

```java
package demo.combined;

public interface CatalogApi {
    String find(String sku);
}
```

`src/main/java/demo/combined/CatalogService.java`:

```java
package demo.combined;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;

public class CatalogService implements CatalogApi {
    private final AtomicInteger calls = new AtomicInteger();

    @Override
    @Cacheable(cacheNames = "catalog")
    public String find(String sku) {
        int count = calls.incrementAndGet();
        System.out.println("target#" + count);
        return "item:" + sku;
    }

    public int targetCallCount() {
        return calls.get();
    }
}
```

`find(...)` trả kết quả cố định theo SKU. Cache manager có thể lưu `"item:sku-7"` sau lần đầu. `targetCallCount()` chỉ đo số lần logic method trong target thực sự chạy.

### 5.3. Aspect có precedence cao

`src/main/java/demo/combined/TraceAspect.java`:

```java
package demo.combined;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

@Aspect
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceAspect {

    @Before("execution(public * demo.combined.CatalogService.find(..))")
    public void beforeFind() {
        System.out.println("aspect:before");
    }
}
```

`@Aspect` khai báo Spring AOP aspect; `@Before` có pointcut chỉ khớp method `CatalogService.find(..)`. `@Order` được cố định để advice đứng phía ngoài cache advice trong ví dụ; ở cache hit, logging vẫn có thể chạy dù target không được gọi.

### 5.4. Một context bật hai cơ chế

`src/main/java/demo/combined/AppConfig.java`:

```java
package demo.combined;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(
    proxyTargetClass = true,
    order = Ordered.LOWEST_PRECEDENCE
)
public class AppConfig {

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

Ba bean được đăng ký tường minh để không bị ảnh hưởng bởi component scanning. `TraceAspect` không cần `@Component` vì đã là một `@Bean`; một lớp chỉ được gắn `@Aspect` sẽ không tự thành Spring bean nếu không được đăng ký.

`@EnableCaching` hoạt động ở proxy mode mặc định, yêu cầu class proxy và đăng ký cache advisor. `@EnableAspectJAutoProxy` bật nhận diện aspect. Tùy chọn `true` của caching thắng lựa chọn `false` của aspect trong hạ tầng auto-proxy chung.

### 5.5. Chạy chương trình

`src/main/java/demo/combined/DemoApp.java`:

```java
package demo.combined;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            CatalogApi byInterface = context.getBean(CatalogApi.class);
            CatalogService byClass = context.getBean(CatalogService.class);

            System.out.println("sameBean=" + (byInterface == byClass));
            System.out.println("isAopProxy=" +
                               AopUtils.isAopProxy(byInterface));
            System.out.println("isClassProxy=" +
                               AopUtils.isCglibProxy(byInterface));

            System.out.println("first=" + byInterface.find("sku-7"));
            System.out.println("second=" + byInterface.find("sku-7"));
            System.out.println("targetCalls=" + byClass.targetCallCount());
        }
    }
}
```

Dùng một Gradle installation có thể chạy project, tại thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu project có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

Các dòng **do chương trình Java in ra** (bỏ qua thông tin build/logging từ công cụ):

```text
sameBean=true
isAopProxy=true
isClassProxy=true
aspect:before
target#1
first=item:sku-7
aspect:before
second=item:sku-7
targetCalls=1
```

Ý nghĩa:
1. `sameBean=true`: lấy theo interface hay class đều trả về đúng một Spring-managed singleton/proxy.
2. `isAopProxy=true`: bean đã được Spring AOP bọc proxy.
3. `isClassProxy=true`: dù aspect khai báo `proxyTargetClass=false`, caching đã yêu cầu `true`.
4. `aspect:before` xuất hiện **hai lần** vì aspect có precedence cao hơn cache advisor, quan sát cả cache hit.
5. `target#1` xuất hiện **một lần**: caching trả kết quả của lời gọi thứ hai từ `ConcurrentMapCacheManager`, không gọi lại method target.
6. `targetCalls=1` chứng thực điều đó. Kiểm tra bộ đếm target khác với việc chỉ kiểm tra hai string trả về bằng nhau.

Đây là ví dụ kiểm chứng cách Spring phối hợp hai cơ chế. Nó không mặc định rằng mọi proxy do người dùng tự tạo đều được hợp nhất.

## 6. Thử biến thể để thấy cấu hình nào quyết định proxy

Dựa trên mã ví dụ, bạn có thể thay **một cấu hình tại một thời điểm**.

### Biến thể A: bỏ class-based request từ caching

Đổi:

```java
@EnableCaching(proxyTargetClass = false)
```

Nếu không có cấu hình khác yêu cầu class-based proxy, `CatalogService` triển khai `CatalogApi` thường được bọc bởi **JDK dynamic proxy**. Khi đó:
- `context.getBean(CatalogApi.class)` vẫn hợp lệ.
- `context.getBean(CatalogService.class)` có thể không lấy được JDK proxy vì proxy không kế thừa `CatalogService`.
- `AopUtils.isJdkDynamicProxy(bean)` là phép kiểm tra đúng, sau khi sửa `DemoApp` để không lookup qua kiểu class.

Không dùng lại chương trình gốc không chỉnh sửa để kết luận JDK proxy “bị lỗi” khi lookup bằng class.

### Biến thể B: chỉ bật `@EnableCaching`

Giữ cache manager và bean nhưng bỏ `@EnableAspectJAutoProxy`. Caching infrastructure vẫn xử lý `@Cacheable`; nó không tự bảo đảm diễn giải bean `@Aspect` thành aspect advisor. Không nên kỳ vọng log `aspect:before` vẫn có nếu không còn hạ tầng xử lý `@AspectJ` nào khác.

### Biến thể C: chỉ bật `@EnableAspectJAutoProxy`

Bỏ `@EnableCaching`. Aspect vẫn có thể advice `find` qua proxy, nhưng annotation `@Cacheable` trên target không tự kích hoạt caching. Hai lần gọi target sẽ tăng bộ đếm lên hai.

### Biến thể D: đổi thứ tự advice

Nếu cache interceptor ở phía ngoài và có cache hit, advice của aspect phía trong **có thể không chạy** lần thứ hai vì cache trả kết quả trước khi tiếp tục chuỗi. Vì thế thứ tự interceptor là hành vi cần thiết kế và kiểm chứng, không phải sự tình cờ của cách Spring hợp nhất hạ tầng.

## 7. Kiểm tra auto-proxy creator và advisor tại runtime

Nếu đang có biến `context` là `AnnotationConfigApplicationContext` trong ví dụ trên, có thể đọc bean hạ tầng (đoạn mã kiểm tra bổ sung, không phải chương trình độc lập):

```java
import org.springframework.aop.config.AopConfigUtils;

String autoProxyCreatorName =
    AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME;
Object creator = context.getBean(autoProxyCreatorName);
System.out.println(creator.getClass().getName());
```

Trong cấu hình có `@AspectJ`, có thể thấy `AnnotationAwareAspectJAutoProxyCreator` vì nó hỗ trợ phát hiện các advisor khai báo từ `@Aspect` ngoài infrastructure advisors. Đây là chi tiết hạ tầng dành cho chẩn đoán, không phải lớp nên phụ thuộc trong business code.

Để xem advisors trên proxy, khi có biến `byInterface`:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

if (byInterface instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Có thể nhìn thấy advisor liên quan tới cache và aspect. Thứ tự được in phản ánh cấu hình proxy thực tế; danh sách không phải hợp đồng API bất biến giữa các phiên bản. Một advisor trong proxy không nhất thiết chạy trên mọi method; pointcut và method matcher tiếp tục quyết định invocation.

**Lưu ý về double-proxy:** Trong hạ tầng Spring chuẩn, thống nhất auto-proxy creator giúp hạn chế việc mỗi khai báo tạo một lớp proxy mới. Nhưng các `BeanPostProcessor` riêng hoặc proxy factory tự viết vẫn có thể tạo thêm một lớp proxy. Đừng lấy `AopUtils.isAopProxy` làm bằng chứng không có proxy lồng; cần inspect `Advised`/target source nếu chẩn đoán tình huống này.

## 8. Thêm `@Transactional`: advisor chung, logic giao dịch độc lập

Khi bật `@EnableTransactionManagement(mode=AdviceMode.PROXY)`, Spring đăng ký advisor cho `@Transactional`.

Ví dụ minh họa cấu hình, **không phải chương trình chạy độc lập** vì thiếu `TransactionManager` và datasource thích hợp:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
@EnableCaching(proxyTargetClass = false)
@EnableTransactionManagement(
    mode = AdviceMode.PROXY,
    proxyTargetClass = true,
    order = 200
)
class ServiceAopConfig {
    // Cần có CacheManager và TransactionManager thật.
}
```

`proxyTargetClass=true` ở transaction áp dụng yêu cầu class-based proxy trong cùng hạ tầng, kể cả bean được advise bởi aspect hoặc cache. Tuy nhiên:
- **Không có transaction manager** thì proxy/advisor không thể tự thực hiện một database transaction hợp lệ.
- `order=200` có ý nghĩa ordering của transaction advisor, không đổi thứ tự tạo Spring bean tùy ý.
- Thứ tự transaction/cache quan trọng: nếu cache interceptor đứng ngoài và trả ở cache hit, phần chuỗi bên trong có thể không mở transaction. Nếu transaction interceptor ở ngoài cache, transaction có thể bắt đầu trước khi caching quyết định kết quả.
- Cache invalidation sau commit thành công là một yêu cầu nghiệp vụ riêng; không được đảm bảo chỉ bởi việc cùng dùng Spring proxy.

**Chế độ AspectJ khác chế độ PROXY:** `@EnableTransactionManagement(mode=AdviceMode.ASPECTJ)` dùng transaction aspect với weaving khi hạ tầng tương ứng được cấu hình; khi đó `proxyTargetClass` của nhánh transaction này không có tác dụng. Không áp dụng quy tắc hợp nhất auto-proxy của `PROXY` để suy diễn rằng weaving cũng đi qua cùng proxy.

Tương tự, `@EnableCaching(mode=AdviceMode.ASPECTJ)` là một mô hình khác, cần `spring-aspects` và cấu hình weaving. Ví dụ trên chỉ dùng proxy mode.

## 9. `@Async` và thay đổi theo phiên bản Spring

Trong **Spring Framework 6.1**, `@EnableAsync` không hoàn toàn là cùng một đường đăng ký auto-proxy creator với `@EnableAspectJAutoProxy`/cache/transaction.

- `@EnableAsync` thường dùng `AsyncAnnotationBeanPostProcessor`.
- Bộ xử lý này có thể thêm `AsyncAnnotationAdvisor` vào **AOP proxy đã có**, hoặc tạo proxy mới khi cần.
- `order` mặc định của post-processor hướng tới việc xử lý sau các post-processor khác để có thể bổ sung advisor vào proxy thay vì bọc lại một lớp mới.
- `@EnableAsync(proxyTargetClass=true)` vẫn có tác động về lựa chọn class-based proxy đối với các bean cần proxy khác trong context theo Javadoc Spring 6.1, nhưng không vì thế mà kết luận **mọi BeanPostProcessor đều chính là một instance auto-proxy creator**.

**Theo tài liệu Spring Framework 7.0**, cơ chế thống nhất global default proxy settings đã được mở rộng cho các proxy processor riêng lẻ, ví dụ `@EnableAsync`. Do đó nếu ứng dụng dùng Spring 7.0, đọc reference/Javadoc của **đúng release** trước khi suy luận hành vi chi tiết giống Spring 6.1.

`@EnableScheduling` lại thiên về đăng ký method chạy theo lịch và không mặc nhiên đồng nghĩa tạo thêm AOP auto-proxy creator cho mọi scheduled method. Tương tự, các cấu hình security hoặc interceptor do người dùng viết có thể dùng cách tích hợp riêng; cần kiểm tra thật trước khi kết luận số lượng proxy.

## 10. Trong Spring Boot, ai quyết định proxy type?

Spring Boot có auto-configuration Spring AOP khi dependency phù hợp được nạp (thường qua `spring-boot-starter-aop`). Ở **Spring Boot 3.3**, class-based proxy thường là mặc định của AOP auto-configuration khi không đổi property:

```properties
spring.aop.proxy-target-class=true
```

Có thể đổi hướng bằng:

```properties
spring.aop.proxy-target-class=false
```

Tuy nhiên, nếu ứng dụng cùng context còn có `@EnableCaching(proxyTargetClass=true)` hay `@EnableTransactionManagement(proxyTargetClass=true)`, yêu cầu class proxy mạnh hơn có thể vẫn chi phối việc auto-proxy. Vì vậy chỉ nhìn một Boot property chưa đủ để kết luận proxy cuối cùng thuộc JDK hay CGLIB.

Ngoài ra, ứng dụng Boot có thể có thêm auto-configured advisors (transaction, cache, security...). Muốn hiểu một method cần xem cả dependency, auto-configurations, context sở hữu bean, advisor và method thật sự được gọi. Khi giải thích behavior nên ghi rõ phiên bản Boot/Spring đang chạy.

## 11. Lỗi phổ biến và cách kiểm chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý/kiểm tra |
| --- | --- | --- |
| `@EnableAspectJAutoProxy(proxyTargetClass=false)` nhưng kết quả vẫn là CGLIB | Caching, transaction hoặc Boot đã yêu cầu `true` | Tập hợp mọi cấu hình proxy của cùng context; dùng `AopUtils.isCglibProxy`. |
| Bean có proxy nhưng `@Before` không chạy | Aspect chưa là bean, AOP chưa bật, pointcut không khớp hoặc lời gọi không qua proxy | Kiểm tra aspect bean, advisor, pointcut và đường gọi. |
| Aspect chạy hai lần, target chỉ chạy một lần | Aspect ngoài caching; cache hit không gọi target | Đây có thể là hành vi đúng, tùy nhu cầu logging. |
| Aspect chỉ chạy lần đầu khi gọi method được cache | Cache interceptor đứng ngoài aspect và trả ở cache hit | Kiểm tra `@Order` và `order` của cache advisor. |
| Lấy bean theo class thất bại | Bean đang có JDK dynamic proxy | Inject interface hoặc cấu hình class-based proxy khi thật sự cần. |
| Transaction không hoạt động dù `@Transactional` hiện diện | Thiếu/sai `TransactionManager`, method không khớp hoặc self-invocation | Kiểm tra manager, advisor, transaction mode và lời gọi qua proxy. |
| Caching không có tác dụng | Chưa bật `@EnableCaching`, thiếu `CacheManager`, self-invocation hoặc method không phù hợp | Xác minh cấu hình cache, key, số lần chạy target. |
| Sau khi bật CGLIB, một bean `final` gặp lỗi | Không tạo được subclass proxy | Thiết kế class có thể proxy hoặc giữ interface-based proxy thích hợp. |
| Cấu hình AOP nằm ở parent mà bean ở child không nhận proxy | Auto-proxy creator là hạ tầng **theo context** | Bật cơ chế ở đúng context tạo bean; kiểm tra bean ownership. |
| Có nhiều proxy lồng | Custom post-processors hoặc cơ chế đặc biệt bọc proxy thêm | Kiểm tra `Advised`, target source và thứ tự BeanPostProcessor. |
| Behavior async khác tài liệu | So sánh nhầm phiên bản hoặc nhầm processor async với auto-proxy creator tiêu chuẩn | Đối chiếu Spring Framework 6.x/7.0 và `AsyncAnnotationBeanPostProcessor`. |

### Quy trình debug gọn nhưng đủ bằng chứng

1. **Context:** Xác định `ApplicationContext` nào tạo bean và nhận các `@Enable...`.
2. **Hạ tầng:** Có `internalAutoProxyCreator` không? Có `AsyncAnnotationBeanPostProcessor` hoặc custom processors khác không?
3. **Proxy:** Spring cấp JDK proxy hay CGLIB? `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`.
4. **Advisor:** Trên proxy có advisor từ `@Aspect`, cache và transaction đúng như dự kiến không?
5. **Order:** Advice nào ở ngoài/trong? Cache hit có dừng chuỗi trước target/transaction không?
6. **Target:** Số lần chạy method nghiệp vụ có phù hợp không? Có self-invocation hoặc method `final`/`private` không?
7. **Phiên bản:** Với Spring 6.x, Spring 7.0 hoặc Boot khác nhau, xác minh defaults và cơ chế processor riêng.

## 12. Kết luận áp dụng

Spring thống nhất các đăng ký **auto-proxy creator tiêu chuẩn trong một context** để nhiều cơ chế dựa trên proxy có thể cùng làm việc với một bean. Việc “thống nhất” có hai kết quả thực tế: hạ tầng đủ khả năng nhận diện các advisor khác nhau và những tùy chọn mạnh như `proxyTargetClass=true` được áp dụng nhất quán.

Tuy nhiên, ba điều phải luôn được tách riêng: **ai tạo proxy**, **advisor nào áp dụng**, và **interceptor chạy theo thứ tự nào**. Việc dùng cùng proxy không thay thế yêu cầu có `CacheManager`, `TransactionManager`, aspect bean hay việc lời gọi đi qua proxy. Thứ tự logging–cache–transaction và đặc thù `@Async` vẫn phải được xác minh theo context và phiên bản Spring cụ thể.

### Tài liệu Spring chính thức

- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): unified auto-proxy creator và class/interface proxy.
- [@AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): bật `@Aspect`-based proxy.
- [Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): precedence của advice.
- [Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@EnableCaching`, proxy mode, order và cache hit.
- [@EnableTransactionManagement Javadoc (6.1.14)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html): transaction advisor, `proxyTargetClass` và `AdviceMode`.
- [@EnableAsync Javadoc (6.1.8)](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): `AsyncAnnotationBeanPostProcessor`, `proxyTargetClass` và thứ tự.
- [AsyncAnnotationBeanPostProcessor Javadoc (6.1.2)](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html): thêm async advisor lên proxy đã có.

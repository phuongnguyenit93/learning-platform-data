# Thứ tự giữa aspect tự viết và advisor hạ tầng Spring

## 1. Câu hỏi trung tâm

Khi một Spring service method vừa khớp `@Aspect` tự viết, vừa có `@Transactional`, `@Cacheable`, Spring Method Security hoặc `@Async`, **advice nào thực thi trước, advice nào thực thi sau và advice nào có thể ngăn method đích chạy?**

Trong **Spring AOP theo mô hình proxy**, nhiều advisor/interceptor có thể cùng tham gia xử lý một lần gọi method. Điều cần phân biệt không chỉ là tên annotation mà là **vị trí của từng advisor trong chuỗi gọi**, thứ tự “đi vào”/“đi ra”, nơi có thể short-circuit, và **cơ chế đặt order của từng infrastructure feature**.

Ví dụ: với custom `@Around` audit bao **ngoài** transaction interceptor, audit có thể ghi log sau khi `proceed()` kết thúc **bao gồm bước commit**. Nhưng với custom aspect đặt **bên trong** transaction interceptor, log “method returned” có thể xuất hiện **trước khi transaction interceptor commit**. Vì vậy hai log “success” ở những vị trí khác nhau **không mang cùng ý nghĩa**.

**Phạm vi bài này:** Spring `@AspectJ`/Spring AOP proxy, `@Order`/`Ordered`, transaction/cache/method-security/async advisors và cách quan sát chính xác thứ tự. Các ví dụ tập trung vào Spring Framework, không đi sâu AspectJ weaving hay lý thuyết AOP chung.

## 2. Bản chất của thứ tự trong Spring AOP

Một Spring-managed service có thể được trả ra dưới dạng proxy. Caller đi qua reference proxy, Spring áp dụng các advisors có thể match vào method execution:

```text
Other Spring bean / caller
         |
         | workService.run("A")
         v
Spring AOP proxy
         |
         +--> Custom @Around audit            (order 10)
         |        |
         |        +--> Spring transaction advice (order 20)
         |                  |
         |                  +--> Custom @Around metric (order 30)
         |                            |
         |                            +--> target.run("A")
         |                            |
         |                            +-- return / throw
         |                  |
         |                  +-- commit / rollback
         |        |
         |        +-- audit exit
         v
Result / exception to caller
```

**Số order nhỏ hơn có precedence cao hơn** theo Spring `Ordered` và `@Order`. Trên đường đi vào method, advisor có precedence cao thường được gọi **trước**. Trên đường đi ra, wrapper có precedence cao kết thúc **sau**, vì nó nằm **ngoài** wrapper thấp hơn.

Nếu mọi interceptor đều cho chain tiếp tục:

```text
Audit.enter    (10)
  Tx.begin     (20)
    Metric.enter (30)
      target.run()
    Metric.exit
  Tx.commit
Audit.exit
```

Với exception khiến Spring transaction mặc định rollback:

```text
Audit.enter
  Tx.begin
    Metric.enter
      target.run() -> throw RuntimeException
    Metric.throw
  Tx.rollback
Audit.throw -> caller
```

Đây là **sơ đồ định hướng**, không phải thứ tự mặc định của mọi dự án. Các giá trị 10/20/30 là cấu hình **được chọn tường minh trong demo**, không phải giá trị Spring tự chọn cho transaction, security hoặc cache.

### Hai phân biệt quyết định

1. **Match hay không match:** pointcut của custom `@Aspect`; annotation `@Transactional`, `@Cacheable`, policy bảo mật; method/proxy eligibility; runtime conditions. Một advisor không match thì `order` của nó không khiến nó xuất hiện.
2. **Sau khi match, ai nằm ngoài ai:** Spring áp precedence/order; nhưng một số infrastructure features dùng cách thêm advisor/BeanPostProcessor riêng và có thể tạo nhiều proxy layers. Không xem mọi cấu hình `order` đều là số trên một danh sách duy nhất.

Một advisor ngoài cùng có thể **không gọi downstream** (`@Around` trả sớm, cache hit, security deny, exception). Như vậy một custom aspect nằm trong chain có thể không thấy invocation dù pointcut của nó phù hợp.

## 3. @Order trên custom aspect: ý nghĩa và giới hạn

Ví dụ:

```java
@Aspect
@Order(10)
public class AuditAspect {
    @Around("execution(public * com.example.work..*Service.*(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit:enter");
        try {
            Object result = pjp.proceed();
            System.out.println("audit:return");
            return result;
        } catch (Throwable error) {
            System.out.println("audit:throw");
            throw error;
        }
    }
}
```

Đây là **mẫu minh họa**, cần imports, Spring bean registration và application context thích hợp. `@Order(10)` đặt precedence cho **aspect bean/advice** do Spring AOP dựng từ class này. Aspect `@Order(30)` khác thường có precedence thấp hơn và sẽ được gọi sau ở chiều vào.

Các quy tắc:

- Spring cho phép dùng `@Order(int)` hoặc implement `org.springframework.core.Ordered` trong aspect.
- **Số nhỏ có precedence cao.** `Ordered.HIGHEST_PRECEDENCE` và `LOWEST_PRECEDENCE` là hai mốc.
- Precedence cao chạy **trước trên đường vào, sau trên đường ra** đối với wrapper theo chuỗi.
- Nếu hai aspects có cùng order và thứ tự rất quan trọng, **đừng trông cậy vào thứ tự bean registration/tên class**.
- `@Order` không làm thay đổi pointcut expression, không khiến `@Aspect` tự thành Spring bean, không sửa self-invocation.
- Nếu nhiều advice **cùng loại trong cùng một `@Aspect`** cùng match, không suy thứ tự Java declaration là cố định. Dùng các aspect classes khác nhau hoặc gom logic cần thứ tự trong một method advice.

**Quan trọng:** precedence trong Spring không có nghĩa “audit luôn nhìn thấy mọi call”. Cache/security/async/transaction advisors khác có thể kết thúc sớm, đổi outcome hoặc thay đổi threading.

## 4. Infrastructure advisor là gì trong bài này?

Nhiều tính năng Spring được triển khai bằng **AOP advisor/interceptor infrastructure** (trong proxy mode). Không nên đồng nhất mọi thứ với class có `@Aspect`:

| Feature | Kích hoạt/configuration điển hình | Advisor/interceptor quan trọng | Ý nghĩa khi cùng tồn tại với custom aspect |
| --- | --- | --- | --- |
| Declarative transaction | `@EnableTransactionManagement` hoặc Spring Boot transaction auto-configuration tương ứng | Transaction advisor/`TransactionInterceptor` | Bắt đầu/tham gia transaction, quyết định commit/rollback theo outcome nó nhìn thấy. |
| Spring caching | `@EnableCaching` hoặc Boot caching configuration khi được enable | Cache advisor/`CacheInterceptor` | Cache hit có thể trả ngay, không gọi target/downstream. |
| Method security | `@EnableMethodSecurity` của Spring Security | Authorization interceptors cho `@PreAuthorize`, `@PostAuthorize`, filter, v.v. | Có thể deny trước method, kiểm tra result sau method, hoặc filter args/result theo policy. |
| Async execution | `@EnableAsync` | `AsyncAnnotationAdvisor`/`AnnotationAsyncExecutionInterceptor`, thường thêm qua `AsyncAnnotationBeanPostProcessor` | Có thể chuyển execution sang executor/thread khác; order có ý nghĩa khác với transaction/cache trong config. |
| Custom `@Aspect` | `@Aspect` + Spring bean + `@EnableAspectJAutoProxy` / Boot AOP | Advisors sinh từ `@Around`, `@Before`, ... | Quan sát hoặc thay call/result; precedence đặt trên aspect bằng `@Order`/`Ordered`. |

**Điều kiện chung:** tính năng phải được enable đúng Spring context, method/annotation đủ điều kiện, lời gọi đi qua Spring proxy. Có `@EnableAspectJAutoProxy` **không tự bật** caching, transaction management hay Spring Method Security. `@Transactional` cũng cần `PlatformTransactionManager` hoặc transactional infrastructure tương ứng. Mỗi feature có yêu cầu của riêng nó.

## 5. Transaction advisor: ví dụ order có thể kiểm soát trực tiếp

Spring Framework `@EnableTransactionManagement` có thuộc tính `order` dành cho **transaction advisor**:

```java
@Configuration
@EnableTransactionManagement(order = 20)
@EnableAspectJAutoProxy(proxyTargetClass = true)
class WorkConfiguration {
    // @Bean PlatformTransactionManager transactionManager() ...
    // @Bean custom @Aspect beans ...
}
```

Đây là đoạn **cấu hình minh họa**, chưa phải project chạy độc lập. Điểm cần nhớ:

- `@EnableTransactionManagement(order=20)` đặt vị trí ưu tiên của **transaction advisor** khi cùng match.
- Mặc định `@EnableTransactionManagement.order` là `Ordered.LOWEST_PRECEDENCE`. Giá trị mặc định không bảo đảm transaction sẽ nằm bên ngoài custom `@Order(10)` hoặc các advisors khác có same precedence; phải xem cụ thể.
- `@Order(10)` trên custom aspect có precedence cao hơn transaction advisor có order 20, **bao ngoài transaction interceptor**.
- `@Order(30)` trên custom aspect nằm bên trong transaction advisor order 20 theo thứ tự tương ứng.
- Transaction semantics/rollback rules vẫn do Spring transaction infrastructure quyết định. `@Order` không tạo database connection hoặc bảo đảm commit thành công.
- Spring `@Transactional` có proxy semantics, không tự áp khi một target gọi `this.innerTransactionalMethod()`.

### Quan sát “sau commit” cho đúng

Giả sử:

```text
@Order(10) Audit.enter
  TransactionInterceptor.begin
    @Order(30) Metrics.enter
      Target returns normally
    @Order(30) Metrics.return   <-- thường trước commit
  TransactionInterceptor.commit
@Order(10) Audit.return        <-- sau khi proceed() qua tx interceptor kết thúc
```

Trong mô hình này, khi `AuditAspect` thực sự **ở ngoài** transaction advisor và `proceed()` đi qua nó, lúc `AuditAspect` nhận normal result thì transaction interceptor phía trong đã xử lý commit/cleanup theo cấu hình. Nhưng không tổng quát hóa thành:

- Mọi `@AfterReturning` trong mọi Spring aspect đều là event **sau commit**;
- Transaction của caller/outer transaction cũng đã commit;
- Các `REQUIRES_NEW`/`REQUIRED`/nested transactions đều có cùng thời điểm;
- Event đang xử lý trên thread khác đã hoàn tất;
- Database/business side effects thực sự đạt mức durability theo mọi storage/configuration.

Nếu cần xử lý **chỉ sau commit thành công** trong transaction phù hợp, sử dụng Spring `TransactionSynchronization` hoặc `@TransactionalEventListener(phase = AFTER_COMMIT)`, với contract và configuration rõ ràng.

### @Transactional method return vẫn có thể bị rollback

Một method có thể return bình thường nhưng transaction interceptor sau đó nhận exception trong commit, hoặc transaction đã được đánh dấu rollback-only và kết thúc bằng `UnexpectedRollbackException`. Nếu metrics aspect **nằm trong** transaction interceptor, nó có thể in `metric:return` trước một rollback/commit failure. Nếu audit aspect **ở ngoài**, nó có thể thấy một exception từ transaction completion thay vì normal return của target.

**Do đó:** cần phân biệt **target returned** và **transactional invocation completed**.

## 6. @EnableCaching.order và nguy cơ cache hit bỏ qua advice

Spring caching cho phép:

```java
@Configuration
@EnableCaching(order = 20)
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

Đây là **đoạn minh họa**, cần import `CacheManager` và `ConcurrentMapCacheManager` cùng các Spring beans thích hợp. `@EnableCaching.order` là order của **cache advisor**; mặc định `Ordered.LOWEST_PRECEDENCE` trong Spring Framework.

Giả sử `CatalogService.find(..)` có `@Cacheable("catalog")` và một custom `@Around`:

| Chuỗi order giả định | Cache miss | Cache hit |
| --- | --- | --- |
| Custom audit **ngoài** cache advisor | Audit.enter → cache → target → cache → audit.exit | Audit.enter → cache trả từ cache → audit.exit; target không chạy. |
| Cache advisor **ngoài** custom audit | Cache → audit.enter → target → audit.exit → cache | Cache trả từ cache; **custom audit không được gọi**. |

**Đây là trường hợp rất quan trọng:** “Không có log audit” không nhất thiết là thiếu pointcut. Cache hit có thể **short-circuit trước khi vào advice** nếu vị trí advisor là như vậy.

Nhưng điều này **không có nghĩa** đặt audit ngoài cache tự động bảo đảm mọi success metric đúng. Khi cache hit, audit có thể đo **proxy request** chứ không đo **target business execution**. Phải đặt tên metric theo đúng đại lượng.

### Caching và transaction cùng dùng LOWEST_PRECEDENCE

Mặc định transaction advisor và caching advisor đều có thể dùng `Ordered.LOWEST_PRECEDENCE`. Nếu nghiệp vụ phụ thuộc ai bao ngoài ai, **không coi tie là thứ tự có hợp đồng**. Hãy cấu hình order có chủ đích và integration test:

- Cache hit có vào transaction không?
- Cache được put/evict trước hay sau outcome nào?
- Nếu commit fail, cache có chứa dữ liệu stale hay không?
- Advisor có thể thay thế return value/exception không?

Các câu hỏi cuối cần xét cache manager, transaction semantics, event handling và feature integration cụ thể; một con số `@Order` không tự giải quyết tính nhất quán DB-cache.

## 7. Spring Security method advisors: không tự gán cùng công thức order

Spring Security Method Security khi được bật bằng `@EnableMethodSecurity` cung cấp **nhiều advisors/interceptors chuyên biệt**, ví dụ `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Chúng có **vị trí mặc định trong chain**, không phải một “SecurityAspect” chung có một số order.

Trong tài liệu Spring Security hiện đại, có ví dụ `@PreFilter` ở precedence 100, `@PreAuthorize` ở 200; các advisors khác có thứ tự tương ứng và có thể chịu cấu hình. Phiên bản/configuration thay đổi thì cần **đọc chính docs của bản Security đang chạy**; đừng lấy số từ một README để suy thành hằng số bất biến cho mọi bản.

`@EnableMethodSecurity(offset = ...)` (ở các bản hỗ trợ) có thể dịch vị trí precedence của các method-security interceptors theo cấu hình, nhưng đây là **quy tắc của Spring Security infrastructure**, không phải lời khuyên tùy tiện thay offset để khắc phục lỗi proxy.

### Security đặt trước hay sau custom @Around?

Giả sử custom `@Around` có precedence cao hơn `@PreAuthorize` advisor:

```text
CustomAround.enter
   SecurityAdvisor checks permission
      -> DENIED (throw)
CustomAround.catch/exit
Caller nhận denial
```

Nếu custom aspect **bỏ qua `proceed()`** và tự trả fallback “ok”, security advisor **bên trong có thể không được thực thi**. Điều này đặc biệt nguy hiểm nếu custom advice được dùng như cache hoặc degradation fallback.

Nếu security advisor bao ngoài custom aspect, authorization có thể deny **trước khi** custom aspect nhận invocation. Việc thiếu audit log ở custom aspect khi deny có thể là expected behavior, không phải security không chạy.

**Đối với security:** thay vì chỉ assert một chuỗi log, test **user không đủ quyền không thể gây side effect**, kể cả với cache hit, fallback, exception, async và các entry paths khác. Không dùng custom aspect thứ tự tùy hứng để thay thế cấu hình method security đúng.

### Post-authorization khác Pre-authorization

`@PostAuthorize` cần nhìn result để kiểm tra policy sau invocation. Vị trí và outcome semantics có thể khác `@PreAuthorize`; vì vậy không kết luận chung “security phải trước target trong mọi trường hợp”. Một method có thể chạy xong rồi bị post-authorization từ chối. Nếu method ghi dữ liệu trước đó, transaction và side effects cần được thiết kế theo security policy thực tế.

## 8. @EnableAsync.order không giống transaction/cache advisor order

**Đây là bẫy Spring-specific dễ gặp.** Với:

```java
@EnableAsync(order = Ordered.LOWEST_PRECEDENCE)
```

Thuộc tính `order` của `@EnableAsync` nói về **thứ tự áp dụng `AsyncAnnotationBeanPostProcessor`**, **không trực tiếp cùng ý nghĩa** với `@EnableTransactionManagement(order=...)` hoặc `@EnableCaching(order=...)`.

Tài liệu Spring mô tả mặc định `LOWEST_PRECEDENCE` để Async post-processor chạy sau các post-processors khác và có thể thêm async advisor vào proxy hiện có thay vì gây double-proxy không cần thiết. Mặt khác, `AsyncAnnotationBeanPostProcessor` có xu hướng **đưa async advisor vào trước các advisors đang có** để chuyển sang async execution sớm trong chain.

Do đó **không làm phép so sánh máy móc**:

```text
@Order(10) của custom aspect
so với
@EnableAsync(order=20)
=> custom aspect chắc chắn nằm ngoài async interceptor
```

Kết luận ấy **không được đảm bảo**, vì hai order values ở đây có thể thuộc **khác cơ chế** (advisor precedence so với BeanPostProcessor order). Khi cần biết code audit đang chạy trên **caller thread hay executor thread**, hãy xem actual proxy/advisor structure và test thread names:

- Caller gọi `@Async` method qua Spring proxy.
- Async interceptor có thể submit phần downstream execution sang executor.
- Aspect nằm ngoài async interception có thể ghi log lúc **submit**, trước task completion.
- Aspect nằm trong async execution có thể ghi log trên worker thread và quan sát target execution tại thời điểm khác.
- `CompletableFuture<T>`/`Future<T>` là handle; một normal return của wrapper không đảm bảo computation hoàn tất thành công.
- `@EnableAsync` cần executor/configuration phù hợp. Self-invocation (`this.asyncMethod()`) vẫn bypass proxy trong mặc định proxy mode.

**Không lấy thứ tự log giữa hai threads làm chứng minh thứ tự advisors của cùng synchronous invocation.** Dùng correlation ID, completion synchronization và thực tế order của proxies.

## 9. Bảng phân biệt nhanh các cơ chế đặt order

| Cấu hình | Điều khiển cái gì? | Default/ngữ nghĩa cần nhớ |
| --- | --- | --- |
| `@Order(10)` trên Spring `@Aspect` | Precedence của aspect/advice trong chain | Số nhỏ precedence cao; vào trước, ra sau. |
| `Ordered.getOrder()` trên aspect | Precedence lấy từ bean instance | Cùng quy tắc số nhỏ hơn ưu tiên hơn. |
| `@EnableTransactionManagement(order=...)` | Order của transaction advisor | Mặc định `LOWEST_PRECEDENCE`. |
| `@EnableCaching(order=...)` | Order của cache advisor | Mặc định `LOWEST_PRECEDENCE`. |
| `@EnableMethodSecurity(offset=...)` | Dịch precedence của nhóm method-security interceptors trong những phiên bản có hỗ trợ | Có nhiều advisors khác nhau; xem bản Spring Security và actual advisor order. |
| `@EnableAsync(order=...)` | Thứ tự áp dụng Async annotation **BeanPostProcessor** | **Không đồng nghĩa** advisor order; async advisor có thể được đưa trước existing advisors. |
| `@Transactional(propagation=...)` | Transaction participation/creation semantics | **Không** phải tham số chọn vị trí AOP advisor. |
| `@Order` trên class service thông thường | Order của bean trong một số Spring collections/processes | Không tự ra lệnh mọi interceptors của service xếp theo số đó. |

Khi có nhiều proxies lồng nhau hoặc post-processors riêng, không ép tất cả order settings thành một phép sort toàn cục. Quan sát actual instance được inject và loại advisor/proxy chain.

## 10. Ví dụ chạy được: custom aspects nằm hai bên transaction advisor

Demo Spring Framework dưới đây **chỉ dùng transaction infrastructure** để minh họa thứ tự một cách có thể lặp lại. Nó không cần database: một `TraceTransactionManager` giả lập ranh giới transaction và **in sự kiện begin/commit/rollback**. Manager này **không quản lý tài nguyên thật** và tuyệt đối **không dùng production**; mục đích là quan sát thứ tự của Spring transaction interceptor.

Cấu hình:

- Custom `OuterAuditAspect`: `@Order(10)`.
- `@EnableTransactionManagement(order=20)`: transaction advisor.
- Custom `InnerMetricAspect`: `@Order(30)`.
- `WorkService` có hai `@Transactional` methods: một return bình thường, một throw `IllegalStateException`.
- Tất cả beans do Spring tạo và method calls đi qua class-based proxy.

Môi trường: **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle. Đây là Spring Framework thuần, không phụ thuộc Boot auto-configuration.

### 10.1. Cấu trúc

```text
spring-advisor-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/advisororder/
    ├── AppConfig.java
    ├── WorkService.java
    ├── OuterAuditAspect.java
    ├── InnerMetricAspect.java
    ├── TraceTransactionManager.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-advisor-order-demo'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.springframework:spring-tx:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.advisororder.Main'
}
```

Spring `spring-tx` cung cấp `@Transactional`, `@EnableTransactionManagement` và transaction interceptor, `spring-context` cung cấp context/Java config. `aspectjweaver` dùng cho Spring `@AspectJ` pointcut parsing, **không** tự bật AspectJ weaving.

### 10.2. Target bean với hai @Transactional methods

**`WorkService.java`**

```java
package com.example.advisororder;

import org.springframework.transaction.annotation.Transactional;

public class WorkService {
    @Transactional
    public String ok(String id) {
        System.out.println("target:ok");
        return "done:" + id;
    }

    @Transactional
    public String fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }
}
```

Target class/methods không final, methods public và không có self-invocation. `@Transactional` ở từng method bảo đảm transaction advisor có lý do match cả hai; custom aspects cũng cùng match.

### 10.3. Transaction manager chỉ ghi sự kiện, không có DB

**`TraceTransactionManager.java`**

```java
package com.example.advisororder;

import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;

public class TraceTransactionManager
        extends AbstractPlatformTransactionManager {

    @Override
    protected Object doGetTransaction() {
        return new Object();
    }

    @Override
    protected void doBegin(
            Object transaction, TransactionDefinition definition) {
        System.out.println("tx:begin");
    }

    @Override
    protected void doCommit(DefaultTransactionStatus status) {
        System.out.println("tx:commit");
    }

    @Override
    protected void doRollback(DefaultTransactionStatus status) {
        System.out.println("tx:rollback");
    }
}
```

`AbstractPlatformTransactionManager` đảm nhiệm flow phân định transaction; bốn hooks được implement để tạo transaction object tối giản và ghi sự kiện.

**Giới hạn có chủ đích:** manager không bind JDBC connection hoặc resource vào thread, không thực hiện database commit/rollback thật, không đại diện cho khả năng rollback của một storage engine. Vì `doGetTransaction()` tạo object mới và không báo một transaction có sẵn, demo chỉ nhắm **mỗi external invocation độc lập**. Không dùng implementation này để xác nhận propagation với DB, nested transactions, isolation, read-only semantics hoặc recovery.

Trong ứng dụng thật dùng `DataSourceTransactionManager`/`JdbcTransactionManager`, `JpaTransactionManager` hoặc manager thích hợp và xác nhận database state.

### 10.4. Audit aspect precedence cao, nằm ngoài transaction

**`OuterAuditAspect.java`**

```java
package com.example.advisororder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAuditAspect {
    @Around("execution(public * com.example.advisororder.WorkService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("audit:enter:" + method);
        try {
            Object result = pjp.proceed();
            System.out.println("audit:return:" + method);
            return result;
        } catch (Throwable error) {
            System.out.println("audit:throw:" + method);
            throw error;
        }
    }
}
```

`@Order(10)` nhỏ hơn transaction advisor order 20: audit enter trước `tx:begin`; khi `proceed()` kết thúc bình thường nó sẽ in `audit:return` sau `tx:commit` trong setup này. `throw error` giữ original exception.

### 10.5. Metrics aspect precedence thấp, nằm trong transaction

**`InnerMetricAspect.java`**

```java
package com.example.advisororder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class InnerMetricAspect {
    @Around("execution(public * com.example.advisororder.WorkService.*(..))")
    public Object metric(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("metric:enter:" + method);
        try {
            Object result = pjp.proceed();
            System.out.println("metric:return:" + method);
            return result;
        } catch (Throwable error) {
            System.out.println("metric:throw:" + method);
            throw error;
        }
    }
}
```

Ở đây, `metric:return` diễn ra **trước `tx:commit`**. Vì thế nếu commit fail, một event “target returned” trong metrics không đủ để kết luận transaction hoàn tất thành công. Aspect này cố ý chỉ quan sát và bảo toàn result/exception, không short-circuit hay retry.

### 10.6. AppConfig: bật cả Spring AOP và transaction management

**`AppConfig.java`**

```java
package com.example.advisororder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
@EnableTransactionManagement(order = 20)
public class AppConfig {
    @Bean
    WorkService workService() {
        return new WorkService();
    }

    @Bean
    OuterAuditAspect outerAuditAspect() {
        return new OuterAuditAspect();
    }

    @Bean
    InnerMetricAspect innerMetricAspect() {
        return new InnerMetricAspect();
    }

    @Bean
    PlatformTransactionManager transactionManager() {
        return new TraceTransactionManager();
    }
}
```

Không cần `@ComponentScan` vì các beans được tạo bằng `@Bean`. Tên `transactionManager` rõ ràng giúp Spring tìm bean manager cho declarative transactions. `@EnableAspectJAutoProxy` và `@EnableTransactionManagement` tham gia hạ tầng proxy/advisor của cùng context; không có lời gọi self-invocation.

### 10.7. Main: quan sát call path thực qua Spring proxy

**`Main.java`**

```java
package com.example.advisororder;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkService service = context.getBean(WorkService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("case=ok");
            System.out.println("result=" + service.ok("A"));

            System.out.println("case=fail");
            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
        }
    }
}
```

Chạy ở root project với JDK 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows).

**Các dòng `System.out` của demo theo thứ tự** (không tính logging ngoài của JVM/Gradle/Spring):

```text
proxy=true
case=ok
audit:enter:ok
tx:begin
metric:enter:ok
target:ok
metric:return:ok
tx:commit
audit:return:ok
result=done:A
case=fail
audit:enter:fail
tx:begin
metric:enter:fail
target:fail
metric:throw:fail
tx:rollback
audit:throw:fail
caught=boom
```

### 10.8. Chứng minh ba vị trí trong một invocation

Trường hợp bình thường:

1. `audit:enter:ok` trước `tx:begin` vì aspect `@Order(10)` nằm **ngoài** transaction advisor order 20.
2. `tx:begin` trước `metric:enter:ok` vì transaction advisor precedence cao hơn metric `@Order(30)`.
3. `metric:enter:ok` trước `target:ok` vì target nằm sâu nhất.
4. `metric:return:ok` sau target nhưng **trước commit hook**: ở thời điểm này transaction interceptor chưa hoàn tất.
5. `tx:commit` in sau khi downstream return bình thường.
6. `audit:return:ok` xuất hiện sau khi transaction interceptor `proceed()` hoàn tất.
7. Caller nhận `result=done:A`.

Trường hợp exception:

1. Vào vẫn là `audit → tx:begin → metric → target`.
2. `target:fail` ném `IllegalStateException`.
3. `metric:throw:fail` thấy exception trước khi transaction interceptor xử lý rollback.
4. `tx:rollback` được gọi do exception runtime (và default rollback rules).
5. `audit:throw:fail` thấy exceptional outcome của transaction-wrapped invocation.
6. Caller catch `IllegalStateException("boom")`.

**Ranh giới của demo:** `tx:commit`/`tx:rollback` là các sự kiện do **dummy transaction manager** in ra, không chứng minh DB đã commit/rollback. Điều minh họa là **ordering thực thi advisor**. Đối với dữ liệu thật, dùng manager thật và integration tests với database.

### 10.9. Nếu bỏ @EnableTransactionManagement(order=20) thì sao?

Mặc định transaction advisor thường dùng `Ordered.LOWEST_PRECEDENCE`. Khi đó `@Order(10)` và `@Order(30)` của hai custom aspects có precedence cao hơn transaction advisor theo numeric order: cả hai có thể **bao ngoài transaction interception**, nên `metric:return` có thể xuất hiện **sau commit hook**, không còn cùng chuỗi như mục 10.7.

Đó là điểm bài học: **không tự suy “transaction luôn bọc mọi custom aspect”**. Nếu thứ tự phải là một phần của contract, cấu hình `order` có chủ đích và test.

Không thay phiên bản `@EnableTransactionManagement(order=20)` trong code demo mà vẫn dùng y nguyên expected stdout; khi thay order cần tính lại và kiểm chứng.

## 11. Cách kiểm tra các advisors thực sự nằm trên proxy

### 11.1. AopUtils chứng minh có proxy, chưa chứng minh order

```java
Object bean = context.getBean("workService");
System.out.println(AopUtils.isAopProxy(bean));
```

Đây là đoạn minh họa dựa vào Spring context của demo. Kết quả true xác nhận bean được proxied nhưng **không chỉ ra** advisor nào đứng trước/đứng sau.

### 11.2. Inspect Advised.getAdvisors()

Nhiều Spring AOP proxies implements `org.springframework.aop.framework.Advised`. Có thể dùng:

```java
Object bean = context.getBean("workService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName()
                + " -> " + advisor.getAdvice().getClass().getName());
    }
}
```

Đây là **đoạn chẩn đoán minh họa**, không thêm vào `Main` nếu muốn giữ stdout ở mục 10.7. `Advised.getAdvisors()` hiển thị advisors của proxy đang inspect; nếu có nested proxies, phải lần theo cấu trúc tương ứng một cách an toàn thay vì suy mọi advisor luôn ở một danh sách.

Lưu ý:

- `getAdvisors()` chỉ cho bạn danh sách thành phần được lắp vào proxy; các pointcut có thể có **runtime matching conditions**.
- Một interceptor có thể short-circuit nên advisor phía trong **không nhận invocation**, dù nó có trong danh sách.
- `Advised` là API infrastructure; không sửa danh sách advisors lúc production chạy chỉ để ép order.
- Một số proxy config bị `frozen`/không cho mutate; đọc để chẩn đoán thường thích hợp hơn can thiệp.
- Bean khác hoặc child `ApplicationContext` có thể dùng advisor infrastructure khác; phải inspect **đúng bean mà caller được inject**.

### 11.3. Dùng event recorder thay println trong test

Có thể thay `System.out` bằng một Spring bean `EventRecorder`:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public java.util.List<String> snapshot() {
        return java.util.List.copyOf(events);
    }
}
```

Đây là **mã minh họa riêng**, muốn tích hợp vào demo phải tạo `@Bean EventRecorder`, inject vào cả hai aspects, target và dummy manager. Thứ tự đồng bộ có thể assert theo `List<String>`; không trộn events từ nhiều threads/request vào cùng một thứ tự toàn cục rồi suy advisor precedence.

## 12. Những lỗi thiết kế thường gặp

### 12.1. “@Order(0) luôn là lớp ngoài mọi thứ”

Sai. Một số advisor infrastructure có `HIGHEST_PRECEDENCE`/numeric order nhỏ hơn 0; async BeanPostProcessor có cơ chế thêm advisor khác; nhiều proxies có thể được lồng. `@Order(0)` không tự bảo đảm custom aspect bao hết Spring Security/cache/transaction ở mọi môi trường.

**Đúng:** dùng order cấu hình thực, inspect advisors/proxies và test.

### 12.2. Dùng transaction order để sửa lỗi self-invocation

`@Transactional` trên `inner()` bị bypass nếu `outer()` trên cùng target gọi `this.inner()`. Đổi `@EnableTransactionManagement(order=5)` không tạo proxy hop. Cần tách collaborator bean và gọi qua injected Spring proxy hoặc chọn operation boundary phù hợp.

### 12.3. Không bật tính năng nhưng mong nó xuất hiện trong chain

`@Aspect` không tự bật `@Transactional`, `@Cacheable`, `@Async` hoặc Method Security. Mỗi feature cần activation, required dependencies và infrastructure beans riêng.

### 12.4. Tưởng @Order điều khiển commit

`@Order` điều khiển tương quan interceptors; commit/rollback còn phụ thuộc transaction semantics, propagation, rollback rules, manager implementation, exception/outcome. Order không thể thay business transaction contract.

### 12.5. Nhầm cache hit với thiếu advice

Khi cache advisor ở ngoài, nó có thể trả từ cache và không cho custom aspect bên trong chạy. Cần đếm proxy invocation, cache hit và target execution **tách riêng** để hiểu metrics.

### 12.6. Security advisor nằm sâu trong @Around short-circuit

Một custom `@Around` trả sớm mà không `proceed()` có thể bỏ qua downstream method security check. Nếu đây không phải behavior có chủ đích, đó là vấn đề bảo mật nghiêm trọng; đừng chọn fallback “ok” cho exception authorization.

### 12.7. @EnableAsync(order=...) bị dùng như @Order(aspect)

Thuộc tính `order` ở `@EnableAsync` là BeanPostProcessor order. So nó trực tiếp với `@Order` trên custom aspect để dự đoán thread thực thi là sai. Kiểm tra `AsyncAnnotationBeanPostProcessor`, proxy chain và behavior thực.

### 12.8. Hai advisors cùng LOWEST_PRECEDENCE

Đừng khẳng định transaction luôn chạy trước cache hoặc ngược lại chỉ từ hai default order values bằng nhau. Khi behavior phụ thuộc order, cấu hình rõ, regression test, kiểm tra context đã kích hoạt đúng hai features.

### 12.9. Gọi getter của advisor là “bằng chứng đã advice”

`getAdvisors()` cho thấy proxy có advisor; không đảm bảo một runtime call match dynamic pointcut hoặc tới được advisor sâu trong chain. Cần event traces kèm method/args/outcome.

### 12.10. Một thành công giả do outer advice nuốt exception

```java
@Around("execution(* com.example.advisororder.WorkService.*(..))")
public Object unsafe(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        return null; // có thể che rollback/security/caching failure
    }
}
```

Đây là **anti-pattern minh họa**, không có trong demo runnable. Nếu inner transaction advisor đã rollback, outer advice trả `null` có thể làm caller tưởng normal result. Nếu nó bao trong transaction, outcome mà transaction advisor nhìn thấy có thể thành normal return. Không suy hệ quả commit một cách tuyệt đối mà phải xét vị trí advisor và test transaction thật.

## 13. Quy trình debug nhanh trên hệ thống Spring thực tế

### Bước 1 — Chốt đúng entry method và call path

Ghi lại Spring bean nào được inject vào caller, method signature, target annotation và nơi lời gọi bắt đầu. Xác nhận không dùng raw object từ `new` hoặc self-invocation.

### Bước 2 — Liệt kê các feature thực sự bật

Xem custom `@Aspect` beans, `@EnableAspectJAutoProxy`/Boot AOP, `@EnableTransactionManagement`, `@EnableCaching`, `@EnableAsync`, `@EnableMethodSecurity` và beans manager/executor/security config tương ứng. Đừng coi annotation trong source là bằng chứng advisor đã được đăng ký.

### Bước 3 — Ghi rõ mỗi cơ chế order

Tạo bảng cho project: aspect `@Order`, transaction advisor `order`, cache advisor `order`, security interceptors/offset, async BeanPostProcessor/advisor placement. Khi có default LOWEST value, đừng kết luận thứ tự tie.

### Bước 4 — Quan sát thứ tự thực tế ở một invocation

Instrument `enter`, `target`, `return/throw`, `commit/rollback` bằng test recorder. Với async, đặt correlation ID và đồng bộ futures khi assert. Không dùng tổng thứ tự logs đa luồng làm một single call chain.

### Bước 5 — Test short-circuit

Kiểm tra cache hit, denied permission, `@Around` skip `proceed()`, exception trong target và exception trong commit. Mỗi nhánh có thể dừng ở advisor khác nhau.

### Bước 6 — Kiểm chứng outcome nghiệp vụ

Nếu cần đảm bảo transaction, nhìn DB state và synchronization callbacks; nếu cần đảm bảo authorization, chứng minh unauthorized caller không gây side effects; nếu cần cache correctness, test stale cache, eviction, concurrent calls.

### Bước 7 — Lock behavior bằng integration test

Viết test chạy đúng Spring/Boot/Security versions và proxy mode production. Tránh hard-code một “thứ tự chung” từ tài liệu vào tất cả dự án không có cùng infrastructure.

## 14. Test case nên có

| Case | Cần assert | Tại sao |
| --- | --- | --- |
| Custom outer aspect, transaction advisor, custom inner aspect | `outer.enter → tx.begin → inner.enter → target → inner.exit → tx.commit → outer.exit` | Xác nhận precedence và nesting. |
| Target throw RuntimeException | Inner throw → rollback → outer throw → caller nhận lỗi | Xác nhận exceptional flow và default rollback behavior. |
| Target return nhưng commit fail | Outer nhìn exception sau tx commit attempt; inner đã ghi return | Tránh nhầm target success với committed transaction. |
| Cache miss | Target chạy, cache populate theo config | Không nhầm cache advisor với custom aspect. |
| Cache hit | Target không chạy; custom aspect outer/inner khác nhau | Đếm đúng proxy calls so với target executions. |
| Method security deny | Target không có side effect ngoài policy | Chứng minh security advisor không bị custom short-circuit bỏ qua. |
| Async completion | Caller thread vs worker thread, future failure | Phân biệt advisor order và BeanPostProcessor/threading. |
| Self-invocation | Inner method advice không tự xuất hiện | Khẳng định Spring proxy boundary. |
| Two aspects same order | Không assert ordering không có contract | Tránh test brittle. |
| JDK vs CGLIB proxy | Method được expose/override được | Không đổ lỗi cho ordering khi interception không xảy ra. |

### Regression test đơn giản cho demo

Một integration test có thể thay console prints bằng recorder và assert ordered events sau khi gọi `ok("A")`:

```java
java.util.List<String> expected = java.util.List.of(
    "audit:enter:ok",
    "tx:begin",
    "metric:enter:ok",
    "target:ok",
    "metric:return:ok",
    "tx:commit",
    "audit:return:ok"
);
```

Đây là **đoạn dữ liệu test minh họa**, cần tích hợp `EventRecorder` vào các components để lấy actual events. Đừng cố assert danh sách này từ `System.out` khi app có logging đa luồng khác xen vào.

Quan trọng hơn, với transaction manager thật, test outcome database/state, không dùng `tx:commit` từ dummy manager để tuyên bố business correctness.

## 15. Spring Boot và việc đặt order đúng phạm vi

Với Spring Boot đã có Spring AOP auto-configuration và các starters phù hợp:

- `@Aspect` tự viết vẫn cần trở thành Spring bean qua `@Component`/`@Bean`.
- `@Order` vẫn dùng để xác định relative precedence giữa custom aspects và advisors khi cùng chain.
- `@Transactional`, `@Cacheable`, `@Async`, method security có những kích hoạt/cấu hình riêng; Boot không tự kích hoạt mọi feature chỉ vì AOP starter xuất hiện.
- Không ép phiên bản Spring Framework trong Boot project trái Boot BOM. Kết quả advisors/proxy có thể chịu ảnh hưởng auto-configuration order và các BeanPostProcessors khác.
- Spring Boot 3.x thường dùng `spring-boot-starter-aop`, Spring Boot 4.x dùng `spring-boot-starter-aspectj` nếu cần starter AspectJ phù hợp. Hai lựa chọn này là **theo major version**, không chép đồng thời.
- `spring.aop.proxy-target-class` ảnh hưởng việc dùng class proxy hay interface proxy. `final` class/method và method interface exposure cần kiểm tra, nhưng chuyển proxy mode **không chữa self-invocation**.
- Với Spring Security, đọc tài liệu tương ứng đúng version của dự án; `@EnableMethodSecurity(offset=...)` là policy order của nhóm Security advisors ở các phiên bản hỗ trợ, không phải “cách bật AOP” chung.

**Điểm quan trọng:** các ví dụ `@EnableTransactionManagement(order=20)`/`@Order(10)`/`@Order(30)` trong README nhằm minh họa một cấu hình cụ thể. Trong production, không sao chép các số ấy mà thiếu kiểm tra tương quan với advisor của thư viện đang dùng.

## 16. Checklist áp dụng

- [ ] Đã xác nhận custom aspects và target beans đều do Spring quản lý, AOP proxy active?
- [ ] Các transaction/cache/security/async features được **enable độc lập** và có manager/executor/config phù hợp?
- [ ] Biết rõ từng `order` thuộc **aspect, advisor hay BeanPostProcessor**?
- [ ] `@Order` trên custom aspects có numeric precedence riêng, không tạo tie với advisor cần ordering?
- [ ] Hiểu rằng số nhỏ ưu tiên cao, **vào trước, ra sau** ở nested interceptor wrappers?
- [ ] Đã đọc default `LOWEST_PRECEDENCE` của transaction/cache thay vì giả sử transaction luôn ngoài?
- [ ] Không so trực tiếp `@EnableAsync.order` với aspect `@Order`?
- [ ] Khi có method security, đã kiểm tra advisors/offset trên Spring Security version thực tế?
- [ ] Không suy normal return của inner aspect tương đương transaction committed?
- [ ] Đã xác định cache hits/security denies có thể short-circuit và bỏ qua advisors sâu trong chain?
- [ ] `@Around` được kiểm tra không tự skip `proceed()` hoặc nuốt security/transaction exceptions ngoài policy?
- [ ] Đã xét self-invocation, object `new`, method `final`, JDK/CGLIB proxy khi missing advice?
- [ ] Chẩn đoán actual `Advised.getAdvisors()`/event recorder thay vì chỉ `AopUtils.isAopProxy=true`?
- [ ] Có integration tests cho success, failure, commit failure, rollback, cache hit, access deny và async completion nếu ứng dụng dùng chúng?
- [ ] Không biến thứ tự log đa luồng thành lời khẳng định về thứ tự advisor trong một invocation?
- [ ] Thay đổi order/configuration được coi là thay đổi behavior có regression tests?

**Ghi nhớ:** Trong Spring AOP, **thứ tự giữa custom `@Aspect` và infrastructure advisors có thể thay đổi điều mà mỗi advice thực sự quan sát**: target return, transaction commit/rollback, cache hit, security deny hay async scheduling. `@Order` số nhỏ có precedence cao, nhưng **không phải mọi cấu hình `order` đều là cùng một loại số advisor**; đặc biệt `@EnableAsync.order` thuộc BeanPostProcessor. Cách đúng là đặt order có chủ đích ở feature hỗ trợ, inspect Spring proxy/advisors, và khóa behavior bằng integration tests.

## Tài liệu chính thức

- [Spring Framework 6.2 — Advice Ordering trong @AspectJ](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/applying-more-than-just-tx-advice.html)
- [Spring Framework 6.2 — @Transactional: proxy mode, order và rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — Annotation-driven Caching: @EnableCaching và advisor order](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework 6.2 — AsyncAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html)
- [Spring Framework 6.2 — @EnableAsync và BeanPostProcessor order](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Security — Method Security: advisor ordering và offset](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)

# Kiểm tra tác động của self-invocation tới transaction, cache và validation

## 1. Vấn đề: có annotation nhưng hành vi runtime lại không như mong đợi

Trong một ứng dụng Spring Boot, bạn có thể gặp ba biểu hiện khó hiểu:

- Method gắn `@Transactional` ném `RuntimeException` nhưng INSERT trước đó **vẫn được commit**.
- Method gắn `@Cacheable` bị gọi đi gọi lại và phần tính toán đắt đỏ vẫn chạy mỗi lần.
- Method gắn `@Validated` và constraint `@NotBlank` nhận chuỗi rỗng mà **không ném lỗi**, trong khi cùng method được gọi từ một Spring bean khác lại ném `ConstraintViolationException`.

Một nguyên nhân quan trọng là **self-invocation**: một method của target bean gọi method khác **trên chính instance đó** bằng `this.method()` hoặc gọi không ghi `this`. Khi ứng dụng dùng Spring AOP theo **proxy mode** mặc định, interceptor chỉ có cơ hội chạy với lời gọi **đi qua proxy**. Đường gọi trực tiếp bên trong target bỏ qua interceptor.

Ví dụ:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        this.saveAudit();  // Self-invocation: không qua Spring proxy
    }

    @Transactional
    public void saveAudit() {
        // JDBC write tại đây không tự được bọc transaction
        // chỉ vì có annotation khi gọi bằng this.saveAudit().
    }
}
~~~

Nhìn source, nhiều người tưởng `@Transactional` luôn có hiệu lực. Thực tế, annotation là **metadata** để transaction advice thực thi **ở nơi proxy intercept được call**. Nó không tự rewrite mọi lời gọi Java trong class.

Bài học này thuộc nhóm **Tích hợp bổ sung** của Spring Boot Testing. Trọng tâm là viết **tests phân biệt được** lời gọi trực tiếp, self-invocation và gọi qua bean proxy, đồng thời chứng minh ảnh hưởng cụ thể tới **transaction, cache và method validation**.

### Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Giải thích Spring AOP proxy, target object, advice và self-invocation một cách chính xác.
2. Biết lời gọi nào đi qua proxy, lời gọi nào bypass proxy.
3. Kiểm bằng database thật rằng `@Transactional` có/không rollback khi method được gọi từ bên ngoài so với `this.method()`.
4. Kiểm `Propagation.REQUIRES_NEW` bị bỏ qua khi self-invocation dù outer method **đã có transaction**.
5. Kiểm `@Cacheable` hit/miss bằng counter và `CacheManager`, tránh kết luận từ giá trị trả về giống nhau.
6. Kiểm service method validation qua `@Validated` và Jakarta Bean Validation constraints ở parameter **và return value**.
7. So sánh giải pháp tách Spring bean với `TransactionTemplate`, `CacheManager`/programmatic validation, self-injection và AspectJ weaving.
8. Tránh false positive do `@Transactional` trên chính test method hoặc do `@Mock` không có proxy thật.
9. Biết giới hạn của `@WebMvcTest` và validation tích hợp Spring MVC 6.1+ so với method validation dựa trên proxy ở service.
10. Chạy dự án mẫu **Java 17 / Spring Boot 3.5.16 / Maven / JDBC / H2 / Cache / Hibernate Validator / JUnit 5** với các tests kiểm kết quả thực.
11. Không áp dụng kết luận quá rộng: direct call có thể **vẫn nằm trong transaction đã được mở từ outer method**, nhưng **annotation trên inner method không được xử lý riêng**.
12. Chọn đúng phạm vi kiểm thử: unit business logic, proxy integration test, database transaction và web security/validation contract.

## 2. Spring AOP proxy thực sự hoạt động thế nào?

### 2.1. Target và proxy

Khi một bean có advice từ `@Transactional`, `@Cacheable` hoặc `@Validated`, Spring có thể cung cấp một proxy cho các bean/caller khác dùng:

~~~text
Controller / Service B / JUnit @Autowired
                 |
                 v
        Spring-managed proxy
          |   |   |
          |   |   +-- validation advice
          |   +------ cache advice
          +---------- transaction advice
                 |
                 v
            Target object
                 |
                 +-- this.innerMethod() ----> Target object trực tiếp
                                                  |
                                                  +-- advice không chạy lại
~~~

Trong proxy mode:
- Caller gọi `springBean.innerMethod()` → proxy intercept method.
- Target đang thực thi `outerMethod()` rồi gọi `this.innerMethod()` → lời gọi **không vòng trở lại proxy**.
- Dùng `innerMethod()` không ghi `this` vẫn là self-invocation.
- Đưa method sang **Spring bean khác** rồi inject bean ấy giúp call đi qua proxy của bean được gọi.

Spring AOP thông dụng có thể dùng **JDK dynamic proxy** (thông qua interfaces) hoặc **CGLIB class-based proxy**. Cả hai tuân theo giới hạn self-invocation trong Spring AOP proxy mode; chuyển từ JDK proxy sang CGLIB **không tự chữa** self-invocation.

### 2.2. Ví dụ minh họa bằng call graph

~~~text
Client -> proxy(A) -> target(A).outer()
                          |
                          +-- this.inner() -> target(A).inner() [bypass]

Client -> proxy(B).delegate()
                    |
                    +-- proxy(A).inner() -> advice -> target(A).inner()
~~~

**Không phải** “Spring bỏ qua toàn bộ logic”. Inner Java method **vẫn chạy**; chỉ các cross-cutting interceptors (transaction/caching/validation) có thể **không** chạy.

### 2.3. Gọi một method từ constructor hoặc @PostConstruct

Ngay cả khi bean sau khởi tạo sẽ có proxy, một lời gọi annotation-protected method từ constructor hoặc `@PostConstruct` của chính target không nên dựa vào proxy. Trong quá trình khởi tạo, proxy có thể chưa sẵn sàng hoặc lời gọi là local. Với startup work cần transaction/caching, hãy tách initialization orchestration sang bean khác có lifecycle thích hợp, dùng `ApplicationRunner`/`ApplicationReadyEvent` hoặc một after-start mechanism được kiểm soát; vẫn phải đi qua proxy.

### 2.4. Không phải mọi annotation đều dựa proxy

Một số annotation hoạt động qua cơ chế khác (MVC argument binding/validation, Spring configuration class enhancement, ORM/JPA mapping, compile-time processing, AspectJ weaving). Bài này nói về **Spring AOP proxy-based interception**. Không nên học một quy tắc “mọi annotation self-invocation đều vô hiệu” rồi áp bừa.

## 3. Self-invocation và @Transactional

### 3.1. Sai lầm phổ biến: inner method mở transaction

~~~java
@Service
class BillingService {

    private final JdbcTemplate jdbc;

    BillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void bill() {
        createReceipt();   // tự gọi target method
    }

    @Transactional
    public void createReceipt() {
        jdbc.update("insert into receipts (id) values (?)", 42);
        throw new IllegalStateException("failed");
    }
}
~~~

Đây là snippet kiến trúc, chưa có toàn bộ class/schema để chạy độc lập. Khi `bill()` **không** transactional và tự gọi `createReceipt()`, transaction advice gắn trên `createReceipt()` không chạy. Với JDBC connection auto-commit, INSERT có thể đã commit khi exception xảy ra. Nếu caller bên ngoài gọi `billingService.createReceipt()` qua proxy thì transaction được mở và exception unchecked thường khiến rollback.

**Cảnh báo:** Spring Data repository methods nhiều khi tự có `@Transactional`. Nếu ví dụ dùng `repository.save(...)` và kết luận rằng self-invocation đã được transaction từ kết quả rollback, có thể bạn đang đo **transaction của repository** chứ không phải transaction của service. Lab dùng `JdbcTemplate` trực tiếp cùng auto-commit để ranh giới rõ.

### 3.2. Kiểm transaction đang active

Spring cung cấp:

~~~java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();
~~~

Snippet cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. Giá trị `true` có nghĩa thread hiện có transaction resource đang active theo Spring; không đủ để chứng minh đúng **propagation**, **isolation** hoặc rollback semantics. Muốn kiểm transaction thật, vẫn cần lỗi có chủ đích + database readback sau completion.

### 3.3. Outer đã @Transactional: nuance quan trọng

~~~java
@Transactional
public void outer() {
    this.innerRequiresNew();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void innerRequiresNew() {
    // ...
}
~~~

Nếu `outer()` được caller gọi qua proxy thì outer transaction **có thật**. Nhưng `this.innerRequiresNew()` bypass proxy, nên annotation `REQUIRES_NEW` trên inner **không có hiệu lực riêng**. Inner code **vẫn chạy trong outer transaction đang active** (vì cùng thread), không tạo một transaction mới. Do đó:
- Nếu inner ném exception và outer **catch** exception, outer có thể vẫn commit cả writes của inner.
- Nếu inner được gọi qua một **bean proxy khác**, `REQUIRES_NEW` mở transaction riêng; exception unchecked làm rollback transaction inner, và outer có thể catch rồi commit phần của mình.
- Đừng phát biểu quá rộng rằng “self-invocation luôn không có transaction”. Chính xác là **advice trên method tự được gọi không được áp dụng**; transaction bao quanh từ caller có thể vẫn active.

Đây là một tình huống quan trọng cần test riêng, không chỉ kiểm `isActualTransactionActive()`.

### 3.4. Các tham số @Transactional có thể bị bỏ qua

Nếu self-invocation, những cấu hình chỉ gắn trên inner method có thể không được thực thi:
- `propagation = REQUIRES_NEW`, `MANDATORY`, `NEVER`.
- `isolation = SERIALIZABLE`.
- `timeout = ...`.
- `readOnly = true`.
- `rollbackFor = ...`.
- Qualifier chỉ transaction manager cụ thể.

Không tự kết luận value nào áp dụng nếu call không qua proxy. Test đúng bằng database và transaction behavior thực tế, không chỉ reflection thấy annotation.

### 3.5. Rollback rules vẫn quan trọng

Khi transaction advice **được chạy**, Spring theo mặc định rollback cho `RuntimeException` và `Error`. Checked exceptions có thể commit nếu không cấu hình `rollbackFor` hoặc default policy khác. Nếu exception được catch bên trong method mà không đánh dấu rollback-only, transaction có thể commit. Các vấn đề này **khác** self-invocation nhưng thường cùng gây symptom “không rollback”.

## 4. Self-invocation và @Cacheable

### 4.1. Cache interceptor cũng nằm ở proxy

~~~java
@Service
class PriceService {

    @Cacheable(cacheNames = "quotes", key = "#p0")
    public int quote(int productId) {
        return expensiveLookup(productId);
    }

    public int quoteTwice(int productId) {
        return quote(productId) + quote(productId);
    }
}
~~~

Nếu gọi `priceService.quote(7)` qua proxy hai lần với cache key giống nhau, lần hai có thể trả value từ cache. Nhưng `priceService.quoteTwice(7)` đi vào target rồi gọi `this.quote(7)` hai lần: cả hai bypass cache advice, nên `expensiveLookup` chạy hai lần.

Cả hai đường có thể trả **cùng giá trị**. Vì thế test chỉ assert result là chưa đủ. Phải kiểm:
- Số lần actual computation/DB query/external call.
- Cache entry có được tạo không.
- Kết quả khi cache cleared/evicted.
- Giá trị key và condition/unless của annotation.

### 4.2. @CachePut và @CacheEvict cũng chịu ảnh hưởng

Spring Cache annotations thường được áp qua caching interceptor:
- `@Cacheable`: tìm trong cache và có thể skip method body.
- `@CachePut`: chạy method và update cache.
- `@CacheEvict`: xóa cache entry theo key hoặc allEntries.
- `@Caching`: tổ hợp operations.

Nếu một method gọi `this.evict(...)` hoặc `this.refresh(...)`, lời gọi có thể bỏ qua cache advice. Hệ quả có thể **nguy hiểm hơn việc thiếu cache hit**: dữ liệu stale không bị evict, hoặc cache không được cập nhật khi business state đổi.

### 4.3. Cache key phải được định nghĩa

~~~java
@Cacheable(cacheNames = "numbers", key = "#p0")
public int compute(int number) {
    return number * 10;
}
~~~

`#p0` tham chiếu tham số đầu tiên, không phụ thuộc khả năng đọc tên parameter `number`. Với key dựa user/tenant, method signature hoặc cache key phải chứa đủ dimensions. Một cache hit với wrong tenant không phải thành công.

### 4.4. TTL, eviction và test isolation

Một test dùng `ConcurrentMapCacheManager` không có TTL mặc định. Khi dùng Caffeine/Redis/Ehcache thực, cần kiểm expiration/serialization/eviction theo provider. Unit cache test tốt nhất có cache manager riêng hoặc clear cache trước mỗi method; tránh cache từ test trước tạo PASS giả.

### 4.5. Cache inside transaction

Khi cùng method có `@Transactional` và `@Cacheable`, thứ tự advice và cache transaction-awareness có thể ảnh hưởng thời điểm populate/evict. Không suy mọi cache update tự rollback với DB transaction: memory/Redis cache không phải resource transactional giống JDBC theo mặc định. Bài lab **tách method cache và method transaction**, để chỉ đo self-invocation cho từng concern; production cần test thêm consistency after rollback, update/eviction và advice ordering.

## 5. Self-invocation và method validation

### 5.1. Điều kiện để service method validation hoạt động

Với Spring Boot 3.5:
- Có Bean Validation provider (thường từ `spring-boot-starter-validation`).
- Service class được Spring quản lý.
- Class có `@Validated` ở type level.
- Method có Jakarta constraints trên arguments/return value như `@NotBlank`, `@NotNull`, `@Positive` hoặc cascaded validation theo setup.
- Lời gọi phải đi qua proxy của method validation infrastructure (thường `MethodValidationPostProcessor`).

Ví dụ:

~~~java
@Service
@Validated
public class ProductService {

    public String placeFromBatch(String code) {
        return this.place(code); // bypass validation advice
    }

    public String place(@NotBlank String code) {
        return code.strip();
    }
}
~~~

Trong proxy mode, `productService.place(" ")` từ caller bên ngoài thường bị reject bởi Jakarta `ConstraintViolationException`. Nhưng `productService.placeFromBatch(" ")` tự gọi `place`, nên interceptor validation cho `place` **không chạy**. Body vẫn chạy và trả chuỗi rỗng. Đó là lỗi contract dễ lọt qua khi test chỉ gọi public facade.

### 5.2. Parameter validation và return value validation

Method validation có thể kiểm:
- **Parameters**: `create(@NotBlank String code)`.
- **Return value**: `@NotBlank String create(...)` không được trả blank.
- Constraint groups khi `@Validated(SomeGroup.class)`.
- Cascaded object validation khi dùng `@Valid` ở vị trí thích hợp.

Khi self-invocation bypass interceptor, cả parameter và return value validation trên method nội bộ đều có thể bị bỏ qua. Lab có test **cả hai**.

### 5.3. @Valid không thay thế @Validated proxy

`@Valid` là marker cho cascaded validation khi một validator thực thi; nó **không tự tạo một AOP proxy** để kiểm mọi self-call. `@Validated` ở class cùng Bean Validation provider giúp Spring đăng ký method validation proxy. Cần xác định đúng validation boundary và không tin annotation như một lời hứa compiler-enforced.

### 5.4. Spring MVC controller validation không hoàn toàn cùng cơ chế

Spring MVC 6.1+ có hỗ trợ **built-in method validation cho controller handler methods** trong luồng web, có trường hợp không cần AOP proxy `@Validated` ở controller và còn khuyến nghị bỏ class-level `@Validated` nếu muốn dùng built-in MVC method validation. Vì thế:
- Đừng tự động suy lỗi self-invocation service tương đương lỗi `@RequestBody`/`@RequestParam` validation của DispatcherServlet.
- Controller được MVC gọi qua handler adapter và có exception handling riêng.
- Khi test **service** dùng `@Validated` AOP, phải gọi bean qua proxy.
- Với controller HTTP contract, kiểm bằng MockMvc/filter/handler invocation thật, không chỉ gọi controller như POJO.

### 5.5. Lỗi nhận được có thể tùy cấu hình

Mặc định `MethodValidationPostProcessor` thường ném `jakarta.validation.ConstraintViolationException`. Nếu cấu hình adapt violations, Spring có thể ném `MethodValidationException`. MVC built-in validation lại có kiểu exception HTTP riêng (ví dụ `HandlerMethodValidationException`). Test nên xác định **layer và configuration thực**, không hard-code một exception type từ layer khác.

## 6. Ma trận các lời gọi

| Lời gọi | Transaction annotation trên inner | @Cacheable trên inner | @Validated constraint trên inner |
| --- | --- | --- | --- |
| `bean.inner()` từ caller bên ngoài qua proxy | Có cơ hội chạy | Có cơ hội chạy | Có cơ hội chạy |
| `this.inner()` trong cùng target | **Bypass advice mới** | **Bypass cache advice** | **Bypass validation advice** |
| `inner()` không ghi `this` trong target | Tương tự self-call | Tương tự | Tương tự |
| `otherBean.inner()` (otherBean là Spring proxy) | Có | Có | Có |
| `new Service().inner()` | Không có Spring proxy | Không có Spring cache proxy | Không có Spring method validation proxy |
| `@PostConstruct` tự gọi inner | Không nên dựa vào proxy | Không nên dựa vào proxy | Không nên dựa vào proxy |
| Outer method đã mở transaction và self-call inner | Inner tham gia **outer transaction có sẵn**; metadata inner bị bỏ qua | Cache advice inner bỏ qua | Validation advice inner bỏ qua |
| AspectJ weaving được cấu hình đúng | Có thể intercept self-call | Có thể intercept self-call | **Không mặc định áp dụng cho Spring method-validation advisor** |

Đối với validation, đừng tuyên bố chỉ bật AspectJ transaction/cache sẽ tự làm method validation intercept local calls; đó là một infrastructure concern riêng và cần kiểm advisor/weaving integration tương ứng.

## 7. Dự án runnable: Spring Boot 3.5.16 + JDBC/H2 + Cache + Validation

### 7.1. Kịch bản kỹ thuật

Một Spring service `BoundaryService` có:
1. `@Transactional insertThenFail`: INSERT audit row rồi throw unchecked exception.
2. `selfInsertThenFail`: gọi `this.insertThenFail`, **không đi qua transaction interceptor**.
3. `@Transactional isTransactionActive` và `selfTransactionActive`: quan sát boundary.
4. `@Cacheable compute`: tăng AtomicInteger mỗi lần tính thật.
5. `selfComputeTwice`: gọi compute hai lần qua this, bỏ cache.
6. `normalize(@NotBlank String)`: validated parameter.
7. `@NotBlank invalidReturn`: validated return.
8. `selfNormalize`/`selfInvalidReturn`: hai self-calls bypass validation.
9. `@Transactional outerSelfRequiresNew` gọi `this.innerRequiresNewAndFail` rồi catch, chứng minh `REQUIRES_NEW` bị bỏ qua.

Một `CrossBeanFacade` gọi `BoundaryService` qua dependency injection để **khôi phục proxy interception**. Một `RequiresNewWorker` minh họa inner transaction thật khi gọi từ bean khác. JUnit integration test đọc H2 **sau lời gọi** để chứng minh commit/rollback, chứ không chỉ kiểm mock.

### 7.2. Sơ đồ file

~~~text
self-invocation-lab/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── schema.sql
├── src/main/java/com/example/selfinvoke/
│   ├── SelfInvocationApplication.java
│   ├── BoundaryService.java
│   ├── RequiresNewWorker.java
│   └── CrossBeanFacade.java
└── src/test/java/com/example/selfinvoke/
    └── SelfInvocationIntegrationTest.java
~~~

**Điều kiện chạy:** JDK 17+, Maven 3.6.3+, mạng hoặc cache Maven để tải dependencies. Không cần Docker vì lab dùng H2; nếu muốn kiểm locking/transaction semantics với PostgreSQL cần test riêng qua Testcontainers.

**Tính độc lập:** Đây là một project Maven hoàn chỉnh; các snippets ở các chương khác được ghi rõ là minh họa và không phải thêm vào project nếu không được yêu cầu.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>self-invocation-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Giải thích dependencies:
- `starter-jdbc`: `JdbcTemplate`, HikariCP, transaction manager với DataSource.
- H2: embedded relational database; cho phép quan sát auto-commit ngoài Spring transaction và rollback khi advice có hiệu lực.
- `starter-cache` + `@EnableCaching`: caching infrastructure.
- `starter-aop`: Spring AOP/AspectJ weaver runtime support cho proxies.
- `starter-validation`: Hibernate Validator/Jakarta Validation và Boot method validation postprocessor.
- `starter-test`: JUnit 5, AssertJ, Spring Test.
- Spring Boot BOM quản lý versions tương thích; không cố trộn framework major khác.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=self-invocation-lab

spring.datasource.url=jdbc:h2:mem:self_invocation_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.auto-commit=true

spring.sql.init.mode=always
spring.cache.type=simple
spring.aop.proxy-target-class=true
~~~

**Vai trò:** Hikari auto-commit=true giúp JDBC statement **không nằm trong Spring transaction** tự commit, khiến test self-invocation có thể quan sát một row tồn tại sau RuntimeException. Khi transaction interceptor hoạt động, Spring transaction manager điều khiển commit/rollback; Hikari pool auto-commit không phá một transaction đã bind cho thread.

`spring.aop.proxy-target-class=true` yêu cầu class-based proxies khi framework cần proxy. Việc chọn CGLIB **không làm self-invocation được intercept**. Hãy giữ dòng này để sample nhất quán, nhưng đừng dùng nó như “fix”.

`spring.cache.type=simple` dùng cache in-memory cơ bản. Ở mục main class, ta còn chủ động tạo `ConcurrentMapCacheManager` để behavior dễ đo. Không có Redis/external cache dependency trong lab.

### 7.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS audit_rows (
    id INTEGER PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
~~~

Schema đơn giản và đủ để quan sát transaction. `id` là primary key, mỗi test dùng ID khác nhau; `@BeforeEach` cleanup DB trước mỗi method. `IF NOT EXISTS` được H2 hỗ trợ trong lab; với production DB migrations, sử dụng Flyway/Liquibase và schema phù hợp DB version thay vì copy file này.

### 7.6. SelfInvocationApplication.java

`src/main/java/com/example/selfinvoke/SelfInvocationApplication.java`:

~~~java
package com.example.selfinvoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableCaching
@EnableTransactionManagement
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SelfInvocationApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("numbers");
    }
}
~~~

`@EnableTransactionManagement` làm transaction advisor rõ ràng trong sample. Với Spring Boot JDBC/DataSource, nhiều phần transaction auto-configuration đã có, nhưng khai báo này giúp người học thấy điều kiện để metadata `@Transactional` được xử lý. `@EnableCaching` kích hoạt caching annotations.

Tạo bean `CacheManager` explicit để test `numbers` cache đã tồn tại và có thể clear. `ConcurrentMapCacheManager` phù hợp test nhỏ, **không phải** production distributed cache.

### 7.7. BoundaryService.java

`src/main/java/com/example/selfinvoke/BoundaryService.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.validation.constraints.NotBlank;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BoundaryService {

    private final JdbcTemplate jdbc;
    private final AtomicInteger calculations =
            new AtomicInteger();

    public BoundaryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ------------------------------------------------
    // Transaction: direct proxy call vs self-invocation
    // ------------------------------------------------

    @Transactional
    public void insertThenFail(int id) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                id, "inserted before exception");
        throw new IllegalStateException(
                "injected failure after INSERT");
    }

    public void selfInsertThenFail(int id) {
        // Cùng target: KHÔNG qua transaction advice của inner.
        this.insertThenFail(id);
    }

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }

    public boolean selfTransactionActive() {
        return this.isTransactionActive();
    }

    // -----------------------------------------------
    // Caching: số lần method body thực sự được gọi
    // -----------------------------------------------

    @Cacheable(cacheNames = "numbers", key = "#p0")
    public int compute(int n) {
        calculations.incrementAndGet();
        return n * 10;
    }

    public List<Integer> selfComputeTwice(int n) {
        return List.of(
                this.compute(n),
                this.compute(n));
    }

    public int computationCount() {
        return calculations.get();
    }

    public void resetComputationCounter() {
        calculations.set(0);
    }

    // -----------------------------------------------
    // Method validation: parameter và return value
    // -----------------------------------------------

    public String normalize(@NotBlank String input) {
        return input.strip();
    }

    public String selfNormalize(String input) {
        return this.normalize(input);
    }

    @NotBlank
    public String invalidReturn() {
        return " ";
    }

    public String selfInvalidReturn() {
        return this.invalidReturn();
    }

    // -------------------------------------------------
    // Inner REQUIRES_NEW bị bỏ qua trong self invocation
    // -------------------------------------------------

    @Transactional
    public void outerWithSelfRequiresNew(
            int outerId, int innerId) {

        try {
            // Không đi qua proxy: REQUIRES_NEW bị bỏ qua.
            this.innerRequiresNewAndFail(innerId);
        }
        catch (IllegalStateException expected) {
            // Catch trong outer: outer có thể commit.
        }

        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                outerId, "outer committed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void innerRequiresNewAndFail(int innerId) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                innerId, "inner may rollback");

        throw new IllegalStateException(
                "inner transaction failure");
    }
}
~~~

**Các điểm cần quan sát:**

- `insertThenFail` ghi một row rồi throw. Gọi từ bên ngoài proxy → transaction rollback; gọi từ `selfInsertThenFail` → không có transaction của inner, JDBC statement auto-commit nên row còn.
- `isTransactionActive` khi gọi qua proxy → `true`; gọi qua `selfTransactionActive` → `false`, vì wrapper method không annotated.
- `compute` chỉ tăng counter khi body chạy. Gọi qua proxy hai lần cùng cache key → count 1; qua `selfComputeTwice` → count 2.
- `normalize` reject blank nếu validation interceptor chạy. Qua `selfNormalize("   ")`, constraint không được intercept; body trả chuỗi rỗng.
- `invalidReturn` có return value constraint. Qua proxy sẽ reject blank result; qua `selfInvalidReturn` return blank mà không báo lỗi.
- `outerWithSelfRequiresNew` **được gọi qua proxy** nên có outer transaction. Nhưng inner self-invocation không mở REQUIRES_NEW. Exception từ inner bị outer catch; cả inner và outer INSERT có thể cùng commit. Điều này kiểm trực tiếp tác động propagation chứ không dựa vào boolean transaction active.

### 7.8. RequiresNewWorker.java

`src/main/java/com/example/selfinvoke/RequiresNewWorker.java`:

~~~java
package com.example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiresNewWorker {

    private final JdbcTemplate jdbc;

    public RequiresNewWorker(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void insertThenFail(int innerId) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                innerId, "independent inner");
        throw new IllegalStateException(
                "new transaction failed");
    }
}
~~~

`RequiresNewWorker` là **bean khác**, nên một caller Spring-managed nhận nó qua constructor sẽ gọi `insertThenFail` qua proxy. REQUIRES_NEW suspends outer transaction và mở independent transaction. Throw unchecked làm rollback inner, outer có thể catch exception và tiếp tục.

Chọn INSERT outer **sau** inner để tránh khóa dữ liệu H2 giữa outer transaction và inner transaction trong ví dụ. Đây là lựa chọn deterministic cho lab, không phải một quy tắc xử lý deadlock chung.

### 7.9. CrossBeanFacade.java

`src/main/java/com/example/selfinvoke/CrossBeanFacade.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CrossBeanFacade {

    private final BoundaryService boundary;
    private final RequiresNewWorker requiresNewWorker;
    private final JdbcTemplate jdbc;

    public CrossBeanFacade(
            BoundaryService boundary,
            RequiresNewWorker requiresNewWorker,
            JdbcTemplate jdbc) {
        this.boundary = boundary;
        this.requiresNewWorker = requiresNewWorker;
        this.jdbc = jdbc;
    }

    public void callTransactionalInner(int id) {
        // boundary là Spring proxy, không phải this.
        boundary.insertThenFail(id);
    }

    public List<Integer> computeTwiceThroughProxy(int n) {
        return List.of(
                boundary.compute(n),
                boundary.compute(n));
    }

    public String normalizeThroughProxy(String value) {
        return boundary.normalize(value);
    }

    public String invalidReturnThroughProxy() {
        return boundary.invalidReturn();
    }

    @Transactional
    public void outerWithDelegatedRequiresNew(
            int outerId, int innerId) {
        try {
            // Call qua bean khác -> REQUIRES_NEW có hiệu lực.
            requiresNewWorker.insertThenFail(innerId);
        }
        catch (IllegalStateException expected) {
            // Inner rollback; outer vẫn có thể commit.
        }

        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                outerId, "outer committed");
    }
}
~~~

So sánh:
- `BoundaryService.selfInsertThenFail`: self-call không có transaction advice.
- `CrossBeanFacade.callTransactionalInner`: cross-bean call có transaction advice.
- `BoundaryService.outerWithSelfRequiresNew`: inner REQUIRES_NEW bị bypass.
- `CrossBeanFacade.outerWithDelegatedRequiresNew`: inner được rollback trong transaction riêng.
- `computeTwiceThroughProxy`: cache được sử dụng vì `boundary.compute` đi qua proxy.
- `normalizeThroughProxy`: Jakarta method validation được intercept.

### 7.10. SelfInvocationIntegrationTest.java

`src/test/java/com/example/selfinvoke/SelfInvocationIntegrationTest.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;
import java.util.Objects;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class SelfInvocationIntegrationTest {

    @Autowired
    BoundaryService boundary;

    @Autowired
    CrossBeanFacade facade;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CacheManager cacheManager;

    @BeforeEach
    void resetState() {
        // Test không @Transactional: cleanup commit thật.
        jdbc.update("DELETE FROM audit_rows");
        Objects.requireNonNull(
                cacheManager.getCache("numbers")).clear();
        boundary.resetComputationCounter();
    }

    private int rows(int id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_rows WHERE id = ?",
                Integer.class, id);
        return Objects.requireNonNull(result);
    }

    @Test
    void beanIsProxiedButItsOwnThisCallsStillBypassAdvice() {
        assertThat(AopUtils.isAopProxy(boundary)).isTrue();

        // External method invocation qua proxy:
        assertThat(boundary.isTransactionActive()).isTrue();

        // Local target call không đi qua transaction advice:
        assertThat(boundary.selfTransactionActive()).isFalse();
    }

    @Test
    void directProxyCallRollsBackInsertAfterRuntimeException() {
        assertThatThrownBy(() ->
                boundary.insertThenFail(101))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("injected failure");

        // Kiểm sau khi proxy đã hoàn tất rollback.
        assertThat(rows(101)).isZero();
    }

    @Test
    void selfInvocationBypassesTransactionAndLeavesAutocommitRow() {
        assertThatThrownBy(() ->
                boundary.selfInsertThenFail(102))
                .isInstanceOf(IllegalStateException.class);

        // Không có transaction interceptor của inner.
        // JDBC statement tự commit theo cấu hình H2/Hikari lab.
        assertThat(rows(102)).isEqualTo(1);
    }

    @Test
    void separateSpringBeanRestoresTransactionRollback() {
        assertThatThrownBy(() ->
                facade.callTransactionalInner(103))
                .isInstanceOf(IllegalStateException.class);

        assertThat(rows(103)).isZero();
    }

    @Test
    void selfInvokedRequiresNewIsNotASeparateTransaction() {
        boundary.outerWithSelfRequiresNew(201, 202);

        // Inner exception bị outer catch.
        // Cả hai writes thuộc outer transaction và commit.
        assertThat(rows(201)).isEqualTo(1);
        assertThat(rows(202)).isEqualTo(1);
    }

    @Test
    void crossBeanRequiresNewRollsBackOnlyInnerTransaction() {
        facade.outerWithDelegatedRequiresNew(203, 204);

        // Inner transaction rollback, outer transaction commit.
        assertThat(rows(203)).isEqualTo(1);
        assertThat(rows(204)).isZero();
    }

    @Test
    void externalCacheCallRunsExpensiveBodyOnce() {
        assertThat(boundary.compute(7)).isEqualTo(70);
        assertThat(boundary.compute(7)).isEqualTo(70);

        assertThat(boundary.computationCount()).isEqualTo(1);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(7)).isNotNull();
    }

    @Test
    void selfInvocationBypassesCacheAdviceTwice() {
        List<Integer> result = boundary.selfComputeTwice(8);

        assertThat(result).containsExactly(80, 80);
        assertThat(boundary.computationCount()).isEqualTo(2);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(8)).isNull();
    }

    @Test
    void crossBeanCacheCallUsesOneCachedResult() {
        List<Integer> result =
                facade.computeTwiceThroughProxy(9);

        assertThat(result).containsExactly(90, 90);
        assertThat(boundary.computationCount()).isEqualTo(1);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(9)).isNotNull();
    }

    @Test
    void externalMethodValidationRejectsBlankParameter() {
        assertThatThrownBy(() ->
                boundary.normalize("   "))
                .isInstanceOf(
                        ConstraintViolationException.class);

        assertThat(boundary.normalize("  valid  "))
                .isEqualTo("valid");
    }

    @Test
    void selfInvocationBypassesParameterValidation() {
        assertThat(boundary.selfNormalize("   "))
                .isEqualTo("");
    }

    @Test
    void externalReturnValueValidationRejectsBlankResult() {
        assertThatThrownBy(() ->
                boundary.invalidReturn())
                .isInstanceOf(
                        ConstraintViolationException.class);
    }

    @Test
    void selfInvocationBypassesReturnValueValidation() {
        assertThat(boundary.selfInvalidReturn())
                .isBlank();
    }

    @Test
    void delegatedValidationThroughAnotherBeanIsIntercepted() {
        assertThatThrownBy(() ->
                facade.normalizeThroughProxy(" "))
                .isInstanceOf(
                        ConstraintViolationException.class);

        assertThatThrownBy(
                facade::invalidReturnThroughProxy)
                .isInstanceOf(
                        ConstraintViolationException.class);
    }
}
~~~

### 7.11. Giải thích từng nhóm assertions

**Nhóm transaction (6 tests):**
- Bean có AOP proxy không có nghĩa các self-calls được intercept.
- External `insertThenFail` rollback, H2 không có row 101.
- Self `insertThenFail` bypass, H2 có row 102 vì auto-commit.
- Cross-bean delegate qua proxy rollback, không có row 103.
- Self-call vào inner `REQUIRES_NEW` **không mở transaction mới**; catch exception cho phép outer commit row 201 và 202.
- Delegate sang `RequiresNewWorker` mở transaction riêng; inner row 204 rollback, outer row 203 commit.

**Nhóm cache (3 tests):**
- External call `compute(7)` hai lần → computation count 1 và cache entry tồn tại.
- Self `compute(8)` hai lần → computation count 2 và cache entry **không được tạo**.
- Cross-bean two calls `compute(9)` → count 1 và entry tồn tại.

**Nhóm validation (5 tests):**
- External blank parameter bị `ConstraintViolationException`; valid parameter được trim.
- Self blank parameter lọt qua, trả chuỗi rỗng.
- External invalid return value bị constraint error.
- Self invalid return value lọt qua.
- Cross-bean delegate bị chặn cả parameter lẫn return value invalid.

Tổng cộng **14 JUnit test methods**. Sample test class cố ý **không có `@Transactional`** để service transactions mở/commit/rollback thật. Nếu thêm `@Transactional` trên JUnit class/method, default test-managed transaction có thể làm kết quả khác và che failure mode, đặc biệt với `REQUIRED` propagation.

### 7.12. Chạy Maven và kiểm kết quả

Từ thư mục `self-invocation-lab`:

~~~bash
mvn -q clean test

mvn -q -Dtest=SelfInvocationIntegrationTest test
~~~

Kết quả thiết kế mong đợi:
- Maven tải dependencies và chạy **14 tests**.
- `Tests run: 14, Failures: 0, Errors: 0` nếu môi trường/configuration tương thích.
- Transaction tests phân biệt row count 0/1 đúng như expected.
- Cache tests quan sát counter 1 vs 2.
- Validation tests quan sát `ConstraintViolationException` trên external/proxied calls.
- Surefire reports tại `target/surefire-reports`.
- Exit code Maven bằng 0 khi thành công; nội dung log/elapsed time có thể khác tùy môi trường.

**Chú ý QA:** Đây là dự án mẫu được thiết kế/kiểm tra về cú pháp và API, **chưa thực thi Maven** trong quá trình biên soạn Knowledge. Không công bố một số test PASS thật khi chưa chạy. CI của dự án cần chạy lệnh và xác nhận Surefire summary.

### 7.13. Có nên chạy ứng dụng bằng spring-boot:run?

~~~bash
mvn spring-boot:run
~~~

App có thể khởi động cùng H2 và cache manager nhưng không cung cấp REST controller hoặc CLI menu. Mục tiêu là JUnit integration tests, không phải HTTP API. Nếu muốn thử interactively, cần tạo `ApplicationRunner` hoặc REST endpoint được kiểm soát để gọi proxy bean, không gọi target class bằng `new`.

## 8. Test nào chứng minh điều gì? Tránh kết luận quá phạm vi

### 8.1. Kiểm annotation có mặt là quá yếu

~~~java
assertThat(BoundaryService.class
        .getMethod("insertThenFail", int.class)
        .isAnnotationPresent(Transactional.class))
        .isTrue();
~~~

Đoạn minh họa chỉ chứng minh source metadata có annotation, **không** chứng minh AOP đã enable, bean được proxied, caller đi qua proxy, transaction manager được chọn đúng hoặc rollback thật. Test meaningful phải quan sát outcome.

### 8.2. AopUtils.isAopProxy là điều kiện cần nhưng chưa đủ

~~~java
assertThat(AopUtils.isAopProxy(service)).isTrue();
~~~

Có proxy vẫn không có nghĩa self-call chạy advice. Một proxy có thể là caching proxy nhưng không có transaction interceptor, hoặc method không public/final khiến advice không intercept. Cần test behavior từng concern.

### 8.3. TransactionSynchronizationManager trả true cũng chưa đủ

Nếu outer đã transactional, `innerRequiresNew` tự gọi vẫn thấy transaction active vì inherited thread-bound context. Giá trị boolean không chứng minh `REQUIRES_NEW` đã mở một transaction khác. Lab có test **outer commit + inner rollback** để phân biệt.

### 8.4. Cache values giống nhau không chứng minh cache hit

~~~java
assertThat(service.compute(7)).isEqualTo(70);
assertThat(service.compute(7)).isEqualTo(70);
~~~

Cả cached và uncached đều có thể trả 70. Đo computation count, real repository/gateway calls hoặc cache entry. Với cache có TTL, test thêm fake clock/provider-specific expiry nếu requirement.

### 8.5. Validation test chỉ kiểm return value chưa đủ

Nếu method `normalize(" ")` trả `""`, một test chỉ assert output sẽ không nhận biết missing validation. Cần negative test qua proxy, assert exception. Với controller validation, verify status HTTP/validation body ở web layer riêng.

## 9. Unit test, slice test và full integration test

| Kiểu test | Có Spring AOP proxy thật? | Có transaction manager thật? | Có cache manager thật? | Có method validation proxy? |
| --- | --- | --- | --- | --- |
| `new BoundaryService(...)` | Không | Không từ AOP | Không từ AOP | Không từ AOP |
| Mockito `@Mock` đối tượng | Không | Không | Không | Không |
| Mockito `@Spy` POJO không trong Spring | Không mặc định | Không | Không | Không |
| `@WebMvcTest` | Chủ yếu MVC slice, không đủ mọi service beans | Thường không đúng service transaction setup | Không đảm bảo | Không bảo đảm target service proxies |
| `@JdbcTest` | Slice JDBC; service cần import/config riêng | Test thường transactional, rollback mặc định | Không đầy đủ nếu không import | Không đầy đủ nếu không import |
| `@DataJpaTest` | JPA slice, test-managed transaction | Có nhưng default rollback test có thể che commit semantics | Không đầy đủ | Không đầy đủ |
| `@SpringBootTest` (lab) | Có với config đúng | Có | Có | Có |
| Production-like DB/Redis + `@SpringBootTest` | Có | Có, backend thật | Có, provider thật | Có |
| Plain AspectJ-woven integration | Tùy weaving config | Có thể | Có thể | Không tự động tương đương MethodValidationPostProcessor |

**Đừng nhầm Mockito spy với Spring AOP proxy.** `@MockitoBean`/`@MockitoSpyBean` còn có bean override mechanics; nếu spy target/proxy sai layer, bạn có thể thay mất advice đang muốn kiểm. Khi bài tập là proxy integration, giữ bean thật và chỉ fake external collaborators không liên quan.

## 10. Giải pháp ưu tiên: tách bean theo boundary

### 10.1. Vì sao tách bean hiệu quả?

Nếu một use case cần:
- API gọi domain orchestration.
- Transaction per item.
- Cached read model.
- Validated inputs.

Hãy tách:
- `OrchestratorService`: điều phối.
- `TransactionalWorker`: boundary transaction.
- `CachedCatalogService`: boundary cache.
- `ValidatedCommandService`: boundary validation.

Orchestrator inject các interfaces/beans, và lời gọi từ orchestrator tới collaborator đi qua Spring proxy. Business boundaries trở nên rõ hơn, dễ unit test và integration test.

### 10.2. Pattern minh họa

~~~java
@Service
class InvoiceOrchestrator {

    private final InvoiceWriter writer;
    private final PriceCatalog catalog;
    private final InvoiceValidator validator;

    InvoiceOrchestrator(
            InvoiceWriter writer,
            PriceCatalog catalog,
            InvoiceValidator validator) {
        this.writer = writer;
        this.catalog = catalog;
        this.validator = validator;
    }

    public void create(String invoiceId) {
        validator.check(invoiceId);
        int price = catalog.cachedPrice(invoiceId);
        writer.write(invoiceId, price);
    }
}
~~~

Đây là snippet thiết kế, không thuộc project runnable và cần khai báo các collaborator. Lợi ích là các annotations trên `check`, `cachedPrice` và `write` có một cross-bean invocation rõ ràng. Đừng tạo hàng chục classes không cần thiết; tách theo **cross-cutting boundary có ý nghĩa**, không chỉ để “làm Spring chạy”.

### 10.3. Vì sao không tự new collaborator?

~~~java
InvoiceWriter writer = new InvoiceWriter(...);
writer.write(id, amount);
~~~

Nếu `writer` không lấy từ Spring container, nó không có Spring AOP proxy. Tách file thôi chưa đủ: phải là **managed bean** với injection đúng. Một POJO tự `new` không tự được @Transactional hoặc @Cacheable.

## 11. Giải pháp programmatic khi không muốn tách bean

### 11.1. TransactionTemplate

Khi cần transaction **bên trong một method mà không phụ thuộc proxy**, dùng `TransactionTemplate`:

~~~java
@Service
public class ProgrammaticBillingService {

    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    public ProgrammaticBillingService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.tx = new TransactionTemplate(manager);
        this.jdbc = jdbc;
    }

    public void createInTransaction(int id) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO audit_rows(id, description) "
                            + "VALUES (?, ?)",
                    id, "programmatic");
        });
    }
}
~~~

Snippet này cần imports và H2 schema tương ứng; dùng như lựa chọn kiến trúc mở rộng, không phải file của lab. Callback chạy trong transaction do `TransactionTemplate` điều khiển ngay khi method được gọi, kể cả lời gọi local.

Muốn `REQUIRES_NEW` programmatically, cấu hình:
`template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW)`. Chú ý transaction manager/connection pool và exceptions đúng semantics.

### 11.2. CacheManager programmatic

~~~java
Cache cache = cacheManager.getCache("numbers");
Integer value = cache.get(key, Integer.class);
if (value == null) {
    value = expensiveCalculation(key);
    cache.put(key, value);
}
~~~

Snippet minh họa: code tự làm caching có thể chạy trong local calls, nhưng cần xử lý cache stampede, null/value semantics, TTL và concurrency; `@Cacheable` qua proxy thường gọn hơn. Với production cache, tránh check-then-put race nếu yêu cầu only-once computation; dùng provider-specific atomic loading.

### 11.3. Validator.validate và ExecutableValidator

~~~java
Set<ConstraintViolation<SomeDto>> errors =
        validator.validate(dto);
~~~

Đây là snippet cần bean `jakarta.validation.Validator` và `SomeDto` thực. Nếu muốn method parameter/return constraints độc lập proxy, có thể dùng Bean Validation `ExecutableValidator` để validate parameters/return values một cách tường minh. Nhưng điều đó yêu cầu quản lý method references và errors; trong đa số service ứng dụng, Spring method validation qua proxy là lựa chọn rõ và nhất quán hơn.

## 12. Các workaround self-injection và AopContext

### 12.1. Inject lại proxy của chính bean

Có thể dùng self-reference (ví dụ `@Lazy` injection) để gọi qua proxy thay vì `this`:

~~~java
@Service
class SelfAwareService {

    private final SelfAwareService proxy;

    SelfAwareService(@Lazy SelfAwareService proxy) {
        this.proxy = proxy;
    }

    void outer() {
        proxy.inner();
    }

    @Transactional
    public void inner() {
        // ...
    }
}
~~~

**Đây là snippet có caveat**, không nằm trong lab. Self-injection có rủi ro circular dependency, phụ thuộc kiểu proxy và khó đọc/test. Spring Boot mặc định không khuyến khích circular references. Nếu sử dụng, phải verify reference thực sự trỏ tới proxy, không phải raw target và không gây cycle/bootstrap failure.

### 12.2. AopContext.currentProxy()

Một giải pháp low-level:

~~~java
((MyService) AopContext.currentProxy())
        .inner();
~~~

Cần `exposeProxy=true` trên AOP infrastructure, call đang ở trong proxy context, kiểu proxy phù hợp và import `AopContext`. Nó couple business code chặt với Spring AOP và có thể fail ngoài advised context. Không nên chọn chỉ vì nhanh hơn việc tách bean.

### 12.3. AspectJ weaving

Spring hỗ trợ `AdviceMode.ASPECTJ` cho transaction và caching với cấu hình weaving thích hợp (compile-time hoặc load-time), và dependencies phù hợp như `spring-aspects`. Khi target bytecode được woven, self-invocation có thể được intercept mà không cần Spring proxy.

Nhưng:
- Chỉ thêm dependency AspectJ vào pom **không tự kích hoạt weaving**.
- Weaving có build/runtime agent config, classloader và test setup riêng.
- Không được suy rằng Spring `@Validated` service method validation auto chuyển sang AspectJ chỉ vì bật AspectJ transaction/cache.
- AOT/native image và toolchain có caveats khác.
- Phải viết chính những integration tests này cho deployment mode đã chọn.

Với Spring Boot service thông thường, **tách bean** hoặc **programmatic boundary** dễ bảo trì hơn.

## 13. Visibility, final methods, JDK/CGLIB và annotation placement

### 13.1. Private/final methods

- Spring AOP proxy interception không thể áp vào **private method** theo cách caller bên ngoài gọi nó; private method cũng không override được.
- CGLIB class-based proxy không thể override `final` method/class. Method final có annotation có thể khiến advice không chạy.
- JDK interface proxy chỉ có thể expose methods trên proxied interfaces.
- Với `@Transactional` Spring Framework 6.x, protected/package-private methods có caveats với class-based proxies; public methods vẫn là thiết kế dễ hiểu, portable nhất.
- `@Cacheable` docs khuyên apply trên public methods khi dùng proxies.
- Method validation thường cần externally accessible methods trên Spring-managed `@Validated` beans.

### 13.2. Interface annotation vs implementation annotation

Spring có thể hỗ trợ annotations trên interface methods trong một số proxy configurations, nhưng AspectJ weaving và class proxy có khác biệt về annotation inheritance. Với transaction/cache, ưu tiên đặt annotations trên concrete service implementation methods khi có thể để tránh behavior thay đổi khi proxy strategy đổi.

### 13.3. CGLIB không chữa self call

Một số người bật `spring.aop.proxy-target-class=true` rồi kỳ vọng `this.inner()` đi qua CGLIB proxy. Trong Spring AOP proxy mode, internal call diễn ra trên target và **vẫn bypass advice**. Source Spring Framework AOP Proxying Mechanisms giải thích rõ điều này.

### 13.4. @Configuration(proxyBeanMethods = true) là câu chuyện khác

Spring `@Configuration` class enhancement có cơ chế intercept lời gọi giữa `@Bean` methods để bảo đảm singleton semantics khi `proxyBeanMethods=true`. Đây không phải lý do để suy các self-invocations của `@Service` sẽ chạy transaction/cache/validation advice. Hai feature có mục đích và infrastructure khác nhau.

## 14. Làm sao kiểm thử proxy thay vì chỉ kiểm logic thuần?

### 14.1. Dùng Spring-managed bean thật

Với mục tiêu này, `@SpringBootTest` là lựa chọn rõ ràng vì:
- Nạp AOP/caching/validation/transaction infrastructure.
- Nạp real `DataSourceTransactionManager`/JdbcTemplate.
- Nạp cache manager có thể kiểm entry.
- Method validation postprocessor tồn tại.
- Có thể autowire cả target service proxy và bean caller khác.

Một pure unit test `new BoundaryService(jdbc)` có thể kiểm code Java nhưng không thể khẳng định Spring advice chạy. Mockito mocks/spies cũng không thay cho một integration test AOP.

### 14.2. Tránh @Transactional ở test class

~~~java
@SpringBootTest
@Transactional
class MisleadingTest {
    // ...
}
~~~

Nếu test có transaction bao ngoài theo Spring TestContext, service `@Transactional(propagation=REQUIRED)` có thể tham gia transaction của test. Khi gọi `this.inner()` trực tiếp trong bean, vẫn có thể thấy transaction active vì test-managed transaction. Điều này che việc inner annotation không được intercept.

Khi cần test commit/rollback thực tế:
- Không gắn test-level `@Transactional`.
- Dùng real DB và query sau method exception/commit.
- Hoặc điều khiển transaction bằng `TestTransaction` có chủ đích.
- Đừng chỉ assert state trong cùng persistence context trước rollback.

### 14.3. @JdbcTest/@DataJpaTest rollback mặc định

`@JdbcTest` và `@DataJpaTest` thường chạy test trong transaction và rollback cuối test. Chúng tốt cho mapping/repository operations, nhưng không phải setup thuận tiện nhất để chứng minh **một public service call** tự mở/rollback transaction, nhất là khi test đã mở transaction trước.

### 14.4. Cache phải reset giữa tests

Nếu cache giữ `compute(7)` từ method trước, một test mới có thể thấy computation count 0 mà vẫn cho kết quả 70. Lab:
- Clear cache `numbers` trong `@BeforeEach`.
- Reset computation counter.
- Dùng keys khác nhau cho test cases.
- Assert cả result, counter và cache entry.

Với Redis/Caffeine, cần test provider-specific expiry, serialization, eviction và namespacing; Spring's simple cache lab không chứng minh các behavior đó.

### 14.5. Đừng dùng Mockito verify thay rollback assertion

~~~java
verify(service).insertThenFail(101);
~~~

Ngay cả khi method được gọi, verify không cho biết transaction commit/rollback. Đặt row thật, trigger exception, query DB sau transaction. Nếu muốn kiểm advice order, có thể thêm test instrumentation nhưng không thay durable state verification.

### 14.6. Kiểm exception thuộc layer nào

Nếu `normalize(" ")` bị từ chối:
- Jakarta Bean Validation `ConstraintViolationException` từ service method interceptor.
- Spring MVC `HandlerMethodValidationException` có thể xuất hiện khi request qua controller handler.
- Bind/validation trên `@RequestBody` thường có `MethodArgumentNotValidException`.

Các exception types khác nhau không tự chứng minh self-invocation issue. Xác định đúng invocation path và test layer.

## 15. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/giải pháp |
| --- | --- | --- |
| `@Transactional` trên inner nhưng INSERT vẫn commit | Self-invocation bỏ transaction advice | Gọi qua bean khác, kiểm rollback DB |
| `isActualTransactionActive()` true nhưng REQUIRES_NEW sai | Outer transaction đã active, inner bypass | Test separate commit/rollback |
| Tăng propagation nhưng không có tác dụng | Local call không đi qua proxy | Refactor bean/TransactionTemplate |
| `@Cacheable` không giảm DB queries | `this.cachedMethod()` bypass advice | Counter/cache inspection, tách cache service |
| `@CacheEvict` tự gọi không xóa cache | Local call bỏ qua eviction advice | Cross-bean call/CacheManager explicit |
| `@Validated` không reject blank service arg | Method gọi nội bộ không qua proxy hoặc thiếu provider | `starter-validation`, class @Validated, gọi proxy |
| Validates parameter nhưng không validates return | Method return constraint không được intercept | Test return via proxy |
| @Valid DTO có nhưng không chạy | Validator chưa được gọi tại boundary | HTTP validation hoặc manual Validator |
| `@SpringBootTest` test vẫn thấy tx khi self call | Test-level @Transactional tạo outer tx | Bỏ test tx và kiểm durable state |
| `@WebMvcTest` không thấy service advice | Service/infra không được nạp trong slice | Full integration test hoặc import đủ beans |
| Bean không được proxied | Chưa enable AOP/transaction/cache validation | Inspect AopUtils/advisors/config |
| CGLIB được bật nhưng self vẫn fail | CGLIB class proxy không intercept self | Split beans hoặc weaving phù hợp |
| @Transactional ở private method | Proxy không intercept private | Public boundary trên Spring bean |
| @Transactional ở final method | Class proxy không override được | Tránh final advised method |
| `new Service()` không chạy caching | Không phải managed bean | Inject từ Spring context |
| @PostConstruct inner tx không chạy | Bean/proxy chưa sẵn sàng hoặc local call | Runner/ready event qua proxy |
| Method validation throws exception khác expected | MVC vs AOP method validation hoặc adapt configured | Kiểm layer/exception strategy |
| @Cacheable cùng @Transactional cho dữ liệu stale | Cache consistency/advice order | Test rollback/eviction/provider |
| Self-injection gây application context cycle | Circular reference/proxy class mismatch | Tách bean là ưu tiên |
| AopContext.currentProxy() fails | Chưa expose proxy hoặc không có advised context | Tránh coupling hoặc cấu hình có test |
| AspectJ dependency thêm mà self vẫn bypass | Weaving chưa được bật | Bật compiler/agent + tests riêng |
| Direct DB writes trong transaction bị query thấy dữ liệu | Query cùng transaction chưa chứng minh commit | Đọc sau transaction completion |
| Test class pass nhưng production khác | Production DB/cache/provider khác H2/simple cache | Testcontainers/provider integration |
| Mockito @Spy/ @Mock che advice thật | Bean đã bị thay bằng test double | Giữ bean thật khi test interception |

### 15.1. Quy trình debug có hệ thống

1. Xác định **annotation nào** không chạy: transaction/cache/validation.
2. Từ caller, vẽ call graph: external bean proxy hay `this`?
3. Kiểm bean lấy từ Spring container hay `new`?
4. Xác nhận infrastructure có enable không: tx manager, cache manager, Bean Validation provider, @Validated.
5. Kiểm method visibility, final, proxy type (JDK/CGLIB) và annotation placement.
6. Kiểm test class có outer `@Transactional`/cached state làm sai observation không.
7. Với transaction: inject unchecked exception, **readback DB sau completion**.
8. Với cache: reset counter/cache và kiểm actual computations.
9. Với validation: gửi invalid parameter/return qua proxy, assert exception.
10. Khi sửa, thêm **cross-bean regression test** để behavior không bị đổi lại bởi refactor.

## 16. Self-invocation trong các integration concerns khác

### 16.1. @Async

`@Async` cũng thường dùng Spring AOP proxy. Nếu một method của cùng bean gọi `this.asyncMethod()`, lời gọi có thể chạy đồng bộ trên thread hiện tại thay vì dispatch vào executor. Hãy kiểm thread identity/`CompletableFuture` và bounded wait trong bài test. Không dùng một `Thread.sleep` để suy kết luận.

~~~java
@Service
class MailDispatcher {
    public void sendAll() {
        this.sendAsync(); // Có thể chạy synchronous
    }

    @Async
    public void sendAsync() {
        // ...
    }
}
~~~

Đây là snippet, cần `@EnableAsync`, executor và imports trong app phù hợp. Mục tiêu chính của bài vẫn là transaction/cache/validation.

### 16.2. @Retryable

`@Retryable` trong Spring Retry cũng có advice/proxy infrastructure, và local calls có thể bỏ qua retry interceptor. Cần đúng dependency/configuration, public boundary và test call count/backoff. Không giả định một `@Retryable` annotation làm Java method tự gọi lặp lại bên trong target.

### 16.3. @Secured/@PreAuthorize

Spring Method Security cũng có AOP interception. Với protected service method tự được gọi trong same target, phải kiểm proxy boundary và security configuration, không coi controller URL authorization là thay thế object-level service policy. Đây là một lý do nên tách service cross-cutting boundaries và test denied cases qua proxy.

### 16.4. @EventListener và @TransactionalEventListener

Các event listeners có lifecycle/dispatch infrastructure riêng và `@TransactionalEventListener` có phase semantics theo transaction. Không áp công thức “self-invocation luôn bypass” một cách máy móc cho mọi event annotation; phải hiểu method được ai dispatch/call và listener registration.

### 16.5. Reactive transaction

Reactive transactions với `TransactionalOperator`/reactive `@Transactional` dùng Reactor context, không đơn thuần dựa vào ThreadLocal transaction như JDBC. Lab dùng imperative JdbcTemplate, nên `TransactionSynchronizationManager.isActualTransactionActive()` có ý nghĩa tương ứng. Với R2DBC, cần bài test riêng theo reactive flow/subscription, không copy boolean/JDBC test.

## 17. Tác động tới thiết kế kiến trúc và code review

### 17.1. Boundary methods phải rõ

Một codebase dễ review khi:
- Orchestrator method không có annotation làm người đọc hiểu lầm.
- Side-effect boundary như `paymentWrite` ở separate service.
- Cached read ở service có contract cache riêng.
- Validation ở request boundary và service boundary theo nghiệp vụ.
- Public methods có annotations được gọi qua managed dependencies.

Annotation không nên là “trang trí”, mà phải có integration test bảo vệ semantics.

### 17.2. Chọn rollback test thay vì reflection test

Nếu rule là “không lưu receipt khi validation fail”:
- Mock đơn thuần không chứng minh DB rollback.
- Reflection thấy `@Transactional` không chứng minh proxy active.
- Test thật nên tạo H2/PostgreSQL fixture, gọi external bean method, inject exception và query row count sau rollback.

### 17.3. Đừng tạo coupling chỉ để ép proxy

Self-injection hoặc `AopContext.currentProxy()` có thể giải quyết cục bộ, nhưng đổi lại:
- Class khó unit test ngoài Spring.
- Circular dependencies dễ phát sinh.
- Proxy type thay đổi có thể gây runtime cast issues.
- Business code biết nhiều chi tiết AOP infrastructure.
- Developer mới khó hiểu vì sao gọi `self.method` mà không gọi `this.method`.

Tách bean hoặc programmatic boundary thường trực quan hơn.

### 17.4. Kiểm cache và transaction với dữ liệu phân tán

Một test H2/simple cache chỉ kiểm Spring AOP semantics. Với production:
- PostgreSQL/MySQL: lock/isolation/transaction rollback khác DB dialect.
- Redis: network, serialization, TTL, stale cache và cache eviction timing.
- Hibernate/JPA: first-level persistence context có thể làm query result “cached” dù `@Cacheable` không chạy.
- Distributed services: cache invalidation và external side effects không thuộc cùng JDBC transaction.

Dùng Testcontainers/prod-like services và assertions end-to-end cho những phần contract critical, tránh overclaim từ lab.

## 18. Bài tập

1. Chạy project, nhìn 14 JUnit methods; xác định nhóm transaction, cache và validation.
2. Gọi `BoundaryService.insertThenFail` qua Spring bean, giải thích vì sao row bị rollback.
3. Gọi `selfInsertThenFail`, giải thích vì sao H2 vẫn có row dù exception.
4. Đổi `spring.datasource.hikari.auto-commit=false` trong một nhánh thử nghiệm, phân tích vì sao nó thay đổi observation nhưng **không chữa** proxy bypass.
5. Thêm một `@Transactional(readOnly=true)` inner method, tự gọi từ outer; kiểm read-only advice có được áp dụng không.
6. Thêm `Propagation.MANDATORY` vào inner và thử external vs self invocation khi outer không transactional.
7. Đổi REQUIRES_NEW thành REQUIRED ở cả hai paths; lập luận khác biệt trước/sau refactor.
8. Thêm checked exception trong proxied method; kiểm rollback rule mặc định và `rollbackFor`.
9. Thêm một test có `@Transactional` trên JUnit method, quan sát tại sao nó che trạng thái “no transaction” của self-call.
10. Tạo phương thức cache `@CacheEvict` được self-called sau update; kiểm cache stale và sửa bằng cross-bean invocation.
11. Dùng cache TTL của Caffeine/Redis trong integration test riêng, không dùng ConcurrentMapCacheManager để suy TTL.
12. Thay key `#p0` thành key thiếu tenant dimension; viết test negative cho cache cross-tenant data leak.
13. Thử `@NotBlank` parameter qua external call và self-call; kiểm exception/returned blank khác nhau.
14. Thêm `@Positive` cho integer parameter, kiểm input 0 bị từ chối qua proxy.
15. Thêm return value `@NotNull` và test validation sau method body.
16. Đặt `@Validated` trên service interface thay vì concrete class, kiểm tác động dưới JDK/CGLIB proxy modes.
17. Thêm interface cho service, chọn JDK proxy và kiểm casting/autowiring đúng type.
18. Đánh dấu advised method `final` trong một branch, quan sát proxy limitations; không đưa branch đó vào release.
19. Viết chương trình pure unit `new BoundaryService(...)` với mock JdbcTemplate; chỉ ra nó **không** test Spring AOP.
20. Thử `@WebMvcTest` chỉ load controller; giải thích tại sao service transaction/cache/validation không được kiểm đầy đủ.
21. Chuyển `CrossBeanFacade` sang một orchestration service thực trong ứng dụng; đo số SQL queries/cache hits.
22. Refactor dùng `TransactionTemplate` thay `@Transactional` inner; test local invocation có transaction.
23. Test programmatic `Validator.validate(dto)` và so sánh với method-validation proxy.
24. Thiết lập AspectJ weaving ở module thử nghiệm riêng; viết cùng regression tests để xác nhận self-call được intercept khi weaving thực sự bật.
25. Thêm một `@Async` inner method, kiểm thread identity khi self-called vs cross-bean call.
26. Bật `@EnableMethodSecurity` và kiểm `@PreAuthorize` cross-bean vs self invocation trong module riêng.
27. Tạo PostgreSQL Testcontainers variant để kiểm rollback và isolation ngoài H2.
28. Viết code review checklist cho team: mỗi annotated boundary method phải có caller path và regression test phù hợp.

## 19. Checklist trước khi merge

- [ ] Các `@Transactional`, `@Cacheable`, `@Validated` có thực sự được Spring infrastructure xử lý?
- [ ] Public annotated methods có được gọi qua proxy?
- [ ] Có `this.annotatedMethod()` hoặc implicit self-call gây bypass?
- [ ] CGLIB/JDK proxy được hiểu đúng, không coi CGLIB là giải pháp self-call?
- [ ] Có test transaction rollback thực thay vì chỉ assert annotation?
- [ ] Có kiểm `REQUIRES_NEW` bằng separate commit/rollback, không chỉ boolean transaction active?
- [ ] Không dùng `@Transactional` trên JUnit test làm che service transaction boundaries?
- [ ] Có kiểm data sau khi transaction hoàn tất?
- [ ] Caching tests kiểm counter/side-effect/cache contents, không chỉ return value?
- [ ] Cache key có đủ tenant/user/business dimensions?
- [ ] Cache được clear/isolated giữa test methods?
- [ ] Caching infrastructure có `@EnableCaching` và provider phù hợp?
- [ ] Method validation có Bean Validation implementation và class-level `@Validated`?
- [ ] Invalid method parameter bị reject qua proxied path?
- [ ] Invalid return value cũng được kiểm?
- [ ] Phân biệt Spring MVC built-in validation với AOP service validation?
- [ ] Không mock chính proxy/service muốn kiểm?
- [ ] Có AopUtils check và **behavioral assertions**?
- [ ] Có regression test sau refactor tách bean?
- [ ] Nếu dùng self-injection, không có circular reference/proxy-type bug?
- [ ] Nếu dùng AspectJ, weaving được bật và kiểm trong actual runtime?
- [ ] @PostConstruct, private/final methods không bị lạm dụng làm advice boundary?
- [ ] Có kiểm rollback/caching trên production-like DB/cache nếu critical?
- [ ] Không lộ secrets/production data trong integration tests?
- [ ] Maven/JUnit reports đã xác minh tests thực sự executed và behavior đúng?

**Kết luận:** Self-invocation không ngăn Java method body chạy, nhưng với Spring AOP **proxy mode** nó bỏ qua advice gắn trên method nội bộ. Kết quả có thể là thiếu rollback, thiếu cache hit/eviction hoặc validation không được thực thi. Một outer transaction đang active không cứu được metadata `REQUIRES_NEW` của inner tự gọi. Hãy kiểm **outcome thật**: DB state sau exception, cache computation count và constraint violation của parameter/return value; so sánh self-call với cross-bean call, sau đó chọn tách bean hoặc programmatic boundary để sửa. Đừng dùng reflection, Mockito-only test hoặc `@Transactional` test-level để suy ra một proxy integration behavior chưa hề được thực thi.

## 20. Tài liệu chính thức

- Spring Framework 6.2 — AOP Proxying Mechanisms (self-invocation): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — Using @Transactional (proxy mode, REQUIRES_NEW caveats): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2 — Programmatic Transaction Management/TransactionTemplate: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework 6.2 — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — Java Bean Validation, MethodValidationPostProcessor: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Caching: https://docs.spring.io/spring-boot/3.5/reference/io/caching.html
- Spring Boot 3.5 — JDBC SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Testing Spring Boot Applications and JDBC test slices: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — TransactionalTestExecutionListener: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html
- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5.16 — Release notes: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now

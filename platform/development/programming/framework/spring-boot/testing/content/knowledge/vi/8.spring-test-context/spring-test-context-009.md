# Proxy Spring trong test: transaction, cache và method security

Trong ứng dụng Spring Boot, một phương thức có `@Transactional`, `@Cacheable` hoặc `@PreAuthorize` có thể hành xử **khác hẳn khi được gọi thông qua bean do Spring quản lý** so với khi gọi trực tiếp trên object tạo bằng `new`. Nguyên nhân thường là **Spring AOP proxy**: một đối tượng trung gian chặn lời gọi để mở/đóng transaction, đọc/ghi cache hoặc kiểm tra quyền trước khi chuyển tiếp vào mã nghiệp vụ.

Bài học thuộc nhóm **Spring TestContext**: mục tiêu không chỉ xác nhận logic Java thuần, mà còn xác nhận **đường đi qua Spring proxy thực sự hoạt động trong ngữ cảnh kiểm thử**. Ba chủ đề transaction, cache và method security có cùng điểm chung là hành vi framework thường nằm *ngoài thân phương thức*, nhưng mỗi chủ đề có một hợp đồng quan sát và kiểu test thích hợp khác nhau.

## 1. Phân biệt phương thức thật, bean, proxy và lời gọi qua proxy

Xét ví dụ khái niệm:

```java
@Transactional
public void transfer() {
    debit();
    credit();
}
```

Annotation là metadata, không phải một câu lệnh Java tự tạo transaction. Với cơ chế Spring transaction dựa trên proxy, khi một bean bên ngoài gọi `transfer()` thông qua proxy, interceptor có cơ hội mở transaction, gọi logic thật rồi commit hoặc rollback theo kết quả. Nếu viết `new TransferService(...).transfer()`, Spring không có cơ hội chặn lời gọi.

```text
                         bean reference được inject từ Spring
Caller  -----------------------------------------------+
                                                      |
                                                      v
                                           [Spring AOP proxy]
                                            /      |       \
                                    transaction  cache  authorization
                                            \      |       /
                                                      |
                                                      v
                                               [Target object]
                                                      |
                                                      v
                                              Business method
```

**Các khái niệm cần nắm:**

- **Target:** đối tượng chứa logic nghiệp vụ; phương thức Java vẫn chạy theo cách thông thường.
- **Proxy:** đối tượng mà Spring cung cấp cho caller, có thể thực hiện một hoặc nhiều interceptor/advisor trước/sau lời gọi.
- **Advice/interceptor:** logic của framework (giao dịch, cache, phân quyền) áp dụng khi phương thức phù hợp với cấu hình.
- **ApplicationContext:** nơi Spring tạo bean, resolve dependency, đăng ký cơ chế proxy và cấp reference tới bean.
- **Spring TestContext:** hạ tầng Spring Test kết hợp với JUnit Jupiter để tạo/sử dụng ApplicationContext trong test; ví dụ `@SpringJUnitConfig` và `@SpringBootTest`.

**Điểm mấu chốt:** với các tính năng proxy-based, **“test method chạy đúng” không đồng nghĩa “annotation được Spring thực thi”**. Test phải đi qua bean được lấy từ context và kiểm chứng một hiệu ứng đặc trưng của proxy, không chỉ kiểm tra output nghiệp vụ.

## 2. Khi nào cần test dùng Spring và khi nào không?

| Điều cần kiểm tra | Unit test dùng `new Service(...)` | Test có Spring context |
| --- | --- | --- |
| Hàm tính toán, validation, state machine thuần | Phù hợp, nhanh | Thường không cần |
| Service quyết định có gọi repository port hay không | Phù hợp với mock/fake | Chỉ thêm khi cần wiring hoặc tích hợp |
| `@Transactional` thực sự rollback dữ liệu đã ghi | Không; annotation không tự chạy | Cần proxy + transaction manager + nguồn dữ liệu thật |
| `@Cacheable` trả kết quả từ cache, không chạy lại target | Không nếu chỉ gọi target bằng `new` | Cần caching advisor + CacheManager thật |
| `@PreAuthorize` chặn caller thiếu quyền | Không nếu chỉ gọi target bằng `new` | Cần method-security interceptor + SecurityContext |
| JSON binding, filter chain, HTTP status | Không | Cần MVC/WebFlux slice hoặc integration test phù hợp |
| Redis TTL, DB isolation, transaction propagation thực | Mock không chứng minh được | Cần adapter/integration test với hạ tầng tương ứng |

Đừng sử dụng `@SpringBootTest` cho mọi test chỉ vì source code nằm trong Spring Boot. **Tăng độ rộng của test chỉ khi hành vi cần chứng minh thực sự phụ thuộc vào Spring hoặc hạ tầng.** Ngược lại, khi yêu cầu nói rõ transaction/cache/security proxy, chỉ test Java thuần là chưa đủ.

## 3. Những loại proxy và các tình huống dễ làm advice không chạy

Ở mức đơn giản, Spring AOP có thể sử dụng **JDK dynamic proxy** (thường cho interface) hoặc **class-based proxy** dựa trên subclass (thường gọi là CGLIB proxy). Cách chọn chịu ảnh hưởng interface, cấu hình proxy và cơ chế đang sử dụng.

- **JDK dynamic proxy:** proxy thể hiện các interface được proxy; một bean kiểu interface có thể hoạt động bình thường nhưng ép kiểu sang implementation cụ thể có thể không phù hợp.
- **Class-based proxy:** proxy là subclass của class mục tiêu. Phương thức `final` không thể bị override để chặn bằng cơ chế subclass; class `final` cũng ngăn tạo subclass proxy. Private method không phải điểm chặn được gọi từ bên ngoài theo kiểu proxy thông thường.
- **Self-invocation:** khi một phương thức trong target gọi `this.anotherMethod()`, lời gọi nội bộ thường không đi **ra ngoài rồi vào lại proxy**, nên advice proxy-based trên `anotherMethod()` có thể bị bỏ qua.
- **Object tạo bằng `new`:** không phải bean proxy, cho dù class có annotation.
- **Annotation không được bật:** có thể thêm `@Transactional`/`@Cacheable`/`@PreAuthorize` mà thiếu transaction/caching/method-security infrastructure; logic Java vẫn chạy và khiến test “xanh giả”.

Một ví dụ self-invocation chỉ để hình dung:

```java
public String outer(String sku) {
    return this.cachedPrice(sku); // Lời gọi bên trong target
}

@Cacheable("prices")
public String cachedPrice(String sku) {
    return fetchPrice(sku);
}
```

Đây là **đoạn phương thức minh họa**, chưa phải class chạy độc lập (chưa có `fetchPrice`). Nếu caller gọi `outer(...)` trên bean, lời gọi nội bộ `this.cachedPrice(...)` không nhất thiết đi qua caching advice. Cách thiết kế tốt hơn là đưa boundary cần chặn sang một bean riêng và gọi **bean proxy được inject**, hoặc cấu trúc lại để advice áp dụng ở public entrypoint thích hợp. Không dùng cơ chế gọi vòng qua `ApplicationContext` hoặc self-injection chỉ để “ép proxy” khi chưa đánh giá ảnh hưởng thiết kế.

**Không suy diễn loại proxy chỉ từ một annotation.** Kiểm tra proxy bằng API của Spring khi cần chẩn đoán, ví dụ `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)` hoặc `AopUtils.isCglibProxy(bean)`. Quan trọng hơn việc xác định loại proxy là test **hiệu ứng thực** của transaction/cache/security.

## 4. Ví dụ Spring TestContext kiểm chứng cả ba proxy

Ví dụ dưới đây dùng **Java 17+, JUnit Jupiter, Spring TestContext, H2 in-memory và Spring Security method security**. Mục tiêu là thực thi code thật qua các proxy, không mock chính interceptor. Nó cố tình cấu hình một context nhỏ bằng `@SpringJUnitConfig` thay vì bootstrap toàn bộ ứng dụng.

**Ba hành vi độc lập cần kiểm tra:**

1. `AuditService.addThenFail(...)` ghi một hàng bằng JDBC rồi ném `IllegalStateException`. Khi transaction interceptor chạy, dữ liệu phải rollback. `addNormally(...)` phải commit.
2. `PriceService.quote(sku)` tính giá trị và tăng bộ đếm. Với `@Cacheable`, hai lời gọi qua proxy cùng key trả cùng kết quả nhưng target chỉ tính một lần.
3. `DocumentService.readSecret()` chỉ cho phép authority `doc:read` theo `@PreAuthorize`. Người thiếu quyền bị chặn trước khi nhận dữ liệu.

### 4.1. Chuẩn bị dependencies

Ví dụ có thể chạy trong dự án Spring Boot/Gradle đã thiết lập plugin, repositories và quản lý phiên bản dependency. Các dòng liên quan trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải toàn bộ `build.gradle` độc lập. `spring-security-test` chứa hỗ trợ test với `@WithMockUser`; không nên mặc định dependency này đã xuất hiện chỉ vì project có `spring-boot-starter-test`. H2 là database test in-memory; khi dùng database production có dialect/constraint riêng, cần integration test với DB engine phù hợp.

Tạo một file duy nhất:

```text
src/test/java/example/testing/proxy/ProxyBehaviorTest.java
```

Test sử dụng class và cấu hình lồng bên trong; nhờ đó không cần tạo source file khác cho ví dụ.

### 4.2. File test đầy đủ: ProxyBehaviorTest.java

```java
package example.testing.proxy;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ProxyBehaviorTest.Config.class)
class ProxyBehaviorTest {

    @Autowired
    private AuditService auditService;

    @Autowired
    private PriceService priceService;

    @Autowired
    private DocumentService documentService;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private CacheManager cacheManager;

    @BeforeEach
    void resetState() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS audit_entry (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                note VARCHAR(100) NOT NULL
            )
            """);
        jdbc.update("DELETE FROM audit_entry");

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("prices"));
        cache.clear();
    }

    @Test
    void servicesAreSpringAopProxies() {
        assertTrue(AopUtils.isAopProxy(auditService));
        assertTrue(AopUtils.isAopProxy(priceService));
        assertTrue(AopUtils.isAopProxy(documentService));
    }

    @Test
    void transactionRollsBackOnRuntimeException() {
        assertThrows(IllegalStateException.class,
                () -> auditService.addThenFail("failed"));

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_entry", Long.class);
        assertEquals(0L, count.longValue());
    }

    @Test
    void transactionCommitsOnNormalReturn() {
        auditService.addNormally("ok");

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_entry", Long.class);
        assertEquals(1L, count.longValue());
    }

    @Test
    void cacheAvoidsRecomputingForSameKey() {
        int before = priceService.computations();

        String first = priceService.quote("SKU-1");
        String second = priceService.quote("SKU-1");
        String other = priceService.quote("SKU-2");

        assertEquals(first, second);
        assertNotEquals(first, other);
        assertEquals(before + 2, priceService.computations());
    }

    @Test
    @WithMockUser(authorities = "doc:read")
    void authorizedCallerCanRead() {
        assertEquals("classified", documentService.readSecret());
    }

    @Test
    @WithMockUser(authorities = "doc:write")
    void callerWithoutReadAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> documentService.readSecret());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableCaching
    @EnableMethodSecurity
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:proxy_lesson;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        PriceService priceService() {
            return new PriceService();
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void addNormally(String note) {
            jdbc.update(
                    "INSERT INTO audit_entry(note) VALUES (?)", note);
        }

        @Transactional
        public void addThenFail(String note) {
            jdbc.update(
                    "INSERT INTO audit_entry(note) VALUES (?)", note);
            throw new IllegalStateException("failed deliberately");
        }
    }

    public static class PriceService {
        private final AtomicInteger counter = new AtomicInteger();

        @Cacheable(cacheNames = "prices")
        public String quote(String sku) {
            return sku + "#" + counter.incrementAndGet();
        }

        public int computations() {
            return counter.get();
        }
    }

    public static class DocumentService {
        @PreAuthorize("hasAuthority('doc:read')")
        public String readSecret() {
            return "classified";
        }
    }
}
```

**Tính độc lập của file:** toàn bộ class, config và service demo được định nghĩa trong cùng một file Java. `AuditService`, `PriceService` và `DocumentService` là class `public static` lồng bên trong, **không final**, phương thức được proxy là `public` và không final. Spring đăng ký chúng qua `@Bean`; test lấy chính reference do context inject. Với cấu hình cụ thể ở đây, không cần interface repository hoặc HTTP controller.

**Không gắn `@Transactional` lên test class hoặc các test method** trong ví dụ này. Mục tiêu là quan sát transaction được mở bởi *proxy của service* và kết quả dữ liệu **sau khi lời gọi service kết thúc**. Nếu test tự nằm trong một transaction được Spring Test rollback sau test, dữ liệu đang nhìn thấy trong cùng transaction có thể tạo bằng chứng gây hiểu nhầm.

### 4.3. Chạy file kiểm thử

Từ thư mục root dự án Gradle có wrapper:

```bash
./gradlew test --tests example.testing.proxy.ProxyBehaviorTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.proxy.ProxyBehaviorTest"
```

**Kỳ vọng:** có **6 test methods** và tất cả pass khi các dependencies đã nêu được cấu hình đúng, H2 có trên test runtime classpath và Spring TestContext tạo context thành công. Gradle/JUnit không có một chuỗi stdout cố định chung; có thể kiểm tra report của test runner để xác nhận từng test.

File này **không phải chương trình Java thuần chạy bằng `javac File.java; java File`**: nó phụ thuộc Spring Framework, Spring Security, JUnit và H2, nên phải có dependency classpath/test engine như Gradle/Maven đã cấu hình. Không nên trình bày stdout `javac/java` giả cho framework test này. Nếu muốn thử business rule thuần, hãy viết test `new Service(...)` riêng — nhưng nó không chứng minh proxy.

### 4.4. Giải thích tại sao từng test có ý nghĩa

**Test 1 — proxy tồn tại.** `AopUtils.isAopProxy(...)` là tín hiệu Spring đang cấp reference có AOP proxy. Nó giúp chẩn đoán thiếu `@EnableTransactionManagement`/`@EnableCaching`/`@EnableMethodSecurity`, nhưng **chỉ có proxy chưa chứng minh đúng hiệu ứng**. Các test tiếp theo kiểm tra từng hành vi.

**Test 2 — rollback thật.** `auditService.addThenFail("failed")` đi qua transaction interceptor; `JdbcTemplate` tham gia transaction trên cùng `DataSource` với `DataSourceTransactionManager`. Sau runtime exception, transaction phải rollback. Test đọc lại bảng bằng JDBC sau khi method đã kết thúc và mong **0 hàng**. Nếu gọi object không có transaction qua `new AuditService(jdbc)`, insert có thể tự commit theo autocommit của datasource trước khi exception được ném; test rollback sẽ phát hiện sự khác biệt.

**Test 3 — commit thật.** `addNormally("ok")` hoàn thành bình thường. Sau lời gọi, JDBC thấy một hàng tồn tại. Đây là kiểm tra đôi cho test rollback, giúp tránh kết luận “0 hàng” chỉ vì câu lệnh insert chưa hề được thực hiện. Để chắc chắn hơn với hệ thống thực, có thể kiểm tra cả giá trị `note`, uniqueness và transaction isolation nếu là hợp đồng.

**Test 4 — cache thật.** `PriceService.quote("SKU-1")` chạy target và tăng `counter`. Lần thứ hai với cùng key đi qua cache advisor và trả dữ liệu được lưu mà không tăng counter. Lời gọi với `SKU-2` có key khác nên target tính lần nữa. Test dùng chênh lệch `before + 2` thay vì giả định counter luôn bắt đầu từ 0, vì bean/context có thể được tái sử dụng giữa các test; chỉ cache được xóa trước mỗi test.

**Test 5–6 — method security thật.** `@WithMockUser(authorities = "doc:read")` đặt Authentication kiểm thử trong `SecurityContext`, nên `hasAuthority('doc:read')` chấp nhận. Với `doc:write`, proxy method-security từ chối bằng exception kế thừa `AccessDeniedException`. Test này kiểm tra **phân quyền method** qua proxy; nó **không gửi HTTP request**, không chứng minh security filter chain hay status HTTP 403.

## 5. Spring TestContext nào nên dùng?

Đặt đúng ranh giới giúp test nhanh mà vẫn chứng minh proxy.

| Công cụ | Ngữ cảnh | Nên dùng khi |
| --- | --- | --- |
| JUnit + `new Service(...)` | Không Spring | Quy tắc thuần, logic điều kiện, orchestration với mock |
| `@SpringJUnitConfig(Config.class)` | Context Spring tối thiểu với bean/config do test chỉ định | Muốn xác nhận AOP proxy cụ thể mà không cần auto-configuration toàn ứng dụng |
| `@SpringBootTest` | Boot context rộng, auto-configuration của ứng dụng | Cần chứng minh wiring production, transaction manager/cache/security beans thực tế của ứng dụng |
| `@DataJpaTest` | Slice JPA/repository | Kiểm tra mapping/query, không mặc định chứng minh toàn bộ service AOP |
| `@WebMvcTest` + `MockMvc` | Slice MVC và HTTP infrastructure | Cần xem request/validation/filter/status của controller và cách security hoạt động ở HTTP |
| Test dùng Redis/DB/broker thật | Có adapter/hạ tầng tương ứng | Cần chứng minh TTL, serialization, unique constraint, transaction isolation, network behavior |

**`@SpringJUnitConfig`** kết hợp cấu hình Spring Test với JUnit Jupiter. Nó tạo context từ `Config`; trong ví dụ ta tự bật ba cơ chế bằng `@EnableTransactionManagement`, `@EnableCaching` và `@EnableMethodSecurity`. Vì không bật toàn bộ Spring Boot auto-configuration, test rõ ràng bean nào tham gia.

**`@SpringBootTest`** thích hợp khi cần kiểm tra cấu hình thật của ứng dụng — nhưng phải bảo đảm đang dùng đúng bean và profile test. Một test sử dụng mock bean thay target hoặc giả lập transaction manager có thể vô tình **không còn kiểm chứng điều người viết muốn chứng minh**.

**TestContext caching:** Spring Test có thể tái sử dụng ApplicationContext giữa các test có cấu hình tương đương để giảm thời gian bootstrap. Vì vậy mutable bean state, cache và dữ liệu DB **không tự được reset** sau mỗi method. Test ví dụ chủ động dọn bảng/caching trong `@BeforeEach`. Với test chạy song song, cần cách ly database/cache/context phù hợp; không xem `@BeforeEach` trên shared DB là bảo đảm an toàn cho parallel execution.

## 6. Transaction proxy: cơ chế và bằng chứng cần có

### 6.1. Một transaction được tạo khi nào?

Với proxy-based declarative transactions, luồng thường là:

```text
Caller -> transactional proxy
       -> TransactionInterceptor / transaction manager
       -> begin or join transaction according to propagation
       -> target business method (JDBC/JPA work)
       -> commit on normal return
       -> rollback for configured failure types
       -> return/throw to caller
```

Chi tiết thực tế còn phụ thuộc `Propagation`, isolation, transaction manager, exception type và hạ tầng. **`@Transactional` không tự tạo transaction nếu lời gọi không qua cơ chế Spring đã cấu hình.**

Các trường hợp nên có trong test:

- Thành công: có bằng chứng thay đổi đã **commit** sau khi proxy method trả về.
- Runtime exception: dữ liệu được ghi trong transaction rồi **rollback**.
- Checked exception: mặc định Spring thường **không rollback** chỉ vì một checked exception; nếu nghiệp vụ yêu cầu rollback, khai báo `rollbackFor` hoặc policy tương đương và test bằng dữ liệu thật.
- Propagation: với `REQUIRES_NEW`, transaction mới có thể commit độc lập với transaction ngoài, nên chỉ unit test mock repository không đủ chứng minh kết quả.
- Self-invocation: method bên trong cùng target gọi một method annotated khác qua `this` có thể bypass proxy, nên propagation mới không tự xuất hiện.

**Ví dụ checked exception (minh họa, chưa phải class chạy riêng):**

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    repository.save(record);
    throw new IOException("invalid source");
}
```

Vì đây là đoạn method minh họa, nó giả định `repository` và `record` đã được định nghĩa. Test transaction chính xác cần môi trường DB và xác minh rollback sau exception. Không đổi `rollbackFor` theo cảm tính: nếu checked exception có ý nghĩa nghiệp vụ là “không thể tiếp tục”, policy rollback cần được thiết kế rõ.

### 6.2. Bẫy test-managed transaction rollback

Spring Test có thể dùng `@Transactional` trên test method để tự mở transaction và rollback sau test. Đây là tính năng hữu ích để **cô lập dữ liệu test**, nhưng dễ làm test giao dịch của service không phản ánh commit thật.

Ví dụ:

```java
@Transactional
@Test
void example() {
    service.save(...);
    assertEquals(1, repository.count());
}
```

Đây là đoạn cấu trúc minh họa, không chạy độc lập. Nếu service tham gia transaction do **test** mở, `repository.count()` có thể thấy dữ liệu **chưa commit** trong cùng transaction. Test xanh không chứng minh service thực sự commit; khi method test hoàn tất, Spring Test có thể rollback mọi thay đổi. Để test commit/rollback của service như ví dụ mục 4, **không đặt transaction trên test**, gọi bean proxy, rồi đọc dữ liệu sau lời gọi khi transaction của service kết thúc.

Nếu cần test logic trong transaction do test quản lý, hãy phân biệt mục tiêu: dùng `@Transactional` trên test để cleanup là hợp lý, nhưng không quảng bá nó thành bằng chứng commit/rollback của annotated service. Với những case phức tạp có thể dùng `TransactionTemplate`, `TestTransaction` hoặc test framework transaction API phù hợp; hãy kiểm chứng đúng điểm commit/rollback mong muốn.

### 6.3. Proxy, public method và self-invocation

Trong cách cấu hình proxy thường gặp, annotation đặt trên public method được gọi qua bean proxy là phương án dễ dự đoán nhất. Private method không trở thành entrypoint proxy chỉ vì gắn `@Transactional`. Với class-based proxy, final method không được override để chặn; JDK proxy dựa trên interface có giới hạn riêng. Đừng dựa vào annotation có mặt trên source file như bằng chứng advice đã chạy.

**Tách bean khi cần giao dịch độc lập:** nếu `OrderService.place` phải gọi `PaymentService.charge` trong transaction/propagation riêng, inject `PaymentService` là bean và gọi qua reference đó. Test transaction cần chứng minh điều xảy ra khi phương thức có lỗi; không tự kết luận chỉ từ tương tác `verify(paymentService).charge(...)`.

## 7. Cache proxy: test một lần tính, nhiều lần lấy cache

### 7.1. @Cacheable thật sự thay đổi đường gọi

Khi method có `@Cacheable` được gọi qua proxy:

1. Cache interceptor xác định cache name và cache key (theo tham số hoặc cấu hình key).
2. Nếu cache có kết quả hợp lệ, interceptor có thể **trả ngay kết quả đó**, không chạy target.
3. Nếu cache chưa có, target chạy; kết quả được cache theo policy phù hợp để dùng cho lời gọi sau.

Bởi vậy, test có ý nghĩa phải chứng minh **target không chạy lại** khi cùng key. Trong ví dụ, bộ đếm `computations()` tăng đúng hai lần cho hai key khác nhau dù có ba lời gọi.

**Những điều phải tránh:**

- Gọi `new PriceService().quote("SKU-1")` hai lần rồi nghĩ cache không hoạt động. Object đó không đi qua caching proxy.
- Gọi một method trong cùng target để chuyển tiếp sang `@Cacheable` method rồi mong luôn có cache hit. Self-invocation có thể bypass proxy.
- Chỉ assert hai lần trả cùng giá trị. Nếu target là hàm thuần luôn trả kết quả giống nhau, test này vẫn pass **kể cả không có cache**. Cần đo số lần target chạy hoặc số lần outbound call thực.
- Không xóa cache giữa test. Một giá trị từ test trước có thể làm test hiện tại “xanh” hoặc “đỏ” sai lý do.

### 7.2. Những annotation liên quan

- `@Cacheable`: dùng cache để tránh tính lại khi key có kết quả.
- `@CachePut`: vẫn thực thi method và cập nhật cache theo cấu hình; không có cùng ý nghĩa “skip target” như `@Cacheable`.
- `@CacheEvict`: xóa cache entry hoặc vùng cache theo cấu hình khi xử lý mutation.
- `@Caching`: nhóm nhiều caching operations.

Ví dụ minh họa (nằm trong bean được proxy, không phải class đầy đủ):

```java
@CacheEvict(cacheNames = "prices", key = "#sku")
public void changePrice(String sku, BigDecimal newPrice) {
    repository.update(sku, newPrice);
}
```

Đoạn này giả định đã khai báo `repository`, `BigDecimal` và cache key matching. Nếu lúc đọc dùng key khác với key lúc evict, dữ liệu cũ có thể tiếp tục được trả. Thực tế còn cần xem transaction commit và thời điểm evict; xóa cache trước khi transaction thất bại có thể gây bất nhất tạm thời. Một test chỉ dùng `ConcurrentMapCacheManager` **không chứng minh** Redis TTL, distributed locking, serialization hay hành vi khi nhiều node cập nhật cùng lúc.

### 7.3. Test cache production và test cache tối thiểu khác nhau

Trong mục 4, `ConcurrentMapCacheManager` là cache **trong JVM** để chứng minh advisor và key. Nó phù hợp với mục tiêu “lời gọi thứ hai đi qua caching proxy không chạy target”. Nếu production dùng Redis/Caffeine với TTL, eviction, serialization và concurrency-specific behavior, cần **adapter/integration tests** với implementation production tương ứng.

Với cache có biến đổi dữ liệu, hãy kiểm tra **stale-data risk**, quy tắc invalidation và thời điểm cache entry thay đổi, không chỉ test happy path. Với parallel tests, shared cache có thể khiến bộ đếm và điều kiện miss/hit không còn độc lập.

## 8. Method security: không phải HTTP filter và không phải kiểm tra role trong method

### 8.1. @EnableMethodSecurity và @PreAuthorize

Spring Security có cơ chế chặn lời gọi method, độc lập với việc caller đến từ HTTP, scheduler hay messaging. Cấu hình:

```java
@EnableMethodSecurity
```

bật hạ tầng method security (với các tùy chọn phù hợp phiên bản/config). Một method có:

```java
@PreAuthorize("hasAuthority('doc:read')")
public String readSecret() {
    return "classified";
}
```

phải được gọi **thông qua bean proxy** thì authorization interceptor mới đánh giá biểu thức. Nếu quyền không đủ, một ngoại lệ phân quyền có thể được ném trước khi target chạy. Trong test mục 4, dùng `@WithMockUser` thiết lập `SecurityContext` giả lập mà không cần đăng nhập qua HTTP.

### 8.2. @WithMockUser kiểm tra chính xác điều gì?

`@WithMockUser(authorities = "doc:read")` thiết lập một Authentication thử nghiệm có authority chính xác `doc:read`. Khi method gọi qua proxy, biểu thức `hasAuthority('doc:read')` nhận được context đó. Với `doc:write`, test kiểm chứng bị từ chối.

Phân biệt hai trường thông dụng:

- `@WithMockUser(roles = "ADMIN")` thông thường tạo authority `ROLE_ADMIN`; phù hợp với `hasRole('ADMIN')` khi giữ quy ước prefix mặc định.
- `@WithMockUser(authorities = "doc:read")` cấp **chuỗi authority được chỉ định**, không tự thêm `ROLE_`; phù hợp khi biểu thức dùng `hasAuthority('doc:read')`.

Đừng lẫn `roles = "doc:read"` với `authorities = "doc:read"`; chúng có thể dẫn tới SecurityContext khác nhau và test đỏ dù không có bug trong business method.

**Test không có quyền** phải gọi bean proxy, ví dụ:

```java
@WithMockUser(authorities = "doc:write")
@Test
void cannotReadWithoutAuthority() {
    assertThrows(AccessDeniedException.class,
            () -> documentService.readSecret());
}
```

Đoạn này nằm trong class test đã có `documentService` và JUnit/Spring Security Test setup. Đừng mock `DocumentService` rồi verify nó bị gọi: mock có thể không mang advice của Spring, và “đã gọi mock” không chứng minh chính sách phân quyền.

### 8.3. Khi nào phải kiểm tra HTTP security?

Method security test **không** xác minh filter chain, session/CSRF, JWT decoder, URL matcher, `AuthenticationEntryPoint` hay cách exception được chuyển thành HTTP 401/403. Muốn bảo vệ hợp đồng REST, cần thêm kiểm thử qua `MockMvc`/`WebTestClient` hoặc integration test có security filter và cấu hình thật.

Ngược lại, một bài test HTTP chỉ kiểm tra “anonymous nhận 401” ở filter layer có thể chưa chứng minh rule `@PreAuthorize` trên service. Mỗi ranh giới giải quyết một câu hỏi; chọn cả hai nếu hệ thống dựa vào cả URL security và method security.

### 8.4. Kiểm thử không có Authentication

Nếu method có `@PreAuthorize` và không có Authentication trong `SecurityContext`, thường lời gọi bị từ chối và có thể phát sinh exception khác với trường hợp **đã đăng nhập nhưng thiếu quyền**, tùy cấu hình/phiên bản Spring Security. Để test có tính ổn định, phân biệt case **unauthenticated** và **authenticated but unauthorized** theo đúng policy; không viết một assertion chung cho mọi failure rồi bỏ qua HTTP translation.

Nếu muốn test method `@Secured` hoặc JSR-250 annotations, kiểm tra lựa chọn bật tương ứng (ví dụ `securedEnabled`, `jsr250Enabled` của `@EnableMethodSecurity`) và dependency/config liên quan. **`@PreAuthorize`** trong ví dụ chạy với cấu hình được bật phù hợp.

## 9. False positives: test xanh nhưng proxy chưa chứng minh được gì

Một số kiểu test thường khiến đánh giá sai:

**1. Tạo object bằng `new`:**

```java
DocumentService direct = new DocumentService();
String actual = direct.readSecret();
```

Trong ví dụ test, mã Java này **gọi target trực tiếp và có thể nhận `"classified"` dù không có authority** — vì annotation không tự chặn lời gọi. Đoạn này dùng để minh họa **bypass proxy**, không phải pattern production cho code cần method security.

**2. Mockito mock target annotated:** stub `when(annotatedService.someMethod()).thenReturn(...)` có thể thay toàn bộ target; nếu mục tiêu là chứng minh transaction/cache/security proxy, test mock chưa đi qua advice thật.

**3. Assert giá trị thuần:** hai lần gọi phương thức `@Cacheable` đều trả cùng giá không chứng minh cache, vì một target deterministic cũng có thể trả như vậy. Đếm số lần target thực thi hoặc quan sát outbound operation.

**4. Test `@Transactional` mà chưa có DB:** `verify(repository).save(...)` chỉ chứng minh lời gọi được gửi đi, không biết commit/rollback. Dùng transaction manager và DB test thích hợp.

**5. Test tự `@Transactional` rồi mặc định rollback của service:** dữ liệu rollback sau test có thể do **Spring Test**, không phải do annotation trên service. Gọi service ngoài test-managed transaction khi cần kiểm chứng commit/rollback của service.

**6. Có annotation nhưng thiếu enablement:** một class có `@Cacheable` nhưng không có `@EnableCaching`/cấu hình auto-config tương ứng có thể chạy như method thường. Tương tự method security và transaction manager. Test chức năng thật sẽ phát hiện nếu hiệu ứng không xuất hiện.

**7. Gọi self-invocation:** `this.saveTransactional()`/`this.cachedCall()` có thể tránh proxy; test cần tái hiện đường gọi thực tế từ caller ngoài target nếu annotation dự kiến áp dụng tại đó.

**8. Dùng `final` tùy tiện:** class/method final có thể cản class-based proxy; không mặc định mọi proxy hoạt động tương tự nhau. Thiết kế bean public entrypoints và chọn proxy strategy phù hợp.

**9. Cache/DB giữa các test không được reset:** test thứ hai trông có cache hit hoặc không còn dữ liệu dù logic sai. Cô lập dữ liệu, cache, SecurityContext và external resources theo test.

**10. `@WithMockUser` bị hiểu là kiểm thử đăng nhập thật:** nó giả lập Authentication phục vụ unit/integration boundary của method security, không kiểm tra password/JWT/session.

## 10. Tổ chức test thực tế theo phạm vi xác minh

Có thể chia test thành ba lớp bổ sung nhau:

1. **Unit test nghiệp vụ không Spring:** dùng constructor injection và test double để kiểm tra quyết định của service — nhanh, nhiều ca biên.
2. **Spring TestContext nhỏ cho proxy:** dùng `@SpringJUnitConfig` với advisor và bean thật để kiểm tra transaction, caching, method security ở method boundary — ví dụ trong bài.
3. **Integration/contract test với cấu hình production:** dùng `@SpringBootTest` hoặc slice thích hợp cùng DB/cache/security infrastructure thực, tùy câu hỏi cần bảo vệ — chi phí cao hơn nhưng chứng minh wiring/adapter.

Đừng cố gộp mọi cơ chế vào một test lớn. Ví dụ mục 4 đặt ba nhóm trong một file để thấy điểm giống nhau là proxy, nhưng trong dự án thật có thể tách thành `AuditTransactionTest`, `PriceCacheTest`, `DocumentMethodSecurityTest` theo trách nhiệm. Mỗi nhóm có thể chọn fixture/hạ tầng riêng: DB chính xác cho transaction, cache manager phù hợp cho caching, security context/authorization đúng cho method security.

**Một kế hoạch review trước khi viết test:**

| Câu hỏi | Cách chọn |
| --- | --- |
| Quy tắc chỉ dùng `if/else` và dữ liệu thuần? | JUnit test bằng `new` |
| Muốn chứng minh Spring thật sự tạo proxy? | Inject bean từ TestContext và kiểm tra `AopUtils` khi hữu ích |
| Muốn chứng minh rollback/commit? | Gọi bean proxy, dùng DB thật và đọc state sau transaction |
| Muốn chứng minh cache hit không chạy target? | Cấu hình CacheManager, gọi proxy lặp key, đếm target execution |
| Muốn chứng minh phân quyền method? | Bật method security, dùng `@WithMockUser`/SecurityContext, gọi proxy |
| Muốn chứng minh Redis/HTTP/production transaction manager? | Dùng integration/adapter test với hệ thống/config tương ứng |
| Test chạy chậm và dữ liệu chia sẻ gây flakiness? | Thu hẹp context, reset state/fixture, cô lập parallel execution |

## 11. Một số tình huống nâng cao cần tránh kết luận vội

### 11.1. Một method vừa có @Transactional vừa có @Cacheable

Khi nhiều advisor áp dụng, thứ tự interceptor và thời điểm cache update/evict so với transaction commit có thể ảnh hưởng tính nhất quán. Ví dụ một thao tác DB thất bại mà cache đã bị xóa hoặc cập nhật có thể tạo trạng thái tạm không đồng bộ. Không tự suy luận rằng mọi cache operation đều xảy ra **sau commit** chỉ vì method có `@Transactional`. Test phải nêu rõ kỳ vọng thời điểm cập nhật cache, chính sách transaction synchronization và config thật.

### 11.2. Transaction mới và propagation

Một method `@Transactional(propagation = Propagation.REQUIRES_NEW)` được gọi **qua proxy** có thể tạm ngưng transaction ngoài để mở transaction độc lập. Nếu method được gọi qua `this` trong cùng class, annotation có thể không được chặn như mong đợi. Với nghiệp vụ thanh toán/ghi audit, test bằng DB cần kiểm chứng những bản ghi thực sự commit hoặc rollback theo yêu cầu, không chỉ verify method được gọi.

### 11.3. Spring test và timeout preemptive

JUnit `assertTimeoutPreemptively(...)` có thể chạy callback trong **thread khác**. Spring Test transaction thường gắn với thread qua `ThreadLocal`; callback ở thread riêng có thể **không tham gia transaction được quản lý cho test**, dẫn tới side effect không rollback như người viết nghĩ. Với test DB, tránh thay tùy tiện `assertTimeout` bằng preemptive timeout chỉ để test nhanh. Nếu cần bảo đảm timeout cho I/O, dùng cơ chế timeout của client/driver hoặc test integration có kiểm soát và cleanup cụ thể.

### 11.4. Multiple transaction managers / cache managers

Trong ứng dụng nhiều datasource hoặc cache manager, một annotation có thể cần chỉ định manager tương ứng; nếu dùng nhầm, test có thể chạy nhưng state của hệ thống mục tiêu không được quản lý. Ví dụ `@Transactional("ordersTransactionManager")` hoặc `@Cacheable(cacheManager = "redisCacheManager", ...)` chỉ đúng khi bean thực sự được đăng ký. Test cần nhìn vào **hạ tầng được chọn** thay vì chỉ nhìn annotation.

### 11.5. Mock thay thế bean có thể làm biến mất behavior cần test

Khi dùng cơ chế thay bean bằng Mockito trong Spring test (tên annotation có thể khác theo phiên bản Spring Boot/Spring Framework), nếu mock **chính bean được annotate** thì proxy/advisor cần kiểm chứng có thể không còn đường đi giống production. Để test proxy, giữ target bean thật và chỉ mock **dependency ngoài phạm vi** (ví dụ HTTP client phía sau target) nếu cần.

### 11.6. TestContext caching không đồng nghĩa cô lập tài nguyên

Cache của Spring Test giữ ApplicationContext để tiết kiệm bootstrap, không cam kết reset cache contents, database, singleton mutable fields hoặc ngoại vi. Dùng fixture có setup/cleanup rõ, tận dụng transaction test chỉ khi mục tiêu phù hợp và hạn chế shared mutable state khi chạy song song. `@DirtiesContext` có thể buộc dựng context mới nhưng làm test chậm; không dùng như cách chữa mặc định cho dữ liệu bẩn nếu có thể dọn state đúng boundary.

## 12. Checklist QA cho proxy trong Spring TestContext

Trước khi viết bài test:

- **SUT:** cần kiểm tra logic thuần hay cơ chế Spring AOP? Nếu là proxy, test có lấy bean từ Spring context không?
- **Enablement:** context đã bật transaction manager, caching và method security đúng phạm vi chưa?
- **Proxy shape:** bean/method được gọi có khả năng được intercept không (entrypoint, visibility, final, interface, proxy strategy)?
- **Self-invocation:** có lời gọi `this.method()` khiến advice bị bỏ qua không?
- **Bằng chứng:** với transaction là commit/rollback data; với cache là hit/miss và số lần target chạy; với security là access granted/denied.
- **Fixtures:** test có cô lập DB/cache/SecurityContext và không phụ thuộc thứ tự test không?
- **Scope:** dùng context tối thiểu hay full Boot context? Nếu có nhiều manager, test có đúng bean/config production?
- **Ranh giới:** test chỉ chứng minh proxy in-memory hay còn chứng minh Redis/HTTP/JPA/DB production?

Sau khi test xanh:

- Có chắc test không pass chỉ vì mock target hoặc cache đã có giá trị từ lần chạy trước?
- Transaction có được kiểm tra sau lời gọi service bên ngoài test-managed transaction?
- Kết quả unauthorized có đến từ method interceptor chứ không phải HTTP filter không liên quan?
- Có dữ liệu bên ngoài còn lại sau test, đặc biệt khi dùng timeout preemptive hay propagation mới?
- Nếu refactor/đổi proxy mode, test còn xác minh đúng hợp đồng chứ không khóa vào chi tiết implementation của AOP?

**Ghi nhớ:** `@Transactional`, `@Cacheable` và `@PreAuthorize` thường phát huy tác dụng khi lời gọi đi qua **bean proxy do Spring quản lý**. Vì thế test về transaction/cache/method security phải dùng **Spring TestContext thích hợp, bean thật và assertion về hiệu ứng của advice**. Unit test `new Service(...)` vẫn rất giá trị để kiểm tra nghiệp vụ, nhưng không phải bằng chứng cho proxy.
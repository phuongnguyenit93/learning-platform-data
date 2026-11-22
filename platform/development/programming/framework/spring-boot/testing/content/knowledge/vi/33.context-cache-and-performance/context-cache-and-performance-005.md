# `@DirtiesContext` và chi phí dựng lại ứng dụng trong Spring Boot Test

## 1. Bài toán: một dòng annotation có thể khiến cả bộ test chậm đi

Giả sử project Spring Boot có 300 integration tests. Mỗi lớp test đều khai báo `@SpringBootTest`, kết nối repository, khởi tạo security, cấu hình Jackson, migrations, message listeners hoặc clients. Bạn thấy một test thay đổi biến của singleton bean làm test tiếp theo đôi khi thất bại. Để “chắc chắn sạch”, ai đó thêm `@DirtiesContext` lên **mọi lớp**. Test có thể bớt phụ thuộc trạng thái, nhưng Spring phải **đóng và dựng lại ApplicationContext** nhiều lần; thời gian CI tăng dù service code không đổi.

Đây không phải một vấn đề “có nên dùng annotation hay không” theo kiểu trắng–đen. `@DirtiesContext` là công cụ **đúng khi context thực sự không còn có thể tái sử dụng an toàn**. Vấn đề là phải phân biệt:

- **Context cache**: Spring TestContext Framework giữ lại một `ApplicationContext` đã load cho các tests có **cùng cấu hình** trong cùng JVM.
- **Mutable test data/state**: dữ liệu trong DB, message queue, static fields hoặc singleton có thể tồn tại qua nhiều tests; trạng thái đó **không tự sạch** chỉ vì một test method đã kết thúc.
- **`@DirtiesContext`**: yêu cầu Spring **loại context khỏi test context cache và đóng nó** ở một mốc cụ thể. Test cần cùng context key tiếp theo sẽ phải dựng context mới.
- **Chi phí khởi động lại**: component scan, `BeanFactory`/auto-configuration, bean instantiation/post-processing, proxying, connection pools, JPA EntityManagerFactory, Liquibase/Flyway, embedded web server và integration resource lifecycle có thể phải diễn ra lại.
- **Cách reset nhẹ hơn**: rollback transaction, `@Sql`, fixture reset, `Mockito` mock reset, clear cache, đóng resource đúng cách; thường sạch được **dữ liệu** mà không đập cả **ApplicationContext**.

**Mục tiêu học tập** (nhóm cha: *Context cache và hiệu năng*):

1. Hiểu chính xác Spring TestContext cache, context key, reuse, LRU eviction và phạm vi một JVM.
2. Hiểu `@DirtiesContext` khác `@Transactional`, `@Rollback`, `@Sql`, `@AfterEach` và `@MockBean` reset như thế nào.
3. Nắm **hai method modes** và **bốn class modes**, thời điểm đóng context trước/sau method/class.
4. Phân biệt `@DirtiesContext` **trên method** và **trên class**; lưu ý các modes có thể kết hợp.
5. Biết `hierarchyMode = EXHAUSTIVE/CURRENT_LEVEL` khi dùng `@ContextHierarchy` và tránh vô tình loại context của nhiều nhánh.
6. Biết vì sao Spring Boot 3.3 `@MockBean`, `@ActiveProfiles`, `@TestPropertySource`, `@SpringBootTest(properties=...)` và `@DynamicPropertySource` có thể ảnh hưởng cache keys.
7. Viết **project Java 17 / Spring Boot 3.3.5 / JUnit Jupiter** chạy được, quan sát chính xác **bean instance identity** và callback `@PreDestroy`.
8. Có **14 phương thức JUnit `@Test`**, kiểm reuse, `AFTER_METHOD`, `BEFORE_METHOD`, `BEFORE_EACH_TEST_METHOD`, `AFTER_EACH_TEST_METHOD`, `AFTER_CLASS` và cache key khác nhau.
9. Biết **đo** số context cache hits/misses, context startup và suite runtime trước khi tối ưu; không bịa số giây hay dùng timing assertion dễ flaky.
10. Hiểu những giới hạn với DB ngoài JVM, Testcontainers, web server thật, các tests chạy parallel và Gradle forks.
11. Xây chiến lược tối ưu hiệu năng suite mà không làm giảm tính độc lập của từng test.

**Phiên bản cố định:** Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, JUnit Jupiter. Ví dụ không mở HTTP server, không Docker, không DB; phần về database, JPA, Spring MVC và Testcontainers là **hướng áp dụng bổ sung**, không giả vờ chúng đã được kiểm bởi mã thử nghiệm nhỏ.

## 2. Cơ chế cache của Spring TestContext: cùng cấu hình, không nhất thiết cùng lớp

Khi một test dùng `@SpringBootTest` hoặc `@ContextConfiguration`, Spring TestContext tìm `ApplicationContext` trong **static cache** của JVM chạy tests. Nếu cache có entry khớp **context cache key**, Spring dùng lại context và bean instances. Nếu không có, framework khởi tạo context, thêm vào cache và test sử dụng nó.

~~~text
Test A -- key K1 --> cache miss --> load AppContext #1
Test B -- key K1 --> cache hit  --> reuse AppContext #1
Test C -- key K2 --> cache miss --> load AppContext #2
Test D -- key K1 --> cache hit  --> reuse AppContext #1
Test E -- key K1 --> @DirtiesContext AFTER_METHOD
                           |
                           +--> evict K1 + close #1
Test F -- key K1 --> cache miss --> load AppContext #3
~~~

**Cache key** không phải chỉ là tên lớp test. Framework tính key từ các thành phần cấu hình như:
- `locations` và `classes` của `@ContextConfiguration`.
- `contextInitializerClasses`.
- `contextCustomizers`: ví dụ Boot test customizers, `@DynamicPropertySource`, `@MockBean`/`@SpyBean` (Spring Boot 3.3); các bean override khác ở những phiên bản mới.
- `contextLoader`.
- `parent` khi dùng `@ContextHierarchy`.
- `activeProfiles` từ `@ActiveProfiles`.
- `propertySourceDescriptors`/`propertySourceProperties` từ `@TestPropertySource`, `@SpringBootTest(properties=...)`.
- `resourceBasePath` cho web application contexts.

Hai test classes có cùng `@SpringBootTest` và cùng environment có thể chia sẻ context. Hai classes trông tương tự nhưng một class có `@ActiveProfiles("qa")`, một class có thêm mock bean hoặc khác inline property có thể tạo **hai cache keys**, dù chúng không dùng `@DirtiesContext`.

**Đừng dùng `ApplicationContext.getId()` làm bằng chứng instance được dựng mới.** Một context mới có thể được đặt **cùng chuỗi ID** theo tên application. Trong bài, dùng dấu `UUID` tạo trong constructor của một Spring singleton bean và sự kiện `@PreDestroy` để quan sát identity/lifecycle.

### 2.1. Cache là của Spring test, không phải @Cacheable hay cache nghiệp vụ

`ContextCache` giữ **ApplicationContext instances**. Đây không phải cache Redis, Hibernate second-level cache hoặc kết quả `@Cacheable` của service. `@DirtiesContext` đóng **cả container**, chứ không chỉ `cacheManager.clear()`. Một test cần clear business cache không nhất thiết cần đánh dấu dirty.

**Ví dụ:** Bạn đã thêm một record vào cache in-memory để test logic invalidation. Thay vì:
~~~java
@DirtiesContext
@Test
void cacheInvalidation() { ... }
~~~

hãy cân nhắc xóa đúng cache trong `@BeforeEach`/`@AfterEach`, hoặc dùng fixture riêng, nếu context và bean definitions vẫn ổn. Snippet trên chỉ minh họa cách gắn annotation; không phải method độc lập.

### 2.2. LRU, default max size 32, và phạm vi một JVM

Spring Framework 6.1 mặc định có **context cache max size = 32**. Khi vượt giới hạn, một chính sách **Least Recently Used (LRU)** evict/close context ít được dùng gần đây. Có thể chỉnh bằng **JVM system property** `spring.test.context.cache.maxSize`, ví dụ 16 hoặc 64 sau khi đo.

**Không nhầm** `spring.test.context.cache.maxSize` với một ứng dụng `application.properties` bình thường: đây là **system property/SpringProperties của Spring TestContext framework**, được đọc trong test JVM. Ví dụ Gradle ở mục 6 cấu hình `systemProperty` cho task `test`.

Nếu Gradle cấu hình nhiều **forked JVMs**, mỗi JVM có static cache riêng, không chia sẻ bean instances hay hits/misses. `forkEvery=1` hoặc chia nhiều test workers có thể gây mất reuse giữa classes dù chúng có cùng config. Tương tự, khi IDE chạy từng test class trong process riêng, không thể kỳ vọng reuse từ một lần chạy trước.

**LRU eviction không có nghĩa `@DirtiesContext` đã được gọi.** Hai lý do đều có thể đóng context, nhưng mục đích khác nhau. Đọc logs/cache stats để phân biệt.

### 2.3. Cache failure threshold là một khái niệm khác

Kể từ Spring Framework **6.1**, cấu hình `spring.test.context.failure.threshold` (mặc định **1**) giới hạn số lần cố load một context bị lỗi cho **cùng cache key**, để các tests không cùng thử khởi động một context hỏng hàng chục lần. Một test sau có thể nhận `IllegalStateException` rằng context load attempt đã bị bỏ qua.

Đây **không phải cache size**, **không phải thời gian khởi động**, và **không phải `@DirtiesContext` tự động giải quyết lỗi**. Khi gặp failure threshold, hãy điều tra **lỗi khởi tạo đầu tiên** (DB unreachable, bean config, migration, property sai), không tăng threshold hoặc đánh dấu dirty bừa để che nguyên nhân.

## 3. `@DirtiesContext` thực chất có tác động gì?

Annotation `org.springframework.test.annotation.DirtiesContext` nói với TestContext rằng **ApplicationContext liên quan đã “bẩn”** — ví dụ test đã làm biến dạng một bean singleton, một bean definition hoặc trạng thái mà test khác không thể reset an toàn. Framework sẽ **remove khỏi context cache, close context** theo phase được cấu hình. Lần sau nếu một test cần cùng context key, một instance mới được tạo.

~~~text
Test method dùng Context A
       |
       +-- thay đổi state không thể/không nên reset thủ công
       |
       +-- mark dirty theo @DirtiesContext
                 |
                 +-- Spring TestContext remove cache entry
                 +-- Context A.close()
                 |      - @PreDestroy / DisposableBean / lifecycle callbacks
                 |      - hủy singleton beans, pools/resources thuộc context
                 +-- Test sau cần key đó -> xây Context B
~~~

**Không phải “reset beans in-place”.** Spring không gọi một hàm `reset()` trên bean hiện có và tái sử dụng instance cũ. Nó đóng container cũ; những bean được tạo lại là những instances mới. Context creation có thể tốn nhiều hơn nhiều so với reset vài rows trong test database.

**Không đảm bảo reset external state.** Nếu context dùng PostgreSQL external database, Kafka/RabbitMQ broker hoặc một static Testcontainers container, đóng Spring context **không tự xóa toàn bộ tables, topics, queues hay files**. Những resources có vòng đời **ngoài** context có thể vẫn tồn tại. Không chọn `@DirtiesContext` chỉ để “xóa dữ liệu” mà chưa xác minh nguồn state thật.

**Không đồng nghĩa test fail.** `@DirtiesContext` không phải assertion. Nó có thể được dùng dù test PASS, để thay đổi lifecycle của context cho test tiếp theo.

### 3.1. Annotation mặc định

~~~java
// Ở cấp method:
@DirtiesContext
@Test
void someTest() {
    // Mặc định methodMode = AFTER_METHOD
}
~~~

~~~java
// Ở cấp class:
@DirtiesContext
@SpringBootTest
class SomeTests {
    // Mặc định classMode = AFTER_CLASS
}
~~~

Hai snippet là ví dụ annotation, không phải lớp chạy độc lập. Sự khác biệt **mặc định** rất quan trọng: method được dirty **sau method**, class được dirty **sau toàn bộ class**. Không được suy rằng gắn `@DirtiesContext` trên class sẽ load context mới trước **mỗi** test method.

### 3.2. Toàn bộ sáu thời điểm (phases)

| Cấp | Tham số | Mode | Hành vi |
|---|---|---|---|
| Method | `methodMode` | **`AFTER_METHOD`** (default) | Sau method hiện tại, close/evict context; test tiếp theo sẽ load mới nếu cần cùng key |
| Method | `methodMode` | `BEFORE_METHOD` | Trước method hiện tại, loại context cache hiện có để method dùng context mới |
| Class | `classMode` | **`AFTER_CLASS`** (default) | Sau toàn bộ test class, loại/đóng context |
| Class | `classMode` | `BEFORE_CLASS` | Trước class, bắt đầu từ một context mới nếu key cũ đã cache |
| Class | `classMode` | `BEFORE_EACH_TEST_METHOD` | Trước **mỗi** method, loại/đóng context trước đó và load mới cho method |
| Class | `classMode` | `AFTER_EACH_TEST_METHOD` | Sau **mỗi** method, loại/đóng context, method kế tiếp cần context mới |

**Cú pháp chuẩn:**

~~~java
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
@Test
void useFreshContext() { ... }
~~~

~~~java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
@SpringBootTest
class ExpensiveTestClass { ... }
~~~

Đây là snippets minh họa, không phải mã copy để compile độc lập. Ở cấp class phải dùng `classMode`; ở cấp method phải dùng `methodMode`. Gán `methodMode` ở annotation gắn lên class hoặc `classMode` lên method **không có ý nghĩa cho phase mong muốn**.

**Kết hợp:** Có thể đặt annotation ở cả class và method; Spring tôn trọng cả hai phases. Ví dụ class `BEFORE_EACH_TEST_METHOD` cộng một method `AFTER_METHOD` có thể đóng context cả trước và sau method đó — rất tốn kém. Tránh chồng annotations không có lý do.

### 3.3. `BEFORE_*` và dependency injection

Khi context bị dirty **trước một method**, Spring TestContext chạy những listeners hỗ trợ và xử lý **re-injection** khi cần. Trong Boot 3.3/Framework 6.1, `DirtiesContextBeforeModesTestExecutionListener` và `DependencyInjectionTestExecutionListener` làm việc theo listener ordering để injected test fields trỏ tới context mới. Đó là lý do bài có thể dùng `@Autowired StateProbe` ở `BEFORE_METHOD`/`BEFORE_EACH_TEST_METHOD` tests.

**Đừng cache Spring bean tham chiếu vào static test field rồi cố dùng sau khi context bị đóng.** Bean cũ có thể đã nhận `@PreDestroy`, pools đã đóng; gọi nó có thể sai và tạo test xanh giả nếu bean không kiểm trạng thái. Lưu **immutable marker String** của bean cũ để so sánh, không giữ reference rồi dùng như service còn sống.

## 4. Tại sao context rebuild có thể rất đắt?

Một `@SpringBootTest` dùng **full application context** có thể:
- Quét classes, xử lý `@Configuration`, `@Conditional`, `@ConfigurationProperties`, auto-configuration.
- Tạo singleton beans, proxy AOP (`@Transactional`, `@Async`, security method interceptors), validation provider.
- Khởi tạo Jackson `ObjectMapper`, Hibernate ORM `EntityManagerFactory`, connection pool và caches.
- Khởi tạo embedded HTTP server nếu dùng `webEnvironment = RANDOM_PORT`, tạo socket/port mới.
- Chạy Flyway/Liquibase migrations hoặc DB initialization, tùy cấu hình.
- Tạo message listeners, schedulers, clients, observability exporters.
- Khai báo queue/broker resources hoặc khởi động Testcontainers nếu thuộc bean lifecycle/config.
- Thực hiện `@PostConstruct`, `InitializingBean`, `SmartLifecycle`, startup events.
- Đăng ký rồi dọn resources trong `@PreDestroy`/`close()` khi context bị đóng.

**Chi phí đo được = số context load × startup cost thực tế + thời gian đóng context + tài nguyên side effects.** Đây là mô hình trực giác, không phải công thức số học chính xác (load cost phụ thuộc warm JVM, classloading, resource reuse, parallelism, OS, DB). Một ứng dụng nhỏ có thể rebuild rất nhanh; một hệ dùng JPA/Testcontainers/migrations có thể chậm đáng kể. Không được gắn một con số “mỗi @DirtiesContext tốn N giây” nếu chưa đo trên project thật.

Ví dụ so sánh lý thuyết:

~~~text
10 test classes cùng cache key, mỗi lớp 5 methods:

Không dirty:
  Context #1 load 1 lần
  50 test methods chia sẻ context #1
  (Mỗi method vẫn phải reset data đúng cách!)

Dirty AFTER_CLASS trên mọi class:
  Context #1 load trước class 1 -> close sau class 1
  Context #2 load trước class 2 -> close sau class 2
  ...
  Ít nhất 10 lần load context nếu tất cả cùng key.

Dirty AFTER_EACH_TEST_METHOD trên mọi class:
  Mỗi method hoàn thành thì context bị đóng
  Context sẽ được nạp lại cho method tiếp theo.
  Có thể ~50 context loads cho 50 methods.

Các con số trên là số load theo cấu hình giả định,
không phải thời gian đo và không xét LRU/parallel/forks.
~~~

**Trường hợp `BEFORE_EACH_TEST_METHOD`:** Context có thể bị loại trước từng method, gồm cả context mới load cho test instance trước phase; chi tiết số load phụ thuộc lifecycle/injection. Đừng mặc định con số startup chính xác bằng số methods cho mọi cấu hình/phương thức chạy; hãy đọc cache stats và runtime logs.

### 4.1. `@SpringBootTest` mặc định không mở server thật

Boot `@SpringBootTest` mặc định dùng **MOCK web environment**, nếu project có Spring MVC; không mở một TCP HTTP server thật. `@SpringBootTest(webEnvironment=RANDOM_PORT)` mới khởi động embedded server trên port ngẫu nhiên. Project runnable dùng **`WebEnvironment.NONE`** để cô lập hiệu ứng context rebuild và tránh chi phí HTTP server không cần thiết.

**Không dùng `@DirtiesContext` để “reset port”** nếu yêu cầu chỉ là gửi lại request test: Spring MVC MockMvc không cần server port. Ngược lại, nếu một test thật sự thay đổi bean definitions/server configuration, context isolation là hợp lệ.

### 4.2. Một vài chi phí ẩn

- **Restart listeners/schedulers:** Background thread chưa stop sạch sẽ làm context mới hoạt động song song với task cũ; cần kiểm lifecycle, không chỉ tăng dirty count.
- **Đóng connection pool:** Context bị close có thể làm request async từ test trước nhận connection đã đóng. Bảo đảm chờ async tasks hoàn thành và cleanup trước khi dirty.
- **Thay đổi test properties:** Mỗi tổ hợp `@SpringBootTest(properties=...)` tạo key riêng, có thể phát sinh context loads ngoài dự kiến.
- **Mocks trong cache key:** Hai lớp có sets `@MockBean` khác nhau ở Boot 3.3 có thể không chia sẻ context. Đừng tạo một mock override vô ích ở mỗi class.
- **Context hierarchy:** Dirty một nhánh với EXHAUSTIVE có thể ảnh hưởng những contexts khác chia sẻ ancestor.
- **LRU churn:** Nếu suite cần >32 cấu hình khác nhau, context cũ có thể bị evict dù không có annotation dirt.
- **Gradle forks:** Mỗi fork khởi tạo cache mới; không xem startup logs trong fork A là đã làm ấm fork B.

## 5. Dùng `@DirtiesContext` khi nào là chính đáng?

Những trường hợp thường **có thể cần**:

1. Test **thay đổi bean definition** hoặc `BeanFactory` mà không thể hoàn nguyên.
2. Test thay đổi state của một singleton bean phức tạp, không có reset API an toàn và test tiếp theo cần trạng thái lúc startup.
3. Test chạm tới Spring-managed context resource như JMX MBean registration và cần cleanup container để tránh name conflicts (Spring Boot có ví dụ JMX + DirtiesContext).
4. Test sửa application configuration/runtime environment gắn chặt với context, không thể đảm bảo rollback/cô lập theo test.
5. Test `@ContextHierarchy` cần cô lập nhánh context cụ thể và hiểu rõ consequences của hierarchyMode.
6. Test đang xác minh **lifecycle khởi động/đóng context**; dirty là chính đối tượng cần quan sát.

Những trường hợp thường **không cần**:

1. **Insert/update DB rows**: dùng transaction rollback, `@Sql`, cleanup fixture hoặc database/schema riêng.
2. **Mockito mock stubbing/calls**: reset mocks giữa tests; Boot 3.3 `@MockBean` có hỗ trợ auto-reset sau mỗi test method theo mặc định.
3. **@Cacheable data**: clear cache đúng key hoặc `CacheManager` phù hợp.
4. **Static state**: reset fixture static cụ thể; dirty Spring context **không reset static variables**.
5. **ThreadLocal/MDC/security context**: clear theo lifecycle của test/request; dirty không đảm bảo xóa các giá trị trên mọi threads.
6. **Messages trong external broker**: purge test queues/topic hoặc dùng names/consumer groups riêng; dirty không “xóa broker”.
7. **Files trên disk**: dùng temporary directory và cleanup.
8. **HTTP test client/session**: tạo client mới hoặc clear cookies/session; không đập ApplicationContext nếu không cần.
9. **Migrations/test database external**: reset schema/transaction đúng; đóng context không drop external DB trừ khi lifecycle được cấu hình như vậy.
10. **Test order dependency**: sửa fixture/test isolation thay vì thêm dirty để giấu sự phụ thuộc.

**Quy tắc quyết định:** Hãy hỏi “chính xác state nào bị nhiễm?”, “ai sở hữu state đó?”, “có reset/rollback có kiểm chứng được không?”, “nếu reset không khả thi, dirty ở mốc nhỏ nhất nào?”, và “cache misses/startup tăng bao nhiêu sau thay đổi?”.

## 6. Project runnable: Java 17, Spring Boot 3.3.5, 14 JUnit tests

Ví dụ có một singleton **`StateProbe`** với:
- `id()` là **UUID được tạo khi bean khởi tạo**.
- `generation()` là số lần tạo StateProbe trong **JVM hiện tại**, giúp quan sát tăng/giảm (không assert số tuyệt đối).
- `increment()`/`reset()` mô phỏng mutable bean state.
- `@PreDestroy` ghi UUID vào một **static set** để test chứng minh context cũ thực sự được đóng. Static set này chỉ là **test instrumentation**, không phải business state.

Test suite gồm:
- `ContextReuseTest`: 3 tests, reuse cùng context; reset biến đếm chứ không dirty.
- `DirtiesAfterMethodTest`: 2 tests có order minh họa, lần đầu dirty AFTER_METHOD; lần sau marker khác và marker cũ đã đóng.
- `DirtiesBeforeMethodTest`: 2 tests có order minh họa, lần thứ hai dirty BEFORE_METHOD; ngữ nghĩa chính xác với dependency reinjection.
- `DirtiesBeforeEachTest`: 2 tests, context tươi trước từng method.
- `DirtiesAfterEachTest`: 2 tests, context cũ đóng sau từng method.
- `DirtiesAfterClassTest`: 1 test trong class gắn default AFTER_CLASS; minh họa code và chính sách lifecycle.
- `BlueConfigurationTest` và `RedConfigurationTest`: mỗi lớp 1 test, properties khác nhau → cache keys khác nhau ngay cả khi **không** dirty.

**Tổng: 3+2+2+2+2+1+1+1 = 14 phương thức `@Test`.**

### 6.1. Cây thư mục

~~~text
settings.gradle
build.gradle
src/main/java/demo/cache/CacheDemoApplication.java
src/main/java/demo/cache/StateProbe.java
src/test/resources/junit-platform.properties
src/test/resources/application.properties
src/test/java/demo/cache/ContextReuseTest.java
src/test/java/demo/cache/DirtiesAfterMethodTest.java
src/test/java/demo/cache/DirtiesBeforeMethodTest.java
src/test/java/demo/cache/DirtiesBeforeEachTest.java
src/test/java/demo/cache/DirtiesAfterEachTest.java
src/test/java/demo/cache/DirtiesAfterClassTest.java
src/test/java/demo/cache/BlueConfigurationTest.java
src/test/java/demo/cache/RedConfigurationTest.java
~~~

### 6.2. Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'dirties-context-cost-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Một test JVM để quan sát static ContextCache reuse;
    // nếu đổi forks, cache không còn được chia sẻ.
    maxParallelForks = 1
    forkEvery = 0

    // JVM system property của TestContext framework.
    systemProperty 'spring.test.context.cache.maxSize', '32'

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích:** `spring-boot-starter` đủ cho Spring ApplicationContext và logging, không thêm web/JPA để kết quả quan sát tập trung vào context lifecycle. `starter-test` mang JUnit Jupiter và Spring TestContext. Config `maxParallelForks=1`/`forkEvery=0` giữ một test JVM để hiện rõ cache reuse; khi production CI cần parallel forks, cân nhắc đổi có chủ đích và chấp nhận mỗi worker có cache riêng.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Điều này tắt **JUnit Jupiter method/class parallel execution**, tránh một test đang dirt context thì test khác đồng thời lấy từ cache. Nó không ảnh hưởng threads được ứng dụng tạo; chỉ kiểm scheduling tests trong bài. Không phải lời khuyên “mọi dự án phải tắt parallel tests”; một suite có data isolation và không dùng dirt/mocks có thể chạy song song. Riêng ví dụ này cần quan sát lifecycle không bị nhiễu.

**src/test/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Logger `org.springframework.test.context.cache` bật thống kê hits/misses/cache size và giúp hiểu vì sao context được tái sử dụng. Vì Spring TestContext có thể log trước khi Boot logging system khởi tạo, một số logs ban đầu có thể không xuất hiện trong IDE; nếu cần thống kê đầy đủ hãy cấu hình logging sớm qua test logging backend và giữ nguyên JVM. Trong dự án lớn bật DEBUG có thể sinh nhiều logs; chỉ dùng khi phân tích.

### 6.3. Application

**src/main/java/demo/cache/CacheDemoApplication.java**

~~~java
package demo.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

Không có embedded HTTP server vì project không thêm `spring-boot-starter-web`, và các tests dùng `WebEnvironment.NONE`.

### 6.4. Bean có dấu identity và callback đóng

**src/main/java/demo/cache/StateProbe.java**

~~~java
package demo.cache;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class StateProbe {

    private static final AtomicInteger CONSTRUCTED =
            new AtomicInteger();

    private static final Set<String> CLOSED_IDS =
            ConcurrentHashMap.newKeySet();

    private final String id = UUID.randomUUID().toString();

    private final int generation =
            CONSTRUCTED.incrementAndGet();

    private final AtomicInteger counter = new AtomicInteger();

    public String id() {
        return id;
    }

    public int generation() {
        return generation;
    }

    public int increment() {
        return counter.incrementAndGet();
    }

    public int count() {
        return counter.get();
    }

    public void reset() {
        counter.set(0);
    }

    public static boolean wasClosed(String id) {
        return CLOSED_IDS.contains(id);
    }

    public static int totalConstructed() {
        return CONSTRUCTED.get();
    }

    @PreDestroy
    void onDestroy() {
        CLOSED_IDS.add(id);
    }
}
~~~

**Vì sao marker tin cậy hơn `context.getId()`?** Mỗi **StateProbe bean instance** trong mỗi context có `UUID.randomUUID()`. Nếu framework tạo context mới, nó phải tạo **StateProbe instance mới**, nên ID khác. `@PreDestroy` ghi ID cũ vào set khi bean bị destroy; test có thể kiểm close xảy ra. UUID collision là không đáng kể trong phạm vi học tập, nhưng nếu cần chứng minh reference identity tuyệt đối có thể so bean references trực tiếp khi cả hai còn sống (ở bài chỉ lưu ID để không giữ reference tới closed bean).

**Lưu ý về static counters:** `CONSTRUCTED`/`CLOSED_IDS` tồn tại theo JVM, **không được reset khi Spring context bị dirty**. Không assert `generation()==1` cho một test không kiểm soát thứ tự classes; JUnit/Gradle có thể thay đổi order. Dùng marker unique và quan hệ **same/different** thay vì con số tạo context tuyệt đối.

`@PreDestroy` được kích hoạt khi Spring đóng/destroy bean thuộc context. Nó không có nghĩa JVM hủy class/static state. Không dùng `System.gc()` hoặc `finalize()` như cách xác minh context close.

## 7. Test thứ nhất: reuse cùng context, reset state thủ công

**src/test/java/demo/cache/ContextReuseTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextReuseTest {

    private static final AtomicReference<String> FIRST =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @Autowired
    ApplicationContext context;

    @BeforeAll
    static void clearLocalObservation() {
        FIRST.set(null);
    }

    @BeforeEach
    void verifyReuseAndResetData() {
        String oldMarker = FIRST.getAndSet(probe.id());

        if (oldMarker != null) {
            assertEquals(
                    oldMarker, probe.id(),
                    "Same class/config should reuse the context");
        }

        assertSame(probe, context.getBean(StateProbe.class));

        // Reset đúng dữ liệu test, không rebuild container.
        probe.reset();
    }

    @Test
    void firstOperationUsesFreshData() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
    }

    @Test
    void anotherOperationIsIndependent() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
        assertEquals(2, probe.increment());
    }

    @Test
    void thirdOperationDoesNotRequireDirtyContext() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
    }
}
~~~

**Đúng 3 JUnit `@Test`.** Đây là ví dụ hữu ích khi bean state **có API reset được kiểm soát**: mỗi method bắt đầu counter=0, còn `StateProbe.id()` **giữ nguyên**. Không cần `@DirtiesContext`, tránh context startup lặp lại.

`AtomicReference` lưu ID từ lần kiểm trước để chứng minh reuse **trong một class không chạy parallel**. Test không phụ thuộc thứ tự ba test methods: tất cả đều chạy `@BeforeEach` reset data và assert cùng context. `@BeforeAll` clear local observation khi class bắt đầu. Các classes khác trong suite có thể cùng sử dụng context trước/sau class này, nhưng không bị interleave nếu JUnit parallel disabled.

**Giới hạn:** Phép reset chỉ là reset `AtomicInteger` trong một bean. Với business state trải rộng nhiều caches/DB/external queues, reset đúng có thể phức tạp hơn. Nếu không thể chứng minh fixture isolation, hãy chọn cô lập khác hoặc dirty có chủ đích.

## 8. `AFTER_METHOD`: một test làm bẩn, test kế tiếp có context mới

**src/test/java/demo/cache/DirtiesAfterMethodTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class DirtiesAfterMethodTest {

    private static final AtomicReference<String> BEFORE =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void resetObservation() {
        BEFORE.set(null);
    }

    @Test
    @Order(1)
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void firstTestMarksItsContextDirtyAfterCompletion() {
        BEFORE.set(probe.id());

        probe.reset();
        assertEquals(1, probe.increment());
    }

    @Test
    @Order(2)
    void secondTestGetsRebuiltContext() {
        String old = BEFORE.get();

        assertNotNull(old);
        assertNotEquals(old, probe.id());

        assertTrue(
                StateProbe.wasClosed(old),
                "Old bean must receive @PreDestroy");
        assertEquals(0, probe.count());
    }
}
~~~

**Đúng 2 `@Test`.** Test thứ nhất **không tự gọi `context.close()`**: Spring `DirtiesContextTestExecutionListener` xử lý annotation **sau method**, remove context cache entry và đóng Spring container. Test thứ hai nhận một `StateProbe` mới, không còn counter=1 của instance cũ. `wasClosed` chứng minh `@PreDestroy` ở bean cũ đã chạy.

`@TestMethodOrder` chỉ dùng trong bài để **chứng minh lifecycle theo hai bước có chủ đích**, không phải pattern khuyến nghị cho business tests. Ở project thật, những tests ứng dụng nên độc lập thứ tự. Có thể kiểm cache behavior bằng logs và kiểm mỗi class riêng thay vì tạo suite dựa vào order.

**Không suy từ “second has counter=0” rằng dirty đã xảy ra**: test có thể reset counter trước đó. Chính **marker khác + closed old marker** mới là bằng chứng rõ về rebuild ở ví dụ.

## 9. `BEFORE_METHOD`: loại context trước một method được chỉ định

**src/test/java/demo/cache/DirtiesBeforeMethodTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class DirtiesBeforeMethodTest {

    private static final AtomicReference<String> EARLIER =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void resetObservation() {
        EARLIER.set(null);
    }

    @Test
    @Order(1)
    void captureContextBeforeFreshMethod() {
        EARLIER.set(probe.id());
        probe.reset();
        assertEquals(1, probe.increment());
    }

    @Test
    @Order(2)
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
    void freshContextIsInjectedBeforeThisMethod() {
        String prior = EARLIER.get();

        assertNotNull(prior);
        assertNotEquals(prior, probe.id());
        assertTrue(StateProbe.wasClosed(prior));
        assertEquals(0, probe.count());
    }
}
~~~

**Đúng 2 `@Test`.** Khác `AFTER_METHOD`, method thứ hai **chủ động yêu cầu context mới trước khi chạy**. Spring test listeners hỗ trợ dependency re-injection nên `@Autowired probe` của method thứ hai trỏ đến bean mới khi method body được thực thi.

**Khi nào cân nhắc BEFORE_METHOD?** Một test cụ thể cần một context có state ban đầu ngay trước khi method thực hiện thao tác phá cấu hình, nhưng các methods phía trước có thể đã tác động context. Đây vẫn là giải pháp đắt. Nếu chỉ cần fresh database rows, dùng fixture reset hoặc transaction rollback thay thế.

## 10. Class mode `BEFORE_EACH_TEST_METHOD`: reset cả container trước từng test

**src/test/java/demo/cache/DirtiesBeforeEachTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode =
                DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class DirtiesBeforeEachTest {

    private static final AtomicReference<String> PREVIOUS =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void clearObservation() {
        PREVIOUS.set(null);
    }

    @BeforeEach
    void verifyFreshBean() {
        String earlier = PREVIOUS.getAndSet(probe.id());

        if (earlier != null) {
            assertNotEquals(earlier, probe.id());
            assertTrue(StateProbe.wasClosed(earlier));
        }

        assertEquals(0, probe.count());
    }

    @Test
    void firstOperation() {
        assertEquals(1, probe.increment());
    }

    @Test
    void secondOperation() {
        assertEquals(1, probe.increment());
    }
}
~~~

**Đúng 2 `@Test`.** Spring TestContext dirty trước mỗi method. `PREVIOUS` là static marker dùng cho demonstration, không bị reset bởi dirty; nhờ đó `@BeforeEach` có thể kiểm bean cũ khác ID và đã đóng. Không cần ép thứ tự methods vì mỗi method có cùng behavior.

**Điểm về chi phí:** Chỉ thay đổi counter là bài toán nhỏ, nên dùng classMode BEFORE_EACH ở đây **chỉ để quan sát**, không phải lựa chọn thiết kế tối ưu. Với application lớn, mọi method đều có thể làm Spring dựng lại container, dẫn đến độ trễ CI không cần thiết.

## 11. Class mode `AFTER_EACH_TEST_METHOD`: dirty sau mỗi method

**src/test/java/demo/cache/DirtiesAfterEachTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode =
                DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DirtiesAfterEachTest {

    private static final AtomicReference<String> PREVIOUS =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void clearObservation() {
        PREVIOUS.set(null);
    }

    @BeforeEach
    void verifyLastMethodWasCleanlyClosed() {
        String earlier = PREVIOUS.getAndSet(probe.id());

        if (earlier != null) {
            assertNotEquals(earlier, probe.id());
            assertTrue(StateProbe.wasClosed(earlier));
        }

        probe.reset();
    }

    @Test
    void oneOperationCompletesAndContextWillClose() {
        assertEquals(1, probe.increment());
    }

    @Test
    void anotherOperationGetsANewBean() {
        assertEquals(1, probe.increment());
    }
}
~~~

**Đúng 2 `@Test`.** Mỗi method kết thúc thì context bị dirty theo **class-level AFTER_EACH_TEST_METHOD**. Đến method tiếp theo, context không còn trong cache và Spring phải load lại. Test xác minh marker khác và old bean đã nhận @PreDestroy.

**Khác với BEFORE_EACH:** `BEFORE_EACH_TEST_METHOD` loại context **ngay trước** method; `AFTER_EACH_TEST_METHOD` loại context **ngay sau** method. Cả hai thường phá reuse giữa methods, nhưng khác ở giai đoạn lifecycle nào làm việc, đặc biệt khi có setup/teardown listeners và initialization logging.

**Không được dùng `@DirtiesContext(classMode=AFTER_EACH_TEST_METHOD)` như một cách định nghĩa “mọi test bắt đầu DB sạch”** mà không kiểm DB thuộc resource nào. Nếu database là PostgreSQL external, context mới vẫn có thể truy cập cùng rows của method trước.

## 12. `AFTER_CLASS` và cache key khác nhau ngay cả khi không dirty

### 12.1. Dirty sau toàn bộ class

**src/test/java/demo/cache/DirtiesAfterClassTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext
class DirtiesAfterClassTest {

    @Autowired
    StateProbe probe;

    @Test
    void contextIsUsableDuringClass() {
        probe.reset();

        assertEquals(1, probe.increment());
        assertNotNull(probe.id());
    }
}
~~~

**Đúng 1 `@Test`.** Class-level `@DirtiesContext` không cần tham số vì **default là `ClassMode.AFTER_CLASS`**: framework sẽ đóng context sau khi lớp đã chạy. Test body tự nó không quan sát được `AFTER_CLASS`, vì callback xảy ra **sau** giai đoạn test class. Đây là lý do không viết một assertion `assertTrue(StateProbe.wasClosed(probe.id()))` ngay trong test: nó sẽ sai thời điểm.

Nếu thật sự cần kiểm lifecycle sau class, có thể dùng test runner/lifecycle harness riêng, listener hoặc một integration test điều phối context explicitly. Tránh tạo dependency không ổn định vào thứ tự giữa hai classes.

### 12.2. Thay inline property tạo context key mới

**src/test/java/demo/cache/BlueConfigurationTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "lab.variant=blue")
class BlueConfigurationTest {

    @Value("${lab.variant}")
    String variant;

    @Test
    void usesBlueTestProperty() {
        assertEquals("blue", variant);
    }
}
~~~

**src/test/java/demo/cache/RedConfigurationTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "lab.variant=red")
class RedConfigurationTest {

    @Value("${lab.variant}")
    String variant;

    @Test
    void usesRedTestProperty() {
        assertEquals("red", variant);
    }
}
~~~

**Đúng 1 `@Test` ở mỗi class**. Hai classes này **không gắn `@DirtiesContext`**. Nhưng `@SpringBootTest(properties="lab.variant=blue")` và `...red` khác cấu hình nên Spring TestContext tạo **hai cache keys**. Nếu cùng suite còn có những classes `@SpringBootTest` không có inline variant, chúng lại là một nhóm cấu hình khác.

Tests chỉ assert property đúng, **không tự tuyên bố đã đo được chính xác số contexts trên toàn JVM**. Để quan sát, xem DEBUG cache logs và `StateProbe.totalConstructed()` nếu cần — nhưng tránh assert một số tuyệt đối vì thứ tự các test classes, LRU và fork configuration có thể làm thay đổi số.

## 13. Đếm số tests, chạy Gradle và đọc kết quả đúng

| Test class | `@Test` | Mục đích |
|---|---:|---|
| `ContextReuseTest` | 3 | Không dirty; reuse bean ID; reset counter cho từng method |
| `DirtiesAfterMethodTest` | 2 | `AFTER_METHOD` evict/close và rebuild ở test kế |
| `DirtiesBeforeMethodTest` | 2 | `BEFORE_METHOD` fresh context + reinjection |
| `DirtiesBeforeEachTest` | 2 | `BEFORE_EACH_TEST_METHOD` |
| `DirtiesAfterEachTest` | 2 | `AFTER_EACH_TEST_METHOD` |
| `DirtiesAfterClassTest` | 1 | Default class-level `AFTER_CLASS` |
| `BlueConfigurationTest` | 1 | Cache key có inline property blue |
| `RedConfigurationTest` | 1 | Cache key có inline property red |
| **Tổng** | **14** | JUnit Jupiter, không có @Disabled |

**Chạy với Gradle Wrapper** nếu project đã tạo wrapper:
~~~bash
./gradlew test
~~~

Windows:
~~~powershell
.\gradlew.bat test
~~~

Nếu chỉ copy `settings.gradle`, `build.gradle` và các source files mà **chưa có wrapper scripts/JAR**, `./gradlew` sẽ không tồn tại. Dùng Gradle tương thích để tạo wrapper hoặc chạy `gradle test`. Trên máy chưa tải dependencies, lần chạy đầu cần Maven Central để resolve Boot plugin/starter.

**Chạy từng lớp riêng:**
~~~bash
./gradlew test --tests demo.cache.ContextReuseTest
./gradlew test --tests demo.cache.DirtiesAfterMethodTest
./gradlew test --tests demo.cache.DirtiesBeforeMethodTest
./gradlew test --tests demo.cache.DirtiesBeforeEachTest
./gradlew test --tests demo.cache.DirtiesAfterEachTest
./gradlew test --tests demo.cache.DirtiesAfterClassTest
./gradlew test --tests demo.cache.BlueConfigurationTest
./gradlew test --tests demo.cache.RedConfigurationTest
~~~

**Lưu ý quan trọng:** Chạy từng lớp một bằng những lệnh Gradle riêng **không chia sẻ static ContextCache giữa các JVM test workers của các lần chạy**. Nếu muốn quan sát cache reuse **giữa các lớp** trong cùng suite, chạy `./gradlew test` cho toàn suite **trong một test JVM**, như cấu hình ở bài. Để tìm test flaky, chạy tất cả nhiều lần và đọc cache stats chứ không chỉ chạy một method isolated.

**Báo cáo Gradle** thường ở `build/reports/tests/test/index.html`. **Kết quả thiết kế dự kiến** là 14 tests PASS trên Java 17/Boot 3.3.5 khi code được tạo và chạy đúng. Đây là **kỳ vọng từ code/API**, không phải tuyên bố Gradle đã được chạy trên máy người đọc.

**Test lifecycle assumptions:**
- JUnit parallel disabled, các classes không chạy interleaved; các marker static chỉ dùng kiểm trong **một class**.
- `@TestMethodOrder(OrderAnnotation.class)` ở đúng hai classes là ngoại lệ phục vụ minh họa BEFORE/AFTER phases; không phải khuyến nghị áp thứ tự test cho logic ứng dụng.
- `StateProbe.wasClosed(old)` được đánh giá sau listener xử lý dirty; không dựa vào JVM GC/finalizer.
- Test application không dùng `@Transactional`, không external DB, không có async jobs chưa hoàn tất.
- `StateProbe.generation()` tăng khi bean instance được tạo, **không đồng nghĩa toàn JVM chỉ có một application context hoặc chỉ một Spring bean**.
- `DirtiesAfterClassTest` kiểm behavior trong class; việc đóng sau class được xác nhận bằng semantics Spring và cache logs, không cố assert trước thời điểm đóng.

## 14. Quan sát và đo **chi phí** thay vì đoán

### 14.1. Bật cache DEBUG stats

Spring TestContext cache có logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Đây là log level trong ví dụ; với Logback tests thật có thể cấu hình logger từ `logback-test.xml` sớm. Cache stats thường đề cập **size**, **maxSize**, **parentContextCount**, **hitCount**, **missCount** và **failureCount** (các trường/cách hiển thị có thể khác theo Framework version). Các con số minh họa sau **không phải log đã chạy thật**:

~~~text
Illustrative cache observation, not actual stdout:

Before adding broad dirties:
  many hits, few misses, fewer context refreshes

After adding @DirtiesContext(AFTER_EACH_TEST_METHOD):
  misses rise, startup/close more frequent
  build total time may increase

After replacing unnecessary dirties by data reset:
  cache reuse returns, hits increase
  tests still isolated by fixture cleanup
~~~

**Không cộng tùy tiện hitCount = số test methods.** Spring TestContext có thể gọi `getApplicationContext` nhiều lần trong các test lifecycle phases; mỗi lần lookup có thể đóng góp hit. Cần đọc **xu hướng** và correlating context startups, không biến hits/misses thành số methods.

### 14.2. Phương pháp benchmark hợp lý

**Bước 1:** Chụp baseline suite trong một môi trường cố định: JDK, CPU/RAM, Gradle version/daemon, Docker/DB resource, Gradle forks/parallel settings. Đo **total test task wall-clock** và số lần Spring context được tạo.

**Bước 2:** Ghi lại config keys khác nhau: `@ActiveProfiles`, `@SpringBootTest(properties)`, test slices, `@MockBean`, test config imports, web environments. Phân biệt cache miss vì **key khác** với cache miss vì **dirty** hoặc **LRU**.

**Bước 3:** Loại `@DirtiesContext` ở các nơi có reset/rollback rõ, không loại ở test sửa bean definitions thật. Chạy lại tests và kiểm **functional correctness** trước khi quan sát thời gian.

**Bước 4:** So sánh nhiều lần chạy ở điều kiện tương đương, bỏ ảnh hưởng dependency download và những biến động môi trường bất thường. **Không viết assertion như `assertTrue(startup < 500ms)`** vào integration test: trên CI chậm nó có thể fail dù ứng dụng hoàn toàn đúng.

**Bước 5:** Kiểm context cache size vs memory. Giữ 32 contexts lớn có thể tốn RAM, dẫn tới GC; tăng maxSize chỉ có lợi khi cache churn chiếm chi phí đáng kể và bộ nhớ cho phép. Thử 16/32/64 theo measurements, không tự mặc định càng lớn càng nhanh.

**Bước 6:** Kiểm JUnit/Gradle parallelism. Một suite mà test methods chạy parallel có thể share mutable context, làm behavior không an toàn dù nhanh hơn. Spring docs cảnh báo khi dùng `@DirtiesContext` trong parallel tests vì một thread có thể evict/close context trong khi thread khác còn đang sử dụng nó.

### 14.3. Đọc dấu hiệu khởi tạo bean

`StateProbe.totalConstructed()` trong project minh họa cho biết **đã có bao nhiêu StateProbe beans được tạo trong test JVM**. Nó không đo “thời gian dựng toàn application”. Có thể bổ sung `ApplicationStartup` hoặc Java Flight Recorder/Actuator startup observations để biết beans/steps nào tốn thời gian khi application start. Không thêm timer giả vào test rồi dùng để assert performance như một contract ổn định.

**Không nhầm Gradle configuration time và Spring context startup time.** `./gradlew test` gồm Gradle startup/configuration, compilation, dependency resolution, JUnit discovery, JVM startup, context loads và actual tests. Context cache chỉ tối ưu một phần trong tổng thời gian đó.

## 15. Dữ liệu test bị nhiễm: chọn reset dữ liệu thay vì rebuild context

### 15.1. Database transaction rollback

Nếu dùng `@DataJpaTest` hoặc test có `@Transactional` được Spring TestContext quản lý, transaction test thường được **rollback** sau mỗi test method. Điều này làm DB changes do test method thực hiện được hoàn tác mà **vẫn giữ ApplicationContext**.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    TestEntityManager entityManager;

    @Test
    void findsOrder() {
        // Insert/query trong test-managed transaction.
        // Khi test method kết thúc, transaction rollback.
    }
}
~~~

**Snippet minh họa**, không thuộc runnable project không có JPA. Phải khai báo starter-data-jpa, DB test, entity/repository classes phù hợp. **Đừng suy rằng `@Transactional` trên test luôn rollback mọi server-side write**: với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP client và embedded server thường xử lý ở **khác threads/transactions**; writes ở server không tự rollback theo test transaction. Test dùng `@Async` cũng có ThreadLocal transaction boundary riêng.

### 15.2. @Sql setup/cleanup hoặc fixture repository

~~~java
@Sql(
    scripts = "/db/seed-orders.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
    scripts = "/db/cleanup-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
@Test
void testOrderEndpoint() {
    // HTTP assertions...
}
~~~

**Snippet minh họa**, không phải project runnable vì các SQL scripts không được định nghĩa ở phần 6. `@Sql` thuộc Spring Test; kiểm transaction mode (`ISOLATED`, default inference), cleanup behavior và thật sự không còn data dư sau test. Với shared DB, có thể cần schema riêng, truncate trong thứ tự FK hoặc disposable database.

### 15.3. @MockBean và mock state

Trong **Spring Boot 3.3**, `@MockBean`/`@SpyBean` của Boot có thể replace/wrap beans. Mock definitions **đi vào context customizer/cache key**, nên khác mocks giữa lớp làm context không share. Mocks trong cùng context thường được reset tự động giữa test methods theo Boot default; không cần `@DirtiesContext` chỉ để xóa Mockito stubbing/interaction history.

**Version note:** Ở Spring Framework/Spring Boot phiên bản mới hơn có `@MockitoBean`/`@MockitoSpyBean` riêng và Boot mock annotations cũ có thay đổi deprecation. Bài cố định Boot 3.3, vì vậy không thay imports vô căn cứ.

Nếu bạn mock một external client:
~~~java
@MockBean
ExternalGateway gateway;
~~~

Đây là **snippet** giả định có `ExternalGateway` interface. Cần thêm `when(gateway.call(...))` trong từng method hoặc reset policy phù hợp; tránh trộn stubbing từ hai tests. Đồng thời, nếu hai classes có mocks khác nhau thì dù không dirty, chúng có thể tạo **cache keys riêng**. Dùng shared base test configuration để giảm variants, nhưng không biến cả suite thành một giant context có hàng chục mock overrides không liên quan.

### 15.4. Reset Spring caches và static data

Nếu test sửa `@Cacheable` data, thao tác cleanup có thể là:
~~~java
@BeforeEach
void clearCache() {
    cacheManager.getCache("products").clear();
}
~~~

**Snippet minh họa**, cần `CacheManager` được inject và cache tên products tồn tại; không nằm trong project runnable. Nếu nhiều cache names/tenants, clear đúng phần cần; không cần đóng context. Với static fields, thêm reset API cho fixture/test data thay vì mong `@DirtiesContext` sẽ xóa static variables.

### 15.5. Vì sao test “xanh” sau khi dirty chưa chứng minh thiết kế sạch?

Nếu integration test thất bại vì singleton giữ user ID của request trước, thêm dirty có thể làm test xanh do mỗi method tạo bean mới. Nhưng trong **ứng dụng production đang chạy lâu**, singleton vẫn tồn tại và vẫn có thể giữ user ID của request trước — một lỗi nghiêm trọng! Test đúng nên sửa singleton thành stateless/request-scoped hoặc dùng concurrency-safe design, rồi kiểm các requests liên tiếp trong **cùng context**.

`@DirtiesContext` có thể **che bug state leakage** thay vì chữa. Trước khi thêm annotation, kiểm xem state bị nhiễm là:
- Business data cần cleanup.
- ThreadLocal/MDC SecurityContext cần clear.
- Sai scope của bean (`@Singleton` cho request data).
- Một global static registry không reset.
- External resource không còn sạch.
- Cấu hình Spring context bị biến đổi thực sự.

Chỉ nhóm cuối (và một số trường hợp cleanup bất khả thi) thường biện minh rõ ràng cho context rebuild.

## 16. Context hierarchy và `hierarchyMode`

Nếu test dùng `@ContextHierarchy`, application có thể gồm parent context chứa shared infrastructure/config và một hay nhiều child contexts (WebApplicationContext, servlet MVC, module riêng). Annotation có tham số:

~~~java
@DirtiesContext(
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
@Test
void testOnlyThisChildContext() { ... }
~~~

Đây là **snippet minh họa**, không nằm trong runnable project vì bài không thiết lập @ContextHierarchy. Hai modes:

- **`EXHAUSTIVE`** (mặc định): Spring dùng thuật toán rộng để clear tất cả contexts thuộc những sub-hierarchies có chung ancestor context liên quan. Việc dirty một child có thể ảnh hưởng đến cả những branches chia sẻ parent, dẫn tới nhiều context loads.
- **`CURRENT_LEVEL`**: giới hạn việc clear vào level hiện tại trong hierarchy theo semantics Spring, tránh lan tới những siblings không cần thiết khi phù hợp; nhưng bạn phải bảo đảm parent/shared state chưa bị hỏng. Không lạm dụng `CURRENT_LEVEL` nếu thay đổi đã ảnh hưởng bean trong ancestor.

**Không tự suy CURRENT_LEVEL chỉ evict duy nhất một bean hoặc không đóng child contexts phụ thuộc.** Nó hoạt động trên **context cache entries trong hierarchy**, không trên từng bean. Nếu tests dùng custom hierarchy, cần đọc đúng Spring version docs và kiểm logs/identity của parent/child.

### 16.1. Context cache khi dùng @DynamicPropertySource

`@DynamicPropertySource` thường đăng ký dynamic suppliers như port từ Testcontainers. Sự hiện diện của **method định nghĩa dynamic properties** có thể tham gia `contextCustomizers`/cache key; nhưng giá trị trả về từ supplier tại thời điểm khác nhau **không nhất thiết** tự tạo một cache key mới. Khi một base class test có dynamic property thay đổi theo subclass/resource lifecycle, Spring có thể reuse context cũ nếu configuration metadata giống nhau, khiến client bean vẫn trỏ port đã thay đổi.

Khi đó phải thiết kế **container scope/context scope** thống nhất; có thể cần `@DirtiesContext` ở base class nếu dynamic properties thực sự khác và context cũ không hợp lệ, hoặc tránh đổi external endpoint trong cùng cached context. Không dùng thay đổi `DynamicPropertyRegistry` như một “auto-refresh” của mọi bean đã init.

### 16.2. Testcontainers không tự restart vì context dirty

**Static `@Container`** thường được JUnit extension quản lý theo test class; nó không phải Spring singleton bean. `@ServiceConnection` đưa connection details từ container vào Spring context, nhưng `@DirtiesContext` **không đồng nghĩa container static sẽ bị xóa hay khởi động lại**. Ngược lại, nếu container được khai báo như Spring-managed bean, lifecycle có thể gắn với context và bị ảnh hưởng khi context đóng. Phải phân biệt owner thực của container, connection pools, DB schema và data volumes.

Ví dụ với Postgres Testcontainers, một context mới có thể kết nối tới **cùng** database container còn đang chạy; dữ liệu cũ vẫn tồn tại. Dùng transactions/schema reset/test isolation đúng, không coi context rebuild là truncate DB.

## 17. `@DirtiesContext` và parallel execution: những race khó thấy

Spring TestContext hỗ trợ chạy tests song song ở mức nhất định, nhưng tài liệu chính thức khuyến cáo **tránh parallel tests** nếu các tests sử dụng `@DirtiesContext`. Trong một thread, test A có thể đánh dấu dirty/close context mà thread B đang dùng để chạy test khác. Hậu quả: bean/pool đã đóng, `ApplicationContext` no longer active, flaky failures và khó debug.

**Rủi ro độc lập:** Hai tests dùng cùng cached context nhưng cùng sửa mutable singleton hoặc DB rows cũng có thể race dù không dirty. Parallelism cần **data isolation** và hạn chế shared state chứ không chỉ tắt annotation.

Chiến lược:
1. Chạy các lớp dirt context tuần tự hoặc tách vào task/fork riêng.
2. Không xóa context trong khi các background tasks vẫn tham chiếu bean thuộc context cũ.
3. Không giả định `@DirtiesContext` khóa chặn các tasks khác cùng cache key.
4. Khi cần parallel speedup, ưu tiên data fixtures/schema namespace riêng và context reuse thay vì rebuild.
5. Dùng `@ResourceLock`/JUnit parallel settings có chủ đích nếu có shared resources; lock phải bao đúng tất cả tests cùng dùng resource.
6. Ghi logs cache và shutdown stack để biết context bị close do DirtiesContext hay LRU.
7. Đừng dùng `Thread.sleep` để “chờ context đóng”; rely on Spring test listener phases hoặc latches/lifecycle callbacks phù hợp.

**CI benchmark phải so đồng điều kiện concurrency**. Ví dụ 10 test forks có thể giảm elapsed time nhưng tăng tổng số contexts, DB connections và memory. Một số chậm/nhanh trong một lần chạy không đủ kết luận.

## 18. Phương án tối ưu hóa bộ kiểm thử thực tế

### 18.1. Chia tests theo mục tiêu

| Test mục tiêu | Lựa chọn context | Reset state | Khi nào Dirty |
|---|---|---|---|
| Pure service logic | JUnit + Mockito, **không Spring context** | Tạo object mới mỗi test | Không |
| Spring MVC controller mapping | `@WebMvcTest` | Mocks/fixture method | Hiếm |
| JPA repository | `@DataJpaTest`, rollback | Transaction/DB fixtures | Hiếm |
| Application wiring/integration | `@SpringBootTest` chia sẻ key | `@BeforeEach`, `@Sql`, transactional cleanup | Chỉ context thật sự nhiễm |
| HTTP server thật | `@SpringBootTest(RANDOM_PORT)` | DB setup/cleanup, client state | Khi server/context resources bị thay đổi |
| Kafka/RabbitMQ | Context + broker test/container | Queue/topic/group names riêng; purge | Chỉ khi Spring infrastructure hỏng/đổi |
| Spring context lifecycle | TestContext/Boot context | Không có cleanup tương đương | Có chủ đích |
| Security with @MockBean | Boot mock reset giữa tests | Reset stubbing, request state | Hiếm |

**Không dùng @SpringBootTest cho mọi pure function test.** Nếu chỉ tính tổng tiền với input/output Java, gọi service logic bằng `new` hoặc Mockito thay vì load container. Context cache giúp giảm *lần thứ hai*, nhưng **lần đầu** load cả app vẫn tốn hơn unit test không context.

### 18.2. Giảm số context cache keys

- Dùng cùng `@ActiveProfiles("test")` cho những classes có chung nhu cầu, không tạo hàng chục variants không cần.
- Gom những inline properties thật sự giống nhau, tránh mỗi class có `@SpringBootTest(properties={"feature=x"})` tùy tiện.
- Hạn chế `@MockBean` khác nhau giữa lớp nếu chỉ để dựng unit logic; chuyển unit tests sang Mockito standalone khi phù hợp.
- Dùng test slices (`@WebMvcTest`, `@DataJpaTest`) nhưng cân nhắc rằng mỗi slice/config vẫn là một context key riêng; không tạo quá nhiều tiny custom contexts.
- Đừng import mỗi nested `@TestConfiguration` riêng mà không cần, vì nó có thể thay đổi context customizer key.
- Đảm bảo `@DynamicPropertySource`/Testcontainers lifespan tương thích cache reuse.
- Không thay một loạt tests bằng `@DirtiesContext` chỉ vì mỗi class có một test setup method không idempotent.
- Quan sát `hitCount/missCount/size` trước và sau thay đổi.

**Tối ưu không có nghĩa gom tất cả vào một application context lớn.** Mục tiêu là reuse **hợp lý** mà vẫn cô lập state và tiết kiệm RAM. Một slice test nhỏ có thể nhanh hơn full context, dù nó tạo một key riêng.

### 18.3. Chọn dirty nhỏ nhất cần thiết

Nếu một method duy nhất sửa bean definitions, đánh dấu:
~~~java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void modifiesBeanFactory() { ... }
~~~

thay vì gắn:
~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EveryTestInClass { ... }
~~~

Khi có thể, tách nhóm tests cần context mutation thành một class nhỏ, không làm toàn bộ suite rebuild. Nếu **mỗi method** thực sự cần một Spring context mới để kiểm lifecycle, `BEFORE_EACH`/`AFTER_EACH` hợp lệ — nhưng đó phải là **mục tiêu kiểm thử**, không là phản xạ để chữa flaky test.

## 19. Mutation experiments: làm thế nào biết test đang kiểm đúng?

| Thay đổi thử nghiệm | Bằng chứng kỳ vọng |
|---|---|
| Gỡ `@DirtiesContext` khỏi method thứ nhất trong `DirtiesAfterMethodTest` | Test thứ hai thấy **cùng marker**; assertion different fail |
| Đổi `AFTER_METHOD` thành `BEFORE_METHOD` ở method đầu | Test kế có thể vẫn reuse context của method đầu; khác phase |
| Gỡ `BEFORE_METHOD` trên method thứ hai | Marker cũ trùng marker mới; test fail |
| Đổi `BEFORE_EACH_TEST_METHOD` thành `AFTER_CLASS` | Tests trong class reuse marker; test verify freshness fail |
| Đổi `AFTER_EACH_TEST_METHOD` thành `AFTER_CLASS` | Test thứ hai thấy marker cũ; test fail |
| Bỏ `probe.reset()` trong `ContextReuseTest` | Một số test có thể phụ thuộc thứ tự/state; test reset invariant phát hiện |
| Dùng `ApplicationContext.getId()` thay probe UUID | Context mới có thể mang cùng ID string; false confidence |
| Thêm `@SpringBootTest(properties="x=1")` cho một class | Cache key khác, cache miss dù không dirty |
| Thêm `@MockBean` khác nhau ở mỗi class | Nhiều context customizers/keys hơn |
| Chạy mỗi class trong Gradle fork khác | Mất reuse cross-class vì static cache không chung |
| Bật test parallel khi dùng DirtiesContext | Có thể race khi một test đóng context test khác sử dụng |
| Chỉ reset DB bằng DirtyContext trong external PostgreSQL | Dữ liệu cũ có thể vẫn tồn tại |
| Đổi maxSize từ 32 xuống 1 với nhiều keys | LRU eviction tăng ngay cả khi không dirty |
| Tắt @PreDestroy callback trên StateProbe | `wasClosed(old)` test không còn bằng chứng bean đã bị destroy |
| Dùng `@Transactional` với real HTTP server và kỳ vọng rollback server writes | Các threads/transactions khác nhau; sai giả định |

Đây là **mutation experiments tùy chọn**, không phải các thay đổi phải thực hiện trên project chính. Chạy từng mutation trong branch/sandbox rồi revert; không để suite production chứa các tests cố ý fail. Một test dirty thực sự kiểm **marker new + old closed**, chứ không dựa vào số giây hoặc thứ tự logs.

## 20. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xác minh/sửa |
|---|---|---|
| `@SpringBootTest` càng ngày càng chậm | Quá nhiều context cache misses | Bật cache DEBUG, kiểm keys và DirtiesContext |
| Mọi class đều khởi tạo app lại | `@DirtiesContext(AFTER_CLASS)` hàng loạt | Reset fixtures thay cho dirty nếu có thể |
| Mọi test method startup lại | `AFTER_EACH`/`BEFORE_EACH` class mode | Xác định need; reset state nhẹ hơn |
| Hai test classes tương tự không reuse | Profiles/properties/mocks/test customizers khác | So cấu hình metadata; giảm variants |
| Một test trước làm test sau fail | Mutable singleton/DB/broker state không cleanup | Truy tìm nguồn state, reset cụ thể |
| Test passes isolated nhưng fail full suite | Shared state hoặc context cache behavior | Chạy same JVM suite, kiểm lifecycle |
| Test context ID không đổi sau dirty | Context ID là tên logic có thể giống | So bean instance UUID/identity |
| `StateProbe.wasClosed` false trong test đang dirty | Đang assert **trước** listener phase | Assert ở test sau hoặc dùng lifecycle listener |
| `@DirtiesContext` không reset static counter | Static tồn tại suốt JVM | Reset static test fixture riêng |
| Dirty rồi database vẫn còn rows | External DB không thuộc context lifecycle | Transaction rollback/cleanup schema |
| Dirty nhưng static Testcontainers vẫn chạy | Container do JUnit/static quản lý | Phân biệt container lifecycle ownership |
| App shutdown gây lỗi connection closed trong async test | Dirty trước khi worker hoàn thành | Await task completion/cleanup trước dirty |
| Cache hit count lớn hơn số tests | TestContext tra context nhiều lần mỗi test | Đọc xu hướng/hits/misses, không chia 1:1 |
| Context load failure bị skip ngay lần hai | Spring 6.1 failure threshold=1 | Điều tra lỗi load đầu, không tăng threshold bừa |
| `ApplicationContext is no longer active` khi chạy song song | Test khác dirty hoặc LRU evict | Tránh parallel DirtiesContext, tune cache size |
| CI có nhiều JVM workers | Mỗi JVM static ContextCache riêng | Kiểm Gradle forks / forkEvery |
| Cache chiếm RAM cao | Too many large contexts/maxSize quá lớn | Benchmark trade-off memory vs reload |
| Test khác nhau chỉ vì @MockBean | Mock customizer khác key | Gom cấu hình hoặc unit Mockito |
| Property từ DynamicPropertySource trỏ port cũ | Supplier/resource lifecycle lệch cache | Align lifespan, dirty khi cần, verify |
| JMX MBean trùng tên giữa tests | Spring-managed JMX resource cần đóng | Có thể dùng @DirtiesContext scoped |
| @Sql cleanup không chạy như tưởng | Transaction mode/order/scripts lỗi | Kiểm DB state sau cleanup thực |
| Unit test chậm vì load Spring | Không cần @SpringBootTest | Tạo object và mocks thuần Java |
| Dirty masking singleton bug | Context mới che memory leakage trong production | Sửa bean state/scope; test many requests same context |
| Startup logs hiển thị dưới test khác | Context init/close nằm ở listener lifecycle | Đọc theo phases/cache logs, không chỉ runner grouping |

## 21. Checklist chọn `@DirtiesContext` trong code review

1. **Đề bài test là context lifecycle hay business data?** Nếu business data, xem reset/rollback trước.
2. **Có state nào không reset được không?** Xác định chính xác bean/resource bị nhiễm.
3. **Có chứng minh context bị đóng cần thiết không?** Không dùng annotation để chữa mơ hồ.
4. **Chọn phase đúng:** method BEFORE/AFTER hay class BEFORE/AFTER_EACH/AFTER_CLASS.
5. **Mặc định method/class khác nhau:** AFTER_METHOD vs AFTER_CLASS.
6. **Có annotation chồng chéo không?** Tránh đóng trước và sau cùng một test vô cớ.
7. **@ContextHierarchy:** EXHAUSTIVE có thể lan đến siblings; CURRENT_LEVEL cần hiểu scope.
8. **External DB/broker/file:** dirty không tự cleanup chúng.
9. **Mockito mocks:** Boot 3.3 mock auto reset có thể đủ; mock definitions vẫn ảnh hưởng key.
10. **Dynamic ports/Testcontainers:** context cache scope phải trùng resource lifecycle.
11. **Parallel:** Không dirty context khi test khác vẫn đang dùng cùng instance.
12. **Gradle forks:** Một JVM thì cache reuse, nhiều JVM là nhiều caches.
13. **Startup cost:** Đo context loads/cache misses và suite runtime trước/sau, không assert thời gian cứng.
14. **Cache size:** Default 32; tune khi có bằng chứng LRU churn và memory headroom.
15. **Test independence:** Không dùng method order như cách workaround business tests.
16. **Transaction boundaries:** Test-managed rollback không bao trùm server/async threads mặc định.
17. **Singleton state:** Reset/test đúng scope, không che bug bằng rebuild.
18. **No false performance claim:** Logs/metrics có thể khác theo test runner/JVM/CI.
19. **Version compatibility:** Boot 3.3/Spring 6.1 APIs đúng, không mặc định Boot 4 dùng cùng bean override annotations.
20. **Completion:** Thay đổi tối ưu chỉ merge khi tất cả functional tests còn PASS và suite đo được cải thiện.

## 22. Bài tập luyện tập

**Bài 1 — Cached context:** Chạy `ContextReuseTest`, quan sát ba `@Test` cùng dùng `StateProbe.id()`. Vì sao từng method vẫn độc lập khi dùng `@BeforeEach reset()`?

**Bài 2 — AFTER_METHOD:** Gỡ annotation ở test thứ nhất của `DirtiesAfterMethodTest`. Test thứ hai quan sát ID như thế nào? Tại sao đó là hồi quy về isolation?

**Bài 3 — BEFORE_METHOD:** Đổi annotation trên test thứ hai thành `AFTER_METHOD`. Vì sao test thứ hai không còn được bảo đảm fresh context **trước** body của nó?

**Bài 4 — BEFORE_EACH:** Tăng số tests trong `DirtiesBeforeEachTest` lên năm. Theo semantics, bao nhiêu lần dirty xảy ra? Vì sao số context loads thực tế có thể bị ảnh hưởng bởi injection lifecycle?

**Bài 5 — AFTER_EACH:** Đọc Spring cache DEBUG logs và đối chiếu `@PreDestroy` markers sau mỗi method.

**Bài 6 — AFTER_CLASS:** Đặt `@DirtiesContext` trên toàn class và không đặt trên methods. So với `AFTER_EACH`, lifecycle và chi phí khác nhau thế nào?

**Bài 7 — BEFORE_CLASS:** Thay annotation của lớp bằng `@DirtiesContext(classMode=BEFORE_CLASS)`. Mục tiêu “context mới trước class” khác “đóng sau class” ở đâu?

**Bài 8 — Cache keys:** Thêm `@ActiveProfiles("test")` vào một class. Khi profile đó không có ở class khác, key có giống nhau không?

**Bài 9 — Mock customizer:** Hai classes có cùng @SpringBootTest nhưng một class thêm @MockBean. Cache có chắc reuse không? Đề xuất cách tổ chức mocks để không tăng context variants.

**Bài 10 — DB rollback:** Viết một `@DataJpaTest` sử dụng test-managed transaction, insert rồi query. Chạy test kế để chứng minh DB sạch mà không cần dirty.

**Bài 11 — HTTP server:** Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, POST tạo record qua HTTP, rồi @Transactional test. Vì sao server-side write có thể không rollback?

**Bài 12 — External database:** Dùng PostgreSQL Testcontainers static và DirtiesContext. Kiểm records trước/sau context rebuild; tại sao cần schema cleanup riêng?

**Bài 13 — LRU:** Tạo 35 distinct test context keys trong một JVM, giữ maxSize=32. Quan sát LRU evictions/close callbacks; không thay đổi production test suite.

**Bài 14 — Gradle forks:** Chạy cùng suite với `maxParallelForks=1` rồi một cấu hình nhiều workers. So số cache hits/misses tổng và runtime. Kết luận trade-off thay vì chỉ nhìn số contexts.

**Bài 15 — Hierarchy:** Dựng parent context + hai child contexts. So `HierarchyMode.EXHAUSTIVE` và `CURRENT_LEVEL`, kiểm đúng những contexts bị close.

**Bài 16 — Failure threshold:** Tạo một bean cố ý fail khi init trong sandbox. Khi nhiều tests có cùng key, vì sao có lỗi “preemptively skipped”? Chỉ ra lỗi gốc đầu tiên.

**Bài 17 — DynamicPropertySource:** Dùng hai test classes có same method metadata nhưng container ports đổi. Viết test xác minh client không trỏ resource đã stop, thiết kế lifecycle khớp cache.

**Bài 18 — Parallel risk:** Bật JUnit parallel trong một sandbox có DirtiesContext. Có thể xảy ra lỗi nào khi một thread đóng context thread khác đang dùng? Cách tránh?

**Bài 19 — Mutating singleton:** Thay StateProbe thành một singleton lưu dữ liệu request; chạy nhiều requests trong một context để phát hiện leak. Vì sao DirtyContext từng method là giải pháp sai ở production?

**Bài 20 — Benchmark:** Đo suite trước/sau thay một số @DirtiesContext bằng `@Sql`/reset; ghi tổng thời gian, context startup count, max cache size, GC/memory và mức ổn định.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — Context Caching](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/caching.html): cache key, reuse, static cache, LRU, maxSize và DEBUG logging.
- [Spring Framework 6.1 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.1/testing/annotations/integration-spring/annotation-dirtiescontext.html): methodMode/classMode, trước/sau test và context close.
- [Spring Framework 6.1 — Context Hierarchies](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/hierarchies.html): parent/child context, hierarchyMode.
- [Spring Framework 6.1 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/failure-threshold.html): failure threshold mặc định 1 và property.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): cảnh báo dùng DirtiesContext với tests chạy song song.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): SpringBootTest, mocking, cache reuse, webEnvironment.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, ThreadLocal transaction boundaries.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL setup/cleanup.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic values và cache key implications.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): container lifecycle và @ServiceConnection.
- [Spring Framework 6.1 API — DirtiesContext](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/annotation/DirtiesContext.html): tất cả enum phases/defaults.
- [JUnit Jupiter — Test Order & Lifecycle](https://junit.org/junit5/docs/current/user-guide/): TestMethodOrder, BeforeEach và parallel settings.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): forks, parallel tests, test JVM system properties.

**Kết luận:** **`@DirtiesContext` là công cụ để loại và đóng ApplicationContext đã bị làm bẩn, không phải nút “reset mọi dữ liệu”.** Context bị dirty sẽ không được tái sử dụng trong Spring TestContext cache, và một test khác cùng cache key phải load context mới với chi phí tương ứng. Dùng annotation đúng phase khi context thực sự không thể tái sử dụng; với thay đổi dữ liệu thông thường, ưu tiên transaction rollback, fixture reset, mock reset hoặc clear business caches. **Quan sát UUID bean mới, `@PreDestroy` marker và cache hits/misses** để chứng minh lifecycle, đo suite time thay vì suy đoán. Thiết kế tests vừa độc lập vừa chia sẻ cấu hình hợp lý mới đem lại cải thiện hiệu năng thực.

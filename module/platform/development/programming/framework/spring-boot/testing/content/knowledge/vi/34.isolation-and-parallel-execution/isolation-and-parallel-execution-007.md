# @DirtiesContext và bean override khi nhiều test dùng cùng context

## 1. Vì sao lỗi chỉ xuất hiện khi chạy cả test suite?

Một lớp Spring Boot test chạy độc lập luôn xanh. Nhưng khi chạy cùng hàng chục test classes, nó thỉnh thoảng nhận kết quả từ Mockito stub của lớp khác, một singleton bean đã bị thay đổi, hoặc lỗi `ApplicationContext is no longer active`. Developer thêm `@DirtiesContext` vào mọi lớp để “cách ly”; test bớt flaky nhưng suite mất rất nhiều thời gian vì ApplicationContext liên tục khởi động lại.

Vấn đề không chỉ ở cache. Có **ba vòng đời khác nhau**:

1. **Spring TestContext cache**: quyết định test classes nào có thể tái sử dụng *chính cùng một* `ApplicationContext`.
2. **Bean override và mock reset**: quyết định bean trong context dùng implementation thật, Mockito mock/spy hay test replacement; nếu là mock, những stubbings/interactions sẽ được reset lúc nào.
3. **JUnit/runner parallel execution**: quyết định test methods/classes nào có thể chạy cùng lúc trên một context hoặc một tài nguyên bên ngoài.

**Nguyên tắc:** `@DirtiesContext` đóng/loại context khỏi cache. Nó **không** đồng nghĩa `Mockito.reset(mock)`, `@AfterEach` cleanup, transaction rollback hoặc cách bảo vệ mọi test song song khỏi tranh chấp. Tương tự, một `@MockitoBean` có cấu hình giống nhau ở hai lớp có thể được chia sẻ cùng context; nó **không** bảo đảm hai test được phép stub và verify mock đó đồng thời.

Bài học này tập trung vào chủ đề **Cách ly và chạy song song** với trọng tâm **“@DirtiesContext và bean override khi nhiều test dùng cùng context”**.

### Sau bài này, bạn sẽ làm được

- Giải thích vì sao hai test classes khác nhau lại dùng chung cùng context và singleton beans.
- Phân biệt cache key, cache hit, dirty/evict và create-new-context.
- Sử dụng `@DirtiesContext` ở method/class với thời điểm BEFORE/AFTER hợp lý.
- Dùng `@MockitoBean`, `@MockitoSpyBean` và `@TestBean` của Spring Framework 6.2 đúng với bean override lifecycle.
- Hiểu `REPLACE_OR_CREATE`, `REPLACE`, `WRAP` và `enforceOverride=true`.
- Biết field name, bean name, qualifier và context hierarchy ảnh hưởng việc matching/cache key ra sao.
- Phân biệt reset mock mặc định `MockReset.AFTER` với rebuild context.
- Xác định race conditions khi hai tests stub/verify cùng mock, hay test A dirty context đang được test B sử dụng.
- Chọn giữa reset bean state, rollback database, reset mocks, resource locks, tách context và dirties một cách có căn cứ.
- Chạy ví dụ Java 17+/Spring Boot 3.5 với **10 JUnit Jupiter methods** cho cùng-key reuse, override variant, mock reset, singleton state và controlled eviction.
- Đọc log cache và đưa ra quy tắc CI cho integration tests chạy song song.

**Phiên bản mục tiêu:** Java 17+, Spring Boot **3.5.16**, Spring Framework **6.2.x**, JUnit Jupiter, Mockito 5 và AssertJ được Boot BOM quản lý. Spring Framework 6.2 giới thiệu `@MockitoBean`, `@MockitoSpyBean` và `@TestBean`. Ở Spring Boot 4.x/Framework 7.x, module/starter/import paths có thể thay đổi; luôn xem tài liệu của version đang dùng.

## 2. ApplicationContext cache chia sẻ cái gì?

Spring TestContext Framework có một context cache static trong JVM test worker. Với mỗi test cần Spring context:

```text
TestClass A -----------------------------+
                                         |
                                         v
                            MergedContextConfiguration
                                  (cache KEY)
                                         |
                                  cache lookup
                                 /           \
                               HIT          MISS
                                |             |
                                v             v
                           same context   load/refresh new
                                |             |
                                +------+------+
                                       |
                                ApplicationContext
                                       |
                      beans, singletons, proxies, mocks
                                       |
                TestClass B với effective key tương đương
                            -> cùng context object
```

Cache hit có nghĩa **chính cùng Java object ApplicationContext** được trả về. Theo đó các singleton beans trong container đó cũng là cùng instances, trừ khi được tái cấu hình/override theo một cache key khác.

Đây không phải cache kết quả phương thức test. `@BeforeEach`, test methods, assertions, DB operations và Mockito calls vẫn chạy lại. Nó cũng không phải Gradle build cache hay JUnit test result cache.

### 2.1. Cache key không chỉ là @SpringBootTest

Các metadata chủ yếu tham gia `MergedContextConfiguration` key trong Spring Framework 6.2:

| Thành phần | Ví dụ |
|---|---|
| `locations` / `classes` | @ContextConfiguration XML/classes, Boot application class |
| `contextInitializerClasses` | ApplicationContextInitializer |
| `contextCustomizers` | `@MockitoBean`, `@TestBean`, `@DynamicPropertySource`, Boot test customizers |
| `contextLoader` | Loader/bootstrapping strategy |
| `parent` | @ContextHierarchy parent |
| `activeProfiles` | @ActiveProfiles("test") |
| `propertySourceDescriptors` | @TestPropertySource resource descriptors |
| `propertySourceProperties` | Inline test properties |
| `resourceBasePath` | @WebAppConfiguration |

Tên lớp test **không phải** một thành phần độc lập chỉ vì khác tên. Nếu A và B có effective key giống nhau, cả hai có thể dùng chung context. Nếu cùng application class nhưng khác profile, properties hoặc bean overrides, thường key khác.

### 2.2. Context cache sống trong JVM

```text
JVM test worker #1:
   KEY X -> context X
   KEY Y -> context Y
   Tests in this worker may reuse them.

JVM test worker #2:
   separate empty cache initially
   even KEY X cannot reuse context from worker #1.
```

Với Gradle, `maxParallelForks`/`forkEvery` hoặc Maven Surefire `forkCount`/`reuseForks` ảnh hưởng số JVMs và khả năng chia sẻ. **JUnit @ResourceLock không khóa tài nguyên xuyên JVM processes**, nên nếu nhiều forks cùng truy cập một database hoặc file chung, vẫn cần resource isolation/coordination thích hợp.

Spring Framework default cache max size là **32** và implementation dùng LRU eviction khi quá capacity. Vì vậy cùng key có thể reload sau khi bị evict, dirty hoặc test JVM bị thay. Không suy “same annotations” nghĩa là context sẽ tồn tại mãi mãi trong mọi suite.

## 3. @DirtiesContext thực hiện việc gì?

`@DirtiesContext` là tín hiệu cho Spring TestContext rằng một context **không còn an toàn để tiếp tục chia sẻ**. Khi áp dụng, framework loại entry tương ứng khỏi cache và đóng context. Lần sau có test yêu cầu cùng configuration metadata thì context mới được tải.

```text
Context K in cache
      |
 Test mutates global bean/context state
      |
 @DirtiesContext trigger
      |
      v
 remove K from TestContext cache
      |
      v
 close old ApplicationContext
      |
      v
 next lookup K -> cache miss -> new context
```

**Không làm những việc sau:**

- Không tự động xóa mọi dữ liệu ở PostgreSQL/Kafka/external service.
- Không bảo đảm state static Java/OS environment được reset.
- Không tự tạo transaction rollback đúng cho side effects ngoài test thread.
- Không khóa JUnit threads và không đồng bộ hóa test B đang dùng context cũ.
- Không chỉ reset Mockito stubbings; nó đóng **toàn bộ container**.
- Không thay thế thiết kế test data độc lập.

### 3.1. Annotation ở class level

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class ModifiesGlobalContextTest {
    // ... JUnit tests ...
}
```

Đây là snippet, không phải file Java đầy đủ. `AFTER_CLASS` là class mode mặc định: sau class, cached context bị dirty. `BEFORE_CLASS` làm dirty trước khi class bắt đầu, phù hợp khi class phải bắt đầu bằng fresh context nhưng không nhất thiết sửa context trong class.

### 3.2. Annotation ở method level

```java
@Test
@DirtiesContext(
    methodMode = DirtiesContext.MethodMode.AFTER_METHOD
)
void changesMutableSingletonBeyondSafeReset() {
    // A change that makes reuse unsafe.
}
```

`AFTER_METHOD` là method mode mặc định; `BEFORE_METHOD` đánh dấu dirty trước method, giúp method cần fresh context. Nếu sử dụng các modes ở cả class và method, các trigger tương ứng đều được áp dụng. Nếu dùng `@DirtiesContext` chỉ vì một Mockito mock đã được stub, thường là lạm dụng.

### 3.3. Chọn mode theo yêu cầu thực

| Mode | Khi nào dirty? | Hệ quả |
|---|---|---|
| Class BEFORE_CLASS | Trước class | Evict shared key cũ trước khi test class dùng |
| Class AFTER_CLASS | Sau class | Các classes cần key đó về sau phải reload |
| Class BEFORE_EACH_TEST_METHOD | Trước mỗi method | Context startup có thể lặp nhiều lần |
| Class AFTER_EACH_TEST_METHOD | Sau mỗi method | Evict sau mỗi method; tăng startup |
| Method BEFORE_METHOD | Trước method đánh dấu | Chỉ method đó yêu cầu fresh |
| Method AFTER_METHOD | Sau method đánh dấu | Những method/class tiếp theo reload |

Mode BEFORE/AFTER không phải là “dùng transaction trước/sau”; đó là **thời điểm đóng context**. Test có thể bị re-inject dependencies theo Spring TestContext lifecycle khi context thay, nhưng nếu code giữ reference context cũ trong biến static/field ngoài Spring-managed lifecycle thì reference ấy có thể thành **stale/closed**.

### 3.4. Context hierarchy

Với `@ContextHierarchy`, `@DirtiesContext.hierarchyMode` cho phép chọn phạm vi invalidation. Default `EXHAUSTIVE` có thể xóa các nhánh chia sẻ một ancestor; `CURRENT_LEVEL` giới hạn vào level hiện tại khi phù hợp. Nếu parent bean bị mutate, CURRENT_LEVEL có thể **không đủ**. Với `@MockitoBean/@MockitoSpyBean/@TestBean` trong context hierarchy, dùng `contextName` để giới hạn override đúng level nếu cần; mặc định có thể áp dụng lên các levels dẫn đến behavior ngoài ý định.

## 4. Bean override: thay definition/instance ở lúc dựng test context

Trong Spring Framework 6.2, bean override support được thực thi qua TestContext infrastructure (ContextCustomizerFactory, BeanFactoryPostProcessor, TestExecutionListener). Nó không phải tự động mutate một ApplicationContext đã cache sẵn khi một test method bắt đầu.

**Mỗi cấu hình override trở thành một phần của context customizers/cache key.** Nếu hai test classes cần cùng một mock target, same name/qualifier/reset mode và metadata khác cũng tương đương, chúng có thể share context **đã được override**. Nếu một class override và class kia không override, hoặc override khác target, chúng thông thường nhận context khác.

### 4.1. Ba chiến lược

| Strategy | Ý nghĩa | Được dùng bởi |
|---|---|---|
| `REPLACE_OR_CREATE` | Thay bean nếu tồn tại, tạo mock/test bean nếu chưa có | @MockitoBean mặc định, @TestBean mặc định |
| `REPLACE` | Bắt buộc bean đã tồn tại; nếu không, fail fast | @MockitoBean(enforceOverride=true), @TestBean(enforceOverride=true) |
| `WRAP` | Bắt lấy instance thật và bọc bằng spy | @MockitoSpyBean |

**Giới hạn quan trọng:** Spring Framework bean override facility hỗ trợ **singleton beans**; không coi nó là cơ chế tự động override bất kỳ prototype/request-scoped bean nào. Với `FactoryBean`, replace/wrap semantics được áp dụng lên object được tạo ra theo hướng dẫn Spring; không đơn thuần thay một prototype FactoryBean tùy ý.

### 4.2. Có thể “âm thầm tạo” bean không tồn tại

```java
@MockitoBean
PaymentGateway gateway;
```

Mặc định `@MockitoBean` có thể **tạo mới mock bean** nếu không có production bean tương ứng. Một slice test nhờ vậy có thể start, nhưng bạn chưa chứng minh real dependency wiring tồn tại. Khi test chủ ý thay **bean đã có**, dùng:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
```

Lúc này nếu target bean vắng, test setup fail thay vì tự thêm mock. Lựa chọn nào đúng phụ thuộc test boundary: trong MVC slice, service có thể không được scan và cần tạo mock; trong full-context bean override test, enforceOverride giúp phát hiện wiring regression.

### 4.3. Định danh bean và qualifier

Spring TestContext có thể chọn bean theo type, `@Qualifier`, name explicit hoặc fallback field name. Hai test classes cùng mock type nhưng khác field names có thể nhận **context key khác nhau** vì qualifier metadata. Ví dụ:

```java
@MockitoBean
PaymentGateway paymentGateway;

// Một test class khác:
@MockitoBean
PaymentGateway gateway;
```

Ngay cả khi chỉ có một candidate bean, Spring docs lưu ý field name/qualifiers có thể ảnh hưởng cache sharing. **Ưu tiên tên ổn định hoặc chỉ định `name="..."` khi thật sự cần target cụ thể**, không đổi field names vô cớ.

## 5. @MockitoBean: một mock trong context không thuộc riêng một test method

`@MockitoBean` thay/đăng ký một Mockito mock dưới dạng Spring bean. Nếu context được reuse, **cùng mock instance** có thể được inject vào nhiều test instances/classes. Nó không giống `@Mock` từ MockitoExtension trong pure unit test:

- `@Mock` thuộc vòng đời Mockito/JUnit, không thay Spring ApplicationContext bean.
- `@MockitoBean` tham gia startup/caching của Spring TestContext, có thể được inject vào nhiều Spring beans.
- Các Spring beans sử dụng dependency đó sẽ gọi mock, không phải real implementation.
- Cùng config key → có thể cùng mock Java object giữa classes.
- Mock được reset theo lifecycle test listeners ở Spring Framework 6.2.

### 5.1. Mock reset mặc định là AFTER

Javadoc Spring Framework 6.2 cho `@MockitoBean.reset` đặt mặc định **`MockReset.AFTER`**: framework reset mock **sau mỗi test method**, khi Spring TestContext Mockito reset listener hoạt động theo cấu hình mặc định.

Điều đó thường giúp test method sau không nhận stubbings/interactions cũ:

```java
@Test
void firstTest() {
    when(gateway.fetch()).thenReturn("A");
    assertThat(service.read()).isEqualTo("A");
}

// @MockitoBean default AFTER reset runs at end of first test.
// The second test should define its own stubbing.
@Test
void secondTest() {
    when(gateway.fetch()).thenReturn("B");
    assertThat(service.read()).isEqualTo("B");
}
```

Đây là snippet cho test class có `@MockitoBean` và service được inject. Nó **không** bảo đảm an toàn khi hai methods thực thi **đồng thời**: nếu test A reset trong lúc test B đang gọi cùng mock, stub B có thể biến mất hoặc verification bị nhiễu.

### 5.2. Mock reset không phải context reset

| Tác vụ | Thay đổi gì? | Chi phí |
|---|---|---|
| Default MockReset.AFTER | Xóa stubbings/interactions của Mockito mock sau method | Nhẹ, không cần re-create context |
| `Mockito.clearInvocations(mock)` | Xóa recorded invocations nhưng giữ stubbings | Nhẹ, cần dùng đúng mục tiêu |
| `Mockito.reset(mock)` | Xóa stubbings và invocations | Nhẹ nhưng có thể che test design nếu lạm dụng |
| Custom stateful bean `reset()` | Reset chính bean theo API ứng dụng | Không đóng context |
| `@Transactional` rollback | Hoàn tác transaction DB thuộc phạm vi test | Không reset mock/singleton ngoại transaction |
| `@DirtiesContext` | Evict và close cả ApplicationContext | Đắt, có thể ảnh hưởng test khác |

**Không dùng @DirtiesContext chỉ vì mock đã có một stub.** Nếu default reset mode bị tắt (`MockReset.NONE`) hoặc custom listeners bị thay, cần hiểu lifecycle và cleanup rõ trước khi kỳ vọng test isolation.

### 5.3. Cùng mock trong hai test classes là điều có thể mong đợi

Nếu cả hai classes cấu hình:

```java
@SpringBootTest(classes = ExampleApp.class)
class FirstTest {
    @MockitoBean(name = "paymentGateway", enforceOverride = true)
    PaymentGateway paymentGateway;
}

@SpringBootTest(classes = ExampleApp.class)
class SecondTest {
    @MockitoBean(name = "paymentGateway", enforceOverride = true)
    PaymentGateway paymentGateway;
}
```

thì chúng có thể share **một context đã override** nếu mọi key metadata khác tương đương. **Không được** kết luận sẽ luôn load hai Spring contexts riêng chỉ vì có hai test classes.

## 6. @MockitoSpyBean: giữ real behavior nhưng có side effects

`@MockitoSpyBean` dùng strategy `WRAP`: yêu cầu **đúng một candidate bean** để bọc bằng spy. Method không được stub thường gọi implementation thật, khác mock trả default answers.

```java
@MockitoSpyBean
InvoiceCalculator calculator;

@Test
void recordsRealCall() {
    int amount = calculator.total(2, 100);
    assertThat(amount).isEqualTo(200);
    verify(calculator).total(2, 100);
}
```

Đây là snippet minh họa, giả định có một `InvoiceCalculator` thật và tính toán đó trả 200. Nó **không** phải một phần mã runnable demo ở dưới. Spy có thể gọi DB/network/transaction hoặc thay singleton state thật, nên test isolation cần thận trọng hơn.

### 6.1. Stubbing spies đúng cách

Với spy, `when(spy.method())` có thể **gọi real method ngay trong lúc thiết lập stub**. Spring/Mockito docs khuyên sử dụng doReturn/doThrow/doNothing khi side effects không mong muốn:

```java
doReturn("stubbed")
    .when(spyGateway)
    .fetchRemote();
```

Không suy `@MockitoSpyBean` sẽ tạo bean mới nếu không có target; nó cần một existing bean (một candidate) để wrap. Nếu có nhiều candidates, chỉ định qualifier/name; khi cần target level trong hierarchy, dùng contextName.

## 7. @TestBean: thay bean bằng đối tượng từ static factory

Không phải mọi override đều cần Mockito. Spring Framework 6.2 có `@TestBean` để thay một bean bằng object từ **static factory method không tham số**.

```java
@TestBean(
    name = "clock",
    methodName = "fixedClock",
    enforceOverride = true
)
Clock clock;

static Clock fixedClock() {
    return Clock.fixed(
        Instant.parse("2040-06-01T00:00:00Z"),
        ZoneOffset.UTC);
}
```

Đoạn này được dùng trong fixture của runnable demo. Nó hữu ích khi muốn một fake/stub deterministic nhưng không cần Mockito stubbings. Giống @MockitoBean, override tham gia context customizer và cache key; factory method thường được gọi khi context được tạo, **không** nhất thiết mỗi @Test method.

**Lưu ý:** nếu fake có mutable state, nó vẫn là singleton trong cached context và có thể rò qua tests. Không được coi “test bean” tự động có scope per-method.

## 8. Lỗi chạy song song: Spring có hỗ trợ cơ bản nhưng có giới hạn

Spring Framework 6.2 documentation về parallel test execution đưa ra hướng dẫn **không chạy song song** các tests:

- sử dụng `@DirtiesContext`;
- sử dụng `@MockitoBean` hoặc `@MockitoSpyBean`;
- sử dụng Spring Boot legacy `@MockBean`/`@SpyBean`;
- thay đổi trạng thái chung của database, broker, filesystem và các shared services;
- phụ thuộc JUnit test method order hoặc các cơ chế sắp xếp thứ tự trong cùng test class.

Đây là khuyến nghị chính thức để tránh flakiness, không phải phủ nhận mọi khả năng chạy parallel của Spring. Nhiều tests không có shared mutable state có thể chạy concurrent bình thường.

### 8.1. Race từ cùng shared Mockito mock

```text
Class A & Class B share Context K and mock M.

Thread A: when(M.read()).thenReturn("A")
Thread B: when(M.read()).thenReturn("B")
Thread A: service.read() -> M.read() might see B
Thread B: verify(M).read() sees A's invocation too
Thread A: @AfterTest Mockito reset(M)
Thread B: service.read() -> M.read() may return default null

Result: timing-dependent assertions, flaky verification.
```

Kể cả JUnit tạo **test class instances khác nhau**, Spring context vẫn có thể giữ **cùng mock bean instance**. Default AFTER reset không phải concurrent synchronization.

### 8.2. Race từ @DirtiesContext khi test khác đang dùng context

```text
Thread A: using ApplicationContext K
Thread B: @DirtiesContext(AFTER_METHOD) closes K
Thread A: continues --> "ApplicationContext is no longer active"
```

Spring docs nhắc lỗi `ApplicationContext ... no longer active` khi một thread loại cached context mà thread khác đang dùng (do @DirtiesContext hoặc LRU eviction).

**Không “fix” bằng cách tăng timeout ngẫu nhiên hay thêm synchronized quanh một bean.** Cần xét lại scheduling/isolation: tránh parallel nhóm tests có dirties/mock overrides, hoặc tách resource/configurations phù hợp.

### 8.3. JUnit @ResourceLock: hữu ích nhưng không phải phép màu

JUnit Jupiter hỗ trợ:

```java
@ResourceLock(
    value = "shared-payment-test-resource",
    mode = ResourceAccessMode.READ_WRITE
)
class PaymentIntegrationTests {
    // ...
}
```

JUnit engine có thể khóa resource key trong cùng execution plan; READ locks có thể cùng chạy, READ_WRITE ngăn những tests cũng khai báo **cùng key** chạy đồng thời. Nó bao phủ lifecycle methods tương ứng. Nhưng:

- Tất cả test classes cạnh tranh cùng tài nguyên phải **đều khai báo khóa tương thích**.
- Khóa không cross JVM/Gradle workers/Maven forks.
- Khóa không tự ngăn một class khác không đăng ký lock dirty context.
- Một test có mock reset/dirty complex vẫn nên **ưu tiên serial execution**, theo khuyến nghị Spring.
- `@Execution(SAME_THREAD)` trên một class chỉ hạn chế việc thực thi trong class đó; nó **không tự serialize mọi classes khác**.

Một lựa chọn ở JUnit Jupiter là `@Isolated` cho class cần chạy mà không có tests khác đồng thời trong cùng engine execution plan (tùy version). Nếu cần đơn giản/đáng tin hơn, disable parallel cho **integration test task** và giữ parallel ở pure unit test task.

### 8.4. Không dùng order để “giải quyết” state leakage

Chỉ định `@TestMethodOrder` rồi để method 2 dựa trên stub của method 1 không tạo isolation. Nó làm test phụ thuộc order và dễ lỗi khi class/run bị chọn riêng. Mỗi method cần tự thiết lập stub/test data, và cleanup side effects của nó.

## 9. Chọn cách reset nhẹ nhất phù hợp

| State/tài nguyên bị thay đổi | Cách cleanup ưu tiên | Khi cần @DirtiesContext |
|---|---|---|
| Mockito stubbing/verification | @MockitoBean default reset, Mockito reset đúng mode | Hiếm khi cần |
| Singleton counter/map/cache | API clear/reset trong finally hoặc @AfterEach | Nếu không khôi phục được context state |
| Embedded DB records | Transaction rollback/@Sql cleanup/truncate | Khi schema/embedded context không khôi phục an toàn |
| External DB rows | Unique IDs + cleanup/transactions | Khi client/context đã hỏng vì mutations |
| Kafka topics/messages | Group/topic isolation và cleanup/lifecycle | Khi infrastructure context bị invalidated |
| Java static fields | Clear static state, tránh global mutations | Dirties context không reset static |
| System properties/OS env | Scoped mutation + restore trong finally | Dirties không tự phục hồi OS/JVM global state |
| ThreadLocal/MDC | `remove()` trong finally | Dirties không thay cleanup trên thread reuse |
| Bean definitions/context config mutate | Tránh mutate; dùng test config key riêng | Thường cần |
| Server/DataSource pool lifecycle bị phá | Restart dependency/context có kiểm soát | Có thể cần sau lifecycle mutation |
| Real HTTP operation qua RANDOM_PORT | Reset DB/external side effects riêng | Không chỉ dựa test @Transactional |

Nếu chỉ gọi `reset()` trên bean để khôi phục invariant, chi phí ít hơn startup lại cả Spring container. Nhưng **reset phải đáng tin khi có parallel tests**; reset một singleton giữa lúc thread khác đọc nó vẫn là race.

## 10. Ví dụ runnable Java 17+/Spring Boot 3.5.16

Ví dụ tập trung vào TestContext cache + bean overrides + dirties; không cần web server, database hoặc Docker. Tất cả tests chạy trong cùng JVM và **không chạy song song** để bảo đảm phép đo identity deterministic.

### 10.1. Các tình huống sẽ chứng minh

1. Hai Spring Boot test classes với cùng `@MockitoBean` inherited field chia sẻ context cùng mock override configuration.
2. Một test class không override dùng **context khác** với mock override configuration.
3. Một fixture đổi `@ActiveProfiles` tạo cache key khác.
4. Một `@TestBean` có explicit replacement tạo context khác và giá trị cố định.
5. Một singleton counter trong context chia sẻ giữ state nếu không cleanup.
6. Một fixture `@DirtiesContext(AFTER_CLASS)` loại cached context; lần sau lookup cùng key tạo context mới.
7. `@MockitoBean` reset stubbings sau mỗi JUnit method khi Spring listeners hoạt động.
8. Không cần test method order giữa hai classes để chứng minh shared context.

**Kỳ vọng:** đúng **10 JUnit Jupiter methods**: 2 trong lớp mock A, 2 trong lớp mock B, 6 trong lớp cache evidence. Các nested fixture classes không có methods `@Test` và không phải các tests được chạy riêng.

### 10.2. Cây file

```text
build.gradle
settings.gradle
src/
├── main/java/com/example/sharedctx/
│   └── SharedContextApplication.java
└── test/
    ├── java/com/example/sharedctx/
    │   ├── SharedClockSupport.java
    │   ├── ClockMockAlphaTest.java
    │   ├── ClockMockBetaTest.java
    │   └── CacheBehaviorTest.java
    └── resources/
        └── junit-platform.properties
```

Các classes ở cùng package để không gặp vấn đề package-private accessibility. App chỉ có Java singleton beans; `webEnvironment=NONE` để không mở socket. Thời gian khởi động demo không đại diện cho full production app.

### 10.3. Gradle Groovy DSL

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'shared-context-isolation-lab'
```

**File `src/test/resources/junit-platform.properties`:**

```properties
# Explicitly disable JUnit parallel execution for these integration tests.
junit.jupiter.execution.parallel.enabled=false
```

Boot 3.5 BOM quản lý Spring Framework 6.2, Mockito/JUnit/AssertJ versions. Gradle Wrapper files không được liệt kê, có thể tạo bằng Gradle/IDE. Đừng trộn Boot 4 dependencies với source Boot 3.5 và kỳ vọng package giống nhau.

## 11. Source production: một Clock, một Service và một Counter

**File `src/main/java/com/example/sharedctx/SharedContextApplication.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SharedContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedContextApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2025-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }

    @Bean
    Counter counter() {
        return new Counter();
    }

    public static final class GreetingService {
        private final Clock clock;

        public GreetingService(Clock clock) {
            this.clock = clock;
        }

        public String greet(String name) {
            return "Xin chào " + name + " @ " + clock.instant();
        }
    }

    public static final class Counter {
        private final AtomicInteger value = new AtomicInteger();

        public int get() {
            return value.get();
        }

        public int increment() {
            return value.incrementAndGet();
        }

        public void restore(int original) {
            value.set(original);
        }
    }
}
```

**Giải thích:**

- Production Clock là deterministic; không phụ thuộc wall-clock của máy CI.
- `GreetingService` nhận Clock qua constructor injection; nếu test override Clock bean, Service sẽ dùng mock/fake Clock ngay từ lúc context được xây.
- `Counter` singleton có AtomicInteger. AtomicInteger bảo đảm thao tác increment atomic, **không** bảo đảm nhiều test cases cùng mutate/reset một cách độc lập.
- Không có DB, @Transactional, @Profile hoặc HttpClient; demo cố tình cô lập vấn đề cache/override.
- Singleton bean `Counter` mới được tạo khi context thật sự reload; nếu cache hit thì counter cũ được giữ.

## 12. Base class: cấu hình mock giống nhau ở nhiều classes

**File `src/test/java/com/example/sharedctx/SharedClockSupport.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

abstract class SharedClockSupport {

    @MockitoBean(name = "clock", enforceOverride = true)
    Clock clock;

    @Autowired
    SharedContextApplication.GreetingService service;

    @Autowired
    ApplicationContext context;
}
```

Đây là base class không có JUnit method. Các lớp con dùng cùng inherited field declaration và cùng explicit target name, tránh sự khác biệt về fallback field qualifiers. `enforceOverride=true` đảm bảo test **không im lặng tạo một Clock mock mới** nếu production bean `clock` biến mất.

### 12.1. Test class A

**File `src/test/java/com/example/sharedctx/ClockMockAlphaTest.java`:**

```java
package com.example.sharedctx;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
    classes = SharedContextApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ClockMockAlphaTest extends SharedClockSupport {

    @Test
    void mockClockDrivesServiceWithoutRealClock() {
        Instant fixed =
                Instant.parse("2031-01-02T03:04:05Z");

        when(clock.instant()).thenReturn(fixed);

        assertThat(service.greet("Linh"))
                .isEqualTo("Xin chào Linh @ 2031-01-02T03:04:05Z");
        verify(clock).instant();
    }

    @Test
    void stubbingStartsCleanInEachMethod() {
        // Spring MockitoBean defaults to MockReset.AFTER.
        assertThat(Mockito.mockingDetails(clock).getStubbings())
                .isEmpty();

        when(clock.instant()).thenReturn(
                Instant.parse("2032-01-01T00:00:00Z"));

        assertThat(service.greet("Minh"))
                .isEqualTo("Xin chào Minh @ 2032-01-01T00:00:00Z");
    }
}
```

### 12.2. Test class B

**File `src/test/java/com/example/sharedctx/ClockMockBetaTest.java`:**

```java
package com.example.sharedctx;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
    classes = SharedContextApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ClockMockBetaTest extends SharedClockSupport {

    @Test
    void sameMockOverrideSupportsAnotherTestClass() {
        when(clock.instant()).thenReturn(
                Instant.parse("2041-05-06T07:08:09Z"));

        assertThat(service.greet("An"))
                .isEqualTo("Xin chào An @ 2041-05-06T07:08:09Z");
        verify(clock).instant();
    }

    @Test
    void mockHasNoLeftoverStubbingsAtMethodStart() {
        assertThat(Mockito.mockingDetails(clock).getStubbings())
                .isEmpty();

        when(clock.instant()).thenReturn(
                Instant.parse("2042-06-07T08:09:10Z"));

        assertThat(service.greet("Bình"))
                .isEqualTo("Xin chào Bình @ 2042-06-07T08:09:10Z");
    }
}
```

**Những gì 4 tests minh họa:**

- Cùng một target `Clock` được mock ở context xây cho cả hai classes.
- Mỗi method tự tạo stubbing cho hành vi của nó.
- Default `MockReset.AFTER` giúp cleanup stubbings giữa sequential methods.
- Các tests không dựa vào thứ tự JUnit chạy class A rồi class B.
- Không có `@DirtiesContext` chỉ để xóa mock stubs.

**Giới hạn:** asserts về stubbings sạch phụ thuộc Spring Mockito reset listener hoạt động và suite chạy **không song song** như junit-platform.properties. Nếu custom test listeners hoặc reset mode `NONE` làm mất cơ chế reset, phải thiết kế setup/cleanup riêng.

## 13. Bộ kiểm thử cache identity, @TestBean và @DirtiesContext

Một lớp test độc lập dùng `TestContextManager` với các fixture classes để **chủ động load context bên trong cùng một test method**, so sánh object references mà không dựa vào thứ tự hai test classes khác nhau.

Đây là kỹ thuật **quan sát cơ chế Spring TestContext**, không phải quy trình bắt buộc cho mọi ứng dụng.

**File `src/test/java/com/example/sharedctx/CacheBehaviorTest.java`:**

```java
package com.example.sharedctx;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.bean.override.convention.TestBean;

import static org.assertj.core.api.Assertions.assertThat;

class CacheBehaviorTest {

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class PlainFixtureA {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class PlainFixtureB {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    @ActiveProfiles("other")
    static class OtherProfileFixture {}

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    static class FixedClockFixture {

        @TestBean(
            name = "clock",
            methodName = "fixedClock",
            enforceOverride = true
        )
        Clock clock;

        static Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2040-06-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @SpringBootTest(
        classes = SharedContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
    )
    @DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
    )
    static class DirtyAfterFixture {}

    private static ApplicationContext load(Class<?> fixture) {
        return new TestContextManager(fixture)
                .getTestContext()
                .getApplicationContext();
    }

    @Test
    void equalMockMetadataAcrossClassesUsesSameContext() {
        ApplicationContext a = load(ClockMockAlphaTest.class);
        ApplicationContext b = load(ClockMockBetaTest.class);

        assertThat(b).isSameAs(a);
        assertThat(b.getBean(Clock.class))
                .isSameAs(a.getBean(Clock.class));
        assertThat(Mockito.mockingDetails(
                a.getBean(Clock.class)).isMock()).isTrue();
    }

    @Test
    void nonOverriddenContextDiffersFromMockContext() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext samePlain = load(PlainFixtureB.class);
        ApplicationContext withMock =
                load(ClockMockAlphaTest.class);

        assertThat(samePlain).isSameAs(plain);
        assertThat(withMock).isNotSameAs(plain);
        assertThat(Mockito.mockingDetails(
                plain.getBean(Clock.class)).isMock()).isFalse();
    }

    @Test
    void activeProfileChangesCacheKey() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext other = load(OtherProfileFixture.class);

        assertThat(other).isNotSameAs(plain);
        assertThat(other.getEnvironment().getActiveProfiles())
                .contains("other");
    }

    @Test
    void testBeanFactoryCreatesSeparateReplacementContext() {
        ApplicationContext plain = load(PlainFixtureA.class);
        ApplicationContext replacement =
                load(FixedClockFixture.class);

        assertThat(replacement).isNotSameAs(plain);
        assertThat(replacement.getBean(Clock.class).instant())
                .isEqualTo(Instant.parse("2040-06-01T00:00:00Z"));
        assertThat(replacement.getBean(
                SharedContextApplication.GreetingService.class)
                .greet("Lan"))
                .isEqualTo("Xin chào Lan @ 2040-06-01T00:00:00Z");
    }

    @Test
    void singletonMutableStateIsVisibleAcrossSharedContexts() {
        ApplicationContext first = load(PlainFixtureA.class);
        ApplicationContext second = load(PlainFixtureB.class);

        SharedContextApplication.Counter counter =
                first.getBean(SharedContextApplication.Counter.class);
        int original = counter.get();

        try {
            int next = counter.increment();
            assertThat(next).isEqualTo(original + 1);
            assertThat(second.getBean(
                    SharedContextApplication.Counter.class).get())
                    .isEqualTo(original + 1);
        }
        finally {
            // Cleanup is cheaper than evicting the whole context.
            counter.restore(original);
        }
    }

    @Test
    void dirtyAfterClassEvictsThenSameKeyReloads()
            throws Exception {
        ApplicationContext old = load(PlainFixtureA.class);
        TestContextManager manager =
                new TestContextManager(DirtyAfterFixture.class);

        manager.beforeTestClass();
        try {
            ApplicationContext dirtyFixtureContext =
                    manager.getTestContext().getApplicationContext();

            // @DirtiesContext itself does not make a new cache key.
            assertThat(dirtyFixtureContext).isSameAs(old);
        }
        finally {
            // Triggers the DirtiesContext AFTER_CLASS test listener.
            manager.afterTestClass();
        }

        ApplicationContext fresh = load(PlainFixtureB.class);
        assertThat(fresh).isNotSameAs(old);
    }
}
```

### 13.1. Phân biệt identity tests với integration behavior tests

| Method | Điều được chứng minh |
|---|---|
| `equalMockMetadataAcrossClassesUsesSameContext` | Hai classes mock giống nhau reuse context và mock bean |
| `nonOverriddenContextDiffersFromMockContext` | Plain/override có cache keys khác |
| `activeProfileChangesCacheKey` | Profile là thành phần cache key |
| `testBeanFactoryCreatesSeparateReplacementContext` | @TestBean tạo replacement bean trong config khác |
| `singletonMutableStateIsVisibleAcrossSharedContexts` | Shared singleton có state; cleanup ngăn nhiễm chéo |
| `dirtyAfterClassEvictsThenSameKeyReloads` | @DirtiesContext evict; lookup sau reload |

**Sáu methods**, cộng 4 từ hai lớp Mockito = **10 methods**. Fixture classes chỉ chứa annotations, không chứa @Test. Lúc so sánh “khác context”, một variant context có thể **đã tồn tại sẵn** trong cache; assertion chỉ nói nó **khác baseline key**, không nhất thiết vừa được tạo lần đầu.

### 13.2. Vì sao không assert số lần khởi động bằng UUID/global counter?

Spring Framework cache lookups có thể diễn ra nhiều lần cho một test method, và JUnit execution order khác nhau. Dùng global static counter “phải tăng chính xác N lần” khiến test dễ flaky nếu có caches hoặc framework listeners gọi lookup thêm. So sánh Java object identity ngay trong cùng method rõ hơn.

### 13.3. @DirtiesContext trong fixture được kích hoạt bằng lifecycle

Trong test cuối, `TestContextManager.beforeTestClass()` và `afterTestClass()` kích hoạt test listeners theo annotation của `DirtyAfterFixture`. Việc này phục vụ mục đích kiểm chứng **AFTER_CLASS** có tác dụng eviction ngay trong cùng method. Production tests thông thường không cần tự tạo TestContextManager; `SpringExtension` tự gọi các lifecycle callbacks.

**Quan trọng:** test cuối không nên chạy song song với các tests khác cùng key, vì nó cố ý close context. Demo đặt JUnit parallel disabled và Gradle một worker để tránh race.

## 14. Cách chạy

**Linux/macOS**, khi project có Gradle Wrapper:

```bash
./gradlew test --tests "com.example.sharedctx.ClockMockAlphaTest"
./gradlew test --tests "com.example.sharedctx.ClockMockBetaTest"
./gradlew test --tests "com.example.sharedctx.CacheBehaviorTest"

# Full demo suite:
./gradlew test
```

**Windows PowerShell**:

```powershell
.\gradlew.bat test --tests "com.example.sharedctx.ClockMockAlphaTest"
.\gradlew.bat test --tests "com.example.sharedctx.ClockMockBetaTest"
.\gradlew.bat test --tests "com.example.sharedctx.CacheBehaviorTest"
.\gradlew.bat test
```

**Kỳ vọng của mã:** 10 JUnit methods được phát hiện/chạy và pass với Spring Boot 3.5.16, Framework 6.2 và test runner đúng config. Đây là bài viết được rà soát tĩnh theo APIs, **không phải báo cáo đã biên dịch hoặc chạy Gradle/JUnit thực tế**.

### 14.1. Đọc test report

Khi kiểm chứng trên máy:

- Xác nhận Java 17+ được dùng trong Gradle test worker.
- Test runner phát hiện đúng 2+2+6 = **10 @Test methods**.
- Không có @Disabled và không bị lọc mất classes.
- Nếu chạy lại một class riêng, Context cache sẽ bắt đầu theo test worker JVM mới; không kỳ vọng giữ context từ lệnh trước.
- Một build task báo UP-TO-DATE hoặc FROM-CACHE không thay cho báo cáo test đã thực sự được thực thi lần đó.
- Bật cache DEBUG khi muốn quan sát hit/miss, không cần bật mọi CI run.

### 14.2. Dùng Maven thay Gradle

Với Maven, phải có project tương ứng dùng Spring Boot 3.5 parent/BOM, starter và starter-test. Có thể chọn class test qua Maven Wrapper:

```bash
./mvnw -Dtest=CacheBehaviorTest test
```

Đây là command minh họa, không phải file pom.xml được cung cấp sẵn. Không dùng command Maven trong project chỉ có Gradle.

## 15. @DirtiesContext và thứ tự listener có gì cần lưu ý?

### 15.1. AFTER_METHOD không phải @AfterEach thông thường

`@DirtiesContext(methodMode=AFTER_METHOD)` được Spring TestContext xử lý ở phase after test method theo listener ordering. Các `@AfterEach` của JUnit có thể chạy trong phase liên quan trước/ngoài callback này tùy extension/test listeners. Đừng viết cleanup phụ thuộc một thứ tự nội bộ chưa được tài liệu bảo đảm.

Trong test có @Transactional, transactions cũng có lifecycle listener. Nếu test cần cleanup DB có thể rollback, ưu tiên transaction/fixtures hơn là dirty context. Khi thực sự dirty, việc đóng DataSource/EntityManagerFactory khiến cleanup code còn giữ references cũ có thể fail.

### 15.2. Class AFTER_CLASS ảnh hưởng tests chạy sau cùng key

Khi class A đánh dấu dirty AFTER_CLASS, class B dùng cùng key sau đó phải reload. Điều này làm bộ test chậm hơn và có thể thay context identity. Nhưng **không cần viết test phụ thuộc “A phải chạy trước B”**; các assertions của test B phải đúng dù nó được chạy riêng.

### 15.3. BEFORE_CLASS phù hợp với state có từ trước

Nếu một test class cần bắt đầu trên fresh context bất kể cache đang có gì, BEFORE_CLASS có thể phù hợp. Tuy nhiên nếu nó vẫn mutate context và bỏ lại state sau class, BEFORE_CLASS **không tự cleanup sau class**. Khi cần cả hai, cân nhắc mode class BEFORE/AFTER theo cách framework hỗ trợ hoặc tách tests/context setup. Đừng nghĩ cứ BEFORE_CLASS là test khác sẽ an toàn.

### 15.4. Các test chạy song song có thể làm BEFORE/AFTER đều nguy hiểm

Một thread khác có thể đã lấy context cũ và dùng nó ngay lúc bạn dirty. Cache eviction là operation hợp lệ nhưng không chờ mọi consumers kết thúc công việc. Do đó **“dirty trước method” không thay thế mutual exclusion** trong một suite parallel.

## 16. Bean override khác @TestConfiguration/@Primary thế nào?

Spring Boot test code còn có `@TestConfiguration`, `@Import`, `@Primary` để bổ sung/điều chỉnh test beans. Chúng không hoàn toàn tương đương override API:

- `@MockitoBean`: Spring Framework bean override qua Mockito mock, thuận tiện stubbing/verification, tham gia context customizer.
- `@MockitoSpyBean`: Wrap existing singleton real bean bằng Mockito spy.
- `@TestBean`: Override bean bằng static factory method.
- `@TestConfiguration`: Đưa thêm configuration vào test context, có thể tạo alternative @Bean, nhưng phải xét naming/candidate resolution và Boot bean-definition-overriding settings.
- `@Primary`: Chọn bean ưu tiên khi có nhiều candidates, **không tự xóa bean cũ**.
- `@Profile("test")` / `@Conditional...`: Thay tập beans theo profile/condition, có thể tạo cache key khác nếu profile khác.
- `@Import(TestBeans.class)`: Bổ sung test config classes vào context; metadata khác có thể tạo cache key khác.

Không khuyên bật global `spring.main.allow-bean-definition-overriding=true` chỉ để đè mọi bean theo tên; nó có thể giấu duplicate bean errors. Spring Framework 6.2 test-specific override facility rõ target và an toàn hơn cho nhiều tình huống.

### 16.1. Cache reuse với inherited @MockitoBean

Một abstract base test class chứa cùng mock fields và hai subclasses cùng `@SpringBootTest` metadata thường được share context. Điều này giúp giảm startup, nhưng **nó cũng tạo shared mock instance**. Khi enable parallel, không thể dựa vào “subclasses khác nhau” để có isolation.

### 16.2. @MockitoSpyBean và AOP proxy

Spy một bean đang được Spring AOP proxy (transactions, caching, security) có thể đòi hỏi xác định proxy vs target và việc verify methods không đơn giản. Hãy đọc docs cho target type, proxy/call-site và stub using doReturn khi có side effects. Không lấy việc spy verify call làm bằng chứng transaction thực commit/rollback đúng; cần integration test behavior.

## 17. Chạy song song an toàn hơn: phân nhóm theo rủi ro

Thay vì bật parallel toàn suite, phân loại:

| Nhóm | Khuyến nghị |
|---|---|
| Pure Java/JUnit unit tests stateless | Có thể chạy parallel nếu không shared globals |
| Spring tests read-only, không overrides/dirty | Có thể chạy parallel sau khi xác minh lifecycle/resources |
| Tests có @MockitoBean/@MockitoSpyBean | Ưu tiên serial theo Spring 6.2 docs |
| Tests có @DirtiesContext | Ưu tiên serial, không overlap cùng context |
| DB transaction tests độc lập | Xem isolation level, fixtures và threads |
| Shared external DB/Kafka/file | Unique resources hoặc serial/coordination |
| Testcontainers static/shared container | Quản lý lifecycle, cache key, shared topics/databases |
| Real HTTP RANDOM_PORT | Port tự động, nhưng DB/bean state có thể vẫn shared |
| Context hierarchy + dirty | Cẩn thận parent/child eviction |
| Native/AOT/other JVM test workers | Xử lý riêng, không dựa JUnit locks cross-process |

### 17.1. Một cách tách Gradle tasks

Dưới đây là **snippet ý tưởng**, cần project có source sets/tags phù hợp:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'spring-shared-context'
    }
    maxParallelForks = 4
}

tasks.register('sharedContextTest', Test) {
    description = 'Run shared-context Spring tests serially'
    group = 'verification'
    useJUnitPlatform {
        includeTags 'spring-shared-context'
    }
    maxParallelForks = 1
    forkEvery = 0
}
```

**Không coi snippet này là đủ để chạy ngay nếu task chưa cấu hình testClassesDirs/classpath hoặc project dùng Java plugin conventions khác.** Một dedicated Test task thường cần gán testClassesDirs và classpath từ sourceSet.test, và `check.dependsOn(...)` khi muốn CI chạy cả hai groups. Trong sample runnable, ta chọn một test task serial đơn giản để tránh cấu hình gây nhầm.

### 17.2. @ResourceLock có thể giảm phạm vi serialize

Khi một số tests cùng ghi một resource Java static/map, `@ResourceLock(value="resource-id", mode=READ_WRITE)` có thể giúp ngăn chúng overlap **nếu tất cả tests dùng resource đó đều tuân thủ**. Với @DirtiesContext hoặc Mockito overrides, lock vẫn không thay mọi khuyến nghị serial của Spring TestContext.

### 17.3. @Execution(SAME_THREAD) không serial hóa các test classes khác

Một lỗi thường gặp: đặt `@Execution(SAME_THREAD)` trên class A rồi nghĩ class B không thể chạy cùng lúc. SAME_THREAD điều khiển execution của A và children theo JUnit rules; nó **không tạo khóa toàn suite**. Dùng task-level serial, @Isolated hoặc toàn bộ resource coordination theo thiết kế, không dựa vào một annotation cục bộ.

## 18. Troubleshooting các hiện tượng khó hiểu

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
|---|---|---|
| Test đơn lẻ pass, suite fail | Shared mock/singleton/DB state | Isolate setup, reset/cleanup, kiểm tra parallel |
| Stub từ class A “rò” sang class B | Cùng context/mock, reset listener/mode sai | @MockitoBean default reset, verify after method |
| Mock trả null bất chợt | Test khác reset cùng mock concurrently | Chạy serial hoặc tách context hợp lý |
| Verify(mock) thấy nhiều calls hơn dự kiến | Concurrent tests hoặc no reset | Serial, reset listeners, per-method stubbing |
| ApplicationContext no longer active | Test khác dirty hoặc LRU evict | Ngừng parallel trong group, xem cache logs |
| @DirtiesContext mọi class làm suite chậm | Evict context liên tục | Reset beans/mock/DB thay vì context |
| Two classes same @SpringBootTest nhưng contexts khác | Override metadata/qualifier/profile khác | So effective cache key |
| @MockitoBean tạo mock dù production bean mất | Default REPLACE_OR_CREATE | enforceOverride=true khi kiểm tra existing bean |
| @MockitoSpyBean startup fail | Zero/multiple target candidates | Chính xác bean name/qualifier, existing singleton |
| @TestBean factory not found | Thiếu static no-arg factory hoặc methodName sai | Sửa name/signature/visibility |
| TestBean fake giữ state qua methods | Singleton replacement cached | Stateless fake/reset() |
| Mocks không reset sau method | reset=NONE hoặc custom listeners | Phục hồi listener/default mode |
| Reset mock giúp pass nhưng real bean vẫn sai | Mock đã bỏ behavior cần test | Thêm integration test real implementation |
| Count DB rollback nhưng Kafka messages còn | DB rollback khác broker state | Cleanup topic/consumer-group fixtures |
| Test A @DirtiesContext làm test B fail ngẫu nhiên | Race invalidation | Tách serial task/tránh dirty |
| Same test class ở fork JVM khác reload context | Static cache process-scoped | Review Gradle/Maven fork settings |
| Cache size đạt 32, nhiều reloads | LRU eviction do nhiều unique configs | Giảm key variation, xem memory |
| Chỉnh mock field name tăng startup | Fallback qualifier đổi | Stable target/field names |
| Context hierarchy invalidation quá rộng | Default EXHAUSTIVE | Xem hierarchyMode/contextName |
| @Transactional được đặt trên RANDOM_PORT test | Server thread transaction khác | Explicit DB cleanup |
| @TestInstance(PER_CLASS) và singleton bean lẫn nhau | JUnit object lifecycle khác Spring cache | Tách lifecycle/correct cleanup |
| Tests chạy theo order mới fail | Implicit state dependency | Mỗi test tự setup/assert/reset |

## 19. Chẩn đoán cache miss và context closed

Spring TestContext cache log category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Trong một số test logging setups, cấu hình logger của test worker phải được áp dụng đủ sớm (Logback test config hoặc JVM property). Thông số hữu ích:

- Current cache size/maxSize.
- Cache hits và misses.
- Number of parent contexts (khi hierarchy).
- Các context bị evict/close.
- Failure threshold preemptively skipped startup cases.

Default `spring.test.context.cache.maxSize=32`. Có thể đặt JVM system property trước khi TestContext framework init:

```text
-Dspring.test.context.cache.maxSize=64
```

Đừng tăng maxSize ngay khi thấy một lỗi “not active”; trước tiên xem @DirtiesContext/parallel races và context key variations. Tăng cache size giúp LRU thrash nếu memory đủ, **không giải quyết shared mock reset race**.

### 19.1. Failure threshold khác context cache hit

Spring Framework 6.1+ có context failure threshold mặc định **1** theo key: nếu context startup fail một lần, lần tiếp theo có thể bị skip sớm với `IllegalStateException`. Đây **không phải** cache một context thành công. Khi log báo threshold exceeded, tìm **root cause startup failure đầu tiên**. Đừng đặt failure threshold rất cao chỉ để CI lặp lại cấu hình lỗi.

## 20. Tình huống @DirtiesContext cần giữ lại

Có những bài test thật sự cần rebuild context:

1. Thay bean definitions hoặc factory environment theo cách không thể restore.
2. Một test intentionally thay ApplicationContext lifecycle, stop/restart bean infrastructure.
3. Reconfiguration global cho Spring container không thể reverse qua bean API.
4. Một test phá internal singleton caches mà không có safe reset và behavior khác phụ thuộc context sạch.
5. Embedded infrastructure gắn với lifecycle context bị đóng/restart làm graph không còn hợp lệ.

Khi đó:

- Dùng method-level dirty nếu chỉ một method làm hỏng context.
- Dùng AFTER_CLASS nếu toàn class thực sự mutate.
- Dùng BEFORE_CLASS nếu muốn nhận fresh context, và xử lý cleanup sau class nếu còn dirty.
- Cân nhắc cache key variant để tách một cấu hình test có yêu cầu khác.
- Chạy serial với nhóm tests dùng cùng key hoặc còn shared resources.
- Đo tác động startup thay vì thêm dirties vô điều kiện.
- Không tin @DirtiesContext xóa dữ liệu external DB/Kafka hoặc static state.

**Ví dụ phân biệt:** test thay một feature-flag singleton object có API restore() đáng tin → restore trong finally tốt hơn. Test mutate BeanFactory definitions khiến graph không nhất quán → @DirtiesContext có thể là lựa chọn đúng.

## 21. Bài tập thực hành và đáp án

### A. Hai classes cùng @SpringBootTest và cùng @MockitoBean

Có phải chắc chắn có hai mock instances khác nhau?

**Không.** Nếu effective context key giống và cache hit, có thể share cùng ApplicationContext và mock bean. Default reset giúp cô lập *sequential tests* nhưng không làm mock thành per-method instance.

### B. Thêm @DirtiesContext ở mọi method để xóa stub

Có nên?

**Không.** @MockitoBean default `MockReset.AFTER` thường reset stubbings/invocations sau method, không cần rebuild context. Chỉ dirty khi context thực sự không an toàn.

### C. Test A dirty AFTER_CLASS, test B đang chạy cùng context

Điều gì có thể xảy ra?

**Context bị đóng trong khi B sử dụng**, dẫn đến intermittent “not active”/bean lifecycle errors. Tránh parallel overlap; đừng kỳ vọng @DirtiesContext đợi mọi request/threads hoàn thành.

### D. Hai lớp mock type giống, field names khác

Có thể gây thêm context startup?

**Có.** Field name có thể là fallback qualifier và ảnh hưởng cache key. Dùng tên ổn định hoặc explicit bean name khi target giống nhau.

### E. @MockitoBean tạo mock dù bean thật chưa từng tồn tại

Tại sao?

Mặc định `REPLACE_OR_CREATE`. Khi cần bắt buộc bean production có sẵn, dùng `enforceOverride=true` để fail nhanh nếu bean vắng.

### F. @MockitoSpyBean nhưng bean là prototype

Có hợp lệ trong Framework 6.2 test override facility không?

**Không theo cơ chế chung**, override chỉ hỗ trợ singleton beans. Spy cũng yêu cầu đúng một existing candidate.

### G. @TestBean factory method là non-static

Có hợp lệ không?

**Không.** Factory phải static, zero-arg, compatible return type. Có thể cung cấp explicit methodName để tránh convention ambiguity.

### H. Transaction rollback có reset singleton map không?

**Không.** Rollback DB không xóa in-memory singleton fields. Dùng reset/clear riêng hoặc dirty nếu không thể khôi phục.

### I. JUnit @ResourceLock có khóa cross Gradle forks không?

**Không.** Nó phối hợp scheduling trong Jupiter execution plan, không cross JVM processes. Shared external resources cần isolation khác.

### J. maxSize 32 đã đầy và context cũ bị reload

Có phải test đã đánh dấu dirty?

**Không nhất thiết.** LRU eviction có thể đóng entry do capacity. Xem cache DEBUG stats.

### K. Đổi profile test từ "unit" sang "integration"

Context vẫn share?

Thông thường **không**, active profiles là thành phần cache key. Khác context không tự nói tests song song an toàn nếu chúng vẫn cùng DB/broker ngoài JVM.

### L. Method @DirtiesContext(BEFORE_METHOD)

Nó dọn database records từ một Testcontainers Postgres được nhiều classes dùng không?

**Không.** Nó chỉ invalidate Spring context. DB external state cần cleanup transactions/SQL/schema riêng.

### M. MockitoBean(reset=NONE) và parallel

Đây có phải cách giải quyết race?

**Không.** Bỏ reset không bảo đảm stubbing/verify không đè nhau. Nó còn tạo nguy cơ leakage lớn hơn khi các sequential methods chia sẻ mock. Thiết kế isolation hoặc serial execution mới quan trọng.

### N. @TestBean fake có thể bị share giữa hai classes?

**Có.** Nếu override metadata và context key tương đương, fake singleton nằm trong reused context; cần stateless fake hoặc reset đáng tin.

### O. @Isolated có thay thế @DirtiesContext?

**Không.** @Isolated (JUnit Jupiter) điều khiển scheduling cô lập class trong một execution plan; @DirtiesContext điều khiển Spring context invalidation. Một test có thể cần một, cả hai hoặc không cần cái nào, tùy state/lifecycle.

## 22. Checklist QA trước khi bật parallel hoặc thêm bean override

- [ ] Đã hiểu Spring TestContext cache chia sẻ chính ApplicationContext instance.
- [ ] Không nhầm JUnit per-method test instance với Spring singleton lifecycle.
- [ ] Cùng context key hay khác key được xác định từ classes/profiles/properties/customizers.
- [ ] Mock override target/name/qualifier giống nhau được giữ nhất quán khi mục tiêu share.
- [ ] @MockitoBean default reset AFTER có test listeners phù hợp.
- [ ] Không dùng @DirtiesContext để reset stubbings/invocations đơn thuần.
- [ ] @MockitoBean(enforceOverride=true) dùng khi phải chứng minh existing bean được thay.
- [ ] @MockitoSpyBean có đúng một existing singleton, tránh side-effect stubbing.
- [ ] @TestBean static factory/bean name chính xác và fake không rò mutable state.
- [ ] Không chạy song song tests có Dirties/Mockito overrides theo khuyến nghị Spring khi chưa có isolation mạnh.
- [ ] @ResourceLock không được giả định khóa tất cả tests hoặc cross JVM forks.
- [ ] @Execution(SAME_THREAD) không bị hiểu nhầm thành toàn suite serial.
- [ ] Shared mutable beans có cleanup trong finally/@AfterEach đáng tin.
- [ ] DB/Kafka/File state được cô lập/clean riêng, không dựa context dirty.
- [ ] ThreadLocal/MDC/global system properties được restore.
- [ ] Có cơ chế reset/clear trước khi quyết định rebuild ApplicationContext.
- [ ] Nếu dùng @ContextHierarchy, hierarchyMode và contextName được review.
- [ ] Test class sử dụng @DirtiesContext không overlap với test đang dùng cùng context.
- [ ] Cache capacity/LRU/forks có thể gây reload ngoài @DirtiesContext.
- [ ] Failure threshold error được truy tới startup failure đầu tiên.
- [ ] Không assert cache hit count tuyệt đối phụ thuộc test order.
- [ ] Đã đo test time, startup count, flakiness và memory trên cùng CI.
- [ ] CI report hiển thị đúng executed/failed/skipped methods.
- [ ] Test fixtures không chứa credentials/production data.
- [ ] Java 17+/Boot 3.5/Framework 6.2 imports đã được đối chiếu.
- [ ] Khi nâng lên Boot 4/Framework 7, chạy lại tests với API mới.
- [ ] Tests có mock vẫn có integration tests bảo vệ real collaborator behavior.
- [ ] Không ép tất cả tests share context nếu chúng có semantic requirements khác.
- [ ] Không thêm @DirtiesContext đại trà như một “tối ưu cách ly”.
- [ ] Nhận diện tests dùng shared services ở nhiều JVM/parallel tasks.

## 23. Tổng kết

**@DirtiesContext và bean override giải quyết những vấn đề khác nhau.**

- Context cache của Spring TestContext giữ **chính ApplicationContext instance** theo key; hai test classes khác nhau có thể share cùng singleton beans.
- `@MockitoBean`, `@MockitoSpyBean` và `@TestBean` đưa **bean override metadata vào cache key**; cùng override có thể share context đã thay.
- `@MockitoBean` mặc định reset sau test method (MockReset.AFTER), nhưng reset mock **không đóng context** và **không bảo đảm concurrency-safe**.
- `@DirtiesContext` loại/đóng context khiến lần lookup sau reload; nó đắt hơn nhiều so với reset bean/mock/DB state.
- Spring Framework 6.2 khuyến cáo tránh chạy parallel với `@DirtiesContext`, `@MockitoBean` và `@MockitoSpyBean` do nguy cơ reset/close trong lúc test khác đang dùng chung context.
- JUnit scheduling controls có thể giúp, nhưng phải hiểu phạm vi, đặc biệt các forked JVMs và external resources.
- Chỉ dirty khi state/context thật sự không còn an toàn; còn lại ưu tiên fixtures cô lập và cleanup đúng ranh giới.

Ví dụ đi kèm 10 JUnit methods dùng Java 17+, Boot 3.5.16, Framework 6.2 chứng minh reuse theo effective key, mock override khác plain context, profile variation, @TestBean replacement, shared counter state và controlled @DirtiesContext eviction. Đây là **test design dựa trên API documentation**, chưa tuyên bố đã thực thi biên dịch/JUnit trong phiên viết nội dung.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache, key, maxSize 32/LRU và DEBUG statistics.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): nhóm test không nên chạy parallel, context no longer active.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): method/class modes, hierarchy clearing.
- [Spring Framework 6.2 — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): override, qualifier, reset và cache key.
- [Spring Framework 6.2 — @TestBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testbean.html): static factory replacement.
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): REPLACE/REPLACE_OR_CREATE/WRAP, lifecycle.
- [Spring Framework 6.2 — TestContextManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/TestContextManager.html): lifecycle methods and context access.
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html): failure threshold.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, context setup and slices.
- [JUnit 5 — Parallel Execution](https://docs.junit.org/5.13.0/user-guide/#writing-tests-parallel-execution): @ResourceLock, @Isolated, execution mode and resource scheduling.

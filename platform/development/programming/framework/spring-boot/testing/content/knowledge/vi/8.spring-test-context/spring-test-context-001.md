# TestContext framework và vai trò của SpringExtension

Spring Boot có thể được kiểm thử ở nhiều cấp: từ một hàm Java thuần đến service, controller, repository, transaction và một ứng dụng đã cấu hình đầy đủ. Khi test cần đến dependency injection, cấu hình bean, profile, transaction hoặc các tính năng Spring khác, việc tự tạo mọi đối tượng bằng `new` không còn đủ. **Spring TestContext Framework** cung cấp nền tảng để tạo, quản lý và tái sử dụng `ApplicationContext` cho các bài kiểm thử. **`SpringExtension`** là cầu nối đưa khả năng đó vào vòng đời của **JUnit Jupiter (JUnit 5)**.

Bài này giải thích mối quan hệ giữa JUnit, SpringExtension và TestContext Framework; những thành phần đứng phía sau annotation; cách context được bootstrap, inject và cache; cách các listener làm việc qua từng pha test; sự khác biệt giữa `@SpringJUnitConfig` và `@SpringBootTest`; cùng những giới hạn quan trọng liên quan đến transaction, test isolation và chi phí thực thi.

**Sau bài học, bạn có thể:**

- Phân biệt `TestContext`, `ApplicationContext`, `TestContextManager`, `TestExecutionListener` và `SpringExtension`.
- Chọn JUnit thuần, Spring TestContext thuần, test slice hoặc Spring Boot integration test theo hợp đồng cần bảo vệ.
- Cấu hình `@ExtendWith(SpringExtension.class)`, `@ContextConfiguration` và `@SpringJUnitConfig` đúng vai trò.
- Inject Spring bean vào field, constructor, test method và lifecycle callback khi cần.
- Hiểu các pha trong vòng đời JUnit Jupiter mà SpringExtension chuyển tiếp cho TestContext.
- Dùng `@ActiveProfiles`, `@TestPropertySource`, `@Transactional` và `@DirtiesContext` đúng mục đích.
- Hiểu cơ chế cache, nguyên nhân tạo context mới, và các lỗi thường gặp khi chạy test Spring Boot.

## 1. Bắt đầu từ nhu cầu: khi nào test cần Spring?

Xét một class không có phụ thuộc Spring:

```java
public final class PricePolicy {
    public boolean hasFreeShipping(int total) {
        if (total < 0) {
            throw new IllegalArgumentException("total must be >= 0");
        }
        return total >= 200;
    }
}
```

Đây là **mã minh họa**: nếu đưa vào file Java riêng cần khai báo package theo dự án. Với phép tính thuần, một JUnit test có thể dùng `new PricePolicy()` và assert kết quả; không cần Spring. Nhưng nếu muốn kiểm tra rằng một service đã được Spring tạo, property từ cấu hình đã inject đúng, interceptor transaction hoạt động, hay repository kết nối thật với database, ta cần các thành phần do Spring quản lý.

| Điều cần kiểm chứng | Cấp kiểm thử phù hợp | Có nhất thiết dùng Spring TestContext? |
|---|---|---|
| Quy tắc tính toán độc lập | Unit test JUnit | Không |
| Service nhận dependency qua constructor và logic của service | Unit test với mock/fake collaborator | Không, nếu wiring của Spring không phải mục tiêu |
| Bean có được tạo và inject đúng theo cấu hình không? | Spring context/integration test | Có |
| REST routing, binding, JSON và security MVC | Spring MVC slice với `@WebMvcTest` | Có, qua tích hợp Spring Test |
| JPA mapping/query và DB constraint | Persistence slice với `@DataJpaTest` | Có |
| Transaction, cấu hình auto-configuration, tích hợp nhiều bean | `@SpringBootTest` hoặc context test phù hợp | Có |
| HTTP thật qua cổng mạng và nhiều thành phần | Integration/end-to-end test | Thường có, nhưng còn cần kiểm soát môi trường và dữ liệu |

**Quy tắc quan trọng:** đừng khởi động Spring chỉ vì test có lớp `@Service`. Một Spring bean vẫn là Java object. Chỉ nạp context khi **khả năng của Spring là một phần điều cần xác minh** hoặc các dependency thật đòi hỏi nó.

## 2. Các thành phần cốt lõi của Spring TestContext Framework

Tên `TestContext` rất dễ bị nhầm với `ApplicationContext`. Chúng có vai trò khác nhau.

| Thành phần | Vai trò | Điều cần nhớ |
|---|---|---|
| **`ApplicationContext`** | Container chứa bean, dependency, properties, resource, event và các thành phần cấu hình Spring | Là môi trường chạy bean mà test muốn sử dụng |
| **`TestContext`** | Ngữ cảnh của **bài kiểm thử**: test class, instance, method, exception, các attribute và cách truy cập application context | Không phải tên khác của `ApplicationContext` |
| **`TestContextManager`** | Điều phối một `TestContext` và phát các callback vòng đời tới listener | Điểm kết nối của framework kiểm thử với TestContext |
| **`TestExecutionListener`** | Các hook chạy trước/sau các pha thực thi test để inject dependency, xử lý transaction, SQL, context dirty... | Có listener mặc định và có thể cấu hình listener tùy chỉnh |
| **`TestContextBootstrapper`** | Đọc cấu hình test, chọn loader/listener, xây dựng thông tin để khởi tạo TestContext | Boot có bootstrapper riêng để xử lý đặc tính của Boot |
| **`ContextLoader` / `SmartContextLoader`** | Cách nạp `ApplicationContext` từ các class, location và nguồn cấu hình | Không phải JUnit trực tiếp tạo bean |
| **`SpringExtension`** | JUnit Jupiter extension chuyển callback JUnit sang `TestContextManager`, hỗ trợ resolve tham số từ Spring context | Là lớp **tích hợp JUnit Jupiter**, không phải bản thân container |

Sơ đồ quan hệ:

```text
JUnit Platform / JUnit Jupiter
         |
         | chạy @Test, @BeforeEach, @AfterEach...
         v
  SpringExtension   (@ExtendWith)
         |
         | chuyển callback vòng đời + giải quyết tham số
         v
  TestContextManager
         |
         +--> TestContext (test class / method / instance / attributes)
         |
         +--> TestExecutionListener (DI, transaction, SQL, cache...)
         |
         +--> TestContextBootstrapper / ContextLoader
                         |
                         v
               ApplicationContext
                (bean, profile, data source...)
                         |
                         +--> Context cache tái sử dụng khi cấu hình tương đương
```

Sơ đồ diễn đạt **trách nhiệm**, không phải một call stack cố định cho mọi callback. Context có thể được tải khi một listener hoặc callback thực sự cần nó; việc sử dụng extension không đồng nghĩa mỗi test method tạo một container mới.

## 3. `SpringExtension` đứng ở đâu trong JUnit Jupiter?

JUnit Jupiter hỗ trợ extension model qua `@ExtendWith`. Một extension có thể can thiệp lifecycle, post-process test instance và cung cấp tham số cho method. `SpringExtension` triển khai các điểm mở rộng phù hợp để Spring TestContext tham gia vòng đời JUnit.

Khi viết:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class ExampleTest {
    // ...
}
```

ta yêu cầu:

1. **JUnit Jupiter** dùng `SpringExtension` để tích hợp Spring vào bài test.
2. **Spring TestContext** dùng `@ContextConfiguration` để biết class cấu hình `TestConfig` cần được nạp.
3. Test có thể nhận các bean từ `ApplicationContext`; listener của Spring có thể chuẩn bị instance và xử lý transaction, SQL hoặc cleanup theo annotation.

Ví dụ trên là **cú pháp minh họa**; để biên dịch cần import annotation, class `TestConfig` thực tế và các method `@Test`. Ở mục 7 có ví dụ hoàn chỉnh.

### 3.1. Vì sao cần cả hai annotation?

`@ExtendWith(SpringExtension.class)` chỉ **đăng ký cầu nối với JUnit**; nó không nói rõ tất cả bean hay configuration sẽ đến từ đâu.

`@ContextConfiguration` mô tả **nguồn cấu hình context** (như `classes`, `locations`, `initializers`, loader tùy chỉnh...). Nó không tự thay thế việc đăng ký extension trong một JUnit Jupiter test nếu không có annotation tổng hợp khác.

Spring cung cấp `@SpringJUnitConfig` để gộp cả hai việc. Do đó, hai cách sau tương đương về mục đích cấu hình thông thường:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class FirstTest {
}
```

```java
@SpringJUnitConfig(TestConfig.class)
class SecondTest {
}
```

Hai class chỉ minh họa cấu hình, chưa chứa `@Test` thực tế. **Không gắn thêm `@ExtendWith(SpringExtension.class)` một lần nữa khi đã dùng `@SpringJUnitConfig`**; annotation tổng hợp đã chứa extension.

### 3.2. JUnit thực hiện điều gì, Spring thực hiện điều gì?

- JUnit Jupiter khám phá test, chạy `@Test`, `@ParameterizedTest`, kiểm tra assertion và quản lý lifecycle JUnit.
- SpringExtension đưa TestContext Framework vào các điểm lifecycle, cung cấp argument resolver để test nhận bean, property hoặc `ApplicationContext`.
- Spring TestContext chịu trách nhiệm bootstrap, truy xuất `ApplicationContext`, gọi listener và sử dụng context cache.
- Spring Boot mở rộng quá trình bootstrap để nạp ứng dụng bằng `SpringApplication`, hỗ trợ auto-configuration và cơ chế test chuyên biệt.

Nếu một test đơn giản chỉ dùng JUnit `@Test` + `assertEquals`, nó không tự động cần SpringExtension.

## 4. Vòng đời: JUnit và TestContext phối hợp như thế nào?

Một lớp JUnit Jupiter có các mốc `@BeforeAll`, khởi tạo test instance, `@BeforeEach`, `@Test`, `@AfterEach`, `@AfterAll`. SpringExtension chuyển những mốc này thành callback quản lý bởi TestContextManager.

| Pha có ý nghĩa | Callback JUnit/SpringExtension | Callback TestContextManager / TestExecutionListener |
|---|---|---|
| Trước toàn bộ test trong class | Before-all extension callback | `beforeTestClass` |
| Sau khi JUnit tạo instance | Test-instance post-processing | `prepareTestInstance` (ví dụ inject `@Autowired` field) |
| Trước `@BeforeEach` của test | Before-each extension callback | `beforeTestMethod` |
| Sau `@BeforeEach`, ngay trước `@Test` | Before-test-execution callback | `beforeTestExecution` |
| Ngay sau `@Test`, trước `@AfterEach` | After-test-execution callback | `afterTestExecution` |
| Sau `@AfterEach` | After-each extension callback | `afterTestMethod` |
| Sau toàn bộ test trong class | After-all extension callback | `afterTestClass` |

**Hai mốc “before” khác nhau**: `beforeTestMethod` được gọi trước setup `@BeforeEach`, còn `beforeTestExecution` được gọi ngay trước thân `@Test`. Tương tự, `afterTestExecution` chạy ngay sau thân test, còn `afterTestMethod` chạy sau teardown `@AfterEach`. Điều này quan trọng nếu bạn tự viết listener đo thời gian test method, chuẩn bị fixture hoặc thực hiện cleanup.

Một số TestExecutionListener phổ biến trong Spring TestContext có nhiệm vụ như:

- `DependencyInjectionTestExecutionListener`: inject dependency vào test instance.
- `DirtiesContextBeforeModesTestExecutionListener` và `DirtiesContextTestExecutionListener`: xử lý các chế độ `@DirtiesContext`.
- `TransactionalTestExecutionListener`: khởi tạo/kết thúc test-managed transaction và xử lý `@BeforeTransaction`, `@AfterTransaction`.
- `SqlScriptsTestExecutionListener`: xử lý `@Sql` để chuẩn bị và dọn dữ liệu SQL.
- `EventPublishingTestExecutionListener`: phát các test execution events khi điều kiện phù hợp.

**Đừng hiểu listener là JUnit callback trực tiếp:** `TestExecutionListener` là abstraction của Spring, dùng chung với nhiều test framework; SpringExtension là adapter riêng cho JUnit Jupiter.

## 5. `TestContext` khác với `ApplicationContext` ở điểm nào?

`ApplicationContext` là Spring container, nơi bean được tạo/inject. `TestContext` chứa thông tin liên quan đến **việc chạy test**, gồm test class, test instance, test method, exception và attribute phục vụ các listener.

Ví dụ với một listener tùy chỉnh, ta có thể đọc tên method đang kiểm thử:

```java
// Đoạn minh họa: không phải file độc lập.
// Trong implementation của TestExecutionListener:
@Override
public void beforeTestExecution(TestContext context) {
    String name = context.getTestMethod().getName();
    System.out.println("Running: " + name);
}
```

Ở đây `context` là `org.springframework.test.context.TestContext`, **không** phải `org.springframework.context.ApplicationContext`. Trong code thực, test/bean thường chỉ cần `@Autowired` hoặc nhận một `ApplicationContext` qua argument injection; không phải tự thao tác `TestContextManager`.

Thông thường bạn **không cần tạo `TestContextManager` bằng `new`** trong một test JUnit Jupiter dùng SpringExtension. Framework thực hiện bước điều phối. Những API này chủ yếu cần biết để debug/test custom integration hoặc viết extension/listener.

## 6. Các annotation cần phân biệt

| Annotation | Tầng | Tác dụng chính |
|---|---|---|
| `@ExtendWith(SpringExtension.class)` | JUnit Jupiter | Đăng ký tích hợp Spring TestContext |
| `@ContextConfiguration` | Spring TestContext | Chỉ định class/resource/loader/initializer để dựng context |
| `@SpringJUnitConfig` | Spring TestContext + Jupiter | Gộp extension và context configuration cho test thường |
| `@SpringJUnitWebConfig` | Spring TestContext + Jupiter | Gộp extension, context config và web application context |
| `@SpringBootTest` | Spring Boot Test | Dùng SpringApplication/Boot context; đã tích hợp SpringExtension |
| `@WebMvcTest`, `@DataJpaTest` | Spring Boot Test slices | Nạp các phần thích hợp của ứng dụng để test một ranh giới |
| `@ActiveProfiles` | Spring TestContext | Chọn profile cho context trong test |
| `@TestPropertySource` | Spring TestContext | Bổ sung/ghi đè property để dựng context trong test |
| `@Autowired` | Spring DI | Inject bean vào field/constructor/parameter được hỗ trợ |
| `@Transactional` trên test | Spring TestContext transaction | Chạy test trong test-managed transaction khi hạ tầng phù hợp |
| `@Sql` | Spring TestContext SQL | Thực thi script/statement SQL trước/sau test theo cấu hình |
| `@DirtiesContext` | Spring TestContext cache | Đánh dấu context không nên tiếp tục tái sử dụng |
| `@TestExecutionListeners` | Spring TestContext | Đăng ký/thay đổi listener tham gia lifecycle |

**Lưu ý phiên bản:** Ví dụ sử dụng **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+ / JUnit Jupiter 5**. Nếu dự án dùng Spring Framework 7 hoặc Spring Boot 4, hãy kiểm tra dependency và tài liệu đúng phiên bản vì nhiều API/phụ thuộc kiểm thử đã phát triển. Nguyên tắc bridge qua extension và quản lý context vẫn là trọng tâm của bài.

## 7. Ví dụ hoàn chỉnh: `@SpringJUnitConfig` với Spring TestContext thuần

Ta tạo một service nhỏ nhận prefix từ Spring property. Mục tiêu: xác nhận TestContext nạp một `@Configuration`, resolve `Environment`, tạo bean và inject bean vào test. Không cần khởi động toàn bộ Spring Boot.

**`src/main/java/com/example/testcontext/plain/GreetingService.java`**

```java
package com.example.testcontext.plain;

import java.util.Objects;

public final class GreetingService {
    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name.strip() + "!";
    }
}
```

**`src/test/java/com/example/testcontext/plain/GreetingTestConfig.java`**

```java
package com.example.testcontext.plain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class GreetingTestConfig {

    @Bean
    GreetingService greetingService(Environment environment) {
        String prefix = environment.getRequiredProperty("greeting.prefix");
        return new GreetingService(prefix);
    }
}
```

**`src/test/java/com/example/testcontext/plain/GreetingSpringTest.java`**

```java
package com.example.testcontext.plain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class GreetingSpringTest {

    @Autowired
    GreetingService greetingService;

    @Test
    void createsBeanFromConfigurationAndProperties() {
        String result = greetingService.greet("  Mai  ");

        assertEquals("Xin chào, Mai!", result);
    }

    @Test
    void injectsTheSameSingletonBeanFromContext(
            @Autowired ApplicationContext applicationContext) {

        assertSame(greetingService,
                applicationContext.getBean(GreetingService.class));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> greetingService.greet("  "));
    }
}
```

### 7.1. Giải thích bằng chính luồng thực thi

1. JUnit phát hiện `GreetingSpringTest`.
2. Annotation `@SpringJUnitConfig` đăng ký `SpringExtension` và chỉ ra `GreetingTestConfig`.
3. `@TestPropertySource` đưa property `greeting.prefix=Xin chào` vào context test.
4. Khi context cần được nạp, Spring tạo bean `GreetingService` qua method `@Bean`. `Environment` được Spring resolve; `getRequiredProperty` thất bại rõ nếu thiếu property.
5. `DependencyInjectionTestExecutionListener` inject bean vào field `greetingService` trên test instance.
6. Test method gọi service thật, assert giá trị trả về; method thứ hai nhận trực tiếp `ApplicationContext` qua `@Autowired` parameter do SpringExtension resolve.
7. Không có database, web server, transaction hoặc I/O ngoài trong ví dụ này.

**Vì sao `assertSame` đúng ở test thứ hai?** Trong cấu hình ở trên, `@Bean` có scope singleton mặc định, và field lẫn `applicationContext.getBean(...)` trỏ đến cùng bean trong cùng context. Nếu bean cố ý có prototype scope thì không dùng assertion này.

**Vì sao không dùng `@SpringBootTest`?** Bài đang kiểm tra Spring Java configuration và dependency injection nhỏ. Một context nhỏ từ `@SpringJUnitConfig` đủ chứng minh mục tiêu; `@SpringBootTest` sẽ bổ sung khối lượng auto-configuration không cần thiết.

### 7.2. Viết annotation tường minh cũng có cùng ý nghĩa

Có thể thay hai annotation phía trên test bằng:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class GreetingSpringTest {
    // Giữ nguyên các method @Test trong ví dụ ở trên.
}
```

Đây chỉ là **phiên bản cú pháp của header**, không phải một class bổ sung cần biên dịch cùng tên. Cần import `org.junit.jupiter.api.extension.ExtendWith`, `org.springframework.test.context.junit.jupiter.SpringExtension` và `org.springframework.test.context.ContextConfiguration` nếu dùng cách tường minh.

## 8. Injection trong test: field, constructor, parameter và lifecycle

SpringExtension tích hợp với `ParameterResolver` của JUnit Jupiter. Ngoài field `@Autowired` mà listener xử lý, bạn có thể yêu cầu Spring cung cấp bean ngay tại tham số constructor, `@Test` hoặc `@BeforeEach`.

Ví dụ thay thế **chỉ để minh họa cú pháp**, dùng cấu hình và service của mục 7:

```java
@SpringJUnitConfig(GreetingTestConfig.class)
@TestPropertySource(properties = "greeting.prefix=Xin chào")
class ParameterInjectionTest {

    @Test
    void receivesBeanAsMethodArgument(
            @Autowired GreetingService service) {
        assertEquals("Xin chào, An!", service.greet("An"));
    }

    @BeforeEach
    void prepare(@Autowired ApplicationContext context) {
        assertNotNull(context.getBean(GreetingService.class));
    }
}
```

Đoạn này cần import JUnit/Spring assertions và annotations tương ứng; đây là **mẫu minh họa**, không phải một file độc lập trong danh sách chạy ở mục 18.

Khi dùng constructor injection trong JUnit test, một tham số có `@Autowired` hoặc constructor được đánh dấu phù hợp sẽ được Spring resolve. Nhưng cần hiểu **lifecycle của test instance**. Nếu dùng `@TestInstance(PER_CLASS)`, constructor chỉ chạy một lần; đồng thời bạn dùng `@DirtiesContext` giữa các phương thức, bean được inject từ context cũ có thể đã đóng. Trong tình huống đặc biệt này, **field/setter injection** cho phép Spring re-inject test instance theo cơ chế thích hợp; đừng giữ reference tới bean đã thuộc context bị đóng.

JUnit có thể có nhiều extension cùng xử lý tham số; nếu hai resolver cùng nhận cùng một tham số một cách xung đột, test có thể báo lỗi. Sử dụng `@Autowired` rõ ràng cho bean Spring và các parameter do JUnit cung cấp theo ngữ nghĩa framework.

**Không nhầm với constructor injection của production bean:** Trong production, dùng constructor injection là thiết kế rất tốt. Lưu ý trên chỉ nói về **constructor của test class có lifecycle PER_CLASS kết hợp thay context**, không phải lý do tránh constructor injection cho service.

## 9. Ví dụ hoàn chỉnh: `@SpringBootTest` đã bao gồm SpringExtension

`@SpringBootTest` sử dụng Spring Boot để dựng `ApplicationContext` qua `SpringApplication`, mang theo khả năng cấu hình và auto-configuration của Boot. Ở JUnit Jupiter, annotation này **đã meta-annotate `@ExtendWith(SpringExtension.class)`**, nên không cần đăng ký SpringExtension lần thứ hai.

**`src/main/java/com/example/testcontext/boot/TestContextDemoApplication.java`**

```java
package com.example.testcontext.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestContextDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/testcontext/boot/ShippingPolicy.java`**

```java
package com.example.testcontext.boot;

import org.springframework.stereotype.Service;

@Service
public class ShippingPolicy {

    public int shippingFee(int subtotal, boolean express) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        if (express) {
            return 30;
        }
        return subtotal >= 200 ? 0 : 15;
    }
}
```

**`src/test/java/com/example/testcontext/boot/ShippingPolicyContextTest.java`**

```java
package com.example.testcontext.boot;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = TestContextDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ShippingPolicyContextTest {

    @Autowired
    ShippingPolicy policy;

    @Test
    void autowiresServiceAndAppliesShippingRules() {
        assertAll("shipping rules",
                () -> assertEquals(15, policy.shippingFee(199, false)),
                () -> assertEquals(0, policy.shippingFee(200, false)),
                () -> assertEquals(30, policy.shippingFee(200, true)));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.shippingFee(-1, false));
    }
}
```

Bài test xác minh **Boot context được dựng và bean `ShippingPolicy` được Spring inject**, sau đó kiểm chứng hành vi. `webEnvironment=NONE` giúp không cần tạo môi trường web; `SpringApplication` vẫn được sử dụng để dựng context.

**Thiết kế test thực tế:** nếu chỉ muốn kiểm tra `shippingFee` tính đúng, một unit test trực tiếp `new ShippingPolicy()` sẽ nhẹ hơn. `@SpringBootTest` có giá trị khi muốn bảo vệ bootstrapping, bean wiring, auto-configuration, property hoặc tương tác nhiều bean thật. Ví dụ dùng một service đơn giản để quan sát chính cơ chế TestContext.

### 9.1. Có cần `@ExtendWith(SpringExtension.class)` nữa không?

Không. Với Spring Boot 3.3 và JUnit Jupiter, `@SpringBootTest` cùng các slice test như `@WebMvcTest` đã tích hợp SpringExtension. Thêm `@ExtendWith(SpringExtension.class)` chỉ gây nhiễu cho người đọc và không làm ứng dụng được inject “nhiều hơn”.

### 9.2. `@SpringBootTest` khởi động HTTP server không?

Tùy `webEnvironment`:

| Chế độ | Ý nghĩa |
|---|---|
| `MOCK` (mặc định với môi trường web thích hợp) | Tạo mock web environment, không tự mở embedded HTTP server |
| `RANDOM_PORT` | Mở embedded server tại cổng ngẫu nhiên, HTTP client có thể gọi thực |
| `DEFINED_PORT` | Mở server ở cổng cấu hình/cổng mặc định; dễ đụng tài nguyên nếu test chạy song song |
| `NONE` | Tạo non-web `ApplicationContext` với SpringApplication |

Đối với `MOCK`, nếu muốn thử MVC bằng `MockMvc` thì thường kết hợp `@AutoConfigureMockMvc`. Đừng cho rằng chỉ có `@SpringBootTest` là tự inject `MockMvc` vào mọi test.

## 10. Bootstrap: cấu hình được tìm thấy như thế nào?

Spring TestContext đọc annotation trên test class, xác định `TestContextBootstrapper`, chọn `ContextLoader` thích hợp, các listener, context initializer và các thông số để nạp context.

Với `@SpringJUnitConfig(GreetingTestConfig.class)`, cấu hình được khai báo tường minh. Với `@SpringBootTest` không ghi `classes`, Spring Boot thường tìm `@SpringBootConfiguration` hoặc `@SpringBootApplication` bằng cách đi từ package của test lên các package cha. Nếu không tìm thấy, test có thể báo không tìm được configuration class.

**Để tránh mơ hồ:** trong ví dụ Boot, ta viết `classes = TestContextDemoApplication.class` rõ ràng. Trong dự án thật, có thể bỏ thuộc tính này nếu package/class cấu trúc đúng và cách khám phá mặc định là phù hợp.

Không nhầm hai cấu hình:

- `@Configuration` là cấu hình Spring thông thường; khi khai báo nested class trong Boot test có thể được hiểu là cấu hình chính của test.
- `@TestConfiguration` của Boot được dùng để thêm/ghi đè bean cho ngữ cảnh test mà vẫn sử dụng cấu hình ứng dụng chính theo cơ chế Boot.

Thêm một `@ComponentScan` tùy biến ở application root có thể thay đổi hành vi exclude filter của các slice test. Khi thấy `@WebMvcTest` bất ngờ nạp nhiều bean hoặc thiếu bean, hãy kiểm tra component scanning và những cấu hình đã được import.

## 11. `@ActiveProfiles` và `@TestPropertySource` ảnh hưởng cả context lẫn cache

Một bài test có thể cần profile riêng để tránh kết nối dịch vụ production hoặc sử dụng cấu hình test:

```java
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.registration.enabled=true",
        "external.mail.enabled=false"
})
@SpringJUnitConfig(TestConfig.class)
class FeatureTest {
    // ...
}
```

Đây là **mẫu annotation**, `TestConfig` và body test chưa được định nghĩa tại đây. Hai annotation cung cấp thông tin khi Spring tạo context, nhưng bản thân chúng **không bảo đảm** production infrastructure sẽ bị vô hiệu hóa: bean và cấu hình của ứng dụng phải thật sự tôn trọng các property/profile đó.

Các điểm quan trọng:

1. `@ActiveProfiles` làm thay đổi bộ bean/config được kích hoạt theo profile.
2. `@TestPropertySource` bổ sung property phục vụ test và có độ ưu tiên phù hợp trong nguồn thuộc TestContext.
3. Nếu hai test có cấu hình context khác nhau, profile khác hoặc test property khác, chúng có thể nhận **hai cache entry** và hai context khác nhau.
4. Tránh tạo một profile/property không cần thiết cho từng test nhỏ, khiến cache bị phân mảnh và suite chậm.
5. Đối với Spring Boot, `@SpringBootTest(properties = ...)` cũng là một cách cung cấp property; nên dùng nhất quán và chỉ bổ sung khi contract thật sự cần.

**Giới hạn:** Không tự tin rằng một property đã được áp dụng chỉ vì annotation có mặt. Test nên kiểm tra hành vi/bean liên quan, như `GreetingSpringTest` đã xác nhận prefix của bean.

## 12. Context cache: vì sao nhiều test không nạp lại Spring từ đầu?

Một lợi ích lớn của TestContext Framework là **cache `ApplicationContext` theo cấu hình**. Nếu nhiều test dùng cấu hình context tương đương trong cùng JVM và cache chưa bị vô hiệu hóa, Spring có thể tái sử dụng context đã tạo, giảm chi phí khởi động.

Các yếu tố trong cache key có thể bao gồm class/resource cấu hình, initializer, loader, profile, property source, parent context, cấu hình web và các `context customizers` (ví dụ customizer do mock bean của framework cung cấp). Do đó, **không thể chỉ nhìn hai test đều dùng `@SpringBootTest` rồi kết luận chúng chắc chắn chia sẻ một context**.

Thông tin quan trọng với Spring Framework 6.x:

- Context cache mặc định giới hạn tối đa **32** entry; khi vượt giới hạn, chính sách loại bỏ theo LRU (least recently used).
- Cache thường được giữ trong **bộ nhớ static của JVM**. Hai test chạy ở hai JVM/fork khác nhau không chia sẻ trực tiếp cache này.
- `@DirtiesContext` đánh dấu context bị thay đổi đến mức không nên dùng lại; context đó bị loại khỏi cache và đóng theo mode đã chỉ định.
- Log cấp DEBUG cho category `org.springframework.test.context.cache` có thể giúp thấy thống kê hit/miss và kích thước cache.
- Thay đổi `@ActiveProfiles`, nguồn property hoặc cấu hình mock bean không cần thiết có thể làm tăng số context khác nhau.

Ví dụ:

```text
Test A: @SpringJUnitConfig(GreetingTestConfig.class)
        property greeting.prefix = Xin chào
Test B: cùng cấu hình + cùng property
        -> thường tái sử dụng context trong cùng JVM

Test C: cùng config nhưng greeting.prefix = Hello
        -> cấu hình khác, thường có cache entry khác
```

Đây là mô hình khái niệm; cache key thực còn xét metadata và customizer khác. Đừng biến tên class hoặc thứ tự chạy của suite thành giả định chắc chắn về identity của context.

### 12.1. Khi nào cần `@DirtiesContext`?

Dùng khi một test đã làm bẩn context, chẳng hạn sửa bean definition hoặc làm thay đổi trạng thái singleton theo cách mà các test khác không thể tự khôi phục. **Không mặc định gắn `@DirtiesContext` cho mọi test để “đảm bảo độc lập”**: cách đó thường làm context phải dựng lại nhiều lần và tăng runtime đáng kể.

Nếu chỉ thay đổi dữ liệu database hoặc một đối tượng request-scope, hãy cân nhắc transaction rollback, fixture cleanup, reset mock hoặc tạo dữ liệu độc lập. `@DirtiesContext` không thay thế được một chiến lược isolation có chủ đích cho DB hay tài nguyên ngoài.

## 13. TestExecutionListener: vì sao DI và transaction hoạt động?

SpringExtension không tự viết lại logic inject field, transaction hay chạy SQL script. Nó gọi TestContextManager, và **TestExecutionListener** phù hợp sẽ làm công việc tại các lifecycle callback.

Ví dụ tích hợp bean:

- Lúc chuẩn bị test instance, `DependencyInjectionTestExecutionListener` có thể inject field `@Autowired`.
- Khi một test có `@Transactional` và có transaction manager phù hợp, `TransactionalTestExecutionListener` có thể mở và kết thúc test-managed transaction.
- Với `@Sql`, `SqlScriptsTestExecutionListener` xử lý việc chạy SQL theo cấu hình.
- Với `@DirtiesContext`, các listener tương ứng biết khi nào cần đánh dấu, đóng hoặc bỏ context cache.

### 13.1. Listener tùy chỉnh

Trong những trường hợp chuyên biệt, có thể viết listener để đo thời gian test, chuẩn bị tài nguyên hoặc ghi dấu sự kiện:

```java
package com.example.testcontext.plain;

import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestExecutionListener;

public class TestNameListener implements TestExecutionListener {

    @Override
    public void beforeTestExecution(TestContext testContext) {
        String testName = testContext.getTestMethod().getName();
        System.out.println("Starting test method: " + testName);
    }
}
```

Nếu thực sự cần đăng ký listener này, thêm annotation sau lên **test class**:

```java
@TestExecutionListeners(
        listeners = TestNameListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
```

Đây là **mẩu annotation**, không phải class Java độc lập. `MERGE_WITH_DEFAULTS` giúp giữ các listener mặc định như dependency injection/transaction khi thêm listener tùy chỉnh. Nếu tùy ý thay cả tập listener mặc định, bạn có thể vô tình làm mất các hành vi mà test đang phụ thuộc vào.

Không nên viết listener chỉ để tăng lượng log. Test có thể được chạy song song hoặc theo thứ tự khác, và stdout của listener không phải bằng chứng về tính đúng nghiệp vụ. Khi có ích, listener cần một mục đích rõ, tránh side effect và không lệ thuộc vào thứ tự chạy.

### 13.2. Listener khác với application event listener

`TestExecutionListener` không nhất thiết là Spring bean trong `ApplicationContext`. Spring TestContext còn hỗ trợ `EventPublishingTestExecutionListener` phát **test execution events** cho bean listener, nhưng việc phát event phụ thuộc context đã được nạp và lifecycle. Không nên giả định sự kiện `BeforeTestClassEvent` luôn được gửi trên lần đầu dựng context. Đó là một API nâng cao; phần lớn test không cần tùy chỉnh những event này.

## 14. Transaction và rollback trong Spring TestContext

Một ưu điểm của integration test với Spring là khả năng chạy test trong **test-managed transaction**. Nếu method/class có `@Transactional`, có `PlatformTransactionManager` thích hợp và TestContext listener tương ứng đang hoạt động, framework thường tạo transaction và **rollback sau test** theo mặc định.

Đoạn sau **chỉ minh họa annotation**, cần repository/transaction manager và database được cấu hình thật:

```java
@SpringBootTest
@Transactional
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrderInTransactionalTest() {
        repository.save(new OrderEntity("ORDER-1"));
        assertEquals(1, repository.count());
    }
}
```

Đoạn này không phải file biên dịch độc lập vì `OrderRepository` và `OrderEntity` chưa được khai báo; không đưa vào nhóm ví dụ runnable ở mục 18. Nó minh họa ý nghĩa của `@Transactional` trong test.

Các giới hạn cần nhớ:

1. **Rollback mặc định** chỉ áp dụng cho transaction được TestContext quản lý phù hợp. Không phải mọi side effect đều nằm trong cùng transaction: HTTP server, message broker, file và remote API không tự rollback.
2. Với `@SpringBootTest(webEnvironment=RANDOM_PORT)` hoặc `DEFINED_PORT`, HTTP client và server thường chạy trên **thread/transaction khác nhau**. Rollback transaction của test client không tự rollback transaction do request bên server tạo.
3. `@BeforeEach` và `@AfterEach` thường chạy trong test-managed transaction của method có `@Transactional`, trong khi lifecycle `@BeforeAll`/`@AfterAll` không nằm trong transaction đó.
4. Có `@BeforeTransaction` và `@AfterTransaction` để chạy kiểm chứng trước khi transaction test mở hoặc sau khi nó kết thúc.
5. Transaction gắn với thread. **Preemptive timeout** như `assertTimeoutPreemptively` có thể chạy code ở thread khác, khiến code đó không tham gia test-managed transaction và không được rollback như mong đợi.
6. Rollback giúp giữ dữ liệu test sạch, nhưng một test **chỉ rollback** không chứng minh được transaction business trong production được commit/rollback đúng ở mọi ranh giới. Nếu cần kiểm tra hành vi commit thực, thiết kế integration test chuyên biệt và cleanup dữ liệu phù hợp.

**Đừng lạm dụng `@Transactional` để chữa lỗi dữ liệu không cô lập.** Hãy hiểu ranh giới transaction, sequence/id tự tăng, async worker, cache và tài nguyên ngoài; những thứ đó có thể tồn tại ngoài rollback.

## 15. Các kiểu test khác nhau vẫn dùng chung TestContext

Một điểm quan trọng: `SpringExtension` không bắt mọi test phải dùng full application context. **Loại context và bean được nạp phụ thuộc annotation/configuration**.

| Kiểu test | Cấu hình tiêu biểu | Điều kiểm chứng |
|---|---|---|
| Spring thuần | `@SpringJUnitConfig(TestConfig.class)` | Bean/configuration tập trung, dependency injection |
| Full Spring Boot | `@SpringBootTest` | SpringApplication, auto-configuration, wiring/tích hợp |
| MVC slice | `@WebMvcTest(Controller.class)` | Controller, mapping, binding, JSON, MVC/security theo slice |
| JPA slice | `@DataJpaTest` | Repository, mapping JPA, query/constraint trên DB test phù hợp |
| Runtime HTTP thật | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Request tới embedded server và các thành phần thật |
| Web Spring context không dùng Boot | `@SpringJUnitWebConfig(WebConfig.class)` | WebApplicationContext theo Spring TestContext |

Ví dụ, `@WebMvcTest` và `@DataJpaTest` thường có cấu hình bootstrap/auto-configuration riêng. Chúng vẫn hưởng lợi từ SpringExtension và context management, nhưng không tự nhiên chứa tất cả bean của ứng dụng. Khi bean dependency thiếu trong slice, hãy cân nhắc mock collaborator/import cấu hình cần thiết hoặc nâng cấp độ tích hợp nếu mục tiêu test thật sự cần.

**Không chồng nhiều slice annotation lên cùng một test** chỉ vì muốn “gộp” MVC và JPA; hãy chọn một slice hoặc full integration test theo hành vi phải kiểm chứng.

## 16. Lỗi thường gặp khi sử dụng SpringExtension và TestContext

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Field `@Autowired` vẫn `null` trong JUnit test | Chưa đăng ký SpringExtension hoặc test instance được tự tạo bằng `new` bên ngoài lifecycle JUnit | Dùng `@SpringJUnitConfig`, `@ExtendWith(SpringExtension.class)` hay annotation Boot phù hợp; để JUnit quản lý test |
| `NoSuchBeanDefinitionException` | Bean không nằm trong test context, profile không hợp lệ hoặc slice loại bean đó | Kiểm tra `@ContextConfiguration`, `@Import`, component scan, profile và loại slice |
| `Unable to find a @SpringBootConfiguration` | Boot không tìm thấy application root từ package test | Đặt test dưới package hợp lệ hoặc khai báo `classes=...` tường minh |
| Test nạp DB/remote thật khi chỉ cần unit logic | Dùng `@SpringBootTest` quá rộng hoặc production bean chưa được cô lập | Dùng JUnit thuần, Spring config nhỏ hoặc slice phù hợp |
| Suite Spring chạy rất chậm | Quá nhiều context key khác nhau, fork JVM, `@DirtiesContext` quá thường xuyên | Xem thống kê cache, gom cấu hình tương đương, giảm context loading thừa |
| Test không rollback sau HTTP thật | Request và test method ở thread/transaction khác nhau | Thiết kế cleanup/test data isolation phía server; không dựa vào rollback của client |
| Test transaction không rollback khi dùng timeout | Preemptive timeout đưa code sang thread khác | Tránh preemptive timeout với test-managed transaction |
| Test bị fail sau khi thay `@TestExecutionListeners` | Ghi đè bộ listener mặc định và làm mất DI/transaction hooks | Dùng `MERGE_WITH_DEFAULTS` khi thêm listener |
| Spring bean bị inject khác kỳ vọng | Trùng bean, `@Primary`, `@Qualifier` hoặc profile/test property không đúng | Kiểm tra bean type/name, qualifier và cấu hình đang active |
| Test chạy độc lập pass nhưng chạy suite fail | Trạng thái singleton/static/DB/cache chia sẻ hoặc tùy thuộc thứ tự | Cô lập fixture, reset trạng thái, tránh side effect và dùng `@DirtiesContext` chỉ khi cần |
| Mockito `@Mock` không tự thay bean trong context | Mockito mock field và Spring bean là hai phạm vi khác nhau | Dùng cơ chế bean override/mocking đúng phiên bản Boot/Spring khi mục tiêu thực sự cần |
| Thêm `@ExtendWith` cho `@SpringBootTest` mà vẫn lỗi | Extension đã được tích hợp; lỗi nằm ở context/bean/configuration hoặc test logic | Đọc root cause `ApplicationContext`, dependency/auto-configuration và stack trace |

**Khi context không khởi động:** hãy tìm **root cause đầu tiên** trong chuỗi `Caused by`. Các exception cuối như `Failed to load ApplicationContext` chỉ mô tả kết quả, không chỉ ra bean hoặc property gây lỗi. Nếu test có `@ActiveProfiles("test")`, kiểm tra chính profile và bean điều kiện đã kích hoạt.

## 17. Quy trình lựa chọn và đánh giá test

Một cách làm thực dụng khi thêm bài kiểm thử Spring Boot:

1. **Nêu rõ hành vi cần bảo vệ.** Ví dụ “API trả 400 khi đầu vào sai”, “bean nhận cấu hình theo profile test”, “đơn hàng rollback khi xử lý thất bại”.
2. **Xác định ranh giới quan sát.** Nếu chỉ là phép tính, viết unit test; nếu cần HTTP mapping, MVC slice; nếu cần JPA/transaction, test tích hợp hạ tầng cần thiết.
3. **Chọn annotation nhỏ nhất đủ mục tiêu.** `@SpringJUnitConfig` cho bean/config nhỏ; `@WebMvcTest` hoặc `@DataJpaTest` cho slice; `@SpringBootTest` khi cần Boot context rộng.
4. **Chỉ cấu hình những gì test thật sự cần.** Dùng `classes`, `@Import`, property/profile khi có lý do; tránh biến mỗi test thành một context riêng khó cache.
5. **Giữ test độc lập.** Dữ liệu, singleton mutable, DB và message không nên phụ thuộc test khác chạy trước.
6. **Assert contract, không chỉ rằng context load.** Smoke test khởi động context có mục đích riêng, nhưng các chức năng phải có assertion đầu ra/lỗi/tác dụng phụ rõ.
7. **Đọc tín hiệu thất bại đúng cấp.** Lỗi context, lỗi DI, lỗi transaction và lỗi assertion có nguyên nhân khác nhau.
8. **Theo dõi thời gian chạy và cache.** Một context nặng có thể đáng giữ nếu bảo vệ luồng quan trọng; với phép tính đơn giản thì không cần trả chi phí đó.

**Bài tập phân tích:** một team có 50 test `@SpringBootTest`, mỗi test chỉ kiểm tra method tính giá của một `@Service` không có I/O; CI chạy chậm. Hướng cải thiện hợp lý là viết phần lớn case thành unit test Java thuần, giữ lại một số integration test có mục tiêu bảo vệ Spring wiring/configuration. Việc xóa toàn bộ test khởi động context mà không còn kiểm tra bean/config quan trọng lại có thể tạo lỗ hổng mới.

## 18. Chạy hai bộ ví dụ và đọc kết quả

Các ví dụ trên dành cho **Java 17+**, Spring Boot **3.3.x**, JUnit Jupiter **5**. Nếu dự án đã quản lý dependency qua Spring Boot plugin/BOM, có thể khai báo trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` kéo các thư viện test cần thiết, bao gồm `spring-test` và JUnit Jupiter trong hệ sinh thái Boot 3.3. Không thêm dependency trùng nếu module hiện tại đã khai báo.

**Danh sách các file runnable chính:**

```text
src/main/java/com/example/testcontext/plain/GreetingService.java
src/test/java/com/example/testcontext/plain/GreetingTestConfig.java
src/test/java/com/example/testcontext/plain/GreetingSpringTest.java

src/main/java/com/example/testcontext/boot/TestContextDemoApplication.java
src/main/java/com/example/testcontext/boot/ShippingPolicy.java
src/test/java/com/example/testcontext/boot/ShippingPolicyContextTest.java
```

`TestNameListener.java` ở mục 13 là ví dụ listener tùy chọn, không bắt buộc để chạy hai bộ test. Các đoạn đánh dấu **minh họa/không độc lập** không được chép thành file Java chạy riêng.

Chạy từ thư mục có Gradle wrapper và project `test`:

```bash
./gradlew test --tests com.example.testcontext.plain.GreetingSpringTest --tests com.example.testcontext.boot.ShippingPolicyContextTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.testcontext.plain.GreetingSpringTest --tests com.example.testcontext.boot.ShippingPolicyContextTest
```

Với multi-project, thay `test` bằng task `:ten-module:test` đúng với module chứa các file; không dùng một tên module ví dụ nếu dự án thực tế không có.

**Kết quả được thiết kế:**

- `GreetingSpringTest.createsBeanFromConfigurationAndProperties` trả `"Xin chào, Mai!"`.
- `GreetingSpringTest.injectsTheSameSingletonBeanFromContext` xác nhận field và `ApplicationContext` tham chiếu cùng bean.
- `GreetingSpringTest.rejectsBlankName` bắt `IllegalArgumentException`.
- `ShippingPolicyContextTest` thấy `ShippingPolicy` được inject; với 199 thường phí 15, 200 thường phí 0, 200 giao nhanh phí 30; số âm ném `IllegalArgumentException`.
- Nếu dự án và dependency đúng, Gradle dự kiến in `BUILD SUCCESSFUL`. Đây là **kỳ vọng từ mã ví dụ**, không phải tuyên bố các test đã được chạy trên workspace cụ thể.

Vì các ví dụ dùng JUnit test và không có `System.out.println` trong các class test chính, **không có stdout nghiệp vụ cố định** cần đối chiếu. Có thể xem báo cáo Gradle trong `build/reports/tests/test/index.html` hoặc XML test results tại `build/test-results/test/` của module.

## 19. Tự kiểm tra và câu hỏi ôn tập

### Câu 1: Vì sao `@Autowired` không hoạt động trong một JUnit test thường?

Nếu test chỉ có `@Test` nhưng không có SpringExtension/Boot test annotation, Spring TestContext không tham gia để chuẩn bị instance và inject field. Cần đăng ký đúng extension và cấu hình context; hoặc không dùng Spring, tạo dependency trực tiếp bằng constructor nếu chỉ cần unit test.

### Câu 2: `SpringExtension` có phải Spring container không?

Không. SpringExtension là **JUnit Jupiter extension**. Spring container là `ApplicationContext`; `TestContextManager` và listener điều phối lifecycle/context cho test.

### Câu 3: `@SpringJUnitConfig` và `@SpringBootTest` khác nhau ra sao?

`@SpringJUnitConfig` là annotation tổng hợp của `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration`, hữu ích để dựng Spring context có phạm vi nhỏ. `@SpringBootTest` dùng cơ chế bootstrap Spring Boot (`SpringApplication`, auto-configuration, app configuration, webEnvironment khi yêu cầu) và đã tích hợp SpringExtension.

### Câu 4: Vì sao hai test cùng dùng `@SpringBootTest` vẫn có thể tốn hai lần nạp context?

Vì cache key còn phụ thuộc profile, property, class cấu hình, context customizer và các yếu tố khác. Nếu khác nhau, chúng có thể là hai context riêng; nếu `@DirtiesContext` hoặc JVM fork khác, context cũng không được chia sẻ như mong đợi.

### Câu 5: Khi nào cần `TestExecutionListener` tùy chỉnh?

Khi có yêu cầu rõ ở các điểm lifecycle mà annotation/fixture bình thường không đáp ứng. Nên hiểu và giữ listener mặc định, dùng `MERGE_WITH_DEFAULTS` khi bổ sung và tránh dùng listener để sửa dữ liệu nghiệp vụ một cách ngầm định.

### Câu 6: Có thể tin rằng mọi thay đổi DB trong `@SpringBootTest(RANDOM_PORT)` đều rollback nhờ `@Transactional` của test client không?

Không. Client test và HTTP server chạy trên thread/transaction khác nhau. Cần chiến lược dữ liệu và cleanup phù hợp ở bên server.

### Câu 7: `@DirtiesContext` có giúp mọi test độc lập tuyệt đối không?

Không. Nó điều khiển lifecycle **context cache**; không tự hoàn nguyên database ngoài, file, socket, message hoặc static state nằm ngoài context. Dùng khi context bị bẩn thật, đồng thời quản lý các tài nguyên khác riêng.

## 20. Checklist thực hành

- [ ] Tôi biết rõ **hành vi** nào cần Spring context để được kiểm tra.
- [ ] Tôi phân biệt `TestContext` (metadata/lifecycle) với `ApplicationContext` (bean container).
- [ ] Tôi biết `SpringExtension` đăng ký với JUnit Jupiter và chuyển callback sang TestContextManager.
- [ ] Với Spring thuần, tôi dùng `@SpringJUnitConfig` hoặc `@ExtendWith` + `@ContextConfiguration` rõ ràng.
- [ ] Với Spring Boot test annotation đã tích hợp extension, tôi không thêm annotation trùng không cần thiết.
- [ ] Tôi khai báo context/profile/property và bean đúng để test inject thành công.
- [ ] Tôi hiểu `@BeforeEach`, `@Test`, `@AfterEach` tương ứng các hook nào trong listener.
- [ ] Tôi không làm mất listener mặc định khi thêm listener tùy chỉnh.
- [ ] Tôi biết khi nào `@Transactional` rollback được và khi nào HTTP/async/thread tạo ranh giới khác.
- [ ] Tôi giữ cache hiệu quả, tránh tạo context khác nhau không cần và chỉ dùng `@DirtiesContext` khi có lý do.
- [ ] Tôi chọn đúng unit, Spring config, slice hoặc full Boot test, thay vì luôn bật cả ứng dụng.
- [ ] Tôi đọc root cause của lỗi context/bean và khẳng định được contract qua assertion cụ thể.

**Ghi nhớ:** Spring TestContext Framework là nền tảng quản lý ngữ cảnh và vòng đời kiểm thử Spring; `SpringExtension` là adapter để **JUnit Jupiter** sử dụng nền tảng ấy. Nắm rõ ranh giới giữa extension, TestContextManager, listener và ApplicationContext giúp bạn viết test Spring Boot chính xác, có tính cô lập và không tốn thời gian khởi động không cần thiết.

### Tài liệu tham khảo

- Spring Framework 6.2 — TestContext Framework Support Classes: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/support-classes.html
- Spring Framework — Key Abstractions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/key-abstractions.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

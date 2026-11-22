# AOT, native testing và phạm vi annotation được hỗ trợ

## 1. Vì sao test JVM xanh nhưng GraalVM native test lại đỏ?

Trong module **Spring Boot - testing**, nhóm **Phiên bản và chuyển đổi**, phần này giải thích những gì thực sự xảy ra khi chuyển từ JVM integration tests sang **Spring AOT** và **GraalVM Native Image tests**. Một bài `@SpringBootTest` chạy thành công trên JVM có thể thất bại trong bước `processTestAot`, `nativeCompile` hoặc `nativeTest`, dù cùng một business assertion.

Nguyên nhân cơ bản: trên JVM, Spring có thể quét classpath, suy luận bean graph, nạp resource và sử dụng reflection/dynamic proxies tại runtime. Với AOT (ahead-of-time), Spring **phân tích và xử lý ApplicationContext trước khi chạy**, sinh code và metadata cho GraalVM; một số quyết định về bean definitions, profiles và conditions đã được chốt từ build time. GraalVM Native Image lại có mô hình closed world, nên nhiều thao tác reflection, resource lookup, dynamic proxy, JNI, serialization và initialization cần được native compiler biết trước.

Đây không phải lỗi của `@Test` đơn thuần. Hãy phân biệt:

1. **JUnit test trên JVM**: code và Spring context chạy bình thường; không cần native image.
2. **Spring AOT processing của ứng dụng**: chuẩn bị bean graph và sinh source/metadata cho production application.
3. **Spring TestContext AOT processing**: phát hiện các test configurations, xử lý từng context cần dùng và sinh test context initializers.
4. **AOT-enabled JVM runtime**: ứng dụng có generated artifacts và dùng `-Dspring.aot.enabled=true`; vẫn chạy JVM, chưa chứng minh native compiler được đáp ứng.
5. **Native application executable**: GraalVM biên dịch chương trình chính thành binary.
6. **Native test executable**: GraalVM biên dịch JUnit engine + test classes + các Spring test contexts đã xử lý AOT thành binary để thực thi tests.

**Kết quả JVM PASS không mặc nhiên suy ra native PASS.** Ngược lại, nếu native build fail ở build-time AOT analysis, đó chưa phải một JUnit assertion thất bại. Bài học xây dựng cách phân loại annotation/test styles: nhóm được hỗ trợ trong giới hạn rõ ràng, nhóm cần runtime hints hoặc kiểm tra provider, và nhóm không được hỗ trợ trong phiên bản được xét.

Phiên bản xuyên suốt: **Java 17, Spring Boot 3.3.0, Spring Framework 6.1, JUnit Jupiter 5, Gradle 8.x và GraalVM Native Build Tools Gradle plugin 0.10.1**. Đây là **một stack lịch sử được cố định có chủ đích** để hiểu migration; các phiên bản mới có thể thay đổi đặc tính annotation/Mockito/Native Image. Ví dụ không giả định API của Spring 6.2, 7.0 hoặc Boot 4.x có sẵn trong Boot 3.3.

## 2. Kết quả học tập

Sau bài, bạn có thể:

- Phân biệt `AOT processing` với `GraalVM native-image compilation` và native test execution.
- Giải thích vai trò `processAot`, `processTestAot`, `nativeCompile` và `nativeTest`.
- Dùng `@SpringBootTest` hoặc Spring Boot test slice theo phạm vi phù hợp khi native test có hỗ trợ tương ứng.
- Hiểu JUnit Platform `TestEngine` vẫn cần thiết để thực thi các test classes trong native test image.
- Biết Spring TestContext AOT xử lý **các ApplicationContext khác nhau theo cấu hình**, không đơn giản mỗi test method một lần bootstrap.
- Phân biệt `@DisabledInAotMode` (Spring) với `@DisabledInNativeImage`/`@EnabledInNativeImage` (JUnit Jupiter).
- Biết `@ContextHierarchy` không được hỗ trợ trong Spring TestContext AOT mode của stack được xét.
- Biết `@ActiveProfiles`, `@TestPropertySource`, `@Import` và `@TestConfiguration` là cấu hình cần xem xét **tại build time**, không phải runtime hot reconfiguration.
- Hiểu `@DynamicPropertySource` có thể mang runtime-derived values, nhưng không được ngầm dùng nó để thay đổi bean graph/conditions đã được đóng ở AOT build time.
- Nhận diện rủi ro `@MockBean`/`@SpyBean` và Mockito trong native test theo toolchain/version; không tuyên bố tự động được hỗ trợ như JVM.
- Biết `@DirtiesContext`, `@Transactional`, `@Sql` có ý nghĩa khác nhau và không tự mang lại mọi native capability cho third-party libraries.
- Dùng `@RegisterReflectionForBinding` và `@ImportRuntimeHints` để cung cấp reflection/resource metadata khi Spring không tự suy luận.
- Biết custom `ContextLoader` cần tương thích `AotContextLoader` và custom `TestExecutionListener` cần tích hợp `AotTestExecutionListener` khi tham gia AOT processing.
- Kiểm tra context-specific build-time property values và profile activation.
- Viết native-friendly test dùng real service/test fake thay vì mock framework phức tạp.
- Chạy đường chuẩn JVM test trước, rồi `processTestAot`, cuối cùng `nativeTest` trên GraalVM phù hợp.
- Phân biệt compilation/runtime error với test assertion failure và “không có test được phát hiện”.
- Đảm bảo reflection/resource hints vừa đủ, không thêm cấu hình cho mọi class vô điều kiện.
- Thiết kế CI chạy JVM tests thường xuyên, native smoke/integration tests theo lịch/thay đổi phù hợp với chi phí build.
- Đánh giá đúng support matrix theo **framework + Boot + test engine + thư viện bên thứ ba + OS/GraalVM**, không chỉ dựa vào tên annotation.

## 3. Sơ đồ end-to-end AOT test

```text
                 Source code + test classes
                            |
                     Java compilation
                            |
              +-------------+---------------+
              |                             |
              v                             v
        JVM Gradle test               processTestAot
              |                             |
        Jupiter engine               Find TestContext tests
        loads Spring                 Group unique contexts
        by reflection                Analyze bean graphs
              |                     Generate initializers
              v                     Register runtime hints
        Assertions/report                     |
                                            v
                                     native-image compiler
                                            |
                                  JUnit engine + test code
                                  + generated AOT assets
                                  + reachable classes
                                            |
                                            v
                                       nativeTest
                                            |
                                  Native test executable
                                            |
                                  Assertions + test report
```

Spring Boot Gradle plugin phối hợp với GraalVM Native Build Tools để cấu hình các task tương ứng. Với native tests, quá trình tích hợp thường chạy `processAot` **và** `processTestAot` trước khi biên dịch test binary. Tự tạo một executable từ `javac` không tương đương Spring TestContext native testing.

### 3.1. AOT processing không phải native binary

`processTestAot` tạo code và metadata, nhưng nó **chưa** chạy các test assertions bên trong native executable. Nó có thể PASS ngay cả khi native compilation fail vì reflection của third-party library. Nó cũng có thể fail ngay vì test context không thể xử lý AOT.

### 3.2. Native binary không phải JVM với flag khác

GraalVM Native Image biên dịch closed-world executable. Nhiều dynamic features không sẵn có như JVM classpath scanning/reflection thông thường. Không sửa bằng cách “chuyển JDK vendor” tùy tiện; phải xác định missing hints, library compatibility, build-time properties hoặc môi trường.

### 3.3. AOT runtime trên JVM chỉ là một cột kiểm chứng

`spring.aot.enabled=true` yêu cầu có generated artifacts trong application jar hoặc runtime classpath; nó giúp phát hiện lỗi code đã sinh, nhưng không chứng minh native-image reflection/resource/proxy metadata đã hoàn chỉnh. Mặc định JVM không dùng generated AOT assets khi không bật flag đó.

## 4. Version boundary: Spring Boot 3.3, Spring Framework 6.1 và JUnit

| Thành phần | Stack bài này | Ý nghĩa |
| --- | --- | --- |
| JDK source/bytecode | Java 17 | API & ngôn ngữ |
| Spring Boot | 3.3.0 | Boot test, auto-configuration, Gradle AOT |
| Spring Framework | 6.1.x do Boot BOM quản lý | TestContext AOT, `@DisabledInAotMode` |
| JUnit | Jupiter 5.x do Boot BOM quản lý | Test methods, native-image conditions |
| Gradle | 8.x, ví dụ 8.7 | `test`, `nativeTest` build integration |
| GraalVM Native Build Tools | Gradle plugin 0.10.1 | Native compiler tasks |
| GraalVM JDK | Một bản GraalVM có `native-image` và tương thích Java target | Biên dịch/run native |
| Spring Native đời cũ | **Không dùng** | Không pha trộn cấu hình Boot 2.x/experimental APIs |

**Không hardcode phiên bản thư viện JUnit lệch với Boot BOM** khi không có lý do rõ; native build rất nhạy với runtime engine/platform versions. Kiểm tra dependency resolution thực nếu có lỗi `NoClassDefFoundError` hoặc không phát hiện TestEngine.

### 4.1. Không copy ví dụ Boot 4.x vào Boot 3.3

Spring Boot 3.4+ chuyển dần khỏi `@MockBean`/`@SpyBean` và Spring Framework 6.2+ có `@MockitoBean`/`@MockitoSpyBean`; Spring Framework 7.x có các thay đổi hỗ trợ AOT/JPA khác. Bài này không giả vờ các API sau đó có sẵn trong Boot 3.3. Nếu nâng version, cần đối chiếu lại toàn bộ annotation matrix.

### 4.2. GraalVM phải có native-image

Kiểm tra bằng:

```bash
java -version
native-image --version
./gradlew --version
```

`java -version` hiển thị một bản JDK không có nghĩa executable `native-image` được cài. Tùy GraalVM distribution, compiler có thể đi kèm hoặc cần cài thêm; phải đối chiếu phiên bản Java target và GraalVM Native Build Tools. Native compilation cũng cần toolchain hệ điều hành (C/C++ linker/libraries) theo hướng dẫn GraalVM.

## 5. Những gì Spring TestContext AOT thực sự làm

Spring TestContext Framework có AOT support cho các integration tests tải `ApplicationContext`. Khi build:

1. Phát hiện các test classes/suite liên quan dựa trên test classpath và JUnit Platform engines đã đăng ký.
2. Tính cấu hình contexts cần cho những test classes đó.
3. Dùng Spring AOT engine để xử lý từng **unique ApplicationContext** dự kiến.
4. Sinh code `ApplicationContextInitializer`, bean registration logic và metadata/hints.
5. Ghi mapping test class ↔ generated context initializer.
6. GraalVM Native Build Tools sử dụng assets này khi build native test executable.
7. Lúc chạy native, Spring TestContext dùng context đã AOT-process và vẫn tham gia context cache.

Không phải toàn bộ annotations được “đọc lại tùy ý ở runtime như JVM”. Bean graph được sinh trong bối cảnh build-time; code thay đổi bean definitions theo profile/conditional runtime có thể trái với giả định AOT.

### 5.1. Cache key vẫn tồn tại

Hai test classes có cấu hình tương đương có thể chia sẻ context được sinh và context cache trong native test runtime. Vì vậy mutable singleton state vẫn có thể rò giữa methods/classes; AOT **không** tự tạo một context sạch cho mỗi method.

### 5.2. Nhiều test profiles có thể sinh nhiều contexts

`@ActiveProfiles("test")` và `@ActiveProfiles("integration")` có thể dẫn tới hai distinct test contexts/AOT generated initializers. Tăng số context có thể làm native build nặng và thời gian AOT kéo dài. Không gộp tất cả contexts bừa bãi nếu điều đó làm sai test fidelity.

### 5.3. Lỗi AOT build time có thể khác runtime

Ví dụ một `@Configuration` bean cần giá trị profile/property mà chỉ được cung cấp **khi chạy native test**, nhưng AOT processor đã phải quyết định sự có mặt của bean **trước đó**. Kết quả có thể fail build hoặc tạo bean graph khác kỳ vọng. Cần cấu hình môi trường build-time AOT cho nhất quán, không chỉ đặt runtime system property.

## 6. Bảng annotation support: câu trả lời ngắn

Phải phân biệt **“Spring TestContext nhận annotation”** với **“mọi thư viện/behavior được GraalVM native chạy được”**. Bảng dưới dùng Spring Boot 3.3 / Spring Framework 6.1:

| Annotation / tính năng | Phân loại | Điều cần kiểm chứng |
| --- | --- | --- |
| `@SpringBootTest` | **Hỗ trợ AOT/native tests** | App bean graph và dependencies native-compatible |
| `@WebMvcTest`, `@DataJpaTest`, các Boot test slices | **Được Boot hỗ trợ theo mô hình slice** | Hints cho controller/serializer/JPA/provider và scope beans |
| JUnit Jupiter `@Test`, `@ParameterizedTest`, `@Nested` | **JUnit engine hỗ trợ** | Engine discovery, params/resources và native build plugin |
| `@ContextConfiguration`, `@Import`, `@TestConfiguration` | **Hỗ trợ theo static configuration** | Custom loader và graph có thể AOT-process |
| `@ActiveProfiles`, `@TestPropertySource` | **Có hỗ trợ, chốt logic bean graph ở build time** | Build-time profile/property selection |
| `@DynamicPropertySource` | **Có cơ chế hỗ trợ nhưng cần xét timing** | Dynamic endpoint, container lifecycle, conditions/bean graph |
| `@Autowired` / `@Resource` vào test class | **Dùng được theo version constraints** | Loại bean, lifecycle và native hints |
| `@Transactional`, `@Sql` | **Được dùng trong TestContext theo điều kiện** | Transaction manager, schema/resources, runtime hints |
| `@DirtiesContext` | **Có semantics TestContext** | Native context reload/overhead, external data cleanup |
| `@RegisterReflectionForBinding`, `@ImportRuntimeHints` | **Cơ chế cấp AOT hints** | Reflection/resources/proxies được mô tả đủ |
| `@DisabledInAotMode` | **Đúng annotation Spring 6.1** | Class/method scope và shared context rule |
| `@DisabledInNativeImage` / `@EnabledInNativeImage` | **JUnit native runtime condition** | Chỉ điều kiện trong native executable |
| `@ContextHierarchy` | **Không được hỗ trợ trong TestContext AOT mode** | Phải thiết kế lại context composition |
| `@MockBean` / `@SpyBean` của Boot 3.3 | **Thận trọng: Mockito/native limitations** | Không mặc định giả định hoạt động; test/fake strategy |
| Test class `@PersistenceContext` / `@PersistenceUnit` injection | **Đòi hỏi kiểm tra AOT version; tránh dựa vào trong 6.1 native test** | Ưu tiên inject Spring repository/service qua `@Autowired` |
| Custom `ContextLoader` | **Có điều kiện** | Phải thực hiện `AotContextLoader` nếu muốn AOT processing |
| Custom `TestExecutionListener` | **Có điều kiện** | `AotTestExecutionListener` khi cần tham gia processing |
| JUnit 4 tests | **Platform/engine tùy cấu hình** | Vintage engine/runtime, native compatibility; không chỉ `@RunWith` |
| TestNG và engines khác | **Phụ thuộc engine/toolchain thực** | Phải có JUnit Platform TestEngine được đăng ký cho native build |

Chữ “hỗ trợ” trong bảng **không phải lời hứa mọi tổ hợp Boot starter, database, mocks, Testcontainers, tracing agent và plugin đều chạy được**. Với native tests, chính integration test trên binary là bằng chứng cuối cùng.

## 7. @SpringBootTest trong native tests

Một test dạng:

```java
@SpringBootTest(
        classes = AotLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AotIntegrationTest {
    @Autowired GreetingService greetings;

    @Test
    void contextLoadsAndGreetWorks() {
        assertEquals(
                "Hello, Ada",
                greetings.greet("Ada"));
    }
}
```

Đây là snippet rút gọn; bản runnable đầy đủ ở chương 19. Spring Boot/Spring Framework cho phép `@SpringBootTest` được đưa qua TestContext AOT processing. Khi native executable chạy, test method vẫn được JUnit Jupiter thực thi, còn ApplicationContext dùng generated initialization assets.

**Điều này không có nghĩa** mọi bean của ứng dụng đều native-compatible: một SDK dùng reflection tùy ý, classpath scanner động, JNI hoặc resources thiếu hints vẫn có thể làm native image fail.

### 7.1. Test slices

`@WebMvcTest`, `@DataJpaTest`, `@JsonTest` hoặc các slices khác giảm beans cần load. Native image testing có thể dùng test slices, nhưng từng slice vẫn cần dependencies và hints phù hợp. Ví dụ:

- `@WebMvcTest` với Jackson/validation/security phải kiểm tra controller request/response types và filters.
- `@DataJpaTest` cần native-compatible ORM/database driver, entity metadata và JPA behavior.
- `@JsonTest` cần serializers/deserializers/record binding hints khi engine không tự suy ra.
- Một slice không tự mở full embedded server; native test task không làm thay đổi phạm vi của annotation.

**Không kết hợp hai test slices tùy tiện**. Nếu cần full integration dùng `@SpringBootTest`; nếu cần partial context thì giữ đúng slice contract.

## 8. @ContextConfiguration, @TestConfiguration và @Import

Khi context composition là static/deterministic, Spring AOT có thể phân tích ở build time:

```java
@TestConfiguration(proxyBeanMethods = false)
class TestClockConfig {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-11-08T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

Đây là snippet minh họa, cần imports. `@Import(TestClockConfig.class)` trên test giúp AOT processor thấy bean definition của test config.

Một sai lầm là **đăng ký/loại beans ở runtime sau khi AOT generated code đã tạo bean graph** rồi mong Spring chạy lại classpath scanning/conditions như JVM. Với AOT, chọn bean graph cần thống nhất ở build time.

### 8.1. @ContextConfiguration custom loader

Nếu dự án dùng `@ContextConfiguration(loader=SomeLoader.class)` với custom loader, loader không chỉ được yêu cầu chạy JVM tests. Để tham gia AOT processing, custom loader phải tương thích `AotContextLoader`. Loader mặc định do Spring Framework/Spring Boot cung cấp đã tích hợp tương ứng; loader viết riêng thì phải xem lại SPI.

### 8.2. ApplicationContextInitializer

`ApplicationContextInitializer` giúp thay đổi context trước refresh. Nhưng một initializer runtime không được dùng để làm phát sinh tùy tiện beans/definitions chưa được AOT xử lý. Khi cần custom AOT contributions, dùng Spring AOT extension/hint registration chứ không trông cậy một runtime scan ngẫu nhiên.

### 8.3. TestExecutionListener

Spring TestContext `@TestExecutionListeners` vẫn là cơ chế test lifecycle. Một listener custom cần chạy ở AOT build time phải tích hợp `AotTestExecutionListener`. Nếu không, listener có thể vẫn tồn tại như runtime test listener ở mức phù hợp, nhưng không được giả định nó tự đóng góp AOT hints/registration.

## 9. @ActiveProfiles, @TestPropertySource và lựa chọn bean graph

Xét:

```java
@Profile("test")
@Configuration
class TestOnlyBeans {
    @Bean
    PaymentClient paymentClient() {
        return new FakePaymentClient();
    }
}
```

Đây là snippet minh họa; interfaces/classes chưa được khai báo. Với Spring AOT, sự có mặt của `TestOnlyBeans` được quyết định theo profile/conditions khi build-time AOT processing. Nếu build image dưới profile "test" rồi runtime chuyển sang "production" để thay toàn bộ bean graph, kết quả không tương đương JVM dynamic configuration.

### 9.1. Profiles không được coi là runtime feature toggle cho bean definitions

Ghi rõ:

- `@ActiveProfiles("native-test")` trên test class giúp AOT processor biết context configuration của test.
- `@TestPropertySource(properties="feature.useMock=true")` có thể ảnh hưởng bean definition conditions tại build time.
- Thay `feature.useMock` lúc native test executable đã biên dịch **không buộc AOT sinh lại graph**.
- Các runtime properties dùng như **giá trị** cho existing beans có thể vẫn động tùy cơ chế; nhưng properties thay **sự tồn tại của beans** cần xử lý ở build-time.

### 9.2. Đừng bịa rằng mọi property đều đóng băng

AOT không có nghĩa mọi `Environment.getProperty(...)` là compile-time constant. Cần phân biệt property được dùng để đánh giá `@Conditional`/`@Profile`/BeanFactory conditions với property được existing bean đọc lúc runtime. Test từng trường hợp theo wiring/code thực.

### 9.3. Những nguồn cấu hình dễ bất đồng

- Gradle daemon JVM khác Gradle test JVM.
- `processTestAot` là build-time JavaExec task, có môi trường/system properties riêng.
- Native test executable có runtime process environment riêng.
- Docker/CI secrets được inject khi runtime, không có ở AOT build-time.
- `application-test.yml` được có mặt trong classpath nhưng không được active profile như bạn nghĩ.
- Testcontainers dynamic mapped ports chỉ biết khi container start runtime.

Hãy ghi logs đã sanitize cho build-time profile/property keys và runtime env; không in credentials.

## 10. @DynamicPropertySource, Testcontainers và native AOT

`@DynamicPropertySource` là API Spring TestContext để đăng ký dynamic suppliers (thường cho host/port của Testcontainers). Ví dụ:

```java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("service.endpoint",
            container::getServiceEndpoint);
}
```

**Đây là snippet minh họa**, biến `container`/method chưa được khai báo. Nó **không** có nghĩa Spring chắc chắn biết mapped port từ build time.

Với AOT, cần xác định:

1. Dynamic value là **endpoint/credential của existing bean** hay dùng để quyết định bean definitions?
2. Testcontainers được start ở build-time analysis hay chỉ runtime native test?
3. Context được cache hay reuse trong khi container cũ đã stop?
4. Runtime hints cho driver/SDK/serialization có đủ chưa?
5. Test binary/native image có khả năng giao tiếp Docker network/host architecture không?

### 10.1. Không đánh đồng dynamic value và dynamic bean graph

Nếu BeanFactory condition dùng giá trị chỉ xuất hiện runtime để chọn một class, AOT có thể đã xử lý một graph khác. Tránh thiết kế native tests phải thay bean definitions theo mapped port; dùng stable bean types và inject endpoint values đúng phase nếu framework/library hỗ trợ.

### 10.2. @ServiceConnection

Spring Boot Testcontainers integration có `@ServiceConnection` giúp cung cấp connection details từ container. Nhưng nó không làm mọi third-party driver native-compatible và không tự giải quyết Docker availability trên nativeTest CI. Cần dependencies và runtime hooks phù hợp Boot3.3.

### 10.3. Không dùng @DirtiesContext như thuốc chữa phổ quát

`@DirtiesContext` có thể buộc Spring context reload ở test runtime, nhưng nó không thay đổi AOT-generated bean graph hoặc tạo thêm native metadata đã thiếu. Nó cũng không đảm bảo dọn database external, topic hay Redis keys. Chỉ dùng khi state context thật sự không thể reset; validate với native toolchain.

## 11. @DisabledInAotMode: cơ chế Spring 6.1

`@DisabledInAotMode` ở package:

```java
import org.springframework.test.context.aot.DisabledInAotMode;
```

Nó báo cho TestContext biết annotation test class **không nên được AOT-process**; khi dùng JUnit Jupiter, test class/method tương ứng sẽ bị disable trong Spring AOT runtime mode.

Ví dụ method-level:

```java
@Test
@DisabledInAotMode
void requiresOrdinaryJvmSpringMode() {
    assertFalse(
            AotDetector.useGeneratedArtifacts());
}
```

Đây là snippet minh họa; runnable example ở chương 19 có imports đầy đủ. Nó **chạy trên JVM thông thường**, nhưng bị skip khi Spring AOT generated artifacts được dùng. Với method-level, context chứa method vẫn có thể được AOT-process vì các method khác trong class cần nó.

### 11.1. Class-level có ảnh hưởng build-time

```java
@DisabledInAotMode
@SpringBootTest
class LegacyJvmOnlyIntegrationTest {
    @Test
    void usesUnsupportedRuntimeFeature() {
        // JVM-only coverage.
    }
}
```

Đây là snippet. Spring TestContext không tạo AOT optimization cho context test class này. **Điều kiện rất quan trọng:** nếu một test class khác dùng **cùng ApplicationContext configuration**, tất cả classes có chung context đó cũng phải được đánh dấu `@DisabledInAotMode`; nếu không có thể ném exception ở build/runtime. Không chỉ đánh dấu ngẫu nhiên một class trong group rồi bỏ qua others.

### 11.2. Không tắt toàn bộ native suite để build xanh

Native testing nhằm phát hiện incompatibilities. Dùng `@DisabledInAotMode` **có lý do và phạm vi nhỏ**, ghi rõ coverage gap/case cần migration, và giữ test JVM. Nếu phần quan trọng như security/serialization/database chỉ có JVM tests bị skip native, phải có native-safe replacement tests.

### 11.3. Method-level khác class-level

- Method-level: bỏ method trong Spring AOT run, các methods còn lại trong class có thể vẫn được xử lý/chạy.
- Class-level: bỏ cả test class và không AOT-process context riêng của class đó.
- Với **shared context configuration**, áp dụng class-level phải nhất quán cho tất cả classes tham gia cùng context.

## 12. @DisabledInNativeImage và @EnabledInNativeImage là điều kiện JUnit

JUnit Jupiter cung cấp:

```java
import org.junit.jupiter.api.condition.DisabledInNativeImage;
import org.junit.jupiter.api.condition.EnabledInNativeImage;
```

Ví dụ:

```java
@Test
@DisabledInNativeImage
void usesOnlyJvmInstrumentation() {
    // Runs on an ordinary JVM, not native executable.
}

@Test
@EnabledInNativeImage
void onlyVerifyNativeBehavior() {
    // Runs only within a GraalVM native image.
}
```

**Khác biệt cốt lõi:** các annotations này là **JUnit native runtime conditions**, không phải chỉ dẫn Spring TestContext loại một ApplicationContext khỏi build-time AOT processing. Đối với Spring context không thể AOT-process, gắn `@DisabledInNativeImage` vào một test method chưa chắc tránh được lỗi `processTestAot`. Dùng `@DisabledInAotMode` khi cần điều khiển AOT processing.

### 12.1. Bảng so sánh

| Annotation | JVM thông thường | JVM có Spring AOT artifacts | GraalVM native test | Loại context khỏi build-time AOT? |
| --- | --- | --- | --- | --- |
| Không annotation skip | Có | Có | Có, nếu tương thích | Không |
| `@DisabledInAotMode` method | Có | Skip method | Skip method | Không loại toàn context |
| `@DisabledInAotMode` class | Có | Skip class | Skip class | **Có**, với shared-context rule |
| `@DisabledInNativeImage` | Có | Có, nếu vẫn là JVM | Skip | **Không** |
| `@EnabledInNativeImage` | Skip | Skip nếu JVM | Có | **Không** |

Khi muốn chỉ test Java behavior trên JVM, method-level có thể đủ. Khi muốn tránh Spring AOT processing một context không tương thích, annotation **class-level** của Spring và shared-context consistency mới quan trọng.

### 12.2. @Disabled không sửa lỗi generated code

Một native image không compile được vì reachability/hint lỗi của production bean, đánh dấu JUnit method `@Disabled` không làm Spring đột nhiên có runtime hints cho bean khác. Hãy sửa nguyên nhân build. Không dùng tests skipped như evidence đạt native coverage.

## 13. @ContextHierarchy: giới hạn chính thức

Spring Framework TestContext AOT **không hỗ trợ `@ContextHierarchy`** trong phiên bản được xét. Đây là giới hạn cụ thể, không phải “có thể work khi thêm @Import”. Một test phụ thuộc parent-child ApplicationContext hierarchy có thể chạy trên JVM nhưng không đủ điều kiện AOT/native tests.

Ví dụ **không đặt trong project runnable**:

```java
@ContextHierarchy({
    @ContextConfiguration(classes = ParentConfig.class),
    @ContextConfiguration(classes = ChildConfig.class)
})
class LegacyHierarchyTest {
    // ...
}
```

Cách xử lý:

1. Giữ test này trên JVM; đánh dấu class-level `@DisabledInAotMode` nếu nó đang phá quá trình xử lý AOT.
2. Thiết kế một **flat test context** cho behavior cần native coverage với `@Import`/`@ContextConfiguration` có chủ đích.
3. Nếu production cần hierarchy, test JVM vẫn giữ để bảo vệ behavior; native smoke/integration có thể test một ApplicationContext tương thích khác.
4. Không lặng lẽ xóa parent context mà không kiểm tra injection/bean override/security behavior.
5. Không hứa thay `@ContextHierarchy` bằng một annotation khác là semantic equivalent.

## 14. Mockito @MockBean/@SpyBean: cẩn thận với native

Trong Spring Boot **3.3**, `@MockBean`/`@SpyBean` thuộc test support của Boot và dựa vào Mockito. Trên JVM chúng được dùng rộng rãi; nhưng việc tạo mocks/spies có thể cần dynamic proxies, bytecode generation và inline mocking không giống Native Image. Spring Boot GraalVM guidance nêu **Mockito/native test limitations**. Vì vậy không nên lập bảng “@MockBean supported trong mọi native tests” khi chưa kiểm chứng đúng version/provider.

### 14.1. Ví dụ test native-friendly

Thay vì dựa vào mock framework để tạo dynamic implementation, có thể định nghĩa một **test fake bean** theo static type:

```java
public interface PriceGateway {
    int price(String sku);
}

public final class FixedPriceGateway
        implements PriceGateway {

    @Override
    public int price(String sku) {
        return 50;
    }
}

@TestConfiguration(proxyBeanMethods = false)
class FakeGatewayConfig {
    @Bean
    @Primary
    PriceGateway fakePriceGateway() {
        return new FixedPriceGateway();
    }
}
```

Đây là **design snippet**, không thuộc lab runnable; production cần đầy đủ interface/gateway beans để quyết định override. Static test fake có thể dễ AOT-process hơn bytecode-generated Mockito mock, nhưng phải đảm bảo không làm sai test mục tiêu.

### 14.2. Không xóa Mockito tests khỏi JVM regression suite

Những tests dựa mocks vẫn có giá trị trên JVM. Tách native smoke tests cho paths cần chứng minh native compatibility; test JVM vẫn giữ unit-level interaction behavior. Native PASS không cần đồng nghĩa chạy lại 100% Mockito-heavy tests nếu toolchain chưa hỗ trợ.

### 14.3. Chú ý khi nâng lên Boot mới

Spring Framework 6.2+ có `@MockitoBean`/`@MockitoSpyBean` và Boot 3.4+ deprecates legacy `@MockBean`. Chúng **không có sẵn trong Boot3.3**. Không copy một snippet annotation chưa tồn tại rồi gọi compiler failure là lỗi AOT.

## 15. @Autowired, JPA injection và test-only dependencies

Spring TestContext native tests có hỗ trợ injection của Spring-managed beans theo AOT generated context. Cách ít phụ thuộc internals nhất là inject service/repository:

```java
@SpringBootTest
class RepositoryBehaviorTest {
    @Autowired OrderRepository orders;

    @Test
    void savesOrder() {
        // Exercise repository through Spring.
    }
}
```

Snippet này chưa runnable vì `OrderRepository` chưa khai báo. Với JPA, kiểm tra Spring Framework version hỗ trợ injection annotation nào ngay trên **test instance**. Đặc biệt không giả định `@PersistenceContext`/`@PersistenceUnit` trên test fields hoạt động y hệt AOT mode của Framework 6.1; một số cải tiến đã xuất hiện ở Framework 7.x.

**Điểm cần tránh:** nói “JPA không hoạt động với native tests” là sai. Giới hạn injection annotation trên test instance không đồng nghĩa toàn bộ Hibernate/JPA provider không thể compile thành native image. Cần đọc provider/version và test bằng repository/entity manager pathways phù hợp.

### 15.1. @Transactional

`@Transactional` trong test-managed transaction giữ semantics Spring TestContext khi được hỗ trợ, thường rollback khi test kết thúc. Trong native tests, transaction manager, datasource, DB driver và database external vẫn phải hoạt động; AOT không tạo transaction manager thiếu.

### 15.2. @Sql

`@Sql` có thể chạy SQL setup/cleanup từ test classpath, nhưng native resource inclusion phải được bảo đảm; nếu script không có trong native executable, test sẽ fail dù SQL đúng. Nếu cần, đăng ký resource hints. Đừng dùng `@Sql` để sửa bean graph đã được AOT generate hoặc để tự động reset external database không thuộc scope.

### 15.3. @DirtiesContext

`@DirtiesContext` làm Spring TestContext close/evict context tại runtime, không reset external databases. Native test executable vẫn có AOT-generated context; “load lại context” không bằng “quét lại mọi class/bean condition như JVM dynamic startup”.

## 16. Runtime hints: reflection, resource, proxy, serialization

GraalVM closed-world analysis cần biết trước những thao tác dynamic không suy luận được. Spring AOT sinh nhiều hints tự động từ bean definitions, configuration properties và Spring infrastructure, nhưng không bảo đảm nhận diện thư viện custom.

Các loại thường gặp:

| Loại hint | Triệu chứng khi thiếu | Hướng sửa |
| --- | --- | --- |
| Reflection | Constructor/method/record binding không truy cập được | `@RegisterReflectionForBinding` hoặc `RuntimeHintsRegistrar` |
| Classpath resource | `getResourceAsStream` trả null | `resources().registerPattern(...)` |
| JDK dynamic proxy | Interface proxy không tạo được | `RuntimeHints.proxies()`/framework hints |
| Serialization | DTO/serializer cần metadata runtime | Binding/serialization hints phù hợp |
| JNI | Native library/call không được support | Native Image JNI metadata/provider |
| Resource bundle | i18n/messages missing | Bundle hints |
| Third-party driver | SDK khởi tạo lỗi | Native reachability metadata, version upgrade, library-specific hints |

**Đừng bật reflection cho cả classpath** chỉ để làm một test xanh. Hints quá rộng tăng binary size/attack surface và làm khó bảo trì. Đăng ký đúng classes, constructors, fields, resources theo path cần dùng.

### 16.1. @RegisterReflectionForBinding

Spring Framework hỗ trợ:

```java
@RegisterReflectionForBinding(TicketPayload.class)
class AotIntegrationTest {
    // ...
}
```

Annotation của Spring mang runtime reflection hints cho constructors, properties, records và related binding types. Nó phù hợp khi test dùng Jackson/data binding trên một DTO không được Spring AOT tự infer.

### 16.2. @ImportRuntimeHints

```java
@ImportRuntimeHints(TestResourceHints.class)
class AotIntegrationTest {
    // ...
}
```

`TestResourceHints` implements `RuntimeHintsRegistrar`, có thể đăng ký resources trong `src/test/resources`. Khác với JAXB/Jackson annotations chỉ khai báo DTO, cách này phù hợp với một resource path hoặc reflection/proxy type không tự suy ra.

### 16.3. RuntimeHintsRegistrar vs TestRuntimeHintsRegistrar

- `RuntimeHintsRegistrar` của Spring Core có thể đăng ký hints cho một component/context, dùng `@ImportRuntimeHints`.
- `TestRuntimeHintsRegistrar` của Spring TestContext dành cho global hints đặc thù test infrastructure, đăng ký qua `META-INF/spring/aot.factories`.
- Nếu hints dùng lại được giữa production/tests, ưu tiên Core `RuntimeHintsRegistrar` thay vì global test-only SPI.
- Không viết custom registrar nếu Spring AOT đã tự suy ra chính xác; duplicate hints không làm test chắc chắn hơn.

### 16.4. Hints không tương đương executable coverage

`processTestAot` hoặc việc register một type có thể PASS, nhưng test native runtime vẫn fail bởi resource missing, driver native unsupported hoặc business assertion. Phải chạy `nativeTest` và kiểm tra reports thật.

## 17. Thiết kế ví dụ thực hành

Dự án gồm:

- `AotLabApplication`: Boot application đơn giản.
- `GreetingProperties`: record `@ConfigurationProperties(prefix="demo")`, cho thấy binding được AOT nhìn thấy.
- `GreetingService`: business logic thuần Java được inject configuration.
- `TicketPayload`: Java record dùng JSON binding trong integration test.
- `TestResourceHints`: registrar đăng ký một test-only resource.
- `AotIntegrationTest`: `@SpringBootTest` + `@ActiveProfiles` + `@TestPropertySource` + runtime hints + annotation skip.
- `GreetingUnitTest`: hai pure JUnit tests không khởi tạo Spring context.
- `src/test/resources/samples/native-proof.txt`: test resource trong native executable.

Lab tránh Mockito, JPA, database, Docker, HTTP server và `@ContextHierarchy` để tập trung vào **AOT processing vs annotation support**. Từng thành phần có một bằng chứng rõ. Nếu muốn mở rộng sang database/HTTP, làm sau khi baseline `nativeTest` pass trên toolchain.

### 17.1. Cây thư mục

```text
spring-aot-test-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/aot/
    │   ├── AotLabApplication.java
    │   ├── GreetingProperties.java
    │   └── GreetingService.java
    └── test/
        ├── java/example/aot/
        │   ├── TicketPayload.java
        │   ├── TestResourceHints.java
        │   ├── AotIntegrationTest.java
        │   └── GreetingUnitTest.java
        └── resources/samples/
            └── native-proof.txt
```

**Mỗi `public class`/`public record` ở đúng tên file và package `example.aot`.** Text resource tồn tại thật trong `src/test/resources`; native image metadata sẽ khai báo path tương ứng.

## 18. Build Gradle: processTestAot và nativeTest

### 18.1. settings.gradle

```groovy
rootProject.name = 'spring-aot-test-lab'
```

### 18.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
    id 'org.graalvm.buildtools.native' version '0.10.1'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-json'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

Giải thích:

- Java 17 là compile target; Native Image toolchain phải tương thích Java target.
- `spring-boot-starter` cung cấp Spring Boot core/auto-configuration.
- `spring-boot-starter-json` thêm Jackson và auto-configuration cần cho `ObjectMapper`.
- `spring-boot-starter-test` cung cấp Spring Test + JUnit Jupiter.
- `junit-platform-launcher` nằm ở test runtime để native TestEngine discovery có dependency phù hợp.
- `org.graalvm.buildtools.native` kích hoạt GraalVM plugin; Spring Boot plugin thiết lập AOT sources/tasks tương ứng.
- `useJUnitPlatform()` cần cho Jupiter tests trên Gradle `test` task.
- Chúng ta **không khai báo manual nativeCompile/nativeTest task** vì Boot plugin phối hợp Native Build Tools theo documented integration.
- Không dùng `nativeTest` trên một JDK bất kỳ không có native-image toolchain.

### 18.3. Vì sao plugin 0.10.1?

Đây là nhánh Native Build Tools phù hợp thời kỳ Spring Boot 3.3.0, được ghi trong tài liệu Boot 3.3. Nếu triển khai thực, đối chiếu GraalVM version và plugin patch tương thích; không ghép tùy ý một plugin đời Boot 4.x vào build Boot 3.3 rồi suy ra framework API bị lỗi.

### 18.4. Có nên chạy nativeTest trong mọi PR?

Native compilation thường tốn thời gian/tài nguyên hơn JVM tests. Chính tài liệu Boot khuyến nghị giữ phần lớn tests trên JVM, tập trung native tests vào hành vi có khả năng khác biệt như reflection, resource loading, dynamic proxies, serialization và startup. CI có thể chạy native smoke trên PR quan trọng/nightly tùy rủi ro; **không bỏ hoàn toàn native tests** khi production release là native executable.

## 19. Mã nguồn runnable: application và properties

### 19.1. AotLabApplication.java

**src/main/java/example/aot/AotLabApplication.java**

```java
package example.aot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(GreetingProperties.class)
public class AotLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                AotLabApplication.class, args);
    }
}
```

`@EnableConfigurationProperties(GreetingProperties.class)` khai báo rõ properties bean, giúp Spring Boot bind constructor-based Java 17 record theo `demo.*`. Bean graph được AOT-process ở build time.

### 19.2. GreetingProperties.java

**src/main/java/example/aot/GreetingProperties.java**

```java
package example.aot;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record GreetingProperties(String prefix) {}
```

Record tạo immutable configuration object. Test cấu hình `demo.prefix=Hello` qua `@TestPropertySource`. Với Spring Boot3, record có một constructor phù hợp với constructor binding; không cần annotation `@ConstructorBinding` cho case đơn giản này.

### 19.3. GreetingService.java

**src/main/java/example/aot/GreetingService.java**

```java
package example.aot;

import org.springframework.stereotype.Service;

@Service
public final class GreetingService {

    private final GreetingProperties properties;

    public GreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return properties.prefix() + ", " + name.strip();
    }
}
```

Dự án không dùng reflection tùy ý trong business method. Nó thích hợp để tạo baseline: nếu `processTestAot` fail, nguyên nhân có thể do build/toolchain/annotation setup hơn là một thuật toán phức tạp.

## 20. Test payload và test-only resource hints

### 20.1. TicketPayload.java

**src/test/java/example/aot/TicketPayload.java**

```java
package example.aot;

public record TicketPayload(String code, int quantity) {}
```

DTO test-only dùng Jackson roundtrip. Vì record chỉ được tham chiếu từ test code, Spring AOT không phải lúc nào cũng có đủ bằng chứng để tự thêm reflection hints cho mọi binding path; `@RegisterReflectionForBinding` làm ý định explicit.

### 20.2. TestResourceHints.java

**src/test/java/example/aot/TestResourceHints.java**

```java
package example.aot;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class TestResourceHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        hints.resources().registerPattern(
                "samples/native-proof.txt");
    }
}
```

Spring AOT xử lý registrar và ghi resource pattern vào hints dùng bởi Native Image. Nó **không** tạo file nếu `src/test/resources/samples/native-proof.txt` thiếu. Phải cung cấp resource thật.

### 20.3. native-proof.txt

**src/test/resources/samples/native-proof.txt**

```text
AOT test resource is available.
```

File content này là toàn bộ một dòng và newline tùy editor. Test dùng `trim()` nên không phụ thuộc LF/CRLF cuối file, nhưng vẫn dùng UTF-8 explicit để tránh charset-dependent behavior.

## 21. AotIntegrationTest.java — Spring TestContext + annotations

**src/test/java/example/aot/AotIntegrationTest.java**

```java
package example.aot;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.aot.AotDetector;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.aot.DisabledInAotMode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = AotLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("aot-lab")
@TestPropertySource(properties = "demo.prefix=Hello")
@RegisterReflectionForBinding(TicketPayload.class)
@ImportRuntimeHints(TestResourceHints.class)
class AotIntegrationTest {

    @Autowired
    GreetingService service;

    @Autowired
    GreetingProperties properties;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    Environment environment;

    @Test
    void aotProcessedContextCanInjectService() {
        assertNotNull(service);
        assertEquals("Hello, Ada", service.greet("Ada"));
    }

    @Test
    void testPropertySourceIsApplied() {
        assertEquals("Hello", properties.prefix());
        assertTrue(environment.acceptsProfiles(
                org.springframework.core.env.Profiles
                        .of("aot-lab")));
    }

    @Test
    void jacksonRecordBindingWorks() throws Exception {
        TicketPayload expected =
                new TicketPayload("T-42", 3);

        String json =
                objectMapper.writeValueAsString(expected);

        TicketPayload actual =
                objectMapper.readValue(
                        json,
                        TicketPayload.class);

        assertEquals(expected, actual);
    }

    @Test
    void testResourceIsReadable() throws Exception {
        try (InputStream stream =
                getClass().getResourceAsStream(
                        "/samples/native-proof.txt")) {

            assertNotNull(stream);

            String content = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();

            assertEquals(
                    "AOT test resource is available.",
                    content);
        }
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> service.greet("  "));

        assertEquals(
                "name must not be blank",
                ex.getMessage());
    }

    @Test
    @DisabledInAotMode
    void jvmOnlyTestDoesNotRequireGeneratedAssets() {
        // Runs in ordinary JVM testing; skipped in
        // Spring AOT mode, including native test runs.
        assertFalse(
                AotDetector.useGeneratedArtifacts());
    }
}
```

### 21.1. Annotation nào đang chứng minh điều gì?

- `@SpringBootTest`: context được Spring TestContext tải và AOT-process.
- `@ActiveProfiles("aot-lab")`: profile là một phần của test configuration tại AOT processing.
- `@TestPropertySource`: cung cấp `demo.prefix` cho configuration properties.
- `@RegisterReflectionForBinding(TicketPayload.class)`: explicit Jackson record binding hints.
- `@ImportRuntimeHints(TestResourceHints.class)`: explicit classpath resource hints.
- `@Autowired`: bean injection từ generated context.
- `@DisabledInAotMode` trên **một method**: method đó chạy JVM bình thường nhưng được skip trong AOT mode; class vẫn có năm methods khác cần context AOT.
- `org.junit.jupiter.api.Test`: Jupiter engine quyết định discovery/execution.

### 21.2. Vì sao AOT smoke vẫn cần assertion nghiệp vụ?

Test `aotProcessedContextCanInjectService` không chỉ assert Spring context starts; nó còn assert business output chính xác. `jacksonRecordBindingWorks` kiểm tra serialization/deserialization, một loại behavior dễ khác nhau khi reflection metadata bị thiếu trong native image.

### 21.3. Vì sao dùng @RegisterReflectionForBinding trên test class?

Spring TestContext AOT docs cho phép annotation này trên test class. Nó cho thấy việc thêm hints **gắn với phạm vi test**, thay vì đăng ký reflection cho mọi DTO của ứng dụng trong production nếu không cần.

### 21.4. @DisabledInAotMode không phải native test pass

Khi `nativeTest` chạy, test `jvmOnlyTestDoesNotRequireGeneratedAssets` dự kiến được skip, không tính là executed pass. CI phải ghi skipped count. Nếu test này chứa một business assertion quan trọng, cần có native-safe replacement test; không bỏ qua coverage gap.

## 22. GreetingUnitTest.java — pure JUnit không cần context

**src/test/java/example/aot/GreetingUnitTest.java**

```java
package example.aot;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingUnitTest {

    @Test
    void greetingIsPureJava() {
        GreetingService service =
                new GreetingService(
                        new GreetingProperties("Hi"));

        assertEquals(
                "Hi, Linh",
                service.greet("  Linh  "));
    }

    @Test
    void blankNameIsRejected() {
        GreetingService service =
                new GreetingService(
                        new GreetingProperties("Hi"));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

Hai pure unit tests không dùng `@SpringBootTest`, nên không yêu cầu Spring TestContext/AOT-generated context, nhưng trong native test binary chúng vẫn cần được JUnit native engine discover và Java classes của chúng reachable. Đây là lý do **không cần biến mọi unit test thành @SpringBootTest** chỉ để “có AOT”.

### 22.1. Tổng số phương thức JUnit

| Test class | JUnit methods | JVM bình thường | Native AOT |
| --- | ---: | ---: | ---: |
| `AotIntegrationTest` | 6 | 6 dự kiến chạy | 5 chạy, 1 `@DisabledInAotMode` skipped |
| `GreetingUnitTest` | 2 | 2 dự kiến chạy | 2 dự kiến chạy |
| **Tổng** | **8** | **8 được chọn chạy** | **7 được chọn chạy, 1 skipped** |

Đây là **số lượng kỳ vọng theo source code**, không phải báo cáo đã thực thi. JUnit report thực có thể hiển thị thêm container/test engine nodes; khi có lỗi compile, runtime hoặc filtering, số thực tế khác expected.

## 23. Cách chạy trên JVM

### 23.1. Baseline

Linux/macOS:

```bash
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

Kỳ vọng: Spring Boot test context khởi tạo, properties được bind, Jackson roundtrip đúng, file resource được đọc, pure unit tests pass. `@DisabledInAotMode` method **vẫn chạy trên JVM bình thường** (không có generated AOT runtime artifacts được sử dụng).

### 23.2. Chạy từng class

```bash
./gradlew test --tests example.aot.AotIntegrationTest
./gradlew test --tests example.aot.GreetingUnitTest
```

Khi test riêng fail với `@ActiveProfiles`/`@TestPropertySource`, kiểm tra context config, không đổ ngay cho native toolchain. Nếu JVM baseline chưa pass, ưu tiên sửa Java imports, dependencies, bean wiring và assertions trước.

### 23.3. Đọc kết quả thật

Gradle test reports:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

Đọc `tests`, `failures`, `errors`, `skipped` theo từng lần chạy. `BUILD SUCCESSFUL` không tự chứng minh native executable đã được biên dịch; JVM `test` task khác `nativeTest`.

## 24. Chạy processTestAot rồi nativeTest

Yêu cầu GraalVM `native-image` trên toolchain phù hợp cùng các native build dependencies của OS.

### 24.1. Chỉ kiểm tra AOT test processing

```bash
./gradlew processTestAot
```

Nếu task thành công, Spring đã xử lý test contexts và tạo artifacts theo cấu hình hiện tại. **Nó chưa chạy JUnit trong native binary.** Nếu task này fail, xem nguồn lỗi ở Spring bean/conditions/custom loader/annotation trước khi debug native compiler.

### 24.2. Biên dịch và chạy native test executable

```bash
./gradlew nativeTest
```

Native Build Tools phối hợp với Spring Boot AOT tasks để biên dịch native test executable, sau đó chạy tests. Các dependencies/plugin/OS/JDK thật phải tương thích.

Windows PowerShell:

```powershell
.\gradlew.bat processTestAot
.\gradlew.bat nativeTest
```

### 24.3. Phân biệt tasks

| Task | Công việc | Không chứng minh |
| --- | --- | --- |
| `test` | JUnit JVM tests | Native support |
| `processAot` | Sinh AOT assets cho application | Native binary compile/test |
| `processTestAot` | Sinh AOT assets cho TestContext | Native execution thành công |
| `nativeCompile` | Build production native executable | JUnit native tests chạy |
| `nativeTest` | Build/run native test executable | Mọi test JVM đều được chọn nếu bị skip/filter |
| `bootJar` | Build JVM executable jar | Native test được chạy |
| `bootBuildImage` | Build container image theo cấu hình | JUnit native testing |

### 24.4. Nếu nativeTest quá chậm

Native compilation có thể mất nhiều tài nguyên CPU/RAM và thời gian đáng kể. Trên máy dev, chạy JVM `test` thường xuyên; trong CI, cân nhắc `processTestAot` sớm để phát hiện cấu hình, còn `nativeTest` dùng cho native smoke paths quan trọng và build release. Không tạo SLA từ máy của người khác.

## 25. AOT-enabled JVM application mode

Có thể kiểm chứng Spring AOT generated app code trên JVM:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/spring-aot-test-lab-0.0.1-SNAPSHOT.jar
```

Điều kiện: jar phải **bao gồm generated AOT assets**. Với Gradle/native plugin integration, cần bảo đảm build task thực sự đóng gói source/resource generated AOT. Chạy `bootJar` bình thường không tự đảm bảo mọi cấu hình/version đều đưa chúng vào jar; hãy theo Boot 3.3 AOT plugin guide (nếu cần cấu hình AOT task/packaging riêng).

### 25.1. Không áp dụng trực tiếp spring.aot.enabled cho test task thường

`java -Dspring.aot.enabled=true` là cách chạy **application** trên JVM với AOT assets; nó không thay `nativeTest`. Nếu bạn chỉ đặt flag này cho `./gradlew test` mà chưa chạy test AOT processing và chưa đưa generated test initializers vào test runtime classpath, Spring TestContext có thể fail vì không tìm được artifacts.

### 25.2. AOT mode không chỉ là startup optimization flag

Khi generated artifacts được dùng, profile/conditional choices đã được lựa chọn ở build time. Đặt một runtime property để lật bean graph rồi tin code generated tự re-scan là sai. Test này giúp phát hiện cấu hình không đồng bộ trước native compilation.

## 26. Resource hints: một negative experiment có kiểm soát

Trong một branch học tập, bỏ:

```java
@ImportRuntimeHints(TestResourceHints.class)
```

khỏi `AotIntegrationTest`, giữ file `src/test/resources/samples/native-proof.txt` và chạy JVM `test` trước. JVM vẫn có thể tìm file vì classpath resources bình thường. Khi `nativeTest`, resource có thể bị thiếu nếu không có cơ chế nào khác đăng ký pattern trong binary; test `testResourceIsReadable` sẽ cho tín hiệu.

**Đây là thí nghiệm, không phải lời khẳng định chắc chắn thiếu hints sẽ fail trên mọi compiler/configuration**: native build có thể nhận resource pattern từ automatic metadata hoặc plugin khác. Muốn kết luận, xem native image resource configuration/generated metadata và test report thực.

Sau đó khôi phục `@ImportRuntimeHints` để bảo đảm intent rõ và có thể lặp lại trên toolchain.

### 26.1. Nếu lỗi resource path

Dùng đúng `samples/native-proof.txt` và Java call `getResourceAsStream("/samples/native-proof.txt")`. Slash đầu ở `getResourceAsStream` là absolute classpath resource, còn `registerPattern` thường dùng resource path không có slash đầu. Tránh dùng đường dẫn filesystem absolute trong native hints.

### 26.2. Không nhét toàn bộ resources vào native image

Một pattern rộng `**/*` có thể làm binary phình lớn, đóng gói secrets/test fixtures không cần thiết. Đăng ký resources được đọc thực, không đưa credentials vào test resources.

## 27. Reflection hints: một negative experiment

Trong sandbox, bỏ:

```java
@RegisterReflectionForBinding(TicketPayload.class)
```

Sau đó chạy:

```bash
./gradlew test
./gradlew processTestAot
./gradlew nativeTest
```

JVM Jackson roundtrip có thể vẫn PASS. Native test có thể thiếu reflection metadata để deserialize Java record, **nếu không có auto-hints khác**. Nếu vẫn PASS, kiểm tra AOT có tự discover TicketPayload từ code/metadata khác không; không tuyên bố annotation là bắt buộc trong mọi tình huống.

**Sửa chính thống:** khai báo reflection hints chính xác cho type, hoặc thiết kế binding path mà AOT engine tự suy ra; tránh force all reflection. Với third-party serializers, xem reachability metadata/provider docs.

## 28. Vì sao @ContextHierarchy không thể chữa bằng RuntimeHints?

`RuntimeHints` giúp GraalVM biết classes/resources/proxies có thể dùng. Nó **không** thay đổi việc Spring TestContext AOT engine có hỗ trợ một cấu trúc context hierarchy hay không. Nếu `@ContextHierarchy` không được support trong AOT processing, thêm reflection hints cho `ParentConfig`/`ChildConfig` **không** biến TestContext thành hỗ trợ hierarchy.

Cần đổi thiết kế test hoặc loại JVM-only context khỏi native AOT processing có chủ đích. Không tắt mọi build-time error rồi tin native test đã chạy đầy đủ.

## 29. Build-time profiles/conditions: negative experiment

Giả sử app có:

```java
@Configuration
class ConditionalConfig {

    @Bean
    @ConditionalOnProperty(
            name = "demo.special.enabled",
            havingValue = "true")
    SpecialService specialService() {
        return new SpecialService();
    }
}
```

**Snippet không độc lập:** `SpecialService` chưa được định nghĩa. Nếu Spring AOT processor tạo bean graph khi property là false, rồi runtime property đổi thành true, bạn không nên kỳ vọng generated context tự tạo thêm `SpecialService` như ordinary JVM classpath scan.

### 29.1. Cách xử lý hợp lệ

- Cho AOT processing biết profile/property quyết định bean definitions ở build time.
- Giữ runtime feature flags ở mức behavior của **existing beans**, không tùy tiện thay bean classes.
- Nếu cần nhiều graph, build/test distinct native artifacts theo profiles tương ứng.
- Không coi việc JVM `@TestPropertySource` có thể đổi theo test class là bằng chứng một native executable có thể tạo mọi graph runtime tùy ý mà không có generated initializers.

## 30. Native test discovery, JUnit engines và filters

Một Gradle task có thể compile native image nhưng chạy ít tests hơn dự kiến do:

- Chỉ một subset test classes có thể AOT-process.
- Classes/methods bị `@DisabledInAotMode` hoặc `@DisabledInNativeImage`.
- `@Tag`/Gradle `--tests` hoặc engine filters chỉ chọn một tập.
- Jupiter engine/junit-platform-launcher thiếu hoặc version lệch trên test runtime.
- JUnit 4 tests cần Vintage engine nếu dùng JUnit Platform.
- Custom test task/source set không được đưa vào `processTestAot`/`nativeTest` task config.
- Native image không hỗ trợ một library/test framework plugin cụ thể.

### 30.1. Không nhầm skipped với undiscovered

`@DisabledInAotMode` method được JUnit engine nhận diện theo điều kiện, nhưng không execute khi AOT-enabled. Báo `skipped` chứ không nói “native runtime không tìm thấy JUnit @Test”.

### 30.2. Đọc report task chính xác

Xem `nativeTest` task output và artifact reports theo native plugin/version; không đọc XML JVM `test` của lượt chạy trước rồi báo native PASS. Trong CI, lưu riêng JUnit JVM và native results.

### 30.3. Pure unit tests và AOT generation

Pure JUnit unit tests không cần Spring ApplicationContext; Spring TestContext AOT processor không nhất thiết tạo initializer cho chúng. Nhưng chúng vẫn có thể được JUnit engine đưa vào native test executable nếu test selection/plugin support phù hợp. Không ép pure unit tests dùng SpringExtension chỉ để được phát hiện.

## 31. @Sql và transactional tests trong native mode

Giả sử một `@DataJpaTest` test đọc `schema.sql`/`test-data.sql`:

```java
@DataJpaTest
@Sql("/sql/seed-test-data.sql")
class JpaRepositoryNativeTest {
    @Test
    void findsSeededEntity() {
        // Assertions via repository.
    }
}
```

Snippet này **chưa runnable**: thiếu Entity/Repository, datasource và resource. Native test cần:

1. JPA provider/driver native support.
2. Resource `sql/seed-test-data.sql` có mặt trong native image.
3. Entity metadata, converters, proxies và reflection hints phù hợp.
4. Test transaction rollback semantics chính xác theo Spring TestContext.
5. Tách internal JVM test data khỏi external database/SQL side effects nếu provider DB thật.

Nếu `@Sql` script không được đóng gói, lỗi có thể là resource missing, không phải SQL dialect. Nếu DB connection fail, kiểm tra service readiness/network/driver; không đổi `@Transactional` để chữa runtime hints.

## 32. @DirtiesContext và native cache

`@DirtiesContext` có thể làm một test reload context trong runtime. Nhưng cùng một AOT-generated context vẫn là bean graph được xử lý sẵn; nó không tạo thêm bean definitions theo một runtime profile mới.

- Có thể dùng khi singleton/bean graph bị mutate không thể reset.
- Không dùng cho database fixture cleanup mặc định.
- Không tạo thêm GraalVM reflection hints sau image compilation.
- Native startup/reinitialization có thể khác JVM; test đo performance riêng nếu relevant.
- Trong parallel tests, close/evict context đang được thread khác dùng có thể gây race.
- Với nhiều distinct test contexts, AOT build và context cache memory cost đáng kể.

## 33. TestRuntimeHintsRegistrar và AotTestExecutionListener

Đây là hai extension points quan trọng khi dự án có test infrastructure riêng.

### 33.1. Global hints

Nếu một test framework/library riêng cần resource hoặc reflection cho mọi test contexts, có thể implement `TestRuntimeHintsRegistrar` và đăng ký trong `META-INF/spring/aot.factories`. Nếu hints gắn với một production component, ưu tiên `RuntimeHintsRegistrar` gần component để không đóng gói vô điều kiện.

### 33.2. Custom TestExecutionListener

Một listener custom có hành vi build-time contributions muốn tham gia AOT processing cần phù hợp `AotTestExecutionListener`. Không chỉ implement `TestExecutionListener` rồi kỳ vọng Spring AOT gọi code đó ở build time theo mọi callback.

### 33.3. Custom ContextLoader

Custom loader cần implement `AotContextLoader` để xử lý AOT build time/runtime. Không tự gắn `@ContextConfiguration(loader=LegacyLoader.class)` vào native test suite rồi suy luận engine sẽ biết cách generate context.

### 33.4. AOT failures mặc định fail-fast

Spring Framework 6.1 mặc định **fail** khi gặp AOT processing error. Có property `spring.test.aot.processing.failOnError=false` để tiếp tục và log các lỗi trong tình huống chẩn đoán; **không dùng cấu hình này làm default CI release gate**, vì nó có thể che missing native coverage/failed contexts.

## 34. Phân loại lỗi theo phase

| Thời điểm | Biểu hiện | Gợi ý root cause |
| --- | --- | --- |
| `compileJava` | Cannot resolve annotation/record | Imports/version/API sai |
| `compileTestJava` | @DisabledInAotMode class not found | Spring Framework version chưa có |
| `test` JVM | Failed to load ApplicationContext | Bean scan/config/dependencies |
| `test` JVM | Assertions failed | Business/test logic |
| `processTestAot` | Unsupported hierarchy | `@ContextHierarchy` trong AOT |
| `processTestAot` | Missing property/bean graph failure | Build-time profile/condition |
| `processTestAot` | Custom loader/listener errors | Missing AOT SPI support |
| `nativeCompile` / native image build | Unsupported reflection/library | Missing hints/native reachability metadata |
| `nativeTest` startup | Resource not found | Missing resource hints/packaging |
| `nativeTest` startup | Cannot instantiate bean | Generated config/provider incompatibility |
| `nativeTest` JUnit | Skipped due to annotation | `@DisabledInAotMode`/native condition |
| `nativeTest` JUnit | Test assertion failed | Real behavior difference |
| `nativeTest` zero tests | Engine/filter/task discovery | TestEngine, selector/runtime deps |
| CI native only | Linker/platform/architecture errors | GraalVM/OS/compiler toolchain |
| CI native only | Docker/network connection error | Container readiness/permissions |

Không gộp tất cả vào “native test failed”, vì fix khác nhau rất lớn.

## 35. Khi cần đăng ký resource/reflection hints

Một trình tự chẩn đoán tốt:

1. Chạy JVM test với exact input để loại bỏ lỗi business.
2. Chạy `processTestAot` để kiểm tra Spring-generated contexts.
3. Đọc root cause trước `Caused by` cuối cùng khi native compiler fail.
4. Xác định đúng type, method hoặc resource bị thiếu.
5. Kiểm tra Spring AOT có tự tạo hints chưa.
6. Nếu chưa, thêm `@RegisterReflectionForBinding`/`@ImportRuntimeHints`/`RuntimeHintsRegistrar` đúng chỗ.
7. Chạy lại nativeTest; xác minh đúng test được execute, không bị skip/filter.
8. Kiểm tra binary size/metadata scope nếu hints tăng rộng.
9. Thêm regression test cho behavior vừa sửa.
10. Ghi phiên bản GraalVM/JDK/Native Build Tools vì một bản cập nhật provider có thể làm hints thay đổi.

**Không dùng reflection agent output chưa lọc** làm file reachability metadata vĩnh viễn: tracing agent khi chạy tests có thể ghi thêm hints của test infrastructure không cần trong production app binary. Cần review/trim hints có mục đích và test lại.

## 36. Maven nativeTest khi không dùng Gradle

Nếu dùng Spring Boot 3.3 Maven starter parent và Native Build Tools Maven plugin, cấu hình nativeTest profile phù hợp rồi chạy:

```bash
mvn test
mvn -PnativeTest test
```

Lệnh thứ hai thực hiện test AOT/native pipeline khi plugins/profile được cấu hình đúng. Không coi `mvn -Pnative test` như tự động có native **test** coverage — profile `native` dành cho production AOT/image building; `nativeTest` dành cho test binary.

**Quan trọng:** nếu không dùng `spring-boot-starter-parent`, bạn phải cấu hình `spring-boot:process-test-aot` và Native Build Tools test goal theo Boot 3.3 Maven plugin guide. Không sao chép một POM Boot 4.x hoặc native-maven-plugin đời khác rồi dùng trong bài Boot 3.3.

### 36.1. Maven test naming vẫn quan trọng

Surefire có default file patterns như `*Test`/`*Tests`; Maven Failsafe thường dùng `*IT`. Engine selection và file naming ảnh hưởng test set được AOT xử lý. Nếu native test count thấp, đừng chỉ thêm hints khi nguyên nhân là test classes bị Maven includes lọc ra từ đầu.

## 37. Cách chọn phạm vi native test suite

Để cân bằng hiệu năng và rủi ro:

| Lớp kiểm thử | Mục tiêu | Ưu tiên |
| --- | --- | --- |
| Pure JVM unit tests | Business logic, edge cases | Chạy mỗi PR |
| JVM `@SpringBootTest` | Dependency injection, transaction, integration | Chạy thường xuyên |
| JVM test slices | MVC/JPA/JSON behavior trong scope | Chạy thường xuyên |
| `processTestAot` | Test context AOT generation | Chạy khi thay test configs/AOT |
| JVM app với generated AOT | App startup theo AOT assets | Hữu ích để debug sớm |
| `nativeTest` smoke | Startup, binding, resources, hints | Chạy trên CI toolchain native |
| Native integration DB/HTTP | Provider behavior trên binary | Theo rủi ro release |
| Production native binary E2E | Real deployment environment | Release/critical path |

Một test suite có thể có nhiều JVM-only tests vẫn hữu ích. Tuy nhiên không nên tuyên bố full native compatibility nếu các code paths serialization/security/provider quan trọng chưa được thử trên native binary.

### 37.1. Khi có nhiều profiles

Nếu một profile làm bean graph khác, hãy tạo native testing/release plan cho từng graph cần support. Đừng giả định một generated initializer sẽ tự biến thành mọi profile runtime.

### 37.2. Khi có các annotations không được hỗ trợ

- Di chuyển behavior cần native coverage sang static bean graph tương đương khi hợp lệ.
- Với `@ContextHierarchy`, giữ JVM test hoặc flatten scope có chủ đích.
- Với Mockito tests, cân nhắc test fake/real collaborator native-safe; không ép Mockito nếu toolchain không support.
- Với custom loader/listeners, implement AOT SPI trước khi convert.
- Với JPA/resources/JSON, kiểm tra native provider và hints.

## 38. Negative experiments có kiểm soát

### 38.1. Thử class-level @DisabledInAotMode

Tạo **một class dùng một test context độc lập** (khác properties/beans) có `@DisabledInAotMode`; kiểm tra nó vẫn chạy JVM test nhưng bị loại khỏi AOT build/native runtime. Không bỏ annotation ở class khác cùng context, vì Spring yêu cầu consistency trong shared context group.

### 38.2. Thử @DisabledInNativeImage

Đặt `@DisabledInNativeImage` cho một JUnit method. Dù method skipped khi chạy native executable, TestContext AOT vẫn có thể phải xử lý class/context ở build-time. Nếu context unsupported, hãy chuyển sang `@DisabledInAotMode` hoặc sửa context design.

### 38.3. Thử thay runtime property quyết định bean graph

Tạo `@ConditionalOnProperty` config ở sandbox, xử lý AOT dưới false rồi runtime true. So sánh với JVM startup bình thường. Đừng áp hành vi này cho production toggles khi chưa design build-time profiles.

### 38.4. Thử thiếu test resource hint

Bỏ `@ImportRuntimeHints` rồi chạy nativeTest; nếu test fail do missing resource, khôi phục pattern. Nếu không fail, giải thích auto hints/provider behavior, không khẳng định đây là lỗi chắc chắn.

### 38.5. Thử thiếu reflection hint

Bỏ `@RegisterReflectionForBinding` và quan sát JSON record binding native; nếu vẫn pass vì Jackson metadata được sinh bởi auto configuration, xem generated hints trước khi kết luận annotation dư.

### 38.6. Thử chuyển @ContextHierarchy từ JVM

Trong branch thử nghiệm, có một test class hierarchy-based và một flat-context replacement. JVM có thể pass cả hai; AOT xử lý cái flat-context, hierarchy-based được đánh dấu JVM-only nếu chưa được support.

### 38.7. Thử Mockito

Tạo Boot3.3 JVM test dùng `@MockBean` và một native-smoke fake-bean equivalent. So coverage và behavior. Không coi “mocks bị skip” là logic nghiệp vụ đã được native kiểm chứng.

### 38.8. Thử custom loader

Dùng legacy custom ContextLoader trong AOT, ghi error đầy đủ, sau đó implement AotContextLoader hoặc quay về default Spring Boot loader. Không dùng reflection hint để che missing SPI contract.

## 39. Lỗi phổ biến

### 39.1. “JVM PASS nên native PASS”

Sai vì native compiler cần reachability metadata, resources, proxies, native-friendly libraries và AOT-generated contexts.

### 39.2. “processTestAot PASS nên nativeTest PASS”

Sai vì processTestAot mới generate assets; native compilation/runtime có thể fail ở bước sau.

### 39.3. “@DisabledInNativeImage giống @DisabledInAotMode”

Sai vì JUnit native condition không đồng nghĩa loại Spring test context khỏi AOT build-time analysis.

### 39.4. “Thêm reflection hint sẽ sửa @ContextHierarchy”

Sai vì đó là giới hạn TestContext AOT architecture, không phải chỉ thiếu class reflection.

### 39.5. “Runtime profile có thể thêm mọi bean”

Sai với AOT generated bean graph: build-time conditions/profiles có thể đã cố định quyết định.

### 39.6. “Mọi @MockBean đều chạy native như JVM”

Không được mặc định kết luận trong Boot 3.3; Mockito/native image có các giới hạn phụ thuộc provider/version/toolchain.

### 39.7. “@SpringBootTest tự thêm JUnit engine”

Sai. JUnit Platform cần Jupiter TestEngine/launcher tương thích; SpringExtension không thay engine.

### 39.8. “@DirtiesContext làm Spring AOT phân tích lại toàn bộ”

Sai. Native image đã biên dịch không tự bổ sung new classpath/hints/bean conditions.

### 39.9. “Test resource có trên JVM là tự có trong native image”

Không chắc. Native resource inclusion dựa metadata/hints và native image build configuration.

### 39.10. “Dùng @Sql xóa được external DB từ context khác”

Sai nếu test chạy parallel trên shared DB; AOT không giải quyết isolation/ownership.

### 39.11. “Không cần phân biệt skip và pass”

Sai. Test đã skip không phải native behavior được kiểm chứng. CI phải đếm executed/failed/skipped.

### 39.12. “Boot 4.x docs dùng trực tiếp cho Boot3.3”

Sai vì các API/annotations/plugin versions đã thay đổi. Cần pin đúng reference docs.

### 39.13. “Chỉ cần nativeCompile, không cần nativeTest”

Native app binary compile cho biết một artifact build được, nhưng không chạy test assertions trên native runtime. NativeTest cung cấp coverage khác.

### 39.14. “Có GraalVM JDK là đủ”

Không chắc; cần native-image CLI/component và OS compiler/linker toolchain, memory, runtime OS compatibility.

### 39.15. “Một lỗi Mockito là bug của Spring AOT”

Có thể là native-image/JUnit/Mockito instrumentation incompatibility; phân loại trước khi mở rộng hints.

## 40. Bảng chẩn đoán triệu chứng

| Triệu chứng | Nguyên nhân gợi ý | Bước đầu |
| --- | --- | --- |
| `processTestAot` không có task | Chưa áp GraalVM native plugin/AOT plugin | Kiểm tra Gradle plugins |
| `native-image: command not found` | GraalVM Native Image chưa cài | native-image --version, GraalVM env |
| `@DisabledInAotMode cannot resolve` | Wrong Framework version/import | Spring6.1+, đúng package |
| Unsupported context hierarchy | `@ContextHierarchy` trong AOT | Chuyển flat context hoặc disable class |
| AOT build bean not found | Profile/property evaluated build-time | ProcessTestAot environment |
| Native reflection constructor error | Missing reflection hints | @RegisterReflectionForBinding |
| Test resource returns null | Missing resource hints/packaging | @ImportRuntimeHints/path |
| Jackson binding fails only native | Record/serializer hints/provider | Binding hints, ObjectMapper config |
| Missing TestEngine | Dependency/runtime classpath | junit-platform-launcher/Jupiter |
| Native tests all skipped | Disabled annotations/filters | Count skipped and reasons |
| JVM runs 8, native runs 7 | AOT-only skip method | Expected from @DisabledInAotMode |
| Class skipped but AOT still processes shared context | Shared context rules | Annotate all sharing same config |
| @DisabledInNativeImage but AOT build fails | Native-only skip not AOT exclusion | @DisabledInAotMode or fix graph |
| Native compilation OOM | Image build resource pressure | RAM/toolchain/CI runner |
| Native process starts but DB fails | Driver/service readiness | Connection/health/provider native |
| Dynamic port wrong | Testcontainers lifecycle/property timing | @DynamicPropertySource/@ServiceConnection |
| @MockBean mock creation fails native | Mockito dynamic mocking limitation | Native-safe test fake; JVM tests retained |
| Maven nativeTest profile not found | No Boot parent/plugins/profile | Configure Boot3.3 nativeTest |
| Gradle test passes, nativeTest says no tests | Native runner selection/engine | Task logs, filters, test reports |
| Runtime conditional bean differs | Build-time AOT graph fixed | Align profiles/conditions |
| @Sql script missing in native | Test resource not included | Resource hints |
| TestContext custom loader fails AOT | Not AotContextLoader | Implement AOT-compatible loader |
| Unexpected test beans reload | Context cache/dirtying | Cache diagnostics, avoid dirty misuse |
| Native smoke PASS but production API fails | Inadequate native coverage | Native HTTP/provider integration |

## 41. Bài tập thực hành

1. Chạy `./gradlew clean test` trên JVM và ghi thực số methods executed/skipped/failed.
2. Chạy `./gradlew processTestAot`, quan sát generated test assets.
3. Cài GraalVM Native Image tương thích và chạy `./gradlew nativeTest`; ghi executed/skipped từ report thật.
4. Giữ `@DisabledInAotMode` trên một method, quan sát nó chạy trong ordinary JVM test nhưng skip native.
5. Đổi annotation sang `@DisabledInNativeImage` ở sandbox; so phân biệt AOT processing vs native runtime selection.
6. Tạo class-level `@DisabledInAotMode` với context key riêng, kiểm tra xử lý build-time.
7. Tạo hai classes có shared context; đánh dấu class-level chỉ một class rồi quan sát shared-context consistency restriction.
8. Bỏ `@RegisterReflectionForBinding`, quan sát Jackson record binding native và phân tích generated hints thực.
9. Bỏ `@ImportRuntimeHints`, thử resource lookup native và kiểm tra resource metadata.
10. Viết `RuntimeHintsRegistrar` cho một proxy interface cần dùng trong sandbox, test đúng interface list.
11. Tạo test với `@ContextHierarchy`, ghi unsupported AOT error và thiết kế flat-context alternative.
12. Tạo `@ConditionalOnProperty` bean, đổi property giữa AOT build/runtime, so outputs.
13. Thử `@ActiveProfiles` với hai profiles tạo bean graphs khác, đo số generated contexts.
14. Chuyển `@MockBean` test JVM sang explicit test fake bean, chạy native smoke.
15. Giữ Mockito interaction test trên JVM, không tuyên bố fake-bean native smoke đã bao phủ mọi Mockito assertion.
16. Tạo `@JsonTest` với DTO record/custom serializer, kiểm tra binding/reflection hints.
17. Tạo `@WebMvcTest` controller trả DTO, kiểm tra endpoint/JSON native serialization.
18. Tạo `@DataJpaTest` với embedded/native-compatible driver và entity/SQL resources, theo dõi provider-specific limitations.
19. Thêm `@Sql` test script dưới `src/test/resources`, kiểm tra native resource availability.
20. Tạo custom TestExecutionListener chỉ runtime và tìm hiểu `AotTestExecutionListener` khi cần build-time contributions.
21. Tạo custom ContextLoader trong sandbox, kiểm tra `AotContextLoader` contract.
22. Tạo một JUnit 4 test, thêm Vintage engine nếu muốn chạy qua Platform; kiểm tra native plugin support thực.
23. Chạy ordinary JVM application với `spring.aot.enabled=true` khi jar có generated artifacts; ghi khác biệt với JVM test.
24. Chạy `nativeCompile` và `nativeTest` riêng, giải thích vì sao một task PASS không suy ra task kia PASS.
25. Xây CI matrix cho JVM tests + AOT processing + native smoke, ghi build time/resource cost và coverage gap.
26. Nâng Boot3.3 → Boot mới trên branch riêng, so versions, test annotations, Mockito support và Gradle Native Build Tools plugin compatibility.
27. Dùng tracing agent để tìm missing hints của third-party library, review/sanitize metadata thay vì copy tất cả JSON.
28. Lập một danh sách tests bị skip native, owner và lý do; đề xuất thay thế native-safe tests cho critical paths.

## 42. Checklist QA khi chuyển test sang AOT/native

- [ ] Biết Spring Boot, Framework, JUnit, Gradle, Native Build Tools và GraalVM versions cụ thể.
- [ ] JVM tests baseline chạy và có executed counts thật.
- [ ] `processTestAot` tạo được generated contexts cho test scope.
- [ ] `nativeTest` chạy executable, không chỉ `nativeCompile`.
- [ ] Test runtime có JUnit Jupiter engine/launcher tương thích.
- [ ] `@SpringBootTest`/test slices được dùng đúng scope.
- [ ] `@ActiveProfiles` và properties quyết định bean graph đã align build-time.
- [ ] `@TestConfiguration`/`@Import` beans được AOT processor nhìn thấy.
- [ ] `@DynamicPropertySource` chỉ dùng dynamic values phù hợp, không giả định runtime tự thay bean graph.
- [ ] `@ContextHierarchy` đã được loại khỏi AOT tests hoặc thiết kế lại rõ.
- [ ] `@DisabledInAotMode` method/class scope được hiểu đúng.
- [ ] Các classes dùng cùng context với class-level disabled nhất quán annotation.
- [ ] `@DisabledInNativeImage` không bị dùng thay AOT build-time exclusion.
- [ ] Mockito `@MockBean`/`@SpyBean` native compatibility được kiểm tra, không suy đoán.
- [ ] Tests JPA injection annotations được đánh giá đúng Framework version.
- [ ] `@Transactional` và `@Sql` được test với provider/resource thực.
- [ ] `@DirtiesContext` không bị dùng thay missing runtime hints.
- [ ] Custom loader implements `AotContextLoader` nếu cần.
- [ ] Custom listener extends/implements đúng AOT SPI nếu có build-time contributions.
- [ ] DTO/record binding có reflection hints phù hợp khi cần.
- [ ] Classpath resources có resource hints và source file thực.
- [ ] Native proxy/serialization/third-party libraries có reachability metadata phù hợp.
- [ ] Không đăng ký wildcard reflection/resources quá rộng.
- [ ] GraalVM native-image, C/C++ toolchain và RAM CI được chuẩn bị.
- [ ] Native tests không phụ thuộc Docker/provider chưa sẵn sàng.
- [ ] Reports phân biệt build error, native runtime error, assertion fail và skipped.
- [ ] JVM-only tests vẫn được duy trì khi native support chưa đầy đủ.
- [ ] Critical native paths có native-compatible regression tests.
- [ ] Không hạ `spring.test.aot.processing.failOnError` chỉ để CI xanh.
- [ ] Không tuyên bố native PASS khi chưa chạy nativeTest trên toolchain.
- [ ] Khi nâng Boot/Framework, annotation support matrix được kiểm tra lại.
- [ ] Hints/tracing agent outputs không chứa test secrets hoặc dữ liệu nhạy cảm.
- [ ] Project docs ghi exact commands và expected vs observed results riêng biệt.

## 43. Một quy tắc quyết định để dùng ngay

```text
JVM @SpringBootTest PASS, nativeTest FAIL?
        |
        +-- processTestAot FAIL?
        |       |
        |       +-- @ContextHierarchy?
        |       |       -> Unsupported AOT; redesign/disable.
        |       |
        |       +-- Build-time property/profile mismatch?
        |       |       -> Align AOT build configuration.
        |       |
        |       +-- Custom loader/listener?
        |               -> AotContextLoader/AotTestExecutionListener.
        |
        +-- native-image compiler FAIL?
        |       |
        |       +-- Reflection/resource/proxy missing?
        |       |       -> RuntimeHints/@RegisterReflectionForBinding.
        |       |
        |       +-- Mockito/native library incompatible?
        |               -> Native-safe fake/upgrade/metadata.
        |
        +-- Native executable starts but tests FAIL?
        |       |
        |       +-- Resource missing?
        |       |       -> registerPattern, package resource.
        |       |
        |       +-- External driver/service?
        |       |       -> Provider native support/readiness.
        |       |
        |       +-- Assertion mismatch?
        |               -> Diagnose actual business behavior.
        |
        +-- Native tests are skipped/not discovered?
                |
                +-- @DisabledInAotMode/@DisabledInNativeImage?
                +-- JUnit engine/filters/classpath?
                +-- Wrong Gradle/Maven source set/test task?
```

## 44. Tổng kết

**AOT test support là có thật**, nhưng **không đồng nghĩa mọi annotation và mọi dynamic testing technique trên JVM đều chạy được trong GraalVM Native Image**. Với Spring Boot 3.3 / Framework 6.1, `@SpringBootTest` và nhiều test slices được hỗ trợ; `@ContextHierarchy` là giới hạn được công bố; Spring `@DisabledInAotMode` quản lý cả build-time test context processing, khác JUnit native-only conditions. `@ActiveProfiles`, `@TestPropertySource` và bean conditions phải được đánh giá theo build-time context. Reflection/resources/proxies cần runtime hints khi Spring không tự suy luận, và Mockito/native integration nên được kiểm chứng riêng.

Quy trình kiểm thử đáng tin là **JVM test → TestContext AOT processing → GraalVM native test execution**, mỗi bước có reports và lỗi riêng. Không dùng test skip hoặc `failOnError=false` làm bằng chứng đã chuyển đổi thành công. Duy trì JVM test coverage, bổ sung native-safe smoke/integration assertions cho paths có nguy cơ khác biệt, và giữ đúng matrix versions khi migrate.

## 45. Tài liệu chính thức và tài nguyên kiểm chứng

- Spring Framework 6.1 — TestContext AOT package/Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/aot/package-summary.html
- Spring Framework 6.1 — `@DisabledInAotMode` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/test/context/aot/DisabledInAotMode.html
- Spring Framework — Ahead of Time Support for Tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/aot.html
- Spring Framework — Core AOT optimizations and runtime hints: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework 6.1 — `@RegisterReflectionForBinding` API: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html
- Spring Framework — RuntimeHints & `@ImportRuntimeHints`: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot 3.3 — Testing native applications: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/testing-native-applications.html
- Spring Boot 3.3 — Gradle AOT plugin/tasks: https://docs.spring.io/spring-boot/docs/3.3.0-SNAPSHOT/gradle-plugin/reference/htmlsingle/
- Spring Boot 3.3 — Maven AOT processing: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot 3.3 — Native image advanced topics: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html
- Spring Boot 3.3 — Spring Boot testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot GraalVM wiki — Mockito/native limitations: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM
- JUnit Jupiter — `@DisabledInNativeImage`/`@EnabledInNativeImage` conditions: https://docs.junit.org/5.11.4/user-guide/index.html
- GraalVM — Native Image testing with Maven and Gradle: https://www.graalvm.org/latest/reference-manual/native-image/guides/debug-native-tests-maven-gradle/

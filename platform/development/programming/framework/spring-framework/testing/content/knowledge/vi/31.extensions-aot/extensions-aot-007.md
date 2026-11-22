# AOT processing cho kiểm thử tích hợp Spring

Spring thường tạo application context khi ứng dụng hoặc bài kiểm thử bắt đầu chạy. Trong quá trình đó, framework đọc cấu hình, phát hiện bean, phân tích dependency và chuẩn bị các thành phần cần thiết. Với ứng dụng lớn, bước khởi tạo này có thể tốn thời gian; khi biên dịch thành native image, một số thao tác phản chiếu và truy cập tài nguyên còn phải được khai báo trước để GraalVM có thể đóng gói đúng.

Ahead-of-Time (AOT) processing chuyển một phần công việc chuẩn bị context sang thời điểm build. Spring phân tích cấu hình, sinh mã khởi tạo và đăng ký runtime hints cho các thao tác cần thiết. Spring Boot hỗ trợ AOT cho cả ứng dụng và test context, nhờ đó có thể kiểm tra các cấu hình tích hợp trong chế độ AOT và chuẩn bị test để chạy trong môi trường native phù hợp.

Trong kiểm thử tích hợp, cần phân biệt ba việc có liên quan nhưng không giống nhau:

- **Application AOT:** xử lý cấu hình của ứng dụng để sinh mã khởi tạo và hints cho runtime.
- **Test context AOT:** xử lý các application context được tạo từ test configuration, chẳng hạn context của `@SpringBootTest` hoặc một test slice.
- **Native test execution:** biên dịch và chạy test trong native executable. Đây là một bước kiểm tra bổ sung, không đồng nghĩa với việc chỉ chạy AOT processing trên JVM.

## 1. AOT processing giải quyết vấn đề gì?

Trong cách khởi động thông thường, Spring xây dựng `ApplicationContext` trong runtime. Các bước chính có thể gồm:

1. Đọc cấu hình ứng dụng và các nguồn property.
2. Phát hiện configuration class, component và bean definition.
3. Phân tích dependency giữa các bean.
4. Đăng ký bean post-processor, proxy và các thành phần hạ tầng.
5. Tạo bean và hoàn tất refresh context.

Với AOT, Spring thực hiện một phần công việc phân tích khi build và sinh mã Java đại diện cho việc khởi tạo context. Khi chạy ứng dụng, runtime có thể dùng mã được sinh để tạo context với ít công việc khám phá động hơn.

Quá trình này đặc biệt quan trọng với GraalVM Native Image. Native Image phân tích chương trình theo mô hình closed-world: các lớp, phương thức, tài nguyên và proxy cần dùng phải được nhận diện trong quá trình build native. Những thao tác chỉ xuất hiện qua reflection hoặc truy cập tài nguyên động có thể cần runtime hints.

AOT processing giúp Spring cung cấp metadata cần thiết thay vì phụ thuộc hoàn toàn vào việc dò tìm động khi ứng dụng đã chạy.

## 2. Application AOT và Test AOT khác nhau thế nào?

Spring Boot cung cấp hai luồng AOT chính:

| Luồng | Đầu vào | Kết quả chính | Mục đích |
| --- | --- | --- | --- |
| Application AOT | Cấu hình ứng dụng production | Mã khởi tạo context và runtime hints cho ứng dụng | Chuẩn bị ứng dụng để chạy với AOT hoặc native image |
| Test AOT | Cấu hình context được khai báo bởi test | Mã khởi tạo và hints cho test application context | Chuẩn bị context của integration test cho AOT/native test execution |

Application AOT thường được gọi qua task `processAot` của Gradle hoặc goal `process-aot` của Spring Boot Maven Plugin. Test AOT dùng task `processTestAot` hoặc goal `process-test-aot` tương ứng trong các phiên bản plugin hỗ trợ.

Ví dụ, ứng dụng có cấu hình production và test slice:

```text
Application configuration
        |
        +--> Application AOT processing
        |         |
        |         +--> Generated application context initializer
        |         +--> Application runtime hints
        |
Test classes and test configuration
        |
        +--> Test AOT processing
                  |
                  +--> Generated test context initializer
                  +--> Test runtime hints
```

Test AOT không sinh lại logic assertion trong từng phương thức test. Nó chuẩn bị context mà test cần sử dụng. Test method vẫn được thực thi bởi test engine như JUnit; phần khác biệt nằm ở cách test context được khởi tạo trong AOT mode.

## 3. Test context AOT hoạt động như thế nào?

Spring TestContext Framework quản lý context cho các test tích hợp. Khi dùng `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc `@ContextConfiguration`, framework xác định metadata của test và tạo context tương ứng.

Trong luồng thông thường, context được tải từ cấu hình lúc test chạy. Trong luồng AOT, Spring phân tích test context ở build time và sinh mã initializer cho cấu hình đó. Khi test chạy trong AOT mode, Spring sử dụng initializer được sinh thay vì thực hiện toàn bộ quá trình phân tích context theo cách thông thường.

Luồng tổng quát:

```text
Build time
----------
Test classes + Spring test metadata
              |
              v
      TestContext AOT processor
              |
              +--> Analyze test context configuration
              +--> Generate context initializer code
              +--> Register runtime hints
              |
              v
      Generated test AOT artifacts

Test runtime
------------
JUnit discovers test class
              |
              v
      Spring TestContext Framework
              |
              v
      Generated context initializer
              |
              v
      ApplicationContext for test
              |
              v
      Execute test methods
```

Điều này giúp kiểm tra rằng context của test có thể được chuẩn bị bằng các artifact đã sinh. Với native testing, nó còn giúp đưa cấu hình test và các hints cần thiết vào quá trình tạo native executable.

## 4. Những loại test nào có thể hưởng lợi từ Test AOT?

Test AOT hữu ích nhất với các test cần Spring application context, đặc biệt khi muốn xác nhận ứng dụng hoặc các lớp cấu hình có thể chạy trong môi trường native.

| Loại test | Ví dụ | Giá trị của Test AOT |
| --- | --- | --- |
| Full integration test | `@SpringBootTest` | Kiểm tra context tích hợp rộng có thể được AOT xử lý |
| MVC slice | `@WebMvcTest` | Chuẩn bị context chứa controller và hạ tầng MVC |
| JPA slice | `@DataJpaTest` | Chuẩn bị context persistence của test |
| JSON slice | `@JsonTest` | Kiểm tra cấu hình mapper/serializer trong context AOT |
| Spring context tùy chỉnh | `@ContextConfiguration` | Kiểm tra nguồn cấu hình test có thể được xử lý AOT nếu các thành phần liên quan hỗ trợ |

Không phải mọi test đều cần Test AOT. Unit test thuần Java không tạo Spring context thường không thu được lợi ích từ việc sinh context initializer. Hãy ưu tiên các test đại diện cho cấu hình Spring thực tế và các tích hợp có rủi ro liên quan đến reflection, resource loading, proxy hoặc native runtime.

## 5. Bật AOT processing cho ứng dụng và test

Các task/goal AOT được Spring Boot plugin cung cấp. Tên và khả năng tích hợp cụ thể phụ thuộc phiên bản Spring Boot Gradle Plugin hoặc Maven Plugin của dự án.

### Với Gradle

Ví dụ build sử dụng Spring Boot Gradle Plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Các task AOT thường dùng:

```bash
./gradlew processAot
./gradlew processTestAot
```

- `processAot` xử lý application context của ứng dụng.
- `processTestAot` xử lý context được khai báo trong test.

Nếu dự án tích hợp GraalVM Native Build Tools, plugin native cung cấp các task liên quan đến biên dịch hoặc chạy native executable. Hãy kiểm tra task có trong phiên bản plugin đang dùng, ví dụ:

```bash
./gradlew tasks --all
```

Không nên nhầm `processTestAot` với task chạy test. Nó chuẩn bị artifact AOT; các task test hoặc native test mới thực thi test method.

### Với Maven

Spring Boot Maven Plugin cung cấp các goal AOT trong các phiên bản hỗ trợ:

```bash
./mvnw spring-boot:process-aot
./mvnw spring-boot:process-test-aot
```

Goal thứ nhất xử lý cấu hình ứng dụng; goal thứ hai xử lý test context. Nếu dự án dùng Maven profile hoặc plugin native riêng, hãy xem cấu hình build hiện tại để xác định goal biên dịch và chạy test native.

### Kiểm tra phiên bản plugin

Không nên nâng riêng `spring-boot-maven-plugin` hoặc Gradle plugin khỏi phiên bản Spring Boot mà ứng dụng đang dùng. Plugin cần đồng bộ với dòng Spring Boot và dependency management của dự án. Nếu task `processTestAot` hoặc goal `process-test-aot` không tồn tại, hãy kiểm tra phiên bản plugin và tài liệu tương ứng trước khi tự thêm task thủ công.

## 6. Ví dụ integration test với @SpringBootTest

Giả sử ứng dụng có service và controller:

```java
@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Collections.singletonMap("message", greetingService.greet(name));
    }
}
```

Integration test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void loadsApplicationContextAndReturnsGreeting() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

Test này khởi tạo application context Boot và đi qua Spring MVC bằng MockMvc. Khi chạy AOT test processing, Spring chuẩn bị context initializer cho cấu hình test đó. Khi test chạy theo AOT mode, context có thể được tạo từ artifact đã sinh.

MockMvc vẫn dùng Servlet request/response mô phỏng. Nếu cần xác nhận embedded server hoặc network stack, hãy có thêm test dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client. Test AOT không tự biến MockMvc thành HTTP server thật.

## 7. Test slice và AOT

Test slice cũng tạo application context, vì vậy chúng có thể tham gia luồng Test AOT khi phiên bản Spring Boot và các thành phần trong context hỗ trợ.

Ví dụ MVC slice:

```java
@WebMvcTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private GreetingService greetingService;

    @Test
    void mapsGreetingRequest() throws Exception {
        given(greetingService.greet("Lan")).willReturn("Hello, Lan");

        mockMvc.perform(get("/greetings/Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

Test slice giữ phạm vi nhỏ hơn full context. AOT processing của slice giúp kiểm tra cấu hình MVC test và các bean liên quan có thể được chuẩn bị trong AOT mode. Nếu slice dùng custom test configuration hoặc test context customizer, thành phần đó cũng phải tương thích với cơ chế AOT.

Với các phiên bản Spring Framework/Spring Boot cũ, annotation mock bean có thể là `@MockBean` thay vì `@MockitoBean`. Ví dụ dùng `@MockitoBean` yêu cầu Spring Framework 6.2 trở lên.

## 8. Runtime hints và native image trong integration test

Native Image không thể tự động giữ mọi lớp và tài nguyên mà ứng dụng có thể truy cập động. Nếu code dùng reflection, resource loading, serialization hoặc dynamic proxy, native image có thể cần metadata để biết những thành phần nào phải được giữ lại.

Spring AOT sinh runtime hints cho nhiều trường hợp framework có thể phân tích. Khi ứng dụng có thư viện hoặc code tùy chỉnh sử dụng reflection/resource động, developer có thể cần đăng ký hints.

Một `RuntimeHintsRegistrar` ví dụ:

```java
public class GreetingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("greetings/*.json");
        hints.reflection().registerType(
                GreetingPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Đăng ký registrar bằng `@ImportRuntimeHints`:

```java
@Configuration
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingConfiguration {
}
```

Khi test tích hợp chạy trên JVM thông thường, thiếu runtime hint có thể không gây lỗi vì JVM cho phép reflection và resource access linh hoạt. Khi chạy native executable, thiếu hint có thể làm test hoặc ứng dụng thất bại. Vì vậy, native integration test là cách hữu ích để phát hiện những giả định runtime chưa được khai báo.

### Kiểm tra hints bằng RuntimeHintsPredicates

Spring cung cấp API để kiểm tra hints đã được đăng ký:

```java
class GreetingRuntimeHintsTest {

    @Test
    void registersGreetingPayloadReflectionHints() {
        RuntimeHints hints = new RuntimeHints();
        new GreetingRuntimeHints().registerHints(hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onType(GreetingPayload.class))
                .accepts(hints);
    }
}
```

Đây là unit test cho đăng ký metadata, không phải native integration test hoàn chỉnh. Nó xác nhận registrar khai báo hint mong đợi. Native image test vẫn cần thiết để kiểm tra kết quả cuối cùng trong môi trường closed-world.

## 9. Hạn chế và điều kiện của Test AOT

AOT processing diễn ra ở build time, vì vậy test context cần có cấu hình đủ ổn định để phân tích và sinh mã. Một số tình huống có thể cần xử lý riêng:

- Cấu hình phụ thuộc biến môi trường hoặc system property thay đổi giữa build và test runtime.
- Bean definition được tạo bằng logic động mà AOT engine không thể suy luận.
- `ContextCustomizer`, `ContextCustomizerFactory` hoặc extension test tùy chỉnh không hỗ trợ AOT.
- Cấu hình dựa vào tài nguyên chỉ có trong môi trường chạy test, không có khi build.
- Test cần khởi động service bên ngoài ngay trong giai đoạn xử lý context.
- Code sử dụng reflection, resource hoặc proxy mà chưa có runtime hints cần thiết.

Với Testcontainers hoặc `@DynamicPropertySource`, hãy đặc biệt chú ý thời điểm giá trị được tạo. AOT processing có thể cần nạp test context ở build time; nếu việc đó yêu cầu container hoặc dịch vụ bên ngoài, môi trường build phải cung cấp chúng hoặc test phải được thiết kế để không phụ thuộc vào một giá trị runtime không ổn định khi sinh mã.

Không nên giả định mọi integration test có thể được AOT xử lý mà không thay đổi. Hãy chạy task Test AOT trên CI hoặc môi trường build tương ứng để phát hiện customizer, context configuration hoặc external dependency không tương thích.

### Dùng @DisabledInAotMode khi test không phù hợp

Spring Test cung cấp `@DisabledInAotMode` trong các phiên bản hỗ trợ để đánh dấu test class hoặc method không nên chạy khi AOT mode được bật.

Ví dụ:

```java
@SpringBootTest
@DisabledInAotMode("This test depends on runtime-only context mutation")
class RuntimeOnlyConfigurationTest {

    @Test
    void verifiesRuntimeSpecificBehavior() {
        // Test chỉ phù hợp với context khởi tạo theo runtime thông thường.
    }
}
```

Annotation này dành cho trường hợp có lý do kỹ thuật rõ ràng khiến test không thể chạy trong AOT mode. Không nên dùng nó để che giấu lỗi AOT trong test đại diện cho cấu hình production; các test quan trọng cho native compatibility vẫn cần được chạy và sửa cho tương thích.

## 10. Test AOT trên JVM và native test execution

Hai môi trường này cung cấp mức độ kiểm chứng khác nhau:

| Cách chạy | Điều được xác nhận | Giới hạn |
| --- | --- | --- |
| Test thông thường trên JVM | Logic ứng dụng và context được tạo theo runtime path thông thường | Không xác nhận generated AOT context |
| Test trong AOT mode trên JVM | Context có thể được khởi tạo bằng artifact AOT | Vẫn chạy trên JVM, không kiểm tra mọi giới hạn của native image |
| Native integration test | Context, runtime hints và test code hoạt động trong native executable | Build chậm hơn, cần GraalVM/native toolchain và tài nguyên phù hợp |

Không nên coi một lần chạy test thông thường là bằng chứng native compatibility. Ngược lại, native test thường tốn thời gian build và chạy hơn, nên có thể chọn một tập integration test đại diện để thực thi trong pipeline native.

Một pipeline có thể tổ chức theo các lớp:

```text
Pull request
   |
   +--> Unit tests on JVM
   |
   +--> Integration tests on JVM
   |
   +--> Test AOT processing
             |
             +--> AOT-mode tests on JVM (nếu cấu hình)
             |
             +--> Native test build/run (theo pipeline native)
```

Các bước có thể chạy ở stage khác nhau tùy thời gian build và mức độ quan trọng của native deployment.

## 11. Tổ chức integration test để phù hợp AOT

Một số nguyên tắc giúp test context dễ xử lý AOT:

1. Ưu tiên cấu hình Spring rõ ràng bằng `@Configuration`, `@Import`, `@TestConfiguration` và các annotation Boot chuẩn.
2. Giữ bean definition xác định được ở build time; tránh thay đổi cấu hình bean tùy tiện sau khi context đã refresh.
3. Tách test phụ thuộc môi trường động khỏi test xác nhận cấu hình ứng dụng cốt lõi.
4. Khai báo runtime hints cho reflection, resource và proxy tùy chỉnh khi cần.
5. Đảm bảo test infrastructure như database, container hoặc mock server sẵn sàng ở giai đoạn AOT processing nếu context cần chúng.
6. Chạy cả test thường và test AOT; hai đường chạy có thể phát hiện những lỗi khác nhau.
7. Chọn một nhóm native integration test đại diện cho các đường đi quan trọng của ứng dụng.

Không cần chuyển mọi unit test thành AOT test. Tập trung vào context tích hợp và các thành phần có khả năng gặp vấn đề trong native runtime.

## 12. Chẩn đoán lỗi thường gặp

### Task processTestAot không tồn tại

Kiểm tra phiên bản Spring Boot plugin và cách plugin được áp dụng. Các task AOT phụ thuộc vào dòng phiên bản Boot; không tự tạo task cùng tên khi plugin chưa hỗ trợ.

### Test context không thể được xử lý ở build time

Đọc lỗi AOT để xác định bean definition, context customizer hoặc property source gây vấn đề. Kiểm tra xem context có phụ thuộc service bên ngoài, biến môi trường hoặc giá trị chỉ có ở runtime hay không.

### Native image thiếu class hoặc resource

Kiểm tra runtime hints cho reflection, serialization, resource và proxy. Dùng `RuntimeHintsPredicates` để xác nhận registrar đăng ký hint cần thiết; sau đó chạy native test để xác nhận artifact cuối.

### Test chạy trên JVM nhưng thất bại trong native executable

JVM cho phép nhiều hành vi động mà native image không thể tự suy luận. Kiểm tra reflection, resource path, serialization, dynamic proxy, JNI và các thư viện chưa hỗ trợ native. Bổ sung hints hoặc thay cách triển khai phù hợp.

### Test dùng Testcontainers thất bại khi AOT processing

Xác định container có bị khởi động trong build-time context loading hay không, và Docker/runtime có sẵn trong môi trường build không. Cấu hình pipeline để cung cấp dependency cần thiết hoặc tách test không phù hợp khỏi AOT mode với lý do rõ ràng.

### Context AOT chạy được nhưng hành vi test sai

AOT processing kiểm tra cách context được chuẩn bị, không chứng minh mọi quy tắc nghiệp vụ đúng. Vẫn cần assertion cho endpoint, repository, transaction, message handling và các hành vi tích hợp mà test hướng tới.

## 13. Quy trình triển khai AOT cho integration test

Có thể triển khai theo các bước sau:

1. Xác định mục tiêu: tăng tốc khởi tạo context, xác nhận generated context hay kiểm tra native compatibility.
2. Kiểm tra Spring Boot, Spring Framework, build plugin và GraalVM Native Build Tools version.
3. Chạy integration test thông thường để có baseline.
4. Chạy application AOT nếu cần xác nhận cấu hình production.
5. Chạy Test AOT để xử lý các context được khai báo trong test suite.
6. Sửa các cấu hình hoặc customizer chưa tương thích; bổ sung runtime hints khi cần.
7. Chạy test trong AOT mode trên JVM nếu pipeline hỗ trợ.
8. Chọn test đại diện để build và chạy native executable.
9. Theo dõi thời gian build, kích thước native image, lỗi khởi tạo context và kết quả integration test trên CI.

Nên giữ bước Test AOT trong pipeline đủ thường xuyên để phát hiện regression ở cấu hình test, đặc biệt khi thêm thư viện, custom bean factory logic hoặc thay đổi cách nạp tài nguyên.

## 14. Kết luận

AOT processing cho kiểm thử tích hợp Spring chuẩn bị application context của test ở build time, sinh mã initializer và runtime hints để context có thể được khởi tạo trong AOT mode và môi trường native phù hợp. `processAot` xử lý context ứng dụng; `processTestAot` xử lý context được khai báo trong test. Native test execution là bước bổ sung để kiểm tra chương trình trong native executable.

Hãy dùng Test AOT cho những integration test đại diện cho cấu hình Spring quan trọng, giữ test context ổn định và khai báo runtime hints cho hành vi động khi cần. Chạy test thường để xác nhận logic, Test AOT để xác nhận generated context và native integration test để phát hiện khác biệt của closed-world runtime. Ba mức kiểm tra này bổ trợ nhau khi ứng dụng cần hỗ trợ AOT hoặc GraalVM Native Image.

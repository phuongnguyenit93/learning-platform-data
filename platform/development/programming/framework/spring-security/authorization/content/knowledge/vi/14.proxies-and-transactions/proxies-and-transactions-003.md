# Self-invocation: khi lời gọi nội bộ bỏ qua proxy của Spring Security và giao dịch

## 1. Mục tiêu

Trong ứng dụng Spring Security, bạn có thể đã gắn `@PreAuthorize` vào một phương thức nhưng vẫn thấy phương thức đó được chạy khi người dùng không có quyền. Một nguyên nhân quan trọng là **self-invocation**: phương thức của một bean gọi phương thức khác **trên chính đối tượng đó**, ví dụ `this.adminAction()` hoặc `adminAction()`.

Ở chế độ Spring AOP proxy thông thường, lời gọi nội bộ này không đi lại qua proxy. Vì vậy, những advice gắn với phương thức được gọi bên trong, như **method security** (`@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`) hoặc **transaction** (`@Transactional`), có thể **không được kích hoạt cho lượt gọi nội bộ**.

Bài học thuộc nhóm **Proxy và giao dịch** của Spring Security Authorization. Sau khi học, bạn có thể:

1. Giải thích đường gọi bên ngoài qua proxy và đường gọi `this.method()` bỏ qua proxy.
2. Nhận diện hậu quả đối với `@PreAuthorize` và `@Transactional`, nhất là `REQUIRES_NEW`.
3. Phân biệt trường hợp annotation chưa được bật, phương thức không thể được proxy và self-invocation.
4. Sửa thiết kế bằng cách chuyển ranh giới được bảo vệ sang bean khác, rồi gọi qua Spring injection.
5. Viết kiểm thử tích hợp Java 17+ để chứng minh một đường gọi nguy hiểm và một đường gọi an toàn, không chỉ tin rằng annotation đã xuất hiện trong mã nguồn.

**Phạm vi:** Spring Framework AOP và Spring Security Method Security ở chế độ **proxy mặc định**, với ví dụ Spring Boot 3.x / Spring Security 6.x. Những chế độ weaving AspectJ được trình bày như ngoại lệ có điều kiện, không được coi là mặc định.

## 2. Proxy bảo vệ phương thức như thế nào?

Khi bật `@EnableMethodSecurity`, Spring Security tạo các advisor/interceptor xử lý annotation ủy quyền trên Spring-managed bean. Một service có phương thức:

```java
@PreAuthorize("hasRole('ADMIN')")
public String adminAction() {
    return "secret";
}
```

không được kiểm soát chỉ vì Java nhìn thấy annotation. Khi một **client gọi qua Spring proxy**, các interceptor liên quan mới có cơ hội kiểm tra quyền trước khi đến thân phương thức.

Luồng minh họa:

```text
Lời gọi từ bean khác / controller
           |
           v
       Spring proxy
           |
           +--> Method Security interceptor: @PreAuthorize
           |        |
           |        +-- không đủ quyền --> AccessDeniedException
           |        |
           |        +-- đủ quyền ------+
           |                           |
           v                           v
   các advice liên quan          target.adminAction()
           |
           v
     kết quả cho caller
```

Trong thực tế, bean có thể được áp dụng nhiều advice (authorization, transaction, logging...). Sơ đồ chỉ mô tả ý tưởng; **thứ tự giữa authorization và transaction là cấu hình advisor**, không được tự mặc định rằng luôn có một thứ tự cố định. Điểm quyết định ở đây là **lời gọi phải đi vào chuỗi advice qua proxy**.

### Self-invocation bỏ qua chuỗi advice của phương thức được gọi

```java
public class ReportService {

    public String buildReport() {
        return this.adminAction(); // self-invocation
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminAction() {
        return "secret";
    }
}
```

Nếu controller gọi `reportService.buildReport()` qua proxy, proxy tiếp nhận **lời gọi buildReport**. Sau khi chuyển vào target, `buildReport()` gọi `this.adminAction()` trực tiếp trên chính target. Không có lần đi vào proxy thứ hai để kích hoạt `@PreAuthorize` của `adminAction()`.

Hai cách gọi có thể khác nhau hoàn toàn:

| Cách gọi | Có đi qua proxy cho `adminAction`? | Hệ quả khi user không có ADMIN |
| --- | --- | --- |
| `reportService.adminAction()` từ bean/client đang giữ reference proxy | Có | `@PreAuthorize` chặn lời gọi |
| `reportService.buildReport()` rồi `this.adminAction()` | **Không** ở bước gọi nội bộ | `@PreAuthorize` trên `adminAction` bị bỏ qua |
| `buildReport()` rồi `adminAction()` không ghi `this` | **Không** | Tương tự self-invocation |
| `coordinator.run()` gọi `securedService.adminAction()` qua dependency do Spring inject | Có | `@PreAuthorize` được kiểm tra |

Lưu ý: nếu **`buildReport()` cũng có annotation** và được gọi qua proxy, advice trên `buildReport` vẫn có hiệu lực. Chỉ **lần chuyển tiếp nội bộ sang `adminAction()`** không được proxy chặn. Không nên nói “mọi bảo mật đều mất” khi vẫn có những kiểm tra khác ở các ranh giới đã thực thi.

## 3. Hậu quả với bảo mật phương thức

Ví dụ một API cho nhân viên thông thường có thể gọi `buildReport`; trong method lại có `this.deleteAllReports()` được gắn `@PreAuthorize("hasRole('ADMIN')")`. Nếu không có kiểm tra bổ sung, đường gọi nội bộ có thể vào phần xóa dữ liệu dù người dùng thiếu quyền ADMIN. Đây là lỗi **vượt ranh giới ủy quyền** trong thiết kế service, không đơn giản là lỗi hiển thị UI.

Các annotation bị ảnh hưởng nếu lời gọi đến chính phương thức có annotation không đi qua proxy:

- `@PreAuthorize`: quyết định cho vào thân phương thức có thể không chạy.
- `@PostAuthorize`: kiểm tra giá trị trả về có thể không chạy.
- `@PreFilter`: tham số đầu vào có thể không được lọc.
- `@PostFilter`: dữ liệu trả về có thể không được lọc.

Nếu phương thức nội bộ đọc dữ liệu nhạy cảm, `@PostFilter` bị bỏ qua có thể trả **toàn bộ kết quả**, thay vì chỉ tập người dùng được xem. Nếu `@PreFilter` bị bỏ qua, tác vụ batch có thể xử lý cả những phần tử vốn phải bị loại. Đừng thiết kế chính sách dựa vào giả định rằng “có annotation là an toàn với mọi lời gọi Java”.

Cũng đừng xem việc kiểm soát ở HTTP endpoint là bảo vệ đủ cho mọi đường gọi. Service có thể được tái sử dụng bởi scheduled job, listener, batch worker hoặc API khác. Các điểm vào đó cần có hợp đồng xác thực, ủy quyền và lời gọi qua proxy phù hợp.

## 4. Hậu quả với `@Transactional`

`@Transactional` trong proxy mode có **cùng ranh giới AOP**. Một phương thức nội bộ được gắn `@Transactional` nhưng gọi bằng `this.inner()` sẽ không được transaction advice xử lý cho chính lời gọi ấy.

```java
@Service
public class BillingService {

    public void process() {
        this.saveInvoice(); // Không đi qua transactional proxy cho saveInvoice.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInvoice() {
        // Lời gọi nội bộ không tự khởi tạo transaction REQUIRES_NEW.
    }
}
```

**Tình huống A — phương thức ngoài không có transaction:** `process()` gọi trực tiếp `saveInvoice()`; `REQUIRES_NEW` trên `saveInvoice` không được áp dụng, nên không tự mở transaction riêng cho method này. Nếu bên trong có các repository method tạo transaction độc lập, điều đó là hành vi của **repository/lời gọi khác**, không chứng minh annotation trên `saveInvoice` đã chạy.

**Tình huống B — phương thức ngoài đang có transaction:** nếu `process()` được gọi qua proxy và đã ở trong transaction, `this.saveInvoice()` vẫn thực thi **bên trong transaction hiện có**. Khi đó `TransactionSynchronizationManager.isActualTransactionActive()` có thể là `true`, nhưng `REQUIRES_NEW` của `saveInvoice` vẫn **không hề được áp dụng**. Để kiểm tra đúng ngữ nghĩa `REQUIRES_NEW`, cần xác minh transaction mới được tạo/tách biệt, chẳng hạn bằng một integration test rollback/commit trên database thực.

Khi một phương thức đồng thời có `@PreAuthorize` và `@Transactional`, lời gọi bên ngoài qua proxy có thể kích hoạt **cả hai** advice. Lời gọi self-invocation có thể bỏ qua cả hai advice của phương thức đích. Đừng dùng việc transaction có hoạt động hay không để suy đoán rằng authorization chắc chắn đã chạy: hai chính sách cần được kiểm thử riêng.

## 5. Ví dụ Java 17+ chạy được: chứng minh lỗi và cách sửa

Bộ test sau dùng Spring Boot 3.x, H2 in-memory database để có transaction manager, Spring Security Method Security và JUnit Jupiter. Nó có hai phương án:

- **Không an toàn:** `BrokenService.unsafeEntry()` gọi `this.adminAction()`. Cả `@PreAuthorize` và `@Transactional` trên `adminAction` không được áp dụng trong lượt gọi nội bộ.
- **An toàn:** `Coordinator.safeEntry()` gọi `SecuredService.adminAction()` qua reference **Spring-injected bean**. Proxy của `SecuredService` chặn quyền và mở transaction khi người dùng đủ quyền.

### 5.1. Cấu trúc project và dependencies

```text
self-invocation-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/SelfInvocationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'self-invocation-demo'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` và `@EnableMethodSecurity` cung cấp method security; `spring-boot-starter-jdbc` và H2 cho Spring Boot tự cấu hình `DataSource`/transaction manager. Spring test context chạy mà không cần web server. Ví dụ không lưu dữ liệu thực vào H2; H2 được dùng để quan sát **ranh giới transaction**. Khi đưa về ứng dụng thật, hãy dùng transaction manager phù hợp nguồn dữ liệu của dự án.

### 5.2. Toàn bộ test class

Tạo tệp `src/test/java/demo/SelfInvocationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = SelfInvocationTest.TestConfig.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
public class SelfInvocationTest {

    @Autowired BrokenService brokenService;
    @Autowired SecuredService securedService;
    @Autowired Coordinator coordinator;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @EnableTransactionManagement
    public static class TestConfig {

        @Bean
        BrokenService brokenService() {
            return new BrokenService();
        }

        @Bean
        SecuredService securedService() {
            return new SecuredService();
        }

        @Bean
        Coordinator coordinator(SecuredService securedService) {
            return new Coordinator(securedService);
        }
    }

    public static class BrokenService {

        public String unsafeEntry() {
            return this.adminAction(); // Nội bộ: bỏ qua proxy.
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public String adminAction() {
            return "txActive=" +
                TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static class SecuredService {

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public String adminAction() {
            return "txActive=" +
                TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static class Coordinator {
        private final SecuredService securedService;

        public Coordinator(SecuredService securedService) {
            this.securedService = securedService;
        }

        public String safeEntry() {
            // Khác bean: đi qua Spring proxy của SecuredService.
            return securedService.adminAction();
        }
    }

    @Test
    void servicesReallyAreSpringProxies() {
        assertThat(AopUtils.isAopProxy(brokenService)).isTrue();
        assertThat(AopUtils.isAopProxy(securedService)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directCallToRestrictedMethodIsDenied() {
        assertThatThrownBy(brokenService::adminAction)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void selfInvocationUnexpectedlyBypassesAuthorizationAndTransaction() {
        // Ví dụ phơi bày bug, KHÔNG phải hành vi an toàn mong muốn.
        assertThat(brokenService.unsafeEntry())
            .isEqualTo("txActive=false");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void differentBeanEnforcesAuthorization() {
        assertThatThrownBy(coordinator::safeEntry)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directAuthorizedCallStartsTransaction() {
        assertThat(securedService.adminAction())
            .isEqualTo("txActive=true");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void differentBeanStartsTransactionForAuthorizedCaller() {
        assertThat(coordinator.safeEntry())
            .isEqualTo("txActive=true");
    }
}
```

**Vì sao ví dụ kiểm tra được cả security và transaction?** `@EnableMethodSecurity` phát hành method authorization advisors; `@EnableTransactionManagement` kích hoạt transaction proxy; `@EnableAutoConfiguration` cùng starter JDBC/H2 tạo transaction manager. Test inject **chính các bean Spring** vào trường `@Autowired`, không khởi tạo service bằng `new` tại nơi gọi.

`BrokenService` và `SecuredService` là class cụ thể công khai và có phương thức public, nên trong cấu hình ví dụ Spring có thể tạo class-based proxy. `AopUtils.isAopProxy(...)` chứng minh ít nhất bean đang được proxy; nó **không tự chứng minh mọi đường gọi** đều đi qua proxy. Các test còn lại xác minh hành vi đó.

### 5.3. Lệnh chạy và kết quả mong đợi

Từ thư mục chứa `build.gradle` (yêu cầu máy có Gradle tương thích và JDK 17+):

```bash
gradle test --tests demo.SelfInvocationTest
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew test --tests demo.SelfInvocationTest` trên Linux/macOS, hoặc `gradlew.bat test --tests demo.SelfInvocationTest` trên Windows.

**Kỳ vọng:** có **6 test JUnit thành công** và Gradle kết thúc `BUILD SUCCESSFUL`. Đây là kết quả **dự kiến theo cấu hình minh họa**, không phải log được sao chép từ một lần chạy thực tế. Báo cáo test HTML: `build/reports/tests/test/index.html`.

| Test | Principal | Đường gọi | Kỳ vọng |
| --- | --- | --- | --- |
| `servicesReallyAreSpringProxies` | Không cần user | Kiểm tra proxy | Cả hai service đều là AOP proxy |
| `directCallToRestrictedMethodIsDenied` | USER | Proxy → `BrokenService.adminAction` | `AccessDeniedException` |
| `selfInvocationUnexpectedlyBypassesAuthorizationAndTransaction` | USER | Proxy → `unsafeEntry` → `this.adminAction` | `"txActive=false"` — bộc lộ lỗ hổng |
| `differentBeanEnforcesAuthorization` | USER | Coordinator → proxy SecuredService | `AccessDeniedException` |
| `directAuthorizedCallStartsTransaction` | ADMIN | Proxy → SecuredService | `"txActive=true"` |
| `differentBeanStartsTransactionForAuthorizedCaller` | ADMIN | Coordinator → proxy SecuredService | `"txActive=true"` |

Lưu ý test self-invocation **cố ý khẳng định hành vi nguy hiểm** để người học quan sát được lỗi. Không áp dụng test kỳ vọng “USER lọt qua” làm yêu cầu chấp nhận sản phẩm; sau khi sửa service thật, assertion đúng phải là **USER bị từ chối** ở mọi đường vào được bảo vệ.

## 6. Vì sao phương án tách bean giải quyết được lỗi?

Phương án khuyến nghị là đặt hành động nhạy cảm ở một bean có trách nhiệm rõ ràng và để người điều phối gọi bean đó qua Spring dependency injection:

```java
@Service
public class AdminOperationService {

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void runAdminOperation() {
        // Chỉ chạy sau khi authorization được chấp nhận.
    }
}

@Service
public class OperationCoordinator {
    private final AdminOperationService adminOperationService;

    public OperationCoordinator(AdminOperationService adminOperationService) {
        this.adminOperationService = adminOperationService;
    }

    public void runWorkflow() {
        adminOperationService.runAdminOperation();
    }
}
```

Đây là **đoạn mã minh họa kiến trúc**, không phải toàn bộ ứng dụng độc lập. Khi `OperationCoordinator` là Spring bean và nhận `AdminOperationService` từ container, reference mà nó gọi là bean có thể đã được proxy. Lời gọi `runAdminOperation()` đi qua điểm chặn bảo mật và transaction.

Lợi ích thực tế:

- Ranh giới authorization trở nên rõ: mọi caller truy cập hành động nhạy cảm qua `AdminOperationService`.
- Ranh giới transaction trở nên rõ: annotation trên `runAdminOperation()` có hiệu lực khi gọi qua proxy.
- Kiểm thử có thể gọi cùng public method từ controller, coordinator hoặc một bean khác và xác nhận cùng chính sách.
- Tránh phụ thuộc cơ chế tự gọi lại proxy của cùng một class.

Nếu một workflow cần transaction **bao trùm nhiều thao tác**, bạn có thể đặt transaction trên phương thức **entry point được gọi qua proxy**, thay vì lạm dụng `REQUIRES_NEW` trên những method được gọi nội bộ. Tuy nhiên, quyết định transaction phải theo yêu cầu nhất quán dữ liệu; không tự đổi propagation chỉ để làm test pass.

## 7. Các lựa chọn thay thế và giới hạn

### 7.1. Tự inject proxy của chính bean

Có thể cấu hình reference tới chính bean/proxy và gọi qua reference đó thay vì `this`, nhưng dễ gây **circular dependency**, rối vòng đời bean, khó đọc code và rủi ro khi cấu hình thay đổi. Nếu thực sự buộc phải giữ một class, phải chứng minh reference đó là proxy đúng và có integration test cho ranh giới security/transaction. Tách bean thường đơn giản hơn.

### 7.2. `AopContext.currentProxy()`

Spring AOP có `AopContext.currentProxy()` khi proxy được cấu hình expose proxy; cách này gắn nghiệp vụ trực tiếp với AOP infrastructure, dễ lỗi nếu gọi ngoài ngữ cảnh proxy và được tài liệu Spring khuyến nghị hạn chế. Không dùng làm “fix nhanh” mặc định cho logic bảo mật.

### 7.3. AspectJ weaving

Spring Security có thể cấu hình `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)`, và Spring transaction hỗ trợ AspectJ transaction weaving. Do advice được **weave vào bytecode**, self-invocation có thể được intercept theo cách khác với proxy mode. Tuy nhiên, đó là thay đổi kiến trúc cần dependency, compiler/load-time weaving và kiểm thử riêng; chỉ đổi một annotation khi chưa cấu hình weaving đầy đủ **không đủ**. Ví dụ chính của bài này **không** dùng AspectJ.

### 7.4. JDK dynamic proxy, CGLIB, final/private

- **JDK dynamic proxy:** dùng interface để đại diện bean; thông thường chỉ những lời gọi có thể tới qua interface proxy mới được intercept.
- **Class-based proxy (CGLIB):** tạo subclass để intercept method có thể override. `final` class không thể được subclass theo cách này, `final` method không thể được override; `private` method không thể được advised bằng cơ chế proxy thông thường.
- **Self-invocation:** tồn tại với **cả** JDK proxy lẫn class-based proxy. Đổi `proxyTargetClass=true` không biến `this.someMethod()` thành một lần gọi qua proxy.
- Với method có visibility đặc biệt, interface và version framework, xác minh cách hoạt động **trên cấu hình Spring cụ thể**. An toàn nhất cho ranh giới security trong bài là dùng public method được gọi từ bean khác qua Spring proxy, và có test chặn quyền.

## 8. Những hiểu nhầm dễ gây lỗi production

**Hiểu nhầm 1: “Bean có proxy thì mọi method call đều an toàn.”** Một bean đúng là proxy không có nghĩa mọi lời gọi **từ bên trong target** đều qua proxy. Test `AopUtils.isAopProxy(...)` chỉ là điều kiện hỗ trợ; cần test đường gọi thực tế.

**Hiểu nhầm 2: “Thêm `@EnableMethodSecurity` giải quyết self-invocation.”** Annotation này bật method security advisors nhưng không thay đổi ngữ nghĩa `this.method()`. Nếu thiếu `@EnableMethodSecurity`, ngay cả direct external call qua Spring bean cũng có thể không có method security. Đó là lỗi khác, phải kiểm tra độc lập.

**Hiểu nhầm 3: “CGLIB sẽ intercept cả lời gọi nội bộ.”** Class-based proxy không giải quyết self-invocation trên target. Đừng dùng đổi proxy type như biện pháp thay thế việc tách bean.

**Hiểu nhầm 4: “Không thấy exception thì người dùng đủ quyền.”** Nếu đường gọi bỏ qua `@PreAuthorize`, không có `AccessDeniedException` dù quyền chưa từng được kiểm tra. Khi điều tra lỗi authorization, kiểm tra có đi qua proxy hay không trước khi kết luận role/SpEL sai.

**Hiểu nhầm 5: “`@Transactional(REQUIRES_NEW)` vẫn mở transaction vì có annotation.”** Với lời gọi `this.inner()`, propagation của inner method không được áp dụng. Nếu outer transaction đã tồn tại, thấy `isActualTransactionActive() == true` vẫn **không chứng minh** inner `REQUIRES_NEW` đã tạo transaction mới.

**Hiểu nhầm 6: “Chỉ cần test controller.”** Một endpoint có thể bảo vệ tốt, nhưng một code path khác gọi thẳng service theo cách khác. Service-level integration test nên kiểm tra authorization trên các đường vào thực tế và đảm bảo thao tác nhạy cảm không có đường vòng self-invocation.

## 9. Checklist kiểm tra và xử lý lỗi

Khi nghi ngờ annotation bị bỏ qua, kiểm tra theo thứ tự:

1. **Điểm bắt đầu:** object do Spring inject hay do code tạo bằng `new`? `@EnableMethodSecurity` đã bật và `@Transactional` có transaction manager hợp lệ chưa?
2. **Hình dạng lời gọi:** có `this.securedMethod()`, `securedMethod()` (implicit `this`), gọi từ constructor hoặc `@PostConstruct`, hay private helper có annotation không?
3. **Đường proxy:** `AopUtils.isAopProxy(bean)` cho kết quả gì? Dùng JDK proxy hay class proxy? Method có public/override được không?
4. **Quyền:** test trực tiếp secured method qua bean proxy bằng user thiếu quyền phải ném `AccessDeniedException`. Test đường vào workflow của cùng user cũng phải bị chặn nếu hợp đồng yêu cầu.
5. **Giao dịch:** test direct external invocation có mở transaction không? Nếu method yêu cầu `REQUIRES_NEW`, kiểm tra tính riêng biệt bằng hành vi commit/rollback, không chỉ kiểm tra boolean “đang có transaction”.
6. **Thiết kế:** chuyển hành động nhạy cảm sang bean riêng, inject và gọi qua proxy; kiểm tra lại cả hành vi hợp lệ lẫn hành vi bị từ chối.
7. **Lớp bảo vệ khác:** cần ràng buộc quyền ở service/data access theo yêu cầu; không giả định HTTP authorization hay UI ẩn nút đã bao phủ mọi code path.

Một dấu hiệu rất mạnh là **cùng một phương thức**: gọi từ bean khác thì user thiếu quyền bị chặn, nhưng gọi từ method khác trong chính class lại chạy. Khi gặp dấu hiệu này, hãy kiểm tra self-invocation trước khi thay đổi biểu thức SpEL hoặc cấu hình role.

## 10. Bài tập áp dụng

**Bài tập 1 — phát hiện bypass:** Dùng `BrokenService` ở trên, thêm phương thức `public String report() { return adminAction(); }` mà không ghi `this`. Dưới `@WithMockUser(roles = "USER")`, so sánh `brokenService.adminAction()` với `brokenService.report()`. Giải thích vì sao lời gọi thứ hai vẫn là self-invocation.

**Bài tập 2 — sửa đường vào:** Thay `BrokenService` bằng `Coordinator` và `SecuredService`. Viết test dưới role USER khẳng định **mọi đường vào được hỗ trợ** đều bị từ chối. Viết test role ADMIN khẳng định business action chạy và transaction active.

**Bài tập 3 — transaction nested:** Cho outer method có `@Transactional`, inner method có `@Transactional(propagation = REQUIRES_NEW)`; thử lời gọi `this.inner()` so với lời gọi qua bean riêng. Kiểm tra rollback/commit ở hai scope trên H2 thay vì chỉ `isActualTransactionActive()`. Dự đoán đường gọi nào thực sự có transaction độc lập.

**Bài tập 4 — method filter:** Đặt `@PostFilter("filterObject.owner == authentication.name")` trên method trả danh sách dữ liệu nhạy cảm. Viết hai test: external call qua proxy chỉ trả data của user, và self-invocation có nguy cơ trả toàn bộ; sửa bằng bean boundary rõ ràng. Không dùng ví dụ nguy hiểm làm đường xử lý production.

## 11. Tổng kết

- **Spring AOP proxy** chặn những lời gọi đi **qua proxy**; `this.method()` và `method()` gọi trên cùng target bỏ qua advice của method đích.
- Với **Spring Security Method Security**, self-invocation có thể bỏ qua `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` của method được gọi nội bộ.
- Với **`@Transactional` proxy mode**, self-invocation có thể bỏ qua cả việc mở transaction và ngữ nghĩa propagation của method bên trong; transaction bên ngoài (nếu có) vẫn là một trường hợp khác.
- Giải pháp thiết kế dễ kiểm chứng là **tách hành động nhạy cảm sang bean riêng**, inject và gọi qua Spring proxy.
- Luôn kiểm tra **hai đường gọi** với cùng principal: direct proxy invocation và workflow đi qua bean khác. Test cũng cần chứng minh đường gọi self-invocation nguy hiểm trước khi sửa để tránh sửa nhầm nguyên nhân.

## Tài liệu tham khảo

- Spring Security Reference — Method Security, advisor/proxy và AspectJ: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework Reference — AOP Proxying Mechanisms và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — `@Transactional` và các ranh giới của proxy mode: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

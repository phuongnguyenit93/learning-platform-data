# AspectJ như lựa chọn có chủ đích khi mô hình proxy không đáp ứng

## 1. Mục tiêu và vấn đề thực tế

Spring Security Method Security và quản lý giao dịch `@Transactional` thường hoạt động bằng **Spring AOP proxy**. Mô hình này phù hợp với đa số service: một bean khác gọi phương thức qua reference do Spring cung cấp, proxy chạy authorization/transaction advice, rồi mới chuyển lời gọi vào đối tượng thật.

Giới hạn xuất hiện khi một phương thức gọi phương thức khác **trên chính đối tượng đó**, ví dụ `this.restricted()`, khi cần interception trên một lớp không được gọi qua Spring proxy, hoặc khi mô hình proxy không thể đáp ứng một ràng buộc đã được chứng minh. **AspectJ weaving** là một lựa chọn có chủ đích: thay vì chỉ đặt advice lên proxy, AspectJ có thể đan (weave) advice vào bytecode của lớp đích để interception xảy ra cả trong những đường gọi nội bộ mà proxy thông thường bỏ qua.

Đây không phải lựa chọn mặc định cho tất cả ứng dụng. Weaving có chi phí về build, startup, class loader, vận hành và kiểm thử. Bài học thuộc nhóm **Proxy và giao dịch** trong Spring Security Authorization, giúp bạn đánh giá *khi nào* cần AspectJ, *cần những thành phần gì*, *kiểm chứng kết quả ra sao*, và *làm thế nào giữ chính sách bảo mật đúng sau khi chuyển*.

Kết thúc bài, bạn có thể:

1. Phân biệt **Spring AOP proxy**, **AspectJ bytecode weaving** và cú pháp pointcut AspectJ trong Spring AOP.
2. Giải thích vì sao self-invocation bỏ qua proxy; vì sao đổi JDK proxy sang CGLIB không tự giải quyết.
3. Thiết lập có chủ đích `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)` và `@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` cùng dependency, weaving và kiểm thử tương ứng.
4. So sánh **compile-time weaving (CTW)** với **load-time weaving (LTW)** và các yêu cầu vận hành.
5. Đưa ra quyết định dựa trên test và nhu cầu thực tế, bao gồm kiểm tra quyền, propagation giao dịch, annotation, startup và phiên bản bảo mật.

**Phạm vi:** Java 17+, Spring Framework 6.x, Spring Security 6.x, Spring Boot 3.x. Ví dụ tập trung vào method security/giao dịch đồng bộ ở service; không thay thế việc xác thực request hoặc bảo vệ dữ liệu tại repository.

## 2. Bản chất giới hạn của proxy

### 2.1. Lời gọi bên ngoài và self-invocation

Giả sử một service có phương thức công khai:

```java
public class PaymentService {

    public void checkout() {
        this.charge(); // Lời gọi nội bộ trên cùng target.
    }

    @PreAuthorize("hasRole('PAYMENT_ADMIN')")
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void charge() {
        // Hành động nhạy cảm.
    }
}
```

Khi một bean khác gọi `paymentService.charge()` thông qua Spring proxy, method security có thể kiểm tra role và transaction advice có thể tạo transaction theo propagation đã khai báo. Nhưng trong `checkout()`, `this.charge()` là lời gọi trực tiếp trên target: **không đi vào proxy lần nữa** cho `charge`. Vì vậy, annotation trên `charge` có thể không được thực thi ở đường gọi này.

```text
Gọi từ bean khác (proxy mode)
Controller/Coordinator -> PaymentService proxy
                         -> security / transaction advice
                         -> target.charge()

Self-invocation (proxy mode)
Controller/Coordinator -> PaymentService proxy -> target.checkout()
                                                 -> this.charge()
                                                    (bỏ qua advice cho charge)
```

Nếu `checkout()` có advisor riêng, lời gọi ban đầu vào `checkout()` qua proxy vẫn có thể được bảo vệ. Điều bị bỏ qua là **interception riêng của phương thức được gọi nội bộ**, không phải mọi cơ chế bảo vệ trong ứng dụng.

### 2.2. Tác động của từng annotation

| Annotation | Khi gọi `this.inner()` trong proxy mode | Rủi ro nếu dựa vào annotation |
| --- | --- | --- |
| `@PreAuthorize` | Interceptor trên `inner` không được kích hoạt | Thiếu quyền vẫn vào thân phương thức |
| `@PostAuthorize` | Không kiểm tra kết quả của `inner` | Kết quả nhạy cảm có thể được trả ra |
| `@PreFilter` | Không lọc phần tử đầu vào của `inner` | Batch xử lý phần tử không được phép |
| `@PostFilter` | Không lọc phần tử kết quả của `inner` | Lộ dữ liệu qua collection trả về |
| `@Transactional` | Transaction advice của `inner` không chạy | Mở transaction/rollback/propagation sai |

**Trường hợp dễ nhầm về transaction:** nếu phương thức ngoài đã chạy trong một transaction, gọi `this.inner()` có thể vẫn thấy `TransactionSynchronizationManager.isActualTransactionActive() == true`. Điều đó **không chứng minh** `@Transactional(propagation = REQUIRES_NEW)` trên `inner` có tác dụng: thao tác bên trong có thể đang chạy trong transaction của method ngoài mà không tạo transaction mới.

### 2.3. Proxy CGLIB không tự sửa được self-invocation

Spring AOP sử dụng JDK dynamic proxy (thường với interface) hoặc class-based proxy (CGLIB). Cả hai đều là **proxy**. Đổi `proxyTargetClass = true` có thể thay hình thức proxy, nhưng không biến `this.inner()` thành lời gọi **đi ra khỏi target rồi quay lại proxy**.

Tương tự, `@EnableAspectJAutoProxy` kích hoạt cách Spring diễn dịch `@Aspect` thành **Spring AOP proxies**. Nó **không tương đương** với AspectJ compiler/weaver và không tự khiến self-invocation được advise.

## 3. AspectJ weaving khác gì Spring AOP?

**Weaving** là quá trình gắn advice vào class bytecode tại thời điểm biên dịch hoặc lúc JVM tải class. Với class được weave đúng và aspect được cấu hình đúng, advice có thể áp dụng ngay tại execution join point của method, bao gồm self-invocation.

```text
Proxy mode:
Caller -> proxy(advice) -> target
                     target.outer() -> this.inner()
                                      không qua proxy

AspectJ weaving:
Caller -> lớp đã được weave
          outer() -> inner()
                     advice được gắn vào execution của inner()
```

| Tiêu chí | Spring AOP proxy | AspectJ weaving |
| --- | --- | --- |
| Cơ chế | Đặt advice ở proxy của Spring bean | Đan advice vào bytecode của class được weave |
| Self-invocation | Không intercept advice của lời gọi nội bộ | Có thể intercept khi lớp/join point/aspect được weave đúng |
| Điểm chặn | Chủ yếu method execution qua proxy | AspectJ hỗ trợ nhiều join point hơn tùy loại aspect |
| Đối tượng không phải Spring bean | Không tự được proxy | Có thể được weave, nhưng aspect bảo mật/giao dịch vẫn cần khởi tạo và dependency phù hợp |
| Thiết lập | Tương đối đơn giản qua Spring configuration | Cần CTW/LTW, aspect library, build/JVM/class loader và kiểm thử |
| Rủi ro vận hành | Self-call, final/private, reference sai | Sai phạm vi weaving, thiếu agent, class đã tải trước, toolchain/packaging khác môi trường |

**Hai ý nghĩa của “AspectJ” cần tách biệt:**

- Spring AOP có thể dùng cú pháp biểu thức **AspectJ pointcut** (chẳng hạn `execution(* com.example..*Service.*(..))`) nhưng vẫn chạy bằng **proxy**. Cú pháp này không chứng minh weaving đã xảy ra.
- Spring Security/Transaction ở **`AdviceMode.ASPECTJ`** yêu cầu AspectJ weaving thực sự, tức class mục tiêu đã được biến đổi theo advice liên quan. Chỉ có annotation cấu hình là chưa đủ.

## 4. Khi nào cân nhắc AspectJ?

Bước đầu tiên nên là xác nhận **yêu cầu không thể giải quyết hợp lý bằng thiết kế proxy bình thường**. Các lựa chọn đơn giản hơn thường có thể đáp ứng nhu cầu: tách method nhạy cảm ra bean riêng, inject bean đó vào coordinator, gọi bằng reference Spring; dùng `TransactionTemplate` khi cần ranh giới transaction tường minh; đưa điều kiện quyền vào policy/service hoặc query phù hợp.

AspectJ có cơ sở khi có **yêu cầu bắt buộc** và **bằng chứng từ kiểm thử** như:

1. Một luồng nội bộ trong cùng class phải được áp dụng advice **ngay tại method execution**, không thể tái cấu trúc ranh giới bean mà vẫn giữ được hợp đồng hệ thống.
2. Một framework bên ngoài tạo/gọi object theo cách khó đi qua Spring proxy, và tổ chức đã đánh giá đầy đủ vòng đời khởi tạo, cấu hình aspect, class loader và quyền truy cập.
3. Cần advice ở các điểm mà proxy không hỗ trợ, với scope cụ thể và kiểm thử cho chính join point đó.
4. Dự án đã có quy trình CTW/LTW ổn định, CI/CD và môi trường chạy có thể xác minh weaving, nên chi phí bổ sung được kiểm soát.

**Không đủ lý do:** “muốn nhanh hơn”, “cần sửa một self-call đơn lẻ”, “thích `@Aspect`”, hay “muốn tất cả private method tự được bảo vệ”. Weaving không tự làm quyền đúng, transaction nguyên tử, logging đủ hay dữ liệu an toàn. Nó thay đổi **cách thực thi advice**, không định nghĩa chính sách ủy quyền.

## 5. Bốn thành phần phải đi cùng nhau

### 5.1. Chọn AspectJ mode cho đúng subsystem

Trong cấu hình Spring:

```java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class AuthorizationAndTxConfig {
}
```

`@EnableMethodSecurity(mode=ASPECTJ)` yêu cầu Spring Security phát hành method-security advice theo hình thức phục vụ AspectJ weaving. `@EnableTransactionManagement(mode=ASPECTJ)` kích hoạt AspectJ transaction management. **Hai cài đặt là riêng biệt:** chuyển security sang ASPECTJ không tự chuyển transaction, và ngược lại.

Nếu chỉ cần xử lý transaction, đừng vô tình chuyển method security; chọn chế độ của từng subsystem theo mục tiêu và phạm vi đã kiểm chứng.

### 5.2. Dependency đúng chức năng

Với Spring Boot Gradle project có quản lý phiên bản dependency phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-aspects'
    implementation 'org.springframework:spring-aspects'
    runtimeOnly 'org.aspectj:aspectjweaver'
}
```

- `spring-security-aspects` chứa các aspect hỗ trợ Spring Security method authorization.
- `spring-aspects` chứa Spring Framework aspects, bao gồm `AnnotationTransactionAspect` cho `@Transactional`.
- `aspectjweaver` cung cấp công cụ weaving lúc class được tải; để chạy LTW trên JVM thông thường còn phải **kích hoạt weaver**, ví dụ `-javaagent`.

Đoạn dependencies ở đây là **một phần của build đã tồn tại**, không phải `build.gradle` độc lập. Version của `spring-security-aspects` phải đồng bộ với các module Spring Security khác, `spring-aspects` đồng bộ Spring Framework, còn AspectJ phải tương thích JDK và packaging thực tế.

### 5.3. Phải có weaving thật

Hai tuyến chính:

| Tuyến | Khi nào weave? | Thiết lập đặc trưng | Cần quan sát |
| --- | --- | --- | --- |
| **Compile-time weaving (CTW)** | Khi build class | AspectJ compiler `ajc`, aspect library, cấu hình plugin/build | Log weave, class đầu ra thực sự được biến đổi |
| **Load-time weaving (LTW)** | JVM đang tải class | `aspectjweaver` Java agent hoặc Spring LTW phù hợp class loader; cấu hình aspect | Agent có hoạt động và class mục tiêu được weave đúng lúc |

Một lệnh LTW khái niệm khi chạy Java application:

```bash
java -javaagent:/opt/aspectj/aspectjweaver.jar -jar application.jar
```

Đường dẫn agent phải trỏ tới file JAR thực tế, không phải tên dependency. Với container/CI/test, JVM ở **mỗi nơi chạy** cũng phải nhận đúng cấu hình; class loader và Spring Boot executable JAR cần được kiểm thử theo cách ứng dụng thật được triển khai. Không giả định thêm JAR vào runtime classpath là đã weave.

AspectJ dùng file `META-INF/aop.xml` để khai báo và giới hạn weaving. Các thư viện aspect có thể chứa sẵn `aop.xml`; nếu thêm tệp của ứng dụng, cần phối hợp tránh khai báo aspect lặp hoặc giới hạn nhầm class. Ví dụ cấu hình **chỉ phạm vi và log weave** cho ứng dụng package `demo`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
    "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo..*"/>
    </weaver>
</aspectj>
```

Đặt ở `src/main/resources/META-INF/aop.xml` hoặc `src/test/resources/META-INF/aop.xml` tùy phạm vi. Đây **không phải** danh sách aspect hoàn chỉnh; các aspect cần thiết phải được đăng ký/khả dụng qua thư viện `spring-security-aspects` và `spring-aspects` tương thích. Kiểm tra log thực tế: một file `aop.xml` tồn tại không chứng minh class đã được weave.

### 5.4. Phải có kiểm thử cho chính lời gọi nội bộ

Điều kiện nghiệm thu có ý nghĩa không phải “app khởi động” mà là:

- USER thiếu role bị từ chối khi gọi **trực tiếp** protected method và qua **self-invocation**.
- ADMIN được phép đi vào method theo cùng hai đường.
- Khi method được gắn `@Transactional` và được weave, transaction active đúng nơi mong đợi.
- Khi cần `REQUIRES_NEW`, có test thực sự chứng minh transaction **riêng biệt**, không chỉ boolean active.
- Tắt agent/bỏ weaving có thể làm test **self-invocation** thất bại theo cách dự đoán. Đây là bằng chứng test đủ nhạy để phát hiện cấu hình weaving bị mất.

## 6. Ví dụ Java 17+: kiểm chứng self-invocation với AspectJ LTW

Ví dụ này là một **bộ test tích hợp phụ thuộc weaving**. Nó mô tả đủ code, dependency và agent để thử trong một project riêng. Cần máy có JDK 17+, Gradle tương thích, truy cập kho dependency và `aspectjweaver` tương thích. Kết quả phía dưới là **kỳ vọng khi weaving thành công**, không phải log đã chạy.

### 6.1. Bố cục

```text
aspectj-method-security/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AspectJWeavingTest.java
    └── resources/META-INF/aop.xml
```

`settings.gradle`:

```groovy
rootProject.name = 'aspectj-method-security'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

configurations {
    aspectjAgent
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-aspects'
    implementation 'org.springframework:spring-aspects'
    runtimeOnly 'com.h2database:h2'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'

    aspectjAgent 'org.aspectj:aspectjweaver:1.9.22.1'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    doFirst {
        jvmArgs "-javaagent:${project.configurations.aspectjAgent.singleFile.absolutePath}"
    }
}
```

**Chủ ý:** dùng BOM để quản lý phiên bản Spring dependencies; Gradle chạy JVM test với AspectJ agent. `spring-boot-starter-jdbc` cùng H2 tạo transaction manager để test một transaction thật mà không cần database bên ngoài. Đây là dự án kiểm thử, không cần ứng dụng có web server hay `main()`.

Đặt `src/test/resources/META-INF/aop.xml`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
    "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo..*"/>
    </weaver>
</aspectj>
```

Tệp này chỉ giới hạn phạm vi test và bật log woven join points. Aspect definitions cần đến từ các aspect JAR đã liệt kê; khi chuyển vào application thật, kiểm tra classpath cuối cùng, các `META-INF/aop.xml` được tìm thấy và warning của AspectJ.

### 6.2. Test class đầy đủ

Tạo `src/test/java/demo/AspectJWeavingTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AspectJWeavingTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
public class AspectJWeavingTest {

    @Autowired
    GuardedService service;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity(mode = AdviceMode.ASPECTJ)
    @EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
    public static class Config {
        @Bean
        public GuardedService guardedService() {
            return new GuardedService();
        }
    }

    public static class GuardedService {

        public String internalEntry() {
            return this.restrictedAction(); // self-invocation có chủ đích
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public String restrictedAction() {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
            return active ? "AUTHORIZED_TX_ACTIVE" : "NO_TRANSACTION";
        }
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directCallRejectsUser() {
        assertThatThrownBy(service::restrictedAction)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void selfInvocationAlsoRejectsUserWhenWoven() {
        assertThatThrownBy(service::internalEntry)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directAuthorizedCallHasTransaction() {
        assertThat(service.restrictedAction())
            .isEqualTo("AUTHORIZED_TX_ACTIVE");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void internalAuthorizedCallHasTransactionWhenWoven() {
        assertThat(service.internalEntry())
            .isEqualTo("AUTHORIZED_TX_ACTIVE");
    }
}
```

Test intentionally đặt **cùng annotation trên `restrictedAction()`** và gọi nó qua **hai đường**. Nếu chỉ nhìn direct call, Spring proxy mode cũng có thể pass; test `selfInvocationAlsoRejectsUserWhenWoven` và `internalAuthorizedCallHasTransactionWhenWoven` là những ca phát hiện chính xác ảnh hưởng của weaving.

### 6.3. Chạy và đọc kết quả

Trong thư mục project:

```bash
gradle test --tests demo.AspectJWeavingTest --info
```

Nếu dùng Gradle Wrapper, chạy `./gradlew test --tests demo.AspectJWeavingTest --info` trên Linux/macOS hoặc `gradlew.bat test --tests demo.AspectJWeavingTest --info` trên Windows.

Khi cấu hình AspectJ LTW, security aspect và transaction aspect đều được áp dụng đúng, kết quả kỳ vọng là **4 test thành công**, Gradle kết thúc `BUILD SUCCESSFUL`. Những test này **không tự chứng minh** tính độc lập của `REQUIRES_NEW`; chúng chỉ chứng minh advice của method được gọi nội bộ có thể kiểm tra quyền và mở transaction khi bên ngoài chưa có transaction.

| Test | Quyền | Đường gọi | Kỳ vọng |
| --- | --- | --- | --- |
| `directCallRejectsUser` | USER | Direct vào restrictedAction | `AccessDeniedException` |
| `selfInvocationAlsoRejectsUserWhenWoven` | USER | `internalEntry() -> this.restrictedAction()` | `AccessDeniedException` |
| `directAuthorizedCallHasTransaction` | ADMIN | Direct | `AUTHORIZED_TX_ACTIVE` |
| `internalAuthorizedCallHasTransactionWhenWoven` | ADMIN | Self-invocation | `AUTHORIZED_TX_ACTIVE` |

**Kiểm tra log và bằng chứng:** Nếu class không được weave hoặc advisor bị thiếu, test self-call của USER có thể **không ném exception**, test self-call của ADMIN có thể trả `NO_TRANSACTION`. Khi đó đừng chỉ sửa expected result để test xanh: kiểm tra agent thực sự được gắn vào JVM chạy test, log woven classes, `aop.xml`, aspect dependencies, annotation trên class triển khai và transaction manager.

Nếu muốn kiểm chứng sự khác biệt với proxy mặc định, hãy chạy cùng hợp đồng trong một **cấu hình/projet thử riêng** không có weaving và dùng `@EnableMethodSecurity` cùng `@EnableTransactionManagement` mặc định. Đừng vô tình dùng song song hai chế độ cho cùng một method trong một test context, vì dễ khiến kết quả không thể quy nguyên nhân.

## 7. CTW và LTW: chọn đường triển khai

### CTW (Compile-time weaving)

AspectJ compiler `ajc` có thể weave các class trong quá trình build. Với service đã được weave từ artifact đầu ra, không cần agent để weave lại class ấy lúc runtime. Tuy nhiên, phải tích hợp AspectJ compiler/plugin vào Gradle hoặc Maven, đưa đúng aspect libraries vào cấu hình weaving và bảo đảm artifact được deploy đúng là **bản đã weave**.

Pipeline cần có bước chứng minh classes woven được đóng gói, kiểm tra build cache/incremental compile, tương thích JDK và rollback về artifact không weave khi cần. Không dùng `javac` thuần rồi tự gọi đó là CTW.

### LTW (Load-time weaving)

AspectJ agent transform class lúc JVM nạp chúng. Lợi thế là vẫn dùng Java compiler thông thường, nhưng vận hành phải kiểm soát `-javaagent`, thư mục thư viện, class loader, cơ chế nạp sớm và cấu hình `META-INF/aop.xml`. Kiểm thử không có agent có thể pass nhờ Spring proxy khác hoặc fail theo cách khó hiểu nếu không có test riêng cho self-invocation.

Spring Framework còn hỗ trợ `@EnableLoadTimeWeaving` và một số `LoadTimeWeaver` tùy môi trường. Cơ chế đó cũng cần thiết lập class loader/transformer phù hợp; **không** xem riêng `@EnableLoadTimeWeaving` là bằng chứng mọi class đã được weave.

**Thực hành vận hành:** ghi nhận log weaving ở môi trường test và staging; giới hạn phạm vi package; đánh giá thời gian khởi động; xác minh lúc chạy executable JAR, Gradle Test, container và hệ thống production đều cùng một chiến lược. Không bỏ sót test của background jobs hoặc nhiều class loader.

## 8. Những lỗi cấu hình và giới hạn cần kiểm tra

### 8.1. Chỉ có config hoặc dependency, không có weaving

`@EnableMethodSecurity(mode=ASPECTJ)` không tự biến đổi bytecode. Thiếu agent/CTW hoặc thiếu aspect library có thể khiến method security không bảo vệ đúng các đường gọi dự kiến. Nên có một test có principal thiếu quyền **phải ném `AccessDeniedException` trên self-call**.

### 8.2. Khác biệt annotation trên interface và class

AspectJ tuân theo quy tắc Java: **annotation trên interface không tự được kế thừa bởi phương thức triển khai**. Với AspectJ transaction aspect, đặt `@Transactional` trên class triển khai hoặc method triển khai. Với method security AspectJ, cũng cần kiểm tra annotation thực sự được nhận diện trên class/method được weave. Đừng chuyển từ proxy sang weaving rồi tiếp tục dựa vào annotation chỉ ở interface mà không có integration test.

### 8.3. Method private/final và phạm vi weave

AspectJ có khả năng advice những join point mà Spring proxy không intercept, nhưng điều đó phụ thuộc aspect cụ thể, pointcut, version và bytecode thực tế. Không xem một private method đã gắn `@PreAuthorize` là bảo đảm an toàn chỉ vì `mode=ASPECTJ`.

**Bằng chứng phiên bản quan trọng:** Spring đã công bố **CVE-2025-41232** liên quan `spring-security-aspects` và method-security annotation trên **private method** ở Spring Security **6.4.0 đến 6.4.5**; phiên bản 6.4.6 là bản sửa cho nhánh đó. Kiểm kê version và kiểm thử đường gọi private/đường vào thực tế trước khi áp dụng, đặc biệt khi nâng cấp giữa các nhánh. Tham khảo: https://spring.io/security/cve-2025-41232/

### 8.4. Transaction đang active không có nghĩa `REQUIRES_NEW` đã hoạt động

Để chứng minh `REQUIRES_NEW` dưới weaving, dùng test transaction thật với H2/PostgreSQL: outer transaction ghi A, inner `REQUIRES_NEW` ghi B và commit, outer rollback; xác minh B vẫn còn, A rollback. Thiết lập transaction manager, connection và ranh giới gọi thật. Chỉ kiểm tra `isActualTransactionActive()` không phát hiện việc inner đã vô tình tham gia outer transaction.

### 8.5. Advice ordering và side effect

Khi security và transaction đều apply vào một method, **thứ tự** ảnh hưởng việc có mở transaction trước khi kiểm tra quyền hay không. Tài liệu Spring Security mô tả ordering của các method interceptors; với weaving hãy quan sát đúng cấu hình thực tế. Từ chối người dùng thiếu quyền phải xảy ra **trước hành động nghiệp vụ nhạy cảm**; kiểm tra side effect và audit thay vì dựa vào giả định advice order.

### 8.6. Hiệu năng, debug và compatibility

Không được suy luận rằng AspectJ luôn nhanh hơn proxy. Weaving có thể giảm một số proxy overhead nhưng tăng chi phí build, startup và khó đọc stack trace. Cần benchmark trên dữ liệu ứng dụng, kiểm soát bản AspectJ tương thích JDK, Spring, Java agents và package layout. Cân nhắc tác động đến AOT/native image, testing tools và instrumentation agents khác; các khả năng này tùy phiên bản/runtime, không mặc định hỗ trợ trọn vẹn.

## 9. Quy trình quyết định có chủ đích

Có thể dùng chuỗi quyết định sau:

1. **Chỉ ra chính xác lỗi:** method nào, annotation nào, caller nào, principal nào, request/transaction nào, test nào đang fail?
2. **Thử thiết kế proxy chuẩn:** tách bean, inject collaborator; nếu cần transaction programmatic, cân nhắc `TransactionTemplate`. Chạy cùng bộ test qua ranh giới mới.
3. **Nếu vẫn không đáp ứng:** xác lập yêu cầu vì sao interception phải xảy ra trong class/non-proxy code path; đánh giá chi phí CTW/LTW và phiên bản thư viện.
4. **Thử nghiệm cô lập:** dùng cấu hình `ASPECTJ` cho subsystem cần thiết, aspect modules đúng phiên bản, agent/compiler được kiểm chứng, log weave và các test positive/negative.
5. **Kiểm thử đủ độ sâu:** direct call, self-call, USER/ADMIN, transaction active, `REQUIRES_NEW` rollback, private/interface annotation, side effect và đường gọi ngoài dự kiến.
6. **Chấp nhận triển khai khi có bằng chứng:** môi trường CI, staging và production nạp đúng classes woven; có kiểm soát version/CVE, startup và kế hoạch rollback.

| Tình huống | Lựa chọn nên thử đầu tiên | Khi nào AspectJ đáng cân nhắc |
| --- | --- | --- |
| Một service gọi `this.securedMethod()` | Tách method sang bean riêng, gọi qua Spring | Không thể đổi ranh giới vì hợp đồng đặc biệt |
| Cần `REQUIRES_NEW` từ logic gọi nội bộ | Tách transactional service hoặc `TransactionTemplate` | Phải weave execution join point và có test transaction riêng |
| Muốn intercept method final/private | Xác minh hợp đồng, thiết kế public service boundary | Aspect hiện hành hỗ trợ join point, version an toàn và có test trực tiếp |
| Object tạo ngoài Spring | Đưa operation cần quyền vào Spring-managed policy/service | Không kiểm soát được điểm vào bằng proxy, đã giải quyết initialization aspect |
| Chỉ muốn dùng cú pháp pointcut AspectJ | Spring AOP `@Aspect`/pointcut expression | Không cần weaving nếu chỉ quan tâm public proxy interception |
| Cần tối ưu hiệu năng | Profile, tối ưu call path/queries | Benchmark cho thấy lợi ích thực sự lớn hơn chi phí vận hành |

## 10. Checklist nghiệm thu trước khi sử dụng AspectJ ở production

- [ ] Xác định rõ **lý do kỹ thuật** không dùng được Spring proxy/bean boundary.
- [ ] Mỗi subsystem cần weaving đều có mode/dependency đúng: `spring-security-aspects` cho method security; `spring-aspects` cho transaction.
- [ ] Build hoặc JVM thực sự weave đúng class; có log/bằng chứng weave và kiểm thử self-invocation.
- [ ] `@PreAuthorize` chặn USER ở **cả direct call và internal call**, ADMIN chỉ được chạy hành động đã ủy quyền.
- [ ] `@Transactional` mở transaction đúng chỗ; `REQUIRES_NEW` được chứng minh bằng commit/rollback và transaction độc lập.
- [ ] Annotation nằm trên class/method triển khai phù hợp; không dựa mù quáng vào annotation của interface.
- [ ] Kiểm tra bản vá security, đặc biệt advisory cho private method AspectJ, và tương thích JDK/AspectJ/Spring.
- [ ] Chạy kiểm thử trên đúng cách đóng gói/khởi chạy production, quan sát class loader, agent và startup.
- [ ] Có thể rollback thay đổi weaving mà không bỏ mất chính sách quyền ở các đường gọi quan trọng.

## 11. Ghi nhớ

- **Spring AOP proxy** chỉ intercept những lời gọi đi qua proxy; `this.method()` thường bỏ qua advice trên method được gọi nội bộ.
- **AspectJ weaving** thay đổi bytecode của class, nên có thể intercept self-invocation khi *đúng aspect, đúng class và đúng cơ chế weaving* đã được thiết lập.
- **`AdviceMode.ASPECTJ` không đủ một mình**: cần aspect library, CTW/LTW và test xác thực.
- **Security và transaction là hai subsystem độc lập**. Chuyển mode và xác minh từng subsystem theo yêu cầu.
- Tách bean/transaction programmatic thường ít phức tạp hơn. Chỉ chọn weaving khi ràng buộc kỹ thuật đã được chứng minh và vận hành có thể quan sát/kiểm soát nó.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security, Integrate with AspectJ Byte-weaving: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework 6.2 — Using `@Transactional`, đặc biệt `mode = aspectj` và self-invocation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework — Using AspectJ with Spring Applications, LTW, `META-INF/aop.xml`: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Framework — AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security Advisory — CVE-2025-41232: https://spring.io/security/cve-2025-41232/

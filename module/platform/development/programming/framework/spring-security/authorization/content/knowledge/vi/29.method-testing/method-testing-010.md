# Kiểm thử self-invocation, giao dịch và tác động phụ của phương thức

> **Ngữ cảnh:** Spring Security – authorization, nhóm **Kiểm thử phương thức**. Bài thực hành tập trung vào Spring Method Security dựa trên Spring AOP proxy và giao dịch khai báo (`@Transactional`), với ví dụ Spring Boot 3.x / Spring Security 6.x, Java 17+, JUnit 5. Các chú thích trong bài liên quan đến giao dịch JDBC thông thường trên cùng luồng; cơ chế reactive/AspectJ có ranh giới khác.

## 1. Mục tiêu và câu hỏi cần chứng minh

Khi một service vừa kiểm tra quyền vừa ghi dữ liệu, phép kiểm thử chỉ xác nhận “người không có quyền nhận lỗi” là **chưa đủ**. Cần chứng minh đồng thời:

1. **Lời gọi thực sự đi qua Spring proxy.** `@PreAuthorize` phải được thực thi trước thân phương thức, kể cả khi phương thức được gọi từ service khác. Gọi `this.protectedMethod()` trong cùng bean có thể bỏ qua advice.
2. **Giao dịch thực sự được kích hoạt ở đúng ranh giới.** `@Transactional` phải có hiệu lực khi gọi qua proxy. Cần quan sát commit, rollback và, nếu dùng `REQUIRES_NEW`, tính độc lập của giao dịch con.
3. **Khi bị từ chối quyền, không có tác động nghiệp vụ không mong muốn.** Kiểm tra số bản ghi, lần gọi repository, sự kiện/notification, chứ không chỉ loại exception.
4. **Rollback có phạm vi giới hạn.** Database có thể rollback trong khi email, HTTP request, message gửi ra hệ thống ngoài hoặc thay đổi bộ nhớ vẫn đã xảy ra.
5. **Test không vô tình che giấu lỗi.** Test tự gắn `@Transactional` có thể tạo sẵn giao dịch, làm kết quả khác với lời gọi service ngoài đời thực.

Điểm phân biệt quan trọng: **bị từ chối truy cập**, **thất bại nghiệp vụ**, **rollback của CSDL** và **đã phát tác động bên ngoài** là bốn quan sát riêng, cần assertion riêng.

## 2. Cơ chế gốc: proxy, method security và transaction

### 2.1. Một lời gọi qua proxy và một lời gọi qua `this`

Khi bật `@EnableMethodSecurity`, Spring Security đăng ký các interceptor của Spring AOP. Ví dụ `@PreAuthorize("hasRole('ADMIN')")` yêu cầu authority `ROLE_ADMIN`. Khi caller giữ tham chiếu đến bean do Spring quản lý, đường đi khái quát là:

```text
Caller
  │
  ▼
Spring proxy  ──► kiểm tra @PreAuthorize ──► transaction advice (nếu có)
  │                                            │
  └────────────────────────────────────────────▼
                                     thân phương thức đích
                                              │
                                              ▼
                                   JDBC / repository / notification
```

Hình trên chỉ minh họa hai lớp advice, **không quy định cứng thứ tự advice**. Thứ tự cụ thể phụ thuộc advisor/order và cấu hình. Kiểm tra trước `@PreAuthorize` diễn ra trước khi cho phép thân phương thức chạy; `@PostAuthorize` đánh giá sau khi thân phương thức tạo ra kết quả.

Vấn đề self-invocation:

```java
@Service
public class WrongService {
    public void start() {
        this.adminOperation(); // gọi trên target, không đi qua proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void adminOperation() {
        // Một lời gọi từ start() có thể bỏ qua cả security và transaction advice.
    }
}
```

- `caller -> wrongService.adminOperation()` qua Spring bean proxy: security và transaction advice có cơ hội chạy.
- `caller -> wrongService.start() -> this.adminOperation()`: lời gọi bên trong target **không đi lại qua proxy**, nên advice gắn *riêng* với `adminOperation()` không chạy.
- Nếu `start()` đã được gọi qua proxy và đã mở một giao dịch, mã bên trong `adminOperation()` vẫn có thể dùng giao dịch **đang tồn tại**. Nhưng annotation riêng của `adminOperation()` (chẳng hạn `REQUIRES_NEW`, isolation, rollback rule) vẫn không được áp dụng do self-invocation. Không kết luận “self-invocation luôn không có transaction” khi có transaction bao ngoài.
- Proxy class-based (CGLIB) không tự khắc phục self-invocation; private/final và lời gọi trong quá trình khởi tạo bean còn có giới hạn interception. AspectJ weaving là cơ chế khác và phải được cấu hình rõ ràng.

**Ưu tiên khắc phục:** tách phương thức cần bảo vệ sang **bean Spring khác** và inject bean đó vào facade. Có thể dùng self-injection hoặc `AopContext.currentProxy()` trong những trường hợp đặc biệt, nhưng cách này tăng kết dính vào Spring AOP; không nên là lựa chọn mặc định.

### 2.2. Phối hợp quyền và transaction

- `@PreAuthorize`: nếu không đủ quyền, thân phương thức không chạy; phù hợp để chặn thao tác ghi **trước** tác động phụ.
- `@PostAuthorize`: kiểm tra dựa trên kết quả sau khi thân phương thức đã chạy. Với phương thức ghi, dữ liệu/sự kiện **có thể đã thay đổi** trước lúc bị từ chối; thứ tự advisor và việc commit có thể làm tình hình nghiêm trọng hơn. Không dùng `@PostAuthorize` như chốt chặn duy nhất cho write.
- `@Transactional` mặc định dùng propagation `REQUIRED`: tham gia giao dịch hiện hữu, hoặc tạo giao dịch mới nếu chưa có. Mặc định `RuntimeException`/`Error` gây rollback; checked exception thông thường **không** gây rollback nếu không đặt `rollbackFor`. Cách xử lý exception (ví dụ bắt rồi nuốt exception) cũng ảnh hưởng kết quả.
- `REQUIRES_NEW` tạo transaction vật lý độc lập **khi advice thực sự được kích hoạt qua proxy**; transaction này có thể commit dù transaction bên ngoài rollback. Đây là ngữ nghĩa giao dịch, không phải biện pháp xác thực quyền.

Ví dụ cần tránh trong luồng ghi (đoạn minh họa, không phải chương trình độc lập):

```java
@PostAuthorize("returnObject.owner().equals(authentication.name)")
@Transactional
public Receipt createOrder(OrderRequest request) {
    orderRepository.save(/* order */);
    paymentGateway.charge(/* payment */);
    return /* receipt */;
}
```

Nếu điều kiện `@PostAuthorize` thất bại, phương thức đã gọi database và cổng thanh toán. Không được suy luận việc trả `AccessDeniedException` đồng nghĩa mọi thay đổi đã bị đảo ngược. Hãy kiểm tra owner/permission **trước khi ghi** (ví dụ `@PreAuthorize` hoặc kiểm tra trên bean bảo vệ) và thiết kế riêng cơ chế bù trừ/tin cậy cho hệ thống ngoài.

## 3. Ma trận kiểm thử tối thiểu

| Tình huống | Điểm gọi | Kết quả cần assert |
| --- | --- | --- |
| USER gọi trực tiếp phương thức `@PreAuthorize("hasRole('ADMIN')")` | Proxy | `AccessDeniedException`; DB và notification không đổi |
| USER gọi phương thức đó qua `this` cùng bean | Self-invocation | Chứng minh lỗ hổng: thân phương thức **vẫn chạy**; advice bảo vệ bị bỏ qua |
| USER gọi facade chuyển tiếp sang **bean được bảo vệ khác** | Qua proxy của bean thứ hai | Bị từ chối; DB và notification vẫn nguyên |
| ADMIN gọi thành công | Qua proxy | Có transaction và dữ liệu commit |
| ADMIN ghi DB rồi ném `RuntimeException` | Qua proxy | DB rollback |
| ADMIN ghi DB, gửi notification, rồi ném lỗi | Qua proxy | DB rollback **nhưng** notification không tự thu hồi |
| Code sử dụng `@PostAuthorize` để bảo vệ write | Qua proxy | Xác minh side effect **trước** kết quả deny; tránh coi deny là bảo đảm rollback |

Ma trận là đặc tả hành vi. Test kiểu unit gọi `new Service()` hoặc dùng `@InjectMocks` trực tiếp sẽ không dựng AOP proxy, vì vậy không đủ để chứng minh `@PreAuthorize`/`@Transactional` thực sự hoạt động.

## 4. Bộ integration test Java 17+ có thể chạy

Ví dụ sau dùng **H2 + JdbcTemplate thật**, một notification gateway giả đếm số lần gửi (mô phỏng tác động bên ngoài giao dịch), và `@WithMockUser` từ Spring Security Test. Mỗi phép thử gọi **Spring bean đã inject**, không tự tạo service bằng `new`.

Trong module Gradle Spring Boot 3.x có quản lý dependency versions, thêm các dependency test cần thiết (nếu dependency nào đã có, không cần khai báo lặp):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo **một file đầy đủ** `src/test/java/example/security/MethodSecurityTransactionTest.java`:

```java
package example.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = MethodSecurityTransactionTest.TestApp.class)
class MethodSecurityTransactionTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @EnableTransactionManagement
    @Import({
        VulnerableService.class,
        ProtectedService.class,
        SafeFacade.class,
        NotificationGateway.class
    })
    static class TestApp {
        // DataSource/JdbcTemplate/transaction manager lấy từ Spring Boot
        // auto-configuration với H2 hiện diện trên test runtime classpath.
    }

    @Autowired JdbcTemplate jdbc;
    @Autowired VulnerableService vulnerable;
    @Autowired SafeFacade safeFacade;
    @Autowired NotificationGateway notifications;

    @BeforeEach
    void reset() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                label VARCHAR(80) NOT NULL
            )
            """);
        jdbc.update("DELETE FROM audit_log");
        notifications.reset();
    }

    private int rowCount() {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_log", Integer.class);
    }

    // Trường hợp lỗi: cùng bean gọi this.guardedWrite().
    public static class VulnerableService {
        private final JdbcTemplate jdbc;

        public VulnerableService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public boolean invokeInternally() {
            return this.guardedWrite(); // BỎ QUA proxy của guardedWrite()
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public boolean guardedWrite() {
            boolean txActive =
                TransactionSynchronizationManager.isActualTransactionActive();
            jdbc.update(
                "INSERT INTO audit_log(label) VALUES (?)", "vulnerable");
            return txActive;
        }
    }

    // Gateway giả: số lần gửi KHÔNG thuộc giao dịch H2.
    public static class NotificationGateway {
        private final AtomicInteger sent = new AtomicInteger();

        public void send() {
            sent.incrementAndGet();
        }

        public int count() {
            return sent.get();
        }

        public void reset() {
            sent.set(0);
        }
    }

    // Bean riêng: caller phải đi qua proxy của ProtectedService.
    public static class ProtectedService {
        private final JdbcTemplate jdbc;
        private final NotificationGateway notifications;

        public ProtectedService(
            JdbcTemplate jdbc, NotificationGateway notifications) {
            this.jdbc = jdbc;
            this.notifications = notifications;
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public boolean writeAndNotify(boolean failAfterNotify) {
            boolean txActive =
                TransactionSynchronizationManager.isActualTransactionActive();

            jdbc.update(
                "INSERT INTO audit_log(label) VALUES (?)", "protected");
            notifications.send();

            if (failAfterNotify) {
                throw new IllegalStateException("business failure");
            }
            return txActive;
        }
    }

    public static class SafeFacade {
        private final ProtectedService protectedService;

        public SafeFacade(ProtectedService protectedService) {
            this.protectedService = protectedService;
        }

        public boolean execute(boolean fail) {
            return protectedService.writeAndNotify(fail);
        }
    }

    @Test
    @WithMockUser(roles = "USER")
    void selfInvocationBypassesMethodSecurityAndTransactionAdvice() {
        // Gọi thẳng bean proxy: USER bị chặn.
        assertThrows(
            AccessDeniedException.class, vulnerable::guardedWrite);
        assertEquals(0, rowCount());

        // Gọi qua this trong cùng bean: đây là bằng chứng của lỗi thiết kế.
        boolean txActive = vulnerable.invokeInternally();
        assertFalse(txActive);        // Không có transaction bao ngoài.
        assertEquals(1, rowCount()); // USER vẫn ghi được dữ liệu!
    }

    @Test
    @WithMockUser(roles = "USER")
    void separateProtectedBeanRejectsUnauthorizedWrite() {
        assertThrows(AccessDeniedException.class,
            () -> safeFacade.execute(false));
        assertEquals(0, rowCount());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void authorizedWriteCommits() {
        assertTrue(safeFacade.execute(false)); // Có transaction trong service.
        assertEquals(1, rowCount());           // Đọc sau khi method return.
        assertEquals(1, notifications.count());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void runtimeFailureRollsBackDbButNotExternalNotification() {
        assertThrows(IllegalStateException.class,
            () -> safeFacade.execute(true));
        assertEquals(0, rowCount());          // INSERT đã rollback.
        assertEquals(1, notifications.count()); // "Gửi" vẫn đã xảy ra.
    }
}
```

Chạy trong module chứa test (ví dụ khi đứng ở thư mục project Gradle tương ứng):

```bash
./gradlew test --tests "example.security.MethodSecurityTransactionTest"
```

Trên Windows dùng `gradlew.bat` với cùng đối số; trong multi-project Gradle có thể cần chỉ rõ task `:module-path:test`. Kết quả mong đợi: **4 test PASS** nếu có Spring Boot 3.x, starter JDBC/Security, H2 và JUnit Platform như cấu hình trên. Không có stdout cố định; JUnit/Gradle báo kết quả chạy test, còn assertion là nguồn xác minh hành vi.

### 4.1. Tại sao các assertion này có ý nghĩa?

**Test self-invocation:** cùng một USER bị từ chối khi gọi `vulnerable.guardedWrite()` nhưng ghi được DB qua `vulnerable.invokeInternally()`. Giá trị `false` của `isActualTransactionActive()` chỉ có ý nghĩa vì test này **không có giao dịch bao ngoài**. H2 JDBC ngoài transaction có thể tự commit thao tác INSERT. Đây là một test cố tình phơi bày lỗ hổng; sự “PASS” của nó **không có nghĩa implementation sai là an toàn**.

**Test tách bean:** `SafeFacade` giữ tham chiếu `ProtectedService` do Spring inject; lời gọi `protectedService.writeAndNotify()` qua proxy nên USER bị chặn **trước INSERT và send**.

**Test commit:** nếu chạy từ lời gọi ngoài transaction, `@Transactional` bao bọc thao tác; sau khi phương thức trả về, đọc DB thấy bản ghi là quan sát commit thực tế (không chỉ trạng thái trong persistence context).

**Test rollback và side effect:** `IllegalStateException` là unchecked exception, khiến giao dịch JDBC rollback; `AtomicInteger` của gateway đã tăng bên ngoài tài nguyên giao dịch nên không quay về 0. Thay gateway giả bằng HTTP/email/message broker thật sẽ cần cách xác minh và cleanup phù hợp.

## 5. Mở rộng: các ca đặc biệt dễ bỏ sót

### 5.1. Self-invocation với `REQUIRES_NEW` và transaction bao ngoài

Xét đoạn minh họa (chưa phải file Java chạy riêng):

```java
@Transactional
public void outer() {
    this.writeInNewTransaction(); // không qua proxy
    throw new IllegalStateException("outer failed");
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeInNewTransaction() {
    repository.save(/* audit */);
}
```

Nếu `outer()` đi qua proxy, transaction bao ngoài có hiệu lực, nhưng lời gọi `this.writeInNewTransaction()` không tạo transaction `REQUIRES_NEW` riêng; ghi audit vẫn tham gia transaction hiện hữu và có thể rollback cùng outer. Nếu chuyển `writeInNewTransaction` sang bean riêng rồi gọi qua proxy, transaction mới có thể commit độc lập khi outer rollback. **Bộ test đúng** xác nhận trạng thái DB **sau khi outer kết thúc**, với kỳ vọng rõ ràng cho từng thiết kế; không chỉ assert `TransactionSynchronizationManager.isActualTransactionActive() == true` vì cả giao dịch cũ và mới đều trả `true`.

Cần cân nhắc thêm rủi ro pool connection khi dùng `REQUIRES_NEW` trong khi outer đang giữ connection. Không nên dùng `REQUIRES_NEW` chỉ để “cứu” một lỗi self-invocation hoặc bỏ qua policy quyền.

### 5.2. Lỗi bị bắt rồi nuốt và loại exception

```java
@Transactional
public void saveWithCatch() {
    repository.save(/* entity */);
    try {
        remoteGateway.call();
    } catch (RuntimeException ex) {
        log.warn("Call failed", ex);
        // Trả về bình thường: transaction advice có thể commit DB.
    }
}
```

Nếu nghiệp vụ yêu cầu toàn bộ DB phải rollback khi remote call lỗi, test cần ném lại exception, đánh dấu rollback-only có chủ đích, hoặc thiết kế lại workflow. Với checked exception, mặc định `@Transactional` không rollback trừ khi khai báo `rollbackFor` phù hợp. Cần test rõ: **exception loại nào, có đi ra ngoài transaction boundary không, DB còn dữ liệu không?**

### 5.3. `@PostAuthorize` sau khi đã ghi

`@PostAuthorize` dùng tốt cho kết quả **đọc** (ví dụ quyền xem đối tượng do mình sở hữu). Với write, post-check có thể xảy ra sau side effect và có thể sau commit, phụ thuộc thứ tự advice. Hãy kiểm thử bằng một thao tác ghi giả có counter: gọi với USER không đủ quyền, assert exception **và** đọc lại counter/DB. Nếu counter tăng hoặc DB còn bản ghi, test đã chứng minh deny không bảo vệ tính nguyên tử. Thiết kế lại bằng quyền ở *trước* thao tác và ưu tiên tách read/authorize/write theo yêu cầu domain.

### 5.4. DB rollback không thu hồi email, HTTP, queue hoặc file

- **Email/HTTP call:** đã gửi thì rollback CSDL không thể thu hồi; dùng fake/mock để đếm số lần, với integration test có thể dùng test server và kiểm tra request.
- **Message broker:** “send đã được gọi” khác với “broker đã xác nhận” và khác với “consumer đã xử lý”; cần assertion theo mức bảo đảm mong muốn.
- **File, cache, memory:** cần hoàn tác/đồng bộ riêng; `@Transactional` JDBC không quản lý mặc định.
- **`@TransactionalEventListener(phase = AFTER_COMMIT)`:** listener chỉ được kích hoạt sau commit thành công khi có transaction phù hợp; test nên xác nhận “rollback thì listener không chạy”, “commit thì chạy”. Nếu không có transaction, listener mặc định không chạy (trừ cấu hình fallback). AFTER_COMMIT giúp tránh gửi trước rollback nhưng **không bảo đảm** giao hàng tin cậy khi process chết giữa commit và gửi.
- **Transactional outbox:** ghi cả dữ liệu nghiệp vụ và một row outbox trong **cùng** DB transaction, rồi worker riêng gửi sự kiện; thường cần retry, idempotency, deduplication. Test phải chứng minh rollback không còn outbox row và commit để lại outbox row, sau đó mới kiểm thử bước phát tin.

### 5.5. Đừng để test-managed transaction tạo kết quả giả

`@Transactional` trên phương thức test của Spring Test thường mở một **test-managed transaction** và tự rollback sau test. Điều này có thể che lỗi “service không tự mở transaction”, vì service vẫn chạy trong transaction do test tạo. Cũng dễ nhầm một INSERT nhìn thấy **trong** test với dữ liệu đã commit.

Với test cần khẳng định commit/rollback của **service**, như ví dụ ở mục 4:

1. **Không** đặt `@Transactional` lên test/test class.
2. Dọn dữ liệu trong `@BeforeEach` rồi gọi bean thật từ một luồng bình thường.
3. Assert trạng thái DB **sau khi** lời gọi service đã trả về hoặc ném exception.
4. Nếu buộc dùng test-managed transaction, cân nhắc `TestTransaction.flagForCommit()/flagForRollback()` và `TestTransaction.end()`, xác nhận dữ liệu từ transaction/connection riêng, và hiểu rõ propagation.
5. Với JPA, `flush()` và có thể `clear()` trước truy vấn xác minh để tránh chỉ đọc state đang đệm; flush **không đồng nghĩa** đã commit.

Các timeout chạy đoạn test trên luồng khác và mã bất đồng bộ cũng có thể vượt ranh giới transaction/thread-local hoặc SecurityContext của test. Cần test tích hợp riêng cho async; không ngoại suy kết quả từ test đồng bộ trên một luồng.

## 6. Những lỗi test thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có khả năng | Cách kiểm tra/sửa |
| --- | --- | --- |
| USER vẫn thực thi method gắn `@PreAuthorize` | Gọi `this.method()`, tạo bean thủ công, method không intercept được, chưa bật method security | Kiểm tra `@EnableMethodSecurity`, Spring bean đã inject, đường gọi qua proxy; tách bean |
| Lời gọi `@Transactional` nhưng không mở transaction mới | Self-invocation; có transaction bao ngoài; phương thức/bean không được advice | Test khi không có transaction test; assert commit/rollback; kiểm tra propagation và lời gọi qua proxy |
| Test luôn rollback dù service không có `@Transactional` | `@Transactional` trên test | Bỏ annotation khỏi test xác minh transaction boundary; dùng `TestTransaction` nếu cần |
| `assertThrows` PASS nhưng vẫn có dữ liệu/notification | `@PostAuthorize` kiểm tra sau side effect; transaction/order/ngoại lệ không đúng | Assert thêm trạng thái DB và side effects, chuyển check về trước write |
| `verify(repository).save()` PASS nhưng DB không commit | Mock không chứng minh transaction hoặc flush/commit | Kiểm thử JDBC/JPA với database thật và dữ liệu sau lời gọi |
| Có rollback DB nhưng đã gửi email/message | Tài nguyên ngoài không cùng transaction | AFTER_COMMIT hoặc outbox/idempotency; kiểm tra cả DB lẫn outbound effect |
| Giao dịch không rollback khi có lỗi | Checked exception; bị bắt rồi nuốt; nested `REQUIRES_NEW` đã commit | Test rollback rule, exception propagation và boundaries thật |

Một `AccessDeniedException` khi gọi service trực tiếp **không tự trở thành HTTP 403**; ánh xạ 403 là trách nhiệm của web/security filter hoặc exception handling ở ranh giới HTTP. Bài này kiểm thử method layer; nếu cần hợp đồng HTTP, bổ sung `MockMvc`/request test riêng. Ngoài ra, `@WithMockUser` cung cấp danh tính/authorities giả, không kiểm thử JWT/session/identity provider thực.

## 7. Checklist nghiệm thu bài thực hành

- [ ] Bật method security và transaction management; dùng **Spring-injected bean**, không gọi `new` đối với đối tượng cần AOP.
- [ ] Có ca **direct call qua proxy** bị deny, và ca **self-invocation** chứng minh vì sao đường đi bên trong có vấn đề.
- [ ] Sau khi refactor thành hai bean, USER bị deny và **không có ghi DB/notification**.
- [ ] ADMIN thành công: kiểm chứng dữ liệu **sau khi service return** và transaction active trong lúc service chạy.
- [ ] Exception runtime: DB rollback, đồng thời ghi rõ tác động ngoài DB còn hay mất.
- [ ] Khi dùng `REQUIRES_NEW`, kiểm tra commit độc lập bằng dữ liệu sau khi outer kết thúc, không dựa riêng vào cờ “đang có transaction”.
- [ ] Nếu dùng `@PostAuthorize`, tuyệt đối không mặc định deny bảo vệ write; kiểm tra thứ tự và side effects.
- [ ] Test phục vụ xác minh transaction boundary không tự mang `@Transactional`; mọi exception, mock và lifecycle đều được kiểm soát.

## Tài liệu chính thống

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` và interceptor.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, test context.
- [Spring Framework – AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): vì sao self-invocation bỏ qua advice và lựa chọn khắc phục.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, transaction defaults và rollback rule.
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback trong test, `TestTransaction` và lỗi false positive.
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và `AFTER_COMMIT`.

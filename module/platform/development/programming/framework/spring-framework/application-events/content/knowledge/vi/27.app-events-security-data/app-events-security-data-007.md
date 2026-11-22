# Kiểm soát listener của thư viện bên thứ ba trong Spring Application Events

## 1. Vấn đề bảo mật khi ứng dụng tích hợp thư viện có listener

Spring Application Events cho phép code phát sự kiện qua `ApplicationEventPublisher.publishEvent(...)` và các listener phù hợp phản ứng mà producer không cần biết danh sách consumer. Một thư viện hoặc Spring Boot starter có thể cung cấp bean triển khai `ApplicationListener<?>`, method `@EventListener` hoặc cơ chế đăng ký listener bằng code. Nếu được đăng ký vào đúng `ApplicationContext`, listener ấy có thể thấy event mà nó quan tâm.

Điều này rất thuận tiện cho audit, logging, monitoring, caching, analytics và integration. Nhưng với hệ thống chứa dữ liệu nhạy cảm, cần hỏi:

- Thư viện có thật sự cần nhận event này không?
- Event payload chứa những gì: email, số điện thoại, token, thông tin thanh toán, `Authentication`, JPA entity, request hoặc dữ liệu tenant?
- Listener được đăng ký từ đâu: `@ComponentScan`, `@Import`, auto-configuration, hay `SpringApplication.addListeners(...)`?
- Thư viện có thể ghi log, gọi API ngoài hoặc phát sự kiện con không?
- Nếu listener chậm hoặc ném exception, request/transaction nguồn có bị ảnh hưởng không?
- Nếu cập nhật phiên bản starter, có listener mới tự xuất hiện không?
- Có cách tắt đúng listener trước khi ứng dụng hoạt động và kiểm thử việc tắt không?

Ví dụ luồng rủi ro:

~~~text
OrderService
    |
    +-- publish(OrderPlaced)
                  |
                  +-- InternalAuditListener          (nội bộ)
                  +-- SearchProjectionListener       (nội bộ)
                  +-- VendorAnalyticsListener        (thư viện bên thứ ba)
                  +-- LibraryTelemetryListener       (thư viện khác)
~~~

Nếu `OrderPlaced` chứa cả một object `Customer` có địa chỉ, email và thông tin riêng tư, các listener phù hợp có thể tiếp cận dữ liệu đó. Điều này **không chứng minh** vendor chắc chắn làm rò rỉ dữ liệu, nhưng đủ để cần kiểm soát **data flow** và quyền của integration.

**Nguyên tắc quan trọng:** Spring `ApplicationEventPublisher` **không phải cơ chế phân quyền hoặc sandbox**. Listener trong cùng JVM là code đang chạy trong cùng process, có thể có những con đường truy cập dữ liệu khác ngoài việc lắng nghe event. Việc tắt một listener hay lọc event chỉ là kiểm soát hành vi cụ thể, **không bảo đảm cô lập mã không đáng tin**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện các cơ chế thư viện dùng để đăng ký `ApplicationListener` và `@EventListener`.
2. Phân biệt có class trên classpath với có listener thật sự hoạt động trong context.
3. Dùng explicit registration, phạm vi component scan, conditional configuration và exclude auto-config đúng cách.
4. Thiết kế event DTO bất biến, tối thiểu và có phân loại dữ liệu.
5. Phân biệt event routing, `@Order`, `@EventListener(condition)` với authorization thực sự.
6. Phát hiện listener bên thứ ba có thể ảnh hưởng transaction, latency và side effect.
7. Kiểm thử Spring context thật với listener vendor bật/tắt và payload không chứa dữ liệu nhạy cảm.
8. Đưa integration ra gateway/service riêng khi cần ranh giới tin cậy mạnh hơn.

## 2. Spring xác định listener như thế nào?

Trong `ApplicationContext`, `ApplicationEventMulticaster` lựa chọn listener dựa trên event type và metadata phù hợp. `SimpleApplicationEventMulticaster` mặc định thường gọi listener trên **thread của publisher**. Một listener có thể thuộc các dạng:

~~~java
// Mã minh họa, cần type/import thật.
public class VendorApplicationListener
        implements ApplicationListener<SomeApplicationEvent> {

    @Override
    public void onApplicationEvent(SomeApplicationEvent event) {
        // Xử lý event.
    }
}
~~~

Hoặc:

~~~java
// Mã minh họa trong một Spring-managed bean.
@Component
public class VendorAnnotatedListener {

    @EventListener
    public void on(AccountLifecycleNotice notice) {
        // Xử lý notice.
    }
}
~~~

Với hình thức thứ hai, Spring dùng `EventListenerMethodProcessor` để tìm method có `@EventListener` trên bean được quản lý và đăng ký listener adapter. Vì vậy **không thể kiểm kê tất cả listener chỉ bằng việc đếm bean extends/implements ApplicationListener**.

Spring cũng hỗ trợ phát event POJO/record; object có thể được bọc trong `PayloadApplicationEvent<?>` khi xử lý. Không nên chỉ tìm những class extends `ApplicationEvent` khi rà soát dữ liệu được phát.

### 2.1. Những con đường đăng ký có thể xuất hiện

| Con đường | Cách hoạt động | Điểm kiểm soát |
| --- | --- | --- |
| `@ComponentScan` | Bean `@Component` trong package được scan | Giới hạn package/filter |
| `@Bean` | `@Configuration` của app/vendor tạo listener | Chỉ import config đã duyệt |
| `@Import` | Import vendor configuration | Review điểm import |
| Spring Boot auto-configuration | Starter tự cung cấp config khi condition phù hợp | Property và exclude auto-config |
| Programmatic | `context.addApplicationListener(...)` | Review code bootstrap/plugin loader |
| Boot early listener | `SpringApplication.addListeners(...)` hoặc `spring.factories` | Review startup registration |
| Framework/plugin manager | Tự tạo bean hoặc gắn listener theo lifecycle riêng | Có owner và policy rõ |

**Một JAR được thêm vào dependency không mặc nhiên kích hoạt tất cả listener trong JAR.** Phải có đường registration. Ngược lại, một starter có thể tự cấu hình listener mà application code không hề gọi trực tiếp nó.

### 2.2. Type matching không phải kiểm tra quyền

`@EventListener` có thể khai báo event class hoặc điều kiện `condition`. Nó giúp framework chọn method có tham gia dispatch hay không, **không áp đặt ACL cho listener khác**.

Ví dụ một method `@EventListener(condition = "...")` không ngăn một listener khác đăng ký nhận cùng event. `@Order` thay đổi thứ tự thực thi trong những điều kiện tương ứng, chứ không làm payload “bí mật” trước listener chạy sau.

Nếu một event chứa token, việc tạo một internal listener `@Order(0)` để “xóa token trước” cũng không phải thiết kế bảo mật đáng tin: object có thể shared/mutable, listener khác vẫn có thể được gọi, và order không phải data access policy.

## 3. Phân loại rủi ro theo confidentiality, integrity, availability

| Loại rủi ro | Tình huống | Giảm thiểu |
| --- | --- | --- |
| Confidentiality | Vendor listener nhận PII, token hoặc thông tin nội bộ | Không publish dữ liệu không cần thiết; outbound gateway có allowlist |
| Integrity | Listener ghi sai trạng thái hoặc publish fact giả | Giới hạn quyền, xác thực command, idempotency |
| Availability | Listener đồng bộ gọi HTTP chậm/ném lỗi | Timeout, retry policy, bulkhead, quản lý exception |
| Data governance | Log/export/event history giữ dữ liệu quá lâu | Retention, audit, DLP và review dữ liệu |
| Supply chain | Upgrade thêm listener/exporter mới | SBOM, scan, pin version, integration tests |

Có ít nhất hai **mô hình tin cậy** khác nhau:

- **Thư viện được tin cậy, nhưng chức năng listener là tùy chọn:** có thể dùng feature flag, config opt-in/opt-out và kiểm thử.
- **Thư viện/mã không đáng tin hoặc có nguy cơ bị compromise:** một feature flag trên listener **không tạo security boundary**. Cần đánh giá việc chạy code trong cùng process, giới hạn secrets/OS/network permissions hoặc đưa nó ra process/service cô lập.

### 3.1. Threat model trước khi tích hợp

Hỏi rõ:

1. Ai sở hữu thư viện, cách cập nhật và xác thực artifact thế nào?
2. Các bean của thư viện có thể inject `ApplicationContext`, `Environment`, `DataSource`, client nội bộ hoặc credential không?
3. Có outbound network access không; đích nào được phép?
4. Vendor cần dữ liệu gì, được retention bao lâu và có yêu cầu consent/hợp đồng xử lý dữ liệu không?
5. Có nguy cơ truy xuất xuyên tenant bằng ID trong event không?
6. Khi event bị ghi vào logs/traces/outbox/broker, có tạo thêm bản sao PII không?
7. Có thể thay integration bằng API nhận DTO tối giản ở một service riêng không?

Nếu code vendor thực sự có thể chạy lệnh tùy ý với quyền của ứng dụng, **chặn đường event không đủ để chống truy cập tài nguyên khác**. Đây là giới hạn phải trình bày minh bạch khi review bảo mật.

## 4. Kiểm kê listener trước khi tắt hoặc giới hạn

Đừng cố tắt thứ mình chưa xác định. Quy trình kiểm kê hữu ích:

1. Xác định starter/JAR, version và dependency tree.
2. Rà soát `@EventListener`, `ApplicationListener`, `@Configuration`, `@Import`, `@AutoConfiguration` của vendor.
3. Kiểm tra `@ComponentScan` có quét cả package vendor ngoài ý định không.
4. Xem metadata auto-config của Boot (đối với Boot 3.x là `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`).
5. Xem code dùng `addApplicationListener` hoặc factory registration khi bootstrap.
6. Chạy context test để biết bean vendor có thực sự tồn tại và listener có được gọi với event quan tâm.
7. Rà soát outbound calls/logging của listener đó, không chỉ annotation.
8. So sánh trước/sau mỗi lần upgrade vendor library.

### 4.1. Tại sao đếm ApplicationListener bean là chưa đủ?

~~~java
// Snippet minh họa: chỉ là một nguồn dữ liệu để inventory.
Map<String, ApplicationListener> beans =
    context.getBeansOfType(ApplicationListener.class);
~~~

Code trên cần biến `context` và import phù hợp. Nó chỉ nhìn thấy những bean có kiểu `ApplicationListener` mà container trả về, **không nhất thiết có cả các listener adapter từ method `@EventListener`**. Kết hợp source review, bean config, integration test và instrumentation để có inventory đáng tin.

### 4.2. Spring Boot condition report và Actuator

Với Spring Boot, có thể xem condition evaluation report khi bật diagnostic `--debug` phù hợp. Nếu có Actuator, endpoint `/actuator/beans` và `/actuator/conditions` giúp hiểu bean/auto-config đang tồn tại.

Không mở các endpoint này công khai: chúng có thể tiết lộ cấu trúc nội bộ. Chỉ truy cập bằng cơ chế bảo vệ thích hợp; cũng cần tránh in secrets khi bật debug logs.

### 4.3. Không kết luận từ tên class

Một vendor có class `VendorAnalyticsListener` nhưng không được đăng ký thì không phải listener đang hoạt động. Ngược lại, một class có tên chung `StarterConfiguration` có thể tạo nhiều bean listener khác. Hãy bám theo dependency graph và cơ chế registration thực tế.

## 5. Ưu tiên không đăng ký listener không cần thiết

Cách kiểm soát sạch nhất là **không tạo bean/listener** nếu tính năng chưa được phép.

Tránh mở component scan quá rộng:

~~~java
// Snippet ví dụ: có thể vô ý scan toàn bộ component vendor.
@ComponentScan(basePackages = {
    "com.example.application",
    "com.vendor.all"
})
~~~

Nếu app sở hữu configuration, hãy chỉ import phần đã được review:

~~~java
@Configuration
@Import(ApprovedVendorConfiguration.class)
public class ApplicationConfiguration {
    // Các config còn lại phải explicit và được kiểm soát.
}
~~~

Hai snippet cần import và type cụ thể; chúng **không** có ý nghĩa rằng chỉ bỏ `@Import` là tắt được mọi listener vendor. Vendor có thể còn được đưa vào context bằng Spring Boot auto-config, component scan, programmatic listener hoặc Boot early listener.

### 5.1. Cấu hình opt-in bằng điều kiện của Spring Boot

Nếu app kiểm soát config tạo listener, có thể đặt condition khi khởi tạo context:

~~~java
// Snippet Spring Boot; @ConditionalOnProperty không thuộc Spring core.
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "integrations.vendor",
    name = "events.enabled",
    havingValue = "true",
    matchIfMissing = false
)
public class VendorEventConfiguration {
    @Bean
    VendorListener vendorListener() {
        return new VendorListener();
    }
}
~~~

Trong file properties:

~~~properties
integrations.vendor.events.enabled=false
~~~

Khi property false và configuration trên là **đường tạo listener duy nhất**, listener bean ấy không được tạo. Nếu thư viện có một auto-config độc lập, property do app tự đặt **không tự vô hiệu hóa** auto-config đó. Cần dùng property được vendor tài liệu hóa hoặc can thiệp đúng con đường đăng ký.

**Không coi property động là unregister.** Condition thường được đánh giá trong lúc xây dựng `ApplicationContext`. Đổi property sau startup không tự hủy bean/listener đã được đăng ký hay thu hồi event đã xử lý.

### 5.2. Exclude đúng auto-configuration của Spring Boot

Khi vendor starter cung cấp một auto-configuration class cụ thể, Spring Boot hỗ trợ exclude:

~~~properties
spring.autoconfigure.exclude=com.vendor.starter.VendorEventsAutoConfiguration
~~~

Hoặc dùng `@SpringBootApplication(excludeName = "...")` khi tên đầy đủ phù hợp.

Điều kiện bắt buộc: class đó phải thực sự là **Boot auto-configuration** được Boot nạp, không phải bất kỳ `@Component` nào. Exclude auto-config không gỡ JAR khỏi classpath và không ngăn một cơ chế khác đăng ký listener. Tên class trong ví dụ chỉ minh họa; kiểm tra documentation/metadata đúng version.

### 5.3. @ConditionalOnMissingBean không phải nút tắt mọi vendor listener

Một số starter lùi lại khi app cung cấp bean cùng type nhờ `@ConditionalOnMissingBean`. Chỉ dựa vào điều này **nếu vendor thật sự dùng condition đó** và match đúng bean type/name. Tạo một dummy bean để “chặn mọi listener” có thể che giấu side effect còn sót hoặc tạo cấu hình sai.

### 5.4. Đừng gỡ listener muộn nếu có thể ngăn tạo từ đầu

`ApplicationEventMulticaster` có API quản lý registration, nhưng việc remove một listener sau `refresh` có thể không an toàn vì:

- Method `@EventListener` có adapter nội bộ, không phải luôn là một bean direct.
- Listener có thể đã chạy, đọc payload hoặc gửi thông tin ra ngoài.
- Một nguồn khác có thể đăng ký lại.
- Task async in-flight có thể vẫn tiếp tục.
- Các API remove-all không có chọn lọc có thể làm hỏng listener nội bộ/framework.

Cách ưu tiên là kiểm soát configuration **trước khi context hoàn tất khởi tạo**, sau đó xác nhận bằng integration test. Dynamic plugin lifecycle đòi hỏi ownership/register/unregister contract riêng, không phải một lệnh remove tùy tiện.

## 6. Bảo vệ dữ liệu bằng event DTO tối giản

Kể cả khi đã kiểm soát registration, dữ liệu nhạy cảm **không nên được đưa lên shared event bus nếu không cần**.

Phản ví dụ:

~~~java
// Mã minh họa: không publish payload như thế này.
publisher.publishEvent(
    new CustomerUpdated(
        customerEntity, authentication, servletRequest, accessToken
    )
);
~~~

Với payload như vậy, một listener phù hợp có thể nhận object chứa PII, token, session, JPA relation và những tham chiếu có thể truy dữ liệu bổ sung. Async listener có thêm rủi ro dùng object mutable, lazy proxy hoặc persistence context ngoài transaction.

Thiết kế tốt hơn:

~~~java
public record AccountLifecycleNotice(
    String accountRef,
    String action,
    long aggregateVersion
) { }
~~~

Phát một fact tối giản:

~~~java
publisher.publishEvent(
    new AccountLifecycleNotice("acct-42", "CREATED", 1L)
);
~~~

Đó là một contract có data allowlist: identifier, loại thay đổi, version. Từng field vẫn phải được phân loại. Ví dụ `accountRef` có thể vẫn là dữ liệu cá nhân nếu tra ngược được danh tính. Nhưng không đưa thừa email, password, raw HTTP request hoặc entity graph làm giảm đáng kể diện tích phơi lộ.

### 6.1. Những thứ thường không nên có trong event dùng chung

- Password, API key, OAuth token, refresh token, cookie, session ID.
- `Authentication`, `Principal`, security context hoặc full HTTP headers.
- JPA entity lớn, object mutable hoặc lazy relationships không rõ vòng đời.
- Địa chỉ, số điện thoại, email nếu consumer chỉ cần biết một đối tượng đã đổi trạng thái.
- Full payment information, hợp đồng nội bộ hoặc log/error message chứa PII.
- `DataSource`, connection, transaction/session object.
- Toàn bộ command/request DTO khi nó chứa nhiều field không dùng đến.
- Dữ liệu từ tenant khác khi consumer chỉ xử lý tenant hiện tại.

Với record, `toString()` thường in tên và giá trị của mọi component. Đừng vô tư log toàn bộ event record nếu có component nhạy cảm.

### 6.2. Metadata cần có và cần kiểm soát

| Field | Mục đích | Lưu ý |
| --- | --- | --- |
| `eventId` | Dedupe và audit | Không thay bằng customer email |
| `eventType` | Fact nghiệp vụ | Tên rõ, versionable |
| `schemaVersion` | Hợp đồng payload | Hỗ trợ evolution |
| `aggregateRef` | Đối tượng liên quan | ID có thể vẫn là PII |
| `occurredAt` | Thời điểm fact xảy ra | UTC/Instant |
| `correlationId` | Theo dõi workflow | Tránh chèn dữ liệu nhạy cảm trực tiếp |
| `tenantRef` | Phạm vi dữ liệu | Không thay thế kiểm tra authorization |
| `audience` (nếu tự định nghĩa) | Gợi ý policy outbound | Spring **không tự thi hành ACL** theo field này |

Một field `audience` trong event chỉ là dữ liệu. Cần một **gateway/adapter tin cậy** để quyết định consumer nào được gửi thông tin nào.

## 7. Chương trình Java 17+ hoàn chỉnh: cấu hình listener vendor có chủ đích

Ví dụ dùng Spring Framework 6.2.8, JDK 17+ và Maven, không dùng Spring Boot. Nó chỉ nhằm chứng minh:

1. Một listener vendor **không có mặt** nếu app không import config tạo bean.
2. Khi config được đăng ký trước `refresh`, listener nhận event đã được phép.
3. Service nhận email riêng tư nhưng record event **không chứa email**.
4. Đây là **kiểm soát đăng ký và giảm dữ liệu** chứ không phải sandbox bảo mật.

### 7.1. Thư mục

~~~text
vendor-listener-demo/
├── pom.xml
└── src/main/java/VendorListenerControlDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>vendor-listener-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>VendorListenerControlDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/VendorListenerControlDemo.java

~~~java
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class VendorListenerControlDemo {

    // DTO chỉ chứa dữ liệu được duyệt cho event bus.
    public record AccountLifecycleNotice(
        long accountId,
        String action
    ) { }

    public static class AccountService {
        private final ApplicationEventPublisher publisher;

        public AccountService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void register(long id, String privateEmail) {
            Objects.requireNonNull(privateEmail, "privateEmail");
            if (id <= 0 || privateEmail.isBlank()) {
                throw new IllegalArgumentException("Invalid account");
            }
            // Dữ liệu email không được đưa vào event record.
            System.out.println("SERVICE_UPDATED id=" + id);
            publisher.publishEvent(
                new AccountLifecycleNotice(id, "CREATED")
            );
        }
    }

    // Giả lập listener trong một thư viện tùy chọn.
    public static class VendorListener {
        private int received;

        @EventListener
        public void on(AccountLifecycleNotice notice) {
            received++;
            System.out.println(
                "VENDOR_NOTICE id=" + notice.accountId()
                + " action=" + notice.action()
            );
        }

        public int receivedCount() {
            return received;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        AccountService accountService(
                ApplicationEventPublisher publisher) {
            return new AccountService(publisher);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class VendorConfig {
        @Bean
        VendorListener vendorListener() {
            return new VendorListener();
        }
    }

    private static void scenario(boolean vendorEnabled) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.register(CoreConfig.class);
            if (vendorEnabled) {
                context.register(VendorConfig.class);
            }
            context.refresh();

            System.out.println("VENDOR_ENABLED=" + vendorEnabled);
            context.getBean(AccountService.class)
                .register(42L, "private@example.invalid");

            int handled = context
                .getBeansOfType(VendorListener.class)
                .values()
                .stream()
                .mapToInt(VendorListener::receivedCount)
                .sum();

            System.out.println("VENDOR_DELIVERED=" + handled);
        }
    }

    public static void main(String[] args) {
        scenario(false);
        scenario(true);
    }
}
~~~

Chạy từ thư mục `vendor-listener-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng **do chương trình in** (không kể log Maven) theo thứ tự:

~~~text
VENDOR_ENABLED=false
SERVICE_UPDATED id=42
VENDOR_DELIVERED=0
VENDOR_ENABLED=true
SERVICE_UPDATED id=42
VENDOR_NOTICE id=42 action=CREATED
VENDOR_DELIVERED=1
~~~

### 7.4. Diễn giải đúng

Trong scenario đầu, chỉ `CoreConfig` được đăng ký; `VendorListener` không tồn tại trong context. Service vẫn publish event nhưng không có vendor listener nhận nó, nên counter bằng 0.

Trong scenario thứ hai, `VendorConfig` được đăng ký **trước `context.refresh()`**. Spring phát hiện method `@EventListener` và đăng ký adapter; listener chạy đồng bộ khi `AccountLifecycleNotice` được publish, in một dòng và counter thành 1.

`AccountLifecycleNotice` chỉ có `accountId` và `action`. Email đầu vào chỉ được kiểm tra trong service, không được truyền qua event payload. **Nhưng** việc event không chứa email không chứng minh một thư viện độc hại không thể lấy email theo cách khác; nếu nó có repository/HTTP client/credential trong cùng JVM thì vẫn có những quyền khác. Cần security boundary và permission thật sự khi trust thấp.

### 7.5. Phạm vi mà demo không bao phủ

- Demo không có Boot auto-configuration hoặc component scan vendor package.
- Không kiểm thử runtime unregister listener.
- Không có multi-tenant authorization.
- Không có database transaction, broker, outbox, async executor hoặc network I/O.
- Không chứng minh cấm vendor library nạp class hoặc truy cập tài nguyên khi thư viện đã nằm trong cùng process.
- Không chứng minh bảo vệ dữ liệu từ một plugin có khả năng thực thi code tùy ý.

Đây là ví dụ **functional registration control** và **data minimization**, không phải security sandbox.

## 8. Khi nào cần đưa listener bên thứ ba ra khỏi event bus nội bộ?

Nếu library chỉ cần gửi một số fact cho analytics hoặc notification service, có thể cân nhắc **trusted outbound gateway** thay vì cho vendor SDK đăng ký thẳng vào bus nội bộ có payload phong phú.

~~~text
Domain use case
     |
     +-- internal state change
     |
     +-- Trusted OutboundGateway
             |
             +-- select approved fact
             +-- validate business and tenant policy
             +-- map to public DTO
             +-- redact / pseudonymize as required
             +-- enqueue durable intent if necessary
             |
             v
         Isolated vendor adapter
             |
             +--> vendor API / broker
~~~

Các nguyên tắc:

- App giữ các dữ liệu nhạy cảm không cần thiết **trong trusted boundary**.
- Outbound DTO được thiết kế theo allowlist, không phải serialize nguyên entity.
- Authorization kiểm tra tại gateway/data layer, không chỉ xem field `tenantId`.
- Credential chỉ có scope cần thiết cho API vendor.
- Network egress được allowlist, rate-limit và audit.
- Retry/idempotency rõ, không gửi trùng side effect ngoài ý định.
- Logs và telemetry dùng trường dữ liệu đã phê duyệt, có retention.

Với vendor code **thật sự không đáng tin**, tách process/container/service với IAM, filesystem và network boundaries mạnh hơn shared JVM. Nhưng một process riêng không tự bảo đảm an toàn nếu nó vẫn được cấp dữ liệu và quyền quá rộng. Cần policy end-to-end.

### 8.1. Context riêng không nhất thiết là sandbox

Một hoặc nhiều `ApplicationContext` trong cùng JVM giúp tách cấu hình/lifecycle nhưng không phải security boundary chống mã thực thi tùy ý. Hơn nữa, event từ child context có thể propagate lên parent; đặt listener vendor ở parent không bảo đảm tránh event từ child. Không dùng context hierarchy như một ACL mặc định.

### 8.2. Phân biệt event contract với command/authorization

Event là mô tả fact đã xảy ra. Nếu một vendor cần **thực hiện hành động có quyền**, hãy dùng một API/command gateway có authorization thay vì cho nó tự gọi service nội bộ tùy ý từ listener. Event không tự chứng minh principal nào được phép thực hiện side effect.

## 9. Exception, latency và transaction của vendor listener

Một listener từ thư viện có thể gây sự cố dù payload không nhạy cảm:

- HTTP call chậm làm tăng p95/p99 của request.
- Runtime exception truyền ngược khi dispatch đồng bộ.
- Side effect làm transaction nguồn giữ connection/lock lâu.
- Listener phát event con, hình thành chain hoặc vòng lặp.
- Logging lỗi chứa thông tin quá mức.
- Retry thiếu idempotency gây duplicate notification/payment.

### 9.1. Listener đồng bộ có thể ảnh hưởng rollback

`SimpleApplicationEventMulticaster` mặc định gọi listener thông thường trên publisher thread. Nếu `publishEvent` nằm trong `@Transactional` và listener ném exception chưa được xử lý, exception có thể propagate và khiến transaction nguồn rollback theo rule phù hợp.

Nếu listener vendor chỉ làm tác vụ phụ trợ, cần quyết định rõ: lỗi của nó **có được phép làm thất bại use case chính không?** Đừng để một starter mặc nhiên thay đổi business semantics.

### 9.2. ErrorHandler không phải permission enforcement

~~~java
// Snippet cấu hình, cần bean/import trong ứng dụng.
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(ex -> {
        System.err.println(
            "Listener failure type=" +
            ex.getClass().getSimpleName()
        );
    });
    return multicaster;
}
~~~

`ErrorHandler` xử lý lỗi khi multicaster gọi listener; tùy logic, exception có thể được log/suppress hoặc rethrow. Nó **không ngăn** listener đã đọc event và không undo side effect đã xảy ra. Không dùng error handler làm data loss prevention.

### 9.3. @Async không biến thư viện thành thành phần đáng tin

`@Async @EventListener` có thể chuyển thân handler sang executor, nhưng:

- Payload vẫn được giao cho listener.
- Code vẫn chạy trong JVM của ứng dụng và có quyền của process.
- Lỗi trong `@Async void` thường đi qua `AsyncUncaughtExceptionHandler` thay vì call stack publisher.
- Executor có thể đầy, reject hoặc mất task khi process chết.
- Thread-bound transaction và một số ThreadLocal context không tự được truyền.
- Timeout và circuit breaker cần được cấu hình ở outbound calls.

Cân nhắc **bounded executor/bulkhead riêng** cho workload vendor để giảm ảnh hưởng availability, nhưng muốn ngăn data exposure phải thiết kế payload/gateway đúng trước.

### 9.4. AFTER_COMMIT không làm dữ liệu an toàn hơn

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` giúp đồng bộ thời điểm sau commit trong transaction phù hợp; nó không giới hạn ai đọc payload. Nếu publish ngoài transaction, mặc định handler không chạy trừ khi chọn `fallbackExecution=true`.

Sau commit cũng không tự là durable delivery. Nếu process chết trước khi job thực thi, task có thể mất. Khi event bắt buộc phải giao, dùng **transactional outbox** hoặc job storage bền vững với consumer idempotent. Outbox chứa PII cũng phải có encryption/access control/retention, không mặc nhiên an toàn.

## 10. Kiểm thử listener vendor và data contract

### 10.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Vendor disabled | Bean/config listener vendor không xuất hiện qua đường registration đã kiểm soát |
| Vendor enabled | Listener nhận đúng event contract đã phê duyệt |
| Event payload tối thiểu | Không có email/token/request/entity nhạy cảm |
| Vendor auto-config exclude | Không có listener được đăng ký qua config bị exclude |
| Vendor có đăng ký thứ cấp | Test phát hiện listener vẫn được đưa vào context qua đường khác |
| Listener sync lỗi | Propagation/rollback đúng policy |
| Listener async lỗi | Error monitoring và retry policy được kiểm tra |
| Listener chậm | Timeout/bulkhead và latency SLA được duy trì |
| Child/parent context | Không có propagation ngoài chủ ý |
| Boot early listener | Không chạy trước mốc startup được phép |
| Upgrade dependency | Contract và listener inventory không thay đổi ngoài dự kiến |
| Outbound vendor payload | Chỉ dữ liệu allowlist được gửi tới destination đã duyệt |
| Nhiều tenant | Authorization và data segregation được enforce |
| Retry/dedup | Không gây side effect trùng khi nhận lại event |

### 10.2. Dùng Spring context thật để test wiring

Một Mockito mock `ApplicationEventPublisher` có thể verify `publishEvent(...)` đã được gọi, nhưng **không tự dispatch** cho listener Spring. Vì vậy unit test mock **không chứng minh** vendor listener enabled hay disabled.

Với registration test, khởi tạo `ApplicationContext` theo configuration của môi trường cần kiểm thử, publish event bằng publisher thật và đo outcome của listener/gateway. Trong demo, `VendorListener.receivedCount()` là outcome có thể quan sát vì handler chạy đồng bộ.

### 10.3. Kiểm tra record schema allowlist

Với một record DTO tối giản, một unit test có thể xác minh component names:

~~~java
// Snippet trong test JUnit, không nằm trong tệp runnable demo.
var names = java.util.Arrays.stream(
    AccountLifecycleNotice.class.getRecordComponents()
).map(java.lang.reflect.RecordComponent::getName).toList();

assertEquals(
    java.util.List.of("accountId", "action"),
    names
);
~~~

Nhưng chỉ kiểm tra schema record **không đủ** để kết luận an toàn tuyệt đối. ID có thể truy ngược dữ liệu, còn outbound adapter có thể thêm metadata/headers/log mà record không chứa. Test quan trọng hơn là **serialized request/payload thực tế tại trusted gateway** không chứa dữ liệu không được phép.

### 10.4. Một negative test dữ liệu

1. Tạo account với email giả có chuỗi đánh dấu.
2. Gọi use case theo test environment.
3. Capture outbound request/body tại mock server của vendor adapter.
4. Assert schema allowlist và không có chuỗi email đánh dấu.
5. Kiểm tra không có token hoặc raw entity được log.
6. Kiểm thử cả trường hợp exception để bảo đảm error logs không in toàn bộ payload.

Không dùng email thật, token thật hay thông tin khách hàng thật trong test logs.

## 11. Spring Boot listener sớm và lifecycle

Một số event khởi động của Spring Boot xảy ra trước khi `ApplicationContext` tồn tại. Listener đăng ký qua `SpringApplication.addListeners(...)` hoặc `META-INF/spring.factories` có thể chạy rất sớm. Một bean `@EventListener` trong context không nhận được tất cả event trước khi context hình thành.

Điều này quan trọng khi audit vendor library: một starter có thể đăng ký startup listener không thông qua bean mà test chỉ kiểm tra sau `ApplicationReadyEvent` sẽ không nhìn thấy hành vi đầu quá trình khởi động.

Khi context đóng, `ContextClosedEvent` xuất hiện trong lifecycle shutdown. Một listener vendor có thể gọi API khi executor/dependency đang dừng. Hãy đặt timeout và shutdown policy phù hợp, không phụ thuộc một event async late shutdown sẽ luôn chạy.

### 11.1. Mã library trong cùng JVM có quyền gì?

Nếu vendor code đã được nạp vào cùng process, nó có thể tương tác với Spring bean, filesystem hoặc network tùy quyền và thiết kế. Một event router không ngăn hoạt động khác của code ấy. Cần:

- Review dependency, provenance, signatures/CVE.
- Tách egress credentials cho integration.
- Không cấp `DataSource`/secret rộng nếu không cần.
- Giới hạn network endpoints và quyền container/process.
- Cân nhắc adapter chạy trong process/service riêng nếu mức tin cậy thấp.

**Không trình bày một field `allowedListener` hoặc type filter như sandbox.**

## 12. Audit, metrics và phát hiện listener mới ngoài dự kiến

Các log nên mô tả **ai xử lý event nào**, nhưng không đưa PII vào nội dung log:

~~~text
event=AccountLifecycleNotice id=e-42
publisher=AccountService listener=VendorListener
listener=VendorListener enabled=true status=handled
vendor_outbound=analytics dataClass=APPROVED_REFERENCE
~~~

Có thể thu thập:

- Event type, schemaVersion, publisher, context ID.
- Listener class/bean, module origin, dependency version.
- Handler duration, exceptions, retry và rejected task.
- Outbound destination và data classification.
- Auto-config condition và feature flag lúc startup.
- Thời điểm config thay đổi và version deployment.

Ví dụ metrics **ứng dụng tự định nghĩa**:

~~~text
app_event_published_total{type="AccountLifecycleNotice"}
app_event_listener_calls_total{listener="VendorListener"}
app_event_listener_failures_total{listener="VendorListener"}
app_vendor_outbound_requests_total{destination="analytics"}
app_vendor_outbound_denied_total{reason="policy"}
~~~

Không đưa `eventId`/`accountId`/email vào metric labels có cardinality cao. ID chi tiết nên ở logs/traces được bảo vệ với retention rõ ràng.

### 12.1. Bảng policy mẫu

| Event | Loại dữ liệu | Consumer hợp lệ | Outbound policy |
| --- | --- | --- | --- |
| `AccountLifecycleNotice` | ID đã phê duyệt, action | InternalAudit, VendorGateway | Có thể gửi sau kiểm tra tenant/business |
| `FullCustomerProfileUpdated` | PII nhạy cảm | Chỉ trusted internal services | Không publish lên shared bus cho vendor |
| `PaymentCaptured` | Fact giao dịch | Ledger, billing | Mapping chính xác, idempotency |
| `CredentialRotated` | Chỉ metadata tối thiểu | Security monitor | Không gửi credential secret |

Đây là policy governance **do ứng dụng định nghĩa**, không phải bảng ACL được Spring tự thực thi.

## 13. Kiểm soát thay đổi khi nâng cấp thư viện

Một bản nâng cấp của vendor có thể:

- Thêm method `@EventListener` mới trên bean đã tồn tại.
- Đổi listener từ explicit config sang Boot auto-configuration.
- Thay đổi property tắt/bật hoặc class auto-config.
- Đăng ký startup listener qua `spring.factories`.
- Chuyển handler sync sang async và thay đổi error propagation.
- Thêm HTTP exporter/telemetry hoặc ghi log payload.
- Thay đổi schema của event hoặc cách xử lý PII.
- Yêu cầu credential/network permissions mới.

Vì vậy một ứng dụng an toàn không chỉ kiểm soát listener lúc viết lần đầu, mà còn kiểm soát **dependency version drift**.

### 13.1. CI/release gate đề xuất

1. Pin version vendor và kiểm tra SBOM/dependency tree.
2. Scan security advisories và đánh giá nguồn gốc artifact.
3. So sánh auto-config/import/annotation registrations trước và sau upgrade.
4. Chạy integration tests cho trường hợp vendor enabled và disabled.
5. Chạy data-contract tests với fake PII và capture outbound request.
6. Kiểm tra exception, latency và shutdown behavior.
7. Review mọi permission, destination và retention mới.
8. Ghi chép kết quả phê duyệt trước release.

Một test khẳng định không có `VendorListener` cụ thể **không bảo đảm** thư viện không còn chạy chức năng khác, nên đừng dùng kết quả đó để bỏ qua security review.

## 14. Sai lầm phổ biến

1. **Nhầm class có annotation với listener đã hoạt động:** phải có registration.
2. **Chỉ tắt @ComponentScan mà quên auto-configuration:** vendor vẫn có thể tự đăng ký qua starter.
3. **Tin @Order giúp lọc payload:** order không phải ACL.
4. **Tin @EventListener(condition=...) có hiệu lực lên mọi listener:** nó chỉ chi phối method đó.
5. **Publish JPA entity, raw request hoặc Authentication:** lộ nhiều dữ liệu hơn cần.
6. **Coi ID luôn không nhạy cảm:** ID có thể liên kết đến một cá nhân hay tenant.
7. **Ghi toàn bộ event.toString() vào log:** record có thể in mọi component.
8. **Để vendor SDK có mọi credential ứng dụng:** event filtering không giới hạn access đến DB/network.
9. **Dùng @Async để “cô lập” library không đáng tin:** vẫn ở cùng JVM.
10. **Coi ErrorHandler là DLP:** exception handling không thu hồi payload đã nhận.
11. **Mock publisher rồi kết luận listener không chạy:** mock không dispatch Spring events.
12. **Chỉ đếm ApplicationListener beans:** không thấy đầy đủ method adapters.
13. **Đổi property runtime rồi tin bean bị unregister:** conditions thường được quyết định khi khởi tạo context.
14. **Remove listener sau khi đã publish:** dữ liệu và side effect đã xảy ra không được thu hồi.
15. **Dùng parent/child context làm sandbox:** event child có thể truyền lên parent; cả hai còn chung process.
16. **Cho rằng AFTER_COMMIT nghĩa là không có PII:** phase không giới hạn data access.
17. **Lưu event nhạy cảm trong outbox không có retention/encryption:** tạo thêm bản sao dữ liệu lâu dài.
18. **Bỏ qua sự kiện Spring Boot sớm:** listener có thể chạy trước context.
19. **Không kiểm thử version upgrade:** một startup listener mới có thể xuất hiện mà app không đổi code.
20. **Không có bounded executor/timeout:** vendor handler có thể làm cạn tài nguyên.
21. **Không kiểm tra cross-tenant authorization:** trường `tenantId` không đủ ngăn truy dữ liệu sai tenant.
22. **Coi process riêng mặc nhiên an toàn:** còn phải giới hạn API, IAM, network, schema và logging.

## 15. Checklist trước khi tích hợp listener vendor

- [ ] Đã xác định thư viện, version, tất cả đường registration và nguồn auto-config?
- [ ] Listener có thật sự cần nhận event được publish không?
- [ ] `@ComponentScan`, `@Import` và vendor properties đã được review?
- [ ] Opt-out có test trên context thật, không chỉ nhìn file properties?
- [ ] Event dùng DTO tối thiểu, bất biến, không chứa secret/PII không cần thiết?
- [ ] Các ID/pseudonyms có được phân loại đúng không?
- [ ] Outbound gateway enforce tenant/business permissions thay vì tin event fields?
- [ ] Đã kiểm tra serialized outbound payload và logs không lộ sensitive data?
- [ ] Có ghi nhận exception, latency, rejected task và retry?
- [ ] Listener có thể ảnh hưởng transaction nguồn không; đó có phải chủ ý?
- [ ] Có process isolation nếu library không đủ mức tin cậy?
- [ ] Có least-privilege credentials, network allowlist và retention?
- [ ] Boot startup listener/ContextClosedEvent đã được xem xét?
- [ ] Upgrade library có integration test và SBOM/security review?
- [ ] Nếu side effect quan trọng, có idempotency/outbox và failure policy không?

## 16. Bài tập tự kiểm tra

1. Class trong JAR có `@EventListener` nhưng không là Spring bean: nó có tự xử lý event không?
2. Vì sao `context.getBeansOfType(ApplicationListener.class)` không cho thấy mọi listener?
3. Một listener có `@Order(1)` có thể chặn listener vendor khác đọc payload không?
4. Một event record chứa `CustomerEntity` và `Authentication`. Vì sao nên thay bằng DTO tối giản?
5. Bỏ `@ComponentScan("com.vendor")` có chắc tắt listener được tạo bởi Boot auto-config không?
6. `spring.autoconfigure.exclude` áp dụng cho loại config nào và có gỡ JAR khỏi classpath không?
7. Thay property `integrations.vendor.events.enabled` lúc runtime có tự gỡ bean đã tạo không?
8. Trong demo, vì sao scenario đầu có `VENDOR_DELIVERED=0` và scenario sau có `VENDOR_DELIVERED=1`?
9. Vì sao demo không chứng minh vendor SDK chạy trong cùng JVM đã được sandbox?
10. Listener vendor sync ném exception có thể tác động gì tới transaction nguồn?
11. `SimpleApplicationEventMulticaster.setErrorHandler` có ngăn listener đọc dữ liệu trước khi lỗi không?
12. `@Async` có làm token biến mất khỏi payload được gửi cho vendor không?
13. `@TransactionalEventListener(AFTER_COMMIT)` kiểm soát thời điểm hay quyền đọc dữ liệu?
14. Có `tenantId` trong event đã đủ để enforce cross-tenant authorization chưa?
15. Khi thư viện không đáng tin, giải pháp nào có ranh giới mạnh hơn việc đưa listener vào Spring context?
16. Vì sao phải capture serialized outbound request thay vì chỉ nhìn component names của record?
17. Khi vendor upgrade thêm startup listener qua `spring.factories`, test chỉ chạy sau ready có đủ không?

**Định hướng:** (1) không, cần registration; (2) adapter của @EventListener không nhất thiết là ApplicationListener bean; (3) không; (4) tránh payload/graph/PII không cần thiết; (5) không; (6) Boot auto-config, không gỡ JAR; (7) không tự động; (8) config opt-in; (9) cùng JVM/quyền; (10) có thể propagate/rollback; (11) không; (12) không; (13) thời điểm; (14) không, cần enforcement; (15) service/process riêng với IAM/network policy; (16) mapper/metadata/outbound có thể thêm dữ liệu; (17) không, phải review startup registration.

## 17. Tổng kết

**Kiểm soát listener của thư viện bên thứ ba** là phối hợp ba lớp:

1. **Registration control:** tạo bean/listener theo opt-in, giới hạn scan/import, exclude đúng Boot auto-configuration và kiểm thử Spring event wiring thật.
2. **Data minimization và outbound policy:** không publish event chứa secret/PII không cần thiết, chuyển qua DTO có allowlist, xác minh serialized payload và authorization tại gateway được tin cậy.
3. **Trust boundary và reliability:** code chạy trong cùng JVM không được Spring event bus sandbox; nếu mức tin cậy thấp, cân nhắc process isolation và least privilege, đồng thời kiểm soát exception, transaction, async, timeout và retry.

`@Order`, `@EventListener(condition=...)`, `@Async`, `ErrorHandler` và `@TransactionalEventListener(AFTER_COMMIT)` đều có vai trò riêng nhưng **không phải cơ chế phân quyền dữ liệu**.

Một tích hợp tốt không chỉ hỏi **“listener có chạy không?”**, mà còn hỏi **“ai được đăng ký, payload bộc lộ những gì, library có quyền gì khác và hệ thống phản ứng ra sao khi thư viện lỗi hoặc thay đổi?”**

## Tài liệu tham khảo

- Spring Framework Reference 6.2 — *Application Events and @EventListener*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.8 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2.8 Javadoc — *EventListenerMethodProcessor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Boot Reference — *Application Events and Listeners*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot Reference — *Auto-configuration and exclusion*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html

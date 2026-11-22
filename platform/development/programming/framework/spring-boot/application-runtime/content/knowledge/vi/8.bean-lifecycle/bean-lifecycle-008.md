# Chọn callback bean hay runner cho công việc khởi động Spring Boot

## 1. Vấn đề: “khi khởi động” có nhiều thời điểm khác nhau

Trong Spring Boot, không phải mọi mã chạy lúc ứng dụng bật lên đều diễn ra cùng một thời điểm. **Callback vòng đời bean** chạy khi Spring đang tạo và khởi tạo từng bean; **ApplicationRunner** và **CommandLineRunner** chạy sau khi ApplicationContext đã refresh, ngay trước khi SpringApplication hoàn tất quá trình khởi động. Chọn sai điểm thực thi có thể khiến startup chậm, tạo vòng phụ thuộc, sử dụng bean chưa sẵn sàng, công bố readiness quá sớm hoặc khó dọn tài nguyên khi lỗi.

Hãy phân biệt hai mục tiêu:

- **Khởi tạo chính một bean:** xác thực cấu hình nội bộ, dựng cấu trúc dữ liệu từ các dependency đã inject, chuẩn bị tài nguyên thuộc sở hữu của bean. Dùng constructor, @PostConstruct, InitializingBean.afterPropertiesSet() hoặc initMethod tùy trường hợp.
- **Thực hiện một công việc cấp ứng dụng sau khi context đã được dựng:** nạp cache ban đầu, kiểm tra kết nối bắt buộc, nhập dữ liệu khởi động, xác nhận điều kiện trước khi nhận request. Dùng ApplicationRunner hoặc CommandLineRunner.

Công việc khởi động phải hoàn thành **trước khi hệ thống coi service là ready** phù hợp với runner, vì Spring Boot phát **ApplicationReadyEvent sau khi các runner hoàn tất**. Ngược lại, việc tạo dữ liệu nội bộ nhỏ gắn chặt với một bean nên để chính bean chịu trách nhiệm. Các listener/scheduler chạy **liên tục** lại thường cần SmartLifecycle hoặc cơ chế riêng có start/stop; runner không tự cung cấp vòng đời dừng.

## 2. Bản đồ thứ tự vòng đời

Ở một ứng dụng Spring Boot 3.x đi theo nhánh khởi động thành công, trình tự đơn giản hóa:

~~~text
SpringApplication.run(args)
    |
    +-- Chuẩn bị Environment / tạo ApplicationContext
    |
    +-- refresh context
    |     |
    |     +-- Tạo và inject các singleton không lazy
    |     |     +-- constructor / dependency injection
    |     |     +-- @PostConstruct
    |     |     +-- InitializingBean.afterPropertiesSet()
    |     |     +-- @Bean(initMethod = "...")
    |     |
    |     +-- SmartInitializingSingleton.afterSingletonsInstantiated()
    |     +-- SmartLifecycle.start() (autoStartup=true)
    |     +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- LivenessState.CORRECT
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- SpringApplication.run(...) trả về
~~~

Đây là **trình tự khái niệm** cho các thành phần thông thường của context. Thứ tự khởi tạo **giữa các bean khác nhau** phụ thuộc dependency graph, @DependsOn, loại scope, lazy initialization và cấu hình; không được coi các bean có @PostConstruct là một danh sách chạy đồng loạt theo thứ tự tên class. Spring Framework gọi các callback nội bộ của **cùng một bean** theo thứ tự đã công bố: **@PostConstruct → afterPropertiesSet() → custom initMethod** khi cả ba có mặt và là những phương thức khác nhau.

Một bean **lazy** có thể chỉ được tạo khi được sử dụng, thậm chí sau khi ứng dụng ready. Vì vậy “@PostConstruct luôn chạy trước ApplicationRunner” **không đúng với mọi bean**. Trong ví dụ runner inject một bean non-lazy bình thường, callback của bean đó chắc chắn hoàn thành trước runner sử dụng nó.

## 3. Bảng lựa chọn theo tiêu chí

| Tiêu chí | Callback khởi tạo bean | ApplicationRunner / CommandLineRunner |
| --- | --- | --- |
| Phạm vi | Một bean và tài nguyên nó sở hữu | Một tác vụ cấp ứng dụng sau khi context đã refresh |
| Thời điểm | Khi bean được tạo, trong giai đoạn khởi tạo bean | Sau ApplicationStartedEvent, trước ApplicationReadyEvent |
| Dependency injection | Dependency được đưa vào bean trước callback | Runner là bean nên có thể inject các service đã được dựng |
| Trạng thái toàn context | Không bảo đảm mọi bean khác đã được tạo | Context đã refresh thành công; bean lazy vẫn có thể chưa tạo |
| Tham số dòng lệnh | Có thể inject ApplicationArguments nhưng ít khi cần | ApplicationRunner nhận ApplicationArguments; CommandLineRunner nhận String... args |
| Thứ tự nhiều tác vụ | Chủ yếu theo dependency graph và @DependsOn | Dùng @Order / Ordered để sắp thứ tự các runner |
| Nếu ném exception | Bean creation hoặc refresh có thể thất bại; lazy bean có thể lỗi ở lần dùng sau | SpringApplication.run(...) thất bại, không đi tiếp đường ready |
| Thời điểm shutdown | Gắn với destroy callback của bean nếu có | Runner không tự có stop callback; sử dụng lifecycle/resource owner riêng |
| Phù hợp | Validate cấu hình, dựng lookup table, chuẩn bị state cục bộ | Warm up bắt buộc, kiểm tra điều kiện startup, import/seeding có kiểm soát |

**Nguyên tắc lựa chọn:** nếu thao tác là điều kiện để **chính bean** trở thành hợp lệ, chọn bean initialization; nếu đó là một **công việc cần nhiều bean đã sẵn sàng** và phải hoàn tất trước readiness, chọn runner.

## 4. Bean initialization: dùng khi nào?

### 4.1. Constructor và dependency injection

Constructor nên thiết lập bất biến, nhận và kiểm tra dependency bắt buộc, tạo state đơn giản. Đừng thực hiện network I/O dài, gửi message, gọi API thanh toán hoặc truy vấn hàng triệu bản ghi từ constructor. Tại thời điểm constructor, quá trình tạo bean chưa hoàn tất, khả năng proxy/AOP chưa được áp dụng đầy đủ và nếu lỗi giữa chừng sẽ khó cleanup tài nguyên mới mở.

Ví dụ:

~~~java
public PricePolicy(int maxDiscountPercent) {
    if (maxDiscountPercent < 0 || maxDiscountPercent > 100) {
        throw new IllegalArgumentException("Invalid discount");
    }
    this.maxDiscountPercent = maxDiscountPercent;
}
~~~

Đây là **đoạn minh họa** nằm trong lớp PricePolicy có trường maxDiscountPercent được khai báo; không phải một chương trình Java độc lập.

### 4.2. @PostConstruct

Spring Framework 6 / Spring Boot 3 sử dụng annotation **jakarta.annotation.PostConstruct**, thay vì **javax.annotation.PostConstruct** của hệ sinh thái cũ.

~~~java
import jakarta.annotation.PostConstruct;

@PostConstruct
void validate() {
    if (path == null || path.isBlank()) {
        throw new IllegalStateException("Missing output path");
    }
}
~~~

Đây là **đoạn minh họa trong một bean** có field path; giá trị học tập là vị trí callback. Method chạy **sau khi dependency được inject và trước khi bean được công bố là đã khởi tạo hoàn chỉnh**. Nó phù hợp để validate property, dựng cấu trúc dữ liệu nhỏ trong RAM hoặc kiểm tra invariant.

Một @PostConstruct chạy lâu có thể kéo dài quá trình tạo singleton và context refresh. Đặc biệt, tránh thực hiện thao tác phức tạp làm truy cập hàng loạt bean khác, vì quá trình khởi tạo singleton còn đang diễn ra và có thể phát sinh deadlock hoặc vòng phụ thuộc.

**Lưu ý AOP/transaction:** @PostConstruct được gọi trong quá trình khởi tạo bean, trước khi bean hoàn chỉnh được các BeanPostProcessor tạo proxy cần thiết. Tự gọi một method @Transactional trên chính bean trong @PostConstruct **không bảo đảm đi qua transaction proxy**. Nếu cần công việc giao dịch tại startup, dùng runner gọi **một Spring service khác** qua proxy của container, thay vì gọi self-invocation.

### 4.3. InitializingBean và custom initMethod

**InitializingBean.afterPropertiesSet()** là giao diện Spring yêu cầu method khởi tạo; phù hợp khi viết component gắn chặt với framework và cần một contract rõ ràng. **@Bean(initMethod="initialize")** gọi method init do bạn đặt tên, hữu ích khi cấu hình lớp thư viện bên ngoài mà không thể sửa source.

~~~java
@Bean(initMethod = "initialize", destroyMethod = "close")
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

Ví dụ trên là **mã cấu hình minh họa**, ExternalClient là lớp giả định có hai method initialize() và close(). Tên method phải khớp với API thật của thư viện. Không khai báo cả @PostConstruct, afterPropertiesSet và initMethod chỉ vì muốn “chắc ăn”; chọn một cơ chế rõ ràng, tránh lặp việc init.

**Dọn dẹp:** đối với bean sở hữu kết nối, stream hoặc executor, đăng ký **@PreDestroy**, **DisposableBean** hoặc destroyMethod thích hợp. Nếu factory/constructor mở resource rồi ném exception trước khi bean được đăng ký đầy đủ, hãy đóng resource ngay trong try/finally tại chỗ; không giả định Spring có thể dọn một đối tượng chưa tạo xong.

## 5. Runner: dùng khi nào?

Spring Boot cung cấp hai giao diện nhận công việc startup sau refresh:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

Hai đoạn trên trình bày **chữ ký rút gọn để học**, bỏ package và Javadoc; chúng không thay thế source thực của Spring Boot. Cả hai là **Spring bean** khi bạn đăng ký bằng @Component hoặc @Bean, và đều được SpringApplication gọi ở cùng giai đoạn.

**ApplicationRunner** hợp khi muốn phân tích đối số thuận tiện: **args.containsOption("flag")**, **args.getOptionValues("name")**, **args.getNonOptionArgs()**. **CommandLineRunner** nhận mảng String[] nguyên bản, phù hợp khi có parser riêng hoặc lệnh đơn giản. Khác nhau chủ yếu ở **cách truyền tham số**, không phải thời điểm thực thi.

Ví dụ tác vụ phù hợp với runner:

- Warm up một cache bắt buộc trước khi nhận traffic.
- Kiểm tra điều kiện sẵn sàng của một resource quan trọng và từ chối startup nếu không đạt.
- Kiểm tra metadata hoặc dữ liệu hệ thống sau khi toàn bộ bean/service đã được khởi tạo.
- Chạy một công việc CLI/batch có đầu vào từ arguments, sau đó ứng dụng kết thúc theo thiết kế.

Với database schema migration, nên sử dụng **Flyway hoặc Liquibase** và integration tương ứng của Spring Boot: migration có thứ tự, lịch sử và kiểm soát phiên bản riêng. Đừng tự thay thế cơ chế migration bằng @PostConstruct hoặc một runner ad hoc. Với seeding dữ liệu, cần xác định idempotency và điều kiện thực thi để không ghi trùng mỗi lần service restart.

## 6. Ví dụ hoàn chỉnh Java 17+, Spring Boot 3.x

Ví dụ dưới đây cho thấy **@PostConstruct chạy trong lúc tạo bean**, sau đó một **ApplicationRunner** làm warm up, rồi **CommandLineRunner** ghi nhận tác vụ đã chạy, cuối cùng **ApplicationReadyEvent** mới được phát.

Tạo một dự án Spring Boot 3.3.x dùng Java 17+, có dependency **spring-boot-starter** và Spring Boot Gradle plugin. Ví dụ không cần web server. Đặt tất cả mã vào **src/main/java/demo/StartupChoiceDemo.java**; chỉ có một lớp public, các class còn lại là package-private nên Java cho phép nằm chung trong tệp.

~~~java
package demo;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class StartupChoiceDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupChoiceDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_RETURNED");
        }
    }
}

@Component
class ConfigurationCheck {
    private boolean valid;

    @PostConstruct
    void initialize() {
        valid = true;
        System.out.println("BEAN_INITIALIZED");
    }

    boolean isValid() {
        return valid;
    }
}

@Component
@Order(10)
class WarmupRunner implements ApplicationRunner {
    private final ConfigurationCheck configuration;

    WarmupRunner(ConfigurationCheck configuration) {
        this.configuration = configuration;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!configuration.isValid()) {
            throw new IllegalStateException("Configuration not initialized");
        }

        System.out.println("RUNNER_WARMUP_START");

        if (args.containsOption("fail-warmup")) {
            throw new IllegalStateException("Warmup failed");
        }

        System.out.println("RUNNER_WARMUP_DONE");
    }
}

@Component
@Order(20)
class AuditRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("RUNNER_AUDIT");
    }
}

@Component
class ReadyReporter {
    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

### Cách chạy

Nếu dự án dùng Gradle wrapper đã cấu hình plugin Spring Boot:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Thứ tự các dòng do chính ví dụ in ra, với lần chạy thành công không truyền đối số:**

~~~text
BEAN_INITIALIZED
RUNNER_WARMUP_START
RUNNER_WARMUP_DONE
RUNNER_AUDIT
APPLICATION_READY
MAIN_RETURNED
~~~

Log của Spring Boot/Gradle có thể xuất hiện xen kẽ, nhưng thứ tự **giữa sáu thông điệp này** được xác lập bởi dependency và contract vòng đời trong ví dụ:

1. **ConfigurationCheck** được Spring khởi tạo, inject vào WarmupRunner; @PostConstruct đặt valid=true và in **BEAN_INITIALIZED** trước khi runner sử dụng bean.
2. Sau refresh, **WarmupRunner** chạy. **@Order(10)** làm nó đứng trước AuditRunner **@Order(20)**, dù hai runner triển khai hai giao diện khác nhau.
3. **AuditRunner** in **RUNNER_AUDIT** sau khi warm up hoàn tất.
4. Spring Boot phát **ApplicationReadyEvent** sau khi cả hai runner trả về thành công; ReadyReporter in **APPLICATION_READY**.
5. **SpringApplication.run(...)** trả về context và main in **MAIN_RETURNED**.

**Quan trọng:** @Order điều khiển thứ tự **runner**, không bắt Spring phải tạo tất cả bean theo thứ tự annotation. Nếu có nhiều runner cùng order, hãy dùng dependency hoặc chỉ số order riêng khi thứ tự là yêu cầu bắt buộc; đừng dựa vào thứ tự component scanning.

### Thử lỗi warm up

~~~bash
./gradlew bootRun --args="--fail-warmup"
~~~

Trong lần này, các thông điệp của ứng dụng xuất hiện trước lỗi là:

~~~text
BEAN_INITIALIZED
RUNNER_WARMUP_START
~~~

Sau đó runner ném **IllegalStateException("Warmup failed")**. SpringApplication xử lý startup failure; **RUNNER_WARMUP_DONE**, **RUNNER_AUDIT**, **APPLICATION_READY** và **MAIN_RETURNED** không xuất hiện trong nhánh thất bại này. Gradle có thể in thêm exception và báo tác vụ bootRun thất bại. Ví dụ cho thấy **runner là một phần của startup barrier**, nếu nó thất bại thì không công bố ready theo đường thành công.

Nếu exception xảy ra trong **@PostConstruct của ConfigurationCheck** khi bean được khởi tạo, context refresh có thể thất bại **trước khi runner nào được gọi**. Với bean lazy chỉ được tạo khi truy cập muộn, lỗi init cũng có thể xảy ra muộn hơn: đó là lý do phải xét loại bean và thời điểm tạo thật.

### Vì sao ví dụ dùng ApplicationReadyEvent?

ApplicationReadyEvent ở đây **chỉ để quan sát thời điểm ứng dụng ready**, không phải nơi thực hiện warm up bắt buộc. Nếu chuyển đoạn warm up sang handler của ApplicationReadyEvent, bạn đã đưa công việc nặng vào event dispatch. Spring Boot mặc định gọi listener sự kiện đồng bộ; điều này làm chậm tín hiệu readiness và khó thể hiện rõ thứ tự nghiệp vụ giữa nhiều công việc. Runner phù hợp hơn cho điều kiện startup phải hoàn tất trước khi phục vụ.

## 7. Các lựa chọn nằm giữa bean init và runner

Không phải mọi trường hợp đều thuộc đúng hai nhóm. Spring Framework có những hook riêng, mỗi hook giải một vấn đề khác.

### SmartInitializingSingleton

**SmartInitializingSingleton.afterSingletonsInstantiated()** được gọi sau khi BeanFactory hoàn tất giai đoạn tạo các **singleton không lazy**. Nó phù hợp nếu component cần biết các singleton thông thường đã được tạo xong nhưng vẫn muốn can thiệp ở pha khởi tạo context, ví dụ xác thực tập các plugin/handler đã đăng ký.

~~~java
@Component
class HandlerRegistryVerifier implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Kiem tra tap handler da duoc tao o pha singleton.
    }
}
~~~

Đây là đoạn minh họa: cần import **org.springframework.beans.factory.SmartInitializingSingleton** và **org.springframework.stereotype.Component** để dùng trong một lớp Java đầy đủ. Hook này **không bảo đảm mọi lazy bean/prototype đã được tạo** và không phải tín hiệu ApplicationReadyEvent.

### SmartLifecycle

Nếu bean phải **bắt đầu và dừng hoạt động liên tục** (consumer, listener, bộ xử lý nền), **SmartLifecycle** thích hợp hơn một runner đơn thuần vì có các phương thức **start()**, **stop()**, **isRunning()**, **isAutoStartup()**, **getPhase()** và khả năng dừng có kiểm soát.

Khi refresh context, bean SmartLifecycle được tự start nếu **isAutoStartup()=true** theo cơ chế lifecycle processor. **getPhase() thấp hơn được start trước**, còn shutdown theo thứ tự ngược; quan hệ dependency vẫn có ý nghĩa. Đây là thứ tự start/stop của lifecycle bean, **khác với @Order của runner**.

Nếu consumer bắt đầu xử lý message từ xa ngay khi SmartLifecycle.start() được gọi, cần tự quản lý việc chấp nhận traffic công việc khi ứng dụng chưa ready. Không mặc định mọi hệ thống ngoài sẽ chờ Spring Boot công bố readiness.

### ContextRefreshedEvent, ApplicationStartedEvent, ApplicationReadyEvent

- **ContextRefreshedEvent** báo context đã refresh. Trong ứng dụng có context hierarchy hoặc refresh nhiều lần, handler có thể nhận nhiều event; đừng tự hiểu nó luôn chỉ chạy một lần.
- **ApplicationStartedEvent** của Spring Boot xuất hiện sau refresh nhưng **trước runner**; phù hợp để quan sát mốc started, không thay thế runner cho tác vụ có thứ tự rõ ràng.
- **ApplicationReadyEvent** xuất hiện **sau runner** và trước khi Spring Boot công bố **ReadinessState.ACCEPTING_TRAFFIC**. Phù hợp cho log/telemetry nhẹ khi startup thành công.

Nếu mục tiêu là **nghiệp vụ cần được hoàn tất trước ready**, runner là lựa chọn dễ theo dõi nhất. Nếu cần thực hiện công việc nền **sau khi đã sẵn sàng**, cần thiết kế cơ chế chạy nền và chính sách readiness/giám sát phù hợp; chỉ dùng @Async để “đẩy công việc ra khỏi startup” sẽ làm runner trả về trước khi công việc thật hoàn thành.

## 8. Lưu ý về @Transactional và phụ thuộc ngoài

Một công việc khởi động thường cần truy vấn database hoặc gọi remote API. Cách tổ chức nên là **runner điều phối, service thực hiện nghiệp vụ**, với transaction được đặt tại ranh giới service và gọi qua bean do Spring quản lý:

~~~java
@Service
class SeedService {
    @Transactional
    public void seedIfMissing() {
        // Doc va ghi du lieu trong transaction.
    }
}

@Component
class SeedRunner implements ApplicationRunner {
    private final SeedService seedService;

    SeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seedIfMissing();
    }
}
~~~

Đoạn này **chỉ minh họa tổ chức trách nhiệm**, vì cần bổ sung các import, nghiệp vụ thực, repository và transaction manager trước khi chạy. Với Spring Boot 3.x, @Service thuộc **org.springframework.stereotype.Service**, @Transactional thuộc **org.springframework.transaction.annotation.Transactional**.

Việc runner gọi **seedService.seedIfMissing()** qua injected bean tạo điều kiện cho Spring AOP transaction proxy áp dụng khi transaction management được cấu hình. **Self-invocation** từ cùng class, đặc biệt trong @PostConstruct, có thể bỏ qua proxy nên không có transaction như kỳ vọng.

Khi seed từ startup:

- Dùng **idempotency**: nếu nhiều instance cùng chạy, “check rồi insert” đơn giản có race condition; nên dùng unique constraint, upsert hoặc cơ chế khóa/điều phối phù hợp.
- Xác định **timeout**, retry có giới hạn và trường hợp dependency bên ngoài không sẵn sàng.
- Tách **schema migration** (Flyway/Liquibase) khỏi **data seeding**.
- Nếu một lần chạy thất bại giữa chừng, xem xét transaction boundary hoặc checkpoint để retry không phá dữ liệu.
- Không giả định runner chỉ chạy một lần **trên toàn hệ thống**: nó chạy mỗi lần SpringApplication tương ứng khởi động, bao gồm mỗi Pod/replica và lần restart.

## 9. Tính đúng đắn của readiness và startup failure

Theo Spring Boot, sau refresh có **ApplicationStartedEvent**, rồi liveness được công bố đúng. Sau khi mọi runner hoàn thành, có **ApplicationReadyEvent** và readiness được công bố **ACCEPTING_TRAFFIC**. Điều này có ý nghĩa vận hành:

| Trường hợp | Tín hiệu vận hành |
| --- | --- |
| @PostConstruct của singleton bắt buộc ném exception | Context refresh có thể fail; runner không chạy |
| Runner bắt buộc ném exception | Startup thất bại; không đi đến ready theo nhánh thành công |
| Runner gọi async task rồi trả về ngay | Spring Boot có thể ready trong khi async task còn chạy |
| Một request HTTP gặp lỗi sau ready | Thường là lỗi runtime, không mặc nhiên là startup failure |
| SmartLifecycle khởi động consumer sớm | Consumer có thể nhận việc trước readiness nếu không tự chặn |
| Runner chạy lâu vô thời hạn | Kéo dài startup/readiness; có thể khiến startup probe hoặc hệ thống điều phối timeout |

**Không dùng readiness như một phép thử toàn năng về nghiệp vụ.** Readiness phản ánh khả năng instance nhận lưu lượng theo trạng thái được công bố; hệ thống còn cần health probe, metric và kiểm soát lỗi từng request/event.

Nếu startup runner có thể bị chặn vô hạn bởi một dependency bên ngoài, cần giới hạn thời gian và xác định chiến lược fail-fast hoặc degraded mode dựa trên hợp đồng sản phẩm. Đừng dùng retry không giới hạn để giữ tiến trình ở trạng thái “đang khởi động” mãi.

## 10. Ma trận tình huống: chọn hook nào?

| Yêu cầu | Điểm mở rộng phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra property cấu hình của một bean | Constructor hoặc @PostConstruct | Là invariant cục bộ; fail sớm khi bean được tạo |
| Dựng bảng tra cứu nhỏ từ field đã inject | @PostConstruct hoặc initMethod | Chuẩn bị state nội bộ nhanh |
| Dùng service và repository để warm up cache bắt buộc | ApplicationRunner | Context đã refresh, điều phối trước ready |
| Xử lý đối số CLI theo dạng --name=value | ApplicationRunner | Có ApplicationArguments đã phân tích |
| Chuyển nguyên mảng String[] cho parser riêng | CommandLineRunner | Nhận raw arguments |
| Kiểm tra tập singleton handler đã khởi tạo | SmartInitializingSingleton | Sau giai đoạn pre-instantiation singleton không lazy |
| Bắt đầu consumer có start/stop rõ ràng | SmartLifecycle | Quản lý trạng thái chạy và shutdown |
| Ghi một log khi context refresh xong | ContextRefreshedEvent | Quan sát context, chú ý nhiều context |
| Ghi telemetry sau startup runners | ApplicationReadyEvent | Biết đường startup thành công đã qua runner |
| Migration schema DB có phiên bản | Flyway/Liquibase | Có quản lý thứ tự, lịch sử và phiên bản |
| Công việc định kỳ sau khi service chạy | Scheduler/@Scheduled hoặc worker quản lý | Không phải tác vụ startup một lần |
| Tạo nội dung seed chỉ một lần cho cả cluster | Migration/Job riêng hoặc cơ chế đồng bộ toàn hệ thống | Runner trên mỗi replica không bảo đảm chạy một lần toàn cụm |

## 11. Các lỗi thường gặp

**Lỗi 1 — Đặt công việc mất vài phút vào @PostConstruct.** Nó chạy khi BeanFactory vẫn đang khởi tạo bean; có thể khóa đường tạo singleton, gây chậm refresh hoặc xung đột với bean khác. Chuyển tác vụ cần toàn context sang runner nếu phải hoàn tất trước ready.

**Lỗi 2 — Gọi bean phức tạp từ constructor.** Bean khác có thể đang được tạo, proxy chưa hình thành, resource chưa sẵn sàng. Constructor nên gọn và tập trung vào invariant của đối tượng.

**Lỗi 3 — Nghĩ @PostConstruct chạy sau khi ứng dụng ready.** Nó chạy khi bean được tạo. Với non-lazy singleton thông thường, điều này là **trước** ApplicationStartedEvent và runner; với lazy bean, thời điểm có thể muộn hơn.

**Lỗi 4 — Dùng @Order để xếp thứ tự mọi callback bean.** @Order dùng được để xếp thứ tự runner; nó không thay thế dependency graph và @DependsOn cho khởi tạo bean, cũng không thay đổi thời điểm của @PostConstruct so với ready.

**Lỗi 5 — Runner chạy async và lập tức trả về nhưng vẫn coi warm up đã xong.** Spring Boot chỉ biết phương thức run(...) đã trở về. Nếu kết quả async là điều kiện ready, cần chờ kết quả có timeout, xử lý lỗi hoặc điều khiển readiness một cách có chủ đích.

**Lỗi 6 — Runner đóng toàn bộ JVM bằng System.exit(0) khi lỗi.** Hệ thống điều phối có thể ghi nhận thành công giả. Hãy để exception bắt buộc fail startup và ghi đúng exit code khi viết ứng dụng CLI.

**Lỗi 7 — Dùng @PostConstruct gọi method @Transactional ngay trên chính bean.** Lời gọi self-invocation không đi qua proxy Spring; transaction có thể không kích hoạt. Chuyển nghiệp vụ sang service riêng và gọi từ runner.

**Lỗi 8 — Một runner tự mở tài nguyên nền nhưng không có shutdown path.** Runner là điểm bắt đầu, không tự cung cấp stop() hoặc destroy(). Dùng bean quản lý resource với @PreDestroy, destroyMethod hoặc SmartLifecycle.

**Lỗi 9 — Xem runner như một cron job chạy đúng một lần toàn hệ thống.** Mỗi restart/replica có thể chạy lại runner; cần idempotency, constraint và điều phối.

**Lỗi 10 — Dùng ApplicationReadyEvent để chạy một tác vụ rất dài.** Listener đồng bộ có thể làm startup chưa hoàn tất hoặc block luồng phát event; hãy chọn runner cho tác vụ startup bắt buộc và thiết kế công việc nền riêng nếu không bắt buộc.

**Lỗi 11 — Khởi tạo bean bằng cách phụ thuộc thứ tự quét class.** Component scanning không phải lịch thực thi nghiệp vụ. Hãy khai báo dependency tường minh và @Order cho runner.

## 12. Checklist thiết kế

Trước khi chọn callback, hãy trả lời:

1. Công việc **gắn với một bean** hay **phối hợp nhiều service**?
2. Có cần đợi **ApplicationContext refresh xong** không?
3. Công việc có phải **hoàn tất trước khi nhận traffic** không?
4. Có cần **đối số dòng lệnh**, transaction, repository hoặc remote API không?
5. Mất bao lâu, có **timeout/retry** và cách báo lỗi không?
6. Có cần **start/stop liên tục** hoặc giải phóng resource khi shutdown không?
7. Công việc có thể chạy lại ở mỗi replica/restart không? Đã bảo đảm **idempotency** chưa?
8. Nếu exception xuất hiện, nên **fail startup**, hoạt động degraded hay ghi nhận một lỗi background?

Một quyết định hợp lý thường là: **bean init để bean hợp lệ; runner để hoàn thành việc cấp ứng dụng trước readiness; SmartLifecycle để quản lý thành phần hoạt động liên tục**.

## 13. Tự kiểm tra

**Câu 1:** Một bean cần kiểm tra property "timeoutMs" lớn hơn 0 sau khi được inject. Chọn gì?  
**Đáp án:** Constructor nếu dữ liệu đã có ngay lúc tạo, hoặc @PostConstruct/initMethod để kiểm tra invariant của chính bean.

**Câu 2:** Cần gọi ba service để preload cache quan trọng trước khi service nhận HTTP request. Chọn gì?  
**Đáp án:** ApplicationRunner; dùng @Order/Ordered nếu có nhiều runner cần thứ tự.

**Câu 3:** ApplicationRunner và CommandLineRunner khác nhau chính ở điểm nào?  
**Đáp án:** ApplicationRunner nhận ApplicationArguments đã parse; CommandLineRunner nhận String... args.

**Câu 4:** Runner đã gọi Future để tải dữ liệu, không đợi Future hoàn thành rồi trả về. Có chắc cache sẵn sàng trước ready không?  
**Đáp án:** Không. Runner hoàn tất về mặt method, còn công việc async vẫn có thể đang chạy.

**Câu 5:** @PostConstruct ném exception thì runner có chạy không?  
**Đáp án:** Nếu đó là singleton non-lazy bắt buộc trong refresh, startup fail và runner không chạy. Với bean lazy được tạo sau đó, thời điểm lỗi phụ thuộc lúc bean được yêu cầu.

**Câu 6:** Muốn một Kafka consumer được start và stop có kiểm soát, nên dùng runner hay SmartLifecycle?  
**Đáp án:** SmartLifecycle hoặc cơ chế listener container đã có sẵn phù hợp hơn cho vòng đời dài hạn.

**Câu 7:** Hai runner có @Order(10) và @Order(20), cái nào chạy trước?  
**Đáp án:** Runner order 10, bất kể chúng thuộc ApplicationRunner hay CommandLineRunner.

**Câu 8:** Runner dùng @Transactional method của chính nó bằng this.doWork(), giao dịch có chắc hoạt động không?  
**Đáp án:** Không. Self-invocation thường không qua AOP proxy; gọi một service bean được inject và có transaction management phù hợp.

**Ghi nhớ:** Chọn **bean callback** khi cần đảm bảo tính hợp lệ và state cục bộ của một bean trong lúc nó được khởi tạo; chọn **ApplicationRunner/CommandLineRunner** khi cần làm việc cấp ứng dụng sau refresh nhưng trước ready. Sắp thứ tự runner bằng @Order/Ordered, đừng dùng callback bean cho tác vụ startup dài và luôn định nghĩa rõ hành vi khi lỗi, timeout, restart và shutdown.

### Tài liệu tham khảo

- [Spring Boot — SpringApplication và Application Events](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot 3.3 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html)
- [Spring Framework — Bean lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — SmartInitializingSingleton API](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html)

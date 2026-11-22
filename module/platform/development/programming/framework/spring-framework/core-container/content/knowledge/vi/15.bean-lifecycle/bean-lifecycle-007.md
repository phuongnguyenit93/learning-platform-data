# Giới hạn gọi bean khác hoặc làm việc nặng trong callback khởi tạo của Spring

## 1. Mục đích và nguyên tắc

Spring quản lý vòng đời của bean: tạo instance, giải quyết dependency, tiêm thuộc tính, gọi callback khởi tạo, áp dụng bean post-processing rồi cung cấp bean đã hoàn chỉnh cho ứng dụng. `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và `@Bean(initMethod = "...")` là các callback **trong quá trình tạo chính bean đó**.

**Quy tắc thực hành:** callback khởi tạo chỉ nên kiểm tra tính hợp lệ của cấu hình và chuẩn bị trạng thái nội bộ nhỏ, có chi phí dự đoán được. Không dùng callback như điểm khởi chạy mọi nghiệp vụ, job nặng, mạng, database hay thread nền.

Tài liệu chính thức của Spring nhấn mạnh `@PostConstruct` và initialization methods nói chung được thực thi trong **singleton creation lock** đối với singleton đang tạo. Bean chỉ được xem là hoàn toàn initialized sau khi callback trả về; truy cập bean khác không kiểm soát ở giai đoạn này làm tăng nguy cơ **initialization deadlock**. Với công việc cần thực hiện sau khi eager singleton hoàn tất, có `SmartInitializingSingleton.afterSingletonsInstantiated()`, `ContextRefreshedEvent` hoặc `(Smart)Lifecycle`.

Điều này **không đồng nghĩa** mọi lời gọi method của dependency đã inject đều bị cấm. Việc đọc dữ liệu immutable đã có hoặc kiểm tra invariant đơn giản có thể phù hợp. Điều nên tránh là truy cập động kéo theo tạo bean khác, kích hoạt chuỗi nghiệp vụ lớn hoặc chờ một tác vụ phụ thuộc vào container đang bootstrap.

## 2. Lifecycle và thời điểm bean thật sự sẵn sàng

~~~text
ApplicationContext.refresh()
  ├─ Đọc bean definitions, đăng ký BeanPostProcessor
  ├─ Resolve constructor/factory method arguments
  ├─ Tạo bean instance
  ├─ Tiêm setter/field/property dependencies
  ├─ Các Aware callbacks và post-processing trước khởi tạo
  │     └─ @PostConstruct được xử lý trong giai đoạn này
  ├─ InitializingBean.afterPropertiesSet()
  ├─ Custom initMethod / init-method
  ├─ BeanPostProcessor sau khởi tạo (có thể tạo proxy)
  ├─ Bean hoàn tất và được container quản lý theo scope
  ├─ Tạo xong các singleton eager khác
  ├─ SmartInitializingSingleton.afterSingletonsInstantiated()
  ├─ LifecycleProcessor thực hiện startup các lifecycle beans phù hợp
  └─ Publish ContextRefreshedEvent; kết thúc refresh()
~~~

Đây là sơ đồ khái niệm của bean thông thường. Có những trường hợp đặc biệt như `FactoryBean`, proxy sớm, bean lazily initialized, custom post-processor hoặc circular dependencies. Không suy ra từ sơ đồ rằng tất cả post-processor trước initialization chắc chắn chạy trước `@PostConstruct`: annotation này được xử lý bởi một post-processor tương ứng, còn thứ tự giữa các post-processors có contract riêng.

Nếu khai báo ba callback **khác method** trong cùng bean, thứ tự thông dụng Spring bảo đảm là:

1. Method `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method (ví dụ `@Bean(initMethod = "initialize")`).

**Bean đã được Java constructor tạo** chưa có nghĩa là **Spring đã hoàn tất bean**. Init callback vẫn có thể chạy trước khi AOP proxy bên ngoài được hình thành. Nếu đối tượng bị đưa cho thread khác quá sớm, thread ấy có thể thấy state chưa hoàn thiện hoặc raw target không đi qua interceptor.

### Scope thay đổi thời điểm chạy callback

| Scope | Thời điểm callback init chạy | Rủi ro cụ thể |
| --- | --- | --- |
| Singleton non-lazy | Thường trong context refresh | Blocking callback kéo dài bootstrap |
| Singleton `@Lazy` | Khi lần đầu cần bean, có thể sau refresh | Request đầu tiên chậm; bean vẫn đang trong creation |
| Prototype | Mỗi lần container tạo một instance mới | Chi phí/side effect lặp nhiều lần |
| Request | Khi target được tạo trong HTTP request | Làm chậm request đầu của scope |
| Session | Khi target được tạo trong HTTP session | Làm chậm lần đầu truy cập session state |

Spring không tự gọi destroy callback cho từng prototype đã được trao; với bean giữ resource phải có owner rõ ràng.

## 3. Singleton creation lock và vòng chờ

Spring cần đồng bộ hóa việc tạo singleton để không có nhiều luồng tùy tiện dựng cùng một bean và để bean được công bố đúng lúc. Một init method chờ công việc bên ngoài có thể làm chính quá trình tạo bean bị kẹt.

~~~text
Luồng STARTUP:
    đang tạo bean A
    A.@PostConstruct()
       ├─ submit một task T
       └─ Future.get() chờ T hoàn tất

Luồng EXECUTOR:
    task T cần applicationContext.getBean(A.class)
       └─ chờ quá trình tạo A hoàn tất

STARTUP đang chờ EXECUTOR
EXECUTOR đang chờ STARTUP
→ vòng chờ có thể gây deadlock
~~~

Sơ đồ là **kịch bản nguy cơ**, không bảo đảm mọi cấu hình Spring đều deadlock đúng cách này; tùy bean graph, framework có thể báo `BeanCurrentlyInCreationException`, trả early reference trong trường hợp cho phép, hoặc block. Nhưng cấu trúc chờ vòng tròn cần được loại bỏ.

Các hoạt động thường dẫn tới rủi ro:

- Gọi `applicationContext.getBean(...)` hoặc `getBeansOfType(...)` khi chưa biết bean nào đã được tạo, kéo thêm singleton khác vào bootstrap.
- Gọi một service khác mà service ấy thực hiện lazy lookup hoặc gọi ngược bean đang khởi tạo.
- Khởi chạy thread, rồi `join()`/`Future.get()` ngay trong callback.
- Dùng latch, lock hoặc monitor phụ thuộc vào event chỉ phát sau `refresh()`.
- Mở kết nối network/DB không có timeout hoặc retry vô hạn.
- Tạo executor/consumer/scheduler bắt đầu xử lý ngay khi các dependency và proxy chưa initialized.

**Không phải mọi `getBean()` đều chắc chắn deadlock**. Một bean đơn giản đã initialized có thể được lấy thành công. Rủi ro là callback đang giữ trạng thái tạo bean của container, trong khi logic được gọi có thể thay đổi hoặc kéo thêm dependencies theo thời gian. Thiết kế dài hạn không nên phụ thuộc vào thứ tự khởi tạo ngẫu nhiên.

## 4. Những việc thích hợp trong `@PostConstruct`

Callback init phù hợp với **validation cục bộ, setup dữ liệu nhỏ và invariant của chính bean**.

~~~java
@Component
public class RetrySettings {
    private final int attempts;
    private Map<String, Integer> delays;

    public RetrySettings(@Value("3") int attempts) {
        this.attempts = attempts;
    }

    @PostConstruct
    void validateAndPrepare() {
        if (attempts < 1 || attempts > 10) {
            throw new IllegalStateException("attempts out of range");
        }
        delays = Map.of("fast", 100, "normal", 500);
    }

    public int delay(String priority) {
        return delays.getOrDefault(priority, 1000);
    }
}
~~~

Đây là **snippet minh họa**, cần các import `java.util.Map`, `jakarta.annotation.PostConstruct`, `org.springframework.stereotype.Component` và `org.springframework.beans.factory.annotation.Value`; component scanning cần được bật. `@Value("3")` là literal nhằm làm rõ vòng đời. Callback thực hiện kiểm tra và tạo `Map` nhỏ, không I/O, không chờ external service và không lấy thêm bean.

Nếu constructor có thể thiết lập đầy đủ state, hãy cân nhắc bỏ hẳn callback:

~~~java
public final class RetryDefaults {
    private final Map<String, Integer> delays;

    public RetryDefaults() {
        delays = Map.of("fast", 100, "normal", 500);
    }
}
~~~

Snippet thứ hai cần import `Map`. Các `final` fields rõ ràng thường giúp object đơn giản, dễ test và giảm phụ thuộc vào thứ tự lifecycle.

### Fail fast hợp lý

Nếu cấu hình sai khiến bean không thể hoạt động, `@PostConstruct` có thể ném `IllegalStateException` với thông báo đủ rõ. Spring thường bọc lỗi tạo bean vào `BeanCreationException`; với eager singleton, context refresh có thể thất bại. Điều này hợp lý với invariant bắt buộc, **khác** với việc làm cả ứng dụng thất bại vì một optional remote cache tạm thời không hoạt động.

## 5. Những hành vi không nên thực hiện trong callback

| Công việc | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Warm cache hàng triệu bản ghi | Giữ startup, tốn RAM, ngoại lệ giữa chừng | Hook hậu singleton, job riêng, timeout và readiness |
| Gọi API REST/gRPC nhiều lần | Remote outage, DNS, retry vô hạn | Timeout, backoff có hạn; startup workflow có quản lý |
| DB schema migration | Lock DB, cạnh tranh nhiều replica | Flyway/Liquibase hoặc deployment migration |
| Start consumer/long-running scheduler | Chạy trước khi app initialized; thiếu stop | `SmartLifecycle` |
| `Future.get()` đợi task từ init | Task có thể cần bean/lock startup | Tách orchestration ra sau local init |
| `Thread.sleep()` đợi bean khác | Không biểu diễn dependency; race khó chẩn đoán | Constructor injection và readiness condition |
| Quét tất cả beans trong init | Có thể kích hoạt tạo bean quá sớm | `SmartInitializingSingleton` nếu cần eager singletons |
| Gọi proxy request/session ở startup | Chưa có active request/session | Dùng ở request handler có context hợp lệ |
| Gọi `@Transactional` method bằng `this` | Không qua proxy-based AOP advice | Chuyển sang collaborator qua proxy sau init |
| Tạo thread giữ `this` | Bean chưa đầy đủ; unmanaged lifecycle | Executor và lifecycle quản lý |

Không có mức thời gian cố định mà Spring “cho phép dưới N ms và cấm trên N ms”. Vấn đề là **nhiệm vụ có phải local initialization hay một hoạt động runtime độc lập**, tác động lên creation lock, tính bounded của công việc, và cách xử lý thất bại.

## 6. `@Transactional` và proxy trong init callback

Một lỗi điển hình:

~~~java
@Service
class PaymentService {
    @PostConstruct
    void init() {
        reconcilePayments();
    }

    @Transactional
    public void reconcilePayments() {
        // Truy vấn và cập nhật dữ liệu thanh toán.
    }
}
~~~

Đây là **phản ví dụ minh họa**, chưa có import và transaction manager, không phải chương trình standalone. Lời gọi `reconcilePayments()` từ `init()` tương đương `this.reconcilePayments()`: self-invocation trên target **không đi qua Spring AOP proxy**. Ngoài ra callback chạy khi bean vẫn đang khởi tạo; không thể kỳ vọng transaction advice, `@Async` hay caching advice hoạt động y như lời gọi từ một bean khác qua proxy.

Cách sửa là tách trách nhiệm:

~~~text
Bean A: @PostConstruct → chỉ validate cấu hình cục bộ

StartupCoordinator: hook sau khi eager singletons initialized
       ↓ gọi collaborator được Spring inject
TransactionalPaymentService (proxy của Spring)
       ↓ thực hiện nghiệp vụ @Transactional
~~~

Để transaction thật sự có hiệu lực vẫn cần bật transaction management, có transaction manager thích hợp, một public/proxy-interceptable method và lời gọi **qua Spring proxy**. Chuyển hook tự nó không thiết lập transaction.

### Request/session scoped proxies

Inject một request-scoped proxy vào singleton có thể thành công ngay lúc startup. Nhưng **gọi method qua proxy** khi không có HTTP request đang bound thường dẫn đến scope-not-active exception. Callback khởi tạo của một singleton không tạo ra HTTP request giả. Chỉ dùng request data trong active request, hoặc trích xuất thành dữ liệu độc lập để truyền sang background job.

## 7. `BeanPostProcessor` và bean khởi tạo quá sớm

`BeanPostProcessor` là extension point được container đăng ký tương đối sớm để can thiệp các bean tạo sau. Nếu BeanPostProcessor phụ thuộc trực tiếp hoặc gián tiếp vào service nghiệp vụ, service có thể bị tạo **trước khi tất cả post-processors được đăng ký**, khiến nó không đủ điều kiện full post-processing, bao gồm auto-proxying trong một số trường hợp. Spring có thể log cảnh báo bean không eligible cho tất cả BeanPostProcessors.

Với `@Bean` tạo BeanPostProcessor, thường nên dùng **static factory method** và hạn chế dependency:

~~~java
@Configuration
class ExtensionConfig {
    @Bean
    static BeanPostProcessor loggingProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {
                return bean;
            }
        };
    }
}
~~~

Đoạn này là snippet, cần import `BeanPostProcessor`, `@Bean`, `@Configuration`. Ví dụ không chứa nghiệp vụ ở processor. Đừng sử dụng `BeanFactoryPostProcessor` để `getBean()` nghiệp vụ sớm; extension point đó chủ yếu chỉnh **bean definitions**, không nên kích hoạt bean instances trong phase cấu hình.

## 8. `SmartInitializingSingleton`: sau khi eager singletons được tạo

`org.springframework.beans.factory.SmartInitializingSingleton` cung cấp:

~~~java
void afterSingletonsInstantiated();
~~~

Callback chạy ở cuối pha pre-instantiation các **regular singleton non-lazy**, ngoài local init method của từng singleton. Nếu cần tiếp cận danh sách eager singleton hoặc gọi collaborator đã được dựng, đây là lựa chọn hợp lý.

~~~java
@Component
class IndexWarmup implements SmartInitializingSingleton {
    private final IndexService index;

    IndexWarmup(IndexService index) {
        this.index = index;
    }

    @Override
    public void afterSingletonsInstantiated() {
        index.validateLocalMetadata();
    }
}
~~~

Đây là snippet; giả định ứng dụng có `IndexService`, các import Spring tương ứng và metadata validation nhanh.

**Giới hạn chính xác:**

- Hook này không tự chạy cho prototype, request/session bean và **không bảo đảm** chạy cho singleton `@Lazy` chỉ được tạo sau giai đoạn eager bootstrap.
- Các eager singleton đã initialized không có nghĩa **external systems** đã sẵn sàng, hoặc traffic readiness đã đạt.
- Hook **không tự async**; một callback mất 30 giây vẫn làm startup chậm 30 giây.
- Với asynchronous worker cần start/stop thực sự, Spring javadoc khuyến nghị dùng `Lifecycle` hoặc `SmartLifecycle`.

## 9. `ContextRefreshedEvent`: sau giai đoạn refresh

Có thể dùng `ApplicationListener<ContextRefreshedEvent>` hoặc `@EventListener` để thực thi logic sau khi context hoàn tất những bước khởi tạo trong refresh.

~~~java
@Component
class StartupVerifier {
    private final ExternalCheck check;

    StartupVerifier(ExternalCheck check) {
        this.check = check;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onContextRefreshed() {
        check.verifyWithTimeout();
    }
}
~~~

Đây là snippet: `ExternalCheck` cần được cung cấp và method thực sự phải có deadline, có import `EventListener`, `ContextRefreshedEvent`, `Component`.

**Lưu ý:**

- Event listener thông thường được invoke **đồng bộ** bởi multicaster mặc định. I/O lâu trong listener vẫn có thể làm `refresh()` chậm.
- Có thể có nhiều contexts (cha/con), hoặc nhiều lần refresh; event có thể đến nhiều lần. Dùng filtering và idempotence nếu operation có side effect.
- Mốc `ContextRefreshedEvent` không đồng nghĩa với **application readiness**. `ApplicationReadyEvent` là hook của Spring Boot và có semantics cao hơn Spring Core Container.

Ví dụ lọc context nếu listener chỉ dành cho context cụ thể:

~~~java
if (event.getApplicationContext() != expectedContext) {
    return;
}
~~~

Đây là snippet, với `expectedContext` được xác định đúng trong ứng dụng.

## 10. `SmartLifecycle`: start/stop một tiến trình dài hạn

Một job polling, consumer hoặc scheduler cần cả **startup và shutdown**, không chỉ một callback init. `SmartLifecycle` hỗ trợ:

- `start()`: khởi động thành phần.
- `stop()` hoặc `stop(Runnable)`: ngừng thành phần; với shutdown async, gọi callback **sau** khi đã dừng.
- `isRunning()`: trạng thái.
- `isAutoStartup()`: có khởi động khi refresh không.
- `getPhase()`: thứ tự tương đối. **Phase thấp start trước, phase cao stop trước** trong quy trình shutdown điển hình.

~~~java
public final class PollerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        // Đăng ký polling worker qua executor được quản lý.
        running = true;
    }

    @Override
    public void stop() {
        // Dừng polling và đóng tài nguyên theo hợp đồng thực tế.
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là **skeleton minh họa**, không phải worker production vì chưa có executor, queue và xử lý concurrency thực. Cần import `org.springframework.context.SmartLifecycle` và đăng ký bean. Nếu `stop()` asynchronous, không được gọi `callback.run()` trước khi shutdown đã hoàn tất thật. `running=true` cũng không chứng minh business readiness.

## 11. Ví dụ Java 17 chạy được: init ngắn và hai mốc hậu init

Ví dụ độc lập sử dụng Java 17, Maven và Spring Framework 6.2.12. Không dùng Spring Boot, web server hay các công việc async khó đoán stdout.

Cấu trúc thư mục:

~~~text
safe-startup/
├── pom.xml
└── src/main/java/example/SafeStartupDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>safe-startup</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/SafeStartupDemo.java`:

~~~java
package example;

import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;

public final class SafeStartupDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            LocalRules rules = context.getBean(LocalRules.class);
            if (rules.weight("urgent") != 10) {
                throw new IllegalStateException("Unexpected rules");
            }
            System.out.println("6. Main: context refreshed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(initMethod = "prepare")
        public LocalRules localRules() {
            return new LocalRules("vn");
        }

        @Bean
        public StartupHooks startupHooks(LocalRules rules) {
            return new StartupHooks(rules);
        }
    }

    public static final class LocalRules {
        private final String region;
        private Map<String, Integer> weights;

        public LocalRules(String region) {
            this.region = region;
            System.out.println("1. Constructor: region configured");
        }

        @PostConstruct
        public void validate() {
            if (region.isBlank()) {
                throw new IllegalStateException("Region required");
            }
            System.out.println("2. @PostConstruct: validation");
        }

        public void prepare() {
            weights = Map.of("urgent", 10, "normal", 5);
            System.out.println("3. initMethod: local map");
        }

        public int weight(String key) {
            return weights.getOrDefault(key, 0);
        }
    }

    public static final class StartupHooks
            implements SmartInitializingSingleton,
                       ApplicationListener<ContextRefreshedEvent> {
        private final LocalRules rules;

        public StartupHooks(LocalRules rules) {
            this.rules = rules;
        }

        @Override
        public void afterSingletonsInstantiated() {
            if (rules.weight("normal") != 5) {
                throw new IllegalStateException("Rules not ready");
            }
            System.out.println("4. Eager singletons initialized");
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            System.out.println("5. ContextRefreshedEvent received");
        }
    }
}
~~~

Lệnh chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.SafeStartupDemo
~~~

Stdout chính xác từ `System.out.println` của chương trình (không tính log Maven hoặc logger hệ thống):

~~~text
1. Constructor: region configured
2. @PostConstruct: validation
3. initMethod: local map
4. Eager singletons initialized
5. ContextRefreshedEvent received
6. Main: context refreshed
~~~

Giải thích:

1. Spring gọi factory method `localRules()`, factory dùng constructor `LocalRules("vn")`.
2. `@PostConstruct` validate một string thuộc state nội bộ, không lấy bean khác hoặc làm I/O.
3. `initMethod="prepare"` tạo một `Map` nhỏ; lúc này bean hoàn thành các callback nội bộ.
4. `StartupHooks` là singleton eager; `afterSingletonsInstantiated` chạy sau pre-instantiation của các eager singletons, nên `LocalRules` đã sẵn sàng.
5. `ContextRefreshedEvent` được phát trong quá trình refresh của context duy nhất.
6. Sau khi constructor `AnnotationConfigApplicationContext(Config.class)` hoàn tất, `main` mới in dòng 6.

Code phân biệt đúng **local init**, **sau eager singleton initialization** và **context refresh**. Nó không tạo task async nên thứ tự sáu dòng xác định. Nếu thêm executor/thread, thứ tự hoàn tất tùy scheduling và synchronization; không được bịa một stdout cố định.

## 12. Chuyển warmup nguy hiểm ra khỏi local init

**Trước — việc nặng trong callback:**

~~~java
@Component
class ProductCache {
    private final ProductApi api;

    ProductCache(ProductApi api) {
        this.api = api;
    }

    @PostConstruct
    void init() {
        api.downloadFullCatalog();
    }
}
~~~

Đây là phản ví dụ minh họa, không phải file Java standalone. Nếu network chậm, `ProductCache` chưa fully initialized trong suốt thời gian `downloadFullCatalog()` chờ. Remote outage biến thành lỗi bootstrap.

**Sau — init nhẹ, warmup ở hook phù hợp:**

~~~java
@Component
class ProductCache {
    private final ProductApi api;

    ProductCache(ProductApi api) {
        this.api = api;
    }

    @PostConstruct
    void validateLocalState() {
        // Chỉ kiểm tra cấu hình cục bộ.
    }

    void warmup() {
        api.downloadCatalogWithDeadline();
    }
}

@Component
class ProductCacheWarmup implements SmartInitializingSingleton {
    private final ProductCache cache;

    ProductCacheWarmup(ProductCache cache) {
        this.cache = cache;
    }

    @Override
    public void afterSingletonsInstantiated() {
        cache.warmup();
    }
}
~~~

Hai class minh họa yêu cầu type `ProductApi` và import Spring phù hợp. Cách này chuyển external I/O sang mốc sau eager singleton initialization, **nhưng vẫn đồng bộ**: một lần download 2 phút sẽ kéo dài startup 2 phút. Nếu cache optional hoặc warmup rất tốn thời gian, cần managed executor/job và readiness phù hợp. Không giả định `SmartInitializingSingleton` tự chuyển công việc sang background.

## 13. Chọn hook phù hợp từng mục tiêu

| Mục tiêu thật | Lựa chọn | Giới hạn cần nhớ |
| --- | --- | --- |
| Validate config và build local map nhỏ | Constructor/`@PostConstruct`/`initMethod` | Không nên phụ thuộc vào bean khác chưa sẵn sàng |
| Cần gọi collaborator sau khi regular eager singletons hoàn tất | `SmartInitializingSingleton` | Không bao gồm lazy/prototype, vẫn có thể block |
| Cần làm việc ở mốc refresh context | `ContextRefreshedEvent` | Có thể đồng bộ và phát nhiều lần |
| Worker/consumer phải start và stop theo pha | `SmartLifecycle` | Phải quản lý thực tế resource và shutdown callback |
| Logic sau khi Boot đã chạy startup runners | `ApplicationReadyEvent` (Spring Boot) | Không thuộc API Core Container thuần |
| DB migration/seed có phiên bản | Flyway/Liquibase hoặc deployment job | Cần coordination khi nhiều replica |
| Job lớn, retry/cancel, theo dõi tiến độ | Managed executor/job queue | Readiness và policy failure phải tách khỏi local bean init |
| Xử lý của mỗi HTTP request | Request handler/service | Không thể thay bằng application startup callback |

“Sau singleton init” **không bảo đảm mọi external system healthy**. Mỗi lựa chọn có sự khác biệt giữa **bean được tạo xong**, **context refresh xong** và **ứng dụng thực sự sẵn sàng xử lý traffic**.

## 14. Timeout, lỗi startup, idempotence và cleanup

### 14.1. Validation bắt buộc và lỗi tạm thời

- Cấu hình cục bộ không hợp lệ: **fail fast** trong init là hợp lý.
- External API đang outage nhưng có fallback: thường nên báo degraded health và retry có giới hạn; đừng chờ vô hạn trong init.
- Một hạ tầng bắt buộc chưa ready: policy có thể là chặn readiness, giới hạn thời gian startup hoặc từ chối khởi động theo yêu cầu vận hành.

Phải phân biệt lỗi **bắt buộc** với lỗi **recoverable**; đừng nuốt exception rồi tuyên bố “ready” khi chức năng cốt lõi chưa dùng được.

### 14.2. Timeouts

External I/O cần connect timeout, read/request timeout và tổng deadline. Retry nên có giới hạn, backoff và chính sách tránh nhiều replica cùng retry dồn dập. Timeout ngăn treo vô hạn nhưng **không sửa deadlock do chu trình dependency**, vì vậy vẫn phải loại bỏ vòng chờ.

### 14.3. Idempotence

Một `ContextRefreshedEvent` có thể đến nhiều lần khi có context hierarchy hoặc refresh lại. Nhiều instance của ứng dụng có thể đồng thời chạy một job lúc startup. Nếu job tạo bảng, gửi message hay ghi vào DB, cần idempotence, unique key, locking hoặc migration orchestration thích hợp; Spring event không bảo đảm exactly-once cho side effects ngoài JVM.

### 14.4. Cleanup

Thread, executor, subscription, socket và file handle cần owner rõ ràng, shutdown callback và thời gian dừng có giới hạn. Với `SmartLifecycle.stop(Runnable)`, callback phải được gọi **khi đã dừng xong**. Đừng dựa vào `@PreDestroy` như một cơ chế tự dừng mọi thread tự tạo nếu không có code cleanup. Khi startup thất bại giữa chừng, không được mặc định mọi destroy callback trên object khởi tạo dở đều chạy; cần `try/finally` hoặc cơ chế cleanup có kiểm soát.

## 15. Chẩn đoán khi ứng dụng treo ở startup

Khi ứng dụng log “Creating bean ...” mãi không xong, thực hiện:

1. Lấy thread dump; kiểm tra thread khởi động bị kẹt ở `@PostConstruct`, `Future.get()`, DB read, socket read, lock hay call graph nào.
2. Vẽ dependency graph từ bean đang tạo; xác định lệnh gọi nào từ callback làm tạo bean khác hoặc quay lại chính bean ấy.
3. Kiểm tra bean có AOP proxy không; phân biệt raw target và proxy, self-invocation và external invocation.
4. Đo duration của constructor, setters, callbacks, listeners và lifecycle start. Cài timeout trên external I/O.
5. Kiểm tra `refresh()` chưa hoàn tất vì init, `SmartInitializingSingleton` hay synchronous event listener.
6. Nếu thấy warning bean “not eligible for getting processed by all BeanPostProcessors”, xem có BeanPostProcessor nào kéo service tạo quá sớm.
7. Test với API chậm, DB offline, executor không có worker, parent-child contexts, startup failure và shutdown có in-flight task.

Đừng khắc phục startup hang chỉ bằng cách tăng thời gian chờ vô hạn.

## 16. Sai lầm thường gặp

| Triệu chứng | Nguyên nhân điển hình | Sửa thế nào |
| --- | --- | --- |
| Init callback gọi hàng loạt service | Truy cập bean khác quá sớm | Giữ init local; dùng hook hậu eager singleton |
| `BeanCurrentlyInCreationException` | Circular dependency | Tách nhiệm vụ và phá vòng phụ thuộc |
| `@Transactional` vô hiệu trong init | `this` bỏ qua proxy | Gọi collaborator qua Spring proxy sau init |
| `@Async` không async khi gọi nội bộ | Self-invocation | Tách bean, quản lý executor và lifecycle |
| Request proxy lỗi từ startup | Chưa có active request | Chỉ dùng trong HTTP request |
| Boot mất phút để start | DB/network/warmup trong callback | Timeout, chuyển job, readiness |
| Chuyển `@PostConstruct` sang listener nhưng vẫn chậm | Listener thường đồng bộ | Async có quản lý hoặc quy trình job riêng |
| `afterSingletonsInstantiated` không chạy | Bean lazy/prototype | Xem scope và contract của hook |
| Listener chạy hai lần | Context hierarchy/refresh lặp | Lọc context, idempotence |
| Shutdown treo | Worker thiếu stop/cancel hoặc callback shutdown | `SmartLifecycle`, graceful stop có deadline |
| Bean không được auto-proxy | Được tạo quá sớm bởi BeanPostProcessor | Đơn giản hóa processor và dependency |
| Prototype cứ làm I/O ở mỗi lookup | Callback init chạy theo instance | Đưa I/O ra khỏi prototype hoặc cache phù hợp |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Trong `@PostConstruct` gọi `getBean(OtherService.class)` có luôn deadlock không?

**Đáp án:** Không. Nhưng callback nằm trong quá trình tạo bean và có thể kéo dependency chưa initialized, gây vòng phụ thuộc hoặc deadlock. Chỉ sử dụng tương tác local, rõ ràng và ngắn; tránh dynamic bean resolution không cần thiết.

**Câu 2.** Chuyển warmup 90 giây sang `SmartInitializingSingleton` làm startup hoàn tất tức thì?

**Đáp án:** Không. Hook vẫn chạy đồng bộ. Nó giải quyết thời điểm tạo các eager singleton, không tự chạy async.

**Câu 3.** `@EventListener(ContextRefreshedEvent.class)` có bảo đảm chạy đúng một lần và async?

**Đáp án:** Không. Nó có thể chạy đồng bộ và nhận nhiều events/context refresh. Cần cấu hình dispatch và idempotence nếu yêu cầu.

**Câu 4.** Gọi một method `@Transactional` qua `this` từ init callback có chắc có transaction không?

**Đáp án:** Không. Self-invocation bỏ qua advice của proxy-based Spring AOP; bean còn đang initialization.

**Câu 5.** Worker cần start theo thứ tự và stop gracefully. Chọn `@PostConstruct` hay `SmartLifecycle`?

**Đáp án:** `SmartLifecycle`, vì có phase, start, stop và shutdown callback.

**Câu 6.** Bean prototype có `@PostConstruct` gọi external API. Nếu `getBean` 100 lần thì API chỉ gọi một lần?

**Đáp án:** Không. Mỗi prototype instance mới có initialization callback riêng; external I/O có thể lặp 100 lần. Cần chuyển sang mô hình phù hợp với đơn vị trạng thái và cache.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Customizing the Nature of a Bean / Initialization Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Javadoc — SmartInitializingSingleton](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html)
- [Spring Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

# Thất bại khi refresh() và dọn dẹp tài nguyên đã tạo trong Spring ApplicationContext

## 1. Vì sao đây là một phần quan trọng của vòng đời context?

Khi khởi động `ApplicationContext`, Spring cần tải bean definitions, chạy các extension point, tạo những singleton không lazy và hoàn tất các lifecycle callbacks. Nếu một bước thất bại, ứng dụng không thể coi context là đã sẵn sàng. Tuy nhiên, **một phần object có thể đã được tạo và một số tài nguyên có thể đã được mở** trước khi lỗi xảy ra.

Ví dụ:

1. Spring đã tạo một singleton pool, pool mở kết nối và thread nền.
2. Spring tạo service phụ thuộc pool.
3. Trong `@PostConstruct` của service, cấu hình không hợp lệ gây exception.
4. Lần `refresh()` thất bại; phải dọn các bean/tài nguyên đã khởi tạo mà Spring quản lý.
5. Caller vẫn phải đóng hoặc hoàn nguyên những tài nguyên mà Spring chưa kịp quản lý, hoặc đã được tạo ngoài container.

Điểm học tập trọng tâm:

- `refresh()` có cơ chế **hủy các singleton đã được đăng ký** trong nhánh thất bại.
- Container đánh dấu context **không active** khi refresh bị hủy.
- Những đối tượng **chưa hoàn tất khởi tạo**, prototype, tài nguyên tự tạo bên ngoài và side effect ngoại hệ thống **không tự động được rollback hoàn chỉnh**.
- Cần đặt ownership và cleanup logic đúng vị trí, đặc biệt khi init method hoặc `@Bean` factory method có thể throw.

Bài này xét API/hành vi của **Spring Framework 6.2.x**, tập trung vào Spring Core Container. Spring Boot có thể thêm xử lý thất bại khi chạy ứng dụng, đóng context hoặc phát application events riêng; không nên dùng các sự kiện Boot để suy luận mọi đường đi của `AbstractApplicationContext.refresh()`.

## 2. Hợp đồng cơ bản của refresh()

`ConfigurableApplicationContext.refresh()` nạp hoặc làm mới trạng thái cấu hình và khởi tạo container. Javadoc nhấn mạnh: nếu startup thất bại, nó **nên hủy các singleton đã tạo**, nhằm tránh giữ những tài nguyên không còn được sử dụng. Điều này là ý định lifecycle của container, **không phải cam kết hủy bất kỳ tài nguyên Java nào từng được tạo ở nơi nào đó**.

Luồng bình thường, giản lược:

```text
prepareRefresh()
   |
obtainFreshBeanFactory()
   |
prepareBeanFactory()
   |
invokeBeanFactoryPostProcessors()
   |
registerBeanPostProcessors()
   |
initMessageSource(), initApplicationEventMulticaster()
   |
onRefresh(), registerListeners()
   |
finishBeanFactoryInitialization()
   |   +--> preInstantiateSingletons()
   |   +--> tạo bean, inject dependencies, init callbacks
   |
finishRefresh()
   |   +--> lifecycle handling
   +--> ContextRefreshedEvent
```

Một singleton non-lazy có thể mở socket, khởi động pool, load file hoặc tạo thread trong constructor, factory method hoặc init callback. Nếu sau đó một bean khác không thể khởi tạo, Spring sẽ đi vào nhánh xử lý lỗi thay vì công bố lần refresh hoàn tất.

**Mốc quan trọng:** `ContextRefreshedEvent` chỉ là dấu hiệu lần refresh đã đi đến bước publish event; nếu thất bại sớm hơn, listener không được nhận sự kiện đó từ lần refresh đang thất bại. Nếu chính listener throw exception trong lúc publish event đồng bộ, phải xét đến khả năng một số listener trước đó đã nhận event; không suy luận rằng không ai được báo khi listener thất bại ở bước cuối.

## 3. Spring 6.2 xử lý lỗi trong refresh() như thế nào?

Ở phiên bản Spring Framework 6.2.18, `AbstractApplicationContext.refresh()` có một khối `try/catch` bao quanh phần lớn các bước xử lý sau `prepareBeanFactory()`. Nhánh xử lý lỗi cốt lõi tương đương đoạn **mã giả rút gọn**:

```java
try {
    postProcessBeanFactory(beanFactory);
    invokeBeanFactoryPostProcessors(beanFactory);
    registerBeanPostProcessors(beanFactory);
    initMessageSource();
    initApplicationEventMulticaster();
    onRefresh();
    registerListeners();
    finishBeanFactoryInitialization(beanFactory);
    finishRefresh();
} catch (RuntimeException | Error ex) {
    // Spring ghi cảnh báo hủy lần refresh đang thực hiện.
    destroyBeans();
    cancelRefresh(ex);
    throw ex;
}
```

Đây không phải một source file chạy độc lập, và đã lược bỏ tracking/lock cùng các phương thức chuẩn bị khác. Xem [source gắn tag Spring v6.2.18](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java) khi đối chiếu.

Ý nghĩa các hành động:

- **Ghi nhận/throw exception:** nguyên nhân khởi tạo được trả cho caller; startup thất bại không bị che thành thành công.
- **`destroyBeans()`:** trong implementation mặc định, ủy quyền cho `getBeanFactory().destroySingletons()` để hủy **các singleton đang được container quản lý**.
- **`cancelRefresh(ex)`:** chuyển trạng thái `active` về `false` và dọn một số metadata caches của Spring.
- **Không đi tiếp:** những bước bình thường phía sau vị trí lỗi không được chạy.

### Không khẳng định mọi lỗi trong mọi pha đều đi đúng một catch

Cần lưu ý vị trí của khối xử lý trong source theo version. Trong Spring 6.2.18, các lời gọi `prepareRefresh()`, `obtainFreshBeanFactory()` và `prepareBeanFactory()` được thực hiện **trước khối catch nêu trên**. Một exception từ những giai đoạn rất sớm có thể đi theo đường khác hoặc phụ thuộc cách subclass thực hiện việc tải BeanFactory. Vì vậy, câu “mọi failure ở bất kỳ đâu trong refresh đều chắc chắn chạy đủ destroyBeans/cancelRefresh” là quá rộng.

Điểm này đặc biệt quan trọng với custom `ApplicationContext` và việc tải configuration từ file/URL. Nếu công việc tự tạo tài nguyên xảy ra **trước khi BeanFactory sở hữu các singleton tương ứng**, hãy quản lý cleanup tại chính bước chuẩn bị.

### Phân biệt phiên bản Spring

Các phiên bản mới hơn có thể bổ sung bước xử lý riêng trước khi `destroyBeans()` (chẳng hạn điều phối các lifecycle components đã start). Không suy diễn source ở nhánh `main` trên GitHub cho đúng mọi bản Spring 6.2 đã phát hành. Trong bài này, ví dụ kiểm chứng nhánh Spring 6.2.18 và các invariant mà API công bố.

## 4. DestroyBeans chỉ quản lý những gì?

`destroyBeans()` trong `AbstractApplicationContext` triển khai mặc định:

```java
protected void destroyBeans() {
    getBeanFactory().destroySingletons();
}
```

Đây là trích đoạn API rất ngắn nhằm minh họa delegation. `destroySingletons()` xử lý singleton registry, các callback destruction được đăng ký và quan hệ dependency. **Không quét heap**, không tìm mọi object đã từng new và không tự rollback hành động bên ngoài như HTTP request, gửi email, ghi database hay tạo file.

### 4.1. Singleton đã tạo và đăng ký thành công

Một singleton đã khởi tạo đầy đủ, đã được factory nhận quản lý và có destruction metadata phù hợp có thể được gọi:

- Method `@PreDestroy`.
- `DisposableBean.destroy()`.
- Custom `destroyMethod`, bao gồm các method được suy luận theo cấu hình `@Bean` như `close()`/`shutdown()`.
- Callback từ `DestructionAwareBeanPostProcessor` hay extension point hỗ trợ liên quan.

Với nhiều callback trên **cùng bean**, Spring có trình tự lifecycle; với **nhiều bean khác nhau**, quan hệ phụ thuộc sẽ ảnh hưởng thứ tự teardown.

Một class có method `close` chỉ được gọi khi bean definition có cơ chế destruction phù hợp và container thực sự sở hữu destruction của instance đó. `AutoCloseable` là tín hiệu có API close, không phải bằng chứng mọi scope đều được Spring theo dõi.

### 4.2. Bean đang lỗi khi khởi tạo

Giả sử constructor bean chạy xong, nhưng `@PostConstruct` hoặc `initMethod` throw exception. Instance có thể **chưa đến bước đăng ký callback hủy** và chưa được đăng ký là singleton hoàn chỉnh.

Trong luồng `AbstractAutowireCapableBeanFactory.doCreateBean()` của Spring 6.2.18, Spring gọi `populateBean`/`initializeBean` trước, rồi mới `registerDisposableBeanIfNecessary`. Nếu initialization throw, tiến trình thoát trước bước đăng ký destruction thông thường cho bean đó.

Hệ quả thực tiễn: **không dựa vào `@PreDestroy` của chính bean thất bại** để đóng những tài nguyên mà constructor/init method của nó đã mở trước khi throw. Khi bản thân init là điểm có thể thất bại, phải tự cleanup các resource cục bộ trong `catch/finally`.

### 4.3. Bean prototype

Spring tạo và khởi tạo prototype khi caller yêu cầu, nhưng không theo dõi toàn bộ lifecycle destruction sau khi trả về. Một prototype đã được khởi tạo thành công và giữ socket/file không tự được đóng vì context refresh thất bại sau đó.

### 4.4. Đối tượng được tạo ngoài BeanFactory

`new Client()` trong static initializer, startup hook bên ngoài container, thread sinh ra trong factory method trước khi bean được return, temporary file được tạo rồi mất reference, hoặc object do thư viện khác sở hữu đều có thể nằm ngoài singleton registry.

Đừng gắn nhãn chúng là “đã được Spring quản lý” chỉ vì code tạo object đang chạy bên trong một method `@Bean`. Điều kiện quan trọng là object đã **được factory nhận làm instance có lifecycle quản lý** hay chưa.

## 5. Ví dụ Java 17+ hoàn chỉnh: refresh thất bại, singleton được dọn

Ví dụ sử dụng Spring Framework 6.2.18 qua Gradle, không cần Spring Boot. Chúng ta cố ý tạo chuỗi dependency:

```text
BrokenService
    |
    v
   Pool
    |
    v
 Connection
```

`Connection` và `Pool` là singleton đã được tạo thành công. `BrokenService` được construct nhưng init method cố tình throw. Kết quả mong đợi: Spring dọn `Pool` và `Connection` khi hủy refresh. Chúng ta cũng quan sát rằng destruction callback của chính bean `BrokenService` chưa hoàn tất khởi tạo không phải một cơ chế đáng trông đợi.

Cấu trúc dự án:

```text
refresh-failure-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/RefreshFailureDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'refresh-failure-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'RefreshFailureDemo'
}
```

### src/main/java/RefreshFailureDemo.java

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;

public class RefreshFailureDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static final class Connection implements AutoCloseable {
        public Connection() {
            EVENTS.add("connection.created");
        }

        @Override
        public void close() {
            EVENTS.add("connection.closed");
        }
    }

    public static final class Pool implements AutoCloseable {
        private final Connection connection;

        public Pool(Connection connection) {
            this.connection = connection;
            EVENTS.add("pool.created");
        }

        @Override
        public void close() {
            EVENTS.add("pool.closed");
        }
    }

    public static final class BrokenService {
        private final Pool pool;

        public BrokenService(Pool pool) {
            this.pool = pool;
            EVENTS.add("service.created");
        }

        public void initialize() {
            EVENTS.add("service.initialize");
            throw new IllegalStateException("simulated startup failure");
        }

        public void cleanup() {
            EVENTS.add("service.cleanup");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(destroyMethod = "close")
        public Connection connection() {
            return new Connection();
        }

        @Bean(destroyMethod = "close")
        public Pool pool(Connection connection) {
            return new Pool(connection);
        }

        @Bean(initMethod = "initialize", destroyMethod = "cleanup")
        public BrokenService brokenService(Pool pool) {
            return new BrokenService(pool);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        AtomicBoolean refreshedEventSeen = new AtomicBoolean(false);
        context.addApplicationListener(event -> {
            if (event instanceof ContextRefreshedEvent) {
                refreshedEventSeen.set(true);
            }
        });

        context.register(Config.class);
        boolean failed = false;
        try {
            context.refresh();
        } catch (BeansException ex) {
            failed = true;
        } finally {
            // Đóng một context do ta tạo vẫn là thói quen tốt.
            // Trong trường hợp này Spring đã hủy singleton
            // và đánh dấu context inactive khi refresh thất bại.
            context.close();
        }

        EVENTS.forEach(System.out::println);
        System.out.println("refreshFailed=" + failed);
        System.out.println("contextActive=" + context.isActive());
        System.out.println("refreshedEventSeen=" + refreshedEventSeen.get());
        System.out.println("failedBeanCleanupCalled="
                + EVENTS.contains("service.cleanup"));
    }
}
```

Chạy từ thư mục chứa `build.gradle`:

```bash
gradle run --quiet
# Nếu đã có Gradle Wrapper trong dự án:
# ./gradlew run --quiet
```

Các dòng do logic chương trình in ra qua `System.out`:

```text
connection.created
pool.created
service.created
service.initialize
pool.closed
connection.closed
refreshFailed=true
contextActive=false
refreshedEventSeen=false
failedBeanCleanupCalled=false
```

Spring có thể ghi thêm một **WARN log trên stderr hoặc qua logging framework** để thông báo hủy lần refresh. Log đó không thuộc tập `System.out` nêu trên và thông điệp cụ thể có thể thay đổi theo version/log configuration.

### Tại sao kết quả này đáng tin?

1. Bean `BrokenService` yêu cầu `Pool` trong factory method; `Pool` lại yêu cầu `Connection`, nên có quan hệ dependency thực, không cần tin vào thứ tự method `@Bean` viết trong file.
2. Spring đã tạo và đăng ký thành công `Connection` và `Pool` dưới scope singleton mặc định.
3. `initialize()` của `BrokenService` throw `IllegalStateException`. Trong quá trình tạo bean, Spring báo lỗi khởi tạo (thường qua `BeanCreationException`, một subtype của `BeansException`).
4. `AbstractApplicationContext.refresh()` trong đường lỗi này gọi `destroyBeans()`; container dọn singleton đã quản lý. Do `Pool` phụ thuộc `Connection`, hai callback close được thực thi theo dependency teardown phù hợp.
5. `BrokenService` bị lỗi trước khi hoàn tất đăng ký destruction, nên method `cleanup()` của nó không chạy trong trường hợp minh họa.
6. `cancelRefresh()` khiến `context.isActive()` trả `false`. `ContextRefreshedEvent` chưa được phát vì lỗi xảy ra ở vòng tạo singleton.
7. `context.close()` trong `finally` giúp xử lý nhất quán resource ownership từ code gọi; đừng coi lệnh này là nguyên nhân duy nhất đã dọn singleton, vì nhánh lỗi của `refresh()` đã làm việc đó.

**Bảo đảm về phạm vi output:** danh sách này áp dụng cho cấu trúc bean và Spring 6.2.18 trong ví dụ. Nếu thay processor, scope, phiên bản Spring hay cách startup, cần đo lại thay vì giữ nguyên thứ tự log.

## 6. Trường hợp nguy hiểm: init mở tài nguyên rồi mới throw

Trong ví dụ trước, `BrokenService.initialize()` chỉ thêm event rồi throw. Nếu nó tự mở socket, tạo thread, khởi động một remote session hoặc tạo temporary file, destructor của **chính bean khởi tạo thất bại** chưa chắc được đăng ký để Spring gọi.

Ví dụ code **không an toàn**:

```java
public void initialize() throws Exception {
    socket = new Socket(host, port);
    validateRemoteHandshake();  // Có thể throw.
}

// Không thể dựa vào @PreDestroy để chắc chắn
// cleanup cho chính bean init bị lỗi.
@PreDestroy
public void shutdown() throws Exception {
    socket.close();
}
```

Đây là mảnh minh họa, không độc lập; các tên `host`, `port` và `validateRemoteHandshake` thuộc ứng dụng giả định. Nếu validation ném exception trước khi initialization xong, `@PreDestroy` của bean có thể không chạy.

### Giải pháp A: quản lý resource cục bộ trước khi commit state

```java
public void initialize() throws Exception {
    Socket candidate = new Socket(host, port);
    boolean success = false;
    try {
        validateRemoteHandshake(candidate);
        this.socket = candidate;
        success = true;
    } finally {
        if (!success) {
            candidate.close();
        }
    }
}
```

Đây cũng là mảnh minh họa; method `validateRemoteHandshake(Socket)` phải được implement trong ứng dụng. Ý tưởng là chỉ chuyển quyền sở hữu socket từ biến cục bộ sang instance sau khi các bước có thể lỗi hoàn tất. Nếu có nhiều resources thì thiết kế cleanup theo thứ tự ngược khi khởi tạo không thành công.

### Giải pháp B: tách resource thành bean riêng đã được quản lý

Thay vì tạo socket bên trong method init có thể lỗi, tạo một bean resource độc lập có destroy callback rõ ràng và inject vào service. Khi service không init được, bean resource đã tạo thành công sẽ được Spring đưa vào quá trình hủy singleton.

```java
@Bean(destroyMethod = "close")
ClientConnection clientConnection() {
    return ClientConnection.connect();
}

@Bean(initMethod = "verify")
BusinessService businessService(ClientConnection connection) {
    return new BusinessService(connection);
}
```

Đây là mảnh cấu hình, không phải chương trình chạy độc lập. Nếu chính `ClientConnection.connect()` **mở tài nguyên rồi throw trước khi trả object** thì factory method cũng phải cleanup trong nội bộ; Spring chưa nhận được bean thành công để destroy.

### Giải pháp C: try-with-resources với resource có phạm vi thao tác

Với tác vụ ngắn, không nhất thiết biến mọi `AutoCloseable` thành singleton. Có thể cấp resource trong method nghiệp vụ và close bằng `try-with-resources`, hoàn toàn không lệ thuộc vào teardown của context.

```java
try (ClientSession session = clientFactory.openSession()) {
    session.performValidation();
    session.execute();
}
```

Đây là mảnh minh họa, yêu cầu `ClientSession implements AutoCloseable` và có API tương ứng. Cách này làm lifetime rõ ràng ngay cả khi exception xuất hiện.

## 7. Bean factory method throw trước khi return

Một bẫy điển hình khác là đặt code khởi tạo bên trong `@Bean` method:

```java
@Bean(destroyMethod = "close")
ExternalClient client() {
    ExternalClient client = new ExternalClient();
    client.open();
    client.verifySettings(); // Throw sau khi open().
    return client;
}
```

Đây là anti-example minh họa, giả định `ExternalClient` có các method được gọi. `destroyMethod = "close"` **không đủ bảo đảm** cleanup nếu `verifySettings()` throw trước khi `return client`. Container có thể không bao giờ nhận được một bean instance hoàn tất.

Sửa bằng cleanup ngay trong factory method:

```java
@Bean(destroyMethod = "close")
ExternalClient client() {
    ExternalClient candidate = new ExternalClient();
    try {
        candidate.open();
        candidate.verifySettings();
        return candidate;
    } catch (RuntimeException | Error ex) {
        try {
            candidate.close();
        } catch (Exception cleanupError) {
            ex.addSuppressed(cleanupError);
        }
        throw ex;
    }
}
```

Đây là mảnh minh họa; lựa chọn loại exception phải phù hợp API thật. Nếu `open/verify` có checked exceptions, mở rộng cách xử lý tương ứng, ví dụ khai báo `throws Exception` và cleanup tại nhánh catch thích hợp. Ý nghĩa của `addSuppressed`: giữ exception gốc là lý do startup thất bại, đồng thời bảo toàn thông tin lỗi cleanup thứ cấp, tránh che mất nguyên nhân đầu tiên.

Nếu `close()` có thể throw `Error` hoặc những lỗi nghiêm trọng, đừng cố dùng `catch(Throwable)` rồi bỏ qua tất cả. Trong production, test rõ các hợp đồng lỗi của SDK bạn tích hợp.

## 8. Destruction callbacks: thứ tự và giới hạn

Các cơ chế hủy thông thường trong Spring:

- `@PreDestroy`: do processor hỗ trợ lifecycle annotation.
- `DisposableBean.destroy()`: giao diện Spring dành cho bean được quản lý.
- Custom `destroyMethod`: có thể là `close()`, `shutdown()` hoặc method tùy chỉnh.
- `DestructionAwareBeanPostProcessor`: hook cho infrastructure khi bean bị destroy.
- `SmartLifecycle.stop()`: lifecycle orchestration theo phase, phục vụ thành phần cần start/stop có kiểm soát.

Với các callback **khác method name** trong cùng bean đã được quản lý, quy tắc thường gặp là `@PreDestroy` trước `DisposableBean.destroy()`, sau đó custom destroy method.

Quan trọng: **cách container xử lý failed refresh không tương đương một shutdown bình thường của một context active**. Trong Spring 6.2.18, code bắt exception ở `refresh()` thực hiện `destroyBeans()` và `cancelRefresh()`. Nó không đi qua toàn bộ nhánh `doClose()` vốn phát `ContextClosedEvent` và điều phối lifecycle stop thông thường.

Vì thế:

1. **Đừng dựa duy nhất vào `ContextClosedEvent`** để dọn tài nguyên cần hủy khi refresh thất bại.
2. **Đừng dựa duy nhất vào `SmartLifecycle.stop()`** khi failure xảy ra trước lifecycle start hoặc khi version không gọi lifecycle shutdown giống `close()` bình thường.
3. Bean nào thật sự đã đăng ký destroy callbacks vẫn được container dọn theo nhánh failure thích hợp.
4. Code phải tự quản lý side effect xuất hiện trong giai đoạn chưa hoàn tất đăng ký bean.

### Dependency destruction

Nếu A phụ thuộc B và cả hai là singleton đã tạo thành công, Spring cố gắng destroy A **trước** B để A có cơ hội ngừng dùng B trước khi B đóng. Đây là lý do ví dụ `Pool` phụ thuộc `Connection` nhận `pool.closed` trước `connection.closed`.

Đừng suy luận rằng toàn bộ bean không liên quan sẽ destroy theo thứ tự khai báo trong class hoặc thứ tự alphabetical. Kiểm thử sự kiện có ý nghĩa theo quan hệ dependency, không snapshot toàn bộ log framework.

## 9. Close sau refresh thất bại: làm đúng ownership

Với `AnnotationConfigApplicationContext` tạo bằng constructor rỗng, caller thường làm:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
try {
    context.register(AppConfig.class);
    context.refresh();
    // Nếu refresh thành công, sử dụng context.
} finally {
    context.close();
}
```

Đây là mảnh minh họa; giả định `AppConfig` là class `@Configuration` hợp lệ. `close()` trong `finally` là thói quen quản lý resource tốt khi **caller sở hữu context**.

Tuy nhiên, phân biệt hai hoàn cảnh:

- **Refresh thành công, rồi close:** `doClose()` trên context active có thể phát `ContextClosedEvent`, chạy lifecycle stop, destroy singleton, đóng BeanFactory và đánh dấu context inactive.
- **Refresh thất bại trong đường catch thông thường:** `destroyBeans()` và `cancelRefresh()` đã chạy. Khi gọi `close()` lúc active=false, không nên kỳ vọng toàn bộ thứ tự `doClose()` bình thường hoặc phát `ContextClosedEvent`. Đó không phải một “lần shutdown thành công” đầy đủ.

**Không cố gọi `getBean()` sau khi context đã bị hủy refresh** để dùng những singleton “còn sống”. Coi startup là thất bại; không cung cấp context này như một ứng dụng đã sẵn sàng. Một số API query metadata có thể còn phản hồi tùy class context, nhưng điều đó không chứng minh bean graph còn hợp lệ.

### Context có thể refresh lại không?

Không có câu trả lời chung cho mọi `ApplicationContext` implementation:

- Một số loại context hỗ trợ nhiều chu kỳ refresh, với BeanFactory mới hoặc tái cấu trúc.
- `GenericApplicationContext` và `AnnotationConfigApplicationContext` dựa trên một BeanFactory và **không hỗ trợ refresh nhiều lần** theo kiểu thông thường; sau một lần đã khởi tạo, gọi lại có thể ném `IllegalStateException`.
- Nếu startup thất bại, an toàn nhất là **tạo context mới** sau khi sửa nguyên nhân, thay vì cố tái sử dụng object thất bại với resource state còn mơ hồ.

Điều này quan trọng trong integration tests: mỗi test failure nên cô lập ApplicationContext, tránh làm ô nhiễm context cache hoặc dùng lại một failed context giữa các phép thử.

## 10. Context hierarchy và external-owned resources

Ứng dụng có thể có parent/child contexts. Mỗi context quản lý BeanFactory/beans riêng; một bean trong child có thể inject dependency từ parent. Nếu refresh của child thất bại, không nên mặc định rằng Spring sẽ destroy **mọi singleton của parent**. Parent còn có owner và vòng đời độc lập.

Ví dụ hệ thống có shared client từ ngoài container:

```java
@Bean(destroyMethod = "")
SharedClient sharedClient(ExternalRegistry registry) {
    return registry.lookupSharedClient();
}
```

Đây là mảnh minh họa, giả định `SharedClient` và `ExternalRegistry` có trong ứng dụng. Nếu Spring chỉ **mượn** resource, có thể cần tắt inferred `close()`/`shutdown()` bằng `destroyMethod = ""`. Ngược lại, nếu context thật sự sở hữu resource, nên để một destroy method được thực thi khi failed refresh.

### Quy tắc ownership rõ ràng

| Resource | Ai là chủ sở hữu? | Cách cleanup khi startup lỗi |
| --- | --- | --- |
| Singleton resource tạo và đăng ký thành công với context | Spring (nếu thiết kế giao quyền sở hữu cho Spring) | Destroy method/`@PreDestroy`/`DisposableBean` qua destruction pipeline |
| Resource cục bộ mới tạo trong init method còn có thể throw | Method init trước khi commit ownership | `try/finally` hoặc try-with-resources tại chính method |
| Resource vừa tạo trong `@Bean` factory method nhưng chưa return | Factory method | `catch/finally` trước khi throw |
| Prototype đã được cấp cho caller | Caller | Caller `close()`/`destroy()` tường minh |
| External JNDI/shared pool | External owner | Không đóng từ context borrowed; cấu hình ownership/destroy thích hợp |
| File/database/message đã ghi ra hệ thống khác | Hệ thống/transaction điều khiển side effect | Compensation/transaction/rollback explicit khi hợp đồng cho phép |
| Thread do ứng dụng tự start ngoài Spring-managed lifecycle | Code khởi tạo thread | Interrupt, signal, join đúng hợp đồng, đóng các resource thread dùng |

Lưu ý: không có bảng scope nào có thể tự suy ra “mọi resource luôn tự hủy”; cần biết bean thật sự được quản lý đến giai đoạn nào.

## 11. Các dạng failure khác nhau và phạm vi cleanup

| Giai đoạn xảy ra lỗi | Ví dụ | Điều có thể đã xảy ra | Hướng xử lý |
| --- | --- | --- | --- |
| Trước khi có BeanFactory hợp lệ | Environment/property source hoặc load config bị lỗi | Ít hoặc chưa có singleton; có thể có side effect của custom code | Cleanup tại custom loader/preparation và báo root cause |
| BeanDefinitionRegistryPostProcessor | Đăng ký definition sai, conflict | Registry đang đổi; một số processor/dependency có thể tạo sớm | Không tạo business beans trong metadata phase; sửa definitions |
| BeanFactoryPostProcessor | Placeholder thiếu, cấu hình không hợp lệ | Bean instances bình thường chưa được preinstantiate, ngoại lệ có thể tạo sớm | Validate metadata, tránh `getBean()` trong BFPP |
| BeanPostProcessor registration | Processor có dependency quá rộng hoặc constructor lỗi | Infrastructure beans đã tạo một phần | Giữ processors gọn, tránh buộc business singleton tạo sớm |
| Constructor/factory method | Throws sau khi mở socket/file | Đối tượng lỗi chưa hoàn tất quản lý | Cleanup ngay trong factory/constructor wrapper; tách resource owner bean |
| Setter/`@Autowired` dependency | `NoSuchBeanDefinitionException`, circular dependency | Một số dependency singleton đã sẵn sàng | Container destroy singleton đã có; sửa graph |
| `@PostConstruct`/`afterPropertiesSet`/custom init | Invalid config, handshake fail | Bean lỗi đang khởi tạo, dependencies có thể đã đăng ký | Cleanup nội bộ trước khi throw, cộng destruction các dependency singleton |
| `SmartInitializingSingleton` | Validation cuối vòng singleton thất bại | Nhiều singleton có thể đã hoàn tất | Dọn singleton qua failed refresh; không publish readiness |
| `SmartLifecycle`/`finishRefresh` | Startup background consumer hoặc listener ném exception | Có thể đã có worker, một phần subsystem active | Thiết kế stop/cleanup riêng, rà soát behavior Spring version và kiểm thử failure |
| ApplicationEvent listener | Listener đồng bộ ném exception | Một số listener đã thấy event trước khi lỗi | Chọn semantics event/exception rõ ràng; không assume atomic broadcast |

Bảng này mô tả trách nhiệm và rủi ro. Nhánh catch cụ thể phụ thuộc Spring version và vị trí exception, nhất là **trước khối try quản lý destruction**.

## 12. Resource leak không chỉ là “bean chưa close”

Một lần failed refresh có thể để lại các side effect mà `destroySingletons()` không rollback được:

- **HTTP calls** đã gửi sang dịch vụ khác.
- **Message** đã publish ra broker.
- **File** đã ghi lên filesystem.
- **Database updates** đã commit ngoài một transaction được kiểm soát.
- **OS threads** đang chạy nếu ứng dụng tự start mà không gắn termination hook.
- **Scheduled tasks** đã đăng ký với scheduler bên ngoài.
- **Static caches/registries** giữ reference tới bean chưa hoàn tất.
- **ThreadLocal** chứa data chưa reset.

Bất kỳ callback cleanup nào chạy trong một container đang startup thất bại cũng có thể encounter một dependency khác chưa ready. Vì vậy destruction method nên **idempotent, non-blocking trong giới hạn hợp lý, chịu được partial state** và không đòi toàn bộ context active.

### Ví dụ idempotent close

```java
import java.util.concurrent.atomic.AtomicBoolean;

final class SafeHandle implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        // Thực thi cleanup thật, theo ownership của handle.
    }
}
```

Đây là class minh họa độc lập về mặt cú pháp, nhưng `// cleanup thật` cần được triển khai tùy resource. Code cho thấy tránh lặp callback đóng cùng handle trong các đường failure hoặc shutdown. Với resource phức tạp, cần đảm bảo close không đánh dấu “đã dọn sạch” trước khi cleanup thật sự thành công nếu còn cơ chế retry/reconciliation.

### Không nuốt exception gốc

Khi xử lý lỗi init, ưu tiên log root cause đầy đủ, rồi thực hiện cleanup mà không thay thế thông điệp nguyên nhân chính. Dùng `Throwable.addSuppressed` khi cleanup cũng throw trong quá trình xử lý một failure đã tồn tại.

Không trả `null` hay một bean “giả” từ factory method chỉ để tiếp tục refresh nếu dependency cần thiết chưa sẵn sàng; container có thể hoàn thành startup với trạng thái không hợp lệ khó phát hiện hơn.

## 13. Dấu hiệu context đã hủy refresh

Khi Spring xử lý nhánh `cancelRefresh()` chuẩn của 6.2.18, `context.isActive()` trả `false`. Trong ví dụ mục 5, các quan sát:

```text
refreshFailed=true
contextActive=false
refreshedEventSeen=false
failedBeanCleanupCalled=false
```

có ý nghĩa khác nhau:

- `refreshFailed=true`: caller nhận exception và không xem context startup thành công.
- `contextActive=false`: trạng thái lifecycle container đã bị cancel.
- `refreshedEventSeen=false`: đường lỗi xảy ra trước bước hoàn tất lần refresh và phát event.
- `failedBeanCleanupCalled=false`: instance bị lỗi trong init chưa được đăng ký callback destruction để Spring gọi trong tình huống đó.

Đừng dùng chỉ một tín hiệu `isActive()` để kết luận rằng **mọi resource hệ điều hành và remote resource đã được thu hồi**. Để chứng minh điều đó, kiểm tra tài nguyên thật hoặc counters/callbacks từ những owner chịu trách nhiệm.

### Một câu hỏi diagnostic quan trọng

Khi thấy ngoại lệ khởi tạo, hãy hỏi theo thứ tự:

1. **Exception ban đầu từ đâu?** Constructor, factory method, BFPP, BPP, init callback hay một event listener?
2. **Bean nào đã đăng ký thành công?** Tìm dependencies đã tạo trước bean lỗi.
3. **Tài nguyên nào được mở trước khi bean hoàn tất lifecycle?** Chúng có cleanup trong `catch/finally` không?
4. **Có thread hoặc external side effect nào nằm ngoài BeanFactory không?**
5. **Log destruction xuất hiện thật chưa?** Nếu close ném exception, root cause startup có bị che không?
6. **Có phụ thuộc vào `ContextClosedEvent` của failed context không?** Cần kiểm tra lại thiết kế.
7. **Có thao tác retry bằng cùng context instance không?** Nếu có, xem type context hỗ trợ không và liệu state thật sự được reset.

## 14. Unit test và integration test cho nhánh failure

Một unit test của class `BrokenService` có thể gọi `initialize()` và assert exception, nhưng điều đó **không** chứng minh Spring tự destroy dependency singletons lúc `refresh()` thất bại. Để kiểm tra hợp đồng này, cần khởi tạo một `ApplicationContext` thật.

### Kiểm thử có ý nghĩa

- Tạo singleton `Connection` và `Pool` qua BeanFactory; buộc bean phụ thuộc throw trong init.
- Assert caller nhận `BeansException` hoặc cause được kỳ vọng.
- Assert `Connection.close()` và `Pool.close()` đều được gọi đúng một lần theo nghiệp vụ.
- Assert thứ tự cleanup theo dependency: pool trước connection.
- Assert bean init lỗi không bị mặc định xem là đã đăng ký destruction.
- Assert context không active, không publish thành công `ContextRefreshedEvent` trước lỗi.
- Assert client/job ngoài container được dọn bằng owner riêng nếu có.
- Assert khởi tạo thành công vẫn close đúng khi context shutdown bình thường.
- Assert cleanup hoạt động khi init throw lần đầu và nhiều lần (tránh resource leak do retry).
- Assert exceptions của cleanup không làm mất dấu root cause startup.

Đối với ví dụ mục 5, danh sách `EVENTS` có thể biến thành các assertion JUnit 5:

```java
assertTrue(EVENTS.contains("connection.closed"));
assertTrue(EVENTS.contains("pool.closed"));
assertFalse(EVENTS.contains("service.cleanup"));
assertTrue(EVENTS.indexOf("pool.closed")
        < EVENTS.indexOf("connection.closed"));
```

Đây là **mảnh test minh họa**; giả định code test có quyền truy cập `EVENTS` và import các assertion phù hợp. Việc test các event rất nhỏ như trên giúp chứng minh lifecycle đã thực thi, khác với test chỉ kiểm tra `context.isActive()==false`.

Không dùng snapshot nguyên văn toàn bộ Spring WARN log làm hợp đồng kiểm thử: logging nội bộ có thể đổi giữa patch versions.

## 15. Khi nào không dùng refresh() để retry?

Một số ứng dụng có ý định nếu startup fail thì “gọi lại `refresh()` sau vài giây”. Cách này dễ sai:

- Implementation `GenericApplicationContext`/`AnnotationConfigApplicationContext` không dành cho refresh lặp lại sau khi đã khởi tạo.
- Một số resource bên ngoài đã bị hủy, một số khác chưa được hủy, và singleton registry có thể không còn ở trạng thái hợp lệ để tạo lại theo cách mong đợi.
- Custom BeanFactoryPostProcessors có thể đã mutate definitions một lần.
- Static state và global callbacks có thể bị giữ lại từ lần đầu.
- Shutdown hook/lifecycle events trên failed context không phải bộ reset ứng dụng tổng quát.

Nếu muốn resilience khi **dependency ngoài tạm thời chưa sẵn sàng**, cân nhắc tách thành chiến lược retry ở **resource/client layer** có timeout, backoff, retry budget và circuit breaker/health checks thích hợp. Khi initialization phải fail-fast, sửa nguyên nhân và **khởi tạo một context mới** là hướng an toàn hơn.

Đừng retry vô hạn trong `@PostConstruct` và chặn startup mãi nếu ứng dụng không thể quan sát tiến độ hoặc dừng gọn khi shutdown.

## 16. Khác biệt giữa refresh thất bại và close bình thường

| Tiêu chí | Refresh thành công rồi `close()` | Refresh thất bại trong catch của Spring 6.2.18 |
| --- | --- | --- |
| Trạng thái trước shutdown | Context active | Startup bị exception |
| `ContextRefreshedEvent` | Đã được phát ở cuối refresh | Không nếu thất bại trước `finishRefresh()` |
| Đường cleanup chính | `doClose()` | `destroyBeans()` rồi `cancelRefresh()` |
| `ContextClosedEvent` | Phát từ `doClose()` của active context | Không nên kỳ vọng do đường cancel không phải `doClose()` |
| `LifecycleProcessor.onClose()` | Được gọi trong shutdown bình thường | Không được mặc định kỳ vọng trong nhánh catch 6.2.18 |
| Singleton destroy callbacks | Được chạy khi phù hợp | Được cố gắng chạy cho singletons đã quản lý |
| Bean lỗi giữa lúc init | Không áp dụng trong trường hợp startup đã thành công | Có thể chưa đăng ký destructor |
| Prototype destruction | Caller chịu trách nhiệm | Caller vẫn chịu trách nhiệm |
| External side effects | Không tự rollback | Không tự rollback |
| Context active sau thao tác | `false` | `false` nếu đường `cancelRefresh` hoàn tất |

Cần kiểm tra Javadoc/source đúng **version** khi triển khai custom context hoặc thư viện yêu cầu graceful shutdown; đừng áp dụng nhận định 6.2.18 cho mọi release mới.

## 17. Lỗi phổ biến và giải pháp

| Lỗi | Vì sao sai? | Điều chỉnh |
| --- | --- | --- |
| Cho rằng failed refresh không có singleton nào từng được tạo | Có thể đã tạo nhiều dependency singleton trước bean lỗi | Hiểu destroyBeans dọn những singleton đã được quản lý |
| Tin rằng `@PreDestroy` của bean lỗi init luôn chạy | Bean lỗi có thể chưa được đăng ký disposal | Cleanup resource đang mở ngay trong code init khi throw |
| Dựa vào `@Bean(destroyMethod="close")` khi factory method throw trước khi return | Factory chưa giao bean đã tạo xong cho container | Try/finally bên trong factory method |
| Xem `ContextClosedEvent` là điểm cleanup duy nhất | Failed refresh không phải normal close path | Dùng destroy callbacks trên owner bean và cleanup trong failure paths |
| Giữ reference tới bean từ context inactive | Bean graph có thể đã bị destroy một phần | Bỏ context thất bại, tạo context mới |
| Dùng `getBean()` trong BeanFactoryPostProcessor để “kiểm tra sẵn sàng” | Tạo instance quá sớm, thiếu processors | Kiểm tra metadata hoặc dùng hook đúng sau initialization |
| Mở resource trong constructor rồi để `@PreDestroy` xử lý nếu constructor throw | Container không nhận object tạo thành công | Tạo resource trong một factory wrapper có cleanup rõ ràng |
| Close external shared client trong failed refresh | Ownership thuộc application server/registry khác | Dùng destroyMethod rỗng nếu phù hợp, tránh các callback khác cũng close |
| Không test cleanup khi callback throw | Rò rỉ hoặc mất root cause | Test failure injection + suppressed exceptions |
| Assume mọi phiên bản Spring tự stop mọi SmartLifecycle khi refresh fail | Nhánh code có thể khác theo version và timing | Đọc source đúng phiên bản; thiết kế teardown idempotent |
| Gọi lại `refresh()` trên cùng `AnnotationConfigApplicationContext` | Không phải refreshable multi-cycle context | Khởi tạo context mới |
| Kết luận “không leak” chỉ từ `isActive=false` | Active là state của context, không đo socket/thread/file | Đo resource thật, callback count, liveness của worker |

## 18. Hướng thiết kế an toàn cho hệ thống thực

1. **Tách ownership thành các bean nhỏ:** database connection pool, HTTP client, executor và message consumer nên có một owner có lifecycle rõ ràng. Khi một service phía sau fail, Spring có thể destroy owner đã được tạo thành công.
2. **Init chỉ commit state khi đã thành công:** mọi resource mở trong init phải được bảo vệ bằng cleanup cục bộ nếu có bước sau đó throw.
3. **Tắt cleanup chỉ khi resource là borrowed:** `@Bean(destroyMethod = "")` có ích khi container không sở hữu external resource; nó không tự tắt `@PreDestroy`/`DisposableBean` nếu bean còn những callback đó.
4. **Không lạm dụng init callback để start thread ngay:** `SmartLifecycle` hoặc một cơ chế start/stop rõ ràng có thể phù hợp hơn, nhưng vẫn phải thiết kế failure cleanup theo version/thời điểm.
5. **Đừng để shutdown phụ thuộc vào context còn active:** destruction method của bean có thể được gọi khi container đang cancel; hạn chế `getBean()` tùy ý trong destroy.
6. **Dùng dependency graph thay vì thứ tự khai báo:** bean cần resource khác thì khai báo dependency thật bằng constructor/factory args, giúp Spring biết quan hệ destroy.
7. **Giữ nguyên nhân lỗi:** log tên bean và root cause; nếu cleanup cũng fail, lưu thông tin suppressed error.
8. **Test cả fail-fast và partial-success:** một test chỉ cho fail trước khi bất kỳ bean nào được tạo không chứng minh Spring cleanup ở trạng thái khó nhất.

## 19. Tóm tắt quy tắc tư duy

Có thể đặt ra ba câu hỏi cho mỗi tài nguyên có thể đã được tạo trong `refresh()`:

**Thứ nhất, ai đang sở hữu nó?** Nếu Spring đã tạo và đăng ký nó như singleton được quản lý, Spring có thể gọi destruction callback khi cancel refresh. Nếu resource do method local hoặc container khác sở hữu, ownership không tự chuyển chỉ vì code nằm trong Spring app.

**Thứ hai, object đã hoàn tất creation chưa?** Một init callback ném lỗi khiến object không được hoàn tất đăng ký destruction theo dòng xử lý bình thường; cleanup của chính object đó phải được thiết kế cục bộ.

**Thứ ba, failure xảy ra ở pha nào?** Trong Spring 6.2.18, khối catch chịu trách nhiệm `destroyBeans()`/`cancelRefresh()` bao quanh phần lớn hoạt động sau `prepareBeanFactory()`, không thể áp dụng vô điều kiện cho mọi exception sớm trước pha đó.

Nếu cả ba câu hỏi được trả lời rõ ràng, bạn có thể kiểm chứng startup failure mà không nhầm giữa trạng thái context đã hủy và resource bên ngoài đã thực sự được giải phóng.

## 20. Nguồn chính thức

- [Spring Framework 6.2.18 — AbstractApplicationContext.refresh() source](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java): vị trí try/catch, `destroyBeans()`, `cancelRefresh()` và khác biệt với `doClose()`.
- [Spring Framework 6.2.18 — AbstractAutowireCapableBeanFactory.doCreateBean() source](https://github.com/spring-projects/spring-framework/blob/v6.2.18/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java): `populateBean`/`initializeBean` trước `registerDisposableBeanIfNecessary`.
- [Spring Framework 6.2 — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): hợp đồng refresh failure, `destroyBeans`, `cancelRefresh`, `doClose`.
- [Spring Framework 6.2 — ConfigurableApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): ý nghĩa startup, refresh và close.
- [Spring Framework Reference — Bean lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean` và custom destruction.
- [Spring Framework Reference — Bean scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton và prototype destruction semantics.

**Điểm cần nhớ:** thất bại trong `refresh()` kích hoạt cleanup theo phạm vi bean mà container đã quản lý; mã ứng dụng vẫn chịu trách nhiệm đóng tài nguyên mở trước khi bean tạo xong và hoàn nguyên các side effects nằm ngoài BeanFactory.

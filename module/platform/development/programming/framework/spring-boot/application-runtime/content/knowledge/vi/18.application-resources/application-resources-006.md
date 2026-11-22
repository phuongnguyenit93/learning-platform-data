# Giải phóng tài nguyên khi khởi tạo mới hoàn tất một phần

## Mục tiêu học tập

Một thành phần ứng dụng có thể **khởi tạo được một phần rồi thất bại**: đã mở connection nhưng tạo subscription lỗi; đã mở file nhưng bước parse ném exception; đã tạo thread pool nhưng đăng ký worker thất bại; đã cấp phát cache nhưng xác thực cấu hình không qua. Đó là *partial initialization*. Nếu chỉ chờ đến lúc Spring đóng ứng dụng mới gọi `@PreDestroy`, những tài nguyên phát sinh trước khi bean hoàn tất có nguy cơ không được giải phóng.

Trong Spring Boot Application Runtime, nhóm **Tài nguyên ứng dụng**, vấn đề cốt lõi là quản lý **quyền sở hữu (ownership)** của tài nguyên tại từng giai đoạn, đặc biệt khi constructor, factory `@Bean`, `@PostConstruct`, `InitializingBean` hoặc `SmartLifecycle.start()` có thể thất bại.

Sau bài này, bạn sẽ biết cách:

1. Xác định chính xác tài nguyên nào đã mở khi initialization ném exception.
2. Phân biệt **cleanup trong đường khởi tạo thất bại** với **destroy callback của bean đã tạo thành công**.
3. Dùng `try/catch`, `finally`, `try-with-resources` và `Throwable.addSuppressed(...)` để dọn tài nguyên an toàn.
4. Đóng tài nguyên **ngược thứ tự mở** và không để lỗi cleanup che mất lỗi ban đầu.
5. Thiết kế **ownership transfer** từ factory sang managed bean **chỉ khi toàn bộ initialization đã thành công**.
6. Dùng `@Bean(destroyMethod = "close")` và `@PreDestroy` đúng phạm vi, không dựa vào chúng khi factory chưa trả về bean hoặc init method chưa hoàn tất.
7. Chạy project **Java 17+ / Spring Boot 3.3.13 / Gradle** với ba kịch bản: thành công, lỗi sau tài nguyên thứ nhất, lỗi sau tài nguyên thứ hai.
8. Thiết kế rollback cho constructor, bean initialization, `SmartLifecycle.start()`, runner và resource ngoài JVM; kiểm thử bằng failure injection.

**Phạm vi phiên bản:** Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+. Ví dụ dùng Spring Boot 3.3.13. Không đánh đồng các callback đóng **bootstrap context** trong startup với việc **application context** đóng khi shutdown.

## 1. Partial initialization là gì?

Giả sử một client cần ba bước:

~~~text
createClient()
    |
    +-- openConnection()             [THÀNH CÔNG]
    |
    +-- registerSubscription()       [THÀNH CÔNG]
    |
    +-- verifyCredentials()          [THẤT BẠI]
    |
    +-- return client                [KHÔNG CHẠY]
~~~

Khi xác thực thất bại, chương trình có thể không có một client đã được tạo thành công, nhưng hai tài nguyên **connection** và **subscription** đã tồn tại. Để mặc chúng hoạt động là rò rỉ; đóng connection mà quên hủy subscription cũng có thể để lại trạng thái ngoài ý muốn.

**Nguyên tắc:** Mỗi bước mở tài nguyên thành công phải đi kèm một kế hoạch đóng tài nguyên ấy nếu bất kỳ bước tiếp theo nào thất bại.

### Những loại tài nguyên dễ bị bỏ quên

| Tài nguyên | Ví dụ khởi tạo dở | Hậu quả |
| --- | --- | --- |
| `InputStream`, `FileChannel` | Đọc file A được, file B lỗi | File descriptor/lock còn giữ |
| `Socket`/HTTP client | Mở socket được, cấu hình TLS lỗi | Socket hoặc worker nội bộ còn sống |
| JDBC connection | Borrow connection rồi tạo statement lỗi | Rò connection trong pool |
| Executor và thread | Tạo pool rồi đăng ký job lỗi | Thread treo hoặc JVM không thoát |
| Message consumer | Subscribe xong, tạo handler lỗi | Poll/ack sai hoặc listener mồ côi |
| Temporary file | Tạo staging file rồi ghi lỗi | File rác, tốn disk hoặc lộ dữ liệu |
| Timer, callback | Đăng ký listener xong, init tiếp lỗi | Callback vẫn chạy trên object chưa hoàn chỉnh |
| Remote lease/resource | API create thành công nhưng bước confirm lỗi | Tài nguyên bên ngoài không tự biến mất |

Các nhóm tài nguyên có cách rollback khác nhau. Socket có thể đóng bằng `close()`; bản ghi từ xa cần API delete/compensate; task chạy nền có thể cần stop signal, cancellation và join có timeout. Không có một lời gọi `close()` chung đủ giải quyết mọi tình huống.

## 2. Ownership: ai chịu trách nhiệm ở thời điểm nào?

Hãy hình dung một nhà máy tạo bean:

~~~text
Factory bắt đầu create()
    |
    +-- Mở tài nguyên A   (factory đang sở hữu)
    +-- Mở tài nguyên B   (factory đang sở hữu)
    +-- Kiểm tra invariant
          |
          +-- LỖI
          |     └-- Factory đóng B, đóng A, ném lại lỗi gốc
          |
          +-- THÀNH CÔNG
                |
                └-- Trả managed bean và chuyển ownership
                      |
                      +-- Bean được sử dụng bình thường
                      |
                      └-- Khi Spring hủy bean: bean.close()
~~~

Có hai đường cleanup độc lập:

- **Rollback trong initialization:** factory hoặc method init đã mở tài nguyên phải tự dọn nếu không thể hoàn tất.
- **Normal destruction:** bean đã được tạo và Spring quản lý được dọn khi context đóng hoặc bean bị destroy theo lifecycle thích hợp.

Thời điểm **commit ownership** thường là lúc factory trả về object hoàn chỉnh, sau khi đã kiểm tra được những điều kiện cần thiết mà factory chịu trách nhiệm. Nếu bên ngoài factory còn có `@PostConstruct`/BeanPostProcessor có thể fail, chính giai đoạn đó cũng cần chiến lược cleanup cho resource của nó.

### Hai lỗi đối nghịch

**Resource leak:** Factory nghĩ Spring sẽ tự dọn connection mặc dù `@Bean` factory throw trước khi trả object cho container.

**Close quá sớm:** Factory dùng `try-with-resources` bao connection rồi trả về object giữ connection; khi scope kết thúc, connection đã bị đóng trước khi caller sử dụng.

Bởi vậy, cùng một tài nguyên **không được vừa “chuyển ownership” vừa “tự động close” ở scope cũ**, trừ khi có thiết kế chia sẻ reference/lease rõ ràng.

## 3. Constructor, @Bean, @PostConstruct và @PreDestroy không phải một mốc

Trong một bean Spring thông thường, các bước khái niệm:

~~~text
Spring chọn bean definition
    |
    +-- Constructor hoặc @Bean factory method
    +-- Giải quyết dependency và injection
    +-- BeanPostProcessor trước initialization
    |    └-- @PostConstruct (khi có processor phù hợp)
    +-- InitializingBean.afterPropertiesSet()
    +-- Custom init method (nếu có)
    +-- BeanPostProcessor sau initialization
    |
    +-- Bean hoàn tất creation / usable
    |
    +-- Normal destruction khi context đóng
         ├-- @PreDestroy
         ├-- DisposableBean.destroy()
         └-- Custom destroy method (nếu có)
~~~

Sơ đồ rút gọn, không bao quát mọi `FactoryBean`, proxy hay scope. Điểm quan trọng: **constructor đã trả về không có nghĩa bean init xong**; `@PostConstruct` vẫn có thể thất bại.

Spring Framework hỗ trợ các callback hủy cho bean do nó quản lý, nhưng **không được xem callback hủy của chính bean chưa hoàn tất initialization là bảo đảm để giải phóng mọi tài nguyên nó đã mở trước khi lỗi**.

### Ví dụ dễ rò rỉ

~~~java
@Component
class DangerousSubscriber {

    private Socket socket;

    @PostConstruct
    void initialize() throws IOException {
        socket = new Socket("localhost", 8080);
        configureProtocol(socket); // có thể throw
    }

    @PreDestroy
    void destroy() throws IOException {
        if (socket != null) {
            socket.close();
        }
    }
}
~~~

Đây là **snippet minh họa vấn đề**, không phải file độc lập: cần imports `Component`, `PostConstruct`, `PreDestroy`, `Socket`, `IOException` và định nghĩa `configureProtocol`. Nếu `configureProtocol` lỗi, bean có thể chưa hoàn tất initialization. Dù có `@PreDestroy`, thiết kế đúng là **tự đóng socket ngay trong catch của init method**.

### Mẫu init an toàn hơn

~~~java
@PostConstruct
void initialize() throws IOException {
    Socket newlyOpened = new Socket("localhost", 8080);

    try {
        configureProtocol(newlyOpened);
        socket = newlyOpened; // Chỉ publish state khi thành công.
    }
    catch (IOException | RuntimeException original) {
        try {
            newlyOpened.close();
        }
        catch (IOException closeFailure) {
            original.addSuppressed(closeFailure);
        }
        throw original;
    }
}
~~~

Đây là **method minh họa** trong class có field `socket` và method `configureProtocol`. Nếu `configureProtocol` đã tạo thêm resource nội bộ rồi throw trước khi trả handle, trách nhiệm dọn tài nguyên nội bộ đó nằm ở chính code của nó. Caller không thể close một handle mình chưa nhận được.

## 4. Vì sao @Bean(destroyMethod = "close") chưa đủ?

Một method:

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

cho Spring biết dùng `close()` khi destroy **bean được tạo và quản lý thành công**. Nhưng nếu factory làm nhiều việc trước `return`:

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    Connection connection = openConnection();
    Subscription subscription =
            openSubscription(connection); // có thể throw
    return new ExternalClient(connection, subscription);
}
~~~

thì khi `openSubscription` throw, container chưa nhận được object `ExternalClient` hoàn chỉnh. Không có bảo đảm Spring sẽ tự đóng connection do local variable của factory giữ.

**Hướng đúng:** Ghi nhận từng handle ngay sau khi mở thành công, bao bọc các bước tiếp theo trong `try/catch` và cleanup những handle đã có trước khi ném lại exception.

~~~java
@Bean(destroyMethod = "close")
ExternalClient externalClient() {
    Connection connection = openConnection();
    Subscription subscription = null;

    try {
        subscription = openSubscription(connection);
        validate(subscription);
        return new ExternalClient(connection, subscription);
    }
    catch (RuntimeException original) {
        closeSuppressing(subscription, original);
        closeSuppressing(connection, original);
        throw original;
    }
}
~~~

Đây là **minh họa**, không có các định nghĩa `Connection`/`Subscription`/`ExternalClient`/`closeSuppressing`. Ví dụ hoàn chỉnh ở mục 9 dùng fake resource thật sự có `close()` để minh họa cả hai điểm lỗi.

**Lưu ý về constructor:** Nếu constructor `new ExternalClient(connection, subscription)` còn thực hiện I/O dễ fail, ownership trở nên mơ hồ. Tốt hơn là constructor chỉ gán các field đã kiểm tra; mọi bước có thể thất bại được thực hiện **trước khi chuyển ownership**.

## 5. Thứ tự cleanup nên ngược thứ tự khởi tạo

Ví dụ dependency:

~~~text
open connection
    └-- open session dùng connection
          └-- open consumer dùng session
~~~

Khi rollback:

~~~text
close consumer
close session
close connection
~~~

Consumer có thể cần session để flush/ack, session có thể cần connection để kết thúc giao dịch. Đóng connection trước có thể làm hỏng cleanup của consumer. Với những tài nguyên độc lập, vẫn nên định nghĩa thứ tự rõ ràng để code dễ dự đoán.

### Cleanup lỗi không được làm mất lỗi gốc

Anti-pattern:

~~~java
try {
    initializeSecondaryResource();
}
finally {
    primaryResource.close(); // Nếu close cũng throw, có thể che lỗi init.
}
~~~

Với Java, lỗi phát sinh trong `finally` có thể che exception đang được truyền ra. Một mẫu thủ công an toàn:

~~~java
try {
    initializeSecondaryResource();
}
catch (Exception original) {
    try {
        primaryResource.close();
    }
    catch (Exception closeFailure) {
        if (closeFailure != original) {
            original.addSuppressed(closeFailure);
        }
    }
    throw original;
}
~~~

Đây là **mã trong một method có `throws Exception`**, giả định `primaryResource` là `AutoCloseable`. `Throwable.addSuppressed(...)` giữ lỗi cleanup ở `getSuppressed()` trong khi exception ban đầu vẫn là nguyên nhân chính.

### Helper cleanup dùng được cho nhiều resource

~~~java
static void closeOnFailure(
        AutoCloseable resource, Throwable original) {

    if (resource == null) {
        return;
    }

    try {
        resource.close();
    }
    catch (Exception | Error cleanupFailure) {
        if (cleanupFailure != original) {
            original.addSuppressed(cleanupFailure);
        }
    }
}
~~~

Helper minh họa có thể đặt trong factory class. Cần bảo đảm **vẫn cố close resource còn lại** ngay cả khi một lần close đã throw.

Giữ `Error` trong multi-catch giúp minh họa cleanup ngay cả khi một lỗi nghiêm trọng xảy ra trong initialization. Với các `VirtualMachineError` như OOM, JVM có thể không đủ điều kiện để cleanup đáng tin cậy; không hứa mọi tài nguyên đều được dọn dưới mọi tình huống lỗi VM.

## 6. try-with-resources: dùng đúng phạm vi sống

`try-with-resources` là lựa chọn tốt khi tài nguyên chỉ cần **trong một method hoặc block**:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    byte[] bytes = in.readAllBytes();
    return decode(bytes);
}
~~~

Đây là **snippet** cần imports `InputStream`, `Files`, `Path` và method `decode`. Java tự đóng `in` khi rời block, kể cả khi đọc hoặc giải mã lỗi. Với nhiều resource trong header, Java đóng **ngược thứ tự khai báo** và giữ exception từ body làm primary nếu close cũng throw.

### Bẫy ownership transfer

~~~java
Client createClient() throws IOException {
    try (Socket socket = new Socket("localhost", 8080)) {
        return new Client(socket); // SAI nếu Client còn cần socket.
    }
}
~~~

Đây là **anti-pattern**; cần định nghĩa `Client` và imports. `return` không ngăn `try-with-resources` chạy cleanup. Khi method trả về, socket đã đóng.

Nếu resource phải sống cùng bean Spring, cần một **factory có rollback khi fail**, sau đó chuyển ownership cho bean hoàn chỉnh và cấu hình destroy callback. Không dùng scope ngắn hơn lifetime thực của resource.

### Khi chỉ một phần resource thuộc về bean

Một factory có thể mở file cấu hình để đọc dữ liệu rồi đóng file, nhưng kết quả của parse được lưu trong bean. Khi đó file stream **không chuyển ownership**; `try-with-resources` là phù hợp. Ngược lại, kết nối mạng cần giữ để xử lý runtime là resource dài hạn; cần được đóng ở bean destruction.

## 7. Không publish đối tượng chưa hoàn chỉnh

Một object khởi tạo dở không chỉ gây resource leak mà còn có thể tạo lỗi concurrency nếu được publish quá sớm.

~~~java
class UnsafeClient {
    UnsafeClient() {
        GlobalRegistry.register(this);
        openSocket();
        subscribeToEvents(); // có thể fail
    }
}
~~~

Đây là snippet minh họa, thiếu helper definitions. Nếu subscription fail, registry có thể giữ một object chưa hợp lệ, và thread khác có thể gọi phương thức của nó.

Cách phòng tránh:

1. Không đưa `this` vào registry/worker thread từ constructor khi chưa hoàn tất invariant.
2. Mở tài nguyên trong biến local, kiểm tra đủ điều kiện rồi mới trả về object và publish cho hệ thống.
3. Nếu đã đăng ký listener hoặc timer trước khi fail, phải **unregister/cancel** đúng API.
4. Nếu đã tạo thread, phải stop signal, interrupt/join theo deadline; không coi một boolean đã đổi là thread chắc chắn dừng.
5. Với object được dùng đa luồng, thiết kế safe publication và state transitions, không chỉ dựa vào `final` fields hay `volatile` một cách ngẫu nhiên.

**Cần phân biệt:** Spring bean được tạo thành công về mặt Java chưa có nghĩa đã đủ điều kiện nghiệp vụ. Sau factory return, `@PostConstruct`, BeanPostProcessor hoặc một bước start có thể tiếp tục thay đổi trạng thái. Từng điểm có side effect phải có đường rollback tương ứng.

## 8. Checklist trước khi viết factory nhiều bước

| Câu hỏi | Ý nghĩa |
| --- | --- |
| Bước nào mở socket/file/connection/thread? | Xác định acquisition points |
| Handle được trả về và ghi nhận ở đâu? | Đảm bảo có cách close nếu bước sau fail |
| Resource B có cần A để close không? | Xác định reverse cleanup order |
| Exception nào có thể xảy ra ở mỗi bước? | Thiết kế catch/throws đúng |
| Close có thể throw không? | Không để cleanup che lỗi init |
| Bao giờ ownership chuyển sang bean? | Không close quá sớm, không quên close |
| Bean được destroy bằng cơ chế nào? | `@PreDestroy`, `destroyMethod`, lifecycle |
| Callback init có chạy sau factory return không? | Không quên lỗi `@PostConstruct` |
| Có state được publish trước success không? | Tránh expose object nửa chừng |
| Nếu close gọi hai lần thì sao? | Idempotency/state machine |
| Nếu init được retry thì sao? | Không giữ lại connection/thread của lần fail |
| Nếu JVM bị kill thì sao? | TTL, recovery, reconciliation ngoài JVM |

Với logic có nhiều bước phức tạp, dùng **builder/rollback stack** hoặc component sở hữu tài nguyên rõ ràng thay vì rải rác `close()` trong nhiều nhánh `if`.

## 9. Project chạy được: Spring Boot đóng tài nguyên trên đường success và partial failure

Project này dùng **Java 17+**, **Spring Boot 3.3.13** và Gradle, là một ứng dụng CLI **non-web**. Ta tạo bean `ManagedPipeline` cần hai resource giả lập:

1. `connection`.
2. `subscription` dựa trên connection.

Có ba chế độ:

- `--demo.fail-at=none`: mở cả hai thành công; Spring gọi `ManagedPipeline.close()` khi context đóng.
- `--demo.fail-at=connection`: fail ngay sau khi mở connection, trước khi mở subscription; factory tự đóng connection.
- `--demo.fail-at=subscription`: fail sau khi cả hai đã mở; factory đóng subscription rồi connection.

Vì resource chỉ in log và không dùng mạng thật, không có random timing hoặc race từ I/O bên ngoài. Mỗi trường hợp cho thứ tự log có thể giải thích và test.

### 9.1. Cấu trúc thư mục

~~~text
partial-resource-cleanup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cleanup/
    └── PartialResourceApplication.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'partial-resource-cleanup-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.cleanup.PartialResourceApplication'
}
~~~

Cần JDK 17+ và Gradle tương thích với Spring Boot 3.3. Nếu có Gradle Wrapper, có thể dùng wrapper thay `gradle`. Mẫu không tạo wrapper sẵn và không cần `spring-boot-starter-web`.

### 9.2. Full Java source

**`src/main/java/com/example/cleanup/PartialResourceApplication.java`:**

~~~java
package com.example.cleanup;

import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PartialResourceApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PartialResourceApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: context started");
        }
        catch (RuntimeException failure) {
            System.out.println("MAIN: startup failed");
            // Không nuốt lỗi thành một lần startup thành công.
            throw failure;
        }

        System.out.println("MAIN: context closed");
    }

    @Bean(destroyMethod = "close")
    ManagedPipeline managedPipeline(
            @Value("${demo.fail-at:none}") String failAt) {

        return ManagedPipeline.create(failAt);
    }

    public static final class ManagedPipeline
            implements AutoCloseable {

        private final TrackedResource connection;
        private final TrackedResource subscription;
        private final AtomicBoolean closed = new AtomicBoolean();

        private ManagedPipeline(
                TrackedResource connection,
                TrackedResource subscription) {
            this.connection = connection;
            this.subscription = subscription;
        }

        public static ManagedPipeline create(String failAt) {
            // Validate trước khi mở resource.
            if (!Set.of("none", "connection", "subscription")
                    .contains(failAt)) {
                throw new IllegalArgumentException(
                        "Unknown demo.fail-at: " + failAt);
            }

            TrackedResource connection = null;
            TrackedResource subscription = null;

            try {
                connection = TrackedResource.open("connection");

                if ("connection".equals(failAt)) {
                    System.out.println(
                            "INIT: failure after connection");
                    throw new IllegalStateException(
                            "Simulated connection-stage failure");
                }

                subscription = TrackedResource.open("subscription");

                if ("subscription".equals(failAt)) {
                    System.out.println(
                            "INIT: failure after subscription");
                    throw new IllegalStateException(
                            "Simulated subscription-stage failure");
                }

                System.out.println("INIT: completed");

                // Ownership chỉ chuyển khi mọi bước đã thành công.
                return new ManagedPipeline(connection, subscription);
            }
            catch (RuntimeException | Error original) {
                closeOnFailure(subscription, original);
                closeOnFailure(connection, original);
                throw original;
            }
        }

        private static void closeOnFailure(
                AutoCloseable resource, Throwable original) {

            if (resource == null) {
                return;
            }

            try {
                resource.close();
            }
            catch (Exception | Error cleanupFailure) {
                if (cleanupFailure != original) {
                    original.addSuppressed(cleanupFailure);
                }
            }
        }

        @Override
        public void close() {
            if (!closed.compareAndSet(false, true)) {
                return;
            }

            // Resource giả lập không throw trong close().
            try {
                subscription.close();
            }
            finally {
                connection.close();
            }
        }
    }

    public static final class TrackedResource
            implements AutoCloseable {

        private final String name;
        private final AtomicBoolean closed = new AtomicBoolean();

        private TrackedResource(String name) {
            this.name = name;
            System.out.println("RESOURCE: " + name + " opened");
        }

        public static TrackedResource open(String name) {
            return new TrackedResource(name);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("RESOURCE: " + name + " closed");
            }
        }
    }
}
~~~

### 9.3. Vì sao code này không rò tài nguyên trong kịch bản demo?

**Tại factory:**

- `ManagedPipeline.create` kiểm tra mode trước khi mở resource.
- Connection được mở và gán cho local variable. Nếu bước kế tiếp lỗi, factory vẫn có handle để close.
- Subscription được mở sau đó và cũng gán vào local variable.
- Nếu lỗi ở bước validation sau subscription, `catch` đóng subscription **trước** connection.
- `closeOnFailure` không để lỗi cleanup thay thế lỗi gốc; nó dùng `addSuppressed`.
- Chỉ sau khi tạo xong cả hai tài nguyên, factory trả về `ManagedPipeline` chứa hai final fields. Từ thời điểm đó, bean sở hữu tài nguyên.

**Tại Spring:**

- `@Bean(destroyMethod = "close")` cho Spring gọi `ManagedPipeline.close()` khi bean đã tạo thành công và context hủy bình thường.
- Nếu factory ném exception trước `return`, bản thân factory đã cleanup; không dựa vào destruction callback của bean chưa tồn tại.
- `AtomicBoolean` trong demo giúp close chỉ in một lần nếu bị gọi lặp. Đây là hình thức idempotency đơn giản; production có thể cần state machine rõ hơn khi cleanup có thể thất bại.

**Tại main:**

- Chương trình non-web dùng `try-with-resources` cho **application context**, không đóng connection trực tiếp.
- Khi startup fail, `app.run(args)` ném exception; code in `MAIN: startup failed` rồi ném lại. Lệnh Gradle có thể exit non-zero.
- Khi startup thành công, context được đóng khi ra khỏi `try`, khiến Spring gọi destroy method.

### 9.4. Chạy thành công

~~~bash
gradle bootRun --args="--demo.fail-at=none"
~~~

**Các dòng do code Java tự in**, bỏ qua log của Spring/Gradle:

~~~text
RESOURCE: connection opened
RESOURCE: subscription opened
INIT: completed
MAIN: context started
RESOURCE: subscription closed
RESOURCE: connection closed
MAIN: context closed
~~~

Giải thích:

1. Bean singleton `managedPipeline` được tạo eager trong `ApplicationContext.refresh()`.
2. Factory mở connection rồi subscription và in `INIT: completed`.
3. `SpringApplication.run(...)` trả về, main in context started.
4. `try-with-resources` đóng context. Spring gọi `ManagedPipeline.close()` và đóng subscription rồi connection.
5. Main in context closed sau khi context.close hoàn thành.

### 9.5. Lỗi sau tài nguyên thứ nhất

~~~bash
gradle bootRun --args="--demo.fail-at=connection"
~~~

Dòng in bởi chính Java code:

~~~text
RESOURCE: connection opened
INIT: failure after connection
RESOURCE: connection closed
MAIN: startup failed
~~~

Không có subscription vì bước mở thứ hai chưa chạy. Không có `MAIN: context started` vì startup không hoàn tất. Spring/Gradle có thể in thêm stack trace và thông báo build thất bại. **Connection được đóng trong catch của factory**, không phải bởi destroy method trên một bean hoàn chỉnh.

### 9.6. Lỗi sau tài nguyên thứ hai

~~~bash
gradle bootRun --args="--demo.fail-at=subscription"
~~~

Dòng in bởi chính Java code:

~~~text
RESOURCE: connection opened
RESOURCE: subscription opened
INIT: failure after subscription
RESOURCE: subscription closed
RESOURCE: connection closed
MAIN: startup failed
~~~

Factory đóng hai resource ngược thứ tự mở. Quan sát thấy mỗi resource có đúng một dòng closed. Đây là minh chứng rằng **mở cả hai tài nguyên chưa đồng nghĩa initialization đã được commit**.

### 9.7. Input không hợp lệ

~~~bash
gradle bootRun --args="--demo.fail-at=unknown"
~~~

Validation ném `IllegalArgumentException` **trước** khi mở connection. Vì vậy không có dòng `RESOURCE: ... opened`. Trong main có dòng `MAIN: startup failed` rồi exception được ném lại.

### 9.8. Không được mở resource rồi bỏ qua lỗi

Nếu sửa `catch` thành:

~~~java
catch (RuntimeException original) {
    System.err.println("Ignored: " + original.getMessage());
    return new ManagedPipeline(connection, subscription);
}
~~~

đó là **anti-pattern**, không phải sửa đổi hợp lệ cho project: `subscription` có thể `null`; object trả về sẽ ở trạng thái không hợp lệ và dễ lỗi muộn. Giữ nguyên exception nếu không có **fallback đầy đủ và được thiết kế trước**.

## 10. Đường lỗi trong @PostConstruct

Trong ví dụ đầy đủ, cả hai tài nguyên đều được mở bên trong `@Bean` factory. Nhưng một bean có thể được tạo trước và mở tài nguyên trong `@PostConstruct`.

Mẫu có nghĩa:

~~~java
@Component
class ConfiguredClient {

    private AutoCloseable connection;
    private AutoCloseable consumer;

    @PostConstruct
    void init() throws Exception {

        AutoCloseable newConnection = null;
        AutoCloseable newConsumer = null;

        try {
            newConnection = openConnection();
            newConsumer = openConsumer(newConnection);
            verify(newConsumer);

            connection = newConnection;
            consumer = newConsumer;
        }
        catch (Exception | Error original) {
            closeOnFailure(newConsumer, original);
            closeOnFailure(newConnection, original);
            throw original;
        }
    }

    @PreDestroy
    void destroy() throws Exception {
        // Đóng consumer rồi connection trên đường hủy bình thường.
    }
}
~~~

Đây là **snippet minh họa chưa độc lập**: các helper `openConnection`, `openConsumer`, `verify`, `closeOnFailure` và phần thân cleanup bình thường cần định nghĩa theo hệ thống thực tế; imports `Component`, `PostConstruct` và `PreDestroy` cũng cần có.

Điểm học tập:

- Local resources **thuộc quyền sở hữu của init method** cho đến khi `verify` thành công.
- Khi lỗi, init method cleanup ngay mà không đợi Spring gọi destroy.
- Khi thành công, gán fields; về sau destruction của bean có thể dùng những fields ấy.
- Nếu setup mở resource bên trong helper rồi ném exception **trước khi trả handle**, helper chịu trách nhiệm dọn nội bộ.

Với bean init fail, không được dựa vào giả định `@PreDestroy` của chính bean đó chắc chắn được gọi. Spring có thể dọn những bean khác đã tạo thành công, nhưng nghĩa vụ của init method đối với tài nguyên nó vừa mở không thay đổi.

## 11. Khi constructor ném exception

Một constructor thất bại không trả về reference tới object hoàn chỉnh:

~~~java
class BadClient {
    private final Socket socket;

    BadClient() throws IOException {
        socket = new Socket("localhost", 8080);
        verifyServer(socket); // nếu throw, không có BadClient được trả về
    }
}
~~~

Đây là snippet anti-pattern, cần imports/helper. Caller không có `BadClient` để `close()` nếu constructor không hoàn tất. Resource đã mở vẫn có thể sống.

**Thiết kế tốt hơn:** Để constructor chỉ nhận các resource đã được kiểm tra rồi gán final fields; dùng static factory/builder để acquire, validate và rollback. Nếu bản thân constructor vẫn có thể throw, factory cần nắm các handle và cleanup theo contract ownership.

### Tránh escape của this khi constructor chưa xong

Nếu constructor đăng ký `this` vào global registry hoặc tạo thread giữ tham chiếu tới object trước khi init hoàn tất, lúc init fail có thể có “ghost” object sống trong thread khác. Cần unregister/stop theo đường lỗi hoặc không publish `this` trước khi thành công.

## 12. SmartLifecycle.start() thất bại

`SmartLifecycle` là một hook khác: bean có thể đã tạo và initialize xong, nhưng `start()` chỉ mới mở connection rồi thất bại khi subscribe.

~~~java
@Override
public void start() {
    channel.open();
    consumer.subscribe(); // throw
    running = true;
}
~~~

Snippet trên **không tự rollback**. Nếu `subscribe()` throw, `running` vẫn false nhưng channel có thể vẫn mở.

Mẫu an toàn hơn:

~~~java
@Override
public void start() {
    if (running) {
        return;
    }

    try {
        channel.open();
        consumer.subscribe();
        running = true;
    }
    catch (RuntimeException | Error original) {
        try {
            consumer.unsubscribeIfNecessary();
        }
        catch (RuntimeException cleanupFailure) {
            original.addSuppressed(cleanupFailure);
        }
        try {
            channel.closeIfOpen();
        }
        catch (RuntimeException cleanupFailure) {
            original.addSuppressed(cleanupFailure);
        }
        running = false;
        throw original;
    }
}
~~~

Đây là snippet cần type có API `unsubscribeIfNecessary()`, `closeIfOpen()` và field `running`. Nó minh họa **rollback ngay trong start()**. Không dựa vào `stop(Runnable)` được framework gọi sau đó để dọn một phần khởi động thất bại.

Nếu `start()` chỉ submit một task async rồi trả về, lỗi xảy ra **bên trong thread khác** không được catch bởi `try/catch` của thread caller. Khi đó cần `Future`/completion stage, startup barrier, cancellation, timeout và cơ chế close riêng. `running=true` không được xem là “connection đã sẵn sàng” chỉ vì task đã submit.

## 13. Runner fail cũng cần dọn resource tự mở

`ApplicationRunner`/`CommandLineRunner` chạy **sau context refresh**, trước `ApplicationReadyEvent`. Một runner có thể tự mở file để import dữ liệu rồi ném exception khi parse.

Anti-pattern:

~~~java
@Bean
ApplicationRunner importData() {
    return args -> {
        InputStream stream = Files.newInputStream(path);
        parse(stream); // throw
        stream.close(); // có thể không chạy
    };
}
~~~

Đây là snippet chưa độc lập, cần biến `path` và method `parse`. Nếu `parse` throw, stream không được close.

Mẫu phù hợp khi stream **chỉ sống trong runner**:

~~~java
@Bean
ApplicationRunner importData() {
    return args -> {
        try (InputStream stream = Files.newInputStream(path)) {
            parse(stream);
        }
    };
}
~~~

Nếu runner thất bại, Spring Boot có thể phát `ApplicationFailedEvent` và xử lý cleanup context, nhưng stream được runner mở độc lập vẫn cần được dọn trong runner. Một resource cần sống **sau** runner không nên được đóng khi runner trả về; phải chuyển ownership sang component sống lâu hơn.

## 14. Rollback stack cho nhiều bước

Khi có nhiều hơn hai resource, một stack chứa cleanup actions giúp tránh bỏ sót:

~~~java
Deque<AutoCloseable> rollback = new ArrayDeque<>();

try {
    Resource a = openA();
    rollback.push(a);

    Resource b = openB(a);
    rollback.push(b);

    Resource c = openC(b);
    rollback.push(c);

    return new ManagedGroup(a, b, c);
}
catch (Exception | Error original) {
    while (!rollback.isEmpty()) {
        try {
            rollback.pop().close();
        }
        catch (Exception | Error cleanupFailure) {
            if (cleanupFailure != original) {
                original.addSuppressed(cleanupFailure);
            }
        }
    }
    throw original;
}
~~~

Đây là **minh họa**, cần `Deque`, `ArrayDeque`, types `Resource`/`ManagedGroup` và helpers `openA/B/C`, method signature phù hợp.

`Deque.push(...)` thêm resource ngay sau khi acquire thành công, và `pop()` dọn theo **LIFO**. Với đường success, phải **chuyển ownership** cho `ManagedGroup` và **không tự dọn stack** trong `finally`. Nếu return object thành công mà finally vẫn đóng tất cả handle, caller sẽ nhận resource đã đóng.

### Khi rollback là bù trừ thay vì close

Một số bước tạo side effect:

- Đăng ký listener → cần `unregister`.
- Tạo scheduled task → cần `cancel` và có thể chờ task thoát.
- Tạo remote subscription → cần unsubscribe API.
- Tạo temporary file → cần delete nếu file còn thuộc sở hữu local.
- Tạo cloud resource → cần compensating delete hoặc reconciliation.

Những hành động này phải được ghi vào rollback stack/compensation log **sau khi bước tương ứng thành công**. Một remote API timeout có thể có trạng thái không chắc chắn; đôi khi cần query bằng request ID/idempotency key trước khi kết luận resource đã tồn tại.

## 15. Bảo vệ root cause và các suppressed exceptions

Giả sử initialization fail vì TLS configuration, và khi cleanup connection cũng phát sinh `IOException`. Bắt exception rồi ném lỗi cleanup có thể khiến log chỉ thấy “close failed” mà bỏ mất “certificate invalid”.

Dùng:

~~~java
catch (Exception original) {
    try {
        resource.close();
    }
    catch (Exception closeFailure) {
        original.addSuppressed(closeFailure);
    }
    throw original;
}
~~~

Trên đường exception, công cụ log thông thường có thể in cả `Caused by` và `Suppressed`. Không nên chỉ in `getMessage()` rồi bỏ mọi suppressed errors trong production telemetry.

### Nếu cleanup nhiều resource đều throw

Cần cố gắng dọn **tất cả** resource, không dừng sau resource đầu tiên lỗi. Helper `closeOnFailure` trong project mục 9 làm điều đó. Với đường **normal shutdown**, có thể dùng `try-with-resources` hoặc một close aggregator để giữ lỗi đầu tiên và suppressed những lỗi sau, đồng thời luôn cố close mọi resource.

### Đừng nuốt lỗi critical

Nếu một component thiết yếu không thể khởi tạo, bắt exception rồi trả bean nửa chừng để Spring Boot đạt ready là hành vi nguy hiểm. Chỉ dùng fallback khi đã định nghĩa một cấu hình hoạt động hợp lệ, health/readiness phù hợp và không làm sai nghiệp vụ.

## 16. Idempotency của close và trạng thái cleanup

Một resource có thể được yêu cầu đóng do nhiều đường: rollback, context close, timeout, retry hoặc operator stop. Nếu `close()` không idempotent, có thể xảy ra double-release hoặc lỗi trạng thái.

Mẫu đơn giản:

~~~java
private final AtomicBoolean closed = new AtomicBoolean();

@Override
public void close() {
    if (!closed.compareAndSet(false, true)) {
        return;
    }
    releaseResources();
}
~~~

Đây là **snippet**, cần import `AtomicBoolean` và method `releaseResources`. Nó ngăn việc chạy logic release hai lần trong một instance. Nhưng nếu `releaseResources()` throw sau khi `closed=true`, lần gọi sau không tự retry. Với resource đòi hỏi cleanup được xác nhận, nên có state machine (`OPEN → CLOSING → CLOSED/FAILED`), log và retry/backoff khi an toàn.

**Không đánh đồng** “đã gọi close” với “đã release thành công”. Đặc biệt với network socket, cloud lease, broker registration hoặc file deletion, có thể cần quan sát thêm và reconciliation.

## 17. Spring dọn bean nào khi startup fail?

Spring Boot có cơ chế xử lý failure, có thể phát `ApplicationFailedEvent` và đóng application context đã tạo khi phù hợp. Khi context destruction chạy, những bean singleton **đã được container quản lý hoàn chỉnh** có thể nhận callback hủy.

Nhưng không được suy ra:

- Factory throw trước `return` → Spring biết local resource để đóng.
- Constructor throw → Caller có object hoàn chỉnh để destroy.
- `@PostConstruct` throw → Destroy callback của chính bean đó chắc chắn được gọi.
- Thread tạo bằng `new Thread(...)` ngoài quản lý Spring → BeanFactory sẽ luôn dừng thread.
- External resource được tạo qua HTTP API → JVM shutdown tự xóa nó.
- `ApplicationFailedEvent` listener luôn có một `ApplicationContext` đầy đủ để inject bean.

Đó là lý do cần **rollback cục bộ ngay tại nơi mở tài nguyên** và một đường destruction riêng cho object đã được tạo thành công.

### Đừng nhầm bootstrap close với application close

`BootstrapRegistryInitializer` có thể dùng để đăng ký những object rất sớm trước application context. `BootstrapContextClosedEvent` là mốc chuyển giao trong quá trình **startup**, không phải `ContextClosedEvent` của application shutdown. Nếu tạo client/resource tại bootstrap, cần ownership/cleanup riêng và bridge tường minh nếu client phải sống tiếp thành Spring bean.

## 18. Kiểm thử bằng failure injection

Một test chỉ chạy startup thành công và đóng context bình thường **không đủ** để phát hiện resource leak trong partial initialization.

### Ma trận cần kiểm tra

| Điểm lỗi | Resource đã mở | Kết quả đúng |
| --- | --- | --- |
| Validate input trước acquire | Không | Không có close |
| Sau connection | Connection | Connection close đúng một lần |
| Sau subscription | Connection + subscription | Subscription close trước connection |
| Sau validate cuối | Tất cả resource | Dọn toàn bộ ngược thứ tự |
| Success | Tất cả resource | Factory không dọn; owner/bean dọn khi close |
| Cleanup đầu tiên throw | Nhiều resource | Còn cố dọn resource khác; giữ lỗi gốc |
| Gọi close lặp | Bean đã tạo | Idempotency theo contract |
| Lazy bean fail tại request đầu | Resource một phần | Cleanup ngay dù startup trước đó đã ready |
| Init async fail | Task/thread và resource | Cancellation/stop/join hoặc recovery có deadline |
| Process bị SIGKILL | Có thể còn resource ngoài JVM | TTL/lease/reconciliation; không mong Java callback |

### Test tự động

Có thể viết unit test cho factory `ManagedPipeline.create(...)` và fake resource có counter/spy, không cần boot toàn bộ SpringApplication. Assert:

- Đúng số lần mở/đóng.
- Thứ tự cleanup.
- Exception gốc vẫn là loại và cause đã dự kiến.
- `getSuppressed()` chứa lỗi close khi cố tình inject close failure.
- Không đóng resource trong success path trước khi owner.close().
- Không còn pending worker hoặc subscription sau failure.

Một test JUnit minh họa:

~~~java
@Test
void cleanupWhenSecondStageFails() {
    assertThrows(
            IllegalStateException.class,
            () -> ManagedPipeline.create("subscription"));

    // Trong test hoàn chỉnh, thay System.out bằng fake/spy
    // và assert mỗi resource được close đúng một lần.
}
~~~

Đây là **snippet chưa độc lập**: cần `spring-boot-starter-test`, JUnit 5 imports và tham chiếu đúng `ManagedPipeline` nested class (`PartialResourceApplication.ManagedPipeline`). Có thể dùng `ApplicationContextRunner` hoặc Spring Boot integration tests để xác nhận startup failure branch và destroy của các bean khác.

### Tại sao không dựa vào log framework làm assertion tuyệt đối?

Spring Boot có thể log nhiều chi tiết khác nhau tùy phiên bản/level. Ví dụ mục 9 chỉ khẳng định thứ tự **các dòng do code demo tự in**, không phải thứ tự mọi log Boot/Gradle. Với automated test, tốt hơn dùng counter/spy và quan hệ trước–sau có ý nghĩa thay vì chuỗi log console toàn hệ thống.

## 19. Các tình huống production khó rollback hoàn toàn

### Database và transaction

Một borrowed JDBC connection thường cần `close()` để **trả về pool** theo contract pool, không phải dừng cả pool. Nếu transaction đã mở rồi lỗi, cần rollback theo transaction manager. Với `@Transactional`, Spring quản lý transaction trong phạm vi được proxy kích hoạt phù hợp, nhưng code tự mở tài nguyên ngoài transaction vẫn cần tự cleanup.

Transaction DB không tự rollback email đã gửi hoặc external HTTP request. Với side effect xuyên hệ thống, cân nhắc outbox, idempotency key, compensating action và kiểm tra trạng thái sau lỗi.

### Temporary files

~~~java
Path temp = Files.createTempFile("import-", ".tmp");
try {
    writePayload(temp);
    validatePayload(temp);
    publish(temp);
}
catch (Exception original) {
    try {
        Files.deleteIfExists(temp);
    }
    catch (IOException cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
    throw original;
}
~~~

Đây là snippet, cần helper definitions, imports `Path`/`Files`/`IOException` và method signature phù hợp. Sau khi `publish` thành công, phải quyết định file tạm còn thuộc sở hữu của factory không. Với move/rename thành công, xóa nguồn theo một đường generic có thể vô tình xóa thứ đã publish nếu ownership thay đổi.

### Executor và worker threads

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    initializeHandlers(executor);
}
catch (RuntimeException original) {
    executor.shutdownNow();
    throw original;
}
~~~

Đây chỉ là bước đầu, **chưa đủ bảo đảm cleanup**. `shutdownNow()` chỉ cố interrupt; task có thể bỏ qua interrupt hoặc giữ I/O. Cần `awaitTermination(timeout)`, task cancellation đúng contract và telemetry để biết thread đã thoát. Không để worker tự tạo sống mãi vì bean chứa nó không hoàn tất initialization.

### Message consumer

Nếu consumer subscribe xong rồi lỗi khi tạo parser, phải pause/unsubscribe/close theo API đúng broker và tránh ack/commit offset trước khi side effect thật sự bền vững. Nếu startup bị kill sau side effect nhưng trước ack, redelivery có thể làm job lặp; cần idempotency.

### Remote resource và cloud API

Một API create có thể thành công ở server nhưng client timeout trước khi trả resource ID. Lúc đó caller không biết chắc tài nguyên đã tạo hay chưa. Hãy dùng idempotency token, operation ID, query trạng thái, rollback bù trừ và reconciliation job. `AutoCloseable` cục bộ không tự giải quyết được sự không chắc chắn ở remote side.

## 20. Lỗi thường gặp

**1. “Chỉ cần @PreDestroy là Spring dọn mọi thứ.”** Sai cho local resources mở trong một factory/init chưa thành công.

**2. “@Bean(destroyMethod) dọn được resource trước khi @Bean return.”** Không nên dựa vào đó; factory phải rollback chính nó.

**3. “Có try-with-resources thì được return object giữ stream.”** Sai nếu stream cần sống tiếp; scope try đóng nó trước khi caller sử dụng.

**4. “Cleanup error nên thay exception init.”** Sai; giữ root cause và đính kèm cleanup exception bằng suppressed.

**5. “Close tài nguyên theo thứ tự mở cũng được.”** Không khi resource sau phụ thuộc resource trước; thường đóng ngược thứ tự mở.

**6. “Có handle đã mở thì chắc chắn đã đăng ký thành bean.”** Không. Local variable của factory không phải bean đã hoàn tất.

**7. “Constructor throw thì caller có thể close object.”** Không có object hoàn chỉnh được trả về.

**8. “@PostConstruct ném exception rồi vẫn chắc chắn có @PreDestroy.”** Không có bảo đảm phù hợp để dùng làm cơ chế cleanup duy nhất cho phần init fail.

**9. “Bean initialize thất bại thì Spring dọn cả external thread.”** Không tự động với thread tạo ngoài Spring lifecycle.

**10. “Đăng ký listener trước khi init xong là vô hại.”** Không; callback có thể giữ object nửa chừng sau fail.

**11. “AtomicBoolean closed=true chứng nhận resource đã release.”** Không nếu release có thể throw; state cần phản ánh kết quả.

**12. “Lỗi close đầu tiên thì bỏ qua các resource còn lại.”** Có thể gây leak thứ hai; phải tiếp tục cố dọn.

**13. “Init fail thì chỉ log rồi return object rỗng.”** Dễ làm ứng dụng báo ready với thành phần không hợp lệ; cần fail-fast hoặc fallback có contract.

**14. “SmartLifecycle.stop chắc chắn xử lý mọi start failure.”** Không dùng stop callback của đường shutdown làm đường rollback duy nhất cho `start()` fail.

**15. “Runner fail thì các stream tự mở được Spring đóng.”** Không nếu runner giữ resource ngoài bean management.

**16. “Lazy bean chỉ lỗi khi startup.”** Có thể fail ở lần dùng đầu rất lâu sau khi Boot ready.

**17. “close() đã gọi là chắc chắn dừng thread.”** Không; interrupt không bảo đảm terminated; cần join/deadline.

**18. “Khởi tạo lại nhiều lần không cần dọn lần fail trước.”** Sai; có thể tích lũy connection/thread/file handles.

**19. “SpringApplication failure dọn mọi external resource.”** Không có bảo đảm với tài nguyên container chưa nhận và remote side effects.

**20. “JVM luôn chạy shutdown hooks.”** Sai khi SIGKILL, host crash hoặc một số lỗi VM nghiêm trọng.

**21. “Rollback local luôn hủy được remote transaction.”** Không; cần compensating transaction/outbox/reconciliation theo semantics.

**22. “Chỉ test happy path là đủ.”** Không; phải inject failure sau từng acquisition step.

## 21. Bài thực hành

1. Trong project mục 9, nêu thời điểm chuyển ownership từ factory sang Spring-managed bean.
2. Vì sao `--demo.fail-at=connection` không in `subscription opened` nhưng vẫn phải đóng connection?
3. Vì sao `--demo.fail-at=subscription` phải đóng hai resource theo thứ tự ngược?
4. Nếu bỏ `closeOnFailure(connection, original)`, lỗi gì xuất hiện ở nhánh connection?
5. Nếu đổi thứ tự đóng connection rồi subscription, tài nguyên nào có thể không flush/ack được trong ứng dụng thực tế?
6. Viết thêm điểm lỗi sau bước xác thực thứ ba, đảm bảo mọi tài nguyên đã mở được dọn.
7. Thử sửa `TrackedResource.close()` để ném exception; làm thế nào giữ lỗi init gốc ở ngoài cùng?
8. Khi dùng `@PostConstruct` để mở resource, bạn đặt cleanup đường init failure ở đâu?
9. Vì sao constructor làm I/O và publish `this` quá sớm là một thiết kế nguy hiểm?
10. Viết builder chứa rollback stack và giải thích vì sao dùng LIFO.
11. Trong một bean `SmartLifecycle`, nếu `start()` throw sau khi đã mở socket, tại sao không chỉ chờ `stop(Runnable)`?
12. Nếu init tạo thread async và thread fail sau khi method đã return, bắt lỗi bằng cơ chế nào?
13. Viết một bean factory mở connection rồi parse config; sử dụng `try-with-resources` cho resource nào và ownership transfer cho resource nào?
14. Tạo test cho 3 mode, assert `opened count`, `closed count` và thứ tự cleanup.
15. Thêm fake resource mà `close()` lỗi; assert `getSuppressed()` không rỗng và resource khác vẫn được cố đóng.
16. Nếu resource được tạo qua cloud API nhưng client timeout, làm sao biết cần bù trừ?
17. Vì sao `@Bean(destroyMethod="close")` không thay thế try/catch của factory?
18. Một lazy bean được dùng lần đầu sau ready nhưng init fail. Có thể leak resource trong JVM đang chạy lâu không?
19. Khi container bị SIGKILL, vì sao không có cách Java thuần bảo đảm gọi close?
20. Nêu các metrics cần có: resource opened/closed, partial init failures, cleanup failures, active handles và retry count.
21. Thiết kế thứ tự cleanup giữa consumer, session và connection để không phá vỡ bước flush.
22. Một task đã gửi email nhưng DB transaction rollback: cleanup nào giúp tránh side effect trùng ở lần retry?
23. So sánh “factory rollback thành công” với “bean destroy bình thường”; khi nào chúng được gọi?
24. Trong code review, tìm mọi câu lệnh acquire nằm **trước** một lệnh có thể throw. Có thiếu catch cleanup nào không?

## Ghi nhớ

- **Partial initialization** xảy ra khi một số tài nguyên đã được cấp phát nhưng object/bean chưa hoàn tất initialization.
- **Cleanup ngay tại nơi acquire:** constructor helper, factory hoặc init method phải tự dọn resource đã mở nếu bước tiếp theo thất bại.
- **Ownership chỉ chuyển sau success:** factory sở hữu resource trong quá trình xây dựng; bean/owner quản lý resource sau khi initialization thành công.
- `@PreDestroy`/`destroyMethod` phục vụ đường destruction của managed bean, **không phải bảo đảm duy nhất cho object fail init**.
- Thường **đóng ngược thứ tự mở** để tránh phá dependency của resource cấp trên.
- Dùng `try-with-resources` khi resource chỉ sống trong scope của block; không vô tình đóng resource cần giao cho bean dài hạn.
- Giữ **exception gốc** và đính kèm cleanup errors qua `addSuppressed(...)`.
- Nếu cleanup có thể thất bại, idempotency và state machine cần phản ánh kết quả thực thay vì chỉ đánh dấu “closed”.
- Với thread, queue, cloud resource và remote side effects, cần thêm cancellation/deadline, retry, idempotency, compensating actions hoặc reconciliation.
- Test failure injection **sau mỗi bước acquisition**, không chỉ test startup thành công.

### Tài liệu tham khảo

- Spring Framework 6.1 — Bean Initialization and Destruction Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework 6.1 — `@Bean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
- Spring Framework 6.1 — `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.3 — SpringApplication and Startup Failure: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Java 17 — `AutoCloseable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- Java 17 — `Throwable.addSuppressed`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)
- Java — try-with-resources: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html

# Kiểm thử khởi động với cấu hình thiếu hoặc tài nguyên chưa sẵn sàng

## 1. Mục tiêu: hợp đồng khởi động và khả năng phục hồi

Trong nhóm **Hợp đồng và khả năng phục hồi** của **Spring Boot - testing**, một bài kiểm thử startup tốt phải trả lời: **ứng dụng làm gì khi thiếu cấu hình bắt buộc, cấu hình sai kiểu, external dependency chưa ready hoặc một optional feature bị tắt?**

Ba hợp đồng có thể hợp lệ tùy hệ thống:

- **Fail fast:** Ứng dụng không khởi động khi thiếu secret bắt buộc, database schema chưa hợp lệ hoặc một remote dependency critical không thể sử dụng. Exception phải đủ rõ để khắc phục và không chứa bí mật.
- **Degraded readiness:** Context có thể chạy, nhưng readiness cho biết chưa nên nhận traffic hoặc một chức năng có fallback/circuit breaker với semantics minh bạch.
- **Feature disabled:** Dependency của tính năng không bật **không được chặn ứng dụng** chỉ vì thiếu host/port hoặc external server không chạy.

Không có quy tắc Spring Boot nào bảo mọi DataSource/KafkaTemplate/RestClient bean **kết nối thật ngay lúc tạo bean**. Nhiều client có thể lazy; vì vậy **contextLoads PASS không chứng minh external service ready**.

Bài học dùng **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, ApplicationContextRunner và Bean Validation**. Ví dụ hoàn chỉnh tạo remote catalog gateway: khi **app.remote.enabled=true** thì bắt buộc có host/port, và bean **StartupDependencyProbe** sẽ kiểm kết nối TCP trong initialization; khi kết nối thất bại, context fail. Khi enabled=false, không tạo remote gateway/probe. Test **fake DependencyDialer** để mô phỏng Connection refused deterministic; test riêng **ServerSocket loopback** xác minh adapter kết nối TCP thật.

Mọi kết quả được nêu là **kỳ vọng từ code**, không phải stdout của một lần chạy Gradle/Docker đã được quan sát.

## 2. Phân biệt các loại bằng chứng

| Tình huống | Cần kiểm tra | Bằng chứng |
| --- | --- | --- |
| enabled không khai báo | Optional disabled | Context start, không remote beans |
| enabled=false | Không kết nối | Không có StartupDependencyProbe |
| enabled=true, host thiếu | Required config | Startup failure |
| enabled=true, port thiếu | Required config | Startup failure |
| host chỉ whitespace | @NotBlank | Startup failure |
| port=abc | Type conversion | Startup failure |
| port=70000 | @Max(65535) | Startup failure |
| connect-timeout=0ms | Timeout contract | Startup failure |
| Kết nối bị từ chối | Resource unavailable | Startup failure, root cause ConnectException |
| Fake kết nối thành công | Startup policy | Context start, properties và arguments chính xác |
| ServerSocket thật đang listen | TCP adapter | Socket.connect thành công |
| TCP mở, HTTP API trả 503 | Protocol chưa ready | HTTP/protocol integration test |
| DB mất sau khi app READY | Runtime outage | Readiness, fallback và recovery tests |

**Missing configuration** thường không hết sau retry: phải sửa môi trường/secret. **Temporary external outage** có thể retry, nhưng phải có deadline/backoff. Không catch toàn bộ Exception rồi tiếp tục READY giả nếu dependency ấy critical.

### Các lớp chứng cứ không được nhập chung

1. Environment chứa key.
2. @ConfigurationProperties đã bind và validate.
3. Bean được tạo.
4. TCP connection thành công.
5. HTTP/TLS/DB/Kafka protocol health thành công.
6. ApplicationReadyEvent/ReadinessState đạt trạng thái phù hợp.
7. Business use case thực sự hoạt động.
8. Phục hồi sau outage.

Một phép assert ở lớp 2 không tự chứng minh lớp 5–8.

## 3. Startup phase và phạm vi kiểm thử

~~~text
ConfigData / Environment
       |
       v
Auto-configuration conditions / bean definitions
       |
       v
@ConfigurationProperties binding + validation
       |
       v
Bean creation / InitializingBean / @PostConstruct
       |
       v
Context refresh
       |
       v
ApplicationStartedEvent
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent / readiness
~~~

Sơ đồ chỉ mang tính khái niệm. Một lỗi tại properties binding, bean initialization, Flyway migration, runner hoặc web-server bind có thể chặn READY, nhưng xuất hiện ở những phase khác nhau.

**ApplicationContextRunner** tạo context cô lập rồi trả cả startup failure cho test assertions. Phù hợp với **conditional registration, properties binding, bean initialization**. Nó không tự chạy toàn bộ SpringApplication.run và ApplicationRunner/CommandLineRunner của application. Nếu failure chỉ xảy ra trong runner, migration hoặc HTTP server binding, cần test đúng phase cao hơn.

Trong ví dụ này, StartupDependencyProbe **implements InitializingBean**. Spring sẽ gọi afterPropertiesSet trong lúc tạo bean; nếu remote unavailable, bean init fail, context fail. Đây là **policy do ứng dụng thiết kế tường minh**, không phải hành vi mặc định của mọi network client.

## 4. Ranh giới: chính sách thật, dependency fake

~~~text
RemoteServiceAutoConfiguration
    |
    +-- @ConditionalOnProperty(enabled=true)
    |
    +-- RemoteEndpointProperties (@Validated)
    |       host, port, connectTimeout
    |
    +-- StartupDependencyProbe (thật)
    |       |
    |       +-- DependencyDialer (port)
    |                |
    |                +-- SocketDependencyDialer (runtime)
    |                +-- RecordingDialer (fake success)
    |                +-- RefusingDialer (fake ConnectException)
    |
    +-- RemoteCatalogGateway (chỉ sau probe)
~~~

**Không mock StartupDependencyProbe**, vì chính logic fail-fast của nó là subject under test. Chỉ fake DependencyDialer để điều khiển network outcome không phụ thuộc CI. Dùng **@ConditionalOnMissingBean(DependencyDialer.class)** để fake test thay default adapter.

Cần ba test paths riêng:
- **Invalid config:** Binder và Bean Validation thật; không mở network.
- **Resource unavailable:** Fake ném ConnectException; probe thật phải gây startup failure.
- **Actual TCP adapter success:** Một ServerSocket do test tự mở tại 127.0.0.1, port 0 để OS cấp port rảnh; không phụ thuộc external server.

## 5. Project đầy đủ Java 17 / Spring Boot 3.4.5

### 5.1. Cây tệp

~~~text
settings.gradle
build.gradle
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/main/java/com/example/startupchecks/StartupChecksApplication.java
src/main/java/com/example/remoteconfig/RemoteEndpointProperties.java
src/main/java/com/example/remoteconfig/DependencyDialer.java
src/main/java/com/example/remoteconfig/SocketDependencyDialer.java
src/main/java/com/example/remoteconfig/StartupDependencyProbe.java
src/main/java/com/example/remoteconfig/RemoteCatalogGateway.java
src/main/java/com/example/remoteconfig/RemoteServiceAutoConfiguration.java
src/test/java/com/example/remoteconfig/RemoteServiceAutoConfigurationTest.java
src/test/java/com/example/startupchecks/DiscoveryWithFakeDialerTest.java
~~~

Auto-config nằm ở **com.example.remoteconfig**, application ở **com.example.startupchecks** (sibling packages). Không để application component scan auto-config class; discovery test sẽ kiểm Boot tìm class qua resource imports.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'startup-contract-testing'
~~~

### 5.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**starter-validation** cung cấp Bean Validation implementation cho @NotBlank/@NotNull/@Min/@Max. **spring-boot-configuration-processor** sinh metadata IDE, không thay Binder. **starter-test** có JUnit Jupiter và ApplicationContextRunner. Không cần Spring MVC/JPA/Kafka cho core tests; thêm chúng khi cần resource-specific integration.

### 5.4. StartupChecksApplication.java

~~~java
package com.example.startupchecks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupChecksApplication {
    public static void main(String[] args) {
        SpringApplication.run(StartupChecksApplication.class, args);
    }
}
~~~

### 5.5. RemoteEndpointProperties.java

~~~java
package com.example.remoteconfig;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public class RemoteEndpointProperties {

    @NotBlank
    private String host;

    @NotNull
    @Min(1)
    @Max(65535)
    private Integer port;

    @NotNull
    private Duration connectTimeout = Duration.ofMillis(250);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Integer getPort() {
        return port;
    }

    public void setPort(Integer port) {
        this.port = port;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration timeout) {
        this.connectTimeout = timeout;
    }
}
~~~

**Không mặc định host/port** để tránh giấu cấu hình thiếu khi feature enabled. **Integer** cho phép phân biệt port chưa cấu hình (null) với giá trị 0. Duration mặc định 250ms có thể override bằng **app.remote.connect-timeout=750ms**; kiểm range dương ở StartupDependencyProbe.

Spring Boot 3.4 thực hiện Bean Validation trên @ConfigurationProperties có @Validated. Với nested configuration phải dùng **@Valid** để cascade theo Bean Validation khi cần. **Relaxed binding** hỗ trợ naming forms hợp lệ nhưng không tự sửa lỗi typo key.

### 5.6. DependencyDialer.java

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.time.Duration;

public interface DependencyDialer {
    void verifyConnectivity(
        String host, int port, Duration timeout) throws IOException;
}
~~~

Đây là outbound port duy nhất cho startup network check. Trong unit test, fake làm thành công hoặc ném IOException; không dựng DNS/firewall.

### 5.7. SocketDependencyDialer.java

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.time.Duration;

public final class SocketDependencyDialer
        implements DependencyDialer {

    @Override
    public void verifyConnectivity(
            String host, int port, Duration timeout)
            throws IOException {

        int timeoutMillis =
            Math.toIntExact(timeout.toMillis());

        try (Socket socket = new Socket()) {
            socket.connect(
                new InetSocketAddress(host, port),
                timeoutMillis);
        }
    }
}
~~~

TCP handshake thành công không chứng minh HTTP 200, TLS, auth, database schema hoặc broker leader. Connect timeout cũng không nhất thiết bao phủ thời gian DNS lookup. Nếu requirement là protocol readiness, thay dialer bằng protocol-specific health/handshake check và viết integration test tương ứng.

### 5.8. StartupDependencyProbe.java

~~~java
package com.example.remoteconfig;

import java.io.IOException;
import java.time.Duration;
import java.util.Objects;

import org.springframework.beans.factory.InitializingBean;

public final class StartupDependencyProbe
        implements InitializingBean {

    private final RemoteEndpointProperties properties;
    private final DependencyDialer dialer;

    public StartupDependencyProbe(
            RemoteEndpointProperties properties,
            DependencyDialer dialer) {
        this.properties = Objects.requireNonNull(properties);
        this.dialer = Objects.requireNonNull(dialer);
    }

    @Override
    public void afterPropertiesSet() {
        Duration timeout = properties.getConnectTimeout();

        if (timeout == null
                || timeout.compareTo(Duration.ofMillis(1)) < 0
                || timeout.compareTo(
                    Duration.ofMillis(Integer.MAX_VALUE)) > 0) {
            throw new IllegalArgumentException(
                "app.remote.connect-timeout must be "
                + "between 1ms and Integer.MAX_VALUE ms");
        }

        try {
            dialer.verifyConnectivity(
                properties.getHost(),
                properties.getPort(),
                timeout);
        } catch (IOException ex) {
            throw new IllegalStateException(
                "required remote catalog unavailable at startup",
                ex);
        }
    }
}
~~~

Bean init thật kiểm timeout và gọi dialer. Khi refused, IOException được giữ làm cause; Spring container startup failure có thể bọc bằng BeanCreationException. Dùng **rootCause** trong test thay vì assert toàn bộ stack trace dễ thay đổi theo patch version.

**Timeout=0** trong Java Socket.connect có thể có nghĩa chờ vô hạn; validate dương là một phần startup contract. Bài demo thử đúng một lần, **không tự retry**. Production có thể chọn bounded retry với deadline nếu remote service khởi động trễ, nhưng cần test khác.

### 5.9. RemoteCatalogGateway.java

~~~java
package com.example.remoteconfig;

import java.util.Objects;

public final class RemoteCatalogGateway {
    private final RemoteEndpointProperties properties;
    private final StartupDependencyProbe checkedAtStartup;

    public RemoteCatalogGateway(
            RemoteEndpointProperties properties,
            StartupDependencyProbe checkedAtStartup) {
        this.properties = Objects.requireNonNull(properties);
        this.checkedAtStartup =
            Objects.requireNonNull(checkedAtStartup);
    }

    public String endpoint() {
        return properties.getHost() + ":" + properties.getPort();
    }
}
~~~

Gateway constructor phụ thuộc StartupDependencyProbe để **probe initialize trước gateway**. Đây là sample gateway chỉ expose endpoint string, không phải HTTP client hoàn chỉnh; mục tiêu là startup contract.

### 5.10. RemoteServiceAutoConfiguration.java

~~~java
package com.example.remoteconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "app.remote",
    name = "enabled",
    havingValue = "true")
@EnableConfigurationProperties(RemoteEndpointProperties.class)
public class RemoteServiceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DependencyDialer.class)
    DependencyDialer socketDependencyDialer() {
        return new SocketDependencyDialer();
    }

    @Bean
    StartupDependencyProbe startupDependencyProbe(
            RemoteEndpointProperties properties,
            DependencyDialer dialer) {
        return new StartupDependencyProbe(properties, dialer);
    }

    @Bean
    RemoteCatalogGateway remoteCatalogGateway(
            RemoteEndpointProperties properties,
            StartupDependencyProbe probe) {
        return new RemoteCatalogGateway(properties, probe);
    }
}
~~~

**@ConditionalOnProperty** đặt ở class level nên nếu enabled missing/false, không đăng ký properties bean/probe/gateway. Khi enabled=true, thiếu host/port phải fail. **@ConditionalOnMissingBean** cho phép user/test tự cung cấp dialer; default SocketDependencyDialer back off.

### 5.11. AutoConfiguration.imports

Tạo tệp chính xác **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**:

~~~text
com.example.remoteconfig.RemoteServiceAutoConfiguration
~~~

Spring Boot 3.x tìm auto-configuration candidates từ imports file. Dùng ApplicationContextRunner với AutoConfigurations.of class **không chứng minh** imports path đúng; một @SpringBootTest discovery riêng làm việc đó.

## 6. ApplicationContextRunner tests: cấu hình thiếu và dependency unavailable

**src/test/java/com/example/remoteconfig/RemoteServiceAutoConfigurationTest.java**

~~~java
package com.example.remoteconfig;

import java.net.ConnectException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class RemoteServiceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                RemoteServiceAutoConfiguration.class));

    @Test
    void missingFeatureFlagDisablesRemoteGateway() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(0, context
                .getBeanNamesForType(RemoteCatalogGateway.class).length);
            assertEquals(0, context
                .getBeanNamesForType(StartupDependencyProbe.class).length);
            assertEquals(0, context
                .getBeanNamesForType(RemoteEndpointProperties.class).length);
        });
    }

    @Test
    void disabledFeatureNeverProbesResource() {
        runner.withUserConfiguration(RefusingDialerConfig.class)
            .withPropertyValues("app.remote.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(0, context
                    .getBeanNamesForType(
                        StartupDependencyProbe.class).length);
            });
    }

    @Test
    void missingHostFailsStartup() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.port=8443")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void missingPortFailsStartup() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void malformedPortFailsBinding() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=not-a-number")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void invalidPortRangeFailsValidation() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=70000")
            .run(context ->
                assertNotNull(context.getStartupFailure()));
    }

    @Test
    void zeroTimeoutFailsBeforeNetworkCall() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=8443",
                "app.remote.connect-timeout=0ms")
            .run(context -> {
                Throwable failure = context.getStartupFailure();
                assertNotNull(failure);
                assertInstanceOf(
                    IllegalArgumentException.class,
                    rootCause(failure));
            });
    }

    @Test
    void validPropertiesReachRealStartupProbe() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=catalog.internal",
                "app.remote.port=8443",
                "app.remote.connect-timeout=750ms")
            .run(context -> {
                assertNull(context.getStartupFailure());

                RemoteEndpointProperties props =
                    context.getBean(RemoteEndpointProperties.class);
                assertEquals("catalog.internal", props.getHost());
                assertEquals(Integer.valueOf(8443), props.getPort());
                assertEquals(Duration.ofMillis(750),
                    props.getConnectTimeout());

                RecordingDialer fake =
                    context.getBean(RecordingDialer.class);
                assertEquals(1, fake.calls);
                assertEquals("catalog.internal", fake.host);
                assertEquals(8443, fake.port);
                assertEquals(Duration.ofMillis(750), fake.timeout);
                assertEquals("catalog.internal:8443",
                    context.getBean(
                        RemoteCatalogGateway.class).endpoint());
            });
    }

    @Test
    void missingTimeoutUses250msDefault() {
        runner.withUserConfiguration(RecordingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=8443")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(Duration.ofMillis(250),
                    context.getBean(RecordingDialer.class).timeout);
            });
    }

    @Test
    void refusedResourceFailsStartupAndPreservesCause() {
        runner.withUserConfiguration(RefusingDialerConfig.class)
            .withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=catalog.internal",
                "app.remote.port=8443")
            .run(context -> {
                Throwable failure = context.getStartupFailure();
                assertNotNull(failure);
                assertInstanceOf(
                    ConnectException.class,
                    rootCause(failure));
            });
    }

    @Test
    void realTcpDialerConnectsToTestOwnedServer()
            throws Exception {

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            runner.withPropertyValues(
                "app.remote.enabled=true",
                "app.remote.host=127.0.0.1",
                "app.remote.port=" + server.getLocalPort(),
                "app.remote.connect-timeout=1s")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertInstanceOf(SocketDependencyDialer.class,
                    context.getBean(DependencyDialer.class));
                assertEquals(
                    "127.0.0.1:" + server.getLocalPort(),
                    context.getBean(
                        RemoteCatalogGateway.class).endpoint());
            });
        }
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    static final class RecordingDialer
            implements DependencyDialer {
        int calls;
        String host;
        int port;
        Duration timeout;

        @Override
        public void verifyConnectivity(
                String host, int port, Duration timeout) {
            calls++;
            this.host = host;
            this.port = port;
            this.timeout = timeout;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class RecordingDialerConfig {
        @Bean
        RecordingDialer recordingDialer() {
            return new RecordingDialer();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class RefusingDialerConfig {
        @Bean
        DependencyDialer refusingDialer() {
            return (host, port, timeout) -> {
                throw new ConnectException(
                    "simulated connection refused");
            };
        }
    }
}
~~~

**Ý nghĩa các test:**
- Missing flag/false: không có probe, context start.
- Missing host/port và port sai: context fail trước khi gateway sẵn sàng.
- Timeout=0: StartupDependencyProbe thật reject.
- RecordingDialer: config bind vào properties bean và truyền đúng host/port/timeout vào startup check; fake được gọi một lần, không mở network.
- RefusingDialer: giả lập ConnectException, root cause được giữ và context fail.
- Real TCP: ServerSocket đã listen tại port do OS cấp, SocketDependencyDialer thật connect được.

**Không mặc định mọi failed test đều có root cause là chính property đang kiểm.** Các negative config tests cơ bản assert startup failure; trong CI project thực, nên bổ sung cause-chain/constraint field assertions sau khi xác minh Spring Boot patch version, cùng positive case để tránh false positive do unrelated bean.

### Tại sao không dùng port 9999 rồi mong refused?

Một process khác có thể chiếm port 9999 trên CI; DNS và firewall thay đổi theo máy. Fake ném ConnectException là deterministic cho fail-fast policy. Khi cần test adapter TCP, ServerSocket(0) tự cấp port và được mở **trước** context. Đừng tự dừng một shared database/container của test khác chỉ để kiểm failure.

## 7. SpringBootTest kiểm discovery từ imports file

**src/test/java/com/example/startupchecks/DiscoveryWithFakeDialerTest.java**

~~~java
package com.example.startupchecks;

import java.time.Duration;

import com.example.remoteconfig.DependencyDialer;
import com.example.remoteconfig.RemoteCatalogGateway;
import com.example.remoteconfig.RemoteEndpointProperties;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    classes = StartupChecksApplication.class,
    properties = {
        "app.remote.enabled=true",
        "app.remote.host=catalog.test",
        "app.remote.port=9443",
        "app.remote.connect-timeout=500ms"
    })
@Import(DiscoveryWithFakeDialerTest.NoNetworkConfig.class)
class DiscoveryWithFakeDialerTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void autoConfigIsDiscoveredFromImports() {
        RemoteCatalogGateway gateway =
            context.getBean(RemoteCatalogGateway.class);
        assertNotNull(gateway);
        assertEquals("catalog.test:9443", gateway.endpoint());
        assertEquals(1, context
            .getBeanNamesForType(
                RemoteCatalogGateway.class).length);

        RemoteEndpointProperties properties =
            context.getBean(RemoteEndpointProperties.class);
        assertEquals(Duration.ofMillis(500),
            properties.getConnectTimeout());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class NoNetworkConfig {
        @Bean
        DependencyDialer fakeDialer() {
            return (host, port, timeout) -> {
                // Không gửi network trong discovery test.
            };
        }
    }
}
~~~

**@Import ở đây chỉ import fake test configuration**, không import RemoteServiceAutoConfiguration. Nếu xóa AutoConfiguration.imports và app không scan sibling package, gateway sẽ vắng mặt, test fail. Vì dialer fake, host catalog.test không cần DNS resolve; test **không** chứng minh external catalog reachable.

## 8. Vì sao expected startup failure nên dùng ApplicationContextRunner?

Một class @SpringBootTest có config cố tình sai thường báo **Failed to load ApplicationContext** trước khi JUnit vào @Test method. Do đó viết assertThrows trong method không giúp kiểm expected startup failure. Với ApplicationContextRunner:

~~~java
runner.withPropertyValues(
        "app.remote.enabled=true",
        "app.remote.port=8443")
    .run(context -> {
        assertNotNull(context.getStartupFailure());
    });
~~~

Runner trả failed context vào callback để kiểm. **Không gọi getBean trên failed context** rồi làm mờ nguyên nhân. Dùng getStartupFailure, root cause và condition evaluation report. Với lỗi chỉ ở **CommandLineRunner/ApplicationRunner** hoặc web-server bind, cần test SpringApplication lifecycle thật, vì ApplicationContextRunner không tự chạy chúng.

**Context cache/failure threshold:** Spring TestContext có thể reuse contexts và giới hạn lặp lại cùng cấu hình broken, khiến nhiều @SpringBootTest expected failures khó đọc. Runner hợp lý cho matrix config invalid.

## 9. Fail-fast so với degraded readiness

**Fail fast** nếu một dependency critical phải có trước khi ứng dụng nhận request và không có fallback an toàn. **Degraded mode** nếu feature optional, có fallback hoặc có thể giữ API lõi hoạt động. Không nên chuyển từ fail fast sang swallow IOException chỉ để test xanh.

| Policy | Cách triển khai | Cách kiểm |
| --- | --- | --- |
| Required config fail | @ConfigurationProperties + @Validated | Runner failure + cause |
| Required remote unavailable | InitializingBean/probe | Fake DependencyDialer refused |
| Optional disabled | @ConditionalOnProperty | Runner starts không probe |
| Degraded service | HealthIndicator/ReadinessState + fallback | Actuator/API integration |
| Resource xuất hiện trễ | Bounded retry/backoff | Fake clock/scheduler + latches |
| Resource mất sau READY | Circuit breaker/reconnect | Runtime outage integration |

**Không retry missing credentials/config lỗi vô hạn**. Với IO tạm thời, retry cần max attempts, per-attempt timeout, total startup budget và jitter. Một timeout trên Socket.connect không tự bao gồm DNS resolution, TLS handshake hoặc toàn bộ retry budget.

### Liveness khác readiness

**Liveness** hỏi process có cần restart không. Nếu gắn mọi external DB/API health vào liveness, một shared outage có thể làm toàn bộ pods restart, gây cascading failure. **Readiness** hỏi instance có nên nhận traffic; có thể bao gồm critical dependency health, nhưng Spring Boot **không mặc định include mọi external indicators vào readiness group**.

Ví dụ cấu hình Actuator ngoài runnable project:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: "readinessState,remoteCatalog"
~~~

Cần starter-actuator, web/management endpoint và **HealthIndicator tên remoteCatalog thật**. Nếu group include indicator không tồn tại, Boot có thể fail startup theo validation. Không dùng ví dụ này nếu chưa tạo indicator.

Một shared external dependency down mà mọi pods unready có thể làm service không nhận traffic, kể cả khi có fallback. Chọn policy theo dependency criticality, không chỉ theo mặc định framework.

## 10. DB, Kafka, Redis và HTTP client khi startup

**Database:** DataSource bean có thể chưa kết nối. Flyway/Liquibase migration, Hibernate metadata/schema validation hoặc custom probe có thể buộc DB thực sự được dùng lúc startup. Hikari connection-timeout/initialization-fail-timeout chỉ tác động khi pool init/acquire theo cấu hình. Test đúng là **real connection/migration path**, không chỉ assert bean present.

**Kafka:** KafkaTemplate bean không có nghĩa broker healthy; producer send future có thể fail bất đồng bộ, @KafkaListener container có reconnect/startup policy riêng. Muốn fail fast, thiết kế explicit broker/admin health probe hoặc readiness contract và test nó.

**Redis:** RedisConnectionFactory/RedisTemplate chưa phải một PING thành công. Nếu cache có DB fallback, degraded startup có thể là chính sách tốt; nếu Redis là store cho security sessions/locks critical, policy khác.

**HTTP external API:** TCP connect success không đủ nếu TLS/certificate, HTTP status, token auth hoặc schema API sai. Dùng MockWebServer/WireMock/Testcontainers HTTP service với real client để kiểm 200/503/timeouts/TLS khi những điều ấy là requirement.

**Database migrations:** Script SQL initialization và Flyway/Liquibase có fail-fast behavior khi được kích hoạt; không giả định luôn chạy nếu project thiếu dependencies hoặc mode/config disabled. Hãy test với đúng SQL dialect khi production dùng PostgreSQL thay vì chỉ H2.

## 11. Testcontainers và dynamic endpoints

Spring Boot 3.4 hỗ trợ **@ServiceConnection** với Testcontainers cho JDBC, Redis, Kafka và nhiều services có ConnectionDetails factory phù hợp. Thí dụ phác thảo DB integration, **không nằm trong runnable project**:

~~~java
@Testcontainers
@SpringBootTest
class PostgresStartupExample {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16");

    @Autowired
    DataSource dataSource;

    @Test
    void connectionWorks() throws Exception {
        try (Connection c = dataSource.getConnection()) {
            assertTrue(c.isValid(2));
        }
    }
}
~~~

Cần dependencies **spring-boot-starter-jdbc**, PostgreSQL driver, **spring-boot-testcontainers**, Testcontainers junit-jupiter/postgresql, Docker daemon và imports Java/Spring. **@ServiceConnection** cung cấp ConnectionDetails ưu tiên các connection properties liên quan. Test success với Testcontainers **không** chứng minh production JDBC URL/password đúng nếu URL test đã được override.

Thay thế bằng **@DynamicPropertySource**, static method thêm URL/username/password runtime:

~~~java
@DynamicPropertySource
static void dbProps(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", db::getJdbcUrl);
    registry.add("spring.datasource.username", db::getUsername);
    registry.add("spring.datasource.password", db::getPassword);
}
~~~

Đây là snippet giả sử static container db có sẵn; dynamic properties có precedence cao. Không hard-code mapped port. Với test unavailable thực, dùng container/network isolation; **đừng stop shared static container trong khi test khác còn chạy**.

## 12. Không dùng Thread.sleep để mô phỏng startup race

Nếu muốn resource xuất hiện sau vài attempts, viết **bounded retry policy** tách Clock/Sleeper/RetryScheduler để fake thời gian và ném IO theo từng attempt. Một integration test có thể dùng CountDownLatch/Awaitility với timeout hữu hạn, không ngủ cố định vài giây rồi mong container sẵn sàng.

~~~text
attempts < maximum AND elapsed < startup budget
    try required protocol check with timeout
    success -> finish startup
    transient IO error -> backoff + jitter, retry
    config/auth permanent error -> fail immediately
    exhausted budget -> fail startup with last cause
~~~

Đây là **pseudocode**, không thuộc code runnable; dự án này chỉ check một lần rồi fail fast. Khi dependency mất sau READY, startup-only probe không phát hiện. Cần health/readiness, client timeouts, fallback và runtime recovery tests riêng.

## 13. Security, log và nguyên nhân lỗi

Một startup error hữu ích nên nói:
- dependency nào (remote catalog, PostgreSQL, Redis...);
- phase nào (properties validation, bean init, migration, network probe);
- key cấu hình nào thiếu nếu an toàn;
- loại exception và root cause;
- retryable hay cần operator sửa deployment.

**Không log password, Basic/Bearer token, full secret URL, raw Environment hoặc security cookie**. Chỉ đưa tên property và cause đã redacted. Đừng catch(Exception) rồi chỉ log warning nếu app không thể phục vụ an toàn. Ngược lại, không kill app vì một optional feature đã tắt.

### Test nguyên nhân thay vì chỉ test có lỗi

Một assertion getStartupFailure()!=null có thể PASS vì unrelated bean lỗi. Nên có **positive control** (valid properties + RecordingDialer) và khi cần kiểm cause-chain: ConnectException hoặc BindValidationException/BindException phù hợp version. Không assert nguyên văn toàn bộ stack trace, tên bean sinh tự động hoặc line number để tránh brittle tests.

## 14. Bảng lỗi thực tế

| Sai lầm | Tại sao sai | Hướng sửa |
| --- | --- | --- |
| contextLoads = DB ready | Connection có thể lazy | Real query/migration/health test |
| Mock cả StartupDependencyProbe | Bỏ qua fail-fast logic | Fake DependencyDialer |
| Dùng localhost:9999 để chắc chắn refused | Có thể có process khác | Deterministic refused fake |
| @SpringBootTest expected failure trong @Test body | Context fail trước method | ApplicationContextRunner |
| Tắt mọi dependencies trong test rồi gọi production ready | Che policy production | Disabled + enabled negative/positive tests |
| Không dùng @Validated | Invalid properties lọt qua | Typed config + validation |
| Required endpoint mặc định localhost | Che missing config | @NotBlank host, @NotNull port |
| Socket timeout=0 | Có thể vô hạn | Validate >=1ms |
| Retry vô hạn khi thiếu secret | Deployment treo | Permanent error fail |
| Thread.sleep đợi DB ready | Flaky và chậm | Testcontainers readiness/latch |
| Mọi external health nằm trong liveness | Restart storm | Readiness/fallback có chọn lọc |
| @ServiceConnection pass chứng minh prod URL đúng | Test URL được override | Separate prod config test |
| Health 200 nghĩa mọi request đúng | Indicator có thể thiếu | Real business/health assertions |
| Log full connection string | Lộ credentials | Redacted diagnostics |
| Dùng @DirtiesContext cho mọi flake | Chậm và che shared-state | Lifecycle isolation |
| Chỉ assert exception bất kỳ | Lỗi unrelated cũng pass | Root cause + control case |
| Test với H2 rồi bảo Postgres ready | Dialect khác | Postgres Testcontainers |

## 15. Chạy bộ test và kết quả kỳ vọng

~~~bash
./gradlew clean test
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest
./gradlew test --tests com.example.startupchecks.DiscoveryWithFakeDialerTest
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest.refusedResourceFailsStartupAndPreservesCause
./gradlew test --tests com.example.remoteconfig.RemoteServiceAutoConfigurationTest.realTcpDialerConnectsToTestOwnedServer
~~~

Trên Windows sử dụng **gradlew.bat**. Nếu chưa tạo Gradle Wrapper scripts, dùng Gradle được cài hoặc tạo wrapper trước; chỉ có build.gradle chưa tạo ./gradlew. Những kết quả dưới đây là expected assertions, **không phải runtime output đã quan sát**.

| Test | Kỳ vọng |
| --- | --- |
| missingFeatureFlagDisablesRemoteGateway | Context thành công, 0 remote beans |
| disabledFeatureNeverProbesResource | Context thành công, 0 probe |
| missingHostFailsStartup | Startup failure |
| missingPortFailsStartup | Startup failure |
| malformedPortFailsBinding | Startup failure |
| invalidPortRangeFailsValidation | Startup failure |
| zeroTimeoutFailsBeforeNetworkCall | Root cause IllegalArgumentException |
| validPropertiesReachRealStartupProbe | host/port/750ms đúng, fake calls=1 |
| missingTimeoutUses250msDefault | Default timeout 250ms |
| refusedResourceFailsStartupAndPreservesCause | Root cause ConnectException |
| realTcpDialerConnectsToTestOwnedServer | TCP success tại loopback port |
| autoConfigIsDiscoveredFromImports | Full Boot discovers remote gateway qua imports |

**Giới hạn đã nêu:** TCP handshake không phải protocol readiness; fake unavailable chứng minh policy chứ không sinh packet thật; @SpringBootTest discovery với fake không chứng minh external host reachable. Cần integration tests tương ứng khi yêu cầu vận hành sâu hơn.

## 16. Tự kiểm tra kiến thức

**1.** enabled=false và host/port thiếu thì sao? **Start được**, vì optional feature disabled.

**2.** enabled=true và host thiếu? **Startup fail** do @NotBlank.

**3.** Vì sao Integer port thay int? **@NotNull phát hiện missing config rõ ràng**.

**4.** Port=abc có được tự fallback 8080? **Không**, Binder phải reject invalid type.

**5.** Muốn test Connection refused mà không mở network, fake lớp nào? **DependencyDialer**.

**6.** Tại sao giữ StartupDependencyProbe thật? Vì **fail-fast policy** nằm tại đó.

**7.** ApplicationContextRunner với AutoConfigurations.of chứng minh imports file đúng chưa? **Chưa**, dùng discovery test.

**8.** Vì sao @SpringBootTest failed startup khó assert trong @Test method? Vì context load fail **trước khi JUnit chạy method**.

**9.** DataSource/KafkaTemplate bean có tự chứng minh server available? **Không**.

**10.** Socket.connect thành công có chứng minh HTTP 200 không? **Không**.

**11.** Tại sao dùng ServerSocket(0)? OS chọn port rảnh trong runtime test.

**12.** Timeout 0 có thể làm gì? Có thể đợi không giới hạn, nên validate timeout dương.

**13.** @ConditionalOnProperty class-level disabled ảnh hưởng gì? Không đăng ký auto-config bean/properties của feature.

**14.** @ConditionalOnMissingBean giúp gì? User/test bean khiến default dialer back off.

**15.** Dependency mất sau READY có được startup-only test thấy ngay không? **Không**, cần runtime health.

**16.** Liveness có nên phụ thuộc mọi external API không? **Không**, tránh restart storm.

**17.** Readiness mặc định bao gồm mọi external health indicators chưa? **Chưa**, phải thiết kế group.

**18.** @ServiceConnection với Testcontainers có thể override datasource config không? **Có** cho supported ConnectionDetails.

**19.** @DynamicPropertySource yêu cầu gì? Static method với DynamicPropertyRegistry.

**20.** Quy tắc cốt lõi? **Config sai phải fail rõ; dependency critical phải có fail-fast/readiness policy; feature optional disabled không được chặn startup.**

### Checklist QA

- Startup contract của dependency là fail fast, degraded hay optional disabled?
- Có test enabled flag missing/false và enabled=true?
- Có test host/port missing, type invalid, range invalid, timeout=0?
- Có positive control valid config + fake reachable?
- Có test unavailable với root cause ConnectException?
- Không dùng port đoán hoặc Thread.sleep trong unit/context tests?
- Probe chính sách là implementation thật và chỉ fake network boundary?
- Có test SocketDependencyDialer thật với loopback server-owned port?
- Có tách ApplicationContextRunner from SpringApplication startup lifecycle?
- Có kiểm discovery AutoConfiguration.imports riêng?
- Không nhầm contextLoads với DB/Kafka/Redis ready?
- Có nhận thức liveness/readiness và tác động distributed outage?
- Khi cần DB thật, có Testcontainers/service connection/SQL validation?
- Có bounded retry/deadline, phân loại retryable/permanent errors?
- Có test source precedence/profile/secret configuration khi sản phẩm cần?
- Không log password, API keys, tokens hoặc raw secret URLs?
- Có cleanup/isolation resources để CI parallel không flaky?
- Không tuyên bố đã thực chạy Gradle/Docker nếu chưa có bằng chứng?

**Kết luận:** Kiểm thử Spring Boot startup phải có **hợp đồng cụ thể**: required configuration được bind/validate, external dependency critical được probe theo policy, optional feature disabled không tạo side effect, và readiness phản ánh đúng khả năng phục vụ. **ApplicationContextRunner** kiểm tốt các nhánh lỗi cấu hình và bean init; **fake DependencyDialer** tạo lỗi deterministic; **loopback/Testcontainers** cung cấp bằng chứng hạ tầng thật khi cần. Không coi một context thành công là toàn hệ thống đã sẵn sàng.

## Tài liệu chính thức

- Spring Boot 3.4 — Testing Auto-configuration / ApplicationContextRunner: https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html
- Spring Boot 3.4 — External Configuration và Validation: https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html
- Spring Boot 3.4 — Testcontainers / @ServiceConnection: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Boot 3.4 — Actuator Liveness/Readiness: https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html
- Spring Boot 3.4 — Database Initialization and Migration: https://docs.spring.io/spring-boot/3.4/how-to/data-initialization.html
- Spring Framework 6.2 — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Java 17 — Socket.connect: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html

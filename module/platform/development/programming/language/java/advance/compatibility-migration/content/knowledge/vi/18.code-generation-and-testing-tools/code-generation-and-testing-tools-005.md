# Mockito, mock bằng bytecode và yêu cầu agent

Khi thực hiện **Java Advance Compatibility Migration**, một dự án có thể biên dịch thành công nhưng unit test bắt đầu phát cảnh báo hoặc thất bại khi đổi JDK. Những biểu hiện thường gặp là Mockito không khởi tạo được inline mock maker, Byte Buddy không hiểu class-file version mới, mock một class `final` bị từ chối, hoặc JDK 21+ cảnh báo Java agent được nạp động vào JVM đang chạy.

Các triệu chứng này xuất phát từ một sự thật quan trọng: Mockito không chỉ tạo các object giả theo cách thông thường. Để cung cấp mock, nó có thể **sinh subclass hoặc biến đổi bytecode** nhờ Byte Buddy. Một số cơ chế, đặc biệt **inline mocking** phục vụ final class, static method và constructor, cần quyền `java.lang.instrument.Instrumentation`, thường được cung cấp bởi **Java agent**.

Bài học giải thích cơ chế mock, khác biệt giữa subclass và inline mock maker, quan hệ Mockito–Byte Buddy–Java agent, thay đổi của JDK 21 theo JEP 451, cách cấu hình agent trong Maven/Gradle, các lỗi do JPMS và class-file version, cùng quy trình migration để giữ bộ test ổn định. Mục tiêu là nhận biết chính xác lỗi của **test infrastructure**, không nhầm với lỗi của code nghiệp vụ.

## 1. Mockito tạo test double như thế nào?

Giả sử một service phụ thuộc gateway thanh toán:

~~~java
public interface PaymentGateway {
    boolean charge(String orderId, long minorUnits);
}
~~~

~~~java
public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public boolean checkout(String orderId, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        return gateway.charge(orderId, amount);
    }
}
~~~

Test với Mockito và JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void chargesPositiveAmount() {
        PaymentGateway gateway = mock(PaymentGateway.class);
        when(gateway.charge("ord-1", 12500L)).thenReturn(true);

        CheckoutService service = new CheckoutService(gateway);

        assertTrue(service.checkout("ord-1", 12500L));
        verify(gateway).charge("ord-1", 12500L);
        verifyNoMoreInteractions(gateway);
    }
}
~~~

Ở đây `gateway` là mock, không phải cổng thanh toán thật. Test dùng `when(...).thenReturn(...)` để stub kết quả và `verify(...)` để kiểm tra lời gọi.

Các thuật ngữ thường gặp:

| Loại test double | Vai trò | Ví dụ |
|---|---|---|
| Mock | Cấu hình hành vi và theo dõi interaction | `verify(gateway).charge(...)` |
| Stub | Cung cấp dữ liệu trả về có kiểm soát | Repository trả một entity mẫu |
| Spy | Bao quanh object thật, chỉ thay một số method | `spy(realService)` |
| Fake | Implementation đơn giản nhưng có logic thực | In-memory repository |
| Fixture | Dữ liệu hoặc setup cố định cho test | JSON, entity, token thử |

**Không phải mọi mock đều cần Java agent.** Mock interface bằng cách sinh implementation hoặc mock class thông thường bằng subclass thường có thể hoạt động mà không cần inline instrumentation. Agent trở nên quan trọng khi dùng mock maker cần biến đổi class đã có.

### 1.1. Vì sao mock không phải integration test?

Mockito cô lập logic của `CheckoutService`, nhưng test không chứng minh:
- Gateway thật hỗ trợ TLS, proxy hoặc API mới.
- HTTP client/JSON serializer chạy đúng trên JDK đích.
- Database driver, timezone, native dependency và security properties tương thích.
- Bytecode của dependency thật được JVM production nạp thành công.

Khi migration, giữ cả **unit test** và **integration/contract test**. Test với mock pass không đồng nghĩa toàn bộ hệ thống tương thích với JDK mới.

## 2. Byte Buddy, MockMaker và JVM instrumentation

Mockito dùng điểm mở rộng **MockMaker** để quyết định cách tạo mock. Byte Buddy là thư viện hỗ trợ sinh, định nghĩa và biến đổi class file; quá trình đó phải phù hợp với Java class-file format và các quy tắc JVM hiện hành.

~~~text
                 Mockito.mock(Type.class)
                           |
                           v
                     Mockito API
                           |
                           v
                        MockMaker
                           |
                +----------+----------+
                |                     |
                v                     v
        Subclass mock maker     Inline mock maker
                |                     |
        Byte Buddy tạo          Byte Buddy retransform/
        một class con           instrument class cần mock
                |                     |
        JVM nạp subclass         java.lang.instrument
                |                Instrumentation / agent
                +----------+----------+
                           |
                        Mock object
                           |
                   stub / verify calls
~~~

### 2.1. Subclass mock maker

Cơ chế subclass sinh class con kế thừa kiểu cần mock rồi override method để intercept lời gọi. Nó thường phù hợp với:
- Java interface.
- Class không `final` và có thể subclass.
- Method được override hợp lệ.
- Test không cần intercept static method hoặc constructor.

**Giới hạn:** không thể subclass final class, không override final method, không biến static method thành virtual method bằng override. Vì vậy, nếu test cần mock `final` với subclass maker, test có thể fail dù JDK có hỗ trợ agent.

Cơ chế subclass vẫn có bytecode generation, nhưng **không đồng nghĩa phải self-attach agent** để tạo các mock thông thường. Đây là lý do môi trường giới hạn instrumentation có thể vẫn chạy nhiều bài test Mockito.

### 2.2. Inline mock maker

Inline mock maker can thiệp bytecode của class cần mock, cho phép một số use case:
- Mock final class hoặc final method trong phạm vi được hỗ trợ.
- Mock static method bằng `Mockito.mockStatic(...)`.
- Mock lời gọi constructor bằng `Mockito.mockConstruction(...)`.
- Intercept những method không thể override qua subclass.

Cơ chế này thường cần `Instrumentation`. Mockito/Byte Buddy có thể tìm cách tự attach một agent vào JVM đã chạy nếu chưa có instrumentation tại startup. Khi JDK cấm hoặc cảnh báo dynamic agent loading, cách khởi tạo đó trở nên nhạy cảm với môi trường.

Inline cũng có giới hạn: một số native methods, core JVM types, class loader/module đặc biệt, finalizer và cơ chế VM nội bộ không thể được mock tùy ý. Không diễn giải “inline” thành “mock được mọi class và method”.

### 2.3. Java agent là gì?

Java agent là JAR có entrypoint agent phù hợp, cho phép JVM cung cấp một đối tượng `Instrumentation`. Khi chỉ định lúc khởi động:

~~~bash
java -javaagent:/path/to/compatible-agent.jar ...
~~~

agent có thể đăng ký transformer hoặc sử dụng cơ chế redefinition/retransformation tùy JVM cho phép. Đường dẫn phải trỏ tới **JAR thực sự có manifest/entrypoint agent hợp lệ**, không phải bất kỳ JAR nào có chữ “agent”.

Ba thành phần cần phân biệt:

| Thành phần | Công dụng | Điều cần pin |
|---|---|---|
| `mockito-core` | API Mockito và cơ chế mock maker | Version hỗ trợ JDK/test runtime |
| `byte-buddy` | Sinh/chỉnh bytecode | Version hiểu class-file release |
| `byte-buddy-agent` / Java agent | Cung cấp instrumentation theo cơ chế tương ứng | Version/cách attach và JVM policy |

Theo tài liệu Mockito 5 hiện đại, có thể truyền chính **JAR `mockito-core`** vào `-javaagent` để có instrumentation lúc JVM test bắt đầu. Cần đối chiếu với **phiên bản Mockito cụ thể** trước khi áp dụng, không tự thay bằng JAR `byte-buddy-agent` từ cache chỉ vì warning nhắc tên đó.

## 3. Các mốc Mockito quan trọng khi nâng Java

| Nội dung | Mockito 4 | Mockito 5 |
|---|---|---|
| Java baseline | Hỗ trợ Java 8+ | Yêu cầu Java 11+ |
| Mock maker thông thường | Subclass là lựa chọn mặc định trước Mockito 5 | Inline trở thành mặc định từ 5.0 |
| Mock final/static/constructor | Cần phiên bản/cấu hình inline phù hợp | Inline có sẵn theo mặc định khi JVM hỗ trợ |
| Java agent startup | Tùy mock maker và use case | Nên cấu hình tường minh cho inline trên JDK 21+ |
| `mockito-inline` artifact | Từng dùng để chọn inline | Thường không cần nữa vì inline đã mặc định |
| Chạy trên JDK mới | Phụ thuộc Mockito/Byte Buddy version | Phụ thuộc Mockito/Byte Buddy version |

**Mockito 5 không chạy được trên JVM Java 8 chỉ nhờ một compiler flag.** Nếu test runtime của dự án vẫn là Java 8, cần dùng phiên bản Mockito còn hỗ trợ Java 8 hoặc thay đổi test runtime. Mặt khác, thư viện sản phẩm vẫn có thể được biên dịch với `--release 8` trong khi quá trình test dùng JDK mới hơn, miễn artifact sản phẩm được chạy thử thực tế trên Java 8 theo cam kết hỗ trợ.

### 3.1. MockMaker extension và cấu hình cũ

Một số dự án có tệp:

~~~text
src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker
~~~

Nội dung:

~~~text
mock-maker-inline
~~~

để chọn inline mock maker trong một số version Mockito cũ. Với Mockito 5, inline thường đã là mặc định; file cũ có thể không còn cần thiết.

Nếu có lý do sử dụng subclass mock maker, có thể dùng token phù hợp:

~~~text
mock-maker-subclass
~~~

Nhưng sau khi chuyển, test dùng `mockStatic`, `mockConstruction` hoặc mock final class có thể thất bại. Cần kiểm tra nhu cầu thực tế trước khi đổi. Tránh để nhiều extension file từ dependency/test resources khiến Mockito chọn maker không như dự kiến.

### 3.2. Mockito Jupiter extension

Trong JUnit 5, integration thường nằm ở `mockito-junit-jupiter`:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class CheckoutWithExtensionTest {
    @Mock PaymentGateway gateway;
    @InjectMocks CheckoutService service;

    @Test
    void rejectsZeroAmount() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.checkout("ord-1", 0L)
        );
    }
}
~~~

Cần pin `mockito-core` và `mockito-junit-jupiter` cùng một family/version tương thích. Nếu test runner không phát hiện JUnit 5 test, kiểm tra Gradle `useJUnitPlatform()` hoặc Maven Surefire/JUnit integration trước khi kết luận lỗi agent.

## 4. JEP 451 và JDK 21+: dynamic agent loading

**JEP 451 — Prepare to Disallow the Dynamic Loading of Agents** đưa ra warning từ JDK 21 khi một Java agent hoặc JVMTI agent được **nạp động vào JVM đang chạy**. Chủ đích là chuẩn bị cho một release tương lai có thể chặn dynamic agent loading theo mặc định để nâng tính toàn vẹn của JVM.

Khi Mockito inline chưa có `Instrumentation`, Byte Buddy có thể tự attach agent. Trên HotSpot/OpenJDK JDK 21+, JVM có thể phát thông báo dạng:

~~~text
WARNING: A Java agent has been loaded dynamically (...)
WARNING: If a serviceability tool is in use, please run with
         -XX:+EnableDynamicAgentLoading to hide this warning
WARNING: If a serviceability tool is not in use, please run with
         -Djdk.instrument.traceUsage for more information
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
~~~

**Warning không phải test failure**, nhưng nó chỉ ra một cơ chế cần được xử lý trước khi runtime thắt chặt policy. Đừng chờ đến khi mọi CI job thất bại mới cấu hình agent.

### 4.1. Startup agent và dynamic attach khác nhau

| Cơ chế | Thời điểm áp dụng | Ý nghĩa |
|---|---|---|
| `-javaagent:path/to/mockito-core.jar` | Trước khi test JVM chạy main | Agent được khai báo tường minh; phù hợp khuyến nghị Mockito hiện đại |
| Mockito/Byte Buddy self-attach | Khi JVM đã chạy | Có thể phát warning JDK 21+ hoặc bị JVM policy cấm |
| `-XX:+EnableDynamicAgentLoading` | JVM launcher option | Cho phép dynamic attach, trên JDK 21 có thể ẩn warning; không phải giải pháp ưu tiên |
| `-XX:-EnableDynamicAgentLoading` | JVM launcher option | Cấm dynamic attach, hữu ích để kiểm tra sự lệ thuộc self-attach |
| `-Djdk.instrument.traceUsage` | JVM system property | Hỗ trợ chẩn đoán việc sử dụng Instrumentation |

**Không dùng `-XX:+EnableDynamicAgentLoading` chỉ để che warning** nếu test thực sự cần inline mocking. Giải pháp có chủ đích là cấu hình `-javaagent` lúc test JVM khởi động.

Cũng không được khẳng định mọi JDK 21+ đã cấm dynamic agent loading theo mặc định: thời điểm chuyển từ warning sang cấm phụ thuộc release và vendor. Với JDK mới, cần xem release notes của runtime thực tế; tránh suy đoán một mốc chỉ từ warning trên JDK 21.

### 4.2. Vì sao JEP 451 liên quan security?

Dynamic attach cấp cho agent khả năng sửa/quan sát code đang chạy ở mức thấp. Java hướng tới việc người sở hữu process JVM quyết định trước khi cho phép công cụ loại này được nạp. Khi test runtime khai báo agent bằng launcher option, quyền instrumentation trở nên rõ ràng, dễ kiểm toán và không phụ thuộc vào việc thư viện tự kích hoạt attach.

Điều này không có nghĩa phải đưa Mockito agent vào production. **Mockito là test dependency** trong cấu hình thông thường; agent phục vụ test nên được khai báo trong các JVM test cần nó.

## 5. Cấu hình Mockito Java agent trong Gradle Kotlin DSL

Trong Gradle, `testImplementation` đưa Mockito lên test classpath nhưng **không tự thêm JVM launcher option `-javaagent`**. Nên tạo một configuration riêng chỉ resolve JAR agent, rồi truyền nó cho Test task.

Ví dụ `build.gradle.kts`. Các version placeholder phải được thay bằng version đã pin và xác minh:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

val mockitoVersion = "REPLACE_WITH_PINNED_MOCKITO_VERSION"
val mockitoAgent = configurations.create("mockitoAgent")

dependencies {
    testImplementation("org.mockito:mockito-core:" + mockitoVersion)
    testImplementation("org.mockito:mockito-junit-jupiter:" + mockitoVersion)
    testImplementation("org.junit.jupiter:junit-jupiter:REPLACE_WITH_JUNIT_VERSION")

    mockitoAgent("org.mockito:mockito-core:" + mockitoVersion) {
        isTransitive = false
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    jvmArgs("-javaagent:" + mockitoAgent.asPath)
}
~~~

Ở đây:
1. Mockito API vẫn được resolve bình thường từ `testImplementation`.
2. `mockitoAgent` lấy đúng JAR `mockito-core` cùng version.
3. `isTransitive = false` tránh đưa cả bộ transitive JAR vào một argument `-javaagent`.
4. `jvmArgs(...)` truyền option cho **JVM test fork**, không phải Gradle daemon.
5. Test runner phải dùng Mockito version có khả năng được nạp bằng `-javaagent` theo tài liệu bản đó.

Đây là template cấu hình tối giản. Không chạy trước khi thay các placeholder. Các version JUnit/Mockito cần được quản lý theo BOM/version catalog/convention của repository thực tế.

### 5.1. Gradle CommandLineArgumentProvider

Với build cần configuration/build cache và tính relocatable, Gradle khuyến nghị `CommandLineArgumentProvider` với khai báo input file. Thay dòng `jvmArgs(...)` bằng provider để tránh khai báo file path như một input không được theo dõi.

~~~kotlin
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.process.CommandLineArgumentProvider

abstract class MockitoAgentProvider : CommandLineArgumentProvider {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val agentJar: ConfigurableFileCollection

    override fun asArguments(): Iterable<String> =
        listOf("-javaagent:" + agentJar.singleFile.absolutePath)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    jvmArgumentProviders.add(
        objects.newInstance(MockitoAgentProvider::class.java).apply {
            agentJar.from(mockitoAgent)
        }
    )
}
~~~

Đoạn bổ sung này dựa vào `mockitoAgent` được khai báo trước đó. **Không thêm đồng thời provider và `jvmArgs("-javaagent:...")`** nếu cả hai cùng nạp Mockito agent, vì nạp lặp có thể gây lỗi/side effect.

Nếu build có custom `integrationTest`, nhiều JVM test suite hoặc task khác không thuộc `Test` mặc định, cần đưa option vào **đúng task khởi chạy JVM có dùng inline mock**.

### 5.2. Groovy DSL

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

configurations {
    mockitoAgent
}

dependencies {
    testImplementation 'org.mockito:mockito-core:REPLACE_WITH_VERSION'
    testImplementation 'org.mockito:mockito-junit-jupiter:REPLACE_WITH_VERSION'

    mockitoAgent('org.mockito:mockito-core:REPLACE_WITH_VERSION') {
        transitive = false
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    jvmArgs '-javaagent:' + configurations.mockitoAgent.asPath
}
~~~

Ví dụ minh họa vị trí option; thêm JUnit 5 dependency và quản lý version theo project. Trường hợp build cần cache nghiêm ngặt, ưu tiên cách khai báo agent file như task input.

### 5.3. Gradle daemon JDK không đồng nghĩa test JDK

Ví dụ:

~~~text
Gradle daemon: JDK 21
Compiler toolchain: JDK 17
Test JVM: JDK 21
Application runtime floor: Java 17
~~~

`org.gradle.jvmargs` điều khiển Gradle daemon, **không phải test JVM args**. Agent cần vào `Test.jvmArgs` hoặc `Test.jvmArgumentProviders`. Nếu IDE chạy test trực tiếp bằng JUnit launcher không qua Gradle, IDE có thể không áp dụng cấu hình agent của Gradle; phải xác minh workflow thực tế.

## 6. Cấu hình Maven Surefire/Failsafe

Với Maven, `mockito-core` thường có scope `test`. Để startup agent cần truyền `-javaagent:path/to/mockito-core.jar` qua `argLine` của Surefire/Failsafe JVM fork.

Ví dụ phần cấu hình `pom.xml` (placeholder cần thay và kiểm tra với plugin version thực tế):

~~~xml
<properties>
    <mockito.version>REPLACE_WITH_PINNED_MOCKITO_VERSION</mockito.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
            <executions>
                <execution>
                    <goals>
                        <goal>properties</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
            <configuration>
                <argLine>-javaagent:${org.mockito:mockito-core:jar}</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Goal `properties` của Maven Dependency Plugin có thể đặt property chứa đường dẫn JAR đã resolve, giúp tránh hard-code đường dẫn `~/.m2/repository`. Phải xác minh property và lifecycle hoạt động trong đúng phiên bản plugin đã pin.

**Không dùng nguyên template với placeholder chưa thay.** Thêm JUnit dependency/plugin cần thiết cho dự án; kiểm tra Mockito JAR được resolve chính xác là artifact có agent manifest thích hợp.

### 6.1. Nếu dự án có JaCoCo

JaCoCo thường đặt JVM `argLine` để cài coverage agent. Nếu ghi đè `argLine` chỉ bằng Mockito, test có thể chạy nhưng không còn coverage.

Với Surefire hỗ trợ late property evaluation:

~~~xml
<properties>
    <argLine></argLine>
</properties>

<configuration>
    <argLine>
        @{argLine} -javaagent:${org.mockito:mockito-core:jar}
    </argLine>
</configuration>
~~~

Ví dụ này minh họa cách giữ `argLine` do JaCoCo cung cấp và thêm Mockito. Trong repository thực tế, cần điều chỉnh thứ tự plugin execution, property name, multi-agent configuration và lệnh JVM cuối cùng. Đừng thêm agent lặp hoặc giả định mọi Maven plugin dùng chung `argLine`.

Maven Failsafe chạy integration test ở lifecycle khác; nếu test của Failsafe cần inline mock thì phải cấu hình JVM args cho Failsafe nữa. Khi Maven và test fork dùng **JDK khác nhau** do toolchains, agent phải tương thích với **JDK test**.

## 7. Ví dụ mock final class

Giả sử API ngoài là một class `final`:

~~~java
public final class RateClient {
    public int currentRate(String currency) {
        return 100;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class RateClientTest {
    @Test
    void mocksFinalClass() {
        RateClient client = mock(RateClient.class);
        when(client.currentRate("USD")).thenReturn(25000);

        assertEquals(25000, client.currentRate("USD"));
        verify(client).currentRate("USD");
    }
}
~~~

Trong Mockito 5 với inline mock maker hoạt động và JVM hỗ trợ instrumentation, test này có thể chạy. Với subclass mock maker, `RateClient` không thể subclass vì `final`.

Để tránh coupling vào implementation, với thư viện ngoài nên cân nhắc adapter/interface thay vì mock trực tiếp class final. Tuy nhiên, trong codebase legacy, inline mock có thể là bước chuyển tiếp hữu ích khi chưa thể refactor.

## 8. Ví dụ mock static method bằng MockedStatic

Một utility cũ:

~~~java
public final class EnvironmentMode {
    private EnvironmentMode() {}

    public static String current() {
        return "PRODUCTION";
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

class EnvironmentModeTest {
    @Test
    void overridesStaticMethodTemporarily() {
        try (MockedStatic<EnvironmentMode> mocked =
                     mockStatic(EnvironmentMode.class)) {

            mocked.when(EnvironmentMode::current)
                  .thenReturn("TEST");

            assertEquals("TEST", EnvironmentMode.current());
            mocked.verify(EnvironmentMode::current);
        }

        assertEquals("PRODUCTION", EnvironmentMode.current());
    }
}
~~~

**Bắt buộc quản lý scope cẩn thận:** dùng try-with-resources để đóng static mock. Nếu không đóng, interception có thể rò sang test khác trong cùng thread, làm bộ test chỉ fail khi chạy song song hoặc chạy cả suite.

Static mocks có scope/thread semantics; không mặc định mock trong một thread sẽ áp dụng tới mọi task bất đồng bộ. Hạn chế mock core JVM classes, `System` hoặc những lớp làm việc với thread/class loader vì Mockito có thể không hỗ trợ và kết quả dễ gây side effect khó chẩn đoán.

Nếu mục tiêu test là thời gian, thường ưu tiên inject `java.time.Clock` thay vì mock các method static `now()` của JDK.

## 9. Ví dụ mock constructor bằng MockedConstruction

Code legacy tạo dependency ngay trong method:

~~~java
public class ExternalReader {
    public String load() {
        return "REAL";
    }
}
~~~

~~~java
public final class ReaderService {
    public String read() {
        return new ExternalReader().load();
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.MockedConstruction;

class ReaderServiceTest {
    @Test
    void mocksNewInstancesInsideScope() {
        try (MockedConstruction<ExternalReader> scope =
                     mockConstruction(
                             ExternalReader.class,
                             (mock, context) ->
                                     when(mock.load()).thenReturn("STUB")
                     )) {

            ReaderService service = new ReaderService();
            assertEquals("STUB", service.read());
            assertEquals(1, scope.constructed().size());
        }
    }
}
~~~

`mockConstruction` cần inline mocking phù hợp. Nó hữu ích khi chưa thể sửa legacy code, nhưng test sẽ phụ thuộc cách implementation dùng `new`. Về lâu dài, constructor injection/factory có thể cho test ổn định hơn mà không cần intercept class creation.

## 10. Chẩn đoán lỗi Mockito/Byte Buddy/JDK

| Lỗi hoặc dấu hiệu | Điều cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| JDK cảnh báo agent loaded dynamically | Mockito inline tự attach | Cấu hình `-javaagent` cho test JVM |
| Mockito self-attach warning | Test chưa có startup instrumentation | Dùng JAR Mockito agent đúng version |
| Could not initialize inline Byte Buddy mock maker | Instrumentation không khả dụng hoặc init thất bại | Agent path, JDK policy, mock maker, stack trace |
| Could not self-attach to current VM | Attach bị cấm/không có provider | Startup `-javaagent` hoặc đổi chiến lược mock |
| Mockito cannot mock this class | Class/method/VM/mock maker không hỗ trợ | Kiểm tra `final`, native, module, maker |
| Unsupported class file major version | Byte Buddy/ASM/plugin quá cũ hoặc JVM cũ | Xác minh JDK và nâng bytecode tooling |
| InaccessibleObjectException | JPMS strong encapsulation/reflection | Tìm module/package; chỉnh test/library; chỉ mở hẹp nếu cần |
| NoClassDefFoundError: net.bytebuddy... | Thiếu dependency hoặc classloader conflict | Xem test runtime classpath |
| NoSuchMethodError trong Mockito/Byte Buddy | Binary version mismatch | Kiểm tra dependency resolution, BOM |
| mockStatic already registered in current thread | Scope static mock không được đóng | try-with-resources, test cleanup |
| Test pass, coverage biến mất | Surefire `argLine` ghi đè JaCoCo | Kết hợp các agent đúng cách |
| Local pass, CI fail | JVM/test fork/container attach khác | So sánh launcher args, vendor/build |
| Agent JAR invalid/missing Premain-Class | Sai JAR/version/manifest | Kiểm tra artifact được resolve |

### 10.1. Bytecode version và Byte Buddy

Class-file major version tăng cùng JDK:

| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |

Byte Buddy cần hiểu class-file format mà nó đọc và instrument. Nếu Byte Buddy quá cũ so với JDK đích, có thể gặp thông báo tương tự:

~~~text
Java 21 (65) is not supported by the current version of Byte Buddy
~~~

Điều đó khác với `UnsupportedClassVersionError` do JVM cũ nạp class file mới. Một bên là **tool xử lý bytecode không hỗ trợ format**, một bên là **runtime JVM không hỗ trợ format**.

Khi xảy ra:
1. Kiểm tra version Mockito và Byte Buddy thực sự được chọn.
2. Kiểm tra JDK của process test, không chỉ build daemon.
3. Đọc release note Mockito/Byte Buddy cho JDK/class-file version mới.
4. Pin một tổ hợp được hỗ trợ.
5. Không tự thêm flag experimental để bỏ qua validation bytecode nếu chưa đánh giá rủi ro.

### 10.2. JPMS và reflective access

Nếu test chạy trên **module path**, Mockito hoặc thư viện được mock có thể gặp module access restrictions. Cần phân biệt:
- Module không đọc module khác: readability.
- Package chưa được export: public API access.
- Package chưa được open: deep reflection.
- Instrumentation không sẵn sàng: agent/JVM issue.

`--add-opens` không tự sửa vấn đề self-attach; `-javaagent` không tự bảo đảm mọi module/package đều accessible. Trước khi thêm flag, đọc stack trace để biết chính xác module, package và operation. Với package thuộc module do mình quản lý, cân nhắc khai báo `opens` phù hợp hoặc sửa test design. Tránh mở hàng loạt package nội bộ JDK chỉ để làm test xanh.

### 10.3. Mockito extension và dependency conflict

Một project có thể kéo Mockito qua:
- `mockito-core` trực tiếp.
- Spring Boot test starter/BOM.
- Plugin test framework.
- Dependency bắc cầu khác.
- Test resource chứa MockMaker extension.

Nếu JAR `mockito-core` là một version nhưng `mockito-junit-jupiter` hoặc Byte Buddy bị ép sang version không tương thích, có thể xuất hiện lỗi linkage không liên quan JEP 451. Dùng dependency tree để xác định artifact cuối thay vì đọc một version trong build script.

## 11. Cách quan sát JVM thực chạy test

### 11.1. Gradle

Các lệnh để điều tra trong một project thực tế:

~~~bash
./gradlew --version
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
~~~

Các lệnh cho thấy build tool/dependency graph; cần kiểm tra thêm `Test.javaLauncher`, JVM args của test fork, test suites và IDE runner. **Gradle daemon JVM khác test JVM** nếu dùng toolchain hoặc cấu hình fork.

### 11.2. Maven

~~~bash
./mvnw -version
./mvnw dependency:tree -Dscope=test
~~~

Xem Maven Surefire/Failsafe config, profile, pluginManagement và toolchains. Maven core chạy trên JDK 21 không chứng minh test fork dùng JDK 21; nếu test fork dùng JDK 17, agent phải hoạt động trên JDK 17.

### 11.3. In test JVM arguments để hỗ trợ điều tra

~~~java
import java.lang.management.ManagementFactory;
import org.junit.jupiter.api.Test;

class TestJvmInfo {
    @Test
    void printRuntimeAndInputArgs() {
        System.out.println("java.runtime.version=" +
                System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println(
                ManagementFactory.getRuntimeMXBean().getInputArguments()
        );
    }
}
~~~

Nếu danh sách input arguments không có `-javaagent:...` trên JVM chạy test, cấu hình agent chưa được truyền đúng. Không in arguments vào log công khai nếu chúng chứa secret hay system properties nhạy cảm.

### 11.4. Kiểm tra mà không cho dynamic attach

Trên JVM hỗ trợ option HotSpot tương ứng, cấu hình test fork thêm:

~~~text
-XX:-EnableDynamicAgentLoading
~~~

Nếu test dùng inline mock maker nhưng **không có startup agent**, test có thể fail khi tự attach. Nếu đã cấu hình `-javaagent` đúng, Mockito có thể lấy Instrumentation sẵn có mà không cần self-attach.

Đây là phép kiểm tra chủ động cho migration; không đồng nghĩa phải bật option này ở production. Tùy chọn có thể tác động tới profiler hoặc diagnostic tools mà môi trường vận hành sử dụng.

### 11.5. Tránh workaround dựa vào tự attach

Những hướng dẫn cũ có thể đề xuất `-Djdk.attach.allowAttachSelf=true` hoặc `-XX:+EnableDynamicAgentLoading`. Chúng không thay thế startup agent, không đảm bảo hoạt động với mọi container/vendor, và không giải quyết chủ đích integrity của JEP 451.

Không chạy container ở chế độ privileged chỉ để cho Byte Buddy tự attach. Hãy cấu hình agent rõ ràng, hoặc giảm nhu cầu instrumentation bằng subclass mock maker/test design.

## 12. Gradle/Maven test infrastructure phải nhất quán

Một Java project có thể có nhiều process:
 
~~~text
          Maven / Gradle launcher
                  |
          Plugin/configuration
                  |
        +---------+----------+
        |                    |
     Unit tests       Integration tests
       JVM A                JVM B
        |                    |
       Agent?               Agent?
        |                    |
     Mockito               Mockito
~~~

Nếu chỉ cấu hình agent cho `test`, integration suite do plugin khác tạo có thể vẫn self-attach và phát warning. Cũng tương tự với test chạy trực tiếp trong IDE, JUnit launcher của CI hoặc process trong container.

Cần lập danh sách:
- Task/process chạy test nào.
- Nó dùng JDK nào.
- Mockito và MockMaker nào đang được dùng.
- Agent JAR/version và launcher option.
- Agent khác như JaCoCo, profiler và tracing.
- Classpath/module path và quyền instrumentation.

Đừng suy từ việc **một bài test chạy được** rằng mọi suite đều được cấu hình chính xác.

## 13. Android, native image và môi trường hạn chế

### 13.1. Android

Test chạy trên Android Runtime (ART) không giống HotSpot JVM unit test. Mockito có artifact/cơ chế riêng theo phiên bản, chẳng hạn `mockito-android`. Không giả định `-javaagent:mockito-core.jar` cho Gradle JVM unit test có thể áp dụng cho Android instrumented test trên thiết bị.

Cần kiểm tra version Android Gradle Plugin, Android API level, JDK chạy build, mock maker hỗ trợ ART và từng loại test riêng.

### 13.2. Native image/GraalVM

Native image và AOT có các ràng buộc khác với JVM hỗ trợ instrumentation lúc chạy. Mock/Byte Buddy trong JVM unit test không tự chứng minh code có thể instrument tương đương ở native image runtime.

Với ứng dụng native:
- Dùng JVM tests để kiểm logic.
- Dùng native-specific tests cho artifact native.
- Hạn chế dynamic class generation ở đường production.
- Kiểm tra reflection, class initialization và AOT configuration theo framework.

Không đóng gói Mockito agent vào native production chỉ vì unit tests có inline mocking.

### 13.3. Container/CI bị giới hạn attach

Một container có thể hạn chế PID namespace, attach API, khả năng spawn process, permission và filesystem. Self-attach có thể fail trên CI dù laptop cùng JDK version chạy được.

Startup `-javaagent` làm cấu hình rõ hơn nhưng vẫn cần:
- Đúng artifact có trong filesystem container.
- JDK có hỗ trợ Java agent.
- Quyền đọc JAR và JVM option đúng.
- Runtime image/vendor/architecture đã được pin.
- Test task/runner truyền option vào đúng process.

Không mở rộng quyền container một cách không cần thiết chỉ để làm cho self-attach hoạt động.

## 14. Giảm phụ thuộc vào instrumentation bằng thiết kế test

Trong legacy code, static method và `new` cứng thường dẫn tới nhiều test phụ thuộc inline mock. Có thể chuyển dần sang injection.

Code khó kiểm thử:

~~~java
public class OrderNotifier {
    public void notifyOrder(String orderId) {
        new HttpNotifier().send(orderId);
    }
}
~~~

Thay bằng hợp đồng rõ ràng:

~~~java
public interface Notifier {
    void send(String orderId);
}
~~~

~~~java
public final class OrderNotifier {
    private final Notifier notifier;

    public OrderNotifier(Notifier notifier) {
        this.notifier = notifier;
    }

    public void notifyOrder(String orderId) {
        notifier.send(orderId);
    }
}
~~~

Test chỉ mock interface:

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;

class OrderNotifierTest {
    @Test
    void delegatesToNotifier() {
        Notifier notifier = mock(Notifier.class);
        OrderNotifier service = new OrderNotifier(notifier);

        service.notifyOrder("ord-1");

        verify(notifier).send("ord-1");
    }
}
~~~

Ưu điểm:
- Ít cần mock static/constructor.
- Test phụ thuộc contract thay vì implementation.
- Refactor hoặc thay HTTP client khi nâng JDK dễ hơn.
- Cơ chế subclass/mock interface có thể đủ cho nhiều tình huống.

Tuy nhiên, không cần bỏ toàn bộ inline mocking nếu migration có thời hạn và chi phí lớn. Nó là công cụ hợp lệ khi được cấu hình/kiểm thử rõ ràng. Cần cân bằng giữa sửa test infrastructure và sửa architecture.

## 15. Quy trình migration Mockito khi nâng JDK

### Bước 1: Chốt ma trận runtime

Ghi riêng:
- JDK chạy Maven/Gradle.
- JDK compile source và `--release` target.
- JDK unit/integration test.
- JDK production runtime và version thấp nhất còn hỗ trợ.
- Mockito/Byte Buddy/JUnit/JaCoCo version.

### Bước 2: Kiểm kê nhu cầu mock maker

Tìm static/constructor mocking và MockMaker config:

~~~bash
rg -n 'mockStatic|mockConstruction|MockedStatic|MockedConstruction' src/test
rg -n 'mockito-extensions|mock-maker-inline|mock-maker-subclass' .
~~~

Đây là cách tìm sơ bộ, không phát hiện mọi trường hợp mock `final` hay việc plugin/framework sử dụng Mockito bên trong.

### Bước 3: Chọn Mockito/Byte Buddy tương thích JDK đích

Nếu test còn Java 8, không chọn Mockito 5 cho JVM đó. Với JDK mới, kiểm tra Mockito release notes, Byte Buddy support cho class-file version, và dependency versions được BOM/plugin quản lý.

### Bước 4: Cấu hình startup agent

Khi cần inline Mockito trên JDK 21+:
1. Resolve JAR Mockito agent đúng version.
2. Truyền `-javaagent` tới JVM test (Gradle Test hoặc Surefire/Failsafe).
3. Giữ config JaCoCo/other agents.
4. Xác nhận IDE/CI/integration runners đều được xử lý.
5. Không bật cho application JVM nếu không có nhu cầu và phê duyệt.

### Bước 5: Chạy thử với dynamic attach bị tắt

Ở môi trường thích hợp, dùng `-XX:-EnableDynamicAgentLoading` cùng startup agent để xác nhận test không âm thầm phụ thuộc self-attach. Khi lỗi, xem JVM args và root cause trước khi thêm permission flag.

### Bước 6: Thử các loại test quan trọng

Chạy case:
- Mock interface/class thông thường.
- Mock final class/method.
- Static mocking với scope đóng đúng.
- Constructor mocking.
- Parallel tests, test retries và integration suite.
- Module path/classpath cùng JPMS setup thực tế.

### Bước 7: Duy trì test hành vi thật

Unit test có mock pass là tín hiệu về logic cô lập, không đủ chứng minh HTTP/TLS, JDBC, bytecode dependency và serialization trên JDK mới. Dùng integration/contract tests với dependency thật để bắt những breaking changes ở runtime.

### Bước 8: Tài liệu hóa và khóa cấu hình

Lưu Mockito/Byte Buddy versions, JDK vendor/build, agent artifact/path, launcher arguments và mock maker. Có quy trình cập nhật khi thêm JDK mới hoặc nâng framework test.

## 16. Những nhầm lẫn phổ biến

- **“Mockito nào cũng phải dùng Java agent”:** sai; subclass/interface mocks thường không cần self-attach.
- **“Mockito 5 mặc định vẫn là subclass”:** sai; Mockito 5 chuyển inline thành mặc định.
- **“Mockito 5 có thể chạy trên Java 8 nếu dùng `--release 8`”:** sai; runtime của Mockito 5 yêu cầu Java 11+.
- **“JDK 21 đã cấm mọi dynamic agent”:** JEP 451 ban đầu phát warning, cần xem chính sách release đích.
- **“Bật `-XX:+EnableDynamicAgentLoading` là xong”:** che hoặc cho phép attach, không thay startup agent có chủ đích.
- **“Có `mockito-core` trên classpath là đã cấu hình `-javaagent`”:** hai việc khác nhau.
- **“Thêm agent vào Gradle daemon thì Test JVM cũng có”:** các JVM/task có thể khác nhau.
- **“Một `argLine` mới không ảnh hưởng JaCoCo”:** có thể ghi đè coverage agent.
- **“Byte Buddy cũ vẫn hiểu mọi class-file version tương lai”:** phải kiểm tra release support.
- **“`--add-opens` sửa mọi lỗi Mockito”:** không sửa agent initialization hoặc dependency conflict.
- **“Static mock tự reset khi test kết thúc”:** scope cần đóng đúng; try-with-resources là cách rõ ràng.
- **“Mock final class có nghĩa test đã kiểm API thật”:** mock không thay integration.
- **“Android/Native Image dùng cơ chế như HotSpot”:** mỗi runtime có giới hạn riêng.
- **“Phải nâng quyền container để self-attach”:** ưu tiên startup agent hoặc test design khác.

## 17. Checklist trước khi hoàn tất migration

- [ ] Đã ghi JDK build, compiler, test và runtime thật sự.
- [ ] Đã xác định Mockito core/extension, Byte Buddy, JUnit và coverage agent versions.
- [ ] Đã biết mock maker đang dùng (subclass hay inline).
- [ ] Đã tìm các test mock final/static/constructor.
- [ ] Mockito version hỗ trợ JDK thấp nhất của test JVM.
- [ ] Byte Buddy hỗ trợ bytecode JDK mục tiêu.
- [ ] Khi cần inline trên JDK 21+, đã cấu hình `-javaagent` cho đúng Test JVM.
- [ ] Mockito agent JAR có version phù hợp và là một artifact được resolve rõ.
- [ ] Gradle Test/custom suites hoặc Maven Surefire/Failsafe đều có JVM args cần thiết.
- [ ] Cấu hình JaCoCo/profiler không bị ghi đè.
- [ ] Đã thử tắt dynamic attach trên JDK hỗ trợ option để phát hiện self-attach phụ thuộc ẩn.
- [ ] Không nhầm lỗi JPMS access với lỗi agent initialization.
- [ ] Static/constructor mock scopes được đóng đúng.
- [ ] Đã chạy unit và integration tests trên JDK mới.
- [ ] Agent không bị đưa vào runtime production ngoài ý muốn.
- [ ] Đã ghi rõ owner, version, runner, JDK vendor/build và đường nâng tiếp theo.

## 18. Tài liệu tham khảo

- [Mockito API — hướng dẫn cấu hình agent cho inline mocking trên Java 21+](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html).
- [Mockito source Javadoc về MockMaker và -javaagent](https://github.com/mockito/mockito/blob/main/mockito-core/src/main/java/org/mockito/Mockito.java).
- [Mockito 5 release notes — Java 11 baseline và inline mặc định](https://github.com/mockito/mockito/wiki/Draft-Mockito-5-release-notes).
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451).
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- [Gradle Java build caching và CommandLineArgumentProvider](https://docs.gradle.org/current/userguide/caching_java_projects.html).
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/).
- [Maven Dependency Plugin properties goal](https://maven.apache.org/plugins/maven-dependency-plugin/properties-mojo.html).

Dùng tài liệu **đúng version** của Mockito, Gradle/Maven và JDK vendor tại thời điểm triển khai. Một ví dụ từ version mới không bảo đảm áp dụng nguyên vẹn cho build plugin hoặc runtime cũ.

## 19. Kết luận

Mockito có thể tạo mock bằng cách sinh subclass hoặc dùng **inline bytecode instrumentation**. Inline mock maker, vốn là mặc định từ Mockito 5, mở rộng khả năng mock final class/method, static method và constructor nhưng làm cho **Java agent** trở thành một thành phần quan trọng của test infrastructure trong nhiều dự án.

Từ JDK 21, **JEP 451 cảnh báo khi agent được nạp động**. Hướng migration phù hợp là pin tổ hợp Mockito–Byte Buddy hỗ trợ JDK mục tiêu, truyền **`-javaagent` tường minh vào JVM chạy test**, và kiểm chứng trên Gradle/Maven, CI, IDE và các test fork liên quan. Không chỉ ẩn warning bằng flag cho phép dynamic attach, không nhầm JVM chạy build với JVM chạy test và không lấy Mockito unit test làm bằng chứng duy nhất về runtime compatibility. Khi có thể, dùng interface/dependency injection cùng integration tests để bộ kiểm thử bền vững hơn trong các lần nâng JDK tiếp theo.

# Mockito agent, mock maker và tương thích JDK

> **Module:** Spring Boot – testing  
> **Nhóm:** Chẩn đoán lỗi kiểm thử  
> **Đề bài:** Mockito agent, mock maker và tương thích JDK  
> **Mục tiêu:** Phân biệt Mockito mock maker với Java instrumentation agent, đọc đúng warning JDK 21+ theo JEP 451, cấu hình Mockito `-javaagent` ở test JVM cho Maven/Gradle, hiểu lựa chọn `INLINE`/`SUBCLASS`/`PROXY`, phát hiện mismatch Mockito/Byte Buddy/JDK và kiểm tra Spring `@MockitoBean`. Có project Java 17 + Spring Boot 3.5.0 + Mockito 5/JUnit 5 với **11 phương thức `@Test`**.

## 1. Triệu chứng: warning về agent xuất hiện khi nâng JDK

Một dự án dùng Mockito 5 đang test xanh trên JDK 17 có thể in cảnh báo khi chuyển sang JDK 21 hoặc mới hơn:

```text
Mockito is currently self-attaching to enable the inline-mock-maker.
This will no longer work in future releases of the JDK.
Please add Mockito as an agent to your build.

WARNING: A Java agent has been loaded dynamically
WARNING: Dynamic loading of agents will be disallowed by default
         in a future release
```

Đây là **trích dẫn rút gọn dạng thông báo**, không phải stdout chạy thử của project trong bài. JDK 21 đưa ra cảnh báo theo **JEP 451** khi Java agent được nạp động **sau khi JVM đã khởi động**. Trên một số môi trường, warning xuất hiện nhưng tests vẫn PASS; trên môi trường không cho attach, Mockito có thể thực sự FAIL:

```text
org.mockito.exceptions.base.MockitoInitializationException:
Could not initialize inline Byte Buddy mock maker.

It appears as if your JDK does not supply a working
agent attachment mechanism.
```

Thông điệp cụ thể phụ thuộc Mockito/Byte Buddy/JDK/vendor. Đừng gộp hai trường hợp thành “Mockito không tương thích Java 21”:

- **Warning nhưng test PASS:** Có thể inline instrumentation đã thành công bằng dynamic attach; cần migrate sang startup agent thay vì bỏ qua tương lai.
- **Error khi init inline mock maker:** Cần điều tra Java agent, VM capabilities, classpath và Byte Buddy versions.
- **Final class không mock được nhưng interface mock được:** Có thể đang dùng `SUBCLASS`/`PROXY` hoặc inline instrumentation lỗi.
- **Maven xanh, IDE đỏ:** Thường hai runners tạo JVM với arguments/JDK khác nhau.
- **Surefire fork crash:** Có thể `argLine` không được interpolate, thiếu agent jar hoặc JVM crash; không suy ra ngay bug Mockito.

**Câu hỏi đúng:** Mockito đang dùng mock maker nào? Java agent được nạp **khi JVM start** hay attach động? Có instrumentation tương thích JDK đó không? Test đang mock interface, class thường, final class, static method hay constructor?

## 2. Sơ đồ: MockMaker không phải Java agent

```text
JUnit Jupiter test
      |
      +-- Mockito.mock(...)
      +-- @Mock / @InjectMocks
      +-- Spring @MockitoBean (bean override)
      |
      v
Mockito plugin: org.mockito.plugins.MockMaker
      |
      +-- INLINE (default Mockito 5)
      |     |
      |     +-- Byte Buddy class instrumentation
      |     +-- java.lang.instrument.Instrumentation
      |           |
      |           +-- JVM startup -javaagent [khuyến nghị]
      |           +-- JVM dynamic self-attach [warning/hạn chế]
      |
      +-- SUBCLASS
      |     +-- tạo mock subclass, chỉ overridable methods/types
      |
      +-- PROXY
            +-- Java proxy, chỉ dành cho interfaces
```

**Mockito** chịu trách nhiệm stub/verify; **MockMaker** tạo mocks; **Byte Buddy** hỗ trợ bytecode instrumentation/generation; **Java agent** cho phép truy cập `Instrumentation` của JVM. Các khái niệm liên quan nhưng **không đồng nhất**.

`MockitoExtension` của JUnit 5 quản lý `@Mock`/`@InjectMocks` và validation theo method lifecycle, không phải cơ chế cung cấp JVM instrumentation. `@MockitoBean` của Spring Framework 6.2 thay một bean trong `ApplicationContext` bằng Mockito mock; nó cũng không tự cấu hình `-javaagent`.

### 2.1. Default thay đổi ở Mockito 5

Từ **Mockito 5.0**, **inline mock maker** trở thành mặc định trong `mockito-core`. Vì vậy nhiều hướng dẫn Mockito 2–4 nói “phải thêm `mockito-inline` để mock final class” đã lỗi thời với Mockito 5.

Trong Spring Boot 3.5:

- `spring-boot-starter-test` cung cấp Mockito và JUnit Jupiter theo dependency management.
- Không tự thêm `mockito-inline` chỉ vì thấy blog cũ.
- Không ép version `mockito-core` lệch với `mockito-junit-jupiter`/`byte-buddy`/`byte-buddy-agent`.
- Có thể khai `mockito-core` test dependency trực tiếp để Maven plugin resolve jar path một cách rõ ràng, vẫn để BOM quản lý version.
- Không tự thêm `mockito-subclass` cùng resource extension xung đột nếu chưa audit mock maker toàn module.

### 2.2. So sánh ba mock makers

| Năng lực | `INLINE` | `SUBCLASS` | `PROXY` |
| --- | --- | --- | --- |
| Mock interface | Có | Có | Có |
| Mock concrete non-final class | Có | Có | Không |
| Mock final class/final method | Có nếu VM hỗ trợ | Không | Không |
| `Mockito.mockStatic` | Có, giới hạn JVM/type | Không | Không |
| `Mockito.mockConstruction` | Có, giới hạn JVM/type | Không | Không |
| Cần inline Instrumentation | Có | Không cho chính mock subclass | Không cho chính interface proxy |
| Mock native methods | Inline có hạn chế | Không phải workaround | Không áp dụng |
| Phù hợp với | Final/static/constructor tests | Open non-final collaborators | Ports/interfaces |

Trong Mockito 5.17, dùng constants:

```java
MockMakers.INLINE
MockMakers.SUBCLASS
MockMakers.PROXY
```

Tương đương extension names `mock-maker-inline`, `mock-maker-subclass`, `mock-maker-proxy`. `SUBCLASS` có giới hạn kỹ thuật căn bản: không thể tạo class con của final class. `PROXY` chỉ phục vụ interface.

**Một nuance:** Chọn `withSettings().mockMaker(MockMakers.PROXY)` cho một interface không chứng minh **toàn bộ JVM** sẽ không khởi tạo default inline maker; các tests khác và plugins vẫn có thể dùng inline. Đừng suy từ một Mockito method về agent status của cả test suite.

## 3. Tương thích JDK: đừng chỉ nhìn `java.version` trong pom

Có ba loại version độc lập:

1. **Source/bytecode target:** Java 17, ví dụ `<java.version>17</java.version>`.
2. **Runtime chạy Maven, Surefire test fork hoặc IDE runner:** có thể là JDK 17, 21 hoặc mới hơn.
3. **Mockito + Byte Buddy/JUnit/Spring versions:** phải tương thích cả với bytecode và runtime.

Một POM dùng target Java 17 **vẫn có thể chạy tests trên JDK 21** nếu CI cập nhật `JAVA_HOME`. JDK 21 có cảnh báo dynamic agent load; JDK mới cũng có thể yêu cầu Byte Buddy release hỗ trợ class file format mới.

### 3.1. Java 17 baseline

- Không in cảnh báo JEP 451 mặc định của Java 21.
- Mockito inline vẫn có thể dùng instrumentation và có nhu cầu attach/agent.
- Một restricted JRE/container image có thể không cho self-attach ngay cả với JDK 17.
- Dùng explicit Mockito startup agent vẫn hợp lệ.
- Maven Surefire, Byte Buddy và Mockito versions vẫn cần align.

### 3.2. JDK 21, JEP 451 và startup agent

JEP 451 bổ sung cảnh báo khi **nạp Java agent động** vào JVM đang chạy, để chuẩn bị cho integrity-by-default. Nó không có nghĩa mọi Mockito test trên Java 21 chắc chắn fail.

Hai luồng:

```text
Có startup agent:
Surefire forks JVM -javaagent:/path/mockito-core.jar
     |
     +-- Mockito có Instrumentation lúc khởi tạo
     +-- Không phải self-attach động chỉ để enable inline
```

```text
Không có startup agent:
Surefire forks JVM
     |
     +-- Mockito inline needs Instrumentation
           |
           +-- dynamic self-attach
                 |
                 +-- warning JDK 21 hoặc attach bị từ chối
```

Đây là lý do **Mockito 5 Javadoc mục 0.3** khuyến nghị chỉ định chính `mockito-core` jar qua `-javaagent` cho JVM **chạy tests**.

### 3.3. Vì sao không chỉ dùng `-XX:+EnableDynamicAgentLoading`?

HotSpot JDK 21 có option `-XX:+EnableDynamicAgentLoading` để cho phép và suppress warning khi attach động. Nhưng:

- Vẫn dựa vào dynamic attach; không nạp agent rõ ràng từ đầu.
- Không giải quyết agent jar/version không phù hợp.
- Không giải quyết JDK thiếu/cấm attach hoặc class format không được Byte Buddy hỗ trợ.
- Không phải API JVM chuẩn hóa tương đương cho mọi vendor/JDK tương lai.
- Không được bật toàn fleet production để che cảnh báo trong test.

Có thể dùng để chẩn đoán tình huống cụ thể, nhưng **startup `-javaagent` theo Mockito docs là lựa chọn tốt hơn**. `-Djdk.instrument.traceUsage` hỗ trợ truy dấu instrumentation use, không thay việc cấu hình agent.

### 3.4. Mocking trên JVM đặc biệt

Android, GraalVM native-image, stripped/custom runtimes, container security policy hoặc JDK vendors có thể không hỗ trợ cùng kiểu instrumentation. Ngay cả khi version numbers đúng, agent có thể bị chặn; hãy xem root cause và VM supported capabilities. `SUBCLASS`/`PROXY` có thể là lựa chọn cho test-only seams phù hợp, nhưng chúng **không thể** giả làm final/static/constructor mock maker.

### 3.5. Khác biệt giữa các lỗi

| Lỗi/cảnh báo | Ý nghĩa có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Mockito is currently self-attaching` | Đang dùng dynamic attach cho inline | Startup Mockito agent |
| `WARNING: A Java agent has been loaded dynamically` | JEP 451 warning | Đọc test status và tác nhân attach |
| `Could not initialize inline Byte Buddy mock maker` | Instrumentation init không thành công | Agent, VM, Byte Buddy, attach |
| `No compatible attachment provider` | VM attach mechanism hạn chế | Startup agent/supported JDK |
| `Unsupported class file major version` | Byte Buddy/ASM không hỗ trợ bytecode/JDK | Upgrade compatible BOM/dependencies |
| `Could not modify all classes` | Type/redefinition hạn chế | Kiểm tra class hierarchy và VM |
| `Cannot mock/spy ... final class` | Dùng subclass maker hoặc inline unavailable | Maker selection, final class |
| `ClassNotFoundException org.mockito...` | Test classpath sai | Test dependencies |
| `NoClassDefFoundError net.bytebuddy...` | Byte Buddy thiếu/lệch | Dependency tree/exclusions |
| `InaccessibleObjectException` | JPMS reflective access bị giới hạn | Đọc module/package cụ thể |
| `Forked VM terminated ... goodbye` | JVM args lỗi/crash/exit | Effective Surefire launch, dumps |
| IDE đỏ, Maven xanh | JVM args/dependencies khác | IDE runner/toolchain vs Maven |

**Đừng** thêm ngẫu nhiên `--add-opens java.base/java.lang=ALL-UNNAMED`, `-Djdk.attach.allowAttachSelf` hoặc disable tests khi chưa biết root cause. Một warning không giống một exception.

## 4. Maven Surefire `-javaagent` đúng theo Mockito Javadoc

### 4.1. Nguyên tắc

- Nạp Mockito jar lúc **test JVM startup**.
- Không đặt agent chỉ ở JVM chạy Maven (Maven parent process).
- Không hard-code `~/.m2/repository` hoặc đường dẫn một developer.
- Giữ các Java agents khác như JaCoCo bằng `@{argLine}` late replacement.
- Tránh literal `@{argLine}` nếu plugin chưa cung cấp property bằng cách khai `<argLine></argLine>` mặc định.
- Surefire phải có **forked test JVM** để sử dụng agent flags theo cấu hình.

### 4.2. Maven POM pattern

```xml
<properties>
    <java.version>17</java.version>
    <argLine></argLine>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
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
            <configuration>
                <forkCount>1</forkCount>
                <reuseForks>true</reuseForks>
                <argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`maven-dependency-plugin:properties` cung cấp Maven property `${org.mockito:mockito-core:jar}` tương ứng **đường dẫn jar đã resolve**. Surefire thêm chính path đó vào `-javaagent`. `@{argLine}` được Surefire thay **muộn** nên Java agent flags từ JaCoCo `prepare-agent` không bị mất. Mockito tài liệu hóa pattern này trong chính Javadoc.

**Không nhầm ba thứ:**

- `${org.mockito:mockito-core:jar}`: Maven property do dependency plugin tạo.
- `@{argLine}`: Surefire late property replacement.
- `-javaagent:<path>`: JVM option, không phải Java system property `-D...`.

Nếu Maven không resolve property, JVM có thể cố mở agent path là chuỗi literal và Surefire fork fail. Hãy điều tra property/plugin execution, không đổi thành hard-coded absolute path.

### 4.3. Có JaCoCo thì sao?

`jacoco-maven-plugin:prepare-agent` thường ghi JVM flags vào property `argLine`. Nếu cấu hình lại Surefire bằng chỉ `<argLine>-javaagent:mockito...</argLine>`, bạn có thể vô tình **loại JaCoCo agent khỏi test JVM** và coverage report trống.

Pattern an toàn:

```xml
<argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
```

và default `<argLine></argLine>` nếu không có plugin khác set. Với dự án cấu hình `jacoco.propertyName` riêng, late replacement cần dùng đúng property name thực tế. Không dùng `mvn -DargLine=...` tùy tiện nếu chưa hiểu effect trên Surefire và coverage.

### 4.4. Vì sao `MAVEN_OPTS` không đủ?

`MAVEN_OPTS` ảnh hưởng Maven JVM. Surefire thường tạo một JVM **khác** để chạy JUnit; Maven parent không tự truyền tất cả JVM flags của mình vào fork. Nếu `forkCount=0`, semantics của `argLine` cũng khác, vì không có fork mới.

```text
Maven JVM (build)
   |
   +-- Surefire test JVM [-javaagent:mockito-core.jar]
         |
         +-- JUnit Jupiter + Mockito tests
         +-- Spring Boot test contexts
```

Config đúng ở plugin khởi tạo **test process**.

### 4.5. Lệnh chẩn đoán Maven

```bash
java -version
mvn -version

# Xem Mockito version do Boot parent quản lý:
mvn -B -ntp help:evaluate -Dexpression=mockito.version -q -DforceStdout

# Xem dependencies thực:
mvn -B -ntp dependency:tree -Dincludes=org.mockito:mockito-core,net.bytebuddy:byte-buddy,net.bytebuddy:byte-buddy-agent

# Chạy canary inline:
mvn -B -ntp -Dtest=InlineMockMakerTest test

# Chạy toàn suite:
mvn -B -ntp test
```

Nếu nghi ngờ lỗi path interpolation, dùng Maven debug mode trên CI test-only (có redaction secrets) và inspect command của Surefire fork. Không chạy `mvn test || true` vì sẽ che lỗi JVM agent.

## 5. Gradle và IDE: đúng JVM test task

Mockito Javadoc cung cấp ví dụ Gradle Kotlin DSL với một configuration chỉ lấy `mockito-core` jar làm agent, không lấy transitive dependencies làm một `-javaagent` path hỗn hợp.

### 5.1. Gradle Kotlin DSL — snippet riêng, không thuộc Maven sample

Đoạn dưới giả định version catalog đã khai `libs.mockito` trỏ tới `org.mockito:mockito-core` với version phù hợp với BOM:

```kotlin
val mockitoAgent = configurations.create("mockitoAgent")

dependencies {
    testImplementation(libs.mockito)
    mockitoAgent(libs.mockito) {
        isTransitive = false
    }
}

tasks.withType<Test>().configureEach {
    jvmArgs("-javaagent:${mockitoAgent.asPath}")
}
```

Gradle documentation/Mockito khuyến nghị sử dụng `CommandLineArgumentProvider` khi cần task caching/relocatability tốt. Nếu không dùng version catalog, cấu hình explicit coordinates/version được quản lý bởi Gradle platform/dependency management, không lấy ngẫu nhiên version từ blog.

### 5.2. IDE run configurations

- IntelliJ/Eclipse/VS Code có thể chạy JUnit với JVM riêng, không đọc Surefire `argLine`.
- Có thể delegate tests to Maven/Gradle để dùng cùng cấu hình build.
- Hoặc cấu hình startup agent trong **VM arguments của test runner**, không phải app production run config.
- Kiểm tra JDK mà IDE chạy tests, không chỉ project language level.
- Nếu IDE xanh/CI đỏ hoặc ngược lại, so sánh JDK vendor/version, classpath, mock-maker extension resources và startup flags.
- Không commit absolute local Maven repository path của một người vào cấu hình chung.

### 5.3. CI compatibility matrix

Một strategy thiết thực là chạy 2 jobs với runtime Java **17 và 21**, giữ Mockito/Boot BOM nhất quán. Nếu nâng JDK mới hơn, phải xác nhận Byte Buddy/Mockito/Boot support matrix. Không gọi build compatible chỉ vì source target=17; tests phải thực chạy trên runtime target.

Không cần GitHub Actions expression phức tạp để minh họa:

```yaml
name: Mockito Compatibility
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  jdk17:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - run: mvn -B -ntp test
  jdk21:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - run: mvn -B -ntp test
```

Đây là **workflow minh họa**, không phải bằng chứng đã chạy CI. Cả hai jobs lấy agent JVM config từ Maven POM.

## 6. Chọn mock maker per mock và cấu hình module-wide

### 6.1. INLINE

Mockito 5 default inline hỗ trợ nhiều final classes/final methods, static methods và constructor interception khi JVM cho phép instrumentation.

```java
PriceMath math = mock(PriceMath.class);
when(math.addFee(100, 5)).thenReturn(77);
assertThat(math.addFee(100, 5)).isEqualTo(77);
```

`PriceMath` là final class trong project mẫu; đây là snippet chưa có imports. Để test final type/`mockStatic`/`mockConstruction` ổn định, project cấu hình explicit Mockito agent.

### 6.2. SUBCLASS

`SUBCLASS` tạo subclass và override method, chỉ hợp lệ khi type/method overridable:

```java
OpenPricePolicy policy = mock(
        OpenPricePolicy.class,
        withSettings().mockMaker(MockMakers.SUBCLASS));

when(policy.adjust(100)).thenReturn(91);
assertThat(policy.adjust(100)).isEqualTo(91);
```

Không dùng subclass maker để mock `PriceMath` final. Một `@Service` class có `final` ở Java/Kotlin cũng không thể mock bằng maker này.

### 6.3. PROXY

`PROXY` chỉ mock interfaces, không tạo concrete-class mock:

```java
DiscountGateway gateway = mock(
        DiscountGateway.class,
        withSettings().mockMaker(MockMakers.PROXY));

when(gateway.discountPercent("u-1")).thenReturn(15);
assertThat(gateway.discountPercent("u-1")).isEqualTo(15);
```

Thiết kế một business port interface thường giúp test dùng proxy mock hoặc fake mà không đụng đến bytecode của concrete class. Nhưng mock maker proxy không cho phép `mockStatic`/constructor interception.

### 6.4. Mock-maker extension file — ví dụ chỉ để tham khảo

Đổi maker của **cả module** có thể tạo file:

```text
src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker
```

với nội dung:

```text
mock-maker-subclass
```

**Không tạo file này trong project sample bên dưới.** Nó sẽ làm các inline tests mock final/static/constructor không còn hợp lệ. Cẩn thận nếu có nhiều extension resources/plugin artifacts mâu thuẫn: Mockito sẽ resolve plugin trên classpath và behavior có thể khác kỳ vọng. Nếu team cần dùng subclass vì runtime hạn chế, refactor code theo interface/seam và audit tests trước khi đổi global config.

### 6.5. Không mock những thứ không cần mock

- Với pure arithmetic, gọi real method và assert result, không cần mock `PriceMath` trong business suite.
- Với clock/time, inject `Clock` để khỏi mock `LocalDateTime.now` static.
- Với IDs/random, inject generator interface để không cần mock `UUID.randomUUID`.
- Với network/DB, mock adapter boundary trong unit tests và dùng integration tests cho protocol thật.
- Với Spring AOP/transaction, mock service không chứng minh `@Transactional` advice chạy thật.
- Tránh mock `System`, `Thread`, `ClassLoader` và các JVM core types nhạy cảm.
- Static/constructor mocking đặc biệt dễ làm test coupling nếu quên đóng scope.

## 7. Spring Boot: `@Mock`, `@InjectMocks` và `@MockitoBean` khác nhau

### 7.1. Pure unit test

```java
@ExtendWith(MockitoExtension.class)
class ServiceTest {
    @Mock DiscountGateway gateway;
    @InjectMocks BillingService service;
}
```

MockitoExtension khởi tạo field mocks, áp dụng inject strategy/lifecycle, kiểm tra tương tác. Nó **không** khởi động Spring ApplicationContext.

### 7.2. Spring context bean override

Với Spring Framework 6.2/Boot 3.5:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` thay hoặc thêm bean Mockito vào **Spring test context** theo matching rules. Nó không khác `@Mock` chỉ ở tên; nó thay dependency mà Controller/Service autowire.

Ví dụ:

```java
@WebMvcTest(BillingController.class)
class BillingControllerSliceTest {
    @MockitoBean BillingService service;
    @Autowired MockMvc mvc;
}
```

Test này mock một **final BillingService**: default Mockito 5 inline/agent phải hoạt động. `@WebMvcTest` không load toàn bộ service layer; bean override cung cấp collaborator cần thiết. Nó không khởi động real HTTP server.

### 7.3. `@SpringBootTest` dùng mock collaborator, real service

```java
@SpringBootTest
class BillingSpringIntegrationTest {
    @MockitoBean DiscountGateway gateway;
    @Autowired BillingService service;
}
```

Đây là real Spring service bean, nhưng gateway bị override bởi Mockito. Test kiểm tra Spring wiring + business behavior, không chứng minh remote payment/discount API thật hoạt động.

### 7.4. Legacy `@MockBean`

Spring Boot 3.4+ deprecate các `@MockBean`/`@SpyBean` legacy của Boot để chuyển sang Spring Framework `@MockitoBean`/`@MockitoSpyBean`. Project pin Boot 3.5 nên dùng import `org.springframework.test.context.bean.override.mockito.MockitoBean`, không trộn imports của Boot 2.7/Boot 4.

### 7.5. Chẩn đoán Spring bean override

- Nếu chỉ dùng `@Mock` field, Spring có thể vẫn inject bean production thật.
- Nếu có nhiều beans cùng interface, dùng `@Qualifier` hoặc `@MockitoBean(name=...)`.
- `@MockitoBean(enforceOverride=true)` yêu cầu bean có sẵn; có ích để bắt cấu hình test thiếu.
- `@MockitoBean` mặc định có thể REPLACE_OR_CREATE nếu không có bean theo match.
- `@MockitoSpyBean` wraps bean thật, có thể gọi real methods/side effects; thường stub bằng `doReturn` thay `when(realMethod())`.
- Nếu contexts cached và tests chạy parallel, hai tests cùng reset/stub shared mock có thể race.
- Test với mock bean không chứng minh Spring AOP `@Transactional`/`@Async`/security advice thật của bean đã mock.

## 8. Dự án Java 17, Boot 3.5.0, 11 JUnit tests

Project dùng Mockito 5 version do Boot BOM quản lý. Maven Surefire truyền `-javaagent` vào test JVM ngay cả trên JDK 17, nên khi chuyển sang JDK 21 không phụ thuộc dynamic self-attach cho inline instrumentation.

### 8.1. Cây files

```text
mockito-agent-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/mockitoagent/
    │   ├── MockitoAgentApplication.java
    │   ├── DiscountGateway.java
    │   ├── DefaultDiscountGateway.java
    │   ├── BillingService.java
    │   ├── BillingController.java
    │   ├── PriceMath.java
    │   └── OpenPricePolicy.java
    └── test/java/com/example/mockitoagent/
        ├── InlineMockMakerTest.java
        ├── AlternativeMockMakerTest.java
        ├── BillingServiceTest.java
        ├── BillingControllerSliceTest.java
        └── BillingSpringIntegrationTest.java
```

Không có `mockito-extensions` file hoặc `mockito-inline` dependency trong sample. Mỗi public Java type ở file đúng tên, tất cả ở package `com.example.mockitoagent`.

### 8.2. `pom.xml` — đầy đủ agent config

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mockito-agent-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <argLine></argLine>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
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
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                    <argLine>@{argLine} -javaagent:${org.mockito:mockito-core:jar}</argLine>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vì sao khai `mockito-core` trực tiếp?** Để dependency plugin có một artifact path rõ cho agent; version vẫn được quản lý bởi Spring Boot BOM, dù `starter-test` đã transitively bao gồm Mockito.

**Vì sao `@{argLine}` và `<argLine></argLine>`?** Mockito Javadoc nhắc tới Surefire late replacement và khả năng literal `@{argLine}` gây fork failure nếu property không tồn tại.

### 8.3. `MockitoAgentApplication.java`

```java
// src/main/java/com/example/mockitoagent/MockitoAgentApplication.java
package com.example.mockitoagent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockitoAgentApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockitoAgentApplication.class, args);
    }
}
```

### 8.4. `DiscountGateway.java`

```java
// src/main/java/com/example/mockitoagent/DiscountGateway.java
package com.example.mockitoagent;

public interface DiscountGateway {
    int discountPercent(String customer);
}
```

### 8.5. `DefaultDiscountGateway.java`

```java
// src/main/java/com/example/mockitoagent/DefaultDiscountGateway.java
package com.example.mockitoagent;

import org.springframework.stereotype.Component;

@Component
public class DefaultDiscountGateway
        implements DiscountGateway {

    @Override
    public int discountPercent(String customer) {
        return 0;
    }
}
```

Adapter demo không gọi network. Trong full-context test, `@MockitoBean DiscountGateway` thay bean này.

### 8.6. `BillingService.java`

```java
// src/main/java/com/example/mockitoagent/BillingService.java
package com.example.mockitoagent;

import org.springframework.stereotype.Service;

@Service
public final class BillingService {

    private final DiscountGateway gateway;

    public BillingService(DiscountGateway gateway) {
        this.gateway = gateway;
    }

    public int totalFor(String customer, int subtotal) {
        if (customer == null || customer.isBlank()
                || subtotal < 0) {
            throw new IllegalArgumentException(
                    "invalid billing request");
        }

        int discount = gateway.discountPercent(customer);
        if (discount < 0 || discount > 100) {
            throw new IllegalStateException(
                    "invalid discount");
        }

        return Math.toIntExact(
                (long) subtotal * (100 - discount) / 100);
    }
}
```

Final service giúp minh họa `@MockitoBean` cần inline maker trong MVC slice. Nó không dùng Spring AOP/`@Transactional` nên Java final modifier không ngăn ứng dụng demo tạo Spring bean trực tiếp. Công thức integer pricing chỉ dành cho bài học mocking, không thay production monetary rounding policy.

### 8.7. `BillingController.java`

```java
// src/main/java/com/example/mockitoagent/BillingController.java
package com.example.mockitoagent;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/billing")
public class BillingController {

    private final BillingService service;

    public BillingController(BillingService service) {
        this.service = service;
    }

    @GetMapping("/{customer}")
    public int total(
            @PathVariable String customer,
            @RequestParam int subtotal) {
        return service.totalFor(customer, subtotal);
    }
}
```

`@RestController` sẽ serialize `int` thành JSON number; MockMvc assert string representation như `85`.

### 8.8. `PriceMath.java`

```java
// src/main/java/com/example/mockitoagent/PriceMath.java
package com.example.mockitoagent;

public final class PriceMath {

    public int addFee(int base, int fee) {
        return Math.addExact(base, fee);
    }

    public static String currencyCode() {
        return "VND";
    }
}
```

Test final/static/constructor uses this class. Đó là **instrumentation canary**, không phải lời khuyên mock arithmetic thông thường.

### 8.9. `OpenPricePolicy.java`

```java
// src/main/java/com/example/mockitoagent/OpenPricePolicy.java
package com.example.mockitoagent;

public class OpenPricePolicy {

    public int adjust(int amount) {
        return amount + 10;
    }
}
```

Class không final, method không final, phù hợp SUBCLASS maker.

## 9. Mười một JUnit methods

### 9.1. `InlineMockMakerTest.java` — 4 tests

```java
// src/test/java/com/example/mockitoagent/InlineMockMakerTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;
import org.mockito.MockedConstruction;
import org.mockito.MockedStatic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockConstruction;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.withSettings;

class InlineMockMakerTest {

    @Test
    void canMockFinalClass() {
        PriceMath math = mock(PriceMath.class);
        when(math.addFee(100, 5)).thenReturn(77);

        assertThat(math.addFee(100, 5)).isEqualTo(77);
        verify(math).addFee(100, 5);
    }

    @Test
    void staticMockIsScopedAndRestored() {
        assertThat(PriceMath.currencyCode())
                .isEqualTo("VND");

        try (MockedStatic<PriceMath> scoped =
                     mockStatic(PriceMath.class)) {
            scoped.when(PriceMath::currencyCode)
                    .thenReturn("TEST");

            assertThat(PriceMath.currencyCode())
                    .isEqualTo("TEST");
            scoped.verify(PriceMath::currencyCode);
        }

        assertThat(PriceMath.currencyCode())
                .isEqualTo("VND");
    }

    @Test
    void constructionMockIsScopedAndRestored() {
        try (MockedConstruction<PriceMath> constructed =
                     mockConstruction(
                             PriceMath.class,
                             (mock, context) ->
                                     when(mock.addFee(100, 5))
                                             .thenReturn(42))) {
            PriceMath created = new PriceMath();

            assertThat(created.addFee(100, 5))
                    .isEqualTo(42);
            assertThat(constructed.constructed())
                    .containsExactly(created);
        }

        assertThat(new PriceMath().addFee(100, 5))
                .isEqualTo(105);
    }

    @Test
    void explicitInlineMakerSupportsFinalType() {
        PriceMath math = mock(
                PriceMath.class,
                withSettings().mockMaker(MockMakers.INLINE));

        when(math.addFee(10, 5)).thenReturn(99);
        assertThat(math.addFee(10, 5)).isEqualTo(99);
        verify(math).addFee(10, 5);
    }
}
```

`MockedStatic` và `MockedConstruction` implement scoped mocking; **đóng bằng try-with-resources** là bắt buộc để không contaminating test thread sau đó. Mock static thường chỉ áp dụng trong thread tạo scope; không coi nó là global fake cho async background threads.

### 9.2. `AlternativeMockMakerTest.java` — 2 tests

```java
// src/test/java/com/example/mockitoagent/AlternativeMockMakerTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.mockito.MockMakers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.withSettings;

class AlternativeMockMakerTest {

    @Test
    void subclassMakerMocksOverridableClass() {
        OpenPricePolicy policy = mock(
                OpenPricePolicy.class,
                withSettings().mockMaker(MockMakers.SUBCLASS));

        when(policy.adjust(100)).thenReturn(91);
        assertThat(policy.adjust(100)).isEqualTo(91);
        verify(policy).adjust(100);
    }

    @Test
    void proxyMakerMocksInterfaceOnly() {
        DiscountGateway gateway = mock(
                DiscountGateway.class,
                withSettings().mockMaker(MockMakers.PROXY));

        when(gateway.discountPercent("u-1"))
                .thenReturn(15);

        assertThat(gateway.discountPercent("u-1"))
                .isEqualTo(15);
        verify(gateway).discountPercent("u-1");
    }
}
```

Bài không cố mock `PriceMath` bằng `SUBCLASS` vì nó final; một test cố tình fail không cần có trong runnable suite. Hãy dùng bài tập riêng để thấy exception, không biến Maven CI thành always-red.

### 9.3. `BillingServiceTest.java` — 2 pure unit tests

```java
// src/test/java/com/example/mockitoagent/BillingServiceTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class BillingServiceTest {

    @Mock
    DiscountGateway gateway;

    @InjectMocks
    BillingService service;

    @Test
    void totalUsesDiscountFromMock() {
        when(gateway.discountPercent("u-1"))
                .thenReturn(15);

        assertThat(service.totalFor("u-1", 200))
                .isEqualTo(170);

        verify(gateway).discountPercent("u-1");
    }

    @Test
    void invalidInputDoesNotCallGateway() {
        assertThatThrownBy(
                () -> service.totalFor(" ", 100))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid billing request");

        verifyNoInteractions(gateway);
    }
}
```

`@InjectMocks` của Mockito dựng service qua constructor. Nó không phải Spring `@Autowired` và không khởi tạo ApplicationContext.

### 9.4. `BillingControllerSliceTest.java` — 2 MVC tests

```java
// src/test/java/com/example/mockitoagent/BillingControllerSliceTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BillingController.class)
class BillingControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    BillingService service;

    @Test
    void controllerUsesMockedFinalService()
            throws Exception {
        when(service.totalFor("u-1", 100))
                .thenReturn(85);

        mvc.perform(get("/billing/u-1")
                        .param("subtotal", "100"))
                .andExpect(status().isOk())
                .andExpect(content().string("85"));

        verify(service).totalFor("u-1", 100);
    }

    @Test
    void missingParameterDoesNotInvokeService()
            throws Exception {
        mvc.perform(get("/billing/u-2"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

`@MockitoBean` thay final service bean trong MVC slice. `@WebMvcTest` không load service business thật theo mặc định; đây là controller wiring/routing test với mock Servlet environment, không phải end-to-end TCP server test.

### 9.5. `BillingSpringIntegrationTest.java` — 1 full-context test

```java
// src/test/java/com/example/mockitoagent/BillingSpringIntegrationTest.java
package com.example.mockitoagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class BillingSpringIntegrationTest {

    @Autowired
    BillingService service;

    @MockitoBean
    DiscountGateway gateway;

    @Test
    void fullContextUsesGatewayOverride() {
        when(gateway.discountPercent("u-2"))
                .thenReturn(25);

        assertThat(service.totalFor("u-2", 200))
                .isEqualTo(150);

        verify(gateway).discountPercent("u-2");
    }
}
```

Đây là real `BillingService` bean + mocked `DiscountGateway` trong Spring context. `@SpringBootTest` mặc định **không** start embedded HTTP server. Test này không chứng minh remote provider contract/production tracing hay transaction semantics.

### 9.6. Test count và lệnh chạy

| Test class | `@Test` methods | Kiểm chứng |
| --- | ---: | --- |
| `InlineMockMakerTest` | 4 | Final/static/constructor/per-mock inline |
| `AlternativeMockMakerTest` | 2 | Subclass/proxy per mock |
| `BillingServiceTest` | 2 | MockitoExtension |
| `BillingControllerSliceTest` | 2 | @WebMvcTest và @MockitoBean |
| `BillingSpringIntegrationTest` | 1 | @SpringBootTest và @MockitoBean |
| **Tổng** | **11** | Không Docker, không external service |

```bash
java -version
mvn -version

# Inline canaries:
mvn -B -ntp -Dtest=InlineMockMakerTest test

# Chọn mock maker khác:
mvn -B -ntp -Dtest=AlternativeMockMakerTest test

# Pure unit:
mvn -B -ntp -Dtest=BillingServiceTest test

# Spring slice/full:
mvn -B -ntp -Dtest=BillingControllerSliceTest,BillingSpringIntegrationTest test

# Tất cả 11 methods:
mvn -B -ntp test
```

**Kỳ vọng theo mã nguồn:** tests PASS khi JDK/Mockito/Byte Buddy compatible và Surefire khởi động test JVM với Mockito agent. Đây là lời hướng dẫn để người học **tự thực thi**. Không tuyên bố đã chạy Maven/JUnit, không bịa log `BUILD SUCCESS` hay số mili-giây.

## 10. Troubleshooting theo triệu chứng

### 10.1. Warning động trên JDK 21, assertions vẫn xanh

Tình huống: Mockito tự attach thành công nhưng JVM in warning theo JEP 451.

Giải pháp: dùng `maven-dependency-plugin:properties` và Surefire `-javaagent:${org.mockito:mockito-core:jar}`. Kiểm tra agent đã vào **test JVM**, rồi chạy lại final/static canary. Nếu còn warning từ agents khác, điều tra đúng process/agent; không tắt toàn bộ logging JVM.

### 10.2. Inline mock maker không khởi tạo

Checklist:

1. `java -version`/`mvn -version` có dùng đúng JDK/VM vendor không?
2. Mockito/Byte Buddy version nào được resolve?
3. Có exclusion làm thiếu `byte-buddy-agent`/`byte-buddy`?
4. Có startup `-javaagent` từ đúng Mockito core jar trong test JVM?
5. JVM có support instrumentation/redefinition không?
6. Có đang chạy trong custom JRE/Android/native image/restricted container?
7. Có mock-maker extension file/`mockito-subclass` làm plugin selection lệch?
8. Stack trace root cause xảy ra lúc agent attach hay lúc transform class?

Không dùng `--add-opens` như thuốc chữa mặc định; chỉ khi root cause thật là module encapsulation có thể cân nhắc targeted options sau security review.

### 10.3. Final mock thất bại sau khi đổi maker

`SUBCLASS` không kế thừa được final class/method. `PROXY` chỉ có thể mock interfaces. Dùng INLINE nếu environment phù hợp, hoặc refactor code nhận interface/port và test theo behavior. Đừng sửa bằng `@SuppressWarnings` hoặc ép Mockito bỏ qua exception.

### 10.4. Static mock leak làm test kế tiếp fail

`MockedStatic` và `MockedConstruction` phải được đóng. Với static:

```java
try (MockedStatic<PriceMath> scoped =
             Mockito.mockStatic(PriceMath.class)) {
    // mock and assert in this scope
}
// MockedStatic.close() tự động.
```

Không giữ static mock trên field chia sẻ qua test classes hoặc để nó qua một thread boundary. Nếu cần thời gian giả, inject `Clock` thay vì mock static globally.

### 10.5. `@MockitoBean` không replace bean mong đợi

- `@Mock` JUnit field không đăng ký Spring bean.
- `@WebMvcTest` slice chỉ load MVC, phải cung cấp mock service collaborator.
- Multiple beans cùng type cần qualifier/name.
- `@MockitoBean(enforceOverride=true)` có thể giúp phát hiện thiếu bean thay vì REPLACE_OR_CREATE im lặng.
- Bean target là final nhưng global mock maker bị ép SUBCLASS.
- Test context cache/mocking reset cùng lúc trong parallel tests gây state races.

Đừng thay mọi slice thành `@SpringBootTest` chỉ vì bean override sai; sửa import và context match.

### 10.6. JaCoCo report rỗng sau khi thêm agent

Nếu Surefire `argLine` chỉ có Mockito agent, JaCoCo `prepare-agent` có thể bị loại. Giữ `@{argLine}` late replacement và optional empty `argLine` property. Verify JVM fork command có cả JaCoCo + Mockito agents, không đưa JaCoCo vào application production runtime để chữa test coverage.

### 10.7. Forked VM terminated without goodbye

Đây là thông báo chung của Surefire khi test fork chấm dứt bất thường. Cần xem `target/surefire-reports`, dump logs, JVM command:

- Literal `@{argLine}` chưa replace.
- Literal `${org.mockito:mockito-core:jar}` hoặc đường dẫn jar sai.
- `forkCount=0` khiến flags không đi vào fork dự kiến.
- Agent JAR không tương thích hoặc không đọc được.
- JaCoCo/Mockito agents overwrite nhau.
- `System.exit()` trong test, OutOfMemory hoặc native JVM crash.
- Windows paths/quoting và CI environment khác local.

Không biến build fail thành pass bằng `mvn test || true`.

### 10.8. Byte Buddy không hỗ trợ JDK mới

Lỗi “Unsupported class file major version” hoặc “Java N not supported” đòi đối chiếu Mockito/Byte Buddy/JDK matrix. Nên nâng Spring Boot patch/version cùng managed dependencies được hỗ trợ. Tránh giữ một Mockito 5.x cũ và override ngẫu nhiên một Byte Buddy jar mới/old trên classpath; đồng bộ versions và chạy canary tests.

### 10.9. IDE đỏ, Maven xanh

IDE JUnit runner thường không đọc Maven Surefire `argLine`. Chạy delegated to Maven/Gradle hoặc thiết lập VM arguments cho test runner. Kiểm tra runtime JDK/path của IDE và Maven, không chỉ language level.

### 10.10. MockMaker warnings không thay integration tests

Mockito tests xác nhận contract ở seam mock. Chúng không thay real HTTP/database/broker integration tests. Một test `verify(gateway).discountPercent("u-1")` không chứng minh production endpoint có thể kết nối hoặc transaction commit đúng.

## 11. Security và kiểm thử khả năng nâng JDK

### 11.1. Vì sao JEP 451 quan trọng?

Java agent có năng lực sửa class bytecode của JVM đang chạy. Integrity-by-default hướng tới việc operators chấp nhận agents qua startup flags thay vì thư viện tự ý attach sau startup. `-javaagent` được khai ở test build có thể code review, pin dependency và kiểm soát.

**Không** tự đưa Mockito agent/`EnableDynamicAgentLoading` vào production JVM, chỉ vì CI test warning. Giữ production privileges tối thiểu và quan sát những agents khác riêng biệt.

### 11.2. Diagnosing readiness with dynamic attach disabled

Trên HotSpot JDK có hỗ trợ flag, một job test có thể sử dụng:

```text
-XX:-EnableDynamicAgentLoading
-javaagent:<resolved Mockito core jar>
```

để kiểm chứng Mockito inline vẫn hoạt động khi **startup instrumentation** đã có mà dynamic agent loading bị tắt. Đây là thử nghiệm chẩn đoán tùy environment, không phải cấu hình bắt buộc; công cụ coverage/profiler khác có thể vẫn muốn attach động.

### 11.3. Canary tests cần thiết

Một test chỉ mock interface có thể pass với PROXY hoặc SUBCLASS và không chứng minh inline instrumentation. Khi nâng JDK/Mockito/Byte Buddy, nên giữ canaries:

- Mock một **final** class.
- Mock static method và đóng scope.
- Mock construction và đóng scope nếu production tests thực sự dùng.
- `@MockitoBean` trên final service trong slice nếu team dùng pattern đó.
- Thử test fork startup flags trên JDK 17 + 21 + runtime ứng viên.

**Không** để warning JDK21 biến thành full-suite suppression; thay vào đó ghi nhận version/agent path cụ thể và sửa vào build.

## 12. Ma trận chẩn đoán nhanh

| Tín hiệu | Phân loại | Cách xác nhận |
| --- | --- | --- |
| JDK21 dynamic attach warning | Warning chưa chắc fail | Run test + capture result |
| Final mock cannot initialize | Instrumentation/maker | Inline canary, root cause |
| Mockito version 5.x + mockito-inline legacy | Classpath/version risk | dependency tree |
| Byte Buddy major unsupported | JDK/library mismatch | Upgrade managed versions |
| Mockito init JDK17 restricted runtime | Agent capability | Explicit startup agent + vendor check |
| Mockito mock works but @MockitoBean fails | Spring context/config | Correct annotation/import and qualifier |
| Mockito final fails under SUBCLASS | Maker cannot extend final | INLINE or port interface |
| Proxy maker concrete class error | Wrong target type | Mock interface only |
| mockStatic already registered | Scope not closed | try-with-resources |
| JaCoCo coverage lost | argLine overwritten | @{argLine} late replacement |
| Maven passes, IDE fails | Test VM mismatch | Compare launch args/JDK |
| Surefire fork crash | JVM launch/agent/crash | Inspect fork command and dumps |
| Full-context tests slow after overrides | Cache keys differ | Standardize @MockitoBean field qualifiers |
| Shared Mockito beans concurrent failures | Mock reset/stub race | Serialize or pure unit per-method mocks |

## 13. Checklist trước khi merge thay đổi Mockito/JDK

- [ ] Xác nhận JDK chạy **test JVM** chứ không chỉ Java source target.
- [ ] Mockito 5 inline maker là default; không thêm mockito-inline legacy nếu không cần.
- [ ] Mockito/Byte Buddy/Byte Buddy Agent cùng dependency management hợp lệ.
- [ ] Dùng `-javaagent` trỏ mockito-core jar ở **test fork startup**.
- [ ] Maven dependency plugin properties resolve đường dẫn jar portable.
- [ ] Surefire forkCount và argLine đúng; không truyền agent chỉ qua Maven parent.
- [ ] `@{argLine}` giữ JaCoCo/other agents.
- [ ] Empty argLine property có nếu needed, không để literal late replacement.
- [ ] IDE test runner dùng agent tương đương hoặc delegate Maven.
- [ ] JDK 17/21 matrix chạy inline canary.
- [ ] Không bật dynamic attach flag toàn production.
- [ ] Không dùng `SUBCLASS` với final class hoặc final methods.
- [ ] Không dùng `PROXY` với concrete class.
- [ ] `mockStatic` và `mockConstruction` được close đúng scope.
- [ ] Spring `@MockitoBean` khác Mockito `@Mock`.
- [ ] Bean override qualifiers/context cache và concurrency được kiểm soát.
- [ ] Không dùng Mockito mock để chứng minh AOP/DB/HTTP thật.
- [ ] Unsupported class file errors xử lý bằng compatible library/JDK versions.
- [ ] Khi fail, lưu root cause stack trace, JVM args và dependency tree.
- [ ] Không gọi tests PASS nếu chưa thực thi.

## 14. Bài tập

1. Chạy `InlineMockMakerTest` trên JDK 17 và 21; so sánh warnings, xác minh test fork có startup Mockito agent.
2. Bỏ startup agent ở nhánh thử nghiệm, kiểm tra JEP451 warning so với test failure trên JVM của bạn; không đụng production flags.
3. Thử mock `PriceMath` final với `SUBCLASS` trong bài tập tách riêng; giải thích vì sao không thể, rồi refactor seam.
4. Thử `MockMakers.PROXY` với `DiscountGateway` và một concrete class; phân biệt interface-only limitation.
5. Xóa scope close của `MockedStatic` trong sandbox rồi xem lỗi mock leak; khôi phục `try-with-resources`.
6. Dùng MockitoExtension `@Mock` và Spring `@MockitoBean` trong hai tests khác nhau, chỉ ra object được Spring autowire.
7. Thêm JaCoCo `prepare-agent` và kiểm tra JVM có cả coverage agent + Mockito agent.
8. Chạy từ IDE riêng so với Maven; đối chiếu launcher/test JDK, classpath và JVM args.
9. Tạo JDK candidate CI job, ghi dependency tree khi class format unsupported.
10. Trên test-only HotSpot VM, thử dynamic attach disabled + explicit startup Mockito agent; ghi rõ nếu agents khác fail.
11. Refactor một static `Clock.systemUTC` wrapper thành constructor-injected `Clock` để tránh static mocking trong async code.
12. Xây một error classifier phân biệt warning, `MockitoInitializationException`, unsupported class version, bean-override failure và Surefire fork failure.

## 15. Câu hỏi tự kiểm tra

**1.** Mockito 5 mặc định dùng maker nào? — `INLINE`.

**2.** MockMaker là Java agent không? — Không. MockMaker là chiến lược tạo mock; agent cung cấp `Instrumentation`.

**3.** JDK21 warning có đồng nghĩa tất cả tests đỏ không? — Không; phải xem status/root cause.

**4.** Cấu hình được khuyến nghị khi cần inline trên Java21+? — Startup `-javaagent` trỏ Mockito core jar ở test JVM.

**5.** `-XX:+EnableDynamicAgentLoading` có tốt hơn startup agent không? — Không, nó vẫn dựa dynamic attach.

**6.** `SUBCLASS` mock final class được không? — Không.

**7.** `PROXY` mock concrete class được không? — Không, maker này dùng interfaces.

**8.** Vì sao `MockedStatic` nên nằm trong try-with-resources? — Để close scope/không leak behavior.

**9.** `@Mock` có đăng ký mock thành Spring bean? — Không; `@MockitoBean` dành cho context override.

**10.** `@MockitoBean` tự sửa lỗi attach agent không? — Không, vẫn dùng Mockito mock maker.

**11.** `MAVEN_OPTS` có luôn đến Surefire fork không? — Không.

**12.** Vì sao `@{argLine}` có ích? — Giữ flags từ JaCoCo/late replacement.

**13.** Khi có `Unsupported class file major version`, nên làm gì? — Kiểm tra Byte Buddy/Mockito/JDK compatibility.

**14.** Test mock final PASS có chứng minh app production compatible mọi JDK? — Không, chỉ bảo vệ mock instrumentation boundary đó.

## 16. Tài liệu chính thức

- [Mockito 5.17 Javadoc — Mockito](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/Mockito.html): inline default; mục 0.3 Java 21 agent Maven/Gradle; API static/constructor mocking.
- [Mockito 5.17 — MockMakers](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockMakers.html): INLINE/SUBCLASS/PROXY và giới hạn.
- [Mockito 5.17 — MockedStatic](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockedStatic.html): scoped static mock lifecycle.
- [Mockito 5.17 — MockedConstruction](https://javadoc.io/static/org.mockito/mockito-core/5.17.0/org.mockito/org/mockito/MockedConstruction.html): constructor interception scope.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): dynamic agent loading warnings/integrity-by-default.
- [Oracle JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html): `EnableDynamicAgentLoading` semantics.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest` và MockitoBean tests.
- [Spring Framework 6.2 — MockitoBean & MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean matching/override.
- [Spring Boot 3.5 — Dependency versions](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Mockito/Byte Buddy BOM.
- [Apache Maven Surefire — fork options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options.html): `forkCount`/`reuseForks`.
- [Apache Maven Surefire — test mojo](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo): `argLine`/late replacement.
- [JaCoCo — Maven prepare-agent](https://www.jacoco.org/jacoco/trunk/doc/prepare-agent-mojo.html): coverage Java agent integration.
- [Gradle — Testing Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test task JVM args.

**Kết luận:** Mockito 5 inline là một **mock maker**, Java agent là cơ chế cấp JVM instrumentation cho nó. JDK 21 cảnh báo **dynamic loading**, không kết luận mọi test fail; nếu inline cần instrumentation, ưu tiên `-javaagent` của `mockito-core` lúc **test JVM startup** theo Mockito docs. `SUBCLASS`/`PROXY` hữu ích cho test seams phù hợp nhưng không thay final/static/constructor mocking. Khi chẩn đoán, kiểm tra JDK **runtime**, Mockito/Byte Buddy **dependency tree**, Surefire/IDE **JVM args**, Mockito **MockMaker** và Spring `@MockitoBean` wiring thay vì bật một flag chung cho mọi failure.
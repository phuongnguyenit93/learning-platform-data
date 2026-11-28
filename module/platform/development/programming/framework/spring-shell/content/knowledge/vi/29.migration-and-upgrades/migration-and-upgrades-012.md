# Chuyển API kiểm thử và kiểm tra lại hỗ trợ native

Khi nâng cấp một ứng dụng Spring Shell từ 3.x lên 4.x, cần kiểm tra hai phần có liên quan nhưng không thay thế cho nhau: bộ API kiểm thử command và khả năng đóng gói ứng dụng thành GraalVM Native Image. Test chạy tốt trên JVM chưa chứng minh rằng native executable có thể khởi động, đăng ký command và xử lý argument đúng.

Spring Shell 4 thay đổi đáng kể mô hình command, package, dependency và test utilities. Đồng thời, Spring Shell có hỗ trợ AOT/GraalVM, nhưng migration guide hiện vẫn ghi nhận giới hạn với cách đăng ký command bằng annotation khi biên dịch native: ở nhánh 4.0.x, cách được hỗ trợ là đăng ký command theo mô hình programmatic bằng bean kiểu **Command**. Vì vậy, hãy nâng cấp test API trước, xác nhận command chạy đúng trên JVM, rồi mới kiểm tra AOT và native binary.

## 1. Phạm vi cần kiểm tra khi nâng cấp

Nên chia việc nâng cấp thành các mục độc lập:

| Phần | Cần xác nhận |
| --- | --- |
| Nền tảng | Spring Shell 4 dùng Spring Framework 7; tích hợp Spring Boot cần Spring Boot 4 trở lên |
| Dependency | Dùng starter/module 4.x tương thích; core không tự kéo Spring Boot hoặc JLine như trước |
| Test API | Chuyển sang ShellTestClient, ShellScreen, ShellAssertions và ShellInputProvider |
| Command registration | Kiểm tra annotation model và programmatic model; dùng programmatic model nếu cần native image theo giới hạn hiện tại |
| AOT | Spring AOT xử lý được application context và các bean cần thiết |
| Native Image | GraalVM tạo được binary; runtime có đủ reachability metadata |
| Terminal | Runner và JLine provider đã chọn hoạt động trong môi trường chạy native |

Trước khi chuyển sang 4.x, migration guide khuyến nghị nâng ứng dụng lên phiên bản mới nhất của Spring Shell 3.4.x. Làm bước này trước giúp tách lỗi nâng cấp nội bộ 3.x khỏi các thay đổi lớn khi chuyển major version.

## 2. Cập nhật nền tảng và dependency

Spring Shell 4 dựa trên Spring Framework 7. Nếu ứng dụng tích hợp Spring Boot, cần dùng Spring Boot 4+. Hãy đồng bộ BOM, Spring Shell starter và các module test theo cùng dòng phiên bản.

Một thay đổi quan trọng là **spring-shell-core** không còn phụ thuộc Spring Boot hoặc JLine:

- Ứng dụng Spring Boot nên dùng một Spring Shell starter hoặc thêm **spring-shell-core-autoconfigure** tường minh.
- Nếu cần JLine, thêm **spring-shell-jline** hoặc starter tương ứng.
- Các module **spring-shell-standard** và **spring-shell-standard-commands** đã được gộp vào core.
- **spring-shell-table** đã được gộp vào JLine.
- Module auto-configuration cũ được đổi tên thành **spring-shell-core-autoconfigure**.

Với test, Spring Shell cung cấp **spring-shell-starter-test**. Khai báo dependency ở test scope và để BOM quản lý version:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án không dùng BOM, cần đặt version tương thích với Spring Shell đang chạy. Không giữ lẫn các module test 3.x và runtime 4.x trong cùng test classpath.

## 3. Các API kiểm thử mới trong Spring Shell 4

API test 4.x tập trung vào việc gửi command và kiểm tra nội dung màn hình:

| API | Vai trò |
| --- | --- |
| **ShellTestClient** | Gửi command như người dùng nhập và nhận kết quả |
| **ShellScreen** | Đại diện cho nội dung màn hình sau khi command chạy |
| **ShellAssertions** | Cung cấp assertion chuyên biệt trên ShellScreen |
| **ShellInputProvider** | Mô phỏng command có đọc input hoặc password |
| **@ShellTest** | Thiết lập Spring test context cho các shell component |

Với cách kiểm thử cơ bản, gọi **sendCommand(String)** rồi kiểm tra screen:

```java
@ShellTest
@ContextConfiguration(classes = ExampleShellApplication.class)
class ShellCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void runsCommand() throws Exception {
        ShellScreen screen = client.sendCommand("hello");

        ShellAssertions.assertThat(screen)
                .containsText("Xin chào");
    }
}
```

**ShellTestClient.sendCommand(String)** thực thi chuỗi command qua parser và registry trong test context. Nhờ vậy, test xác nhận cả tên command, cú pháp, việc bind argument/option và output. Gọi trực tiếp method Java chỉ kiểm tra logic method, không kiểm tra toàn bộ đường đi của command.

**ShellScreen** có thể được đọc qua **lines()** khi cần kiểm tra thứ tự hoặc cấu trúc dòng. Với assertion nội dung, ưu tiên **ShellAssertions.assertThat(screen).containsText(...)** thay vì so sánh toàn bộ chuỗi định dạng dễ thay đổi.

## 4. Thay thế các test API đã bị loại bỏ

Migration guide 4.x liệt kê một số test API và annotation của 3.x đã bị loại bỏ:

| API 3.x đã bị loại bỏ | Hướng chuyển đổi trong 4.x |
| --- | --- |
| **ShellWriteSequence** | Dùng ShellInputProvider để cấp các câu trả lời input/password; gửi command bằng sendCommand(...) |
| **@AutoConfigureShellTestClient** | Dùng @ShellTest để nạp test auto-configuration |
| **@AutoConfigureShell** | Dùng @ShellTest kết hợp @ContextConfiguration hoặc Spring Boot test configuration phù hợp |
| **ShellTypeExcludeFilter** | Rà soát lại cách giới hạn test context; dùng cấu hình context tường minh thay vì giữ filter cũ |
| **SpringShellTestProperties** | Chuyển các thuộc tính cần thiết sang @SpringBootTest properties, test properties hoặc cấu hình Spring phù hợp |

Không có phép thay thế một-một cho mọi session helper cũ. Hãy xem lại mục đích của từng test:

- Nếu test chỉ gửi một command và kiểm tra output, dùng **sendCommand(String)**.
- Nếu test phải trả lời prompt, dùng **sendCommand(ShellInputProvider)**.
- Nếu test cần khởi động đầy đủ ứng dụng và kiểm tra runner, dùng **@SpringBootTest**.
- Nếu test cần kiểm tra hành vi của process native, chạy binary thật và kiểm tra output cùng exit code.

Đừng giữ một lớp adapter tự viết để giả lập toàn bộ session API cũ nếu test chỉ cần gửi command. API 4.x được thiết kế để các ca kiểm thử command phổ biến có thể viết trực tiếp và ngắn gọn hơn.

## 5. Kiểm thử command không tồn tại và lỗi thực thi

Command không có trong registry được báo bằng **CommandNotFoundException**. Có thể kiểm tra riêng:

```java
@Test
void rejectsUnknownCommand() {
    assertThatThrownBy(() -> client.sendCommand("missing-command"))
            .isInstanceOf(CommandNotFoundException.class);
}
```

Với lỗi trong command, hãy kiểm tra hợp đồng exception của ứng dụng. Spring Shell 4 thay đổi mô hình xử lý lỗi và trạng thái thoát:

- Command programmatic trả về **ExitStatus**.
- Exception mặc định được truyền lên shell.
- Có thể dùng **ExitStatusExceptionMapper** để ánh xạ exception thành exit status.
- **ExitStatusExceptionMapper** thay thế vai trò của **CommandExceptionResolver** trong 3.x.

Không nên chỉ kiểm tra một chuỗi ERROR trên màn hình để suy ra command thất bại. Kiểm tra riêng thông báo hiển thị và trạng thái thoát của command/process ở tầng phù hợp.

## 6. Mô phỏng input và password

Spring Shell 4.0.2 bổ sung overload **sendCommand(ShellInputProvider)**. Provider giữ command cùng hai hàng đợi riêng cho input thông thường và password.

Ví dụ command đọc input:

```java
@Bean
Command ask() {
    return new AbstractCommand("ask", "Hỏi tên người dùng") {
        @Override
        public ExitStatus doExecute(CommandContext context) throws Exception {
            String name = context.inputReader().readInput();
            context.outputWriter().println("Bạn đã nhập: " + name);
            return ExitStatus.OK;
        }
    };
}
```

Test cung cấp câu trả lời:

```java
ShellInputProvider input = ShellInputProvider
        .providerFor("ask")
        .withInput("Ada")
        .build();

ShellScreen screen = client.sendCommand(input);

ShellAssertions.assertThat(screen)
        .containsText("Bạn đã nhập: Ada");
```

Với command đọc mật khẩu, dùng **withPassword(...)**:

```java
ShellInputProvider input = ShellInputProvider
        .providerFor("login")
        .withInput("ada")
        .withPassword("test-only-password")
        .build();

ShellScreen screen = client.sendCommand(input);
```

Dùng dữ liệu giả dành riêng cho test. Không lưu password thật trong source, log hoặc assertion. Nếu command đọc nhiều giá trị, thêm chúng theo đúng thứ tự mà command gọi input reader.

## 7. Giữ test JVM và test native ở hai mục tiêu khác nhau

Phần lớn unit test và command test nên tiếp tục chạy trên JVM. Chúng nhanh, dễ chạy trong IDE và phù hợp để kiểm tra parser, binding, validation, output, service và exception mapping.

Test trên JVM không chứng minh native binary hoạt động. Native Image sử dụng phân tích tĩnh khi build; các truy cập động như reflection, resource loading, serialization hoặc proxy cần được nhận diện và đăng ký trước. Vì vậy, quy trình native nên có thêm các bước:

1. Chạy test suite thông thường trên JVM.
2. Chạy ứng dụng với mã AOT đã sinh nhưng vẫn trên JVM.
3. Biên dịch GraalVM Native Image.
4. Khởi chạy binary và thực thi các command đại diện.
5. Kiểm tra output, exit code, resource và hành vi terminal.

Spring Boot khuyến nghị tiếp tục dùng JVM cho phần lớn test, sau đó tập trung native testing vào các khu vực có khác biệt giữa JVM và native runtime. Cách này giúp giữ thời gian phát triển hợp lý mà vẫn kiểm tra được binary trước khi phát hành.

## 8. Giới hạn native cần kiểm tra trong Spring Shell 4

Spring Shell 4 có cấu hình GraalVM riêng và dựa vào AOT của Spring Framework/Spring Boot. Tuy nhiên, migration guide v4 hiện ghi nhận một giới hạn quan trọng: **đăng ký command bằng annotation chưa được hỗ trợ cho native compilation với GraalVM; mô hình programmatic là cách được hỗ trợ ở thời điểm hướng dẫn nêu ra**.

Điều này không có nghĩa toàn bộ Spring Shell không thể chạy native. Cần phân biệt:

| Thành phần | Tình trạng và cách xử lý |
| --- | --- |
| Spring AOT và GraalVM Native Image | Có hướng dẫn build native trong Spring Shell 4 |
| Spring Shell core | Có GraalVM configuration/reachability hints |
| Command đăng ký bằng annotation | Migration guide hiện ghi nhận chưa hỗ trợ native compilation |
| Command đăng ký bằng bean **Command** | Là mô hình được khuyến nghị cho native theo migration guide |
| Dependency bên thứ ba | Có thể cần reachability metadata bổ sung |
| JLine terminal provider | Có native code riêng; cần kiểm tra provider và quyền native access của JDK |

Giới hạn này có thể thay đổi theo bản phát hành. Trước khi quyết định kiến trúc, kiểm tra lại migration guide và issue **spring-projects/spring-shell#1229** của phiên bản đang dùng. Không kết luận rằng một bản 4.x mới hơn đã sửa giới hạn chỉ vì native image build thành công.

## 9. Chuyển command annotation sang programmatic bean

Một command annotation thường có dạng:

```java
@Component
class GreetingCommands {

    @Command(name = "hello")
    public String hello() {
        return "Xin chào";
    }
}
```

Nếu ứng dụng cần GraalVM native theo giới hạn hiện tại, chuyển đăng ký command sang bean **Command**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class NativeCommandConfiguration {

    @Bean
    Command helloCommand(GreetingService greetingService) {
        return Command.builder()
                .name("hello")
                .description("Chào người dùng")
                .execute(context -> {
                    context.outputWriter().println(greetingService.greeting());
                });
    }
}
```

Spring Shell 4 tự đăng ký các bean có kiểu **Command** trong application context. Builder cho phép đặt tên, mô tả, nhóm, help, alias, option, argument, completion provider, availability provider và exception mapper.

Nếu cần chủ động trả trạng thái thoát, có thể dùng **AbstractCommand**:

```java
@Bean
Command healthCommand(HealthService healthService) {
    return new AbstractCommand("health", "Kiểm tra trạng thái ứng dụng") {
        @Override
        public ExitStatus doExecute(CommandContext context) {
            HealthResult result = healthService.check();
            context.outputWriter().println(result.message());
            return result.healthy() ? ExitStatus.OK : ExitStatus.EXECUTION_ERROR;
        }
    };
}
```

Trong ví dụ, service nghiệp vụ vẫn được inject theo cách thông thường của Spring. Chỉ cách định nghĩa và đăng ký command thay đổi; không cần đưa toàn bộ logic nghiệp vụ vào bean command.

### Giữ khả năng kiểm thử sau khi chuyển

Programmatic command vẫn có thể được kiểm thử bằng **@ShellTest** và **ShellTestClient** trên JVM:

```java
@ShellTest
@ContextConfiguration(classes = {
        ExampleShellApplication.class,
        NativeCommandConfiguration.class
})
class NativeReadyCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void executesProgrammaticCommand() throws Exception {
        ShellScreen screen = client.sendCommand("hello");
        ShellAssertions.assertThat(screen).containsText("Xin chào");
    }
}
```

Điều này giúp kiểm tra cùng một command bean trước khi chạy native build. Tuy nhiên, test client trên JVM vẫn không thay thế bước chạy native executable thật.

## 10. Cấu hình GraalVM Native Image

Spring Shell yêu cầu GraalVM được cài đặt và **JAVA_HOME** trỏ tới GraalVM phù hợp. Spring Shell khuyến nghị bật GraalVM Reachability Metadata Repository để bổ sung hint cho dependency bên thứ ba chưa cung cấp đủ metadata.

### Gradle

Thêm Native Build Tools plugin và bật metadata repository:

```groovy
plugins {
    id 'org.graalvm.buildtools.native' version '<version-phu-hop>'
}

graalvmNative {
    metadataRepository {
        enabled = true
    }
}
```

Build binary:

```bash
./gradlew nativeCompile
```

Spring Shell ghi nhận binary Gradle được tạo dưới **build/native/nativeCompile/**.

### Maven

Nếu dùng **spring-boot-starter-parent**, có thể kích hoạt profile native do Spring Boot cung cấp. Bật metadata repository cho Native Build Tools:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.graalvm.buildtools</groupId>
                <artifactId>native-maven-plugin</artifactId>
                <configuration>
                    <metadataRepository>
                        <enabled>true</enabled>
                    </metadataRepository>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Biên dịch:

```bash
./mvnw native:compile -Pnative
```

Spring Shell ghi nhận binary Maven được tạo trong **target/**. Tên file thực tế phụ thuộc artifact và cấu hình build.

Nếu không dùng Spring Boot parent, cần tự cấu hình các execution AOT và Native Build Tools tương ứng với phiên bản Spring Boot. Không sao chép version plugin cũ một cách máy móc; dùng version được quản lý tương thích với JDK, Spring Boot và GraalVM của dự án.

## 11. Kiểm tra AOT trước khi biên dịch native

Biên dịch native có thể mất nhiều thời gian. Có thể chạy ứng dụng trên JVM nhưng dùng code khởi tạo do Spring AOT sinh để phát hiện một số lỗi sớm hơn:

```bash
java -Dspring.aot.enabled=true -jar target/spring-shell-cli.jar hello
```

JAR phải chứa AOT-generated code. Với Maven, build bằng profile **native**; với Gradle, phải bật Native Image plugin để các task AOT được cấu hình.

Nếu ứng dụng khởi động được với **spring.aot.enabled=true**, độ tin cậy về AOT tăng lên. Tuy nhiên, đây vẫn là JVM process; nó chưa chứng minh native image được tạo và chạy thành công.

## 12. Native test và kiểm tra binary thực tế

Spring Boot Native Build Tools hỗ trợ chạy test bên trong native image. Với các phiên bản Spring Boot có cấu hình native test:

```bash
# Maven
./mvnw -PnativeTest test

# Gradle
./gradlew nativeTest
```

Native test thường chậm hơn test JVM vì cần tạo image chứa test engine và các test đã phát hiện. Có thể chạy trên CI theo lịch hoặc ở stage phát hành thay vì chạy sau mỗi thay đổi nhỏ. Kiểm tra tài liệu đúng minor version Spring Boot để xác nhận profile, plugin và task được hỗ trợ.

Với ứng dụng CLI, nên bổ sung smoke test chạy chính native executable:

```bash
# Thay đường dẫn bằng binary được tạo trong build/native/nativeCompile hoặc target.
./spring-shell-cli hello
status=$?
test "$status" -eq 0
```

Một process test có thể dùng **ProcessBuilder** để chạy binary, capture stdout/stderr và kiểm tra exit value:

```java
Process process = new ProcessBuilder(
        nativeBinary.toString(),
        "hello"
).redirectErrorStream(true).start();

String output = new String(
        process.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8
);
int exitCode = process.waitFor();

assertThat(exitCode).isZero();
assertThat(output).contains("Xin chào");
```

Đường dẫn **nativeBinary** nên được truyền từ cấu hình build hoặc biến môi trường của test. Không hard-code đường dẫn riêng của máy phát triển vào test source.

Kiểm tra tối thiểu:

- Ứng dụng khởi động được.
- Command chính được đăng ký và chạy.
- Argument/option được parse đúng.
- Help và version command hoạt động.
- Output có nội dung mong đợi.
- Command lỗi trả trạng thái hoặc exit code đúng hợp đồng.
- Resource, cấu hình và file cần thiết có mặt trong native image.
- Không có lỗi missing reflection/resource/proxy metadata ở runtime.

## 13. Phân biệt GraalVM Native Image và native terminal provider

Trong Spring Shell, từ **native** có thể chỉ hai việc khác nhau:

**GraalVM Native Image** biên dịch ứng dụng Java thành executable độc lập với JVM. Nó dựa vào AOT và reachability metadata, đồng thời chịu giới hạn đăng ký command bằng annotation đã nêu.

**JLine native terminal provider** dùng mã native để giao tiếp với terminal. Spring Shell cung cấp các lựa chọn provider như JANSI, JNI, JNA và FFM. Đây là lựa chọn cho terminal runtime, không phải cách biên dịch toàn bộ ứng dụng thành GraalVM binary.

| Provider | Ghi chú |
| --- | --- |
| JANSI | Hỗ trợ xử lý terminal/ANSI qua provider riêng |
| JNI | Dùng Java Native Interface |
| JNA | Dùng Java Native Access |
| FFM | Dùng Foreign Function and Memory API; Spring Shell hỗ trợ từ 3.4.x và yêu cầu JDK 22+ |

Với FFM, JLine yêu cầu bật native access:

```bash
java --enable-native-access=ALL-UNNAMED -jar spring-shell-cli.jar
```

Hoặc thêm thuộc tính vào manifest của JAR:

```text
Enable-Native-Access: ALL-UNNAMED
```

Khi dùng Gradle:

```groovy
tasks.named("bootJar") {
    manifest {
        attributes 'Enable-Native-Access': 'ALL-UNNAMED'
    }
}
```

Nếu cần shell cơ bản, **SystemShellRunner** dùng Java Console và không cần JLine. Runner này không cung cấp các tính năng nâng cao như history, tab completion và rich text formatting. Nếu cần JLine, thêm module hoặc starter tương ứng và kiểm tra native provider trên hệ điều hành mục tiêu.

## 14. Kiểm tra dependency và reachability metadata

Native Image phân tích tĩnh để xác định phần code và resource cần giữ lại. Những thành phần được truy cập động có thể không được phát hiện nếu thiếu hint:

- Reflection trên class, constructor, method hoặc field.
- Resource đọc bằng tên hoặc pattern.
- Serialization/deserialization.
- Dynamic proxy.
- JNI hoặc thư viện native.
- Dependency tải resource hoặc class theo cấu hình runtime.

Spring Shell có cấu hình GraalVM riêng, nhưng không thể tự bổ sung metadata cho mọi dependency bên thứ ba. Nếu native image build hoặc chạy thất bại:

1. Xác định class/resource bị thiếu từ lỗi native runtime.
2. Kiểm tra dependency đã có reachability metadata chưa.
3. Bật GraalVM Reachability Metadata Repository trong build.
4. Bổ sung RuntimeHints hoặc metadata riêng nếu ứng dụng cần truy cập động.
5. Tạo lại native image và chạy lại smoke test.

Không thêm hint rộng cho mọi class chỉ để build qua. Hint nên mô tả đúng phần reflection/resource/proxy mà ứng dụng thực sự sử dụng; metadata dư thừa làm binary lớn hơn và che khuất nguyên nhân thật.

## 15. Quy trình CI đề xuất

Một pipeline nâng cấp có thể chia thành các stage:

| Stage | Nội dung | Mục tiêu |
| --- | --- | --- |
| JVM tests | Unit test service, @ShellTest và test parser/output | Phát hiện lỗi nghiệp vụ và command |
| Migration checks | Kiểm tra dependency, package và API 3.x còn sót | Xác nhận chuyển đổi source/test |
| AOT-on-JVM | Chạy ứng dụng với spring.aot.enabled=true | Kiểm tra code sinh bởi AOT |
| Native compile | Build GraalVM image với metadata repository | Xác nhận build native |
| Native smoke test | Chạy binary với command và argument đại diện | Kiểm tra hành vi thực tế |
| Native test suite | Chạy nativeTest theo lịch hoặc trước release | Kiểm tra sâu trên native runtime |

Không cần chạy native image build cho mọi vòng lặp phát triển nếu thời gian build quá dài. Nhưng mỗi bản phát hành cần có bằng chứng binary đã chạy được trên OS/architecture mục tiêu.

## 16. Lỗi thường gặp khi chuyển test và native

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test không compile sau khi nâng cấp | Test API 3.x đã bị loại bỏ | Chuyển sang ShellTestClient, ShellScreen, ShellAssertions |
| Không inject được ShellTestClient | Thiếu spring-shell-starter-test hoặc @ShellTest | Thêm test starter và annotation |
| Command test chờ input | Command đọc input nhưng test chỉ gửi chuỗi | Dùng ShellInputProvider |
| Native build thành công nhưng không có command | Dùng annotation-based command registration | Chuyển command sang bean Command theo giới hạn native hiện tại |
| JVM test pass nhưng native binary lỗi reflection | Thiếu reachability metadata | Bật metadata repository và thêm RuntimeHints cần thiết |
| Resource có trên JVM nhưng thiếu trong native | Resource không được đăng ký khi AOT/native build | Khai báo resource hint |
| FFM provider báo thiếu native access | Chưa bật quyền native access | Dùng --enable-native-access=ALL-UNNAMED hoặc manifest attribute |
| JLine feature không hoạt động | Ứng dụng dùng SystemShellRunner hoặc thiếu spring-shell-jline | Chọn runner/provider và dependency phù hợp |
| Native test mất quá nhiều thời gian | Native test tạo image chứa test engine | Giữ phần lớn test trên JVM; chạy native test ở CI theo lịch/release |
| Binary chỉ chạy trên máy build | Native executable gắn với OS/architecture và thư viện hệ thống | Build/test trên môi trường tương ứng với máy đích |

## 17. Checklist hoàn tất nâng cấp

- Nâng Spring Shell 3.x lên bản mới nhất của nhánh 3.4.x trước khi chuyển major.
- Đồng bộ Spring Shell 4 với Spring Framework 7 và Spring Boot 4+.
- Cập nhật starter/module, đặc biệt core-autoconfigure, JLine và starter-test.
- Loại bỏ các test API đã bị xóa như ShellWriteSequence và @AutoConfigureShellTestClient.
- Chuyển test command sang ShellTestClient và ShellScreen.
- Dùng ShellInputProvider cho input/password; overload này có từ 4.0.2.
- Kiểm tra command output, unknown command và exception mapping trên JVM.
- Kiểm tra lại native limitation của annotation-based command registration trong migration guide/issue #1229.
- Dùng bean Command hoặc AbstractCommand nếu cần native image theo hỗ trợ hiện tại.
- Bật GraalVM Reachability Metadata Repository.
- Chạy test JVM, AOT-on-JVM và native compilation.
- Chạy native binary thật với command, argument và trường hợp lỗi đại diện.
- Phân biệt GraalVM Native Image với JLine native terminal provider.
- Kiểm tra native access nếu chọn JLine FFM trên JDK 22+.
- Chạy native smoke test trên đúng OS/architecture sẽ phân phối.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)
- [Spring Shell 4.0.3 — Building và Native Support](https://docs.spring.io/spring-shell/reference/building.html)
- [Spring Shell 4.0.3 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 — ShellTestClient API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Shell 4.0.3 — ShellInputProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/test/ShellInputProvider.html)
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Boot — Developing a Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html)
- [Spring Boot — Testing Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

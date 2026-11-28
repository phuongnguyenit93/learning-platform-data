# Kiểm tra khả năng native của đăng ký bằng annotation hoặc bằng mã

Spring Shell hỗ trợ hai cách khai báo command: dùng annotation trên method của Spring bean hoặc tạo command object bằng code rồi đăng ký thành bean. Cả hai cách đều có thể được đưa vào GraalVM Native Image khi cấu trúc ứng dụng được Spring AOT nhận biết ở thời điểm build. Điểm cần kiểm tra là command có được phát hiện trước khi đóng gói, các thao tác reflection/resource có đủ runtime hints và binary native có thực thi được cả hai loại command hay không.

Bài viết dùng Spring Shell 4.x làm mốc API. Trọng tâm là kiểm tra khả năng native của command registration, phân biệt đăng ký tĩnh với đăng ký động, xây dựng AOT/native executable, bổ sung hints khi thật sự cần và kiểm tra kết quả trên binary. API của Spring Shell 3.x có khác biệt về package và annotation; không trộn ví dụ giữa hai major version.

## 1. “Native” có hai nghĩa cần phân biệt

Trong tài liệu Spring Shell, từ native có thể xuất hiện ở hai ngữ cảnh:

| Khái niệm | Ý nghĩa | Kết quả |
|---|---|---|
| GraalVM Native Image | Spring AOT chuẩn bị application context khi build, sau đó GraalVM biên dịch thành executable theo hệ điều hành/kiến trúc đích | File thực thi chạy trực tiếp, không cần JVM riêng |
| JLine native terminal provider | JLine dùng thư viện native hoặc Foreign Function & Memory API để giao tiếp với terminal | Chọn cách truy cập terminal, không tự biến ứng dụng thành GraalVM executable |

Ví dụ, chọn starter JLine `jansi`, `jni`, `jna` hoặc `ffm` liên quan đến terminal provider. Biên dịch Spring Shell thành GraalVM Native Image là một bước đóng gói khác. Một ứng dụng có thể dùng JLine native provider nhưng vẫn chạy trên JVM; ngược lại, native executable cũng cần kiểm tra provider terminal phù hợp với môi trường triển khai.

## 2. Hai mô hình đăng ký command của Spring Shell 4

Spring Shell 4 hỗ trợ hai mô hình:

| Mô hình | Cách định nghĩa | Thành phần được Spring đăng ký |
|---|---|---|
| Annotation-based | `@Command` trên method của một Spring bean | Method command được adapter của Spring Shell phát hiện và chuyển thành command |
| Programmatic | Tạo `Command` bằng `Command.builder()` hoặc `AbstractCommand`, sau đó khai báo thành `@Bean` | Command object được đưa vào application context |

Sau khi khởi tạo context, `CommandRegistry` chứa các command được khai báo trong application context. Registry cũng có API `registerCommand()` và `unregisterCommand()` để thay đổi danh sách command khi ứng dụng đang chạy.

Trong GraalVM Native Image, điểm quan trọng là classpath và bean graph được xác định khi build. Vì vậy, command được khai báo tĩnh trong cấu hình Spring là mô hình dễ kiểm tra AOT nhất. Một registry có thể thay đổi danh sách command ở runtime, nhưng việc đó không làm cho class mới hoặc plugin JAR bên ngoài tự xuất hiện trong native executable.

## 3. Đăng ký bằng annotation

Trong Spring Shell 4.x, `@Command` đánh dấu một method là command. Class chứa method phải là Spring bean, thường được đánh dấu `@Component` và nằm trong vùng component scan.

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticCommands {

    @Command(name = "diagnostic-annotation",
            description = "Run the annotation-registered diagnostic command")
    public String annotationProbe() {
        return "ANNOTATION_COMMAND_OK";
    }
}
```

Trong ứng dụng Spring Boot dùng Spring Shell starter, auto-configuration sẽ đăng ký command target phù hợp. Class command vẫn phải được component scan tìm thấy. Nếu package chứa class bị loại khỏi component scan, method `@Command` sẽ không xuất hiện trong shell.

Với ứng dụng Spring không dùng Spring Boot auto-configuration, có thể bật các class command bằng `@EnableCommand`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.annotation.EnableCommand;

@Configuration(proxyBeanMethods = false)
@EnableCommand(DiagnosticCommands.class)
public class ShellCommandConfiguration {
}
```

Không cần thêm `@EnableCommand` chỉ để lặp lại cơ chế auto-configuration trong ứng dụng Spring Boot. Hãy chọn một cấu hình đăng ký đúng với kiểu khởi tạo ứng dụng.

### Vì sao annotation command có thể tham gia AOT?

Trong API Spring Shell 4.0.x, annotation `@Command` được gắn `@Reflective`. Spring Framework dùng metadata này để nhận biết method cần được gọi qua reflection và tạo invocation hint trong quá trình AOT. Cơ chế này hỗ trợ native image mà không cần người dùng tự viết reflection hint cho mọi method `@Command`.

Điều kiện để cơ chế đó có tác dụng:

1. Class command là Spring bean và được đưa vào application context.
2. Method có `@Command` được Spring Shell nhận diện.
3. Class không bị loại khỏi component scan hoặc cấu hình `@EnableCommand`.
4. AOT được chạy trên đúng cấu hình và profile dùng để tạo native image.

`@Reflective` không có nghĩa mọi class, method hoặc thư viện mà command sử dụng đều tự động được đưa vào native image. Reflection tùy ý, resource được nạp theo tên động hoặc proxy do ứng dụng tự tạo vẫn có thể cần hint riêng.

## 4. Đăng ký bằng code qua Command bean

Mô hình programmatic tạo một object `Command` bằng builder. Đây là một bean thông thường trong application context:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration(proxyBeanMethods = false)
public class ProgrammaticCommandConfiguration {

    @Bean
    Command programmaticProbeCommand() {
        return Command.builder()
                .name("diagnostic-programmatic")
                .description("Run the programmatically registered diagnostic command")
                .execute(context ->
                        context.outputWriter().println("PROGRAMMATIC_COMMAND_OK"));
    }
}
```

`Command.builder()` tạo command với tên, mô tả và logic thực thi. Command object được khai báo bằng `@Bean`, nên Spring AOT có thể xử lý cấu hình này cùng application context. Logic `execute` là lời gọi trực tiếp đến code đã được biên dịch; không cần reflection chỉ để gọi lambda này.

Có thể dùng `AbstractCommand` khi cần kiểm soát `ExitStatus`, help hoặc logic thực thi phức tạp hơn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.ExitStatus;

@Configuration(proxyBeanMethods = false)
public class AdvancedCommandConfiguration {

    @Bean
    AbstractCommand diagnosticStatusCommand() {
        return new AbstractCommand(
                "diagnostic-status", "Show diagnostic status") {

            @Override
            public ExitStatus doExecute(CommandContext context) {
                println("PROGRAMMATIC_STATUS_OK", context);
                return ExitStatus.OK;
            }
        };
    }
}
```

Đặt command thành bean ngay trong cấu hình Spring. Tránh tạo command trong một callback runtime không được AOT nhận biết hoặc đăng ký bean bằng `registerSingleton()` sau khi context đã khởi động. Với cấu hình phức tạp, hãy khai báo factory method/bean definition có kiểu cụ thể để AOT có thể phân tích.

## 5. CommandRegistry và giới hạn của đăng ký động

`CommandRegistry` là danh mục command mà shell sử dụng để parse, hoàn thành và thực thi lệnh. Spring Shell tự nạp các command bean từ application context. Registry cũng cung cấp:

- `getCommandByName(name)` để tìm command.
- `getCommands()` để lấy danh sách command.
- `registerCommand(command)` để thêm command object.
- `unregisterCommand(command)` để gỡ command object.

Có thể dùng đăng ký động để bật/tắt một command đã có trong binary, chẳng hạn command chỉ được mở sau khi người dùng kết nối tới một hệ thống khác. Nhưng phải phân biệt hai thao tác:

| Thao tác | Native Image |
|---|---|
| Đăng ký command bean được khai báo tĩnh trong `@Configuration` | Phù hợp với AOT |
| Đăng ký một `Command` object có implementation đã được biên dịch và tham chiếu trong ứng dụng | Có thể dùng ở runtime; cần kiểm tra đường code và test native |
| Nạp class command từ JAR plugin mới sau khi native executable đã build | Không phải mô hình native image thông thường; classpath đã cố định lúc build |
| Quét classpath tùy ý để tìm class command ở runtime | Không thể dựa vào classpath scanning runtime như JVM thông thường |
| Tạo bean bằng callback tùy ý hoặc `registerSingleton()` sau khi context chạy | Không được AOT xử lý đầy đủ như bean definition tĩnh |

GraalVM dùng giả định closed-world: code và classpath phải được biết khi build. Nếu cần plugin, hãy đóng gói các plugin đã biết vào artifact và đăng ký chúng bằng bean definition có thể được AOT xử lý; nếu cần nạp plugin thực sự từ bên ngoài sau khi triển khai, JVM thường phù hợp hơn.

### Profile và điều kiện tạo bean

Các quyết định ảnh hưởng đến việc bean nào tồn tại được thực hiện ở build-time khi AOT. `@Profile` và các điều kiện như `@ConditionalOnProperty` có giới hạn: profile/condition được dùng để tạo AOT assets phải khớp môi trường native runtime. Không dựa vào việc đổi profile lúc chạy để tạo thêm command bean chưa được đưa vào native image.

Nếu command cần thay đổi trạng thái sẵn sàng theo kết nối hoặc quyền, hãy cân nhắc `AvailabilityProvider` hoặc logic availability trên command thay vì tạo class command mới theo profile runtime.

## 6. Spring Shell cung cấp native configuration nào?

Spring Shell xây dựng native support trên Spring Framework AOT và Spring Boot Native Image. Spring Shell cung cấp GraalVM configuration/hints cho các thành phần của chính framework. Điều này giảm nhu cầu khai báo thủ công các reflection/resource hints cho phần tích hợp đã được Spring Shell hỗ trợ.

Tuy nhiên, ứng dụng có thể còn thư viện bên thứ ba hoặc logic riêng dùng:

- Reflection để gọi method/constructor theo tên.
- Resource được nạp bằng đường dẫn tạo động.
- Java serialization hoặc JSON binding mà AOT không suy ra được.
- JDK dynamic proxy hoặc JNI.
- Plugin/driver cần file cấu hình native riêng.

Spring Boot khuyến nghị dùng GraalVM Reachability Metadata Repository cho thư viện bên thứ ba chưa cung cấp đủ metadata. Native build có thể thành công nhưng một nhánh command chưa được chạy thử vẫn có thể lỗi khi thực thi do thiếu hint hoặc resource.

## 7. Cấu hình build GraalVM Native Image

Để tạo native executable, cần GraalVM distribution có Native Image compiler hoặc build bằng Cloud Native Buildpacks. Phiên bản JDK/GraalVM phải tương thích với phiên bản Spring Boot, Spring Framework, Spring Shell và Native Build Tools của dự án. Không lấy version plugin từ một bài hướng dẫn cũ rồi ghép tùy ý với dependency hiện tại.

### Maven

Nếu dùng `spring-boot-starter-parent`, parent quản lý native profile và version của Native Build Tools. Thêm plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Khi cần tải metadata cho thư viện bên thứ ba, bật Reachability Metadata Repository trong cấu hình plugin theo hướng dẫn của Spring Boot/Spring Shell version đang dùng. Sau đó build:

```bash
./mvnw -Pnative native:compile
```

Native executable được tạo trong thư mục `target`. Nếu không dùng `spring-boot-starter-parent`, phải cấu hình các bước `process-aot` và `add-reachability-metadata` tương ứng; chỉ thêm native plugin không bảo đảm Spring AOT đã chạy.

### Gradle

Áp dụng Native Build Tools plugin với version tương thích do dự án quản lý:

```groovy
plugins {
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'org.graalvm.buildtools.native' version '<native-build-tools-version>'
}

graalvmNative {
    metadataRepository {
        enabled = true
    }
}
```

Chạy:

```bash
./gradlew nativeCompile
```

Native executable được tạo trong `build/native/nativeCompile`. Spring Boot Gradle plugin cấu hình AOT tasks khi Native Image plugin được áp dụng.

### Native container image

Nếu muốn phát hành container chứa native executable, có thể dùng Cloud Native Buildpacks:

```bash
# Maven
./mvnw -Pnative spring-boot:build-image

# Gradle
./gradlew bootBuildImage
```

Buildpacks cần Docker daemon và tài nguyên build phù hợp. Binary/container native là platform-specific; build cho Linux x64 không tự tạo executable chạy trên Windows ARM64.

## 8. Kiểm tra AOT trên JVM trước khi compile native

Native Image compilation mất thời gian. Có thể kiểm tra AOT-generated initialization trên JVM trước để phát hiện lỗi bean definition hoặc code generation sớm hơn.

Với Maven, tạo AOT assets qua native profile rồi chạy JAR với `spring.aot.enabled=true`:

```bash
./mvnw -Pnative package
SPRING_SHELL_INTERACTIVE_ENABLED=false java -Dspring.aot.enabled=true -jar target/catalog-cli.jar diagnostic-annotation
SPRING_SHELL_INTERACTIVE_ENABLED=false java -Dspring.aot.enabled=true -jar target/catalog-cli.jar diagnostic-programmatic
```

Điều chỉnh tên JAR theo artifact thực tế. Spring Shell 4 mặc định bật interactive mode ngay cả khi có command-line arguments; để thực thi command được truyền từ process arguments, cần đặt `spring.shell.interactive.enabled=false`. Ví dụ trên dùng biến môi trường `SPRING_SHELL_INTERACTIVE_ENABLED=false`. Nếu command được gọi từ một REPL đang chạy, nhập tên command trực tiếp thay vì thay đổi runner mode.

Chạy ở chế độ AOT trên JVM giúp kiểm tra các bean và command đã được chuẩn bị lúc build. Nó chưa chứng minh executable native chạy được; vẫn cần build và chạy native binary.

## 9. Kiểm tra cả hai mô hình trong CommandRegistry

Trước khi build native, viết integration test xác nhận cả command annotation và command programmatic đều có trong registry:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.core.command.CommandRegistry;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class CommandRegistrationTests {

    @Autowired
    CommandRegistry commandRegistry;

    @Test
    void registersAnnotationAndProgrammaticCommands() {
        assertThat(commandRegistry.getCommandByName("diagnostic-annotation"))
                .isNotNull();
        assertThat(commandRegistry.getCommandByName("diagnostic-programmatic"))
                .isNotNull();
    }
}
```

Test này xác nhận cấu hình Spring/JVM đã đăng ký đúng command. Nó không thay thế native build. Khi test dùng profile hoặc condition, bảo đảm test dùng cùng cấu hình được chọn khi chạy AOT.

## 10. Kiểm tra native executable theo từng command

Sau khi build, chạy binary trực tiếp và kiểm tra các command đã đăng ký:

```bash
# Linux/macOS, tên executable minh họa
SPRING_SHELL_INTERACTIVE_ENABLED=false ./target/catalog-cli --help
SPRING_SHELL_INTERACTIVE_ENABLED=false ./target/catalog-cli diagnostic-annotation
SPRING_SHELL_INTERACTIVE_ENABLED=false ./target/catalog-cli diagnostic-programmatic
```

Với Gradle, executable nằm trong `build/native/nativeCompile`. Trên PowerShell, dùng đường dẫn và quoting phù hợp, ví dụ:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
& .\build\native\nativeCompile\catalog-cli.exe --help
& .\build\native\nativeCompile\catalog-cli.exe diagnostic-annotation
& .\build\native\nativeCompile\catalog-cli.exe diagnostic-programmatic
```

Ma trận kiểm tra nên có:

| Kiểm tra | Annotation command | Programmatic command |
|---|---:|---:|
| Xuất hiện trong help/list command | Có | Có |
| Lookup trong `CommandRegistry` | Có | Có |
| Chạy trên JVM thông thường | Có | Có |
| Chạy với AOT-generated code trên JVM | Có | Có |
| Chạy từ native executable | Có | Có |
| Argument/option và validation | Theo khai báo command | Theo `Command.Builder` |
| Exit status và lỗi | Đúng chính sách | Đúng chính sách |
| Availability/completion nếu có | Đã kiểm tra | Đã kiểm tra |

Đừng chỉ xác nhận binary khởi động thành công. Cần gọi từng command, thử option hợp lệ/không hợp lệ, đường lỗi và các nhánh dùng reflection/resource. Command có thể được đăng ký nhưng vẫn thất bại khi thực thi một nhánh code chưa có runtime hint.

## 11. Bổ sung RuntimeHints cho phần ứng dụng tự viết

Nếu command đọc resource theo tên động, dùng reflection tùy ý hoặc tạo proxy, đăng ký hint gần với thành phần cần nó bằng `RuntimeHintsRegistrar` và `@ImportRuntimeHints`.

Ví dụ command dùng file mẫu được đóng gói trong classpath:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class DiagnosticCommandRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("diagnostic/templates/*.txt");
    }
}
```

Đăng ký hints:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(DiagnosticCommandRuntimeHints.class)
public class DiagnosticNativeConfiguration {
}
```

Nếu thật sự cần gọi một method qua reflection, có thể đăng ký invocation hint tường minh:

```java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class PluginHandlerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
                PluginHandler.class, "handle", String.class);
        if (method != null) {
            hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
        }
    }
}
```

Chỉ đăng ký hint cho thao tác thực sự cần thiết. Hạn chế bật reflection rộng cho mọi method/constructor vì nó làm tăng bề mặt native image và che giấu việc ứng dụng đang phụ thuộc vào truy cập động.

### Kiểm thử custom hints

`RuntimeHintsPredicates` có thể xác nhận registrar đã đăng ký resource hoặc reflection hint mong muốn. Ví dụ kiểm tra resource:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class DiagnosticCommandRuntimeHintsTests {

    @Test
    void registersCommandTemplateResources() {
        RuntimeHints hints = new RuntimeHints();
        new DiagnosticCommandRuntimeHints()
                .registerHints(hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("diagnostic/templates/help.txt"))
                .accepts(hints);
    }
}
```

Test hint chỉ chứng minh registrar khai báo đúng metadata. Nó không chứng minh command đã được đăng ký trong registry hoặc native executable chạy thành công. Cần giữ riêng ba lớp kiểm tra: registration test, hints test và native executable test.

## 12. Dùng tracing agent khi thiếu hint

GraalVM Native Image tracing agent ghi nhận reflection, resource, serialization hoặc proxy usage khi chạy ứng dụng trên JVM. Có thể khởi động JAR đã AOT với agent:

```bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config \
  -jar target/catalog-cli.jar
```

Chạy lần lượt tất cả command và nhánh nghiệp vụ cần đóng gói, sau đó thoát ứng dụng để agent ghi metadata. Kiểm tra các file JSON được tạo trước khi đưa vào `src/main/resources/META-INF/native-image/`.

Agent chỉ ghi lại đường code đã chạy. Nếu chưa thử command programmatic, command annotation hoặc một nhánh lỗi, metadata sinh ra có thể thiếu thông tin cho nhánh đó. Khi chạy agent trên test suite, cần lọc các hint chỉ phục vụ test infrastructure để tránh đưa metadata không cần thiết vào artifact runtime.

## 13. Chạy native tests trong CI

Spring Boot khuyến nghị phát triển và chạy phần lớn unit/integration test trên JVM để giữ vòng lặp phản hồi nhanh. Native test có thể chạy định kỳ hoặc trong CI để xác nhận các khác biệt chỉ xuất hiện trong GraalVM.

Với Maven, nếu dự án dùng `spring-boot-starter-parent` và đã cấu hình Native Build Tools, có thể bật native test profile:

```bash
./mvnw -PnativeTest test
```

Với Gradle:

```bash
./gradlew nativeTest
```

Native tests tạo executable chứa test engine và test đã được AOT xử lý; quá trình này thường tốn thời gian và tài nguyên hơn test JVM. Chọn một nhóm integration test tập trung vào command registration, parsing, resource/hints và các đường chạy quan trọng thay vì mặc định chuyển toàn bộ test suite sang native.

## 14. Phân biệt JLine native terminal provider

Spring Shell có các starter lựa chọn JLine terminal provider như `jansi`, `jni`, `jna` và `ffm`. Những provider này liên quan đến cách terminal được truy cập. Native Image lại là cách biên dịch toàn ứng dụng thành executable.

Từ Spring Shell 3.4.x, provider `ffm` được hỗ trợ và yêu cầu JDK 22 trở lên. FFM sử dụng native access của JDK; tùy runtime, có thể cần bật native access:

```bash
java --enable-native-access=ALL-UNNAMED -jar catalog-cli.jar
```

Hoặc thêm thuộc tính manifest `Enable-Native-Access: ALL-UNNAMED` theo cách build của dự án. Cấu hình này không thay thế AOT, runtime hints hoặc native image compilation. Khi phát hành binary native, kiểm tra provider JLine trên từng OS/architecture mục tiêu.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Annotation command không xuất hiện trong help | Class không phải Spring bean hoặc bị loại khỏi component scan | Kiểm tra `@Component`, package scan và `@EnableCommand` nếu không dùng Boot |
| Programmatic command không xuất hiện | `Command` object không được khai báo thành bean hoặc config không được nạp | Khai báo `@Bean Command` trong `@Configuration` được scan/import |
| JVM chạy được nhưng native image không tìm thấy command | Cấu hình bean/target chỉ được tạo động lúc runtime | Đưa command vào cấu hình tĩnh được AOT xử lý |
| Command có trong registry nhưng chạy lỗi reflection | Thiếu invocation/runtime hint cho code tùy chỉnh | Dùng `RuntimeHintsRegistrar`, `@Reflective` phù hợp hoặc tracing agent |
| Resource có trên JVM nhưng thiếu trong native image | Resource được tạo tên động hoặc chưa đăng ký | Đăng ký resource pattern và kiểm tra file trong artifact |
| Plugin JAR không được nạp trong native image | Native image có classpath cố định | Đóng gói plugin đã biết khi build hoặc chọn JVM nếu cần nạp plugin động |
| Thay profile khi chạy nhưng command không xuất hiện | Bean graph đã được chọn trong AOT build | Build riêng cho profile cần phát hành hoặc dùng availability runtime |
| Build native thất bại ở thư viện thứ ba | Thiếu reachability metadata hoặc thư viện chưa hỗ trợ | Bật metadata repository, kiểm tra version và cung cấp hints cần thiết |
| Build thành công nhưng command chưa được kiểm tra | Chỉ thử startup hoặc help | Chạy từng command trên binary, kiểm tra option, error path và resource |
| Native executable chạy trên máy build nhưng không chạy trên máy khác | Khác OS, CPU architecture hoặc system library | Build/test theo target platform và kiểm tra dependency native |
| Nghĩ FFM/JNI đồng nghĩa GraalVM native | Nhầm terminal provider với native image | Kiểm tra riêng JLine provider và quy trình AOT/GraalVM |

## 16. Checklist kiểm tra native command registration

- [ ] Đã xác định đúng Spring Shell major version và dùng đúng package/API.
- [ ] Annotation command là method trên Spring bean được phát hiện lúc build.
- [ ] Nếu không dùng Spring Boot, đã cấu hình `@EnableCommand` cho target class.
- [ ] Programmatic command được khai báo thành `@Bean Command` trong cấu hình Spring tĩnh.
- [ ] Đã xác nhận cả hai command có trong `CommandRegistry` trên JVM.
- [ ] Không dựa vào runtime classpath scan hoặc nạp plugin JAR mới.
- [ ] Đã kiểm tra profile/condition được chọn khi chạy AOT.
- [ ] Đã bật Spring AOT và Native Build Tools phù hợp với dependency version.
- [ ] Đã bật Reachability Metadata Repository nếu cần cho thư viện bên thứ ba.
- [ ] Đã kiểm tra custom reflection, resource, serialization và proxy hints.
- [ ] Đã test custom `RuntimeHintsRegistrar` bằng `RuntimeHintsPredicates`.
- [ ] Đã chạy JVM với `spring.aot.enabled=true`.
- [ ] Đã build và chạy native executable.
- [ ] Đã gọi từng command annotation/programmatic và kiểm tra option/error path.
- [ ] Đã chạy native tests hoặc một nhóm native smoke tests trong CI.
- [ ] Đã xác minh JLine terminal provider trên OS/architecture mục tiêu.

## Tài liệu tham khảo

1. [Spring Shell 4 – Building](https://docs.spring.io/spring-shell/reference/building.html) – Native Support, Spring Shell GraalVM configuration, Reachability Metadata Repository và native build.
2. [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – annotation-based, programmatic registration và `CommandRegistry`.
3. [Spring Shell 4 – `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) – annotation đánh dấu command method và metadata reflection.
4. [Spring Shell 4 – `Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html) và [`CommandRegistry` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html) – command object và đăng ký/gỡ command runtime.
5. [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html) – closed-world, AOT và các loại runtime hints.
6. [Spring Boot – Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html) – tracing agent, `RuntimeHintsRegistrar`, JSON hints và kiểm thử hints.
7. [Spring Boot – Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html) – AOT trên JVM, native tests Maven/Gradle.
8. [Spring Framework – Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) – `@Reflective`, fixed classpath, bean definitions và runtime hints.

Khả năng native của đăng ký command phụ thuộc vào việc Spring AOT có nhìn thấy command target và cấu hình bean ngay lúc build hay không. Cả annotation-based và programmatic `Command` bean đều có thể được kiểm tra trong native image khi được khai báo tĩnh và các runtime hints cần thiết đã có. Hãy xác nhận command trong registry, chạy AOT trên JVM, build native executable và thực thi riêng từng command trên binary phát hành.

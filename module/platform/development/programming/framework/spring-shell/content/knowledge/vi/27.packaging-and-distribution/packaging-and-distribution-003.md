# Phân biệt tham số JVM với tham số của ứng dụng hoặc command

Khi chạy một Spring Shell executable JAR, một dòng lệnh có thể chứa nhiều loại tham số: tùy chọn dành cho Java launcher, system property của JVM, cấu hình Spring Boot và đối số của command Spring Shell. Các loại này có cú pháp khá giống nhau nhưng được đọc ở những thời điểm và bởi những thành phần khác nhau.

Nếu đặt `-Xmx` sau tên JAR, JVM không nhận đó là cấu hình heap. Nếu đặt `--spring.profiles.active=staging` trong command line, Spring Boot có thể dùng nó làm property của `Environment`. Nếu truyền `--project-id=orders`, Spring Shell có thể hiểu đó là option của command đang chạy. Muốn đóng gói và vận hành CLI đúng cách, cần biết chính xác tham số nào thuộc lớp nào.

## 1. Ba lớp tham số trong một lệnh chạy

Một lệnh chạy JAR thường có dạng:

```bash
java [JVM_OPTIONS] -jar app.jar [APPLICATION_ARGS]
```

Các thành phần:

| Thành phần | Ví dụ | Ai xử lý? |
| --- | --- | --- |
| Java launcher options | `-Xms256m`, `-Xmx1g`, `--add-opens` | Java launcher và JVM |
| JVM system properties | `-Duser.timezone=UTC` | JVM; ứng dụng đọc qua `System.getProperty` hoặc Spring Environment |
| Application arguments | `--spring.profiles.active=staging`, `deploy` | `main(String[])`, Spring Boot và Spring Shell |
| Command arguments/options | `deploy --project-id=orders --dry-run` | Spring Shell command parser và command method |

Ranh giới quan trọng nằm ở `-jar app.jar`. Các tùy chọn JVM phải nằm trước `-jar`; các token sau tên JAR được truyền vào `main(String[])` của ứng dụng. Quy tắc này do Java launcher quy định. <Link url="https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html" title="The java Command — Java 17"/>.

## 2. Đọc một lệnh từ trái sang phải

Xét ví dụ dùng biến môi trường để chọn profile:

```bash
SPRING_PROFILES_ACTIVE=staging java -Xms256m -Xmx1g -Duser.timezone=UTC -jar spring-shell-app.jar deploy --project-id=orders --dry-run
```

Diễn giải:

1. `java`: khởi chạy Java launcher.
2. `-Xms256m`: heap ban đầu của JVM.
3. `-Xmx1g`: giới hạn heap tối đa.
4. `-Duser.timezone=UTC`: tạo system property cho JVM.
5. `-jar spring-shell-app.jar`: chạy ứng dụng trong JAR.
6. `SPRING_PROFILES_ACTIVE=staging`: biến môi trường được Spring Boot bind thành property.
7. `deploy`: tên command mà Spring Shell thực thi trong chế độ non-interactive.
8. `--project-id=orders --dry-run`: các option được command parser xử lý.

Các đối số sau JAR đều thuộc `String[] args` mà `main` nhận. Spring Boot và Spring Shell có thể cùng phân tích tập đối số này cho mục đích riêng. Vì vậy, không nên suy luận rằng một token sau JAR chỉ được một framework nhìn thấy.

## 3. Tham số dành cho Java launcher và JVM

Tùy chọn JVM điều khiển cách tiến trình Java khởi chạy và vận hành. Một số tùy chọn thường gặp:

| Tùy chọn | Tác dụng | Ví dụ |
| --- | --- | --- |
| `-Xms` | Heap ban đầu | `-Xms256m` |
| `-Xmx` | Heap tối đa | `-Xmx1g` |
| `-Dname=value` | Tạo system property | `-Duser.timezone=UTC` |
| `-ea` | Bật Java assertions | `-ea` |
| `--add-opens` | Mở package cho reflection theo module system | `--add-opens=java.base/java.lang=ALL-UNNAMED` |
| `-XX:...` | Tùy chọn nâng cao của HotSpot JVM | `-XX:+UseG1GC` |

Các tùy chọn này đặt trước `-jar`:

```bash
java -Xmx1g -Duser.timezone=UTC -jar app.jar
```

Nếu đặt sau tên JAR:

```bash
java -jar app.jar -Xmx1g -Duser.timezone=UTC
```

thì `-Xmx1g` và `-Duser.timezone=UTC` trở thành application arguments. JVM đã khởi chạy trước đó và không quay lại áp dụng chúng. Nếu Spring Shell không có command hoặc option tương ứng, các token này có thể khiến command thất bại vì cú pháp không hợp lệ.

## 4. System property -D và Spring Boot property --

Hai cách sau có thể cùng thiết lập một thuộc tính Spring:

```bash
java -Dspring.profiles.active=staging -jar app.jar
```

```bash
java -jar app.jar --spring.profiles.active=staging
```

Nhưng nguồn property khác nhau:

- `-Dspring.profiles.active=staging` tạo Java system property trước khi ứng dụng chạy.
- `--spring.profiles.active=staging` là application argument. Mặc định Spring Boot chuyển các option argument bắt đầu bằng `--` thành property trong `Environment`.

Command-line properties của Spring Boot có độ ưu tiên cao hơn system properties và file cấu hình. Vì vậy, nếu cùng một key được đặt ở nhiều nguồn, giá trị từ command line có thể ghi đè giá trị từ file hoặc `-D`. <Link url="https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html" title="Externalized Configuration — Spring Boot 3.4"/>.

Không nên nhầm `-D` với `--`. Một bên là cú pháp của Java launcher; bên kia là quy ước application property mà Spring Boot nhận diện.

Khi chạy command non-interactive, hãy lưu ý application arguments sau JAR cũng là đầu vào của Spring Shell. Nếu đưa `--spring.profiles.active=staging` vào cùng danh sách token với command, token đó vừa là Boot property vừa có thể đi vào quá trình dựng command line. Để lệnh dễ dự đoán, nên chọn profile bằng biến môi trường hoặc system property `-D` trước JAR; chỉ dùng Boot command-line property sau JAR khi đã xác nhận runner và cách phân tách arguments của ứng dụng.

## 5. ApplicationArguments của Spring Boot

Spring Boot cung cấp bean `ApplicationArguments` để đọc các đối số truyền vào `SpringApplication.run(...)`. Interface này phân biệt:

| API | Giá trị |
| --- | --- |
| `getSourceArgs()` | Mảng đối số thô ban đầu |
| `getOptionNames()` | Tên các option dạng `--key` hoặc `--key=value` |
| `containsOption(name)` | Kiểm tra option có xuất hiện |
| `getOptionValues(name)` | Lấy danh sách giá trị của option |
| `getNonOptionArgs()` | Các đối số không có dạng option |

Ví dụ:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Component;

@Component
public class StartupArgumentInspector {

    public StartupArgumentInspector(ApplicationArguments arguments) {
        System.out.println("Raw: "
                + String.join(" ", arguments.getSourceArgs()));
        System.out.println("Profile option: "
                + arguments.getOptionValues("spring.profiles.active"));
        System.out.println("Non-option args: "
                + arguments.getNonOptionArgs());
    }
}
```

Với lệnh:

```bash
java -jar app.jar --spring.profiles.active=staging deploy
```

Spring Boot có thể đọc `spring.profiles.active` từ option argument và `deploy` từ non-option arguments. `ApplicationArguments` hữu ích khi ứng dụng cần kiểm tra tham số khởi động hoặc viết `ApplicationRunner`/`CommandLineRunner`. Nó không thay thế command parser của Spring Shell. <Link url="https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/ApplicationArguments.html" title="ApplicationArguments API — Spring Boot 3.4"/>.

## 6. Tham số của command Spring Shell

Spring Shell có hai cách vận hành chính:

- **Non-interactive:** nhận command và các option từ application arguments, chạy command rồi kết thúc.
- **Interactive:** mở shell để người dùng nhập nhiều command trong một phiên.

Trong Spring Shell 3.4, `ShellApplicationRunner` nhận `ApplicationArguments` của Spring Boot rồi lựa chọn `ShellRunner` phù hợp. `NonInteractiveShellRunner` chuyển application arguments thành command line để thực thi. Từ nhánh 3.3, chỉ `NonInteractiveShellRunner` được bật mặc định; các runner interactive và script có thể bật bằng property tương ứng. <Link url="https://docs.spring.io/spring-shell/reference/3.4/execution.html" title="Execution — Spring Shell 3.4.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/NonInteractiveShellRunner.html" title="NonInteractiveShellRunner API — Spring Shell 3.4"/>.

Ví dụ command:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class DeploymentCommands {

    @ShellMethod(key = "deploy", value = "Triển khai một project")
    public String deploy(
            @ShellOption(value = "--project-id") String projectId,
            @ShellOption(value = "--dry-run", defaultValue = "false") boolean dryRun) {

        if (dryRun) {
            return "Chạy thử triển khai project " + projectId;
        }
        return "Đã gửi yêu cầu triển khai project " + projectId;
    }
}
```

Gọi command:

```bash
java -jar app.jar deploy --project-id=orders --dry-run
```

`deploy` là tên command. `--project-id` và `--dry-run` là option thuộc command. Chúng nằm sau JAR vì command là một phần của application arguments.

## 7. Một token --... có thể được nhiều lớp phân tích

Spring Boot mặc định xem option application argument bắt đầu bằng `--` là command-line property. Spring Shell cũng dùng tiền tố `--` cho option của command. Vì vậy, một token sau JAR có thể vừa xuất hiện trong `ApplicationArguments`/`Environment`, vừa được Spring Shell chuyển đến command parser.

Ví dụ:

```bash
java -jar app.jar deploy --project-id=orders
```

Boot có thể tạo property `project-id=orders`; Spring Shell có thể dùng token đó để bind tham số `projectId` của command `deploy`. Điều này không có nghĩa hai framework dùng chung một parser hoặc cùng một hợp đồng.

Để tránh xung đột:

- Dành namespace `spring.*`, `logging.*` và các key cấu hình cho Spring Boot.
- Dùng tên option riêng theo nghiệp vụ, chẳng hạn `--project-id`, `--dry-run`, `--output-file`.
- Tránh đặt tên command option trùng với property cấu hình mà ứng dụng đọc từ `Environment`.
- Kiểm tra `ApplicationArguments` và test command thực tế khi thay đổi tên option.
- Nếu không muốn Spring Boot thêm command-line properties vào `Environment`, có thể gọi `SpringApplication.setAddCommandLineProperties(false)`; nhưng hãy đánh giá ảnh hưởng tới toàn bộ cấu hình khởi động trước khi tắt.

## 8. Không nhầm application property với option của command

Giả sử ứng dụng có property:

```yaml
deployment:
  default-project: orders
```

Và command có option:

```text
deploy --project-id=payments
```

Hai giá trị có mục đích khác nhau:

- `deployment.default-project` là cấu hình ứng dụng, được bind vào bean hoặc đọc qua `Environment`.
- `--project-id=payments` là dữ liệu người dùng gửi cho lần gọi command.

Command có thể dùng option làm giá trị ưu tiên cho lần chạy hiện tại, hoặc dùng cấu hình mặc định khi option không được truyền. Hãy thể hiện quy tắc đó rõ trong code:

```java
@ShellMethod(key = "deploy")
public String deploy(
        @ShellOption(value = "--project-id", defaultValue = ShellOption.NULL)
        String projectId) {

    String effectiveProjectId =
            projectId != null ? projectId : targetProperties.defaultProject();
    return deploymentService.deploy(effectiveProjectId);
}
```

Ví dụ trên minh họa việc command tự chọn cấu hình mặc định khi option vắng mặt. Kiểm tra API `@ShellOption` của phiên bản Spring Shell đang sử dụng nếu muốn dùng một sentinel như `ShellOption.NULL`; có thể thay bằng default rõ ràng hoặc một lớp wrapper để biểu diễn giá trị chưa được truyền.

## 9. Truyền tham số trong Maven spring-boot:run

Khi phát triển, `mvn spring-boot:run` chạy ứng dụng qua Maven plugin. Plugin tách riêng tham số JVM và tham số của ứng dụng:

| Thuộc tính plugin | Dùng cho |
| --- | --- |
| `jvmArguments` | Tùy chọn JVM, ví dụ `-Xmx512m`, `-D...` |
| `arguments` | Mảng đối số truyền cho ứng dụng |
| `commandlineArguments` | Chuỗi đối số ứng dụng; khi có sẽ ưu tiên hơn `arguments` |
| `profiles` | Shortcut để chọn Spring profile |
| `environmentVariables` | Biến môi trường của tiến trình fork |

Ví dụ cấu hình trong `pom.xml`:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <jvmArguments>
            -Xmx512m -Duser.timezone=UTC
        </jvmArguments>
        <arguments>
            <argument>deploy</argument>
            <argument>--project-id=orders</argument>
            <argument>--dry-run</argument>
        </arguments>
    </configuration>
</plugin>
```

Hoặc truyền user properties khi chạy:

```bash
mvn spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Duser.timezone=UTC" -Dspring-boot.run.arguments="deploy --project-id=orders --dry-run"
```

Các `-Dspring-boot.run...` trong lệnh trên là Maven user properties để cấu hình plugin. Chúng không đồng nghĩa với việc ứng dụng nhận một system property có cùng tên. Plugin chạy ứng dụng trong tiến trình fork và có tham số riêng cho JVM với application arguments. <Link url="https://docs.spring.io/spring-boot/3.4/maven-plugin/run.html" title="Running your Application with Maven — Spring Boot 3.4"/>.

## 10. Truyền tham số trong Gradle bootRun

Gradle Spring Boot plugin cũng phân biệt application arguments và JVM arguments.

Có thể cấu hình task:

```groovy
tasks.named("bootRun") {
    jvmArgs = ["-Xmx512m", "-Duser.timezone=UTC"]
    args = ["deploy", "--project-id=orders", "--dry-run"]
}
```

Sau đó chạy:

```bash
./gradlew bootRun
```

Hoặc chỉ truyền application arguments trên command line:

```bash
./gradlew bootRun --args="deploy --project-id=orders --dry-run"
```

`--args` là option của Gradle task `bootRun`, không phải JVM option. Để truyền JVM option, cấu hình `jvmArgs` trong task hoặc dùng cấu hình run phù hợp của Gradle. Không đặt `-Xmx` vào `--args` vì khi đó nó được chuyển vào `main(String[])` của ứng dụng.

## 11. Dùng biến môi trường cho tùy chọn JVM

Khi triển khai trên máy chủ hoặc container, có thể cần cung cấp JVM options mà không sửa lệnh khởi chạy. Java hỗ trợ biến môi trường launcher `JDK_JAVA_OPTIONS`; nội dung của biến được thêm vào command line của Java launcher.

Ví dụ Linux/macOS:

```bash
export JDK_JAVA_OPTIONS="-Xmx1g -Duser.timezone=UTC"
java -jar app.jar deploy --project-id=orders
```

`JAVA_TOOL_OPTIONS` cũng được JVM nhận diện để thêm tùy chọn khi tạo VM. Hai biến có phạm vi và thời điểm xử lý khác nhau; chọn một cơ chế theo chuẩn vận hành của tổ chức và tránh đặt cùng một flag ở nhiều nơi khiến khó truy vết.

Các biến cấu hình ứng dụng như `SPRING_PROFILES_ACTIVE` lại là biến môi trường mà Spring Boot bind vào `Environment`:

```bash
export SPRING_PROFILES_ACTIVE=staging
java -Xmx1g -jar app.jar deploy --project-id=orders
```

Không dùng `JDK_JAVA_OPTIONS` để truyền tên command hoặc option nghiệp vụ. Không dùng `SPRING_PROFILES_ACTIVE` để thay đổi heap JVM.

## 12. Truyền tham số trong Docker

Với Docker image, `ENTRYPOINT` thường cố định Java launcher và JAR; `CMD` cung cấp application arguments mặc định:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["deploy", "--project-id=orders", "--dry-run"]
```

Khi chạy container:

```bash
docker run --rm my-cli
```

Docker truyền các phần tử `CMD` vào sau `ENTRYPOINT`, vì vậy chúng trở thành application arguments. Có thể thay command mặc định:

```bash
docker run --rm my-cli deploy --project-id=payments
```

Nếu cần JVM option, hãy đặt chúng trong `ENTRYPOINT` hoặc dùng wrapper script/biến môi trường JVM được chuẩn hóa. Không nối `-Xmx` vào cuối lệnh `docker run` vì nó sẽ trở thành application argument.

## 13. Trích dẫn và khoảng trắng trong tham số

Một giá trị có khoảng trắng phải được shell truyền thành một argument duy nhất. Ví dụ:

Linux/macOS:

```bash
java -jar app.jar project create --name "Order Service"
```

PowerShell:

```powershell
java -jar app.jar project create --name "Order Service"
```

Trong Java, command method sẽ nhận một giá trị `Order Service` nếu parser và shell quoting được cấu hình đúng. Nếu bỏ dấu nháy, shell có thể truyền `Order` và `Service` thành hai token khác nhau.

Đừng nhầm dấu nháy của terminal với cú pháp Spring Shell. Shell hệ điều hành xử lý việc gom token trước khi Java nhận `String[] args`; sau đó Spring Shell áp dụng parser của nó. Khi có script trung gian, cần kiểm tra cả cách script quote và cách command parser hiểu token.

## 14. Tham số dạng file và argument file của Java

Java launcher hỗ trợ argument file bằng ký hiệu `@filename`. File chứa các tùy chọn launcher và có thể giúp tránh lệnh quá dài:

```text
# jvm.args
-Xmx1g
-Duser.timezone=UTC
-ea
```

Chạy:

```bash
java @jvm.args -jar app.jar deploy --project-id=orders
```

Argument file này được Java launcher đọc trước khi chạy ứng dụng. Nó phù hợp với JVM options. Nếu cần lưu application arguments hoặc command Spring Shell, hãy dùng file script riêng của ứng dụng hoặc cơ chế script runner của Spring Shell; không đặt chúng vào JVM argument file với kỳ vọng Java sẽ chuyển chúng thành tham số command.

## 15. Script runner và command line của Spring Shell

Spring Shell 3.4 có `NonInteractiveShellRunner`, `InteractiveShellRunner` và `ScriptShellRunner`. Tài liệu 3.4.3 nêu rằng từ 3.3.x chỉ non-interactive runner được bật mặc định; interactive và script runner cần được bật theo cấu hình:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true
```

`NonInteractiveShellRunner` có `setCommandsFromArgs(...)` để chuyển application arguments thành một hoặc nhiều command line. API nhận raw `String[]` và tạo danh sách command, ví dụ `history --file myHistory.txt`. Đây là cơ chế của Spring Shell, khác với việc Spring Boot thêm `--key=value` vào `Environment`.

`ScriptShellRunner` tìm các application argument bắt đầu bằng ký tự `@` và xem phần theo sau là đường dẫn file script cần chạy. Ví dụ, khi script runner được bật:

```bash
java -jar app.jar @deploy.commands
```

Đây là quy ước của Spring Shell sau JAR. Nó khác Java launcher argument file `@jvm.args` đặt trước `-jar`; vị trí token quyết định thành phần nào đọc file. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html" title="ScriptShellRunner API — Spring Shell 3.4.3"/>.

Khi phân phối CLI, hãy quyết định rõ:

- Chạy một command rồi thoát: non-interactive.
- Mở prompt để người dùng chạy nhiều command: interactive.
- Chạy chuỗi lệnh từ file: script runner.

Đừng bật đồng thời các runner mà không hiểu thứ tự và điều kiện lựa chọn của chúng. Kiểm tra `spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled` theo đúng cấu hình phiên bản đang dùng.

## 16. Kiểm tra tham số thực tế mà ứng dụng nhận

Khi lệnh chạy sai, hãy xác định tham số bị xử lý ở tầng nào. Có thể tạm thời ghi log an toàn từ `ApplicationArguments`:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Component;

@Component
public class ArgumentDiagnostics {

    public ArgumentDiagnostics(ApplicationArguments arguments) {
        System.out.println("Source argument count: "
                + arguments.getSourceArgs().length);
        System.out.println("Option names: "
                + arguments.getOptionNames());
        System.out.println("Non-option arguments: "
                + arguments.getNonOptionArgs());
    }
}
```

Không log token, password hoặc secret nếu command nhận chúng qua option. Khi cần chẩn đoán JVM, dùng `jcmd <pid> VM.command_line` hoặc công cụ giám sát phù hợp; giới hạn quyền truy cập vì command line có thể chứa thông tin nhạy cảm.

Sau khi xác nhận tham số đến được ứng dụng, kiểm tra tiếp command registration, tên option, kiểu dữ liệu và quy tắc quoting của shell hệ điều hành.

## 17. Bảng so sánh nhanh

| Nhu cầu | Cách truyền | Vị trí |
| --- | --- | --- |
| Tăng heap tối đa | `-Xmx1g` | Trước `-jar` |
| Đặt Java system property | `-Duser.timezone=UTC` | Trước `-jar` |
| Mở package Java module | `--add-opens=...` | Trước `-jar` |
| Chọn Spring profile | `SPRING_PROFILES_ACTIVE=staging` hoặc `-Dspring.profiles.active=staging` | Môi trường hoặc trước `-jar` |
| Chọn cấu hình một lần chạy | `SPRING_CONFIG_LOCATION=...` hoặc `-Dspring.config.location=...` | Môi trường hoặc trước `-jar` |
| Gọi command | `deploy` | Sau JAR |
| Truyền option command | `--project-id=orders` | Sau tên command |
| Truyền chuỗi có khoảng trắng | `"Order Service"` | Sau JAR, quote theo shell |
| Truyền JVM args khi dùng Maven | `spring-boot.run.jvmArguments` | Maven plugin property |
| Truyền app args khi dùng Maven | `spring-boot.run.arguments` | Maven plugin property |
| Truyền app args khi dùng Gradle | `bootRun --args="..."` | Gradle task option |
| Chạy file lệnh Spring Shell 3.4 | `@deploy.commands` | Sau JAR, khi script runner được bật |
| Dùng Java launcher argument file | `@jvm.args` | Trước `-jar` |

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Heap không tăng dù đã truyền `-Xmx` | Đặt `-Xmx` sau tên JAR | Chuyển `-Xmx` về trước `-jar` |
| `-Dfoo=bar` không xuất hiện trong System properties | Đặt `-D` sau tên JAR | Đặt `-D` trước `-jar` hoặc dùng property phù hợp của Spring Boot |
| Spring profile không được kích hoạt | Dùng nhầm `-D` sau JAR hoặc sai tên property | Dùng `-Dspring.profiles.active=...` trước JAR hoặc `--spring.profiles.active=...` sau JAR |
| Command không được tìm thấy | Application arguments không được runner chuyển thành command | Kiểm tra runner và cú pháp command |
| Command option bị hiểu như cấu hình Boot | Dùng tên option trùng với property ứng dụng | Đặt namespace command rõ ràng và kiểm tra `Environment` |
| Maven chạy được nhưng JAR không chạy | Tham số đặt trong cấu hình plugin mà chưa chuyển sang cách chạy JAR | So sánh `jvmArguments` với `arguments` và vị trí sau `-jar` |
| Gradle không áp dụng heap option | Đưa `-Xmx` vào `--args` | Cấu hình `jvmArgs` cho `bootRun` |
| Giá trị có dấu cách bị tách | Quote sai ở shell hoặc script wrapper | Quote giá trị thành một token duy nhất |
| Script runner không hoạt động | Chưa bật `spring.shell.script.enabled` | Kiểm tra cấu hình runner của Spring Shell 3.4 |

## 19. Bài thực hành tổng hợp

Đóng gói một CLI có command `deploy` và kiểm tra từng lớp tham số:

1. Tạo executable JAR Spring Boot chứa Spring Shell 3.4.3.
2. Tạo command `deploy` nhận `--project-id`, `--dry-run` và một giá trị có thể chứa khoảng trắng.
3. Chạy JAR với `-Xmx512m` và `-Duser.timezone=UTC` trước `-jar`.
4. Chọn profile bằng biến môi trường `SPRING_PROFILES_ACTIVE=staging` hoặc `-Dspring.profiles.active=staging` trước tên JAR.
5. Gọi command `deploy --project-id=orders --dry-run`.
6. Inject `ApplicationArguments` và quan sát `getSourceArgs`, `getOptionNames`, `getNonOptionArgs`.
7. Thử đặt `-Xmx` sau JAR và giải thích vì sao JVM không áp dụng.
8. Chạy cùng lệnh qua `mvn spring-boot:run`, tách `jvmArguments` và `arguments`.
9. Chạy qua `./gradlew bootRun --args=...`, cấu hình JVM args riêng.
10. Tạo Docker image có `ENTRYPOINT` Java và `CMD` command mặc định; thử override command khi `docker run`.
11. Viết test process để xác nhận command nhận đúng option và trả mã thoát mong đợi.
12. Bật script runner, chạy file lệnh bằng `@deploy.commands` và phân biệt nó với Java launcher argument file `@jvm.args`.

## 20. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Java launcher | Xác định đúng ranh giới `-jar` và vị trí JVM options |
| JVM properties | Phân biệt `-D` với application properties |
| Spring Boot | Hiểu `ApplicationArguments` và command-line property source |
| Spring Shell | Hiểu non-interactive, interactive và script runner |
| Command parsing | Truyền đúng command name, argument và option |
| Build tools | Phân biệt Maven `jvmArguments`/`arguments` và Gradle `jvmArgs`/`--args` |
| Container | Hiểu `ENTRYPOINT`, `CMD` và application arguments |
| Quoting | Truyền đúng giá trị có khoảng trắng |
| Diagnostics | Kiểm tra được raw args, option names và non-option args |
| Distribution | Tạo lệnh khởi chạy rõ ràng, có thể lặp lại và dễ vận hành |

## Tài liệu tham khảo

- [Java 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Spring Boot 3.4 — Externalized Configuration](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html)
- [Spring Boot 3.4 — Application Arguments](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html)
- [Spring Boot 3.4 — Running with Maven](https://docs.spring.io/spring-boot/3.4/maven-plugin/run.html)
- [Spring Boot 3.4 — Running with Gradle](https://docs.spring.io/spring-boot/3.4/gradle-plugin/running.html)
- [Spring Shell 3.4.3 — Execution](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Shell 3.4.3 — NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/NonInteractiveShellRunner.html)

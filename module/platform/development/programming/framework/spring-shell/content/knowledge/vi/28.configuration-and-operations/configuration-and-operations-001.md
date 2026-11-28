# Tổ chức thuộc tính Spring Shell trong cấu hình ứng dụng

Một ứng dụng Spring Shell có nhiều loại cấu hình: chế độ chạy interactive hay non-interactive, xử lý script, lịch sử lệnh, help, theme và các tùy chọn nghiệp vụ như thư mục export, giới hạn bản ghi hoặc thời gian chờ. Nếu rải các giá trị này trong code, biến môi trường và nhiều file không có quy ước, ứng dụng sẽ khó triển khai và khó chẩn đoán khi chạy ở môi trường khác nhau.

Spring Shell 3.x sử dụng cơ chế externalized configuration của Spring Boot. Các thuộc tính riêng của shell nằm dưới prefix `spring.shell`; thuộc tính do ứng dụng định nghĩa nên có prefix riêng như `app.export` hoặc `inventory.cli`. Spring Boot đọc cấu hình từ YAML, properties, environment variable, system property và command-line argument, sau đó bind vào bean hoặc cho phép truy cập qua `Environment`.

Bài này tập trung vào cách tổ chức thuộc tính theo nhóm chức năng, chọn nguồn cấu hình phù hợp và kiểm tra giá trị trước khi command sử dụng. Một điểm cần chú ý khi làm việc với Spring Shell 3.3 là chỉ `NonInteractiveShellRunner` được bật mặc định; muốn mở REPL hoặc chạy script phải cấu hình runner tương ứng.

Sau bài này, bạn có thể:

- Nhận biết các nhóm thuộc tính phổ biến dưới `spring.shell`.
- Tổ chức `application.yaml` theo nhóm shell và nhóm nghiệp vụ.
- Phân biệt cấu hình Spring Shell với cấu hình nạp file của Spring Boot.
- Dùng profile để tách cấu hình development, test và production.
- Ghi đè thuộc tính bằng environment variable và command-line argument.
- Bind cấu hình nghiệp vụ vào object có kiểu bằng `@ConfigurationProperties`.
- Xác thực cấu hình ngay khi khởi động và cung cấp giá trị mặc định hợp lý.
- Quản lý history, đường dẫn cấu hình và secret an toàn.
- Kiểm tra cấu hình thực tế khi ứng dụng chạy sai môi trường.

> Ví dụ dùng Spring Shell 3.3.x và Spring Boot 3.3.x. Các tên thuộc tính Spring Shell được minh họa theo `SpringShellProperties` của Spring Shell 3.3.0 và tài liệu tham chiếu 3.3.4.

## 1. Hai nhóm thuộc tính: shell và nghiệp vụ

Hãy chia cấu hình thành hai nhóm:

| Nhóm | Prefix ví dụ | Nội dung |
|---|---|---|
| Spring Shell | `spring.shell` | Runner, history, help, command tích hợp, theme và cấu hình riêng của shell |
| Ứng dụng | `app`, `inventory`, `report` | Thư mục export, giới hạn dữ liệu, timeout, endpoint dịch vụ và chính sách nghiệp vụ |

Không đặt mọi thuộc tính dưới `spring.shell`. Prefix này thuộc về Spring Shell và được bind vào `SpringShellProperties`. Các giá trị do ứng dụng sở hữu nên có namespace riêng để tránh xung đột và giúp người đọc biết component nào chịu trách nhiệm.

Sơ đồ tổ chức:

~~~text
application.yaml
|
+-- spring
|   +-- application
|   |   +-- name
|   +-- shell
|       +-- interactive
|       +-- noninteractive
|       +-- script
|       +-- history
|       +-- config
|       +-- command
|       +-- help
|       +-- theme
|
+-- app
    +-- export
    +-- report
    +-- connection
~~~

`spring.application.name` là thuộc tính Spring Boot. Spring Shell có thể dùng tên ứng dụng để xác định tên file history mặc định.

## 2. Cấu hình runner trong Spring Shell 3.3

Spring Shell 3.3 cung cấp ba runner:

| Runner | Mục đích | Thuộc tính bật |
|---|---|---|
| `InteractiveShellRunner` | Mở REPL để người dùng nhập nhiều command | `spring.shell.interactive.enabled` |
| `NonInteractiveShellRunner` | Chạy command được truyền khi khởi động rồi kết thúc | `spring.shell.noninteractive.enabled` |
| `ScriptShellRunner` | Đọc và thực thi một chuỗi command từ script | `spring.shell.script.enabled` |

Từ phiên bản 3.3, chỉ `NonInteractiveShellRunner` được bật mặc định. Các phiên bản đến 3.2.x từng bật tất cả runner theo mặc định, vì vậy không nên sao chép cấu hình cũ mà không kiểm tra phiên bản đang dùng.

Ví dụ bật REPL và giữ khả năng chạy command non-interactive:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: false
~~~

Khi triển khai một công cụ dành cho người vận hành, có thể bật interactive runner để họ làm việc theo phiên. Trong pipeline tự động, có thể giữ non-interactive runner và tắt interactive runner để chương trình không chờ prompt.

Nếu cần chỉ định command chính cho non-interactive mode, có thể cấu hình:

~~~yaml
spring:
  shell:
    noninteractive:
      enabled: true
      primary-command: "orders list"
~~~

Chỉ dùng `primary-command` khi thiết kế khởi động của ứng dụng thực sự cần một command mặc định. Thông thường, command nên được truyền rõ ràng từ script hoặc hệ thống gọi để hành vi dễ dự đoán.

## 3. Tổ chức cấu hình Spring Shell theo chức năng

Một file `application.yaml` có thể gom các thuộc tính shell vào cùng một nhánh:

~~~yaml
spring:
  application:
    name: inventory-cli
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: false
    history:
      enabled: false
      name: inventory-cli-history
    config:
      location: "{userconfig}/inventory-cli"
    command:
      help:
        enabled: true
        grouping-mode: group
    help:
      enabled: true
      long-names: help
      short-names: h
      command: help
    theme:
      name: default
    context:
      close: false
~~~

Ví dụ trên minh họa cách nhóm thuộc tính. Giá trị `history.enabled: false` được chọn để tránh lưu các command có thể chứa thông tin nhạy cảm; ứng dụng không cần history thì nên giữ trạng thái tắt. Nếu history là tính năng cần thiết, bật nó sau khi đã xác định thư mục lưu, quyền truy cập và chính sách dữ liệu.

### Runner và execution mode

`spring.shell.interactive.enabled`, `spring.shell.noninteractive.enabled` và `spring.shell.script.enabled` điều khiển runner. Chúng ảnh hưởng đến cách ứng dụng bắt đầu xử lý command, không phải option của từng command.

Với annotation legacy, `@ShellMethod` còn có thuộc tính `interactionMode` để giới hạn command phù hợp với interactive hoặc non-interactive mode. Cấu hình runner và giới hạn command là hai quyết định liên quan nhưng khác nhau.

### History và vị trí file cấu hình shell

Các thuộc tính history:

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.shell.history.enabled` | Bật/tắt ghi lịch sử command; mặc định là bật |
| `spring.shell.history.name` | Tên file history |
| `spring.shell.config.location` | Vị trí cấu hình shell được dùng để xác định nơi lưu history |

Nếu không đặt tên history, Spring Shell dùng `spring.application.name` để tạo tên file và mặc định là `spring-shell.log` khi không có tên ứng dụng. Theo mặc định, file được tạo trong working directory. `spring.shell.config.location` có thể thay đổi vị trí này; giá trị `{userconfig}` được phân giải thành thư mục cấu hình dùng chung phù hợp với hệ điều hành.

Lưu ý: `spring.shell.config.location` không phải thuộc tính để Spring Boot tìm `application.yaml`. Nó là cấu hình của Spring Shell, được dùng trong ngữ cảnh history. Phần nạp file cấu hình của Spring Boot sử dụng `spring.config.location` hoặc `spring.config.additional-location`, được giải thích ở phần sau.

History có thể chứa command và argument người dùng đã nhập. Không truyền password, access token hoặc secret trực tiếp trên command line nếu chúng có thể bị lưu trong history hoặc process listing. Nếu không cần lưu lịch sử, tắt `spring.shell.history.enabled`; nếu cần, hãy giới hạn quyền file và đặt chính sách lưu giữ.

### Hai nhóm thuộc tính liên quan đến help

Spring Shell 3.3 có hai nhánh dễ bị nhầm:

| Prefix | Vai trò |
|---|---|
| `spring.shell.help` | Cấu hình các option trợ giúp tự động như `--help`, `-h`, tên option và command trợ giúp |
| `spring.shell.command.help` | Cấu hình built-in command `help`, cách nhóm command và template hiển thị |

Ví dụ, `spring.shell.command.help.grouping-mode` nhận `group` hoặc `flat`. Chọn `flat` để hiển thị danh sách command không chia theo group. `command-template` và `commands-template` cho phép thay template của phần trợ giúp chi tiết và danh sách command.

Không nhầm `spring.shell.command.help.enabled=false` với `spring.shell.help.enabled=false`: thuộc tính thứ nhất tắt built-in help command; thuộc tính thứ hai điều khiển việc thêm help option tự động.

### Theme và đóng application context

`spring.shell.theme.name` chọn tên theme được dùng bởi shell. Giá trị phải tương ứng với theme mà ứng dụng cung cấp hoặc theme đã được cấu hình.

`spring.shell.context.close` điều khiển việc yêu cầu đóng Spring `ApplicationContext` sau khi logic shell đã hoàn tất. Thuộc tính này hữu ích với ứng dụng chạy command theo batch nhưng còn thread nền không daemon khiến JVM chưa thoát. Không bật tùy tiện cho REPL cần duy trì phiên làm việc.

## 4. Phân biệt spring.config.location và spring.shell.config.location

Hai thuộc tính có tên gần giống nhau nhưng tác dụng khác nhau:

| Thuộc tính | Chủ sở hữu | Tác dụng |
|---|---|---|
| `spring.config.location` | Spring Boot | Chỉ định vị trí nạp file cấu hình; thay thế các vị trí tìm kiếm mặc định |
| `spring.config.additional-location` | Spring Boot | Bổ sung vị trí nạp file, giữ các vị trí mặc định |
| `spring.shell.config.location` | Spring Shell | Xác định vị trí cấu hình shell, trong đó có vị trí lưu history |

Ví dụ yêu cầu Spring Boot nạp thêm file bên ngoài:

~~~text
java -jar inventory-cli.jar --spring.config.additional-location=optional:file:./deploy/
~~~

Spring Boot tiếp tục tìm cấu hình theo vị trí mặc định và nạp thêm cấu hình trong `./deploy/`. Nếu dùng `spring.config.location`, các vị trí mặc định bị thay thế bởi danh sách đã chỉ định; cần cân nhắc trước khi dùng.

Ví dụ cấu hình vị trí history của Spring Shell:

~~~yaml
spring:
  shell:
    config:
      location: "{userconfig}/inventory-cli"
~~~

Đừng dùng `spring.shell.config.location` để cố gắng nạp một file `application-prod.yaml`. Hãy dùng cơ chế config data của Spring Boot cho việc đó.

## 5. Dùng profile để tách development, test và production

Đặt giá trị dùng chung trong `application.yaml`, sau đó ghi đè những thuộc tính khác nhau trong file profile:

`application.yaml`:

~~~yaml
spring:
  application:
    name: inventory-cli
  shell:
    noninteractive:
      enabled: true
    history:
      enabled: false

app:
  export:
    directory: ./var/exports
    max-rows: 5000
    timeout: 30s
    overwrite: false
~~~

`application-dev.yaml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true

app:
  export:
    directory: ./build/dev-exports
    max-rows: 1000
~~~

`application-prod.yaml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    script:
      enabled: false
    noninteractive:
      enabled: true

app:
  export:
    directory: /var/lib/inventory-cli/exports
    max-rows: 10000
    timeout: 2m
~~~

Kích hoạt profile bằng environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Hoặc dùng system property:

~~~text
java -Dspring.profiles.active=prod -jar inventory-cli.jar
~~~

File `application-{profile}.yaml` ghi đè các giá trị tương ứng trong file chung khi profile đó hoạt động. Nếu bật nhiều profile, profile được xét sau có thể ghi đè profile trước. Nên giữ cấu hình dùng chung ở file cơ sở và chỉ đặt phần khác biệt vào file profile để tránh sao chép toàn bộ cấu hình.

## 6. Ghi đè cấu hình bằng environment variable và command-line argument

Spring Boot hỗ trợ relaxed binding để một thuộc tính có thể được biểu diễn trong nhiều dạng.

Ví dụ cùng một thuộc tính:

| Nguồn | Cách viết |
|---|---|
| YAML | `app.export.max-rows: 5000` |
| Properties | `app.export.max-rows=5000` |
| Environment variable | `APP_EXPORT_MAXROWS=5000` |
| System property | `-Dapp.export.max-rows=5000` |
| Command-line property | `--app.export.max-rows=5000` |

Quy tắc chuyển tên property sang environment variable:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-`.
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ `spring.shell.interactive.enabled` trở thành `SPRING_SHELL_INTERACTIVE_ENABLED`; `app.export.max-rows` trở thành `APP_EXPORT_MAXROWS`.

Trong một số môi trường, có thể dùng command-line property để ghi đè giá trị một lần:

~~~text
java -jar inventory-cli.jar --app.export.max-rows=2000
~~~

Spring Boot chuyển các argument bắt đầu bằng `--` thành property trong `Environment`. Command-line property có độ ưu tiên cao hơn cấu hình file. Khi chạy Spring Shell, hãy phân biệt argument dành cho Spring Boot lúc khởi động với option của command được thực thi; đặt property ở startup chỉ khi muốn thay đổi cấu hình của application context.

### Thứ tự ưu tiên tổng quát

Spring Boot có nhiều nguồn property. Với các nguồn thường gặp trong ứng dụng CLI, thứ tự từ ưu tiên thấp đến cao có thể hình dung như sau:

~~~text
application.yaml
    ↓
application-{profile}.yaml
    ↓
application.yaml bên ngoài JAR
    ↓
application-{profile}.yaml bên ngoài JAR
    ↓
OS environment variables
    ↓
Java system properties (-D...)
    ↓
SPRING_APPLICATION_JSON
    ↓
command-line properties (--key=value)
~~~

Đây là sơ đồ rút gọn để dễ nhớ. Thứ tự đầy đủ còn có default properties, `@PropertySource`, JNDI, test properties và một số nguồn khác. Khi có hai nguồn cùng khai báo một key, nguồn có độ ưu tiên cao hơn quyết định giá trị cuối cùng.

## 7. Bind thuộc tính nghiệp vụ bằng @ConfigurationProperties

`@Value` phù hợp với một vài giá trị đơn lẻ. Khi một nhóm thuộc tính có quan hệ với nhau, dùng `@ConfigurationProperties` để bind thành một object có kiểu. Cách này giúp gom cấu hình, dễ kiểm tra, dễ inject và dễ viết test.

Ví dụ cấu hình:

~~~yaml
app:
  export:
    directory: ./var/exports
    max-rows: 5000
    timeout: 30s
    overwrite: false
~~~

Tạo record:

~~~java
import java.nio.file.Path;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
        @NotNull Path directory,
        @Min(1) @Max(100000) int maxRows,
        @NotNull Duration timeout,
        boolean overwrite) {
}
~~~

Kích hoạt scan cấu hình trong ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class InventoryShellApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryShellApplication.class, args);
    }
}
~~~

Nếu dùng Bean Validation như `@NotNull`, `@Min` hoặc `@Max`, thêm dependency validation tương thích với Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Spring Boot bind các giá trị từ `Environment` vào record. `Duration` nhận chuỗi có đơn vị như `30s`, `2m`; `Path` được chuyển thành kiểu đường dẫn. Khi cấu hình thiếu hoặc không hợp lệ theo constraint, ứng dụng báo lỗi trong quá trình khởi tạo thay vì để command gặp lỗi muộn.

### Inject cấu hình vào service

~~~java
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    private final ExportProperties properties;

    public ExportService(ExportProperties properties) {
        this.properties = properties;
    }

    public void export() {
        Path directory = properties.directory();
        int maxRows = properties.maxRows();
        Duration timeout = properties.timeout();

        // Dùng cấu hình đã được bind và validate.
    }
}
~~~

Service không cần tự đọc file YAML hoặc gọi `System.getenv()`. Spring Boot đã giải quyết nguồn cấu hình và bind vào bean. Điều này cũng giúp test có thể truyền property khác nhau mà không sửa code nghiệp vụ.

## 8. Dùng Environment khi cần đọc một giá trị linh hoạt

`Environment` hữu ích khi một thành phần cần đọc thuộc tính theo tên, chẳng hạn một integration tùy chọn hoặc một giá trị có thể không tồn tại:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ShellDiagnostics {

    private final Environment environment;

    public ShellDiagnostics(Environment environment) {
        this.environment = environment;
    }

    public String activeProfile() {
        String[] profiles = environment.getActiveProfiles();
        return profiles.length == 0
                ? "default"
                : String.join(", ", profiles);
    }

    public boolean isInteractiveEnabled() {
        return environment.getProperty(
                "spring.shell.interactive.enabled",
                Boolean.class,
                false);
    }
}
~~~

Khi cần bind một nhóm thuộc tính ổn định, ưu tiên `@ConfigurationProperties`. Khi cần truy vấn linh hoạt theo tên hoặc kiểm tra profile đang hoạt động, `Environment` là lựa chọn phù hợp. Tránh gọi `System.getenv()` trực tiếp trong service vì như vậy bỏ qua cơ chế precedence và relaxed binding của Spring Boot.

## 9. Giá trị mặc định, validation và cấu hình bắt buộc

Một cấu hình tốt cần phân biệt:

- **Giá trị mặc định:** ứng dụng có thể chạy an toàn nếu người triển khai không cung cấp.
- **Giá trị bắt buộc:** thiếu giá trị thì ứng dụng nên dừng với thông báo rõ ràng.
- **Giá trị theo môi trường:** khác nhau giữa dev, test và prod.
- **Secret:** phải lấy từ nguồn bảo mật, không commit vào file cấu hình.

Ví dụ:

| Thuộc tính | Cách xử lý |
|---|---|
| `app.export.max-rows` | Có thể có mặc định hợp lý và giới hạn bằng `@Min`/`@Max` |
| `app.export.directory` | Có thể có mặc định trong dev; production nên chỉ định rõ |
| `app.export.timeout` | Đặt mặc định có đơn vị, ví dụ `30s` |
| `app.connection.api-token` | Không commit giá trị thật vào repository; lấy từ secret store hoặc environment được quản lý |

Không dùng giá trị mặc định giả như `admin/admin` hoặc token mẫu có thể bị dùng nhầm ở production. Với thuộc tính bắt buộc, validation nên làm ứng dụng fail fast ngay khi khởi động và nêu rõ key nào cần cấu hình.

### Dùng placeholder để tái sử dụng giá trị

Spring Boot cho phép tham chiếu thuộc tính khác bằng cú pháp placeholder:

~~~yaml
app:
  export:
    base-directory: ${APP_DATA_DIR:./var}
    directory: ${app.export.base-directory}/exports
~~~

Placeholder `${APP_DATA_DIR:./var}` dùng giá trị environment nếu có, nếu không thì dùng `./var`. Khi nhiều thuộc tính phụ thuộc nhau, hãy giữ tên và quan hệ rõ ràng để người vận hành biết thay đổi một key sẽ ảnh hưởng đến đâu.

## 10. Quản lý secret và dữ liệu nhạy cảm

Không lưu password, access token, private key hoặc credential thật trong `application.yaml` được commit vào Git. Các lựa chọn thường dùng:

- Environment variable được quản lý bởi hệ thống triển khai.
- Secret manager hoặc vault của nền tảng.
- Spring Boot config tree khi secret được mount thành file.
- File cấu hình ngoài JAR có permission giới hạn, nếu môi trường triển khai yêu cầu.

Ví dụ nạp secret từ config tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Nếu thư mục `/run/secrets/` có file tên `app.connection.password`, nội dung file có thể được bind thành property tương ứng. Cơ chế này là của Spring Boot; Spring Shell không tự quản lý secret.

Ngoài nơi lưu cấu hình, cần xem xét dữ liệu bị lộ qua history và log. Một command như `connect --password ...` có thể làm secret xuất hiện trong history, process arguments hoặc log debug. Nên dùng cơ chế nhập secret an toàn, prompt không echo hoặc credential provider thay vì truyền secret như option thông thường.

## 11. Kiểm tra cấu hình khi ứng dụng chạy

Khi một command chạy sai hành vi, hãy kiểm tra theo thứ tự:

1. Profile nào đang hoạt động?
2. Thuộc tính có được khai báo trong `application.yaml` hoặc file profile đúng không?
3. Environment variable hoặc system property có đang ghi đè không?
4. Command-line argument có cung cấp giá trị khác không?
5. Bean `@ConfigurationProperties` đã bind đúng kiểu và qua validation chưa?
6. Có nhầm `spring.shell.config.location` với `spring.config.location` không?
7. Runner tương ứng đã được bật chưa?

Có thể log profile và các giá trị không nhạy cảm khi khởi động:

~~~java
import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationSummary implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ConfigurationSummary.class);

    private final Environment environment;
    private final ExportProperties exportProperties;

    public ConfigurationSummary(
            Environment environment,
            ExportProperties exportProperties) {
        this.environment = environment;
        this.exportProperties = exportProperties;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles()));
        log.info("Export directory: {}", exportProperties.directory());
        log.info("Export max rows: {}", exportProperties.maxRows());
    }
}
~~~

Đây là phần thân minh họa; trong ứng dụng thực tế cần khai báo logger phù hợp. Không log toàn bộ `Environment`, mọi property hoặc credential. Chỉ ghi những giá trị vận hành an toàn và hữu ích để chẩn đoán.

Nếu ứng dụng có Spring Boot Actuator, endpoint `env` và `configprops` có thể giúp kiểm tra nguồn và giá trị đã bind. Chỉ bật và bảo vệ các endpoint chẩn đoán trong môi trường phù hợp; không công khai chúng cho người dùng shell hoặc mạng không tin cậy.

## 12. Kiểm thử cấu hình

Có thể kiểm tra binding bằng test Spring context với property được cung cấp trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.export.directory=./build/test-exports",
        "app.export.max-rows=200",
        "app.export.timeout=5s",
        "app.export.overwrite=true"
})
class ExportPropertiesTest {

    @Autowired
    ExportProperties properties;

    @Test
    void bindsExportSettings() {
        assertThat(properties.directory())
                .isEqualTo(Path.of("./build/test-exports"));
        assertThat(properties.maxRows()).isEqualTo(200);
        assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(5));
        assertThat(properties.overwrite()).isTrue();
    }
}
~~~

Test này kiểm tra Spring Boot bind chuỗi cấu hình thành kiểu Java đúng. Có thể viết thêm test context khởi động thất bại khi `max-rows` bằng 0 hoặc thiếu `directory` bắt buộc. Nếu chỉ kiểm tra một lớp nghiệp vụ, không cần khởi động shell runner hoặc terminal.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng chỉ chạy command rồi thoát, không hiện prompt | Spring Shell 3.3 chỉ bật non-interactive runner mặc định | Bật `spring.shell.interactive.enabled=true` |
| Script không chạy | `spring.shell.script.enabled` đang tắt | Bật script runner trong profile phù hợp |
| History không xuất hiện | `spring.shell.history.enabled=false` hoặc thư mục không ghi được | Kiểm tra cờ history và quyền thư mục |
| History nằm ở thư mục không mong muốn | Nhầm working directory hoặc `spring.shell.config.location` | Kiểm tra vị trí cấu hình history và placeholder `{userconfig}` |
| File `application-prod.yaml` không được nạp | Profile chưa active hoặc tên file sai | Kiểm tra `SPRING_PROFILES_ACTIVE` và tên profile |
| Biến môi trường không ghi đè property | Tên biến không theo quy tắc relaxed binding | Thay dấu chấm bằng `_`, bỏ dấu `-`, viết hoa |
| `APP_EXPORT_MAX_ROWS` không bind như dự kiến | Dấu gạch ngang được chuyển đổi không đúng theo quy tắc environment variable | Dùng `APP_EXPORT_MAXROWS` cho `app.export.max-rows` |
| Help command biến mất | Đã tắt `spring.shell.command.help.enabled` | Bật lại built-in help command |
| Option `--help` không xuất hiện | Nhầm `spring.shell.help.enabled` với `spring.shell.command.help.enabled` | Kiểm tra đúng nhánh cấu hình |
| `spring.shell.config.location` không nạp file YAML | Dùng nhầm thuộc tính của Spring Shell thay cho Spring Boot | Dùng `spring.config.location` hoặc `spring.config.additional-location` |
| Giá trị cấu hình có kiểu sai | Bind thủ công hoặc dùng chuỗi ở nhiều nơi | Dùng `@ConfigurationProperties` và kiểu Java phù hợp |
| Ứng dụng khởi động nhưng command lỗi muộn | Thiếu validation cho property bắt buộc | Dùng Bean Validation và fail fast |
| Secret xuất hiện trong history | Người dùng truyền secret trực tiếp trong command | Tắt history khi cần, dùng prompt hoặc secret provider |
| Test context bị ảnh hưởng bởi profile máy phát triển | Test dựa vào environment bên ngoài | Truyền property và profile rõ ràng trong test |

## 14. Checklist tổ chức cấu hình

- Giữ thuộc tính Spring Shell dưới `spring.shell`.
- Đặt thuộc tính nghiệp vụ dưới prefix riêng của ứng dụng.
- Chia cấu hình theo runner, history, help, theme và command tích hợp.
- Kiểm tra thay đổi mặc định giữa Spring Shell 3.2 và 3.3.
- Dùng `application.yaml` cho cấu hình chung và `application-{profile}.yaml` cho khác biệt môi trường.
- Chọn profile qua environment hoặc system property.
- Dùng environment variable theo relaxed binding của Spring Boot.
- Dùng command-line property cho ghi đè một lần, có chủ đích.
- Dùng `@ConfigurationProperties` cho nhóm thuộc tính có cấu trúc.
- Validate giá trị bắt buộc và giới hạn ngay khi khởi động.
- Phân biệt `spring.config.location` với `spring.shell.config.location`.
- Xác định vị trí, quyền và chính sách lưu history.
- Không commit secret hoặc ghi secret vào history/log.
- Log một phần cấu hình vận hành an toàn để chẩn đoán.
- Viết test cho binding, profile và validation.

## 15. Bài tập thực hành

Tạo ứng dụng `inventory-cli` với cấu hình development và production:

1. Đặt `spring.application.name` thành `inventory-cli`.
2. Trong `application.yaml`, cấu hình `spring.shell.noninteractive.enabled=true`.
3. Trong `application-dev.yaml`, bật interactive runner và script runner.
4. Trong `application-prod.yaml`, tắt interactive và script runner, giữ non-interactive runner.
5. Cấu hình history file trong thư mục user config; thử tắt history khi command có thể nhận dữ liệu nhạy cảm.
6. Tùy chỉnh `spring.shell.command.help.grouping-mode` giữa `group` và `flat`.
7. Tạo `ExportProperties` với `directory`, `maxRows`, `timeout` và `overwrite`.
8. Dùng `@ConfigurationPropertiesScan` để đăng ký record cấu hình.
9. Dùng Bean Validation để từ chối `maxRows` bằng 0 hoặc âm.
10. Ghi đè `app.export.max-rows` bằng environment variable `APP_EXPORT_MAXROWS`.
11. Chạy ứng dụng với profile `dev`, sau đó `prod`; xác nhận runner và thư mục export thay đổi.
12. Thử `spring.config.additional-location` để nạp cấu hình triển khai từ thư mục bên ngoài.
13. Kiểm tra sự khác nhau giữa `spring.config.location` và `spring.shell.config.location`.
14. Viết test xác nhận `Duration` và `Path` được bind đúng kiểu.
15. Kiểm tra log khởi động không in token hoặc password.

Khi hoàn thành, hãy giải thích thuộc tính nào thuộc Spring Shell, thuộc tính nào thuộc nghiệp vụ ứng dụng và vì sao profile, environment variable cùng command-line property có thể tạo ra giá trị cuối khác với `application.yaml`.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): interactive, non-interactive và script runner; thay đổi mặc định từ 3.3.
- [Spring Shell 3.3 – History](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html): cấu hình history, tên file và `spring.shell.config.location`.
- [Spring Shell 3.3 – Help](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/help.html): built-in help, grouping mode và template.
- [Spring Shell 3.3 – Help Options](https://docs.spring.io/spring-shell/reference/3.3/commands/helpoptions.html): cấu hình option trợ giúp `--help` và `-h`.
- [Spring Shell 3.3 – SpringShellProperties API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/SpringShellProperties.html): prefix `spring.shell` và các nhóm thuộc tính.
- [Spring Boot 3.3 – Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): YAML, profile, environment variable, system property, command-line argument và precedence.
- [Spring Boot 3.3 – Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html): metadata hỗ trợ IDE và tài liệu thuộc tính cấu hình.
- [Spring Boot 3.3 – @ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): bind cấu hình có kiểu và validation.

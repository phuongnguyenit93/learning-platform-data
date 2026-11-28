# Tệp lịch sử, thư mục làm việc và vị trí cấu hình người dùng

Ứng dụng Spring Shell có thể tạo hoặc đọc nhiều tệp trong lúc chạy: tệp lịch sử lệnh, script, cấu hình riêng của người dùng và dữ liệu do command xuất ra. Nếu không xác định rõ thư mục gốc của các tệp này, cùng một lệnh có thể ghi dữ liệu vào những vị trí khác nhau tùy nơi người dùng khởi chạy ứng dụng. Việc đặt nhầm tệp lịch sử vào thư mục cài đặt cũng có thể khiến ứng dụng không ghi được khi thư mục đó chỉ có quyền đọc.

Bài học thuộc chương **Cấu hình và vận hành**. Nội dung giải thích ba khái niệm cần phân biệt: thư mục làm việc hiện tại của tiến trình, thư mục cấu hình người dùng do Spring Shell cung cấp và tệp lịch sử lệnh của JLine. Bạn sẽ biết cách cấu hình vị trí lưu, truy xuất đường dẫn khi chạy, tổ chức tệp theo từng ứng dụng và bảo vệ nội dung lịch sử.

Sau bài học, bạn có thể:

- Phân biệt working directory, user home và user configuration directory.
- Xác định thư mục làm việc bằng `user.dir` hoặc `Path`.
- Hiểu nơi Spring Shell lưu history mặc định và cách đổi tên tệp.
- Cấu hình `spring.shell.config.location` và placeholder `{userconfig}`.
- Sử dụng `spring.shell.config.env` để lấy vị trí từ biến môi trường.
- Truy xuất hoặc thay thế `UserConfigPathProvider`.
- Phân biệt cấu hình lưu dữ liệu của Spring Shell với `spring.config.location` của Spring Boot.
- Quản lý quyền truy cập, nội dung nhạy cảm và vòng đời tệp history.
- Nhận biết thay đổi tích hợp JLine khi chuyển từ Spring Shell 3.x sang 4.x.

## Ba loại vị trí cần phân biệt

Một ứng dụng CLI thường làm việc với ít nhất ba loại thư mục. Chúng có mục đích khác nhau và không nên được xem là một đường dẫn duy nhất.

| Khái niệm | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| Working directory | Thư mục hiện tại của tiến trình khi ứng dụng được khởi chạy. | Đọc `./scripts/setup.shell`, ghi `./exports/report.csv`. |
| User home | Thư mục cá nhân của tài khoản đang chạy tiến trình, thường được JVM cung cấp qua `user.home`. | Lưu dữ liệu hoặc cấu hình cá nhân theo lựa chọn của ứng dụng. |
| User configuration directory | Thư mục cấu hình cấp người dùng do `UserConfigPathProvider` cung cấp. | Lưu history hoặc dữ liệu cấu hình riêng của CLI. |

Working directory phụ thuộc vào nơi gọi lệnh khởi chạy. User home gắn với tài khoản hệ điều hành. User configuration directory là khái niệm mà ứng dụng có thể lấy từ Spring Shell; không nên tự giả định nó luôn bằng working directory hoặc một thư mục cố định dưới user home.

Ví dụ, cùng một JAR có thể được chạy từ hai nơi:

```bash
cd /opt/deploy
java -jar deploy-cli.jar
```

```bash
cd /srv/jobs/nightly
java -jar /opt/deploy/deploy-cli.jar
```

Ở lần chạy thứ nhất, working directory là `/opt/deploy`; ở lần chạy thứ hai, working directory là `/srv/jobs/nightly`. Đường dẫn tương đối được phân giải theo thư mục làm việc của tiến trình, không tự động theo thư mục chứa JAR.

## Xác định working directory

Trong Java, `System.getProperty("user.dir")` cho biết working directory của tiến trình. Có thể dùng `Path` để chuẩn hóa và kết hợp đường dẫn:

```java
import java.nio.file.Path;

Path workingDirectory = Path.of("")
    .toAbsolutePath()
    .normalize();

Path reportPath = workingDirectory
    .resolve(Path.of("exports", "report.csv"))
    .normalize();
```

`Path.of("")` biểu diễn đường dẫn tương đối rỗng; `toAbsolutePath()` chuyển nó thành đường dẫn tuyệt đối theo working directory hiện tại. `resolve(...)` nối một đường dẫn con và `normalize()` loại bỏ các thành phần `.` hoặc `..` dư thừa về mặt cú pháp.

Có thể dùng `System.getProperty("user.dir")` để chẩn đoán khi một tệp không được tìm thấy:

```java
String userDir = System.getProperty("user.dir");
System.out.println("Working directory: " + userDir);
```

Không nên ghép đường dẫn bằng cách nối chuỗi với dấu `/` hoặc `\\`. `Path.of(...)` và `Path.resolve(...)` xử lý dấu phân cách theo hệ điều hành.

### Đường dẫn tương đối và tuyệt đối

Đường dẫn tương đối phụ thuộc working directory:

```java
Path script = Path.of("scripts", "bootstrap.shell");
Path resolvedScript = script.toAbsolutePath().normalize();
```

Đường dẫn tuyệt đối không phụ thuộc thư mục mà người dùng gọi lệnh:

```java
Path configFile = Path.of("/etc/deploy-cli/application.yml");
```

Trong ứng dụng đa nền tảng, không nên ghi cứng đường dẫn Unix như ví dụ trên. Hãy nhận đường dẫn từ cấu hình, biến môi trường hoặc `Path` được xây dựng theo quy tắc của hệ điều hành.

Nếu command nhận đường dẫn từ người dùng, nên hiển thị đường dẫn đã phân giải khi cần chẩn đoán và kiểm tra quyền đọc/ghi trước khi thao tác. Đừng giả định file tồn tại chỉ vì `Path` đã được tạo thành công.

## Tệp lịch sử của Spring Shell

Trong Spring Shell 3.3.x sử dụng JLine, lịch sử các lệnh đã nhập được lưu trong một log file và được bật mặc định. Lệnh tích hợp `history` cho phép xem những lệnh đã chạy; nó cũng có thể ghi lịch sử ra tệp để dùng với command `script`.

Spring Shell cung cấp các thuộc tính chính:

| Property | Mục đích | Hành vi mặc định theo tài liệu 3.3.x |
| --- | --- | --- |
| `spring.shell.history.enabled` | Bật/tắt việc lưu lịch sử vào log file. | `true`. |
| `spring.shell.history.name` | Đặt tên tệp lịch sử. | Tên được suy ra từ `spring.application.name`; nếu không có thì dùng `spring-shell.log`. |
| `spring.shell.config.location` | Đặt thư mục cơ sở cho dữ liệu cấu hình runtime của shell, bao gồm vị trí history. | Working directory hiện tại. |
| `spring.shell.config.env` | Chỉ định tên biến môi trường dùng để cung cấp vị trí cấu hình người dùng. | Không bắt buộc. |
| `spring.shell.command.history.enabled` | Bật/tắt command `history` trong command registry. | `true` nếu không cấu hình. |

Hai thuộc tính có chữ `history` đầu tiên có mục đích khác nhau: `spring.shell.history.enabled` điều khiển lưu history; `spring.shell.command.history.enabled` điều khiển command `history` có xuất hiện và được gọi hay không. Tắt command không đồng nghĩa đã tắt lưu tệp, và ngược lại.

### Cấu hình tệp history

Ví dụ sau đặt tên ứng dụng, bật lưu lịch sử và đặt tên tệp rõ ràng:

```yaml
spring:
  application:
    name: deploy-cli
  shell:
    history:
      enabled: true
      name: deploy-cli-history.log
```

Nếu không cấu hình `spring.shell.config.location`, tài liệu Spring Shell 3.3.x mô tả log file được tạo trong working directory. Vì vậy, nếu ứng dụng được khởi chạy từ thư mục khác, vị trí history mặc định cũng có thể thay đổi theo.

Có thể tắt lưu history:

```yaml
spring:
  shell:
    history:
      enabled: false
```

Có thể ẩn command `history` khỏi command registry:

```yaml
spring:
  shell:
    command:
      history:
        enabled: false
```

Chỉ tắt command nếu yêu cầu là người dùng không được gọi `history`. Nếu yêu cầu là không ghi lệnh xuống đĩa, hãy cấu hình `spring.shell.history.enabled=false`.

## Đặt thư mục bằng spring.shell.config.location

`spring.shell.config.location` điều khiển thư mục cơ sở mà Spring Shell dùng cho dữ liệu cấu hình runtime như history. Thuộc tính này có thể nhận đường dẫn tương đối, đường dẫn tuyệt đối hoặc placeholder `{userconfig}`.

### Lưu history trong working directory con

```yaml
spring:
  shell:
    config:
      location: "./.deploy-cli"
    history:
      name: history.log
```

Với cấu hình này, thư mục `.deploy-cli` được tính từ working directory của tiến trình. Cách lưu này phù hợp khi mỗi workspace cần history riêng, ví dụ một môi trường CI chạy trong workspace độc lập.

Đảm bảo thư mục tồn tại và tiến trình có quyền ghi. Nếu chạy từ thư mục cài đặt chỉ đọc hoặc từ thư mục không ổn định, việc lưu history có thể thất bại hoặc tạo tệp ở nơi người vận hành không mong đợi.

### Lưu trong thư mục cấu hình người dùng

Spring Shell hỗ trợ placeholder `{userconfig}`. Placeholder này được thay bằng đường dẫn mà `UserConfigPathProvider` cung cấp:

```yaml
spring:
  application:
    name: deploy-cli
  shell:
    config:
      location: "{userconfig}/deploy-cli"
    history:
      name: history.log
```

Cách này giúp history không phụ thuộc thư mục mà người dùng khởi chạy JAR. Người dùng có thể mở CLI từ terminal bất kỳ mà vẫn dùng cùng một thư mục cấu hình cấp người dùng.

Không nên tự ghi cứng một đường dẫn mặc định cho Linux, macOS hoặc Windows khi chưa kiểm tra provider đang dùng. Hãy lấy đường dẫn từ `UserConfigPathProvider` hoặc cấu hình tường minh nếu sản phẩm cần một vị trí cố định.

### Lấy vị trí từ biến môi trường

`spring.shell.config.env` cho phép chỉ định tên biến môi trường cung cấp thư mục cấu hình. Ví dụ:

```yaml
spring:
  shell:
    config:
      env: DEPLOY_CLI_CONFIG_DIR
```

Trước khi khởi chạy, thiết lập biến môi trường đó theo môi trường triển khai.

PowerShell:

```powershell
$env:DEPLOY_CLI_CONFIG_DIR = "D:\Data\deploy-cli"
java -jar deploy-cli.jar
```

Bash:

```bash
export DEPLOY_CLI_CONFIG_DIR="$HOME/.config/deploy-cli"
java -jar deploy-cli.jar
```

`DEPLOY_CLI_CONFIG_DIR` là tên biến môi trường mà cấu hình chỉ định; giá trị của biến là thư mục cần dùng. Cách này hữu ích khi triển khai cùng một artifact ở nhiều máy nhưng mỗi máy có chính sách lưu dữ liệu khác nhau.

## UserConfigPathProvider

`UserConfigPathProvider` là functional interface cung cấp một `Path` đến vị trí cấu hình runtime cấp người dùng. Spring Shell có auto-configuration đăng ký implementation mặc định nếu ứng dụng chưa cung cấp bean khác.

Trong Spring Shell 3.3.x, interface nằm trong package `org.springframework.shell.config`:

```java
import java.nio.file.Path;

import org.springframework.shell.config.UserConfigPathProvider;
import org.springframework.stereotype.Component;

@Component
public class ShellPathCommands {

    private final UserConfigPathProvider userConfigPathProvider;

    public ShellPathCommands(UserConfigPathProvider userConfigPathProvider) {
        this.userConfigPathProvider = userConfigPathProvider;
    }

    public Path userConfigDirectory() {
        return userConfigPathProvider.provide();
    }
}
```

`provide()` trả về đường dẫn cấu hình người dùng. Có thể dùng giá trị này để hiển thị chẩn đoán, đặt thư mục mặc định cho tệp riêng của ứng dụng hoặc kiểm tra quyền ghi.

Ví dụ command hoàn chỉnh hiển thị hai vị trí:

```java
import java.nio.file.Path;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.config.UserConfigPathProvider;

@ShellComponent
public class LocationCommands {

    private final UserConfigPathProvider userConfigPathProvider;

    public LocationCommands(UserConfigPathProvider userConfigPathProvider) {
        this.userConfigPathProvider = userConfigPathProvider;
    }

    @ShellMethod(key = "paths show", value = "Hiển thị các thư mục của shell")
    public String showPaths() {
        Path workingDirectory = Path.of("")
            .toAbsolutePath()
            .normalize();
        Path userConfigDirectory = userConfigPathProvider.provide();

        return "Working directory: " + workingDirectory
            + System.lineSeparator()
            + "User config directory: " + userConfigDirectory;
    }
}
```

Khi chạy `paths show`, người vận hành có thể thấy working directory và user config directory mà ứng dụng đang nhận được. Đây là cách hữu ích để xử lý lỗi ghi tệp mà không cần đoán vị trí theo hệ điều hành.

### Thay thế provider mặc định

Nếu sản phẩm có quy ước riêng, có thể đăng ký một bean `UserConfigPathProvider`. Ví dụ sau chủ động chọn một thư mục con của user home:

```java
import java.nio.file.Path;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.config.UserConfigPathProvider;

@Configuration(proxyBeanMethods = false)
public class UserConfigLocationConfiguration {

    @Bean
    UserConfigPathProvider userConfigPathProvider() {
        return () -> Path.of(System.getProperty("user.home"), ".deploy-cli");
    }
}
```

Đây là lựa chọn do ứng dụng đặt ra, không phải khẳng định rằng `.deploy-cli` là thư mục chuẩn trên mọi hệ điều hành. Khi thay thế provider, hãy thống nhất quy tắc này với tài liệu cài đặt, backup, quyền truy cập và gỡ cài đặt.

Không tạo thư mục hoặc tệp chỉ bằng cách gọi `provide()`. Provider trả về một đường dẫn; code ghi dữ liệu cần chủ động tạo thư mục nếu cần, kiểm tra quyền và xử lý `IOException`.

## Phân biệt cấu hình Spring Shell với cấu hình Spring Boot

Hai thuộc tính sau có tên gần giống nhau nhưng giải quyết hai việc khác nhau:

| Property | Thành phần sở hữu | Mục đích |
| --- | --- | --- |
| `spring.shell.config.location` | Spring Shell | Chọn thư mục cơ sở cho dữ liệu cấu hình runtime của shell, trong đó có history. |
| `spring.config.location` | Spring Boot | Chọn vị trí các file cấu hình ứng dụng như `application.yml` hoặc `application.properties`. |

Ví dụ, nếu muốn Spring Boot đọc file cấu hình ứng dụng bên ngoài:

```bash
java -jar deploy-cli.jar --spring.config.location=file:./config/application.yml
```

Nếu muốn đổi nơi lưu history của Spring Shell, dùng `spring.shell.config.location` trong YAML, system property hoặc nguồn cấu hình phù hợp. Đặt `spring.config.location` không tự động chuyển tệp history; ngược lại, đặt `spring.shell.config.location` cũng không đổi nơi Spring Boot tìm `application.yml`.

Spring Boot xử lý `spring.config.location` rất sớm trong quá trình khởi động. Nếu cấu hình thuộc tính này bằng biến môi trường, system property hoặc command-line argument, hãy dùng đúng cơ chế externalized configuration của Spring Boot. Không nhầm các thuộc tính cấu hình của shell với property source loader của Boot.

## Working directory trong script và khi xuất dữ liệu

Đường dẫn tương đối trong command, script hoặc code Java phụ thuộc working directory của tiến trình. Vì vậy, nên quyết định rõ đường dẫn nào là:

- Đầu vào do người dùng cung cấp.
- Tương đối với workspace hiện tại.
- Thuộc thư mục cấu hình người dùng.
- Thuộc thư mục dữ liệu hoặc output do ứng dụng quản lý.

Ví dụ command xuất báo cáo nên nhận đường dẫn đầu ra tường minh:

```text
report export --output ./exports/daily.csv
```

Nếu muốn có thư mục mặc định theo user config, có thể dùng provider để lấy base directory rồi kết hợp tên file:

```java
Path outputDirectory = userConfigPathProvider.provide()
    .resolve("exports")
    .normalize();

Path outputFile = outputDirectory.resolve("daily.csv");
```

Trước khi ghi, tạo thư mục nếu cần:

```java
Files.createDirectories(outputFile.getParent());
Files.writeString(outputFile, csvContent);
```

Trong ứng dụng thực tế, hãy kiểm tra `outputFile.getParent()` không null trước khi tạo thư mục nếu đường dẫn có thể chỉ là tên file. Đồng thời kiểm tra quyền ghi và xử lý lỗi khi đĩa đầy hoặc thư mục không khả dụng.

Đối với script, nên dùng đường dẫn rõ ràng hoặc quy ước workspace nhất quán trong tài liệu vận hành. Một script gọi `script ./scripts/setup.shell` sẽ phụ thuộc working directory nếu truyền đường dẫn tương đối.

## Bảo vệ và quản lý tệp history

History hữu ích để xem lại thao tác, nhưng nó là dữ liệu cục bộ do ứng dụng ghi ra. Không nên xem tệp này là audit log có tính toàn vẹn hoặc nguồn sự thật cho hoạt động nghiệp vụ.

Một số command có thể chứa token, password, mã truy cập, thông tin cá nhân hoặc dữ liệu nội bộ ngay trong argument. Nếu history ghi nguyên dòng lệnh, những giá trị đó có thể tồn tại trên đĩa và được người khác đọc nếu quyền tệp quá rộng.

Thực hành nên áp dụng:

- Không truyền password, access token hoặc secret qua command argument nếu có thể dùng prompt bảo mật hoặc secret manager.
- Tắt lưu history bằng `spring.shell.history.enabled=false` trong môi trường xử lý dữ liệu nhạy cảm nếu không cần chức năng này.
- Giới hạn quyền đọc/ghi thư mục user config và tệp history cho đúng tài khoản chạy CLI.
- Không đặt history trong thư mục dùng chung mà mọi người dùng hệ thống đều có quyền đọc.
- Đặt chính sách retention và dọn lịch sử theo yêu cầu vận hành.
- Khi export history ra script, rà soát nội dung trước khi lưu trữ hoặc chia sẻ.
- Chỉ chạy script được tin cậy; tệp history export có thể chứa các command thực thi được.

Ví dụ cấu hình cho môi trường không lưu history:

```yaml
spring:
  shell:
    history:
      enabled: false
```

Nếu chỉ muốn ẩn command `history` nhưng vẫn duy trì ghi history cho mục đích nội bộ, cấu hình riêng `spring.shell.command.history.enabled=false`. Hãy xác định rõ yêu cầu bảo mật trước khi chọn một trong hai thuộc tính.

## Khác biệt cần chú ý khi chuyển sang Spring Shell 4.x

Spring Shell 4.x thay đổi cách chia module. `spring-shell-core` không còn phụ thuộc trực tiếp vào JLine; console mặc định có thể dùng `java.io.Console`. Nếu muốn dùng JLine, cần thêm tích hợp `spring-shell-jline` hoặc starter phù hợp.

Điều này ảnh hưởng tới history: `History` dựa trên JLine là chức năng của tích hợp JLine. Khi chuyển từ 3.x sang 4.x, không nên giả định rằng chỉ có `spring-shell-core` là đủ để có tệp history giống ứng dụng 3.3.x.

Một số package API cũng được chuyển:

| API | Spring Shell 3.3.x | Spring Shell 4.x |
| --- | --- | --- |
| `UserConfigPathProvider` | `org.springframework.shell.config.UserConfigPathProvider` | `org.springframework.shell.core.config.UserConfigPathProvider` |
| `SpringShellProperties` | `org.springframework.shell.boot.SpringShellProperties` | `org.springframework.shell.core.autoconfigure.SpringShellProperties` |
| JLine history command | `org.springframework.shell.standard.commands.History` | `org.springframework.shell.jline.command.History` trong tích hợp JLine. |

Trước khi chuyển phiên bản, kiểm tra dependency tree để biết JLine có được đưa vào hay không, sau đó kiểm tra lại vị trí history và quyền truy cập trên máy đích. Không dựa vào import 3.3.x khi viết code cho 4.x.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| History xuất hiện ở thư mục khác nhau sau mỗi lần chạy | Mặc định location phụ thuộc working directory. | Đặt `spring.shell.config.location` hoặc dùng `{userconfig}`. |
| Không ghi được history khi chạy từ thư mục cài đặt | Thư mục hiện tại không có quyền ghi. | Chuyển sang user config directory hoặc một thư mục writable. |
| Tưởng `spring.config.location` đổi vị trí history | Nhầm property của Spring Boot với property của Spring Shell. | Dùng `spring.shell.config.location` cho dữ liệu shell. |
| Tệp history có tên không mong muốn | Tên mặc định được suy ra từ `spring.application.name` hoặc fallback. | Đặt rõ `spring.shell.history.name`. |
| Không thấy command `history` | `spring.shell.command.history.enabled=false` hoặc command đã bị thay thế. | Kiểm tra command registry và cấu hình command. |
| Vẫn có tệp history dù đã ẩn command | Chỉ tắt `spring.shell.command.history.enabled`. | Tắt persistence bằng `spring.shell.history.enabled=false`. |
| Placeholder `{userconfig}` không được thay bằng đường dẫn mong muốn | Provider mặc định hoặc cấu hình location không đúng. | Kiểm tra `UserConfigPathProvider.provide()` và `spring.shell.config.location`. |
| Biến môi trường không được sử dụng | `spring.shell.config.env` không trỏ tới đúng tên biến hoặc biến chưa được thiết lập trước khi khởi chạy. | Kiểm tra tên biến và giá trị trong process environment. |
| Script không tìm thấy file | Đường dẫn tương đối được phân giải theo working directory khác dự kiến. | Hiển thị `user.dir`, dùng đường dẫn tuyệt đối hoặc chuẩn hóa workspace. |
| Không inject được `UserConfigPathProvider` | Auto-configuration không được kích hoạt hoặc ứng dụng đã loại trừ cấu hình đó. | Kiểm tra starter/auto-configuration hoặc đăng ký bean provider tường minh. |
| Spring Shell 4.x không có history như bản 3.x | Chỉ có core console, chưa thêm JLine integration. | Thêm `spring-shell-jline` phù hợp nếu cần history của JLine. |

## Checklist trước khi phát hành

- [ ] Đã xác định working directory khi ứng dụng được khởi chạy.
- [ ] Đã phân biệt working directory, user home và user config directory.
- [ ] Đã chọn vị trí history không phụ thuộc thư mục cài đặt chỉ đọc.
- [ ] Đã cấu hình `spring.shell.history.name` nếu cần tên ổn định.
- [ ] Đã quyết định có lưu history hay không.
- [ ] Đã phân biệt `spring.shell.history.enabled` với `spring.shell.command.history.enabled`.
- [ ] Đã kiểm tra `{userconfig}` và `UserConfigPathProvider`.
- [ ] Đã xác nhận biến môi trường nếu dùng `spring.shell.config.env`.
- [ ] Đã phân biệt `spring.shell.config.location` với `spring.config.location`.
- [ ] Đã kiểm tra quyền đọc/ghi và chính sách retention cho history.
- [ ] Không để password hoặc token trong command line history.
- [ ] Đã rà soát tệp history trước khi export hoặc chạy lại bằng `script`.
- [ ] Khi dùng Spring Shell 4.x, đã kiểm tra JLine integration và package API mới.

## Ghi nhớ

Working directory là thư mục của tiến trình lúc khởi chạy và quyết định cách phân giải đường dẫn tương đối. Spring Shell 3.3.x lưu history mặc định trong working directory; tên tệp được suy ra từ `spring.application.name` hoặc dùng `spring-shell.log`, có thể đổi bằng `spring.shell.history.name`. Dùng `spring.shell.config.location` để chọn thư mục lưu và `{userconfig}` để dựa vào `UserConfigPathProvider`. `spring.shell.history.enabled` điều khiển lưu tệp; `spring.shell.command.history.enabled` điều khiển command hiển thị. Tệp history có thể chứa lệnh nhạy cảm và có thể được xuất thành script, vì vậy cần bảo vệ quyền truy cập và không truyền secret qua argument. Khi chuyển sang Spring Shell 4.x, kiểm tra JLine integration vì core không còn phụ thuộc JLine mặc định.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — History](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html): cấu hình bật/tắt history, tên log file, working directory và placeholder `{userconfig}`.
- [Spring Shell 3.3.0 API — `UserConfigPathProvider`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/config/UserConfigPathProvider.html): interface cung cấp user configuration path.
- [Spring Shell 3.3.0 API — `SpringShellProperties.Config`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/SpringShellProperties.Config.html): thuộc tính `env` và `location`.
- [Spring Shell 3.3.0 API — `SpringShellProperties.History`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/SpringShellProperties.History.html): thuộc tính bật/tắt và tên history.
- [Spring Shell 3.3.0 API — `History`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.html): xem hoặc ghi lịch sử đã chạy ra tệp.
- [Spring Shell 3.3.0 API — `History.Command`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.Command.html): cách tắt command history khỏi command registry.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): vị trí file cấu hình ứng dụng và ý nghĩa của `spring.config.location`.
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi module JLine, console mặc định và package API khi nâng cấp.
- [Spring Shell 4.0.4 API — `UserConfigPathProvider`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/config/UserConfigPathProvider.html): package và interface provider ở dòng 4.x.

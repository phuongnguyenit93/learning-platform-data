# Lệnh script và phạm vi thực thi tệp lệnh

Spring Shell cho phép lưu nhiều command vào một tệp rồi chạy lần lượt. Cách này hữu ích khi cần chuẩn bị môi trường, thực hiện một quy trình quản trị lặp lại hoặc chạy một chuỗi thao tác tự động. Tuy nhiên, cần phân biệt hai cách chạy tệp: gọi built-in command `script --file` trong một shell đang hoạt động, và truyền `@file` khi khởi động ứng dụng để dùng runner không tương tác.

Hai cách cùng đọc các dòng command của Spring Shell nhưng có điểm bắt đầu và phạm vi phiên khác nhau. `script --file` chạy bên trong phiên shell hiện tại; `@file` yêu cầu ứng dụng chạy tệp lệnh trong chế độ non-interactive rồi kết thúc. Cả hai đều dùng command đã đăng ký trong ứng dụng, không phải một ngôn ngữ shell tổng quát như Bash hoặc PowerShell.

Bài này sử dụng cú pháp và tài liệu Spring Shell 4.0.4.

## 1. Tệp script của Spring Shell là gì?

Tệp script là một tệp văn bản chứa các command Spring Shell, mỗi dòng là một command. Spring Shell đọc từng dòng và thực thi theo thứ tự xuất hiện trong tệp. Dòng chú thích bắt đầu bằng `//` được bỏ qua.

Ví dụ `setup.shell`:

```text
// Chuẩn bị môi trường kiểm thử
config set environment staging
remote connect --endpoint https://staging.example.com
user list --status ACTIVE
report export --format csv --output ./reports/active-users.csv
```

Các command `config`, `remote`, `user` và `report` trong ví dụ là command do ứng dụng cung cấp. Spring Shell không tự tạo các command nghiệp vụ này; chúng phải được đăng ký trong `CommandRegistry` trước khi script gọi chúng.

Tệp script không phải một chương trình Bash hay PowerShell. Mỗi dòng được phân tích theo cú pháp command của Spring Shell. Không mặc định rằng các cấu trúc như `if`, `for`, biến môi trường, pipe (`|`), chuyển hướng (`>`) hoặc lệnh hệ điều hành sẽ hoạt động trong tệp. Nếu cần logic điều kiện hoặc vòng lặp, hãy đặt logic đó trong command/service Java hoặc dùng một công cụ điều phối bên ngoài để gọi ứng dụng.

## 2. Chạy tệp bằng built-in command `script --file`

Khi đã ở prompt Spring Shell, gọi built-in command `script` với option `--file`:

```text
shell:>script --file /absolute/path/to/setup.shell
```

`--file` là option chỉ vị trí tệp script. Cú pháp của Spring Shell 4.0.4 chấp nhận:

- Đường dẫn tuyệt đối trên filesystem.
- Spring resource reference như `file:`.
- Tài nguyên nằm trong classpath bằng `classpath:`.

Ví dụ:

```text
script --file /opt/admin-cli/scripts/setup.shell
script --file file:/opt/admin-cli/scripts/setup.shell
script --file classpath:scripts/setup.shell
```

Khi dùng classpath reference, tệp cần được đóng gói trong classpath runtime của ứng dụng, ví dụ `src/main/resources/scripts/setup.shell` trong dự án Maven hoặc Gradle. Cách này phù hợp với script mẫu đi kèm ứng dụng và không phụ thuộc vào thư mục làm việc hiện tại của người chạy.

Với đường dẫn filesystem, hãy cung cấp đường dẫn rõ ràng để tránh nhầm working directory. Nếu đường dẫn có khoảng trắng, đặt toàn bộ giá trị trong dấu nháy theo quy tắc parser:

```text
script --file "/opt/admin cli/scripts/setup.shell"
```

Không truyền tên tệp như một positional argument trần. Cú pháp hiện tại là `script --file <location>`.

## 3. Nội dung và thứ tự thực thi

Spring Shell thực thi các command theo thứ tự dòng trong tệp. Ví dụ:

```text
// Bước 1: chọn môi trường
config set environment staging
// Bước 2: xác thực với hệ thống
remote login --profile staging
// Bước 3: kiểm tra trạng thái
remote status
// Bước 4: xuất báo cáo
report export --format json --output ./reports/staging.json
```

Command ở dòng sau có thể phụ thuộc vào trạng thái được tạo bởi dòng trước. Vì thế, hãy đặt các thao tác theo trình tự nghiệp vụ: cấu hình trước, kết nối hoặc xác thực tiếp theo, rồi mới thực hiện thao tác cần kết nối.

Các dòng chú thích bắt đầu bằng `//`:

```text
// Đây là dòng chú thích
user list
```

Không nên tự thay `//` bằng cú pháp chú thích của ngôn ngữ khác như `#` hoặc `REM`; tài liệu Spring Shell mô tả `//` là ký hiệu chú thích trong tệp script.

Để giảm rủi ro, mỗi dòng nên chứa một command hoàn chỉnh. Với giá trị có khoảng trắng, dùng dấu nháy theo cú pháp command:

```text
user create --name "Nguyen Minh An" --email an@example.com
```

Nếu cần nhiều thao tác trong một command, hãy thiết kế command nhận các argument/option phù hợp thay vì ghép nhiều lệnh hệ điều hành vào cùng dòng.

## 4. Phạm vi thực thi của `script --file`

Built-in command `script --file` được gọi từ shell đang hoạt động. Nó đọc tệp và gửi từng dòng qua cơ chế phân tích, tra cứu và thực thi command của Spring Shell. Nó không tạo một JVM mới và cũng không tạo một application context Spring mới cho từng dòng.

Điều này có một số hệ quả:

- Các command trong script dùng cùng command registry của ứng dụng hiện tại.
- Các command tiếp tục dùng những Spring bean đã được khởi tạo trong application context hiện tại.
- Singleton bean vẫn là cùng instance; state được command trước cập nhật có thể được command sau đọc.
- Kết nối, cấu hình trong bộ nhớ và các thay đổi trạng thái trong tiến trình tiếp tục tồn tại sau khi script kết thúc, miễn là ứng dụng vẫn chạy.
- Tác động đã ghi ra filesystem, database hoặc hệ thống từ xa không tự được hoàn tác chỉ vì script kết thúc hoặc một dòng sau gặp lỗi.

Ví dụ, nếu `remote login` cập nhật state của một singleton `RemoteSessionState`, command `remote status` ở dòng kế tiếp có thể đọc trạng thái đã cập nhật. Đây là cùng application context và cùng registry, không phải một phiên ứng dụng độc lập cho từng dòng script.

Script không tạo transaction chung bao quanh toàn bộ tệp. Nếu dòng đầu cập nhật database thành công và dòng thứ hai thất bại, ứng dụng không tự động rollback dòng đầu chỉ vì cả hai nằm trong một file. Nếu quy trình cần tính nguyên tử, hãy triển khai transaction ở service nghiệp vụ cho một thao tác phù hợp hoặc thiết kế bước bù trừ rõ ràng.

## 5. Chạy tệp bằng `@file` khi khởi động ứng dụng

Spring Shell 4 có `NonInteractiveShellRunner` để chạy command mà không mở prompt. Runner này có thể nhận một command đơn hoặc một tệp script. Để chỉ định tệp, thêm ký tự `@` trước tên file trong đối số khởi động:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  @/opt/admin-cli/scripts/setup.shell
```

Trong ví dụ này:

- `spring.shell.interactive.enabled=false` chọn chế độ non-interactive.
- `@/opt/admin-cli/scripts/setup.shell` yêu cầu runner đọc và thực thi tệp script.
- Ứng dụng chạy command theo thứ tự trong tệp rồi kết thúc quá trình chạy shell.

Với Spring Shell 4, interactive mode được bật mặc định. Nếu mục tiêu là automation và chạy script từ đối số tiến trình, hãy cấu hình rõ `spring.shell.interactive.enabled=false` thay vì giả định chỉ cần có command-line arguments là ứng dụng tự thoát sau khi chạy.

Có thể đặt thuộc tính trong `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó gọi:

```bash
java -jar target/admin-cli.jar @/opt/admin-cli/scripts/setup.shell
```

Khi dùng PowerShell hoặc một shell hệ điều hành khác, cần bảo đảm đối số bắt đầu bằng `@` được truyền nguyên vẹn cho JVM. Nếu shell ngoài diễn giải ký tự đó, hãy đặt đối số trong dấu nháy theo quy tắc của shell ngoài.

## 6. So sánh hai cách chạy script

| Tiêu chí | `script --file` | `@file` |
|---|---|---|
| Điểm bắt đầu | Người dùng gọi command trong prompt đang mở | Người gọi truyền file lúc khởi động ứng dụng |
| Runner/mode | Shell tương tác hiện tại | `NonInteractiveShellRunner` |
| Tệp được chỉ định | Option `--file` | Ký tự `@` trước tên file trong process arguments |
| Resource reference | Hỗ trợ filesystem path, `file:` và `classpath:` trong Spring Shell 4.0.4 | API runner mô tả tên file với tiền tố `@`; không mặc định áp dụng cú pháp resource reference của `script --file` |
| Sau khi chạy xong | Trở về prompt của phiên hiện tại | Hoàn tất shell run và ứng dụng kết thúc theo vòng đời tiến trình |
| Trường hợp phù hợp | Người dùng đang thao tác và muốn chạy một chuỗi lệnh | CI/CD, automation, tác vụ batch hoặc chạy theo lịch |

Hai cách dùng chung command model và application context của lần chạy tương ứng. Khác biệt chính là cách bắt đầu và cách kết thúc phiên.

## 7. Đóng gói script trong classpath

Spring Shell 4.0.4 bổ sung khả năng cho built-in `script` nhận classpath reference. Đặt file dưới `src/main/resources`:

```text
src/main/resources/
└── scripts/
    └── bootstrap.shell
```

Nội dung `bootstrap.shell`:

```text
// Khởi tạo cấu hình mặc định
config set environment local
user list
```

Sau khi build ứng dụng, gọi trong prompt:

```text
script --file classpath:scripts/bootstrap.shell
```

Tệp trong classpath phù hợp với quy trình được phân phối cùng ứng dụng. Nếu người vận hành cần sửa nội dung mà không build lại JAR, dùng tệp ngoài filesystem và truyền đường dẫn `file:` hoặc đường dẫn tuyệt đối.

Lưu ý: tính năng classpath reference được release note Spring Shell 4.0.4 nêu cho built-in `script` command. Không tự suy luận rằng `@classpath:scripts/bootstrap.shell` được hỗ trợ bởi cú pháp `@file`; hãy dùng đúng cơ chế được tài liệu cho từng runner mô tả.

## 8. Working directory và đường dẫn tương đối

Đường dẫn tương đối phụ thuộc working directory của tiến trình hoặc cách resource được phân giải. Hai lần chạy cùng một JAR từ hai thư mục khác nhau có thể đọc hai tệp khác nhau nếu dùng tên file tương đối.

Để tránh nhầm lẫn:

1. Dùng đường dẫn tuyệt đối hoặc Spring resource reference rõ ràng cho `script --file`.
2. Với command bên trong script có nhận đường dẫn file, xác định rõ đường dẫn đó được tính từ working directory nào.
3. Trong CI, đặt working directory một cách tường minh trước khi chạy JAR.
4. Không giả định thư mục chứa JAR cũng là working directory.
5. Ghi log đường dẫn đã resolve khi command đọc hoặc ghi file.

Ví dụ, script có dòng:

```text
report export --output ./reports/daily.csv
```

Đường dẫn `./reports/daily.csv` được command xử lý theo working directory mà ứng dụng nhìn thấy. Nếu cần luôn ghi vào một vị trí cố định, truyền đường dẫn tuyệt đối hoặc cấu hình thư mục gốc trong ứng dụng.

## 9. Xử lý lỗi và kết quả của script

Tệp script chỉ xác định danh sách và thứ tự command. Mỗi command vẫn có thể thành công, trả `ExitStatus` không thành công hoặc phát sinh exception. Spring Shell cung cấp `ExitStatusExceptionMapper` để ánh xạ exception thành mã và mô tả phù hợp.

Không nên mặc định rằng mọi lỗi ở một dòng đều có cùng chính sách dừng hoặc tiếp tục cho mọi cấu hình. Tài liệu script mô tả thứ tự thực thi nhưng không định nghĩa đầy đủ một chính sách fail-fast chung cho mọi loại lỗi. Hãy kiểm tra hành vi của phiên bản đang dùng bằng một script có chủ ý tạo lỗi ở giữa.

Với automation, nên thiết kế command có đầu ra và trạng thái rõ ràng:

- Xác thực input trước khi thực hiện side effect.
- Trả `ExitStatus` có ý nghĩa cho trường hợp thành công hoặc thất bại nghiệp vụ.
- Ánh xạ exception đã biết sang thông báo và exit status phù hợp.
- Không nuốt lỗi rồi trả thành công nếu bước đó ảnh hưởng các bước tiếp theo.
- Kiểm thử mã thoát của tiến trình thực tế trong CI, không chỉ kiểm tra output trên terminal.

Ví dụ cấu hình mapper có thể ánh xạ lỗi nghiệp vụ sang lỗi thực thi:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class DeploymentCommands {

    @Command(name = "deploy run", exitStatusExceptionMapper = "deploymentExitMapper")
    public String run() {
        // Thực hiện triển khai; ném exception nếu nghiệp vụ thất bại.
        return "Deployment completed";
    }
}

```

Đăng ký mapper thành Spring bean và tham chiếu bean bằng tên trong `@Command`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
class ShellErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper deploymentExitMapper() {
        return exception -> new ExitStatus(
                20,
                "Không thể thực hiện command: " + exception.getMessage());
    }
}
```

Mã `20` trong ví dụ là quy ước của ứng dụng; hãy định nghĩa bảng exit code ổn định để script bên ngoài có thể xử lý. Không đưa password, token hoặc thông tin bí mật vào thông báo lỗi.

## 10. Thiết kế script an toàn và có thể chạy lại

Một script có thể tạo dữ liệu, cập nhật cấu hình, gửi request hoặc xóa tài nguyên. Trước khi dùng cho production:

- **Xác định môi trường:** command nên yêu cầu hoặc hiển thị rõ môi trường đích.
- **Kiểm tra trước:** xác minh quyền, trạng thái kết nối và điều kiện nghiệp vụ trước khi thay đổi dữ liệu.
- **Giảm tác dụng phụ lặp lại:** thiết kế command idempotent nếu quy trình có thể được chạy lại sau lỗi.
- **Không lưu bí mật trong file:** lấy token hoặc password từ secret store hoặc cơ chế cấu hình an toàn.
- **Giới hạn quyền:** chỉ cấp cho tiến trình những quyền filesystem và dịch vụ cần thiết.
- **Ghi nhận kết quả:** log bước đang chạy, kết quả và định danh tác vụ; tránh ghi dữ liệu nhạy cảm.
- **Có phương án khôi phục:** xác định cách xử lý khi một bước giữa script thất bại sau khi các bước trước đã hoàn tất.

Không nên đặt lệnh phá hủy như xóa dữ liệu hoặc reset môi trường vào script tự động mà không có kiểm tra đích và quyền rõ ràng. Có thể thêm command `plan` hoặc `--dry-run` để hiển thị hành động dự kiến trước khi thực hiện thật.

## 11. Kiểm thử script

Hãy kiểm tra cả nội dung file lẫn cách chạy:

1. **Kiểm tra command tồn tại:** mọi tên command trong file phải được đăng ký trong ứng dụng.
2. **Kiểm tra thứ tự:** xác nhận các bước phụ thuộc được sắp xếp đúng.
3. **Kiểm tra tham số:** thử giá trị có khoảng trắng, option bắt buộc, default và kiểu dữ liệu.
4. **Kiểm tra chú thích:** dùng `//` và xác nhận dòng chú thích không được thực thi như command.
5. **Kiểm tra nguồn file:** thử đường dẫn filesystem, `file:` và `classpath:` với built-in `script`.
6. **Kiểm tra lỗi giữa chừng:** cố ý tạo một command thất bại, quan sát các dòng sau và ghi lại exit status.
7. **Kiểm tra state:** xác nhận state bean được chia sẻ trong cùng lần chạy và các tác động bên ngoài được ghi nhận đúng.
8. **Kiểm tra automation:** chạy bằng `@file` trong non-interactive mode, xác nhận tiến trình kết thúc và mã thoát phù hợp.
9. **Kiểm tra working directory:** chạy từ một thư mục khác để phát hiện đường dẫn tương đối bị phụ thuộc môi trường.

Không chỉ chạy script trên máy phát triển. Hãy chạy bằng JAR đã đóng gói trong môi trường gần production, với cùng cấu hình, quyền và working directory dự kiến.

## 12. Bài tập thực hành

Xây dựng script triển khai một ứng dụng mẫu lên môi trường staging. Ứng dụng có các command `config set`, `remote login`, `remote status`, `artifact verify` và `deploy run`.

Hãy thực hiện:

1. Tạo `deploy-staging.shell` với một command trên mỗi dòng.
2. Thêm chú thích `//` giải thích mục đích từng bước.
3. Sắp xếp bước cấu hình, đăng nhập, kiểm tra artifact rồi triển khai.
4. Chạy script bằng `script --file /absolute/path/to/deploy-staging.shell` trong interactive shell.
5. Đưa một bản script mẫu vào `src/main/resources/scripts` và chạy bằng `script --file classpath:scripts/deploy-staging.shell`.
6. Tắt interactive mode và chạy script bằng đối số `@file` khi khởi động JAR.
7. Cố ý làm `artifact verify` thất bại, quan sát cách phiên bản đang dùng xử lý các dòng tiếp theo và exit code.
8. Chạy lại script sau khi sửa lỗi; xác nhận command không tạo dữ liệu trùng hoặc triển khai lặp ngoài ý muốn.
9. Chạy từ working directory khác và kiểm tra mọi đường dẫn đầu vào/đầu ra.

**Kết quả cần nộp:** hai cách gọi script, nội dung tệp, log thứ tự command, kết quả kiểm thử lỗi và mã thoát, cùng ghi chú về working directory và side effect.

## 13. Checklist trước khi đưa script vào sử dụng

- [ ] Đã chọn đúng cách chạy: `script --file` hay `@file`.
- [ ] Tệp chứa command Spring Shell, một command trên mỗi dòng.
- [ ] Chú thích dùng `//`.
- [ ] Tất cả command đã được đăng ký trong ứng dụng.
- [ ] Đường dẫn tệp được phân giải rõ ràng; classpath resource đã được đóng gói nếu dùng `classpath:`.
- [ ] Đã xác định working directory cho đường dẫn tương đối trong các command.
- [ ] Đã hiểu các command dùng chung application context và bean state của lần chạy.
- [ ] Đã xác định cách xử lý lỗi giữa các dòng và kiểm tra exit code.
- [ ] Command quan trọng có thể chạy lại an toàn hoặc có phương án bù trừ.
- [ ] Không lưu bí mật trong script hoặc log.
- [ ] Đã kiểm thử bằng JAR và cấu hình gần production.

## Tài liệu tham khảo

- [Spring Shell Reference — Script](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell Reference — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell API — `NonInteractiveShellRunner`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell Reference — Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Spring Shell Releases — v4.0.4](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

# Tránh chờ prompt tương tác trong chế độ tự động

Một CLI chạy trong CI/CD, cron job hoặc script hệ điều hành cần nhận đủ dữ liệu từ đối số, cấu hình hoặc biến môi trường rồi thực thi và kết thúc. Nếu ứng dụng vẫn khởi động vòng lặp nhập lệnh hoặc chờ câu trả lời từ terminal, job tự động có thể bị treo, hết thời gian chờ hoặc không hoàn thành.

Trong Spring Shell, cần cấu hình runner phù hợp và thiết kế command để không yêu cầu nhập tương tác khi chạy tự động. Từ Spring Shell 3.3, `InteractiveShellRunner` bị tắt mặc định, còn `NonInteractiveShellRunner` được bật mặc định. Tuy nhiên, nên đặt property tường minh theo môi trường để hành vi không phụ thuộc vào cấu hình mặc định của phiên bản hoặc profile khác.

Bài học tập trung vào cách ngăn REPL và prompt chặn tiến trình automation, cách cung cấp đủ đầu vào cho command, cấu hình riêng cho CI và kiểm thử ứng dụng khi không có terminal tương tác.

## 1. Vì sao tiến trình tự động có thể bị chờ?

Trong một phiên terminal trực tiếp, prompt là cách giao tiếp tự nhiên: ứng dụng hỏi thông tin còn thiếu và người dùng trả lời. Trong CI/CD hoặc cron job, thường không có người ngồi trước terminal để trả lời.

Các tình huống có thể làm tiến trình chờ:

- `InteractiveShellRunner` được bật và mở REPL khi ứng dụng không nhận command một lần.
- Command gọi API đọc dòng từ terminal hoặc hiển thị prompt để hỏi giá trị còn thiếu.
- Luồng nghiệp vụ chờ xác nhận như “Bạn có chắc muốn xóa?”.
- Script chạy command cần thông tin mà command không nhận qua option hoặc cấu hình.
- Test khởi động shell tương tác trong môi trường không có terminal.

Điều cần xử lý ở đây có hai lớp:

1. **Chế độ chạy của ứng dụng:** chọn runner không tương tác và tắt runner tương tác trong môi trường tự động.
2. **Thiết kế command:** không yêu cầu nhập liệu hoặc xác nhận trực tiếp từ terminal; mọi dữ liệu cần thiết phải được cung cấp trước khi command chạy.

Chỉ tắt interactive runner chưa đủ nếu chính code nghiệp vụ vẫn gọi prompt hoặc đọc stdin.

## 2. Cấu hình runner không tương tác

Spring Shell cung cấp ba property điều khiển runner:

| Property | Runner | Mục đích |
|---|---|---|
| `spring.shell.interactive.enabled` | `InteractiveShellRunner` | Bật/tắt REPL |
| `spring.shell.noninteractive.enabled` | `NonInteractiveShellRunner` | Bật/tắt thực thi command từ đối số khởi chạy |
| `spring.shell.script.enabled` | `ScriptShellRunner` | Bật/tắt thực thi file script có tiền tố `@` |

Với Spring Shell 3.3.x, giá trị mặc định là:

| Runner | Mặc định |
|---|---:|
| Interactive | `false` |
| Non-interactive | `true` |
| Script | `false` |

Ở các phiên bản đến 3.2.x, cả ba runner được bật mặc định. Vì vậy, cấu hình explicit đặc biệt hữu ích khi ứng dụng cần hỗ trợ nhiều phiên bản hoặc đang nâng cấp.

### 2.1. Cấu hình cho command chạy một lần

Trong môi trường automation chỉ gọi command qua tham số khởi chạy, có thể dùng:

```yaml
# application-ci.yml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Cấu hình này thể hiện rõ:

- Không mở REPL.
- Cho phép nhận command từ đối số tiến trình.
- Không bật script runner nếu job không chạy file script.

Ví dụ gọi một command:

```bash
java -jar project-cli.jar report export --format=json --output=report.json
```

Ứng dụng nhận command, thực thi rồi kết thúc. Không có bước hỏi người dùng tiếp theo.

Nếu ứng dụng dùng file script, đặt `spring.shell.script.enabled=true` thay vì tắt script runner.

### 2.2. Cấu hình bằng application.properties

Có thể dùng dạng key-value tương ứng:

```properties
spring.shell.interactive.enabled=false
spring.shell.noninteractive.enabled=true
spring.shell.script.enabled=false
```

Nên giữ cấu hình automation trong profile riêng, ví dụ `ci`, `batch` hoặc `production-cli`, để tránh vô tình bật prompt trong job chạy nền.

## 3. Tách cấu hình theo môi trường

Một ứng dụng có thể cần prompt khi kỹ sư chạy local nhưng phải chạy không tương tác trong CI. Hãy dùng profile để thể hiện rõ mục đích của từng môi trường.

Cấu hình mặc định cho local có thể bật interactive:

```yaml
# application.yml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Cấu hình CI ghi đè interactive:

```yaml
# application-ci.yml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Khi kích hoạt profile `ci`, các property trong profile này ghi đè cấu hình tương ứng:

```bash
java -jar project-cli.jar --spring.profiles.active=ci report export --format=json
```

Với pipeline, có thể đặt profile bằng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=ci java -jar project-cli.jar report export --format=json
```

Nếu pipeline gọi ứng dụng qua một wrapper script, hãy đặt profile và property ở một vị trí thống nhất để mọi job dùng cùng quy tắc.

## 4. Ghi đè bằng biến môi trường

Spring Boot hỗ trợ relaxed binding cho property. Dạng biến môi trường của ba thuộc tính runner là:

| Property | Biến môi trường |
|---|---|
| `spring.shell.interactive.enabled` | `SPRING_SHELL_INTERACTIVE_ENABLED` |
| `spring.shell.noninteractive.enabled` | `SPRING_SHELL_NONINTERACTIVE_ENABLED` |
| `spring.shell.script.enabled` | `SPRING_SHELL_SCRIPT_ENABLED` |

Ví dụ trên Linux hoặc macOS:

```bash
SPRING_SHELL_INTERACTIVE_ENABLED=false \
SPRING_SHELL_NONINTERACTIVE_ENABLED=true \
SPRING_SHELL_SCRIPT_ENABLED=false \
java -jar project-cli.jar report export --format=json
```

Ví dụ trên Windows PowerShell:

```powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
$env:SPRING_SHELL_NONINTERACTIVE_ENABLED = "true"
$env:SPRING_SHELL_SCRIPT_ENABLED = "false"

java -jar .\project-cli.jar report export --format=json
```

Biến môi trường phù hợp khi hệ thống CI quản lý cấu hình qua secret, variable hoặc job environment. Các giá trị này cần được đặt trong đúng job hoặc container chạy CLI; không giả định biến đã được truyền sang tiến trình con nếu runner CI không cấu hình điều đó.

## 5. Cung cấp đủ dữ liệu qua option và argument

Một command tự động nên nhận mọi dữ liệu bắt buộc từ option hoặc argument. Không nên đợi đến lúc thực thi mới hỏi người dùng nhập giá trị còn thiếu.

Ví dụ command xuất báo cáo:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(
        command = "report export",
        description = "Xuất báo cáo theo định dạng được chọn"
    )
    public String export(
            @Option(longName = "format", required = true)
            String format,
            @Option(longName = "output", required = true)
            String output) {

        // Gọi application service để tạo file báo cáo.
        return "Exported " + format + " report to " + output;
    }
}
```

Lệnh gọi trong automation:

```bash
java -jar project-cli.jar report export --format=json --output=report.json
```

Nếu thiếu option bắt buộc, parser hoặc binding có thể trả lỗi trước khi phương thức được gọi. Đây là hành vi phù hợp cho automation: job nhận lỗi rõ ràng và có thể dừng thay vì chờ người dùng nhập dữ liệu.

Với giá trị có thể có mặc định an toàn, khai báo default value rõ ràng. Với giá trị cần quyết định theo từng lần chạy, đánh dấu required và buộc caller cung cấp.

Không dùng một giá trị mặc định tùy tiện cho dữ liệu quan trọng như môi trường triển khai, mã tài khoản hoặc đường dẫn đích. Mặc định sai có thể khiến job thực hiện thao tác trên nhầm tài nguyên.

## 6. Tránh prompt và đọc terminal bên trong command

Tắt `InteractiveShellRunner` chỉ ngăn shell mở REPL. Nó không tự động vô hiệu hóa mọi đoạn code có thể đọc input.

Ví dụ cần tránh trong command được dùng bởi automation:

```java
public void deleteProject(String projectId) {
    System.out.print("Bạn có chắc muốn xóa? (y/n): ");
    // Đọc câu trả lời từ terminal...
}
```

Trong CI, không có người dùng trả lời câu hỏi này. Tiến trình có thể chờ mãi, nhận EOF hoặc thất bại tùy cách đọc input và môi trường.

Thay vào đó, đưa quyết định vào option tường minh:

```text
project delete --id=42 --confirm
```

Command có thể yêu cầu `--confirm` đối với thao tác phá hủy dữ liệu. Nếu thiếu cờ xác nhận, trả lỗi và kết thúc:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;

@Command(command = "project delete")
public String delete(
        @Option(longName = "id", required = true) String id,
        @Option(longName = "confirm", defaultValue = "false") boolean confirm) {

    if (!confirm) {
        throw new IllegalArgumentException(
            "Thao tác xóa yêu cầu cung cấp --confirm"
        );
    }

    // Gọi service xóa project.
    return "Deleted project " + id;
}
```

Ở phiên terminal trực tiếp, có thể cung cấp một command tương tác riêng để hỏi xác nhận. Với automation, caller phải truyền `--confirm` rõ ràng. Cách này giúp log và script thể hiện chính xác quyết định đã được đưa ra.

Không nên tự động coi việc không có stdin là đồng ý. Nếu thiếu xác nhận, hãy dừng thao tác.

## 7. Không dùng prompt nhiều bước trong luồng tự động

Một số CLI có wizard nhiều bước để thu thập thông tin, chọn cấu hình hoặc xác nhận thao tác. Wizard hữu ích cho người dùng mới nhưng khó phù hợp với automation.

Ví dụ một luồng tương tác có thể hỏi:

1. Chọn môi trường.
2. Chọn project.
3. Chọn định dạng.
4. Xác nhận ghi đè file.

Đối với job tự động, chuyển các câu trả lời thành option tường minh:

```bash
java -jar project-cli.jar deploy \
  --environment=staging \
  --project=payments \
  --format=zip \
  --overwrite=false
```

Các option có tên giúp người đọc script hiểu job sẽ làm gì. Khi thêm một trường bắt buộc mới, command nên báo lỗi nếu caller chưa cung cấp thay vì tự chuyển sang wizard.

Nếu cần hỗ trợ cả wizard và automation, hãy tách phần thu thập dữ liệu khỏi phần nghiệp vụ:

- Luồng interactive hỏi người dùng và tạo một request có cấu trúc.
- Luồng non-interactive nhận request từ option, argument hoặc file cấu hình.
- Cả hai gọi cùng application service để thực hiện nghiệp vụ.

Nhờ vậy, logic deploy hoặc export không phụ thuộc vào terminal.

## 8. Chạy file script mà không mở prompt

Nếu cần chạy nhiều command theo thứ tự, có thể dùng `ScriptShellRunner`. Script runner nhận đối số có tiền tố `@` và đọc command từ file.

Ví dụ file `release.shell`:

```text
project validate --id=42
project export --id=42 --format=json --output=project-42.json
project publish --id=42 --confirm
```

Bật script runner và giữ interactive tắt:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Chạy script:

```bash
java -jar project-cli.jar @release.shell
```

Mỗi dòng script cần chứa đủ option và argument để command chạy mà không hỏi thêm dữ liệu. Nếu một command trong script yêu cầu prompt, toàn bộ tiến trình vẫn có thể bị chặn dù interactive runner đã tắt.

Khi dùng script trong pipeline, hãy kiểm tra hành vi của phiên bản Spring Shell đang triển khai đối với lỗi giữa chừng, thứ tự thực thi và mã thoát. Nếu job cần dừng ngay khi một bước thất bại, hãy xác nhận chính sách đó bằng kiểm thử tích hợp hoặc điều phối các command riêng trong script CI.

## 9. Phân biệt runner với InteractionMode

`spring.shell.interactive.enabled` bật hoặc tắt runner mở REPL. `InteractionMode` là một cơ chế ở cấp command trong mô hình annotation legacy, quyết định command đó được phép chạy trong chế độ nào.

| Cơ chế | Phạm vi | Vai trò |
|---|---|---|
| `spring.shell.interactive.enabled` | Toàn ứng dụng | Bật/tắt interactive runner |
| `spring.shell.noninteractive.enabled` | Toàn ứng dụng | Bật/tắt runner xử lý command một lần |
| `@ShellMethod(interactionMode = ...)` | Một command legacy | Giới hạn command theo chế độ tương tác |
| Prompt hoặc đọc stdin trong code | Phần triển khai command | Có thể chờ input bất kể runner nào đã mở shell |

Không dùng `InteractionMode` để thay thế property runner. Cũng không giả định rằng command được đánh dấu non-interactive sẽ tự động không gọi prompt; phần triển khai command vẫn phải tuân theo hợp đồng không tương tác.

Khi dùng annotation declarative mới, kiểm tra API của đúng phiên bản Spring Shell trước khi áp dụng annotation hoặc thuộc tính lấy từ mô hình legacy.

## 10. Kiểm thử để phát hiện prompt ngoài ý muốn

Nên kiểm tra command theo cả hai điều kiện: có terminal tương tác và không có terminal tương tác.

### 10.1. Kiểm thử ApplicationContext với interactive bị tắt

Trong test không cần REPL, đặt property tường minh:

```java
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.shell.interactive.enabled=false",
    "spring.shell.noninteractive.enabled=true",
    "spring.shell.script.enabled=false"
})
class ReportCommandsTests {
    // Kiểm thử service hoặc command theo test fixture của dự án.
}
```

Mục tiêu là bảo đảm test context không khởi chạy vòng lặp terminal ngoài ý muốn. Nếu test cần kiểm tra prompt thật, hãy dùng một test chuyên biệt có input giả lập và giới hạn thời gian rõ ràng.

### 10.2. Kiểm thử tiến trình trong môi trường không có TTY

Một kiểm thử tích hợp có thể chạy JAR như tiến trình con với stdin đóng hoặc không nối terminal. Kiểm tra các điểm:

- Command có đủ option thì hoàn thành.
- Thiếu option bắt buộc thì trả lỗi rõ ràng.
- Không xuất hiện prompt xác nhận hoặc wizard.
- Tiến trình kết thúc trong thời gian giới hạn.
- Exit code phản ánh kết quả thành công hoặc thất bại.
- Output và error output có thể được CI lưu lại.

Không chỉ kiểm tra rằng ứng dụng không in chuỗi `shell:>`; một command vẫn có thể chờ đọc stdin mà không hiển thị prompt. Hãy đặt timeout cho bài kiểm thử để phát hiện tiến trình bị treo.

### 10.3. Kiểm tra script và command trực tiếp riêng biệt

Nếu ứng dụng hỗ trợ cả non-interactive và script runner, kiểm thử hai đường chạy riêng:

```bash
java -jar project-cli.jar project list
java -jar project-cli.jar @smoke-test.shell
```

Không suy luận rằng command chạy được trực tiếp thì script cũng chắc chắn chạy được. Script có thêm bước đọc file, phân tích từng dòng và xử lý lỗi trong quá trình thực thi.

## 11. Checklist trước khi đưa CLI vào CI/CD

- [ ] Tắt `spring.shell.interactive.enabled` trong profile automation.
- [ ] Bật `spring.shell.noninteractive.enabled` nếu chạy command qua đối số.
- [ ] Chỉ bật `spring.shell.script.enabled` khi job thực sự dùng file script.
- [ ] Kiểm tra giá trị mặc định nếu ứng dụng hỗ trợ Spring Shell trước 3.3.
- [ ] Cung cấp mọi option và argument bắt buộc ngay trong lệnh gọi.
- [ ] Không gọi prompt, wizard hoặc đọc stdin trong command tự động.
- [ ] Dùng option xác nhận tường minh cho thao tác có tác động lớn.
- [ ] Không tự coi thiếu input là đồng ý.
- [ ] Tách logic nghiệp vụ khỏi giao diện nhập liệu.
- [ ] Kiểm tra tiến trình trong môi trường không có TTY.
- [ ] Đặt timeout cho job và bài kiểm thử tích hợp.
- [ ] Xác minh output, error output và exit code.
- [ ] Kiểm thử riêng command trực tiếp và file script.
- [ ] Ghi cấu hình runner vào profile hoặc biến môi trường được quản lý.

## 12. Các lỗi thường gặp

**Chỉ dựa vào mặc định của Spring Shell 3.3.** Môi trường cũ hoặc profile khác có thể bật interactive. Đặt property tường minh trong cấu hình CI.

**Tắt interactive nhưng command vẫn hỏi dữ liệu.** Runner không mở REPL nhưng code command vẫn có thể đọc stdin hoặc gọi prompt. Chuyển dữ liệu thành option, argument hoặc cấu hình.

**Thiếu option rồi tự chuyển sang wizard.** Automation không thể trả lời wizard. Báo lỗi đầu vào và kết thúc command.

**Bật script runner nhưng script gọi command tương tác.** `ScriptShellRunner` không biến command có prompt thành command không tương tác. Sửa command hoặc cung cấp một đường chạy phù hợp cho automation.

**Dùng một cấu hình cho cả local và CI mà không phân biệt profile.** Người dùng local có thể cần prompt trong khi pipeline cần chạy một lần. Tách profile để tránh cấu hình vô tình ghi đè.

**Không đặt timeout.** Nếu command bị chờ ở một API nhập liệu hoặc tác vụ bên ngoài, job có thể treo vô hạn. Đặt timeout ở cấp job và trong các thao tác I/O có thể chờ.

**Coi việc không có stdin là xác nhận.** EOF không phải sự đồng ý. Với thao tác cần xác nhận, yêu cầu option xác nhận rõ ràng.

**Chỉ kiểm tra output mà bỏ qua exit code.** Job CI cần biết command thành công hay thất bại. Kiểm thử và cấu hình cách ánh xạ lỗi sang exit code phù hợp.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): ba runner, thuộc tính bật/tắt và thay đổi mặc định từ 3.3.
- [Spring Shell 3.3.4 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): bật/tắt interactive runner và chạy command không tương tác.
- [Spring Shell 3.3.0 API — ShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/ShellRunner.html): hợp đồng chạy của runner.
- [Spring Shell 3.3.0 API — ScriptShellRunner](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/jline/ScriptShellRunner.html): nhận diện file script qua đối số bắt đầu bằng `@`.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): cấu hình qua file, profile, biến môi trường và tham số dòng lệnh.

Để CLI chạy ổn định trong automation, hãy tắt interactive runner theo profile, bật runner xử lý command phù hợp và cung cấp toàn bộ dữ liệu qua option hoặc argument. Đồng thời loại bỏ prompt khỏi đường thực thi tự động, kiểm tra exit code và đặt timeout để job không bị chờ vô hạn.


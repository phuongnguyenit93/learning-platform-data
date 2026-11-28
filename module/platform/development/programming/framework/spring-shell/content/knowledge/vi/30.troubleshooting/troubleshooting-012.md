# Script dừng, tiếp tục hoặc trả mã thoát khác dự kiến

Khi chạy Spring Shell CLI trong một script, ba kết quả cần kiểm tra riêng là: command có được thực thi không, các dòng tiếp theo có tiếp tục chạy không, và tiến trình Java trả mã thoát nào cho hệ điều hành. Một command có thể báo lỗi trên terminal nhưng tiến trình vẫn trả mã thành công; ngược lại, script có thể dừng đúng lúc nhưng mã thoát bị một lệnh sau đó ghi đè.

Để tìm nguyên nhân, hãy xác định lớp đang quyết định kết quả:

1. Spring Shell chọn runner nào và đọc command/script ra sao.
2. Command trả trạng thái nào hoặc ném exception nào.
3. Spring Boot chuyển lỗi thành mã thoát của tiến trình JVM như thế nào.
4. Bash, PowerShell hoặc Windows Command Prompt nhận và truyền mã thoát đó cho bước tiếp theo ra sao.

## 1. Phân biệt ba loại trạng thái

Không phải mọi thông báo lỗi đều có nghĩa là tiến trình đã thất bại. Hãy phân biệt:

| Lớp | Giá trị cần xem | Ý nghĩa |
|---|---|---|
| Command Spring Shell | Kết quả command hoặc `ExitStatus` | Command nghiệp vụ chạy thành công, lỗi cú pháp hay lỗi thực thi |
| Script/runner Spring Shell | Dòng tiếp theo có được chạy, runner có ném exception hay không | Cách nhiều command được điều phối |
| Tiến trình JVM | Process exit code | Mã mà hệ điều hành và chương trình gọi nhận được |

Quy ước phổ biến của hệ điều hành là mã `0` biểu thị thành công, mã khác `0` biểu thị thất bại. Một dòng log `ERROR` không tự động làm mã tiến trình khác `0`; chương trình phải chuyển lỗi thành exit status và runner phải đưa trạng thái đó ra ngoài tiến trình.

Ví dụ, command có thể in `Project not found` rồi trả về bình thường. Nếu nó không ném exception hoặc trả trạng thái lỗi theo hợp đồng của runner, tiến trình vẫn có thể kết thúc với mã thành công.

## 2. Xác định đúng Spring Shell runner theo phiên bản

Spring Shell có các runner cho interactive, non-interactive và script. Quy tắc chọn runner thay đổi giữa các phiên bản:

| Phiên bản | Mặc định | Cách chạy command/script |
|---|---|---|
| 3.2.x | Các runner interactive, non-interactive và script được bật mặc định | Có thể chạy REPL, command theo arguments hoặc script runner |
| 3.3.x–3.4.x | Chỉ `NonInteractiveShellRunner` được bật mặc định | Bật `spring.shell.interactive.enabled` hoặc `spring.shell.script.enabled` nếu cần runner tương ứng |
| 4.0.x | Interactive mode được bật mặc định, kể cả khi có command-line arguments | Đặt `spring.shell.interactive.enabled=false` để chạy arguments hoặc script bằng non-interactive runner |

Với Spring Shell 3.3.x và 3.4.x, có thể bật interactive và script runner trong `application.yml`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    script:
      enabled: true
~~~

Nếu chỉ muốn chạy command được truyền sau tên JAR, dùng `NonInteractiveShellRunner`. Nếu muốn truyền file cho `ScriptShellRunner` trong dòng 3.x, bật `spring.shell.script.enabled` và truyền đối số bắt đầu bằng ký tự `@`.

Với Spring Shell 4, cấu hình non-interactive:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Khi đó, `NonInteractiveShellRunner` có thể chạy một command hoặc một script file được chỉ định bằng tiền tố `@`. Nếu không tắt interactive mode, ứng dụng có thể mở REPL và chờ input thay vì chạy command rồi kết thúc.

Đừng suy luận runner chỉ từ việc lệnh có arguments. Kiểm tra `spring.shell.interactive.enabled`, `spring.shell.script.enabled` và phiên bản Spring Shell thực tế trong runtime.

## 3. Phân biệt script command với @file runner

Spring Shell có hai cách phổ biến để đọc nhiều command từ file. Chúng có cú pháp và vòng đời khác nhau.

### Dùng command script --file

Built-in `script` command đọc một file và thực thi các command theo thứ tự, mỗi dòng một command:

~~~text
script --file /absolute/path/to/deploy.shell
~~~

Ví dụ file `deploy.shell`:

~~~text
// Chuẩn bị môi trường
login --profile production
project validate --all
project deploy --name api
report export --format json --output build/report.json
~~~

Trong tài liệu Spring Shell 4.0.4, `script --file` chấp nhận đường dẫn tuyệt đối hoặc resource reference như `classpath:` và `file:`:

~~~text
script --file classpath:scripts/deploy.shell
script --file file:/opt/admin-cli/deploy.shell
~~~

Dòng comment bắt đầu bằng `//` được bỏ qua. Mỗi command phải nằm trên một dòng và dùng đúng cú pháp parser của Spring Shell.

### Dùng @file với runner

Trong Spring Shell 3.3.x–3.4.x, `ScriptShellRunner` tìm các process arguments bắt đầu bằng `@` và xem phần còn lại là đường dẫn file script:

~~~bash
java --disable-@files -jar target/admin-cli.jar @deploy.shell
~~~

Với Spring Shell 3.x, bảo đảm `spring.shell.script.enabled=true`. Với Spring Shell 4, `NonInteractiveShellRunner` hỗ trợ chạy một script file bằng tiền tố `@` khi non-interactive mode được bật:

~~~bash
java --disable-@files -jar target/admin-cli.jar @deploy.shell
~~~

`--disable-@files` là tùy chọn của Java launcher. Java cũng dùng cú pháp `@file` cho argument file của chính JVM; tùy chọn này ngăn Java mở rộng `@deploy.shell` trước khi Spring Shell nhận được đối số. Đặt nó trước `-jar`.

### Không nhầm hai cách gọi

| Cách gọi | Ai đọc file | Mục đích |
|---|---|---|
| `script --file deploy.shell` | Built-in `script` command | Chạy file từ một phiên shell đang hoạt động |
| `java ... -jar app.jar @deploy.shell` | `ScriptShellRunner` trong 3.x hoặc `NonInteractiveShellRunner` trong 4.x | Chạy script ở chế độ non-interactive rồi kết thúc |

Nếu lệnh `script` báo không tồn tại, hãy kiểm tra built-in command có được đóng gói/đăng ký hay không. Nếu `@file` không chạy, hãy kiểm tra runner và property theo đúng phiên bản.

## 4. Hiểu hành vi dừng hoặc tiếp tục sau lỗi

Tài liệu Spring Shell mô tả script được thực thi tuần tự theo từng dòng, nhưng không nên suy rộng điều đó thành một cam kết tương đương `set -e` của Bash cho mọi phiên bản và mọi loại lỗi.

Có ít nhất ba trường hợp khác nhau:

1. Command chạy thành công và trả trạng thái `0`: script có thể chuyển sang dòng tiếp theo.
2. Command chạy nhưng trả trạng thái lỗi hoặc ném exception: runner có thể dừng quá trình script và trả lỗi.
3. Parser không thể phân tích một dòng, hoặc file script không thể mở/đọc: runner có thể xử lý khác với lỗi phát sinh trong thân command.

Vì hành vi phụ thuộc phiên bản và runner, hãy kiểm thử bằng một file có command đánh dấu trước lỗi, command lỗi và command đánh dấu sau lỗi. Không dựa vào một dòng log để kết luận dòng sau đã chạy hay chưa.

### Tạo script kiểm tra thứ tự

Đăng ký ba command test đơn giản:

~~~java
@ShellComponent
class ScriptProbeCommands {

    @ShellMethod("Đánh dấu trước lỗi")
    public String probeBefore() {
        return "PROBE_BEFORE";
    }

    @ShellMethod("Tạo lỗi có chủ đích")
    public void probeFail() {
        throw new IllegalStateException("PROBE_FAILURE");
    }

    @ShellMethod("Đánh dấu sau lỗi")
    public String probeAfter() {
        return "PROBE_AFTER";
    }
}
~~~

Tạo file `probe.shell`:

~~~text
probe-before
probe-fail
probe-after
~~~

Chạy script bằng đúng runner của phiên bản đang dùng. Sau đó kiểm tra:

- Có thấy `PROBE_BEFORE` không?
- Có thấy thông báo `PROBE_FAILURE` không?
- Có thấy `PROBE_AFTER` không?
- Process exit code là bao nhiêu?

Lặp lại với một dòng command không tồn tại hoặc sai cú pháp. Kết quả giúp phân biệt lỗi parser với exception do command ném ra.

### Quyết định chính sách tiếp tục

Một workflow có thể cần một trong hai chính sách:

| Chính sách | Hành vi mong muốn | Cách triển khai |
|---|---|---|
| Fail-fast | Dừng ngay khi command đầu tiên thất bại | Kiểm tra exit status sau từng command; không chạy bước tiếp theo khi mã khác `0` |
| Continue-and-report | Tiếp tục các bước độc lập, tổng hợp lỗi ở cuối | Bọc từng bước, lưu mã lỗi và trả một mã tổng hợp khác `0` nếu có lỗi |

Nếu built-in script runner không cung cấp chính sách đúng với yêu cầu vận hành, hãy điều phối từng command từ Bash/PowerShell hoặc tạo một command orchestration riêng. Khi cần tiếp tục, chỉ tiếp tục các bước độc lập và ghi nhận mọi lỗi; không bỏ qua lỗi rồi trả `0`.

## 5. Các lỗi mã thoát theo phiên bản Spring Shell

### Spring Shell 3.4.x

Tài liệu 3.4 mô tả mã mặc định:

| Trường hợp | Mã mặc định |
|---|---:|
| Lỗi phân tích option/command | `2` |
| Lỗi tổng quát | `1` |
| Thành công | `0` |

Với command registration, có thể cấu hình ánh xạ exception sang exit code bằng `withExitCode()`:

~~~java
CommandRegistration.builder()
        .command("project deploy")
        .withExitCode()
            .map(ProjectNotFoundException.class, 4)
            .map(ProjectPermissionException.class, 5)
            .and()
        .build();
~~~

Tài liệu 3.4 ghi chú mã thoát không thể tùy chỉnh bằng annotation-based configuration. Nếu command dùng annotation, hãy kiểm tra cách xử lý exception đang dùng và kiểm thử process exit code thật thay vì giả định mapping trong builder tự áp dụng.

### Spring Shell 4.x

Trong mô hình command mới, command trả về `ExitStatus` hoặc ném exception. `ExitStatus` chứa mã và mô tả:

~~~java
return new ExitStatus(4, "Project was not found");
~~~

`ExitStatusExceptionMapper` có thể chuyển exception thành trạng thái command. Khi chạy non-interactive, runner chuyển lỗi thực thi thành exception chứa mã để Spring Boot xử lý ở cấp ứng dụng.

Phân biệt `ExitStatus` của command với process exit code. Nếu script hoặc CI cần mã thoát của JVM, hãy kiểm tra tiến trình thực tế bằng `Process.waitFor()` hoặc `$LASTEXITCODE`.

### Lưu ý quan trọng với Spring Shell 4.0.4

Spring Shell 4.0.2 đã sửa lỗi tổng quát khiến non-interactive runner luôn trả `0` ngay cả khi command thất bại. Tuy nhiên, ở Spring Shell 4.0.4 vẫn có issue #1391 đang mở về mã thoát khi command không parse được.

Theo xác nhận của maintainer trong issue:

- Khi parser ném exception, runner ghi log rồi trả về mà không ném lỗi lên Spring Boot.
- Với `@file`, vòng lặp script dừng ở dòng parse lỗi.
- Vì runner kết thúc bình thường, tiến trình có thể trả `0` dù script chưa chạy hết.
- File script không tồn tại, không mở được hoặc không đọc được cũng có thể rơi vào tình huống trả `0`.
- Built-in `script` command cũng ủy quyền việc chạy từng dòng cho non-interactive runner; do đó lỗi parse có thể bị bỏ qua và kết quả script vẫn là thành công trong phiên bản bị ảnh hưởng.

PR #1393 đề xuất chuyển các lỗi này thành `CommandExecutionException` để trả mã khác `0`, nhưng PR vẫn ở trạng thái Open và chưa được triển khai trong bản phát hành 4.0.4. Vì vậy, hãy kiểm thử lỗi parser, file thiếu và lỗi đọc file trên đúng phiên bản đang triển khai. Nếu cần bảo đảm CI không báo thành công giả, dùng wrapper kiểm tra trước file, xác thực command và bổ sung bước kiểm tra kết quả sau khi chạy.

## 6. Chẩn đoán khi script dừng sớm

Khi một file chỉ chạy đến một dòng rồi kết thúc, kiểm tra theo thứ tự:

1. Xác nhận runner đã được bật. Với Spring Shell 3.3.x–3.4.x, kiểm tra `spring.shell.script.enabled`; với 4.x, kiểm tra `spring.shell.interactive.enabled=false` khi chạy `@file`.
2. Xác nhận file đúng đường dẫn, có quyền đọc và dùng encoding phù hợp.
3. Kiểm tra dòng ngay trước vị trí dừng có exception hoặc lỗi parser không.
4. Kiểm tra dòng comment có bắt đầu bằng `//` ở đầu dòng hay không.
5. Kiểm tra option, dấu nháy và giá trị có khoảng trắng.
6. Thử chạy riêng command gây lỗi với cùng arguments.
7. Chạy lại script có command đánh dấu trước/sau lỗi để xác định chính xác dòng tiếp theo có được thực thi.
8. Kiểm tra version Spring Shell và release notes để tìm bug đã được sửa hoặc issue còn mở.

Với Spring Shell 4, có thể bật debug mode khi điều tra:

~~~yaml
spring:
  shell:
    debug:
      enabled: true
~~~

Debug mode giúp hiển thị stack trace cho lỗi thực thi trong interactive mode. Với script non-interactive, vẫn cần kiểm tra log runner và process exit code.

## 7. Chẩn đoán khi script tiếp tục dù command lỗi

Nếu các dòng sau vẫn chạy sau một command lỗi:

- Kiểm tra command có thực sự trả trạng thái lỗi hoặc ném exception hay chỉ in thông báo rồi kết thúc bình thường.
- Kiểm tra script runner có bắt exception và tiếp tục hay không.
- Phân biệt lỗi command với lỗi parser; hai loại có thể đi qua nhánh xử lý khác nhau.
- Không giả định `script --file` có hành vi giống `set -e` của Bash.
- Nếu chính sách là fail-fast, chạy từng command qua wrapper có kiểm tra mã trả về.

Một cách an toàn là đặt mỗi bước trong một process riêng:

~~~bash
run_step() {
  local command_name="$1"
  shift

  if java -jar target/admin-cli.jar "$command_name" "$@"; then
    printf 'OK: %s\n' "$command_name"
  else
    local rc=$?
    printf 'FAILED: %s (exit=%s)\n' "$command_name" "$rc" >&2
    return "$rc"
  fi
}

run_step "project validate" --all || exit $?
run_step "project deploy" --name api || exit $?
run_step "report export" --format json --output build/report.json || exit $?
~~~

Wrapper này làm chính sách fail-fast rõ ràng: bước tiếp theo chỉ chạy khi bước trước trả `0`. Cách này phù hợp khi mỗi command có thể chạy độc lập. Nếu các bước cần chia sẻ trạng thái trong cùng một Spring context, hãy dùng một command orchestration hoặc một script runner có kiểm soát thay vì khởi động lại JVM cho từng bước. Nếu muốn tiếp tục sau lỗi, lưu mã lỗi và tổng hợp ở cuối thay vì dùng `|| true` để bỏ qua mọi thất bại.

## 8. Bash: giữ đúng exit status

Trong Bash, `$?` chứa trạng thái của command vừa chạy. Hãy lưu nó ngay sau command cần kiểm tra:

~~~bash
java -jar target/admin-cli.jar @deploy.shell
rc=$?

if [ "$rc" -ne 0 ]; then
  printf 'Spring Shell failed: exit=%s\n' "$rc" >&2
  exit "$rc"
fi

echo "Deploy completed"
~~~

Nếu chạy lệnh tiếp theo trước khi lưu `$?`, mã thoát ban đầu bị ghi đè. Ví dụ `java -jar ...; echo done` thường trả mã của `echo`, không phải mã của Java.

Có thể dùng cấu trúc điều kiện để kiểm tra mà không phụ thuộc vào `set -e`:

~~~bash
if java -jar target/admin-cli.jar project deploy --name api; then
  echo "Deploy completed"
else
  rc=$?
  echo "Deploy failed: $rc" >&2
  exit "$rc"
fi
~~~

### Dùng set -e và pipefail đúng cách

`set -e` yêu cầu Bash thoát khi một command hoặc pipeline thất bại trong nhiều ngữ cảnh, nhưng có các ngoại lệ như điều kiện `if`, danh sách `&&`/`||`, vòng lặp và một số vị trí trong pipeline. Vì vậy, không xem `set -e` là cơ chế bắt mọi lỗi.

`pipefail` thay đổi mã của pipeline để lỗi từ thành phần trước không bị che bởi thành phần cuối:

~~~bash
set -euo pipefail

java -jar target/admin-cli.jar report export --format json |
  tee build/report.json
~~~

Không có `pipefail`, pipeline có thể trả `0` nếu `tee` thành công dù Java thất bại. Khi cần đọc mã riêng của từng phần pipeline, lưu `PIPESTATUS` ngay sau pipeline:

~~~bash
java -jar target/admin-cli.jar report export --format json |
  tee build/report.json
statuses=("${PIPESTATUS[@]}")

cli_rc=${statuses[0]}
tee_rc=${statuses[1]}
if [ "$cli_rc" -ne 0 ]; then
  exit "$cli_rc"
fi
if [ "$tee_rc" -ne 0 ]; then
  exit "$tee_rc"
fi
~~~

Lưu ý: với `set -e`, pipeline thất bại có thể làm shell thoát trước khi các dòng đọc `PIPESTATUS` chạy. Trong trường hợp cần kiểm tra từng mã, đặt pipeline trong `if` hoặc chủ động tắt `errexit` cho đoạn đó rồi kiểm tra tường minh.

## 9. PowerShell: dùng LASTEXITCODE cho chương trình native

Khi PowerShell gọi `java.exe`, mã thoát nằm trong `$LASTEXITCODE`. Mặc định, mã khác `0` không tự tạo exception để `catch` bắt được:

~~~powershell
& java -jar "target/admin-cli.jar" "@deploy.shell"
$rc = $LASTEXITCODE

if ($rc -ne 0) {
    Write-Error "Spring Shell failed with exit code $rc"
    exit $rc
}

Write-Output "Deploy completed"
~~~

`$?` chỉ cho biết thao tác gần nhất thành công hay thất bại; `$LASTEXITCODE` giữ số cụ thể của chương trình native. Nếu cần báo cáo mã lỗi chính xác, hãy đọc `$LASTEXITCODE` ngay sau lệnh Java.

PowerShell 7.4 có `$PSNativeCommandUseErrorActionPreference`. Khi bật cùng `$ErrorActionPreference = 'Stop'`, native command trả mã khác `0` có thể trở thành lỗi PowerShell để `try/catch` xử lý. Tuy nhiên, kiểm tra tường minh `$LASTEXITCODE` vẫn dễ đọc và tương thích hơn giữa Windows PowerShell 5.1 và PowerShell 7.x.

## 10. Windows Command Prompt: kiểm tra ERRORLEVEL

Trong file `.bat` hoặc `.cmd`, kiểm tra `ERRORLEVEL` ngay sau chương trình Java:

~~~bat
@echo off
java -jar target\admin-cli.jar @deploy.shell
set "rc=%ERRORLEVEL%"
if not "%rc%"=="0" exit /b %rc%

echo Deploy completed
~~~

Có thể dùng:

~~~bat
if errorlevel 1 exit /b %ERRORLEVEL%
~~~

`if errorlevel N` có nghĩa là điều kiện đúng khi mã trả về bằng hoặc lớn hơn `N`, không phải chỉ bằng `N`. Nếu cần so sánh chính xác một mã cụ thể, dùng phép so sánh chuỗi như ví dụ `if not "%rc%"=="0"`.

Trong một khối lệnh đặt trong ngoặc, `%ERRORLEVEL%` có thể được mở rộng trước khi các dòng trong khối chạy. Khi cần giá trị thay đổi bên trong khối, dùng delayed expansion với `!ERRORLEVEL!` hoặc tách lệnh kiểm tra ra ngoài khối.

## 11. Phân biệt exit code của Java với mã của script cha

Một số ví dụ gây mất mã lỗi:

| Cách viết | Vấn đề |
|---|---|
| `java -jar app.jar; echo done` trong Bash | Mã cuối cùng là của `echo` |
| `java -jar app.jar \| tee output.log` không có `pipefail` | Pipeline có thể trả mã `0` từ `tee` |
| Gọi Java trong PowerShell rồi chỉ kiểm tra `$?` | Không giữ số mã cụ thể như `$LASTEXITCODE` |
| Chạy Java trong batch rồi chạy `echo` trước khi đọc `ERRORLEVEL` | Mã có thể bị lệnh sau ghi đè |
| `try/catch` trong PowerShell nhưng không kiểm tra `$LASTEXITCODE` | Native program trả mã khác `0` không mặc định kích hoạt `catch` |
| `|| true` sau lệnh Java | Chủ động biến thất bại thành thành công cho shell gọi |

Nếu cần ghi log sau khi chạy mà vẫn giữ mã:

~~~bash
java -jar target/admin-cli.jar @deploy.shell
rc=$?
printf 'Spring Shell exit code: %s\n' "$rc" >&2
exit "$rc"
~~~

Không đặt `exit 0` ở cuối wrapper nếu command trước đó có thể thất bại.

## 12. Kiểm tra bằng ProcessBuilder

Để xác nhận mã tiến trình độc lập với terminal đang dùng, chạy JAR trong một tiến trình con:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

Path outputFile = Path.of("build", "script-output.log");
Files.createDirectories(outputFile.getParent());

Process process = new ProcessBuilder(
        "java",
        "--disable-@files",
        "-jar",
        "target/admin-cli.jar",
        "@deploy.shell"
).redirectErrorStream(true)
 .redirectOutput(outputFile.toFile())
 .start();

boolean finished = process.waitFor(60, TimeUnit.SECONDS);
if (!finished) {
    process.destroyForcibly();
    throw new IllegalStateException("CLI timed out");
}

int exitCode = process.exitValue();
String output = Files.readString(outputFile, StandardCharsets.UTF_8);

if (exitCode != 0) {
    throw new IllegalStateException(
            "CLI failed with exit code " + exitCode + "\n" + output);
}
~~~

Ví dụ dùng `redirectErrorStream(true)` để gộp stdout và stderr vào file, tránh để buffer của tiến trình con đầy khi chương trình chạy lâu. Nếu cần kiểm tra hai luồng riêng, redirect stdout và stderr ra hai file khác nhau.

Tạo các bài test cho ít nhất bốn trường hợp: command hợp lệ, command ném exception, command sai cú pháp và script file không tồn tại. Mỗi test nên xác nhận cả output lẫn `exitCode`.

## 13. Ma trận chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Ứng dụng mở REPL thay vì chạy script | Runner interactive đang bật | Kiểm tra `spring.shell.interactive.enabled` |
| `@file` bị bỏ qua trong Spring Shell 3.4 | `ScriptShellRunner` chưa bật | Kiểm tra `spring.shell.script.enabled=true` |
| Java đọc file `@deploy.shell` trước Spring Shell | Java launcher mở rộng argument file | Thêm `--disable-@files` trước `-jar` |
| Command đầu chạy nhưng script dừng ở command tiếp theo | Exception, lỗi parser hoặc file input có dòng không hợp lệ | Chạy riêng dòng lỗi và kiểm tra log |
| Script tiếp tục sau command lỗi | Runner hoặc script policy đang tiếp tục; command có thể chỉ in lỗi | Dùng probe command và kiểm tra `ExitStatus`/exception |
| Script dừng nhưng process trả `0` | Lỗi parser/file bị ghi log rồi kết thúc bình thường | Kiểm tra Spring Shell 4.0.4 issue #1391 |
| Mọi command lỗi đều trả `0` ở 4.0.0–4.0.1 | Bug non-interactive runner | Nâng tối thiểu lên 4.0.2 và kiểm thử lại |
| Dòng comment làm script dừng | Bug xử lý comment ở một số bản 4.0.x đầu | Nâng bản và kiểm tra release notes; comment phải bắt đầu bằng `//` |
| Command lỗi nhưng Bash script vẫn báo thành công | `$?` bị ghi đè hoặc pipeline che mã | Lưu mã ngay; dùng `pipefail` khi cần |
| PowerShell không vào catch | Native exit code không phải PowerShell terminating error | Kiểm tra `$LASTEXITCODE` |
| Batch chạy bước tiếp dù Java thất bại | Chưa kiểm tra `ERRORLEVEL` | Lưu mã và `exit /b` khi khác `0` |
| Script trả mã của lệnh cuối thay vì lỗi đầu tiên | Wrapper không lưu mã lỗi trước đó | Lưu mã đầu tiên thất bại và trả lại ở cuối |

## 14. Lưu ý phiên bản và release notes

Khi chẩn đoán mã thoát, ghi lại chính xác phiên bản Spring Shell:

- Spring Shell 3.3.x: chỉ `NonInteractiveShellRunner` bật mặc định; `ScriptShellRunner` cần được bật bằng `spring.shell.script.enabled`.
- Spring Shell 3.4.x: mã mặc định trong tài liệu là `2` cho lỗi parse option, `1` cho lỗi tổng quát và `0` cho thành công.
- Spring Shell 4.0.0–4.0.1: có lỗi khiến non-interactive runner luôn trả `0` trong một số trường hợp.
- Spring Shell 4.0.2: đã sửa lỗi tổng quát về exit code luôn bằng `0` và một số lỗi khi chạy script.
- Spring Shell 4.0.4: đã bổ sung hỗ trợ classpath reference cho built-in `script` command; issue #1391 về parse error và script file không đọc được vẫn được ghi nhận là Open, PR #1393 chưa được triển khai.

Nếu kết quả khác tài liệu, hãy tái hiện trên đúng patch version đang chạy và kiểm tra release notes/issue tracker trước khi thêm workaround.

## 15. Checklist vận hành script

Trước khi đưa script vào CI hoặc cron, kiểm tra:

1. Phiên bản Spring Shell và runner được chọn đã được xác định rõ.
2. Script runner được bật đúng property theo phiên bản.
3. File script tồn tại, đọc được và đường dẫn không bị nhầm với Java argument file.
4. Script dùng cú pháp một command mỗi dòng và comment `//` đúng vị trí.
5. Command có lỗi cú pháp và lỗi thực thi đã được thử riêng.
6. Đã kiểm tra script có dừng hay tiếp tục sau từng loại lỗi.
7. Exit code của tiến trình được kiểm tra, không chỉ đọc log.
8. Bash lưu `$?` ngay; pipeline dùng `pipefail` khi cần.
9. PowerShell kiểm tra `$LASTEXITCODE`.
10. Batch kiểm tra `ERRORLEVEL` trước khi chạy lệnh tiếp theo.
11. Wrapper không ghi đè mã lỗi bằng một lệnh log hoặc `exit 0`.
12. CI có test cho command sai cú pháp và file script không tồn tại.

## 16. Bài tập thực hành

Tạo script `release.shell` với các bước:

~~~text
project validate --all
project package --profile production
project publish --repository internal
report release --format json --output build/release.json
~~~

Thực hiện:

1. Chạy script bằng `script --file` trong phiên interactive.
2. Chạy script bằng `@release.shell` ở non-interactive mode.
3. Cố ý nhập sai tên command ở dòng thứ hai.
4. Cố ý làm command `project publish` ném exception.
5. Ghi nhận dòng nào đã chạy, dòng nào bị bỏ qua và process exit code.
6. Chạy lại trong Bash, PowerShell hoặc `cmd.exe` và xác nhận wrapper truyền đúng mã lỗi.
7. Tạo một wrapper fail-fast và một wrapper continue-and-report.
8. Kiểm thử trường hợp file script không tồn tại.
9. Lặp lại trên đúng phiên bản Spring Shell mà ứng dụng triển khai.

Sau bài tập, hãy giải thích được vì sao command log lỗi, script dừng và process exit code `0` có thể cùng xảy ra; đồng thời nêu cách ngăn CI nhận nhầm một lần chạy thất bại là thành công.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Execution và Shell Runners](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4 – Exit Code Mappings](https://docs.spring.io/spring-shell/reference/3.4/commands/exceptionhandling/mappings.html)
- [Spring Shell 3.4 API – Script](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/Script.html)
- [Spring Shell 3.4 API – ScriptShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html)
- [Spring Shell 4.0.4 – Built-in Script Command](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Spring Shell 4.0.4 API – NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell – Releases](https://github.com/spring-projects/spring-shell/releases)
- [Spring Shell Issue #1391 – Wrong exit value when commands cannot be parsed](https://github.com/spring-projects/spring-shell/issues/1391)
- [Spring Shell PR #1393 – Fail with non-zero exit code when a command cannot be parsed](https://github.com/spring-projects/spring-shell/pull/1393)
- [Spring Boot 3.5 – SpringApplication Exit Code](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Bash Reference Manual – Exit Status and set](https://www.gnu.org/software/bash/manual/bash.html)
- [Microsoft Learn – PowerShell Error Handling](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_error_handling)
- [Microsoft Learn – cmd.exe IF and ERRORLEVEL](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/if)

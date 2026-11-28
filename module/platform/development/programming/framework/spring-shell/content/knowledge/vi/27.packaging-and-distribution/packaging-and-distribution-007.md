# Chạy trong container có hoặc không cấp terminal tương tác

Một ứng dụng Spring Shell có thể được phân phối dưới dạng container image và chạy theo hai cách: mở một phiên REPL để người dùng gõ nhiều command, hoặc thực thi một command/script rồi kết thúc để phục vụ CI, cron hay pipeline dữ liệu. Cùng một image có thể hỗ trợ cả hai kiểu chạy nếu cấu hình shell runner và cách truyền input/output phù hợp.

Khi chạy trong Docker, cần phân biệt hai lớp cấu hình. Docker quyết định container có nhận `STDIN` và có pseudo-terminal (TTY) hay không. Spring Shell quyết định dùng runner tương tác, runner non-interactive hay runner chạy script. `-it` giúp nối terminal của máy host vào container, nhưng tự nó không bật interactive runner của Spring Shell. Ngược lại, bật interactive runner trong ứng dụng không thể tạo ra bàn phím hoặc TTY nếu container không được cấp các luồng đó.

Bài viết dùng Spring Shell 3.4.x, Spring Boot và Docker/OCI. Các ví dụ tập trung vào image cho ứng dụng CLI, `ENTRYPOINT`, `STDIN`/`STDOUT`/`STDERR`, TTY, interactive/non-interactive/script runner, mã thoát và vòng đời container.

## Ba khái niệm cần tách biệt

Một ứng dụng terminal có ba yếu tố liên quan nhưng không đồng nghĩa:

1. **STDIN** là luồng dữ liệu đầu vào. Docker `-i` giữ luồng này mở để container nhận dữ liệu từ bàn phím hoặc pipe.
2. **TTY/PTY** là terminal giả lập. Docker `-t` cấp pseudo-terminal để chương trình sử dụng tính năng như điều khiển con trỏ, resize, màu sắc và tắt echo khi nhập bí mật.
3. **Interaction mode** là chế độ chạy của Spring Shell. Interactive runner giữ REPL hoạt động qua nhiều command; non-interactive runner chạy command được truyền lúc khởi động rồi kết thúc; script runner đọc một file lệnh rồi kết thúc.

| Cấu hình Docker | STDIN | Có PTY | Cách dùng thường gặp |
| --- | --- | --- | --- |
| Không có `-i`, không có `-t` | Không giữ mở | Không | Một command hoặc job chạy trong CI |
| `-i` | Giữ mở | Không | Pipe dữ liệu hoặc nhận input văn bản không cần terminal |
| `-t` | Không bảo đảm có input | Có | Chương trình cần định dạng terminal nhưng không cần nhập |
| `-it` | Giữ mở | Có | Phiên REPL tương tác qua bàn phím |

Vì vậy, hãy chọn Docker flags theo cách container nhận input, rồi chọn Spring Shell runner theo mục tiêu của tiến trình. Một container không có TTY vẫn có thể chạy command non-interactive thành công; một container có TTY vẫn có thể chạy một command rồi thoát nếu ứng dụng được cấu hình như vậy.

## Cấu hình runner của Spring Shell 3.4.x

Spring Shell 3.4.x có ba runner chính:

| Runner | Vai trò | Cấu hình |
| --- | --- | --- |
| `InteractiveShellRunner` | Khởi động REPL và chờ người dùng nhập nhiều command | `spring.shell.interactive.enabled=true` |
| `NonInteractiveShellRunner` | Thực thi command từ đối số tiến trình rồi kết thúc | `spring.shell.noninteractive.enabled=true` |
| `ScriptShellRunner` | Đọc file script được truyền dưới dạng đối số bắt đầu bằng `@` rồi kết thúc | `spring.shell.script.enabled=true` |

Từ Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Interactive và script runner mặc định không được bật. Vì vậy, nếu muốn cùng một image hỗ trợ cả REPL lẫn chạy batch, hãy bật các runner cần thiết trong cấu hình ứng dụng:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
```

`noninteractive.enabled` mặc định là `true` trong cấu hình auto-configuration 3.4.x, nhưng ghi rõ trong cấu hình triển khai giúp người vận hành thấy được chủ đích. Nếu image chỉ được dùng cho batch, có thể giữ interactive runner tắt để giảm khả năng một lệnh thiếu đối số làm tiến trình chờ prompt.

Spring Shell 3.4.x cũng cung cấp `ShellContext` để đọc chế độ và khả năng terminal:

```java
import org.springframework.shell.context.ShellContext;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class RuntimeCommands {

    private final ShellContext shellContext;

    public RuntimeCommands(ShellContext shellContext) {
        this.shellContext = shellContext;
    }

    @ShellMethod(key = "runtime mode", value = "Hiển thị chế độ chạy hiện tại")
    public String mode() {
        return "interaction=" + shellContext.getInteractionMode()
                + ", pty=" + shellContext.hasPty();
    }
}
```

`getInteractionMode()` cho biết shell đang ở `INTERACTIVE` hay `NONINTERACTIVE`. `hasPty()` cho biết terminal có pseudo-terminal hay không. Hai giá trị này có thể khác nhau: một command có thể chạy non-interactive trong một phiên có TTY, hoặc shell interactive có thể được khởi chạy trong môi trường không có PTY. Không dùng riêng `hasPty()` để suy ra runner đang hoạt động.

## Đóng gói ứng dụng thành Docker image

Một container CLI thường chỉ cần JRE và executable JAR. Multi-stage build giữ Maven và mã nguồn ở build stage, còn image cuối chỉ chứa runtime và JAR.

```dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY src ./src
RUN mvn -B package

FROM eclipse-temurin:21-jre-jammy

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

WORKDIR /app
COPY --from=build --chown=app:app \
    /workspace/target/spring-shell-app.jar /app/app.jar

USER app:app
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Thay `spring-shell-app.jar` bằng tên artifact thực tế của dự án. JDK ở build stage và JRE ở runtime stage phải tương thích với `maven.compiler.release`/Java version mà ứng dụng sử dụng. Với Maven multi-module, cần copy các POM/module cần thiết trước khi chạy `mvn package`.

Một số điểm trong Dockerfile:

- `ENTRYPOINT` dùng exec form (mảng JSON), để JVM trở thành tiến trình chính trong container và nhận signal từ Docker.
- `USER app:app` chạy ứng dụng bằng user không phải root.
- Không cần `EXPOSE` nếu ứng dụng chỉ là CLI và không mở cổng mạng.
- Không đưa file script, dữ liệu đầu vào hoặc credential vào image nếu chúng thay đổi theo môi trường; mount hoặc truyền chúng khi chạy.
- `mvn package` chạy các test gắn với lifecycle trước khi tạo artifact. Có thể tách test và image build trong CI, nhưng không nên bỏ qua kiểm thử mà không có một bước xác minh tương đương.

Nên loại file build và thông tin phát triển khỏi build context bằng `.dockerignore`:

```text
.git
.idea
.vscode
target
*.log
```

Build image:

```bash
docker build -t spring-shell-cli:1.0 .
```

Nếu dùng registry để phân phối, gắn tag theo registry/project/version rồi push:

```bash
docker tag spring-shell-cli:1.0 registry.example.com/tools/spring-shell-cli:1.0
docker push registry.example.com/tools/spring-shell-cli:1.0
```

Máy chạy image có thể `docker pull` image theo tag đã phát hành. Dùng tag version cụ thể cho quy trình production; tag `latest` không đủ để tái tạo chính xác một lần chạy cũ.

## `ENTRYPOINT`, `CMD` và đối số command

Với image dùng như một executable CLI, `ENTRYPOINT` cố định JVM và JAR:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đối số đặt sau tên image trong `docker run` được nối vào exec-form `ENTRYPOINT`. Vì vậy:

```bash
docker run --rm spring-shell-cli:1.0 artifact download --source /data/input.csv
```

về cơ bản chạy:

```bash
java -jar /app/app.jar artifact download --source /data/input.csv
```

Spring Shell nhận các đối số và `NonInteractiveShellRunner` thực thi command. Container kết thúc khi command kết thúc. Không cần mở TTY hoặc giữ STDIN cho trường hợp này.

Có thể dùng `CMD` để cung cấp đối số mặc định có thể ghi đè, nhưng tránh đặt một command nghiệp vụ cụ thể làm mặc định nếu image được dùng cho nhiều command. Khi người dùng truyền command khác trong `docker run`, phần `CMD` bị thay thế còn exec-form `ENTRYPOINT` vẫn được giữ.

Không dùng shell-form `ENTRYPOINT` như sau:

```dockerfile
ENTRYPOINT java -jar /app/app.jar
```

Shell form chạy thông qua `/bin/sh -c`; tiến trình Java có thể không trở thành PID 1 và có thể không nhận trực tiếp signal `SIGTERM` khi Docker dừng container. Nếu cần script khởi động, script phải kết thúc bằng `exec java -jar /app/app.jar "$@"` để thay shell bằng JVM.

## Chạy REPL với terminal tương tác

Khi người dùng cần mở prompt và gõ nhiều command, bật interactive runner trong cấu hình Spring Shell và chạy container ở foreground với cả `-i` và `-t`:

```bash
docker run --rm -it --name spring-shell spring-shell-cli:1.0
```

Ví dụ phiên làm việc:

```text
shell:> help
shell:> remote connect staging
shell:> artifact list
shell:> quit
```

`-i` giữ STDIN mở để JLine nhận phím. `-t` cấp pseudo-terminal để có line editing, cursor, resize, màu sắc và các tính năng terminal khác. `--rm` xóa container sau khi người dùng thoát.

Nếu chạy container detached bằng `-d`, terminal không được gắn trực tiếp vào cửa sổ đang dùng. Với một REPL cần điều khiển, chạy foreground thường dễ sử dụng hơn. Nếu chủ động chạy detached với `-dit`, có thể attach vào phiên terminal chính bằng `docker attach <container>`; `docker exec -it <container> sh` chỉ mở một tiến trình shell khác trong container, không tự nối vào phiên Spring Shell đang chạy.

Trong Docker Compose, hai thuộc tính tương ứng là:

```yaml
services:
  shell:
    image: spring-shell-cli:1.0
    stdin_open: true
    tty: true
```

Chỉ bật `stdin_open` và `tty` cho service cần người dùng tương tác trực tiếp.

## Chạy một command không có TTY

Với một command batch, truyền command và options sau image. Không thêm `-it`:

```bash
docker run --rm \
  --mount type=bind,src="$PWD/input",dst=/input,readonly \
  --mount type=bind,src="$PWD/output",dst=/output \
  spring-shell-cli:1.0 \
  artifact import --file /input/customers.csv --report /output/import-report.json
```

Container nhận file đầu vào qua mount chỉ đọc và ghi báo cáo vào mount output. Không cần đóng gói dữ liệu trong image, và kết quả vẫn còn trên máy host sau khi container bị xóa.

Đối với một command non-interactive:

- Không gọi `StringInput`, `ConfirmationInput` hoặc `TerminalUI` để chờ phím người dùng.
- Yêu cầu dữ liệu cần thiết qua positional argument hoặc option có validation.
- Dùng thông báo theo dòng, dễ đọc và dễ parse.
- Trả exit code khác 0 khi command thất bại.
- Ghi thông tin chẩn đoán vào `STDERR` hoặc logger; giữ `STDOUT` cho kết quả mà script có thể tiêu thụ.

Không bật TTY chỉ để có màu. Trong CI hoặc khi output được pipe vào file, ký tự điều khiển terminal có thể làm log khó đọc. Nếu muốn hiển thị progress, hãy kiểm tra `ShellContext.hasPty()` và chuyển sang thông báo theo mốc khi không có PTY.

## Truyền dữ liệu qua STDIN

`-i` có thể hữu ích khi command cần đọc dữ liệu từ pipe thay vì file mount. Ví dụ:

```bash
cat ./input/customers.csv | docker run --rm -i spring-shell-cli:1.0 artifact import --stdin
```

Ở đây container nhận dữ liệu qua STDIN; không có PTY. Command `artifact import --stdin` phải chủ động đọc `System.in` hoặc một `InputStream` được ứng dụng quản lý. `-i` chỉ giữ luồng đầu vào mở, không tự biến dữ liệu pipe thành command Spring Shell và không tự kích hoạt REPL.

Không dùng `-t` khi cần truyền dữ liệu nhị phân hoặc cần giữ nguyên byte của pipe. Pseudo-terminal có thể áp dụng xử lý dòng và các hành vi terminal không phù hợp với dữ liệu thô. Với dữ liệu nhị phân, file mount hoặc stream không có PTY là lựa chọn phù hợp hơn.

## Chạy file script không cần terminal

Spring Shell 3.4.x có `ScriptShellRunner`. Khi được bật bằng `spring.shell.script.enabled=true`, runner tìm đối số bắt đầu bằng `@`, coi phần còn lại là đường dẫn script, thực thi các command trong file rồi thoát.

Ví dụ file `nightly.shell`:

```text
// Kết nối tới môi trường kiểm thử
remote connect staging

// Đồng bộ dữ liệu và tạo báo cáo
artifact sync --source /data/incoming --target /data/archive
report generate --output /data/reports/nightly.json
```

Mount thư mục script và dữ liệu vào container, sau đó truyền đường dẫn script:

```bash
docker run --rm \
  --mount type=bind,src="$PWD/scripts",dst=/scripts,readonly \
  --mount type=bind,src="$PWD/data",dst=/data \
  spring-shell-cli:1.0 @/scripts/nightly.shell
```

Runner chạy từng dòng như một command của shell và kết thúc sau khi xử lý script. Không cần `-i` hoặc `-t` chỉ để đọc file script. File script phải nằm trong filesystem mà container nhìn thấy; đường dẫn trên host không tự xuất hiện bên trong container nếu chưa mount.

Nếu đang ở một REPL tương tác và muốn chạy file, built-in command `script` cũng có thể đọc một file command. Đây là cách gọi từ bên trong phiên shell; `@/path/file` là cách khởi động `ScriptShellRunner` từ đối số tiến trình.

## Lựa chọn runner và Docker flags theo tình huống

| Mục tiêu | Spring Shell | Docker | Kết quả |
| --- | --- | --- | --- |
| Mở REPL cho người vận hành | Bật `interactive` | `docker run -it` | Prompt và nhiều command trong cùng phiên |
| Chạy một command trong CI | Bật `noninteractive` | `docker run --rm image command ...` | Chạy xong rồi trả exit code |
| Chạy chuỗi command định sẵn | Bật `script` | `docker run --rm image @/scripts/job.shell` | Đọc script rồi kết thúc |
| Nhập CSV từ pipe | Command tự đọc STDIN | `docker run --rm -i` | Nhận dữ liệu, không có PTY |
| Chỉ cần ghi log | Non-interactive | Không `-i`, không `-t` | Output được chuyển qua stdout/stderr |

Một lỗi cấu hình phổ biến là bật `interactive.enabled=true` rồi nghĩ rằng container tự có terminal. Nếu chạy không có `-i`, người dùng không thể nhập; nếu không có `-t`, JLine không có đầy đủ tính năng PTY. Ngược lại, chỉ thêm `-it` mà interactive runner vẫn bị tắt cũng không tạo được REPL.

## Quản lý history và filesystem của container

Spring Shell có thể lưu command history vào file. Mặc định history được bật và file được ghi vào thư mục cấu hình hiện hành hoặc working directory. Điều này cần được tính đến khi image chạy bằng user không root hoặc root filesystem chỉ đọc.

Nếu container batch không cần lưu history, có thể tắt:

```yaml
spring:
  shell:
    history:
      enabled: false
```

Nếu REPL cần giữ history giữa các lần khởi động, cấu hình `spring.shell.config.location` trỏ tới thư mục có quyền ghi và mount volume vào vị trí đó. Không cấp quyền ghi toàn bộ filesystem chỉ để lưu history.

Với container production, có thể dùng filesystem read-only và chỉ cấp volume cho dữ liệu cần ghi:

```bash
docker run --rm --read-only \
  --tmpfs /tmp \
  --mount type=bind,src="$PWD/output",dst=/output \
  spring-shell-cli:1.0 artifact export --output /output/result.json
```

Ứng dụng phải được cấu hình để ghi file tạm vào `/tmp` và kết quả vào `/output`. Nếu Java, Spring hoặc thư viện phụ thuộc cần ghi vào một thư mục khác, hãy cấp một mount có phạm vi hẹp cho thư mục đó. Kiểm tra quyền sở hữu file trên host vì container chạy bằng UID/GID của user `app`.

Không đưa mật khẩu, token hoặc private key vào Dockerfile bằng `ENV`, `ARG` hay `COPY`. Truyền bí mật lúc runtime bằng secret store hoặc cơ chế quản lý secret của nền tảng triển khai; tránh đưa secret vào command argument vì chúng có thể xuất hiện trong process listing và log.

## Log và mã thoát

Docker thu thập nội dung ghi ra `STDOUT` và `STDERR`. Với container chạy detached hoặc không có terminal đính kèm, có thể đọc log bằng:

```bash
docker logs --follow <container-name>
```

Với một lệnh `docker run --rm`, output thường được hiển thị trực tiếp trong terminal gọi lệnh. Nếu cần lưu log, có thể redirect output ở host hoặc cấu hình logging driver phù hợp.

Trong non-interactive mode, mã thoát của tiến trình là tín hiệu để CI hoặc script quyết định bước tiếp theo. Một command thành công nên trả 0; lỗi tham số, lỗi nghiệp vụ hoặc lỗi hệ thống cần trả mã khác 0 theo quy ước của ứng dụng. Không bắt exception rồi chỉ in “thất bại” nhưng vẫn trả 0, vì pipeline sẽ hiểu nhầm job thành công.

Ví dụ kiểm tra kết quả trong shell:

```bash
docker run --rm spring-shell-cli:1.0 artifact import --file /input/missing.csv
status=$?

if [ "$status" -ne 0 ]; then
  echo "Import failed with exit code $status" >&2
  exit "$status"
fi
```

Trong PowerShell, có thể đọc `$LASTEXITCODE` ngay sau lệnh Docker. Nếu command trả về dữ liệu để pipe sang một chương trình khác, hãy dành `STDOUT` cho dữ liệu và đưa thông tin chẩn đoán sang `STDERR` để không làm hỏng định dạng đầu ra.

## Dừng container và xử lý signal

Khi người dùng thoát REPL bằng command `quit`/`exit`, Spring Shell đóng phiên và Spring application context kết thúc. Khi Docker dừng container, Docker gửi `SIGTERM` tới tiến trình chính và sau thời gian chờ sẽ gửi `SIGKILL` nếu tiến trình chưa dừng.

Exec-form `ENTRYPOINT` giúp JVM nhận signal trực tiếp. Spring Boot có thể chạy shutdown hooks để đóng context và các bean có lifecycle. Nếu command đang ghi file, kết nối database hoặc gọi dịch vụ bên ngoài, hãy dùng `try/finally`, transaction và cleanup đúng cách để tránh để lại dữ liệu dở dang.

Ví dụ yêu cầu Docker chờ lâu hơn cho một tác vụ cần thời gian đóng an toàn:

```bash
docker stop --timeout 30 spring-shell-job
```

Không dùng `docker kill` làm cách dừng thông thường nếu muốn ứng dụng có cơ hội xử lý shutdown. Nếu image chạy thêm process con hoặc wrapper phức tạp, cân nhắc `docker run --init` để có init process hỗ trợ chuyển tiếp signal và thu dọn zombie process.

Một CLI chạy một command rồi thoát thường không cần `HEALTHCHECK` như một dịch vụ luôn chạy. Container kết thúc với exit code là trạng thái của job. Nếu ứng dụng được triển khai như một worker chạy liên tục, health check phải đo khả năng hoạt động của worker chứ không chỉ kiểm tra JVM còn sống.

## Kiểm thử image trước khi phân phối

Kiểm thử bằng JUnit trong JVM chưa đủ để chứng minh image hoạt động trong container. Nên chạy image đã build với cả trường hợp có TTY và không có TTY:

| Kiểm thử | Lệnh hoặc thao tác | Điều cần xác minh |
| --- | --- | --- |
| Khởi động REPL | `docker run --rm -it image` | Prompt xuất hiện, nhập được lệnh và thoát được |
| Chạy một command | `docker run --rm image help` | Command chạy rồi process kết thúc |
| Command thành công | `docker run --rm image artifact list` | Exit code bằng 0 và output đúng |
| Command thất bại | Truyền file không tồn tại | Exit code khác 0, lỗi được ghi rõ |
| Chạy script | `docker run --rm image @/scripts/job.shell` | Script được đọc, thực thi theo thứ tự và kết thúc |
| Pipe STDIN | `cat input.csv | docker run --rm -i image data import --stdin` | Dữ liệu được đọc đủ, không cần PTY |
| Không có PTY | Chạy trong CI hoặc redirect output | Không có prompt chờ, spinner hoặc mã điều khiển gây nhiễu |
| Mount output | Mount thư mục kết quả | File được tạo và có quyền đọc trên host |
| Read-only root | Chạy với `--read-only` | Chỉ các thư mục được cấp quyền mới được ghi |
| Shutdown | Gửi `docker stop` khi đang chạy | Ứng dụng nhận SIGTERM và dừng trong timeout |

Đối với REPL, kiểm tra ít nhất `help`, một command nghiệp vụ, một lỗi có thể phục hồi và `quit`. Đối với batch, kiểm tra stdout, stderr và exit code. Đối với script, kiểm tra đường đi khi một command lỗi giữa file và xác định rõ chính sách: dừng ngay, tiếp tục hay ghi nhận lỗi rồi xử lý các dòng sau.

## Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Container không hiện prompt | Interactive runner chưa được bật hoặc STDIN không mở | Bật `spring.shell.interactive.enabled` và chạy `-it` |
| Có prompt nhưng không nhập được | Không giữ STDIN hoặc terminal không được attach | Dùng `-i`; với REPL thông thường dùng `-it` |
| Chạy CI nhưng command chờ nhập | Interactive runner hoặc component hỏi input được gọi trong batch | Dùng non-interactive runner và truyền đủ options |
| `-it` nhưng app vẫn chạy một command rồi thoát | Docker TTY không quyết định Spring Shell runner | Kiểm tra `spring.shell.interactive.enabled` |
| Script không được thực thi | Script runner bị tắt hoặc đường dẫn không tồn tại trong container | Bật `spring.shell.script.enabled`, mount file và dùng đối số `@/path/file` |
| Script tìm thấy trên host nhưng không tìm thấy trong container | Chưa mount thư mục hoặc dùng sai đường dẫn đích | Mount thư mục và truyền đường dẫn container |
| Mất dữ liệu khi pipe | Dùng TTY cho stream dữ liệu thô hoặc command không đọc STDIN | Dùng `-i` không `-t` và triển khai nhánh đọc input |
| Output có ký tự điều khiển trong CI | Ứng dụng giả định có terminal tương tác | Kiểm tra `hasPty()` và dùng output dạng dòng |
| `docker stop` phải đợi đến timeout | Shell-form ENTRYPOINT không chuyển signal tới JVM | Dùng exec-form hoặc `exec` trong entrypoint script |
| Không ghi được history | User không root hoặc filesystem read-only | Tắt history hoặc mount thư mục config có quyền ghi |
| File output thuộc root hoặc không đọc được | Container chạy với UID/GID không phù hợp | Chạy bằng user rõ ràng và kiểm tra quyền mount |
| Job thất bại nhưng pipeline vẫn xanh | Command trả exit code 0 dù có lỗi | Ánh xạ lỗi sang mã thoát khác 0 và kiểm tra exit code Docker |
| `docker logs` không có output mong đợi | Ứng dụng ghi log vào file hoặc logging driver không hỗ trợ đọc | Ghi log ra stdout/stderr hoặc dùng backend log đã cấu hình |

## Quy trình phát hành container cho Spring Shell

1. Chọn các chế độ cần hỗ trợ: REPL, một command non-interactive, script hoặc kết hợp.
2. Bật đúng Spring Shell runner trong `application.yml` hoặc cấu hình theo môi trường.
3. Tạo multi-stage Dockerfile, dùng JRE phù hợp, user không root và exec-form `ENTRYPOINT`.
4. Build image, kiểm tra artifact và gắn tag version cụ thể.
5. Chạy thử REPL bằng `docker run -it`.
6. Chạy command batch và script không có TTY; xác minh output và exit code.
7. Kiểm tra mount dữ liệu, history, quyền ghi và shutdown.
8. Push image lên registry, pull lại bằng tag đã phát hành và chạy smoke test trên image đã push.

Một container Spring Shell có thể phục vụ cả người vận hành và pipeline tự động. Docker cung cấp hoặc không cung cấp TTY tùy mục tiêu; Spring Shell chọn runner tương ứng để duy trì REPL, thực thi command đơn lẻ hoặc đọc script. Khi tách rõ hai lớp này, thiết kế image, cách truyền dữ liệu, log và mã thoát sẽ dự đoán được trong cả terminal tương tác lẫn môi trường CI.

## Lưu ý khi nâng cấp lên Spring Shell 4.x

Các thuộc tính và ví dụ runner trong bài được viết cho Spring Shell 3.4.x. Spring Shell 4 thay đổi mặc định: ứng dụng interactive theo mặc định; muốn chạy non-interactive thì đặt `spring.shell.interactive.enabled=false`. Ở 4.x, `InteractionMode` đã bị loại bỏ và command không còn được đánh dấu riêng là chỉ interactive hoặc chỉ non-interactive. Vì vậy, không sao chép đoạn kiểm tra `ShellContext.getInteractionMode()` của 3.4.x sang 4.x; hãy kiểm tra migration guide và API đúng phiên bản trước khi build image.

Sự khác biệt này không thay đổi ý nghĩa của Docker flags: `-i` vẫn giữ STDIN mở và `-t` vẫn cấp PTY. Dù dùng Spring Shell 3.4 hay 4.x, TTY của container vẫn là một cấu hình I/O độc lập với chế độ runner của ứng dụng.

## Tài liệu tham khảo

- [Execution – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Shell Context – Spring Shell 3.4.2](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/shellcontext.html)
- [ScriptShellRunner API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/docs/3.4.x/api/org/springframework/shell/jline/ScriptShellRunner.html)
- [ShellRunnerAutoConfiguration API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/docs/3.4.x/api/org/springframework/shell/boot/ShellRunnerAutoConfiguration.NonePrimaryCommandConfiguration.html)
- [Spring Shell 4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [History – Spring Shell](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html)
- [docker run – Docker Docs](https://docs.docker.com/reference/cli/docker/container/run/)
- [Dockerfile reference – Docker Docs](https://docs.docker.com/reference/dockerfile/)
- [docker logs – Docker Docs](https://docs.docker.com/reference/cli/docker/container/logs/)
- [View container logs – Docker Docs](https://docs.docker.com/engine/logging/)

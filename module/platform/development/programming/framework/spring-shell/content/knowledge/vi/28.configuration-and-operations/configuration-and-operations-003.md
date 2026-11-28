# Kiểm tra thuộc tính runner, debug và lệnh có sẵn theo phiên bản

Khi một ứng dụng Spring Shell được nâng cấp hoặc triển khai ở môi trường khác, cùng một lệnh khởi động có thể cho kết quả khác nhau: ứng dụng mở REPL hay chạy command rồi thoát, lỗi chỉ hiện một dòng hay in cả stack trace, và một built-in command có xuất hiện trong `help` hay không. Các khác biệt này thường đến từ cấu hình runner, dependency có trên classpath và thay đổi giữa các major version.

Spring Shell 3.4.x có ba runner riêng cho interactive, non-interactive và script. Spring Shell 4.x đơn giản hóa thành interactive hoặc non-interactive: không còn `ScriptShellRunner` riêng, nhưng non-interactive runner vẫn có thể nhận script file qua đối số `@/path/file`; trong REPL, người dùng gọi built-in command `script --file`. Cách chẩn đoán lỗi cũng thay đổi: 3.4.x có `stacktrace`, còn 4.x dùng debug mode để in stack trace ngay khi lỗi xảy ra trong interactive shell. Vì vậy, cần xác định phiên bản trước khi áp dụng thuộc tính hoặc hướng dẫn built-in command.

Bài viết tập trung vào Spring Shell 3.4.x và 4.x, cách kiểm tra cấu hình hiệu lực, cách phân biệt debug của Spring Shell với debug của Spring Boot, và cách xác minh danh sách lệnh có sẵn trong runtime.

## Xác định phiên bản trước khi kiểm tra cấu hình

Trước khi thay đổi `application.yml`, hãy xác định phiên bản Spring Shell thực sự được đóng gói trong ứng dụng. Không suy ra phiên bản Spring Shell chỉ từ Spring Boot version hoặc từ một ví dụ trên mạng.

Với Maven, xem dependency tree:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.shell
```

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-shell \
  --configuration runtimeClasspath
```

Nếu ứng dụng đã chạy, built-in command `version` cho biết phiên bản Spring Shell. Có thể gọi trực tiếp trong REPL hoặc truyền command trong chế độ non-interactive:

```text
shell:> version
```

Tên module và package cũng thay đổi ở Spring Shell 4. Migration guide yêu cầu nâng cấp lên bản 3.4.x mới nhất trước khi chuyển sang 4.x. Spring Shell 4 dựa trên Spring Framework 7 và Spring Boot 4 trở lên; các annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` đã bị loại bỏ. Khi kiểm tra một cấu hình cũ, hãy đọc tài liệu tương ứng với major version đang chạy.

## Bảng khác biệt runner giữa 3.4.x và 4.x

| Nội dung | Spring Shell 3.4.x | Spring Shell 4.x |
| --- | --- | --- |
| Runner tương tác | `InteractiveShellRunner` | `SystemShellRunner` hoặc `JLineShellRunner` |
| Runner non-interactive | `NonInteractiveShellRunner` | `NonInteractiveShellRunner` |
| Runner đọc script khi khởi động | `ScriptShellRunner` | Không còn runner riêng; `NonInteractiveShellRunner` hỗ trợ đối số `@/path/file` |
| Cấu hình non-interactive | `spring.shell.noninteractive.enabled=true` | `spring.shell.interactive.enabled=false` |
| Cấu hình interactive | `spring.shell.interactive.enabled=true` | Interactive được bật mặc định |
| Cấu hình script runner | `spring.shell.script.enabled=true` | Không còn thuộc tính runner này |
| `InteractionMode` | Có trong `ShellContext` | Đã bị loại bỏ |
| Debug stack trace | Built-in `stacktrace` xem lỗi gần nhất | `spring.shell.debug.enabled=true` in stack trace ngay khi lỗi trong interactive mode |

Spring Shell 3.3.x thay đổi mặc định so với 3.2.x: chỉ `NonInteractiveShellRunner` được bật mặc định; các runner interactive và script phải bật rõ ràng. Trong Spring Shell 4, interactive mode được bật mặc định và có thể tắt bằng `spring.shell.interactive.enabled=false` để chạy command từ đối số tiến trình.

## Cấu hình runner trong Spring Shell 3.4.x

Với ứng dụng 3.4.x cần hỗ trợ cả REPL, command chạy một lần và script runner, có thể khai báo:

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

Ba thuộc tính điều khiển ba runner riêng biệt:

- `spring.shell.interactive.enabled`: cho phép `InteractiveShellRunner` mở REPL.
- `spring.shell.noninteractive.enabled`: cho phép `NonInteractiveShellRunner` thực thi command được truyền qua đối số tiến trình.
- `spring.shell.script.enabled`: cho phép `ScriptShellRunner` đọc script từ đối số bắt đầu bằng `@`.

`noninteractive.enabled` được bật mặc định trong 3.4.x. Hai runner còn lại không được bật mặc định từ dòng 3.3.x. Nếu ứng dụng chỉ là CLI batch, có thể giữ interactive runner tắt để tránh một command thiếu đối số rơi vào prompt chờ người dùng.

Ví dụ chạy một command bằng đối số tiến trình:

```bash
java -jar app.jar artifact list --environment staging
```

Ví dụ chạy script bằng `ScriptShellRunner`:

```bash
java -jar app.jar @/opt/app/nightly.shell
```

`ScriptShellRunner` là runner lúc khởi động; nó khác built-in command `script` mà người dùng gọi từ một REPL đang mở. Không nhầm `spring.shell.script.enabled` với việc bật/tắt built-in command `script`.

## Cấu hình runner trong Spring Shell 4.x

Spring Shell 4 chỉ chọn một shell runner khi khởi động. Mặc định ứng dụng là interactive. Để chạy command từ đối số tiến trình rồi thoát, đặt:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Khi dùng Spring Shell starter có JLine, runner interactive là `JLineShellRunner`. Nếu không có JLine trên classpath, Spring Shell dùng `SystemShellRunner` dựa trên `java.io.Console`. Non-interactive mode dùng `NonInteractiveShellRunner`.

Trong 4.x:

- Không còn `spring.shell.noninteractive.enabled` để bật một runner song song.
- Không còn `spring.shell.script.enabled` hoặc `ScriptShellRunner` riêng; `NonInteractiveShellRunner` vẫn hỗ trợ đối số `@/path/file` để chạy script khi khởi động.
- `InteractionMode` đã bị loại bỏ; command không còn được đánh dấu riêng chỉ chạy interactive hoặc non-interactive.
- Mọi command được thực thi theo mode mà ứng dụng đã chọn lúc khởi động.

Để chạy script khi khởi động ở non-interactive mode, có thể truyền `@/path/file` cho `NonInteractiveShellRunner`. Để chạy một chuỗi lệnh trong một phiên REPL đã mở, dùng built-in command `script --file`. Đây là command thực thi script bên trong shell, không phải runner khởi động riêng như `ScriptShellRunner` của 3.4.x.

## Phân biệt debug của Spring Shell và Spring Boot

Từ Spring Shell 4, debug mode của shell được bật bằng:

```yaml
spring:
  shell:
    debug:
      enabled: true
```

Khi bật, Spring Shell in stack trace của lỗi command ngay khi lỗi xảy ra trong interactive mode. Điều này thay thế cách phải chạy `stacktrace` sau khi command lỗi ở 3.x.

Không nhầm thuộc tính này với debug mode của Spring Boot:

| Cấu hình | Tác dụng |
| --- | --- |
| `spring.shell.debug.enabled=true` | Spring Shell 4 in stack trace lỗi command ngay trong interactive shell |
| `logging.level.org.springframework.shell=DEBUG` | Bật log DEBUG cho logger thuộc Spring Shell |
| `--debug` hoặc `debug=true` của Spring Boot | Bật một tập logger lõi và condition evaluation report của Boot; không có nghĩa mọi logger đều chuyển sang DEBUG |

Với Spring Shell 3.4.x, tài liệu execution sử dụng built-in command `stacktrace` để xem đầy đủ exception gần nhất. Để điều tra hoạt động framework, có thể bật logger:

```yaml
logging:
  level:
    org.springframework.shell: DEBUG
```

Nếu log console xen vào prompt hoặc output của command, có thể chuyển log sang file:

```yaml
logging:
  file:
    name: logs/shell.log
```

Hoặc tắt console log bằng pattern rỗng nếu chính sách vận hành yêu cầu:

```yaml
logging:
  pattern:
    console:
```

Spring Boot `--debug` hữu ích để xem điều kiện auto-configuration được áp dụng, nhưng không thay thế `logging.level.org.springframework.shell=DEBUG`. Tương tự, logger DEBUG không thay thế debug mode của Spring Shell 4 khi mục tiêu là in stack trace command ngay tại terminal.

### Khi nào nên bật debug?

- Trong phát triển hoặc khi tái hiện lỗi: bật debug để có stack trace và log đủ chi tiết.
- Trong production: chỉ bật theo thời gian cần điều tra; kiểm tra log có thể chứa đường dẫn, tham số hoặc dữ liệu nhạy cảm.
- Trong CI: ưu tiên lưu log vào artifact của pipeline và giữ stdout dành cho kết quả mà bước sau cần parse.
- Khi shell bị rối output: chuyển log framework sang file, không in log DEBUG vào cùng luồng với prompt.

## Danh sách built-in command trong Spring Shell 3.4.x

Một ứng dụng 3.4.x thường có các lệnh tích hợp sau, tùy dependency và cấu hình:

| Command | Công dụng |
| --- | --- |
| `help` | Liệt kê command và xem hướng dẫn chi tiết |
| `clear` | Xóa màn hình terminal |
| `quit`, `exit` | Thoát REPL và đóng application context một cách graceful |
| `stacktrace` | In stack trace của exception gần nhất |
| `script` | Đọc và chạy các command từ file trong shell hiện tại |
| `history` | Hiển thị hoặc lưu lịch sử command |
| `completion bash` | Tạo script completion cho Bash |
| `version` | Hiển thị phiên bản Spring Shell và thông tin build được cấu hình |

Lệnh `help` liệt kê cả command đang unavailable. Vì vậy, sự xuất hiện trong `help` không nhất thiết có nghĩa command có thể chạy ngay; hãy đọc lý do availability hoặc chi tiết help của command.

## Built-in command trong Spring Shell 4.x

Spring Shell 4 thay đổi danh sách và cách hoạt động của một số lệnh:

| Command | Trạng thái trong 4.x | Ghi chú |
| --- | --- | --- |
| `help` | Có | Liệt kê command; `help <command>` xem chi tiết; command cũng hỗ trợ `-h`/`--help` |
| `clear` | Có | Xóa màn hình |
| `quit`, `exit` | Có | Thoát interactive shell |
| `version` | Có | Hiển thị phiên bản Spring Shell |
| `script` | Có | Dùng `script --file <path>` để chạy file |
| `history` | Có khi có JLine | Command thuộc module `spring-shell-jline`; core-only không kéo JLine vào mặc định |
| `stacktrace` | Đã loại bỏ | Dùng `spring.shell.debug.enabled=true` để in stack trace ngay khi lỗi trong interactive mode |
| `completion` | Đã loại bỏ | Lệnh tạo script completion cho Bash bị bỏ; completion provider bên trong Spring Shell vẫn là tính năng riêng |

Trong Spring Shell 4, `spring-shell-core` không còn phụ thuộc JLine. Nếu cần line editing, JLine history hoặc built-in `history`, hãy thêm module `spring-shell-jline` hoặc starter phù hợp. Không kết luận `history` bị xóa chỉ vì built-in index của reference không liệt kê nó; kiểm tra classpath và `help` của ứng dụng thực tế.

### Cú pháp `script` thay đổi

Spring Shell 3.4.x dùng command `script` với file cục bộ làm đối số. Trong Spring Shell 4, script file được truyền qua option `--file`, và có thể dùng filesystem path hoặc Spring resource:

```text
shell:> script --file /opt/app/nightly.shell
shell:> script --file classpath:scripts/seed.shell
shell:> script --file file:/opt/app/nightly.shell
```

File chứa mỗi command trên một dòng; dòng bắt đầu bằng `//` được xem là comment. Nếu nâng cấp script tự động hóa từ 3.4 lên 4.x, hãy cập nhật cú pháp gọi và kiểm tra lại thứ tự command, output cùng exit status.

## Dùng `help` để kiểm tra command có sẵn

`help` là bước kiểm tra runtime nhanh nhất sau khi khởi động:

```text
shell:> help
shell:> help version
shell:> help script
shell:> help artifact import
```

Trong 3.4.x, `help <command>` hiển thị tên, synopsis, options, kiểu dữ liệu, tính bắt buộc và giá trị mặc định. Danh sách help được nhóm theo command group; có thể chuyển sang dạng phẳng bằng:

```yaml
spring:
  shell:
    command:
      help:
        grouping-mode: flat
```

Template danh sách và template chi tiết có thể được tùy chỉnh bằng `spring.shell.command.help.commands-template` và `spring.shell.command.help.command-template`. Các biến template chứa tên command, alias, mô tả, parameters và trạng thái availability.

Trong 4.x, command cũng có thể tự hiển thị short help:

```text
shell:> artifact import --help
shell:> artifact import -h
```

Đây là cách xác minh command đã đăng ký và xem option mà không cần chạy nghiệp vụ. Nếu command không xuất hiện, kiểm tra version, dependency, command scan/registration và property `enabled` tương ứng.

## Bật hoặc tắt built-in command

Trong Spring Shell 3.4.x, các built-in command được tạo bởi auto-configuration khi chưa có bean thay thế và property cho phép. Có thể tắt một command bằng `spring.shell.command.<command>.enabled=false`.

Ví dụ:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
      clear:
        enabled: true
      history:
        enabled: false
      stacktrace:
        enabled: true
      version:
        enabled: true
```

Các property command và các property lưu history là hai nhóm khác nhau. `spring.shell.command.history.enabled=false` tắt command `history`; `spring.shell.history.enabled=false` tắt việc lưu history xuống file. Tắt một cái không tự động có nghĩa cái còn lại cũng tắt.

Trong Spring Shell 4, các command vẫn có property enable tương ứng, nhưng `quit` có quy tắc riêng. Khi non-interactive, đặt `spring.shell.command.quit.enabled=false` sẽ loại command khỏi registry và khỏi output `help`. Trong interactive shell, `quit`/`exit` vẫn hoạt động để người dùng có thể thoát, dù property này được đặt false.

Không nên tắt `help` hoặc `quit` chỉ để làm danh sách ngắn hơn nếu người vận hành vẫn cần cách tự khám phá command hoặc thoát REPL. Nếu thay thế built-in command bằng implementation riêng, hãy kiểm tra bean override và command name để tránh đăng ký trùng.

## Cấu hình history và vị trí lưu file

Trong 3.4.x, history được lưu vào file log theo mặc định. Có thể cấu hình:

```yaml
spring:
  application:
    name: inventory-shell
  shell:
    history:
      enabled: true
      name: inventory-history.log
    config:
      location: "{userconfig}/inventory-shell"
```

- `spring.shell.history.enabled` bật hoặc tắt việc lưu history.
- `spring.shell.history.name` đặt tên file history.
- `spring.shell.config.location` chỉ định thư mục cấu hình/lưu history; `{userconfig}` đại diện thư mục cấu hình dùng chung của người dùng.
- Nếu không đặt tên file riêng, tên mặc định được suy ra từ `spring.application.name`, hoặc `spring-shell.log`.

Trong 4.x, history dựa vào JLine. `spring-shell-core` không có JLine trên classpath theo mặc định; cần dùng `spring-shell-jline` nếu muốn history command và tính năng lịch sử do JLine cung cấp. Hãy kiểm tra quyền ghi của thư mục cấu hình khi chạy bằng user service hoặc trong container.

History có thể chứa command arguments. Không đưa password, access token, private key hoặc secret vào command line nếu shell có thể ghi lịch sử. Với dữ liệu nhạy cảm, dùng cơ chế nhập an toàn hoặc secret provider thay vì truyền bí mật trực tiếp trong command.

## Kiểm tra version và built-in command theo quy trình

Một quy trình chẩn đoán ngắn có thể áp dụng khi một máy dev chạy khác máy CI:

1. Chạy `mvn dependency:tree` hoặc `gradle dependencyInsight` để xác định đúng Spring Shell runtime version.
2. Chạy `version` để xác nhận phiên bản trong artifact đang chạy.
3. Chạy `help` để xem danh sách command được đăng ký ở runtime.
4. Chạy `help <command>` hoặc `<command> --help` để xác minh option và mô tả.
5. Đối chiếu runner property với major version: 3.4.x dùng ba runner; 4.x chỉ chọn interactive/non-interactive.
6. Khi có lỗi: 3.4.x dùng `stacktrace`; 4.x bật `spring.shell.debug.enabled` trong môi trường cần điều tra.
7. Nếu thiếu `history`, kiểm tra `spring-shell-jline` và `spring.shell.command.history.enabled`.
8. Nếu thiếu `completion bash`, kiểm tra major version; lệnh tạo completion script này đã bị loại bỏ ở 4.x, dù completion provider bên trong shell vẫn có thể dùng.
9. Kiểm tra `spring.shell.history.enabled` và thư mục cấu hình nếu lịch sử không được lưu.

Ví dụ cấu hình theo version nên được tách profile thay vì dùng một file chung có mọi property:

```yaml
# application-shell-3.yml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
```

```yaml
# application-shell-4.yml
spring:
  shell:
    interactive:
      enabled: true
    debug:
      enabled: false
```

Không dùng file cấu hình 3.4.x nguyên trạng cho 4.x. Một số property cũ có thể bị bỏ qua vì không còn binding tương ứng, dẫn đến ứng dụng khởi động thành công nhưng hành vi khác dự kiến.

## Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| 3.4.x không mở REPL | `InteractiveShellRunner` chưa bật | Đặt `spring.shell.interactive.enabled=true` |
| 3.4.x không chạy `@/script` | `ScriptShellRunner` chưa bật | Đặt `spring.shell.script.enabled=true` |
| 3.4.x chạy non-interactive nhưng không mong muốn | Runner non-interactive đang bật và nhận command args | Kiểm tra `spring.shell.noninteractive.enabled` và cách gọi tiến trình |
| 4.x không mở REPL | `spring.shell.interactive.enabled=false` | Bật lại `true` hoặc bỏ property để dùng mặc định |
| 4.x bỏ qua `spring.shell.script.enabled` | 4.x không còn `ScriptShellRunner` | Gọi built-in `script --file` trong shell |
| Không có `stacktrace` trong 4.x | Command đã bị loại bỏ | Bật `spring.shell.debug.enabled=true` khi cần stack trace |
| Không có `completion bash` trong 4.x | Built-in completion command đã bị loại bỏ | Cấu hình completion theo Bash/Zsh bên ngoài |
| Không thấy `history` trong 4.x | Thiếu `spring-shell-jline` hoặc command bị disable | Thêm JLine module và kiểm tra `help`/property |
| `history` có nhưng file không được ghi | Persistence history bị tắt hoặc thư mục không ghi được | Kiểm tra `spring.shell.history.enabled`, `name` và `config.location` |
| `--debug` không in stack trace command | Nhầm debug của Spring Boot với debug của Spring Shell | Dùng `spring.shell.debug.enabled` trong 4.x hoặc `stacktrace` trong 3.4.x |
| `help` không có command tự viết | Bean chưa được scan/đăng ký hoặc profile không hoạt động | Kiểm tra command registration và profile runtime |
| `help` có command nhưng chạy bị từ chối | Command đang unavailable | Xem lý do availability và trạng thái ứng dụng |
| `quit` vẫn hoạt động dù disabled trong 4.x | Interactive shell luôn giữ cách thoát | Đây là hành vi có chủ đích của interactive shell |

## Kiểm thử cấu hình trước khi phát hành

Không chỉ kiểm tra ứng dụng khởi động thành công. Hãy xác minh hành vi thực tế theo version:

| Trường hợp | Kiểm tra |
| --- | --- |
| 3.4.x interactive | REPL xuất hiện và nhận được nhiều command |
| 3.4.x non-interactive | Một command được truyền qua process args và ứng dụng kết thúc |
| 3.4.x script runner | `@/path/file` chạy script khi `spring.shell.script.enabled=true` |
| 4.x interactive | REPL mặc định được bật |
| 4.x non-interactive | `spring.shell.interactive.enabled=false` chạy command từ args rồi thoát |
| Built-in help | Danh sách command khớp dependency và property đã cấu hình |
| Debug 3.4.x | Lỗi command hiển thị thông báo gọn và `stacktrace` in chi tiết |
| Debug 4.x | Bật debug mode in stack trace ngay sau lỗi trong interactive shell |
| History | Command history được lưu đúng file hoặc không lưu theo policy |
| JLine | History và khả năng nhập dòng hoạt động khi module JLine có mặt |
| Version | `version` báo đúng Spring Shell version trong artifact phát hành |
| Built-in command bị tắt | Command không xuất hiện/không được đăng ký theo property, ngoại trừ quy tắc `quit` trong interactive 4.x |

Nên chạy smoke test trên chính JAR hoặc image sẽ phát hành. Unit test cấu hình bean không chứng minh runner được chọn đúng khi `ApplicationRunner` xử lý đối số thực tế.

## Quy trình vận hành theo phiên bản

1. Xác định Spring Shell version từ dependency tree và command `version`.
2. Chọn cấu hình runner đúng major version; không mang property `script.enabled` của 3.4 sang 4.x.
3. Xác định có cần JLine hay không, đặc biệt khi cần history và terminal line editing ở 4.x.
4. Chọn cách debug: `stacktrace`/logger DEBUG ở 3.4.x; `spring.shell.debug.enabled` ở 4.x.
5. Dùng `help` để kiểm tra built-in và command nghiệp vụ được đăng ký.
6. Tắt built-in command bằng property `spring.shell.command.<name>.enabled` chỉ khi có lý do vận hành rõ ràng.
7. Cấu hình vị trí và chính sách history, đồng thời tránh ghi secret vào lịch sử.
8. Chạy smoke test cho interactive, non-interactive, script, lỗi và shutdown trước khi phát hành.

Khi kiểm tra cấu hình Spring Shell, phiên bản là điểm bắt đầu để hiểu đúng runner, debug và built-in command. Spring Shell 3.4.x còn ba runner và lệnh `stacktrace`/`completion`; Spring Shell 4.x mặc định interactive, dùng debug mode cho stack trace và thay đổi cách chạy script. Kết hợp dependency inspection, `version`, `help` và kiểm thử trên artifact thực tế sẽ giúp phát hiện sớm cấu hình cũ hoặc dependency thiếu trước khi đưa CLI vào vận hành.

## Tài liệu tham khảo

- [Execution – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Shell Context – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/shellcontext.html)
- [Help – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/help.html)
- [Stacktrace – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/stacktrace.html)
- [History – Spring Shell 3.3](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html)
- [Script – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/script.html)
- [ScriptShellRunner API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html)
- [Logging – Spring Shell 3.4.2](https://docs.spring.io/spring-shell/reference/3.4/customization/logging.html)
- [StandardCommandsAutoConfiguration API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/boot/StandardCommandsAutoConfiguration.html)
- [Execution – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/execution.html)
- [Built-In Commands – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/builtin/index.html)
- [Help – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Script – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [NonInteractiveShellRunner API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Exit – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/builtin/exit.html)
- [Version – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/builtin/version.html)
- [Spring Shell v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

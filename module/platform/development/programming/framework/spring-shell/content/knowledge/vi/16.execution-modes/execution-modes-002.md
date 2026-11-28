# Phân biệt cách chọn runner ở 3.x và 4.x

Spring Shell sử dụng `ShellRunner` để quyết định cách ứng dụng nhận và thực thi đầu vào. Ở Spring Shell 3.x, ứng dụng có thể bật nhiều runner cùng lúc; runner mặc định của Boot xem các đối số khởi động và lần lượt chọn runner phù hợp. Từ Spring Shell 4.x, ứng dụng chọn một runner cho application context ngay khi khởi động. Đây là thay đổi quan trọng khi nâng cấp, vì cùng một câu lệnh khởi động có thể được xử lý theo cách khác giữa hai thế hệ.

Bài học này tập trung vào việc chọn runner cho ba nhu cầu: mở phiên terminal để nhập nhiều command, chạy một command rồi thoát, và thực thi một tệp script. Nắm rõ cơ chế lựa chọn giúp cấu hình CLI phù hợp khi chạy thủ công, trong CI/CD hoặc qua lịch tự động.

## 1. Runner là thành phần nào?

`ShellRunner` là thành phần thực thi shell. Runner quyết định cách nhận đầu vào, giữ tiến trình mở để chờ lệnh hay thực thi đầu vào có sẵn rồi kết thúc. Spring Shell cung cấp các runner cho chế độ tương tác, chế độ không tương tác và script; tên lớp và cách đăng ký chúng thay đổi giữa 3.x và 4.x.

| Nhu cầu | Hành vi mong muốn | Runner thường dùng |
| --- | --- | --- |
| Người dùng làm việc trực tiếp trong terminal | Hiển thị prompt, chờ nhiều command và tiếp tục sau mỗi lần chạy | Interactive runner |
| Script hoặc CI gọi một tác vụ | Nhận command từ đối số lúc khởi động, chạy rồi kết thúc | Non-interactive runner |
| Tệp chứa nhiều command đã chuẩn bị | Đọc các dòng trong tệp, thực thi theo thứ tự rồi kết thúc | Script runner ở 3.x; script được xử lý bởi non-interactive runner ở 4.x |

Không nên nhầm `ShellRunner` với command handler. Command handler thực hiện nghiệp vụ như `user list`; runner quyết định đầu vào đó được lấy từ terminal, đối số tiến trình hay tệp script.

## 2. Cách chọn runner trong Spring Shell 3.x

Trong Spring Shell 3.x, `ShellApplicationRunner` nhận `ApplicationArguments` của Spring Boot và chọn `ShellRunner` phù hợp. Một application context chỉ có một `ShellApplicationRunner`, nhưng runner có thể được thay thế nếu ứng dụng cần tùy biến cách khởi động.

Ba runner tiêu biểu của mô hình 3.x là:

- `InteractiveShellRunner`: mở vòng lặp tương tác, thường dùng JLine để đọc dòng lệnh và hiển thị prompt.
- `NonInteractiveShellRunner`: xử lý command được truyền từ đối số tiến trình mà không mở vòng lặp chờ nhập.
- `ScriptShellRunner`: nhận đối số chỉ tới tệp script và thực thi các command trong tệp.

### Mặc định thay đổi từ 3.2 sang 3.3

Mặc định của runner đã thay đổi trong dòng 3.x:

| Phiên bản | Runner được bật mặc định | Ý nghĩa cấu hình |
| --- | --- | --- |
| 3.2.x trở về trước | Cả interactive, non-interactive và script | Nhiều runner cùng có thể tham gia chọn cách xử lý đầu vào |
| 3.3.x và 3.4.x | Chỉ `NonInteractiveShellRunner` | Muốn mở prompt hoặc chạy script phải bật runner tương ứng |

Trong 3.3.x trở đi, các thuộc tính bật/tắt runner là:

| Thuộc tính | Runner điều khiển | Mặc định từ 3.3.x |
| --- | --- | --- |
| `spring.shell.interactive.enabled` | `InteractiveShellRunner` | `false` |
| `spring.shell.noninteractive.enabled` | `NonInteractiveShellRunner` | `true` |
| `spring.shell.script.enabled` | `ScriptShellRunner` | `false` |

Ví dụ bật cả phiên tương tác và khả năng chạy script:

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

Ở cấu hình trên, ứng dụng có thể phục vụ cả người dùng terminal và quy trình tự động. Runner được xét theo thứ tự ưu tiên và khả năng xử lý đầu vào; `InteractiveShellRunner` có độ ưu tiên thấp hơn các runner script và non-interactive. Vì vậy, không nên hiểu rằng chỉ cần bật interactive là mọi đối số khởi động sẽ bị bỏ qua để mở prompt.

Nếu ứng dụng chỉ cần một command từ đối số, giữ non-interactive và tắt hai runner còn lại:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Nếu ứng dụng chỉ dùng prompt tương tác:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: false
    script:
      enabled: false
```

Với 3.2.x, cần kiểm tra cấu hình mặc định và phiên bản thực tế trước khi áp dụng các giả định của 3.3.x. Khi muốn hành vi nhất quán giữa các môi trường, nên khai báo tường minh những runner cần bật thay vì dựa vào mặc định theo phiên bản.

## 3. Runner 3.x nhận đầu vào như thế nào?

Khi ứng dụng được khởi động, Spring Boot chuyển các đối số tiến trình tới `ShellApplicationRunner`. Runner phù hợp sẽ nhận phần đầu vào của mình:

```text
java -jar app.jar
```

Nếu `InteractiveShellRunner` được bật và không có runner ưu tiên cao hơn nhận đầu vào, ứng dụng mở prompt:

```text
shell:> user list
Danh sách người dùng
shell:>
```

Khi truyền một command cùng đối số:

```text
java -jar app.jar user list
```

`NonInteractiveShellRunner` xử lý command, in kết quả và kết thúc tiến trình. Nếu cần chạy tệp script, bật `spring.shell.script.enabled` và truyền đường dẫn script theo cú pháp `@`:

```text
java -jar app.jar @commands.txt
```

Ví dụ nội dung `commands.txt`:

```text
user list
project list
system status
```

Script runner nhận tệp và thực thi các command theo nội dung đã chuẩn bị. Hãy kiểm tra cú pháp script, cách xử lý lỗi và mã thoát theo đúng phiên bản Spring Shell đang dùng; việc bật script runner không tự biến một tệp bất kỳ thành script hợp lệ.

### Thứ tự runner và cách tùy biến

Trong 3.x, `ShellRunner` có thể được xét theo độ ưu tiên. Runner không xử lý đầu vào sẽ nhường cơ hội cho runner tiếp theo; runner đã thực thi sẽ báo rằng nó đã xử lý để không gọi thêm runner khác. `InteractiveShellRunner` có độ ưu tiên thấp hơn `ScriptShellRunner` và `NonInteractiveShellRunner`.

Từ 3.3.x, phương thức `run(String[] args)` là API chính của `ShellRunner`. Các phương thức cũ nhận `ApplicationArguments` đã bị deprecated để chuyển dần sang API dùng mảng chuỗi. Nếu tự triển khai runner hoặc customizer, hãy dùng API phù hợp với phiên bản 3.x cụ thể và không viết mới dựa trên phương thức đã deprecated.

## 4. Cách chọn runner trong Spring Shell 4.x

Spring Shell 4.x thay đổi mô hình: mỗi application context chỉ sử dụng một `ShellRunner`. Ứng dụng chọn chế độ khi khởi động; không còn cơ chế bật đồng thời ba runner để lần lượt cạnh tranh xử lý cùng đầu vào.

Ba implementation chính trong 4.x là:

- `SystemShellRunner`: phiên tương tác dựa trên `java.io.Console` của JDK, không cần JLine.
- `JLineShellRunner`: phiên tương tác dựa trên JLine, có lịch sử, completion và các khả năng terminal do JLine cung cấp; cần dependency `spring-shell-jline` hoặc starter có JLine.
- `NonInteractiveShellRunner`: thực thi command hoặc script đã truyền vào rồi kết thúc.

Mặc định Spring Shell 4.x chạy ở chế độ tương tác, kể cả khi tiến trình có command-line arguments. Nếu ứng dụng dùng Spring Shell starter có JLine trên classpath, runner tương tác là `JLineShellRunner`; nếu không có JLine, framework dùng `SystemShellRunner`.

### Chuyển sang chế độ không tương tác

Đặt thuộc tính `spring.shell.interactive.enabled` thành `false` để chọn `NonInteractiveShellRunner`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó, truyền command ở đối số tiến trình:

```bash
java -jar app.jar user list
```

Runner thực thi command rồi kết thúc. Để chạy script, dùng tiền tố `@` trước đường dẫn tệp:

```bash
java -jar app.jar @commands.txt
```

Khác với 3.x, 4.x không có một `ScriptShellRunner` riêng trong danh sách runner. `NonInteractiveShellRunner` đảm nhiệm cả việc chạy một command lẫn đọc script. Không dùng thuộc tính `spring.shell.script.enabled` của 3.x như cách chọn một runner độc lập trong 4.x.

### Chọn runner tương tác

Để mở shell tương tác, giữ mặc định hoặc đặt tường minh:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Khi có JLine trên classpath, ứng dụng dùng `JLineShellRunner`; nếu không, ứng dụng dùng `SystemShellRunner`. Vì vậy, dependency có ảnh hưởng đến trải nghiệm terminal dù thuộc tính `interactive.enabled` giống nhau.

Nếu cần thay đổi logic khởi động trong ứng dụng Spring Boot, Spring Shell đăng ký bean `ApplicationRunner` tên `springShellApplicationRunner` để gọi runner đã cấu hình. Có thể cung cấp `ApplicationRunner` riêng cùng tên để thay thế logic mặc định. Với ứng dụng không dùng Spring Boot, có thể lấy `ShellRunner` từ application context và gọi `run(args)` sau khi cấu hình command.

## 5. Bảng so sánh cách chọn runner 3.x và 4.x

| Tiêu chí | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Số runner trong một application context | Có thể bật nhiều runner | Chỉ một `ShellRunner` được dùng |
| Thành phần chọn runner | `ShellApplicationRunner` nhận `ApplicationArguments` và chọn runner phù hợp | `ShellRunner` được cấu hình cho ứng dụng ngay từ đầu; Boot cung cấp `ApplicationRunner` để gọi runner |
| Mặc định interactive | 3.3.x/3.4.x tắt nếu không bật thuộc tính | Bật mặc định |
| Mặc định non-interactive | Bật từ 3.3.x | Được chọn khi `interactive.enabled=false` |
| Script | `ScriptShellRunner` riêng, cần `spring.shell.script.enabled=true` từ 3.3.x | Script được `NonInteractiveShellRunner` xử lý bằng đối số `@file` |
| Chọn tương tác hay một command | Dựa vào runner được bật và runner nào nhận đầu vào | Đặt `spring.shell.interactive.enabled` trước khi khởi động |
| Command chỉ dùng trong một chế độ | Có `InteractionMode` và metadata command tương ứng | Không còn `InteractionMode`; command dùng được ở cả hai chế độ |
| API runner | `run(String[])` là API chính từ 3.3.x; API nhận `ApplicationArguments` cũ bị deprecated | `ShellRunner.run(String[] args)` |

Sự thay đổi quan trọng nhất khi nâng cấp là cách lựa chọn chế độ. Trong 3.x, ứng dụng có thể bật nhiều runner và dựa vào thứ tự xử lý; trong 4.x, cấu hình `interactive.enabled` xác định runner cho toàn ứng dụng.

## 6. Thay đổi về InteractionMode của command

Spring Shell 3.x cho phép giới hạn một số command theo chế độ. Với legacy annotation, `@ShellMethod` có thuộc tính `interactionMode`; enum `InteractionMode` có các giá trị:

- `INTERACTIVE`: command chỉ phù hợp với phiên tương tác.
- `NONINTERACTIVE`: command chỉ phù hợp khi chạy command trực tiếp hoặc qua script.
- `ALL`: command có thể được dùng trong cả hai chế độ.

Ví dụ legacy API 3.x:

```java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class SessionCommands {

    @ShellMethod(
        key = "session close",
        value = "Đóng phiên tương tác.",
        interactionMode = InteractionMode.INTERACTIVE
    )
    public void closeSession() {
        // Kết thúc phiên terminal tương tác.
    }
}
```

Khi nâng lên Spring Shell 4.x, `InteractionMode` đã bị loại bỏ và command không còn được đánh dấu riêng cho interactive hoặc non-interactive. Tất cả command được đăng ký trong ứng dụng đều có thể được gọi trong chế độ đã chọn. Vì vậy, hãy rà soát những command phụ thuộc vào prompt, xác nhận thủ công hoặc vòng lặp phiên; chúng cần tự xử lý ngữ cảnh phù hợp hoặc được thiết kế lại cho chế độ không tương tác.

Ví dụ, một command cần hỏi người dùng xác nhận trước khi xóa dữ liệu có thể phù hợp với phiên tương tác nhưng không phù hợp với CI. Khi chuyển sang 4.x, hãy cung cấp option rõ ràng như `--confirm` hoặc `--dry-run` và yêu cầu giá trị tường minh khi chạy tự động, thay vì dựa vào `InteractionMode` để ẩn command khỏi một runner.

## 7. Cấu hình mẫu theo từng mục tiêu

### 3.x: CLI ưu tiên chạy một command

```yaml
spring:
  shell:
    interactive:
      enabled: false
    noninteractive:
      enabled: true
    script:
      enabled: false
```

Lệnh gọi:

```bash
java -jar app.jar report daily --date 2026-11-26
```

### 3.x: hỗ trợ terminal và script

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

Lệnh gọi:

```bash
java -jar app.jar
java -jar app.jar @commands.txt
```

### 4.x: mặc định tương tác

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Lệnh gọi:

```bash
java -jar app.jar
```

### 4.x: chỉ chạy command hoặc script

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Lệnh gọi:

```bash
java -jar app.jar user list
java -jar app.jar @commands.txt
```

Khi triển khai, nên tách cấu hình theo profile hoặc theo biến môi trường. Ví dụ, profile `terminal` bật interactive, còn profile `automation` đặt `spring.shell.interactive.enabled=false`. Điều này giúp cách chạy của CI/CD không phụ thuộc vào cấu hình máy phát triển.

## 8. Những lỗi thường gặp khi chọn runner

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Ứng dụng 3.3.x/3.4.x khởi động nhưng không hiện prompt | `InteractiveShellRunner` chưa được bật | Đặt `spring.shell.interactive.enabled=true` |
| 3.x chạy command một lần nhưng không nhận script | `ScriptShellRunner` chưa bật | Đặt `spring.shell.script.enabled=true` |
| Script không được nhận diện | Thiếu tiền tố `@`, sai đường dẫn hoặc runner script chưa bật | Kiểm tra đối số, đường dẫn và cấu hình script |
| 3.x mở prompt dù muốn chạy một command | Interactive runner đang bật và cấu hình/đầu vào không chọn runner như dự kiến | Kiểm tra runner được bật và thứ tự ưu tiên; tắt interactive nếu chỉ muốn chạy tự động |
| 4.x mở prompt dù đã truyền command | Interactive mặc định vẫn bật | Đặt `spring.shell.interactive.enabled=false` |
| 4.x không có lịch sử hoặc completion như mong đợi | Ứng dụng đang dùng `SystemShellRunner` vì không có JLine trên classpath | Thêm `spring-shell-jline` hoặc starter phù hợp nếu cần JLine |
| Không biên dịch được `InteractionMode` sau nâng cấp | Enum đã bị loại bỏ trong 4.x | Xóa metadata mode và thiết kế command phù hợp với chế độ chạy |
| Không tìm thấy `spring.shell.script.enabled` trong cấu hình 4.x | Script runner riêng của 3.x không còn | Dùng `NonInteractiveShellRunner` với đối số `@file` |

## 9. Checklist trước khi triển khai

- Xác nhận chính xác ứng dụng đang dùng Spring Shell 3.x hay 4.x.
- Với 3.x, kiểm tra khác biệt mặc định giữa 3.2.x và 3.3.x trở lên.
- Liệt kê runner cần bật và đặt các thuộc tính tương ứng rõ ràng.
- Với 3.x, kiểm tra thứ tự ưu tiên và khả năng xử lý đầu vào của từng runner.
- Với 4.x, chọn interactive hoặc non-interactive trước khi khởi động application context.
- Nếu cần JLine trong 4.x, bảo đảm dependency JLine/starter có trên classpath.
- Chuyển script sang cú pháp `@file` phù hợp với phiên bản.
- Rà soát command có `InteractionMode` trong mã 3.x trước khi nâng cấp.
- Kiểm thử khởi động không có đối số, có command arguments và có script file.
- Kiểm tra hành vi khi chạy từ terminal, CI/CD và môi trường triển khai thực tế.

## Tài liệu tham khảo

- [Spring Shell 3.3 — Execution and Shell Runners](https://docs.spring.io/spring-shell/reference/3.3/execution.html)
- [Spring Shell 3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.x — Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Shell 4.0.4 — ShellRunnerAutoConfiguration API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/ShellRunnerAutoConfiguration.html)
- [Spring Shell 4.0.3 — NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)

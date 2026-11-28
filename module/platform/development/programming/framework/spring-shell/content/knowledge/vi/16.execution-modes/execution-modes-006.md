# SystemShellRunner, JLineShellRunner và NonInteractiveShellRunner ở 4.x

## 1. ShellRunner điều khiển cách ứng dụng nhận và thực thi lệnh

Trong Spring Shell 4.x, **ShellRunner** là thành phần điều khiển vòng đời thực thi shell. Runner nhận mảng đối số ban đầu, đọc lệnh từ nguồn input phù hợp, chuyển lệnh đến parser và command registry, sau đó quyết định shell tiếp tục chờ lệnh hay kết thúc tiến trình.

Hợp đồng chính của runner là phương thức:

~~~java
void run(String[] args) throws Exception;
~~~

Spring Shell 4.x cung cấp ba triển khai:

| Runner | Chế độ | Nguồn input | Trường hợp sử dụng |
|---|---|---|---|
| `SystemShellRunner` | Interactive | `java.io.Console` của JDK | Shell tương tác gọn, không cần JLine. |
| `JLineShellRunner` | Interactive | JLine `LineReader` và terminal | Shell cần chỉnh sửa dòng lệnh, lịch sử, completion và trải nghiệm terminal phong phú. |
| `NonInteractiveShellRunner` | Non-interactive | Đối số tiến trình hoặc file script | Chạy một command hoặc một chuỗi command từ script/CI. |

Mỗi application context chỉ có một `ShellRunner` được chọn để chạy. Trong ứng dụng Spring Boot, Spring Shell đăng ký `ApplicationRunner` tên `springShellApplicationRunner` để gọi runner đã cấu hình khi ứng dụng khởi động.

## 2. Phân biệt hai chế độ thực thi

Spring Shell 4.x yêu cầu chọn chế độ interactive hoặc non-interactive ngay khi ứng dụng khởi động. Property điều khiển là:

~~~properties
spring.shell.interactive.enabled=true
~~~

Giá trị mặc định là `true`. Khi bật, ứng dụng khởi động shell tương tác và tiếp tục chờ người dùng nhập command.

Để chạy command được truyền qua tham số tiến trình rồi kết thúc, đặt:

~~~properties
spring.shell.interactive.enabled=false
~~~

Khi đó, Spring Shell chọn `NonInteractiveShellRunner`. Một thay đổi quan trọng so với nhánh cũ là Spring Shell 4.x vẫn bật interactive mode ngay cả khi tiến trình nhận command-line arguments. Có tham số đầu vào không tự động làm ứng dụng chuyển sang non-interactive mode.

Chế độ được chọn ở cấp ứng dụng, không gắn riêng vào từng command. Cùng một command có thể được gọi trong phiên tương tác hoặc từ process arguments/script. Các annotation và enum `InteractionMode` của mô hình cũ đã bị loại bỏ. Một số lệnh như `exit` chỉ có ý nghĩa trong phiên interactive vì non-interactive runner kết thúc sau khi thực thi đầu vào.

~~~mermaid
flowchart TD
    A[Ứng dụng Spring Shell khởi động] --> B{spring.shell.interactive.enabled?}
    B -->|true hoặc không khai báo| C{JLine có trên classpath?}
    C -->|Có| D[JLineShellRunner]
    C -->|Không| E[SystemShellRunner]
    D --> F[Đọc nhiều lệnh trong phiên tương tác]
    E --> F
    B -->|false| G[NonInteractiveShellRunner]
    G --> H[Nhận command hoặc script từ args]
    H --> I[Thực thi rồi kết thúc]
~~~

Trong ứng dụng Spring Boot, cách đơn giản là đặt property trong `application.properties` hoặc cấu hình qua biến môi trường. Không nên dựa vào việc Spring Shell tự suy luận chế độ từ số lượng tham số dòng lệnh.

## 3. SystemShellRunner: shell tương tác dựa trên Console của JDK

`SystemShellRunner` nằm trong package `org.springframework.shell.core` và sử dụng `ConsoleInputProvider`, dựa trên `java.io.Console` của JDK. Đây là lựa chọn nhẹ khi ứng dụng cần một vòng lặp nhập lệnh cơ bản và không cần các tính năng terminal do JLine cung cấp.

Đặc điểm:

- Thuộc module core của Spring Shell.
- Không yêu cầu thêm thư viện JLine.
- Đọc input từ system console và thực thi command trong cùng một phiên.
- Dùng chung `CommandParser` và `CommandRegistry` như các runner còn lại.
- Phù hợp với công cụ nội bộ hoặc môi trường terminal đơn giản.

Spring Shell 4.x sử dụng `SystemShellRunner` khi chế độ interactive được bật nhưng JLine không có trên classpath. Vì vậy, khi chỉ dùng core mà không thêm module JLine, đây là runner tương tác có thể được auto-configuration chọn.

Ví dụ trải nghiệm:

~~~text
shell:>user list
shell:>user show --id=42
shell:>help
shell:>exit
~~~

Các lệnh trên chỉ minh họa một phiên làm việc. Command thực tế phụ thuộc vào những command mà ứng dụng đã đăng ký. `SystemShellRunner` không cung cấp các tiện ích nhập liệu nâng cao của JLine như lịch sử dòng lệnh và completion bằng Tab.

## 4. JLineShellRunner: shell tương tác với JLine

`JLineShellRunner` nằm trong package `org.springframework.shell.jline`, thuộc module `spring-shell-jline`. Runner này kết nối Spring Shell với JLine để đọc dòng lệnh và làm việc với terminal.

JLine bổ sung các khả năng thường cần trong một shell tương tác:

- Chỉnh sửa dòng lệnh trước khi thực thi.
- Di chuyển con trỏ và thao tác với văn bản đang nhập.
- Lưu và duyệt lịch sử lệnh.
- Tự hoàn thành command, lệnh con, option và giá trị được hỗ trợ.
- Tô sáng hoặc trình bày dòng lệnh theo cấu hình terminal.
- Tích hợp các thành phần terminal UI của Spring Shell.

Spring Shell 4.x không còn kéo JLine vào module core. Nếu dùng starter có tích hợp JLine, interactive mode sử dụng `JLineShellRunner`. Nếu ứng dụng chỉ có core và không có JLine trên classpath, Spring Shell chọn `SystemShellRunner`.

Khi cần thêm JLine trực tiếp vào Maven project đã có dependency management phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
~~~

Nếu dự án dùng Spring Shell starter đã cung cấp JLine, không cần khai báo trùng dependency này. Hãy kiểm tra dependency tree để biết module nào đang đưa JLine vào classpath.

Ví dụ trải nghiệm với JLine:

~~~text
shell:>user cr<Tab>
shell:>user create --<Tab>
shell:>history
~~~

Kết quả completion phụ thuộc command và provider đã đăng ký. JLine cung cấp cơ chế nhập liệu và gọi completion; nội dung gợi ý vẫn đến từ metadata command hoặc `CompletionProvider` của ứng dụng.

## 5. NonInteractiveShellRunner: chạy command hoặc script rồi kết thúc

`NonInteractiveShellRunner` nằm trong package `org.springframework.shell.core`. Runner này không mở vòng lặp REPL. Nó nhận command từ mảng đối số, thực thi rồi kết thúc ứng dụng. Đây là lựa chọn phù hợp cho script, tác vụ CI/CD, cron job hoặc công cụ được gọi từ một chương trình khác.

Ví dụ cấu hình:

~~~properties
spring.shell.interactive.enabled=false
~~~

Sau khi đóng gói ứng dụng, gọi một command:

~~~bash
java -jar target/admin-cli.jar user list
java -jar target/admin-cli.jar user show --id=42
java -jar target/admin-cli.jar user disable --id=42 --reason="account expired"
~~~

Ứng dụng khởi tạo Spring context, phân tích command được truyền vào, gọi command tương ứng rồi kết thúc. Không có prompt chờ nhập lệnh tiếp theo.

### Chạy một file script

`NonInteractiveShellRunner` hỗ trợ chạy một file chứa nhiều command. Đặt ký tự `@` trước tên file khi truyền vào tiến trình:

~~~bash
java -jar target/admin-cli.jar @maintenance.commands
~~~

Ví dụ file `maintenance.commands`:

~~~text
user list
user show --id=42
report run --format=json
~~~

Runner đọc và thực thi các command trong file theo thứ tự. File script nên chứa các command đã được đăng ký trong ứng dụng và sử dụng cú pháp giống khi nhập trực tiếp vào shell. Đường dẫn file được phân giải theo working directory của tiến trình; nếu chạy từ thư mục khác, hãy truyền đường dẫn phù hợp.

### Chạy bằng biến môi trường

Có thể bật non-interactive mode mà không cần sửa `application.properties`.

Trên Bash:

~~~bash
SPRING_SHELL_INTERACTIVE_ENABLED=false java -jar target/admin-cli.jar user list
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_SHELL_INTERACTIVE_ENABLED = "false"
java -jar .\target\admin-cli.jar user list
Remove-Item Env:SPRING_SHELL_INTERACTIVE_ENABLED
~~~

Đối với pipeline, hãy kiểm tra mã thoát của tiến trình và quy ước ánh xạ `ExitStatus` mà ứng dụng đã cấu hình. Không nên chỉ dựa vào nội dung được in ra để kết luận command thành công.

## 6. Chọn runner nào?

| Nhu cầu | Runner phù hợp | Lý do |
|---|---|---|
| CLI đơn giản, người dùng nhập lệnh trực tiếp, không cần JLine | `SystemShellRunner` | Dùng Console của JDK, không thêm dependency terminal. |
| CLI tương tác có Tab completion, history và chỉnh sửa dòng | `JLineShellRunner` | Tích hợp JLine và các thành phần terminal của Spring Shell. |
| Chạy đúng một command rồi kết thúc | `NonInteractiveShellRunner` | Nhận command từ process arguments và không mở REPL. |
| Chạy một chuỗi command định kỳ hoặc trong CI | `NonInteractiveShellRunner` | Đọc file script qua cú pháp `@file`. |

Các runner cùng thực thi command đã đăng ký. Khác biệt chính nằm ở cách nhận input và vòng đời phiên làm việc, không phải ở logic nghiệp vụ của command.

## 7. Một runner trong một application context

Spring Shell 4.x chỉ sử dụng một `ShellRunner` trong mỗi application context. Ứng dụng chọn runner thông qua cấu hình và các module có mặt trên classpath:

- `spring.shell.interactive.enabled=true` chọn chế độ tương tác.
- Khi có JLine integration, runner tương tác là `JLineShellRunner`.
- Khi không có JLine integration, runner tương tác là `SystemShellRunner`.
- `spring.shell.interactive.enabled=false` chọn `NonInteractiveShellRunner`.

Không nên tự đăng ký cả ba runner rồi mong framework tự chuyển qua lại trong cùng một lần chạy. Nếu cần kiểm soát cách khởi động riêng, Spring Boot có bean `ApplicationRunner` tên `springShellApplicationRunner`; tài liệu Spring Shell cho phép thay thế bean này để tùy chỉnh startup logic. Khi làm vậy, cần bảo đảm chỉ có một luồng khởi chạy runner và không vô tình gọi shell hai lần.

## 8. Những thay đổi quan trọng khi chuyển từ 3.x sang 4.x

Spring Shell 4.x thay đổi cách lựa chọn chế độ chạy và tổ chức module:

| Spring Shell 3.x | Spring Shell 4.x |
|---|---|
| Việc chọn interactive/non-interactive có thể dựa vào cách truyền tham số và cấu hình runner cũ. | Interactive mode bật mặc định, kể cả khi có command-line arguments; đặt `spring.shell.interactive.enabled=false` để chạy non-interactive. |
| Core gắn chặt hơn với cấu hình JLine trong các ứng dụng phổ biến. | Core không còn phụ thuộc JLine; thêm `spring-shell-jline` khi cần JLine. |
| Các API runner và package sử dụng namespace cũ. | `ShellRunner`, `SystemShellRunner` và `NonInteractiveShellRunner` nằm dưới `org.springframework.shell.core`; `JLineShellRunner` nằm dưới `org.springframework.shell.jline`. |
| Command có thể được đánh dấu interactive/non-interactive bằng `InteractionMode`. | `InteractionMode` đã bị loại bỏ; chế độ được chọn ở cấp ứng dụng khi khởi động. |

Vì vậy, khi nâng cấp:

1. Kiểm tra dependency để xác định JLine có được đưa vào classpath hay không.
2. Chọn rõ interactive hoặc non-interactive bằng `spring.shell.interactive.enabled`.
3. Cập nhật các import runner sang package 4.x.
4. Bỏ cấu hình `InteractionMode` cũ khỏi command.
5. Kiểm thử lại lệnh chạy từ tham số tiến trình và script `@file`.
6. Xác nhận mã thoát và output trong pipeline sau khi chuyển runner.

Lưu ý tương thích: Spring Shell 4.x dựa trên Spring Framework 7; khi dùng Spring Boot, cần Spring Boot 4 trở lên. Hãy kiểm tra ma trận phiên bản trước khi nâng cấp ứng dụng hiện tại.

## 9. Kiểm thử chế độ chạy

Nên kiểm thử cả ba runner theo cách ứng dụng sẽ được triển khai:

**SystemShellRunner hoặc JLineShellRunner:** xác nhận ứng dụng mở prompt, nhận nhiều command trong một phiên và kết thúc khi người dùng gọi lệnh thoát. Với JLine, kiểm tra thêm history, completion và thao tác chỉnh sửa dòng.

**NonInteractiveShellRunner:** xác nhận command từ process arguments được thực thi một lần rồi tiến trình kết thúc; command lỗi trả mã thoát phù hợp; script `@file` chạy theo thứ tự và không chờ prompt.

**Cấu hình khởi động:** xác nhận property `spring.shell.interactive.enabled` được nạp đúng ở từng profile hoặc môi trường. Đặc biệt, kiểm thử trường hợp có command-line arguments nhưng property interactive vẫn ở mặc định `true` để tránh hiểu nhầm rằng chỉ truyền command là đủ chuyển sang non-interactive.

Trong kiểm thử tích hợp, nên chạy tiến trình con với cấu hình tương ứng và kiểm tra stdout, stderr, mã thoát cùng thời gian kết thúc. Kiểm thử command riêng lẻ không thay thế được kiểm thử runner vì runner quyết định cách tiến trình nhận input và kết thúc.

## 10. Quy trình chọn chế độ cho ứng dụng

Trước khi phân phối CLI, hãy trả lời các câu hỏi:

1. Người dùng cần nhập nhiều command trong một phiên hay chỉ gọi một thao tác mỗi lần?
2. Có cần lịch sử, completion và chỉnh sửa dòng lệnh không? Nếu có, chọn JLine.
3. Môi trường chạy có JLine integration trên classpath không? Nếu không, interactive runner là SystemShellRunner.
4. Công cụ có được gọi từ script, CI hoặc scheduler không? Nếu có, cấu hình non-interactive.
5. Script có cần chạy nhiều command không? Dùng file script và tiền tố `@`.
6. Mã thoát và output đã được kiểm thử trong môi trường triển khai thực tế chưa?

Chọn runner dựa trên cách người dùng hoặc hệ thống gọi công cụ, sau đó giữ cấu hình nhất quán giữa môi trường phát triển, kiểm thử và triển khai.

## Kết luận

Spring Shell 4.x có ba runner với ba mục đích rõ ràng. `SystemShellRunner` cung cấp shell tương tác dựa trên Console của JDK; `JLineShellRunner` bổ sung trải nghiệm terminal qua JLine; `NonInteractiveShellRunner` chạy command hoặc file script rồi kết thúc. Property `spring.shell.interactive.enabled` quyết định chế độ chạy ở cấp ứng dụng, còn dependency JLine quyết định runner tương tác nào được sử dụng. Hiểu đúng lựa chọn này giúp ứng dụng hoạt động nhất quán trong terminal, script và pipeline tự động hóa.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 – Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell 4.0.4 API – ShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/ShellRunner.html)
- [Spring Shell 4.0.4 API – SystemShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/SystemShellRunner.html)
- [Spring Shell 4.0.4 API – JLineShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/JLineShellRunner.html)
- [Spring Shell 4.0.4 API – NonInteractiveShellRunner](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [Spring Shell 4.x – Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

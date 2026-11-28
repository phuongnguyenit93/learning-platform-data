# Lịch sử nhập lệnh và khả năng lưu hoặc tìm lại theo terminal

Khi làm việc với CLI, nhiều thao tác thường được lặp lại: xem trạng thái, kiểm tra cấu hình, tìm một bản ghi hoặc triển khai một môi trường. Gõ lại toàn bộ command vừa tốn thời gian vừa dễ sai. Spring Shell kết hợp với JLine để lưu các dòng lệnh đã nhập, cho phép người dùng gọi lại bằng bàn phím, tìm kiếm nội dung cũ và xuất lịch sử thành file để dùng lại.

Trong Spring Shell 3.x cần phân biệt ba cách làm việc với lịch sử:

- **Gọi lại trong terminal:** dùng phím điều hướng và tìm kiếm của JLine khi đang ở phiên shell tương tác.
- **Lưu lịch sử giữa các phiên:** Spring Shell ghi history vào file theo cấu hình; lần chạy sau có thể nạp lại để người dùng tiếp tục tra cứu.
- **Xuất lịch sử thành script:** built-in command `history` có thể ghi các command đã chạy vào một file mà built-in command `script` đọc và thực thi.

Ba khả năng này liên quan với nhau nhưng không phải cùng một thao tác. Phím mũi tên giúp sửa và chạy lại một dòng trong phiên tương tác; file history giúp giữ lịch sử qua lần khởi động; file script là danh sách command có thể thực thi lại.

Sau bài này, bạn có thể:

- Dùng phím mũi tên và tìm kiếm ngược để gọi lại command trong terminal.
- Xem lịch sử bằng built-in command `history`.
- Hiểu file history mặc định và cấu hình tên, vị trí lưu.
- Phân biệt cấu hình lưu history với cấu hình bật/tắt command `history`.
- Xuất lịch sử thành file và chạy lại bằng `script`.
- Nhận biết giới hạn giữa phiên tương tác và chế độ non-interactive.
- Bảo vệ thông tin nhạy cảm được ghi trong lịch sử command.

> Nội dung tập trung vào Spring Shell 3.3.x và JLine 3. Một số phím tắt có thể khác khi terminal dùng keymap Vi, cấu hình JLine tùy chỉnh hoặc môi trường không cấp terminal tương tác.

## 1. Lịch sử command được tạo và dùng ở đâu?

Trong phiên tương tác, JLine đọc dòng nhập, cung cấp chức năng chỉnh sửa và quản lý các command người dùng đã gửi. Spring Shell dùng lịch sử này để hỗ trợ gọi lại, tìm kiếm và hiển thị qua command `history`.

Luồng cơ bản:

~~~mermaid
flowchart TD
    A[Người dùng nhập command] --> B[JLine LineReader nhận dòng]
    B --> C[Command được gửi tới Spring Shell]
    C --> D[Spring Shell phân giải và thực thi]
    D --> E[JLine History ghi dòng đã nhập]
    E --> F[Điều hướng và tìm kiếm trong terminal]
    E --> G[File history được lưu theo cấu hình]
    E --> H[history xuất ra file script]
    H --> I[script đọc và thực thi lại]
~~~

Lịch sử lưu **dòng command đã nhập**, không lưu kết quả trả về, nội dung terminal hay trạng thái nghiệp vụ sau khi command chạy. Nếu command `order show --id 42` được lưu, history giữ dòng lệnh đó; nó không lưu bản chụp dữ liệu đơn hàng tại thời điểm chạy.

Một dòng chỉ trở thành lịch sử sau khi người dùng gửi nó. Nội dung đang gõ dở và chưa nhấn Enter không phải command đã thực thi.

## 2. Gọi lại command bằng bàn phím

Trong interactive shell, JLine cung cấp các thao tác điều hướng history phổ biến:

| Phím | Hành vi thường gặp |
|---|---|
| `Up` | Chuyển về command cũ hơn |
| `Down` | Chuyển về command mới hơn sau khi đã điều hướng ngược |
| `Ctrl+R` | Tìm kiếm ngược trong lịch sử theo nội dung đang nhập |
| `Ctrl+S` | Tìm kiếm xuôi trong một số terminal/keymap; có thể bị terminal dùng cho flow control |

Ví dụ, sau khi đã chạy:

~~~text
shell:>customer list --status ACTIVE
shell:>customer show --code C102
shell:>invoice list --limit 20
~~~

Nhấn `Up` một lần sẽ đưa command gần nhất trở lại dòng nhập. Có thể sửa `--limit 20` thành `--limit 50` rồi nhấn Enter để chạy lại command đã chỉnh.

### Tìm command theo một phần nội dung

Khi lịch sử dài, dùng `Ctrl+R` để tìm ngược theo chuỗi:

1. Nhấn `Ctrl+R`.
2. Nhập một phần command, ví dụ `customer show`.
3. JLine tìm một mục lịch sử phù hợp và hiển thị dòng tìm được.
4. Tiếp tục nhấn `Ctrl+R` để chuyển tới kết quả khớp cũ hơn nếu có.
5. Nhấn Enter để chạy dòng hiện tại, hoặc dùng phím chỉnh sửa để sửa trước khi chạy.

Phím tắt cụ thể phụ thuộc keymap. Với keymap Emacs thường dùng trong terminal, `Ctrl+R` là tìm ngược; keymap Vi có thể cung cấp cách điều hướng khác. Nếu phím không hoạt động, kiểm tra terminal có đang ở chế độ tương tác và ứng dụng có dùng JLine line editor hay không.

### Tìm lại không đồng nghĩa với chạy lại ngay

Khi một command cũ được đưa trở lại dòng nhập, người dùng vẫn có thể sửa option hoặc argument. Chỉ khi nhấn Enter thì Spring Shell mới nhận và thực thi dòng đó. Hãy kiểm tra các giá trị có tác động như mã khách hàng, môi trường, đường dẫn hoặc cờ ghi đè trước khi gửi.

## 3. Dùng built-in command history

Spring Shell 3.x cung cấp built-in command `history`. Lệnh này hiển thị lịch sử các command đã thực thi. Nó cũng có thể ghi lịch sử ra một file để built-in `script` đọc được.

Chạy:

~~~text
shell:>history
~~~

Để xem cú pháp của bản ứng dụng cụ thể, dùng:

~~~text
shell:>help history
~~~

API legacy 3.x khai báo `history(File file)` với tham số file tùy chọn. Với tên tham số mặc định `file`, cách gọi thường dùng là:

~~~text
shell:>history --file ./commands-from-history.shell
~~~

Lệnh xuất tạo file chứa các dòng command trong lịch sử. Đây là file script, không phải bản sao định dạng của file history nội bộ JLine. File được thiết kế để có thể đọc lại bằng built-in command `script`.

Nếu cú pháp option của ứng dụng đã được tùy biến, hãy ưu tiên kết quả `help history` của chính ứng dụng thay vì đoán tên option.

## 4. Lưu lịch sử thành file script và thực thi lại

Một cách hữu ích để tái sử dụng thao tác đã chạy là xuất history thành file, kiểm tra nội dung rồi chạy file bằng command `script`.

Ví dụ:

~~~text
shell:>history --file ./customer-check.shell
shell:>script --file ./customer-check.shell
~~~

File `customer-check.shell` có thể chứa các dòng như:

~~~text
customer list --status ACTIVE
customer show --code C102
invoice list --limit 20
~~~

Built-in `script` đọc từng command và thực thi theo thứ tự trong file. Có thể thêm comment bắt đầu bằng `//` để ghi chú mục đích của từng nhóm lệnh:

~~~text
// Kiểm tra khách hàng đang hoạt động
customer list --status ACTIVE
customer show --code C102

// Xem hóa đơn gần đây
invoice list --limit 20
~~~

### Kiểm tra file trước khi replay

Không nên xuất toàn bộ lịch sử rồi chạy lại ngay. Lịch sử có thể chứa:

- Command đã tạo, sửa hoặc xóa dữ liệu.
- Command triển khai hoặc khởi động lại dịch vụ.
- Đường dẫn chỉ tồn tại trên máy hoặc môi trường cũ.
- ID và trạng thái dữ liệu đã thay đổi.
- Giá trị bí mật hoặc thông tin riêng tư được truyền trực tiếp trên command line.

Hãy mở file script, loại bỏ các dòng không cần thiết, kiểm tra thứ tự và xác nhận những command có side effect trước khi chạy. Nếu cần một quy trình lặp lại ổn định, nên duy trì script đã được rà soát như một tài liệu vận hành riêng thay vì phụ thuộc toàn bộ history cá nhân.

## 5. File history tự động của Spring Shell

Spring Shell 3.3 lưu history vào log file theo mặc định. Có thể cấu hình:

| Thuộc tính | Tác dụng |
|---|---|
| `spring.shell.history.enabled` | Bật hoặc tắt việc lưu file history |
| `spring.shell.history.name` | Đặt tên file history |
| `spring.shell.config.location` | Chỉ định thư mục chứa file cấu hình/history; mặc định là thư mục làm việc hiện tại |
| `spring.application.name` | Tham gia xác định tên file history khi không đặt tên riêng |

Nếu không cấu hình tên riêng và không có tên ứng dụng để thay thế, tên file mặc định là `spring-shell.log`. Có thể dùng placeholder `{userconfig}` trong `spring.shell.config.location` để trỏ tới thư mục cấu hình dùng chung do Spring Shell phân giải.

Ví dụ cấu hình trong `application.yml`:

~~~yaml
spring:
  application:
    name: customer-shell
  shell:
    history:
      enabled: true
      name: customer-shell-history.log
    config:
      location: "{userconfig}/customer-shell"
~~~

Với cấu hình trên, ứng dụng bật lưu history, đặt tên file là `customer-shell-history.log` và dùng thư mục cấu hình được chỉ định. Nếu không cần thư mục dùng chung, có thể bỏ `config.location` để sử dụng thư mục làm việc hiện tại theo mặc định.

### Tắt lưu file history

Nếu không muốn Spring Shell ghi file lịch sử, cấu hình:

~~~yaml
spring:
  shell:
    history:
      enabled: false
~~~

Thuộc tính này điều khiển việc lưu file history. Nó khác với việc tắt built-in command `history` và khác với việc điều hướng history trong bộ nhớ của JLine trong phiên tương tác.

## 6. Phân biệt hai thuộc tính enabled

Spring Shell có hai cấu hình với mục đích khác nhau:

| Thuộc tính | Điều khiển |
|---|---|
| `spring.shell.history.enabled` | Việc lưu file history |
| `spring.shell.command.history.enabled` | Việc đăng ký built-in command `history` |

Muốn ẩn command `history` khỏi command catalog, dùng:

~~~yaml
spring:
  shell:
    command:
      history:
        enabled: false
~~~

Khi tắt command, người dùng không còn gọi `history` để xem hoặc xuất lịch sử qua built-in command. Cấu hình này không phải cách tắt riêng file history. Nếu cần điều khiển cả hai, cấu hình hai thuộc tính tương ứng.

Spring Shell cũng cho phép thay thế built-in history command bằng cách đăng ký bean triển khai marker interface `History.Command`. Khi có bean thay thế, implementation mặc định sẽ nhường chỗ. Chỉ làm việc này khi ứng dụng cần hành vi history riêng, chẳng hạn kiểm soát quyền xem hoặc xuất lịch sử theo chính sách.

## 7. Tìm kiếm, mở rộng và tái sử dụng history

JLine hỗ trợ nhiều khả năng ngoài việc nhấn mũi tên:

| Khả năng | Ý nghĩa |
|---|---|
| Điều hướng trước/sau | Di chuyển qua các dòng lịch sử bằng phím điều hướng |
| Tìm kiếm ngược | Tìm command cũ theo phần văn bản |
| Tìm kiếm xuôi | Tìm command mới hơn nếu keymap và terminal hỗ trợ |
| History expansion | Tham chiếu command cũ bằng cú pháp kiểu Bash nếu event expansion đang bật |
| Lưu bền vững | Nạp và lưu lịch sử qua file giữa các phiên |

JLine có hỗ trợ history expansion kiểu Bash như `!!`, `!n`, `!-n`, `!string` và `^old^new`. Tuy nhiên, cách diễn giải các ký tự `!` và escape phụ thuộc cấu hình event expansion. Không nên mặc định các biểu thức này luôn hoạt động trong mọi ứng dụng Spring Shell; hãy thử trong phiên shell của dự án trước khi đưa vào hướng dẫn vận hành.

Ký tự `!` cũng có thể xuất hiện trong chuỗi hoặc dữ liệu hợp lệ. Đặc biệt, tài liệu JLine lưu ý việc event expansion có thể ảnh hưởng đến cách xử lý escape và đường dẫn Windows có dấu gạch chéo ngược. Nếu ứng dụng có nhu cầu đặc biệt, cần cấu hình và kiểm thử parser/expander phù hợp.

## 8. Interactive terminal và non-interactive mode

Điều hướng bằng phím, tìm kiếm ngược và chỉnh sửa dòng là tính năng của phiên interactive dùng JLine. Khi chạy command theo chế độ non-interactive, ví dụ:

~~~powershell
java -jar app.jar customer list --status ACTIVE
~~~

ứng dụng nhận command để thực thi rồi kết thúc theo runner; không có trải nghiệm REPL để nhấn Up, Down hoặc `Ctrl+R`.

Trong Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Nếu ứng dụng cần REPL tương tác, đặt thuộc tính `spring.shell.interactive.enabled=true`:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
~~~

Terminal cũng cần cung cấp đầu vào tương tác và hỗ trợ line editing. Trong container hoặc CI không cấp TTY, không nên kỳ vọng các phím lịch sử hoạt động giống terminal máy phát triển. Với tác vụ tự động, dùng file script và runner phù hợp thay cho thao tác phím.

## 9. Bảo vệ thông tin trong lịch sử

History có thể chứa toàn bộ command line, bao gồm argument, đường dẫn và mã định danh mà người dùng đã nhập. Vì vậy, không nên đưa mật khẩu, access token, private key hoặc bí mật khác vào option của command.

Ví dụ không nên dùng:

~~~text
shell:>service login --username admin --password MySecret123
~~~

Thay vào đó, dùng cơ chế nhận bí mật phù hợp như prompt che ký tự, biến môi trường được quản lý an toàn hoặc secret store của hệ thống. Tránh ghi bí mật vào history, script, log hoặc output hỗ trợ.

Các nguyên tắc vận hành:

- Giới hạn quyền đọc file history và file script đã xuất.
- Không commit file history cá nhân vào Git.
- Rà soát file trước khi gửi cho đồng nghiệp hoặc đính kèm ticket.
- Không dùng script được xuất từ history như một artifact đã được phê duyệt.
- Tắt lưu file history nếu chính sách môi trường yêu cầu.
- Xóa hoặc xoay vòng file history theo chính sách lưu trữ của tổ chức.
- Không giả định Spring Shell tự động che mọi giá trị nhạy cảm trong command.

JLine có cơ chế lọc history và giới hạn số entry ở cấp `LineReader`. Nếu cần lọc theo quy tắc riêng, cần cấu hình JLine hoặc thay thế cơ chế history phù hợp với phiên bản; không nhầm các thuộc tính đó với hai property `spring.shell.history.enabled` và `spring.shell.command.history.enabled`.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Nhấn Up nhưng không có command cũ | Đang chạy non-interactive hoặc terminal không dùng JLine line editor | Bật interactive runner và kiểm tra TTY |
| `Ctrl+R` không tìm được | Keymap khác, terminal chặn phím hoặc binding đã bị thay đổi | Thử phím mũi tên, kiểm tra keymap và cấu hình terminal |
| `history` không tồn tại | Built-in command đã bị tắt hoặc bị thay thế | Kiểm tra `spring.shell.command.history.enabled` và bean `History.Command` |
| Lịch sử không còn sau khi khởi động lại | File history bị tắt, thư mục lưu thay đổi hoặc file không ghi được | Kiểm tra `spring.shell.history.enabled`, `spring.shell.history.name` và `spring.shell.config.location` |
| File history nằm ở vị trí khác | Thư mục làm việc hoặc config location khác dự kiến | Kiểm tra working directory và cấu hình `spring.shell.config.location` |
| `history --file` không xuất được | Đường dẫn file không hợp lệ hoặc không có quyền ghi | Kiểm tra `help history`, thư mục đích và quyền filesystem |
| Script chạy lại thao tác không mong muốn | File export chứa toàn bộ command cũ, kể cả command có side effect | Rà soát và chỉnh file script trước khi chạy |
| History chứa bí mật | Bí mật được truyền dưới dạng argument | Thay bằng cơ chế nhận secret an toàn và xử lý file history theo chính sách |
| Hai phiên shell ghi history đồng thời | Nhiều tiến trình cùng sử dụng file | Dùng thư mục/file phù hợp cho từng ứng dụng hoặc phiên và kiểm tra cơ chế ghi của JLine |

## 11. Checklist sử dụng history

- Xác nhận ứng dụng đang chạy interactive shell nếu cần điều hướng bằng bàn phím.
- Dùng Up/Down để gọi lại command và sửa trước khi nhấn Enter.
- Dùng `Ctrl+R` khi cần tìm theo một phần command trong keymap hỗ trợ.
- Dùng `history` để xem các command đã thực thi.
- Dùng `help history` để kiểm tra cú pháp xuất file của ứng dụng.
- Cấu hình tên và vị trí file history rõ ràng nếu cần lưu qua nhiều phiên.
- Phân biệt `spring.shell.history.enabled` với `spring.shell.command.history.enabled`.
- Rà soát file xuất trước khi chạy bằng `script`.
- Không truyền mật khẩu hoặc token trực tiếp trên command line.
- Bảo vệ quyền truy cập và thời hạn lưu của file history.

## 12. Bài tập thực hành

Trong ứng dụng Spring Shell 3.3.x, thực hiện các bước:

1. Khởi động ứng dụng ở chế độ interactive.
2. Chạy ít nhất ba command khác nhau, chẳng hạn `help`, `version` và một command nghiệp vụ.
3. Dùng `Up` và `Down` để điều hướng, sửa một option rồi chạy lại.
4. Dùng `Ctrl+R` tìm một command theo từ khóa và xác nhận cách hoạt động của keymap hiện tại.
5. Chạy `history` để xem danh sách command đã nhập.
6. Chạy `help history` và xuất lịch sử ra file script.
7. Mở file, thêm comment, bỏ các dòng không muốn chạy lại và kiểm tra các command có side effect.
8. Dùng `script` để thực thi file đã rà soát.
9. Cấu hình `spring.shell.history.name` và `spring.shell.config.location`, khởi động lại ứng dụng và kiểm tra vị trí lưu.
10. Thử tắt riêng built-in command `history`, sau đó bật lại; tiếp tục thử tắt lưu file history và quan sát sự khác biệt.
11. Giải thích vì sao không nên lưu mật khẩu hoặc token trong command line.

Khi hoàn thành, hãy mô tả sự khác nhau giữa lịch sử trong bộ nhớ của phiên terminal, file history được lưu tự động và file script được xuất để chạy lại.

## Tài liệu tham khảo

- [Spring Shell 3.3 – History](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/history.html): lệnh `history`, file log, tên file và vị trí lưu.
- [Spring Shell 3.3 – History API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.html): khả năng hiển thị hoặc xuất history ra file đọc được bởi `Script`.
- [Spring Shell 3.3 – History.Command API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/commands/History.Command.html): thay thế hoặc tắt built-in history command.
- [Spring Shell 3.3 – Script](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/script.html): đọc và thực thi command từ file.
- [Spring Shell 3.3 – Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): chế độ interactive và non-interactive; cấu hình interactive runner.
- [JLine 3 – History](https://jline.org/versions/3.x/docs/history/): lưu bền vững, tìm kiếm, lọc, giới hạn và vòng đời history.
- [JLine 3 – Line Reader](https://jline.org/versions/3.x/docs/line-reader/): line editing, history navigation và tìm kiếm trong terminal.

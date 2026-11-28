# Kiểm tra giao diện trên terminal thật thay vì chỉ cửa sổ chạy IDE

Một ứng dụng Spring Shell có thể chạy bình thường trong cửa sổ Run của IDE nhưng gặp lỗi khi người dùng mở từ PowerShell, Windows Terminal, macOS Terminal hoặc Linux terminal. Nguyên nhân thường nằm ở môi trường đầu vào/đầu ra: cửa sổ Run có thể chỉ là console nhận và hiển thị stream, trong khi terminal thật còn cung cấp khả năng điều khiển con trỏ, kích thước cửa sổ, phím chức năng, tín hiệu và mã ANSI.

Vì vậy, kiểm thử command trong IDE vẫn hữu ích, nhưng chưa đủ để xác nhận trải nghiệm terminal. Trước khi phát hành, hãy chạy chính artifact của ứng dụng trong terminal hệ điều hành và kiểm tra các thao tác mà người dùng sẽ thực hiện: nhập lệnh, sửa dòng, nhấn Tab, dùng lịch sử, đổi kích thước cửa sổ, ngắt tiến trình và đọc output có dấu tiếng Việt.

## Phân biệt Run console, IDE Terminal và terminal hệ điều hành

Ba môi trường này không có cùng hợp đồng tương tác:

| Môi trường | Cách hoạt động | Dùng để kiểm tra |
|---|---|---|
| IDE Run/Debug console | IDE khởi chạy JVM và hiển thị stdout/stderr; có thể không cung cấp đầy đủ TTY hoặc terminal control | Log, kết quả command đơn giản, breakpoint và debug |
| IDE Terminal tool window | IDE mở một shell hệ điều hành trong terminal emulator tích hợp | Chạy build, chạy ứng dụng từ shell, thử phần lớn thao tác terminal |
| Terminal hệ điều hành bên ngoài IDE | JVM được khởi chạy trực tiếp từ terminal emulator hoặc console của hệ điều hành | Kiểm thử chấp nhận cuối cùng về TTY, phím, signal, ANSI, resize và môi trường người dùng |

Không nên đồng nhất Run console với Terminal tool window. Ví dụ, IntelliJ IDEA có cả Run tool window và Terminal tool window. Terminal tool window mở một shell như PowerShell, Command Prompt, Bash hoặc Zsh; đây là môi trường gần với terminal hệ điều hành hơn Run console. Tuy nhiên, nếu ứng dụng có giao diện tương tác phức tạp, vẫn nên kiểm tra ít nhất một lần trong terminal độc lập bên ngoài IDE.

JLine mô tả system terminal là terminal được dùng để khởi chạy JVM. Nếu JVM được mở từ một console không có đầy đủ terminal capabilities hoặc từ các stream đã redirect, JLine có thể không nhận diện được terminal như mong đợi. Tài liệu troubleshooting của JLine cũng khuyến nghị chạy ứng dụng trong terminal thật khi IDE console không hỗ trợ đủ tính năng.

## Terminal cung cấp những khả năng nào?

Terminal không chỉ là một vùng hiển thị văn bản. JLine cung cấp abstraction cho input/output, terminal size, attributes, signal và capabilities. Một giao diện CLI có thể phụ thuộc vào các khả năng sau:

| Khả năng | Ví dụ trong Spring Shell | Điều cần quan sát |
|---|---|---|
| Nhập và sửa dòng | Gõ command, Backspace, Delete, Home, End, Left/Right | Ký tự được chèn/xóa đúng vị trí con trỏ |
| Lịch sử | Up/Down để gọi lại command trước | Lệnh cũ được khôi phục, không bị cắt hoặc nối sai |
| Completion | Nhấn Tab khi nhập command hoặc option | Candidate xuất hiện và được chèn đúng |
| Tín hiệu | Ctrl+C để ngắt thao tác | Command dừng theo chính sách và terminal vẫn dùng được |
| Kích thước terminal | Bảng, prompt hoặc màn hình TUI | Nội dung tự căn chỉnh khi cửa sổ thay đổi kích thước |
| Màu và escape sequence | ANSI color, con trỏ, progress indicator | Màu hiển thị đúng, không lộ chuỗi escape thô |
| Encoding và Unicode | Tiếng Việt, ký tự đặc biệt, emoji | Không lỗi dấu, không vỡ cột hoặc lệch vị trí |
| Chế độ tương tác | Prompt, xác nhận, nhập mật khẩu | Không bị treo khi stdin không phải terminal |

Không phải terminal nào cũng hỗ trợ mọi capability. Ứng dụng cần có fallback phù hợp: nếu không thể dùng màu hoặc điều khiển con trỏ, vẫn nên hiển thị thông tin bằng văn bản dễ đọc.

## Chuẩn bị artifact để chạy ngoài IDE

Nên kiểm tra đúng artifact mà người dùng sẽ cài đặt hoặc chạy, thay vì chỉ dùng cấu hình Run của IDE. Bằng cách này, classpath, resource, profile, working directory và cách đóng gói cũng được kiểm tra gần với môi trường phát hành.

### Windows PowerShell

Mở Windows Terminal hoặc PowerShell độc lập, chuyển đến thư mục dự án và build artifact:

```powershell
Set-Location C:\work\customer-cli
.\mvnw.cmd clean package
$jar = ".\target\customer-cli.jar"
java -jar $jar
```

Thay tên file JAR bằng artifact thực tế của dự án. Nếu dùng Gradle:

```powershell
.\gradlew.bat bootJar
$jar = ".\build\libs\customer-cli.jar"
java -jar $jar
```

### macOS hoặc Linux

Mở Terminal, iTerm2, GNOME Terminal hoặc terminal emulator của hệ điều hành:

```bash
cd ~/work/customer-cli
./mvnw clean package
java -jar target/customer-cli.jar
```

Với Gradle:

```bash
./gradlew bootJar
java -jar build/libs/customer-cli.jar
```

Chạy không truyền command để kiểm tra REPL nếu cấu hình phiên bản Spring Shell của dự án bật interactive mode. Nếu ứng dụng mặc định chạy non-interactive hoặc chỉ chạy command khi có đối số, hãy dùng cấu hình runner đúng với phiên bản đang sử dụng. Đừng thay đổi property chỉ để làm cho một lần chạy thử có vẻ tương tác; hãy xác minh cùng cấu hình mà sản phẩm sẽ phát hành.

Trong Spring Shell 4.0.4, interactive mode được bật mặc định; khi cần chạy command từ process arguments, có thể đặt `spring.shell.interactive.enabled=false`. Nếu starter có JLine trên classpath, runner tương tác là `JLineShellRunner`; nếu không có JLine, Spring Shell dùng `SystemShellRunner`. Các phiên bản 3.x có thay đổi mặc định runner giữa các minor version, nên cần kiểm tra tài liệu đúng phiên bản.

## Kiểm tra môi trường terminal trước khi chạy

Thông tin môi trường giúp giải thích khác biệt giữa các máy. Các biến này chỉ là dấu hiệu chẩn đoán; không dùng riêng một biến để kết luận terminal có đầy đủ tính năng hay không.

### Windows PowerShell

```powershell
$Host.Name
$env:TERM
$env:WT_SESSION
[Console]::InputEncoding
[Console]::OutputEncoding
chcp
java -version
```

`WT_SESSION` thường có mặt trong Windows Terminal; `TERM` mô tả loại terminal nếu shell thiết lập biến đó; `chcp` hiển thị code page hiện tại. Kết quả khác nhau giữa PowerShell chạy trong Windows Terminal, Windows Console, Git Bash hoặc WSL là bình thường.

### macOS và Linux

```bash
printf 'TERM=%s\n' "${TERM:-<unset>}"
tty
stty size
locale
tput colors
java -version
```

- `tty` cho biết input hiện tại có gắn với terminal device hay không.
- `stty size` hiển thị số dòng và cột nếu stdin là TTY.
- `TERM` là tên loại terminal được khai báo cho chương trình.
- `tput colors` cho biết số màu terminfo mô tả nếu có cơ sở dữ liệu phù hợp.
- `locale` giúp kiểm tra thiết lập ngôn ngữ và encoding.

Nếu `tty` báo `not a tty`, `stty` thất bại hoặc `TERM=dumb`, ứng dụng có thể đang chạy trong môi trường không cung cấp terminal tương tác đầy đủ. Không tự đặt `TERM=xterm-256color` để che vấn đề; khai báo sai loại terminal có thể khiến ứng dụng gửi escape sequence mà môi trường không hỗ trợ.

## Kiểm tra prompt và chỉnh sửa dòng lệnh

Chạy ứng dụng và kiểm tra thao tác nhập cơ bản bằng tay:

1. Nhập một command dài có nhiều option.
2. Dùng Left/Right để di chuyển con trỏ vào giữa dòng.
3. Chèn một ký tự tại vị trí con trỏ và xác nhận phần còn lại không bị ghi đè.
4. Dùng Backspace và Delete để xóa ký tự ở hai phía con trỏ.
5. Dùng Home/End để về đầu và cuối dòng.
6. Dùng Up/Down để duyệt lịch sử command.
7. Dán một chuỗi dài từ clipboard và xác nhận không bị mất ký tự hoặc thực thi sớm.
8. Nhập một giá trị có dấu cách trong dấu nháy và kiểm tra parser nhận đúng.

Nếu ứng dụng có prompt nhập mật khẩu, xác nhận ký tự không bị echo ra màn hình, thao tác paste hoạt động theo yêu cầu và prompt trở lại bình thường sau khi nhập sai hoặc hủy thao tác.

## Kiểm tra Tab completion trong terminal thật

Completion có thể hoạt động trong unit test hoặc ShellTestClient nhưng vẫn sai khi dùng bàn phím thật. Hãy kiểm tra:

- Nhấn Tab khi chưa nhập gì: shell hiển thị hoặc xử lý danh sách command theo thiết kế.
- Nhập một phần tên command rồi nhấn Tab: candidate được lọc đúng.
- Nhập `--` hoặc một phần tên option rồi nhấn Tab: gợi ý option chính xác.
- Nhập option cần giá trị rồi nhấn Tab: gợi ý value đúng loại.
- Nhấn Tab khi con trỏ nằm giữa dòng: completion thay đúng token hiện tại, không cắt phần văn bản phía sau.
- Nhấn Tab nhiều lần: danh sách candidate không bị nhân đôi hoặc treo.
- Chọn giá trị có dấu cách hoặc ký tự đặc biệt: shell quote/escape đúng để command parser đọc lại được.

Nếu IntelliJ Terminal tool window có completion riêng của Bash, Zsh hoặc PowerShell, hãy phân biệt popup của terminal emulator với completion do Spring Shell cung cấp. Có thể thử trong terminal hệ điều hành độc lập để xác định candidate đến từ ứng dụng hay từ shell hệ điều hành.

## Kiểm tra màu sắc, Unicode và bố cục

Chạy các command có output nhiều màu, bảng hoặc progress indicator. Kiểm tra cả trạng thái có và không có ANSI support.

### Màu và escape sequence

- Màu foreground/background hiển thị đúng và được reset sau mỗi thông báo.
- Bold, dim hoặc style khác không làm phần output tiếp theo bị giữ style ngoài ý muốn.
- Khi terminal không hỗ trợ màu, ứng dụng vẫn hiển thị văn bản dễ đọc.
- Khi redirect output ra file, file không bị trộn các escape sequence nếu chế độ non-interactive cần plain text.
- Không giả định mọi terminal đều có cùng số màu hoặc hỗ trợ cùng control sequence.

JLine cung cấp terminal type và capability để ứng dụng chọn cách hiển thị. Nếu dùng màu hoặc cursor control, hãy kiểm tra capability trước và có fallback cho terminal tối giản.

### Unicode và tiếng Việt

Thử các chuỗi như:

```text
Nguyễn Thị Ánh — Đã xử lý thành công
Đường dẫn: C:\Users\An\Documents\báo-cáo.txt
Trạng thái: Đang chờ xác nhận
```

Kiểm tra dấu tiếng Việt, ký tự kết hợp, ký tự rộng và emoji nếu sản phẩm có sử dụng. Một chuỗi có thể được encode đúng UTF-8 nhưng vẫn chiếm số cột khác nhau tùy terminal/font; vì vậy hãy quan sát căn lề và line wrap thực tế, không chỉ so sánh byte hoặc số ký tự Java.

### Kích thước cửa sổ và line wrapping

Thử ít nhất ba kích thước: cửa sổ hẹp, cửa sổ tiêu chuẩn và cửa sổ rộng. Có thể thay đổi kích thước terminal ngay khi ứng dụng đang chạy.

- Prompt không ghi đè lên output trước đó.
- Bảng không cắt mất cột quan trọng mà không báo.
- Dòng dài wrap đúng và con trỏ vẫn ở vị trí có thể dự đoán.
- Progress bar hoặc màn hình TUI được vẽ lại theo kích thước mới.
- Khi terminal quá hẹp, ứng dụng chuyển sang bố cục đơn giản hoặc thông báo rõ.

JLine có API đọc kích thước terminal và nhận thay đổi resize. Nếu ứng dụng dùng component toàn màn hình của Spring Shell, hãy kiểm tra cả việc chuyển màn hình, cập nhật nội dung và thoát về prompt.

## Kiểm tra Ctrl+C, Ctrl+D và khôi phục terminal

Ngắt ứng dụng là một phần của trải nghiệm CLI. Hãy kiểm tra ở các thời điểm khác nhau:

1. Khi prompt đang chờ lệnh.
2. Khi command đang chạy lâu.
3. Khi đang nhập một giá trị nhiều dòng hoặc xác nhận.
4. Khi progress indicator hoặc TUI đang hiển thị.

Sau Ctrl+C, ứng dụng nên dừng thao tác theo chính sách, giải phóng tài nguyên và đưa terminal về trạng thái nhập bình thường. Kiểm tra lại:

- Ký tự gõ tiếp theo được echo đúng.
- Con trỏ không biến mất.
- Màu sắc không bị giữ.
- Dòng mới không bị ghi vào vị trí sai.
- Có thể chạy command khác trong cùng terminal session.

Ctrl+D thường biểu thị EOF trong terminal Unix-like; hành vi của Windows console và shell có thể khác. Hãy kiểm tra trên hệ điều hành mục tiêu thay vì giả định hai phím có cùng ý nghĩa. Nếu ứng dụng thay đổi terminal attributes hoặc vào raw mode, phải khôi phục chúng ngay cả khi command bị ngắt hoặc ném exception.

## Phân biệt terminal tương tác và output bị redirect

Một CLI có thể được gọi trực tiếp, qua pipe hoặc ghi output ra file. Những môi trường này không nên nhận cùng một giao diện tương tác:

```bash
java -jar target/customer-cli.jar customer-list
java -jar target/customer-cli.jar customer-list > customers.txt 2>&1
```

Lệnh đầu chạy trực tiếp trong terminal. Lệnh thứ hai chuyển stdout/stderr vào file; ứng dụng không nên chờ Tab, prompt xác nhận hoặc điều khiển con trỏ trong luồng output đã redirect.

Với Spring Shell 4.0.4, interactive mode được bật mặc định kể cả khi có process arguments. Nếu muốn chạy command một lần trong môi trường automation, cấu hình non-interactive mode cho profile tương ứng:

```yaml
# application-batch.yml
spring:
  shell:
    interactive:
      enabled: false
```

Ví dụ kích hoạt profile trong PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "batch"
java -jar .\target\customer-cli.jar customer-list
```

Trong Bash:

```bash
SPRING_PROFILES_ACTIVE=batch java -jar target/customer-cli.jar customer-list
```

Với Spring Shell 3.x, kiểm tra mặc định runner của minor version đang dùng trước khi áp dụng cấu hình này; hành vi mặc định interactive/non-interactive đã thay đổi giữa các dòng 3.x.

Trong Bash, có thể kiểm tra exit code sau khi redirect:

```bash
java -jar target/customer-cli.jar customer-list > run.log 2>&1
status=$?
printf 'exit=%s\n' "$status"
```

Trong PowerShell:

```powershell
java -jar .\target\customer-cli.jar customer-list *> .\run.log
$LASTEXITCODE
```

Nếu command cần xác nhận tương tác, hãy cung cấp option như `--yes` hoặc yêu cầu người dùng chạy trong interactive mode theo hợp đồng của ứng dụng. Không để command tự chờ input vô thời hạn trong CI hoặc khi stdin là pipe.

Kiểm thử cả hai trường hợp: terminal tương tác và non-interactive/redirection. Output máy đọc như JSON hoặc CSV không nên bị trộn prompt, màu hoặc progress bar vào cùng stream dữ liệu.

## Kiểm tra trong Docker, WSL và SSH

Ứng dụng có thể chạy trong container hoặc phiên SSH. Cần phân biệt phiên có pseudo-terminal (PTY) với phiên chỉ truyền stream.

Ví dụ Docker:

```bash
docker run --rm -it customer-cli:latest
```

`-i` giữ stdin mở; `-t` cấp pseudo-terminal. Để kiểm tra non-interactive, chạy không có `-t` và truyền command rõ ràng:

```bash
docker run --rm customer-cli:latest customer-list
```

Với SSH, `ssh -t host` yêu cầu cấp pseudo-terminal; `ssh host command` thường chạy command không có interactive PTY theo cấu hình mặc định. Hãy kiểm tra đúng cách triển khai thực tế của người dùng.

Trong WSL, Git Bash hoặc terminal remote, xác minh JDK, encoding, terminal type và đường dẫn. Không giả định biến môi trường hoặc terminal provider của Windows host giống môi trường Linux bên trong WSL/container.

## IDE vẫn hữu ích khi dùng đúng cửa sổ

Không cần bỏ IDE khỏi quy trình. Hãy dùng từng cửa sổ cho đúng mục tiêu:

| Công cụ | Cách mở | Vai trò |
|---|---|---|
| IntelliJ Run | Chạy cấu hình Run/Debug | Debug command, xem log, kiểm tra lỗi khởi tạo |
| IntelliJ Terminal | `View | Tool Windows | Terminal` hoặc `Alt+F12` | Mở PowerShell/Bash/Zsh trong terminal emulator tích hợp và chạy artifact như từ shell |
| Terminal bên ngoài | Windows Terminal, PowerShell, macOS Terminal, iTerm2, GNOME Terminal... | Kiểm thử cuối cùng trên môi trường terminal độc lập |

IntelliJ IDEA có terminal emulator tích hợp chạy shell hệ điều hành; đây là công cụ hữu ích để phát triển. Tuy vậy, tài liệu JLine lưu ý một số IDE console không hỗ trợ đầy đủ terminal features. Vì thế, nếu vấn đề chỉ xuất hiện ở terminal bên ngoài hoặc chỉ ở IDE Run console, hãy so sánh môi trường và capability thay vì mặc định ứng dụng sai.

## Bộ kiểm thử chấp nhận trên terminal

Có thể dùng bảng sau làm checklist cho mỗi bản phát hành:

| Nhóm | Thao tác | Kết quả mong đợi |
|---|---|---|
| Khởi chạy | Chạy JAR từ terminal ngoài IDE | Ứng dụng khởi động đúng profile và runner |
| Prompt | Nhập command và option | Prompt hiển thị ổn định, không mất ký tự |
| Line editing | Home/End, Left/Right, Backspace/Delete | Sửa dòng đúng vị trí |
| History | Up/Down | Gọi lại command trước chính xác |
| Completion | Tab ở command, option và value | Gợi ý đúng và chèn đúng token |
| Unicode | Output tiếng Việt và ký tự rộng | Không lỗi encoding, không vỡ bố cục |
| ANSI | Màu, style và reset | Hiển thị đúng hoặc fallback plain text |
| Resize | Thu nhỏ và phóng to cửa sổ | Bảng, prompt và TUI tự điều chỉnh |
| Signal | Ctrl+C ở prompt và khi command chạy | Hủy đúng và terminal được khôi phục |
| EOF | Ctrl+D hoặc đóng stdin | Ứng dụng kết thúc theo hợp đồng |
| Redirection | Ghi stdout/stderr ra file | Không yêu cầu tương tác hoặc in control sequence không phù hợp |
| PTY | Chạy trong Docker/SSH có và không có PTY | Chọn đúng interactive/non-interactive behavior |
| Exit code | Chạy command thành công và thất bại | Process trả mã đúng cho shell gọi |

Nên ghi lại hệ điều hành, terminal emulator, shell, JDK, phiên bản Spring Shell, terminal type và kích thước cửa sổ khi báo lỗi. Những thông tin này giúp tái hiện lỗi thay vì chỉ ghi “terminal bị lệch”.

## Kiểm thử tự động không thay thế terminal thật

Spring Shell cung cấp test support để kiểm tra command, output và một số tương tác trong môi trường kiểm thử. Những test này phù hợp để xác minh logic và regression tự động, nhưng không tái tạo hoàn toàn terminal emulator, font, code page, key mapping, PTY và signal handling của máy người dùng.

Chia kiểm thử thành ba tầng:

1. **Unit test:** kiểm tra logic command, formatter, parser hoặc service bằng dữ liệu giả.
2. **Shell integration test:** dùng test client của Spring Shell để kiểm tra command registration, output và luồng tương tác được hỗ trợ.
3. **Terminal acceptance test:** chạy artifact thật từ terminal hệ điều hành và thao tác bằng bàn phím/resize/signal như người dùng.

Không cần lặp toàn bộ bộ test bằng tay sau mỗi thay đổi nhỏ. Chạy unit/integration test thường xuyên; chạy terminal acceptance test cho các tính năng phụ thuộc terminal, trước release hoặc khi thay đổi JDK, Spring Shell, JLine, OS hay terminal emulator.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Run console hoạt động nhưng terminal ngoài IDE lỗi | Khác biệt TTY, terminal type, encoding hoặc native terminal provider | Chạy lại bằng artifact và ghi nhận môi trường terminal thực tế |
| Không dùng được Tab hoặc phím mũi tên | JVM không nhận được terminal tương tác hoặc line reader/provider không hoạt động | Chạy trong terminal có TTY; kiểm tra JLine và runner đang dùng |
| Màn hình xuất hiện `\u001B` hoặc chuỗi escape thô | ANSI control sequence không được terminal hỗ trợ hoặc output bị redirect | Kiểm tra capability và chuyển sang plain text khi không interactive |
| Bảng bị lệch cột | Unicode display width, terminal width hoặc font khác nhau | Test ký tự rộng và resize; tính độ rộng hiển thị thay vì số UTF-16 code unit |
| Sau Ctrl+C không gõ được hoặc con trỏ biến mất | Terminal attributes/raw mode chưa được khôi phục | Khôi phục attributes trong finally/shutdown path và xử lý signal |
| Ứng dụng treo trong CI | Command chờ input nhưng stdin không phải TTY | Cung cấp option không tương tác và tránh prompt khi chạy automation |
| Chạy Docker không có prompt | Container không được cấp PTY hoặc interactive runner bị tắt | Dùng `-it` khi cần REPL; dùng command rõ ràng cho batch |
| Terminal hiển thị sai dấu tiếng Việt | Encoding/code page/font không phù hợp | Kiểm tra locale, code page và encoding của process/terminal |
| IntelliJ Terminal và Windows Terminal cho kết quả khác | Khác terminal engine, shell, environment hoặc capability | Ghi nhận cấu hình cả hai và xác nhận trên môi trường mục tiêu |

## Quy trình kiểm tra trước khi phát hành

1. Build artifact và chạy bằng `java -jar` từ shell hệ điều hành.
2. Ghi lại JDK, Spring Shell/JLine version, OS, shell, terminal type và encoding.
3. Kiểm tra prompt, line editing, history và completion.
4. Kiểm tra màu, Unicode, line wrapping và resize.
5. Kiểm tra Ctrl+C, EOF và việc khôi phục terminal.
6. Chạy command với output redirect và xác nhận không có prompt/ANSI không phù hợp.
7. Kiểm tra process exit code với command thành công và thất bại.
8. Nếu hỗ trợ Docker/SSH/WSL, thử cả môi trường có PTY và không có PTY.
9. Đối chiếu kết quả với IDE Run console và IDE Terminal để khoanh vùng khác biệt.
10. Ghi nhận môi trường và bước tái hiện nếu phát hiện lỗi.

Kiểm tra bằng terminal thật giúp phát hiện những lỗi mà unit test hoặc cửa sổ Run không thể hiện: phím không được nhận, màu không được render, resize làm vỡ bảng, signal khiến terminal ở trạng thái sai hoặc ứng dụng chờ input trong pipeline. Đây là bước cần thiết để xác nhận CLI hoạt động đúng trong môi trường mà người dùng sẽ sử dụng.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html): interactive/non-interactive mode và lựa chọn `JLineShellRunner` hoặc `SystemShellRunner`.
- [Spring Shell 3.4.3 — InteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/InteractiveShellRunner.html): runner tương tác dựa trên JLine trong dòng 3.x.
- [JLine 3.x — Terminal](https://jline.org/versions/3.x/docs/terminal/): system terminal, input/output, terminal size, signal, terminal type và capabilities.
- [JLine 3.x — Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/): lỗi tạo system terminal, môi trường non-interactive, giới hạn IDE console và ANSI output.
- [IntelliJ IDEA — Terminal](https://www.jetbrains.com/help/idea/terminal-emulator.html): phân biệt Terminal tool window với các cửa sổ IDE khác, shell hỗ trợ và terminal emulator tích hợp.
- [Spring Shell 3.4.3 — ShellTestClient API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/test/ShellTestClient.html): kiểm thử interactive và non-interactive session trong test.

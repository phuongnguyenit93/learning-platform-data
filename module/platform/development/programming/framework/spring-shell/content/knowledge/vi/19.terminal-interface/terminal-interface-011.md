# Chế độ văn bản thuần khi đầu ra được chuyển hướng

Khi chạy command trong terminal, màu sắc, ký tự Unicode trang trí và hiệu ứng con trỏ có thể làm kết quả dễ đọc hơn. Nhưng khi đầu ra được chuyển hướng vào file, pipe hoặc hệ thống CI, những hiệu ứng này có thể trở thành dữ liệu thừa. Mã ANSI có thể xuất hiện nguyên dạng trong file, ký tự spinner làm sai nội dung log và prompt tương tác có thể khiến tác vụ tự động bị chờ vô hạn.

Spring Shell cung cấp theme `dump` để tạo đầu ra ít trang trí hơn. Kết hợp theme này với chế độ non-interactive và một quy ước output ổn định, ứng dụng có thể phục vụ cả người dùng terminal lẫn script tự động.

Bài này sử dụng Spring Shell 4.0.4.

## 1. Vì sao cần chế độ văn bản thuần?

Một terminal hiện đại có thể hiểu các chuỗi điều khiển như ANSI escape sequence để đổi màu, in đậm, di chuyển con trỏ hoặc xóa màn hình. Khi output đi tới terminal, chuỗi điều khiển được diễn giải. Khi output đi vào file hoặc pipe, chương trình nhận có thể nhìn thấy chính các byte điều khiển đó.

Ví dụ một chuỗi có màu có thể chứa ký tự ESC và mã đổi màu:

```text
\u001B[31mERROR\u001B[0m: Không thể kết nối
```

Trong terminal hỗ trợ ANSI, chữ `ERROR` được hiển thị màu đỏ. Trong file văn bản, chuỗi điều khiển có thể xuất hiện dưới dạng ký tự lạ hoặc làm công cụ xử lý log khó đọc.

Các vấn đề thường gặp khi redirect output:

- Mã màu ANSI nằm trong file kết quả.
- Ký tự trang trí hoặc emoji không được font/consumer hỗ trợ.
- Spinner dùng ký tự backspace hoặc carriage return khiến log nhiều dòng bị ghi đè hoặc khó phân tích.
- Hiệu ứng xóa màn hình, di chuyển con trỏ và cập nhật một dòng không phù hợp với file tuần tự.
- Prompt tương tác chờ input trong pipeline hoặc CI không có người nhập.
- Log ứng dụng trộn vào stdout, làm hỏng JSON hoặc CSV mà script cần đọc.

Chế độ văn bản thuần giúp kết quả dễ lưu, so sánh, tìm kiếm và truyền sang công cụ khác.

## 2. Phân biệt terminal, TTY/PTY và redirect

TTY là thiết bị terminal; PTY là pseudo-terminal, thường được terminal emulator, SSH hoặc công cụ CI cấp để mô phỏng terminal. Một chương trình có thể kiểm tra khả năng terminal để quyết định có nên bật tương tác hoặc hiệu ứng hay không.

Một số tình huống:

| Cách chạy | Đặc điểm | Điều cần cân nhắc |
|---|---|---|
| Chạy trực tiếp trong terminal | Input và output thường gắn với terminal | Có thể dùng prompt, màu và hiệu ứng nếu terminal hỗ trợ |
| Redirect stdout vào file | `stdout` đi vào file; stdin có thể vẫn là terminal | Output cần sạch; prompt có thể bị ghi vào file |
| Pipe stdout sang chương trình khác | Output trở thành input của chương trình kế tiếp | Không trộn thông báo phụ vào payload |
| Chạy trong CI không có terminal thật | Thường không có PTY hoặc input tương tác | Tránh prompt, spinner và full-screen UI |
| Chỉ redirect stderr | Dữ liệu kết quả vẫn đi ra terminal hoặc stdout | Log và output được tách theo cách redirect của hệ điều hành |

Redirect output và non-interactive mode là hai khái niệm khác nhau. Ví dụ, `stdout` có thể được chuyển vào file trong khi `stdin` vẫn kết nối với terminal. Việc redirect một stream không tự động chứng minh rằng ứng dụng nên chuyển sang non-interactive mode.

## 3. Chọn theme `dump` của Spring Shell

Spring Shell có hai theme tích hợp được tài liệu mô tả:

- `default`: theme mặc định, hỗ trợ styling và các figure trang trí.
- `dump`: không dùng styling màu và cố gắng tránh các figure đặc biệt.

Chọn theme bằng thuộc tính `spring.shell.theme.name`.

Trong `application.yml`:

```yaml
spring:
  shell:
    theme:
      name: dump
```

Hoặc truyền trực tiếp khi chạy JAR:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.theme.name=dump
```

Theme `dump` phù hợp khi muốn output của các thành phần sử dụng Spring Shell theming dễ đọc trong file hoặc pipe. Nó tác động đến style và figure được giải quyết qua theme. Nó không tự xóa các chuỗi ANSI mà code ứng dụng tự ghi, cũng không chuyển mọi nội dung Unicode do command tạo ra thành ASCII.

Vì vậy, nếu command tự nối chuỗi `\u001B[31m` hoặc in emoji trực tiếp, ứng dụng cần thay đổi phần output đó. Không nên coi `dump` là bộ lọc tổng quát có thể làm sạch mọi byte trên stdout.

## 4. Chạy command không tương tác khi redirect

Trong Spring Shell 4, interactive mode được bật mặc định, kể cả khi tiến trình được khởi chạy với command-line arguments. Muốn chạy command được truyền qua đối số rồi kết thúc, hãy đặt `spring.shell.interactive.enabled=false`. Spring Shell khi đó dùng `NonInteractiveShellRunner`.

Ví dụ chạy command và lưu kết quả:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  --spring.shell.theme.name=dump \
  report list --status ACTIVE \
  > reports.txt
```

Nếu muốn tách log chẩn đoán khỏi dữ liệu kết quả:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  --spring.shell.theme.name=dump \
  report list --status ACTIVE \
  > reports.txt 2> diagnostics.log
```

Trong ví dụ, `reports.txt` là stdout được redirect và `diagnostics.log` là stderr được redirect. Cách phân luồng thực tế còn phụ thuộc logging backend và cách ứng dụng ghi output. Hãy cấu hình logger riêng nếu log của Spring Boot hoặc thư viện vẫn được ghi ra console.

Trong PowerShell, có thể chạy tương tự:

```powershell
java -jar .\target\admin-cli.jar `
  --spring.shell.interactive.enabled=false `
  --spring.shell.theme.name=dump `
  report list --status ACTIVE `
  > .\reports.txt 2> .\diagnostics.log
```

Nếu vẫn cần phiên interactive, chỉ chọn theme `dump` để giảm styling; không đặt `interactive.enabled=false` vì thuộc tính đó thay đổi runner và cách ứng dụng nhận command.

## 5. Dùng profile riêng cho automation

Một ứng dụng có thể dùng theme `default` khi người dùng thao tác trực tiếp và theme `dump` khi chạy batch. Tách cấu hình bằng Spring profile giúp tránh phải truyền lặp lại nhiều thuộc tính.

`application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
    theme:
      name: default
```

`application-batch.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
    theme:
      name: dump
```

Khởi chạy profile batch:

```bash
java -jar target/admin-cli.jar \
  --spring.profiles.active=batch \
  report export --format csv --output ./reports/daily.csv \
  > command-output.txt 2> command-diagnostics.log
```

Profile `batch` chọn runner non-interactive và theme ít trang trí. Có thể bổ sung cấu hình logging riêng cho profile này để giữ stdout dành cho dữ liệu command và đưa log sang file hoặc hệ thống thu thập log.

## 6. Giữ stdout chỉ chứa dữ liệu command

Khi output được chương trình khác đọc, stdout nên có một contract ổn định. Nếu command xuất JSON, stdout chỉ nên chứa JSON. Nếu xuất CSV, stdout chỉ nên chứa header và các dòng dữ liệu theo schema đã công bố.

Ví dụ command xuất CSV:

```java
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class UserExportCommands {

    @Command(name = "user export", description = "Xuất danh sách người dùng")
    public void export(CommandContext context) {
        var writer = context.outputWriter();
        writer.println("id,name,status");
        writer.println("U-1001,An,ACTIVE");
        writer.println("U-1002,Binh,ACTIVE");
        writer.flush();
    }
}
```

`CommandContext.outputWriter()` là cách Spring Shell khuyến nghị để command ghi vào shell. Không cần dùng `System.out.println()` trực tiếp trong command. Khi chạy non-interactive và redirect stdout, hãy kiểm tra writer đang được nối với output stream mà runner sử dụng trong ứng dụng.

Tránh in thêm các dòng như:

```text
Starting export...
Export completed successfully.
```

vào cùng stdout nếu chương trình nhận mong đợi CSV. Có thể đưa tiến độ và thông báo trạng thái sang logger hoặc một tùy chọn output text riêng.

## 7. Tách logging khỏi payload

Log phục vụ chẩn đoán; payload phục vụ người dùng hoặc chương trình tiêu thụ. Nếu cùng ghi vào stdout, một dòng log có thể làm hỏng JSON/CSV.

Ví dụ cấu hình Spring Boot ghi log vào file:

```yaml
logging:
  file:
    name: logs/admin-cli.log
  level:
    root: INFO
    com.example.admin: DEBUG
```

Việc cấu hình file log không tự động đảm bảo mọi logger ngừng ghi console trong mọi logging backend. Hãy kiểm tra cấu hình appender/pattern đang dùng và quyết định rõ log có được phép xuất hiện trên stderr hay phải chuyển sang file hoặc hệ thống log tập trung.

Trong code Java, dùng SLF4J cho chẩn đoán:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class ImportService {

    private static final Logger log =
            LoggerFactory.getLogger(ImportService.class);

    public void importFile(String fileName, int rowCount) {
        log.info("Imported file={}, rows={}", fileName, rowCount);
    }
}
```

Không log token, mật khẩu hoặc dữ liệu cá nhân không cần thiết. Nếu stderr được redirect vào file diagnostics, hãy bảo đảm thông báo lỗi và log không chứa bí mật.

## 8. Hạn chế spinner, progress animation và điều khiển con trỏ

Spinner thường cập nhật cùng một vị trí bằng carriage return hoặc backspace. Hiệu ứng này dễ hiểu trong terminal nhưng khó đọc khi lưu thành file. Một số component giao diện terminal còn di chuyển con trỏ, xóa màn hình hoặc vẽ lại toàn bộ vùng hiển thị.

Khi output không có terminal thật:

- Tránh spinner chạy liên tục.
- Không dùng ký tự backspace để ghi đè nội dung trước đó.
- Không xóa màn hình hoặc di chuyển con trỏ.
- Không giả định terminal có chiều rộng cố định.
- Dùng các dòng tiến độ độc lập nếu người vận hành cần theo dõi.
- Với automation, ưu tiên báo cáo kết quả cuối cùng hoặc sự kiện có cấu trúc.

Ví dụ output tiến độ phù hợp với file log:

```text
10:00:01 STEP 1/3 validate - completed
10:00:02 STEP 2/3 export - started
10:00:05 STEP 2/3 export - completed rows=250
10:00:05 STEP 3/3 upload - completed
```

Mỗi dòng là một sự kiện độc lập, có thể tìm kiếm hoặc xử lý bằng công cụ khác. Không cần cập nhật lại cùng một dòng bằng escape sequence.

## 9. Phân biệt văn bản thuần với ASCII

Văn bản thuần không đồng nghĩa với ASCII. Theme `dump` hạn chế styling màu và cố gắng tránh figure đặc biệt, nhưng nội dung command vẫn có thể chứa Unicode.

Ví dụ:

```text
Đã xuất báo cáo thành công.
Người phụ trách: Nguyễn An
```

Đây là văn bản thuần hợp lệ nếu file được ghi và đọc bằng UTF-8. Không cần loại bỏ dấu tiếng Việt chỉ vì output được redirect.

Chỉ chuyển sang ASCII khi hệ thống nhận có yêu cầu cụ thể, ví dụ một giao thức cũ chỉ chấp nhận ASCII. Nếu cần, hãy chuẩn hóa ở lớp export và công bố rõ quy tắc thay thế ký tự. Không tự động xóa dấu tiếng Việt khỏi output thông thường.

Tương tự, `dump` không bảo đảm mọi bảng hoặc output tùy chỉnh chỉ chứa ký tự ASCII. Nếu downstream yêu cầu CSV hoặc JSON theo schema, hãy tạo đúng định dạng đó thay vì dựa vào hình thức hiển thị của terminal.

## 10. Xử lý output của bảng và component terminal

Spring Shell có thể hiển thị bảng ASCII và component giao diện terminal. Khi dùng chúng trong interactive shell, viền và căn cột giúp người dùng đọc dễ hơn. Khi redirect, chiều rộng terminal không còn là cơ sở đáng tin cậy và ký tự viền có thể khó xử lý.

Với dữ liệu cần được xử lý tiếp:

- Cung cấp output CSV hoặc JSON có schema rõ ràng.
- Dùng header ổn định và thứ tự cột cố định.
- Escape dấu phẩy, dấu nháy và xuống dòng theo chuẩn CSV khi cần.
- Không phụ thuộc vào khoảng trắng để phân tách cột.
- Tránh đưa màu hoặc ký tự viền vào payload.

Với output chỉ dành cho người đọc, có thể giữ bảng văn bản nhưng nên dùng dấu phân cách đơn giản và mỗi bản ghi một dòng. Nếu cần cả hai trải nghiệm, cung cấp `--format table` cho terminal và `--format csv` hoặc `--format json` cho automation.

## 11. Không tự giả định Spring Shell sẽ tự chuyển sang plain text

Có một số quyết định độc lập:

| Quyết định | Cấu hình hoặc cơ chế | Tác động |
|---|---|---|
| Chọn theme ít trang trí | `spring.shell.theme.name=dump` | Tắt styling màu của theme và hạn chế figure đặc biệt |
| Chạy command từ process arguments | `spring.shell.interactive.enabled=false` | Chọn `NonInteractiveShellRunner` |
| Ghi kết quả command | `CommandContext.outputWriter()` | Ghi output qua writer của command |
| Ghi thông tin chẩn đoán | SLF4J và logging backend | Đưa log tới file, stderr hoặc hệ thống log |
| Tạo dữ liệu cho máy đọc | JSON/CSV hoặc định dạng đã công bố | Giữ contract output ổn định |

Không nên cho rằng redirect stdout tự động đổi theme, tắt prompt, tắt log hoặc loại bỏ các chuỗi ANSI do code tự tạo. Tài liệu Spring Shell mô tả theme `dump` như một lựa chọn cấu hình; hãy chọn nó tường minh trong cấu hình automation và kiểm tra output thực tế.

Nếu ứng dụng dùng JLine và cần logic riêng dựa trên khả năng terminal, hãy dựa vào API terminal/capability của phiên bản JLine đang được Spring Shell quản lý. Không tạo thêm một terminal độc lập chỉ để kiểm tra TTY, vì nó có thể mở lại hoặc chiếm các stream mà shell đang sử dụng. Với ứng dụng không cần tự động phát hiện, profile hoặc tham số cấu hình tường minh thường dễ kiểm thử hơn.

## 12. Kiểm tra file đầu ra

Hãy xác minh kết quả bằng chính công cụ sẽ đọc file trong pipeline.

Ví dụ Bash:

```bash
java -jar target/admin-cli.jar \
  --spring.shell.interactive.enabled=false \
  --spring.shell.theme.name=dump \
  user export \
  > users.csv 2> diagnostics.log

head -n 5 users.csv
cat diagnostics.log
```

Kiểm tra mã ANSI trong file bằng cách tìm byte ESC hoặc chuỗi `ESC [` theo công cụ của hệ điều hành. Với PowerShell, có thể xem byte đầu file bằng:

```powershell
Format-Hex .\users.csv | Select-Object -First 10
```

Nếu output là JSON, dùng JSON parser để xác nhận toàn bộ file hợp lệ. Nếu output là CSV, dùng parser CSV để kiểm tra header, số cột và quy tắc quote. Không chỉ mở file bằng editor rồi nhìn bằng mắt.

## 13. Ma trận kiểm thử redirect

Hãy chạy cùng một command trong nhiều môi trường:

| Môi trường | Cấu hình | Điều cần xác nhận |
|---|---|---|
| Terminal tương tác | Theme `default`, interactive bật | Prompt, màu và nội dung hiển thị đúng |
| Terminal tương tác, theme dump | `spring.shell.theme.name=dump` | Nội dung dễ đọc, không có styling màu của theme |
| Redirect stdout | Theme `dump`, command non-interactive | File chỉ chứa payload dự kiến |
| Redirect stdout và stderr | Hai stream tách riêng | Log chẩn đoán không làm hỏng payload |
| Pipe sang parser | JSON/CSV output | Parser đọc thành công và không có dòng phụ |
| CI không có PTY | Non-interactive, theme dump | Không chờ prompt, không dùng hiệu ứng terminal |

Các điểm cần kiểm tra:

1. Không có prompt bị ghi vào file kết quả.
2. Không có mã màu hoặc chuỗi điều khiển con trỏ ngoài contract.
3. Không có spinner hoặc carriage return ghi đè dòng.
4. Log không xen vào JSON/CSV.
5. Encoding của file phù hợp với consumer.
6. Exit code của tiến trình phản ánh kết quả command theo quy ước ứng dụng.
7. Lỗi vẫn có thông báo đủ hữu ích trong diagnostics.

## 14. Bài tập thực hành

Xây dựng command `user export --format <csv|json>` để xuất dữ liệu người dùng. Command phải chạy được trong terminal tương tác và trong CI khi stdout được redirect.

Hãy thực hiện:

1. Cấu hình theme `default` cho profile tương tác.
2. Tạo profile `batch` dùng `spring.shell.theme.name=dump` và `spring.shell.interactive.enabled=false`.
3. Dùng `CommandContext.outputWriter()` để ghi dữ liệu command.
4. Đưa log chẩn đoán sang file hoặc stream riêng.
5. Không dùng ANSI escape, spinner hoặc thao tác di chuyển con trỏ trong payload.
6. Xuất CSV với header cố định và dữ liệu được quote đúng chuẩn.
7. Xuất JSON có schema ổn định.
8. Chạy JAR với stdout redirect vào file và stderr redirect vào file khác.
9. Dùng parser CSV/JSON để xác nhận file hợp lệ.
10. Kiểm tra file không chứa mã ANSI hoặc dòng log ngoài contract.
11. Chạy trong CI hoặc môi trường không có PTY và xác nhận tiến trình không chờ input.

**Kết quả cần nộp:** cấu hình hai profile, source command, file CSV/JSON mẫu, diagnostics log và bảng kết quả kiểm thử redirect.

## 15. Checklist trước khi phát hành CLI

- [ ] Đã xác định output có thể được terminal, file, pipe hoặc CI tiêu thụ.
- [ ] Đã chọn `dump` theme khi cần output ít styling và ít figure trang trí.
- [ ] Đã tắt interactive mode khi chạy command tự động từ process arguments.
- [ ] Không giả định redirect stdout tự động tắt prompt hoặc màu.
- [ ] Command dùng `CommandContext.outputWriter()` để ghi kết quả.
- [ ] Không tự ghi ANSI escape vào payload.
- [ ] Không dùng spinner, cursor movement hoặc full-screen redraw trong output được redirect.
- [ ] Đã phân biệt văn bản thuần với ASCII và giữ UTF-8 khi cần tiếng Việt.
- [ ] JSON/CSV có schema và contract ổn định.
- [ ] Log được tách khỏi stdout khi stdout là dữ liệu máy đọc.
- [ ] Đã kiểm tra file bằng parser hoặc công cụ downstream thật.
- [ ] Đã kiểm thử interactive, redirect, pipe và môi trường CI.

## Tài liệu tham khảo

- [Spring Shell Reference — Theming](https://docs.spring.io/spring-shell/reference/customization/styling.html)
- [Spring Shell Reference — Execution](https://docs.spring.io/spring-shell/reference/execution.html)
- [Spring Shell Reference — Writing Output](https://docs.spring.io/spring-shell/reference/commands/writing.html)
- [Spring Shell Reference — Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell API — `CommandContext`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell Releases — v4.0.4](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)

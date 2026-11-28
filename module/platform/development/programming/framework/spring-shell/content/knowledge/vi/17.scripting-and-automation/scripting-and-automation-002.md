# Gọi script bằng cú pháp của phiên bản đang sử dụng

Spring Shell có thể chạy một chuỗi command được lưu trong file. Cách này phù hợp khi cần khởi tạo dữ liệu thử nghiệm, cấu hình môi trường, thực hiện một quy trình vận hành lặp lại hoặc chạy nhiều thao tác từ CI. Một file script thường chứa từng command theo thứ tự thực hiện; shell đọc từng dòng và chuyển nó qua parser giống như khi người dùng nhập command trong terminal.

Cú pháp gọi script thay đổi giữa Spring Shell 3.x và 4.x. Trong 3.4.x, command dựng sẵn `script` nhận đường dẫn file như một positional argument. Trong 4.x, command này nhận đường dẫn qua option `--file`. Spring Shell 4.0.4 còn hỗ trợ tham chiếu tài nguyên Spring như `classpath:` và `file:`. Ngoài command `script` trong REPL, cả hai thế hệ đều có cách chạy file từ đối số khởi động với tiền tố `@`, nhưng cơ chế runner và cấu hình chế độ chạy khác nhau.

## File script có cấu trúc như thế nào?

Một script Spring Shell là file văn bản chứa các command mà ứng dụng đã đăng ký. Ví dụ `bootstrap.shell`:

```text
// Kiểm tra ứng dụng trước khi cấu hình
system status

// Tạo dữ liệu ban đầu
customer create --code CUS-100001 --name "Nguyen Van An"
customer create --code CUS-100002 --name "Tran Thi Binh"

// Xem lại dữ liệu
customer list
```

Các dòng command được thực thi theo thứ tự trong file. Dòng bắt đầu bằng `//` là comment và được bỏ qua. Với dữ liệu có khoảng trắng, hãy dùng dấu nháy như khi nhập trực tiếp trong shell. Tên command, option, argument và giá trị phải đúng với những gì ứng dụng đang đăng ký.

Một số lưu ý khi viết script:

- Mỗi dòng nên chứa một command hoàn chỉnh để dễ đọc và chẩn đoán lỗi.
- Không thêm prompt như `shell:>` vào file; chỉ ghi command.
- Dùng comment `//` để giải thích mục đích của từng nhóm lệnh.
- Dùng đường dẫn và tên option đúng với môi trường chạy script.
- Không ghi mật khẩu, token hoặc bí mật trực tiếp vào file script nếu file có thể bị commit hoặc chia sẻ.

Spring Shell 3.4.x hỗ trợ nối dòng khi dòng kết thúc bằng dấu gạch chéo ngược `\`. Ví dụ:

```text
customer create --code CUS-100003 \
  --name "Le Minh Chau" \
  --note "Khách hàng doanh nghiệp"
```

Tài liệu Spring Shell 4.0.4 mô tả file script theo nguyên tắc một command trên mỗi dòng và comment `//`. Để script dễ chuyển đổi giữa các phiên bản, hãy ưu tiên viết command trên một dòng và không phụ thuộc vào nối dòng nếu chưa kiểm tra parser của bản đang dùng.

## Gọi script bên trong shell tương tác

Khi shell đã khởi động và đang hiển thị prompt, người dùng có thể gọi command dựng sẵn `script`. Cú pháp của command này là điểm khác biệt quan trọng giữa hai thế hệ.

### Spring Shell 3.4.x: đường dẫn là positional argument

Trong Spring Shell 3.4.x, command `script` nhận một file cục bộ như đối số vị trí:

```text
shell:> script ./scripts/bootstrap.shell
```

Trên Windows, ví dụ:

```text
shell:> script "C:\work\spring-shell\scripts\bootstrap.shell"
```

Đường dẫn tương đối được phân giải theo working directory của tiến trình. Có thể dùng đường dẫn tuyệt đối khi script được gọi từ nhiều thư mục khác nhau. Đặt đường dẫn trong dấu nháy nếu nó chứa khoảng trắng.

Không viết `script --file ...` theo cú pháp 4.x khi đang dùng 3.4.x. Ở nhánh 3.4, phương thức command nhận một tham số `File`, nên đường dẫn được truyền trực tiếp như positional argument.

### Spring Shell 4.x: dùng option `--file`

Trong Spring Shell 4.x, file được truyền qua option có tên:

```text
shell:> script --file /absolute/path/to/bootstrap.shell
```

Trên Windows:

```text
shell:> script --file "C:\work\spring-shell\scripts\bootstrap.shell"
```

Spring Shell 4.0.3 mô tả đường dẫn file tuyệt đối. Từ Spring Shell 4.0.4, option `--file` còn chấp nhận Spring resource reference:

```text
shell:> script --file classpath:scripts/bootstrap.shell
shell:> script --file file:/opt/my-app/scripts/bootstrap.shell
```

`classpath:` phù hợp khi script được đóng gói cùng ứng dụng trong classpath, chẳng hạn bên trong JAR. `file:` tham chiếu file trên filesystem. Khi dùng resource reference, hãy bảo đảm tài nguyên thực sự có trong artifact hoặc đường dẫn file tồn tại ở máy chạy ứng dụng.

Không nhầm `script --file ...` với cú pháp chạy script từ đối số khởi động có tiền tố `@`. Đây là command được nhập trong REPL; người dùng có thể gọi nó sau khi shell đã khởi động và đang tương tác.

## So sánh nhanh cú pháp `script`

| Phiên bản | Cách gọi trong REPL | Loại đường dẫn được tài liệu hỗ trợ |
| --- | --- | --- |
| Spring Shell 3.4.x | `script ./scripts/bootstrap.shell` | File cục bộ |
| Spring Shell 4.0.0–4.0.3 | `script --file /absolute/path/bootstrap.shell` | Đường dẫn filesystem tuyệt đối |
| Spring Shell 4.0.4+ | `script --file /absolute/path/bootstrap.shell` | Đường dẫn tuyệt đối hoặc resource `classpath:`/`file:` |

Nếu chưa chắc phiên bản đang chạy, dùng `version` trong shell hoặc kiểm tra dependency đã resolve trong Maven/Gradle. Không dựa vào phiên bản Spring Boot để đoán cú pháp Spring Shell vì hai dependency có thể được nâng cấp độc lập.

## Chạy script ngay khi khởi động ứng dụng bằng `@file`

Ngoài việc nhập command `script` trong REPL, Spring Shell có thể đọc script từ đối số của tiến trình. Cách gọi này hữu ích cho batch job, CI hoặc tác vụ tự động không cần mở prompt tương tác. Tên file được đặt sau ký tự `@`:

```text
@/absolute/path/to/bootstrap.shell
```

### Spring Shell 3.4.x: `ScriptShellRunner`

Trong 3.4.x, `ScriptShellRunner` kiểm tra đối số tiến trình bắt đầu bằng `@`. Nếu tìm thấy, runner đọc file script, thực thi các command rồi kết thúc thay vì mở REPL.

Ví dụ cấu hình bật script runner trong `application.yml`:

```yaml
spring:
  shell:
    script:
      enabled: true
```

Khởi chạy JAR:

```bash
java -jar app.jar @/opt/my-app/scripts/bootstrap.shell
```

Trên Windows PowerShell, đặt đối số có tiền tố `@` trong dấu nháy để truyền nguyên chuỗi cho tiến trình Java:

```powershell
java -jar app.jar '@C:\work\spring-shell\scripts\bootstrap.shell'
```

Từ Spring Shell 3.3.x, việc bật các `ShellRunner` có thay đổi so với những bản trước. `spring.shell.script.enabled` là thuộc tính dành cho `ScriptShellRunner`; đừng mặc định runner này luôn hoạt động chỉ vì command `script` xuất hiện trong `help`. Nếu ứng dụng không nhận đối số `@file`, hãy kiểm tra cấu hình runner và phiên bản 3.x đang sử dụng.

### Spring Shell 4.x: `NonInteractiveShellRunner`

Trong 4.x, `NonInteractiveShellRunner` xử lý cả command đơn và file script được chỉ định bằng tiền tố `@`. Ví dụ:

```bash
java -jar app.jar @/opt/my-app/scripts/bootstrap.shell
```

Trên Windows PowerShell:

```powershell
java -jar app.jar '@C:\work\spring-shell\scripts\bootstrap.shell'
```

Điểm cần chú ý là Spring Shell 4 mặc định bật chế độ interactive, kể cả khi tiến trình được khởi chạy với đối số. Để các đối số được xử lý theo chế độ non-interactive, đặt:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Khi đó, `NonInteractiveShellRunner` có thể nhận command hoặc script từ đối số khởi động. Đây là khác biệt quan trọng khi chuyển một lệnh tự động hóa từ 3.x sang 4.x: cú pháp `@file` vẫn có, nhưng runner chịu trách nhiệm và cách chọn chế độ chạy đã thay đổi.

### Phân biệt hai cách bật script

Không trộn các thuộc tính dưới đây:

| Thuộc tính | Vai trò | Phiên bản liên quan |
| --- | --- | --- |
| `spring.shell.script.enabled` | Bật/tắt `ScriptShellRunner` nhận đối số `@file` | Spring Shell 3.x |
| `spring.shell.interactive.enabled` | Chọn shell interactive hay `NonInteractiveShellRunner` | Spring Shell 4.x; cũng có trong cấu hình runner 3.x |
| `spring.shell.command.script.enabled` | Bật/tắt command dựng sẵn `script` trong REPL | Các bản có standard script command |

Command `script` trong REPL và runner xử lý `@file` là hai cơ chế riêng. Tắt command `script` không đồng nghĩa với việc tắt mọi cách chạy script từ đối số khởi động; ngược lại, bật command `script` cũng không tự động bật runner `@file`.

## Chạy một command đơn và chạy một file script

Trong chế độ non-interactive, ứng dụng có thể thực thi một command từ đối số tiến trình hoặc đọc nhiều command từ file. Ví dụ Spring Shell 4:

Trước đó, cấu hình ứng dụng ở chế độ non-interactive trong `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó gọi một command hoặc một file script:

```bash
# Một command
java -jar app.jar customer list

# Một file script gồm nhiều command
java -jar app.jar @/opt/my-app/scripts/bootstrap.shell
```

Một command đơn phù hợp khi scheduler hoặc CI chỉ cần một thao tác. File script phù hợp khi nhiều bước cần chạy tuần tự trong cùng một lần khởi động shell. Với script dài, hãy chia thành các file theo mục đích và ghi rõ thứ tự gọi trong pipeline.

## Ví dụ hoàn chỉnh cho hai phiên bản

Giả sử có file `scripts/release-check.shell`:

```text
// Xác nhận ứng dụng và dữ liệu
system status
customer list

// Kiểm tra trạng thái đơn hàng
order list --status PAID --limit 20
```

Gọi trong REPL:

```text
# Spring Shell 3.4.x
script ./scripts/release-check.shell

# Spring Shell 4.x
script --file /absolute/path/to/scripts/release-check.shell
```

Gọi khi khởi động ứng dụng:

```bash
# Spring Shell 3.4.x: cần bật ScriptShellRunner trong cấu hình
java -jar app.jar @/opt/my-app/scripts/release-check.shell

# Spring Shell 4.x: application.yml đã đặt spring.shell.interactive.enabled=false
java -jar app.jar @/opt/my-app/scripts/release-check.shell
```

Hai ví dụ khởi động trên dùng file trong filesystem. Nếu muốn đóng gói script trong JAR, hãy dùng `classpath:` với command `script --file` của Spring Shell 4.0.4+; không suy ra rằng runner `@file` cũng nhận Spring resource reference chỉ từ khả năng đó.

## Những lỗi thường gặp khi gọi script

| Triệu chứng | Nguyên nhân có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| 3.4.x báo thừa option khi gọi `script --file ...` | Command 3.4.x nhận file như positional argument | Gọi `script ./path/file` |
| 4.x báo thiếu option khi gọi `script ./path/file` | Command 4.x yêu cầu option `--file` | Gọi `script --file /absolute/path/file` |
| Không tìm thấy file | Đường dẫn tương đối được tính từ working directory khác dự kiến | Dùng đường dẫn tuyệt đối hoặc kiểm tra working directory |
| `classpath:` không hoạt động ở 4.0.3 | Hỗ trợ classpath reference được bổ sung từ 4.0.4 | Nâng lên 4.0.4+ hoặc dùng file tuyệt đối |
| `@file` không kích hoạt trong 3.4.x | `ScriptShellRunner` chưa được bật | Kiểm tra `spring.shell.script.enabled=true` |
| 4.x mở REPL thay vì chạy đối số | Chế độ interactive vẫn đang bật | Đặt `spring.shell.interactive.enabled=false` |
| File được đọc nhưng command không chạy | Tên command, option hoặc cú pháp trong file không hợp lệ | Chạy từng dòng trong REPL và sửa theo `help` |
| Script chạy ở máy dev nhưng thất bại trong CI | Working directory, file hoặc quyền truy cập khác nhau | Dùng path xác định và cấp quyền cần thiết |
| Script không chạy command mong đợi sau một lỗi | Hành vi tiếp tục/dừng có thể phụ thuộc runner và loại lỗi | Kiểm thử lỗi thực tế và xác định rõ bước kiểm tra sau mỗi command |

## Kiểm thử script trước khi tự động hóa

Trước khi đưa file vào CI hoặc scheduler, hãy chạy thử trong đúng phiên bản Spring Shell và môi trường triển khai:

1. Xác nhận command `script` xuất hiện trong `help` nếu dùng REPL.
2. Dùng đúng cú pháp theo major/minor version để gọi file.
3. Kiểm tra working directory, đường dẫn tuyệt đối, quyền đọc file và resource có được đóng gói hay không.
4. Xác nhận comment, dòng trống, quote và các dòng lệnh nhiều option được parser xử lý đúng.
5. Thử một command thành công, một command có đầu vào sai và một trường hợp file không tồn tại.
6. Nếu gọi từ tiến trình tự động, kiểm tra cả output lẫn process exit code trên đúng phiên bản đang chạy.
7. Chạy lại script để xác định thao tác có an toàn khi thực hiện lặp hay cần bước kiểm tra trước khi tạo/cập nhật dữ liệu.

Không dùng dữ liệu production hoặc bí mật thật khi thử một script chưa được kiểm tra. Nếu script có thao tác thay đổi dữ liệu, hãy dùng môi trường thử nghiệm và xác nhận kết quả trước khi đưa vào lịch chạy tự động.

## Checklist chọn cú pháp đúng phiên bản

- [ ] Xác định chính xác phiên bản Spring Shell trong dependency đã resolve.
- [ ] Nếu dùng 3.4.x trong REPL, gọi `script <file>`.
- [ ] Nếu dùng 4.x trong REPL, gọi `script --file <file>`.
- [ ] Nếu dùng `classpath:` hoặc `file:` với `--file`, xác nhận đang ở 4.0.4+.
- [ ] Nếu dùng `@file` trong 3.4.x, bật `spring.shell.script.enabled`.
- [ ] Nếu dùng `@file` trong 4.x, đặt `spring.shell.interactive.enabled=false`.
- [ ] Phân biệt thuộc tính runner với thuộc tính bật/tắt command `script`.
- [ ] Kiểm thử file trong đúng working directory, OS và môi trường chạy.
- [ ] Xác minh kết quả, lỗi và mã thoát trước khi đưa vào CI/scheduler.

Khi gọi script, hãy xác định trước mình đang dùng command trong REPL hay runner nhận đối số lúc khởi động. Sau đó áp dụng cú pháp tương ứng: `script <file>` cho 3.4.x, `script --file <file>` cho 4.x, và cấu hình runner phù hợp nếu dùng `@file`. Điều này giúp script chạy nhất quán khi phát triển, triển khai và tự động hóa.

## Tài liệu tham khảo

- [Script Command – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html)
- [Script Command – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/script.html)
- [Execution – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/execution.html)
- [Execution – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [NonInteractiveShellRunner API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html)
- [ScriptShellRunner API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

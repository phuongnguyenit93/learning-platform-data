# Tệp script Spring Shell và giới hạn ngôn ngữ lệnh của nó

Spring Shell cung cấp khả năng đọc một tệp chứa nhiều command rồi thực thi lần lượt. Cách này hữu ích khi cần khởi tạo dữ liệu, thiết lập môi trường, chạy một chuỗi thao tác lặp lại hoặc chuẩn bị phiên làm việc cho người vận hành.

Tệp script Spring Shell là danh sách các command mà chính Spring Shell hiểu. Nó dùng parser, cách đặt tên option, quy tắc dấu nháy và cơ chế thực thi command của ứng dụng. Tệp này không phải Bash script, PowerShell script hay một ngôn ngữ lập trình tổng quát. Các cấu trúc như biến shell, `if`, `for`, `&&`, pipe và chuyển hướng không tự nhiên có ý nghĩa trong tệp script Spring Shell.

Bài học tập trung vào built-in `script`, cú pháp tệp được tài liệu hỗ trợ và những giới hạn cần biết khi tự động hóa. Các khác biệt được đối chiếu giữa Spring Shell 3.1.3 và Spring Shell 4.0.4.

## 1. Tệp script Spring Shell dùng để làm gì?

Một tệp script chứa các command hợp lệ của ứng dụng Spring Shell. Khi chạy tệp, framework đọc từng dòng, phân tích dòng đó như một command và thực thi theo thứ tự.

Ví dụ ứng dụng quản lý kho có các command:

- `warehouse list`: xem danh sách kho.
- `product create`: tạo sản phẩm.
- `stock adjust`: điều chỉnh tồn kho.
- `stock report`: tạo báo cáo.

Thay vì nhập từng command mỗi lần cần chuẩn bị dữ liệu thử nghiệm, có thể lưu chuỗi thao tác vào một tệp:

```text
// Kiểm tra phiên bản và danh sách kho
version
warehouse list

// Tạo sản phẩm mẫu
product create --sku SKU-100 --name "Bàn phím cơ"

// Nhập số lượng ban đầu
stock adjust --sku SKU-100 --warehouse HN --quantity 20

// Xem kết quả
stock show --sku SKU-100 --warehouse HN
```

Mỗi dòng command được thực thi theo thứ tự xuất hiện. Tệp có thể được dùng lại trong môi trường phát triển, kiểm thử hoặc thao tác vận hành nếu các command và dữ liệu đầu vào phù hợp.

## 2. Built-in command `script`

Spring Shell cung cấp command tích hợp tên `script`. Command này đọc một tệp cục bộ và phát lại các command được tìm thấy trong đó. Có thể chạy `help script` trong ứng dụng để xem cú pháp chính xác của phiên bản đang dùng.

Trong Spring Shell 3.1.x, tài liệu mô tả `script` nhận một tệp cục bộ làm đối số. Ví dụ thông dụng:

```text
shell:>script --file /opt/inventory/setup.shell
```

Trong Spring Shell 4.0.4, tài liệu chỉ rõ option `--file` và hỗ trợ đường dẫn tuyệt đối hoặc Spring resource reference:

```text
shell:>script --file /opt/inventory/setup.shell
shell:>script --file file:/opt/inventory/setup.shell
shell:>script --file classpath:scripts/setup.shell
```

`classpath:` hữu ích khi tệp script được đóng gói cùng ứng dụng, chẳng hạn tài nguyên nằm trong `src/main/resources/scripts/`. `file:` chỉ rõ tài nguyên trên hệ thống file. Hỗ trợ classpath reference được bổ sung trong Spring Shell 4.0.4; không nên giả định cú pháp này có trong mọi bản 4.0.x trước đó.

Nếu đường dẫn có khoảng trắng, hãy đặt giá trị option trong dấu nháy theo parser của phiên bản đang chạy:

```text
shell:>script --file "/opt/inventory/scripts/setup kho.shell"
```

## 3. Cấu trúc và cú pháp tệp script

Tài liệu Spring Shell 4.0.4 quy định tệp script chứa một command trên mỗi dòng và các command được thực thi theo thứ tự. Dòng comment bắt đầu bằng `//`.

```text
// Bước 1: kiểm tra trạng thái
version
warehouse list

// Bước 2: tạo dữ liệu
product create --sku SKU-200 --name "Chuột không dây"
stock adjust --sku SKU-200 --warehouse HCM --quantity 15

// Bước 3: kiểm tra dữ liệu
stock show --sku SKU-200 --warehouse HCM
```

Các nguyên tắc nên áp dụng:

1. Mỗi command hoàn chỉnh nằm trên một dòng để tệp dễ đọc và dễ chuyển giữa các phiên bản.
2. Dùng `//` ở đầu dòng để ghi chú. Đây là dạng comment được tài liệu Spring Shell mô tả.
3. Dùng dấu nháy quanh giá trị có khoảng trắng, ví dụ `--name "Chuột không dây"`.
4. Dùng tên option, alias và giá trị đúng như command khai báo trong ứng dụng.
5. Đặt các bước kiểm tra trước hoặc sau thao tác ghi dữ liệu để người vận hành dễ xác nhận kết quả.

Không nên giả định `#`, `/* ... */` hoặc comment ở cuối một dòng command có cùng ý nghĩa với `//` ở đầu dòng. Những dạng này không nằm trong cú pháp script được tài liệu Spring Shell nêu; nếu cần ghi chú, hãy dùng một dòng riêng bắt đầu bằng `//`.

## 4. Comment và nối dòng trong Spring Shell 3.x

Tài liệu Spring Shell 3.1.3 nói rõ rằng dòng bắt đầu bằng `//` được bỏ qua và dòng kết thúc bằng dấu gạch chéo ngược `\` kích hoạt line continuation. Các dòng nối tiếp được xem như một command dài.

Ví dụ tệp `setup-3x.shell`:

```text
// Tạo sản phẩm và nhập kho
product create --sku SKU-300 \
  --name "Màn hình văn phòng" \
  --category DISPLAY

stock adjust --sku SKU-300 \
  --warehouse HN \
  --quantity 8
```

Parser ghép các dòng được nối thành một command trước khi thực thi. Dấu `\` phải nằm ở cuối dòng để biểu thị tiếp tục. Nếu dấu này xuất hiện như dữ liệu của option hoặc đường dẫn, hãy dùng cách quote/escape phù hợp để tránh bị hiểu là ký hiệu nối dòng.

### 4.1. Khác biệt khi chuyển sang 4.x

Tài liệu script Spring Shell 4.0.4 mô tả một command trên mỗi dòng và comment bắt đầu bằng `//`; tài liệu này không nêu bảo đảm về line continuation bằng `\` như tài liệu 3.1.3. Vì vậy, nếu một tệp cần chạy trên cả 3.x và 4.x, hãy viết mỗi command trên một dòng hoàn chỉnh. Nếu muốn dùng line continuation trong một phiên bản cụ thể, hãy kiểm tra trực tiếp bằng `help script` và thử trên đúng patch version trước khi đưa vào quy trình vận hành.

## 5. Dấu nháy, khoảng trắng và parser

Nội dung trong tệp được phân tích theo quy tắc command của Spring Shell, tương tự cách nhập command tại prompt. Dấu nháy gom nhiều từ thành một giá trị option; parser xử lý việc tách token và chuyển giá trị cho command.

Ví dụ:

```text
product create --sku SKU-400 --name "Bàn làm việc gỗ sồi"
user note --username linh --text "Đã xác nhận lịch giao hàng"
report export --format csv --output "/tmp/reports/stock tháng 11.csv"
```

Không cần thêm dấu nháy cho mọi giá trị. Chỉ dùng khi giá trị chứa khoảng trắng hoặc ký tự có ý nghĩa đặc biệt với parser. Khi cần chứa dấu nháy bên trong chuỗi, hãy thử quy tắc escape của parser đúng phiên bản và giữ ví dụ trong tài liệu kiểm thử.

Đường dẫn file trong tệp command cũng là giá trị option thông thường. Nó không tự động trở thành đường dẫn tương đối với thư mục chứa script. Nếu command nhận đường dẫn tương đối, cách phân giải thường phụ thuộc working directory của tiến trình hoặc logic của command; hãy dùng đường dẫn tuyệt đối khi cần kết quả nhất quán.

## 6. Tệp script không phải Bash hoặc PowerShell

Tệp script Spring Shell chỉ phát lại command mà ứng dụng đã đăng ký. Parser không phải shell hệ điều hành và không cung cấp đầy đủ các cấu trúc điều khiển của Bash, Zsh hay PowerShell.

| Cú pháp thường gặp trong shell hệ điều hành | Ý nghĩa trong Bash/PowerShell | Trong tệp script Spring Shell |
|---|---|---|
| `$NAME` hoặc `$env:NAME` | Đọc biến môi trường | Không có cơ chế nội suy biến shell được tài liệu script hỗ trợ |
| `if ...; then ...; fi` hoặc `if (...) { ... }` | Rẽ nhánh theo điều kiện | Không phải cấu trúc điều khiển của script Spring Shell |
| `for`, `while`, `foreach` | Lặp thao tác | Không có vòng lặp tích hợp trong cú pháp tệp |
| `command1 && command2` | Chạy lệnh sau khi lệnh trước thành công | Không được định nghĩa là toán tử nối command trong tệp Spring Shell |
| `command1 | command2` | Chuyển stdout sang stdin của tiến trình tiếp theo | Không tạo pipeline giữa các command Spring Shell |
| `command > output.txt` | Chuyển hướng stdout vào file | Không ghi output vào file theo cú pháp chuyển hướng của hệ điều hành |
| `$(command)` | Thay thế command bằng output của nó | Không có command substitution tích hợp |
| `# comment` | Comment trong Bash/PowerShell | Dùng dòng bắt đầu bằng `//` theo cú pháp Spring Shell |

Nếu đưa những ký hiệu này vào tệp, parser có thể coi chúng là token hoặc dữ liệu của command hiện tại rồi báo lỗi phân tích, lỗi command hoặc lỗi tham số. Chúng không tự kích hoạt shell hệ điều hành.

Ví dụ sau là cú pháp Bash, không phải tệp script Spring Shell:

```bash
if [ "$ENVIRONMENT" = "test" ]; then
  java -jar inventory-shell.jar stock report --format csv > stock.csv
fi
```

Trong tệp script Spring Shell, hãy chỉ đặt các command:

```text
stock report --format csv
```

Nếu cần điều kiện, vòng lặp, biến, pipe hoặc chuyển hướng, hãy viết Bash/PowerShell script bên ngoài để gọi ứng dụng ở chế độ non-interactive, hoặc triển khai một command Java thực hiện quy trình đó trong service/use case.

## 7. Chạy tệp bằng `@file` ở chế độ không tương tác

Ngoài built-in command `script`, Spring Shell còn có cách yêu cầu runner thực thi tệp từ đối số tiến trình bằng tiền tố `@`.

### 7.1. Spring Shell 3.1.x

Spring Shell 3.1.x có `ScriptShellRunner`. API mô tả runner này tìm các đối số tiến trình bắt đầu bằng `@` và coi phần còn lại là tham chiếu đến tệp script để chạy rồi thoát.

Ví dụ:

```bash
java -jar inventory-shell.jar @/opt/inventory/setup.shell
```

Trong Spring Shell 3.1.x, các runner `InteractiveShellRunner`, `NonInteractiveShellRunner` và `ScriptShellRunner` được cấu hình riêng. Thuộc tính `spring.shell.script.enabled` điều khiển runner script; hãy kiểm tra cấu hình ứng dụng nếu `@file` không được xử lý.

### 7.2. Spring Shell 4.x

Spring Shell 4 tổ chức runner lại. `NonInteractiveShellRunner` có thể thực thi một command hoặc một tệp script được chỉ định bằng cách thêm ký tự `@` trước tên file. Để ứng dụng chọn chế độ non-interactive, đặt:

```yaml
spring:
  shell:
    interactive:
      enabled: false
```

Sau đó gọi:

```bash
java -jar inventory-shell.jar @/opt/inventory/setup.shell
```

Trong Spring Shell 4, interactive mode mặc định được bật ngay cả khi có đối số dòng lệnh. Vì vậy, nếu muốn `NonInteractiveShellRunner` xử lý command hoặc `@file`, hãy cấu hình chế độ non-interactive rõ ràng. `@file` là cơ chế đầu vào của runner; nó khác với việc khởi động REPL rồi gõ built-in command `script --file ...`.

## 8. Phân biệt ba cách chạy tệp

| Cách chạy | Ngữ cảnh | Phiên bản và mục đích |
|---|---|---|
| `script --file ...` tại prompt | REPL đang chạy | Đọc và phát lại tệp từ bên trong shell; có trong 3.x và 4.x |
| `java -jar app.jar @commands.shell` | Runner xử lý đối số tiến trình | 3.1.x dùng `ScriptShellRunner`; 4.x dùng `NonInteractiveShellRunner` ở chế độ non-interactive |
| `bash setup.sh` hoặc `pwsh setup.ps1` | Shell hệ điều hành | Chạy ngôn ngữ script của hệ điều hành; có thể gọi ứng dụng Spring Shell nhiều lần |

Ba cách trên có thể cùng được dùng trong một quy trình, nhưng nội dung file và cú pháp của chúng không thể thay thế lẫn nhau. Hãy đặt phần command Spring Shell trong `.shell` hoặc `.txt`; đặt logic điều khiển hệ điều hành trong `.sh` hoặc `.ps1` để người đọc nhận biết đúng loại file.

## 9. Giới hạn về luồng điều khiển và trạng thái

Một tệp Spring Shell thực hiện danh sách command theo thứ tự. Cú pháp file không có biến cục bộ, biểu thức điều kiện, vòng lặp, hàm, import hoặc cơ chế truyền dữ liệu giữa các dòng như một ngôn ngữ scripting tổng quát.

Ví dụ, nếu cần tạo nhiều sản phẩm với các mã khác nhau, không thể dùng một vòng `for` Bash ngay trong tệp `.shell`. Có thể viết từng command:

```text
product create --sku SKU-501 --name "Sản phẩm A"
product create --sku SKU-502 --name "Sản phẩm B"
product create --sku SKU-503 --name "Sản phẩm C"
```

Nếu danh sách lớn hoặc thay đổi thường xuyên, hãy tạo một command như `product import --file products.csv` để command đọc dữ liệu bằng Java, xác thực từng dòng và gọi service. Cách này giữ logic xử lý dữ liệu trong ứng dụng, nơi có thể kiểm thử và quản lý lỗi tốt hơn.

Tệp script cũng không tạo một transaction chung cho tất cả command. Nếu command đầu đã ghi dữ liệu và command tiếp theo thất bại, không nên giả định các thay đổi trước đó tự động được rollback. Hãy thiết kế từng command an toàn khi chạy lại, kiểm tra trạng thái sau mỗi bước quan trọng và dùng transaction trong service cho một đơn vị nghiệp vụ cần tính nguyên tử.

Tài liệu mô tả thứ tự thực thi command nhưng không đưa ra một hợp đồng chung về rollback toàn tệp hoặc cú pháp `try/catch` cho từng dòng. Với quy trình cần xử lý lỗi có điều kiện, hãy triển khai logic điều phối trong Java hoặc trong shell script hệ điều hành.

## 10. Lỗi thường gặp khi chạy script

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy file | Đường dẫn tương đối được phân giải từ working directory khác dự kiến | Dùng đường dẫn tuyệt đối hoặc kiểm tra working directory |
| `script --file classpath:...` không hoạt động ở bản cũ | Hỗ trợ classpath resource được bổ sung trong 4.0.4 | Dùng đường dẫn file phù hợp với phiên bản hoặc nâng lên 4.0.4+ |
| Command có khoảng trắng bị tách tham số | Giá trị chưa được đặt trong dấu nháy | Quote giá trị theo parser Spring Shell |
| Dòng dài bị tách thành hai command ở 4.x | Dựa vào line continuation chỉ được tài liệu 3.1.3 mô tả rõ | Viết mỗi command trên một dòng hoàn chỉnh hoặc kiểm thử đúng patch version |
| `if`, `for` hoặc `$VAR` không hoạt động | Đang dùng cú pháp Bash/PowerShell trong tệp Spring Shell | Chuyển logic điều khiển sang `.sh`/`.ps1` hoặc command Java |
| `>` không tạo file output | Parser Spring Shell không xử lý redirection của hệ điều hành | Dùng shell hệ điều hành hoặc option `--output` do command cung cấp |
| `@file` không được chạy trong 4.x | Ứng dụng vẫn ở interactive mode | Đặt `spring.shell.interactive.enabled=false` để chọn non-interactive runner |
| Script dừng hoặc cho kết quả một phần | Một command có lỗi sau khi các bước trước đã tạo side effect | Kiểm tra output từng bước, thiết kế command idempotent và xử lý lỗi ở service/runner |
| Dòng comment làm phát sinh lỗi trên bản 4.0.0–4.0.1 | Các bản đầu 4.x có lỗi xử lý comment/empty line trong script | Dùng bản sửa mới hơn; Spring Shell 4.0.2 có các bản sửa liên quan script |

## 11. Thiết kế tệp script dễ bảo trì

**Đặt tên theo mục đích.** Dùng tên như `setup-demo-data.shell`, `verify-stock.shell` hoặc `prepare-test-environment.shell` thay vì `script1.txt`.

**Ghi chú trước mỗi nhóm thao tác.** Dùng `//` để người vận hành hiểu mục đích của các command tiếp theo.

**Giữ command có thể chạy lại.** Nếu script tạo dữ liệu, dùng mã định danh ổn định và thiết kế command để phát hiện dữ liệu đã tồn tại hoặc báo lỗi rõ ràng.

**Tách dữ liệu khỏi điều phối.** Với danh sách dài, dùng option `--file` của command nghiệp vụ để đọc CSV/JSON; không sao chép hàng trăm command vào tệp script.

**Tránh ghi bí mật trực tiếp.** Không lưu mật khẩu, token hoặc khóa truy cập trong tệp script được commit vào Git. Dùng cơ chế cấu hình/secret phù hợp và bảo đảm command không in giá trị nhạy cảm ra output.

**Kiểm tra trước khi chạy trên môi trường thật.** Đọc toàn bộ tệp, xác nhận profile và endpoint, thử trên dữ liệu không quan trọng rồi mới chạy ở môi trường có tác động thực tế.

## 12. Quy trình kiểm thử tệp script

Một tệp script nên được kiểm tra như một phần của ứng dụng, không chỉ kiểm tra bằng cách nhìn nội dung file.

1. Xác nhận từng command tồn tại bằng `help` và `help <command>`.
2. Chạy từng command riêng lẻ để kiểm tra option, dấu nháy, giá trị mặc định và quyền truy cập.
3. Chạy toàn bộ script trên môi trường thử nghiệm với dữ liệu có thể khôi phục.
4. Kiểm tra trạng thái sau mỗi bước ghi dữ liệu và xác định command nào đã hoàn thành nếu có lỗi.
5. Chạy lại script để đánh giá tính idempotent và cách ứng dụng xử lý dữ liệu trùng.
6. Kiểm tra riêng `script --file ...` trong REPL và `@file` qua runner nếu ứng dụng hỗ trợ cả hai cách.
7. Nếu hỗ trợ cả 3.x và 4.x, duy trì một tệp chỉ dùng cú pháp chung: một command trên mỗi dòng, comment `//`, không phụ thuộc line continuation.
8. Nếu script dùng resource `classpath:`, kiểm tra file thực sự được đóng gói trong artifact sau khi build.

Có thể kiểm thử từng command bằng `ShellTestClient` và kiểm thử service bằng unit/integration test. Tuy nhiên, việc kiểm thử command riêng không thay thế kiểm thử toàn bộ tệp vì thứ tự, dữ liệu do bước trước tạo ra và tính idempotent chỉ thể hiện khi chạy theo chuỗi.

## 13. Bài tập thực hành

Giả sử ứng dụng có các command `warehouse list`, `product create`, `stock adjust` và `stock show`.

1. Tạo tệp `prepare-stock.shell` với comment `//`, một command liệt kê kho, một command tạo sản phẩm và một command nhập tồn kho.
2. Chạy tệp trong REPL bằng built-in `script` và kiểm tra kết quả.
3. Thêm giá trị có khoảng trắng như `--name "Bàn phím cơ"` và xác nhận parser giữ nguyên một giá trị.
4. Với Spring Shell 3.1.x, nối một command dài bằng dấu `\` ở cuối dòng. Chạy lại để quan sát kết quả.
5. Dùng `@prepare-stock.shell` với runner phù hợp; trên Spring Shell 4, bật non-interactive mode trước khi gọi `@file`.
6. Thử đặt `if`, `for` hoặc `> output.txt` trong tệp `.shell`. Giải thích vì sao chúng không được xử lý như cú pháp Bash.
7. Viết một file Bash hoặc PowerShell riêng để kiểm tra biến môi trường, gọi ứng dụng Spring Shell và chuyển hướng output.
8. Chạy lại script hai lần trên môi trường thử nghiệm và ghi nhận command nào cần được thiết kế idempotent.

## 14. Tổng kết

Tệp script Spring Shell là danh sách command được parser của Spring Shell đọc và thực thi lần lượt. Dạng được tài liệu hỗ trợ gồm command trên từng dòng và comment bắt đầu bằng `//`; Spring Shell 3.1.3 còn mô tả line continuation bằng `\`. Spring Shell 4.0.4 hỗ trợ built-in `script --file` với đường dẫn tuyệt đối, `file:` và `classpath:`; runner non-interactive cũng có thể nhận tệp qua đối số `@file`.

Giới hạn quan trọng là tệp `.shell` không phải Bash hoặc PowerShell: nó không cung cấp biến shell, điều kiện, vòng lặp, pipeline, chuyển hướng hay command substitution. Hãy dùng tệp này để sắp xếp các command Spring Shell theo trình tự. Khi cần logic điều khiển, xử lý file dữ liệu lớn hoặc phối hợp tiến trình hệ điều hành, hãy chuyển phần đó sang command Java hoặc shell script phù hợp.

## Tài liệu tham khảo

- [Spring Shell 3.1.3 Reference Documentation](https://docs.spring.io/spring-shell/docs/3.1.3/docs/index.html) — mục 4.8.5 Script và 10.2 Shell Runners.
- [Spring Shell 3.1.x Script API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/commands/Script.html) — built-in command đọc và thực thi command từ một file.
- [Spring Shell 3.1.x JLine package API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/jline/package-summary.html) — `ScriptShellRunner` xử lý đối số bắt đầu bằng `@`.
- [Spring Shell 4.0.4 Script Documentation](https://docs.spring.io/spring-shell/reference/commands/builtin/script.html) — option `--file`, absolute path, `file:` và `classpath:` resource, command-per-line và comment.
- [Spring Shell 4.0.4 NonInteractiveShellRunner API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/NonInteractiveShellRunner.html) — thực thi một command hoặc script file qua tiền tố `@`.
- [Spring Shell 4.0.4 Execution Documentation](https://docs.spring.io/spring-shell/reference/execution.html) — lựa chọn interactive/non-interactive runner.
- [Spring Shell 4.x Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi runner và mô hình thực thi khi nâng từ 3.x lên 4.x.
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases) — các bản sửa lỗi script trong Spring Shell 4.0.2 và hỗ trợ classpath reference trong 4.0.4.

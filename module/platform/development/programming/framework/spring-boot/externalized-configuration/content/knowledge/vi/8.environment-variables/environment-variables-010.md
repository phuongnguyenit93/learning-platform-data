# Dấu nháy và ký tự đặc biệt khi chạy trên PowerShell hoặc shell Unix

## 1. Vì sao cấu hình Spring Boot bị thay đổi ngay trước khi ứng dụng nhận được?

Trong Spring Boot 3.3, bạn có thể cung cấp cấu hình bằng biến môi trường hoặc đối số khởi động. Thoạt nhìn, hai lệnh sau đều giống việc đặt một chuỗi:

```bash
APP_MESSAGE="Welcome $USER" java -jar app.jar
```

```powershell
$env:APP_MESSAGE = "Welcome $HOME"
java -jar .\app.jar
```

Nhưng **shell xử lý dấu nháy và các ký tự đặc biệt trước khi Java hay Spring Boot đọc giá trị**. Trong Bash, `$USER` có thể được thay bằng tên người dùng; trong PowerShell, `$HOME` có thể được thay bằng đường dẫn thư mục người dùng. Dấu nháy chỉ là cú pháp của shell và thường không nằm trong giá trị mà tiến trình Java nhận được.

Nếu một URL chứa `&`, một chuỗi chứa `$`, mật khẩu thử nghiệm chứa `!`, hay đường dẫn chứa dấu cách, lệnh chạy có thể cho kết quả khác mong muốn, bị tách thành nhiều đối số, hoặc thậm chí bị shell hiểu là lệnh điều khiển.

Bài này giúp bạn:

- Phân biệt chuỗi bạn **gõ vào terminal** và giá trị Spring Boot **thực sự nhìn thấy**.
- Biết lúc nào chọn **dấu nháy đơn** hay **dấu nháy kép** trong Bash trên Unix và trong PowerShell.
- Đưa giá trị chứa dấu cách, `$`, `#`, `&`, `;`, `|`, `*`, `?`, dấu nháy, dấu gạch chéo ngược và JSON vào biến môi trường đúng cách.
- Hiểu khác biệt giữa truyền qua **environment variable**, **đối số `--key=value`** và **thuộc tính JVM `-Dkey=value`**.
- Kiểm tra kết quả nhận được từ `Environment` hoặc `@ConfigurationProperties` trong Spring Boot 3.3.

Các ví dụ sử dụng Java 17+, Spring Boot 3.3.x, **Bash** cho phần shell Unix và **PowerShell** cho phần Windows/cross-platform. `app.jar` là tên JAR minh họa; hãy thay bằng đường dẫn JAR của ứng dụng.

## 2. Ba tầng cần phân biệt: shell → tiến trình Java → Spring Boot

Một lỗi cấu hình có thể xảy ra ở một trong ba tầng:

```text
Bạn nhập văn bản tại terminal
          |
          v
Bash hoặc PowerShell phân tích câu lệnh
- xác định ranh giới đối số
- bỏ dấu nháy cú pháp
- thực hiện nội suy biến khi thích hợp
- xử lý $, &, ;, |, *, ?, dấu cách, dấu thoát...
          |
          v
Tiến trình Java nhận
- bảng biến môi trường (environment)
- mảng đối số khởi động (arguments)
- thuộc tính hệ thống JVM (system properties)
          |
          v
Spring Boot 3.3 xây dựng PropertySource / Environment
- chuyển tên biến môi trường thành khóa cấu hình
- chọn giá trị có hiệu lực theo thứ tự ưu tiên
- giải quyết placeholder khi thích hợp
- liên kết giá trị vào kiểu Java
          |
          v
Bean sử dụng cấu hình
```

Ví dụ trong Bash:

```bash
APP_MESSAGE='Hello $USER & goodbye' java -jar app.jar
```

Với dấu nháy đơn, shell giữ nguyên chữ `$USER` và `&` trong giá trị biến `APP_MESSAGE`. Java không nhận hai dấu nháy bao ngoài. Khi Spring Boot đọc `APP_MESSAGE` dưới khóa `app.message`, nội dung được cung cấp là:

```text
Hello $USER & goodbye
```

Trong khi đó:

```bash
APP_MESSAGE="Hello $USER & goodbye" java -jar app.jar
```

Bash thay `$USER` bằng giá trị biến `USER` nếu có, còn `&` nằm **trong dấu nháy kép** nên chỉ là ký tự văn bản. Nếu `USER=alice`, giá trị sẽ là:

```text
Hello alice & goodbye
```

Cùng một chuỗi trông gần giống nhau, nhưng kết quả khác vì **shell đã nội suy trước**. Đây không phải hành vi riêng của Spring Boot.

## 3. Đặt tên biến môi trường cho thuộc tính Spring Boot

Cần làm đúng cả **tên biến** lẫn **giá trị biến**. Ví dụ tệp `application.properties` có:

```properties
app.message=Giá trị mặc định
app.timeout=5s
app.feature-enabled=false
```

Khi dùng `@ConfigurationProperties`, Spring Boot có cơ chế **liên kết tên linh hoạt (relaxed binding)** để ánh xạ tên cấu hình chuẩn sang biến môi trường.

Quy tắc đổi tên thuộc tính dạng chữ thường và dấu gạch nối sang biến môi trường:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch nối `-`.
3. Đổi thành chữ in hoa.

Ví dụ:

| Khóa Spring Boot | Tên biến môi trường |
| --- | --- |
| `app.message` | `APP_MESSAGE` |
| `app.timeout` | `APP_TIMEOUT` |
| `app.feature-enabled` | `APP_FEATUREENABLED` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `server.port` | `SERVER_PORT` |

Đặc biệt, `app.feature-enabled` tương ứng với **`APP_FEATUREENABLED`**, không nên tự đoán rằng chèn dấu `_` vào chỗ dấu gạch nối là luôn tương đương. Tên biến ở Unix cũng phân biệt chữ hoa và chữ thường; nên dùng tên in hoa theo quy ước.

Dấu nháy bao quanh **giá trị**, chẳng hạn `'Hello world'`, không sửa quy tắc đặt **tên biến**. Trước khi nghi ngờ lỗi dấu nháy, hãy chắc chắn ứng dụng đang tra cứu đúng khóa.

Trong ví dụ thông thường, nguồn biến môi trường có thể ghi đè tệp `application.properties`/YAML. Tuy nhiên, đối số dòng lệnh, thuộc tính JVM, nguồn JSON, profile và các nguồn khác còn tham gia thứ tự ưu tiên của Spring Boot. Đôi khi biến môi trường đã được truyền đúng nhưng giá trị cuối bị một nguồn ưu tiên cao hơn ghi đè.

## 4. Bash trên Unix: dấu nháy đơn

Dấu nháy đơn `'...'` là lựa chọn đơn giản nhất khi bạn muốn **giữ nguyên các ký tự bên trong**. Bash không thực hiện nội suy `$VARIABLE`, không chạy `$(...)`, không coi `&`, `;`, `|`, `*`, `?` là toán tử shell khi chúng nằm trong dấu nháy đơn.

Ví dụ:

```bash
APP_MESSAGE='Price $5; use A&B | C#1 * ?.txt' java -jar app.jar
```

Biến môi trường `APP_MESSAGE` có đúng phần văn bản:

```text
Price $5; use A&B | C#1 * ?.txt
```

Không có lệnh bổ sung nào được chạy bởi các dấu `;`, `&` hoặc `|` nằm bên trong chuỗi được nháy. Mẫu `*.txt` cũng không được mở rộng thành danh sách tệp.

Một ví dụ với URL có tham số truy vấn:

```bash
APP_ENDPOINT='https://api.example.test/search?q=red+blue&page=2&sort=desc' \
  java -jar app.jar
```

Dấu `&` của URL vẫn là một phần giá trị. Dấu `\` ở cuối dòng trong ví dụ là cú pháp **nối dòng của Bash**; nó không thuộc URL.

Một ví dụ chuỗi có dấu nháy kép:

```bash
APP_MESSAGE='He said "run now" & stopped.' java -jar app.jar
```

Dấu `"` nằm trong nháy đơn là văn bản bình thường. Java có thể nhận:

```text
He said "run now" & stopped.
```

### 4.1. Muốn chứa dấu nháy đơn thật thì làm gì?

Bash không cho chèn dấu nháy đơn vào giữa một đoạn `'...'` chỉ bằng `\'` **ở bên trong** cặp dấu nháy. Cách quen thuộc là đóng nháy đơn, chèn dấu nháy đơn được thoát ở bên ngoài, rồi mở lại:

```bash
APP_MESSAGE='It'\''s ready' java -jar app.jar
```

Kết quả:

```text
It's ready
```

Một trường hợp đơn giản khác có thể dùng dấu nháy kép nếu nội dung không chứa ký tự cần nội suy:

```bash
APP_MESSAGE="It's ready" java -jar app.jar
```

Với cấu hình phức tạp có nhiều dấu nháy và ký tự đặc biệt, nên cân nhắc đưa nội dung vào tệp cấu hình phù hợp thay vì tạo chuỗi shell quá khó đọc.

### 4.2. Dấu `!` trong Bash tương tác

Bash có tính năng **mở rộng lịch sử lệnh (history expansion)**, thường bật khi chạy tương tác. Ký tự `!` có thể mang ý nghĩa đặc biệt, kể cả trong một số chuỗi dấu nháy kép.

Ví dụ một chuỗi:

```bash
APP_MESSAGE='Hello! Please retry!' java -jar app.jar
```

Dấu nháy đơn giúp giữ nguyên các dấu `!`.

Không nên dựa vào cách Bash tương tác xử lý:

```bash
APP_MESSAGE="Hello! Please retry!" java -jar app.jar
```

vì history expansion có thể thay đổi cách phân tích chuỗi tùy tình huống và cấu hình shell. Trong nhiều script không tương tác, history expansion không bật mặc định, nhưng chọn dấu nháy đơn vẫn dễ dự đoán hơn khi cần ký tự `!` theo đúng nghĩa đen.

## 5. Bash trên Unix: dấu nháy kép

Dấu nháy kép `"..."` giữ dấu cách và phần lớn ký tự đặc biệt thành một phần giá trị, nhưng **vẫn cho phép nội suy biến, thay thế kết quả lệnh và một số phép xử lý dấu gạch chéo ngược**.

Ví dụ:

```bash
USER_LABEL='Lan'
APP_MESSAGE="Hello $USER_LABEL" java -jar app.jar
```

Giá trị được truyền là:

```text
Hello Lan
```

Trong Bash, cú pháp `$(...)` còn thực thi lệnh rồi thay bằng kết quả:

```bash
APP_MESSAGE="Built on $(date +%Y-%m-%d)" java -jar app.jar
```

Nếu bạn **muốn giữ nguyên** chuỗi `$(date +%Y-%m-%d)` để ứng dụng đọc như văn bản, phải dùng dấu nháy đơn:

```bash
APP_MESSAGE='Built on $(date +%Y-%m-%d)' java -jar app.jar
```

Hoặc phải thoát đúng các ký tự đặc biệt trong dấu nháy kép:

```bash
APP_MESSAGE="Literal \$HOME and \"quoted\"" java -jar app.jar
```

Giá trị mong đợi:

```text
Literal $HOME and "quoted"
```

Trong dấu nháy kép Bash, dấu `\` có vai trò đặc biệt trước `$`, dấu nháy kép, dấu gạch chéo ngược, dấu backtick và ký tự xuống dòng. Vì vậy, **không có quy tắc “một dấu backslash thoát mọi thứ” giống nhau cho mọi trường hợp**.

### 5.1. Vì sao `'$HOME'` và `"$HOME"` khác nhau?

```bash
APP_MESSAGE='$HOME' java -jar app.jar
```

Truyền đúng năm ký tự `$HOME`.

```bash
APP_MESSAGE="$HOME" java -jar app.jar
```

Truyền giá trị của biến `HOME`, ví dụ `/home/lan`.

Dấu nháy kép không có nghĩa “giữ nguyên văn bản”; nó nghĩa là **giữ thành một chuỗi nhưng vẫn thực hiện những phép nội suy được cho phép**.

### 5.2. Dấu gạch chéo ngược khi không có dấu nháy

Ngoài dấu nháy, `\` trong Bash thường thoát ý nghĩa của ký tự ngay sau nó:

```bash
APP_MESSAGE=Hello\ World java -jar app.jar
```

Cho giá trị `Hello World`.

Tuy vậy, khi giá trị chứa nhiều ký tự đặc biệt, chuỗi dài nhiều dấu `\` khó bảo trì hơn viết:

```bash
APP_MESSAGE='Hello World' java -jar app.jar
```

**Quy ước dễ nhớ:** dùng nháy đơn khi cần nguyên văn; dùng nháy kép khi cố ý muốn shell chèn giá trị biến hoặc kết quả lệnh.

## 6. Bash: đặt biến cho một lệnh hay xuất biến cho nhiều lệnh?

### 6.1. Chỉ áp dụng cho một lệnh

Trong Bash và các shell POSIX thông dụng, có thể đặt biến ngay trước lệnh:

```bash
APP_MESSAGE='Chỉ dùng trong lần chạy này' APP_TIMEOUT='2s' java -jar app.jar
```

Các biến được truyền cho tiến trình Java của lệnh đó. Sau khi lệnh kết thúc, việc gán theo dạng này không có ý nghĩa tự động lưu cấu hình cho các tiến trình chạy sau.

Đây là cách rất tiện khi so sánh hai lần chạy:

```bash
APP_MESSAGE='Lần A' java -jar app.jar
APP_MESSAGE='Lần B' java -jar app.jar
```

### 6.2. Dùng `export` cho các tiến trình con tiếp theo

```bash
export APP_MESSAGE='Đã export cho shell hiện tại'
export APP_TIMEOUT='4s'

java -jar app.jar
```

Khi một biến được export, tiến trình Java được shell khởi chạy có thể kế thừa biến đó. Nếu đặt:

```bash
APP_MESSAGE='Chưa export'
java -jar app.jar
```

thì không nên mặc định tiến trình Java nhận biến; một biến shell thông thường phải được export nếu muốn tiến trình con kế thừa nó.

Cũng có thể dùng chương trình `env` trên Unix:

```bash
env APP_MESSAGE='Value with space & $' APP_TIMEOUT='4s' java -jar app.jar
```

Lệnh này cho phép cung cấp biến môi trường cho tiến trình được gọi. **Đừng sao chép nguyên dạng `env NAME=value command` sang PowerShell rồi tưởng đó là cú pháp PowerShell tương đương.**

### 6.3. Kiểm tra trong shell trước khi chạy ứng dụng

Với **giá trị minh họa không nhạy cảm**:

```bash
export APP_MESSAGE='A & B; literal $HOME'
printf '%s\n' "$APP_MESSAGE"
```

Kết quả:

```text
A & B; literal $HOME
```

Dùng `"$APP_MESSAGE"` trong lệnh `printf` để tránh giá trị bị tách từ hay mở rộng mẫu tên tệp ngoài ý muốn.

Khi xong bài thực hành:

```bash
unset APP_MESSAGE
unset APP_TIMEOUT
```

Lưu ý việc `unset` ở shell hiện tại không xóa cấu hình đã được một tiến trình Java khác nhận lúc nó bắt đầu.

## 7. PowerShell: dấu nháy đơn

Trong PowerShell, chuỗi `'...'` cũng là **chuỗi nguyên văn (literal/verbatim string)**: không nội suy `$name` và không thực thi biểu thức `$(...)` bên trong.

Ví dụ:

```powershell
$env:APP_MESSAGE = 'Price $5; use A&B | C#1 * ?.txt'
java -jar .\app.jar
```

Java nhận giá trị:

```text
Price $5; use A&B | C#1 * ?.txt
```

Sự khác biệt lớn so với Bash nằm ở **cú pháp gán biến môi trường**:

```powershell
$env:APP_MESSAGE = 'Hello from PowerShell'
java -jar .\app.jar
```

PowerShell dùng đối tượng ổ biến môi trường `Env:` qua `$env:NAME`. Cú pháp:

```bash
APP_MESSAGE='Hello' java -jar app.jar
```

là cách thường dùng trong Bash, **không phải cú pháp gán biến môi trường trực tiếp của PowerShell**.

Một lệnh PowerShell khác với đường dẫn chứa dấu cách:

```powershell
$env:APP_MESSAGE = 'Hello A & B'
java -jar 'C:\Workspaces\My Demo\app.jar'
```

Dấu nháy đơn bao đường dẫn giúp PowerShell đọc đường dẫn JAR thành một đối số. Dấu nháy cú pháp không phải một phần đường dẫn.

### 7.1. Dấu nháy đơn thật trong chuỗi PowerShell

Trong dấu nháy đơn PowerShell, viết **hai dấu nháy đơn liên tiếp** để biểu diễn một dấu nháy đơn:

```powershell
$env:APP_MESSAGE = 'It''s ready'
```

Giá trị thực tế:

```text
It's ready
```

Đây **không** phải cú pháp như Bash `'It'\''s ready'`. Nếu cần soạn script chạy được trên cả hai hệ shell, phải tách cách viết cú pháp tương ứng.

### 7.2. Dấu nháy kép bên trong dấu nháy đơn

```powershell
$env:APP_MESSAGE = 'He said "Hello!" and left.'
```

PowerShell giữ nguyên dấu `"` và dấu `!` trong chuỗi:

```text
He said "Hello!" and left.
```

Khi giá trị chứa nhiều `$`, nháy kép và ký tự điều khiển, dùng chuỗi PowerShell trong nháy đơn thường dễ đọc hơn việc thoát từng ký tự.

## 8. PowerShell: dấu nháy kép, nội suy và backtick

Dấu nháy kép trong PowerShell cho phép nội suy biến và biểu thức:

```powershell
$name = 'Lan'
$env:APP_MESSAGE = "Hello $name"
```

Giá trị truyền cho tiến trình con là:

```text
Hello Lan
```

Với biến môi trường:

```powershell
$env:APP_MESSAGE = "Home: $env:USERPROFILE"
```

Nếu biến `USERPROFILE` có giá trị, PowerShell thay nó vào chuỗi. Trên những môi trường khác có thể sử dụng `$HOME`, nhưng **đó là biến PowerShell** và cách mở rộng của nó vẫn thuộc tầng shell.

PowerShell dùng **backtick** (dấu huyền `` ` ``) để thoát một số ký tự trong chuỗi nháy kép, không dùng dấu gạch chéo ngược theo quy tắc Bash.

Ví dụ:

```powershell
$env:APP_MESSAGE = "Literal `$HOME and `"quoted`""
```

Giá trị mong đợi:

```text
Literal $HOME and "quoted"
```

Trong chuỗi nháy kép, ký tự `` `n `` biểu diễn xuống dòng và `` `t `` biểu diễn tab:

```powershell
$env:APP_MESSAGE = "First line`nSecond line"
```

Giá trị nhận được chứa một ký tự xuống dòng thật giữa `First line` và `Second line`.

Đặt lại chuỗi trong nháy đơn:

```powershell
$env:APP_MESSAGE = 'First line`nSecond line'
```

thì hai ký tự backtick và `n` được giữ nguyên, không chuyển thành xuống dòng.

### 8.1. PowerShell không dùng backslash làm ký tự thoát nháy chung

Đừng mang nguyên thói quen Bash sang PowerShell:

```powershell
$env:APP_MESSAGE = "He said \"hello\""
```

Dấu `\` không phải ký tự thoát nháy trong cú pháp chuỗi PowerShell. Câu lệnh có thể bị phân tích khác mong đợi.

Viết đơn giản hơn:

```powershell
$env:APP_MESSAGE = 'He said "hello"'
```

Hoặc:

```powershell
$env:APP_MESSAGE = "He said `"hello`""
```

Nếu không cần nội suy, nháy đơn rõ ràng và ít lỗi hơn.

### 8.2. Lưu ý khi truyền trực tiếp đối số tới chương trình native

PowerShell gọi `java.exe` như một **lệnh native**. Cách chuyển đối số chứa dấu nháy nhúng sang chương trình native từng có khác biệt giữa Windows PowerShell 5.1 và PowerShell 7.x; PowerShell mới cũng có thiết lập liên quan đến cách truyền đối số.

Với giá trị đơn giản có dấu cách, có thể viết:

```powershell
java -jar .\app.jar '--app.message=Hello world'
```

Nhưng với JSON dài hoặc chuỗi chứa đồng thời dấu nháy kép, dấu nháy đơn và dấu gạch chéo ngược, nên **ưu tiên biến môi trường đã được gán rõ ràng**, hoặc kiểm tra cụ thể cách phiên bản PowerShell đang dùng truyền argv cho `java.exe`.

Trong PowerShell, toán tử `&` có thể được dùng để **gọi chương trình từ đường dẫn được nháy**, ví dụ:

```powershell
& 'C:\Program Files\Java\jdk-17\bin\java.exe' -jar '.\app.jar'
```

Đó là `&` ở vị trí cú pháp để gọi lệnh. Ký tự `&` nằm bên trong chuỗi nháy đơn như `'A&B'` chỉ là văn bản. Đừng nhầm cú pháp gọi chương trình với nội dung giá trị cấu hình.

## 9. Bảng so sánh dấu nháy: Bash và PowerShell

| Tình huống | Bash trên Unix | PowerShell |
| --- | --- | --- |
| Giữ nguyên `$HOME` | `'$HOME'` | `'$HOME'` |
| Cho shell chèn biến `name` | `"$name"` | `"$name"` |
| Giữ nguyên `$(...)` | `'$(date)'` | `'$(Get-Date)'` |
| Viết dấu `"` trong giá trị | `'He said "go"'` | `'He said "go"'` |
| Viết một dấu `'` trong chuỗi nguyên văn | `'It'\''s'` | `'It''s'` |
| Giữ nguyên `&`, `;`, `|` | `'A&B;C|D'` | `'A&B;C|D'` |
| Giữ nguyên dấu `!` | `'Hello!'` | `'Hello!'` |
| Chèn ký tự xuống dòng bằng cú pháp shell | `$'A\nB'` (riêng Bash) | `"A`nB"` |
| Thoát `$` trong nháy kép | `"\$HOME"` | `` "`$HOME" `` |
| Gán biến môi trường | `export APP_MESSAGE='value'` | `$env:APP_MESSAGE = 'value'` |
| Chỉ đặt biến cho một lệnh | `APP_MESSAGE='value' java -jar app.jar` | Gán `$env:` rồi gọi lệnh; dọn biến khi xong |

**Lưu ý về bảng:** nhiều cú pháp trong hai cột trông giống nhau, nhưng có những khác biệt nhỏ về nháy đơn, ký tự thoát và cơ chế truyền đối số cho chương trình native. Khi sao chép một lệnh từ Linux sang Windows, phải thay **toàn bộ cú pháp shell phù hợp**, không chỉ thay dấu `/` bằng `\`.

## 10. Ký tự đặc biệt thường gặp trong giá trị cấu hình

### 10.1. Dấu cách và tab

Không nên truyền URL, tên file hay thông báo chứa khoảng trắng dưới dạng đối số không nháy:

```bash
java -jar app.jar --app.message=Hello World
```

Trong Bash, `World` có thể trở thành một đối số riêng. Trong PowerShell, tương tự, cú pháp truyền đối số native không nên dựa vào cách shell tự đoán ý định.

Nên dùng:

```bash
java -jar app.jar '--app.message=Hello World'
```

Với PowerShell:

```powershell
java -jar .\app.jar '--app.message=Hello World'
```

Hoặc đặt biến môi trường trước khi gọi ứng dụng:

```bash
APP_MESSAGE='Hello World' java -jar app.jar
```

```powershell
$env:APP_MESSAGE = 'Hello World'
java -jar .\app.jar
```

Đặt toàn bộ `--app.message=Hello World` trong **một đối số** là cách tránh việc tách văn bản thành nhiều tham số.

### 10.2. Dấu `&` trong URL

Ví dụ giá trị phải giữ:

```text
https://api.example.test/items?size=10&sort=desc
```

Bash:

```bash
APP_ENDPOINT='https://api.example.test/items?size=10&sort=desc' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_ENDPOINT = 'https://api.example.test/items?size=10&sort=desc'
java -jar .\app.jar
```

Nếu bỏ dấu nháy, shell có thể coi `&` là ký hiệu điều khiển lệnh. Khi giá trị chứa nhiều dấu `?`, `&`, `=`, `#`, tốt nhất hãy giữ nguyên trong một chuỗi nháy.

### 10.3. Dấu `$` và dấu backtick

Nếu giá trị muốn giữ nguyên:

```text
Price $100; literal $(calc)
```

Bash:

```bash
APP_MESSAGE='Price $100; literal $(calc)' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'Price $100; literal $(calc)'
```

Đưa chuỗi vào nháy kép khi không có chủ ý nội suy là nguồn gây nhầm lẫn phổ biến. Ngoài ra, dấu backtick là một phần cú pháp thay thế lệnh trong Bash khi không được bảo vệ, đồng thời là ký tự thoát trong PowerShell. Nháy đơn bảo vệ được các trường hợp này trong hai shell.

### 10.4. Dấu `#` và dấu `;`

Trong Bash và PowerShell, `#` có thể mở đầu chú thích ở ngữ cảnh cú pháp thích hợp. Trong Bash, `;` tách các lệnh. Với PowerShell, `;` cũng là ký hiệu phân tách câu lệnh.

Ví dụ cần truyền:

```text
Release #2; mode=trial
```

Bash:

```bash
APP_MESSAGE='Release #2; mode=trial' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'Release #2; mode=trial'
```

Trong chuỗi nháy, `#` và `;` được giữ là văn bản thay vì tạo ranh giới câu lệnh.

### 10.5. Dấu `*`, `?`, dấu ngoặc và `|`

Bash có thể mở rộng mẫu tên tệp chứa `*` và `?` khi không được nháy; `|` có thể tạo pipeline. PowerShell cũng coi một số ký tự là phần của cú pháp lệnh, và có cơ chế ký tự đại diện trong các cmdlet.

Giá trị minh họa:

```text
pattern=(a|b)*?.txt
```

Hãy truyền dưới dạng:

```bash
APP_PATTERN='pattern=(a|b)*?.txt' java -jar app.jar
```

```powershell
$env:APP_PATTERN = 'pattern=(a|b)*?.txt'
```

Điều cần bảo đảm là **chuỗi đi vào tiến trình Java vẫn mang nghĩa dữ liệu**; ứng dụng có thể tự quyết định xem đó là regex, glob hay văn bản, tùy nghiệp vụ. Shell không nên tự diễn giải thay cho ứng dụng.

### 10.6. Dấu gạch chéo ngược và đường dẫn Windows

Trên PowerShell, viết:

```powershell
$env:APP_DIR = 'C:\Program Files\Demo App\data'
```

Trong nháy đơn PowerShell, các dấu `\` được giữ nguyên.

Trên Bash chạy trong môi trường Unix, một đường dẫn có dấu `\` nếu thực sự cần giữ nguyên như văn bản cũng nên dùng nháy đơn:

```bash
APP_DIR='C:\Program Files\Demo App\data' java -jar app.jar
```

Tuy nhiên, **đúng cú pháp chuỗi không có nghĩa đường dẫn Windows tồn tại trên Unix**. Đó là vấn đề độc lập về hệ thống tệp. Nếu đang chạy ứng dụng trên Linux, thường dùng đường dẫn Linux tương ứng.

### 10.7. Dấu `=` trong giá trị

Với URL hoặc token minh họa có nhiều dấu `=`:

```text
a=b=c
```

Bash:

```bash
APP_MESSAGE='a=b=c' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'a=b=c'
```

Shell tách phần gán theo cú pháp của nó; các dấu `=` còn lại nằm trong giá trị nếu bạn đã tạo đúng một chuỗi. Spring Boot không tự coi mỗi dấu `=` trong chuỗi biến môi trường là một cặp cấu hình mới.

## 11. Truyền cấu hình bằng `--key=value`, `-Dkey=value` và biến môi trường

Có ba đường truyền thường thấy:

| Cách truyền | Ví dụ | Tiến trình nào xử lý |
| --- | --- | --- |
| Biến môi trường | `APP_MESSAGE='Hello'` / `$env:APP_MESSAGE = 'Hello'` | Shell gán, Java kế thừa, Spring đọc từ môi trường |
| Đối số Spring Boot | `--app.message=Hello` | Shell tạo đối số; Spring Boot đọc khi khởi động |
| Thuộc tính hệ thống JVM | `-Dapp.message=Hello` | Shell tạo đối số; JVM xử lý thuộc tính hệ thống |

### 11.1. Bash với đối số Spring Boot

```bash
java -jar app.jar '--app.message=A&B; literal $HOME'
```

Toàn bộ `--app.message=A&B; literal $HOME` là một đối số; dấu nháy đơn được Bash loại bỏ trong bước phân tích lệnh.

### 11.2. PowerShell với đối số Spring Boot

```powershell
java -jar .\app.jar '--app.message=A&B; literal $HOME'
```

Với chuỗi đơn giản này, nháy đơn giữ `$HOME` thành văn bản. Nếu cần giữ dấu nháy kép **nằm bên trong đối số**, hãy lưu ý khác biệt theo phiên bản PowerShell khi truyền đối số cho chương trình native, hoặc chuyển sang biến môi trường để giảm việc phải thoát nhiều lớp ký tự.

### 11.3. Thuộc tính JVM phải đứng đúng vị trí

Bash:

```bash
java '-Dapp.message=Hello world' -jar app.jar
```

PowerShell:

```powershell
java '-Dapp.message=Hello world' -jar .\app.jar
```

Tham số `-Dapp.message=...` là tùy chọn của **JVM** nên đặt **trước** `-jar`. Nếu đặt sau đường dẫn JAR, nó không còn là cùng cách cung cấp thuộc tính hệ thống cho JVM; phần sau JAR được truyền như đối số của ứng dụng.

### 11.4. Dấu nháy không phải một phần cú pháp Spring

Ví dụ:

```bash
java -jar app.jar '--app.message=Hello world'
```

Trong Bash, dấu nháy đơn bảo vệ đối số khi shell phân tích. Spring Boot nhận:

```text
--app.message=Hello world
```

Spring không nhận hai dấu `'` bao ngoài. Nếu giá trị cuối có dấu `'`, phải viết dấu nháy **như dữ liệu** theo cú pháp shell, thay vì nghĩ rằng cặp dấu nháy dùng để bao đối số sẽ được giữ lại.

### 11.5. Đừng nhầm thứ tự ưu tiên

Theo thứ tự ưu tiên thông thường của Spring Boot 3.3, **đối số dòng lệnh ứng dụng** có thể ghi đè **thuộc tính hệ thống JVM**, còn thuộc tính hệ thống JVM có thể ghi đè **biến môi trường hệ điều hành**; những nguồn này thường ưu tiên hơn giá trị trong config data (`application.properties`/YAML). Tuy nhiên, các nguồn dành riêng cho kiểm thử và những cơ chế bổ sung có thể thay đổi bức tranh đầy đủ.

Nếu đặt `APP_MESSAGE=A`, nhưng chạy với `--app.message=B`, ứng dụng thường nhận `B`. Dấu nháy của `A` hay `B` không phải nguyên nhân; **thứ tự ưu tiên của nguồn** mới là điều cần xem xét.

## 12. Thực hành chạy được với Spring Boot 3.3

Tạo dự án Java 17, Spring Boot 3.3.x với dependency `spring-boot-starter` (có thể tạo qua Spring Initializr). Ví dụ dùng `@ConfigurationProperties` để quan sát giá trị cuối cùng từ các biến môi trường.

### Bước 1 — cấu hình mặc định

Tạo `src/main/resources/application.properties`:

```properties
spring.application.name=shell-quoting-lab

app.message=Default hello
app.timeout=5s
app.feature-enabled=false
```

### Bước 2 — tạo đối tượng cấu hình

`src/main/java/example/shellquoting/AppSettings.java`:

```java
package example.shellquoting;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(
        String message,
        Duration timeout,
        boolean featureEnabled
) {
}
```

Spring Boot liên kết `app.message`, `app.timeout` và `app.feature-enabled` vào kiểu Java tương ứng. `Duration` giúp kiểm tra một thời lượng như `2s` thay vì tự xử lý chuỗi thời gian trong ứng dụng.

### Bước 3 — đọc giá trị trong ứng dụng

`src/main/java/example/shellquoting/ShellQuotingApplication.java`:

```java
package example.shellquoting;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShellQuotingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShellQuotingApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(AppSettings settings, Environment env) {
        return args -> {
            System.out.println("message=" + settings.message());
            System.out.println("timeout=" + settings.timeout());
            System.out.println("featureEnabled=" + settings.featureEnabled());
            System.out.println("rawProperty=" + env.getProperty("app.message"));
        };
    }
}
```

`@ConfigurationPropertiesScan` đăng ký `AppSettings` và Spring đưa bean đó vào phương thức `showValues(...)`. Thuộc tính `app.message` không cần được đọc thủ công từ file trong mã Java.

Nếu chạy không có nguồn ghi đè, các dòng do `ApplicationRunner` in dự kiến:

```text
message=Default hello
timeout=PT5S
featureEnabled=false
rawProperty=Default hello
```

Chuỗi `PT5S` là dạng hiển thị thông dụng của `Duration` tương ứng 5 giây.

### Bước 4 — chạy từ Bash

Sau khi đóng gói thành JAR, ví dụ:

```bash
APP_MESSAGE='Unix literal: $HOME & "quoted" #1' \
APP_TIMEOUT='2s' \
APP_FEATUREENABLED='true' \
java -jar app.jar
```

Giá trị dự kiến trong ứng dụng:

```text
message=Unix literal: $HOME & "quoted" #1
timeout=PT2S
featureEnabled=true
rawProperty=Unix literal: $HOME & "quoted" #1
```

Vì toàn bộ phần sau dấu `=` nằm trong nháy đơn nên `$HOME` được giữ nguyên. Dấu `&` và `#` không làm tách câu lệnh.

### Bước 5 — chạy từ PowerShell

Trong PowerShell:

```powershell
$env:APP_MESSAGE = 'PowerShell literal: $HOME & "quoted" #1'
$env:APP_TIMEOUT = '2s'
$env:APP_FEATUREENABLED = 'true'

java -jar .\app.jar
```

Các dòng giá trị mong đợi:

```text
message=PowerShell literal: $HOME & "quoted" #1
timeout=PT2S
featureEnabled=true
rawProperty=PowerShell literal: $HOME & "quoted" #1
```

PowerShell không thay `$HOME` trong nháy đơn. `APP_FEATUREENABLED` minh họa tên biến môi trường tương ứng với `app.feature-enabled`.

### Bước 6 — thay nháy đơn bằng nháy kép có chủ đích

Bash:

```bash
APP_MESSAGE="Unix user: $USER" java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = "PowerShell home: $HOME"
java -jar .\app.jar
```

Quan sát giá trị cuối. Bạn sẽ thấy phần sau `$USER` hoặc `$HOME` được shell thay theo môi trường trước khi Java nhận được.

### Bước 7 — thử đối số ghi đè biến môi trường

Trong Bash:

```bash
APP_MESSAGE='From environment' \
java -jar app.jar '--app.message=From command line'
```

Trong PowerShell:

```powershell
$env:APP_MESSAGE = 'From environment'
java -jar .\app.jar '--app.message=From command line'
```

Trong trường hợp thông thường, `app.message` sẽ là `From command line`. Đây là ví dụ phân biệt lỗi **trích dẫn ở shell** và việc **Spring Boot chọn nguồn ưu tiên cao hơn**.

### Bước 8 — dọn biến sau thực hành

Bash:

```bash
unset APP_MESSAGE APP_TIMEOUT APP_FEATUREENABLED
```

PowerShell:

```powershell
Remove-Item Env:APP_MESSAGE
Remove-Item Env:APP_TIMEOUT
Remove-Item Env:APP_FEATUREENABLED
```

Các lệnh này tác động đến phiên shell hiện tại; không tự thay đổi môi trường của những tiến trình Java đã chạy từ trước.

## 13. JSON trong biến môi trường `SPRING_APPLICATION_JSON`

Spring Boot hỗ trợ `SPRING_APPLICATION_JSON` để cung cấp nhiều khóa cấu hình từ một chuỗi JSON. Đây là trường hợp dễ nhầm vì có **hai bộ quy tắc cú pháp độc lập**:

1. Shell xử lý nháy, `$`, backtick, dấu thoát khi gán biến.
2. Bộ phân tích **JSON** xử lý dấu `"`, `\`, `\n` và các ký tự thoát sau khi chuỗi đã đi vào tiến trình Java.

### 13.1. Bash: bọc JSON trong nháy đơn

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"Hello $USER & friends","timeout":"4s","feature-enabled":true}}' \
  java -jar app.jar
```

Chuỗi JSON được truyền nguyên văn qua shell, nên `$USER` không được Bash nội suy. Sau đó Spring Boot phân tích JSON và cung cấp các thuộc tính tương ứng.

Nếu muốn nội suy giá trị từ shell vào JSON, không nên nối chuỗi tùy tiện, nhất là khi giá trị có nháy kép hoặc backslash. Hãy dùng công cụ tạo JSON đúng chuẩn hoặc cơ chế cấp cấu hình có cấu trúc của nền tảng triển khai.

### 13.2. PowerShell: nháy đơn giữ JSON nguyên văn

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"Hello $HOME & friends","timeout":"4s","feature-enabled":true}}'
java -jar .\app.jar
```

Đây là cách thuận tiện vì dấu nháy kép bên trong JSON là cú pháp JSON, còn cặp nháy đơn bên ngoài là cú pháp PowerShell. Shell không thay `$HOME`.

### 13.3. Có dấu nháy kép thật trong giá trị JSON

Giả sử muốn giá trị là:

```text
He said "go"
```

Chuỗi JSON đúng cần thoát dấu nháy kép bên trong giá trị:

```json
{
  "app": {
    "message": "He said \"go\""
  }
}
```

Bash:

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"He said \"go\""}}' java -jar app.jar
```

PowerShell:

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"He said \"go\""}}'
java -jar .\app.jar
```

Ở đây dấu `\` trước nháy kép là **ký tự thoát của JSON**; vì JSON đã được bọc trong nháy đơn shell nên dấu `\` được giữ đủ để bộ phân tích JSON xử lý.

### 13.4. Đường dẫn có backslash trong JSON

Muốn một giá trị JSON biểu diễn đường dẫn:

```text
C:\Program Files\Demo App
```

Nội dung JSON phải biểu diễn dấu `\` theo cú pháp JSON, tức dùng `\\`:

```json
{"app":{"directory":"C:\\Program Files\\Demo App"}}
```

PowerShell:

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"directory":"C:\\Program Files\\Demo App"}}'
```

Bash:

```bash
SPRING_APPLICATION_JSON='{"app":{"directory":"C:\\Program Files\\Demo App"}}' java -jar app.jar
```

Các dấu `\\` trong JSON được chuyển thành dấu `\` trong giá trị cuối. Đừng lẫn việc thoát ký tự của **shell** với việc thoát ký tự của **JSON**.

### 13.5. JSON không hợp lệ làm lỗi xuất hiện ở tầng nào?

Ví dụ:

```json
{"app":{"message":"He said "go""}}
```

Chuỗi này sai cú pháp JSON vì nháy kép trong giá trị chưa được thoát. Dù bạn đặt cả chuỗi vào nháy đơn Bash hoặc PowerShell chính xác, Spring Boot vẫn không thể phân tích JSON đó.

Hãy tách vấn đề:

- Nếu shell báo lỗi cú pháp, câu lệnh có thể chưa khởi chạy Java.
- Nếu tiến trình Java khởi chạy nhưng Spring Boot báo lỗi parse JSON, xem cú pháp JSON và các ký tự thoát bên trong.
- Nếu JSON hợp lệ nhưng giá trị cuối sai, kiểm tra tên khóa, kiểu dữ liệu và thứ tự ưu tiên giữa các nguồn cấu hình.

**Nháy đúng ở shell chưa đủ để làm nội dung JSON đúng.**

## 14. Placeholder của Spring là một tầng xử lý khác

Có một điểm tinh tế khi muốn giữ nguyên chuỗi chứa cú pháp `${...}`.

Ví dụ Bash:

```bash
APP_MESSAGE='The text is ${HOME}' java -jar app.jar
```

Hoặc PowerShell:

```powershell
$env:APP_MESSAGE = 'The text is ${HOME}'
```

Nháy đơn giúp shell **không tự nội suy** `${HOME}`. Tuy nhiên, khi ứng dụng đọc giá trị thông qua một API có **giải quyết placeholder của Spring**, biểu thức `${HOME}` vẫn có thể được hiểu là tham chiếu thuộc tính ở tầng **Spring**. Vì vậy không nên mặc định rằng bảo vệ ký tự khỏi shell sẽ bảo vệ luôn khỏi mọi cơ chế xử lý chuỗi phía sau.

Cần phân biệt:

```text
$HOME       -> cú pháp nội suy biến của Bash/PowerShell trong ngữ cảnh thích hợp
${HOME}     -> cũng có thể là cú pháp shell; đồng thời giống placeholder Spring
$(command)  -> cú pháp thay thế lệnh/biểu thức của shell
```

Nếu ứng dụng thực sự cần lưu nguyên văn `${...}` như dữ liệu, hãy kiểm tra cách API đọc cấu hình của Spring xử lý placeholder và sử dụng cơ chế thoát hoặc kiểu lưu trữ phù hợp. Đây là vấn đề của **giải quyết placeholder**, khác với câu hỏi dấu nháy đơn hay dấu nháy kép ở shell.

Đối với một thông báo thông thường, chuỗi `$HOME` không có dấu `{}` thường thuận tiện hơn để minh họa việc giữ nguyên ký tự `$` mà không kích hoạt dạng placeholder `${...}` của Spring.

## 15. Các lỗi phổ biến và cách nhận biết

| Biểu hiện | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `Hello $USER` thành `Hello alice` | Dùng nháy kép Bash nên `$USER` bị nội suy | Dùng nháy đơn nếu muốn giữ nguyên chữ `$USER` |
| Giá trị sau `&` bị hiểu thành phần lệnh khác | URL/chuỗi chưa được nháy đúng | Bao toàn bộ giá trị trong nháy phù hợp |
| Đối số bị chia thành nhiều từ | Giá trị chứa dấu cách không được bao trong một đối số | Nháy toàn bộ `--key=value` |
| Bash báo lỗi liên quan đến `!` | History expansion của shell tương tác | Dùng nháy đơn cho chuỗi literal |
| PowerShell không hiểu kiểu gán `NAME=value command` | Sao chép cú pháp Bash sang PowerShell | Dùng `$env:NAME = 'value'` rồi gọi chương trình |
| PowerShell nhận thêm dấu `\` trước dấu `"` | Nhầm backslash là ký tự thoát nháy PowerShell | Dùng nháy đơn ngoài hoặc backtick trong nháy kép |
| JSON có dấu nháy bên trong báo lỗi | Cú pháp JSON thiếu `\"` | Sửa JSON rồi mới xét shell quoting |
| Đường dẫn `C:\...` trong JSON sai | JSON cần thoát `\` thành `\\` | Dùng `C:\\...` ở tầng JSON |
| Giá trị ứng dụng vẫn là giá trị cũ | Có nguồn ưu tiên cao hơn hoặc tiến trình cũ chưa khởi động lại | Kiểm tra `Environment`, nguồn ghi đè và khởi động lại |
| Biến có mặt trong shell nhưng Java không thấy | Bash chưa export hoặc tiến trình được chạy ở môi trường khác | Dùng `export`, dạng gán trước lệnh, hoặc cấu hình launch chính xác |
| `APP_FEATURE_ENABLED` không liên kết như dự đoán | Tên env không tuân theo quy tắc relaxed binding từ khóa có dấu `-` | Dùng `APP_FEATUREENABLED` |
| Giá trị xuất hiện thêm dòng trống/ký tự lạ | Dấu xuống dòng thật, CRLF, copy/paste hoặc cú pháp thoát khác shell | Quan sát chuỗi đầu vào tại nơi an toàn và kiểm tra từng tầng |
| Đối số `-D` không có tác dụng | Đặt sau `-jar`, hoặc shell chia tham số | Đưa `-D...` trước `-jar` |
| Dùng nháy đơn mà `${...}` vẫn được thay | Spring hoặc công cụ khác xử lý placeholder sau shell | Kiểm tra tầng placeholder, không chỉ cú pháp shell |

## 16. Cách kiểm tra đúng khi cấu hình có ký tự đặc biệt

Khi gặp một giá trị bất ngờ, hãy đi từ ngoài vào trong:

**Bước 1 — xác định shell thực tế.** Bạn đang sử dụng Bash, Zsh, PowerShell 5.1, PowerShell 7 hay một shell khác? Ví dụ dành cho Bash không mặc nhiên hoạt động trên Zsh và PowerShell. Bài này mô tả cụ thể Bash và PowerShell.

**Bước 2 — xác định cách truyền cấu hình.** Bạn đang đặt biến môi trường, dùng `--app.key=value` hay `-Dapp.key=value`? Mỗi cách cần cú pháp và vị trí đúng.

**Bước 3 — kiểm tra giá trị sau khi shell xử lý.** Chỉ thực hiện với chuỗi kiểm thử không nhạy cảm:

Bash:

```bash
export APP_MESSAGE='A&B; literal $HOME'
printf '%s\n' "$APP_MESSAGE"
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'A&B; literal $HOME'
Write-Output $env:APP_MESSAGE
```

Nếu tại bước này giá trị đã sai, cần sửa cú pháp shell trước.

**Bước 4 — xác nhận tiến trình Java đang nhận đúng biến.** Shell có thể giữ một biến chưa export, tiến trình Java có thể chạy từ IDE, dịch vụ, Docker hoặc terminal khác, và môi trường của tiến trình con có thể khác phiên shell đang quan sát.

**Bước 5 — kiểm tra tên thuộc tính và thứ tự ưu tiên.** Ví dụ `APP_MESSAGE` ứng với `app.message`; nguồn `--app.message=...` có thể ghi đè biến môi trường. Đừng nhầm vấn đề thứ tự ưu tiên với vấn đề dấu nháy.

**Bước 6 — đọc giá trị có hiệu lực trong Spring.** Trong môi trường phát triển, dùng `Environment#getProperty("app.message")` hoặc bean `@ConfigurationProperties` như ví dụ. Chỉ in giá trị minh họa, không in bí mật thật.

**Bước 7 — nếu dùng JSON, xác minh hai tầng.** Shell phải giữ nguyên chuỗi JSON; bản thân chuỗi JSON phải hợp lệ. Kiểm tra dấu `"` và dấu `\` ở tầng JSON.

**Bước 8 — kiểm tra có cần khởi động lại không.** Biến môi trường được truyền khi tiến trình Java bắt đầu; đổi biến ở terminal sau khi ứng dụng đã chạy thường không làm các bean hiện có tự cập nhật.

Một cách kiểm tra đơn giản trong mã Java, độc lập với Spring, là xem biến môi trường mà JVM nhận:

```java
String value = System.getenv("APP_MESSAGE");
System.out.println(value);
```

Chỉ dùng với chuỗi mẫu không nhạy cảm. Nếu `System.getenv` đã sai, lỗi nằm ở giai đoạn đưa biến vào tiến trình. Nếu `System.getenv` đúng nhưng `Environment#getProperty("app.message")` khác, hãy xem lớp ánh xạ tên, thứ tự ưu tiên và xử lý placeholder.

## 17. Môi trường triển khai, script và những khác biệt cần lưu ý

### 17.1. Terminal hiện tại khác tiến trình đã chạy

Ví dụ PowerShell:

```powershell
$env:APP_MESSAGE = 'First'
java -jar .\app.jar
$env:APP_MESSAGE = 'Second'
```

Việc gán `Second` không làm tiến trình Java đã khởi chạy trước đó tự thay đổi. Với một lần chạy ứng dụng mới từ PowerShell, biến mới có thể được kế thừa.

Bash cũng tương tự: một tiến trình con nhận bản môi trường tại thời điểm khởi chạy. Nếu chương trình cần thay đổi cấu hình trong khi đang chạy, phải có cơ chế cập nhật được thiết kế riêng.

### 17.2. Một tệp `.env` không tự đồng nghĩa với biến môi trường của Spring

Spring Boot không mặc định coi mọi tệp tên `.env` trong thư mục dự án là nguồn cấu hình tự động giống `application.properties`. Một số công cụ như Docker Compose, IDE hoặc script có thể đọc `.env` và chuyển thành biến môi trường, nhưng đó là **bước riêng của công cụ**.

Không nên lấy nội dung một tệp `.env` rồi chạy `source` một cách máy móc nếu nó không được viết bằng cú pháp shell và chưa được xem xét về độ tin cậy. Tệp YAML của Docker Compose cũng có quy tắc nháy và nội suy riêng, không đồng nhất với Bash/PowerShell tương tác.

### 17.3. Chạy từ IDE không nhất thiết dùng terminal đang mở

Nếu ứng dụng được chạy bằng nút Run trong IDE, IDE có thể đặt biến môi trường trong cấu hình chạy riêng. Biến bạn vừa export trong một terminal bên ngoài có thể không nằm trong môi trường của tiến trình IDE.

Khi kiểm tra, hãy xác định **cơ chế khởi động thật**: terminal, script, Gradle/Maven, IDE, container hoặc dịch vụ hệ điều hành.

### 17.4. Windows PowerShell và `cmd.exe` khác nhau

Ví dụ trong bài dùng PowerShell:

```powershell
$env:APP_MESSAGE = 'Hello'
```

Trong `cmd.exe`, cú pháp đặt biến môi trường lại khác. Do đó, không thể coi mọi câu lệnh “Windows” đều là PowerShell. Nếu tài liệu dự án đưa lệnh cho Windows, nên ghi rõ tên shell cần dùng.

### 17.5. Tên biến và ký tự Unicode

Tên biến môi trường thường nên dùng chữ Latin, số và gạch dưới, ví dụ `APP_MESSAGE`. **Giá trị** có thể chứa tiếng Việt và nhiều ký tự Unicode. Tuy nhiên, cách hiển thị terminal và mã hóa ký tự có thể khác theo hệ điều hành, terminal hoặc file nguồn script.

Khi thấy chữ tiếng Việt bị lỗi hiển thị, cần phân biệt:

- Chuỗi đã sai trước khi vào Java hay chỉ sai khi hiển thị?
- Script và terminal đang dùng mã hóa nào?
- Java đang in văn bản ra console theo cách nào?

Không phải mọi lỗi hiển thị Unicode đều do chọn nháy đơn hoặc nháy kép sai.

## 18. Thực hành tự kiểm tra

### Bài 1 — dự đoán nội suy Bash

Giả sử `USER=an`:

```bash
APP_MESSAGE='Hello $USER' java -jar app.jar
APP_MESSAGE="Hello $USER" java -jar app.jar
```

Hai lần chạy sẽ nhận `app.message` là gì?

**Đáp án:** lần thứ nhất là `Hello $USER`; lần thứ hai là `Hello an`, nếu biến `USER` đúng bằng `an`.

### Bài 2 — bảo vệ URL

URL:

```text
https://shop.example.test/search?term=a+b&sort=price
```

Viết một câu lệnh Bash và một đoạn PowerShell để truyền URL qua `APP_ENDPOINT`, giữ nguyên cả `?`, `&` và dấu `=`.

**Đáp án Bash:**

```bash
APP_ENDPOINT='https://shop.example.test/search?term=a+b&sort=price' java -jar app.jar
```

**Đáp án PowerShell:**

```powershell
$env:APP_ENDPOINT = 'https://shop.example.test/search?term=a+b&sort=price'
java -jar .\app.jar
```

### Bài 3 — ký tự `$`, dấu nháy kép và dấu chấm than

Muốn ứng dụng nhận chính xác:

```text
Cost $20! He said "yes".
```

**Đáp án Bash:**

```bash
APP_MESSAGE='Cost $20! He said "yes".' java -jar app.jar
```

**Đáp án PowerShell:**

```powershell
$env:APP_MESSAGE = 'Cost $20! He said "yes".'
```

Dấu nháy đơn bao ngoài là cú pháp shell; dấu nháy kép bên trong là nội dung.

### Bài 4 — có dấu nháy đơn trong giá trị

Muốn ứng dụng nhận:

```text
It's John's app
```

**Đáp án Bash:**

```bash
APP_MESSAGE='It'\''s John'\''s app' java -jar app.jar
```

**Đáp án PowerShell:**

```powershell
$env:APP_MESSAGE = 'It''s John''s app'
```

### Bài 5 — JSON nhiều tầng

Muốn `SPRING_APPLICATION_JSON` cung cấp `app.message` đúng bằng `He said "go"`.

**Đáp án Bash:**

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"He said \"go\""}}' java -jar app.jar
```

**Đáp án PowerShell:**

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"He said \"go\""}}'
java -jar .\app.jar
```

Dấu `\"` thuộc tầng JSON; nháy đơn thuộc tầng shell.

### Bài 6 — tên biến theo relaxed binding

Khóa cấu hình:

```properties
app.client.connect-timeout=5s
```

Tên biến môi trường phù hợp theo quy tắc dành cho `@ConfigurationProperties` là gì?

**Đáp án:** `APP_CLIENT_CONNECTTIMEOUT`. Thay dấu chấm thành `_`, bỏ dấu `-`, đổi thành chữ hoa.

### Bài 7 — phân biệt quoting với precedence

```bash
APP_MESSAGE='Environment Value' java -jar app.jar '--app.message=CLI Value'
```

Ứng dụng có thể nhận giá trị nào? Vì sao?

**Đáp án:** `CLI Value` theo thứ tự ưu tiên thông thường của Spring Boot. Dấu nháy đơn của biến môi trường đã hợp lệ; chính đối số dòng lệnh ưu tiên cao hơn cung cấp giá trị cuối.

### Bài 8 — phân biệt shell và Spring placeholder

```bash
APP_MESSAGE='${HOME}' java -jar app.jar
```

Có thể kết luận rằng mọi API Java/Spring đều nhận đúng các ký tự `${HOME}` không?

**Đáp án:** không. Nháy đơn bảo vệ `${HOME}` khỏi nội suy của Bash, nhưng các API của Spring có khả năng giải quyết placeholder có thể xử lý tiếp biểu thức này. Cần xác định rõ API và tầng xử lý.

## 19. Nguyên tắc thực hành dành cho dự án Spring Boot

Một số quy ước giúp giảm lỗi khi chuyển câu lệnh giữa Unix và Windows:

1. **Dùng nháy đơn cho giá trị literal** khi không cần nội suy: trong Bash và PowerShell, đây thường là lựa chọn dễ dự đoán.
2. **Dùng nháy kép có chủ đích** khi thực sự cần `$VARIABLE` hoặc biểu thức shell được thay bằng giá trị.
3. **Ghi rõ shell ở đầu ví dụ**: `bash`, `powershell`; không tạo một đoạn lệnh chung cho hai cú pháp gán biến khác nhau.
4. **Với PowerShell, dùng `$env:NAME = 'value'`** để đặt biến cho tiến trình con. Với Bash, dùng `export` hoặc gán ngay trước lệnh.
5. **Nháy toàn bộ đối số `--key=value`** nếu giá trị có dấu cách hoặc ký tự điều khiển shell.
6. **Nếu dùng JSON, kiểm tra riêng cú pháp JSON**, đặc biệt dấu `\"` và `\\`.
7. **Dùng tên biến môi trường theo quy tắc của Spring Boot**, nhất là thuộc tính có dấu gạch nối.
8. **Quan sát giá trị ở đúng tiến trình Java đang chạy**, không chỉ nhìn biến ở một terminal khác.
9. **Giới hạn việc in cấu hình trong ví dụ** vào những giá trị không nhạy cảm.
10. **Không đưa mật khẩu hay token thật trực tiếp lên dòng lệnh hoặc log**; cú pháp nháy đúng không đồng nghĩa với bảo vệ bí mật. Khi triển khai thật, dùng cơ chế quản lý bí mật phù hợp với hạ tầng.

Nếu một giá trị chứa quá nhiều loại dấu nháy, JSON lồng nhau, xuống dòng và ký tự thoát, việc đặt nó trong tệp cấu hình hoặc nguồn cấu hình có cấu trúc thường dễ bảo trì hơn một câu lệnh terminal dài.

## 20. Ghi nhớ cốt lõi

```text
Lớp 1 — Bash / PowerShell:
  Nháy đơn   -> thường giữ nguyên văn bản
  Nháy kép   -> có thể nội suy biến / biểu thức
  Cú pháp gán environment khác nhau giữa hai shell

Lớp 2 — Tiến trình Java:
  Nhận environment, argv và -D sau khi shell phân tích

Lớp 3 — Spring Boot:
  Ánh xạ tên biến -> chọn nguồn ưu tiên -> liên kết vào bean
  Có thể còn giải quyết placeholder hoặc parse JSON
```

Khi cấu hình Spring Boot 3.3 bằng biến môi trường, hãy luôn trả lời lần lượt: **Shell nào đang chạy? Giá trị thật sau khi shell xử lý là gì? Java có nhận đúng biến không? Spring Boot cuối cùng chọn giá trị từ nguồn nào?** Cách phân chia thành ba tầng giúp tìm đúng nguyên nhân của hầu hết lỗi liên quan dấu nháy và ký tự đặc biệt.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, Property Source Order và Binding From Environment Variables: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- GNU Bash Reference Manual — Quoting, Single Quotes, Double Quotes và Shell Expansions: https://www.gnu.org/software/bash/manual/bash.html
- GNU Bash Reference Manual — History Interaction: https://www.gnu.org/software/bash/manual/html_node/History-Interaction.html
- Microsoft Learn — PowerShell about_Quoting_Rules: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
- Microsoft Learn — PowerShell about_Parsing: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing

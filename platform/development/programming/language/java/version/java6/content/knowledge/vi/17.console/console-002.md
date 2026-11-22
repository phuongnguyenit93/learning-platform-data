# Trường hợp console không tồn tại và chiến lược thay thế trong Java

`System.console()` trả về một đối tượng `java.io.Console` **nếu** JVM hiện tại có thiết bị console ký tự thích hợp, và trả về **`null` nếu không có**. Đây không phải tình huống bất thường: chương trình Java thường chạy trong IDE, pipeline, container, CI, tác vụ nền, dịch vụ hoặc môi trường có luồng nhập/xuất chuyển hướng. Nếu gọi ngay `System.console().readLine()` hay `System.console().readPassword()`, ứng dụng có thể ném `NullPointerException`.

Một thiết kế tốt phải xác định rõ **dữ liệu nào cần nhập**, **có yêu cầu bảo mật hay không**, và **có thật sự được phép chờ người dùng gõ trực tiếp hay không**. Không có console không đồng nghĩa không có `System.in`, nhưng `System.in` cũng **không được bảo đảm** chứa dữ liệu hay có người đang nhập.

Bài học thuộc chủ đề `Console`, dùng API vẫn còn áp dụng trong **Java 17+** và lưu ý thay đổi thực tế của JDK 25/26. Ví dụ chính chạy với Java 17 trở lên, không phụ thuộc thư viện ngoài.

## 1. Phân biệt Console và standard streams

Java có hai nhóm API liên quan:

| API | Ý nghĩa | Cần nhớ |
| --- | --- | --- |
| `System.console()` | Lấy thiết bị console tương tác, nếu JVM có. | Có thể `null`; kiểm tra trước khi gọi method. |
| `Console.readLine(prompt, args...)` | Hiện prompt và đọc một dòng từ console. | Trả `null` khi EOF; có thể block nếu đang chờ người gõ. |
| `Console.readPassword(prompt, args...)` | Đọc bí mật mà không echo như input thông thường. | Trả `char[]` hoặc `null` khi EOF; phải xóa array sau sử dụng. |
| `System.in` | Luồng nhập bytes chuẩn của tiến trình. | Có thể đọc từ keyboard, file, pipe hoặc nguồn khác; có thể EOF/block. |
| `System.out` | Luồng output chuẩn. | Có thể được redirect; nên dành cho kết quả bình thường. |
| `System.err` | Luồng lỗi chuẩn. | Hữu ích cho lỗi cấu hình, usage và diagnostics của CLI. |
| `BufferedReader` + `InputStreamReader` | Đọc dòng text từ `System.in` với charset xác định. | Thích hợp cho dữ liệu **không nhạy cảm** qua pipe/file. |
| Tham số lệnh/config | Dữ liệu được cung cấp trước khi chạy. | Tránh phụ thuộc thiết bị tương tác; không đưa password vào argv. |

`System.console() == null` là thông tin về **thiết bị console tương tác**, không phải phép thử “`System.in` có tồn tại không?”. `System.in` có thể trỏ đến file hoặc pipe và vẫn sử dụng được ngay cả khi không có console.

Ngược lại, `System.console() != null` cũng **không bảo đảm lần đọc tiếp theo sẽ có dữ liệu**: người dùng có thể đóng input hoặc runtime có console nhưng input kết thúc ngay. Vì vậy phải kiểm tra **cả console null lẫn kết quả `readLine()/readPassword()` null**.

### Khi nào `System.console()` có thể trả null?

Những bối cảnh thường gặp:

- Chạy bằng nút Run trong IDE, nơi input/output do IDE quản lý thay vì một terminal tương tác thực.
- Chạy trong pipeline: `printf 'abc\n' | java App`, hoặc đọc input từ file redirect.
- Standard output được chuyển đến file hoặc stream thu log.
- Chạy trong CI/CD, task scheduler, Windows service, Linux service, cron, container không cấp interactive TTY.
- Chạy trong môi trường test hoặc host ứng dụng nơi JVM không được gắn thiết bị console thích hợp.

**Không khẳng định cứng mọi môi trường đều hành xử giống nhau.** Runtime, hệ điều hành, phiên bản JDK và cách JVM được khởi động đều ảnh hưởng. JDK 25 đổi lại default Console implementation không dùng JLine; tài liệu Console của Java 26 nêu rõ khi stdin/stdout chuyển hướng hoặc chạy nền, console sẽ không tồn tại. Các JDK trước đó (đặc biệt nhóm có JLine-based default) có thể hành xử khác trong terminal giả lập. **Luôn viết code phòng thủ trước cả `null` lẫn EOF**, thay vì dùng tên IDE/hệ điều hành để suy ra kết quả.

## 2. Quy tắc quan trọng: thiếu Console không có nghĩa nên hỏi qua stdin

Một mẫu code **dễ lỗi**:

```java
// Sai trong môi trường không có console:
String user = System.console().readLine("Username: ");
```

Khi `System.console() == null`, câu lệnh ném `NullPointerException`. Cách phòng vệ tối thiểu:

```java
import java.io.Console;

Console console = System.console();
if (console == null) {
    throw new IllegalStateException(
            "Interactive console unavailable; supply input explicitly");
}
String user = console.readLine("Username: ");
if (user == null) {
    throw new IllegalStateException("Console input reached EOF");
}
```

Đây là **mảnh code minh họa**, không phải một class biên dịch độc lập. Cách này **tốt cho chương trình bắt buộc tương tác** nhưng chưa có chiến lược nhận dữ liệu thay thế.

Một fallback thiếu cân nhắc cũng có rủi ro:

```java
// Không nên tự động làm thế cho mọi loại đầu vào:
if (System.console() == null) {
    String password = new java.util.Scanner(System.in).nextLine();
}
```

Nhược điểm: nếu input rỗng sẽ có thể ném `NoSuchElementException`; nếu luồng vẫn mở có thể **treo chờ vô hạn**; và với **password** đây là một đường nhập có thể echo hoặc lưu trong log/shell history. Không được thay `readPassword()` bằng `Scanner(System.in)` một cách tự động chỉ để “cho chạy được”.

**Nguyên tắc thiết kế:** phân biệt **dữ liệu thường** (tên, lựa chọn, đường dẫn) với **secret** (mật khẩu, token, private key). Chỉ dữ liệu thường mới phù hợp với line-input qua pipe trong một hợp đồng CLI rõ ràng.

## 3. Ma trận chọn chiến lược theo môi trường

| Tình huống | Chiến lược phù hợp | Điều cần tránh |
| --- | --- | --- |
| Chạy trực tiếp trong terminal, nhập tên/lựa chọn | `Console.readLine` sau kiểm tra null | Gọi `System.console()` không kiểm tra. |
| Tên hoặc giá trị không nhạy cảm đã biết trước | `--name` hoặc tham số cấu hình rõ ràng | Bắt user gõ mỗi lần dù chạy automation. |
| Pipeline có chủ đích gửi một dòng dữ liệu | Chế độ `--stdin`, đọc `BufferedReader(System.in)` | Tự động tiêu thụ pipe khi user chưa yêu cầu. |
| Input nhiều dòng hoặc định dạng JSON | Chọn contract `--stdin` và parser phù hợp, validation | Dùng `readLine()` một lần rồi tưởng đã đọc đủ JSON. |
| Batch/CI/service/container không có TTY | Cung cấp config qua file/flags/runtime injection hoặc fail nhanh | Prompt chờ người gõ không tồn tại. |
| Desktop/web app | Dùng form/UI/API của framework tương ứng | Cố dùng `System.console()` làm input cho web request. |
| Test tự động | Inject `Reader`/`InputStream` giả vào logic nhập liệu | Test phụ thuộc terminal của IDE/CI, dùng `System.setIn` vô tội vạ. |
| Password/token | `Console.readPassword` khi có console; không có thì dùng secret manager/kênh cung cấp bảo mật đã quy định hoặc từ chối | Fallback sang `System.in` echo hoặc truyền secret qua argv/log. |

Bảng trên là **chiến lược** chứ không phải một bảo đảm JVM tự phát hiện môi trường hoàn toàn đúng. Một chương trình CLI nên mô tả rõ contract: ví dụ “`--name NAME`”, “`--stdin`”, hoặc “không tham số thì yêu cầu console tương tác”.

## 4. Ví dụ hoàn chỉnh Java 17+: hỗ trợ console, tham số hoặc stdin

Chương trình này xử lý một dữ liệu **không nhạy cảm** là tên người dùng. Thay vì âm thầm fallback sang `System.in`, nó cho phép caller chọn:

- `java ConsoleFallbackDemo --name Ada`: nhận từ command line.
- `java ConsoleFallbackDemo --stdin`: đọc **một dòng** từ standard input theo UTF-8, thường cấp bởi pipe hoặc file.
- `java ConsoleFallbackDemo`: thử console tương tác; nếu không có console hoặc không nhận được dòng thì báo lỗi rõ ràng và kết thúc.

Vì dành cho automation, chế độ không có input sẽ **không tiếp tục với tên giả** và không nuốt lỗi.

### 4.1. Tệp `ConsoleFallbackDemo.java`

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class ConsoleFallbackDemo {
    private static void fail(String message) {
        System.err.println("ERROR: " + message);
        System.exit(2);
    }

    public static void main(String[] args) throws IOException {
        String name;
        if (args.length == 2 && "--name".equals(args[0])) {
            name = args[1];
        } else if (args.length == 1 && "--stdin".equals(args[0])) {
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
            name = input.readLine();
            if (name == null) {
                fail("stdin ended before a line was read");
                return;
            }
        } else if (args.length == 0) {
            Console console = System.console();
            if (console == null) {
                fail("no console; pass --name NAME or --stdin");
                return;
            }
            name = console.readLine("Your name: ");
            if (name == null) {
                fail("console input ended");
                return;
            }
        } else {
            fail("usage: java ConsoleFallbackDemo [--name NAME | --stdin]");
            return;
        }
        name = name.strip();
        if (name.isEmpty()) {
            fail("name must not be blank");
            return;
        }
        System.out.println("Hello, " + name + "!");
    }
}
```

**Giải thích từng nhánh:**

1. `--name` dùng dữ liệu caller đã cung cấp; không gọi Console và không chờ stdin. Thích hợp cho giá trị **không bí mật**.
2. `--stdin` tạo `InputStreamReader` với `StandardCharsets.UTF_8` theo hợp đồng đầu vào của ví dụ và đọc đúng **một dòng** bằng `BufferedReader.readLine()`.
3. Nếu `readLine() == null` nghĩa là **EOF trước khi đọc được bất kỳ ký tự của dòng đó**. Không gọi `strip()` trên null.
4. Không tham số → thử `System.console()`. Nếu không có console thì thông báo cách cấp dữ liệu tường minh; nếu có nhưng `Console.readLine()` trả null thì báo input kết thúc.
5. `String.strip()` (có từ Java 11) bỏ khoảng trắng hai đầu, phù hợp với tên trong ví dụ; **không áp dụng máy móc cho secret**, vì ký tự whitespace có thể là một phần hợp lệ của mật khẩu.
6. `System.err` dành cho lỗi; chương trình kết thúc với **exit code 2** khi cấu hình/input không hợp lệ. Đây là lựa chọn của ví dụ, không phải một mã lỗi chuẩn được Java quy định.
7. Ví dụ cố ý **không `close()` reader bọc `System.in`** vì đây là luồng toàn cục có thể còn được thành phần khác dùng. Với file stream do ứng dụng tự mở và sở hữu, nên dùng `try-with-resources`.
8. `System.exit` chỉ nằm ở tầng entrypoint CLI đơn giản. Khi viết library, nên trả lỗi có kiểu hoặc ném exception để caller tự quyết định lifecycle.

### 4.2. Biên dịch

Lệnh dùng JDK 17 trở lên:

```bash
javac --release 17 ConsoleFallbackDemo.java
```

Nếu chỉ có JDK 17, vẫn chạy được. `--release 17` giúp compiler JDK mới không vô tình cho phép sử dụng API hoặc cú pháp chỉ tồn tại ở release mới hơn.

### 4.3. Cách chạy 1: tham số không nhạy cảm

```bash
java ConsoleFallbackDemo --name Ada
```

**Stdout đã kiểm chứng trên JDK 24:**

```text
Hello, Ada!
```

Exit code: `0`.

### 4.4. Cách chạy 2: pipe dữ liệu qua stdin

Trên Linux/macOS với shell hỗ trợ `printf`:

```bash
printf 'Lan\n' | java ConsoleFallbackDemo --stdin
```

Kết quả mong đợi:

```text
Hello, Lan!
```

Trên Windows PowerShell 5.1, để kiểm soát bytes UTF-8 và **tránh BOM do một số cách pipe text của shell đưa vào**, có thể tạo file UTF-8 **không BOM**, rồi cho `cmd` gửi bytes từ file:

```powershell
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    "input.txt", "Lan" + [Environment]::NewLine, $utf8)
cmd /c "type input.txt | java ConsoleFallbackDemo --stdin"
```

**Stdout đã kiểm chứng với file UTF-8 không BOM trên Windows/JDK 24:**

```text
Hello, Lan!
```

Exit code: `0`.

Điểm quan trọng: `System.console()` có thể không tồn tại trong pipeline, nhưng `System.in` vẫn nhận bytes. Chế độ `--stdin` hoạt động vì **caller cố ý cấp dữ liệu**, không phải vì chương trình đoán từ trạng thái console.

### 4.5. Cách chạy 3: stdin rỗng, chỉ toàn khoảng trắng hoặc không có console

Với `--stdin` và **dòng input không tồn tại (EOF)**:

```text
ERROR: stdin ended before a line was read
```

Với `--stdin` và **dòng chỉ có khoảng trắng**:

```text
ERROR: name must not be blank
```

Hai trường hợp đã kiểm chứng trả exit code `2`. Phân biệt:

- Input trống về mặt dữ liệu (`EOF`) → `readLine() == null`.
- Có một dòng nhưng chỉ là khoảng trắng → `readLine()` không null, `strip().isEmpty() == true`.

Khi chạy `java ConsoleFallbackDemo` **không có tham số**, có hai nhánh lỗi có thể xảy ra tùy runtime:

```text
ERROR: no console; pass --name NAME or --stdin
```

hoặc (nếu runtime trả một Console nhưng input đã kết thúc):

```text
Your name: ERROR: console input ended
```

Trường hợp thứ hai đã được **quan sát khi chạy trong môi trường kiểm thử JDK 24**. Đừng coi hai nhánh là output bắt buộc giống nhau trên mọi JDK. Trong terminal tương tác thực với người dùng gõ tên hợp lệ, chương trình sẽ in lời chào và kết thúc bình thường.

### 4.6. Vì sao ví dụ không tự đọc `System.in` khi console null?

Vì trong service, container hoặc CI, `System.in` có thể là một luồng **mở nhưng không có dữ liệu**, khiến lệnh `readLine()` chờ mãi. Một giải pháp an toàn phải nêu rõ **khi nào được phép block** và ai chịu trách nhiệm cấp input. Chọn `--stdin` giúp caller tự quyết định việc này.

## 5. Những thuộc tính dễ nhầm của standard input

### 5.1. `System.in` có thể đọc được nhưng không nhất thiết là terminal

Ví dụ:

```bash
java ConsoleFallbackDemo --stdin < input.txt
```

`System.in` là file input; không có tác nhân ngồi gõ. Nếu file có một dòng hợp lệ, đọc được dù `System.console()==null`. Khi file rỗng, `readLine()` trả null. Với pipe, thời điểm EOF phụ thuộc tiến trình gửi dữ liệu và việc đóng pipe.

Không dùng câu hỏi “có `System.in` không?” để thay cho yêu cầu giao thức nhập. Chương trình nên biết **nguồn dữ liệu nào là hợp lệ** theo mode, và báo lỗi khi thiếu.

### 5.2. `available()` và `ready()` không phải công tắc phát hiện input

- `System.in.available()` chỉ ước lượng số bytes có thể đọc mà không block tại thời điểm kiểm tra; `0` **không chứng minh** input đã EOF hoặc sẽ không có dữ liệu.
- `BufferedReader.ready()` cho biết có thể đọc mà không block ngay bây giờ; `false` **không có nghĩa** stream bị đóng hoặc không thể có dòng tiếp theo.
- Không dựa vào `System.getenv("TERM")`, tên IDE hay OS để kết luận chắc chắn `System.console()` null/không null.
- Không dùng vòng lặp polling `available()==0` để “chờ người nhập” trong CLI server: vừa không chính xác vừa dễ gây rắc rối hiệu năng.

Muốn không block, thiết kế protocol với timeout/cancellation và nguồn dữ liệu thích hợp; với batch job, giải pháp dễ kiểm soát nhất là **yêu cầu input có sẵn hoặc fail sớm**.

### 5.3. EOF là một trạng thái nghiệp vụ cần xử lý

`BufferedReader.readLine()` trả `null` khi chạm end-of-stream mà chưa nhận ký tự cho dòng. `Console.readLine()` cũng có thể trả `null` khi input kết thúc. Đừng viết:

```java
// Nguy hiểm: có thể NPE khi EOF:
String answer = new BufferedReader(
        new InputStreamReader(System.in)).readLine().trim();
```

Trong vòng lặp đọc nhiều dòng, kiểm tra kết quả trước:

```java
// Mảnh code minh họa trong một method đã có BufferedReader reader:
String line;
while ((line = reader.readLine()) != null) {
    // Xử lý một dòng đã đọc.
}
// Ra khỏi vòng lặp khi EOF; không tiếp tục spin.
```

Vòng lặp này có thể **block** nếu nguồn chưa kết thúc và không gửi dòng; đó là điều hợp lệ với một reader truyền thống. Không dùng nó trong job mà điều kiện thành công đòi hỏi không có bước chờ tương tác.

### 5.4. Charset và Byte Order Mark

`System.in` là bytes; `InputStreamReader` chuyển bytes thành characters theo charset. Trong chương trình minh họa, caller phải cấp **UTF-8**. Nếu producer dùng encoding khác, dấu tiếng Việt và ký tự Unicode có thể bị sai.

Một số tổ hợp shell trên Windows (đặc biệt PowerShell 5.1 khi pipe text cho native process) có thể đưa **UTF-8 BOM** vào đầu stream. Java reader UTF-8 thông thường có thể trả ký tự U+FEFF ở đầu dòng; lúc đó `strip()` **không bảo đảm bỏ BOM**. Triệu chứng là string nhìn giống `"Lan"` nhưng có ký tự ẩn đứng trước.

Giải pháp ưu tiên là **thống nhất encoding/protocol không BOM với producer** và test đầu-cuối, không gắn logic console null với lỗi encoding. Nếu input contract tuyên bố có thể có BOM, parser có thể chủ động nhận diện U+FEFF đầu stream và xử lý theo hợp đồng.

### 5.5. Đọc stdin có thể ảnh hưởng các thành phần khác

`BufferedReader` có buffering; không tạo nhiều wrapper độc lập cùng đọc một `System.in` rồi kỳ vọng mọi thành phần nhận đúng các bytes xen kẽ. Chọn một component sở hữu việc đọc, parse thành giá trị/domain object và truyền tiếp.

Không gọi `Scanner.close()` hoặc `BufferedReader.close()` trên wrapper của `System.in` nếu ứng dụng còn cần dùng luồng toàn cục sau đó. Với file tự mở, ngược lại, **hãy đóng stream** đúng cách.

## 6. Phương án thay thế khác cho dữ liệu thường

### 6.1. Command-line arguments

Thích hợp với batch hoặc script:

```bash
java ConsoleFallbackDemo --name Ada
```

Ưu điểm: không block, dễ lập lịch, dễ kiểm thử. Nhưng CLI arguments có thể xuất hiện trong process inspection, logs hoặc shell history; **không đưa secret vào `--password`, `--token` hoặc các tham số tương tự**.

Nên có parser rõ ràng nếu CLI lớn, thông báo usage, validation, exit code có ý nghĩa và tài liệu hóa giá trị bắt buộc. Không dùng “chế độ mặc định tự hỏi” làm điều kiện để tool chạy đúng trong CI.

### 6.2. Configuration file

Thích hợp với nhiều tham số có cấu trúc và không nhạy cảm, đặc biệt service:

```properties
app.displayName=Lan
app.region=vi-VN
```

Đây là **ví dụ cấu hình dạng properties**, không phải password. Code Java có thể đọc bằng `java.util.Properties` từ file được operator cấp rõ ràng. Quản lý đường dẫn, encoding, quyền truy cập và sự thay đổi cấu hình theo policy deployment. Nếu file chứa secret, cần cơ chế bảo vệ tương ứng; không mặc định plain-text properties an toàn.

### 6.3. Environment variables

Có thể là kênh cấu hình khi chạy container/CI, nhưng env vars cũng có rủi ro: bị kế thừa bởi child process, xuất hiện trong dumps/log hoặc công cụ quản trị tùy nền tảng. Với cấu hình thường, env vars tiện; với secret, ưu tiên kênh quản lý secret chuyên biệt và kiểm soát quyền truy cập.

`System.getenv("APP_DISPLAY_NAME")` có thể được dùng cho cấu hình thường với default rõ ràng. **Không nên lấy tên biến môi trường như `TERM` để suy ra Console API sẽ tồn tại**.

### 6.4. Tầng UI hoặc API thay cho console

Ứng dụng desktop/web không nên đòi người dùng tương tác qua terminal JVM. Hãy nhận giá trị từ UI form, HTTP request hoặc context đã xác thực, rồi gọi cùng business logic. Chương trình có thể sử dụng `Console` như một adapter ở CLI, nhưng logic nghiệp vụ không nên phụ thuộc trực tiếp vào nó.

## 7. Xử lý password và token khi không có console

Đây là **trường hợp bắt buộc phân nhánh với dữ liệu thường**. `Console.readPassword()` được thiết kế để nhập password không echo, trả mảng `char[]` để ứng dụng có thể **xóa vùng nhớ mà nó kiểm soát** sau khi dùng. Ngược lại, nhập bằng `BufferedReader(System.in)` hoặc `Scanner` có thể echo, lưu history, bị thu vào log/pipeline; chuyển secret thành `String` cũng tăng khả năng để lại bản sao trong bộ nhớ khó xóa chủ động.

### 7.1. Khi có console tương tác

Mẫu minh họa Java 17+:

```java
import java.io.Console;
import java.util.Arrays;

Console console = System.console();
if (console == null) {
    throw new IllegalStateException(
            "Secure interactive input unavailable");
}
char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("Password input reached EOF");
}
try {
    // Truyền char[] đến API xác thực thích hợp; không in hoặc log secret.
    // Không chuyển thành String nếu không thật sự cần.
} finally {
    Arrays.fill(password, '\0');
}
```

Đây là **mảnh code cần đặt trong một method/class thích hợp**, không phải chương trình độc lập. Dấu `'\0'` là ký tự null; `Arrays.fill` giảm thời gian giữ secret trong mảng do chương trình kiểm soát, nhưng không phải lời hứa xóa mọi bản sao trong runtime hoặc hệ điều hành.

Không in password bằng `System.out` hay `System.err`, kể cả trong debug. Không vô tình ghi password vào exception message.

### 7.2. Khi `System.console() == null`

**Không tự chuyển sang `Scanner(System.in)` để hỏi password.** Có các lựa chọn thiết kế:

1. **Fail closed:** chương trình CLI yêu cầu console bảo mật thì báo lỗi rằng không có terminal phù hợp, kết thúc với code khác 0 và hướng dẫn dùng đường cấp secret được hỗ trợ.
2. **Secret manager/credential provider:** service lấy secret từ hệ thống quản lý secret đã cấu hình, có identity, quyền truy cập và rotation. Tách việc lấy secret khỏi business logic.
3. **Kênh injected được bảo vệ:** với một số môi trường, operator cấp file descriptor hoặc secret file được bảo vệ/được mount theo chính sách deployment. Cần phân quyền, giới hạn thời gian tồn tại và không log nội dung.
4. **Input không tương tác có hợp đồng bảo mật riêng:** chỉ hỗ trợ nếu ứng dụng/caller đã thiết kế rõ quyền truy cập, đường truyền và vòng đời; không coi mọi stdin pipe là “ẩn nhập” an toàn.

**Không đưa password vào argv** vì có thể lộ qua process listings và history. **Không mặc định env var an toàn tuyệt đối**. Khi công cụ không có kênh secret thích hợp, từ chối thao tác sẽ an toàn hơn đọc secret bằng cơ chế dễ echo.

### 7.3. Mật khẩu không phải tên người dùng

Ví dụ `ConsoleFallbackDemo` chỉ dành cho **tên**, không dành cho secret. Đừng đổi nhãn `--name` thành `--password` rồi giữ nguyên thiết kế. Secret cần contract, transport, redaction và quy trình xử lý khác.

## 8. Tách input khỏi business logic để dễ kiểm thử

Gọi trực tiếp `System.console()` sâu trong code nghiệp vụ gây khó test vì môi trường test không chắc có console. Cách tốt hơn:

```text
CLI input adapter (Console / --stdin / flags)
              |
              v
          Validated value
              |
              v
         Business service
```

Tầng CLI chịu trách nhiệm tương tác và parse; service chỉ nhận giá trị đã được validate. Với library hoặc ứng dụng có nhiều frontend, có thể inject một `Reader`, `InputStream` hoặc abstraction như `InputProvider`, thay vì buộc chúng phụ thuộc vào terminal.

Ví dụ test một reader độc lập, **không dùng global `System.setIn`**:

```java
// Mảnh minh họa Java 17+, đặt trong test/method có imports:
// import java.io.BufferedReader;
// import java.io.StringReader;
BufferedReader fakeInput = new BufferedReader(
        new StringReader("Lan\n"));
String line = fakeInput.readLine(); // "Lan"
```

Trong unit test khác, dùng `new StringReader("")` để mô phỏng EOF. Bạn kiểm soát input bằng một object truyền vào; test không phụ thuộc IDE, terminal thực hoặc việc có ai bấm phím.

### Vì sao hạn chế `System.setIn` trong tests?

`System.setIn(...)` có thể hữu ích trong test rất nhỏ, nhưng nó sửa **global static state** của toàn JVM. Test chạy song song hoặc library khác đang đọc stdin dễ bị ảnh hưởng. Nếu phải dùng, hãy lưu/khôi phục stream cũ trong `finally` và tránh chạy song song; thiết kế inject input thường đơn giản và ổn định hơn.

## 9. Java 25+: `java.lang.IO.readln` là lựa chọn mới, nhưng không thay thế Console bảo mật

Java 25 giới thiệu `java.lang.IO` với `readln()` và `readln(String prompt)` để đọc dòng từ `System.in` và ghi prompt ra `System.out`. Đây là API **còn mới và hiện hành**, có thể hữu ích cho ứng dụng dùng Java 25+ hoặc bài học Java hiện đại:

```java
// Chỉ biên dịch trên JDK 25+ (mảnh code minh họa):
String line = java.lang.IO.readln();
if (line == null) {
    throw new IllegalStateException("No input");
}
```

**Cần phân biệt:**

- `java.lang.IO.readln` dựa trên **standard input**, không cần `System.console()` có giá trị khác null.
- `readln()` vẫn có thể **block** và trả `null` khi EOF; nó không giải quyết tự động bài toán CI không có người nhập.
- Nó không phải cách nhập password không echo. **Không dùng làm fallback bí mật cho `Console.readPassword()`.**
- API này **không có trong Java 17**, vì vậy chương trình mẫu `ConsoleFallbackDemo` dùng `BufferedReader` để tương thích Java 17+.
- Theo Java 26 API, lần gọi `IO.readln` đầu tiên thiết lập bộ giải mã và có thể đọc đệm; không nên trộn các lần gọi `IO.readln` với thao tác khác trên `System.in` vì tài liệu cảnh báo hành vi đọc sau đó không được xác định.
- Nếu dự án đã có abstraction input nhất quán, việc dùng `java.lang.IO` không bắt buộc; đừng trộn nhiều input stacks trong một tiến trình.

Sự xuất hiện của `java.lang.IO` **không khiến `java.io.Console` lỗi thời**: Console vẫn có vai trò với terminal tương tác và nhập password bảo mật. Chọn API tùy phiên bản Java được hỗ trợ và yêu cầu sản phẩm.

## 10. Vận hành trong CI, server và container

### CI/CD

- Yêu cầu tất cả dữ liệu thường qua flags, config hoặc `--stdin` rõ ràng; **không phát prompt** khi job cần chạy unattended.
- Với giá trị bắt buộc thiếu, trả exit code khác 0 cùng message ngắn, không ghi stack trace NPE làm người vận hành khó hiểu.
- Nếu đọc từ pipeline, producer phải được cấu hình kết thúc stream đúng lúc; tránh chờ một dòng không bao giờ đến.
- Giữ message lỗi trên stderr để stdout vẫn có thể dùng như dữ liệu máy đọc được.

### Dịch vụ chạy nền

- Không thiết kế nghiệp vụ “gõ vào console” trong service request handler.
- Config được cấp trong deployment, request hoặc API; secrets đến từ credential provider.
- Nếu có tác vụ cần xác nhận của người vận hành, dùng workflow riêng (UI, approval, queue) thay vì block thread service trên `System.in`.

### Container

- Docker/Kubernetes có thể cấp hoặc không cấp TTY/stdin theo cách chạy. Một container không có console vẫn có thể nhận pipe nếu được cấp rõ ràng, nhưng nhiều deployment không có input để đọc.
- Đừng dùng `-it` như một phương án sửa kiến trúc của batch service; tương tác TTY chỉ phù hợp với chạy thủ công.
- Tránh “detect container” bằng env vars rồi suy ra chắc chắn khả năng đọc. Ưu tiên input contract và error handling thực tế.

### IDE

- Run console của IDE có thể cung cấp luồng `System.in` nhưng không phải `java.io.Console` tương ứng.
- Chế độ `--stdin` cho phép test piped input khi IDE/tooling thực sự cấp dữ liệu; `--name` thuận tiện hơn cho những lần chạy không cần hỏi.
- Nếu developer cần kiểm tra `Console.readPassword()` thực sự, chạy trong terminal tương tác với TTY phù hợp, không ghi password vào test log.

## 11. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `NullPointerException` tại `System.console().readLine()` | Console không có, `System.console()==null`. | Kiểm tra null trước, cấp dữ liệu qua API tương ứng hoặc fail rõ ràng. |
| App đứng im trên CI | Tự gọi `System.in.read()`/`readLine()` dù không ai/không gì cấp dữ liệu. | Chỉ đọc ở mode explicit; nếu input bắt buộc mà thiếu, fail fast. |
| `NoSuchElementException` từ `Scanner.nextLine()` | Input đã EOF, nhưng code không kiểm tra. | Dùng `hasNextLine()` hoặc `BufferedReader.readLine()` và kiểm tra null. |
| `readLine().trim()` gây NPE | EOF trả `null`. | Kiểm tra `null` rồi mới gọi method của String. |
| Bỏ qua sự khác nhau EOF và dòng rỗng | Cả hai bị coi là “không nhập” mà không phân biệt. | `null` là EOF; `""` hoặc whitespace là dòng đã nhận, xử lý theo nghiệp vụ. |
| Có stdin nhưng `System.console()==null` | Standard stream redirected/IDE; không phải thiết bị console. | Dùng `--stdin` rõ ràng với dữ liệu thường. |
| Có Console nhưng không lấy được dòng | Console input kết thúc hoặc người dùng đóng stream. | Xử lý `Console.readLine()==null`, không chỉ check Console object. |
| Password hiển thị trên terminal/log | Tự fallback sang input echo hoặc log raw secret. | Dùng `readPassword()` khi có console; nếu không có, secret provider bảo mật hoặc fail closed. |
| Tên trông giống nhau nhưng compare sai | BOM/encoding mismatch ở đầu stdin. | Chuẩn hóa contract UTF-8, kiểm tra source bytes và BOM. |
| Test phụ thuộc IDE/terminal chạy không ổn định | Gọi console API trực tiếp trong service hoặc test. | Inject Reader/InputProvider, mô phỏng EOF/blank/error. |
| stdout chứa cả prompt lẫn dữ liệu API | Prompt ghi vào stdout trong batch/pipeline. | Không prompt trong `--stdin`, để diagnostic trên stderr. |
| Đọc một dòng mất dữ liệu của thành phần khác | Nhiều BufferedReader/Scanner cùng bọc `System.in`. | Tập trung quyền sở hữu luồng và parsing trong một component. |
| Tự đoán có input nhờ `available()>0` | Chỉ cho biết dữ liệu sẵn ngay tại thời điểm gọi. | Dùng protocol rõ ràng và EOF/timeout hợp lý. |
| Code chỉ chạy trên máy có JDK 25 | Dùng `java.lang.IO` trong project đặt Java 17. | Dùng `BufferedReader` tương thích Java 17, hoặc nâng source target có chủ đích. |

## 12. Checklist thiết kế fallback an toàn

Trước khi triển khai CLI hoặc job:

1. Xác định input bắt buộc là **dữ liệu thường** hay **secret**.
2. Xác định những mode hỗ trợ (`--name`, `--stdin`, console interactive, config, service injection).
3. Chỉ hỏi qua console sau khi kiểm tra `System.console()!=null`.
4. Xử lý `Console.readLine()==null` và `Console.readPassword()==null` như EOF, không NPE.
5. Với stdin, yêu cầu caller opt-in bằng mode explicit nếu không muốn job block bất ngờ.
6. Thống nhất charset (ví dụ UTF-8) giữa producer/consumer và kiểm thử BOM/Unicode khi cần.
7. Phân biệt EOF, dòng rỗng, whitespace, sai định dạng và lỗi I/O.
8. Không đọc secret bằng cơ chế có khả năng echo khi console không hỗ trợ `readPassword`.
9. Không đưa secrets vào command-line arguments, history, logs hoặc exceptions; dùng secret manager/cơ chế bảo vệ được tài liệu hóa.
10. Chọn exit code và ghi diagnostics trên stderr; đầu ra thành công trên stdout.
11. Với service, tách input adapter khỏi nghiệp vụ, tránh block request thread để hỏi terminal.
12. Trong tests, inject Reader hoặc input provider, không dựa vào terminal thực và hạn chế global `System.setIn`.
13. Test có console, không console, console EOF, stdin EOF, stdin blank, stdin hợp lệ, thiếu config và nhiều phiên bản JDK nếu sản phẩm hỗ trợ.
14. Đừng chọn giải pháp dựa vào detection bằng OS/IDE/env; dùng trạng thái API thực tế và contract input rõ ràng.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `System.console()` trả `null` dù `System.in` vẫn tồn tại?

**Đáp án:** `Console` chỉ được cấp khi JVM có thiết bị console tương tác thích hợp; `System.in` là luồng bytes chuẩn, có thể kết nối tới file hoặc pipe mà không có terminal.

**Câu 2.** Nếu console null, luôn dùng `new Scanner(System.in).nextLine()` được không?

**Đáp án:** Không. Với dữ liệu thường và mode stdin có chủ đích, có thể đọc standard input; nhưng stream có thể EOF hoặc block, và với password đó có thể là fallback không an toàn.

**Câu 3.** Khác nhau giữa `readLine()==null` và `readLine().isEmpty()`?

**Đáp án:** `null` là EOF, còn chuỗi rỗng nghĩa là **đã đọc một dòng** không chứa ký tự trước line terminator. Phải kiểm tra null **trước** khi gọi `isEmpty()`.

**Câu 4.** Vì sao chương trình chạy trong JDK 24 có thể nhận Console nhưng `readLine()` trả null?

**Đáp án:** Sự có mặt của Console và sự có mặt của dữ liệu là hai vấn đề riêng. Implementation/môi trường có thể cấp Console nhưng input stream đã EOF; JDK 25 thay đổi default implementation, càng cần xử lý cả hai điều kiện.

**Câu 5.** Có nên đưa `--password abc123` vào lệnh chạy để né console?

**Đáp án:** Không nên. Arguments có thể lộ qua process listing và history. Dùng secret provider/kênh bảo mật theo chính sách hệ thống, hoặc từ chối chạy nếu không có cách nhận secret an toàn.

**Câu 6.** `java.lang.IO.readln()` là thay thế hoàn toàn cho `Console.readPassword()` trong Java 25+?

**Đáp án:** Không. `java.lang.IO.readln` đọc `System.in`, không bảo đảm nhập ẩn, và có thể EOF/block. Nó chỉ là tiện ích cho line-oriented input, không phải primitive lấy secret an toàn.

**Câu 7.** Vì sao một CI job nên fail nhanh thay vì tự đọc stdin khi không có console?

**Đáp án:** stdin có thể không được cấp và không bao giờ có người gõ; chương trình có thể block vô hạn. Contract flags/config/pipe rõ ràng giúp automation deterministic, có thể validate trước.

## 14. Tài liệu Java chính thức còn áp dụng

- [Console — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): điều kiện tồn tại của Console, EOF, `readLine`, `readPassword`, thay đổi hành vi theo môi trường.
- [System — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): `console()`, `in`, `out`, `err` và hợp đồng standard streams.
- [BufferedReader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và EOF.
- [InputStreamReader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): giải mã bytes theo charset.
- [java.lang.IO — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IO.html): `readln` có từ Java 25; lưu ý không trộn với cách đọc `System.in` khác.
- [JDK 25 Release Notes — Oracle](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): default Console implementation thay đổi, không còn JLine-based theo mặc định.
- [Console — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): kiểm tra các API console cơ bản vẫn có trên Java 17.

**Ghi nhớ:** `System.console() == null` là một trạng thái runtime phải xử lý, không phải lý do tự động đọc mọi thứ từ stdin. Với **dữ liệu thường**, dùng flags/config hoặc chế độ pipe `--stdin` được định nghĩa rõ, xử lý EOF/charset và tránh block không dự đoán. Với **secret**, dùng `Console.readPassword` khi thực sự có terminal phù hợp, còn không hãy dùng kênh secret an toàn có thiết kế hoặc fail closed. Thiết kế độc lập với terminal sẽ chạy vững trong IDE, CI, service và những phiên bản Java hiện hành.

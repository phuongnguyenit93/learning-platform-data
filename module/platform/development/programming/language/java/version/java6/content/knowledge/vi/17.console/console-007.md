# Phân biệt ứng dụng terminal với tiến trình được chuyển hướng I/O trong Java

## 1. Tại sao phải phân biệt hai môi trường chạy?

Một ứng dụng dòng lệnh Java có thể được khởi động từ một **terminal tương tác** (người dùng gõ lệnh, đọc thông báo và trả lời prompt), nhưng cũng có thể được chạy bằng **pipeline**, **redirect file**, IDE, CI/CD, scheduler, service hoặc dưới sự quản lý của một tiến trình khác.

Ví dụ cùng một chương trình:

```bash
java IoModes --interactive
java IoModes --batch < input.txt > output.txt 2> errors.txt
cat input.txt | java IoModes --batch | sort
```

Ở tình huống đầu, ứng dụng có thể cần **prompt, chỉnh sửa dòng, nhập mật khẩu không echo**. Ở hai tình huống sau, ứng dụng phải coi **stdin là dữ liệu**, **stdout là kết quả máy khác có thể đọc**, **stderr là chẩn đoán**; nếu in prompt lên stdout hoặc chờ bàn phím khi pipeline đã kết thúc, công cụ có thể treo hoặc phá vỡ dữ liệu.

**Mục tiêu bài học:**

- Phân biệt *terminal*, *Java Console*, *standard streams* và *OS-level redirection*.
- Hiểu chính xác vai trò `System.in`, `System.out`, `System.err` và `System.console()`.
- Biết vì sao **`System.console() != null` không phải một phép kiểm tra terminal đáng tin trên mọi JDK**.
- Sử dụng `Console.isTerminal()` (**có từ Java 22**) khi cần quyết định tính tương tác trên JDK hỗ trợ.
- Thiết kế CLI có chế độ **`--interactive`** và **`--batch`** rõ ràng, không suy đoán nguy hiểm.
- Đọc dữ liệu từ pipe/file, tách data khỏi diagnostics, xử lý EOF và encoding.
- Dùng `ProcessBuilder` để chạy tiến trình con và chủ động chuyển hướng input/output/error mà không phụ thuộc shell.
- Kiểm thử được ví dụ chạy thật trên JDK hiện đại và lưu ý khác biệt giữa những bản JDK.

**Phạm vi hiện hành:** Các API trong bài thuộc Java SE đang được duy trì. Chương trình chính sử dụng **Java 22+** để gọi `Console.isTerminal()`, và đã được biên dịch bằng `javac --release 22`, chạy trên OpenJDK 24. Phần Java 17–21 giải thích cách triển khai khi method mới này chưa có.

## 2. Ba standard streams không phải một terminal

Khi JVM khởi động, môi trường host cung cấp ba luồng I/O chuẩn:

| Java API | Hướng dữ liệu | Vai trò thường dùng | Thực tế có thể nối tới |
| --- | --- | --- | --- |
| `System.in` (`InputStream`) | Vào tiến trình | Dữ liệu đầu vào | Bàn phím, file, pipe, stream của parent process |
| `System.out` (`PrintStream`) | Ra khỏi tiến trình | Dữ liệu/kết quả chính | Terminal, file, pipe, collector logs |
| `System.err` (`PrintStream`) | Ra khỏi tiến trình | Lỗi, warning, progress, diagnostic | Terminal, file khác, pipe khác, collector logs |

`System.in`, `System.out` và `System.err` **không tự chứng minh có người sử dụng terminal**. Cả ba vẫn là Java objects ngay cả khi OS đã thay nơi cấp/nhận bytes.

Ví dụ luồng:

```text
              Interactive terminal
              ┌────────────────┐
user typing ──►│   stdin (fd 0) │
              │                │
display     ◄──│  stdout (fd 1) │
display     ◄──│  stderr (fd 2) │
              └────────────────┘

              Redirected / automated process
              ┌────────────────┐
input.txt  ───►│    System.in   │
output.txt ◄───│    System.out  │
errors.txt ◄───│    System.err  │
              └────────────────┘

              Pipeline
producer stdout ──pipe──► consumer System.in
consumer System.out ──pipe──► next command
consumer System.err ────────► separate diagnostic destination
```

**Terminal** là thiết bị/giao diện I/O tương tác (có thể là terminal emulator hoặc pseudo-terminal). **Console của Java** là một đối tượng `java.io.Console` gắn với JVM khi môi trường triển khai cung cấp. **Standard streams** là các kênh byte I/O được JVM cung cấp. **Shell** là chương trình diễn giải lệnh và có thể nối/redirect các kênh ấy trước khi khởi động Java.

Một tiến trình **được chạy từ cửa sổ terminal** vẫn có thể **không có stdin/stdout nối tới terminal** nếu người dùng áp dụng `<`, `>` hoặc `|`. Vì vậy “mở từ terminal” không đồng nghĩa “đang tương tác”.

### Ví dụ redirection

Trên shell POSIX:

```bash
# Đầu vào lấy từ file; stdout ra file; stderr ra file khác.
java IoModes --batch < input.txt > output.txt 2> errors.txt

# stdout của chương trình A thành stdin của chương trình B.
java IoModes --batch < input.txt | grep '^DATA:'

# Gộp stderr vào stdout; mất tính tách biệt về giao thức.
java IoModes --batch < input.txt > all.log 2>&1
```

`>` thường tạo mới/ghi đè file output; `>>` thường append. `2>` hướng **file descriptor 2** (stderr) tới file. `2>&1` gộp stderr với nơi hiện tại của stdout ở thời điểm shell xử lý redirection; thứ tự các redirect có thể làm kết quả khác.

Các ví dụ này là cú pháp shell POSIX; PowerShell có khác biệt quan trọng về pipeline và encoding, được giải thích ở phần 10.

## 3. `System.console()` trả về gì?

`System.console()` trả **`Console` của JVM nếu có**, hoặc `null` nếu không:

```java
Console console = System.console();
if (console == null) {
    System.err.println("No console available.");
}
```

`Console` cung cấp:

- `readLine(...)`: nhập một dòng, có thể hiện prompt.
- `readPassword(...)`: nhập mật khẩu/passphrase với echoing bị tắt khi được console hỗ trợ.
- `printf(...)`, `format(...)`, `writer()`: xuất text ra console.
- `reader()`: đọc ký tự từ console.
- `charset()`: charset dùng cho **ghi** trên console (từ Java 17).
- `isTerminal()`: cho biết console instance có phải terminal hay không (**từ Java 22**).

**Chú ý:** `Console` không phải một phiên bản khác của `System.out`. Tài liệu mô tả đây là thiết bị console gắn với JVM, có semantics riêng. Không nên dùng `System.setOut(...)` hoặc kiểm tra class của `System.out` để suy ra chắc chắn tình trạng terminal.

### Khác biệt theo phiên bản JDK — điểm rất quan trọng

Quá trình triển khai `Console` đã thay đổi giữa các bản JDK. Cần phân biệt **API contract đang sử dụng** với thói quen từ một JDK cụ thể.

| Phiên bản / hợp đồng | `System.console()` dưới redirection | Cách kiểm tra khuyến nghị |
| --- | --- | --- |
| Java 17–21 (API chưa có `isTerminal`) | Thường `null` khi standard input/output được redirect; phụ thuộc platform/JVM | Không có `Console.isTerminal()`; ưu tiên chọn mode bằng CLI/options và kiểm tra console chỉ để biết tính năng có sẵn |
| Java 22–25, với JLine console provider được đưa vào JDK | **Có thể không `null`** ngay cả khi stdin/stdout bị redirect hoặc nối virtual terminal | Kiểm tra `console != null && console.isTerminal()`, không chỉ `console != null` |
| Oracle Java SE 26 API hiện hành | Javadoc ghi khi stdin/stdout redirect hoặc JVM chạy background thì **không có console**; `isTerminal()` luôn `true` nếu có instance | Vẫn dùng `console != null && console.isTerminal()` để diễn đạt ý định và tương thích theo API |

Nguồn trực tiếp:

- [Oracle Java SE 26 — Console](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): hợp đồng hiện hành về việc có console, `readLine`, `readPassword`, `isTerminal`.
- [Oracle Java SE 22 — Console](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/io/Console.html): `isTerminal` từ Java 22 và cách nó kiểm tra terminal.
- [OpenJDK / Inside Java — JLine is now the Default Console Provider](https://inside.java/2023/07/31/quality-heads-up/): giải thích thay đổi `System.console()` khi redirected và ý nghĩa `isTerminal()` trong JDK 22.
- [Oracle Java SE 26 — System.console()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): trả console hoặc `null`.

**Hệ quả thực tế:** Câu lệnh:

```java
boolean interactive = System.console() != null;
```

**không đủ đáng tin trên nhiều JDK** để bật ANSI escape codes, in prompt hoặc quyết định “người dùng đang ngồi trước bàn phím”. Trên Java 22+, viết rõ hơn:

```java
Console console = System.console();
boolean interactive =
        console != null && console.isTerminal();
```

Đây vẫn là **tín hiệu môi trường hiện tại**, không thay thế việc ứng dụng phải có chính sách `--interactive`/`--batch` và xử lý EOF/timeout. Terminal capability cũng không đồng nghĩa mọi tính năng màu, Unicode, chiều rộng màn hình, mật khẩu hay cursor movement đều được hỗ trợ.

### Ví dụ đã kiểm chứng trên OpenJDK 24

Khi chạy trong một môi trường không có terminal tương tác, kiểm tra bằng Java 24 cho:

```text
consolePresent=true
terminal=false
```

Đây là **quan sát của một môi trường thử nghiệm OpenJDK 24**, không phải stdout bắt buộc trên Windows/Linux, IDE hoặc JDK 26. Nó minh họa chính xác vì sao kiểm tra `console != null` có thể dẫn đến quyết định sai.

## 4. Chọn chế độ hoạt động theo hợp đồng CLI, không đoán

Nên thiết kế hai chế độ có mục đích rõ:

| Chế độ | Input | Output | Khi nào chọn |
| --- | --- | --- | --- |
| `--interactive` | `Console.readLine` / `readPassword` khi có terminal thật | Prompt/trình bày cho người | Người dùng chủ động làm việc tại terminal |
| `--batch` | `System.in` hoặc file/stream được cấu hình | Dữ liệu máy đọc được trên stdout; diagnostic trên stderr | Pipe, redirect file, CI/CD, scheduler, automation |
| `--probe` | Không cần input | Chỉ in thông tin môi trường | Gỡ lỗi sự hiện diện Console/terminal; không dùng làm kết luận tuyệt đối về quyền hạn |

**Quy tắc triển khai khuyến nghị:**

1. **Tôn trọng mode được truyền tường minh.** Có `--batch` thì không in prompt, không chờ người nhập.
2. Với `--interactive`, kiểm tra điều kiện hỗ trợ và **fail fast** nếu không có terminal; hướng dẫn người dùng chuyển sang `--batch`.
3. Nếu muốn tự động chọn mode, chỉ làm khi ứng dụng có chính sách rõ về stdin/stdout, trường hợp `null`/`false` và quyền tương tác. Với hệ thống quan trọng, yêu cầu mode tường minh thường an toàn hơn.
4. Không dùng `System.console() == null` để kết luận **đã được redirect theo một hướng cụ thể**. Nó chỉ nói không có console phù hợp, và có thể do IDE, background task hoặc chính sách JVM.
5. **Không dùng sự tồn tại của Console để quyết định có nên đọc toàn bộ `System.in`**. Input của batch là stream, có thể có/không có dữ liệu, pipe có thể mở lâu và EOF có thể đến muộn.

### Interactive mode cần kiểm tra cả console và terminal

Trong Java 22+:

```java
Console console = System.console();
if (console == null || !console.isTerminal()) {
    System.err.println(
            "Interactive terminal required; use --batch.");
    System.exit(2);
}
String name = console.readLine("Name: ");
if (name == null) {
    // EOF: xử lý thay vì dereference null.
}
```

Đoạn này là **minh họa chưa độc lập**; phần 7 có chương trình đầy đủ. `Console.readLine` có thể trả `null` tại EOF. Việc không có terminal không nên được xử lý bằng cách âm thầm hỏi qua `System.in` trong pipeline vì có thể tiêu thụ dữ liệu mà một chương trình khác đang định truyền.

## 5. Đọc dữ liệu redirected bằng `System.in`

Một ứng dụng batch thường nhận input qua `System.in` và một `Reader` phù hợp:

```java
String encoding = System.getProperty("stdin.encoding");
Charset charset = encoding == null
        ? StandardCharsets.UTF_8
        : Charset.forName(encoding);

BufferedReader input = new BufferedReader(
        new InputStreamReader(System.in, charset));

for (String line; (line = input.readLine()) != null;) {
    // Xử lý từng dòng input.
}
```

Mã trên **không phải ứng dụng độc lập**; dùng imports `BufferedReader`, `InputStreamReader`, `Charset`, `StandardCharsets`. `System.in` là **byte stream**, nên phải biết cách chuyển bytes sang text. `stdin.encoding` là system property hữu ích trên JDK hiện hành; với dữ liệu file có hợp đồng cố định, **định nghĩa UTF-8 ở hai đầu** thường rõ ràng hơn việc phụ thuộc encoding của terminal/shell.

**Phân biệt ba trạng thái:**

- `readLine()` trả chuỗi **rỗng `""`**: có một dòng trống trong input.
- `readLine()` trả chuỗi chỉ gồm khoảng trắng: có dòng nhưng có thể bị coi là blank theo nghiệp vụ; `String.isBlank()` từ Java 11 giúp kiểm tra.
- `readLine()` trả **`null`**: **EOF** — input stream đã kết thúc. Nếu pipe writer còn mở và chưa có dòng đầy đủ, thao tác đọc có thể **block**, không nhất thiết trả `null`.

Không dùng:

```java
while (true) {
    String line = reader.readLine();
    // Quên xử lý null => có thể loop sai hoặc ném lỗi.
}
```

Thay bằng điều kiện dừng ở EOF như ví dụ đúng ở trên.

### Lưu ý về đóng `System.in`

`System.in` là tài nguyên chuẩn thường do JVM/host cấp. Một CLI ngắn có thể để nó tự kết thúc cùng tiến trình; nếu viết thư viện hoặc một hệ thống chia sẻ `System.in`, **đóng wrapper `BufferedReader` cũng đóng `System.in`**, có thể ảnh hưởng các thành phần khác. Đừng sử dụng nhiều Reader/Scanner đồng thời trên cùng `System.in`: buffering có thể khiến các thành phần đọc mất dữ liệu của nhau.

Với file input do **ứng dụng tự mở**, nên dùng `try-with-resources` để đóng. Với global standard streams, xác định ownership trước khi quyết định đóng.

## 6. Stdout dành cho dữ liệu; stderr dành cho diagnostics

CLI dễ tự động hóa nên có một quy ước:

- `System.out`: dữ liệu/sản phẩm chính. Ví dụ dòng bắt đầu `DATA:` mà lệnh tiếp theo có thể parse được.
- `System.err`: thông tin tiến độ, cảnh báo, số dòng xử lý, thông báo lỗi và hướng dẫn cách dùng.
- **Exit code:** 0 cho thành công; khác 0 cho lỗi hoặc yêu cầu không thể thực hiện. Các con số 2, 3, 64 ở ví dụ là **quy ước của chương trình**, không phải giá trị Java bắt buộc.
- **Prompt:** chỉ xuất trong mode tương tác. Tránh đưa prompt vào stdout của mode batch vì script sẽ coi prompt là bản ghi dữ liệu.

Ví dụ output khi xử lý hai bản ghi:

```text
stdout:
DATA:ALPHA
DATA:BETA

stderr:
processed=2,blank=1
```

Nếu stdout được redirect tới file, stderr thường vẫn có thể hiển thị ở terminal, nhưng nó cũng có thể bị redirect hoặc bị host thu thập riêng. Không giả định `System.err` luôn được người dùng nhìn thấy lập tức.

### Khi các streams bị gộp

Nếu chạy:

```bash
java IoModes --batch < input.txt > all.log 2>&1
```

thì **stdout và stderr đi chung một destination**. Đây là quyết định của người chạy hoặc parent process, không phải thay đổi trong Java code. Ứng dụng vẫn có thể dùng hai streams tách biệt về mặt logic, nhưng parser đọc `all.log` phải biết nó đã bị trộn.

`PrintStream` như `System.out` có hành vi ghi nhận I/O errors khác `Writer` thường: một số lỗi ghi không tự ném checked exception qua `println`; nếu công cụ cần phản hồi chính xác với pipe bị đóng hoặc ổ đĩa đầy, thiết kế policy kiểm tra `checkError()`, flush và logging/exit code thay vì mặc định in ra là thành công.

## 7. Chương trình Java 22+ đầy đủ: `IoModes.java`

File này có ba mode:

- `--probe`: báo cáo sự hiện diện của Java Console và kết quả `Console.isTerminal()`.
- `--batch`: đọc stdin tới EOF, bỏ dòng trắng, in uppercase records vào stdout và tổng kết vào stderr.
- `--interactive`: chỉ prompt nếu có terminal thực sự; từ chối trong CI/pipe không tương tác.

### 7.1. Nguồn `IoModes.java`

```java
import java.io.BufferedReader;
import java.io.Console;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class IoModes {
    private static Charset inputCharset() {
        String name = System.getProperty("stdin.encoding");
        return name == null ? StandardCharsets.UTF_8
                : Charset.forName(name);
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                    "usage: IoModes --probe|--batch|--interactive");
            System.exit(64);
        }

        switch (args[0]) {
            case "--probe" -> {
                Console console = System.console();
                System.out.println(
                        "consolePresent=" + (console != null));
                System.out.println(
                        "terminal=" + (console != null
                                && console.isTerminal()));
            }
            case "--batch" -> {
                BufferedReader input = new BufferedReader(
                        new InputStreamReader(
                                System.in, inputCharset()));
                int processed = 0;
                int blank = 0;

                for (String line;
                        (line = input.readLine()) != null;) {
                    if (line.isBlank()) {
                        blank++;
                        continue;
                    }
                    System.out.println("DATA:"
                            + line.strip().toUpperCase(Locale.ROOT));
                    processed++;
                }

                System.err.println(
                        "processed=" + processed + ",blank=" + blank);
            }
            case "--interactive" -> {
                Console console = System.console();
                if (console == null || !console.isTerminal()) {
                    System.err.println(
                            "Interactive terminal required; use --batch.");
                    System.exit(2);
                    return;
                }

                String name = console.readLine("Name: ");
                if (name == null) {
                    System.err.println("No input.");
                    System.exit(3);
                    return;
                }
                console.printf("Hello, %s%n", name);
            }
            default -> {
                System.err.println(
                        "usage: IoModes --probe|--batch|--interactive");
                System.exit(64);
            }
        }
    }
}
```

**Tương thích phiên bản:** `Console.isTerminal()` được thêm từ **Java 22**, vì vậy compile:

```bash
javac --release 22 IoModes.java
```

Cần **JDK 22 hoặc mới hơn** khi biên dịch/chạy đúng chương trình này. Java 17 không có method đó; giải pháp Java 17–21 được trình bày ở phần 13, không dùng các lệnh của đoạn này trên JDK 17 mà kỳ vọng thành công.

### 7.2. Chạy thử trong terminal

```bash
java IoModes --probe
java IoModes --interactive
```

Đầu ra `--probe` **phụ thuộc môi trường**. Trên một terminal tương tác thực sự có thể thấy:

```text
consolePresent=true
terminal=true
```

Nếu không có console, có thể thấy:

```text
consolePresent=false
terminal=false
```

Nhưng **JDK 22–25 có thể trả Console non-null dù không phải terminal**, nên còn một trường hợp hợp lệ:

```text
consolePresent=true
terminal=false
```

Đây chính là kết quả đã quan sát trong môi trường kiểm thử OpenJDK 24. Các ví dụ trên là **những khả năng**, không phải một stdout cố định cho mọi máy.

`--interactive` chỉ nên chạy trong terminal khi người dùng tự nguyện nhập dữ liệu; nó in `Name:` và sau đó có thể in `Hello, Alice` nếu bạn gõ `Alice`. Không dùng input thật của người dùng để viết golden test có stdout cứng.

### 7.3. Chạy trong batch/pipeline

Tạo file `input.txt` (UTF-8) có nội dung:

```text
alpha

 beta 
```

Sau đó trên Linux/macOS:

```bash
java IoModes --batch < input.txt > output.txt 2> errors.txt
cat output.txt
cat errors.txt
```

Kết quả nội dung file `output.txt`:

```text
DATA:ALPHA
DATA:BETA
```

Nội dung file `errors.txt`:

```text
processed=2,blank=1
```

`line.strip()` bỏ whitespace hai đầu; `toUpperCase(Locale.ROOT)` giúp kết quả không phụ thuộc locale mặc định của máy; `line.isBlank()` nhận ra dòng trống. Không in message nào lên stdout ngoài data records trong `--batch`.

Nếu input rỗng và stdin đến EOF ngay, kết quả hợp lệ là **stdout không có dòng DATA**, còn stderr ghi `processed=0,blank=0`. Nếu stdin là một pipe còn mở mà producer chưa gửi EOF, consumer có thể chờ thêm dữ liệu; đây không phải chứng cứ có terminal.

## 8. Kiểm thử redirection chính xác bằng `ProcessBuilder`

Khác với chạy qua shell, `java.lang.ProcessBuilder` cho Java cha **tự cấu hình** stdin/stdout/stderr của tiến trình con. Điều này hữu ích để test CI ổn định, tránh sự khác nhau giữa Bash, PowerShell 5.1 và PowerShell 7 về encoding hoặc cách truyền text pipeline.

### 8.1. Các redirect trong ProcessBuilder

| Lệnh | Tác dụng |
| --- | --- |
| `redirectInput(file)` | Đưa nội dung file làm **stdin của child**. |
| `redirectOutput(file)` | Ghi **stdout của child** vào file. |
| `redirectError(file)` | Ghi **stderr của child** vào file riêng. |
| `inheritIO()` | Cho child **kế thừa** stdin/out/err hiện tại của parent. |
| `redirectErrorStream(true)` | Gộp stderr của child vào stdout của child. |
| `ProcessBuilder.Redirect.PIPE` | Kết nối stream của child tới parent qua pipe (mặc định). |
| `ProcessBuilder.Redirect.INHERIT` | Dùng kênh standard stream đã có của parent. |

`inheritIO()` **không tự tạo terminal**. Nếu I/O của parent là pipeline/file, child kế thừa kênh ấy, không đột nhiên biến thành ứng dụng terminal tương tác.

Với redirect sang file, các stream tương ứng trên `Process` phía parent có thể là **null streams** theo hợp đồng API (ví dụ `Process.getInputStream()` đọc `-1` khi stdout child đã được redirect sang file). Đừng vừa redirect output sang file vừa mong đọc lại toàn bộ stdout child qua `Process.getInputStream()`. Hãy đọc file nếu chọn redirect file.

### 8.2. File thứ hai: `RunRedirected.java`

Lưu bên cạnh `IoModes.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Locale;
import java.util.stream.Stream;

public final class RunRedirected {
    private static String javaBinary() {
        String exe = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win")
                ? "java.exe" : "java";
        return Path.of(
                System.getProperty("java.home"), "bin", exe).toString();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-redirect-test-");

        try {
            Path input = dir.resolve("input.txt");
            Path out = dir.resolve("stdout.txt");
            Path err = dir.resolve("stderr.txt");

            Files.writeString(
                    input, "alpha\n\n beta \n", StandardCharsets.UTF_8);

            Process child = new ProcessBuilder(
                    javaBinary(),
                    "-cp", System.getProperty("java.class.path"),
                    "IoModes", "--batch")
                    .redirectInput(input.toFile())
                    .redirectOutput(out.toFile())
                    .redirectError(err.toFile())
                    .start();

            int exit = child.waitFor();
            String stdout = Files.readString(
                    out, StandardCharsets.UTF_8);
            String stderr = Files.readString(
                    err, StandardCharsets.UTF_8);

            System.out.println("exit=" + exit);
            System.out.println("stdoutLines="
                    + stdout.lines()
                            .reduce((a, b) -> a + "|" + b)
                            .orElse(""));
            System.out.println(
                    "stderrLine=" + stderr.strip());
        } finally {
            try (Stream<Path> files = Files.walk(dir)) {
                for (Path p : files
                        .sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

Chương trình sử dụng `ProcessBuilder` với **một danh sách arguments**, không khởi chạy shell, vì vậy không cần escape `<`, `>` hoặc `|` theo OS. Nó sinh file đầu vào có **UTF-8 không BOM**, thiết lập redirection, chờ child kết thúc, rồi đọc các file output. Cuối cùng nó dọn file tạm.

`RunRedirected.java` riêng lẻ sử dụng APIs chạy được trên Java 17+, nhưng vì nó khởi chạy **`IoModes` phiên bản Java 22+**, cần JDK 22+ để chạy đầy đủ cả hai file như demo này.

### 8.3. Biên dịch và kiểm thử

Từ thư mục chứa hai file:

```bash
javac --release 22 IoModes.java RunRedirected.java
java RunRedirected
```

**Stdout xác thực:**

```text
exit=0
stdoutLines=DATA:ALPHA|DATA:BETA
stderrLine=processed=2,blank=1
```

Kết quả trên đã được kiểm thử với **OpenJDK 24**, chạy `javac --release 22`. Đây là **output ổn định của fixture** vì input chỉ là ASCII, file được ghi bằng Java UTF-8, ProcessBuilder chuyển hướng từng stream trực tiếp, và program in đúng định dạng đã thiết kế.

Việc stdout và stderr được thu vào hai file khác nhau giúp test assert chính xác “data không bị trộn với diagnostics”. Nếu đổi `redirectErrorStream(true)`, quy tắc đọc stderr/output sẽ khác; đừng giữ nguyên expected stdout của fixture khi đã gộp streams.

### 8.4. Tại sao không dùng shell cho test byte-exact?

POSIX `<`, `>` và `|` thường thao tác trên byte streams. Trong **Windows PowerShell 5.1**, pipeline các command có thể chuyển output qua đối tượng chuỗi và encoding trung gian, dẫn tới BOM hoặc encoding khác với bytes gốc. PowerShell phiên bản mới có một số cải tiến, nhưng script chạy đa phiên bản không nên dựa vào giả định đồng nhất.

Vì vậy, nếu muốn kiểm tra output **chính xác từng byte** trong CI, ưu tiên:

- Dùng `Files.writeString(..., StandardCharsets.UTF_8)` tạo fixture.
- Dùng `ProcessBuilder.redirectInput/redirectOutput/redirectError` để truyền file bytes.
- Đọc lại bằng charset đã xác định.
- So sánh nội dung/exit code và kiểm tra dọn tài nguyên.

Với demo dùng ASCII, các lệnh shell vẫn phù hợp cho việc học thông thường, nhưng không nên đồng nhất “nội dung text nhìn giống nhau” với “byte encoding hoàn toàn giống nhau”.

## 9. Khi parent dùng PIPE thay vì redirect file

`ProcessBuilder` mặc định dùng `Redirect.PIPE` cho stdin/stdout/stderr của subprocess. Khi đó:

- `child.getOutputStream()` từ parent **ghi vào stdin child**.
- `child.getInputStream()` từ parent **đọc stdout child**.
- `child.getErrorStream()` từ parent **đọc stderr child**.

Tên các accessor có vẻ đảo chiều nếu nhìn từ phía child, vì chúng được đặt theo góc nhìn **parent process**: OutputStream để parent gửi input cho child, InputStreams để parent nhận output.

Ví dụ hướng dẫn, **không phải chương trình standalone**:

```java
Process child = new ProcessBuilder(
        "java", "IoModes", "--batch").start();

// Parent viết dữ liệu vào stdin của child.
try (var childInput = child.getOutputStream()) {
    childInput.write("alpha\n".getBytes(StandardCharsets.UTF_8));
}
// Việc đóng childInput báo EOF cho child.
```

Nếu không đóng `child.getOutputStream()`, child đang đọc tới EOF có thể **chờ mãi**.

**Deadlock khi không tiêu thụ output:** OS pipes có dung lượng buffer giới hạn. Nếu child liên tục ghi nhiều dữ liệu vào stdout/stderr mà parent chỉ gọi `child.waitFor()`, buffer có thể đầy, child không ghi tiếp được và parent cũng đang chờ child kết thúc. Để tránh:

1. Đọc stdout **và** stderr kịp thời, thường qua những consumer tasks khác nhau; hoặc
2. Chủ động redirect chúng ra files bằng `ProcessBuilder`; hoặc
3. `redirectErrorStream(true)` để trộn streams nếu giao thức output chấp nhận, và vẫn tiêu thụ output đó.

Không gọi `readAllBytes()` một cách vô hạn với child tạo log lớn mà không có giới hạn bộ nhớ. Khi cần timeout, dùng `Process.waitFor(timeout, TimeUnit)`, xử lý timeout/terminate theo policy và bảo đảm đóng streams.

## 10. Shell examples theo hệ điều hành

### Linux/macOS, Bash/Zsh

```bash
# Đọc từ file, ghi data và diagnostics riêng:
java IoModes --batch < input.txt > output.txt 2> errors.txt

# Dữ liệu từ chương trình khác:
printf 'alpha\n\n beta \n' | java IoModes --batch

# Pipe stdout của Java sang một chương trình tiếp theo:
java IoModes --batch < input.txt | grep 'DATA:'

# Chạy probe trong terminal hoặc qua pipe:
java IoModes --probe
java IoModes --probe | cat

# Trộn cả hai channels vào cùng file khi chủ ý:
java IoModes --batch < input.txt > all.log 2>&1
```

Không nên giả định hai lệnh `--probe` cuối luôn trả cùng `consolePresent`. Chính việc gắn stdin/stdout vào pipe và phiên bản Console provider có thể thay kết quả.

### Windows PowerShell

```powershell
# Có thể chạy probe trong PowerShell:
java IoModes --probe

# Chạy batch nhận text từ pipeline:
Get-Content -Path .\input.txt | java IoModes --batch

# Redirect stdout và stderr bằng cú pháp PowerShell:
Get-Content -Path .\input.txt |
    java IoModes --batch 1> .\output.txt 2> .\errors.txt

# Gửi output cho lệnh tiếp theo:
Get-Content -Path .\input.txt | java IoModes --batch |
    Select-String '^DATA:'
```

**Cảnh báo:** PowerShell 5.1 và PowerShell 7 có thể xử lý encoding và stdout/stderr từ native commands khác nhau; đặc biệt, pipeline text từ `Get-Content` không phải cách bảo đảm giữ nguyên **bytes gốc** của file. Đối với test binary-safe, dùng `ProcessBuilder` theo phần 8 hoặc công cụ đọc/ghi bytes có hợp đồng rõ.

Trong PowerShell 5.1, cú pháp POSIX `< input.txt` **không** là redirection đầu vào tương đương Bash. Đừng sao chép nguyên dòng `java ... < input.txt` sang PowerShell rồi nghĩ nó chắc chắn hoạt động. `Get-Content | java` là lựa chọn cho dữ liệu text; `ProcessBuilder.redirectInput` là lựa chọn có thể kiểm thử chặt chẽ.

## 11. Password và input nhạy cảm

Đối với mật khẩu, một ứng dụng terminal tương tác không nên dùng:

```java
System.out.print("Password: ");
String password = new Scanner(System.in).nextLine();
```

Dù đoạn này có thể đọc chữ, nó thường để ký tự mật khẩu **hiện trên màn hình**, tồn tại trong `String` và có thể bị log hoặc capture. Tốt hơn là dùng `Console.readPassword(...)` nếu console thực sự hỗ trợ:

```java
Console console = System.console();
if (console == null || !console.isTerminal()) {
    throw new IllegalStateException(
            "Interactive terminal required for password input");
}

char[] password = console.readPassword("Password: ");
if (password == null) {
    throw new IllegalStateException("End of input");
}

try {
    // Gửi password đến cơ chế xác thực phù hợp,
    // không log và không chuyển sang String nếu có thể tránh.
} finally {
    java.util.Arrays.fill(password, '\0');
}
```

Đây là **đoạn minh họa tích hợp**, yêu cầu JDK 22+ để gọi `isTerminal` và import `Console`. Mảng `char[]` có thể được xóa thủ công sau khi dùng; `String` immutable không thể được xóa nội dung một cách tương tự.

**Không tự động fallback sang `System.in` để nhận secret từ pipe** trừ khi hệ thống có một giao thức bí mật được thiết kế rõ ràng và người vận hành chủ động bật nó; pipeline/stdout/CI logs có nguy cơ làm lộ bí mật. Hệ thống sản xuất thường dùng secret manager, environment/OS facilities có chính sách phù hợp, file descriptor riêng hoặc cơ chế credential injection đã được bảo vệ; không in secret trong process arguments/logs.

`Console.readPassword` tắt echoing theo contract, nhưng **không bảo đảm bảo mật của toàn bộ thiết bị/host**. Quản lý nguồn secret, transport, memory lifetime và chính sách ghi log vẫn cần thiết.

## 12. Charset, buffering và line endings

### 12.1. Không giả định charset mặc định luôn phù hợp

`System.in` là bytes. `InputStreamReader` phải decode theo charset mà producer dùng. Java runtime hiện đại có các property hữu ích:

- `stdin.encoding`: encoding của standard input do host/runtime chỉ định.
- `stdout.encoding`: encoding dùng cho standard output.
- `stderr.encoding`: encoding dùng cho standard error.

`Console.charset()` (từ Java 17) trả charset dùng cho **console write operations** trong hợp đồng hiện hành; không mặc định tất cả stdin, stdout, stderr và file/pipe đều dùng đúng cùng charset.

Trong chương trình, `inputCharset()` dùng `System.getProperty("stdin.encoding")`, fallback UTF-8 nếu property vắng mặt. Đó là chính sách của **demo**, không phải định nghĩa rằng mọi nguồn redirected đều UTF-8.

Với giao thức file/pipe được hai bên kiểm soát, **ghi rõ charset trong contract**. Ví dụ `RunRedirected` tạo file UTF-8 bằng `Files.writeString(..., UTF_8)` và chỉ dùng dữ liệu ASCII để test độc lập với code page.

### 12.2. Newline và EOF

`BufferedReader.readLine()` nhận `\n`, `\r` hoặc `\r\n` làm line terminators; text trả về không gồm các ký tự kết thúc dòng. Nó trả `null` ở EOF. Đừng suy ra có EOF chỉ vì gặp một blank line.

`System.out.println` tạo line separator theo môi trường, thường `\n` trên Unix và `\r\n` trên Windows. Khi test nội dung text, phương thức `String.lines()` giúp lấy logical lines mà không giả định line endings là byte-identical.

Nếu giao thức đòi định dạng byte cụ thể (chẳng hạn JSON Lines UTF-8 với LF), cân nhắc dùng `OutputStreamWriter` với `StandardCharsets.UTF_8` và ghi `'\n'` tường minh, cũng như kiểm soát flush/close theo ownership.

### 12.3. Prompt không nên dùng stdout trong batch

Việc in `"Enter value: "` vào stdout rồi chuyển stdout sang pipeline sẽ tạo ra một dòng bất ngờ ở đầu dữ liệu. Chế độ interactive nên dùng `Console.readLine("Prompt: ")`; chế độ batch **không có prompt** và phải dựa trên một input format rõ ràng.

## 13. Nếu phải hỗ trợ Java 17–21

`Console.isTerminal()` chỉ được bổ sung ở **Java 22**. Để xây ứng dụng chạy JDK 17–21, bạn vẫn dùng được:

```java
Console console = System.console();

if (console == null) {
    // Không có Console API tương tác phù hợp.
} else {
    // Có Console; nhưng đừng biến presence
    // thành một phép kiểm tra TTY đa phiên bản tuyệt đối.
}
```

Phương án **dễ kiểm chứng nhất** cho CLI đa JDK là có **`--interactive` và `--batch` tường minh**. `--batch` luôn đọc `System.in` và ghi data ra `System.out`, không phụ thuộc `Console`; `--interactive` chỉ dùng `Console` khi tồn tại và yêu cầu người dùng chịu trách nhiệm chạy ở môi trường phù hợp. Nếu ứng dụng **bắt buộc** phát hiện TTY đáng tin trên JDK cũ, cần giải pháp có hợp đồng theo platform/runtime hoặc thư viện chuyên dụng, thay vì tự suy đoán mọi môi trường từ `console != null`.

Không nên dùng reflection phức tạp chỉ để cố gọi một method chưa có nếu mục tiêu đơn giản là xử lý stdin và stdout trong batch. Nếu nâng minimum JDK lên 22+, `isTerminal()` là cách trực tiếp, rõ ràng hơn.

**Quan trọng:** đoạn `IoModes.java` ở phần 7 không compile với `--release 17`, vì chứa `Console.isTerminal()`. `RunRedirected` có thể dùng riêng trên Java 17+, nhưng để chạy đúng **fixture hai file** trong bài phải dùng JDK 22+.

## 14. Bảng quyết định theo từng môi trường

| Môi trường | Std streams thường thế nào? | Console/terminal | Quyết định CLI nên làm |
| --- | --- | --- | --- |
| Terminal cục bộ tương tác | In/out/err thường nối terminal | Thường có terminal nếu JVM/host hỗ trợ | Cho phép `--interactive` sau kiểm tra; `--batch` vẫn có thể dùng |
| SSH interactive có pseudo-terminal | I/O qua PTY | Có thể được xem như terminal thật theo API | Dùng kiểm tra terminal, nhưng vẫn xử lý resize/encoding và đóng kết nối |
| SSH không có PTY | Stream/pipe | Thường không phải terminal | Batch, không prompt |
| `java App < file` | stdin từ file | Tùy JDK/host; không giả định console có mặt | `--batch`, đọc tới EOF |
| `java App > file` | stdout ra file | Tùy JDK/host | Không in prompt vào data output |
| `producer | java App` | stdin từ pipe | Có thể có Console object nhưng không có terminal ở JDK 22–25 | `--batch`, đọc protocol |
| IDE Run console | Stream do IDE quản lý | Thường không phải OS terminal, dù hiển thị console UI | Dùng mode tường minh, không dựa `console != null` |
| CI/CD, scheduler, service | Pipes/files/log collector | Thường noninteractive | Mặc định batch hoặc cấu hình rõ, không chờ prompt |
| ProcessBuilder mặc định | stdin/stdout/stderr dùng PIPE | Không có terminal được tạo chỉ bởi builder | Parent phải ghi input, đọc output/err, đóng input stream |
| `ProcessBuilder.inheritIO()` | Kế thừa streams của parent | Chỉ là terminal nếu parent thực sự có terminal | Không giả định interactive chỉ vì `inheritIO()` |
| `redirectErrorStream(true)` | Stderr nhập vào stdout child | Không ảnh hưởng bản chất terminal | Parser cần biết hai luồng dữ liệu đã bị trộn |

Đây là **những hành vi thường gặp**, không phải bảo đảm tuyệt đối về mọi shell, container, pseudo-terminal, JDK provider hoặc hệ điều hành. Khi cần bảo đảm dữ liệu, hãy thiết kế protocol và thực hiện test ở môi trường triển khai.

## 15. Kiểm thử tự động và checklist QA

### 15.1. Các tình huống cần test

| Case | Cách chạy | Assertion |
| --- | --- | --- |
| Batch có 2 dòng hợp lệ, 1 dòng trống | `RunRedirected` | Exit 0, stdout hai dòng DATA, stderr tổng kết đúng |
| Empty input | Redirect file rỗng tới `--batch` | Không có DATA, `processed=0,blank=0` |
| Input có whitespace | `" beta "` | `DATA:BETA` |
| Console probe trong terminal | `--probe` | Trả hai cờ kiểu boolean; không hard-code theo máy |
| Console probe trong CI/pipe | `--probe` | `terminal=false` theo môi trường không terminal; `consolePresent` tùy JDK |
| Interactive không có TTY | `--interactive` | Không prompt, stderr báo cần terminal, exit khác 0 |
| EOF khi prompt | Có terminal nhưng input kết thúc | Xử lý `readLine == null`, không NPE |
| Redirect stdout và stderr riêng | `ProcessBuilder.redirectOutput/redirectError` | File data không chứa diagnostics |
| Gộp stderr vào stdout | `redirectErrorStream(true)` hoặc shell | Output gộp theo chủ đích; test parser phù hợp |
| Child không kết thúc vì stdin chưa đóng | ProcessBuilder.PIPE | Parent đóng `getOutputStream` đúng lúc và timeout khi cần |
| Charset khác UTF-8 | Input bytes có Unicode | Có cấu hình đúng để decode, không mặc định ổn với mọi shell |
| No console trong IDE | Chạy qua IDE/CI | Ứng dụng xử lý batch hoặc fail fast, không treo prompt |

### 15.2. Golden output của fixture

Với hai file `IoModes.java` và `RunRedirected.java` được compile bằng `javac --release 22`:

```text
exit=0
stdoutLines=DATA:ALPHA|DATA:BETA
stderrLine=processed=2,blank=1
```

Đây là **kết quả kiểm chứng của fixture**, không chứa dòng `consolePresent` vì giá trị của nó phụ thuộc JDK và môi trường. Tách test môi trường khỏi test xử lý dữ liệu giúp CI ổn định.

### 15.3. Checklist cho CLI production

1. Tuyên bố rõ mode `--interactive`/`--batch` và chính sách mặc định.
2. Với mode interactive, kiểm tra Console/terminal API theo minimum JDK thực tế.
3. Với mode batch, không prompt; đọc stdin theo schema có định nghĩa và dừng đúng EOF.
4. Chỉ ghi sản phẩm lên stdout; diagnostics lên stderr; đặt exit code có ý nghĩa.
5. Ghi rõ charset của input/output, không đoán theo shell trong CI.
6. Không dùng `System.console() != null` làm TTY test chung cho mọi JDK.
7. Không trộn `Console.reader()` và `System.in` để đọc cùng một dữ liệu tùy tiện.
8. Khi chạy child qua ProcessBuilder, biết chính xác pipe nào phải đọc/ghi/đóng; tránh deadlock.
9. Test redirect file, pipeline, no-TTY, EOF, empty input, broken pipe và output lớn.
10. Với password, sử dụng `readPassword` và xóa `char[]`, không log secrets hoặc tự fallback không an toàn.

## 16. Các lỗi phổ biến

**Lỗi 1 — Đồng nhất `System.console() != null` với “người dùng đang ngồi tại terminal”.**  
Không đúng trên mọi phiên bản JDK; đặc biệt JDK 22–25 có thể có Console không phải terminal. Dùng `isTerminal` trên Java 22+ khi có.

**Lỗi 2 — Cho rằng `System.console() == null` nghĩa “stdin bị redirect từ file”.**  
Không nhất thiết. IDE, CI, background scheduler hoặc host không có console đều có thể dẫn đến trạng thái này.

**Lỗi 3 — Gọi `readLine` mà không kiểm tra Console null.**  
Gây `NullPointerException` trong môi trường không có console. Kiểm tra capability trước.

**Lỗi 4 — Prompt trong batch mode.**  
Có thể chờ vô hạn, tiêu thụ input data như câu trả lời, hoặc làm hỏng stdout dành cho parser.

**Lỗi 5 — Chỉ đọc stdout của child, không đọc stderr.**  
Stderr pipe có thể đầy làm child block. Đọc đồng thời hoặc redirect riêng ra file.

**Lỗi 6 — Parent không đóng `child.getOutputStream()` sau khi gửi input.**  
Child đang đọc tới EOF có thể chờ mãi. Đóng để báo input đã kết thúc.

**Lỗi 7 — Dùng `ProcessBuilder.inheritIO()` rồi tin rằng child sẽ có terminal.**  
`inheritIO` kế thừa **chính các kênh parent đang có**, kể cả file/pipe.

**Lỗi 8 — Nhầm `Process.getInputStream()` với stdin của child.**  
Tên accessor theo góc nhìn parent: `getInputStream()` đọc **stdout child**; `getOutputStream()` viết vào **stdin child**.

**Lỗi 9 — Đọc line rỗng như EOF.**  
`readLine() == null` mới là EOF. Chuỗi `""` chỉ là một dòng trống.

**Lỗi 10 — Không xác định charset trong pipeline.**  
Text bị hỏng hoặc BOM xuất hiện khi shell/encoding khác nhau. Dùng contract charset và byte-safe test.

**Lỗi 11 — Ghi diagnostics vào stdout.**  
Làm hỏng NDJSON/CSV/line protocol. Dùng stderr cho diagnostic khi giao thức yêu cầu stdout sạch.

**Lỗi 12 — Đọc password bằng `Scanner(System.in)` mà không quản lý echo.**  
Có thể lộ secret. Dùng `Console.readPassword` khi có terminal hoặc kênh credential injection được thiết kế an toàn.

**Lỗi 13 — Quên xóa buffer secret.**  
Với `char[]` từ `readPassword`, dùng `Arrays.fill` trong `finally` khi có thể.

**Lỗi 14 — Compile `Console.isTerminal()` trên Java 17.**  
Method được bổ sung ở Java 22, nên `javac --release 17` không thể compile code gọi nó. Nâng target hoặc thiết kế mode tường minh mà không phụ thuộc method.

**Lỗi 15 — Tin rằng một lời gọi `println` luôn thành công.**  
`PrintStream` có error state; nếu output bị đóng hoặc full, cần xét `checkError` và policy xử lý lỗi thay vì giả định không thể thất bại.

**Lỗi 16 — Coi terminal là một phép kiểm tra bảo mật.**  
TTY detection là dữ liệu về I/O của môi trường, không phải xác thực người dùng, quyền truy cập, hay chứng minh không bị capture output.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `System.out` có luôn hiển thị lên màn hình không?  
**Không.** Nó có thể trỏ đến terminal, file, pipe hoặc collector khác do host/parent/shell cấu hình.

**Câu 2.** Nếu `System.console() == null`, có thể kết luận stdin đang lấy từ file không?  
**Không.** Chỉ biết JVM không có Console object tương ứng; nguyên nhân có thể là IDE, CI, scheduler hoặc redirection tùy phiên bản.

**Câu 3.** Trên JDK 24, `System.console() != null` có đảm bảo là terminal không?  
**Không.** Từ thay đổi trong JDK 22, object có thể tồn tại với `isTerminal() == false`.

**Câu 4.** `Console.isTerminal()` có từ phiên bản Java nào?  
**Java 22.** Không gọi trực tiếp trong class target Java 17–21.

**Câu 5.** Theo Javadoc Oracle Java SE 26, nếu Console tồn tại thì `isTerminal()` thường trả gì?  
**`true`**; tài liệu hiện hành nói Console chỉ được cung cấp khi stdin/stdout không bị redirect và là terminal tương tác. Dùng kiểm tra kép vẫn mô tả ý định rõ.

**Câu 6.** Với `java App < input.txt > out.txt 2> err.txt`, ba streams đi đâu?  
`System.in` từ `input.txt`, `System.out` vào `out.txt`, `System.err` vào `err.txt`.

**Câu 7.** `BufferedReader.readLine()` trả `""` có phải EOF không?  
**Không.** EOF là `null`.

**Câu 8.** Trong `ProcessBuilder`, parent muốn gửi dữ liệu cho child thì dùng method gì?  
`Process.getOutputStream()` để ghi vào **stdin child** khi redirect input là PIPE.

**Câu 9.** Có nên dùng `readPassword` làm fallback tự động từ stdin trong CI không?  
**Không.** Nếu không có interactive terminal cần một policy cung cấp secret riêng, không tự mở đường đọc password có echo.

**Câu 10.** Vì sao nên để diagnostic trên stderr?  
Để stdout giữ giao thức dữ liệu sạch cho file/pipeline, và để người chạy redirect/quan sát lỗi độc lập.

**Câu 11.** `ProcessBuilder.inheritIO()` có bảo đảm child thành ứng dụng terminal không?  
**Không.** Nó chỉ thừa hưởng I/O endpoints của parent.

**Câu 12.** Trong fixture, output ổn định `stdoutLines=DATA:ALPHA|DATA:BETA` dựa vào điều gì?  
Input file UTF-8 xác định, redirect stdin/stdout/stderr bằng ProcessBuilder, xử lý batch không prompt và so các logical lines, không phụ thuộc việc có terminal.

## Tài liệu API chính thức và thông tin phiên bản

- [Oracle Java SE 26 — `Console`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): `readLine`, `readPassword`, `charset`, `isTerminal`, các điều kiện có/không có console trong hợp đồng hiện hành.
- [Oracle Java SE 22 — `Console`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/io/Console.html): nguồn gốc `isTerminal()` và semantics kiểm tra terminal khi console provider có thể tồn tại dưới redirection.
- [Oracle Java SE 26 — `System`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): `in`, `out`, `err`, `console()`, system properties liên quan.
- [Oracle Java SE 26 — `ProcessBuilder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): `Redirect.PIPE`, `INHERIT`, `redirectInput`, `redirectOutput`, `redirectError`, `inheritIO`, `redirectErrorStream`.
- [Oracle Java SE 26 — `Process`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): các stream từ góc nhìn parent và quy tắc xử lý tiến trình con.
- [Oracle Java SE 26 — `BufferedReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và EOF.
- [Oracle Java SE 26 — `InputStreamReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): chuyển bytes input thành ký tự theo charset.
- [Inside Java / OpenJDK — JLine as Default Console Provider (JDK 22)](https://inside.java/2023/07/31/quality-heads-up/): thay đổi `System.console()` trong môi trường redirected và động cơ bổ sung `isTerminal()`.

**Ghi nhớ:** Đối với chương trình Java, **“được khởi động từ terminal”**, **“có Console object”**, **“có terminal tương tác”** và **“ba standard streams đang nối vào đâu”** là những câu hỏi khác nhau. Tách `--interactive` khỏi `--batch`, dùng `Console.isTerminal()` trên JDK hỗ trợ, đọc stdin tới EOF và giữ stdout sạch là nền tảng để một CLI chạy đúng cả dưới bàn phím người dùng lẫn trong pipeline/CI.

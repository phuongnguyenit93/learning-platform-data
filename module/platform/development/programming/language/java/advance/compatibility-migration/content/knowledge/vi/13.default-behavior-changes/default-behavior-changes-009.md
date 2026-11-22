# Hành vi ProcessBuilder và cách truyền tham số trên từng hệ điều hành

Trong quá trình nâng cấp hoặc di chuyển ứng dụng Java, một đoạn mã gọi chương trình bên ngoài có thể hoạt động trên máy phát triển nhưng thất bại trên Windows, Linux hoặc macOS. Nguyên nhân không nhất thiết nằm ở phiên bản JDK; nhiều lỗi bắt nguồn từ sự khác nhau giữa **danh sách đối số Java truyền đi**, **cách hệ điều hành tạo process**, **quy tắc phân tích command line của chương trình đích** và **cú pháp của shell nếu ứng dụng chủ động gọi shell**.

`java.lang.ProcessBuilder` là API chuẩn để cấu hình và khởi chạy tiến trình con. Sử dụng đúng API giúp tránh nhiều lỗi với đường dẫn có dấu cách, đối số rỗng, ký tự đặc biệt, môi trường làm việc và luồng dữ liệu. Tuy vậy, ProcessBuilder **không bảo đảm mọi hệ điều hành đều diễn giải command line giống nhau**, và không tự biến một câu lệnh shell thành pipeline hoặc redirection.

Bài học này giải thích hợp đồng của ProcessBuilder, chỉ ra các khác biệt Windows/Unix-like, minh họa lệnh đúng và sai, hướng dẫn quản lý stdin/stdout/stderr, môi trường và vòng đời process, đồng thời đưa ra quy trình kiểm thử khi di chuyển ứng dụng Java sang JDK hoặc nền tảng mới.

## 1. Phân biệt bốn lớp xử lý một lệnh

Khi Java cần chạy một chương trình bên ngoài, hãy tách bốn lớp:

1. **Mã Java** tạo danh sách phần tử `List<String>` của lệnh: executable, sau đó là từng argument.
2. **JDK** chuyển cấu hình đó thành lời gọi tạo process của nền tảng.
3. **Hệ điều hành** tạo process, cung cấp environment, working directory và các handle hoặc file descriptor.
4. **Chương trình đích** nhận và phân tích các đối số theo runtime, thư viện hoặc quy ước riêng.

Trong trường hợp Java gọi một shell như `/bin/sh` hoặc `cmd.exe`, có thêm một lớp xử lý cú pháp shell trước khi chương trình đích được khởi chạy.

Sơ đồ:

```text
Java ProcessBuilder
      |
      | command = [executable, arg1, arg2, ...]
      v
JDK process-launch implementation
      |
      +-- Unix-like: process/exec với argv riêng biệt
      |
      +-- Windows: CreateProcess và một command-line string
      |
      v
Chương trình con
      |
      +-- nhận argv theo quy tắc của runtime/chương trình
      +-- sử dụng environment, cwd và I/O streams
```

Nếu gọi shell:

```text
Java
  |
  v
ProcessBuilder("/bin/sh", "-c", "echo ... | grep ...")
  |
  v
Shell phân tích quotes, $, |, >, ...
  |
  v
Một hoặc nhiều chương trình con
```

**Nguyên tắc đầu tiên:** với executable và các argument đã biết, truyền từng argument thành một phần tử riêng trong ProcessBuilder. Chỉ dùng shell khi thật sự cần cú pháp hoặc tính năng của shell.

## 2. ProcessBuilder: truyền danh sách, không truyền câu lệnh shell

### 2.1. Ví dụ đúng với đối số chứa dấu cách

```java
import java.io.IOException;
import java.util.List;

public final class LaunchExample {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        List<String> command = List.of(
            "my-tool",
            "--output",
            "reports/final report.txt",
            "--title",
            "Annual Report"
        );

        Process process = new ProcessBuilder(command)
            .inheritIO()
            .start();

        int exitCode = process.waitFor();
        System.out.println("Exit code: " + exitCode);
    }
}
```

Đây là mẫu xây dựng lệnh; executable `my-tool` chỉ là tên minh họa và phải có thật ở môi trường chạy. ProcessBuilder nhận bốn argument sau executable: `--output`, `reports/final report.txt`, `--title`, `Annual Report`. Dấu cách trong argument thứ hai và thứ tư **không** khiến Java tự tách chúng thành nhiều argument.

### 2.2. Ví dụ sai: gộp toàn bộ command thành một phần tử

```java
// Sai nếu kỳ vọng Java tự phân tích câu lệnh:
new ProcessBuilder(
    "my-tool --output reports/final report.txt"
).start();
```

Ở đây Java sẽ cố khởi chạy một executable mang tên chuỗi đó, thay vì tìm `my-tool` và tách arguments. Lệnh có thể báo `IOException` do không tìm thấy executable.

Một biến thể cũng sai:

```java
String output = "reports/final report.txt";

new ProcessBuilder(
    "my-tool",
    "--output " + output
).start();
```

Đối số thứ hai ở đây là **một phần tử** có nội dung `--output reports/final report.txt`. Nếu chương trình đích yêu cầu một option `--output` rồi một path, nó sẽ không hiểu đúng.

Cách đúng:

```java
new ProcessBuilder(
    "my-tool",
    "--output",
    output
).start();
```

### 2.3. Không tự chèn dấu nháy kép để “bảo vệ” dấu cách

```java
String path = "C:\\Program Files\\Example Tool\\data.txt";

// Không nên tự thêm dấu nháy vào dữ liệu argument:
new ProcessBuilder("my-tool", "\"" + path + "\"");
```

Nếu ý định là truyền đường dẫn không có dấu nháy như dữ liệu, hãy dùng:

```java
new ProcessBuilder("my-tool", path);
```

Với các chương trình nhận đối số theo quy ước phổ biến, JDK sẽ xử lý phần đóng gói cần thiết cho lời gọi process. Tự thêm dấu nháy có thể khiến chương trình nhận dấu nháy như một phần giá trị hoặc gây khác biệt parser giữa các nền tảng.

Ngoại lệ là khi bạn **cố tình gọi shell** và cung cấp mã lệnh cho shell. Khi đó quoting thuộc cú pháp shell, không thuộc API truyền danh sách thông thường; cần xem xét riêng ở phần sau.

### 2.4. Danh sách argument không đồng nghĩa một chuỗi in ra log

Nếu log bằng `String.join(" ", command)`, các ranh giới argument có dấu cách hoặc chuỗi rỗng sẽ bị mơ hồ.

Ví dụ:

```text
["tool", "--name", "Alice Smith", ""]
```

Log ghép bằng dấu cách có thể trông giống bốn hoặc nhiều argument; nó không tái hiện chính xác cách chương trình đích nhận đối số.

Để chẩn đoán, hãy log từng argument kèm chỉ số và cách biểu diễn rõ ràng (đồng thời che hoặc loại bỏ secret):

```java
for (int i = 0; i < command.size(); i++) {
    System.out.printf(
        "arg[%d] length=%d%n",
        i,
        command.get(i).length()
    );
}
```

Không in password, access token, private key hoặc nội dung nhạy cảm vào log chỉ để xác nhận quoting.

## 3. Khác biệt nền tảng: Unix-like và Windows

### 3.1. Linux và macOS: executable với argv riêng biệt

Ở Unix-like OS, lời gọi tạo process thường đi đến một dạng `exec` nhận đường dẫn executable và mảng các chuỗi đối số. Khi không đi qua shell, các ký tự như dấu cách, `*`, `$`, `|`, `>`, `;` không tự trở thành cú pháp shell.

Ví dụ:

```java
new ProcessBuilder(
    "/usr/bin/printf",
    "%s\\n",
    "hello world",
    "*.txt",
    "$HOME"
).inheritIO().start().waitFor();
```

Theo ý định, chương trình `printf` nhận `hello world`, `*.txt` và `$HOME` là các argument riêng. Không có bước glob expand `*.txt` thành tên file hay expand `$HOME` thành thư mục home chỉ vì hai chuỗi xuất hiện trong ProcessBuilder.

Khi cần biến `$HOME` thành một giá trị cụ thể, hãy đọc environment bằng Java hoặc chủ động gọi shell. Khi cần tìm file theo pattern, dùng `Files.newDirectoryStream`, `Files.walk` hoặc API file phù hợp thay vì trông chờ globbing ngầm.

### 3.2. Windows: CreateProcess nhận command-line string

Windows truyền một command-line string cho lời gọi tạo process. Nhiều chương trình Windows dùng runtime C/C++ hoặc parser riêng để xây `argv` từ chuỗi đó. JDK phải chuyển danh sách argument mà Java cung cấp thành chuỗi command line theo cơ chế của nền tảng.

Hệ quả:

- Java vẫn yêu cầu từng phần tử argument riêng biệt.
- JDK xử lý việc quote/escape cho nhiều trường hợp phổ biến.
- Chương trình đích có thể dùng parser không giống quy ước Microsoft C runtime.
- Batch script, `cmd.exe` và PowerShell có thêm tầng cú pháp riêng.
- Các ký tự như dấu nháy, backslash và dấu cách cần được kiểm thử với **chương trình đích thực tế**.

Không tự xây một chuỗi command line Windows rồi gán cả chuỗi thành một phần tử trong ProcessBuilder. Cách đó không “giống cmd.exe” mà thường khiến executable path sai.

### 3.3. So sánh nhanh

| Tình huống | Linux/macOS không dùng shell | Windows không dùng shell |
|---|---|---|
| Argument có dấu cách | Một phần tử Java được truyền như một argument | JDK quote khi cần; parser chương trình đích quyết định kết quả cuối |
| `*.txt` | Không tự glob-expand | Không tự giả định glob expansion |
| `$HOME` hoặc `%USERPROFILE%` | Không tự thay biến shell | Không tự thay biến cmd |
| `|`, `>`, `&&` | Không phải pipe/redirection | Không phải pipe/redirection nếu không qua shell |
| File `.sh` | Cần interpreter hoặc executable script hợp lệ | Không phải executable Windows thông thường |
| File `.bat`/`.cmd` | Không phải script Unix thông thường | Cần lưu ý xử lý bởi command processor |
| Đường dẫn executable có dấu cách | Dùng nguyên path làm phần tử đầu tiên | Dùng nguyên path làm phần tử đầu tiên |
| Phân tách PATH | Dấu hai chấm | Dấu chấm phẩy |
| Tính phân biệt hoa/thường | Thường phân biệt | Thường không phân biệt ở filesystem thông dụng |

Các mô tả filesystem và argument parsing là đặc điểm thường gặp, không phải quy tắc tuyệt đối của mọi filesystem, runtime hoặc executable trên từng nền tảng.

## 4. Đường dẫn executable: tuyệt đối, tương đối và PATH

### 4.1. Dùng đường dẫn tuyệt đối khi cần tính tái lập

Ví dụ Windows:

```java
String exe = "C:\\Program Files\\Example Tool\\my-tool.exe";

ProcessBuilder builder = new ProcessBuilder(
    exe,
    "--version"
);
```

Không cần nối dấu nháy bao quanh `C:\Program Files\...`. Đường dẫn đầy đủ là một phần tử của `command()`.

Ví dụ Unix:

```java
ProcessBuilder builder = new ProcessBuilder(
    "/usr/local/bin/my-tool",
    "--version"
);
```

Đường dẫn tuyệt đối giúp loại bỏ một phần phụ thuộc vào PATH, hạn chế nguy cơ chọn nhầm binary có cùng tên và dễ tái hiện môi trường. Tuy nhiên, phải xác nhận đường dẫn tồn tại trên mỗi máy/container và có quyền thực thi.

### 4.2. Chạy chương trình qua PATH

```java
new ProcessBuilder("git", "--version")
    .inheritIO()
    .start();
```

Ở đây `git` phải được hệ thống tìm thấy theo cơ chế tìm executable của JDK/OS trong môi trường phù hợp. Kết quả phụ thuộc cách Java được chạy, cấu hình PATH, shell/IDE/service/container và platform.

Không mặc định `git` nằm trên PATH chỉ vì gõ `git --version` thành công trong một terminal khác. Terminal tương tác có thể nạp shell profile hoặc thiết lập environment khác với service chạy Java.

Nếu cần đảm bảo binary đúng, cấu hình absolute path theo môi trường thay vì giả định vị trí.

### 4.3. `directory()` không phải cách thiết lập executable path

```java
import java.nio.file.Path;

Path work = Path.of("/opt/app/work");

ProcessBuilder builder =
    new ProcessBuilder("/usr/bin/my-tool", "input.txt");

builder.directory(work.toFile());
```

`directory()` đặt working directory cho tiến trình con. Nó không có nghĩa mọi cách tìm executable theo PATH được tự động chuyển thành tìm tại working directory đó. Để tránh mơ hồ giữa các hệ điều hành, dùng executable path tuyệt đối khi cần.

Đường dẫn `input.txt` mà chương trình con tự mở thường được diễn giải tương đối với working directory của process (trừ khi chương trình đó định nghĩa quy tắc riêng). Hãy đảm bảo thư mục tồn tại và service account có quyền truy cập.

### 4.4. Chạy Java con bằng runtime hiện tại

Nếu chương trình mẹ cần khởi chạy Java con cùng JDK đang sử dụng, có thể xác định launcher theo `java.home`:

```java
import java.nio.file.Path;
import java.util.Locale;

static boolean isWindows() {
    return System.getProperty("os.name")
        .toLowerCase(Locale.ROOT)
        .contains("win");
}

static Path javaLauncher() {
    String file = isWindows() ? "java.exe" : "java";
    return Path.of(
        System.getProperty("java.home"),
        "bin",
        file
    );
}
```

Sử dụng:

```java
Path java = javaLauncher();

Process process = new ProcessBuilder(
    java.toString(),
    "-version"
).inheritIO().start();

int exitCode = process.waitFor();
```

Đây là chiến lược thông dụng nhưng vẫn cần xác nhận runtime image có launcher phù hợp. Một ứng dụng đóng gói tùy chỉnh hoặc môi trường nhúng có thể có bố cục khác với JDK đầy đủ.

## 5. Không nhầm ProcessBuilder với shell

### 5.1. Pipe và redirection không tự hoạt động

Sai khi kỳ vọng shell xử lý:

```java
new ProcessBuilder(
    "find",
    ".",
    "|",
    "grep",
    ".java"
).start();
```

Lệnh này cố chạy `find` với các đối số `.`, `|`, `grep`, `.java`. Nó không tạo pipeline giữa hai process.

Tương tự:

```java
new ProcessBuilder(
    "my-tool",
    "--output",
    ">",
    "result.txt"
).start();
```

Dấu `>` chỉ là một argument nếu không có shell; nó không tự chuyển stdout thành file.

Nếu muốn chuyển stdout thành file, ProcessBuilder cung cấp redirect API:

```java
import java.io.File;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--version"
);

builder.redirectOutput(
    ProcessBuilder.Redirect.to(new File("result.txt"))
);

Process process = builder.start();
int exitCode = process.waitFor();
```

### 5.2. Nếu thật sự cần shell trên Unix

Ví dụ shell command cố định:

```java
Process process = new ProcessBuilder(
    "/bin/sh",
    "-c",
    "printf '%s\\n' hello | grep hello"
).inheritIO().start();

int exitCode = process.waitFor();
```

Shell phân tích đoạn lệnh `printf ... | grep ...`, thực hiện pipe và tạo tiến trình cần thiết. Đây là lựa chọn phù hợp khi tính năng shell thực sự được yêu cầu.

Tuy nhiên, dữ liệu từ người dùng **không** được ghép trực tiếp vào chuỗi lệnh shell. Nếu cần truyền dữ liệu động vào một script Unix, nên truyền qua positional parameters của shell, không qua nội suy chuỗi:

```java
String userValue = "a b; $(not-a-command)";

Process process = new ProcessBuilder(
    "/bin/sh",
    "-c",
    "printf '%s\\n' \"$1\"",
    "sh",
    userValue
).inheritIO().start();
```

Trong trường hợp này, `userValue` là argument riêng được shell truy cập qua `"$1"`. Vì được đặt trong dấu nháy kép trong script cố định, giá trị được xử lý như dữ liệu chứ không bị phân tích lại thành mã shell. Dấu `$` và dấu `;` nằm trong giá trị biến sẽ không tự trở thành command substitution hoặc separator mới.

Với các thao tác đơn giản như in chuỗi, vẫn nên gọi executable trực tiếp để không cần shell.

### 5.3. Nếu cần `cmd.exe` trên Windows

Ví dụ lệnh cmd cố định:

```java
Process process = new ProcessBuilder(
    "cmd.exe",
    "/c",
    "echo Hello from cmd"
).inheritIO().start();
```

`cmd.exe` có ngữ pháp riêng với các ký tự `&`, `|`, `<`, `>`, `^`, `%` và những quy tắc thay biến môi trường; khi bật delayed expansion còn có xử lý `!`. Vì vậy, việc ghép dữ liệu không tin cậy vào chuỗi lệnh `/c` có thể gây command injection hoặc sai giá trị.

Không áp dụng máy móc quy tắc escaping của Bash cho cmd.exe. Nếu cần truyền giá trị động, hãy thiết kế giao thức an toàn qua stdin, environment hoặc một file dữ liệu có kiểm soát; hoặc tốt hơn là gọi executable đích trực tiếp mà không đi qua cmd.

### 5.4. PowerShell có ngữ pháp khác cmd

Nếu chạy một PowerShell script, có thể gọi interpreter với đường dẫn script và tham số riêng:

```java
Process process = new ProcessBuilder(
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-File",
    "C:\\Scripts\\report.ps1",
    "-OutputPath",
    "C:\\Reports\\Monthly report.csv"
).inheritIO().start();
```

`powershell.exe` là Windows PowerShell nếu được cài/khả dụng. PowerShell 7 thường dùng launcher `pwsh` và có tính đa nền tảng hơn; không được giả định `pwsh` luôn có ở mọi máy. `-File` phù hợp với việc chạy script; `-Command` xử lý biểu thức PowerShell và có các quy tắc quoting, parameter binding khác.

Khi cần argument chứa ký tự đặc biệt, đường dẫn rỗng hoặc nested quoting, hãy kiểm tra script thực tế bằng thử nghiệm end-to-end. Không dùng chung một mẫu quoting cho `cmd`, PowerShell và `sh`.

## 6. Script `.sh`, `.bat` và `.cmd`

### 6.1. Unix shell script

Một script trên Linux/macOS có thể có shebang:

```sh
#!/bin/sh
printf 'Argument: %s\n' "$1"
```

Nếu file có quyền executable và môi trường hỗ trợ shebang, có thể chạy trực tiếp qua executable path. Nếu không, truyền interpreter rõ ràng:

```java
new ProcessBuilder(
    "/bin/sh",
    "/opt/app/scripts/process.sh",
    "file with spaces.txt"
).inheritIO().start();
```

Đường dẫn shell và các tùy chọn có thể khác giữa môi trường Linux, macOS hoặc container tối giản. Không dùng `bash` nếu script chỉ cần `sh` trừ khi tính năng Bash là yêu cầu thực sự.

Lưu ý script tải từ Windows có thể có CRLF line endings khiến shebang hoặc interpreter xử lý lỗi trên Unix. Quyền executable và case sensitivity cũng cần được kiểm tra.

### 6.2. Windows batch script

Trên Windows, file `.bat` hoặc `.cmd` được diễn giải theo quy tắc command processor. Một cách chủ động là gọi `cmd.exe` và script theo cấu hình đã kiểm soát. Tuy nhiên, việc truyền giá trị chứa `&`, `%`, dấu nháy hoặc ký tự điều khiển có thể chịu thêm tầng parsing của cmd và batch parameter expansion.

Ví dụ chỉ dùng tên và argument đơn giản:

```java
new ProcessBuilder(
    "cmd.exe",
    "/c",
    "C:\\Scripts\\build-report.cmd",
    "daily"
).inheritIO().start();
```

Không coi ví dụ đơn giản này là bộ escaping tổng quát cho mọi argument. Nếu đường dẫn script và argument có dấu cách/ký tự đặc biệt, cần kiểm thử chính xác với Windows, JDK và script đích. Đối với dữ liệu không tin cậy, nên tránh batch và chuyển sang chương trình nhận arguments trực tiếp hoặc dữ liệu qua stdin/file.

### 6.3. Xác định nền tảng trước khi chọn launcher

Mẫu dùng hai command shape khác nhau theo OS:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

static List<String> buildCommand(String input) {
    boolean windows = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT)
        .contains("win");

    List<String> cmd = new ArrayList<>();

    if (windows) {
        cmd.add("C:\\Tools\\analyzer.exe");
    } else {
        cmd.add("/usr/local/bin/analyzer");
    }

    cmd.add("--input");
    cmd.add(input);
    return cmd;
}
```

Dù chỉ khác executable path, phần xử lý options vẫn cần xác nhận chương trình hai nền tảng có cùng CLI contract. Đừng mặc định tên executable, separator đường dẫn hoặc charset của stdout giống nhau.

## 7. Windows command-line parsing: vì sao danh sách argument vẫn cần kiểm thử?

ProcessBuilder cung cấp API list arguments độc lập nền tảng, nhưng trên Windows, một chương trình nhận command-line string từ hệ điều hành. Mỗi runtime hoặc executable có thể diễn giải quote và backslash khác nhau.

Ví dụ những giá trị dễ gây vấn đề:

```text
a b
"quoted"
C:\data\folder\
value&other
100%complete
empty argument: ""
text with non-ASCII characters
```

Một chương trình biên dịch bằng C/C++ runtime phổ biến có thể nhận `argv` theo các quy tắc quote/backslash nhất định; một chương trình khác có thể dùng `GetCommandLineW` rồi tự phân tích. Một batch script lại được `cmd.exe` phân tích theo quy tắc khác.

Vì vậy:

- Đối với executable native thông thường, truyền từng argument bằng ProcessBuilder và kiểm thử thực tế.
- Không cố escape trước như khi gõ lệnh vào shell.
- Không dùng `cmd.exe /c` nếu chỉ cần gọi một `.exe`.
- Với batch/PowerShell, xác nhận quy tắc của interpreter và hợp đồng của script.
- Với dữ liệu phức tạp, dùng file UTF-8 hoặc stdin khi chương trình đích hỗ trợ.

### 7.1. Bài kiểm thử argument round-trip

Có thể viết một chương trình Java con in số lượng và từng argument:

```java
public final class ArgsPrinter {
    public static void main(String[] args) {
        System.out.println("argc=" + args.length);

        for (int i = 0; i < args.length; i++) {
            String value = args[i];
            System.out.println(
                i + ": length=" + value.length()
                    + ", value=[" + value + "]"
            );
        }
    }
}
```

Đoạn mã mẹ:

```java
import java.nio.file.Path;
import java.util.List;

List<String> command = List.of(
    javaLauncher().toString(),
    "-cp",
    Path.of("build", "classes")
        .toAbsolutePath()
        .toString(),
    "ArgsPrinter",
    "hello world",
    "",
    "a\"b",
    "C:\\Temp\\some folder\\",
    "Tiếng Việt"
);

Process process = new ProcessBuilder(command)
    .inheritIO()
    .start();

int code = process.waitFor();
```

`javaLauncher()` là helper đã định nghĩa trong phần trước. Directory classpath chỉ mang tính minh họa và phải chứa class `ArgsPrinter` đã biên dịch. Nếu test dùng Maven/Gradle, hãy lấy classpath thực tế từ build tool thay vì hard-code directory.

Chạy với JDK và OS mục tiêu để xác minh thứ tự, argument rỗng, quote, dấu cách, backslash và Unicode được bảo toàn qua đường truyền tới chương trình Java đích.

### 7.2. Đối số rỗng và khoảng trắng

Có khác biệt giữa:

- Không truyền argument nào.
- Truyền một argument rỗng `""`.
- Truyền một argument chỉ có dấu cách.
- Truyền đường dẫn có dấu cách ở giữa.

Ví dụ:

```java
new ProcessBuilder(
    "my-tool",
    "--value",
    ""
);
```

Đây là ba phần tử, trong đó phần tử thứ ba là chuỗi rỗng. Một CLI parser có thể coi “có option nhưng giá trị rỗng” khác với “không có option”. Hãy kiểm thử thay vì gộp bằng `String.trim()` rồi làm mất sự khác biệt.

## 8. Environment variables và khác biệt hệ điều hành

### 8.1. Environment của tiến trình con

`ProcessBuilder.environment()` trả về một map có thể chỉnh sửa cho tiến trình được tạo bởi builder đó:

```java
ProcessBuilder builder = new ProcessBuilder(
    "/usr/bin/env"
);

builder.environment().put("APP_MODE", "integration-test");
builder.environment().put("LANG", "C.UTF-8");

builder.inheritIO();

Process process = builder.start();
int exitCode = process.waitFor();
```

`/usr/bin/env` và giá trị locale `C.UTF-8` là ví dụ Unix-like; không đảm bảo xuất hiện trên mọi hệ thống. Trong production, dùng executable thực tế và kiểm tra locale được OS hỗ trợ.

Map environment là một bản sao để cấu hình process con; thay đổi nó không sửa môi trường của process Java cha và không sửa biến môi trường toàn hệ thống.

### 8.2. Không đồng nhất environment của terminal và service

Một ứng dụng Java chạy từ IDE, systemd, Windows Service, container hoặc CI có thể nhận `PATH`, `HOME`, `TEMP`, `JAVA_HOME` hoặc proxy settings khác với terminal tương tác.

Ví dụ, một shell đăng nhập có thể nạp `.bashrc` hoặc profile, còn service không đọc các file đó. Nếu Java chạy trong container, PATH có thể chỉ chứa các thư mục trong image.

Vì vậy, khi executable chỉ tìm thấy trong một môi trường, hãy kiểm tra environment thực tế của process Java, không chỉ kiểm tra terminal khác.

### 8.3. Phân biệt hoa/thường của tên biến môi trường

Trên nhiều Unix-like OS, tên biến môi trường phân biệt hoa/thường: `PATH` và `Path` có thể là hai tên khác nhau. Windows thường có cách xử lý environment names không phân biệt hoa/thường.

Java `Map` do `environment()` trả về có hành vi phụ thuộc nền tảng. Tránh viết code dựa vào khả năng lưu đồng thời `PATH` và `Path` rồi kỳ vọng giống nhau trên mọi OS.

### 8.4. Thay PATH không phải chiến lược tốt nhất để chọn executable

Một số code thay `builder.environment().put("PATH", ...)` rồi kỳ vọng JDK sẽ luôn tìm executable theo PATH mới. Chi tiết tìm executable có thể phụ thuộc JDK và OS, vì việc resolve command và environment của child không nhất thiết là cùng một bước.

Để chọn executable đáng tin cậy, ưu tiên đường dẫn tuyệt đối đã được cấu hình và xác thực. PATH trong environment phù hợp khi **chương trình con** hoặc các process con của nó cần môi trường PATH đó.

### 8.5. Secret trong environment

Environment variables có thể giúp tránh lộ secret trong command line, nhưng không phải nơi lưu bí mật tuyệt đối: các công cụ chẩn đoán, crash report hoặc process cùng quyền có thể đọc chúng tùy OS.

Không log toàn bộ `builder.environment()`, không in access token và không để secret trong `ProcessBuilder.command()` nếu có kênh an toàn hơn. Với secret quan trọng, ưu tiên secret manager, file quyền hạn chế hoặc IPC theo mô hình bảo mật của ứng dụng.

## 9. Working directory và xử lý đường dẫn

### 9.1. Đặt thư mục làm việc

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path workDir = Path.of("work", "jobs", "42").toAbsolutePath();

Files.createDirectories(workDir);

ProcessBuilder builder =
    new ProcessBuilder("/usr/local/bin/analyzer", "input.csv");

builder.directory(workDir.toFile());

Process process = builder.start();
```

Trên Windows, executable path phải được thay bằng path hợp lệ. Nếu chương trình đích mở `input.csv` bằng đường dẫn tương đối, thường nó sẽ tìm file tương đối với working directory được cấp.

`directory(null)` (giá trị mặc định) thường dùng working directory của tiến trình Java cha. Đừng giả định working directory luôn là thư mục chứa JAR; nó phụ thuộc cách ứng dụng được khởi chạy.

### 9.2. Dùng `Path` thay vì ghép separator

Không nên tạo file path bằng cách nối chuỗi thủ công:

```java
String file = base + "/" + subfolder + "/" + name;
```

Thay bằng:

```java
Path input = basePath
    .resolve("data")
    .resolve("report 2026.csv")
    .toAbsolutePath();

new ProcessBuilder(
    executable.toString(),
    "--input",
    input.toString()
);
```

`Path` xử lý separator theo filesystem provider của Java. Tuy nhiên, nếu một command nhận URL, POSIX path trên Windows, hoặc cú pháp path riêng của ứng dụng, cần chuyển đổi theo CLI contract của chương trình đó, không mù quáng dùng `Path.toString()`.

### 9.3. Không phụ thuộc vào relative path trong CI

Trong CI, project root, temporary directory và working directory của runner có thể khác nhau. Sử dụng `Path.toAbsolutePath()` khi chuẩn bị resource, hoặc đặt `builder.directory()` rõ ràng. Log directory dự kiến và executable path, nhưng tránh in dữ liệu nhạy cảm.

Kiểm tra quyền read/write/execute của service account hoặc user chạy Java. Trên Unix, tồn tại file không có nghĩa file executable; trên Windows, extension và file association cũng ảnh hưởng cách script được chạy.

## 10. Standard input, output và error

### 10.1. Ba luồng của tiến trình

`Process` cung cấp:

- `getOutputStream()`: Java ghi vào **stdin của tiến trình con**.
- `getInputStream()`: Java đọc **stdout của tiến trình con**.
- `getErrorStream()`: Java đọc **stderr của tiến trình con**.

Tên method có thể gây nhầm vì được đặt theo góc nhìn process Java cha:

```text
Java parent                     Child process
-----------                     -------------
getOutputStream() --------->    stdin
getInputStream()  <---------    stdout
getErrorStream()  <---------    stderr
```

Không tự động có một console tương tác. Mặc định, ProcessBuilder tạo các pipe thích hợp trừ khi đã redirect hoặc inherit streams.

### 10.2. `inheritIO()` cho công cụ dòng lệnh tương tác

```java
Process process = new ProcessBuilder(
    "git",
    "--version"
).inheritIO().start();

int exitCode = process.waitFor();
```

`inheritIO()` cho phép process con dùng standard input/output/error của process Java cha. Cách này thích hợp cho CLI không cần thu thập riêng output hoặc công cụ mà người vận hành muốn nhìn trực tiếp.

Không dùng `inheritIO()` nếu ứng dụng cần phân tích output thành dữ liệu máy. Khi chạy trong service/container, inherited streams có thể đi vào stdout/stderr logging của container thay vì console người dùng.

### 10.3. Vì sao đọc sai stdout/stderr gây deadlock?

Nếu process con ghi rất nhiều dữ liệu vào stdout hoặc stderr mà Java không đọc, buffer pipe có thể đầy, khiến process con chặn khi ghi. Khi đó Java chờ `waitFor()`, còn process con chờ Java đọc pipe: ứng dụng có thể treo.

Ví dụ nguy hiểm:

```java
Process process = new ProcessBuilder("very-verbose-tool").start();

// Có thể treo nếu child ghi đầy stdout/stderr:
int exitCode = process.waitFor();
```

Phải tiêu thụ output, redirect về file, dùng `inheritIO()` hoặc hợp nhất luồng phù hợp. Nếu tool có nhiều output, đừng đọc hết stdout rồi mới đọc stderr vì một trong hai pipe vẫn có thể đầy.

### 10.4. Hợp nhất stderr vào stdout

```java
import java.nio.charset.StandardCharsets;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--version"
);

builder.redirectErrorStream(true);

Process process = builder.start();

try (var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(
            process.getInputStream(),
            StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}

int exitCode = process.waitFor();
```

Khi `redirectErrorStream(true)`, stderr được trộn vào stdout và Java chỉ cần đọc một pipe. Nhược điểm là khó phân biệt dòng nào là lỗi, và chương trình có thể ghi các loại nội dung khác nhau vào hai luồng.

`StandardCharsets.UTF_8` chỉ đúng nếu **child phát output UTF-8**. Không được mặc định mọi chương trình Windows sử dụng UTF-8; có ứng dụng dùng legacy code page hoặc encoding tùy locale.

### 10.5. Redirect output trực tiếp ra file

```java
import java.io.File;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--run"
);

builder.redirectOutput(
    ProcessBuilder.Redirect.to(
        new File("logs/tool.stdout.log")
    )
);

builder.redirectError(
    ProcessBuilder.Redirect.appendTo(
        new File("logs/tool.stderr.log")
    )
);

Process process = builder.start();
int exitCode = process.waitFor();
```

Thư mục `logs` phải tồn tại và user chạy Java phải có quyền ghi. Với redirect ra file, không nên đồng thời giả định `process.getInputStream()` vẫn mang dữ liệu stdout để đọc: output đã được điều hướng ra đích khác.

Cần cân nhắc rotation, dung lượng ổ đĩa và bảo mật log nếu tool tạo nhiều output.

### 10.6. Ghi stdin cho process con

Nếu công cụ nhận input qua stdin, tránh ghép dữ liệu vào câu lệnh shell. Có thể ghi bằng Java:

```java
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

Process process = new ProcessBuilder(
    "my-tool",
    "--read-stdin"
).start();

try (OutputStreamWriter writer =
        new OutputStreamWriter(
            process.getOutputStream(),
            StandardCharsets.UTF_8)) {

    writer.write("one record\n");
    writer.write("two records\n");
}

int exitCode = process.waitFor();
```

Đóng output stream để gửi EOF cho child khi protocol mong đợi kết thúc input. Nhưng ví dụ này vẫn cần xử lý stdout/stderr nếu child ghi đáng kể ra hai luồng; trong hệ thống thực tế, có thể phải sử dụng task riêng cho input/output hoặc redirect phù hợp để tránh deadlock hai chiều.

## 11. Charset và Unicode khi đi qua biên tiến trình

### 11.1. Java String là Unicode, nhưng I/O bytes phụ thuộc encoding

Một argument Java là `String`, còn môi trường tiến trình và thư viện của chương trình đích có quy tắc mã hóa/giải mã riêng. Đối với Windows, Unicode command line được hệ điều hành hỗ trợ, nhưng chương trình native cũ có thể dùng API ANSI hoặc chuyển đổi qua code page, làm mất ký tự.

Trên Unix-like OS, argument bytes và locale/encoding cũng cần tương thích với chương trình đích. Một chuỗi tiếng Việt có thể đi qua Java tới child Java hiện đại, nhưng một CLI native lâu đời có thể xử lý khác.

Đừng mặc định “Java mặc định UTF-8” đồng nghĩa tất cả chương trình con, shell và terminal đều dùng UTF-8. JDK 18 thay đổi default charset theo JEP 400, nhưng encoding của child process hoặc console vẫn phải được xác nhận độc lập.

### 11.2. Tránh decode ngầm theo charset của máy

Ví dụ không ổn định:

```java
new InputStreamReader(process.getInputStream());
```

Constructor này sử dụng charset mặc định của Java process cha, có thể không trùng với output của chương trình con.

Nếu child đã có hợp đồng UTF-8:

```java
new InputStreamReader(
    process.getInputStream(),
    java.nio.charset.StandardCharsets.UTF_8
);
```

Với công cụ native, cần kiểm tra có tùy chọn như `--encoding UTF-8` hoặc khả năng cấu hình locale hay không. Nếu không hỗ trợ Unicode tốt, cân nhắc truyền dữ liệu phức tạp qua file UTF-8 đã kiểm soát hoặc giao thức IPC phù hợp.

### 11.3. Line endings khác nhau

Windows thường dùng CRLF và Unix-like thường dùng LF cho file text. `BufferedReader.readLine()` có thể xử lý các kiểu newline phổ biến, nhưng khi truyền dữ liệu nhị phân hoặc giao thức yêu cầu CRLF, không nên tự ý chuyển.

Nếu command tạo file cấu hình, hãy xác định encoding và newline yêu cầu thay vì dựa vào `System.lineSeparator()` của máy build.

## 12. Exit code, timeout và vòng đời tiến trình

### 12.1. Process start thành công không có nghĩa command thành công

`ProcessBuilder.start()` tạo được tiến trình con, nhưng tool có thể báo lỗi và kết thúc với exit code khác 0:

```java
Process process = new ProcessBuilder(
    "my-tool",
    "--validate"
).inheritIO().start();

int exitCode = process.waitFor();

if (exitCode != 0) {
    throw new IllegalStateException(
        "Tool failed with exit code " + exitCode
    );
}
```

Một số executable dùng exit code đặc biệt theo contract; không nên mặc định mọi non-zero code cùng một nghĩa nghiệp vụ. Cần đọc tài liệu của tool và phân biệt lỗi khởi tạo (IOException khi `start()`) với lỗi sau khi process đã chạy.

### 12.2. Đặt timeout để không chờ vô hạn

```java
import java.util.concurrent.TimeUnit;

Process process = new ProcessBuilder(
    "my-tool",
    "--long-task"
).redirectErrorStream(true)
 .inheritIO()
 .start();

boolean finished = process.waitFor(30, TimeUnit.SECONDS);

if (!finished) {
    process.destroy();

    if (!process.waitFor(5, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }

    throw new IllegalStateException("Process timed out");
}

int exitCode = process.exitValue();
```

Ví dụ minh họa timeout cho process trực tiếp. Thời gian 30/5 giây chỉ là giá trị mẫu; cần đặt theo SLO và đặc tính workload. `destroy()` yêu cầu kết thúc theo cơ chế nền tảng, còn `destroyForcibly()` tìm cách cưỡng bức chấm dứt.

Nếu đã chặn vào việc đọc stream và child không kết thúc, timeout chỉ đặt quanh `waitFor` có thể không đủ. Một giải pháp production cần quản lý cả nhiệm vụ đọc pipe, đóng stream, hủy tác vụ và cleanup.

### 12.3. Process con có thể tạo thêm descendant process

Nếu Java khởi chạy một shell hoặc build tool, process đó có thể tiếp tục tạo các process khác. Gọi `destroy()` lên process trực tiếp không tự động bảo đảm mọi descendant đều bị kết thúc trên tất cả OS.

Từ Java 9, `ProcessHandle` cho phép quan sát PID, descendants và một số thông tin liên quan:

```java
ProcessHandle handle = process.toHandle();

System.out.println("PID: " + handle.pid());

handle.descendants()
    .forEach(child ->
        System.out.println("Child PID: " + child.pid()));
```

Việc quản lý process tree đòi hỏi đồng bộ, quyền OS và xử lý race; danh sách descendants có thể thay đổi trong lúc đọc. Với dịch vụ cần dừng toàn bộ job, cân nhắc process group/job object, scheduler hoặc cơ chế isolation của container tương ứng.

### 12.4. Khi thread Java bị interrupt

`waitFor()` có thể ném `InterruptedException`. Không nên nuốt exception và để child chạy vô hạn mà không có owner. Tùy hợp đồng:

- Hủy child hoặc chuyển quyền quản lý cho một coordinator khác.
- Khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` nếu tầng trên cần biết.
- Cleanup pipe và task đọc output.
- Đừng giữ process sống vì code thoát sớm từ exception path.

## 13. ProcessBuilder.startPipeline không cần shell

Java 9 bổ sung `ProcessBuilder.startPipeline` cho phép nối stdout của một process sang stdin của process tiếp theo mà không phải tự viết cú pháp `|` trong shell.

Ví dụ ý tưởng trên một hệ thống có `grep` và `sort`:

```java
import java.util.List;

ProcessBuilder grep = new ProcessBuilder(
    "grep",
    "java",
    "README.txt"
);

ProcessBuilder sort = new ProcessBuilder(
    "sort"
);

List<Process> processes = ProcessBuilder.startPipeline(
    List.of(grep, sort)
);
```

Trong pipeline, Java thiết lập liên kết pipe giữa các process. Ứng dụng vẫn phải quản lý stderr, stdout cuối, exit codes và vòng đời **của tất cả** process; đồng thời phải chọn executable phù hợp với OS.

Ví dụ `grep` và `sort` không mặc định có trên Windows. Nếu cần pipeline portable, có thể thực hiện một số xử lý text thuần trong Java hoặc dùng chương trình cross-platform đã được đóng gói/khai báo rõ.

`startPipeline` không giải quyết shell syntax như variable expansion hay globbing. Nó tạo một pipeline từ những ProcessBuilder có command/arguments tách riêng.

## 14. An toàn bảo mật khi truyền lệnh và tham số

### 14.1. Phân biệt command injection và argument injection

**Command injection** thường xảy ra khi ghép dữ liệu không tin cậy vào chuỗi lệnh shell:

```java
// Không an toàn:
String command = "some-tool " + userInput;

new ProcessBuilder(
    "/bin/sh",
    "-c",
    command
).start();
```

Nếu `userInput` chứa dấu `;`, pipe, substitution hoặc cú pháp shell khác, shell có thể diễn giải thành lệnh ngoài ý định.

Dùng argument riêng làm giảm nguy cơ shell injection:

```java
new ProcessBuilder(
    "/usr/local/bin/some-tool",
    userInput
).start();
```

Nhưng **argument injection** vẫn có thể xảy ra nếu tool diễn giải dữ liệu người dùng bắt đầu bằng dấu gạch như một option. Ví dụ, một filename `--delete-all` có thể được CLI parser coi là option thay vì file.

Nếu chương trình đích hỗ trợ `--` để kết thúc option parsing:

```java
new ProcessBuilder(
    "/usr/local/bin/some-tool",
    "--",
    userProvidedFilename
).start();
```

Phải xác nhận tool thực sự hỗ trợ `--`; không phải mọi CLI đều có contract giống nhau.

### 14.2. Dùng allowlist cho executable và operation

Không nên cho người dùng nhập nguyên đường dẫn executable hoặc command template rồi chạy trực tiếp trong process Java có đặc quyền cao. Nếu ứng dụng cần hỗ trợ một tập operation, hãy khai báo allowlist:

```java
enum Operation {
    REPORT,
    VALIDATE
}

static List<String> commandFor(
        Operation operation,
        String inputPath) {

    return switch (operation) {
        case REPORT ->
            List.of("/opt/tools/report", "--input", inputPath);
        case VALIDATE ->
            List.of("/opt/tools/validate", "--input", inputPath);
    };
}
```

Ví dụ minh họa path Unix; Windows cần binary phù hợp. Dữ liệu `inputPath` vẫn phải được xác thực theo chính sách quyền và vùng filesystem được phép truy cập. List arguments không tự giải quyết path traversal hoặc hành vi nguy hiểm của tool.

### 14.3. Giới hạn quyền của process con

Process con thường kế thừa identity và nhiều quyền OS của process Java cha. Nếu Java service chạy với quyền cao, một command tùy ý có thể truy cập nhiều tài nguyên.

Do đó:

- Dùng service account quyền tối thiểu.
- Giới hạn filesystem/network trong container hoặc sandbox OS thích hợp.
- Không chạy executable không tin cậy chỉ vì đã tránh shell.
- Đặt timeout, giới hạn CPU/memory nếu hạ tầng hỗ trợ.
- Kiểm soát environment và secret được truyền cho child.
- Xác minh executable path và nguồn binary.

`ProcessBuilder` là API process management, **không** phải security sandbox.

## 15. So sánh ProcessBuilder với Runtime.exec

Java cũ thường dùng:

```java
Runtime.getRuntime().exec("my-tool --input report.txt");
```

Overload `Runtime.exec(String)` thực hiện tokenization đơn giản thay vì chạy lệnh qua shell mặc định. Nó không phải parser Bash hay Windows cmd hoàn chỉnh, nên có thể phá vỡ chuỗi chứa dấu cách và dấu nháy.

Ví dụ:

```java
String path = "C:\\Reports\\Monthly report.csv";

// Dễ sai nếu kỳ vọng shell-style quoting:
Runtime.getRuntime().exec(
    "my-tool --input \"" + path + "\""
);
```

Đối với code mới hoặc migration, nên ưu tiên ProcessBuilder với danh sách:

```java
new ProcessBuilder(
    "my-tool",
    "--input",
    path
).start();
```

`Runtime.exec(String[])` cũng nhận argument array, nhưng `ProcessBuilder` cung cấp cấu hình environment, working directory, redirect và I/O rõ ràng hơn.

### 15.1. Nâng JDK có thể lộ lỗi cũ

Một script có thể hoạt động khi đầu vào không chứa khoảng trắng hoặc ký tự đặc biệt, rồi thất bại khi chuyển môi trường mới với đường dẫn như:

```text
C:\Program Files\Vendor\tool.exe
/home/build agent/workspace/input.csv
/Users/Example User/My Documents/report.txt
```

Đây thường là lỗi thiết kế command construction từ trước, không nhất thiết là regression của JDK. Migration là thời điểm phù hợp để chuyển sang command list có kiểm thử.

## 16. Quy trình migration ProcessBuilder từ JDK 8 lên JDK hiện đại

### Giai đoạn 1: Kiểm kê điểm gọi process

Tìm các API và pattern:

- `new ProcessBuilder(...)`.
- `Runtime.getRuntime().exec(...)`.
- `ProcessBuilder.command(...)` hoặc thay đổi command list động.
- `/bin/sh -c`, `bash -c`, `cmd.exe /c`, `powershell -Command`.
- Gọi `.sh`, `.bat`, `.cmd`, `.exe`.
- Tự nối arguments thành một chuỗi.
- Gọi `getInputStream()`/`getErrorStream()` và `waitFor()`.
- `System.getenv()`, `builder.environment()` và `builder.directory()`.

Ví dụ tìm kiếm trong repository:

```shell
rg -n "ProcessBuilder|Runtime\\.getRuntime\\(\\)\\.exec" src
rg -n "cmd\\.exe|powershell|pwsh|/bin/sh|bash" src
rg -n "redirectErrorStream|inheritIO|waitFor\\(" src
```

Các lệnh chỉ là truy vấn ban đầu; cần kiểm tra script CI, plugin và thư viện bên thứ ba nếu chúng tự chạy process.

### Giai đoạn 2: Phân loại theo mục đích

| Nhóm | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Chạy executable có options | `tool --input file` | Command list, không shell |
| Chạy script | `.sh`, `.cmd`, `.ps1` | Interpreter phù hợp và contract rõ |
| Cần pipe/redirection | `|`, `>`, `2>` | ProcessBuilder redirection/pipeline hoặc shell cố định |
| Tìm command trên PATH | Tên executable ngắn | Xác nhận environment hoặc dùng absolute path |
| Xử lý output | Đọc stream/process log | Charset, pipe draining và exit code |
| Chạy tác vụ dài | Wait, timeout, kill | Lifecycle, cancellation và descendants |
| Truyền dữ liệu người dùng | Ghép chuỗi hoặc options | Phân tách arguments, validation, hạn chế shell |

Mục đích khác nhau cần giải pháp khác nhau; không thay toàn bộ bằng một wrapper shell duy nhất.

### Giai đoạn 3: Tách executable, arguments và environment

Tạo một cấu trúc lệnh rõ ràng, ví dụ:

```java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

static ProcessBuilder createExporter(
        Path exporter,
        Path input,
        Path output) {

    List<String> command = new ArrayList<>();

    command.add(exporter.toAbsolutePath().toString());
    command.add("--input");
    command.add(input.toAbsolutePath().toString());
    command.add("--output");
    command.add(output.toAbsolutePath().toString());

    return new ProcessBuilder(command);
}
```

Cấu trúc này cho phép kiểm thử danh sách argument trước khi chạy và tránh lỗi tự quote.

Nếu tool có đường dẫn hoặc options khác nhau theo OS, xây hai adapter riêng và dùng cùng bộ test contract về dữ liệu đầu vào/đầu ra.

### Giai đoạn 4: Chọn chiến lược I/O

Mỗi lệnh cần một chính sách rõ:

- Cho output đi thẳng vào terminal/log của service qua `inheritIO()`.
- Capture output với giới hạn kích thước và charset phù hợp.
- Redirect output/error về file.
- Dùng hai tác vụ đọc đồng thời cho stdout và stderr.
- Dùng `redirectErrorStream(true)` nếu không cần tách lỗi và dữ liệu.
- Đóng stdin để báo EOF nếu child chờ input.

Không chỉ gọi `waitFor()` rồi bỏ qua stdout/stderr.

### Giai đoạn 5: Đặt timeout và kiểm tra exit code

Định nghĩa những trường hợp:

- Start thất bại: `IOException`.
- Process chạy nhưng exit code khác 0.
- Timeout.
- Caller bị interrupt.
- Child không trả output như mong đợi.
- Child tạo thêm descendants.
- Lỗi khi đóng hoặc redirect stream.

Tại mỗi trường hợp, cần biết có process nào còn chạy và ai chịu trách nhiệm dọn dẹp.

### Giai đoạn 6: Thử trên từng OS/JDK mục tiêu

Không suy diễn từ một test chạy thành công trên Windows rằng command sẽ chạy trên Linux. Ma trận nên bao gồm OS/architecture/JDK/vendor mà sản phẩm cam kết:

| Test | Windows | Linux | macOS |
|---|---|---|---|
| Executable path chứa dấu cách | Có | Có | Có |
| Argument có dấu nháy/backslash | Có | Có | Có |
| Unicode và argument rỗng | Có | Có | Có |
| Script native theo OS | `cmd`/PowerShell | `sh`/Bash nếu có | `sh`/Bash/zsh tùy hệ thống |
| CWD và relative paths | Có | Có | Có |
| Env/PATH, case sensitivity | Có | Có | Có |
| Stdout/stderr lớn | Có | Có | Có |
| Timeout, interruption và descendants | Có | Có | Có |

Không nhất thiết dự án hỗ trợ mọi hệ điều hành. Chỉ đưa những target được cam kết vào acceptance gate, nhưng không dùng cấu hình không thuộc phạm vi hỗ trợ để kết luận tương thích.

## 17. Các tình huống lỗi thường gặp

### 17.1. `CreateProcess error=2` hoặc “No such file or directory”

**Dấu hiệu:** `start()` ném `IOException`, executable không được tìm thấy.

**Nguyên nhân:** path sai, command phần tử đầu chứa cả options, PATH không đúng hoặc môi trường service thiếu binary.

**Cách xử lý:** in executable path đã che dữ liệu nhạy cảm, xác nhận file tồn tại/quyền execute và chọn absolute path. Không tự nối quote vào executable path.

### 17.2. Executable chạy nhưng nhận sai số lượng argument

**Dấu hiệu:** tool báo “unknown option”, “missing value” hoặc nhận tên file bị tách.

**Nguyên nhân:** nối `--input file` thành một argument hoặc tự tách giá trị dựa trên whitespace.

**Cách xử lý:** dùng `List<String>`, mỗi option và value là một phần tử nếu CLI yêu cầu. Kiểm tra bằng `ArgsPrinter` hoặc một chương trình mock tương tự.

### 17.3. Dấu `|` hoặc `>` xuất hiện trong output thay vì tạo pipe

**Nguyên nhân:** truyền shell syntax như argument bình thường.

**Cách xử lý:** dùng `redirectOutput`, `redirectInput`, `startPipeline` hoặc gọi shell có chủ đích. Không giả định ProcessBuilder tự gọi shell.

### 17.4. Batch script lỗi chỉ khi đường dẫn có khoảng trắng

**Nguyên nhân:** thêm một tầng phân tích của `cmd.exe` và các quy tắc quoting khác executable thông thường.

**Cách xử lý:** tránh batch nếu có executable tương đương; nếu cần batch, dùng script/adapter Windows được kiểm thử với đường dẫn chứa space, quote và metacharacters. Tránh ghép dữ liệu không tin cậy vào chuỗi `/c`.

### 17.5. Unicode output bị lỗi ký tự

**Nguyên nhân:** child xuất dữ liệu theo code page khác UTF-8 hoặc parent đọc sai charset.

**Cách xử lý:** công bố encoding của child, cấu hình tool nếu có, đọc stream với charset tương ứng; không suy ra encoding của child từ Java source encoding.

### 17.6. Java treo khi chờ tiến trình con

**Nguyên nhân:** stdout hoặc stderr pipe đầy; child chờ input; process không kết thúc; timeout thiếu hoặc executor đọc output bị khóa.

**Cách xử lý:** drain/redirect streams, gửi EOF khi cần, đặt timeout, quản lý interruption và process tree.

### 17.7. Tool chạy trong terminal nhưng không chạy từ Java service

**Nguyên nhân:** PATH, environment, quyền user, working directory hoặc shell profile khác nhau.

**Cách xử lý:** lấy environment từ runtime service thực tế, sử dụng absolute executable path, set cwd và env rõ, kiểm tra quyền filesystem/network.

### 17.8. Process con chạy xong nhưng service không dừng

**Nguyên nhân:** task đọc pipe chưa kết thúc, còn process descendants, stream chưa được đóng, thread pool chờ vô hạn hoặc shutdown hook không phối hợp.

**Cách xử lý:** xây lifecycle rõ, đóng resource theo owner, đợi/hủy task có timeout, quan sát descendants và metrics.

## 18. Thiết kế helper API ổn định cho ứng dụng

Để tránh mỗi module tự xây lệnh khác nhau, có thể cung cấp một abstraction nhỏ quản lý command list và I/O. Nhưng abstraction không nên che hết chi tiết OS hoặc ngầm gọi shell.

Ví dụ helper cho lệnh có output nhỏ, không cần tương tác:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

record CommandResult(int exitCode, String output) {}

static CommandResult runCommand(
        List<String> command,
        Charset outputCharset,
        Duration timeout)
        throws IOException, InterruptedException {

    ProcessBuilder builder = new ProcessBuilder(command);
    builder.redirectErrorStream(true);

    Process process = builder.start();

    // Chỉ thích hợp khi output được giới hạn và tiến trình kết thúc
    // đúng hạn; production nên đọc bất đồng bộ để timeout có hiệu lực
    // ngay cả khi child không đóng pipe.
    try {
        if (!process.waitFor(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS)) {

            process.destroyForcibly();
            process.waitFor();
            throw new IOException("Process timed out");
        }

        StringBuilder output = new StringBuilder();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                    process.getInputStream(), outputCharset))) {

            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append('\n');
            }
        }

        return new CommandResult(
            process.exitValue(), output.toString()
        );
    } finally {
        if (process.isAlive()) {
            process.destroyForcibly();
        }
    }
}
```

**Giới hạn của ví dụ:** dù có timeout, việc chờ process trước khi tiêu thụ pipe vẫn có thể gây deadlock nếu stdout/stderr lớn. Đây là mẫu minh họa cấu trúc result và quản lý timeout chứ **không phải helper production an toàn cho mọi workload**. Với tool có output không được giới hạn, hãy redirect ra file hoặc khởi động reader đồng thời trước khi chờ process.

Trong implementation production, nên tách thành các thành phần:

- `CommandSpec`: executable path, arguments, working directory, environment delta.
- `OutputPolicy`: inherit, file, capture có giới hạn, hoặc streaming callback.
- `TimeoutPolicy`: deadline, graceful shutdown, forced stop.
- `CommandResult`: exit code, output metadata, elapsed time.
- `DiagnosticPolicy`: log path và argument đã redact, không ghi secret.

Thiết kế như vậy cho phép kiểm thử dễ hơn và tránh trùng lặp logic quoting, timeout, charset trong từng module.

## 19. Checklist tương thích ProcessBuilder

### Danh sách lệnh

- [ ] Mỗi argument được truyền như một phần tử `String` riêng biệt.
- [ ] Không ghép toàn bộ command thành phần tử đầu.
- [ ] Không tự thêm dấu quote như dữ liệu vào path chỉ để xử lý space.
- [ ] Đã kiểm tra argument rỗng, dấu nháy, backslash, Unicode và ký tự đặc biệt.
- [ ] Các options do người dùng cung cấp có validation hoặc delimiter `--` nếu tool hỗ trợ.

### Nền tảng và môi trường

- [ ] Executable tồn tại và có quyền chạy trên OS đích.
- [ ] Không mặc định shell, `git`, `bash`, `cmd.exe` hoặc `pwsh` luôn tồn tại ở mọi target.
- [ ] Có adapter riêng cho `.sh`, `.bat`/`.cmd`, `.ps1` khi cần.
- [ ] Working directory và path của file đầu vào/đầu ra được xác định rõ.
- [ ] PATH và environment của service/container đã được kiểm tra.
- [ ] Không lộ secret trong command line hoặc log.

### I/O và vòng đời

- [ ] Stdout/stderr được drain, redirect hoặc inherit có chủ đích.
- [ ] Charset output/input phù hợp với chương trình con.
- [ ] Stdin được đóng hoặc gửi EOF khi protocol yêu cầu.
- [ ] Exit code được kiểm tra theo contract của tool.
- [ ] Có timeout, xử lý interruption và cleanup.
- [ ] Process descendants được quản lý nếu command tạo thêm tiến trình.
- [ ] Không đọc stream đã được redirect ra file.

### Migration và kiểm thử

- [ ] Đã rà soát `Runtime.exec(String)` và các câu lệnh nối chuỗi.
- [ ] Đã loại bỏ shell invocation khi không cần shell.
- [ ] Test argument round-trip chạy trên từng OS/JDK được hỗ trợ.
- [ ] Test đường dẫn có dấu cách và environment thật của CI/service.
- [ ] Test output lớn, timeout, lỗi start và exit code khác 0.
- [ ] Tài liệu triển khai nêu rõ executable, quyền, working directory và encoding.

## Kết luận

`ProcessBuilder` cung cấp API tường minh để khởi chạy process và truyền danh sách argument, nhưng nó không phải một shell portable. Không dùng cách nghĩ “gõ được trong terminal thì đưa cả chuỗi vào ProcessBuilder sẽ chạy”. Trên Unix-like OS, argument thường đi qua cơ chế `argv`; trên Windows, JDK cần chuyển danh sách đó thành command-line string cho `CreateProcess` và chương trình đích có thể áp dụng parser riêng. Khi chủ động gọi `sh`, `cmd.exe` hoặc PowerShell, các quy tắc shell lại tạo thêm một lớp xử lý.

Để migration ổn định, hãy tách executable khỏi từng argument, dùng absolute path và working directory khi cần, tránh ghép dữ liệu vào shell command, quản lý environment và encoding, đọc hoặc redirect đầy đủ stdout/stderr, kiểm tra exit code và timeout. Cuối cùng, kiểm thử với các chuỗi khó như dấu cách, argument rỗng, Unicode và ký tự đặc biệt trên chính OS và JDK được hỗ trợ. Nhờ đó, lỗi “chạy được trên máy này nhưng hỏng trên máy khác” sẽ được phát hiện bằng kiểm thử thay vì xuất hiện sau khi triển khai.


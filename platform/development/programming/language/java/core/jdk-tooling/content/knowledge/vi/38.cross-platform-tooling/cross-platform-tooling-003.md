# Quoting tham số trên nhiều nền tảng: Bash, PowerShell, cmd.exe và Java

**Quoting tham số** là cách giữ cho một giá trị được truyền tới chương trình đúng như dự định, dù giá trị có dấu cách, dấu nháy, dấu gạch chéo ngược, ký tự Unicode hoặc ký tự đặc biệt của shell. Chủ đề này rất quan trọng khi viết script build, gọi Java CLI, chạy Maven/Gradle trong CI, hoặc khởi tạo tiến trình con từ Java.

Một chuỗi lệnh thường đi qua nhiều lớp phân tích. Shell có thể mở rộng biến, tách từ, xử lý pipe hoặc wildcard trước khi chương trình được chạy. Trên Windows, `CreateProcess` nhận một command-line string và chương trình đích tự phân tích string đó thành arguments. Java launcher, `cmd.exe`, PowerShell và Bash có quy tắc khác nhau.

Cách làm đáng tin cậy là hiểu lớp nào đang phân tích lệnh, giữ mỗi tham số thành một giá trị riêng càng lâu càng tốt, và kiểm thử round-trip bằng cách quan sát chính xác `args[]` mà chương trình đích nhận được.

## 1. Vì sao quoting tham số dễ sai?

Giả sử chương trình cần nhận đúng ba tham số:

~~~text
--file
C:\Build Output\release candidate.jar
--label
nightly build
~~~

Nếu shell tách chuỗi theo dấu cách, đường dẫn có thể bị chia thành nhiều arguments. Nếu shell mở rộng `$HOME`, `*` hoặc `%TEMP%`, chương trình nhận giá trị đã thay đổi. Nếu dấu nháy bị shell loại bỏ ở sai lớp, chương trình không còn nhận được dấu nháy literal mà dữ liệu yêu cầu.

Các lỗi thường gặp:

- Đường dẫn có dấu cách bị chia thành nhiều arguments.
- `&`, `|`, `;`, `(` hoặc `)` bị shell hiểu thành toán tử.
- `$name`, `%NAME%` hoặc `!NAME!` bị thay bằng environment variable ngoài ý muốn.
- Wildcard `*` bị shell mở rộng thành danh sách file.
- Dấu nháy kép bên trong giá trị làm đóng chuỗi sớm.
- Backslash ở cuối đường dẫn tương tác với dấu nháy đóng trên Windows.
- Script chạy được trên máy developer nhưng hỏng trên runner dùng shell khác.
- Giá trị do người dùng cung cấp bị ghép vào command string, dẫn đến command injection.

Quoting đúng phải bảo toàn **ranh giới argument** và **nội dung từng argument**. Hai yêu cầu này có liên quan nhưng không giống nhau.

## 2. Phân biệt shell command string và argument vector

Một chương trình Java nhận arguments qua:

~~~java
public static void main(String[] args)
~~~

Mỗi phần tử `args[i]` là một argument. Shell không phải là một phần của mảng này; shell phân tích command text trước khi khởi chạy chương trình.

Ví dụ Bash:

~~~bash
java -cp "out classes" com.example.Main "two words"
~~~

Shell bỏ dấu nháy bao quanh `out classes` và `two words`, sau đó truyền mỗi giá trị thành một argument riêng. Dấu nháy cú pháp không xuất hiện trong `args[]`.

Trong Java:

~~~java
String[] args = {
    "-cp",
    "out classes",
    "com.example.Main",
    "two words"
};
~~~

Mảng này đã biểu diễn ranh giới arguments. Không cần nối các phần tử thành một chuỗi có dấu nháy rồi hy vọng mọi shell hiểu giống nhau.

Trên POSIX, hệ điều hành tạo tiến trình bằng một mảng arguments. Trên Windows, `CreateProcess` nhận command-line string; runtime của chương trình đích thường tự phân tích string thành `argv`. Vì thế cùng một giá trị có thể cần cách biểu diễn khác nhau tùy nền tảng và chương trình nhận.

## 3. Các lớp phân tích trong một lệnh

Một lệnh gọi Java từ CI có thể đi qua các lớp sau:

~~~text
YAML workflow / CI configuration
             |
             v
       Shell parser
   Bash / PowerShell / cmd.exe
             |
             v
      OS process creation
      POSIX argv / Windows
             |
             v
     Java launcher parser
       java / javac / jcmd
             |
             v
       Application parser
       main(String[] args)
~~~

Không có một quy tắc escape duy nhất dùng cho mọi lớp.

- YAML quoting bảo vệ giá trị YAML, không tự bảo vệ shell command.
- Shell quoting bảo vệ token trong shell hiện tại.
- Windows command-line quoting phụ thuộc cách chương trình đích phân tích command line.
- Java launcher có cú pháp riêng cho `@argument-files`.
- Ứng dụng có thể tiếp tục parse argument thành option, path, expression hoặc mini-language.

Khi lỗi xảy ra, xác định lớp đầu tiên làm thay đổi dữ liệu. Đừng thêm dấu `\` hoặc `"` ngẫu nhiên vào mọi nơi.

## 4. Ký tự nào thường cần chú ý?

| Ký tự/giá trị | Bash | PowerShell | cmd.exe | Java ProcessBuilder |
|---|---|---|---|---|
| Dấu cách | Tách từ nếu không quote | Tách argument nếu không quote | Tách argument nếu không quote | Giữ trong một phần tử list |
| `$` | Mở rộng biến/command substitution | Mở rộng biến hoặc `$()` | Thường là ký tự thường | Không có ý nghĩa shell nếu không gọi shell |
| `&` | Toán tử điều khiển | Toán tử gọi command | Toán tử nối command | Là dữ liệu nếu target nhận đúng |
| `;` | Dấu phân cách lệnh | Dấu phân cách statement | Không phải command separator chính | Là dữ liệu |
| `|` | Pipe | Pipe | Pipe | Là dữ liệu nếu không gọi shell |
| `*` | Có thể glob thành tên file | Không glob giống Bash theo mặc định | Không glob giống Bash | Là dữ liệu; Java launcher có classpath wildcard riêng |
| `"` | Quote, có quy tắc escape riêng | Quote, có interpolation | Quote, có quy tắc shell riêng | Trên Windows còn phụ thuộc parser của target |
| `\` | Escape ngoài quote; trong double quote chỉ một số trường hợp | Không phải escape character của PowerShell | Không phải escape character của cmd | Có thể tham gia Windows CRT quoting hoặc Java argfile escaping |
| `%NAME%` | Ký tự thường nếu không được shell mở rộng theo cách khác | Thường là ký tự thường | Environment expansion | Dữ liệu nếu không gọi cmd |
| `!NAME!` | Thường là ký tự thường | History/khác tùy context | Delayed expansion nếu bật | Dữ liệu nếu không gọi cmd |

Bảng là hướng dẫn định hướng. Cú pháp thực tế phụ thuộc shell version, chế độ parsing và loại executable được gọi.

## 5. Quoting trong Bash

Bash có ba cơ chế phổ biến: single quotes, double quotes và backslash escape.

**Single quotes** giữ nguyên mọi ký tự bên trong. Một dấu nháy đơn literal không thể đặt trực tiếp trong một cặp single quotes.

~~~bash
java -cp 'out classes' com.example.Main '$HOME & (x); *'
~~~

Trong ví dụ, `$HOME`, `&`, dấu chấm phẩy và `*` đều là dữ liệu literal.

Để đưa một dấu nháy đơn vào chuỗi, đóng quote, escape dấu nháy, rồi mở quote lại:

~~~bash
printf '%s\n' 'it'\''s a build'
~~~

**Double quotes** giữ dấu cách và hầu hết metacharacters, nhưng `$`, backtick và một số trường hợp backslash vẫn có ý nghĩa:

~~~bash
java -Dbuild.label="$BUILD_LABEL" -cp "$CLASSPATH" com.example.Main
~~~

**Backslash** escape ký tự tiếp theo khi ở ngoài quotes:

~~~bash
printf '%s\n' two\ words
~~~

Trong script, dùng positional parameters hoặc array để giữ arguments:

~~~bash
set -- -cp "$CLASSPATH" com.example.Main --label "$BUILD_LABEL" --path "$OUTPUT_PATH"
java "$@"
~~~

`"$@"` mở rộng từng positional parameter thành một argument riêng. Tránh dùng `"$*"` hoặc ghép toàn bộ arguments thành một chuỗi nếu mục tiêu là giữ nguyên ranh giới arguments.

Khi chuyển tiếp toàn bộ arguments của script, dùng `"$@"`:

~~~bash
#!/usr/bin/env bash
exec java -jar app.jar "$@"
~~~

Không dùng `eval` để thực thi chuỗi do người dùng nhập. `eval` yêu cầu shell parse lại nội dung và có thể biến dữ liệu thành command.

## 6. Quoting trong PowerShell

PowerShell dùng backtick làm escape character. Backslash `\` thường là ký tự path, không phải escape character của PowerShell.

**Single-quoted string** là literal. Để biểu diễn dấu nháy đơn bên trong, viết hai dấu nháy đơn liên tiếp:

~~~powershell
$value = 'it''s a build'
~~~

**Double-quoted string** cho phép variable expansion và subexpression:

~~~powershell
$label = "build-$env:BUILD_NUMBER"
$path = "output/$($env:BUILD_LABEL)"
~~~

Để gọi native executable với argument array:

~~~powershell
$exe = Join-Path $env:JAVA_HOME 'bin/java.exe'
$args = @(
    '-cp'
    'out classes'
    'com.example.Main'
    '--label'
    'nightly build'
    '$HOME & (x); *'
)

& $exe @args
~~~

Call operator `&` thực thi executable được chỉ định. Splatting `@args` truyền các phần tử array thành arguments riêng. Cách này dễ đọc hơn ghép một command string.

PowerShell 7.3 thay đổi cách truyền arguments tới native executables. Biến `$PSNativeCommandArgumentPassing` có các mode `Legacy`, `Standard` và `Windows`. Trên Windows, mode mặc định là `Windows`; mode này có cách xử lý riêng cho `cmd.exe`, batch files và một số script host. Windows PowerShell 5.1 có hành vi legacy, vì vậy script có dấu nháy literal có thể hoạt động khác nhau giữa 5.1 và PowerShell 7.3+.

Có thể kiểm tra mode hiện tại:

~~~powershell
$PSVersionTable.PSVersion
$PSNativeCommandArgumentPassing
~~~

Token `--%` là stop-parsing token dành cho native commands trên Windows. Nó có thể hữu ích với một lệnh cố định có nhiều metacharacters, nhưng phần còn lại của dòng được xem như literal và khả năng dùng biểu thức PowerShell động bị hạn chế. Không coi `--%` là giải pháp quoting tổng quát cho dữ liệu không tin cậy.

Với script PowerShell 7+ cần xây dựng process programmatically, `System.Diagnostics.ProcessStartInfo.ArgumentList` cho phép thêm từng argument:

~~~powershell
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $exe
$psi.ArgumentList.Add('-cp')
$psi.ArgumentList.Add('out classes')
$psi.ArgumentList.Add('com.example.Main')
$psi.ArgumentList.Add('two words')

$process = [System.Diagnostics.Process]::Start($psi)
$process.WaitForExit()
$process.ExitCode
~~~

`ArgumentList` tránh việc tự ghép `ProcessStartInfo.Arguments` thành một chuỗi. Chương trình đích trên Windows vẫn có parser riêng, vì vậy cần kiểm tra các giá trị có dấu nháy literal với executable thực tế.

## 7. Quoting trong cmd.exe

`cmd.exe` dùng dấu nháy kép để giữ đường dẫn hoặc argument có dấu cách:

~~~bat
"%JAVA_HOME%\bin\java.exe" -cp "out classes" com.example.Main "two words"
~~~

Các metacharacters thường gặp gồm:

- `&`: chạy lệnh tiếp theo.
- `&&`: chạy lệnh tiếp theo nếu lệnh trước thành công.
- `||`: chạy lệnh tiếp theo nếu lệnh trước thất bại.
- `|`: pipe.
- `<` và `>`: chuyển hướng input/output.
- `(` và `)`: nhóm lệnh.
- `^`: escape character trong cmd.

Ví dụ dùng caret để escape ampersand:

~~~bat
echo A^&B
~~~

Dấu nháy kép thường đủ để bảo vệ `&`, `|`, dấu cách và một số metacharacters, nhưng cmd có nhiều bước xử lý bổ sung. `%NAME%` được mở rộng thành environment variable. Khi delayed expansion bật (`cmd /v:on` hoặc `EnableDelayedExpansion`), `!NAME!` cũng được mở rộng.

Đừng cho rằng đặt `%USER_INPUT%` trong dấu nháy sẽ vô hiệu hóa mọi expansion. `cmd /c` và đặc biệt `cmd /s /c` còn có quy tắc xử lý chuỗi lệnh riêng; `/s` có thể loại dấu nháy đầu/cuối theo quy tắc của cmd.

Nếu phải gọi một batch file, cần tính đến việc arguments đi qua `cmd.exe`. Nếu chỉ cần chạy một executable `.exe`, gọi trực tiếp executable sẽ tránh thêm một lớp shell parsing.

## 8. Windows command line và Microsoft C runtime

Windows `CreateProcess` nhận command-line string. Nó không nhận một `argv[]` array như POSIX `execve`. Chương trình đích quyết định cách phân tích string thành arguments.

Microsoft C runtime có quy tắc quan trọng đối với dấu nháy:

- Space và tab phân tách arguments khi ở ngoài quote.
- `\"` biểu diễn một dấu nháy kép literal.
- Backslash được giữ nguyên, trừ khi đứng ngay trước dấu nháy kép.
- Nếu có `n` backslashes ngay trước `"`, parser xét số lượng chẵn/lẻ: mỗi cặp backslash tạo một backslash literal; số lẻ còn dư escape dấu nháy.
- Backslash ở cuối một argument đã được quote cần được xử lý riêng để không vô tình escape dấu nháy đóng.

Ví dụ, để truyền giá trị `a"b` theo quy tắc Microsoft C runtime, command line có thể cần biểu diễn:

~~~text
"a\"b"
~~~

Để truyền một backslash literal ngay trước dấu nháy literal, phải nhân đôi backslash đó theo quy tắc trên.

Không phải mọi Windows executable đều dùng Microsoft C runtime. Một số chương trình có parser riêng, hoặc dùng parser cũ. Vì vậy, một hàm escape đúng cho `java.exe` không mặc nhiên đúng cho mọi `.exe`, `.bat` hay `.cmd`.

## 9. Dùng Java ProcessBuilder để gọi chương trình

`ProcessBuilder` nhận command dưới dạng `List<String>` hoặc `String...`. Mỗi phần tử mô tả executable hoặc một argument:

~~~java
Path java = Path.of(
        System.getProperty("java.home"),
        "bin",
        isWindows() ? "java.exe" : "java"
);

List<String> command = List.of(
        java.toString(),
        "-cp",
        classPath,
        "com.example.Main",
        "--label",
        "nightly build"
);

Process process = new ProcessBuilder(command).start();
~~~

Không tự thêm dấu nháy bao quanh path trong từng phần tử:

~~~java
// Sai: quote có thể trở thành ký tự thật trong giá trị.
new ProcessBuilder("java", "-cp", "\"out classes\"", "com.example.Main");

// Đúng: truyền path như một argument.
new ProcessBuilder("java", "-cp", "out classes", "com.example.Main");
~~~

`ProcessBuilder` không tự gọi Bash, PowerShell hoặc cmd. Nếu command là executable trực tiếp, shell metacharacters không được thực thi như shell operators.

Tuy nhiên, API vẫn phải chuyển arguments sang cách biểu diễn mà OS và target executable hiểu. Java API ghi rõ tính hợp lệ của command list phụ thuộc hệ điều hành. Trên Windows, việc truyền một dấu nháy kép literal cần xét parser của chương trình đích.

## 10. ProcessBuilder không thay thế shell parser

Các chuỗi sau không tự tạo pipe, redirection hoặc wildcard expansion khi truyền trực tiếp cho `ProcessBuilder`:

~~~java
new ProcessBuilder("grep", "error", "*.log");
new ProcessBuilder("java", "-jar", "app.jar", ">", "build.log");
~~~

Ở đây `*.log` có thể được chuyển nguyên văn tới `grep`; `>` có thể trở thành một argument bình thường. Shell mới là lớp thường mở rộng wildcard và xử lý redirection.

Nếu cần pipe, Java 9+ có `ProcessBuilder.startPipeline`:

~~~java
List<Process> pipeline = ProcessBuilder.startPipeline(List.of(
    new ProcessBuilder("find", "src", "-type", "f"),
    new ProcessBuilder("grep", "\\.java$")
));
~~~

Ví dụ trên minh họa pipeline trên môi trường POSIX có `find` và `grep`. Với Windows, cần công cụ tương đương hoặc triển khai xử lý stream trong Java.

Nếu cố ý gọi shell:

~~~java
new ProcessBuilder("bash", "-c", "echo hello");
~~~

hoặc:

~~~java
new ProcessBuilder("cmd.exe", "/c", "echo hello");
~~~

thì shell parsing lại xuất hiện. Mọi giá trị động được nối vào script phải được escape theo đúng shell, hoặc chuyển qua stdin/environment/file. Tránh ghép dữ liệu không tin cậy vào tham số `-c` hay `/c`.

## 11. Ví dụ Java hoàn chỉnh: kiểm tra round-trip arguments

Ví dụ sau khởi chạy một JVM con bằng `ProcessBuilder`. Chương trình kiểm tra các giá trị có dấu cách, argument rỗng, dấu nháy, backslash, path Windows, ký tự shell và Unicode.

Trên Windows, hàm `encodeForWindowsCrt` chỉ áp dụng cho target dùng Microsoft C runtime parsing. Hàm nhân đôi backslash đứng trước dấu nháy và thêm một backslash để dấu nháy được hiểu là literal. Trên POSIX, truyền nguyên giá trị vì OS đã nhận argument vector.

Tệp `ArgRoundTrip.java`:

~~~java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class ArgRoundTrip {
    private static final String[] EXPECTED = {
        "two words",
        "",
        "quote\"inside",
        "space and quote \"inside\"",
        "trailing-backslash\\",
        "C:\\Program Files\\Java\\bin",
        "$HOME & (x); *",
        "Ti\u1EBFng Vi\u1EC7t \u2013 \u6771\u4EAC",
        "-leading-option",
        "one-backslash\\\"then-quote"
    };

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            for (int i = 1; i < args.length; i++) {
                System.out.println("ARG[" + (i - 1) + "]=" + escape(args[i]));
            }
            return;
        }

        Path javaExecutable = Path.of(System.getProperty("java.home"), "bin",
                isWindows() ? "java.exe" : "java").toAbsolutePath();

        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add(ArgRoundTrip.class.getName());
        command.add("--child");

        for (String argument : EXPECTED) {
            command.add(isWindows()
                    ? encodeForWindowsCrt(argument)
                    : argument);
        }

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);

        int exit = process.waitFor();
        if (exit != 0) {
            throw new IllegalStateException(
                    "Child exit code " + exit + ": " + output);
        }

        String[] lines = output.stripTrailing().split("\\R", -1);
        if (lines.length != EXPECTED.length) {
            throw new AssertionError(
                    "Expected " + EXPECTED.length
                    + " arguments, received " + lines.length + ": " + output);
        }

        for (int i = 0; i < EXPECTED.length; i++) {
            String expectedLine = "ARG[" + i + "]=" + escape(EXPECTED[i]);
            if (!expectedLine.equals(lines[i])) {
                throw new AssertionError(
                        "Argument " + i + " mismatch. Expected "
                        + expectedLine + " but got " + lines[i]);
            }
        }

        System.out.println("ARGUMENT_COUNT=" + EXPECTED.length);
        System.out.println("ARGUMENT_ROUND_TRIP=PASS");
        for (String line : lines) {
            System.out.println(line);
        }
    }

    private static String encodeForWindowsCrt(String value) {
        StringBuilder encoded = new StringBuilder();
        int backslashes = 0;

        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);

            if (current == '\\') {
                backslashes++;
                continue;
            }

            if (current == '"') {
                encoded.append("\\".repeat(backslashes * 2 + 1));
            } else {
                encoded.append("\\".repeat(backslashes));
            }

            encoded.append(current);
            backslashes = 0;
        }

        encoded.append("\\".repeat(backslashes));
        return encoded.toString();
    }

    private static String escape(String value) {
        StringBuilder escaped = new StringBuilder();

        value.codePoints().forEach(cp -> {
            if (cp == '\\') escaped.append("\\\\");
            else if (cp == '"') escaped.append("\\\"");
            else if (cp < 32 || cp > 126) {
                escaped.append(String.format("\\u%04X", cp));
            } else {
                escaped.appendCodePoint(cp);
            }
        });

        return escaped.toString();
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
    }
}
~~~

Biên dịch và chạy từ Bash, PowerShell hoặc cmd. Dùng cùng một tên thư mục output có dấu cách để kiểm tra classpath:

~~~bash
javac --release 17 -d "out classes" ArgRoundTrip.java
java -cp "out classes" ArgRoundTrip
~~~

PowerShell cũng có thể dùng single quotes:

~~~powershell
javac --release 17 -d 'out classes' ArgRoundTrip.java
java -cp 'out classes' ArgRoundTrip
~~~

Stdout đã xác minh trên Windows 11 với Azul OpenJDK 24.0.2:

~~~text
ARGUMENT_COUNT=10
ARGUMENT_ROUND_TRIP=PASS
ARG[0]=two words
ARG[1]=
ARG[2]=quote\"inside
ARG[3]=space and quote \"inside\"
ARG[4]=trailing-backslash\\
ARG[5]=C:\\Program Files\\Java\\bin
ARG[6]=$HOME & (x); *
ARG[7]=Ti\u1EBFng Vi\u1EC7t \u2013 \u6771\u4EAC
ARG[8]=-leading-option
ARG[9]=one-backslash\\\"then-quote
~~~

Ví dụ được biên dịch với `javac --release 17` và chạy thành công. Nó kiểm tra cả số lượng arguments lẫn nội dung từng argument sau khi đi qua process boundary.

**Giới hạn quan trọng:** `encodeForWindowsCrt` là ví dụ cho parser theo quy tắc Microsoft C runtime, đã kiểm thử với `java.exe`. Không dùng hàm này cho mọi Windows executable nếu chưa biết parser của target. Khi target dùng quy tắc riêng, hãy dùng response file/argument file, stdin hoặc file dữ liệu, hoặc viết adapter theo parser của target.

## 12. Runtime.exec và lỗi ghép command string

`Runtime.exec(String)` không phải cách gọi shell tổng quát. Nó không tự hiểu Bash syntax, pipe hoặc redirection. Việc tách chuỗi command cũng có thể phụ thuộc implementation.

Không nên viết:

~~~java
String command = "java -jar app.jar --name " + userInput;
Runtime.getRuntime().exec(command);
~~~

Nếu `userInput` chứa dấu cách, quote hoặc shell metacharacter, kết quả có thể sai. Nếu sau này command được chuyển qua `sh -c` hoặc `cmd /c`, dữ liệu có thể biến thành cú pháp thực thi.

Dùng `ProcessBuilder` với danh sách arguments:

~~~java
List<String> command = List.of(
        javaExecutable.toString(),
        "-jar",
        jarPath.toString(),
        "--name",
        userInput
);

Process process = new ProcessBuilder(command).start();
~~~

Cách này giữ từng argument tách biệt và không yêu cầu viết shell escape cho một command string. Vẫn phải hiểu quy tắc parser của target trên Windows khi argument chứa dấu nháy literal.

## 13. Path, classpath và working directory

Dùng `Path` để tạo đường dẫn thay vì tự nối `/` hoặc `\`:

~~~java
Path projectDir = Path.of("build", "workspace");
Path jar = projectDir.resolve("app.jar");
Path log = projectDir.resolve("logs").resolve("compile.log");
~~~

`Path.toString()` trả biểu diễn path native của hệ điều hành. Khi truyền vào `ProcessBuilder`, đưa path thành một phần tử riêng:

~~~java
new ProcessBuilder(
        javaExecutable.toString(),
        "-jar",
        jar.toString()
);
~~~

Đặt working directory bằng API:

~~~java
ProcessBuilder builder = new ProcessBuilder(command);
builder.directory(projectDir.toFile());
~~~

Không thay working directory bằng cách nối `cd ... && ...` vào command string nếu không cần shell.

Classpath dùng path separator khác nhau:

- Windows: dấu chấm phẩy `;`.
- Linux/macOS: dấu hai chấm `:`.

Dùng `File.pathSeparator` khi ghép classpath trong Java:

~~~java
String classPath = String.join(
        java.io.File.pathSeparator,
        libraryPaths
);
~~~

Nếu gọi shell, nhớ rằng dấu `;` có thể là command separator trên Bash/PowerShell. Khi gọi bằng `ProcessBuilder`, classpath là một argument riêng và không cần shell quoting.

## 14. Java launcher argument files (`@argfile`)

Java launcher hỗ trợ argument file để chuyển một danh sách options, classpath, main class và arguments qua file văn bản. Đây là cách hữu ích khi command line quá dài hoặc có nhiều path chứa dấu cách.

Tạo `run.args`:

~~~text
-cp
"out classes"
ArgRoundTrip
--child
"two words"
""
"trailing-backslash\\"
"C:\\Program Files\\Java\\bin"
"$HOME & (x); *"
"quote\"inside"
~~~

Chạy:

~~~bash
java @run.args
~~~

Trong PowerShell, quote token `@run.args` để tránh PowerShell hiểu `@` là cú pháp splatting:

~~~powershell
java '@run.args'
~~~

Trong argument file:

- Dùng whitespace hoặc newline để phân tách arguments.
- Bao option/path có dấu cách trong dấu nháy kép.
- Backslash là escape character, vì vậy phải viết `\\` để truyền một backslash.
- `#` mở comment đến hết dòng.
- Path tương đối được tính từ working directory hiện tại, không phải thư mục chứa argfile.
- Wildcard trong argfile không được shell mở rộng.
- Java launcher hỗ trợ `--disable-@files` để dừng expansion.
- Không hỗ trợ lồng `@file` đệ quy.

`@argfile` là cú pháp của Java launcher. Một chương trình bất kỳ sẽ không tự hiểu file này nếu nó không tự triển khai response-file parsing.

## 15. Phân biệt shell wildcard và Java classpath wildcard

Trong Bash, `*.jar` có thể được mở rộng thành danh sách file trước khi chương trình chạy:

~~~bash
java -cp "lib/*" com.example.Main
~~~

Ở đây wildcard nằm trong dấu nháy nên shell không mở rộng nó. Java launcher có thể xử lý classpath wildcard trong classpath entry.

Nếu viết:

~~~bash
java -cp lib/* com.example.Main
~~~

Bash có thể mở rộng `lib/*` trước khi Java launcher nhận lệnh, làm thay đổi ranh giới arguments và kết quả.

PowerShell và cmd có quy tắc wildcard khác Bash. Đừng dựa vào shell glob nếu muốn một script dùng được trên nhiều hệ điều hành. Hãy để Java launcher xử lý classpath wildcard theo đúng cú pháp của nó hoặc tạo classpath rõ ràng từ build tool.

## 16. Dùng environment variable và stdin khi dữ liệu phức tạp

Nếu dữ liệu dài, chứa nhiều dấu nháy hoặc có thể chứa ký tự điều khiển, truyền nó qua stdin hoặc file có thể dễ kiểm soát hơn command line.

`ProcessBuilder` cho phép sửa environment:

~~~java
ProcessBuilder builder = new ProcessBuilder(command);
builder.environment().put("BUILD_LABEL", buildLabel);
builder.directory(projectDir.toFile());
Process process = builder.start();
~~~

Gửi nội dung qua stdin:

~~~java
try (var writer = process.outputWriter(
        java.nio.charset.StandardCharsets.UTF_8)) {
    writer.write(configurationJson);
}
~~~

Chỉ dùng environment variable cho dữ liệu phù hợp với môi trường tiến trình. Secret trong environment vẫn có thể bị lộ qua diagnostics hoặc process inspection; không đưa signing key hay credential vào log. Với payload lớn hoặc cấu trúc phức tạp, file JSON/YAML có quyền truy cập giới hạn thường dễ kiểm tra hơn.

## 17. Quoting trong Maven và Gradle scripts

Build tool thường nhận arguments qua wrapper, rồi tiếp tục parse options theo cú pháp riêng.

Maven:

~~~bash
./mvnw --batch-mode -DskipTests=false -Dbuild.label="nightly build" clean verify
~~~

PowerShell:

~~~powershell
.\mvnw.cmd --batch-mode '-Dbuild.label=nightly build' clean verify
~~~

Gradle:

~~~bash
./gradlew -PbuildLabel="nightly build" clean build
~~~

Trong PowerShell:

~~~powershell
.\gradlew '-PbuildLabel=nightly build' clean build
~~~

Các dấu nháy ở shell chỉ giữ một argument. Sau khi wrapper nhận argument, Maven/Gradle mới parse option `-D...` hoặc `-P...`.

Nếu property value đến từ người dùng, hãy truyền nó qua biến đã quote đúng cho shell hiện tại. Không nối raw value vào script hoặc dùng `eval`.

## 18. Quoting trong GitHub Actions và YAML

Workflow GitHub Actions có ít nhất hai lớp: YAML parser và shell được chọn bởi runner. YAML block scalar giúp giữ script nhiều dòng:

~~~yaml
steps:
  - name: Compile
    shell: bash
    env:
      BUILD_LABEL: ${{ github.ref_name }}
    run: |
      java -version
      ./mvnw --batch-mode "-Dbuild.label=$BUILD_LABEL" clean verify
~~~

Nếu dùng PowerShell:

~~~yaml
steps:
  - name: Compile on Windows
    shell: pwsh
    env:
      BUILD_LABEL: ${{ github.ref_name }}
    run: |
      java -version
      .\mvnw.cmd --batch-mode "-Dbuild.label=$env:BUILD_LABEL" clean verify
~~~

YAML quoting không thay thế shell quoting. `run: |` chỉ giữ block text; Bash hoặc PowerShell vẫn parse nội dung theo cú pháp riêng.

Đối với giá trị do người dùng cung cấp trong event payload, ưu tiên đưa qua `env:` rồi tham chiếu như một biến đã quote. Tránh chèn trực tiếp dữ liệu không tin cậy vào đoạn shell script được nội suy trước khi chạy.

Chọn `shell` rõ ràng khi cần hành vi nhất quán. Runner Linux thường dùng Bash; runner Windows thường dùng PowerShell. Không sao chép nguyên một dòng lệnh Bash sang `cmd` hoặc PowerShell mà không chuyển cú pháp.

## 19. Shell injection và nguyên tắc bảo mật

Command injection xảy ra khi dữ liệu bị hiểu thành cú pháp thực thi thay vì dữ liệu.

Ví dụ nguy hiểm:

~~~java
String script = "sh -c \"grep " + userPattern + " app.log\"";
new ProcessBuilder("sh", "-c", script).start();
~~~

Nếu `userPattern` chứa dấu nháy hoặc shell operators, nội dung có thể thay đổi command được thực thi.

Cách an toàn hơn:

~~~java
new ProcessBuilder(
        "grep",
        "--",
        userPattern,
        "app.log"
).start();
~~~

`--` là end-of-options marker được nhiều CLI hỗ trợ, giúp giá trị bắt đầu bằng `-` không bị hiểu nhầm là option. Hãy xác nhận chương trình đích hỗ trợ `--`; không phải mọi CLI đều có quy ước này.

Các nguyên tắc quan trọng:

- Ưu tiên `ProcessBuilder(List<String>)`.
- Không gọi shell nếu chỉ cần khởi chạy executable.
- Không ghép dữ liệu không tin cậy vào `sh -c`, `bash -c`, `cmd /c` hoặc `powershell -Command`.
- Validate option/value theo hợp đồng ứng dụng.
- Dùng allowlist executable và path nếu có thể.
- Không dùng `eval`.
- Không đưa secret vào command line vì process arguments có thể xuất hiện trong diagnostics/process listings.
- Khi target cần script, tạo script file với quyền truy cập giới hạn và truyền dữ liệu riêng qua file/stdin.

Quoting không thay thế validation. Một argument được quote đúng vẫn có thể khiến ứng dụng đích thực thi một chức năng nguy hiểm nếu value đó được truyền vào option không phù hợp.

## 20. Unicode và encoding

Quoting bảo vệ ranh giới arguments; encoding quyết định bytes hoặc code units được chuyển thành ký tự nào.

Với Java process:

- `String` lưu dữ liệu UTF-16.
- Windows command line dùng Unicode API khi khởi tạo process.
- POSIX arguments là byte strings; cách chuyển đổi phụ thuộc môi trường và encoding.
- stdout/stderr có encoding riêng; đừng mặc định mọi console dùng UTF-8 nếu chưa cấu hình.
- File argument/response có encoding theo tài liệu của công cụ.

Nếu CI có tiếng Việt, tiếng Nhật hoặc ký tự ngoài ASCII, test cả input lẫn output. Đặt encoding rõ cho compiler/resource:

~~~xml
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

Trong Java code, khi đọc output process, chọn charset đã thỏa thuận với chương trình con:

~~~java
String output = new String(
        process.getInputStream().readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
);
~~~

Không dùng charset mặc định một cách ngầm định nếu output được chuyển giữa runner Windows và Linux.

## 21. Đọc stdout, stderr và exit code của tiến trình con

Một process có thể chạy thành công nhưng ghi cảnh báo vào stderr; cũng có thể ghi kết quả vào stdout rồi kết thúc với exit code khác 0.

Đọc hai stream riêng:

~~~java
Process process = new ProcessBuilder(command).start();

byte[] stdout = process.getInputStream().readAllBytes();
byte[] stderr = process.getErrorStream().readAllBytes();
int exitCode = process.waitFor();
~~~

Đối với chương trình có thể ghi lượng output lớn, đọc stdout và stderr đồng thời hoặc redirect ra file. Nếu chỉ đọc một stream trong khi stream còn lại đầy buffer, tiến trình con có thể bị block và không kết thúc.

Gộp stderr vào stdout khi thứ tự log quan trọng:

~~~java
Process process = new ProcessBuilder(command)
        .redirectErrorStream(true)
        .start();
~~~

CI nên fail khi exit code khác 0, đồng thời lưu log và test report. Không suy luận build thành công chỉ từ một dòng `BUILD SUCCESS` nếu process cuối cùng trả exit code khác 0.

## 22. Các lỗi quoting thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Path có dấu cách bị chia | Argument không được quote ở shell layer | Quote cả giá trị tại shell đang dùng hoặc truyền một list element |
| `$HOME` biến mất | Bash/PowerShell mở rộng biến | Dùng single quotes cho literal hoặc truyền qua array |
| `&` chạy thành command khác | cmd/Bash/PowerShell hiểu `&` là toán tử | Quote/escape theo shell hoặc bỏ shell bằng ProcessBuilder |
| `*.jar` thành nhiều arguments | Shell glob expansion | Quote wildcard hoặc để Java launcher xử lý classpath wildcard |
| Dấu nháy literal bị mất trên Windows | Target parser coi quote là delimiter | Dùng escape theo Microsoft CRT khi đúng parser; test target |
| Backslash cuối path làm sai quote | Backslash trước quote đóng có ý nghĩa trong Windows CRT | Tránh path kết thúc bằng slash nếu không cần; nếu cần, kiểm thử parser cụ thể |
| Script chạy ở PS 7 nhưng lỗi PS 5.1 | Native argument passing khác version | Kiểm tra version/mode hoặc dùng `ProcessStartInfo.ArgumentList` trên PowerShell hiện đại |
| `cmd /c` hoạt động khác lệnh trực tiếp | Thêm một lớp cmd parsing | Bỏ `/c` nếu không cần shell syntax |
| ProcessBuilder không tạo pipe | ProcessBuilder không tự gọi shell | Dùng `startPipeline` hoặc nối streams trong Java |
| CI nhận sai ký tự tiếng Việt | Encoding khác giữa shell, file và process | Chỉ định UTF-8 và kiểm tra output encoding |
| Giá trị bắt đầu bằng `-` bị hiểu là option | CLI parse value như option | Dùng `--` nếu chương trình hỗ trợ hoặc truyền theo cú pháp `--name=value` |

## 23. Cách debug arguments thực tế

Khi command không chạy như mong muốn, in từng argument ở phía chương trình đích thay vì chỉ in command string phía gọi.

Ví dụ:

~~~java
for (int i = 0; i < args.length; i++) {
    System.out.printf("args[%d]=<%s>%n", i, args[i]);
}
~~~

Dùng dữ liệu kiểm thử bao gồm:

- Chuỗi có dấu cách.
- Chuỗi rỗng.
- Dấu nháy kép literal.
- Backslash ở giữa và cuối chuỗi.
- Đường dẫn có dấu cách.
- `&`, `|`, `;`, `$`, `%`, `!`, `*`.
- Chuỗi bắt đầu bằng dấu `-`.
- Unicode có dấu và ký tự ngoài ASCII.

So sánh giá trị mong đợi với giá trị nhận được từng index. Không chỉ so tổng số arguments vì một argument bị tách thành hai có thể vẫn tạo ra số lượng tình cờ giống nhau.

Với PowerShell, có thể dùng `Trace-Command -Name ParameterBinding` để xem cách bind arguments. Với Java, ghi log `ProcessBuilder.command()` chỉ cho biết list đầu vào; nó không chứng minh target đã nhận đúng arguments. Hãy dùng echo-args utility hoặc test child process.

## 24. Kiểm thử cross-platform trong CI

Một bộ test quoting nên chạy trên ít nhất một runner Windows và một runner Linux nếu sản phẩm hỗ trợ cả hai.

Matrix ví dụ:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]

runs-on: ${{ matrix.os }}
steps:
  - uses: actions/checkout@v7
  - uses: actions/setup-java@v6
    with:
      distribution: temurin
      java-version: '17'
  - name: Compile argument test
    shell: bash
    run: |
      javac --release 17 -d "out classes" ArgRoundTrip.java
      java -cp "out classes" ArgRoundTrip
~~~

Trong workflow thật, nếu dùng `shell: bash` trên Windows, runner cần Bash có sẵn. Nếu dự án muốn kiểm thử PowerShell và cmd cụ thể, tạo job riêng dùng `shell: pwsh` hoặc `shell: cmd`.

Kiểm thử cùng một tập dữ liệu trên các OS giúp phát hiện lỗi ở shell layer, process creation, path handling và target parser. Nếu chỉ chạy một lệnh build mẫu, các edge case như empty argument hoặc embedded quote có thể không được phát hiện.

## 25. Checklist trước khi viết script gọi Java

- Xác định shell thực tế: Bash, PowerShell, cmd.exe hay không có shell.
- Xác định executable đích và parser của nó.
- Giữ mỗi argument thành phần tử riêng; không ghép thành command string.
- Quote theo shell layer hiện tại, không copy cú pháp từ shell khác.
- Dùng `Path` và `File.pathSeparator` trong Java thay vì tự nối path.
- Với Windows, kiểm tra quote và backslash theo parser của target.
- Với Java launcher, cân nhắc `@argfile` cho command dài.
- Truyền payload phức tạp qua stdin hoặc file có encoding rõ ràng.
- Dùng `--` nếu CLI hỗ trợ và value có thể bắt đầu bằng `-`.
- Không đưa untrusted input vào `eval`, `sh -c`, `cmd /c` hoặc `powershell -Command`.
- Đọc stdout/stderr, kiểm tra exit code và tránh deadlock.
- Kiểm thử argument round-trip trên mọi OS/shell được hỗ trợ.
- Lưu lại phiên bản JDK, shell và runner khi chẩn đoán lỗi.

Quoting tham số không phải là một công thức escape áp dụng ở mọi nơi. Nó là việc bảo toàn dữ liệu qua từng parser trên đường đi từ script tới chương trình. Khi dùng argument arrays, hiểu sự khác nhau giữa shell và OS, và kiểm tra giá trị thực tế mà target nhận được, Java tooling có thể chạy nhất quán trên Windows, Linux và macOS.

## Tài liệu tham khảo

- Oracle Java SE 24 — [ProcessBuilder API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ProcessBuilder.html).
- Oracle JDK — [The java Command and Argument Files](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).
- Microsoft Learn — [PowerShell about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing).
- Microsoft Learn — [cmd Command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd).
- Microsoft Learn — [Parsing C Command-Line Arguments](https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments).
- GNU Bash Manual — [Quoting](https://www.gnu.org/software/bash/manual/html_node/Quoting.html).
- GNU Bash Manual — [Shell Syntax](https://www.gnu.org/software/bash/manual/bash.html).

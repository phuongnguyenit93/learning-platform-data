# Ảnh hưởng của shell, dấu cách và ký tự đặc biệt

Một lệnh chạy được khi gõ trong Terminal có thể không chạy khi đưa nguyên chuỗi đó vào `ProcessBuilder`. Nguyên nhân thường là Terminal đã nhờ một **bộ thông dịch lệnh (shell)** phân tích cú pháp, còn Java đang khởi chạy trực tiếp một chương trình.

Muốn truyền đối số đúng, cần tách ba lớp: cú pháp chuỗi Java, cách hệ điều hành khởi chạy tiến trình và cú pháp của shell hoặc chương trình đích. Bài này tập trung vào dấu cách, dấu nháy, ký tự đặc biệt và cách nhận biết lớp nào đang diễn giải chúng.

## 1. ProcessBuilder nhận chương trình và danh sách đối số

Cách dùng thông thường:

```java
// Đoạn cấu hình minh họa; chưa khởi chạy công cụ.
ProcessBuilder builder = new ProcessBuilder(
        "tool",
        "--input",
        "report final.txt"
);
```

Ý định là chạy chương trình `tool` với hai đối số: `--input` và `report final.txt`.

Dấu cách bên trong phần tử thứ ba thuộc giá trị của **một đối số**. Không cần thêm dấu nháy bao quanh chỉ vì giá trị chứa dấu cách.

Ngược lại:

```java
// Sai nếu ý định là chạy tool với hai đối số riêng.
ProcessBuilder builder = new ProcessBuilder(
        "tool --input report final.txt"
);
```

Ở đây danh sách chỉ có một phần tử. Java không cung cấp một shell để tự hiểu đó là tên chương trình và các đối số. Thao tác khởi chạy có thể thất bại vì phần tử đầu không phải tên tệp thực thi mong muốn.

Tài liệu [ProcessBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html) mô tả lệnh dưới dạng danh sách chuỗi và lưu ý cách ánh xạ xuống hệ điều hành phụ thuộc nền tảng. Vì vậy, dùng các phần tử riêng là cách thể hiện đúng ý định, đồng thời vẫn phải kiểm tra quy tắc của chương trình đích trên nền tảng hỗ trợ.

## 2. Khi nào có shell?

### Khởi chạy trực tiếp

```text
Java
  -> chương trình thực thi
      -> chương trình nhận đối số
```

Ví dụ, khi chạy trình khởi động Java, một công cụ nén hoặc một chương trình xử lý ảnh bằng đường dẫn thực thi, không có bước tự động phân tích toán tử shell của `ProcessBuilder`.

### Chủ động gọi shell

```text
Java
  -> shell
      -> shell phân tích đoạn lệnh
          -> chương trình hoặc lệnh nội bộ của shell
```

Các dạng gọi thường gặp:

| Nền tảng/công cụ | Phần tử chương trình | Các đối số mang mã lệnh |
| --- | --- | --- |
| Hệ POSIX có sh | `/bin/sh` | `-c`, chuỗi mã lệnh |
| Windows cmd | `cmd.exe` | `/d`, `/c`, chuỗi mã lệnh |
| PowerShell đã cài | `pwsh` | `-NoProfile`, `-Command`, chuỗi mã lệnh |

Đường dẫn shell và chương trình có sẵn hay không phụ thuộc máy. Không mặc nhiên coi `sh`, `cmd.exe` và PowerShell là cùng ngôn ngữ.

Lệnh nội bộ như `cd` không nhất thiết có tệp thực thi độc lập để Java gọi. Nếu mục đích là đặt thư mục làm việc cho tiến trình con, cấu hình `ProcessBuilder.directory(...)` trực tiếp thay vì chạy một lệnh `cd` rồi mong nó thay đổi thư mục của Java.

Tệp script hoặc trình bao của công cụ cũng có thể gọi thêm bộ thông dịch. Cần biết **chương trình thực sự đang chạy**, không chỉ nhìn tên biến chứa lệnh.

## 3. Ký tự đặc biệt: ý nghĩa phụ thuộc bên đọc

Khi truyền trực tiếp cho một chương trình chỉ nhận chúng như văn bản, các chuỗi dưới đây không tự biến thành thao tác shell:

| Giá trị đối số | ProcessBuilder không tự làm gì |
| --- | --- |
| `a b` | Không tự tách thành hai phần tử |
| `*.txt` | Không tự liệt kê các tệp khớp mẫu |
| `$HOME` | Không tự thay bằng giá trị biến |
| `%TEMP%` | Không tự mở rộng biến theo cmd |
| `a;b` | Không tự chạy hai lệnh |
| `one|two` | Không tự tạo đường ống |
| `>` | Không tự chuyển stdout vào tệp |
| `~` | Không tự đổi thành thư mục người dùng |

Điều này chỉ nói về việc `ProcessBuilder` không cung cấp cú pháp shell. Chương trình đích vẫn có thể tự hiểu ký tự đặc biệt. Ví dụ, một công cụ tìm kiếm có thể coi đối số là biểu thức chính quy; một công cụ khác có thể tự mở rộng mẫu tên tệp.

Nếu chương trình đích là shell, các toán tử trên có thể trở thành cú pháp thực thi theo ngôn ngữ của shell đó.

## 4. Dấu nháy trong mã Java khác dấu nháy của shell

Trong mã Java:

```java
String first = "report final.txt";
String second = "\"report final.txt\"";
```

Giá trị của `first` là:

```text
report final.txt
```

Giá trị của `second` chứa thêm hai dấu nháy kép thực sự:

```text
"report final.txt"
```

Dấu nháy bao quanh literal Java chỉ đánh dấu đầu và cuối chuỗi trong **mã nguồn**. Chúng không được truyền đi. Dấu nháy viết bằng `\"` là dữ liệu bên trong chuỗi.

Khi chạy trực tiếp, hãy truyền đường dẫn chứa dấu cách bằng đúng một phần tử, không tự bọc nháy theo thói quen gõ Terminal. Các dấu nháy thêm vào có thể bị chương trình đích nhận như dữ liệu hoặc bị cơ chế phân tích lệnh của nền tảng xử lý theo cách khác ý định.

Tương tự, trong mã nguồn Java, đường dẫn Windows cần escape dấu gạch chéo ngược:

```java
String path = "C:\\work folder\\report.txt";
```

Giá trị thực có một dấu gạch chéo ngược ở mỗi vị trí. Đây là quy tắc literal Java, không phải quy tắc escape của cmd hay PowerShell. Nếu đường dẫn đến từ `Path`, tệp cấu hình hoặc đầu vào đã là chuỗi tại thời điểm chạy, không áp dụng thêm một lượt escape mã nguồn Java.

## 5. Thực nghiệm: quan sát chính đối số tiến trình con nhận

Lưu thành **ProcessArgumentsDemo.java**. Chương trình cha chạy lại chính lớp này ở chế độ con, sử dụng trình khởi động Java trong JDK hiện tại.

Không cần cài một công cụ echo riêng và không dựa vào lệnh echo của shell.

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class ProcessArgumentsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            System.out.println("argument count = " + (args.length - 1));
            for (int i = 1; i < args.length; i++) {
                System.out.println("arg[" + (i - 1) + "]=<" + args[i] + ">");
            }
            return;
        }

        boolean windows = System.getProperty("os.name").startsWith("Windows");
        String java = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java"
        ).toString();

        List<String> command = new ArrayList<>(List.of(
                java,
                "-cp",
                System.getProperty("java.class.path"),
                ProcessArgumentsDemo.class.getName(),
                "--child"
        ));

        command.addAll(List.of(
                "a b",
                "*.txt",
                "$HOME",
                "%TEMP%",
                "one|two",
                ">",
                "a;b",
                "",
                "C:\\work folder\\report.txt"
        ));

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        process.getOutputStream().close();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }

        int status = process.waitFor();
        System.out.println("exit = " + status);
        if (status != 0) {
            throw new IllegalStateException("Child process failed");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 ProcessArgumentsDemo.java
java ProcessArgumentsDemo
```

Stdout:

```text
argument count = 9
arg[0]=<a b>
arg[1]=<*.txt>
arg[2]=<$HOME>
arg[3]=<%TEMP%>
arg[4]=<one|two>
arg[5]=<>>
arg[6]=<a;b>
arg[7]=<>
arg[8]=<C:\work folder\report.txt>
exit = 0
```

Ở dòng `arg[5]=<>>`, cặp dấu `<...` và `>` ngoài cùng là khung trình bày của chương trình; giá trị bên trong là đúng một ký tự `>`.

Đối số rỗng vẫn được nhận như một đối số riêng. Các chuỗi chỉ biến môi trường, ký tự đại diện và đường ống đều giữ nguyên vì chương trình con Java chỉ in chúng.

Chương trình đọc stdout trong khi tiến trình con chạy rồi mới đợi kết thúc. Nó gộp stderr vào stdout để ví dụ chỉ cần đọc một luồng. Với tiến trình bất kỳ có thể chạy lâu hoặc tạo dữ liệu lớn, cần thiết kế thêm giới hạn thời gian và xử lý luồng phù hợp; phần này không thay đổi quy tắc truyền đối số. Tài liệu [Process](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html) giải thích vì sao bỏ đọc các luồng có thể khiến tiến trình bị chặn.

## 6. Nếu cần chuyển hướng hoặc đường ống

Một lỗi thường gặp là đưa toán tử shell thành phần tử:

```java
// Minh họa cấu hình sai nếu muốn chuyển stdout vào out.txt.
ProcessBuilder builder = new ProcessBuilder(
        "tool", "input.txt", ">", "out.txt"
);
```

Ở đây `>` và `out.txt` chỉ là đối số cho `tool`, trừ khi chính công cụ có quy tắc riêng.

Nếu mục đích chỉ là chuyển stdout vào tệp, dùng API:

```java
// Đoạn cấu hình; cần import java.nio.file.Path.
ProcessBuilder builder = new ProcessBuilder("tool", "input.txt");
builder.redirectOutput(Path.of("out.txt").toFile());
```

Đường dẫn `out.txt` tương đối được giải quyết theo môi trường chạy; nên chọn đường dẫn rõ ràng trong ứng dụng thật. Chuyển hướng như trên sẽ ghi đè tệp đích khi tiến trình được khởi chạy; nếu muốn nối thêm phải chọn chế độ append phù hợp.

Nếu cần kết nối stdout tiến trình này sang stdin tiến trình khác, Java hiện đại có `ProcessBuilder.startPipeline` từ Java 9. Cũng có thể chủ động nối luồng. Không bắt buộc phải đưa ký tự `|` vào chuỗi shell chỉ để biểu đạt một đường ống.

## 7. Khi shell thực sự cần thiết

Có thể cần shell khi thực thi một script đã có, một lệnh nội bộ hoặc cú pháp shell là một phần của yêu cầu.

Điểm thay đổi là: chuỗi sau `-c`, `/c` hoặc `-Command` có thể là **mã lệnh**, không còn chỉ là dữ liệu thông thường.

### Shell kiểu POSIX

Với các shell như sh hoặc Bash, dấu nháy và phép mở rộng ảnh hưởng đến cách tách từ, mở rộng biến và mẫu tên tệp. Dấu nháy kép không vô hiệu hóa mọi phép mở rộng, nên “bọc trong nháy kép” không phải quy tắc đủ cho mọi chuỗi. Xem [Bash Shell Expansions](https://www.gnu.org/s/bash/manual/html_node/Shell-Expansions.html).

Một cách truyền dữ liệu vào mã shell cố định là dùng tham số vị trí:

```java
// Đoạn dùng riêng trên hệ có /bin/sh, bên trong một phương thức.
// input là dữ liệu đã có; đoạn script được giữ cố định.
ProcessBuilder builder = new ProcessBuilder(
        "/bin/sh",
        "-c",
        "printf '%s\\n' \"$1\"",
        "argument-demo",
        input
);
```

Sau `-c`, `argument-demo` làm giá trị `$0`, còn `input` làm `$1`. Dữ liệu không được nối trực tiếp vào mã script. Cặp nháy quanh `"$1"` giữ giá trị mở rộng như một đối số cho printf; ký tự `|` trong giá trị đó không tự trở thành toán tử shell mới.

Đây là ví dụ có điều kiện nền tảng, không phải lệnh dùng nguyên xi trên mọi Windows. Cách này cũng không áp dụng tự động cho cmd hoặc PowerShell.

### cmd trên Windows

`cmd.exe /c` phân tích chuỗi lệnh theo quy tắc của cmd. Các ký tự như `&`, `|` và `>` có ý nghĩa đặc biệt; `%NAME%` là dạng mở rộng biến thường gặp. Tham số `/d` vô hiệu hóa các lệnh AutoRun của cmd, nhưng không biến chuỗi sau `/c` thành dữ liệu thuần. Xem [cmd](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd).

Lệnh nội bộ `dir` cần cmd nếu không có một chương trình khác thay thế, còn một tệp thực thi thông thường thường có thể được khởi chạy trực tiếp.

### PowerShell

PowerShell có quy tắc phân tích và mở rộng riêng. `-Command` nhận mã PowerShell; cú pháp như biến bắt đầu bằng `$` hoặc biểu thức nhúng có thể được diễn giải. Không mang hàm escape cho Bash hay cmd sang PowerShell. Xem [PowerShell about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing?view=powershell-7.5).

Nếu cần một script ổn định, cân nhắc một tệp script với tham số rõ ràng và kiểm tra cách truyền tham số của phiên bản PowerShell đang dùng.

## 8. Windows còn có lớp phân tích dòng lệnh của chương trình đích

Trên hệ POSIX, giao diện tiến trình thường nhận một mảng đối số. Trên Windows, cơ chế khởi chạy và chương trình con có thể làm việc qua một dòng lệnh rồi phân tích lại thành đối số. JDK phải ánh xạ danh sách Java vào cơ chế nền tảng.

Do đó, ngay cả khi không gọi shell, không nên suy rộng rằng mọi tệp thực thi Windows đều xử lý dấu nháy và gạch chéo ngược giống nhau. Quy tắc của Microsoft C runtime là một ví dụ cụ thể, không phải luật của tất cả chương trình Windows. Xem [Parsing C command-line arguments](https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments?view=msvc-170).

Hướng thực hành:

- Đường dẫn chương trình là một phần tử riêng, không gồm sẵn đối số.
- Mỗi đối số logic là một phần tử riêng.
- Không tự nối tất cả thành chuỗi để “giúp Windows tách”.
- Kiểm tra giá trị thực chương trình đích nhận, nhất là đối số rỗng, dấu nháy bên trong và đường dẫn có dấu cách.
- Với tệp batch hoặc công cụ bọc nhiều lớp, kiểm tra cả bộ thông dịch mà nó sử dụng.

Ví dụ thực nghiệm của bài dùng Java làm chương trình đích nên có thể quan sát và kiểm tra chính xác đối số. Khi thay bằng một công cụ khác, giữ cùng phương pháp kiểm chứng nhưng theo tài liệu của công cụ đó. Không thêm dấu nháy kép bên trong một đối số rồi mặc nhiên coi nó luôn được giữ nguyên trên mọi hệ điều hành; cần kiểm tra riêng trường hợp đó.

## 9. Tránh nhầm dữ liệu với mã lệnh

Nếu nối một tên tệp nhận từ bên ngoài vào chuỗi shell, các ký tự trong tên có thể làm thay đổi cấu trúc lệnh. Đây là lý do tách chương trình và đối số có giá trị về cả tính đúng đắn lẫn an toàn.

Tuy nhiên, tách đối số chưa thay thế kiểm tra nghiệp vụ. Một tên tệp bắt đầu bằng `--` có thể bị công cụ đích hiểu là tùy chọn. Khi công cụ hỗ trợ, dùng dấu kết thúc tùy chọn `--` ở vị trí thích hợp; không giả định mọi công cụ đều hỗ trợ quy ước đó.

Cũng cần chọn chương trình thực thi được phép chạy. Nếu người dùng được tự chọn phần tử đầu tiên hoặc chọn tùy chọn nguy hiểm, việc không có shell không tự khiến thao tác đúng với phạm vi ứng dụng.

Không cần một hàm “escape mọi shell”. Cần xác định dữ liệu đi vào lớp nào, ưu tiên truyền trực tiếp khi đủ đáp ứng yêu cầu, và dùng đúng cơ chế tham số của bộ thông dịch khi thực sự gọi nó.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| Một chuỗi chứa cả lệnh và đối số | Không tìm thấy chương trình | Tách thành danh sách |
| Tách bằng `split(" ")` | Đường dẫn có khoảng trắng bị vỡ | Xây danh sách ngay từ dữ liệu có cấu trúc |
| Tự thêm dấu nháy cho mọi đối số | Chương trình nhận dư nháy hoặc sai đường dẫn | Truyền đúng giá trị, kiểm tra nền tảng |
| Đưa `>` hoặc `|` vào danh sách | Công cụ nhận chúng như dữ liệu | Dùng redirect/pipeline hoặc shell chủ động |
| Trông đợi `$HOME` hoặc `%TEMP%` tự mở rộng | Nhận nguyên văn tên biến | Lấy giá trị môi trường trong Java hoặc dùng shell có chủ đích |
| Escape theo shell khác | Kết quả khác giữa hệ điều hành | Xác định chính xác bộ thông dịch |
| Chỉ xem chuỗi log đã nối | Không biết ranh giới đối số | Ghi số thứ tự và độ dài từng đối số khi kiểm tra |

Thực hành:

1. Thêm một đối số chỉ chứa hai dấu cách vào chương trình và quan sát nó khác chuỗi rỗng.
2. Thay giá trị cuối bằng một đường dẫn có dấu cách; giữ nguyên một phần tử và kiểm tra chương trình con.
3. Giải thích vì sao `"a b"` trong mã nguồn không có nghĩa là truyền dấu nháy, còn `"\"a b\""` có chứa dấu nháy.
4. Chọn cách cấu hình stdout ra tệp mà không cần shell.
5. Với công cụ thật của bạn, xác định phần nào là chương trình, phần nào là dữ liệu đối số, phần nào là mã shell nếu có.

Điểm cần nắm là **một ký tự chỉ trở thành cú pháp khi một lớp cụ thể diễn giải nó như cú pháp**. Giữ rõ ranh giới các lớp giúp việc truyền lệnh có thể dự đoán và kiểm tra.

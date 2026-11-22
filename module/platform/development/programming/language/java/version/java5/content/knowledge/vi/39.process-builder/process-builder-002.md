# Danh sách lệnh và đối số tách biệt

## 1. `ProcessBuilder` cần cấu trúc, không chỉ một câu lệnh nhìn giống terminal

Khi gõ lệnh trong terminal, ta thường thấy một dòng văn bản:

```shell
java -version
```

Nhưng một dòng terminal đã được môi trường dòng lệnh xử lý. Khi tạo tiến trình từ Java, cần mô tả rõ chương trình được gọi và dữ liệu đối số mà chương trình đó sẽ nhận.

Trong cách dùng thông thường trên Windows/Linux/macOS:

```text
command[0]     = đường dẫn hoặc tên chương trình thực thi
command[1..n]  = các đối số, theo đúng thứ tự
```

Ví dụ minh họa cấu trúc:

```java
ProcessBuilder builder = new ProcessBuilder("java", "-version");
```

Đoạn trên chỉ tạo cấu hình; chưa khởi chạy tiến trình cho đến khi gọi `start()`. Nó giả định hệ điều hành tìm được chương trình `java`. Chương trình đầy đủ trong bài sẽ dùng đường dẫn tới Java của JVM hiện tại để tránh phụ thuộc ví dụ vào tên lệnh trên PATH.

API nhận danh sách chuỗi và cách ánh xạ cụ thể phụ thuộc hệ điều hành, như [Java ProcessBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html) mô tả. Vì vậy nên kiểm tra hành vi với chương trình đích và nền tảng thực tế, đặc biệt khi đối số có dấu nháy hoặc dấu gạch chéo ngược.

## 2. Mỗi đối số có ranh giới riêng

Giả sử cần truyền cho một công cụ hai dữ liệu: `--input` và tên tệp `report final.txt`.

Cấu trúc đúng theo hợp đồng giả định của công cụ:

```text
[0] /path/to/tool
[1] --input
[2] report final.txt
```

Tên tệp là một chuỗi có khoảng trắng, nhưng chỉ là một đối số. Không tách nó thành `report` và `final.txt`.

So sánh:

| Danh sách | Ý nghĩa |
| --- | --- |
| `["tool", "--input", "report final.txt"]` | Chương trình nhận hai đối số |
| `["tool", "--input", "report", "final.txt"]` | Chương trình nhận ba đối số |
| `["tool --input report final.txt"]` | Một phần tử chứa toàn bộ chuỗi; không phải mô hình chương trình + đối số đã tách |

Ví dụ cuối không yêu cầu Java tự phân tích khoảng trắng giống terminal. Thông thường nó dẫn tới việc tìm một tên chương trình không đúng và thất bại lúc khởi chạy. Cách báo lỗi cụ thể phụ thuộc nền tảng.

Đối số rỗng cũng có ý nghĩa riêng. `""` trong danh sách là một đối số có độ dài 0; bỏ nó đi là thay đổi số lượng và vị trí các đối số. Chương trình đích có thể phân biệt rõ “không truyền giá trị” và “truyền giá trị rỗng”.

## 3. Không thêm dấu nháy chỉ để bọc một tên có khoảng trắng

Trong mã Java:

```java
String fileName = "report final.txt";
```

Hai dấu nháy trong mã nguồn xác định một `String`; chúng không phải ký tự nằm trong giá trị. Khi thêm `fileName` làm một phần tử của danh sách, ranh giới đối số đã được mô tả.

Không tự đổi nó thành giá trị có thêm hai ký tự `"` để mô phỏng cách nhập trong terminal. Làm vậy có thể truyền dấu nháy thành dữ liệu hoặc làm tương tác với quy tắc phân tích của chương trình đích trở nên khác.

Điều tương tự áp dụng cho đường dẫn tới chương trình. Nếu đường dẫn chứa khoảng trắng, đưa toàn bộ đường dẫn vào phần tử đầu tiên; không chèn thêm một lớp dấu nháy quanh đường dẫn chỉ vì có khoảng trắng.

Cần phân biệt ba lớp:

1. Cú pháp chuỗi Java: viết `\\` để biểu diễn một dấu `\` trong chuỗi thường.
2. Danh sách đối số: mỗi phần tử xác định một dữ liệu được truyền.
3. Cú pháp của chương trình đích: chương trình có thể tự diễn giải tùy chọn, mẫu tìm kiếm hoặc các ký hiệu khác.

Dấu nháy thật sự có thể là dữ liệu cần truyền, nhưng khi đó phải có yêu cầu cụ thể từ công cụ nhận. Đừng áp dụng một hàm “escape shell” chung cho tất cả đối số gọi trực tiếp.

## 4. Gọi trực tiếp khác gọi shell

`ProcessBuilder` không tự thêm `cmd.exe`, PowerShell hoặc `sh` để diễn giải danh sách.

Trong ví dụ tiến trình con Java ở phần sau:

- `a;b` là một đối số.
- `x|y` là một đối số.
- Không có lệnh thứ hai được chạy chỉ vì chuỗi chứa `;`.
- Không có pipeline được tạo chỉ vì chuỗi chứa `|`.

Tương tự, đừng mong các biểu thức như `*.txt`, `$HOME` hoặc ký hiệu `>` tự được mở rộng theo quy tắc shell khi gọi trực tiếp một chương trình. Chương trình đích có thể tự có quy tắc xử lý riêng, nhưng đó là hành vi của chương trình, không phải một shell ẩn do Java thêm vào.

Nếu chủ động gọi một shell và đưa cho nó chuỗi mã lệnh, chuỗi ấy được shell phân tích theo cú pháp riêng. Lúc đó vấn đề nối chuỗi, dấu nháy và chèn lệnh quay trở lại. Không dùng shell chỉ vì muốn gọi một chương trình có vài đối số.

Với tác vụ Java làm được trực tiếp bằng API, chẳng hạn thao tác tệp, cân nhắc dùng API thay vì khởi chạy công cụ bên ngoài. Với chuyển hướng đầu ra hoặc pipeline, `ProcessBuilder` cũng có API riêng; không cần mặc định ghép `>` hay `|` vào một chuỗi shell.

## 5. Chương trình đầy đủ: tiến trình con in những đối số thật sự nhận được

Ví dụ sau dùng chính Java làm chương trình đích. Chế độ `--child` in đối số, còn chế độ bình thường khởi tạo một JVM con. Nó không phụ thuộc `echo` hay một lệnh tích hợp của shell.

Lưu thành `CommandArgumentsDemo.java`, dùng JDK 17 trở lên:

```java
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class CommandArgumentsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            System.out.println("count=" + (args.length - 1));
            for (int i = 1; i < args.length; i++) {
                System.out.println("arg[" + (i - 1) + "]=<" + args[i] + ">");
            }
            return;
        }

        String executableName = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String javaExecutable = Path.of(
                System.getProperty("java.home"), "bin", executableName).toString();

        List<String> command = List.of(
                javaExecutable,
                "-cp",
                System.getProperty("java.class.path"),
                CommandArgumentsDemo.class.getName(),
                "--child",
                "report final.txt",
                "--title=Hello Java",
                "a;b",
                "x|y",
                "");

        Process process = new ProcessBuilder(command).inheritIO().start();
        if (!process.waitFor(10, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            throw new IllegalStateException("Child process timed out");
        }
        System.out.println("exit=" + process.exitValue());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CommandArgumentsDemo.java
java -cp . CommandArgumentsDemo
```

Stdout:

```text
count=5
arg[0]=<report final.txt>
arg[1]=<--title=Hello Java>
arg[2]=<a;b>
arg[3]=<x|y>
arg[4]=<>
exit=0
```

Giải thích danh sách:

| Phần | Vai trò |
| --- | --- |
| `javaExecutable` | Chương trình Java của JVM hiện tại |
| `-cp` và giá trị tiếp theo | Cấu hình classpath cho Java launcher |
| `CommandArgumentsDemo.class.getName()` | Lớp có `main()` mà JVM con sẽ chạy |
| `--child` | Đánh dấu chế độ con, tránh khởi tạo lặp vô hạn |
| Năm phần tử còn lại | Dữ liệu thử nghiệm để in ra |

Java launcher dùng các phần đầu để tìm lớp. Phương thức `main()` của lớp con chỉ nhận các phần từ `--child` trở đi; nó không nhận lại đường dẫn chương trình và `-cp` như dữ liệu ứng dụng.

Vì vậy `count=5` đã trừ phần tử đánh dấu `--child`. Dấu `<>` trong dòng cuối chứng minh đối số rỗng vẫn tồn tại; đây là ký hiệu do chương trình thêm khi in, không phải dữ liệu được truyền.

`--title=Hello Java` vẫn là một đối số. Dấu `=` không làm `ProcessBuilder` tách nó; việc ứng dụng con có coi đó là tùy chọn hay không do chính ứng dụng quyết định. Ở đây tiến trình con chỉ in, không phân tích tùy chọn.

`inheritIO()` giúp đầu ra của tiến trình con hiện trực tiếp. Thời hạn chờ 10 giây giới hạn thời gian ví dụ chạy; đây là phần hỗ trợ cho minh chứng, không phải mô hình quản lý tiến trình đầy đủ cho mọi ứng dụng.

Chương trình giữ nguyên thư mục làm việc mặc định, nên classpath tương đối như `.` trong lệnh chạy vẫn được hiểu từ cùng thư mục. Nếu đổi thư mục làm việc của tiến trình con, phải xem lại các đường dẫn tương đối, gồm cả classpath.

## 6. Tạo danh sách có điều kiện mà vẫn giữ ranh giới

Khi một tùy chọn chỉ xuất hiện trong một số trường hợp, thêm đúng từng phần tử thay vì nối một chuỗi dài:

```java
List<String> command = new java.util.ArrayList<>();
command.add(executable);
if (verbose) {
    command.add("--verbose");
}
command.add("--input");
command.add(inputFile);
```

Đây là đoạn minh họa cần các biến `executable`, `verbose` và `inputFile`; nó chưa tự khởi chạy được. Các tên tùy chọn chỉ có nghĩa nếu công cụ đích hỗ trợ chúng.

Không dùng `String.join(" ", command).split(" ")` để chuyển qua lại. Phép ghép làm mất thông tin ranh giới: một đối số `report final.txt` và hai đối số `report`, `final.txt` có thể tạo dòng nhìn giống nhau. Dùng `split("\\s+")` cũng không khôi phục đầy đủ các quy tắc dấu nháy và đối số rỗng.

Nếu đầu vào của ứng dụng là một cấu hình, thiết kế cấu hình giữ sẵn danh sách chương trình/đối số hoặc các trường nghiệp vụ riêng. Đừng bắt người dùng nhập một dòng shell rồi tự viết bộ phân tích tạm bằng cách tách khoảng trắng.

## 7. Tách đối số giúp giảm lỗi, nhưng vẫn cần hiểu tùy chọn của công cụ

Gọi trực tiếp với danh sách là cách giữ cấu trúc rõ ràng và tránh biến dữ liệu thành cú pháp shell. Tuy nhiên, công cụ đích vẫn phân tích đối số theo quy tắc của nó.

Ví dụ, một dữ liệu bắt đầu bằng `--` có thể bị công cụ hiểu là tùy chọn thay vì tên tệp. Đây là vấn đề chèn đối số hoặc chèn tùy chọn, khác với việc chạy thêm lệnh shell. [OWASP OS Command Injection Defense](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html) phân biệt ranh giới tham số và yêu cầu kiểm tra dữ liệu đầu vào.

Khi áp dụng:

- Cố định hoặc giới hạn chương trình được phép chạy.
- Xây dựng các tùy chọn được phép từ logic ứng dụng.
- Kiểm tra dữ liệu theo nghiệp vụ và hợp đồng của công cụ.
- Chỉ dùng dấu phân cách `--` để kết thúc tùy chọn khi công cụ đó có tài liệu hỗ trợ.
- Tránh nhận nguyên danh sách tùy chọn tùy ý từ một nguồn không đáng tin rồi chuyển thẳng sang công cụ đặc quyền.

Những điểm này không đòi hỏi phải loại bỏ mọi khoảng trắng hoặc ký tự đặc biệt. Một tên tệp hợp lệ có khoảng trắng vẫn cần được xử lý đúng như một dữ liệu duy nhất.

## 8. Cách kiểm chứng và lỗi thường gặp

Khi nghi ngờ đối số bị tách sai, in riêng chỉ số và giá trị như tiến trình con trong ví dụ. Một dòng log ghép tất cả phần tử bằng dấu cách thường làm mất bằng chứng ranh giới.

Không in bí mật như mật khẩu hoặc token chỉ để gỡ lỗi. Có thể in số lượng, tên trường và giá trị đã che phần nhạy cảm.

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không tìm thấy chương trình | Phần tử đầu có chứa cả câu lệnh hoặc đường dẫn sai |
| Tên tệp bị tách thành hai phần | Ứng dụng tự `split()` dữ liệu hoặc thêm sai phần tử |
| Công cụ nhận ký tự nháy lạ | Tự bọc dấu nháy theo thói quen terminal |
| Không có pipeline hoặc tệp đầu ra mong muốn | Đưa `\|`/`>` như đối số rồi mong shell tự diễn giải |
| Một tên tệp bị hiểu thành tùy chọn | Chưa xét cú pháp tùy chọn của chương trình đích |
| Mất đối số rỗng | Bỏ chuỗi rỗng hoặc ghép/tách lại danh sách |

Tự kiểm tra:

1. `["tool", "a b"]` và `["tool", "a", "b"]` có tương đương không?
2. Vì sao không cần thêm hai ký tự nháy vào chuỗi `"report final.txt"` chỉ để giữ khoảng trắng?
3. Trong ví dụ, vì sao `x|y` không tạo pipeline?
4. Nếu dùng `cmd.exe /c` hoặc `sh -c`, phần chuỗi được giao cho shell có còn chỉ là dữ liệu của một chương trình thông thường không?

Đáp án: (1) không, số đối số khác nhau; (2) một phần tử danh sách đã thể hiện ranh giới; (3) tiến trình Java con chỉ nhận nó như một đối số, không có shell diễn giải; (4) không, shell sẽ phân tích chuỗi theo cú pháp riêng.

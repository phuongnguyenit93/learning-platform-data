# Chuyển hướng đầu vào, đầu ra và lỗi ở mức tiến trình trong Java I/O

## 1. Ba kênh chuẩn của một tiến trình

Khi một chương trình Java chạy, nó thường nhận được ba kênh giao tiếp chuẩn do môi trường khởi chạy chuẩn bị:

| Kênh | Tên | File descriptor thông dụng trên POSIX | API Java | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Standard input | stdin | 0 | **System.in**, kiểu InputStream | Đọc dữ liệu vào |
| Standard output | stdout | 1 | **System.out**, kiểu PrintStream | Ghi kết quả bình thường |
| Standard error | stderr | 2 | **System.err**, kiểu PrintStream | Ghi lỗi hoặc thông tin chẩn đoán |

Khi khởi chạy trực tiếp từ terminal, stdin thường nhận dữ liệu từ bàn phím; stdout và stderr thường cùng hiện trong terminal. Nhưng **đích của hai luồng xuất vẫn độc lập về mặt logic**. Shell hoặc tiến trình cha có thể nối riêng mỗi luồng đến file, pipe, terminal hay dịch vụ thu thập log.

**Chuyển hướng I/O ở mức tiến trình (process redirection)** nghĩa là đổi nguồn stdin hoặc đích stdout/stderr của một tiến trình. Nếu môi trường chuyển hướng stdout vào file, lệnh **System.out.println(...)** trong Java vẫn được gọi như cũ; nội dung sẽ tới file thay vì màn hình.

~~~text
                 +-------------------------+
input.txt ------>| stdin   System.in       |
                 |                         |
                 |     Java process        |
                 |                         |
output.txt <-----| stdout  System.out      |
error.txt  <-----| stderr  System.err      |
                 +-------------------------+
~~~

**Tại sao phải tách stdout và stderr?** Khi chương trình tạo dữ liệu đầu ra cho công cụ khác xử lý (ví dụ JSON, CSV, tên file, mã kết quả), những dòng lỗi được in lẫn vào stdout có thể khiến bên đọc không phân tích được. Tách stderr giúp lấy kết quả thuần từ stdout và vẫn theo dõi thông báo chẩn đoán.

## 2. Chuyển hướng bằng shell

Trên **Bash/sh của Linux và macOS** và **cmd.exe của Windows**, những toán tử quen thuộc có ý nghĩa:

| Toán tử | Hành động |
| --- | --- |
| **< input.txt** | Nối stdin của chương trình từ file |
| **> output.txt** hoặc **1> output.txt** | Nối stdout vào file; thường tạo mới hoặc ghi đè file cũ |
| **>> output.txt** | Ghi nối thêm stdout vào file |
| **2> error.txt** | Nối stderr vào file; thường tạo mới hoặc ghi đè file cũ |
| **2>> error.txt** | Ghi nối thêm stderr |
| **> both.txt 2>&1** | Chuyển stdout vào file, rồi nối stderr với đích stdout hiện tại |
| **2> error.txt > output.txt** | Chuyển hai luồng tới hai file riêng |

Đối với ký hiệu **0, 1, 2**, đây là các số file descriptor được shell sử dụng: 0 là stdin, 1 là stdout, 2 là stderr. Toán tử **2>&1** có nghĩa là sao chép đích hiện tại của stdout cho stderr; nó không phải thao tác nối nội dung hai String trong Java.

### Thứ tự chuyển hướng rất quan trọng

~~~bash
java Example > combined.log 2>&1
~~~

Shell xử lý từ trái sang phải: trước tiên stdout hướng đến combined.log, sau đó stderr nối cùng đích đó. Cả kết quả và lỗi đều có thể vào một file.

~~~bash
java Example 2>&1 > only-stdout.log
~~~

Ở lệnh thứ hai, stderr được nối với **đích stdout ban đầu** trước khi stdout hướng vào only-stdout.log. Nếu đích ban đầu là terminal, lỗi vẫn có thể hiện ở terminal. Hai lệnh **không tương đương**.

Khi cùng chuyển vào một file, không nên dựa vào thứ tự xen kẽ chính xác của từng dòng stdout và stderr trong mọi tình huống: hai luồng có bộ đệm và lịch trình ghi độc lập, và công cụ thu thập log cũng có thể ảnh hưởng thứ tự quan sát.

## 3. Chương trình Java 17+ dùng cả ba luồng

Tạo file **StandardStreamsDemo.java**, lưu mã nguồn UTF-8:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class StandardStreamsDemo {
    public static void main(String[] args) throws IOException {
        BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));

        String line = input.readLine();

        if (line == null) {
            System.out.println("OUT:<EOF>");
        } else {
            System.out.println("OUT:" + line);
        }
        System.err.println("ERR:diagnostic");
    }
}
~~~

Giải thích:

- **System.in** cung cấp byte đầu vào. InputStreamReader giải mã byte thành ký tự theo UTF-8; BufferedReader cung cấp **readLine()**.
- Nếu stdin đã kết thúc mà chưa có dòng nào, **readLine() trả null**, chương trình in OUT:<EOF>.
- Kết quả hoặc trạng thái vào stdout qua System.out; thông điệp chẩn đoán vào stderr qua System.err.
- Chương trình đọc đúng **một dòng** rồi kết thúc, phù hợp để thử chuyển hướng từ file. Ví dụ không chủ động đóng System.in để tránh đóng kênh chuẩn khi chương trình khác cần dùng tiếp.

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StandardStreamsDemo.java
~~~

Trên **Bash/sh**:

~~~bash
printf 'xin chao\n' > input.txt
java StandardStreamsDemo < input.txt > output.txt 2> error.txt
cat output.txt
cat error.txt
~~~

Trên **cmd.exe**:

~~~bat
echo xin chao>input.txt
java StandardStreamsDemo < input.txt > output.txt 2> error.txt
type output.txt
type error.txt
~~~

Cả hai cách đều tạo đầu vào là một dòng xin chao và tách hai luồng. Nội dung **output.txt**:

~~~text
OUT:xin chao
~~~

Nội dung **error.txt**:

~~~text
ERR:diagnostic
~~~

Nếu bỏ phần **2> error.txt** mà vẫn có **> output.txt**, thông báo ERR:diagnostic sẽ tiếp tục đi theo stderr ban đầu, thường là terminal. Nếu dùng **> combined.txt 2>&1**, cả hai dòng được hướng vào combined.txt.

### PowerShell có cú pháp và quy tắc riêng

Không mặc định lấy ví dụ **< input.txt** của Bash/cmd áp dụng nguyên xi cho PowerShell, đặc biệt Windows PowerShell 5.1. Trong PowerShell, có thể dùng Start-Process với ba tham số chuyển hướng riêng:

~~~powershell
$p = Start-Process -FilePath java -ArgumentList 'StandardStreamsDemo' -RedirectStandardInput 'input.txt' -RedirectStandardOutput 'output.txt' -RedirectStandardError 'error.txt' -NoNewWindow -Wait -PassThru
$p.ExitCode
~~~

Ví dụ giả định input.txt đã tồn tại, class được biên dịch trong thư mục đang làm việc và Java có trên PATH. **-Wait** đợi tiến trình hoàn tất, **-PassThru** lấy đối tượng tiến trình để kiểm tra ExitCode.

PowerShell còn có hệ thống stream và cách xử lý encoding của redirection riêng, thay đổi theo phiên bản. Nếu cần dữ liệu binary giữ nguyên từng byte, ưu tiên API byte của Java thay vì suy rằng mọi shell sẽ luôn giữ nguyên byte trong các pipeline có xử lý text.

## 4. Exit code độc lập với stdout và stderr

**Thông báo lỗi** và **mã thoát tiến trình** là hai khái niệm khác nhau:

- Một chương trình có thể ghi cảnh báo vào stderr và vẫn thoát với mã 0.
- Một chương trình có thể không ghi gì vào stderr nhưng trả mã thoát khác 0.
- Chương trình có thể ghi dữ liệu một phần ra stdout rồi thất bại.
- Chuyển stderr vào file không khiến thao tác lỗi biến thành thành công.

Trong Bash, biến **$?** ngay sau lệnh có exit status của lệnh gần nhất; cmd.exe thường dùng **%ERRORLEVEL%**; PowerShell hỗ trợ **$LASTEXITCODE** cho tiến trình native. Trong Java, **Process.waitFor()** trả exit code của tiến trình con sau khi nó kết thúc. Quy ước phổ biến là 0 biểu thị thành công, nhưng ý nghĩa chính xác phải theo hợp đồng của từng chương trình.

Để tự quy định mã thoát cho một ứng dụng Java, có thể dùng **System.exit(code)** ở nơi phù hợp. Không dùng phương thức đó để kết thúc tùy tiện một thư viện vì nó chấm dứt cả JVM hiện tại.

## 5. ProcessBuilder: cấu hình kênh chuẩn của tiến trình con

Khi Java cần chạy một chương trình bên ngoài, dùng **ProcessBuilder**. Khác với shell, ProcessBuilder nhận **danh sách lệnh và đối số**, và cung cấp API để nối stdin/stdout/stderr trước khi gọi **start()**.

Mặc định, ba kênh của tiến trình con dùng **PIPE**:

~~~text
               Java parent process
                       |
    ghi vào child stdin: process.getOutputStream()
                       |
                       v
                  Java child
                       |
     +-----------------+-----------------+
     |                                   |
 child stdout                        child stderr
     |                                   |
     v                                   v
process.getInputStream()      process.getErrorStream()
~~~

Tên phương thức theo **góc nhìn của parent**: getOutputStream() là nơi parent **ghi vào stdin của child**, còn getInputStream() là nơi parent **đọc stdout của child**. Đây là nguyên nhân dễ gây nhầm lẫn khi mới dùng Process API.

### Chương trình chạy được: redirect từ file và thu hai output riêng

Tạo file **ProcessRedirectionDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class ProcessRedirectionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "child".equals(args[0])) {
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            System.in, StandardCharsets.UTF_8));

            String first = input.readLine();
            String second = input.readLine();

            System.out.println("received=" + first + "|" + second);
            System.err.println("warning=demo");
            System.exit(7);
            return;
        }

        Path dir = Files.createTempDirectory("redirect-java-");
        Path source = dir.resolve("source.txt");
        Path normal = dir.resolve("normal.txt");
        Path errors = dir.resolve("errors.txt");

        try {
            Files.writeString(source, "alpha\nbeta\n",
                    StandardCharsets.UTF_8);

            String os = System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT);
            String javaName = os.contains("win") ? "java.exe" : "java";
            Path executable = Path.of(
                    System.getProperty("java.home"),
                    "bin", javaName);

            ProcessBuilder builder = new ProcessBuilder(
                    executable.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    ProcessRedirectionDemo.class.getName(),
                    "child");

            builder.redirectInput(source.toFile());
            builder.redirectOutput(normal.toFile());
            builder.redirectError(errors.toFile());

            Process child = builder.start();
            int exit = child.waitFor();

            String stdout = Files.readString(
                    normal, StandardCharsets.UTF_8).strip();
            String stderr = Files.readString(
                    errors, StandardCharsets.UTF_8).strip();

            System.out.println("exit=" + exit);
            System.out.println("stdout=" + stdout);
            System.out.println("stderr=" + stderr);
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(normal);
            Files.deleteIfExists(errors);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ProcessRedirectionDemo.java
java ProcessRedirectionDemo
~~~

Stdout từ **parent**:

~~~text
exit=7
stdout=received=alpha|beta
stderr=warning=demo
~~~

Điều gì đã xảy ra?

1. Parent tạo file tạm chứa alpha và beta, mỗi giá trị ở một dòng.
2. Parent dùng đường dẫn đến Java executable của JDK đang chạy và khởi động **một JVM con**, chạy lại class với đối số child.
3. **redirectInput(source)** dùng nội dung file làm stdin của child.
4. **redirectOutput(normal)** và **redirectError(errors)** tách stdout, stderr vào hai file riêng.
5. Child đọc hai dòng, in received=alpha|beta lên stdout, in warning=demo lên stderr rồi chủ động thoát với mã 7.
6. Parent **waitFor()** trước khi đọc các file kết quả, nên có thể biết child đã kết thúc. Parent chỉ in lại nội dung file sau đó.
7. Parent xóa các file tạm trong finally.

**System.exit(7)** bên nhánh child chỉ kết thúc **JVM con**, không kết thúc JVM cha. Mã thoát 7 được chọn để minh họa rằng parent có thể nhận một exit code khác 0.

Ví dụ giả định chạy bằng classpath thông thường như lệnh đã đưa. Với ứng dụng chạy trên module path, fat JAR hoặc classloader tùy chỉnh, lệnh gọi JVM con cần điều chỉnh theo cách đóng gói. Các chuỗi trong output của ví dụ chỉ dùng ASCII nên không phát sinh khác biệt console encoding; với văn bản Unicode phải thống nhất encoding ở hai phía.

## 6. Chế độ redirect được Java cung cấp

| Cơ chế ProcessBuilder | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| **Redirect.PIPE** | Nối qua pipe do Java parent sở hữu; mặc định | Parent xử lý output hoặc cấp input trong thời gian chạy |
| **Redirect.INHERIT** | Child dùng kênh chuẩn đã có của parent | Chương trình con tương tác trực tiếp hoặc cùng dùng log của parent |
| **Redirect.from(file)** | Child lấy stdin từ file | Dữ liệu đầu vào hữu hạn có sẵn |
| **Redirect.to(file)** | Child ghi stdout/stderr vào file, thay nội dung cũ | Tạo báo cáo/log mới |
| **Redirect.appendTo(file)** | Ghi nối stdout/stderr vào file | Giữ log trước đó |
| **Redirect.DISCARD** | Bỏ stdout/stderr | Output không cần thiết |

Một số cấu hình minh họa, đặt **trước** builder.start():

~~~java
// Mảnh code; builder là ProcessBuilder, logPath là Path.
builder.inheritIO(); // Kế thừa stdin/stdout/stderr từ parent.
~~~

Hoặc:

~~~java
builder.redirectOutput(
        ProcessBuilder.Redirect.appendTo(logPath.toFile()));
builder.redirectError(ProcessBuilder.Redirect.INHERIT);
~~~

Hai mảnh code mô tả **các cách chọn cấu hình**, không phải yêu cầu gọi liên tiếp nếu muốn giữ nguyên cả ba redirect của inheritIO.

**Lưu ý về API Process:** khi stdout của child đã được chuyển tới file hay INHERIT, **process.getInputStream()** tương ứng thường là *null input stream*, không có nội dung stdout để parent đọc. Tương tự, khi stderr đã redirect, getErrorStream() không còn kênh dữ liệu stderr riêng; khi stdin đã lấy từ file/INHERIT, getOutputStream() là *null output stream*. Đừng đồng thời kỳ vọng vừa redirect thẳng tới file vừa đọc toàn bộ nội dung qua PIPE mặc định.

**inheritIO()** kế thừa kênh chuẩn của **process parent**, và parent có thể đã được shell chuyển hướng từ trước. Chế độ inherit không nhất thiết có nghĩa child nối với màn hình vật lý.

## 7. Gộp stdout với stderr trong Java

Nếu một lệnh chỉ cần ghi log chung, có thể bật **redirectErrorStream(true)**:

~~~java
// Mảnh code: builder đã được cấu hình lệnh phù hợp.
builder.redirectErrorStream(true);
Process process = builder.start();

try (var input = process.getInputStream()) {
    input.transferTo(System.out);
}
int exitCode = process.waitFor();
~~~

Lúc này stderr của child được gộp vào stdout và parent đọc dữ liệu gộp từ **getInputStream()**. Cấu hình redirectError(...) riêng bị bỏ qua khi redirectErrorStream(true). Nếu stdout còn là PIPE thì input.transferTo(System.out) tiêu thụ pipe trong lúc child chạy; sau khi stream hết dữ liệu, waitFor() thu mã thoát.

Nếu muốn lưu chung vào file:

~~~java
builder.redirectErrorStream(true);
builder.redirectOutput(
        ProcessBuilder.Redirect.appendTo(logPath.toFile()));
~~~

**Nhược điểm khi gộp:** thông báo lỗi có thể xen trong JSON/CSV vốn được kỳ vọng chỉ nằm ở stdout, làm hỏng quá trình phân tích. Chọn gộp khi thực sự muốn log chung; giữ riêng stderr khi stdout là dữ liệu có cấu trúc.

Thứ tự tương đối của thông điệp sau khi gộp không nhất thiết tái tạo chính xác thứ tự lập trình do buffering, flush và tiến độ thực thi.

## 8. Rủi ro deadlock khi không đọc các PIPE

Lỗi thường gặp khi parent gọi:

~~~java
// KHÔNG AN TOÀN nếu stdout/stderr của child vẫn là PIPE
// và child ghi đủ nhiều dữ liệu.
Process child = builder.start();
int code = child.waitFor();
// Sau đó mới bắt đầu đọc stdout và stderr.
~~~

**Vì sao có thể treo?** Pipe có bộ đệm hữu hạn. Child ghi stdout hoặc stderr quá nhiều làm pipe đầy; child phải chờ parent đọc. Parent lại đang **waitFor()**, chờ child kết thúc. Hai bên chờ nhau:

~~~text
child write() -> pipe đầy -> chờ parent đọc
parent waitFor() -> chờ child kết thúc
=> deadlock
~~~

Các lựa chọn giải quyết:

1. Redirect stdout và stderr của child **trực tiếp tới file**, như chương trình ProcessRedirectionDemo.
2. Dùng **inheritIO()** nếu có môi trường sẵn tiêu thụ output và chấp nhận dùng kênh chuẩn của parent.
3. Nếu muốn một stream chung, **redirectErrorStream(true)** và đọc stream chung trong lúc child chạy.
4. Nếu cần tách kết quả và lỗi, **đọc stdout và stderr đồng thời**, ví dụ mỗi stream bằng một task hoặc thread riêng; sau đó đợi child hoàn tất.

Một tình huống chờ khác liên quan stdin: khi mặc định stdin của child nối với PIPE, chương trình con có thể đợi dữ liệu hoặc EOF. Sau khi parent ghi xong vào **process.getOutputStream()**, phải **đóng đầu ghi** để thông báo hết input khi giao thức yêu cầu EOF. Nếu không, child có thể chờ vô thời hạn.

**waitFor() không tạo timeout tự động.** Nếu child có nguy cơ treo, dùng biến thể waitFor(timeout, unit), xử lý trường hợp quá hạn và lựa chọn chấm dứt tiến trình theo yêu cầu ứng dụng. Timeout cũng không thay thế việc quản lý các luồng đang đọc.

## 9. Encoding và tính toàn vẹn dữ liệu

Việc chuyển hướng chỉ thay đổi **kết nối dữ liệu**, không tự chọn charset và không tự hiểu định dạng file. Java String phải được **encode** thành byte khi ghi ra kênh; byte từ stdin phải được **decode** nếu chương trình muốn xử lý dưới dạng ký tự.

Ví dụ **InputStreamReader(System.in, StandardCharsets.UTF_8)** có nghĩa là ứng dụng tin rằng stdin đang mang văn bản UTF-8. Nếu file thực tế là Windows-1252 hoặc UTF-16LE mà chương trình giải mã như UTF-8, chữ có thể lỗi hoặc ký tự bị thay thế. Ngược lại, các luồng stdout/stderr dùng PrintStream có encoding riêng theo cấu hình runtime; nếu bên nhận cần text Unicode, hãy thống nhất encoding hoặc ghi bằng OutputStreamWriter với charset tường minh.

Nếu stdout chứa **ảnh, ZIP hoặc dữ liệu binary**, đừng đọc bằng Reader rồi ghi thành String. Hãy truyền nguyên byte bằng InputStream/OutputStream; ví dụ input.transferTo(output) sao chép byte mà không decode thành ký tự. Đối với text, dùng BufferedReader/BufferedWriter với charset đúng.

Chú ý **buffering**: khi chương trình ghi vào pipe hoặc file, dữ liệu có thể nằm trong bộ đệm trước khi được gửi tới kênh dưới. Flush thích hợp có thể cần thiết với giao thức tương tác để phía nhận thấy dữ liệu kịp thời. Nhưng flush không bảo đảm file đã được đồng bộ bền vững lên đĩa hoặc phía nhận đã xử lý xong.

**Không coi stderr là dữ liệu của stdout** chỉ vì chúng cùng hiển thị trên màn hình. Nếu cần parse nội dung stdout bằng ứng dụng khác, hãy chọn dữ liệu có cấu trúc ở stdout và chẩn đoán ở stderr từ ngay thiết kế.

## 10. System.setIn/out/err không phải redirect OS của process con

Java có thể thay đối tượng kênh chuẩn trong **JVM hiện tại**:

~~~java
System.setIn(otherInputStream);
System.setOut(otherPrintStream);
System.setErr(otherPrintStream);
~~~

Đây là **mảnh code minh họa**: biến otherInputStream thuộc InputStream, còn otherPrintStream thuộc PrintStream, do chương trình cung cấp. Nó thay các đối tượng mà mã Java truy cập qua System.in/out/err. Vì tác động trên toàn JVM, nhiều thread hoặc thư viện cùng sử dụng System.out có thể bị ảnh hưởng.

Tuy nhiên, **System.setOut không tương đương chuyển hướng stdout ở cấp hệ điều hành** và không tự cấu hình stdout của mọi tiến trình con đã khởi động. Mã native hoặc thư viện giữ tham chiếu đến luồng cũ có thể không tuân theo luồng mới. Muốn điều khiển kênh chuẩn của **tiến trình con**, ưu tiên ProcessBuilder; muốn chuyển hướng khi người dùng chạy một lệnh, dùng shell.

| Phương án | Phạm vi | Mục đích |
| --- | --- | --- |
| Bash/cmd redirection | Tiến trình được shell khởi chạy | Chạy chương trình qua file hoặc pipe |
| ProcessBuilder redirects | Tiến trình con được Java tạo | Thu output, cấp input, lưu log, kế thừa terminal |
| System.setIn/out/err | Các đối tượng kênh chuẩn của JVM hiện tại | Thay I/O mà mã Java hiện tại tham chiếu |
| System.console() | API truy cập console tương tác nếu tồn tại | Hỏi/đọc console, không thay thế redirect |

**System.console() có thể trả null** khi chạy qua IDE, CI, pipeline hoặc khi môi trường không có console thích hợp. Không dùng riêng giá trị null để khẳng định cụ thể stdout đang được chuyển vào file nào.

## 11. Tình huống thực tế

**Xuất kết quả và giữ lỗi riêng:** Một công cụ sinh JSON nên in JSON ra stdout và lỗi parse/tham số ra stderr. Khi dùng redirect, bên gọi nhận file JSON sạch và vẫn có file lỗi để điều tra.

**Gọi bộ biên dịch từ Java:** Parent dùng ProcessBuilder với danh sách lệnh/đối số; redirect stdout và stderr sang file hoặc đọc đồng thời; kiểm tra exit code để biết compilation thành công. Có log không đồng nghĩa exit code bằng 0.

**Ghi log lâu dài:** Có thể dùng Redirect.appendTo(logFile) khi cần giữ log cũ, nhưng phải xem xét tăng trưởng file và cách xoay vòng log; chuyển hướng không tự quản lý dung lượng.

**Lệnh cần nhập dữ liệu:** Nếu stdin từ file, dùng redirectInput(file). Nếu parent cần gửi dữ liệu động, để stdin là PIPE, ghi vào process.getOutputStream() và đóng đầu ghi đúng lúc. Nếu child cần tương tác với terminal, cân nhắc inheritIO().

**Pipeline nhiều tiến trình:** Shell có thể nối stdout của tiến trình A vào stdin của tiến trình B. Trong Java, có ProcessBuilder.startPipeline(...) cho một số cấu hình pipeline; vẫn phải quản lý lỗi stderr, mã thoát của từng process và vòng đời toàn pipeline. Đừng mặc định mã thoát của tiến trình cuối phản ánh mọi lỗi ở các giai đoạn trước nếu giao thức không định nghĩa điều đó.

## 12. Các lỗi thường gặp và cách tránh

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Dùng >file rồi tưởng stderr cũng vào file | Lỗi vẫn đi tới stderr cũ | Thêm 2>file khác hoặc 2>&1 |
| Đảo thứ tự >file và 2>&1 | Đích stderr không như dự kiến | Xác định redirect trái sang phải |
| Gọi waitFor trước khi drain các PIPE lớn | Child có thể chặn, parent đợi mãi | Drain đồng thời hoặc redirect file |
| Không đóng stdin PIPE khi hoàn tất | Child có thể tiếp tục chờ EOF | Đóng getOutputStream() sau khi ghi xong |
| Coi có stderr là exit code thất bại | Đánh giá trạng thái sai | Đọc cả exit code và hợp đồng chương trình |
| Gộp stderr vào stdout JSON | Output có thể không parse được | Giữ hai luồng riêng |
| Đưa dấu > vào ProcessBuilder như đối số | Child nhận chuỗi >, không được redirect | Dùng redirectOutput |
| Thay System.out rồi tưởng child cũng thay | Child có kênh chuẩn OS riêng | Cấu hình ProcessBuilder |
| Mặc định stdout là Unicode đúng mọi nơi | Encoding có thể khác nhau | Xác định charset ở hai đầu |
| Dùng Reader/Writer cho file ảnh qua PIPE | Có thể đổi byte, hỏng file | Dùng luồng byte |
| Đọc từ stdout bằng getInputStream sau redirectOutput(file) | Stream tương ứng không còn dữ liệu để đọc | Đọc file đã redirect hoặc giữ PIPE |
| Quên đóng stream hoặc cleanup khi lỗi | Rò rỉ tài nguyên/file tạm | try-with-resources, finally |

## 13. Bài tập tự kiểm tra

**Câu 1.** Nếu chạy java App >out.txt 2>err.txt, System.out và System.err đi đâu?  
**Đáp án:** System.out đi vào out.txt; System.err đi vào err.txt. System.in giữ nguồn cũ nếu không chuyển hướng riêng.

**Câu 2.** java App >both.txt 2>&1 khác java App 2>&1 >both.txt thế nào?  
**Đáp án:** Lệnh đầu nối stderr vào đích stdout đã đổi sang file; lệnh sau sao chép đích stdout ban đầu cho stderr rồi mới đổi stdout, nên lỗi có thể ở terminal.

**Câu 3.** Vì sao Process.getOutputStream() của Java parent lại viết vào stdin của child?  
**Đáp án:** Tên phương thức lấy theo hướng nhìn của parent: đó là output stream từ parent **đến** input của child.

**Câu 4.** Process.waitFor() có bảo đảm không bị kẹt khi child in nhiều lỗi không?  
**Đáp án:** Không. Nếu stderr PIPE đầy nhưng parent không đọc, child có thể chặn. Cần drain stderr đồng thời hoặc redirect ra file/gộp.

**Câu 5.** Nếu parent muốn parse JSON từ stdout của child, có nên bật redirectErrorStream(true) không?  
**Đáp án:** Thường không. Nó trộn stderr với stdout, có thể làm JSON mất tính hợp lệ.

**Câu 6.** Chương trình ghi ERR:warning lên stderr nhưng exit code 0 thì bắt buộc thất bại?  
**Đáp án:** Không. Exit code và nội dung stderr được định nghĩa riêng trong hợp đồng của công cụ.

**Câu 7.** System.setOut(newStream) có tự đổi stdout của mọi process khác không?  
**Đáp án:** Không. Nó đổi tham chiếu System.out của JVM hiện tại; ProcessBuilder hoặc shell mới cấu hình stdio của child process.

**Câu 8.** Dữ liệu nhị phân được redirect qua file hay PIPE có tự biến thành văn bản không?  
**Đáp án:** Không. Redirect là nối byte giữa các kênh, còn ý nghĩa byte phụ thuộc định dạng và encoding; cần giữ byte nguyên vẹn nếu là binary.

## 14. API Java tham khảo

- [Java SE 17 — System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): System.in, System.out, System.err và setIn/setOut/setErr.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): redirectInput, redirectOutput, redirectError, redirectErrorStream, inheritIO.
- [Java SE 17 — ProcessBuilder.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.Redirect.html): PIPE, INHERIT, DISCARD, from, to, appendTo.
- [Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): getInputStream, getOutputStream, getErrorStream, waitFor.

**Điểm cốt lõi:** Stdin, stdout và stderr là ba kênh chuẩn riêng của một tiến trình. Shell hoặc ProcessBuilder nối chúng với terminal, file hay PIPE; mã Java tiếp tục thao tác qua System.in/out/err. Muốn vận hành đúng, phải quản lý thêm charset, việc tiêu thụ PIPE, EOF đầu vào, exit code và sự khác biệt giữa log chẩn đoán và dữ liệu đầu ra.

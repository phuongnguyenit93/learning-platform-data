# try-with-resources cho Process và các luồng dữ liệu

Khi Java khởi chạy một tiến trình hệ điều hành, ứng dụng giữ nhiều tài nguyên cùng lúc: đối tượng Process, các pipe kết nối stdin/stdout/stderr và những reader/writer dùng để trao đổi dữ liệu. Nếu quên đóng stream hoặc để tiến trình con chạy ngoài phạm vi quản lý, ứng dụng có thể giữ file descriptor, handle và tiến trình hệ điều hành lâu hơn dự kiến.

Từ JDK 26, java.lang.Process triển khai Closeable/AutoCloseable và có phương thức close(). Vì vậy, có thể đặt Process trực tiếp trong try-with-resources. Khi khối try kết thúc, close() đóng các luồng đọc/ghi của tiến trình rồi chờ tiến trình kết thúc. Đây là điểm thay đổi đáng chú ý so với JDK 25 và các bản trước.

Bài học tập trung vào Java 26: quản lý vòng đời Process, đóng đúng các luồng dữ liệu, đọc đồng thời stdout/stderr để tránh deadlock, gửi EOF qua stdin, lấy exit code và xử lý timeout/interruption. Các ví dụ dùng ProcessBuilder vì đây là cách rõ ràng để truyền lệnh và từng đối số riêng biệt.

## 1. Những tài nguyên cần quản lý

Một Process được tạo bằng ProcessBuilder.start() đại diện cho tiến trình hệ điều hành. Mặc định, ba luồng chuẩn của tiến trình con được nối với tiến trình Java đang gọi:

| Luồng | Phía Java cha | Hướng dữ liệu |
|---|---|---|
| stdin của tiến trình con | Process.getOutputStream() hoặc Process.outputWriter() | Java cha ghi, tiến trình con đọc |
| stdout của tiến trình con | Process.getInputStream() hoặc Process.inputReader() | Tiến trình con ghi, Java cha đọc |
| stderr của tiến trình con | Process.getErrorStream() hoặc Process.errorReader() | Tiến trình con ghi lỗi, Java cha đọc |

Có thể hình dung:

~~~text
Java application
      |
      | ProcessBuilder.start()
      v
  Process object
      |
      +---- outputWriter()  ------> child stdin
      |
      +<--- inputReader()   <------ child stdout
      |
      +<--- errorReader()   <------ child stderr
~~~

Các reader/writer và stream giữ tài nguyên giao tiếp giữa hai tiến trình. Hãy đóng chúng khi không còn cần dùng. Chỉ bỏ tham chiếu đến Process không làm tiến trình con tự kết thúc; tiến trình con có thể tiếp tục chạy bất đồng bộ.

Từ Java 17, Process cung cấp các phương thức tiện ích:

- outputWriter() và outputWriter(Charset) để ghi văn bản vào stdin.
- inputReader() và inputReader(Charset) để đọc stdout.
- errorReader() và errorReader(Charset) để đọc stderr.

Từ Java 26, Process có thêm close() và có thể được quản lý bằng try-with-resources. Các reader/writer ở trên là API đã có trước đó; điểm mới của JDK 26 là khả năng đóng chính đối tượng Process theo hợp đồng Closeable.

## 2. Process.close() thực hiện điều gì?

Trong JDK 26, Process.close() có hợp đồng cụ thể:

1. Đóng các reader và writer/stream I/O của Process.
2. Chờ tiến trình hệ điều hành kết thúc.
3. Nếu thread gọi close() bị interrupt trong lúc chờ, tiến trình bị destroyForcibly(); close() tiếp tục chờ đến khi tiến trình kết thúc.
4. Khôi phục trạng thái interrupt của thread trước khi close() trả về hoặc ném IOException.
5. close() có tính idempotent: gọi lại sau khi Process đã đóng không làm phát sinh hành động đóng lần nữa.

Có một số hệ quả cần nhớ:

- Nếu cần dữ liệu stdout hoặc stderr, hãy đọc dữ liệu trước khi gọi close(). Nội dung chưa đọc đến EOF sẽ bị bỏ khi close() đóng stream.
- Nếu cần exit code, hãy gọi waitFor() trước close(). close() không trả exit code.
- close() không phải timeout. Nếu tiến trình không kết thúc sau khi các pipe bị đóng, close() có thể chờ lâu hoặc vô thời hạn.
- Nếu tiến trình chỉ kết thúc sau khi nhận EOF ở stdin, đóng writer có thể giúp nó kết thúc. Nhưng không phải chương trình con nào cũng thoát khi stdin đóng.
- Khi cần thời hạn kết thúc rõ ràng, hãy dùng waitFor(timeout, unit), sau đó destroy() và destroyForcibly() theo chính sách của ứng dụng.

Không coi close() là lệnh yêu cầu kết thúc bình thường tương đương destroy(). close() đóng các kênh I/O rồi chờ; khi việc chờ bị interrupt, API mới buộc tiến trình kết thúc bằng destroyForcibly().

## 3. Cấu trúc try-with-resources và thứ tự đóng

Try-with-resources đóng tài nguyên theo thứ tự ngược với thứ tự khai báo. Vì vậy, hãy khai báo Process trước, sau đó khai báo reader/writer được tạo từ Process:

~~~java
try (Process process = new ProcessBuilder(command).start();
     BufferedWriter stdin = process.outputWriter(StandardCharsets.UTF_8);
     BufferedReader stdout = process.inputReader(StandardCharsets.UTF_8)) {

    // Dùng stdin và stdout.
}
~~~

Khi rời khối try, thứ tự đóng là:

1. stdout reader.
2. stdin writer.
3. Process.

Cách sắp xếp này giúp các stream được đóng trước khi Process.close() hoàn tất việc đóng và chờ tiến trình kết thúc. Nếu cần gửi EOF cho tiến trình con trước khi đọc kết quả, hãy đóng writer sớm hơn bằng một khối try-with-resources lồng nhau.

~~~java
try (Process process = new ProcessBuilder(command).start()) {

    try (BufferedWriter stdin =
                 process.outputWriter(StandardCharsets.UTF_8)) {
        stdin.write("request");
        stdin.newLine();
    } // Đóng stdin để báo EOF cho tiến trình con.

    try (BufferedReader stdout =
                 process.inputReader(StandardCharsets.UTF_8)) {
        List<String> response = stdout.readAllLines();
        System.out.println(response);
    }

    int exitCode = process.waitFor();
    System.out.println("Exit code: " + exitCode);
}
~~~

Sau khi khối ngoài kết thúc, Process.close() vẫn được gọi tự động. Các stream đã đóng trong khối lồng; Process chịu trách nhiệm đóng toàn bộ stream còn lại và chờ tiến trình kết thúc.

Nếu phần thân try ném exception, Java vẫn gọi close() cho các tài nguyên đã tạo. Exception trong phần thân được giữ làm lỗi chính; lỗi phát sinh khi đóng tài nguyên được ghi nhận dưới dạng suppressed exception. Có thể xem chúng bằng getSuppressed() khi cần chẩn đoán.

## 4. Ví dụ hoàn chỉnh: gửi stdin, đọc stdout và lấy exit code

Ví dụ dưới đây khởi chạy một Java child process để nhận các dòng văn bản từ stdin và gửi lại phản hồi trên stdout. Dùng chính executable của JDK đang chạy để tránh phụ thuộc đường dẫn java trong PATH.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public class ProcessTwrDemo {

    public static void main(String[] args) throws Exception {
        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);

        String javaName = os.startsWith("windows")
                ? "java.exe"
                : "java";

        Path javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin",
                javaName);

        List<String> command = List.of(
                javaExecutable.toString(),
                "-cp",
                System.getProperty("java.class.path"),
                EchoChild.class.getName());

        ProcessBuilder builder = new ProcessBuilder(command)
                .redirectErrorStream(true);

        try (Process process = builder.start()) {

            // Gửi dữ liệu cho stdin của child.
            try (BufferedWriter stdin =
                         process.outputWriter(StandardCharsets.UTF_8)) {
                stdin.write("Xin chao");
                stdin.newLine();

                stdin.write("Java 26");
                stdin.newLine();
            } // Child nhận EOF và kết thúc vòng lặp đọc.

            // Đọc stdout. stderr đã được gộp vào stdout.
            List<String> response;

            try (BufferedReader stdout =
                         process.inputReader(StandardCharsets.UTF_8)) {
                response = stdout.readAllLines();
            }

            // Lấy exit code trước khi Process.close() chạy.
            int exitCode = process.waitFor();

            if (exitCode != 0) {
                throw new IOException(
                        "Child process failed with exit code " + exitCode);
            }

            response.forEach(System.out::println);
        }
    }

    public static final class EchoChild {

        public static void main(String[] args) throws IOException {
            BufferedReader stdin = new BufferedReader(
                    new InputStreamReader(
                            System.in,
                            StandardCharsets.UTF_8));

            BufferedWriter stdout = new BufferedWriter(
                    new OutputStreamWriter(
                            System.out,
                            StandardCharsets.UTF_8));

            String line;

            while ((line = stdin.readLine()) != null) {
                stdout.write("echo: " + line);
                stdout.newLine();
                stdout.flush();
            }
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
echo: Xin chao
echo: Java 26
~~~

Luồng thực thi:

1. ProcessBuilder khởi chạy JVM con.
2. Java cha ghi hai dòng vào stdin thông qua BufferedWriter.
3. Đóng writer gửi EOF, giúp child biết không còn dữ liệu đầu vào.
4. Child đọc đến EOF, ghi phản hồi và kết thúc.
5. Java cha đọc stdout đến EOF.
6. waitFor() trả exit code.
7. Khi rời khối try, Process.close() đóng các kênh còn lại và bảo đảm tiến trình đã kết thúc.

Ví dụ dùng redirectErrorStream(true) để đơn giản hóa việc đọc một luồng. Trong ứng dụng thực tế, chỉ gộp stderr vào stdout khi việc trộn thông báo lỗi với kết quả thông thường không làm sai giao thức dữ liệu.

## 5. Đọc stdout và stderr mà không gây deadlock

Mặc định, stdout và stderr là hai pipe riêng. Mỗi pipe có bộ đệm giới hạn theo nền tảng. Nếu tiến trình con ghi đầy một pipe mà Java cha không đọc, tiến trình con có thể bị chặn khi ghi. Java cha cũng có thể bị chặn khi chờ tiến trình kết thúc. Hai bên chờ nhau sẽ tạo deadlock.

Một lỗi thường gặp là đọc stdout đến hết rồi mới đọc stderr:

~~~java
// Có thể deadlock nếu child ghi nhiều dữ liệu vào stderr.
List<String> stdout = process.inputReader(UTF_8).readAllLines();
List<String> stderr = process.errorReader(UTF_8).readAllLines();
~~~

Nếu child ghi nhiều stderr trước khi đóng stdout, buffer stderr có thể đầy. Child dừng ghi và không thể kết thúc; Java cha vẫn đợi EOF trên stdout.

Có ba cách xử lý thường dùng:

| Cách | Khi phù hợp | Lưu ý |
|---|---|---|
| Gộp stderr vào stdout | Chỉ cần một luồng output, không cần phân biệt nguồn | Dùng redirectErrorStream(true); stderr không còn là pipe riêng |
| Redirect ra file | Output lớn hoặc cần lưu log riêng | Java không cần đọc pipe; phải quản lý file đích |
| Đọc hai stream đồng thời | Cần giữ stdout và stderr riêng | Dùng thread/executor riêng để liên tục drain cả hai |

### Đọc hai stream đồng thời bằng virtual threads

Virtual thread là lựa chọn thuận tiện cho tác vụ đọc I/O chờ đợi. Ví dụ sau đọc stdout và stderr đồng thời, trong khi thread gọi quản lý stdin và chờ process:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

static void runCommand(List<String> command) throws Exception {

    try (var readers = Executors.newVirtualThreadPerTaskExecutor();
         Process process = new ProcessBuilder(command).start()) {

        Future<List<String>> stdout = readers.submit(() -> {
            try (BufferedReader reader =
                         process.inputReader(StandardCharsets.UTF_8)) {
                return reader.readAllLines();
            }
        });

        Future<List<String>> stderr = readers.submit(() -> {
            try (BufferedReader reader =
                         process.errorReader(StandardCharsets.UTF_8)) {
                return reader.readAllLines();
            }
        });

        // Nếu child cần dữ liệu, gửi xong rồi đóng stdin.
        try (BufferedWriter stdin =
                     process.outputWriter(StandardCharsets.UTF_8)) {
            stdin.write("request");
            stdin.newLine();
        }

        int exitCode = process.waitFor();

        List<String> outLines = stdout.get();
        List<String> errorLines = stderr.get();

        System.out.println("stdout: " + outLines);
        System.out.println("stderr: " + errorLines);
        System.out.println("exit: " + exitCode);
    }
}
~~~

Hai reader chạy đồng thời nên child có thể ghi cả hai pipe mà không phải đợi Java cha đọc tuần tự. Khi process kết thúc, hai reader nhận EOF và Future hoàn tất. TWR đóng Process trước khi đóng executor vì Process được khai báo sau executor; tuy nhiên các Future đã được lấy kết quả trước khi rời khối nên tác vụ đọc đã hoàn tất.

Nếu output rất lớn, không dùng readAllLines() để giữ toàn bộ dữ liệu trong heap. Hãy xử lý từng dòng, giới hạn kích thước, ghi ra file hoặc chuyển đến consumer có backpressure phù hợp. Đồng thời kiểm soát dung lượng log để tránh tiến trình con tạo output không giới hạn.

### Gộp stderr vào stdout

Khi thứ tự tương đối của thông báo quan trọng hơn việc phân biệt kênh, có thể dùng:

~~~java
ProcessBuilder builder = new ProcessBuilder(command)
        .redirectErrorStream(true);

try (Process process = builder.start();
     BufferedReader output =
             process.inputReader(StandardCharsets.UTF_8)) {

    List<String> lines = output.readAllLines();
    int exitCode = process.waitFor();
}
~~~

Khi redirectErrorStream(true) được bật, stderr được gửi chung vào stdout. Process.getErrorStream() hoặc errorReader() trả về luồng rỗng. Không mở thêm errorReader để chờ dữ liệu trong cấu hình này.

## 6. Redirect I/O và quyền sở hữu stream

Không phải tiến trình nào cũng cần Java cha đọc hoặc ghi qua pipe. ProcessBuilder cho phép chuyển hướng từng luồng:

~~~java
ProcessBuilder builder = new ProcessBuilder(command)
        .redirectInput(inputFile.toFile())
        .redirectOutput(outputFile.toFile())
        .redirectError(errorFile.toFile());

try (Process process = builder.start()) {
    int exitCode = process.waitFor();
}
~~~

Trong trường hợp này, hệ điều hành nối stdin/stdout/stderr với các file đã chỉ định. Các getter tương ứng trên Process trả về null stream:

- Nếu stdin đã redirect, getOutputStream() trả về null output stream; ghi vào đó ném IOException và close() không làm gì.
- Nếu stdout đã redirect, getInputStream() trả về null input stream; đọc trả EOF.
- Nếu stderr đã redirect hoặc gộp với stdout, getErrorStream() trả về null input stream.

Các getter vẫn tồn tại để API có thể dùng nhất quán, nhưng không còn đại diện cho pipe đang truyền dữ liệu. Không mở reader rồi kết luận child không tạo output khi bạn đã redirect output ra file.

Một số lựa chọn khác:

- redirectErrorStream(true): gộp stderr vào stdout.
- inheritIO(): dùng stdin/stdout/stderr của tiến trình Java cha.
- redirectOutput(file): ghi stdout trực tiếp vào file.
- redirectError(file): ghi stderr trực tiếp vào file.
- redirectInput(file): đọc stdin từ file.

ProcessBuilder là đối tượng cấu hình để khởi chạy; nó không phải tài nguyên cần đóng. Process mới là tài nguyên đại diện cho tiến trình đã được tạo.

## 7. Chọn Reader/Writer hay InputStream/OutputStream

Process cung cấp cả byte stream lẫn API ký tự. Chọn một cách cho mỗi pipe và dùng nhất quán:

| Nhu cầu | API nên dùng |
|---|---|
| Giao thức văn bản có charset xác định | outputWriter(Charset), inputReader(Charset), errorReader(Charset) |
| Dữ liệu nhị phân | getOutputStream(), getInputStream(), getErrorStream() |
| Đọc văn bản theo encoding mặc định của hệ điều hành | outputWriter(), inputReader(), errorReader() |
| Đọc/ghi theo dòng | BufferedReader.readLine(), BufferedWriter.write()/newLine() |

Không dùng reader và raw stream đồng thời trên cùng một kênh. Reader có thể đọc trước và giữ dữ liệu trong buffer; sau đó code đọc trực tiếp InputStream sẽ không nhìn thấy những byte đã được reader lấy vào buffer.

Ví dụ không nên làm:

~~~java
BufferedReader reader = process.inputReader(StandardCharsets.UTF_8);
InputStream raw = process.getInputStream();

// Không trộn hai cách đọc trên cùng stdout.
String line = reader.readLine();
int nextByte = raw.read();
~~~

Nếu child gửi JSON, XML hoặc giao thức văn bản, chọn charset được hai phía thống nhất. UTF-8 là lựa chọn phổ biến nhưng không tự động đúng cho mọi chương trình native. Nếu child dùng encoding hệ điều hành, có thể dùng các phương thức không truyền Charset hoặc cấu hình child rõ ràng.

Khi dùng BufferedWriter, nhớ flush() nếu cần child nhận dữ liệu trước khi writer đóng. close() cũng flush trước khi đóng theo hợp đồng của Writer, nhưng nếu giao thức cần phản hồi từng phần trong lúc kết nối còn mở thì phải flush sau mỗi thông điệp thích hợp.

## 8. Đóng stdin là tín hiệu giao thức

Đóng writer gắn với stdin không chỉ giải phóng stream. Nó báo cho tiến trình con rằng phía cha đã gửi xong dữ liệu và không còn byte nào nữa.

Ví dụ child đọc cho đến EOF:

~~~java
String line;

while ((line = stdin.readLine()) != null) {
    handle(line);
}
~~~

Nếu Java cha ghi xong nhưng không đóng stdin, child có thể tiếp tục chờ dữ liệu mới và không bao giờ thoát vòng lặp. Khi Java cha gọi readAllLines() trên stdout, cả hai có thể chờ nhau.

Quy trình cho giao thức dạng “gửi hết rồi nhận kết quả”:

1. Khởi chạy Process.
2. Mở writer cho stdin.
3. Ghi toàn bộ request.
4. Flush nếu cần gửi dữ liệu ngay.
5. Đóng writer để gửi EOF.
6. Đọc stdout/stderr đến EOF.
7. Gọi waitFor() và kiểm tra exit code.
8. Rời khối try để Process.close() hoàn tất việc dọn dẹp.

Với giao thức tương tác lâu dài, không đóng stdin sau từng thông điệp. Thay vào đó, định nghĩa ranh giới thông điệp rõ ràng như newline, length prefix hoặc frame. Cần đồng thời đọc output và ghi input để không làm đầy pipe.

## 9. Timeout và kết thúc tiến trình có kiểm soát

Process.close() không nhận timeout. Nó đóng các luồng rồi chờ tiến trình kết thúc. Nếu child không phản hồi EOF hoặc tiếp tục chạy, close() có thể chờ vô hạn.

Nếu ứng dụng cần giới hạn thời gian, hãy quản lý timeout trước khi rời khối TWR:

~~~java
boolean exited = process.waitFor(30, TimeUnit.SECONDS);

if (!exited) {
    // Yêu cầu kết thúc theo cách thông thường.
    process.destroy();

    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        // Buộc kết thúc nếu child vẫn còn chạy.
        process.destroyForcibly();
        process.waitFor();
    }
}

int exitCode = process.exitValue();
~~~

waitFor(timeout, unit) trả true nếu tiến trình đã kết thúc trong thời hạn và false nếu hết thời gian chờ. destroy() yêu cầu hệ điều hành kết thúc tiến trình; hành vi bình thường hay cưỡng bức phụ thuộc nền tảng và implementation. destroyForcibly() yêu cầu kết thúc cưỡng bức, nhưng tiến trình có thể chưa dừng ngay tại thời điểm phương thức trả về. Gọi waitFor() để xác nhận nó đã kết thúc.

Trong khi chờ timeout, vẫn phải tiếp tục drain stdout/stderr. Nếu không, child có thể bị chặn vì pipe đầy và không thể tiến đến điểm kết thúc.

Không dùng exitValue() trước khi process kết thúc. Nếu process còn sống, phương thức ném IllegalThreadStateException.

## 10. Xử lý interruption và lỗi khi đóng

### Owner bị interrupt khi chờ

Process.close() có hành vi đặc biệt: nếu thread gọi close() bị interrupt trong khi chờ process, process bị destroyForcibly(), close() tiếp tục đợi cho đến khi process kết thúc rồi khôi phục trạng thái interrupt.

Nếu waitFor() trong phần thân try bị interrupt, nó ném InterruptedException và xóa trạng thái interrupt theo quy tắc của Java. Muốn Process.close() nhận được tín hiệu interrupt khi TWR bắt đầu dọn dẹp, hãy khôi phục trạng thái trước khi ném exception ra ngoài:

~~~java
try (Process process = new ProcessBuilder(command).start()) {
    try {
        int exitCode = process.waitFor();
        System.out.println(exitCode);
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw exception;
    }
}
~~~

Khi exception rời khỏi khối try, Process.close() được gọi trong lúc thread đã được đánh dấu interrupted. close() sẽ cưỡng bức kết thúc process nếu bị interrupt trong lúc chờ, tiếp tục chờ và khôi phục trạng thái interrupt.

Nếu ứng dụng có chính sách hủy riêng, có thể gọi destroy() hoặc destroyForcibly() tường minh trước khi thoát khối try. Không nuốt InterruptedException rồi tiếp tục chờ như chưa có yêu cầu hủy.

### IOException khi đóng stream

Process.close() có thể ném IOException nếu một stream không đóng được. Theo Javadoc, lỗi đóng stream được báo sau khi process đã kết thúc; các lỗi đóng bổ sung được gắn vào lỗi IOException đầu tiên dưới dạng suppressed exception.

Nếu phần thân try đã ném exception, lỗi từ close() được Java lưu trong getSuppressed(). Khi điều tra sự cố, xem cả exception chính và các suppressed exception.

### Không dựa vào garbage collection

Khi không còn tham chiếu đến Process, tiến trình con không tự động bị kill. Nó có thể tiếp tục chạy bất đồng bộ. Các handle/descriptor của stream có thể được implementation dọn dẹp khi không còn tham chiếu, nhưng điều đó không thay thế việc đóng tài nguyên một cách xác định.

Hãy dùng try-with-resources hoặc quản lý close() tường minh. Không dùng finalize() hay chờ GC để dừng tiến trình.

## 11. Process và tiến trình con do nó tạo ra

Process.close() quản lý Process đại diện cho tiến trình được khởi chạy. Nếu lệnh đó tự tạo thêm tiến trình con, không mặc định rằng đóng Process cha sẽ luôn kết thúc toàn bộ cây tiến trình.

Khi chương trình có thể sinh child process hoặc pipeline:

- Xác định tiến trình nào sở hữu từng child.
- Dùng ProcessHandle.children() hoặc descendants() để quan sát cây tiến trình khi cần.
- Có chính sách dừng child trước hoặc cùng lúc với parent.
- Chờ các tiến trình cần thiết kết thúc và xác nhận tài nguyên đã được giải phóng.
- Kiểm tra khác biệt hành vi giữa Windows, Linux và macOS.

ProcessBuilder.startPipeline() tạo một pipeline các Process. Các pipe giữa tiến trình trung gian được quản lý bởi API và không thể truy cập trực tiếp. Nếu khởi chạy pipeline, vẫn cần đóng từng Process được trả về và quản lý vòng đời của cả pipeline theo thứ tự phù hợp.

Không coi Process.close() trên một Process đơn lẻ là cơ chế quản lý toàn bộ process tree.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Child chờ mãi dù Java cha đã ghi dữ liệu | stdin chưa đóng nên child chưa nhận EOF | Đóng outputWriter() khi gửi xong request |
| Java cha chờ stdout nhưng child không kết thúc | Child đang chờ thêm input hoặc pipe stderr đã đầy | Đóng stdin và drain stdout/stderr đồng thời |
| Child bị block khi ghi stderr | Java cha chỉ đọc stdout | Đọc hai pipe đồng thời hoặc redirect/gộp stderr |
| Mất một phần output khi đóng Process | close() đóng stream trước khi dữ liệu được đọc hết | Đọc stdout/stderr đến EOF trước khi đóng Process |
| Không lấy được exit code | Gọi close() trước waitFor() | Gọi waitFor() và lấy exitValue trước khi rời TWR |
| Process.close() chờ vô hạn | Child không thoát khi pipe đóng | Dùng timeout, destroy(), destroyForcibly() và waitFor() |
| Process không kết thúc khi Java cha mất tham chiếu | GC không tự kill tiến trình con | Đóng Process tường minh bằng TWR |
| getErrorStream() luôn EOF | stderr đã redirect hoặc gộp vào stdout | Kiểm tra ProcessBuilder.redirectError() và redirectErrorStream() |
| getInputStream() luôn EOF | stdout đã redirect ra file hoặc inherit | Đọc file đích hoặc dùng cơ chế redirect phù hợp |
| Dữ liệu văn bản bị lỗi ký tự | Charset của cha và child không thống nhất | Chọn charset rõ ràng ở cả hai phía |
| Code đọc thiếu dữ liệu sau khi dùng Reader | Đọc cùng pipe bằng cả Reader và InputStream | Chọn một abstraction cho mỗi pipe |
| Dùng Process trong TWR không biên dịch trên JDK 25 | Process.close() được thêm từ JDK 26 | Biên dịch bằng JDK 26 trở lên hoặc quản lý vòng đời theo API của JDK cũ |

## 13. Ma trận kiểm thử

Có thể kiểm thử các trường hợp sau trên JDK 26:

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Process kết thúc bình thường | Child đọc stdin đến EOF rồi thoát | Writer đóng, stdout đọc hết, waitFor() trả exit code, Process.close() hoàn tất |
| Body ném exception | Cố ý ném exception trong khối try | Process.close() vẫn được gọi |
| Child không thoát sau EOF | Child bỏ qua stdin EOF và tiếp tục chạy | close() chờ; timeout và destroy phải được dùng nếu cần giới hạn thời gian |
| Child ghi nhiều stdout | Tạo output lớn hơn pipe buffer | Java cha phải drain output trong lúc child chạy |
| Child ghi nhiều stderr | Ghi dữ liệu lớn vào stderr | Đọc stderr song song hoặc redirect |
| stdout/stderr gộp | Bật redirectErrorStream(true) | Đọc cả hai qua inputReader(); errorReader() rỗng |
| Redirect ra file | redirectOutput và redirectError | Getter stream tương ứng trả null stream; dữ liệu nằm trong file |
| Thread owner bị interrupt khi close chờ | Interrupt thread đang đóng Process | Process bị destroyForcibly(), close chờ kết thúc và khôi phục interrupt |
| Child có tiến trình con | Child sinh thêm process | Kiểm tra descendants và quản lý vòng đời riêng |
| Charset khác nhau | Cố ý dùng charset không thống nhất | Phát hiện lỗi giải mã và chuẩn hóa encoding |

**Tiêu chí hoàn thành:** giải thích được Process.close() của JDK 26; sắp xếp đúng tài nguyên trong try-with-resources; biết đóng stdin để gửi EOF; đọc stdout và stderr mà không tạo deadlock; chọn redirect phù hợp; lấy exit code trước khi close; xử lý timeout và interruption; không phụ thuộc GC để dừng tiến trình; hiểu giới hạn của Process.close() đối với child process.

## 14. Khác biệt phiên bản và lưu ý nâng cấp

| Phiên bản | Khả năng liên quan |
|---|---|
| JDK 17 | Có outputWriter(), inputReader() và errorReader() với overload Charset |
| JDK 25 trở về trước | Process chưa có close() theo hợp đồng Closeable của JDK 26; không thể đặt Process trực tiếp trong try-with-resources |
| JDK 26 | Process triển khai Closeable/AutoCloseable; close() đóng reader/writer streams và chờ process kết thúc |
| JDK 27 | Tiếp tục có Process.close() với cùng hợp đồng API được công bố |

Khi build bằng JDK 26, có thể viết:

~~~java
try (Process process = new ProcessBuilder(command).start()) {
    // ...
}
~~~

Nếu dự án cần chạy trên JDK 25 hoặc thấp hơn, đoạn code trên không biên dịch với Process như resource vì API close() chưa có ở các release đó. Phải có lớp adapter quản lý stream và dừng process theo cách tương thích với release mục tiêu, hoặc đặt baseline runtime lên JDK 26.

Khi nâng cấp từ JDK 26 lên JDK 27, vẫn cần giữ các nguyên tắc: đọc dữ liệu trước close, lấy exit code bằng waitFor, đóng writer để gửi EOF, drain stdout/stderr và đặt timeout riêng nếu cần. Kiểm tra Javadoc của đúng JDK và implementation Process nếu dùng một provider không phải HotSpot chuẩn.

## 15. Tài liệu tham khảo chính thức

- [Java 26 Process API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html) — Process.close(), reader/writer streams, waitFor(), exitValue(), destroy() và interruption.
- [Java 26 ProcessBuilder API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html) — khởi chạy process, redirect stdin/stdout/stderr, gộp error stream và startPipeline().
- [Java 26 Process API – New API List](https://docs.oracle.com/en/java/javase/26/docs/api/new-list.html) — xác nhận Process.close() là API mới từ JDK 26.
- [Java 25 Process API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Process.html) — đối chiếu API trước khi Process có close().
- [Java 27 Process API Index](https://docs.oracle.com/en/java/javase/27/docs/api/index-files/index-3.html) — xác nhận Process.close() tiếp tục có trong JDK 27.
- [Java 26 AutoCloseable API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html) — cơ chế try-with-resources và xử lý lỗi khi đóng tài nguyên.
- [Java 26 Closeable API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Closeable.html) — hợp đồng đóng tài nguyên I/O.
- [Java Language Specification 26 – try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls26.pdf) — thứ tự khởi tạo và đóng ngược thứ tự tài nguyên.

Process.close() là API quản lý vòng đời được bổ sung trong JDK 26. Hãy đọc hết dữ liệu cần thiết và lấy exit code trước khi đóng Process. Với tiến trình có thể treo hoặc tạo nhiều output, cần quản lý timeout và đọc các pipe đúng cách; try-with-resources đảm bảo đóng tài nguyên nhưng không thay thế thiết kế giao thức I/O và chính sách dừng tiến trình.


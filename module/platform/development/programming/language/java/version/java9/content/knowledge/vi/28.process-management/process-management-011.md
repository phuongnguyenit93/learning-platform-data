# Tiêu thụ stdout, stderr và tránh bế tắc do bộ đệm

## Mục tiêu

Khi chạy một chương trình con bằng `ProcessBuilder`, Java cung cấp các luồng để chương trình cha gửi dữ liệu vào stdin và đọc dữ liệu từ stdout, stderr của tiến trình con. Nếu không tiêu thụ hai luồng đầu ra đúng cách, chương trình có thể bị treo dù cả hai tiến trình đều đang chạy.

Nguyên nhân thường gặp là **pipe buffer có dung lượng hữu hạn**. Khi tiến trình con ghi nhiều dữ liệu hơn bộ đệm có thể chứa mà chương trình cha chưa đọc, thao tác ghi của tiến trình con bị chặn. Nếu chương trình cha lại đang chờ tiến trình con kết thúc, hai bên sẽ chờ nhau vô thời hạn.

Cách xử lý cốt lõi là bắt đầu đọc stdout và stderr đồng thời ngay sau khi tiến trình được tạo, trước khi chờ tiến trình kết thúc. Nếu không cần phân biệt hai luồng, có thể gộp chúng hoặc chuyển hướng thẳng ra file, terminal hay thiết bị discard.

## 1. Ba luồng của Process

Khi gọi `ProcessBuilder.start()`, đối tượng `Process` đại diện cho tiến trình con. Các phương thức stream có hướng nhìn từ chương trình cha:

| Phương thức | Dữ liệu được truy cập | Hướng |
|---|---|---|
| `process.getOutputStream()` | stdin của tiến trình con | Cha ghi, con đọc |
| `process.getInputStream()` | stdout của tiến trình con | Con ghi, cha đọc |
| `process.getErrorStream()` | stderr của tiến trình con | Con ghi, cha đọc |

Tên `getInputStream()` dễ gây nhầm. Đây là luồng đầu vào của chương trình cha, nhưng dữ liệu đến từ stdout của chương trình con.

Với Java 17 trở lên, có thể lấy reader theo charset rõ ràng:

~~~java
BufferedReader stdout = process.inputReader(StandardCharsets.UTF_8);
BufferedReader stderr = process.errorReader(StandardCharsets.UTF_8);
~~~

`inputReader(Charset)` và `errorReader(Charset)` là các tiện ích hiện hành từ Java 17. Nếu cần hỗ trợ source level Java 9 đến Java 16, có thể bọc các stream tương ứng bằng `InputStreamReader` và `BufferedReader`:

~~~java
BufferedReader stdout = new BufferedReader(
        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)
);

BufferedReader stderr = new BufferedReader(
        new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8)
);
~~~

Chọn charset phù hợp với giao thức của chương trình con. Không nên dựa vào charset mặc định của máy nếu dữ liệu có thể chứa ký tự ngoài ASCII. Nếu stdout hoặc stderr chứa dữ liệu nhị phân, hãy đọc bằng byte stream thay vì giải mã thành văn bản.

Với mỗi channel, chọn một cách đọc: reader API hoặc byte stream. Không đọc đồng thời cùng một channel bằng cả `inputReader()` lẫn `getInputStream()`, vì hai cách này cùng tiêu thụ một nguồn dữ liệu.

## 2. Vì sao pipe buffer gây deadlock?

Khi dùng chế độ pipe mặc định của ProcessBuilder, stdout và stderr thường là hai pipe riêng. Mỗi pipe có dung lượng hữu hạn do hệ điều hành quản lý.

Giả sử chương trình cha thực hiện:

~~~java
Process process = new ProcessBuilder("some-command").start();
int exitCode = process.waitFor();

String stdout = new String(
        process.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8
);
~~~

Đoạn mã này có nguy cơ deadlock. Nếu tiến trình con ghi đủ dữ liệu làm đầy stdout hoặc stderr, nó phải chờ chương trình cha đọc bớt dữ liệu. Trong khi đó, chương trình cha đang chờ `waitFor()` trả về; tiến trình con không thể kết thúc cho đến khi ghi xong.

### Deadlock khi đọc tuần tự hai luồng

Một biến thể khác là đọc stdout đến EOF rồi mới đọc stderr:

~~~java
String stdout = readAll(process.getInputStream());
String stderr = readAll(process.getErrorStream());
~~~

Nếu tiến trình con ghi nhiều stderr trước khi đóng stdout, pipe stderr có thể đầy. Tiến trình con bị chặn khi ghi stderr nên không thể tiếp tục và đóng stdout; chương trình cha lại đang đợi stdout kết thúc nên không chuyển sang đọc stderr.

### Trình tự đúng

~~~text
ProcessBuilder.start()
        |
        v
Tạo hai tác vụ đọc độc lập
        |
        +------> Đọc stdout liên tục
        |
        +------> Đọc stderr liên tục
        |
        v
Đóng stdin nếu không gửi dữ liệu
        |
        v
waitFor(timeout)
        |
        v
Lấy kết quả hai tác vụ đọc
        |
        v
Kiểm tra exit code và xử lý kết quả
~~~

Hai luồng phải được tiêu thụ đồng thời. Có thể dùng hai thread, hai tác vụ trong ExecutorService hoặc một cơ chế bất đồng bộ phù hợp. Với một tiến trình con, hai tác vụ đọc độc lập là cách triển khai dễ hiểu và dễ kiểm tra.

## 3. Đọc stdout và stderr đồng thời bằng ExecutorService

Ví dụ cấu trúc:

~~~java
ExecutorService readers = Executors.newFixedThreadPool(2);

Future<String> stdoutFuture = readers.submit(
        () -> readAll(process.inputReader(StandardCharsets.UTF_8))
);

Future<String> stderrFuture = readers.submit(
        () -> readAll(process.errorReader(StandardCharsets.UTF_8))
);

process.getOutputStream().close();

int exitCode = process.waitFor();

String stdout = stdoutFuture.get();
String stderr = stderrFuture.get();

readers.shutdown();
~~~

Hai tác vụ đọc được gửi đi trước khi gọi `waitFor()`. Trong lúc thread chính chờ tiến trình con, các thread đọc vẫn liên tục lấy dữ liệu ra khỏi pipe để tiến trình con không bị chặn vì bộ đệm đầy.

Nếu chương trình con không cần nhận dữ liệu từ stdin, đóng `process.getOutputStream()` để gửi EOF. Một số chương trình con chờ đến khi stdin đóng mới xử lý xong hoặc thoát. Nếu cần gửi dữ liệu, hãy ghi và flush dữ liệu cần thiết, sau đó đóng stdin khi đã gửi hết.

Không gọi `get()` trên Future đọc stdout trước khi bắt đầu tác vụ đọc stderr. Cả hai tác vụ phải được khởi chạy độc lập trước khi chờ bất kỳ luồng nào hoàn tất.

## 4. Gộp stderr vào stdout khi không cần phân biệt

Nếu log lỗi và log thông thường có thể được xử lý như một luồng chung, dùng:

~~~java
Process process = new ProcessBuilder(command)
        .redirectErrorStream(true)
        .start();

try (BufferedReader output =
        process.inputReader(StandardCharsets.UTF_8)) {
    String line;
    while ((line = output.readLine()) != null) {
        System.out.println(line);
    }
}

int exitCode = process.waitFor();
~~~

Khi `redirectErrorStream(true)` được bật, stderr được gộp vào stdout của tiến trình con. Chương trình cha chỉ cần tiêu thụ một luồng qua `getInputStream()` hoặc `inputReader(...)`; `getErrorStream()` không còn cung cấp stderr riêng.

Cách này giảm số tác vụ đọc và tránh tình huống quên tiêu thụ một trong hai pipe. Đổi lại, chương trình cha không còn phân loại được dòng nào đến từ stdout hay stderr. Thứ tự quan sát là thứ tự dữ liệu đến trên luồng gộp, không phải một nhật ký có timestamp chính xác của từng lần ghi.

## 5. Chuyển hướng output thay vì tự đọc pipe

Không phải lúc nào chương trình cha cũng cần giữ output trong bộ nhớ.

### Ghi stdout và stderr vào file riêng

~~~java
Process process = new ProcessBuilder(command)
        .redirectOutput(stdoutFile.toFile())
        .redirectError(stderrFile.toFile())
        .start();

int exitCode = process.waitFor();
~~~

Hệ điều hành ghi dữ liệu trực tiếp vào file được chỉ định. Chương trình cha không cần tự đọc hai pipe; có thể đọc file sau khi tiến trình hoàn tất.

### Bỏ qua output không cần thiết

Từ Java 9, có thể chuyển hướng một luồng đến `ProcessBuilder.Redirect.DISCARD`:

~~~java
Process process = new ProcessBuilder(command)
        .redirectOutput(ProcessBuilder.Redirect.DISCARD)
        .redirectError(ProcessBuilder.Redirect.DISCARD)
        .start();

int exitCode = process.waitFor();
~~~

Chỉ dùng DISCARD khi chắc chắn không cần nội dung output để chẩn đoán hoặc xử lý nghiệp vụ.

### Cho tiến trình con dùng terminal của chương trình cha

Nếu muốn chương trình con hiển thị trực tiếp trên terminal hiện tại, có thể dùng:

~~~java
Process process = new ProcessBuilder(command)
        .inheritIO()
        .start();

int exitCode = process.waitFor();
~~~

`inheritIO()` kế thừa stdin, stdout và stderr của tiến trình cha. Khi các luồng được kế thừa thay vì nối vào pipe do chương trình cha đọc, không cần tạo tác vụ đọc riêng cho các luồng đó.

## 6. Đóng stdin và xử lý dữ liệu đầu vào

Deadlock không chỉ liên quan đến output. Tiến trình con có thể chờ dữ liệu ở stdin trong khi chương trình cha chờ tiến trình kết thúc.

Nếu chương trình con cần input:

~~~java
try (OutputStream childInput = process.getOutputStream()) {
    childInput.write("hello\n".getBytes(StandardCharsets.UTF_8));
    childInput.flush();
}
~~~

Đóng stream sau khi gửi hết dữ liệu để tiến trình con nhận EOF. Nếu không có input, đóng ngay:

~~~java
process.getOutputStream().close();
~~~

Không đóng stdin trước khi gửi xong dữ liệu mà chương trình con cần. Nếu input lớn, cần có chiến lược ghi và đọc song song phù hợp để tránh tình huống hai bên cùng chờ.

## 7. Timeout, exit code và dọn dẹp

Không nên chờ tiến trình con vô thời hạn nếu lệnh được chạy từ dữ liệu bên ngoài hoặc có thể treo.

Dùng overload timeout:

~~~java
boolean finished = process.waitFor(30, TimeUnit.SECONDS);

if (!finished) {
    process.destroyForcibly();
    process.waitFor();
}
~~~

- `waitFor(timeout, unit)` trả về true nếu tiến trình kết thúc trong thời gian cho phép.
- Nếu hết thời gian, `destroyForcibly()` yêu cầu chấm dứt tiến trình.
- Gọi `waitFor()` sau đó để xác nhận tiến trình đã kết thúc.
- Lấy exit code bằng `exitValue()` sau khi tiến trình đã kết thúc.

Exit code thường bằng 0 khi chương trình con báo thành công; quy ước cụ thể vẫn phụ thuộc chương trình được chạy. Không được bỏ qua stderr hoặc coi mọi output trên stderr là lỗi thất bại: nhiều công cụ ghi tiến độ hoặc cảnh báo lên stderr nhưng vẫn trả exit code 0.

Trong mã thực tế, luôn dọn dẹp executor và stream trong `finally` hoặc try-with-resources. Nếu tác vụ đọc thất bại sớm, hãy xử lý lỗi và cân nhắc kết thúc tiến trình con để nó không tiếp tục ghi vào pipe không còn được tiêu thụ.

## 8. Ví dụ hoàn chỉnh: đọc đồng thời lượng output lớn

Tệp `ProcessOutputDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

public class ProcessOutputDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "--child".equals(args[0])) {
            runChild();
            return;
        }

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        String javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java"
        ).toString();

        Process process = new ProcessBuilder(
                javaExecutable,
                "-cp",
                System.getProperty("java.class.path"),
                ProcessOutputDemo.class.getName(),
                "--child"
        ).start();

        ExecutorService readers = Executors.newFixedThreadPool(2);
        try {
            Future<String> stdoutFuture = readers.submit(
                    () -> readAll(process.inputReader(StandardCharsets.UTF_8))
            );
            Future<String> stderrFuture = readers.submit(
                    () -> readAll(process.errorReader(StandardCharsets.UTF_8))
            );

            // Child không cần input; gửi EOF để nó không chờ stdin.
            process.getOutputStream().close();

            if (!process.waitFor(30, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
                throw new IllegalStateException("Child process timed out");
            }

            int exitCode = process.exitValue();
            String stdout = stdoutFuture.get(10, TimeUnit.SECONDS);
            String stderr = stderrFuture.get(10, TimeUnit.SECONDS);

            System.out.println("exit code: " + exitCode);
            System.out.println("stdout lines: " + stdout.lines().count());
            System.out.println("stderr lines: " + stderr.lines().count());
            System.out.println("stdout last: "
                    + stdout.substring(stdout.lastIndexOf('\n') + 1));
            System.out.println("stderr last: "
                    + stderr.substring(stderr.lastIndexOf('\n') + 1));

            if (exitCode != 0) {
                throw new IllegalStateException("Child exited with " + exitCode);
            }
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
            readers.shutdownNow();
        }
    }

    private static String readAll(BufferedReader reader) throws IOException {
        try (reader) {
            return reader.lines().collect(Collectors.joining("\n"));
        }
    }

    private static void runChild() {
        for (int i = 0; i < 20_000; i++) {
            System.out.println("out-" + i);
            System.err.println("err-" + i);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all ProcessOutputDemo.java
java ProcessOutputDemo
~~~

Kết quả chuẩn:

~~~text
exit code: 0
stdout lines: 20000
stderr lines: 20000
stdout last: out-19999
stderr last: err-19999
~~~

Tiến trình con ghi 20.000 dòng vào mỗi pipe. Chương trình cha khởi chạy hai tác vụ đọc song song trước khi chờ tiến trình kết thúc, vì vậy cả hai pipe liên tục được tiêu thụ và tiến trình con không bị chặn do bộ đệm đầy.

Ví dụ thu toàn bộ output vào String để dễ kiểm tra. Với output không giới hạn hoặc rất lớn, không nên giữ tất cả trong bộ nhớ; hãy xử lý từng dòng, ghi ra file hoặc chuyển byte trực tiếp đến đích phù hợp.

## 9. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi `waitFor()` trước khi đọc output | Pipe có thể đầy, tiến trình con không thể kết thúc | Bắt đầu drain stdout và stderr trước khi chờ |
| Đọc hết stdout rồi mới đọc stderr | Pipe stderr có thể đầy trong lúc cha chờ EOF của stdout | Đọc hai luồng đồng thời hoặc gộp chúng |
| Chỉ đọc stdout và bỏ stderr | stderr vẫn có thể đầy và chặn tiến trình con | Tiêu thụ cả hai hoặc redirect stderr |
| Gọi `Future.get()` tuần tự trước khi khởi chạy reader còn lại | Một pipe có thể không được tiêu thụ | Submit cả hai tác vụ trước khi chờ |
| Không đóng stdin khi không gửi input | Chương trình con có thể chờ EOF mãi | Đóng `process.getOutputStream()` |
| Dùng charset mặc định | Nội dung tiếng Việt hoặc ký tự đa byte có thể bị giải mã sai | Chỉ định charset rõ ràng |
| Đọc toàn bộ output không giới hạn vào String | Có thể gây áp lực bộ nhớ hoặc OutOfMemoryError | Xử lý streaming hoặc redirect ra file |
| Dùng `redirectErrorStream(true)` nhưng vẫn chờ stderr riêng | Hai luồng đã được gộp | Đọc luồng input duy nhất |
| Chờ vô thời hạn một tiến trình không tin cậy | Lệnh có thể treo hoặc chờ input | Dùng timeout và chính sách hủy tiến trình |
| Xem mọi dòng stderr là thất bại | Nhiều chương trình dùng stderr cho cảnh báo hoặc tiến độ | Đánh giá cả exit code và hợp đồng của lệnh |

## 10. Checklist khi chạy tiến trình con

- Xác định rõ chương trình con có cần stdin hay không.
- Bắt đầu đọc stdout và stderr ngay sau khi start nếu giữ hai pipe riêng.
- Không gọi waitFor trước khi có tác vụ drain output.
- Đóng stdin sau khi gửi xong dữ liệu hoặc ngay lập tức nếu không cần input.
- Chọn giữa đọc riêng, gộp stderr, redirect ra file, DISCARD hoặc inheritIO theo yêu cầu.
- Chỉ định charset nếu xử lý output dạng văn bản.
- Dùng byte stream cho output nhị phân.
- Đặt timeout cho tiến trình có thể treo.
- Kiểm tra exit code và thu thập stderr phục vụ chẩn đoán.
- Dọn dẹp reader, executor và tiến trình trong mọi đường chạy.
- Với output lớn, xử lý từng phần thay vì tích lũy toàn bộ vào bộ nhớ.

Để tránh deadlock khi dùng Process, chương trình cha phải tiếp tục tiêu thụ mọi pipe mà tiến trình con có thể ghi. Đọc stdout và stderr đồng thời, đóng stdin đúng lúc và đặt giới hạn thời gian chờ giúp việc chạy tiến trình con ổn định hơn trên các môi trường khác nhau.
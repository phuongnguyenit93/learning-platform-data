# Tạo pipeline qua ProcessBuilder.startPipeline

Từ Java 9, `ProcessBuilder.startPipeline(List<ProcessBuilder>)` cho phép khởi chạy nhiều tiến trình hệ điều hành và nối đầu ra chuẩn (stdout) của tiến trình trước vào đầu vào chuẩn (stdin) của tiến trình kế tiếp. Cách này tạo thành một pipeline mà không cần tự tạo thread để sao chép dữ liệu giữa từng cặp tiến trình.

Pipeline hữu ích khi một tác vụ có thể chia thành các chương trình độc lập: chương trình đầu tạo dữ liệu, chương trình giữa lọc hoặc chuyển đổi, chương trình cuối tổng hợp hoặc lưu kết quả. Java quản lý các pipe nối giữa tiến trình; ứng dụng vẫn phải quản lý lỗi khởi chạy, luồng stderr, exit code và vòng đời từng tiến trình.

## 1. Pipeline tiến trình là gì?

Một pipeline là chuỗi tiến trình có kết nối dữ liệu theo hướng:

```text
Process A stdout  ──pipe──>  Process B stdin
Process B stdout  ──pipe──>  Process C stdin
Process C stdout  ─────────>  Java application
```

Mỗi tiến trình vẫn là một chương trình độc lập. Pipeline chỉ kết nối các luồng chuẩn để đầu ra của tiến trình trước trở thành dữ liệu đầu vào của tiến trình sau.

Ví dụ trong shell thường được viết dưới dạng `producer | filter | consumer`. Với Java, `ProcessBuilder.startPipeline` tạo kết nối tương tự nhưng không chạy lệnh qua shell. Mỗi `ProcessBuilder` mô tả một tiến trình riêng, gồm executable và các đối số của nó.

Cần phân biệt hai loại stream:

- `java.util.stream.Stream` là API xử lý dữ liệu trong JVM.
- `Process.getInputStream()`, `getOutputStream()` và `getErrorStream()` là các luồng byte giao tiếp giữa JVM và tiến trình con.

`startPipeline` thuộc API quản lý tiến trình và I/O hệ điều hành, không phải Stream API.

## 2. Cách gọi startPipeline

Chữ ký API:

```java
public static List<Process> startPipeline(
        List<ProcessBuilder> builders
) throws IOException
```

Danh sách `builders` mô tả các tiến trình theo đúng thứ tự pipeline. Phương thức khởi chạy chúng và nối stdout của mỗi tiến trình (trừ tiến trình cuối) vào stdin của tiến trình kế tiếp.

Ví dụ cấu trúc:

```java
ProcessBuilder first = new ProcessBuilder("program-a", "--export");
ProcessBuilder second = new ProcessBuilder("program-b", "--normalize");
ProcessBuilder third = new ProcessBuilder("program-c", "--store");

List<Process> processes = ProcessBuilder.startPipeline(
        List.of(first, second, third)
);
```

Danh sách `Process` trả về có thứ tự tương ứng với danh sách `ProcessBuilder` đầu vào. Phần tử đầu là tiến trình đầu pipeline; phần tử cuối là tiến trình cuối pipeline. Dùng các đối tượng `Process` này để đọc output cuối, theo dõi trạng thái, chờ hoàn tất và dừng tiến trình khi cần.

`List.of` có từ Java 9, cùng phiên bản với `startPipeline`. Nếu cần tương thích Java 8, API này không có sẵn; phải tự khởi chạy các tiến trình và nối luồng bằng cơ chế khác.

## 3. Quy tắc kết nối stdin, stdout và stderr

`startPipeline` tự thiết lập các pipe nội bộ:

- stdin của tiến trình đầu tiên là đầu vào của toàn pipeline. Ứng dụng có thể cấp dữ liệu cho nó qua `processes.get(0).getOutputStream()` hoặc cấu hình redirect phù hợp.
- stdout của tiến trình cuối cùng là đầu ra của toàn pipeline. Ứng dụng có thể đọc qua `processes.get(last).getInputStream()` hoặc redirect đến file/đích khác.
- stdout của các tiến trình ở giữa được nối trực tiếp tới stdin của tiến trình kế tiếp.
- stdin của các tiến trình ở giữa được nối từ stdout của tiến trình đứng trước.
- stderr của từng tiến trình là luồng riêng. Nó không tự động đi vào pipeline stdout.

Với pipeline nhiều hơn hai tiến trình, Java quản lý các kết nối nội bộ. Ứng dụng không đọc stdout của tiến trình giữa như một output độc lập vì stdout đó đang được nối sang stdin của tiến trình sau. Tương tự, stdin của tiến trình giữa nhận dữ liệu từ pipe trước đó.

### Redirect hợp lệ

Trong pipeline, stdin của tiến trình đầu và stdout của tiến trình cuối là hai đầu ngoài. Có thể cấu hình redirect ở hai đầu này. Các stdin/stdout nằm giữa pipeline phải dùng pipe nội bộ; cấu hình redirect xung đột với kết nối pipeline sẽ bị từ chối bằng `IllegalArgumentException`.

stderr của mỗi tiến trình có thể được redirect độc lập, ví dụ kế thừa stderr của JVM:

```java
ProcessBuilder builder = new ProcessBuilder(command)
        .redirectError(ProcessBuilder.Redirect.INHERIT);
```

Nếu dùng `redirectErrorStream(true)`, stderr được gộp vào stdout của chính tiến trình đó. Với một tiến trình nằm giữa pipeline, dữ liệu lỗi sau khi gộp cũng sẽ đi sang stdin của tiến trình kế tiếp. Chỉ bật tùy chọn này khi chương trình sau có thể xử lý cả dữ liệu thường lẫn thông báo lỗi.

Nếu cần tách stderr để ghi log, redirect stderr ra file hoặc để pipe và đọc `getErrorStream()` của từng tiến trình. Khi để stderr ở chế độ pipe, phải đọc nó đủ thường xuyên; nếu buffer đầy, tiến trình con có thể bị chặn khi ghi lỗi.

## 4. Ví dụ Java chạy được: producer nối với consumer

Ví dụ sau khởi chạy hai JVM con. Tiến trình `producer` ghi ba dòng UTF-8 ra stdout. Tiến trình `consumer` đọc stdin của nó, đếm các dòng bắt đầu bằng `ERROR` và ghi kết quả ra stdout. `startPipeline` nối hai tiến trình mà không cần ứng dụng tự sao chép byte giữa chúng.

Mã dùng chính lớp `Main` làm chương trình con với hai chế độ chạy. Vì vậy chỉ cần biên dịch một tệp.

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class Main {
    private static void writeLine(String value) throws IOException {
        System.out.write((value + "\n").getBytes(StandardCharsets.UTF_8));
        System.out.flush();
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("producer")) {
            writeLine("INFO starting");
            writeLine("ERROR disk unavailable");
            writeLine("INFO finished");
            return;
        }

        if (args.length == 1 && args[0].equals("consumer")) {
            long errors;
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                errors = reader.lines()
                        .filter(line -> line.startsWith("ERROR"))
                        .count();
            }
            writeLine("Error lines: " + errors);
            return;
        }

        String java = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").toLowerCase().contains("win")
                        ? "java.exe" : "java"
        ).toString();

        String classPath = System.getProperty("java.class.path");

        ProcessBuilder producer = new ProcessBuilder(
                java, "-cp", classPath, Main.class.getName(), "producer"
        ).redirectError(ProcessBuilder.Redirect.INHERIT);

        ProcessBuilder consumer = new ProcessBuilder(
                java, "-cp", classPath, Main.class.getName(), "consumer"
        ).redirectError(ProcessBuilder.Redirect.INHERIT);

        List<Process> processes = ProcessBuilder.startPipeline(
                List.of(producer, consumer)
        );

        try {
            Process last = processes.get(processes.size() - 1);
            String output;
            try (InputStream stream = last.getInputStream()) {
                output = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            }

            for (int i = 0; i < processes.size(); i++) {
                Process process = processes.get(i);
                if (!process.waitFor(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Process " + i + " timed out");
                }
                if (process.exitValue() != 0) {
                    throw new IllegalStateException(
                            "Process " + i + " exited with " + process.exitValue()
                    );
                }
            }

            writeLine("Pipeline output: " + output.strip());
            writeLine("Processes completed: " + processes.size());
        } catch (IOException | InterruptedException | RuntimeException exception) {
            processes.forEach(Process::destroyForcibly);
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw exception;
        }
    }
}
```

Lưu mã thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 Main.java
java Main
```

Kết quả stdout:

```text
Pipeline output: Error lines: 1
Processes completed: 2
```

Diễn giải:

1. Khi JVM chạy `Main` với đối số `producer`, chương trình chỉ ghi dữ liệu ra stdout rồi kết thúc. Stdout của tiến trình này được nối vào stdin của `consumer`.
2. Chế độ `consumer` đọc stdin đến EOF. Khi producer kết thúc và đóng đầu ghi của pipe, consumer nhận EOF và hoàn tất việc đếm.
3. JVM cha chỉ đọc stdout của tiến trình cuối trong danh sách `processes`. Output trung gian đã được chuyển trực tiếp qua pipe.
4. Ví dụ redirect stderr của cả hai tiến trình sang stderr của JVM cha, nên log lỗi không lẫn vào dữ liệu mà consumer đang lọc.
5. Chương trình kiểm tra exit code của từng tiến trình. Pipeline chỉ được xem là thành công khi mọi tiến trình kết thúc với mã 0.
6. Nếu bước đọc output, chờ tiến trình hoặc xử lý kết quả gặp lỗi, khối `catch` yêu cầu dừng các tiến trình còn lại. Khi bị interrupt, chương trình khôi phục interrupt flag trước khi truyền lỗi lên trên.

Ví dụ này cố ý dùng executable Java hiện tại và đối số riêng biệt để chạy trên Windows, Linux hoặc macOS mà không phụ thuộc lệnh shell như `grep`, `findstr` hay cú pháp pipe của terminal.

## 5. Xây dựng ProcessBuilder an toàn

Mỗi `ProcessBuilder` mô tả một lệnh độc lập. Nên truyền executable và từng đối số thành các phần tử riêng:

```java
ProcessBuilder builder = new ProcessBuilder(
        "/usr/bin/tool",
        "--input",
        inputFile.toString(),
        "--mode",
        "strict"
);
```

Không ghép toàn bộ lệnh thành một chuỗi rồi giả định Java tự phân tích dấu cách, dấu nháy hoặc ký tự pipe. `ProcessBuilder` không tự chạy shell; shell chỉ được chạy nếu chính bạn chọn shell làm executable và truyền script cho nó.

Các thuộc tính hữu ích:

- `directory(File)` đặt thư mục làm việc của tiến trình con. Nếu không cấu hình, tiến trình thường kế thừa thư mục làm việc hiện tại của JVM.
- `environment()` trả về map môi trường có thể chỉnh sửa trước khi start. Chỉ đặt biến môi trường cần thiết và tránh ghi đè cấu hình hệ thống ngoài ý muốn.
- `redirectInput`, `redirectOutput` và `redirectError` chọn nguồn/đích cho các luồng chuẩn khi redirect được phép.
- `redirectErrorStream(true)` gộp stderr vào stdout của cùng tiến trình.
- `command()` cho phép xem hoặc thay đổi danh sách executable và đối số trước khi khởi chạy.

Ví dụ đặt thư mục và biến môi trường:

```java
ProcessBuilder builder = new ProcessBuilder(
        executable,
        "--config",
        "app.conf"
);

builder.directory(workingDirectory.toFile());
builder.environment().put("APP_MODE", "batch");
```

Hãy kiểm tra executable có tồn tại và có quyền chạy trong môi trường triển khai. Đường dẫn tuyệt đối giúp giảm phụ thuộc vào PATH; nếu dùng tên executable ngắn, kết quả tìm kiếm phụ thuộc môi trường hệ điều hành.

## 6. Theo dõi tiến trình và exit code

`startPipeline` trả về một `Process` cho mỗi builder. Không có một exit code tổng hợp đại diện cho cả pipeline. Mỗi tiến trình có thể kết thúc thành công hoặc thất bại độc lập.

Các phương thức thường dùng:

| API | Vai trò |
|---|---|
| `waitFor()` | Chờ tiến trình kết thúc và trả exit code |
| `waitFor(timeout, unit)` | Chờ tối đa thời gian chỉ định; trả `false` nếu hết thời gian mà tiến trình chưa kết thúc |
| `exitValue()` | Lấy exit code nếu tiến trình đã kết thúc; nếu chưa, ném `IllegalThreadStateException` |
| `isAlive()` | Kiểm tra tiến trình còn chạy hay không |
| `destroy()` | Yêu cầu kết thúc tiến trình |
| `destroyForcibly()` | Yêu cầu kết thúc cưỡng bức |
| `onExit()` | Trả `CompletableFuture<Process>` hoàn tất khi tiến trình kết thúc |

Luôn kiểm tra tất cả tiến trình, không chỉ tiến trình cuối. Consumer có thể trả mã 0 dù producer đã lỗi sau khi gửi một phần dữ liệu; hoặc producer có thể thành công nhưng consumer thất bại khi lưu kết quả.

Một quy tắc nghiệp vụ thường dùng là:

```java
boolean success = processes.stream()
        .allMatch(process -> !process.isAlive() && process.exitValue() == 0);
```

Đoạn mã này chỉ kiểm tra trạng thái sau khi đã chờ các tiến trình hoàn tất. Không gọi `exitValue()` trên tiến trình còn chạy.

## 7. Tránh deadlock khi đọc output và error

Mỗi pipe có buffer hữu hạn. Nếu tiến trình con ghi nhiều dữ liệu hơn buffer mà JVM cha không đọc, tiến trình con có thể bị chặn khi ghi. Nếu tiến trình đó đang chặn pipeline phía sau, toàn bộ pipeline có thể đứng chờ.

Một số nguyên tắc:

- Đọc stdout của tiến trình cuối trong khi pipeline đang chạy hoặc redirect nó ra file nếu output lớn.
- Nếu stderr đang là pipe, đọc stderr của từng tiến trình song song với việc đọc stdout. Không đợi pipeline kết thúc rồi mới đọc một luồng stderr có thể đã đầy buffer.
- Nếu không cần phân tích stderr, có thể redirect sang file hoặc `Redirect.INHERIT`.
- Không gom stderr vào stdout trừ khi tiến trình kế tiếp có thể chấp nhận dữ liệu log như dữ liệu đầu vào.
- Tránh gọi `waitFor()` trên mọi tiến trình trước khi đọc các output có thể đầy buffer.

Ví dụ trên dùng stderr kế thừa và output cuối chỉ có một dòng nên việc đọc `readAllBytes()` là phù hợp. Với output lớn hoặc không giới hạn, nên xử lý theo buffer trong một thread/virtual thread hoặc redirect ra file, thay vì giữ toàn bộ nội dung trong heap.

## 8. EOF, đóng pipe và luồng dữ liệu

Một tiến trình đọc stdin thường tiếp tục chờ cho đến khi nhận EOF hoặc gặp lỗi. EOF trên pipe xuất hiện khi tất cả đầu ghi tương ứng đã đóng. Khi tiến trình trước kết thúc bình thường, hệ điều hành đóng stdout của nó và tiến trình sau có thể đọc đến EOF.

Nếu JVM cha ghi dữ liệu vào stdin của tiến trình đầu tiên thông qua `processes.get(0).getOutputStream()`, phải đóng stream đó khi đã gửi xong dữ liệu để tiến trình đầu nhận EOF:

```java
try (OutputStream input = processes.get(0).getOutputStream()) {
    input.write(payload);
}
// close() báo rằng JVM cha không gửi thêm dữ liệu cho stdin của tiến trình đầu.
```

Không đóng nhầm stream trung gian: các kết nối stdout/stdin giữa tiến trình được `startPipeline` quản lý. Đóng đầu vào của tiến trình đầu hoặc đầu ra của tiến trình cuối là quyết định của ứng dụng; các đầu nối nội bộ thuộc pipeline.

Nếu chương trình sau cần xử lý dữ liệu theo từng dòng, giao thức hai bên phải thống nhất encoding, delimiter, framing và quy tắc kết thúc. Pipe truyền byte; nó không tự hiểu chuỗi UTF-8, dòng văn bản hay cấu trúc JSON.

## 9. Lỗi khi khởi chạy và lỗi khi pipeline đang chạy

Có hai giai đoạn lỗi khác nhau.

**Lỗi khi khởi chạy**

`startPipeline` có thể ném `IOException` nếu một tiến trình không thể được tạo, chẳng hạn executable không tồn tại hoặc hệ điều hành từ chối khởi chạy. Nếu lỗi xảy ra sau khi một số tiến trình đã được khởi chạy, các tiến trình đã tạo sẽ bị hủy cưỡng bức để tránh để lại một phần pipeline chạy nền.

Cấu hình redirect không hợp lệ có thể dẫn đến `IllegalArgumentException`; danh sách hoặc phần tử null có thể dẫn đến `NullPointerException`. Kiểm tra cấu hình builder trước khi khởi chạy để lỗi dễ chẩn đoán.

**Lỗi sau khi pipeline đã chạy**

Khi phương thức đã trả về danh sách `Process`, lỗi runtime của một chương trình thường được thể hiện qua exit code khác 0, stderr hoặc việc pipeline bị đóng. `startPipeline` không tự biến exit code khác 0 thành ngoại lệ Java và cũng không tự rollback dữ liệu mà các chương trình đã xử lý.

Ứng dụng cần:

1. Đọc stderr hoặc log của từng tiến trình để có thông tin chẩn đoán.
2. Chờ và kiểm tra exit code của từng tiến trình.
3. Khi một bước thất bại, quyết định dừng các tiến trình còn lại hay để chúng kết thúc tự nhiên.
4. Đóng các stream do ứng dụng sở hữu.
5. Xác định output có phải dữ liệu hoàn chỉnh không trước khi công bố cho bước tiếp theo của nghiệp vụ.

Không mặc định rằng tiến trình cuối trả mã 0 nghĩa là mọi tiến trình trước đó đều thành công. Cũng không giả định dữ liệu chưa được chuyển chỉ vì một tiến trình trả mã lỗi; tiến trình có thể đã ghi một phần trước khi thất bại.

## 10. Timeout và dừng pipeline

Một tiến trình có thể treo do chờ input, deadlock nội bộ hoặc chương trình con không phản hồi. Dùng `waitFor(timeout, unit)` để đặt giới hạn chờ:

```java
if (!process.waitFor(30, TimeUnit.SECONDS)) {
    process.destroy();

    if (!process.waitFor(2, TimeUnit.SECONDS)) {
        process.destroyForcibly();
    }
}
```

Với pipeline, phải áp dụng chính sách timeout cho toàn bộ nhóm tiến trình. Khi một tiến trình thất bại hoặc hết hạn, các tiến trình còn lại có thể đang chờ dữ liệu từ nó. Dừng chúng theo thứ tự và chính sách phù hợp; sau đó chờ chúng kết thúc để thu hồi tài nguyên.

Nếu thread đang chờ bằng `waitFor()` bị interrupt, `InterruptedException` được ném. Nên khôi phục interrupt flag khi truyền lỗi lên tầng gọi và thực hiện cleanup các tiến trình mà ứng dụng sở hữu.

`destroy()` là yêu cầu kết thúc thông thường; tiến trình có thể không dừng ngay. `destroyForcibly()` yêu cầu kết thúc cưỡng bức, nhưng không phải rollback những file hoặc dữ liệu đã được ghi trước đó.

## 11. Khi nào nên dùng startPipeline?

Dùng `startPipeline` khi:

- Có nhiều executable độc lập đã được thiết kế để trao đổi dữ liệu qua stdin/stdout.
- Dữ liệu có thể truyền tuần tự qua pipe, không cần ứng dụng giữ toàn bộ kết quả trung gian trong bộ nhớ.
- Cần kết hợp công cụ hệ điều hành với ứng dụng Java.
- Mỗi bước có thể được theo dõi riêng qua `Process`, stderr và exit code.

Cân nhắc cách khác khi:

- Các bước chỉ là xử lý dữ liệu trong JVM: Java collection, Stream API hoặc một pipeline xử lý nội bộ thường đơn giản hơn.
- Cần giao thức trao đổi phức tạp hai chiều giữa nhiều tiến trình: socket hoặc IPC chuyên dụng có thể dễ kiểm soát hơn.
- Cần lưu checkpoint, retry từng bản ghi hoặc đảm bảo exactly-once: pipe đơn thuần không cung cấp các đảm bảo đó.
- Các tiến trình cần truyền dữ liệu nhị phân có cấu trúc: hãy định nghĩa framing, length prefix, version và encoding rõ ràng.

## 12. Lỗi thường gặp

- **Cho rằng startPipeline chạy shell command:** phương thức khởi chạy executable theo từng builder; ký tự `|` không tự tạo pipe nếu không có shell.
- **Chỉ kiểm tra tiến trình cuối:** cần kiểm tra exit code của mọi tiến trình trong pipeline.
- **Không đọc stdout cuối hoặc stderr:** buffer đầy có thể làm tiến trình con bị chặn.
- **Gộp stderr vào stdout tùy tiện:** log lỗi có thể bị chuyển thành dữ liệu đầu vào của tiến trình sau.
- **Redirect stdin/stdout ở tiến trình giữa:** các đầu nối giữa pipeline phải được giữ cho pipe nội bộ.
- **Chờ tiến trình trước khi đọc output lớn:** có thể deadlock khi pipe buffer đầy.
- **Không đóng stdin của tiến trình đầu:** tiến trình đọc stdin có thể chờ EOF vô thời hạn.
- **Retry toàn bộ pipeline sau lỗi:** một phần dữ liệu có thể đã được xử lý; cần thiết kế idempotency hoặc checkpoint ở tầng ứng dụng.
- **Bỏ qua timeout và cleanup:** tiến trình còn sống có thể giữ tài nguyên hoặc tiếp tục thay đổi dữ liệu sau khi JVM cha đã báo lỗi.

## 13. Checklist trước khi chạy pipeline

- Danh sách builder có đúng thứ tự producer → transformer → consumer không?
- Mỗi executable, đối số, thư mục làm việc và biến môi trường đã được xác định rõ chưa?
- Redirect stdin/stdout chỉ được đặt ở các đầu ngoài của pipeline chưa?
- stderr được tách, kế thừa hay gộp vào stdout theo đúng nhu cầu chưa?
- JVM cha có đọc output và error đủ nhanh để tránh pipe buffer bị đầy không?
- Có kiểm tra exit code của tất cả tiến trình không?
- Có timeout và chiến lược dừng/cleanup khi một bước thất bại không?
- Giao thức dữ liệu có quy định encoding, framing, EOF và cách xử lý dữ liệu một phần không?
- Có cơ chế tránh xử lý trùng khi cần retry sau lỗi không?

`ProcessBuilder.startPipeline` từ Java 9 giúp kết nối nhiều tiến trình qua stdin/stdout bằng pipe do Java thiết lập. API trả về từng `Process` để ứng dụng kiểm soát vòng đời và kết quả của từng bước. Pipeline đáng tin cậy cần quản lý cả stdout, stderr, EOF, timeout, exit code và dữ liệu đã chuyển một phần; bản thân việc nối pipe không thay thế các chính sách lỗi và tính toàn vẹn dữ liệu của ứng dụng.

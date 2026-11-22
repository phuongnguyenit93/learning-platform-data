# Giới hạn dữ liệu đầu vào khi tạo lệnh từ nội dung bên ngoài

## 1. Đầu vào bên ngoài phải có vai trò dữ liệu rõ ràng

Một ứng dụng Java có thể cần chạy công cụ bên ngoài để tạo báo cáo, chuyển đổi tài liệu hoặc kiểm tra một tệp. Người dùng có thể cung cấp mã báo cáo, chế độ xử lý hay giới hạn số bản ghi.

Nếu ứng dụng nhận nguyên một chuỗi “lệnh tùy ý”, phạm vi quyền rất rộng. Thiết kế dễ kiểm soát hơn là:

```text
Yêu cầu nghiệp vụ
      |
Kiểm tra từng trường
      |
Chuyển thành giá trị có kiểu, nằm trong miền cho phép
      |
Ứng dụng chọn executable và các tùy chọn cố định
      |
Đưa giá trị đã kiểm tra vào đúng vị trí đối số dữ liệu
```

Điểm cốt lõi không chỉ là loại bỏ vài ký tự đặc biệt. Cần xác định **người gửi được phép điều khiển phần nào của thao tác**.

`ProcessBuilder` vẫn là API phù hợp trên Java hiện đại. Ví dụ trong bài chạy với Java 17+ và chỉ khởi chạy một chương trình Java con do chính ví dụ quản lý.

## 2. Phân biệt ba loại đầu vào

| Thành phần | Ai nên quyết định? | Ví dụ |
| --- | --- | --- |
| Executable | Cấu hình tin cậy của ứng dụng | Đường dẫn công cụ đã triển khai |
| Cấu trúc tùy chọn | Mã ứng dụng hoặc tập lựa chọn hữu hạn | Một trong summary/detail |
| Giá trị dữ liệu | Có thể lấy từ bên ngoài nhưng phải kiểm tra | Mã báo cáo, số lượng, đường dẫn được cấp quyền |

Không cho đầu vào người dùng trở thành executable chỉ vì nó vượt một regex “không có dấu chấm phẩy”. Một tên executable khác vẫn có thể làm một việc hoàn toàn ngoài phạm vi được cho phép.

Cũng không nhận danh sách tùy chọn tùy ý rồi coi đó chỉ là dữ liệu. Một tùy chọn hợp lệ của công cụ có thể bật ghi đè, truy cập mạng hoặc tải cấu hình.

Hợp đồng nên gần với nghiệp vụ, ví dụ:

```text
jobId: 1..32 ký tự ASCII thuộc tập đã chọn
mode: chỉ summary hoặc detail
limit: số nguyên 1..30
```

Đây là lựa chọn cho một dịch vụ giả định, không phải chính sách chung cho mọi công cụ hay mọi ngôn ngữ người dùng.

## 3. Danh sách đối số giúp tách cấu trúc lệnh khỏi giá trị

Cách thường dùng:

```java
ProcessBuilder builder = new ProcessBuilder(
        trustedExecutable,
        "--mode", validatedMode,
        "--job", validatedJobId);
```

Đây là đoạn minh họa; các biến phải được cấp từ cấu hình/hợp đồng phù hợp. Mỗi phần tử biểu diễn một thành phần của command theo quy tắc nền tảng và executable đích.

Đừng ghép tất cả thành một chuỗi rồi tự cắt theo dấu cách:

```java
// Không dùng cách tự tách này cho một command line tổng quát.
String[] pieces = combinedCommand.split(" ");
```

Nó không hiểu đúng đường dẫn có khoảng trắng, quoting hay ngữ pháp của công cụ.

Không tự thêm dấu nháy quanh từng giá trị chỉ vì nhìn thấy khoảng trắng. Khi dùng danh sách đối số, việc truyền thêm dấu nháy có thể khiến chương trình con nhận chính ký tự nháy, hoặc đi qua quy tắc xử lý nền tảng khác với ý định.

[ProcessBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html) quy định command là danh sách chuỗi và lưu ý cách một danh sách được diễn giải còn phụ thuộc hệ điều hành. Cần kiểm thử trên nền tảng và executable được triển khai, đặc biệt ở Windows và với chương trình có bộ phân tích command line riêng.

### Không tự đưa shell vào giữa nếu không cần

Nếu executable được chọn là một shell và ứng dụng truyền một chuỗi lệnh qua tùy chọn của shell, chuỗi ấy lại bị diễn giải như ngôn ngữ shell.

Vì thế, danh sách ProcessBuilder chứa shell vẫn có thể quay về vấn đề ghép lệnh. Bỏ lớp shell khi công cụ có thể được gọi trực tiếp là cách giảm một tầng diễn giải.

Script hoặc wrapper cũng cần được xem như một thành phần của hợp đồng. Không mặc định tệp bat/cmd hoặc script trên mọi nền tảng có cùng cách truyền đối số với executable native.

## 4. Không qua shell vẫn có thể bị điều khiển qua đối số

Giả sử một công cụ chấp nhận tên tệp, nhưng chuỗi được truyền bắt đầu bằng dấu gạch ngang. Công cụ có thể hiểu nó là một tùy chọn thay vì tên tệp.

Đây là khác biệt giữa:

- **Chèn lệnh qua shell:** dữ liệu trở thành cấu trúc lệnh.
- **Chèn/điều khiển đối số:** dữ liệu thay đổi ý nghĩa tùy chọn của chính executable đích.

Danh sách đối số giúp giữ ranh giới truyền dữ liệu, nhưng không tự quyết định công cụ đích sẽ hiểu đối số ấy ra sao.

Một số CLI hỗ trợ dấu `--` để kết thúc phần tùy chọn:

```java
new ProcessBuilder(trustedExecutable, fixedOption, "--", fileName);
```

Đây chỉ là đoạn minh họa cho **công cụ có tài liệu hỗ trợ quy ước đó**. Không thêm -- một cách phổ quát: có công cụ không hỗ trợ, hỗ trợ ở vị trí khác hoặc còn có cú pháp diễn giải riêng cho giá trị.

Ngay cả một đối số duy nhất cũng có thể là ngôn ngữ hoặc tham chiếu tài nguyên, như biểu thức, URL, mẫu tệp hay tệp cấu hình. Kiểm tra theo ngữ nghĩa của đối số đó, không chỉ theo số phần tử command.

OWASP khuyến nghị tránh gọi lệnh hệ điều hành khi có API phù hợp, đồng thời kết hợp tách tham số với xác thực đầu vào khi thật sự cần gọi công cụ. Xem [OS Command Injection Defense](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html).

## 5. Thiết kế giới hạn theo từng trường

| Trường | Cách kiểm tra hữu ích | Sai lầm cần tránh |
| --- | --- | --- |
| Chế độ | Ánh xạ từ tập chuỗi hữu hạn sang enum/giá trị cố định | Cho phép nguyên chuỗi tùy chọn tùy ý |
| Số lượng | Giới hạn độ dài, parse, kiểm tra miền và chuẩn hóa lại thành số | Chỉ kiểm tra toàn chữ số nhưng cho số quá lớn |
| Mã định danh | Giới hạn độ dài, tập ký tự và cấu trúc phù hợp nghiệp vụ | Dùng một blacklist ngắn cho mọi trường |
| Đường dẫn | Xác định root được phép, quyền sở hữu và đích thực tế | Chỉ tìm ký tự .. hoặc so tiền tố chuỗi |
| Văn bản tự do | Giới hạn theo hợp đồng, truyền như dữ liệu, cân nhắc stdin/tệp | Đặt thẳng vào chuỗi shell hoặc tùy chọn cấu hình |
| URL | Cho phép giao thức/đích theo quyền nghiệp vụ | Coi URL hợp cú pháp là được phép truy cập mọi nơi |

Kiểm tra độ dài trước khi chạy regex hoặc parse giúp đầu vào bất thường không tạo chi phí xử lý không cần thiết.

Định nghĩa đơn vị độ dài: `String.length()` đếm đơn vị UTF-16, không phải số byte UTF-8 hay số ký tự người dùng cảm nhận. Nếu giới hạn cuối nằm ở giao thức byte hoặc tệp đầu vào, cần kiểm tra thêm đúng đơn vị ấy.

Không xóa ký tự lạ rồi âm thầm chạy một giá trị khác. Nếu hợp đồng không chấp nhận đầu vào, từ chối rõ; nếu chuẩn hóa, nói rõ chuẩn hóa nào được cho phép và kiểm tra lại giá trị cuối.

Chuỗi rỗng, null, ký tự NUL, ký tự điều khiển và xuống dòng cũng phải được xét theo từng vai trò. Một trường mã định danh ngắn thường không cần chấp nhận chúng; một trường nội dung nhiều dòng lại có thể cần, nhưng nên truyền qua giao thức dữ liệu thích hợp.

## 6. Đường dẫn hợp lệ cú pháp chưa đủ quyền truy cập

Path.of thành công chỉ cho biết chuỗi có thể được biểu diễn thành Path trên nền tảng đó. Nó không chứng minh người gửi được phép chọn tệp ấy.

Với đầu vào là tên một tài nguyên do dịch vụ quản lý, có thể ưu tiên nhận **mã tài nguyên**, rồi ứng dụng tra ra đường dẫn tin cậy. Cách này thu hẹp quyền hơn việc nhận đường dẫn bất kỳ.

Nếu phải nhận đường dẫn tương đối:

1. Xác định root được phép từ cấu hình tin cậy.
2. Từ chối dạng tuyệt đối nếu hợp đồng chỉ cho tương đối.
3. Resolve và normalize theo Path.
4. Kiểm tra chứa trong root bằng quan hệ Path, không bằng startsWith trên String.
5. Nếu tệp phải tồn tại, xem xét đường dẫn thực sau khi giải symbolic link/junction và quyền truy cập.

Theo [Path.toRealPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toRealPath(java.nio.file.LinkOption...)), việc xác định đường dẫn thực liên quan tới hệ thống tệp và các liên kết. Normalize chủ yếu xử lý cấu trúc đường dẫn, không tự giải mọi liên kết.

Kiểm tra đường dẫn rồi đưa cho tiến trình con mở sau đó còn có khoảng cách thời gian kiểm tra–sử dụng. Nếu người ngoài có thể thay liên kết hoặc thư mục trong khoảng ấy, chỉ normalize/toRealPath tại một thời điểm chưa tạo ranh giới tuyệt đối.

Với tệp đầu ra chưa tồn tại, cũng không thể gọi toRealPath trên chính tệp rồi mặc định xong. Cần chính sách cho thư mục cha, quyền tạo/ghi đè và quyền sở hữu root. Đây là phần của thiết kế thao tác tệp, không phải một regex command line.

## 7. Ví dụ đầy đủ: hợp đồng nghiệp vụ trước ProcessBuilder

Ví dụ nhận ba trường: mã công việc, chế độ và giới hạn. Chỉ yêu cầu hợp lệ mới được chuyển thành danh sách đối số.

Chương trình con chỉ in các giá trị nhận được, không đọc/ghi tài nguyên nghiệp vụ hay gọi shell. Một lớp Java được dùng cho cả cha và con để thí nghiệm chạy độc lập.

Lưu thành `BoundedProcessInputDemo.java`:

```java
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

public class BoundedProcessInputDemo {
    private static final Pattern JOB_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,31}");

    enum Mode {
        SUMMARY, DETAIL;

        String cliValue() {
            return name().toLowerCase(Locale.ROOT);
        }
    }

    record Job(String id, Mode mode, int limit) {}

    private static Job parseRequest(
            String id, String modeText, String limitText) {
        if (id == null || id.length() > 32
                || !JOB_ID.matcher(id).matches()) {
            throw new IllegalArgumentException("invalid job id");
        }

        Mode mode;
        if ("summary".equals(modeText)) {
            mode = Mode.SUMMARY;
        } else if ("detail".equals(modeText)) {
            mode = Mode.DETAIL;
        } else {
            throw new IllegalArgumentException("invalid mode");
        }

        if (limitText == null
                || !limitText.matches("[0-9]{1,2}")) {
            throw new IllegalArgumentException("invalid limit syntax");
        }

        int limit = Integer.parseInt(limitText);
        if (limit < 1 || limit > 30) {
            throw new IllegalArgumentException("limit out of range");
        }

        return new Job(id, mode, limit);
    }

    private static void expectRejected(
            String label, String id, String mode, String limit) {
        try {
            parseRequest(id, mode, limit);
            throw new AssertionError("request should be rejected");
        } catch (IllegalArgumentException e) {
            System.out.println("Rejected: " + label);
        }
    }

    private static Process startChild(Job job) throws Exception {
        String executable =
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java";

        String java = Path.of(
                System.getProperty("java.home"), "bin", executable)
                .toString();

        return new ProcessBuilder(
                java,
                "-cp", System.getProperty("java.class.path"),
                BoundedProcessInputDemo.class.getName(),
                "child",
                "--job", job.id(),
                "--mode", job.mode().cliValue(),
                "--limit", Integer.toString(job.limit()))
                .inheritIO()
                .start();
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 7 && "child".equals(args[0])) {
            System.out.println("Child arguments: " + (args.length - 1));
            System.out.println("Job value: " + args[2]);
            System.out.println("Mode value: " + args[4]);
            System.out.println("Limit value: " + args[6]);
            return;
        }

        Job accepted = parseRequest("report_2026", "summary", "5");

        expectRejected("leading option", "-danger", "summary", "5");
        expectRejected("path syntax", "../other", "summary", "5");
        expectRejected("unexpected punctuation", "ok;extra", "summary", "5");
        expectRejected("newline", "ok\nextra", "summary", "5");
        expectRejected("too long", "a".repeat(33), "summary", "5");
        expectRejected("unknown mode", "ok", "custom", "5");
        expectRejected("zero limit", "ok", "summary", "0");
        expectRejected("nonnumeric limit", "ok", "summary", "five");

        Process child = startChild(accepted);
        try {
            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("child timed out");
            }
            System.out.println("Exit code: " + child.exitValue());
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("child did not stop");
                }
            }
        }
    }
}
```

Chạy:

```shell
javac BoundedProcessInputDemo.java
java BoundedProcessInputDemo
```

Stdout khi chạy thành công:

```text
Rejected: leading option
Rejected: path syntax
Rejected: unexpected punctuation
Rejected: newline
Rejected: too long
Rejected: unknown mode
Rejected: zero limit
Rejected: nonnumeric limit
Child arguments: 6
Job value: report_2026
Mode value: summary
Limit value: 5
Exit code: 0
```

Không có giá trị bị từ chối nào được gửi thành một lệnh để “thử xem nó làm gì”. Chúng chỉ đi qua hàm kiểm tra trong JVM cha.

### Những bảo đảm cụ thể của ví dụ

- Executable Java và tên lớp con đến từ môi trường triển khai của chương trình, không từ trường dữ liệu người dùng.
- Người gửi chỉ chọn một trong hai chế độ đã định nghĩa.
- Mã công việc có miền ký tự và độ dài hẹp vì đây là mã, không phải tên hiển thị tự do.
- Giới hạn được parse và kiểm tra 1..30, rồi chuyển lại bằng Integer.toString.
- Các tùy chọn --job, --mode và --limit là chuỗi cố định do cha tạo.
- Giá trị không được ghép thành một chuỗi shell.
- Lỗi được minh họa bằng nhãn đã biết thay vì in nguyên dữ liệu có xuống dòng vào log.

Đây là một hợp đồng minh họa, không phải bộ xác thực chung cho mọi CLI. Nhánh child chỉ phục vụ quan sát argv trong thí nghiệm; nó giả định được cha này gọi theo giao thức cố định và không phải một dịch vụ nhận yêu cầu độc lập.

Trong ứng dụng thực tế, cấu hình executable, classpath hoặc script wrapper cũng phải thuộc quyền quản lý tin cậy. Có đường dẫn tuyệt đối mà nội dung executable/thư viện lại bị người ngoài thay được thì ranh giới chưa đủ.

## 8. Không dùng một regex chung thay cho hợp đồng

Regex ở ví dụ cố tình chỉ nhận mã ASCII. Nếu trường là tên người, nhãn tiếng Việt hoặc nội dung tài liệu, dùng cùng regex ấy có thể loại dữ liệu hợp lệ mà vẫn không giải quyết đúng nguy cơ của công cụ đích.

Thiết kế theo vai trò:

- Mã nội bộ: tập ký tự hẹp có thể phù hợp.
- Tên hiển thị: thường cần Unicode và quy tắc độ dài riêng.
- Nội dung lớn: cân nhắc stdin hoặc tệp tạm do ứng dụng sở hữu, kèm giới hạn dung lượng.
- Lựa chọn công việc: enum hoặc ánh xạ hữu hạn.
- Biểu thức của công cụ: cần parser/tập ngữ nghĩa riêng nếu cho phép, không chỉ truyền nguyên chuỗi.

Tránh phụ thuộc vào blacklist một số dấu shell. Các shell và nền tảng có cú pháp khác nhau; công cụ không qua shell vẫn có thể diễn giải một giá trị hợp cú pháp theo hướng ngoài mong muốn.

Nếu API thư viện Java đã thực hiện trực tiếp đúng công việc cần làm, không cần đi qua tiến trình chỉ để có một lệnh ngắn. Mỗi lần thêm lớp shell/công cụ là thêm hợp đồng phải hiểu và giới hạn.

## 9. Command chỉ là một phần của ngữ cảnh chạy

ProcessBuilder còn mang thư mục làm việc, môi trường và chuyển hướng I/O. Chúng cũng có thể thay đổi hành vi:

| Thuộc tính | Quyết định cần kiểm soát |
| --- | --- |
| executable | Nguồn cài đặt, đường dẫn và quyền sửa |
| working directory | Công cụ tìm tệp tương đối/cấu hình ở đâu |
| environment | Biến cấu hình, đường dẫn tải thư viện và hành vi công cụ |
| stdin | Ai cung cấp dữ liệu, khi nào kết thúc và dung lượng tối đa |
| stdout/stderr | Thu ra đâu, bao nhiêu và ai được đọc |
| redirect output | Có được ghi đè tệp do người dùng chọn không |

Môi trường ban đầu của ProcessBuilder là bản sao của môi trường tiến trình Java. Không cho người gửi tùy ý thêm/sửa mọi biến môi trường chỉ vì chúng không nằm trong command.

Có thể xây dựng tập biến môi trường được phép theo công cụ, nhưng không xóa sạch một cách máy móc rồi giả định mọi runtime vẫn hoạt động đúng. Cần hiểu biến nào thật sự bắt buộc trên nền tảng triển khai.

ProcessBuilder có thể thay đổi được; không chia sẻ một builder đang cấu hình giữa nhiều yêu cầu rồi để yêu cầu khác thay executable hoặc đối số trước start. Tạo cấu hình riêng từ các giá trị đã kiểm tra giúp quyền sở hữu rõ hơn.

## 10. Giới hạn đầu vào còn bao gồm giới hạn tài nguyên

Đầu vào hợp cú pháp vẫn có thể yêu cầu một khối lượng việc quá lớn. Ví dụ limit một tỷ, tài liệu hàng GB hoặc số lượng yêu cầu không giới hạn đều có thể vượt năng lực dịch vụ.

Cần giới hạn phù hợp:

- Độ dài từng trường và tổng kích thước dữ liệu.
- Số đối số và số lựa chọn mà yêu cầu được quyền điều khiển.
- Kích thước dữ liệu stdin/tệp đầu vào.
- Số tiến trình được chạy đồng thời và số việc chờ.
- Thời gian chạy, ngân sách cleanup.
- Lượng stdout/stderr được lưu giữ.
- Dung lượng/tệp đầu ra theo mô hình triển khai.

Các giới hạn này thuộc quyền sở hữu tác vụ, không phải một tính năng tự có của ProcessBuilder.

waitFor có thời hạn không tự dừng tiến trình. Bỏ đọc output sau khi vượt giới hạn nhưng để pipe đầy cũng có thể làm con kẹt; phải có cách drain, chuyển hướng hoặc dừng phù hợp. Hủy yêu cầu Java không tự hoàn tác công việc mà tiến trình con đã thực hiện.

Không giả định giới hạn kích thước command line của hệ điều hành đủ bảo vệ ứng dụng. Từ chối sớm theo hợp đồng nghiệp vụ tốt hơn chờ start thất bại sau khi đã chuẩn bị một yêu cầu quá lớn.

## 11. Kiểm tra trước khi đưa dữ liệu vào lệnh

Một luồng kiểm tra rõ ràng:

1. Xác thực và kiểm tra quyền thực hiện loại công việc.
2. Đọc từng trường theo một hợp đồng đầu vào hữu hạn.
3. Chuẩn hóa có chủ đích rồi kiểm tra kiểu, độ dài, miền giá trị.
4. Xác định executable, option, môi trường và thư mục từ cấu hình tin cậy.
5. Tạo danh sách đối số riêng cho yêu cầu.
6. Chạy với cơ chế giới hạn tài nguyên và thu kết quả.
7. Diễn giải mã thoát/output theo hợp đồng công cụ.

Chỉ bước 5 dùng ProcessBuilder là chưa đủ. Ngược lại, validation tốt cũng không cứu được thiết kế đưa lại giá trị vào một chuỗi shell ở bước sau.

## 12. Tự kiểm tra

**Mỗi giá trị là một phần tử command có loại bỏ mọi nguy cơ không?**  
Không. Công cụ vẫn có thể hiểu giá trị như option, biểu thức hoặc tài nguyên ngoài phạm vi.

**Chặn dấu chấm phẩy có đủ không?**  
Không. Cần giới hạn theo vai trò và tránh biến dữ liệu thành cấu trúc lệnh.

**Có thể nhận tên executable từ người dùng nếu không có khoảng trắng không?**  
Không nên suy ra quyền chạy từ hình dạng chuỗi. Executable phải thuộc phạm vi ứng dụng cho phép.

**Dấu -- luôn giải quyết đối số bắt đầu bằng - không?**  
Không. Chỉ dùng theo tài liệu của công cụ đích và đúng vị trí nó hỗ trợ.

**Path.normalize có giải quyết mọi symbolic link và cuộc đua tệp không?**  
Không. Cần xét đích thực, quyền sở hữu và thời điểm sử dụng.

Ranh giới đáng tin đến từ một thao tác có phạm vi rõ: ứng dụng chọn công cụ và cấu trúc lệnh, còn đầu vào bên ngoài chỉ cung cấp những giá trị dữ liệu đã được cho phép và giới hạn theo đúng nghĩa của chúng.

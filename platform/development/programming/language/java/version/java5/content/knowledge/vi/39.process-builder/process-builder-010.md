# Nguy cơ đầy bộ đệm và deadlock khi không tiêu thụ đầu ra

## 1. Tiến trình con ghi dữ liệu vào một đường ống hữu hạn

Khi tạo tiến trình bằng `ProcessBuilder`, đầu ra chuẩn và đầu ra lỗi mặc định được nối tới tiến trình Java cha qua các đường ống (pipe).

Từ phía Java:

| Stream của Process | Chiều dữ liệu |
| --- | --- |
| `getOutputStream()` | Cha ghi → stdin của con |
| `getInputStream()` | Cha đọc ← stdout của con |
| `getErrorStream()` | Cha đọc ← stderr của con |

Tên phương thức nhìn từ phía tiến trình cha. `getInputStream()` là luồng **đọc đầu ra của con**, không phải đầu vào mà con đọc.

Pipe có bộ đệm hữu hạn. Khi bộ đệm đầy, bên ghi có thể phải chờ bên đọc lấy dữ liệu ra. API Process cảnh báo việc không đọc/ghi kịp thời có thể làm tiến trình bị chặn, thậm chí tạo deadlock; xem [Process và giới hạn bộ đệm I/O](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html).

Dung lượng thực tế phụ thuộc hệ điều hành và cách triển khai. Không dựa vào một con số cố định như “đầu ra dưới 64 KiB luôn an toàn”.

## 2. Vòng chờ khi cha đợi con thoát trước khi đọc

Đoạn sau dễ có lỗi với công cụ tạo nhiều đầu ra:

```java
// Ví dụ nguy hiểm: tiến trình con có thể tạo nhiều stdout/stderr.
Process process = builder.start();
int code = process.waitFor();
String output = new String(
        process.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8);
```

Giả sử con ghi nhiều stdout:

```text
Cha: waitFor() chờ con kết thúc
                    ↓
Con: cần ghi tiếp trước khi kết thúc
                    ↓
Pipe stdout đầy, con chờ cha đọc
                    ↓
Cha chưa đọc vì đang chờ con kết thúc
                    └──────────────────→ vòng chờ
```

Không có yêu cầu nào rằng tiến trình con phải tiếp tục ghi được vô hạn. Việc `start()` thành công chỉ xác nhận tiến trình đã được tạo, không xác nhận luồng dữ liệu đã được phục vụ.

Lỗi này thường xuất hiện muộn: dữ liệu thử ít nên chạy được, nhưng dữ liệu thật hoặc mức log cao làm pipe đầy.

## 3. Đọc stdout xong rồi mới đọc stderr vẫn có thể treo

Một cách sửa chưa đủ:

```java
// Ví dụ vẫn nguy hiểm nếu cả hai stream đều là PIPE.
byte[] output = process.getInputStream().readAllBytes();
byte[] errors = process.getErrorStream().readAllBytes();
int code = process.waitFor();
```

Tình huống có thể xảy ra:

1. Cha đọc stdout và chờ EOF của stdout.
2. Con ghi nhiều stderr.
3. Pipe stderr đầy vì chưa có bên đọc.
4. Con chờ ghi stderr, nên chưa kết thúc và chưa tạo điều kiện kết thúc stdout.
5. Cha vẫn đang chờ stdout hoàn tất, chưa chuyển sang đọc stderr.

Vì vậy thứ tự đọc tuần tự không giải quyết được hai luồng dữ liệu độc lập.

Nguyên tắc là: **mọi pipe có thể nhận dữ liệu phải được phục vụ trong lúc tiến trình còn có khả năng ghi**, hoặc phải được chuyển hướng để không cần cha đọc pipe đó.

## 4. Chọn một chính sách đầu ra ngay trước start()

Có vài mô hình phù hợp với các nhu cầu khác nhau:

| Nhu cầu | Cách tổ chức |
| --- | --- |
| Cần phân biệt stdout và stderr | Đọc hai stream đồng thời |
| Chấp nhận trộn log và kết quả | `redirectErrorStream(true)`, đọc một stream |
| Chỉ cần ghi log ra tệp | Chuyển hướng stdout và stderr ra tệp |
| Chỉ cần hiện lên đích xuất của cha | Dùng chuyển hướng `INHERIT` phù hợp hoặc `inheritIO()` |
| Không cần giữ đầu ra | Chuyển hướng sang `Redirect.DISCARD` |

Chính sách là thuộc tính của `ProcessBuilder` dùng khi tạo tiến trình. Đổi builder sau `start()` không sửa đường ống của tiến trình đã chạy. Xem [ProcessBuilder và cấu hình I/O](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html).

### Gộp stderr vào stdout

```java
// Mã minh họa trước start().
builder.redirectErrorStream(true);
Process process = builder.start();
// Đọc đầu ra gộp từ process.getInputStream().
```

Cách này giảm số stream đầu ra cần tiêu thụ xuống một, nhưng **vẫn phải đọc stream gộp**. Gộp rồi bỏ mặc nó vẫn có nguy cơ đầy.

Đổi lại, không còn phân biệt bằng stream dữ liệu nào từ stdout và dữ liệu nào từ stderr. Nếu stdout chứa JSON, CSV hoặc dữ liệu nhị phân cho máy đọc, trộn thông báo lỗi vào đó có thể phá định dạng. Không chọn gộp chỉ vì mã đọc ngắn hơn.

## 5. Ví dụ đầy đủ: đọc đầu ra gộp trong khi chờ tiến trình

Chương trình sau tự chạy một bản Java con của chính lớp đó:

- Con ghi 16 MiB vào stdout và 16 MiB vào stderr.
- Cha gộp hai stream trước khi khởi động.
- Một tác vụ đọc bắt đầu tiêu thụ trong lúc con đang chạy.
- Luồng chính chờ tiến trình với thời hạn.
- Sau khi con thoát, cha tiếp tục chờ bên đọc hoàn tất và kiểm tra số byte.

Tệp `PipeDrainDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class PipeDrainDemo {
    private static void emitChildOutput() throws IOException {
        byte[] block = new byte[8192];
        for (int i = 0; i < 2048; i++) {
            System.out.write(block);
            System.err.write(block);
        }
        System.out.flush();
        System.err.flush();
    }

    private static long drain(InputStream input) throws IOException {
        try (input) {
            byte[] buffer = new byte[8192];
            long total = 0;
            for (int count; (count = input.read(buffer)) != -1;) {
                total += count;
            }
            return total;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("child")) {
            emitChildOutput();
            return;
        }

        Path bin = Path.of(System.getProperty("java.home"), "bin");
        Path java = bin.resolve("java");
        if (!Files.isRegularFile(java)) {
            java = bin.resolve("java.exe");
        }

        ProcessBuilder builder = new ProcessBuilder(
                java.toString(), "-cp", System.getProperty("java.class.path"),
                PipeDrainDemo.class.getName(), "child");
        builder.redirectErrorStream(true);
        Process process = builder.start();
        ExecutorService reader = Executors.newSingleThreadExecutor();

        try {
            Future<Long> bytes = reader.submit(
                    () -> drain(process.getInputStream()));
            process.getOutputStream().close();

            if (!process.waitFor(20, TimeUnit.SECONDS)) {
                throw new IOException("Child process timed out");
            }
            long total = bytes.get(5, TimeUnit.SECONDS);
            System.out.println("exitCode=" + process.exitValue());
            System.out.println("mergedBytes=" + total);
        } finally {
            try {
                if (process.isAlive()) {
                    process.destroyForcibly();
                    if (!process.waitFor(5, TimeUnit.SECONDS)) {
                        throw new IOException("Child process did not terminate");
                    }
                }
            } finally {
                reader.shutdownNow();
                process.getInputStream().close();
                process.getErrorStream().close();
                process.getOutputStream().close();
            }
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac PipeDrainDemo.java
java PipeDrainDemo
```

Kết quả:

```text
exitCode=0
mergedBytes=33554432
```

Mỗi lần lặp, con ghi hai khối 8192 byte. Có 2048 lần lặp:

```text
2048 × 8192 × 2 = 33554432 byte
```

Đó là 32 MiB đầu ra gộp. Byte trong khối là 0; chúng chỉ dùng để tạo lượng dữ liệu xác định, không được cha in lên màn hình.

Hàm `drain` dùng một bộ đệm 8192 byte và biến đếm `long`, không tích toàn bộ đầu ra vào một mảng lớn.

### Những điểm cần chú ý trong ví dụ

- Tác vụ đọc được gửi **trước** `waitFor()`.
- Dù luồng chính đang chờ con, tác vụ đọc vẫn lấy byte ra khỏi pipe.
- Cha đóng stream ghi stdin vì con trong ví dụ không cần đầu vào.
- `waitFor` có thời hạn không tự hủy tiến trình; mã dọn dẹp mới yêu cầu `destroyForcibly()` nếu con còn sống.
- Sau khi yêu cầu hủy, chương trình chờ thêm để quan sát việc kết thúc.
- Khi tiến trình đã thoát, vẫn chờ tác vụ đọc hoàn tất; việc có exit code và việc đã xử lý hết đầu ra là hai mốc khác nhau.

Ví dụ chỉ tạo một tiến trình Java con trực tiếp, không sinh cây tiến trình. Nó minh họa vòng đời hữu hạn và không phải một bộ điều khiển mọi kiểu tiến trình, giao thức stdin hoặc cây tiến trình của hệ điều hành.

Các thời hạn phục vụ ví dụ. Khi chạy chương trình thật, chọn theo loại công việc và báo rõ lỗi tiến trình, lỗi đọc hoặc lỗi dọn dẹp; không coi việc tăng timeout là cách sửa pipe bị bỏ đọc.

## 6. Nếu giữ stdout và stderr riêng, phải có đủ khả năng đọc đồng thời

Có thể tổ chức hai tác vụ đọc độc lập:

```java
// Mã minh họa: readers là ExecutorService có ít nhất hai luồng
// sẵn sàng phục vụ; drain đọc đến EOF và trả số byte.
Future<Long> stdoutBytes = readers.submit(
        () -> drain(process.getInputStream()));
Future<Long> stderrBytes = readers.submit(
        () -> drain(process.getErrorStream()));

// Luồng điều phối quản lý deadline và vòng đời process ở đây.
```

Một nhóm thực thi chỉ có một luồng rồi gửi hai tác vụ đọc vẫn có thể lặp lại lỗi đọc tuần tự: tác vụ đầu chờ EOF, tác vụ thứ hai còn nằm trong hàng đợi.

Không xếp hai tác vụ đọc vào một nhóm mà mọi luồng đã bị các công việc khác chiếm và đang chờ chính tiến trình này. Cần bảo đảm các bên tiêu thụ có cơ hội chạy.

Khi cần lưu nội dung, mỗi bên đọc phải có chính sách riêng:

- Ghi vào tệp hoặc đích lưu phù hợp.
- Giữ một phần giới hạn trong bộ nhớ.
- Đếm hoặc bỏ dữ liệu không cần.
- Báo lỗi đọc về bộ điều phối.

Chỉ khởi động một thread rồi bỏ qua ngoại lệ của nó chưa đủ. Nếu bên đọc chết sớm, con có thể tiếp tục ghi đến khi pipe đầy. Cần theo dõi bên đọc cũng như theo dõi tiến trình.

## 7. Không giữ đầu ra vô hạn trong heap

`readAllBytes()` đọc toàn bộ dữ liệu còn lại vào bộ nhớ. Nó có thể phù hợp khi có giới hạn đầu ra nhỏ và đáng tin, nhưng không phải giải pháp chung cho công cụ có log lớn hoặc không giới hạn. Xem [InputStream.readAllBytes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html#readAllBytes()).

Giải quyết pipe đầy bằng cách chứa mọi byte vào một `ByteArrayOutputStream` không giới hạn có thể chuyển vấn đề từ chặn I/O sang hết bộ nhớ.

Nếu chỉ muốn giữ tối đa một phần log:

```text
Đọc liên tục
    ↓
Còn trong giới hạn lưu? → giữ lại
Đã đủ giới hạn?        → tiếp tục đọc nhưng bỏ phần không giữ
```

Không ngừng đọc ngay khi bộ đệm lưu nội dung đã đầy, trừ khi đồng thời có chính sách dừng tiến trình phù hợp. Ngừng lưu và ngừng tiêu thụ pipe là hai hành động khác nhau.

Nếu dùng hàng đợi trung gian có dung lượng giới hạn, phải xét khi hàng đợi đầy. Bên đọc bị chặn ở hàng đợi cũng sẽ ngừng tiêu thụ pipe và truyền áp lực ngược trở lại con.

Đó có thể là điều khiển tốc độ có chủ ý, nhưng phải được thiết kế; nó không tự loại bỏ nguy cơ vòng chờ.

## 8. Đích nhận đầu ra cũng có thể quá chậm

Ví dụ chuyển thẳng mọi dòng đọc được vào một hệ thống log đồng bộ có thể khiến bên đọc chờ log. Nếu log lại phụ thuộc vào tài nguyên mà tiến trình con hoặc bộ điều phối đang giữ, vòng chờ mới có thể xuất hiện.

Cần kiểm tra toàn bộ đường đi:

```text
Con → pipe → bên đọc Java → hàng đợi/log/tệp → nơi lưu cuối
```

Một bên đọc tồn tại không có nghĩa dữ liệu được tiêu thụ đủ nhanh mãi mãi. Với lượng dữ liệu lớn, phải quyết định giữa:

- Chấp nhận giảm tốc tiến trình con.
- Mở rộng năng lực đích ghi.
- Giới hạn lượng công việc đồng thời.
- Bỏ hoặc rút gọn phần log không thiết yếu theo chính sách rõ ràng.

Chuyển hướng sang tệp bỏ được trách nhiệm đọc pipe của cha cho stream đó, nhưng vẫn có giới hạn tốc độ ghi và dung lượng đĩa. `INHERIT` cũng phụ thuộc đích xuất mà tiến trình cha đang dùng.

## 9. EOF, dòng văn bản và available()

### available() bằng 0 không có nghĩa đã xong

```java
// Ví dụ sai nếu dùng để kết luận đã đọc hết đầu ra.
while (input.available() > 0) {
    consume(input.read());
}
```

`available()` chỉ ước lượng lượng byte có thể đọc ngay mà không chặn. Bằng 0 có thể nghĩa chưa có dữ liệu tại thời điểm đó, không phải EOF.

Đọc đến khi `read(...)` trả `-1` theo giao thức stream, hoặc dừng theo chính sách hủy đã thiết kế.

### readLine() không nhận được newline thì sao?

Nếu con không ghi ký tự xuống dòng, `BufferedReader.readLine()` có thể chưa trả về một dòng dù bên dưới đang nhận byte. Với một dòng cực dài, nó còn có thể tích lũy nhiều nội dung trong bộ nhớ.

Vì vậy:

- Không thấy dòng log mới không tự chứng minh pipe chưa được đọc.
- Không chọn đọc theo dòng cho dữ liệu nhị phân.
- Chọn charset đúng khi giải mã văn bản.
- Giới hạn độ dài hoặc có cách xử lý khối nếu đầu ra có thể không phân dòng hợp lý.

Ví dụ chính đếm byte để tập trung vào cơ chế pipe, tránh phụ thuộc newline hoặc charset.

## 10. Stdin cũng có thể tạo vòng chờ hai chiều

Một giao thức tương tác có thể có vòng phụ thuộc khác:

```text
Cha ghi lượng lớn stdin → pipe stdin đầy
Con muốn ghi stdout trước khi đọc tiếp stdin → pipe stdout đầy
Cha chưa đọc stdout vì đang bận ghi hết stdin
```

Khi vừa gửi đầu vào lớn vừa nhận đầu ra, cần các hoạt động có khả năng tiến triển đồng thời hoặc một giao thức yêu cầu/phản hồi theo khối phù hợp.

Nếu con chờ EOF stdin trước khi kết thúc, cha phải đóng `process.getOutputStream()` sau khi gửi đủ dữ liệu. Chỉ flush không báo EOF.

Nhưng không đóng stdin sớm khi chương trình con còn cần nhận dữ liệu. Việc đóng, flush và thứ tự thông điệp phải đi theo hợp đồng của chương trình được chạy.

## 11. Timeout và hủy không thay cho việc tiêu thụ đầu ra

`waitFor(timeout, unit)` trả `false` khi tiến trình chưa kết thúc trong thời hạn. Nó không tự:

- Hủy tiến trình.
- Đóng mọi stream.
- Dừng các tác vụ đọc.
- Thu thập phần log còn lại.
- Dừng mọi tiến trình cháu.

`destroyForcibly()` cũng là yêu cầu kết thúc; có thể cần chờ để quan sát tiến trình đã thật sự dừng. Một `Future.cancel(true)` của tác vụ đọc không bảo đảm mọi thao tác đọc native đang chặn sẽ lập tức được giải phóng chỉ bằng ngắt luồng.

Cần có trình tự quản lý tài nguyên: phát hiện lỗi, quyết định dừng, yêu cầu tiến trình kết thúc, xử lý stream và đợi các bên đọc theo giới hạn phù hợp.

Nếu chương trình con tạo thêm tiến trình và chúng giữ các đầu pipe, vòng đời EOF có thể phức tạp hơn vòng đời của một Process trực tiếp. Phải quản lý cây tiến trình theo phạm vi công việc; không coi exit của một PID là bằng chứng mọi bên dùng pipe đã kết thúc.

Nếu không cần đọc đầu ra, lựa chọn rõ ràng trước start có thể đơn giản hơn:

```java
// Mã minh họa: chỉ dùng khi thật sự không cần giữ hai loại đầu ra.
builder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
builder.redirectError(ProcessBuilder.Redirect.DISCARD);
Process process = builder.start();
```

Các dạng chuyển hướng chuẩn được mô tả trong [ProcessBuilder.Redirect](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.Redirect.html).

## 12. Chẩn đoán tình huống “process không chịu thoát”

Khi gặp treo, kiểm tra theo chuỗi:

1. Cha đang ở `waitFor`, đọc stdout, đọc stderr hay ghi stdin?
2. Mỗi stream đang là PIPE, được gộp, chuyển tệp, kế thừa hay bỏ?
3. Bên đọc của từng pipe còn sống không; có bị kẹt ở hệ thống log hoặc hàng đợi không?
4. Con có thể đang chờ ghi, chờ đầu vào hay chờ một công việc khác?
5. Deadline có bao phủ cả chờ tiến trình và hoàn tất bên đọc không?
6. Có tiến trình khác giữ tài nguyên hoặc đầu pipe không?

Thread dump Java có thể thấy luồng cha đang chờ Process và các luồng đọc. Nhưng một vòng chờ qua pipe và tiến trình hệ điều hành không nhất thiết được báo bởi bộ phát hiện deadlock khóa Java.

Bài tập: giữ `redirectErrorStream(true)` nhưng xóa tác vụ đọc trong ví dụ. Vì sao việc gộp hai stream chưa đủ? Vì con vẫn ghi vào một pipe hữu hạn mà không có bên tiêu thụ. Tùy môi trường, nó có thể bị chặn trước khi hoàn thành; timeout chỉ giúp phát hiện việc chưa xong.

Điều cần bảo đảm là **mọi đầu ra có thể được tạo đều có đường tiêu thụ đang hoạt động, với bộ nhớ và vòng đời được quản lý rõ ràng**.

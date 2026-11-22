# Các luồng stdin, stdout và stderr của Process

## 1. Nhìn hướng dữ liệu từ tiến trình nào?

Khi `ProcessBuilder.start()` tạo tiến trình con, đối tượng `Process` trong JVM cha cho phép trao đổi dữ liệu với ba luồng chuẩn của tiến trình đó.

Điểm dễ nhầm là tên phương thức được nhìn từ phía JVM cha:

| Luồng của tiến trình con | Hướng dữ liệu | Phương thức trên `Process` mà cha sử dụng |
| --- | --- | --- |
| stdin — đầu vào chuẩn | Cha ghi → con đọc | `getOutputStream()` |
| stdout — đầu ra chuẩn | Con ghi → cha đọc | `getInputStream()` |
| stderr — đầu ra chẩn đoán | Con ghi → cha đọc | `getErrorStream()` |

Sơ đồ:

```text
JVM cha                                  Tiến trình con
getOutputStream()  ─── ghi dữ liệu ────→ stdin
getInputStream()   ←── đọc dữ liệu ───── stdout
getErrorStream()   ←── đọc chẩn đoán ─── stderr
```

`getOutputStream()` không có nghĩa “lấy stdout của con”. Nó là luồng mà **cha ghi ra**, nối tới stdin của con. Ngược lại, `getInputStream()` là luồng mà **cha đọc vào**, lấy dữ liệu từ stdout của con.

Bảng trên áp dụng khi các kênh dùng pipe mặc định, chưa được chuyển hướng sang tệp hoặc kế thừa từ tiến trình cha. Xem [Java Process API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html).

## 2. Ba luồng phục vụ ba vai trò khác nhau

Một công cụ xử lý văn bản có thể:

- Đọc nội dung cần xử lý từ stdin.
- Ghi kết quả chính sang stdout.
- Ghi cảnh báo hoặc thông tin chẩn đoán sang stderr.

Tách stdout và stderr giúp ứng dụng giữ kết quả máy đọc được mà không trộn log vào dữ liệu. Ví dụ stdout có thể chứa JSON, còn stderr chứa thông báo tiến độ.

Tuy nhiên, tên “error” không có nghĩa mọi nội dung trên stderr đều là lỗi khiến chương trình thất bại. Một công cụ có thể ghi cảnh báo hoặc tiến độ vào stderr rồi trả mã thoát 0. Ngược lại, một tiến trình có thể trả mã khác 0 dù stderr rỗng.

Muốn kết luận thành công cần xem hợp đồng của công cụ, mã thoát và dữ liệu mong đợi. Không dùng điều kiện “stderr không rỗng” như phép kiểm tra lỗi duy nhất.

## 3. Dữ liệu là byte; văn bản cần thống nhất bộ mã

Các getter cơ bản trả `InputStream` hoặc `OutputStream`, tức luồng byte. Nếu giao tiếp bằng văn bản, dùng lớp chuyển đổi với bộ mã (charset) phù hợp:

```java
BufferedWriter inputToChild = new BufferedWriter(
        new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8));

BufferedReader outputFromChild = new BufferedReader(
        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
```

Đây là đoạn minh họa cần các import `java.io.*`, `java.nio.charset.StandardCharsets` và một biến `process` đã được khởi chạy. Chương trình đầy đủ bên dưới xử lý cả stderr.

Chọn UTF-8 ở phía Java không ép một công cụ bên ngoài tự đổi bộ mã. Hai đầu phải có cùng hợp đồng. Nếu công cụ phát dữ liệu nhị phân như ảnh hoặc tệp nén, giữ dạng byte và không đưa qua `Reader`.

Cũng không đọc cùng một luồng đồng thời bằng cả `InputStream` thô và một `BufferedReader`. Reader có thể đọc trước vào bộ đệm; hai cách đọc cạnh tranh sẽ làm việc quản lý dữ liệu khó dự đoán. Chọn một cách truy cập cho mỗi kênh.

## 4. Ghi, flush và đóng stdin là ba việc khác nhau

Khi cha ghi dữ liệu qua một writer có bộ đệm:

1. `write()` có thể mới đưa ký tự vào bộ đệm.
2. `flush()` đẩy phần đang đệm xuống luồng nền.
3. `close()` hoàn tất writer và đóng đầu ghi pipe; con có thể quan sát EOF sau khi đọc hết dữ liệu đã gửi.

EOF là dấu hiệu hết dữ liệu của luồng, không phải một ký tự đặc biệt mà cha cần tự chèn vào chuỗi.

Nếu con đọc stdin cho tới EOF, chỉ `flush()` chưa đủ để nó kết thúc. Cha giữ đầu ghi mở rồi chờ con, trong khi con vẫn chờ thêm đầu vào, có thể khiến cả hai chờ nhau.

Nếu giao thức dùng nhiều lượt hỏi–đáp trên cùng stdin thì không đóng sau mỗi thông điệp. Khi đó cần `flush()` đúng lúc và quy ước ranh giới thông điệp, chẳng hạn xuống dòng hoặc độ dài. Đóng đầu ghi chỉ khi giao thức thực sự đã hết phần gửi.

Nếu không cần gửi gì nhưng công cụ có thể đợi stdin, đóng `process.getOutputStream()` ngay sau khi khởi chạy là cách báo rằng không có đầu vào nữa, với điều kiện stdin vẫn đang dùng pipe.

## 5. Vì sao phải xử lý stdout và stderr đồng thời?

Pipe có dung lượng bộ đệm hữu hạn. Giả sử con đang ghi rất nhiều stderr nhưng cha chỉ đọc stdout. Khi stderr đầy:

```text
Con đợi ghi thêm stderr
Cha đợi stdout hoặc đợi con kết thúc
Không bên nào tiếp tục
```

Do đó, hai mẫu dễ gây treo là:

- Gọi `waitFor()` trước rồi mới bắt đầu đọc hai kênh.
- Đọc stdout tới EOF hoàn toàn rồi mới đọc stderr.

Chúng có thể chạy được với ví dụ đầu ra nhỏ, nhưng không an toàn với công cụ tạo nhiều dữ liệu. [Java Process API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html) lưu ý nguy cơ tiến trình bị chặn khi các luồng không được xử lý kịp thời.

Các cách thường dùng là đọc hai kênh bằng hai tác vụ đồng thời, gộp stderr vào stdout nếu chấp nhận mất phân biệt kênh, hoặc chuyển hướng sang tệp/kế thừa I/O để không phải tự thu thập.

Nếu trao đổi đầu vào rất lớn hoặc tương tác lâu dài, cả việc ghi stdin cũng cần được phối hợp. Không xem việc chỉ thêm hai luồng đọc là lời giải cho mọi giao thức tương tác.

## 6. Chương trình đầy đủ: gửi một dòng, nhận hai kênh riêng

Ví dụ sau dùng một JVM con có hành vi rõ ràng:

- Đọc các dòng stdin đến EOF.
- Ghi nội dung nhận được ra stdout với tiền tố `OUT:`.
- Ghi số dòng đã đọc ra stderr với tiền tố `ERR:`.
- Kết thúc bình thường.

Lưu thành `ProcessStreamsDemo.java`, dùng JDK 17 trở lên:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ProcessStreamsDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            child();
            return;
        }

        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String javaPath = Path.of(
                System.getProperty("java.home"), "bin", executable).toString();
        Process process = new ProcessBuilder(
                javaPath, "-cp", System.getProperty("java.class.path"),
                ProcessStreamsDemo.class.getName(), "--child").start();

        ExecutorService readers = Executors.newFixedThreadPool(2);
        try {
            Future<String> stdout = readers.submit(
                    () -> readSmallOutput(process.getInputStream()));
            Future<String> stderr = readers.submit(
                    () -> readSmallOutput(process.getErrorStream()));

            try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
                    process.getOutputStream(), StandardCharsets.UTF_8))) {
                writer.write("Hello Java");
                writer.newLine();
            }

            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child process timed out");
            }

            String out = stdout.get(5, TimeUnit.SECONDS);
            String err = stderr.get(5, TimeUnit.SECONDS);
            System.out.println("stdout=" + out);
            System.out.println("stderr=" + err);
            System.out.println("exit=" + process.exitValue());
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
            process.getInputStream().close();
            process.getErrorStream().close();
            process.getOutputStream().close();
            readers.shutdownNow();
        }
    }

    private static String readSmallOutput(InputStream stream) throws IOException {
        try (stream) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .stripTrailing();
        }
    }

    private static void child() throws IOException {
        BufferedReader input = new BufferedReader(new InputStreamReader(
                System.in, StandardCharsets.UTF_8));
        BufferedWriter output = new BufferedWriter(new OutputStreamWriter(
                System.out, StandardCharsets.UTF_8));
        BufferedWriter error = new BufferedWriter(new OutputStreamWriter(
                System.err, StandardCharsets.UTF_8));

        int count = 0;
        String line;
        while ((line = input.readLine()) != null) {
            output.write("OUT:" + line);
            output.newLine();
            count++;
        }
        error.write("ERR:lines=" + count);
        error.newLine();
        output.flush();
        error.flush();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ProcessStreamsDemo.java
java -cp . ProcessStreamsDemo
```

Stdout của chương trình cha:

```text
stdout=OUT:Hello Java
stderr=ERR:lines=1
exit=0
```

Trong stdout trên, dòng bắt đầu bằng `stderr=` là báo cáo do **cha** in sau khi đã thu thập stderr của con. Nó không có nghĩa hai kênh đã được cấu hình gộp.

Luồng thực thi cần chú ý:

1. Sau `start()`, cha khởi động hai tác vụ đọc trước khi chờ con.
2. Cha ghi `Hello Java` và một dấu xuống dòng bằng UTF-8.
3. Ra khỏi khối try-with-resources, writer đóng stdin của con.
4. Con đọc hết dữ liệu rồi nhận EOF, hoàn tất hai kênh đầu ra.
5. Hai tác vụ đọc độc lập thu thập stdout và stderr.
6. Cha đợi tiến trình với thời hạn, lấy hai kết quả rồi in theo thứ tự cố định.

Vì kết quả được thu riêng và chỉ in sau khi thu xong, ba dòng stdout của cha ổn định. Điều đó không chứng minh có thể suy một thứ tự thời gian toàn cục giữa các lần ghi stdout và stderr của con.

Ví dụ dùng `readAllBytes()` vì con chỉ tạo đầu ra nhỏ đã biết. Hàm này đọc tới EOF và gom toàn bộ vào bộ nhớ; không dùng nguyên cách thu thập này cho đầu ra lớn hoặc không giới hạn. Xem [Java InputStream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html#readAllBytes()).

`stripTrailing()` chỉ bỏ dấu xuống dòng cuối để bản in minh họa gọn. Nếu dữ liệu thật coi khoảng trắng cuối là nội dung, phải giữ nguyên hoặc phân tích theo đúng giao thức.

Thời hạn chờ tiến trình là 10 giây; chờ kết quả mỗi tác vụ đọc có thời hạn riêng. Việc quản lý cả cây tiến trình, đầu ra vô hạn hoặc dừng một giao thức phức tạp cần thiết kế bổ sung. Ví dụ này chỉ khởi chạy JVM con đã kiểm soát, không tạo tiến trình cháu.

## 7. Chuyển hướng thay đổi cách các getter hoạt động

Các lựa chọn phải được cấu hình trên builder trước `start()`:

| Cấu hình | Nơi dữ liệu đi | Hệ quả khi đọc qua `Process` |
| --- | --- | --- |
| Mặc định | stdout/stderr tới hai pipe | Cha đọc hai kênh riêng |
| `redirectErrorStream(true)` | stderr đi chung đích với stdout | Đọc phần gộp qua `getInputStream()` |
| `redirectOutput(file)` | stdout vào tệp | Không còn thu stdout qua pipe |
| `redirectError(file)` | stderr vào tệp | Không còn thu stderr qua pipe |
| `inheritIO()` | Kế thừa các kênh chuẩn của cha | Không dùng các getter để thu như pipe mặc định |
| `redirectInput(file)` | Con đọc stdin từ tệp | Không ghi stdin qua pipe mặc định |

Khi một kênh đã được chuyển hướng khỏi pipe, Java thường vẫn trả một đối tượng luồng đặc biệt thay vì tham chiếu `null`: luồng đọc tương ứng cho EOF; luồng ghi không dùng được sẽ ném `IOException` khi ghi. Cần đọc hợp đồng cụ thể, không kiểm tra `getInputStream() == null` để suy rằng stdout đã bị chuyển hướng.

Với `redirectErrorStream(true)`, `getErrorStream()` không còn chứa stderr riêng. Ưu điểm là chỉ cần xử lý một pipe; đổi lại không còn biết chắc byte nào ban đầu thuộc kênh nào. Không gộp nếu stdout chứa dữ liệu cần phân tích nghiêm ngặt mà log stderr có thể làm hỏng cấu trúc.

Hành vi chuyển hướng được mô tả trong [Java ProcessBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html).

## 8. Một số lỗi đọc/ghi thường gặp

### `readLine()` chưa trả về không nhất thiết là tiến trình treo

Reader có thể đang chờ dấu xuống dòng hoặc EOF. Nếu con ghi một thông báo không có xuống dòng và chưa đóng luồng, `readLine()` có thể tiếp tục đợi.

Ngược lại, nếu con đã đóng đầu ghi, phần ký tự cuối không có xuống dòng vẫn có thể được trả về trước khi lần đọc kế tiếp cho `null`. Cần biết giao thức đang dùng dòng, byte hay khối có độ dài.

### `available() == 0` không có nghĩa đã hết đầu ra

Nó có thể chỉ cho biết hiện chưa có byte nào đọc được ngay. Con có thể ghi thêm sau đó. Không dùng vòng lặp dựa trên `available()` để kết luận EOF hoặc cắt ngắn đầu ra.

### `waitFor()` không thay cha đọc dữ liệu

Nó chờ trạng thái tiến trình, không tự xả hai pipe vào bộ nhớ ứng dụng. Nếu con bị chặn do pipe đầy, việc chờ tiến trình có thể không hoàn tất như dự kiến.

### Đóng sớm đầu đọc có thể làm con gặp lỗi ghi

Nếu không muốn giữ đầu ra, chọn chuyển hướng phù hợp hoặc tiếp tục đọc rồi bỏ dữ liệu theo kế hoạch. Đóng một pipe khi con đang ghi không phải thao tác tương đương “bỏ qua log” trong mọi công cụ.

## 9. Tự kiểm tra

1. Cha muốn gửi dữ liệu vào stdin của con thì dùng getter nào?
2. Cha đã `flush()` nhưng vẫn giữ writer mở; con đọc tới EOF có chắc kết thúc không?
3. Vì sao đọc stdout xong mới đọc stderr có thể gây chờ nhau?
4. Có nội dung trên stderr thì mã thoát bắt buộc khác 0 không?
5. Khi stdout đã chuyển vào tệp, có nên tiếp tục mong `getInputStream()` thu lại nội dung ấy không?

Đáp án: (1) `getOutputStream()`; (2) không, flush chưa báo EOF; (3) con có thể bị chặn khi stderr đầy; (4) không, phụ thuộc hợp đồng công cụ; (5) không, đích nhận đã thay đổi.

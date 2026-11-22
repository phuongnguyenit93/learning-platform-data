# Thiết lập thư mục làm việc cho ProcessBuilder

## 1. Thư mục làm việc quyết định điểm xuất phát của đường dẫn tương đối

Giả sử một công cụ đọc `input.txt` và ghi `result.txt`. Hai tên đó chưa nói đầy đủ tệp nằm ở đâu: chúng phải được hiểu từ một **thư mục làm việc (working directory)**.

Nếu cùng công cụ chạy từ hai thư mục khác nhau, nó có thể đọc hai tệp `input.txt` khác nhau dù đối số giống hệt nhau. Đây là nguyên nhân phổ biến của tình huống “chạy trong terminal thì đúng nhưng chạy từ IDE hoặc dịch vụ lại không tìm thấy tệp”.

Với tiến trình con do Java tạo ra, thiết lập thư mục bằng:

```java
builder.directory(workDirectory.toFile());
```

Đây là cấu hình của tiến trình con sẽ được khởi chạy. Nó không chuyển thư mục của JVM cha và không di chuyển tệp thực thi.

## 2. Hiểu cặp directory() và directory(File)

| Cách gọi | Ý nghĩa |
|---|---|
| `builder.directory()` | Đọc thư mục đã được cấu hình; trả `null` nếu dùng thư mục làm việc mặc định |
| `builder.directory(file)` | Cấu hình thư mục làm việc cho các tiến trình khởi chạy sau đó |
| `builder.directory(null)` | Quay lại dùng thư mục làm việc mặc định của tiến trình hiện tại |

Builder mới có giá trị thư mục là `null`. `null` ở đây không có nghĩa “không có thư mục làm việc”; tiến trình con vẫn có thư mục làm việc, mặc định là thư mục làm việc của tiến trình hiện tại.

Việc gọi setter chưa khởi chạy chương trình và chưa chứng minh thư mục dùng được. Nếu thư mục không tồn tại hoặc không sử dụng được, lỗi có thể chỉ xuất hiện khi `start()` yêu cầu hệ điều hành tạo tiến trình. Xem [API ProcessBuilder.directory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html#directory(java.io.File)).

Một cấu hình đã truyền cho tiến trình P1 không bị thay đổi khi sửa builder để tạo P2:

```text
builder.directory(A) → start() → P1 có thư mục làm việc A
builder.directory(B) → start() → P2 có thư mục làm việc B

Thư mục làm việc của JVM cha không đổi bởi hai thao tác trên.
```

## 3. Phân biệt ba vị trí thường bị nhầm

| Vị trí | Câu hỏi nó trả lời |
|---|---|
| Nơi chứa tệp thực thi | Chương trình cần chạy nằm ở đâu? |
| Thư mục làm việc của con | Tệp tương đối mà chương trình con mở được tính từ đâu? |
| Thư mục làm việc của cha | Đường dẫn tương đối trong mã Java cha được hiểu từ đâu? |

Ví dụ, chương trình thực thi có thể nằm trong `tools/bin`, nhưng cần chạy với dữ liệu ở `jobs/job-42`. Không bắt buộc hai nơi đó giống nhau.

Nếu con mở `input.txt` theo cách thông thường, nó sẽ tìm trong thư mục làm việc của nó. Tuy nhiên, một công cụ có thể tự định nghĩa quy tắc khác: tệp cấu hình tương đối với tệp dự án, thư mục gốc do tùy chọn `--root` chỉ định, hoặc thư mục đầu ra riêng. Hãy đọc hợp đồng công cụ thay vì mặc định mọi đối số đường dẫn đều theo cùng quy tắc.

Ở phía cha, tạo một `Path` hay `File` tương đối không tự gắn đối tượng đó với thư mục đã cấu hình cho con. Muốn chỉ rõ tệp nằm trong thư mục công việc, hãy dùng:

```java
Path input = workDirectory.resolve("input.txt");
```

Đoạn này là minh họa đặt trong phương thức có sẵn biến `workDirectory` kiểu `Path`.

## 4. Ưu tiên đường dẫn tuyệt đối ở ranh giới khởi chạy

Một cách chuẩn bị thư mục:

```java
Path workDirectory = Path.of("work").toAbsolutePath().normalize();
if (!Files.isDirectory(workDirectory)) {
    throw new IllegalArgumentException("Working directory does not exist");
}
builder.directory(workDirectory.toFile());
```

Đoạn trên cần import `java.nio.file.Path`, `java.nio.file.Files` và một builder đã có lệnh. Nó **yêu cầu thư mục đã tồn tại**.

Nếu ứng dụng có trách nhiệm tạo thư mục, hãy gọi `Files.createDirectories(workDirectory)` một cách chủ động trước khi chạy. `directory(...)` tự nó không tạo thư mục.

Một số điểm cần hiểu:

- `toAbsolutePath()` chuyển đường dẫn thành dạng tuyệt đối dựa trên hệ thống tệp và thư mục mặc định phù hợp.
- `normalize()` xử lý các thành phần đường dẫn như `.` và `..` theo cấu trúc đường dẫn; nó không xác nhận đối tượng tồn tại.
- Kiểm tra trước giúp thông báo rõ hơn, nhưng trạng thái hệ thống tệp vẫn có thể thay đổi trước `start()`. Vẫn phải xử lý lỗi khởi chạy.
- Nếu công việc cần tạo tệp, quyền truy cập thư mục và tệp liên quan cũng phải đáp ứng thao tác thực tế.

Không coi chuẩn hóa chuỗi đường dẫn là phép xác minh quyền hoặc giới hạn truy cập. Thư mục làm việc chỉ là điểm xuất phát cho đường dẫn; nó không ngăn chương trình mở một đường dẫn tuyệt đối hoặc đi ra ngoài bằng các thao tác mà quyền của nó cho phép. Các khái niệm đường dẫn tuyệt đối, tương đối và chuẩn hóa được mô tả trong [API Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html).

### Không dùng thay đổi user.dir để thay directory(...)

`user.dir` là một thuộc tính Java thường phản ánh thư mục làm việc lúc JVM được khởi chạy. Gán lại chuỗi thuộc tính bằng `System.setProperty` không phải một giao diện chuyển thư mục của tiến trình hệ điều hành.

Cần cấu hình thư mục cho con thì dùng `ProcessBuilder.directory(...)`. Với các tệp cha cần quản lý, giữ một `Path` gốc rõ ràng và dùng `resolve` để tạo đường dẫn. Cách này tránh làm các phần mã khác phụ thuộc vào việc sửa một thuộc tính toàn cục.

## 5. Bẫy khi chạy JVM con: classpath tương đối

Lệnh:

```text
java -cp . MyProgram
```

dùng `.` làm một mục classpath. Khi JVM con khởi chạy ở thư mục khác, `.` là thư mục làm việc **của con**. Nếu tệp lớp chỉ tồn tại ở thư mục cha đang đứng, JVM con có thể báo không tìm thấy lớp.

Vấn đề tương tự xảy ra với `classes`, `lib/tool.jar` hoặc tên JAR tương đối. Đổi thư mục làm việc phải đi cùng việc xác định lại những đường dẫn phụ thuộc thư mục. Cú pháp `-cp` và cách khởi chạy ứng dụng được mô tả trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#standard-options-for-java).

Trong ví dụ của bài:

1. Tệp thực thi `java` có đường dẫn tuyệt đối.
2. Các mục classpath của cha được chuyển thành đường dẫn tuyệt đối **trước khi khởi chạy con**.
3. Chỉ đường dẫn dữ liệu `input.txt` bên con được cố ý giữ tương đối để quan sát tác dụng của thư mục làm việc.

Không thêm dấu ngoặc kép vào từng chuỗi đối số chỉ vì đường dẫn có khoảng trắng. Mỗi đối số được truyền thành một phần tử riêng của `ProcessBuilder`.

## 6. Chương trình đầy đủ: con đọc tệp tương đối ở thư mục được chọn

Lưu mã vào `WorkingDirectoryDemo.java`. Ví dụ dùng JDK 17 trở lên, tạo một thư mục tạm riêng và chỉ dọn đúng tệp/thư mục mà nó tạo.

```java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class WorkingDirectoryDemo {
    private static String absoluteClassPath() {
        return Arrays.stream(System.getProperty("java.class.path")
                        .split(Pattern.quote(File.pathSeparator), -1))
                .map(entry -> Path.of(entry.isEmpty() ? "." : entry)
                        .toAbsolutePath().normalize().toString())
                .collect(Collectors.joining(File.pathSeparator));
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--child")) {
            String value = Files.readString(
                    Path.of("input.txt"), StandardCharsets.UTF_8);
            System.out.println("child input=" + value);
            return;
        }

        Path parentDirectory = Path.of("").toAbsolutePath().normalize();
        Path workDirectory = Files.createTempDirectory("pb-workdir-")
                .toAbsolutePath().normalize();
        Path input = workDirectory.resolve("input.txt");
        Process child = null;

        try {
            Files.writeString(input, "working-directory-data",
                    StandardCharsets.UTF_8);

            boolean windows = System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT).startsWith("windows");
            Path javaExecutable = Path.of(
                    System.getProperty("java.home"),
                    "bin", windows ? "java.exe" : "java")
                    .toAbsolutePath().normalize();

            ProcessBuilder builder = new ProcessBuilder(
                    javaExecutable.toString(),
                    "-cp", absoluteClassPath(),
                    WorkingDirectoryDemo.class.getName(),
                    "--child");

            System.out.println("default directory inherited="
                    + (builder.directory() == null));
            builder.directory(workDirectory.toFile());
            builder.redirectErrorStream(true);
            builder.redirectOutput(ProcessBuilder.Redirect.INHERIT);

            child = builder.start();
            child.getOutputStream().close();
            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Child process timed out");
            }
            int exitCode = child.exitValue();
            if (exitCode != 0) {
                throw new IllegalStateException("Child failed: " + exitCode);
            }
            System.out.println("child exit=" + exitCode);
            System.out.println("parent directory unchanged="
                    + parentDirectory.equals(
                            Path.of("").toAbsolutePath().normalize()));
        } finally {
            if (child != null && child.isAlive()) {
                child.destroyForcibly();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Child did not stop; temporary files preserved");
                }
            }
            Files.deleteIfExists(input);
            Files.deleteIfExists(workDirectory);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 WorkingDirectoryDemo.java
java WorkingDirectoryDemo
```

Stdout khi con chạy và kết thúc trong thời hạn:

```text
default directory inherited=true
child input=working-directory-data
child exit=0
parent directory unchanged=true
```

### Những dòng nào chứng minh tác dụng của thư mục làm việc?

Cha ghi `input.txt` bằng đường dẫn tuyệt đối được tạo từ `workDirectory.resolve(...)`. Sau đó cha cấu hình chính thư mục ấy cho con.

Trong nhánh `--child`, con chỉ gọi:

```java
Files.readString(Path.of("input.txt"), StandardCharsets.UTF_8);
```

Nó không nhận đường dẫn tuyệt đối của tệp làm đối số. Việc đọc được nội dung đã chuẩn bị cho thấy đường dẫn tương đối của con được hiểu từ thư mục công việc mới trong ví dụ.

Dòng cuối xác nhận đường dẫn tuyệt đối mặc định mà cha quan sát không đổi sau lần khởi chạy. Nó không dựa vào tên thư mục tạm cụ thể, nên stdout vẫn xác định dù mỗi lần chạy tạo thư mục tạm khác.

### Vì sao có hàm absoluteClassPath?

Hàm tách classpath theo `File.pathSeparator`, chuyển từng mục sang đường dẫn tuyệt đối rồi ghép lại. Dấu phân cách classpath thường là `;` trên Windows và `:` trên Linux/macOS; không nhầm nó với dấu phân cách thư mục.

Ví dụ này dành cho cách biên dịch/chạy lớp thông thường đã ghi ở trên. Nếu ứng dụng dùng module path, bộ nạp lớp riêng hoặc cách đóng gói đặc biệt, hãy xây cấu hình khởi chạy tương ứng; sao chép classpath không thay thế mọi mô hình khởi chạy Java.

### Vì sao có mã theo dõi và dọn tiến trình?

Cấu hình thư mục đúng chưa đủ để bảo đảm chương trình con thành công. Cha vẫn đóng đầu vào không dùng, chuyển tiếp đầu ra, chờ có thời hạn và kiểm tra mã thoát.

Khối `finally` yêu cầu dừng con nếu nó còn sống rồi chờ xác nhận trước khi xóa tệp tạm. Nếu con không dừng trong khoảng dọn dẹp, ví dụ giữ tệp tạm và báo lỗi. Như vậy nó không cố xóa thư mục công việc khi tiến trình được theo dõi vẫn có thể đang dùng.

Mã chỉ quản lý tiến trình con đơn giản mà nó tạo. Nếu công cụ sinh thêm tiến trình hậu duệ hoặc tạo thêm tệp, cần thiết kế dọn dẹp theo vòng đời và dữ liệu của công cụ đó.

## 7. Chẩn đoán lỗi theo giai đoạn

| Biểu hiện | Điều cần kiểm tra |
|---|---|
| `start()` báo lỗi | Thư mục có tồn tại, có phải thư mục, có dùng được không; tệp thực thi có đúng không |
| Con chạy nhưng không tìm thấy tệp | Đường dẫn dữ liệu đang được hiểu từ đâu; công cụ có quy tắc riêng không |
| JVM con báo không tìm thấy lớp | Classpath tương đối có bị đổi nghĩa sau khi đổi thư mục không |
| Kết quả xuất hiện ở vị trí bất ngờ | Công cụ ghi tương đối theo thư mục làm việc hay theo tùy chọn khác |
| Chỉ chạy được từ IDE | Có đang phụ thuộc vào thư mục làm việc do IDE chọn không |
| Xóa thư mục công việc thất bại | Tiến trình/tệp còn đang dùng, quyền hoặc dữ liệu còn sót có phù hợp dự kiến không |

Khi báo lỗi, ghi rõ thư mục đã cấu hình ở dạng tuyệt đối và chương trình cần chạy. Không chỉ ghi “không tìm thấy tệp”, vì thiếu ngữ cảnh gốc khiến việc tái hiện rất khó.

Một đường dẫn tương đối đến tệp thực thi có thể còn phụ thuộc quy tắc khởi chạy của hệ điều hành và cách tìm chương trình. Dùng đường dẫn tuyệt đối cho tệp thực thi khi cần hành vi ổn định giữa môi trường, thay vì dựa vào giả định rằng đổi `directory` sẽ tự giải quyết mọi vấn đề tìm lệnh.

## 8. Bài thực hành

1. Tạo hai thư mục công việc, mỗi thư mục có `input.txt` với nội dung khác nhau. Dùng hai builder chạy cùng chương trình con và quan sát kết quả.
2. Trong một bản thử riêng, giữ classpath `.` rồi đổi thư mục làm việc sang thư mục tạm không chứa lớp. Giải thích lỗi khởi chạy JVM con ở giai đoạn nào.
3. Đặt thư mục công việc có khoảng trắng trong tên. Giữ nguyên cách truyền từng đối số, không tự thêm dấu ngoặc kép.
4. Trỏ builder đến một đường dẫn chưa tồn tại. Xác định bước nào phát hiện lỗi, rồi bổ sung thông báo đầu vào rõ hơn trước `start()`.

Sau mỗi thử nghiệm, xác định riêng nơi chứa chương trình, nơi chứa dữ liệu và thư mục làm việc của tiến trình đang dùng đường dẫn tương đối. Sự phân biệt đó giúp cấu hình chạy ổn định ngoài môi trường phát triển của bạn.

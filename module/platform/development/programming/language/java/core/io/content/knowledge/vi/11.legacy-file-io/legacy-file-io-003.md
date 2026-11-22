# Đường dẫn tuyệt đối, tương đối và thư mục làm việc trong Java

## Mục tiêu

Trong Java I/O, một đường dẫn như `data/report.txt` chỉ xác định được vị trí thực tế khi biết **thư mục làm việc** hoặc một thư mục gốc được chỉ định. Đó là lý do cùng một chương trình đôi khi đọc file thành công trong IDE nhưng báo không tìm thấy file khi chạy từ terminal, JAR, Gradle hay container.

Sau bài này, bạn sẽ biết:

- Phân biệt đường dẫn **tuyệt đối** và **tương đối**, và diễn giải đường dẫn tương đối dựa trên working directory.
- Hiểu `System.getProperty("user.dir")` và tại sao thư mục đặt `.java`, `.class` hay `.jar` không mặc nhiên là thư mục làm việc.
- Dùng `java.io.File`: `getPath()`, `isAbsolute()`, `getAbsolutePath()`, `getCanonicalPath()` và các phép kiểm tra tồn tại.
- Dùng `java.nio.file.Path` và `Files` để ghép đường dẫn, chuẩn hóa, mở file và xử lý lỗi.
- Biết khi nào cần `toAbsolutePath()`, `normalize()`, `toRealPath()`; tránh nhầm lẫn với symbolic link và kiểm tra bảo mật.
- Chạy ví dụ Java 17+ trên nhiều hệ điều hành mà không phụ thuộc đường dẫn tuyệt đối của một máy cụ thể.

## 1. Đường dẫn tuyệt đối và tương đối

Đường dẫn (*path*) mô tả vị trí file hoặc thư mục trong một filesystem. **Tạo đối tượng đường dẫn không có nghĩa file đã tồn tại hay đã được mở.**

- **Tuyệt đối (absolute path):** mang đủ thông tin vị trí từ gốc do hệ điều hành/filesystem quy định. Ví dụ `/opt/demo/data/report.txt` trên Linux hoặc `C:\projects\demo\data\report.txt` trên Windows.
- **Tương đối (relative path):** cần một thư mục cơ sở (base directory). Ví dụ `data/report.txt`, `reports/2026.txt`, `../config/app.properties`.
- **Thư mục làm việc (working directory):** thư mục mà tiến trình Java thường sử dụng để diễn giải đường dẫn tương đối trên filesystem mặc định.

Giả sử working directory là `/home/learner/demo`:

```text
Working directory: /home/learner/demo

Đường dẫn tương đối: data/report.txt
Đường dẫn được giải: /home/learner/demo/data/report.txt

Đường dẫn tương đối: ../config/app.properties
Sau khi giải và chuẩn hóa:
                    /home/learner/config/app.properties
```

Một file tương đối có thể trỏ đến nơi khác khi chương trình được khởi động từ thư mục khác. Ngược lại, đường dẫn tuyệt đối không cần dựa vào working directory khi xác định địa chỉ trên filesystem tương ứng.

**Tuyệt đối không đồng nghĩa tồn tại:** `Path.of("/opt/demo/missing.txt").isAbsolute()` có thể là `true` ngay cả khi file không tồn tại. Việc đọc vẫn có thể gặp `NoSuchFileException` hoặc lỗi quyền truy cập.

### Khác biệt cú pháp giữa hệ điều hành

| Nền tảng/kiểu | Ví dụ | Lưu ý |
| --- | --- | --- |
| Unix/Linux/macOS | `/var/log/app.log` | Bắt đầu từ gốc `/`. |
| Unix tương đối | `./data/input.txt` | Dấu `.` chỉ thư mục hiện tại. |
| Windows có ổ đĩa | `C:\apps\demo\input.txt` | Có drive và gốc của drive. |
| Windows UNC | `\\server\share\input.txt` | Có thể trỏ đến chia sẻ mạng. |
| Windows đặc biệt | `C:notes.txt` | Là đường dẫn tương đối theo ngữ cảnh hiện tại của drive C:, **khác** `C:\notes.txt`. |

Đừng tự kết luận tính tuyệt đối bằng `path.startsWith("/")` hoặc tìm dấu hai chấm. `C:\data` trên Linux có thể chỉ là một tên đường dẫn tương đối chứa các ký tự thông thường. Dùng `File.isAbsolute()` hoặc `Path.isAbsolute()` theo filesystem của môi trường đang chạy.

## 2. Thư mục làm việc đến từ đâu?

Working directory là ngữ cảnh được môi trường khởi chạy thiết lập cho tiến trình:

- **Terminal:** thư mục đang đứng khi gọi `java`, trừ khi cách khởi chạy thay đổi nó.
- **IDE:** cấu hình *Working directory* trong Run/Debug Configuration.
- **Gradle/Maven:** tùy tác vụ, plugin và working directory cấu hình cho tiến trình chạy.
- **Container:** giá trị `WORKDIR` hoặc working directory do runtime/container định nghĩa.
- **System service / scheduler:** cấu hình dịch vụ, không nhất thiết là thư mục chứa JAR.

Java thường cung cấp thuộc tính:

```java
String cwd = System.getProperty("user.dir");
System.out.println(cwd);
```

Đây là **snippet** trong phương thức Java. Kết quả là đường dẫn của môi trường chạy, nên không có một stdout chung cho mọi máy.

Ví dụ, khi thực hiện `java -jar /opt/tools/app.jar` từ `/home/learner`, chương trình có thể có working directory `/home/learner` mặc dù JAR nằm ở `/opt/tools`. Khi đó:

```text
new File("config/app.properties")
    -> /home/learner/config/app.properties
    (nếu working directory là /home/learner)
```

Thư mục chứa mã nguồn, thư mục chứa tệp lớp, đường dẫn classpath và vị trí JAR là **những khái niệm khác working directory**.

**Không nên đổi working directory bằng `System.setProperty("user.dir", "...")`.** Thay thuộc tính Java không phải một cách tổng quát, đáng tin cậy để đổi current directory của tiến trình OS và có thể làm các phần ứng dụng hiểu khác nhau. Khi muốn làm việc theo một thư mục nhất định, hãy lưu `Path base` và gọi `base.resolve(...)` rõ ràng.

## 3. API truyền thống: `java.io.File`

`File` biểu diễn tên đường dẫn đến file hoặc thư mục; constructor không tự tạo file, không tự mở stream. Các phương thức quan trọng:

| Phương thức | Hành vi |
| --- | --- |
| `new File("data", "report.txt")` | Tạo đối tượng đường dẫn con của thư mục `data`. |
| `getPath()` | Trả biểu diễn đường dẫn hiện tại; có thể tương đối. |
| `isAbsolute()` | Kiểm tra đường dẫn có tuyệt đối trên nền tảng hiện tại. |
| `getAbsolutePath()` | Trả dạng đường dẫn tuyệt đối; không đòi hỏi file tồn tại. |
| `getAbsoluteFile()` | Trả đối tượng `File` chứa đường dẫn tuyệt đối. |
| `getCanonicalPath()` | Trả đường dẫn canonical theo filesystem; có thể truy cập filesystem và ném `IOException`. |
| `getName()` | Tên thành phần cuối của đường dẫn. |
| `getParentFile()` | Đường dẫn thư mục cha được thể hiện trong đối tượng, có thể `null`. |
| `exists()` | Kiểm tra tồn tại tại thời điểm gọi; không đảm bảo thao tác sau sẽ thành công. |
| `isFile()` / `isDirectory()` | Kiểm tra loại đối tượng, không suy từ đuôi file. |
| `toPath()` | Chuyển sang API `Path`. |

### Ví dụ Java 17+: đường dẫn tương đối không cần file thật

Lưu thành **`FilePathDemo.java`**:

```java
import java.io.File;
import java.nio.file.Path;

public class FilePathDemo {
    public static void main(String[] args) {
        File relative = new File("data", "report.txt");
        File absolute = relative.getAbsoluteFile();

        System.out.println("relative.isAbsolute = " + relative.isAbsolute());
        System.out.println("absolute.isAbsolute = " + absolute.isAbsolute());
        System.out.println("file name = " + relative.getName());
        System.out.println("parent name = " + relative.getParentFile().getName());

        Path cleaned = Path.of("output", "..", "data", "report.txt")
                .normalize();
        System.out.println("normalized first = " + cleaned.getName(0));
        System.out.println("normalized last = " + cleaned.getFileName());
        System.out.println("normalized absolute = "
                + cleaned.toAbsolutePath().isAbsolute());
    }
}
```

Chạy:

```bash
javac FilePathDemo.java
java FilePathDemo
```

Kết quả trên hệ thống tệp mặc định thông thường:

```text
relative.isAbsolute = false
absolute.isAbsolute = true
file name = report.txt
parent name = data
normalized first = data
normalized last = report.txt
normalized absolute = true
```

Các giá trị trên không in nguyên địa chỉ gốc nên không phụ thuộc tên thư mục làm việc của từng máy. Tạo `File` và `Path` không yêu cầu `data/report.txt` hay `output` tồn tại. Dấu `..` trong `Path` được rút gọn **từ vựng** khi gọi `normalize()`.

## 4. Từ `File` sang `Path` và `Files`

Java NIO.2 cung cấp `java.nio.file.Path` để diễn tả đường dẫn và `java.nio.file.Files` để thực hiện I/O. Trong Java hiện đại nên ưu tiên cách này cho nghiệp vụ mới, đồng thời hiểu `File` khi làm việc với API cũ.

| Nhu cầu | `File` | `Path` / `Files` |
| --- | --- | --- |
| Xây path | `new File("a", "b.txt")` | `Path.of("a", "b.txt")` |
| Kiểm tra tuyệt đối | `isAbsolute()` | `isAbsolute()` |
| Lấy đường dẫn tuyệt đối | `getAbsolutePath()` | `toAbsolutePath()` |
| Chuẩn hóa `.`, `..` theo cú pháp | Dùng canonical khi thích hợp | `normalize()` không cần I/O |
| Giải đường dẫn theo base | `new File(parent, child)` | `base.resolve(child)` |
| Tìm đường dẫn tương đối từ base tới target | Không có API tương đương trực tiếp | `base.relativize(target)` nếu tương thích |
| Đường dẫn thực của file hiện tồn tại | Kiểm tra tồn tại + canonical theo nhu cầu | `toRealPath()` |
| Kiểm tra tồn tại | `exists()` | `Files.exists(path)` |
| Tạo thư mục cha | `mkdir()` / `mkdirs()` | `Files.createDirectories(path)` |
| Đọc/ghi text | Stream/Reader/Writer kết hợp | `Files.readString` / `Files.writeString` |
| Lỗi I/O | Nhiều phương thức trả boolean | Phần lớn phép I/O ném `IOException` |

### `resolve` và `relativize`

`base.resolve(child)` thông thường ghép `child` tương đối vào `base`. Nếu `child` là **absolute path**, nó không bị buộc nằm dưới `base`; đừng dùng `resolve` làm cơ chế bảo vệ quyền truy cập.

`base.relativize(target)` tìm đường dẫn tương đối từ `base` đến `target` khi hai đường dẫn có kiểu/gốc tương thích. Đừng mong phương thức này tự truy cập filesystem hoặc tự xác minh target tồn tại.

Ví dụ:

```java
// Snippet minh họa Path, không làm I/O:
Path base = Path.of("workspace");
Path child = base.resolve("notes").resolve("today.txt");
Path relative = base.relativize(child); // notes/today.txt
```

Dấu phân cách hiển thị phụ thuộc hệ điều hành; `relativize` và `resolve` làm việc ở cấp thành phần đường dẫn, tránh việc tự ghép chuỗi.

### `toAbsolutePath()`, `normalize()` và `toRealPath()` không giống nhau

- `toAbsolutePath()`: chuyển thành đường dẫn tuyệt đối dựa vào ngữ cảnh filesystem, **không yêu cầu file có thật**.
- `normalize()`: rút gọn các thành phần `.` và `..` theo cú pháp, **không đọc filesystem**.
- `toRealPath()`: mặc định cần đối tượng tồn tại, xác minh và giải quyết symbolic link theo provider, có thể ném `IOException`.
- `toRealPath(LinkOption.NOFOLLOW_LINKS)`: dùng quy tắc khác với symbolic link, không mặc định theo chúng khi xác định đường dẫn thực.
- `File.getCanonicalPath()`: chuẩn hóa tên đường dẫn theo quy tắc file system, có thể giải symlink và có thể trả canonical path khi đích chưa tồn tại; **không hoàn toàn đồng nghĩa** với `Path.toRealPath()`.

Một đường dẫn có `someLink/..` có thể mang nghĩa khác nhau sau khi filesystem giải symbolic link. `normalize()` rút gọn theo từ vựng nên **không đủ để xác minh đối tượng mà I/O sẽ thực sự tác động**.

## 5. Ví dụ Java 17+: tạo file trong thư mục tạm

Ví dụ dưới đây tạo một thư mục tạm riêng, ghi một file UTF-8, kiểm chứng `normalize` và `toRealPath` rồi xóa những đối tượng đã tạo. Nó không cần cố định đường dẫn tuyệt đối kiểu `C:\temp` hoặc `/tmp`.

Lưu thành **`TemporaryFilePathDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TemporaryFilePathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("path-lesson-");
        Path reports = root.resolve("reports");
        Path file = reports.resolve("daily.txt");

        try {
            Files.createDirectories(reports);
            Files.writeString(file, "Xin chao", StandardCharsets.UTF_8);

            Path withDots = root.resolve("reports")
                    .resolve(".")
                    .resolve("..")
                    .resolve("reports")
                    .resolve("daily.txt");

            System.out.println("file exists = " + Files.exists(file));
            System.out.println("regular file = " + Files.isRegularFile(file));
            System.out.println("same normalized path = "
                    + withDots.normalize().equals(file.normalize()));
            System.out.println("real path matches = "
                    + file.toRealPath().equals(withDots.toRealPath()));
            System.out.println("read text = "
                    + Files.readString(file, StandardCharsets.UTF_8));

            File legacy = file.toFile();
            System.out.println("File name = " + legacy.getName());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(reports);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TemporaryFilePathDemo.java
java TemporaryFilePathDemo
```

Stdout dự kiến trong filesystem mặc định hỗ trợ tạo/xóa file và thư mục:

```text
file exists = true
regular file = true
same normalized path = true
real path matches = true
read text = Xin chao
File name = daily.txt
```

**Giải thích:**

1. `Files.createTempDirectory` trả một thư mục tạm do Java tạo theo cấu hình runtime.
2. `root.resolve("reports").resolve("daily.txt")` xác định rõ file bên dưới base, không phụ thuộc working directory khi đã có `root`.
3. `Files.createDirectories` tạo thư mục cha trước khi ghi; `Files.writeString` không tự tạo mọi thư mục cha.
4. `withDots.normalize()` rút gọn chuỗi path, còn `toRealPath()` truy cập filesystem để xác minh đường dẫn thực của file đã tồn tại.
5. `Files.deleteIfExists` dọn dữ liệu đã tạo từ file đến thư mục cha. Nếu có dữ liệu ngoài ý muốn được tạo đồng thời trong thư mục, xóa thư mục có thể thất bại; chương trình không xóa đệ quy vô điều kiện.
6. `Path.toFile()` hữu ích để tương tác với API cũ trên filesystem mặc định; với một số filesystem provider đặc biệt nó có thể không được hỗ trợ.

Nếu chạy trong môi trường không cho tạo file tạm hoặc lỗi quyền, thao tác sẽ ném `IOException`. Đó là giới hạn môi trường I/O thực tế; không nên giả lập thành công.

## 6. Vì sao cùng code chạy từ IDE và terminal cho kết quả khác?

Giả sử ứng dụng viết:

```java
Path config = Path.of("config", "app.properties");
String content = Files.readString(config);
```

Đây là **snippet**: cần import `Path`/`Files`, xử lý `IOException` và có file thật. Với cùng đường dẫn tương đối:

| Working directory | File thực tế sẽ được tìm |
| --- | --- |
| `/home/alice/project` | `/home/alice/project/config/app.properties` |
| `/home/alice` | `/home/alice/config/app.properties` |
| `/srv/app` | `/srv/app/config/app.properties` |

Cách chẩn đoán:

1. In hoặc log `System.getProperty("user.dir")`.
2. Log `config.toAbsolutePath().normalize()` để xác định vị trí được tìm.
3. Xác minh cấu hình working directory ở IDE, build tool, container hoặc service.
4. Kiểm tra quyền truy cập và thao tác mở file thật. `Files.exists` có thể trả `false` nếu lỗi I/O/không xác định được trạng thái; nó không bảo đảm lần đọc tiếp theo sẽ thành công.
5. Nếu ứng dụng cần thư mục gốc cố định, nhận giá trị đó qua cấu hình rõ ràng (tham số CLI, environment, config file đáng tin), sau đó `base.resolve(...)`.

### Tài nguyên nằm trong JAR không phải file bên cạnh JAR

Nếu `defaults.properties` được đóng gói trong classpath/JAR, thay vì giả định nó vẫn tồn tại dưới thư mục `src/main/resources` sau khi build, hãy dùng classpath resource:

```java
// Snippet; MyApp là class thật trong ứng dụng.
try (java.io.InputStream in =
        MyApp.class.getResourceAsStream("/config/defaults.properties")) {
    if (in == null) {
        throw new java.io.FileNotFoundException("resource not found");
    }
    // Đọc nội dung từ in.
}
```

Đoạn trên chưa phải chương trình độc lập vì class `MyApp` chỉ là tên minh họa. Trong ứng dụng thực tế, thay bằng class tồn tại và xử lý/khai báo `IOException`. Resource bên trong JAR được đọc qua class loader; path của source code không tự trở thành path file trong runtime.

## 7. Đừng nối đường dẫn bằng dấu phân cách tự viết

Cách nối chuỗi kiểu Windows:

```java
// Ví dụ không nên áp dụng xuyên hệ điều hành.
String filePath = base + "\\" + folder + "\\" + filename;
```

là một snippet giả định các biến `base`, `folder`, `filename` đã tồn tại. Nó dễ sai trên hệ điều hành dùng dấu phân cách khác, dễ sinh ký tự thừa và khó xử lý các dạng path đặc biệt.

Thay bằng:

```java
// Snippet; cần import java.nio.file.Path
Path file = Path.of(base).resolve(folder).resolve(filename);
```

Hoặc dùng API cũ:

```java
// Snippet; base và filename là chuỗi do ứng dụng cung cấp.
File file = new File(new File(base), filename);
```

Phân biệt:

- `File.separator`: dấu phân cách **thành phần đường dẫn**, ví dụ forward slash trên Unix hoặc backslash trên Windows.
- `File.pathSeparator`: dấu phân cách **nhiều path trong một danh sách**, thường `:` trên Unix, `;` trên Windows (ví dụ classpath).

Đối với file trong thư mục con, `Path.of("data", "report.txt")` thường đơn giản và ít lỗi hơn thao tác chuỗi.

## 8. Đường dẫn từ người dùng và path traversal

Khi một đường dẫn đến từ tên file upload, URL, archive entry hoặc input CLI, đối tượng bên ngoài có thể cung cấp path chứa `..` hoặc path tuyệt đối. Nếu ghép mà không kiểm tra, ứng dụng có thể truy cập ngoài thư mục dự kiến:

```text
Thư mục được phép: /srv/app/uploads
Đầu vào:           ../../etc/secret
Sau giải từ vựng:  /srv/etc/secret
```

Từ thư mục `/srv/app/uploads`, hai bước đi lên đưa path về `/srv`, rồi ghép `etc/secret`. Điều nguy hiểm là path đã thoát vùng `uploads`.

Để minh họa **kiểm tra cú pháp ban đầu**, có thể dùng `Path.startsWith(Path)` thay vì so sánh chuỗi. Lưu thành **`LexicalPathGuard.java`**:

```java
import java.nio.file.Path;

public class LexicalPathGuard {
    static Path resolveUnder(Path base, String input) {
        Path supplied = Path.of(input);
        if (supplied.isAbsolute()) {
            throw new IllegalArgumentException("absolute input rejected");
        }

        Path root = base.toAbsolutePath().normalize();
        Path target = root.resolve(supplied).normalize();
        if (!target.startsWith(root)) {
            throw new IllegalArgumentException("outside allowed directory");
        }
        return target;
    }

    public static void main(String[] args) {
        Path base = Path.of("uploads");
        System.out.println(resolveUnder(base, "2026/report.txt")
                .getFileName());

        try {
            resolveUnder(base, "../secret.txt");
        } catch (IllegalArgumentException e) {
            System.out.println("traversal rejected");
        }
    }
}
```

Chạy:

```bash
javac LexicalPathGuard.java
java LexicalPathGuard
```

Kết quả:

```text
report.txt
traversal rejected
```

**Cảnh báo về giới hạn của ví dụ:** hàm trên chỉ kiểm tra các **thành phần tên đường dẫn**, không đủ bảo vệ nếu trong thư mục có symbolic link, junction/reparse point, mount, hard link hoặc đối tượng thay đổi giữa lúc kiểm tra và lúc mở. Với thao tác nhạy cảm, cần thiết kế quyền truy cập phù hợp; kiểm tra đường dẫn thực của file/cha hiện hữu theo chính sách, xử lý khả năng thay đổi đồng thời, và cân nhắc các API mở file gắn với thư mục đáng tin như `SecureDirectoryStream` nơi filesystem provider hỗ trợ. Đừng quảng bá `normalize().startsWith(root)` là bảo vệ path traversal đầy đủ.

`Path.startsWith(Path)` kiểm tra **thành phần path**, không kiểm tra tiền tố chuỗi. Ví dụ `/safe/app2` không phải con của `/safe/app` dù chuỗi chữ bắt đầu giống nhau.

## 9. Những nhầm lẫn thường gặp

1. **Tưởng path tương đối tính từ thư mục chứa file Java.** Nó thường phụ thuộc working directory của tiến trình hoặc base được truyền vào API.
2. **Tưởng `getAbsolutePath()` kiểm tra file đã có.** Nó chỉ trả địa chỉ tuyệt đối, không mở file.
3. **Tưởng `normalize()` tương đương `toRealPath()`.** Một cái rút gọn cú pháp; một cái mặc định xác minh file hiện hữu và xử lý symlink.
4. **Tưởng `getCanonicalPath()` luôn cần file tồn tại.** Nó có thể đưa ra đường dẫn canonical ngay cả khi file đích không tồn tại, tùy filesystem.
5. **Tưởng `Files.exists() == false` luôn nghĩa file chắc chắn không có.** Có thể thiếu quyền hoặc xảy ra lỗi; khi cần đọc, hãy mở và xử lý ngoại lệ.
6. **Tưởng thay `user.dir` là đổi cwd của mọi API.** Hãy lưu và truyền base directory tường minh.
7. **Tưởng slash/backslash có cùng nghĩa trên mọi nền tảng.** Hãy dùng `Path.of` và `resolve`.
8. **Tưởng path của resource đóng gói trong JAR là path của một file trên ổ đĩa.** Dùng API classpath resource khi phù hợp.
9. **Tưởng kiểm tra có tồn tại trước thì thao tác sau chắc chắn thành công.** File có thể bị thay đổi hoặc quyền bị thu hồi; vẫn phải xử lý `IOException`.
10. **Tưởng `resolve(userInput)` sẽ giữ input trong base.** Absolute path, `..` và symlink có thể làm mất ranh giới mong muốn; cần validation và cơ chế filesystem an toàn.
11. **Tưởng tên có đuôi `.txt` nghĩa là file thường.** Cần kiểm tra loại đối tượng, không dựa vào phần mở rộng.
12. **Không kiểm tra quyền sở hữu file tạm và dọn dẹp.** Với test/ứng dụng tạm thời, nên tạo file trong thư mục tạm riêng, xử lý lỗi và xóa đúng các file mình tạo.

## 10. Bảng lựa chọn nhanh

| Mục đích | API/hướng xử lý |
| --- | --- |
| Kiểm tra path tuyệt đối | `File.isAbsolute()` / `Path.isAbsolute()` |
| Hiển thị working directory | `System.getProperty("user.dir")` |
| Hiển thị vị trí dự kiến đọc file | `path.toAbsolutePath().normalize()` |
| Xác định file dưới một thư mục cấu hình | `base.resolve("sub").resolve("file.txt")` |
| Rút gọn `.` và `..` mà không làm I/O | `Path.normalize()` |
| Xác minh đường dẫn thực của file hiện có | `Path.toRealPath()` và xử lý `IOException` |
| Tương thích thư viện chỉ nhận `File` | `path.toFile()` nếu provider hỗ trợ |
| Tạo thư mục cha trước khi ghi | `Files.createDirectories(path.getParent())` khi parent hợp lệ |
| Tài nguyên đi kèm JAR | Classpath stream thay vì path dựa vào thư mục source |
| File cấu hình bên ngoài | Đường dẫn/base truyền qua cấu hình chạy |
| Dữ liệu đường dẫn không tin cậy | Chính sách validate + kiểm soát symlink/race và quyền filesystem |
| Bài kiểm thử thao tác file | `Files.createTempDirectory` và dọn dữ liệu trong `finally` |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Chạy JAR đặt tại `/opt/apps/app.jar` từ thư mục `/home/alice`. `new File("data.txt")` thường trỏ đến đâu?

**Trả lời:** `/home/alice/data.txt` khi working directory của tiến trình là `/home/alice`. Vị trí JAR không mặc định quyết định đường dẫn tương đối.

**Câu 2.** Gọi `new File("missing.txt").getAbsolutePath()` có tạo file không?

**Trả lời:** Không. Nó chỉ cho biểu diễn địa chỉ tuyệt đối.

**Câu 3.** `Path.of("a", "..", "b.txt").normalize()` có cần file `a` tồn tại không?

**Trả lời:** Không. Đây là phép biến đổi tên đường dẫn theo cú pháp, không truy cập filesystem.

**Câu 4.** `Path.toRealPath()` khác `toAbsolutePath()` ở đâu?

**Trả lời:** `toAbsolutePath()` xây path tuyệt đối mà không cần file có thật; `toRealPath()` mặc định kiểm tra tồn tại và giải quyết path thực, có thể ném `IOException`.

**Câu 5.** Dùng `File.pathSeparator` để nối thư mục `data` và file `report.txt` được không?

**Trả lời:** Không. `pathSeparator` tách danh sách nhiều path; dùng `Path.of("data", "report.txt")` hoặc `File.separator` khi thực sự cần chuỗi.

**Câu 6.** Vì sao `root.resolve(input).normalize().startsWith(root)` chưa phải kiểm tra bảo mật đầy đủ?

**Trả lời:** Nó chỉ kiểm tra tên path từ vựng. Symlink và thay đổi file đồng thời vẫn có thể khiến thao tác I/O thực tế trỏ ra ngoài vùng dự kiến.

**Câu 7.** File cấu hình đã được đóng gói thành resource bên trong JAR nên được mở từ đâu?

**Trả lời:** Từ classpath resource API như `getResourceAsStream`, không mặc nhiên bằng path `src/main/resources` tương đối với working directory.

## Kết luận

**Path tương đối + base directory = vị trí chương trình sẽ tìm đến.** Với chương trình chạy bằng IDE, Gradle, Docker hay JAR, hãy xác định working directory trước khi chẩn đoán lỗi “không tìm thấy file”. `File` giúp hiểu hệ API truyền thống; `Path`/`Files` giúp ghép, chuyển đổi, kiểm tra và thao tác file minh bạch hơn.

Khi cần đường dẫn ổn định, hãy cấu hình **base path tường minh**, dùng `resolve` để tạo path con, phân biệt rõ `toAbsolutePath()`, `normalize()` với `toRealPath()`, và xử lý ngoại lệ I/O thay vì suy đoán sự tồn tại của file từ tên đường dẫn.

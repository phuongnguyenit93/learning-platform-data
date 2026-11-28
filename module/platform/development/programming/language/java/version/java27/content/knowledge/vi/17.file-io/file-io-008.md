# Xử lý đường dẫn, symbolic link và giới hạn tài nguyên khi đọc tệp

Trong Java 27, API `java.nio.file` là nền tảng để biểu diễn đường dẫn, thao tác trên tệp và thư mục, đọc metadata và làm việc với symbolic link. Một chức năng “đọc tệp theo tên người dùng cung cấp” tưởng đơn giản nhưng thường liên quan đồng thời đến ba vấn đề:

1. **Đường dẫn:** tên tệp là tương đối hay tuyệt đối, được kết hợp với thư mục gốc ra sao, và liệu có chứa các thành phần `.` hoặc `..`?
2. **Symbolic link:** đường dẫn trên đĩa có thể trỏ tới tệp hoặc thư mục ở nơi khác, thậm chí ra ngoài thư mục ứng dụng được phép truy cập.
3. **Giới hạn tài nguyên:** đọc toàn bộ tệp lớn vào bộ nhớ, duyệt cây thư mục không giới hạn hoặc quên đóng stream có thể làm cạn heap, file descriptor hoặc thời gian xử lý.

Bài thuộc chương **Tệp và nhập xuất** trong module **Java 27 và các kiến thức liên quan**. Nội dung sử dụng những API Java SE 27 hiện hành, đặc biệt là `Path`, `Files`, `LinkOption`, `InputStream`, `BufferedReader`, `FileVisitor` và `SecureDirectoryStream`. Các ví dụ không cần tính năng Preview và không sử dụng cơ chế I/O đã bị loại bỏ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Tạo và xử lý `Path` bằng `Path.of`, `resolve`, `relativize`, `normalize`, `toAbsolutePath` và `toRealPath`.
- Hiểu sự khác biệt giữa **đường dẫn theo cú pháp** và **vị trí thực tế trong hệ thống tệp**.
- Xác định khi nào một API theo symbolic link và cách dùng `LinkOption.NOFOLLOW_LINKS` đúng nơi có hỗ trợ.
- Giải thích cách `..`, đường dẫn tuyệt đối và symbolic link có thể gây **path traversal**.
- Biết giới hạn của cách “kiểm tra đường dẫn rồi mở” trước rủi ro **TOCTOU** (*time of check to time of use*).
- Đọc tệp theo luồng và áp dụng ngưỡng byte thực đọc để tránh tải dữ liệu lớn vô hạn vào RAM.
- Phân biệt giới hạn số dòng, kích thước mỗi dòng, tổng số byte, độ sâu thư mục và số mục duyệt.
- Đóng đúng `InputStream`, `DirectoryStream` và những stream trả về từ `Files.list`/`Files.walk`/`Files.lines`.

## 2. Path đại diện cho một đường dẫn, không phải nội dung tệp

### 2.1. Khởi tạo Path

~~~java
import java.nio.file.Path;

Path relative = Path.of("documents", "report.txt");
Path absolute = Path.of("/srv/app/data/report.txt");
~~~

`Path` là abstraction đại diện cho một vị trí trong file system, thường gồm root và các thành phần tên. `Path.of` chỉ tạo đối tượng đường dẫn; **nó không đòi hỏi tệp tồn tại** và không tự mở tệp.

Đường dẫn tuyệt đối trong ví dụ `/srv/app/data/report.txt` là minh họa theo hệ thống dạng Unix. Trên Windows, cú pháp root/drive khác và các chi tiết phụ thuộc file system provider.

Làm việc với `Path` tốt hơn ghép chuỗi đường dẫn bằng `"/"` hoặc `"\\"` vì `Path` tôn trọng quy tắc đường dẫn của file system provider tương ứng.

### 2.2. Các thành phần cơ bản

~~~java
Path path = Path.of("logs", "2026", "app.log");

System.out.println(path.getFileName()); // app.log
System.out.println(path.getParent());   // logs/2026 (trên Unix)
System.out.println(path.getNameCount()); // 3
System.out.println(path.isAbsolute());   // false
~~~

`getFileName` trả về thành phần tên cuối, `getParent` trả về phần cha nếu có, `getRoot` trả về phần root nếu đường dẫn có root. `Path.toString()` được biểu diễn theo provider/hệ điều hành; không nên kiểm thử cứng dấu phân cách để suy ra đường dẫn thuộc thư mục nào.

### 2.3. resolve: kết hợp đường dẫn

~~~java
Path base = Path.of("workspace");
Path target = base.resolve("documents").resolve("report.txt");
~~~

`resolve` kết hợp đường dẫn dựa trên các thành phần. Với provider mặc định, nếu đối số được resolve là đường dẫn tuyệt đối thì kết quả là đường dẫn tuyệt đối đó, không còn nằm dưới `base`.

~~~java
Path base = Path.of("/srv/app/data");
Path input = Path.of("/etc/passwd");

// Trên Unix: không còn nằm bên dưới base.
Path resolved = base.resolve(input);
~~~

Vì vậy, **không được mặc định rằng `base.resolve(userInput)` sẽ luôn nằm trong `base`**. Nếu hệ thống chỉ cho phép đường dẫn tương đối, hãy kiểm tra `input.isAbsolute()` trước khi kết hợp.

### 2.4. relativize: tính đường dẫn tương đối

~~~java
Path root = Path.of("/srv/app");
Path file = Path.of("/srv/app/data/report.txt");

Path relative = root.relativize(file);
// Trên Unix: data/report.txt
~~~

`relativize` suy ra đường dẫn tương đối để đi từ một `Path` tới `Path` khác theo ngữ nghĩa của provider. Cần chú ý tính tương thích giữa đường dẫn tuyệt đối/tương đối và root; những đường dẫn không tương thích có thể dẫn tới `IllegalArgumentException`.

Không nhầm `relativize` với một phép kiểm tra bảo mật. Kết quả có thể chứa `..`; bản thân phép tính này không xác nhận tệp thực tế ở trong vùng an toàn.

## 3. normalize, toAbsolutePath và toRealPath khác nhau thế nào?

### 3.1. normalize chỉ xử lý cú pháp

~~~java
Path raw = Path.of("files", ".", "images", "..", "report.txt");
Path normalized = raw.normalize();

// files/report.txt (trên hệ thống dùng '/')
~~~

`normalize` loại bỏ các thành phần `.` và một số cặp `tên/..` có thể rút gọn về mặt từ vựng. Nó **không truy cập file system**, không cần tệp tồn tại, không kiểm tra quyền và **không giải quyết symbolic link**.

Do đó, không thể lấy việc `normalize` thành công làm bằng chứng rằng đường dẫn là an toàn hoặc tệp có thật.

### 3.2. toAbsolutePath không đồng nghĩa real path

~~~java
Path input = Path.of("data", "report.txt");

Path absolute = input.toAbsolutePath();
Path normalizedAbsolute = input.toAbsolutePath().normalize();
~~~

`toAbsolutePath` tạo đường dẫn tuyệt đối theo ngữ nghĩa provider (thường dựa vào working directory của tiến trình nếu đường dẫn tương đối). Tệp không nhất thiết tồn tại; các symbolic link chưa được xác minh.

Working directory cũng không nhất thiết là thư mục chứa mã nguồn, file JAR hay executable. Trong dịch vụ chạy qua IDE, container, system service hoặc scheduled job, vị trí này có thể khác. Hãy cấu hình thư mục gốc rõ ràng thay vì ngầm định.

### 3.3. toRealPath truy cập hệ thống tệp

~~~java
Path file = Path.of("data", "report.txt");
Path real = file.toRealPath();
~~~

`toRealPath()` yêu cầu đường dẫn có thể được xác định trên file system; nó trả về đường dẫn tuyệt đối với các thành phần dư thừa được xử lý và **mặc định phân giải symbolic link** tới đích cuối.

Phương thức có thể ném `IOException` nếu đường dẫn không tồn tại, không truy cập được hoặc thao tác I/O thất bại.

~~~java
Path realWithoutFollowing =
        file.toRealPath(java.nio.file.LinkOption.NOFOLLOW_LINKS);
~~~

Khi có `NOFOLLOW_LINKS`, `toRealPath` không phân giải symbolic link theo lựa chọn này. Chi tiết thực thi khi gặp `..` liên quan tới link có thể phụ thuộc provider. Quan trọng hơn: dùng `NOFOLLOW_LINKS` với `toRealPath` **không phải lời cam kết rằng mọi lần mở tệp sau đó đều không đi theo link**.

### 3.4. Bảng so sánh

| Phương thức | Cần tệp tồn tại? | Theo symbolic link? | Công dụng |
|---|---|---|---|
| `normalize()` | Không | Không truy cập file system | Rút gọn thành phần đường dẫn theo cú pháp |
| `toAbsolutePath()` | Không | Không phân giải link | Chuyển sang đường dẫn tuyệt đối |
| `toAbsolutePath().normalize()` | Không | Không | Cơ sở cho kiểm tra từ vựng |
| `toRealPath()` | Có | Có, theo mặc định | Xác định vị trí thực tế tại thời điểm truy vấn |
| `toRealPath(NOFOLLOW_LINKS)` | Có | Không phân giải link theo tùy chọn | Xác định real path với chính sách không theo link |

### 3.5. Vì sao normalize có thể làm thay đổi ý nghĩa khi có link?

Giả sử:

~~~text
/allowed/
    shortcut -> /external/folder/
    report.txt
~~~

Đường dẫn `/allowed/shortcut/../secret.txt` có thể được hệ điều hành hiểu khác đường dẫn từ vựng sau khi rút gọn `shortcut/..`. Nếu `shortcut` là symlink, việc đi qua nó có thể làm thay đổi nơi `..` tác động.

Vì vậy, `normalize()` chỉ phù hợp để xử lý thành phần tên; **nó không mô phỏng chính xác mọi lần phân giải đường dẫn thực qua symlink**. Không nên dùng normalize như cơ chế duy nhất chống path traversal.

## 4. Symbolic link: tên tệp trỏ đến vị trí khác

### 4.1. Symbolic link là gì?

Symbolic link là một mục trong file system tham chiếu tới một đường dẫn đích. Khi nhiều API mở hoặc kiểm tra đường dẫn link, file system provider có thể đi theo link và thao tác với đối tượng đích.

Một symlink có thể:

- Trỏ tới tệp hoặc thư mục.
- Trỏ theo đường dẫn tuyệt đối hoặc tương đối.
- Trỏ tới đích chưa tồn tại (*dangling/broken symlink*).
- Tạo ra chuỗi link hoặc vòng lặp.

Khả năng tạo và xử lý symbolic link phụ thuộc file system, quyền hạn và hệ điều hành. Trên một số cấu hình Windows, tạo symbolic link có thể yêu cầu quyền hoặc chế độ hệ thống phù hợp.

### 4.2. Tạo symbolic link

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class LinkExample {
    static void createLink(Path link, Path target) throws IOException {
        Files.createSymbolicLink(link, target);
    }
}
~~~

`link` là đường dẫn của mục symlink được tạo; `target` là đường dẫn đích được ghi vào link. Nếu `target` là đường dẫn **tương đối**, nó được hiểu tương đối với **thư mục chứa link**, không mặc nhiên tương đối với working directory của tiến trình.

`Files.createSymbolicLink` có thể thất bại nếu link đã tồn tại, provider không hỗ trợ hoặc người chạy không đủ quyền. Không nên giả định ví dụ sẽ tạo link thành công trên mọi máy.

### 4.3. Nhận diện và đọc nội dung link

~~~java
Path link = Path.of("data", "latest");

if (Files.isSymbolicLink(link)) {
    Path storedTarget = Files.readSymbolicLink(link);
    System.out.println("Link target: " + storedTarget);
}
~~~

`Files.isSymbolicLink(link)` kiểm tra liệu chính mục được định danh là symlink. `Files.readSymbolicLink(link)` trả về **giá trị đường dẫn đích được lưu trong link**, không nhất thiết là đường dẫn tuyệt đối đã được chuẩn hóa hoặc trỏ tới tệp đang tồn tại.

Để xác định đích thực tế đang truy cập được, dùng `link.toRealPath()` nếu chính sách cho phép đi theo link.

### 4.4. exists và isRegularFile có thể theo link

~~~java
import static java.nio.file.LinkOption.NOFOLLOW_LINKS;

boolean targetExists = Files.exists(link);
boolean linkEntryExists = Files.exists(link, NOFOLLOW_LINKS);
boolean regularTarget = Files.isRegularFile(link);
boolean linkItselfRegular = Files.isRegularFile(link, NOFOLLOW_LINKS);
~~~

Theo mặc định, những phép kiểm tra như `Files.exists` và `Files.isRegularFile` sẽ đi theo symbolic link khi thích hợp. Với `NOFOLLOW_LINKS`, chúng kiểm tra mục link thay vì đích.

Ví dụ, khi symlink bị gãy:

- `Files.exists(link)` có thể là `false` do đích không tồn tại.
- `Files.exists(link, NOFOLLOW_LINKS)` có thể là `true` vì bản thân mục link vẫn tồn tại.
- `Files.isSymbolicLink(link)` có thể là `true`.

Cũng cần chú ý: `Files.exists` và `Files.notExists` **không nhất thiết là hai kết quả phủ định hoàn toàn**. Nếu không xác định được sự tồn tại do I/O/quyền truy cập, cả hai có thể trả về `false`.

### 4.5. NOFOLLOW_LINKS không phải tùy chọn dùng chung cho mọi API

`LinkOption.NOFOLLOW_LINKS` được dùng ở các phương thức có overload/tập option hỗ trợ nó. Không thể thêm tùy chọn này vào một phương thức không nhận option tương ứng, chẳng hạn `Files.readString(path)`.

Để từ chối symlink ở **thành phần cuối** khi mở byte channel, có thể dùng:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;

class ChannelExample {
    static void inspect(Path file) throws java.io.IOException {
        try (SeekableByteChannel channel = Files.newByteChannel(
                file, Set.of(StandardOpenOption.READ,
                             LinkOption.NOFOLLOW_LINKS))) {
            System.out.println(channel.size());
        }
    }
}
~~~

Theo hợp đồng của API, `NOFOLLOW_LINKS` trong lời gọi này yêu cầu không đi theo symlink ở mục file được mở; hành vi cụ thể còn tùy provider. Nó **không tự bảo đảm** rằng mọi thành phần thư mục cha là an toàn khi attacker có thể thay đổi chúng. Muốn ràng buộc đầy đủ từng thành phần, cần chiến lược truy cập có kiểm soát hơn.

## 5. Path traversal: kiểm tra đường dẫn do người dùng cung cấp

### 5.1. Tình huống điển hình

Giả sử một API chỉ được đọc file trong `/srv/app/uploads` nhưng nhận tên từ HTTP request:

~~~text
uploads/report.txt
uploads/2026/summary.txt
../../etc/passwd
/srv/app/secrets/credentials.txt
images/link-to-outside/private.txt
~~~

Hai rủi ro khác nhau:

1. `..` hoặc đường dẫn tuyệt đối làm thoát khỏi thư mục gốc bằng tên đường dẫn.
2. Một đường dẫn **trông như ở trong thư mục gốc** nhưng chứa symlink trỏ tới nơi khác.

Vì vậy, cần phân biệt **kiểm tra từ vựng** và **kiểm tra điểm đích thực**.

### 5.2. Kiểm tra từ vựng với Path.startsWith

Ví dụ kiểm tra đường dẫn tương đối:

~~~java
import java.nio.file.Path;

static Path resolveLexically(Path root, String userValue) {
    Path relative = Path.of(userValue);

    if (relative.isAbsolute()) {
        throw new IllegalArgumentException(
                "Absolute paths are not accepted");
    }

    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(relative).normalize();

    if (!candidate.startsWith(normalizedRoot)
            || candidate.equals(normalizedRoot)) {
        throw new IllegalArgumentException(
                "Path outside allowed directory");
    }

    return candidate;
}
~~~

`Path.startsWith(Path)` so sánh **các thành phần đường dẫn**, không phải kiểm tra tiền tố ký tự trong `String`. Ví dụ `/srv/app/uploads-copy` không được coi là nằm trong `/srv/app/uploads` chỉ vì chuỗi có cùng tiền tố.

Nhưng mẫu này **chưa phải một sandbox file system**. Nó chỉ ngăn một số cách thoát bằng cú pháp; symlink bên trong root vẫn có thể trỏ ra ngoài. Ngoài ra, file system có thể thay đổi sau lúc kiểm tra.

### 5.3. Kiểm tra real path tại thời điểm truy vấn

Nếu file đã tồn tại và chính sách cho phép đọc qua link khi đích vẫn nằm trong thư mục gốc:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static Path resolveExistingWithin(Path root, String userValue)
        throws IOException {

    Path trustedRoot = root.toRealPath();
    Path relative = Path.of(userValue);

    if (relative.isAbsolute()) {
        throw new IOException("Absolute path rejected");
    }

    Path lexical = trustedRoot.resolve(relative).normalize();
    if (lexical.equals(trustedRoot)
            || !lexical.startsWith(trustedRoot)) {
        throw new IOException("Lexical path escape rejected");
    }

    Path actual = lexical.toRealPath(); // follows links
    if (!actual.startsWith(trustedRoot)
            || !Files.isRegularFile(actual)) {
        throw new IOException("Resolved target is not an allowed file");
    }

    return actual;
}
~~~

Đoạn trên:

- Cố định root bằng `toRealPath()`.
- Từ chối đầu vào tuyệt đối.
- Giới hạn đường dẫn từ vựng dưới root.
- Giải quyết symlink tới file thực tế.
- Kiểm tra file thực tế còn nằm dưới root và là regular file.

**Giới hạn quan trọng:** thao tác kiểm tra `toRealPath`, `isRegularFile` và thao tác `open/read` sau đó là những bước **khác nhau**. Nếu đối thủ có quyền sửa thư mục hoặc symlink, họ có thể thay đổi file system giữa các bước (*TOCTOU*). Vì thế ví dụ này phù hợp để **giải thích nguyên tắc và xử lý nguồn tệp tương đối tin cậy**, không đủ làm bảo đảm an ninh trước người có khả năng chủ động thay đổi cây thư mục đồng thời.

### 5.4. Time of check to time of use (TOCTOU)

~~~text
T1: Ứng dụng kiểm tra /uploads/user.txt -> nằm trong vùng cho phép
T2: Attacker đổi một thư mục/link trung gian
T3: Ứng dụng mở /uploads/user.txt -> có thể tới đích khác
~~~

Đây là lỗ hổng xuất hiện khi đối tượng được kiểm tra và đối tượng được sử dụng không còn là một. Gọi `Files.exists`, `Files.isSymbolicLink` hoặc `toRealPath` trước khi mở **không loại bỏ** cửa sổ race nếu file system bị sửa đồng thời.

Để bảo vệ dữ liệu không đáng tin cậy trong môi trường có attacker chủ động, cần kết hợp:

- Phân quyền file system/OS để tiến trình và người dùng khác không tự ý sửa cây đường dẫn nhạy cảm.
- Mở tệp tương đối với một directory handle an toàn và kiểm soát từng thành phần khi provider hỗ trợ.
- Không đi theo symlink ở thành phần không được phép, theo đúng option của thao tác mở thực tế.
- Giới hạn phạm vi dữ liệu và quyền của tài khoản chạy ứng dụng.
- Kiểm tra lại các giả định về threat model và platform support.

### 5.5. SecureDirectoryStream là công cụ nâng cao

`SecureDirectoryStream<Path>` cung cấp các thao tác tương đối với một directory stream đang mở, nhằm giảm những race khi đường dẫn thay đổi trong lúc truy cập.

~~~java
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SecureDirectoryStream;

static void checkSupport(Path directory) throws java.io.IOException {
    try (DirectoryStream<Path> stream =
                 Files.newDirectoryStream(directory)) {
        if (stream instanceof SecureDirectoryStream<Path>) {
            System.out.println("SecureDirectoryStream supported");
        } else {
            System.out.println("SecureDirectoryStream unavailable");
        }
    }
}
~~~

Việc dùng `SecureDirectoryStream` cho phép các thao tác như `newDirectoryStream` và `newByteChannel` tương đối với directory handle; API hỗ trợ `NOFOLLOW_LINKS` trong những thao tác tương ứng.

**Không phải mọi file system provider đều hỗ trợ** `SecureDirectoryStream`. Kiểm tra `instanceof` chỉ xác định khả năng API; nó **chưa tự triển khai** một trình đọc chống path traversal. Muốn dùng an toàn với đường dẫn nhiều thành phần phải mở từng directory con tương đối với directory handle, xác minh chính sách từng bước và đóng tài nguyên đúng cách. Hệ thống cần định nghĩa rõ cách xử lý khi provider không hỗ trợ, thay vì âm thầm quay về cách mở path dễ bị race.

## 6. Chọn API đọc tệp theo dung lượng dữ liệu

### 6.1. API tiện dụng để đọc toàn bộ

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("notes.txt");

byte[] bytes = Files.readAllBytes(file);
String text = Files.readString(file, StandardCharsets.UTF_8);
~~~

Hai cách này phù hợp khi **đã biết tệp nhỏ** và giới hạn bộ nhớ phù hợp. `readAllBytes` trả toàn bộ nội dung trong một mảng; `readString` giải mã toàn bộ nội dung thành `String`.

Chúng **không phù hợp** cho file không rõ kích thước hoặc có thể rất lớn. Tài liệu `Files.readAllBytes` ghi rõ đây là phương thức cho tình huống đơn giản, không phải giải pháp đọc file lớn; khi không thể cấp phát mảng có thể gặp `OutOfMemoryError`.

`Files.readString(Path)` mặc định dùng UTF-8. Quá trình giải mã có thể ném `IOException` khi dữ liệu không hợp lệ theo charset được chỉ định; không nên mặc định file văn bản luôn được mã hóa UTF-8 chỉ vì tên mở rộng là `.txt`.

### 6.2. Tại sao Files.size chưa phải giới hạn an toàn?

~~~java
long size = Files.size(file);
if (size > MAX_BYTES) {
    throw new java.io.IOException("File too large");
}

byte[] data = Files.readAllBytes(file);
~~~

Đoạn trên chỉ là **kiểm tra sớm**. `Files.size` phản ánh thông tin tại thời điểm đọc metadata; nội dung file có thể thay đổi trước hoặc trong khi `readAllBytes` thực hiện. Size cũng không đại diện một cách đáng tin cậy cho mọi loại file đặc biệt/virtual file.

Để thực sự giới hạn tổng byte được nhận, phải **đếm byte khi đang đọc** và dừng ngay khi vượt ngân sách.

### 6.3. Đọc theo stream với bộ đệm hữu hạn

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long countBytes(Path file) throws IOException {
    byte[] buffer = new byte[8192];
    long count = 0;

    try (InputStream in = Files.newInputStream(file)) {
        int n;
        while ((n = in.read(buffer)) != -1) {
            count += n;
        }
    }

    return count;
}
~~~

Cách đọc này không đưa toàn bộ nội dung vào một mảng. Bộ đệm tạm thời chỉ khoảng 8 KiB, nhưng mã mẫu **chưa** giới hạn **tổng thời gian** hoặc **tổng số byte đọc**: nếu nguồn dữ liệu không kết thúc, vòng lặp vẫn có thể tiếp tục rất lâu. Cần bổ sung ngân sách byte, deadline hoặc chính sách hủy nếu yêu cầu hệ thống.

### 6.4. Giới hạn số byte thực sự được đọc

Ví dụ dưới đây trả về tối đa `maxBytes` dữ liệu; nếu file chứa nhiều hơn giới hạn thì ném `IOException` thay vì tiếp tục tích lũy trong bộ nhớ.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static byte[] readAtMost(Path file, int maxBytes) throws IOException {
    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must not be negative");
    }

    byte[] buffer = new byte[8192];
    int total = 0;

    try (InputStream in = Files.newInputStream(file);
         ByteArrayOutputStream out = new ByteArrayOutputStream()) {

        int n;
        while ((n = in.read(buffer)) != -1) {
            if (n > maxBytes - total) {
                throw new IOException(
                        "File exceeds " + maxBytes + " bytes");
            }

            out.write(buffer, 0, n);
            total += n;
        }
        return out.toByteArray();
    }
}
~~~

`maxBytes - total` không âm trong luồng hợp lệ vì `total` chỉ được tăng khi dữ liệu chưa vượt ngưỡng. Nếu `maxBytes=0`, một tệp rỗng hợp lệ, còn bất kỳ byte nào cũng bị từ chối.

Cách đọc này bảo đảm **số byte được tích lũy không vượt `maxBytes`**. Tuy nhiên, `ByteArrayOutputStream` và `toByteArray()` có thể tạo bản sao/buffer phụ; lượng RAM cực đại không nhất thiết bằng chính xác `maxBytes`. Dù vậy, nó giúp giới hạn bộ nhớ ở bậc `O(maxBytes)` và ngăn tải dữ liệu không giới hạn.

Nếu chỉ cần tạo hash, kiểm tra chữ ký hoặc chuyển tiếp dữ liệu, tốt hơn là **xử lý từng chunk rồi bỏ** thay vì giữ toàn bộ nội dung trong RAM.

## 7. Giới hạn bộ nhớ không đồng nghĩa giới hạn thời gian

Một ứng dụng đọc file không đáng tin cậy thường cần ngân sách độc lập:

| Tài nguyên | Nguy cơ | Cách kiểm soát |
|---|---|---|
| Tổng byte dữ liệu | File cực lớn hoặc dữ liệu bất thường | Đếm byte trong vòng lặp đọc; dừng khi vượt giới hạn |
| Heap | `readAllBytes`, `readAllLines` hoặc collect toàn bộ | Xử lý theo chunk; chỉ giữ phần cần thiết |
| Độ dài mỗi dòng | Một dòng dài hàng GB | Dùng bộ đọc có giới hạn ký tự/byte; `readLine` không tự áp đặt ngưỡng |
| Số dòng | Hàng triệu dòng | Dừng sau N dòng; không collect toàn bộ |
| Thời gian | Đọc rất chậm hoặc file đặc biệt không kết thúc | Deadline/cancellation theo kiến trúc và nguồn dữ liệu |
| File descriptor | Quên đóng stream/channel | `try`-with-resources |
| Độ sâu cây thư mục | Cây quá sâu hoặc link vòng | Giới hạn `maxDepth`; không FOLLOW_LINKS nếu không cần |
| Số mục trong cây | Thư mục rất rộng | Đếm số mục, dừng duyệt khi vượt ngưỡng |
| Dữ liệu giải nén | Zip bomb, input nhỏ nhưng giải nén khổng lồ | Giới hạn dữ liệu **sau giải nén** riêng với byte nguồn |

Không có một tham số `maxBytes` nào tự giải quyết tất cả các rủi ro trên. Đối với file do người dùng tải lên, cần kết hợp chính sách kích thước, loại nội dung, thời gian và giới hạn tài nguyên của môi trường chạy.

## 8. Đọc văn bản theo dòng: tiện lợi và cạm bẫy

### 8.1. BufferedReader

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void printFirstLines(Path path, int maxLines)
        throws IOException {

    if (maxLines < 0) {
        throw new IllegalArgumentException("maxLines must be nonnegative");
    }

    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

        for (int i = 0; i < maxLines; i++) {
            String line = reader.readLine();
            if (line == null) {
                break;
            }
            System.out.println(line);
        }
    }
}
~~~

`BufferedReader` thích hợp khi chỉ cần đọc từng dòng. Tuy nhiên, `readLine()` tạo một `String` chứa **toàn bộ dòng**. Một file có một dòng cực dài vẫn có thể tiêu tốn rất nhiều bộ nhớ dù `maxLines=1`.

Nếu đầu vào không đáng tin cậy, cần giới hạn kích thước file/byte trước hoặc dùng một parser có giới hạn độ dài mỗi dòng khi đọc tuần tự từng ký tự hoặc từng byte.

### 8.2. Files.lines là Stream và cần đóng

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static void showLines(Path path) throws java.io.IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        lines.limit(20).forEach(System.out::println);
    }
}
~~~

`Files.lines` trả về một stream các dòng đọc lazily; nó vẫn nắm giữ tài nguyên file cho đến khi đóng. Dùng `try`-with-resources để bảo đảm resource được giải phóng.

`limit(20)` giới hạn **số dòng được phát ra**, không bảo đảm mỗi dòng nhỏ, không giới hạn byte đầu vào và không phải deadline. Cũng cần tránh các pipeline như `Files.lines(path).toList()` với file lớn, vì toàn bộ các dòng sẽ được giữ trong bộ nhớ.

### 8.3. Charset và dữ liệu lỗi

Đối với text, chọn charset minh bạch:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

`Files.readString` là tiện ích cho file nhỏ. Nếu muốn kiểm soát chặt nội dung UTF-8 khi dùng bộ đọc có giới hạn byte, có thể giải mã qua `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện dãy byte lỗi, thay vì tùy API mặc định thay bằng ký tự thay thế.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeStrictUtf8(byte[] bytes)
        throws java.nio.charset.CharacterCodingException {

    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
~~~

Cần phân biệt giới hạn byte (dung lượng lưu trữ) với giới hạn ký tự Unicode/code point. Một ký tự có thể chiếm nhiều byte UTF-8; một số ký tự Unicode được biểu diễn bằng hai UTF-16 code units trong Java. Giới hạn theo byte không tương đương giới hạn theo số ký tự người dùng nhìn thấy.

## 9. Duyệt thư mục: độ sâu, số mục và symbolic link

### 9.1. Files.list chỉ duyệt một cấp

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static void printEntries(Path dir) throws IOException {
    try (Stream<Path> entries = Files.list(dir)) {
        entries.limit(100).forEach(System.out::println);
    }
}
~~~

`Files.list` trả về stream các mục trong thư mục, không tự đi sâu xuống mọi thư mục con. Stream phải được đóng. Khi thao tác duyệt gặp lỗi I/O sau khi stream đã mở, một số API stream có thể bọc `IOException` trong `UncheckedIOException`; cần cân nhắc đường xử lý lỗi khi duyệt.

### 9.2. Files.walk có maxDepth

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static void scanShallow(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root, 2)) {
        paths.limit(200).forEach(System.out::println);
    }
}
~~~

`maxDepth` giới hạn độ sâu tìm kiếm. `limit(200)` giới hạn số phần tử được consumer xử lý trong pipeline; nó không thay thế deadline hoặc các giới hạn nội bộ của filesystem provider.

Mặc định, `Files.walk` **không đi theo symbolic link**. Nếu chỉ định `FileVisitOption.FOLLOW_LINKS`, quá trình đi theo link có thể dẫn ra ngoài root hoặc tạo vòng. Không dùng `FOLLOW_LINKS` khi không thực sự cần tính năng này.

### 9.3. FileVisitor để dừng kiểm soát hơn

Khi cần kiểm soát tổng số mục thăm, độ sâu, loại file và nhánh được duyệt, `Files.walkFileTree` cùng `SimpleFileVisitor`/`FileVisitResult` thường rõ ràng hơn.

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

static int countUpTo(Path root, int maxEntries)
        throws IOException {

    if (maxEntries < 0) {
        throw new IllegalArgumentException("maxEntries must be >= 0");
    }

    final int[] count = {0};

    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult preVisitDirectory(
                Path dir, BasicFileAttributes attrs) {

            if (count[0] >= maxEntries) {
                return FileVisitResult.TERMINATE;
            }
            count[0]++;
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult visitFile(
                Path file, BasicFileAttributes attrs) {

            if (count[0] >= maxEntries) {
                return FileVisitResult.TERMINATE;
            }
            count[0]++;
            return FileVisitResult.CONTINUE;
        }
    });

    return count[0];
}
~~~

Ví dụ minh họa dừng sau ngưỡng số mục (có tính cả thư mục); `FileVisitor` vẫn cần chính sách xử lý lỗi phù hợp và giới hạn độ sâu nếu dữ liệu đầu vào có cấu trúc rất sâu. Để giới hạn độ sâu, có overload `walkFileTree(start, options, maxDepth, visitor)`.

Khi bật `FOLLOW_LINKS`, một chu trình symbolic link có thể được báo qua `FileSystemLoopException` trong quá trình duyệt. Cần xác định rõ cách xử lý `visitFileFailed` thay vì bỏ qua mọi lỗi.

## 10. Ví dụ hoàn chỉnh: đọc file UTF-8 có giới hạn byte

Đoạn mã sau là một ứng dụng console độc lập, có thể lưu vào file `BoundedFileReaderDemo.java`. Nó:

1. Nhận thư mục gốc và một đường dẫn **tương đối** do caller cung cấp.
2. Kiểm tra cú pháp không thoát khỏi thư mục gốc.
3. Tra cứu real path và xác nhận vị trí thực tế tại thời điểm kiểm tra.
4. Kiểm tra đây là regular file.
5. Đọc từng chunk và từ chối file vượt quá **1 MiB**.
6. Giải mã UTF-8 theo chế độ báo lỗi khi dữ liệu không hợp lệ.
7. Đóng `InputStream` bằng `try`-with-resources.

> **Phạm vi an toàn:** ví dụ nhằm minh họa kiểm tra đường dẫn và giới hạn tài nguyên, **không** phải một sandbox chống đối thủ thay đổi symlink/thư mục đồng thời. Nếu attacker có quyền sửa cây thư mục trong lúc truy cập, phải sử dụng cơ chế mở an toàn bằng directory handle và phân quyền OS như mục 5.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundedFileReaderDemo {

    private static final int MAX_BYTES = 1024 * 1024;

    private static Path resolveAllowedFile(Path root, String supplied)
            throws IOException {

        Path realRoot = root.toRealPath();
        Path relative = Path.of(supplied);

        if (relative.isAbsolute()) {
            throw new IOException("Absolute path is not allowed");
        }

        Path lexical = realRoot.resolve(relative).normalize();
        if (lexical.equals(realRoot)
                || !lexical.startsWith(realRoot)) {
            throw new IOException("Path escapes allowed directory");
        }

        Path realFile = lexical.toRealPath(); // follows symbolic links

        if (!realFile.startsWith(realRoot)
                || !Files.isRegularFile(realFile)) {
            throw new IOException("Resolved file is outside allowed area"
                    + " or is not regular");
        }

        // TOCTOU caution: the file may change after these checks.
        return realFile;
    }

    private static byte[] readAtMost(Path path, int maxBytes)
            throws IOException {

        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes < 0");
        }

        byte[] buffer = new byte[8192];
        int total = 0;

        try (InputStream input = Files.newInputStream(path);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            int n;
            while ((n = input.read(buffer)) != -1) {
                if (n > maxBytes - total) {
                    throw new IOException("File size exceeds limit");
                }

                output.write(buffer, 0, n);
                total += n;
            }
            return output.toByteArray();
        }
    }

    private static String decodeStrictUtf8(byte[] bytes)
            throws java.nio.charset.CharacterCodingException {

        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java BoundedFileReaderDemo"
                    + " <root-directory> <relative-file>");
            return;
        }

        Path root = Path.of(args[0]);
        Path allowedFile = resolveAllowedFile(root, args[1]);
        byte[] data = readAtMost(allowedFile, MAX_BYTES);
        String text = decodeStrictUtf8(data);

        // Không in nội dung file tùy ý ra log.
        System.out.println("UTF-8 chars read: " + text.length());
        System.out.println("Bytes read: " + data.length);
    }
}
~~~

Biên dịch và chạy trong một hệ thống có JDK phù hợp:

~~~bash
javac BoundedFileReaderDemo.java
java BoundedFileReaderDemo /srv/app/data reports/summary.txt
~~~

Ví dụ lệnh sử dụng cú pháp đường dẫn kiểu Unix. Trên Windows, thay `/srv/app/data` bằng đường dẫn thư mục của hệ thống.

**Những giới hạn cần nhớ:** ví dụ dùng `ByteArrayOutputStream` nên bộ nhớ vẫn tỷ lệ với ngưỡng 1 MiB (cộng các bản sao và `String`); nó không thiết lập deadline; và thao tác mở bằng `Files.newInputStream` vẫn có cửa sổ TOCTOU sau các bước xác minh. Đối với một tác vụ bảo mật thực sự, cần thiết kế mô hình tin cậy và cách mở đối tượng tệp trong file system cụ thể.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `Path.of(...)` kiểm tra file tồn tại | Nó chỉ tạo đường dẫn, chưa truy cập nội dung tệp |
| `normalize` giải quyết symbolic link | `normalize` chỉ xử lý cú pháp đường dẫn |
| `toAbsolutePath` giống `toRealPath` | Absolute path không chứng minh file tồn tại, real path truy cập file system |
| `path.startsWith(root)` là sandbox an toàn tuyệt đối | Đây là kiểm tra từ vựng; symlink và TOCTOU vẫn đáng lo |
| `String.startsWith(rootString)` đủ chống path traversal | Tiền tố chuỗi có thể nhầm tên thư mục; dùng `Path.startsWith` với root phù hợp |
| `Files.exists(path) == false` chứng minh file không có | Có thể không xác định do lỗi I/O hoặc quyền truy cập |
| `Files.isSymbolicLink(path) == false` đảm bảo không có symlink ở cha | Nó chỉ kiểm tra mục được nêu, không bảo đảm toàn bộ chuỗi cha |
| `NOFOLLOW_LINKS` dùng được cho mọi phương thức Files | Chỉ những API có option tương ứng mới hỗ trợ |
| `toRealPath` rồi `readString` loại bỏ mọi race | File system có thể thay đổi giữa kiểm tra và mở |
| `Files.size` trước `readAllBytes` là giới hạn cứng | Size có thể thay đổi; phải đếm byte thực đọc |
| `readAllLines` và `readAllBytes` phù hợp file bất kỳ | Chúng tải dữ liệu vào bộ nhớ, không thích hợp với file rất lớn |
| `Files.lines(...).limit(5)` giới hạn kích thước mỗi dòng | Chỉ giới hạn số dòng được xử lý |
| `Files.lines` tự đóng khi `forEach` kết thúc | Cần đóng stream bằng `try`-with-resources |
| `Files.walk(root, 2)` tự bảo đảm ít phần tử | Nó giới hạn độ sâu, không giới hạn số mục trong cây |
| `FOLLOW_LINKS` luôn an toàn khi duyệt cây | Có thể đi ra ngoài root hoặc gặp chu trình link |
| `ByteArrayOutputStream` với maxBytes dùng đúng bằng maxBytes RAM | Có thể có cấp phát/bản sao phụ, chỉ nên coi bộ nhớ tỷ lệ với giới hạn |

## 12. Checklist thiết kế API đọc file thực tế

Trước khi đưa chức năng đọc file vào ứng dụng:

1. **Phạm vi đường dẫn:** root nào đáng tin cậy, caller được cung cấp tên file hay cả đường dẫn tuyệt đối?
2. **Phân tích cú pháp:** xử lý `InvalidPathException`, từ chối đường dẫn tuyệt đối khi chỉ cho phép tương đối.
3. **Kiểm tra thành phần:** dùng `Path.resolve` và `Path.normalize` để kiểm tra từ vựng, không dùng so sánh tiền tố chuỗi.
4. **Chính sách symlink:** cho phép hay cấm link? Cần kiểm tra mục link hay đích? API mở có hỗ trợ `NOFOLLOW_LINKS` không?
5. **Mô hình đối thủ:** liệu một bên khác có thể đổi symlink/thư mục giữa kiểm tra và mở? Nếu có, cần giải pháp cấp directory handle và quyền OS.
6. **Dung lượng:** giới hạn byte thực đọc, không dựa độc nhất vào `Files.size`.
7. **Kiểu nội dung:** file nhị phân hay UTF-8? Quy tắc xử lý byte không hợp lệ là gì?
8. **Bộ nhớ:** đọc toàn bộ có thật sự cần không, hay có thể xử lý theo chunk?
9. **Giới hạn thời gian:** có thể đọc vô hạn từ nguồn đặc biệt hay bị chậm bất thường không?
10. **Duyệt thư mục:** giới hạn độ sâu, số mục và chính sách `FOLLOW_LINKS`.
11. **Dọn dẹp:** đóng `InputStream`, `Channel`, `DirectoryStream` và stream do `Files.lines`/`walk`/`list` trả về.
12. **Xử lý lỗi:** phân biệt không tìm thấy, quyền truy cập, tệp vượt giới hạn, dữ liệu UTF-8 lỗi và file system thay đổi.
13. **Kiểm thử:** dùng tệp rỗng, tệp đúng ngưỡng, vượt ngưỡng một byte, một dòng dài, symlink gãy, symlink ra ngoài root và tệp biến đổi trong lúc đọc.
14. **Vận hành:** giới hạn quyền tài khoản chạy, theo dõi số file descriptor, thời gian I/O và lượng RAM.

## 13. Câu hỏi tự kiểm tra

1. `Path.of("a/b")` có kiểm tra xem file có tồn tại không?
2. Vì sao `normalize()` không đủ để kiểm tra một đường dẫn có symlink?
3. Khi nào `toRealPath()` ném `IOException`?
4. Khác biệt giữa `Files.exists(path)` và `Files.exists(path, NOFOLLOW_LINKS)` khi symlink bị gãy?
5. `Files.readSymbolicLink` có trả ngay đường dẫn đích đã chuẩn hóa thành tuyệt đối không?
6. Vì sao `base.resolve(userInput)` có thể không nằm trong `base`?
7. So sánh `Path.startsWith(Path)` và `String.startsWith(String)` khi kiểm tra thư mục gốc.
8. Path traversal có thể xảy ra dù tên đường dẫn không chứa `..` không?
9. Vì sao kiểm tra `toRealPath` trước khi mở file vẫn có cửa sổ TOCTOU?
10. `SecureDirectoryStream` hỗ trợ những trường hợp nào và vì sao không thể giả định luôn có?
11. Vì sao `Files.size` không phải giới hạn tuyệt đối nếu file có thể thay đổi?
12. Điều gì xảy ra nếu một file rất lớn được truyền tới `Files.readAllBytes`?
13. `Files.lines(path).limit(10)` có ngăn một dòng dài hàng trăm MB không?
14. Tại sao cần `try`-with-resources với `Files.walk` và `Files.lines`?
15. Hai giới hạn `maxDepth` và `maxEntries` giải quyết hai vấn đề khác nhau nào?
16. Ví dụ `BoundedFileReaderDemo` giới hạn điều gì và **không** bảo đảm điều gì?

## 14. Tài liệu chính thức cho Java SE 27

- [Java SE 27 API — Path](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): cách tạo, kết hợp, rút gọn, chuyển sang absolute/real path và so sánh thành phần đường dẫn.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): kiểm tra tệp, symbolic link, mở file, `readString`, `readAllBytes`, `lines`, `list`, `walk` và `walkFileTree`.
- [Java SE 27 API — LinkOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/LinkOption.html): ý nghĩa `NOFOLLOW_LINKS`.
- [Java SE 27 API — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác tương đối với directory handle nhằm giảm race trong các tình huống được hỗ trợ.
- [Java SE 27 API — FileVisitor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileVisitor.html): duyệt cây có kiểm soát và xử lý lỗi.
- [Java SE 27 API — FileVisitOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/FileVisitOption.html): tùy chọn `FOLLOW_LINKS`.
- [Java SE 27 API — InputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/InputStream.html): đọc byte tuần tự và quản lý vòng đời stream.
- [Java SE 27 API — BufferedReader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/BufferedReader.html): đọc văn bản theo dòng.
- [Java SE 27 API — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): kiểm soát lỗi giải mã văn bản.
- [Java SE 27 API — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/ByteArrayOutputStream.html): tích lũy byte trong bộ nhớ khi có ngưỡng hợp lý.

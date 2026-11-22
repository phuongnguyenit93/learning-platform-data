# Normalize không thay thế việc xử lý symbolic link trong Java NIO

## 1. Vấn đề cốt lõi: đường dẫn nhìn an toàn chưa chắc trỏ tới tài nguyên an toàn

Khi ứng dụng Java nhận một tên tệp từ người dùng, API hoặc nội dung giải nén, ta thường muốn giới hạn mọi thao tác trong một thư mục tin cậy, ví dụ `/srv/app/uploads`. Một bước quen thuộc là dùng `Path.normalize()` để loại `.` và `..` dư thừa.

Nhưng **`Path.normalize()` chỉ là thao tác trên cấu trúc tên đường dẫn**. Nó **không mở filesystem, không xác minh tệp tồn tại, không kiểm tra symbolic link và không biết thực tế mỗi thành phần tên trỏ đến đâu**.

Một symbolic link (symlink) là một entry chứa tham chiếu tới đường dẫn khác. Nó có thể khiến đường dẫn **nằm bên trong thư mục cho phép về mặt cú pháp**, nhưng thao tác I/O thực tế lại truy cập dữ liệu **bên ngoài**.

~~~text
Filesystem:

/srv/app/uploads/
    public.txt
    latest -> /var/private
              (symbolic link)

/var/private/
    secret.txt

Đầu vào: latest/secret.txt
Kết quả normalize:
/srv/app/uploads/latest/secret.txt
            │
            └── VẪN có prefix /srv/app/uploads theo cú pháp

Nhưng khi hệ điều hành đi theo symlink:
latest → /var/private
           │
           └── /var/private/secret.txt   (ngoài uploads)
~~~

**Kết luận quan trọng:** `normalize()` giúp xử lý những đoạn đường dẫn như `a/../b`, nhưng **không thay thế chính sách xử lý symbolic link**, không đủ để chống mọi kiểu path traversal và không tạo ra một cơ chế sandbox filesystem.

Bài học này phân biệt lexical path và đường dẫn thực, giải thích `toRealPath()`, `NOFOLLOW_LINKS`, kiểm tra containment, race condition và hướng thiết kế an toàn trong Java 17+.

## 2. Ba thao tác Path rất dễ bị nhầm

### 2.1. `normalize()` — chuẩn hóa thuần cú pháp

~~~java
Path p = Path.of("docs", ".", "drafts", "..", "report.txt");
System.out.println(p.normalize());
~~~

Đầu ra thường là:

~~~text
docs/report.txt
~~~

`normalize()` loại các đoạn `.` và một số cặp `tên/..` theo quy tắc đường dẫn của provider. Nó **không** truy cập filesystem nên vẫn hoạt động với đường dẫn chưa tồn tại.

Lưu ý đặc biệt từ hợp đồng Java: nếu thành phần ngay trước `..` là symbolic link, việc bỏ cặp tên/`..` có thể **thay đổi tài nguyên được trỏ tới**, vì cách phân giải symlink của filesystem không tương đương thao tác xóa chuỗi.

Ví dụ mang tính khái niệm:

~~~text
dir/link -> /different/location

Đường dẫn gốc: dir/link/../file.txt
Sau normalize: dir/file.txt

Hai đường dẫn không nhất thiết trỏ cùng một file thực.
~~~

Do đó, không được mô tả `normalize()` là "resolve symlink" hoặc "canonicalize filesystem path".

### 2.2. `toAbsolutePath()` — lấy đường dẫn tuyệt đối

~~~java
Path absolute = Path.of("reports", "a.txt").toAbsolutePath();
~~~

Phương thức này chuyển đường dẫn tương đối thành đường dẫn tuyệt đối theo filesystem/provider, thường dựa trên working directory. Nó **không xác minh đích tồn tại và không mặc nhiên xử lý symbolic link**.

`toAbsolutePath().normalize()` vẫn là một đường dẫn được biến đổi chủ yếu theo cú pháp, **không phải bằng chứng đích I/O thực nằm bên trong thư mục cho phép**.

### 2.3. `toRealPath()` — tìm đường dẫn thực của mục đang tồn tại

~~~java
Path real = path.toRealPath();
~~~

Với provider filesystem mặc định và tùy chọn mặc định, `toRealPath()` trả đường dẫn tuyệt đối thực tới mục **đã tồn tại**, loại thành phần dư thừa và **đi theo symbolic link** để tìm đích. Nó có thể ném `IOException` khi mục không tồn tại, đường dẫn lỗi, quyền không đủ hoặc bị lỗi I/O.

Khác với `normalize()`, `toRealPath()` làm việc với trạng thái filesystem thực tế tại thời điểm gọi.

| API | Cần mục tồn tại? | Đi theo symlink? | Ý nghĩa |
| --- | --- | --- | --- |
| `normalize()` | Không | Không truy cập filesystem | Rút gọn cấu trúc tên đường dẫn |
| `toAbsolutePath()` | Không | Không tự xác minh symlink | Lấy đường dẫn tuyệt đối |
| `toAbsolutePath().normalize()` | Không | Không xác minh đích I/O | Absolute + lexical normalization |
| `toRealPath()` | Thường có | Có, theo mặc định | Xác định đường dẫn thực tại thời điểm kiểm tra |
| `toRealPath(NOFOLLOW_LINKS)` | Thường có | Không theo symlink theo chính sách option | Không thích hợp để chứng minh đích sau khi follow nằm trong root |

Từ "thường" để ghi nhận provider-specific semantics; khi thiết kế an toàn phải hiểu hợp đồng của filesystem đang sử dụng. Trên filesystem có symlink, khác biệt này đặc biệt quan trọng.

## 3. Một ví dụ lỗi: kiểm tra prefix sau normalize rồi tin là an toàn

Giả sử `trustedRoot` là thư mục ứng dụng cho phép đọc:

~~~java
Path trustedRoot = Path.of("/srv/app/uploads")
        .toAbsolutePath().normalize();

Path supplied = Path.of("latest/secret.txt");
Path candidate = trustedRoot.resolve(supplied).normalize();

if (!candidate.startsWith(trustedRoot)) {
    throw new SecurityException("Outside root");
}

// Không an toàn chỉ nhờ phép kiểm tra trên!
byte[] data = Files.readAllBytes(candidate);
~~~

Đoạn trên là **mảnh minh họa lỗi**, không phải chương trình chạy độc lập, và dấu `/` là ví dụ trên hệ thống dùng đường dẫn kiểu Unix.

Nếu `uploads/latest` là symlink tới `/var/private`, `candidate.startsWith(trustedRoot)` **vẫn đúng**, vì phép so sánh xét **các thành phần tên của Path**, không bắt buộc mở symlink và xác minh đích.

Phép kiểm tra trên bảo vệ một phần khỏi traversal **thuần chữ** như `../../etc/passwd` nhưng không bảo vệ khỏi **symlink traversal**.

### Vì sao phải dùng `Path.startsWith` chứ không dùng `String.startsWith`?

Đừng thay bằng:

~~~java
candidate.toString().startsWith(trustedRoot.toString());
~~~

Nếu root là `/srv/app/data` thì tên `/srv/app/database-secret` cũng bắt đầu bằng chuỗi `/srv/app/data`. `Path.startsWith(Path)` là so sánh **theo thành phần đường dẫn và quy tắc provider**, tránh lỗi prefix text đơn giản đó.

Nhưng ngay cả `Path.startsWith(Path)` cũng chỉ có ý nghĩa trên **những Path đang được so sánh**; nếu cả hai vẫn là lexical path thì nó không xác minh symlink.

## 4. Kiểm tra đích thực của file đã tồn tại

Nếu chính sách cho phép **theo symlink nhưng chỉ khi đích vẫn ở trong trusted root**, một bước kiểm tra hữu ích là:

~~~java
Path rootReal = trustedRoot.toRealPath();

Path userInput = Path.of(userProvidedName);
if (userInput.isAbsolute()) {
    throw new SecurityException("Absolute paths not allowed");
}

Path candidate = trustedRoot.resolve(userInput).normalize();
Path candidateReal = candidate.toRealPath();

if (!candidateReal.startsWith(rootReal)) {
    throw new SecurityException("Resolved path escapes root");
}

// candidateReal nằm trong rootReal tại thời điểm kiểm tra.
// Tuy nhiên vẫn phải xét race condition trước lúc mở file.
~~~

Đây là **mảnh mã minh họa**, với `trustedRoot` và `userProvidedName` đã được khai báo; cần xử lý `IOException` do đường dẫn hoặc filesystem.

Điểm chính:

1. `rootReal` có thể là đường dẫn tuyệt đối thực của thư mục gốc tin cậy.
2. `userInput.isAbsolute()` giúp loại tên tuyệt đối do người gọi cung cấp; tránh để logic `resolve` lệ thuộc ngữ nghĩa provider với path tuyệt đối.
3. `candidateReal` được xác định sau khi đi theo symlink trong đường dẫn ở thời điểm kiểm tra.
4. `candidateReal.startsWith(rootReal)` kiểm tra containment của **đường dẫn đã resolve**; symlink trỏ ra ngoài root sẽ bị phát hiện.
5. `toRealPath()` không dùng trực tiếp cho đích **chưa tồn tại**; phần tạo file mới cần chiến lược khác.
6. Kiểm tra này **chưa loại trừ Time-of-Check to Time-of-Use (TOCTOU)** nếu đường dẫn hoặc symlink thay đổi sau khi kiểm tra.

Đây là một **lớp phòng vệ**, không phải sự bảo đảm tuyệt đối rằng lời gọi `Files.newInputStream(candidateReal)` hoặc `Files.readAllBytes(candidate)` về sau sẽ luôn truy cập cùng tài nguyên.

### Chính sách phải rõ: cho phép hay từ chối symlink?

Hai chính sách hợp lệ nhưng khác nhau:

- **Cho phép symlink nội bộ:** chấp nhận `docs/current.txt -> docs/v2.txt` nếu đích thực vẫn nằm trong root; từ chối link trỏ ra ngoài.
- **Không cho phép symlink:** từ chối mọi symlink trên các thành phần mà ứng dụng dùng để truy cập tài nguyên, kể cả khi đích của chúng đang nằm trong root.

Chính sách thứ hai cần kiểm tra hoặc mở đường dẫn bằng những API có khả năng không follow symlink và chống thay đổi giữa các bước; chỉ gọi `normalize()` hoặc `toRealPath()` một lần là chưa đủ.

## 5. Ví dụ Java 17+ chạy được: lexical inside nhưng real outside

Chương trình tạo một thư mục tạm gồm một vùng tin cậy và một vùng khác cùng cấp. Trong vùng tin cậy có `public.txt`. Nó thử tạo symlink `redirect` từ vùng tin cậy tới vùng bên ngoài; nếu hệ thống hỗ trợ, chương trình chứng minh:

- Đường dẫn `trusted/redirect/secret.txt` **lexically startsWith(trusted)**.
- Đích thực của đường dẫn đó **không startsWith(trustedReal)**.
- Một đường dẫn `../outside/secret.txt` sau `normalize` bị loại bằng phép kiểm tra lexical.
- File `public.txt` thực sự nằm trong vùng tin cậy.

Một số môi trường Windows yêu cầu quyền đặc biệt để tạo symbolic link; mã xử lý trường hợp không có quyền/thư viện không hỗ trợ mà không giả định mọi hệ điều hành giống nhau.

Lưu thành `NormalizeVsSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class NormalizeVsSymlinkDemo {

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("path-security-");
        Path trusted = workspace.resolve("trusted");
        Path outside = workspace.resolve("outside");
        Path publicFile = trusted.resolve("public.txt");
        Path secretFile = outside.resolve("secret.txt");
        Path link = trusted.resolve("redirect");

        try {
            Files.createDirectory(trusted);
            Files.createDirectory(outside);
            Files.writeString(publicFile, "public",
                    StandardCharsets.UTF_8);
            Files.writeString(secretFile, "private",
                    StandardCharsets.UTF_8);

            Path trustedReal = trusted.toRealPath();

            Path normal = trusted.resolve("public.txt");
            System.out.println("normal lexical inside="
                    + normal.toAbsolutePath().normalize()
                            .startsWith(trusted.toAbsolutePath().normalize()));
            System.out.println("normal real inside="
                    + normal.toRealPath().startsWith(trustedReal));

            Path traversal = trusted.resolve("../outside/secret.txt")
                    .normalize();
            System.out.println("dotdot lexical inside="
                    + traversal.startsWith(trusted.toAbsolutePath().normalize()));

            boolean linkCreated = false;
            try {
                Files.createSymbolicLink(link, outside.toAbsolutePath());
                linkCreated = true;
            } catch (UnsupportedOperationException
                    | IOException | SecurityException ex) {
                // Symlink không có sẵn hoặc không được phép.
            }

            if (!linkCreated) {
                System.out.println("symlink demo=unavailable");
            } else {
                System.out.println("symlink demo=available");
                Path redirected = trusted.resolve("redirect/secret.txt");
                System.out.println("symlink lexical inside="
                        + redirected.toAbsolutePath().normalize()
                                .startsWith(trusted.toAbsolutePath().normalize()));
                System.out.println("symlink real inside="
                        + redirected.toRealPath().startsWith(trustedReal));
            }
        } finally {
            // Xóa symlink như một entry, không xóa đích mà nó trỏ tới.
            Files.deleteIfExists(link);
            Files.deleteIfExists(publicFile);
            Files.deleteIfExists(secretFile);
            Files.deleteIfExists(trusted);
            Files.deleteIfExists(outside);
            Files.deleteIfExists(workspace);
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac NormalizeVsSymlinkDemo.java
java NormalizeVsSymlinkDemo
~~~

Khi filesystem mặc định hỗ trợ tạo symbolic link trong thư mục tạm, stdout là:

~~~text
normal lexical inside=true
normal real inside=true
dotdot lexical inside=false
symlink demo=available
symlink lexical inside=true
symlink real inside=false
~~~

Nếu không thể tạo symlink, stdout thay thế hợp lệ:

~~~text
normal lexical inside=true
normal real inside=true
dotdot lexical inside=false
symlink demo=unavailable
~~~

Phân tích:

1. `trusted` và `outside` là hai thư mục anh em. `trustedReal` dùng làm gốc containment sau khi resolve thực tế.
2. `normal` là file bình thường trong root: cả kiểm tra theo cú pháp và theo đích thực đều trả `true`.
3. `traversal` sau `normalize()` trỏ sang thư mục `outside`, nên phép kiểm tra lexical `startsWith(trusted)` trả `false`.
4. `redirect` nếu được tạo thành công là symlink nằm **bên trong** thư mục `trusted` nhưng trỏ tới `outside`.
5. `redirected` có tên lexical bắt đầu bằng `trusted` nên dòng `symlink lexical inside` là `true`.
6. `redirected.toRealPath()` đi theo symlink và dẫn tới `outside/secret.txt`, ngoài trusted root, nên dòng `symlink real inside` là `false`.
7. Khối `finally` xóa symbolic link như một entry; xóa link không xóa file đích. Các file/thư mục thử nghiệm được dọn theo thứ tự từ con tới cha.

**Điểm cần nhớ:** ví dụ giúp quan sát khác biệt về mặt **phân giải đường dẫn**. Nó không tuyên bố phép `toRealPath()` cộng `startsWith()` tự tạo ra một sandbox chống mọi race condition hoặc attacker có quyền sửa filesystem.

## 6. Symbolic link có thể xuất hiện ở nhiều vị trí trong đường dẫn

Có ít nhất ba kiểu cần phân biệt:

### 6.1. Bản thân file đích là symlink

~~~text
trusted/report.txt -> /outside/report.txt
~~~

`Files.isSymbolicLink(trusted.resolve("report.txt"))` có thể phát hiện entry cuối cùng là symbolic link tại thời điểm gọi. Nhưng nếu một tiến trình khác có quyền thay entry đó, kết quả kiểm tra có thể lỗi thời trước lúc mở.

### 6.2. Thư mục cha ở giữa là symlink

~~~text
trusted/archives -> /outside
trusted/archives/2026.txt
~~~

`Files.isSymbolicLink(trusted.resolve("archives/2026.txt"))` chỉ kiểm tra entry cuối `2026.txt`, không tự nói rằng `archives` là symlink. Dù `2026.txt` là file thường, đường dẫn vẫn đi qua một symlink ở thành phần cha.

Chính sách cấm symlink phải xét **toàn bộ quá trình duyệt**, không chỉ tên cuối.

### 6.3. Symlink kết hợp với `..`

~~~text
trusted/jump -> /outside/folder
trusted/jump/../target.txt
~~~

Xóa `jump/..` theo cú pháp có thể làm tên đường dẫn chuyển thành `trusted/target.txt`, không nhất thiết tương đương cách hệ điều hành phân giải `jump` rồi đi lên thư mục cha của đích thực. Vì vậy, ngay cả phát biểu "normalize luôn giữ nguyên đích vật lý" cũng **sai** khi symbolic link tham gia.

### Broken symlink và symlink cycle

Một symbolic link có thể trỏ tới đường dẫn không tồn tại (broken) hoặc tạo vòng lặp khi đi theo nhiều link. `toRealPath()` có thể ném `IOException`/`FileSystemException` trong các tình huống đó. Đừng biến mọi ngoại lệ thành "đường dẫn an toàn" hoặc "file không tồn tại nên cho phép tạo"; cần xử lý lỗi một cách bảo thủ theo chính sách.

## 7. NOFOLLOW_LINKS dùng để làm gì và không làm được gì?

`java.nio.file.LinkOption.NOFOLLOW_LINKS` là lựa chọn để một số API thao tác với **entry symbolic link** thay vì đi theo link tới đích.

Ví dụ:

~~~java
boolean link = Files.isSymbolicLink(path);

boolean regularWithoutFollowing =
        Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS);

Path lexicalLikeReal =
        path.toRealPath(LinkOption.NOFOLLOW_LINKS);
~~~

Đây là các mảnh minh họa có biến `Path path` đang tồn tại và import tương ứng.

Ý nghĩa:

- `Files.isSymbolicLink(path)` kiểm tra path entry cuối ở thời điểm gọi. Nó không là phép duyệt an toàn toàn bộ cây.
- `Files.isRegularFile(path, NOFOLLOW_LINKS)` thường không coi bản thân symbolic link cuối là regular file, kể cả khi đích của link là file thường.
- `toRealPath(NOFOLLOW_LINKS)` yêu cầu không đi theo symbolic link khi xác định đường dẫn theo ngữ nghĩa của provider; **không dùng kết quả này để chứng minh rằng việc mở một path theo mặc định sẽ không đi ra ngoài root**.
- Những API mở file có tùy chọn `NOFOLLOW_LINKS` phù hợp có thể từ chối symbolic link ở **entry cuối**. Nó không tự bảo đảm các thành phần thư mục cha không phải symbolic link hoặc không bị thay đổi.

Một ví dụ yêu cầu mở entry cuối mà không follow symlink:

~~~java
try (SeekableByteChannel channel = Files.newByteChannel(
        candidate,
        Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Đọc các byte qua channel đã mở.
}
~~~

Mảnh code cần import `java.nio.channels.SeekableByteChannel`, `java.nio.file.*` và `java.util.Set`; biến `candidate` là một `Path`.

Đối với file cuối là symbolic link, lời gọi có thể bị từ chối theo chính sách/provider. **Nhưng parent path vẫn có thể chứa symbolic link**, nên không được khẳng định mảnh code này là đủ để cưỡng chế containment dưới một root có thể bị attacker chỉnh sửa.

Tóm tắt:

| Cách làm | Chặn traversal lexical kiểu `../`? | Nhận biết symlink? | Chống race khi path bị thay? |
| --- | --- | --- | --- |
| `normalize()` + so `startsWith` | Một phần, trên tên đường dẫn | Không | Không |
| `toRealPath()` rồi kiểm tra rootReal | Phát hiện đích thực ở thời điểm kiểm tra | Theo symlink mặc định | Không tự bảo đảm |
| `isSymbolicLink()` rồi `open()` | Không đầy đủ | Kiểm tra tại một thời điểm | Không |
| `NOFOLLOW_LINKS` khi mở entry cuối | Có thể từ chối link cuối | Có tác dụng ở vị trí API hỗ trợ | Không nhất thiết bảo vệ các ancestor |
| Directory-relative secure operations | Có thể giảm mạnh rủi ro thay đổi path giữa các bước | Có thể kiểm soát từng thành phần | Tốt hơn khi provider hỗ trợ và dùng đúng |

## 8. TOCTOU: kiểm tra đúng vẫn có thể mở sai file

TOCTOU là viết tắt của **Time of Check to Time of Use**: trạng thái filesystem có thể thay đổi giữa lúc kiểm tra và lúc sử dụng.

Ví dụ:

~~~text
Thread A / ứng dụng                     Process B / attacker

candidate.toRealPath()
→ /trusted/public.txt
                                        thay public.txt thành symlink
                                        → /outside/secret.txt

Files.readAllBytes(candidate)
→ hệ điều hành đi theo symlink mới
→ đọc file ngoài root
~~~

Ngay cả khi phép kiểm tra `toRealPath()`, `startsWith(rootReal)` vừa trả kết quả tốt, nó chỉ mô tả filesystem **tại một thời điểm**. Nó không khóa tên file hay entry khỏi việc bị đổi.

Mẫu dễ có race:

~~~java
if (!Files.isSymbolicLink(candidate)
        && candidate.toRealPath().startsWith(rootReal)) {
    return Files.readAllBytes(candidate);
}
~~~

Nếu một tiến trình khác có quyền thay directory entry, thời điểm mở thực tế có thể không còn giống thời điểm kiểm tra.

Không nên viết trong tài liệu bảo mật rằng "đã canonicalize nên chắc chắn không bị symlink attack". Đúng hơn: canonicalization là một phép kiểm tra hữu ích, **nhưng cần thêm cơ chế mở/duyệt không dựa vào một tên đường dẫn dễ bị thay thế**.

## 9. SecureDirectoryStream: thao tác tương đối với directory đã mở

Java NIO có giao diện `java.nio.file.SecureDirectoryStream`, dành cho provider có khả năng thao tác **tương đối với một directory stream đang mở**, giúp giảm rủi ro khi các entry trên filesystem bị thay thế đồng thời.

Một chiến lược:

1. Xác định và mở một thư mục gốc mà ứng dụng tin cậy và kiểm soát quyền sửa.
2. Nếu `DirectoryStream` trả về có hỗ trợ `SecureDirectoryStream`, thực hiện các thao tác tương đối với directory đã mở, thay vì liên tục resolve một chuỗi absolute path mới.
3. Với từng thư mục con cần vào, mở tiếp bằng `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` khi chính sách cấm symlink.
4. Với file cuối, dùng `secure.newByteChannel(relativeName, options)` và yêu cầu `NOFOLLOW_LINKS` nếu thích hợp.
5. Truy cập dữ liệu qua **channel đã mở**, không lặp lại bước check rồi mở theo tên toàn cục.

Mảnh Java minh họa đọc một file con trực tiếp:

~~~java
Path baseReal = trustedRoot.toRealPath();

try (DirectoryStream<Path> opened = Files.newDirectoryStream(baseReal)) {
    if (!(opened instanceof SecureDirectoryStream<?>)) {
        throw new UnsupportedOperationException(
                "Provider does not support SecureDirectoryStream");
    }

    @SuppressWarnings("unchecked")
    SecureDirectoryStream<Path> secure =
            (SecureDirectoryStream<Path>) opened;

    Path childName = baseReal.getFileSystem().getPath("public.txt");

    try (SeekableByteChannel file = secure.newByteChannel(
            childName,
            Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
        // Thao tác đọc qua file channel đã mở.
    }
}
~~~

Đây là **mảnh minh họa**, không phải chương trình độc lập. Cần import `java.nio.file.*`, `java.nio.channels.SeekableByteChannel` và `java.util.Set`, cùng một `Path trustedRoot` đã được tin cậy.

**Không giả định `SecureDirectoryStream` luôn có sẵn** trên mọi provider/OS/filesystem. Nếu ứng dụng có yêu cầu bảo mật bắt buộc, khi provider không hỗ trợ nên **fail closed** hoặc sử dụng cơ chế cô lập mạnh hơn, thay vì âm thầm chuyển về mô hình check-then-open dễ bị race.

Ví dụ chỉ mở **một tên con trực tiếp**. Nếu đầu vào gồm nhiều component, phải duyệt từng thành phần directory bằng một `SecureDirectoryStream` mới, kiểm soát `.`/`..`, link và quyền, tuyệt đối không truyền đường dẫn không kiểm soát chứa `../` rồi kỳ vọng một handle cấp root tự tạo sandbox.

`SecureDirectoryStream` có lợi ích mạnh hơn check path thuần túy nhưng không thay thế thiết kế quyền, owner, tính đáng tin của root ban đầu và chính sách truy cập file. Nó cũng không tự giải quyết dữ liệu nhạy cảm trong file đã được mở nếu ứng dụng cho phép người dùng chọn sai file từ đầu.

## 10. Tạo file mới: toRealPath() không thể kiểm tra một đích chưa tồn tại

Một trường hợp phổ biến là upload file mới:

~~~text
trusted/
    users/
       new-image.png   (chưa tồn tại)
~~~

`target.toRealPath()` sẽ lỗi nếu `new-image.png` chưa tồn tại. Không nên thấy lỗi rồi tự cho phép tạo mà bỏ kiểm tra ancestor.

Với chính sách cho phép tạo **file mới** trong một thư mục có thể tin cậy, cần:

- Xác minh root và đường dẫn thư mục cha **đã tồn tại**.
- Xác định đích nằm trong cấu trúc được phép theo policy.
- Nếu root/subdirectory có thể bị attacker đổi, dùng thao tác directory-relative an toàn nếu provider hỗ trợ.
- Tạo bằng `CREATE_NEW` khi muốn thất bại nếu entry cuối đã tồn tại; tránh ghi đè file người khác.
- Dùng `NOFOLLOW_LINKS` hoặc cơ chế không follow entry cuối nếu API/provider hỗ trợ và chính sách yêu cầu.
- Nếu tên file đến từ user, từ chối path tuyệt đối, `..` và các thành phần đặc biệt theo policy; dùng tên basename được kiểm tra hoặc một ID server-side nếu có thể.
- Thiết lập quyền truy cập/ownership và vùng staging thích hợp. `Files.createDirectories()` không phải một cơ chế chống symlink race khi thư mục cha không đáng tin.

Ví dụ lưu upload bằng tên do server sinh thay vì dùng nguyên đường dẫn từ HTTP request thường đơn giản và an toàn hơn. Không cho client chọn thư mục con sâu nếu nghiệp vụ không cần.

### CREATE_NEW có tác dụng gì?

`StandardOpenOption.CREATE_NEW` yêu cầu tạo mới và thất bại nếu entry đích đã tồn tại; thao tác kiểm tra-tạo ở entry cuối được định nghĩa là atomic so với các thao tác tạo khác theo hợp đồng API. Điều này hữu ích để tránh vô tình overwrite một entry có sẵn, nhưng **không thay thế việc bảo vệ toàn bộ parent directory** nếu các ancestor có thể bị đổi.

## 11. Phòng vệ nhiều lớp và ranh giới tin cậy

Không có một câu lệnh `normalize()` nào thay thế được thiết kế bảo mật filesystem. Một hệ thống xử lý đường dẫn từ nguồn không tin cậy có thể áp dụng các lớp sau:

| Lớp phòng vệ | Vai trò |
| --- | --- |
| API chỉ nhận ID/tên file server sinh | Tránh cho user cung cấp path tùy ý |
| Kiểm tra path tuyệt đối và component `..` | Loại các dạng traversal trực tiếp |
| `Path.normalize()` và `Path.startsWith()` | Kiểm tra cấu trúc lexical cho đường dẫn được xây dựng |
| `toRealPath()` với root thật | Phát hiện symlink escape ở thời điểm kiểm tra đối với mục tồn tại |
| `NOFOLLOW_LINKS` và/hoặc `SecureDirectoryStream` | Hạn chế việc theo symlink và giảm check/use race |
| Quyền OS và thư mục do ứng dụng kiểm soát | Ngăn attacker thay link/entry trong vùng tin cậy |
| Tài khoản tiến trình tối thiểu quyền | Hạn chế thiệt hại nếu có lỗi logic |
| Sandboxing / container / mount policy | Tạo ranh giới hệ điều hành bổ sung |
| Logging và test symlink race | Kiểm chứng các tình huống bị lợi dụng |

Phải phân biệt **bảo đảm về đường dẫn** với **ủy quyền người dùng**. Ngay cả file nằm bên trong root đúng policy, không có nghĩa bất kỳ user nào cũng được đọc nó. Ứng dụng vẫn cần kiểm tra quyền truy cập đối với đối tượng/danh tính người dùng.

### Không dựa vào chuỗi và separator

`String.startsWith` không hiểu ranh giới component. Ghép chuỗi thủ công kiểu `root + "/" + filename` còn phụ thuộc separator, absolute path, Windows drive letter và provider. Dùng `Path`/`FileSystem` nhất quán; sau đó áp dụng chính sách containment theo path thực khi cần.

Nếu có nhiều filesystem/provider (`zipfs`, filesystem mạng...), so sánh path của provider khác nhau có thể không có ý nghĩa như path của cùng filesystem. Chỉ so sánh khi hiểu rõ `Path.getFileSystem()` và ngữ nghĩa của provider.

## 12. Các tình huống thường gây nhầm lẫn

### Tình huống A: kiểm tra lexical pass, nhưng symlink trỏ ra ngoài

~~~text
trusted/aliases -> /private
trusted/aliases/account.db
~~~

`normalize().startsWith(trusted)` có thể đúng, nhưng `toRealPath()` (mặc định follow) trỏ ra `/private/account.db`. Đây là ca bài học muốn nhấn mạnh.

### Tình huống B: symlink trỏ tới file khác nhưng vẫn bên trong root

~~~text
trusted/latest.txt -> trusted/v2.txt
~~~

Nếu chính sách **cho phép internal symlink**, có thể chấp nhận sau khi xác minh real containment. Nếu chính sách **cấm mọi symlink**, vẫn phải từ chối. Bảo mật không phải chỉ là “link trỏ ra ngoài hay không”; đó là policy cụ thể.

### Tình huống C: symlink ở ancestor

~~~text
trusted/data -> /private
trusted/data/info.txt
~~~

`Files.isSymbolicLink(trusted/data/info.txt)` không tự kiểm tra `data`. Một API `NOFOLLOW_LINKS` ở file cuối có thể vẫn đi qua link ở thư mục cha nếu không bảo vệ các bước duyệt.

### Tình huống D: đường dẫn đã xác minh bị tráo sau đó

~~~text
Check: trusted/config.txt là file thật.
Race: attacker thay nó bằng symlink.
Use: ứng dụng mở theo tên cũ.
~~~

`toRealPath()` và `isSymbolicLink()` kiểm tra tại thời điểm gọi, không cấp khóa bất biến cho tên file. Dùng handle-based access và quyền filesystem để giảm nguy cơ.

### Tình huống E: file đích chưa có

`toRealPath()` không thể bảo đảm containment của một file chưa tồn tại bằng cách gọi trực tiếp lên target. Hãy bảo vệ các thư mục cha, tạo entry mới với chính sách nhất quán và ưu tiên tên do server sinh.

### Tình huống F: theo dõi directory bằng Files.walk

`Files.walk(...)` theo mặc định không đi theo symbolic link như một directory khi không bật `FOLLOW_LINKS`. Nhưng việc quét cây không biến mọi thao tác sau đó thành an toàn; cây vẫn có thể thay đổi trong lúc hoặc sau khi đi qua, nhất là với thư mục ghi được bởi người khác.

## 13. Checklist thiết kế truy cập file an toàn

Khi viết API đọc hoặc upload từ tên người dùng:

1. **Xác định trusted root**: thư mục có chủ sở hữu và quyền sửa do ứng dụng kiểm soát.
2. **Định nghĩa symlink policy**: cấm hoàn toàn hay cho phép link có đích thực nội bộ?
3. **Giảm quyền chọn path**: ưu tiên ID/basename server sinh hơn relative path tùy ý.
4. **Kiểm tra path syntax**: path tuyệt đối, `..`, ký tự/đường dẫn đặc biệt theo provider.
5. **Dùng lexical normalize như một bước phụ**: hữu ích nhưng không coi là sandbox.
6. **Nếu mục đã tồn tại**, dùng `toRealPath()` để xác minh real containment theo policy khi phù hợp.
7. **Xử lý race**: không mặc định check-then-open là atomic; dùng `SecureDirectoryStream`/handle access hoặc isolation phù hợp.
8. **Với tạo file mới**, bảo vệ parent, dùng `CREATE_NEW` nếu không muốn overwrite, không tự follow link tùy ý.
9. **Không cho process quá nhiều quyền OS**: ngay cả khi lỗi traversal xảy ra, phạm vi truy cập vẫn nên bị giới hạn.
10. **Test cả negative cases**: `../`, absolute path, root prefix giống nhau, symlink ở file cuối, symlink ở ancestor, broken link, replace-during-open, permission denied.
11. **Quản lý fallback**: nếu filesystem thiếu primitive bảo mật cần thiết, trả lỗi thay vì hạ cấp im lặng.
12. **Đánh giá quyền ứng dụng**: file trong root chưa đủ để chứng minh caller có quyền xem nội dung.

## 14. Lỗi phổ biến và cách sửa

**Lỗi 1 — Đồng nhất normalize với canonicalize.** `normalize()` chỉ biến đổi cú pháp, không đi theo symbolic link. Dùng `toRealPath()` để biết đích thực **tại thời điểm kiểm tra**, nhưng không bỏ qua race.

**Lỗi 2 — Kiểm tra `startsWith(root)` trên lexical path rồi mở tùy ý.** Symlink nằm trong root có thể trỏ ra ngoài. Cần policy và cơ chế resolve/open an toàn.

**Lỗi 3 — Dùng `String.startsWith(rootString)`.** Prefix text không có ranh giới component, dễ chấp nhận `data-secret` khi root là `data`. Dùng `Path.startsWith(Path)` phù hợp.

**Lỗi 4 — Chỉ gọi isSymbolicLink trên file cuối.** Symlink có thể ở bất kỳ ancestor nào. Với policy cấm link, phải quản lý từng bước duyệt và hạn chế TOCTOU.

**Lỗi 5 — Nghĩ NOFOLLOW_LINKS ở final file cấm mọi symlink.** Nó không mặc nhiên ngăn ancestor symlink. Cần kiểm soát directory traversal tương đối an toàn.

**Lỗi 6 — Kiểm tra realPath rồi mở lại theo tên không được bảo vệ.** Attacker có thể tráo symlink giữa check và use. Ưu tiên thao tác dựa vào directory/file handle và quyền filesystem.

**Lỗi 7 — Coi mọi lỗi toRealPath là bằng chứng đích “chưa tồn tại nên an toàn”.** Lỗi có thể do broken symlink, permission hoặc vòng link. Không fail open.

**Lỗi 8 — Cho phép path tuyệt đối do user đưa vào.** `root.resolve(userInput)` với absolute path có thể dẫn đến vị trí không mong muốn. Từ chối input tuyệt đối và kiểm tra policy trước khi dùng.

**Lỗi 9 — Tin rằng file trong trusted root tự động được phép đọc.** Còn cần authorization cho từng người dùng và loại dữ liệu.

**Lỗi 10 — Phụ thuộc SecureDirectoryStream mà không kiểm tra support.** Không phải provider nào cũng hỗ trợ; ứng dụng có yêu cầu mạnh nên fail closed nếu thiếu primitive cần thiết.

## 15. Tự kiểm tra

1. `Path.normalize()` có tự đọc symbolic link không? **Không**. Nó xử lý thành phần tên theo cú pháp.
2. `toAbsolutePath().normalize()` có xác minh file tồn tại không? **Không**.
3. `toRealPath()` mặc định xử lý symbolic link ra sao? **Đi theo symlink** để tìm real path của mục đang tồn tại, theo ngữ nghĩa provider.
4. `candidate.normalize().startsWith(root.normalize())` đúng có bảo đảm open không thoát root không? **Không**.
5. Vì sao nên dùng `Path.startsWith` thay vì `String.startsWith`? Vì nó so **component đường dẫn**, không chỉ prefix text.
6. `Files.isSymbolicLink(candidate)` trả false có nghĩa mọi parent không phải symlink không? **Không**.
7. `NOFOLLOW_LINKS` với file cuối có tự chặn link ở parent không? **Không bảo đảm**.
8. `toRealPath()` trước `Files.readAllBytes()` có loại được race khi directory entry bị thay không? **Không hoàn toàn**; đó là TOCTOU.
9. Một file chưa tồn tại có thể gọi `toRealPath()` thành công để kiểm tra không? **Thông thường không**; cần chiến lược tạo file an toàn dựa trên parent.
10. `SecureDirectoryStream` có phải luôn được mọi filesystem cung cấp không? **Không**.
11. Symlink `trusted/latest -> trusted/v2` nên được phép hay không? **Tùy policy**: cho phép internal link hoặc cấm mọi symlink.
12. File nằm trong root đúng policy có tự chứng minh user có quyền xem không? **Không**; phải kiểm tra authorization.
13. Nếu phải bảo vệ dữ liệu nhạy cảm ngay cả khi logic path có lỗi, lớp bảo vệ ngoài Java nào hữu ích? **Quyền OS tối thiểu, root ownership, sandbox/container/mount policy** và cô lập dữ liệu.
14. Mô hình nào tốt hơn khi attacker có thể thay đổi thư mục giữa check và open? **Thao tác qua handle/directories an toàn với no-follow theo từng component**, kết hợp policy rõ ràng.

**Ghi nhớ:** `Path.normalize()` loại thành phần tên thừa nhưng **không biết symbolic link trỏ đi đâu**. Muốn kiểm tra đích đang tồn tại, hãy hiểu `toRealPath()` và containment trên các real path. Muốn chống việc path bị thay giữa kiểm tra và mở, cần cơ chế như `SecureDirectoryStream` nếu provider hỗ trợ, cùng với quyền filesystem và quản lý ownership đáng tin. **Không lấy một phép chuẩn hóa cú pháp làm ranh giới bảo mật của ứng dụng.**

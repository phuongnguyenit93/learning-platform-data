# Path traversal và ranh giới thư mục được phép trong Java IO/NIO.2

Một ứng dụng thường cho người dùng tải ảnh, xem tài liệu, giải nén file hoặc đọc nhật ký thông qua tham số như `file=reports/2026.txt`. Nếu ứng dụng lấy chuỗi do người dùng gửi rồi ghép trực tiếp thành đường dẫn hệ thống, người dùng có thể khiến chương trình truy cập dữ liệu nằm **ngoài thư mục mà họ được phép sử dụng**. Lỗi này gọi là **path traversal** (directory traversal).

Mục tiêu của thiết kế an toàn là biến “chỉ đọc/ghi bên trong thư mục được cấp quyền” thành một **bất biến được kiểm tra trước thao tác IO**. Trong Java, điều đó đòi hỏi hiểu sự khác nhau giữa biểu diễn chuỗi, chuẩn hóa cú pháp, đường dẫn thực trên hệ thống file, symbolic link và quyền truy cập ở thời điểm mở file.

## 1. Path traversal là gì?

Giả sử dịch vụ cho phép tải tài liệu nằm dưới `/srv/app/uploads/alice/` và nhận tên tương đối:

```text
GET /download?name=invoices/2026.txt
```

Cách viết dễ lỗi:

```java
Path file = Path.of("/srv/app/uploads/alice").resolve(userInput);
byte[] content = Files.readAllBytes(file);
```

Đây là **đoạn mã minh họa chưa an toàn**, không phải chương trình độc lập. Nếu `userInput` chứa các thành phần `..`, hoặc là đường dẫn tuyệt đối, vị trí truy cập có thể nằm ngoài nơi được cấp quyền. Không thể tin chuỗi path chỉ vì giao diện thông thường chỉ hiển thị tên file.

Những nguồn đầu vào cần xem là **không tin cậy** gồm tham số HTTP, tên file upload (`Content-Disposition`), đường dẫn trong ZIP/TAR, chuỗi lấy từ hàng đợi, cấu hình do tenant tự sửa và dữ liệu đọc lại từ DB từng được lấy từ người dùng.

Khi lỗi xảy ra, hậu quả có thể gồm đọc file cấu hình/bí mật, ghi đè file của người khác, ghi tệp vào nơi ứng dụng thực thi, hoặc truy cập dữ liệu của tenant khác. Mức độ ảnh hưởng phụ thuộc **quyền tài khoản hệ điều hành đang chạy JVM** và thao tác thực hiện: đọc, tạo, sửa, xóa, liệt kê hay giải nén.

## 2. Ranh giới thư mục: kiểm tra theo thành phần Path

Ta cần phân biệt ba khái niệm:

- **Allowed root**: thư mục gốc đã được máy chủ quyết định, ví dụ thư mục riêng của một tenant. Không để client tự gửi allowed root. Quyền đọc/ghi nên được tách rõ theo nghiệp vụ.
- **User path**: tên/đường dẫn tương đối do client yêu cầu bên dưới root; phải được phân tích như dữ liệu và kiểm tra.
- **Candidate/real path**: đường dẫn sau khi kết hợp và kiểm tra vị trí thực tế. Chỉ sử dụng khi nó thuộc ranh giới cho phép.

Các API quan trọng trong `java.nio.file`:

| API | Có tác dụng | Không bảo đảm |
| --- | --- | --- |
| `Path.of(text)` | Phân tích chuỗi theo filesystem provider/OS | Không tự chặn traversal hay xác minh tồn tại |
| `path.isAbsolute()` | Nhận biết absolute path theo cú pháp nền tảng | Không xử lý hết các dạng path đáng ngờ như drive-relative trên Windows |
| `base.resolve(child)` | Ghép đường dẫn; nếu `child` là absolute, kết quả có thể bỏ qua một phần/toàn bộ `base` | Không kiểm tra quyền |
| `path.normalize()` | Loại bỏ `.` và rút gọn `name/..` trên chuỗi path | **Không** truy cập filesystem, không giải quyết symbolic link |
| `path.toAbsolutePath()` | Tạo biểu diễn absolute path | Không chứng minh nơi trỏ đến là hợp lệ |
| `path.toRealPath()` | Với path tồn tại: trả đường dẫn thực, theo liên kết biểu tượng theo mặc định | File chưa tồn tại sẽ không có real path; kết quả có thể lỗi thời nếu filesystem bị sửa sau khi kiểm tra |
| `candidate.startsWith(root)` | So khớp **các thành phần** của `Path` theo filesystem provider | Không tự giải quyết liên kết biểu tượng hoặc bảo vệ khỏi thay đổi đồng thời |
| `Files.isRegularFile(path)` | Kiểm tra file thường (theo symlink mặc định) | Không thay thế authorization hoặc thao tác mở file an toàn |

**Không dùng `String.startsWith` cho path.** Ví dụ chuỗi `/srv/app/files-backup/secret` bắt đầu bằng `/srv/app/files`, nhưng hai thư mục này là anh em, không phải quan hệ cha–con. `Path.startsWith` phân biệt các thành phần path; tuy nhiên chỉ nên so sánh những Path đã được chuẩn hóa cùng provider và ở dạng tương ứng (thường là absolute/real path).

Tương tự, việc thay `"../"` bằng chuỗi rỗng hoặc chỉ dùng regex chặn một mẫu là thiếu an toàn. Dấu phân cách `/`/`\`, đường dẫn tuyệt đối, dấu chấm, mã hóa URL, chữ hoa/thường và cú pháp đường dẫn phụ thuộc nền tảng. Hãy dùng `Path` để kiểm tra cấu trúc; áp dụng chính sách tên file đơn giản hơn khi có thể.

## 3. Quy trình kiểm tra khi đọc file đã tồn tại

Với một thư mục root được cấu hình và file **đã tồn tại**, quy trình cơ bản là:

1. Xác định allowed root từ phía server; dùng `toRealPath()` để neo root vào vị trí thực đang tồn tại.
2. Yêu cầu tên tương đối, từ chối tên rỗng và đường dẫn absolute. Với ứng dụng chỉ phục vụ file thông thường, nên từ chối luôn mọi thành phần `..` để làm rõ hợp đồng API.
3. Kết hợp `root.resolve(relative).normalize()` và kiểm tra candidate là **con** của root qua `startsWith`; có thể từ chối candidate bằng chính root nếu API chỉ chấp nhận file.
4. Gọi `candidate.toRealPath()` để theo symbolic links tới vị trí vật lý; kiểm tra **lần nữa** `real.startsWith(root)` nhằm ngăn liên kết dẫn ra ngoài.
5. Kiểm tra kiểu đối tượng (ví dụ file thường) và quyền nghiệp vụ; chỉ sau đó mới đọc file. Bắt lỗi IO khi file không tồn tại, quyền OS từ chối hoặc nội dung thay đổi.

Kiểm tra **cả lexical path lẫn real path** là có chủ đích: lexical check loại truy cập thoát root qua `..` hoặc đường dẫn tuyệt đối; real-path check nhận ra link vốn có tên nằm trong root nhưng dẫn đến file ở nơi khác.

## 4. Ví dụ Java 17+ chạy được: giới hạn quyền đọc file

Tạo file `SafeFileRead.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SafeFileRead {
    public static String readInside(Path configuredRoot, String userInput)
            throws IOException {
        if (userInput == null || userInput.isBlank()) {
            throw new IllegalArgumentException("Empty file name");
        }

        // Root do server quản lý, phải tồn tại.
        Path root = configuredRoot.toRealPath();
        Path relative = Path.of(userInput);

        // Chỉ cho phép path tương đối và không có thành phần "..".
        if (relative.isAbsolute()) {
            throw new SecurityException("Absolute path is forbidden");
        }
        for (Path part : relative) {
            if (part.toString().equals("..")) {
                throw new SecurityException("Parent traversal is forbidden");
            }
        }

        // Kiểm tra cấu trúc đường dẫn, không dùng String.startsWith.
        Path candidate = root.resolve(relative).normalize();
        if (candidate.equals(root) || !candidate.startsWith(root)) {
            throw new SecurityException("Outside allowed directory");
        }

        // Theo symbolic links để kiểm tra nơi file thực sự trỏ tới.
        Path real = candidate.toRealPath();
        if (!real.startsWith(root) || !Files.isRegularFile(real)) {
            throw new SecurityException("Not an allowed regular file");
        }

        // Đọc nội dung UTF-8; với binary nên dùng Files.newInputStream.
        return Files.readString(real, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        Path sandbox = Files.createTempDirectory("path-demo-");
        Path root = Files.createDirectories(sandbox.resolve("allowed"));
        Path docs = Files.createDirectories(root.resolve("docs"));

        Files.writeString(
                docs.resolve("hello.txt"), "Xin chao",
                StandardCharsets.UTF_8);

        System.out.println("OK: " + readInside(root, "docs/hello.txt"));

        try {
            readInside(root, "../private.txt");
        } catch (SecurityException expected) {
            System.out.println("BLOCKED: ..");
        }

        try {
            readInside(root, docs.resolve("hello.txt").toString());
        } catch (SecurityException expected) {
            System.out.println("BLOCKED: absolute");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 SafeFileRead.java
java SafeFileRead
```

Stdout (thư mục tạm có tên ngẫu nhiên nhưng không được in):

```text
OK: Xin chao
BLOCKED: ..
BLOCKED: absolute
```

Ý nghĩa từng lớp kiểm tra:

- `"docs/hello.txt"` có đường dẫn tương đối nằm trong root, file tồn tại và là file thường.
- `"../private.txt"` bị chặn **trước khi mở file**, bất kể file đích có tồn tại hay không.
- `docs.resolve("hello.txt").toString()` là absolute path nên bị từ chối ngay cả khi trỏ **đến file hợp lệ**. Quy tắc của API là client chỉ được gửi tên tương đối.
- `toRealPath()` còn ngăn trường hợp `allowed/link.txt` là symbolic link trỏ tới file ngoài root (nếu kiểm tra và sử dụng cùng trạng thái filesystem).

**Giới hạn quan trọng của ví dụ:** Đây là phương pháp hợp lý khi cây thư mục dưới root **không thể bị đối thủ thay symbolic link hoặc parent directory đồng thời**. Vẫn có khoảng thời gian giữa lúc kiểm tra `toRealPath()` và lúc mở qua `Files.readString()` (*time-of-check to time-of-use*, TOCTOU). Nếu kẻ tấn công có quyền sửa cấu trúc thư mục vào thời điểm đó, họ có thể thay đường dẫn sau khi kiểm tra. Phần 6 trình bày cách nâng mức bảo vệ. Đừng xem ví dụ như lời bảo đảm chống mọi cuộc đua filesystem.

**Bài kiểm thử nên bổ sung:** tạo symbolic link **bên trong** allowed root trỏ ra file **bên ngoài**, rồi xác nhận ứng dụng từ chối. Quyền tạo link trên Windows phụ thuộc hệ thống/cấu hình nên không đưa vào stdout bắt buộc của ví dụ.

## 5. Đường dẫn chưa tồn tại: upload, tạo file và ghi dữ liệu

Với file mới, `candidate.toRealPath()` thường ném `NoSuchFileException` vì file chưa tồn tại. **Không nên bỏ qua mọi kiểm tra rồi ghi file mới**. Cần kiểm tra thư mục cha thực đã tồn tại, hạn chế tên, và tạo file không ghi đè.

Một thiết kế đơn giản cho upload: ánh xạ `uploadId` sang tên file do server sinh (ví dụ UUID), lưu tên gốc chỉ làm metadata hiển thị. Đoạn minh họa dưới đây là **một phần của phương thức xử lý upload**, giả định `configuredRoot` đã được cấp quyền riêng và `bytes` đã được kiểm tra kích thước:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

// Bên trong một phương thức throws IOException:
Path root = configuredRoot.toRealPath();
String storedName = UUID.randomUUID() + ".bin";
Path output = root.resolve(storedName).normalize();

if (!output.getParent().equals(root)) {
    throw new SecurityException("Invalid output parent");
}
try (OutputStream out = Files.newOutputStream(
        output, StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    out.write(bytes);
}
```

`CREATE_NEW` tạo file mới một cách nguyên tử về điều kiện **chưa tồn tại tên file đích** và từ chối ghi đè mục đã tồn tại (kể cả symlink có sẵn ở tên cuối). Nó không thay thế kiểm tra quyền, hạn mức dung lượng, bảo vệ parent directories hay sandbox của hệ điều hành.

Nếu bắt buộc cho phép client chọn đường dẫn lồng nhau, hãy kiểm tra từng thành phần theo chính sách, từ chối absolute/parent traversal, ràng buộc với root bằng `Path.startsWith`, rồi xác minh parent directory thực bằng `toRealPath()` nằm trong root. Đảm bảo thư mục cha không thể bị kẻ tấn công đổi thành symbolic link sau khi kiểm tra. Khi tạo thư mục trung gian, `Files.createDirectories` không tự bảo đảm đường dẫn đã nằm trong boundary; phải kiểm soát cả chuỗi thao tác.

Với thao tác **ghi đè, xóa, đổi tên, move**, rủi ro còn lớn hơn: cần xác thực quyền đối với tài nguyên đích lẫn nguồn, xử lý symlink và thực hiện thao tác nguyên tử khi nền tảng hỗ trợ. Tránh những endpoint nhận trực tiếp absolute filesystem paths.

## 6. Symbolic link và TOCTOU: vì sao chỉ normalize chưa đủ?

Xét cấu trúc:

```text
/srv/app/allowed/
    reports/
    current -> /srv/app/private/
```

Ở đây `current` là symbolic link. Chuỗi `/srv/app/allowed/current/token.txt` trông có vẻ nằm dưới root về **mặt từ vựng** (lexical), nhưng sau khi hệ thống file giải liên kết, nó nằm trong `/srv/app/private/`. `normalize()` không hề kiểm tra symlink. `toRealPath()` mặc định theo link để tìm đích thực.

Một trường hợp khó hơn:

```text
T1: ứng dụng kiểm tra allowed/reports/file.txt là an toàn
T2: kẻ tấn công đổi reports thành symlink đi ra ngoài
T3: ứng dụng mở allowed/reports/file.txt
```

Đây là **TOCTOU**: đường dẫn đã được xác thực ở thời điểm T1 có thể không còn trỏ tới cùng tài nguyên ở T3. Lặp lại `toRealPath()` ngay trước `Files.readString()` chỉ thu hẹp cửa sổ race, **không loại bỏ hoàn toàn**.

Các mức bảo vệ thực tế:

1. **Phân quyền hệ điều hành:** không để đối tượng gửi request có quyền thay thư mục cha, symlink, junction hoặc mount bên dưới vùng mà tiến trình tin cậy đọc. Đây thường là biện pháp thiết yếu.
2. **Tách storage theo user/tenant và quyền tác vụ:** phân phối allowed root phía server; user A không thể dùng tên file để đọc tenant B dù cả hai cùng dưới một root rộng.
3. **Tránh theo symlink nếu không cần:** có thể dùng `LinkOption.NOFOLLOW_LINKS` trong các API hỗ trợ (ví dụ `Files.isRegularFile(path, NOFOLLOW_LINKS)`, `Files.newByteChannel`); kiểm soát **từng thành phần thư mục**, không chỉ tên cuối. Lưu ý dùng `toRealPath(NOFOLLOW_LINKS)` để thay cho việc kiểm tra đích thực là sai nếu sau đó vẫn mở đường dẫn theo link.
4. **Mở tương đối với directory handle:** `SecureDirectoryStream` của Java NIO.2 hỗ trợ thao tác tương đối với directory stream đã mở, giảm race khi filesystem provider hỗ trợ. `Files.newDirectoryStream` **không bảo đảm** sẽ trả `SecureDirectoryStream` trên mọi hệ điều hành/filesystem; cần kiểm tra `instanceof`, chính sách fallback và thao tác từng phân đoạn có `NOFOLLOW_LINKS` khi cần.
5. **Cô lập ở tầng OS** cho yêu cầu nghiêm ngặt: container/sandbox, quyền account ít nhất, mount namespace/chroot phù hợp hoặc API hệ điều hành hỗ trợ mở theo file descriptor. Java `Path` tự nó không tạo một security boundary toàn diện trước một cây filesystem mà attacker có thể thay đổi liên tục.

Không dựa vào Java `SecurityManager` để xử lý bài toán này trong ứng dụng hiện đại. Điều cần bảo vệ là quyền truy cập tài nguyên và độ ổn định của các thành phần path khi thao tác IO.

### Hard link, mount và junction

`toRealPath()` giúp với symbolic link; nó không chứng minh nội dung bên trong file là “vô hại”. Hard link có thể tạo thêm tên tới cùng một inode; mount point hoặc Windows junction/reparse point còn tùy provider. Vì vậy chính sách bảo vệ phải gồm quyền tạo link/mount, ownership và phân quyền OS. Một path hợp lệ nằm dưới root vẫn có thể bị từ chối theo quyền nghiệp vụ.

## 7. URL encoding, Windows path và tên file từ upload

Lỗi traversal không chỉ nằm ở chuỗi `../` nhìn thấy trực tiếp.

- **URL decoding:** Những chuỗi có mã hóa percent phải được giải mã nhất quán ở tầng HTTP/router. Tránh việc một lớp kiểm tra chuỗi **chưa decode** nhưng lớp khác decode tiếp trước khi mở file. Không tùy tiện decode hai lần; đặt quy tắc xử lý ở đúng một ranh giới.
- **Windows:** Ngoài dấu `/` còn có `\`, drive letter, UNC path (ví dụ `\\server\share`) và dạng drive-relative (ví dụ `C:folder`). `Path.isAbsolute()` không đủ để biến mọi chuỗi khác thành tên file an toàn. Nếu API chỉ cần file identifier, tốt hơn hết chỉ chấp nhận một tập ký tự và cú pháp đơn giản, độc lập OS.
- **Linux/macOS:** Backslash thường là ký tự tên file, không nhất thiết là separator. Bộ lọc chỉ hiểu separator của một OS có thể hoạt động khác khi triển khai lên OS khác.
- **Tên file upload:** Không dùng nguyên `getOriginalFilename()` hoặc tham số `filename` làm đường dẫn lưu. Có thể chứa path từ phía client. Tên hiển thị phải tách khỏi key vật lý do server sinh; áp dụng giới hạn độ dài/ký tự, tránh tên đặc biệt và collision.
- **Case và Unicode:** Khả năng phân biệt chữ hoa/thường và chuẩn hóa Unicode tùy filesystem. Đừng dùng so sánh chuỗi tùy tiện để xác nhận root hoặc quyền user.
- **Ký tự điều khiển và path lạ:** `Path.of` có thể ném `InvalidPathException` tùy platform. Bắt và trả lỗi yêu cầu không hợp lệ; không để lộ đường dẫn hệ thống trong HTTP error.

Với endpoint nhận một **ID tài liệu**, thiết kế tốt hơn là `GET /documents/{id}` → tra cứu ownership trong DB → lấy storage key do server quản lý. API không cần cung cấp thao tác filesystem path trực tiếp cho client.

## 8. Zip Slip: traversal trong tên entry của file nén

Đường dẫn trong ZIP cũng do nguồn không tin cậy cung cấp. Với `ZipEntry.getName()`, tên như `../outside.txt` hoặc absolute path có thể thoát thư mục extract nếu code ghép thẳng vào destination. Mẫu kiểm tra **trước khi tạo thư mục hoặc ghi entry**:

```java
// Đoạn nằm trong vòng lặp đọc ZipEntry, không phải chương trình độc lập.
Path root = destinationDirectory.toRealPath();
Path entryPath = Path.of(entry.getName());

if (entryPath.isAbsolute()) {
    throw new SecurityException("Absolute ZIP entry");
}
for (Path part : entryPath) {
    if (part.toString().equals("..")) {
        throw new SecurityException("Parent traversal in ZIP");
    }
}
Path target = root.resolve(entryPath).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("ZIP entry outside destination");
}
```

Đây mới là **phần kiểm tra tên**. Bộ giải nén hoàn chỉnh còn phải từ chối entry rỗng/đáng ngờ, kiểm soát thư mục cha và symlink, tránh ghi đè bằng `CREATE_NEW` nếu thích hợp, giới hạn số lượng entry/tổng dung lượng đã giải nén (zip bomb) và xử lý dữ liệu stream an toàn. Nếu tự giải nén qua filesystem có thư mục mà attacker đồng thời sửa được, cần biện pháp race-resistant ở phần 6.

## 9. Kiểm thử bảo vệ ranh giới

Đừng chỉ kiểm thử `"file.txt"` hợp lệ. Tạo bộ case có kết quả mong đợi:

| Đầu vào hoặc tình huống | Kỳ vọng |
| --- | --- |
| `docs/report.txt` tồn tại trong allowed root | Đọc được nếu user có quyền nghiệp vụ |
| `../secret.txt` | Từ chối traversal |
| `docs/../../secret.txt` | Từ chối traversal |
| Absolute path trỏ vào allowed root | Từ chối nếu API chỉ nhận relative path |
| Absolute path trỏ ra ngoài | Từ chối |
| `files-backup/x.txt` là thư mục anh em với root `files` | Không chấp nhận bằng so sánh prefix chuỗi |
| Symlink dưới root trỏ ra ngoài | Từ chối dựa trên đích thực hoặc chính sách NOFOLLOW |
| File trong root nhưng thuộc tenant khác | Từ chối theo authorization, dù containment hợp lệ |
| File không tồn tại hoặc thiếu quyền đọc | Xử lý lỗi rõ ràng; không trả nội dung ngoài root |
| Đổi symlink/thư mục cha đồng thời trong lúc mở | Không cho phép attacker tác động cấu trúc trusted directory; hoặc dùng cơ chế mở race-resistant |
| ZIP entry chứa parent traversal/absolute path | Từ chối trước khi tạo file |

Nên chạy các test tương thích trên nền tảng thực tế dùng triển khai (Linux/Windows/container), vì cú pháp path và hỗ trợ symbolic link khác nhau. Với test có symlink, đừng âm thầm biến việc thiếu quyền tạo symlink thành “test bảo mật PASS”; hãy báo rõ test bị bỏ qua và kiểm chứng trong môi trường có hỗ trợ.

Các lỗi thường gặp đáng kiểm tra khi review code: `new File(root, userInput)` không có kiểm tra containment; chỉ `normalize()`; `String.startsWith(root)`; chỉ check basename ở UI; cho client chọn root; dùng `toRealPath(NOFOLLOW_LINKS)` nhưng sau đó mở file theo link; và kiểm tra trước khi tạo file nhưng bỏ qua parent symlink/race.

## 10. Quy tắc thiết kế khi đưa vào production

1. **Mô hình quyền trước:** Xác định dữ liệu user nào được xem, thư mục nào app có quyền, tác vụ nào (read/write/delete) được cấp. Chọn allowed root từ server, theo đúng tenant và quyền tài nguyên.
2. **Giảm quyền biểu đạt của đầu vào:** Ưu tiên opaque file ID hoặc một tên file đơn; dùng path lồng nhau chỉ khi bài toán thực sự cần. Từ chối absolute path, parent traversal và các dạng path mơ hồ.
3. **Kiểm tra cấu trúc và vị trí thực:** Dùng `Path.resolve/normalize/startsWith` và `toRealPath` với file đã tồn tại; đối với file mới, kiểm tra parent và tạo bằng `CREATE_NEW` nếu không ghi đè.
4. **Bảo vệ TOCTOU:** Cấm attacker đổi cấu trúc trusted directory, hoặc dùng mở tương đối qua directory handle/`SecureDirectoryStream` khi phù hợp. Kết hợp quyền OS tối thiểu.
5. **Kiểm tra dữ liệu và khả năng vận hành:** Giới hạn kích thước file, thời gian và tổng dung lượng, xử lý exceptions, không tiết lộ absolute server paths trong response/log công khai.
6. **Dùng fixture/tình huống tấn công khi kiểm thử:** Kết hợp path traversal, symlink, tenant boundary, file không tồn tại, upload, xóa/ghi đè và entry trong archive.

Điều kiện cần nhớ là **`normalize()` giải quyết cú pháp đường dẫn; `toRealPath()` giải quyết đích thực tại một thời điểm; authorization và các biện pháp chống race mới giúp duy trì ranh giới quyền thực tế**. Không một hàm xử lý chuỗi đơn lẻ nào bảo đảm an toàn cho mọi thao tác filesystem.

**Tài liệu tham khảo chính thức:** Java SE 17 API `java.nio.file.Path` (`resolve`, `normalize`, `startsWith`, `toRealPath`), `java.nio.file.Files`, `java.nio.file.SecureDirectoryStream`, `java.nio.file.LinkOption` và `java.nio.file.StandardOpenOption`.
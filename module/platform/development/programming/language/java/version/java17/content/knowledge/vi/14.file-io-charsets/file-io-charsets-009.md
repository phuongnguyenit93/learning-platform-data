# Đường dẫn, liên kết tượng trưng và kiểm tra quyền truy cập trong Java 17

Khi làm việc với tệp và thư mục, chỉ ghép một chuỗi như `"data/report.txt"` là chưa đủ để biết chương trình đang truy cập đối tượng nào hoặc có quyền thực hiện thao tác hay không. Một đường dẫn có thể là tương đối hoặc tuyệt đối; nó có thể chứa thành phần `.` và `..`; một thành phần có thể là **symbolic link** trỏ sang nơi khác; và quyền truy cập còn phụ thuộc hệ điều hành, tài khoản chạy chương trình, ACL, mount và trạng thái filesystem tại thời điểm thao tác.

Trong Java 17, API hiện đại để xử lý các vấn đề này nằm trong **Java NIO.2**, chủ yếu là:

- `Path`: biểu diễn đường dẫn theo filesystem/provider.
- `Path.of(...)` hoặc `Paths.get(...)`: tạo đối tượng đường dẫn.
- `Files`: kiểm tra, đọc thuộc tính, tạo, xóa và thao tác với tệp/thư mục.
- `LinkOption.NOFOLLOW_LINKS`: yêu cầu một số API không lần theo symbolic link.
- `BasicFileAttributes`, `PosixFileAttributes` và `AclFileAttributeView`: đọc thuộc tính và quyền theo khả năng của provider.

Bài này tập trung vào cách phân biệt đường dẫn với đối tượng filesystem, cách nhận biết và xử lý symbolic link, cũng như cách kiểm tra quyền truy cập mà không dựa vào giả định riêng của Windows hay Unix.

## 1. Path biểu diễn tên/vị trí, không phải bản thân tệp

`Path` là một đối tượng biểu diễn đường dẫn trong một filesystem. Nó không tự chứng minh tệp tồn tại, không tự mở tệp và cũng không lưu trạng thái quyền truy cập.

```java
import java.nio.file.Path;

Path relative = Path.of("data", "reports", "summary.txt");
Path absolute = Path.of("/var/app/data/reports/summary.txt");

System.out.println(relative);
System.out.println(absolute);
```

`Path.of(...)` có từ Java 11; Java 17 có thể sử dụng trực tiếp. `Paths.get(...)` vẫn tồn tại và cũng tạo `Path`, nhưng trong code mới có thể dùng `Path.of(...)` ngắn gọn hơn.

Một số điểm cần nhớ:

- `Path` có thể là đường dẫn tương đối hoặc tuyệt đối.
- Cách phân tách thành phần phụ thuộc filesystem/provider. Không nên tự ghép đường dẫn bằng dấu `/` hoặc `\` nếu muốn code đa nền tảng; dùng `Path.of("folder", "file.txt")` hoặc `resolve`.
- Một `Path` có thể chỉ tới tệp chưa tồn tại.
- Hai `Path` có thể biểu diễn cùng một vị trí về mặt filesystem dù chuỗi của chúng khác nhau.
- Đường dẫn có thể đi qua symbolic link, nên tên nhìn thấy trong `Path` chưa chắc là đường dẫn vật lý cuối cùng.

### 1.1. Tạo đường dẫn tương đối và tuyệt đối

```java
Path config = Path.of("config", "app.properties");

System.out.println(config.isAbsolute()); // false trên filesystem thông thường

Path absoluteConfig = config.toAbsolutePath();
System.out.println(absoluteConfig);
```

`toAbsolutePath()` chuyển đường dẫn tương đối thành đường dẫn tuyệt đối dựa trên thư mục làm việc mặc định của JVM. Nó **không yêu cầu tệp phải tồn tại** và không tự lần theo symbolic link để tạo đường dẫn thực.

Để biết thư mục làm việc hiện tại, có thể xem:

```java
System.out.println(System.getProperty("user.dir"));
```

Thư mục làm việc là thuộc tính của tiến trình, không phải luôn là thư mục chứa file `.java` hoặc file `.jar`.

### 1.2. Ghép đường dẫn bằng resolve

Không nên nối chuỗi thủ công:

```java
// Tránh tự xử lý dấu phân cách:
// String fileName = base + "/" + child;
```

Dùng `resolve`:

```java
Path base = Path.of("data", "exports");
Path file = base.resolve("orders.csv");

System.out.println(file);
```

`resolve` thêm đường dẫn con vào đường dẫn cơ sở theo quy tắc của `Path`. Nếu đối số truyền vào là một đường dẫn tuyệt đối, kết quả là đường dẫn tuyệt đối đó, không phải ghép vào `base`.

```java
Path base = Path.of("data", "exports");
Path child = Path.of("orders.csv");
Path result = base.resolve(child);
```

Để tạo đường dẫn ngang hàng, dùng `resolveSibling`:

```java
Path report = Path.of("data", "reports", "summary.txt");
Path backup = report.resolveSibling("summary.txt.bak");
```

### 1.3. normalize() chỉ chuẩn hóa cú pháp đường dẫn

Đường dẫn có thể chứa thành phần `.` hoặc `..`:

```java
Path path = Path.of("data", "reports", "..", "logs", ".", "app.log");
Path normalized = path.normalize();

System.out.println(normalized);
```

`normalize()` loại bỏ các thành phần dư thừa theo cú pháp đường dẫn, ví dụ `.` và một cặp tên thư mục theo sau bởi `..` khi có thể. Đây là phép biến đổi **trên đường dẫn**, không cần filesystem và không kiểm tra tệp có tồn tại.

Điều quan trọng: `normalize()` không tương đương với tìm đường dẫn thực. Nếu một thành phần là symbolic link, loại bỏ `..` theo cú pháp có thể cho kết quả khác với việc thực sự đi qua filesystem.

Ví dụ giả định:

```text
/work/link/../result.txt
```

Nếu `/work/link` là symbolic link trỏ đến `/outside/project`, việc truy cập theo filesystem có thể đi qua vị trí đích trước khi xử lý `..`. `normalize()` chỉ nhìn chuỗi thành phần và không biết link đó trỏ đi đâu. Khi cần xác định đường dẫn thực của một đối tượng đang tồn tại, xem `toRealPath()` ở phần sau.

## 2. toRealPath() và sự khác nhau với normalize()

`Path.toRealPath(...)` yêu cầu filesystem phân giải đường dẫn và trả về đường dẫn thực của đối tượng. Mặc định, phương thức lần theo symbolic link và yêu cầu đối tượng tồn tại.

```java
import java.io.IOException;
import java.nio.file.Path;

Path path = Path.of("data", "reports", "..", "reports", "summary.txt");

try {
    Path real = path.toRealPath();
    System.out.println(real);
} catch (IOException ex) {
    System.out.println("Không phân giải được đường dẫn: " + ex.getMessage());
}
```

Khác biệt:

| API | Có truy cập filesystem? | Cần đối tượng tồn tại? | Xử lý symbolic link |
| --- | --- | --- | --- |
| `normalize()` | Không | Không | Không lần theo link |
| `toAbsolutePath()` | Không cần đọc thuộc tính đối tượng | Không | Không tự lần theo link |
| `toRealPath()` | Có | Có, nếu không dùng tùy chọn đặc biệt | Mặc định lần theo link |
| `toRealPath(NOFOLLOW_LINKS)` | Có | Các thành phần đường dẫn được phân giải theo chế độ không lần theo link | Không lần theo symbolic link theo tùy chọn |

`toRealPath()` có thể làm rõ hai đường dẫn khác chuỗi nhưng cùng trỏ tới một vị trí thực. Tuy nhiên, nó có thể ném `IOException` nếu đường dẫn không tồn tại, không thể truy cập hoặc không phân giải được.

### 2.1. normalize() không kiểm tra an toàn đường dẫn

Một lỗi thường gặp trong ứng dụng nhận tên tệp từ người dùng là:

```java
Path target = uploadDirectory.resolve(userInput).normalize();
```

`normalize()` giúp loại bỏ các thành phần dư thừa, nhưng **không tự bảo đảm target nằm trong thư mục upload**. Ví dụ người dùng có thể nhập `../../outside.txt`; sau khi normalize, đường dẫn có thể thoát khỏi thư mục gốc.

Có thể kiểm tra quan hệ đường dẫn sau khi tạo đường dẫn tuyệt đối đã chuẩn hóa:

```java
Path root = uploadDirectory.toAbsolutePath().normalize();
Path target = root.resolve(userInput).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Đường dẫn nằm ngoài thư mục cho phép");
}
```

Kiểm tra này hữu ích cho việc ngăn đường dẫn thoát khỏi root ở mức cú pháp. Nhưng nếu thư mục chứa symbolic link hoặc môi trường có thể bị thay đổi đồng thời, vẫn cần thiết kế thao tác filesystem an toàn hơn; chỉ kiểm tra chuỗi đường dẫn không giải quyết mọi rủi ro link traversal hoặc race condition.

## 3. Symbolic link là gì?

**Symbolic link** (liên kết tượng trưng, thường gọi là symlink) là một filesystem object chứa đường dẫn tham chiếu tới một đối tượng khác. Khi chương trình truy cập link theo cách mặc định, filesystem thường lần theo link tới đích.

Sơ đồ:

```text
project/
├── data/
│   └── report.txt
└── latest.txt  ───────────────┐
                              │ symbolic link
                              └──> data/report.txt
```

Ở đây, `latest.txt` là một link; nội dung thực tế nằm tại `data/report.txt`.

Symbolic link có thể:

- Trỏ tới tệp hoặc thư mục.
- Trỏ bằng đường dẫn tương đối hoặc tuyệt đối.
- Trỏ tới một vị trí trên filesystem khác, tùy hệ điều hành và provider.
- Trỏ tới một đối tượng chưa tồn tại (dangling/broken link).
- Tạo vòng lặp link hoặc chuỗi link nhiều tầng.

Đừng nhầm symbolic link với **hard link**. Hard link là một tên directory entry khác cho cùng file object (theo ngữ nghĩa filesystem); symbolic link là một object riêng chứa đường dẫn đích. Java có API riêng cho hai loại.

## 4. Tạo và nhận biết symbolic link

### 4.1. Tạo symbolic link bằng Files.createSymbolicLink

API:

```java
Files.createSymbolicLink(link, target);
```

Trong đó:

- `link` là vị trí tạo tên symbolic link.
- `target` là đường dẫn mà link sẽ tham chiếu tới.

Ví dụ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path directory = Path.of("demo");
Path target = directory.resolve("original.txt");
Path link = directory.resolve("shortcut.txt");

Files.createDirectories(directory);
Files.writeString(target, "Nội dung gốc");

try {
    Files.createSymbolicLink(link, Path.of("original.txt"));
    System.out.println(Files.readString(link));
} catch (UnsupportedOperationException ex) {
    System.out.println("Filesystem/provider không hỗ trợ symbolic link");
} catch (IOException | SecurityException ex) {
    System.out.println("Không thể tạo symbolic link: " + ex.getMessage());
}
```

Đích `original.txt` là đường dẫn tương đối. Nó được diễn giải tương đối với thư mục chứa link `shortcut.txt`, không phải thư mục làm việc của JVM.

Quyền tạo symbolic link phụ thuộc nền tảng và cấu hình hệ thống. Trên một số môi trường Windows, việc tạo symlink có thể yêu cầu quyền phù hợp hoặc Developer Mode; trên Unix-like, quyền và chính sách filesystem cũng có thể ảnh hưởng. Vì vậy, code portable phải xử lý `IOException`, `SecurityException` và `UnsupportedOperationException` thay vì giả định mọi máy đều cho phép tạo link.

### 4.2. Kiểm tra một Path có phải symbolic link không

Dùng `Files.isSymbolicLink(path)`:

```java
if (Files.isSymbolicLink(link)) {
    System.out.println("Đây là symbolic link");
} else {
    System.out.println("Không phải symbolic link");
}
```

Phương thức kiểm tra chính đối tượng tại chính đường dẫn đó; nó không trả lời liệu đích của link có tồn tại hay không.

### 4.3. Đọc đường dẫn đích bằng readSymbolicLink

```java
Path target = Files.readSymbolicLink(link);
System.out.println(target);
```

`readSymbolicLink` trả về đường dẫn được lưu trong symbolic link. Nếu link lưu đích tương đối, kết quả cũng là `Path` tương đối. API này **không tự trả về đường dẫn thực cuối cùng**; muốn lần theo link đến đối tượng thực, dùng `toRealPath()` trên đường dẫn thích hợp.

Nếu `path` không phải symbolic link, `readSymbolicLink` ném `NotLinkException`. Nếu link không thể đọc hoặc filesystem gặp lỗi, có thể ném `IOException`.

## 5. Link hợp lệ, dangling link và NOFOLLOW_LINKS

Một symbolic link có thể tồn tại dù đích của nó đã bị xóa hoặc chưa từng được tạo. Trường hợp này gọi là **dangling symbolic link**.

Ví dụ:

```java
Path link = Path.of("demo", "missing-link");

Files.createSymbolicLink(link, Path.of("not-created.txt"));
```

Nếu tạo link thành công nhưng `not-created.txt` không tồn tại:

- `Files.isSymbolicLink(link)` trả `true`.
- `Files.exists(link)` mặc định lần theo link, nên thường trả `false` vì đích không tồn tại.
- `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` kiểm tra chính link và có thể trả `true`.

Ví dụ kiểm tra:

```java
boolean linkObjectExists =
        Files.exists(link, LinkOption.NOFOLLOW_LINKS);
boolean targetExists =
        Files.exists(link);

System.out.println("Link object: " + linkObjectExists);
System.out.println("Target: " + targetExists);
```

### 5.1. LinkOption.NOFOLLOW_LINKS dùng để làm gì?

`LinkOption.NOFOLLOW_LINKS` yêu cầu các API hỗ trợ tùy chọn này **không lần theo symbolic link cuối cùng** khi thực hiện thao tác. Nó hữu ích khi cần kiểm tra hoặc đọc thuộc tính của link object thay vì đối tượng đích.

Một số API nhận tùy chọn này:

- `Files.exists(path, NOFOLLOW_LINKS)`
- `Files.notExists(path, NOFOLLOW_LINKS)`
- `Files.isDirectory(path, NOFOLLOW_LINKS)`
- `Files.isRegularFile(path, NOFOLLOW_LINKS)`
- `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)`
- `Path.toRealPath(NOFOLLOW_LINKS)`
- Một số thao tác mở file nhận `LinkOption.NOFOLLOW_LINKS` như một `OpenOption`, nếu provider hỗ trợ.

Ví dụ đọc thuộc tính của chính link:

```java
import java.nio.file.LinkOption;
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attributes = Files.readAttributes(
        link,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);

System.out.println(attributes.isSymbolicLink());
System.out.println(attributes.isRegularFile());
```

Nếu đường dẫn là symbolic link, `isSymbolicLink()` cho biết điều đó. Với tùy chọn không lần theo link, `isRegularFile()` là `false` cho chính link object, dù đích link có thể là một regular file.

**Lưu ý:** `NOFOLLOW_LINKS` không phải công tắc áp dụng cho mọi API `Files`. Chỉ truyền nó cho những phương thức có hỗ trợ theo chữ ký API; không tự giả định mọi thao tác sẽ bỏ qua link.

### 5.2. exists và notExists có thể cùng trả false

`Files.exists(...)` và `Files.notExists(...)` không phải hai hàm luôn đối lập tuyệt đối. Nếu Java không xác định được trạng thái vì thiếu quyền hoặc lỗi truy cập filesystem, cả hai có thể trả `false`.

Do đó:

```java
if (!Files.exists(path)) {
    // Không thể kết luận chắc chắn rằng path không tồn tại.
}
```

Nếu cần biết trạng thái chính xác, phải xử lý kết quả theo ngữ cảnh và thực hiện thao tác cần thiết với ngoại lệ phù hợp. API kiểm tra tồn tại chỉ là thông tin tại thời điểm gọi.

## 6. Lần theo đích và kiểm tra symbolic link an toàn

### 6.1. toRealPath() mặc định lần theo link

Giả sử `shortcut.txt` trỏ tới `original.txt`:

```java
Path realTarget = shortcut.toRealPath();
System.out.println(realTarget);
```

Nếu đích tồn tại và có thể truy cập, kết quả là đường dẫn thực sau khi phân giải link. Điều này hữu ích để:

- So sánh đường dẫn thực của hai tên file.
- Hiển thị vị trí cuối cùng mà link dẫn tới.
- Ghi log đường dẫn đã được filesystem phân giải.
- Xác định đích tồn tại của một symlink.

Nếu link bị hỏng hoặc đích không thể phân giải, `toRealPath()` có thể ném `IOException`.

### 6.2. toRealPath(NOFOLLOW_LINKS) không lần theo symbolic link

Khi muốn giữ link như một thành phần của đường dẫn, có thể gọi:

```java
Path pathWithoutFollowingLinks =
        shortcut.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

Tùy chọn này thay đổi cách phân giải symbolic link; không nên hiểu rằng phương thức chỉ đơn giản trả lại nguyên chuỗi đầu vào. Nó vẫn là thao tác filesystem và vẫn có thể thất bại nếu các thành phần cần thiết không thể phân giải.

### 6.3. Xóa link hay xóa đích?

`Files.delete(link)` xóa chính symbolic link, không xóa đối tượng mà nó trỏ tới:

```java
Files.delete(link);
```

Đây là hành vi quan trọng khi dọn dẹp. Nếu muốn xóa đích, phải xác định và thao tác riêng trên đường dẫn đích; không nên vô tình xóa dữ liệu thật chỉ vì đang dọn một shortcut.

Nếu `link` là dangling link, `Files.delete(link)` vẫn có thể xóa link object vì chính link tồn tại dù đích không có.

## 7. Kiểm tra quyền truy cập bằng Files

Java cung cấp một số phép kiểm tra quyền phổ biến:

```java
Files.isReadable(path);
Files.isWritable(path);
Files.isExecutable(path);
```

Các phương thức này trả về `boolean`, hữu ích để hiển thị trạng thái hoặc quyết định trải nghiệm giao diện:

```java
if (Files.isReadable(path)) {
    System.out.println("Có thể đọc theo kiểm tra hiện tại");
}

if (Files.isWritable(path)) {
    System.out.println("Có thể ghi theo kiểm tra hiện tại");
}

if (Files.isExecutable(path)) {
    System.out.println("Có thể thực thi theo kiểm tra hiện tại");
}
```

Chúng thường lần theo symbolic link theo mặc định và kiểm tra quyền của đối tượng đích.

### 7.1. isReadable, isWritable, isExecutable không ném IOException

Khác với nhiều thao tác đọc/ghi thật, các phương thức này trả `false` nếu không thể xác định hoặc không có quyền tương ứng. Ví dụ:

- Đường dẫn không tồn tại.
- Tiến trình hiện tại không có quyền truy cập.
- Provider không thể xác định quyền.
- File system hoặc thiết bị gặp vấn đề.

Không nên xem `false` là một thông báo nguyên nhân duy nhất; muốn biết lý do chi tiết, thực hiện thao tác thật và xử lý ngoại lệ.

### 7.2. Kiểm tra quyền không bảo đảm thao tác kế tiếp thành công

Đây là điểm rất quan trọng:

```java
if (Files.isWritable(path)) {
    Files.writeString(path, "Updated");
}
```

Giữa lúc `isWritable` trả `true` và lúc `writeString` thực thi, quyền có thể thay đổi, file có thể bị xóa, thay thế, filesystem có thể chuyển trạng thái hoặc symbolic link có thể bị thay đích.

Hiện tượng này thuộc nhóm **time-of-check to time-of-use (TOCTOU)**: kiểm tra và sử dụng diễn ra ở hai thời điểm khác nhau.

Vì vậy, cách chắc chắn hơn là thực hiện thao tác cần thiết và xử lý kết quả:

```java
try {
    Files.writeString(path, "Updated");
    System.out.println("Ghi thành công");
} catch (IOException ex) {
    System.out.println("Không thể ghi file: " + ex.getMessage());
}
```

`isWritable()` có thể dùng để thông báo sớm cho người dùng, nhưng `writeString()` mới là kết quả thực tế của thao tác ghi.

## 8. Đọc quyền POSIX khi filesystem hỗ trợ

Trên hệ thống hỗ trợ POSIX, Java cung cấp `PosixFilePermissions` và `PosixFileAttributeView`. Quyền POSIX cơ bản gồm ba nhóm:

- **Owner:** chủ sở hữu.
- **Group:** nhóm.
- **Others:** những người dùng còn lại.

Mỗi nhóm có ba quyền:

- `READ`: đọc.
- `WRITE`: ghi.
- `EXECUTE`: thực thi (với thư mục thường mang nghĩa tìm kiếm/traverse).

Ví dụ đọc quyền:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

Path file = Path.of("data", "report.txt");

try {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(file);

    System.out.println(permissions);
} catch (UnsupportedOperationException ex) {
    System.out.println("Filesystem không hỗ trợ POSIX permissions");
} catch (IOException ex) {
    System.out.println("Không đọc được quyền: " + ex.getMessage());
}
```

`Files.getPosixFilePermissions(path)` đọc quyền POSIX của đối tượng; mặc định các API thuộc nhóm này lần theo symbolic link. Có overload nhận `LinkOption...` để yêu cầu không theo link nếu provider hỗ trợ.

### 8.1. Hiển thị dạng rwxr-x---

Có thể dùng `PosixFilePermissions.toString(...)`:

```java
String mode = PosixFilePermissions.toString(permissions);
System.out.println(mode);
```

Ví dụ `rw-r-----` diễn tả:

- Owner: đọc và ghi.
- Group: chỉ đọc.
- Others: không có quyền.

Đây là cách biểu diễn POSIX phổ biến, không phải định dạng quyền tổng quát của mọi filesystem.

### 8.2. Đặt quyền POSIX

```java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-r-----");
Files.setPosixFilePermissions(file, permissions);
```

Thao tác này có thể ném `IOException`, `UnsupportedOperationException` hoặc `SecurityException` tùy môi trường và quyền của tiến trình.

Không nên gọi `setPosixFilePermissions` mà không xác định filesystem có hỗ trợ POSIX hay không. Windows thường dùng ACL thay vì mô hình POSIX truyền thống; provider có thể không hỗ trợ API POSIX.

## 9. Quyền truy cập và ACL trên Windows hoặc filesystem khác

Không phải mọi filesystem đều có mô hình quyền POSIX. Một số môi trường dùng **Access Control List (ACL)**, trong đó quyền được gán cho user hoặc group cụ thể bằng các ACL entry.

Java NIO cung cấp:

- `AclFileAttributeView`
- `AclEntry`
- `AclEntryPermission`
- `AclEntryType`
- `UserPrincipal`
- `UserPrincipalLookupService`

Có thể kiểm tra provider có hỗ trợ ACL view:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path,
        AclFileAttributeView.class
);

if (aclView == null) {
    System.out.println("Provider không hỗ trợ ACL view");
} else {
    List<AclEntry> entries = aclView.getAcl();
    entries.forEach(System.out::println);
}
```

Để dùng ví dụ trên cần import:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclFileAttributeView;
import java.util.List;
```

`getFileAttributeView` có thể trả `null` nếu provider không hỗ trợ view được yêu cầu. Khi đọc ACL, thao tác có thể ném `IOException` hoặc `SecurityException`.

### 9.1. Vì sao không nên tự suy ra quyền từ chuỗi rwx trên mọi hệ điều hành?

POSIX permission và Windows ACL không tương đương một-một:

- POSIX thường mô tả quyền owner/group/others.
- ACL có thể có nhiều entry cho từng user/group và quyền chi tiết hơn.
- Quyền thực tế còn chịu ảnh hưởng bởi quyền kế thừa, nhóm, chính sách hệ thống, mount và tài khoản tiến trình.

Nếu ứng dụng cần biết có thể thực hiện thao tác hay không, `Files.isReadable`, `isWritable`, `isExecutable` hoặc chính thao tác đọc/ghi là lựa chọn gần với nhu cầu hơn. Nếu ứng dụng quản trị quyền chi tiết, hãy dùng attribute view phù hợp với filesystem và xử lý trường hợp không hỗ trợ.

## 10. Kiểm tra loại đối tượng: file, directory và symbolic link

Các phương thức sau thường lần theo symbolic link theo mặc định:

```java
Files.isRegularFile(path);
Files.isDirectory(path);
Files.isSymbolicLink(path);
```

Ví dụ:

```java
if (Files.isRegularFile(path)) {
    System.out.println("Đường dẫn dẫn tới regular file");
} else if (Files.isDirectory(path)) {
    System.out.println("Đường dẫn dẫn tới directory");
} else if (Files.isSymbolicLink(path)) {
    System.out.println("Đường dẫn là symbolic link");
} else {
    System.out.println("Loại khác hoặc không xác định");
}
```

Thứ tự ở ví dụ trên có chủ ý: `isRegularFile` và `isDirectory` mặc định theo link; nếu link trỏ tới file, nhánh đầu có thể đúng và chương trình không đi tới nhánh `isSymbolicLink`. Nếu mục tiêu là nhận biết link object, hãy gọi `Files.isSymbolicLink(path)` riêng hoặc dùng API thuộc tính với `NOFOLLOW_LINKS`.

```java
boolean isLink = Files.isSymbolicLink(path);
boolean targetIsFile = Files.isRegularFile(path);
boolean linkItselfIsFile = Files.isRegularFile(
        path, LinkOption.NOFOLLOW_LINKS
);
```

Tên biến giúp thể hiện rõ đang hỏi về link hay đối tượng đích. `isRegularFile(path, NOFOLLOW_LINKS)` không coi symbolic link là regular file chỉ vì đích của nó là regular file.

## 11. Đọc thuộc tính bằng BasicFileAttributes

Khi cần nhiều thông tin cùng lúc, `Files.readAttributes(...)` có thể đọc một nhóm thuộc tính:

```java
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class
);

System.out.println("Directory: " + attrs.isDirectory());
System.out.println("Regular file: " + attrs.isRegularFile());
System.out.println("Symbolic link: " + attrs.isSymbolicLink());
System.out.println("Size: " + attrs.size());
System.out.println("Modified: " + attrs.lastModifiedTime());
```

Mặc định, API lần theo symbolic link. Để đọc thuộc tính của link object:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);
```

`BasicFileAttributes` có thể cho biết:

- Đối tượng là directory, regular file, symbolic link hay loại khác.
- Kích thước theo byte.
- Thời điểm tạo, truy cập gần nhất và sửa đổi gần nhất (nếu provider cung cấp).
- File key, nếu provider hỗ trợ định danh filesystem object.

Đọc thuộc tính vẫn có thể thất bại do `IOException`, `SecurityException` hoặc đối tượng thay đổi trong lúc thao tác. Không dùng một lần đọc thuộc tính như bằng chứng rằng trạng thái sẽ không thay đổi ở bước kế tiếp.

## 12. Ví dụ tổng hợp: kiểm tra link và quyền trước khi đọc

Ví dụ sau nhận một đường dẫn, báo nếu chính đường dẫn là symbolic link, kiểm tra trạng thái đích, hiển thị quyền đọc/ghi/thực thi và thử đọc nội dung:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class PathAccessDemo {
    public static void main(String[] args) {
        Path path = Path.of(args.length == 0 ? "data/report.txt" : args[0]);

        System.out.println("Path: " + path.toAbsolutePath());
        System.out.println("Is symbolic link: " + Files.isSymbolicLink(path));
        System.out.println("Exists (follow link): " + Files.exists(path));
        System.out.println("Link object exists: "
                + Files.exists(path, LinkOption.NOFOLLOW_LINKS));

        System.out.println("Readable: " + Files.isReadable(path));
        System.out.println("Writable: " + Files.isWritable(path));
        System.out.println("Executable: " + Files.isExecutable(path));

        try {
            System.out.println("Real path: " + path.toRealPath());
            System.out.println("Content:");
            System.out.println(Files.readString(path));
        } catch (IOException ex) {
            System.out.println("Không thể phân giải hoặc đọc file: "
                    + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac --release 17 PathAccessDemo.java
java PathAccessDemo data/report.txt
```

Đây là ví dụ quan sát và chẩn đoán. Trong ứng dụng thật, nếu mục tiêu là đọc dữ liệu thì hãy thực hiện `Files.readString` hoặc mở stream và xử lý `IOException`; những phép kiểm tra quyền ở trước chỉ cung cấp thông tin bổ sung.

## 13. Tạo và kiểm tra đường dẫn trong thư mục cho phép

Khi ứng dụng nhận tên tệp từ người dùng, ví dụ tên file upload hoặc tên báo cáo, cần ngăn việc nhập `..` để thoát khỏi thư mục gốc.

Một bước kiểm tra cú pháp:

```java
static Path resolveInside(Path root, String userFileName) {
    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(userFileName).normalize();

    if (!candidate.startsWith(normalizedRoot)) {
        throw new SecurityException("Đường dẫn vượt ra ngoài thư mục gốc");
    }
    return candidate;
}
```

Ví dụ:

```java
Path root = Path.of("uploads");

Path safe = resolveInside(root, "2026/report.pdf");
Path rejected = resolveInside(root, "../../private/secret.txt");
```

`startsWith(Path)` so sánh theo thành phần đường dẫn, phù hợp hơn so sánh chuỗi kiểu `candidate.toString().startsWith(root.toString())`. So sánh chuỗi có thể sai khi tên thư mục chỉ có chung tiền tố, ví dụ `uploads-old` bắt đầu bằng chuỗi `uploads` nhưng không phải thư mục con của `uploads`.

### 13.1. Giới hạn của kiểm tra startsWith

Kiểm tra trên chỉ ngăn một số đường dẫn thoát root ở mức cú pháp. Nó không đủ nếu kẻ tấn công có thể tạo hoặc thay symbolic link trong thư mục upload.

Ví dụ:

```text
uploads/
└── public-link -> /private
```

Tên đầu vào `public-link/secret.txt` không chứa `..`, và đường dẫn chuẩn hóa vẫn bắt đầu bằng `uploads`. Nhưng khi filesystem lần theo link, đường dẫn thực có thể đi tới `/private/secret.txt`.

Trong môi trường có nguy cơ bị thay đổi đồng thời, cần cân nhắc:

- Kiểm tra đường dẫn thực sau khi tạo hoặc xác nhận các thư mục cần thiết.
- Không cho phép người dùng không tin cậy tạo symbolic link trong vùng lưu trữ.
- Mở file với tùy chọn không theo symbolic link nếu API/provider hỗ trợ và yêu cầu nghiệp vụ phù hợp.
- Dùng `SecureDirectoryStream` khi provider hỗ trợ và cần thao tác tương đối an toàn bên trong một directory đã mở.
- Giữ quyền thư mục gốc và thư mục cha trong tay tài khoản tin cậy.

Không có một phép `normalize()` hoặc `startsWith()` đơn lẻ nào giải quyết hoàn toàn mọi race condition liên quan filesystem.

## 14. SecureDirectoryStream và thao tác tương đối an toàn

`SecureDirectoryStream` cung cấp các thao tác trên directory theo cách giúp giảm rủi ro khi đường dẫn bị thay đổi đồng thời trong một số filesystem/provider. Nó không được hỗ trợ ở mọi provider.

Có thể kiểm tra qua `DirectoryStream`:

```java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<Path> secure) {
        // Provider hỗ trợ các thao tác tương đối với directory đã mở.
    } else {
        // Provider không cung cấp SecureDirectoryStream.
    }
}
```

Khi có hỗ trợ, API này có các thao tác như `newByteChannel`, `newDirectoryStream`, `deleteFile`, `deleteDirectory` và `move` tương đối với directory đang mở. Tùy chọn `NOFOLLOW_LINKS` có thể dùng ở những API tương ứng để không theo link cuối.

Đây là công cụ chuyên biệt cho ứng dụng cần thao tác filesystem an toàn trong môi trường nhiều tiến trình hoặc dữ liệu không tin cậy. Với ứng dụng thông thường, dùng `Path`, `Files` và xử lý ngoại lệ đúng đã đáp ứng phần lớn nhu cầu. Không giả định mọi hệ điều hành đều cung cấp `SecureDirectoryStream`; luôn có nhánh xử lý khi provider không hỗ trợ.

## 15. Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Files.exists(link)` trả `false` dù link object có trên đĩa. | API mặc định lần theo link và đích không tồn tại. | Kiểm tra `Files.exists(link, NOFOLLOW_LINKS)` và `Files.isSymbolicLink(link)`. |
| `toRealPath()` ném `IOException`. | Tệp không tồn tại, link hỏng, không có quyền hoặc filesystem lỗi. | Kiểm tra nguyên nhân và xử lý ngoại lệ; không dùng `normalize()` thay thế nếu cần đường dẫn thực. |
| `normalize()` cho đường dẫn nằm trong root nhưng thao tác đi ra ngoài. | Một thành phần trung gian là symbolic link. | Kiểm tra link, kiểm soát thư mục gốc và dùng chiến lược mở file an toàn hơn. |
| `isWritable()` trả `true` nhưng ghi file vẫn thất bại. | Quyền hoặc trạng thái file thay đổi sau lần kiểm tra; thao tác thực có thể bị từ chối. | Thực hiện ghi và xử lý `IOException`. |
| `getPosixFilePermissions()` ném `UnsupportedOperationException`. | Provider không hỗ trợ POSIX permission view. | Kiểm tra ACL hoặc dùng các phép kiểm tra quyền tổng quát; xử lý khác biệt nền tảng. |
| `readSymbolicLink()` ném `NotLinkException`. | Path không phải symbolic link. | Kiểm tra `Files.isSymbolicLink` hoặc xử lý ngoại lệ. |
| Tạo symbolic link thất bại trên máy khác. | Hệ điều hành, filesystem hoặc chính sách quyền khác nhau. | Xử lý `IOException`, `SecurityException`, `UnsupportedOperationException`; không giả định môi trường. |
| So sánh chuỗi đường dẫn cho kết quả sai. | Dấu phân cách, chữ hoa/thường, `..`, symlink hoặc provider khác nhau. | Dùng API `Path` và `Files.isSameFile` khi cả hai đối tượng tồn tại và cần so sánh cùng file. |
| Cho rằng `Files.notExists(path)` luôn là phủ định của `exists`. | Provider có thể không xác định được trạng thái. | Xử lý trường hợp cả hai trả `false`; thực hiện thao tác cần thiết và bắt ngoại lệ. |

## 16. Bài tập thực hành

### Bài 1 — Phân biệt normalize và toRealPath

Tạo đường dẫn có thành phần `.` và `..`. In kết quả `normalize()` và `toRealPath()`. Giải thích phép nào chỉ xử lý cú pháp và phép nào cần filesystem.

### Bài 2 — Tạo symbolic link

Tạo file `original.txt`, tạo symbolic link `shortcut.txt` trỏ tới nó, rồi đọc nội dung qua link. Thử xóa file gốc và quan sát:

- `Files.isSymbolicLink(shortcut)`.
- `Files.exists(shortcut)`.
- `Files.exists(shortcut, NOFOLLOW_LINKS)`.

### Bài 3 — Kiểm tra quyền

Viết chương trình nhận một `Path`, in `isReadable`, `isWritable`, `isExecutable`. Thực hiện thao tác đọc hoặc ghi thật trong khối `try/catch` và giải thích vì sao kết quả kiểm tra không bảo đảm thao tác sau đó thành công.

### Bài 4 — POSIX và ACL

Thử đọc `PosixFilePermissions` trên filesystem hiện tại. Nếu không hỗ trợ, kiểm tra `AclFileAttributeView` và giải thích vì sao hai mô hình quyền không thể thay thế nhau hoàn toàn.

### Bài 5 — Ngăn path traversal

Viết hàm chỉ chấp nhận tên tệp nằm trong thư mục `uploads`. Thử đầu vào `report.pdf`, `2026/report.pdf`, `../secret.txt` và `sub/../../secret.txt`. Sau đó giải thích vì sao symbolic link bên trong thư mục vẫn có thể khiến kiểm tra cú pháp chưa đủ.

### Bài 6 — Dangling symbolic link

Tạo symbolic link trỏ tới một file không tồn tại. Dùng `readAttributes(..., NOFOLLOW_LINKS)` để xác nhận link object vẫn tồn tại và có loại symbolic link. Thử `toRealPath()` rồi giải thích ngoại lệ.

## 17. Tài liệu Java 17 chính thức

- [Java SE 17 API — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): biểu diễn, ghép, chuẩn hóa và phân giải đường dẫn.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): kiểm tra tồn tại/quyền, đọc thuộc tính, tạo link, xóa và thao tác tệp.
- [Java SE 17 API — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): các tùy chọn xử lý symbolic link.
- [Java SE 17 API — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): thuộc tính cơ bản và nhận biết symbolic link.
- [Java SE 17 API — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): chuyển đổi và hiển thị quyền POSIX.
- [Java SE 17 API — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): truy cập danh sách quyền ACL khi provider hỗ trợ.
- [Java SE 17 API — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác filesystem tương đối với directory đã mở.

Khi xử lý tệp trong Java 17, hãy tách rõ **đường dẫn được viết ra**, **đối tượng mà filesystem thực sự phân giải**, và **quyền mà tiến trình có tại thời điểm thao tác**. `normalize()` xử lý cấu trúc đường dẫn; `toRealPath()` phân giải đường dẫn qua filesystem; `NOFOLLOW_LINKS` giúp làm việc với chính link object; còn `isReadable`/`isWritable` chỉ là phép kiểm tra tức thời. Khi cần đọc, ghi, tạo hoặc xóa tệp, thao tác thực tế và xử lý ngoại lệ vẫn là bước quyết định.

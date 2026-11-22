# Kiểm tra symbolic link, quyền truy cập và hành vi theo nền tảng trong Java NIO.2

## 1. Mục tiêu bài học

Một đoạn mã I/O chạy đúng trên Linux có thể gặp lỗi trên Windows, macOS, filesystem mạng, ổ USB hoặc filesystem ảo. Các nguyên nhân thường liên quan đến **symbolic link (liên kết tượng trưng)**, **quyền của tệp**, **file attribute view**, chính sách của provider và những thay đổi xảy ra giữa lúc kiểm tra với lúc sử dụng đường dẫn.

Ví dụ, đoạn mã sau không phải một phép bảo đảm an toàn:

```java
if (Files.exists(path) && Files.isReadable(path)) {
    // Không bảo đảm thao tác đọc sau đó sẽ thành công.
    String content = Files.readString(path);
}
```

Đây là snippet, chưa phải chương trình độc lập. Sau phép kiểm tra, file có thể bị xóa, thay quyền, đổi tên, thay bằng symbolic link hoặc khóa bởi cơ chế khác; `readString` vẫn có thể ném `IOException`.

Sau bài này, bạn có thể:

1. Kiểm tra một `Path` có phải symbolic link không, đọc link target và phân biệt **follow** với **`NOFOLLOW_LINKS`**.
2. Giải thích vì sao một link bị đứt có thể cho `Files.exists(path) == false` nhưng `Files.exists(path, NOFOLLOW_LINKS) == true`.
3. Xem basic attributes và phát hiện khả năng hỗ trợ **POSIX permissions**, **DOS attributes** hoặc **ACL** mà không giả định mọi platform đều có.
4. Phân biệt `Files.isReadable/isWritable/isExecutable` với phép kiểm tra quyền truy cập có thể tin cậy; hiểu các race kiểu **TOCTOU**.
5. Viết ví dụ Java 17+ và test có kết quả **phụ thuộc nền tảng được nhận diện rõ ràng**, thay vì dùng kết quả Linux làm chuẩn cho mọi hệ điều hành.
6. Xử lý unsupported operation, thiếu quyền, symbolic-link loop, đường dẫn tạm và cleanup an toàn.

Trong nhóm **Kiểm thử và chẩn đoán**, trọng tâm là biết **quan sát, kiểm chứng và đưa ra kết luận đúng phạm vi**, không phải cố vượt qua phân quyền hệ điều hành.

## 2. Symbolic link là gì?

Symbolic link (*symlink*) là một filesystem entry chứa tham chiếu tới một đường dẫn target. Nó **không phải** bản sao nội dung file đích và cũng không giống **hard link**.

```text
work/
  actual.txt       nội dung: "HELLO"
  shortcut.txt -->  actual.txt      (symbolic link tương đối)
```

Khi chương trình truy cập `shortcut.txt`, nhiều thao tác `Files` mặc định **đi theo symlink** tới `actual.txt`; một số thao tác được thiết kế để quan sát chính đối tượng link.

Cần phân biệt:

- **Link path**: đường dẫn nơi symbolic link được lưu, ví dụ `work/shortcut.txt`.
- **Link target**: giá trị target bên trong link, ví dụ `actual.txt` hoặc một đường dẫn tuyệt đối.
- **Resolved target**: đường dẫn nhận được khi hệ thống giải quyết target tương đối với **thư mục chứa link**, không phải mặc định theo thư mục làm việc của Java process.
- **Dangling/broken link**: link vẫn tồn tại nhưng target không tồn tại hoặc không thể được giải quyết.
- **Link cycle**: chuỗi link hoặc liên kết tới thư mục tạo vòng lặp khi theo dõi.

Ví dụ: `Files.readSymbolicLink(link)` trả target được lưu trong link và **không bắt buộc trả đường dẫn tuyệt đối**. Nếu target là relative, ngữ cảnh giải quyết chính là thư mục chứa link.

## 3. Những phương thức và tùy chọn quan trọng

| API | Công dụng | Lưu ý |
| --- | --- | --- |
| `Files.isSymbolicLink(path)` | Hỏi entry có phải symbolic link không | Nếu không thể xác định, có thể trả false |
| `Files.createSymbolicLink(link, target)` | Tạo symlink; operation tùy khả năng provider/OS | Có thể không hỗ trợ hoặc thiếu quyền |
| `Files.readSymbolicLink(link)` | Đọc target được lưu trong link | Target có thể là relative hoặc chưa tồn tại |
| `Files.exists(path)` | Kiểm tra path tồn tại theo quy tắc follow mặc định | Trả false khi không xác định được hoặc link target mất |
| `Files.exists(path, NOFOLLOW_LINKS)` | Kiểm tra chính entry link mà không theo target | Có thể true dù target mất |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | Kiểm tra loại của chính entry | Symlink không được xem như regular file |
| `Files.readAttributes(path, BasicFileAttributes.class, options)` | Đọc loại, size, thời gian, file key | Có thể ném `IOException`; dùng để phân biệt lỗi |
| `Path.toRealPath(options)` | Trả đường dẫn thực theo contract provider | Không phải một biện pháp authorization độc lập |
| `Files.isSameFile(a, b)` | Kiểm tra cùng file khi có thể | Có thể truy cập filesystem và ném `IOException` |
| `Files.delete(link)` | Xóa directory entry chỉ định | Xóa symlink không tự xóa target |
| `Files.walkFileTree(...)` | Duyệt cây thư mục | Mặc định không đi theo symlink; `FOLLOW_LINKS` có tác động riêng |

Import thường dùng:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
```

Đây là tập import phục vụ các snippet trong bài. Khi cần bắt lỗi, dùng `IOException` và các subclass hoặc `UnsupportedOperationException` theo đặc điểm API.

## 4. `NOFOLLOW_LINKS` có nghĩa chính xác gì?

`LinkOption.NOFOLLOW_LINKS` điều khiển việc đi theo symbolic link cho **những API có tham số `LinkOption...` hoặc nhận option này theo hợp đồng**.

Giả sử:

```text
dir/
  item.txt
  link.txt -> item.txt
  broken.txt -> missing.txt
```

Trên hệ thống hỗ trợ symlink và còn nguyên trạng thái:

| Phép kiểm tra | `item.txt` | `link.txt` | `broken.txt` |
| --- | --- | --- | --- |
| `Files.exists(path)` | true | true | false |
| `Files.exists(path, NOFOLLOW_LINKS)` | true | true | true |
| `Files.isSymbolicLink(path)` | false | true | true |
| `Files.isRegularFile(path)` | true | true | false |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | true | false | false |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()` | false | true | true |

Bảng nêu **tình huống file local bình thường, có quyền và provider phân loại đúng**, không hứa rằng `Files.exists` luôn trả true/false như trên khi có I/O lỗi hoặc điều kiện truy cập không đủ.

**Hai cảnh báo:**

1. Không phải phương thức nào của `Files` cũng nhận hoặc tuân theo `NOFOLLOW_LINKS` theo cùng cách; đọc Javadoc của phương thức cụ thể.
2. `NOFOLLOW_LINKS` thường kiểm soát việc đi theo **symbolic link cuối cùng** cho API được gọi; nó **không tự động bảo đảm mọi thành phần thư mục cha không có symlink hoặc không bị đổi trong lúc thao tác**.

Nếu một yêu cầu bảo mật là “không được vượt ra khỏi thư mục gốc kể cả khi có symlink trong path”, chỉ kiểm tra `normalize()` hoặc `exists(..., NOFOLLOW_LINKS)` là chưa đủ.

## 5. Ví dụ Java 17+ hoàn chỉnh: symlink hợp lệ và link bị đứt

Tạo **`SymbolicLinkInspectionDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymbolicLinkInspectionDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-symlink-");
        Path actual = dir.resolve("actual.txt");
        Path link = dir.resolve("shortcut.txt");
        Path broken = dir.resolve("broken.txt");

        try {
            Files.writeString(actual, "HELLO");

            boolean linksAvailable;
            try {
                Files.createSymbolicLink(link, Path.of("actual.txt"));
                Files.createSymbolicLink(broken, Path.of("missing.txt"));
                linksAvailable = true;
            } catch (UnsupportedOperationException
                     | IOException | SecurityException ex) {
                linksAvailable = false;
            }

            System.out.println("symbolicLinksAvailable=" + linksAvailable);

            if (linksAvailable) {
                System.out.println("linkIsSymbolic="
                        + Files.isSymbolicLink(link));
                System.out.println("linkTargetIsRelative="
                        + !Files.readSymbolicLink(link).isAbsolute());
                System.out.println("regularWhenFollowed="
                        + Files.isRegularFile(link));
                System.out.println("regularWhenNotFollowed="
                        + Files.isRegularFile(
                                link, LinkOption.NOFOLLOW_LINKS));

                BasicFileAttributes attrs = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);
                System.out.println("attributesSaySymbolic="
                        + attrs.isSymbolicLink());

                System.out.println("brokenExistsFollow="
                        + Files.exists(broken));
                System.out.println("brokenExistsNoFollow="
                        + Files.exists(broken, LinkOption.NOFOLLOW_LINKS));
                System.out.println("sameAsActual="
                        + Files.isSameFile(link, actual));

                Files.delete(link); // xóa link, không xóa actual
                System.out.println("targetSurvivedDelete="
                        + Files.exists(actual));
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(broken);
            Files.deleteIfExists(actual);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SymbolicLinkInspectionDemo.java
java SymbolicLinkInspectionDemo
```

**Stdout khi nền tảng hỗ trợ tạo symlink và các phép I/O thành công:**

```text
symbolicLinksAvailable=true
linkIsSymbolic=true
linkTargetIsRelative=true
regularWhenFollowed=true
regularWhenNotFollowed=false
attributesSaySymbolic=true
brokenExistsFollow=false
brokenExistsNoFollow=true
sameAsActual=true
targetSurvivedDelete=true
```

Nếu provider hoặc quyền thực thi **không cho tạo symbolic link**, dòng đầu có thể là:

```text
symbolicLinksAvailable=false
```

và chương trình bỏ qua phần kiểm tra symlink. Việc chỉ thấy `false` không chứng minh “Windows không hỗ trợ symlink”: nguyên nhân có thể là quyền, filesystem, policy, provider hoặc điều kiện I/O. Đừng tạo test bắt buộc symlink phải tạo được trên mọi CI runner.

**Giải thích:**

- `createSymbolicLink(link, Path.of("actual.txt"))` tạo target tương đối: đường dẫn được giải quyết từ **thư mục chứa `shortcut.txt`**.
- `readSymbolicLink(link).isAbsolute()` bằng false vì target được lưu là relative.
- Không kèm `NOFOLLOW_LINKS`, `isRegularFile(link)` kiểm tra target `actual.txt`; có `NOFOLLOW_LINKS`, nó kiểm tra chính entry link.
- `BasicFileAttributes` cung cấp phép thử loại file với lỗi I/O tường minh.
- `broken.txt` vẫn có entry là symlink nhưng target `missing.txt` không tồn tại, nên hai kiểu `exists` khác nhau.
- `Files.delete(link)` không xóa `actual.txt`.
- Cleanup thử xóa từng entry được tạo; ví dụ không thay đổi file nào ngoài thư mục tạm do chính nó tạo.

Phần catch khi tạo link chỉ xử lý lỗi khả năng nền tảng để **skip kiểm tra link**. Các phép I/O tiếp theo vẫn có thể thất bại; ví dụ để exception đó lộ ra như lỗi test, không che tất cả lỗi bằng `catch (Exception)`.

## 6. Không nhầm symlink với hard link và shortcut giao diện

**Hard link** là một directory entry khác tham chiếu cùng đối tượng file, được tạo bằng `Files.createLink(link, existing)` nếu provider/filesystem hỗ trợ. Nó thường không được `Files.isSymbolicLink()` nhận là symbolic link.

| Đặc điểm | Symbolic link | Hard link |
| --- | --- | --- |
| Đích có thể chưa tồn tại? | Có thể | Thường phải trỏ tới file đang tồn tại |
| `Files.isSymbolicLink` | true cho symlink hợp lệ được nhận diện | false |
| `Files.readSymbolicLink` | Đọc chuỗi target được lưu | Không áp dụng |
| Xóa một entry | Xóa link, không tự xóa target | Gỡ một directory entry; dữ liệu có thể còn qua hard link khác |
| Khả năng hỗ trợ | Có thể bị OS/policy/provider giới hạn | Có thể khác filesystem/provider |
| Tác động đến kiểm thử | Test follow/NOFOLLOW | Test identity và số lượng link theo OS khi phù hợp |

Tệp shortcut kiểu `.lnk` của Windows thường là **một file do shell xử lý**, không được mặc nhiên coi là filesystem symbolic link của `Files.isSymbolicLink`. Tương tự alias của GUI và junction/reparse point có ngữ nghĩa platform riêng; không suy ra mọi loại liên kết đều xuất hiện đồng nhất qua `java.nio.file.Files`.

## 7. Quyền truy cập trong Java: kiểm tra khác với mở thật

Các phép thử tiện dụng:

```java
boolean readable = Files.isReadable(path);
boolean writable = Files.isWritable(path);
boolean executable = Files.isExecutable(path);
```

Đây là snippet cần có `path`. Những phương thức này hữu ích để **hiển thị trạng thái quan sát** hoặc tối ưu đường đi, nhưng:

- Trả true không phải là cam kết lần `Files.newInputStream`/`newOutputStream` kế tiếp sẽ thành công.
- Trả false có thể do không có quyền **hoặc không thể xác định** quyền tại thời điểm đó.
- Quyền thực tế có thể liên quan owner, group, ACL, chính sách sandbox, share mode, network mounts hoặc process identity.
- File có thể bị đổi permission/xóa/thay link giữa phép thử và thao tác.
- Không suy từ `isWritable` ra chắc chắn còn quota/dung lượng đĩa hoặc storage hoạt động.

Cách xử lý đúng là **thực hiện thao tác I/O cần thiết và bắt exception phát sinh**, thay vì dùng `isReadable` như một “authorization check” của người dùng.

Ví dụ:

```java
try (var in = Files.newInputStream(path)) {
    // Xử lý nội dung và kiểm tra kết quả I/O.
} catch (java.nio.file.NoSuchFileException ex) {
    // File/đường dẫn không tồn tại ở thời điểm thao tác.
} catch (java.nio.file.AccessDeniedException ex) {
    // OS/provider từ chối truy cập.
} catch (java.io.IOException ex) {
    // Các lỗi I/O khác: link loop, device, file system...
}
```

Đây là snippet, không phải chương trình độc lập. Các ngoại lệ cụ thể không nhất thiết xuất hiện giống nhau trên mọi provider; nhiều lỗi được báo qua `FileSystemException` hoặc `IOException` chung. **Không được suy diễn `AccessDeniedException` thay thế authorization nghiệp vụ**; hệ điều hành và ứng dụng có các mô hình quyền riêng.

## 8. Basic attributes là điểm bắt đầu portable

`BasicFileAttributes` dùng cho những thuộc tính cơ bản:

```java
BasicFileAttributes info = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

System.out.println(info.isRegularFile());
System.out.println(info.isDirectory());
System.out.println(info.isSymbolicLink());
System.out.println(info.isOther());
System.out.println(info.size());
```

Snippet cần `path`, import và xử lý `IOException`.

`BasicFileAttributes` còn cung cấp `lastModifiedTime()`, `creationTime()`, `lastAccessTime()` và `fileKey()`. Nhưng không nên giả định:

- Mọi filesystem lưu `creationTime` theo nghĩa giống nhau.
- Timestamps có cùng độ chính xác hoặc được cập nhật cùng chính sách trên mọi OS.
- `fileKey()` luôn khác null, ổn định mãi mãi hoặc dùng được như ID public.
- `size()` của symbolic link khi `NOFOLLOW_LINKS` có nghĩa là số byte nội dung của target.
- Toàn bộ attributes được đọc atomically với những thay đổi đồng thời: Javadoc cho phép sự khác biệt do provider.

Nếu cần phân biệt “không phải symbolic link” với “không xác định được vì I/O lỗi”, dùng `readAttributes(..., NOFOLLOW_LINKS)` và xử lý exception, thay vì chỉ gọi `Files.isSymbolicLink` rồi coi false là chứng minh chắc chắn.

## 9. Các nhóm attribute view theo nền tảng

Java NIO.2 có nhiều giao diện attribute view, nhưng hỗ trợ cụ thể phụ thuộc filesystem/provider:

| View | Java API | Thông tin tiêu biểu |
| --- | --- | --- |
| Basic | `BasicFileAttributeView` | Loại entry, size, timestamps, file key |
| POSIX | `PosixFileAttributeView` | Owner, group, POSIX permission bits |
| DOS | `DosFileAttributeView` | Readonly, hidden, archive, system flags |
| Owner | `FileOwnerAttributeView` | Owner user principal |
| ACL | `AclFileAttributeView` | Danh sách ACE và owner |
| User-defined | `UserDefinedFileAttributeView` | Extended attributes nếu provider hỗ trợ |

Thư viện có thể hỏi ở hai cấp:

```java
Set<String> providerViews =
        path.getFileSystem().supportedFileAttributeViews();

FileStore store = Files.getFileStore(path);
boolean posixAvailable =
        store.supportsFileAttributeView(
                PosixFileAttributeView.class);
```

Snippet cần import `Set`, `FileStore`, `PosixFileAttributeView` và `Path`; `Files.getFileStore` có thể ném `IOException`.

- `supportedFileAttributeViews()` là khả năng mà **filesystem provider** hỗ trợ nói chung.
- `FileStore.supportsFileAttributeView(...)` là phép kiểm tra trên **file store** cụ thể.
- Quyền thực tế vẫn có thể khiến thao tác đọc/đổi attributes thất bại, dù view được hỗ trợ.
- Không dùng `System.getProperty("os.name")` làm nguồn quyết định duy nhất: cả trên một OS có thể có nhiều file store với khả năng khác nhau.

`Files.getFileAttributeView(path, PosixFileAttributeView.class)` có thể trả `null` khi view không hỗ trợ. Khi thật sự gọi `Files.getPosixFilePermissions` trên filesystem không hỗ trợ POSIX, thường nhận `UnsupportedOperationException`. Bài test phải có nhánh skip riêng.

## 10. Ví dụ Java 17+ hoàn chỉnh: kiểm tra khả năng file store

Tạo **`FileAttributeCapabilityDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Set;

public class FileAttributeCapabilityDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-views-");
        Path file = dir.resolve("sample.txt");

        try {
            Files.writeString(file, "hello");

            Set<String> views =
                    file.getFileSystem().supportedFileAttributeViews();
            FileStore store = Files.getFileStore(file);

            boolean basic = Files.getFileAttributeView(
                    file, BasicFileAttributeView.class) != null;
            boolean posix = store.supportsFileAttributeView(
                    PosixFileAttributeView.class);
            boolean dos = store.supportsFileAttributeView(
                    DosFileAttributeView.class);
            boolean acl = store.supportsFileAttributeView(
                    AclFileAttributeView.class);

            System.out.println("basic=" + basic);
            System.out.println("providerSupportsBasic="
                    + views.contains("basic"));
            System.out.println("posixSupported=" + posix);
            System.out.println("dosSupported=" + dos);
            System.out.println("aclSupported=" + acl);

            // Kết quả thăm dò không thay thế open/read/write thực tế.
            System.out.println("content="
                    + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FileAttributeCapabilityDemo.java
java FileAttributeCapabilityDemo
```

Hai dòng chắc chắn theo hợp đồng file system provider chuẩn khi các thao tác thành công:

```text
basic=true
providerSupportsBasic=true
```

Các dòng tiếp theo **phụ thuộc nền tảng và file store**:

```text
posixSupported=<true hoặc false>
dosSupported=<true hoặc false>
aclSupported=<true hoặc false>
content=hello
```

Các dấu `<true hoặc false>` là **mô tả khả năng**, không phải output literal cần mong đợi từng ký tự. Chương trình thật in `true` hoặc `false`. Không viết unit test buộc POSIX phải true hoặc DOS/ACL phải false: Java có thể chạy trên filesystem có khả năng khác hệ điều hành chủ.

**Giải thích:** `getFileStore(file)` lấy store của tệp thử nghiệm, không suy từ hệ điều hành. `supportsFileAttributeView` cho biết một khả năng, **không** xác nhận process luôn có quyền chỉnh thuộc tính đó. Ví dụ không thay đổi owner/ACL hoặc permission thật, nên có thể chạy trong workspace tạm mà không ảnh hưởng cấu hình tệp của người dùng.

## 11. POSIX permissions: hiểu các bit và giới hạn

Trên file store hỗ trợ POSIX, có thể đọc quyền bằng:

```java
Set<PosixFilePermission> perms =
        Files.getPosixFilePermissions(path);
String symbolic = PosixFilePermissions.toString(perms);
```

Snippet cần `path` và import `Set`, `PosixFilePermission`, `PosixFilePermissions`, xử lý `IOException`/`UnsupportedOperationException`.

Các ký hiệu `rwxr-x---` là quyền read/write/execute của **owner, group, others**. Nhưng hiệu lực có thể còn phụ thuộc user hiện hành, supplementary groups, ACL, mount flags, quyền thư mục cha và hệ điều hành.

Lưu ý:

- Trên filesystem không hỗ trợ POSIX view, gọi `getPosixFilePermissions` có thể thất bại với `UnsupportedOperationException`.
- `Files.setPosixFilePermissions(path, perms)` **thay đổi quyền file thực**; không dùng trên file người dùng trong ví dụ thử nghiệm.
- `Files.createTempFile`/`createTempDirectory` có thể tạo quyền ban đầu khác nhau theo provider và umask; không hardcode output octal dự kiến cho mọi máy.
- POSIX `OWNER_READ` không tương đương một công bố “mọi process đọc được”.
- Ở Windows, quyền NTFS thường dựa trên ACL; không thể suy ra cách phân quyền chỉ bằng sơ đồ rwx.
- Không dùng permission bits làm cơ chế kiểm tra quyền nghiệp vụ đối với user web. Cần authorization riêng ở application.

### Thăm dò quyền ở mức không gây thay đổi

Trong phần chẩn đoán, ghi các thông tin **không nhạy cảm** như `posixSupported=true`, `fileType=regular`, `testReadSucceeded=true` có thể hữu ích. Nếu cần ghi owner/group/path vào log, phải xét quyền truy cập và bảo vệ dữ liệu; owner hoặc path có thể chứa username thật.

Một phép thử `Files.isWritable(path)` trả true **không hứa** rằng `Files.write(path, bytes)` sẽ thành công sau đó: hệ thống có thể hết dung lượng, quota, file lock, thay trạng thái hoặc policy từ chối ghi vào thời điểm thực hiện.

## 12. DOS flags và ACL: không đồng nhất với POSIX

**DOS attributes** như `readonly`, `hidden`, `archive`, `system` có thể được truy cập qua `DosFileAttributeView` nếu provider hỗ trợ. Chúng không phải bản sao trực tiếp của các bit POSIX.

**ACL** qua `AclFileAttributeView` biểu diễn danh sách mục cấp quyền/từ chối quyền. Hệ thống có thể xét thứ tự và loại ACE, user/group principals và các quy tắc riêng; **không** nên tự thực hiện một parser đơn giản rồi nói “user này chắc chắn được đọc”.

Ví dụ phát hiện view:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path, AclFileAttributeView.class);

if (aclView == null) {
    // Không có ACL view cho path/provider này.
} else {
    // Chỉ khi nghiệp vụ cần và có quyền,
    // đọc ACL theo chính sách bảo mật.
}
```

Đây là snippet. `getAcl()` có thể trả dữ liệu nhạy cảm về user/group; không in toàn bộ ACL lên trang lỗi công khai. Với các test về thay đổi ACL/owner, sử dụng môi trường cô lập có chính sách cụ thể và làm sạch trạng thái sau test; không thay ACL của thư mục làm việc chung.

## 13. Thử thao tác thật và bắt lỗi đúng cách

Một phép thăm dò cần thiết nên ưu tiên **thao tác tối thiểu mà nghiệp vụ dự định làm**, trong phạm vi tệp/thư mục đã cấp quyền:

```java
try (var in = Files.newInputStream(path)) {
    byte[] first = in.readNBytes(32);
    // Chỉ xử lý first.length byte thực đọc.
} catch (java.nio.file.NoSuchFileException ex) {
    // Không tồn tại tại thời điểm mở.
} catch (java.nio.file.AccessDeniedException ex) {
    // Hệ thống không cho phép truy cập.
} catch (IOException ex) {
    // Các lỗi IO khác.
}
```

Đoạn snippet cần `IOException`, `Files`, `Path` và một `path` từ luồng nghiệp vụ đã phân quyền. Nếu cần không đi theo symbolic link cuối cùng, **mở bằng API có hợp đồng tùy chọn phù hợp**, chứ đừng chỉ gọi `isSymbolicLink` rồi mở bình thường.

Một lựa chọn đối với những provider hỗ trợ `NOFOLLOW_LINKS` khi mở channel là:

```java
try (var channel = Files.newByteChannel(
        path,
        java.util.Set.of(
                java.nio.file.StandardOpenOption.READ,
                LinkOption.NOFOLLOW_LINKS))) {
    // Đọc từ channel đã mở nếu thành công.
}
```

Snippet này giả định `path` và import `Files`, `LinkOption`, xử lý `IOException`/`UnsupportedOperationException`. `NOFOLLOW_LINKS` là `OpenOption` được hỗ trợ theo hợp đồng NIO phù hợp; khi target cuối là symbolic link, việc mở có thể thất bại thay vì theo link. Nó **không tự ngăn việc path cha chứa symlink** hoặc một đối thủ thay đổi đường dẫn trước khi mở.

Hãy nghĩ theo nguyên tắc **mở đối tượng cụ thể một lần và dùng handle đã mở**, hạn chế chuỗi “kiểm tra path → sử dụng lại path” tạo cơ hội cho race.

## 14. TOCTOU: lỗi giữa check và use

TOCTOU (*Time Of Check To Time Of Use*) xảy ra khi trạng thái được kiểm tra tại một thời điểm nhưng file thay đổi trước thao tác tiếp theo.

Ví dụ không an toàn:

```java
Path candidate = root.resolve(userSuppliedName).normalize();

if (candidate.startsWith(root)
        && !Files.isSymbolicLink(candidate)
        && Files.isReadable(candidate)) {
    // Một tiến trình khác có thể thay candidate sau các check.
    return Files.readAllBytes(candidate);
}
```

Snippet cố ý minh họa rủi ro; cần khai báo `root` và `userSuppliedName`, kiểm soát đầu vào và xử lý ngoại lệ. Ngoài race ở final symlink, kiểm tra `candidate.startsWith(root)` dựa trên **đường dẫn chuẩn hóa cú pháp**, không bảo đảm đường dẫn thực ở trong root khi thư mục cha chứa symlink.

Đối sách theo mức cần thiết:

1. **Không cho client truyền path tùy ý**; ánh xạ resource ID sang storage key do server quản lý.
2. Thiết lập thư mục lưu trữ có quyền OS phù hợp, không cho bên không tin cậy thay entry và symlink.
3. Dùng các tùy chọn mở `NOFOLLOW_LINKS` khi yêu cầu cấm final symlink; cần xem xét từng thành phần đường dẫn.
4. Trong provider hỗ trợ, cân nhắc `SecureDirectoryStream` để thao tác tương đối qua directory handle và giảm race khi phân giải directory entry.
5. Với tệp cần tạo mới, dùng `StandardOpenOption.CREATE_NEW` để tránh ghi đè entry tồn tại trong những tình huống thích hợp; kết hợp quyền thư mục và option liên quan.
6. Thiết kế xử lý `IOException` ngay ở thao tác thật; không coi check trước là giấy phép chắc chắn.
7. Khi yêu cầu an ninh cao, kiểm tra định danh/file identity và quyền ở OS/resource handle theo khả năng môi trường, thay vì dựa vào string path.

`Path.toRealPath()` giải quyết đường dẫn thực theo hợp đồng, nhưng kết quả đó **cũng có thể lỗi thời ngay sau lời gọi**. Không biến phép chuẩn hóa thành bảo đảm chống symlink swap.

## 15. `toRealPath()` và đường dẫn canonical: dùng đúng ý nghĩa

So sánh:

| API | Tác dụng chính |
| --- | --- |
| `path.toAbsolutePath()` | Tạo dạng absolute theo filesystem context |
| `path.normalize()` | Chuẩn hóa cú pháp `.`, `..`; không cần truy cập file thực |
| `path.toRealPath()` | Trả path thực của một entry tồn tại, theo dõi link mặc định, giải quyết path theo provider |
| `path.toRealPath(NOFOLLOW_LINKS)` | Trả path thực theo tùy chọn không theo symbolic links theo hợp đồng |
| `Files.readSymbolicLink(path)` | Trả target lưu trong symlink, có thể relative và chưa tồn tại |

`toRealPath()` có thể ném `NoSuchFileException`, `FileSystemLoopException` hoặc `IOException` nếu không giải quyết được. `normalize()` không xác minh tệp tồn tại. Tính đặc thù platform còn ảnh hưởng case sensitivity và aliasing.

Không in `toRealPath()` (hoặc path nội bộ gốc) trong HTTP error response chỉ để chẩn đoán; đó có thể là đường dẫn chứa tên người dùng, mount hoặc cấu trúc deployment. Hãy trả mã lỗi công khai ổn định, lưu diagnostic theo chính sách truy cập phù hợp.

## 16. Duyệt cây thư mục và vòng lặp symbolic link

`Files.walkFileTree(start, visitor)` mặc định **không đi theo symlink**. Nếu truyền `FileVisitOption.FOLLOW_LINKS`, traversal có thể đi vào directory liên kết và gặp vòng lặp.

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(
                java.nio.file.FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

Đây là snippet cần `root` và một `FileVisitor<Path> visitor` cùng import; không phải chương trình độc lập. Khi `FOLLOW_LINKS`, Java có cơ chế phát hiện cycle; `FileSystemLoopException` có thể được đưa đến `visitFileFailed`. Người viết visitor phải quyết định xử lý ra sao.

Khi **không có nhu cầu theo dõi link**, nên giữ mặc định không follow và xử lý symbolic-link entry riêng nếu cần. Đặc biệt khi thao tác xóa hoặc đóng gói cây thư mục, một traversal follow link ngoài root có thể chạm đến dữ liệu không thuộc phạm vi. Đừng chạy một chương trình “dọn thư mục” theo tên path chưa tin cậy với `FOLLOW_LINKS` mà không xác định rõ tác động.

### Không suy luận mọi directory listing là snapshot

`Files.walk` hoặc `walkFileTree` có thể quan sát trạng thái thay đổi trong lúc đang duyệt. Directory entry bị xóa, đổi quyền hoặc thay link có thể làm một vòng lặp fail giữa chừng. Chẩn đoán phải xử lý exception theo từng entry và không mặc định danh sách trả về là snapshot nhất quán tuyệt đối.

## 17. Tính đặc thù Windows, Linux, macOS và provider

| Chủ đề | Những điểm có thể thay đổi |
| --- | --- |
| Khả năng tạo symlink | Filesystem, quyền hệ điều hành, policy, developer mode/đặc quyền trên Windows |
| POSIX permission bits | Thường có trên nhiều filesystem kiểu Unix; không nên giả định có trên Windows/NTFS |
| ACL | Có thể có trên Windows/NTFS và một số filesystem khác; không đồng nhất với POSIX bits |
| DOS attributes | Thường gắn với FAT/NTFS hoặc provider liên quan; không có trên mọi store |
| Case sensitivity | NTFS, APFS, ext4... có thể cấu hình/diễn giải khác nhau |
| Separator/path syntax | Windows/Unix và filesystem provider có cách thể hiện khác |
| Symlink/junction/reparse point | Một số loại link riêng OS không nhất thiết được báo theo cùng API |
| Xóa file đang mở | Hành vi chia sẻ/khóa, đặc biệt giữa Windows và POSIX, khác nhau |
| Rename atomic | Phụ thuộc file store/provider và hỗ trợ `ATOMIC_MOVE` |
| Timestamp precision | Mốc thời gian có thể bị làm tròn/không được cập nhật giống nhau |
| Network filesystem | Caching, credentials, lỗi mạng, eventual observation, quyền từ xa |
| Virtual filesystem | ZIP filesystem, in-memory provider, read-only store có tập operation khác |

Không dùng `System.getProperty("os.name")` rồi hardcode toàn bộ hành vi. Kiểm tra **khả năng cụ thể** trên path/file store và **thử operation thật** khi có quyền. Một OS có thể gắn nhiều store với capability khác nhau, hoặc cùng store thay đổi policy giữa môi trường CI và production.

## 18. Viết bài test portable thay vì test phụ thuộc một máy

Một kiểm thử tốt:

- Chỉ tạo file/thư mục **bên trong temp directory** do test sở hữu.
- Với tính năng optional như symlink/POSIX view, có nhánh **skip/assumption** rõ ràng nếu không hỗ trợ hoặc không có quyền.
- Khác biệt giữa **không hỗ trợ** và **đã hỗ trợ nhưng thao tác bị lỗi bất ngờ**; không blanket catch mọi exception rồi báo PASS.
- Không yêu cầu exact POSIX permission string hoặc ACL trên mọi platform.
- Không thay quyền/chủ sở hữu file có sẵn của người dùng hoặc thư mục shared CI.
- Sau khi tạo link, kiểm tra bằng API cụ thể như `readAttributes(..., NOFOLLOW_LINKS)`.
- Kiểm tra broken link, link relative, quyền của target và cleanup.
- Không dựa vào giả định cùng thứ tự listing/timestamp precision cho mọi filesystem.
- Khi test security-critical code, bổ sung test có actor thay symlink đồng thời hoặc test ở môi trường kiểm soát; nêu rõ khả năng nondeterministic của race.

### Ví dụ Java 17+ hoàn chỉnh: test điều kiện symlink có hỗ trợ

Tạo **`SymlinkInvariantTest.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymlinkInvariantTest {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symlink-test-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("alias.txt");

        try {
            Files.writeString(target, "OK");

            try {
                Files.createSymbolicLink(link, Path.of("data.txt"));
            } catch (UnsupportedOperationException
                     | IOException | SecurityException ex) {
                System.out.println("SKIP: symlink cannot be created");
                return;
            }

            BasicFileAttributes attrs = Files.readAttributes(
                    link, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);

            if (!attrs.isSymbolicLink()) {
                throw new AssertionError("Expected symbolic link");
            }
            if (!Files.isSameFile(link, target)) {
                throw new AssertionError("Link must resolve to target");
            }
            if (!Files.readString(link).equals("OK")) {
                throw new AssertionError("Following link read wrong data");
            }

            Files.delete(link);
            if (!Files.exists(target)) {
                throw new AssertionError("Target must survive link deletion");
            }

            System.out.println("PASS: symlink invariants");
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 SymlinkInvariantTest.java
java SymlinkInvariantTest
```

Kết quả nếu symlink được hỗ trợ và mọi phép kiểm tra đúng:

```text
PASS: symlink invariants
```

Nếu provider/policy không cho tạo link:

```text
SKIP: symlink cannot be created
```

**Điểm khác với test “luôn PASS”**: nếu việc tạo link thành công nhưng `readAttributes`, `isSameFile` hoặc `readString` thất bại ngoài dự kiến, lỗi không bị nuốt bởi catch tạo link. Nếu dữ liệu sai, `AssertionError` làm test fail. Chỉ giới hạn skip ở bước tạo link optional.

Trong hệ thống test lớn, nên phân loại lý do skip (unsupported/permission/other I/O) để vận hành dễ chẩn đoán; ví dụ tối giản này chỉ in một thông báo chung và không phụ thuộc JUnit.

## 19. Chẩn đoán lỗi quyền mà không lộ thông tin nội bộ

Khi một hành động I/O bị từ chối, có thể cần ghi log phục vụ nhân viên vận hành:

```text
event=FILE_ACCESS_FAILED
operation=OPEN_READ
reason=ACCESS_DENIED
requestId=<server-generated-id>
```

Không nên tự động trả cho client hoặc log công khai:

```text
AccessDeniedException:
 /var/run/secrets/app/production/token.key
```

`AccessDeniedException.getFile()`, `FileSystemException.getReason()` hoặc `exception.getMessage()` có thể chứa path và chi tiết provider. Nếu cần diagnostic đầy đủ, dùng kênh được bảo vệ, kiểm soát retention và nội dung theo chính sách; **public response** chỉ cần mã lỗi ổn định.

Test phần bảo mật thông báo công khai phải cố tình tạo path có sentinel nhạy cảm và xác minh rằng response/serializer không phản chiếu nó. Hãy phân biệt lỗi quyền truy cập file của process và **authorization nghiệp vụ của user**; hai tầng có thể cùng phát sinh mã 403/404/500 tùy chính sách API.

## 20. Những nhầm lẫn cần tránh

1. **“`Files.exists` false chắc chắn tệp không tồn tại.”** Sai: có thể không xác định được do lỗi truy cập.
2. **“Link bị đứt nghĩa là không có directory entry.”** Sai: `NOFOLLOW_LINKS` có thể chứng minh link vẫn tồn tại.
3. **“`Files.isSymbolicLink` false chứng minh file không phải symlink.”** Chưa chắc nếu không xác định được loại do I/O lỗi.
4. **“`NOFOLLOW_LINKS` chặn mọi symlink ở mọi thư mục cha.”** Không đủ: phải hiểu hợp đồng API và thiết kế directory/path security.
5. **“`readSymbolicLink` trả absolute path.”** Có thể trả relative target được lưu trong link.
6. **“Xóa symbolic link là xóa cả target.”** Sai với `Files.delete(link)` trong trường hợp bình thường.
7. **“Hard link chính là symlink khác tên.”** Sai; định danh và nội dung liên quan theo ngữ nghĩa khác.
8. **“`isReadable` true nghĩa là đọc chắc chắn thành công.”** Sai: TOCTOU và các lý do khác vẫn làm I/O fail.
9. **“`isWritable` false luôn là do ACL từ chối.”** Sai: có thể do không xác định được hoặc chính sách khác.
10. **“Mọi hệ điều hành hỗ trợ POSIX permissions.”** Sai; phải kiểm tra view của file store.
11. **“Windows không bao giờ tạo được symlink.”** Sai; phụ thuộc hệ điều hành, quyền và provider.
12. **“Mỗi file store trên Linux giống nhau.”** Sai; network/ZIP/FUSE/container stores có thể khác.
13. **“`normalize` và `toRealPath` là đủ chống path traversal.”** Sai nếu vẫn còn symlink race/authorization.
14. **“Có view ACL nghĩa là user web đã được cho phép.”** Sai; quyền OS khác policy ứng dụng.
15. **“`Files.walkFileTree` theo link theo mặc định.”** Sai; phải chủ động truyền `FOLLOW_LINKS`.
16. **“Symlink cycle sẽ luôn được xử lý im lặng.”** Sai; khi follow có thể xuất hiện `FileSystemLoopException`.
17. **“Timestamps và thứ tự duyệt luôn ổn định giữa Windows/macOS/Linux.”** Sai; dùng test dựa trên hợp đồng cụ thể.
18. **“Test không tạo symlink được là code xử lý symlink sai.”** Chưa chắc; feature có thể không hỗ trợ hoặc bị policy chặn.
19. **“Catch mọi IOException rồi báo SKIP.”** Sai: che lỗi thật sau khi đã xác định feature hỗ trợ.
20. **“In raw path để debug là vô hại.”** Có thể lộ username, server layout, private storage key.

## 21. Bài tập vận dụng

### Bài A — broken link

Tạo symlink `broken.txt -> missing.txt` trong thư mục tạm. Dự đoán `exists` có/không `NOFOLLOW_LINKS`, `isSymbolicLink` và `readSymbolicLink`. Vì sao các kết quả có thể khác nhau?

### Bài B — POSIX/ACL capability

Trên máy bạn, dùng `Files.getFileStore(path)`, `supportsFileAttributeView(PosixFileAttributeView.class)` và `AclFileAttributeView.class`. So sánh hai file store khác nhau nếu có. Vì sao không nên biến một kết quả thành quy tắc chung cho hệ điều hành?

### Bài C — race giữa kiểm tra và thao tác

Một tiến trình gọi `Files.isRegularFile(candidate, NOFOLLOW_LINKS)`, rồi tiến trình khác thay entry thành symbolic link trước `Files.readString(candidate)`. Giải thích rủi ro TOCTOU và đề xuất cách giảm thiểu bằng giới hạn thư mục, open options và handle.

### Bài D — directory traversal

Một file ZIP chứa entry `../../outside.txt`. Tại sao `root.resolve(name).normalize().startsWith(root)` vẫn chưa đủ nếu thư mục trong root có thể bị thay bởi symlink? Nếu cần thao tác trên cây thư mục do người dùng khác sửa đồng thời, cần cân nhắc capability nào của provider?

### Bài E — test portable trên CI

Hãy sửa `SymlinkInvariantTest` để log lý do skip vào kênh nội bộ nhưng không trả path ra output công khai. Trên môi trường không hỗ trợ symlink, tại sao phải skip test thuộc tính symlink thay vì fail cả build (nếu tính năng là optional)?

### Bài F — file đang mở và cleanup

Thử mở `FileChannel`, sau đó xóa/rename file trong cùng process ở các OS khác nhau. Ghi nhận hành vi thực tế, nhưng không viết test portable giả định Windows hoặc POSIX luôn cho kết quả giống nhau. Sau test phải đóng channel và xóa dữ liệu tạm an toàn.

## 22. Câu hỏi tự kiểm tra

1. `Files.isSymbolicLink(path)` khác `Files.isRegularFile(path, NOFOLLOW_LINKS)` thế nào?
2. Khi target của symlink bị xóa, vì sao `Files.exists(link)` và `Files.exists(link, NOFOLLOW_LINKS)` có thể khác?
3. `Files.readSymbolicLink(link)` trả Path relative so với đâu?
4. `NOFOLLOW_LINKS` có ý nghĩa và giới hạn gì trong việc chống symlink attack?
5. Khi nào nên dùng `Files.readAttributes(..., NOFOLLOW_LINKS)` thay vì chỉ dùng `Files.isSymbolicLink`?
6. `Files.isReadable(path)` trả true có thay thế việc bắt `IOException` không?
7. `FileStore.supportsFileAttributeView` cho biết điều gì, và điều gì nó không cam kết?
8. POSIX permissions và Windows ACL có thể được đồng nhất hoàn toàn không?
9. Tại sao việc check quyền rồi mở file có thể tạo TOCTOU?
10. `Files.delete(link)` có tự động xóa nội dung target của symlink không?
11. Vì sao `Path.normalize()` không phải phép kiểm tra security root chắc chắn?
12. Khi dùng `FOLLOW_LINKS` trong `walkFileTree`, cần xem xét dạng lỗi nào?
13. Nếu CI không thể tạo symlink, làm sao tổ chức test để vẫn nhận diện lỗi thật của chức năng khác?
14. Vì sao cần chạy kiểm thử trên nhiều loại file store, không chỉ nhiều tên hệ điều hành?
15. Có nên đưa path tuyệt đối hoặc owner name lên trang lỗi HTTP khi một `AccessDeniedException` xảy ra không?

## 23. Tài liệu tham khảo Java 17

- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): create/read symbolic link, exists, readAttributes, access probes, walkFileTree.
- [`Path` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): normalize, toAbsolutePath, toRealPath và semantics provider.
- [`LinkOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [`FileStore` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView`.
- [`java.nio.file.attribute` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/package-summary.html): Basic/POSIX/DOS/ACL/User-defined attribute views.
- [`SecureDirectoryStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác directory entry giúp giảm race nếu provider hỗ trợ.
- [`FileVisitOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` khi duyệt cây.

## 24. Ghi nhớ

**Symbolic link là một entry riêng với target**, và `NOFOLLOW_LINKS` chỉ có ý nghĩa trong các API hỗ trợ. Với link bị đứt, kiểm tra tồn tại mặc định có thể false trong khi kiểm tra chính link với `NOFOLLOW_LINKS` là true.

**Quyền truy cập và thuộc tính file phụ thuộc provider/file store, OS, process identity và thời điểm**. `Files.isReadable/isWritable` không thay thế phép mở thật; POSIX/DOS/ACL views cần được phát hiện động. Đối với mã cần bảo mật, tránh TOCTOU bằng quản lý root/handle, quyền thư mục phù hợp, tùy chọn mở không follow và kiểm soát thành phần đường dẫn — không chỉ bằng `normalize()`.

Bài test chất lượng tốt **chỉ dùng tài nguyên tạm**, nhận diện tính năng optional, phân biệt SKIP với FAIL, không yêu cầu output về quyền/symlink giống nhau ở mọi nền tảng, và không làm lộ đường dẫn nội bộ trong thông báo công khai.

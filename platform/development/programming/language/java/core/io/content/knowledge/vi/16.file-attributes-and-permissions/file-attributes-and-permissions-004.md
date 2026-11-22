# Đọc thuộc tính theo kiểu hoặc theo tên trong Java NIO.2

Khi làm việc với tệp và thư mục, ngoài việc đọc nội dung, ứng dụng thường cần biết **kích thước (byte), thời điểm sửa đổi, loại tài nguyên, chủ sở hữu hoặc quyền truy cập**. Java NIO.2, thông qua `java.nio.file.Files` và `java.nio.file.attribute`, cung cấp hai cách quan trọng để đọc **nhiều thuộc tính của một `Path`**:

1. **Theo kiểu (typed):** `Files.readAttributes(path, BasicFileAttributes.class)` trả về một đối tượng có interface xác định tại thời điểm biên dịch.
2. **Theo tên (named):** `Files.readAttributes(path, "basic:size,lastModifiedTime")` trả về `Map<String,Object>` chứa những thuộc tính được yêu cầu bằng tên chuỗi.

Nếu chỉ cần **một** thuộc tính, có `Files.getAttribute(path, "basic:size")`. Mỗi cách có ưu điểm về tính rõ ràng, khả năng mở rộng và yêu cầu provider khác nhau.

Bài này nằm trong phần **Thuộc tính và quyền** của Java Core I/O, dùng Java 17+. Trọng tâm là đọc metadata **không làm thay đổi dữ liệu**, hiểu đúng view `basic`/`posix`/`dos`, tùy chọn symbolic link, khả năng hỗ trợ của filesystem và các tình huống lỗi.

## 1. File attributes là gì?

**File attributes** là thông tin mô tả tệp hoặc thư mục do hệ thống tệp/provider cung cấp, không phải nội dung byte của tệp. Ví dụ:

- `size`: kích thước được báo của tệp theo byte.
- `lastModifiedTime`: thời điểm hệ thống tệp ghi nhận lần sửa đổi cuối.
- `lastAccessTime`: thời điểm truy cập cuối, tùy khả năng hệ thống tệp.
- `creationTime`: thời điểm tạo; có thể không được hỗ trợ đầy đủ.
- `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`: phân loại đối tượng.
- `fileKey`: định danh do provider trả về, có thể là `null`.
- Với những filesystem hỗ trợ: `permissions`, `owner`, `group` của POSIX hoặc `hidden`/`readonly`/`archive`/`system` của DOS.

Đây là metadata, không phải dữ liệu văn bản. `Files.readAttributes` **không đọc toàn bộ nội dung file** giống `Files.readString` hoặc `Files.readAllBytes`. Với tệp lớn, một lần đọc metadata thường không yêu cầu nạp toàn bộ nội dung vào RAM; tuy nhiên nó vẫn có thể là **thao tác I/O** tới ổ đĩa, mạng hoặc filesystem provider.

### Tổng quan các API

| API | Kết quả | Khi dùng |
| --- | --- | --- |
| `Files.readAttributes(path, BasicFileAttributes.class)` | `BasicFileAttributes` | Cần metadata cơ bản và type safety |
| `Files.readAttributes(path, PosixFileAttributes.class)` | `PosixFileAttributes` | Cần POSIX permissions/owner/group và provider hỗ trợ |
| `Files.readAttributes(path, DosFileAttributes.class)` | `DosFileAttributes` | Cần DOS hidden/read-only/archive/system và provider hỗ trợ |
| `Files.readAttributes(path, "basic:size,isDirectory")` | `Map<String,Object>` | Cần chọn thuộc tính theo danh sách tên |
| `Files.readAttributes(path, "posix:*")` | `Map<String,Object>` | Cần tập thuộc tính POSIX từ provider hỗ trợ |
| `Files.getAttribute(path, "basic:size")` | `Object` (thực tế là `Long`) | Cần một thuộc tính xác định |
| `Files.size(path)` | `long` | Cách tiện lợi nếu chỉ cần kích thước |
| `Files.getLastModifiedTime(path)` | `FileTime` | Cách tiện lợi nếu chỉ cần thời gian sửa đổi |
| `Files.getOwner(path)` | `UserPrincipal` | Cách tiện lợi nếu cần owner và provider hỗ trợ |

**Điểm mấu chốt:** Từ “theo kiểu” và “theo tên” nói về **cách Java biểu diễn và yêu cầu thuộc tính**, không phải hai loại file khác nhau.

## 2. Đọc theo kiểu: Files.readAttributes(Path, Class<A>, ...)

Chữ ký quan trọng (rút gọn):

```java
<A extends BasicFileAttributes> A readAttributes(
        Path path,
        Class<A> type,
        LinkOption... options) throws IOException
```

Cách dùng cơ bản:

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

long bytes = attrs.size();
boolean regular = attrs.isRegularFile();
FileTime modified = attrs.lastModifiedTime();
```

Đây là **mảnh mã**: cần import `java.nio.file.*` và `java.nio.file.attribute.*`; `path` đã được xác định và phải xử lý `IOException`.

Đặc điểm:

- Tham số `Class<A>` chỉ rõ kiểu đối tượng metadata cần nhận.
- Trả về đối tượng thực thi interface thuộc tính tương ứng; lập trình viên gọi phương thức có kiểu như `size()` hoặc `isDirectory()` thay vì tự ép kiểu từ `Object`.
- `BasicFileAttributes.class` được mọi triển khai NIO.2 hỗ trợ ở mức giao diện cơ bản. Các kiểu mở rộng như `PosixFileAttributes` và `DosFileAttributes` **không được bảo đảm hỗ trợ trên mọi provider**.
- Cách đọc này yêu cầu **một lần đọc nhiều thuộc tính** qua provider (*bulk operation*). Điều đó **không bảo đảm tất cả trường được đọc nguyên tử** so với thay đổi đồng thời của filesystem.
- Đối tượng `attrs` mô tả kết quả tại thời điểm đọc. Không nên coi `attrs.size()` là giá trị “tự cập nhật” khi file tiếp tục bị ghi. Muốn lấy thông tin mới, đọc lại metadata.

### Các thành viên chính của BasicFileAttributes

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `size()` | `long` | Kích thước file theo byte; ý nghĩa với loại không phải regular file phụ thuộc provider |
| `isRegularFile()` | `boolean` | Có phải file thường |
| `isDirectory()` | `boolean` | Có phải thư mục |
| `isSymbolicLink()` | `boolean` | Có phải symbolic link — phụ thuộc cách follow link |
| `isOther()` | `boolean` | Loại khác file thường/thư mục/symbolic link |
| `creationTime()` | `FileTime` | Thời điểm tạo, có thể dùng giá trị dự phòng khi filesystem không hỗ trợ |
| `lastModifiedTime()` | `FileTime` | Thời điểm sửa nội dung/metadata theo provider |
| `lastAccessTime()` | `FileTime` | Thời điểm truy cập cuối nếu có |
| `fileKey()` | `Object`, có thể `null` | Định danh đối tượng file nếu provider cung cấp |

`FileTime` không phải `long` mặc định. Bạn có thể dùng `toMillis()` hoặc `toInstant()` khi cần chuyển đổi, nhưng phải nhớ độ phân giải, chính sách cập nhật thời gian và vùng thời gian hiển thị khác nhau giữa filesystem.

**Đừng suy diễn:** `creationTime()` có giá trị không có nghĩa filesystem chắc chắn lưu được thời điểm tạo thực; Java cho phép giá trị mặc định/giá trị thay thế khi thuộc tính thời gian không được hỗ trợ. `fileKey()` có thể `null` và không phải mã định danh bền vững vĩnh viễn qua xóa/tạo lại.

### Chọn type khi metadata nâng cao

`PosixFileAttributes` mở rộng `BasicFileAttributes`, thêm:

```java
PosixFileAttributes posix =
        Files.readAttributes(path, PosixFileAttributes.class);

Set<PosixFilePermission> permissions = posix.permissions();
UserPrincipal owner = posix.owner();
GroupPrincipal group = posix.group();
```

Đây là **mảnh mã chạy trên provider có POSIX attribute view**, không mặc định portable lên mọi Windows hoặc ZIP filesystem. Cần import `java.nio.file.attribute.*`, `java.nio.file.*` và xử lý `IOException`/`UnsupportedOperationException` khi phù hợp.

Tương tự, `DosFileAttributes` mở rộng `BasicFileAttributes` và có các boolean `isHidden()`, `isReadOnly()`, `isArchive()` và `isSystem()`. Không được giả định rằng tệp trên mọi hệ điều hành đều có những cờ DOS này.

## 3. Đọc theo tên: Files.readAttributes(Path, String, ...)

Chữ ký:

```java
Map<String, Object> values =
        Files.readAttributes(path, "basic:size,lastModifiedTime");
```

Mảnh mã cần `java.nio.file.Files`, `java.nio.file.Path`, `java.util.Map` và xử lý `IOException`.

Tham số chuỗi có cú pháp:

```text
[view-name:]attribute-name[,attribute-name...]

Ví dụ:
size
basic:size
basic:size,isRegularFile,lastModifiedTime
size,lastModifiedTime
basic:*
posix:permissions,owner,group
posix:*
dos:hidden,readonly,archive,system
```

Ý nghĩa:

- `view-name` là tên **FileAttributeView** như `basic`, `posix` hoặc `dos`.
- Nếu bỏ `view-name`, Java hiểu là `basic`. Vì vậy `"size"` tương đương cách yêu cầu `"basic:size"` trong ngữ cảnh default basic view.
- Với `"basic:size,isDirectory"`, phần `basic:` áp dụng cho **toàn danh sách** ở phía sau, không phải riêng `size`.
- Nhiều thuộc tính được phân tách bằng dấu phẩy.
- Ký hiệu `*` có nghĩa chọn **tất cả thuộc tính mà view đó hỗ trợ**. `"*"` mặc định là `"basic:*"`.
- Kết quả là `Map<String,Object>`, các **key là tên thuộc tính** như `"size"` hoặc `"isDirectory"`, **không kèm `"basic:"` ở đầu key**.
- Những thuộc tính không được hỗ trợ có thể không xuất hiện trong map theo hợp đồng; tên không hợp lệ hoặc view không hỗ trợ có thể gây ngoại lệ.

Ví dụ:

```java
Map<String, Object> attrs =
        Files.readAttributes(path, "basic:size,isRegularFile");

long size = (Long) attrs.get("size");
boolean regular = (Boolean) attrs.get("isRegularFile");
```

Đây là **mảnh mã**; giá trị của `size` trong basic view có kiểu boxed `Long`, của `isRegularFile` là `Boolean`. Đừng ép sang `Integer` chỉ vì size nhỏ. `Map.get(...)` có thể trả `null` khi key không có; với những thuộc tính/provider không chắc chắn, kiểm tra `containsKey(...)` và kiểu dữ liệu trước khi ép.

### Vì sao map trả Object?

Cùng một view có thuộc tính với nhiều kiểu:

| Tên khóa basic | Java object thường nhận |
| --- | --- |
| `size` | `Long` |
| `lastModifiedTime` | `FileTime` |
| `creationTime` | `FileTime` |
| `isDirectory` | `Boolean` |
| `isRegularFile` | `Boolean` |
| `fileKey` | `Object` hoặc `null` nếu không có |

Với `posix:permissions`, giá trị là `Set<PosixFilePermission>`; `posix:owner` là `UserPrincipal`; `posix:group` là `GroupPrincipal`. Cần hiểu schema của attribute view trước khi sử dụng kết quả.

Ưu điểm của named API là có thể chọn theo cấu hình lúc chạy, đặc biệt khi chương trình cần tùy chọn các field hoặc hỗ trợ nhiều provider. Nhược điểm là lỗi chính tả tên field có thể chỉ được phát hiện khi chạy và cần ép kiểu.

### Có nên in map trực tiếp?

Bạn có thể dùng `System.out.println(attrs)` để quan sát, nhưng đừng coi thứ tự key trong `Map` là thứ tự bảo đảm. Với dữ liệu cần output kiểm thử ổn định, lấy từng key riêng, hoặc sắp xếp tên key nếu muốn in danh sách.

## 4. Chỉ cần một thuộc tính: Files.getAttribute(Path, String, ...)

`Files.getAttribute` trả về **một** giá trị dưới dạng `Object`:

```java
long bytes = (Long) Files.getAttribute(path, "basic:size");
FileTime modified =
        (FileTime) Files.getAttribute(path, "lastModifiedTime");
boolean directory = (Boolean) Files.getAttribute(path, "basic:isDirectory");
```

Mảnh mã cần import `java.nio.file.*` và `java.nio.file.attribute.FileTime`, xử lý `IOException`.

Sự khác nhau:

| Trường hợp | Chọn API hợp lý |
| --- | --- |
| Nhiều thuộc tính basic cần sử dụng trong code Java có kiểu tĩnh | `readAttributes(path, BasicFileAttributes.class)` |
| Cần chọn vài tên theo chuỗi/cấu hình | `readAttributes(path, "basic:size,isDirectory")` |
| Cần đọc đúng một thuộc tính đặc thù | `getAttribute(path, "view:name")` |
| Chỉ muốn kích thước file | `Files.size(path)` |
| Chỉ muốn thời điểm sửa đổi | `Files.getLastModifiedTime(path)` |

`Files.size(path)` trả `long` nên tránh phải cast `Object`. Nó là API tiện ích dễ đọc cho trường hợp chỉ muốn kích thước. Nhưng đừng gọi `Files.size(...)` liên tiếp với nhiều getter rồi giả định tất cả giá trị được lấy từ cùng một thời điểm hệ thống tệp: file có thể thay đổi giữa các lệnh.

## 5. Ví dụ hoàn chỉnh Java 17+: so sánh typed, named và single attribute

Tạo file `AttributeReadDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Map;

public class AttributeReadDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("attrs-", ".txt");

        try {
            Files.writeString(file, "Hello", StandardCharsets.UTF_8);

            BasicFileAttributes typed =
                    Files.readAttributes(file, BasicFileAttributes.class);

            Map<String, Object> named = Files.readAttributes(
                    file, "basic:size,isRegularFile,isDirectory");

            long onlySize =
                    (Long) Files.getAttribute(file, "basic:size");

            System.out.println("typed size: " + typed.size());
            System.out.println("typed regular: " + typed.isRegularFile());
            System.out.println("named size: " + named.get("size"));
            System.out.println("named regular: "
                    + named.get("isRegularFile"));
            System.out.println("named directory: "
                    + named.get("isDirectory"));
            System.out.println("single size: " + onlySize);
            System.out.println("named keys: " + named.size());
            System.out.println("basic supported: "
                    + Files.getFileStore(file)
                            .supportsFileAttributeView("basic"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac AttributeReadDemo.java
java AttributeReadDemo
```

Stdout đã đối chiếu với Java trên filesystem bình thường:

```text
typed size: 5
typed regular: true
named size: 5
named regular: true
named directory: false
single size: 5
named keys: 3
basic supported: true
```

Giải thích:

1. `Files.createTempFile(...)` thực sự tạo một file tạm có tên riêng, nên demo tránh ghi đè file của người dùng.
2. `Files.writeString(file, "Hello", UTF_8)` ghi đúng **5 byte ASCII/UTF-8**.
3. Typed overload trả `BasicFileAttributes`; `typed.size()` là kiểu `long` và `typed.isRegularFile()` là `boolean`.
4. Named overload chỉ yêu cầu ba trường, vì vậy map có đúng ba key được cung cấp trên basic view.
5. `getAttribute(file, "basic:size")` trả `Object`, được ép sang `Long` rồi auto-unbox về `long`.
6. Basic file attribute view là phần được bảo đảm trên các provider NIO.
7. `finally` xóa duy nhất file tạm do demo tạo. Nếu file bị tiến trình khác sửa/xóa giữa chừng, hoặc filesystem từ chối I/O, chương trình có thể báo lỗi; những điều đó không phải hành vi mà bài demo cố tái hiện.

**Lưu ý về “cùng kết quả”:** trong ví dụ không có tiến trình khác sửa file sau khi `writeString`, cả ba cách báo 5 byte. Trong hệ thống đang có ghi đồng thời, mỗi lần đọc có thể thấy trạng thái khác nhau. Đọc nhiều thuộc tính trong một lời gọi không được Java bảo đảm là snapshot nguyên tử so với thao tác filesystem khác.

## 6. LinkOption.NOFOLLOW_LINKS: thuộc tính của link hay của đích?

Filesystem có thể chứa **symbolic link**. Một `Path` trỏ tới symlink thực tế có hai đối tượng liên quan:

```text
Path: alias.txt  ----symbolic link---->  actual.txt
       |                                  |
       | metadata của chính link          | metadata của file đích
       |                                  |
       +-- NOFOLLOW_LINKS                 +-- theo link (mặc định)
```

Các overload đọc thuộc tính nhận `LinkOption... options`. Mặc định, khi gặp symbolic link, Java thường **đi theo link tới đích** và đọc thuộc tính đích. Để yêu cầu metadata của chính symbolic link:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        symbolicLink, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

Map<String, Object> linkNamed = Files.readAttributes(
        symbolicLink, "basic:isSymbolicLink,size",
        LinkOption.NOFOLLOW_LINKS);

Object value = Files.getAttribute(
        symbolicLink, "basic:isSymbolicLink",
        LinkOption.NOFOLLOW_LINKS);
```

Đây là mảnh mã; `symbolicLink` là `Path` thực sự trỏ tới một link; cần import `java.nio.file.*`, `java.nio.file.attribute.*` và `java.util.Map`. Nếu hệ thống không hỗ trợ symbolic link, quyền tạo link bị giới hạn, hoặc link bị thay đổi trong lúc chạy, phải xử lý lỗi phù hợp.

Trong điều kiện link tồn tại và trỏ tới file thường:

| Cách đọc | `isRegularFile()` | `isSymbolicLink()` |
| --- | ---: | ---: |
| `Files.readAttributes(link, BasicFileAttributes.class)` | Thường `true` | Thường `false`, vì đang xem **đích** |
| `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Thường `false` | `true`, vì đang xem **link** |

Không được hiểu rằng `NOFOLLOW_LINKS` tự động chặn mọi loại filesystem traversal hoặc chống tất cả TOCTOU/symlink race. Nó là tùy chọn **chỉ dẫn cách xử lý link cho lời gọi đó**, không phải sandbox bảo mật toàn diện.

### Ví dụ có thể chạy khi provider hỗ trợ symlink

```java
Path dir = Files.createTempDirectory("links-");
Path target = dir.resolve("target.txt");
Path link = dir.resolve("alias.txt");

try {
    Files.writeString(target, "AB", StandardCharsets.UTF_8);
    Files.createSymbolicLink(link, target.getFileName());

    BasicFileAttributes followed =
            Files.readAttributes(link, BasicFileAttributes.class);
    BasicFileAttributes notFollowed = Files.readAttributes(
            link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);

    System.out.println("followed regular: " + followed.isRegularFile());
    System.out.println("link itself: " + notFollowed.isSymbolicLink());
} finally {
    Files.deleteIfExists(link);
    Files.deleteIfExists(target);
    Files.deleteIfExists(dir);
}
```

Đây là **mảnh mã**, cần import `java.nio.file.*`, `java.nio.file.attribute.BasicFileAttributes`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Trên filesystem hỗ trợ và cho phép tạo symbolic link, hai dòng output là `true` và `true`. Trên một số Windows hoặc provider khác, `createSymbolicLink` có thể không được hỗ trợ hoặc cần quyền đặc biệt; vì vậy ví dụ **không** tuyên bố portable về quyền tạo link. Trong thực tế, dùng `try/finally` và dọn chính link chứ không duyệt theo link ra ngoài thư mục.

## 7. FileAttributeView: basic, posix, dos và owner

Tên `basic`, `posix`, `dos` trong cú pháp chuỗi là **tên các attribute view**, không phải file extension hay chế độ mã hóa nội dung. Chúng tương ứng những nhóm thuộc tính mà provider hỗ trợ.

### basic: phổ biến nhất

`BasicFileAttributes` gồm kích thước, loại file, các mốc thời gian và fileKey. Mọi NIO provider phải hỗ trợ basic view. Ví dụ:

```java
BasicFileAttributes a =
        Files.readAttributes(path, BasicFileAttributes.class);
Map<String, Object> b =
        Files.readAttributes(path, "basic:size,lastModifiedTime");
```

Bạn có thể dùng cả hai trên file và thư mục; tuy nhiên `size()` cho đối tượng không phải regular file có ý nghĩa do provider quy định. Ví dụ không được dựa vào `size()` của thư mục để xác định số lượng file con.

### posix: permissions, owner, group

Nếu provider hỗ trợ `posix`:

```java
PosixFileAttributes a =
        Files.readAttributes(path, PosixFileAttributes.class);

Set<PosixFilePermission> perms = a.permissions();
UserPrincipal owner = a.owner();
GroupPrincipal group = a.group();

Map<String, Object> named =
        Files.readAttributes(path, "posix:permissions,owner,group");
```

Đây là mảnh mã, cần import `java.nio.file.*`, `java.nio.file.attribute.*`, `java.util.*`, xử lý `IOException`. Một provider không hỗ trợ view này có thể ném `UnsupportedOperationException` khi bạn cố đọc.

`permissions()` trả một tập `PosixFilePermission`; có thể hiển thị bằng `PosixFilePermissions.toString(perms)` dưới dạng như `rw-r-----`. Tập quyền phản ánh metadata hệ thống tệp, không cam kết ứng dụng chắc chắn được thao tác: ACL, chính sách sandbox, owner, mount option hoặc thay đổi đồng thời vẫn có thể tác động.

### dos: hidden, read-only, archive, system

Nếu view `dos` được hỗ trợ:

```java
DosFileAttributes a =
        Files.readAttributes(path, DosFileAttributes.class);

boolean hidden = a.isHidden();
boolean readOnly = a.isReadOnly();

Map<String, Object> named =
        Files.readAttributes(path, "dos:hidden,readonly");
```

Đây là mảnh mã; cần `java.nio.file.*`, `java.nio.file.attribute.*` và `java.util.Map`, xử lý `IOException`. Trong named view, key thường là `"hidden"` và `"readonly"`, không phải `"isHidden"`/`"isReadOnly"`. Lưu ý sự khác nhau giữa **tên thuộc tính trong chuỗi** và **tên phương thức Java**!

POSIX và DOS không phải hai chế độ mà mọi OS có đầy đủ. Provider có thể hỗ trợ một, cả hai hoặc có ràng buộc riêng. Hãy kiểm tra khả năng hỗ trợ và giải quyết graceful fallback theo nhu cầu nghiệp vụ.

### owner, ACL, user-defined attributes

Các nhóm thuộc tính khác như `FileOwnerAttributeView`, `AclFileAttributeView` và `UserDefinedFileAttributeView` được truy cập qua API view phù hợp, ví dụ:

```java
FileOwnerAttributeView ownerView =
        Files.getFileAttributeView(path, FileOwnerAttributeView.class);

if (ownerView != null) {
    UserPrincipal owner = ownerView.getOwner();
}
```

Mảnh mã cần `java.nio.file.*` và `java.nio.file.attribute.*`. `getFileAttributeView(...)` có thể trả `null` khi không hỗ trợ. **Không** nghĩ rằng tất cả attribute view đều là một kiểu con của `BasicFileAttributes`: overload typed `readAttributes(Path, Class<A>)` chỉ chấp nhận `A extends BasicFileAttributes`, vì vậy `AclFileAttributeView.class` không phải đối số kiểu hợp lệ cho overload đó. Với ACL, dùng `Files.getFileAttributeView(path, AclFileAttributeView.class)` rồi gọi `getAcl()` nếu được hỗ trợ.

## 8. Xác định provider hỗ trợ view nào

Một chương trình portable cần **phát hiện khả năng hỗ trợ trước khi phụ thuộc vào POSIX/DOS**. Hai API hữu ích:

```java
Set<String> views = path.getFileSystem()
        .supportedFileAttributeViews();

boolean posixOnStore = Files.getFileStore(path)
        .supportsFileAttributeView("posix");
```

Đây là mảnh mã; cần `java.nio.file.*` và `java.util.Set`. `supportedFileAttributeViews()` mô tả các view mà filesystem hỗ trợ; `FileStore.supportsFileAttributeView("posix")` hỏi về hỗ trợ của file store chứa file đó. Hai tầng này cung cấp thông tin khả năng hỗ trợ nhưng **không** bảo đảm đọc file cụ thể chắc chắn thành công (quyền, đường dẫn bị xóa, race, lỗi I/O có thể xảy ra).

Mẫu có fallback:

```java
BasicFileAttributes basic =
        Files.readAttributes(path, BasicFileAttributes.class);

FileStore store = Files.getFileStore(path);
if (store.supportsFileAttributeView("posix")) {
    PosixFileAttributes posix =
            Files.readAttributes(path, PosixFileAttributes.class);
    // Xử lý owner/group/permissions nếu thao tác thành công.
} else {
    // Chỉ dùng basic attributes hoặc chiến lược khác.
}
```

Đây là mảnh mã, cần import `java.nio.file.*` và `java.nio.file.attribute.*`, xử lý `IOException`. Nếu một view có thể biến mất/không hoạt động giữa lúc kiểm tra và sử dụng, vẫn xử lý ngoại lệ ở lời gọi thực sự.

Không đặt một chuỗi `"posix:*"` làm mặc định cho mọi runtime rồi bắt mọi lỗi bằng `catch (Exception ignored)`. Điều đó có thể che các lỗi quyền/đường dẫn quan trọng và làm hệ thống tưởng đã kiểm tra bảo mật thành công.

## 9. Ngoại lệ khi đọc thuộc tính

Đọc metadata vẫn là I/O, do đó có thể lỗi:

| Lỗi/ngoại lệ | Nguyên nhân phổ biến |
| --- | --- |
| `NoSuchFileException` | File hoặc thành phần đường dẫn không tồn tại tại thời điểm đọc |
| `AccessDeniedException` | Provider/hệ điều hành từ chối truy cập |
| `IOException` | Lỗi I/O tổng quát, file system/network provider, v.v. |
| `UnsupportedOperationException` | Provider không hỗ trợ attribute type/view được yêu cầu |
| `IllegalArgumentException` | Chuỗi attribute name/syntax không hợp lệ |
| `SecurityException` | Môi trường áp đặt kiểm tra bảo mật và từ chối thao tác |

Không phải mọi provider sẽ ném đúng một subtype cố định trong mọi tình huống. Ví dụ unsupported attribute name có thể bị từ chối, trong khi một thuộc tính hợp lệ nhưng không được cung cấp có thể bị bỏ qua khỏi kết quả map. Khi thiếu key, đừng ép kiểu vô điều kiện.

Dạng xử lý có thể dùng:

```java
try {
    BasicFileAttributes attrs =
            Files.readAttributes(path, BasicFileAttributes.class);
    System.out.println(attrs.size());
} catch (NoSuchFileException e) {
    // File đã bị xóa, hoặc chưa tồn tại.
} catch (AccessDeniedException e) {
    // Không đủ quyền để đọc metadata.
} catch (IOException e) {
    // Một lỗi I/O khác.
}
```

Đây là mảnh mã; cần `java.nio.file.*` và `java.nio.file.attribute.*`. Hai subtype cụ thể đứng trước `IOException`. Nếu ứng dụng thực sự dùng POSIX, cũng cần xử lý trường hợp unsupported view.

`Files.exists(path)` có thể hữu ích cho UI hoặc luồng điều khiển mềm, nhưng **không** nên dùng `exists` như điều kiện bảo đảm lời gọi `readAttributes` tiếp theo thành công. Filesystem có thể thay đổi giữa hai thao tác (*TOCTOU*).

## 10. Thời gian và tính nhất quán của metadata

Các timestamp `creationTime`, `lastModifiedTime` và `lastAccessTime` là `FileTime`. Có thể chuyển:

```java
FileTime time = attrs.lastModifiedTime();
Instant instant = time.toInstant();
long millis = time.toMillis();
```

Đây là mảnh mã với biến `attrs` đã đọc; cần import `java.nio.file.attribute.FileTime` và `java.time.Instant`. Khi định dạng hiển thị theo múi giờ, sử dụng `Instant` và `ZoneId` thích hợp; không tự mặc định timestamp là chuỗi theo giờ địa phương.

Một số giới hạn:

- Độ chính xác/độ phân giải timestamp phụ thuộc filesystem (nanosecond, millisecond, second hoặc kém hơn).
- Một filesystem không hỗ trợ đầy đủ creation/access time có thể trả giá trị mặc định thay thế.
- Các attribute có thể đến từ cache của OS/network filesystem. Không được coi metadata là “real-time tuyệt đối” trên mọi provider.
- Nhiều trường đọc trong một lời gọi `readAttributes` **có thể không phải một snapshot nguyên tử** khi có hoạt động file system đồng thời; đây là chi tiết triển khai.
- Nếu file lớn đang được ghi, kích thước và lastModifiedTime có thể đổi ngay sau khi đọc.
- `fileKey()` có thể hỗ trợ nhận biết cùng file trong những điều kiện nhất định, nhưng có thể `null`, không bảo đảm duy nhất vĩnh viễn sau khi file bị xóa/tạo lại.

Khi nghiệp vụ đòi hỏi tính nhất quán cao (ví dụ trước khi xử lý file nhạy cảm hoặc kiểm tra hash), phải thiết kế cách mở file/khóa/đối chiếu nội dung phù hợp thay vì chỉ dựa vào những kiểm tra metadata trước đó.

## 11. So sánh hai overload cho các tác vụ điển hình

| Tiêu chí | Typed `readAttributes(Path, Class<A>)` | Named `readAttributes(Path, String)` |
| --- | --- | --- |
| Giá trị trả về | `BasicFileAttributes` hoặc subtype | `Map<String,Object>` |
| Truy cập field | Gọi phương thức như `size()` | Tra key như `get("size")` |
| Type safety | Cao hơn: compiler biết kiểu phương thức | Thấp hơn: cần cast/kiểm tra kiểu |
| Chọn field | Đọc tập thuộc tính mà interface định nghĩa | Chọn danh sách tên yêu cầu |
| Tên thuộc tính | Theo method API | Theo tên trong attribute view |
| Phát hiện sai tên | Lỗi method dễ phát hiện lúc biên dịch | Dễ sai chuỗi, lỗi runtime |
| POSIX/DOS | Dùng subtype nếu provider hỗ trợ | Dùng `posix:...`/`dos:...` nếu hỗ trợ |
| Kết quả khi không hỗ trợ | Unsupported type/view có thể ném exception | Unsupported view/name có thể ném exception; unsupported field có thể vắng |
| Bulk operation | Có | Có |
| Atomic metadata snapshot | Không được đảm bảo mọi provider | Không được đảm bảo mọi provider |

**Gợi ý thực hành:**

- Code Java cần dùng vài trường cơ bản và muốn compiler hỗ trợ: dùng **typed** `BasicFileAttributes`.
- Công cụ thống kê hoặc xuất metadata theo cấu hình tùy chọn: dùng **named** API, song có schema rõ ràng cho các key.
- Chỉ cần một trường: dùng API tiện ích `Files.size` hoặc `getAttribute`.
- Muốn sửa metadata thay vì đọc: dùng `Files.setAttribute`, `Files.setLastModifiedTime` hoặc attribute view tương ứng; đó là **một nhiệm vụ khác**, có thể thay đổi filesystem và cần quyền ghi.

## 12. Ví dụ tình huống: xuất báo cáo kích thước và loại tệp

Một chương trình quét thư mục có thể dùng `walkFileTree`. `FileVisitor.visitFile(Path, BasicFileAttributes)` **đã được truyền metadata theo kiểu `BasicFileAttributes`** cho entry đang thăm, nên không nhất thiết phải gọi `Files.readAttributes` một lần nữa cho mỗi file:

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file,
                                     BasicFileAttributes attrs)
            throws IOException {
        if (attrs.isRegularFile()) {
            System.out.println(file.getFileName() + ": " + attrs.size());
        }
        return FileVisitResult.CONTINUE;
    }
});
```

Đây là **mảnh mã** cần import `java.nio.file.*`, `java.nio.file.attribute.*`, `java.io.IOException`; `root` đã có sẵn. Những callback của visitor có thể báo lỗi I/O; ứng dụng thực tế cần xử lý `visitFileFailed` theo chính sách. Trong quét file lớn, hạn chế những lần đọc lại metadata không cần thiết thường giúp tránh I/O phụ.

Nếu ứng dụng muốn hiển thị quyền POSIX cho một vài file, có thể đọc `PosixFileAttributes` hoặc `Files.readAttributes(path, "posix:permissions")` tại nơi cần. Tránh giả định mỗi entry đều hỗ trợ POSIX, nhất là khi quét nhiều filesystem.

## 13. Lưu ý về API đặt thuộc tính theo tên

API **đọc** và API **ghi** có tên gần nhau nhưng mục đích khác:

```java
Object before = Files.getAttribute(path, "basic:lastModifiedTime");
Files.setAttribute(path, "basic:lastModifiedTime", someFileTime);
```

Đây là mảnh mã; `path` đã có, `someFileTime` là `FileTime` hợp lệ, và cần xử lý `IOException`. Lệnh đầu **không sửa file**; lệnh sau yêu cầu **thay đổi metadata**. Không ghép thao tác set vào ví dụ chỉ đọc nếu không có yêu cầu. Với view hoặc attribute không cho sửa, việc `setAttribute` có thể thất bại dù `getAttribute` đọc được.

Để đọc thời gian sửa đổi, `Files.getLastModifiedTime(path)` thường rõ hơn là gọi `getAttribute` và ép `FileTime`; để ghi, `Files.setLastModifiedTime(path, time)` có chữ ký rõ ràng hơn.

## 14. Lỗi thường gặp khi đọc thuộc tính

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `Files.readString` để hỏi kích thước | Nạp nội dung file không cần thiết | `BasicFileAttributes.size()` hoặc `Files.size` |
| Nhầm `readAttributes(path, BasicFileAttributes.class)` trả `Map` | Sai kiểu hoặc không biên dịch | Dùng phương thức typed `size()`, `isDirectory()` |
| Nghĩ `readAttributes(path, "basic:size")` trả `long` | Cast sai | Nhận `Map<String,Object>` rồi `get("size")` |
| Ép `map.get("size")` sang `Integer` | `ClassCastException` | Kiểu basic `size` là `Long` |
| Dùng `map.get("basic:size")` | Nhận `null` do key không có prefix | Dùng `map.get("size")` |
| Dùng `Files.getAttribute` để đọc cả danh sách | Không đúng API | Dùng overload `Files.readAttributes` theo tên |
| Ghi `"basic:lastModifiedTime,size"` nhưng giả định key có thứ tự | Báo cáo output không ổn định | Đọc từng key hoặc sắp xếp nếu cần |
| Dùng `PosixFileAttributes.class` ở mọi hệ điều hành | Unsupported view | Kiểm tra provider/file store; fallback basic |
| Dùng tên method `"isHidden"` cho DOS map | Sai key attribute | Dùng `"dos:hidden"`, giá trị Boolean |
| Cho rằng `fileKey()` luôn có | Null/giả định sai | Cho phép `null`, tránh phụ thuộc identity vĩnh viễn |
| So sánh time ở độ phân giải nanosecond trên mọi FS | Kết luận sai | Chấp nhận độ chính xác theo provider |
| Gọi `size()` cho directory rồi coi là tổng byte các file con | Sai ý nghĩa | Duyệt file con nếu cần tính tổng |
| Gọi typed/read named nhiều lần rồi coi là snapshot thống nhất | Metadata có thể đổi giữa các lần | Thiết kế nhất quán và retry/lock khi cần |
| Đọc link khi muốn chính metadata của symlink | Thấy metadata của đích | `LinkOption.NOFOLLOW_LINKS` |
| Coi `NOFOLLOW_LINKS` là kiểm tra bảo mật toàn diện | Vẫn còn race/traversal | Kết hợp mô hình quyền/đường dẫn an toàn |
| Không xử lý `IOException` khi đọc metadata | Ứng dụng thất bại ngoài ý muốn | Bắt và xử lý lỗi phù hợp |
| Đọc sai view-name/attribute-name | Runtime error hoặc thiếu key | Dựa trên API của view và kiểm tra schema |
| Nhầm kiểm tra `exists()` với đảm bảo `readAttributes` thành công | TOCTOU | Gọi API thật và xử lý ngoại lệ |
| Coi `readAttributes` là thao tác sửa quyền | Hiểu sai semantics | Dùng `setAttribute`/view setter khi thật sự cần sửa |

## 15. Câu hỏi tự kiểm tra

1. **Hai overload `Files.readAttributes` khác nhau thế nào?** Một nhận `Class<A extends BasicFileAttributes>` và trả đối tượng typed, một nhận danh sách tên `String` và trả `Map<String,Object>`.
2. **`"basic:size,isRegularFile"` yêu cầu mấy thuộc tính?** Hai thuộc tính thuộc basic view: `size` và `isRegularFile`.
3. **Nếu không viết `basic:`, view nào được dùng?** `basic`.
4. **Ký hiệu `"*"` nghĩa gì trong `readAttributes` theo tên?** Lấy tất cả thuộc tính mà view tương ứng hỗ trợ.
5. **Map key của `"basic:size"` là `"basic:size"` hay `"size"`?** `"size"`.
6. **Kiểu Java cho size trong map?** `Long`; `getAttribute` cũng trả một `Object` là `Long` cho basic size.
7. **`BasicFileAttributes` có sẵn ở mọi provider NIO không?** Có, basic attribute view được yêu cầu hỗ trợ.
8. **Có thể đưa `AclFileAttributeView.class` vào typed `readAttributes` không?** Không, vì overload yêu cầu subtype của `BasicFileAttributes`.
9. **Khi nào dùng `PosixFileAttributes`?** Khi cần owner/group/permissions và provider hỗ trợ POSIX view.
10. **Đọc theo kiểu có chắc snapshot nguyên tử không?** Không; tính nguyên tử so với I/O khác là phụ thuộc triển khai.
11. **`NOFOLLOW_LINKS` dùng để làm gì?** Yêu cầu lấy metadata của chính link thay vì đi theo link tới đích (nếu provider hỗ trợ).
12. **`creationTime()` có chắc thời điểm tạo thật trong mọi filesystem?** Không, provider có thể dùng giá trị mặc định nếu không hỗ trợ.
13. **`size()` của thư mục có phải tổng kích thước các file bên trong?** Không.
14. **`Files.getFileStore(path).supportsFileAttributeView("posix")` có bảo đảm lần đọc chắc thành công không?** Không; quyền và trạng thái file vẫn có thể thay đổi.
15. **Muốn đọc một thuộc tính thay vì một map thì làm gì?** `Files.getAttribute(path, "view:name")` hoặc API tiện ích như `Files.size`.
16. **Nếu filesystem không hỗ trợ view DOS/POSIX?** Không giả định có mặt; kiểm tra capability, chọn basic/fallback, xử lý `UnsupportedOperationException`.
17. **`readAttributes` có tự sửa permission hay timestamp không?** Không, đó là thao tác đọc.
18. **Làm sao giảm đọc metadata dư khi dùng `walkFileTree`?** Dùng tham số `BasicFileAttributes` mà callback `visitFile` đã cung cấp.

## Tài liệu API Java 17

- [`Files.readAttributes`, `Files.getAttribute` và `Files.getFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).
- [`PosixFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributes.html).
- [`DosFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributes.html).
- [`FileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttributeView.html).
- [`FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html).
- [`LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html).
- [`FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html).
- [`FileSystemProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html).

**Ghi nhớ:** Với Java NIO, muốn có **thuộc tính rõ kiểu**, dùng `Files.readAttributes(path, BasicFileAttributes.class)`; muốn **chọn thuộc tính theo tên**, dùng `Files.readAttributes(path, "basic:size,isDirectory")`; muốn một thuộc tính, dùng `Files.getAttribute` hoặc getter chuyên dụng. Đừng lẫn metadata với nội dung file, đừng giả định POSIX/DOS có trên mọi provider, và luôn xử lý symbolic link, quyền truy cập, lỗi I/O cùng khả năng metadata thay đổi đồng thời.
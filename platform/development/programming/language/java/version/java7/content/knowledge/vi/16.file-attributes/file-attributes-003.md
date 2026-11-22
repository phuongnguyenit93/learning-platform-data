# Java 7 — Thuộc tính tệp: Đọc ghi thuộc tính theo tên hoặc giao diện có kiểu

## Mục tiêu bài học

Khi làm việc với file và directory, **nội dung** không phải toàn bộ thông tin của một mục trên filesystem. Mỗi file còn có **thuộc tính (file attributes / metadata)**: kích thước, loại mục, thời gian sửa lần cuối, thời gian truy cập, quyền truy cập, chủ sở hữu, cờ ẩn, v.v. Java NIO.2 cung cấp API để đọc và — với những thuộc tính cho phép — cập nhật metadata này.

Đề bài tập trung vào **hai cách truy cập thuộc tính bổ sung cho nhau**, đều có từ Java 7 và vẫn hợp lệ trên các JDK hiện đại:

1. **Theo tên (dynamic/named access):** Chuỗi như `"basic:size"` hoặc `"basic:lastModifiedTime"` truyền vào `Files.getAttribute`, `Files.setAttribute` hay `Files.readAttributes(Path, String, ...)`. Kết quả thường là `Object` hoặc `Map<String,Object>`.
2. **Theo giao diện có kiểu (typed access):** Các interface `BasicFileAttributes`, `BasicFileAttributeView`, `PosixFileAttributeView`, `DosFileAttributeView`, v.v. Các method, kiểu trả về và khả năng ghi được thể hiện trong Java API.

Hai cách không phải hai loại metadata khác nhau. Chúng là **hai lối truy cập một hệ thống attribute views**, với sự khác nhau ở mức an toàn kiểu, khả năng chọn thuộc tính động, cách kiểm tra view được hỗ trợ và cách update.

Sau bài, bạn sẽ:

- Giải thích `attribute`, `attribute view` và filesystem provider.
- Đọc metadata cơ bản bằng `Files.readAttributes(path, BasicFileAttributes.class)` và hiểu vì sao return type có kiểu.
- Đọc theo tên bằng `Files.readAttributes(path, "basic:...")` và `Files.getAttribute(path, "...")`; biết cú pháp `view:attribute`, danh sách tên phân cách dấu phẩy, dấu `*`.
- Lấy `BasicFileAttributeView` bằng `Files.getFileAttributeView` rồi đọc và ghi timestamps.
- Cập nhật thuộc tính cho phép ghi bằng `Files.setAttribute(path, "basic:lastModifiedTime", FileTime)`.
- Nhận ra thuộc tính **read-only** như `size` không thể tùy tiện ghi bằng `setAttribute`.
- Phân biệt basic, POSIX, DOS, owner, ACL và user-defined views, kiểm tra hỗ trợ thay vì giả định.
- Hiểu `LinkOption.NOFOLLOW_LINKS` khi có symbolic link.
- Xử lý độ chính xác timestamps, I/O errors, race condition, permission và giới hạn bảo mật.
- Viết chương trình có đầu ra kiểm chứng được, không phụ thuộc tên file tạm hoặc quyền đặc biệt.

**Phiên bản:** `Files`, `BasicFileAttributes`, `BasicFileAttributeView`, `FileTime` và các attribute views được giới thiệu trong Java 7. Những ví dụ sử dụng `Files.writeString` là tiện ích có từ Java 11 trở đi, được phép dùng vì bài kiểm chứng trên Java 17+. Nếu dự án yêu cầu runtime Java 7, thay `writeString` bằng `Files.write` hoặc `newBufferedWriter`, còn nguyên lý đọc/ghi thuộc tính NIO.2 không đổi.

## 1. Thuộc tính tệp là gì?

Cho file:

```text
data/
  report.txt
```

Một filesystem có thể lưu:

| Thuộc tính | Ví dụ minh họa | Ý nghĩa |
| --- | --- | --- |
| Loại mục | Regular file | `report.txt` là file thông thường |
| Kích thước | 3 byte | Số byte theo thuộc tính size |
| Last modified | Một `FileTime` | Thời điểm nội dung/metadata được xem là sửa theo filesystem |
| Last access | Một `FileTime` | Thời điểm truy cập do filesystem ghi nhận nếu được hỗ trợ và bật |
| Creation time | Một `FileTime` | Thông tin tạo file nếu filesystem cung cấp |
| File key | `Object` hoặc null | Khóa nhận diện mang tính provider-specific |
| POSIX permissions | `rw-r-----` | Quyền owner/group/others trên hệ thống hỗ trợ |
| DOS flags | hidden, read-only... | Cờ metadata trên hệ thống hỗ trợ |
| ACL | Danh sách entry quyền | Cơ chế truy cập dựa trên danh sách kiểm soát |

**Đừng đồng nhất metadata với file content:** `Files.readAttributes` không đọc toàn bộ byte nội dung của file. Ngược lại, `Files.readAllBytes` đọc dữ liệu trong file chứ không phải một bản đầy đủ của metadata.

Một `Path` chỉ mô tả đường dẫn. Nó **không xác minh mục tồn tại** cho đến khi bạn dùng một API truy cập filesystem. Việc gọi `Files.getAttribute` hoặc `Files.readAttributes` có thể thực hiện I/O và ném `IOException`.

### 1.1. Provider quyết định khả năng hỗ trợ

Java không yêu cầu mọi filesystem có mọi kiểu metadata. Một tệp trên NTFS/Windows, ext4/Linux, share mạng, zip filesystem hoặc provider tùy biến có thể có tập attribute views khác nhau.

Theo chuẩn NIO.2, **basic file attributes** được yêu cầu hỗ trợ bởi các file-system implementations. Các view như POSIX, DOS, ACL và user-defined là **khả năng tùy chọn**. Khi không hỗ trợ, một API có thể trả `null` cho view hoặc ném `UnsupportedOperationException` cho thao tác đòi hỏi view không có.

**Không viết chương trình mặc định rằng `PosixFileAttributes.class` đọc được trên Windows, hoặc `DosFileAttributeView` đọc được trên Linux.** Hãy kiểm tra và thiết kế fallback.

## 2. Attribute view: lớp phân nhóm metadata

NIO.2 nhóm metadata thành **attribute views**. Những interface chính:

| View | Giao diện typed | Thuộc tính/operation |
| --- | --- | --- |
| `basic` | `BasicFileAttributeView` / `BasicFileAttributes` | Time, size, loại mục, fileKey; cập nhật time nếu được hỗ trợ |
| `posix` | `PosixFileAttributeView` / `PosixFileAttributes` | Basic + owner, group, permissions |
| `dos` | `DosFileAttributeView` / `DosFileAttributes` | Basic + read-only, hidden, system, archive flags |
| `owner` | `FileOwnerAttributeView` | Owner dưới dạng `UserPrincipal` |
| `acl` | `AclFileAttributeView` | ACL và một số thao tác liên quan owner |
| `user` | `UserDefinedFileAttributeView` | Metadata tùy biến do ứng dụng đặt theo khả năng filesystem |

Không phải giao diện nào cũng có một type `...FileAttributes` tương ứng trả về từ overload `Files.readAttributes(path, Class<A>)`. Chẳng hạn `FileOwnerAttributeView` và `AclFileAttributeView` truy cập qua **view methods** chứ không phải tùy ý truyền một class attribute không tồn tại vào API.

### 2.1. Khác nhau giữa attributes và attribute view

- `BasicFileAttributes` là **kết quả đọc** mang những giá trị như `size()`, `lastModifiedTime()`, `isDirectory()`. Nó không cung cấp `setSize` hay `setLastModifiedTime`.
- `BasicFileAttributeView` là **giao diện làm việc với metadata của một path**, có `readAttributes()` và `setTimes(...)`.
- `Files.readAttributes(path, BasicFileAttributes.class)` là cách tắt để lấy snapshot metadata dạng typed.
- `Files.getFileAttributeView(path, BasicFileAttributeView.class)` lấy một view để có thể đọc lẫn cập nhật những trường mà view cho phép.

Đừng nhầm `BasicFileAttributes` (dữ liệu đã đọc) với `BasicFileAttributeView` (giao diện thao tác).

### 2.2. Cú pháp tên `view:attribute`

Với access theo tên, dạng thường gặp:

```text
basic:size
basic:lastModifiedTime
basic:isRegularFile
posix:permissions
dos:hidden
owner:owner
```

`"basic:size"` là **tên thuộc tính**, không phải đường dẫn file. Prefix `basic:` chọn view, phần sau chọn tên thuộc tính theo view ấy. Nếu bỏ prefix khi dùng `Files.getAttribute`/`setAttribute` hoặc `readAttributes(Path, String, ...)`, view mặc định là **basic** theo API.

Vì vậy trong file demo:

```java
Object a = Files.getAttribute(file, "basic:size");
Object b = Files.getAttribute(file, "size");
```

có thể nhận hai giá trị kích thước giống nhau. Dù cú pháp ngắn hoạt động, **nên viết prefix tường minh** ở code hỗ trợ nhiều views để người đọc biết metadata đến từ đâu.

## 3. Đọc thuộc tính kiểu `BasicFileAttributes`

Cách typed căn bản:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class);
```

Đây là **đoạn minh họa** bên trong một phương thức, cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.file.attribute.BasicFileAttributes`, cùng xử lý `IOException`.

Lợi ích:

- Compiler biết `attrs.size()` trả `long`, `attrs.isRegularFile()` trả `boolean` và `attrs.lastModifiedTime()` trả `FileTime`.
- IDE gợi ý đúng tên method và kiểu kết quả.
- Tránh cast tay từ `Object`.
- Thể hiện rõ bạn muốn **nhóm thuộc tính cơ bản**, không phụ thuộc tên view theo string do người dùng cung cấp.

Đây là **bulk read**: nhiều thuộc tính được lấy qua một lời gọi logic. Tuy nhiên, theo đặc tả, provider quyết định liệu việc đọc tất cả thuộc tính ấy có **nguyên tử so với hoạt động filesystem khác** hay không. “Bulk” **không đồng nghĩa snapshot transaction bảo đảm**.

### 3.1. Chương trình A — `TypedAttributesDemo.java`

Chương trình dùng file tạm có nội dung ASCII 3 byte để stdout ổn định, và chỉ in thuộc tính cơ bản, không in timestamp ngẫu nhiên.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class TypedAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-typed-");
        Path file = root.resolve("sample.txt");
        try {
            Files.writeString(file, "abc", StandardCharsets.UTF_8);
            BasicFileAttributes a = Files.readAttributes(
                    file, BasicFileAttributes.class);
            BasicFileAttributes b = Files.readAttributes(
                    file, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);

            System.out.println("regular=" + a.isRegularFile());
            System.out.println("directory=" + a.isDirectory());
            System.out.println("symbolicLink=" + a.isSymbolicLink());
            System.out.println("size=" + a.size());
            System.out.println("sameBasicSize=" + (a.size() == b.size()));
            System.out.println("timeAvailable=" +
                    (a.lastModifiedTime() != null));
            System.out.println("fileKeyMayBeNull=" +
                    (a.fileKey() == null || a.fileKey() != null));
            System.out.println("directoryType=" + Files.readAttributes(
                    root, BasicFileAttributes.class).isDirectory());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 TypedAttributesDemo.java
java TypedAttributesDemo
```

**Stdout đã kiểm tra trên JDK/Windows:**

```text
regular=true
directory=false
symbolicLink=false
size=3
sameBasicSize=true
timeAvailable=true
fileKeyMayBeNull=true
directoryType=true
```

### 3.2. Giải thích kết quả

1. `Files.writeString(file, "abc", UTF_8)` tạo file thật với ba byte ASCII.
2. `a.isRegularFile()` là true; `a.isDirectory()` và `a.isSymbolicLink()` là false.
3. `a.size() == 3` do file chứa ba byte, không phải ba code points hay “kích thước của String object trong JVM”.
4. `NOFOLLOW_LINKS` không tạo khác biệt với **regular file không phải symbolic link** của ví dụ, nên `sameBasicSize=true`.
5. `lastModifiedTime()` có giá trị kiểu `FileTime`.
6. `fileKeyMayBeNull=true` minh họa kiểu `fileKey` có thể là null hoặc không: điều kiện này cố ý không áp đặt một fileKey cụ thể. **Không dùng output ấy để chứng minh `fileKey()` thật sự khác null**.
7. Root tạm là directory, vì vậy `isDirectory()` của nó true.

**Hạn chế:** Kết quả là phép quan sát filesystem tại thời điểm chạy. Trên file do process khác đang ghi, size/timestamps có thể thay đổi giữa các lần đọc.

## 4. Những trường của `BasicFileAttributes`

Các method của `BasicFileAttributes` thường cần nắm:

| Method | Kiểu trả về | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `lastModifiedTime()` | `FileTime` | Thời gian sửa cuối theo metadata của provider |
| `lastAccessTime()` | `FileTime` | Thời gian truy cập; có thể có độ phân giải/hành vi khác nhau |
| `creationTime()` | `FileTime` | Thời gian tạo theo khả năng filesystem; có hệ thống không hỗ trợ độc lập |
| `size()` | `long` | Kích thước file theo metadata, không phải lúc nào cũng ý nghĩa giống nhau với directory |
| `isRegularFile()` | `boolean` | File thông thường theo view |
| `isDirectory()` | `boolean` | Directory theo view |
| `isSymbolicLink()` | `boolean` | Symbolic link nếu đọc chính entry link |
| `isOther()` | `boolean` | Các loại entry khác |
| `fileKey()` | `Object` hoặc `null` | Khóa file provider-specific; không phải ID portable |

### 4.1. `fileKey()` không phải UUID ổn định cho mọi hệ thống

`fileKey()` có kiểu `Object` và **có thể là null**. Định dạng, khả năng so sánh và tính ổn định phụ thuộc provider. Không lưu `fileKey.toString()` thành khóa định danh xuyên filesystem hoặc xuyên lần restart mà không có một contract rõ ràng.

Nếu cần xác định hai path cùng chỉ vào file theo một thao tác được hỗ trợ, cân nhắc `Files.isSameFile` và xử lý `IOException`. Ngay cả vậy, kết quả là quan sát tại thời điểm xét, không ngăn directory entry thay đổi sau đó.

### 4.2. Kích thước file khác kích thước thư mục

Với regular file, `size()` thường phản ánh số byte được ghi vào nội dung file. Với directory, size có thể mang ý nghĩa provider-specific; không dùng `attrs.size()` trên directory để suy ra tổng kích thước **toàn bộ cây con**.

Muốn tính tổng file bytes trong một cây, cần traversal (ví dụ `Files.walkFileTree`) và cộng size của **regular files** theo chính sách về symbolic links, permission, lỗi và concurrency.

### 4.3. Timestamps là metadata, không phải cơ chế audit hoàn chỉnh

`lastModifiedTime`, `lastAccessTime` và `creationTime` khác nhau về ý nghĩa; không xem chúng là lịch sử đầy đủ của mọi hành động trên file. Filesystem có thể:

- Không cập nhật access time theo từng lần đọc.
- Ghi timestamp với độ phân giải thấp hoặc làm tròn.
- Không có creation time tách biệt theo cách bạn mong đợi.
- Chịu ảnh hưởng của thao tác copy, restore hoặc chỉnh metadata thủ công.

Nếu bài toán cần audit nghiệp vụ đáng tin cậy, dùng hệ thống log/metadata có kiểm soát độc lập thay vì mặc nhiên coi timestamps trên filesystem là nguồn sự thật đầy đủ.

## 5. Đọc thuộc tính theo tên: `Files.readAttributes(Path, String, ...)`

Cách named bulk read:

```java
Map<String, Object> values = Files.readAttributes(
        path,
        "basic:size,isRegularFile,lastModifiedTime");
```

Đây là **mảnh minh họa** cần import `Map` và `Files`. Cú pháp là **một** prefix view đứng trước dấu hai chấm; phía sau là **danh sách thuộc tính** phân cách bằng dấu phẩy. Bạn không cần lặp prefix `basic:` cho từng tên trong cùng lời gọi.

Map trả về dùng **tên thuộc tính làm key**, ví dụ `"size"`, `"lastModifiedTime"`. Map **không bắt buộc bảo toàn thứ tự các key theo chuỗi request**. Nếu cần thứ tự hiển thị cố định, tự sắp xếp tên khi in.

### 5.1. Ba cách đọc theo tên

```java
Object size1 = Files.getAttribute(path, "basic:size");
Object size2 = Files.getAttribute(path, "size");

Map<String, Object> selected = Files.readAttributes(
        path, "basic:size,isRegularFile");

Map<String, Object> allBasic = Files.readAttributes(
        path, "basic:*");
```

Các đoạn trên là **mảnh minh họa**, cần `path` và import `Map`, `Files`. Trong đó:

- `getAttribute` trả về **một** giá trị `Object`.
- `readAttributes(..., "basic:size,isRegularFile")` trả map chỉ những thuộc tính chọn.
- `"basic:*"` yêu cầu nhóm thuộc tính được view hỗ trợ qua wildcard. Tập thực tế phụ thuộc view/provider; đừng coi `Map` là một schema để serialize trực tiếp bất kể hệ thống.
- Bỏ prefix trong `"size"` dùng view basic theo hợp đồng.
- View prefix phải đúng tên mà provider/view hỗ trợ; tên sai không tự suy đoán sang view khác.

### 5.2. Chương trình B — `NamedAttributesDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.Map;

public final class NamedAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-named-");
        Path file = root.resolve("sample.txt");
        try {
            Files.writeString(file, "abc", StandardCharsets.UTF_8);

            Map<String, Object> a = Files.readAttributes(file,
                    "basic:size,isRegularFile,isDirectory,lastModifiedTime");

            System.out.println("keyCount=" + a.size());
            System.out.println("namedSize=" + a.get("size"));
            System.out.println("namedRegular=" + a.get("isRegularFile"));
            System.out.println("namedDirectory=" + a.get("isDirectory"));
            System.out.println("sizeType=" +
                    a.get("size").getClass().getSimpleName());
            System.out.println("timeType=" +
                    (a.get("lastModifiedTime") instanceof FileTime));
            System.out.println("singlePrefixed=" +
                    Files.getAttribute(file, "basic:size"));
            System.out.println("singleImplicit=" +
                    Files.getAttribute(file, "size"));

            Map<String, Object> all =
                    Files.readAttributes(file, "basic:*");
            System.out.println("allHasSize=" +
                    all.containsKey("size"));
            System.out.println("allHasCreation=" +
                    all.containsKey("creationTime"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 NamedAttributesDemo.java
java NamedAttributesDemo
```

**Stdout đã kiểm chứng:**

```text
keyCount=4
namedSize=3
namedRegular=true
namedDirectory=false
sizeType=Long
timeType=true
singlePrefixed=3
singleImplicit=3
allHasSize=true
allHasCreation=true
```

### 5.3. Giải thích những điểm dễ bỏ qua

- Map có 4 key đúng theo danh sách yêu cầu.
- `size` nhận giá trị của kiểu wrapper `Long` vì Map lưu `Object`, trong khi typed `BasicFileAttributes.size()` trả kiểu nguyên thủy `long`.
- `isRegularFile` và `isDirectory` trong Map là `Boolean`.
- `lastModifiedTime` mang kiểu `FileTime`.
- `Files.getAttribute(path, "size")` có cùng nghĩa với `"basic:size"` trên provider mặc định trong ví dụ.
- Wildcard `"basic:*"` trả các thuộc tính cơ bản; kết quả minh họa chứa `size` và `creationTime`.
- In `all.keySet()` không sắp xếp có thể cho thứ tự khác trên các triển khai; bài không phụ thuộc thứ tự ấy.

**Khác biệt chính với typed access:** Với Map, compiler không biết `a.get("size")` phải là `Long`. Code phải biết contract thuộc tính khi cast/đọc giá trị. Vì vậy named API phù hợp cho chương trình muốn **lựa chọn các tên thuộc tính tại runtime**, nhưng nên xử lý type và tên sai cẩn thận.

## 6. `Files.getAttribute` và an toàn kiểu

`Files.getAttribute(path, name, options...)` trả về `Object`. Muốn sử dụng như một `long`, cần cast hoặc kiểm tra kiểu.

Ví dụ đúng:

```java
Object value = Files.getAttribute(path, "basic:size");
if (!(value instanceof Long)) {
    throw new IllegalStateException("Unexpected size type");
}
long size = (Long) value;
```

Đây là **mảnh minh họa**, với `path` có thật và đã xử lý `IOException`. Đừng cast tùy tiện `Integer` chỉ vì “size nhìn như số nguyên nhỏ”: hợp đồng của `basic:size` là `Long`.

Một sai lầm tương tự:

```java
String wrong = (String) Files.getAttribute(path, "basic:lastModifiedTime");
```

Đây là **anti-pattern**, vì thời gian sửa cuối là `FileTime`, không phải `String`. Cast sai có thể dẫn tới `ClassCastException`.

### 6.1. Khi nào chọn typed access, khi nào chọn named access?

| Hoàn cảnh | Hướng nên cân nhắc |
| --- | --- |
| Biết trước cần size, loại file và timestamp cơ bản | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Cần thay thời gian bằng API có kiểu rõ | `BasicFileAttributeView.setTimes` |
| Người dùng chọn một danh sách thuộc tính hợp lệ tại runtime | `Files.readAttributes(path, "...")` |
| Công cụ quan sát metadata hỗ trợ nhiều view khác nhau | Named API, nhưng kiểm tra view support và whitelist tên |
| Chương trình cần POSIX permissions chắc chắn khi provider hỗ trợ | `PosixFileAttributeView` hoặc `Files.getPosixFilePermissions` |
| Cần tích hợp library có phương thức nhận `String` thuộc tính | Named API, quản lý validation và kiểu dữ liệu |

**Không có quy tắc “named access luôn xấu”.** Nó là phần API chính thức, rất hữu ích cho công cụ generic. Lựa chọn dựa trên tính ổn định schema, yêu cầu chọn động và khả năng kiểm soát type.

## 7. Lấy một attribute view có kiểu

Với metadata cơ bản:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        path,
        BasicFileAttributeView.class);

BasicFileAttributes attrs = view.readAttributes();
```

Đây là mảnh minh họa, cần import `Files`, `BasicFileAttributeView`, `BasicFileAttributes` và xử lý `IOException`. `BasicFileAttributeView` có tên view là `"basic"`, và được hỗ trợ trên các filesystem implementations tuân thủ hợp đồng basic.

Các bước:

1. `getFileAttributeView` tạo view cho path và type được yêu cầu.
2. Với một view **tùy chọn**, kết quả có thể là `null` nếu provider không hỗ trợ.
3. `view.readAttributes()` mới là thao tác đọc metadata tại thời điểm gọi; tạo view object không có nghĩa file đã tồn tại hoặc dữ liệu đã được đọc.
4. `BasicFileAttributeView` còn cung cấp `setTimes(lastModified, lastAccess, creation)` để cập nhật những timestamp mà filesystem hỗ trợ.

### 7.1. Vì sao view có thể tiện khi cần nhiều thao tác?

Với một đối tượng view, code làm việc bằng method có kiểu:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        path, BasicFileAttributeView.class);
BasicFileAttributes before = view.readAttributes();
// ... xử lý dựa trên attributes ...
view.setTimes(newTime, null, null);
```

Đoạn này cần định nghĩa `path` và `newTime` kiểu `FileTime`, cũng như xử lý `IOException`. Các lệnh vẫn có thể là những thao tác I/O khác nhau; **không được hiểu “cùng một view object” là một transaction khóa metadata**. Nếu file thay đổi giữa `readAttributes` và `setTimes`, hành vi phụ thuộc filesystem.

### 7.2. View không tạo quyền truy cập bổ sung

Bạn không thể lấy `PosixFileAttributeView` rồi tự động vượt qua ACL của hệ điều hành để sửa permission. Kiểm tra view support và **quyền hiện có** là hai vấn đề khác nhau. Hệ thống có thể hỗ trợ view nhưng thao tác ghi vẫn nhận `AccessDeniedException` hoặc `IOException` khác.

## 8. Ghi thời gian sửa với `BasicFileAttributeView.setTimes`

Chữ ký:

```java
void setTimes(FileTime lastModifiedTime,
              FileTime lastAccessTime,
              FileTime createTime) throws IOException;
```

Ý nghĩa ba tham số theo thứ tự:

1. `lastModifiedTime`: thời gian sửa cuối.
2. `lastAccessTime`: thời gian truy cập cuối.
3. `createTime`: thời gian tạo.

**Truyền `null`** cho tham số nào nghĩa là không yêu cầu đổi timestamp tương ứng. Khi cả ba `null`, không có thay đổi. Đây là quy tắc của `setTimes`, **không có nghĩa `null` là giá trị timestamp cần lưu**.

Có thể lấy `FileTime` bằng `FileTime.fromMillis(...)` hoặc từ các đối tượng thời gian thích hợp. Nên dùng số millisecond chuẩn UTC từ epoch trong test để tránh phụ thuộc múi giờ/local formatter khi so kết quả.

### 8.1. Chương trình C — `TypedViewWriteDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;

public final class TypedViewWriteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-view-");
        Path file = root.resolve("sample.txt");
        try {
            Files.createFile(file);
            BasicFileAttributeView view = Files.getFileAttributeView(
                    file, BasicFileAttributeView.class);

            FileTime value = FileTime.fromMillis(1704067200000L);
            view.setTimes(value, null, null);
            BasicFileAttributes a = view.readAttributes();

            System.out.println("viewName=" + view.name());
            System.out.println("firstTime=" +
                    a.lastModifiedTime().toMillis());
            System.out.println("sameViaFiles=" +
                    (Files.readAttributes(file, BasicFileAttributes.class)
                            .lastModifiedTime().toMillis()
                    == a.lastModifiedTime().toMillis()));
            System.out.println("sizeStillZero=" +
                    (a.size() == 0L));
            System.out.println("getTimeEqual=" +
                    Files.getLastModifiedTime(file)
                            .equals(a.lastModifiedTime()));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 TypedViewWriteDemo.java
java TypedViewWriteDemo
```

**Stdout trên Windows/JDK đã thử:**

```text
viewName=basic
firstTime=1704067200000
sameViaFiles=true
sizeStillZero=true
getTimeEqual=true
```

### 8.2. Giải thích

- `view.name()` trả `"basic"` theo giao diện.
- `FileTime.fromMillis(1704067200000L)` tương ứng một instant xác định, không phụ thuộc việc in giờ địa phương.
- `view.setTimes(value, null, null)` yêu cầu sửa riêng `lastModifiedTime`.
- Đọc lại bằng `view.readAttributes()` cho timestamp đã đặt trong filesystem kiểm thử.
- Lệnh đọc độc lập qua `Files.readAttributes(file, BasicFileAttributes.class)` cho cùng số millisecond vì file không bị bên ngoài thay đổi giữa các lần đọc trong test.
- File vẫn rỗng: **sửa metadata time không tự tạo nội dung**.

### 8.3. Không cam kết độ chính xác mọi filesystem

Java API nêu rõ timestamps được chuyển sang **precision/range mà filesystem hỗ trợ**, có thể mất độ chính xác nếu timestamp được ghi với granularity thô hơn. Một filesystem có thể làm tròn hoặc không hỗ trợ thay đổi một timestamp nào đó theo cách mong đợi.

Do đó:

- **Không** viết test portable buộc `actual.equals(requested)` với một giá trị có nanoseconds lẻ tùy ý.
- Với timestamp nằm trong phạm vi hỗ trợ, có thể chọn giá trị tròn giây để tăng độ ổn định của ví dụ.
- Nếu ứng dụng cần so chính xác theo yêu cầu, phải kiểm tra khả năng filesystem/format mục tiêu.
- `setTimes` có thể không atomic với thao tác khác: implementation có thể cần đọc rồi ghi lại một số timestamps khi chỉ cập nhật một trường.
- Không coi cập nhật last modified time thành cách bảo vệ dữ liệu khỏi sửa đổi hoặc thay thế.

### 8.4. Ba tham số `FileTime` có thứ tự cố định

Rất dễ nhầm `setTimes(lastModifiedTime, lastAccessTime, createTime)` thành `setTimes(creationTime, lastModifiedTime, lastAccessTime)`. Compiler không bắt được lỗi nếu cả ba cùng kiểu `FileTime`, vì vậy kiểm tra chính xác thứ tự tham số trong code review.

Khi chỉ sửa một trường, viết `view.setTimes(newModifiedTime, null, null)` vừa rõ vừa tránh đổi các timestamp khác không cần thiết.

## 9. Ghi theo tên bằng `Files.setAttribute`

Cách dynamic:

```java
Files.setAttribute(
        path,
        "basic:lastModifiedTime",
        FileTime.fromMillis(1704153600000L));
```

Đây là **mảnh minh họa**, cần import `Files` và `FileTime`, cùng xử lý `IOException`. `Files.setAttribute` nhận `Object`, nên bạn phải truyền **đúng kiểu giá trị** theo hợp đồng của attribute, không phải chuỗi thời gian tùy ý.

Ví dụ sai:

```java
Files.setAttribute(path, "basic:lastModifiedTime", "2024-01-02");
```

Đây là **anti-pattern**, vì thuộc tính `basic:lastModifiedTime` mong `FileTime` chứ không phải `String`. Provider có thể ném `ClassCastException` hoặc lỗi phù hợp; không tự đoán kiểu.

### 9.1. `Files.setLastModifiedTime` là shortcut có kiểu

Khi chỉ đổi thời gian sửa cuối, `Files.setLastModifiedTime(file, time)` biểu đạt trực tiếp hơn việc dùng chuỗi tên metadata. API này cũng có từ Java 7 và vẫn dùng được.

Lựa chọn:

- Chỉ cần `lastModifiedTime`: `Files.setLastModifiedTime(path, time)`.
- Cần thay một hoặc nhiều times trong cùng view: `BasicFileAttributeView.setTimes`.
- Tên thuộc tính do một cơ chế cấu hình/schema lựa chọn động: `Files.setAttribute(path, "basic:lastModifiedTime", time)` với whitelist và type check.

### 9.2. Chương trình D — `NamedAttributeWriteDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.FileTime;

public final class NamedAttributeWriteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-setname-");
        Path file = root.resolve("sample.txt");
        try {
            Files.createFile(file);

            FileTime one = FileTime.fromMillis(1704153600000L);
            Files.setAttribute(file, "basic:lastModifiedTime", one);
            System.out.println("namedTime=" +
                    ((FileTime) Files.getAttribute(
                            file, "basic:lastModifiedTime")).toMillis());

            FileTime two = FileTime.fromMillis(1704240000000L);
            Files.setLastModifiedTime(file, two);
            System.out.println("typedTime=" +
                    Files.getFileAttributeView(
                            file, BasicFileAttributeView.class)
                            .readAttributes()
                            .lastModifiedTime().toMillis());

            System.out.println("filePresent=" +
                    Files.isRegularFile(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 NamedAttributeWriteDemo.java
java NamedAttributeWriteDemo
```

**Stdout đã xác minh:**

```text
namedTime=1704153600000
typedTime=1704240000000
filePresent=true
```

### 9.3. Phân tích

1. `Files.setAttribute(..., "basic:lastModifiedTime", one)` cập nhật thời gian theo tên.
2. `Files.getAttribute(..., "basic:lastModifiedTime")` trả `Object` nhưng giá trị theo contract là `FileTime`; cast rồi gọi `toMillis()`.
3. `Files.setLastModifiedTime(file, two)` cập nhật thời gian theo shortcut có kiểu.
4. `BasicFileAttributeView.readAttributes()` đọc lại kết quả sau update.
5. `filePresent=true` cho thấy thao tác update metadata không xóa file.

Các con số trên là output đã chạy trên Windows/JDK; nếu filesystem có độ phân giải khác, cần áp dụng quy tắc rounding ở mục 8.3 khi viết test portable.

## 10. Read-only và writable: không phải thuộc tính nào cũng set được

Một nhầm lẫn rất phổ biến: vì `Files.getAttribute(path, "basic:size")` trả `Long`, ta có thể gọi:

```java
Files.setAttribute(path, "basic:size", Long.valueOf(2));
```

**Sai về hợp đồng.** `basic:size` là một thuộc tính **chỉ đọc trong BasicFileAttributeView**. Độ dài file thay đổi qua I/O nội dung hoặc các API thích hợp như `SeekableByteChannel.truncate`, không phải qua `setAttribute(...,"basic:size",...)`.

Với view `basic`:

| Thuộc tính | Đọc theo tên? | Có thể yêu cầu set qua basic view? |
| --- | --- | --- |
| `lastModifiedTime` | Có | Có, qua `setTimes` / `setAttribute` |
| `lastAccessTime` | Có | Có yêu cầu; khả năng cập nhật thực phụ thuộc provider |
| `creationTime` | Có | Có yêu cầu; hỗ trợ/semantics phụ thuộc filesystem |
| `size` | Có | **Không** qua basic `setAttribute` |
| `isRegularFile` | Có | **Không** |
| `isDirectory` | Có | **Không** |
| `isSymbolicLink` | Có | **Không** |
| `isOther` | Có | **Không** |
| `fileKey` | Có | **Không** |

Cần phân biệt hai trường hợp:

- “View có operation để cập nhật timestamp” **không đồng nghĩa** mọi timestamp đều có thể chỉnh chính xác trên mọi filesystem.
- “Thuộc tính xem được” **không đồng nghĩa** “thuộc tính ghi được”.

### 10.1. Chương trình E — `InvalidAttributeDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class InvalidAttributeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-invalid-");
        Path file = root.resolve("sample.txt");
        try {
            Files.createFile(file);

            try {
                Files.getAttribute(file, "basic:notARealField");
                System.out.println("unknownAttribute=unexpected");
            } catch (IllegalArgumentException |
                    UnsupportedOperationException ex) {
                System.out.println("unknownAttributeRejected=true");
            }

            try {
                Files.setAttribute(file, "basic:size", Long.valueOf(2));
                System.out.println("readOnlyWrite=unexpected");
            } catch (IllegalArgumentException |
                    UnsupportedOperationException ex) {
                System.out.println("readOnlyWriteRejected=true");
            }

            System.out.println("sizeUnchanged=" +
                    (Files.size(file) == 0L));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InvalidAttributeDemo.java
java InvalidAttributeDemo
```

**Stdout trên filesystem kiểm thử:**

```text
unknownAttributeRejected=true
readOnlyWriteRejected=true
sizeUnchanged=true
```

### 10.2. Vì sao catch hai loại exception?

Lỗi cú pháp/tên thuộc tính không hợp lệ có thể nhận `IllegalArgumentException`; view/operation không được hỗ trợ có thể nhận `UnsupportedOperationException`. Demo gộp hai loại để minh họa “request bị từ chối” trên môi trường thử, **không cam kết mọi provider đều dùng cùng subtype cho mọi trường hợp**.

Với ứng dụng thực:

- Đừng dùng catch-all để bỏ qua lỗi cập nhật metadata quan trọng.
- Với thuộc tính không hỗ trợ, thông báo rõ nền tảng nào chưa hỗ trợ.
- Với input người dùng được phép chọn attribute name, dùng **whitelist tên** thay vì truyền chuỗi tùy ý trực tiếp.
- Chỉ đặt writable attributes mà ứng dụng có quyền chỉnh sửa.
- Không truyền sai type với hy vọng Java tự parse chuỗi thành `FileTime` hoặc set permission.

## 11. Kiểm tra hỗ trợ view: đừng giả định POSIX trên Windows

Hai API hữu ích:

```java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);
if (view != null) {
    // Provider hỗ trợ view tại path này; vẫn cần xử lý I/O/quyền.
}
```

và:

```java
FileStore store = Files.getFileStore(path);
boolean posix = store.supportsFileAttributeView("posix");
```

Đây là **mảnh minh họa**, cần import `Files`, `Path`, `PosixFileAttributeView`, `FileStore` và xử lý `IOException`. `getFileAttributeView` trả `null` nếu requested view không được provider hỗ trợ. `FileStore.supportsFileAttributeView(...)` giúp biết một file store có hỗ trợ view hay không. Hai cách bổ sung nhau; hỗ trợ ở mức store **không tự cấp quyền ghi** lên từng file.

### 11.1. Chương trình F — `OptionalViewsDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.UserDefinedFileAttributeView;

public final class OptionalViewsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-views-");
        Path file = root.resolve("sample.txt");
        try {
            Files.createFile(file);

            BasicFileAttributeView basic = Files.getFileAttributeView(
                    file, BasicFileAttributeView.class);
            PosixFileAttributeView posix = Files.getFileAttributeView(
                    file, PosixFileAttributeView.class);
            DosFileAttributeView dos = Files.getFileAttributeView(
                    file, DosFileAttributeView.class);
            AclFileAttributeView acl = Files.getFileAttributeView(
                    file, AclFileAttributeView.class);
            UserDefinedFileAttributeView user =
                    Files.getFileAttributeView(
                            file, UserDefinedFileAttributeView.class);

            System.out.println("basicAvailable=" + (basic != null));
            System.out.println("basicName=" + basic.name());
            System.out.println("posixAvailable=" + (posix != null));
            System.out.println("dosAvailable=" + (dos != null));
            System.out.println("aclAvailable=" + (acl != null));
            System.out.println("userAvailable=" + (user != null));
            System.out.println("posixOnStore=" +
                    Files.getFileStore(file)
                            .supportsFileAttributeView("posix"));
            System.out.println("dosOnStore=" +
                    Files.getFileStore(file)
                            .supportsFileAttributeView("dos"));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OptionalViewsDemo.java
java OptionalViewsDemo
```

**Stdout trên Windows/default filesystem được kiểm chứng:**

```text
basicAvailable=true
basicName=basic
posixAvailable=false
dosAvailable=true
aclAvailable=true
userAvailable=true
posixOnStore=false
dosOnStore=true
```

**Không hardcode stdout này cho mọi máy.** Trên Linux/macOS hay một file store khác, khả năng POSIX, DOS, ACL và user-defined có thể khác đáng kể. Điều cần kiểm tra là **code phát hiện hỗ trợ thay vì giả định**, còn các boolean phụ thuộc môi trường.

### 11.2. View class khác với view name

- `BasicFileAttributeView.class` là **class token** để chọn typed API.
- `"basic"` là **string view name** để dùng trong named API.
- `"basic:size"` là **string đầy đủ cho một attribute**.
- `Files.getFileAttributeView(...).name()` trả tên view, ví dụ `"basic"`.

Nếu bạn đang viết một công cụ cho phép người dùng chọn `"posix"`, không thể truyền chuỗi đó vào overload `getFileAttributeView(Path, Class<V>)`. Phải chọn một type token phù hợp, hoặc dùng named access với validation và policy thích hợp.

## 12. POSIX view: owner, group và permissions

Trên các filesystem hỗ trợ POSIX, bạn có thể lấy `PosixFileAttributeView`, đọc `PosixFileAttributes` và dùng các phương thức typed như:

- `attrs.owner()`: trả `UserPrincipal`.
- `attrs.group()`: trả `GroupPrincipal`.
- `attrs.permissions()`: trả `Set<PosixFilePermission>`.
- `view.setPermissions(perms)`: yêu cầu đặt quyền.
- `view.setOwner(principal)` và `view.setGroup(group)`: yêu cầu cập nhật chủ sở hữu/nhóm.

Lấy typed view:

```java
PosixFileAttributeView view = Files.getFileAttributeView(
        path, PosixFileAttributeView.class);
if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    System.out.println(
            PosixFilePermissions.toString(attrs.permissions()));
}
```

Đây là **mảnh minh họa chỉ chạy khi view hỗ trợ**, cần import `Files`, `Path`, `PosixFileAttributeView`, `PosixFileAttributes`, `PosixFilePermissions` và xử lý `IOException`. Trên Windows default provider trong môi trường QA, `view == null` nên code không cố đọc quyền POSIX.

### 12.1. Named access với POSIX

Nếu provider hỗ trợ:

```java
Object perms = Files.getAttribute(path, "posix:permissions");
```

Giá trị có kiểu theo hợp đồng `Set<PosixFilePermission>`, không phải chuỗi `"rwxr-x---"` trực tiếp. Muốn dùng chuỗi, hãy format bằng `PosixFilePermissions.toString(...)` sau khi đã có tập quyền typed.

### 12.2. Chỉnh quyền là thao tác bảo mật

Đừng hướng dẫn ứng dụng mở rộng `OTHERS_WRITE` hoặc cấp quyền rộng một cách vô thức chỉ để “cho ghi được”. Trong code thật:

- Xác định owner/service account và least privilege.
- Kiểm tra thư mục cha, ACL và umask/policy.
- Hạn chế thao tác chỉ trên file mà ứng dụng được ủy quyền.
- Kiểm tra kết quả sau update khi cần.
- Không cho raw client tự gửi một chuỗi `"posix:permissions"` bất kỳ để chỉnh quyền của file khác.

**Không phải mọi file store hỗ trợ POSIX đều cho phép một user sửa mọi metadata.** Khả năng API và quyền thao tác là hai tầng khác nhau.

## 13. DOS, owner, ACL và user-defined views

### 13.1. DOS attributes vẫn là một view hiện hành khi filesystem hỗ trợ

`DosFileAttributeView` truy cập các cờ như `hidden`, `readonly`, `system` và `archive`. Tên “DOS” phản ánh nguồn gốc các cờ metadata, nhưng API Java này **vẫn tồn tại và hữu dụng** với file stores hỗ trợ; không có lý do ép sử dụng nó trên mọi nền tảng.

Truy cập có điều kiện:

```java
DosFileAttributeView view = Files.getFileAttributeView(
        path, DosFileAttributeView.class);
if (view != null) {
    DosFileAttributes attrs = view.readAttributes();
    boolean hidden = attrs.isHidden();
    // Chỉ thay flag nếu nghiệp vụ được ủy quyền rõ.
}
```

Đây là mảnh minh họa, cần import `Files`, `DosFileAttributeView`, `DosFileAttributes` và xử lý `IOException`. Với named access trên provider hỗ trợ, ví dụ `Files.getAttribute(path, "dos:hidden")` trả một `Boolean`.

Cần phân biệt `dos:readonly` với permission policy tổng quát. Trên những hệ thống khác nhau, khả năng đọc/ghi còn phụ thuộc ACL, quyền trên directory và trạng thái file; **một cờ không đủ để mô hình hóa toàn bộ kiểm soát truy cập**.

### 13.2. Owner view

`FileOwnerAttributeView` cung cấp typed API `getOwner()` và `setOwner(...)` khi provider hỗ trợ. Tên người dùng và kiểu principal phụ thuộc hệ thống; không giả định một path của Windows có owner/group dưới cùng mô hình với Linux.

Khi chỉ cần biết owner trong chương trình được phép đọc, có thể cân nhắc `Files.getOwner(path)`. Nếu cần cập nhật owner, phải có quyền hệ điều hành thích hợp. **Không thay owner của file ngẫu nhiên chỉ để kiểm tra API.**

### 13.3. ACL view

`AclFileAttributeView` cung cấp quyền chi tiết theo các ACL entries trên các filesystem hỗ trợ. ACL không phải chỉ một chuỗi `"rwx"`; nó có cấu trúc entry, principal, type, flags và permissions riêng.

Thao tác đổi ACL có thể ảnh hưởng bảo mật thực tế. Trong một bài học về truy cập thuộc tính, nên biết view tồn tại và cách phát hiện support, nhưng **không áp đặt một ACL mẫu không hiểu cấu hình hệ thống**.

### 13.4. User-defined attributes

`UserDefinedFileAttributeView` cho phép truy cập một số metadata tùy biến theo tên và dữ liệu byte, nếu filesystem/provider hỗ trợ. Nó có các API kiểu `list()`, `size(name)`, `read(name, ByteBuffer)` và `write(name, ByteBuffer)`.

Đây **không phải giải pháp portable để lưu mọi loại metadata**: nếu file được copy sang file store khác, metadata tùy biến có thể mất hoặc không thể ghi. Cần có data model và persistence contract rõ ràng.

## 14. Symbolic link và `NOFOLLOW_LINKS`

Đọc attributes của symbolic link có hai ý nghĩa:

1. **Theo link (mặc định):** đọc thuộc tính của target cuối nếu link trỏ hợp lệ.
2. **Không theo link:** đọc thuộc tính của **chính entry link**, dùng `LinkOption.NOFOLLOW_LINKS`.

Ví dụ:

```java
BasicFileAttributes targetAttrs = Files.readAttributes(
        link, BasicFileAttributes.class);

BasicFileAttributes linkAttrs = Files.readAttributes(
        link, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là **mảnh minh họa**, `link` cần là Path trỏ đến symbolic link và filesystem hỗ trợ. Nếu target là regular file, `targetAttrs.isRegularFile()` có thể true; nếu đọc chính link bằng NOFOLLOW, `linkAttrs.isSymbolicLink()` có thể true.

### 14.1. Named access cũng nhận `LinkOption`

```java
Object sizeOfEntry = Files.getAttribute(
        link, "basic:size", LinkOption.NOFOLLOW_LINKS);
```

Với symbolic link, giá trị size có thể nói về **entry link**, không phải kích thước nội dung target, và cách filesystem báo cáo phụ thuộc provider. Đừng so sánh hai số size với giả định chúng luôn bằng nhau.

Tương tự, `Files.setAttribute(link, "basic:lastModifiedTime", time, LinkOption.NOFOLLOW_LINKS)` yêu cầu thao tác trên chính link. **Provider có thể không hỗ trợ cập nhật timestamp của link**, nên cần xử lý lỗi và không coi flag NOFOLLOW thành bảo đảm việc ghi sẽ thành công.

### 14.2. Chương trình G — `SymbolicLinkAttributesDemo.java`

Tạo symbolic link có thể yêu cầu quyền hoặc cấu hình đặc biệt trên một số hệ thống, đặc biệt Windows. Ví dụ này được thiết kế **thử có điều kiện**; không xóa target ngoài thư mục tạm.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class SymbolicLinkAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("attributes-link-");
        Path target = root.resolve("target.txt");
        Path link = root.resolve("shortcut.txt");
        try {
            Files.createFile(target);
            try {
                Files.createSymbolicLink(link, target.getFileName());
                BasicFileAttributes following = Files.readAttributes(
                        link, BasicFileAttributes.class);
                BasicFileAttributes itself = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

                System.out.println("linkCreated=true");
                System.out.println("followsRegular=" +
                        following.isRegularFile());
                System.out.println("noFollowLink=" +
                        itself.isSymbolicLink());
                System.out.println("targetStillExists=" +
                        Files.exists(target));
            } catch (UnsupportedOperationException |
                     SecurityException | IOException ex) {
                System.out.println("linkCreated=false");
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SymbolicLinkAttributesDemo.java
java SymbolicLinkAttributesDemo
```

**Stdout trên Windows/JDK trong môi trường kiểm thử:**

```text
linkCreated=false
```

Trong môi trường **hỗ trợ tạo và đọc symbolic links**, nhánh thành công dự kiến:

```text
linkCreated=true
followsRegular=true
noFollowLink=true
targetStillExists=true
```

**Cần diễn giải chính xác:** `linkCreated=false` ở máy kiểm thử chỉ cho biết thao tác tạo/đọc link được thử trong khối `try` đã gặp một ngoại lệ mà ví dụ bắt; không kết luận mọi Windows đều không hỗ trợ symlink. Để chẩn đoán production, cần phân biệt lỗi cụ thể thay vì gộp như ví dụ ngắn.

### 14.3. Dangling link làm phép kiểm tra `Files.exists` dễ gây nhầm

Khi target của symbolic link đã biến mất, `Files.exists(link)` theo mặc định có thể trả false dù **bản thân link entry** vẫn tồn tại. Nếu muốn kiểm tra link entry, dùng `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` hoặc đọc attributes với NOFOLLOW và xử lý lỗi.

Đọc chính link **không phải** truy cập nội dung target. Không tự mở target dựa trên metadata mà không xét symlink và quyền truy cập.

## 15. `FileTime`: loại dữ liệu và độ chính xác

`FileTime` là biểu diễn timestamp phù hợp với metadata filesystem. Nó có thể được tạo từ một giá trị epoch hoặc chuyển sang đơn vị thích hợp:

```java
FileTime target = FileTime.fromMillis(1704067200000L);
long millis = target.toMillis();
```

Đây là **mảnh minh họa**, cần import `java.nio.file.attribute.FileTime`. Giá trị epoch không phải một chuỗi múi giờ địa phương; khi cần hiển thị, chuyển sang kiểu thời gian và timezone phù hợp.

### 15.1. Đọc theo tên trả `FileTime`, không phải String

`Files.getAttribute(path, "basic:lastModifiedTime")` có contract trả `FileTime` được bọc trong `Object`. Bạn không thể cast thẳng thành `String`. Muốn in human-readable time, định nghĩa formatter/tz riêng ở presentation layer.

### 15.2. Không thiết kế test đòi timestamp nanoseconds chính xác mọi filesystem

Filesystem có granularity và range khác nhau. Ví dụ dùng các mốc nguyên giây để tăng độ ổn định, nhưng ngay cả thế cũng không biến mọi provider thành một nền tảng có time resolution hoàn hảo.

Những ngoại lệ cần nghĩ tới:

- Update timestamp có thể bị làm tròn.
- Metadata thời gian tạo có thể không được hỗ trợ theo nghĩa native.
- Access time có thể không thay đổi cho mỗi lần đọc do policy hiệu năng.
- Metadata có thể bị process khác cập nhật giữa read và write.
- Sao chép file có thể có policy copy attributes riêng.
- `FileTime.toMillis()` làm tròn/giới hạn độ chính xác so với giá trị có độ phân giải cao hơn.

Nếu hệ thống dùng timestamp để quyết định đồng bộ hoặc cache invalidation, hãy xét hành vi đồng hồ, độ phân giải, thay đổi mtime thủ công và các dấu hiệu khác như content digest hoặc version ID khi cần.

## 16. Đọc nhiều thuộc tính không có nghĩa lấy snapshot atomic

Cả typed bulk read:

```java
BasicFileAttributes a = Files.readAttributes(
        path, BasicFileAttributes.class);
```

và named bulk read:

```java
Map<String, Object> m = Files.readAttributes(
        path, "basic:size,lastModifiedTime");
```

đều tránh việc mỗi thuộc tính phải được đọc bằng một API riêng trong code. Đây là lợi ích hiệu năng và tính rõ ràng. Tuy nhiên, tài liệu Java nêu việc **mọi thuộc tính có được lấy nguyên tử so với các hoạt động filesystem khác hay không là implementation-specific**.

Đặc biệt, mẫu:

```java
long size = (Long) Files.getAttribute(path, "basic:size");
FileTime time = (FileTime) Files.getAttribute(
        path, "basic:lastModifiedTime");
```

dễ dẫn tới việc file thay đổi giữa hai lần I/O. Bulk read có thể tốt hơn khi cần một nhóm metadata nhất quán về thời điểm, **nhưng không được coi là transaction snapshot được bảo đảm**.

### 16.1. Đọc rồi ghi không phải compare-and-set

Giả sử bạn đọc mtime, quyết định mtime “cũ”, rồi gọi `Files.setAttribute(...,"basic:lastModifiedTime",...)`. Một process khác có thể sửa file giữa hai bước. Java không cung cấp một CAS mặc định trên các tên thuộc tính kiểu `basic:...`.

Nếu app cần đồng bộ hóa dưới concurrency, dùng cơ chế locking/versioning/transaction ở tầng thích hợp và **không suy từ một attribute view object rằng nó khóa file**.

## 17. Các lỗi và ngoại lệ khi đọc/ghi attributes

| Trường hợp | Exception/hiện tượng có thể gặp | Cách xử lý |
| --- | --- | --- |
| Path không tồn tại | `NoSuchFileException` hoặc `IOException` | Xác minh path và contract; không lặng lẽ tạo file nếu chỉ được phép đọc |
| Thiếu quyền đọc metadata | `AccessDeniedException` / `IOException` | Kiểm tra account, permission, ACL |
| View không được hỗ trợ | `UnsupportedOperationException` hoặc view trả `null` | Kiểm tra support và dùng phương án portable |
| Tên attribute không hợp lệ | `IllegalArgumentException` | Whitelist và sửa tên |
| Giá trị sai kiểu khi set | `ClassCastException`/lỗi phù hợp | Chuyển giá trị sang kiểu contract thực |
| Thuộc tính chỉ đọc bị set | `IllegalArgumentException`/`UnsupportedOperationException` hoặc lỗi provider | Không dùng `setAttribute` cho read-only |
| Timestamp ngoài precision/range | Có thể làm tròn, không có hiệu lực hoặc lỗi I/O | Kiểm tra sau ghi, không đòi exact vô điều kiện |
| Symlink target biến mất | Lỗi đọc khi follow; NOFOLLOW có thể đọc link entry | Quyết định cần metadata target hay link |
| File bị đổi/xóa giữa các bước | Kết quả lỗi hoặc đã lỗi thời | Xử lý race, không giả định snapshot |
| Không cho phép đổi owner/permissions | `AccessDeniedException` / `IOException` / security error | Không vượt quyền; báo rõ thiếu quyền |

### 17.1. Không dùng catch-all để làm giả dữ liệu

Anti-pattern:

```java
long size;
try {
    size = (Long) Files.getAttribute(path, "basic:size");
} catch (Exception ignored) {
    size = 0L;
}
```

Đây là **mảnh minh họa không nên dùng**. Một file không đọc được metadata **không đồng nghĩa file rỗng**. `0L` có thể làm sai nghiệp vụ, báo cáo, đồng bộ hoặc quyết định bảo mật.

Thay vào đó, xác định rõ:

- Việc không đọc được metadata có làm operation thất bại không?
- Nếu có thể bỏ qua entry, kết quả báo cáo có ghi rõ rằng **không đầy đủ** không?
- Có cần phân loại thiếu file, thiếu quyền hay không hỗ trợ view?
- Có cần propagate cause tới một exception ở service boundary?

### 17.2. Tránh tự xử lý I/O như một lỗi cú pháp

Một named key sai như `"basic:notARealField"` có thể báo `IllegalArgumentException`, trong khi thiếu quyền đọc một named key đúng có thể báo `IOException`. Không gộp chúng thành “thuộc tính không có” vì nguyên nhân sửa lỗi khác nhau.

## 18. Thuộc tính thiết lập **khi tạo** khác update **sau khi tạo**

Bài đang nói tới **đọc/ghi attributes của file hiện hữu**. NIO.2 còn có `FileAttribute<T>` để truyền attributes khi tạo file/directory:

```java
Files.createFile(path, attrs);
Files.createDirectory(directory, attrs);
```

Đây là các chữ ký minh họa (không phải chương trình hoàn chỉnh). Với POSIX filesystem, bạn có thể dùng `PosixFilePermissions.asFileAttribute(perms)` khi cần đặt quyền trong lúc tạo, nếu provider hỗ trợ.

Vì sao phân biệt?

- **Create-time attributes:** Yêu cầu thiết lập cùng thao tác tạo đối tượng theo khả năng provider, giúp tránh một số cửa sổ thời gian “tạo file với quyền mặc định rồi mới sửa quyền”.
- **Update attributes:** `Files.setAttribute` hoặc `FileAttributeView` sửa metadata của đối tượng đã tồn tại; giữa lúc tạo và lúc update có thể có cơ hội truy cập khác.

### 18.1. Ví dụ POSIX có điều kiện

```java
Set<PosixFilePermission> perms =
        PosixFilePermissions.fromString("rw-------");
FileAttribute<Set<PosixFilePermission>> attr =
        PosixFilePermissions.asFileAttribute(perms);
Files.createFile(path, attr);
```

Đây là **mảnh minh họa chỉ dành cho provider hỗ trợ POSIX**, cần import `Set`, `PosixFilePermission`, `PosixFilePermissions`, `FileAttribute` và `Files`, và `path` phải chưa tồn tại. Không chạy mù quáng với default filesystem Windows hoặc thư mục nhạy cảm.

Thực tế permission có thể bị giới hạn thêm bởi umask hoặc policy của filesystem. **Chỉ hỗ trợ view không có nghĩa process có quyền thiết lập mọi thuộc tính như yêu cầu.**

## 19. Chọn API theo cấu trúc code

Một số quy tắc thực hành:

### 19.1. Ứng dụng nghiệp vụ biết rõ thuộc tính cần dùng

Ưu tiên typed:

```java
BasicFileAttributes attrs = Files.readAttributes(
        file, BasicFileAttributes.class);

if (attrs.isRegularFile() && attrs.size() > 1024L) {
    // Xử lý theo nghiệp vụ.
}
```

Đây là **mảnh minh họa**, cần định nghĩa `file`, import các type và xử lý `IOException`. Compiler giúp bạn với `long`/`boolean` và tránh typo tên string.

### 19.2. Công cụ thống kê cấu hình được danh sách thuộc tính

Dùng named list:

```java
Map<String, Object> values = Files.readAttributes(
        file, "basic:size,isRegularFile,lastModifiedTime");
```

Nhưng không nên nhận thẳng một chuỗi attribute names từ request khách hàng mà không có policy. Danh sách tên nên được **whitelist**, và việc truy vấn owner/ACL có thể tiết lộ thông tin hệ thống mà client không cần biết.

### 19.3. Công cụ cập nhật một timestamp

Chọn shortcut:

```java
Files.setLastModifiedTime(file, newTime);
```

Vì nó cụ thể, có kiểu rõ ràng và dễ review. Dùng `BasicFileAttributeView.setTimes` nếu cần nhiều timestamp; dùng `Files.setAttribute` nếu thực sự cần dispatch theo tên.

### 19.4. Công cụ làm việc với nhiều filesystem providers

Phải có branch kiểm tra support:

```java
PosixFileAttributeView posix = Files.getFileAttributeView(
        file, PosixFileAttributeView.class);
if (posix != null) {
    // Xử lý POSIX metadata.
} else {
    // Fallback hoặc báo view không hỗ trợ.
}
```

Đây là **mảnh minh họa**; đừng chọn một fallback **bịa metadata** chỉ để JSON đầu ra đủ các key.

## 20. Một case study: thống kê file và cập nhật mtime của kết quả export

Một tác vụ export có thể tạo `report.csv`, ghi nội dung, rồi lưu mtime theo một instant đã được nghiệp vụ chỉ định.

Quy trình nên tách:

1. Chọn directory an toàn và có quyền ghi.
2. Tạo hoặc mở file đúng contract không ghi đè ngoài ý muốn.
3. Ghi nội dung qua charset/byte API phù hợp.
4. Đóng resource; biết I/O đã thành công hay thất bại.
5. Gọi `Files.readAttributes(file, BasicFileAttributes.class)` để xác minh loại và kích thước.
6. Nếu nghiệp vụ cần, cập nhật `lastModifiedTime` bằng `Files.setLastModifiedTime`.
7. Đọc lại thuộc tính, xét precision policy.
8. Không lấy mtime làm chứng cứ file đã được ghi bền vững hoặc nội dung đúng; nếu cần integrity, xác minh bằng hash/checksum/protocol.

### 20.1. Vì sao không dùng mtime làm checksum?

Hai file khác nội dung vẫn có thể trùng mtime; một file có thể bị sửa metadata time mà không sửa content. Filesystem cũng có granularity, timestamp behavior và độ trễ khác nhau. Nếu cần xác thực nội dung, phải dựa vào dữ liệu/file digest cùng contract phù hợp chứ không dùng mỗi `lastModifiedTime`.

### 20.2. Khi nào nên lưu metadata ngoài filesystem?

Nếu nghiệp vụ cần mô tả tùy chỉnh, lịch sử duyệt, trạng thái workflow hoặc quyền application-level, metadata trong database/manifest riêng có thể phù hợp hơn. Không dựa vào `UserDefinedFileAttributeView` như một nơi lưu dữ liệu chắc chắn có trên mọi ổ đĩa/provider hoặc tồn tại qua mọi thao tác copy.

## 21. Metadata và an toàn dữ liệu

### 21.1. Không nhận raw path + attribute name bất kỳ từ client

Một API kiểu:

```text
POST /set-attribute
path=/sensitive/file
name=posix:permissions
value=...
```

là thiết kế nguy hiểm nếu client có thể tự chọn path/attribute. Nó có thể cho phép đổi permission, hidden flag, owner, ACL hoặc metadata ở ngoài phạm vi.

Nên:

- Xác thực resource ID và quyền của caller.
- Chọn path từ một directory/base do service quản lý.
- Chỉ cho phép một **whitelist attribute names** thật sự cần.
- Kiểm tra đúng kiểu giá trị.
- Ngăn path traversal theo threat model, xử lý symbolic link/TOCTOU và file identity.
- Sử dụng service account với least privilege.
- Ghi audit cho update nhạy cảm, không log dữ liệu bí mật không cần thiết.
- Không báo thành công trước khi provider hoàn thành thao tác và trạng thái đạt contract.

### 21.2. `NOFOLLOW_LINKS` không phải cờ bảo mật tuyệt đối

Khi đọc metadata của chính link entry, NOFOLLOW giúp phân biệt link và target. Nhưng nó không tự đảm bảo directory cha không bị thay thế bởi symlink giữa các bước, không tạo một sandbox filesystem, và không nâng quyền truy cập.

Với file paths do người dùng cung cấp, cần thiết kế confinement/permission và file operations đáng tin cậy theo nền tảng thay vì chỉ thêm `NOFOLLOW_LINKS` rồi coi như an toàn.

### 21.3. Attribute views không phải lớp authorization riêng

Java interface chỉ mô tả cách truy vấn/cập nhật metadata khi được phép. File-owner view không tự cấp quyền đổi owner; ACL view không tự cho quyền sửa ACL; POSIX view không tự mở khóa file read-only.

Có thể có view hỗ trợ nhưng `AccessDeniedException` khi cập nhật. Code phải phân biệt "không hỗ trợ" với "có hỗ trợ nhưng không được phép".

## 22. Ma trận kiểm thử

| Bài thử | API | Kết quả đáng kiểm |
| --- | --- | --- |
| Regular file `"abc"` | `Files.readAttributes(..., BasicFileAttributes.class)` | `size=3`, `isRegularFile=true` |
| Directory tạm | Typed basic attrs | `isDirectory=true` |
| Basic named list | `Files.readAttributes(file,"basic:size,isRegularFile")` | Map có key typed `Long`, `Boolean` |
| Single named attr | `Files.getAttribute(file,"basic:size")` | Trả `Object` chứa `Long` |
| Prefix mặc định | `Files.getAttribute(file,"size")` | Dùng basic view |
| Wildcard | `Files.readAttributes(file,"basic:*")` | Map các thuộc tính basic khả dụng |
| Typed view | `Files.getFileAttributeView(file,BasicFileAttributeView.class)` | View `name()="basic"` |
| Ghi time typed | `view.setTimes(t,null,null)` | Đọc lại lastModifiedTime theo precision |
| Ghi time named | `Files.setAttribute(file,"basic:lastModifiedTime",t)` | Đọc lại `FileTime` |
| Shortcut typed | `Files.setLastModifiedTime(file,t)` | Thay đổi mtime theo provider |
| Tên attr không tồn tại | `getAttribute(...,"basic:notARealField")` | Báo request không hợp lệ |
| Ghi `size` qua basic | `setAttribute(...,"basic:size",...)` | Bị từ chối vì read-only |
| POSIX view không hỗ trợ | `getFileAttributeView(...,PosixFileAttributeView.class)` | `null` hoặc hỗ trợ tùy provider |
| DOS view | `getFileAttributeView(...,DosFileAttributeView.class)` | Có/không theo provider |
| Follow symbolic link | Typed/named read mặc định | Đọc target khi target hợp lệ |
| NOFOLLOW symbolic link | Thêm `LinkOption.NOFOLLOW_LINKS` | Đọc chính link entry nếu hỗ trợ |
| Missing path | Read metadata | `IOException`, subtype có thể khác |
| Không có quyền | Get/set attributes | Lỗi quyền/I/O, không được giả định success |
| Concurrent modification | Hai lần get metadata | Không bảo đảm cùng snapshot/giá trị |

### 22.1. Bộ test portable cần tránh điều gì?

- In absolute path thư mục tạm chứa tên ngẫu nhiên rồi hardcode expected output.
- In timestamp theo timezone hệ điều hành rồi so với chuỗi ngày giờ cố định.
- Assert POSIX/DOS/ACL/user view đều có trên mọi máy.
- Tạo symbolic link mà không xét quyền provider.
- Bắt buộc timestamp nanosecond chính xác trên mọi file store.
- Nghĩ `readAttributes` là một transaction snapshot atomic.
- Bỏ qua cleanup của file tạm.
- Chạy thử update owner/ACL/permission trên file người dùng thật.

### 22.2. Tại sao không nên so fileKey giữa hai máy?

`fileKey` provider-specific; ngay cả khi có giá trị khác null, nó không nhất thiết có định dạng hoặc ý nghĩa giống nhau giữa hai filesystem. Test về file identity nên xác định rõ contract và môi trường, không dựa vào `fileKey.toString()` toàn cục.

## 23. Bài tập tự luyện

**Bài 1 — Hai phương pháp.** So sánh `Files.getAttribute(file,"basic:size")` với `Files.readAttributes(file,BasicFileAttributes.class).size()`. Kiểu trả về của hai cách khác nhau thế nào?

**Bài 2 — Attribute map.** Đọc cùng lúc `size`, `lastModifiedTime`, `isRegularFile` bằng named bulk read. Giải thích các kiểu `Long`, `FileTime`, `Boolean` và vì sao phải dùng key đúng tên.

**Bài 3 — Wildcard.** Chạy `Files.readAttributes(file,"basic:*")` trên temp file. Duyệt từng entry của Map, in key và Java type của value, nhưng không hardcode thứ tự key.

**Bài 4 — Typed view.** Lấy `BasicFileAttributeView`, gọi `name()` và `readAttributes()`. So kết quả với `Files.readAttributes(file,BasicFileAttributes.class)`.

**Bài 5 — Thời gian.** Tạo temp file, đặt lastModifiedTime bằng `view.setTimes(t,null,null)`. Dùng `Files.getLastModifiedTime` để kiểm tra, chú ý precision.

**Bài 6 — Ghi theo tên.** Thay `Files.setLastModifiedTime(file,t)` bằng `Files.setAttribute(file,"basic:lastModifiedTime",t)`. Kiểu của `t` phải là gì?

**Bài 7 — Read-only.** Thử `Files.setAttribute(file,"basic:size",Long.valueOf(10L))`. Vì sao API từ chối mặc dù `size` đọc được?

**Bài 8 — Tên sai.** Gọi `Files.getAttribute(file,"basic:unknownField")`. Giải thích sự khác nhau giữa lỗi tên thuộc tính và lỗi không có quyền.

**Bài 9 — POSIX view.** Viết một hàm kiểm tra `PosixFileAttributeView` có được hỗ trợ không; chỉ khi có mới đọc `permissions`. Trên Windows default provider có thể nhận kết quả nào?

**Bài 10 — DOS view.** Kiểm tra `DosFileAttributeView`. Nếu hỗ trợ, đọc `attrs.isHidden()`; không kết luận bit này tự biểu diễn toàn bộ quyền truy cập.

**Bài 11 — Symlink.** Trên filesystem cho phép tạo symlink, so `Files.readAttributes(link,BasicFileAttributes.class)` với overload có `NOFOLLOW_LINKS`.

**Bài 12 — Missing target.** Khi đọc thuộc tính file không tồn tại, phải xử lý ra sao? Có nên trả `size=0` như thể đó là file rỗng không?

**Bài 13 — Creation time.** Tại sao không nên viết test bắt buộc `creationTime` thay đổi được một cách chính xác trên mọi OS/filesystem?

**Bài 14 — Snapshot.** Một process đọc `size`, sau đó đọc `lastModifiedTime` trong hai lời gọi. Nếu process khác ghi file giữa hai lần, điều gì có thể xảy ra? Bulk read có bảo đảm atomic snapshot không?

**Bài 15 — Security.** Một API cho phép client gửi `"posix:permissions"` và một đường dẫn tùy ý. Hãy chỉ ra nguy cơ và đề xuất kiểm soát.

**Bài 16 — Create vs update.** Nếu cần tạo file với POSIX permission chặt từ đầu, tại sao `FileAttribute<?>` lúc tạo có thể tốt hơn tạo xong mới sửa quyền?

**Bài 17 — Data integrity.** Vì sao `lastModifiedTime` không thay được checksum của file?

**Bài 18 — Cross-platform.** Nếu một chương trình dùng `Files.getPosixFilePermissions` không guard trên Windows, bạn sẽ thay đổi thiết kế như thế nào để code hoạt động hoặc báo rõ không hỗ trợ?

### Đáp án gợi ý ngắn

- **Bài 1:** Named trả `Object` chứa `Long`; typed trả `long`.
- **Bài 2:** Map lưu key/value động, mỗi attribute có type contract riêng.
- **Bài 3:** `"basic:*"` yêu cầu các basic fields khả dụng; thứ tự Map không được giả định.
- **Bài 4:** Hai API truy cập nhóm basic metadata; view còn có `setTimes`.
- **Bài 5:** Dùng `FileTime` và kiểm tra sau ghi theo granularity provider.
- **Bài 6:** `t` là `FileTime`.
- **Bài 7:** `size` là basic attribute read-only.
- **Bài 8:** Tên sai là lỗi request/API; thiếu quyền là vấn đề authorization/I/O.
- **Bài 9:** Nếu view không hỗ trợ, có thể nhận `null`; không cố gọi view methods.
- **Bài 10:** Hidden flag là metadata, không phải security policy tổng quát.
- **Bài 11:** Mặc định follow target, NOFOLLOW đọc chính entry link.
- **Bài 12:** Xử lý lỗi theo contract; không biến thiếu file thành size=0.
- **Bài 13:** Creation time phụ thuộc filesystem; setTimes có thể không giữ đúng precision/range.
- **Bài 14:** Không có bảo đảm snapshot atomic; cần kiểm soát concurrency riêng.
- **Bài 15:** Whitelist, xác thực quyền, giới hạn path, least privilege và chống race.
- **Bài 16:** Giúp hạn chế cửa sổ quyền mở rộng giữa create và metadata update.
- **Bài 17:** Mtime có thể trùng hoặc bị thay mà content khác.
- **Bài 18:** Phát hiện view support và dùng fallback/diagnostic rõ.

## 24. Những lỗi sai phổ biến

### 24.1. Cho rằng `Files.readAttributes` luôn trả Map

Có **hai overload**: nhận `Class<A>` trả đối tượng typed, còn nhận `String` trả `Map<String,Object>`. Khi review code, đọc đúng overload được gọi.

### 24.2. Nhầm `BasicFileAttributes` và `BasicFileAttributeView`

Một bên là kết quả metadata typed, bên kia là interface có method đọc/ghi. `attrs.setTimes(...)` không tồn tại trên `BasicFileAttributes`.

### 24.3. Cast giá trị named attribute sai type

`basic:size` là `Long`, `basic:lastModifiedTime` là `FileTime`. Đừng cast thành `Integer` hoặc `String` vì nhìn đơn giản.

### 24.4. Ghi được mọi thứ vì `setAttribute` nhận Object

Sai. Tham số `Object` chỉ giúp API nhận nhiều kiểu giá trị theo tên; nó **không biến read-only attributes thành writable**.

### 24.5. Quên prefix rồi tưởng API tự chọn POSIX

Khi bỏ prefix, view mặc định là `basic`, không phải một view nào đó tự động được suy từ tên attribute. Muốn quyền POSIX, dùng `posix:permissions` và kiểm tra support.

### 24.6. Hardcode `PosixFileAttributes` trên Windows

POSIX là optional view. Trên provider không hỗ trợ, phải có branch/fallback, không áp đặt giả định mọi OS hỗ trợ.

### 24.7. Tưởng `FileStore.supportsFileAttributeView` nghĩa là có quyền ghi

View support không phải authorization. Có hỗ trợ vẫn có thể bị từ chối do permission.

### 24.8. Lấy `fileKey().toString()` để lưu làm ID toàn cục

`fileKey` có thể null và implementation-specific. Không coi nó là UUID.

### 24.9. Coi `BasicFileAttributes.size()` là số byte toàn bộ cây directory

Size của directory không phải tổng các file con. Muốn tổng file size, traversal có chính sách riêng.

### 24.10. Coi `readAttributes` là atomic snapshot

Bulk read không được Java bảo đảm atomic với filesystem operations khác. Dữ liệu có thể thay đổi.

### 24.11. So timestamp độ phân giải nanosecond chính xác trên mọi file store

Granularity khác nhau; cần so với tolerance/quy tắc provider phù hợp.

### 24.12. Dùng `creationTime` như timestamp luôn ghi được

Không phải mọi filesystem hỗ trợ cập nhật creation time theo cùng cách. Phải kiểm tra provider, không đoán.

### 24.13. Nhầm metadata của link với target

Mặc định theo symbolic link; `NOFOLLOW_LINKS` khi cần đọc entry link. Cả hai có ý nghĩa khác nhau.

### 24.14. Nghĩ NOFOLLOW_LINKS loại mọi path traversal và symlink race

Không. Nó là một lựa chọn của thao tác đọc/ghi link, không phải sandbox security boundary.

### 24.15. Dùng `Files.isWritable` như chứng cứ cập nhật attribute chắc chắn thành công

Quyền cập nhật metadata khác nhau theo ACL/ownership và provider. Hãy gọi thao tác được phép và xử lý ngoại lệ.

### 24.16. Cho rằng lastModifiedTime là dấu xác thực content

Mtime không thay thế hash, version hoặc audit log.

### 24.17. Dùng named wildcard như một schema ổn định để serialize qua mạng

Tập metadata hỗ trợ phụ thuộc provider. Để tạo API JSON ổn định, hãy định nghĩa schema, chuẩn hóa type/time/optional fields và privacy policy riêng.

### 24.18. Bỏ qua exception khi set permissions vì nghĩ chỉ là metadata

Permission/owner/ACL là yếu tố bảo mật thực tế. Xử lý thất bại một cách rõ ràng, không báo success giả.

## 25. Checklist khi áp dụng vào dự án

- [ ] Phân biệt metadata với nội dung file.
- [ ] Biết `Path` đang trỏ file, directory hay symlink, có thể không tồn tại.
- [ ] Chọn typed `readAttributes(...,Class)` khi schema cố định.
- [ ] Chọn named `readAttributes(...,String)` khi cần danh sách attributes động và có validation.
- [ ] Biết `getAttribute` trả `Object`, không cast sai.
- [ ] Hiểu prefix `view:name` và default `basic`.
- [ ] Không giả định thứ tự các key của Map.
- [ ] Không cố `setAttribute` những thuộc tính basic read-only như `size`.
- [ ] Chỉnh mtime bằng `setLastModifiedTime`/`setTimes`/`setAttribute` theo đúng type.
- [ ] Không giả định timestamps chính xác tuyệt đối hoặc update atomic.
- [ ] Kiểm tra POSIX/DOS/ACL/user-defined view support.
- [ ] Không nhầm view support với permission trên file.
- [ ] Xử lý `IOException` và lỗi tên/type/view riêng.
- [ ] Hiểu và kiểm thử `NOFOLLOW_LINKS` nếu gặp symbolic link.
- [ ] Không tin `fileKey` là ID portable.
- [ ] Không coi size của directory là tổng cây.
- [ ] Có giới hạn path/whitelist/authorization nếu input từ bên ngoài.
- [ ] Chỉ chỉnh owner/ACL/permissions khi thật sự được phép.
- [ ] Dùng thư mục tạm trong test, không thay metadata của file người dùng.
- [ ] Có test đọc trước/đọc sau nếu thao tác ghi metadata là một phần contract.
- [ ] Biết `Files.writeString` là Java 11+; các attribute APIs đang học có từ Java 7.

## 26. Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readAttributes` (typed và named), `getAttribute`, `setAttribute`, `getFileAttributeView`, `setLastModifiedTime` và `getFileStore`.
- [Java SE 17 — `java.nio.file.attribute` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/package-summary.html): các attribute views và kiểu metadata trong NIO.2.
- [Java SE 17 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): size, loại mục, timestamps, fileKey.
- [Java SE 17 — `BasicFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): tên `basic`, danh sách named fields, `readAttributes` và `setTimes`.
- [Java SE 17 — `FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html): thời gian cho attributes.
- [Java SE 17 — `PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): owner, group, permissions và set permissions trên provider hỗ trợ.
- [Java SE 17 — `DosFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributeView.html): các cờ DOS metadata hiện được hỗ trợ nơi phù hợp.
- [Java SE 17 — `AclFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): ACL metadata.
- [Java SE 17 — `UserDefinedFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/UserDefinedFileAttributeView.html): các thuộc tính do ứng dụng định nghĩa trên provider hỗ trợ.
- [Java SE 17 — `LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Java SE 17 — `FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): kiểm tra support metadata view.

**Kết luận:** Truy cập **theo tên** dùng `Files.getAttribute`, `Files.setAttribute` và `Files.readAttributes(path,"view:attr1,attr2")`, mang tính động nhưng đòi hỏi kiểm soát tên và kiểu của `Object/Map`. Truy cập **theo giao diện có kiểu** dùng `BasicFileAttributes`, `BasicFileAttributeView` và những view đặc thù khi hỗ trợ, giúp compiler kiểm tra method và kiểu dữ liệu. Không phải mọi attribute ghi được, không phải mọi view có trên mọi filesystem, và bulk read **không bảo đảm snapshot atomic**. Hãy chọn API theo nhu cầu, dùng `FileTime`/`NOFOLLOW_LINKS` đúng ngữ nghĩa và chỉ cập nhật metadata trong phạm vi có quyền.
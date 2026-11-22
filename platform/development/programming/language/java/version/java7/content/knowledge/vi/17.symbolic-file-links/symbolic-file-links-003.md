# Java 7 — Liên kết tệp: `NOFOLLOW_LINKS` trong kiểm tra và thao tác metadata

## Mục tiêu bài học

Trong Java NIO.2, nhiều thao tác với `Path` mặc định **đi theo symbolic link (symlink)** để thao tác trên **đối tượng đích**. Điều này thường đúng khi bạn muốn đọc dữ liệu mà một đường dẫn liên kết trỏ tới, nhưng có thể **sai** nếu muốn kiểm kê, kiểm tra hoặc thay đổi thuộc tính của **chính entry liên kết**. Java cung cấp `LinkOption.NOFOLLOW_LINKS` để yêu cầu các phương thức có hỗ trợ tùy chọn ấy **không tự đi theo symbolic link ở mục đích cần xử lý**.

`LinkOption` và `NOFOLLOW_LINKS` có từ **Java 7**; chúng vẫn là API hiện hành trên các JDK 17+ và được dùng cùng `java.nio.file.Files`, `BasicFileAttributes` và `FileAttributeView`.

Sau bài, bạn có thể:

1. Phân biệt *đường dẫn link*, *đích link* và *metadata của link* với *metadata của đích*.
2. Giải thích mặc định **follow** và ý nghĩa chính xác của `LinkOption.NOFOLLOW_LINKS`.
3. Dùng `Files.exists`, `Files.notExists`, `Files.isRegularFile`, `Files.isDirectory` đúng trong các trường hợp link, dangling link và path không tồn tại.
4. Hiểu vì sao `exists(path) == false` **không nhất thiết** có nghĩa chính entry symlink không tồn tại.
5. Đọc metadata của chính link bằng `Files.readAttributes` (typed hoặc named), `Files.getAttribute` và `Files.getFileAttributeView` với `NOFOLLOW_LINKS`.
6. Biết khi nào metadata có thể chỉnh bằng `Files.setAttribute(..., NOFOLLOW_LINKS)` hoặc view có `NOFOLLOW_LINKS` và vì sao chỉnh timestamp **của link** có thể không được hỗ trợ.
7. Phân biệt API **có tham số LinkOption** và API **không có overload ấy**, tránh gọi nhầm như `Files.size(path, NOFOLLOW_LINKS)`.
8. Hiểu vì sao `NOFOLLOW_LINKS` không đồng nghĩa “chống mọi path traversal”, “không đi theo bất cứ symlink nào trong cả đường dẫn” hay “khóa đối tượng để tránh race”.
9. Xử lý symbolic links có đích tương đối, dangling links, permission, I/O errors và filesystem provider khác nhau.
10. Tự kiểm chứng bằng chương trình Java chạy trên JDK 17+ và test có điều kiện cho môi trường cho phép tạo symlink.

**Ngữ cảnh cha:** Liên kết tệp (`A175`); trọng tâm bài là **`NOFOLLOW_LINKS` khi kiểm tra tồn tại, phân loại entry và đọc/ghi metadata**, không phải một khóa học về toàn bộ thao tác I/O của NIO.2. Kiến thức được chọn là API còn hiệu lực hiện nay; nơi sử dụng tiện ích sau Java 7, bài ghi rõ phiên bản.

## 1. Symbolic link và metadata: hai đối tượng có thể khác nhau

Hình dung một directory như sau:

```text
workspace/
  report.txt           # regular file, nội dung thực
  latest.txt -> report.txt   # symbolic link
```

`latest.txt` là **entry liên kết**. `report.txt` là **target**.

Nếu code gọi:

```java
BasicFileAttributes attrs = Files.readAttributes(
        latest, BasicFileAttributes.class);
```

thì theo mặc định, khi `latest` là symlink trỏ đến một target hợp lệ, Java đọc **thuộc tính của target** `report.txt`.

Nếu code gọi:

```java
BasicFileAttributes attrs = Files.readAttributes(
        latest,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

thì mục tiêu là đọc **thuộc tính của chính symlink entry** `latest.txt`, không truy đuổi target của link đó để lấy loại/kích thước/timestamp của target.

Hai đoạn trên là **mảnh minh họa**, cần định nghĩa `latest` là `Path` và import `Files`, `BasicFileAttributes`, `LinkOption`, cùng xử lý `IOException`.

### 1.1. Follow mặc định không phải “luôn đọc link”

**Follow** có nghĩa là nếu đoạn path kết thúc bằng một symbolic link, provider truy đuổi nó theo hành vi mặc định của API rồi thao tác trên mục được liên kết tới. Với phép đọc loại file:

- Link tới **regular file** → khi follow, có thể có `attrs.isRegularFile() == true`.
- Link tới **directory** → khi follow, có thể có `attrs.isDirectory() == true`.
- Link tới target **không còn tồn tại** → phép đọc theo target có thể ném `NoSuchFileException`/`IOException`.
- Link tới target bị **từ chối truy cập** → có thể ném lỗi I/O/quyền.
- Provider không hỗ trợ symbolic link → tham số NOFOLLOW có thể không tạo khác biệt.

### 1.2. `NOFOLLOW_LINKS` không có nghĩa “từ chối mọi symlink”

Tùy chọn này nói cách **xử lý target khi path chỉ tới symbolic link**. Nếu muốn nhận diện rằng entry cuối là link, bạn phải **kiểm tra metadata**, chẳng hạn `Files.isSymbolicLink(path)` hoặc `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()`.

Đọc thuộc tính chính link **không xóa, phá hoặc vô hiệu hóa link**. Mục đích là có một lựa chọn rõ giữa **metadata của link** và **metadata của target**.

### 1.3. Dangling link là gì?

**Dangling/broken symbolic link** là entry symlink vẫn tồn tại nhưng target mà nó chỉ đến đã bị xóa, di chuyển hoặc hiện không thể được resolve.

```text
workspace/
  alias.txt -> missing.txt
  # missing.txt hiện không có
```

Đây là tình huống đặc biệt quan trọng cho `exists` và `notExists`:

- `Files.exists(alias)` theo target có thể trả **false** vì target thiếu.
- `Files.exists(alias, NOFOLLOW_LINKS)` có thể trả **true** vì bản thân entry link vẫn có.
- `Files.readAttributes(alias, BasicFileAttributes.class)` có thể báo lỗi missing target.
- `Files.readAttributes(alias, BasicFileAttributes.class, NOFOLLOW_LINKS)` có thể đọc được thuộc tính của chính entry link.

Những kết quả cụ thể phụ thuộc quyền truy cập và provider; bảng trong mục sau dùng giả định **filesystem hỗ trợ symlink, không có race và có đủ quyền kiểm tra**.

## 2. Bảng ngữ nghĩa: mặc định và `NOFOLLOW_LINKS`

| Path đầu vào | Follow mặc định, `Files.exists` | `Files.exists(..., NOFOLLOW_LINKS)` | Phân loại metadata khi NOFOLLOW |
| --- | --- | --- | --- |
| Regular file tồn tại | `true` | `true` | `isRegularFile=true` |
| Directory tồn tại | `true` | `true` | `isDirectory=true` |
| Link tới regular file hợp lệ | `true` | `true` | `isSymbolicLink=true`; không tự coi entry là regular file |
| Link tới directory hợp lệ | `true` | `true` | `isSymbolicLink=true`; không tự coi entry là directory |
| Dangling link | Thường `false` khi xác minh target thiếu | Thường `true` khi xác minh entry link tồn tại | `isSymbolicLink=true` |
| Path không hề có entry | Thường `false` | Thường `false` | `readAttributes` có thể ném `NoSuchFileException` |
| Không xác minh được vì quyền/lỗi | `false` có thể xảy ra | `false` có thể xảy ra | Không thể khẳng định chỉ từ boolean |

**Điểm cốt lõi:** `Files.exists(path)` trả `false` trong **hai** tình huống: mục không tồn tại **hoặc không xác định được nó tồn tại**. `Files.notExists(path)` cũng không phải phép phủ định toán học của `exists` trong mọi trạng thái.

### 2.1. Không biến ba trạng thái thành hai trạng thái

Khi cần phân loại:

```java
boolean exists = Files.exists(path, LinkOption.NOFOLLOW_LINKS);
boolean missing = Files.notExists(path, LinkOption.NOFOLLOW_LINKS);

if (exists) {
    // Xác nhận entry tồn tại ở thời điểm kiểm tra.
} else if (missing) {
    // Xác nhận entry không tồn tại ở thời điểm kiểm tra.
} else {
    // Trạng thái không thể xác minh.
}
```

Đây là **mảnh minh họa**, cần import `Files`, `LinkOption` và định nghĩa `path`. Cả `exists` và `notExists` có thể là `false` khi không xác định được; không nên tự chuyển thành “chắc chắn đã mất”.

Bất kỳ kết quả kiểm tra nào cũng có thể **lỗi thời ngay lập tức** nếu filesystem có hoạt động đồng thời. Vì thế không dùng `exists` như một khóa ngăn người khác xóa/tạo/thay entry.

## 3. API nào thực sự nhận `LinkOption`?

Không phải mọi phương thức `Files` đều có overload nhận `LinkOption...`. Một bảng chọn lọc các phương thức quan trọng cho chủ đề:

| API | Có `LinkOption...`? | Công dụng khi NOFOLLOW |
| --- | --- | --- |
| `Files.exists(path, options)` | Có | Kiểm tra **entry link** thay vì target |
| `Files.notExists(path, options)` | Có | Kiểm tra sự vắng mặt của entry theo lựa chọn |
| `Files.isRegularFile(path, options)` | Có | Xác định bản thân entry có phải regular file |
| `Files.isDirectory(path, options)` | Có | Xác định bản thân entry có phải directory |
| `Files.readAttributes(path, BasicFileAttributes.class, options)` | Có | Typed metadata của entry link |
| `Files.readAttributes(path, "basic:...", options)` | Có | Named metadata của entry link |
| `Files.getAttribute(path, "basic:...", options)` | Có | Đọc một named attribute của entry |
| `Files.setAttribute(path, "basic:...", value, options)` | Có | Yêu cầu ghi một attribute trên chính link nếu hỗ trợ |
| `Files.getFileAttributeView(path, View.class, options)` | Có | Tạo typed view có chính sách NOFOLLOW |
| `Files.getLastModifiedTime(path, options)` | Có | Đọc last-modified time của link entry |
| `Files.getOwner(path, options)` | Có | Đọc owner theo view/provider hỗ trợ |
| `Files.getPosixFilePermissions(path, options)` | Có | Đọc POSIX permissions của link nếu hỗ trợ |
| `Files.isSymbolicLink(path)` | **Không cần tùy chọn** | Tự kiểm tra chính entry có phải symlink |
| `Files.readSymbolicLink(path)` | **Không có `LinkOption`** | Đọc target Path *được lưu trong link* |
| `Files.size(path)` | **Không** | Không truyền `NOFOLLOW_LINKS`; muốn metadata của link dùng `readAttributes` |
| `Files.setLastModifiedTime(path, time)` | **Không** | Muốn ghi time của chính link dùng `setAttribute(..., NOFOLLOW_LINKS)` hoặc NOFOLLOW view, nếu provider hỗ trợ |
| `Files.isHidden(path)` | **Không** | Không viết lời gọi `isHidden(path, NOFOLLOW_LINKS)` |
| `Files.delete(path)` / `deleteIfExists(path)` | **Không** | Theo contract, xóa **link entry** nếu path là symlink |
| `Files.isSameFile(pathA, pathB)` | **Không** | Không suy ra có overload NOFOLLOW |

**Đọc đúng chữ ký phương thức** thay vì thêm `LinkOption` vào mọi lời gọi cho quen tay. `LinkOption.NOFOLLOW_LINKS` là một enum constant, có thể được truyền vào những API chấp nhận kiểu tương ứng; việc class `LinkOption` triển khai `OpenOption` và `CopyOption` cũng không làm phát sinh overload không tồn tại.

### 3.1. Vì sao `Files.isSymbolicLink` không cần cờ NOFOLLOW?

Mục đích của `isSymbolicLink(path)` chính là kiểm tra liệu **entry tại path** có phải symbolic link hay không. Nó không hỏi “target là loại gì”. Vì vậy lời gọi `Files.isSymbolicLink(path, NOFOLLOW_LINKS)` không thuộc chữ ký API.

### 3.2. Khi cần đọc cả loại và các metadata khác

`Files.isRegularFile(path, NOFOLLOW_LINKS)` là phép hỏi boolean nhanh, nhưng nếu yêu cầu phân biệt **lý do lỗi**, lấy size, timestamp, isOther và symlink cùng lúc, dùng `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` rồi đọc nhiều field.

Các boolean test như `isRegularFile`/`isDirectory` trả false cả khi entry không đúng loại **hoặc không xác định được loại**; với nghiệp vụ cần phân loại lỗi, ưu tiên typed read kèm xử lý `IOException`.

## 4. Chương trình A — `RegularNoFollowDemo.java`

Ở regular file bình thường **không phải symbolic link**, việc cho phép follow và cấm follow có thể cho cùng kết quả. Đây là bài thử nền tảng trước khi sang symlink/dangling.

Lưu tệp:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class RegularNoFollowDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-regular-");
        Path file = root.resolve("data.txt");
        try {
            Files.writeString(file, "abc", StandardCharsets.UTF_8);
            BasicFileAttributes followed = Files.readAttributes(
                    file, BasicFileAttributes.class);
            BasicFileAttributes nofollowed = Files.readAttributes(
                    file, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);

            System.out.println("exists=" + Files.exists(file));
            System.out.println("existsNoFollow=" +
                    Files.exists(file, LinkOption.NOFOLLOW_LINKS));
            System.out.println("regular=" + Files.isRegularFile(file));
            System.out.println("regularNoFollow=" +
                    Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS));
            System.out.println("symbolicLink=" +
                    Files.isSymbolicLink(file));
            System.out.println("typeMatches=" +
                    (followed.isRegularFile() == nofollowed.isRegularFile()));
            System.out.println("sizeMatches=" +
                    (followed.size() == nofollowed.size()));
            System.out.println("directoryNoFollow=" +
                    Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS));
            System.out.println("readFileIs3Bytes=" +
                    (nofollowed.size() == 3L));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 RegularNoFollowDemo.java
java RegularNoFollowDemo
```

**Stdout đã chạy trên JDK/Windows:**

```text
exists=true
existsNoFollow=true
regular=true
regularNoFollow=true
symbolicLink=false
typeMatches=true
sizeMatches=true
directoryNoFollow=true
readFileIs3Bytes=true
```

### 4.1. Giải thích

- `Files.writeString` ghi `"abc"` bằng UTF-8, tạo regular file 3 byte. `writeString` được bổ sung từ **Java 11**; mục tiêu bài là NOFOLLOW vốn có từ Java 7.
- Vì `file` không phải symlink, typed attributes đọc có/không có NOFOLLOW nhất quán trong phép thử.
- `Files.isSymbolicLink(file)` trả false — không cần truyền option.
- `Files.isDirectory(root, NOFOLLOW_LINKS)` true với directory tạm thường.
- Không in absolute path của directory tạm vì tên temp có thể ngẫu nhiên và khác máy.
- `finally` chỉ xóa file và directory vừa tạo, tránh động tới dữ liệu dự án.

**Chú ý:** `typeMatches` và `sizeMatches` là kết quả của cùng một regular file ổn định trong ví dụ, **không bảo đảm mọi attribute read đều atomic** nếu file đang bị process khác thay đổi.

## 5. Chương trình B — `MissingNoFollowDemo.java`

Phân biệt **mục hoàn toàn không có** với **dangling link**. Đầu tiên ta xét path chắc chắn chưa được tạo trong temp directory.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class MissingNoFollowDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-missing-");
        Path missing = root.resolve("absent.txt");
        try {
            System.out.println("exists=" + Files.exists(missing));
            System.out.println("notExists=" + Files.notExists(missing));
            System.out.println("existsNoFollow=" +
                    Files.exists(missing, LinkOption.NOFOLLOW_LINKS));
            System.out.println("notExistsNoFollow=" +
                    Files.notExists(missing, LinkOption.NOFOLLOW_LINKS));
            System.out.println("regularNoFollow=" +
                    Files.isRegularFile(missing, LinkOption.NOFOLLOW_LINKS));

            try {
                Files.readAttributes(missing, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);
                System.out.println("typedMissing=unexpected");
            } catch (NoSuchFileException e) {
                System.out.println("typedMissing=NoSuchFileException");
            }

            try {
                Files.getAttribute(missing, "basic:isSymbolicLink",
                        LinkOption.NOFOLLOW_LINKS);
                System.out.println("namedMissing=unexpected");
            } catch (NoSuchFileException e) {
                System.out.println("namedMissing=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MissingNoFollowDemo.java
java MissingNoFollowDemo
```

**Stdout đã kiểm tra trên filesystem mặc định của Windows:**

```text
exists=false
notExists=true
existsNoFollow=false
notExistsNoFollow=true
regularNoFollow=false
typedMissing=NoSuchFileException
namedMissing=NoSuchFileException
```

### 5.1. Vì sao không nhận `isSymbolicLink=false` từ một attribute object?

Vì `missing` không có entry, `Files.readAttributes(missing, ..., NOFOLLOW_LINKS)` **không tạo một object attributes toàn false**. Nó có thể ném `NoSuchFileException` — một subtype `IOException`. Ngược lại, `Files.isRegularFile(missing, NOFOLLOW_LINKS)` có kiểu boolean và trả false cho missing/wrong type/unknown.

Đó là khác biệt hữu ích giữa **phép hỏi boolean** và **phép đọc attributes với lỗi rõ**.

### 5.2. Ngoại lệ là provider-specific

Trong ví dụ, subtype là `NoSuchFileException`. Một provider khác có thể dùng `IOException` khác theo trường hợp; không nên catch đúng một subtype rồi khẳng định mọi thao tác metadata trên mọi filesystem đều báo cùng exception. Với code ứng dụng, bắt lỗi cụ thể nếu có ích nhưng vẫn phải có chính sách xử lý `IOException` tổng quát.

## 6. Symlink có target tương đối và thao tác `readSymbolicLink`

Một symlink có thể chứa target path **tương đối**:

```text
root/
  target.txt
  alias.txt -> target.txt
```

Khi tạo link:

```java
Files.createSymbolicLink(alias, target.getFileName());
```

đoạn trên yêu cầu lưu một target path tương đối `"target.txt"` trong `alias.txt`. Khi filesystem resolve link, target path tương đối thường được hiểu so với **directory chứa link**.

Nếu muốn biết target path **được lưu trong link**, dùng:

```java
Path storedTarget = Files.readSymbolicLink(alias);
```

Đây là mảnh minh họa: `storedTarget` có thể là một `Path` tương đối, **không tự bảo đảm target hiện tồn tại** và cũng không bắt buộc là absolute path.

**Đừng nhầm ba câu hỏi**:

1. “Entry cuối là symlink không?” → `Files.isSymbolicLink(alias)` hoặc metadata NOFOLLOW.
2. “Target path được lưu trong link là gì?” → `Files.readSymbolicLink(alias)`.
3. “Target hiện là file/dir gì, có tồn tại không?” → phép đọc attributes **theo link** và xử lý I/O errors.

Từng câu hỏi có API và rủi ro khác nhau.

### 6.1. Vì sao không thể yêu cầu tất cả máy tạo symlink thành công?

Tạo symlink là thao tác phụ thuộc filesystem và quyền. Trên một số cấu hình Windows, quyền tạo symlink có thể bị hạn chế; một provider không có symbolic link cũng có thể báo unsupported. Vì vậy ví dụ có tạo link trong bài được thiết kế thành **bài thử có điều kiện**.

**Không được tự nâng quyền hoặc xóa những file ngoài thư mục tạm** chỉ để ví dụ tạo symlink chạy. Nếu môi trường không hỗ trợ, vẫn có thể kiểm tra phần lớn API NOFOLLOW trên regular files và đối chiếu ngữ nghĩa symlink theo hợp đồng Java chính thức.

## 7. Chương trình C — `SymbolicLinkNoFollowDemo.java`

Chương trình này so sánh follow/NOFOLLOW ở một symlink trỏ tới regular file và sau đó cố ý làm link thành dangling link. Nó chỉ thao tác trên temp directory do test tạo.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Map;

public final class SymbolicLinkNoFollowDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-link-");
        Path target = root.resolve("target.txt");
        Path link = root.resolve("alias.txt");
        try {
            Files.writeString(target, "DATA", StandardCharsets.UTF_8);

            boolean created;
            try {
                Files.createSymbolicLink(link, target.getFileName());
                created = true;
            } catch (IOException |
                     UnsupportedOperationException |
                     SecurityException ex) {
                created = false;
            }

            System.out.println("linkCreated=" + created);
            if (created) {
                System.out.println("existsDefault=" + Files.exists(link));
                System.out.println("existsNoFollow=" +
                        Files.exists(link, LinkOption.NOFOLLOW_LINKS));
                System.out.println("regularDefault=" +
                        Files.isRegularFile(link));
                System.out.println("regularNoFollow=" +
                        Files.isRegularFile(link, LinkOption.NOFOLLOW_LINKS));
                System.out.println("isSymbolicLink=" +
                        Files.isSymbolicLink(link));

                BasicFileAttributes follow = Files.readAttributes(
                        link, BasicFileAttributes.class);
                BasicFileAttributes self = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

                System.out.println("followRegular=" +
                        follow.isRegularFile());
                System.out.println("selfIsLink=" +
                        self.isSymbolicLink());
                System.out.println("readLinkRawRelative=" +
                        Files.readSymbolicLink(link)
                                .equals(target.getFileName()));
                System.out.println("namedLink=" +
                        Files.getAttribute(link, "basic:isSymbolicLink",
                                LinkOption.NOFOLLOW_LINKS));

                Map<String, Object> named = Files.readAttributes(
                        link,
                        "basic:isSymbolicLink,isRegularFile",
                        LinkOption.NOFOLLOW_LINKS);
                System.out.println("namedSelfIsLink=" +
                        named.get("isSymbolicLink"));

                Files.delete(target);
                System.out.println("danglingFollowExists=" +
                        Files.exists(link));
                System.out.println("danglingFollowNotExists=" +
                        Files.notExists(link));
                System.out.println("danglingSelfExists=" +
                        Files.exists(link, LinkOption.NOFOLLOW_LINKS));
                System.out.println("danglingSelfNotExists=" +
                        Files.notExists(link, LinkOption.NOFOLLOW_LINKS));
                System.out.println("danglingSelfLink=" +
                        Files.readAttributes(
                                link, BasicFileAttributes.class,
                                LinkOption.NOFOLLOW_LINKS).isSymbolicLink());

                try {
                    Files.readAttributes(link, BasicFileAttributes.class);
                    System.out.println("danglingFollowRead=unexpected");
                } catch (NoSuchFileException ex) {
                    System.out.println(
                            "danglingFollowRead=NoSuchFileException");
                }
                System.out.println("linkDeleted=" +
                        Files.deleteIfExists(link));
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
javac --release 17 -encoding UTF-8 SymbolicLinkNoFollowDemo.java
java SymbolicLinkNoFollowDemo
```

**Stdout trên Windows/JDK của môi trường kiểm thử (không tạo được link):**

```text
linkCreated=false
```

**Nếu môi trường hỗ trợ tạo và đọc symbolic link trong directory tạm, nhánh thành công dự kiến:**

```text
linkCreated=true
existsDefault=true
existsNoFollow=true
regularDefault=true
regularNoFollow=false
isSymbolicLink=true
followRegular=true
selfIsLink=true
readLinkRawRelative=true
namedLink=true
namedSelfIsLink=true
danglingFollowExists=false
danglingFollowNotExists=true
danglingSelfExists=true
danglingSelfNotExists=false
danglingSelfLink=true
danglingFollowRead=NoSuchFileException
linkDeleted=true
```

Dòng `danglingFollowRead=NoSuchFileException` mô tả provider thường gặp khi đã xác nhận target thiếu; subtype cụ thể có thể khác trên filesystem khác. **Các dòng nhánh có symlink là kết quả dự kiến từ hợp đồng API, chưa được chạy trên Windows đang không cho tạo symlink**. Không mô tả chúng như stdout đã đo được trong lần kiểm thử ấy.

### 7.1. Trước khi target bị xóa

`alias.txt` trỏ tới `target.txt`:

- `Files.exists(link)` và `Files.exists(link, NOFOLLOW_LINKS)` đều true nếu quyền đủ.
- `Files.isRegularFile(link)` true khi follow tới regular file.
- `Files.isRegularFile(link, NOFOLLOW_LINKS)` false vì chính **entry cuối** là symbolic link, không phải regular file.
- `Files.isSymbolicLink(link)` true.
- Typed `readAttributes` mặc định lấy metadata target; với NOFOLLOW lấy metadata symlink.
- Named `"basic:isSymbolicLink"` với NOFOLLOW trả true; cũng có thể dùng `"basic:isRegularFile"` để biết bản thân entry link không phải regular file.
- `readSymbolicLink(link)` cho target path được lưu: `target.txt`, không phải nội dung `"DATA"`.

### 7.2. Sau khi xóa target

`Files.delete(target)` xóa regular file đích, nhưng link vẫn là một directory entry riêng. Lúc này:

- Default `exists(link)` không tìm được target: có thể false.
- `exists(link, NOFOLLOW_LINKS)` kiểm tra chính link entry: có thể true.
- `notExists(link, NOFOLLOW_LINKS)` false khi đã xác nhận link có.
- `readAttributes(link, NOFOLLOW_LINKS)` vẫn có thể báo `isSymbolicLink=true`.
- `readAttributes(link)` theo target có thể ném lỗi.
- `Files.deleteIfExists(link)` xóa **chính symlink**, không tự tạo/xóa target.

Bài này giải thích một lỗi thường gặp trong công cụ cleanup: kiểm tra `Files.exists(link)` (mặc định follow) trước rồi bỏ qua việc xóa dangling link vì kết quả false. Khi muốn xử lý **entry**, dùng phép hỏi NOFOLLOW hoặc thao tác xóa trực tiếp theo contract, tránh check-then-act không cần thiết.

## 8. `NOFOLLOW_LINKS` không dừng việc resolve mọi thành phần cha

Đây là điểm rất quan trọng khi path có **symlink ở giữa**:

```text
root/
  real/
    data.txt
  shortcut -> real/
```

Xét path:

```text
root/shortcut/data.txt
```

Khi gọi:

```java
Files.readAttributes(
        root.resolve("shortcut").resolve("data.txt"),
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

`NOFOLLOW_LINKS` nhắm tới việc **không theo link nếu chính entry mục tiêu cuối là symlink**. Nó **không có nghĩa mọi thành phần cha của path đều được cấm resolve qua symbolic link**. Ở path trên, `shortcut` là một thành phần trung gian, và quá trình tìm `data.txt` có thể đi qua link đó để tới `real/data.txt` trên filesystem hỗ trợ.

Vì vậy:

- `readAttributes(shortcut, NOFOLLOW)` có thể cho `isSymbolicLink=true`.
- `readAttributes(shortcut/data.txt, NOFOLLOW)` có thể cho `isRegularFile=true` vì **thành phần cuối** `data.txt` là regular file.
- Không được dùng sự hiện diện của `NOFOLLOW_LINKS` ở thao tác cuối như bằng chứng rằng “không một symlink nào trong đường dẫn đã bị theo”.

### 8.1. Chương trình D — `IntermediateSymlinkDemo.java`

Chương trình thử có điều kiện tạo symlink trỏ tới **directory**.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class IntermediateSymlinkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-intermediate-");
        Path real = root.resolve("real");
        Path file = real.resolve("data.txt");
        Path alias = root.resolve("shortcut");

        try {
            Files.createDirectory(real);
            Files.createFile(file);
            boolean created;
            try {
                Files.createSymbolicLink(alias, real.getFileName());
                created = true;
            } catch (IOException |
                     UnsupportedOperationException |
                     SecurityException ex) {
                created = false;
            }
            System.out.println("directoryLinkCreated=" + created);

            if (created) {
                Path viaAlias = alias.resolve("data.txt");
                BasicFileAttributes a = Files.readAttributes(
                        viaAlias, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

                System.out.println("lastEntryIsRegular=" +
                        a.isRegularFile());
                System.out.println("lastEntryIsLink=" +
                        a.isSymbolicLink());
                System.out.println("aliasItselfIsLink=" +
                        Files.readAttributes(
                                alias, BasicFileAttributes.class,
                                LinkOption.NOFOLLOW_LINKS)
                                .isSymbolicLink());
                System.out.println("intermediateFollowingWorks=" +
                        Files.isRegularFile(
                                viaAlias, LinkOption.NOFOLLOW_LINKS));
            }
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(file);
            Files.deleteIfExists(real);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 IntermediateSymlinkDemo.java
java IntermediateSymlinkDemo
```

**Stdout trên Windows/JDK của môi trường kiểm thử:**

```text
directoryLinkCreated=false
```

**Khi tạo directory symlink được hỗ trợ, nhánh thành công dự kiến:**

```text
directoryLinkCreated=true
lastEntryIsRegular=true
lastEntryIsLink=false
aliasItselfIsLink=true
intermediateFollowingWorks=true
```

Kết quả này nhấn mạnh: **NOFOLLOW_LINKS là tùy chọn của thao tác lên entry cuối, không phải một hệ thống confinement cho toàn bộ path lookup.** Nếu yêu cầu ngăn tuyệt đối symlink traversal hoặc path traversal do attacker điều khiển, cần thiết kế filesystem-level security khác.

## 9. Typed metadata: `Files.readAttributes` với `NOFOLLOW_LINKS`

Một cách rất rõ để lấy metadata của chính entry:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

Với symlink entry đã được xác minh:

- `attrs.isSymbolicLink()` true.
- `attrs.isRegularFile()` thường false.
- `attrs.isDirectory()` thường false.
- `attrs.size()` có thể mang ý nghĩa của **link entry**, không phải size của target.
- `attrs.lastModifiedTime()` là time metadata của **link entry** nếu provider hỗ trợ.
- `attrs.fileKey()` có thể là null hoặc một key provider-specific.

### 9.1. Kích thước symlink không nhất thiết bằng kích thước target

`Files.size(path)` không nhận `LinkOption`. Đừng cố:

```java
Files.size(link, LinkOption.NOFOLLOW_LINKS); // Không biên dịch.
```

Đây là **anti-pattern**, không phải code runnable. Nếu muốn size theo NOFOLLOW:

```java
long linkSize = Files.readAttributes(
        link, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS).size();
```

Đây là mảnh minh họa hợp lệ khi `link` là Path có thể đọc metadata. Giá trị size của symlink **provider-specific**: đừng suy rằng nó luôn bằng độ dài chuỗi target, kích thước nội dung target hay một hằng số.

### 9.2. Kiểu trả về và exceptions

`readAttributes(..., BasicFileAttributes.class, ...)` trả một đối tượng typed; bạn gọi method trực tiếp, tránh cast `Object`.

Nếu file bị xóa, thiếu quyền hoặc provider không thể lấy attributes, nó có thể ném `IOException`, gồm các subtype như `NoSuchFileException` và `AccessDeniedException`. Khác với `Files.exists`, lỗi đọc metadata không được mặc định đổi thành `false`.

### 9.3. Bulk read không là atomic snapshot

NIO.2 cho phép đọc nhóm attributes bằng một operation ở mức Java, nhưng việc **toàn bộ values được lấy nguyên tử so với filesystem operations khác hay không** là implementation-specific. Nếu một process khác sửa target/link trong lúc đọc, bạn không có bảo đảm rằng mọi metadata phản ánh cùng một phiên bản bất biến.

## 10. Named metadata: `readAttributes` và `getAttribute` với NOFOLLOW

Khi cần lựa chọn thuộc tính theo tên:

```java
Map<String, Object> values = Files.readAttributes(
        link, "basic:isSymbolicLink,isRegularFile,size",
        LinkOption.NOFOLLOW_LINKS);
```

Đây là **mảnh minh họa**, cần import `Map`, `Files`, `LinkOption`. Prefix `basic:` là attribute view và phần sau là danh sách tên phân cách dấu phẩy.

Hoặc đọc một trường:

```java
Object isLink = Files.getAttribute(
        link, "basic:isSymbolicLink",
        LinkOption.NOFOLLOW_LINKS);
```

Dạng này trả `Object`, trong trường hợp `basic:isSymbolicLink` chứa `Boolean`. Các types cơ bản:

| Tên thuộc tính | Kiểu giá trị trong named Map/Object |
| --- | --- |
| `basic:isSymbolicLink` | `Boolean` |
| `basic:isRegularFile` | `Boolean` |
| `basic:isDirectory` | `Boolean` |
| `basic:size` | `Long` |
| `basic:lastModifiedTime` | `FileTime` |
| `basic:lastAccessTime` | `FileTime` |
| `basic:creationTime` | `FileTime` |
| `basic:fileKey` | `Object` hoặc `null` tùy provider |

**Đừng cast `"basic:lastModifiedTime"` thành `String` hoặc `"basic:size"` thành `Integer`**. Named API linh hoạt ở runtime nhưng đòi hỏi xử lý kiểu dữ liệu theo contract.

### 10.1. Wildcard khi cần metadata của chính link

```java
Map<String, Object> all = Files.readAttributes(
        link, "basic:*", LinkOption.NOFOLLOW_LINKS);
```

Dấu `*` chọn các thuộc tính của view. Việc map có key nào ngoài basic, thứ tự Map và các kiểu mở rộng phụ thuộc provider/view; không serialize bản đồ metadata thô thành một API contract bất biến mà không định nghĩa schema.

### 10.2. Named access không tự bỏ qua quyền truy cập

`NOFOLLOW_LINKS` chỉ thay đối tượng metadata được nhắm tới theo semantics link, **không cấp thêm quyền**. Nếu path không đọc được hoặc view không hỗ trợ, vẫn có thể nhận `IOException` hoặc `UnsupportedOperationException`.

## 11. Typed attribute view với NOFOLLOW

NIO.2 có `BasicFileAttributeView` để đọc/ghi metadata bằng method có kiểu:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        link,
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

BasicFileAttributes attrs = view.readAttributes();
```

Đây là **mảnh minh họa**; cần import `Files`, `LinkOption`, `BasicFileAttributeView` và `BasicFileAttributes`, cùng xử lý `IOException`.

Nếu `link` là symlink và provider hỗ trợ thao tác tương ứng, view sẽ làm việc với **attributes của chính link**. Với basic view trên filesystem tuân thủ NIO.2, basic attributes được hỗ trợ; với các view tùy chọn (POSIX, DOS, owner, ACL...) cần kiểm tra view có tồn tại không.

### 11.1. View object không phải snapshot đã đọc

`getFileAttributeView` tạo ra một object đại diện cho cách thao tác trên một path; không tự chứng minh entry vẫn tồn tại. Khi bạn gọi `view.readAttributes()`, metadata được đọc lúc đó, có thể lỗi nếu entry đã biến mất.

### 11.2. Một view không khóa file

Sau khi lấy view, một process khác vẫn có thể sửa, move hoặc thay directory entry. `view.readAttributes()` và `view.setTimes(...)` là các thao tác có thể diễn ra ở thời điểm khác nhau. Không coi một object `BasicFileAttributeView` như transaction, mutex hay file identity khóa cố định.

## 12. Ghi metadata bằng `NOFOLLOW_LINKS`: cần biết rõ đang đổi cái gì

`NOFOLLOW_LINKS` cũng xuất hiện trong các API cho phép ghi metadata:

```java
FileTime time = FileTime.fromMillis(1704067200000L);

Files.setAttribute(
        link, "basic:lastModifiedTime", time,
        LinkOption.NOFOLLOW_LINKS);
```

Hoặc dùng typed view:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
        link, BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

view.setTimes(time, null, null);
```

Hai đoạn là **mảnh minh họa**. Chúng yêu cầu ghi timestamp của **link entry**, không ghi timestamp của target. **Nhưng điều đó không có nghĩa mọi filesystem cho phép đặt timestamp trên symlink.** Provider có thể không hỗ trợ hoặc từ chối thao tác với `IOException`/lỗi phù hợp.

### 12.1. Những gì `setTimes` thực sự cập nhật

Thứ tự tham số:

```java
view.setTimes(lastModifiedTime, lastAccessTime, createTime);
```

Giá trị `null` cho một tham số nghĩa là **không yêu cầu thay đổi** timestamp tương ứng.

Timestamps có độ chính xác/range phụ thuộc filesystem. Một số provider cần đọc lại các fields khác khi chỉ cập nhật một time; cập nhật có thể **không atomic với các hoạt động khác**. Vì vậy test trên filesystem thực phải xét precision, permission và concurrency.

### 12.2. `setLastModifiedTime` không có `NOFOLLOW_LINKS` overload

`Files.getLastModifiedTime(path, LinkOption.NOFOLLOW_LINKS)` là lời gọi hợp lệ để **đọc** time của link.

Nhưng:

```java
Files.setLastModifiedTime(
        link, time, LinkOption.NOFOLLOW_LINKS); // Không biên dịch.
```

Là anti-pattern. API `Files.setLastModifiedTime(Path, FileTime)` không có tham số LinkOption. Nếu cần yêu cầu **ghi mtime của symlink entry**, dùng `Files.setAttribute(..., LinkOption.NOFOLLOW_LINKS)` hoặc typed view đã lấy với NOFOLLOW như trên, rồi xử lý khả năng provider không hỗ trợ.

### 12.3. Không chỉnh metadata của link trên môi trường không hỗ trợ chỉ để thử

Các ví dụ runnable sẽ **chỉnh metadata trên regular file tạm** với NOFOLLOW để xác minh chữ ký API và kiểu dữ liệu. Bài không cố ép Windows tạo symlink hoặc sửa link timestamps nếu môi trường bị giới hạn quyền.

Khi chạy trong môi trường hỗ trợ symlink attributes, hãy đặt thử trên temp link riêng và **bắt lỗi I/O mà provider có thể ném** thay vì tuyên bố mọi filesystem hỗ trợ ghi link mtime.

## 13. Chương trình E — `MetadataNoFollowDemo.java`

Chương trình kết hợp **typed view, named Map, getAttribute, getLastModifiedTime và setAttribute** với `NOFOLLOW_LINKS`. Dùng regular file tạm để kết quả có thể kiểm chứng ngay cả khi không có quyền tạo symlink.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.util.Map;

public final class MetadataNoFollowDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-metadata-");
        Path file = root.resolve("sample.txt");
        try {
            Files.createFile(file);
            BasicFileAttributeView view = Files.getFileAttributeView(
                    file,
                    BasicFileAttributeView.class,
                    LinkOption.NOFOLLOW_LINKS);

            System.out.println("viewPresent=" + (view != null));
            System.out.println("viewName=" + view.name());
            System.out.println("viewRegular=" +
                    view.readAttributes().isRegularFile());

            Map<String, Object> named = Files.readAttributes(
                    file,
                    "basic:size,isSymbolicLink,lastModifiedTime",
                    LinkOption.NOFOLLOW_LINKS);
            System.out.println("namedCount=" + named.size());
            System.out.println("namedSize=" + named.get("size"));
            System.out.println("namedLink=" + named.get("isSymbolicLink"));
            System.out.println("namedTimeType=" +
                    (named.get("lastModifiedTime") instanceof FileTime));
            System.out.println("singleLink=" +
                    Files.getAttribute(
                            file, "basic:isSymbolicLink",
                            LinkOption.NOFOLLOW_LINKS));

            FileTime first = FileTime.fromMillis(1704067200000L);
            view.setTimes(first, null, null);
            System.out.println("typedSetTime=" +
                    Files.getLastModifiedTime(
                            file, LinkOption.NOFOLLOW_LINKS).toMillis());

            FileTime second = FileTime.fromMillis(1704153600000L);
            Files.setAttribute(
                    file, "basic:lastModifiedTime",
                    second, LinkOption.NOFOLLOW_LINKS);
            System.out.println("namedSetTime=" +
                    view.readAttributes()
                            .lastModifiedTime().toMillis());
            System.out.println("sizeStillZero=" +
                    (Files.readAttributes(
                            file, BasicFileAttributes.class).size() == 0));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 MetadataNoFollowDemo.java
java MetadataNoFollowDemo
```

**Stdout đã kiểm tra trên Windows/JDK:**

```text
viewPresent=true
viewName=basic
viewRegular=true
namedCount=3
namedSize=0
namedLink=false
namedTimeType=true
singleLink=false
typedSetTime=1704067200000
namedSetTime=1704153600000
sizeStillZero=true
```

### 13.1. Phân tích API cụ thể

- `getFileAttributeView(..., BasicFileAttributeView.class, NOFOLLOW_LINKS)` trả typed view.
- `view.name()` là `"basic"`.
- `Files.readAttributes(path, "basic:...", NOFOLLOW_LINKS)` trả Map 3 key.
- `basic:size` có kiểu `Long`, `basic:isSymbolicLink` có kiểu `Boolean`, `basic:lastModifiedTime` là `FileTime`.
- `Files.getAttribute` đọc một trường riêng lẻ theo tên và theo chính sách NOFOLLOW.
- `view.setTimes(first, null, null)` cập nhật mtime qua typed view.
- `Files.getLastModifiedTime(file, NOFOLLOW_LINKS)` đọc mtime mới.
- `Files.setAttribute(..., "basic:lastModifiedTime", second, NOFOLLOW_LINKS)` cập nhật metadata qua tên.
- `view.readAttributes()` đọc lại mtime và thấy giá trị `second` trên filesystem thử.
- `sizeStillZero=true`: cập nhật mtime **không tự viết dữ liệu** vào file.

**Giới hạn của stdout:** Các giá trị epoch milliseconds được filesystem kiểm thử lưu chính xác. Với provider có granularity khác, cần kiểm tra precision, không hardcode một yêu cầu accuracy nanosecond cho mọi hệ thống.

## 14. Chương trình F — `CheckNoFollowVsReadDemo.java`

Ví dụ này nhấn mạnh ba giai đoạn **chưa tạo → đã tạo → đã xóa** trên cùng một path và sự khác nhau giữa phép hỏi boolean và typed read.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class CheckNoFollowVsReadDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nofollow-check-");
        Path file = root.resolve("new.txt");
        try {
            System.out.println("existsBefore=" +
                    Files.exists(file, LinkOption.NOFOLLOW_LINKS));
            System.out.println("notExistsBefore=" +
                    Files.notExists(file, LinkOption.NOFOLLOW_LINKS));

            Files.createFile(file);
            System.out.println("existsAfter=" +
                    Files.exists(file, LinkOption.NOFOLLOW_LINKS));
            System.out.println("notExistsAfter=" +
                    Files.notExists(file, LinkOption.NOFOLLOW_LINKS));

            BasicFileAttributes a = Files.readAttributes(
                    file, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);
            System.out.println("typedRegular=" + a.isRegularFile());

            Files.delete(file);
            System.out.println("existsDeleted=" +
                    Files.exists(file, LinkOption.NOFOLLOW_LINKS));
            System.out.println("notExistsDeleted=" +
                    Files.notExists(file, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CheckNoFollowVsReadDemo.java
java CheckNoFollowVsReadDemo
```

**Stdout đã kiểm chứng:**

```text
existsBefore=false
notExistsBefore=true
existsAfter=true
notExistsAfter=false
typedRegular=true
existsDeleted=false
notExistsDeleted=true
```

### 14.1. Điều nên và không nên suy ra

- Trong môi trường thử có quyền đầy đủ, `exists`/`notExists` phản ánh trạng thái file ở từng thời điểm.
- `Files.createFile` thật sự tạo file mới; `Files.delete` thật sự xóa entry.
- Typed read sau khi tạo thành công giúp biết loại entry khi nó còn tồn tại.
- **Không suy ra** rằng nếu một thread khác đang thay file thì mọi phép hỏi và thao tác sẽ luôn nhìn một trạng thái cố định.

Những phép hỏi được dùng để học và quan sát; với nghiệp vụ “chỉ tạo nếu chưa có”, dùng `Files.createFile` hoặc `CREATE_NEW` theo hợp đồng nguyên tử của thao tác tạo, không dựa vào `exists` như điều kiện đồng bộ.

## 15. API sai chữ ký: hai ví dụ *cố ý không biên dịch*

Có những phương thức không có overload nhận `LinkOption` dù tên nhìn tương tự những phương thức có hỗ trợ.

### 15.1. `Files.size` không nhận NOFOLLOW

```java
Files.size(path, LinkOption.NOFOLLOW_LINKS);
```

Đây là **đoạn cố ý sai**, không phải code mẫu chạy. Thay bằng:

```java
long size = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS).size();
```

Nếu muốn size của **target**, có thể dùng `Files.size(path)`; nếu muốn metadata size của **symlink entry**, dùng typed/named read có NOFOLLOW.

### 15.2. `Files.setLastModifiedTime` không nhận NOFOLLOW

```java
Files.setLastModifiedTime(path, time, LinkOption.NOFOLLOW_LINKS);
```

Cũng **cố ý sai**. Thay bằng:

```java
Files.setAttribute(
        path, "basic:lastModifiedTime",
        time, LinkOption.NOFOLLOW_LINKS);
```

Hai phép thử biên dịch bị từ chối bằng `javac --release 17`, xác nhận không có overload tương ứng. Đây là lỗi **compile-time**, khác với trường hợp code biên dịch được nhưng provider không hỗ trợ cập nhật metadata của link và ném exception lúc chạy.

### 15.3. Lưu ý về `LinkOption` và `CopyOption`

`LinkOption` cũng triển khai `CopyOption`, vì thế `Files.copy(source, destination, LinkOption.NOFOLLOW_LINKS)` là một lựa chọn có ý nghĩa khi **copy symlink** (thay vì copy target theo mặc định) trên provider hỗ trợ. Nhưng đó là **semantics của thao tác copy**; không biến `Files.size` hoặc `Files.setLastModifiedTime` thành các API nhận `LinkOption`.

## 16. Các attribute views khác và `NOFOLLOW_LINKS`

Ngoài basic attributes, NIO.2 có các view tùy chọn:

| View | Ví dụ sử dụng | Điều cần lưu ý khi NOFOLLOW |
| --- | --- | --- |
| `PosixFileAttributeView` | Quyền `permissions`, owner, group | Provider không hỗ trợ POSIX thì view có thể là `null`; symlink permissions/ownership có semantics riêng |
| `DosFileAttributeView` | hidden, read-only, archive, system flags | Không có trên mọi filesystem, cập nhật flags của symlink có thể không được hỗ trợ |
| `FileOwnerAttributeView` | Owner principal | Quyền truy vấn/thay owner phụ thuộc OS/ACL |
| `AclFileAttributeView` | ACL entries | Thay ACL là thao tác nhạy cảm về quyền; không cấp phép chỉ vì có view |
| `UserDefinedFileAttributeView` | Metadata do ứng dụng định nghĩa | Hỗ trợ và semantics trên link có thể khác nhau |

### 16.1. POSIX attributes khi provider hỗ trợ

```java
PosixFileAttributeView view = Files.getFileAttributeView(
        link,
        PosixFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view != null) {
    PosixFileAttributes attrs = view.readAttributes();
    // Xử lý owner/group/permissions của entry theo provider.
}
```

Đây là **mảnh minh họa**, cần import các interface từ `java.nio.file.attribute`, `Files`, `LinkOption`, và xử lý `IOException`.

**Không gán permission mặc định cho symlink từ kiến thức Unix truyền thống rồi giả định mọi provider Java làm hệt như vậy.** Kiểm tra support và yêu cầu quyền truy cập thực tế. `PosixFileAttributeView` và `DosFileAttributeView` vẫn là API hiện hành nhưng **tùy chọn**, không phải legacy cần bỏ.

### 16.2. `Files.getOwner` và `Files.getPosixFilePermissions` có LinkOption

Hai phương thức đọc này có overload varargs `LinkOption...`:

```java
UserPrincipal owner = Files.getOwner(
        link, LinkOption.NOFOLLOW_LINKS);

Set<PosixFilePermission> perms =
        Files.getPosixFilePermissions(
                link, LinkOption.NOFOLLOW_LINKS);
```

Đây là **mảnh minh họa có điều kiện**: cần import `UserPrincipal`, `PosixFilePermission`, `Set`; `getPosixFilePermissions` chỉ được dùng khi filesystem hỗ trợ POSIX. Nếu provider không hỗ trợ, có thể ném `UnsupportedOperationException`. Hai lời gọi không tự cấp quyền và không đảm bảo một link có permissions độc lập với target trên mọi file store.

### 16.3. Không cho client thay metadata tùy ý

Một API nhận `path` + `attributeName` + `value` trực tiếp từ người dùng có thể cho phép chỉnh owner, ACL, permissions hoặc timestamp ngoài phạm vi. Dù có NOFOLLOW, cần **authorization**, whitelist tên và kiểu attribute, giới hạn root/base và biện pháp filesystem-level nếu attacker có thể thay path entries.

## 17. `NOFOLLOW_LINKS` liên quan thế nào đến `Files.walkFileTree` và `Files.delete`?

Bài tập trung vào kiểm tra và metadata, nhưng hai nhóm API gần kề dễ gây nhầm:

### 17.1. `Files.walkFileTree` dùng `FileVisitOption`, không dùng `LinkOption`

`Files.walkFileTree(root, visitor)` **mặc định không đi theo symlinks** khi duyệt cây. Nếu muốn theo links, overload của walker dùng `FileVisitOption.FOLLOW_LINKS`, **không phải** `LinkOption.NOFOLLOW_LINKS`.

Đừng viết:

```java
// Không phải chữ ký walkFileTree hợp lệ:
Files.walkFileTree(root, LinkOption.NOFOLLOW_LINKS, visitor);
```

Đây là mảnh **cố ý sai**. Muốn giữ mặc định không follow:

```java
Files.walkFileTree(root, visitor);
```

Muốn khai báo rõ options và độ sâu:

```java
Files.walkFileTree(
        root,
        EnumSet.noneOf(FileVisitOption.class),
        Integer.MAX_VALUE,
        visitor);
```

Đây là **mảnh minh họa**; cần `root`, `visitor` và import `EnumSet`, `FileVisitOption`, `Files`, cùng xử lý `IOException`.

### 17.2. `Files.delete`/`deleteIfExists` xóa chính link, không xóa target

Nếu `path` là symlink, `Files.delete(path)` hoặc `Files.deleteIfExists(path)` xóa **entry link** chứ không mặc nhiên xóa target. Chúng không nhận một tham số `LinkOption` để chọn giữa “delete target” và “delete link”.

Đặc biệt, với dangling link, `Files.exists(link)` theo mặc định có thể trả false; điều đó **không** có nghĩa `Files.deleteIfExists(link)` sẽ luôn trả false. Nếu link entry thực sự tồn tại và được phép xóa, API có thể xóa nó.

**Tránh anti-pattern:** kiểm tra `Files.exists(link)` trước `Files.deleteIfExists(link)` rồi bỏ qua dangling link. Thao tác `deleteIfExists` đã tự xử lý trường hợp entry vắng theo contract, dù vẫn có thể ném lỗi I/O khác.

### 17.3. `NOFOLLOW_LINKS` không biến copy, move hay delete thành transaction

Bất kể link handling option, filesystem vẫn có thể thay đổi; copy/move có khác biệt provider, và nhiều thao tác không bảo đảm atomic với tất cả hoạt động đồng thời. Nếu code thao tác trên đường dẫn chưa tin cậy, chỉ một flag NOFOLLOW không thay thế chính sách bảo vệ filesystem.

## 18. Sai lầm bảo mật: nghĩ NOFOLLOW tự chống path traversal

Giả sử một service chỉ cho phép xem metadata trong `/srv/storage`. Kẻ bên ngoài có thể đưa path như:

```text
../private/key.pem
/srv/storage/shortcut-to-outside/file.txt
```

Một đoạn kiểm tra từ vựng:

```java
Path base = Paths.get("/srv/storage")
        .toAbsolutePath().normalize();
Path request = Paths.get("reports", "summary.txt");

if (request.isAbsolute()) {
    throw new IllegalArgumentException("Absolute input forbidden");
}
Path candidate = base.resolve(request).normalize();
if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes base");
}
BasicFileAttributes attrs = Files.readAttributes(
        candidate, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

là **mảnh minh họa**, không phải chương trình portable trên Windows vì `"/srv/storage"` chỉ minh họa một path Unix-like. Nó giúp từ chối một số đường dẫn tuyệt đối/`..` không hợp lệ nhưng **không đủ làm security boundary** khi attacker có thể sửa directory entries:

- `NOFOLLOW_LINKS` không cấm symlink trong **các thành phần trung gian**.
- `normalize()` chỉ rút gọn `.`/`..` bằng từ vựng, không xác minh filesystem objects.
- `Path.startsWith` so theo thành phần path, không chứng minh mục thực tế đã resolve nằm bên trong base.
- Nếu kiểm tra `isSymbolicLink(path)` rồi gọi `readAttributes(path)`, attacker có thể thay entry giữa hai lời gọi (**TOCTOU**).
- Link, junction, mount và file-store-specific behaviors cần được đánh giá riêng.
- Ngay cả realpath/`toRealPath` trước thao tác cũng không loại bỏ mọi race nếu entry có thể thay đổi sau kiểm tra.

### 18.1. Một giải pháp an toàn cần những tầng nào?

Tùy threat model, có thể cần:

1. **Chọn base directory tin cậy** và không cho attacker thay các directory ancestors.
2. **Xác thực resource ID**, tránh dùng raw path từ client khi không cần.
3. **Giới hạn quyền hệ điều hành** của process, kể cả quyền đọc/ghi metadata.
4. **Kiểm tra đầu vào**: absolute, `..`, tên không hợp lệ, path outside allowed tree.
5. **Sử dụng API filesystem relative-to-directory handle** trong môi trường hỗ trợ, ví dụ các thao tác `SecureDirectoryStream` giúp giảm một số race.
6. **Chọn link policy** rõ: đọc link entry, đọc target, hay hoàn toàn từ chối symlinks.
7. **Ghi nhận lỗi và trạng thái không xác minh** thay vì tự coi `false` là không tồn tại.
8. **Kiểm thử adversarial**: symlink ở cuối/giữa, dangling link, target bị thay, permission và races.

Không có một câu “cứ thêm NOFOLLOW là an toàn” có thể thay thế toàn bộ thiết kế ấy.

### 18.2. Metadata cũng có thể nhạy cảm

Các fields như owner, ACL, permissions, timestamps, file keys hoặc đường dẫn target của symlink có thể lộ cấu trúc hệ thống. Nếu cung cấp một API trả metadata cho người dùng, chỉ trả những fields cần thiết và được phép xem; không expose `BasicFileAttributes` hoặc map `"posix:*"` nguyên xi nếu không có policy riêng.

## 19. Lỗi thường gặp và cách sửa

### 19.1. `Files.exists(link) == false` nên kết luận không có link

Sai nếu target của link bị mất. Muốn hỏi về chính entry link, dùng `Files.exists(link, NOFOLLOW_LINKS)` hoặc typed metadata với NOFOLLOW.

### 19.2. Nghĩ `Files.notExists` luôn là `!Files.exists`

Không: nếu không xác định được trạng thái vì quyền/lỗi I/O, cả hai có thể false. Phải có nhánh unknown khi business logic cần chắc chắn.

### 19.3. Dùng `isRegularFile(link)` để hỏi chính link có regular không

Mặc định follow target. Nếu muốn biết **entry cuối** có regular không, thêm `NOFOLLOW_LINKS`; nếu muốn biết đó có phải symlink, dùng `isSymbolicLink`.

### 19.4. Dùng `Files.size(link)` rồi tưởng đang xem size của link

`Files.size` không nhận NOFOLLOW option. Muốn metadata của link, đọc `BasicFileAttributes` với NOFOLLOW rồi lấy `size()`.

### 19.5. Truyền NOFOLLOW vào `setLastModifiedTime`

Không có overload đó. Dùng `setAttribute(...,"basic:lastModifiedTime", time, NOFOLLOW_LINKS)` hoặc typed view NOFOLLOW, nếu filesystem cho phép.

### 19.6. Đọc được attributes của link nên tự tin sửa được mtime của link

Không. Metadata view có thể đọc được, nhưng thay timestamp/permissions/ACL của chính symlink có thể không được hỗ trợ hoặc thiếu quyền.

### 19.7. Nghĩ NOFOLLOW chặn các symlink ở cha

Không. Tùy chọn này liên quan handling của entry được thao tác; symlink trung gian vẫn có thể được resolve trong path lookup.

### 19.8. Quên `NOFOLLOW_LINKS` ở typed view

Nếu lấy `BasicFileAttributeView` không truyền options, view mặc định theo symlink; sau đó `view.readAttributes()`/`setTimes` có thể tác động tới target thay vì link.

### 19.9. Nhầm `BasicFileAttributes` và `BasicFileAttributeView`

Một bên là **object kết quả đọc**; một bên là **giao diện thao tác** với `readAttributes` và `setTimes`. `NOFOLLOW` có thể được đưa vào lúc **lấy view**, không phải gọi `attrs.isSymbolicLink(NOFOLLOW)`.

### 19.10. Cast named attribute sai type

`"basic:isSymbolicLink"` trả `Boolean`, `"basic:size"` trả `Long` và `"basic:lastModifiedTime"` trả `FileTime`. Không cast thành string/int tùy ý.

### 19.11. Hardcode hành vi symlink của Windows/Linux

Khả năng tạo link, subtype exception, POSIX permissions và thao tác lên link timestamps tùy provider. Chạy bài thử có điều kiện, không giả định tất cả hệ thống đồng nhất.

### 19.12. Dùng `getAttribute` trong if mà bỏ qua IOException

Khi cần đọc metadata rõ ràng, lỗi permission/I/O cần được xử lý theo contract. Tránh biến missing/denied thành một boolean mặc định “không phải link” nếu điều đó làm sai security decision.

### 19.13. Dùng NOFOLLOW như một transaction snapshot

Một attribute read không khóa file. Một process khác có thể thay entry ngay sau khi bạn đọc. Với nghiệp vụ yêu cầu identity ổn định, cần phương án filesystem/locking phù hợp.

### 19.14. Tự sửa timestamp rồi coi mọi filesystem lưu nanosecond chính xác

Precision/range phụ thuộc filesystem. So sánh expected theo granularity được hỗ trợ thay vì áp đặt nanosecond tuyệt đối.

### 19.15. Xóa dangling link bằng check-then-delete mặc định follow

Có thể bỏ sót link vì target không tồn tại. Nếu đã được ủy quyền dọn link entry, dùng `Files.deleteIfExists(link)` theo contract và xử lý lỗi còn lại.

### 19.16. Nghĩ `readSymbolicLink` mở target file

Không. Nó đọc target `Path` được lưu trong link; target có thể chưa tồn tại và có thể là path tương đối.

## 20. Ma trận kiểm thử nên có

| Tình huống | Phép thử | Kết quả/điều cần kiểm |
| --- | --- | --- |
| Regular file có thật | `exists`, `isRegularFile`, typed read có/không NOFOLLOW | Kết quả phù hợp loại regular |
| Directory thật | `isDirectory(..., NOFOLLOW)` | True nếu xác định được directory |
| Path không tồn tại | `exists`/`notExists` với NOFOLLOW | False/true khi có thể xác minh |
| Missing path với typed read | `readAttributes(..., NOFOLLOW)` | `IOException`, thường `NoSuchFileException` |
| Symlink hợp lệ tới file | `isRegularFile(link)` vs `isRegularFile(link, NOFOLLOW)` | Follow target vs phân loại link |
| Symlink hợp lệ tới directory | `isDirectory(link)` vs `isDirectory(link, NOFOLLOW)` | Follow target vs phân loại entry |
| Dangling link | `exists(link)` vs `exists(link, NOFOLLOW)` | Target vắng nhưng link entry có thể vẫn có |
| Dangling link, read attrs | Typed read mặc định vs NOFOLLOW | Follow có thể lỗi; NOFOLLOW đọc link |
| `readSymbolicLink` | Đọc target Path đã lưu | Có thể là relative, không xác minh target |
| Link trung gian | `alias/file.txt` với NOFOLLOW | Có thể đi qua alias để tới entry cuối |
| Typed attribute view | `getFileAttributeView(...,NOFOLLOW)` | View của link khi provider hỗ trợ |
| Named attribute read | `getAttribute(...,NOFOLLOW)` | Giá trị metadata của link |
| Named bulk read | `readAttributes(...,"basic:*",NOFOLLOW)` | Map metadata chính entry |
| Get mtime | `getLastModifiedTime(...,NOFOLLOW)` | Time của link nếu metadata hỗ trợ |
| Set mtime | `setAttribute(...,NOFOLLOW)` | Có thể lỗi nếu link update unsupported |
| Invalid overload | `Files.size(path,NOFOLLOW)` | Không biên dịch |
| Invalid overload | `setLastModifiedTime(path,time,NOFOLLOW)` | Không biên dịch |
| Không có quyền | `exists` vs `readAttributes` | Boolean có thể unknown; typed read ném I/O |
| File được thay giữa hai lệnh | Read rồi action khác | Không có bảo đảm identity/TOCTOU |
| Provider không hỗ trợ symlink | Conditional symlink test | Không ép tạo link để QA |
| Symlink loop | Follow target/real path tùy API | Có thể gặp I/O/loop errors; cần policy |

### 20.1. Test nên độc lập môi trường

- Tạo root bằng `Files.createTempDirectory`; không dùng đường dẫn cá nhân.
- Với test không cần symlink, dùng regular file/directory để có stdout ổn định.
- Với symlink, bắt lỗi **tạo link** rồi skip nhánh link-specific có điều kiện, không báo rằng API không tồn tại.
- Đừng hardcode size của link entry, fileKey, ACL, POSIX flags hay timestamp độ phân giải nanosecond.
- Không áp đặt subtype exception giống nhau trên mọi provider.
- Dọn file, link và root theo thứ tự, **chỉ dọn đối tượng do test tạo**.
- Không thay symlink trong directory chung để thử bảo mật; dùng temp sandbox.

### 20.2. Test security không chỉ có một cờ

Với threat model attacker có thể thay directory entries, bổ sung test có symlink cha, symlink ở entry cuối, dangling, thay link sau check, path `..`, absolute path, provider khác và quyền truy cập. Nếu chỉ có một test `isSymbolicLink(path)` rồi `readAttributes(path, NOFOLLOW)`, đừng tuyên bố đã kiểm hết race.

## 21. Quy trình thực hành cho một công cụ kiểm kê symlink

Giả sử ứng dụng muốn liệt kê **những link entry** trong một directory do service kiểm soát mà không cần mở target:

1. **Chọn root** đã xác thực và có quyền truy cập.
2. Liệt kê những entry theo API directory traversal phù hợp, tránh follow link targets khi không cần.
3. Với mỗi entry, gọi `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)`.
4. Kiểm tra `attrs.isSymbolicLink()`; nếu false, không coi entry là link.
5. Khi cần biết target path được lưu, gọi `Files.readSymbolicLink(path)` và xử lý lỗi.
6. Nếu cần xác minh target tồn tại, đó là **một thao tác khác** (follow) và phải có chính sách/quyền riêng.
7. Nếu cần phân biệt dangling, so `exists(link)` và `exists(link, NOFOLLOW)`, nhưng không coi đó là kết quả bất biến.
8. Không tự động truy cập hoặc xóa target chỉ vì link trỏ tới nó.
9. Nếu phải dọn dangling link, chỉ xóa **chính link entry** do service được ủy quyền quản lý.
10. Ghi rõ các lỗi `IOException`/permission; kết quả kiểm kê có thể chưa đầy đủ.
11. Không cung cấp target path hoặc metadata nhạy cảm cho caller không được phép.
12. Nếu cần bảo đảm chống symlink races, đưa bài toán xuống cơ chế filesystem access/dir handles phù hợp thay vì tin một precheck.

### 21.1. Khi chỉ cần biết entry nào là symlink

`Files.isSymbolicLink(path)` là API gọn, không cần tự gọi `readAttributes(...NOFOLLOW)` chỉ để kiểm tra loại. Nhưng nếu cần **nguyên nhân lỗi** hoặc nhiều metadata liên quan, typed read có exception là công cụ tốt hơn.

### 21.2. Khi cần làm việc với link mục tiêu

Nếu nghiệp vụ thực sự muốn đi đến target để đọc dữ liệu, việc cố ý **follow** có thể đúng; `NOFOLLOW_LINKS` không phải “luôn tốt hơn”. Cần viết rõ policy: “đọc object ở target” hay “đọc entry link”, rồi chọn API tương ứng.

## 22. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Follow hay NOFOLLOW?** Một symlink `alias.txt` trỏ tới regular file `real.txt`. `Files.isRegularFile(alias)` và `Files.isRegularFile(alias, NOFOLLOW_LINKS)` có thể trả khác nhau như thế nào?

**Bài 2 — Dangling link.** Sau khi xóa `real.txt`, `alias.txt` còn tồn tại. Vì sao `Files.exists(alias)` có thể false còn `Files.exists(alias, NOFOLLOW_LINKS)` có thể true?

**Bài 3 — Ba trạng thái existence.** Tại sao `Files.notExists(path)` không luôn bằng `!Files.exists(path)`? Hãy đưa ra một trường hợp quyền/I/O khiến cả hai false.

**Bài 4 — Loại entry.** So `Files.isSymbolicLink(path)` với `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()`. Cách nào cho lỗi rõ hơn khi thiếu quyền?

**Bài 5 — Typed metadata.** Đọc `size`, `isRegularFile`, `isSymbolicLink` và `lastModifiedTime` của chính link bằng `BasicFileAttributes`. Vì sao size không phải luôn kích thước target?

**Bài 6 — Named metadata.** Dùng `Files.getAttribute(alias,"basic:isSymbolicLink", NOFOLLOW_LINKS)`. Kiểu runtime của value là gì? Vì sao cần cast khi dùng named access?

**Bài 7 — Wildcard.** Gọi `Files.readAttributes(alias,"basic:*",NOFOLLOW_LINKS)`. Vì sao không nên hardcode thứ tự key Map?

**Bài 8 — View.** Lấy `BasicFileAttributeView` với NOFOLLOW, gọi `readAttributes()`. Phân biệt việc tạo view với việc đọc metadata.

**Bài 9 — Update mtime.** Hãy viết `Files.setAttribute(alias,"basic:lastModifiedTime",FileTime,NOFOLLOW_LINKS)`. Vì sao code đúng về chữ ký vẫn có thể lỗi trên provider?

**Bài 10 — Invalid overload.** Vì sao `Files.size(path,NOFOLLOW_LINKS)` không biên dịch? Cách thay thế nếu muốn size của symlink entry?

**Bài 11 — Invalid mtime setter.** Vì sao `Files.setLastModifiedTime(path,time,NOFOLLOW_LINKS)` không biên dịch? Có hai API thay thế nào?

**Bài 12 — Đường dẫn trung gian.** Một `shortcut` là symlink tới directory `real`, còn `shortcut/data.txt` có entry cuối là regular file. NOFOLLOW có ngăn resolve qua shortcut không? Vì sao?

**Bài 13 — Relative target.** `Files.readSymbolicLink(alias)` trả `Path` tương đối `"target.txt"`. Nó được diễn giải theo directory nào? Nó có tự xác minh target tồn tại không?

**Bài 14 — Cleanup dangling links.** Vì sao `if (Files.exists(link)) Files.deleteIfExists(link)` có thể để lại dangling link? Viết policy thích hợp cho mục đích xóa chính link entry.

**Bài 15 — Provider support.** Viết test tạo symlink trong temp dir; khi bị từ chối, bỏ qua nhánh symlink-specific một cách minh bạch. Vì sao không nên giả định Windows luôn cho hoặc luôn cấm symlink?

**Bài 16 — POSIX.** Khi nào `Files.getPosixFilePermissions(path,NOFOLLOW_LINKS)` có thể ném `UnsupportedOperationException`? Đâu là vấn đề view support, đâu là quyền?

**Bài 17 — Bảo mật.** Một API dùng `base.resolve(userInput).normalize().startsWith(base)` rồi `readAttributes(..., NOFOLLOW_LINKS)`. Vì sao vẫn có thể bị lừa bởi symlink trong directory cha hoặc race?

**Bài 18 — Snapshot.** Một process đọc `isSymbolicLink` rồi `getAttribute`. Một process khác thay entry giữa hai lời gọi. Java có bảo đảm hai kết quả nói về cùng filesystem object không?

**Bài 19 — Copy và walk.** Phân biệt `LinkOption.NOFOLLOW_LINKS` với `FileVisitOption.FOLLOW_LINKS`; trường hợp nào bạn dùng mỗi cái?

**Bài 20 — Lựa chọn thiết kế.** Một ứng dụng backup muốn đọc **target content**; một công cụ inventory muốn đọc **link metadata**. Bên nào nên follow, bên nào nên nofollow? Liệt kê các hạn chế/cần xác minh.

### Đáp án định hướng

- **Bài 1:** Follow xem target regular file; NOFOLLOW xem chính link, không coi entry là regular file.
- **Bài 2:** Target đã mất nhưng link entry vẫn có.
- **Bài 3:** Trạng thái không xác định có thể làm cả hai phép hỏi false.
- **Bài 4:** `isSymbolicLink` trả boolean; typed `readAttributes` có thể ném `IOException` và cho nhiều metadata hơn.
- **Bài 5:** Với NOFOLLOW, metadata thuộc link entry, size có semantics provider-specific.
- **Bài 6:** `Boolean` nằm trong `Object`.
- **Bài 7:** Map không có contract hiển thị theo thứ tự tên request; tự sort khi cần.
- **Bài 8:** View là giao diện thao tác; `readAttributes()` mới đọc metadata.
- **Bài 9:** Set metadata của symlink có thể bị filesystem từ chối hoặc không hỗ trợ.
- **Bài 10:** Không có overload; dùng `readAttributes(...,NOFOLLOW).size()`.
- **Bài 11:** Dùng `Files.setAttribute` với NOFOLLOW hoặc typed view được lấy với NOFOLLOW rồi `setTimes`.
- **Bài 12:** Không; NOFOLLOW không có nghĩa cấm resolve mọi symlink trung gian.
- **Bài 13:** Relative target gắn với directory chứa link khi resolve; `readSymbolicLink` chỉ đọc path đã lưu.
- **Bài 14:** Default `exists` có thể kiểm tra target vắng và trả false; dọn link entry bằng API xóa theo contract mà không cần precheck không cần thiết.
- **Bài 15:** Khả năng symlink phụ thuộc quyền/provider/configuration.
- **Bài 16:** POSIX là optional view; thiếu hỗ trợ khác thiếu quyền.
- **Bài 17:** Lexical path check và NOFOLLOW không loại bỏ intermediate symlink hay TOCTOU.
- **Bài 18:** Không có snapshot/lock mặc định qua các lời gọi riêng.
- **Bài 19:** `LinkOption` dùng cho các phương thức file/metadata/copy có nhận option; `FileVisitOption` dùng khi duyệt cây với `walkFileTree`.
- **Bài 20:** Backup target có thể cần follow; inventory entry cần NOFOLLOW, nhưng cả hai phải xét authorization/symlink policy.

## 23. Checklist code review

- [ ] Xác định rõ đang cần metadata **link entry** hay **target**.
- [ ] Kiểm tra API có thực sự nhận `LinkOption...`.
- [ ] Với `Files.exists`/`notExists`, xử lý được trạng thái không xác minh.
- [ ] Không coi `exists(link) == false` là bằng chứng bản thân link đã biến mất.
- [ ] Dùng `Files.isSymbolicLink` khi chỉ cần phân loại link entry.
- [ ] Dùng `Files.readAttributes(...,NOFOLLOW_LINKS)` khi cần typed metadata và lỗi rõ.
- [ ] Nếu dùng named access, hiểu `view:name` và các kiểu `Boolean`, `Long`, `FileTime`.
- [ ] Không nhầm `Files.size` có overload NOFOLLOW.
- [ ] Không nhầm `Files.setLastModifiedTime` có overload NOFOLLOW.
- [ ] Khi chỉnh mtime link, dùng `setAttribute` hoặc `FileAttributeView` với NOFOLLOW và xử lý unsupported/errors.
- [ ] Không coi attribute view là lock hoặc snapshot atomic.
- [ ] Không giả định `NOFOLLOW` cấm symlinks trong những path components trung gian.
- [ ] Dùng `Files.readSymbolicLink` khi cần đọc stored target Path, không coi nó là chứng cứ target tồn tại.
- [ ] Không nhầm `FileVisitOption.FOLLOW_LINKS` với `LinkOption.NOFOLLOW_LINKS`.
- [ ] Không xóa target khi chỉ có chủ ý dọn link entry.
- [ ] Có test regular/missing/symlink/dangling và trường hợp symlink không hỗ trợ.
- [ ] Dùng temp directory, không chạm file nhạy cảm hoặc path cá nhân.
- [ ] Kiểm soát quyền, base path, symlink races và metadata privacy theo threat model.
- [ ] Biết API NIO.2 nói trên vẫn hiện hành trên Java 17+.

## 24. Tài liệu chính thức còn hiệu lực

- [Java SE 17 — `LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): enum `NOFOLLOW_LINKS` và các interface `OpenOption`, `CopyOption`.
- [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `isRegularFile`, `isDirectory`, `isSymbolicLink`, `readAttributes`, `getAttribute`, `setAttribute`, `getFileAttributeView`, `getLastModifiedTime`, `readSymbolicLink`, `deleteIfExists`.
- [Java SE 17 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): metadata typed với `isSymbolicLink`, `isRegularFile`, `size`, timestamps, fileKey.
- [Java SE 17 — `BasicFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): typed view, tên `basic` và `setTimes`.
- [Java SE 17 — `FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html): kiểu timestamp cho metadata.
- [Java SE 17 — `PosixFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html): view quyền POSIX tùy provider.
- [Java SE 17 — `FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` thuộc tree traversal.
- [Java SE 17 — `SecureDirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): API directory-relative hỗ trợ giảm một số race trong provider phù hợp.
- [Java SE 17 — `Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith` và path semantics.

**Kết luận:** `LinkOption.NOFOLLOW_LINKS` giúp bạn **chọn đọc/ghi metadata của chính symbolic link entry** thay vì mặc định đi theo target, với những API có hỗ trợ tùy chọn ấy. Dùng nó khi kiểm tra dangling links, phân loại entries, đọc `BasicFileAttributes` hoặc truy cập `FileAttributeView` theo nhu cầu. Nhưng **không phải mọi API có overload NOFOLLOW; không phải mọi filesystem cho sửa thuộc tính link; không phải mọi path component đều được bảo vệ khỏi symlink traversal; và không có bảo đảm snapshot/race-free chỉ nhờ một flag**. Chọn chính sách follow hay nofollow theo đúng nghiệp vụ, xử lý lỗi tường minh và áp dụng biện pháp filesystem security phù hợp khi làm việc với path chưa tin cậy.
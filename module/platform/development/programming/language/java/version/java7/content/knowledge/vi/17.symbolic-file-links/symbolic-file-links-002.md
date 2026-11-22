# Tạo và đọc đích liên kết tượng trưng trong Java

## 1. Tổng quan: liên kết tượng trưng là gì?

Trong hệ thống tệp, **symbolic link** (symlink, liên kết tượng trưng) là một entry mang một **đường dẫn tham chiếu đến một entry khác**. Một liên kết có thể trỏ tới file, thư mục, một liên kết khác, hoặc thậm chí một đường dẫn mà tại thời điểm tạo **chưa tồn tại**.

Ví dụ:

~~~text
workspace/
├── original.txt
└── shortcut.txt -> original.txt
~~~

`shortcut.txt` là link, còn `original.txt` là target. Hai API cốt lõi của Java NIO.2:

~~~java
Files.createSymbolicLink(link, target);
Path storedTarget = Files.readSymbolicLink(link);
~~~

Đây là hai dòng minh họa trong một phương thức với `link` và `target` kiểu `Path`. **Thứ tự tham số khi tạo là `link` trước, `target` sau.**

Khác biệt quan trọng:

- `Files.createSymbolicLink` tạo **entry link**, không sao chép nội dung file và không tự tạo file đích.
- `Files.readSymbolicLink` đọc **đường dẫn đích được lưu** trong link và trả một `Path`. Nó **không đọc nội dung target**.
- Khi mở `Files.readString(link, UTF_8)`, hệ thống có thể **theo link** để đọc file đích, đó là thao tác khác với `readSymbolicLink`.
- Symlink là tính năng **phụ thuộc FileSystem provider và quyền OS**, không được đảm bảo mọi máy có thể tạo.

Bài nằm trong chủ đề **Liên kết tệp** của Java 7. Hai API trên, `Path`, `LinkOption.NOFOLLOW_LINKS`, `Files.isSymbolicLink` và `Files.isSameFile` đã có từ **Java 7** và vẫn được hỗ trợ trong Java hiện đại. Các chương trình đầy đủ trong bài dùng **Java 17+** và `Files.readString/writeString` của Java 11+ để viết ví dụ dễ đọc.

### 1.1. Học xong bài này cần nắm gì?

1. Tạo symbolic link dùng `Files.createSymbolicLink(link, target)`, có khả năng target tuyệt đối hoặc tương đối.
2. Đọc đường dẫn target bằng `Files.readSymbolicLink(link)`, không nhầm với đọc dữ liệu file.
3. Hiểu **relative target tính từ thư mục chứa link**, không tính từ process working directory.
4. Phân biệt link entry và file target qua `isSymbolicLink`, `exists(..., NOFOLLOW_LINKS)`, `readAttributes`.
5. Biết tạo/đọc **dangling link**, link chain, link tới directory, và hành vi khi xóa link.
6. Phân loại các lỗi `NotLinkException`, `NoSuchFileException`, `FileAlreadyExistsException`, `UnsupportedOperationException`, `IOException`.
7. Biết kiểm tra “hai Path cùng file thực” bằng `Files.isSameFile`, phân biệt với `Path.equals()`.
8. Hiểu giới hạn Windows/Linux/macOS, quyền tạo symlink, các nguy cơ bảo mật và TOCTOU.
9. Viết test Java chạy được và chỉ báo PASS sau khi thực sự tạo và đọc liên kết trên filesystem hỗ trợ.

**Thông tin kiểm thử:** Các chương trình được biên dịch bằng `javac -encoding UTF-8 --release 17` và chạy thành công trên OpenJDK 21/Linux cho phép tạo symlink. Một môi trường Windows được kiểm thử riêng đã trả `FileSystemException` khi tạo symlink. Các chương trình có nhánh `symlinkTest=SKIPPED` khi tạo liên kết thất bại. **SKIPPED không chứng minh symlink hoạt động ở runner đó.**

## 2. Chữ ký API và hợp đồng

### 2.1. Tạo liên kết

~~~java
public static Path createSymbolicLink(
        Path link,
        Path target,
        FileAttribute<?>... attrs
) throws IOException
~~~

Đây là cách trình bày chữ ký API, không phải class Java độc lập. Theo Javadoc:

- **`link`:** Đường dẫn của entry symbolic link mới.
- **`target`:** Đường dẫn được lưu trong liên kết; có thể tuyệt đối/tương đối, và theo hợp đồng có thể chưa tồn tại.
- **`attrs`:** Các thuộc tính được yêu cầu đặt khi tạo, nếu provider hỗ trợ; là varargs tùy chọn.
- **Giá trị trả về:** chính đường dẫn `link`.
- Nếu `link` đã tồn tại, thao tác thất bại; `FileAlreadyExistsException` là một loại cụ thể có thể xảy ra.
- Đây là **optional operation**. Nếu không được hỗ trợ có thể ném `UnsupportedOperationException`. Nếu quyền hoặc FileStore từ chối, có thể ném `IOException`.

Không nên tạo symlink bằng cách tự viết một file .txt chứa path. File văn bản như vậy không có semantics của symbolic link trong hệ thống tệp.

### 2.2. Đọc target đã lưu

~~~java
public static Path readSymbolicLink(Path link)
        throws IOException
~~~

Method này:

- Đọc target của **entry symbolic link**.
- Trả một `Path` gắn với cùng FileSystem như link.
- **Không yêu cầu target tồn tại**.
- Không tự đọc byte/content file đích.
- Không tự trả “file cuối cùng” nếu link trỏ đến một **symlink khác**.
- Có thể ném `NotLinkException` nếu path không phải symlink (một loại lỗi cụ thể *optional* theo Javadoc), hoặc `IOException` khác.
- Có thể ném `UnsupportedOperationException` nếu provider không hỗ trợ.

Nguồn hiện hành: [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html).

### 2.3. Ba kiểu “đích” không được đánh đồng

| Thuật ngữ | Nội dung | Cách xác định |
| --- | --- | --- |
| Target **được lưu** | Path ghi bên trong entry link, ví dụ `../data.txt` | `Files.readSymbolicLink(link)` |
| Target **ghép theo cha link** | Path biểu diễn sau khi ghép với thư mục chứa link | `link.getParent().resolve(stored).normalize()` với stored tương đối |
| File **thực tại thời điểm kiểm tra** | Đối tượng filesystem mà một path sau khi theo symlink chỉ đến | `Files.isSameFile(link,target)`, `link.toRealPath()` |

Phép `resolve(...).normalize()` là **xử lý path từ vựng**, không phải một phép đọc filesystem và không đảm bảo target có thật hoặc an toàn trước symbolic-link chain. `toRealPath` và `isSameFile` cần tương tác filesystem, có thể ném `IOException`; kết quả là theo **thời điểm gọi**, không khóa hệ thống tệp.

## 3. Ví dụ 1 — Tạo target tuyệt đối

Bài toán: có file `original.txt` và muốn tạo entry `shortcut.txt` tham chiếu tới **đường dẫn tuyệt đối** của file.

Tạo `AbsoluteSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class AbsoluteSymlinkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("absolute-link-");
        Path target = root.resolve("original.txt");
        Path link = root.resolve("shortcut.txt");

        try {
            Files.writeString(
                    target, "Xin chào Java", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(link, target.toAbsolutePath());
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            Path stored = Files.readSymbolicLink(link);
            System.out.println("isSymbolicLink=" +
                    Files.isSymbolicLink(link));
            System.out.println("storedAbsolute=" +
                    stored.isAbsolute());
            System.out.println("storedEqualsTarget=" +
                    stored.equals(target.toAbsolutePath()));
            System.out.println("sameFile=" +
                    Files.isSameFile(link, target));
            System.out.println("contentEqual=" +
                    "Xin chào Java".equals(
                            Files.readString(
                                    link, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Lưu source UTF-8 và chạy:

~~~bash
javac -encoding UTF-8 --release 17 AbsoluteSymlinkDemo.java
java AbsoluteSymlinkDemo
~~~

Stdout đã kiểm chứng trên Linux hỗ trợ link:

~~~text
isSymbolicLink=true
storedAbsolute=true
storedEqualsTarget=true
sameFile=true
contentEqual=true
~~~

Nếu không thể tạo symbolic link:

~~~text
symlinkTest=SKIPPED
~~~

**Diễn giải:**

1. `Files.createTempDirectory` tạo vùng thử riêng, không sửa thư mục dự án.
2. `Files.writeString` tạo file target bằng UTF-8.
3. `createSymbolicLink(link, target.toAbsolutePath())` tạo một **link entry** chứa target tuyệt đối.
4. `readSymbolicLink(link)` đọc lại stored target; `stored.isAbsolute()` xác nhận kiểu path được lưu.
5. `isSameFile(link,target)` kiểm tra cùng thực thể file trên filesystem. Không thay nó bằng `link.equals(target)`.
6. `Files.readString(link)` **theo link** để đọc nội dung target. Nó không phải API đọc “đích liên kết”.
7. `finally` xóa link trước, sau đó target và root. Xóa link không tự xóa target.
8. Nếu create fail, mã in SKIPPED rồi vẫn đi qua `finally` để dọn fixture.

**Nhược điểm của absolute target:** Nếu toàn bộ thư mục được chuyển sang vị trí mới, link chứa target tuyệt đối cũ có thể đứt. Hãy lựa chọn dạng target theo vòng đời dữ liệu thay vì luôn ép tuyệt đối.

## 4. Ví dụ 2 — Target tương đối tính từ thư mục chứa link

Cấu trúc:

~~~text
root/
├── data.txt
└── docs/
    └── shortcut.txt -> ../data.txt
~~~

Đích tương đối `../data.txt` được hiểu từ **`docs/`**, tức thư mục chứa `shortcut.txt`; **không phải từ working directory của tiến trình Java**.

Tạo `RelativeSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class RelativeSymlinkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("relative-link-");
        Path docs = Files.createDirectory(root.resolve("docs"));
        Path target = root.resolve("data.txt");
        Path link = docs.resolve("shortcut.txt");
        Path relativeTarget = Path.of("..", "data.txt");

        try {
            Files.writeString(target, "Tiếng Việt", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(link, relativeTarget);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            Path stored = Files.readSymbolicLink(link);
            System.out.println("relativeStored=" + !stored.isAbsolute());
            System.out.println("storedUnchanged=" +
                    stored.equals(relativeTarget));
            System.out.println("lexicalTargetMatches=" +
                    link.getParent().resolve(stored)
                            .normalize().equals(target));
            System.out.println("sameFile=" +
                    Files.isSameFile(link, target));
            System.out.println("textEquals=" +
                    "Tiếng Việt".equals(
                            Files.readString(
                                    link, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 RelativeSymlinkDemo.java
java RelativeSymlinkDemo
~~~

Stdout trên Linux có thể tạo link:

~~~text
relativeStored=true
storedUnchanged=true
lexicalTargetMatches=true
sameFile=true
textEquals=true
~~~

Nếu setup không tạo được link:

~~~text
symlinkTest=SKIPPED
~~~

**Giải thích:**

- Link ở `docs/shortcut.txt`, còn target thật ở `root/data.txt`.
- Stored path là `..` rồi `data.txt`, không tự bị chuyển thành absolute.
- `link.getParent().resolve(stored).normalize()` cho vị trí biểu diễn target đúng với fixture.
- `Files.isSameFile` kiểm chứng rằng link đang tham chiếu tới chính file target ở thời điểm gọi.
- **Sai lầm phổ biến:** Gọi `stored.toAbsolutePath()` rồi tin rằng kết quả là target. Với stored relative, phương pháp ấy có thể lấy mốc từ working directory, không phải thư mục chứa link.

### 4.1. Tạo relative target bằng `relativize`

Khi đã có path vị trí link và target trên cùng filesystem:

~~~java
Path link = docs.resolve("shortcut.txt");
Path target = root.resolve("data.txt");

Path relative = link.getParent().relativize(target);
Files.createSymbolicLink(link, relative);
~~~

Đây là **đoạn trong một phương thức** có `docs` và `root` được khai báo trước. Mốc phải là `link.getParent()`, không phải path của **file link**. `relativize` có thể ném `IllegalArgumentException` nếu hai path không tương thích về dạng absolute/relative hoặc root.

Chọn relative target khi link và target dự kiến giữ **quan hệ cấu trúc** qua việc chuyển toàn bộ thư mục, nhưng phải kiểm tra trường hợp đường dẫn chứa `..` có thể vượt ra ngoài root được phép.

## 5. Ví dụ 3 — Dangling link: target chưa tồn tại

Cấu trúc:

~~~text
root/
└── alias.txt -> future.txt
~~~

Entry `alias.txt` có thể tồn tại dù `future.txt` chưa có. Đây là **dangling/broken symlink**.

| Kiểm tra | Trước khi tạo `future.txt` |
| --- | --- |
| `Files.isSymbolicLink(alias)` | Có thể true |
| `Files.exists(alias)` | Thường false vì mặc định theo link |
| `Files.exists(alias, NOFOLLOW_LINKS)` | Thường true vì entry link còn |
| `Files.readSymbolicLink(alias)` | Trả `future.txt` |
| `Files.readString(alias, UTF_8)` | Thất bại vì target chưa có |

**Trên filesystem cụ thể** các lời gọi `exists` có thể trả false khi không xác định được tồn tại do quyền hoặc I/O. Không xem false là bằng chứng tuyệt đối.

Tạo file `DanglingSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class DanglingSymlinkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("dangling-link-");
        Path link = root.resolve("alias.txt");
        Path target = root.resolve("future.txt");

        try {
            try {
                Files.createSymbolicLink(link, Path.of("future.txt"));
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            System.out.println("linkIsSymbolic=" +
                    Files.isSymbolicLink(link));
            System.out.println("existsFollow=" + Files.exists(link));
            System.out.println("existsNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("storedTarget=" +
                    Files.readSymbolicLink(link));

            boolean readFailed = false;
            try {
                Files.readString(link, StandardCharsets.UTF_8);
            } catch (NoSuchFileException ex) {
                readFailed = true;
            }
            System.out.println("readBeforeTarget=" +
                    (readFailed ? "MISSING" : "OPENED"));

            Files.writeString(target, "ready", StandardCharsets.UTF_8);
            System.out.println("readAfterTarget=" +
                    Files.readString(link, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 DanglingSymlinkDemo.java
java DanglingSymlinkDemo
~~~

Stdout đã kiểm chứng trên Linux:

~~~text
linkIsSymbolic=true
existsFollow=false
existsNoFollow=true
storedTarget=future.txt
readBeforeTarget=MISSING
readAfterTarget=ready
~~~

Nếu không được phép tạo link:

~~~text
symlinkTest=SKIPPED
~~~

**Điểm học tập:**

1. Java API cho phép target chưa tồn tại, nếu provider/OS hỗ trợ tạo kiểu link đó.
2. `readSymbolicLink` vẫn đọc stored target vì nó đọc entry link, không cần mở file đích.
3. `exists` mặc định khác `exists(...NOFOLLOW_LINKS)` ở dữ liệu dangling.
4. Khi tạo file target ở vị trí mà link tham chiếu, chính link cũ có thể lập tức trở nên hữu dụng mà không cần tạo lại.
5. Không dùng `!Files.exists(alias)` để khẳng định tên link chưa có: dangling link trả false khi *follow*, nhưng entry **đã tồn tại** và create cùng tên vẫn có thể báo duplicate.
6. `NoSuchFileException` trong demo là loại cụ thể đã kiểm thử; chương trình sản phẩm vẫn phải xử lý `IOException` khác khi đọc.

## 6. Entry link và target có metadata khác nhau

Với cùng path link, bạn có thể yêu cầu **thuộc tính của entry link** hoặc **thuộc tính của file target**.

~~~java
BasicFileAttributes linkAttrs = Files.readAttributes(
        link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
BasicFileAttributes targetAttrs = Files.readAttributes(
        link, BasicFileAttributes.class);
~~~

Đây là đoạn trong phương thức có `link`; import `java.nio.file.attribute.BasicFileAttributes` và `java.nio.file.*`.

- `linkAttrs.isSymbolicLink()` có thể true.
- `linkAttrs.isRegularFile()` có thể false, vì bản thân entry là link.
- `targetAttrs.isRegularFile()` có thể true, vì mặc định đã theo link tới file thường.
- `Files.isSymbolicLink(link)` giúp kiểm tra loại entry nhanh.
- Khi cần phân biệt lỗi I/O với “không phải symbolic link”, dùng `readAttributes`, bởi một số phép kiểm tra boolean có thể false khi không xác định được thuộc tính.

### 6.1. Ví dụ 4 — Xóa entry link nhưng giữ target

Tạo `LinkTypeAndDeleteDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class LinkTypeAndDeleteDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("type-link-");
        Path target = root.resolve("actual.txt");
        Path link = root.resolve("shortcut.txt");

        try {
            Files.writeString(target, "abc", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(link, target.toAbsolutePath());
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            BasicFileAttributes linkAttrs = Files.readAttributes(
                    link, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes targetAttrs = Files.readAttributes(
                    link, BasicFileAttributes.class);

            System.out.println("isLink=" + linkAttrs.isSymbolicLink());
            System.out.println("followIsRegular=" +
                    targetAttrs.isRegularFile());
            System.out.println("nofollowIsRegular=" +
                    linkAttrs.isRegularFile());

            Files.delete(link);
            System.out.println("targetSurvives=" +
                    Files.isRegularFile(target));
            System.out.println("linkGone=" +
                    !Files.exists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 LinkTypeAndDeleteDemo.java
java LinkTypeAndDeleteDemo
~~~

Stdout trên Linux:

~~~text
isLink=true
followIsRegular=true
nofollowIsRegular=false
targetSurvives=true
linkGone=true
~~~

`Files.delete(link)` xóa **entry liên kết**; `target` vẫn là file thật. Nhưng chú ý: nếu bạn dùng path link để **ghi dữ liệu**, thao tác I/O có thể **theo link và sửa target**. Vì vậy “xóa entry không xóa target” không đồng nghĩa “mọi thao tác thông qua tên link đều vô hại”.

## 7. Ví dụ 5 — Chuỗi nhiều symbolic links

Một chuỗi:

~~~text
root/
├── payload.txt
├── middle -> payload.txt
└── outer  -> middle
~~~

`Files.readSymbolicLink(outer)` chỉ đọc **target của outer**, tức `middle`. Nó không tự chạy qua middle và trả `payload.txt`. Khi muốn biết hai path trỏ **cùng một file cuối cùng**, có thể dùng `Files.isSameFile(outer, target)` hoặc `outer.toRealPath()` khi có khả năng giải quyết đường dẫn.

Tạo `LinkChainDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class LinkChainDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("chain-link-");
        Path target = root.resolve("payload.txt");
        Path middle = root.resolve("middle");
        Path outer = root.resolve("outer");

        try {
            Files.writeString(
                    target, "chain works", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(middle, Path.of("payload.txt"));
                Files.createSymbolicLink(outer, Path.of("middle"));
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            System.out.println("immediateTarget=" +
                    Files.readSymbolicLink(outer));
            System.out.println("secondTarget=" +
                    Files.readSymbolicLink(middle));
            System.out.println("sameFile=" +
                    Files.isSameFile(outer, target));
            System.out.println("readWorks=" +
                    "chain works".equals(
                            Files.readString(
                                    outer, StandardCharsets.UTF_8)));
            System.out.println("realPathEquals=" +
                    outer.toRealPath().equals(target.toRealPath()));
        } finally {
            Files.deleteIfExists(outer);
            Files.deleteIfExists(middle);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 LinkChainDemo.java
java LinkChainDemo
~~~

Stdout Linux:

~~~text
immediateTarget=middle
secondTarget=payload.txt
sameFile=true
readWorks=true
realPathEquals=true
~~~

Nếu filesystem không cho tạo link:

~~~text
symlinkTest=SKIPPED
~~~

**Đừng tự viết vòng theo link ngây thơ:**

~~~java
Path current = link;
while (Files.isSymbolicLink(current)) {
    current = Files.readSymbolicLink(current);
}
~~~

Đây là **đoạn minh họa không an toàn/không đầy đủ**: target tương đối phải được giải quyết từ cha của **link hiện tại**, không phải từ process working directory. Chuỗi liên kết cũng có thể tạo **vòng lặp**. Nếu chỉ cần stored target, gọi `readSymbolicLink` **một lần**. Nếu cần xác định đường dẫn file thực ở thời điểm gọi, ưu tiên `toRealPath` hoặc kiểm tra identity theo filesystem, kèm xử lý IOException.

## 8. Ví dụ 6 — Lỗi NotLink, missing và duplicate

Các trạng thái:

- `readSymbolicLink(plain)` với file thường có thể ném `NotLinkException`.
- `readSymbolicLink(absent)` với path chưa có có thể ném `NoSuchFileException`.
- `createSymbolicLink(alias,target)` khi `alias` đã tồn tại có thể ném `FileAlreadyExistsException`.
- `IOException` có thể phát sinh vì permission, parent thiếu, hoặc lỗi filesystem; không suy luận mọi lỗi là duplicate.

Tạo `SymlinkErrorsDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;

public class SymlinkErrorsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("errors-link-");
        Path plain = root.resolve("plain.txt");
        Path alias = root.resolve("alias.txt");
        Path target = root.resolve("target.txt");

        try {
            Files.createFile(plain);
            Files.createFile(target);

            boolean notLink = false;
            try {
                Files.readSymbolicLink(plain);
            } catch (NotLinkException ex) {
                notLink = true;
            }
            System.out.println("plainNotLink=" + notLink);

            boolean missing = false;
            try {
                Files.readSymbolicLink(
                        root.resolve("absent.txt"));
            } catch (NoSuchFileException ex) {
                missing = true;
            }
            System.out.println("missingLink=" + missing);

            try {
                Files.createSymbolicLink(alias, target.toAbsolutePath());
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            boolean duplicateRejected = false;
            try {
                Files.createSymbolicLink(alias, target.toAbsolutePath());
            } catch (FileAlreadyExistsException ex) {
                duplicateRejected = true;
            }
            System.out.println("duplicateRejected=" + duplicateRejected);
            System.out.println("targetStillExists=" +
                    Files.isRegularFile(target));
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(target);
            Files.deleteIfExists(plain);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SymlinkErrorsDemo.java
java SymlinkErrorsDemo
~~~

Stdout Linux khi hỗ trợ symlink:

~~~text
plainNotLink=true
missingLink=true
duplicateRejected=true
targetStillExists=true
~~~

Nếu chỉ giai đoạn tạo symlink thất bại, chương trình đã in hai kết quả đầu rồi in:

~~~text
plainNotLink=true
missingLink=true
symlinkTest=SKIPPED
~~~

**Quy tắc xử lý:** Các subclass được ghi là *optional specific exceptions* trong Javadoc có thể khác nhau giữa filesystem providers. Code sản phẩm cần phân loại theo nghiệp vụ và giữ nguyên cause, không so sánh exception message chứa OS path.

### 8.1. Không dùng `exists` làm ràng buộc chống race

Đoạn code sau không đủ cho chính sách “chỉ tạo link nếu chưa có”:

~~~java
if (!Files.exists(link)) {
    Files.createSymbolicLink(link, target);
}
~~~

**Hai lý do:** `exists(link)` theo link có thể false đối với dangling link **đã có entry**; và filesystem có thể đổi trạng thái giữa bước kiểm tra và bước tạo (**TOCTOU**). Cứ gọi API tạo link được thiết kế để từ chối tên đã tồn tại và xử lý kết quả/lỗi. Đừng xoá entry cũ theo cảm tính để “sửa” lỗi trùng.

## 9. Ví dụ 7 — Link tới thư mục và tác động lên traversal

Symbolic link không chỉ trỏ tới file. Giả sử:

~~~text
root/
├── actual/
│   └── marker.txt
└── alias -> actual/
~~~

Nếu provider hỗ trợ directory symlink, `Files.isDirectory(alias)` có thể true do theo target, trong khi `Files.isDirectory(alias, NOFOLLOW_LINKS)` false vì entry chính là symlink.

Tạo `DirectorySymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class DirectorySymlinkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("dir-link-");
        Path actual = Files.createDirectory(root.resolve("actual"));
        Path link = root.resolve("alias");
        Path marker = actual.resolve("marker.txt");

        try {
            Files.writeString(marker, "hello", StandardCharsets.UTF_8);
            try {
                Files.createSymbolicLink(link, Path.of("actual"));
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            System.out.println("linkIsDirectory=" +
                    Files.isDirectory(link));
            System.out.println("nofollowIsDirectory=" +
                    Files.isDirectory(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("readThroughLink=" +
                    "hello".equals(
                            Files.readString(
                                    link.resolve("marker.txt"),
                                    StandardCharsets.UTF_8)));

            AtomicInteger noFollowDirs = new AtomicInteger();
            AtomicInteger noFollowLinks = new AtomicInteger();

            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path p, BasicFileAttributes attrs) {
                    noFollowDirs.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path p, BasicFileAttributes attrs) {
                    if (attrs.isSymbolicLink()) {
                        noFollowLinks.incrementAndGet();
                    }
                    return FileVisitResult.CONTINUE;
                }
            });

            AtomicInteger followDirs = new AtomicInteger();
            Files.walkFileTree(
                    root, EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path p, BasicFileAttributes attrs) {
                    followDirs.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("nofollowDirs=" +
                    noFollowDirs.get());
            System.out.println("nofollowLinks=" +
                    noFollowLinks.get());
            System.out.println("followDirs=" +
                    followDirs.get());
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(marker);
            Files.deleteIfExists(actual);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 DirectorySymlinkDemo.java
java DirectorySymlinkDemo
~~~

Stdout Linux:

~~~text
linkIsDirectory=true
nofollowIsDirectory=false
readThroughLink=true
nofollowDirs=2
nofollowLinks=1
followDirs=3
~~~

Giải thích:

- Khi không theo symlink, `walkFileTree` vào hai directory thật `root` và `actual`, còn `alias` được xem là entry link.
- Với `FOLLOW_LINKS`, walker vào `actual` qua path thật và qua alias, nên ba lượt `preVisitDirectory` (root + actual + alias) trong fixture này.
- Duyệt trùng target **không tự động** là chu trình; link trỏ tới **tổ tiên hiện tại** mới có thể gây `FileSystemLoopException` khi follow.
- Nếu không cần target của symlink, giữ chính sách không follow để tránh quét ngoài root hoặc vòng lặp không mong muốn.

## 10. Ví dụ 8 — Relative link vẫn hoạt động khi chuyển cả cây

Khi link và target **cùng một thư mục** và link lưu target tương đối, di chuyển **cả thư mục** sang tên mới có thể giữ quan hệ:

~~~text
Trước:
root/before/
  real.txt
  alias.txt -> real.txt

Sau:
root/after/
  real.txt
  alias.txt -> real.txt
~~~

Tạo `MoveRelativeTreeDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class MoveRelativeTreeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("move-link-");
        Path before = Files.createDirectory(root.resolve("before"));
        Path link = before.resolve("alias.txt");
        Path target = before.resolve("real.txt");
        Path after = root.resolve("after");

        try {
            Files.writeString(
                    target, "stays relative", StandardCharsets.UTF_8);
            try {
                Files.createSymbolicLink(link, Path.of("real.txt"));
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            System.out.println("beforeMove=" +
                    "stays relative".equals(
                            Files.readString(
                                    link, StandardCharsets.UTF_8)));
            Files.move(before, after);
            System.out.println("afterMove=" +
                    "stays relative".equals(
                            Files.readString(
                                    after.resolve("alias.txt"),
                                    StandardCharsets.UTF_8)));
            System.out.println("storedTarget=" +
                    Files.readSymbolicLink(
                            after.resolve("alias.txt")));
        } finally {
            Files.deleteIfExists(after.resolve("alias.txt"));
            Files.deleteIfExists(after.resolve("real.txt"));
            Files.deleteIfExists(after);
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(before);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MoveRelativeTreeDemo.java
java MoveRelativeTreeDemo
~~~

Stdout Linux:

~~~text
beforeMove=true
afterMove=true
storedTarget=real.txt
~~~

Nếu không tạo được symlink:

~~~text
symlinkTest=SKIPPED
~~~

**Giới hạn:** Demo đổi tên/move một thư mục con trong cùng root và filesystem. Không có nghĩa mọi lần move qua volume/provider đều giữ nguyên link hoặc thực hiện được. Chỉ di chuyển **link** mà không di chuyển target có thể làm relative path trỏ sai; chỉ di chuyển **target** cũng vậy.

## 11. Chọn absolute hay relative target?

| Tiêu chí | Absolute target | Relative target |
| --- | --- | --- |
| Stored target | Toàn bộ path | Path từ cha của link |
| Đọc `readSymbolicLink` | Có thể là absolute | Có thể là relative |
| Di chuyển cả link + target cùng cây | Có thể đứt do vị trí cũ | Thường giữ nếu quan hệ đường dẫn được bảo toàn |
| Di chuyển chỉ link | Có thể vẫn tới target cố định | Có thể đứt |
| Di chuyển chỉ target | Có thể đứt | Có thể đứt |
| Khả năng trỏ ngoài root | Có | Có, nhất là qua `..` |
| Nhu cầu điển hình | Alias tới vị trí cố định, do hệ thống quản trị | Gói dữ liệu tự mang theo cấu trúc |

Chọn theo **vòng đời và ranh giới bảo mật**, không theo một quy tắc tuyệt đối. Trong gói phân phối di chuyển như một khối, relative path thường phù hợp; nếu một file cố định được quản lý độc lập, absolute path có thể dễ xác định hơn.

## 12. Các API liên quan: không nhầm mục tiêu

| API | Trả về | Đặc điểm |
| --- | --- | --- |
| `Files.readSymbolicLink(link)` | `Path` | **Stored target của một symlink entry** |
| `Files.isSymbolicLink(path)` | boolean | Kiểm tra path là entry link |
| `Files.exists(path)` | boolean | Mặc định theo link |
| `Files.exists(path, NOFOLLOW_LINKS)` | boolean | Kiểm tra bản thân entry |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | attrs | Metadata entry link, có thể IOException |
| `Files.isSameFile(a,b)` | boolean | Hai path có cùng file identity |
| `Path.normalize()` | `Path` | Chuẩn hóa cú pháp `.`/`..`, không giải quyết symlink |
| `Path.toAbsolutePath()` | `Path` | Biểu diễn absolute, không nhất thiết canonical |
| `Path.toRealPath()` | `Path` | Giải quyết filesystem path theo chính sách, mặc định theo link |
| `Files.readString(path,UTF_8)` | `String` | Đọc nội dung file sau khi theo path, không đọc stored target |
| `Files.createLink(link, existing)` | `Path` | Hard link, **khác** symbolic link |

**Hard link không phải symlink:** `Files.createLink` tạo thêm một directory entry cho file đã tồn tại, có ràng buộc provider/filesystem; không dùng `readSymbolicLink` để hỏi “target được lưu” của hard link.

**Copy/move không giống read:** `Files.copy`, `Files.move` có option riêng như `NOFOLLOW_LINKS`/`REPLACE_EXISTING`. Không dùng ngữ nghĩa của `readSymbolicLink` để suy ra một phép copy sẽ sao chép link hay nội dung target; hãy đọc API và test đúng overload.

## 13. Rủi ro bảo mật và tính nhất quán

### 13.1. Path link có vẻ nằm trong root nhưng target có thể ở ngoài

~~~text
allowed/
└── alias -> ../../private/secret.txt
~~~

Một path ở dưới `allowed/` theo **chuỗi ký tự** có thể theo symlink tới file nằm ngoài vùng ứng dụng được phép truy cập.

- Không dựa vào `path.toString().startsWith(root.toString())` để kiểm soát directory traversal.
- `link.getParent().resolve(stored).normalize()` chỉ ghép path từ vựng; không loại bỏ mọi rủi ro symlink chain.
- `toRealPath()` có thể cho vị trí thực tại thời điểm gọi, nhưng kiểm tra trước rồi mở sau vẫn có thể bị **TOCTOU race** khi người khác có quyền thay entry.
- Nếu sản phẩm không cần follow link, ưu tiên không follow link ở API thích hợp và bảo vệ filesystem permission.
- Với thao tác ghi/xóa quan trọng trên thư mục không tin cậy, cần chiến lược kiểm soát quyền/ownership và primitive filesystem phù hợp, không chỉ một lần `Files.exists` hoặc `isSameFile`.

### 13.2. Link tới directory và vòng lặp

Một symlink tới chính thư mục cha có thể tạo chu trình khi duyệt cây với `FOLLOW_LINKS`. `Files.walkFileTree` mặc định không follow link; nếu bật `FOLLOW_LINKS`, Java có cơ chế phát hiện vòng lặp và báo `FileSystemLoopException` thông qua `visitFileFailed`.

**Không tự viết vòng `while(readSymbolicLink(...))` không giới hạn** để cố tìm file đích cuối, vì target tương đối cần tính đúng từ cha link và có thể có cycle.

### 13.3. Xóa link khác mở link để ghi

- `Files.delete(link)` xóa **entry link**, không xóa target mà link đang tham chiếu.
- Ngược lại, `Files.writeString(link, ...)` có thể theo link rồi **thay nội dung target**.
- Vì vậy một link trong vùng được phép không làm cho **mọi thao tác** qua path ấy tự động an toàn.
- Đối với path do người dùng cung cấp, xác định rõ chính sách được phép tạo link tới đâu, ai được phép sửa và lúc nào có thể follow.

### 13.4. Không suy ra file identity từ text của path

Hai Path khác nhau có thể cùng file đích. Một `Path.equals` false không chứng minh hai file khác nhau. Sử dụng `Files.isSameFile` khi cần kiểm tra identity, lưu ý method có thể I/O và trạng thái filesystem có thể thay đổi sau khi kiểm tra.

## 14. Portability: Linux, macOS, Windows và provider đặc biệt

**Symbolic link là optional operation.** Điều đó nghĩa là chương trình hợp lệ vẫn có thể không tạo được link trên một hệ thống nhất định.

| Môi trường | Những điều cần kiểm tra |
| --- | --- |
| Linux | FileStore/mount, quyền thư mục, hạn chế container, target path |
| macOS | Filesystem thật, quyền, relative path, move và cleanup |
| Windows | Quyền tạo symlink, chính sách OS/Developer Mode và Java provider; test thực, không suy đoán |
| Network filesystem | Hỗ trợ link/metadata có thể khác local disk |
| FileSystem provider khác | Có thể hoàn toàn không hỗ trợ symlink hoặc hỗ trợ hạn chế |

Trong một phép thử Java trên máy Windows hiện tại, `Files.createSymbolicLink` đã ném `FileSystemException`. Điều này **chỉ chứng minh môi trường đó chưa tạo được link**, không chứng minh mọi Windows đều không hỗ trợ. Bộ test Linux có permission phù hợp đã tạo/đọc link thành công. Muốn tuyên bố hỗ trợ macOS/Windows, phải có runner thật với cấu hình đủ điều kiện.

### 14.1. Phân biệt PASS, FAIL và SKIPPED

- **PASS:** Tạo link thật và kiểm tra `readSymbolicLink`/follow/no-follow/cleanup đạt.
- **FAIL:** Môi trường đã được xác nhận đủ điều kiện nhưng lời gọi hoặc assertion lỗi.
- **SKIPPED:** Không đáp ứng điều kiện tạo symbolic link, nên các assertion runtime liên quan chưa được chạy.
- **SETUP_ERROR:** Lỗi fixture, hết dung lượng, permission bất thường hoặc môi trường chưa được chuẩn bị; cần phân loại riêng.

Trong code ví dụ, `catch(IOException | UnsupportedOperationException | SecurityException)` quanh create được dùng để cho học viên có thể chạy và **quan sát SKIPPED**; code production không nên đánh đồng mọi IOException với “thiếu hỗ trợ”. Phải ghi nguyên nhân và quyết định retry/error/fallback theo hợp đồng.

## 15. Lỗi thường gặp

| Lỗi/ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Đảo `link` và `target` | Thứ tự đúng là `createSymbolicLink(link, target)` |
| Cho rằng tạo symlink là tạo file đích | Tạo **entry link**, không tạo content target |
| Cho rằng `readSymbolicLink` đọc nội dung file | Trả **Path stored target** |
| Cho rằng readSymbolicLink luôn trả absolute path | Có thể trả path tương đối |
| Giải quyết relative target từ working directory | Phải giải quyết từ **cha của link** |
| Dùng `stored.toAbsolutePath()` mà không xét cha link | Có thể tham chiếu nhầm vị trí |
| Cho rằng symlink phải có target tồn tại | Target có thể chưa tồn tại theo hợp đồng |
| `exists(link)==false` nghĩa chưa có entry | Dangling link có thể còn đó |
| Dùng `Files.isRegularFile(link)` để chứng minh không phải link | Mặc định có thể theo link tới file thường |
| Gọi `readSymbolicLink` trên plain file | Có thể `NotLinkException` |
| Gọi `createSymbolicLink` với tên đã có và mong overwrite | Phương thức được định nghĩa để thất bại |
| Cho rằng link outer → middle tự trả file cuối | `readSymbolicLink` chỉ trả **một bước** |
| Tự theo link bằng vòng while không kiểm soát | Sai mốc relative path/có thể loop |
| Tin `Path.equals()` là kiểm tra identity | Dùng `Files.isSameFile` khi thích hợp |
| Tin `normalize()` là resolver an ninh | Chỉ chuẩn hóa lexical path |
| Nghĩ xóa link sẽ xóa target | `Files.delete(link)` xóa entry symlink |
| Nghĩ mọi thao tác qua path link đều không tác động target | Mở ghi thường có thể theo link và sửa target |
| Tin link tương đối luôn hoạt động sau bất kỳ phép move | Chỉ còn đúng nếu quan hệ tương đối được giữ |
| Tin mọi OS cho tạo symlink như nhau | Tạo link optional/permission-dependent |
| Coi test symlink bị SKIPPED là PASS | Phải chạy trên runner có thể tạo link |
| Chỉ kiểm tra root bằng chuỗi `startsWith` | Không chống link escape/TOCTOU |
| Bắt mọi IOException rồi xem là duplicate | Có nhiều nguyên nhân, phải phân loại |

## 16. Checklist trước khi dùng trong ứng dụng

1. Đã xác định đúng **entry link** và **target path**, không đảo thứ tự?
2. Đích cần lưu tuyệt đối hay tương đối? Tại sao?
3. Relative target được tính từ **cha của link**?
4. Target được phép chưa tồn tại hay bắt buộc có sẵn?
5. Filesystem/OS có hỗ trợ symbolic link và quyền phù hợp?
6. Nếu link path đã tồn tại, code có chính sách từ chối rõ ràng?
7. Có xử lý `NotLinkException`/missing/duplicate/I/O phù hợp?
8. Có dùng `readSymbolicLink` đúng mục đích đọc stored target?
9. Có dùng `Files.readString/readAllBytes` khi thực sự muốn nội dung target?
10. Có phân biệt `exists(link)` và `exists(link, NOFOLLOW_LINKS)`?
11. Có kiểm tra `isSymbolicLink`/attrs của entry khi cần?
12. Nếu cần file identity, có dùng `isSameFile` hoặc `toRealPath` với xử lý lỗi?
13. Có tránh tự theo một chuỗi link không giới hạn?
14. Có chính sách directory link và `FOLLOW_LINKS` khi duyệt cây?
15. Có xác thực allowed root và không tin vào lexical prefix path?
16. Có bảo vệ trước thay đổi symlink giữa các thao tác (TOCTOU) theo threat model?
17. Có test xóa link mà target còn nguyên?
18. Có test di chuyển cả link và target với stored relative target?
19. Có test trên filesystem thật Windows/Linux/macOS cần hỗ trợ?
20. Có ghi rõ **PASS / FAIL / SKIPPED**, không biến thiếu quyền thành PASS?

## 17. Câu hỏi tự kiểm tra

**1.** `Files.createSymbolicLink(a,b)` thì a và b là gì?  
**Đáp án:** a là đường dẫn entry link mới, b là target path được lưu.

**2.** `Files.readSymbolicLink(link)` trả nội dung file hay đường dẫn?  
**Đáp án:** Trả `Path` target được lưu, không đọc byte/content target.

**3.** `docs/shortcut -> ../data.txt` được giải quyết từ đâu?  
**Đáp án:** Từ thư mục `docs` chứa link.

**4.** `readSymbolicLink` tự trả absolute canonical path?  
**Đáp án:** Không; target đã lưu có thể relative.

**5.** Tạo symlink tới target chưa tồn tại có được Java API cho phép?  
**Đáp án:** Có theo hợp đồng, nếu provider/OS hỗ trợ thao tác.

**6.** Dangling link có thể `exists(link) == false` nhưng `exists(link, NOFOLLOW_LINKS) == true` không?  
**Đáp án:** Có, vì hai cách kiểm tra theo target hoặc entry.

**7.** Link outer → middle → file: `readSymbolicLink(outer)` trả gì?  
**Đáp án:** Path `middle`, chỉ một bước.

**8.** `Files.isSameFile(link,target)` kiểm tra gì?  
**Đáp án:** Hai Path có cùng file identity tại thời điểm gọi không.

**9.** Nếu gọi `readSymbolicLink` trên file thường, có thể nhận lỗi nào?  
**Đáp án:** `NotLinkException`.

**10.** Nếu tạo link ở tên đã tồn tại, điều gì xảy ra?  
**Đáp án:** Thao tác thất bại, có thể `FileAlreadyExistsException`.

**11.** Xóa symlink có xóa target không?  
**Đáp án:** Không; xóa entry link, target vẫn còn.

**12.** Một link tới thư mục có được `Files.isDirectory(link)` xem là directory không?  
**Đáp án:** Có thể có, vì API mặc định theo link; với NOFOLLOW_LINKS khác.

**13.** Nếu di chuyển cả thư mục chứa relative link và target, link có thể tiếp tục hoạt động?  
**Đáp án:** Có nếu quan hệ tương đối không đổi và move thành công.

**14.** JDK compile được trên Windows có chứng minh runtime tạo symlink được?  
**Đáp án:** Không; cần quyền/FS support và test thực.

**15.** Test không có quyền tạo link nên báo thế nào?  
**Đáp án:** SKIPPED hoặc setup failure, không phải PASS.

**16.** Vì sao `Path.normalize` không đủ chống symlink escape?  
**Đáp án:** Nó không giải quyết toàn bộ symlink chain trên filesystem và không ngăn race.

**17.** `Files.readString(link,UTF_8)` có thể thay nội dung link không?  
**Đáp án:** Đây là read-only file operation, đọc content target nếu theo link, khác với readSymbolicLink.

**18.** Hard link và symbolic link giống hệt nhau không?  
**Đáp án:** Không; hard link là directory entry khác cùng file identity, không chứa stored target path như symbolic link.

## 18. Nguồn tài liệu chính thức

- [Oracle Java SE 26 — Files.createSymbolicLink](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): tạo symbolic link, target tuyệt đối/tương đối và quyền/optional operation.
- [Oracle Java SE 26 — Files.readSymbolicLink](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): đọc stored target, `NotLinkException` và target có thể không tồn tại.
- [Oracle Java SE 26 — Files.isSymbolicLink/exists/isSameFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): phân biệt loại link, entry và file identity.
- [Oracle Java SE 26 — Files.readAttributes](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): đọc thuộc tính link với `NOFOLLOW_LINKS`.
- [Oracle Java SE 26 — LinkOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html): chính sách không theo symbolic link.
- [Oracle Java SE 26 — Path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): `getParent`, `resolve`, `relativize`, `normalize` và `toRealPath`.
- [Oracle Java SE 26 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): phân biệt `isSymbolicLink` và `isRegularFile`.
- [Oracle Java SE 26 — NotLinkException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/NotLinkException.html): trường hợp không phải symlink.
- [Oracle Java SE 26 — FileAlreadyExistsException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileAlreadyExistsException.html): tạo mới ở tên đã tồn tại.
- [Oracle Java SE 26 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): FOLLOW_LINKS và xử lý cycle khi duyệt cây.
- [Oracle Java SE 7 — Files](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html): nguồn xác nhận API đã ra đời từ Java 7.
- [Oracle Java Tutorial — Links, Symbolic or Otherwise](https://docs.oracle.com/javase/tutorial/essential/io/links.html): kiến thức nền, dùng cùng Javadoc hiện hành.

**Ghi nhớ:** `Files.createSymbolicLink(link,target)` tạo một **entry link**, còn `Files.readSymbolicLink(link)` trả **target path được lưu**. Target tương đối được hiểu từ **thư mục chứa link**, và có thể được đọc ngay cả khi target chưa tồn tại. Đừng nhầm stored target với file nội dung hoặc real path; xử lý đúng `NOFOLLOW_LINKS`, duplicate, lỗi quyền và bảo mật khi dùng symbolic links trong ứng dụng.
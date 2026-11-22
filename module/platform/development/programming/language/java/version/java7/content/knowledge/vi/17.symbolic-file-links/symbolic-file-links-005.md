# Liên kết không còn đích và vòng tham chiếu trong Java NIO.2

> **Chủ đề:** Nhận biết, chẩn đoán và xử lý **dangling/broken symbolic link** (liên kết tượng trưng không phân giải được đích) và **symbolic-link cycle** (vòng tham chiếu liên kết). Trọng tâm là các API Java NIO.2 còn hiện hành: `Files.createSymbolicLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`, `Files.exists` / `Files.notExists` với `LinkOption.NOFOLLOW_LINKS`, `Files.readAttributes`, `Path.toRealPath`, cùng `Files.walkFileTree` và `FileSystemLoopException` khi duyệt cây có `FOLLOW_LINKS`. NIO.2 có từ **Java 7**, vẫn áp dụng trong Java 17+. Các ví dụ chạy với **JDK 17** và ghi rõ trường hợp hệ điều hành không cho tạo symbolic links.

## 1. Bài toán: tên link còn nhưng đích không đến được

Hãy tưởng tượng một chương trình lưu liên kết đến tài liệu:

```text
workspace/
  final.txt                [có dữ liệu]
  latest.txt -> final.txt  [symbolic link]
```

Khi `final.txt` tồn tại, ứng dụng đọc `latest.txt` và filesystem tìm đến file đích. Nhưng điều gì xảy ra nếu `final.txt` bị xóa hoặc đổi tên?

```text
workspace/
  latest.txt -> final.txt  [entry link vẫn còn]
  final.txt                [đã bị xóa]
```

Lúc này entry `latest.txt` có thể **vẫn tồn tại**, nhưng khi đi theo link, hệ thống không tìm được file đích. Đây là hình thức điển hình của **dangling symbolic link**.

Một tình huống khác:

```text
workspace/
  a -> b
  b -> a
```

Việc tìm theo target của `a` dẫn tới `b`, từ `b` quay về `a`, và cứ như vậy. Đây là **vòng tham chiếu**. Tùy API, filesystem provider và hệ điều hành, thao tác follow có thể phát sinh `IOException` hoặc một subclass cụ thể, hoặc Java báo vòng lặp khi duyệt cây với `FOLLOW_LINKS`.

Điểm cần nắm: **tồn tại của directory entry**, **khả năng phân giải đến target**, và **tính hợp lệ/an toàn của thao tác I/O** là ba câu hỏi khác nhau.

## 2. Nhắc lại bản chất symbolic link và hard link

### 2.1. Symbolic link lưu tham chiếu đường dẫn

`Files.createSymbolicLink(link, target)` tạo **entry liên kết tượng trưng** tại `link`. Target có thể là absolute hoặc relative Path; trong mô hình NIO.2, không bắt buộc target đã tồn tại khi tạo.

Một symbolic link có thể:
- Trỏ tới regular file hoặc directory, tùy provider.
- Trỏ tới một tên đích hiện **chưa có**.
- Trỏ tới entry khác cũng là symbolic link.
- Trỏ qua chuỗi nhiều symbolic links.
- Trỏ tới chính nó hoặc tới một vòng gồm nhiều links.
- Trỏ tới nơi không đủ quyền truy cập.
- Bị di chuyển khiến target tương đối đổi ý nghĩa.

### 2.2. Hard link không có “đích theo tên” để bị đứt kiểu symlink

`Files.createLink(newName, existing)` tạo một directory entry khác tới **cùng đối tượng file đã tồn tại**, khi provider hỗ trợ. Nếu bạn xóa `existing` nhưng `newName` còn, bản thân `newName` vẫn là tên trực tiếp tới file. Nó **không trở thành dangling chỉ vì tên được tạo đầu tiên biến mất**.

Ví dụ:

```text
HARD LINK:
original.txt ──┐
alias.txt ─────┴──> same file object

Xóa original.txt:
alias.txt ─────────> same file object (vẫn truy cập được)

SYMBOLIC LINK:
original.txt ──────> file object
alias.txt --"original.txt"--> target name

Xóa original.txt:
alias.txt --"original.txt"--> không tìm thấy target
```

Đây là sơ đồ khái niệm. Một hard link vẫn có thể không đọc được do quyền/thiết bị bị lỗi; ý ở đây chỉ là **nó không cần resolve một target path riêng** như symbolic link.

### 2.3. Phạm vi của bài

Tập trung vào **symbolic link không phân giải được và vòng tham chiếu**. Hard link chỉ xuất hiện như một trường hợp đối chiếu, để tránh hiểu sai “xóa file gốc làm hỏng mọi loại liên kết”.

## 3. Ba trạng thái khác nhau: link hợp lệ, dangling và cycle

| Trạng thái | Hình dung | Đọc target bình thường | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Link hợp lệ** | `shortcut -> data.txt`, target có thể truy cập | Thường thành công | Raw target, file type, quyền |
| **Dangling/missing target** | `shortcut -> missing.txt`, target chưa có hoặc bị xóa | Thường thất bại | Entry link còn không, target path nào |
| **Circular reference** | `a -> b -> a` | Không phân giải thành file cuối | Số bước, khả năng nhận diện vòng và IOException |
| **Không đủ quyền** | Link/ancestor có, nhưng không đọc được thông tin | Có thể thất bại | Quyền filesystem, loại IOException |
| **Đích ngoài phạm vi cho phép** | Link dưới root nhưng target nằm ngoài root | Có thể thành công về I/O nhưng không được phép nghiệp vụ | Real-path containment và authorization |

**Cực kỳ quan trọng:** “không đọc được target” **không tự chứng minh** link dangling. Có thể là thiếu quyền, lỗi mạng, vòng lặp, provider không hỗ trợ hoặc hệ thống đang thay đổi đồng thời. Trong log và API nghiệp vụ, phân biệt **TARGET_MISSING**, **UNRESOLVED_IO**, **LOOP** và **UNKNOWN** khi có đủ thông tin.

## 4. Cách filesystem phân giải symbolic link

Khi chương trình mở `link` theo chế độ mặc định có follow, filesystem cố gắng thay entry link bằng target mà link biểu diễn. Nếu target cũng là symlink, quá trình có thể tiếp tục.

Sơ đồ một chuỗi bình thường:

```text
app/latest -> versions/current -> versions/2026/report.txt

Follow "app/latest"
  -> "versions/current"
  -> "versions/2026/report.txt"
  -> regular file
```

Trong trường hợp target không có:

```text
app/latest -> versions/current -> versions/2027/report.txt (missing)

Follow link
  -> ... 
  -> không tìm được target cuối
```

Trong trường hợp vòng:

```text
app/latest -> a
a -> b
b -> a
```

Vòng không có regular file cuối để trả về. Hệ điều hành và provider không được phép đi theo liên kết vô hạn; thao tác có thể báo lỗi sau khi nhận ra vòng hoặc sau khi vượt quá giới hạn follow links nội bộ.

**Không giả định mọi API đều ném đúng `FileSystemLoopException`**. Java tài liệu hóa exception đó rõ nhất cho **traversal với `Files.walkFileTree(..., FOLLOW_LINKS, ...)` khi gặp vòng directory-to-ancestor**. Với `Path.toRealPath()` hoặc đọc file qua một chuỗi links, loại `IOException` cụ thể có thể khác provider.

## 5. Liên kết đích tương đối được hiểu từ nơi chứa link

Giả sử:

```text
workspace/
  shared/
    report.txt
  views/
    latest.txt -> ../shared/report.txt
```

Entry `views/latest.txt` giữ raw target `../shared/report.txt`. Path đó được hiểu **từ thư mục `views` chứa link**, không phải từ working directory tùy ý của ứng dụng khi mở link.

Cách giải thích bằng `Path`:

```java
Path storedTarget = Files.readSymbolicLink(link);
Path resolvedFromParent =
        link.getParent().resolve(storedTarget).normalize();
```

Đây là snippet với `Path link` là symlink thật, trong method xử lý `IOException`. `resolvedFromParent` là kết quả **lexical** của việc ghép; chưa chứng minh file thật tồn tại hoặc không có symbolic links khác nằm ở ancestor/target.

### 5.1. Vì sao symlink có thể đứt sau khi move?

Nếu chỉ move `views/latest.txt` sang `archive/2026/latest.txt` mà vẫn giữ raw target `../shared/report.txt`, raw target giờ được hiểu từ `archive/2026`, nên dẫn tới `archive/shared/report.txt`. Nếu vị trí đó không có file, link trở thành dangling.

Không phải Java tự “thay target trong link” khi move; target vẫn là một đường dẫn tương đối nhưng có **điểm neo khác**.

### 5.2. Đường dẫn tuyệt đối có luôn an toàn hơn không?

Không. Target absolute tránh biến đổi theo vị trí thư mục chứa link, nhưng có thể kém portable khi di chuyển cả cây sang máy khác, volume khác hoặc môi trường container khác. Nó cũng có thể đưa ứng dụng ra ngoài root được phép khi một user kiểm soát link.

Lựa chọn absolute/relative là **quyết định thiết kế**, không phải bản thân một phép bảo mật.

## 6. Chương trình 1: phân giải raw target tương đối, không cần symlink thật

Lưu thành `LinkPathSemanticsDemo.java`:

```java
import java.nio.file.Path;

public class LinkPathSemanticsDemo {
    static String unixStyle(Path path) {
        return path.toString().replace('\\', '/');
    }

    public static void main(String[] args) {
        Path root = Path.of("workspace").toAbsolutePath().normalize();
        Path link = root.resolve(Path.of("views", "latest.txt"));
        Path rawTarget = Path.of("..", "shared", "report.txt");
        Path originalDestination = link.getParent().resolve(rawTarget).normalize();

        Path movedLink = root.resolve(Path.of("archive", "2026", "latest.txt"));
        Path movedDestination = movedLink.getParent().resolve(rawTarget).normalize();

        System.out.println("rawIsRelative=" + !rawTarget.isAbsolute());
        System.out.println("rawTarget=" + unixStyle(rawTarget));
        System.out.println("originalTarget=" +
                unixStyle(root.relativize(originalDestination)));
        System.out.println("afterMovingOnlyLink=" +
                unixStyle(root.relativize(movedDestination)));
        System.out.println("meaningChanged=" + !originalDestination.equals(movedDestination));
    }
}
```

Biên dịch/chạy với JDK 17:

```bash
javac -encoding UTF-8 --release 17 LinkPathSemanticsDemo.java
java LinkPathSemanticsDemo
```

Stdout đã kiểm thử:

```text
rawIsRelative=true
rawTarget=../shared/report.txt
originalTarget=shared/report.txt
afterMovingOnlyLink=archive/shared/report.txt
meaningChanged=true
```

Đây là phép tính **Path thuần túy**, không tạo symlink thật nên vẫn chạy được khi hệ điều hành không cho phép tạo symbolic link. Nó chứng minh ý nghĩa của raw relative target đổi khi **thư mục chứa link** thay đổi.

**Giới hạn:** kết quả `normalize()` ở đây chỉ là thao tác lexical. Nếu một ancestor như `views` hoặc `archive` là symlink, ý nghĩa của `..` khi filesystem thật phân giải có thể khác phép normalize đã làm. Vì vậy không dùng đoạn trên làm kiểm tra security toàn diện.

## 7. Bộ API quan trọng nhất để phát hiện và chẩn đoán

| Method | Câu hỏi | Có theo symbolic link không? |
| --- | --- | --- |
| `Files.isSymbolicLink(path)` | Entry tại Path có phải symlink? | Xét entry link, không cần mở target cuối |
| `Files.readSymbolicLink(link)` | Trong entry link lưu raw target nào? | Không cần target tồn tại |
| `Files.exists(path)` | Theo semantics mặc định, file có tồn tại? | Mặc định theo link |
| `Files.exists(path, NOFOLLOW_LINKS)` | Entry tại path có tồn tại? | Không theo link cuối theo option |
| `Files.notExists(path)` | Có thể xác minh file không tồn tại? | Mặc định theo link |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Metadata của entry là gì? | Xem chính link/entry |
| `Files.readAttributes(path, BasicFileAttributes.class)` | Metadata của target được phân giải? | Mặc định theo link |
| `path.toRealPath()` | Real path của file thật đã tồn tại? | Mặc định giải symlink |
| `path.toRealPath(NOFOLLOW_LINKS)` | Lấy real path theo policy không giải symlink? | Không theo link, semantics có khác |
| `Files.walkFileTree(root, FOLLOW_LINKS, depth, visitor)` | Duyệt cây khi đi theo symbolic links | Theo links và có phát hiện directory cycles |

Các phương thức `Files.exists` / `Files.notExists` và `Files.isSymbolicLink` trả boolean để thuận tiện. **Boolean không thay thế việc xử lý lỗi I/O** nếu bạn thật sự cần phân biệt thiếu quyền, I/O error và target missing.

### 7.1. Các import thường dùng

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
```

Tất cả API chính trong danh sách thuộc NIO.2 có từ Java 7; `Path.of` có từ Java 11, nên đoạn chạy JDK 17 dùng cách viết hiện đại. Với dự án target Java 7, dùng `Paths.get` để tạo Path.

## 8. Bẫy lớn nhất: `exists` và `notExists` không luôn là phủ định của nhau

Với một link đã bị đứt nhưng entry vẫn còn, trong một môi trường đọc metadata thành công thông thường:

```java
boolean follows = Files.exists(link);
boolean ownEntry = Files.exists(link, LinkOption.NOFOLLOW_LINKS);
boolean knownMissing = Files.notExists(link);
```

Bạn **có thể** quan sát:

```text
follows      = false
ownEntry     = true
knownMissing = true
```

Nhưng Javadoc có một sắc thái cực quan trọng: `Files.exists` và `Files.notExists` **không phải hai giá trị đảo nhau trong mọi trường hợp**. Khi không thể xác định trạng thái tồn tại, **cả hai cùng có thể là false**. Ví dụ quyền bị từ chối hoặc I/O hỏng.

| `Files.exists(path)` | `Files.notExists(path)` | Có thể diễn giải |
| --- | --- | --- |
| true | false | Xác định path hiện tồn tại theo cách kiểm tra |
| false | true | Xác định path không tồn tại theo cách kiểm tra |
| false | false | **Không xác định được** trạng thái |
| true | true | Không phải kết quả nhất quán cho cùng một trạng thái; có thể do thay đổi giữa hai lần gọi hoặc giả định sai |

Hai method được gọi **riêng biệt**, không có một snapshot nguyên tử chung. Khi file đang thay đổi đồng thời, kết quả có thể không còn mô tả cùng một trạng thái thời điểm.

### 8.1. Vì sao `Files.exists(link)==false` chưa đủ để gọi link dangling?

Vì ít nhất những khả năng sau:

- **Không hề có entry `link`** tại đường dẫn đó.
- Entry là symlink nhưng target không tồn tại.
- Target có nhưng không có quyền traverse ancestor.
- Metadata query gặp lỗi I/O.
- Link bị thay/xóa khi đang kiểm tra.
- Phép follow link rơi vào vòng tham chiếu.
- Provider không thể xác minh tồn tại.

Muốn phân loại, bắt đầu bằng việc đọc **entry không theo link**, sau đó kiểm tra/giải target riêng và xử lý ngoại lệ rõ ràng.

### 8.2. `Files.isSymbolicLink(link)` có phải chứng cứ tuyệt đối?

Khi trả true, nó nhận diện link entry. Khi trả false, không nhất thiết chứng minh “entry là regular file”; có thể là directory, file loại khác, entry không tồn tại hoặc I/O/permission không xác định. Khi cần chẩn đoán chi tiết, dùng `Files.readAttributes(..., NOFOLLOW_LINKS)` và xử lý IOException.

## 9. `readSymbolicLink` đọc raw target ngay cả khi đích không tồn tại

`Files.readSymbolicLink(link)` trả `Path` mà symlink lưu để tham chiếu; method **không mở nội dung target cuối**.

Ví dụ:

```java
Path stored = Files.readSymbolicLink(link);
System.out.println("storedTarget=" + stored);
```

Đây là snippet trong method khai báo/ xử lý `IOException` và với `link` là symbolic link thực. Nếu target `future.txt` chưa có nhưng entry link được tạo đúng, method vẫn có thể trả `future.txt`.

### 9.1. Khi link không còn hoặc không phải symbolic link

Nếu entry không tồn tại, bạn có thể gặp `NoSuchFileException` hoặc IOException tương ứng. Nếu entry không phải symlink, có thể gặp `NotLinkException` hoặc IOException khác tùy provider. Javadoc xếp `readSymbolicLink` vào **optional operation**, nên cũng cần dự liệu môi trường không hỗ trợ.

**Đừng viết:**

```java
Path target = Files.readSymbolicLink(anyFile);
```

và giả định mọi Path hợp lệ đều là symlink. Đây chỉ là **snippet minh họa tiền điều kiện còn thiếu**, không phải pattern production; hãy xác minh loại entry và xử lý lỗi.

### 9.2. Raw target không đồng nghĩa final target

Nếu `a -> b` và `b -> final.txt`:
- `readSymbolicLink(a)` trả `b`;
- nó không tự trả `final.txt`, vì method **chỉ đọc một link**;
- `a.toRealPath()` (mặc định follow) mới cố gắng phân giải toàn chuỗi đến file cuối đang tồn tại.

Khi vòng hoặc đích không thể truy cập, `toRealPath()` có thể ném IOException. Đó là sự khác nhau giữa **metadata của liên kết** và **truy cập file đích**.

## 10. Chương trình 2: dangling link, phục hồi khi target xuất hiện và đứt lại

Lưu thành `DanglingLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DanglingLinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("dangling-");
        Path target = dir.resolve("future.txt");
        Path link = dir.resolve("shortcut.txt");
        try {
            try {
                Files.createSymbolicLink(link, Path.of("future.txt"));
            } catch (IOException | UnsupportedOperationException | SecurityException unsupported) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            System.out.println("isSymbolic=" + Files.isSymbolicLink(link));
            System.out.println("storedTarget=" + Files.readSymbolicLink(link));
            System.out.println("existsFollow=" + Files.exists(link));
            System.out.println("existsNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("notExistsFollow=" + Files.notExists(link));
            try {
                link.toRealPath();
                System.out.println("realPath=UNEXPECTED");
            } catch (IOException expected) {
                System.out.println("realPath=UNRESOLVED");
            }
            Files.writeString(target, "READY", StandardCharsets.UTF_8);
            System.out.println("existsAfterCreate=" + Files.exists(link));
            System.out.println("readAfterCreate=" +
                    Files.readString(link, StandardCharsets.UTF_8));
            Files.delete(target);
            System.out.println("danglingAgain=" + !Files.exists(link));
            Files.delete(link);
            System.out.println("linkRemoved=" +
                    Files.notExists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy bằng JDK 17:

```bash
javac -encoding UTF-8 --release 17 DanglingLinkDemo.java
java DanglingLinkDemo
```

**Khi filesystem cho phép tạo symlink**, kết quả kỳ vọng ở thư mục tạm thông thường:

```text
isSymbolic=true
storedTarget=future.txt
existsFollow=false
existsNoFollow=true
notExistsFollow=true
realPath=UNRESOLVED
existsAfterCreate=true
readAfterCreate=READY
danglingAgain=true
linkRemoved=true
```

**Kết quả đã chạy trên máy Windows kiểm thử hiện tại** là:

```text
symlink=SKIPPED
```

Nhánh supported được mô tả theo hợp đồng Java và giả định thư mục tạm không bị sửa/khóa bởi tác nhân khác; **không tuyên bố đã kiểm thử nó trên máy bị giới hạn quyền**. Để kiểm chứng link thật, chạy cùng chương trình trong môi trường có quyền tạo symlink.

### 10.1. Diễn biến từng bước

1. Tạo thư mục tạm riêng mà chương trình sở hữu.
2. Tạo symlink `shortcut.txt` trỏ bằng raw target `future.txt`, **không tạo target ngay**.
3. `readSymbolicLink` xem raw target. `exists(..., NOFOLLOW_LINKS)` có thể xác nhận entry link còn, dù `exists(link)` chưa follow đến file.
4. `link.toRealPath()` thất bại vì target chưa tồn tại ở thời điểm đó; demo **không** ép một subclass IOException cụ thể cho mọi provider.
5. Tạo file `future.txt` với nội dung `READY`, không thay đổi link.
6. Link đã có **bắt đầu phân giải đến target**, nên đọc qua shortcut nhận `READY`.
7. Xóa target làm shortcut **dangling lần nữa**.
8. Xóa chính entry link và dọn thư mục tạm.

**Hàm ý thiết kế:** symlink không lưu “trạng thái broken” như một flag vĩnh viễn; kết quả phụ thuộc **khả năng phân giải target ở thời điểm gọi**.

### 10.2. Vì sao dùng `Files.createSymbolicLink(link, Path.of("future.txt"))`?

Raw target tương đối sẽ được hiểu từ thư mục chứa `link`. Với `link` và `target` cùng trong thư mục tạm, `future.txt` là đúng tên. Không cần hard-code full path của temp directory, vốn có phần đuôi ngẫu nhiên.

### 10.3. Vì sao cleanup có `deleteIfExists(link)` và `deleteIfExists(target)` riêng?

Nếu symlink đã tạo thành công nhưng target chưa có, `Files.deleteIfExists(link)` cần xóa **entry link**, không phải xóa file đích. Với link đang tồn tại, `Files.delete`/`deleteIfExists` thao tác trên link entry theo hợp đồng. Demo chỉ dọn **những tên do chính nó tạo**, không xóa đường dẫn do user cung cấp.

## 11. Phân loại trạng thái bằng `readAttributes(..., NOFOLLOW_LINKS)`

Muốn phân biệt “không có entry” với “entry là symlink nhưng target không phân giải được”, nên bắt đầu bằng metadata của **chính entry**:

```java
BasicFileAttributes attrs =
        Files.readAttributes(
                path,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);

if (attrs.isSymbolicLink()) {
    Path raw = Files.readSymbolicLink(path);
    // Phần tiếp theo tùy policy: thử toRealPath, xác định quyền, v.v.
}
```

Đây là **snippet** trong method xử lý `IOException`. Một ngoại lệ từ `readAttributes` là dữ kiện cần xử lý; không nên lén thay bằng một boolean false để caller tưởng entry chắc chắn không tồn tại.

### 11.1. Sơ đồ quyết định hợp lý

```text
Bắt đầu với Path được phép kiểm tra
     |
     v
readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)
     |
     +-- NoSuchFileException --> ENTRY_MISSING_NOW
     |
     +-- IOException khác --> ENTRY_UNREADABLE/UNKNOWN
     |
     +-- attrs.isSymbolicLink()==false --> NOT_SYMLINK
     |
     +-- attrs.isSymbolicLink()==true
              |
              v
            path.toRealPath() [follow mặc định]
              |
              +-- Thành công --> LINK_RESOLVES_NOW
              +-- NoSuchFileException --> LINK_TARGET_MISSING_NOW
              +-- IOException khác --> LINK_UNRESOLVED_IO
```

Đây là **cách phân loại tại thời điểm quan sát**, không phải chứng nhận bảo mật. Cần có policy riêng với `SecurityException` nếu môi trường bảo mật có thể ném runtime exception đó.

### 11.2. Vì sao trạng thái có chữ “NOW”?

Bởi filesystem có thể thay đổi ngay sau khi method trả:
- Target bị xóa hoặc tạo.
- Một symlink bị đổi sang target khác.
- Permission của thư mục cha được thay.
- Một đường dẫn bị thay thế bằng file hoặc link khác.

Không bao giờ hứa “trả `LINK_RESOLVES_NOW` thì mọi open trong tương lai chắc chắn thành công”. Muốn truy cập dữ liệu, hãy mở tệp theo chính sách và xử lý IOException của **chính thao tác mở**.

## 12. Chương trình 3: bộ phân loại có xử lý entry missing và I/O

Lưu thành `LinkStateInspectorDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class LinkStateInspectorDemo {
    static String inspect(Path path) {
        try {
            BasicFileAttributes own =
                    Files.readAttributes(path, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);
            if (!own.isSymbolicLink()) return "NOT_SYMLINK";
            try {
                path.toRealPath();
                return "LINK_RESOLVES_NOW";
            } catch (NoSuchFileException missing) {
                return "LINK_TARGET_MISSING_NOW";
            } catch (IOException failure) {
                return "LINK_UNRESOLVED_IO";
            }
        } catch (NoSuchFileException missingEntry) {
            return "ENTRY_MISSING_NOW";
        } catch (IOException failure) {
            return "ENTRY_UNREADABLE";
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("inspect-link-");
        Path ordinary = dir.resolve("ordinary.txt");
        Path absent = dir.resolve("absent.txt");
        Path target = dir.resolve("target.txt");
        Path link = dir.resolve("link.txt");
        try {
            Files.writeString(ordinary, "DATA", StandardCharsets.UTF_8);
            System.out.println("ordinary=" + inspect(ordinary));
            System.out.println("missing=" + inspect(absent));
            try {
                Files.createSymbolicLink(link, Path.of("target.txt"));
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            System.out.println("beforeTarget=" + inspect(link));
            Files.writeString(target, "NOW", StandardCharsets.UTF_8);
            System.out.println("afterTarget=" + inspect(link));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(ordinary);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 LinkStateInspectorDemo.java
java LinkStateInspectorDemo
```

**Stdout thực nghiệm trên máy hiện tại:**

```text
ordinary=NOT_SYMLINK
missing=ENTRY_MISSING_NOW
symlink=SKIPPED
```

**Nhánh kỳ vọng thêm nếu provider cho tạo symlink:**

```text
beforeTarget=LINK_TARGET_MISSING_NOW
afterTarget=LINK_RESOLVES_NOW
```

Hai dòng này chỉ là **kỳ vọng của nhánh supported**, không được gán nhãn đã kiểm thử thực tế trong môi trường Windows thiếu quyền.

### 12.1. Diễn giải các lớp lỗi

- `ENTRY_MISSING_NOW` được trả khi không thể tìm entry và provider thông báo `NoSuchFileException` trong bước đọc attributes **không follow**.
- `NOT_SYMLINK` là entry hiện hữu nhưng không mang cờ symbolic-link, có thể là regular file, directory hoặc loại file khác.
- `LINK_TARGET_MISSING_NOW` là symlink entry đã được xác minh, nhưng `toRealPath()` theo link báo target path không tồn tại ở thời điểm đó.
- `LINK_UNRESOLVED_IO` là những IOException còn lại khi follow: có thể gồm loop, permission, lỗi provider. Không tự gắn nhãn dangling.
- `ENTRY_UNREADABLE` là lỗi I/O khi đọc metadata của chính entry.

Tên trạng thái là **quy ước của chương trình demo**, không phải enum có sẵn trong Java SE. Một ứng dụng thật có thể dùng `enum`/sealed hierarchy/Result object thay String và cần ghi nguyên nhân lỗi vào kênh log có kiểm soát.

### 12.2. Có nên dùng method demo như một hàm cấp quyền?

Không. Nó chưa xác minh path containment/authorization, chưa bảo vệ race giữa các thao tác, và có thể trả một trạng thái rồi filesystem đổi ngay. Khi quyền truy cập là vấn đề quan trọng, tách **classification for diagnostics** khỏi **secure access policy**.

## 13. Phân biệt broken target với lỗi do permission

Giả sử target **có thật**, nhưng tài khoản ứng dụng không được phép duyệt một directory cha. Từ phía ứng dụng, một số API có thể không xác minh được trạng thái tồn tại hoặc không phân giải được real path.

Nếu code viết:

```java
if (!Files.exists(link)) {
    System.out.println("Link is broken");
}
```

thì thông báo có thể **sai**: false có thể là thiếu quyền chứ không phải target chắc chắn đã bị xóa.

### 13.1. Thiết kế thông báo chính xác hơn

- Khi `readAttributes(..., NOFOLLOW_LINKS)` xác nhận link entry vẫn tồn tại và `toRealPath()` ném `NoSuchFileException`: có thể báo “target không tìm thấy ở thời điểm kiểm tra” với caveat race.
- Khi `toRealPath()` ném `AccessDeniedException`: báo “không có quyền xác minh/truy cập target”.
- Khi gặp `FileSystemLoopException` hoặc lỗi OS tương ứng: báo “không thể phân giải do vòng/giới hạn follow”.
- Khi không phân biệt được: báo “link không phân giải được”, **không khẳng định chắc chắn target bị xóa**.
- Không tiết lộ full path server/sensitive target cho client công khai.

### 13.2. Có thể đọc raw target mà không đọc được nội dung target không?

Có thể. `Files.readSymbolicLink(link)` chỉ đọc metadata của link; việc theo link mở file cuối là một thao tác khác, có thể thất bại vì quyền, target thiếu hoặc vòng tham chiếu.

Vì vậy một công cụ kiểm tra links có thể hiển thị raw target cho quản trị viên được phép, nhưng vẫn phải tách “raw target biết được” với “target truy cập được”.

## 14. `Path.toRealPath()` và `NOFOLLOW_LINKS` có ngữ nghĩa khác nhau

`path.toRealPath()` được thiết kế để lấy **đường dẫn thực của file đang tồn tại**, mặc định giải symbolic links đến target cuối.

```java
Path finalTarget = link.toRealPath();
```

Đây là snippet với `link` là `Path` và method có xử lý IOException.

Ngược lại:

```java
Path linkPath = link.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

yêu cầu **không giải symbolic links** theo policy của method. Nó có thể trả đường dẫn tới **entry link** đã tồn tại, ngay cả khi target cuối chưa tồn tại, tùy provider/cấu trúc path. Đừng nhầm `toRealPath(NOFOLLOW_LINKS)` là “cách khôi phục file target đã mất”. Nó không theo tới target.

### 14.1. `normalize()` không phát hiện broken link hoặc cycle

`link.normalize()` chỉ là thao tác trên cấu trúc tên Path: xử lý các đoạn `.`, `..` theo quy tắc provider. Nó **không truy cập filesystem**, nên không thể tự biết:
- Link entry có tồn tại hay không.
- Link trỏ đi đâu.
- Target có tồn tại hay không.
- Một target lại là link khác hay không.
- Chuỗi references có vòng hay không.

Muốn biết các điều đó, cần I/O thực hoặc mô hình dữ liệu riêng. Đặc biệt, `normalize()` có thể thay nghĩa đường dẫn khi xóa `..` đứng sau một symbolic-link component; vì vậy không dùng normalize như một phép “giải link thật”.

### 14.2. `toAbsolutePath()` cũng không phải giải link

`toAbsolutePath()` cho một biểu diễn absolute theo ngữ cảnh filesystem, thường dựa trên working directory. Nó không yêu cầu target tồn tại và không tự xác định final file object. Nếu cần follow link tới real target, `toRealPath()` khác hẳn.

## 15. Vòng tham chiếu: tự trỏ, hai link, nhiều link và directory ancestor

### 15.1. Vòng tự tham chiếu

```text
self -> self
```

Entry là link và raw target có thể được đọc. Nhưng theo link không dẫn đến regular file cuối. API follow phải ngừng theo quy tắc OS/provider thay vì đi vô tận.

### 15.2. Vòng hai link

```text
a -> b
b -> a
```

Đây là vòng rất trực quan. Từng entry `a` và `b` tồn tại theo `NOFOLLOW_LINKS`, nhưng không có final target. `readSymbolicLink(a)` trả `b` và `readSymbolicLink(b)` trả `a`. `toRealPath` qua chúng sẽ không giải được một file thật bình thường.

### 15.3. Vòng ba hoặc nhiều link

```text
a -> b
b -> c
c -> a
```

Nếu bạn tự duyệt **một graph metadata độc lập** (không phải filesystem thật), có thể nhận ra vòng bằng một tập `visited`. Nhưng filesystem thực có thể có alias, directory links, relative targets và quyền thay đổi đồng thời; thuật toán “lần theo một chuỗi tên thô” có những giới hạn không có ở graph đơn giản.

### 15.4. Vòng quay lại directory ancestor

```text
root/
  branch/
    back -> ..  [trỏ về root]
```

Nếu duyệt `root` mà bật `FOLLOW_LINKS`, walker đi vào `branch` rồi gặp link tới `root`, tức directory **đã là ancestor** của vị trí đang duyệt. Đây là trường hợp `Files.walkFileTree` phát hiện vòng và báo tới `visitFileFailed` bằng `FileSystemLoopException` theo hợp đồng API.

**Điểm phân biệt:** `FileSystemLoopException` có quy định rõ ở API traversal khi `FOLLOW_LINKS` tạo cycle về directory ancestor; không bắt buộc mọi thao tác khác với vòng symlink đơn giản luôn trả đúng exception đó.

## 16. Chương trình 4: vòng a → b → a với hai symbolic links

Lưu thành `TwoLinkCycleDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class TwoLinkCycleDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("cycle-two-");
        Path a = dir.resolve("a");
        Path b = dir.resolve("b");
        try {
            try {
                Files.createSymbolicLink(a, Path.of("b"));
                Files.createSymbolicLink(b, Path.of("a"));
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            System.out.println("aEntry=" +
                    Files.exists(a, LinkOption.NOFOLLOW_LINKS));
            System.out.println("bEntry=" +
                    Files.exists(b, LinkOption.NOFOLLOW_LINKS));
            System.out.println("aTarget=" + Files.readSymbolicLink(a));
            System.out.println("bTarget=" + Files.readSymbolicLink(b));
            System.out.println("aIsSymbolic=" +
                    Files.readAttributes(a, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS).isSymbolicLink());
            try {
                a.toRealPath();
                System.out.println("follow=UNEXPECTED");
            } catch (IOException expected) {
                System.out.println("follow=UNRESOLVED");
            }
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TwoLinkCycleDemo.java
java TwoLinkCycleDemo
```

**Nhánh kỳ vọng ở provider cho phép tạo symlink**:

```text
aEntry=true
bEntry=true
aTarget=b
bTarget=a
aIsSymbolic=true
follow=UNRESOLVED
```

**Kết quả thật trên máy kiểm thử Windows thiếu quyền tạo symbolic link:**

```text
symlink=SKIPPED
```

Hai đường dẫn riêng `a` và `b` trong demo trỏ đến nhau. `Files.readSymbolicLink` vẫn đọc được raw target của từng entry, nhưng `toRealPath()` không thể dẫn tới final regular file. Demo bắt `IOException` thay vì đòi một exception subtype cố định để tránh phụ thuộc thông điệp và khả năng provider.

### 16.1. Nếu lần tạo symlink thứ hai thất bại thì sao?

`finally` dọn cả `a` và `b` nếu chúng được tạo một phần. Không thể coi hai bước `createSymbolicLink` là một transaction. Trong ứng dụng thật, nếu tạo một **chuỗi links** nhiều bước, cần thiết kế cleanup/rollback khi lỗi và tránh để lại entry gây hiểu lầm.

### 16.2. Vì sao không dùng `Files.exists(a)` để kết luận vòng?

Vì `Files.exists(a)==false` có thể có nhiều nguyên nhân. Muốn chẩn đoán vòng, phải xem ít nhất **raw target và khả năng resolve**, hoặc để API được thiết kế cho file-tree traversal báo vòng directory khi thích hợp. Không xây hệ thống giám sát chỉ dựa vào một boolean.

## 17. Duyệt cây với `FOLLOW_LINKS` và `FileSystemLoopException`

`Files.walkFileTree` là API Java 7 vẫn dùng phổ biến cho traversal có callbacks. Dạng cơ bản:

```java
Files.walkFileTree(root, visitor);
```

**Không theo symbolic links mặc định.** Symlink có thể được chuyển tới `visitFile` với `BasicFileAttributes.isSymbolicLink()==true`.

Khi chủ động bật follow:

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor
);
```

Walker phải xét các directory đã gặp trên nhánh ancestor hiện tại. Khi theo link dẫn trở lại một directory ancestor, Java có cơ chế phát hiện loop và gọi `visitFileFailed` với `FileSystemLoopException`.

### 17.1. Xử lý đúng callback

```java
@Override
public FileVisitResult visitFileFailed(Path file, IOException failure)
        throws IOException {
    if (failure instanceof FileSystemLoopException) {
        System.err.println("Loop encountered");
        return FileVisitResult.CONTINUE;
    }
    throw failure;
}
```

Đây là snippet bên trong `SimpleFileVisitor<Path>`. Trả `CONTINUE` chỉ có ý nghĩa khi ứng dụng **có chủ đích bỏ qua nhánh lỗi** và báo partial scan. Nếu tạo backup hoặc thực hiện thao tác cần đầy đủ mọi file, ném lại có thể phù hợp hơn.

### 17.2. Cách walker phát hiện cycle

Javadoc mô tả khi bật `FOLLOW_LINKS`, walker theo dõi các directory đã thăm trên nhánh hiện tại: sử dụng `fileKey` khi provider hỗ trợ hoặc `Files.isSameFile` để xác định một directory có trùng với **ancestor** không.

Vì vậy vòng link tới directory ancestor được báo với `FileSystemLoopException`. Nhưng đừng suy rộng rằng mọi chuỗi symlink hỏng đều biến thành `FileSystemLoopException`: khi target không đọc được, walker còn có cơ chế fallback để đọc attributes của chính symlink và gọi `visitFile`, thay vì nhất định gọi `visitFileFailed`.

### 17.3. Một bẫy: broken symlink có thể xuất hiện như file entry ngay cả khi bật `FOLLOW_LINKS`

Theo hợp đồng `walkFileTree`, nếu `FOLLOW_LINKS` được bật mà **không đọc được attributes của target**, walker thử đọc `BasicFileAttributes` của **chính link**. Nếu đọc được, nó **có thể gọi `visitFile` với attrs của symlink**. Do đó không mặc định mọi broken symlink đều đi qua `visitFileFailed`.

Nếu visitor cần đếm dangling links, phải thiết kế theo **entry type, khả năng follow và policy**, không chỉ đếm exceptions.

## 18. Chương trình 5: vòng directory khi duyệt cây

Lưu thành `DirectoryCycleWalkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public class DirectoryCycleWalkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("cycle-walk-");
        Path branch = root.resolve("branch");
        Path backlink = branch.resolve("back");
        try {
            Files.createDirectory(branch);
            try {
                Files.createSymbolicLink(backlink, Path.of(".."));
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            int[] seenLinks = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (attrs.isSymbolicLink()) seenLinks[0]++;
                    return FileVisitResult.CONTINUE;
                }
            });
            System.out.println("defaultLinkEntries=" + seenLinks[0]);

            int[] loops = {0};
            Files.walkFileTree(root, EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFileFailed(Path file, IOException failure)
                        throws IOException {
                    if (failure instanceof FileSystemLoopException) {
                        loops[0]++;
                        return FileVisitResult.CONTINUE;
                    }
                    throw failure;
                }
            });
            System.out.println("loopsDetected=" + loops[0]);
        } finally {
            Files.deleteIfExists(backlink);
            Files.deleteIfExists(branch);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 DirectoryCycleWalkDemo.java
java DirectoryCycleWalkDemo
```

**Nhánh kỳ vọng ở provider hỗ trợ tạo symlink**:

```text
defaultLinkEntries=1
loopsDetected=1
```

**Kết quả đã quan sát trên máy hiện tại:**

```text
symlink=SKIPPED
```

Sự khác biệt:
- Lượt đầu không bật FOLLOW_LINKS → thấy `back` như một symbolic link entry, không đi theo vòng.
- Lượt sau bật FOLLOW_LINKS → link `back -> ..` dẫn về `root` là ancestor. Walker phát hiện cycle và gọi `visitFileFailed`.
- Ví dụ **chỉ** bỏ qua `FileSystemLoopException`, lỗi I/O khác được ném lại để không biến lỗi đọc dữ liệu thành một báo cáo “duyệt đầy đủ”.

### 18.1. Vì sao không bỏ qua mọi IOException?

Nếu quyền bị từ chối, ổ đĩa bị ngắt hoặc directory stream hỏng, bỏ qua mọi lỗi có thể khiến chương trình lầm tưởng đã quét hết cây. Một hệ thống bảo mật/backup nên báo partial scan hoặc fail-fast theo hợp đồng.

### 18.2. Có nên bật `FOLLOW_LINKS` mặc định cho công cụ cleanup?

Thường không. Nếu người dùng tạo symlink trong cây được dọn và target nằm ngoài cây, việc follow links có thể đưa traversal sang nơi không định xử lý. Với một công cụ xóa tài nguyên, quyền truy cập và containment phải được phân tích kỹ hơn cả việc phát hiện cycles.

## 19. Thuật toán mô phỏng graph để hiểu bản chất vòng lặp

Một cách học vòng tham chiếu mà không cần quyền tạo symbolic link là biểu diễn chuỗi aliases bằng `Map<String,String>`. Ví dụ:

```text
short -> long -> data.txt  (regular file)
dangling -> missing.txt   (file không có)
a -> b -> a               (cycle)
self -> self              (cycle)
```

Thuật toán thường dùng:

1. Bắt đầu ở tên yêu cầu.
2. Ghi tên hiện tại vào `visited`.
3. Nếu tên đã có trong `visited` → vòng trong **graph giả lập**.
4. Nếu không có edge alias và tên là file thường đã biết → resolve thành công.
5. Nếu không có edge alias và tên không tồn tại → missing.
6. Nếu số bước follow vượt một giới hạn an toàn → dừng vì hop limit.

**Đây là mô hình kiến thức, không phải một resolver filesystem production**. Filesystem thật có Path components, relative targets, directory symlinks, normalization khác nhau theo provider, permissions, mount points và khả năng đổi dữ liệu đồng thời.

## 20. Chương trình 6: mô phỏng cycle/missing/hop limit mà không cần symbolic links

Lưu thành `LinkGraphSimulationDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class LinkGraphSimulationDemo {
    static String follow(String start, Map<String, String> aliases,
                         Set<String> files, int hopLimit) {
        Set<String> visited = new HashSet<>();
        String name = start;
        int linksFollowed = 0;
        while (true) {
            if (!visited.add(name)) return "CYCLE";
            String next = aliases.get(name);
            if (next == null) {
                return files.contains(name) ? "RESOLVED:" + name : "MISSING:" + name;
            }
            if (linksFollowed >= hopLimit) return "HOP_LIMIT";
            name = next;
            linksFollowed++;
        }
    }

    public static void main(String[] args) {
        Map<String, String> links = new HashMap<>();
        links.put("short", "long");
        links.put("long", "data.txt");
        links.put("dangling", "missing.txt");
        links.put("a", "b");
        links.put("b", "a");
        links.put("self", "self");
        Set<String> files = Set.of("data.txt");

        System.out.println("chain=" + follow("short", links, files, 8));
        System.out.println("dangling=" + follow("dangling", links, files, 8));
        System.out.println("cycle=" + follow("a", links, files, 8));
        System.out.println("self=" + follow("self", links, files, 8));
        System.out.println("limit=" + follow("short", links, files, 1));
        System.out.println("missingEntry=" + follow("unknown", links, files, 8));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 LinkGraphSimulationDemo.java
java LinkGraphSimulationDemo
```

Stdout **đã biên dịch và kiểm thử độc lập, không cần quyền symbolic link**:

```text
chain=RESOLVED:data.txt
dangling=MISSING:missing.txt
cycle=CYCLE
self=CYCLE
limit=HOP_LIMIT
missingEntry=MISSING:unknown
```

### 20.1. Giải thích

- `short -> long -> data.txt` gặp một tên trong tập file hiện hữu, nên trả `RESOLVED:data.txt`.
- `dangling -> missing.txt` kết thúc ở tên không phải link và không có file giả lập, nên trả `MISSING:missing.txt`.
- `a -> b -> a` lần thứ hai gặp `a`, có vòng.
- `self -> self` gặp lại tên `self` ngay bước kế tiếp.
- `hopLimit=1` chỉ cho follow một liên kết, nhưng chuỗi short → long → data cần hai bước, nên trả `HOP_LIMIT`.
- `unknown` không có alias edge và không nằm trong tập files, nên `MISSING:unknown`.

### 20.2. Phân biệt CYCLE với HOP_LIMIT

Không phải cứ vượt giới hạn follow links là chứng minh có vòng. Có thể có **chuỗi dài nhưng không chu kỳ**, hoặc provider áp đặt giới hạn số link thấp hơn chiều dài chuỗi. Vì thế trạng thái `HOP_LIMIT` khác với `CYCLE`.

Ngược lại, một vòng có thể được phát hiện sớm bằng tập visited khi graph đơn giản có các node/tên ổn định. Dùng một hạn mức hop vẫn là một cơ chế **phòng vệ về tài nguyên**, không phải phép chứng minh không có vòng trong filesystem thật.

### 20.3. Có nên áp dụng nguyên thuật toán này cho đường dẫn thật?

Không trực tiếp. Nếu ứng dụng phải giải chuỗi symlinks thật, còn phải xử lý:
- Target relative từ parent của từng link.
- Link nằm tại một **directory component**, không chỉ final filename.
- Tên khác nhau có thể trỏ cùng directory/file.
- `..` đi sau symbolic component có semantics khác lexical normalize.
- Race giữa `isSymbolicLink` và `readSymbolicLink`.
- Permission, file store, provider và khả năng hỗ trợ.
- Chuỗi dài hoặc thay đổi liên tục.

Dùng API có sẵn như `Path.toRealPath()`, `Files.readAttributes` và `Files.walkFileTree` khi phù hợp; nếu cần giải theo policy bảo mật đặc biệt, phải thiết kế và kiểm thử trên provider mục tiêu, không tự quảng cáo Map-based resolver là secure filesystem resolver.

## 21. Vì sao vòng tham chiếu chưa chắc là một entry “không tồn tại”?

Trong vòng `a -> b -> a`, các **directory entries `a` và `b` đều có thể tồn tại**. Điều thất bại là **quá trình follow để tìm final file**.

Do đó:
- `Files.exists(a, NOFOLLOW_LINKS)` có thể là true.
- `Files.isSymbolicLink(a)` có thể là true.
- `Files.readSymbolicLink(a)` có thể trả `b`.
- `Files.exists(a)` có thể trả false nếu provider không phân giải được, nhưng đó không phải chẩn đoán đặc thù vòng.
- `a.toRealPath()` có thể ném IOException, với loại cụ thể tùy provider.

Đừng viết logic “nếu `!Files.exists(a)` thì xóa a” khi chưa phân biệt entry, target và quyền sửa link.

## 22. Điều gì xảy ra khi link được sửa hay đích được tạo sau?

Một symlink không tự nhớ “đã từng bị broken”. Khi target xuất hiện đúng đường dẫn, link có thể bắt đầu hoạt động. Khi target biến mất, link có thể lại hỏng. Khi entry bị thay, raw target có thể thay đổi.

```text
T0: shortcut -> future.txt; future.txt chưa có   → không follow được
T1: tạo future.txt                               → follow được
T2: xóa future.txt                               → lại không follow được
T3: tạo future.txt với dữ liệu khác               → follow tới object mới
```

**Bài học về identity:** symlink bám theo **đường dẫn**, không giữ một danh tính bất biến cho object được trỏ tới ở T1. Vì thế link “latest/current” có thể thay file đích khi tên được cập nhật, và ứng dụng phải kiểm soát version/authorization.

### 22.1. Vì sao không sửa target liên tục bằng check-and-use?

Một chương trình dùng:

```java
if (Files.exists(link)) {
    String data = Files.readString(link);
}
```

Đây là snippet, **không bảo đảm** lần đọc thành công. Đích có thể bị xóa hoặc link bị thay giữa check và read. Hãy xử lý IOException tại `readString` và giữ quyền filesystem phù hợp. Với dữ liệu nhạy cảm, có thể cần một thiết kế mở file dựa trên directory handle hoặc cơ chế khác để giảm TOCTOU.

### 22.2. Link target có thể xuất hiện với loại khác

Một đường dẫn trước đó là regular file có thể bị xóa rồi thay bằng **directory** hoặc entry khác. Một symlink có thể vẫn follow đến path đó, nhưng thao tác `Files.readString` trên directory có thể thất bại. **“Target tồn tại” không đồng nghĩa “target là regular file và phù hợp với thao tác”.**

Khi loại tài nguyên quan trọng, đọc attributes và kiểm tra `isRegularFile`/`isDirectory` theo policy; xử lý race sau khi kiểm tra.

## 23. Chương trình 7: hard link còn sau khi xóa tên đầu tiên

Lưu thành `HardLinkNotDanglingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class HardLinkNotDanglingDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("hard-no-dangling-");
        Path original = dir.resolve("original.txt");
        Path hard = dir.resolve("alias.txt");
        try {
            Files.writeString(original, "STILL HERE", StandardCharsets.UTF_8);
            try {
                Files.createLink(hard, original);
            } catch (IOException | UnsupportedOperationException | SecurityException unavailable) {
                System.out.println("hardLink=SKIPPED");
                return;
            }
            System.out.println("sameBefore=" + Files.isSameFile(original, hard));
            Files.delete(original);
            System.out.println("originalGone=" + Files.notExists(original));
            System.out.println("hardStillExists=" + Files.exists(hard));
            System.out.println("hardContent=" + Files.readString(hard));
        } finally {
            Files.deleteIfExists(hard);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 HardLinkNotDanglingDemo.java
java HardLinkNotDanglingDemo
```

Stdout **đã kiểm thử trên máy hỗ trợ hard link**:

```text
sameBefore=true
originalGone=true
hardStillExists=true
hardContent=STILL HERE
```

Nếu provider/quyền không cho tạo hard link, demo in:

```text
hardLink=SKIPPED
```

Kết quả nhấn mạnh một điểm nền tảng: **xóa một hard-link name** không tạo ra dangling link theo nghĩa symbolic link. Nó chỉ xóa một directory entry, còn hard-link name khác vẫn tham chiếu file object. Khi mọi tên cuối đều bị xóa, việc thu hồi tài nguyên phụ thuộc hệ điều hành/file handles.

### 23.1. Có nên dùng hard link để thay symbolic link tránh dangling?

Không tự động. Hai loại có tính chất nghiệp vụ khác:
- Hard link yêu cầu file có sẵn, thường cùng filesystem và không portable với directory.
- Symbolic link có thể trỏ qua file stores và có thể mang đích chưa tồn tại.
- Hard link bám **object**, symbolic link bám **target path**.
- Hard link không thích hợp nếu bạn muốn alias “latest” theo một tên đích được thay thế bằng file mới.

Nếu ứng dụng cần theo version bằng tên, symlink có thể đúng hơn, nhưng phải quản lý broken states và quyền truy cập. Nếu cần cùng file identity, hard link có thể phù hợp khi provider hỗ trợ.

## 24. Những hạn chế của quyền và file-system provider

### 24.1. Vì sao Java code đúng mà vẫn không tạo được symlink?

`Files.createSymbolicLink` là API chuẩn, nhưng thao tác cần **hệ điều hành/provider cho phép**. Trên một số Windows, tạo symbolic link có thể yêu cầu quyền, chính sách hệ thống hoặc môi trường cấu hình tương ứng. Provider khác có thể không hỗ trợ symlink.

Do đó:
- `UnsupportedOperationException` cho biết optional operation không được hỗ trợ theo provider.
- `IOException` có thể mô tả lỗi tạo link, quyền, tên đã có hoặc điều kiện khác.
- `SecurityException` có thể phản ánh chính sách bảo mật.
- Một **test demo** có thể báo `SKIPPED` khi không thể tạo link.
- Một **dịch vụ production** không nên nuốt mọi IOException rồi âm thầm coi thao tác đã thành công.

### 24.2. Cần test ở đâu?

Nếu ứng dụng thật phải quản lý symbolic links, hãy kiểm thử trên:
- OS/version được sản phẩm hỗ trợ.
- File store/provider thực sẽ dùng, gồm network mounts nếu có.
- Quyền của **tài khoản chạy dịch vụ**, không chỉ tài khoản admin phát triển.
- Tình huống target missing, chain dài, directory loop, quyền bị từ chối.
- Cùng quy tắc relative path sau khi move/rename.
- Cleanup/recovery khi thao tác chỉ hoàn thành một phần.

Một chương trình in `symlink=SKIPPED` vẫn **biên dịch và thoát bình thường**; nhưng nó không chứng minh các nhánh symlink-supported hoạt động trên môi trường đó.

### 24.3. Không làm yếu bảo mật máy chỉ để test

Không khuyến khích vô hiệu hóa protections hoặc cấp quyền không cần thiết trên máy làm việc thật. Dùng một CI/container/test VM có capability phù hợp hoặc để quản trị viên cấp quyền theo chính sách tổ chức khi yêu cầu.

## 25. Phân biệt vòng link với vòng thư mục trong `walkFileTree`

Có thể có một chuỗi `a -> b -> a` không chứa directory ancestor đã duyệt, và có thể có một link `branch/back -> ..` trỏ về root đang duyệt. Cả hai khiến việc follow gặp vấn đề, nhưng **cách API báo lỗi có thể khác**.

| Tình huống | API kiểm tra phù hợp | Kết quả nên dự liệu |
| --- | --- | --- |
| `a -> b -> a` ở final filename | `readSymbolicLink` để xem raw links; `toRealPath` để thử final target | Không phân giải được, IOException theo provider |
| Directory `back -> ancestor` khi walker bật FOLLOW_LINKS | `Files.walkFileTree` + `visitFileFailed` | `FileSystemLoopException` theo hợp đồng traversal |
| Target của link bị xóa | `readAttributes(..., NOFOLLOW_LINKS)`, `toRealPath` | Entry còn; target missing hoặc I/O |
| Link trỏ ra ngoài allowed root | `toRealPath`/authorization theo policy | Có thể resolve thành công nhưng bị từ chối quyền |
| Chuỗi link quá dài | Provider/JDK path resolution | Có thể IOException hoặc giới hạn nội bộ; không mặc định là cycle |

**Không dùng tên exception làm bằng chứng duy nhất để phân biệt toàn bộ các tình huống.** Mô hình quyền, loại operation, raw link entries và trạng thái filesystem mới xác định ý nghĩa thực tế.

## 26. Bảo mật: broken links, vòng lặp và traversal không thay được kiểm soát quyền

### 26.1. Symlink có thể trỏ ra khỏi root đã cho phép

Giả sử ứng dụng chỉ được đọc dưới `/srv/app/uploads`, nhưng user có thể tạo `uploads/shortcut -> /srv/private`. Lexical path `uploads/shortcut/file.txt` nằm dưới root, nhưng real target có thể ở ngoài.

```java
Path realBase = allowedRoot.toRealPath();
Path realTarget = candidate.toRealPath();
if (!realTarget.startsWith(realBase)) {
    throw new SecurityException("outside allowed directory");
}
```

Đây là snippet trong method có biến `allowedRoot`/`candidate` và xử lý IOException. Nó **kiểm tra real containment ở thời điểm gọi**, không phải phép bảo mật hoàn chỉnh nếu attacker có quyền đổi filesystem trong thời gian check-use.

### 26.2. TOCTOU: link có thể bị đổi giữa kiểm tra và mở tệp

Ví dụ:

```text
T1: kiểm tra shortcut -> safe.txt
T2: tác nhân có quyền sửa shortcut để trỏ tới secret.txt
T3: ứng dụng mở shortcut
```

Ngay cả `toRealPath` trước đó cũng không tự bảo đảm một open sau đó **không đi tới object khác**. Cần:
- Thư mục cha và root có ownership/permissions đáng tin.
- Không cho tác nhân không tin cậy đổi symlink entries khi có thao tác nhạy cảm.
- Xem xét directory-handle-relative APIs như `SecureDirectoryStream` khi provider hỗ trợ.
- Giới hạn quyền tiến trình chạy ứng dụng.
- Có authorization theo người dùng/tài liệu riêng; path containment không thay role/ACL checks.

### 26.3. Bảo vệ công cụ cleanup và backup

Nếu đi qua cây để xóa file hoặc backup, việc bật `FOLLOW_LINKS` có thể làm walker chạm directory ngoài root hoặc gặp vòng. Đối với cleanup, thường nên **không theo symbolic links**, xử lý trực tiếp entry link khi cần và xác nhận phạm vi được phép.

**Chú ý:** trong `Files.walkFileTree`, việc không follow links là mặc định, nhưng không tự tạo snapshot hoặc bảo vệ mọi race. Nếu source tree có thể bị sửa đồng thời, từng thao tác đọc/copy/delete vẫn cần policy và exception handling.

## 27. Thiết kế một API chẩn đoán link rõ hợp đồng

Thay vì một hàm `boolean isBroken(Path p)` mơ hồ, hãy dùng kết quả biểu đạt trạng thái:

```java
enum LinkStatus {
    NOT_FOUND,
    NOT_SYMLINK,
    RESOLVED,
    TARGET_MISSING,
    LOOP_OR_HOP_ERROR,
    ACCESS_DENIED,
    UNKNOWN_IO
}
```

Đây là **snippet enum**, không phải một ứng dụng chạy độc lập. Ý nghĩa các trạng thái phải được document kỹ:

- `NOT_FOUND`: entry được xác minh không tồn tại tại thời điểm đọc.
- `NOT_SYMLINK`: entry tồn tại nhưng không phải symlink.
- `RESOLVED`: symlink được follow thành công ở thời điểm kiểm tra.
- `TARGET_MISSING`: metadata link có nhưng target theo path không tìm thấy.
- `LOOP_OR_HOP_ERROR`: lỗi giải link do vòng/giới hạn, có bằng chứng thích hợp.
- `ACCESS_DENIED`: quyền không cho xác minh hoặc đọc.
- `UNKNOWN_IO`: những lỗi còn lại chưa thể phân loại.

### 27.1. Phân biệt API dùng để hiển thị với API dùng để quyết định quyền

Một UI quản trị có thể chấp nhận `UNKNOWN_IO` và hiển thị “chưa xác minh được”. Nhưng code thực sự **đọc/ghi/xóa file** cần thực hiện thao tác có kiểm soát và xử lý IOException của thao tác đó.

Đừng lưu kết quả `RESOLVED` như một “chứng chỉ” mà mọi thao tác sau đều tin tưởng. Link có thể đổi theo thời gian.

### 27.2. Đừng để debug endpoint lộ raw paths

`readSymbolicLink` có thể trả path tới cấu trúc nội bộ. Khi log lỗi:
- Giữ thông tin đủ chẩn đoán trong log có kiểm soát.
- Không gửi full path máy chủ, thông tin user riêng hoặc stack trace thô cho client.
- Dùng ID/tên tương đối đã được sanitize trong response công khai khi cần.

## 28. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách tiếp cận đúng |
| --- | --- | --- |
| `!Files.exists(link)` → kết luận entry đã mất | Dangling link có thể còn entry | `NOFOLLOW_LINKS` và attributes |
| Nghĩ `exists` và `notExists` luôn đảo nhau | Cả hai có thể false khi không biết | Thiết kế trạng thái UNKNOWN |
| Nghĩ `readSymbolicLink` phải follow được target | Method chỉ đọc raw target | Dùng `toRealPath` khi cần final target |
| Coi `isSymbolicLink==false` là regular file | Có nhiều loại entry/lỗi | `BasicFileAttributes` |
| Nghĩ `normalize` phát hiện broken/loop | Nó chỉ xử lý lexical path | I/O metadata và resolution |
| Nhầm relative target dựa vào CWD | Relative dựa vào thư mục link | `link.getParent().resolve(rawTarget)` |
| Chỉ move link rồi tin raw relative target vẫn đúng | Parent thay đổi | Tính lại target sau move |
| Nghĩ link chỉ đứt một lần vĩnh viễn | Target có thể xuất hiện lại | Kiểm tra trạng thái hiện tại |
| Nghĩ hard link thành dangling khi tên đầu tiên bị xóa | Hard link là tên độc lập tới file | Phân biệt hard vs symlink |
| Nghĩ mọi vòng đều báo `FileSystemLoopException` từ mọi API | API/provider có thể khác | Nêu rõ trường hợp walker FOLLOW_LINKS |
| Bật `FOLLOW_LINKS` không xét ancestor | Có loop và thoát root | Policy symlink, exception handling |
| Chỉ đếm `visitFileFailed` để tìm mọi broken symlinks | Walker có thể fallback attrs của link | Kiểm tra entry/attrs riêng |
| Nuốt mọi IOException và gọi là “link missing” | Có thể thiếu quyền/I/O khác | Phân loại nguyên nhân |
| Tự giải link bằng Map rồi dùng như sandbox | Bỏ qua directory links/races | API filesystem đúng ngữ cảnh |
| Không giới hạn chuỗi link tự kiểm tra | Có thể tốn tài nguyên | Hop limit + cycle detection trong graph |
| Thấy HOP_LIMIT và báo chắc chắn CYCLE | Chuỗi có thể dài không vòng | Hai trạng thái riêng |
| Dùng `toRealPath(NOFOLLOW_LINKS)` để lấy final target | Không theo symbolic links | `toRealPath()` nếu muốn follow |
| Tin `Path.equals` là cùng file identity | Chỉ so biểu diễn Path | `Files.isSameFile` khi cần |
| Đọc/mở sau `exists` và không catch IOException | TOCTOU | Xử lý lỗi ở thao tác thực |
| Xóa “broken” link không xác minh ownership | Có thể xóa nhầm entry của user khác | Phạm vi/ủy quyền và race policy |
| Dùng code `Path.of` với target Java 7 | API này từ Java 11 | Java 7 dùng `Paths.get` |
| Ghi test SKIPPED thành PASS của symlink branch | Chưa thực thi nhánh thật | CI có capability, báo rõ |
| Dùng symlink như backup độc lập | Chỉ là alias đường dẫn | Copy/snapshot/version riêng |

## 29. Ma trận kiểm thử đề xuất

Một bộ kiểm thử chẩn đoán symbolic link nên có cả **kết quả thành công** và **kết quả không xác định**:

1. Regular file bình thường: không phải symlink.
2. Không có entry: `NoSuchFileException` từ thao tác đọc attributes.
3. Symlink hợp lệ tới regular file cùng directory.
4. Symlink trỏ tới target chưa tạo.
5. Target xuất hiện sau khi link đã tạo: link bắt đầu hoạt động.
6. Target bị xóa: link trở thành dangling.
7. Target đổi tên: link có thể trở thành dangling.
8. Raw target relative có `..`: được tính từ parent của link.
9. Chỉ di chuyển link tới parent khác: ý nghĩa raw target thay đổi.
10. Link A → B → C → regular file: chuỗi dài nhưng hợp lệ.
11. Link A → B → A: vòng hai entry.
12. Link self → self: vòng một entry.
13. Directory symlink trỏ về ancestor khi walker bật `FOLLOW_LINKS`: phát hiện loop.
14. Duyệt cùng cây khi không follow: xem link entry, không đi vòng.
15. Permission denied ở target hoặc ancestor: không báo nhầm target missing.
16. `Files.exists` và `Files.notExists` ở trạng thái không xác minh được: xử lý UNKNOWN.
17. Chuỗi link rất dài nhưng không có vòng: phân biệt HOP_LIMIT với CYCLE.
18. User có quyền đổi link/target trong lúc kiểm tra: thử nghiệm race trên môi trường được kiểm soát.
19. Provider không hỗ trợ tạo symlink: ghi `SKIPPED/UNSUPPORTED`, không đánh dấu behavior PASS.
20. Hard link còn sau khi xóa một tên: không phải dangling symbolic link.
21. Cleanup: chỉ xóa resource test tự tạo, không xóa target nằm ngoài phạm vi.
22. Quyền truy cập/tenant: link resolve thành công vẫn phải bị từ chối nếu vi phạm authorization.
23. Khả năng theo link khi directory entries đổi liên tục: IOException được xử lý.
24. Network filesystem hoặc provider khác: phân biệt optional operation và errors.

### 29.1. Test cần tách ba lớp kết quả

- **Compile PASS:** Java source có cú pháp và API hợp lệ.
- **Run PASS:** chương trình khởi chạy và thoát bình thường.
- **Symlink behavior PASS:** nhánh thật đã tạo symlink và xác minh kết quả.

Một chương trình có `symlink=SKIPPED` có thể đạt hai lớp đầu nhưng **chưa đạt lớp thứ ba**. Báo cáo kiểm thử cần nói rõ điều đó.

### 29.2. Test giả lập graph có giá trị gì?

`LinkGraphSimulationDemo` không yêu cầu quyền tạo symlink, nên có thể chạy trên bất kỳ máy JDK 17 bình thường nào. Nó xác minh thuật toán cycle detection, missing và hop limit ở **mô hình dữ liệu**. Tuy nhiên không thay cho integration test real filesystem khi chức năng production phụ thuộc symbolic links thật.

## 30. Bài tập thực hành và lời giải định hướng

**Câu 1.** Khi nào symbolic link được gọi là dangling?  
**Đáp án:** Khi entry link còn nhưng target path không phân giải được thành đối tượng đích theo hoàn cảnh đó; thường do target bị xóa/chưa tạo/đổi vị trí. Cần phân biệt với thiếu quyền hoặc lỗi I/O chưa xác minh.

**Câu 2.** `Files.readSymbolicLink(link)` có yêu cầu target đang tồn tại không?  
**Đáp án:** Không. Nó đọc raw target path của chính link.

**Câu 3.** Vì sao `Files.exists(link)==false` chưa đủ để xác nhận entry link không có?  
**Đáp án:** Mặc định theo link; target có thể mất, quyền bị chặn hoặc trạng thái không thể xác định.

**Câu 4.** Muốn kiểm tra entry có tồn tại không đi theo link, dùng gì?  
**Đáp án:** `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` hoặc tốt hơn khi cần chẩn đoán lỗi là `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)`.

**Câu 5.** `Files.exists` và `Files.notExists` có luôn là hai trạng thái đối nghịch không?  
**Đáp án:** Không. Cả hai có thể false khi trạng thái không xác định được.

**Câu 6.** Có thể tạo symlink trỏ tới file chưa có không?  
**Đáp án:** Có, nếu provider và quyền cho phép. Link có thể bắt đầu hoạt động khi target xuất hiện.

**Câu 7.** Sau khi tạo target rồi xóa lại, raw target path trong symlink có tự đổi không?  
**Đáp án:** Không. Symlink có thể hợp lệ, dangling rồi hợp lệ tiếp theo trạng thái filesystem.

**Câu 8.** Vòng `a -> b -> a` có làm hai entry `a` và `b` biến mất không?  
**Đáp án:** Không. Entries vẫn có thể tồn tại; chính việc follow đến file cuối thất bại.

**Câu 9.** `Path.normalize()` có phát hiện vòng không?  
**Đáp án:** Không. Nó không truy cập filesystem và không theo symlinks.

**Câu 10.** Khi nào `FileSystemLoopException` được tài liệu hóa rõ?  
**Đáp án:** Khi `Files.walkFileTree` được bật `FOLLOW_LINKS` và theo link dẫn đến directory ancestor đang trong nhánh traversal.

**Câu 11.** Trong walker bật FOLLOW_LINKS, mọi broken link đều vào `visitFileFailed` đúng không?  
**Đáp án:** Không. Khi target attrs không đọc được, walker thử attrs của link; nếu đọc được thì có thể gọi `visitFile` với link attrs.

**Câu 12.** Vì sao phải có hop limit nếu đã dùng Set visited trong graph simulation?  
**Đáp án:** Chuỗi có thể rất dài nhưng chưa lặp; hop limit giúp giới hạn tài nguyên. Vượt giới hạn không tự chứng minh có vòng.

**Câu 13.** Target relative được tính từ đâu?  
**Đáp án:** Từ thư mục chứa symlink, không phải working directory của ứng dụng ở thời điểm đọc.

**Câu 14.** Nếu chỉ move symlink tới thư mục mới, target relative có thể đổi ý nghĩa không?  
**Đáp án:** Có, vì parent dùng làm gốc của raw relative target đã thay đổi.

**Câu 15.** Hard link đến regular file có thành dangling khi xóa một hard-link name khác không?  
**Đáp án:** Không theo cùng nghĩa symlink. Tên hard link còn vẫn tham chiếu cùng object file.

**Câu 16.** `toRealPath(NOFOLLOW_LINKS)` có trả đường dẫn final target không?  
**Đáp án:** Không khi nó được yêu cầu không follow symlinks; cần chọn semantics phù hợp với mục đích.

**Câu 17.** Nếu `toRealPath()` ném IOException, có thể luôn báo “target missing” không?  
**Đáp án:** Không. Có thể loop, permission hoặc lỗi provider; phân loại theo nguyên nhân khi có thể.

**Câu 18.** Kiểm tra link rồi mở file có chống hoàn toàn TOCTOU không?  
**Đáp án:** Không. Directory entry/target có thể bị đổi giữa hai thời điểm.

**Câu 19.** Một link resolve thành công có nghĩa caller đủ quyền đọc dữ liệu nghiệp vụ không?  
**Đáp án:** Không. Còn cần authorization theo user, tenant, tài liệu và filesystem permissions.

**Câu 20.** Một chương trình in `symlink=SKIPPED` có chứng minh nhánh link thật đã hoạt động không?  
**Đáp án:** Không. Nó chỉ chứng minh chương trình xử lý môi trường không hỗ trợ quyền/capability; cần test bổ sung.

### Thực hành A — Đọc raw target

Trên môi trường có quyền tạo symlink, chạy `DanglingLinkDemo` và ghi nhận `storedTarget` trước/sau tạo/xóa target. Giải thích tại sao raw target không đổi dù `Files.exists(link)` đổi.

### Thực hành B — Vòng hai link

Chạy `TwoLinkCycleDemo` trên filesystem hỗ trợ. Thêm một link `c -> a` và thử đọc raw targets. Phân biệt **chỉ đọc metadata** với **follow link**.

### Thực hành C — Directory loop và visitor

Chạy `DirectoryCycleWalkDemo` trên provider hỗ trợ. Đổi handler để ném lại `FileSystemLoopException`, so sánh lượt duyệt fail-fast với policy tiếp tục nhưng báo partial scan.

### Thực hành D — Graph không có quyền symlink

Chạy `LinkGraphSimulationDemo`, thêm `x -> y -> z -> data.txt` và kiểm tra số bước. Thêm một chuỗi dài không vòng, thử hopLimit=2 và giải thích khác biệt `HOP_LIMIT`/`CYCLE`.

### Thực hành E — Chẩn đoán thiếu entry

Chạy `LinkStateInspectorDemo`; in trạng thái trước khi tạo `ordinary.txt`, sau khi tạo và sau khi xóa. Chỉ trong thư mục tạm mà chương trình sở hữu.

### Thực hành F — Relative targets

Chạy `LinkPathSemanticsDemo`. Thay raw target thành `../../shared/report.txt` rồi tính kết quả khi link ở hai thư mục khác nhau. Đừng nối string bằng ký tự `/` để xây native Path.

### Thực hành G — Hard vs symlink

Chạy `HardLinkNotDanglingDemo` và so sánh với `DanglingLinkDemo`. Viết ngắn sự khác nhau giữa xóa một directory entry và làm hỏng target path.

### Thực hành H — Trạng thái UNKNOWN

Thiết kế `enum` có `ENTRY_MISSING`, `TARGET_MISSING`, `RESOLVED`, `UNKNOWN_IO` và `LOOP`. Đảm bảo các lỗi quyền/I/O không bị lẫn vào `TARGET_MISSING`.

### Thực hành I — Không theo link khi xóa

Dựng một cây tạm có symlink trỏ ra một thư mục tạm riêng; viết visitor chỉ liệt kê entries mà **không** theo link. Xác minh không mở/đụng file ngoài cây. Không dùng ví dụ này trực tiếp để xóa dữ liệu người dùng.

### Thực hành J — TOCTOU và bảo mật

Lập bảng hai attacker models: (1) caller chỉ gửi tên file nhưng không được phép sửa filesystem; (2) caller được phép đổi symlink trong vùng upload. Giải thích vì sao kiểm tra `toRealPath` trước rồi mở file là **rủi ro khác nhau** giữa hai mô hình và có thể cần handle-relative ops.

## 31. Checklist trước khi triển khai một link inspector

1. Root và Path do ai kiểm soát?
2. Bạn cần xem **entry link** hay **final target**?
3. Đã dùng `NOFOLLOW_LINKS` ở bước đọc metadata link khi cần chưa?
4. Đã xử lý trạng thái `exists==false` và `notExists==false` cùng lúc chưa?
5. Có phân biệt entry missing với target missing không?
6. Có lưu raw target do `readSymbolicLink` trả không, và có kiểm soát việc lộ path không?
7. Target relative có được phân giải từ parent của link không?
8. Có thử `toRealPath()` khi cần target thật và xử lý IOException cụ thể không?
9. Có kiểm soát quyền và trường hợp không đọc được ancestor không?
10. Có kiểm tra file type của final target trước operation không?
11. Có bật `FOLLOW_LINKS` khi duyệt cây không? Có policy rõ chưa?
12. Có handler `FileSystemLoopException` trong `visitFileFailed` không?
13. Có xử lý trường hợp broken link đi qua `visitFile` khi walker fallback attrs không?
14. Nếu tự duyệt graph, có `visited` và hop limit tách biệt không?
15. Có coi `normalize()`/`toAbsolutePath()` chỉ là lexical operations không?
16. Có mô hình permission/TOCTOU cho phần filesystem không tin cậy không?
17. Có bao giờ xóa/ghi đè link mà chưa xác minh ownership/authorization không?
18. Có phân biệt hard link và symbolic link trong nghiệp vụ không?
19. Có tạo mọi fixture test trong thư mục tạm riêng không?
20. Có báo `SKIPPED` thay vì giả định symlink branch đã chạy nếu OS không hỗ trợ không?
21. Có integration test trên các OS/providers mục tiêu không?
22. Có giới hạn thông tin full path trong log/response không?
23. Có giữ nguyên link API NIO.2 hiện đại thay vì dùng cách kiểm tra legacy không?
24. Có chỉ mở file thật sau khi áp dụng quyền và xử lý exception tại thao tác I/O không?

## 32. Tài liệu chính thức

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createSymbolicLink`, `readSymbolicLink`, `isSymbolicLink`, `exists`, `notExists`, `readAttributes`, `walkFileTree`, `delete` và `createLink`.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `getParent`, `resolve`, `relativize`, `normalize`, `toRealPath` và ngữ nghĩa follow link.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` ở các API hỗ trợ.
- [Java SE 17 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemLoopException.html): checked exception khi phát hiện filesystem cycle.
- [Java SE 17 — FileSystemException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html): thông tin file/otherFile/reason phục vụ chẩn đoán.
- [Java SE 17 — FileVisitor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html): các callback và xử lý traversal errors.
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `isSymbolicLink`, `isDirectory`, `isRegularFile`.
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS`.
- [Dev.java — Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/): tài liệu hiện đại về traversal, directory cycles và `visitFileFailed`.

**Kết luận:** Dangling symbolic link là **entry link còn nhưng target không phân giải được**, còn circular reference là **chuỗi links dẫn trở lại đối tượng đã gặp hoặc đường duyệt directory ancestor**. Dùng `NOFOLLOW_LINKS` để xem entry, `readSymbolicLink` để đọc raw target, `toRealPath` để thử phân giải final target, và `Files.walkFileTree` với `FOLLOW_LINKS`/`FileSystemLoopException` khi duyệt cây có chủ đích. `Files.exists` không phải chứng nhận an toàn hay kết luận missing tuyệt đối; luôn phân biệt lỗi quyền, I/O, race và mô hình bảo mật. Các API NIO.2 từ Java 7 vẫn phù hợp trong Java hiện đại.

# Phân biệt liên kết cứng và liên kết tượng trưng trong Java (Hard Link vs Symbolic Link)

> **Chủ đề:** Hiểu bản chất **hard link** (liên kết cứng) và **symbolic link** (liên kết tượng trưng, thường gọi *symlink*), điểm giống và khác về danh tính đối tượng, đường dẫn, nội dung, xóa/đổi tên, file không còn tồn tại, giới hạn filesystem và quyền truy cập. Sử dụng các API NIO.2 còn hiện hành: `Files.createLink`, `Files.createSymbolicLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`, `Files.isSameFile` và `LinkOption.NOFOLLOW_LINKS`. Các API liên kết cơ bản có từ **Java 7** và vẫn dùng trong Java 17+. Các chương trình dưới đây biên dịch bằng **JDK 17** để dùng các tiện ích `Path.of` và `Files.readString/writeString` (được bổ sung từ Java 11).

## 1. Hai loại liên kết trả lời hai câu hỏi khác nhau

Khi làm việc với filesystem, đừng nhầm **tên đường dẫn** với **đối tượng/tài nguyên thực** đằng sau tên đó. Một file có thể được truy cập qua nhiều tên. Nhưng hai tên đó có thể liên hệ với nhau theo những cách hoàn toàn khác nhau.

**Hard link** là **một directory entry/tên khác của cùng một đối tượng file** trong filesystem. Với một hệ thống hỗ trợ hard links cho regular files, hai tên hard link cùng tham chiếu dữ liệu của **cùng file**. Không có một “file gốc” cố hữu về bản chất chỉ vì một tên được tạo trước; hai tên đều là các entry đến cùng đối tượng.

**Symbolic link** là **một entry liên kết chứa/thể hiện đường dẫn đến một đích**. Khi chương trình dùng link theo chế độ *follow links*, hệ thống thử phân giải đường dẫn đích. Nếu đích bị xóa, đổi vị trí hoặc đường dẫn link bị sai, link có thể trở thành **broken/dangling symlink**.

Sơ đồ mô hình khái niệm:

```text
HARD LINK (cùng đối tượng, nhiều tên)

folder/
  report.txt   ─────┐
  alias.txt    ─────┴────> file object X ───> bytes/data

SYMBOLIC LINK (một entry mang tham chiếu đường dẫn)

folder/
  report.txt   ───────────> file object X ───> bytes/data
  shortcut.txt ──"report.txt"──> phân giải tên report.txt
```

Đây là **sơ đồ khái niệm**, không phải cách mọi filesystem triển khai trên đĩa ở cấp inode/reparse point. Tên “inode” thường gặp trong Unix/POSIX nhưng không phải khái niệm portable bắt buộc trong API Java. Hãy tập trung vào **hợp đồng của Files/Path và khả năng của file-system provider**.

### 1.1. Điều giống nhau

- Cả hai đều giúp chương trình tiếp cận tài nguyên qua một tên đường dẫn khác.
- Cả hai tồn tại trong cấu trúc thư mục của filesystem nếu provider hỗ trợ.
- Cả hai có thể liên quan đến đọc, ghi, đổi tên, xóa và truy cập metadata.
- Cả hai được NIO.2 cung cấp API rõ ràng trong `java.nio.file.Files`.
- Cả hai vẫn phải tuân theo quyền filesystem; tạo được link không có nghĩa có quyền truy cập mọi đích.
- Không loại nào tự động là **bản sao dự phòng độc lập** của nội dung.

### 1.2. Điều khác biệt quyết định

- Với hard link, **đổi nội dung qua một tên** thường được quan sát qua tên còn lại vì là cùng đối tượng.
- Với symbolic link, **đổi tên/xóa đích** có thể làm link trỏ tới một tên không còn hợp lệ.
- Hard link thông thường cần file đích **đã tồn tại** và cùng filesystem.
- Symbolic link có thể được tạo với **đích chưa tồn tại**; bản thân symlink là một entry riêng.
- Xóa một hard-link name làm mất **một tên**, nhưng đối tượng vẫn truy cập được bằng những hard-link names còn lại.
- Xóa một symbolic-link name thường xóa **chính link**, không xóa file mà nó trỏ đến.

## 2. Bảng so sánh nhanh

| Tiêu chí | Hard link | Symbolic link |
| --- | --- | --- |
| API tạo | `Files.createLink(link, existing)` | `Files.createSymbolicLink(link, target)` |
| Bản chất | Tên/directory entry khác cho cùng file | Entry chứa tham chiếu đường dẫn đến đích |
| Đích có cần tồn tại khi tạo? | **Có** | **Không bắt buộc** |
| Dữ liệu có bị sao chép? | Không tạo bản sao nội dung thông thường | Không tạo bản sao nội dung; link mang thông tin đích |
| Đổi nội dung qua tên link | Cùng dữ liệu với tên khác của file | Khi theo link, thao tác lên file được phân giải ở đích |
| Xóa tên đích ban đầu | Hard link còn lại vẫn truy cập được file | Có thể trở thành dangling link |
| Chuyển tên đích sang tên khác | Các hard link còn lại vẫn cùng file | Có thể hỏng nếu đường dẫn link không còn dẫn tới đích |
| Tham chiếu tới thư mục | Thường bị cấm/không portable | Có thể hỗ trợ tùy OS, provider, quyền |
| Qua filesystem/volume khác | Thông thường **không** | Có thể trỏ tới nơi khác, tùy hệ thống và đường dẫn |
| Có thể đọc raw target path? | Không có “raw target path” kiểu symlink | `Files.readSymbolicLink(link)` |
| `Files.isSymbolicLink(...)` | `false` với regular hard link | `true` nếu entry là symlink |
| `Files.exists(link)` khi đích biến mất | Link name còn là entry tới file | Mặc định có thể `false` vì theo link |
| Xác định cùng file | `Files.isSameFile(a,b)` thường `true` | `isSameFile(link,target)` có thể `true` khi link hợp lệ |
| Giới hạn | FileStore/provider, quyền, loại đối tượng | Provider, quyền tạo link, cách phân giải, link loops |

Bảng trên mô tả **mô hình thông thường** và các hợp đồng NIO.2. Các filesystem có thể khác nhau về thuộc tính trên từng directory entry, loại file được phép hard link, cách xử lý đặc quyền và link tới nơi lưu trữ khác. Không chuyển một đặc điểm Linux sang mọi máy Windows/macOS/network filesystem mà không kiểm tra.

## 3. API Java NIO.2 để làm việc với liên kết

Các import thường dùng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
```

Các API trọng tâm:

```java
Path hardLink = Files.createLink(newHardLinkPath, existingFilePath);

Path softLink = Files.createSymbolicLink(
        newSymbolicLinkPath, targetPath);

Path storedTarget = Files.readSymbolicLink(softLink);

boolean isSoft = Files.isSymbolicLink(softLink);

boolean sameFile = Files.isSameFile(existingFilePath, hardLink);

boolean entryExists = Files.exists(softLink, LinkOption.NOFOLLOW_LINKS);
```

Đây là các **snippet**, không phải một class chạy độc lập: các biến `Path` phải được khai báo và những thao tác I/O cần xử lý/khai báo `IOException`.

### 3.1. Thứ tự tham số có ý nghĩa

`Files.createLink(link, existing)` nhận:
- `link`: **tên mới** cần tạo.
- `existing`: **file đã tồn tại** để thêm một tên khác.

`Files.createSymbolicLink(link, target)` nhận:
- `link`: **tên symlink mới** cần tạo.
- `target`: **đường dẫn được lưu/tham chiếu** bởi symlink, có thể tuyệt đối hoặc tương đối.

Đừng đảo chỗ hai tham số. Với symbolic link, một `target` tương đối được diễn giải **tương đối với vị trí chứa link**, không phải luôn tương đối với working directory của tiến trình lúc sau.

### 3.2. Java 7 hay Java 17?

`Files.createLink`, `Files.createSymbolicLink`, `Files.readSymbolicLink`, `Files.isSymbolicLink`, `Files.isSameFile`, `Files.exists`, `LinkOption.NOFOLLOW_LINKS` và `Path` đều là phần NIO.2 có từ Java 7.

Các ví dụ chạy với Java 17 nên sử dụng:
- `Path.of(...)`: được bổ sung trong Java 11. Với code phải biên dịch trên Java 7–10, dùng `java.nio.file.Paths.get(...)`.
- `Files.writeString(...)` và `Files.readString(...)`: từ Java 11. Với Java 7, dùng `Files.write(...)`, `Files.readAllBytes(...)` hoặc streams và charset rõ ràng.
- `Files.readString` mặc định giải mã UTF-8; trong ví dụ dùng chuỗi ASCII ngắn nên output không phụ thuộc cài đặt console.

Điều này **không biến NIO.2 hard/symlink API thành kiến thức mới riêng Java 17**; nó chỉ chọn cách viết hiện đại, dễ chạy để học.

## 4. Hard link: hai tên, cùng một đối tượng file

Với regular file đã tồn tại:

```java
Path original = Path.of("data", "report.txt");
Path alias = Path.of("data", "other-name.txt");

Files.createLink(alias, original);
```

Đây là snippet, cần file `original` tồn tại và provider cho phép tạo hard link. Sau đó, trong mô hình filesystem thông thường, cả `original` và `alias` là directory entries trỏ tới **cùng file**. Không có bước nhân đôi toàn bộ bytes như `Files.copy`.

### 4.1. Cập nhật nội dung qua một tên

Giả sử `report.txt` và `other-name.txt` là hard links hợp lệ đến cùng file. Nếu bạn mở `other-name.txt` và ghi đè nội dung, sau đó đọc `report.txt`, nội dung vừa ghi được thấy qua tên kia.

**Cần phân biệt hai hoạt động:**

- **Ghi vào file đang được tham chiếu** qua một hard-link name → cùng đối tượng file thay đổi.
- **Thay thế một directory entry bằng file mới** (ví dụ move một file mới lên tên `report.txt`) → tên `report.txt` có thể trỏ sang **đối tượng mới**, còn hard link `other-name.txt` vẫn tham chiếu **đối tượng cũ**.

Vì vậy quy tắc “hai hard links luôn đồng bộ nội dung mãi mãi” là diễn đạt thiếu điều kiện. Nó đúng **khi cả hai tên vẫn liên kết tới cùng file object**; replacement bằng một đối tượng khác có thể làm quan hệ đó chấm dứt.

### 4.2. Hard link không có khái niệm “đường dẫn đích để đọc”

Với symbolic link, `Files.readSymbolicLink` trả về một Path biểu diễn target. Với hard link **không có thông tin tương đương “tên gốc là gì”** theo mô hình Java.

Đừng cố gọi `Files.readSymbolicLink(hardLink)` để tìm tên “file gốc”. Nó không phải symbolic link; method có thể ném `NotLinkException` hoặc IOException tương ứng. Nếu muốn kiểm tra hai tên chỉ cùng file hay không, dùng `Files.isSameFile`.

### 4.3. Đích của hard link phải tồn tại

`Files.createLink(alias, original)` yêu cầu `original` là đường dẫn đến file đã tồn tại; nó không được thiết kế để tạo “lời hứa tên file sẽ xuất hiện trong tương lai”. Nếu existing không có, thao tác có thể ném `NoSuchFileException`/`IOException`.

Ngoài ra, **tên alias mới** không được đã bị chiếm bởi file, directory hay entry khác. Với tên đã có, thường nhận `FileAlreadyExistsException`. Đây là subclass IOException; đừng bắt mọi IOException rồi cho rằng chỉ do xung đột tên.

## 5. Chương trình 1: tạo hard link, ghi qua alias và xóa tên ban đầu

Lưu thành `HardLinkBasicsDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class HardLinkBasicsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("hard-basics-");
        Path original = dir.resolve("original.txt");
        Path alias = dir.resolve("alias.txt");
        try {
            Files.writeString(original, "HELLO", StandardCharsets.UTF_8);
            try {
                Files.createLink(alias, original);
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("hardLink=SKIPPED");
                return;
            }
            System.out.println("hardLink=CREATED");
            System.out.println("sameFile=" + Files.isSameFile(original, alias));
            System.out.println("aliasIsSymbolic=" + Files.isSymbolicLink(alias));
            Files.writeString(alias, "UPDATED", StandardCharsets.UTF_8);
            System.out.println("originalContent=" +
                    Files.readString(original, StandardCharsets.UTF_8));
            Files.delete(original);
            System.out.println("aliasSurvives=" + Files.exists(alias));
            System.out.println("aliasContent=" +
                    Files.readString(alias, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy với JDK 17:

```bash
javac -encoding UTF-8 --release 17 HardLinkBasicsDemo.java
java HardLinkBasicsDemo
```

Stdout **đã chạy và kiểm chứng trên filesystem hỗ trợ hard link**:

```text
hardLink=CREATED
sameFile=true
aliasIsSymbolic=false
originalContent=UPDATED
aliasSurvives=true
aliasContent=UPDATED
```

Nếu filesystem/provider/quyền hiện tại không cho tạo hard link, chương trình chủ động báo:

```text
hardLink=SKIPPED
```

### 5.1. Diễn giải từng dòng

- `Files.createLink(alias, original)` tạo thêm tên `alias.txt` cho file đang ở `original.txt`.
- `Files.isSameFile(original, alias)` trả true: hai Path đang dẫn đến **cùng một file** trên máy kiểm thử.
- `Files.isSymbolicLink(alias)` là false: **hard link không phải symbolic link**.
- `Files.writeString(alias,"UPDATED")` cập nhật **file chung**; đọc lại qua `original` cũng nhận `UPDATED`.
- `Files.delete(original)` xóa một directory entry. `alias` còn tồn tại và vẫn có thể đọc nội dung, vì vẫn là một tên hợp lệ cho file đó.

**Không kết luận** rằng “bất kỳ file nào đã bị xóa qua tên đầu tiên đều luôn khôi phục được nhờ hard link”: điều này chỉ đúng nếu **hard-link name khác vẫn tồn tại và có thể truy cập**. Nếu xóa hết các tên, khả năng truy cập/tái sử dụng dung lượng còn phụ thuộc filesystem và file handles đang mở.

### 5.2. Tại sao không in đường dẫn tạm đầy đủ?

`Files.createTempDirectory` tạo tên có hậu tố ngẫu nhiên; hiển thị full path khiến output khác giữa các lần chạy và hệ điều hành. Ví dụ in các **thuộc tính ngữ nghĩa** cùng nội dung biết trước, thuận tiện cho việc tự kiểm chứng.

### 5.3. `SKIPPED` có nghĩa gì?

`SKIPPED` không phải “Java chưa có API”. Nó nói **môi trường thử nghiệm không thực hiện được thao tác tạo hard link** vì provider, quyền hoặc lỗi I/O. Với production, cần báo nguyên nhân thực và xem `SKIPPED` là trạng thái test chưa chứng minh capability, không phải PASS cho hành vi liên kết.

Trong demo dùng `catch (IOException | UnsupportedOperationException | SecurityException)` để kết thúc an toàn vì bài học không yêu cầu bắt buộc tạo link trên máy người học. Một ứng dụng cần hard link để đúng nghiệp vụ **không nên âm thầm bỏ qua mọi IOException**; phải phân biệt lỗi quyền, tên đã có, thiếu file, lỗi thiết bị và unsupported.

## 6. Hard link không phải bản sao: so sánh với `Files.copy`

Một bản sao dữ liệu và một hard link có thể ban đầu đọc ra cùng chuỗi, nhưng quan hệ của chúng khác nhau.

`Files.copy(source, copy)` tạo **một file/đối tượng đích mới** chứa dữ liệu được copy trong trường hợp thông thường. Còn `Files.createLink(hard, source)` tạo **một tên khác cho cùng file hiện hữu**. Nếu nội dung source được cập nhật sau đó, hard link thấy thay đổi còn bản sao độc lập **không tự cập nhật**.

### 6.1. Chương trình 2: hard link vs copy

Lưu thành `HardLinkVsCopyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class HardLinkVsCopyDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("hard-copy-");
        Path original = dir.resolve("source.txt");
        Path alias = dir.resolve("hard.txt");
        Path copy = dir.resolve("copy.txt");
        try {
            Files.writeString(original, "V1", StandardCharsets.UTF_8);
            Files.copy(original, copy);
            try {
                Files.createLink(alias, original);
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("hardLink=SKIPPED");
                return;
            }
            Files.writeString(original, "V2", StandardCharsets.UTF_8);
            System.out.println("original=" + Files.readString(original));
            System.out.println("hard=" + Files.readString(alias));
            System.out.println("copy=" + Files.readString(copy));
            System.out.println("hardIsSameFile=" + Files.isSameFile(original, alias));
            System.out.println("copyIsSameFile=" + Files.isSameFile(original, copy));
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(copy);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 HardLinkVsCopyDemo.java
java HardLinkVsCopyDemo
```

Stdout **đã xác minh khi hard link được hỗ trợ**:

```text
original=V2
hard=V2
copy=V1
hardIsSameFile=true
copyIsSameFile=false
```

Nếu không tạo được hard link, test in `hardLink=SKIPPED` và không thực hiện nhánh so sánh danh tính.

### 6.2. Bẫy thường gặp: hai file giống bytes chưa chắc là cùng file

`Files.readString(a).equals(Files.readString(b))` chỉ chứng minh **nội dung chuỗi đang đọc giống nhau** tại các thời điểm đọc. Nó không chứng minh `a` và `b` là hard links.

`Files.isSameFile(a,b)` trả lời câu hỏi khác: hai Path hiện có **định vị cùng file** theo filesystem/provider. Một bản copy có thể bằng nội dung nhưng là đối tượng khác, nên isSameFile thường false. Ngược lại hard links cùng file có thể trỏ tới dữ liệu đang được thay đổi; hai lần đọc có thể khác do concurrency dù danh tính giống nhau.

### 6.3. Liên kết cứng có phải backup?

Không. Nếu một ứng dụng ghi đè/làm hỏng bytes của file thông qua **bất kỳ hard-link name nào**, tất cả tên cùng tham chiếu tới nội dung bị tác động. Hard link không phải bản sao bảo vệ trước corruption hoặc cập nhật nhầm.

Nếu muốn sao lưu độc lập, cần copy/snapshot/versioning với chính sách kiểm chứng nội dung, quyền và khôi phục rõ ràng. Bản sao cũng cần bảo vệ trước thay đổi đồng thời khi copy, nhưng có danh tính tách biệt.

## 7. Một bất ngờ quan trọng: thay thế một tên có thể “tách” hard links

Bởi hard link là một **directory entry**, việc ghi nội dung qua tên đã có khác với việc **thay thế directory entry bằng một đối tượng file mới**.

Giả sử có hai tên `current.txt` và `saved-hard.txt` cùng tham chiếu đối tượng OLD. Nếu ứng dụng tạo một file NEW khác rồi `Files.move(replacement, current, REPLACE_EXISTING)`, entry `current.txt` có thể được thay thế để trỏ sang file NEW; còn `saved-hard.txt` vẫn trỏ tới OLD.

Đừng nghĩ hard links luôn vĩnh viễn có cùng nội dung sau **mọi** kiểu operation ở tên file.

### 7.1. Chương trình 3: hard link giữ đối tượng cũ sau khi replacement

Lưu thành `HardLinkReplaceDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class HardLinkReplaceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("hard-replace-");
        Path original = dir.resolve("current.txt");
        Path hard = dir.resolve("saved-hard.txt");
        Path replacement = dir.resolve("replacement.tmp");
        try {
            Files.writeString(original, "OLD", StandardCharsets.UTF_8);
            try {
                Files.createLink(hard, original);
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("hardLink=SKIPPED");
                return;
            }
            Files.writeString(replacement, "NEW", StandardCharsets.UTF_8);
            System.out.println("beforeSameFile=" + Files.isSameFile(original, hard));
            Files.move(replacement, original, StandardCopyOption.REPLACE_EXISTING);
            System.out.println("afterSameFile=" + Files.isSameFile(original, hard));
            System.out.println("current=" + Files.readString(original));
            System.out.println("oldHard=" + Files.readString(hard));
        } finally {
            Files.deleteIfExists(replacement);
            Files.deleteIfExists(hard);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 HardLinkReplaceDemo.java
java HardLinkReplaceDemo
```

Stdout đã xác minh trên file store của máy kiểm thử:

```text
beforeSameFile=true
afterSameFile=false
current=NEW
oldHard=OLD
```

### 7.2. Phân tích kết quả

**Trước move:** `current.txt` và `saved-hard.txt` cùng định vị một file; `Files.isSameFile` trả true.

**Sau move:** tên `current.txt` bị thay bằng entry của file từ `replacement.tmp`, trong khi `saved-hard.txt` vẫn là hard link đến file cũ. Vì vậy:
- `current=NEW`;
- `oldHard=OLD`;
- `afterSameFile=false`.

Điều này phân biệt **sửa nội dung** với **thay thế tên**. Nó cũng giải thích tại sao không nên xem hard link là một con trỏ mềm dẻo “luôn theo tên gốc sau này”.

**Cảnh báo phạm vi:** thao tác move/replace có ràng buộc provider, quyền và trạng thái target. Chương trình được kiểm thử trên file store mặc định; không khẳng định mọi môi trường hỗ trợ cùng một hành vi replace trong mọi tình huống, đặc biệt với file đang mở hoặc provider đặc biệt. `REPLACE_EXISTING` cũng **không tự tạo bảo đảm atomicity**.

## 8. Symbolic link là một entry tham chiếu tới đường dẫn

API tạo:

```java
Path symbolicLink = Files.createSymbolicLink(
        Path.of("data", "shortcut.txt"),
        Path.of("report.txt")
);
```

Đây là snippet. Với `link` ở `data/shortcut.txt` và `target` là `report.txt` tương đối, filesystem hiểu target theo **thư mục chứa symbolic link**, tức `data/report.txt` trong ví dụ. Không lấy working directory hiện tại làm gốc mặc định của link relative target sau khi đã tạo.

### 8.1. Symlink có thể chỉ đến tệp hoặc thư mục

Tùy provider/OS/quyền, symbolic link có thể trỏ tới một **regular file** hoặc **directory**. Khi link trỏ đến directory và chương trình theo link, việc đi sâu vào đường dẫn có thể dẫn sang một cây khác.

Đây là khác biệt lớn với hard link tới directory: **hard links cho directories thường bị hạn chế/cấm trên filesystem phổ biến** để tránh những cấu trúc khó quản lý. Java `Files.createLink` không hứa portable việc thêm hard link tới mọi directory.

### 8.2. Symlink có thể chứa target chưa tồn tại

`Files.createSymbolicLink(link, target)` không yêu cầu target hiện hữu tại thời điểm tạo. Bạn có thể tạo một link tới `future.txt` trước khi file `future.txt` xuất hiện; khi file xuất hiện đúng vị trí, link có thể bắt đầu phân giải thành công.

Ngược lại hard link phải thêm directory entry cho **một file đã tồn tại**. Đây là khác biệt cấu trúc, không đơn thuần do lựa chọn exception.

### 8.3. Symlink không tự tạo dữ liệu đích

Tạo một link tên `shortcut.txt` không có nghĩa tạo một bản sao bytes của `report.txt`. Khi `Files.readString(shortcut)` được gọi trong chế độ follow link và target tồn tại/hợp lệ, ứng dụng đọc file đích mà đường dẫn link dẫn tới.

Cần phân biệt:
- **Path của link:** vị trí entry shortcut.
- **Target path được lưu trong link:** được `readSymbolicLink` trả lại.
- **Real path của object đã phân giải:** có thể lấy bằng `toRealPath()` khi file thật tồn tại và permission/provider cho phép.

Không nhất thiết ba Path này có cùng nội dung chuỗi.

## 9. Chương trình 4: tạo, đọc và nhận diện symbolic link

Lưu thành `SymbolicLinkBasicsDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymbolicLinkBasicsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symlink-basics-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("shortcut.txt");
        try {
            Files.writeString(target, "HELLO", StandardCharsets.UTF_8);
            try {
                Files.createSymbolicLink(link, Path.of("data.txt"));
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("symbolicLink=SKIPPED");
                return;
            }
            System.out.println("symbolicLink=CREATED");
            System.out.println("storedTarget=" + Files.readSymbolicLink(link));
            System.out.println("linkDetected=" + Files.isSymbolicLink(link));
            System.out.println("followRegular=" +
                    Files.readAttributes(link, BasicFileAttributes.class).isRegularFile());
            System.out.println("noFollowSymbolic=" +
                    Files.readAttributes(link, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS).isSymbolicLink());
            System.out.println("sameFile=" + Files.isSameFile(link, target));
            System.out.println("readThroughLink=" + Files.readString(link));
            Files.delete(target);
            System.out.println("followExistsAfterDelete=" + Files.exists(link));
            System.out.println("linkEntryExists=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("linkStillSymbolic=" + Files.isSymbolicLink(link));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SymbolicLinkBasicsDemo.java
java SymbolicLinkBasicsDemo
```

**Nếu hệ thống hỗ trợ việc tạo symlink và cấp quyền**, dự kiến:

```text
symbolicLink=CREATED
storedTarget=data.txt
linkDetected=true
followRegular=true
noFollowSymbolic=true
sameFile=true
readThroughLink=HELLO
followExistsAfterDelete=false
linkEntryExists=true
linkStillSymbolic=true
```

**Kết quả thực tế trên Windows kiểm thử không cho tạo symlink:**

```text
symbolicLink=SKIPPED
```

**Trung thực với kết quả test:** toàn bộ class đã biên dịch và chạy thành công, nhưng **nhánh tạo symlink không được kiểm thử bằng một link thật trên máy này**. Output ở nhánh supported là kết quả kỳ vọng theo API với file store hoạt động bình thường; cần chạy trên hệ thống có quyền/capability nếu muốn xác minh tích hợp.

### 9.1. Đọc output theo thứ tự

- `Files.readSymbolicLink(link)` trả raw target path `data.txt`; nó **không mở file nội dung**.
- `Files.isSymbolicLink(link)` xem bản thân directory entry, nên true khi link được tạo.
- `Files.readAttributes(link, BasicFileAttributes.class)` mặc định theo symlink và thấy một regular file.
- `readAttributes(..., NOFOLLOW_LINKS)` yêu cầu xem metadata của **entry symlink**.
- `Files.isSameFile(link,target)` có thể true vì khi phân giải, hai Path cùng định vị file hiện hữu.
- `Files.readString(link)` đọc dữ liệu thông qua link và trả `HELLO`.

Khi xóa **file đích** bằng `Files.delete(target)`:
- Mặc định `Files.exists(link)` có thể trả false vì quá trình theo link không đến được target.
- `Files.exists(link, NOFOLLOW_LINKS)` xem **entry link** và thường true nếu link vẫn hiện hữu.
- `Files.isSymbolicLink(link)` vẫn true.
- `Files.readString(link)` nếu thử tiếp sẽ không còn đọc được `HELLO` qua một target hợp lệ.

### 9.2. False khi kiểm tra tồn tại không phải luôn chứng minh “không có”

Javadoc nêu `Files.exists` có thể trả false cả khi **không xác định được** trạng thái tồn tại (ví dụ do hạn chế quyền). Khi xử lý broken symlink, kết hợp kiểm tra follow/no-follow, xử lý IOException khi mở file thật và mô hình quyền; đừng thiết kế logic bảo mật dựa vào một boolean như một “bằng chứng tuyệt đối”.

## 10. Symbolic link tương đối: tính từ **thư mục chứa link**

Đây là lỗi tạo link phổ biến: có thể chương trình tạo link ở một directory, rồi truyền một Path tương đối được tính **từ working directory**, dẫn đến link sai.

Giả sử cây:

```text
root/
  shared/
    report.txt
  views/
    latest.txt -> ../shared/report.txt
```

Đích mong muốn của `views/latest.txt` là `shared/report.txt`. Raw target hợp lý là `../shared/report.txt`, vì **bắt đầu tại `views/`, không phải tại root/cwd**.

### 10.1. Cách tính chính xác

```java
Path parent = link.getParent();
Path relativeTarget = parent.relativize(existingFile);
Files.createSymbolicLink(link, relativeTarget);
```

Đây là snippet với `link` và `existingFile` thuộc các Path tương thích. `relativize` tạo đường dẫn tương đối từ parent của link đến file hiện hữu. Nếu muốn ví dụ portable, dùng `Path` để tính thay vì nối chuỗi dấu `/` hoặc `\`.

**Lưu ý:** `parent.relativize(existingFile)` đòi Path tương thích về absolute/relative và provider. Nếu có root/drive khác, việc tạo relative target có thể không hợp lệ; khi đó phải xem lại chính sách và khả năng sử dụng target absolute.

### 10.2. Chương trình 5: relative symlink đúng vị trí

Lưu thành `RelativeSymbolicLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RelativeSymbolicLinkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("relative-link-");
        Path shared = root.resolve("shared");
        Path views = root.resolve("views");
        Path file = shared.resolve("report.txt");
        Path link = views.resolve("latest.txt");
        try {
            Files.createDirectory(shared);
            Files.createDirectory(views);
            Files.writeString(file, "REPORT", StandardCharsets.UTF_8);
            try {
                Files.createSymbolicLink(link,
                        Path.of("..", "shared", "report.txt"));
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("symbolicLink=SKIPPED");
                return;
            }
            Path stored = Files.readSymbolicLink(link);
            System.out.println("storedIsRelative=" + !stored.isAbsolute());
            System.out.println("storedTarget=" +
                    stored.toString().replace('\\', '/'));
            System.out.println("resolvedMatches=" +
                    link.getParent().resolve(stored).normalize().equals(file));
            System.out.println("sameFile=" + Files.isSameFile(link, file));
            System.out.println("content=" + Files.readString(link));
            Files.delete(link);
            System.out.println("targetSurvives=" + Files.exists(file));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(file);
            Files.deleteIfExists(views);
            Files.deleteIfExists(shared);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 RelativeSymbolicLinkDemo.java
java RelativeSymbolicLinkDemo
```

**Nhánh kỳ vọng trên filesystem có hỗ trợ symlink:**

```text
storedIsRelative=true
storedTarget=../shared/report.txt
resolvedMatches=true
sameFile=true
content=REPORT
targetSurvives=true
```

**Nhánh quan sát trên máy kiểm thử hiện tại:**

```text
symbolicLink=SKIPPED
```

### 10.3. Vì sao lại có `replace('\\','/')`?

Nó chỉ giúp **in** đường dẫn theo một dạng thống nhất khi thực hành trên Windows/Unix. Toàn bộ thao tác thực tế xây Path bằng `Path.of` và `resolve`, không biến dấu phân cách thành quy tắc cố định trong mã I/O.

**Không nên dùng chuỗi output sau replace như một cách chuyển đường dẫn native.** Với Windows, Unix, ZIP filesystem hoặc provider khác, parsing theo provider có thể khác nhau.

### 10.4. Đường dẫn tương đối có lợi gì?

Nếu bạn **di chuyển cả cấu trúc thư mục theo cùng mối quan hệ tương đối** và không thay đổi khoảng cách giữa link và target, relative symbolic link có thể vẫn hoạt động. Nhưng nếu chỉ di chuyển **riêng link** hoặc **riêng target**, raw target có thể không còn đến đúng nơi.

Symlink lưu **ý nghĩa của đường dẫn**; nó không có “liên hệ danh tính bất biến” giống hard link. Đó là lý do nhiều installer/package manager dùng symlinks để đặt tên “current/latest”, nhưng phải quản lý target/version và permissions cẩn thận.

## 11. Broken/dangling symlink: entry tồn tại nhưng không theo đến đích

Một symlink “dangling” là symlink có directory entry hiện hữu nhưng **đường dẫn đích không thể được phân giải thành một file hiện hữu** theo môi trường ở thời điểm kiểm tra. Có thể do:
- Đích chưa từng được tạo.
- Đích đã bị xóa.
- Đích được rename/move sang vị trí khác.
- Đường dẫn tương đối của link được tính sai.
- Thiếu quyền truy cập một thành phần hoặc có sự cố filesystem.

Cần phân biệt ba phép hỏi:

```java
boolean followsToSomething = Files.exists(link);

boolean entryItselfExists =
        Files.exists(link, LinkOption.NOFOLLOW_LINKS);

boolean entryIsSymbolicLink = Files.isSymbolicLink(link);
```

Đây là snippets. Khi link hợp lệ và trỏ đến file có thể truy cập, các giá trị thường đều true. Khi đích bị xóa nhưng link entry còn:
- `Files.exists(link)` thường false vì mặc định theo link.
- `Files.exists(link, NOFOLLOW_LINKS)` thường true.
- `Files.isSymbolicLink(link)` thường true.

Đừng coi `Files.exists(link)==false` là đủ để bảo đảm **tên đường dẫn chưa có entry**. Một dangling link có thể đang chiếm tên đó; `Files.createFile(link)` hoặc tạo symlink mới cùng tên có thể thất bại với `FileAlreadyExistsException`.

### 11.1. `readSymbolicLink` không cần target tồn tại

`Files.readSymbolicLink(link)` đọc **target path lưu trong link**. Nếu target bị xóa, method vẫn có thể trả Path đó vì nó đọc metadata link, không cần mở file đích. Do đó đây là công cụ phù hợp để chẩn đoán “link đang trỏ đến đâu” kể cả khi link bị đứt.

Tuy nhiên, nếu **entry link** không tồn tại hoặc nó không thực sự là symlink, method có thể ném `IOException`/`NotLinkException` hoặc lỗi khác theo provider. `readSymbolicLink` là optional operation trong API.

### 11.2. Không sửa broken link bằng cách xóa bừa

Một thao tác bảo trì có thể muốn thay dangling link bằng target mới. Trước khi `Files.delete(link)` hoặc replace:
- Kiểm tra đúng vùng đường dẫn và quyền ownership của ứng dụng.
- Xác định link có đang bị thay bởi một tác nhân khác không.
- Biết policy xử lý race/overwrite.
- Tránh tình huống bạn tưởng một tên là broken symlink nhưng nó đã trở thành file thật hoặc thuộc về người khác khi thực hiện thao tác xóa.

API kiểm tra tồn tại không khóa directory entry. Với môi trường thù địch, cần thiết kế thao tác theo quyền và handle, không chỉ “check rồi delete”.

## 12. `Files.isSameFile`, `Path.equals` và so sánh nội dung là ba câu hỏi khác

| Phép so sánh | Câu hỏi | Ghi chú |
| --- | --- | --- |
| `a.equals(b)` | Hai đối tượng Path có cùng biểu diễn Path theo provider không? | So sánh Path, không buộc mở file |
| `Files.isSameFile(a,b)` | Hai Path có định vị **cùng file** không? | Có thể cần I/O, có IOException |
| So sánh bytes/content | Nội dung hiện có bằng nhau không? | Không chứng minh file identity |
| `Files.isSymbolicLink(path)` | Entry ở Path có là symlink không? | Không phát hiện hard link như một loại file riêng |

### 12.1. Vì sao `Path.equals` của hard links có thể false?

`original.txt` và `alias.txt` là **hai tên khác nhau**, nên hai `Path` có thể không equal theo cú pháp/path semantics. Nhưng `Files.isSameFile(original,alias)` có thể true vì chúng định vị cùng object.

Ngược lại, hai file độc lập có nội dung giống nhau vẫn có thể `isSameFile=false`.

### 12.2. Một góc cạnh của `Files.isSameFile`

Javadoc nói khi **hai Path objects bằng nhau**, method có thể trả true **mà không kiểm tra file có tồn tại**. Do đó đừng gọi `Files.isSameFile(path,path)` rồi coi đó là bằng chứng rằng file thật hiện hữu.

Với hai Path khác nhau, provider có thể cần I/O để xác minh danh tính; có thể ném IOException. Phương pháp này là phép thử file identity, **không phải lời hứa giữ file bất biến** sau thời điểm gọi.

### 12.3. Khi symlink trỏ đúng target

Khi link hoạt động bình thường, `Files.isSameFile(link, target)` thường true vì quá trình phân giải dẫn đến cùng file. Cần phân biệt:
- **Link entry** là một đối tượng/entry riêng với raw target path.
- Khi **đi theo link**, Path link định vị file target.
- Metadata của bản thân link lấy bằng `NOFOLLOW_LINKS` khác với metadata của target.

Vì vậy `isSameFile(link,target)==true` không có nghĩa link là hard link. Dùng `isSymbolicLink` để xác định bản thân entry có phải symbolic link.

## 13. `BasicFileAttributes` và `NOFOLLOW_LINKS`

`Files.readAttributes(path, BasicFileAttributes.class)` mặc định **theo symbolic link** ở nơi API/provider hỗ trợ. Nếu muốn đọc attributes của **entry symlink**, truyền `LinkOption.NOFOLLOW_LINKS`.

Ví dụ:

```java
BasicFileAttributes followed =
        Files.readAttributes(link, BasicFileAttributes.class);

BasicFileAttributes own =
        Files.readAttributes(
            link,
            BasicFileAttributes.class,
            LinkOption.NOFOLLOW_LINKS
        );
```

Đây là snippet với `Path link` và method xử lý IOException.

Nếu `link` trỏ tới một regular file:
- `followed.isRegularFile()` thường true.
- `own.isSymbolicLink()` thường true.

Một **hard link tới regular file** lại không phải symbolic link: `Files.readAttributes(hard, BasicFileAttributes.class, NOFOLLOW_LINKS).isRegularFile()` thường true và `isSymbolicLink()` false.

### 13.1. `fileKey()` có dùng để nhận diện hard links được không?

`BasicFileAttributes.fileKey()` trả một khóa nhận diện file **nếu provider hỗ trợ**, nhưng được phép trả `null`. Ngữ nghĩa của key phụ thuộc filesystem/provider và không phải ID nghiệp vụ portable.

Nếu hệ thống có fileKey đáng tin trong đúng ngữ cảnh, hard links tới cùng file có thể có key giống nhau; tuy nhiên đừng dùng fileKey như một bảo đảm xuyên filesystem, sau copy/backup, sau delete/recreate hoặc trên tất cả providers.

Để hỏi hai đường dẫn hiện tại có định vị cùng file không, `Files.isSameFile` là API có chủ đích hơn, dù vẫn cần xử lý IOException/race.

### 13.2. Có phương thức `Files.isHardLink` không?

Không có phương thức `Files.isHardLink(path)` trong NIO.2 chuẩn tương đương `Files.isSymbolicLink`.

Một hard link là một **tên bình thường của file**, nên chỉ nhìn một Path đơn lẻ không nhất thiết biết có những tên khác cùng file hay không.

Trên một số filesystem kiểu Unix, metadata như `unix:nlink` có thể thể hiện số hard links:

```java
Object linkCount = Files.getAttribute(path, "unix:nlink");
```

Đây là snippet **không portable**; attribute view `unix` không được bảo đảm trên Windows hoặc provider khác. Không dùng nó làm phần bắt buộc của một thư viện Java đa nền tảng. Nếu không hỗ trợ, provider có thể báo `UnsupportedOperationException`/`IllegalArgumentException` hoặc IOException tùy API.

## 14. Chương trình 6: nhận diện attributes của hard link và symlink

Lưu thành `LinkAttributesDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.LinkOption;
import java.nio.file.attribute.BasicFileAttributes;

public class LinkAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("link-attributes-");
        Path file = dir.resolve("original.bin");
        Path hard = dir.resolve("hard.bin");
        Path soft = dir.resolve("soft.bin");
        try {
            Files.write(file, new byte[] {1, 2, 3});
            try {
                Files.createLink(hard, file);
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("hardLink=SKIPPED");
                return;
            }
            BasicFileAttributes attrs =
                    Files.readAttributes(hard, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);
            System.out.println("hardIsRegular=" + attrs.isRegularFile());
            System.out.println("hardIsSymbolic=" + attrs.isSymbolicLink());
            System.out.println("hardSharesIdentity=" + Files.isSameFile(file, hard));
            try {
                Files.createSymbolicLink(soft, Path.of("original.bin"));
                BasicFileAttributes linkAttrs =
                        Files.readAttributes(soft, BasicFileAttributes.class,
                                LinkOption.NOFOLLOW_LINKS);
                System.out.println("softIsSymbolic=" + linkAttrs.isSymbolicLink());
                System.out.println("softSharesTargetIdentity=" +
                        Files.isSameFile(file, soft));
            } catch (IOException | UnsupportedOperationException | SecurityException error) {
                System.out.println("soft=SKIPPED");
            }
        } finally {
            Files.deleteIfExists(soft);
            Files.deleteIfExists(hard);
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 LinkAttributesDemo.java
java LinkAttributesDemo
```

Stdout **đã kiểm chứng trên máy hỗ trợ hard links nhưng không cho tạo symbolic links**:

```text
hardIsRegular=true
hardIsSymbolic=false
hardSharesIdentity=true
soft=SKIPPED
```

Khi môi trường cho phép tạo symlink, sau ba dòng hard link có thể xuất hiện:

```text
softIsSymbolic=true
softSharesTargetIdentity=true
```

Các dòng `soft...` là **kết quả kỳ vọng**, không phải output đã chạy trên máy hiện tại. Hãy kiểm thử trong CI có quyền tạo symbolic link nếu ứng dụng phụ thuộc vào link thật.

### 14.1. Vì sao hard link không bị nhận diện bởi `isSymbolicLink`?

Một hard-link name đại diện cùng file object, **không phải entry chứa target path cần được follow**. Vì thế với regular file, BasicFileAttributes đọc không follow vẫn có thể báo regular, còn `isSymbolicLink` false.

### 14.2. Metadata có thể trùng nhưng không phải quy tắc tuyệt đối

Javadoc `Files.createLink` lưu ý việc attributes được duy trì **theo file** hay **theo từng directory entry** là chi tiết của filesystem. Không khẳng định tất cả timestamp/ACL của hai hard-link names luôn có cách lưu/hiển thị giống hệt trên mọi provider, kể cả khi chúng định vị cùng nội dung.

Trong ứng dụng cần bảo mật hoặc metadata, kiểm tra cụ thể trên file store đang sử dụng và đừng dùng một timestamp như ID của đối tượng.

## 15. Hành vi xóa: xóa một tên khác với xóa file đích

### 15.1. Xóa hard-link name

Giả sử `original` và `hard` là hard links tới cùng một file; gọi:

```java
Files.delete(original);
```

làm mất **directory entry `original`**. File vẫn truy cập được qua `hard` nếu hard link còn và quyền truy cập cho phép.

Không có nguyên tắc “xóa file gốc thì hard link cũng mất”. Khái niệm “tên gốc” thường chỉ là cách con người gọi tên được tạo trước.

Khi tên cuối cùng bị xóa, filesystem có thể thu hồi dữ liệu sau khi không còn tham chiếu/file handle sử dụng; thời điểm giải phóng storage cụ thể phụ thuộc OS/filesystem.

### 15.2. Xóa symbolic-link name

Giả sử `shortcut` là symlink tới `report`:

```java
Files.delete(shortcut);
```

Theo hợp đồng `Files.delete`, nếu path là symbolic link thì xóa **chính symbolic link**, **không xóa final target** mà link dẫn đến.

Do đó sau khi xóa shortcut, `report` vẫn có thể tồn tại. Đây là hành vi cần nhớ khi dọn các link phiên bản “latest/current”.

### 15.3. Xóa target của symbolic link

Nếu gọi `Files.delete(report)`, file đích biến mất. Link `shortcut` vẫn là một directory entry có thể tồn tại nhưng trở thành dangling, và `Files.exists(shortcut, NOFOLLOW_LINKS)` có thể vẫn true.

### 15.4. Không dùng `Files.deleteIfExists` trên đường dẫn chưa xác minh

Mặc dù `deleteIfExists` có vẻ an toàn vì không báo lỗi khi không có entry, nó **vẫn là thao tác xóa dữ liệu**. Nếu người dùng có thể kiểm soát một phần đường dẫn, cần kiểm tra scope/authorization và race/permissions. Không sử dụng `exists` theo link rồi suy ra đúng đối tượng sẽ bị xóa khi thực hiện operation sau đó.

## 16. Đổi tên và di chuyển link

`Files.move(source, target, options...)` di chuyển/đổi tên một entry.

Với **symbolic link**, Javadoc quy định nếu source là symlink, thao tác move di chuyển **chính link**, không di chuyển file đích mà link trỏ tới.

Điều này gây một tình huống thú vị:

- Symlink có target **tương đối**, chẳng hạn `../data/file.txt`.
- Nếu move **riêng symlink** từ thư mục A sang thư mục B, cùng chuỗi target tương đối giờ được hiểu từ **B**.
- Nếu B có cấu trúc khác, symlink có thể không còn trỏ đúng file.
- Cần tính lại relative target hoặc dùng một chiến lược định vị tương thích với thao tác move.

Với hard link, đổi tên một trong các directory entries thông thường không làm các hard links khác ngừng tham chiếu file hiện hữu. Nhưng nếu một entry bị thay thế **bằng file object khác**, quan hệ identity có thể thay đổi như `HardLinkReplaceDemo`.

### 16.1. Phải tách `move` với `copy`

`Files.copy` có semantics riêng khi source là symlink:
- Mặc định, nếu source là symbolic link và provider hỗ trợ, việc copy thường copy **file đích cuối** chứ không nhất thiết tạo một symlink mới.
- Với `LinkOption.NOFOLLOW_LINKS` trong copy options, API yêu cầu **không theo symlink**, có thể sao chép **chính link** nếu provider hỗ trợ; thuộc tính link khi copy phụ thuộc implementation.
- `Files.move` với source symlink thì di chuyển link entry, không di chuyển target.

Đừng đoán cả copy và move đều có cùng quy tắc chỉ vì đều nhận `Path`.

### 16.2. Thêm `REPLACE_EXISTING` không loại bỏ nhu cầu kiểm tra quyền

Nếu target của move/copy đã tồn tại, `REPLACE_EXISTING` có thể thay entry target theo hợp đồng. Đây là thao tác có thể phá dữ liệu hoặc chuyển tên công khai sang đối tượng khác. Nó không tự cấp quyền overwrite cho caller và không tự tạo tính nguyên tử. Với thao tác sensitive, phải có chính sách ownership/authorization và xử lý lỗi phù hợp.

## 17. Giới hạn filesystem: hard link thường cần cùng file store

Hard link trên filesystem phổ biến thường cần **mọi directory entry tới một file nằm trong cùng filesystem**. Bạn thường không thể tạo hard link từ volume A tới file trên volume B, dù có thể nhìn thấy chúng dưới một cây đường dẫn.

Symlink có thể chứa một Path tuyệt đối đến một vị trí khác, ví dụ volume/mount khác, **nếu OS/provider và quyền cho phép**. Nhưng việc target có được giải quyết thành công ở runtime hay không vẫn phụ thuộc môi trường.

### 17.1. Kiểm tra FileStore có bảo đảm hard link thành công không?

Không. `Files.getFileStore(path)` có thể giúp xác định nơi lưu trữ của một path hiện hữu hoặc thư mục cha, nhưng **cùng FileStore không đủ** để bảo đảm:
- provider hỗ trợ tạo hard link;
- caller có đủ quyền;
- target là loại file cho phép;
- tên link chưa bị chiếm;
- filesystem không có ràng buộc đặc biệt.

Dùng `Files.createLink` và xử lý lỗi thực tế. Tránh tự khẳng định một capability chỉ từ `System.getProperty("os.name")`.

### 17.2. Directory hard links

Không tạo hard link tới directory như một bước portable trong bài. Phần lớn filesystem thông dụng hạn chế hard links tới thư mục để bảo vệ cấu trúc cây; một số providers hoặc môi trường đặc thù có quy tắc khác. Nếu ứng dụng chỉ cần alias đến directory, symbolic link có thể là lựa chọn phù hợp **khi môi trường hỗ trợ và chính sách bảo mật cho phép**.

### 17.3. Windows và quyền tạo symbolic link

Khả năng tạo symbolic link ở Windows có thể phụ thuộc quyền đặc biệt, chính sách hệ thống và cấu hình môi trường. Vì thế một ứng dụng Java có thể biên dịch hoàn toàn đúng nhưng `Files.createSymbolicLink` vẫn ném IOException trên một máy cụ thể.

Đây không phải lý do để hướng người học tắt các biện pháp bảo vệ máy hoặc thay đổi chính sách hệ thống không cần thiết. Kiểm thử trong môi trường có quyền phù hợp, hoặc xử lý `UNSUPPORTED/SKIPPED` rõ ràng.

### 17.4. Network filesystem, ZIP và provider khác

`Path` không phải luôn đến từ local OS filesystem. Một số provider biểu diễn ZIP archives hoặc hệ thống ảo; không phải tất cả hỗ trợ symlink/hard link. Một đường dẫn có hình thức tương tự không chứng minh provider hỗ trợ link.

Nếu cần tính portable cho một thư viện, hãy:
- xác định file-system provider mà Path thuộc về;
- xử lý UnsupportedOperationException/IOException có phân loại;
- có feature detection thông qua một phép thử an toàn trong thư mục tạm do ứng dụng sở hữu, nếu cần;
- không giả định quyền/semantics hệ thống ngoài vùng ứng dụng kiểm soát.

## 18. Symlink tới directory và vòng lặp khi duyệt cây

Một symbolic link có thể trỏ về một **ancestor** hoặc dẫn tới nơi có đường dẫn quay lại nó, tạo ra vòng lặp:

```text
project/
  src/
    back -> ../          (link trỏ lại project/)
```

Nếu một công cụ duyệt cây **theo symlink** mà không kiểm soát vòng lặp, việc truy cập có thể lặp/đi ngoài phạm vi.

Java `Files.walkFileTree` có chế độ mặc định **không theo symbolic links**. Khi chọn `FileVisitOption.FOLLOW_LINKS`, walker có cơ chế phát hiện loop; `visitFileFailed` có thể nhận `FileSystemLoopException`.

Mẫu minh họa:

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor
);
```

Đây là snippet với `Path root` và visitor đã khai báo. Không dùng chế độ này cho dữ liệu không tin cậy khi chưa có policy symlink/containment và xử lý lỗi phù hợp.

**Phân biệt với hard link:** hard link tới regular file không khiến một lần directory tree traversal đột nhiên có một cây thư mục mới cần đi vào. Nhưng các công cụ thống kê có thể **đếm trùng dữ liệu** khi hai hard-link names được liệt kê riêng. Nếu muốn tính dung lượng *unique file objects*, cần chiến lược nhận dạng file phù hợp thay vì cộng size của tất cả Path.

## 19. Hard link count và dung lượng lưu trữ

Trên một số filesystem, một file object có **link count** mô tả số directory entries tham chiếu tới nó. Tạo hard link thường tăng count; xóa một tên thường giảm count.

Trong Java chuẩn **không có** một method `Files.getHardLinkCount(path)` portable. Một số Unix providers hỗ trợ dynamic attribute `unix:nlink`; hãy xem đó là dữ liệu **provider-specific**.

### 19.1. Hard link có nhân đôi dung lượng không?

Tạo thêm hard-link name **không thông thường sao chép toàn bộ bytes của file**. Nó thêm entry tham chiếu tới dữ liệu hiện hữu. Tuy nhiên, dung lượng metadata và chính sách phân bổ storage phụ thuộc filesystem; không nên tuyên bố thêm hard link tốn **đúng 0 byte** theo mọi cách đo dung lượng.

Ngược lại, tạo một bản copy độc lập thường cần một đối tượng file riêng, nhưng những filesystem hỗ trợ copy-on-write/reflink/deduplication có thể tối ưu việc lưu trữ vật lý. Vì vậy đừng nhận dạng hard link chỉ dựa vào số byte storage tăng/giảm.

### 19.2. Vì sao tool thống kê dung lượng cần quan tâm?

Nếu thư mục chứa `original.txt` và `hard.txt` cùng trỏ tới một file 1 GiB, cộng `Files.size` cho từng Path sẽ ra **2 GiB logical sizes cộng dồn**, dù cả hai tên có thể cùng một dữ liệu trên đĩa.

Nếu mục tiêu là thống kê file entries, cách cộng này có thể đúng theo định nghĩa. Nếu mục tiêu là dung lượng unique objects, phải tránh đếm trùng bằng identity/fileKey theo provider hoặc cơ chế khác. Cần nêu rõ định nghĩa số liệu và xử lý hard links đúng phạm vi.

## 20. Bảo mật: symbolic link có thể đưa đường dẫn ra ngoài thư mục được phép

Giả sử ứng dụng chỉ được đọc trong `/srv/app/uploads`. Người dùng có quyền tạo một symlink:

```text
/srv/app/uploads/public.txt -> /srv/app/private/secret.txt
```

Một phép kiểm tra **lexical**:

```java
Path base = allowedRoot.toAbsolutePath().normalize();
Path candidate = base.resolve(relativeUserPath).normalize();
boolean lexicalInside = candidate.startsWith(base);
```

Đây là snippet. Nó có thể trả true vì tên `public.txt` nằm dưới base, **dù target của symlink nằm ngoài base**. `normalize()` chỉ xử lý cấu trúc `.`/`..`, không giải toàn bộ symlink.

Khi cần đánh giá **một đối tượng có thật** và policy cho phép đi theo link, có thể dùng:

```java
Path realBase = allowedRoot.toRealPath();
Path realTarget = candidate.toRealPath();

if (!realTarget.startsWith(realBase)) {
    throw new SecurityException("outside allowed directory");
}
```

Đây là snippet trong method xử lý `IOException`. Nó kiểm tra **real path tại thời điểm gọi**, không phải một cơ chế sandbox tuyệt đối.

### 20.1. Giới hạn TOCTOU

Sau khi kiểm tra `realTarget.startsWith(realBase)`, một tác nhân có quyền sửa directory entries có thể thay link hoặc ancestor trước khi chương trình mở file. Đây là rủi ro **time-of-check to time-of-use**. Do đó:
- Kiểm soát quyền tạo/đổi symlink trong root và parent directories.
- Khi cần bảo đảm cao, cân nhắc các thao tác dựa trên directory handles, như `SecureDirectoryStream` nếu provider hỗ trợ.
- Không cho process có quyền cao tùy ý follow user-controlled links ra ngoài vùng của nghiệp vụ.
- Phân biệt authorization theo user/document với containment theo vị trí path.

### 20.2. `NOFOLLOW_LINKS` không phải một phép bảo vệ thần kỳ

`LinkOption.NOFOLLOW_LINKS` hướng dẫn các API được hỗ trợ **không theo symbolic link** tại ngữ cảnh tương ứng. Nhưng thêm một option ở một lời gọi không tự bảo đảm toàn bộ **các thành phần cha** của path không có symlink. Chi tiết từng API và provider có ý nghĩa.

Nếu cần cấm symlink, thiết kế quy trình duyệt/validate từng thành phần và quyền filesystem phù hợp, thay vì kiểm tra `Files.isSymbolicLink(candidate)` một lần rồi tin rằng mọi ancestor đều an toàn.

### 20.3. Bảo mật hard link cũng không tự động

Hard links có thể tạo **thêm đường dẫn truy cập cùng một dữ liệu**, nên chính sách quyền cần tính đến việc dữ liệu có nhiều tên. Trên nhiều hệ thống, quyền hard link bị hạn chế nhằm tránh một số hành vi khai thác quyền sở hữu.

Không dùng hard link để “vượt qua” filesystem permissions và không cho rằng một tên dưới thư mục tin cậy có nghĩa data ownership hoàn toàn thuộc về thư mục đó. Mọi thao tác đọc/ghi/xóa phải gắn với quyền và mục tiêu ứng dụng.

## 21. Lỗi cần dự liệu khi tạo liên kết

| Tình huống | API liên quan | Loại lỗi hoặc kết quả cần xử lý |
| --- | --- | --- |
| Tên link mới đã có | `createLink`, `createSymbolicLink` | Thường `FileAlreadyExistsException`, hoặc IOException theo provider |
| Hard link tới file chưa tồn tại | `createLink` | `NoSuchFileException`/IOException tùy provider |
| Hard link qua file stores | `createLink` | Thường IOException do filesystem không thể tạo hard link |
| Provider không hỗ trợ hard link | `createLink` | `UnsupportedOperationException` hoặc I/O errors theo hợp đồng/môi trường |
| Provider không hỗ trợ symbolic link | `createSymbolicLink` | `UnsupportedOperationException` hoặc lỗi I/O/quyền |
| Không đủ quyền tạo link | Các API tạo | IOException, AccessDeniedException hoặc lỗi security tương ứng |
| Đọc raw target của entry không phải symlink | `readSymbolicLink` | `NotLinkException` nếu provider dùng, hoặc IOException |
| Symlink target bị xóa | `exists(link)`, `readString(link)` | Exists theo link có thể false; read nội dung có thể thất bại |
| Link trỏ vòng lặp | Các thao tác follow | Có thể có FileSystemLoopException/IOException theo API |
| Path source/target ở provider không tương thích | Các API phối hợp Path | UnsupportedOperationException/ProviderMismatchException/IOException tùy method |
| Dữ liệu bị thay đổi đồng thời | Các thao tác liên tiếp | TOCTOU, trạng thái có thể khác qua các lần kiểm tra |

### 21.1. Tại sao không bắt mọi IOException rồi bỏ qua?

Trong chương trình **học** tạo link, nhánh `SKIPPED` giúp người học vẫn chạy phần kiểm thử khác trên máy không hỗ trợ/không có quyền. Nhưng trong một ứng dụng thực:
- Nếu hard link là điều kiện bắt buộc, **không được silently fallback** sang copy vì semantics khác.
- Nếu symlink là optional, cần báo fallback mode khác biệt cho caller.
- Không coi `FileAlreadyExistsException` là unsupported: có thể tên thuộc dữ liệu người khác và không được ghi đè.
- Nếu cần retry, phải xem trạng thái target/link đã có hay bị đổi từ lần trước.
- Không tự xóa đích cũ khi lỗi tạo link.

Một lỗi mạng/permission không thể được hiểu tự động là “provider không hỗ trợ”. Thông báo lỗi cần rõ nhưng không nên tiết lộ raw full path nội bộ cho client không đáng tin.

## 22. Khi nào nên chọn hard link, symlink hay copy?

| Nhu cầu | Phương án thường cân nhắc | Lý do |
| --- | --- | --- |
| Muốn hai tên cùng định vị một regular file | **Hard link** nếu same filesystem và provider hỗ trợ | Thêm directory entry cho cùng file, không nhân đôi nội dung thông thường |
| Muốn alias “latest/current” theo đường dẫn có thể thay đổi | **Symlink** nếu OS/provider/quyền cho phép | Link mang tham chiếu path; có thể quản lý đường dẫn đích |
| Muốn link đến directory | **Symlink** thường phù hợp hơn | Directory hard link không portable |
| Cần đường dẫn đích có thể chưa tồn tại | **Symlink** | Target có thể tạo sau |
| Cần liên kết giữa các volumes/file stores | **Symlink** nếu được hỗ trợ và target có thể phân giải | Hard link thường cần cùng filesystem |
| Cần bản sao dữ liệu độc lập | **Copy/backup** | Hard/symlink không thay việc có bản nội dung riêng |
| Muốn thay thế một tên file công khai bằng phiên bản mới | File mới + move/rename theo policy | Hard link cũ có thể giữ object cũ; symlink cần quản lý target |
| Cần tương thích nhất quán trên đa provider | **Kiểm tra capability + chiến lược fallback được định nghĩa** | Không có bảo đảm mọi environment hỗ trợ links |
| Cần ngăn user path đi ra ngoài root | Permission/containment/authorization | Chọn loại link không tự giải quyết security |

### 22.1. Không tự chuyển hard link thất bại thành symlink

Hai loại có semantics xóa/đổi tên, target và identity khác nhau. Nếu sản phẩm cần tính chất **cùng file object kể cả khi tên đầu tiên bị xóa**, fallback sang symlink có thể **vi phạm yêu cầu**. Ngược lại khi sản phẩm muốn alias theo tên target có thể thay đổi, hard link không tự bám theo các lần thay entry của target name.

Mọi fallback phải được mô tả trong hợp đồng, kiểm thử và báo cho caller.

### 22.2. Không dùng symlink như một cơ chế transaction

Đổi một symlink “current” sang bản mới có thể là một thành phần của kiến trúc versioned files, nhưng cách tạo link mới, thay link cũ và tính nguyên tử/độ bền metadata phụ thuộc provider và open/move policies. Chỉ có một symlink chưa đảm bảo transaction nhiều tệp, không tự bảo vệ trước mất điện hoặc race giữa writer/reader.

## 23. Các bẫy thường gặp

| Sai lầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| Nghĩ hard link là một “file shortcut” chứa target path | Nó là directory entry tới cùng file | Dùng `createLink` và hiểu file identity |
| Nghĩ symlink là một hard link có tên khác | Nó mang tham chiếu đường dẫn, có thể đứt | Dùng `createSymbolicLink`/`readSymbolicLink` |
| Cho rằng hai file cùng nội dung là hard links | Copy cũng có nội dung giống | Dùng `Files.isSameFile` |
| Nghĩ hard link có “file gốc” luôn là tên được tạo trước | Các tên cùng tham chiếu file | “Original” chỉ là cách đặt tên của chương trình |
| Nghĩ tạo hard link phải sao chép toàn bộ bytes | Nó thêm tên file, không tạo bản copy thường | Phân biệt `createLink` với `copy` |
| Dùng hard link làm backup độc lập | Sửa file qua một tên sửa cùng data | Dùng copy/snapshot/versioning |
| Nghĩ xóa tên gốc làm hard link hết đọc được | Hard link còn tên và dữ liệu | `HardLinkBasicsDemo` |
| Nghĩ hard link luôn bám theo một path đã bị replace | Replacement có thể làm hai tên trỏ object khác nhau | `HardLinkReplaceDemo` |
| Nghĩ symlink target bắt buộc tồn tại khi tạo | API cho phép target chưa tồn tại | Xử lý dangling symlink |
| Dùng `Files.exists(link)` để quyết định có entry symlink không | Mặc định theo link, dangling có thể false | `exists(..., NOFOLLOW_LINKS)` khi cần |
| Gọi `readSymbolicLink` trên hard link | Hard link không lưu raw target path | `isSameFile`, attribute/provider APIs |
| Nghĩ relative symlink dựa vào CWD mỗi khi mở | Dựa vào thư mục chứa link | Tính relative từ `link.getParent()` |
| Tự ghép `"/"` để tính target trên mọi OS | Parsing khác nhau theo provider | `Path.resolve`/`relativize` |
| Nghĩ symlink tới directory luôn theo khi `walkFileTree` | Mặc định không follow | Cân nhắc `FOLLOW_LINKS` riêng |
| Bật `FOLLOW_LINKS` không kiểm soát loop/outside root | Có thể vòng lặp/thoát phạm vi | Policy rõ, xử lý `FileSystemLoopException` |
| Cho rằng `NOFOLLOW_LINKS` một chỗ bảo vệ mọi ancestor | Có thể có link ở thư mục cha | Xét toàn bộ quá trình traversal và permissions |
| Dùng `Path.equals` thay `isSameFile` để tìm hard-link identity | So Path representation, không file identity | `Files.isSameFile` |
| Dùng `isSameFile(path,path)` làm existence check | Có thể trả true không cần I/O | `Files` phù hợp + xử lý IOException |
| Dùng `isSymbolicLink==false` để kết luận “không phải hard link” | Hard link thường không được phân biệt bằng method này | Identity và mục tiêu chính sách |
| Dùng `unix:nlink` và mặc định nó có trên Windows | Provider-specific | Không dựa vào Unix attr để viết API portable |
| Dùng hard link qua nhiều volumes mà không kiểm tra | Thường không hỗ trợ | Tạo cùng FileStore hoặc dùng chiến lược khác |
| Thấy symbolic test SKIPPED rồi ghi PASS behavior | Chưa thực thi nhánh supported | Test trên máy/CI có quyền |
| Xóa link mà không kiểm tra scope/ownership | Có thể ảnh hưởng dữ liệu hoặc entry khác | Validation/authorization |
| Dùng link types để suy ra quyền truy cập | Filesystem permissions không được thay thế | Kiểm tra quyền ở OS và ứng dụng |

## 24. Checklist review mã xử lý liên kết

1. Mục tiêu là **cùng file object**, **alias tới đường dẫn** hay **bản sao độc lập**?
2. Đã phân biệt đúng `createLink(link,existing)` và `createSymbolicLink(link,target)` chưa?
3. Với hard link, file `existing` có thật và thuộc filesystem hỗ trợ không?
4. Tên link mới có thể đã được dùng không? Có policy cho `FileAlreadyExistsException` không?
5. Có cấm hoặc kiểm soát hard links tới directory theo portability chưa?
6. Nếu symlink target là relative, đã tính từ **thư mục chứa link** chưa?
7. Nếu target bị xóa/rename, ứng dụng có xử lý dangling link không?
8. Khi dùng `Files.exists`, có cần `NOFOLLOW_LINKS` để hỏi về entry bản thân link không?
9. Có hiểu `isSymbolicLink` không phát hiện hard links như một kiểu đặc biệt không?
10. Có dùng `Files.isSameFile` khi thật sự cần so file identity không?
11. Có biết `isSameFile(path,path)` không chứng minh file đang tồn tại không?
12. Nếu di chuyển một symlink, đường dẫn relative target còn đúng từ vị trí mới không?
13. Nếu move/replace một hard-link name, các tên còn lại có thể giữ object cũ không?
14. Nếu copy từ symlink, có định nghĩa follow/no-follow rõ ràng chưa?
15. Nếu duyệt cây có symlinks, đã xét vòng lặp và phạm vi ngoài root chưa?
16. Nếu nhận input người dùng, đã giới hạn root, quyền, authorization và TOCTOU chưa?
17. Nếu thống kê dung lượng, có thể có nhiều hard-link entries trỏ cùng dữ liệu không?
18. Các test có tạo resource trong temp directory do chương trình sở hữu không?
19. Có xử lý trường hợp OS/provider không cấp quyền tạo symbolic links không?
20. Có phân biệt kết quả **SKIPPED** với nhánh behavior được kiểm chứng không?
21. Có ghi rõ Java 7 NIO.2 core và Java 11 utility APIs trong ví dụ JDK 17 không?
22. Cleanup có tránh xóa file thực của người dùng không?

## 25. Câu hỏi ôn tập kèm đáp án

**Câu 1.** Hard link khác symbolic link căn bản ở đâu?  
**Đáp án:** Hard link là một directory entry khác cho **cùng file object**; symbolic link là entry tham chiếu **một đường dẫn target** cần được phân giải khi dùng.

**Câu 2.** Muốn tạo hard link trong Java dùng method gì?  
**Đáp án:** `Files.createLink(link, existing)`; `existing` là file đã có.

**Câu 3.** Muốn tạo symbolic link trong Java dùng method gì?  
**Đáp án:** `Files.createSymbolicLink(link, target)`; `target` có thể absolute hoặc relative và chưa cần tồn tại.

**Câu 4.** Nếu đọc `original` và `hard` thấy cùng bytes, đã đủ kết luận là hard links chưa?  
**Đáp án:** Chưa. Một bản copy cũng có thể cùng bytes. Dùng `Files.isSameFile` để kiểm tra file identity khi đối tượng tồn tại.

**Câu 5.** Xóa tên `original` của hard link thì `hard` có còn đọc được không?  
**Đáp án:** Trong mô hình regular hard link thông thường, có, vì `hard` vẫn là directory entry tới file đó.

**Câu 6.** Nếu thay `original` bằng một file mới bằng `Files.move(..., REPLACE_EXISTING)`, `hard` có tự trỏ sang file mới không?  
**Đáp án:** Không. Nó vẫn có thể định vị file object cũ. Xem `HardLinkReplaceDemo`.

**Câu 7.** Symlink có thể tạo trước khi target tồn tại không?  
**Đáp án:** Có. Nó có thể là dangling symlink cho đến khi đường dẫn target hợp lệ.

**Câu 8.** Với `views/latest -> ../shared/report.txt`, target tương đối được tính từ đâu?  
**Đáp án:** Từ directory `views` chứa link, không phải từ cwd lúc chương trình chạy sau này.

**Câu 9.** Vì sao `Files.exists(link)` có thể false dù link entry còn?  
**Đáp án:** Vì mặc định theo symlink; target có thể đã biến mất hoặc không truy cập được. Dùng `exists(link,NOFOLLOW_LINKS)` để hỏi entry khi phù hợp.

**Câu 10.** `Files.readSymbolicLink` có cần target tồn tại không?  
**Đáp án:** Không. Method đọc raw target Path được link lưu, không mở file đích.

**Câu 11.** `Files.isSymbolicLink(hard)` có trả true với hard link tới regular file không?  
**Đáp án:** Không. Hard link không phải symlink; method này chỉ phát hiện symbolic link entry.

**Câu 12.** `Files.isSameFile(link,target)` true có chứng minh link là hard link không?  
**Đáp án:** Không. Một symbolic link hợp lệ được follow cũng có thể định vị cùng target.

**Câu 13.** `Files.delete(symlink)` xóa link hay file đích?  
**Đáp án:** Xóa bản thân symbolic link theo hợp đồng, không xóa final target.

**Câu 14.** Hard link có thể trỏ tới file trên volume khác không?  
**Đáp án:** Thông thường không. Các directory entries của một hard-linked file thường phải nằm trên cùng filesystem.

**Câu 15.** Có thể tạo symbolic link tới directory không?  
**Đáp án:** Có trên nhiều hệ thống, tùy provider, OS và quyền; cần kiểm tra khả năng.

**Câu 16.** Vì sao hard link không nên được dùng làm bản backup độc lập?  
**Đáp án:** Hai tên cùng một đối tượng; ghi/hỏng data qua một tên ảnh hưởng data quan sát qua tên khác.

**Câu 17.** `Files.walkFileTree` có tự theo symbolic links không?  
**Đáp án:** Mặc định không. Khi bật `FOLLOW_LINKS` phải xét vòng lặp và quyền ngoài root.

**Câu 18.** `NOFOLLOW_LINKS` có luôn giải quyết toàn bộ nguy cơ symbolic link escape không?  
**Đáp án:** Không. Cần xem semantics của từng API, ancestor links, quyền và TOCTOU.

**Câu 19.** Có thể xác định số hard links portable bằng `Files.getAttribute(path,"unix:nlink")` không?  
**Đáp án:** Không; `unix` là provider-specific, có thể không khả dụng.

**Câu 20.** Các chương trình symlink biên dịch chạy được nhưng in `SKIPPED` vì thiếu quyền. Có được báo “đã test đúng đường link thật” không?  
**Đáp án:** Không. Phải ghi nhánh symlink chưa được kiểm chứng thực nghiệm và thử tại OS/provider có capability.

### Thực hành A — Sửa nội dung qua một tên

Chạy `HardLinkBasicsDemo`, đổi chuỗi `UPDATED` thành `SECOND` và xác nhận đọc qua tên `original` thấy nội dung mới khi hard link được tạo thành công.

### Thực hành B — Phân biệt hard link và copy

Chạy `HardLinkVsCopyDemo`, thêm một lần sửa nội dung qua `hard`, sau đó đọc `original` và `copy`. Giải thích hai kết quả khác nhau theo file identity.

### Thực hành C — Thay directory entry

Chạy `HardLinkReplaceDemo`. Trước move xác nhận `isSameFile` true, sau move false. Dự đoán kết quả nếu chỉ dùng `Files.writeString(original,"NEW")` thay vì move replacement.

### Thực hành D — Link tương đối

Trên môi trường cho phép tạo symlink, chạy `RelativeSymbolicLinkDemo` rồi đổi vị trí `latest.txt` sang một thư mục khác nhưng **không sửa raw target**. Quan sát điều gì xảy ra với khả năng phân giải target, và giải thích vì sao.

### Thực hành E — Dangling link

Trong `SymbolicLinkBasicsDemo`, sau khi xóa target, thêm `Files.readSymbolicLink(link)` và so sánh kết quả với `Files.exists(link)` và `Files.exists(link,NOFOLLOW_LINKS)`. Không cố đọc String từ broken link mà không xử lý IOException.

### Thực hành F — Attributes

Chạy `LinkAttributesDemo`. Ghi rõ `hardIsSymbolic=false` dù `hardSharesIdentity=true`. Nếu có symlink, quan sát `softIsSymbolic=true` và `softSharesTargetIdentity=true`.

### Thực hành G — Provider support

Chạy các chương trình trên một file store khác nếu có quyền. Ghi rõ kết quả `CREATED/SKIPPED` và lý do lỗi khi thử trong môi trường test, không tự kết luận từ tên OS.

### Thực hành H — Thống kê file trùng danh tính

Tạo một thư mục tạm với hai hard-link names cùng chỉ file 100 byte và một bản copy riêng. So sánh tổng số entry, tổng `Files.size` của entries, số file objects unique theo `Files.isSameFile` và kích thước unique khi không có thay đổi đồng thời.

### Thực hành I — Symlink và an toàn path

Dựng một cây temp với symlink từ thư mục trong root sang một thư mục khác, nếu hệ thống cho phép. So sánh lexical `startsWith(base)` với `toRealPath().startsWith(realBase)`. Ghi rõ kiểm tra real path vẫn không tự chống tất cả TOCTOU races.

### Thực hành J — Chính sách fallback

Thiết kế hàm tạo hard link “nếu supported” nhưng **không tự thay bằng symbolic link/copy** khi hợp đồng bắt buộc file identity. Trả outcome tường minh `CREATED`, `UNSUPPORTED` hoặc `FAILED` theo exception đã phân loại.

## 26. Tài liệu Java chính thức

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createLink`, `createSymbolicLink`, `readSymbolicLink`, `isSymbolicLink`, `isSameFile`, `exists`, `delete`, `copy`, `move` và exception semantics.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `relativize`, `normalize`, `toRealPath` và cấu trúc đường dẫn.
- [Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` và những API có hỗ trợ option này.
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `isSymbolicLink`, `isRegularFile` và `fileKey`.
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` trong traversal.
- [Java SE 17 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemLoopException.html): báo vòng lặp khi giải links.
- [Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): đặc tính file store liên quan đến portability.
- [Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING` và các option file operations.
- [Dev.java — File System API](https://dev.java/learn/api/io/java-io/file-system/): tài liệu học Java hiện đại về filesystem và NIO.2.

**Kết luận:** Hard link là **một tên khác của cùng file**, còn symbolic link là **một entry tham chiếu đường dẫn đến target**. Chúng khác nhau khi xóa, rename, thay thế một directory entry, theo liên kết, cross-filesystem, backup và bảo mật. Trong Java dùng `Files.createLink` cho hard link; `createSymbolicLink`/`readSymbolicLink` cho symlink; `Files.isSameFile` để hỏi identity; `NOFOLLOW_LINKS` để xem bản thân link khi cần. Luôn xét provider/OS/quyền, phân biệt output `SKIPPED` với test thật, và không biến alias thành giả định về sao lưu độc lập hay authorization.

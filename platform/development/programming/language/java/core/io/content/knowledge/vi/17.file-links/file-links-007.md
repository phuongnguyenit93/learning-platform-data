# Copy, move, delete tác động vào symbolic link hay tệp đích?

> **Phạm vi:** Java Core I/O, API `java.nio.file` (Java 17+). Bài học tập trung vào **symbolic link (liên kết tượng trưng)**, đồng thời phân biệt với **hard link (liên kết cứng)** để tránh suy luận sai khi sao chép, di chuyển và xóa tệp.

## 1. Hiểu đúng “link” và “đích”

Giả sử có cấu trúc:

~~~text
work/
├── report.txt            # Tệp thật, nội dung: hello
└── shortcut.txt          # Symbolic link -> report.txt
~~~

`report.txt` là **đối tượng đích** (target/referent); `shortcut.txt` là **một đối tượng hệ thống tệp riêng** chứa đường dẫn tham chiếu đến đích. Khi chương trình truy cập `shortcut.txt`, hệ thống tệp có thể đi theo liên kết để đọc dữ liệu từ `report.txt`. Nhưng không phải API nào cũng đi theo liên kết.

Cần phân biệt ba vai trò:

- **Source (đường dẫn nguồn):** tham số đầu tiên của `Files.copy(source, destination)` hoặc `Files.move(source, destination)`. Nó có thể là đường dẫn đến chính symbolic link.
- **Destination (đường dẫn nhận):** nơi đặt bản sao hoặc nơi chuyển tới; tại đó cũng có thể đã tồn tại một symbolic link khác.
- **Referent/target của link:** tệp hoặc thư mục được một symbolic link trỏ đến; khác với tham số tên là `target` trong `Files.copy`/`Files.move`.

Ví dụ: `Files.copy(shortcut, backup)` có **source là shortcut** và **destination là backup**, nhưng dữ liệu thực được đọc mặc định lại từ **report.txt**. Vì vậy câu hỏi “thao tác vào link hay đích?” phải xét cả **loại thao tác**, **vị trí link (nguồn/đích)** và **tùy chọn API**.

### Symbolic link và hard link khác nhau thế nào?

- **Symbolic link:** có nội dung tham chiếu là một đường dẫn; có thể trỏ đến thư mục hoặc tệp, có thể bị *dangling/broken* khi đích mất hoặc đường dẫn không còn hợp lệ. Có thể kiểm tra bằng `Files.isSymbolicLink(path)` và đọc đường dẫn tham chiếu bằng `Files.readSymbolicLink(path)`.
- **Hard link:** hai tên đường dẫn cùng tham chiếu đến **một đối tượng tệp** trên hệ thống tệp. Không tồn tại một “tệp shortcut chứa đường dẫn đích” để đi theo như symbolic link. Sửa nội dung qua tên nào cũng là sửa nội dung chung; xóa một tên không tự động xóa tên còn lại. Java có `Files.createLink(newLink, existingFile)` nếu hệ thống tệp hỗ trợ.
- **Giới hạn:** hard link thường không được tạo cho thư mục và không vượt qua các file store; tính khả dụng tùy hệ điều hành và hệ thống tệp. Những ví dụ chính dưới đây sử dụng symbolic link.

## 2. Bảng quy tắc cần nhớ

Bảng này giả sử thao tác trên `Path` trực tiếp, hệ thống tệp hỗ trợ symbolic link, và không có lỗi quyền hoặc I/O.

| Thao tác | Khi **source/path là symbolic link** | Tệp/thư mục mà link trỏ tới |
|---|---|---|
| `Files.copy(link, newPath)` | **Mặc định đi theo link**, sao chép dữ liệu/đối tượng đích sang `newPath`; bản mới thường là tệp/thư mục thường | Không bị sửa/xóa |
| `Files.copy(link, newPath, LinkOption.NOFOLLOW_LINKS)` | Sao chép **chính symbolic link** sang tên mới (giữ tham chiếu dạng đường dẫn) | Không bị sửa/xóa |
| `Files.move(link, newPath)` | Di chuyển/đổi tên **chính link** | Không bị di chuyển |
| `Files.delete(link)` | Xóa **chính link** | Không bị xóa |
| `Files.deleteIfExists(link)` | Xóa **chính link** nếu tồn tại | Không bị xóa |
| `Files.readString(link)` hoặc `Files.newInputStream(link)` | Thông thường đi theo link để đọc nội dung | Được đọc qua link |
| `Files.isSymbolicLink(link)` | Kiểm tra chính đối tượng link | Không cần đi theo đến đích |

**Mẹo ghi nhớ:** *copy* mặc định lấy **nội dung đích**; *move* và *delete* tác động lên **bản thân symbolic link**. `NOFOLLOW_LINKS` thay đổi cách **copy nguồn**, không phải là tùy chọn bắt buộc khi move/delete.

Lưu ý rằng `Files.copy` **không tự sao chép đệ quy** một thư mục: với source là thư mục, mặc định chỉ tạo thư mục mới rỗng. Nếu source là link trỏ đến thư mục, việc copy mặc định theo link cũng không đồng nghĩa sao chép toàn bộ cây thư mục.

## 3. Sao chép: tách riêng symbolic link nguồn và link ở đường dẫn nhận

### 3.1. Nguồn là symbolic link

~~~java
Path link = Path.of("work/shortcut.txt");
Path contentCopy = Path.of("work/content-copy.txt");
Path linkCopy = Path.of("work/link-copy.txt");

Files.copy(link, contentCopy);                        // Đi theo link nguồn
Files.copy(link, linkCopy, LinkOption.NOFOLLOW_LINKS); // Copy chính link nguồn
~~~

Đây là **đoạn minh họa**, giả sử `work/shortcut.txt` đã là symbolic link hợp lệ và hai đường dẫn đích chưa tồn tại; mã hoàn chỉnh có thể chạy nằm ở mục 6.

Sau lệnh thứ nhất, `content-copy.txt` có **dữ liệu độc lập** với `report.txt`. Nếu sửa `report.txt` sau đó, bản copy không tự đổi theo. Sau lệnh thứ hai, `link-copy.txt` là một **symbolic link khác**. Khi `report.txt` đổi nội dung, đọc qua `link-copy.txt` sẽ thấy nội dung mới, miễn liên kết còn trỏ đúng đích.

**Đường dẫn tương đối có thể làm bản link sao chép bị hỏng:** nếu `shortcut.txt -> report.txt` thì chuỗi tham chiếu bên trong là `report.txt`, được phân giải **tương đối với thư mục chứa link**. Copy link sang thư mục khác bằng `NOFOLLOW_LINKS` giữ nguyên tham chiếu đó; nó có thể trỏ đến tệp khác hoặc trở thành dangling link. Java không tự chuyển một đường dẫn tương đối thành đường dẫn tuyệt đối để duy trì ý nghĩa ban đầu.

Nếu source là một **dangling symbolic link**, `Files.copy(link, newPath)` theo mặc định thường thất bại khi không mở được đích; `Files.copy(link, newPath, NOFOLLOW_LINKS)` có thể sao chép chính đường dẫn liên kết dù đích không tồn tại (nếu provider cho phép tạo link).

### 3.2. Đường dẫn nhận đã là symbolic link

Đừng nhầm hành vi của **link nguồn** với **link nằm ở destination**:

~~~text
work/
├── important.txt          # Đích của existing-link.txt
└── existing-link.txt -> important.txt
~~~

- `Files.copy(source, existingLink)` **không có** `REPLACE_EXISTING`: thất bại vì đường dẫn nhận đã có một symbolic link.
- `Files.copy(source, existingLink, StandardCopyOption.REPLACE_EXISTING)`: **thay thế entry symbolic link** mang tên `existing-link.txt` bằng bản copy. Tệp `important.txt` mà link cũ trỏ đến **không bị ghi đè qua link**.
- Nếu `source` cũng là symbolic link, cách lấy nội dung nguồn vẫn theo quy tắc riêng: mặc định theo link; có `NOFOLLOW_LINKS` thì copy bản thân link. `REPLACE_EXISTING` không có nghĩa là “không theo link nguồn”.
- Nếu destination là **thư mục không rỗng**, `REPLACE_EXISTING` không cho phép thay thế tùy tiện; thao tác có thể báo `DirectoryNotEmptyException`.

`COPY_ATTRIBUTES` yêu cầu cố gắng sao chép thuộc tính được hỗ trợ (ví dụ thời gian sửa đổi). Khi copy **chính symbolic link** với `NOFOLLOW_LINKS`, khả năng sao chép thuộc tính của link phụ thuộc provider, và `COPY_ATTRIBUTES` có thể bị bỏ qua.

## 4. Di chuyển/đổi tên: di chuyển link, không dời referent

~~~java
Path link = Path.of("work/shortcut.txt");       // -> report.txt
Path renamed = Path.of("work/renamed-link.txt");

Files.move(link, renamed);                       // Đổi tên entry symbolic link
~~~

Kết quả: `shortcut.txt` không còn; `renamed-link.txt` vẫn là symbolic link; `report.txt` vẫn ở nguyên vị trí. Nếu `renamed-link.txt` là link tương đối và vẫn nằm trong cùng thư mục, nó thường tiếp tục trỏ đúng `report.txt`.

Nếu chuyển link từ `work/shortcut.txt -> report.txt` sang `archive/shortcut.txt`, đường dẫn tham chiếu `report.txt` được diễn giải trong thư mục `archive`. **Link sau move có thể bị broken**, mặc dù `report.txt` trong `work` vẫn tồn tại. Cần tự quyết định có tạo lại link với đích phù hợp hay không.

Khi đường dẫn nhận đã tồn tại:

- Mặc định `Files.move(source, destination)` thường thất bại nếu destination đã tồn tại.
- Với `StandardCopyOption.REPLACE_EXISTING`, nếu destination là symbolic link, **chính destination link bị thay thế**, không phải referent của nó. Không thể thay thế tùy tiện một thư mục không rỗng.
- Với `StandardCopyOption.ATOMIC_MOVE`, yêu cầu thao tác nguyên tử; nếu không hỗ trợ sẽ ném `AtomicMoveNotSupportedException`. Khi sử dụng tùy chọn này, các tùy chọn khác bị bỏ qua, và hành vi khi destination đã tồn tại phụ thuộc triển khai. Không mặc định cho rằng có thể move nguyên tử qua file store khác.

**Move bản thân tệp đích khác hoàn toàn với move link.** Nếu di chuyển `report.txt` sang tên khác mà không điều chỉnh tham chiếu `shortcut.txt -> report.txt`, link cũ có thể bị broken. Đó là kết quả của việc đổi vị trí referent, không phải thao tác `Files.move(link, ...)`.

## 5. Xóa: delete link không xóa đích

~~~java
Path link = Path.of("work/shortcut.txt");
Files.delete(link);                     // Xóa shortcut.txt
// report.txt vẫn còn nếu trước đó tồn tại.
~~~

- `Files.delete(link)` xóa entry của symbolic link ngay cả khi link trỏ đến thư mục **có dữ liệu**. Nó không đi vào thư mục đích để xóa các tệp bên trong.
- `Files.deleteIfExists(link)` tương tự, nhưng trả về `false` khi bản thân entry không tồn tại; `Files.delete(link)` có thể ném `NoSuchFileException` trong trường hợp đó.
- Nếu xóa **chính đường dẫn tệp thật** `Files.delete(targetPath)`, tệp thật bị xóa. Những symbolic link còn trỏ tới đường dẫn đó sẽ thành dangling link (trừ khi xuất hiện đối tượng khác tại đường dẫn này).
- Nếu mục tiêu của chương trình là xóa cả cây thư mục, `Files.delete(dir)` chỉ xóa được thư mục rỗng. Cần duyệt cây một cách có kiểm soát, thường bằng `Files.walkFileTree`, và xác định rõ chính sách theo link.

**Cẩn trọng với thao tác “xóa đích của link”:** `Files.delete(link)` *không* thực hiện việc này. Nếu thật sự muốn xóa referent, phải **chủ động xác định** đường dẫn đích (ví dụ `link.toRealPath()` khi đích tồn tại) rồi xóa đường dẫn đó. Việc phân giải và xóa là hai thao tác riêng, nên trong môi trường có thay đổi đồng thời vẫn phải cân nhắc race condition và quyền truy cập. Tuyệt đối không dùng một cách mù quáng cho đầu vào không tin cậy.

## 6. Chương trình Java 17+ chạy được

Chương trình tạo một thư mục tạm, một tệp thật và một **symbolic link tương đối**, sau đó chứng minh riêng từng thao tác. Nó dọn những entry do chính chương trình tạo trong khối `finally`.

Lưu tệp là **`SymbolicLinkOperationsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymbolicLinkOperationsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symlink-ops-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("alias.txt");
        Path contentCopy = dir.resolve("content-copy.txt");
        Path linkCopy = dir.resolve("link-copy.txt");
        Path movedLink = dir.resolve("moved-alias.txt");

        try {
            Files.writeString(target, "hello");
            // data.txt được phân giải tương đối với thư mục chứa alias.txt.
            Files.createSymbolicLink(link, Path.of("data.txt"));

            Files.copy(link, contentCopy);
            Files.copy(link, linkCopy, LinkOption.NOFOLLOW_LINKS);
            System.out.println("copy default: file="
                    + Files.isRegularFile(contentCopy)
                    + ", data=" + Files.readString(contentCopy));
            System.out.println("copy nofollow: link="
                    + Files.isSymbolicLink(linkCopy)
                    + ", points=" + Files.readSymbolicLink(linkCopy));

            Files.move(link, movedLink);
            System.out.println("move: oldLinkExists="
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS)
                    + ", newLink=" + Files.isSymbolicLink(movedLink)
                    + ", targetExists=" + Files.exists(target));

            Files.delete(movedLink);
            System.out.println("delete: movedLinkExists="
                    + Files.exists(movedLink, LinkOption.NOFOLLOW_LINKS)
                    + ", targetExists=" + Files.exists(target));
        } finally {
            Files.deleteIfExists(movedLink);
            Files.deleteIfExists(link);
            Files.deleteIfExists(linkCopy);
            Files.deleteIfExists(contentCopy);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa source:

~~~bash
javac SymbolicLinkOperationsDemo.java
java SymbolicLinkOperationsDemo
~~~

**Stdout khi hệ thống hỗ trợ tạo symbolic link và các thao tác thành công:**

~~~text
copy default: file=true, data=hello
copy nofollow: link=true, points=data.txt
move: oldLinkExists=false, newLink=true, targetExists=true
delete: movedLinkExists=false, targetExists=true
~~~

Giải thích từng dòng:

1. Copy mặc định cho ra **regular file** chứa `hello`, bởi Java đã theo `alias.txt` đến `data.txt`.
2. Copy với `NOFOLLOW_LINKS` cho ra **một symbolic link mới**, còn ghi nhận tham chiếu tương đối `data.txt`.
3. Move làm biến mất tên link cũ, tạo tên link mới, trong khi tệp `data.txt` không chuyển.
4. Delete xóa tên link vừa move; `data.txt` vẫn còn.

**Tính khả chuyển:** trên một số máy Windows, tạo symbolic link có thể cần quyền/Developer Mode; một số file system không hỗ trợ symbolic link. Khi đó `Files.createSymbolicLink` có thể ném `UnsupportedOperationException`, `IOException` hoặc lỗi quyền; chương trình không cho ra đúng stdout trên. Chạy trên hệ thống/tài khoản cho phép symbolic link để quan sát đủ thí nghiệm. Chương trình có thể cần đóng các chương trình đang giữ tệp trên hệ điều hành có hạn chế xóa tệp đang mở.

## 7. Trường hợp riêng: hard link

Giả sử tạo:

~~~java
Path original = Path.of("work/report.txt");
Path hardLink = Path.of("work/also-report.txt");
Files.createLink(hardLink, original);  // Hai tên cùng trỏ tới một đối tượng tệp
~~~

Đây là đoạn minh họa, yêu cầu `original` tồn tại và provider hỗ trợ hard link.

- **Copy:** `Files.copy(hardLink, anotherPath)` bình thường tạo **bản sao dữ liệu tệp độc lập**, không tự tạo thêm một hard link. Muốn tạo thêm hard link, dùng `Files.createLink(...)`.
- **Move:** `Files.move(hardLink, newPath)` đổi vị trí/tên entry `hardLink`; tên `original` vẫn truy cập được dữ liệu chung.
- **Delete:** `Files.delete(hardLink)` xóa **một tên**; `original` vẫn truy cập được. Trên hệ thống tệp kiểu Unix, dữ liệu thường chỉ được giải phóng khi không còn hard link (và không còn handle mở giữ đối tượng tệp), nhưng chi tiết phụ thuộc hệ thống tệp/hệ điều hành.
- **Nhận diện:** `Files.isSymbolicLink(hardLink)` trả về `false` vì hard link không phải symbolic link. Khi được hỗ trợ và cả hai tồn tại, `Files.isSameFile(original, hardLink)` có thể xác nhận hai đường dẫn chỉ cùng một đối tượng tệp.

Không nhầm `Files.createLink` với `Files.createSymbolicLink`: chúng biểu diễn hai quan hệ hoàn toàn khác nhau.

## 8. Broken link, duyệt cây và các lỗi dễ mắc

### 8.1. `exists` mặc định thường theo link

Nếu `alias.txt -> missing.txt` và `missing.txt` không tồn tại:

~~~java
Files.isSymbolicLink(link);                         // true
Files.exists(link);                                 // false: đích không có
Files.exists(link, LinkOption.NOFOLLOW_LINKS);      // true: entry link còn
Files.readSymbolicLink(link);                       // trả về đường dẫn tham chiếu
Files.deleteIfExists(link);                         // xóa link dangling
~~~

Đây là đoạn minh họa, giả định `link` là dangling symbolic link. Vì vậy, **đừng dùng duy nhất `Files.exists(link)` để quyết định link có cần xóa hay không**. Kết quả `exists` còn có thể bị ảnh hưởng bởi thiếu quyền hoặc lỗi I/O, nên khi cần biết nguyên nhân chính xác hãy dùng API ném ngoại lệ thích hợp.

### 8.2. Duyệt thư mục để copy/delete đệ quy

- `Files.walkFileTree(root, visitor)` **mặc định không đi theo symbolic link**. Khi gặp link, visitor thường xử lý bản thân entry; nếu xóa entry này, referent ở ngoài/ở trong cây không bị xóa qua link.
- Bật `FileVisitOption.FOLLOW_LINKS` nghĩa là cho phép đi theo symbolic link khi duyệt; điều này có thể đưa chương trình vào thư mục ngoài phạm vi mong muốn, hoặc gặp chu trình liên kết và `FileSystemLoopException`. Phải xác định rõ ranh giới và xử lý lỗi, nhất là với đường dẫn do người dùng cung cấp.
- `Files.walk(root)` cũng không đi theo symbolic link theo mặc định; chỉ đi theo khi cấp `FOLLOW_LINKS`. Không coi thao tác duyệt + xóa là nguyên tử; nội dung thư mục có thể đổi giữa lúc kiểm tra và lúc thực hiện.

### 8.3. Những sai lầm cần tránh

| Ngộ nhận | Thực tế |
|---|---|
| “`Files.copy(link, x)` luôn tạo một link mới” | Mặc định sao chép **referent**; muốn sao chép link phải chỉ định `NOFOLLOW_LINKS`. |
| “`NOFOLLOW_LINKS` là tùy chọn dành cho `move`/`delete`” | Hai thao tác này **vốn đã tác động lên symbolic link** khi đường dẫn đầu vào là link. |
| “`REPLACE_EXISTING` ghi đè tệp mà destination link trỏ đến” | Nó thay **entry destination link**, không ghi đè referent của link ấy. |
| “Move link sang thư mục khác vẫn luôn hoạt động như cũ” | Link tương đối có thể trỏ sai sau khi đổi thư mục chứa. |
| “Xóa link đến một thư mục sẽ xóa cây thư mục đích” | `Files.delete(link)` chỉ xóa link; cây thư mục thật còn nguyên. |
| “`Files.exists(link) == false` chắc chắn không có entry link” | Dangling symbolic link có thể vẫn tồn tại; dùng `NOFOLLOW_LINKS` khi cần kiểm tra entry. |
| “Hard link giống file shortcut” | Hard link là tên bổ sung của cùng một đối tượng tệp, không phải một đối tượng chứa chuỗi đường dẫn đích. |

## 9. Cách chọn thao tác cho đúng yêu cầu

1. **Muốn một bản dữ liệu độc lập:** `Files.copy(link, copy)` nếu muốn theo referent, và đảm bảo đó là đúng hành vi cần thiết.
2. **Muốn nhân bản một symbolic link:** `Files.copy(link, newLink, LinkOption.NOFOLLOW_LINKS)`; sau đó xác minh `Files.readSymbolicLink(newLink)` và đường dẫn tương đối.
3. **Muốn đổi tên hoặc chuyển nơi chứa shortcut:** `Files.move(link, destination)`; kiểm tra lại referent nếu chuyển thư mục.
4. **Muốn gỡ shortcut mà giữ tệp gốc:** `Files.delete(link)` hoặc `Files.deleteIfExists(link)`.
5. **Muốn xóa tệp gốc:** chỉ định đúng **đường dẫn của tệp gốc** sau khi xác minh quyền, phạm vi và danh tính đích; chấp nhận rằng các symbolic link trỏ đến nó có thể bị dangling.
6. **Muốn xóa/copy toàn cây thư mục:** thiết kế một lượt duyệt rõ ràng và chỉ bật `FOLLOW_LINKS` nếu thật sự cần, với biện pháp tránh chu trình và vượt phạm vi.

**Câu hỏi tự kiểm tra:**

- `alias -> data.txt`. Sau `Files.copy(alias, snapshot)` rồi sửa `data.txt`, `snapshot` có đổi theo không? **Không**: bản copy mặc định là dữ liệu độc lập.
- Sau `Files.copy(alias, alias2, NOFOLLOW_LINKS)` rồi sửa `data.txt`, đọc qua `alias2` có thể thấy gì? **Nội dung mới của data.txt**, nếu `alias2` còn trỏ đúng.
- Sau `Files.move(alias, archive/alias)`, `data.txt` có tự đi vào `archive` không? **Không**. Tham chiếu tương đối của link có thể bị broken.
- Sau `Files.delete(alias)`, `data.txt` có bị xóa không? **Không**.
- `destination` đang là symbolic link trỏ tới tệp quan trọng. `Files.copy(source, destination, REPLACE_EXISTING)` tác động đến cái gì? **Thay entry link tại destination**; không theo destination link để ghi đè tệp quan trọng.

### Tài liệu tham khảo

- [Java SE 17 — `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đặc tả `copy`, `move`, `delete`, `createLink`, `createSymbolicLink`, `walkFileTree`.
- [Dev.java — Manipulating Files and Directories](https://dev.java/learn/api/io/java-io/file-system/move-copy-delete/): thao tác sao chép, di chuyển và xóa tệp/thư mục.
- [Java SE 17 — `LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): ý nghĩa không theo symbolic link.

# Symbolic link và hard link trong Java NIO.2

## 1. Mục tiêu

Trong hệ thống tệp, **tên/đường dẫn của tệp** và **đối tượng dữ liệu được tên đó tham chiếu** là hai khái niệm cần phân biệt. Symbolic link và hard link cho phép nhiều đường dẫn liên hệ với một tệp, nhưng chúng làm điều đó theo hai cơ chế khác nhau:

- **Hard link (liên kết cứng)**: thêm một tên mới cho **cùng một đối tượng tệp**. Hai tên cùng dùng dữ liệu và metadata của đối tượng đó.
- **Symbolic link (symlink, liên kết tượng trưng)**: một đối tượng liên kết lưu **đường dẫn của mục tiêu**. Khi truy cập có theo liên kết, hệ điều hành/filesystem giải quyết đường dẫn này để tìm mục tiêu.

Java hỗ trợ các thao tác này qua `java.nio.file.Path`, `Files` và `LinkOption`. API xuất hiện từ Java 7; các ví dụ dùng Java 17+. Khả năng tạo liên kết thực tế còn phụ thuộc hệ điều hành, hệ thống tệp và quyền.

```text
Hard link:
  data.txt -----------+
                      +---- [cùng một đối tượng tệp, cùng dữ liệu]
  alias-hard.txt -----+

Symbolic link:
  alias-symbolic.txt --(chứa đường dẫn "data.txt")--> data.txt --> [đối tượng tệp]
```

Symlink không đồng nghĩa với tệp shortcut `.lnk` của Windows: đây là một cơ chế giải quyết đường dẫn của filesystem.

## 2. So sánh

| Tiêu chí | Hard link | Symbolic link |
|---|---|---|
| Bản chất | Một tên khác của cùng đối tượng tệp | Một đối tượng link chứa đường dẫn mục tiêu |
| Mục tiêu phải tồn tại khi tạo? | Có | Không nhất thiết; có thể tạo link bị đứt |
| Khi xóa tên mục tiêu ban đầu | Hard link khác vẫn truy cập được nội dung | Symlink có thể bị đứt vì tên mục tiêu biến mất |
| Khi ghi/sửa nội dung tệp tại chỗ | Mọi hard link thấy cùng nội dung mới | Symlink thấy nội dung mới nếu vẫn giải quyết tới tệp đó |
| Khi thay **đối tượng tệp** tại tên mục tiêu | Hard link cũ vẫn chỉ tới đối tượng cũ | Symlink thường theo tên tới đối tượng mới |
| Qua filesystem/volume khác | Thường không | Có thể nếu nền tảng hỗ trợ |
| Liên kết thư mục | Thường không cho phép tạo hard link thư mục | Thường có hỗ trợ, phụ thuộc quyền/hệ thống |
| Java tạo | `Files.createLink` | `Files.createSymbolicLink` |
| Java quan sát | `Files.isSameFile` kiểm tra hai path cùng tệp | `Files.isSymbolicLink` kiểm tra mục nhập link |

Trên Unix, mô hình thường được mô tả bằng **inode**: hai hard link cùng tham chiếu một inode. Đây là cách hiểu hữu ích, nhưng Java NIO.2 không bắt buộc mọi filesystem dùng inode. Khi đã tạo hard link, “tên gốc” và “tên mới” là **hai tên ngang hàng**.

## 3. Hard link: tên khác, cùng đối tượng tệp

Giả sử có `a.txt` và tạo `b.txt` là hard link tới `a.txt`:

1. Filesystem tạo mục nhập tên `b.txt` trỏ tới **cùng đối tượng** mà `a.txt` đang tham chiếu; không copy toàn bộ dữ liệu.
2. Đọc `a.txt` hoặc `b.txt` đều thấy nội dung như nhau. Nếu ghi nội dung mới **vào cùng đối tượng** thông qua một tên, nội dung đọc qua tên còn lại cũng thay đổi.
3. Xóa `a.txt` chỉ bỏ tên đó. `b.txt` vẫn tham chiếu đối tượng tệp và đọc được dữ liệu.
4. Trên filesystem kiểu POSIX, đối tượng thường được thu hồi khi không còn tên liên kết cứng và không còn handle đang mở giữ nó; chi tiết phụ thuộc hệ thống.

**Phân biệt sửa nội dung với thay tệp:** một chương trình có thể tạo tệp tạm rồi dùng `Files.move(temp, a, REPLACE_EXISTING)` để thay **đối tượng được tên `a.txt` trỏ tới**. Khi đó `b.txt` vẫn có thể tham chiếu đối tượng cũ. Vì vậy hard link **không** phải cách sao lưu độc lập hoặc đồng bộ mọi kiểu cập nhật tệp.

### API tạo hard link

```java
Path existing = Path.of("data.txt");
Path alias = Path.of("data-hard.txt");

Files.createLink(alias, existing);
boolean sameObject = Files.isSameFile(existing, alias);
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. Giả định `data.txt` đã tồn tại, `data-hard.txt` chưa tồn tại, hai tên nằm trên cùng filesystem và filesystem cho phép hard link. Khi tạo thành công, `sameObject` là `true`. Phương thức `Files.isSameFile` kiểm tra hai đường dẫn cùng giải quyết tới một tệp, **không chuyên dùng để phát hiện hard link**: một symlink theo tới cùng tệp cũng có thể cho kết quả `true`.

## 4. Symbolic link: một đường dẫn tham chiếu đường dẫn khác

Symlink chứa một đường dẫn mục tiêu. Đường dẫn này có thể **tuyệt đối** hoặc **tương đối**.

```java
Path link = Path.of("logs", "current.log");
Path target = Path.of("2026-10.log");

Files.createSymbolicLink(link, target);
Path storedTarget = Files.readSymbolicLink(link);
```

Đoạn trên giả định thư mục `logs` tồn tại và hệ thống cho phép tạo symlink. Với target tương đối, `2026-10.log` được giải quyết **từ thư mục chứa symlink**, ở đây là `logs`, chứ không phải từ working directory khi chương trình truy cập. `readSymbolicLink` trả chính path lưu trong link (ở ví dụ là `2026-10.log`), không tự biến nó thành absolute/canonical path.

Symlink thường có thể trỏ tới **tệp** hoặc **thư mục**. Các thao tác đọc nội dung như `Files.readString(link)` theo symlink tới mục tiêu. Nếu đường dẫn mục tiêu không còn giải quyết được (bị xóa, đổi tên, di chuyển sai quan hệ thư mục), symlink trở thành **dangling/broken symlink**: liên kết vẫn là một mục nhập filesystem nhưng không đọc được mục tiêu.

Đường dẫn tương đối thuận tiện khi cần di chuyển cả cây thư mục mà vẫn giữ mối quan hệ giữa link và target. Đường dẫn tuyệt đối dễ hiểu tại một vị trí cố định, nhưng có thể đứt khi di chuyển dự án sang thư mục/máy khác.

### Phân biệt symlink tồn tại và mục tiêu tồn tại

```java
Files.isSymbolicLink(link);                    // Kiểm tra bản thân link
Files.exists(link);                            // Mặc định theo link tới mục tiêu
Files.exists(link, LinkOption.NOFOLLOW_LINKS); // Không theo link
Files.readSymbolicLink(link);                  // Lấy target path đã lưu
```

Với một symlink bị đứt, `Files.exists(link)` thường trả `false` nhưng `Files.exists(link, NOFOLLOW_LINKS)` trả `true`. Tuy nhiên `Files.exists` cũng có thể trả `false` khi không xác định được sự tồn tại do vấn đề truy cập; đây không phải phép kiểm tra đảm bảo thao tác I/O sau đó sẽ thành công.

## 5. Chương trình Java 17+ chạy được

Chương trình sau tạo thư mục tạm, ghi tệp, tạo hard link, thử tạo symlink rồi xóa một tên tệp. Nó minh họa sự khác biệt giữa **dữ liệu còn được hard link tham chiếu** và **mục tiêu của symlink đã biến mất**.

Lưu đúng tên tệp `FileLinksDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class FileLinksDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("file-links-");
        Path original = folder.resolve("original.txt");
        Path hard = folder.resolve("alias-hard.txt");
        Path symbolic = folder.resolve("alias-symbolic.txt");

        try {
            Files.writeString(original, "v1", StandardCharsets.UTF_8);
            Files.createLink(hard, original);
            System.out.println("Cùng tệp: "
                    + Files.isSameFile(original, hard));

            Files.writeString(hard, "v2", StandardCharsets.UTF_8);
            System.out.println("Đọc tên gốc: "
                    + Files.readString(original, StandardCharsets.UTF_8));

            boolean symbolicCreated = false;
            try {
                // Target tương đối: tính từ thư mục chứa symlink.
                Files.createSymbolicLink(symbolic, Path.of("original.txt"));
                symbolicCreated = true;
                System.out.println("Là symlink: "
                        + Files.isSymbolicLink(symbolic));
                System.out.println("Path lưu trong symlink: "
                        + Files.readSymbolicLink(symbolic));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("Không tạo được symbolic link trên hệ thống này.");
            }

            // Xóa tên original.txt, không xóa đối tượng mà hard link giữ.
            Files.delete(original);
            System.out.println("Đọc qua hard link: "
                    + Files.readString(hard, StandardCharsets.UTF_8));

            if (symbolicCreated) {
                System.out.println("Mục nhập symlink còn: "
                        + Files.exists(symbolic, LinkOption.NOFOLLOW_LINKS));
                System.out.println("Mục tiêu symlink còn: "
                        + Files.exists(symbolic));
            }
        } finally {
            Files.deleteIfExists(symbolic);
            Files.deleteIfExists(hard);
            Files.deleteIfExists(original);
            Files.deleteIfExists(folder);
        }
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac FileLinksDemo.java
java FileLinksDemo
```

Nếu filesystem cho phép tạo hard link và symbolic link, stdout là:

```text
Cùng tệp: true
Đọc tên gốc: v2
Là symlink: true
Path lưu trong symlink: original.txt
Đọc qua hard link: v2
Mục nhập symlink còn: true
Mục tiêu symlink còn: false
```

Giải thích theo thứ tự:

- `Files.createLink` không nhân bản dữ liệu; `isSameFile` xác nhận hai tên giải quyết tới cùng tệp.
- Ghi `"v2"` qua `alias-hard.txt` làm thay đổi nội dung nhìn thấy qua `original.txt`.
- Symlink lưu path tương đối `original.txt`; `readSymbolicLink` cho ra đúng path này.
- Xóa `original.txt` chỉ xóa tên đó, nên `alias-hard.txt` vẫn đọc được `v2`.
- Symlink vẫn tồn tại như một mục nhập, nhưng target `original.txt` không còn, nên kiểm tra theo link thất bại.

Nếu không được phép tạo symbolic link, chương trình in dòng `Không tạo được symbolic link trên hệ thống này.` thay cho ba dòng thông tin lúc tạo symlink và hai dòng kiểm tra symlink cuối. Nếu `Files.createLink` không được hỗ trợ hoặc thiếu quyền, chương trình ném ngoại lệ trước phần symlink; điều đó cho thấy điều kiện môi trường phải được xử lý trong ứng dụng thực. Ví dụ dùng một thư mục tạm chung để tránh lỗi hard link qua nhiều filesystem.

## 6. Bảng API quan trọng

| API | Công dụng | Điểm cần nhớ |
|---|---|---|
| `Files.createLink(link, existing)` | Tạo hard link | `existing` cần tồn tại; link mới chưa tồn tại; thường cùng filesystem |
| `Files.createSymbolicLink(link, target)` | Tạo symlink lưu `target` | `target` có thể chưa tồn tại, nhưng hệ thống phải hỗ trợ |
| `Files.readSymbolicLink(link)` | Đọc path nằm trong symlink | Trả path được lưu, không tự giải quyết thành absolute path |
| `Files.isSymbolicLink(path)` | Kiểm tra mục nhập là symlink | Không đòi hỏi target còn tồn tại |
| `Files.isSameFile(a, b)` | Kiểm tra hai đường dẫn chỉ cùng tệp | Theo symlink khi giải quyết; có thể ném `IOException` |
| `Files.exists(path, NOFOLLOW_LINKS)` | Kiểm tra mục nhập không theo symlink | Hữu ích với dangling symlink |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Đọc thuộc tính của bản thân symlink | Có thể xem `isSymbolicLink()` |
| `path.toRealPath()` | Đường dẫn thực, mặc định theo symlink | Yêu cầu giải quyết được đường dẫn, có thể lỗi I/O |
| `path.toRealPath(NOFOLLOW_LINKS)` | Đường dẫn thực không theo symlink | Khác `toAbsolutePath()`, vốn chủ yếu biến đổi cú pháp |

`NOFOLLOW_LINKS` ở đây là `LinkOption.NOFOLLOW_LINKS`. Muốn dùng `BasicFileAttributes`, import `java.nio.file.attribute.BasicFileAttributes`.

### Đọc metadata của bản thân link

```java
Path link = Path.of("alias-symbolic.txt");

// Mặc định theo symlink: thuộc tính của mục tiêu.
var targetInfo = Files.readAttributes(
        link, java.nio.file.attribute.BasicFileAttributes.class);

// Không theo symlink: thuộc tính của chính mục nhập symlink.
var linkInfo = Files.readAttributes(
        link, java.nio.file.attribute.BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa và cần link tồn tại trong môi trường chạy. Nếu mục tiêu đã biến mất, lời gọi đọc `targetInfo` có thể ném `NoSuchFileException`, còn lời gọi đọc `linkInfo` vẫn có thể thành công. Metadata cụ thể thay đổi theo filesystem/provider.

## 7. Copy, move, delete và duyệt cây thư mục

**Delete:** `Files.delete(symbolic)` xóa **mục nhập symlink**, không xóa mục tiêu được trỏ đến; `deleteIfExists` có cùng nguyên tắc. Khi xóa một hard link, chỉ tên đó biến mất; đối tượng vẫn còn nếu có tên/handle khác giữ.

**Move:** `Files.move(symbolic, dest)` di chuyển bản thân symlink. Nếu target lưu tương đối, thư mục mới của symlink có thể thay đổi ý nghĩa đường dẫn, khiến link bị đứt.

**Copy:** `Files.copy(symbolic, dest)` theo symlink để copy mục tiêu theo mặc định; thêm `LinkOption.NOFOLLOW_LINKS` nếu muốn copy chính đối tượng symlink (nếu provider hỗ trợ). Copy thông thường **không** có nghĩa là copy đệ quy toàn bộ cây thư mục. `Files.copy(hard, dest)` thường tạo một tệp mới độc lập có cùng dữ liệu, không tạo thêm hard link.

Ví dụ copy bản thân symlink (minh họa; nguồn và điều kiện filesystem phải hợp lệ):

```java
Files.copy(
        Path.of("alias-symbolic.txt"),
        Path.of("alias-symbolic-copy.txt"),
        LinkOption.NOFOLLOW_LINKS
);
```

**Duyệt thư mục:** `Files.walk(root)` và `Files.walkFileTree(root, visitor)` không đi sâu theo symbolic link tới thư mục theo mặc định. Với `FileVisitOption.FOLLOW_LINKS`, việc duyệt có thể gặp vòng lặp symlink; cần xử lý `FileSystemLoopException` hoặc lỗi I/O tương ứng. Stream trả về bởi `Files.walk` phải được đóng (thường qua try-with-resources).

## 8. Khi nào dùng loại nào?

- Chọn **symbolic link** khi muốn một đường dẫn bí danh linh hoạt, trỏ tới thư mục, hoặc chuyển đổi mục tiêu theo tên (ví dụ tên `current` dẫn đến một thư mục phát hành). Hãy cân nhắc target tương đối/tuyệt đối và rủi ro link đứt.
- Chọn **hard link** khi cần nhiều tên cho cùng **đối tượng tệp** trong một filesystem và muốn dữ liệu vẫn truy cập qua tên còn lại sau khi xóa một tên. Hãy nhớ cập nhật nội dung tại chỗ tác động tới cùng dữ liệu.
- Chọn **bản sao độc lập** khi cần hai dữ liệu có vòng đời riêng; hard link và symbolic link **không thay thế** backup độc lập.

## 9. Giới hạn hệ thống, lỗi thường gặp và an toàn

1. **Cross-filesystem:** hard link thường không thể vượt volume/filesystem. Trên Windows, hard link phổ biến với tệp trên NTFS trong cùng volume; hành vi phụ thuộc filesystem.
2. **Quyền symbolic link:** Windows có thể cần quyền/chế độ hệ thống phù hợp (chẳng hạn Developer Mode), còn Unix cần quyền tại thư mục liên quan. Không giả định một ví dụ link sẽ chạy trên mọi máy.
3. **Link đã tồn tại:** `createLink` / `createSymbolicLink` không tự ghi đè tên cũ; có thể ném `FileAlreadyExistsException`. Không xóa tên có sẵn chỉ để thử lại khi chưa kiểm tra quyền sở hữu dữ liệu.
4. **Đích chưa tồn tại:** hard link cần đối tượng đích hiện hữu; symlink có thể trỏ tới path chưa có, rồi trở thành dangling link. Đọc nội dung theo link đứt thường gây lỗi I/O.
5. **Nhầm cơ sở đường dẫn:** target tương đối của symlink được tính từ **thư mục chứa link**, không từ current working directory của ứng dụng đọc nó.
6. **Chu trình symlink:** link thư mục có thể quay về thư mục tổ tiên, hoặc A → B → A. Theo link khi duyệt cây cần xử lý chu trình để tránh lỗi/vòng lặp.
7. **Race condition/TOCTOU:** giữa `Files.exists`, `isSymbolicLink` và thao tác `read/write/delete`, một tiến trình khác có thể thay link hoặc target. Một lần kiểm tra tồn tại **không đảm bảo** thao tác sau đó an toàn. Đối với path không tin cậy, cần kiểm soát thư mục được phép truy cập, quyền và API thao tác phù hợp.
8. **Ngoại lệ:** `UnsupportedOperationException`, `IOException` (ví dụ `AccessDeniedException`, `NoSuchFileException` hoặc `FileSystemException`) và `SecurityException` có thể xuất hiện tùy API và môi trường. Phải xử lý phù hợp với yêu cầu ứng dụng, không im lặng nuốt mọi lỗi.

Ba câu hỏi dễ nhầm: `isSymbolicLink(path)` hỏi **bản thân tên này có phải symlink không**; `exists(path)` thường hỏi **đường dẫn này giải quyết tới mục tiêu tồn tại không**; `isSameFile(a,b)` hỏi **hai đường dẫn cùng giải quyết tới một tệp không**. Chúng có thể cho các kết quả khác nhau đối với cùng một link.

## 10. Bài tập tư duy và lời giải

**A.** Tạo hard link `b.txt` tới `a.txt` rồi xóa `a.txt`. `b.txt` có đọc được không? **Có**, khi tạo hard link thành công; xóa một tên không xóa đối tượng còn được tên kia tham chiếu.

**B.** Tạo symbolic link `b.txt` chứa path `a.txt` rồi xóa `a.txt`. Vì sao `Files.exists(b)` có thể là `false` còn `Files.exists(b, NOFOLLOW_LINKS)` là `true`? **Vì** cách thứ nhất theo tới mục tiêu đã mất, cách thứ hai kiểm tra bản thân mục nhập link.

**C.** Dùng một tệp tạm để **thay thế đối tượng** tại `a.txt`. Hard link `b.txt` vốn cùng đối tượng với `a.txt` có nhất thiết thấy đối tượng mới không? **Không**; hard link vẫn gắn với đối tượng cũ. Symlink lưu đường dẫn `a.txt` thường theo đến đối tượng mới tại đường dẫn đó.

**D.** Muốn `app/current` là symlink tới `app/releases/v3` và dùng target tương đối, lưu path nào? **`releases/v3`**, vì target được giải quyết từ thư mục chứa symlink, tức `app`.

**E.** Hard link có phải backup không? **Không**, vì các hard link cùng chia sẻ đối tượng dữ liệu và sửa nội dung qua một tên có thể ảnh hưởng toàn bộ tên kia. Backup cần bản sao/snapshot có vòng đời thích hợp.

## 11. Ghi nhớ

**Hard link = tên khác của cùng một đối tượng tệp. Symbolic link = đối tượng chứa đường dẫn tới mục tiêu.** Trong Java NIO.2, phân biệt `createLink`, `createSymbolicLink`, `readSymbolicLink`, `isSymbolicLink`, `isSameFile` và `NOFOLLOW_LINKS`; luôn tính đến quyền truy cập, filesystem và khả năng mục tiêu thay đổi.

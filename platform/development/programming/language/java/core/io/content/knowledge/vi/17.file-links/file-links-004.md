# Liên kết hỏng và khác biệt giữa theo link / không theo link trong Java NIO.2

## 1. Mục tiêu và phạm vi

Trong Java Core I/O, một đường dẫn (`Path`) có thể chỉ trực tiếp tới tệp/thư mục hoặc chỉ tới **symbolic link (symlink, liên kết tượng trưng)**. Symlink là một mục trong hệ thống tệp lưu đường dẫn đến mục khác (đích). Khi API **follow link**, nó truy cập mục đích; khi dùng `LinkOption.NOFOLLOW_LINKS`, những API hỗ trợ tùy chọn này thao tác/đọc thuộc tính của chính mục symlink.

Sau bài này, bạn cần phân biệt được ba câu hỏi độc lập: (1) mục symlink có tồn tại không, (2) đích của symlink có truy cập được không, và (3) lệnh đang tác động tới symlink hay tới đích. Hiểu rõ ba câu hỏi này sẽ giúp tránh báo nhầm “tệp không tồn tại”, sao chép nhầm dữ liệu, hoặc xử lý sai khi dọn tệp.

## 2. Symlink hợp lệ, symlink hỏng và đường dẫn thường

Ví dụ trên hệ thống tệp hỗ trợ symbolic link:

```text
project/
├── data.txt                (tệp thật)
├── alias.txt -> data.txt   (symlink hợp lệ, đích có tồn tại)
└── stale.txt -> gone.txt   (symlink hỏng, đích không tồn tại)
```

- **Symlink hợp lệ**: bản thân mục liên kết tồn tại, và chuỗi đích mà nó trỏ tới được phân giải đến một mục có thể truy cập.
- **Symlink hỏng (broken/dangling symlink)**: bản thân mục liên kết vẫn tồn tại nhưng đường dẫn đích không phân giải đến mục tồn tại; ví dụ đích bị xóa, di chuyển, hoặc một liên kết trong chuỗi trỏ tới đích thiếu.
- **Đường dẫn không tồn tại**: không có mục nào tại vị trí đó; khác với symlink hỏng vì symlink hỏng vẫn có mục liên kết để đọc, di chuyển hoặc xóa.
- **Hard link** khác symlink: hard link là tên khác cho cùng đối tượng tệp trên hệ thống tệp hỗ trợ; xóa một tên không khiến các tên hard link còn lại trở thành symlink hỏng.

Một `Path` chỉ biểu diễn đường dẫn; chỉ gọi `Path.of(...)` hoặc `resolve(...)` không tự động kiểm tra tồn tại và không đảm bảo đường dẫn đó là tệp thật.

## 3. “Follow” và “NOFOLLOW” thực chất thay đổi điều gì?

Java NIO.2 dùng `java.nio.file.LinkOption.NOFOLLOW_LINKS` cho **những phương thức có hỗ trợ tùy chọn này**. Không có cài đặt toàn cục áp dụng cho mọi thao tác `Files`. Mỗi API có quy tắc riêng.

Xét `alias.txt -> data.txt`:

- `Files.exists(alias)`: mặc định **theo liên kết**, hỏi xem đường dẫn phân giải tới đích tồn tại không.
- `Files.exists(alias, LinkOption.NOFOLLOW_LINKS)`: **không theo liên kết ở mục được kiểm tra**, hỏi mục symlink có tồn tại không.
- `Files.readAttributes(alias, BasicFileAttributes.class)`: mặc định lấy thuộc tính của đích.
- `Files.readAttributes(alias, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)`: lấy thuộc tính của chính symlink, chẳng hạn `isSymbolicLink() == true`.
- `Files.isSymbolicLink(alias)`: nhận diện bản thân mục liên kết; vẫn trả `true` cho symlink hỏng nếu mục đó còn tồn tại và có thể được nhận diện.

**Lưu ý:** `NOFOLLOW_LINKS` trên một phép kiểm tra không có nghĩa mọi thành phần cha trong toàn bộ đường dẫn đều không thể được phân giải qua liên kết, cũng không tạo ra bảo đảm an toàn chống việc đường dẫn bị thay đổi đồng thời.

## 4. Bảng so sánh quan trọng nhất: `exists`, `notExists`, `isSymbolicLink`

Trong điều kiện có quyền truy cập, hệ thống tệp ổn định và không có lỗi I/O:

| Trạng thái tại `p` | `Files.exists(p)` | `Files.exists(p, NOFOLLOW_LINKS)` | `Files.isSymbolicLink(p)` |
| --- | --- | --- | --- |
| Tệp thường đang tồn tại | `true` | `true` | `false` |
| Symlink đến đích tồn tại | `true` | `true` | `true` |
| Symlink hỏng (đích thiếu) | `false` | `true` | `true` |
| Mục tại `p` hoàn toàn không tồn tại | `false` | `false` | `false` |

Cặp kiểm tra `exists(p) == false` và `exists(p, NOFOLLOW_LINKS) == true` là **dấu hiệu hữu ích** của link không phân giải được. Tuy nhiên, tuyệt đối không suy luận chắc chắn “đích đã bị xóa”: thiếu quyền, lỗi hệ thống tệp, liên kết vòng, hoặc thay đổi đồng thời cũng có thể làm một phép kiểm tra thất bại.

`Files.notExists(p)` **không phải** phủ định logic của `Files.exists(p)`. Nếu Java không xác định được sự tồn tại, cả `exists` và `notExists` đều có thể trả `false`. `Files.notExists(p, NOFOLLOW_LINKS)` kiểm tra sự vắng mặt của chính mục liên kết, không chỉ của đích.

Với symlink hỏng mà đích được xác định chắc chắn là không tồn tại, thông thường:

```java
Files.exists(link);                            // false
Files.notExists(link);                         // true
Files.exists(link, LinkOption.NOFOLLOW_LINKS);  // true
Files.notExists(link, LinkOption.NOFOLLOW_LINKS);// false
Files.isSymbolicLink(link);                    // true
```

Các dòng trên là **biểu thức minh họa**, giả định biến `link` đã khai báo và có đường dẫn thích hợp; chúng không phải chương trình Java độc lập.

## 5. Ví dụ Java 17+: tạo link hợp lệ, làm hỏng rồi kiểm tra

Tạo file `DanglingLinkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class DanglingLinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java-link-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(target, "Java NIO");
            // Lưu đích tương đối so với thư mục chứa symlink:
            Files.createSymbolicLink(link, target.getFileName());

            System.out.println("target before = " + Files.exists(target));
            System.out.println("follow before = " + Files.exists(link));
            System.out.println("nofollow before = "
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS));

            Files.delete(target); // Chỉ xóa đích; symlink vẫn còn

            System.out.println("target after = " + Files.exists(target));
            System.out.println("follow after = " + Files.exists(link));
            System.out.println("nofollow after = "
                    + Files.exists(link, LinkOption.NOFOLLOW_LINKS));
            System.out.println("is symlink = " + Files.isSymbolicLink(link));
            System.out.println("stored target = " + Files.readSymbolicLink(link));
        } finally {
            // Xóa liên kết, không truy theo liên kết để xóa đích.
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy trong thư mục có file nguồn, bằng JDK 17+:

```bash
javac DanglingLinkDemo.java
java DanglingLinkDemo
```

Kết quả khi hệ thống tệp hỗ trợ symlink và có quyền tạo symlink:

```text
target before = true
follow before = true
nofollow before = true
target after = false
follow after = false
nofollow after = true
is symlink = true
stored target = data.txt
```

**Diễn giải:** `Files.createSymbolicLink(link, target.getFileName())` lưu chuỗi `data.txt` trong mục liên kết. Lúc đầu cả link và đích đều tồn tại. Sau `Files.delete(target)`, mục `shortcut.txt` vẫn tồn tại, nhưng kiểm tra có theo link không còn tìm được tệp đích. `readSymbolicLink` vẫn đọc được đường dẫn đích đã lưu.

Chương trình này cần hệ thống tệp hỗ trợ symlink và quyền tạo nó. Trên một số cấu hình Windows, việc tạo symlink có thể cần quyền thích hợp hoặc Developer Mode; trên file system/provider khác có thể xuất hiện `UnsupportedOperationException` hay `IOException`. Nếu tạo link thất bại, không kỳ vọng stdout phía trên.

## 6. Đọc chính xác thuộc tính: đích hay mục liên kết?

`BasicFileAttributes` hỗ trợ `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `size()` và nhiều thuộc tính khác. Cùng một đường dẫn symlink có thể trả các thuộc tính khác nhau tùy có theo link.

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

// Các dòng dưới nằm trong phương thức có thể throws IOException.
// Giả sử link là symlink đến một tệp thường còn tồn tại.
Path link = Path.of("shortcut.txt");

BasicFileAttributes ofTarget =
        Files.readAttributes(link, BasicFileAttributes.class);
BasicFileAttributes ofLink =
        Files.readAttributes(link, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);

System.out.println(ofTarget.isRegularFile()); // true nếu đích là file thường
System.out.println(ofTarget.isSymbolicLink()); // false khi đọc thuộc tính đích
System.out.println(ofLink.isSymbolicLink());   // true khi đọc chính symlink
```

Đây là **đoạn minh họa đặt trong phương thức**, không phải tệp Java độc lập. Nếu symlink đã hỏng, lệnh đọc thuộc tính **đích** thường ném `NoSuchFileException`; đọc thuộc tính **link** với `NOFOLLOW_LINKS` vẫn có thể thành công. Đừng suy đoán độ dài nội dung của tệp thật từ `size()` lấy trên chính link: kích thước link và cách báo cáo phụ thuộc nhà cung cấp hệ thống tệp.

Các phép thử `Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)` và `Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)` thông thường là `false` đối với một symlink, ngay cả khi đích của nó là file hoặc thư mục tương ứng. Mặc định, những phép thử này thường theo link.

## 7. Đọc giá trị link và phân giải đích tương đối

`Files.readSymbolicLink(link)` trả về **đường dẫn được lưu bên trong symlink**, không tự động mở đích, không tự đảm bảo đích tồn tại, và không buộc trả về đường dẫn tuyệt đối.

Ví dụ, mục `/work/reports/latest.txt` chứa đích `../archive/report.txt`. Đường dẫn được lưu là `../archive/report.txt`, cần giải thích tương đối so với **thư mục chứa link**, chứ không phải thư mục làm việc hiện tại.

```java
Path link = Path.of("/work/reports/latest.txt");
Path storedTarget = Files.readSymbolicLink(link);
Path candidate = link.toAbsolutePath().getParent()
        .resolve(storedTarget)
        .normalize();
```

Đoạn trên minh họa phân giải từ thư mục cha của link; cần nằm trong phương thức xử lý `IOException` (và chỉ chạy với một symlink thực sự tồn tại). `normalize()` chỉ xử lý thành phần từ vựng như `..`, không chứng minh đích thực sự tồn tại, không theo link thêm và không bảo đảm đường dẫn nằm trong thư mục tin cậy. Nếu giá trị lưu sẵn là đường dẫn tuyệt đối, `resolve` theo quy tắc provider sẽ sử dụng đường dẫn tuyệt đối đó trên hệ thống tệp mặc định.

`link.toRealPath()` thường yêu cầu đích truy cập được và phân giải liên kết. `link.toRealPath(LinkOption.NOFOLLOW_LINKS)` xử lý các liên kết theo chế độ không theo link của API, với yêu cầu tồn tại và khác biệt theo provider; không thay thế `readSymbolicLink` khi cần đọc **chuỗi đích gốc**.

## 8. Copy, move, delete: mỗi thao tác có quy tắc riêng

| Thao tác | Với symlink hợp lệ | Khi symlink hỏng |
| --- | --- | --- |
| `Files.copy(link, dst)` | Mặc định theo link nguồn, sao chép **đích** (nếu đích là file: nội dung file) | Thường thất bại vì không thể đọc đích |
| `Files.copy(link, dst, LinkOption.NOFOLLOW_LINKS)` | Sao chép **bản thân symlink** nếu được hỗ trợ | Có thể sao chép link hỏng như một link; chuỗi đích vẫn có thể không hợp lệ ở vị trí mới |
| `Files.move(link, dst)` | Di chuyển/đổi tên **bản thân symlink**, không chuyển dữ liệu đích | Vẫn có thể di chuyển mục symlink hỏng |
| `Files.delete(link)` / `Files.deleteIfExists(link)` | Xóa **mục symlink**, không xóa file/thư mục đích | Xóa được mục symlink hỏng nếu quyền và điều kiện cho phép |
| `Files.readSymbolicLink(link)` | Trả đường dẫn đích được lưu | Vẫn có thể đọc giá trị link đã lưu |

Lưu ý khi di chuyển hoặc sao chép một symlink có **đích tương đối** sang thư mục mới: giá trị đích được lưu không nhất thiết thay đổi theo, vì thế link mới có thể hỏng dù link gốc hợp lệ. Không thêm `NOFOLLOW_LINKS` một cách máy móc vào mọi thao tác: `move` và `delete` đã có quy tắc làm việc với chính symlink; một số API không nhận tùy chọn này.

Đối với `Files.copy`, mục đích **ở nguồn** quyết định theo hay không theo liên kết; nếu vị trí đích đã tồn tại dưới dạng symlink, `REPLACE_EXISTING` tác động tới **mục liên kết đích**, không tự động xóa tệp mà nó trỏ tới. Sao chép không nhất thiết là thao tác nguyên tử; khi phát sinh `IOException`, mục đích mới có thể chưa hoàn chỉnh.

## 9. Duyệt cây thư mục: không theo mặc định, chỉ theo khi chủ động yêu cầu

- `Files.walk(root)` và `Files.walkFileTree(root, visitor)` mặc định **không theo symbolic link** khi duyệt cây.
- `Files.walk(root, FileVisitOption.FOLLOW_LINKS)` hoặc `Files.walkFileTree(root, Set.of(FileVisitOption.FOLLOW_LINKS), maxDepth, visitor)` chủ động theo liên kết thư mục.
- Theo link có thể đưa chương trình ra ngoài nhánh thư mục dự tính, lặp qua cùng vùng dữ liệu, hoặc gặp vòng lặp. Trong `walkFileTree`, vòng lặp có thể được báo bằng `FileSystemLoopException` ở `visitFileFailed`.
- Khi cho phép theo link, phải xác định chính sách đối với đích nằm ngoài cây, đích hỏng, quyền truy cập, độ sâu tối đa và lỗi I/O; với bộ quét hoặc thao tác xóa, không nên bật `FOLLOW_LINKS` một cách vô điều kiện.

Đặc biệt, `LinkOption.NOFOLLOW_LINKS` (trong thao tác kiểm tra thuộc tính, copy...) **khác enum** với `FileVisitOption.FOLLOW_LINKS` (trong duyệt cây). Hai loại tùy chọn được thiết kế cho những phương thức và hành vi riêng.

## 10. Chẩn đoán một đường dẫn nghi là link hỏng

Một quy trình điều tra có kiểm soát:

1. Đọc thuộc tính **mục** với `Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)`. Nếu ném `NoSuchFileException`, tại thời điểm kiểm tra mục không tìm được; nếu ném `AccessDeniedException` hoặc lỗi I/O khác, giữ nguyên thông tin lỗi, không đổi thành kết luận “không tồn tại”.
2. Nếu `attrs.isSymbolicLink()` là `false`, đây không phải symbolic link ở vị trí cuối của đường dẫn; tiếp tục xử lý theo loại tệp tương ứng.
3. Nếu đúng là symlink, đọc chuỗi đích bằng `Files.readSymbolicLink(path)` để phục vụ chẩn đoán.
4. Đọc thuộc tính **đích** bằng `Files.readAttributes(path, BasicFileAttributes.class)`. Thành công chứng tỏ đường dẫn phân giải được tại lúc đọc. `NoSuchFileException` là bằng chứng cho đích/chuỗi phân giải thiếu ở thời điểm đó; `AccessDeniedException`, `FileSystemLoopException` hoặc `IOException` khác yêu cầu xử lý riêng.
5. Quyết định xử lý theo yêu cầu nghiệp vụ: giữ nguyên link, báo cáo lỗi, cập nhật link bằng thao tác có kiểm soát, hoặc xóa **chính link** nếu chính sách cho phép.

Ví dụ đoạn xử lý cốt lõi, đặt trong phương thức khai báo `throws IOException`:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path path = Path.of("shortcut.txt");
BasicFileAttributes linkAttrs = Files.readAttributes(
        path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);

if (linkAttrs.isSymbolicLink()) {
    System.out.println("Stored: " + Files.readSymbolicLink(path));
    try {
        BasicFileAttributes targetAttrs =
                Files.readAttributes(path, BasicFileAttributes.class);
        System.out.println("Resolved target; directory = "
                + targetAttrs.isDirectory());
    } catch (NoSuchFileException e) {
        System.out.println("Target path missing at inspection time");
    } catch (AccessDeniedException e) {
        System.out.println("Cannot read target due to access restrictions");
    } catch (FileSystemLoopException e) {
        System.out.println("Detected symbolic-link cycle");
    } catch (IOException e) {
        System.out.println("Other resolution/I-O error: " + e.getMessage());
    }
}
```

**Giới hạn:** các ngoại lệ cụ thể tùy hệ điều hành/provider, `FileSystemLoopException` không được bảo đảm xuất hiện cho mọi vòng lặp, và mục có thể bị thay đổi giữa hai lần gọi. Cần bắt lỗi thích hợp ngay tại thao tác thực tế. Ví dụ này không tự xóa hoặc “sửa” link.

## 11. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `!Files.exists(link)` nghĩa là bản thân link đã biến mất | Mặc định theo đích, link hỏng vẫn tồn tại | Thêm phép kiểm `Files.exists(link, NOFOLLOW_LINKS)`; đọc thuộc tính link để xác nhận |
| `!Files.exists(path)` tương đương `Files.notExists(path)` | Không xác định được trạng thái có thể khiến cả hai đều `false` | Phân biệt “không tồn tại” và “không xác định”; kiểm tra lỗi khi thao tác |
| `Files.isRegularFile(link, NOFOLLOW_LINKS)` phải là `true` nếu link đến file | NOFOLLOW xem chính symlink, không phải loại của đích | Dùng phép đọc thuộc tính mặc định nếu thực sự cần loại đích |
| `readSymbolicLink` trả đường dẫn chuẩn tuyệt đối hoặc xác nhận đích hợp lệ | API trả chuỗi đường dẫn được lưu, có thể tương đối hoặc đã hỏng | Phân giải theo thư mục chứa link và thử truy cập đích riêng |
| Thêm `NOFOLLOW_LINKS` vào mọi `Files.*` | Không phải API nào cũng nhận tùy chọn này | Xem chữ ký và hợp đồng của từng API |
| `Files.move(link, dst)` sẽ chuyển tệp thật đằng sau | Move xử lý chính mục symlink | Chuyển tệp thật qua đường dẫn đích nếu đó là chủ ý |
| Xóa link sẽ xóa dữ liệu đích | `Files.delete(link)` xóa mục link | Chỉ xóa đích khi thực sự được chỉ định, có kiểm soát |
| Sao chép hoặc di chuyển link tương đối vẫn luôn giữ đích đúng | Link mới có thư mục gốc tương đối khác | Kiểm tra lại đích sau sao chép/di chuyển |
| Kiểm tra `exists` rồi tin kết quả mãi mãi | Có race giữa kiểm tra và sử dụng (TOCTOU) | Thực hiện thao tác cần thiết và xử lý `IOException`; dùng API an toàn hơn khi có yêu cầu bảo mật |

## 12. Vấn đề bảo mật và tính di động

- **TOCTOU (time of check to time of use):** symlink hoặc đích có thể đổi giữa `exists` và `readAttributes`, `copy`, `open`, `delete`. Trạng thái đọc chỉ đúng tại thời điểm quan sát; đừng dùng `exists` làm điều kiện bảo mật duy nhất.
- **Không tự coi `normalize()` là an toàn:** nó chỉ chuẩn hóa cú pháp; không ngăn symlink đưa đường dẫn ra ngoài thư mục được cho phép. Với vùng tệp do người dùng kiểm soát, xác minh ranh giới truy cập và cân nhắc API chống race phù hợp như `SecureDirectoryStream` nếu provider hỗ trợ.
- **Hệ điều hành/provider:** tạo hoặc sao chép symlink có thể không được hỗ trợ hoặc bị giới hạn quyền; nhiều file system có quy tắc riêng. Trên Windows, symbolic link, junction và shortcut `.lnk` không phải ba khái niệm đồng nhất. Kiểm tra bằng NIO.2, không suy diễn từ phần mở rộng file.
- **Xử lý lỗi đúng nghĩa:** phân biệt `NoSuchFileException`, `AccessDeniedException`, vòng lặp liên kết, và lỗi I/O khác; một phép kiểm boolean thường không đủ để tìm nguyên nhân.
- **Không follow khi duyệt/xóa dữ liệu không tin cậy** trừ khi đặc tả yêu cầu và đã có giới hạn rõ ràng.

## 13. Tình huống áp dụng và tự kiểm tra

**Tình huống A — dọn shortcut đã hỏng.** Đọc chính mục link bằng `NOFOLLOW_LINKS`, xác minh `isSymbolicLink()`, thử phân giải đích và phân biệt đích thiếu với lỗi truy cập. Khi được phép dọn, gọi `Files.delete(link)`; không xóa nhầm file đích.

**Tình huống B — sao lưu cây thư mục giữ nguyên cấu trúc link.** Duyệt cây không theo link, và tại nơi cần sao chép symlink dùng `Files.copy(source, destination, LinkOption.NOFOLLOW_LINKS)` nếu provider hỗ trợ. Sau sao chép, chú ý liên kết tương đối có thể đổi ý nghĩa ở vị trí mới.

**Tình huống C — thống kê nội dung thư mục theo đích thật.** Nếu chủ động muốn theo liên kết đến thư mục, sử dụng `FOLLOW_LINKS` khi duyệt, giới hạn độ sâu, xử lý chu trình và lỗi truy cập; chấp nhận rằng một tệp có thể được nhìn thấy qua nhiều đường dẫn.

Tự trả lời:

1. `Files.exists(brokenLink)` có thể là `false` dù `Files.isSymbolicLink(brokenLink)` là `true` không? **Có**, vì một phép hỏi về đích, phép còn lại hỏi về mục liên kết.
2. `Files.notExists(path)` luôn bằng `!Files.exists(path)`? **Không**, vì trạng thái không thể xác định.
3. Muốn lấy metadata của link hỏng? **Đọc `BasicFileAttributes` với `NOFOLLOW_LINKS`**.
4. Muốn biết nguyên văn symlink trỏ tới gì? **`Files.readSymbolicLink(path)`**, rồi phân giải tương đối nếu cần; không coi đó là xác nhận đích tồn tại.
5. `Files.delete(symlink)` xóa gì? **Mục symlink**, không xóa nội dung mà nó trỏ tới.

## Tài liệu đối chiếu

- Java SE 17 `java.nio.file.Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 `java.nio.file.LinkOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html
- Java SE 21 `java.nio.file.FileVisitOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html
- Oracle/dev.java, Walking the File Tree: https://dev.java/learn/api/io/java-io/file-system/walking-tree/

# NOFOLLOW_LINKS trong đọc thuộc tính và kiểm tra tệp (Java NIO.2)

## 1. Mục tiêu và bối cảnh

Khi chương trình Java kiểm tra một đường dẫn bằng `java.nio.file.Files`, đường dẫn đó có thể trỏ tới **tệp thật**, **thư mục**, hoặc một **symbolic link** (liên kết tượng trưng, gọi tắt là symlink). Symlink là một mục trong hệ thống tệp chứa đường dẫn tham chiếu tới một mục khác. Ví dụ:

```text
project/
├── data.txt             (tệp thường)
├── shortcut.txt -> data.txt
└── missing.txt -> gone.txt   (liên kết đứt: đích không tồn tại)
```

Khi hỏi “`shortcut.txt` có phải tệp thường không?”, ta cần xác định đang hỏi về **đích `data.txt`** hay **bản thân mục symlink `shortcut.txt`**. Hai cách hiểu cho kết quả khác nhau. `LinkOption.NOFOLLOW_LINKS` giúp chọn cách thứ hai trong **những API hỗ trợ tùy chọn này**.

Sau bài học, bạn cần phân biệt việc theo liên kết với việc đọc chính liên kết, dự đoán kết quả của `Files.exists` / `Files.isRegularFile` / `Files.readAttributes` khi có symlink hoặc liên kết đứt, và tránh nhầm kiểm tra metadata với bảo đảm an toàn khi mở tệp.

## 2. NOFOLLOW_LINKS thực sự có ý nghĩa gì?

`java.nio.file.LinkOption` là enum có hằng `NOFOLLOW_LINKS`. Với các phương thức `Files` nhận tham số `LinkOption... options`:

- **Mặc định (không truyền `NOFOLLOW_LINKS`):** thường đi theo symlink cuối đường dẫn và làm việc với metadata của **đích cuối cùng**.
- **Có `LinkOption.NOFOLLOW_LINKS`:** không đi theo symlink cuối đường dẫn; đọc hoặc kiểm tra **chính mục liên kết**.
- Nếu đường dẫn không phải symlink, hai cách thường cho cùng kết quả khi đối tượng không thay đổi và việc truy cập hợp lệ.

Ví dụ với `alias.txt -> original.txt`, trong đó `original.txt` là tệp thường:

| Câu hỏi | Mặc định | Với `NOFOLLOW_LINKS` |
|---|---|---|
| `isRegularFile(alias)` | `true`, xét tệp đích | `false`, vì mục alias là symlink |
| `isDirectory(alias)` | `false`, xét tệp đích | `false`, vì alias không phải thư mục |
| `exists(alias)` | `true` nếu đọc được đích | `true` nếu xác minh được chính liên kết |
| `readAttributes(alias, BasicFileAttributes.class).isRegularFile()` | `true` | `false` |
| `readAttributes(alias, BasicFileAttributes.class).isSymbolicLink()` | `false` trong ví dụ này | `true` |

Nếu alias trỏ tới **thư mục**, `Files.isDirectory(alias)` thường là `true`, còn `Files.isDirectory(alias, NOFOLLOW_LINKS)` là `false`. `NOFOLLOW_LINKS` không biến symlink thành tệp thường và không thay đổi loại thực của nó.

**Giới hạn cần nhớ:** tùy chọn được áp dụng cho **lời gọi cụ thể**, không phải một chế độ của JVM hay `Path`. Nó không mặc nhiên chặn symlink ở các thành phần thư mục cha của đường dẫn. Không nên nhầm symlink với *hard link*: hard link là tên khác của cùng mục tệp và không được nhận diện bằng `BasicFileAttributes.isSymbolicLink()`.

## 3. Đọc thuộc tính theo hai góc nhìn

### 3.1. `Files.readAttributes` với `BasicFileAttributes`

Đây là cách rõ ràng để lấy nhiều thông tin cùng lúc:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

// path là một Path đã được xác định trong chương trình.
BasicFileAttributes targetAttributes =
        Files.readAttributes(path, BasicFileAttributes.class);

BasicFileAttributes entryAttributes =
        Files.readAttributes(
                path,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS
        );

System.out.println(targetAttributes.isRegularFile());
System.out.println(entryAttributes.isSymbolicLink());
```

*Đây là đoạn mã minh họa, cần khai báo `path` và xử lý `IOException` trong chương trình chứa nó.* Với symlink trỏ tới tệp thường còn tồn tại, hai dòng in tương ứng là `true` và `true`. Dòng thứ nhất mô tả **đích**, dòng thứ hai mô tả **mục liên kết**. Khi không theo liên kết, `isRegularFile()` và `isDirectory()` trên metadata của symlink đều thường là `false`, còn `isSymbolicLink()` là `true`.

`BasicFileAttributes` cung cấp các phép hỏi loại mục (`isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`), kích thước (`size`), thời gian (`creationTime`, `lastModifiedTime`, `lastAccessTime`) và `fileKey`. Khi dùng `NOFOLLOW_LINKS`, các thuộc tính ấy nói về **liên kết** nếu đường dẫn cuối là symlink. **Không suy diễn `size()` của symlink là kích thước nội dung tệp đích**; giá trị và độ chính xác của nhiều thuộc tính phụ thuộc hệ thống tệp/provider. Việc đọc nhiều thuộc tính cùng một lần cũng không được mọi provider bảo đảm là snapshot nguyên tử trước thay đổi đồng thời.

### 3.2. Đọc thuộc tính theo tên

Hai overload sau cũng chấp nhận `NOFOLLOW_LINKS`:

```java
Object kind = Files.getAttribute(
        path, "basic:isSymbolicLink", LinkOption.NOFOLLOW_LINKS);

var attributes = Files.readAttributes(
        path,
        "basic:size,lastModifiedTime,isSymbolicLink",
        LinkOption.NOFOLLOW_LINKS
);
```

Đây là đoạn minh họa, với `path` có sẵn và `IOException` được xử lý bên ngoài. `getAttribute` trả về `Object`; nên ép kiểu theo thuộc tính cần đọc, ví dụ giá trị của `"basic:isSymbolicLink"` là `Boolean`. `readAttributes` dạng chuỗi trả về `Map<String,Object>`, không phải `BasicFileAttributes`. Tên `basic` là attribute view mặc định; nhóm thuộc tính khác như `posix:*` chỉ dùng khi provider hỗ trợ.

Một số API liên quan cũng nhận `LinkOption...` như `Files.getLastModifiedTime(path, NOFOLLOW_LINKS)`, `Files.getPosixFilePermissions(path, NOFOLLOW_LINKS)`, `Files.getOwner(path, NOFOLLOW_LINKS)` và `Files.getFileAttributeView(path, BasicFileAttributeView.class, NOFOLLOW_LINKS)`. Hãy đọc chữ ký phương thức: **`Files.size(path)` không nhận `LinkOption`**, nên không thể viết `Files.size(path, NOFOLLOW_LINKS)`; muốn hỏi kích thước metadata của chính symlink, dùng `readAttributes` với tùy chọn tương ứng.

### 3.3. Lấy đích được ghi trong symlink

`Files.readSymbolicLink(link)` đọc `Path` **được lưu trong liên kết**, chứ không đọc nội dung của tệp đích và không bảo đảm đích tồn tại. Nếu liên kết được tạo với đích tương đối như `data.txt`, đường dẫn trả về cũng có thể là đường dẫn tương đối. Không đánh đồng kết quả này với `link.toRealPath()`: phương thức thứ hai xử lý đường dẫn thực trong hệ thống tệp và có quy tắc theo liên kết riêng.

## 4. Kiểm tra sự tồn tại và loại mục

Các phương thức kiểm tra thường gặp:

| API | Có nhận `LinkOption...`? | Điều cần nhớ |
|---|---|---|
| `Files.exists(path, options)` | Có | Hỏi mục tồn tại; mặc định theo symlink |
| `Files.notExists(path, options)` | Có | Chỉ `true` nếu xác minh được là không tồn tại |
| `Files.isRegularFile(path, options)` | Có | Symlink đến tệp thường là “tệp thường” theo mặc định, nhưng không phải khi `NOFOLLOW_LINKS` |
| `Files.isDirectory(path, options)` | Có | Tương tự khi symlink trỏ tới thư mục |
| `Files.isSymbolicLink(path)` | Không | Kiểm tra chính mục symlink; không cần truyền `NOFOLLOW_LINKS` |
| `Files.isReadable(path)`, `isWritable(path)`, `isExecutable(path)` | Không | Không có overload nhận `LinkOption`; không suy ra “không theo link” |
| `Files.readString(path)`, `readAllBytes(path)` | Không | Đọc nội dung, không phải API đọc metadata với `LinkOption` |

**Điểm dễ nhầm:** `Files.isSymbolicLink(path)` có ích khi nhận diện liên kết, nhưng trả về `false` cũng có thể là do không xác định được trạng thái. Nếu ứng dụng cần phân biệt lỗi I/O với “không phải liên kết”, dùng `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` và xử lý ngoại lệ.

### 4.1. Trường hợp symlink bị đứt (dangling symlink)

Giả sử `broken.txt -> missing.txt` và `missing.txt` thực sự không tồn tại, còn mục `broken.txt` vẫn tồn tại:

| Biểu thức | Kết quả trong điều kiện kiểm tra thành công | Lý do |
|---|---|---|
| `Files.exists(broken)` | `false` | Theo link tới đích không tồn tại |
| `Files.exists(broken, NOFOLLOW_LINKS)` | `true` | Mục liên kết vẫn hiện diện |
| `Files.notExists(broken)` | `true` | Xác nhận không có đích |
| `Files.notExists(broken, NOFOLLOW_LINKS)` | `false` | Mục liên kết vẫn tồn tại |
| `Files.isSymbolicLink(broken)` | `true` | Kiểm tra bản thân liên kết |
| `Files.isRegularFile(broken, NOFOLLOW_LINKS)` | `false` | Liên kết không phải tệp thường |
| `Files.readAttributes(broken, BasicFileAttributes.class)` | Có thể ném `NoSuchFileException` | Không đọc được thuộc tính của đích |
| `Files.readAttributes(broken, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Đọc được thuộc tính của link nếu provider cho phép | Không cần đích tồn tại |

**Không được dùng `!Files.exists(path)` làm bằng chứng chắc chắn rằng không có mục nào ở đó.** Nếu quyền truy cập hoặc I/O không cho phép xác định, cả `exists` và `notExists` đều có thể trả `false`. Các hàm kiểu boolean như `isDirectory` và `isRegularFile` cũng gộp trường hợp “không xác định” vào `false`. Khi ứng dụng cần biết *vì sao* thất bại, hãy đọc thuộc tính bằng API có ném `IOException` và xử lý cụ thể.

## 5. Ví dụ Java 17+ chạy được: liên kết hợp lệ rồi trở thành liên kết đứt

Chương trình sau tự tạo thư mục tạm, tệp đích và symlink có đích tương đối. Nó so sánh việc đọc thuộc tính/kiểm tra trước và sau khi xóa tệp đích; `finally` dọn tài nguyên đã tạo.

**Tệp:** `NoFollowLinksDemo.java`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

import static java.nio.file.LinkOption.NOFOLLOW_LINKS;

public class NoFollowLinksDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nofollow-demo-");
        Path target = directory.resolve("data.txt");
        Path link = directory.resolve("shortcut.txt");

        try {
            Files.writeString(target, "Hello Java");

            try {
                // Đích tương đối được giải thích từ thư mục chứa link.
                Files.createSymbolicLink(link, target.getFileName());
            } catch (IOException | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("Cannot create symbolic link");
                return;
            }

            BasicFileAttributes followed = Files.readAttributes(
                    link, BasicFileAttributes.class);
            BasicFileAttributes linkItself = Files.readAttributes(
                    link, BasicFileAttributes.class, NOFOLLOW_LINKS);

            System.out.println("target regular: " + followed.isRegularFile());
            System.out.println("entry symbolic: " + linkItself.isSymbolicLink());
            System.out.println("regular nofollow: "
                    + Files.isRegularFile(link, NOFOLLOW_LINKS));
            System.out.println("exists follow: " + Files.exists(link));
            System.out.println("exists nofollow: "
                    + Files.exists(link, NOFOLLOW_LINKS));

            Files.delete(target); // Link vẫn còn, nhưng đích biến mất.
            System.out.println("broken exists follow: " + Files.exists(link));
            System.out.println("broken exists nofollow: "
                    + Files.exists(link, NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp nguồn:

```bash
javac NoFollowLinksDemo.java
java NoFollowLinksDemo
```

Khi hệ thống hỗ trợ tạo symlink và không có thay đổi đồng thời ngoài chương trình, stdout dự kiến:

```text
target regular: true
entry symbolic: true
regular nofollow: false
exists follow: true
exists nofollow: true
broken exists follow: false
broken exists nofollow: true
```

Một số môi trường Windows cần quyền hoặc thiết lập cho phép tạo symlink; provider/hệ thống tệp khác cũng có thể không hỗ trợ. Khi không tạo được liên kết, chương trình in duy nhất `Cannot create symbolic link` và chạy phần `finally`. Dòng `Files.delete(target)` xóa tệp đích **chứ không xóa liên kết**; vì vậy hai kết quả `exists` ở cuối khác nhau. Mã không phụ thuộc đường dẫn tạm cụ thể, và đường dẫn đích tương đối tránh gắn ví dụ với một hệ điều hành.

## 6. Áp dụng trong ứng dụng thực tế

### Tình huống A: công cụ liệt kê thư mục cần phân biệt liên kết

Giả sử trình quản lý tệp muốn gắn nhãn “File”, “Directory”, “Symbolic link” cho mỗi mục mà nó nhìn thấy. Đọc metadata với `NOFOLLOW_LINKS` để không biến một symlink trỏ tới thư mục thành chính thư mục ấy:

```java
BasicFileAttributes attrs = Files.readAttributes(
        entry, BasicFileAttributes.class, NOFOLLOW_LINKS);

String kind = attrs.isSymbolicLink() ? "Symbolic link"
        : attrs.isDirectory() ? "Directory"
        : attrs.isRegularFile() ? "File"
        : "Other";
```

Đoạn minh họa này giả định `entry` là `Path`, `IOException` được xử lý ở caller. Nếu muốn hiển thị cả loại đích, thực hiện **lần đọc khác không có `NOFOLLOW_LINKS`**, và chấp nhận có thể thất bại với link đứt. Tránh trình bày metadata mục symlink như thể là metadata của đích.

### Tình huống B: xử lý thư mục upload có symlink

Nếu nghiệp vụ chỉ cho phép **đối tượng được chỉ định trực tiếp là tệp thường**, `Files.isRegularFile(candidate, NOFOLLOW_LINKS)` là một bước kiểm tra rõ nghĩa: nó từ chối mục cuối là symlink kể cả khi symlink dẫn đến tệp thường. Nếu nghiệp vụ cho phép symlink thì cần chính sách riêng về đích hợp lệ và đường dẫn cha.

Tuy nhiên, **kiểm tra xong rồi mở tệp là hai thao tác riêng**. Giữa chúng, kẻ khác hoặc một luồng khác có thể thay mục hoặc đường dẫn (race condition/TOCTOU). `NOFOLLOW_LINKS` trong kiểm tra metadata **không tự bảo vệ** một lời gọi `Files.newInputStream`, `Files.readString`, hay thao tác mở sau đó. Để xử lý đường dẫn không đáng tin cậy, cần chính sách thư mục gốc, quyền hệ thống tệp, mở tệp với tùy chọn phù hợp và khi khả dụng dùng `SecureDirectoryStream` cho thao tác tương đối theo một thư mục đã mở. Không dựa riêng vào `exists` hoặc `toRealPath` trước khi mở để khẳng định mọi race đã được loại bỏ.

### Tình huống C: theo dõi timestamp của liên kết

Một công cụ chẩn đoán muốn biết “bản thân symlink được sửa lần cuối khi nào?” có thể gọi:

```java
var targetTime = Files.getLastModifiedTime(link);
var linkTime = Files.getLastModifiedTime(link, NOFOLLOW_LINKS);
```

Đây là đoạn minh họa với `link` được khai báo và `IOException` được xử lý bên ngoài. `targetTime` mô tả tệp đích (nếu truy cập được), còn `linkTime` mô tả liên kết (nếu hệ thống tệp hỗ trợ). Hai thời gian có thể khác nhau. Đừng giả định mọi hệ thống tệp đều lưu thời gian hoặc độ chính xác theo cùng một cách.

## 7. Phân biệt với các API lân cận

- **`Path.toRealPath()`:** thường giải quyết các symlink để lấy đường dẫn thực; `toRealPath(NOFOLLOW_LINKS)` có quy tắc không theo link trong quá trình xác định đường dẫn. Không phải API đọc `BasicFileAttributes`.
- **`Files.readSymbolicLink(link)`:** trả đường dẫn mà symlink chứa; không dereference rồi đọc nội dung.
- **`Files.walkFileTree` / `Files.walk`:** mặc định không đi xuống các symlink trong quá trình duyệt cây; việc bật `FileVisitOption.FOLLOW_LINKS` là cơ chế riêng, không phải truyền `LinkOption.NOFOLLOW_LINKS` cho tất cả thao tác.
- **`Files.copy`:** có `LinkOption.NOFOLLOW_LINKS` thông qua tham số `CopyOption...`; khi sao chép link với tùy chọn này, mục liên kết được sao chép thay vì theo đích, theo khả năng/provider của hệ thống tệp. Đừng suy diễn từ đó rằng mọi overload của `Files` đều nhận tùy chọn.
- **`Files.isSymbolicLink(path)`:** bản thân phép thử đã hỏi về liên kết; không viết `Files.isSymbolicLink(path, NOFOLLOW_LINKS)` vì không có chữ ký như vậy.

## 8. Ngoại lệ, giới hạn môi trường và lỗi phổ biến

1. **Gọi nhầm API không có tham số tùy chọn.** `Files.size(path, NOFOLLOW_LINKS)` và `Files.isSymbolicLink(path, NOFOLLOW_LINKS)` không biên dịch. Hãy chọn overload được Java API định nghĩa.
2. **Nhầm `NOFOLLOW_LINKS` thành “đường dẫn không chứa symlink”.** Nó kiểm tra mục cuối theo ngữ nghĩa của lời gọi, không chứng minh rằng mọi thành phần đường dẫn cha đều không phải symlink.
3. **Nhầm `exists == false` thành không tồn tại chắc chắn.** Có trường hợp thiếu quyền hoặc I/O khiến trạng thái không xác định; `notExists` cũng trả `false` khi không chắc.
4. **Bỏ qua liên kết đứt.** Theo link thì không lấy được thuộc tính đích; không theo link vẫn có thể đọc metadata của chính mục liên kết.
5. **Xem `isRegularFile == false` là symlink.** Kết quả đó còn có thể là thư mục, loại tệp đặc biệt, tệp không tồn tại hoặc lỗi xác định. Để phân loại, dùng `BasicFileAttributes` và xử lý ngoại lệ.
6. **Giả định thuộc tính của link là nội dung của đích.** `size`, `lastModifiedTime`, `fileKey` phụ thuộc mục đang đọc và provider; không gán ý nghĩa sai khi hiển thị.
7. **Bỏ qua khả năng của hệ điều hành.** Tạo symlink có thể bị từ chối; các view như POSIX không hiện diện trên mọi hệ thống; một số thao tác với chính thuộc tính symlink có thể không được hỗ trợ.
8. **Dùng kiểm tra tệp như khóa an toàn.** Kiểm tra và sử dụng có thể bị thay đổi giữa hai thời điểm. Khi cần bảo mật, thiết kế thao tác truy cập an toàn ngay tại thời điểm mở/sử dụng.

Khi đọc thuộc tính dạng `readAttributes` / `getAttribute`, hãy chuẩn bị xử lý `IOException` (đặc biệt `NoSuchFileException` nếu đích bị xóa), `UnsupportedOperationException` cho view không được hỗ trợ và `SecurityException` khi môi trường chặn truy cập. Tránh bắt mọi ngoại lệ rồi âm thầm giả định đối tượng là “không tồn tại”.

## 9. Tự kiểm tra

1. Symlink `docs -> actual-directory`: `Files.isDirectory(docs)` và `Files.isDirectory(docs, NOFOLLOW_LINKS)` cho kết quả gì nếu đích còn tồn tại? **Dự kiến:** `true` và `false`.
2. Liên kết `bad -> removed.txt` vẫn còn, nhưng đích đã bị xóa. `Files.exists(bad, NOFOLLOW_LINKS)` là gì? **Dự kiến:** `true` nếu có thể kiểm tra chính mục liên kết.
3. Muốn hỏi symlink là một liên kết hay không và phân biệt lỗi đọc metadata, bạn chọn gì? **Gợi ý:** `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()` trong khối xử lý `IOException`.
4. Vì sao `Files.isRegularFile(path, NOFOLLOW_LINKS)` trước `Files.readString(path)` chưa bảo đảm đọc đúng đối tượng vừa kiểm tra? **Vì:** có thể thay đổi đường dẫn/mục giữa hai lời gọi; phương thức đọc nội dung không nhận cùng `LinkOption`.

## 10. Ghi nhớ và tài liệu chính thức

**Quy tắc cốt lõi:** *Muốn biết đối tượng ở cuối liên kết là gì, dùng mặc định; muốn biết chính mục liên kết là gì, dùng `NOFOLLOW_LINKS` ở API có hỗ trợ.* Đối với kiểm tra sự tồn tại, nhớ trường hợp “không xác định”; đối với bảo mật, nhớ ranh giới giữa đọc metadata và mở/sử dụng tệp.

- Java SE 21 — `Files`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Java SE 21 — `LinkOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html
- Java SE 21 — `BasicFileAttributes`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html

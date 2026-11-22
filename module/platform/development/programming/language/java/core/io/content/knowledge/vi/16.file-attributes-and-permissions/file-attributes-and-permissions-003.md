# Kích thước, loại tệp và `fileKey` với `BasicFileAttributes` trong Java NIO.2

Khi xử lý file trong Java, một đường dẫn (`Path`) không tự cho biết thứ mà nó đang trỏ đến là **tệp thông thường**, **thư mục**, **symbolic link**, đối tượng hệ thống tệp đặc biệt hay không tồn tại. Ứng dụng cũng cần biết **kích thước theo byte**, và đôi khi cần xác định liệu hai đường dẫn có đại diện cho **cùng một tệp thực** hay không. Những câu hỏi này liên quan nhưng không đồng nhất.

API trọng tâm là:

```java
BasicFileAttributes attributes = Files.readAttributes(
        path, BasicFileAttributes.class);
```

Đây là đoạn mã **minh họa**, cần các import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.attribute.BasicFileAttributes`, và xử lý `IOException`. Lệnh đọc thuộc tính từ hệ thống tệp thông qua provider; nó **không đọc nội dung** file vào một `String`, không mở một `InputStream` để bạn đọc các byte nội dung và không tạo file mới.

Từ `attributes`, có thể hỏi:

```java
long bytes = attributes.size();
boolean regular = attributes.isRegularFile();
boolean directory = attributes.isDirectory();
boolean symbolicLink = attributes.isSymbolicLink();
boolean other = attributes.isOther();
Object key = attributes.fileKey();
```

Trong các phương thức này, `size()` và bốn phép phân loại trả về thông tin thuộc tính; `fileKey()` cung cấp một **định danh đối tượng do filesystem/provider quyết định** nếu có hỗ trợ. `fileKey` rất hữu ích nhưng **không phải ID toàn cục, không bảo đảm tồn tại và không dùng làm chứng cứ bảo mật bất biến**.

Bài này dùng Java 17+, tập trung vào ý nghĩa hợp đồng API, khác biệt `File`/`Files`, hành vi với symbolic link, file system metadata thay đổi, kiểm tra danh tính tệp và các sai lầm thực tế.

## 1. `BasicFileAttributes` và `Files.readAttributes(...)`

`BasicFileAttributes` là interface trong package:

```java
java.nio.file.attribute.BasicFileAttributes
```

Nó cung cấp nhóm metadata cơ bản:

| Thành viên | Giá trị | Câu hỏi nó trả lời |
| --- | --- | --- |
| `size()` | `long` | Kích thước được filesystem báo cáo, đơn vị byte |
| `isRegularFile()` | `boolean` | Đây có phải regular file không? |
| `isDirectory()` | `boolean` | Đây có phải thư mục không? |
| `isSymbolicLink()` | `boolean` | Đây có phải symbolic link không? |
| `isOther()` | `boolean` | Đây có thuộc loại khác những loại nêu trên không? |
| `fileKey()` | `Object` hoặc `null` | Có khóa định danh tệp do provider cung cấp không? |
| `creationTime()` | `FileTime` | Thời điểm tạo (phụ thuộc provider) |
| `lastModifiedTime()` | `FileTime` | Thời điểm sửa gần nhất |
| `lastAccessTime()` | `FileTime` | Thời điểm truy cập gần nhất |

Ba timestamp là những phần khác của `BasicFileAttributes`, nhưng trọng tâm ở đây là **size, type, fileKey**. Không mặc định mọi provider có độ chính xác thời gian giống nhau hoặc hỗ trợ đầy đủ metadata của mọi loại filesystem.

Một lời gọi đọc thuộc tính điển hình:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class);
```

Theo mặc định, phép truy vấn thường **đi theo symbolic link** để lấy thuộc tính của *đích liên kết* (target). Nếu muốn hỏi về **chính mục symbolic link**, dùng:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là những đoạn **minh họa**, không phải chương trình Java độc lập. `LinkOption.NOFOLLOW_LINKS` quan trọng vì cùng một `Path` có thể dẫn tới hai đối tượng metadata khác nhau: **link** hoặc **target**.

### Vì sao đọc một nhóm thuộc tính thay vì gọi nhiều phương thức?

Ta có thể gọi:

```java
long bytes = Files.size(path);
boolean regular = Files.isRegularFile(path);
```

Nếu cần cả loại tệp, kích thước và `fileKey`, `Files.readAttributes(...)` gom các thuộc tính cơ bản vào **một truy vấn ở mức API**. Nó cũng cung cấp kết quả theo cùng bộ thuộc tính được trả về.

Tuy nhiên, **không mặc định toàn bộ thuộc tính được đọc nguyên tử** trên mọi filesystem; hợp đồng của API cho phép cách đọc cụ thể tùy implementation. Hơn nữa, các thuộc tính đã lấy có thể trở nên lỗi thời ngay sau khi gọi. `BasicFileAttributes` không phải “khóa” file và không bảo đảm trạng thái không đổi cho các thao tác phía sau.

## 2. `size()` là kích thước theo byte, không phải ký tự

Đối với regular file, `attrs.size()` biểu diễn **kích thước file tính bằng byte** mà hệ thống tệp báo cáo; giá trị có kiểu `long`. `Files.size(path)` cũng trả về kích thước byte và có thể ném `IOException` nếu không lấy được.

Ba đơn vị thường bị nhầm:

- **Byte trên file**: giá trị từ `Files.size(path)` hoặc `attrs.size()` cho regular file.
- **Đơn vị `char` UTF-16**: `String.length()` trong Java, không phải số byte UTF-8.
- **Unicode code point**: số mã Unicode trong chuỗi, cũng không nhất thiết bằng byte hay `String.length()`.

Ví dụ chuỗi `"A😀"` khi được mã hóa bằng UTF-8:

| Đơn vị | Kết quả |
| --- | ---: |
| Byte UTF-8 | 5 |
| `String.length()` | 3 |
| `String.codePointCount(...)` | 2 |

Ký tự `A` chiếm 1 byte UTF-8; emoji ở ví dụ chiếm 4 byte. Emoji chiếm **hai đơn vị UTF-16** trong Java nên chuỗi có `length()==3`.

### Ví dụ 1 — quan sát size, type và fileKey

Chương trình tạo một file tạm trong máy đang chạy, ghi UTF-8 và đọc thuộc tính của file đó. Các phép so sánh không phụ thuộc vào đường dẫn tuyệt đối hay tên file tạm.

```java
// BasicAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class BasicAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("attrs-", ".txt");
        String text = "A😀";

        try {
            Files.writeString(path, text, StandardCharsets.UTF_8);

            BasicFileAttributes attrs = Files.readAttributes(
                    path, BasicFileAttributes.class);

            System.out.println("regular=" + attrs.isRegularFile());
            System.out.println("directory=" + attrs.isDirectory());
            System.out.println("symbolicLink=" + attrs.isSymbolicLink());
            System.out.println("other=" + attrs.isOther());
            System.out.println("size=" + attrs.size());
            System.out.println("filesSize=" + Files.size(path));
            System.out.println("utf16Units=" + text.length());
            System.out.println("codePoints="
                    + text.codePointCount(0, text.length()));
            System.out.println("fileKeyAvailable="
                    + (attrs.fileKey() != null));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 BasicAttributesDemo.java
java BasicAttributesDemo
```

Trên một hệ thống tệp tạm thông thường có regular file và hỗ trợ ghi thành công, các dòng đầu là:

```text
regular=true
directory=false
symbolicLink=false
other=false
size=5
filesSize=5
utf16Units=3
codePoints=2
```

Dòng cuối **phụ thuộc filesystem/provider**:

```text
fileKeyAvailable=true
```

hoặc:

```text
fileKeyAvailable=false
```

Không in chính nội dung `fileKey` vào output mẫu vì kiểu, định dạng và tính sẵn có của nó **không cố định** giữa Windows, Linux, macOS và các filesystem khác.

Lời gọi `Files.writeString(...)` ở ví dụ sử dụng lựa chọn mặc định để ghi nội dung. Sau khi nó hoàn thành, `attrs.size()` và `Files.size(path)` có thể cùng báo 5 byte. Trong một ứng dụng có nhiều tiến trình truy cập file, hai lần truy vấn này vẫn có thể thấy kết quả khác nhau nếu dữ liệu thay đổi ở giữa.

## 3. `size()` không phải “dung lượng đang chiếm trên đĩa”

Phân biệt:

- **Logical file size**: độ dài nội dung file mà ứng dụng nhìn thấy theo byte; thường là kết quả `size()`.
- **Allocated space**: số block/extent thực sự được filesystem cấp phát trên thiết bị, có thể khác logical size.
- **Dung lượng volume**: thông tin tổng, còn trống hoặc có thể sử dụng của phân vùng, không phải kích thước một file.

Ví dụ một file nhỏ 1 byte vẫn có thể chiếm một block trên hệ thống tệp; một **sparse file** rất lớn có thể chỉ cấp phát block tại một số vùng; file được nén tại filesystem có thể chiếm vật lý ít hơn logical size.

`Files.size(path)` và `BasicFileAttributes.size()` **không phải API đo chính xác dung lượng cấp phát vật lý**. Không dùng chúng để suy số block đã chiếm, và cũng không suy lượng bộ nhớ cần thiết cho mọi biến thể giải nén/nén từ giá trị đó.

Ngoài ra:

- **Thư mục:** kích thước do `size()` báo cho directory là **implementation-specific, không được quy định nhất quán**. Nó không có nghĩa tổng kích thước tất cả file con.
- **Symbolic link:** nếu đọc thuộc tính của **chính link** (`NOFOLLOW_LINKS`), ý nghĩa `size()` tùy provider, chẳng hạn độ dài biểu diễn đường dẫn liên kết; không lấy làm dung lượng của target.
- **Socket, device, FIFO hoặc loại khác:** ý nghĩa `size()` có thể khác theo hệ thống; không áp quy tắc regular file một cách mù quáng.
- **File rỗng và file không tồn tại:** regular file rỗng có size bằng 0; một đường dẫn không tồn tại **không có bộ thuộc tính hợp lệ** để `Files.readAttributes` trả về bình thường.

Nếu cần tổng dung lượng của một **cây thư mục**, phải duyệt cây bằng API phù hợp và định nghĩa quy tắc riêng: có tính link không, có theo mount không, có đếm hard link lặp không, xử lý permission và file biến mất thế nào. Không dùng `Files.size(directory)` để thay thao tác đó.

## 4. Phân loại tệp với bốn cờ type

`BasicFileAttributes` phân loại theo những câu hỏi khác nhau:

| Cờ | Ý nghĩa |
| --- | --- |
| `isRegularFile()` | File thường, nội dung được quản lý như regular file |
| `isDirectory()` | Directory |
| `isSymbolicLink()` | Symbolic link |
| `isOther()` | Một loại file khác không nằm trong ba loại được nêu |

Đừng viết:

```java
if (!attrs.isRegularFile()) {
    // Sai nếu mặc định chắc chắn đây là thư mục!
}
```

Một đối tượng không phải regular file có thể là symbolic link, thiết bị, FIFO, socket hoặc file loại khác. Nếu bạn đọc metadata **có đi theo link**, cờ `isSymbolicLink()` có thể là `false` vì đối tượng bạn đang quan sát là **target** (ví dụ một regular file). Khi muốn phân loại mục link, phải đọc với `NOFOLLOW_LINKS`.

`isOther()` **không có nghĩa là file không tồn tại**. Nếu `Files.readAttributes` không lấy được thuộc tính của file vì đường dẫn không tồn tại, thông thường nó ném `NoSuchFileException`/`IOException`, thay vì tạo một `BasicFileAttributes` có `isOther()==true`.

### Ví dụ 2 — phân biệt file thường, thư mục và lỗi không tồn tại

```java
// FileTypeAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileTypeAttributesDemo {
    private static void inspect(String name, Path path)
            throws java.io.IOException {
        try {
            BasicFileAttributes attrs =
                    Files.readAttributes(path, BasicFileAttributes.class);
            System.out.println(name + ":regular="
                    + attrs.isRegularFile() + ",directory="
                    + attrs.isDirectory());
        } catch (NoSuchFileException ex) {
            System.out.println(name + ":missing");
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("kinds-");
        Path regular = root.resolve("file.txt");
        Path folder = root.resolve("folder");
        Path missing = root.resolve("missing.txt");

        try {
            Files.writeString(regular, "OK", StandardCharsets.UTF_8);
            Files.createDirectory(folder);

            inspect("file", regular);
            inspect("folder", folder);
            inspect("absent", missing);
        } finally {
            Files.deleteIfExists(regular);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FileTypeAttributesDemo.java
java FileTypeAttributesDemo
```

Kết quả trên hệ thống tệp tạm thông dụng, khi thao tác tạo tệp/thư mục thành công:

```text
file:regular=true,directory=false
folder:regular=false,directory=true
absent:missing
```

Khác với `java.io.File.isFile()`/`isDirectory()` vốn thường trả `false` khi không xác định được, `Files.readAttributes()` có thể cho biết **lý do thất bại qua `IOException`**. Tuy nhiên, không phải mọi provider đều phân loại lỗi thành đúng `NoSuchFileException`; ví dụ vẫn có thể ném một dạng `IOException` khác và truyền lỗi lên caller.

## 5. `Files.size()`, `File.length()` và `BasicFileAttributes.size()`

Có ba API dễ gặp khi tìm kích thước:

| Cách | Kiểu trả về | Hành vi đáng nhớ |
| --- | --- | --- |
| `new File(pathString).length()` | `long` | API cũ; file không tồn tại thường trả `0`; giá trị cho thư mục không xác định |
| `Files.size(path)` | `long` | API NIO.2, ném `IOException` khi truy vấn thất bại |
| `Files.readAttributes(path, BasicFileAttributes.class).size()` | `long` | Lấy kích thước cùng các thuộc tính type/fileKey, có thể ném `IOException` |

Vì file rỗng cũng có size `0`, không được dùng điều kiện:

```java
if (legacyFile.length() == 0) {
    // Kết luận "file rỗng" là thiếu điều kiện.
}
```

Đây là đoạn minh họa một sai lầm: file có thể không tồn tại, là thư mục, có lỗi truy vấn hoặc thật sự là regular file rỗng.

Cũng không có cách bảo đảm file không đổi chỉ bằng một chuỗi:

```java
if (Files.exists(path) && Files.isRegularFile(path)) {
    long size = Files.size(path);
    // File có thể đã thay đổi giữa các lệnh.
}
```

Kiểm tra trước rồi dùng sau có **TOCTOU** (*time of check to time of use*). Luôn xử lý lỗi của lần truy vấn hoặc mở file thật. Nếu phần xử lý phải đọc một version nhất quán, cần chính sách snapshot, lock hoặc các khả năng cụ thể của hệ thống tệp, không chỉ ba boolean ở trên.

## 6. `fileKey()` chính xác là gì?

Theo hợp đồng `BasicFileAttributes`, `fileKey()` trả một `Object` **nhận diện file** theo cơ chế do filesystem/provider cung cấp, hoặc `null` nếu không có khóa định danh.

```java
Object key = attrs.fileKey();

if (key == null) {
    // Provider không cung cấp file key trong trường hợp này.
}
```

Đây là **đoạn minh họa**; `attrs` là `BasicFileAttributes` có sẵn. Kiểu là `Object`, không phải `long`, `UUID` hoặc `String` bắt buộc. Không ép kiểu nó thành `Long` hay đoán cú pháp in ra. Trên một filesystem, key có thể được triển khai bằng số hiệu inode kết hợp device identifier; nơi khác có thể dùng file ID hoặc cấu trúc riêng; implementation quyết định hình dạng.

### Công dụng

`fileKey` hữu ích khi cần:

- Ghi nhận **danh tính được provider cung cấp** cho một file trong một đợt quét hoặc thao tác.
- Phát hiện **cùng một đối tượng tệp** xuất hiện qua nhiều đường dẫn, chẳng hạn hard link (khi provider hỗ trợ file keys).
- Hỗ trợ thuật toán duyệt cây và nhận biết đối tượng đã gặp trong tình huống có symbolic link, kết hợp cơ chế khác khi key không có.
- So sánh metadata **theo đúng phạm vi tính ổn định của provider**, ví dụ phát hiện một đường dẫn giờ đã trỏ đến object khác sau khi bị thay thế.

Nhưng phải tôn trọng các giới hạn.

### Giới hạn cần nhớ

1. **Có thể `null`.** Không được giả định luôn có key.
2. **Không phải ID toàn cục.** File key chỉ có ý nghĩa trong phạm vi filesystem/provider tương ứng; hai filesystem có thể phát ra các giá trị trông giống nhau.
3. **Không bảo đảm tồn tại vĩnh viễn.** Một file bị xóa có thể giải phóng ID để filesystem tái sử dụng; đừng dùng key như mã nhận diện hồ sơ lâu dài.
4. **Không gắn chặt với chuỗi path.** Đổi tên cùng filesystem có thể giữ file identity; thay file khác vào cùng pathname có thể thay `fileKey`.
5. **Không chứng minh tệp không thay đổi nội dung.** Một file có thể bị ghi lại mà key vẫn thuộc cùng đối tượng.
6. **Không phải token cấp quyền.** `fileKey` không thể thay thế xác thực, ủy quyền hay file handle được bảo vệ.
7. **Không dựa vào `toString()` của key làm chuẩn portable.** Format in ra là chi tiết implementation.
8. **Không đủ để ngăn race.** Sau khi lấy key, entry tại đường dẫn có thể bị thay thế bởi một thao tác đồng thời.

**Cần phân biệt `fileKey` với nội dung hash**: key nhận diện đối tượng do filesystem cung cấp; SHA-256 (ví dụ) nhận diện giá trị băm của **nội dung đã được đọc**. Hai file khác nhau có thể trùng nội dung và hash; cùng một file có thể thay nội dung theo thời gian trong khi key không đổi. Không dùng key để suy dữ liệu hai file giống nhau.

## 7. `Path.equals()`, `Files.isSameFile()` và `fileKey()` khác nhau

Ba câu hỏi hay bị trộn lẫn:

| API | Câu hỏi | Có nhất thiết truy cập filesystem? |
| --- | --- | --- |
| `pathA.equals(pathB)` | Hai đối tượng path có bằng nhau theo quy tắc provider không? | Không dùng làm phép kiểm tra file identity |
| `Files.isSameFile(pathA, pathB)` | Hai đường dẫn hiện nhận diện **cùng file** không? | Có thể truy vấn filesystem, có thể ném `IOException` |
| `attrsA.fileKey()` và `attrsB.fileKey()` | Provider có cấp khóa định danh và hai key có thể dùng để so sánh không? | Key đã được lấy từ các lần đọc metadata; không tạo bất biến |

Ví dụ:

```text
/data/report.txt
/data/aliases/current.txt  --(symbolic link)-->  /data/report.txt
/data/backup-hardlink.txt  --(hard link)------>  cùng đối tượng file
```

Hai `Path` có chuỗi khác nhau vẫn **có thể** đại diện cùng file thực. Trên filesystem hỗ trợ hard link, hai tên trỏ tới cùng một file object có thể có cùng `fileKey`. Một symbolic link **khi đi theo link** có thể dẫn đến cùng object và cùng key với target; **khi dùng NOFOLLOW_LINKS** thì bạn đang lấy thuộc tính và key của **chính link**, không phải target.

`Files.isSameFile(...)` thường là API thích hợp hơn để hỏi “hai path này có trỏ tới cùng file không?”. Nếu hai đối tượng `Path` **bằng nhau theo `equals`**, implementation được phép/ theo hợp đồng trả `true` ngay mà không kiểm tra file thực có tồn tại. Vì thế đừng dùng `Files.isSameFile(p, p)` để xác nhận chắc chắn `p` tồn tại; muốn kiểm tra file thực phải có thao tác khác phù hợp.

### Ví dụ 3 — file key, hard link và danh tính tệp

Chương trình sau thử tạo một **hard link** đến file tạm. Vì filesystem không phải nơi nào cũng cho tạo hard link, chương trình có hai nhánh được giải thích riêng; nó không giả định `fileKey()` luôn có giá trị.

```java
// FileKeyIdentityDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileKeyIdentityDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("key-demo-");
        Path original = directory.resolve("original.txt");
        Path alias = directory.resolve("alias.txt");

        try {
            Files.writeString(original, "same object",
                    StandardCharsets.UTF_8);

            BasicFileAttributes first = Files.readAttributes(
                    original, BasicFileAttributes.class);

            System.out.println("fileKeyAvailable="
                    + (first.fileKey() != null));

            try {
                Files.createLink(alias, original);

                BasicFileAttributes second = Files.readAttributes(
                        alias, BasicFileAttributes.class);

                System.out.println("sameFile="
                        + Files.isSameFile(original, alias));

                if (first.fileKey() != null
                        && second.fileKey() != null) {
                    System.out.println("keyEqual="
                            + first.fileKey().equals(second.fileKey()));
                } else {
                    System.out.println("keyEqual=unavailable");
                }
            } catch (IOException | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("hardLinkDemo=unavailable");
            }
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(original);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FileKeyIdentityDemo.java
java FileKeyIdentityDemo
```

Kết quả **phụ thuộc nền tảng**. Trên filesystem có hỗ trợ hard link, khi mọi thao tác thành công, phần stdout có dạng:

```text
fileKeyAvailable=true
sameFile=true
keyEqual=true
```

Trong một hệ thống cấp `fileKey` là `null` nhưng vẫn hỗ trợ hard link, nhánh này có thể là:

```text
fileKeyAvailable=false
sameFile=true
keyEqual=unavailable
```

Nếu môi trường không hỗ trợ hoặc từ chối tạo hard link:

```text
fileKeyAvailable=true
hardLinkDemo=unavailable
```

Giá trị của `fileKeyAvailable` trong nhánh cuối cũng có thể là `false`. Kết quả **không phải lời hứa stdout cố định trên mọi máy**. Chương trình đặc biệt không in đối tượng `fileKey` vì định dạng và ý nghĩa bên trong của nó không portable.

Trong trường hợp hai tên hard link đến cùng file, `Files.isSameFile()` thích hợp để kiểm tra danh tính hiện tại. So sánh hai key được đọc là thông tin hỗ trợ khi cả hai có giá trị và cùng filesystem, nhưng không thay thế xử lý lỗi và nguy cơ file bị thay đổi trong quá trình kiểm tra.

## 8. Symbolic link: đọc thuộc tính link hay target?

Đây là điểm then chốt đối với `isSymbolicLink()` và `fileKey()`.

Giả sử:

```text
report.txt                 (regular file)
report-link.txt ----------> report.txt   (symbolic link)
```

Hai cách đọc khác nhau:

```java
// Theo link: quan sát thuộc tính target.
BasicFileAttributes targetAttrs = Files.readAttributes(
        link, BasicFileAttributes.class);

// Không theo link: quan sát chính symbolic link.
BasicFileAttributes linkAttrs = Files.readAttributes(
        link, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa với `link` là `Path` đã khai báo; import `LinkOption` cùng những lớp khác.

Nếu target là regular file:

- `targetAttrs.isRegularFile()` thường là `true`.
- `targetAttrs.isSymbolicLink()` thường là `false`, vì đang nhìn **target**.
- `linkAttrs.isSymbolicLink()` là `true` khi provider nhận diện link.
- `targetAttrs.size()` tương ứng regular target (khi có thể xác định).
- `linkAttrs.size()` là thuộc tính của **link** và không nên suy bằng kích thước target.
- `fileKey` có thể phân biệt đối tượng link với đối tượng target, nếu provider cung cấp khóa.

### Ví dụ 4 — quan sát `NOFOLLOW_LINKS`, kể cả broken link

Chương trình này **thử** tạo symlink tương đối trong thư mục tạm. Một số môi trường Windows cần quyền/tính năng nhất định, một số provider không hỗ trợ symlink; khi đó chương trình báo không khả dụng thay vì khẳng định tính năng tồn tại trên mọi máy.

```java
// SymbolicLinkAttributesDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymbolicLinkAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("link-attrs-");
        Path target = dir.resolve("original.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(target, "OK", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        link, target.getFileName());

                BasicFileAttributes followed = Files.readAttributes(
                        link, BasicFileAttributes.class);
                BasicFileAttributes notFollowed = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

                System.out.println("followRegular="
                        + followed.isRegularFile());
                System.out.println("nofollowSymbolic="
                        + notFollowed.isSymbolicLink());

                Files.delete(target);

                System.out.println("brokenTargetExists="
                        + Files.exists(link));
                System.out.println("linkEntryExists="
                        + Files.exists(
                                link, LinkOption.NOFOLLOW_LINKS));
            } catch (IOException | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkDemo=unavailable");
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SymbolicLinkAttributesDemo.java
java SymbolicLinkAttributesDemo
```

Trong hệ thống hỗ trợ symbolic link và thực thi thành công mọi bước, stdout là:

```text
followRegular=true
nofollowSymbolic=true
brokenTargetExists=false
linkEntryExists=true
```

Nếu không tạo/truy vấn được link, chương trình có thể in:

```text
symlinkDemo=unavailable
```

Đây là ví dụ **có đầu ra phụ thuộc hệ thống**. Sau khi target bị xóa, `Files.exists(link)` (thường đi theo link) không thấy target, còn `Files.exists(link, NOFOLLOW_LINKS)` vẫn có thể xác nhận mục symlink còn đó. Đừng coi `Files.exists(link)==false` là đủ chứng minh bản thân link đã biến mất.

Khi một thư viện cần quy tắc “không theo symbolic link”, hãy truyền option thích hợp vào **chính thao tác có hỗ trợ** và hiểu rõ hành vi của provider. Việc kiểm tra trước với `NOFOLLOW_LINKS` không tự bảo vệ một thao tác mở sau đó khỏi thay đổi đồng thời (TOCTOU).

## 9. `fileKey` sau rename, replace, xóa và tạo lại

Một tên đường dẫn không phải danh tính bất biến của đối tượng. Có các tình huống:

| Thao tác | Pathname | File object / key có thể thế nào? |
| --- | --- | --- |
| Ghi đè nội dung trong cùng file đang mở | Path không đổi | File identity có thể giữ nguyên dù nội dung và size thay đổi |
| Rename/move trong cùng filesystem | Path đổi | Object thường được giữ, nhưng phải tôn trọng provider |
| Tạo hard link thêm tên mới | Hai path khác nhau | Có thể cùng file object và cùng key |
| Xóa file rồi tạo file mới trùng pathname | Path giống cũ | Thường là object mới; ID đã giải phóng có thể được tái sử dụng |
| Atomic replace tên đích bằng file mới | Tên đích có thể giữ nguyên | File object ở target có thể đổi; readers cũ có thể vẫn giữ handle cũ tùy OS |
| Di chuyển qua filesystem khác bằng copy/delete | Path đổi và file object có thể đổi | Key có thể đổi hoặc không so sánh trực tiếp được giữa provider |

Vì thế không nên lưu vĩnh viễn `(path, fileKey)` làm “ID duy nhất không đổi cho mọi thời đại” của dữ liệu nghiệp vụ. Nếu cần ID ổn định giữa di chuyển máy, sao lưu, phục hồi và thay thế file, ứng dụng nên tạo **định danh nghiệp vụ** riêng.

### `fileKey` có giúp phát hiện thay thế file không?

Có thể **hỗ trợ** ở một số provider. Ví dụ trước khi đọc file, lấy `fileKey` ban đầu; sau khi thực hiện một thao tác, đọc lại và so sánh. Nếu key thay đổi, đó có thể là tín hiệu file object đã bị thay thế. Nhưng:

- Nếu key là `null`, không có dữ kiện này.
- Một key có thể được tái sử dụng sau xóa/tạo mới.
- Nội dung cùng file có thể đổi mà key không đổi.
- Hai lần đọc thuộc tính không nguyên tử với thao tác của tiến trình khác.
- Chỉ so sánh `key.equals(...)` mà bỏ qua filesystem/provider là không đủ.

Do đó, phương pháp này phù hợp một số bài toán kiểm tra/giám sát có giới hạn, **không phải cơ chế khóa/authorization** cho thao tác nguy hiểm. Nếu cần chống việc thay đổi đối tượng đích giữa kiểm tra và sử dụng, hãy ưu tiên thao tác dựa trên handle/tài nguyên đã mở hoặc API filesystem bảo vệ phù hợp.

## 10. Thay đổi kích thước và metadata không phải dữ liệu bất biến

`BasicFileAttributes` là kết quả thu thập ở **một thời điểm**, không phải đối tượng tự động cập nhật khi file đổi. Nếu bạn gọi `readAttributes()` trước khi ghi, rồi giữ `attrs`, `attrs.size()` vẫn biểu diễn giá trị đã thu thập, không tự tăng theo file mới.

### Ví dụ 5 — so sánh thuộc tính cũ và mới

```java
// FileSizeSnapshotDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileSizeSnapshotDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("size-snapshot-", ".txt");

        try {
            Files.writeString(file, "A", StandardCharsets.UTF_8);
            BasicFileAttributes before = Files.readAttributes(
                    file, BasicFileAttributes.class);

            Files.writeString(file, "ABCDE", StandardCharsets.UTF_8);
            BasicFileAttributes after = Files.readAttributes(
                    file, BasicFileAttributes.class);

            System.out.println("oldSize=" + before.size());
            System.out.println("newSize=" + after.size());
            System.out.println("currentSize=" + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac FileSizeSnapshotDemo.java
java FileSizeSnapshotDemo
```

Stdout khi thao tác với regular file tạm thành công:

```text
oldSize=1
newSize=5
currentSize=5
```

`Files.writeString(file, text, UTF_8)` không có option bổ sung, nên với file đã có nó ghi dữ liệu theo các tùy chọn mặc định bao gồm truncate nội dung trước đó. `before` vẫn giữ kích thước cũ. Sự chênh lệch có thể xuất hiện khi một chương trình khác thay đổi file, hoặc khi một stream writer còn chứa dữ liệu trong bộ đệm.

Quan trọng: dù đọc `BasicFileAttributes` một lần có thể tiện hơn nhiều lời gọi thuộc tính riêng, nó cũng **không bảo đảm đọc một snapshot bất biến của hệ thống tệp trong toàn bộ vòng đời ứng dụng**.

## 11. Quyền truy cập và exception trong việc đọc metadata

`Files.readAttributes()` có thể thất bại vì file không còn tồn tại, thiếu quyền truy cập, mount/provider lỗi hoặc những điều kiện khác. Một mẫu xử lý phù hợp:

```java
// Mã minh họa, path là Path được cung cấp bởi caller.
try {
    BasicFileAttributes attrs = Files.readAttributes(
            path, BasicFileAttributes.class);

    if (attrs.isRegularFile()) {
        System.out.println("Size in bytes: " + attrs.size());
    } else {
        System.out.println("Not a regular file");
    }
} catch (NoSuchFileException ex) {
    System.out.println("Path missing at metadata read time");
} catch (AccessDeniedException ex) {
    System.out.println("Cannot read attributes due to access restrictions");
} catch (IOException ex) {
    System.out.println("Other I/O failure: " + ex.getMessage());
}
```

Mã trên **không độc lập**, cần import và phạm vi phương thức phù hợp. Các subtype được minh họa là tình huống thường gặp, nhưng một provider có thể ném `IOException` tổng quát cho một số loại lỗi. Nếu ứng dụng không có quyền hoặc file bị xóa sau khi đọc attributes, vẫn cần xử lý lỗi **khi mở/đọc thật**.

`Files.exists(path)` hoặc `Files.isRegularFile(path)` trả boolean hữu ích nhưng có thể không phân biệt đầy đủ “không tồn tại” với “không thể xác định”. Đặc biệt, `Files.exists(path)==false` và `Files.notExists(path)==false` **có thể cùng xảy ra** nếu filesystem không thể xác định trạng thái. Khi cần nguyên nhân lỗi để hiển thị cho người dùng hoặc retry, một thao tác `Files.readAttributes(...)` có exception thường phù hợp hơn chỉ dựa vào boolean.

### Quyền và loại file không phải một vấn đề

Một regular file có thể **không đọc được**; một symbolic link có thể dẫn đến target bị hạn chế; một thư mục có thể tồn tại nhưng không thể liệt kê. Việc nhận diện `isRegularFile()==true` không có nghĩa `Files.newInputStream(path)` chắc chắn thành công.

Với các hệ thống nhiều người dùng, metadata là dữ kiện **của hệ thống tệp**, không phải chính sách phân quyền nghiệp vụ. Không dùng `fileKey` làm bearer token hoặc chứng cứ cho phép truy cập; thao tác thật phải đi qua cơ chế authorization đúng.

## 12. Phân loại số lượng file trong thư mục và vai trò `fileKey`

Khi tính dung lượng hoặc thống kê file trong một cây thư mục, `fileKey` có thể giúp tránh **đếm trùng cùng một đối tượng** trong các hệ thống hỗ trợ hard link. Nhưng cần phân biệt hai kiểu bài toán:

- **Đếm đường dẫn/entry**: một file có hai hard link xuất hiện dưới hai tên, đếm thành hai **entry**.
- **Đếm đối tượng file khác nhau**: hai hard link có thể được coi một đối tượng và một kích thước logical, nhưng cách xử lý phải nhất quán.
- **Dung lượng cấp phát trên đĩa**: việc cộng logical `size()` không trả lời chính xác vì sparse files, nén, metadata và chính sách cấp phát.
- **Duyệt theo symlink**: nếu đi theo symlink, một đối tượng có thể được ghé nhiều lần và có thể gặp vòng liên kết.

Vì `fileKey()` có thể `null`, thuật toán đếm/khử trùng lặp cần **fallback**; không chỉ lưu `null` vào `Set` rồi kết luận mọi file thiếu key là một đối tượng. Các cách thay thế còn tùy mục tiêu: so sánh danh tính bằng `Files.isSameFile()` (có chi phí và exception), không đi theo link, hoặc đơn giản là đếm entries thay vì file objects.

Trong `Files.walkFileTree(...)`, lựa chọn **có theo symbolic link** hay không ảnh hưởng cách phân loại/duyệt và quản lý vòng lặp; không dùng `fileKey` tách rời hợp đồng của `FileVisitOption.FOLLOW_LINKS` rồi giả định an toàn với mọi provider.

## 13. Chọn cách lấy metadata phù hợp

| Bài toán | API gợi ý | Lưu ý |
| --- | --- | --- |
| Chỉ cần kích thước một regular file | `Files.size(path)` | Byte, có thể ném `IOException` |
| Cần size + type + identity provider | `Files.readAttributes(path, BasicFileAttributes.class)` | Gom thông tin, `fileKey()` có thể null |
| Cần metadata **của link** | `readAttributes(..., NOFOLLOW_LINKS)` | Khác metadata target |
| Hỏi “có phải symbolic link?” | `Files.isSymbolicLink(path)` | Không đồng nghĩa “target tồn tại” |
| Hỏi “có phải regular file?” | `Files.isRegularFile(path, options...)` | Có thể trả false khi không xác định |
| Hỏi hai path trỏ cùng file? | `Files.isSameFile(pathA, pathB)` | Có thể ném `IOException`, và có shortcut khi `Path.equals` |
| Hỏi tệp có quyền POSIX nào? | `Files.getPosixFilePermissions(...)` nếu hỗ trợ | Khác BasicFileAttributes, phụ thuộc provider |
| Hỏi owner/ACL | `FileOwnerAttributeView`, `AclFileAttributeView` khi hỗ trợ | Không mặc định có trên mọi filesystem |
| Muốn kích thước cây thư mục | Duyệt tree, thống nhất quy tắc cộng kích thước | Không dùng `size(directory)` |
| Muốn nhận biết thay đổi nội dung | Đọc dữ liệu và hash hoặc cơ chế version cụ thể | `fileKey` không phải content hash |
| Muốn bảo đảm mở file đúng quyền | Thực hiện thao tác mở theo contract và bắt exception | Không chỉ `isRegularFile()` rồi tin trạng thái không đổi |

Nếu cần thuộc tính nâng cao ngoài nhóm basic, Java có các file-attribute views như `PosixFileAttributes`, `DosFileAttributes`, `AclFileAttributeView`. Những API này **không phải phần bảo đảm của mọi provider** và có thể ném `UnsupportedOperationException` khi tính năng không có.

## 14. Các lỗi dễ mắc

| Hiểu lầm / lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `size()` trả số ký tự | Kích thước regular file là byte | Phân biệt UTF-8, UTF-16 và code point |
| Dùng `size(directory)` để tính dung lượng thư mục | Giá trị của thư mục không được xác định nhất quán | Duyệt tree, quy định rõ link/hard link |
| Coi `File.length()==0` chắc là file rỗng | File không tồn tại cũng có thể cho 0 | Kiểm tra loại, thực hiện truy vấn có báo lỗi |
| Coi `isRegularFile()==false` nghĩa là directory | Còn symlink, special file, metadata không xác định | Kiểm tra từng loại và xử lý lỗi |
| Dùng `isOther()` để kiểm tra file missing | `isOther()` nói về loại đối tượng, không phải sự vắng mặt | Bắt lỗi `NoSuchFileException`/`IOException` |
| Đọc link không có `NOFOLLOW_LINKS` rồi kết luận đây là symlink | Mặc định có thể lấy thuộc tính target | Chỉ định `NOFOLLOW_LINKS` khi hỏi về link |
| Giả định `fileKey()` luôn có | Có thể trả `null` | Thiết kế fallback |
| Cast `fileKey()` sang `long`, lưu lâu dài như ID toàn cục | Kiểu là `Object`, ý nghĩa tùy provider, có thể tái sử dụng | Dùng đúng phạm vi và ID nghiệp vụ riêng |
| Dùng `key.toString()` làm định dạng trao đổi portable | Implementation tùy filesystem | Không phụ thuộc định dạng key |
| Dùng `fileKey` để phát hiện thay đổi nội dung | Một file thay dữ liệu có thể giữ nguyên identity | Hash/version dữ liệu theo yêu cầu |
| Đồng nhất `Path.equals()` với `Files.isSameFile()` | So sánh đường dẫn khác kiểm tra object | Chọn API theo câu hỏi |
| Lấy attributes một lần rồi giả định không bao giờ đổi | File có thể bị thay thế hoặc ghi sau đó | Xử lý snapshot/race và thao tác thật |
| Cộng mọi `attrs.size()` qua hard link | Có thể đếm trùng cùng file object | Quyết định thống kê entry hay object |
| Coi `Files.exists()==false` là chắc chắn file không tồn tại | Trạng thái đôi khi không xác định | Phân biệt `notExists` và exception khi truy vấn |
| Tin kiểm tra metadata có thể cấp quyền đọc | Metadata không thay thế authorization | Mở file và xử lý permission/I/O |

## 15. Bài tập thực hành

### Bài tập 1 — bảng phân loại

Viết chương trình tạo một file trống và một thư mục tạm. Đọc `BasicFileAttributes` của mỗi đường dẫn rồi hiển thị `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`. Giải thích tại sao **cờ `isOther` không đại diện cho đường dẫn không tồn tại**.

**Gợi ý:** Với file không tồn tại, thử `Files.readAttributes()` và bắt `NoSuchFileException`; không giả vờ nhận được một object attributes hợp lệ.

### Bài tập 2 — Unicode và số byte

Ghi `"A😀"` dưới dạng UTF-8, so `Files.size()`, `attrs.size()`, `String.length()` và `codePointCount(...)`. Sau đó ghi nội dung UTF-8 khác để thấy file size thay đổi theo số byte thực tế.

**Gợi ý:** Kích thước `"A😀"` khi ghi UTF-8 là **5 byte**, không phải 2 hoặc 3.

### Bài tập 3 — hard link

Nếu filesystem hỗ trợ, tạo hai đường dẫn hard link cùng một object. So sánh `Path.equals`, `Files.isSameFile`, `fileKey` (chỉ khi khác `null`). Vì sao chỉ một trong những phép này phản ánh chắc chắn **câu hỏi identity tại thời điểm truy vấn**?

**Gợi ý:** Hai tên khác nhau cho cùng object không làm hai `Path` có cùng cấu trúc.

### Bài tập 4 — symlink

Tạo một symlink trỏ tới regular file nếu quyền/provider cho phép. So sánh `Files.readAttributes` khi theo link và không theo link. Xóa target (giữ link), kiểm tra `Files.exists` với và không với `NOFOLLOW_LINKS`. Không lấy size link làm size file target.

### Bài tập 5 — thiết kế thống kê

Bạn được yêu cầu “tính tổng dung lượng các file trong một thư mục”. Trước khi viết vòng duyệt, giải thích cần làm rõ điều gì về: recursive hay một cấp, đi theo symbolic link, hard link được đếm mấy lần, lỗi quyền truy cập, file thay đổi đồng thời, logical bytes so với allocated bytes.

## 16. Câu hỏi tự kiểm tra

**1.** `Files.size(path)` và `BasicFileAttributes.size()` của regular file trả đơn vị gì?

**Đáp án:** **Byte**, kiểu `long`, không phải `char` UTF-16 hay Unicode code point.

**2.** `isRegularFile()==false` có chắc `isDirectory()==true` không?

**Đáp án:** Không. Có các loại khác như symbolic link và other file types; cũng phải xét việc bạn đang theo link hay không.

**3.** Dùng `size(directory)` để biết tổng dung lượng file bên trong có đúng không?

**Đáp án:** Không. Size của directory không được quy định nhất quán và không phải tổng size file con.

**4.** `fileKey()` có luôn là một số nguyên khác `null` không?

**Đáp án:** Không. Kiểu trả về là `Object` và có thể là `null`; representation do provider quyết định.

**5.** Nếu hai đường dẫn có `Path.toString()` khác nhau, chúng có thể trỏ cùng file không?

**Đáp án:** Có. Hard link, symbolic link hoặc cách đặt tên khác có thể dẫn đến cùng file thực.

**6.** Muốn hỏi về **mục symlink**, truyền tùy chọn gì khi đọc attributes?

**Đáp án:** `LinkOption.NOFOLLOW_LINKS` vào `Files.readAttributes(...)`.

**7.** Một symbolic link đã mất target thì `Files.exists(link)` và `Files.exists(link, NOFOLLOW_LINKS)` nhất thiết bằng nhau?

**Đáp án:** Không. Theo link có thể báo target không tồn tại; không theo link có thể xác nhận chính link vẫn còn.

**8.** File được sửa nội dung nhưng không bị thay thế object. `fileKey` nhất thiết đổi không?

**Đáp án:** Không. File identity và content khác nhau.

**9.** Vì sao không nên lưu `fileKey` lâu dài làm ID toàn cầu?

**Đáp án:** Nó không được bảo đảm trên mọi provider, không duy nhất giữa filesystem, có thể bị tái sử dụng và không phải ID nghiệp vụ ổn định.

**10.** `Files.isSameFile(p, p)` trả `true` có chứng minh `p` tồn tại?

**Đáp án:** Không nhất thiết. API có thể trả `true` ngay khi hai `Path` bằng nhau mà không truy vấn filesystem.

**11.** Sau khi gọi `Files.readAttributes`, một tiến trình khác có thể xóa/thay file trước khi bạn mở nó không?

**Đáp án:** Có. Metadata là thông tin tại thời điểm truy vấn, không loại bỏ race. Phải xử lý lỗi của thao tác thật.

**12.** Khi đếm file trong cây có hard link và symlink, tại sao phải thống nhất chính sách trước?

**Đáp án:** Một object có thể xuất hiện qua nhiều path. Đếm entries, logical file objects và allocated disk usage là những phép tính có ý nghĩa khác nhau.

**Tóm tắt:** Với Java NIO.2, `BasicFileAttributes` giúp lấy **kích thước byte**, **loại đối tượng tệp** và **fileKey** do provider cung cấp. Chú ý `NOFOLLOW_LINKS` khi muốn hỏi về symbolic link thay vì target; không dùng size directory để suy tổng dung lượng; không coi `fileKey` là ID toàn cầu hoặc content hash. Sử dụng `Files.isSameFile()` khi cần kiểm tra identity hiện tại và xử lý `IOException`/TOCTOU ở mọi thao tác thực tế.

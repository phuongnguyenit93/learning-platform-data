# Đọc metadata tệp bằng `BasicFileAttributes` trong Java

## 1. Tại sao cần đọc thuộc tính tệp?

Trong chương trình Java, không phải lúc nào ta cũng cần đọc **nội dung** của tệp. Nhiều tác vụ chỉ cần biết:

- Một đường dẫn đang chỉ tới **tệp thông thường**, **thư mục**, **symbolic link** hay một loại đối tượng khác?
- Kích thước dữ liệu được báo cáo là bao nhiêu **byte**?
- Tệp được sửa lần cuối khi nào? Hệ thống tệp có thể cung cấp thời điểm truy cập và tạo tệp không?
- Có một định danh tệp do file-system provider cung cấp hay không?
- Khi duyệt hàng nghìn mục, có thể lấy nhiều thông tin cơ bản bằng **một lần yêu cầu thuộc tính** thay vì gọi nhiều helper riêng lẻ không?

Java NIO.2 cung cấp interface **`java.nio.file.attribute.BasicFileAttributes`** và phương thức **`Files.readAttributes`** để truy vấn metadata của một đối tượng trong hệ thống tệp:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

Path path = Path.of("data", "report.bin");
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
```

Đây là **đoạn minh họa trong một phương thức có xử lý `IOException`**. `Path.of` có từ Java 11; nếu cần tương thích cú pháp với Java 7, dùng `Paths.get("data", "report.bin")`. Các API `BasicFileAttributes` và `Files.readAttributes(Path, Class, LinkOption...)` đã có từ **Java 7** và vẫn là API hiện hành trong Java hiện đại.

**Điểm cốt lõi:** `Path` là giá trị biểu diễn một vị trí; `BasicFileAttributes` chứa thông tin quan sát được từ **file system tại lúc truy vấn**, không phải nội dung tệp và cũng không phải lời đảm bảo đối tượng ấy sẽ giữ nguyên sau đó.

Bài học tập trung đúng phạm vi **đọc metadata bằng `BasicFileAttributes`**: cách lấy dữ liệu, ý nghĩa từng trường, ảnh hưởng của symbolic link, tính khả chuyển và lỗi thường gặp; ví dụ Java 17+ có thể chạy trực tiếp và được kiểm thử.

## 2. Bốn thành phần cần phân biệt

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Path` | Giá trị đường dẫn thuộc một `FileSystem` | `Path.of("data", "a.bin")` |
| `Files` | Các phương thức truy cập, tạo, đọc, ghi, xóa và truy vấn thuộc tính | `Files.readAttributes(...)` |
| `BasicFileAttributes` | Interface **chỉ đọc** biểu diễn những thuộc tính tệp cơ bản | `attrs.size()`, `attrs.lastModifiedTime()` |
| `FileSystem` / provider | Quy tắc hệ thống tệp: đường dẫn, symbolic link, độ chính xác thời gian, khả năng cung cấp metadata | Hệ thống tệp mặc định hoặc provider khác |

Lời gọi:

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
```

**có thực hiện I/O metadata**; tệp có thể không tồn tại hoặc không cho phép truy cập, nên phương thức có thể ném `IOException`. Ngược lại, `Path.of("data", "a.bin")` chỉ tạo một giá trị đường dẫn, không tự tạo file và không tự đọc metadata.

`BasicFileAttributes` không có các phương thức ghi nội dung hoặc cập nhật tất cả thuộc tính. Bạn không thể gọi `attrs.setSize(...)` hay thay đổi giá trị `attrs.lastModifiedTime()` để sửa file. Nếu cần đặt thời điểm sửa, có API riêng như `Files.setLastModifiedTime` và các file-attribute view phù hợp, chịu khả năng hỗ trợ của provider.

### 2.1. Metadata không phải nội dung

Một tệp ảnh có thể có:

```text
name: avatar.png
type: regular file
size: 12345 bytes
lastModifiedTime: 2026-...
content: [các byte nhị phân của ảnh]
```

`BasicFileAttributes` cung cấp loại tệp, độ dài và timestamp, **không cung cấp mảng byte của ảnh**. Nếu cần nội dung nhỏ có giới hạn, có thể dùng `Files.readAllBytes`; với nội dung lớn, dùng stream. Hai nhóm thao tác có ý nghĩa và chi phí khác nhau.

### 2.2. Metadata được xác định theo hệ thống tệp

Cùng một giao diện `BasicFileAttributes` có thể lấy thông tin từ file system nội bộ, ổ đĩa gắn ngoài, network share hoặc provider khác. Không giả định mọi hệ thống đều hỗ trợ **creation time thật**, cùng độ chính xác timestamp hay cùng định dạng file key.

## 3. Lời gọi `Files.readAttributes` theo kiểu dữ liệu

Cách đọc phổ biến nhất:

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
```

Cần có:

- `path`: đối tượng `Path` mà ta muốn quan sát.
- `BasicFileAttributes.class`: chọn kiểu interface thuộc tính cơ bản.
- Tham số `LinkOption...` tùy chọn: quy định có theo symbolic link không; mặc định **theo symbolic link** khi áp dụng.

Khai báo phương thức đầy đủ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

static BasicFileAttributes readBasic(Path path) throws IOException {
    return Files.readAttributes(path, BasicFileAttributes.class);
}
```

Đây là **phương thức Java đầy đủ để đặt trong một lớp**. Nó không bắt rồi nuốt `IOException`, nên tầng gọi quyết định có retry, báo lỗi, bỏ qua mục tùy chọn hoặc dừng tác vụ.

### 3.1. Vì sao chọn `BasicFileAttributes.class`?

Kiểu trả về là một object triển khai interface `BasicFileAttributes`. Bạn có thể truy cập các phương thức chuẩn với **kiểm tra kiểu lúc biên dịch**:

```java
long bytes = attrs.size();
boolean isFile = attrs.isRegularFile();
boolean isDir = attrs.isDirectory();
```

Đó là API **typed**. Ngoài ra, `Files.readAttributes(path, "basic:size,lastModifiedTime")` có overload nhận chuỗi tên thuộc tính và trả `Map<String,Object>`. Overload chuỗi hữu ích khi cần chọn trường động, nhưng phải xử lý key/type runtime. Với tác vụ cần **nhóm thuộc tính cơ bản**, overload kiểu `BasicFileAttributes.class` thường rõ ràng và ít lỗi ép kiểu hơn.

### 3.2. Đọc nhiều trường không bảo đảm snapshot nguyên tử

`Files.readAttributes` có thể giảm việc tự gọi từng API riêng, nhưng **không có lời bảo đảm tuyệt đối rằng mọi trường được đọc nguyên tử cùng một thời điểm** trên mọi provider. Một tiến trình khác có thể đang sửa file, và việc đọc có thể dùng nhiều thao tác bên dưới tùy hệ thống.

Vì vậy:

- “Tôi đã đọc attrs” **không đồng nghĩa** “file được khóa lại”.
- `attrs.size()` là giá trị quan sát trong lần đọc, không phải kích thước mãi về sau.
- Metadata trong object `attrs` không tự cập nhật khi file thay đổi.
- Nếu cần trạng thái mới, gọi lại `Files.readAttributes` hoặc dùng cơ chế đồng bộ/snapshot phù hợp.

## 4. Các phương thức của `BasicFileAttributes`

Interface cung cấp nhóm phương thức chuẩn sau:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `isRegularFile()` | `boolean` | Đối tượng được nhận diện là **tệp thông thường** |
| `isDirectory()` | `boolean` | Đối tượng được nhận diện là **thư mục** |
| `isSymbolicLink()` | `boolean` | Đối tượng được nhận diện là **symbolic link** |
| `isOther()` | `boolean` | Đối tượng thuộc một dạng khác không phải ba loại thông dụng ở trên |
| `size()` | `long` | Kích thước được file system báo cáo, **đơn vị byte** |
| `lastModifiedTime()` | `FileTime` | Thời điểm sửa cuối theo provider |
| `lastAccessTime()` | `FileTime` | Thời điểm truy cập cuối theo provider |
| `creationTime()` | `FileTime` | Thời điểm tạo theo provider hoặc giá trị thay thế khi không hỗ trợ |
| `fileKey()` | `Object` | Định danh tệp do provider cung cấp, có thể `null` |

Đây là metadata **cơ bản**. Những thuộc tính như owner, POSIX permissions, ACL hoặc quyền đọc/ghi theo hệ điều hành **không phải phương thức của `BasicFileAttributes`**; muốn lấy chúng phải dùng những view/API phù hợp khi provider hỗ trợ.

### 4.1. Đọc loại tệp

```java
if (attrs.isRegularFile()) {
    System.out.println("regular file");
} else if (attrs.isDirectory()) {
    System.out.println("directory");
} else if (attrs.isSymbolicLink()) {
    System.out.println("symbolic link");
} else if (attrs.isOther()) {
    System.out.println("other filesystem entry");
}
```

Đây là đoạn minh họa khi biến `attrs` đã được đọc. Đừng suy ra rằng chỉ cần phần mở rộng `.txt` hay `.jpg` là có tệp thông thường; tên tệp không quyết định loại đối tượng.

**Quan trọng:** Với chế độ **mặc định theo symbolic link**, `attrs.isRegularFile()` có thể là `true` khi `path` chỉ một symlink tới tệp thường. Muốn hỏi **chính entry link**, dùng `NOFOLLOW_LINKS` (mục 7).

### 4.2. Kích thước theo byte

```java
long bytes = attrs.size();
```

`size()` trả số byte được hệ thống tệp báo cho entry, không phải số ký tự của chuỗi Java và không phải lượng bộ nhớ của object `Path`.

Với **tệp thông thường**, kết quả thường là kích thước tệp tính bằng byte. Đối với **directory**, **symbolic link khi không theo link** hoặc những file type đặc biệt, giá trị có thể không mang ý nghĩa “số byte nội dung có thể đọc tuần tự”, và tính chính xác phụ thuộc file system/provider. Không dùng `attrs.size()` của mọi loại entry như một lượng payload đáng tin.

### 4.3. Metadata thời gian

```java
java.nio.file.attribute.FileTime modified =
        attrs.lastModifiedTime();
java.nio.file.attribute.FileTime accessed =
        attrs.lastAccessTime();
java.nio.file.attribute.FileTime created =
        attrs.creationTime();
```

Ba phương thức trả các object `FileTime`, **không** phải `java.util.Date`. Không dùng `Date` cũ khi không cần; trên Java hiện đại, `FileTime.toInstant()` giúp làm việc với `java.time.Instant`.

Điều cần lưu ý: hệ thống tệp có thể **không hỗ trợ** thời gian truy cập/tạo hoặc chỉ hỗ trợ độ phân giải giới hạn. Khi không hỗ trợ, provider có thể trả **giá trị mặc định hoặc thay thế**; `creationTime()` không phải bằng chứng đáng tin tuyệt đối về thời điểm người dùng “tạo file” trên mọi thiết bị.

### 4.4. Định danh file từ provider

```java
Object key = attrs.fileKey();
if (key != null) {
    System.out.println("provider supplied a file key");
}
```

`fileKey()` trả một `Object` theo provider, **có thể là `null`**. Không ép cố định sang `Long`/`String` hay lưu `key.toString()` làm mã ID đa nền tảng.

File key có thể hữu ích để hỗ trợ phân biệt đối tượng hoặc phát hiện vòng trong một số cách duyệt file system. Nhưng nó không phải UUID toàn cầu, không đảm bảo tồn tại, không phải mã nghiệp vụ của tài liệu, và có thể thay đổi hoặc được tái sử dụng khi đối tượng bị xóa/thay thế.

## 5. Bài toán thực tế: byte, UTF-16 và Unicode code point khác nhau

Một ví dụ có thể làm lộ sai lầm khi dùng `String.length()` làm kích thước tệp.

Giả sử nội dung là `A😀B`, được ghi bằng UTF-8. Nó có:

- **3 Unicode code point:** `A`, biểu tượng mặt cười, `B`.
- **4 đơn vị UTF-16** trong `String.length()` của Java (emoji dùng một cặp surrogate).
- **6 byte UTF-8** trên đĩa: `A` = 1 byte, emoji = 4 byte, `B` = 1 byte.

```java
import java.nio.charset.StandardCharsets;

String content = "A\uD83D\uDE00B";
int units = content.length();                        // 4
int points = content.codePointCount(0, units);       // 3
int utf8Bytes = content.getBytes(StandardCharsets.UTF_8).length; // 6
```

Đây là đoạn minh họa có thể đặt trong phương thức. Khi nội dung đó được ghi **chính xác** bằng UTF-8 mà không có header bổ sung hoặc byte khác, `BasicFileAttributes.size()` của file mới tạo sẽ báo **6 byte** trên provider thông thường.

### Vì sao dùng `long`?

Tệp có thể lớn hơn giới hạn `int`. `size()` trả `long`, giúp mô tả những kích thước lớn mà không tràn kiểu `int`. Nhưng điều đó **không có nghĩa** mọi tệp lớn có thể đọc vào một `byte[]`; mảng Java vẫn có giới hạn kích thước và bộ nhớ.

Với nội dung lớn, dùng streaming hoặc file-channel phù hợp; không gọi `Files.readAllBytes` trên file nhiều gigabyte chỉ vì `size()` chứa được giá trị lớn.

### Kích thước logic và kích thước đã chiếm trên ổ đĩa

`attrs.size()` không phải cách chuẩn để hỏi chính xác **số block vật lý chiếm trên ổ**; filesystem có thể nén, dùng sparse file, dedup hoặc cơ chế phân bổ khác. Cần tách:

- **Kích thước logic theo byte:** quan sát qua `BasicFileAttributes.size()`.
- **Dung lượng lưu trữ thực tế:** phụ thuộc filesystem, không được suy trực tiếp từ `size()`.
- **Độ dài văn bản/chuỗi:** phụ thuộc encoding và cách đếm ký tự.

## 6. `FileTime`: đọc thời gian sửa, truy cập và tạo

### 6.1. `lastModifiedTime()`

`lastModifiedTime()` mô tả thời điểm lần sửa cuối theo metadata mà provider trả về. Dùng khi ứng dụng cần hiển thị “sửa lần cuối”, lập chỉ mục sơ bộ hoặc quyết định có nên kiểm tra lại một file.

```java
import java.time.Instant;
import java.nio.file.attribute.BasicFileAttributes;

static Instant modifiedInstant(BasicFileAttributes attrs) {
    return attrs.lastModifiedTime().toInstant();
}
```

Đây là **phương thức hoàn chỉnh đặt trong lớp**. `Instant` mô tả một mốc thời gian, không phụ thuộc múi giờ hiển thị. Khi cần hiển thị giờ địa phương, dùng `ZoneId` và formatter ở tầng giao diện; đừng giả định chuỗi in ra của timestamp sẽ giống nhau nếu file được tạo vào các thời điểm khác nhau.

### 6.2. `lastAccessTime()`

`lastAccessTime()` là thời điểm truy cập cuối **nếu hệ thống hỗ trợ và cập nhật**. Một số file system hoặc cấu hình tối ưu hiệu năng có thể trì hoãn/giới hạn cập nhật access time. Vì vậy không thể kết luận “file chưa từng được truy cập” chỉ vì giá trị không thay đổi trong bài kiểm tra ngắn.

### 6.3. `creationTime()`

`creationTime()` biểu diễn thời điểm tạo **khi provider hỗ trợ**. Không phải filesystem nào cũng ghi nhận timestamp tạo theo cùng ý nghĩa; Java có thể nhận giá trị thay thế theo hợp đồng. Sao chép hoặc khôi phục file từ backup cũng có thể làm thay đổi các thời điểm theo cách không giống kỳ vọng của người dùng.

**Không thiết kế quy tắc pháp lý/nghiệp vụ quan trọng chỉ dựa vào `creationTime()` của filesystem.** Nếu ứng dụng cần thời điểm tạo một bản ghi nghiệp vụ, thường nên lưu trường `createdAt` riêng trong cơ sở dữ liệu đáng tin cùng quy trình ghi nhận được kiểm soát.

### 6.4. Độ phân giải và cách so sánh

Hai tệp được ghi gần nhau không nhất thiết có hai timestamp khác nhau: provider có thể làm tròn hoặc chỉ ghi đến một độ phân giải nhất định. Khi cập nhật file, một lần `lastModifiedTime()` mới cũng không phải cơ chế phát hiện mọi thay đổi nội dung 100%.

Để kiểm tra nội dung một cách chính xác hơn, hãy cân nhắc so byte, hash/digest và quy trình đọc nhất quán; **kích thước + timestamp** thường chỉ là heuristic để bỏ qua công việc không cần thiết trong cache/indexer, không phải chữ ký xác thực nội dung.

### 6.5. Không tự sửa metadata chỉ bằng object đã đọc

`BasicFileAttributes` là giao diện **đọc**. `FileTime` được trả là giá trị thông tin; việc tính toán `modified.toInstant()` hay giữ tham chiếu trong chương trình **không cập nhật file**.

Khi thực sự cần thay thời điểm sửa cuối:

```java
Files.setLastModifiedTime(path,
        java.nio.file.attribute.FileTime.fromMillis(0L));
```

Đây là minh họa trong phương thức khai báo `throws IOException`; chỉ dùng trên **file do ứng dụng được phép sửa**. File system có thể có độ phân giải/giới hạn timestamp khác nhau, và việc đặt thời gian cũng có thể bị từ chối. Không sửa metadata của file người dùng chỉ để “kiểm tra API”.

## 7. Symbolic link: mặc định theo link hay đọc chính link?

Câu hỏi “đây là file hay symlink?” không thể trả lời đúng nếu bỏ qua **`LinkOption`**.

### 7.1. Mặc định: theo symbolic link khi áp dụng

```java
BasicFileAttributes followed =
        Files.readAttributes(path, BasicFileAttributes.class);
```

Khi `path` là symbolic link hợp lệ trỏ tới một file thường, mặc định `followed` có thể cung cấp thuộc tính **đối tượng đích**, và `followed.isRegularFile()` là `true`. Không nên mặc định `followed.isSymbolicLink()` cũng sẽ là `true` chỉ vì **đường dẫn** ban đầu đi qua symlink.

### 7.2. Không theo symbolic link: `NOFOLLOW_LINKS`

```java
import java.nio.file.LinkOption;

BasicFileAttributes linkItself =
        Files.readAttributes(path, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);
```

Ở đây provider được yêu cầu đọc thuộc tính **chính entry symbolic link** khi đường dẫn đại diện một link. Nếu là symbolic link thông thường, `linkItself.isSymbolicLink()` có thể là `true`.

| Tình huống | Đọc mặc định | Đọc với `NOFOLLOW_LINKS` |
| --- | --- | --- |
| `path` là file thường | Thuộc tính file | Thuộc tính file |
| `path` là directory bình thường | Thuộc tính directory | Thuộc tính directory |
| `path` là symlink tới file | Thường thuộc tính file đích | Thường thuộc tính link |
| `path` là symlink tới directory | Thường thuộc tính directory đích | Thường thuộc tính link |
| `path` là symlink đứt (target thiếu) | Có thể thất bại do không có target | Có thể đọc được chính link nếu provider hỗ trợ |

**Không mặc định mọi OS có quyền tạo symbolic link hoặc mọi file-system provider hỗ trợ cùng hành vi.** Trên một số môi trường, tạo symlink cần quyền cụ thể; vì vậy chương trình chạy độc lập ở mục 12 không ép tạo symlink để giữ kiểm thử ổn định.

### 7.3. Kích thước symlink không phải kích thước file đích

Khi dùng `NOFOLLOW_LINKS`, `size()` của symbolic link (nếu được provider báo) có thể là kích thước biểu diễn của link, **không phải dung lượng nội dung file mà link trỏ đến**. Đừng dùng size đó để làm quota cho nội dung target khi mở theo link sau đó.

### 7.4. Bảo mật: `NOFOLLOW_LINKS` khi đọc metadata không phải sandbox hoàn chỉnh

Một lời gọi:

```java
BasicFileAttributes checked =
        Files.readAttributes(candidate, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);
```

chỉ quan sát metadata của đối tượng tại thời điểm gọi. Nó **không khóa** đối tượng. Nếu tiến trình khác có quyền thay đổi directory/link giữa lần kiểm tra và lần mở file, hệ thống vẫn có rủi ro *time-of-check to time-of-use* (TOCTOU). Khi path đến từ dữ liệu không tin cậy, cần thiết kế kiểm soát root, quyền, symlink, cơ chế mở file và mô hình đe dọa; không xem một phép kiểm tra metadata là bảo vệ toàn diện.

## 8. `fileKey()`: có giá trị nhưng không phải ID nghiệp vụ

`BasicFileAttributes.fileKey()` trả về một object mà **file-system provider** dùng để mô tả định danh file, hoặc trả `null` khi không có key phù hợp.

```java
Object key = attrs.fileKey();
if (key == null) {
    System.out.println("No provider file key");
} else {
    System.out.println("Provider key present");
}
```

Đoạn này minh họa trong phương thức có `attrs`.

Một số hệ thống có thể dùng các thành phần như device/inode hoặc file ID nội bộ; nhưng code ứng dụng **không được ép giá trị tới kiểu riêng của provider** để phát triển logic chung cho mọi OS.

### Những điều không được suy ra từ file key

- Không khẳng định nó **luôn khác `null`**.
- Không khẳng định mọi file trong mọi provider có key **duy nhất vĩnh viễn**.
- Không khẳng định key không đổi sau khi file bị xóa rồi tạo lại cùng tên.
- Không dùng `key.toString()` làm ID bất biến qua chuyển máy/backup/storage.
- Không dùng fileKey thay cho cơ chế phân quyền hoặc nhận dạng file đáng tin trong mọi tình huống.

Nếu yêu cầu là “hai đường dẫn hiện đang trỏ cùng tệp?” và được phép truy cập file system, `Files.isSameFile(a,b)` phù hợp hơn việc tự so file key không biết quy tắc provider. `Files.isSameFile` có thể thực hiện I/O và ném `IOException`; kết quả của nó cũng chỉ gắn với trạng thái tại thời điểm kiểm tra.

### Tại sao fileKey vẫn hữu ích?

Trong công cụ duyệt cây có symbolic link, file key có thể hỗ trợ nhận biết một directory đã gặp trong lượt quét; một số implementation traversal dùng thông tin tương đương để phát hiện vòng. Tuy nhiên, khi key thiếu, cần cơ chế/chiến lược khác. Đừng mặc định `fileKey` luôn giải quyết được toàn bộ bài toán vòng liên kết hoặc tính nhất quán của một lượt scan.

## 9. So sánh `readAttributes` với `Files.size`, `isRegularFile` và `getLastModifiedTime`

Java có những helper để đọc nhanh **một** thuộc tính:

```java
long size = Files.size(path);
boolean regular = Files.isRegularFile(path);
java.nio.file.attribute.FileTime modified =
        Files.getLastModifiedTime(path);
```

Các câu lệnh là mã minh họa có `path` kiểu `Path` và xử lý `IOException` khi cần.

| Nhu cầu | API thuận tiện | Cẩn trọng |
| --- | --- | --- |
| Chỉ cần kích thước một file | `Files.size(path)` | Có thể lỗi I/O; giá trị là quan sát hiện tại |
| Chỉ hỏi “có là regular file?” | `Files.isRegularFile(path)` | `false` không đồng nghĩa file chắc chắn không tồn tại; lỗi truy cập có thể cho kết quả `false` |
| Chỉ cần thời điểm sửa cuối | `Files.getLastModifiedTime(path)` | Độ phân giải tùy provider |
| Cần **nhiều trường cùng một lúc** | `Files.readAttributes(path, BasicFileAttributes.class)` | Chưa bảo đảm snapshot nguyên tử hoặc bớt I/O ở mọi provider |
| Cần metadata của chính symlink | `readAttributes(..., NOFOLLOW_LINKS)` | Hiểu chính sách link và race |
| Cần POSIX owner/permissions/ACL | Các attribute view khác được hỗ trợ | Không có trong `BasicFileAttributes` |

**Không có một API luôn tốt hơn trong mọi tình huống.** Nếu chỉ cần size, `Files.size` ngắn gọn. Nếu cần size, loại file và nhiều timestamp trong cùng một đoạn code, `BasicFileAttributes` rõ hơn vì các giá trị được nhóm và có kiểu chặt chẽ.

### Lợi ích hiệu năng có điều kiện

Truy vấn nhiều thuộc tính trong một lời gọi có thể giảm round trips và hợp lý với file system/network provider. Nhưng không được khẳng định rằng nó **luôn** chỉ tạo một system call. Provider có quyền triển khai chi tiết và có thể đọc thuộc tính bằng nhiều thao tác.

Tối ưu hiệu năng nên đo trên hệ thống thật: nhiều file trên network share có profile rất khác nhiều file trên SSD cục bộ.

## 10. Xử lý ngoại lệ khi truy vấn metadata

Lời gọi đọc metadata có thể thất bại:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

static BasicFileAttributes requiredAttributes(Path path)
        throws IOException {
    return Files.readAttributes(path, BasicFileAttributes.class);
}
```

Trong Java NIO.2, những ngoại lệ thường gặp bao gồm:

| Loại | Ví dụ tình huống | Gợi ý xử lý |
| --- | --- | --- |
| `NoSuchFileException` | Đường dẫn hoặc target link không còn tồn tại | Nếu là dữ liệu bắt buộc thì báo thất bại; nếu entry tùy chọn biến mất, có thể bỏ qua theo hợp đồng |
| `AccessDeniedException` | File system từ chối đọc metadata | Ghi nhận operation, xem chính sách quyền, không tự nâng quyền |
| `FileSystemException` | Lỗi provider/file system khác | Xem thông tin đường dẫn/reason (có thể `null`) ở log có kiểm soát |
| `IOException` | Lỗi I/O tổng quát | Giữ cause, xử lý theo chính sách và không giả định subclass cụ thể |
| `InvalidPathException` | Chuỗi tên không hợp lệ khi tạo `Path` | Lỗi unchecked ở bước parse path, không phải `IOException` của `readAttributes` |

Các subclass cụ thể **không được bảo đảm xuất hiện cùng một cách trên mọi provider**. Đừng viết logic dựa vào việc phân tích chuỗi `exception.getMessage()`, vì message có thể khác theo OS/ngôn ngữ hoặc chứa đường dẫn riêng.

### Ví dụ xử lý tệp không bắt buộc

```java
import java.nio.file.NoSuchFileException;

try {
    BasicFileAttributes attrs =
            Files.readAttributes(path, BasicFileAttributes.class);
    System.out.println(attrs.size());
} catch (NoSuchFileException ex) {
    System.out.println("Optional file disappeared");
}
```

Đây là **đoạn minh họa trong một phương thức có thể ném `IOException` khác**. Không nên bắt hết `IOException` rồi coi mọi lỗi là “file biến mất”, vì mất quyền đọc metadata hoặc hỏng thiết bị không tương đương thiếu file.

### Tránh “check-then-act”

```java
if (Files.exists(path)) {
    BasicFileAttributes attrs =
            Files.readAttributes(path, BasicFileAttributes.class);
}
```

Mã trên vẫn có thể thất bại giữa hai dòng do file bị xóa hoặc quyền thay đổi. Nếu mục tiêu là đọc metadata, gọi `readAttributes` và xử lý lỗi **ngay tại thao tác thật**. `Files.exists` chỉ là quan sát bổ sung, không phải khóa hay bảo đảm lần gọi tiếp theo.

## 11. Ứng dụng vào duyệt cây tệp với `FileVisitor`

`Files.walkFileTree` từ Java 7 kết hợp tốt với `BasicFileAttributes`. Khi traversal thăm một file, callback `visitFile` nhận sẵn metadata:

```java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

static long totalRegularBytes(Path root) throws IOException {
    final long[] sum = {0L};

    Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
        @Override
        public FileVisitResult visitFile(Path file,
                                         BasicFileAttributes attrs) {
            if (attrs.isRegularFile()) {
                sum[0] = Math.addExact(sum[0], attrs.size());
            }
            return FileVisitResult.CONTINUE;
        }

        @Override
        public FileVisitResult postVisitDirectory(Path dir,
                                                   IOException exc)
                throws IOException {
            if (exc != null) throw exc;
            return FileVisitResult.CONTINUE;
        }
    });
    return sum[0];
}
```

Đây là **phương thức đầy đủ để đặt trong lớp**; không cần gọi `Files.readAttributes` thêm một lần cho mỗi file trong `visitFile`, vì callback đã nhận `BasicFileAttributes`. Nó cộng kích thước logic của những entry được nhận là regular file trong lần duyệt.

Những giới hạn quan trọng:

- Tổng `sum[0]` **không** phải “dung lượng ổ đĩa đã dùng”. Hard links, sparse files hoặc trùng dữ liệu có thể khiến tổng khác dung lượng vật lý.
- File có thể thay đổi trong lúc quét; tổng không phải snapshot nhất quán tuyệt đối.
- Nếu một entry bị lỗi khi traversal, `SimpleFileVisitor` mặc định báo lỗi; một chương trình best-effort có thể xử lý riêng `visitFileFailed` nhưng phải đánh dấu kết quả thiếu dữ liệu.
- `Math.addExact` làm lộ phép cộng `long` bị tràn dưới dạng exception, thay vì âm thầm wrap-around.
- Không follow symlinks theo mặc định khi dùng `walkFileTree(root, visitor)`. Nếu bật `FOLLOW_LINKS`, phải tính rủi ro vòng liên kết và ảnh hưởng tới cách đếm.

Trong một hệ thống quét tệp cần tính toàn vẹn cao, có thể cần quản lý thêm quyền truy cập, chính sách symbolic link, quota, retry và trạng thái partial.

## 12. Chương trình Java 17+ hoàn chỉnh: đọc loại tệp, kích thước byte, thời gian và lỗi thiếu file

Chương trình sau tạo thư mục tạm và một tệp `sample.txt` có nội dung **`A😀B`**. Nó:

1. Ghi tệp mới bằng UTF-8, không dùng tệp có sẵn của người dùng.
2. Đọc `BasicFileAttributes` của tệp thường và thư mục.
3. Đọc lại metadata tệp với `LinkOption.NOFOLLOW_LINKS` (với **file thường**, kiểu tệp không đổi).
4. So sánh `size()` với số byte UTF-8, `Files.size`, độ dài `String` và số Unicode code point.
5. Xác minh các getter `FileTime` trả object timestamp, **không phụ thuộc** giá trị thời điểm cụ thể.
6. Thử đọc metadata của tệp không tồn tại và bắt `NoSuchFileException`.
7. Xóa các tài nguyên tạm trong `finally`.

Tạo tệp **`BasicFileAttributesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;

public final class BasicFileAttributesDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("basic-attrs-");
        Path file = root.resolve("sample.txt");
        String content = "A\uD83D\uDE00B";

        try {
            Files.writeString(file, content, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            BasicFileAttributes attributes =
                    Files.readAttributes(file, BasicFileAttributes.class);
            BasicFileAttributes noFollow =
                    Files.readAttributes(file, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes directory =
                    Files.readAttributes(root, BasicFileAttributes.class);

            long utf8Length =
                    content.getBytes(StandardCharsets.UTF_8).length;
            FileTime modified = attributes.lastModifiedTime();

            check(attributes.isRegularFile(), "expected regular file");
            check(!attributes.isDirectory(), "file not directory");
            check(!attributes.isSymbolicLink(), "file not symlink");
            check(!attributes.isOther(), "file not other");
            check(directory.isDirectory(), "expected directory");
            check(attributes.size() == utf8Length, "byte size");
            check(attributes.size() == Files.size(file), "size comparison");
            check(noFollow.isRegularFile(),
                    "regular file without following");
            check(utf8Length == 6, "UTF-8 byte count");
            check(content.length() == 4, "UTF-16 units");
            check(content.codePointCount(0, content.length()) == 3,
                    "Unicode code points");
            check(modified != null && attributes.creationTime() != null
                    && attributes.lastAccessTime() != null,
                    "timestamp objects");

            System.out.println("file regular = "
                    + attributes.isRegularFile());
            System.out.println("file directory = "
                    + attributes.isDirectory());
            System.out.println("file symbolic link = "
                    + attributes.isSymbolicLink());
            System.out.println("file other = "
                    + attributes.isOther());
            System.out.println("directory directory = "
                    + directory.isDirectory());
            System.out.println("size bytes = " + attributes.size());
            System.out.println("UTF-16 units = " + content.length());
            System.out.println("Unicode code points = "
                    + content.codePointCount(0, content.length()));
            System.out.println("size matches Files.size = "
                    + (attributes.size() == Files.size(file)));
            System.out.println("NOFOLLOW regular = "
                    + noFollow.isRegularFile());
            System.out.println("time objects non-null = "
                    + (modified != null
                    && attributes.creationTime() != null
                    && attributes.lastAccessTime() != null));

            Path missing = root.resolve("missing.txt");
            try {
                Files.readAttributes(missing, BasicFileAttributes.class);
                throw new AssertionError("expected missing file exception");
            } catch (NoSuchFileException expected) {
                System.out.println("missing metadata = "
                        + expected.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 BasicFileAttributesDemo.java
java BasicFileAttributesDemo
```

**Stdout chính xác đã được kiểm thử trên file system mặc định Windows:**

```text
file regular = true
file directory = false
file symbolic link = false
file other = false
directory directory = true
size bytes = 6
UTF-16 units = 4
Unicode code points = 3
size matches Files.size = true
NOFOLLOW regular = true
time objects non-null = true
missing metadata = NoSuchFileException
cleanup = done
```

### 12.1. Vì sao output không in timestamp thật?

Thời gian tạo/sửa file phụ thuộc lúc chạy, độ chính xác đồng hồ và provider. Nếu in `lastModifiedTime()` rồi dùng một chuỗi ISO cố định làm expected output, unit test sẽ không ổn định. Chương trình chỉ xác minh **object thời gian có mặt**, còn độ chính xác và ý nghĩa là vấn đề riêng cần đánh giá theo provider.

### 12.2. Vì sao không in `fileKey()`?

Giá trị file key có thể khác giữa Windows, Linux, network filesystem, và có thể `null`. Nếu in thẳng, output sẽ không ổn định. Bài hướng dẫn **cách kiểm tra nullable và chính sách sử dụng** ở mục 8 thay vì gán một kết quả giả định.

### 12.3. Vì sao `size bytes = 6` nhưng `UTF-16 units = 4`?

Nội dung là `A😀B`, encode bằng UTF-8. `BasicFileAttributes` trả số **byte trên file**, Java `String.length()` trả số **UTF-16 code unit**; ký tự emoji tương ứng hai code unit nhưng bốn byte UTF-8. Đây không phải lỗi của filesystem metadata.

### 12.4. Vì sao dùng `NOFOLLOW_LINKS` trên file thường?

Ví dụ có thể chạy được mà **không cần quyền tạo symlink**. `NOFOLLOW_LINKS` trên file thường vẫn trả thuộc tính file thường. Để xác minh sự khác biệt trên symbolic link thật, nên dùng một integration test riêng trong môi trường cho phép tạo link.

### 12.5. Vì sao `NoSuchFileException` được kiểm tra?

Đọc thuộc tính là một thao tác I/O: tệp `missing.txt` không tồn tại, nên provider mặc định trong test ném `NoSuchFileException`. Test này không nhầm `Files.readAttributes` với một phương thức chỉ phân tích tên `Path`. Trên provider khác, loại `IOException` có thể thay đổi, nên mã production vẫn cần fallback.

### 12.6. Giới hạn và dọn dẹp

Mã chỉ tạo và xóa **thư mục tạm do chính chương trình tạo**, không xóa tệp tùy ý của người dùng. Nếu không có quyền truy cập thư mục tạm, disk đầy hoặc tác nhân ngoài can thiệp, chương trình có thể phát sinh `IOException` — đây là điều kiện của môi trường I/O. `finally` giúp cố dọn tài nguyên trong phạm vi đã tạo nhưng không thể khắc phục mọi lỗi xóa do file system.

## 13. Các bài toán thực tế với metadata

### 13.1. Kiểm tra loại đầu vào trước khi xử lý

Một ứng dụng chỉ nhận tệp thường:

```java
BasicFileAttributes attrs =
        Files.readAttributes(input, BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);
if (!attrs.isRegularFile()) {
    throw new IOException("Expected a regular file entry");
}
```

Đây là đoạn minh họa trong phương thức có biến `input` kiểu `Path` và các import tương ứng. Nó giúp **phân loại entry** theo metadata lúc kiểm tra; nếu input không tin cậy, bước kiểm tra không thay thế mở file một cách an toàn vì file có thể bị đổi giữa hai thời điểm.

### 13.2. Bộ lọc file nhỏ trước khi đọc nội dung

```java
long threshold = 1024 * 1024;
BasicFileAttributes attrs =
        Files.readAttributes(input, BasicFileAttributes.class);

if (attrs.isRegularFile() && attrs.size() <= threshold) {
    // Chỉ là chính sách chọn nhánh; vẫn cần xử lý file thay đổi.
}
```

Giới hạn **1 MiB** chỉ là ví dụ do ứng dụng đặt ra, không phải quy định tối ưu bắt buộc của JDK. Nếu cần giới hạn bộ nhớ an toàn trước dữ liệu đối kháng, phải kiểm soát **số byte thực sự đọc** chứ không chỉ dựa vào `size()` quan sát trước.

### 13.3. Cache hoặc indexer dựa trên metadata

Có thể lưu `path`, `attrs.size()` và `attrs.lastModifiedTime()` để đánh giá file **có thể** đã thay đổi. Tuy nhiên, do độ phân giải timestamp, việc khôi phục backup, sửa nội dung cùng size hoặc thay thế file, việc **size và modified time không đổi** không bảo đảm nội dung bằng nhau.

Nếu nghiệp vụ yêu cầu chính xác, dùng nội dung/digest và quy trình đọc nhất quán. Không lấy `creationTime` hoặc `fileKey` làm bằng chứng vĩnh viễn về danh tính một bản ghi ứng dụng.

### 13.4. Thống kê thư mục

Khi dùng `walkFileTree` và `visitFile(Path, BasicFileAttributes)`, có thể đếm regular files, tổng byte logic và phân loại file type mà không gọi `Files.readAttributes` riêng cho mọi entry. Nếu traversal bỏ nhánh do quota/lỗi, báo cáo cần mang trạng thái **partial**, không tuyên bố đã kiểm kê toàn bộ.

### 13.5. Theo dõi thay đổi

`BasicFileAttributes` là một **lần đọc**, không phải subscription hay file watcher. Nếu cần biết khi tệp thay đổi, có thể xem API `WatchService` hoặc cơ chế theo dõi tương ứng, nhưng vẫn phải thiết kế việc đọc metadata lại, xử lý sự kiện có thể gộp/mất và tính đồng thời. Không mong một `attrs` cũ tự đổi trường khi tệp được sửa.

## 14. Tính an toàn và các cuộc đua trạng thái filesystem

### 14.1. Metadata chỉ là quan sát tại một thời điểm

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

if (attrs.isRegularFile()) {
    byte[] bytes = Files.readAllBytes(path);
}
```

Đây là mã minh họa trong phương thức có `throws IOException`. Giữa hai lời gọi, một tiến trình khác có thể **thay file bằng directory/symlink**, xóa file hoặc thay nội dung. Việc đã kiểm tra `isRegularFile()` không cam kết `readAllBytes` sẽ đọc cùng một đối tượng.

Với dữ liệu nội bộ đáng tin cậy, mẫu có thể hữu ích như một điều kiện hợp lý. Với đường dẫn **không tin cậy hoặc có tác nhân đối kháng**, cần thiết kế kiểm soát quyền, root, symlink, cách mở file và ownership phù hợp thay vì coi metadata pre-check là hàng rào bảo mật.

### 14.2. Khi đối tượng thay đổi ngay giữa các metadata read

Hai lần gọi `Files.readAttributes` có thể trả hai kết quả khác nhau. Ví dụ kích thước lúc kiểm tra khác kích thước lúc xử lý — đây là trạng thái bình thường của hệ thống tệp đang được cập nhật, không nhất thiết là bug của `BasicFileAttributes`.

Nếu ứng dụng cần snapshot nhất quán để backup, phải dựa vào cơ chế đồng bộ, filesystem snapshot hoặc chiến lược xác minh được thiết kế. Một object metadata không tự cô lập hoặc khóa dữ liệu trên đĩa.

### 14.3. Metadata và quyền truy cập

Không suy ra chỉ vì đọc được metadata thì chương trình cũng có quyền đọc **nội dung** tệp hoặc ghi vào thư mục đó. Các quyền có thể khác; chính sách OS, ACL, mount hoặc provider có thể từ chối một thao tác dù một thao tác trước thành công.

Khi trả lỗi ra UI, đừng hiện absolute path của server hoặc stack trace cho mọi người dùng. Thông báo nên nêu thao tác thất bại ở mức an toàn; log kỹ thuật có kiểm soát có thể dùng tên exception, operation/correlation ID và dữ liệu đường dẫn đã che theo chính sách.

## 15. Những lỗi thường gặp

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Nhầm `Path.of` với thao tác đọc metadata | `Path` chỉ là giá trị tên | Gọi `Files.readAttributes` và xử lý I/O |
| Dùng `String.length()` để đo kích thước file UTF-8 | Đếm UTF-16, không phải byte | Dùng `attrs.size()` hoặc số byte mã hóa thật |
| Coi `size()` của directory/link là số byte nội dung file | Không có ý nghĩa thống nhất như file thường | Kiểm tra loại entry và hợp đồng provider |
| Nghĩ `readAttributes` luôn là snapshot nguyên tử | Provider có thể đọc dữ liệu nhiều bước | Xử lý file biến động và đồng bộ khi cần |
| Cho rằng `lastAccessTime()` cập nhật sau mọi lần đọc | Filesystem có thể trì hoãn/không hỗ trợ | Xác định khả năng môi trường |
| Xem `creationTime()` luôn là ngày tạo thật | Provider có thể dùng fallback | Lưu createdAt nghiệp vụ riêng nếu cần |
| So timestamp bằng chuỗi local time không có timezone | Dễ sai do định dạng/zone/độ phân giải | Dùng `FileTime`/`Instant`, format ở UI |
| Dùng `fileKey().toString()` làm ID toàn cầu | Có thể `null`, tái dùng, provider-dependent | Dùng ID nghiệp vụ riêng |
| Quên `NOFOLLOW_LINKS` khi muốn biết entry có là symlink | Mặc định có thể theo link tới target | Gọi `readAttributes(..., NOFOLLOW_LINKS)` |
| Nghĩ `NOFOLLOW_LINKS` là chống TOCTOU toàn diện | File có thể thay đổi sau kiểm tra | Thiết kế mở file/ownership an toàn |
| Nghĩ `Files.isRegularFile(path) == false` nghĩa là không có file | Có thể không xác định được metadata | Xử lý `readAttributes`/`IOException` khi cần lý do |
| Chỉ catch `IOException` rồi thông báo “file missing” | Nhiều lỗi I/O khác thiếu file | Phân biệt subclass và giữ fallback |
| Dùng `Files.exists` trước rồi bỏ qua exception từ read | Race giữa hai lời gọi | Xử lý ngoại lệ tại thao tác thực tế |
| Dùng `size + modifiedTime` như hash bảo toàn nội dung | File thay đổi mà metadata vẫn có thể giống | So nội dung/hash khi cần chính xác |
| Gọi `readAllBytes` chỉ vì `size` hiện tại nhỏ | File có thể lớn lên, heap có giới hạn | Streaming và quota thực đọc |
| Đọc lại attrs từng file trong `visitFile` dù callback đã có | I/O dư thừa hoặc quan sát hai thời điểm | Dùng `BasicFileAttributes attrs` được cung cấp |
| Cố test creationTime bằng một thời điểm cố định sau khi tạo file | Time phụ thuộc OS/đồng hồ | Kiểm tra kiểu/quan hệ, test môi trường riêng |
| Ép fileKey sang kiểu nội bộ của Windows/Linux | Mã không khả chuyển | Dùng giao diện `Object`, kiểm tra `null` |
| Xem quyền truy cập metadata là quyền truy cập nội dung | Chính sách đọc/ghi khác nhau | Xử lý quyền ở I/O thật |

## 16. Bài tập thực hành và đáp án

### Bài 1 — Đọc hai trường metadata

Hãy lấy loại tệp và kích thước từ `Path path` bằng một lời gọi typed API.

**Đáp án:**

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

boolean regular = attrs.isRegularFile();
long sizeBytes = attrs.size();
```

Đặt trong phương thức có `Path path` và `throws IOException`. `sizeBytes` biểu diễn byte, không phải số ký tự.

### Bài 2 — Phân biệt byte và ký tự

Một tệp được ghi chính xác UTF-8 với nội dung `A😀B`. `attrs.size()`, `content.length()` và số Unicode code point dự kiến bằng bao nhiêu?

**Đáp án:** `6` byte, `4` đơn vị UTF-16 và `3` code point. Emoji chiếm bốn byte UTF-8 và hai đơn vị UTF-16.

### Bài 3 — Symlink tới file thường

Một `Path` là symbolic link tới file thường. Vì sao `Files.readAttributes(path, BasicFileAttributes.class).isRegularFile()` có thể là `true` mà `NOFOLLOW_LINKS` lại cho `isSymbolicLink()`?

**Đáp án:** Lời gọi mặc định có thể **theo link tới đối tượng đích**, còn `NOFOLLOW_LINKS` yêu cầu metadata của **entry link**. Hai lời gọi trả lời hai câu hỏi khác nhau.

### Bài 4 — File key thiếu

`attrs.fileKey()` trả `null`. Có phải code Java bị lỗi?

**Đáp án:** Không. `fileKey()` theo hợp đồng có thể trả `null` khi provider không cung cấp key. Không dereference hoặc ép kiểu khi chưa kiểm tra.

### Bài 5 — Thời điểm tạo file

Ứng dụng dùng `attrs.creationTime()` để quyết định tài khoản có tạo một tài liệu trước một hạn pháp lý không. Có đủ tin cậy không?

**Đáp án:** Không nên. Timestamp của filesystem có thể không được hỗ trợ đúng, có fallback, thay đổi khi restore/copy và bị ảnh hưởng cấu hình/provider. Cần timestamp nghiệp vụ được ghi nhận trong hệ thống tin cậy.

### Bài 6 — Metadata không cập nhật tự động

Ứng dụng đọc `attrs`, sau đó một tiến trình khác ghi thêm 100 byte vào tệp. `attrs.size()` có tự tăng không?

**Đáp án:** Không. `attrs` là kết quả đọc thuộc tính của một thời điểm. Muốn biết kích thước mới phải đọc lại, và vẫn xử lý trạng thái biến động.

### Bài 7 — Có nên kiểm tra tồn tại trước?

`Files.exists(path)` trả `true` rồi ngay sau đó `Files.readAttributes(path, ...)` ném `NoSuchFileException`. Vì sao?

**Đáp án:** Hệ thống tệp có thể thay đổi giữa hai thao tác. `exists` không khóa entry và không bảo đảm trạng thái tương lai (TOCTOU).

### Bài 8 — Truy vấn trong visitor

Trong `Files.walkFileTree`, `visitFile` được truyền `BasicFileAttributes attrs`. Có cần gọi `readAttributes` lại để lấy size của cùng entry không?

**Đáp án:** Thường không. `attrs` đã chứa `size()` và các trường cơ bản. Đọc lại có thể là I/O thừa và có thể lấy trạng thái khác nếu file đang thay đổi; chỉ đọc lại khi nghiệp vụ chủ ý cần metadata mới.

### Bài 9 — File không tồn tại

Nếu `readAttributes` thất bại với `NoSuchFileException` trong một lượt quét, có nên âm thầm tiếp tục không?

**Đáp án:** Tùy hợp đồng. File **bắt buộc** nên gây thất bại hoặc được báo lỗi rõ; file **tùy chọn** có thể bỏ qua và ghi nhận quét thiếu dữ liệu. Không catch mọi `IOException` rồi coi là thiếu file.

### Bài 10 — Tính dung lượng thư mục

Nếu cộng `attrs.size()` của tất cả regular files trong một cây, đã biết chính xác lượng dung lượng vật lý chiếm trên ổ chưa?

**Đáp án:** Chưa. Tổng byte logic có thể khác dung lượng vật lý vì filesystem allocation, sparse file, hard links, compression hoặc dữ liệu thay đổi trong khi quét.

### Bài 11 — Giá trị timestamp trong test

Tại sao ví dụ chạy đầy đủ không in `attrs.lastModifiedTime()` vào stdout chuẩn?

**Đáp án:** Thời gian sửa phụ thuộc lúc chạy, file system, độ phân giải và đồng hồ hệ thống. Test dựa trên một giá trị cố định sẽ không ổn định. Khi cần xác minh timestamp, kiểm tra loại object và các tính chất theo hợp đồng, test chi tiết provider riêng.

### Bài 12 — API theo phiên bản

`BasicFileAttributes` và `Files.readAttributes` có từ phiên bản Java nào? `Path.of` và `Files.writeString` trong chương trình từ khi nào?

**Đáp án:** Cặp `BasicFileAttributes`/`Files.readAttributes` thuộc Java NIO.2 từ **Java 7**. `Path.of` và `Files.writeString` có từ **Java 11**, nên chương trình minh họa biên dịch/chạy với Java 17; trên Java 7 có thể tạo path bằng `Paths.get` và ghi bytes bằng API phù hợp.

## 17. Checklist áp dụng thực tế

- [ ] Xác định liệu bài toán cần **metadata** hay **nội dung**; không đọc file vào RAM nếu chỉ cần type/size/time.
- [ ] Dùng `Files.readAttributes(path, BasicFileAttributes.class)` khi cần nhiều thuộc tính cơ bản, và xử lý `IOException`.
- [ ] Dùng `isRegularFile`/`isDirectory`/`isSymbolicLink`/`isOther` đúng mục đích; không đoán từ phần mở rộng tên.
- [ ] Chỉ diễn giải `size()` của regular file là độ dài logic tính bằng **byte**, không phải độ dài `String` hay disk allocation.
- [ ] Kiểm tra support/granularity của `lastAccessTime` và `creationTime` khi nghiệp vụ phụ thuộc chúng.
- [ ] Dùng `FileTime` và `Instant`; tách giá trị thời điểm khỏi cách hiển thị theo timezone.
- [ ] Kiểm tra `fileKey() == null`, không dùng fileKey làm mã định danh nghiệp vụ đa hệ thống.
- [ ] Chọn mặc định theo symbolic link hay `NOFOLLOW_LINKS` một cách có chủ đích.
- [ ] Không coi metadata check là khóa file, snapshot nguyên tử hoặc xác thực an toàn path.
- [ ] Nếu dữ liệu đầu vào không tin cậy, áp dụng kiểm soát quyền, root, symlink và quota đọc thực tế.
- [ ] Bắt các lỗi I/O theo chính sách, giữ subclass/cause và không dựa vào văn bản message từ provider.
- [ ] Khi `walkFileTree` đã cấp `BasicFileAttributes` ở callback, tận dụng nó thay vì đọc thừa.
- [ ] Test file thường, directory, file thiếu, byte Unicode, symbolic link khi provider hỗ trợ, timestamp và file key không ổn định.
- [ ] Ghi rõ baseline: core metadata API từ Java 7; chương trình hoàn chỉnh dùng `Path.of`/`Files.writeString` từ Java 11 và chạy tốt trên Java 17+.

## 18. Kết luận

**`BasicFileAttributes`** là cách chuẩn, typed và vẫn hiện hành để đọc **thuộc tính tệp cơ bản** trong Java NIO.2: loại entry, kích thước byte, ba giá trị `FileTime` và file key tùy provider. Lời gọi `Files.readAttributes(path, BasicFileAttributes.class, options...)` thực hiện truy vấn metadata thật, có thể gây `IOException`, và kết quả là **quan sát tại thời điểm đọc** chứ không phải tệp được khóa hay nội dung không thay đổi.

Khi triển khai, cần phân biệt **theo hay không theo symbolic link**, **số byte với số ký tự**, **timestamp có thể không chính xác/không được hỗ trợ**, và **file key phụ thuộc provider**. Nếu cần duyệt nhiều entry, `walkFileTree` đã truyền `BasicFileAttributes` vào visitor; nếu cần bảo đảm nội dung hoặc quyền truy cập, phải thiết kế các thao tác I/O và cơ chế bảo vệ bổ sung. Những nguyên tắc này dùng được từ Java 7 đến Java hiện đại và giúp hệ thống quét tệp, cache, indexer và kiểm tra input đáng tin cậy hơn.
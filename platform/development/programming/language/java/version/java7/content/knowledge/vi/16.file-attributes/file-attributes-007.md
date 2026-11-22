# Thuộc tính DOS trên hệ thống tệp hỗ trợ trong Java

## 1. Bài toán và mục tiêu

Trong một công cụ làm việc với file, đôi khi các thuộc tính cơ bản như `size`, `lastModifiedTime` hoặc `isRegularFile` chưa đủ. Ví dụ: ứng dụng chạy trên một volume Windows cần biết một tệp đang được đánh dấu **ẩn**, **chỉ đọc**, **hệ thống** hoặc **archive** theo metadata của file-system provider; hoặc cần đánh dấu một tệp tạm là hidden, rồi khôi phục trạng thái ban đầu.

Java NIO.2 có hai interface hiện hành, được giới thiệu từ **Java 7**:

- **`java.nio.file.attribute.DosFileAttributes`**: giao diện **đọc** các thuộc tính cơ bản cùng bốn cờ DOS.
- **`java.nio.file.attribute.DosFileAttributeView`**: giao diện xem và **cập nhật** các cờ DOS khi file system/provider hỗ trợ và cho phép thao tác.

Tên gọi “DOS attributes” xuất phát từ mô hình cờ thuộc tính truyền thống của hệ thống tệp. **Không vì tên gọi lịch sử mà coi API Java này là lỗi thời**: những API `DosFileAttributes`/`DosFileAttributeView` vẫn có trong Java hiện đại và vẫn thích hợp khi làm việc với **provider hỗ trợ DOS attribute view**. Tuy nhiên, **chúng không phải API metadata phổ quát cho tất cả filesystem**. Ứng dụng đa nền tảng phải kiểm tra khả năng hỗ trợ và có phương án thay thế hợp lý.

Bài này giúp trả lời chính xác:

1. Bốn cờ **`readOnly`, `hidden`, `system`, `archive`** có ý nghĩa gì và **không** có ý nghĩa gì?
2. Làm sao phát hiện volume/provider có **DOS attribute view** hay không?
3. Đọc các cờ bằng `Files.readAttributes` hoặc `DosFileAttributeView.readAttributes` như thế nào?
4. Thay đổi cờ bằng `setReadOnly`, `setHidden`, `setSystem`, `setArchive` ra sao, và vì sao cần khôi phục giá trị cũ?
5. Phân biệt các cờ này với **quyền bảo mật/ACL**, với `Files.isHidden` và với thuộc tính file cơ bản.
6. Xử lý symbolic link, lỗi I/O, đồng thời, môi trường không hỗ trợ và kiểm thử thực tế thế nào?

**Quy tắc chủ đạo:** Chỉ áp dụng chức năng DOS trên **hệ thống tệp hỗ trợ**. Không viết mã giả định rằng chạy Java trên Windows thì mọi volume/provider luôn hỗ trợ, hoặc chạy trên Unix thì chắc chắn không thể có DOS view. Khả năng được quyết định bởi **file system và provider đang gắn với `Path` cụ thể**.

## 2. Nằm ở đâu trong Java NIO.2?

Những đối tượng và API liên quan có vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Path` | Giá trị biểu diễn một đường dẫn thuộc `FileSystem` | `Path.of("reports", "result.bin")` |
| `Files` | Thao tác I/O, đọc/ghi metadata, lấy file store và attribute view | `Files.readAttributes(path, DosFileAttributes.class)` |
| `BasicFileAttributes` | Các thuộc tính cơ bản: loại tệp, size, timestamp, file key | `attrs.size()` |
| `DosFileAttributes` | Mở rộng `BasicFileAttributes` bằng bốn cờ DOS | `attrs.isHidden()` |
| `BasicFileAttributeView` | Cơ chế truy cập/cập nhật nhóm thuộc tính cơ bản | `readAttributes()` |
| `DosFileAttributeView` | Mở rộng view cơ bản với các phương thức đặt cờ DOS | `view.setHidden(true)` |
| `FileStore` | Biểu diễn một file store và hỗ trợ tra cứu loại view mà store cung cấp | `store.supportsFileAttributeView(...)` |

Các thuộc tính DOS gắn với metadata của **đối tượng filesystem**, không phải các field do chính object `Path` lưu. Tạo `Path` không tạo tệp và không tự đọc cờ DOS; truy vấn thuộc tính phải thực hiện qua provider bằng API `Files` hoặc attribute view.

### 2.1. Cấu trúc kế thừa

```text
BasicFileAttributes
    └── DosFileAttributes
          + isReadOnly()
          + isHidden()
          + isSystem()
          + isArchive()

BasicFileAttributeView
    └── DosFileAttributeView
          + setReadOnly(boolean)
          + setHidden(boolean)
          + setSystem(boolean)
          + setArchive(boolean)
```

Đây là **sơ đồ interface**, không phải mã Java. Vì `DosFileAttributes` mở rộng `BasicFileAttributes`, cùng một object thuộc tính DOS còn có `isRegularFile()`, `isDirectory()`, `size()`, `lastModifiedTime()`, `creationTime()`, `lastAccessTime()` và `fileKey()`.

**Giá trị học tập:** Không nhất thiết cần hai lần gọi metadata riêng biệt chỉ để lấy loại file và cờ DOS; khi view được hỗ trợ, `DosFileAttributes` đã bao gồm phần cơ bản. Tuy nhiên, không được mặc định mọi provider trả metadata theo một snapshot nguyên tử.

### 2.2. Phạm vi phiên bản Java

`DosFileAttributes`, `DosFileAttributeView`, `Files.readAttributes` và `FileStore.supportsFileAttributeView` là các thành phần của Java NIO.2 từ **Java 7** và vẫn áp dụng tới Java hiện đại. Đoạn code hoàn chỉnh ở bài dùng **Java 17+**, nhất là `Path.of` từ Java 11. Nếu cần tương thích source với Java 7/8, dùng `Paths.get` để xây dựng `Path` và điều chỉnh các API tiện ích xuất hiện ở phiên bản sau; không gọi API Java 11 rồi gắn nhãn “chạy trên Java 7”.

## 3. Bốn cờ DOS: cách hiểu chính xác

| Cờ | Getter của `DosFileAttributes` | Setter của `DosFileAttributeView` | Ý nghĩa thường gặp |
| --- | --- | --- | --- |
| Read-only | `isReadOnly()` | `setReadOnly(boolean)` | Metadata đánh dấu mục là chỉ đọc theo quy tắc DOS |
| Hidden | `isHidden()` | `setHidden(boolean)` | Metadata đánh dấu mục là ẩn trong cách diễn giải của hệ thống hỗ trợ |
| System | `isSystem()` | `setSystem(boolean)` | Metadata đánh dấu đối tượng thuộc loại hệ thống theo ngữ nghĩa của provider |
| Archive | `isArchive()` | `setArchive(boolean)` | Metadata “archive bit”, thường liên quan quy trình đánh dấu đối tượng đã thay đổi/để sao lưu |

Mỗi cờ được biểu diễn bằng `boolean`. Chúng là **metadata**, không phải một enum loại file; một regular file có thể đồng thời hidden và archive, hoặc nhiều cờ khác cùng lúc.

### 3.1. `readOnly` không đồng nghĩa toàn bộ quyền bảo mật

`attrs.isReadOnly()` báo cờ DOS readonly. Nó **không phải** một câu trả lời đầy đủ cho “ai được đọc/ghi/xóa file này?”. File system có thể còn ACL, quyền sở hữu, chính sách mount, giới hạn của process hoặc quy tắc khác.

Ví dụ, đừng suy ra:

- `isReadOnly() == false` có nghĩa người dùng hiện tại chắc chắn có quyền ghi.
- `isReadOnly() == true` tương đương `Files.isWritable(path) == false` trong mọi filesystem.
- Đặt `setReadOnly(true)` là một cơ chế thay thế cho phân quyền hoặc khóa file an toàn trước người dùng không tin cậy.
- Bỏ read-only bằng `setReadOnly(false)` có nghĩa ứng dụng đã được phép sửa nội dung ở mọi nơi.

Cờ readonly có thể ảnh hưởng thao tác file theo hệ thống tệp, nhưng **không thay thế ACL/security model**. Nếu ứng dụng cần thực thi quyền, dùng cơ chế phân quyền đúng môi trường và để thao tác I/O thật báo lỗi khi không được phép.

### 3.2. `hidden` khác quy tắc “tên bắt đầu bằng dấu chấm”

`attrs.isHidden()` mô tả cờ **DOS hidden** khi DOS view được hỗ trợ. Nó khác với quy ước tên `.config` hoặc `.gitignore` thường thấy trên Unix.

Không nên nói rằng:

```java
path.getFileName().toString().startsWith(".")
```

luôn tương đương `attrs.isHidden()`. Đoạn trên chỉ kiểm tra **ký tự đầu của tên**, không truy vấn DOS metadata.

Java còn có `Files.isHidden(path)`, nhưng phương thức này là một truy vấn **theo định nghĩa hidden của provider/OS**, không nhất thiết là phép thay thế bất biến cho cờ `DosFileAttributes.isHidden()` trên mọi nền tảng. Nếu mục tiêu nghiệp vụ là **cờ DOS**, dùng `DosFileAttributes`; nếu mục tiêu là “hệ thống coi mục này là hidden”, xem ý nghĩa `Files.isHidden` của provider.

### 3.3. `system` là cờ hệ thống, không phải đặc quyền quản trị

`isSystem()` đọc một cờ metadata theo DOS attribute model. Nó **không chứng minh** file do hệ điều hành sở hữu, đang được bảo vệ tuyệt đối, hoặc ứng dụng có/không có quyền quản trị.

Thay đổi `setSystem` có thể ảnh hưởng cách phần mềm/OS diễn giải đối tượng; không dùng ví dụ học tập để đổi cờ system của file thật, file cấu hình hệ điều hành hoặc dữ liệu người dùng. Trong chương trình kiểm thử của bài, chúng ta **chỉ đọc** system flag và **không thay đổi** nó.

### 3.4. `archive` không chứng minh file đã được sao lưu

Cờ `archive` có lịch sử liên quan đến việc đánh dấu file cho quy trình sao lưu; một số phần mềm có thể bật/xóa bit này theo chính sách của chúng. Nhưng:

- `isArchive() == true` **không chứng minh** file đã hoặc chưa được sao lưu trong một hệ thống backup cụ thể.
- `isArchive() == false` **không chứng minh** backup là bản mới nhất.
- Việc sao chép, ghi hoặc di chuyển có thể tác động tới cờ tùy filesystem/ứng dụng.
- Một dịch vụ backup hiện đại có thể dùng snapshot, change journal, hash hoặc metadata nghiệp vụ riêng, thay vì coi archive bit là nguồn sự thật duy nhất.

Chỉ dùng archive bit khi bạn biết rõ **hợp đồng với file system và quy trình vận hành**; không tự tạo tính đúng đắn của backup từ một boolean.

## 4. Trước khi đọc: kiểm tra file store/provider có hỗ trợ không

**Đây là bước quan trọng nhất để viết mã đa nền tảng.** Một máy tính có thể dùng nhiều file store: ổ hệ thống, ổ ngoài, volume mạng, file system ảo hoặc provider được cài đặt. Hỗ trợ DOS view không thể suy ra chỉ từ tên OS.

### 4.1. `FileStore.supportsFileAttributeView`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;

Path path = Path.of("data", "sample.bin");
boolean supported = Files.getFileStore(path)
        .supportsFileAttributeView(DosFileAttributeView.class);
```

Đây là **mã minh họa nằm trong một phương thức có xử lý `IOException`**; muốn gọi `getFileStore(path)` trong thực tế nên có đường dẫn phù hợp/tồn tại theo hợp đồng provider. `supported` cho biết file store tuyên bố hỗ trợ loại attribute view này.

Không dùng:

```java
boolean supported = System.getProperty("os.name").contains("Windows");
```

làm thay thế cho kiểm tra khả năng hỗ trợ. Đó là **đoạn cố ý không nên áp dụng**: nó vừa phụ thuộc chuỗi hệ điều hành, vừa bỏ qua sự khác nhau giữa các volume/provider.

### 4.2. `Files.getFileAttributeView`

Một cách tiếp cận trực tiếp khác:

```java
import java.nio.file.LinkOption;
import java.nio.file.attribute.DosFileAttributeView;

DosFileAttributeView view = Files.getFileAttributeView(
        path, DosFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view == null) {
    // File system/provider không cung cấp view này cho đường dẫn.
} else {
    // Có thể đọc/cập nhật theo khả năng của view và quyền hiện tại.
}
```

Đây là ví dụ ở trong phương thức có biến `path` kiểu `Path`. Khi không hỗ trợ view, kết quả có thể là `null`; **phải kiểm tra trước khi gọi `view.readAttributes()`**.

### 4.3. Kiểm tra hỗ trợ không bảo đảm thao tác sẽ thành công

Cần tách ba mức:

1. **Khả năng provider/file store:** DOS view được khai báo có hỗ trợ hay không.
2. **Khả năng đọc thuộc tính của mục cụ thể:** tệp còn tồn tại, provider truy cập được và người chạy đủ quyền hay không.
3. **Khả năng cập nhật thuộc tính:** setter được cho phép trong hoàn cảnh hiện tại hay bị từ chối bởi quyền, file system, môi trường hoặc trạng thái đối tượng.

Ngay cả khi `supportsFileAttributeView` trả `true` hoặc có `view != null`, `readAttributes()` và các setter vẫn **có thể ném `IOException`**. Không coi bước capability check là cam kết quyền truy cập hoặc tính ổn định.

**Fallback hợp lý:** nếu bài toán chỉ cần biết loại file, size hoặc modified time, có thể đọc `BasicFileAttributes` trên provider không hỗ trợ DOS. Nếu nghiệp vụ **bắt buộc** một cờ DOS, hãy báo rõ chức năng không hỗ trợ, không bịa giá trị `false` cho thuộc tính không đọc được.

## 5. Đọc theo typed API bằng `Files.readAttributes`

Khi đã biết DOS attribute view được hỗ trợ, có thể đọc tất cả thuộc tính bằng một lời gọi:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributes;

static DosFileAttributes readDos(Path path) throws IOException {
    return Files.readAttributes(path, DosFileAttributes.class);
}
```

Đây là **phương thức để đặt trong một lớp Java**. Trả về một object triển khai `DosFileAttributes`, cho phép đọc:

```java
boolean readOnly = attrs.isReadOnly();
boolean hidden = attrs.isHidden();
boolean system = attrs.isSystem();
boolean archive = attrs.isArchive();

boolean regular = attrs.isRegularFile();
long bytes = attrs.size();
```

Đoạn trên cần biến `attrs` kiểu `DosFileAttributes`. Không coi các getter là phép mở file nội dung; chúng trả về dữ liệu đã được provider đưa vào object attributes.

**Với provider không hỗ trợ DOS view**, lời gọi typed này có thể gây `UnsupportedOperationException`. Đây là lý do nên kiểm tra hỗ trợ trước hoặc xử lý trường hợp không có view một cách minh bạch.

### 5.1. Đọc qua view đã lấy

```java
DosFileAttributeView view = Files.getFileAttributeView(
        path, DosFileAttributeView.class);

if (view != null) {
    DosFileAttributes attrs = view.readAttributes();
    System.out.println(attrs.isHidden());
}
```

Đây là đoạn minh họa trong phương thức có `throws IOException`. Đọc theo typed `Files.readAttributes` và qua `view.readAttributes()` đều phục vụ mục tiêu tương tự, nhưng view hữu ích khi muốn **đọc rồi thao tác các setter** trên cùng một nhóm API.

### 5.2. Kết quả là metadata tại lúc truy vấn, không phải đối tượng tự cập nhật

`DosFileAttributes attrs` là giá trị dữ liệu được **đọc** tại một thời điểm. Sau:

```java
DosFileAttributes before = view.readAttributes();
view.setHidden(true);
```

object `before` không trở thành một “live view” mà tự đổi `before.isHidden()`. Muốn xem trạng thái mới, cần gọi:

```java
DosFileAttributes after = view.readAttributes();
```

Phân biệt tên rất quan trọng: **`DosFileAttributeView`** là cơ chế truy cập thuộc tính, còn **`DosFileAttributes`** là object chứa kết quả đọc thuộc tính.

### 5.3. Đọc thuộc tính trước và sau không phải giao dịch nguyên tử

Nếu có một tiến trình khác thay đổi cờ giữa các lần đọc, `before` và `after` có thể khác ngoài dự kiến. Việc đọc nhiều thuộc tính trong một lời gọi cũng không được bảo đảm là một snapshot nguyên tử của mọi trường trên mọi provider.

Không dùng `attrs.isReadOnly() == false` từ vài giây trước làm bảo đảm rằng lệnh ghi tiếp theo không thể bị từ chối.

## 6. Viết qua `DosFileAttributeView`

View hỗ trợ các phương thức:

```java
view.setReadOnly(true);
view.setHidden(true);
view.setSystem(false);
view.setArchive(true);
```

Đây là **mã API minh họa**, không phải hướng dẫn chạy nguyên khối trên tệp bất kỳ: mỗi lệnh **thay đổi metadata thật** của đối tượng khi được cho phép. Với code production, chỉ thay cờ có lý do rõ ràng và quyền thao tác phù hợp.

Chữ ký đều có thể ném `IOException`. Nếu provider không hỗ trợ view, việc lấy view có thể trả `null`; nếu hỗ trợ nhưng người dùng không đủ quyền hoặc file bị thay đổi, setter cũng có thể thất bại.

### 6.1. Thay đổi hidden trên tệp do ứng dụng sở hữu

```java
DosFileAttributeView view = Files.getFileAttributeView(
        ownedFile, DosFileAttributeView.class);

if (view == null) {
    System.out.println("DOS attribute view unavailable");
} else {
    DosFileAttributes original = view.readAttributes();
    boolean oldHidden = original.isHidden();
    try {
        view.setHidden(!oldHidden);
        boolean changed = view.readAttributes().isHidden() != oldHidden;
        System.out.println("changed = " + changed);
    } finally {
        view.setHidden(oldHidden);
    }
}
```

Đây là **đoạn minh họa trong phương thức khai báo `throws IOException`**, có biến `ownedFile` là `Path` của một tệp thử nghiệm mà ứng dụng được phép chỉnh metadata. Khối `finally` cố khôi phục giá trị ban đầu; khôi phục cũng có thể ném `IOException`, nên cần có chính sách xử lý nếu thất bại.

**Không mặc định cờ hidden ban đầu là `false`.** Tệp vừa tạo có thể nhận metadata khác nhau theo file system và cách copy/move. Lưu giá trị gốc và khôi phục đúng giá trị đó thay vì ép về `false`.

### 6.2. Read-only và rủi ro khi thử nghiệm

`setReadOnly(true)` có thể làm một số thao tác ghi/xóa tệp thất bại tùy filesystem. Nếu đang học API, đừng bật read-only trên thư mục chứa dữ liệu thật hoặc file cần xóa ngay khi test. Nếu nghiệp vụ cần thay cờ này, hãy có kế hoạch khôi phục, xử lý lỗi và kiểm thử trên volume thực sự được hỗ trợ.

Ví dụ trong bài **chỉ đọc `isReadOnly()`**; không thay cờ read-only để tránh tạo một tệp tạm khó xóa hoặc ảnh hưởng một chính sách ngoài phạm vi thí nghiệm.

### 6.3. Không tùy tiện thay cờ system

`setSystem(boolean)` là thao tác hợp lệ của view khi có hỗ trợ, nhưng **thay đổi ý nghĩa metadata** trong hệ sinh thái ứng dụng/OS. Việc chuyển cờ system không biến file thường thành “file của hệ điều hành” theo nghĩa bảo mật; cũng không cấp hoặc thu hồi ACL.

Chỉ thao tác khi có yêu cầu nghiệp vụ và quyền sở hữu rõ ràng. Chương trình kiểm thử độc lập ở phần sau **không gọi `setSystem`**.

### 6.4. Archive bit phải theo hợp đồng với hệ thống backup

`setArchive(true/false)` có thể hữu ích khi tích hợp một quy trình được thiết kế sử dụng cờ archive. Nhưng nếu ứng dụng backup hiện đại dùng cơ chế khác, tự thay archive bit có thể làm nhiễu luồng sao lưu hoặc tạo ra kết luận sai về việc dữ liệu đã được backup.

Ví dụ thực hành chỉ đảo archive flag của **tệp tạm do chính chương trình tạo**, kiểm tra trạng thái rồi khôi phục. Không chạy những lệnh này trên dữ liệu sản xuất chỉ để thử API.

## 7. `NOFOLLOW_LINKS` và symbolic link

Đọc các thuộc tính của **mục tiêu mà một link trỏ tới** khác với đọc thuộc tính **chính entry link**.

### 7.1. Mặc định có thể theo symbolic link

```java
DosFileAttributes attrs =
        Files.readAttributes(path, DosFileAttributes.class);
```

Trong ngữ cảnh một symbolic link có target hợp lệ, lời gọi không truyền `LinkOption` thường theo link để lấy thuộc tính của **đối tượng đích**, theo hợp đồng provider. Nếu path trỏ tới tệp thường qua link, `attrs.isRegularFile()` có thể là `true`, và cờ DOS phản ánh đối tượng provider đã thực sự truy vấn.

### 7.2. Yêu cầu không theo symbolic link

```java
import java.nio.file.LinkOption;

DosFileAttributes attrs =
        Files.readAttributes(path, DosFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);
```

Đây là ví dụ trong phương thức có xử lý `IOException`. `NOFOLLOW_LINKS` yêu cầu thao tác trên entry phù hợp **mà không theo symbolic link**. Những attribute view và hành vi cụ thể đối với chính symbolic link vẫn phụ thuộc provider/file system.

Tương tự, lúc lấy view:

```java
DosFileAttributeView view = Files.getFileAttributeView(
        path,
        DosFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);
```

Chỉ gọi `view.readAttributes()` hoặc setter sau khi kiểm tra `view != null`.

### 7.3. Một link có thể không có DOS view riêng

Không nên mặc định provider có khả năng đọc/ghi bốn cờ trên **chính symbolic link** chỉ vì file đích hỗ trợ DOS. Một provider có thể xử lý symlink theo cách riêng hoặc không hỗ trợ một tổ hợp thuộc tính/link option nhất định. Khi cần đảm bảo hành vi trên symlink, nên có integration test cho đúng hệ điều hành và loại volume.

### 7.4. Không biến capability check thành security check

Giữa lúc kiểm tra một đường dẫn, đọc metadata và mở file, một tiến trình khác có thể thay đổi entry hoặc symbolic link (**TOCTOU — time-of-check/time-of-use**). `NOFOLLOW_LINKS` trong một lần đọc metadata **không khóa đối tượng** và không tạo sandbox bảo mật toàn diện.

Đối với đầu vào không tin cậy, yêu cầu an toàn đường dẫn còn gồm root đáng tin, quyền truy cập, cách mở tệp, xử lý link, giới hạn tài nguyên và chính sách ownership. Cờ DOS **không được thiết kế để thay thế** các biện pháp này.

## 8. So sánh DOS attributes, Basic attributes, POSIX permissions và ACL

| Nhu cầu | API phù hợp hơn | Không được nhầm |
| --- | --- | --- |
| Loại file, byte size, timestamp, file key | `BasicFileAttributes` | Không có getter `isHidden` DOS |
| Bốn cờ readonly/hidden/system/archive trên filesystem có hỗ trợ | `DosFileAttributes` | Không phải quyền bảo mật đầy đủ |
| Thay các cờ DOS | `DosFileAttributeView` | Không nên thay ACL thay thế |
| Quyền POSIX như owner/group/permissions khi được hỗ trợ | `PosixFileAttributes`, `PosixFileAttributeView` | Không áp dụng mặc định cho mọi Windows provider |
| Quyền ACL theo provider/hệ thống hỗ trợ | `AclFileAttributeView`, `AclEntry` | Không suy từ `isReadOnly()` |
| Chỉ hỏi OS/provider coi file có hidden không | `Files.isHidden(path)` | Không phải getter DOS `isHidden()` phổ quát |
| Muốn biết lệnh ghi có thành công | Thử thao tác I/O có xử lý lỗi | `isReadOnly()==false` không bảo đảm có quyền ghi |

Các view có thể **được hỗ trợ đồng thời** hoặc chỉ một phần tùy provider. Đừng suy rằng một volume có DOS view thì không thể có ACL, hoặc có POSIX view thì bắt buộc không có DOS view.

### 8.1. `Files.isWritable` khác `isReadOnly` DOS

`Files.isWritable(path)` là phép thử khả năng ghi theo provider với các giới hạn của kiểm tra. Nó có thể trả `false` nếu không xác định được quyền; và kết quả vẫn có thể thay đổi trước khi ghi thật.

`attrs.isReadOnly()` chỉ báo **DOS attribute bit**. Hai API trả lời **những câu hỏi khác nhau**, có thể ảnh hưởng lẫn nhau nhưng không có bảo đảm luôn là phủ định chính xác của nhau.

### 8.2. Không lấy tên file thay cho hidden flag

Một file bắt đầu bằng `.` trong tên nhưng không có DOS hidden bit (hoặc không có DOS view) có thể được xem là ẩn theo một quy ước platform. Một file tên bình thường lại có thể mang DOS hidden bit trên provider hỗ trợ. Vì thế khi viết một công cụ quản lý file đa nền tảng, phải xác định câu hỏi nghiệp vụ:

- **“Có cờ DOS hidden?”** → truy vấn `DosFileAttributes.isHidden` với capability check.
- **“Có được xem là hidden theo OS/provider?”** → nghiên cứu `Files.isHidden` theo hệ thống.
- **“Tên có bắt đầu bằng dấu chấm?”** → kiểm tra `getFileName` như một quy tắc đặt tên riêng.

Ba lựa chọn không thể hoán đổi vô điều kiện.

## 9. API dựa trên tên thuộc tính `"dos:*"`

Bên cạnh typed interface, Java NIO.2 còn có overload nhận tên thuộc tính dạng chuỗi. Với provider có DOS view:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Object value = Files.getAttribute(path, "dos:hidden");
boolean hidden = (Boolean) value;
```

Đây là **đoạn minh họa** trong phương thức có biến `path` phù hợp, hỗ trợ DOS và có xử lý `IOException`. Cách gọi này trả về `Object` nên cần biết tên thuộc tính và kiểu dữ liệu trước khi ép kiểu.

Có thể cập nhật:

```java
Files.setAttribute(path, "dos:hidden", Boolean.TRUE);
```

Nhưng lệnh thực sự **sửa metadata**, nên chỉ dùng trên file có quyền sở hữu/được phép chỉnh cờ. Đừng coi nó là API “gắn nhãn hidden trong Java” mà không đổi gì trên hệ thống tệp.

Đọc một nhóm thuộc tính:

```java
java.util.Map<String, Object> values =
        Files.readAttributes(path,
                "dos:readonly,hidden,system,archive");
```

Đây là đoạn minh họa khi view `dos` được hỗ trợ. Các tên chuỗi của thuộc tính theo hợp đồng provider/API, khác tên Java getter: ví dụ **`readonly`** trong attribute string còn getter typed là **`isReadOnly()`**.

**Nên chọn API nào?**

- **Typed `DosFileAttributes`**: thường rõ ràng hơn, compiler kiểm tra tên getter/kiểu dữ liệu, thích hợp khi ứng dụng cần đủ nhóm thuộc tính DOS.
- **Typed `DosFileAttributeView`**: phù hợp khi cần đọc rồi sửa cờ bằng setter có tên rõ.
- **String-based `getAttribute/setAttribute/readAttributes`**: hữu ích khi code cần chọn thuộc tính động hoặc tích hợp một giao thức cấu hình, nhưng phải cẩn thận với tên, ép kiểu và provider support.

Không dùng `Files.readAttributes(path,"dos:*")` trên mọi filesystem mà không kiểm tra hỗ trợ. Với provider thiếu DOS view, thao tác có thể ném `UnsupportedOperationException`.

## 10. Ví dụ Java 17+ hoàn chỉnh, có fallback khi không hỗ trợ DOS

Ví dụ này:

1. Tạo một thư mục tạm và file nhị phân `sample.bin` gồm ba byte, không đụng tới dữ liệu bên ngoài.
2. Hỏi file store có hỗ trợ `DosFileAttributeView` không.
3. Lấy view với `NOFOLLOW_LINKS`; nếu không hỗ trợ, **bỏ các thao tác DOS** chứ không ép một giá trị giả.
4. Nếu hỗ trợ, đọc bằng `DosFileAttributes`, xác nhận loại file, byte size, timestamp và bốn getter.
5. Đảo cờ **hidden** và **archive** trên **file tạm riêng**, kiểm tra bằng một lần đọc mới.
6. Trong `finally`, trả hai cờ về **giá trị ban đầu**, rồi xóa file và thư mục tạm.
7. Không chỉnh `readOnly` hoặc `system` để giảm tác động phụ không cần thiết.

**Lưu ý:** Đọc view khả dụng **không bảo đảm** tài khoản được phép cập nhật cờ. Nếu setter bị từ chối hoặc hệ thống tệp có vấn đề, chương trình vẫn có thể ném `IOException`; đây là hành vi đúng khi không thể đảm bảo cập nhật/khôi phục.

Tạo file **`DosAttributeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;

public final class DosAttributeDemo {
    private static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("dos-attrs-demo-");
        Path file = directory.resolve("sample.bin");
        try {
            Files.write(file, new byte[] {1, 2, 3},
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

            boolean supported = Files.getFileStore(file)
                    .supportsFileAttributeView(DosFileAttributeView.class);
            DosFileAttributeView view = Files.getFileAttributeView(
                    file, DosFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);

            System.out.println("DOS store supported = " + supported);
            if (!supported || view == null) {
                System.out.println("DOS attributes = unavailable");
            } else {
                DosFileAttributes attrs =
                        Files.readAttributes(file, DosFileAttributes.class,
                                LinkOption.NOFOLLOW_LINKS);
                System.out.println("DOS view = available");
                System.out.println("regular file = " + attrs.isRegularFile());
                System.out.println("file size = " + attrs.size());
                System.out.println("timestamps available = "
                        + (attrs.lastModifiedTime() != null));
                System.out.println("four flags readable = "
                        + (attrs.isReadOnly() == view.readAttributes().isReadOnly()
                        && attrs.isHidden() == view.readAttributes().isHidden()
                        && attrs.isSystem() == view.readAttributes().isSystem()
                        && attrs.isArchive() == view.readAttributes().isArchive()));

                boolean initialHidden = attrs.isHidden();
                boolean initialArchive = attrs.isArchive();
                try {
                    view.setHidden(!initialHidden);
                    System.out.println("hidden changed = "
                            + (view.readAttributes().isHidden() != initialHidden));
                    view.setArchive(!initialArchive);
                    System.out.println("archive changed = "
                            + (view.readAttributes().isArchive() != initialArchive));
                } finally {
                    view.setHidden(initialHidden);
                    view.setArchive(initialArchive);
                }
                DosFileAttributes restored = view.readAttributes();
                check(restored.isHidden() == initialHidden, "hidden restored");
                check(restored.isArchive() == initialArchive, "archive restored");
                System.out.println("flags restored = true");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 DosAttributeDemo.java
java DosAttributeDemo
```

**Stdout chính xác đã kiểm thử trên môi trường Windows có DOS attribute view:**

```text
DOS store supported = true
DOS view = available
regular file = true
file size = 3
timestamps available = true
four flags readable = true
hidden changed = true
archive changed = true
flags restored = true
cleanup = done
```

Trên file system **không hỗ trợ DOS view**, nhánh đúng dự kiến là:

```text
DOS store supported = false
DOS attributes = unavailable
cleanup = done
```

Khối output trên là **mô tả nhánh xử lý theo điều kiện**, không phải kết quả thực nghiệm trên một provider không hỗ trợ. Kết quả cụ thể của phép `supportsFileAttributeView` và việc lấy view do môi trường quyết định; không được mặc định mọi filesystem phi Windows bắt buộc in đúng ba dòng này.

### 10.1. Vì sao không in bốn giá trị cờ ban đầu?

Một file mới có thể được provider gán archive bit theo chính sách, và các cờ khác cũng có thể khác nhau theo môi trường. Thay vì hardcode rằng bốn cờ luôn `false`, chương trình kiểm tra getter hoạt động, rồi lưu đúng trạng thái **trước khi cập nhật**.

Câu `four flags readable = true` trong test thể hiện hai cách đọc trên cùng file tạm trong môi trường không có tác nhân khác can thiệp đã khớp; nó **không** tuyên bố một byte pattern cố định cho bốn cờ trên mọi máy.

### 10.2. Vì sao chỉ đảo hidden và archive?

Đó là hai cờ phù hợp để minh họa setter trên file tạm và khôi phục. `setReadOnly(true)` có thể làm thao tác dọn tệp khác đi theo platform; `setSystem(true)` có ý nghĩa riêng và không cần thiết cho mục tiêu test.

Mặc dù hidden/archive thường cập nhật được trên Windows file store, mã vẫn để ngoại lệ I/O truyền lên nếu setter bị từ chối. Không viết `catch(IOException)` rồi báo “changed = true” khi việc ghi metadata đã thất bại.

### 10.3. Vì sao dùng `LinkOption.NOFOLLOW_LINKS`?

File fixture là tệp thường, nhưng việc truyền tùy chọn giúp người đọc nhận ra rằng **follow links là một phần của chính sách truy cập metadata**. Trong ứng dụng dùng input không tin cậy, cần thêm các biện pháp kiểm soát directory và quyền, chứ không coi `NOFOLLOW_LINKS` đơn lẻ là sandbox.

### 10.4. Vì sao có hai lớp `finally`?

`finally` bên trong cố trả cờ hidden/archive về trạng thái gốc khi các bước thay đổi đã bắt đầu. `finally` bên ngoài cố xóa **duy nhất file và thư mục do chương trình tạo**.

Nếu việc khôi phục cờ gặp lỗi, `IOException` vẫn có thể được ném; tiến trình dọn file có thể thành công hoặc thất bại tùy môi trường. Một chương trình quản lý tài nguyên quan trọng cần ghi nhận cả lỗi chính lẫn lỗi cleanup thay vì nuốt chúng.

### 10.5. Điều gì xảy ra nếu volume không hỗ trợ?

Khi capability check hoặc view không sẵn có, ví dụ **không gọi `DosFileAttributes.class` hoặc setter**. Đây là fallback có chủ đích. Một ứng dụng khác có thể đưa ra thông báo “chức năng này chỉ hoạt động khi file store hỗ trợ DOS attributes” hoặc sử dụng `BasicFileAttributes` nếu chỉ cần size, type và timestamp.

**Không viết code tạo `DosFileAttributes` giả với mọi cờ `false`** cho môi trường unsupported, vì làm mất thông tin “không hỗ trợ” và dễ tạo quyết định nghiệp vụ sai.

## 11. Những phương thức getter còn thừa hưởng từ `BasicFileAttributes`

Vì `DosFileAttributes extends BasicFileAttributes`, bạn có thể lấy thêm:

| Phương thức | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `isRegularFile()` | Đối tượng được nhận diện là regular file | Không suy từ tên có phần mở rộng |
| `isDirectory()` | Đối tượng được nhận diện là thư mục | Có thể khác khi follow symlink |
| `isSymbolicLink()` | Đối tượng là symbolic link ở mức được truy vấn | Hiểu `NOFOLLOW_LINKS` |
| `isOther()` | Loại entry khác các nhóm cơ bản | Không suy ra quyền truy cập |
| `size()` | Kích thước logic theo byte do provider báo | Không phải số ký tự hay dung lượng block vật lý |
| `lastModifiedTime()` | `FileTime` sửa lần cuối | Độ phân giải và chính sách cập nhật tùy provider |
| `lastAccessTime()` | `FileTime` truy cập lần cuối | Có thể không được hỗ trợ/cập nhật thường xuyên |
| `creationTime()` | `FileTime` tạo file, có thể fallback | Không phải timestamp nghiệp vụ bất biến |
| `fileKey()` | Provider-defined identity, có thể `null` | Không phải ID toàn cầu |

Có thể dùng `attrs.isDirectory()` và `attrs.isHidden()` trong cùng một biểu thức, nhưng đừng suy ra hidden flag làm cho directory không thể bị duyệt hay không thể được chương trình nhìn thấy; việc liệt kê hay đọc directory vẫn chịu quyền và chính sách OS riêng.

### 11.1. Đọc nhiều thuộc tính không tự bảo đảm nhất quán toàn file

Một object `attrs` đã đọc **không tự thay đổi** khi file bị writer khác sửa. Bốn cờ DOS, size và timestamps có thể thay đổi ở những thời điểm khác nhau. Nếu cần xác minh trạng thái sau khi cập nhật, **đọc lại**. Nếu cần một thao tác nguyên tử nhiều cờ, API setter riêng lẻ **không bảo đảm giao dịch toàn bộ bốn cờ**.

### 11.2. Giá trị `fileKey` không thay cho DOS flags

`fileKey` là thông tin định danh do provider cung cấp và có thể `null`; còn DOS flags là những thuộc tính trạng thái. Không dùng sự hiện diện của file key làm bằng chứng rằng DOS view được hỗ trợ, và không coi `setArchive` làm thay đổi danh tính tệp.

## 12. Ngoại lệ và khả năng thất bại

Những tình huống cần phân biệt:

| Sự cố | Loại biểu hiện có thể gặp | Cách ứng xử |
| --- | --- | --- |
| DOS view không được provider hỗ trợ | `view == null` hoặc `supportsFileAttributeView == false`; typed/string API có thể `UnsupportedOperationException` | Nhánh unsupported rõ ràng hoặc dừng tính năng bắt buộc |
| File bị xóa hoặc đường dẫn không tồn tại | `NoSuchFileException` / `IOException` khác theo provider | Xác minh ngữ cảnh thao tác; không coi là unsupported |
| Quyền truy cập bị từ chối | `AccessDeniedException`, `FileSystemException` hoặc `IOException` | Không tự nâng quyền, ghi nhận lỗi |
| File system/thiết bị gặp lỗi | `IOException` | Xử lý failure, không thông báo cập nhật thành công |
| Chuỗi đường dẫn không hợp lệ trước khi I/O | `InvalidPathException` (unchecked) | Xử lý tại ranh giới nhận tên đường dẫn |
| Thao tác setter bị từ chối dù view có sẵn | Thường `IOException`, tùy provider | Không coi read support là write permission |
| Đường dẫn thay đổi giữa kiểm tra và dùng | Có thể nhận metadata khác hoặc lỗi I/O | Xử lý race/TOCTOU |
| Lỗi khi khôi phục cờ hoặc xóa fixture | `IOException` khi cleanup | Ghi nhận đầy đủ; tránh làm mất lỗi chính |

**Cần phân loại đúng:** “không có attribute view” khác “không đủ quyền đọc metadata”. Hai trường hợp không nên bị gộp thành một giá trị boolean `false`.

### 12.1. Không nhận diện ngoại lệ bằng chuỗi message

Không dùng:

```java
if (ex.getMessage().contains("not supported")) {
    // ...
}
```

làm chiến lược xác định provider support: thông điệp lỗi có thể khác OS, ngôn ngữ hoặc implementation. Đây là **đoạn cố ý không nên áp dụng**. Ưu tiên capability check, `null` view, kiểu exception và thông tin có cấu trúc.

### 12.2. Thứ tự catch khi có chính sách riêng

Nếu muốn xử lý lỗi đọc metadata theo loại cụ thể:

```java
try {
    DosFileAttributes attrs =
            Files.readAttributes(path, DosFileAttributes.class);
    System.out.println(attrs.isHidden());
} catch (java.nio.file.NoSuchFileException ex) {
    System.err.println("Required entry is missing");
    throw ex;
} catch (java.nio.file.AccessDeniedException ex) {
    System.err.println("Metadata access denied");
    throw ex;
} catch (java.io.IOException ex) {
    System.err.println("Filesystem I/O failure");
    throw ex;
}
```

Đây là **mã minh họa trong phương thức có `throws IOException`**, sau khi biết view có hỗ trợ. Các catch đi từ loại cụ thể đến `IOException`. Nếu muốn phân biệt thêm `UnsupportedOperationException` (unchecked), xử lý ở boundary phù hợp, đừng đánh đồng với `NoSuchFileException`.

### 12.3. Capability check cũng có thể thay đổi

`FileStore` và các đối tượng tệp có thể thay đổi theo môi trường gắn kết mount, provider ảo hoặc hệ thống mạng. Một phép check capability không phải hợp đồng bảo đảm mãi mãi. Trong code production, vẫn xử lý lỗi ở **lời gọi đọc/ghi thực tế**, kể cả khi kiểm tra hỗ trợ đã thành công.

## 13. Metadata DOS, sao lưu và độ tin cậy của trạng thái

Một hệ thống backup hiện đại thường quan tâm tới:

- Nội dung tệp và cách đọc nhất quán.
- Kích thước và thời gian sửa như heuristic.
- Danh tính tệp hoặc bản ghi theo hệ thống.
- Dữ liệu trùng lặp, snapshot, hash, danh sách thay đổi hoặc journal.
- Quy tắc phân quyền và lưu trữ.

DOS archive bit có thể là một **tín hiệu metadata**, nhưng không tự mang đủ những điều đó. Một ứng dụng không nên nói “file đã backup” chỉ vì `isArchive() == false`, hoặc tự đánh dấu archive false để “xác nhận backup thành công” khi không có cơ chế commit và xác minh bản sao.

Tương tự, DOS hidden flag không có nghĩa file không thể liệt kê; một chương trình có quyền vẫn có thể đọc nó. System flag không bảo đảm file không thể bị xóa. Readonly flag không có hiệu lực như cơ chế bảo mật toàn diện khi tiến trình có quyền cao hoặc filesystem quy định cách xử lý khác.

**Nếu nghiệp vụ đòi trạng thái chính xác**, thiết kế dữ liệu nghiệp vụ có nguồn xác thực riêng; dùng DOS attributes đúng chỗ như một đặc tính file-system, không làm nguồn sự thật cho mọi chính sách an toàn.

## 14. Kiểm thử và tính đa nền tảng

### 14.1. Tách unit test với integration test

Các getter/nhánh điều kiện có thể được test bằng đối tượng giả lập hoặc dữ liệu đã chuẩn bị. Nhưng việc **file system thật có hỗ trợ DOS view, có cập nhật cờ hay không, và có cho phép thao tác trên symbolic link không** cần được xác minh trên môi trường triển khai.

Những hệ thống khác nhau có thể có:

- File system mặc định trên Windows hỗ trợ DOS view.
- Ổ được mount, network share hoặc provider ảo có quy tắc khác.
- Một số môi trường Unix hoặc provider hỗ trợ mô hình DOS attribute dù OS không phải Windows.
- Hệ thống không cung cấp DOS attribute view, nơi nhánh fallback phải hoạt động.

**Không viết test cố định `supported == true` hoặc `supported == false` cho mọi CI**. Chỉ ghi rõ điều kiện cần khi test một provider cụ thể; còn với test đa nền tảng, cho phép nhánh hỗ trợ hoặc unsupported theo kết quả runtime.

### 14.2. Không giả định giá trị cờ ban đầu

Một test như:

```java
if (!attrs.isArchive()) {
    throw new AssertionError("new files must be archive");
}
```

không hợp lệ làm bất biến đa nền tảng, vì cờ archive ban đầu tùy provider, thao tác tạo và chính sách filesystem. Test tốt hơn là:

1. Đọc `original.isArchive()`.
2. Nếu được phép cập nhật, gọi `setArchive(!original.isArchive())`.
3. Đọc lại và kiểm tra đã đổi.
4. Trả về giá trị cũ trong `finally`.
5. Không để test chạm file thật ngoài fixture.

### 14.3. Vì sao không ép quyền file để mô phỏng lỗi?

Nếu tự sửa ACL hoặc quyền hệ thống trên một file dùng chung, test có thể trở nên nguy hiểm hoặc không chạy được trên CI. Để test lỗi, nên sử dụng fixture tạm do chính chương trình tạo và test riêng những trường hợp permission trong môi trường được kiểm soát.

### 14.4. Cẩn trọng khi kiểm thử symbolic link

Một số môi trường cần quyền đặc biệt để tạo link hoặc có provider không hỗ trợ đầy đủ `NOFOLLOW_LINKS`. Không nên thiết kế demo cơ bản bắt buộc tạo symbolic link mới chạy được. Có thể thực hiện integration test riêng trên máy và volume cho phép, với preconditions rõ ràng.

### 14.5. Một ví dụ thiết kế helper trả “không hỗ trợ” minh bạch

Khi chỉ cần đọc DOS attrs nếu có:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.DosFileAttributes;
import java.util.Optional;

static Optional<DosFileAttributes> readDosIfSupported(Path path)
        throws IOException {
    DosFileAttributeView view = Files.getFileAttributeView(
            path, DosFileAttributeView.class);
    if (view == null) {
        return Optional.empty();
    }
    return Optional.of(view.readAttributes());
}
```

Đây là **phương thức đầy đủ để đặt trong lớp**, không ghi đè metadata và không bắt rồi che `IOException`. `Optional.empty()` có nghĩa **view không khả dụng**, không có nghĩa “bốn cờ đều false”.

Lưu ý nếu bài toán cần kiểm soát symbolic link, hãy bổ sung `LinkOption.NOFOLLOW_LINKS` theo chính sách. Một số provider có thể cung cấp view nhưng không đọc được do quyền hoặc lỗi: khi đó `readAttributes()` ném `IOException` và caller phải biết.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “DOS attributes là API lỗi thời trong Java.” | Interface NIO.2 vẫn được hỗ trợ và dùng khi file system có view này | Dùng theo capability, không theo tên lịch sử |
| “Ứng dụng chạy trên Windows thì luôn có DOS view.” | Volume/provider/mount có thể khác nhau | Kiểm tra `FileStore` và attribute view |
| “Ứng dụng chạy trên Unix thì chắc chắn không có DOS view.” | Hỗ trợ phụ thuộc provider, không chỉ OS name | Probe runtime |
| “Không hỗ trợ DOS nghĩa là tất cả cờ `false`.” | Chưa đọc được, không biết trạng thái | Phân biệt unavailable với false |
| “`DosFileAttributes` dùng để đặt giá trị cờ.” | Nó chứa kết quả đọc | Setter nằm trên `DosFileAttributeView` |
| “Đổi cờ qua view làm object attrs cũ tự cập nhật.” | Object attrs là kết quả đọc tại thời điểm đó | Gọi `readAttributes()` lại |
| “Cờ readonly là quyền bảo mật tuyệt đối.” | ACL, ownership, provider còn quy định quyền | Phân biệt security với metadata |
| “Cờ system cấp quyền admin.” | Chỉ là metadata DOS | Không dùng làm cơ chế phân quyền |
| “Cờ hidden luôn đồng nghĩa file bắt đầu bằng dấu `.`.” | Quy tắc tên khác attribute bit | Xác định chính xác nhu cầu |
| “`Files.isHidden` luôn bằng `attrs.isHidden`.” | `Files.isHidden` phụ thuộc platform/provider | Không hoán đổi vô điều kiện |
| “Archive bit chứng minh file đã được sao lưu.” | Không có thông tin bản backup, thời điểm hoặc xác thực | Dùng hệ thống backup và metadata nghiệp vụ |
| “`view != null` bảo đảm setter luôn thành công.” | Quyền, lỗi I/O và trạng thái file vẫn ảnh hưởng | Xử lý `IOException` |
| “`NOFOLLOW_LINKS` giải quyết hết race.” | File/link có thể đổi sau truy vấn | Thiết kế access an toàn |
| “DOS view cho biết file chắc chắn là regular file.” | View mô tả thuộc tính, file có thể thuộc loại khác | Dùng `isRegularFile/isDirectory` |
| “`attrs.size()` là dung lượng vật lý.” | Compression/sparse/metadata khác logical byte size | Không đồng nhất với disk allocation |
| “Có thể thay mọi flag rồi coi đó là transaction.” | Setter riêng lẻ có thể hoàn tất một phần | Thiết kế rollback và trạng thái lỗi |
| “Khôi phục luôn đặt hidden/archive về false.” | Có thể xóa mất trạng thái gốc | Lưu và phục hồi giá trị ban đầu |
| “Lỗi permission bằng với unsupported.” | Hai loại thất bại khác nhau | Không nuốt lỗi, phân nhánh rõ |
| “Chuyển đường dẫn thành String rồi sửa dấu slash giải quyết provider.” | Mất semantics file-system | Giữ kiểu `Path` và dùng API NIO.2 |
| “Test nên in fileKey và timestamp cố định.” | Phụ thuộc provider/thời điểm | Test điều kiện phù hợp, không hardcode |
| “Cờ DOS của link luôn là cờ target.” | Phụ thuộc follow links và hỗ trợ provider | Chọn `LinkOption` rõ ràng |

## 16. Bài tập thực hành có đáp án

### Bài 1 — Phát hiện hỗ trợ

Hỏi: Cách nào đáng tin cậy hơn để quyết định có đọc DOS flags của một `Path`: nhìn chuỗi `os.name` hay kiểm tra view tại runtime?

**Đáp án:** Kiểm tra `FileStore.supportsFileAttributeView(DosFileAttributeView.class)` hoặc lấy `Files.getFileAttributeView(path, DosFileAttributeView.class)` và kiểm tra khác `null`. OS name không phản ánh mọi volume/provider.

### Bài 2 — Lấy đầy đủ bốn flag

Cho `path` trên một file system hỗ trợ DOS, hãy lấy read-only, hidden, system, archive.

**Đáp án:**

```java
DosFileAttributes attrs =
        Files.readAttributes(path, DosFileAttributes.class);
boolean readonly = attrs.isReadOnly();
boolean hidden = attrs.isHidden();
boolean system = attrs.isSystem();
boolean archive = attrs.isArchive();
```

Đây là các câu lệnh trong phương thức có xử lý `IOException`, sau khi biết DOS view có hỗ trợ.

### Bài 3 — Vì sao không ép unsupported thành false?

Nếu `Files.getFileAttributeView(...)` trả `null`, có hợp lý tạo một object báo `isHidden()==false` để dùng tiếp không?

**Đáp án:** Không. `null` ở đây mang ý nghĩa view không khả dụng. “Không biết vì không hỗ trợ” khác với “đã đọc và thấy hidden flag tắt”. Có thể dùng `Optional.empty()` hoặc một kiểu kết quả ghi rõ unavailable.

### Bài 4 — Thay hidden và phục hồi

Để thử setter trên một file tạm riêng, thứ tự nào giảm nguy cơ làm mất metadata ban đầu?

**Đáp án:** Đọc `oldHidden = view.readAttributes().isHidden()`, thử `view.setHidden(!oldHidden)`, đọc lại kiểm chứng, rồi `view.setHidden(oldHidden)` trong `finally`. Nếu thao tác khôi phục thất bại, phải ghi nhận và xử lý `IOException`, không báo thành công giả.

### Bài 5 — Quyền và read-only

Nếu `attrs.isReadOnly() == false`, có thể chắc chắn gọi `Files.write` sẽ thành công không?

**Đáp án:** Không. Cờ DOS readonly không bao hàm toàn bộ ACL, quyền truy cập, quota, file lock, mount policy hay lỗi I/O. Việc ghi thực tế phải được thử theo hợp đồng và xử lý thất bại.

### Bài 6 — Hidden và tên dấu chấm

Một file `.env` trên Unix có thể được xem là hidden. Điều đó có bảo đảm `DosFileAttributes.isHidden()==true` không?

**Đáp án:** Không. Quy tắc file name bắt đầu bằng dấu chấm và cờ DOS hidden là hai khái niệm khác nhau. Hơn nữa provider đó có thể không cung cấp DOS view.

### Bài 7 — Archive có nghĩa gì?

Một chương trình thấy `attrs.isArchive() == false` và đánh dấu “đã backup thành công”. Kết luận đúng hay sai?

**Đáp án:** Không đủ cơ sở. Archive bit không xác thực vị trí, thời điểm hay tính nguyên vẹn bản backup. Muốn xác nhận sao lưu, dùng trạng thái được quản lý trong quy trình backup thực tế và cơ chế kiểm chứng phù hợp.

### Bài 8 — Vì sao phải đọc lại attrs?

Sau `view.setArchive(true)`, object `attrs` lấy trước setter có tự cập nhật không?

**Đáp án:** Không. `DosFileAttributes` là kết quả quan sát metadata tại một thời điểm. Đọc lại bằng `view.readAttributes()` hoặc `Files.readAttributes(...)` nếu cần biết trạng thái mới.

### Bài 9 — Link hoặc target?

Nếu `path` là symlink trỏ tới file khác, vì sao nên quyết định dùng `NOFOLLOW_LINKS` trước khi đọc cờ?

**Đáp án:** Vì có thể muốn hỏi metadata của **target** hoặc của **chính entry link**, hai câu hỏi khác nhau. Hành vi cụ thể còn phụ thuộc provider; `NOFOLLOW_LINKS` cũng không loại bỏ mọi race condition.

### Bài 10 — Biến nào có thể `null`?

`fileKey()` của thuộc tính DOS được đảm bảo luôn có giá trị không?

**Đáp án:** Không. Vì `DosFileAttributes` kế thừa `BasicFileAttributes`, `fileKey()` vẫn mang hợp đồng provider-defined, có thể `null`. Không ép thành kiểu số hoặc ID nghiệp vụ bắt buộc.

### Bài 11 — API typed hay string-based?

Khi muốn lấy đủ bốn cờ và loại file, bạn nên chọn `Files.readAttributes(path, DosFileAttributes.class)` hay gọi bốn `Files.getAttribute(path, "dos:...")` riêng rẽ?

**Đáp án:** Typed `DosFileAttributes` thường rõ hơn, compiler kiểm tra getter và cùng object chứa thuộc tính cơ bản. String-based hữu ích khi cần chọn tên thuộc tính động, nhưng yêu cầu cast và quản lý tên chuỗi. Cả hai đều cần DOS view được hỗ trợ.

### Bài 12 — Môi trường không hỗ trợ

Một utility cần chỉ hiển thị size và modified time khi DOS view không khả dụng. Có thể tiếp tục thế nào?

**Đáp án:** Đọc `BasicFileAttributes` bằng `Files.readAttributes(path, BasicFileAttributes.class)` nếu provider hỗ trợ nhóm basic; hiển thị những trường thực sự biết. Không giả lập giá trị DOS flags.

### Bài 13 — Kích thước và loại file

Một directory trên provider có DOS view báo `attrs.size() = 4096`. Có thể kết luận chứa chính xác 4096 byte nội dung file con không?

**Đáp án:** Không. `size()` là kích thước do provider báo cho **entry**; đối với directory, ý nghĩa không đồng nhất với tổng dung lượng các file con. Muốn thống kê cây phải duyệt và tính theo hợp đồng riêng.

### Bài 14 — Test trên Windows và Unix

Một test chứa `assertTrue(store.supportsFileAttributeView(DosFileAttributeView.class))` rồi chạy trên mọi CI. Có ổn không?

**Đáp án:** Không nếu không có precondition provider. Test đa nền tảng phải cho phép nhánh unsupported hoặc chỉ chạy assertions yêu cầu DOS trong môi trường đã kiểm soát. Không suy từ OS name.

### Bài 15 — Mã kiểm tra khả năng

Cho một `Path path`, hãy viết hàm trả kết quả đọc DOS attributes hoặc không khả dụng.

**Đáp án:**

```java
static java.util.Optional<DosFileAttributes> readIfAvailable(Path path)
        throws java.io.IOException {
    DosFileAttributeView view = Files.getFileAttributeView(
            path, DosFileAttributeView.class);
    return view == null
            ? java.util.Optional.empty()
            : java.util.Optional.of(view.readAttributes());
}
```

Đây là **phương thức để đặt trong lớp có import tương ứng**. Nếu view có sẵn nhưng I/O thất bại, ngoại lệ tiếp tục truyền lên; không diễn giải lỗi truy cập thành “view không khả dụng”.

## 17. Checklist áp dụng trong dự án Java

- [ ] Xác định bài toán thực sự cần **cờ DOS** hay chỉ cần basic metadata/quyền truy cập.
- [ ] Kiểm tra view tại runtime trên **đúng `Path` và `FileStore`**, không suy từ `os.name`.
- [ ] Phân biệt **unsupported**, **flag false**, **I/O failure**, **permission denied**.
- [ ] Dùng `DosFileAttributes` để đọc bốn cờ, `DosFileAttributeView` để đặt cờ.
- [ ] Biết `DosFileAttributes` kế thừa `BasicFileAttributes` và dùng các trường cơ bản khi cần.
- [ ] Không nhầm read-only DOS với ACL hay bảo đảm ghi được.
- [ ] Không nhầm DOS hidden với tên dấu chấm hoặc `Files.isHidden` ở mọi provider.
- [ ] Không xem system flag là chứng nhận file thuộc hệ điều hành hoặc quyền quản trị.
- [ ] Không xem archive bit là nguồn sự thật của hệ thống backup.
- [ ] Không thay cờ của file/directory không thuộc quyền quản lý của ứng dụng.
- [ ] Khi test setter, lưu **giá trị cũ**, khôi phục trong `finally` và xử lý lỗi phục hồi.
- [ ] Không mặc định update nhiều cờ là một transaction nguyên tử.
- [ ] Khi thao tác symbolic link, quyết định rõ `NOFOLLOW_LINKS` và giới hạn provider.
- [ ] Xử lý `IOException`/`UnsupportedOperationException` đúng phân loại, không dựa vào chuỗi message.
- [ ] Không coi metadata snapshot là file lock hoặc cơ chế chống TOCTOU.
- [ ] Dùng file tạm có phạm vi rõ khi thử thay hidden/archive; không chỉnh cờ system/readonly tùy tiện.
- [ ] Kiểm thử nhánh hỗ trợ và không hỗ trợ ở môi trường có preconditions, không hardcode bốn flag ban đầu.
- [ ] Ghi rõ baseline Java: nhóm DOS attribute API xuất hiện từ Java 7; `Path.of` dùng trong demo từ Java 11; chạy ví dụ với JDK 17+.

## 18. Tổng kết

**`DosFileAttributes`** là interface hiện hành để đọc **readonly, hidden, system, archive** cùng những trường thuộc tính cơ bản **trên file system/provider hỗ trợ**. Khi cần thay các cờ, sử dụng **`DosFileAttributeView`** và setter có tên tương ứng. Cần kiểm tra `FileStore.supportsFileAttributeView` hoặc lấy view bằng `Files.getFileAttributeView`, chấp nhận trường hợp unsupported, và xử lý lỗi I/O ngay cả khi capability check thành công.

Đừng đồng nhất **cờ DOS** với **ACL/quyền bảo mật**, **trạng thái backup đã xác thực** hoặc **quy ước tên file ẩn**. Đọc metadata không khóa file và không bảo đảm snapshot nguyên tử; cập nhật nhiều cờ không phải transaction. Với Java 17+, phương pháp kiểm tra hỗ trợ, đọc typed attributes, đổi cờ trên file tạm và khôi phục trạng thái ban đầu cho phép viết phần mềm quản lý file thực tế, đa môi trường và ít gây tác dụng phụ hơn. Những nguyên tắc Java NIO.2 từ Java 7 vẫn hoàn toàn hữu ích trong các hệ thống Java hiện đại.
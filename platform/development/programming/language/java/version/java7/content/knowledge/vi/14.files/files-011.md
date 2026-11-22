# Ngoại lệ cụ thể và thông tin đường dẫn khi thao tác `Files` thất bại trong Java

## 1. Vì sao cần phân biệt lỗi của hệ thống tệp?

Một thao tác tệp tưởng chừng đơn giản có thể thất bại vì nhiều lý do khác nhau:

- Tệp nguồn đã bị xóa hoặc thư mục cha không tồn tại.
- Đường dẫn đích đã có một tệp, trong khi ứng dụng chỉ cho phép tạo mới.
- Thư mục đang chứa dữ liệu nên không thể xóa theo cách thông thường.
- Quyền truy cập không cho phép đọc, ghi, đổi tên hoặc xóa.
- Tên đường dẫn không hợp lệ ngay từ lúc phân tích, trước khi có thao tác I/O.
- Hệ thống tệp, thiết bị lưu trữ, mạng, provider hoặc chức năng được yêu cầu gặp lỗi.
- Hai đường dẫn có quan hệ không phù hợp với thao tác (ví dụ di chuyển nguyên tử không được hỗ trợ).

Nếu ứng dụng chỉ viết:

```java
try {
    Files.readAllBytes(path);
} catch (IOException ex) {
    System.out.println("File error");
}
```

thì người dùng và người vận hành không biết **tệp nào, thao tác nào, vì sao thất bại và hành động tiếp theo là gì**. Đoạn trên là mã minh họa trong phương thức có biến `path` và `import java.nio.file.Files; import java.io.IOException;`; nó còn cố ý đơn giản quá mức và không phải mẫu xử lý lỗi nên sao chép nguyên trạng.

Từ **Java 7**, Java NIO.2 cung cấp lớp tiện ích `java.nio.file.Files` cùng các **ngoại lệ cụ thể** trong gói `java.nio.file`. Chúng cho phép xử lý chính xác hơn thay vì dựa vào việc so khớp chuỗi của `IOException.getMessage()`. Những API này **vẫn hiện hành trên Java 17+ và Java hiện đại**.

Mục tiêu bài học:

1. Nhận biết các ngoại lệ hay gặp khi đọc, ghi, tạo, xóa, sao chép hoặc di chuyển tệp.
2. Hiểu quan hệ kiểu giữa `IOException`, `FileSystemException` và các ngoại lệ chuyên biệt.
3. Trích xuất thông tin `getFile()`, `getOtherFile()`, `getReason()` một cách có kiểm tra `null`.
4. Viết `catch` đúng thứ tự và phân biệt lỗi I/O với lỗi phân tích `Path`.
5. Kiểm thử tình huống thất bại có thể tái lập, không phụ thuộc một thông báo lỗi riêng của hệ điều hành.
6. Thiết kế thông báo cho người dùng và log kỹ thuật vừa hữu ích vừa không lộ dữ liệu nhạy cảm.

## 2. Sơ đồ phân cấp ngoại lệ liên quan đến `Files`

Các ngoại lệ chuyên biệt của Java NIO.2 có quan hệ kiểu gần như sau:

```text
java.lang.Exception
└── java.io.IOException                       (checked)
    └── java.nio.file.FileSystemException      (checked)
        ├── NoSuchFileException
        ├── FileAlreadyExistsException
        ├── AccessDeniedException
        ├── DirectoryNotEmptyException
        ├── NotDirectoryException
        ├── FileSystemLoopException
        └── AtomicMoveNotSupportedException

java.lang.RuntimeException                     (unchecked)
├── java.nio.file.InvalidPathException
├── java.io.UncheckedIOException
└── các lỗi sử dụng API/đối số khác tùy thao tác
```

Đây là **sơ đồ khái niệm**, không phải mã Java thực thi. Các lớp kể tên vẫn có trong API Java hiện đại. Một số ngoại lệ thuộc phạm vi liên quan khác không nhất thiết là con của `FileSystemException`, nhưng vẫn có thể phát sinh khi thực hiện I/O hoặc duyệt cây tệp.

Điểm cần ghi nhớ:

- `IOException` là **checked exception**. Nếu phương thức `Files` khai báo có thể ném nó, mã Java phải bắt hoặc khai báo `throws IOException`.
- `FileSystemException` kế thừa `IOException` và bổ sung các trường thông tin đường dẫn.
- `NoSuchFileException`, `FileAlreadyExistsException`, `AccessDeniedException`... kế thừa `FileSystemException`.
- `InvalidPathException` là **unchecked exception** phát sinh khi chuỗi không thể chuyển thành `Path` theo quy tắc của provider. Nó **không phải** con của `IOException`.
- `UncheckedIOException` gói một `IOException` vào dạng unchecked, thường đáng chú ý khi các API lazy/stream thực hiện I/O trong quá trình duyệt.
- Ngoại lệ thực tế phụ thuộc **loại thao tác, các option, provider và trạng thái file system**. Không phải mọi provider đều buộc phải báo đúng cùng một subclass cho mọi lỗi; phải có đường xử lý `IOException` tổng quát.

## 3. Bảng nhận diện lỗi theo thao tác

| Ngoại lệ | Tình huống thường gặp | Hướng xử lý cần cân nhắc |
| --- | --- | --- |
| `NoSuchFileException` | Đọc một tệp không tồn tại; một thành phần đường dẫn cần thiết không tồn tại | Kiểm tra tên đầu vào, xác định tài nguyên có bắt buộc không, không mặc định tự tạo |
| `FileAlreadyExistsException` | `Files.createFile(path)` hoặc `CREATE_NEW` gặp đối tượng đã tồn tại | Đổi tên, từ chối trùng, hoặc đổi chính sách ghi đè theo nghiệp vụ |
| `DirectoryNotEmptyException` | Xóa thư mục vẫn chứa entry | Chỉ xóa đệ quy nếu **được phép rõ ràng**, hoặc yêu cầu xử lý nội dung trước |
| `AccessDeniedException` | Đọc/ghi/xóa bị từ chối theo quyền hoặc chính sách hệ thống tệp | Kiểm tra cấu hình quyền; không tự nâng quyền hay thử lặp vô hạn |
| `NotDirectoryException` | Một thành phần được kỳ vọng là thư mục thực ra không phải | Kiểm tra cấu trúc đường dẫn và loại đối tượng |
| `FileSystemLoopException` | Duyệt cây có vòng liên kết khi theo symbolic links | Xem lại chính sách theo link, phát hiện vòng và tránh duyệt vô hạn |
| `AtomicMoveNotSupportedException` | Yêu cầu `ATOMIC_MOVE` nhưng hệ thống không hỗ trợ | Xác định có chấp nhận fallback phi nguyên tử hay phải thất bại |
| `FileSystemException` (lớp tổng quát) | Lỗi của provider không được biểu diễn bởi subclass cụ thể | Đọc thông tin đường dẫn/reason, giữ cause, xử lý I/O phù hợp |
| `IOException` (khác các trường hợp trên) | Lỗi đọc/ghi, thiết bị, stream hoặc thao tác I/O khác | Không đoán loại lỗi từ message; báo cáo và bảo toàn cause |
| `InvalidPathException` | Chuỗi đường dẫn chứa ký tự/cú pháp không hợp lệ | Xác thực đầu vào, không thực hiện I/O, cung cấp thông báo an toàn |

**Quan trọng:** “Thường gặp” không đồng nghĩa “mọi máy sẽ ném đúng subclass đó”. Ví dụ provider khác nhau có thể trả một `FileSystemException` tổng quát hoặc `IOException` khác. Mã xử lý lỗi nên ưu tiên loại cụ thể **khi có thể**, đồng thời chấp nhận một nhánh lỗi chưa phân loại.

## 4. `FileSystemException`: thông tin quan trọng về đường dẫn

Lớp `FileSystemException` mang tối đa ba mảnh thông tin có cấu trúc:

```java
String file = ex.getFile();
String otherFile = ex.getOtherFile();
String reason = ex.getReason();
```

Đoạn trên nằm trong ngữ cảnh có `ex` là `FileSystemException`.

| Getter | Ý nghĩa | Có thể `null`? |
| --- | --- | --- |
| `getFile()` | Đường dẫn tệp liên quan đến ngoại lệ, dưới dạng chuỗi | Có |
| `getOtherFile()` | Đường dẫn thứ hai, nếu thao tác có liên quan hai đường dẫn như copy/move | Có |
| `getReason()` | Lý do chi tiết do provider hoặc người tạo ngoại lệ cung cấp | Có |
| `getMessage()` | Chuỗi thông điệp được tạo để đọc, có thể kết hợp đường dẫn và lý do | Không nên coi cấu trúc là ổn định để phân tích |

Lưu ý: Các getter trả **`String`**, **không** trả đối tượng `Path`. `getFile()` và `getOtherFile()` có thể không đầy đủ hoặc không có; `getReason()` có thể thiếu hoặc chứa lời giải thích phụ thuộc hệ điều hành.

### 4.1. Lấy dữ liệu bằng getter, không giải mã `getMessage()`

Ví dụ tạo một ngoại lệ để minh họa cấu trúc **mà không cần gây lỗi I/O thật**:

```java
import java.nio.file.FileSystemException;

FileSystemException ex =
        new FileSystemException("source.bin", "target.bin", "demo");

System.out.println(ex.getFile());      // source.bin
System.out.println(ex.getOtherFile()); // target.bin
System.out.println(ex.getReason());    // demo
```

Đây là mã minh họa trong phương thức. Một ngoại lệ được **tạo thủ công** chỉ để dạy getters; nó **không chứng minh** một lần gọi `Files.copy` thật sẽ cung cấp mọi trường này ở mọi provider.

Khi thực hiện một thao tác thất bại, `getMessage()` có thể chứa đường dẫn đầy đủ, lý do bằng ngôn ngữ của hệ điều hành hoặc mã thông báo nội bộ. **Không phân nhánh logic dựa trên văn bản tiếng Anh** như `message.contains("Permission denied")`: message không phải API có cấu trúc và có thể thay đổi theo nền tảng.

### 4.2. Ví dụ lấy thông tin và kiểm tra `null`

```java
import java.nio.file.FileSystemException;

static void inspect(FileSystemException ex) {
    String source = ex.getFile() == null ? "(unknown)" : ex.getFile();
    String destination = ex.getOtherFile() == null
            ? "(not supplied)" : ex.getOtherFile();
    String detail = ex.getReason() == null
            ? "(no provider reason)" : ex.getReason();

    System.err.println("type=" + ex.getClass().getSimpleName());
    System.err.println("source=" + source);
    System.err.println("other=" + destination);
    System.err.println("reason=" + detail);
}
```

Đây là **phương thức minh họa cho log kỹ thuật nội bộ**, cần đặt trong một lớp. Không sao chép nguyên việc in đường dẫn và reason đầy đủ vào response công khai: đường dẫn có thể chứa tên người dùng, đường dẫn mạng, thư mục riêng hoặc cấu trúc máy chủ.

Tốt hơn nên ghi **operation ID, tên tác vụ và mã lỗi ổn định** cho người dùng, còn thông tin kỹ thuật được phân quyền và che bớt theo quy định. Ví dụ đối với upload thất bại, có thể hiển thị “Không thể lưu tệp do tệp đích đã tồn tại” thay vì công bố toàn bộ đường dẫn máy chủ.

### 4.3. Khi chỉ có một đường dẫn

Các lỗi `NoSuchFileException` khi đọc một tệp hoặc `FileAlreadyExistsException` khi tạo trùng thường có `getFile()` nhưng **không nhất thiết** có `getOtherFile()`. Vì vậy đừng dựa vào `getOtherFile().isEmpty()` trước khi kiểm tra `null`.

### 4.4. Khi thao tác có hai đường dẫn

Các thao tác:

```java
Files.copy(source, destination);
Files.move(source, destination);
```

liên quan cả nguồn lẫn đích. Nếu `FileSystemException` xảy ra, provider có thể cung cấp thông tin về một hoặc hai đường dẫn. **Không mặc định `getFile()` luôn là nguồn, `getOtherFile()` luôn là đích** trong mọi kiểu lỗi/provider. Ứng dụng vẫn nên ghi riêng ngữ cảnh `operation`, `source`, `destination` đã biết (được kiểm soát quyền khi log), rồi xem các getters là dữ liệu bổ sung của ngoại lệ.

## 5. `NoSuchFileException`: đường dẫn không dẫn tới tài nguyên cần thiết

Một tình huống phổ biến là đọc tệp bắt buộc chưa tồn tại:

```java
Path path = Path.of("missing.txt");
Files.readAllBytes(path);
```

Đây là **đoạn cố ý có thể ném lỗi I/O** nếu tệp không tồn tại, trong phương thức khai báo `throws IOException`. Provider mặc định thông thường ném `NoSuchFileException`; thông tin `getFile()` có thể giúp chỉ ra đường dẫn liên quan.

### Khi nào phải báo lỗi, khi nào có thể bỏ qua?

- Nếu tệp là **đầu vào bắt buộc**, thiếu tệp là lỗi của thao tác: báo rõ sự cố và kết thúc/phục hồi có kiểm soát.
- Nếu hành vi được thiết kế là **xóa nếu có**, `Files.deleteIfExists(path)` là API diễn đạt đúng ý định; trả `false` khi mục tiêu không tồn tại.
- Nếu tệp có thể được sinh ra hợp lệ khi chưa có, hãy dùng API tạo phù hợp, **không tự động tạo mọi đường dẫn chỉ vì catch `NoSuchFileException`**.
- Không dùng `Files.exists(path)` rồi tin rằng lần đọc kế tiếp chắc chắn thành công: tệp có thể bị xóa/đổi tên giữa hai lần gọi.

Ví dụ:

```java
boolean deleted = Files.deleteIfExists(path);
```

Nếu tệp không có, `deleted` là `false`. Nếu có nhưng xóa thất bại vì quyền, thư mục không rỗng hoặc lỗi khác, phương thức vẫn có thể ném ngoại lệ; tên “IfExists” **không có nghĩa nuốt mọi lỗi**.

### `NoSuchFileException` không phải lúc nào cũng là “sai tên file cuối”

Một thành phần trung gian của đường dẫn có thể bị thiếu. Ví dụ `data/2026/report.bin` thất bại vì thư mục `data/2026` chưa tồn tại, không nhất thiết vì tên `report.bin` sai. Cần xem đường dẫn đã biết, thao tác yêu cầu và thông tin từ provider.

**Không dùng `getMessage()` để đoán chính xác thành phần nào bị thiếu** nếu API không có dữ liệu cấu trúc tương ứng.

## 6. `FileAlreadyExistsException`: xung đột tên khi tạo mới

Khi muốn tạo file chỉ nếu chưa tồn tại:

```java
Path target = Path.of("result.bin");
Files.createFile(target);
```

Nếu `target` đã tồn tại, provider mặc định thường ném `FileAlreadyExistsException`. Tương tự, với output stream:

```java
Files.newOutputStream(target,
        java.nio.file.StandardOpenOption.CREATE_NEW,
        java.nio.file.StandardOpenOption.WRITE);
```

Đây là các câu lệnh minh họa trong ngữ cảnh có xử lý `IOException`; khi mở output stream thật, phải đóng stream bằng `try-with-resources`.

### Tại sao `CREATE_NEW` tốt hơn tự kiểm tra trước?

Mẫu dễ gặp nhưng có race:

```java
if (!Files.exists(target)) {
    Files.createFile(target);
}
```

Một tiến trình khác có thể tạo file sau phép kiểm tra `exists` nhưng trước `createFile`. Đây là vấn đề *time-of-check to time-of-use* (TOCTOU). Phép tạo mới với ngữ nghĩa “thất bại nếu đã tồn tại” được thực hiện như một yêu cầu của **chính thao tác tạo**, phù hợp hơn cho chính sách không ghi đè.

**Đừng xử lý `FileAlreadyExistsException` bằng cách xóa tệp cũ ngay lập tức.** Tệp có thể thuộc người dùng khác, chứa dữ liệu quan trọng hoặc tượng trưng cho một phiên làm việc đồng thời. Hành vi nên theo hợp đồng nghiệp vụ: báo trùng, tạo tên mới, cập nhật có điều kiện hoặc dùng một quy trình thay thế file an toàn.

### `Files.createDirectories` khác `Files.createDirectory`

- `Files.createDirectory(path)` muốn tạo **một thư mục**; nếu mục tiêu đã tồn tại, thường phát sinh lỗi.
- `Files.createDirectories(path)` tạo các thư mục cha còn thiếu và **không báo lỗi chỉ vì đường dẫn đích đã là một thư mục tồn tại**.
- Nếu một thành phần cần là thư mục nhưng thực tế là tệp thường, `createDirectories` vẫn có thể thất bại, thường qua `FileAlreadyExistsException` hoặc ngoại lệ file system phù hợp.

Không phải mọi thao tác tạo thư mục “đã có thì bỏ qua” đều an toàn nếu đường dẫn có thể do người dùng đối kháng kiểm soát: phải xét quyền, symbolic link và root.

## 7. `DirectoryNotEmptyException`: xóa thư mục còn nội dung

`Files.delete(path)` không tự động xóa toàn bộ cây thư mục:

```java
Files.delete(directory);
```

Nếu `directory` chứa tệp hoặc thư mục con, provider mặc định thường ném `DirectoryNotEmptyException`. Điều này giúp tránh vô tình xóa sâu nhiều dữ liệu.

**Cần phân biệt hai ý định:**

1. **Xóa chính thư mục rỗng:** `Files.delete(directory)` hoặc `Files.deleteIfExists(directory)` là lựa chọn phù hợp; lỗi “không rỗng” là thông tin cần xử lý.
2. **Xóa đệ quy toàn bộ cây:** cần quy trình riêng với `Files.walkFileTree`, quyền và kiểm tra an toàn. Không bắt `DirectoryNotEmptyException` rồi tự động xóa mọi phần tử bên dưới trừ khi người dùng và nghiệp vụ **đã cho phép hành vi phá hủy đó**.

`Files.deleteIfExists(directory)` chỉ tránh lỗi **đường dẫn không tồn tại** theo hợp đồng; **nó không xóa đệ quy** và vẫn có thể ném `DirectoryNotEmptyException`.

Một tình huống kiểm thử:

```java
Path dir = Files.createTempDirectory("not-empty-");
Path child = Files.createFile(dir.resolve("child.txt"));

try {
    Files.delete(dir); // Cố ý lỗi: thư mục vẫn có child.
} finally {
    Files.deleteIfExists(child);
    Files.deleteIfExists(dir);
}
```

Đây là đoạn minh họa trong phương thức có `throws IOException`. Mã không bắt cụ thể `DirectoryNotEmptyException` ở đây nên ngoại lệ có thể thoát ra khỏi khối, sau khi `finally` cố dọn tệp/thư mục. Chương trình đầy đủ ở mục 14 cho thấy cách catch và in đúng tên ngoại lệ.

## 8. `AccessDeniedException`: bị từ chối truy cập

Khi quyền hệ thống tệp hoặc chính sách môi trường không cho phép thao tác, provider có thể ném `AccessDeniedException`:

```java
try {
    Files.readAllBytes(source);
} catch (java.nio.file.AccessDeniedException ex) {
    System.err.println("Cannot access required input");
    throw ex;
}
```

Đây là đoạn minh họa bên trong phương thức khai báo `throws IOException`, với biến `source` kiểu `Path`. Ngoại lệ này có thể phát sinh khi đọc, tạo, ghi, xóa hoặc thao tác file khác, nhưng **không phải mọi lỗi quyền ở mọi hệ điều hành đều được báo đúng subclass này**.

### Không đoán nguyên nhân chỉ từ loại ngoại lệ

Nguyên nhân thực tế có thể liên quan đến ACL, quyền của user chạy ứng dụng, thư mục được bảo vệ, file đang bị phần mềm khác sử dụng hoặc hành vi của provider. Có trường hợp provider trả `FileSystemException` chung kèm `reason`, thay vì `AccessDeniedException`.

Đừng suy ra rằng:

- Tệp chắc chắn tồn tại, chỉ vì nhận lỗi truy cập.
- Người dùng ứng dụng chắc chắn thiếu quyền theo logic nghiệp vụ.
- Chỉ cần chạy lại với đặc quyền quản trị là cách giải quyết phù hợp.
- Có thể đưa nguyên đường dẫn máy chủ vào thông báo cho người dùng.

Một hướng xử lý thường hữu ích là ghi nhận operation, loại ngoại lệ, môi trường/quyền được cấu hình, rồi cung cấp hướng dẫn hoặc mã lỗi ổn định. Không cần cố tái tạo một `AccessDeniedException` bằng cách sửa quyền thư mục trong unit test chạy trên mọi OS: test như vậy dễ không ổn định trên CI hoặc tài khoản có đặc quyền khác nhau.

## 9. Các ngoại lệ chuyên biệt khác đáng biết

### 9.1. `NotDirectoryException`

Khi một thao tác cần một đường dẫn hoặc thành phần là **thư mục**, nhưng đối tượng thực tế không phải thư mục, provider có thể ném `NotDirectoryException`.

Ví dụ ứng dụng muốn truy cập `data/file.txt/child.bin`, trong khi `data/file.txt` là tệp thường, không phải thư mục. Đây không phải cùng vấn đề với một tệp đầu vào đơn thuần bị thiếu. Không phải mọi provider đều bắt buộc phân biệt bằng cùng subclass; vẫn cần nhánh `IOException` dự phòng.

### 9.2. `FileSystemLoopException`

Khi duyệt cây thư mục và **theo symbolic link**, có thể gặp vòng liên kết. Các API như `Files.walkFileTree` với `FileVisitOption.FOLLOW_LINKS` có thể cung cấp lỗi liên quan `FileSystemLoopException` cho bước duyệt thất bại.

Không tự viết vòng lặp theo symbolic link mà không có chính sách phát hiện vòng và giới hạn độ sâu. Trong môi trường có đường dẫn không tin cậy, chính sách có theo link hay không phải được xác định trước.

### 9.3. `AtomicMoveNotSupportedException`

Khi yêu cầu một thao tác di chuyển **nguyên tử** qua:

```java
Files.move(source, destination,
        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
```

nếu provider không thể thực hiện di chuyển nguyên tử theo hợp đồng, có thể ném `AtomicMoveNotSupportedException`.

Điều đó **khác** việc file đích trùng tên, source bị thiếu hoặc quyền bị từ chối. Nếu ứng dụng cần bảo đảm nguyên tử để tránh trạng thái nửa chừng, không được âm thầm fallback sang di chuyển không nguyên tử chỉ để cho chương trình chạy tiếp. Hãy xác định rõ chính sách fallback, kiểm chứng môi trường triển khai và xử lý thất bại.

### 9.4. `FileSystemException` tổng quát

Có những lỗi không được biểu diễn bằng một subclass chuyên biệt hoặc provider không thể cung cấp nguyên nhân cụ thể. Khi đó `FileSystemException` chung vẫn có thể mang `file`, `otherFile` và `reason`. Một nhánh `catch (FileSystemException ex)` sau các lớp chuyên biệt có thể ghi nhận thông tin bổ sung, nhưng **vẫn không nên phân tích text `getReason()` để quyết định logic nghiệp vụ cứng**.

## 10. `InvalidPathException`: lỗi phân tích tên, không phải lỗi đọc file

`InvalidPathException` không kế thừa `IOException`. Nó xảy ra khi chuỗi không thể chuyển thành đường dẫn theo quy tắc `FileSystem`:

```java
import java.nio.file.InvalidPathException;
import java.nio.file.Path;

try {
    Path.of(String.valueOf((char) 0));
} catch (InvalidPathException ex) {
    System.out.println("Invalid path input");
}
```

Đây là đoạn minh họa chạy với file system mặc định phổ biến, nơi ký tự NUL không hợp lệ trong tên đường dẫn. Provider khác có thể có quy tắc phân tích khác. `Path.of` có từ **Java 11**; việc tạo `Path` qua `Paths.get` từ Java 7 cũng có thể gặp `InvalidPathException`.

`InvalidPathException` có các thông tin như `getInput()`, `getReason()` và `getIndex()`, khác với `FileSystemException.getFile/getOtherFile`. `getIndex()` có thể bằng `-1` nếu không có vị trí lỗi cụ thể.

**Không chỉ catch `IOException` rồi nghĩ mọi lỗi đường dẫn đã được xử lý.** Nếu ứng dụng nhận tên đường dẫn từ API bên ngoài, hãy có ranh giới xác thực/catch `InvalidPathException` phù hợp. Khi báo lỗi công khai, không in nguyên `getInput()` nếu chuỗi có thể chứa dữ liệu nhạy cảm hoặc ký tự điều khiển gây hỏng log.

### Một số lỗi không phải `IOException`

Tùy API/đối số, cũng có thể gặp `IllegalArgumentException`, `UnsupportedOperationException` hoặc loại unchecked khác. Ví dụ một option không được provider hỗ trợ có thể dẫn đến lỗi khác với lỗi thiếu file. **Không nên viết `catch (Exception)` bao trùm mọi lỗi rồi tự chuyển tất cả thành “file not found”.**

## 11. Cách viết `catch` đúng thứ tự và giữ nguyên cause

Vì `NoSuchFileException`, `FileAlreadyExistsException` và `AccessDeniedException` là các lớp con của `FileSystemException`, còn `FileSystemException` là con của `IOException`, nhánh `catch` phải đi **từ cụ thể đến tổng quát**.

Ví dụ phương thức đọc bắt buộc:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

static byte[] loadRequired(Path path) throws IOException {
    try {
        return Files.readAllBytes(path);
    } catch (NoSuchFileException ex) {
        System.err.println("Required file is missing");
        throw ex;
    } catch (AccessDeniedException ex) {
        System.err.println("Access to required file was denied");
        throw ex;
    } catch (FileSystemException ex) {
        System.err.println("Filesystem failure: "
                + ex.getClass().getSimpleName());
        throw ex;
    }
}
```

Đây là **phương thức cần đặt trong một lớp**. Những loại `IOException` không nằm trong các nhánh trên vẫn được truyền ra vì phương thức khai báo `throws IOException`. Mã không ép mọi nguyên nhân về một loại lỗi duy nhất.

### Vì sao phải đặt `catch(IOException)` sau các subclass?

Đoạn sau là **ví dụ cố ý không biên dịch**:

```java
try {
    Files.readAllBytes(path);
} catch (IOException ex) {
    // Bắt tất cả IOException trước.
} catch (NoSuchFileException ex) {
    // Không thể tới đây: subclass đã bị catch phía trên bao phủ.
}
```

Với hai lớp có quan hệ cha–con, compiler từ chối nhánh catch con không thể đạt tới. Trong mã thực tế, có thể dùng nhiều nhánh subclass trước một nhánh `catch(IOException ex)` cuối, hoặc để `throws IOException` truyền lên tầng gọi nếu tầng hiện tại không thể xử lý tốt.

### Khi nào dùng multi-catch?

Nếu nhiều lỗi có cùng chính sách, có thể viết:

```java
try {
    Files.copy(source, destination);
} catch (NoSuchFileException | AccessDeniedException ex) {
    System.err.println("Copy cannot proceed: "
            + ex.getClass().getSimpleName());
    throw ex;
}
```

Đây là đoạn trong phương thức khai báo `throws IOException`, có hai biến `Path` và các import tương ứng. Java cho phép multi-catch giữa các loại không nằm trong quan hệ subtype trực tiếp với nhau. Không được đưa đồng thời `FileSystemException` và `NoSuchFileException` vào **cùng một multi-catch**, vì một loại là lớp cha của loại kia.

### Đừng làm mất exception gốc

Sai về chẩn đoán:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot read file");
}
```

Cách này bỏ mất **cause**. Khi cần chuyển tầng lỗi, giữ nguyên chuỗi nguyên nhân:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot read required input", ex);
}
```

Trong hai snippet trên, khối `catch` là minh họa nằm trong một cấu trúc `try` hợp lệ. Ở tầng ứng dụng, việc chọn checked hay unchecked, và nội dung thông điệp, phải theo hợp đồng API. Nếu không cần chuyển đổi loại lỗi, **rethrow ngoại lệ gốc** có thể giữ thông tin chuyên biệt tốt hơn.

## 12. Thông tin đường dẫn và bảo mật log

Một ngoại lệ có thể chứa:

- Tên thư mục home, tên tài khoản hệ điều hành hoặc vùng mount nội bộ.
- Đường dẫn mạng/UNC, tên máy chủ hoặc thư mục được bảo vệ.
- Tên file do người dùng cung cấp, có thể chứa ký tự điều khiển hoặc dữ liệu riêng tư.
- Lý do từ provider, có thể mang chi tiết của hệ thống triển khai.

Do đó, có hai nhóm người cần thông tin khác nhau:

| Người nhận | Nên cung cấp | Cần tránh |
| --- | --- | --- |
| Người dùng cuối | Mô tả hành động thất bại, nguyên nhân ở mức phù hợp, mã lỗi có thể tra cứu | Toàn bộ absolute path của server, stack trace, chi tiết hệ thống |
| Log kỹ thuật có kiểm soát | Loại exception, operation, correlation ID, nguồn/đích đã được lọc, cause, thời điểm | Log đầu vào chưa escape hoặc chứa bí mật ở nơi không phân quyền |
| Hệ thống giám sát | Loại lỗi và nhóm operation có cấu trúc, tỷ lệ lỗi, môi trường | Dùng chuỗi `getMessage()` làm khóa metric không ổn định |
| Test tự động | Class ngoại lệ, trạng thái file trước/sau, giá trị getter phù hợp | So khớp nguyên thông báo lỗi phụ thuộc OS/ngôn ngữ |

### Mẫu suy nghĩ theo ngữ cảnh thao tác

Với một thao tác:

```java
Files.copy(source, destination);
```

hãy giữ riêng **operation = COPY**, đường dẫn do ứng dụng đã xác định, rồi khi có lỗi xem:

- `ex.getClass().getSimpleName()` — loại lỗi, có giá trị phân loại.
- `ex.getFile()` — có đường dẫn liên quan không?
- `ex.getOtherFile()` — có một đường dẫn thứ hai không?
- `ex.getReason()` — có giải thích phụ thuộc provider không?
- `ex.getCause()` và các suppressed exceptions nếu có — có lỗi gốc khác không?

**Không tự kết luận** rằng chỉ một chuỗi `getMessage()` là đủ cho mọi công cụ điều tra. Trong mã production, log nên có request ID, operation, trạng thái nghiệp vụ và chính sách che dữ liệu; nhưng đừng tạo thêm log trùng lặp ở mọi tầng khi lỗi đã được ghi rõ ở boundary.

### Tên đường dẫn không giống dữ liệu an toàn để hiển thị

Nếu chỉ muốn đưa tên cuối cho người dùng, vẫn phải cân nhắc rằng nó có thể do người dùng tự nhập và chứa dữ liệu nhạy cảm. Việc gọi `Path.of(ex.getFile())` để lấy tên cuối chỉ phù hợp khi chuỗi đó là đường dẫn hợp lệ của provider phù hợp và **khác `null`**. Với custom provider, đường dẫn có thể không parse được bởi default `Path.of`; tốt nhất nên lưu một **nhãn tài nguyên đáng tin** của ứng dụng từ trước.

## 13. Đọc/ghi bằng stream: lỗi có thể xảy ra muộn

Không phải lỗi luôn xảy ra tại dòng mở tệp. Với:

```java
try (var input = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = input.read(buffer)) != -1) {
        consume(buffer, count);
    }
}
```

đây là đoạn minh họa trong phương thức khai báo `throws IOException`; `consume` là hàm của ứng dụng cần tự định nghĩa. Ngoại lệ có thể xuất hiện khi **mở**, **đọc một lượt sau đó**, hoặc **đóng stream**. Nếu đã xử lý một phần dữ liệu, caller cần biết liệu có phải hủy kết quả trung gian hoặc đánh dấu tác vụ thất bại.

### `try-with-resources` và lỗi khi đóng

`try-with-resources` tự gọi `close()`, kể cả khi thân `try` ném lỗi. Nếu có lỗi chính trong thân và lỗi lúc đóng tài nguyên, Java thường giữ lỗi đóng dưới dạng **suppressed exception** của lỗi chính, có thể kiểm tra bằng `ex.getSuppressed()`. Điều này giúp không đánh mất toàn bộ ngữ cảnh của lỗi đóng.

Không chỉ bắt `IOException`, in “đã đóng” rồi coi nội dung đã ghi chắc chắn hoàn tất. Với `OutputStream` có buffer, lỗi có thể xuất hiện trong lúc flush/close; file đích có thể mới chứa **một phần byte**. Đối với file quan trọng cần chính sách ghi file tạm, kiểm tra kết quả và thay thế phù hợp.

### `UncheckedIOException` trong API lazy

Một số API trả stream, ví dụ `Files.lines` hoặc `Files.walk`, có thể phát sinh `UncheckedIOException` trong quá trình xử lý **sau khi đã tạo stream**:

```java
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws java.io.IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.count();
    } catch (UncheckedIOException ex) {
        throw ex.getCause();
    }
}
```

Đây là **phương thức Java để đặt trong một lớp**. `UncheckedIOException.getCause()` trả một `IOException`. Trong ứng dụng thật, cần biết I/O đã thực hiện đến đâu trước khi lỗi xảy ra. Không để stream `Files.lines` hoặc `Files.walk` mở mà không có cơ chế đóng; chúng có thể giữ tài nguyên hệ thống tệp.

**Phân biệt:** `InvalidPathException` là unchecked vì **cú pháp đường dẫn không hợp lệ**; `UncheckedIOException` là unchecked wrapper cho **lỗi I/O thật**. Hai loại không nên được chuyển thành cùng thông báo “file không tồn tại” khi chưa xem nguyên nhân.

## 14. Chương trình Java 17+ độc lập: kiểm thử các lỗi cụ thể và metadata

Ví dụ dưới đây tạo một thư mục tạm, chủ động dựng những tình huống **có thể tái lập**:

1. Đọc một tệp `missing.txt` chưa tồn tại → `NoSuchFileException`.
2. Tạo lại `existing.txt` đã tồn tại → `FileAlreadyExistsException`.
3. Xóa thư mục vẫn còn `existing.txt` → `DirectoryNotEmptyException`.
4. Gọi `deleteIfExists` trên tệp thiếu → trả `false` thay vì ném lỗi không tồn tại.
5. Tạo `FileSystemException` minh họa để đọc `getFile/getOtherFile/getReason` không phụ thuộc hệ điều hành.
6. Thử tạo `Path` chứa ký tự NUL → `InvalidPathException` trên provider mặc định thông thường.
7. Dọn tệp/thư mục mẫu sau khi kiểm thử.

Các tình huống này đã được kiểm thử với **JDK 17**. Ta cố ý **không ép hệ điều hành tạo `AccessDeniedException` bằng cách chỉnh quyền**, vì kết quả phụ thuộc đặc quyền CI, Windows/Linux và provider.

Tạo tệp **`FilesFailureDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FilesFailureDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("files-errors-");
        Path existing = dir.resolve("existing.txt");
        Path missing = dir.resolve("missing.txt");

        try {
            Files.writeString(existing, "data", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

            try {
                Files.readAllBytes(missing);
                throw new AssertionError("expected NoSuchFileException");
            } catch (NoSuchFileException ex) {
                check(ex.getFile() != null, "missing getFile");
                check("missing.txt".equals(
                        Path.of(ex.getFile()).getFileName().toString()),
                        "missing file name");
                System.out.println("read = "
                        + ex.getClass().getSimpleName());
                System.out.println("read file = "
                        + Path.of(ex.getFile()).getFileName());
            }

            try {
                Files.createFile(existing);
                throw new AssertionError("expected FileAlreadyExistsException");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("create = "
                        + ex.getClass().getSimpleName());
                System.out.println("create file = "
                        + Path.of(ex.getFile()).getFileName());
            }

            try {
                Files.delete(dir);
                throw new AssertionError("expected DirectoryNotEmptyException");
            } catch (DirectoryNotEmptyException ex) {
                System.out.println("delete = "
                        + ex.getClass().getSimpleName());
            }

            System.out.println("delete missing = "
                    + Files.deleteIfExists(missing));

            FileSystemException example =
                    new FileSystemException("source.bin",
                                            "target.bin", "demo");
            System.out.println("example source = "
                    + example.getFile());
            System.out.println("example target = "
                    + example.getOtherFile());
            System.out.println("example reason = "
                    + example.getReason());

            try {
                Path.of(String.valueOf((char) 0));
                throw new AssertionError("expected InvalidPathException");
            } catch (InvalidPathException ex) {
                System.out.println("parse = "
                        + ex.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(existing);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(dir);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 FilesFailureDemo.java
java FilesFailureDemo
```

**Stdout đã kiểm chứng trên hệ thống tệp mặc định Windows với Java 17:**

```text
read = NoSuchFileException
read file = missing.txt
create = FileAlreadyExistsException
create file = existing.txt
delete = DirectoryNotEmptyException
delete missing = false
example source = source.bin
example target = target.bin
example reason = demo
parse = InvalidPathException
cleanup = done
```

### 14.1. Những điều đã được kiểm chứng

- `NoSuchFileException` có `getFile()` trỏ tới đường dẫn liên quan; mã chỉ hiển thị **tên cuối** từ đường dẫn của provider mặc định.
- `Files.createFile(existing)` thất bại với loại `FileAlreadyExistsException`, chứ không âm thầm ghi đè.
- `Files.delete(dir)` không xóa đệ quy; thư mục còn file gây `DirectoryNotEmptyException`.
- `Files.deleteIfExists(missing)` trả `false` khi tệp không tồn tại.
- `FileSystemException` được tạo **chủ đích** với cả hai đường dẫn và lý do, nên ba getter trả đúng chuỗi đã cung cấp.
- `InvalidPathException` là lỗi của việc tạo giá trị `Path` chứa NUL, xuất hiện trước mọi lần mở file.
- `finally` thử xóa các đối tượng tạm bất kể một bước trong `try` thành công hay thất bại.

### 14.2. Giới hạn của ví dụ

Không coi các chuỗi thông báo lỗi hoặc việc provider chọn một subclass là **cam kết xuyên mọi hệ điều hành**. Với file system/provider khác, một thao tác có thể ném `IOException` tổng quát hay một ngoại lệ chuyên biệt khác. Vì thế code production phải có nhánh dự phòng và test môi trường đang triển khai.

Đoạn kiểm tra `InvalidPathException` sử dụng ký tự NUL, bị từ chối trên các file system mặc định thông thường. Với custom provider có quy tắc khác, không được lấy ví dụ này làm điều kiện tuyệt đối cho mọi provider.

Thư mục tạm yêu cầu quyền tạo/xóa file. Nếu ổ đĩa đầy, bị chặn quyền hoặc có tác nhân ngoài can thiệp, chương trình có thể thất bại vì môi trường; đây không phải khác biệt của luật kế thừa exception.

## 15. Thiết kế kiểm thử thất bại không phụ thuộc message của hệ điều hành

### 15.1. Kiểm tra class ngoại lệ thay vì khớp chuỗi lỗi

Không viết unit test kiểu:

```java
// Không ổn định trên mọi nền tảng:
assertTrue(ex.getMessage().contains("No such file or directory"));
```

Đây là mã giả phong cách unit test, cần framework để chạy. Trên Windows, Linux hoặc provider khác, message có thể thay đổi hoặc không chứa tiếng Anh đúng như mong đợi.

Thay vào đó, khi contract môi trường kiểm thử phù hợp:

```java
try {
    Files.readAllBytes(missing);
    throw new AssertionError("expected missing file");
} catch (NoSuchFileException ex) {
    if (ex.getFile() == null) {
        throw new AssertionError("expected file metadata");
    }
}
```

Đây là đoạn cần đặt trong phương thức khai báo `throws IOException`, có biến `missing` kiểu `Path`. Nó test **loại lỗi và metadata có liên quan**, không cần dựa vào chuỗi message.

Với ứng dụng chạy trên nhiều provider, có thể tách **integration tests theo provider** và kiểm tra lớp `IOException` dự phòng, thay vì buộc một provider bất kỳ phải cung cấp đúng cùng một subclass.

### 15.2. Bảng ca kiểm thử đề xuất

| Thao tác | Chuẩn bị tình huống | Kỳ vọng trọng tâm |
| --- | --- | --- |
| `readAllBytes` trên tệp thiếu | Đảm bảo target chưa có trong thư mục tạm | Không đọc được; provider mặc định thường `NoSuchFileException` |
| `createFile` khi target đã có | Tạo một file trước | `FileAlreadyExistsException` ở provider phù hợp, không ghi đè |
| `delete` thư mục không rỗng | Tạo file con | `DirectoryNotEmptyException` thường gặp |
| `deleteIfExists` trên tệp thiếu | Target chưa tồn tại | Trả `false` |
| `CREATE_NEW` trên target đã có | Tạo target trước | Thao tác tạo bị từ chối |
| `Path.of` với input bất hợp lệ | Chuỗi có NUL trên default provider | `InvalidPathException`, không phải `IOException` |
| Đọc/ghi không đủ quyền | Test fixture/quyền kiểm soát được | `AccessDeniedException` hoặc lỗi provider phù hợp |
| Copy/move liên quan hai đường dẫn | Kiểm soát nguồn và đích | Theo dõi operation, path context; `getOtherFile` có thể `null` |
| `ATOMIC_MOVE` ở provider không hỗ trợ | Integration test trên môi trường phù hợp | `AtomicMoveNotSupportedException` |
| Duyệt symlink vòng | Fixture link có thể tạo và provider theo link | Kiểm tra báo lỗi vòng/visitor callback, không treo |

**Cẩn trọng:** Đừng sửa ACL hoặc tạo/xóa cây thư mục ngoài khu vực tạm chỉ để ép một ngoại lệ trong CI. Tình huống quyền, lock, mạng và symlink nên được test riêng trong môi trường cho phép, không cần làm chương trình minh họa phá dữ liệu.

### 15.3. Test phải xác minh trạng thái sau lỗi

Chỉ test tên ngoại lệ chưa đủ. Ví dụ:

- Sau `FileAlreadyExistsException`, tệp cũ còn đúng nội dung không?
- Sau copy/ghi bị lỗi giữa chừng, file đích có tồn tại và chứa dữ liệu một phần không?
- Sau xóa thư mục thất bại, thư mục và các phần tử còn nguyên không?
- Sau lỗi phân tích `Path`, có tránh được mọi thao tác mở tệp không?
- Sau xử lý exception, có bảo toàn cause, đường dẫn đã che và correlation ID trong telemetry không?

Bộ test tốt phản ánh **hợp đồng của ứng dụng** về sự an toàn dữ liệu, không chỉ về loại exception.

## 16. Hướng xử lý phục hồi theo từng lỗi

Một dịch vụ hoặc công cụ CLI thường có thể gắn một chính sách phục hồi tương ứng:

| Loại lỗi | Có nên retry ngay? | Hành động tốt hơn |
| --- | --- | --- |
| `NoSuchFileException` trên input bắt buộc | Thường không nếu không có producer được chờ | Báo input thiếu; nếu quy trình biết file sẽ đến, dùng lịch chờ có giới hạn |
| `FileAlreadyExistsException` với `CREATE_NEW` | Không lặp vô hạn cùng tên | Từ chối trùng hoặc tạo tên mới theo hợp đồng |
| `DirectoryNotEmptyException` | Không tự động xóa toàn bộ dữ liệu | Yêu cầu xử lý nội dung hoặc xác nhận quyền xóa đệ quy |
| `AccessDeniedException` | Không retry mù quáng | Kiểm tra quyền, người vận hành và cấu hình bảo mật |
| `AtomicMoveNotSupportedException` | Không retry y nguyên để hy vọng nguyên tử | Quyết định hỗ trợ fallback hay dừng |
| `InvalidPathException` | Không retry cùng input | Yêu cầu đường dẫn hợp lệ theo provider |
| `IOException` do lỗi thiết bị/mạng tạm thời | Có thể cân nhắc trong chính sách hạn chế | Giới hạn số lần, backoff, tính idempotent và báo lỗi khi hết hạn |

Một file output được ghi một phần **không nhất thiết an toàn để retry bằng thao tác `APPEND`**: retry có thể làm trùng byte. Khi cần tính idempotent, thường nên tạo file tạm riêng, ghi đầy đủ, xác minh rồi chuyển đổi trạng thái bằng thao tác thích hợp.

Với các thao tác xóa hoặc thay thế file, phải xác định rõ **đối tượng sở hữu** và tính quan trọng của nội dung trước khi phục hồi tự động. Không biến một lỗi thành hành vi phá dữ liệu.

## 17. Những nhầm lẫn thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ catch `IOException` và in “unknown error” | Mất ngữ cảnh nguyên nhân | Catch lớp cụ thể khi có hành động riêng, giữ fallback |
| Đặt `catch(IOException)` trước subclass | Nhánh subclass không thể đạt tới | Catch từ cụ thể đến tổng quát |
| Nhận biết lỗi qua `getMessage().contains(...)` | Phụ thuộc OS/ngôn ngữ/provider | Dùng loại exception và getters |
| Giả định `getReason()` luôn có nội dung | Có thể `null` | Kiểm tra `null` |
| Giả định `getOtherFile()` luôn tồn tại khi copy/move | Provider có thể không cung cấp | Ghi thêm context ứng dụng |
| In raw path và reason cho mọi người dùng | Lộ cấu trúc hệ thống hoặc dữ liệu riêng tư | Phân quyền log và che thông tin |
| Nghĩ `InvalidPathException` là `IOException` | Catch I/O không bắt được lỗi parse | Bắt riêng ở boundary đầu vào |
| Cho rằng `deleteIfExists` xóa mọi thư mục kể cả có con | Không xóa đệ quy | Xác định chính sách xóa cây |
| Xử lý `FileAlreadyExistsException` bằng cách xóa file cũ | Có thể mất dữ liệu hoặc quyền không hợp lệ | Từ chối trùng/tạo tên mới có kiểm soát |
| Dựa vào `Files.exists` trước `createFile` để tránh trùng | TOCTOU | Sử dụng thao tác tạo mới nguyên tử theo hợp đồng |
| Nghĩ `AccessDeniedException` luôn có cùng nguyên nhân | Provider, quyền, lock khác nhau | Chẩn đoán theo môi trường |
| Ép test lỗi quyền bằng cách sửa permission toàn máy | Test không ổn định/nguy hiểm | Dùng fixture và integration test kiểm soát |
| Xem `toAbsolutePath` là chắc chắn file tồn tại | Chỉ xử lý tên đường dẫn | Kiểm tra I/O thực và xử lý lỗi |
| Bắt xong không giữ `cause` khi bọc exception | Mất chuỗi điều tra lỗi | Rethrow hoặc truyền exception gốc làm cause |
| Tin rằng try-with-resources không thể lỗi lúc close | Có thể phát sinh `IOException`/suppressed | Xem lỗi close và chính sách hoàn tất dữ liệu |
| Retry copy/append không xem file đích đã ghi dở | Có thể tạo dữ liệu trùng/hỏng | Thiết kế atomicity hoặc file tạm |
| Coi hai `Path` khác chuỗi chắc chắn khác file | Symlink/hard link | Dùng `Files.isSameFile` nếu cần và có điều kiện |
| Cho rằng lớp exception chuyên biệt được bảo đảm trên mọi provider | Có thể nhận một `IOException` khác | Có nhánh fallback theo hợp đồng |
| Bắt `Exception` và coi mọi tình huống là thiếu file | Che lỗi lập trình và lỗi input | Phân loại checked/unchecked đúng tầng |

## 18. Bài tập tự luyện và đáp án

### Bài 1 — Nêu loại ngoại lệ

Một chương trình gọi `Files.readAllBytes` trên tệp vừa bị xóa trước đó. Với provider mặc định thông thường, lớp ngoại lệ nào hay xuất hiện?

**Đáp án:** `NoSuchFileException`, một subclass của `FileSystemException` và `IOException`. Cần hiểu provider có thể đưa lỗi khác; dùng nhánh xử lý `IOException` dự phòng.

### Bài 2 — Vì sao không dựa vào `getMessage()`?

Trong mã production, người viết dùng `ex.getMessage().contains("Permission denied")` để quyết định hiện thông báo “Bạn không có quyền”. Vì sao cách này không ổn?

**Đáp án:** Message không có hợp đồng cấu trúc ổn định; thay đổi theo OS/ngôn ngữ/provider và có thể lộ đường dẫn. Dùng loại exception cụ thể khi có, lưu context thao tác và quyền nghiệp vụ riêng, phân quyền log kỹ thuật.

### Bài 3 — Trường nào có thể thiếu?

`FileSystemException` có ba getter `getFile`, `getOtherFile`, `getReason`. Có thể gọi trực tiếp `getReason().trim()` không?

**Đáp án:** Không nên. `getReason()` có thể `null`; phải kiểm tra trước. Hai getter đường dẫn cũng có thể `null`. Thông tin trả về là chuỗi, không phải `Path`.

### Bài 4 — Trùng file đích

Ứng dụng cần tạo một báo cáo mới và không được ghi đè tên đã có. Nên gọi `Files.exists` rồi `Files.write` không option, hay dùng `CREATE_NEW`?

**Đáp án:** Dùng `CREATE_NEW` với thao tác ghi/tạo phù hợp. Kiểm tra tồn tại trước rồi ghi không option dễ gặp race và có thể truncate tệp cũ.

### Bài 5 — Thư mục không rỗng

`Files.deleteIfExists(dir)` được gọi trên một thư mục đang chứa file. Có chắc trả `true` không?

**Đáp án:** Không. Nó có thể ném `DirectoryNotEmptyException`; `deleteIfExists` chỉ làm cho trường hợp đường dẫn không tồn tại trở thành một kết quả bình thường. Nó không tự động xóa đệ quy.

### Bài 6 — Thứ tự catch

```java
try {
    Files.readAllBytes(path);
} catch (IOException ex) {
    // ...
} catch (FileSystemException ex) {
    // ...
}
```

**Câu hỏi:** Có biên dịch không?

**Đáp án:** Không: nhánh `catch(FileSystemException)` không thể đạt tới vì `IOException` phía trước đã bao phủ nó. Hãy đặt `FileSystemException` và các subclass chuyên biệt trước `IOException`.

### Bài 7 — Lỗi phân tích path

`Path.of(String.valueOf((char)0))` tạo một `InvalidPathException` trên provider mặc định thông thường. `catch(IOException)` có bắt được không?

**Đáp án:** Không. `InvalidPathException` là unchecked exception và không kế thừa `IOException`. Cần catch riêng tại ranh giới nhận chuỗi đường dẫn nếu ứng dụng muốn đưa thông báo đầu vào không hợp lệ.

### Bài 8 — Xem hai đường dẫn trong lỗi

Một tác vụ `Files.move(source,destination)` thất bại và nhận `FileSystemException`. Có nên suy ra `getFile()` luôn là `source` và `getOtherFile()` luôn là `destination` không?

**Đáp án:** Không nên giả định cứng cho mọi provider và loại lỗi. Hãy lưu **ngữ cảnh operation, source, destination** do ứng dụng biết, sau đó bổ sung những trường có thực từ ngoại lệ. Chú ý che đường dẫn trong log và thông báo công khai.

### Bài 9 — Lỗi khi đóng stream

Một stream bị lỗi khi đọc, sau đó `close()` cũng thất bại. Cần điều tra gì?

**Đáp án:** Giữ ngoại lệ chính, kiểm tra `getSuppressed()` khi dùng `try-with-resources` và xem dữ liệu đã xử lý đến đâu. Không chỉ in một thông điệp “file error” rồi coi kết quả ghi là nguyên vẹn.

### Bài 10 — Có nên retry mọi `IOException`?

Một thao tác append thất bại sau khi đã ghi một số byte. Hệ thống định lặp lại toàn bộ append ngay lập tức.

**Đáp án:** Không an toàn nếu chưa biết trạng thái đích và tính idempotent. Retry có thể làm trùng dữ liệu. Cần cơ chế xác minh, file tạm, ranh giới record, transaction logic hoặc thiết kế phục hồi theo nghiệp vụ.

### Bài 11 — `FileAlreadyExistsException` và xóa dữ liệu

Nếu `CREATE_NEW` báo trùng tên, tại sao không nên xóa ngay file hiện có rồi thử tạo lại?

**Đáp án:** File cũ có thể là dữ liệu của một tác vụ khác, tài liệu quan trọng hoặc kết quả của thao tác đồng thời. Loại ngoại lệ chỉ cho biết xung đột; nó không cấp quyền hay yêu cầu xóa. Chính sách xử lý phải do ứng dụng và quyền sở hữu quyết định.

## 19. Checklist khi triển khai xử lý lỗi `Files`

- [ ] Xác định **operation** và những `Path` liên quan ngay tại nơi gọi.
- [ ] Catch loại ngoại lệ cụ thể nếu có hành động riêng; còn lại giữ `IOException` fallback.
- [ ] Đặt `catch` từ subclass đến superclass, tránh nhánh unreachable.
- [ ] Dùng `getFile/getOtherFile/getReason` với kiểm tra `null`, không parse `getMessage()` để quyết định logic.
- [ ] Phân biệt `InvalidPathException` khi tạo `Path` với `IOException` khi thực hiện I/O.
- [ ] Không mặc định provider sẽ luôn báo đúng một subclass chuyên biệt.
- [ ] Dùng `CREATE_NEW` khi yêu cầu không ghi đè; tránh `Files.exists` rồi ghi theo hai bước.
- [ ] Hiểu `deleteIfExists` không xóa đệ quy và không nuốt mọi loại lỗi.
- [ ] Có chính sách cho tệp ghi dở, rollback logic, cleanup và retry idempotent.
- [ ] Dùng `try-with-resources` và giữ nguyên cause/suppressed exceptions khi điều tra.
- [ ] Phân biệt **dữ liệu log kỹ thuật** với thông báo cho người dùng cuối; che đường dẫn nhạy cảm.
- [ ] Với stream/lazy traversal, cân nhắc `UncheckedIOException` trong quá trình duyệt.
- [ ] Test lỗi thiếu file, trùng tên, thư mục không rỗng, invalid path, quyền và tình huống phụ thuộc provider.
- [ ] Không thay đổi ACL, xóa cây tệp hoặc chạy lệnh phá dữ liệu chỉ để tạo test.
- [ ] Đánh dấu API theo phiên bản: `Files` và các ngoại lệ cụ thể (Java 7), `Files.writeString` và `Path.of` (Java 11), các cấu trúc dùng trong ví dụ hoàn chỉnh chạy trên Java 17+.

## 20. Tổng kết

Khi làm việc với `java.nio.file.Files`, một lỗi `IOException` thường không đủ chi tiết để quyết định cách xử lý. Java NIO.2 có các lớp chuyên biệt **`NoSuchFileException`, `FileAlreadyExistsException`, `DirectoryNotEmptyException`, `AccessDeniedException`** và nhiều lớp khác. Chúng kế thừa **`FileSystemException`**, cung cấp thông tin có cấu trúc về **đường dẫn liên quan, đường dẫn thứ hai nếu có và lý do từ provider**.

Hãy dùng **loại ngoại lệ** thay vì giải mã chuỗi message, **kiểm tra `null`** trước khi đọc metadata, giữ **ngữ cảnh thao tác** và **cause**, phân biệt **lỗi phân tích `Path`** với lỗi I/O thực tế, đồng thời thiết kế hành vi phục hồi để không gây mất dữ liệu. Mã Java 17+ trong bài chứng minh trực tiếp ba ngoại lệ file system và cách đọc getters; các nguyên tắc còn phù hợp trong các dự án Java hiện đại, kể cả khi file system/provider khác nhau.
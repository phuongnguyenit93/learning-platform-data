# SecureDirectoryStream và khả năng hỗ trợ của provider trong Java NIO.2

## 1. Tại sao cần SecureDirectoryStream?

Một ứng dụng Java có thể xử lý tệp trong thư mục do người dùng hoặc tiến trình khác có khả năng sửa đổi. Quy trình “kiểm tra đường dẫn rồi thao tác” quen thuộc có một khoảng thời gian dễ bị lợi dụng:

~~~java
Path file = root.resolve(userName);
if (Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
    Files.delete(file);
}
~~~

**Đây là đoạn mã minh họa rủi ro, không phải mẫu xóa an toàn.** Sau khi `isRegularFile` kiểm tra và trước `delete`, một tác nhân khác có thể thay thế một thành phần đường dẫn. Khi đó hai lời gọi có thể nói về **hai đối tượng tệp khác nhau**. Lớp lỗi này gọi là *time-of-check to time-of-use*, viết tắt **TOCTOU**.

`SecureDirectoryStream<T>` trong `java.nio.file` giải quyết một phần quan trọng của vấn đề: cung cấp những thao tác đối với **đường dẫn tương đối theo một thư mục đang mở** thay vì liên tục giải lại từ một đường dẫn tên tuyệt đối có thể bị tráo. Đây là interface được thiết kế cho những ứng dụng cần duyệt cây thư mục hoặc làm việc trên tệp theo cách chống *race condition* khi provider/hệ điều hành hỗ trợ.

~~~text
Không có handle neo thư mục:
check /safe/inbox/item.txt
       |
  attacker đổi inbox -> symlink tới /other
       |
delete /safe/inbox/item.txt  => có thể đụng đối tượng khác

Có SecureDirectoryStream:
open /safe/inbox  --> handle H tới thư mục đang mở
       |
       +-- deleteFile(Path.of("item.txt"))
                thao tác tương đối với H
                kể cả khi tên "inbox" bị đổi
~~~

Đây là sơ đồ **mô hình đe dọa**, không có nghĩa mọi thao tác trên mọi hệ thống đều có cùng kết quả. `SecureDirectoryStream` cần hỗ trợ từ provider và hệ điều hành, và không thay thế kiểm soát quyền, xác thực, bảo vệ link cứng hay chính sách sandbox.

**Ý chính:** `SecureDirectoryStream` tăng khả năng chống tấn công tráo đường dẫn/hoán đổi symbolic link ở các thao tác tương đối với thư mục đang mở. Nó **không mặc nhiên có trên mọi filesystem và provider**; ứng dụng bảo mật phải kiểm tra hỗ trợ ngay tại runtime.

## 2. Quan hệ giữa DirectoryStream và SecureDirectoryStream

`DirectoryStream<T>` hỗ trợ lặp qua các entry của một thư mục, thường được lấy từ:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(root)) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

Đây là đoạn minh họa với `root` là `Path` có sẵn, cần xử lý `IOException`. Với một `DirectoryStream<Path>` thông thường, iterator chỉ mang về các `Path` để ứng dụng tiếp tục gọi `Files.*` trên tên đó. Việc có tên đường dẫn trong iterator **không khóa** entry hoặc bảo đảm entry vẫn là đối tượng cũ khi thao tác.

`SecureDirectoryStream<T>` **extends `DirectoryStream<T>`** và thêm thao tác theo open-directory context:

| Phương thức | Công dụng |
| --- | --- |
| `newDirectoryStream(T path, LinkOption... options)` | Mở thư mục con tương đối với thư mục đang mở, trả về một `SecureDirectoryStream<T>` khác. |
| `newByteChannel(T path, Set<? extends OpenOption> options, FileAttribute<?>... attrs)` | Mở/tạo tệp qua một đường dẫn tương đối và trả về `SeekableByteChannel`. |
| `deleteFile(T path)` | Xóa một file entry (cũng dùng để xóa symbolic link) tương đối với thư mục hiện tại. |
| `deleteDirectory(T path)` | Xóa directory entry tương đối, với các điều kiện xóa thư mục tương ứng. |
| `move(T src, SecureDirectoryStream<T> targetDir, T target)` | Di chuyển entry từ thư mục đang mở sang một thư mục đích đang mở. |
| `getFileAttributeView(Class<V> type)` | Mở attribute view của chính thư mục đang mở. |
| `getFileAttributeView(T path, Class<V> type, LinkOption... options)` | Mở attribute view của một entry tương đối. |
| `close()` | Giải phóng directory stream/handle đang mở. |

Tham số `T` trong Java NIO thường là `Path`. Khi mở từ `Files.newDirectoryStream(root)`, kiểu khai báo thường là `DirectoryStream<Path>`; **không nên ép kiểu ngay** nếu chưa kiểm tra instance.

## 3. Provider support là đặc tính tùy chọn

API `SecureDirectoryStream` tồn tại từ Java 7, và Java 17 có đầy đủ những phương thức trên. Nhưng **sự tồn tại của interface không bảo đảm provider có triển khai**.

Javadoc Java 17 quy định: nếu implementation hỗ trợ tính năng này, `DirectoryStream` được trả bởi `newDirectoryStream` có thể là một `SecureDirectoryStream`. Ứng dụng phải kiểm tra đối tượng thực tế:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        System.out.println("Provider hỗ trợ tại vị trí này");
    } else {
        System.out.println("Không có SecureDirectoryStream");
    }
}
~~~

Đây là đoạn mã minh họa, cần import `java.nio.file.*`, biến `root` và xử lý `IOException`.

Phụ thuộc thực tế:

- **FileSystemProvider** được chọn bởi filesystem của `Path` đang sử dụng.
- Hệ điều hành có hoặc không có cơ chế mở/thao tác tương đối qua handle.
- Tùy phiên bản JDK, provider, loại filesystem và môi trường thực thi (filesystem gắn mạng, filesystem ảo, container...).

**Không viết điều kiện “Linux luôn có”, “Windows luôn không có”, “ZIP filesystem chắc chắn có”**. Khả năng hỗ trợ thực sự phải được kiểm tra ở runtime; các nhà cung cấp có thể khác nhau.

### 3.1. Vì sao không nên gọi trực tiếp trên DirectoryStream?

~~~java
DirectoryStream<Path> stream = Files.newDirectoryStream(root);

// Không hợp lệ về kiểu: DirectoryStream không định nghĩa deleteFile.
// stream.deleteFile(Path.of("data.txt"));
~~~

Phải kiểm tra và sử dụng đối tượng như `SecureDirectoryStream<Path>`:

~~~java
if (stream instanceof SecureDirectoryStream<?>) {
    @SuppressWarnings("unchecked")
    SecureDirectoryStream<Path> secure =
            (SecureDirectoryStream<Path>) stream;
    secure.deleteFile(Path.of("data.txt"));
}
~~~

Đây là những **mảnh minh họa**, chưa có phần mở/đóng resource hoàn chỉnh. Cast phù hợp ở ví dụ vì nguồn `stream` được khai báo `DirectoryStream<Path>`; không suy diễn cast đó cho các custom `DirectoryStream<T>` với type parameter khác.

### 3.2. Nếu provider không hỗ trợ thì làm gì?

Tùy yêu cầu:

1. **Công việc có yêu cầu chống path-race như một điều kiện bảo mật:** *fail closed*, ngừng thao tác và báo provider/môi trường không đáp ứng yêu cầu.
2. **Thư mục thuộc quyền kiểm soát độc quyền, không ai khác có thể đổi entry trong thời gian xử lý:** có thể cân nhắc API `Files.*` thông thường theo mô hình tin cậy đã chứng minh.
3. **Cần hỗ trợ đa nền tảng nhưng vẫn yêu cầu tính an toàn tương đương:** thay kiến trúc (vùng staging riêng với quyền truy cập chặt, phiên bản tệp bất biến, service đặc quyền chuyên trách hoặc cơ chế hệ điều hành tương đương được kiểm chứng).

**Không tạo “fallback” bằng cách chỉ gọi `toRealPath()`, `normalize()`, `Files.isSymbolicLink()` rồi `Files.delete()` và tuyên bố tương đương:** check-then-use vẫn có cửa sổ race khi một actor khác có thể thay đổi đường dẫn.

## 4. Relative path và neo vào directory handle

Điều quan trọng nhất là các phương thức bảo mật thường nhận **đường dẫn tương đối với thư mục đang mở**:

~~~java
Path name = Path.of("invoice.txt");
SeekableByteChannel channel =
        secure.newByteChannel(name, Set.of(StandardOpenOption.READ));
~~~

Mảnh mã này giả định `secure` là `SecureDirectoryStream<Path>` hợp lệ, đã được mở.

Khi `name` là relative path, thao tác dựa vào directory handle hiện tại; đổi tên thư mục trong hệ thống tên đường dẫn không làm handle tự động trỏ sang directory khác.

**Đường dẫn tuyệt đối là một ngoại lệ cần tránh.** Theo Javadoc, nếu truyền absolute path vào các phương thức này, việc định vị có thể tuân theo ngữ nghĩa đường dẫn tuyệt đối và làm mất mục tiêu neo vào thư mục đang mở. Hãy từ chối absolute path cho những thao tác có ý định giới hạn trong root.

### 4.1. Đừng chấp nhận path traversal

Ngay cả khi dùng secure stream, vẫn phải loại đường dẫn không thuộc miền tên được phép:

~~~text
Hợp lệ với API chỉ cho phép tên file đơn:
  report.txt
  data_001.bin

Phải từ chối theo quy tắc một thành phần:
  ../secret.txt
  subdir/../../secret.txt
  /etc/passwd
  ./
  ..
~~~

Kiểm tra `normalize()` và `startsWith(root)` trên đường dẫn tuyệt đối **không bảo vệ đầy đủ** trước các race do liên kết tượng trưng hoặc việc thay đổi thư mục từ bên ngoài. Cách dễ kiểm toán hơn là giới hạn user input thành **tên entry đơn**, từ chối `.`/`..`, phân cách đường dẫn, absolute path, tên đặc biệt và các trường hợp không hợp lệ theo filesystem/ứng dụng.

Ví dụ một validator minh họa:

~~~java
static Path safeSingleName(FileSystem fs, String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Tên rỗng");
    }
    Path name = fs.getPath(raw);
    if (name.isAbsolute()
            || name.getNameCount() != 1
            || name.toString().equals(".")
            || name.toString().equals("..")) {
        throw new IllegalArgumentException("Không phải tên entry đơn");
    }
    return name;
}
~~~

Đây là **mảnh mã**; cần `java.nio.file.FileSystem` và `Path`. Với đầu vào từ Internet, còn phải định nghĩa chính sách tên, Unicode normalization, ký tự cấm, reserved names và case-folding phù hợp hệ thống. Validator không thay thế các kiểm tra authorization/ownership; nó chỉ thu hẹp phạm vi tên mà người dùng được chỉ định.

### 4.2. Nhiều cấp thư mục: đi từng cấp có kiểm soát

Nếu ứng dụng thực sự cho phép thao tác trong cấu trúc con, nên mở thư mục con theo directory handle và kiểm soát symbolic link ở **mỗi bước**:

~~~java
try (SecureDirectoryStream<Path> sub =
        secure.newDirectoryStream(
                Path.of("uploads"), LinkOption.NOFOLLOW_LINKS)) {

    try (SeekableByteChannel file = sub.newByteChannel(
            Path.of("report.txt"),
            Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
        // Đọc dữ liệu từ channel đã mở.
    }
}
~~~

Đây là mảnh minh họa (cần biến `secure` hợp lệ, các import và exception handling). `NOFOLLOW_LINKS` ở `newDirectoryStream` ngăn việc mở thư mục con nếu entry cuối chính là symbolic link. Tương tự, `NOFOLLOW_LINKS` trong set open options của `newByteChannel` yêu cầu thao tác thất bại nếu entry đích là symbolic link.

**Không trộn parent traversal tùy ý vào một chuỗi path do user nhập**, rồi mặc định nó an toàn vì đã có `SecureDirectoryStream`. Path được phép nên được giới hạn và đi từng thành phần qua các handle đã tin cậy.

## 5. Symbolic link và NOFOLLOW_LINKS

Một nguyên nhân phổ biến của path race là **symbolic link**: attacker thay entry trong directory thành link trỏ tới vị trí ngoài phạm vi.

`LinkOption.NOFOLLOW_LINKS` chỉ rõ mục tiêu không được đi theo symlink ở thao tác tương ứng:

| Thao tác | Ví dụ dùng no-follow | Ý nghĩa |
| --- | --- | --- |
| Mở thư mục con | `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` | Thất bại nếu entry đó là symlink. |
| Mở file byte channel | `secure.newByteChannel(file, Set.of(READ, LinkOption.NOFOLLOW_LINKS))` | Thất bại nếu file entry đích là symlink. |
| Đọc metadata của entry | `secure.getFileAttributeView(file, BasicFileAttributeView.class, LinkOption.NOFOLLOW_LINKS)` | Xem attribute của entry/link thay vì đi theo symlink. |

Chú ý **không phải mọi method đều nhận LinkOption**: `deleteFile`, `deleteDirectory` và `move` có hợp đồng riêng. Đừng cố truyền `NOFOLLOW_LINKS` vào `deleteFile` vì overload như vậy không tồn tại.

`NOFOLLOW_LINKS` không thay thế việc giới hạn đường dẫn tuyệt đối hoặc đường dẫn chứa `..`. Nó cũng không ngăn mọi thay đổi do hard link, mount, quyền filesystem hay tiến trình khác đã mở file từ trước.

## 6. Một ví dụ Java 17+ hoàn chỉnh, chạy độc lập và an toàn

Ví dụ này:

1. Tạo **thư mục tạm riêng** và file `message.txt` chứa `HELLO`.
2. Gọi `Files.newDirectoryStream(root)`.
3. Nếu provider hỗ trợ `SecureDirectoryStream`, mở file **theo tên tương đối** và `NOFOLLOW_LINKS`, đọc nội dung bằng `SeekableByteChannel`, rồi dùng `deleteFile` để xóa entry.
4. Nếu không hỗ trợ, **không giả vờ dùng API kém an toàn để thay thế**; chương trình thông báo từ chối thao tác bảo mật.
5. Đóng stream và channel bằng `try-with-resources`, sau đó dọn file/thư mục tạm.

Lưu thành `SecureDirectoryStreamDemo.java`:

~~~java
import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SecureDirectoryStream;
import java.nio.file.StandardOpenOption;
import java.util.Set;

public class SecureDirectoryStreamDemo {

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("sds-demo-");
        Path file = root.resolve("message.txt");

        try {
            Files.writeString(
                    file, "HELLO", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW);

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root)) {

                if (stream instanceof SecureDirectoryStream<?>) {
                    @SuppressWarnings("unchecked")
                    SecureDirectoryStream<Path> secure =
                            (SecureDirectoryStream<Path>) stream;

                    Path name = Path.of("message.txt");

                    try (SeekableByteChannel channel =
                            secure.newByteChannel(
                                    name,
                                    Set.of(
                                            StandardOpenOption.READ,
                                            LinkOption.NOFOLLOW_LINKS))) {

                        byte[] bytes = Channels.newInputStream(channel)
                                .readAllBytes();
                        System.out.println("mode=SECURE");
                        System.out.println("text=" +
                                new String(bytes, StandardCharsets.US_ASCII));
                    }

                    secure.deleteFile(name);
                    System.out.println("deleted=" +
                            !Files.exists(file, LinkOption.NOFOLLOW_LINKS));
                } else {
                    System.out.println("mode=UNAVAILABLE");
                    System.out.println("action=REFUSED");
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SecureDirectoryStreamDemo.java
java SecureDirectoryStreamDemo
~~~

Nếu filesystem/provider hỗ trợ `SecureDirectoryStream` và file tạm hoạt động bình thường, stdout:

~~~text
mode=SECURE
text=HELLO
deleted=true
~~~

Nếu provider **không** hỗ trợ, stdout:

~~~text
mode=UNAVAILABLE
action=REFUSED
~~~

Hai đầu ra trên là **hai nhánh có điều kiện theo môi trường**, không phải kết quả cố định duy nhất của mọi hệ điều hành/JDK. Nếu các thao tác filesystem không được cấp quyền hoặc có lỗi I/O, chương trình có thể ném `IOException` thay vì in trọn nhánh; đây là hành vi đúng khi một thao tác bảo mật thất bại.

### 6.1. Vì sao kiểm tra instance thay vì chỉ kiểm tra hệ điều hành?

`Files.newDirectoryStream(root)` trả kiểu khai báo `DirectoryStream<Path>`. Nếu đối tượng thực tế triển khai `SecureDirectoryStream`, ta có thể dùng API bổ sung. Sự hỗ trợ tùy hệ điều hành và provider, nên kiểm tra kiểu thực tế **chính xác hơn** việc dựa vào tên OS hoặc filesystem được ghi trong cấu hình.

### 6.2. Vì sao đọc qua SeekableByteChannel?

`secure.newByteChannel(...)` gắn thao tác mở file với directory handle, không buộc chương trình gọi lại `Files.newInputStream(root.resolve(name))` (có thể tái giải đường dẫn). `Channels.newInputStream(channel)` chỉ bọc **channel đã mở**, nên không thay đổi đối tượng file được gắn với handle đó.

`newByteChannel` trả một channel độc lập với lifetime của directory stream đã mở nó; tuy nhiên bài ví dụ vẫn giữ stream mở cho đến khi hoàn tất các thao tác `deleteFile` để đảm bảo có directory handle dùng cho deletion.

### 6.3. Vì sao dọn bằng Files.deleteIfExists ở cuối?

Phần `finally` xử lý **thư mục tạm do chương trình tự tạo và sở hữu**, sau khi các secure operations đã kết thúc. Nó là logic dọn thử nghiệm, **không phải fallback bảo mật tương đương** nếu ta đang xử lý một directory do attacker kiểm soát. Nếu root tạm bị một actor không tin cậy kiểm soát thì phải đánh giá lại giả định an toàn của ví dụ.

## 7. Mở file bằng newByteChannel

Chữ ký Java 17:

~~~java
SeekableByteChannel newByteChannel(
        T path,
        Set<? extends OpenOption> options,
        FileAttribute<?>... attrs
) throws IOException;
~~~

Đây là **chữ ký phương thức**, không phải đoạn mã có thể đặt nguyên khối trong `main`.

Những option thường dùng:

- `StandardOpenOption.READ`: đọc.
- `StandardOpenOption.WRITE`: ghi.
- `StandardOpenOption.CREATE_NEW`: chỉ tạo khi file chưa tồn tại; hữu ích để tránh ghi đè entry đã có.
- `StandardOpenOption.CREATE`: tạo nếu chưa tồn tại, nhưng không từ chối entry đã có; cân nhắc với file untrusted.
- `StandardOpenOption.TRUNCATE_EXISTING`: cắt ngắn file hiện có khi mở ghi, nguy hiểm nếu target không được xác thực đúng.
- `LinkOption.NOFOLLOW_LINKS`: từ chối nếu final path entry là symbolic link.

Để tạo tệp mới theo directory handle:

~~~java
try (SeekableByteChannel created = secure.newByteChannel(
        Path.of("new-item.dat"),
        Set.of(
                StandardOpenOption.WRITE,
                StandardOpenOption.CREATE_NEW,
                LinkOption.NOFOLLOW_LINKS))) {

    ByteBuffer data = StandardCharsets.UTF_8.encode("safe payload");
    while (data.hasRemaining()) {
        created.write(data);
    }
}
~~~

Đây là mảnh minh họa cần import `ByteBuffer`, `StandardCharsets` và các API liên quan. `CREATE_NEW` tránh ghi đè một entry đã tồn tại; nhưng không đồng nghĩa user input đã được phép tạo tên đó theo quy tắc nghiệp vụ. Hãy kiểm tra tên/permission và giới hạn byte.

Tham số `FileAttribute<?>... attrs` có thể được sử dụng để đặt thuộc tính ngay lúc tạo file **khi provider hỗ trợ**; các attribute không được hỗ trợ có thể gây `UnsupportedOperationException`. Không giả định mọi provider đều chấp nhận thuộc tính POSIX.

## 8. Xóa file, symlink và thư mục

`secure.deleteFile(relativeName)` xóa một **entry** file tương đối với directory stream; nếu entry là symbolic link, hành vi định nghĩa theo link entry, không phải xóa theo đích link. `secure.deleteDirectory(relativeName)` xóa directory entry theo hợp đồng của filesystem, không phải “xóa cây đệ quy”.

~~~java
secure.deleteFile(Path.of("obsolete.tmp"));
secure.deleteDirectory(Path.of("empty-folder"));
~~~

Đây là mảnh minh họa: cả hai tên phải hợp lệ trong directory handle và provider có quyền xóa; thư mục cần đáp ứng quy tắc xóa directory của filesystem (thường phải rỗng). Các lỗi như `NoSuchFileException`, `DirectoryNotEmptyException`, `AccessDeniedException` hoặc `IOException` cần được xử lý theo nghiệp vụ.

**Rủi ro ngoài phạm vi của secure stream:** nếu attacker có quyền sửa những nội dung bên trong file đã mở hoặc tạo hard link liên quan đến file, directory-relative API không tự đảm bảo nội dung là tin cậy. SecureDirectoryStream chủ yếu phục vụ **định vị file trong cây thư mục khi tên có thể bị tráo**, không thay thế hệ thống quyền.

### 8.1. Xóa cây thư mục có thể phức tạp hơn

Muốn xóa cả cây do attacker có thể đồng thời thay đổi, không nên chỉ liệt kê `Files.walk(root)` rồi gọi `Files.delete(path)` trên absolute paths. Cần chiến lược thao tác tương đối bằng directory handles cho từng cấp, không đi theo symlink, kiểm tra quyền và giới hạn độ sâu/số entry. Trong môi trường không hỗ trợ SecureDirectoryStream, nên **không tuyên bố** một bản đệ quy tương tự có cùng tính kháng TOCTOU.

## 9. move(): thao tác giữa hai thư mục đang mở

API:

~~~java
void move(
        T srcpath,
        SecureDirectoryStream<T> targetdir,
        T targetpath
) throws IOException;
~~~

Ví dụ:

~~~java
try (SecureDirectoryStream<Path> destination =
        secure.newDirectoryStream(
                Path.of("archive"), LinkOption.NOFOLLOW_LINKS)) {

    secure.move(
            Path.of("input.txt"),
            destination,
            Path.of("input-archived.txt"));
}
~~~

Đây là mảnh minh họa với `secure` trỏ vào directory nguồn và có thư mục con `archive` hợp lệ.

Theo Javadoc Java 17, `move` thực hiện tương tự `Files.move` với `ATOMIC_MOVE`: việc di chuyển được thực hiện như một thao tác filesystem nguyên tử. Tuy nhiên:

- Provider có thể ném `AtomicMoveNotSupportedException` khi không thể thực hiện move nguyên tử.
- Nếu target đã tồn tại, việc thay thế hay thất bại là **implementation-specific**.
- Không có tham số `REPLACE_EXISTING` cho phương thức `SecureDirectoryStream.move` này; đừng tự giả định một chính sách ghi đè.
- Tên `srcpath` và `targetpath` nên được kiểm soát là **relative paths** trong các thư mục đã tin cậy. Nếu dùng absolute paths thì ngữ nghĩa có thể bỏ qua directory handle mong muốn.
- Atomic rename không thay thế xác thực dữ liệu, permission check, durability của thay đổi hay quy trình publish phiên bản có thể khôi phục sau mất điện.

## 10. Lấy metadata an toàn theo directory handle

`getFileAttributeView` giúp lấy/sửa thông tin tệp mà không phải dựng lại absolute path theo name:

~~~java
BasicFileAttributeView view = secure.getFileAttributeView(
        Path.of("report.txt"),
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view != null) {
    BasicFileAttributes attrs = view.readAttributes();
    System.out.println("size=" + attrs.size());
}
~~~

Đây là mảnh minh họa, cần `java.nio.file.attribute.BasicFileAttributeView` và `BasicFileAttributes`. Tùy provider, attribute view có thể không được hỗ trợ và trả `null`. Ngoài `BasicFileAttributeView`, một số provider có thể hỗ trợ attribute views chuyên biệt, nhưng không nên giả định như nhau ở các filesystem.

`NOFOLLOW_LINKS` giúp nhắm vào metadata của entry cuối thay vì link target. Mặc dù secure directory handle làm giảm rủi ro *định vị entry*, metadata vẫn là **ảnh chụp tại một thời điểm**: file có thể bị writer khác sửa nội dung hoặc metadata sau khi đọc. Muốn tính nhất quán của payload/ACL/version, cần chiến lược bổ sung như file bất biến, exclusive ownership hoặc protocol đồng bộ.

### 10.1. Attribute view của chính thư mục

~~~java
BasicFileAttributeView dirView =
        secure.getFileAttributeView(BasicFileAttributeView.class);
BasicFileAttributes dirAttrs = dirView.readAttributes();
~~~

Đây là mảnh minh họa; nếu provider không hỗ trợ view được hỏi có thể trả `null`, vì vậy production code cần kiểm tra trước khi dereference.

Lợi ích của view từ thư mục đã mở là hạn chế việc tra lại một tên đường dẫn có thể bị thay thế. Tuy vậy, nó không biến mọi lần đọc thuộc tính thành giao dịch nguyên tử với thao tác khác trong chương trình.

## 11. SecureDirectoryStream không phải sandbox hoàn chỉnh

Những gì interface hướng tới:

- Xử lý các path tương đối theo **open directory** thay vì một chuỗi tên dễ bị thay thế.
- Đi vào thư mục con bằng một **secure directory handle** mới, có thể dùng `NOFOLLOW_LINKS`.
- Mở file byte channel, xóa và move entry theo ngữ nghĩa hỗ trợ giảm path-race.
- Lấy attribute view gắn với directory handle để giảm phụ thuộc check-then-use trên tên đường dẫn toàn cục.

Những gì nó **không tự bảo đảm**:

1. **Không cung cấp authorization theo người dùng:** ứng dụng vẫn phải xác minh user nào được đọc/xóa file nào.
2. **Không chặn mọi hard link:** một entry không phải symlink vẫn có thể trỏ tới inode mà ứng dụng không nên thao tác; quyền và chính sách filesystem vẫn cần thiết.
3. **Không khóa nội dung file khỏi writer khác:** open channel đúng file không có nghĩa byte không thể bị sửa đồng thời.
4. **Không tránh tuyệt đối việc thay đổi mount/namespace:** security model phụ thuộc hệ điều hành và quyền của attacker; cần đánh giá threat model cụ thể.
5. **Không loại bỏ mọi TOCTOU ngoài filesystem operation:** xác minh metadata, parse format, kiểm tra checksum và quyết định nghiệp vụ là những bước riêng.
6. **Không tự giải quyết symbolic link trong path đã cho nếu ta không kiểm soát cấu trúc:** phải đi từng cấp và dùng `NOFOLLOW_LINKS` đúng nơi.
7. **Không bảo đảm mọi provider hỗ trợ:** phải kiểm tra đối tượng thực tế và xử lý nhánh không hỗ trợ.
8. **Không thay thế TLS, chữ ký số hoặc kiểm tra dữ liệu:** đường dẫn “được định vị đúng” không đồng nghĩa dữ liệu là đáng tin.

Một hệ thống an toàn phải xác định rõ quyền hệ điều hành, ai có thể sửa directory và các entry, dữ liệu nào do user nhập, provider nào thực sự hoạt động và hậu quả khi thao tác thất bại.

## 12. Race condition mẫu và cách thay đổi thiết kế

### 12.1. Sai lầm: Files.isDirectory rồi duyệt bên trong

~~~java
if (Files.isDirectory(root.resolve("incoming"))) {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(root.resolve("incoming"))) {
        // Có cửa sổ race giữa kiểm tra và mở.
    }
}
~~~

Thư mục `incoming` có thể bị thay đổi thành symlink trong khoảng giữa hai lời gọi; đây là một **mảnh mã minh họa kém an toàn trong môi trường untrusted**.

Với secure stream, nếu đã có handle tin cậy tới root:

~~~java
try (SecureDirectoryStream<Path> incoming =
        rootSecure.newDirectoryStream(
                Path.of("incoming"), LinkOption.NOFOLLOW_LINKS)) {
    // Làm việc tương đối với chính thư mục đã mở.
}
~~~

Lưu ý việc **tạo `rootSecure` ban đầu** cũng phải xuất phát từ nguồn root đáng tin và cơ chế bảo vệ thích hợp. Nếu attacker có thể thay root giữa lúc ta chọn root và lúc `Files.newDirectoryStream(root)` mở nó, secure stream sau đó neo vào thư mục **thực sự đã mở**, chưa chắc là thư mục ứng dụng dự định theo business policy.

### 12.2. Sai lầm: kiểm tra symlink rồi mở thường

~~~java
if (!Files.isSymbolicLink(file)) {
    Files.newInputStream(file); // Một tên khác có thể xuất hiện sau check.
}
~~~

**Mã minh họa rủi ro.** Khi dùng `SecureDirectoryStream.newByteChannel(relativeName, Set.of(READ, NOFOLLOW_LINKS))`, việc kiểm soát follow-link được chỉ định ngay trong thao tác mở file theo directory handle, tránh khoảng check-then-open đó cho entry cuối.

### 12.3. Sai lầm: bỏ qua trường hợp unsupported

~~~java
DirectoryStream<Path> ds = Files.newDirectoryStream(root);
SecureDirectoryStream<Path> s =
        (SecureDirectoryStream<Path>) ds; // Có thể ClassCastException.
~~~

Chương trình chạy được trên máy A chưa chắc an toàn hoặc hoạt động trên máy B. Kiểm tra `instanceof` và có nhánh fail-closed rõ ràng. Không “bắt ClassCastException rồi chuyển sang Files.delete” nếu rủi ro ban đầu là symlink/path-race.

## 13. Chi tiết về vòng đời và xử lý ngoại lệ

### 13.1. Đóng directory stream đúng lúc

`DirectoryStream` và `SecureDirectoryStream` đều implement `Closeable`, nên:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    // Kiểm tra instanceof và thao tác ở đây.
}
~~~

Đóng stream giải phóng tài nguyên liên quan; những phương thức secure-relative gọi trên stream đã đóng có thể ném `ClosedDirectoryStreamException`. Một `SecureDirectoryStream` con được mở từ stream cha **có vòng đời riêng** theo hợp đồng: đóng cha không tự động đóng con. Tương tự, channel mở từ `newByteChannel` cũng phải đóng độc lập.

Vì vậy có thể tách lifetime của directory handle và file handle, nhưng mã thực tế nên làm ownership minh bạch để tránh rò rỉ descriptor.

### 13.2. Các lỗi có thể cần xử lý

| Lỗi / ngoại lệ | Tình huống |
| --- | --- |
| `NoSuchFileException` | Entry không còn tồn tại khi truy cập. |
| `AccessDeniedException` | Quyền không cho phép thao tác. |
| `NotDirectoryException` | Tên được yêu cầu mở như directory nhưng không phải directory (tùy provider). |
| `DirectoryNotEmptyException` | Xóa thư mục vẫn có entry. |
| `ClosedDirectoryStreamException` | Gọi secure operation sau khi directory stream đã đóng. |
| `AtomicMoveNotSupportedException` | Không thể chuyển `move` theo thao tác nguyên tử. |
| `UnsupportedOperationException` | Provider không hỗ trợ option/attribute được yêu cầu. |
| `IOException` | Lỗi I/O rộng hơn (kể cả race làm target biến mất). |

Không giả định mọi hệ điều hành trả cùng **lớp exception cụ thể** trong mọi tình huống; nhiều lớp ngoại lệ chi tiết là *optional specific exception*. Khi thao tác bảo mật không thể hoàn tất theo yêu cầu, cần dừng/rollback nghiệp vụ phù hợp thay vì âm thầm bỏ qua.

### 13.3. Thread-safety và iteration

Một directory stream dùng để iterate tên entry; tập entry có thể thay đổi trong lúc duyệt. Không dựa vào thứ tự duyệt, không giả định snapshot, và không dùng stream/channels từ nhiều thread theo cách có data race. Nếu cần xử lý bất đồng bộ, hãy xác định thread nào sở hữu directory handle và quản lý thời điểm close.

## 14. Một quy trình an toàn hơn khi xử lý file upload

Ví dụ dịch vụ nhận tên file từ request và lưu trong một thư mục upload:

1. **Xác thực và phân quyền** user trước, giới hạn số lượng và kích thước upload.
2. Chọn root theo cấu hình tin cậy, không lấy một absolute path từ user.
3. Mở root và **kiểm tra `instanceof SecureDirectoryStream<?>`**; nếu provider không hỗ trợ mà yêu cầu chống path-race là bắt buộc, từ chối thao tác.
4. Kiểm soát tên file là **một thành phần relative**; cấm absolute, `.`, `..` và các biểu diễn qua separator.
5. Sử dụng `newByteChannel(name, Set.of(WRITE, CREATE_NEW, NOFOLLOW_LINKS))` để tạo entry, tránh ghi đè và theo symlink.
6. Ghi dữ liệu theo byte count, kiểm tra quota và size giới hạn; xử lý partial write khi cần.
7. Nếu upload cần commit có kiểm soát, lưu ở một vùng staging tin cậy, xác minh nội dung và dùng quy trình publish đã thiết kế. `move` secure-relative có ngữ nghĩa atomic nhưng không tự bổ sung mọi yêu cầu durability/authorization.
8. Đóng channel và directory streams đúng vòng đời, xóa bản tạm khi lỗi, nhưng phải xét race/ownership ngay cả khi cleanup.
9. Log những lỗi không hỗ trợ provider, permission, size/quota và thao tác từ chối mà không lộ đường dẫn nhạy cảm cho client.

Đừng xem `CREATE_NEW` là bảo đảm “file này do mình tạo nên chắc chắn an toàn”: dữ liệu có thể đến từ nguồn không tin cậy, tên có thể có xung đột ở mức nghiệp vụ và còn rất nhiều yêu cầu an ninh khác.

## 15. Khi nào vẫn dùng Files.* bình thường?

`Files.readString`, `Files.copy`, `Files.delete`, `Files.move` và `Files.walkFileTree` có API rất tiện. Chúng không tự trở thành sai chỉ vì tồn tại `SecureDirectoryStream`.

Chọn `Files.*` khi:

- Tệp/thư mục được ứng dụng sở hữu với **quyền hệ điều hành bảo vệ**, không có actor không tin cậy có thể tráo path giữa các thao tác.
- Đọc file cấu hình bất biến, dữ liệu build nội bộ, test fixtures hoặc công việc batch không có threat model path-race đáng kể.
- Provider không hỗ trợ secure stream nhưng workflow **được chứng minh là không yêu cầu** bảo vệ race giữa check/use.

Chọn `SecureDirectoryStream` khi:

- Xóa/di chuyển/đọc/ghi trong thư mục dùng chung nơi actor không tin cậy có thể thay entry đồng thời.
- Cần bảo vệ khỏi symlink swap của các thành phần directory do đối thủ kiểm soát.
- Duyệt cây tệp hoặc publish entry theo directory handle với yêu cầu hạn chế TOCTOU.
- Có thể **yêu cầu môi trường hỗ trợ API này** hoặc có chính sách fail-closed.

Nếu yêu cầu bảo vệ path-race bắt buộc mà platform không có khả năng tương đương, giải pháp đúng có thể là **không triển khai chức năng trên platform đó**, chứ không phải âm thầm giảm bảo đảm.

## 16. Bài tập tự kiểm tra

1. **`SecureDirectoryStream` là class hay interface?** Là interface mở rộng `DirectoryStream<T>`.
2. **Mọi `Files.newDirectoryStream(dir)` đều trả một `SecureDirectoryStream` không?** Không; phụ thuộc provider và hỗ trợ hệ điều hành.
3. **Kiểm tra hỗ trợ bằng cách nào?** Xem đối tượng thực tế có `instanceof SecureDirectoryStream<?>` hay không; chỉ cast khi hợp lệ.
4. **Vì sao `Files.isSymbolicLink(path)` rồi `Files.newInputStream(path)` có thể nguy hiểm?** Có khoảng TOCTOU giữa kiểm tra và sử dụng tên.
5. **Lợi ích của relative path theo directory handle?** Giảm việc giải lại tên directory trên toàn cục khi entry bị đổi tên hoặc tráo.
6. **`NOFOLLOW_LINKS` có vai trò gì?** Yêu cầu không theo symbolic link ở thao tác tương ứng, ví dụ mở thư mục con/file.
7. **`deleteFile` có tham số `NOFOLLOW_LINKS` không?** Không; nó có hợp đồng xóa entry riêng.
8. **`move` của secure stream có bảo đảm overwrite target không?** Không; khi target tồn tại, hành vi replace hay fail tùy implementation.
9. **`move` có thể ném gì nếu atomic move không khả dụng?** `AtomicMoveNotSupportedException`.
10. **Đóng secure directory stream cha có tự đóng stream con không?** Không. Stream con có lifetime riêng.
11. **Đóng directory stream có tự đóng channel đã mở từ nó không?** Không. Channel có lifetime riêng.
12. **Nếu provider không hỗ trợ, có được tuyên bố fallback check-then-delete đạt cùng bảo đảm không?** Không; nếu chống race là yêu cầu bắt buộc cần fail-closed hoặc thay kiến trúc.
13. **Đưa `../../etc/passwd` làm relative path có an toàn vì đã dùng secure stream không?** Không; cần validation và kiểm soát các thành phần path.
14. **SecureDirectoryStream có ngăn mọi hard link attack không?** Không; cần xét ownership, quyền và threat model filesystem.
15. **Nếu file đã mở an toàn nhưng một writer khác có thể thay nội dung cùng file, data có tự bất biến không?** Không; phải có kiểm soát version/ownership và đọc/ghi nhất quán.
16. **Nếu chương trình chạy trên Linux nhưng FileSystemProvider tự viết không hỗ trợ SDS, có dùng được không?** Không được giả định; kiểm tra runtime và xử lý unsupported.
17. **Có nên dùng absolute path khi gọi secure.newByteChannel(...) để giới hạn trong root?** Không; absolute path có thể bỏ qua ngữ nghĩa neo vào thư mục đang mở.
18. **Nếu ứng dụng cần chống path-race nhưng không kiểm soát root ban đầu, mở SDS có đủ chứng minh thư mục đúng không?** Chưa; cần đảm bảo ban đầu root handle trỏ đến thư mục tin cậy.
19. **Có phải mọi DirectoryStream iteration phản ánh snapshot bất biến?** Không; entry có thể thay đổi trong lúc lặp.
20. **SecureDirectoryStream có thay thế kiểm tra nội dung upload và quota không?** Không; nó tập trung thao tác đường dẫn tương đối, không xác thực dữ liệu.

## 17. Tài liệu Java 17 chính thức

- [SecureDirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): ngữ nghĩa open-directory-relative, các phương thức hỗ trợ, fallback và ngoại lệ.
- [DirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): iteration và vòng đời directory stream.
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newDirectoryStream`, `newByteChannel` và các thao tác tệp thông thường.
- [LinkOption — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` và ý nghĩa tùy thao tác.
- [FileSystemProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): vai trò của provider trong filesystem implementation.

**Ghi nhớ:** `SecureDirectoryStream` hoạt động theo **handle của thư mục đang mở**, giúp chống nhiều race do tráo entry/link khi thao tác trên **relative paths**. Hỗ trợ phụ thuộc provider và hệ điều hành, nên phải **kiểm tra `instanceof` tại runtime**. Nếu an toàn chống race là yêu cầu bắt buộc, provider không hỗ trợ thì **fail closed**, không thay bằng check-then-use và tuyên bố tương đương. Luôn kiểm soát tên path, symlink, quyền truy cập, lifetime và tính toàn vẹn dữ liệu.

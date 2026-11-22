# Root directories, `FileStore` và đặc điểm của `FileSystemProvider` trong Java NIO.2

## 1. Mục tiêu và bức tranh tổng thể

Khi làm việc với hệ thống tệp, chương trình không chỉ cần biết một `Path` trỏ tới tệp nào. Nó còn có thể cần biết những vùng gốc (root) mà một `FileSystem` cung cấp, vùng lưu trữ chứa một đường dẫn, không gian đĩa có thể sử dụng, khả năng hỗ trợ thuộc tính POSIX/DOS, và nhà cung cấp (provider) quyết định cách các thao tác NIO.2 hoạt động.

Sau bài này, bạn có thể:

- Phân biệt **root directory**, **`FileStore`** và **`FileSystemProvider`**; tránh giả định mỗi root tương ứng chính xác một ổ đĩa vật lý.
- Duyệt các root và kho lưu trữ, chọn đúng `FileStore` cho một `Path` đang tồn tại.
- Đọc dung lượng, trạng thái chỉ đọc và khả năng hỗ trợ các file attribute view một cách có kiểm soát lỗi.
- Nhận ra giới hạn phụ thuộc hệ điều hành/provider và làm việc với một hệ thống tệp ZIP bằng provider khác.

Các kiểu liên quan thuộc `java.nio.file` và `java.nio.file.spi` trong Java NIO.2:

```text
FileSystemProvider (cách triển khai thao tác theo scheme)
        │ tạo/cung cấp
        ▼
FileSystem (không gian tên, separator, các root, các FileStore)
        │ tạo/cung cấp
        ├── Path (đường dẫn bên trong FileSystem)
        └── FileStore (thông tin kho lưu trữ mà provider nhìn thấy)
```

Đây là sơ đồ quan hệ API, **không** phải sơ đồ phân vùng vật lý: một `FileSystem` có thể có nhiều root hoặc nhiều `FileStore`; hai khái niệm này không có quan hệ một-một bắt buộc.

## 2. Root directory: gốc của không gian đường dẫn

**Root directory** là thành phần gốc của đường dẫn tuyệt đối trong một `FileSystem`. Dùng `FileSystem.getRootDirectories()` để lấy `Iterable<Path>` biểu diễn các root do provider liệt kê.

```java
FileSystem fs = FileSystems.getDefault();
for (Path root : fs.getRootDirectories()) {
    System.out.println(root);
}
```

Trên môi trường Unix thường có root `/`; trên Windows có thể thấy `C:\`, `D:\` hoặc các root khác. Đây chỉ là ví dụ phụ thuộc máy đang chạy. Thứ tự, số lượng, cách biểu diễn và quyền truy cập không cố định; không hard-code danh sách root.

Phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Path.getRoot()` | Phần gốc của **một đường dẫn**; có thể `null` với đường dẫn tương đối | `/` trong `/var/log/app.log` |
| `FileSystem.getRootDirectories()` | Các root mà **provider liệt kê** cho hệ thống tệp | `/` hoặc các ký tự ổ đĩa |
| Mount point | Vị trí một filesystem/volume được gắn vào cây thư mục của OS | `/mnt/data` có thể là volume riêng |
| `FileStore` | Đại diện cho kho lưu trữ và metadata của nó theo provider | volume, partition, mount hoặc đơn vị lưu trữ logic |

Điểm dễ nhầm: trên Linux, một volume riêng gắn tại `/mnt/data` **không nhất thiết** xuất hiện như root thứ hai trong `getRootDirectories()`; ứng dụng vẫn truy cập volume qua `/mnt/data`. Ngược lại, một root không bảo đảm toàn bộ nhánh bên dưới nằm trên cùng `FileStore` do mount point có thể xuất hiện sâu trong cây.

`Path.of(".")` là đường dẫn tương đối; `Path.of(".").toAbsolutePath().normalize()` cho đường dẫn tuyệt đối chuẩn hóa về mặt cú pháp. `normalize()` không tự kiểm tra sự tồn tại của tệp, không phân giải symbolic link và không chứng minh đường dẫn có thể truy cập. Khi cần đường dẫn thực trên đĩa và xác minh tồn tại, xem `toRealPath()` và xử lý `IOException`.

## 3. `FileStore`: kho lưu trữ và metadata

`FileStore` cung cấp thông tin về nơi provider đặt tệp và khả năng của đơn vị lưu trữ đó. Hai cách truy cập hay dùng:

- `Files.getFileStore(existingPath)`: tìm kho lưu trữ cho **đường dẫn cụ thể**. Thích hợp nhất khi cần xác định vị trí ghi của tệp/danh mục làm việc. Đường dẫn nên tồn tại và quyền truy cập phải phù hợp; lời gọi có thể ném `IOException`.
- `FileSystem.getFileStores()`: duyệt các `FileStore` mà hệ thống tệp/provider có thể liệt kê. Tập kết quả và mức độ hiển thị phụ thuộc môi trường, quyền và provider; danh sách không phải bản đồ đầy đủ, bất biến của phần cứng.

Các phương thức chính:

| API | Điều trả về | Diễn giải và giới hạn |
| --- | --- | --- |
| `name()`, `type()` | Tên/loại do provider báo | Có thể là chuỗi rỗng hoặc khác nhau giữa OS; không dùng làm định danh vĩnh viễn |
| `isReadOnly()` | Trạng thái chỉ đọc của store | Không thay thế kiểm tra quyền truy cập đối với một đường dẫn |
| `getTotalSpace()` | Tổng dung lượng (byte) | Dung lượng logic provider báo, không nhất thiết tương ứng dung lượng thiết bị vật lý |
| `getUnallocatedSpace()` | Số byte chưa cấp phát | Có thể bao gồm phần mà tài khoản hiện tại không được phép sử dụng |
| `getUsableSpace()` | Số byte ước tính có thể dùng bởi JVM hiện tại | Có thể bị hạn chế bởi quota, chính sách hoặc filesystem |
| `supportsFileAttributeView(String/Class)` | Store tuyên bố hỗ trợ một view thuộc tính | Cần kiểm tra thêm theo path/thao tác cụ thể nếu ứng dụng phụ thuộc khả năng đó |
| `getAttribute(name)` | Metadata mở rộng theo tên | Không bảo đảm có mọi thuộc tính; có thể không được hỗ trợ |

Mọi đại lượng không gian có đơn vị **byte**, kiểu `long`, và là một phép quan sát tại thời điểm gọi. Giá trị có thể thay đổi ngay sau đó; quota, filesystem ảo, storage mạng, container và đặc quyền của process có thể ảnh hưởng kết quả. Đặc biệt, `usableSpace` khác với `unallocatedSpace`: một phần dung lượng chưa cấp phát có thể dành riêng cho hệ thống hoặc người dùng đặc quyền.

**Không dùng `getUsableSpace()` làm cam kết rằng một thao tác ghi chắc chắn thành công.** Khoảng trống có thể thay đổi; còn có quota, inode, quyền, network failure, trạng thái mount và các hạn chế provider. Thao tác ghi thực tế phải bắt và xử lý lỗi.

## 4. Ví dụ chạy được: root, provider và `FileStore` của thư mục hiện hành

Lưu mã dưới đây thành **`StorageOverview.java`**. Chương trình dùng Java 17+, không tạo, sửa hoặc xóa tệp; nó chỉ quan sát metadata. Lệnh có thể thất bại nếu hệ thống từ chối truy cập metadata, nên ví dụ cho phép ném `IOException` để hiển thị nguyên nhân cho người chạy.

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;

public class StorageOverview {
    public static void main(String[] args) throws IOException {
        FileSystem fs = FileSystems.getDefault();

        System.out.println("Provider scheme: " + fs.provider().getScheme());
        System.out.println("Separator: " + fs.getSeparator());
        System.out.println("Supported views: " + fs.supportedFileAttributeViews());

        for (Path root : fs.getRootDirectories()) {
            System.out.println("Root: " + root);
        }

        Path current = Path.of(".").toAbsolutePath().normalize();
        FileStore store = Files.getFileStore(current);

        System.out.println("Current: " + current);
        System.out.println("Store: " + store.name() + " / " + store.type());
        System.out.println("Read only: " + store.isReadOnly());
        System.out.println("Basic view: "
                + store.supportsFileAttributeView("basic"));
        System.out.println("Total bytes: " + store.getTotalSpace());
        System.out.println("Unallocated bytes: " + store.getUnallocatedSpace());
        System.out.println("Usable bytes: " + store.getUsableSpace());
    }
}
```

Biên dịch/chạy tại thư mục chứa tệp:

```bash
javac StorageOverview.java
java StorageOverview
```

Đầu ra có cấu trúc `Provider scheme: ...`, `Root: ...`, `Store: ...` và các dung lượng. **Không có stdout cố định** cho ví dụ này: đường dẫn, loại filesystem, provider, số lượng root và dung lượng thực tế đều do máy đang chạy quyết định. Một JVM thông thường dùng provider mặc định với scheme `file`, nhưng mã không cần giả định tên volume, có hay không view `posix` hoặc dung lượng cụ thể.

Vì sao gọi `Files.getFileStore(current)` sau khi chọn `current`? Bởi root `/` có thể chứa nhiều mount point con; lấy store của đúng thư mục đích đáng tin cậy hơn là đoán từ root đầu tiên.

Khi vận hành, nên giữ `IOException` trong ngữ cảnh (đường dẫn nào, phép đọc metadata nào), và không để một volume tạm thời mất kết nối làm hỏng toàn bộ màn hình thống kê nếu còn những volume khác đọc được.

## 5. Liệt kê các `FileStore` một cách an toàn

Để tạo trang chẩn đoán, bạn có thể duyệt `fs.getFileStores()`. Mỗi store có thể độc lập trả lỗi khi lấy dung lượng, vì vậy nên giới hạn vùng xử lý lỗi cho từng store:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.FileSystems;

public class ListStores {
    public static void main(String[] args) {
        for (FileStore store : FileSystems.getDefault().getFileStores()) {
            try {
                System.out.printf(
                        "name=%s, type=%s, readOnly=%s, usable=%d bytes%n",
                        store.name(),
                        store.type(),
                        store.isReadOnly(),
                        store.getUsableSpace()
                );
            } catch (IOException | SecurityException ex) {
                System.err.println("Cannot inspect store " + store.name()
                        + ": " + ex.getMessage());
            }
        }
    }
}
```

Lưu là **`ListStores.java`**, rồi:

```bash
javac ListStores.java
java ListStores
```

Các dòng thống kê và thứ tự hoàn toàn phụ thuộc môi trường; với một số provider, danh sách có thể trống hoặc một số store không truy cập được. Đừng suy luận rằng số dòng là số ổ đĩa vật lý. Cũng không nên lưu lâu một `FileStore` rồi cho rằng metadata vẫn ổn định khi filesystem có thể bị tháo/gắn hoặc thay đổi quota.

## 6. Provider: ai thực sự triển khai thao tác tệp?

`FileSystemProvider` là SPI của NIO.2, định nghĩa cách truy cập một kiểu filesystem. Mỗi provider gắn với một **scheme** URI, ví dụ:

- `file`: provider mặc định của hệ điều hành, thường phục vụ đường dẫn trên máy.
- `jar`: ZIP filesystem provider (`jdk.zipfs` trong JDK chuẩn), cho phép xem nội dung một tệp ZIP/JAR như cây `Path`.
- Provider của bên thứ ba có thể đại diện filesystem mạng, tệp trong bộ nhớ hoặc storage tùy biến; cần kiểm tra tài liệu provider vì tính năng không đồng nhất.

Quan hệ thực tế:

1. `FileSystems.getDefault()` trả filesystem mặc định; `fs.provider()` trả provider của nó.
2. `Path` luôn gắn với một `FileSystem`: `path.getFileSystem()`. Hai `Path` từ hai provider có thể mang cú pháp khác nhau và không phải lúc nào dùng chung được.
3. `Files.readString`, `Files.copy`, `Files.getFileStore`... làm việc thông qua provider tương ứng với đường dẫn. Khi kết hợp đường dẫn từ các provider khác nhau, API có thể thực hiện truyền byte liên provider ở một số thao tác, nhưng những thao tác khác sẽ từ chối hoặc có ngữ nghĩa riêng. Không giả định việc di chuyển, quyền hoặc atomicity tương đương trên mọi provider.
4. `FileSystem` quyết định `getSeparator()`, `getRootDirectories()`, `getFileStores()`, `supportedFileAttributeViews()`. Cùng một ứng dụng có thể sử dụng nhiều filesystem/provider.

**Scheme URI không phải tên hệ thống tệp vật lý.** `file` hay `jar` nói đến cơ chế provider xử lý đường dẫn; `FileStore.type()` có thể trả dạng filesystem như NTFS, ext4 hoặc tên khác, và không có định dạng portable cố định.

Có thể liệt kê provider có sẵn bằng `FileSystemProvider.installedProviders()`; kết quả phụ thuộc JDK và classpath/module-path. Không giả định rằng mọi runtime Java đều bao gồm provider ZIP, nhất là runtime image tùy biến đã loại `jdk.zipfs`.

## 7. Ví dụ chạy được: provider `jar` với filesystem ZIP

Ví dụ sau tạo một ZIP tạm trong thư mục tạm của OS, ghi một tệp văn bản vào ZIP qua `Path` của ZIP filesystem, đọc lại, đóng filesystem rồi xóa ZIP. Chạy trên **JDK 17+ có module `jdk.zipfs`**.

Lưu thành **`ZipProviderDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class ZipProviderDemo {
    public static void main(String[] args) throws IOException {
        Path archive = Files.createTempFile("nio-provider-", ".zip");
        try {
            // File ZIP mới do createTempFile tạo đang rỗng:
            // xóa placeholder để ZipFileSystem tạo archive hợp lệ.
            Files.delete(archive);
            URI zipUri = URI.create("jar:" + archive.toUri());

            try (FileSystem zipFs = FileSystems.newFileSystem(
                    zipUri, Map.of("create", "true"))) {
                Path entry = zipFs.getPath("/docs/message.txt");
                Files.createDirectories(entry.getParent());
                Files.writeString(entry, "Xin chào ZIP",
                        StandardCharsets.UTF_8);

                System.out.println(Files.readString(
                        entry, StandardCharsets.UTF_8));
                System.out.println(zipFs.provider().getScheme());
            }
        } finally {
            Files.deleteIfExists(archive);
        }
    }
}
```

```bash
javac ZipProviderDemo.java
java ZipProviderDemo
```

Stdout khi chạy thành công:

```text
Xin chào ZIP
jar
```

Giải thích:

- `archive` là `Path` của filesystem mặc định, còn `entry` là `Path` nằm **bên trong ZIP filesystem**. Cả hai là `Path` nhưng có `getFileSystem()` khác nhau.
- URI dạng `jar:file:...` chọn provider `jar`. Môi trường `Map.of("create", "true")` yêu cầu tạo ZIP nếu chưa tồn tại.
- `zipFs.getPath("/docs/message.txt")` mang ý nghĩa đường dẫn bên trong archive; ký tự `/` ở đây là separator của ZIP filesystem, kể cả khi máy chủ chạy Windows.
- `try-with-resources` đóng ZIP filesystem, hoàn tất việc ghi và giải phóng tài nguyên. Đường dẫn `entry` không còn dùng được bình thường sau khi filesystem của nó đóng (`ClosedFileSystemException` có thể phát sinh).
- `finally` xóa tệp ZIP tạm; nên tránh phụ thuộc vào ZIP file còn tồn tại sau ví dụ.

Trong runtime thiếu `jdk.zipfs`, mở scheme `jar` có thể ném `ProviderNotFoundException`. Trên máy cấm tạo/xóa tệp tạm, chương trình có thể ném `IOException`. Ví dụ không tuyên bố ZIP provider có cùng dung lượng, file attribute view hoặc khả năng ghi nguyên tử với filesystem mặc định.

## 8. Khả năng hỗ trợ thuộc tính: kiểm tra ở đúng tầng

NIO.2 cung cấp những **file attribute view** như `basic`, `dos`, `posix`, `acl`, `owner` và `user`. Hỗ trợ phụ thuộc provider, filesystem, `FileStore`, hệ điều hành và có thể phụ thuộc đường dẫn.

Ba câu hỏi khác nhau:

| Câu hỏi | API kiểm tra | Lưu ý |
| --- | --- | --- |
| Filesystem này thông báo hỗ trợ những tên view nào? | `fs.supportedFileAttributeViews()` | Danh sách ở tầng `FileSystem`; không khẳng định mọi đường dẫn dùng được |
| Store cụ thể thông báo hỗ trợ view này không? | `store.supportsFileAttributeView("posix")` | Nên dùng cùng `FileStore` của path đích |
| Path cụ thể có thể truy xuất/sửa thuộc tính không? | `Files.getFileAttributeView(path, PosixFileAttributeView.class)` và thao tác đọc/ghi tương ứng | Có thể trả `null` hoặc ném lỗi; quyền còn phụ thuộc người chạy |

Ví dụ ngắn, giả sử `path` là `Path` hợp lệ đang tồn tại:

```java
FileSystem fs = path.getFileSystem();
FileStore store = Files.getFileStore(path);

if (fs.supportedFileAttributeViews().contains("posix")
        && store.supportsFileAttributeView("posix")) {
    // Đây mới là kiểm tra khả năng, chưa phải bảo đảm có quyền đọc/ghi.
    var view = Files.getFileAttributeView(
            path, java.nio.file.attribute.PosixFileAttributeView.class);
    if (view != null) {
        var attrs = view.readAttributes(); // vẫn có thể ném IOException
        System.out.println(attrs.permissions());
    }
}
```

Đoạn này **minh họa**, không phải chương trình độc lập: cần khai báo `path`, import các API dùng tới, và phương thức bao quanh xử lý `IOException`. Không nên ép tất cả `Path` phải có POSIX permissions trên Windows hoặc trên ZIP provider. Với yêu cầu portable, nên dùng `BasicFileAttributes` / `Files.readAttributes(path, BasicFileAttributes.class)` cho thông tin cơ bản, và chỉ dùng các view nâng cao sau khi xác nhận hỗ trợ.

`FileStore.getAttribute(String)` cũng mang tính provider-specific. Nếu hỏi thuộc tính không được nhận diện, có thể nhận `UnsupportedOperationException`; truy xuất còn có thể thất bại bằng `IOException`. Đọc tài liệu provider trước khi phụ thuộc vào tên thuộc tính ngoài API chung.

## 9. Chọn API theo tình huống thực tế

**Tình huống A — hiển thị các vùng gốc để người dùng chọn thư mục.** Dùng `FileSystems.getDefault().getRootDirectories()` để gợi ý các điểm bắt đầu. Đừng giả định danh sách đầy đủ mọi mount point; hãy cho phép người dùng chọn hoặc nhập một `Path` hợp lệ ở nơi khác.

**Tình huống B — dự tính dung lượng để xuất báo cáo.** Chọn **thư mục thực sự sẽ chứa output**, tạo thư mục đích nếu nghiệp vụ cho phép, rồi gọi `Files.getFileStore(destinationDirectory)` và `getUsableSpace()`. Không kiểm tra ổ theo ký tự đầu của đường dẫn hoặc lấy đại root `/`. Kết quả chỉ để cảnh báo/sắp xếp lựa chọn; khi ghi vẫn cần xử lý lỗi và dọn dẹp dữ liệu ghi dở.

**Tình huống C — chạy trên Linux, Windows và ZIP filesystem.** Lấy `Path`, `FileSystem` và provider ngay từ đối tượng đang dùng; kiểm tra `supportedFileAttributeViews()` / `supportsFileAttributeView()` trước khi dùng POSIX/DOS. Đừng xây path con bằng cách tự nối separator của host nếu path thuộc ZIP/provider khác: dùng `path.resolve("child")`.

**Tình huống D — xử lý thư mục trên volume mạng hoặc removable media.** Một store có thể biến mất hoặc ngừng phản hồi giữa hai lời gọi. Bọc `Files.getFileStore`, truy xuất dung lượng, liệt kê thư mục và thao tác file trong xử lý `IOException` phù hợp; không coi kết quả chẩn đoán trước đó là snapshot bất biến.

## 10. Lỗi phổ biến và giới hạn cần nhớ

1. **Đếm root như đếm partition/volume.** Root mô tả namespace; volume có thể mount sâu trong cây.
2. **Dùng store của root để đo đường dẫn con.** Một thư mục con có thể nằm trên mount point khác. Hãy lấy store từ đúng path đích.
3. **Coi `usableSpace` là hạn mức chắc chắn có thể ghi.** Đây là ước tính tức thời, không thay thế xử lý lỗi khi ghi.
4. **Coi `isReadOnly() == false` là quyền ghi tệp.** Quyền truy cập còn phụ thuộc ACL, permissions, quota, path và trạng thái vận hành. `Files.isWritable(path)` cũng không thay thế việc xử lý lỗi của thao tác ghi thật.
5. **Hard-code `/`, `C:\` hoặc tên/loại store.** Hãy dùng `Path`/`resolve`; chỉ hiển thị `name()/type()` như dữ liệu chẩn đoán.
6. **Cho rằng provider nào cũng có POSIX, DOS, ACL hoặc file space đáng tin cậy.** Kiểm tra khả năng hỗ trợ và chấp nhận `UnsupportedOperationException` / `IOException` theo hợp đồng API.
7. **Tiếp tục sử dụng `Path` của ZIP đã đóng.** Vòng đời của `Path` gắn với `FileSystem`; đóng tài nguyên bằng `try-with-resources`, rồi chỉ sử dụng chúng trong phạm vi còn mở.
8. **Đồng nhất provider với thiết bị lưu trữ.** Scheme `jar` hay `file` xác định cách triển khai truy cập; filesystem type và store là thông tin ở tầng khác.

## 11. Câu hỏi tự kiểm tra

- Vì sao `getRootDirectories()` trên Linux có thể chỉ cho `/`, trong khi `Files.getFileStore(Path.of("/mnt/data"))` trả metadata của volume riêng?
- Nếu cần kiểm tra dung lượng trước khi ghi vào `/mnt/data/reports`, bạn nên lấy `FileStore` của đường dẫn nào? Điều kiện gì phải đúng với đường dẫn ấy?
- Phân biệt `getUnallocatedSpace()` và `getUsableSpace()`. Vì sao kết quả kiểm tra không bảo đảm một thao tác `Files.writeString()` sau đó sẽ thành công?
- Tại sao `Path` do `zipFs.getPath(...)` tạo ra không nên được xử lý như `Path.of(...)` của hệ điều hành, dù cả hai thực hiện API `Path`?
- Việc `fs.supportedFileAttributeViews().contains("posix")` đủ để khẳng định bạn có thể đổi quyền mọi tệp trên hệ thống không? Vì sao?

## 12. Tổng kết

Hãy xem **root directory** là gốc của không gian đường dẫn, **`FileStore`** là nguồn metadata cho nơi dữ liệu được lưu, còn **`FileSystemProvider`** là thành phần triển khai các thao tác tệp. Khi cần dung lượng hoặc view thuộc tính, hãy bắt đầu từ **`Path` đích**, xác định `FileSystem` và `FileStore` tương ứng, đọc khả năng được quảng bá, rồi xử lý ngoại lệ của thao tác thực tế. Cách làm này bền vững hơn trước khác biệt Unix/Windows, mount point, network storage và các provider như ZIP.

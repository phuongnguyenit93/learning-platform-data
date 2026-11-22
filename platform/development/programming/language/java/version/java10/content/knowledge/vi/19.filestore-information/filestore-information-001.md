# `FileStore` và thông tin hệ thống tệp chứa một `Path`

*Chủ đề cha: Thông tin FileStore. Bài học tập trung vào `java.nio.file.FileStore`, cách lấy bộ lưu trữ tương ứng với một `Path` bằng `Files.getFileStore(Path)` và cách đọc thông tin dung lượng, loại thiết bị/hệ thống tệp, thuộc tính hỗ trợ. Nội dung chỉ đề cập các kiến thức Java còn áp dụng trong Java hiện đại; ví dụ hoàn chỉnh sử dụng JDK 17 trở lên.*

## 1. Mục tiêu và ý nghĩa của `FileStore`

Hãy tưởng tượng ứng dụng chuẩn bị ghi một file báo cáo vào đường dẫn `Path`. Trước khi ghi, bạn cần biết file sẽ nằm trên **bộ lưu trữ (storage)** nào, bộ lưu trữ có được đánh dấu chỉ đọc không, tổng dung lượng và số byte còn có thể sử dụng ước tính là bao nhiêu.

`Path` mô tả **vị trí** của file hoặc thư mục. `FileStore` mô tả **bộ lưu trữ phía dưới** nơi file/thư mục đó được lưu: có thể là volume, phân vùng, pool lưu trữ, thiết bị, mount point hoặc một biểu diễn phụ thuộc nhà cung cấp hệ thống tệp.

Cách kết nối hai khái niệm:

```java
// Đoạn minh họa bên trong method có xử lý IOException:
java.nio.file.Path path = java.nio.file.Path.of(".");
java.nio.file.FileStore store =
        java.nio.file.Files.getFileStore(path);
```

**`Files.getFileStore(path)` trả `FileStore` của vị trí file được `path` chỉ tới.** Từ `store`, bạn có thể gọi:

- `name()`: tên bộ lưu trữ, phụ thuộc nền tảng.
- `type()`: loại/kiểu lưu trữ, phụ thuộc nền tảng.
- `isReadOnly()`: bộ lưu trữ có được đánh dấu chỉ đọc không.
- `getTotalSpace()`: tổng dung lượng bộ lưu trữ, tính bằng byte.
- `getUnallocatedSpace()`: số byte chưa được cấp phát.
- `getUsableSpace()`: số byte ước tính JVM hiện có thể sử dụng.
- `getBlockSize()`: số byte trên một block lưu trữ, nếu implementation hỗ trợ; **phương thức này được bổ sung trong Java 10**.
- `supportsFileAttributeView(...)`: hệ thống tệp lưu trên FileStore có hỗ trợ nhóm thuộc tính được hỏi không.

**Điểm phân biệt lịch sử:** `FileStore` và `Files.getFileStore` đã có từ Java 7 (NIO.2), không phải toàn bộ class mới có trong Java 10. Nội dung gắn trực tiếp với Java 10 là `FileStore.getBlockSize()`. Cả các API còn lại và `getBlockSize()` vẫn là kiến thức hữu ích, không phải legacy.

Sau bài học, bạn có thể chọn đường dẫn đúng để hỏi bộ lưu trữ, đọc các số liệu một cách an toàn, viết ví dụ đa nền tảng không “đóng đinh” số GB và không biến phép kiểm tra dung lượng thành một cam kết ghi file chắc chắn thành công.

## 2. Ba tầng khác nhau: `Path`, `FileSystem` và `FileStore`

Đừng gộp các khái niệm này thành một:

| Đối tượng | Câu hỏi trả lời | API điển hình |
| --- | --- | --- |
| `Path` | File/thư mục ở vị trí nào? | `Path.of(...)`, `resolve(...)`, `toAbsolutePath()` |
| `FileSystem` | Bộ quy tắc/path/provider nào diễn giải Path? | `path.getFileSystem()`, `FileSystems.getDefault()` |
| `FileStore` | File ở bộ lưu trữ/volume/pool nào? | `Files.getFileStore(path)` |
| `FileSystemProvider` | Implementation nào thực hiện thao tác file? | `path.getFileSystem().provider()` |

Một `FileSystem` có thể bao gồm nhiều `FileStore`. Ví dụ trên hệ điều hành có nhiều volume hoặc mount point, các file có thể cùng dùng default FileSystem nhưng nằm trên những bộ lưu trữ khác nhau.

```java
var inputPath = java.nio.file.Path.of("data", "input.csv");
var fs = inputPath.getFileSystem();

// Khi inputPath chỉ tới một file tồn tại và truy cập được:
var store = java.nio.file.Files.getFileStore(inputPath);
```

`fs` và `store` không phải cùng một loại đối tượng. `path.getFileSystem()` lấy FileSystem liên kết với Path; còn `Files.getFileStore(path)` cần truy cập thông tin về vị trí file tương ứng và có thể thất bại do I/O.

### 2.1. `Path` không lưu sẵn số byte còn trống

Không có lý do dùng `path.toString()`, `path.getRoot()` hoặc phần mở rộng file để tự suy ra dung lượng hay filesystem type. Mount point có thể nằm sâu trong cây thư mục, ổ mạng có thể được gắn dưới một thư mục, và provider có thể ánh xạ đường dẫn theo cách riêng.

Hãy hỏi **vị trí thực sự** bằng `Files.getFileStore(path)` thay vì suy đoán rằng mọi đường dẫn có cùng root đều nằm trên một thiết bị.

### 2.2. File khác, FileStore có thể giống; Path giống dạng, FileStore có thể khác

Hai `Path` cùng nằm trong một thư mục bình thường thường được lưu trên cùng FileStore, nhưng **không dùng việc cùng prefix chuỗi** làm quy tắc phát hiện store. Ngược lại, bạn cũng không nên dựa vào `store1 == store2` để quyết định hai file có chung vật lý: API không cam kết identity của các đối tượng `FileStore` do các lời gọi khác nhau trả về.

Khi thật sự cần so sánh đặc tính của hai vị trí, lấy `Files.getFileStore(...)` cho từng file và dùng API/hợp đồng phù hợp; không tự xây câu trả lời từ ký tự của đường dẫn.

## 3. `Files.getFileStore(Path)` — điểm vào từ một đường dẫn

Chữ ký Java:

```java
public static FileStore getFileStore(Path path)
        throws IOException
```

Đây là chữ ký đọc API, không phải khai báo Java độc lập để copy ngoài class. Để gọi:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileStore;
import java.io.IOException;

static FileStore storeFor(Path path) throws IOException {
    return Files.getFileStore(path);
}
```

Đoạn này là method minh họa cần đặt trong một lớp. `Files.getFileStore` không phải method instance trên `Path`: không viết `path.getFileStore()`.

### 3.1. Nên truyền `Path` nào?

- **File có thật:** truyền `Path` đang định vị đúng file đó.
- **Thư mục có thật:** truyền `Path` của thư mục; dùng để biết vùng lưu trữ nơi thư mục đang nằm.
- **File đích chưa được tạo:** nếu chỉ có một đường dẫn dự định ghi, bạn chưa có file thực sự để truy vấn. Có thể lấy `FileStore` của **thư mục cha đã tồn tại** làm dữ liệu tham khảo cho việc ghi vào đó, nhưng cần hiểu ràng buộc mount point/provider và vị trí đích thật khi tạo file.
- **Đường dẫn tương đối:** `Path.of(".")` là thư mục làm việc theo cách giải thích của FileSystem hiện tại. Nếu cần biết chính xác vị trí, chuyển về đường dẫn tuyệt đối hoặc real path theo mục đích.

Ví dụ:

```java
var directory = java.nio.file.Path.of(".")
        .toAbsolutePath()
        .normalize();

var store = java.nio.file.Files.getFileStore(directory);
```

`normalize()` chỉ xử lý các thành phần đường dẫn như `.` và `..` theo cú pháp; nó không tự kiểm tra tồn tại hay giải quyết mọi symbolic link. Khi cần xác định file thực tế sau các liên kết, cân nhắc `toRealPath()` với xử lý `IOException` phù hợp.

**Không dựa vào `Files.exists(path)` rồi cho rằng chắc chắn `Files.getFileStore(path)` sẽ thành công**. File có thể bị xóa, di chuyển, mất quyền hoặc storage không sẵn sàng giữa hai lời gọi. `getFileStore` tự có thể ném `IOException`.

### 3.2. Có xảy ra tác động khi file bị xóa sau khi lấy `FileStore` không?

Javadoc nêu rõ: khi đã lấy được `FileStore`, việc các operation trên đối tượng đó có tiếp tục phụ thuộc vào sự tồn tại của file hay không là **implementation-specific**. Đặc biệt, nếu file bị xóa hoặc chuyển sang một FileStore khác, hành vi về sau không được định nghĩa chung cho mọi provider.

Vì vậy, không nên xem `store` là “binding vĩnh viễn” giữa `Path` với volume trong mọi tình huống. Khi ứng dụng cần thông tin mới sau khi file đã được chuyển/xóa, hãy lấy lại dữ liệu theo workflow phù hợp và chấp nhận I/O failure.

### 3.3. Symbolic link và provider

`Files.getFileStore(Path)` chỉ có overload nhận `Path`, **không có `LinkOption...` để bạn yêu cầu riêng cách xử lý symbolic link trong chính lời gọi này**. Nếu cách giải quyết symbolic link ảnh hưởng yêu cầu (chẳng hạn link trỏ sang volume khác), hãy xác định đường dẫn mà bạn định hỏi, dùng `toRealPath()` khi đúng mục đích, và kiểm tra hợp đồng provider.

Không tự giả định một đường dẫn biểu thị link và đích thật chắc chắn cho thông tin storage giống nhau trên mọi hệ thống tệp. Hệ thống mạng, mount point, file system ảo hoặc archive provider có thể có hành vi riêng.

## 4. Các thông tin mà `FileStore` cung cấp

Những phương thức cốt lõi:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `name()` | `String` | Tên storage pool/volume theo implementation |
| `type()` | `String` | Kiểu bộ lưu trữ/hệ thống tệp theo implementation |
| `isReadOnly()` | `boolean` | Bộ lưu trữ được đánh dấu không hỗ trợ thay đổi file |
| `getTotalSpace()` | `long` | Tổng dung lượng, đơn vị byte |
| `getUnallocatedSpace()` | `long` | Dung lượng chưa cấp phát, đơn vị byte |
| `getUsableSpace()` | `long` | Dung lượng còn có thể dùng cho JVM, ước tính bằng byte |
| `getBlockSize()` | `long` | Số byte mỗi block nếu được hỗ trợ |
| `supportsFileAttributeView(String)` | `boolean` | Có hỗ trợ nhóm file attributes theo tên? |
| `supportsFileAttributeView(Class<?>)` | `boolean` | Có hỗ trợ nhóm file attributes theo kiểu interface? |
| `getFileStoreAttributeView(Class<V>)` | `V` hoặc `null` | Lấy view thuộc tính **của store** nếu được hỗ trợ |
| `getAttribute(String)` | `Object` | Đọc thuộc tính FileStore đặc thù do provider hỗ trợ |

`FileStore` là lớp **abstract**. Bạn thường không trực tiếp tạo `new FileStore()` mà nhận một instance do `Files.getFileStore(...)` hoặc API provider trả về.

`name()` và `type()` là **chuỗi phụ thuộc implementation**. Có thể thấy những tên như ổ đĩa, loại filesystem hay mount volume, nhưng định dạng chính xác không phải hợp đồng di động. Đừng lập trình:

```java
// Không nên gắn cứng tính đúng đắn của ứng dụng vào cách đặt tên:
if (store.type().equals("ext4")) {
    // Giả định mọi đặc tính filesystem bằng nhau trên các máy
}
```

Loại filesystem không phải công cụ dự đoán đầy đủ quota, permission, ACL hay tốc độ đọc/ghi. Khi cần một capability cụ thể, kiểm tra chính capability đó hoặc xử lý kết quả thao tác thực tế.

## 5. Phân biệt ba con số về dung lượng

Đây là phần dễ hiểu sai nhất của `FileStore`:

### 5.1. `getTotalSpace()` — tổng dung lượng store

```java
long totalBytes = store.getTotalSpace();
```

Giá trị đại diện dung lượng toàn bộ storage, **không phải kích thước file** được truyền vào `Files.getFileStore(path)`. Muốn biết kích thước file, dùng `Files.size(path)`; hai phương thức đo hai đối tượng khác nhau.

Ví dụ: một file 3 byte có thể nằm trên volume hàng trăm gigabyte. `Files.size(file) == 3` không dẫn đến `store.getTotalSpace() == 3`.

### 5.2. `getUnallocatedSpace()` — chưa cấp phát

```java
long freeBytes = store.getUnallocatedSpace();
```

Đây là số byte chưa được phân bổ trên store theo cách provider báo cáo. Nó **không có nghĩa** toàn bộ số byte này chắc chắn sẵn có để tiến trình hiện tại ghi file. Một phần dung lượng có thể dành riêng cho hệ thống, tài khoản quản trị, quota của người dùng hoặc chính sách khác.

### 5.3. `getUsableSpace()` — JVM có thể dùng

```java
long usableBytes = store.getUsableSpace();
```

Đây là **ước lượng số byte JVM có thể sử dụng** trên FileStore tại thời điểm truy vấn. Nó thường hữu ích hơn unallocated nếu bạn muốn biết có đáng thử ghi file lớn không, nhưng **vẫn chỉ là gợi ý**, không phải giấy bảo đảm rằng `Files.write(...)` sẽ thành công.

Dữ liệu dung lượng có thể thay đổi ngay sau khi gọi: ứng dụng khác ghi/xóa file, quota thay đổi, storage gắn từ xa mất kết nối, hoặc provider cập nhật số liệu. Không dùng các lần gọi này như một thao tác khóa trước dung lượng.

### 5.4. Bảng so sánh

| Câu hỏi | API hợp lý | Không nên hiểu thành |
| --- | --- | --- |
| File hiện tại lớn bao nhiêu? | `Files.size(file)` | Dung lượng volume |
| Volume được báo cáo tổng bao nhiêu? | `store.getTotalSpace()` | Giới hạn riêng của ứng dụng |
| Dung lượng chưa cấp phát? | `store.getUnallocatedSpace()` | Tất cả chắc chắn ghi được |
| JVM hiện có thể dùng bao nhiêu? | `store.getUsableSpace()` | File ghi tương lai chắc chắn thành công |
| Store có đánh dấu chỉ đọc? | `store.isReadOnly()` | Đầy đủ permission cho một Path cụ thể |
| Block của store bao nhiêu byte? | `store.getBlockSize()` | Buffer size bắt buộc cho mọi thao tác |

**Tất cả các space method trả về số byte kiểu `long`**. Số có thể rất lớn và không nên ép xuống `int` khi lưu trữ hay tính tổng.

### 5.5. Đổi đơn vị cho báo cáo

```java
double usableGiB = store.getUsableSpace()
        / (1024.0 * 1024 * 1024);
```

GiB là đơn vị dựa trên 1024; GB dựa trên 1000. Khi hiển thị, dùng nhãn đúng đơn vị và định dạng thích hợp. Không gọi `getUsableSpace()` rồi tự coi kết quả đã là MB.

Nếu ứng dụng cần số nguyên chính xác để quyết định ngưỡng, so sánh trực tiếp bằng **byte** trước khi định dạng thành GiB; việc làm tròn số ở giao diện có thể che chênh lệch nhỏ.

## 6. Chương trình hoàn chỉnh — lấy store của file tạm

Để tránh phụ thuộc đường dẫn `C:\...` hay `/home/...`, ví dụ tạo thư mục tạm rồi tạo file ngay trong thư mục đó. Tạo **`FileStoreBasicDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.FileStore;

public class FileStoreBasicDemo {
    public static void main(String[] args) throws Exception {
        var directory = Files.createTempDirectory(
                "filestore-demo-");
        var file = directory.resolve("sample.txt");

        try {
            Files.writeString(file, "ABC", StandardCharsets.UTF_8);

            FileStore store = Files.getFileStore(file);
            long total = store.getTotalSpace();
            long usable = store.getUsableSpace();
            long unallocated = store.getUnallocatedSpace();

            System.out.println("fileExists=" + Files.exists(file));
            System.out.println("fileSize=" + Files.size(file));
            System.out.println("storeFound=" + (store != null));
            System.out.println("basicSupported="
                    + store.supportsFileAttributeView("basic"));
            System.out.println("spaceNonNegative="
                    + (total >= 0 && usable >= 0
                    && unallocated >= 0));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 FileStoreBasicDemo.java
java FileStoreBasicDemo
```

Stdout dự kiến trên một file system thông thường cho phép tạo file và đọc thuộc tính:

```text
fileExists=true
fileSize=3
storeFound=true
basicSupported=true
spaceNonNegative=true
```

Giải thích:

1. `Files.createTempDirectory(...)` chọn vị trí thư mục tạm của hệ thống đang chạy; **không giả định** nó ở ổ nào.
2. File `sample.txt` được ghi đúng 3 byte vì ba chữ ASCII `ABC` theo UTF-8 có độ dài 3 byte.
3. `Files.getFileStore(file)` lấy FileStore tương ứng với file đã tạo, không cần đoán mount point.
4. `supportsFileAttributeView("basic")` là `true` theo hợp đồng FileStore với nhóm thuộc tính cơ bản.
5. Các phương thức dung lượng trả `long` byte không âm trong một bộ lưu trữ thông thường; demo chỉ kiểm tra điều kiện, **không đóng đinh con số GB của một máy cụ thể**.
6. `finally` dọn file và thư mục đã tạo. Nếu thao tác I/O thất bại, ví dụ có thể ném `IOException` thay vì luôn cho stdout như trên — điều đó đúng với bản chất truy cập filesystem thật.

Bài học tập trung vào metadata, nên ví dụ không cố tạo file thật lớn để “thử” dung lượng. Không nên dùng bài demo để phân bổ hàng gigabyte chỉ nhằm xác minh giá trị `getUsableSpace()`.

## 7. Khi bạn cần xem con số thật trên máy đang chạy

Ứng dụng giám sát hoặc công cụ dòng lệnh có thể hiển thị `FileStore` thực tế:

```java
// Đoạn minh họa trong một method throws IOException:
var target = java.nio.file.Path.of(".").toAbsolutePath();
var store = java.nio.file.Files.getFileStore(target);

System.out.println("name=" + store.name());
System.out.println("type=" + store.type());
System.out.println("readOnly=" + store.isReadOnly());
System.out.println("totalBytes=" + store.getTotalSpace());
System.out.println("unallocatedBytes=" + store.getUnallocatedSpace());
System.out.println("usableBytes=" + store.getUsableSpace());
```

**Không có một stdout chung chính xác** cho đoạn này: tên store, filesystem type, read-only và dung lượng phụ thuộc máy, hệ điều hành, container/volume và thời điểm gọi. Ví dụ không độc lập vì cần đặt trong class/method và xử lý I/O.

Nếu muốn viết bài kiểm thử tự động, tránh kiểu:

```java
// Không dùng làm assertion portable:
assert store.getTotalSpace() == 500_000_000_000L;
```

Hãy kiểm tra các invariant liên quan chức năng của bạn hoặc tạo abstraction cho FileStore để kiểm thử logic mà không phụ thuộc dung lượng thực tế của máy CI.

### 7.1. Đừng log thông tin hạ tầng không cần thiết

`store.name()` và `type()` có thể tiết lộ tên mount, volume hoặc cấu hình lưu trữ của môi trường. Trong ứng dụng production, giới hạn logging theo chính sách bảo mật; khi chỉ cần đánh giá ngưỡng, có thể log kích thước theo khoảng thay vì ghi đường dẫn đầy đủ của người dùng.

## 8. `getBlockSize()` — điểm đặc biệt được bổ sung trong Java 10

`FileStore.getBlockSize()` xuất hiện từ **Java 10**. Nó trả `long` là số byte của một block theo mô hình bộ lưu trữ do provider cung cấp.

```java
long blockBytes = store.getBlockSize();
```

Cần hiểu đúng:

- **Block size không phải dung lượng file**.
- **Block size không phải tổng dung lượng filesystem**.
- **Block size không phải `InputStream` buffer size bắt buộc**. Không tự áp dụng mọi `read`/`write` phải truyền một byte array dài đúng `blockBytes`.
- `FileStore.getBlockSize()` **có thể không được implementation hỗ trợ**. Hợp đồng cho phép ném `UnsupportedOperationException`; implementation mặc định của phương thức trong lớp FileStore ném ngoại lệ này.
- Nếu hỗ trợ, nó trả một giá trị dương bằng byte. Có thể có `IOException` khi truy vấn.
- Không giả định mọi volume đều có block 4096 byte. Hãy hỏi API thực tế hoặc để chế độ dự phòng nếu số block không phải yêu cầu bắt buộc.

Ví dụ xử lý đúng:

```java
try {
    long blockBytes = store.getBlockSize();
    System.out.println("blockBytes=" + blockBytes);
} catch (UnsupportedOperationException ex) {
    System.out.println("blockSize=unsupported");
}
```

Đây là đoạn minh họa cần một biến `store` đã được tạo. **Stdout phụ thuộc provider**: nếu hỗ trợ thì là một số dương cụ thể, nếu không hỗ trợ thì là `blockSize=unsupported`. Không đưa một con số duy nhất vào expected output cho mọi máy.

### 8.1. Khi nào block size hữu ích?

Thông tin block có thể giúp đánh giá đặc tính lưu trữ hoặc tối ưu sau khi đo đạc. Nhưng hiệu năng I/O còn phụ thuộc caching, buffer hệ điều hành, loại đĩa, mạng, cách truy cập và implementation Java. Không biến `getBlockSize()` thành “công thức chọn buffer tối ưu” mà không benchmark.

Nếu viết thư viện chạy nhiều hệ điều hành, hãy coi `getBlockSize` là một **optional capability**: nếu unsupported, giữ được chức năng chính thay vì buộc ứng dụng dừng chỉ vì không có metadata.

## 9. FileStore có hỗ trợ loại thuộc tính file nào?

`FileStore` có overload:

```java
boolean supportsFileAttributeView(String name);

boolean supportsFileAttributeView(
        Class<? extends FileAttributeView> type);
```

Tên view tiêu biểu:

| Attribute view | Tác dụng | Ghi chú |
| --- | --- | --- |
| `"basic"` / `BasicFileAttributeView` | Thông tin cơ bản như thời gian sửa và kích thước file | Hợp đồng FileStore luôn hỗ trợ basic |
| `"posix"` / `PosixFileAttributeView` | Quyền/nhóm/owner theo kiểu POSIX | Không có trên mọi provider |
| `"dos"` / `DosFileAttributeView` | Các flag DOS như hidden, read-only | Không có trên mọi provider |
| `"acl"` / `AclFileAttributeView` | Danh sách điều khiển truy cập | Phụ thuộc provider |
| `"user"` / `UserDefinedFileAttributeView` | Thuộc tính do ứng dụng gán thêm | Không bảo đảm hỗ trợ |
| `"owner"` / `FileOwnerAttributeView` | Thông tin chủ sở hữu | Phụ thuộc provider |

Ví dụ:

```java
var store = java.nio.file.Files.getFileStore(path);

boolean basicSupported = store.supportsFileAttributeView("basic");
boolean posixSupported = store.supportsFileAttributeView("posix");

boolean typedBasicSupported = store.supportsFileAttributeView(
        java.nio.file.attribute.BasicFileAttributeView.class);
```

Đây là đoạn minh họa với `path` là Path có thật. `basicSupported` và `typedBasicSupported` phải là `true` theo API; `posixSupported` phụ thuộc filesystem và provider. Một Windows volume có thể hỗ trợ view khác với Linux mount, và filesystem ảo có thể khác cả hai.

### 9.1. Capability không phải permission của một file

Nếu `store.supportsFileAttributeView("posix")` là `true`, điều đó **không bảo đảm** tiến trình được phép xem hoặc thay đổi mọi thuộc tính POSIX của mọi file trên store.

Cách đúng:

1. Hỏi FileStore có hỗ trợ nhóm thuộc tính cần dùng không.
2. Gọi `Files.getFileAttributeView(path, PosixFileAttributeView.class)` hoặc API tương ứng cho file cụ thể.
3. Xử lý `IOException`, permission và các giới hạn thực tế của provider.

Nếu bạn chỉ cần kiểm tra một file có được ghi hay không, `Files.isWritable(path)` có ý nghĩa khác với `store.isReadOnly()`. Cả hai vẫn không bảo đảm thao tác ghi tương lai sẽ thành công.

### 9.2. Đừng nhầm FileStore attribute view với file attribute view

Hai nhóm API:

- `store.getFileStoreAttributeView(MyStoreView.class)` lấy một view **thuộc tính của FileStore** nếu provider hỗ trợ; có thể trả `null`.
- `Files.getFileAttributeView(path, BasicFileAttributeView.class)` lấy view **thuộc tính của file được Path chỉ tới**.
  
Chúng không thay thế cho nhau. `getFileStoreAttributeView` có generic bound là `FileStoreAttributeView`, không phải `BasicFileAttributeView`. Đừng cố truyền `BasicFileAttributeView.class` vào method của FileStore chỉ vì tên có “AttributeView”.

## 10. Chương trình hoàn chỉnh — phân biệt `FileSystem`, `FileStore` và thuộc tính file

Tạo **`FileStoreVsSystemDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.FileStore;

public class FileStoreVsSystemDemo {
    public static void main(String[] args) throws Exception {
        var directory = Files.createTempDirectory(
                "store-vs-system-");
        var file = directory.resolve("x.dat");

        try {
            Files.write(file, new byte[] {1, 2});

            var fileSystem = file.getFileSystem();
            FileStore store = Files.getFileStore(file);

            System.out.println("pathFileSystem="
                    + (fileSystem != null));
            System.out.println("pathFileStore="
                    + (store != null));
            System.out.println("basicView="
                    + store.supportsFileAttributeView("basic"));
            System.out.println("fileBytes=" + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy:

```bash
javac --release 17 FileStoreVsSystemDemo.java
java FileStoreVsSystemDemo
```

Stdout:

```text
pathFileSystem=true
pathFileStore=true
basicView=true
fileBytes=2
```

Đoạn code cho thấy:

- `Path.getFileSystem()` truy cập đối tượng FileSystem liên kết với Path.
- `Files.getFileStore(file)` truy cập bộ lưu trữ thực tế chứa file.
- `Files.size(file)` trả kích thước **file riêng**, trong khi dung lượng từ `store` nói về cả bộ lưu trữ.
- Không có yêu cầu hai biến `fileSystem` và `store` phải bằng nhau hoặc cùng một type.
- Dùng byte array ngắn làm dữ liệu ví dụ, không tác động tới file hiện có của dự án.

## 11. `isReadOnly()` — hữu ích nhưng không phải kiểm tra quyền đầy đủ

`store.isReadOnly()` trả `true` nếu store không hỗ trợ các thay đổi đối với file. Đây là thông tin ở **tầng lưu trữ**.

Tuy nhiên:

- `false` **không bảo đảm** một file/path cụ thể có thể ghi. Người dùng có thể thiếu quyền, thư mục cha không cho tạo file, quota hết hoặc storage bị ngắt.
- `true` cho biết tính chất read-only của store, nhưng ứng dụng vẫn cần xử lý lỗi ghi theo hợp đồng I/O.
- `Files.isWritable(path)` kiểm tra tại cấp đường dẫn và quyền khả dụng theo provider; kết quả của nó cũng có thể thay đổi sau khi kiểm tra.
- Không coi “còn 10 GiB usable” cộng với “not read-only” là phép giữ chỗ dung lượng hay giấy phép ghi file.

Một preflight hợp lý có thể bỏ qua thao tác không có ý nghĩa nếu store read-only, nhưng **thao tác ghi thật phải tự xử lý thất bại**.

### 11.1. Vì sao nên giữ câu “có thể thử ghi” thay vì “được phép ghi”?

Nếu bạn cần cấp phát file dung lượng lớn, hãy sử dụng số liệu `getUsableSpace()` để **đánh giá** cơ hội thành công. Nhưng thực tế còn quota, quyền truy cập, loại file, chính sách của provider, thay đổi đồng thời và lỗi I/O.

Vì vậy tên biến `mayAttemptWrite` chính xác hơn `guaranteedCanWrite`.

## 12. Ví dụ thiết kế — preflight dung lượng chỉ là gợi ý

Tạo file **`StorageGuardDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.FileStore;

public class StorageGuardDemo {
    static boolean mayAttempt(
            FileStore store, long payloadBytes, long reserveBytes)
            throws IOException {
        if (payloadBytes < 0 || reserveBytes < 0) {
            throw new IllegalArgumentException("negative");
        }

        if (store.isReadOnly()) {
            return false;
        }

        long neededBytes = Math.addExact(
                payloadBytes, reserveBytes);

        return store.getUsableSpace() >= neededBytes;
    }

    public static void main(String[] args) throws Exception {
        var folder = Files.createTempDirectory(
                "storage-guard-");

        try {
            var store = Files.getFileStore(folder);

            System.out.println("zeroNeedsValidation="
                    + (mayAttempt(store, 0, 0)
                    == !store.isReadOnly()));

            try {
                mayAttempt(store, -1, 0);
            } catch (IllegalArgumentException ex) {
                System.out.println("negativeRejected=true");
            }
        } finally {
            Files.deleteIfExists(folder);
        }
    }
}
```

Chạy:

```bash
javac --release 17 StorageGuardDemo.java
java StorageGuardDemo
```

Stdout trên file system bình thường báo dung lượng không âm:

```text
zeroNeedsValidation=true
negativeRejected=true
```

Ý nghĩa:

1. Phương thức chặn số byte âm.
2. `isReadOnly()` và `getUsableSpace()` được dùng để đánh giá sơ bộ một thao tác ghi.
3. `Math.addExact` kiểm tra overflow trong phép cộng `long`; nếu tổng không biểu diễn được, Java ném `ArithmeticException` thay vì âm thầm tạo số âm.
4. `mayAttempt(...) == true` **không bao giờ nên được hiểu là “ghi chắc chắn thành công”**. Caller vẫn cần thực hiện ghi và xử lý `IOException`, quota/permission và cleanup nếu thất bại.
5. Dùng `long` byte end-to-end thay vì ép thành `int` hoặc làm tròn GiB trước khi so ngưỡng.

Trong code thật, hãy ước tính dữ liệu dự kiến ghi **đúng loại byte** của output, không dùng `String.length()` làm số byte khi mã hóa văn bản UTF-8 hoặc một charset đa byte.

## 13. Liệt kê toàn bộ stores và lấy store của một path là hai việc khác nhau

`Files.getFileStore(path)` lấy **một** FileStore của file/thư mục đó.

Nếu cần liệt kê các stores mà một FileSystem công bố:

```java
var fs = java.nio.file.FileSystems.getDefault();

for (var store : fs.getFileStores()) {
    System.out.println(
            store.name() + " / " + store.type());
}
```

Đây là đoạn minh họa có stdout phụ thuộc máy. `FileSystem.getFileStores()` trả một `Iterable<FileStore>` đại diện các bộ lưu trữ do file system/provider đó nhìn thấy. Nó **không** đồng nghĩa duyệt thư mục, và không bảo đảm số lượng, thứ tự hoặc tên cố định giữa Windows, Linux, máy ảo, container hoặc các nhà cung cấp hệ thống tệp.

| Nhu cầu | API |
| --- | --- |
| Biết file `/data/report.csv` thuộc store nào | `Files.getFileStore(path)` |
| Khám phá các stores mà default FileSystem nhìn thấy | `FileSystems.getDefault().getFileStores()` |
| Lấy file system provider của một Path | `path.getFileSystem().provider()` |
| Lấy một danh sách file trong thư mục | `Files.list(path)` / `Files.newDirectoryStream(path)` |
| Lấy size của một file | `Files.size(path)` |

**Không mặc định `getFileStores()` trả đủ mọi volume vật lý của máy**. Danh sách phụ thuộc provider, quyền và khả năng truy cập. Một store mạng có thể xuất hiện hoặc biến mất; một số FileSystem ảo cũng có storage semantics khác volume truyền thống.

## 14. `getAttribute` và thuộc tính chuyên biệt theo provider

`FileStore.getAttribute(String attribute)` cho phép đọc thuộc tính store đặc thù, thường theo dạng:

```text
view-name:attribute-name
```

Ví dụ Javadoc mô tả một view kiểu `zfs` giả định được hỗ trợ:

```java
// Ví dụ CHỈ hợp lệ trên provider có thuộc tính tương ứng:
boolean compression =
        (Boolean) store.getAttribute("zfs:compression");
```

**Không chạy dòng này trên mọi máy** vì `zfs` view/`compression` không phải thuộc tính chung mà Java SE yêu cầu mọi FileStore hỗ trợ. Nó có thể ném `UnsupportedOperationException`; khi thao tác I/O lỗi có thể ném `IOException`.

Một số provider có thuộc tính riêng hoặc FileStoreAttributeView riêng. Khi code ứng dụng cần một thuộc tính không tiêu chuẩn:

1. Xác định filesystem/provider thật sự hỗ trợ tính năng đó.
2. Tra tài liệu của provider về tên view, kiểu trả về và ngoại lệ.
3. Giữ nhánh dự phòng nếu view không có.
4. Không ép `(Boolean)` hoặc `(Long)` nếu provider không quy định rõ loại.
5. Không thay thế kiểm thử thực tế bằng việc chỉ biết `store.type()` giống một tên quen thuộc.

**`supportsFileAttributeView("posix")` không đảm bảo `getAttribute("posix:...")` có ý nghĩa như file-level attributes**. `supportsFileAttributeView` hỏi khả năng lưu thuộc tính cho file; `getAttribute` của FileStore đọc thuộc tính thuộc **store** theo view do provider quy định.

## 15. Thứ tự lỗi thường gặp và cách xử lý

| Vấn đề | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `Files.getFileStore(path)` ném `IOException` | File không có/không truy cập được, storage/provider lỗi | Kiểm tra path hợp lệ, quyền và trạng thái I/O; xử lý lỗi tại lời gọi |
| `getTotalSpace` / `getUsableSpace` ném `IOException` | Không đọc được số liệu storage | Hiển thị “chưa rõ” hoặc thất bại có kiểm soát |
| `getBlockSize` ném `UnsupportedOperationException` | Provider không hỗ trợ API tùy chọn | Dùng phương án dự phòng, không giả định block size |
| `getAttribute("x:y")` ném `UnsupportedOperationException` | View/attribute không có hoặc không hỗ trợ đọc | Không dùng attribute không tiêu chuẩn khi chưa biết provider |
| `supportsFileAttributeView("posix")` là `false` | Store không cung cấp view POSIX | Chọn API/phương án phù hợp platform |
| `isReadOnly()` là `false` nhưng ghi thất bại | Permission/quota/race/I/O | Vẫn xử lý ngoại lệ từ thao tác ghi |
| `getUsableSpace()` lớn nhưng file không ghi được | Space chỉ là hint, có giới hạn khác | Không dùng space check làm guarantee |
| `name/type` khác giữa máy | String phụ thuộc implementation | Không hardcode format trong logic |
| So sánh `store1 == store2` không nhất quán | Object identity không phải tiêu chí mount portable | Tránh suy luận tương đương vật lý từ `==` |
| FileStore đã lấy cho file nhưng file chuyển sang store khác | Thông tin cũ có thể không còn ý nghĩa | Lấy lại metadata khi cần; không giữ mãi object |

Với I/O thực, cần bắt `IOException` ở đúng tầng có thể xử lý, thông báo lỗi phù hợp hoặc chuyển lên caller. Không nên bắt rồi bỏ qua mọi `Exception` làm thất lạc thông tin về tình trạng thiết bị lưu trữ.

## 16. Tính không ổn định theo thời gian và concurrency

Thông tin của FileStore là **quan sát tại một thời điểm**. Ngay khi đọc xong:

- Một tiến trình khác có thể ghi dữ liệu lớn làm giảm usable space.
- Người dùng có thể xóa file hoặc thay đổi quota.
- Mount point/ổ mạng có thể thay đổi tình trạng kết nối.
- Đường dẫn có thể bị thay thế bằng một symbolic link hoặc file khác.
- Ứng dụng có thể chuyển file sang một FileStore khác.

Đó là lý do những phép:

```java
long usable = store.getUsableSpace();

if (usable >= expectedBytes) {
    // Vẫn phải xử lý lỗi của Files.write(...) khi ghi thật.
}
```

chỉ là preflight. Không thực hiện thao tác “kiểm tra rồi tin tưởng mãi” (time-of-check-to-time-of-use). Ngay cả việc gọi `Files.exists(path)` trước `getFileStore(path)` không thể ngăn race về file bị xóa.

**Đối với upload hoặc ghi file lớn**, quan tâm tới chính sách tài nguyên, quota, giới hạn kích thước ở tầng ứng dụng, ghi file tạm và cleanup khi lỗi. `FileStore` cung cấp tín hiệu ban đầu chứ không thay thế quản lý tài nguyên hay giao dịch dữ liệu.

## 17. Kiểm thử đa nền tảng như thế nào?

### 17.1. Điều có thể assert ổn định

Trong ví dụ có file tạm do chính chương trình tạo và dữ liệu `"ABC"`:

- `Files.exists(file)` là `true` ngay sau khi ghi thành công.
- `Files.size(file)` là `3` byte.
- `Files.getFileStore(file)` trả FileStore hoặc ném `IOException`.
- `store.supportsFileAttributeView("basic")` là `true` theo hợp đồng Java.
- Phần mềm nên trả về kết quả phù hợp hoặc một lỗi I/O được xử lý nếu storage không khả dụng.

### 17.2. Điều không nên đóng đinh

- `store.name()` bằng một chuỗi volume nhất định.
- `store.type()` luôn bằng `NTFS`, `ext4` hoặc một loại filesystem duy nhất.
- `store.getUsableSpace()` bằng một giá trị byte cố định hoặc luôn giữ nguyên giữa hai lời gọi.
- `store.getBlockSize()` luôn trả `4096`; nó có thể không được hỗ trợ.
- `FileSystems.getDefault().getFileStores()` luôn có đúng hai phần tử theo thứ tự nào đó.
- Một kiểm tra `isReadOnly`/`isWritable` đủ để bảo đảm khả năng ghi trong tương lai.

Nếu bạn muốn test logic so ngưỡng dung lượng, hãy tách nó khỏi phần gọi I/O hoặc dùng một abstraction giả lập không lệ thuộc dung lượng thật trên CI. Không dùng test mong hệ thống có hơn 10 GiB trống để chứng minh hàm đúng.

### 17.3. Đừng dùng `Path.toString()` làm định danh FileStore

`Path` biểu diễn logic đường dẫn theo provider. Khác biệt viết hoa, dấu phân cách, symbolic link, mount hoặc mapped drive có thể làm các chuỗi Path khác nhau trỏ đến cùng vùng lưu trữ, hoặc chuỗi có prefix giống nhau nhưng kết quả thực tế khác.

Chọn API dựa trên **ý nghĩa**: `Files.getFileStore` trả thông tin bộ lưu trữ cho file; `Files.isSameFile` so file khi đúng yêu cầu; `Path.toRealPath` giải quyết đường dẫn có thật. Không dùng một API để suy ra hợp đồng của API khác.

## 18. Những hiểu nhầm phổ biến

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “`FileStore` là kiểu mới hoàn toàn của Java 10.” | FileStore có từ Java 7; `getBlockSize` được bổ sung Java 10 |
| “`Path` có `getFileStore()`.” | Gọi `Files.getFileStore(path)` |
| “`path.getRoot()` chắc chắn xác định volume thật.” | Không trong mọi trường hợp mount/provider |
| “`FileStore.getTotalSpace` trả size file.” | Trả dung lượng store; file dùng `Files.size(path)` |
| “`getUnallocatedSpace` là số byte JVM chắc chắn ghi được.” | Nó là byte chưa cấp phát; JVM có thể bị quota/restriction |
| “`getUsableSpace` bảo đảm ghi được.” | Là số liệu gợi ý, thay đổi liên tục |
| “`isReadOnly=false` bảo đảm mọi file writable.” | Permission và lỗi I/O vẫn có thể từ chối |
| “`getBlockSize` chắc chắn có trên mọi store.” | Có thể ném `UnsupportedOperationException` |
| “Block size luôn 4 KiB.” | Phụ thuộc FileStore/provider |
| “`supportsFileAttributeView("posix")` luôn true.” | POSIX không có trên mọi provider |
| “Có view POSIX nghĩa là mọi file có thể chmod.” | Capability khác permission của file cụ thể |
| “FileStore và FileSystem là một.” | FileSystem định nghĩa hệ thống đường dẫn; FileStore là vùng lưu trữ |
| “`name()` hoặc `type()` có format chung mọi OS.” | Implementation-specific |
| “`FileStore.getAttribute("zfs:compression")` luôn hợp lệ.” | Thuộc tính provider-specific |
| “`getFileStore(path)` sau khi file bị xóa vẫn luôn hợp lệ.” | Javadoc không quy định chung khi file xóa/di chuyển |
| “Mọi Path có cùng root đều nằm trên một store.” | Mount point và provider có thể khiến khác nhau |
| “Một FileStore chỉ chứa một file.” | FileStore thường chứa nhiều file/thư mục |
| “`getFileStores()` liệt kê mọi file trong thư mục.” | Liệt kê stores của FileSystem, không phải file |
| “Đọc dung lượng một lần rồi có thể dùng mãi.” | Metadata thay đổi; cần xem time-of-check/time-of-use |

## 19. Bài tập có đáp án

### Bài 1 — Đường dẫn và store

```java
var path = java.nio.file.Path.of("reports", "daily.txt");
// Chưa có code tạo file daily.txt.
var fs = path.getFileSystem();
```

`fs` là gì? Làm sao lấy store chứa file khi file đã có?

**Đáp án:** `fs` có kiểu `FileSystem` liên kết với Path, **không phải FileStore**. Khi file tồn tại và truy cập được, gọi `Files.getFileStore(path)`. Nếu file dự kiến chưa tồn tại, có thể xem FileStore của **thư mục cha đang tồn tại** như một gợi ý cho nơi định tạo file, rồi vẫn xử lý thao tác tạo file thực tế.

### Bài 2 — Dung lượng file và dung lượng store

`Files.size(file)` trả `4096L`, còn `store.getTotalSpace()` trả số lớn hơn nhiều. Có mâu thuẫn không?

**Đáp án:** Không. Kết quả thứ nhất là dung lượng file cụ thể tính bằng byte; kết quả thứ hai là tổng dung lượng FileStore chứa file.

### Bài 3 — Chưa cấp phát và usable

`getUnallocatedSpace()` trả một con số lớn, nhưng `getUsableSpace()` nhỏ hơn. Có thể giải thích thế nào?

**Đáp án:** Provider/hệ điều hành có thể hạn chế phần dung lượng JVM được phép dùng (quota, reserved space...). `getUnallocatedSpace` nói về byte chưa cấp phát, còn `getUsableSpace` ước tính byte JVM có thể sử dụng.

### Bài 4 — Block size

```java
var store = java.nio.file.Files.getFileStore(path);
var blockBytes = store.getBlockSize();
```

Vì sao đoạn thứ hai có thể thất bại dù Java 17 có API `getBlockSize`?

**Đáp án:** Phương thức tồn tại từ Java 10, nhưng provider có thể không hỗ trợ; nó được phép ném `UnsupportedOperationException`. Cần xử lý nhánh không hỗ trợ nếu block size chỉ là metadata tùy chọn.

### Bài 5 — Thuộc tính POSIX

```java
boolean supported = store.supportsFileAttributeView("posix");
```

Nếu `supported` là `true`, ứng dụng đã có quyền sửa owner/permission của mọi file chưa?

**Đáp án:** Chưa. Đây là capability của FileStore; quyền với từng file và thao tác thực tế còn phụ thuộc filesystem, tài khoản, provider và có thể ném `IOException`.

### Bài 6 — Read-only

`store.isReadOnly() == false` và `getUsableSpace() > 1_000_000L`. Có thể khẳng định ghi file 1 MB chắc chắn thành công?

**Đáp án:** Không. Có thể thiếu quyền tạo file trong thư mục, có quota, I/O failure hoặc thay đổi dung lượng sau lần kiểm tra. Vẫn phải bắt lỗi khi ghi.

### Bài 7 — Metadata biến động

Bạn lấy `FileStore` cho file A rồi xóa A và chuyển file mới sang một mount khác. Có được tin kết quả từ `store` trước đó vẫn mô tả file mới không?

**Đáp án:** Không. Javadoc không định nghĩa hành vi chung của FileStore đã lấy khi file bị xóa hoặc chuyển store. Cần truy vấn lại cho file/đường dẫn phù hợp khi cần thông tin hiện thời.

### Bài 8 — Liệt kê stores

Phân biệt `FileSystems.getDefault().getFileStores()` và `Files.getFileStore(path)`.

**Đáp án:** Cách đầu trả một Iterable gồm các FileStore mà default FileSystem công bố; cách sau trả store gắn với vị trí file cụ thể. Không biến số lượng/định dạng list đầu thành giả định portable.

### Bài 9 — Root khác mount

Một hệ thống có file `/data/a.txt` và `/mnt/archive/b.txt`; hai đường dẫn cùng có root `/`. Có thể kết luận chúng cùng volume không?

**Đáp án:** Không. Root cú pháp `/` không đủ xác định mount/storage. Gọi `Files.getFileStore` cho vị trí thực tế, xử lý filesystem provider tương ứng.

### Bài 10 — Kiểm thử CI

Một test assert `store.getUsableSpace() == 10_000_000L`. Vì sao dễ sai?

**Đáp án:** Dung lượng trống phụ thuộc hệ thống, tiến trình khác và thời điểm. Hãy kiểm tra logic theo byte bằng dữ liệu kiểm soát được thay vì bắt buộc metadata thực tế có giá trị cố định.

### Bài 11 — Dự báo bộ nhớ cần ghi

Một báo cáo chứa 1 triệu ký tự. Có thể coi `1_000_000` ký tự là `1_000_000` byte để so `getUsableSpace` không?

**Đáp án:** Không trong tổng quát. Với UTF-8, nhiều ký tự Unicode dùng hơn một byte; một số ký tự ngoài BMP dùng hai đơn vị `char` nhưng có bốn byte UTF-8. Hãy ước tính hoặc tính số **byte thật của encoding đầu ra**, cộng overhead/reserve hợp lý và vẫn chấp nhận I/O failure.

### Bài 12 — Thuộc tính bộ lưu trữ

Có thể gọi `store.getAttribute("zfs:compression")` trên mọi Windows và Linux không?

**Đáp án:** Không. Đây là ví dụ attribute phụ thuộc provider. Chỉ dùng khi provider/file store có view hỗ trợ và tên/type được tài liệu hóa, có nhánh xử lý `UnsupportedOperationException`/`IOException`.

## 20. Checklist áp dụng trong dự án

Trước khi dùng `FileStore` trong một tính năng, hãy kiểm tra:

1. **Path dùng để hỏi có định vị đúng file/thư mục không?** Tránh đoán theo tên file hay root.
2. **File đã tồn tại chưa?** Nếu chưa, cần xem thư mục cha có thật và hiểu kết quả chỉ mang tính dự báo.
3. **Có xử lý `IOException` từ `Files.getFileStore` chưa?** Kể cả khi `Files.exists` trả true trước đó.
4. **Có phân biệt `FileSystem` và `FileStore` chưa?** Hai tầng khác nhau.
5. **Bạn cần kích thước file hay dung lượng volume?** `Files.size` khác `getTotalSpace`.
6. **Bạn đang dùng usable hay unallocated?** Không coi hai số là tương đương.
7. **Có dùng `long` cho byte và nhãn GiB/GB đúng không?** Không ép xuống `int`.
8. **Có hiểu space chỉ là hint không?** Thao tác ghi thật vẫn phải xử lý lỗi.
9. **Có check read-only đúng mục đích không?** `isReadOnly` không phải file permission.
10. **Có dùng `getBlockSize`?** Đã xử lý `UnsupportedOperationException` khi provider không hỗ trợ chưa?
11. **Có cần biết POSIX/DOS/ACL support không?** Kiểm tra capability với `supportsFileAttributeView`.
12. **Có nhầm `FileStoreAttributeView` và `FileAttributeView` không?** Chọn đúng cấp thuộc tính.
13. **Có dùng `getAttribute` chuyên biệt?** Chỉ dùng tên/type do provider thật sự cung cấp.
14. **Có phụ thuộc `name/type` để quyết định business logic?** Tránh suy luận từ format string implementation-specific.
15. **Có so sánh FileStore bằng `==` để kết luận cùng volume?** Không dựa vào identity đối tượng.
16. **Có xem sự thay đổi sau khi file bị xóa/di chuyển không?** Metadata cũ không tự có hợp đồng mô tả file mới.
17. **Có cần dữ liệu liên tục?** Refresh hợp lý, không cache vĩnh viễn số byte còn trống.
18. **Có suy diễn mọi volume từ `getFileStores()` không?** Enumeration phụ thuộc provider.
19. **Test có portable không?** Không hardcode tên store, type, block size hay số GB còn trống.
20. **Có yêu cầu giới hạn tài nguyên từ phía người dùng không?** Đặt giới hạn upload/backup ở tầng ứng dụng chứ không chỉ dựa vào metadata storage.
21. **Có tình huống cùng truy cập từ nhiều thread/process?** Dung lượng không là reservation, cần thiết kế xử lý race.
22. **Có chính sách xử lý lỗi đúng không?** Nếu không đọc được thông tin store, không tự cho rằng luôn còn đủ chỗ.

**Ghi nhớ:** `Files.getFileStore(Path)` cho biết **FileStore đang chứa file/thư mục được Path định vị**, từ đó có thể hỏi tên, loại, trạng thái read-only, dung lượng và khả năng thuộc tính của hệ thống tệp. `FileStore` có từ NIO.2/Java 7; `getBlockSize()` được bổ sung từ Java 10 và có thể không được hỗ trợ. Dung lượng là **thông tin tức thời và gợi ý**, không phải cam kết ghi thành công. Giữ ranh giới rõ giữa file, file system và file store, đồng thời viết code có xử lý I/O và kết quả phụ thuộc nền tảng.

### Tài liệu API

- [Files.getFileStore(Path) — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileStore — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html)
- [FileSystem — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html)
- [BasicFileAttributeView — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html)
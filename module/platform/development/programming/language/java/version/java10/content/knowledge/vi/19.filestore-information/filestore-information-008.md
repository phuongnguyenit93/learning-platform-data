# Kiểm thử trên các nhà cung cấp hệ thống tệp khác nhau

## 1. Mục tiêu: FileStore không đồng nghĩa với một ổ đĩa cố định

Khi ứng dụng Java làm việc với tệp, cùng một đoạn mã `java.nio.file.Files` có thể chạy trên nhiều **nhà cung cấp hệ thống tệp** (*file system providers*): hệ thống tệp mặc định của máy, một ZIP/JAR được mở như hệ thống tệp, nhà cung cấp ảo trong bộ nhớ do thư viện bên ngoài cung cấp, hoặc một hệ thống tệp chuyên biệt của ứng dụng.

Đối tượng `java.nio.file.FileStore` biểu diễn vùng lưu trữ mà provider công bố: có thể là volume, phân vùng, thiết bị, kho dữ liệu ảo hoặc một cơ chế khác do implementation quyết định. Nó **không bắt buộc tương ứng với một ổ đĩa vật lý**.

Bài học này thuộc nhóm **Thông tin FileStore** của Java 10. Điểm đặc biệt ở Java 10 là phương thức `FileStore.getBlockSize()`, trả số byte trên một block **nếu provider hỗ trợ**. Phương thức vẫn tồn tại trên các JDK hiện hành; nó **không** được bảo đảm hoạt động trên mọi provider.

~~~java
// Đoạn minh họa trong phương thức, cần import java.nio.file.*
Path file = Path.of("example.txt");
FileStore store = Files.getFileStore(file);

try {
    long blockSize = store.getBlockSize();
    System.out.println("Có block size: " + (blockSize > 0));
} catch (UnsupportedOperationException unsupported) {
    System.out.println("Provider không hỗ trợ getBlockSize");
}
~~~

Đoạn này giả định `example.txt` đã tồn tại và có thể truy cập. Khi hệ thống gặp lỗi I/O, `Files.getFileStore` hoặc `getBlockSize` còn có thể ném `IOException`; ví dụ hoàn chỉnh bên dưới khai báo/kiểm soát trường hợp đó.

**Quy tắc cốt lõi:** kiểm thử **hợp đồng API** và hành vi fallback, **không** kiểm thử một con số block size, dung lượng, tên volume hay thứ tự file store duy nhất chỉ đúng trên máy của lập trình viên.

## 2. Ba khái niệm phải phân biệt

| Khái niệm | Java API | Vai trò |
| --- | --- | --- |
| FileSystemProvider | `java.nio.file.spi.FileSystemProvider` | Nhà cung cấp các thao tác đối với một hệ thống tệp; có scheme như `file`, `jar` trong các provider tương ứng |
| FileSystem | `java.nio.file.FileSystem` | Hệ thống tệp cụ thể với `Path`, root, view thuộc tính và danh sách `FileStore` do nó cung cấp |
| FileStore | `java.nio.file.FileStore` | Mô tả kho lưu trữ: tên, kiểu, dung lượng tham khảo, trạng thái chỉ đọc, hỗ trợ view và có thể có block size |

Ví dụ:

~~~java
// Đoạn minh họa trong một phương thức.
FileSystem fs = FileSystems.getDefault();
System.out.println(fs.provider().getScheme()); // Thông thường "file".

for (FileStore store : fs.getFileStores()) {
    System.out.println(store.name() + " / " + store.type());
}
~~~

Vòng lặp có thể in **số dòng khác nhau** giữa Windows, Linux, macOS, container hoặc môi trường có mount từ xa. Không được đặt stdout cố định hay khẳng định mọi volume đều có một `FileStore` tương ứng trực tiếp.

Để lấy store gắn với một `Path` cụ thể:

~~~java
// Đặt trong một phương thức có throws IOException.
Path existingPath = Path.of(".").toAbsolutePath();
FileStore store = Files.getFileStore(existingPath);
~~~

`Files.getFileStore(path)` hỏi provider của `Path` và trả store nơi đường dẫn được lưu. Nên thử với một đường dẫn **đã tồn tại** trong vùng thử nghiệm; không giả định provider sẽ luôn xác định được store cho một đường dẫn chưa được tạo.

Một **provider** có thể có nhiều store. Một `FileStore` có thể là một mô hình ảo. Không mặc định rằng một ZIP bên trong tệp máy chủ có cùng tập thuộc tính với ổ đĩa chứa chính tệp ZIP đó.

## 3. Những phương thức FileStore cần kiểm thử

`FileStore` vẫn là API chuẩn của NIO. Các phương thức quan trọng:

| Phương thức | Ý nghĩa | Lưu ý khi kiểm thử |
| --- | --- | --- |
| `name()` | Tên của file store | Provider-defined, không so với chuỗi cố định |
| `type()` | Loại hệ thống tệp/storage do provider công bố | Khác giữa hệ điều hành và provider |
| `isReadOnly()` | Trạng thái chỉ đọc của store theo provider | Không đồng nghĩa kiểm tra toàn bộ quyền ghi tệp của user |
| `getTotalSpace()` | Dung lượng store theo byte | Có thể khác theo môi trường, quota, thời điểm |
| `getUnallocatedSpace()` | Số byte chưa phân bổ | Một phép đo tham khảo, không phải bảo đảm tạo tệp thành công |
| `getUsableSpace()` | Số byte khả dụng cho JVM | Là **hint** có thể thay đổi ngay sau khi đọc |
| `getBlockSize()` | Số byte mỗi block, **có từ Java 10** | Có thể ném `UnsupportedOperationException` |
| `supportsFileAttributeView(BasicFileAttributeView.class)` | Khả năng hỗ trợ view thuộc tính basic | Javadoc quy định luôn trả `true` cho Basic |
| `supportsFileAttributeView("posix")` | Khả năng hỗ trợ view POSIX | Phụ thuộc provider, không mặc định luôn đúng |
| `getAttribute("view:name")` | Đọc thuộc tính mở rộng của store | Provider-specific; có thể ném `UnsupportedOperationException` |
| `getFileStoreAttributeView(type)` | Lấy view thuộc tính của store | Có thể trả `null` nếu view không có |

**Điểm đặc trưng Java 10:**

~~~java
// Chữ ký từ Javadoc FileStore:
public long getBlockSize() throws IOException
~~~

- Thành công: giá trị `long` dương, đơn vị **byte mỗi block**.
- Provider **không hỗ trợ**: `UnsupportedOperationException`.
- Gặp lỗi I/O: `IOException`.
- Quan trọng: **implementation mặc định của `FileStore` cho phương thức này ném `UnsupportedOperationException`**. Một provider có thể chưa override, kể cả khi những phương thức FileStore khác vẫn hoạt động.

Do đó, thử `getTotalSpace()` thành công **không suy ra** `getBlockSize()` cũng được hỗ trợ.

### Không dùng số byte để chứng minh ghi chắc chắn thành công

`getUsableSpace()` và `getUnallocatedSpace()` chỉ là các giá trị tham khảo tại thời điểm gọi; những tiến trình khác, hạn ngạch, chính sách filesystem hoặc sai quyền truy cập có thể làm thao tác ghi tiếp theo thất bại. Không viết:

~~~java
// Logic sai về mặt bảo đảm:
if (store.getUsableSpace() >= requiredBytes) {
    // Không được khẳng định Files.write(...) chắc chắn thành công.
}
~~~

Cách đúng là xem dung lượng như **gợi ý để cảnh báo/lập kế hoạch**, sau đó vẫn xử lý `IOException` của thao tác ghi thực tế.

## 4. Test matrix: cần những lớp kiểm thử nào?

Một bộ kiểm thử tốt tách **unit tests giả lập** khỏi **integration tests trên provider thực**.

| Loại test | Môi trường | Điều kiểm tra | Mức ổn định |
| --- | --- | --- | --- |
| Unit | `FileStore` giả lập trả block size dương | Nhánh có hỗ trợ hoạt động | Xác định, không phụ thuộc OS |
| Unit | `FileStore` giả lập giữ implementation mặc định | Nhánh ném `UnsupportedOperationException` được xử lý | Xác định |
| Unit | `FileStore` giả lập ném `IOException` | Lỗi I/O không bị coi nhầm là “không hỗ trợ” | Xác định |
| Integration | Provider mặc định với tệp tạm | Đọc/ghi thực, lấy store theo path, Basic view, block size có thể hỗ trợ hoặc không | Phụ thuộc quyền và hệ thống chạy |
| Integration | `jdk.zipfs` với ZIP tạm | Mở, đọc/ghi entry, lấy FileStore của ZIP và thử capability | Có thể chạy khi provider ZIP có mặt |
| Integration | Windows/macOS/Linux/container/mount khác | Quyền, kiểu store, dung lượng, view và block size đặc trưng | Cần môi trường tương ứng |
| Integration tùy chọn | Memory/cloud/custom provider do dự án cài | Contract riêng của provider bên thứ ba | Chỉ khi dependency được cài và kích hoạt |

**Không thể chỉ chạy test trên máy phát triển rồi kết luận đa provider.** Trong CI, nên có unit test để bảo đảm nhánh xử lý và integration test trên những hệ điều hành/nhà cung cấp thực sự nằm trong phạm vi sản phẩm hỗ trợ.

### Những điều nên cố định trong test

- Một nội dung tệp ngắn do test tự tạo, ví dụ `"hello"`.
- Kiểu exception hoặc kết quả xử lý `UnsupportedOperationException`.
- `BasicFileAttributeView` được hỗ trợ theo hợp đồng Java.
- Nếu `getBlockSize()` thành công thì số byte phải **dương**, không phải luôn `4096`.
- Với ZIP provider khả dụng: có thể tạo entry rồi đọc lại chính nội dung đó.
- Không đòi tên store, tổng dung lượng hay thứ tự liệt kê phải giống trên mọi môi trường.

## 5. Xử lý getBlockSize bằng capability, không bằng giả định

### 5.1. Phân biệt hỗ trợ, không hỗ trợ và lỗi I/O

Một hàm probe có thể trả trạng thái `SUPPORTED` hoặc `UNSUPPORTED`. Nếu gặp `IOException`, cho caller biết đó là **lỗi truy cập/thao tác**, không mặc định coi như provider không hỗ trợ.

~~~java
// Đoạn minh họa các thành viên trong cùng class.
enum BlockStatus {
    SUPPORTED,
    UNSUPPORTED
}

static BlockStatus probeBlockSize(FileStore store) throws IOException {
    try {
        long size = store.getBlockSize();
        if (size <= 0) {
            throw new AssertionError("getBlockSize must be positive");
        }
        return BlockStatus.SUPPORTED;
    } catch (UnsupportedOperationException unsupported) {
        return BlockStatus.UNSUPPORTED;
    }
}
~~~

**Vì sao không viết `catch (Exception) { return UNSUPPORTED; }`?**

- `UnsupportedOperationException` báo provider không hỗ trợ chức năng.
- `IOException` báo lỗi I/O; đây có thể là lỗi tạm thời hoặc quyền truy cập, cần kiểm tra riêng.
- `AssertionError` khi số byte không dương giúp chỉ ra provider vi phạm hợp đồng thành công.
- Bắt mọi `Exception` rồi coi là “không hỗ trợ” sẽ làm mất thông tin và khiến test bỏ qua một sự cố thực.

### 5.2. Không gọi lại liên tục chỉ để “xác nhận” block size

`getBlockSize()` là một câu hỏi về thuộc tính store, không phải một chuẩn đo hiệu năng; không nên suy ra tốc độ I/O, cache size hay chunk size tối ưu chỉ từ một số block. Để đo hiệu năng, cần benchmark riêng với workload thực tế. Kích thước block dương của store không đồng nghĩa rằng `Files.write` chỉ có thể nhận dữ liệu theo bội số block; đó là chi tiết tổ chức lưu trữ, không phải ràng buộc API ghi byte của ứng dụng.

### 5.3. Hợp đồng cần có khi xây ứng dụng

Nếu ứng dụng chỉ muốn **hiển thị thông tin**: giá trị block size vắng vì không hỗ trợ có thể hiện `N/A`.

Nếu ứng dụng cần chọn một chiến lược ghi: hãy có fallback rõ và không dùng một kích thước block giả như một thuộc tính thật của provider. Nếu việc thiếu block size khiến thuật toán không hợp lệ, trả lỗi cụ thể theo yêu cầu thay vì lặng lẽ dùng kết quả không chính xác.

## 6. Unit test với FileStore giả lập: kiểm tra các nhánh khó gặp

`FileStore` là abstract class. Có thể viết một test double kế thừa nó và cài các phương thức abstract cần thiết, mà **không** cần tự viết toàn bộ `FileSystemProvider`.

Ví dụ code tối giản, biểu diễn ý tưởng:

~~~java
// Giả lập dành riêng cho test, đặt trong một class test.
class UnsupportedBlockStore extends FileStore {
    // Override các abstract method khác của FileStore.
    // KHÔNG override getBlockSize(): method mặc định sẽ ném
    // UnsupportedOperationException trên Java 10+.
}
~~~

Đoạn trên là **phác thảo**, chưa đủ các phương thức abstract để compile. Chương trình hoàn chỉnh ở mục 10 có một fake `FileStore` **đủ mọi override**, dùng trực tiếp với `probeBlockSize`.

Hai test quan trọng:

~~~java
// Dưới đây là biểu thức minh họa khi các fake đã được tạo.
probeBlockSize(new SupportedStore());   // SUPPORTED
probeBlockSize(new UnsupportedStore()); // UNSUPPORTED
~~~

Ngoài ra, cần một fake mà `getBlockSize()` ném `IOException` để xác nhận nhánh lỗi không bị nhầm thành `UNSUPPORTED`. Việc test các nhánh này trên máy phát triển thường **không thể bảo đảm**, bởi provider mặc định có thể luôn hỗ trợ hoặc luôn không hỗ trợ theo nền tảng. Test double giúp bộ test chủ động tạo điều kiện mong muốn.

### Vì sao không dùng reflection thay phương thức của FileStore thật?

Không nên hack private fields, dựa vào tên class nội bộ của JDK hay dùng reflection vào implementation. Nó giòn khi nâng cấp JDK và có thể bị giới hạn bởi module access. Test double theo API công khai là lựa chọn rõ ràng hơn.

Một thư viện mock hiện đại có thể tạo test double thay việc viết subclass, nhưng **không bắt buộc** cài thêm framework chỉ để kiểm tra ba nhánh đơn giản.

## 7. Integration test provider mặc định: ưu tiên tệp tạm

Provider mặc định là môi trường quan trọng nhưng khác nhau tùy hệ điều hành và cấu hình mount. Dùng `Files.createTempDirectory(...)` hoặc `Files.createTempFile(...)` để test không sửa các tệp thực của người dùng.

~~~java
// Ví dụ bên trong method có throws IOException.
Path folder = Files.createTempDirectory("fs-test-");

try {
    Path file = folder.resolve("sample.txt");
    Files.writeString(file, "hello", StandardCharsets.UTF_8);

    FileStore store = Files.getFileStore(file);

    // Javadoc quy định BasicFileAttributeView luôn được hỗ trợ.
    if (!store.supportsFileAttributeView(
            BasicFileAttributeView.class)) {
        throw new AssertionError("basic view missing");
    }

    // Không assert một số như 4096, chỉ kiểm contract.
    probeBlockSize(store);

    if (!"hello".equals(
            Files.readString(file, StandardCharsets.UTF_8))) {
        throw new AssertionError("readback mismatch");
    }
} finally {
    Files.deleteIfExists(folder.resolve("sample.txt"));
    Files.deleteIfExists(folder);
}
~~~

Mục tiêu của ví dụ:

- Đường dẫn và nội dung được test tự sở hữu.
- `Files.getFileStore(file)` chạy trên path **thực sự tồn tại**.
- `supportsFileAttributeView(BasicFileAttributeView.class)` phải true theo Javadoc.
- `probeBlockSize` chấp nhận cả provider hỗ trợ và không hỗ trợ, nhưng không che `IOException`.
- Test xác nhận **đọc lại đúng nội dung tệp**, không chỉ thành công khi hỏi thông tin FileStore.
- Dọn dẹp trong `finally`, tránh để test bẩn môi trường.

Không nên lấy `Path.of("/")` làm đường dẫn test duy nhất trên mọi hệ điều hành. Windows có drive letter và các ngữ nghĩa root khác. Dùng tệp tạm giúp test gắn với nơi chạy thực tế.

### Những thuộc tính thay đổi theo môi trường

~~~java
// Dùng để chẩn đoán thủ công, KHÔNG dùng expected output cố định.
System.out.println("store=" + store.name());
System.out.println("type=" + store.type());
System.out.println("readOnly=" + store.isReadOnly());
System.out.println("usable=" + store.getUsableSpace());
System.out.println("unallocated=" + store.getUnallocatedSpace());
System.out.println("total=" + store.getTotalSpace());
~~~

Tên/kiểu store, quyền và dung lượng có thể khác giữa máy chủ CI, container, Docker volume, mạng và tài khoản user. Những dòng trên chỉ minh họa logging chẩn đoán; `store` phải có trong phạm vi khi chạy. **Không** đưa những giá trị động đó vào stdout cố định của demo.

### isReadOnly không thay thế thử ghi thật

`store.isReadOnly()` phản ánh trạng thái chỉ đọc do provider công bố. Một store báo không chỉ đọc vẫn có thể từ chối một thao tác ghi do quyền thư mục, ACL, quota, sandbox, trạng thái mount hoặc chính sách ứng dụng. Khi cần xác minh khả năng ghi, tạo và xóa tệp tạm trong vùng được cấp phép, xử lý `IOException` và các lỗi quyền tương ứng.

## 8. Integration test với ZIP/JAR provider của JDK

JDK cung cấp module **`jdk.zipfs`**, một file-system provider xem nội dung ZIP/JAR như một hệ thống tệp. Module này vẫn được hỗ trợ trên Java hiện đại (không phải API legacy) và thường có trong JDK đầy đủ; runtime image tùy chỉnh bằng `jlink` có thể loại bỏ module, hoặc môi trường hạn chế không cài provider.

Đối với JDK 17+ có `jdk.zipfs`, có thể tạo ZIP mới như một FileSystem bằng URI `jar:`:

~~~java
// Đoạn trong method có throws IOException, chỉ minh họa.
Path zip = tempDirectory.resolve("data.zip"); // File chưa tồn tại.
URI uri = URI.create("jar:" + zip.toUri());

try (FileSystem zipFs = FileSystems.newFileSystem(
        uri, Map.of("create", "true"))) {
    Path entry = zipFs.getPath("/hello.txt");

    Files.writeString(entry, "hello zip", StandardCharsets.UTF_8);
    FileStore store = Files.getFileStore(entry);

    // Kiểm tra attribute view bắt buộc và probe block size.
    if (!store.supportsFileAttributeView(
            BasicFileAttributeView.class)) {
        throw new AssertionError("basic view missing");
    }
    probeBlockSize(store);

    if (!"hello zip".equals(
            Files.readString(entry, StandardCharsets.UTF_8))) {
        throw new AssertionError("ZIP round trip failed");
    }
}
~~~

`tempDirectory` là thư mục tạm do test tạo. Khi ZIP FS đóng, provider sẽ hoàn tất việc ghi tệp ZIP; sau đó cần xóa file ZIP tạm. **Không tạo trước một tệp ZIP rỗng rồi mặc nhiên coi đó là archive hợp lệ:** với tùy chọn `create=true`, dùng đường dẫn ZIP chưa tồn tại như trên.

Đây là một **provider khác** với provider mặc định, dù tệp ZIP nằm trên một file store của máy chủ. Vì vậy, API/attribute capabilities trong ZIP FS có thể khác với file store thật:

- `FileStore.getBlockSize()` có thể hỗ trợ hoặc ném `UnsupportedOperationException`. Không yêu cầu ZIP FS trả cùng kích thước block như disk.
- Một `ZipFileStore` có thể có thông tin dung lượng và loại store riêng. Không coi các giá trị đó là dung lượng vật lý có thể dùng để đo chỗ trống của ổ chứa ZIP.
- POSIX/DOS/ACL views và cách hỗ trợ metadata không giống nhau giữa default provider, ZIP FS và các phiên bản/cấu hình provider. Không hard-code `supportsFileAttributeView("posix") == true`.
- Một provider có thể không triển khai một thao tác cho ZIP, và một tính năng được hỗ trợ ở provider mặc định có thể không được hỗ trợ ở provider thứ hai.

### Khi module ZIP không có mặt

`FileSystems.newFileSystem(...)` có thể ném `ProviderNotFoundException` nếu không tìm thấy provider phù hợp. Trong bộ test đa nền tảng, nên quyết định rõ:

- Nếu ZIP FS là **chức năng bắt buộc của sản phẩm**, thiếu provider phải làm test **FAIL** và báo thiếu dependency/runtime module.
- Nếu ZIP FS chỉ là **môi trường kiểm thử bổ sung**, có thể đánh dấu **SKIP**, nhưng không nói test đã PASS khi chưa chạy.
- Nếu không thể tạo file hoặc không có quyền, đó thường là lỗi môi trường I/O; không tự động coi là “provider không có mặt”.

Khi đóng gói runtime image tùy chỉnh, xác minh module `jdk.zipfs` được bao gồm nếu ứng dụng cần đọc/ghi ZIP như file system.

## 9. Provider khác: CI, thư viện ngoài và các giả định cần tránh

### Thư viện in-memory hoặc provider bên thứ ba

Một dự án có thể dùng một provider in-memory hoặc provider cloud được cung cấp bởi thư viện bên ngoài. Đây **không phải** bộ phận mặc định bắt buộc của Java SE. Phải thêm dependency, tạo FileSystem theo tài liệu provider và chạy integration test riêng.

Không đặt giả định rằng mọi provider đều:
- hỗ trợ POSIX permissions hoặc ACL;
- cho `getBlockSize()` một con số dương;
- có dung lượng vật lý có nghĩa như một ổ đĩa;
- cho các `FileStore` có cùng tên và kiểu trên mọi môi trường;
- hỗ trợ symbolic link, hard link, atomic move, watch service hoặc file lock với cùng ngữ nghĩa;
- xử lý path separator, case sensitivity, thời gian timestamp và file attributes giống hệ thống mặc định.

Không được biến những giả định hệ điều hành thành hợp đồng chung của `FileStore`.

### Ma trận CI tối thiểu

| Môi trường | Lý do |
| --- | --- |
| Linux (hoặc nền tảng phát triển chính) | Test thao tác tệp thực và kiểm data contract |
| Windows, nếu ứng dụng hỗ trợ | Khác biệt path/volume/quyền và filesystem attribute views |
| macOS, nếu ứng dụng hỗ trợ | Kiểm tra trường hợp file store/metadata khác |
| JDK đầy đủ có `jdk.zipfs` | ZIP/JAR filesystem; kiểm thử API qua provider khác |
| Runtime image tùy chỉnh, nếu triển khai | Phát hiện module/provider thiếu |
| Storage mount từ xa/container, nếu sản phẩm thực sự dùng | Xác nhận quota, quyền, tính khả dụng và failure mode của môi trường thật |

Không nhất thiết chạy tất cả môi trường cho mọi dự án. **Phạm vi test phải theo nền tảng mà sản phẩm tuyên bố hỗ trợ.** Unit fake cần chạy nhanh trong mọi pipeline; integration test trên filesystem chuyên biệt có thể chạy theo job CI riêng.

### Provider-specific assertions phải được gắn nhãn rõ

Test ZIP nên nói “phải đọc lại entry do test vừa ghi”, chứ không nói “ZIP FS và ext4 phải có cùng block size”. Nếu sản phẩm phụ thuộc một attribute không thuộc Java SE, hãy viết test riêng chỉ chạy trên provider/version cung cấp attribute đó và có điều kiện skip/fail minh bạch.

## 10. Chương trình Java 17+ hoàn chỉnh: fake FileStore, default và ZIP

Chương trình này **không cần thư viện ngoài**. Nó thực hiện:

1. Unit test một `FileStore` giả lập **có** `getBlockSize()` trả `4096`.
2. Unit test một `FileStore` giả lập **không override** `getBlockSize()`, nhờ đó nhận `UnsupportedOperationException` mặc định.
3. Unit test một `FileStore` giả lập ném `IOException`, xác nhận lỗi I/O **không bị coi là UNSUPPORTED**.
4. Integration test với provider mặc định, tệp tạm, Basic attribute view và kiểm tra dữ liệu round-trip.
5. Integration test với ZIP filesystem của `jdk.zipfs` nếu có. Thiếu module được báo **SKIPPED** riêng, không giả là PASS.

Lưu file đúng tên **`FileStoreProviderTestDemo.java`**:

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.ProviderNotFoundException;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;
import java.util.Map;

public class FileStoreProviderTestDemo {

    enum BlockStatus {
        SUPPORTED,
        UNSUPPORTED
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static BlockStatus probeBlockSize(FileStore store)
            throws IOException {
        try {
            long blockSize = store.getBlockSize();
            check(blockSize > 0, "block size must be positive");
            return BlockStatus.SUPPORTED;
        } catch (UnsupportedOperationException ignored) {
            return BlockStatus.UNSUPPORTED;
        }
    }

    // Test double: các phương thức abstract đều có implementation.
    // Không override getBlockSize: dùng mặc định của FileStore.
    static class UnsupportedStore extends FileStore {

        @Override
        public String name() {
            return "fake";
        }

        @Override
        public String type() {
            return "fake";
        }

        @Override
        public boolean isReadOnly() {
            return false;
        }

        @Override
        public long getTotalSpace() {
            return 1000L;
        }

        @Override
        public long getUsableSpace() {
            return 600L;
        }

        @Override
        public long getUnallocatedSpace() {
            return 700L;
        }

        @Override
        public boolean supportsFileAttributeView(
                Class<? extends FileAttributeView> view) {
            return view == BasicFileAttributeView.class;
        }

        @Override
        public boolean supportsFileAttributeView(String view) {
            return "basic".equals(view);
        }

        @Override
        public <V extends FileStoreAttributeView> V
                getFileStoreAttributeView(Class<V> view) {
            return null;
        }

        @Override
        public Object getAttribute(String attribute) {
            throw new UnsupportedOperationException(attribute);
        }
    }

    static final class SupportedStore extends UnsupportedStore {
        @Override
        public long getBlockSize() {
            return 4096L;
        }
    }

    static final class IoFailureStore extends UnsupportedStore {
        @Override
        public long getBlockSize() throws IOException {
            throw new IOException("simulated file store I/O error");
        }
    }

    static void unitTests() throws IOException {
        check(probeBlockSize(new SupportedStore())
                == BlockStatus.SUPPORTED, "supported block");
        check(probeBlockSize(new UnsupportedStore())
                == BlockStatus.UNSUPPORTED, "unsupported block");

        boolean ioFailurePropagated = false;
        try {
            probeBlockSize(new IoFailureStore());
        } catch (IOException expected) {
            ioFailurePropagated = true;
        }
        check(ioFailurePropagated, "IOException was swallowed");

        System.out.println("fakeSupported=true");
        System.out.println("fakeUnsupported=true");
        System.out.println("fakeIOExceptionPropagated=true");
    }

    static void defaultProviderTest(Path folder)
            throws IOException {
        Path file = folder.resolve("local.txt");

        Files.writeString(file, "hello", StandardCharsets.UTF_8);

        FileStore store = Files.getFileStore(file);
        check(store.supportsFileAttributeView(
                BasicFileAttributeView.class), "basic view");
        probeBlockSize(store);

        check("hello".equals(
                Files.readString(file, StandardCharsets.UTF_8)),
                "default readback");

        System.out.println("defaultReadback=true");
        System.out.println("defaultBasicView=true");
        System.out.println("defaultBlockContractHandled=true");
    }

    static void zipProviderTest(Path folder) throws IOException {
        Path zipFile = folder.resolve("archive.zip");
        URI zipUri = URI.create("jar:" + zipFile.toUri());

        try (FileSystem zipFs = FileSystems.newFileSystem(
                zipUri, Map.of("create", "true"))) {

            Path entry = zipFs.getPath("/inside.txt");
            Files.writeString(
                    entry, "hello zip", StandardCharsets.UTF_8);

            FileStore store = Files.getFileStore(entry);
            check(store.supportsFileAttributeView(
                    BasicFileAttributeView.class), "ZIP basic view");
            probeBlockSize(store);

            check("hello zip".equals(
                    Files.readString(
                            entry, StandardCharsets.UTF_8)),
                    "ZIP readback");

            System.out.println("zipProvider=PASS");
        } catch (ProviderNotFoundException unavailable) {
            // Chỉ skip khi thiếu provider; lỗi I/O thực vẫn lan ra.
            System.out.println("zipProvider=SKIPPED_NO_PROVIDER");
        }
    }

    public static void main(String[] args) throws IOException {
        unitTests();

        Path folder = Files.createTempDirectory("fs-provider-");

        try {
            defaultProviderTest(folder);
            zipProviderTest(folder);
        } finally {
            Files.deleteIfExists(folder.resolve("local.txt"));
            Files.deleteIfExists(folder.resolve("archive.zip"));
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 FileStoreProviderTestDemo.java
java FileStoreProviderTestDemo
~~~

**Stdout mẫu chính xác trên JDK 17 đầy đủ có `jdk.zipfs`, khi môi trường cho phép tạo file tạm và tất cả phép kiểm tra thành công:**

~~~text
fakeSupported=true
fakeUnsupported=true
fakeIOExceptionPropagated=true
defaultReadback=true
defaultBasicView=true
defaultBlockContractHandled=true
zipProvider=PASS
~~~

**Nếu runtime image không có ZIP provider**, sáu dòng đầu vẫn giống như trên khi default-provider test thành công, còn dòng cuối là:

~~~text
zipProvider=SKIPPED_NO_PROVIDER
~~~

Nếu xảy ra lỗi I/O hoặc vi phạm contract, chương trình có thể ném ngoại lệ/`AssertionError` thay vì in đủ các dòng. Đây là **thất bại cần điều tra**, không phải biến thể stdout được coi là PASS. Những dòng stdout cố định không in dung lượng hay kích thước block thực tế; chúng kiểm tra khả năng xử lý đúng cả hai trạng thái hợp lệ.

### Tại sao chương trình chạy được trên Java 17?

- `FileStore.getBlockSize()` có từ Java 10.
- `Files.writeString/readString` có từ Java 11.
- `Map.of` có từ Java 9.
- `jdk.zipfs` là module đã được cung cấp từ Java 9 nhưng có thể không có trong runtime image tối giản.
- Việc kế thừa `FileStore` và không override `getBlockSize()` cho fake kiểm tra đúng implementation mặc định hiện hành.
- Không dùng API nội bộ `sun.*` hoặc `jdk.nio.zipfs.*`, chỉ dùng `java.nio.file` công khai.
- Dữ liệu tệp tạm và tên file ZIP do test tạo, không ghi vào tệp dự án hay dữ liệu người dùng.

### Đọc kết quả theo từng test

**fakeSupported=true:** `SupportedStore.getBlockSize()` trả `4096L` (số do test **chủ động mô phỏng**, không phải kết luận về mọi ổ đĩa). `probeBlockSize` chấp nhận giá trị dương.

**fakeUnsupported=true:** `UnsupportedStore` không override `getBlockSize()`. Phương thức mặc định của `FileStore` ném `UnsupportedOperationException`; hàm probe chuyển sang trạng thái `UNSUPPORTED`.

**fakeIOExceptionPropagated=true:** fake thứ ba ném `IOException`, và hàm probe để ngoại lệ lan ra. Test xác nhận không nuốt lỗi thành “không hỗ trợ”.

**defaultReadback / defaultBasicView / defaultBlockContractHandled:** provider mặc định đã cho phép tạo tệp, đọc lại đúng chuỗi, hỗ trợ BasicFileAttributeView và `getBlockSize` đi qua một trong hai nhánh **giá trị dương** hoặc **không hỗ trợ**. Không in giá trị block size cụ thể.

**zipProvider=PASS:** module ZIP có mặt, tạo ZIP filesystem, ghi/đọc được `inside.txt`, lấy `FileStore` của path trong ZIP và probe capability thành công. Dùng `try-with-resources` để đóng filesystem.

**zipProvider=SKIPPED_NO_PROVIDER:** không tìm được provider phù hợp với URI `jar:`. Đây là trạng thái skip **có lý do** khi ZIP chỉ là bài test bổ sung; nếu ứng dụng thực sự cần ZIP, phải đổi thành fail trong CI.

## 11. Các trường hợp lỗi phải kiểm thử riêng

### 11.1. Không hỗ trợ chức năng

~~~java
try {
    long bytes = store.getBlockSize();
    // bytes > 0 nếu thành công.
} catch (UnsupportedOperationException unsupported) {
    // Quyết định fallback/hiển thị N/A.
}
~~~

`UnsupportedOperationException` không phải một lỗi “provider hỏng”. Nó có thể là trạng thái hợp lệ của một provider không có khái niệm block size mà Java có thể đọc được. Tuy nhiên, nếu ứng dụng *bắt buộc* cần block size, đây vẫn là điều kiện khiến chức năng của ứng dụng không đáp ứng yêu cầu.

### 11.2. Lỗi I/O thực sự

~~~java
try {
    long bytes = store.getBlockSize();
} catch (IOException io) {
    // Báo lỗi I/O, giữ cause và thông tin ngữ cảnh.
}
~~~

`IOException` không phải `UnsupportedOperationException`; không trả `0` giả rồi dùng nó như block size hợp lệ. Khi dùng `Files.getFileStore(path)` cũng phải xử lý `IOException`.

### 11.3. Permission và môi trường sandbox

Nếu không có quyền tạo file trong thư mục tạm, integration test có thể thất bại. Không đổi mọi `AccessDeniedException` thành “provider không hỗ trợ”. Hãy cấp quyền/tùy chọn đường dẫn test phù hợp hoặc ghi nhận rõ môi trường CI không đạt điều kiện.

### 11.4. Không hỗ trợ attribute view

~~~java
if (store.supportsFileAttributeView("posix")) {
    // Có thể kiểm thử thao tác POSIX khi hệ thống đáp ứng.
} else {
    // Bỏ qua phần POSIX đặc thù; không ép provider này giả lập POSIX.
}
~~~

Kiểm hỗ trợ view trước khi dùng API cần view đó. Với các hệ thống lưu trữ từ xa, Javadoc còn lưu ý việc báo hỗ trợ một số attribute view có thể có hạn chế do provider. Không coi mọi giá trị `true` là bảo đảm rằng từng thao tác cập nhật metadata đều sẽ thành công trong mọi tình huống.

### 11.5. FileStoreAttributeView và thuộc tính đặc thù

`getFileStoreAttributeView(SomeView.class)` có thể trả `null`. `getAttribute("someView:attribute")` có thể ném `UnsupportedOperationException`. Những attribute không thuộc chuẩn chung của ứng dụng phải được thử có điều kiện, không hard-code trên mọi provider.

### 11.6. Dung lượng biến động

Kiểm thử dạng:

~~~java
// Assertion mong manh, không nên dùng:
assert store.getUsableSpace() == 10_000_000_000L;
~~~

Một phép đo dung lượng thay đổi theo hoạt động hệ thống, quota và thời điểm. Test có thể xác nhận kiểu dữ liệu, kiểm phản hồi hợp lệ theo contract và không đòi một con số cụ thể. Khi kiểm giới hạn “đủ chỗ ghi”, vẫn phải thử ghi và xử lý lỗi I/O thật.

## 12. Những lỗi phổ biến khi kiểm thử đa provider

| Giả định/lỗi | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “Mọi FileStore đều có `getBlockSize()`.” | Method từ Java 10 có implementation mặc định ném `UnsupportedOperationException`. | Test cả nhánh có và không hỗ trợ. |
| “Block size của mọi ổ là 4096.” | Tùy filesystem/provider. | Assert dương khi hỗ trợ, không assert số cụ thể. |
| “`getUsableSpace` luôn là dung lượng chắc chắn ghi được.” | Chỉ là hint, có thể đổi ngay sau khi đọc. | Xử lý lỗi ghi thực tế. |
| “`isReadOnly()==false` nghĩa user chắc chắn ghi được.” | Quyền thư mục, quota, ACL, sandbox còn tác động. | Test ghi vào vùng hợp lệ, xử lý lỗi riêng. |
| “ZIP dùng chung mọi thuộc tính với volume chứa ZIP.” | ZIP là provider riêng, có mô hình FileStore riêng. | Hỏi FileStore từ ZIP Path, đừng đoán. |
| “`supportsFileAttributeView("posix")` luôn true.” | POSIX không thuộc mọi provider. | Kiểm tra support trước khi dùng. |
| “Tên/type của store là một chuỗi cố định.” | Phụ thuộc hệ điều hành/provider/mount. | Chỉ log chẩn đoán; test theo contract. |
| “Cứ không chạy được ZIP là skip.” | IOException, tệp hỏng hoặc bug có thể là lỗi thật. | Chỉ skip thiếu provider tùy chính sách; lỗi khác fail. |
| “Đường dẫn `/tmp` hoặc `C:\` hợp lệ mọi nơi.” | Path và quyền phụ thuộc nền tảng. | Dùng `Files.createTempDirectory`. |
| “`FileSystems.getDefault()` chính là ZIP FS đã mở.” | ZIP được mở qua một FileSystem khác. | Dùng `Path` của đúng ZIP FS. |
| “FileStore chỉ là một lớp bọc ổ đĩa vật lý.” | Provider có thể biểu diễn storage ảo. | Dựa hợp đồng FileStore. |
| “Mock mỗi giá trị block size là đủ để chứng minh app chạy trên mọi provider.” | Unit fake không thay thế integration test thật. | Kết hợp fake + default + ZIP + platform CI. |
| “Nếu API trả `UnsupportedOperationException` thì có thể nuốt luôn `IOException`.” | Hai lỗi có ngữ nghĩa khác. | Phân loại rõ capability và lỗi I/O. |
| “Thứ tự `getFileStores()` và số lượng store luôn cố định.” | Danh sách có thể đổi khi mount/CI thay đổi. | Không assert thứ tự/số lượng không thuộc hợp đồng. |

## 13. Checklist code review và vận hành CI

### Checklist thiết kế

- [ ] Có phân biệt `FileSystemProvider`, `FileSystem` và `FileStore`?
- [ ] Lấy FileStore bằng `Files.getFileStore(existingPath)` của **đúng provider**?
- [ ] Có xử lý cả `UnsupportedOperationException` và `IOException` của `getBlockSize()`?
- [ ] Có tránh hard-code block size, total space, store name/type?
- [ ] Có coi dung lượng là hint, không đảm bảo ghi thành công?
- [ ] Có test Basic attribute view và kiểm điều kiện cho POSIX/DOS/ACL?
- [ ] Có unit test fake cho supported, unsupported và I/O failure?
- [ ] Có integration test với tệp tạm thuộc default provider?
- [ ] Có chạy ZIP FS nếu `jdk.zipfs` là dependency được hỗ trợ?
- [ ] Nếu ZIP không có, trạng thái là SKIPPED hay FAIL đã được chính sách hóa?
- [ ] Có dọn file tạm và đóng ZIP FileSystem bằng try-with-resources?
- [ ] Có CI trên những OS/provider/storage thực tế mà sản phẩm hỗ trợ?
- [ ] Có giữ log chẩn đoán đủ để phân biệt lỗi provider với thiếu quyền/hạ tầng?
- [ ] Có tránh test dựa implementation class nội bộ của JDK và reflection?
- [ ] Có kiểm tra Java target cho API mới từ Java 10?

### Bài tập tự kiểm tra

**Câu 1.** `FileStore.getBlockSize()` có từ Java nào, và khi provider không hỗ trợ nó làm gì?

**Đáp án:** Từ Java 10; có thể ném `UnsupportedOperationException`. Implementation mặc định của `FileStore` ném ngoại lệ này.

**Câu 2.** Nếu `getBlockSize()` trả `8192` trên một filesystem, điều gì được bảo đảm?

**Đáp án:** Giá trị trả là số byte dương mỗi block theo provider. Nó không chứng minh mọi provider khác cũng có block size `8192`, và không phải một lời hứa về tốc độ I/O.

**Câu 3.** Tại sao `getUsableSpace() == 0` không nên được xem là một dự báo tuyệt đối cho tương lai?

**Đáp án:** Dung lượng là trạng thái biến động theo quota, hoạt động hệ thống và thời điểm đọc. Dùng để tham khảo, không thay thế thử ghi và bắt lỗi I/O.

**Câu 4.** Có nên assert `store.type().equals("ext4")` trong test chung Java chạy cả Windows không?

**Đáp án:** Không. Kiểu hệ thống tệp phụ thuộc môi trường. Chỉ kiểm cụ thể trong test được đánh dấu chạy trên filesystem mong muốn.

**Câu 5.** Vì sao `FileStore.getBlockSize()` cần unit test dùng test double?

**Đáp án:** Vì trên một máy thật rất khó ép provider mặc định lần lượt hỗ trợ, không hỗ trợ và ném IOException. Test double kiểm ba nhánh một cách xác định.

**Câu 6.** `Files.getFileStore(zipEntry)` có bắt buộc giống `Files.getFileStore(zipArchivePath)` không?

**Đáp án:** Không. `zipEntry` thuộc ZIP FileSystem, còn `zipArchivePath` thuộc provider mặc định chứa tệp ZIP. Chúng có thể công bố FileStore/attribute khác.

**Câu 7.** JDK nào có thể cần module `jdk.zipfs` để chạy integration test?

**Đáp án:** Những JDK/runtime image triển khai ZIP filesystem qua module `jdk.zipfs`; runtime tùy chỉnh có thể không chứa module. Nếu ZIP là chức năng bắt buộc, thiếu provider cần fail thay vì coi là pass.

**Câu 8.** `supportsFileAttributeView("posix")` luôn true trên Windows và ZIP FS không?

**Đáp án:** Không có cam kết như vậy. Kiểm provider cụ thể trước khi gọi thao tác cần view POSIX.

**Câu 9.** Có nên bỏ qua mọi `IOException` ở test ZIP và kết luận provider không có mặt không?

**Đáp án:** Không. `IOException` có thể báo lỗi thật khi tạo, ghi hoặc đọc ZIP; chỉ provider thực sự không hiện diện mới là trường hợp skip có điều kiện.

**Câu 10.** Kết quả integration test trên một máy có đủ chứng minh ứng dụng tương thích mọi filesystem không?

**Đáp án:** Không. Cần unit test cho contract và matrix integration theo các provider/OS thực tế mà sản phẩm hỗ trợ.

## 14. Nguồn chính thức vẫn áp dụng

- [Oracle Java SE 26 — FileStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileStore.html): đặc tả còn hiệu lực, `getBlockSize` từ Java 10, khả năng ném `UnsupportedOperationException`/`IOException` và các phương thức dung lượng/attribute views.
- [Oracle Java SE 17 — FileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): API trên target Java 17, quy tắc block size, Basic view và không hỗ trợ các thuộc tính.
- [Oracle Java SE 17 — Files.getFileStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): lấy FileStore từ một path.
- [Oracle Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `getFileStores()`, `provider()`, root, file attribute views và quản lý vòng đời.
- [Oracle Java SE 17 — FileSystemProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): SPI cho các provider thực hiện thao tác NIO.
- [Oracle Java SE 17 — FileSystems](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystems.html): `getDefault()` và `newFileSystem(...)` để mở filesystem chuyên biệt.
- [Oracle Java SE 17 — jdk.zipfs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.zipfs/module-summary.html): ZIP/JAR filesystem provider chính thức, scheme `jar` và tùy chọn `create=true`.
- [Oracle Java SE 17 — BasicFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): view thuộc tính cơ bản của tệp.
- [OpenJDK — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): runtime image tùy chỉnh có thể chỉ gồm các module được chọn; kiểm tra provider/module mà ứng dụng cần.

**Ghi nhớ:** **Kiểm thử đa provider phải bám vào hợp đồng Java NIO thay vì con số của một ổ đĩa.** `FileStore.getBlockSize()` có từ Java 10 nhưng provider có quyền **không hỗ trợ**; dùng fake để kiểm đủ nhánh, thử với tệp tạm trên provider mặc định và ZIP/JAR provider khi có mặt, phân biệt thiếu capability với lỗi I/O, và chỉ assert những đặc tính thực sự được API hoặc provider cụ thể cam kết.
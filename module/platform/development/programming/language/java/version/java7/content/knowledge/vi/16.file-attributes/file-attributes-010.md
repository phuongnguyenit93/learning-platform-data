# FileStore và kiểm tra dung lượng khả dụng trong Java

## 1. Bài toán: ứng dụng sẽ ghi dữ liệu vào đâu và còn bao nhiêu chỗ?

Một dịch vụ xử lý upload, xuất báo cáo, sao lưu hoặc giải nén thường cần biết **nơi lưu file đích còn bao nhiêu dung lượng**. Nếu chỉ gọi `Files.size(file)`, ta biết độ dài logic của một file nhưng không biết còn bao nhiêu byte trên ổ. Nếu chỉ đo dung lượng nơi chạy chương trình, ta có thể đo nhầm volume khi thư mục đích nằm trên mount/drive khác.

Java NIO.2 có `java.nio.file.FileStore`, được giới thiệu trong Java 7 và **vẫn được hỗ trợ hiện nay**. Nó biểu diễn một vùng lưu trữ do filesystem provider định nghĩa: có thể là partition, volume, storage pool, filesystem hoặc một thiết bị/vùng lưu trữ trừu tượng.

Cách lấy file store chứa thư mục đích:

```java
import java.nio.file.Files;
import java.nio.file.FileStore;
import java.nio.file.Path;

// destinationDirectory đã tồn tại và ứng dụng có quyền truy cập.
Path destinationDirectory = Path.of("data", "uploads");
FileStore store = Files.getFileStore(destinationDirectory);
```

Đoạn trên là **minh họa trong phương thức** có xử lý `IOException`. Nó không phải chương trình độc lập. `Path.of(...)` có từ Java 11; ví dụ đầy đủ trong bài dùng **JDK 17+**.

Sau đó có thể truy vấn:

```java
long totalBytes = store.getTotalSpace();
long unallocatedBytes = store.getUnallocatedSpace();
long usableBytes = store.getUsableSpace();
boolean readOnly = store.isReadOnly();
```

Ba giá trị dung lượng là `long` tính bằng **byte**; các phương thức dung lượng có thể ném `IOException`.

**Kết luận phải nhớ ngay:** `FileStore.getUsableSpace()` chỉ là **ước lượng/gợi ý tại thời điểm đọc**, không dự trữ không gian. Dù hệ thống báo đủ chỗ, các thao tác tạo file, ghi, flush, đóng stream và publish kết quả vẫn có thể thất bại vì I/O, quota hoặc thay đổi đồng thời. Phải xử lý các lỗi đó thật sự.

## 2. Ba chỉ số dung lượng quan trọng

### 2.1. `getTotalSpace()` — dung lượng tổng

```java
long total = store.getTotalSpace();
```

Đây là dung lượng tổng của **file store** được provider báo về. Nó không phải dung lượng còn trống và không phải kích thước của file ở đường dẫn đang xem.

Nếu tổng byte vượt `Long.MAX_VALUE`, API Java 17 quy định kết quả là `Long.MAX_VALUE`. Không nên giả định một giá trị `long` sẽ đo được dung lượng của mọi storage không giới hạn một cách chính xác tuyệt đối.

### 2.2. `getUnallocatedSpace()` — byte chưa cấp phát

```java
long unallocated = store.getUnallocatedSpace();
```

Con số này phản ánh byte **chưa được cấp phát** trong file store theo cách provider diễn giải. Nó không nhất thiết là số byte tiến trình Java có quyền sử dụng. Chẳng hạn hệ thống có thể dành chỗ riêng hoặc áp quota cho tài khoản.

Theo Java API, giá trị là một **hint**, không bảo đảm có thể sử dụng số byte đó trong tương lai. Những thay đổi I/O bên ngoài JVM có thể khiến số đo không còn đúng ngay lập tức.

### 2.3. `getUsableSpace()` — số byte khả dụng đối với JVM

```java
long usable = store.getUsableSpace();
```

Phương thức này được mô tả là số byte có thể sử dụng bởi **JVM hiện tại** trên file store. Khi cần xét **nơi đích có khả năng đáp ứng một thao tác ghi**, đây thường là chỉ số nên tham khảo trước.

Tuy nhiên:

- `usable` không phải giao kèo rằng có thể ghi chắc chắn lượng byte đó.
- Có thể thay đổi tức thời vì luồng khác, process khác, quota, filesystem mạng hoặc các hoạt động I/O.
- Không xác nhận thư mục cụ thể có cho phép tạo file.
- Không phản ánh trọn vẹn mọi yêu cầu allocation, block overhead và metadata.
- Không thay thế giới hạn quota do ứng dụng tự quản lý giữa nhiều người dùng.

### 2.4. Bảng phân biệt

| API | Thông tin trả về | Dùng để | Giới hạn |
| --- | --- | --- | --- |
| `store.getTotalSpace()` | Tổng byte file store | Capacity dashboard | Không phải free space |
| `store.getUnallocatedSpace()` | Byte chưa cấp phát | Theo dõi filesystem | Không bảo đảm JVM dùng được |
| `store.getUsableSpace()` | Byte JVM được báo có thể dùng | Cảnh báo/chấp nhận sơ bộ | Không bảo đảm I/O thành công |
| `Files.size(path)` | Độ dài logic một file | Ước lượng payload nguồn | Không phải dung lượng volume |
| `store.isReadOnly()` | File store có read-only không | Kiểm tra điều kiện chặn ghi | Không nói mọi thư mục đều writable |
| `Files.isWritable(path)` | Dấu hiệu được phép ghi tại path hiện tại | Kiểm tra quyền sơ bộ | Không bảo đảm lần ghi tiếp theo |

**Không tự động suy ra `total = used + usable`.** `usable` có thể thấp hơn `unallocated` do reserved space, quyền hoặc quota; hệ thống lưu trữ với compression, snapshot và thin provisioning còn có cách tính riêng. Các giá trị cũng không được API hứa là một snapshot nguyên tử cùng thời điểm.

## 3. Chọn đúng `FileStore` cho đường dẫn đích

### 3.1. File chưa tồn tại: đo thư mục cha

`Files.getFileStore(path)` nhận một `Path` tới file hoặc thư mục mà file store chứa nó cần được xác định. Nếu file đích **chưa tồn tại**, gọi trực tiếp với tên file mới có thể gây `NoSuchFileException` hoặc `IOException`.

```java
Path target = Path.of("data", "uploads", "new-report.zip");

// Không nên truy vấn file chưa được tạo:
// FileStore store = Files.getFileStore(target);

Path existingParent = target.getParent();
FileStore store = Files.getFileStore(existingParent);
```

Điều kiện: `existingParent` thực sự tồn tại, đã được xác minh thuộc vùng cho phép và có thể truy cập. Với path chỉ có tên file, `getParent()` có thể trả `null`; khi đó phải xác định thư mục đích một cách chủ động.

Nếu cần tạo cấu trúc thư mục đích, `Files.createDirectories(parent)` là một thao tác I/O riêng có thể thất bại; không dùng nó trên input không tin cậy mà thiếu kiểm tra root/authorization.

### 3.2. Đo nơi ghi thực, không đo nơi bắt đầu

Một hệ thống có thể chạy từ ổ A nhưng ghi ra ổ B hoặc network share. Ví dụ:

```java
FileStore sourceStore = Files.getFileStore(sourceFile);
FileStore destinationStore = Files.getFileStore(destinationDirectory);
```

Khi quyết định liệu bản sao có đủ chỗ, xem `destinationStore.getUsableSpace()`. Dung lượng ở source không cho biết nơi nhận có đủ chỗ.

Một pipeline upload cũng có thể có **hai vị trí ghi**:

```text
HTTP stream
   |
   v
Staging temp trên volume A
   |
   v
Bản kết quả trên volume B
```

Khi đó cả hai volumes đều có thể cần kiểm tra và xử lý lỗi riêng. `Files.createTempFile(...)` không có tham số directory tạo trong vùng tạm mặc định; vùng này có thể **khác file store đích**. Nếu staging cần ở gần đích, dùng `Files.createTempFile(destinationDirectory, prefix, suffix)`.

### 3.3. Mount points và symbolic link

Trong hệ thống có mount riêng dưới một thư mục, chỉ vì hai path có prefix chuỗi giống nhau không có nghĩa chúng nằm cùng volume. Symbolic link cũng có thể dẫn tới filesystem khác.

`Files.getFileStore` định vị theo provider và đường dẫn thực tế; nếu ứng dụng thay đổi mount, đổi tệp hoặc di chuyển path, thông tin đã giữ trước đó có thể không còn phù hợp. Theo tài liệu, hành vi của `FileStore` được giữ sau khi path liên quan bị xóa/chuyển sang store khác là **phụ thuộc implementation**.

Đừng cache con số `usable` từ lúc khởi động dịch vụ để ra quyết định nhiều giờ sau.

## 4. Tính dung lượng dự phòng mà không overflow

Một thao tác ghi thường cần nhiều hơn số byte payload: có thể có metadata, block allocation, staging, tệp tạm hay cấu trúc chỉ mục. Ứng dụng có thể đặt `reserveBytes` theo policy để tránh sử dụng hết phần chỗ trống.

Ví dụ chính sách giả lập:

```text
usable  = 1,000 byte
payload =   800 byte
reserve =   100 byte
=> Có thể đi tiếp theo hint: 800 + 100 <= 1000

usable  = 1,000 byte
payload =   950 byte
reserve =   100 byte
=> Cảnh báo hoặc từ chối sớm: vượt phần dự phòng
```

Dùng `long` thay vì `int`. Đừng kiểm tra bằng:

```java
return usable >= payload + reserve;
```

vì `payload + reserve` có thể **tràn số nguyên `long`**, dẫn tới kết quả sai.

Phiên bản không dùng phép cộng có nguy cơ tràn:

```java
static boolean hasHeadroom(
        long usable, long payload, long reserve) {
    return usable >= 0
            && payload >= 0
            && reserve >= 0
            && reserve <= usable
            && payload <= usable - reserve;
}
```

Điều kiện bảo vệ:

1. Ba tham số không âm.
2. `reserve` không lớn hơn `usable` trước phép trừ.
3. `payload` không lớn hơn phần còn lại.

Phương thức này chỉ trả **quyết định theo công thức dung lượng**. Không đặt chỗ thực, không chứng minh quyền ghi và không xét toàn bộ overhead. Có thể dùng tên `probablyEnoughSpace` hay `hasHeadroom` thay vì `willWriteSuccessfully`.

### 4.1. Biên số học

| `usable` | `payload` | `reserve` | Kết quả |
| ---: | ---: | ---: | --- |
| 1.000 | 800 | 100 | `true` |
| 1.000 | 950 | 100 | `false` |
| 1.000 | 900 | 100 | `true` |
| 1.000 | 901 | 100 | `false` |
| 0 | 0 | 0 | `true` — chỉ về số học, không bảo đảm ghi |
| 0 | 1 | 0 | `false` |
| 1.000 | -1 | 0 | `false` |
| `Long.MAX_VALUE` | `Long.MAX_VALUE` | 1 | `false`, không tràn |

Nếu payload gồm nhiều file, cộng các `Files.size` bằng `Math.addExact` hoặc xử lý tổng có kiểm soát overflow. Không ép size xuống `int` trước khi cộng.

### 4.2. Không biết trước độ lớn của file

HTTP upload hoặc giải nén có thể không biết chính xác tổng byte sẽ ghi. Không coi `payload=0` là một “bằng chứng đủ chỗ”. Cần giới hạn byte **trong khi đọc/ghi**, áp quota và dọn staging nếu vượt ngưỡng.

Với file nén, kích thước archive **không phải** dung lượng giải nén; ứng dụng phải giới hạn cả tổng byte được giải nén và số entry theo chính sách an toàn.

## 5. `isReadOnly` và `Files.isWritable`: bổ sung, không thay thế phép ghi

```java
boolean readOnly = store.isReadOnly();
boolean writableDirectory =
        Files.isWritable(destinationDirectory);
```

- `isReadOnly() == true` nói file store không hỗ trợ thao tác ghi/thay đổi file. Đó là dấu hiệu mạnh để dừng trước khi ghi.
- `isReadOnly() == false` **không** nói mọi directory trên volume có thể ghi.
- `Files.isWritable(directory)` kiểm tra khả năng truy cập tại thời điểm gọi theo khả năng provider; quyền và filesystem có thể đổi ngay sau đó.
- Cả hai không bảo đảm quota còn đủ.

Một kiểm tra chặn sớm:

```java
if (store.isReadOnly()
        || !Files.isWritable(destinationDirectory)) {
    throw new IOException("Destination is not writable");
}
```

Đây là **minh họa** trong phương thức có import `IOException` và các biến có sẵn. Sau đó vẫn phải xử lý lỗi khi thật sự `Files.newOutputStream`, `Files.copy`, `Files.move` hoặc `Files.write`.

**Không dùng `Files.isWritable` làm một cơ chế authorization hoàn chỉnh.** Với đường dẫn không tin cậy, ứng dụng còn phải xét root, symlink, path traversal và quyền của người dùng theo hệ thống.

## 6. `FileStore` còn cho biết gì ngoài dung lượng?

### 6.1. `name()`, `type()`

```java
String name = store.name();
String type = store.type();
```

Hai chuỗi này có định dạng **phụ thuộc filesystem provider** và hệ điều hành. Chúng thích hợp cho chẩn đoán, không phải cơ sở quyết định dung lượng. Không giả định mọi volume Windows sẽ cho cùng `type()` hay `name()` tương ứng drive letter theo một khuôn duy nhất.

### 6.2. `supportsFileAttributeView(...)`

```java
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;

boolean basic = store.supportsFileAttributeView(
        BasicFileAttributeView.class);
boolean posix = store.supportsFileAttributeView(
        PosixFileAttributeView.class);
```

Theo Java API, `BasicFileAttributeView` luôn được hỗ trợ khi gọi method này. `PosixFileAttributeView`, `DosFileAttributeView`, `AclFileAttributeView` và các view khác có thể có hoặc không tùy provider. Hỗ trợ view không có nghĩa caller có quyền sửa mọi thuộc tính.

Đối với network file store, provider mặc định cũng có thể không bảo đảm kiểm tra attribute view chính xác trong mọi trường hợp (theo lưu ý của API). Đây là **kiểm tra tính năng**, không phải kiểm tra chỗ trống.

### 6.3. `getBlockSize()`

`getBlockSize()` có từ Java 10. Nó trả byte trên mỗi block nếu provider hỗ trợ, nhưng có thể ném `UnsupportedOperationException` hoặc `IOException`.

```java
try {
    long blockSize = store.getBlockSize();
    System.out.println(blockSize);
} catch (UnsupportedOperationException notAvailable) {
    // Không có số block-size từ provider này.
}
```

Đoạn này cần được đặt trong phương thức xử lý `IOException`. Không bắt buộc phải dùng `getBlockSize` để làm bài toán preflight cơ bản. Có block size cũng không cho ứng dụng quyền **reserve** các block.

### 6.4. `getAttribute(String)`

`FileStore.getAttribute` hỗ trợ một số metadata đặc thù dạng `view-name:attribute-name` nếu provider có. Không có một danh sách tên attribute mở rộng chung cho mọi file store. Với attribute đặc thù, kiểm tra hỗ trợ và xử lý `UnsupportedOperationException`/`IOException` thay vì giả định giống nhau giữa ZFS, NTFS, ZIP hoặc storage mạng.

### 6.5. `getFileStores()` khác `getFileStore(path)`

```java
for (FileStore s : FileSystems.getDefault().getFileStores()) {
    System.out.println(s.name() + " " + s.type());
}
```

Đây là **minh họa** cần import `java.nio.file.FileSystems` và `FileStore`. Method này liệt kê các stores mà filesystem mặc định công bố, không phải “trả store của đường dẫn đích trước tiên”.

Không dùng `getFileStores().iterator().next()` để quyết định nơi ghi; ứng dụng cần **`Files.getFileStore(destinationDirectory)`**. Số lượng và thứ tự các stores không được giả định giống nhau giữa môi trường.

## 7. Quy đổi byte, MiB, GiB và tỷ lệ phần trăm

`FileStore` trả byte. Phải phân biệt:

- `1 MB = 1.000.000 byte` và `1 GB = 1.000.000.000 byte` (hệ thập phân).
- `1 MiB = 1.048.576 byte` và `1 GiB = 1.073.741.824 byte` (hệ nhị phân).

Nếu muốn hiển thị số GiB:

```java
double gib = usableBytes / (1024.0 * 1024 * 1024);
System.out.printf(
        java.util.Locale.ROOT, "%.2f GiB%n", gib);
```

Đây là đoạn minh họa, `usableBytes` đã được khai báo. Dùng `Locale.ROOT` giúp định dạng số không vô tình thay đổi theo locale khi ghi log có format cố định.

**Tính toán chính sách nên giữ byte `long` gốc**, không so sánh số GiB làm tròn. Nếu cần phần trăm sử dụng:

```java
if (totalBytes > 0) {
    double usedPct =
            100.0 * (totalBytes - unallocatedBytes) / totalBytes;
    System.out.printf(
            java.util.Locale.ROOT, "%.1f%%%n", usedPct);
}
```

Chỉ là một phép đo mô tả theo chỉ số provider báo; không coi nó là phép đo dung lượng vật lý chính xác của sparse file, snapshot hay hệ storage có deduplication. Đừng chia khi `totalBytes == 0`.

## 8. Ví dụ Java 17+ chạy độc lập

Ví dụ sau dùng **một workspace tạm riêng**. Chương trình tạo file nguồn 7 byte, đo `FileStore` ở **thư mục đích**, kiểm tra các trường hợp số học bằng dữ liệu giả lập rồi thực sự copy và kiểm tra nội dung. Cuối cùng nó xóa đúng workspace đã tạo; không xóa thư mục của người dùng.

Để stdout dễ kiểm tra giữa nhiều máy, ví dụ không in số GB thật. Có một dòng dựa trên chỉ số dung lượng thực `live.hasRoomForSeven`; giá trị dòng này có thể thay đổi theo máy hoặc thời điểm.

Tạo tệp **`FileStoreCapacityDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributeView;
import java.util.Arrays;

public final class FileStoreCapacityDemo {
    static boolean hasHeadroom(long usable, long payload, long reserve) {
        return usable >= 0
                && payload >= 0
                && reserve >= 0
                && reserve <= usable
                && payload <= usable - reserve;
    }

    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, java.nio.file.attribute.BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException cause) throws IOException {
                if (cause != null) throw cause;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path work = Files.createTempDirectory("file-store-lesson-");
        try {
            Path sourceDir = Files.createDirectory(
                    work.resolve("source"));
            Path destinationDir = Files.createDirectory(
                    work.resolve("destination"));
            Path source = sourceDir.resolve("payload.bin");

            byte[] payload =
                    "storage".getBytes(StandardCharsets.UTF_8);
            Files.write(source, payload);

            FileStore store = Files.getFileStore(destinationDir);
            long total = store.getTotalSpace();
            long unallocated = store.getUnallocatedSpace();
            long usable = store.getUsableSpace();

            boolean nonNegative =
                    total >= 0 && unallocated >= 0 && usable >= 0;
            boolean basic = store.supportsFileAttributeView(
                    BasicFileAttributeView.class);

            System.out.println(
                    "store.metricsNonNegative=" + nonNegative);
            System.out.println("store.basicView=" + basic);
            System.out.println("source.bytes=" + Files.size(source));
            System.out.println(
                    "policy.allow=" + hasHeadroom(1_000, 800, 100));
            System.out.println(
                    "policy.rejectReserve=" +
                    !hasHeadroom(1_000, 950, 100));
            System.out.println(
                    "policy.rejectOverflow=" +
                    !hasHeadroom(Long.MAX_VALUE, Long.MAX_VALUE, 1));
            System.out.println(
                    "policy.rejectNegative=" +
                    !hasHeadroom(1_000, -1, 0));
            System.out.println(
                    "live.hasRoomForSeven=" + hasHeadroom(usable, 7, 0));

            Path copy = destinationDir.resolve("payload.bin");
            Files.copy(source, copy);

            boolean copied = Arrays.equals(
                    payload, Files.readAllBytes(copy));
            System.out.println("copy.bytesEqual=" + copied);

            check(nonNegative && basic && Files.size(source) == 7
                    && hasHeadroom(1_000, 800, 100)
                    && !hasHeadroom(1_000, 950, 100)
                    && !hasHeadroom(Long.MAX_VALUE, Long.MAX_VALUE, 1)
                    && !hasHeadroom(1_000, -1, 0)
                    && copied, "file-store checks");
            System.out.println("checks=PASS");
        } finally {
            deleteTree(work);
        }
        System.out.println(
                "workspace.cleaned=" + !Files.exists(work));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 FileStoreCapacityDemo.java
java FileStoreCapacityDemo
```

**Đầu ra thực tế đã được kiểm thử bằng `javac` và `java` (exit code 0):**

```text
store.metricsNonNegative=true
store.basicView=true
source.bytes=7
policy.allow=true
policy.rejectReserve=true
policy.rejectOverflow=true
policy.rejectNegative=true
live.hasRoomForSeven=true
copy.bytesEqual=true
checks=PASS
workspace.cleaned=true
```

#### Giải thích từng kết quả

- `store.metricsNonNegative=true`: các con số dung lượng trả về không âm ở lần chạy thử.
- `store.basicView=true`: attribute view cơ bản được công bố hỗ trợ.
- `source.bytes=7`: file `payload.bin` chứa đúng 7 byte của chuỗi ASCII `storage` được mã hóa UTF-8.
- `policy.allow=true`: yêu cầu 800 byte với dự phòng 100 byte được phép khi usable giả lập là 1.000.
- `policy.rejectReserve=true`: payload 950 + dự phòng 100 lớn hơn usable 1.000.
- `policy.rejectOverflow=true`: nhánh `Long.MAX_VALUE` bị từ chối đúng, không cộng tràn.
- `policy.rejectNegative=true`: không chấp nhận payload âm.
- `live.hasRoomForSeven=true`: **chỉ là kết quả của máy thử**, có thể là `false` ở môi trường khác; chương trình **không assert dòng này phải true**.
- `copy.bytesEqual=true`: bản copy chứa bytes đúng trong bài thử.
- `checks=PASS` và `workspace.cleaned=true`: phép kiểm tra logic thành công và workspace đã được dọn.

**Điều ví dụ không hứa:** Không xác minh ACL/owner/permission của bản copy, không mô phỏng cạn đĩa thật, không bảo đảm `getUsableSpace` dự đoán chính xác lần ghi lớn hơn, và không chứng minh mọi filesystem provider hỗ trợ cùng khả năng.

## 9. Thiết kế preflight trước upload hoặc copy trong sản phẩm thật

Một trình tự hợp lý:

```text
Xác thực input và quyền ghi
       |
Chọn staging directory thuộc quyền ứng dụng
       |
Files.getFileStore(stagingDirectory)
       |
Đọc isReadOnly, getUsableSpace và áp reserve/quota
       |
Không đủ -> thông báo, từ chối sớm hoặc chọn nơi khác
Có vẻ đủ -> ghi thực tế có kiểm soát
       |
Đóng streams/channels và kiểm tra kết quả
       |
Đối chiếu bytes, kích thước, checksum theo yêu cầu
       |
Publish hoàn chỉnh; dọn staging bị lỗi
```

Một helper minh họa:

```java
static boolean probablyEnough(
        Path existingTargetDirectory,
        long expectedPayloadBytes,
        long reserveBytes) throws IOException {
    if (expectedPayloadBytes < 0 || reserveBytes < 0) {
        throw new IllegalArgumentException("Negative capacity");
    }

    FileStore store = Files.getFileStore(existingTargetDirectory);
    if (store.isReadOnly()) {
        return false;
    }

    return hasHeadroom(
            store.getUsableSpace(), expectedPayloadBytes, reserveBytes);
}
```

Đây là **phương thức minh họa trong lớp** có `hasHeadroom` và import `FileStore`, `Files`, `Path`, `IOException`. Nó không tạo path và không làm I/O để giữ chỗ; mọi kết quả `true` vẫn phải được theo sau bằng xử lý lỗi khi ghi thật.

### 9.1. Staging và tính nguyên tử

`Files.copy` không phải thao tác nguyên tử. Nếu copy bị ngắt, target có thể tồn tại nhưng thiếu nội dung. Một số hệ thống nên copy vào staging riêng, xác minh rồi mới publish.

`Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE)` chỉ khả thi nếu provider hỗ trợ và điều kiện filesystem cho phép; nó có thể ném `AtomicMoveNotSupportedException`. `ATOMIC_MOVE` không bảo đảm mọi hình thức durability/snapshot của dữ liệu và không làm `Files.copy` tự trở thành atomic.

### 9.2. Xử lý hết chỗ thực sự

Dù preflight thành công, write có thể ném `IOException` hoặc subclass tương ứng theo provider. Ứng dụng cần:

- Dừng thao tác ghi và không công bố file dở dang.
- Giữ exception gốc phục vụ chẩn đoán.
- Dọn **chỉ staging do chính job sở hữu**.
- Nếu cleanup lỗi, ghi nhận hoặc gắn suppressed exception phù hợp.
- Cập nhật metric/alert, không tiếp tục vô hạn.
- Không thử “giải phóng dung lượng” bằng cách tự xóa thư mục khác ngoài quyền sở hữu.

Không cố tạo file rất lớn chỉ để kiểm tra ổ đĩa có đủ chỗ: điều đó tiêu tốn I/O và có nguy cơ ảnh hưởng dữ liệu của người khác.

## 10. Quota, đồng thời và TOCTOU

**TOCTOU** (*time of check to time of use*) nghĩa là điều kiện thay đổi giữa lúc kiểm tra và lúc sử dụng. Ví dụ:

```text
T0: getUsableSpace() -> 100 MiB
T1: một process khác ghi 90 MiB
T2: ứng dụng muốn ghi 50 MiB
```

Dù T0 cho thấy đủ chỗ, ở T2 việc ghi có thể thất bại. Hai request cùng đọc số `usable` cũng có thể cùng vượt preflight và tranh một vùng trống.

Giải pháp ở cấp ứng dụng có thể là quota/reservation nội bộ giữa các job và limit byte trong quá trình ghi. Tuy nhiên, đó vẫn **không đặt trước dung lượng cho những tiến trình khác ngoài ứng dụng**. Nếu cần snapshot/transaction thật, phải có cơ chế đặc thù của storage.

Đối với multi-tenant service, `getUsableSpace()` không thay thế quota business theo user/organization. Quota business còn phải xét tác vụ đang chạy, dung lượng đã đặt trước và chính sách thu hồi.

## 11. Giới hạn cross-platform

### 11.1. Local disks và filesystem mạng

Network share có thể cung cấp thông số dung lượng từ server, có cache hoặc bị ngắt kết nối. Các giá trị có thể biến động và provider có thể báo lỗi. Không suy từ một test trên local disk ra bảo đảm cho mọi storage.

### 11.2. ZIP và filesystem ảo

Một ZIP filesystem có mô hình lưu trữ khác file system chứa chính archive bên ngoài. Không giả định mọi `FileStore` ảo đưa ra số byte phản ánh dung lượng vật lý còn trống của backing store.

### 11.3. Mount, quyền và symlink

Nếu directory có symlink, mount alias hoặc được thay đổi trong lúc thao tác, một phép `Path.normalize()` chỉ xử lý **cấu trúc tên**, không xác minh đường thực. Không dùng `Files.getFileStore` như authorization checker; phải bảo vệ input, quyền truy cập, root cho phép và rủi ro race.

### 11.4. Filesystem read-only và attr capability

Khi `isReadOnly()==true`, không nên cố ghi và suy rằng một kết quả `usable > 0` có nghĩa có thể ghi. Khi `supportsFileAttributeView("posix")==false`, không thể dùng POSIX attrs như thể được hỗ trợ. Hai nhóm thuộc tính này phải được hiểu độc lập với con số capacity.

## 12. Hiệu năng, quan sát và cảnh báo

`FileStore` hữu ích cho monitor và cảnh báo khi dung lượng còn thấp. Một số metric ứng dụng có thể xuất:

- `filestore_total_bytes`.
- `filestore_unallocated_bytes`.
- `filestore_usable_bytes`.
- `filestore_read_only`.
- `app_reserved_bytes` nếu ứng dụng có reservation logic riêng.
- `write_failed_total` và `staging_cleanup_failed_total`.

Đây là tên metric **do ứng dụng tự đặt**, không phải các metric JVM tự cấp. Khi thu thập, thêm timestamp/nhận diện volume và hạn chế tiết lộ đường dẫn nhạy cảm. Với network filesystem, truy vấn quá dày có thể tốn chi phí hoặc gặp lỗi.

Ngưỡng có thể dựa trên **GiB khả dụng**, **tỷ lệ sử dụng** hoặc tốc độ tiêu hao. Một volume rất lớn còn 10% khác một volume nhỏ còn 10%. Kết hợp cả ngưỡng tuyệt đối và phần trăm khi nghiệp vụ cần.

## 13. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Dùng `getTotalSpace` để xem còn chỗ không | Total không phải free | Tham khảo `getUsableSpace` |
| Dùng `getUnallocatedSpace` thay usable | Byte chưa cấp phát có thể không dùng được với JVM | Hiểu rõ quota/reserved |
| Lấy store của working directory | Target có thể nằm trên volume khác | `Files.getFileStore(targetParent)` |
| Lấy store của file mới chưa tồn tại | Có thể ném `IOException` | Đo thư mục đích hiện hữu |
| Cho rằng `usable>=size` bảo đảm thành công | TOCTOU, quota, I/O và permission | Luôn xử lý lỗi ghi thật |
| Dùng `payload+reserve` không guard | Có thể tràn `long` | So `payload <= usable-reserve` với kiểm tra |
| Dùng `int` cho byte dung lượng | Tràn khi volume lớn | Dùng `long` |
| Nhầm GB và GiB | Báo cáo lệch đơn vị | Ghi nhãn theo phép chia |
| Chỉ đo lúc khởi động | Snapshot nhanh chóng lỗi thời | Đo gần thao tác hơn |
| `isReadOnly()==false` nghĩa là mọi path writable | Quyền thư mục riêng | Kiểm tra thêm và thử I/O |
| Đo mỗi vị trí publish, bỏ staging | Staging có thể ở volume khác | Đo mọi nơi sẽ ghi thật |
| Chọn phần tử đầu của `getFileStores()` | Không gắn với đích | `Files.getFileStore(path)` |
| Tin vào quota của OS như quota tenant | Không quản lý use cases đồng thời | Quota ứng dụng riêng |
| Không xử lý file ghi dở | Rò dung lượng, file sai | Staging và cleanup |
| Test bằng cách làm đầy ổ đĩa chung | Có thể gây hại môi trường | Fake hoặc quota test sandbox |

## 14. Kiểm thử đúng cho bài toán này

### 14.1. Unit tests của `hasHeadroom`

Nên test các bộ (usable, payload, reserve) = (1000,800,100), (1000,950,100), (0,1,0), (0,0,0), giá trị âm và `Long.MAX_VALUE`. Đây là các test **quyết định số học**, có thể chạy trên mọi máy mà không cần tạo file thật.

### 14.2. Integration tests với FileStore thật

Nên kiểm tra:

- FileStore của một directory đã tồn tại truy vấn thành công.
- File đích chưa tồn tại có thể gây lỗi; logic dùng parent.
- Các chỉ số trả về có kiểu và điều kiện hợp lý theo API.
- Tệp nhỏ có thể được tạo/sao chép trong workspace tạm.
- Trường hợp read-only, quota thấp hoặc mất quyền bằng môi trường test được quản lý.
- Vị trí target khác working directory và staging khác target.
- Provider ảo/network nếu sản phẩm thực sự hỗ trợ chúng.
- Lỗi I/O trong lúc ghi vẫn được xử lý dù preflight báo “đủ”.

Không kiểm thử bằng cách so `getUsableSpace()==một_số_GiB_cố_định`, bởi dung lượng luôn thay đổi. Cũng không cần tự làm đầy ổ đĩa người dùng để mô phỏng lỗi; dùng test filesystem/quota biệt lập.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `FileStore` đại diện một tệp hay một vùng lưu trữ?  
**Đáp án:** Một vùng lưu trữ do provider xác định.

**Câu 2.** Ba phương thức dung lượng khác nhau thế nào?  
**Đáp án:** `getTotalSpace` là tổng; `getUnallocatedSpace` là byte chưa phân bổ; `getUsableSpace` là byte JVM được báo có thể dùng.

**Câu 3.** Có nên đo `getUsableSpace` trên ổ nguồn khi chuẩn bị copy sang ổ đích?  
**Đáp án:** Không. Phải đo nơi dữ liệu sẽ ghi, thường là directory đích.

**Câu 4.** Khi file đích chưa tồn tại, lấy FileStore ở đâu?  
**Đáp án:** Thư mục cha đích đã tồn tại, sau khi kiểm tra đường dẫn và quyền truy cập.

**Câu 5.** `getUsableSpace` trả đủ byte nghĩa là file chắc chắn được tạo không?  
**Đáp án:** Không. Đó chỉ là hint và không reserve dung lượng; mọi ghi vẫn phải xử lý `IOException`.

**Câu 6.** Vì sao check `payload+reserve` có thể sai?  
**Đáp án:** Tràn `long`; dùng phép trừ có guard hoặc tính toán overflow-safe.

**Câu 7.** `isReadOnly()==false` có chứng minh path writable không?  
**Đáp án:** Không. Quyền của thư mục/file và trạng thái I/O phải xét riêng.

**Câu 8.** Sao một chương trình chạy ở container lại báo dung lượng khác host?  
**Đáp án:** File stores, mount, quota và provider được nhìn thấy trong container có thể khác host; không tự suy từ host sang đường dẫn ứng dụng.

**Câu 9.** Kích thước archive nén có cho biết số byte cần giải nén không?  
**Đáp án:** Không. Cần limit/ước tính riêng cho nội dung sau giải nén.

**Câu 10.** Đo đủ dung lượng có thay thế bước cleanup staging không?  
**Đáp án:** Không. File copy có thể bị lỗi giữa chừng và để lại dữ liệu chưa hoàn chỉnh.

## 16. Checklist áp dụng vào dự án

- [ ] Đã xác định đúng **directory sẽ chứa dữ liệu** và directory này tồn tại.
- [ ] Dùng `Files.getFileStore(destinationDirectory)` thay vì chọn một store tùy ý.
- [ ] Đã phân biệt `total`, `unallocated`, `usable` và kích thước file.
- [ ] Dùng `usable` như hint, không phải bảo đảm.
- [ ] Đã xử lý `IOException` của truy vấn và thao tác ghi thực tế.
- [ ] Xác định quota, reserve và loại dữ liệu cần cấp phát.
- [ ] Tính bằng `long` byte, kiểm tra overflow/negative.
- [ ] Không dùng số đã làm tròn GiB để quyết định chính sách.
- [ ] Đã xét `isReadOnly`, permissions và mount/symlinks.
- [ ] Đã đo nơi staging nếu khác volume publish.
- [ ] Có giới hạn byte cho upload/giải nén không biết trước kích thước.
- [ ] Có chính sách nhiều request đồng thời và dữ liệu thay đổi.
- [ ] Có staging, xác minh, publish và cleanup khi copy lỗi.
- [ ] Đã kiểm thử bằng fake số học cùng integration test provider thật.
- [ ] Metric/alert có timestamp, phân biệt hint với write failures.

## 17. Kết luận và tài liệu chuẩn còn hiệu lực

**`FileStore` cho phép ứng dụng biết thông tin về vùng lưu trữ của một đường dẫn.** Trong đó, `getUsableSpace()` là chỉ số phù hợp nhất cho một **kiểm tra khả năng ghi sơ bộ**, còn `getTotalSpace()` và `getUnallocatedSpace()` phục vụ theo dõi capacity. Các số đo đều có thể thay đổi ngay sau khi đọc.

Thiết kế đúng cần đo trên **thư mục đích hiện có**, kiểm soát reserve/quota không tràn số và thực hiện I/O có xử lý lỗi. Không nên viết code phụ thuộc một con số free space duy nhất rồi coi đó là cam kết từ hệ điều hành.

Tài liệu Oracle JDK còn áp dụng:

- [Java SE 17 — `java.nio.file.FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `getTotalSpace`, `getUnallocatedSpace`, `getUsableSpace`, `isReadOnly`, `getBlockSize`, attribute views.
- [Java SE 17 — `Files.getFileStore(Path)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): xác định store của đường dẫn.
- [Java SE 17 — `java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `size`, `isWritable`, `copy`, `createTempDirectory` và thao tác I/O.
- [Java SE 17 — `FileSystem`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `getFileStores` và filesystem provider.
- [Java SE 17 — `BasicFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): thuộc tính tệp cơ bản.
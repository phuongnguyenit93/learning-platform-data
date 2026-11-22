# Phân biệt kích thước khối với kích thước tệp trong Java 10

## 1. Mục tiêu: hai đại lượng khác phạm vi, khác ý nghĩa

Khi truy vấn thông tin lưu trữ bằng Java NIO.2, hai con số dễ bị nhầm là:

- **Kích thước khối của FileStore** (*file-store block size*): số **byte trên một khối**, lấy bằng `FileStore.getBlockSize()`. Đây là **thuộc tính của hệ thống lưu trữ** chứa tệp, không phải số byte nội dung của một tệp. Phương thức này được bổ sung từ **Java 10** và tiếp tục tồn tại trong Java hiện đại.
- **Kích thước tệp** (*file size*): số **byte của tệp** theo metadata, thường lấy bằng `Files.size(path)` hoặc `BasicFileAttributes.size()`. Đối với tệp thông thường, đây là **kích thước logic**, có thể khác dung lượng lưu trữ thực tế được phân bổ.

Ví dụ, một tệp dài **5.001 byte** có thể nằm trên FileStore có kích thước khối **4.096 byte**. Hai số này không mâu thuẫn:

- `5_001` là kích thước logic của **tệp cụ thể**.
- `4_096` là kích thước của **một khối lưu trữ** trong ví dụ giả định.
- `8_192` là kết quả của phép **làm tròn lý thuyết** 5.001 byte lên bội số 4.096. **Không được tự nhận** đây là số byte đĩa thực sự đã được cấp cho tệp nếu chưa có thông tin phân bổ thực tế.

Điểm cuối cùng đặc biệt quan trọng với **sparse file**, nén, deduplication, clone/reflink, hệ thống tệp mạng và metadata. `FileStore.getBlockSize()` **không** phải API đo chính xác dung lượng từng tệp chiếm trên thiết bị.

### Sau bài học, bạn có thể

1. Phân biệt byte/khối với byte/tệp và với dung lượng toàn FileStore.
2. Dùng `Files.getFileStore(path)` kết hợp `FileStore.getBlockSize()` từ Java 10.
3. Dùng `Files.size(path)`, `BasicFileAttributes.size()` và hiểu giới hạn của chúng.
4. Giải thích phép làm tròn theo khối: khi nào có ý nghĩa minh họa và vì sao **không bảo đảm** dung lượng phân bổ thật.
5. Nhận biết `IOException` và `UnsupportedOperationException` khi truy vấn FileStore.
6. Không nhầm block size với sector size, page size, buffer size, file length, total capacity hoặc free space.
7. Chạy được ví dụ Java 17+ có stdout ổn định trên các hệ thống có FileStore provider phù hợp.
8. Chọn đúng thông số khi hiển thị kích thước tệp, tính tải lên, lập quota, ước tính dung lượng và theo dõi ổ đĩa.

**Giới hạn phạm vi:** Nội dung chỉ dùng các API và nguyên tắc còn áp dụng trong Java hiện nay; không dựa vào giả định một hệ điều hành, ổ đĩa hoặc file system duy nhất.

## 2. Khái niệm nền: File, FileStore và block

### 2.1. `Path` biểu diễn vị trí tệp

Trong `java.nio.file`, một `Path` xác định đường dẫn đến tệp hoặc thư mục theo một file-system provider:

~~~java
import java.nio.file.Path;

Path path = Path.of("data", "report.bin");
~~~

`Path` là **đối tượng đại diện đường dẫn**, không có thuộc tính block size cố định chỉ từ chuỗi tên tệp. Để lấy thông tin lưu trữ, cần truy vấn provider và FileStore đang chứa đối tượng đó.

### 2.2. `FileStore` đại diện kho lưu trữ

`FileStore` trong `java.nio.file` biểu diễn nơi file system lưu các file và cung cấp các thông tin như:

- Tên và loại FileStore: `name()`, `type()`.
- Sức chứa FileStore: `getTotalSpace()`.
- Không gian chưa phân bổ: `getUnallocatedSpace()`.
- Không gian có thể sử dụng đối với JVM: `getUsableSpace()`.
- Kích thước khối: `getBlockSize()` (**từ Java 10**).
- Trạng thái chỉ đọc, các file attribute view được hỗ trợ.

Một FileStore có thể chứa rất nhiều tệp, mỗi tệp có **kích thước khác nhau**, trong khi truy vấn `getBlockSize()` trả một thông tin của **FileStore đó**.

### 2.3. Block là gì?

Lưu trữ thường được tổ chức theo các **đơn vị khối** (*blocks*). JavaDoc của `FileStore.getBlockSize()` mô tả một khối là đơn vị lưu trữ nhỏ nhất của file store và các thao tác đọc/ghi bên dưới thường diễn ra theo các bội số khối.

Tuy nhiên, cần phân biệt tầng **thiết bị/file-system** với API **đọc/ghi byte của Java**:

- `OutputStream.write(byte[])` có thể được gọi với mảng dài một byte, 100 byte hoặc 5.001 byte.
- `Files.write(path, byte[])` có thể tạo tệp với kích thước logic không phải bội số của block size.
- File system và bộ đệm có trách nhiệm tổ chức thao tác I/O bên dưới. Người gọi **không phải** tự làm tròn độ dài mảng byte rồi ghi thêm byte chỉ vì block size là 4 KiB.

**Sai lầm nguy hiểm:** ghi thêm byte padding vào file để độ dài trở thành bội số của block size có thể làm **thay đổi định dạng và nội dung file**. Với hầu hết định dạng dữ liệu thông thường, không được tự làm vậy.

## 3. `FileStore.getBlockSize()` — API trọng tâm của Java 10

Chữ ký:

~~~java
public long getBlockSize() throws IOException
~~~

Phương thức thuộc lớp:

~~~java
java.nio.file.FileStore
~~~

Theo JavaDoc hiện hành:

| Thuộc tính | Hợp đồng |
| --- | --- |
| **Since** | **10** |
| Giá trị trả về | Một `long` **dương**, là số byte trên mỗi block của FileStore. |
| `IOException` | Có thể xảy ra khi truy vấn thông tin lưu trữ gặp lỗi I/O. |
| `UnsupportedOperationException` | Có thể xảy ra khi operation/provider không hỗ trợ truy vấn. |
| Implementation Requirements | Cài đặt mặc định của phương thức trong lớp `FileStore` ném `UnsupportedOperationException`; provider hỗ trợ cần triển khai hành vi thích hợp. |

**Không giả định** mọi provider hoặc mọi loại FileStore luôn hỗ trợ `getBlockSize()`. Ví dụ một provider ảo, lưu trữ mạng hoặc triển khai tùy chỉnh có thể không cung cấp thông tin đó.

### 3.1. Truy vấn FileStore từ một tệp cụ thể

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

static void inspectBlockSize(Path file) throws IOException {
    FileStore store = Files.getFileStore(file);

    try {
        long bytesPerBlock = store.getBlockSize();
        System.out.println("Bytes per block: " + bytesPerBlock);
    } catch (UnsupportedOperationException ex) {
        System.out.println("Block size is not supported by this provider");
    }
}
~~~

Đoạn trên là **một phương thức riêng** đặt trong class phù hợp. Nó không có stdout cố định vì kích thước khối phụ thuộc FileStore thực tế.

Điều cần hiểu:

1. `Files.getFileStore(file)` tìm **FileStore chứa đối tượng tại đường dẫn**.
2. `store.getBlockSize()` truy vấn thuộc tính **của kho lưu trữ**, không phải kích thước của `file`.
3. Nếu trả về giá trị hợp lệ, giá trị đó **lớn hơn 0**.
4. Nếu không được hỗ trợ, xử lý `UnsupportedOperationException` và dùng một chiến lược khác theo yêu cầu nghiệp vụ.
5. `IOException` vẫn có thể xảy ra ở `Files.getFileStore` hoặc `getBlockSize` và cần được bắt/khai báo.

Không lấy `FileStore.getBlockSize` bằng cách suy luận từ ký tự ổ đĩa hoặc từ một hằng số 4096. Phải hỏi đúng provider khi tính năng thực sự cần thông tin block.

### 3.2. Vì sao không có “block size của từng file” trong phép gọi này?

Về phương diện chữ ký, `getBlockSize()` là **phương thức của `FileStore`**, không nhận tham số `Path`. Nó không thể mô tả “tệp A dài bao nhiêu byte” hoặc “tệp B đã chiếm đúng bao nhiêu byte vật lý”.

Hai tệp khác kích thước nằm trên **cùng FileStore** có thể có cùng giá trị `store.getBlockSize()`, nhưng điều đó **không suy ra** dung lượng thực tế của hai tệp là bằng nhau, hay đúng bằng mỗi kích thước logic được làm tròn.

### 3.3. Không trộn lẫn block size với các đơn vị khác

| Thuật ngữ | Cấp áp dụng | Ghi chú |
| --- | --- | --- |
| **FileStore block size** | FileStore/file-system provider | `FileStore.getBlockSize()`, byte/block; Java 10+. |
| **Logical file size** | Tệp cụ thể | `Files.size(path)`, byte/tệp. |
| **Device sector size** | Tầng thiết bị lưu trữ | Không có hợp đồng rằng bằng `FileStore.getBlockSize()`. |
| **Memory page size** | Bộ nhớ ảo của hệ điều hành | Không phải thông số mà `FileStore.getBlockSize()` trả về. |
| **Java I/O buffer size** | Buffer mà ứng dụng sử dụng | Có thể chọn dựa trên workload; không nhất thiết bằng block size. |
| **FileStore total capacity** | Toàn FileStore | `getTotalSpace()`, byte toàn kho. |
| **Available/usable space** | Toàn FileStore đối với hệ thống/JVM | `getUnallocatedSpace()`, `getUsableSpace()`; không phải kích thước của một file. |

Ví dụ Java sử dụng `byte[] buffer = new byte[8192]` không có nghĩa block size của FileStore là 8192 byte. Một buffer là **lựa chọn của phần mềm**, một block size là **thuộc tính của kho lưu trữ**.

## 4. `Files.size(path)` — kích thước logic của tệp

Chữ ký:

~~~java
public static long size(Path path) throws IOException
~~~

`Files.size(path)` trả về số byte của tệp. Với **regular file**, đây là cách phổ biến để lấy kích thước logic. Nó **khác** số byte lưu trữ thực tế được sử dụng trên file system vì có thể chịu tác động của:

- File **sparse** với các vùng trống không có dữ liệu vật lý tương ứng.
- **Nén** ở tầng file system.
- Những cách chia sẻ/deduplication lưu trữ giữa nhiều file.
- Các lý do phụ thuộc file system/provider khác.

Với file **không phải regular file**, JavaDoc không quy định một nghĩa phổ quát cho kết quả `Files.size`: giá trị là **implementation specific**. Không dùng `Files.size(directory)` làm tổng dung lượng mọi file trong thư mục.

Ví dụ:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("report.bin");
long fileBytes = Files.size(path);

System.out.println("Logical file length: " + fileBytes);
~~~

Đây là đoạn mã minh họa: tệp `report.bin` phải tồn tại và caller cần xử lý `IOException`. Lời gọi **không cung cấp** số khối đã được phân bổ trên đĩa.

### 4.1. `BasicFileAttributes.size()` cũng là kích thước tệp

~~~java
import java.nio.file.Files;
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

long fileBytes = attrs.size();
~~~

`BasicFileAttributes` còn cho biết regular file, directory, symbolic link, thời gian sửa đổi, v.v. Giá trị `size()` là số byte kích thước tệp theo hợp đồng metadata tương ứng.

Với một **regular file ổn định**, `Files.size(path)` và `attrs.size()` thông thường cho cùng giá trị logic. Tuy nhiên, nếu file bị thay đổi **giữa hai lần đọc metadata**, không được mặc định hai giá trị vẫn khớp: đây không phải một snapshot nguyên tử toàn hệ thống.

### 4.2. Không suy ra kích thước từ nội dung `String`

Nếu một tệp được lưu bằng UTF-8:

~~~java
String text = "Aé";
System.out.println(text.length()); // 2

byte[] encoded = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
System.out.println(encoded.length); // 3
~~~

`String.length()` đo **số đơn vị mã UTF-16**, không phải kích thước byte của văn bản đã mã hóa. `é` (U+00E9) dùng **hai byte UTF-8** và một đơn vị mã UTF-16, nên `"Aé"` có:

- `String.length() == 2`.
- `getBytes(UTF_8).length == 3`.
- Khi ghi toàn bộ thành file UTF-8 không có byte bổ sung, `Files.size(path) == 3`.

Với emoji hoặc ký tự Unicode ở ngoài BMP, khác biệt giữa byte UTF-8, UTF-16 code unit và Unicode code point có thể còn lớn hơn. **Chỉ `Files.size` đo kích thước logic của file trên hệ thống tệp**, không phải `String.length`.

## 5. Làm tròn số byte theo kích thước khối: một mô hình, không phải phép đo đĩa

Giả sử một hệ thống lưu trữ đơn giản sử dụng **block 4 KiB = 4096 byte** và **mỗi file được cấp phát đầy đủ các khối**. Khi đó, để tính số byte tròn khối tối thiểu theo mô hình:

~~~text
blocks = ceil(logicalFileBytes / blockBytes)
roundedBytes = blocks * blockBytes
~~~

Với số nguyên dương và block size dương:

~~~text
blocks = logicalFileBytes / blockBytes + (logicalFileBytes % blockBytes == 0 ? 0 : 1)
~~~

Bảng minh họa:

| Kích thước logic tệp | Khối giả định | Số khối theo mô hình | Byte làm tròn theo mô hình |
| ---: | ---: | ---: | ---: |
| 0 B | 4096 B | 0 | 0 B |
| 1 B | 4096 B | 1 | 4096 B |
| 4095 B | 4096 B | 1 | 4096 B |
| 4096 B | 4096 B | 1 | 4096 B |
| 4097 B | 4096 B | 2 | 8192 B |
| 5001 B | 4096 B | 2 | 8192 B |
| 8192 B | 4096 B | 2 | 8192 B |
| 8193 B | 4096 B | 3 | 12288 B |

**Tất cả các giá trị “byte làm tròn” ở bảng này là giá trị lý thuyết cho giả định đã nêu, không phải kết quả đo thực tế `allocatedBytes` của file.**

### 5.1. Vì sao ví dụ 5001 → 8192 không được xem là kết quả thực tế?

Vì phép làm tròn chỉ áp dụng cho **một mô hình cấp phát đơn giản**. File system thực tế có thể:

- Không cấp phát khối cho một số vùng logic chưa có dữ liệu (**sparse file**).
- Nén dữ liệu nên số byte lưu trữ ít hơn kích thước logic.
- Dùng metadata và cấu trúc lưu trữ bổ sung.
- Chia sẻ cùng extent vật lý giữa nhiều file.
- Có cấu trúc quản lý, preallocation, snapshot và chính sách cấp phát khác.
- Thực hiện ghi xuống thiết bị theo tối ưu hóa riêng.

Vì thế, **`ceil(Files.size(path) / store.getBlockSize()) * store.getBlockSize()` không phải một API chuẩn để lấy dung lượng đã cấp phát của file**.

### 5.2. Tại sao tệp rỗng có thể vẫn tiêu tốn tài nguyên?

Theo mô hình dữ liệu đơn giản, file rỗng chứa **0 byte nội dung**, nên số block nội dung cần là 0. Nhưng hệ thống tệp vẫn phải giữ thông tin tên file, metadata hoặc các cấu trúc khác. Vì vậy **kích thước logic 0** không chứng minh **chi phí lưu trữ tổng thể đúng 0**.

Không cộng metadata một cách tùy tiện vào `Files.size`, vì giá trị trả về có hợp đồng khác.

### 5.3. Tránh lỗi tràn số khi tự tính tròn khối

Cách viết ngắn:

~~~java
// KHÔNG an toàn nếu value gần Long.MAX_VALUE:
// long rounded = ((size + block - 1) / block) * block;
~~~

Biểu thức `size + block - 1` và phép nhân cuối có thể **tràn kiểu `long`**. Nếu thật sự cần một hàm tính **giả định** cho số byte tròn khối, dùng phép chia/dư và các phép kiểm tra tràn:

~~~java
static long hypotheticalWholeBlocks(long logicalBytes, long blockBytes) {
    if (logicalBytes < 0 || blockBytes <= 0) {
        throw new IllegalArgumentException("Invalid sizes");
    }

    long blocks = logicalBytes / blockBytes;
    if (logicalBytes % blockBytes != 0) {
        blocks = Math.addExact(blocks, 1);
    }
    return Math.multiplyExact(blocks, blockBytes);
}
~~~

Hàm trên **không truy cập file system**. Nó chỉ tính kết quả lý thuyết từ hai tham số đầu vào, và `Math.multiplyExact` có thể ném `ArithmeticException` khi kết quả vượt phạm vi `long`.

**Không** dùng hàm như một phép đo dung lượng vật lý. Nó chỉ hữu ích cho mô phỏng, minh họa block rounding hoặc một giao thức tự định nghĩa rõ cách padding.

## 6. Những tình huống kích thước logic khác dung lượng lưu trữ thực tế

### 6.1. Sparse file

Một sparse file có thể có **logical length rất lớn**, nhưng một số vùng logic chưa được cấp phát đầy đủ ở thiết bị lưu trữ. Hệ thống tệp có thể biểu diễn các “lỗ trống” như byte 0 khi đọc mà không lưu từng byte 0 ấy trên ổ đĩa.

Vì vậy:

~~~text
Files.size(sparseFile) = logical length lớn
Allocated physical bytes = có thể nhỏ hơn nhiều
~~~

Không tự suy luận rằng một file 100 GiB logic phải đã sử dụng 100 GiB vật lý. Tuy nhiên, **không phải mọi provider/hệ thống tệp đều hỗ trợ sparse file giống nhau**, và hành vi cấp phát có thể thay đổi sau khi ghi dữ liệu.

### 6.2. Compression ở tầng file system

Một file chứa dữ liệu dễ nén có thể có độ dài logic 10 MiB nhưng cần ít không gian hơn sau khi được nén. `Files.size` vẫn diễn đạt **độ dài logic của file**, không phải kích thước dữ liệu đã nén trong bộ lưu trữ.

Không lấy `getBlockSize` rồi tính làm tròn để đo hiệu quả nén: đây là hai thuộc tính ở các tầng khác nhau.

### 6.3. Hard link và chia sẻ dữ liệu

Trên file system hỗ trợ hard link, hai tên đường dẫn khác nhau có thể trỏ đến **cùng file**. Nếu duyệt tất cả đường dẫn rồi cộng `Files.size`, bạn có thể **đếm hai lần cùng dữ liệu logic**. Ngay cả khi byte content được cấp phát theo khối thông thường, “dung lượng chiếm thêm khi tạo một hard link” không bằng toàn bộ kích thước file.

Tương tự, clone/reflink hoặc deduplication có thể làm nhiều file chia sẻ vùng dữ liệu vật lý. Tổng `Files.size` của các đường dẫn **không phải** số byte vật lý tăng lên tương ứng.

### 6.4. Preallocation, metadata và cơ chế quản lý

File system có thể dành trước dung lượng, duy trì metadata, sử dụng các extent hoặc cấu trúc allocation khác. Không phải mọi chi phí này đều được phản ánh trong `Files.size` của từng regular file.

Bởi vậy cần đặt câu hỏi chính xác:

- Muốn biết **độ dài nội dung logic** của file? Dùng `Files.size`.
- Muốn biết **đơn vị khối** của FileStore? Dùng `getBlockSize` khi được hỗ trợ.
- Muốn biết **tổng/khả dụng của FileStore**? Dùng các API getSpace tương ứng.
- Muốn biết **khối thực sự cấp phát cho từng file**? API Java chuẩn **không cung cấp một phép đo portable trực tiếp qua `FileStore.getBlockSize()`**. Có thể cần attribute đặc thù provider hoặc công cụ hệ điều hành, và phải hiểu semantic của chúng.

## 7. Bảng đối chiếu API Java thường bị nhầm

| API | Trả về | Phạm vi | Từ phiên bản | Có phải số byte đã cấp phát cho từng file? |
| --- | --- | --- | --- | --- |
| `Files.size(path)` | `long` số byte của file | Tệp cụ thể | Java 7 | **Không**, là kích thước file logic. |
| `BasicFileAttributes.size()` | `long` số byte của file | Metadata tệp | Java 7 | **Không**. |
| `Files.getFileStore(path)` | `FileStore` | FileStore chứa đường dẫn | Java 7 | Không; đây là đối tượng để truy vấn. |
| `FileStore.getBlockSize()` | `long` byte/block | FileStore | **Java 10** | **Không**, chỉ số byte trên một block. |
| `FileStore.getTotalSpace()` | `long` byte | Toàn FileStore | API hiện hành | **Không**, là sức chứa của kho. |
| `FileStore.getUnallocatedSpace()` | `long` byte | Toàn FileStore | API hiện hành | **Không**, là byte chưa được phân bổ. |
| `FileStore.getUsableSpace()` | `long` byte | FileStore, theo JVM | API hiện hành | **Không**, là byte JVM có thể sử dụng. |
| `FileStore.getAttribute(name)` | `Object` do provider định nghĩa | Thuộc tính FileStore | API hiện hành | Không phải API portable đo allocated size từng file. |

**Mẹo nhớ:** Có chữ **`FileStore`** thì thông tin có thể thuộc **kho chứa nhiều file**; có chữ **`Files.size(path)`** thì bạn đang hỏi **kích thước một đối tượng tệp tại đường dẫn**. Không hoán đổi hai phạm vi.

## 8. Tương quan với `getTotalSpace`, `getUnallocatedSpace`, `getUsableSpace`

Để lấy thông số sức chứa của FileStore:

~~~java
import java.nio.file.FileStore;
import java.nio.file.Files;

FileStore store = Files.getFileStore(path);

long total = store.getTotalSpace();
long unallocated = store.getUnallocatedSpace();
long usable = store.getUsableSpace();
~~~

Phân biệt:

- `getTotalSpace()`: quy mô tổng của FileStore.
- `getUnallocatedSpace()`: không gian chưa phân bổ được báo cáo.
- `getUsableSpace()`: không gian hiện được xem là sử dụng được đối với JVM/caller, có thể khác unallocated vì hạn ngạch, quyền hoặc giới hạn.
- `getBlockSize()`: số **byte trên mỗi block**, không phải số block trống hay tổng dung lượng.
- `Files.size(path)`: byte logic của **file cụ thể**, không phải dung lượng còn lại.

JavaDoc lưu ý các giá trị về không gian trống/khả dụng chỉ là **gợi ý tại thời điểm truy vấn**, không bảo đảm rằng sau đó ứng dụng có thể ghi được đúng từng byte. Các tiến trình khác, quota, chính sách file system và thao tác I/O tiếp theo có thể làm số liệu thay đổi.

### 8.1. Vì sao `total / blockSize` chưa phải số block cho phép ghi file?

Nếu cả hai số có ý nghĩa trong cùng một mô hình, thương `total / blockSize` có thể hữu ích để hiểu tương quan quy mô. Nhưng **không nên** coi đó là số block người dùng được quyền ghi:

- Một phần dung lượng có thể dùng cho metadata hoặc bị giữ lại.
- Quyền truy cập/quotas có thể giới hạn `usable`.
- File system có thể cung cấp tính năng phân bổ đặc biệt.
- `total`/`usable` là các con số thay đổi theo hệ thống và thời gian.

Tính toán quản lý dung lượng cần lấy đúng API theo mục đích, không chỉ ghép các phép chia mà không kiểm tra ngữ nghĩa.

### 8.2. Hai file cùng FileStore có thể khác kích thước

Ví dụ về mặt logic:

~~~text
FileStore block size = 4096 B (giả định)

file-a.bin: Files.size = 1 B
file-b.bin: Files.size = 5001 B
file-c.bin: Files.size = 2_000_000 B
~~~

Cả ba file có thể thuộc **cùng một FileStore** và cùng giá trị block size. Đó là chuyện bình thường; block size **không** giới hạn file chỉ được có kích thước là bội số 4096 byte.

## 9. Chương trình Java 17+ hoàn chỉnh, kết quả ổn định

Chương trình sau tạo **file tạm**, ghi đúng 5.001 byte, đọc kích thước logic, truy vấn FileStore qua API Java 10, rồi đổi nội dung file thành văn bản UTF-8 để minh họa khác biệt byte/`String.length`.

**Chú ý:** ví dụ không in **giá trị block size thực tế** vì nó phụ thuộc hệ điều hành, hệ thống tệp và provider. Chương trình kiểm tra hợp đồng nếu truy vấn được, hoặc xử lý trường hợp không hỗ trợ, nên phần stdout giữ được tính ổn định trong môi trường thông thường.

Tạo tệp **`BlockVsFileSizeDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class BlockVsFileSizeDemo {
    static long hypotheticalWholeBlocks(long logicalBytes, long blockBytes) {
        if (logicalBytes < 0 || blockBytes <= 0) {
            throw new IllegalArgumentException("Invalid sizes");
        }

        long blocks = logicalBytes / blockBytes;
        if (logicalBytes % blockBytes != 0) {
            blocks = Math.addExact(blocks, 1);
        }
        return Math.multiplyExact(blocks, blockBytes);
    }

    public static void main(String[] args) throws IOException {
        System.out.println("1-byte example=" +
                hypotheticalWholeBlocks(1, 4096));
        System.out.println("4096-byte example=" +
                hypotheticalWholeBlocks(4096, 4096));
        System.out.println("4097-byte example=" +
                hypotheticalWholeBlocks(4097, 4096));
        System.out.println("0-byte example=" +
                hypotheticalWholeBlocks(0, 4096));

        Path file = Files.createTempFile("java-block-size-", ".bin");
        try {
            Files.write(file, new byte[5001]);
            long logical = Files.size(file);
            BasicFileAttributes attrs =
                    Files.readAttributes(file, BasicFileAttributes.class);
            System.out.println("file logical bytes=" + logical);
            System.out.println("basic attribute agrees=" +
                    (attrs.size() == logical));

            FileStore store = Files.getFileStore(file);
            try {
                long blockBytes = store.getBlockSize();
                if (blockBytes <= 0) {
                    throw new AssertionError("Nonpositive block size");
                }
            } catch (UnsupportedOperationException expected) {
                // Provider này không hỗ trợ getBlockSize.
            }
            System.out.println("FileStore query handled");

            Files.writeString(file, "Aé", StandardCharsets.UTF_8);
            System.out.println("UTF-8 file bytes=" + Files.size(file));
            System.out.println("String.length=" + "Aé".length());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 BlockVsFileSizeDemo.java
java BlockVsFileSizeDemo
~~~

**Stdout đã được kiểm chứng bằng JDK 24 trên máy thử nghiệm:**

~~~text
1-byte example=4096
4096-byte example=4096
4097-byte example=8192
0-byte example=0
file logical bytes=5001
basic attribute agrees=true
FileStore query handled
UTF-8 file bytes=3
String.length=2
~~~

### 9.1. Phân tích kết quả

1. **`1-byte example=4096`:** theo mô hình khối giả định 4 KiB, một byte nằm trong một block.
2. **`4096-byte example=4096`:** đúng một block trong mô hình.
3. **`4097-byte example=8192`:** vượt ranh giới một block, lý thuyết cần hai block.
4. **`0-byte example=0`:** công thức chỉ đếm block cho **dữ liệu logic**; không tính metadata.
5. **`file logical bytes=5001`:** `Files.write(file, new byte[5001])` tạo file có đúng 5.001 byte nội dung.
6. **`basic attribute agrees=true`:** `BasicFileAttributes.size()` đồng ý với `Files.size()` trên cùng regular file ổn định.
7. **`FileStore query handled`:** chương trình đã truy vấn API Java 10. Nếu provider trả về block size, nó phải dương; nếu không hỗ trợ, `UnsupportedOperationException` được xử lý. `IOException` vẫn có thể được ném ra khỏi `main` nếu thực sự có sự cố truy vấn I/O.
8. **`UTF-8 file bytes=3`:** sau `Files.writeString`, file chứa UTF-8 của `"Aé"`, dài ba byte.
9. **`String.length=2`:** chuỗi có hai đơn vị mã UTF-16, khác số byte UTF-8.

Chương trình dùng `try/finally` để xóa file tạm và không chỉnh sửa bất kỳ file dữ liệu ứng dụng nào. Số liệu thử nghiệm **không chứng minh** tệp được cấp phát 4 KiB hay 8 KiB thực tế; nó chỉ minh họa các phép đo đúng tầng.

### 9.2. Nếu máy khác có block size khác thì sao?

`FileStore.getBlockSize()` có thể trả về giá trị khác 4096, hoặc provider có thể không hỗ trợ. Đây **không phải lỗi bài học**. Con số 4096 trong `hypotheticalWholeBlocks` là **tham số giả định do code truyền vào** để minh họa, không phải giá trị được báo từ FileStore thực tế.

Nếu muốn in giá trị thật để khảo sát môi trường, thay phần truy vấn bằng:

~~~java
FileStore store = Files.getFileStore(file);
try {
    System.out.println("Actual file-store block size: " +
            store.getBlockSize());
} catch (UnsupportedOperationException ex) {
    System.out.println("Block-size query not supported");
}
~~~

Đoạn này cần nằm trong phương thức có `file` kiểu `Path` và xử lý `IOException`. **Không viết phần stdout cố định** cho đoạn truy vấn phụ này, bởi nó phụ thuộc môi trường.

## 10. Cách đánh giá thực tế: đừng biến block size thành allocated size

Khi khảo sát dung lượng lưu trữ của một file, cần phân biệt:

| Câu hỏi thực tế | Thông tin cần |
| --- | --- |
| Người dùng upload một tệp có nội dung dài bao nhiêu byte? | `Files.size(path)` của regular file. |
| Có bao nhiêu byte trên mỗi block của FileStore? | `Files.getFileStore(path).getBlockSize()` nếu được hỗ trợ. |
| FileStore có tổng sức chứa bao nhiêu? | `getTotalSpace()`. |
| JVM còn có thể dùng khoảng bao nhiêu byte trong FileStore? | `getUsableSpace()` như một gợi ý hiện thời. |
| Tệp đã cấp phát thật bao nhiêu byte trên đĩa? | Dùng API/công cụ **đặc thù provider hoặc hệ điều hành** có định nghĩa rõ về allocated size; không lấy bằng `Files.size` hay nhân block size. |
| Một thư mục chiếm bao nhiêu dung lượng? | Cần duyệt nội dung và định nghĩa rõ muốn tổng **logical file bytes** hay **disk usage**; `Files.size(directory)` không phải tổng đệ quy. |

### 10.1. Thuộc tính cấp phát theo nền tảng: tùy chọn, không portable

Một số hệ thống tệp/OS có metadata riêng về số khối được cấp cho file. Trong các môi trường POSIX hoặc provider cụ thể, có thể có thông số tương tự `st_blocks`, nhưng **đây không phải thuộc tính portable mà Java SE chuẩn cam kết trên mọi hệ thống**.

Không nên đặt một chuỗi attribute như `"unix:blocks"` vào thư viện đa nền tảng rồi giả định Windows, macOS, Linux, cloud file system và provider tùy chỉnh đều trả kết quả giống nhau. Nếu dự án bắt buộc cần disk usage vật lý:

1. Xác định rõ platform và file-system provider.
2. Kiểm tra thuộc tính/API thực sự được hỗ trợ.
3. Hiểu đơn vị của kết quả (một số bộ đếm khối có đơn vị riêng, **không nhất thiết** bằng `getBlockSize()`).
4. Kiểm tra hard links, sparse extents, compressed/shared data và semantics quota.
5. Có fallback hoặc trạng thái **không biết được** thay vì bịa một giá trị chính xác.

### 10.2. Vì sao không thể lấy “disk used” = logical size cho mọi file?

Với các mục đích hiển thị như file manager hoặc UI upload, kích thước logic là hữu ích. Nhưng khi phân tích storage billing, backup, compression, dedup, shared blocks, snapshots hoặc sparsity, tổng byte vật lý **không tự bằng** tổng byte logic.

Một file có thể rất lớn về logical size nhưng lưu trữ ít block, hoặc có metadata/đặc tính phân bổ khiến chi phí khác số byte nội dung. Hai file có thể dùng chung dữ liệu qua clone/hard link. Không có một công thức portable duy nhất từ `Files.size` và `FileStore.getBlockSize` cho mọi trường hợp ấy.

## 11. Lưu ý khi triển khai: lỗi, giới hạn, metadata và concurrency

### 11.1. `UnsupportedOperationException` không phải `IOException`

Đoạn sau **chưa đầy đủ** nếu provider không hỗ trợ block size:

~~~java
try {
    long block = store.getBlockSize();
} catch (java.io.IOException ex) {
    // Chỉ xử lý lỗi I/O.
}
~~~

`UnsupportedOperationException` là **runtime exception**, không phải subclass của `IOException`. Vì vậy cần thêm catch tương ứng nếu code có khả năng chạy trên provider không hỗ trợ:

~~~java
try {
    long block = store.getBlockSize();
} catch (UnsupportedOperationException ex) {
    // Truy vấn không được provider hỗ trợ.
} catch (java.io.IOException ex) {
    // Lỗi I/O khi truy vấn.
}
~~~

Trong phương thức này, `store` đã là một `FileStore` hợp lệ. `IOException` là checked exception; `UnsupportedOperationException` có thể phát sinh theo hợp đồng API. **Không** coi unsupported là bằng 0 byte/block: JavaDoc yêu cầu giá trị dương khi truy vấn thành công.

### 11.2. `Files.size` có thể lỗi hoặc thay đổi

~~~java
long before = Files.size(path);
// Một tiến trình khác có thể sửa file ở đây.
long after = Files.size(path);
~~~

`before` và `after` không bắt buộc bằng nhau nếu file bị cập nhật. Kết quả của `Files.size` là giá trị tại thời điểm metadata được lấy, **không khóa file** hoặc tạo snapshot bất biến.

Ngoài ra, `Files.size` có thể ném `IOException` khi file không tồn tại hoặc không thể đọc metadata. Không nên dùng số liệu vừa đo làm bảo đảm rằng file không thay đổi trong bước xử lý tiếp theo.

Nếu cần tính toàn vẹn trong lúc xử lý upload hoặc hash, cần mô hình hóa nguồn dữ liệu, quyền truy cập và cơ chế kiểm tra/khóa/snapshot riêng.

### 11.3. FileStore có thể khác theo đường dẫn

Không giả định mọi file trên máy luôn nằm cùng một FileStore. Hai đường dẫn khác nhau có thể ở hai phân vùng, volume, mount point hoặc provider khác nhau.

~~~java
FileStore storeA = Files.getFileStore(pathA);
FileStore storeB = Files.getFileStore(pathB);
~~~

Nếu truy vấn kích thước khối hoặc dung lượng để quyết định nơi lưu file, hãy tra **FileStore tương ứng với đường dẫn đích thực tế**. Đừng dùng block size của ổ chứa chương trình để suy đoán mọi file đầu ra.

### 11.4. Tệp không thông thường

Đối với directory, symbolic link, special file hoặc file system ảo:

- `Files.size(path)` không nhất thiết có nghĩa “số byte nội dung regular file”.
- Giá trị trên đối tượng không phải regular file là **implementation-specific**.
- Liên kết tượng trưng có thể khiến ý nghĩa phép đo phụ thuộc cách phương thức theo liên kết và các options `NOFOLLOW_LINKS` của phương thức tương ứng.
- Muốn chỉ xử lý regular files, kiểm tra loại tệp bằng `Files.isRegularFile` hoặc `BasicFileAttributes.isRegularFile`, cùng chính sách symbolic link đã chọn.

Không lấy `Files.size(directory)` rồi diễn giải như tổng số file bên dưới. Nếu muốn tổng độ dài logic trong thư mục, cần một thuật toán duyệt cây file đúng quy tắc và cẩn thận với hard links, symlinks, lỗi truy cập và file thay đổi khi duyệt.

### 11.5. Byte và đơn vị hiển thị

Khi `getBlockSize()` hoặc `Files.size()` trả một `long`, đơn vị gốc là **byte**. Nếu hiển thị:

- `1 KiB = 1024 B`.
- `1 MiB = 1024 KiB`.
- `1 GiB = 1024 MiB`.
- `1 kB = 1000 B` theo hệ thập phân.

Chọn ký hiệu đúng. Một khối **4096 B = 4 KiB**, không phải 4 kB chính xác theo định nghĩa SI. Nếu dùng đơn vị MB/GB trong UI, hãy ghi rõ quy ước chuyển đổi để tránh chênh lệch khi người dùng đối chiếu với công cụ OS.

## 12. Các ví dụ phân biệt “đúng số nhưng sai ý nghĩa”

### Ví dụ A: block size trùng kích thước file

Giả sử một tệp dài 4096 byte nằm trên FileStore có `getBlockSize() = 4096`. Hai số **tình cờ bằng nhau**, nhưng vẫn khác ngữ nghĩa:

- File size là số byte nội dung logic của một file.
- Block size là số byte một block của FileStore.

Nếu file dài 4097 byte, block size **vẫn có thể là 4096** trong khi file size đổi thành 4097.

### Ví dụ B: file rỗng

`Files.size(emptyFile) = 0` nhưng `getBlockSize` của FileStore vẫn có thể trả một số dương, ví dụ 4096. Không suy luận rằng FileStore có block size 0 chỉ vì file rỗng.

### Ví dụ C: file lớn trên FileStore có block nhỏ

File logic 20 GiB có thể nằm trên FileStore với block size vài KiB. Chỉ cần biết block size **không giúp** biết file có nén, sparse hay đã được cấp phát bao nhiêu extent thực.

### Ví dụ D: text UTF-8

Chuỗi Java `"Aé"` dài 2 UTF-16 code units; sau khi ghi UTF-8, file có 3 byte. Block size có thể là hàng nghìn byte. Ba đại lượng cùng có vẻ “kích thước” nhưng trả lời ba câu hỏi khác nhau.

### Ví dụ E: hạn ngạch lưu trữ

`Files.size(file) = 1 GiB` không bảo đảm `store.getUsableSpace()` giảm đúng 1 GiB sau khi thêm file: nén, sparse, metadata, cache, chia sẻ dữ liệu và thay đổi đồng thời có thể tác động. Không dùng phép trừ đơn giản để đo chi phí trên mọi file system.

## 13. Những lỗi phổ biến khi làm việc với FileStore

| Ngộ nhận | Vấn đề | Cách sửa |
| --- | --- | --- |
| “`FileStore.getBlockSize()` trả kích thước tệp.” | Block size thuộc FileStore. | Dùng `Files.size(path)` để đo độ dài file logic. |
| “`Files.size()` cho biết số byte đĩa thực chiếm.” | Sparse, nén, hard links, metadata làm khác nhau. | Tách logical size và allocated size; dùng công cụ/provider thích hợp. |
| “File size phải chia hết cho block size.” | File logic có thể dài 1 hoặc 5001 byte. | Không tự padding file để khớp block size. |
| “Chỉ cần `ceil(size/block) * block` là biết disk usage.” | Đây chỉ là mô hình lý thuyết, không là phép đo. | Nêu giả định hoặc lấy metadata allocation thực. |
| “Block size luôn là 4096.” | Phụ thuộc FileStore và provider. | Hỏi `getBlockSize()` khi hỗ trợ; không hard-code. |
| “`getBlockSize()` chắc chắn có trên mọi provider.” | Có thể ném `UnsupportedOperationException`. | Xử lý unsupported và lỗi I/O. |
| “`getBlockSize()` không hỗ trợ thì trả 0.” | Hợp đồng thành công yêu cầu kết quả dương. | Biểu diễn trạng thái unknown/unsupported riêng. |
| “`getBlockSize()` và sector/page/buffer size bằng nhau.” | Thuộc các tầng khác nhau. | Không hoán đổi các thông số. |
| “`FileStore.getTotalSpace()` là kích thước file.” | Đây là sức chứa toàn FileStore. | Phân biệt scope. |
| “`getUnallocatedSpace()` chắc chắn bằng byte tôi có thể ghi.” | Quotas/privileges và thay đổi đồng thời. | Xem `getUsableSpace()` như gợi ý, kiểm tra lỗi khi ghi. |
| “`Files.size(directory)` là tổng dung lượng thư mục.” | Không được quy định như vậy. | Duyệt các regular files theo chính sách cụ thể. |
| “`String.length()` bằng `Files.size` của file UTF-8.” | UTF-16 code units khác byte UTF-8. | Dùng encoding và `Files.size` đúng. |
| “Tôi có thể cộng mọi `Files.size` để tính chính xác disk usage.” | Hard links, compression, shared blocks. | Định nghĩa metric logical vs physical và tránh double-counting. |
| “Hai lần `Files.size` luôn trả cùng số.” | File có thể thay đổi. | Xét concurrency và snapshot/locking. |
| “Có block size là chọn được buffer tối ưu mọi lúc.” | Hiệu năng phụ thuộc hệ điều hành, API, cache, workload. | Benchmark trên hệ thống đích; không suy luận trực tiếp. |

## 14. Bài tập thực hành có đáp án

### Câu 1 — Phân biệt scope

Một file có `Files.size(file) = 100`. FileStore chứa nó có `getBlockSize() = 4096`. Hai giá trị biểu diễn gì?

**Đáp án:** `100` là số byte **logic của file**; `4096` là số byte/block **của FileStore**. Không phải cả hai cùng đo một file.

### Câu 2 — Làm tròn giả định

Trong mô hình đơn giản cấp phát theo block 4096 B, tệp có `logicalSize = 4097` cần ít nhất mấy block theo phép tính?

**Đáp án:** 2 block, tương ứng 8192 byte **theo mô hình**. Không được khẳng định dung lượng thực tế cấp phát chính xác là 8192 byte.

### Câu 3 — Sparse file

Tệp sparse có logical size 10 GiB có bắt buộc chiếm 10 GiB vật lý không?

**Đáp án:** Không. Một số vùng logic có thể không được cấp phát. `Files.size` không đo trực tiếp allocated bytes.

### Câu 4 — Provider không hỗ trợ

Nếu `store.getBlockSize()` ném `UnsupportedOperationException`, bạn có nên dùng 4096 làm giá trị “chính xác” không?

**Đáp án:** Không. Xử lý trạng thái unsupported. Chỉ dùng 4096 nếu đó là **giả định mô phỏng đã ghi rõ**, không phải giá trị đo thực.

### Câu 5 — API khác tầng

Giải thích `FileStore.getTotalSpace()` và `FileStore.getBlockSize()` khác nhau thế nào.

**Đáp án:** `getTotalSpace` cho byte của **toàn FileStore**; `getBlockSize` cho byte **mỗi block**. Không API nào đo trực tiếp kích thước của một file cụ thể.

### Câu 6 — Java text

Một file UTF-8 chứa `"Aé"`, không có BOM hoặc byte bổ sung. `String.length()` và `Files.size` bằng bao nhiêu?

**Đáp án:** `String.length() = 2` đơn vị mã UTF-16, còn `Files.size(file) = 3` byte nếu file chỉ chứa đúng UTF-8 của chuỗi đó.

### Câu 7 — Đặt tên hàm

Hàm sau có tên đúng không?

~~~java
long allocatedBytes(Path file) throws IOException {
    return Files.size(file);
}
~~~

**Đáp án:** Không. `Files.size` đo **logical file bytes**; tên `allocatedBytes` gợi ý dung lượng vật lý cấp phát nên gây hiểu lầm. Tên tốt hơn là `logicalFileBytes` hoặc `fileSizeBytes`.

### Câu 8 — File trong thư mục

`Files.size(directory)` có cho tổng các regular files nằm bên dưới không?

**Đáp án:** Không. Với đối tượng không phải regular file, kết quả không có nghĩa portable như tổng dung lượng đệ quy. Phải duyệt cây file và định nghĩa cách xử lý symlink/hard link, lỗi truy cập, file thay đổi.

### Câu 9 — Thời điểm truy vấn

Một tiến trình khác tăng kích thước file ngay sau khi `Files.size` trả về. Giá trị đã đo có tự cập nhật không?

**Đáp án:** Không. Đây là một `long` đã trả về ở thời điểm trước; nó không ràng buộc kích thước file tương lai.

### Câu 10 — Block size và buffer

FileStore báo block size 4096. Có phải mọi `InputStream.read(byte[100])` đều sai không?

**Đáp án:** Không. Java I/O cho phép caller đọc/ghi lượng byte theo API. Tầng file system/thiết bị xử lý tổ chức block. Không buộc mọi Java buffer phải là bội số block size.

### Câu 11 — Rounding và overflow

Vì sao không nên dùng `(size + block - 1) / block * block` trên mọi giá trị `long`?

**Đáp án:** `size + block - 1` hoặc phép nhân cuối có thể tràn `long`. Dùng phép chia/dư kết hợp `Math.addExact` và `Math.multiplyExact`, hoặc `BigInteger` nếu miền cần rộng hơn. Dù tính đúng, kết quả vẫn chỉ là **lý thuyết**.

### Câu 12 — Quota

`getUnallocatedSpace()` lớn hơn kích thước file định ghi. Có bảo đảm ghi thành công không?

**Đáp án:** Không. Quyền, quota, cập nhật đồng thời, lỗi I/O hoặc các chính sách file system vẫn có thể chặn thao tác. `getUsableSpace()` hữu ích hơn cho quyền JVM nhưng cũng chỉ là gợi ý không bảo đảm.

## 15. Checklist trước khi dùng số liệu lưu trữ

- [ ] Tôi biết mình hỏi **kích thước khối**, **độ dài tệp**, **dung lượng kho** hay **allocated disk usage**.
- [ ] Nếu cần file logical bytes, tôi dùng `Files.size(path)` cho regular file.
- [ ] Nếu cần block size, tôi lấy `FileStore` từ đúng `Path` và gọi `getBlockSize()` (Java 10+).
- [ ] Tôi xử lý `UnsupportedOperationException` và `IOException` theo hợp đồng, không coi unsupported là 0.
- [ ] Tôi không hard-code 4096 thành sự thật về mọi FileStore.
- [ ] Tôi không xem block size là sector size, memory page size hoặc Java buffer size.
- [ ] Tôi hiểu phép tính làm tròn theo block **chỉ hợp lệ theo giả định được công bố**.
- [ ] Tôi không dùng `roundUp(Files.size(), getBlockSize())` để khẳng định allocated bytes thực.
- [ ] Tôi đã cân nhắc sparse, compression, hard links, shared extents, metadata và quota.
- [ ] Tôi không coi `Files.size(directory)` là tổng dung lượng đệ quy.
- [ ] Tôi phân biệt byte của file UTF-8 với `String.length()`.
- [ ] Tôi không dựa vào kết quả đo như một ảnh chụp bất biến khi tệp đang bị sửa.
- [ ] Tôi biết `getTotalSpace`/`getUnallocatedSpace`/`getUsableSpace` đo toàn FileStore và là các thông số thay đổi.
- [ ] Nếu cần allocated bytes thực, tôi xác định API/provider/hệ điều hành và semantics của phép đo.
- [ ] Tôi đã kiểm tra exception và trường hợp provider không hỗ trợ trên môi trường triển khai.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — `FileStore`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileStore.html): `getBlockSize()` **Since 10**, giá trị dương byte/block, `IOException` và `UnsupportedOperationException`, các phương thức space.
- [Oracle Java SE 25 — `Files.size(Path)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#size(java.nio.file.Path)): kích thước file tính theo byte và khả năng khác mức sử dụng thực do compression, sparse file và nguyên nhân khác.
- [Oracle Java SE 25 — `Files.getFileStore(Path)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): tìm FileStore chứa đối tượng được chỉ định.
- [Oracle Java SE 25 — `BasicFileAttributes`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `size()`, `isRegularFile()` và các metadata liên quan.
- [Oracle Java SE 25 — `Files.writeString`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#writeString(java.nio.file.Path,java.lang.CharSequence,java.nio.charset.Charset,java.nio.file.OpenOption...)): ví dụ Java 11+ về ghi text đã mã hóa thành file.
- [Oracle Java SE 25 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và các charset tiêu chuẩn.
- [Oracle Java SE 25 — `Math.multiplyExact`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): xử lý overflow khi tính toán số byte lớn.

**Kết luận:** `FileStore.getBlockSize()` (Java 10) trả **số byte trên một khối của kho lưu trữ**; `Files.size(path)` trả **kích thước logic của một tệp**; còn số byte vật lý được cấp phát cho tệp là **một đại lượng thứ ba**, không được phép suy ra chính xác bằng phép làm tròn kích thước file theo block size trên mọi file system. Chọn API và cách diễn giải theo đúng câu hỏi cần trả lời.
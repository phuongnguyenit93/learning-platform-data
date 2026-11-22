# FileStore.getBlockSize và đơn vị kích thước khối trong Java

> **Java 10 — Thông tin FileStore.** Phương thức `java.nio.file.FileStore.getBlockSize()` được bổ sung từ Java 10, vẫn còn trong Java SE hiện đại. Nó trả về **kích thước một block của file store, tính bằng byte**, không phải số block, số byte còn trống, kích thước tệp hay dung lượng dữ liệu đã cấp phát thật. Tùy provider, phương thức có thể không được hỗ trợ. Bài tập trung vào API còn áp dụng hiện nay và cách xử lý đúng đơn vị, sai số, giới hạn đo lường, exception và portability.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `FileStore` đại diện cho vùng lưu trữ/filesystem/volume, không phải một tệp; lấy đúng `FileStore` từ `Path` bằng `Files.getFileStore(path)`.
2. Đọc chữ ký `long getBlockSize() throws IOException`; biết kết quả **dương**, đơn vị **byte/block**, phương thức có từ **Java 10**, và có thể ném `UnsupportedOperationException`.
3. Phân biệt kích thước block với `Files.size(path)`, `getTotalSpace()`, `getUnallocatedSpace()`, `getUsableSpace()` và kích thước bộ đệm I/O.
4. Đổi chính xác giữa byte, KiB và kB, tránh khẳng định “4 KB” khi đơn vị có thể đang là KiB, hoặc tự coi kích thước block là bội số 1024.
5. Thực hiện phép tính mô phỏng `ceil(logicalBytes / blockBytes)` và làm tròn lên theo số khối **không tràn số nguyên**, đồng thời hiểu rằng kết quả này **không chứng minh dung lượng vật lý đã cấp phát**.
6. Viết chương trình Java chạy trên JDK hiện đại, có phần kiểm thử ổn định không cần filesystem thật và phần thăm dò filesystem thật tùy chọn.
7. Xử lý provider không hỗ trợ, lỗi I/O, đường dẫn không hợp lệ và các đặc điểm file system như sparse files, nén dữ liệu, metadata và remote/cloud storage.
8. Viết unit tests theo **hợp đồng API**, không khóa cứng giá trị `4096` hoặc tên ổ đĩa của máy phát triển.

## 2. `FileStore` là gì?

`java.nio.file.FileStore` là lớp trừu tượng mô tả một vùng lưu trữ tệp: pool, volume, partition, filesystem hay thực thể do file-system provider xác định. Một đối tượng `FileStore` **không phải** một tệp cụ thể và không đại diện cho một đường dẫn duy nhất.

Ví dụ hai đường dẫn khác nhau có thể cùng nằm trên một file store, hoặc hai mount khác nhau có thể thuộc những file store khác nhau. Provider có thể ánh xạ vào ổ đĩa cục bộ, network mount, hệ thống file ảo hoặc backend khác. Không nên giả định chỉ có các ký hiệu ổ `C:`/`D:`, hoặc chỉ có filesystem kiểu Unix.

### 2.1. Lấy file store cho một đường dẫn

```java
import java.nio.file.Files;
import java.nio.file.FileStore;
import java.nio.file.Path;

Path path = Path.of(".").toAbsolutePath().normalize();
FileStore store = Files.getFileStore(path);
```

Đây là **đoạn mã minh họa bên trong một phương thức** có xử lý `IOException`. `Path.of(".")` trỏ tới thư mục hiện tại — thường tồn tại, nên phù hợp để thử trên máy đang chạy. Trong hệ thống thật, dùng `Path` chỉ đúng tệp hoặc thư mục cần kiểm tra.

`Files.getFileStore(path)` có thể phát sinh `IOException` nếu không lấy được thông tin cho đường dẫn. Không nên hỏi về file store của một `Path` chưa tồn tại rồi giả định việc truy vấn chắc chắn thành công: hành vi phụ thuộc provider. Nếu yêu cầu là xác định nơi **sẽ** tạo file mới, ứng dụng cần xác định thư mục đích đang tồn tại và chính sách symlink/mount phù hợp trước khi suy luận.

### 2.2. Không lấy kết quả của file store này áp cho file store khác

Giả sử tệp A nằm trong một volume, nhưng tệp B nằm dưới một mount khác. Kích thước block của `FileStore` lấy từ A không nhất thiết có ý nghĩa với B. Vì thế:

```java
var storeA = Files.getFileStore(pathA);
var storeB = Files.getFileStore(pathB);
```

Đây là mã minh họa trong một phương thức có hai `Path` đã khai báo. **Không được** suy luận `storeA.getBlockSize()==storeB.getBlockSize()` chỉ vì hai path cùng chung một thư mục cha về mặt chuỗi hoặc cùng nằm dưới “ổ đĩa” trong giao diện người dùng. Symlink, mount và provider có thể ảnh hưởng đến đối tượng file store thực tế.

## 3. Hợp đồng chính xác của `getBlockSize()`

Theo Javadoc `FileStore`:

```java
public long getBlockSize() throws IOException
```

- **Ý nghĩa:** trả về số **byte trong một block** của file store.
- **Giá trị hợp lệ khi trả về bình thường:** số `long` **dương**.
- **Đơn vị:** byte/block; ví dụ `4096` nghĩa là **4.096 byte trong một block**.
- **Ngoại lệ:** `IOException` khi có lỗi I/O trong quá trình truy vấn; `UnsupportedOperationException` khi file store/provider không hỗ trợ thao tác này.
- **Yêu cầu triển khai:** bản triển khai `getBlockSize()` có sẵn trong lớp cơ sở `FileStore` ném `UnsupportedOperationException`. Provider muốn hỗ trợ có thể ghi đè phương thức.
- **Phiên bản:** `Since: 10` (Java 10). `FileStore` tồn tại từ trước Java 10, nhưng **riêng phương thức `getBlockSize`** bắt đầu từ Java 10.

`getBlockSize()` **không có tham số**. Bạn không cung cấp path tại lời gọi này, bởi `FileStore` đã được xác định trước đó từ `Files.getFileStore(path)` hoặc một cách khác do Java NIO cung cấp.

### 3.1. Vì sao `long` chứ không phải `int`?

Javadoc trả về `long`. Phép đọc trực tiếp:

```java
FileStore store = Files.getFileStore(path);
long bytesPerBlock = store.getBlockSize();
```

Dùng `long` theo API thay vì ép về `int` một cách tùy tiện. Mặc dù nhiều hệ thống có block size ở mức vài KiB, không có lý do biến giới hạn của `int` thành giả định về mọi provider hoặc cấu hình trong tương lai.

Khi tính `blockCount * bytesPerBlock`, ngay cả hai giá trị `long` hợp lệ vẫn có thể tạo phép nhân vượt `Long.MAX_VALUE`. Sử dụng `Math.multiplyExact` nếu cần phát hiện overflow; không mặc nhiên tin phép nhân primitive sẽ tự ném exception.

### 3.2. `UnsupportedOperationException` không có nghĩa “block size = 0”

Một provider có thể **không triển khai** `getBlockSize()`. Đây là một tình huống được Javadoc thừa nhận, không phải bug trong Java 10. Khi đó:
- Không gọi `getBlockSize` rồi tự tin rằng “máy nào cũng trả 4096”.
- Không chuyển exception thành `0` và đưa `0` vào phép chia; làm vậy chỉ biến nguyên nhân thật thành lỗi chia cho 0.
- Không giả định `FileStore.supportsFileAttributeView("basic")` báo được khả năng hỗ trợ `getBlockSize`. Đây là **hai API khác nhau**.
- Nếu việc có block size là tùy chọn, có thể trả về trạng thái **UNKNOWN/UNSUPPORTED**, bỏ qua phần tối ưu tùy chọn hoặc dùng phép tính không cần block size.
- Nếu nghiệp vụ **bắt buộc** biết block size, hãy báo lỗi rõ “file store does not support querying block size”, thay vì dùng một hằng số giả như thông tin thật.

Tương tự, `IOException` nghĩa là **truy vấn thất bại**; không biến nó thành một block size hợp lệ. Hai tình huống cần được ghi log và xử lý riêng.

## 4. Kích thước block, số block và kích thước tệp là ba thứ khác nhau

Xét một file store có block size giả định **4096 byte**:

```text
1 block    = 4096 bytes
           = 4 KiB
           = 4.096 kB

2 blocks   = 8192 bytes
           = 8 KiB
           = 8.192 kB
```

`store.getBlockSize() == 4096` nghĩa là **4096 byte/block**, không phải “filesystem có 4096 block” và cũng không phải “một tệp sẽ có đúng 4096 byte”. Một tệp logic 1 byte hoàn toàn có thể nằm trên file store có block size 4096 byte.

| Đối tượng/API | Thứ đo | Đơn vị | Có phải block size không? |
| --- | --- | --- | --- |
| `store.getBlockSize()` | Kích thước một block của file store | **byte/block** | **Đúng** |
| `Files.size(file)` | Kích thước **logic** của tệp, theo provider | byte | Không |
| `store.getTotalSpace()` | Tổng dung lượng file store | byte | Không |
| `store.getUsableSpace()` | Dung lượng khả dụng cho JVM theo thời điểm đo | byte | Không |
| `store.getUnallocatedSpace()` | Dung lượng chưa được phân bổ trên file store theo thời điểm đo | byte | Không |
| `ByteBuffer.capacity()` | Dung lượng một buffer trong chương trình | số phần tử byte | Không |
| `BufferedInputStream` / `BufferedOutputStream` buffer size | Kích thước vùng đệm I/O của ứng dụng | byte | Không |
| Kích thước sector/physical page của thiết bị | Đơn vị phần cứng hoặc hệ điều hành cụ thể | byte hoặc sector | Không tự động đồng nghĩa block size NIO |
| Dung lượng vật lý đã cấp phát cho một tệp | Thông tin file-system/provider đặc thù | thường được hiển thị bằng byte hoặc block | Không được `getBlockSize` trả về |

Quan trọng: `Files.size(Path)` không phải một phương thức trong `FileStore`. Bạn dùng nó trên **một tệp**; `getBlockSize` nói về **file store** chứa tệp. Dùng hai đại lượng đó cho một phép tính minh họa được, nhưng không được biến chúng thành một đo lường chính xác mức cấp phát vật lý.

### 4.1. KiB và kB không phải cùng đơn vị

- **1 byte (B):** đơn vị số byte.
- **1 kB:** 1000 B, theo tiền tố thập phân SI.
- **1 KiB:** 1024 B, theo tiền tố nhị phân IEC.
- **1 MB:** 1.000.000 B.
- **1 MiB:** 1.048.576 B.

Ví dụ `4096 B == 4 KiB` nhưng bằng `4.096 kB`. Nếu giao diện người dùng viết “4 KB”, người đọc có thể hiểu theo những quy ước khác nhau. Trong tài liệu kỹ thuật và test, nên ghi **4096 bytes (4 KiB)**.

Với `getBlockSize` không cần đoán đơn vị:
- Javadoc nói rõ là **bytes**.
- Chỉ đổi sang KiB khi phục vụ mục đích hiển thị.
- Không chia cho 1024 rồi gửi giá trị `4` vào hàm đang mong chờ **bytes**.
- Không giả định mọi block size chia hết cho 1024. API chỉ hứa một giá trị `long` dương, không hứa đó phải là 2^n.

### 4.2. Block size khác buffer size và không ra lệnh mọi `read/write` phải dài đúng một block

Một chương trình có thể gọi `InputStream.read` để đọc một byte, hoặc `Files.write` để ghi một chuỗi ngắn; API I/O Java không đòi bạn luôn tự chia lời gọi thành đúng `getBlockSize()` byte. File system và các lớp I/O có thể xử lý các đơn vị lưu trữ bên trong.

**Không suy ra**:
- “`read` 1 byte sẽ thất bại nếu block size là 4096”.
- “Đổi mọi buffer Java thành 4096 byte chắc chắn tăng tốc”.
- “Số block của một file luôn bằng số lần `read`/`write` đã gọi”.
- “Block size là TCP packet size hay sector size của SSD”.

Block size là một mẩu **metadata của file store**, không phải một thông số thay thế benchmarking, cache, OS/page size hoặc yêu cầu giao thức.

## 5. Cách tính số block theo mô hình đơn giản

Với kích thước file logic `L` byte và kích thước block `B > 0` byte, mô hình **xếp mỗi byte dữ liệu tuần tự vào các block cùng kích thước** dùng:

\[
\mathrm{blocks}(L,B)=
\begin{cases}
0 & L=0 \\
\left\lceil L/B \right\rceil & L>0
\end{cases}
\]

Phép tính này giúp minh họa vì sao một byte dữ liệu cũng có thể cần một block và vì sao vượt ranh giới block sẽ cần block tiếp theo **trong mô hình lý tưởng**.

### 5.1. Bảng ví dụ với B = 4096 bytes

| Kích thước logic L | L/B làm tròn lên | Dung lượng block giả định bằng `blocks * B` |
| ---: | ---: | ---: |
| 0 B | 0 | 0 B |
| 1 B | 1 | 4096 B |
| 1024 B | 1 | 4096 B |
| 4095 B | 1 | 4096 B |
| 4096 B | 1 | 4096 B |
| 4097 B | 2 | 8192 B |
| 8192 B | 2 | 8192 B |
| 8193 B | 3 | 12288 B |

**Nhãn quan trọng:** cột cuối là **dung lượng làm tròn trong mô hình block-size cố định**, không phải kết quả đo “size on disk”. Sparse files, nén, deduplication, inline data, extent allocation, metadata, journaling, clone/reflink, quota và cơ chế của provider có thể làm số byte thực sự được sử dụng **khác đáng kể**.

Không đưa kết quả `blocks * B` vào hóa đơn lưu trữ, kiểm tra quota hay kết luận “file này thật sự chiếm bao nhiêu byte trên đĩa” nếu chưa có API/hợp đồng phù hợp của hệ thống lưu trữ.

### 5.2. Tính làm tròn lên an toàn trước overflow

Một công thức thường thấy:

```java
// Có thể overflow nếu fileBytes + blockBytes - 1 > Long.MAX_VALUE
long blocks = (fileBytes + blockBytes - 1) / blockBytes;
```

Công thức này toán học đúng với `fileBytes>=0` và `blockBytes>0` nhưng **không an toàn cho toàn bộ miền `long`** vì phép cộng có thể tràn.

Phân tích thương và số dư tránh được phép cộng lớn trước khi chia:

```java
static long blocksFor(long fileBytes, long blockBytes) {
    if (fileBytes < 0 || blockBytes <= 0) {
        throw new IllegalArgumentException(
                "fileBytes >= 0 and blockBytes > 0 required");
    }
    return fileBytes / blockBytes
            + (fileBytes % blockBytes == 0 ? 0 : 1);
}
```

- Nếu `fileBytes` chia hết cho `blockBytes`, giữ nguyên thương.
- Nếu còn dư, cộng thêm một block.
- Nếu `fileBytes==0`, kết quả bằng 0.
- Cộng nhiều nhất 1 vào thương; với `blockBytes>=1` và `fileBytes<=Long.MAX_VALUE`, công thức không vượt miền `long`.

Muốn nhân kết quả để ra “dung lượng làm tròn theo mô hình”, dùng:

```java
static long roundedBytes(long fileBytes, long blockBytes) {
    return Math.multiplyExact(
            blocksFor(fileBytes, blockBytes), blockBytes);
}
```

`Math.multiplyExact` ném `ArithmeticException` nếu kết quả nhân vượt miền `long`. Đừng thay bằng phép nhân `*` thông thường rồi tin một kết quả âm do overflow là dung lượng hợp lệ.

### 5.3. Không dùng `int` cho tổng kích thước lớn

`getBlockSize` và `Files.size` đều trả kiểu `long`. Khi tính số block cho tệp lớn, giữ phép toán ở `long` để tránh cắt cụt:

```java
long fileBytes = Files.size(pathToFile);
long blockBytes = store.getBlockSize();
long estimate = blocksFor(fileBytes, blockBytes);
```

Đoạn là mã minh họa trong một phương thức có `pathToFile` và `store` phù hợp, cùng xử lý exception. Đừng ép `(int) Files.size(...)` vì dữ liệu có thể vượt 2 GiB. Với các kích thước vượt giới hạn `long` của API, phải tìm cách đo/biểu diễn khác ở tầng chuyên biệt; không giả định bản tính dùng `long` đo được mọi lưu trữ trong tương lai.

## 6. Có đo được “file này chiếm bao nhiêu block thật” chỉ bằng `getBlockSize` không?

**Không.** Để biết mức sử dụng thực tế, bạn còn cần biết file system đã phân bổ những extent/block nào cho **tệp cụ thể**, có sparse holes, compressed data, shared extents, inline data, copy-on-write, metadata và các chính sách khác hay không. `FileStore.getBlockSize` chỉ có **một** giá trị kích thước block ở cấp file store.

### 6.1. Ví dụ sparse file

Một sparse file có kích thước logic lớn nhưng các khoảng chưa được ghi có thể không có các block vật lý tương ứng. `Files.size(file)` có thể trả về kích thước logic lớn trong khi dung lượng thực tế được cấp phát nhỏ hơn rất nhiều.

Do đó `ceil(Files.size(file)/blockSize)` **không** phải số block vật lý thực sự đã cấp phát. Nó chỉ là một phép mô phỏng dựa trên cách chia dữ liệu logic thành các đoạn dài bằng block size.

### 6.2. Ví dụ file được nén hoặc deduplicate

Một filesystem có nén/deduplication có thể lưu ít byte vật lý hơn nội dung logic. Tính từ block size và file length sẽ không phản ánh được tỷ lệ nén, chia sẻ dữ liệu hoặc cơ chế mã hóa/metadata.

Ngay cả file không nén và không sparse cũng có thể sử dụng metadata, extent tree, allocation unit hoặc cơ chế tối ưu riêng. Không xem phép nhân làm tròn là “dung lượng trên đĩa” chính xác.

### 6.3. Ví dụ cloud hoặc network file store

Một file-store provider có thể đại diện cho NFS, SMB, hệ thống file ảo hoặc lưu trữ đám mây. Ý nghĩa block và khả năng cung cấp metadata có thể phụ thuộc implementation. Một số provider không hỗ trợ `getBlockSize` và sẽ ném `UnsupportedOperationException`. Mã portable phải chấp nhận điều đó.

Nếu ứng dụng cần quản lý quota/hóa đơn, nên dựa trên **số liệu được dịch vụ lưu trữ cung cấp theo hợp đồng** chứ không tự suy từ block size chung.

## 7. Ví dụ ngắn: truy vấn block size của một đường dẫn thực

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.FileStore;
import java.nio.file.Path;

public class ShowBlockSize {
    public static void main(String[] args) {
        Path path = Path.of(".").toAbsolutePath().normalize();

        try {
            FileStore store = Files.getFileStore(path);
            try {
                long blockBytes = store.getBlockSize();
                System.out.println("bytes per block: " + blockBytes);
            } catch (UnsupportedOperationException ex) {
                System.out.println(
                        "block size not supported by this provider");
            }
        } catch (IOException ex) {
            System.err.println(
                    "Cannot inspect file store: " + ex.getMessage());
        }
    }
}
```

Lưu thành `ShowBlockSize.java` và chạy:

```bash
javac ShowBlockSize.java
java ShowBlockSize
```

**Output phụ thuộc máy và provider**, không có một giá trị chính xác cho mọi môi trường. Có thể thấy ví dụ:

```text
bytes per block: 4096
```

hoặc:

```text
block size not supported by this provider
```

Nếu truy vấn I/O thất bại, chương trình in thông báo lỗi tới `stderr`. **4096 chỉ là một kết quả khả dĩ, không phải default Java hay yêu cầu API.** Một giá trị khác như 1024, 8192 hoặc giá trị dương bất kỳ mà provider trả về vẫn phù hợp với chữ ký API.

### 7.1. Vì sao chương trình không nên in “4 KiB” một cách cố định?

Nếu provider trả về `8192`, việc in “4 KiB” là sai đơn vị/kết quả. Nên hiển thị đúng số **bytes** đã đọc, rồi tùy chọn đổi sang KiB nếu người dùng cần.

Nếu in KiB, dùng `blockBytes / 1024.0` để không bị mất phần lẻ; khi định dạng cho giao diện, nên hiển thị rõ đơn vị và quy tắc làm tròn.

### 7.2. Vì sao bắt `UnsupportedOperationException` bên trong `IOException`?

`UnsupportedOperationException` là unchecked exception, **không phải subtype của `IOException`**. `catch(IOException)` một mình không bắt được nó. Cấu trúc try/catch lồng giúp phân biệt hai ý nghĩa:
- FileStore đã xác định nhưng API block-size **không hỗ trợ**.
- Thao tác truy vấn file store hoặc block-size **thất bại do I/O**.

Trong ứng dụng cần audit, log các trường hợp này bằng nhãn riêng. Đừng coi “không hỗ trợ” là “block size bằng 0”, “không còn dung lượng” hoặc “tệp hỏng”.

## 8. Lab Java hoàn chỉnh: API thực và giả lập để có kết quả kiểm thử ổn định

Để có **stdout chính xác trên mọi máy**, chương trình dưới đây mặc định dùng **FileStore giả lập** có block size 4096. Đồng thời chương trình có chế độ `--live` để thăm dò file store của thư mục hiện tại. Cách tổ chức này tránh khẳng định mọi máy có cùng một block size.

### 8.1. Môi trường

Dùng một bản JDK đang được hỗ trợ/cập nhật bản vá, ví dụ bản phân phối **JDK 21 hoặc 25 LTS** theo chính sách tổ chức. `FileStore.getBlockSize` là API Java 10 và vẫn hiện diện trên các JDK mới. Không cần cài bản Java 10 cũ.

```bash
java -version
javac -version
```

Lưu mã dưới đây thành **`FileStoreBlockLab.java`**:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;

public class FileStoreBlockLab {
    /**
     * FileStore giả lập chỉ dùng để test. Các phương thức abstract
     * đều có implementation; getBlockSize() cố ý KHÔNG override
     * để kiểm tra hành vi mặc định của FileStore Java 10+.
     */
    static class UnsupportedStore extends FileStore {
        @Override
        public String name() { return "example"; }

        @Override
        public String type() { return "synthetic"; }

        @Override
        public boolean isReadOnly() { return false; }

        @Override
        public long getTotalSpace() { return 1_000_000L; }

        @Override
        public long getUsableSpace() { return 800_000L; }

        @Override
        public long getUnallocatedSpace() { return 900_000L; }

        @Override
        public boolean supportsFileAttributeView(
                Class<? extends FileAttributeView> type) {
            return false;
        }

        @Override
        public boolean supportsFileAttributeView(String name) {
            return false;
        }

        @Override
        public <V extends FileStoreAttributeView> V
                getFileStoreAttributeView(Class<V> type) {
            return null;
        }

        @Override
        public Object getAttribute(String attribute) {
            throw new UnsupportedOperationException();
        }
    }

    /** Provider giả lập hỗ trợ block-size 4096 bytes. */
    static final class FixedStore extends UnsupportedStore {
        @Override
        public long getBlockSize() {
            return 4096L;
        }
    }

    /** Số block trong MÔ HÌNH chia dữ liệu logic theo block đều. */
    static long blocksFor(long logicalBytes, long blockBytes) {
        if (logicalBytes < 0 || blockBytes <= 0) {
            throw new IllegalArgumentException(
                    "Expected non-negative bytes and positive block size");
        }
        return logicalBytes / blockBytes
                + (logicalBytes % blockBytes == 0 ? 0 : 1);
    }

    /** Số byte làm tròn theo mô hình; phát hiện overflow. */
    static long simpleRoundedBytes(long logicalBytes,
                                   long blockBytes) {
        return Math.multiplyExact(
                blocksFor(logicalBytes, blockBytes), blockBytes);
    }

    /** Nhánh tùy chọn: chạy trên file store của thư mục thật. */
    static void inspectLive(Path path) {
        try {
            FileStore store = Files.getFileStore(path);
            try {
                long value = store.getBlockSize();
                System.out.println("live block bytes: " + value);
                System.out.println("live positive: " + (value > 0));
            } catch (UnsupportedOperationException ex) {
                System.out.println("live block size: unsupported");
            }
        } catch (IOException ex) {
            System.out.println(
                    "live file store: I/O error ("
                    + ex.getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        // Fixture dương đã biết; KHÔNG coi 4096 là mặc định hệ thống.
        FileStore known = new FixedStore();
        long block = known.getBlockSize();

        System.out.println("known block bytes: " + block);
        System.out.println("known block KiB: " + (block / 1024));
        System.out.println("0 bytes -> blocks: "
                + blocksFor(0L, block));
        System.out.println("1 byte -> blocks: "
                + blocksFor(1L, block));
        System.out.println("4096 bytes -> blocks: "
                + blocksFor(4096L, block));
        System.out.println("4097 bytes -> blocks: "
                + blocksFor(4097L, block));
        System.out.println("4097 bytes -> simple rounded bytes: "
                + simpleRoundedBytes(4097L, block));
        System.out.println("two blocks -> bytes: "
                + Math.multiplyExact(2L, block));

        // Hai đại lượng này cùng đơn vị bytes nhưng khác ý nghĩa.
        System.out.println("store usable bytes (different metric): "
                + known.getUsableSpace());

        try {
            new UnsupportedStore().getBlockSize();
        } catch (UnsupportedOperationException ex) {
            System.out.println("unsupported provider: handled");
        }

        try {
            blocksFor(1L, 0L);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero block: rejected");
        }

        try {
            simpleRoundedBytes(Long.MAX_VALUE, block);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "rounded bytes overflow: detected");
        }

        if (args.length > 0 && "--live".equals(args[0])) {
            inspectLive(Path.of(".").toAbsolutePath().normalize());
        }
    }
}
```

### 8.2. Biên dịch và chạy mặc định

```bash
javac FileStoreBlockLab.java
java FileStoreBlockLab
```

Stdout **chính xác 12 dòng**, do fixture giả lập có giá trị 4096 cố định:

```text
known block bytes: 4096
known block KiB: 4
0 bytes -> blocks: 0
1 byte -> blocks: 1
4096 bytes -> blocks: 1
4097 bytes -> blocks: 2
4097 bytes -> simple rounded bytes: 8192
two blocks -> bytes: 8192
store usable bytes (different metric): 800000
unsupported provider: handled
zero block: rejected
rounded bytes overflow: detected
```

Mỗi dòng có một ý nghĩa kiểm thử rõ ràng; không cần tạo tệp thật hoặc gắn ổ mới. Phần logic trên đã được chạy thử trên JDK hiện đại.

### 8.3. Chạy thử file store thật, output không cố định

```bash
java FileStoreBlockLab --live
```

Khi chạy với `--live`, 12 dòng giả lập vẫn xuất hiện như trên; sau đó có **dòng phụ thuộc môi trường**, chẳng hạn:

```text
live block bytes: 4096
live positive: true
```

hoặc:

```text
live block size: unsupported
```

Nếu truy vấn `Files.getFileStore` hoặc `getBlockSize` thất bại do I/O, chương trình in một dòng dạng `live file store: I/O error (IOExceptionSubtype)` với tên subtype thực tế. Không copy một mẫu output tùy môi trường rồi dùng làm assertion cứng trên các máy khác.

### 8.4. Vì sao cần hai loại `FileStore` giả lập?

`UnsupportedStore` là một lớp `FileStore` tùy biến thực hiện đầy đủ các **abstract methods**, nhưng không ghi đè `getBlockSize()`. Theo contract `FileStore` từ Java 10, phương thức kế thừa từ lớp cơ sở ném `UnsupportedOperationException`. Điều này chứng minh một provider **có thể không hỗ trợ** lời gọi.

`FixedStore` ghi đè `getBlockSize()` để trả về `4096L`, cho phép kiểm thử tính toán **không phụ thuộc vào máy chạy**. Các số `1_000_000` hay `800_000` trong fixture chỉ là dữ liệu giả lập để nhấn mạnh rằng `getUsableSpace()` không trả về kích thước block.

Không sử dụng `UnsupportedStore` hoặc `FixedStore` để mô tả một file system production, quyết định quota thật hay xác định kích thước block của đĩa. Chúng là **test doubles**, được tạo nhằm kiểm chứng hợp đồng và xử lý exception.

### 8.5. Diễn giải dòng làm tròn an toàn

`blocksFor(4097,4096)==2` vì `4097/4096` có thương 1 và số dư 1; thêm một block theo mô hình. Khi nhân `2*4096` ta được `8192` byte **trong mô hình minh họa**. Nó không phải “khẳng định tệp dài 4097 byte chắc chắn chiếm 8192 byte vật lý”.

`simpleRoundedBytes(Long.MAX_VALUE,4096)` cố tạo một giá trị làm tròn vượt giới hạn `long`, nên `Math.multiplyExact` ném `ArithmeticException` và in `rounded bytes overflow: detected`. Cách này giúp phát hiện overflow thay vì trả một số âm.

## 9. Các lỗi thiết kế thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `getBlockSize()` rồi coi kết quả là số block của ổ | Javadoc trả **bytes per block** | Đặt biến `bytesPerBlock`, không đặt `blockCount` |
| Giả định 4096 là chuẩn bắt buộc | API chỉ bảo đảm trả `long` dương nếu hỗ trợ | Test trực tiếp giá trị provider, không hardcode |
| Ghi “kB” nhưng tính chia 1024 | `kB=1000B`, `KiB=1024B` | Ghi bytes và KiB rõ ràng |
| Coi `getBlockSize` là số byte tệp đã cấp phát | Không có thông tin extents/sparse/compression | Dùng API đo cấp phát phù hợp provider hoặc ghi đây chỉ là mô hình |
| Coi `Files.size` là “bytes on disk” | Đây là kích thước file, không phải dung lượng cấp phát thật | Tách logic file length và allocation |
| Lấy block size của file store A áp vào tệp thuộc B | FileStore không nhất thiết giống nhau | Lấy `Files.getFileStore(path)` cho path liên quan |
| Bắt mỗi `IOException` và bỏ qua `UnsupportedOperationException` | UOE là unchecked exception khác loại | Bắt riêng và quyết định fallback/không hỗ trợ |
| Biến UOE thành `0` rồi đem chia | Có thể chia 0; còn che khả năng unsupported | Dùng Optional/status UNKNOWN hay báo lỗi rõ |
| Dùng `(fileBytes+blockBytes-1)/blockBytes` cho mọi `long` | Phép cộng có thể overflow | Chia lấy thương + kiểm tra số dư |
| Nhân `blocks*blockBytes` với `*` không kiểm tra | Overflow `long` có thể cho kết quả vô nghĩa | `Math.multiplyExact` |
| Dùng kích thước block làm kích thước buffer tối ưu tuyệt đối | I/O hiệu năng còn phụ thuộc nhiều yếu tố | Benchmark theo workload và provider |
| Tin block size chắc chắn giống physical sector, page cache hay MTU | Các đơn vị này khác tầng | Đọc đúng contract của từng subsystem |
| Thăm dò bằng `Path` không tồn tại | Provider có thể không truy vấn được file store | Dùng path hiện hữu/mount hợp lệ |
| Test exact block size của máy CI | Linux/Windows/macOS/container/cloud khác nhau | Dùng fixture 4096 và test live linh hoạt |
| Dùng `getUsableSpace` làm số byte ghi chắc chắn thành công | Javadoc gọi đó là hint có thể thay đổi | Xử lý I/O failure, quota, concurrency |
| Hiển thị giá trị thực qua ép kiểu `int` | Có thể cắt cụt `long` | Giữ kiểu `long` |
| Dựa trên một phép đo để suy ra chi phí lưu trữ nhiều file nhỏ | Metadata, compression, dedup, filesystem behavior khác | Dùng telemetry thực tế theo file store |

## 10. Ứng dụng thực tế — nên và không nên sử dụng block size

### 10.1. Hiển thị thông tin volume

Một công cụ diagnostics có thể in tên/type của file store, tổng dung lượng, usable space và block size (nếu có). Nên ghi rõ đơn vị cho từng trường.

Ví dụ format:

```text
FileStore: <implementation-specific name>
Block size: <positive long> bytes/block, or unsupported
Total space: <long> bytes
Usable space: <long> bytes (current estimate)
```

Đây là **mẫu format**, không phải stdout cố định. Không suy luận tất cả file stores có cùng tên, hỗ trợ cùng attributes, hay `getUsableSpace` ổn định trong suốt thời gian chương trình chạy.

### 10.2. Ước lượng mô hình lưu trữ để giải thích cho người học

Nếu muốn minh họa dữ liệu 1 byte có thể dẫn đến việc dùng một đơn vị lưu trữ lớn hơn, `getBlockSize` giúp cung cấp một đại lượng hợp lý cho sơ đồ học tập. Nhưng phải giữ nhãn **mô hình** và nêu giới hạn.

Ví dụ `ceil(fileBytes/blockBytes)` có thể là số **đơn vị chia dữ liệu logic**; nó không phải lời đo chính xác số block vật lý mà file system đã cấp phát.

### 10.3. Quyết định cấp phát bộ đệm I/O

Một số người muốn chọn buffer size bằng block size. Đây có thể là **một giả thuyết hiệu năng cần đo**, nhưng không phải yêu cầu từ Javadoc. Với buffered I/O, hiệu năng phụ thuộc pattern truy cập, kích thước tệp, page cache, JDK, OS, thiết bị, compression, network RTT và nhiều yếu tố khác.

Nên dùng kích thước buffer hợp lý ban đầu, benchmark workload thực tế, và chỉ sử dụng block-size metadata như một dữ kiện khi có bằng chứng.

### 10.4. Kiểm tra còn đủ dung lượng trước khi ghi

`getUsableSpace()` có thể giúp **ước tính** khả năng chứa dữ liệu, nhưng Javadoc cảnh báo kết quả là một hint dễ lỗi thời bởi I/O từ các chương trình khác. `getBlockSize` không giải quyết rủi ro cạnh tranh/quota/permission, và phép nhân làm tròn không chứng minh việc ghi sẽ thành công.

Ứng dụng vẫn phải xử lý `IOException` ở bước tạo, ghi, flush, close và publish theo yêu cầu. Nếu dữ liệu quan trọng, cân nhắc staging/transaction hơn là chỉ hỏi trước bao nhiêu byte còn trống.

### 10.5. Cập nhật logic phụ thuộc nền tảng

Một hệ thống hỗ trợ cả local file, NFS và các FileSystemProvider tùy biến có thể gặp `UnsupportedOperationException`. Đừng khóa hoạt động chính vào metadata block size nếu tính năng ấy chỉ dùng để tối ưu hiển thị hay hiệu năng. Khả năng **chạy đúng khi không biết block size** thường quan trọng hơn tối ưu một vài phần trăm cho một provider.

## 11. Kiểm thử `FileStore.getBlockSize` đúng hợp đồng

### 11.1. Test logic xác định với fixture

Với `FixedStore`, những assertion ổn định bao gồm:

```java
// Đoạn minh họa bên trong class test có định nghĩa FixedStore.
long block = new FixedStore().getBlockSize();
if (block != 4096L) {
    throw new AssertionError("Incorrect fixture");
}
if (blocksFor(4096L, block) != 1L) {
    throw new AssertionError("One-block boundary failed");
}
if (blocksFor(4097L, block) != 2L) {
    throw new AssertionError("Rounding boundary failed");
}
```

Fixture kiểm tra cả cách tính, đơn vị và ranh giới. Không đụng tới hệ thống lưu trữ thật.

### 11.2. Test provider không hỗ trợ

`UnsupportedStore` kế thừa `getBlockSize` mặc định. Test phải xác nhận xảy ra `UnsupportedOperationException`, rồi xem ứng dụng thực tế có gắn trạng thái unsupported, đưa ra thông báo hay tiếp tục xử lý phần tùy chọn hay không.

Đừng viết một test rằng “nếu provider không hỗ trợ thì block size = 0” khi API không đưa ra hợp đồng như vậy.

### 11.3. Test tích hợp trên file store thật

Khi có môi trường tích hợp riêng:

```java
var path = Path.of(".").toAbsolutePath().normalize();
var fileStore = Files.getFileStore(path);

try {
    long blockBytes = fileStore.getBlockSize();
    if (blockBytes <= 0) {
        throw new AssertionError("Invalid block-size contract");
    }
} catch (UnsupportedOperationException expected) {
    // Chấp nhận chỉ nếu tính năng là tùy chọn trong test plan.
}
```

Đây là đoạn minh họa trong phương thức có imports/throws phù hợp. **Không** khẳng định giá trị đúng phải là `4096`; chỉ kiểm tra `>0` nếu provider hỗ trợ. Đối với `IOException`, test tích hợp cần báo lỗi môi trường hoặc retry theo policy rõ ràng; đừng ngầm biến thành pass.

### 11.4. Test những đường biên số học

Nên bao gồm:
- `logicalBytes=0` và block dương.
- `logicalBytes=1` và block dương.
- `logicalBytes=blockBytes`.
- `logicalBytes=blockBytes+1` (với các giá trị nhỏ đã biết).
- `logicalBytes=Long.MAX_VALUE` để chắc chắn không overflow ở bước cộng làm tròn.
- `blockBytes=0`, `blockBytes<0`, `logicalBytes<0` là tham số sai của helper.
- `blocks*blockBytes` vượt `Long.MAX_VALUE`, phải ném `ArithmeticException` nếu dùng `Math.multiplyExact`.

Bộ test này tập trung vào **logic phụ trợ**; không mô phỏng đầy đủ file-system allocation.

## 12. Bài tập luyện tập (có đáp án)

### Bài 1 — Đọc tên biến và đơn vị

```java
long n = store.getBlockSize();
```

**Hỏi:** `n` có phải số block của file store không?

**Đáp án:** Không; `n` là **số byte trên mỗi block**. Nên đổi tên thành `bytesPerBlock` và dùng `long`.

### Bài 2 — Đổi đơn vị

Provider trả `4096` từ `getBlockSize`. Hãy đổi sang KiB và kB.

**Đáp án:** `4096 / 1024 = 4 KiB`. `4096 / 1000 = 4.096 kB`. Không ghi `4 kB` nếu đang dùng tiền tố SI chính xác.

### Bài 3 — Một tệp dài một byte

`Files.size(file)==1`, `getBlockSize()==4096`. Phép tính mô hình số block là bao nhiêu? Có thể kết luận tệp đã được cấp phát 4096 byte vật lý không?

**Đáp án:** Theo mô hình `ceil(1/4096)=1` block, tương ứng 4096 byte mô hình. Nhưng **không thể kết luận phân bổ vật lý** chỉ từ hai con số vì cơ chế file system có thể khác.

### Bài 4 — Ranh giới block

Với block 4096 byte, tệp logic 4096 và 4097 byte lần lượt cần bao nhiêu block theo mô hình?

**Đáp án:** `1` và `2`. Chính một byte vượt biên khiến kết quả làm tròn tăng thêm một block.

### Bài 5 — Phân biệt file size và block size

`Files.size(path)==8192` và `store.getBlockSize()==4096`. Có phải `store.getTotalSpace()==8192` không?

**Đáp án:** Không. `Files.size` đo kích thước logic của tệp; `getTotalSpace` đo tổng dung lượng file store; `getBlockSize` đo bytes/block. Không có đẳng thức đó.

### Bài 6 — Provider không hỗ trợ

`getBlockSize` ném `UnsupportedOperationException`. Có nên đổi thành `0` và tiếp tục dùng `fileBytes / blockSize` không?

**Đáp án:** Không. Cần biểu diễn trạng thái **unsupported** hoặc bỏ tính năng tùy chọn. Nếu bắt buộc cần block size thì báo lỗi; không suy ra kích thước giả.

### Bài 7 — Overflow

Vì sao không nên tính `(fileBytes + blockBytes - 1) / blockBytes` với dữ liệu `long` bất kỳ?

**Đáp án:** Phép cộng có thể vượt `Long.MAX_VALUE` và tạo kết quả sai trước khi chia. Dùng `fileBytes/blockBytes + (fileBytes%blockBytes==0?0:1)` sau khi kiểm tra miền hợp lệ.

### Bài 8 — FileStore của thư mục đích

Muốn dự đoán đặc điểm nơi một tệp mới sẽ được tạo. Vì sao có thể kiểm tra `Files.getFileStore(destinationDirectory)` thay vì gọi trên một đường dẫn tệp chưa tồn tại?

**Đáp án:** Thư mục đích đã tồn tại thường có file store xác định. Tuy vậy, symlink, mount, provider và thay đổi cấu trúc filesystem vẫn cần xét. Không coi đó là hợp đồng tiên tri tuyệt đối cho mọi thao tác tạo tệp tương lai.

### Bài 9 — Sparse file

Tệp sparse có kích thước logic 1 GiB nhưng chỉ một số đoạn được ghi. Nếu block size là 4096, có thể suy ra số block vật lý đã cấp phát bằng `ceil(1GiB/4096)` không?

**Đáp án:** Không. Sparse holes có thể không được cấp phát theo dữ liệu logic. Cần cơ chế đo allocation riêng của filesystem/provider.

### Bài 10 — Buffer size

Javadoc cho biết block size 4096 byte. Có bắt buộc gọi `InputStream.read` với buffer 4096 byte mới đúng hoặc nhanh nhất không?

**Đáp án:** Không. Đây không phải yêu cầu API I/O và không đủ để kết luận tối ưu hiệu năng. Cần benchmark theo workload và biết tầng buffer/page cache/protocol.

### Bài 11 — Kiểm thử trên CI

Đội ngũ viết test `assertEquals(4096, store.getBlockSize())` trên máy CI. Test có portable không?

**Đáp án:** Không. Giá trị block size phụ thuộc file store/provider và có thể unsupported. Test tích hợp chỉ nên xác minh `>0` khi API hỗ trợ, còn test tính toán dùng fixture dương 4096 cố định.

### Bài 12 — Lỗi I/O khác với unsupported

Một hàm bắt `IOException` và in “unsupported block size”. Có đúng không?

**Đáp án:** Không. `IOException` nghĩa là lỗi truy vấn I/O; `UnsupportedOperationException` biểu thị phương thức không hỗ trợ. Cần phân loại đúng để debug và quyết định fallback.

### Bài 13 — Nhân số block với block size

`blocksFor(Long.MAX_VALUE,4096)` có thể trả số block toán học hợp lệ. Nếu nhân số block đó với 4096, có chắc vừa kiểu `long` không?

**Đáp án:** Không. Số byte làm tròn lên có thể vượt `Long.MAX_VALUE`. Dùng `Math.multiplyExact` để phát hiện overflow hoặc chọn cấu trúc số học lớn hơn khi thật sự cần.

## 13. Checklist review trước khi áp dụng vào dự án

- [ ] Dùng `Files.getFileStore(path)` đúng với file/directory liên quan.
- [ ] Nhớ `getBlockSize()` có từ Java 10 và còn hỗ trợ trên JDK hiện đại.
- [ ] Hiểu kết quả là **bytes per block**, kiểu `long` dương khi trả về bình thường.
- [ ] Không mặc định giá trị 4096 hay một bội số 1024.
- [ ] Không nhầm byte với KiB/kB, không dùng `int` cắt cụt giá trị.
- [ ] Bắt riêng `UnsupportedOperationException` và `IOException` khi thích hợp.
- [ ] Không biến unsupported thành 0 hoặc kích thước block không được xác minh.
- [ ] Không coi block size bằng file size, file allocation size hoặc usable space.
- [ ] Không dùng phép làm tròn số block như số byte cấp phát thật khi filesystem có sparse/compression/metadata.
- [ ] Dùng công thức thương/số dư, tránh `fileBytes + blockBytes - 1` overflow.
- [ ] Dùng `Math.multiplyExact` cho phép nhân dung lượng có nguy cơ tràn.
- [ ] Không chọn buffer size I/O chỉ vì block size bằng 4096.
- [ ] Không coi `getUsableSpace` bảo đảm ghi được một lượng byte cụ thể.
- [ ] Tách unit tests với fixture và integration tests với file store thực.
- [ ] Không hardcode tên ổ đĩa, loại filesystem hoặc số block trong CI.
- [ ] Chạy `FileStoreBlockLab.java` mặc định và so sánh đúng **12 dòng stdout**; chạy `--live` với output được phép thay đổi tùy provider.

## 14. Kết luận

`FileStore.getBlockSize()` là một API **Java 10 vẫn còn giá trị** để lấy **số byte trong một block của một file store**. Nó không cho biết số block của tệp, mức cấp phát vật lý, dung lượng còn trống hay kích thước buffer Java. Khi lập trình, hãy sử dụng `long`, ghi đúng đơn vị byte/KiB, xử lý `IOException` cùng `UnsupportedOperationException`, và chỉ dùng phép làm tròn kích thước logic như **mô hình tính toán minh họa**.

Trong chương trình đa nền tảng, việc **không hỗ trợ truy vấn block size** là một nhánh hợp lệ của API. Khi cần số liệu thực về allocation/quota/hiệu năng, hãy dùng các API/telemetry thích hợp của provider hoặc benchmark workload, thay vì suy đoán từ `getBlockSize`.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 API — FileStore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html): định nghĩa file store, `getBlockSize` (Since: 10), đơn vị byte/block, điều kiện trả về dương, `IOException` và `UnsupportedOperationException`.
- [Oracle Java SE 25 API — Files.getFileStore(Path)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): lấy FileStore cho một đường dẫn và lỗi I/O.
- [Oracle Java SE 25 API — Files.size(Path)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#size(java.nio.file.Path)): kích thước logic của tệp theo provider.
- [Oracle Java SE 25 API — FileSystem.getFileStores()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileSystem.html#getFileStores()): liệt kê các file store mà provider có thể cung cấp; không bắt buộc dùng cho trường hợp chỉ có một path.
- [Oracle Java SE 25 API — Math.multiplyExact(long,long)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): phát hiện tràn khi nhân các giá trị kiểu `long`.
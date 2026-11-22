# Giới hạn dùng kích thước khối để suy đoán dung lượng cấp phát với `FileStore` (Java 10+)

## 1. Mục tiêu bài học

Java 10 bổ sung phương thức **`FileStore.getBlockSize()`** trong `java.nio.file`. Phương thức này cho biết **số byte trên mỗi khối** mà file store báo cáo. Đây là thông tin hữu ích về đơn vị lưu trữ của hệ thống tệp, nhưng rất dễ bị sử dụng sai khi muốn trả lời câu hỏi:

> “Tệp có kích thước 1 byte, block size là 4.096 byte, vậy tệp chắc chắn chiếm chính xác 4.096 byte trên đĩa?”

**Không thể kết luận như vậy chỉ từ `getBlockSize()`.** Có thể xây dựng một **mô hình ước lượng làm tròn theo khối** trong điều kiện giả định đơn giản, nhưng Java không cam kết rằng kết quả ấy chính là **số byte đã cấp phát vật lý cho tệp**.

Bài này thuộc chủ đề **Thông tin FileStore**, tập trung vào **giới hạn của phép suy đoán dung lượng cấp phát từ kích thước khối**. Nội dung giúp bạn:

1. Hiểu `FileStore.getBlockSize()` từ Java 10 trả về gì, có thể thất bại như thế nào.
2. Phân biệt **kích thước logic của tệp**, **kích thước khối**, **ước lượng theo khối** và **dung lượng thực sự được cấp phát**.
3. Sử dụng công thức `ceil(fileSize / blockSize) × blockSize` **đúng như một mô hình có giả định**, không gán cho nó độ chính xác không tồn tại.
4. Giải thích tác động của **sparse files**, nén, lưu trữ nội tuyến, copy-on-write, deduplication, metadata, snapshot và loại hệ thống tệp.
5. Phân biệt các phương thức `FileStore.getTotalSpace()`, `getUsableSpace()` và `getUnallocatedSpace()` với thống kê riêng của một tệp.
6. Viết mã Java 17+ chạy được, có ví dụ tính toán kết quả cố định và phần thăm dò `FileStore` thực tế.
7. Thiết kế kiểm tra dung lượng theo nguyên tắc **best effort**, không hứa hẹn ghi thành công dựa vào những phép tính suy đoán.

**Phiên bản và phạm vi:** `FileStore.getBlockSize()` có từ **Java 10** và vẫn được dùng trong các JDK hiện đại. Ví dụ đầy đủ sử dụng **JDK 17+**, không cần API legacy hoặc tính năng preview.

## 2. `FileStore` là gì?

`FileStore` là biểu diễn trừu tượng của một vùng lưu trữ theo cách nhìn của `FileSystemProvider`. Tùy hệ thống, nó có thể tương ứng với phân vùng, volume, một file system hoặc một cơ chế lưu trữ khác do provider định nghĩa.

Ví dụ lấy `FileStore` của đường dẫn:

~~~java
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of(".");
FileStore store = Files.getFileStore(path);
~~~

Đây là **đoạn mã minh họa trong phương thức**, cần xử lý `IOException`. `Path.of(".")` trỏ đến thư mục làm việc hiện tại; nó không bắt buộc nằm trên một ổ đĩa vật lý riêng.

Những API liên quan:

| API | Ý nghĩa | Không nên suy ra |
| --- | --- | --- |
| `Files.getFileStore(path)` | Lấy file store gắn với đường dẫn do provider nhận diện | Mọi đường dẫn trên toàn hệ thống đều có cùng block size |
| `store.getBlockSize()` | Số byte trên một khối được file store báo cáo | Số byte vật lý chính xác của một tệp hoặc kích thước buffer Java bắt buộc |
| `store.getTotalSpace()` | Dung lượng tổng được file store báo cáo, tính theo byte | Một tệp có thể tự mình dùng toàn bộ mức ấy |
| `store.getUnallocatedSpace()` | Số byte chưa cấp phát ở cấp file store, mang tính thời điểm | Dung lượng khả dụng chắc chắn cho tài khoản hiện tại |
| `store.getUsableSpace()` | Số byte khả dụng với JVM hiện tại tại thời điểm kiểm tra, có tính gợi ý | Bảo đảm rằng một thao tác ghi tiếp theo sẽ thành công |
| `Files.size(path)` | Kích thước logic theo byte của tệp | Dung lượng chiếm trên thiết bị lưu trữ |
| `Files.readAttributes(path, BasicFileAttributes.class).size()` | Thuộc tính kích thước theo provider, tương tự kích thước logic với tệp thường | Một API đo số block thật được cấp phát |

Tài liệu `Files.size` và `BasicFileAttributes.size` nêu rõ kích thước logic **có thể khác với kích thước thực trên file system**, chẳng hạn do nén hoặc sparse files. Với đối tượng không phải regular file, ngữ nghĩa thuộc tính kích thước có thể tùy implementation.

## 3. `FileStore.getBlockSize()` thực sự cam kết điều gì?

Chữ ký:

~~~java
public long getBlockSize() throws IOException
~~~

Theo Java API:
- Trả về **một giá trị dương**, đơn vị **byte**, biểu diễn số byte trên mỗi block của file store.
- Có thể ném **`IOException`** khi không thể lấy thông tin do sự cố I/O.
- Có thể ném **`UnsupportedOperationException`** nếu provider không hỗ trợ.
- Phương thức có từ **Java 10**.
- Implementation mặc định được định nghĩa trong lớp `FileStore` ném `UnsupportedOperationException`; các provider phải thực hiện hỗ trợ riêng nếu muốn trả block size.

**Đặc điểm quan trọng:** `getBlockSize()` thuộc **file store**, không phải thuộc tính mô tả “số byte đã cấp phát cho tệp X”.

Ví dụ:

~~~java
FileStore store = Files.getFileStore(path);

try {
    long blockSize = store.getBlockSize();
    System.out.println("Block size: " + blockSize + " bytes");
} catch (UnsupportedOperationException ex) {
    System.out.println("Provider does not expose block size");
}
~~~

Đây là **đoạn minh họa**, cần có `Path path`, import `FileStore` và `Files`, và xử lý `IOException` ở phương thức bao ngoài. Giá trị in ra phụ thuộc hệ thống, vì vậy bài **không bịa một stdout cố định** cho phép gọi thực tế này.

### Block size có bắt buộc là 4.096 byte không?

Không. `4096` chỉ là con số giả định thường được dùng trong ví dụ học tập. Một file store cụ thể có thể báo kích thước khác, hoặc không hỗ trợ `getBlockSize()`.

Ngay cả khi provider báo `4096`:
- Không tự kết luận tệp 1 byte **chắc chắn** tốn đúng 4096 byte vật lý.
- Không tự suy ra mức tiêu thụ metadata.
- Không tự kết luận file system không có compression, sparse file, reflink hoặc lưu trữ nội tuyến.
- Không tự suy ra `FileChannel.write`, `Files.write` hoặc `BufferedOutputStream` chỉ có thể xử lý từng đoạn đúng 4096 byte. Quy định về đơn vị block ở tầng lưu trữ **không đồng nghĩa** API I/O buffer ở tầng ứng dụng phải dùng kích thước ấy.

Khi dùng direct I/O hoặc tính toán alignment đặc thù, phải dựa vào **hợp đồng API và hệ điều hành cụ thể**. Không sử dụng `getBlockSize()` làm quy tắc alignment phổ quát cho mọi Java I/O.

## 4. Phân biệt bốn khái niệm thường bị trộn lẫn

### 4.1. Kích thước logic (*logical file size*)

`Files.size(path)` cho biết kích thước tệp tính theo byte theo cách file system công bố. Ví dụ tệp thường có 5.000 byte dữ liệu, kích thước logic có thể là 5.000 byte.

Nó **không tự cho biết**:
- Có bao nhiêu byte/khối đã thực sự được cấp phát.
- Bao nhiêu khối được chia sẻ với bản sao khác.
- Có vùng thưa (*holes*) chưa cấp phát không.
- Dữ liệu có được nén hoặc lưu nội tuyến không.
- Metadata hay hệ thống snapshot có sử dụng thêm dung lượng không.

### 4.2. Kích thước block (*reported block size*)

`getBlockSize()` báo số byte trong một block theo file store. Nếu là 4096 byte, ta có thể dùng **4096** làm tham số cho **mô hình làm tròn giả định**. Con số đó không tự mô tả chiến lược cấp phát của từng tệp.

### 4.3. Kích thước làm tròn theo khối (*rounded model*)

Trong **một mô hình đơn giản** giả sử mọi byte dữ liệu phải chiếm các khối có kích thước cố định, mỗi tệp dùng khối riêng, không có nén, sparse, chia sẻ, lưu nội tuyến hoặc metadata:

\[
R(L,B)=\left\lceil\frac{L}{B}\right\rceil B
\]

Trong đó:
- `L` = logical length, số byte của tệp, `L >= 0`.
- `B` = block size giả định, `B > 0`.
- `R` = số byte dữ liệu **làm tròn theo mô hình**, không phải quan sát allocation thực tế.

Với `L=0`, mô hình trả `0`. Điều này **không có nghĩa** một tệp rỗng chắc chắn không làm hệ thống tệp dùng bất kỳ byte metadata nào.

### 4.4. Dung lượng được cấp phát (*allocated / disk usage*)

Đây là lượng dung lượng mà file system thực sự gán cho dữ liệu và có thể cho metadata, tùy phép đo cần thực hiện. Không có **một** phương thức Java SE `FileStore.getBlockSize()` nào trả trực tiếp lượng này cho một tệp.

Mức allocation thực còn chịu tác động của:
- Cách provider/file system tổ chức dữ liệu và metadata.
- Trạng thái extent, sparse regions và chiến lược delayed allocation.
- Nén, deduplication, copy-on-write, snapshot hoặc clone.
- Lưu trữ nội tuyến với tệp nhỏ và các tối ưu của file system.
- Việc một khối dữ liệu có được nhiều tên/đối tượng tệp dùng chung hay không.
- Thời điểm ghi, flush, quota, caching và các hoạt động đồng thời.

**Kết luận:** `L`, `B`, `R(L,B)` và allocation thực tế là các đại lượng **không được đánh đồng**.

## 5. Mô hình làm tròn theo khối: hữu ích nhưng có điều kiện

Giả sử **chỉ để minh họa**, block size `B = 4096` byte:

| Kích thước logic `L` | Số khối theo mô hình | `R(L,4096)` byte | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Không cấp khối dữ liệu trong mô hình; metadata vẫn có thể tồn tại |
| 1 | 1 | 4.096 | Làm tròn phần dữ liệu nhỏ hơn một khối |
| 4.095 | 1 | 4.096 | Vẫn nằm trong một khối |
| 4.096 | 1 | 4.096 | Bằng đúng một khối |
| 4.097 | 2 | 8.192 | Vượt một khối đúng một byte |
| 9.000 | 3 | 12.288 | Cần ba khối trong mô hình |

Với một tệp có `L=4097` byte:

~~~text
4097 / 4096 = 1 khối đầy + 1 byte dư

Theo mô hình:
  1 khối đầy + 1 khối cho phần dư = 2 khối
  2 × 4096 = 8192 byte
~~~

Đó là phép tính về **làm tròn dung lượng dữ liệu giả định**, không phải lời khẳng định ổ đĩa thật đang sử dụng chính xác 8192 byte.

### Hai tệp nhỏ và một tệp ghép

Với block size giả định 4096:
- Hai tệp riêng, mỗi tệp 1 byte: `4096 + 4096 = 8192` byte **trong mô hình**.
- Một tệp chứa chung 2 byte: `4096` byte **trong mô hình**.

Sự khác biệt mô hình giúp hiểu **internal fragmentation** khi không gian được cấp theo khối riêng biệt. Tuy nhiên:
- Một file system có thể lưu dữ liệu rất nhỏ theo cách khác.
- Các file có thể dùng chung block hoặc chia sẻ extent trong cơ chế đặc biệt.
- Metadata của **hai file** không nhất thiết bằng metadata của **một file**.
- Một kho lưu trữ object, hệ thống tệp mạng hoặc backend ảo hóa có thể có cách hạch toán khác hoàn toàn.

Vì vậy, không dùng ví dụ làm tròn để tuyên bố chắc chắn rằng **gộp hai file sẽ tiết kiệm đúng 4096 byte** trong mọi môi trường.

### Điều kiện sử dụng một ước lượng

Nếu bài toán chỉ yêu cầu **ước lượng giáo dục hoặc mô hình kế hoạch có giả định** và bạn biết cấu trúc cấp phát phù hợp, `R(L,B)` có thể giúp giải thích độ lệch do làm tròn. Nhưng hãy công bố rõ:
1. Đây là **mô hình giả định**, không phải số liệu đo.
2. Giá trị `B` lấy từ cấu hình hay `getBlockSize()`.
3. Những cơ chế file system đã bị **loại khỏi mô hình**.
4. Không dùng ước lượng đó làm **bảo đảm capacity/quota** hoặc cơ sở hạch toán chính xác.

## 6. Vì sao công thức làm tròn không phản ánh allocation thực tế?

### 6.1. Sparse file: logical size lớn, dữ liệu thực có thể ít

Một **sparse file** có những vùng logic chưa thực sự được lưu bằng block dữ liệu vật lý. Chương trình có thể thấy độ dài logic rất lớn, nhưng nhiều đoạn chưa được cấp phát khối theo cách thông thường.

Ví dụ về ý tưởng:

~~~text
Logical file length: 1 GiB
Một số vùng có dữ liệu; nhiều vùng là lỗ thưa (holes).
Dung lượng thực được cấp phát có thể thấp hơn nhiều so với 1 GiB.
~~~

**Không suy ra chính xác số byte cấp phát từ ví dụ này.** Mức tiết kiệm phụ thuộc file system, cách tạo tệp và thao tác ghi. `Files.size(path)` phản ánh chiều dài logic, không phải bản đồ extent.

### 6.2. Nén dữ liệu: kích thước logic không bằng byte sau nén

Một file system có thể nén dữ liệu trước khi lưu. Một tệp chứa các byte lặp lại có thể có kích thước logic rất lớn nhưng số byte thực được cấp phát ít hơn mô hình không nén.

Ngược lại, metadata hoặc cơ chế lưu trữ bổ sung vẫn có thể tạo overhead. `getBlockSize()` **không cho biết tỉ lệ nén** hoặc lượng byte sau nén.

### 6.3. Copy-on-write, reflink và deduplication

Một số hệ thống cho phép nhiều bản sao logic **chia sẻ chung các extent hoặc block**. Hai tệp nhìn riêng có cùng kích thước logic, nhưng byte thực phải cấp thêm cho bản sao thứ hai có thể thấp hơn so với việc sao chép toàn bộ dữ liệu.

Khi một bản sao được sửa, copy-on-write có thể dẫn đến cấp phát thêm. Vì vậy:
- Không cộng đơn giản `R(L,B)` của mọi tệp rồi coi đó là lượng dung lượng vật lý duy nhất.
- Không cố phân bổ “mỗi block vật lý thuộc riêng đúng một file” nếu file system có chia sẻ.
- Không xem chênh lệch giữa hai lần đọc dung lượng rảnh là một phép đo riêng tư hoàn hảo cho tệp vừa copy.

### 6.4. Inline data, metadata và chi phí cấu trúc

Một số file system có thể lưu dữ liệu nhỏ **nội tuyến trong metadata** thay vì cấp một data block thông thường. Ngược lại, một tệp còn có thể cần các cấu trúc metadata, extent tree, index, ACL hoặc thông tin quản lý khác.

Mô hình `ceil(L/B) × B`:
- Có thể **ước lượng cao hơn** dung lượng data block thực trong cơ chế inline/sparse/nén.
- Có thể **ước lượng thấp hơn** khi tính toàn bộ footprint bao gồm metadata/overhead.
- Không chỉ ra cách hạch toán block dùng chung và snapshot.

### 6.5. Delayed allocation và các thời điểm quan sát

Một số hệ thống trì hoãn quyết định cấp phát vật lý đến khi dữ liệu được đẩy xuống tầng lưu trữ. Ngay sau `write`, thống kê có thể chưa phản ánh cách cấp phát cuối cùng.

Dữ liệu có thể bị thay đổi bởi các luồng khác, tiến trình khác hoặc hoạt động nền. Cho nên việc đọc thông số ở hai thời điểm gần nhau **không mặc nhiên phản ánh chỉ một phép ghi** mà chương trình thực hiện.

### 6.6. Provider trừu tượng, ổ đĩa mạng và cloud

`FileStore` là một abstraction của Java NIO. Đối với file system mạng, container, mount ảo hoặc provider tùy chỉnh, cách báo block size và hạch toán dung lượng có thể khác so với cách người học hình dung về ổ đĩa vật lý.

Nếu provider không hỗ trợ `getBlockSize()`, phương thức có thể ném `UnsupportedOperationException`. **Không tự thay bằng 4096 rồi tuyên bố đó là kích thước khối thật.**

## 7. Chương trình Java 17+ hoàn chỉnh: mô hình và thông tin FileStore

Chương trình sau tách **hai việc**:
- Phép tính giả định với block size cố định `4096` để stdout **tái lập được**.
- Phép tra cứu `FileStore` thực nếu truyền thêm một `Path`, với kết quả **phụ thuộc hệ thống**; không trộn nó vào kết quả chuẩn.

Tạo tệp **FileStoreAllocationLimitsDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileStoreAllocationLimitsDemo {

    // Đây là số byte làm tròn THEO MÔ HÌNH, không phải disk usage.
    static long roundedModel(long logicalBytes, long blockBytes) {
        if (logicalBytes < 0 || blockBytes <= 0) {
            throw new IllegalArgumentException(
                    "logicalBytes >= 0 and blockBytes > 0 required");
        }

        long fullBlocks = logicalBytes / blockBytes;
        long remainder = logicalBytes % blockBytes;
        long blockCount = fullBlocks;

        if (remainder != 0) {
            blockCount = Math.addExact(blockCount, 1);
        }

        // Bắt ArithmeticException nếu kết quả vượt phạm vi long.
        return Math.multiplyExact(blockCount, blockBytes);
    }

    static void inspectRealStore(Path path) throws IOException {
        FileStore store = Files.getFileStore(path);

        System.out.println("=== FileStore report (environment-dependent) ===");
        System.out.println("store name = " + store.name());
        System.out.println("store type = " + store.type());
        System.out.println("read-only = " + store.isReadOnly());

        try {
            long block = store.getBlockSize();
            System.out.println("reported block bytes = " + block);
        } catch (UnsupportedOperationException ex) {
            System.out.println("reported block bytes = unsupported");
        }

        System.out.println("total store bytes = " + store.getTotalSpace());
        System.out.println("usable store bytes (hint) = "
                + store.getUsableSpace());
        System.out.println("unallocated store bytes (hint) = "
                + store.getUnallocatedSpace());

        if (Files.isRegularFile(path)) {
            System.out.println("logical file bytes = " + Files.size(path));
        } else {
            System.out.println("logical file bytes = not a regular file");
        }

        System.out.println("per-file allocated bytes = not measured");
    }

    public static void main(String[] args) throws IOException {
        long assumedBlockSize = 4096;
        long[] logicalSizes = {0, 1, 4096, 4097, 9000};

        System.out.println("=== Illustrative rounding model ===");
        System.out.println("assumed block bytes = " + assumedBlockSize);

        long total = 0;
        for (long logical : logicalSizes) {
            long rounded = roundedModel(logical, assumedBlockSize);
            System.out.println("model(" + logical + ") = " + rounded);
            total = Math.addExact(total, rounded);
        }

        System.out.println("sum of model values = " + total);

        long twoFiles = Math.addExact(
                roundedModel(1, assumedBlockSize),
                roundedModel(1, assumedBlockSize));

        long oneFile = roundedModel(2, assumedBlockSize);

        System.out.println("two 1-byte files model = " + twoFiles);
        System.out.println("one 2-byte file model = " + oneFile);

        // Tùy chọn: chỉ khi có đối số Path.
        if (args.length > 0) {
            inspectRealStore(Path.of(args[0]));
        }
    }
}
~~~

Biên dịch và chạy mô hình bằng **JDK 17 trở lên**:

~~~bash
javac FileStoreAllocationLimitsDemo.java
java FileStoreAllocationLimitsDemo
~~~

**Đầu ra chính xác khi KHÔNG truyền đối số:**

~~~text
=== Illustrative rounding model ===
assumed block bytes = 4096
model(0) = 0
model(1) = 4096
model(4096) = 4096
model(4097) = 8192
model(9000) = 12288
sum of model values = 28672
two 1-byte files model = 8192
one 2-byte file model = 4096
~~~

Để thử đọc thông số thực của thư mục làm việc hiện tại:

~~~bash
java FileStoreAllocationLimitsDemo .
~~~

**Kết quả của lệnh có đối số `.` thay đổi theo hệ điều hành, file system, mount, quota và provider.** Nó sẽ in thông tin như tên/type store, block size nếu được hỗ trợ, tổng/usable/unallocated space và nhận định rằng lượng byte cấp phát **cho từng tệp** chưa được đo. Không có một bảng số chính xác hợp lệ cho mọi máy.

Nếu provider không hỗ trợ `getBlockSize()`, chương trình in thông báo `unsupported` thay vì giả định 4096. Nếu phép lấy `FileStore` hoặc đọc dung lượng phát sinh `IOException`, chương trình để lỗi truyền ra theo khai báo `throws IOException`.

### Giải thích mã và ý nghĩa phép tính

1. `roundedModel` kiểm tra `logicalBytes >= 0`, `blockBytes > 0`. Hai điều kiện này tránh kích thước vô nghĩa và chia cho 0.
2. Thay vì dùng ngay `(logicalBytes + blockBytes - 1) / blockBytes` (có thể **tràn `long`** khi cộng), hàm tính thương và số dư, cộng thêm một khối khi có dư.
3. `Math.addExact` và `Math.multiplyExact` phát hiện phép tính vượt phạm vi số nguyên `long`, thay vì âm thầm nhận giá trị sai.
4. Với `B=4096`, file logic 1 byte được mô hình hóa thành 4096 byte dữ liệu; 4097 byte thành 8192 byte.
5. Tổng `28672` là **tổng số byte theo mô hình** cho năm độ dài đã cho, không phải lượng byte đã được cấp phát cho năm tệp thật.
6. `Files.getFileStore(path)` nhận diện store của đường dẫn, không tự cấp phát byte hay tạo tệp.
7. `FileStore.getBlockSize()` có thể được hỗ trợ hoặc không. `getTotalSpace`, `getUsableSpace`, `getUnallocatedSpace` phản ánh thông số ở **cấp store**, không trả allocation riêng của tệp.
8. `Files.isRegularFile(path)` là bước kiểm tra loại file để tránh dùng kích thước các đối tượng đặc biệt như một con số có nghĩa chung. Lời gọi này là phép kiểm tra theo thời điểm; đường dẫn có thể bị thay đổi đồng thời.
9. Câu cuối `per-file allocated bytes = not measured` cố ý khẳng định ranh giới: chương trình **không đo allocation vật lý** bằng mô hình làm tròn.

**Tính portable:** ví dụ không yêu cầu quyền ghi vào ổ đĩa, không tạo file lớn và không giả định hệ thống có sparse file hoặc provider hỗ trợ một thuộc tính hệ điều hành riêng.

## 8. Lỗi số học khi ước lượng từ block size

Công thức đơn giản thường gặp:

~~~java
long rounded = ((size + blockSize - 1) / blockSize) * blockSize;
~~~

Đây là **đoạn minh họa**, không phải lời khuyên dùng trực tiếp cho mọi `long`. Nó dễ sai theo hai hướng:

1. Nếu `size + blockSize - 1` vượt `Long.MAX_VALUE`, phép cộng có thể **tràn số** trước phép chia.
2. Nếu `blockSize <= 0`, phép tính có thể sai hoặc chia cho 0.
3. Ngay cả khi số học không tràn, kết quả vẫn chỉ là **rounded model**.

Một cách an toàn về tràn số cho `long` không âm:

~~~java
static long roundUpAssumingBlocks(long size, long blockSize) {
    if (size < 0 || blockSize <= 0) {
        throw new IllegalArgumentException();
    }

    long count = size / blockSize;
    if (size % blockSize != 0) {
        count = Math.addExact(count, 1);
    }

    return Math.multiplyExact(count, blockSize);
}
~~~

`Math.multiplyExact` ném `ArithmeticException` nếu kết quả làm tròn thực sự **không biểu diễn được bằng `long`**. Đây là hướng xử lý tốt hơn việc trả ra một số âm như thể nó là số byte hợp lệ.

**Vẫn không phải số byte thực tế của tệp.** Bài học chủ yếu là diễn đạt đúng **giả định**, rồi mới quan tâm đến việc tính toán an toàn.

### Khi cộng mô hình của nhiều tệp

Với một danh sách độ dài file, có thể tổng các `roundUpAssumingBlocks`. Nhưng điều đó chỉ có ý nghĩa nếu:
- Mỗi file được mô hình hóa là dùng khối riêng.
- Các file không chia sẻ extent.
- Các file không bị nén hoặc cấp phát sparse.
- Không có metadata hoặc các chi phí khác trong số đo cần trả lời.

Đối với hệ thống hỗ trợ hard link, copy-on-write hoặc deduplication, “cộng dung lượng của từng file” còn gặp câu hỏi **đếm block dùng chung thế nào**. Hệ thống quản lý phải có chính sách kế toán rõ ràng, thay vì coi phép cộng này là một đại lượng vật lý duy nhất.

## 9. Vì sao `getUsableSpace()` không xác nhận được công thức?

Một người học có thể thử:

~~~java
long before = store.getUsableSpace();

// Ghi một tệp vào file store...

long after = store.getUsableSpace();
long delta = before - after;
~~~

Đây là đoạn **minh họa không độc lập**: biến `store` phải được khai báo và thao tác ghi tệp phải được xác định.

Sai lầm là coi `delta` luôn bằng **allocation byte của tệp vừa tạo**.

Những nguyên nhân khiến chênh lệch không đáng tin tuyệt đối:
- Tiến trình khác cũng có thể ghi hoặc xóa dữ liệu giữa hai lần đo.
- Có thể có quota, reserved space hoặc chính sách quyền của hệ thống.
- File system có cơ chế cache/delayed allocation hoặc snapshot.
- Việc tạo tệp có thể thêm metadata riêng.
- Một file mới có thể dùng các block được chia sẻ hoặc nén.
- Các lời gọi về free/usable space chỉ phản ánh **ảnh chụp tại thời điểm gọi**.

Theo Java API, `getUsableSpace()` và `getUnallocatedSpace()` mang tính **gợi ý**, không bảo đảm rằng bạn có thể sử dụng phần lớn hoặc toàn bộ các byte được báo cáo; thông số có thể nhanh chóng mất chính xác khi I/O bên ngoài thay đổi hệ thống.

**Không nên dùng `getUsableSpace()` như một lời hứa “ghi được N byte chắc chắn thành công”.** Một thao tác ghi thực vẫn có thể thất bại vì quota, quyền, dung lượng, cấu hình hay lỗi I/O khác.

### Phân biệt ba loại câu hỏi về dung lượng

| Câu hỏi | Thông tin nên xem | Giới hạn |
| --- | --- | --- |
| “Tệp có bao nhiêu byte logic?” | `Files.size(path)` với regular file | Không cho biết byte thực cấp phát |
| “Store báo một block có bao nhiêu byte?” | `Files.getFileStore(path).getBlockSize()` | Có thể không hỗ trợ; không là allocation per-file |
| “JVM hiện có thể sử dụng khoảng bao nhiêu dung lượng?” | `getUsableSpace()` | Chỉ là hint ở một thời điểm; không đảm bảo ghi thành công |
| “Tổng dung lượng store là bao nhiêu?” | `getTotalSpace()` | Không phải kích thước một file |
| “Có bao nhiêu byte chưa cấp phát trên store?” | `getUnallocatedSpace()` | Không đồng nghĩa còn có thể ghi toàn bộ dưới mọi quota/quyền |
| “Tệp X thực sự chiếm bao nhiêu byte?” | API/thuộc tính hoặc công cụ chuyên biệt của filesystem | Không được Java SE bảo đảm bằng `getBlockSize` + `Files.size` |

## 10. Muốn đo dung lượng cấp phát thật thì làm thế nào?

**Bắt đầu bằng cách xác định chính xác câu hỏi:**
- Bạn muốn **logical bytes** của một file?
- Muốn **data blocks allocated** của file đó?
- Muốn tính cả **metadata**?
- Muốn **bytes charged to a quota**?
- Muốn **marginal cost** khi copy hoặc xóa file?
- Muốn biết dung lượng **còn có thể ghi** cho một tài khoản?

Những đại lượng này không nhất thiết trùng nhau.

### 10.1. Dùng API/thuộc tính đặc thù file system khi cần

Một số hệ điều hành/file system cung cấp thống kê block cấp phát hoặc độ dài vật lý qua các API ngoài Java SE. Ví dụ hệ thống dạng Unix có thể cung cấp thống kê block trong kết quả file status, và một số công cụ hệ điều hành hiển thị **allocated size** khác với logical size.

Tuy nhiên:
- Không có một thuộc tính **portable được cam kết trên mọi `FileSystemProvider`** trong Java SE chỉ bằng `FileStore.getBlockSize`.
- Tên attribute, đơn vị tính, hành vi với symbolic link và quyền truy cập có thể khác nhau.
- Nếu block/extent được chia sẻ, số liệu per-file có thể không biểu thị đúng **dung lượng tăng thêm do file**.
- Đối với cloud/network storage, dữ liệu ghi nợ theo quota/billing có thể khác thống kê lưu trữ tại một thời điểm.

Nếu cần số liệu đáng tin cho hệ thống cụ thể, hãy chọn API thống kê được file system/provider đó hỗ trợ, ghi rõ đơn vị tính và kiểm thử trên **đúng môi trường triển khai**. Tránh sử dụng tên attribute “unix” hoặc lệnh shell của một hệ điều hành rồi coi đó là chuẩn chung của Java.

### 10.2. Đo mức thay đổi của một workload có kiểm soát

Trong một môi trường thử nghiệm được cô lập, có thể đo các chỉ số cấp file store trước/sau một workload và so sánh với dữ liệu đo từ OS. Nhưng vẫn phải ghi rõ:
- Mức đo theo thời điểm, có thể có tác động từ tiến trình ngoài và hoạt động nền.
- Workload có thể tạo cả metadata.
- Số liệu có thể phụ thuộc nén, snapshot, quota, flush và thời điểm đồng bộ.
- Kết quả không tự động áp dụng sang một file system khác.

Đây là **phương pháp thử nghiệm phục vụ đánh giá**, không phải thuật toán xác định allocation chính xác chỉ từ `getBlockSize`.

### 10.3. Đối với bài toán giới hạn dung lượng/quota

Nếu phải giới hạn tổng dữ liệu do ứng dụng nhận:
1. Dùng **kích thước logic** hoặc **tổng số byte được chấp nhận** làm chỉ số nghiệp vụ khi chính sách nói về upload/download size.
2. Với quota của hệ thống lưu trữ, dựa vào API quota hoặc thống kê thực tế của backend, không tự thay thế bằng `ceil(L/B) × B`.
3. Kiểm tra điều kiện trước thao tác ghi nếu hữu ích, **nhưng vẫn xử lý lỗi tại chính thao tác ghi**.
4. Không hứa hẹn dung lượng trống tồn tại cho tới lúc ghi xong; có thể bị thay đổi đồng thời.

## 11. Block size có giúp tối ưu I/O không?

**Có thể là một tín hiệu**, nhưng cần đặt đúng bối cảnh.

Giả sử `getBlockSize()` báo 4096 byte. Điều này **không yêu cầu** mọi lần gọi:

~~~java
Files.write(path, bytes);
~~~

hoặc

~~~java
channel.write(buffer);
~~~

phải có `bytes.length` hay `buffer.remaining()` là bội của 4096. Những ví dụ chỉ là lời gọi minh họa với biến `path`, `bytes`, `channel`, `buffer` đã được khai báo; API Java I/O thông thường có hợp đồng riêng về lượng dữ liệu đọc/ghi.

Một số ngữ cảnh direct I/O đặc thù có các ràng buộc alignment của hệ điều hành/provider. **Không suy ra các ràng buộc đó cho tất cả các `FileChannel` từ mỗi giá trị `getBlockSize()`**.

Để tối ưu thực tế:
- Dùng buffer theo nhu cầu của ứng dụng và API đang dùng.
- Benchmark với loại file, kích thước dữ liệu và môi trường triển khai thực.
- Đừng giả định buffer bằng đúng block size luôn nhanh nhất.
- Phân biệt **kích thước file system block**, **page cache**, **sector/physical device**, **I/O request size** và **application buffer**.

Chủ đề của bài vẫn là **giới hạn suy đoán allocation**; tối ưu I/O là một ứng dụng phụ cần kiểm chứng độc lập.

## 12. Các lỗi và hiểu lầm phổ biến

### Lỗi 1 — “FileStore báo 4096 thì file 1 byte chắc chắn chiếm 4096 byte”

Không thể kết luận chắc chắn. `4096` là block size được báo cáo, không phải thống kê allocation riêng của file. Sparse/nén/inline/shared blocks/metadata có thể làm số thực khác.

### Lỗi 2 — “`Files.size(file)` là số byte trên đĩa”

Không. Nó mô tả kích thước logic. Java API nêu rõ kích thước có thể khác kích thước thực trên file system khi có nén, sparse file hoặc những lý do khác.

### Lỗi 3 — “Cứ lấy `ceil(Files.size/B) × B` là được kết quả chính xác”

Chỉ đúng **trong mô hình đã giả định**. Không có cam kết Java SE rằng mọi provider dùng block size báo cáo làm đơn vị cấp phát riêng cho mọi byte dữ liệu của từng tệp.

### Lỗi 4 — “Kết quả 0 byte theo mô hình nghĩa là tạo tệp rỗng không tốn bộ nhớ”

Không. Mô hình chỉ tính data blocks theo độ dài logic. Một tệp rỗng vẫn có thể cần metadata và các cấu trúc quản lý khác.

### Lỗi 5 — “`getBlockSize()` luôn hỗ trợ trên mọi FileStore”

Không. Phương thức có thể ném `UnsupportedOperationException`. Code production cần xử lý trường hợp không có thông tin.

### Lỗi 6 — “Nếu không hỗ trợ thì mặc định 4096”

Một giả định tùy ý có thể hữu ích **chỉ khi được ghi rõ là giả định của mô hình**. Không được báo “measured block size = 4096” khi provider không trả được thông tin.

### Lỗi 7 — “`getUsableSpace()` là dung lượng còn chắc chắn có thể ghi”

Không. Đây là thông tin gợi ý và có thể thay đổi ngay sau phép đọc; chính thao tác ghi vẫn có thể thất bại.

### Lỗi 8 — “Hiệu hai lần đo usable space là allocation của một tệp”

Không nhất thiết. Nó có thể chịu ảnh hưởng bởi metadata, những tiến trình khác, quota, caching, snapshot hoặc cơ chế chia sẻ dữ liệu.

### Lỗi 9 — “Hai file mỗi file 1 byte luôn tiêu tốn gấp đôi một file 2 byte”

Đó chỉ là kết quả của mô hình dùng block riêng. Các hệ thống tệp hiện đại có thể có chiến lược cấp phát khác; metadata và chia sẻ extent còn làm cách hạch toán phức tạp hơn.

### Lỗi 10 — “Kết quả làm tròn không thể tràn vì FileStore dùng `long`”

Có thể tràn `long` khi cộng `blockSize-1` hoặc nhân số khối với kích thước khối. Dùng số học có kiểm tra overflow và xác thực đầu vào.

### Lỗi 11 — “Kích thước block quyết định bộ đệm I/O bắt buộc”

Không với I/O buffered thông thường. Block size của file store không phải đồng nghĩa kích thước buffer API, page cache hoặc mọi ràng buộc alignment.

### Lỗi 12 — “Đo đúng trên máy phát triển là đúng trên production”

Không. Provider, file system, storage virtualization, nén, quota và hệ điều hành có thể khác; cần xác thực trong môi trường thực tế.

## 13. Checklist trước khi dùng `getBlockSize()` trong một hệ thống

1. **Mục đích số liệu là gì?** Thống kê block size, ước lượng mô hình, giới hạn upload hay đo allocated bytes thực?
2. **FileStore nào đang được hỏi?** Lấy từ đúng `Path`; đừng giả định mọi mount đều giống nhau.
3. **Provider có hỗ trợ `getBlockSize()` không?** Xử lý `UnsupportedOperationException`, `IOException`.
4. **Đơn vị đang dùng là byte hay block?** Không trộn MB/MiB, byte và số block.
5. **Đã phân biệt logical vs allocated chưa?** `Files.size` không phải allocated bytes.
6. **Nếu áp dụng làm tròn, giả định nào được công bố?** Khối cố định, không sparse, không nén, không shared extent, không metadata?
7. **Có dữ liệu sparse/compressed/reflink không?** Nếu có, mô hình làm tròn có thể sai đáng kể.
8. **Có tính metadata và quota không?** Đừng bỏ qua nếu mục tiêu là billing hoặc năng lực ghi.
9. **Có nhiều tiến trình cùng sử dụng store không?** Free/usable space là thông tin theo thời điểm, không phải bảo đảm.
10. **Có thể tràn `long` không?** Sử dụng `Math.addExact`, `Math.multiplyExact` khi cần.
11. **Nếu cần chính xác, có nguồn đo thích hợp không?** Dùng API/công cụ được file system hỗ trợ, không gắn nhãn đo cho phép suy đoán.
12. **Đã kiểm thử trên đúng hệ thống triển khai chưa?** Đặc biệt với cloud, container, mount mạng và provider tùy chỉnh.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `FileStore.getBlockSize()` có từ Java phiên bản nào?

**Đáp án:** Java 10. Nó trả số byte trên mỗi block do file store báo cáo, hoặc có thể không hỗ trợ theo provider.

**Câu 2.** Nếu `getBlockSize()` trả 4096, có thể kết luận file 1 byte chắc chắn chiếm đúng 4096 byte vật lý không?

**Đáp án:** Không. Đó có thể là kết quả mô hình đơn giản, nhưng actual allocation phụ thuộc file system, metadata và các cơ chế như sparse/inline/compression.

**Câu 3.** Vì sao `Files.size(path)` có thể khác dung lượng thật đã cấp phát?

**Đáp án:** `Files.size` trả kích thước logic; sparse file, compression và cơ chế lưu trữ khác có thể khiến số byte thực khác.

**Câu 4.** Với mô hình `B=4096`, `L=4097`, phép làm tròn trả bao nhiêu?

**Đáp án:** `8192` byte (hai block theo mô hình), **không phải kết quả đo đĩa thật**.

**Câu 5.** Với mô hình `B=4096`, `L=0`, kết quả là bao nhiêu và có nghĩa file không tốn storage không?

**Đáp án:** Mô hình trả `0` byte data block. Không suy ra metadata của file là 0.

**Câu 6.** Sparse file có thể khiến logical size và allocated bytes lệch như thế nào?

**Đáp án:** File có chiều dài logic lớn nhưng các vùng chưa cấp phát có thể khiến dung lượng vật lý nhỏ hơn nhiều so với chiều dài logic.

**Câu 7.** Vì sao `getUsableSpace()` không bảo đảm một file mới có thể ghi đầy đủ?

**Đáp án:** Đây là hint tại một thời điểm. Quota, quyền, I/O đồng thời và các vấn đề thực tế có thể khiến thao tác ghi thất bại.

**Câu 8.** Nếu `getBlockSize()` ném `UnsupportedOperationException`, có thể báo 4096 là block size đo được không?

**Đáp án:** Không. Có thể chọn một giả định số học được ghi rõ, nhưng không được trình bày nó như thông số do provider trả về.

**Câu 9.** Tại sao tổng `R(L,B)` cho nhiều file không nhất thiết bằng dung lượng lưu trữ tăng thêm?

**Đáp án:** Nó bỏ qua nén, sparse, metadata, khối dùng chung, snapshots và các chính sách cấp phát của file system.

**Câu 10.** `FileStore.getBlockSize()` có buộc mọi `FileChannel.write` gửi đúng bội số khối không?

**Đáp án:** Không theo hợp đồng I/O Java thông thường. Direct I/O hoặc cơ chế đặc thù có yêu cầu riêng, không thể suy ra trực tiếp cho tất cả `FileChannel`.

**Câu 11.** Nếu cần giới hạn upload 100 MiB, nên dùng block size để tính độ dài upload không?

**Đáp án:** Thông thường không. Giới hạn về lượng dữ liệu nên dựa trên **byte logic thực sự được nhận**; giới hạn storage/quota phải dùng số liệu từ hệ thống lưu trữ theo hợp đồng riêng.

**Câu 12.** Hai lần đọc `getUsableSpace()` trước/sau ghi có đo chính xác allocation của file vừa tạo không?

**Đáp án:** Không bảo đảm. Các hoạt động đồng thời, metadata, quota, caching và cơ chế lưu trữ có thể làm số chênh lệch khác per-file allocation.

## 15. Ghi nhớ cuối bài

1. **`FileStore.getBlockSize()` (Java 10+)** báo số byte trên mỗi block của file store; có thể không hỗ trợ hoặc phát sinh lỗi I/O.
2. **`Files.size(path)` là kích thước logic**, không phải dung lượng vật lý được cấp phát cho file.
3. **`ceil(L/B) × B` là mô hình ước lượng với giả định**, không phải thuật toán chuẩn xác của Java để đo allocation.
4. Sparse files, nén, inline storage, metadata, reflink/copy-on-write, deduplication và snapshot có thể khiến dung lượng thực khác mô hình theo nhiều hướng.
5. **Thông tin space ở cấp FileStore là số liệu tổng hợp và có tính thời điểm**; `getUsableSpace()` không bảo đảm thao tác ghi sau đó thành công.
6. **Nếu cần đo allocation thật**, dùng các phép đo được file system/provider hỗ trợ và xác định chính xác cách hạch toán; không suy ra nó chỉ từ block size.
7. **Không trộn kiến thức về block allocation với buffer/alignment I/O**, và không dựa vào việc “4096 là mặc định mọi nơi”.
8. Với code tính ước lượng, bảo vệ đầu vào và **tràn `long`**, đồng thời ghi nhãn rõ kết quả là `model`, `estimate` hay `measured`.

**Tài liệu chính thức và còn áp dụng:**
- [Oracle Java SE 17 — `FileStore.getBlockSize()`, `getUsableSpace()`, `getUnallocatedSpace()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html).
- [Oracle Java SE 10 — `FileStore`, phương thức `getBlockSize()` có từ Java 10](https://docs.oracle.com/javase/10/docs/api/java/nio/file/FileStore.html).
- [Oracle Java SE 17 — `Files.size(Path)` và `Files.getFileStore(Path)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [Oracle Java SE 17 — `BasicFileAttributes.size()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).

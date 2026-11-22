# Phân biệt dung lượng tổng, dung lượng trống và dung lượng sử dụng được của `FileStore` (Java hiện đại)

## 1. Vấn đề: ba con số giống nhau về đơn vị nhưng khác về ý nghĩa

Khi triển khai tính năng upload, xuất báo cáo, sao lưu, ghi log hoặc lưu tệp trong Java, chúng ta thường muốn biết “ổ đĩa còn bao nhiêu dung lượng?”. Câu hỏi này thực tế có **ít nhất ba ý nghĩa khác nhau**:

1. **Tổng dung lượng kho lưu trữ**: kho lưu trữ đang có quy mô bao nhiêu?
2. **Dung lượng chưa được phân bổ (trống)**: có bao nhiêu byte chưa được cấp phát trong kho?
3. **Dung lượng sử dụng được đối với JVM**: JVM đang chạy được báo là có thể sử dụng bao nhiêu byte để ghi dữ liệu mới?

Java NIO.2 cung cấp `java.nio.file.FileStore` và ba phương thức tương ứng:

```java
long total       = store.getTotalSpace();
long unallocated = store.getUnallocatedSpace();
long usable      = store.getUsableSpace();
```

Đây là đoạn minh họa trong phương thức đã có biến `FileStore store` và xử lý `IOException`. **Cả ba trả số byte dưới dạng `long`**, nhưng không được dùng lẫn nhau.

Ví dụ giả định, **không phải số liệu thực từ máy người học**:

| Chỉ số | Dung lượng giả định | Ý nghĩa |
| --- | ---: | --- |
| `getTotalSpace()` | 100 GiB | Quy mô file store |
| `getUnallocatedSpace()` | 40 GiB | Byte chưa được phân bổ theo file store |
| `getUsableSpace()` | 25 GiB | Byte hiện được báo có thể dùng bởi JVM |
| `total - unallocated` | 60 GiB | **Ước tính** phần đã phân bổ |
| `unallocated - usable` | 15 GiB | Phần chênh giữa chưa phân bổ và khả dụng cho JVM tại thời điểm đo |

Trong ví dụ, **40 GiB trống không đồng nghĩa JVM ghi được 40 GiB**. Một phần dung lượng có thể chịu các giới hạn truy cập, mức dành riêng cho hệ thống, quota hoặc các ràng buộc của file-system provider. Cũng không được gán chắc chắn toàn bộ **15 GiB chênh lệch** cho một nguyên nhân duy nhất khi chưa có thông tin hệ thống file.

**Ghi nhớ quan trọng:** `getUsableSpace()` trả về **gợi ý tại thời điểm kiểm tra**, **không bảo đảm** thao tác ghi kế tiếp sẽ thành công.

### Vị trí trong Java 10

`FileStore` và ba phép đo dung lượng trên đã có từ **Java 7** (NIO.2), **không phải** API mới được giới thiệu riêng trong Java 10. Trong Java 10, `FileStore` được bổ sung `getBlockSize()`; ba phương thức `getTotalSpace`, `getUnallocatedSpace` và `getUsableSpace` vẫn còn hiệu lực trong Java hiện đại. Bài học dùng ngữ nghĩa hiện hành, không trình bày đây là tính năng mới chỉ xuất hiện ở Java 10.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa chính xác của ba chỉ số FileStore.
- Lấy đúng file store từ một `Path` bằng `Files.getFileStore(path)`.
- Tính **ước lượng** dung lượng đã phân bổ bằng `total - unallocated` và hiểu giới hạn của phép tính.
- Phân biệt phần chưa cấp phát và phần khả dụng cho JVM, bao gồm trường hợp bị quota/quyền/không gian dự trữ hạn chế.
- Biết vì sao `getUsableSpace()` không thể thay thế việc xử lý `IOException` khi ghi tệp.
- Hiểu các số được đo **không nhất thiết cùng một thời điểm**, không tạo snapshot nguyên tử.
- Đổi byte sang GiB/GB, tính phần trăm và tránh lỗi `int`, phép chia nguyên, tràn số.
- Dùng `FileStore.isReadOnly()` đúng phạm vi mà không cho rằng `false` bảo đảm ghi được tệp.
- Không nhầm dung lượng file store với `Files.size(file)`, RAM hoặc Java heap.
- Viết chương trình Java 17+ gồm phần **mô phỏng có stdout xác định** và phần **đọc hệ thống thật tùy chọn**.
- Thiết kế kiểm tra trước upload/sao lưu theo hướng dự báo, vẫn xử lý lỗi I/O thực tế.
- Biết khi nào con số có thể khác do mount point, quota, mạng, cloud và file-system provider.

## 3. `FileStore` đại diện cho cái gì?

`FileStore` là một biểu diễn trừu tượng của nơi lưu trữ file. Theo Java API, nó có thể là:

- Thiết bị lưu trữ hoặc phân vùng/volume.
- Storage pool hoặc một file system cụ thể.
- Kho lưu trữ mạng hoặc một cơ chế lưu trữ theo implementation.
- File store được cung cấp bởi một `FileSystemProvider` tùy chỉnh.

Một `FileStore` **không nhất thiết bằng một ổ đĩa vật lý**. Ví dụ một phân vùng, volume logic, mount point hoặc môi trường ảo hóa có thể biểu diễn khác với khái niệm “ổ cứng” mà người dùng nhìn thấy.

### Lấy FileStore từ đường dẫn

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileStore;

Path directory = Path.of(".").toAbsolutePath();

FileStore store = Files.getFileStore(directory);

System.out.println(store.name());
System.out.println(store.type());
```

Đây là đoạn code đặt trong phương thức khai báo hoặc xử lý `IOException`. Vì `"."` thường là thư mục làm việc đang tồn tại, nó thích hợp cho ví dụ đọc file store mà không cần tạo file mới.

- `store.name()`: tên file store, phụ thuộc hệ thống/provider.
- `store.type()`: loại file store, cũng phụ thuộc implementation, ví dụ format hoặc loại lưu trữ.
- `store.isReadOnly()`: chỉ ra file store được khai báo read-only.
- `Files.getFileStore(directory)`: lấy file store nơi **đường dẫn đó** nằm.

**Không nên so sánh tên file store hoặc type với một literal cố định** trên mọi hệ điều hành, cũng không khẳng định tên file store luôn là `C:` hoặc `/dev/...`.

### Đường dẫn chưa tồn tại thì sao?

Đối với file upload **sẽ được tạo**, nên kiểm tra file store của **thư mục đích đã tồn tại**:

```java
Path targetDirectory = Path.of("data").toAbsolutePath();
// Cần bảo đảm "data" đã tồn tại và có thể truy cập trước khi gọi:
FileStore store = Files.getFileStore(targetDirectory);
```

Đây chỉ là đoạn minh họa; nếu `data` không tồn tại thì lời gọi có thể thất bại. Không tự tạo file dự kiến rồi mới lấy file store chỉ để kiểm tra dung lượng nếu không cần. Nếu có mount point trong cây thư mục, file store của `"."` có thể **khác** file store của thư mục upload thực.

## 4. `getTotalSpace()`: dung lượng tổng của file store

Chữ ký:

```java
public abstract long getTotalSpace() throws IOException
```

Hợp đồng API: trả về **kích thước file store, tính bằng byte**.

Ví dụ giả định:

```text
File store có tổng 100 GiB.
getTotalSpace() = 100 × 1024³
                = 107374182400 byte
```

Đây là dung lượng của **toàn file store theo provider**, không phải tổng byte của các file nằm trong một thư mục hay dung lượng còn có thể ghi.

Điều `getTotalSpace()` **không có nghĩa**:

- Không phải “dung lượng trống”.
- Không phải “dung lượng JVM được phép dùng thêm”.
- Không phải kích thước của một file (`Files.size(path)`).
- Không phải lượng RAM hoặc heap của JVM.
- Không nhất thiết là dung lượng vật lý của một thiết bị: volume logic/storage pool có thể có cách báo riêng.

API quy định nếu kích thước vượt `Long.MAX_VALUE`, kết quả được bão hòa ở `Long.MAX_VALUE`. Vì vậy không nên hiểu mọi kết quả `long` đều là thông tin chính xác vô hạn cho storage quy mô cực lớn.

### Total có cố định mãi không?

Không nên giả định. Dung lượng volume, storage pool hoặc quota có thể thay đổi do mở rộng/thu hẹp volume, thay đổi cấu hình hoặc hành vi của provider. Khi một dashboard cần số liệu mới, cần lấy lại thay vì lưu `total` từ lúc khởi động cho toàn bộ vòng đời hệ thống.

## 5. `getUnallocatedSpace()`: dung lượng chưa được phân bổ

Chữ ký:

```java
public abstract long getUnallocatedSpace() throws IOException
```

Hợp đồng API: trả về **số byte chưa được phân bổ trong file store**. Đây thường tương ứng với ý tưởng “free space” ở cấp file store, nhưng không đồng nghĩa chắc chắn với “số byte JVM hiện có thể ghi”.

Ví dụ giả định:

```text
Tổng:           100 GiB
Chưa phân bổ:     40 GiB

Ước tính đã phân bổ: 100 - 40 = 60 GiB
```

Trong điều kiện thông thường, có thể tính:

```java
long allocatedEstimate =
        store.getTotalSpace() - store.getUnallocatedSpace();
```

**Tên biến nên là `allocatedEstimate` hoặc `usedEstimate`**, không nên hiểu là tổng chính xác byte nội dung file người dùng. Dung lượng đã phân bổ có thể bao gồm metadata của file system, dữ liệu riêng của hệ thống, snapshots, không gian phục vụ quản lý lưu trữ và các cấu trúc không phải một file thông thường.

### Chưa phân bổ ≠ phần đang được phép dùng

Một file store có thể báo 40 GiB chưa phân bổ nhưng JVM chỉ dùng được 25 GiB. Có thể có vùng dành riêng cho quản trị/hệ điều hành, quota, hạn chế quyền hoặc logic của provider.

**Điểm tinh tế:** phép đo số byte chưa phân bổ không bảo đảm rằng một lần ghi tới đây sẽ thành công. Javadoc gọi số đó là **hint, not a guarantee**.

Không dùng `getUnallocatedSpace()` làm số duy nhất quyết định một tiến trình không đặc quyền có thể ghi thêm bao nhiêu dữ liệu.

## 6. `getUsableSpace()`: dung lượng báo khả dụng cho JVM hiện tại

Chữ ký:

```java
public abstract long getUsableSpace() throws IOException
```

Hợp đồng API: trả về **số byte hiện được báo khả dụng đối với Java virtual machine trên file store**.

`getUsableSpace()` là phép đo gần nhất với câu hỏi “tiến trình JVM này có thể sử dụng thêm bao nhiêu dung lượng?”. Trên một số hệ thống, nó có thể phản ánh các giới hạn mà `getUnallocatedSpace()` không phản ánh đầy đủ.

Ví dụ:

```text
getTotalSpace()       = 100 GiB
getUnallocatedSpace() =  40 GiB
getUsableSpace()      =  25 GiB
```

Diễn giải hợp lý:

- Hệ thống báo tổng 100 GiB.
- Còn 40 GiB chưa phân bổ ở cấp file store.
- Chỉ 25 GiB được **báo** khả dụng cho JVM này tại thời điểm đo.

**Không được kết luận chắc chắn 25 GiB có thể ghi thành công**. Dữ liệu có thể bị ghi bởi tiến trình khác ngay sau khi kiểm tra; hạn ngạch, path permissions, mount state hoặc hạn chế hệ thống còn có thể gây lỗi. Java API nói rõ con số khả dụng chỉ là **gợi ý** và có thể nhanh chóng không còn chính xác.

### Phần chênh chưa phân bổ nhưng không dùng được

Ở ví dụ trên:

```text
unallocated - usable = 40 - 25 = 15 GiB
```

Có thể gọi đây là **ước lượng chênh lệch tại thời điểm kiểm tra**. Nhưng **không được** mặc định toàn bộ 15 GiB là “hệ điều hành đã giữ lại”, “bị quota chặn” hay “không thể ghi dưới mọi tài khoản”. Java API không cho biết nguyên nhân chính xác từ phép trừ ấy.

### Phép đọc `usable` và quyền ghi file

Ngay cả khi `store.getUsableSpace() > 0`:

- Thư mục đích có thể không cho tạo file.
- File đích có thể bị khóa, trùng tên, read-only hoặc bị kiểm soát truy cập.
- Quota được cập nhật sau đó.
- Một tiến trình khác có thể chiếm dung lượng trống.
- Bộ lưu trữ hoặc kết nối mạng có thể lỗi.

Vì vậy **luôn xử lý `IOException` ở thao tác ghi thực tế**. Không biến pre-check thành lời hứa chắc chắn.

## 7. Bảng so sánh ba chỉ số

| Phương thức | Diễn giải đúng | Giá trị trả về | Có bảo đảm ghi được số byte ấy? |
| --- | --- | --- | --- |
| `getTotalSpace()` | Tổng quy mô file store | `long`, byte | **Không** |
| `getUnallocatedSpace()` | Tổng byte chưa được phân bổ | `long`, byte | **Không** |
| `getUsableSpace()` | Byte được báo có thể sử dụng bởi JVM hiện tại | `long`, byte | **Không** |

| Nhu cầu nghiệp vụ | Chỉ số phù hợp hoặc cách đánh giá |
| --- | --- |
| Hiển thị tổng dung lượng của volume | `getTotalSpace()` |
| Hiển thị số byte chưa được cấp phát | `getUnallocatedSpace()` |
| Ước lượng mức độ đã phân bổ | `total - unallocated`, có kiểm tra tính nhất quán và độ mới |
| Cảnh báo gần hết dung lượng đối với tiến trình | Chủ yếu `getUsableSpace()`, kèm threshold và monitoring |
| Kiểm tra sơ bộ upload 2 GiB | So với `usable` như **hint**, không bỏ `IOException` |
| Xác định user có quyền ghi vào thư mục cụ thể | Kiểm tra access + thử thao tác đúng quy trình; dung lượng chưa đủ để kết luận |
| Tính tổng kích thước file trong một folder | Không dùng ba chỉ số FileStore; dùng giải pháp duyệt file phù hợp |
| Ước lượng RAM cho JVM | Không dùng FileStore; xem API quản lý bộ nhớ tương ứng |

`getUsableSpace()` thường là phép đo gần nhất cho quyết định “có đủ chỗ không?”, nhưng không phải phép kiểm tra quyền ghi, quota toàn diện hoặc giao dịch dự trữ dung lượng.

## 8. Công thức tính “đã dùng” phải có điều kiện

Một công thức thường thấy:

```java
long usedEstimate = total - unallocated;
```

Nó mô tả phần **đã được phân bổ** theo hai phép đo, không nhất thiết mô tả dung lượng file của một ứng dụng.

Tương tự:

```java
long notUsableFromUnallocatedEstimate = unallocated - usable;
```

Đây là phần chênh được báo, **không phải một phân loại vật lý chính xác** về byte đã dự trữ.

### Không dùng `total - usable` làm “dung lượng đã dùng”

Với tổng 100 GiB và usable 25 GiB:

```text
total - usable = 75 GiB
```

Con số 75 GiB bao gồm cả **60 GiB đã phân bổ** và **15 GiB chưa phân bổ nhưng không được báo khả dụng cho JVM** theo giả định. Vì vậy:

```java
long wrongUsed = total - usable; // Sai nếu mục tiêu là “đã phân bổ”
```

Nó có thể có ý nghĩa riêng trong dashboard (“phần không khả dụng cho JVM”), nhưng **không tương đương** `usedEstimate = total - unallocated`.

### Không áp đặt công thức thành bất biến của mọi provider

Trong một snapshot giả định lý tưởng, thường có:

```text
0 ≤ usable ≤ unallocated ≤ total
```

Nhưng Java API không cam kết ba lời gọi được đọc nguyên tử ở cùng thời điểm hoặc mọi provider đều định nghĩa và báo số liệu giống nhau. Thực tế:

- Một tiến trình khác có thể ghi/xóa dữ liệu giữa các lời gọi.
- Quota, mount point, size được cập nhật.
- Một số provider báo thông tin ước lượng hoặc số đã bão hòa ở `Long.MAX_VALUE`.
- Các hệ thống file ảo/network có thể có cách phản ánh capacity khác.

Vì vậy, nếu số đo vi phạm quan hệ mong đợi, **đừng âm thầm dùng phép trừ dẫn đến giá trị âm rồi đưa lên dashboard**. Nên hiển thị số liệu gốc, ghi nhận tình trạng không nhất quán và tránh suy ra “used”/percent từ bộ số đó.

Đây là cách xử lý **phòng vệ của ứng dụng**, không phải khẳng định vi phạm quan hệ luôn là lỗi của JDK.

## 9. `FileStore` không cho snapshot nguyên tử ba giá trị

Các lời gọi:

```java
long total = store.getTotalSpace();
long unallocated = store.getUnallocatedSpace();
long usable = store.getUsableSpace();
```

được thực hiện **riêng rẽ**. Giữa chúng, tiến trình khác hoặc hệ điều hành có thể ghi/xóa file, thay đổi cấp phát hoặc cập nhật quota.

Hệ quả:

- `total`, `unallocated`, `usable` có thể phản ánh những thời điểm không hoàn toàn giống nhau.
- `usedEstimate` và các phần trăm chỉ là **ước lượng gần thời điểm đo**.
- Một số liệu “vừa đo xong” vẫn có thể lỗi thời ngay trước thao tác ghi.
- Không nên lấy `usable` đã cache từ nhiều giờ trước để quyết định upload lớn.

**Thiết kế dashboard:** lưu timestamp của lần lấy mẫu, refresh theo chu kỳ phù hợp, và thể hiện đây là số quan sát, không phải dự trữ dung lượng đã được cấp quyền.

**Thiết kế ghi tệp:** kiểm tra nhanh trước khi ghi nếu có giá trị UX, nhưng thao tác ghi phải tự xử lý lỗi hết chỗ, permission, quota và các lỗi I/O khác.

### Vì sao không thể “đặt trước chỗ” bằng `getUsableSpace()`?

Đọc chỉ số không làm hệ điều hành giữ lại byte nào cho ứng dụng. Hai tiến trình có thể cùng đọc “còn 5 GiB” rồi đồng thời cố ghi 4 GiB. Mỗi tiến trình đều thấy hint có vẻ đủ, nhưng tổng nhu cầu vượt dung lượng. Đây là ví dụ *time-of-check to time-of-use* (TOCTOU).

Nếu yêu cầu phải đảm bảo dành chỗ, giải pháp thuộc tầng quản lý quota/storage hoặc cơ chế ghi/dự trữ do hệ thống file hỗ trợ; **`FileStore` không cung cấp thao tác đặt chỗ**.

## 10. Lấy đúng FileStore khi có nhiều volume hoặc mount point

### 10.1. Đường dẫn tệp/ thư mục thực sự quan trọng

Một máy có thể có:

- Ổ hệ điều hành và ổ lưu dữ liệu riêng.
- Nhiều phân vùng hoặc mount point.
- Container volume, network mount hoặc storage pool.
- Thư mục tạm trên file store khác thư mục lưu thành phẩm.

Ví dụ:

```java
Path tempDir = Path.of(System.getProperty("java.io.tmpdir"));
Path outputDir = Path.of("data").toAbsolutePath();

// Nếu hai thư mục tồn tại:
FileStore tempStore = Files.getFileStore(tempDir);
FileStore outputStore = Files.getFileStore(outputDir);
```

Đây là mã minh họa có import `Path`, `Files`, `FileStore`, yêu cầu các đường dẫn tồn tại và xử lý `IOException`.

Đừng lấy `FileStore` của `"."` rồi áp dụng con số đó cho upload thực sự được ghi vào mount khác. Nếu file dự kiến chưa tồn tại, lấy FileStore của **thư mục cha đã tồn tại** nơi file sẽ được tạo, đồng thời vẫn cần kiểm tra permission trên đường dẫn thực tế.

### 10.2. Các mount point có thể thay đổi

`Files.getFileStore(Path)` trả file store nơi đường dẫn tọa lạc. Nếu file bị xóa hoặc chuyển sang file store khác sau khi đã lấy object, Javadoc cho biết hành vi tiếp theo với object `FileStore` có thể phụ thuộc implementation.

Vì vậy, khi đường dẫn hoặc mount state có thể thay đổi, hãy dùng lại đường dẫn hiện hành và xử lý lỗi thực tế thay vì coi FileStore handle lấy một lần là mãi mãi chính xác.

### 10.3. Liệt kê các file store

```java
for (FileStore fs : FileSystems.getDefault().getFileStores()) {
    System.out.println(fs.name() + " / " + fs.type());
}
```

Đoạn minh họa có import `FileStore` và `FileSystems`. Thứ tự các file store được trả **không được cam kết**; danh sách có thể thay đổi theo thời gian và có thể không chứa store không truy cập được khi xảy ra I/O error.

Không đồng nhất “một store trong danh sách” với “một ổ cứng vật lý”, và không cộng cơ học capacity của tất cả store nếu chúng có thể trùng lặp, ánh xạ chồng lấn hoặc là storage pool/volume ảo. Muốn báo cáo tổng capacity toàn hạ tầng phải có mô hình lưu trữ ở tầng hệ thống.

## 11. `isReadOnly()` không phải phép đo dung lượng

`FileStore.isReadOnly()` cho biết file store có được khai báo là **chỉ đọc** hay không:

```java
boolean readOnly = store.isReadOnly();
```

Nếu `readOnly == true`, không nên thử tạo/ghi tệp trên store như thể writable bình thường. Nhưng:

- `readOnly == false` **không bảo đảm** một user/process được quyền ghi mọi thư mục trong store.
- `usable > 0` **không bảo đảm** đường dẫn đích cho phép ghi.
- Ngược lại, **không suy luận tuyệt đối** mọi provider bắt buộc báo `usable == 0` khi `readOnly == true`; API mô tả hai phép đo khác mục đích.

Ví dụ một volume về nguyên tắc writable, nhưng thư mục `/private` có quyền chỉ cho user khác ghi. FileStore vẫn có thể báo số `usable`, trong khi thao tác thực của ứng dụng thất bại do `AccessDeniedException` hoặc loại `IOException` thích hợp.

**Thiết kế đúng:** dùng `isReadOnly()` để nhận diện một điều kiện loại trừ rõ ràng; dùng thông tin thư mục, quyền và **xử lý kết quả thật của lệnh ghi** để quyết định thành công.

## 12. Byte, KB, KiB, GB và GiB: đừng sai đơn vị

Ba API dung lượng FileStore trả **byte**. Đổi đơn vị đúng:

```text
1 KB  = 1.000 byte
1 KiB = 1.024 byte

1 MB  = 1.000.000 byte
1 MiB = 1.048.576 byte

1 GB  = 1.000.000.000 byte
1 GiB = 1.073.741.824 byte
```

Trong Java:

```java
long bytesPerGiB = 1024L * 1024L * 1024L;
long bytesPerGB  = 1000L * 1000L * 1000L;

double gib = totalBytes / (double) bytesPerGiB;
double gb  = totalBytes / (double) bytesPerGB;
```

Đây là đoạn minh họa giả sử `totalBytes` đã khai báo.

### Vì sao cần `1024L` chứ không chỉ `1024`?

Kiểu `long` giúp phép nhân được thực hiện ở độ rộng 64-bit. Với kích thước thực tế của file store, dùng `int` rất dễ tràn.

```java
long gib = 1024L * 1024L * 1024L; // Đúng: 1_073_741_824
long hundredGiB = 100L * gib;      // Đúng với long

// int wrong = 100 * 1024 * 1024 * 1024; // Tràn int
```

Nếu một đầu vào như `requestedGiB` rất lớn, phép nhân sang byte vẫn có thể vượt cả `Long.MAX_VALUE`. Khi cần phòng vệ, dùng `Math.multiplyExact(requestedGiB, GIB)` để phát hiện tràn số, hoặc kiểm tra giới hạn trước khi nhân.

### Phép chia nguyên và phần trăm

```java
long total = 100L * gib;
long unallocated = 40L * gib;

System.out.println(unallocated / gib); // 40
```

Đây là số nguyên GiB được làm tròn xuống nếu có phần dư. Với tỷ lệ phần trăm, tránh:

```java
long wrongPercent = (unallocated / total) * 100; // 0
```

Vì `unallocated / total` dùng chia nguyên. Dùng:

```java
double pct = 100.0 * unallocated / total;
```

và kiểm tra `total > 0` để tránh chia cho 0. Khi hiển thị, truyền `Locale.ROOT` hoặc locale tường minh nếu cần dấu thập phân nhất quán.

## 13. Tính phần trăm và báo cáo dung lượng đúng nghĩa

Với bộ số giả định:

```text
total = 100 GiB
unallocated = 40 GiB
usable = 25 GiB
```

Ta có các tỷ lệ theo **tổng**:

```text
allocated estimate / total = 60%
unallocated / total        = 40%
usable / total             = 25%
```

**Điểm dễ nhầm:** `60% + 40% = 100%` trong mô hình nhất quán vì allocated và unallocated là hai phần bù của nhau. Nhưng **không nên cộng** `allocated% + usable%` rồi chờ 100%: usable là một **tập con tiềm năng** của phần chưa phân bổ trong mô hình thông thường.

Nếu dashboard chỉ có hai màu “đã dùng” và “còn lại”, chọn rõ bạn đang mô tả:

- **Góc nhìn file store:** đã phân bổ so với chưa phân bổ.
- **Góc nhìn JVM:** byte được báo khả dụng, còn lại không khả dụng cho JVM (có thể bao gồm phần đã phân bổ và giới hạn khác).

Không trộn hai góc nhìn vào một thanh phần trăm mà không chú thích.

### Trường hợp total bằng 0 hoặc số liệu thiếu nhất quán

Có thể gặp provider đặc biệt, số đo thiếu/không đại diện storage thông thường, hoặc một lỗi đọc đã được báo. Nếu `total <= 0`, **không tính phần trăm**. Nếu các số liệu không khớp quan hệ thường gặp, hiển thị raw values và trạng thái cảnh báo thay vì tạo phần trăm giả hoặc số âm.

## 14. Dùng chỉ số khi kiểm tra trước upload: pre-check chỉ là hint

Giả sử ứng dụng dự định lưu một tệp mới kích thước 20 GiB.

```java
long requestedBytes = 20L * 1024 * 1024 * 1024;
long usable = store.getUsableSpace();

if (usable < requestedBytes) {
    System.out.println("Dung lượng báo khả dụng đang thấp.");
} else {
    System.out.println("Dung lượng báo khả dụng có vẻ đủ.");
}
```

Đây là **pre-check tư vấn**, không phải lệnh đặt trước dung lượng. Chưa có file nào được ghi chỉ bởi các phép đo.

Ngay sau khi pre-check:

- Một tiến trình khác có thể bắt đầu ghi.
- Hệ thống có thể cập nhật quota.
- Directory permissions có thể khác với store-level availability.
- Nội dung thực tế có thể vượt kích thước dự kiến do encoding, metadata, block allocation, file-system overhead.
- Network storage có thể mất kết nối hoặc filesystem thay đổi trạng thái.

Vì vậy bước thực sự lưu tệp vẫn phải xử lý exception và bảo đảm cleanup.

### Mẫu thiết kế ở cấp quy trình

```text
1. Xác định thư mục đích có thật và file store của nó.
2. Đọc usable space như một chỉ số tham khảo.
3. Nếu usable thấp: cảnh báo hoặc từ chối theo chính sách sản phẩm.
4. Thực hiện ghi tệp theo thiết kế ứng dụng.
5. Xử lý IOException, quota/permission/disk-full và file ghi dở.
6. Nếu quan trọng: ghi tạm, xác minh, publish/rename an toàn.
7. Thu thập monitoring sau thao tác.
```

**Không sử dụng `getUsableSpace()` làm bảo đảm write thành công**, cũng không bỏ `IOException` khi đã vượt qua pre-check.

## 15. Vì sao tổng kích thước file không bằng “đã dùng” của FileStore?

Giả sử chương trình dùng `Files.walk` để duyệt folder và cộng `Files.size(file)`. Kết quả ấy là **tổng kích thước logic** của các file mà chương trình đi qua, không phải số byte allocated trên toàn file store.

Có thể khác biệt bởi:

- File system metadata và cấu trúc quản lý.
- File trên cùng volume nhưng nằm ngoài folder.
- Hard links, symbolic links hoặc snapshots.
- Compression, sparse files và cách block allocation.
- Nội dung hệ điều hành, recycle bin hoặc dữ liệu không được quyền duyệt.
- Các đặc trưng riêng của provider.

`Files.size(path)` cũng không được tài liệu bảo đảm luôn tương đương dung lượng thực được cấp phát cho file trên đĩa, đặc biệt khi có compression/sparse files.

Vì vậy **đừng chứng minh `getTotalSpace() - getUnallocatedSpace()` sai** chỉ vì phép cộng `Files.size` của một folder không bằng số ấy. Hai phép đo mô tả **hai tầng khác nhau**.

Tương tự, `Runtime.getRuntime().freeMemory()` hay `maxMemory()` là thông tin về **bộ nhớ JVM**, không phải dung lượng file store.

## 16. Chương trình Java 17+ độc lập: mô phỏng xác định và đo thật khi cần

Tạo tệp **`FileStoreSpaceDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class FileStoreSpaceDemo {
    static final long GIB = 1024L * 1024L * 1024L;

    record Space(long total, long unallocated, long usable) {
        boolean typicalOrdering() {
            return total >= 0
                    && unallocated >= 0
                    && usable >= 0
                    && unallocated <= total
                    && usable <= unallocated;
        }

        long allocatedEstimate() {
            if (!typicalOrdering()) {
                throw new IllegalStateException(
                        "Inconsistent or non-typical storage metrics");
            }
            return total - unallocated;
        }

        long unallocatedNotUsableEstimate() {
            if (!typicalOrdering()) {
                throw new IllegalStateException(
                        "Cannot derive space difference reliably");
            }
            return unallocated - usable;
        }

        boolean enoughForHint(long requestBytes) {
            return requestBytes >= 0 && usable >= requestBytes;
        }
    }

    static String percent(long part, long total) {
        if (total <= 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT, "%.1f%%",
                100.0 * part / total);
    }

    static Space readSpace(FileStore store) throws IOException {
        return new Space(
                store.getTotalSpace(),
                store.getUnallocatedSpace(),
                store.getUsableSpace());
    }

    static void showLiveStore(Path existingPath) throws IOException {
        var store = Files.getFileStore(existingPath.toAbsolutePath());
        var live = readSpace(store);

        System.out.println("liveName=" + store.name());
        System.out.println("liveType=" + store.type());
        System.out.println("liveReadOnly=" + store.isReadOnly());
        System.out.println("liveTotalBytes=" + live.total());
        System.out.println("liveUnallocatedBytes=" + live.unallocated());
        System.out.println("liveUsableBytes=" + live.usable());
        System.out.println("liveTypicalOrdering="
                + live.typicalOrdering());
        if (live.typicalOrdering()) {
            System.out.println("liveAllocatedEstimateBytes="
                    + live.allocatedEstimate());
        }
        // Các số live thay đổi theo máy, volume và thời điểm đo.
    }

    public static void main(String[] args) throws IOException {
        var sample = new Space(
                100L * GIB,
                40L * GIB,
                25L * GIB);

        System.out.println("totalGiB="
                + sample.total() / GIB);
        System.out.println("unallocatedGiB="
                + sample.unallocated() / GIB);
        System.out.println("usableGiB="
                + sample.usable() / GIB);
        System.out.println("allocatedEstimateGiB="
                + sample.allocatedEstimate() / GIB);
        System.out.println("unallocatedNotUsableEstimateGiB="
                + sample.unallocatedNotUsableEstimate() / GIB);

        System.out.println("typicalOrdering="
                + sample.typicalOrdering());
        System.out.println("allocatedPercent="
                + percent(sample.allocatedEstimate(), sample.total()));
        System.out.println("unallocatedPercent="
                + percent(sample.unallocated(), sample.total()));
        System.out.println("usablePercent="
                + percent(sample.usable(), sample.total()));

        System.out.println("enough20GiBHint="
                + sample.enoughForHint(20L * GIB));
        System.out.println("enough30GiBHint="
                + sample.enoughForHint(30L * GIB));
        System.out.println("totalMinusUsableGiB="
                + (sample.total() - sample.usable()) / GIB);
        System.out.println("oneGiBBytes=" + GIB);
        System.out.println("zeroTotalPercent=" + percent(0, 0));

        var inconsistent = new Space(100, 150, 40);
        System.out.println("inconsistentOrdering="
                + inconsistent.typicalOrdering());

        if (args.length > 0) {
            showLiveStore(Path.of(args[0]));
        }
    }
}
```

### Chạy mô phỏng với stdout cố định

```bash
javac --release 17 -encoding UTF-8 FileStoreSpaceDemo.java
java FileStoreSpaceDemo
```

**Stdout chính xác của lệnh không truyền tham số:**

```text
totalGiB=100
unallocatedGiB=40
usableGiB=25
allocatedEstimateGiB=60
unallocatedNotUsableEstimateGiB=15
typicalOrdering=true
allocatedPercent=60.0%
unallocatedPercent=40.0%
usablePercent=25.0%
enough20GiBHint=true
enough30GiBHint=false
totalMinusUsableGiB=75
oneGiBBytes=1073741824
zeroTotalPercent=n/a
inconsistentOrdering=false
```

### Đọc FileStore thật (đầu ra phụ thuộc môi trường)

Sau khi biên dịch, có thể chạy:

```bash
java FileStoreSpaceDemo .
```

Dấu chấm `.` chỉ thư mục hiện tại. Khi truyền một đường dẫn tồn tại, chương trình lấy `Files.getFileStore(path)` và in tên store, loại store, `isReadOnly` và ba dung lượng thực của **volume chứa path**. Không cung cấp stdout giả cho phần này vì các giá trị **không cố định** giữa máy, container, mount hoặc thời điểm.

Chương trình mặc định **không ghi tệp, không xóa tệp và không dự trữ dung lượng**. Nó chỉ chạy minh họa dữ liệu giả định. Chế độ có tham số chỉ đọc metadata file store.

### Phân tích stdout cố định

1. Tổng 100 GiB, trống chưa phân bổ 40 GiB, usable 25 GiB.
2. Ước tính đã phân bổ: `100 - 40 = 60 GiB`.
3. Chênh chưa phân bổ nhưng không được báo usable: `40 - 25 = 15 GiB`.
4. Ba phần trăm đều chia cho `total`: 60%, 40%, 25%. Không cộng 60% và 25% để tìm 100%.
5. Pre-check 20 GiB trả true vì `20 <= 25`; pre-check 30 GiB trả false. **True chỉ là hint**, không bảo đảm write thành công.
6. `totalMinusUsableGiB=75` khác `allocatedEstimateGiB=60`: không được gọi 75 GiB là “đã phân bổ” trong ví dụ.
7. `percent(0, 0)` trả `n/a` thay vì chia cho 0.
8. Bộ số giả định không nhất quán `(total=100, unallocated=150)` khiến `typicalOrdering` trả false. Chương trình tránh tính “used” từ bộ số bất thường.
9. Khi chạy với đối số, code in thông tin live nhưng **không suy ra bảo đảm ghi**.

### Vì sao ví dụ không cố gắng dự đoán số liệu thật?

Một chương trình giáo dục cần stdout xác định cho phép QA chính xác; còn chỉ số storage thật vốn thay đổi liên tục. Tách phần **mô phỏng để kiểm logic** và **đo hệ thống thật để quan sát** tránh khẳng định sai về dung lượng máy người học.

## 17. Những lỗi phổ biến và cách sửa

### Lỗi A: Gọi `getTotalSpace()` là dung lượng còn trống

```java
long free = store.getTotalSpace(); // Sai tên biến và ý nghĩa
```

**Sửa:** dùng `total`; để hỏi trống dùng `getUnallocatedSpace`, để hỏi khả dụng cho JVM dùng `getUsableSpace`.

### Lỗi B: Lấy `total - usable` làm “đã dùng”

```java
long used = total - usable; // Không tương đương “đã phân bổ”
```

**Sửa:** nếu số liệu đủ nhất quán, dùng `total - unallocated` như **ước tính đã phân bổ**; giải thích rõ nó không bằng tổng file size.

### Lỗi C: Cho rằng `unallocated == usable`

Điều này không phải bất biến. Quota, quyền, vùng dành riêng, provider và khác biệt thời điểm lấy mẫu có thể khiến hai số khác nhau.

**Sửa:** hiển thị cả hai khi phân tích không gian hệ thống và ưu tiên `usable` để đánh giá sơ bộ dung lượng có thể ghi bởi JVM.

### Lỗi D: Tin rằng `usable >= requestBytes` bảo đảm upload thành công

`getUsableSpace` chỉ là hint, có thể lỗi thời trước khi ghi. Ngoài hết chỗ còn có permission, network, file lock và các điều kiện I/O khác.

**Sửa:** giữ pre-check như cảnh báo, vẫn `try/catch IOException` ở bước ghi và xử lý cleanup.

### Lỗi E: Lấy FileStore của thư mục làm việc, nhưng ghi vào volume khác

```java
FileStore wrongStore = Files.getFileStore(Path.of("."));
// Nhưng file thật được ghi sang một mount/volume khác.
```

**Sửa:** lấy store của **thư mục đích thực sự tồn tại**.

### Lỗi F: Dùng `int` và phép chia nguyên

```java
int size = 100 * 1024 * 1024 * 1024; // Có thể tràn int
long percent = (free / total) * 100; // Có thể thành 0
```

**Sửa:** dùng `long`/`1024L`, `Math.multiplyExact` khi cần và phép chia số thực cho tỷ lệ.

### Lỗi G: Nhầm GB với GiB

Dùng 1000³ để đổi GB, 1024³ để đổi GiB. Nếu giao diện ghi “GB” nhưng tính bằng GiB, người dùng thấy các số khác báo cáo của hệ điều hành.

**Sửa:** khai báo nhất quán đơn vị và công thức.

### Lỗi H: Tưởng `store.isReadOnly() == false` nghĩa là mọi thư mục writable

`isReadOnly` mô tả file store, không phải quyền tạo file của user đối với mọi path. **Sửa:** xử lý quyền trên đường dẫn cụ thể và lỗi ghi thật.

### Lỗi I: Coi ba phép đo tạo một snapshot nguyên tử

Các lời gọi là độc lập; hệ thống có thể thay đổi giữa chúng. **Sửa:** dùng dấu thời gian, diễn giải là số gần thời điểm đo và tránh suy ra số âm không hợp lý.

### Lỗi J: Cộng `Files.size` của thư mục rồi so trực tiếp với `usedEstimate`

Dữ liệu folder không bao gồm toàn bộ filesystem, còn allocated space có thể gồm metadata, files ngoài folder, snapshot và cơ chế file system khác.

**Sửa:** xem phép đo folder và FileStore là hai tầng khác nhau.

### Lỗi K: Hardcode kết quả FileStore cho mọi máy

FileStore của Windows, Linux, container, máy ảo hoặc network storage có thể báo hoàn toàn khác.

**Sửa:** test logic bằng số giả định, test integration trên môi trường được hỗ trợ và không assert literal capacity thật.

### Lỗi L: Không xử lý `IOException` khi đọc thống kê

Ba phương thức có `throws IOException`. **Sửa:** báo lỗi đo lường thật, không tự mặc định mọi lỗi nghĩa là “còn 0 byte” vì điều này làm sai thông tin vận hành.

## 18. Checklist khi làm tính năng thực tế

1. **Đường dẫn ghi thật ở đâu?** Xác định thư mục đích có tồn tại.
2. **Bạn muốn hiển thị tổng, trống hay usable?** Chọn đúng phương thức.
3. **Dữ liệu là byte hay GiB/GB?** Ghi rõ đơn vị.
4. **Có sử dụng `long` không?** Không lưu bytes vào `int`.
5. **Số liệu có thay đổi theo thời điểm không?** Đánh timestamp và refresh phù hợp.
6. **Bạn có tính used từ `total - unallocated`?** Chỉ xem là ước lượng allocated; tránh `total - usable`.
7. **Có suy ra reserved bytes từ phép trừ không?** Không gán nguyên nhân cụ thể khi chỉ có ba số.
8. **Có giới hạn quota/permission không?** Đừng tin unallocated = usable.
9. **File store có read-only không?** Tham khảo `isReadOnly` và quyền thư mục.
10. **Có dùng pre-check làm bảo đảm không?** Không, vẫn xử lý lỗi I/O khi ghi.
11. **Có giới hạn file size/transaction quota không?** Tính theo policy của ứng dụng, không chỉ theo store.
12. **Có dùng đường dẫn của đúng mount không?** Tránh đọc từ một volume rồi ghi sang volume khác.
13. **Phần trăm có chia cho 0 không?** Nếu total không hợp lệ, hiển thị n/a.
14. **Các phép đo có thể không nhất quán không?** Hiển thị raw values, tránh kết quả trừ âm.
15. **Có test trên storage ảo/mạng không?** Provider có thể báo khác local disk.
16. **Có cộng trùng file stores không?** Kiểm mô hình volume/storage pool khi tổng hợp.
17. **Bạn có phân biệt FileStore và tổng Files.size không?** Hai số không đồng nghĩa.
18. **Nếu ghi file quan trọng bị lỗi giữa chừng thì sao?** Xử lý file tạm, cleanup và thông báo chính xác.

## 19. Bài tập tự đánh giá

**Câu 1.** `getTotalSpace()` trả về byte tổng, byte trống hay byte khả dụng cho JVM?

**Câu 2.** `getUnallocatedSpace()` có luôn bằng `getUsableSpace()` không?

**Câu 3.** Cho `total=100 GiB`, `unallocated=40 GiB`, `usable=25 GiB`. Ước lượng đã phân bổ bằng bao nhiêu?

**Câu 4.** Cùng bộ số trên, vì sao `total - usable = 75 GiB` **không** thể gọi là phần đã phân bổ?

**Câu 5.** Chênh `unallocated - usable = 15 GiB` có chứng minh 15 GiB đều bị hệ điều hành giữ lại không?

**Câu 6.** Nếu `usable=5 GiB` và file dự định ghi 4 GiB, Java có bảo đảm ghi thành công không?

**Câu 7.** Tại sao phải gọi `Files.getFileStore(targetDirectory)` thay vì luôn gọi cho `"."`?

**Câu 8.** Ba lời gọi đo dung lượng có tạo snapshot nguyên tử không?

**Câu 9.** `getTotalSpace` trả về byte, vậy muốn hiển thị GiB chia cho số nào?

**Câu 10.** `isReadOnly()==false` có chứng minh ứng dụng ghi được thư mục `/protected` không?

**Câu 11.** Một thư mục chứa tổng `Files.size` là 20 GiB nhưng FileStore báo đã phân bổ 70 GiB. Có chắc số đo sai không?

**Câu 12.** Vì sao test không nên `assertEquals(100*GiB, Files.getFileStore(Path.of(".")).getTotalSpace())`?

**Câu 13.** Nếu total=0, nên hiển thị `usedPercent` bao nhiêu?

**Câu 14.** Tại sao `long request = 100 * 1024 * 1024 * 1024` có thể sai dù biến đích là `long`?

**Câu 15.** Ba chỉ số FileStore được giới thiệu mới ở Java 10 hay đã có từ trước?

**Đáp án:**

1. Byte **tổng dung lượng file store**.
2. Không. `usable` đo byte khả dụng cho JVM; quota/quyền/dự trữ và hoàn cảnh khác có thể tạo chênh.
3. `100 - 40 = 60 GiB`, chỉ là ước lượng phần đã phân bổ.
4. Vì 75 gồm cả phần đã phân bổ và phần trống nhưng không được báo dùng được cho JVM.
5. Không. Chênh lệch là dữ liệu quan sát, không xác định chính xác mọi nguyên nhân.
6. Không. Pre-check chỉ là hint; vẫn phải xử lý lỗi ghi.
7. Để kiểm tra đúng volume/mount thực sự chứa file sẽ lưu.
8. Không. Các phép đo độc lập; hệ thống có thể đổi giữa chúng.
9. Chia cho `1024L * 1024L * 1024L`; ghi đơn vị GiB.
10. Không. Quyền path và các lỗi I/O là chuyện riêng.
11. Không. Tổng size file của folder khác allocated space trên cả store.
12. Dung lượng máy, mount và thời điểm khác nhau; test nên dùng dữ liệu mô phỏng cho logic.
13. `n/a` hoặc trạng thái không xác định; không chia cho 0.
14. Phép nhân có thể được đánh giá bằng `int` rồi **tràn trước** khi gán sang `long`. Dùng `100L * 1024 * 1024 * 1024`.
15. `FileStore` và các phép đo này có từ Java 7; `getBlockSize()` được thêm vào Java 10. Các phép đo vẫn được dùng trong Java hiện đại.

## 20. Ghi nhớ và nguồn Java chính thức

- **`getTotalSpace()`:** tổng byte của file store.
- **`getUnallocatedSpace()`:** byte chưa được phân bổ trong file store.
- **`getUsableSpace()`:** byte được báo khả dụng cho **JVM hiện tại**, không phải bảo đảm ghi.
- **Ước lượng đã phân bổ:** `total - unallocated` nếu bộ số liệu đủ nhất quán. **Không dùng `total - usable` làm “used”.**
- **Chênh `unallocated - usable` không tự giải thích được nguyên nhân**; có thể liên quan quota/quyền/dung lượng dành riêng/đặc điểm provider.
- **Cả ba đo bằng byte `long`, có thể đổi theo thời điểm và không là snapshot nguyên tử.**
- **Chọn đúng FileStore của thư mục đích**; pre-check không thay `IOException` ở lệnh ghi.
- Dùng đúng **GiB/GB**, tránh tràn `int` và chia nguyên khi tính tỷ lệ.
- `FileStore` và ba phép đo thuộc NIO.2 từ Java 7; phần bổ sung `getBlockSize()` xuất hiện ở Java 10. Kiến thức trình bày trong bài vẫn áp dụng hiện nay.

Tài liệu chính thức, còn hiệu lực:

1. [Java SE 26 — `java.nio.file.FileStore`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileStore.html): khái niệm file store, `getTotalSpace`, `getUnallocatedSpace`, `getUsableSpace`, `isReadOnly` và `getBlockSize`.
2. [Java SE 26 — `Files.getFileStore(Path)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): xác định file store chứa một path và các giới hạn khi file bị chuyển/xóa.
3. [Java SE 26 — `FileSystem.getFileStores()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystem.html#getFileStores()): liệt kê file store, thứ tự không được cam kết.
4. [Java SE 26 — `Files.size(Path)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#size(java.nio.file.Path)): kích thước logic file có thể khác dung lượng được cấp phát thực tế.
5. [Java SE 26 — `java.io.File.getUsableSpace()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/File.html#getUsableSpace()): API tương tự trên `File`, hữu ích để đối chiếu nhưng không thay ngữ nghĩa `FileStore`.

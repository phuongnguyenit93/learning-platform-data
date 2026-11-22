# FileChannel.force(boolean) và phạm vi bảo đảm với thiết bị lưu trữ

Khi ghi tệp bằng Java, lời gọi `FileChannel.write(...)` trả về thành công **không đồng nghĩa** dữ liệu đã tới thiết bị lưu trữ bền vững. Hệ điều hành và thiết bị thường dùng các tầng bộ nhớ đệm để tăng tốc. Phương thức `FileChannel.force(boolean metaData)` yêu cầu đẩy các thay đổi thuộc phạm vi hợp đồng của channel xuống thiết bị lưu trữ chứa tệp. Đây là công cụ quan trọng khi ứng dụng lưu dữ liệu cần sống sót sau sự cố hệ thống, nhưng **không phải transaction, không phải khóa ghi, và không bảo đảm tuyệt đối trước mọi lỗi phần cứng hay lưu trữ từ xa**.

Mục tiêu sau bài học:

1. Hiểu `force(false)` và `force(true)` buộc ghi những gì.
2. Phân biệt dữ liệu file, metadata của file và mục tên file trong thư mục.
3. Xác định chính xác ranh giới bảo đảm giữa local storage, remote storage, OS, filesystem, controller và bộ nhớ đệm.
4. Sử dụng `FileChannel.force`, `MappedByteBuffer.force` và các tùy chọn `SYNC`/`DSYNC` đúng hoàn cảnh.
5. Thiết kế trình tự ghi và kiểm thử phù hợp khi cần cả độ bền (*durability*) lẫn tính nguyên tử (*atomicity*).

## 1. Vì sao đã gọi write mà dữ liệu vẫn có thể mất?

Một thao tác ghi file thường đi qua nhiều tầng:

```text
Ứng dụng Java
    |
    | FileChannel.write(ByteBuffer)
    v
JDK / lời gọi hệ điều hành
    |
    v
Bộ đệm của hệ điều hành / page cache
    |
    v
Filesystem / block layer / driver
    |
    v
Cache của controller hoặc thiết bị
    |
    v
Thiết bị lưu trữ thực tế
    (SSD, HDD, bộ nhớ bền vững, thiết bị qua mạng...)
```

Sơ đồ này là mô hình khái quát để hiểu các mức trách nhiệm; đường I/O thực tế phụ thuộc OS, filesystem và loại thiết bị. Một lệnh `write` có thể hoàn tất sau khi dữ liệu được nhận vào cache của OS, trước khi được xác nhận đã ghi bền vững trên thiết bị. Cache khiến đọc lại ngay sau ghi thường thấy dữ liệu mới, ngay cả khi mất điện sau đó có thể dẫn tới kết quả khác.

Phân biệt các trạng thái:

- **Dữ liệu đã được chấp nhận bởi thao tác ghi:** `channel.write(buffer)` trả số byte thực sự được xử lý; vẫn cần lặp khi ghi chưa hết buffer.
- **Dữ liệu nhìn thấy khi đọc lại:** các lần đọc qua cùng OS có thể đọc từ cache. Điều đó chứng minh nội dung logic hiện tại, **không chứng minh khả năng phục hồi sau mất điện**.
- **Dữ liệu đã được yêu cầu đồng bộ xuống thiết bị:** `channel.force(...)` hoàn tất theo hợp đồng Java cho file thuộc local storage và các thay đổi được bao phủ.
- **Ứng dụng phục hồi nhất quán sau sự cố:** ngoài flush, cần xử lý transaction/record dở, metadata thư mục và thứ tự ghi. `force` riêng lẻ không tạo ra giao dịch.

**`flush()` của `OutputStream` và `FileChannel.force(...)` không có cùng ý nghĩa.** `flush` đẩy dữ liệu còn trong lớp đệm của stream theo hợp đồng implementation; nó không hứa dữ liệu đã ở thiết bị lưu trữ. `FileChannel` không có phương thức `flush()` tương tự: dùng `force` cho yêu cầu đồng bộ file.

## 2. Hợp đồng chính thức của FileChannel.force

Chữ ký:

```java
public abstract void force(boolean metaData) throws IOException
```

Phương thức trả về **`void`**; việc hoàn tất bình thường thể hiện thao tác force được thực hiện theo hợp đồng, không cung cấp số byte đã flush hay vị trí vật lý của dữ liệu. `ClosedChannelException` có thể xuất hiện nếu channel đóng; lỗi I/O khác được báo bằng `IOException`.

Theo Javadoc Java SE 21:

- Nếu tệp thuộc **thiết bị lưu trữ cục bộ (local storage device)**, khi `force` trả về bình thường, các thay đổi trong phạm vi mà API cam kết từ khi tạo channel hoặc lần force gần nhất được yêu cầu ghi xuống thiết bị đó.
- Nếu file **không nằm trên local device**, Java **không đưa ra cùng bảo đảm**. Ổ mạng và một số hệ thống file ảo/phân tán là những tình huống cần khảo sát kỹ.
- `metaData=false`: chỉ **nội dung file** bắt buộc được force theo yêu cầu.
- `metaData=true`: cần force **nội dung và metadata** của file. Tác dụng cụ thể của tham số tùy OS và có thể phát sinh thêm I/O.
- Hợp đồng bảo đảm đối với những thay đổi được thực hiện qua **các phương thức của FileChannel**, hoặc qua `FileOutputStream`/`RandomAccessFile` liên quan nếu channel lấy bằng `getChannel()`. Những thay đổi qua `MappedByteBuffer` có quy tắc riêng.

Cụm “được ghi xuống thiết bị” nên hiểu **trong phạm vi giao diện OS/thiết bị thực thi đúng hợp đồng**. Java không thể tự xác nhận firmware đã thật sự bảo đảm dữ liệu chống được mọi trường hợp controller hỏng, firmware lỗi, mất điện ở hệ thống không có bảo vệ cache hoặc sự cố phá hủy thiết bị.

### `force(false)` so với `force(true)`

| Lệnh | Phần được yêu cầu đồng bộ | Phạm vi sử dụng và lưu ý |
| --- | --- | --- |
| `channel.force(false)` | Nội dung byte đã thay đổi thuộc phạm vi API. | Phù hợp khi chỉ cần xác nhận nội dung file, không yêu cầu đồng bộ toàn bộ metadata. **Không mặc định** kích thước file mới hoặc thông tin thư mục đã bền vững như nội dung. |
| `channel.force(true)` | Nội dung **và metadata của file**. | Có thể cần khi thay kích thước, thời điểm hay thông tin metadata đi kèm. Không có nghĩa mọi thông tin thư mục cha, rename hoặc toàn bộ filesystem đã được force. |
| `channel.close()` | Giải phóng tài nguyên. | Không phải API thay thế `force` với cùng hợp đồng đồng bộ bền vững. Đừng dựa vào riêng `close` cho yêu cầu chống sự cố. |
| `OutputStream.flush()` | Đẩy các byte còn đệm ở lớp stream. | Không mang hợp đồng độ bền của `FileChannel.force`. |
| `MappedByteBuffer.force()` | Yêu cầu force các thay đổi của *mapping* (xem mục 5). | Không đồng nhất với channel.force khi dữ liệu được sửa qua mapped memory. |

Ví dụ ứng dụng cập nhật một record có kích thước cố định trong file hiện có: `force(false)` thường diễn đạt rõ ý định đảm bảo nội dung. Khi vừa mở rộng độ dài file hoặc tạo file mới, `force(true)` thường là lựa chọn thận trọng để yêu cầu đồng bộ metadata liên quan. Tuy nhiên, **lựa chọn tham số không biến trình tự cập nhật nhiều file hoặc một thư mục thành transaction**.

## 3. Những gì FileChannel.force bao phủ — và những gì không

### 3.1. Các thay đổi qua channel và đối tượng I/O có liên hệ

`force` được xác định với những thay đổi tệp do `FileChannel` thực hiện. Nếu `FileOutputStream.getChannel()` hoặc `RandomAccessFile.getChannel()` tạo channel, các thay đổi thực hiện qua stream/file ngẫu nhiên gắn với channel thuộc phạm vi hợp đồng ghi force nêu trong Javadoc.

```java
// Minh họa API (không phải chương trình độc lập).
try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw")) {
    raf.seek(0);
    raf.writeInt(42);
    raf.getChannel().force(true);
}
```

Ở đây `path` là `Path` tồn tại/ghi được; `getChannel()` của `RandomAccessFile` liên hệ cùng file handle. Ngược lại, **không tự động suy ra** rằng gọi `force` trên một channel riêng sẽ bao phủ mọi thay đổi do chương trình khác, một handle độc lập, API khác hoặc tiến trình khác tạo ra. Cần hiểu chính xác các writer và giao thức phối hợp.

### 3.2. Không tự biến lần ghi thành nguyên tử

Ví dụ ghi một record 4 KB rồi gọi `force(true)`:

- Nếu writer đã ghi được **một phần record** và gặp exception trước khi đủ 4 KB, `force` không sửa dữ liệu còn thiếu.
- Nếu hai thread ghi chồng lấn lên cùng vùng byte mà không khóa, `force` không quyết định byte của thread nào là đúng.
- Nếu ứng dụng cần thay đổi hai file nhất quán cùng nhau, `force` từng file không cung cấp transaction gồm cả hai.
- Nếu thiết bị mất điện **trong khi** bản ghi đang được ghi/force, file có thể cần cơ chế phục hồi theo format: length + checksum, version, nhật ký hoặc nhiều bản sao có đánh dấu commit.

**Durability** nghĩa là bảo toàn những cập nhật đã cam kết theo chính sách. **Atomicity** nghĩa là cập nhật được quan sát như trọn vẹn hoặc không có. **Consistency** nghĩa là các ràng buộc dữ liệu vẫn hợp lệ. `force` hỗ trợ phần durability trong phạm vi cam kết, không tự cung cấp atomicity và consistency của ứng dụng.

### 3.3. Không đồng nghĩa force metadata của *thư mục*

Metadata file (ví dụ kích thước, thời điểm sửa) khác với **directory entry** ánh xạ tên thành file. Khi ứng dụng tạo file mới hoặc đổi tên file bằng `Files.move`, dữ liệu file và sự bền vững của bản ghi thư mục là hai vấn đề cần xem riêng.

Ví dụ lưu cấu hình an toàn theo mẫu tổng quát:

```text
1. Tạo file tạm trong thư mục đích.
2. Ghi đầy đủ nội dung mới vào file tạm.
3. FileChannel.force(true) trên file tạm; xử lý mọi IOException.
4. Đóng channel.
5. Đổi tên/replace sang đường dẫn chính bằng thao tác atomic nếu filesystem hỗ trợ.
6. Nếu yêu cầu bền vững qua mất điện áp dụng cả cho thao tác đổi tên:
   cần xem cơ chế đồng bộ thư mục theo OS/filesystem.
```

Đây là **phác thảo giao thức**, không phải một lời hứa đa nền tảng. `Files.move(..., StandardCopyOption.ATOMIC_MOVE)` có nghĩa là yêu cầu thao tác move nguyên tử ở cấp filesystem; nó **không tự mang bảo đảm durability của directory entry**. Với `ATOMIC_MOVE`, hành vi thay đích đã tồn tại phụ thuộc implementation; không mặc định `REPLACE_EXISTING` kết hợp sẽ hoạt động giống trên mọi filesystem. Java chuẩn **không có một API di động bảo đảm fsync directory trên mọi hệ điều hành**. Nếu nghiệp vụ yêu cầu bảo vệ sau crash ở mức tên tệp, phải kiểm chứng kỹ platform và có thể cần API native/giao thức lưu trữ chuyên dụng.

## 4. Ví dụ chạy được: force sau khi hoàn thành ghi

Tạo file `ForceWriteDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class ForceWriteDemo {
    private static void writeAll(FileChannel channel, String text) throws IOException {
        ByteBuffer data = ByteBuffer.wrap(text.getBytes(StandardCharsets.UTF_8));
        while (data.hasRemaining()) {
            int n = channel.write(data);
            if (n == 0) throw new IOException("Write made no progress");
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("force-demo-", ".txt");
        try {
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                writeAll(channel, "first");
                channel.force(false);
                System.out.println("content-after-force-false=" +
                        Files.readString(file, StandardCharsets.UTF_8));
                System.out.println("size=" + channel.size());

                channel.truncate(0);
                channel.position(0);
                writeAll(channel, "second");
                channel.force(true);
                System.out.println("content-after-force-true=" +
                        Files.readString(file, StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 ForceWriteDemo.java
java ForceWriteDemo
```

Kết quả đã kiểm tra:

```text
content-after-force-false=first
size=5
content-after-force-true=second
```

**Phân tích**:

1. `Files.createTempFile` tạo một tệp mới. `FileChannel.open` mở kênh đọc/ghi.
2. `writeAll` lặp cho tới khi toàn bộ `ByteBuffer` được tiêu thụ, tránh mặc định một lệnh `write` ghi đủ bytes. Nếu ghi không tiến triển, ví dụ báo lỗi.
3. Sau khi ghi `first`, `force(false)` yêu cầu flush phần nội dung thuộc phạm vi `FileChannel`.
4. `size()` trả `5` byte vì văn bản ở ví dụ chỉ chứa 5 ký tự ASCII.
5. `truncate(0)` rút file về độ dài 0; `position(0)` đặt lại vị trí để ghi `second`. `force(true)` yêu cầu đồng bộ cả nội dung và metadata.
6. Đọc lại file giúp xác minh byte logic, **không phải bài kiểm thử chứng minh dữ liệu sẽ sống sót sau crash**. `force(true)` cũng không được coi là chứng cứ directory entry của file mới đã bền vững sau mất điện.

Chương trình sẽ ném `IOException` khi thao tác ghi/force gặp lỗi; đừng bắt exception rồi in thông báo “lưu thành công”. Dùng `try-with-resources` để đóng channel và `finally` để xóa file tạm trong ví dụ; quy tắc xóa sau khi kiểm thử không áp dụng cho file ứng dụng cần lưu dài hạn.

### Vì sao `force` phải ở đúng điểm cam kết?

Nếu ghi dữ liệu `A`, gọi `force`, rồi ghi tiếp `B`, việc force trước đó không hứa phần `B` đã được đồng bộ. Trong hệ thống ghi nhiều record, điểm gọi `force` là ranh giới cam kết được lựa chọn:

```text
write(record1)
write(record2)
force(true)    <- yêu cầu đồng bộ cho batch này
ACK batch      <- chỉ báo đã cam kết nếu force không ném lỗi
write(record3)
...            <- record3 chưa được cam kết bởi lần force trên
```

Điều này giả định ứng dụng có giao thức record rõ ràng, không có writer khác làm hỏng dữ liệu và underlying local filesystem/thiết bị thực hiện đúng các yêu cầu đồng bộ. **ACK** không phải dữ liệu tự động được Java phát ra; đó là quyết định của hệ thống dùng `force`.

## 5. Với memory-mapped file: phải nghĩ tới MappedByteBuffer.force

`FileChannel.map(FileChannel.MapMode.READ_WRITE, position, size)` tạo `MappedByteBuffer` trỏ đến một vùng của file. Khi sửa nội dung qua buffer đã map, sự thay đổi đi qua cơ chế memory mapping; Javadoc `FileChannel.force` **không cam kết mọi thay đổi do thao tác `put` trên mapped buffer đều được force**.

Dùng:

```java
MappedByteBuffer mapped = channel.map(FileChannel.MapMode.READ_WRITE, 0, size);
mapped.put(0, (byte) 'A');
mapped.force(); // yêu cầu đồng bộ thay đổi qua mapping
```

Đây là **đoạn minh họa** với `channel` đã mở READ/WRITE và `size` hợp lệ. Không thay `mapped.force()` bằng `channel.force(false)` chỉ vì mapped buffer được tạo từ channel đó. Cần nhớ rằng mapping có vòng đời có thể **dài hơn** file channel; đóng channel không tự giải phóng mapping ngay trên mọi platform.

### Ví dụ độc lập: ghi qua mapped buffer

Tạo `MappedForceDemo.java`:

```java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class MappedForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-force-", ".bin");
        try {
            Files.writeString(file, "0000", StandardCharsets.US_ASCII);
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                MappedByteBuffer mapped =
                        channel.map(FileChannel.MapMode.READ_WRITE, 0, 4);
                mapped.put(0, (byte) 'A');
                mapped.put(1, (byte) 'B');
                mapped.force();
                System.out.println("mapped-view=" +
                        StandardCharsets.US_ASCII.decode(mapped.duplicate().position(0)));
            }
        } finally {
            // Trên một số OS, mapping tồn tại lâu hơn channel.
            // File thử nghiệm được dọn khi hệ điều hành cho phép.
            try { Files.deleteIfExists(file); } catch (IOException ignored) { }
        }
    }
}
```

```bash
javac --release 17 MappedForceDemo.java
java MappedForceDemo
```

Kết quả đã kiểm tra:

```text
mapped-view=AB00
```

Ví dụ sửa hai byte trong mapping, gọi `mapped.force()` rồi đọc lại **view của chính buffer**. Kết quả `AB00` kiểm tra logic trong bộ nhớ ánh xạ; **không thể dùng output này chứng minh khả năng chống mất điện**. `duplicate().position(0)` đặt cursor của *buffer sao* về đầu, không tác động file pointer của channel. Khi dùng mapping trong ứng dụng dài hạn, kiểm soát kích thước vùng ánh xạ, tính nhất quán với writer khác, quyền truy cập và vòng đời tài nguyên.

## 6. SYNC, DSYNC và force khác nhau ở thời điểm yêu cầu đồng bộ

Java có tùy chọn mở file `StandardOpenOption.SYNC` và `StandardOpenOption.DSYNC`, phù hợp khi muốn đồng bộ thường xuyên:

| Cơ chế | Khi nào đồng bộ? | Ý nghĩa |
| --- | --- | --- |
| `FileChannel.force(false)` | **Tại điểm gọi force** | Yêu cầu đồng bộ nội dung file đã cập nhật thuộc phạm vi API. |
| `FileChannel.force(true)` | **Tại điểm gọi force** | Yêu cầu đồng bộ nội dung và metadata file. |
| `StandardOpenOption.DSYNC` | Theo mỗi cập nhật được thực hiện bằng kênh mở với option này | Yêu cầu cập nhật **nội dung** được ghi đồng bộ xuống thiết bị, theo hợp đồng NIO. |
| `StandardOpenOption.SYNC` | Theo mỗi cập nhật được thực hiện bằng kênh mở với option này | Yêu cầu cập nhật **nội dung và metadata** được ghi đồng bộ xuống thiết bị. |
| `MappedByteBuffer.force()` | **Tại điểm gọi force trên mapping** | Đồng bộ thay đổi của mapped buffer theo hợp đồng của nó. |

`SYNC` / `DSYNC` có thể tăng độ trễ và số thao tác I/O do cần đồng bộ liên tục. `force` cho phép gom nhiều ghi thành một batch trước khi đồng bộ (group commit) nhưng mở rộng số thay đổi chưa được force giữa hai lần cam kết. Không có lựa chọn “tốt nhất” độc lập với yêu cầu mất dữ liệu chấp nhận được, latency, throughput và filesystem.

```java
// Đoạn minh họa API: path là Path hợp lệ, writable.
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.SYNC)) {
    ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3});
    while (data.hasRemaining()) {
        int n = channel.write(data);
        if (n == 0) throw new IOException("Write stalled");
    }
}
```

Tùy chọn `SYNC` cần môi trường/implementation hỗ trợ; có thể phát sinh `UnsupportedOperationException` hoặc `IOException` tùy nguyên nhân. Đoạn trên minh họa cách lựa chọn mode, **không phải source Java độc lập** (cần import các lớp và khai báo `path`). Không tự thêm `APPEND` hay `TRUNCATE_EXISTING` khi nghiệp vụ không yêu cầu: chúng thay đổi semantics của file và điều kiện phục hồi.

### Có nên gọi force sau mỗi record?

Tùy mức cam kết:

- **Một record cần xác nhận ngay:** ghi đủ, force, rồi mới trả thành công nếu hợp đồng dữ liệu yêu cầu độ bền tới điểm đó.
- **Nhiều record có thể xác nhận theo batch:** ghi record và metadata phục hồi, force theo batch, ACK những record đã được bao gồm trong lần force hoàn tất.
- **Log hiệu năng cao:** dùng write-ahead log hoặc cơ chế durability của database chuyên dụng với nhóm commit/CRC/checkpoint; không thay thế protocol bằng một `force` tùy ý.

Việc `force` nhiều lần thường đắt hơn khi yêu cầu sync làm tăng latency; đo đúng môi trường, kể cả ổ NVMe, filesystem mạng, container và volume orchestration. Không hứa trước mức nhanh/chậm tuyệt đối.

## 7. Phạm vi bảo đảm qua hệ điều hành và loại thiết bị

| Môi trường | Có thể kết luận gì? | Điều cần kiểm chứng |
| --- | --- | --- |
| **Tệp trên local filesystem** như ext4/XFS/APFS/NTFS với storage device cục bộ | Javadoc `FileChannel.force` đưa ra hợp đồng force với thiết bị local cho các thay đổi được hỗ trợ. | OS, filesystem, driver, controller, cơ chế flush/cache và thực tế thiết bị có tuân thủ lệnh đồng bộ hay không. |
| **NFS/SMB/ổ mạng** | Java **không bảo đảm tương đương local device**. | Server thực sự cam kết ghi bền hay chỉ nhận vào cache; network reconnect, mount options, cơ chế đồng bộ bên server. |
| **Ổ ảo/cloud volume/container mount** | Đường truyền ghi có thể đi qua hypervisor, driver, lớp overlay, mạng hay thiết bị khác. | Cái được xem là local theo implementation; hợp đồng durability của tầng hạ tầng và những giới hạn riêng. |
| **Filesystem trong memory** như RAM-backed tmpfs | Việc đồng bộ API không biến dữ liệu volatile thành dữ liệu còn sau mất điện. | Mục tiêu tồn tại sau crash hay chỉ sau restart process? Thiết kế storage bền vững phù hợp. |
| **Thiết bị có write-back cache** | Dữ liệu có thể phải đi qua các cache của controller/SSD. | Power-loss protection, firmware và cơ chế flush mà thiết bị thật sự thực hiện. |

Bảng mô tả cách **đánh giá mức rủi ro**, không khẳng định mọi cấu hình được xếp đúng vào một loại vật lý đơn giản. Ví dụ volume cloud có thể hiển thị là block device “local” trước JVM nhưng backing storage thực tế được cung cấp qua mạng; cần tra đúng cam kết của dịch vụ lưu trữ.

Với ổ đĩa có cache không được bảo vệ khi mất nguồn, `force` không thể tự tạo bộ lưu điện hay sửa firmware gian dối. Ngược lại, trên thiết bị và filesystem tuân thủ lệnh flush, `force` là cách chuẩn Java bày tỏ yêu cầu đồng bộ dữ liệu. Câu “dữ liệu chắc chắn không thể mất” là phát biểu mạnh hơn hợp đồng Java và thực tế phần cứng.

### Crash của ứng dụng, crash OS và mất điện khác nhau

- **Tiến trình Java đột ngột dừng:** OS vẫn chạy, cache OS có thể tiếp tục được ghi ra đĩa. Đây **không** là bài kiểm thử đầy đủ cho force.
- **Kernel/system crash:** cache OS có thể biến mất hoặc chưa kịp đồng bộ; cơ chế force và filesystem recovery trở nên quan trọng.
- **Mất điện hoặc mất thiết bị:** còn phụ thuộc controller cache, storage firmware, hệ thống nguồn và thiết bị backing storage.

Do đó kiểm thử bằng cách `System.exit` hoặc kill process rồi thấy dữ liệu còn **không chứng minh** dữ liệu sẽ còn khi máy mất điện đúng thời điểm.

## 8. Những giới hạn không được suy diễn từ force

### Không bao phủ mọi đối tượng trong một giao dịch

Gọi `force(true)` trên file A không có nghĩa file B đã được flush. Hai file được cập nhật theo trình tự A → B có thể được phục hồi ở trạng thái chỉ một bên đã thay đổi nếu hệ thống gặp sự cố giữa chừng. Muốn cập nhật nhiều file như một đơn vị logic phải có transaction protocol như WAL, manifest + version, commit marker hoặc giải pháp database.

### Không bảo đảm thứ tự logic tự động khi có nhiều writer

Nếu các thread hoặc process cùng ghi, cần lock/ownership/offset độc lập hoặc cấu trúc record để tránh chồng lấn. `FileChannel.force` không khóa file, không ngăn task khác sửa file trong khi force và không cam kết một thứ tự giao dịch cấp ứng dụng. Xây dựng rõ “ai là writer”, “thời điểm nào coi record đã commit”, “khi khởi động lại phát hiện record dở như thế nào”.

### Không đảm bảo đọc ra trạng thái nhất quán nếu bản ghi đang được sửa

`Files.readString` sau `force` có thể nhìn thấy dữ liệu hợp lệ ở lần chạy bình thường, nhưng reader chạy trong lúc writer cập nhật nhiều offset có thể đọc kết hợp dữ liệu cũ và mới. Dùng snapshot, file tạm + rename, khóa đọc/ghi, hoặc phiên bản record với checksum/sequence nếu logic đòi hỏi một snapshot nhất quán.

### Không chứng minh full durability bằng một output test

Không tồn tại output chuẩn kiểu `"durable=true"` do `force` trả về. Ngoại lệ hoặc hoàn tất bình thường chỉ cho biết kết quả lời gọi trong điều kiện hiện tại. Một bài kiểm thử thực tế có thể xác minh readback nội dung, lỗi I/O, thời gian sync và phục hồi sau fault injection, nhưng không thể biến một lần test thành bảo đảm cho mọi ổ đĩa.

## 9. Quy trình lưu một bản ghi bền vững hơn

Một định dạng log record đơn giản có thể gồm:

```text
[magic/version][length][payload][checksum][commit marker/sequence]
```

Định dạng này chỉ là phác thảo: bố cục, checksum và trình tự commit phải được thiết kế để phân biệt record hoàn chỉnh với record dở sau crash. Một hệ thống có thể:

1. Cấp phát offset record và ghi phần header/payload/checksum đầy đủ; kiểm tra mọi lần write, short write và lỗi.
2. `force` những byte cần thiết theo giao thức, rồi ghi commit marker hoặc cập nhật manifest nếu thiết kế yêu cầu.
3. `force` lần cuối cho dữ liệu đánh dấu commit và metadata liên quan.
4. Chỉ ACK bản ghi sau khi force hoàn tất và giao thức nhất quán; nếu force lỗi, đánh dấu trạng thái chưa xác định/không xác nhận.
5. Khi khởi động lại, quét record hợp lệ theo length, checksum, version hoặc marker; dừng ở record không hoàn chỉnh và có chính sách repair.

Thứ tự đồng bộ thực tế phụ thuộc giao thức; ví dụ việc ghi marker và payload cùng một lần force không đảm bảo ứng dụng có thể bỏ qua partial/torn write nếu mất điện giữa chừng. Nên dùng giải pháp database/WAL sẵn có khi yêu cầu độ bền và recovery phức tạp.

## 10. Lỗi phổ biến và cách xử lý

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `write` trả số byte dương nên báo “đã lưu bền vững”. | Byte có thể chỉ đang trong OS cache. | Ghi đủ, gọi `force` tại điểm cam kết phù hợp, chỉ ACK khi hoàn tất. |
| Một lần `channel.write(buffer)` được xem là đủ. | FileChannel có thể ghi ngắn; buffer còn dữ liệu. | Kiểm tra `buffer.hasRemaining()` và lặp; kiểm tra `0`/exception. |
| `channel.force(false)` được coi tương đương `force(true)`. | False chỉ yêu cầu force nội dung; metadata có phạm vi khác. | Chọn theo cập nhật thực tế; phân biệt metadata file và directory entry. |
| `Files.writeString` rồi mở một channel khác chỉ để force và coi mọi ghi đều được bảo đảm. | Hợp đồng `FileChannel.force` giới hạn nguồn thay đổi được cam kết. | Dùng một writer/channel được quản lý nhất quán hoặc cơ chế sync rõ ràng của API sử dụng. |
| Dữ liệu thay bằng `mapped.put(...)` rồi chỉ gọi `channel.force`. | Force của channel không nhất thiết bao phủ cập nhật mapped buffer. | Gọi `mapped.force()` theo hợp đồng mapping. |
| `close`/`flush` thay cho force. | Khác về hợp đồng độ bền. | Dùng `FileChannel.force` hoặc `SYNC`/`DSYNC` khi yêu cầu đồng bộ file. |
| Gọi force trên file tạm rồi rename và coi cả tên file đã an toàn sau mất điện. | Ghi metadata thư mục/rename có hợp đồng riêng. | Kiểm tra atomic rename, fsync directory/cơ chế OS cụ thể khi cần đảm bảo tên tệp. |
| Dùng force như khóa hoặc transaction. | Không bảo vệ vùng byte chồng lấn hay read-modify-write. | Dùng lock/protocol cập nhật riêng; force sau khi đạt trạng thái nhất quán. |
| Cho rằng remote/network filesystem có bảo đảm như local. | Javadoc không hứa cùng semantics. | Xác minh server, provider, mount, dịch vụ lưu trữ. |
| Bỏ qua `IOException` khi force. | Không thể tuyên bố commit thành công sau lỗi sync. | Trả lỗi, ghi log có ngữ cảnh, phục hồi/đánh dấu trạng thái không xác định. |

### Xử lý lỗi đúng tại điểm force

```java
// Đoạn minh họa: channel đã mở và dữ liệu đã được ghi đầy đủ.
try {
    channel.force(true);
    // Chỉ tại đây mới có thể báo commit theo phạm vi bảo đảm của force.
} catch (IOException e) {
    // Không báo thành công; chuyển sang xử lý I/O failure/recovery.
    throw e;
}
```

Nếu exception xảy ra giữa force, **không thể tự suy ra rằng chưa byte nào tới storage**, cũng không thể khẳng định tất cả đã tới. Phải áp dụng chính sách khôi phục theo log/checksum/transaction id để tránh nhân đôi hoặc mất giao dịch sau retry.

## 11. Checklist trước khi đưa vào production

1. **Nội dung nào phải bền vững?** Byte payload, kích thước file, metadata, tên file sau rename, một hay nhiều file?
2. **Điểm cam kết ở đâu?** Trước hay sau ACK? Batch kích thước bao nhiêu? Mức mất dữ liệu chấp nhận được?
3. **Writer dùng API nào?** `FileChannel`, `FileOutputStream`/`RandomAccessFile.getChannel`, mapped memory hay một handle khác? Chọn force đúng phạm vi.
4. **Có ghi đủ chưa?** Kiểm tra short write, `ByteBuffer`, offset, chồng lấn và thứ tự ghi; force không sửa race.
5. **Storage là gì?** Local file, NFS/SMB, tmpfs, cloud volume, container overlay? Đọc cam kết của platform thay vì suy từ OS name.
6. **Cần atomicity và recovery không?** Nếu cần, thiết kế WAL/manifest/checksum, atomic rename và đồng bộ directory nếu được hỗ trợ.
7. **Lỗi force được xử lý thế nào?** Không ACK giả; log context, đánh dấu transaction chưa xác định và phục hồi an toàn.
8. **Hiệu năng ra sao?** Đo p95/p99 latency, throughput và số lần sync; cân nhắc `SYNC`, `DSYNC` hoặc group commit.
9. **Kiểm thử những mức lỗi nào?** Unit test kiểm chứng bytes, integration test trên file store mục tiêu, fault injection/crash recovery cho dữ liệu nghiệp vụ. Không coi readback hoặc kill JVM là phép chứng minh power-loss durability.
10. **Ai sở hữu tài nguyên?** Dùng `try-with-resources`, không đóng channel sớm khi task khác đang force/ghi; kiểm soát vòng đời của mapping.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Sau `channel.write(buffer)`, gọi `Files.readAllBytes(path)` thấy bytes mới. Đã chứng minh dữ liệu chống mất điện chưa?

**Chưa.** Việc đọc lại có thể dùng cache của OS. Cần cơ chế force/sync có hợp đồng phù hợp và kiểm chứng tầng lưu trữ.

**Câu 2.** `force(false)` có yêu cầu force metadata file không?

**Không.** Chỉ nội dung phải được force theo hợp đồng. `force(true)` yêu cầu nội dung và metadata, nhưng tác dụng thực tế của tham số phụ thuộc OS.

**Câu 3.** File lưu trên NFS có thể nhận cùng cam kết độ bền với local device từ Javadoc `FileChannel.force` không?

**Không.** Javadoc nói rõ nếu không phải local storage device thì không đưa ra bảo đảm tương đương; phải khảo sát semantics của server/OS/provider.

**Câu 4.** Nếu nội dung được thay đổi qua `MappedByteBuffer.put` thì nên dùng phương thức force nào?

**`MappedByteBuffer.force()`.** `FileChannel.force` có thể hoặc không đồng bộ những thay đổi tạo ra qua mapping.

**Câu 5.** `force(true)` có đảm bảo sau crash thao tác `Files.move(temp, final, ATOMIC_MOVE)` vẫn tồn tại dưới tên `final` không?

**Không thể suy ra chỉ từ `force(true)` của file.** Atomic move và bền vững của directory entry là những vấn đề khác; cần quy trình và kiểm chứng đặc thù filesystem/OS.

**Câu 6.** Muốn giảm số lần force, có thể gom 100 record thành batch và force một lần không?

**Có, nếu nghiệp vụ chấp nhận ranh giới cam kết của batch.** Phải ghi đủ, duy trì record format nhất quán, và chỉ ACK những record được bảo đảm sau lần force hoàn tất. Nếu ứng dụng sụp trước khi force, batch chưa được cam kết theo chính sách đó.

**Câu 7.** `force` có giải quyết hai writer cập nhật cùng offset không?

**Không.** Phải phối hợp writer/lock/protocol dữ liệu; force chỉ giải quyết yêu cầu đồng bộ thay đổi thuộc phạm vi của nó.

## Tài liệu chính thức

- Oracle Java SE 21 — [`FileChannel`: `force(boolean)`, các phương thức write, map và lock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html).
- Oracle Java SE 21 — [`MappedByteBuffer`: `force()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/MappedByteBuffer.html).
- Oracle Java SE 21 — [`StandardOpenOption`: `SYNC` và `DSYNC`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- Oracle Java SE 21 — [`Files`: `newByteChannel` / `move` và `ATOMIC_MOVE`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).

**Kết luận cần vận dụng:** `FileChannel.force` là yêu cầu đồng bộ thay đổi file xuống thiết bị lưu trữ trong phạm vi hợp đồng của Java; `metaData` điều khiển phạm vi content/metadata. Để đạt một hệ thống lưu trữ bền vững thực sự, phải kết hợp force đúng điểm cam kết với ghi đầy đủ, định dạng có thể phục hồi, phối hợp writer, và kiểm chứng OS/filesystem/hạ tầng mà ứng dụng triển khai.
# `force()` cho thay đổi trên vùng ánh xạ bộ nhớ (Java NIO)

## 1. Bài toán: thay đổi trong memory-mapped file đã được lưu bền vững chưa?

Với Java NIO, `FileChannel.map(...)` ánh xạ một phần tệp vào bộ nhớ và trả về `MappedByteBuffer`. Ta có thể thay đổi nội dung thông qua `mapped.put(...)`, `mapped.putInt(...)` hoặc các phương thức ghi của `ByteBuffer`. Điều quan trọng là **byte mới đã nhìn thấy trong bộ nhớ không đồng nghĩa hệ thống lưu trữ đã nhận yêu cầu ghi bền vững các byte đó**.

Ví dụ, ứng dụng ghi một bản ghi nhị phân trực tiếp trên vùng ánh xạ:

~~~java
// Minh họa: channel mở để đọc và ghi, vùng map đủ dài.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 4096);
mapped.putInt(100, 42);
mapped.force();
~~~

Phương thức `force()` yêu cầu ghi những thay đổi đối với nội dung mapped buffer xuống thiết bị lưu trữ. Đây là điểm mấu chốt khi cần xác định **checkpoint lưu dữ liệu**, thay vì chờ hệ điều hành tự đẩy các trang bẩn (dirty pages) theo lịch của nó.

Cần phân biệt:

- **Thay đổi trong mapping:** ứng dụng đã sửa nội dung nhìn qua buffer; các trang nhớ có thể còn chưa được ghi bền vững.
- **`force()` trả về thành công:** đối với tệp trên **thiết bị lưu trữ cục bộ**, đặc tả Java đưa ra bảo đảm rằng những thay đổi thuộc phạm vi force đã được ghi tới thiết bị.
- **Tính nhất quán giao dịch khi crash:** là bài toán rộng hơn. `force()` không tự cung cấp atomic transaction, isolation, rollback, checksum, journal hay cơ chế phục hồi nhiều bước.

Bài này tập trung vào `MappedByteBuffer.force()` và `force(int index, int length)`, so sánh với `FileChannel.force(boolean)`, phân tích những giới hạn và đưa ra ví dụ Java 17+ chạy độc lập.

## 2. Ánh xạ file tạo ra vùng byte nào?

Để tạo mapping, dùng:

~~~java
MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_WRITE, 4L, 8L);
~~~

`4L` là **offset tính theo byte trong file**, `8L` là số byte được ánh xạ. Buffer trả về có `position=0`, `limit=8`, `capacity=8` (mark ban đầu không được đặt).

~~~text
File offset:      0  1  2  3 |4  5  6  7  8  9 10 11|12 13
                              vùng ánh xạ 8 byte
Buffer index:                 0  1  2  3  4  5  6  7
                              ^                 ^
                          index đầu          index cuối
~~~

Bảng quy đổi:

| Buffer index | File offset khi map từ offset 4 |
|---:|---:|
| 0 | 4 |
| 1 | 5 |
| 4 | 8 |
| 7 | 11 |

Như vậy `mapped.putInt(0, value)` ghi vào **file byte 4–7**; `mapped.putInt(4, value)` ghi vào **file byte 8–11**. Index truyền vào `putInt(index, ...)` hay `force(index, length)` là **index của mapped buffer**, không phải offset file tuyệt đối.

`MappedByteBuffer` kế thừa khả năng truy cập tương đối và tuyệt đối từ `ByteBuffer`. Lệnh `putInt(index, value)` **không thay đổi position**, còn `putInt(value)` tương đối sử dụng position hiện tại và dịch position đi bốn byte.

### Ba chế độ `FileChannel.MapMode`

| Mode | Có ghi qua mapped buffer không? | Ảnh hưởng tới file thật | Tác dụng của `force()` |
|---|---|---|---|
| `READ_ONLY` | Không; `put(...)` ném `ReadOnlyBufferException` | Không có thay đổi qua buffer | Không có tác dụng |
| `READ_WRITE` | Có | Những thay đổi được truyền về file, thời điểm do hệ thống quyết định | **Yêu cầu ghi bền vững thay đổi của mapping** |
| `PRIVATE` | Có, theo copy-on-write | Thay đổi nằm trong bản sao private, **không truyền về file gốc** | Không có tác dụng với việc lưu thay đổi private vào file |

`READ_WRITE` và `PRIVATE` cần `FileChannel` mở cho **đọc và ghi**; `READ_ONLY` yêu cầu quyền đọc. Gọi `force()` trên mapping `PRIVATE` không biến thay đổi riêng thành dữ liệu ghi vào tệp gốc.

## 3. Hợp đồng của `MappedByteBuffer.force()`

Chữ ký trong Java 17:

~~~java
public final MappedByteBuffer force()
~~~

Đặc điểm quan trọng:

1. Yêu cầu ép những thay đổi của **nội dung mapped buffer** ra thiết bị chứa file.
2. Phạm vi là **toàn bộ `[0, capacity())`**, tương đương `force(0, capacity())`. Nó **không chỉ xử lý đoạn `[position, limit)`**.
3. Nếu file nằm trên **local storage**, Java bảo đảm khi phương thức trả về thành công, thay đổi thuộc phạm vi được yêu cầu từ khi buffer được tạo hoặc từ lần force tương ứng trước đó đã được ghi tới thiết bị.
4. Nếu file ở **non-local storage** (ví dụ một số hệ thống file mạng), đặc tả không đưa ra cùng bảo đảm.
5. Với `READ_ONLY` và `PRIVATE`, phương thức không có tác dụng; các mode triển khai đặc thù có thể có hành vi khác.
6. Nó trả về **chính `MappedByteBuffer`**, không trả về số byte flush hay boolean.
7. Lỗi I/O trong khi ghi nội dung có thể dẫn tới **`UncheckedIOException`**.

### Force không đổi position, limit hoặc capacity

~~~java
// Ví dụ minh họa: mapped đã ánh xạ READ_WRITE 128 byte.
mapped.put(10, (byte) 7);
mapped.position(100);
mapped.limit(101);
mapped.force();
~~~

Vùng đồng bộ được yêu cầu là **toàn mapping [0,128)**, không phải chỉ byte 100. Sau force, `position()` vẫn là 100 và `limit()` vẫn là 101. `force()` không thay mark hay di chuyển vị trí đọc/ghi để thực hiện việc đồng bộ.

**Lưu ý:** một chương trình đọc lại byte đã sửa ngay sau `put` hoặc `force` chỉ chứng minh dữ liệu nhìn thấy có giá trị đúng trong phiên đó. Đọc lại thành công **không phải bài kiểm tra mô phỏng mất điện**.

## 4. `force(index, length)`: ép ghi thay đổi của một vùng con

Java 17 hỗ trợ overload:

~~~java
public final MappedByteBuffer force(int index, int length)
~~~

- `index` là **index bắt đầu trong mapped buffer**.
- `length` là **số byte** của vùng yêu cầu.
- Vùng nửa mở: **`[index, index + length)`**.
- Phải có `index >= 0`, `length >= 0` và `index <= capacity() - length`. Tham số không hợp lệ gây **`IndexOutOfBoundsException`**.
- Phương thức không thay `position`/`limit`. Nó không bắt buộc hệ thống chỉ ghi đúng những byte được chọn: có thể ghi thêm byte lân cận do kích thước trang nhớ hoặc block thiết bị.

Ví dụ mapping dài 16 byte:

~~~java
// Ví dụ minh họa: mapped là READ_WRITE, capacity >= 16.
mapped.put(2, (byte) 0x11);
mapped.put(3, (byte) 0x22);
mapped.put(10, (byte) 0x33);
mapped.put(11, (byte) 0x44);

mapped.force(2, 2);   // Yêu cầu đồng bộ vùng [2,4).
mapped.force(10, 2);  // Yêu cầu đồng bộ vùng [10,12).
~~~

Hai lần force có các **vùng bắt buộc** khác nhau; không suy ra byte ngoài vùng được chọn chắc chắn chưa xuống thiết bị. OS có thể ghi nhiều hơn.

### Quy đổi phạm vi khi mapping bắt đầu từ giữa file

Giả sử `FileChannel.map(READ_WRITE, 4096, 2048)`.

| Lệnh | Vùng buffer | File byte tương ứng |
|---|---|---|
| `force(0, 128)` | [0,128) | [4096,4224) |
| `force(512, 256)` | [512,768) | [4608,4864) |
| `force()` | [0,2048) | [4096,6144) |

Các chỉ số đều tính theo byte. Java xử lý chi tiết page/block của hệ thống; không tự cộng offset file vào tham số `force(index,length)`.

### Chọn force toàn vùng hay từng vùng?

`force()` đơn giản và không cần theo dõi danh sách dirty ranges. `force(index,length)` diễn đạt chính xác phạm vi muốn đồng bộ, có thể phù hợp khi chỉ sửa vài bản ghi trong mapping lớn. **Đừng tự kết luận** overload vùng con luôn nhanh hơn trên mọi OS và mọi thiết bị; kernel có thể làm việc theo page lớn hơn vùng chỉ định. Hiệu năng cần đo bằng workload thực tế.

## 5. Chương trình Java 17+ chạy được

Chương trình tạo tệp tạm 16 byte, ánh xạ 8 byte từ file offset 4, ghi hai số nguyên, yêu cầu force một phần rồi toàn bộ, kiểm tra trạng thái buffer và đọc lại nội dung file dưới dạng hex.

Lưu file **`MappedForceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class MappedForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mapped-force-", ".bin");
        Files.write(file, new byte[16]);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            // Buffer index 0..7 tương ứng file offset 4..11.
            MappedByteBuffer mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE, 4, 8);

            mapped.putInt(0, 0x01020304);
            mapped.putInt(4, 0x0A0B0C0D);

            // Cố tình giới hạn vùng dùng cho get/put tương đối.
            mapped.position(6);
            mapped.limit(7);

            System.out.println("state=" + mapped.position()
                    + "/" + mapped.limit()
                    + "/" + mapped.capacity());

            // Yêu cầu ghi index 0..3, tương ứng file offset 4..7.
            mapped.force(0, 4);
            System.out.println("partial-force-done");

            // Yêu cầu ghi mọi thay đổi của mapping.
            mapped.force();
            System.out.println("full-force-done");

            System.out.println("state-after=" + mapped.position()
                    + "/" + mapped.limit()
                    + "/" + mapped.capacity());
        }

        byte[] actual = Files.readAllBytes(file);
        System.out.println("file-hex=" + HexFormat.of().formatHex(actual));

        // Thử dọn khi kết thúc JVM: mapping có thể còn hiệu lực
        // sau khi FileChannel đã đóng (tùy GC/OS).
        file.toFile().deleteOnExit();
    }
}
~~~

Biên dịch và chạy trong thư mục chứa source:

~~~bash
javac MappedForceDemo.java
java MappedForceDemo
~~~

**Stdout khi I/O thành công:**

~~~text
state=6/7/8
partial-force-done
full-force-done
state-after=6/7/8
file-hex=00000000010203040a0b0c0d00000000
~~~

Giải thích từng phần:

1. File ban đầu 16 byte bằng 0; mapping từ offset 4 với size 8.
2. `putInt(0, 0x01020304)` thay byte file 4–7 bằng `01 02 03 04`, còn `putInt(4, 0x0A0B0C0D)` thay byte file 8–11 bằng `0A 0B 0C 0D`. `ByteBuffer` dùng **big-endian** mặc định.
3. Hai lệnh `putInt(index, value)` là truy cập tuyệt đối và không dịch `position`. Chương trình đặt `position=6, limit=7, capacity=8`.
4. `force(0,4)` áp dụng vùng đầu; `force()` áp dụng toàn bộ 8 byte bất kể limit đang là 7.
5. Sau force, trạng thái `6/7/8` được giữ nguyên.
6. Kết quả hex thể hiện bốn byte 0 đầu tiên, tám byte đã cập nhật và bốn byte 0 cuối.

**Điều chương trình kiểm tra:** nội dung và trạng thái buffer. **Điều chương trình không kiểm tra:** khả năng phục hồi sau crash, tính nguyên tử của nhiều lần put và mức bảo đảm của remote storage.

### Vòng đời mapping và tệp tạm

`try-with-resources` đóng `FileChannel`. Nhưng `MappedByteBuffer` và mapping có thể tồn tại **sau khi channel đóng**, tới khi buffer được thu gom rác. Không có phương thức `unmap()` công khai chuẩn trên `MappedByteBuffer` trong Java 17. Trên một số OS, thao tác xóa/truncate tệp đang còn mapping có thể gặp hạn chế. `deleteOnExit()` là nỗ lực dọn khi JVM kết thúc, không phải cam kết xóa file ngay khi đóng channel.

## 6. Khác biệt quan trọng với `FileChannel.force(boolean)`

`MappedByteBuffer.force()` và `FileChannel.force(boolean)` phục vụ **hai đường thay đổi dữ liệu**:

| API | Phạm vi yêu cầu | Metadata | Có đảm bảo force các byte sửa bằng `mapped.put(...)`? |
|---|---|---|---|
| `mapped.force()` | Toàn bộ nội dung mapped region | Không có tham số metadata | **Có**, trong phạm vi và điều kiện của API |
| `mapped.force(index,length)` | Một phần mapped region | Không có tham số metadata | **Có** với phần vùng chỉ định |
| `channel.force(false)` | Các cập nhật nội dung file qua API channel theo hợp đồng | Không yêu cầu metadata | **Không được bảo đảm** |
| `channel.force(true)` | Các cập nhật nội dung **và metadata** qua API channel theo hợp đồng | Có yêu cầu metadata | **Vẫn không được bảo đảm** |

Theo tài liệu `FileChannel.force(boolean)`, phương thức **chỉ được bảo đảm** ép ghi những thay đổi file được thực hiện bằng các phương thức thuộc hợp đồng của `FileChannel` (và các trường hợp liên quan được đặc tả). Nó **có thể** hoặc **không** ép ghi thay đổi thực hiện thông qua một mapped byte buffer tạo bởi `map(...)`.

~~~java
// Ví dụ minh họa: mapped và channel đều hợp lệ.
mapped.put(10, (byte) 99);

channel.force(true); // Không thay thế bảo đảm force mapped buffer.
mapped.force();       // Phương thức phù hợp cho thay đổi bằng mapped.put.
~~~

**Đừng suy ra `channel.force(true)` là bản nâng cấp bao quát mọi dạng ghi.** Tham số `true` yêu cầu đồng bộ metadata theo phạm vi của `FileChannel`, nhưng không biến nội dung mapped buffer thành các thay đổi được bảo đảm flush qua channel.

Nếu ứng dụng vừa sửa nội dung mmap vừa cập nhật metadata hoặc ghi trực tiếp bằng channel, cần thiết kế chính sách đồng bộ cho **từng đường cập nhật**. Ngoài ra, việc tạo file, đổi tên, sửa directory entry hay commit nhiều tệp liên quan có thể cần quy tắc bổ sung tùy OS và filesystem.

## 7. `load()` và `isLoaded()` không phải cách lưu bền vững

Ba API có mục tiêu khác nhau:

- `mapped.load()`: cố gắng (best-effort) đưa các trang của mapping vào **physical memory** để giảm page fault khi truy cập, **không phải flush ra thiết bị**.
- `mapped.isLoaded()`: trả về một gợi ý trang mapped có khả năng đang ở bộ nhớ vật lý; thông tin này có thể thay đổi ngay sau khi kiểm tra.
- `mapped.force()`: yêu cầu đưa **các thay đổi mapped** xuống thiết bị.

~~~java
// Mã minh họa.
mapped.load();                   // Hỗ trợ đưa dữ liệu từ file vào memory.
boolean likelyLoaded = mapped.isLoaded();

mapped.put(0, (byte) 7);
mapped.force();                  // Yêu cầu ghi thay đổi vào storage.
~~~

`isLoaded()==true` không chứng minh dirty data đã bền vững. `load()` gọi sau khi put cũng không thay thế `force()`.

## 8. Giới hạn của độ bền sau khi force

### 8.1. Thiết bị local và remote khác nhau

Java 17 quy định bảo đảm khi `MappedByteBuffer.force()` thành công **nếu file ở thiết bị lưu trữ cục bộ**. Đối với storage không phải local (ví dụ một số network filesystem), Java **không bảo đảm tương tự**. Nếu dữ liệu đi qua network cache, replication hoặc cloud volume, mức bền vững phải dựa vào hợp đồng và triển khai của hệ lưu trữ đó.

### 8.2. Không có tính nguyên tử cho nhiều lần cập nhật

~~~java
mapped.putInt(0, newValue);
mapped.putInt(4, newChecksum);
mapped.force();
~~~

*Đây là đoạn minh họa* có hai giá trị đã định nghĩa. Nếu tiến trình crash sau lệnh `putInt` đầu nhưng trước lệnh tiếp theo, định dạng có thể không nhất quán. `force()` cũng không tự làm hai trường được cập nhật **đồng thời** với các reader.

Với dữ liệu quan trọng, cân nhắc version, checksum, write-ahead log, double buffering, commit marker và cơ chế phục hồi. Chỉ force **không có rollback**.

### 8.3. Nội dung khác với metadata

`MappedByteBuffer.force()` bảo đảm về **nội dung vùng ánh xạ** theo điều kiện đã nêu. Nó không có tùy chọn `metaData=true`. Nếu chương trình mở rộng tệp, tạo file mới, sửa thuộc tính hay đổi tên, không được kết luận một lời gọi `mapped.force()` đã khiến mọi metadata và directory entry liên quan bền vững trong mọi trường hợp.

### 8.4. Concurrent writer và truncate

Một mapped buffer có thể bị tác động bởi chương trình hoặc thread khác. Nếu file nền bị truncate trong khi mapping đang sống, một phần vùng mapped có thể trở nên **không truy cập được**; đặc tả cho phép xảy ra ngoại lệ không được chỉ định cụ thể tại thời điểm truy cập hoặc sau đó. Vì vậy, cần:

- Phối hợp quyền sửa/truncate file trong suốt thời gian còn mapping.
- Kiểm soát nhiều writer đụng cùng byte/record, bằng lock hoặc giao thức đồng bộ phù hợp.
- Không xem `force()` là file lock hay một transaction đảm bảo isolation.
- Không dùng việc có thể đọc lại giá trị mới như chứng cứ rằng đồng thời và crash consistency đã được giải quyết.

## 9. Mốc force: mỗi bản ghi hay theo batch?

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| `force()` sau từng cập nhật quan trọng | Có checkpoint bền vững sớm sau mỗi cập nhật thành công | Tăng số lượt yêu cầu I/O |
| `force()` sau nhóm cập nhật | Ít lời gọi, có thể cải thiện throughput | Thay đổi sau checkpoint cuối có thể chưa bền vững khi crash |
| `force(index,length)` trên vùng dirty | Diễn đạt chính xác vùng cần đồng bộ | Phải tính chính xác index; OS có thể ghi theo page rộng hơn |
| Không chủ động force | Ít chi phí đồng bộ tức thời | Không có mốc bảo đảm từ `MappedByteBuffer.force` |

**Không tồn tại quy tắc “force càng nhiều càng đúng trong mọi trường hợp”.** Chọn checkpoint theo yêu cầu mất dữ liệu tối đa có thể chấp nhận, trạng thái transaction của ứng dụng và hiệu năng trên thiết bị thực tế. Đặc biệt không giả định `force(index,length)` luôn nhanh hơn `force()`: dirty pages, page size, hệ thống tệp và bộ điều khiển I/O có thể làm khác nhau.

### Khi có nhiều vùng mapped hoặc view

Một file có thể được map thành nhiều `MappedByteBuffer` với các phạm vi khác nhau. Khi cần force phần đã sửa, xác định **mapping sở hữu vùng** và index **tương đối với mapping ấy**. Tránh gọi force trên một mapping không liên quan rồi cho rằng tất cả thay đổi của mapping khác đều đã đạt cùng bảo đảm.

Với `slice()` và `duplicate()`, các view có thể chia sẻ dữ liệu nền nhưng giữ position/limit riêng. Phạm vi index của một view phải được tính theo chính view đó; nếu ứng dụng quản lý việc đồng bộ qua mapping gốc, cần chuyển đổi chỉ số về đúng vùng file.

## 10. Xử lý lỗi: đừng báo thành công nếu force thất bại

Các tình huống cần lưu ý:

| Tình huống | Hậu quả/ngoại lệ |
|---|---|
| `force(index,length)` vượt capacity hoặc chỉ số âm | `IndexOutOfBoundsException` |
| Lỗi I/O khi flush mapped region | `UncheckedIOException` |
| `put(...)` lên mapping `READ_ONLY` | `ReadOnlyBufferException` |
| File bị truncate, vùng mapped không còn truy cập được | Có thể xuất hiện ngoại lệ do nền tảng, không được API xác định cụ thể |
| `force()` trên mapping `PRIVATE` | Không ghi thay đổi private về file thật |
| `FileChannel.map(...)` với quyền/điều kiện file không hợp lệ | Có thể ném lỗi quyền, `IOException` hoặc lỗi tham số tùy trường hợp |

Đoạn minh họa xử lý force:

~~~java
try {
    mapped.putInt(recordIndex, value);
    mapped.force(recordIndex, Integer.BYTES);
} catch (java.io.UncheckedIOException e) {
    // Không xác nhận độ bền của bản ghi này.
    // Báo lỗi để tầng ứng dụng quyết định recovery/retry.
    throw e;
}
~~~

Ngoại lệ trên chỉ xử lý **lỗi đồng bộ I/O**; thao tác ghi hoặc index có thể thất bại theo cách khác. Nếu ứng dụng retry, cần thiết kế idempotency và xử lý cạnh tranh trước.

### Kiểm chứng nội dung và độ bền là hai loại test

- **Test nội dung:** tạo file tạm, map, put, force, đóng channel, đọc lại bytes và so sánh với kỳ vọng. Đây là test hợp lệ cho hành vi đọc/ghi, như chương trình ở mục 5.
- **Test lỗi:** giả lập lỗi đường lưu trữ ở abstraction phù hợp; chắc chắn ứng dụng không gắn trạng thái commit thành công khi force thất bại.
- **Test khôi phục crash:** cần môi trường kiểm soát crash/reboot, sau đó kiểm tra dữ liệu/metadata và phục hồi. Đây là lớp test mạnh hơn; đọc lại file ngay trong JVM hiện tại **không chứng minh** điều này.
- **Test đồng thời:** nhiều writer truy cập chung mapping, thử những thứ tự thực thi khó để xác nhận giao thức lock/record không hỏng.

## 11. Lỗi thường gặp

| Sai lầm | Cách sửa |
|---|---|
| “`put(...)` nghĩa là lưu bền” | `put` sửa vùng nhớ mapped; khi cần checkpoint, gọi `MappedByteBuffer.force()`. |
| “`FileChannel.force(true)` luôn flush mọi mmap” | Không được đặc tả bảo đảm; dùng `mapped.force()` cho thay đổi mapped. |
| “`force()` chỉ xử lý từ position đến limit” | Nó xử lý toàn vùng [0,capacity); dùng overload nếu muốn chọn đoạn con. |
| “Tham số index trong `force(index,length)` là offset file” | Index tương đối với buffer; cộng offset mapping khi diễn giải file. |
| “Force vùng con chỉ ghi chính xác vùng con đó” | OS có thể ghi nhiều byte hơn do page/block. |
| “`load()` đồng nghĩa flush” | `load()` phục vụ prefetch vào memory; `force()` phục vụ ghi từ mapping xuống storage. |
| “`MapMode.PRIVATE` có thể force để cập nhật file gốc” | Thay đổi copy-on-write không truyền về file thật. |
| “Force tạo transaction hai bước” | Cần protocol/lock/version/log riêng. |
| “Đóng FileChannel làm mapping bị hủy ngay” | Mapping có vòng đời độc lập với channel. |
| “Force trả về trên network filesystem có cùng bảo đảm như local” | Java không bảo đảm như vậy. |

## 12. Tình huống tự kiểm tra

1. `map(READ_WRITE, 1000, 100)` rồi `force(10,5)`: file byte nào thuộc vùng yêu cầu? **[1010,1015)**.
2. `position=70, limit=80, capacity=100` rồi `force()`: phạm vi nào? **[0,100)**. Position/limit vẫn 70/80.
3. Capacity 100, gọi `force(98,4)`: kết quả? **`IndexOutOfBoundsException`**.
4. Mapping `PRIVATE` được sửa rồi force: file gốc có được lưu thay đổi private không? **Không**.
5. Gọi `mapped.load()` sau khi put có thể thay force không? **Không**.
6. `channel.force(true)` sau `mapped.put(...)` đã đủ bảo đảm chưa? **Không được bảo đảm bởi API**, nên force trên mapped buffer.
7. Nếu force thành công với local file, chương trình có thêm tính nguyên tử cho hai lệnh `putInt` không? **Không**.
8. File mạng có bảo đảm force tương tự local không? **Không theo đặc tả Java 17**.
9. Buffer đã map nhưng channel đóng, mapping có chắc biến mất ngay không? **Không**.
10. Đọc lại đúng byte sau force có chứng minh khả năng phục hồi sau mất điện không? **Không**.

## 13. Tham khảo chính thức

- [Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): `force()`, `force(index,length)`, ngoại lệ, các điều kiện bảo đảm local/remote, `load()` và `isLoaded()`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `map(...)`, các `MapMode` và sự khác biệt giữa `force(boolean)` với force của mapped buffer.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): vị trí/giới hạn, truy cập index tuyệt đối, `putInt` và thứ tự byte.

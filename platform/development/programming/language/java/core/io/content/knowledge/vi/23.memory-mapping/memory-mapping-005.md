# MappedByteBuffer.load(), isLoaded() và tác động của page fault

## 1. Hiểu đúng về memory-mapped file

Trong Java NIO, `FileChannel.map(...)` tạo một `MappedByteBuffer` để truy cập một vùng của tệp như bộ nhớ. Vùng mapping nằm trong **không gian địa chỉ ảo** của tiến trình. Điều này không đồng nghĩa tất cả byte đã được sao chép ngay vào RAM.

Khi đọc `mapped.get(index)`, hệ điều hành xác định trang chứa dữ liệu có ở bộ nhớ vật lý và đã được ánh xạ phù hợp chưa. Nếu chưa, có thể xảy ra **page fault**; kernel xử lý sự kiện, có thể lấy dữ liệu từ bộ nhớ cache hoặc thực hiện I/O tới thiết bị trước khi CPU tiếp tục truy cập.

Các khái niệm quan trọng:

- **Mapping:** liên kết địa chỉ ảo với nội dung một vùng tệp.
- **Resident page:** trang dữ liệu hiện đang có trong bộ nhớ vật lý.
- **Page fault:** sự kiện do cơ chế bộ nhớ ảo yêu cầu kernel xử lý trang/ánh xạ.
- **`load()`:** cố gắng nạp nội dung mapped buffer vào bộ nhớ vật lý (best effort).
- **`isLoaded()`:** trả lời bằng một gợi ý về trạng thái resident, không phải bảo đảm.

Hai phương thức cuối là chủ đề chính. **`load()` không cam kết loại bỏ page fault tương lai; `isLoaded()` không cam kết một kết luận residency chính xác tuyệt đối.**

## 2. Vì sao có page fault khi đã gọi map?

Ví dụ minh họa:

~~~java
try (FileChannel channel = FileChannel.open(path, StandardOpenOption.READ)) {
    MappedByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size());
    byte first = mapped.get(0);
}
~~~

Đoạn trên **không phải chương trình độc lập**: cần có `Path path` hợp lệ, các import cần thiết, và kích thước tệp phù hợp giới hạn mapping. Sau `map`, OS mới có thể thiết lập metadata ánh xạ mà chưa phải đưa đủ nội dung vào RAM.

Luồng truy cập phổ biến:

~~~text
FileChannel.map(...)
     |
     v
Địa chỉ ảo ↔ vùng dữ liệu tệp
     |
     v
mapped.get(offset)
     |
     +-- Trang resident và đã được map --> CPU đọc nhanh
     |
     +-- Trang cần page fault -----------+
                                         |
                         Kernel xử lý ánh xạ/trang
                              |          |
                      Dữ liệu ở RAM    Cần I/O từ storage
                              |          |
                              +----+-----+
                                   |
                           Lệnh đọc tiếp tục
~~~

Đây là sơ đồ khái niệm. Một page fault hợp lệ thường được kernel giải quyết rồi chương trình tiếp tục; không phải cứ có page fault là Java ném `Exception`.

### 2.1. Minor và major page fault

- **Minor/soft page fault:** cần cập nhật trạng thái ánh xạ nhưng dữ liệu đã có sẵn trong bộ nhớ, ví dụ trong **OS page cache**; không nhất thiết phải đọc đĩa.
- **Major/hard page fault:** cần chờ I/O để trang dữ liệu được cung cấp; có khả năng gây độ trễ lớn hơn.
- **Trang resident sẵn:** CPU có thể truy cập mà không cần fault mới tại thời điểm đó.

Phân loại và bộ đếm cụ thể mang tính hệ điều hành. **Không phải mỗi fault là một lần đọc đĩa**; page cache, filesystem readahead và những ứng dụng khác có thể khiến dữ liệu sẵn trong RAM.

### 2.2. Mapping, heap và page cache

`MappedByteBuffer` là một **direct byte buffer** đại diện cho vùng ánh xạ tệp, khác với việc tạo một `byte[]` nằm trên Java heap bằng `Files.readAllBytes`. Khi map một file, kernel có thể trì hoãn đưa dữ liệu vào bộ nhớ vật lý cho đến lần truy cập đầu. OS cũng có thể tự readahead các trang tiếp theo khi phát hiện truy cập tuần tự.

Việc dùng `MappedByteBuffer` không bỏ qua bộ nhớ ảo, không tự khóa RAM, và không làm dữ liệu trở nên miễn nhiễm với eviction.

## 3. Hợp đồng chính xác của MappedByteBuffer.load()

Java 17 định nghĩa:

~~~java
public final MappedByteBuffer load()
~~~

Theo Javadoc, phương thức **best effort** để nội dung buffer resident trong bộ nhớ vật lý lúc nó trả về. Nó có thể tự phát sinh **page faults và I/O** trong quá trình gọi.

Điều được phép kỳ vọng:

1. Hệ thống sẽ cố gắng chuẩn bị các trang của vùng mapped buffer.
2. Lời gọi có thể tiêu tốn thời gian do nạp dữ liệu; đây là bước prefetch/warm-up chủ động.
3. Phương thức trả lại **chính buffer nhận lời gọi** để có thể tiếp tục sử dụng.

Điều **không** được đảm bảo:

1. Mọi trang thật sự resident sau lời gọi.
2. Các trang sẽ tiếp tục ở trong RAM khi ứng dụng truy cập sau đó.
3. Mọi thao tác `get` tiếp theo không có page fault.
4. Lời gọi sẽ nhanh hoặc tăng hiệu năng end-to-end trong mọi workload.
5. Trang dữ liệu được khóa vĩnh viễn trong RAM.
6. Nội dung sửa đổi đã được lưu bền vững xuống thiết bị.

Ví dụ:

~~~java
MappedByteBuffer mapped =
        channel.map(FileChannel.MapMode.READ_ONLY, offset, length);

// Chuẩn bị trước: best effort page-in.
mapped.load();

// Không có bảo đảm thao tác dưới đây sẽ không fault.
byte value = mapped.get(0);
~~~

Đây là mã minh họa cần biến `FileChannel channel`, `long offset` và `long length` thích hợp.

`load()` không tạo `byte[]` và không thay đổi nội dung file. Nó cũng **không phải** `MappedByteBuffer.force()`; `force()` liên quan đến flush thay đổi ra storage.

## 4. Hợp đồng chính xác của MappedByteBuffer.isLoaded()

Java 17 định nghĩa:

~~~java
public final boolean isLoaded()
~~~

`isLoaded()` trả về **hint** về việc nội dung mapped buffer có ở bộ nhớ vật lý hay không:

- Nếu **`true`**: có khả năng cao toàn bộ nội dung buffer đang resident và nhiều truy cập có thể không cần fault/I/O.
- Nếu **`false`**: **không chứng minh** dữ liệu chưa có trong RAM. OS/provider có thể dùng heuristic hoặc không khẳng định residency.
- Với **cả hai kết quả**: ngay sau khi phương thức trả về, OS có thể đã page-out/evict một số dữ liệu. Không có bảo đảm cho lần truy cập tiếp theo.

Ví dụ sai cần tránh:

~~~java
mapped.load();
if (!mapped.isLoaded()) {
    throw new IllegalStateException("load thất bại");
}
~~~

Đây là **mã phản ví dụ**: `false` sau `load()` là hoàn toàn hợp lệ theo hợp đồng Java. Không nên coi hai phương thức này là giao thức xác nhận thành công/thất bại.

### 4.1. Những cặp giá trị đều hợp lệ

| isLoaded trước load | isLoaded sau load | Hợp lệ? | Vì sao? |
|---|---|---|---|
| `false` | `true` | Có | Trang có thể đã được chuẩn bị tốt hơn |
| `true` | `true` | Có | Dữ liệu có thể đã resident trước đó |
| `false` | `false` | Có | Best effort không bắt buộc hint chuyển thành true |
| `true` | `false` | Có | Trạng thái thay đổi hoặc hint không ổn định |

**Không dùng `isLoaded()` để suy ra số lượng page fault, lỗi đọc file, quyền truy cập hay việc nội dung file còn nguyên vẹn.** Nó chỉ là gợi ý về trạng thái cư trú trong bộ nhớ tại một thời điểm.

### 4.2. Nếu không kiểm chứng được thì vì sao có API này?

`isLoaded()` có thể giúp theo dõi trạng thái **mang tính tham khảo** của một mapping, ví dụ phục vụ thống kê/warm-up diagnostics. Nó không thay thế việc đo độ trễ, I/O, RSS hoặc bộ đếm fault từ hệ điều hành. Một chương trình có thể đọc dữ liệu thành công dù `isLoaded()` trả `false`.

## 5. Page fault ảnh hưởng độ trễ như thế nào?

### 5.1. Demand paging: trì hoãn chi phí tới lúc dùng

~~~text
map ----------------------> get(page A)
                               |
                               +-- Resident: thường nhanh
                               |
                               +-- Fault: OS phải xử lý,
                                          có thể chờ I/O
~~~

Nếu ứng dụng nhạy độ trễ, chi phí page fault có thể rơi vào đường xử lý một yêu cầu quan trọng. Tuy nhiên, đọc lần đầu không luôn chậm: file có thể đã nằm trong page cache.

### 5.2. Preload: chuyển một phần chi phí về warm-up

~~~text
map --> load() --> page fault/I/O có thể xảy ra --> xử lý chính --> get(page A)
             (warm-up)                                       (có thể nhanh hơn)
~~~

Nếu trang vẫn resident, truy cập sau có thể nhanh hơn. Nhưng chi phí I/O có thể chỉ được **dời sang trước**, không biến mất. OS có thể thu hồi trang giữa hai thời điểm, khiến `get` vẫn fault.

### 5.3. Preload sai workload có thể tệ hơn

Nếu một file rất lớn nhưng query chỉ truy cập một số ít trang, load cả vùng làm tăng I/O, page cache pressure và thời gian khởi đầu vô ích. Với truy cập ngẫu nhiên thưa, demand paging có thể hiệu quả hơn.

Do vậy, chọn `load()` dựa vào **tần suất/trật tự truy cập, kích thước tập dữ liệu, bộ nhớ khả dụng và độ nhạy độ trễ** thay vì chỉ dựa vào trực giác “prefetch luôn nhanh hơn”.

## 6. Chương trình Java 17+ hoàn chỉnh

Chương trình dưới đây tạo file tạm với dữ liệu có quy luật, ánh xạ 4.096 byte ở offset 512, kiểm tra `isLoaded()` hai lần và đọc byte theo chỉ số tuyệt đối.

**Tệp: `MappedLoadDemo.java`**

~~~java
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class MappedLoadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("mapped-load-", ".bin");
        try {
            byte[] data = new byte[8192];
            for (int i = 0; i < data.length; i++) {
                data[i] = (byte) (i % 251);
            }
            Files.write(file, data);

            try (FileChannel channel =
                         FileChannel.open(file, StandardOpenOption.READ)) {
                MappedByteBuffer mapped =
                        channel.map(FileChannel.MapMode.READ_ONLY, 512, 4096);
                mapped.position(10);

                boolean before = mapped.isLoaded();
                boolean same = mapped.load() == mapped;
                boolean after = mapped.isLoaded();

                System.out.println("capacity=" + mapped.capacity());
                System.out.println("position=" + mapped.position());
                System.out.println("load returns same=" + same);
                System.out.println("first=" + (mapped.get(0) & 0xFF));
                System.out.println("last=" + (mapped.get(4095) & 0xFF));
                System.out.println(
                        "hint before=" + before + ", after=" + after);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac MappedLoadDemo.java
java MappedLoadDemo
~~~

Một lần chạy thực tế trên JDK cho kết quả:

~~~text
capacity=4096
position=10
load returns same=true
first=10
last=89
hint before=false, after=false
~~~

**Dòng cuối chỉ là kết quả một lần chạy.** Nó có thể là `false,false`, `false,true`, `true,true` hoặc `true,false` tùy môi trường và thời điểm. Không viết unit test cố định kỳ vọng cho giá trị `isLoaded()`.

Giải thích từng phần:

1. Mapping bắt đầu từ byte số 512 trong file và có `capacity=4096`.
2. `position(10)` thiết lập vị trí đọc tương đối. `load()` không thay đổi position; hai lệnh `get(index)` absolute cũng không đổi position, nên chương trình in `position=10`.
3. `load()` trả về cùng đối tượng, vì vậy `same` là `true`.
4. `data[i] = (byte) (i % 251)`. Tại offset 512, giá trị là 10; tại offset 512 + 4095 = 4607, giá trị là 89. Phép `& 0xFF` giúp in byte như số không dấu 0–255.
5. `isLoaded()` trước và sau `load()` chỉ tạo các quan sát; chúng không cho phép kết luận chắc chắn trang còn resident ở lần `get` kế tiếp.

**Lưu ý về dọn tài nguyên:** `MappedByteBuffer` có vòng đời mapping tách biệt với `FileChannel`; đóng channel không tự unmap. Trên một số hệ điều hành, việc xóa file khi mapping vẫn còn có thể gặp hạn chế; lệnh `Files.deleteIfExists(file)` trong `finally` có thể ném `IOException` tùy môi trường. Đó là vấn đề vòng đời mapping, không phải bằng chứng `load()` sai.

## 7. load toàn buffer hay chỉ phần còn lại?

`MappedByteBuffer.load()` áp dụng cho **nội dung vùng mapped buffer** mà đối tượng đó đại diện, không nhận offset/length. Thay đổi `position` và `limit` của mapped buffer gốc không tự tạo một yêu cầu preload dành riêng cho khoảng `[position, limit)`.

~~~java
mapped.position(100);
mapped.limit(200);
mapped.load(); // không phải lệnh nạp duy nhất 100 byte trong [100, 200)
~~~

Đây là mã minh họa. Nếu muốn giới hạn vùng, Java 17 có `MappedByteBuffer.slice()` và `slice(index, length)` trả về mapped view của một **subrange**; `load()` trên view tác động tới vùng con ấy theo Javadoc.

~~~java
// mapped có capacity tối thiểu 8192 byte:
MappedByteBuffer part = mapped.slice(4096, 4096);
part.load(); // best effort đối với nội dung của part
~~~

Các vùng chia sẻ nội dung, không copy dữ liệu vào heap. Chỉ số và độ dài slice phải nằm trong giới hạn buffer. Hoặc trực tiếp map một cửa sổ bằng `FileChannel.map(mode, offset, length)` khi phù hợp.

`MappedByteBuffer` có capacity là `int`, vì vậy dạng `FileChannel.map(MapMode, long, long)` không dùng một buffer để biểu diễn một vùng vượt `Integer.MAX_VALUE` byte; tệp rất lớn thường cần chia thành nhiều cửa sổ.

## 8. Phân biệt load, force và thao tác đọc

| API/cơ chế | Vai trò | Có bảo đảm tránh fault về sau? |
|---|---|---|
| `FileChannel.map` | Tạo ánh xạ file vào địa chỉ ảo | Không |
| `MappedByteBuffer.load` | Best effort page-in | Không |
| `MappedByteBuffer.isLoaded` | Hint về residency | Không |
| `MappedByteBuffer.get` | Đọc byte thực sự | Không |
| `MappedByteBuffer.force` | Yêu cầu ghi thay đổi mapping về lưu trữ | Không |
| `FileChannel.force` | Yêu cầu đẩy cập nhật qua channel về thiết bị | Không |
| OS page cache | Cache nội dung file trong RAM | Không |

### 8.1. load khác force

`load()` phục vụ chiều **chuẩn bị dữ liệu trong RAM** cho truy cập. `MappedByteBuffer.force()` phục vụ chiều **ghi các thay đổi ra thiết bị** với những cam kết phụ thuộc chế độ mapping và loại storage.

~~~java
// Với mapped được tạo bằng FileChannel.MapMode.READ_WRITE:
mapped.put(0, (byte) 42);
mapped.force();
~~~

Đoạn minh họa trên không độc lập. `force()` có ý nghĩa cho `READ_WRITE`; với `READ_ONLY` hoặc `PRIVATE`, nó không có cùng tác dụng ghi dữ liệu chung ra file. `force()` cũng không phải cơ chế transaction nguyên tử của ứng dụng.

### 8.2. load khác Files.readAllBytes

`Files.readAllBytes` tạo mảng dữ liệu trong Java heap và đọc byte vào đó. `load()` không đưa file vào một mảng `byte[]`; nó yêu cầu OS cố gắng đưa các trang của mapping vào bộ nhớ vật lý. Vì thế không đánh giá hai phương thức chỉ bằng số lần cấp phát đối tượng Java.

## 9. Benchmark: đo cái gì?

Cùng một mã có thể cho kết quả khác biệt do:

- File cold/warm trong page cache.
- Readahead của filesystem, kích thước trang và mô hình truy cập tuần tự/ngẫu nhiên.
- Trạng thái JVM/JIT, áp lực RAM, số tiến trình cùng dùng dữ liệu.
- SSD/HDD, network file system, container hoặc VM.
- Sự khác nhau giữa minor fault và major fault, và chi phí I/O thực tế.

Quy trình đo nên:

1. Chuẩn bị tập dữ liệu và ít nhất hai chính sách: demand paging (không load) và gọi load trước xử lý.
2. Ghi nhận **tổng thời gian map + load + read + xử lý**, bên cạnh latency riêng của phần đọc.
3. Thử workload sequential, random, cold và warm với nhiều lần lặp; báo cáo p50/p95/p99.
4. Quan sát page fault counters và disk I/O từ OS nếu công cụ hỗ trợ; đừng dùng riêng `isLoaded()` làm thước đo.
5. Kiểm tra memory pressure và overhead của việc preload dữ liệu ít dùng.

Trên Linux có `perf`, ví dụ minh họa:

~~~bash
perf stat -e minor-faults,major-faults java MappedLoadDemo
~~~

Lệnh này tùy quyền và việc cài công cụ; bộ đếm cấp tiến trình **không bằng** số fault của một mapped buffer cụ thể. Windows/macOS cần công cụ tương ứng.

### Có nên dùng load?

| Mô hình | Hướng thử nghiệm |
|---|---|
| Quét toàn bộ vùng lớn trước tác vụ nhạy độ trễ | Thử load một lần trong warm-up |
| Truy cập vài vị trí rải rác trong file lớn | Thử demand paging/cửa sổ map nhỏ |
| Đọc lặp lại nhiều lần | Đo lợi ích load khi page cache đã warm |
| Máy chịu áp lực RAM | Đo chi phí eviction, thrashing và I/O |
| File có thể bị sửa/truncate đồng thời | Giải quyết an toàn vòng đời trước khi tối ưu |

## 10. Vòng đời và các rủi ro khi file thay đổi

Mapping sau khi tạo thành công **không phụ thuộc trực tiếp vòng đời FileChannel đã map nó**. Đóng channel không có nghĩa là unmap ngay; Java 17 không cung cấp `MappedByteBuffer.close()` hoặc `unload()` công khai để ép giải phóng. Mapping tiếp tục tồn tại đến khi buffer được thu hồi theo quản lý bộ nhớ.

Java 17 cảnh báo vùng mapped file **có thể không còn truy cập được** nếu tệp bị truncate hoặc sửa không phù hợp. Khi truy cập vùng không hợp lệ, ngoại lệ xảy ra có thể không được chỉ định trước và không nhất thiết xuất hiện ngay tại lời gọi truy cập. `load()` và `isLoaded()` không bảo vệ ứng dụng khỏi thay đổi kích thước tệp, race condition hoặc lỗi file system.

Đừng dựa vào `System.gc()` để unmap đúng một thời điểm; với ứng dụng production, phải quản lý vòng đời file/mapping, người đọc/người ghi và yêu cầu truy cập an toàn.

## 11. Các hiểu lầm thường gặp

1. **“map() đọc hết file vào RAM.”** Sai: OS có thể dùng demand paging.
2. **“load() đảm bảo không fault nữa.”** Sai: chỉ best effort, trang có thể bị evict.
3. **“isLoaded() == false nghĩa là file chưa ở RAM.”** Sai: đó chỉ là hint.
4. **“isLoaded() == true luôn chứng minh lần get tiếp theo nhanh.”** Sai: trạng thái có thể thay đổi.
5. **“Mỗi page fault đều tốn physical disk read.”** Sai: minor fault có thể được xử lý trong RAM.
6. **“load() thay cho force().”** Sai: chúng phục vụ page-in và flush, hai hướng khác nhau.
7. **“Gọi load() càng nhiều thì càng nhanh.”** Sai: prefetch dư có thể gây I/O và áp lực RAM.
8. **“position/limit tự giới hạn vùng load().”** Sai: dùng mapped slice/cửa sổ map khi cần.
9. **“Đóng FileChannel làm mapping biến mất.”** Sai: vòng đời mapping riêng.
10. **“isLoaded() có thể kiểm chứng file không bị truncate.”** Sai: residency không phải an toàn truy cập.

## 12. Tự kiểm tra

**Câu 1:** Gọi `load()` rồi `isLoaded()` vẫn ra `false` có phải lỗi?

**Đáp án:** Không. `load()` chỉ best effort và `isLoaded()` là hint.

**Câu 2:** Page fault có nhất thiết làm phát sinh I/O từ ổ đĩa?

**Đáp án:** Không. Minor fault có thể được giải quyết với dữ liệu đã có trong RAM/page cache. Major fault có thể phải đợi I/O.

**Câu 3:** Cần yêu cầu ghi thay đổi của READ_WRITE mapping về storage, dùng `load()` hay `force()`?

**Đáp án:** `force()` theo hợp đồng ghi, không phải `load()`.

**Câu 4:** Vì sao load toàn bộ file nhưng chỉ truy cập vài trang có thể chậm hơn không load?

**Đáp án:** Preload có thể đọc dư, tốn I/O và đẩy các trang hữu ích khỏi RAM/page cache.

### Tài liệu chính thức

- [Java 17: MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html)
- [Java 17: FileChannel.map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#map(java.nio.channels.FileChannel.MapMode,long,long))
- [Java 17: ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)

# Heap buffer, direct buffer và chi phí cấp phát trong Java NIO

Trong Java NIO, `ByteBuffer` là vùng nhớ có cấu trúc để đọc, ghi và chuyển byte giữa ứng dụng với file, socket hoặc những kênh dữ liệu khác. Hai cách tạo phổ biến là `ByteBuffer.allocate(capacity)` và `ByteBuffer.allocateDirect(capacity)`. Cả hai đều trả về `ByteBuffer` có các thao tác `put`, `get`, `flip`, `clear` như nhau, nhưng **vị trí vùng nhớ lưu dữ liệu, chi phí cấp phát, cách thu hồi và hiệu năng I/O có thể khác nhau**.

Lựa chọn đúng phụ thuộc vào vòng đời buffer, kích thước, tần suất cấp phát, kiểu xử lý dữ liệu và đường đi I/O cụ thể. Direct buffer không tự động nhanh hơn heap buffer, và việc cấp phát ngoài Java heap không có nghĩa bộ nhớ được giải phóng ngay khi gọi `clear()`.

## 1. Những phần của `ByteBuffer` giống nhau

Một `ByteBuffer` quản lý bốn giá trị:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Sức chứa cố định theo byte, được chọn khi tạo buffer; không đổi khi `flip` hoặc `clear` |
| `limit()` | Mốc đầu tiên không được truy cập theo chế độ hiện tại |
| `position()` | Chỉ số của phần tử tiếp theo được đọc/ghi bằng phương thức tương đối |
| `mark()` / `reset()` | Ghi nhớ và quay lại một vị trí trong cùng buffer; mark có thể chưa được đặt |

Các bất biến là `0 <= position <= limit <= capacity`; mark, nếu được xác định, không vượt position. Một buffer mới từ `allocate(8)` hoặc `allocateDirect(8)` đều có `position=0`, `limit=8`, `capacity=8`. Nội dung ban đầu được khởi tạo bằng 0 theo hợp đồng API.

Chu trình ghi rồi đọc:

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put((byte) 10);       // position: 0 -> 1
buffer.put((byte) 20);       // position: 1 -> 2
buffer.flip();               // position=0, limit=2
int first = Byte.toUnsignedInt(buffer.get()); // 10, position=1
```

Đây là đoạn minh họa; `ByteBuffer` cần import từ `java.nio`. Nếu thay `allocate(8)` bằng `allocateDirect(8)`, các giá trị vị trí và kết quả đọc vẫn như vậy.

- `flip()` biến các byte vừa ghi thành vùng có thể đọc, đặt `limit` bằng position cũ và position về 0.
- `clear()` đặt position về 0, limit về capacity để chuẩn bị ghi tiếp; **không xóa byte**, không đổi loại buffer và không giải phóng bộ nhớ.
- `compact()` giữ các byte chưa đọc bằng cách chuyển chúng về đầu buffer, rồi đặt position sau phần dữ liệu còn lại; hữu ích khi xử lý một khung dữ liệu đến chưa đầy đủ.
- `get(index)` và `put(index, value)` truy cập tuyệt đối theo chỉ số của buffer, không tự di chuyển position.
- Buffer không tự thay đổi capacity: muốn có sức chứa lớn hơn phải cấp phát buffer khác và chuyển dữ liệu còn cần giữ.

**Capacity tính bằng byte**, không phải số ký tự. Một ký tự Unicode có thể được mã hóa thành nhiều byte UTF-8; chuyển đổi byte sang văn bản phải có charset và xử lý đúng phần dữ liệu hợp lệ từ position/limit.

## 2. Heap buffer được cấp phát thế nào?

`ByteBuffer.allocate(n)` tạo **non-direct byte buffer**, thường dựa trên một mảng `byte[]` thuộc Java heap. `ByteBuffer.wrap(byte[])` bọc mảng đã tồn tại thành một heap buffer mà **không chép mảng dữ liệu**. Đây là lựa chọn tự nhiên khi dữ liệu được tạo, sửa, kiểm tra hoặc thao tác bằng Java thông thường.

```java
ByteBuffer heap = ByteBuffer.allocate(1024);
ByteBuffer wrapped = ByteBuffer.wrap(new byte[1024]);

System.out.println(heap.isDirect()); // false
System.out.println(heap.hasArray());  // true
System.out.println(wrapped.isDirect()); // false
```

Đoạn này minh họa đặc tính buffer cấp phát/bọc theo cách trên. Với heap buffer thông thường có mảng truy cập được, `hasArray()` trả `true`, `array()` cung cấp mảng bên dưới và `arrayOffset()` giúp xác định vị trí tương ứng trong mảng đó.

Đừng mặc định mọi heap buffer đều cho gọi `array()`: **heap buffer chỉ đọc** (`asReadOnlyBuffer()`) có thể không cho truy cập mảng, `hasArray()` trả `false` và `array()` có thể ném `ReadOnlyBufferException`. Hãy kiểm tra `hasArray()` trước khi phụ thuộc vào API mảng.

### Chi phí chính của heap buffer

- **Cấp phát:** Mảng backing `byte[]` và đối tượng buffer được quản lý bởi JVM. Với các buffer nhỏ, cơ chế cấp phát heap tối ưu có thể làm thao tác này khá rẻ; đừng giả định luôn chỉ có một phép cấp phát hay không tốn chi phí.
- **Bộ nhớ và GC:** Dữ liệu nằm trong phần heap được quản lý, có thể làm tăng áp lực GC khi tạo nhiều mảng hoặc giữ nhiều mảng lớn.
- **Truy cập bằng Java:** Thuận tiện với `array()`, hệ sinh thái API dùng mảng, thao tác từng byte và xử lý trong JVM.
- **I/O với hệ điều hành:** Một số implementation/channel có thể cần copy qua bộ nhớ trung gian thích hợp cho native I/O. **Số bản sao và chi phí cụ thể không phải lời hứa chung của mọi API Java NIO.**

Nếu đã có dữ liệu trong `byte[]`, `ByteBuffer.wrap(existing)` có thể tránh tạo thêm một mảng dữ liệu mới. Tuy nhiên mảng và buffer chia sẻ nội dung, nên chỉnh mảng sẽ làm thay đổi byte nhìn qua buffer và ngược lại.

## 3. Direct buffer khác ở đâu?

`ByteBuffer.allocateDirect(n)` tạo **direct byte buffer**. Theo API Java, JVM cố gắng đặt nội dung của direct buffer vào bộ nhớ có thể phục vụ thao tác native I/O trực tiếp, tránh một số bước copy trung gian trên những đường I/O phù hợp. Trên các JVM phổ biến, bộ nhớ chứa byte của direct buffer thường là vùng **ngoài Java heap (off-heap/native memory)**; bản thân đối tượng `ByteBuffer` và metadata vẫn là đối tượng Java.

```java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);

System.out.println(direct.isDirect()); // true
System.out.println(direct.hasArray());  // false
```

**Direct không đồng nghĩa với “không có đối tượng Java” hoặc “không chịu ảnh hưởng GC”.** Java vẫn phải theo dõi khả năng tiếp cận đối tượng buffer để có thể thu hồi tài nguyên phía native khi không còn được sử dụng. Direct buffer cũng không tự biến một thao tác `get()` lặp từng byte thành thao tác vector hóa nhanh hơn.

Các đặc điểm quan trọng:

1. **Chi phí tạo cao hơn trong nhiều tình huống:** JVM có thể phải đặt trước/commit bộ nhớ native, khởi tạo nội dung, tạo và theo dõi metadata dọn dẹp. Đặc biệt khi cấp phát rất nhiều direct buffer nhỏ trong vòng lặp, chi phí phân bổ và thu hồi có thể lấn át lợi ích I/O.
2. **Có thể giảm copy tại ranh giới native I/O:** Một số channel và provider tận dụng địa chỉ vùng nhớ direct; lợi ích rõ hơn với khối dữ liệu tương đối lớn và buffer được dùng lặp lại. Điều này **phụ thuộc implementation, nền tảng, loại channel và cách gọi**.
3. **Vẫn cần kiểm soát lifetime:** `clear()` và `flip()` không trả native memory về hệ điều hành. Buffer tồn tại lâu nếu còn được giữ qua field, queue, cache hoặc các view.
4. **Không cung cấp Java array backing:** `hasArray()` thường là `false`, nên các API yêu cầu `byte[]` có thể cần một lần copy riêng.
5. **Có thể chịu giới hạn direct memory của JVM:** Việc cấp phát thất bại có thể dẫn tới `OutOfMemoryError` liên quan direct-buffer memory **dù Java heap vẫn còn chỗ**.

Với HotSpot, tùy chọn JVM như `-XX:MaxDirectMemorySize=256m` đặt giới hạn cho một phần quản lý direct memory. Đây là tùy chọn triển khai JVM, không phải quy tắc quản lý bộ nhớ giống hệt trên mọi JVM. Dữ liệu native khác của tiến trình (stack, mã máy, thư viện, mmap, v.v.) còn nằm ngoài phạm vi riêng của tùy chọn này.

## 4. Bảng so sánh heap và direct buffer

| Khía cạnh | Heap buffer | Direct buffer |
| --- | --- | --- |
| Tạo buffer | `ByteBuffer.allocate(n)`, `wrap(array)` | `ByteBuffer.allocateDirect(n)` |
| `isDirect()` | `false` | `true` |
| Vùng chứa byte | Thường là mảng thuộc Java heap | Thường là vùng native/off-heap trên JVM phổ biến |
| `hasArray()` | Thường `true` nếu không phải read-only | `false` |
| Cấp phát thường xuyên số lượng nhỏ | Thường có lợi về chi phí tạo | Dễ tốn chi phí tạo/thu hồi hơn |
| Truy cập nội dung trong Java | Thuận tiện với mảng và API Java | Vẫn dùng `get/put`, nhưng không mở backing array |
| I/O native | Có thể phát sinh copy trung gian | Có thể giảm copy ở một số đường I/O |
| Thu hồi | Theo GC heap | Phụ thuộc lifetime/reachability và cơ chế thu hồi native memory của JVM |
| Khi giữ nhiều vùng lớn | Tăng áp lực Java heap và GC | Tăng native memory/RSS; vẫn có áp lực quản lý đối tượng và giới hạn riêng |
| Hiệu năng tổng thể | Phụ thuộc workload | Phụ thuộc workload; không có bảo đảm luôn nhanh hơn |

Hai loại đều có `position`, `limit`, `capacity`, byte order, khả năng tạo view và đọc/ghi bằng NIO channel. `ByteBuffer` mới dùng thứ tự byte mặc định `BIG_ENDIAN` khi đọc/ghi kiểu nhiều byte. Byte order chỉ ảnh hưởng diễn giải các số nhiều byte, **không quyết định buffer heap hay direct**.

## 5. Chương trình Java 17+ chạy được: so sánh tính chất và vùng nhớ chia sẻ

Chương trình sau không giả lập benchmark. Nó kiểm tra những hành vi **được hợp đồng API bảo đảm**, đồng thời minh họa mảng của heap buffer và view của direct buffer có thể cùng trỏ tới dữ liệu gốc.

Tạo tệp **`HeapAndDirectDemo.java`**:

```java
import java.nio.ByteBuffer;

public final class HeapAndDirectDemo {
    private HeapAndDirectDemo() {}

    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(8);
        ByteBuffer direct = ByteBuffer.allocateDirect(8);
        ByteBuffer wrapped = ByteBuffer.wrap(new byte[8]);

        describe("heap", heap);
        describe("direct", direct);
        describe("wrapped", wrapped);

        heap.put(new byte[] {10, 20, 30, 40});
        direct.put(new byte[] {10, 20, 30, 40});

        System.out.println("heap after put: pos=" + heap.position()
                + ", remaining=" + heap.remaining());

        heap.flip();
        direct.flip();
        System.out.println("heap first=" + Byte.toUnsignedInt(heap.get()));
        System.out.println("heap position=" + heap.position());

        System.out.println("direct index 1=" +
                Byte.toUnsignedInt(direct.get(1)));
        System.out.println("direct position=" + direct.position());

        heap.array()[0] = 99;
        System.out.println("heap after array edit=" +
                Byte.toUnsignedInt(heap.get(0)));

        ByteBuffer directView = direct.slice();
        directView.put(0, (byte) 77);
        System.out.println("direct view isDirect=" + directView.isDirect());
        System.out.println("direct after view edit=" +
                Byte.toUnsignedInt(direct.get(0)));

        ByteBuffer readOnly = direct.asReadOnlyBuffer();
        System.out.println("readOnly direct=" + readOnly.isDirect()
                + ", hasArray=" + readOnly.hasArray());
        System.out.println("readOnly first=" +
                Byte.toUnsignedInt(readOnly.get(0)));

        direct.clear();
        System.out.println("direct after clear: pos=" + direct.position()
                + ", limit=" + direct.limit());
    }

    private static void describe(String label, ByteBuffer buffer) {
        System.out.println(label + ": isDirect=" + buffer.isDirect()
                + ", hasArray=" + buffer.hasArray()
                + ", capacity=" + buffer.capacity());
    }
}
```

Biên dịch và chạy:

```bash
javac HeapAndDirectDemo.java
java HeapAndDirectDemo
```

Kết quả:

```text
heap: isDirect=false, hasArray=true, capacity=8
direct: isDirect=true, hasArray=false, capacity=8
wrapped: isDirect=false, hasArray=true, capacity=8
heap after put: pos=4, remaining=4
heap first=10
heap position=1
direct index 1=20
direct position=0
heap after array edit=99
direct view isDirect=true
direct after view edit=77
readOnly direct=true, hasArray=false
readOnly first=77
direct after clear: pos=0, limit=8
```

**Phân tích:**

- Ba buffer có cùng capacity 8 nhưng `isDirect` và `hasArray` khác nhau. `wrap` cho heap buffer và chia sẻ mảng được bọc.
- Sau `put` 4 byte, position tăng từ 0 lên 4, remaining bằng 4. `flip()` giới hạn phần đọc ở 4 byte; `heap.get()` làm position tăng lên 1.
- `direct.get(1)` dùng index tường minh nên `direct.position()` vẫn bằng 0.
- `heap.array()[0] = 99` sửa trực tiếp mảng backing, lập tức phản ánh qua `heap.get(0)`.
- `direct.slice()` tạo một view **dùng chung nội dung** với direct buffer gốc; sửa `directView.put(0, ...)` làm giá trị nhìn qua `direct` cũng đổi. `slice` có position/limit riêng và vẫn là direct.
- `asReadOnlyBuffer()` cho một view không được ghi, vẫn chia sẻ nội dung với đối tượng gốc và vẫn là direct. Nó không tạo snapshot bất biến.
- `direct.clear()` đặt lại trạng thái để ghi nhưng **không chứng minh vùng native được giải phóng hoặc byte đã được xóa**.

Kết quả trên thể hiện thuộc tính API; **không dùng thời gian chạy của chương trình này để kết luận heap/direct bên nào nhanh hơn**.

## 6. Phân biệt chi phí cấp phát, chi phí truy cập và chi phí I/O

Nhiều so sánh heap/direct gây nhầm lẫn vì gộp mọi chi phí vào một con số.

### 6.1. Chi phí cấp phát (`allocation cost`)

Đây là thời gian và tài nguyên cần để có một buffer đủ dung lượng:

```java
ByteBuffer h = ByteBuffer.allocate(64 * 1024);
ByteBuffer d = ByteBuffer.allocateDirect(64 * 1024);
```

Đây là đoạn minh họa hai buffer 64 KiB, không phải phép đo. Cả hai phương thức đều phải cấp vùng chứa byte được khởi tạo, nhưng đường cấp phát khác nhau. Với một buffer dùng đúng một lần và chỉ xử lý dữ liệu trong Java, lợi ích giảm copy I/O của direct có thể không đủ để bù thời gian cấp phát ban đầu.

Trong trường hợp cấp phát nhiều lần (ví dụ tạo buffer mới cho từng packet 1 KiB), chi phí gồm tạo đối tượng, khởi tạo vùng nhớ, cấp phát/thu hồi native memory và áp lực garbage collection. Đừng xây đường xử lý hiệu năng cao bằng cách gọi `allocateDirect` cho mọi sự kiện mà chưa đo.

### 6.2. Chi phí đọc/ghi byte trong Java (`access cost`)

Các thao tác `buffer.get()`, `buffer.put()`, `getInt()`, `putLong()` vẫn cần kiểm tra chỉ số, truy cập vùng nhớ và có thể chịu ảnh hưởng CPU cache, JIT, kích thước khối, thứ tự byte, căn chỉnh dữ liệu và kiểu vòng lặp.

Heap buffer không luôn thắng các phép đọc/ghi trong Java; direct buffer cũng không luôn thắng. Việc lấy backing array để làm việc với thư viện chỉ hỗ trợ `byte[]` có thể làm heap buffer thuận tiện hơn, trong khi direct buffer cần bước chép dữ liệu.

### 6.3. Chi phí chuyển dữ liệu tới/từ kênh I/O (`transfer cost`)

`FileChannel.read(ByteBuffer)`, `FileChannel.write(ByteBuffer)` và các API NIO khác làm việc với cả hai loại buffer. Trên một số nền tảng và provider, JVM có thể tận dụng direct buffer để giao dữ liệu cho native I/O mà tránh một bản copy từ heap tới buffer tạm.

Tuy nhiên, **direct buffer không đồng nghĩa với zero-copy I/O**. Vẫn có thể tồn tại những lần sao chép giữa kernel và user space, trong trình điều khiển, ở lớp mạng/TLS, hoặc trong triển khai channel cụ thể. `FileChannel.transferTo/transferFrom` là họ API khác, và `MappedByteBuffer` dùng memory mapping; không nên đánh đồng các cơ chế này với `allocateDirect`.

Lợi ích tiềm năng thường tăng khi lượng byte chuyển lớn, buffer được tái sử dụng và chi phí copy nằm trên đường nóng. Một lần đọc tệp nhỏ hay đoạn xử lý nhiều thao tác tính toán trên mảng có thể không nhận được lợi ích đó.

## 7. Tái sử dụng buffer để giảm chi phí lặp lại

Thay vì tạo direct buffer cho mỗi lần đọc/ghi, một thành phần sở hữu I/O có thể tạo buffer **một lần** và dùng lặp:

```java
// Đoạn minh họa trong phương thức xử lý IOException.
// channel là ReadableByteChannel có dữ liệu, được sở hữu/đóng ở ngoài.
ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
while (true) {
    buffer.clear();
    int n = channel.read(buffer);
    if (n == -1) {
        break;
    }
    if (n == 0) {
        // Tùy channel/blocking mode, xử lý trường hợp chưa có dữ liệu.
        continue;
    }
    buffer.flip();
    while (buffer.hasRemaining()) {
        processByte(buffer.get()); // Hàm nghiệp vụ minh họa.
    }
}
```

Đoạn trên chỉ diễn tả chu trình reuse; `processByte` là hàm nghiệp vụ giả định, không phải chương trình biên dịch độc lập. Trong xử lý thực tế, không nên spin vô hạn khi `read()` liên tục trả 0 trên non-blocking channel; cần dùng selector/cơ chế chờ hoặc scheduling phù hợp.

Một **buffer pool** có thể quản lý nhiều vùng direct memory tái sử dụng cho các kết nối hoặc request. Nhưng pool cũng có chi phí: lock/đồng bộ, tranh chấp, phân mảnh theo kích cỡ, lượng bộ nhớ giữ nhàn rỗi, và nguy cơ cấp nhầm một buffer đang được thread khác sử dụng.

Thiết kế pool cần làm rõ:

- Ai sở hữu buffer, khi nào được mượn và hoàn trả, và có được dùng đồng thời hay không.
- Giới hạn **số lượng × dung lượng**, tránh tăng bộ nhớ native vô hạn khi tải đột biến.
- Cách đặt `position/limit` đúng khi tái sử dụng; `clear()` không làm sạch dữ liệu cũ. Nếu dữ liệu nhạy cảm, cần chính sách xóa/ghi đè thực sự trước khi chuyển quyền sở hữu.
- Xử lý trường hợp dữ liệu chưa được tiêu thụ hết bằng `compact()` hoặc thiết kế phân đoạn phù hợp; không `clear()` làm mất phần chưa đọc.
- View từ `slice()`, `duplicate()` hoặc `asReadOnlyBuffer()` vẫn có thể tham chiếu cùng nội dung, vì vậy không hoàn trả gốc để người khác ghi đè khi view còn đang được dùng.

Đối với buffer nhỏ và ngắn hạn, cấp phát heap đơn giản có thể hợp lý hơn nhiều so với xây pool direct buffer phức tạp.

## 8. Thu hồi bộ nhớ và các loại lỗi thiếu bộ nhớ

Tài nguyên của direct buffer thường gắn với khả năng tiếp cận đối tượng Java đại diện; JVM quản lý cách dọn dẹp native memory khi buffer không còn được sử dụng. **Không có thời điểm giải phóng tức thì được đảm bảo chỉ vì một biến cục bộ ra khỏi scope**. Các view và tham chiếu giữ trong queue/cache có thể kéo dài lifetime của vùng byte.

Đừng dùng những cách sau như phương thức giải phóng:

- `buffer.clear()`: chỉ đặt lại position/limit.
- `buffer.flip()`: chỉ chuyển trạng thái ghi sang đọc.
- Gán `buffer = null` và kỳ vọng native memory được thu hồi ngay.
- Gọi thủ công các API nội bộ như `Cleaner` của JDK qua reflection để ép giải phóng: cách này phụ thuộc triển khai, có thể phá tính an toàn bộ nhớ nếu còn view hoặc công việc I/O đang dùng buffer.

Hai tình huống lỗi là khác nhau:

| Hiện tượng | Gợi ý nguyên nhân |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Áp lực vùng Java heap, có thể do nhiều heap buffer/mảng và các đối tượng khác |
| `OutOfMemoryError` liên quan `direct buffer memory` | Vượt giới hạn/quỹ bộ nhớ direct do JVM quản lý hoặc không thu hồi kịp các buffer cũ |

Câu chữ chính xác của `OutOfMemoryError` phụ thuộc JVM và phiên bản. Ngoài hai lỗi này, tiến trình còn có thể bị giới hạn bởi tổng bộ nhớ của hệ điều hành/container. Cấp phát direct có thể giảm áp lực lưu byte trên heap nhưng **không xóa bỏ giới hạn tổng RAM** và không bảo đảm không xảy ra pause do GC.

### Theo dõi qua JVM

Với JVM có hỗ trợ, `BufferPoolMXBean` cho biết các bộ đệm trong pool như `direct` và `mapped`. Ví dụ sau là **đoạn minh họa trong chương trình Java có import tương ứng**:

```java
for (java.lang.management.BufferPoolMXBean pool :
        java.lang.management.ManagementFactory.getPlatformMXBeans(
                java.lang.management.BufferPoolMXBean.class)) {
    if ("direct".equals(pool.getName())) {
        System.out.println("count=" + pool.getCount());
        System.out.println("capacity=" + pool.getTotalCapacity());
        System.out.println("memoryUsed=" + pool.getMemoryUsed());
    }
}
```

Các số này hữu ích theo dõi xu hướng nhưng **không đại diện chính xác cho toàn bộ native memory/RSS của tiến trình**; một số thống kê có thể không được hỗ trợ trên nền tảng cụ thể (ví dụ báo `-1`). Khi phân tích bộ nhớ, nên xem cùng Java heap, GC, lượng request đang chạy, giới hạn container và chỉ số hệ điều hành.

## 9. Đo hiệu năng đúng câu hỏi

Ví dụ ở phần 5 là kiểm chứng tính năng, **không phải benchmark**. Một phép đo có ích cần tách ít nhất ba câu hỏi:

1. **Cấp phát:** Mất bao nhiêu thời gian và bao nhiêu bộ nhớ khi tạo/thu hồi 1.000 buffer 4 KiB, 64 KiB hoặc 1 MiB? Phải đo cùng số lượng, dung lượng và điều kiện GC.
2. **Tái sử dụng và truy cập:** Với buffer đã cấp phát sẵn, thời gian đọc/ghi theo block, theo byte hoặc theo kiểu số liệu khác nhau thế nào? Tránh để trình biên dịch JIT loại bỏ công việc không quan sát được.
3. **I/O thực tế:** Khi đọc/ghi cùng lượng dữ liệu qua `FileChannel` hoặc socket, throughput, latency, CPU usage và số lần copy thay đổi ra sao? Xét giới hạn thiết bị, cache hệ điều hành và mức đồng thời.

Đối với microbenchmark, ưu tiên **JMH** để xử lý warm-up, fork JVM, đo và tránh nhiều bẫy tối ưu hóa. Với workload I/O, cần thêm end-to-end benchmark trên môi trường phù hợp. Không nên đo một vòng `System.nanoTime()` duy nhất rồi công bố kết luận tổng quát, vì thời gian khởi động JIT, tải hệ thống, GC và trạng thái cache có thể chi phối kết quả.

Khi chạy so sánh cần cố định hoặc báo rõ: phiên bản JDK/JVM, cấu hình heap/direct memory, CPU/hệ điều hành, loại channel, kích thước buffer, việc tái sử dụng, số luồng, blocking/non-blocking, lượng dữ liệu, lần chạy lặp và sai số. Mục tiêu cuối cùng là đo **thời gian hoàn thành công việc của ứng dụng**, không chỉ đo một phép cấp phát rời rạc.

## 10. Chọn heap hay direct theo tình huống

| Tình huống | Hướng chọn ban đầu | Lý do cần kiểm chứng |
| --- | --- | --- |
| Parse một thông điệp nhỏ vừa tạo trong Java | Heap / `wrap(byte[])` | Truy cập mảng tiện, tránh cấp phát native mới cho thao tác ngắn |
| Xử lý mảng byte trong thư viện cũ | Heap | API yêu cầu `byte[]`, direct có thể phải chép dữ liệu |
| Đọc/ghi I/O khối lớn và liên tục | Xem xét direct tái sử dụng | Có khả năng giảm copy ở đường I/O thích hợp |
| Server có nhiều socket, buffer dùng nhiều lần | Xem xét pool direct có giới hạn | Cân bằng chi phí cấp phát và thời gian giữ native memory |
| Buffer tồn tại lâu với lượng dữ liệu lớn | Cần cân đối heap/direct | Heap gây áp lực GC; direct tiêu thụ native memory và khó dự đoán thời điểm thu hồi |
| Ít dữ liệu, throughput không quan trọng | Heap trước | Đơn giản, dễ quản lý hơn; tối ưu hóa chỉ sau khi đo |
| Cần chia sẻ một vùng byte qua nhiều view | Cả hai đều hỗ trợ | Phải quản lý alias, thread-safety và vòng đời buffer |

Không nên coi dung lượng **64 KiB**, **1 MiB** hoặc một ngưỡng cố định nào là ranh giới chính xác mà trên đó direct luôn nhanh hơn. Các con số trong ví dụ chỉ là kích thước minh họa, không phải khuyến nghị phổ quát.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo `ByteBuffer.allocateDirect` trong mọi vòng lặp xử lý gói tin | Tăng chi phí cấp phát và áp lực native memory | Tái sử dụng buffer hoặc đo để cân nhắc heap buffer |
| Nghĩ direct buffer luôn là zero-copy | Kỳ vọng throughput sai trên những provider/I/O path khác nhau | Đo workload thật, phân biệt direct, transferTo và mapped buffer |
| Gọi `array()` trên direct buffer | `UnsupportedOperationException` | Kiểm tra `hasArray()`, dùng `get/put` hoặc copy có chủ đích |
| Nghĩ `clear()` sẽ xóa dữ liệu hoặc giải phóng vùng native | Rò rỉ dữ liệu qua buffer pool, ước lượng sai bộ nhớ | Phân biệt reset trạng thái, xóa byte thật và thu hồi bộ nhớ |
| Giữ `slice()` sau khi trả buffer gốc vào pool | View thấy byte bị chủ sở hữu tiếp theo ghi đè | Ràng buộc lifetime của các view với tài nguyên gốc |
| Benchmark chỉ một lần, không warm-up | Kết quả phản ánh JIT/GC/cache hơn là workload | Dùng JMH và benchmark tổng thể, báo môi trường |
| Nghĩ JVM heap còn trống thì direct allocation không thể lỗi | Có thể gặp `OutOfMemoryError` do direct memory hoặc giới hạn process | Đặt ngân sách native memory, theo dõi direct buffer pool và RSS |
| Coi direct buffer là thread-safe mặc định | Race khi nhiều luồng sửa cùng byte/position/limit | Dùng quyền sở hữu độc lập hoặc đồng bộ phù hợp |
| Nhầm `flip()` với `clear()` | Đọc byte chưa ghi hoặc làm mất trạng thái cần xử lý | Theo đúng chu trình write → flip → read → compact/clear |

**Ghi nhớ:** Heap buffer ưu tiên sự đơn giản, cấp phát thường rẻ và dễ phối hợp với mảng Java. Direct buffer có thể hữu ích cho I/O lớn và được tái sử dụng, nhưng phải trả chi phí quản lý/cấp phát native memory và không đảm bảo nhanh hơn trong mọi trường hợp. Hãy chọn dựa trên **đường dữ liệu thực, vòng đời buffer và số đo phù hợp**; đừng suy luận tốc độ chỉ từ `isDirect()`.
# Heap buffer, direct buffer và chi phí cấp phát, tái sử dụng trong Java NIO

## 1. Đặt vấn đề: mỗi lần đọc/ghi qua channel đều cần một buffer

Khi lập trình Java NIO, `ByteBuffer` là vùng chứa các byte mà `SocketChannel`, `FileChannel` hoặc `DatagramChannel` có thể đọc vào hoặc ghi ra. Một lựa chọn thường gặp:

```java
// Hai cách cấp phát cùng dung lượng 8 KiB; đoạn mã minh họa.
ByteBuffer heapBuffer = ByteBuffer.allocate(8 * 1024);
ByteBuffer directBuffer = ByteBuffer.allocateDirect(8 * 1024);
```

Cả hai đều dùng được trong nhiều API đọc/ghi qua channel và đều có `capacity`, `position`, `limit`, `mark`, nhưng **vùng nhớ dữ liệu** và **chi phí vòng đời** khác nhau. Việc chọn buffer không chỉ là chọn cách gọi hàm cấp phát; còn liên quan đến số lần cấp phát, lượng dữ liệu phải sao chép, quản lý bộ nhớ, tái sử dụng, an toàn giữa các luồng và đặc tính I/O.

Bài toán điển hình:

- Một server có hàng nghìn kết nối TCP, mỗi request cần buffer để đọc frame và ghi response.
- Nếu cấp phát buffer mới cho mỗi yêu cầu, số đối tượng và lượng bộ nhớ luân chuyển có thể rất lớn.
- Nếu giữ quá nhiều buffer trực tiếp (direct) trong pool, dù heap trông còn trống, tiến trình vẫn có thể chịu áp lực **native/direct memory**.
- Nếu lấy buffer từ pool mà quên `clear`/`flip`, trả buffer trước khi I/O hoàn tất hoặc giao cùng một buffer cho hai handler, dữ liệu có thể bị sai.

**Mục tiêu:** hiểu heap/direct khác nhau về cách lưu byte; phân biệt **chi phí cấp phát** với **chi phí sử dụng** và **chi phí tái sử dụng**; biết khi nào direct buffer có lợi cho I/O; thiết kế pool có giới hạn và kiểm chứng bằng Java 17.

## 2. Heap buffer và direct buffer là gì?

### 2.1. Heap buffer

`ByteBuffer.allocate(capacity)` tạo một **non-direct byte buffer**. Vùng chứa byte thường nằm trong mảng `byte[]` thuộc Java heap, do garbage collector quản lý. `ByteBuffer.wrap(byte[])` cũng tạo một buffer nhìn lên mảng đã có, **không sao chép mảng** ở thời điểm wrap.

Đặc trưng:

- `isDirect()` trả `false`.
- Heap buffer ghi bằng `allocate` thường có mảng backing truy cập được; `hasArray()` trả `true` và có thể lấy `array()`/`arrayOffset()`.
- Cấp phát heap trong JVM thường rẻ nhờ cơ chế cấp phát hiện đại, nhưng rất nhiều đối tượng/mảng sống ngắn vẫn tạo **allocation rate** và áp lực GC.
- Nếu đưa heap buffer vào một số API I/O native, triển khai runtime **có thể** dùng vùng nhớ trung gian hoặc sao chép dữ liệu để tương tác với hệ điều hành. Chi tiết phụ thuộc JDK, channel, hệ điều hành và đường I/O; không có công thức “heap luôn sao chép N lần”.

Ví dụ:

```java
// Mã minh họa, đặt trong phương thức.
byte[] raw = new byte[16];
ByteBuffer wrapped = ByteBuffer.wrap(raw);
wrapped.put(0, (byte) 65);
System.out.println(raw[0]); // 65: chia sẻ cùng byte[]
```

`wrap` phù hợp khi dữ liệu đang là `byte[]` hoặc API khác cần truy cập mảng. Tuy nhiên, đừng coi mọi buffer có `isDirect()==false` đều cho phép gọi `array()`: **read-only view** có thể trả `hasArray()==false` dù vùng nhớ gốc ở heap.

### 2.2. Direct buffer

`ByteBuffer.allocateDirect(capacity)` tạo một **direct byte buffer** có vùng dữ liệu thường nằm ngoài Java heap, do runtime quản lý bằng bộ nhớ native/off-heap hoặc cơ chế tương đương. Object `ByteBuffer` và các đối tượng liên quan vẫn được GC nhìn thấy; **direct không có nghĩa hoàn toàn nằm ngoài kiểm soát của JVM**.

Đặc trưng:

- `isDirect()` trả `true`.
- Direct buffer thông thường không có mảng Java backing lộ ra; `hasArray()` thường là `false`. Với buffer tạo từ `allocateDirect`, không dùng `array()` để lấy dữ liệu.
- Theo tài liệu JDK, direct buffer **có thể** cho phép JVM làm I/O native trực tiếp trên nội dung, tránh một số bước sao chép trung gian so với heap buffer.
- **Cấp phát và giải phóng direct buffer thường đắt hơn** cấp phát heap buffer cùng kích thước, vì có công việc dành cho quản lý vùng nhớ ngoài heap, kiểm soát quota và khởi tạo dữ liệu. Điều đó không đồng nghĩa mỗi lần `get`/`put` trên direct luôn nhanh hơn.
- Bộ nhớ ngoài heap vẫn chiếm RAM của tiến trình, vẫn cần thu hồi và có thể gây `OutOfMemoryError` hoặc áp lực bộ nhớ hệ điều hành. Việc GC thấy heap còn dư không chứng minh direct memory còn dư.

**Không được khẳng định “direct = zero-copy tuyệt đối”.** Đưa direct buffer vào `SocketChannel.write` vẫn có thể cần copy từ user space sang kernel/network stack, và có thể gặp partial write; direct chủ yếu là cơ hội giảm **một số bản sao trung gian do Java/native interoperability**, tùy API và nền tảng. “Zero-copy” theo nghĩa chuyển file trực tiếp thường nhắc đến `FileChannel.transferTo/transferFrom` và các điều kiện riêng, không đồng nhất với `allocateDirect`.

### 2.3. Bảng so sánh nhanh

| Thuộc tính | Heap ByteBuffer | Direct ByteBuffer |
|---|---|---|
| Tạo điển hình | `ByteBuffer.allocate(n)`; `wrap(byte[])` | `ByteBuffer.allocateDirect(n)` |
| `isDirect()` | `false` | `true` |
| Vùng lưu byte | Java heap/backing array điển hình | Thường là bộ nhớ native/off-heap |
| `hasArray()` | Thường `true` với buffer writable tạo bởi `allocate`/`wrap` | `false` đối với `allocateDirect` |
| Cấp phát ngắn hạn | Thường rẻ hơn | Thường có overhead lớn hơn |
| Quản lý vòng đời | Bộ nhớ heap được GC xử lý | Native memory vẫn được JVM quản lý/thu hồi; thời điểm thu hồi không nên phụ thuộc vào `System.gc()` |
| Dùng với native I/O | Có thể phát sinh bản sao trung gian | Có thể giảm sao chép trung gian trong một số đường I/O |
| Rủi ro khi pool quá lớn | Chiếm heap và ảnh hưởng GC/retained heap | Chiếm native/direct budget, RSS và giới hạn của JVM/OS |
| Tốc độ `put/get` tuyệt đối | Phụ thuộc workload và truy cập | Phụ thuộc workload; **không mặc định nhanh hơn** |
| Phù hợp | Xử lý mảng, payload nhỏ/sống ngắn, API dùng `byte[]` | I/O lặp lại nhiều, buffer lớn hoặc đường channel hưởng lợi, có vòng đời được kiểm soát |

**Nhớ:** heap và direct có **cùng hợp đồng API ByteBuffer** ở mức position/limit; sự khác biệt chính nằm ở **vị trí lưu dữ liệu và tương tác bộ nhớ/I/O**.

## 3. Mô hình trạng thái của ByteBuffer: biết dùng trước khi tối ưu

Một buffer có ba đại lượng:

- `capacity`: dung lượng tổng, cố định đối với đối tượng buffer.
- `position`: vị trí tương đối của thao tác tiếp theo.
- `limit`: ranh giới không vượt qua khi đọc/ghi tương đối.

Trong trạng thái hợp lệ: `0 <= position <= limit <= capacity`. `mark` là mốc tùy chọn hỗ trợ `reset()`; một số thao tác thay đổi position/limit làm mất mark.

Chu trình ghi vào rồi đọc ra:

```text
Mới cấp phát: position=0, limit=capacity
        |
        v
put(bytes) / channel.read(buffer)
        | position tăng theo số byte ghi vào buffer
        v
flip()
        | limit=position cũ; position=0
        v
get() / channel.write(buffer)
        | position tăng theo số byte được đọc ra
        v
clear() cho một message mới
hoặc compact() để giữ phần chưa xử lý
```

Các API quan trọng:

| Phương thức | Thay đổi | Khi dùng |
|---|---|---|
| `flip()` | `limit=position`, `position=0`, bỏ mark | Chuyển từ **đang ghi vào buffer** sang **đọc byte hiện có** |
| `clear()` | `position=0`, `limit=capacity`, bỏ mark | Muốn dùng toàn bộ vùng nhớ để ghi dữ liệu mới |
| `compact()` | Dồn byte còn lại từ `position..limit` về đầu; position sau các byte còn lại | Sau khi xử lý một phần dữ liệu, muốn nhận/ghép thêm dữ liệu mà không bỏ phần dư |
| `rewind()` | `position=0`; giữ nguyên `limit` | Đọc lại nội dung trong giới hạn hiện hành |
| `remaining()` | `limit-position` | Số byte có thể đọc/ghi tương đối còn lại |
| `slice()` | View có position/limit riêng lên một phần dữ liệu gốc | Chia frame mà không copy byte; phải quản lý vòng đời backing |
| `duplicate()` | View chia sẻ byte, position/limit độc lập | Tạo góc nhìn khác lên cùng dữ liệu, **không** copy |

**Lỗi phổ biến:** gọi `clear()` sau khi nhận được nửa message rồi quên dữ liệu còn lại; gọi `flip()` hai lần liên tiếp; không xử lý `SocketChannel.write` trả về ít byte hơn `remaining()`; hoặc trả buffer về pool khi bên khác còn dùng view `slice`.

**`clear()` không xóa/zero dữ liệu cũ.** Nó chỉ đặt lại **các chỉ số**. Với pool dùng chung giữa nhiều client/tenant, nếu dữ liệu nhạy cảm có thể bị đọc lại, cần chính sách ghi đè/zeroization thích hợp trước khi tái sử dụng hoặc tiết lộ vùng nhớ. Không dùng `clear` như chức năng bảo mật.

## 4. Chi phí cấp phát: không chỉ là vài nanosecond

Hãy tách các thành phần chi phí để không đoán theo tên loại buffer.

### 4.1. Heap allocation cost

Khi gọi `ByteBuffer.allocate(n)`, JVM thường cấp phát object wrapper và backing byte array trên Java heap. Bộ nhớ mới được khởi tạo theo bảo đảm của Java. Với các đối tượng sống ngắn, cấp phát có thể rất nhanh, nhưng nếu server tạo hàng trăm nghìn buffer mỗi giây, hệ quả gồm:

- Allocation rate cao, tăng tần suất GC; mức ảnh hưởng phải đo thay vì đoán.
- Mảng lớn có thể làm tăng heap occupancy/pressure, tùy GC và kích thước.
- Tham chiếu đến buffer hoặc view còn sống giữ backing array lại, dù logic “đã dùng xong”.

Điều này **không tự chứng minh pooling heap luôn có lợi**: pool đưa object sống lâu hơn và có thể tăng retained heap, contention, lỗi vòng đời; GC hiện đại xử lý nhiều object ngắn hạn tốt.

### 4.2. Direct allocation cost

`ByteBuffer.allocateDirect(n)` thường phải quản lý vùng nhớ ngoài heap, tính quota, khởi tạo byte và gắn metadata để JVM theo dõi việc thu hồi. Chi phí cấp phát/thời gian thu hồi của một direct buffer có thể đáng kể hơn heap buffer tương đương, nhất là với buffer nhỏ cấp phát liên tục.

Rủi ro:

- **Native memory pressure:** bộ nhớ direct nằm ngoài dung lượng heap thông thường, nhưng vẫn tăng mức sử dụng bộ nhớ vật lý/ảo của process.
- **Quota direct memory:** JVM HotSpot có cấu hình như `-XX:MaxDirectMemorySize` dành cho direct buffer allocation, cần kiểm tra tương thích với runtime và mức giới hạn container. Không coi tham số này là giới hạn cho **mọi** loại native memory (thread stacks, JNI, allocator, memory mapping…).
- **Thu hồi không tức thì:** một buffer không còn được tham chiếu mới có thể được thu hồi theo cơ chế runtime/GC. Không dựa vào `buffer = null` hoặc `System.gc()` như một thao tác free đồng bộ và có thời hạn chắc chắn.
- **Dùng nhầm quota:** đặt `-Xmx` thấp không đồng nghĩa toàn bộ native memory cũng thấp; tổng RSS của process có cả heap, direct, thread stack, code cache và vùng native khác.

Có thể thấy lỗi liên quan đến direct memory reservation, `OutOfMemoryError` hoặc giới hạn hệ điều hành dù đồ thị Java heap vẫn còn chỗ trống. Cần quan sát **cả heap lẫn native/direct memory**, không chỉ heap.

### 4.3. Chi phí copy và sử dụng trong I/O

Một phép truyền dữ liệu điển hình gồm nhiều bước:

```text
Ứng dụng tạo bytes
     |
heap byte[] / heap ByteBuffer -- (có thể phải copy qua buffer trung gian) -->
     |
native I/O / kernel socket buffer --> NIC --> mạng

direct ByteBuffer -- (có thể bỏ một số bước trung gian) -->
     |
native I/O / kernel socket buffer --> NIC --> mạng
```

Đường thực tế phụ thuộc JDK, loại channel, OS, kích thước và cấu hình. Không có cam kết rằng một lần `SocketChannel.write(direct)` thì kernel không sao chép hoặc NIC đọc thẳng bộ nhớ ứng dụng. Đặc biệt với payload nhỏ, số bước kiểm tra, cache locality và chi phí quản lý có thể áp đảo lợi ích tiềm năng.

**Kết luận hiệu năng:** hỏi “chi phí cấp phát + số lần copy + access pattern + GC + memory footprint” của workload cụ thể, không chỉ “direct hay heap nhanh hơn”.

## 5. Tái sử dụng buffer: khi nào đáng làm?

Một lựa chọn có ý nghĩa là **reuse** buffer, đặc biệt direct buffer có chi phí cấp phát cao.

### 5.1. Cấp phát theo yêu cầu

```java
// Đoạn minh họa: cấp phát mới cho mỗi yêu cầu.
void handleOneRequest() {
    ByteBuffer buffer = ByteBuffer.allocateDirect(64 * 1024);
    // Dùng buffer cho I/O của request...
}
```

Điều này rất đơn giản nhưng nếu lặp với tần suất cao sẽ liên tục cấp phát các vùng native, tăng áp lực thu hồi. Với lưu lượng thấp, cách đơn giản vẫn có thể phù hợp.

### 5.2. Pool có giới hạn (bounded pool)

Một pool định nghĩa tập buffer được tạo trước hoặc tạo theo giới hạn tối đa:

```text
Pool (capacity: 3 buffers, mỗi buffer: 64 KiB)

idle: [Buffer A][Buffer B][Buffer C]
           |
           v acquire()
      handler giữ độc quyền Buffer A
           |
           v xử lý xong, không còn I/O pending
      release(Buffer A)
           |
           v
idle: [Buffer B][Buffer C][Buffer A]
```

Những thuộc tính cần có:

- **Bounded:** tối đa bao nhiêu buffer và bao nhiêu byte; không tăng vô hạn theo số kết nối/request.
- **Exclusive ownership:** mỗi buffer tại một thời điểm có đúng một bên chịu trách nhiệm ghi/đọc; `ByteBuffer` không an toàn để nhiều thread tự do thay đổi position/limit đồng thời.
- **Clear trạng thái đúng thời điểm:** `clear()` trước lần ghi mới; `flip()` khi chuyển sang đọc; `compact()` khi còn dữ liệu cần giữ. Không quên frame dở dang.
- **No early release:** chỉ trả sau khi I/O đồng bộ đã dùng hết dữ liệu hoặc callback I/O bất đồng bộ đã hoàn tất; không trả khi `SocketChannel.write` còn byte chưa ghi, hoặc một `ByteBuffer.slice()` còn được worker khác dùng.
- **Backpressure:** khi hết buffer, nên block với deadline, từ chối, hoặc áp dụng chính sách phân bổ dự phòng **có giới hạn**; đừng cấp phát mới không giới hạn và gọi đó là pooling.
- **Size classes:** thường nhóm buffer theo dung lượng (4 KiB, 16 KiB, 64 KiB...) để tránh giữ hàng nghìn buffer quá lớn chỉ cho thông điệp nhỏ. Các size class là ví dụ, không phải chuẩn Java.
- **Metrics:** số buffer idle/in-use, wait time, contention, tổng byte giữ lại, allocation miss, peak và direct memory usage.

**Pool không tự động cải thiện mọi workload.** Nếu request hiếm, buffer nhỏ, hoặc GC xử lý heap allocation rẻ, lock/queue contention và lượng bộ nhớ giữ lại trong pool có thể **làm tổng hiệu năng kém hơn**. Direct pool lớn có thể khiến application bị OOME vì native memory dù throughput chưa cao.

### 5.3. Hai chính sách khi pool cạn

1. **Chờ với giới hạn (wait/timeout):** ngăn vượt budget, tăng độ trễ khi quá tải. Có cơ chế hủy và báo quá tải rõ ràng.
2. **Cấp phát burst có trần:** bổ sung buffer cho một khoảng lưu lượng tăng đột biến, nhưng phải có hạn mức count/bytes và chính sách thu hồi. Nếu không có trần, rủi ro native memory bùng nổ.

Đặt ngân sách thô từ `số-buffer × capacity`, rồi cộng overhead khác. Ví dụ giữ **1.000 buffer × 64 KiB = 62,5 MiB byte payload** (chưa tính wrapper/metadata, memory alignment, queue và các khoản khác). 1.000 buffer không phải 1.000 kết nối bắt buộc; có thể cho phép tái dùng theo request nếu ownership và deadline được quản lý rõ.

### 5.4. Lỗi vòng đời nguy hiểm

Nếu hai handler cùng dùng một buffer:

```text
Handler 1: put("ABC"), flip(), bắt đầu gửi
Handler 2: clear(), put("XYZ"), flip()
Handler 1: tiếp tục write(...) nhưng dữ liệu/position đã bị thay đổi
```

Kết quả có thể là corrupt payload hoặc thiếu dữ liệu, không chỉ chậm. `duplicate()` và `slice()` **chia sẻ backing memory** nên có position/limit riêng nhưng vẫn có nguy cơ ghi đè vùng byte. Với direct memory, view còn tồn tại cũng có thể giữ native storage sống lâu hơn dự kiến.

Không trả buffer cho pool hai lần; không trả buffer không thuộc pool; không đưa buffer cho worker khác sau khi đã release. Ở ứng dụng thực, dùng cơ chế **lease** (`AutoCloseable` hoặc handle kèm trạng thái) và giám sát để tránh double-release/use-after-release.

## 6. Ví dụ Java 17: hai loại buffer, reuse direct buffer và truyền qua channel

Chương trình này dùng `java.nio.channels.Pipe` để kiểm tra I/O qua channel **mà không cần mạng hoặc DNS**. Nó:

1. Tạo một heap buffer và một direct buffer, in các thuộc tính quan sát được.
2. Khởi tạo một pool chỉ chứa **một direct buffer** dung lượng 16 byte, lấy buffer độc quyền.
3. Ghi thông điệp UTF-8 `NIO` vào buffer, gọi `flip()` và chuyển qua `Pipe.SinkChannel`; xử lý khả năng `write` chưa ghi hết bằng vòng `hasRemaining()`.
4. Đọc từ `Pipe.SourceChannel` vào heap buffer, gọi `flip()` để decode.
5. Trả direct buffer vào pool, lấy lại và kiểm tra **chính cùng instance** được tái sử dụng, position đã reset về 0.

Pool là ví dụ tối giản một slot dùng `ArrayBlockingQueue`, **không cấp phát quá số lượng đã định**. Nếu một handler khác đang giữ buffer, `take()` sẽ chờ; sản xuất thực tế nên thêm `poll(timeout)`/cancellation theo SLA. Ví dụ chạy tuần tự để kết quả dễ xác minh.

Lưu file **`HeapDirectBufferDemo.java`**:

```java
import java.io.EOFException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ArrayBlockingQueue;

public class HeapDirectBufferDemo {

    static final class DirectPool {
        private final ArrayBlockingQueue<ByteBuffer> idle =
                new ArrayBlockingQueue<>(1);

        DirectPool(int bytesPerBuffer) {
            idle.add(ByteBuffer.allocateDirect(bytesPerBuffer));
        }

        ByteBuffer acquire() throws InterruptedException {
            ByteBuffer buffer = idle.take();
            buffer.clear(); // reset indices; KHÔNG xóa dữ liệu cũ
            return buffer;
        }

        void release(ByteBuffer buffer) {
            buffer.clear();
            if (!idle.offer(buffer)) {
                throw new IllegalStateException("Pool already full");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ByteBuffer heap = ByteBuffer.allocate(16);
        ByteBuffer direct = ByteBuffer.allocateDirect(16);

        System.out.println("Heap direct: " + heap.isDirect());
        System.out.println("Heap has array: " + heap.hasArray());
        System.out.println("Direct direct: " + direct.isDirect());
        System.out.println("Direct has array: " + direct.hasArray());

        DirectPool pool = new DirectPool(16);
        byte[] message = "NIO".getBytes(StandardCharsets.UTF_8);
        ByteBuffer sending = pool.acquire();

        try (Pipe.SourceChannel source = Pipe.open().source()) {
            // Đoạn bên dưới mở một pipe riêng để cặp source/sink
            // luôn thuộc cùng Pipe instance.
        }

        Pipe pipe = Pipe.open();
        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink()) {

            sending.put(message);
            sending.flip();
            while (sending.hasRemaining()) {
                sink.write(sending);
            }
            pool.release(sending);

            ByteBuffer receiving = ByteBuffer.allocate(16);
            while (receiving.position() < message.length) {
                if (source.read(receiving) < 0) {
                    throw new EOFException("Pipe closed too soon");
                }
            }
            receiving.flip();

            byte[] received = new byte[receiving.remaining()];
            receiving.get(received);
            System.out.println("Pipe received: "
                    + new String(received, StandardCharsets.UTF_8));

            ByteBuffer reused = pool.acquire();
            System.out.println("Same direct buffer reused: "
                    + (sending == reused));
            System.out.println("Reused position: " + reused.position());
            pool.release(reused);
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac -encoding UTF-8 HeapDirectBufferDemo.java
java HeapDirectBufferDemo
```

**Kết quả dự kiến chính xác:**

```text
Heap direct: false
Heap has array: true
Direct direct: true
Direct has array: false
Pipe received: NIO
Same direct buffer reused: true
Reused position: 0
```

Đây là ví dụ minh họa **vòng đời buffer và tính đúng đắn**, không phải benchmark thông lượng hoặc bằng chứng direct nhanh hơn heap. `Pipe` không phải socket; semantics position/limit, `read`/`write` qua channel và cách reuse vẫn hữu ích cho việc hiểu NIO networking.

### Đọc luồng thực thi

- `allocate(16)`/`allocateDirect(16)` xác nhận các cờ `isDirect` và `hasArray` của hai buffer writable do factory tạo.
- `DirectPool` cấp phát **một** direct buffer trước khi xử lý. `acquire` không tạo buffer mới; `take` đảm bảo buffer không được hai borrower đồng thời lấy từ cùng slot, nhưng **không tự phát hiện** người gọi cố ý lưu/đổi alias.
- `put(message)` tăng position theo 3 byte, `flip()` chuyển sang trạng thái sẵn sàng đọc, rồi `sink.write` tiêu thụ byte cho đến khi `hasRemaining()` bằng false.
- `source.read(receiving)` tăng position của buffer nhận. Chương trình đọc đủ số byte biết trước của thông điệp rồi gọi `flip()` để decode.
- `release(sending)` gọi `clear` để trả trạng thái ghi về đầu buffer. Khi `acquire` lần nữa, so sánh `sending == reused` là `true` vì pool chỉ có buffer ấy.
- Buffer trực tiếp có thể được tái sử dụng mà không cần cấp phát một vùng native mới cho thông điệp thứ hai. **Điều này giảm allocation**, nhưng ta chưa đo hiệu năng tổng thể.

**Giới hạn quan trọng:** mã ví dụ dựa trên blocking `Pipe` và một request nhỏ. Với non-blocking `SocketChannel`, `write` có thể trả `0`; vòng ghi liên tục không có cơ chế chờ sẽ dẫn tới busy-spin. Trong sản phẩm cần queue phần chưa gửi và đăng ký sự kiện writable trên `Selector`, hoặc dùng asynchronous completion/timeout phù hợp.

## 7. Buffer reuse trong server SocketChannel thực tế

### 7.1. Đọc dữ liệu từ SocketChannel

```java
// Đoạn minh họa: channel và buffer có sẵn; chỉ mô tả lifecycle.
buffer.clear();
int count = channel.read(buffer);

if (count > 0) {
    buffer.flip();
    // Giải mã frame từ phần dữ liệu hiện có.
} else if (count == -1) {
    // Remote đã kết thúc phía gửi sau khi dữ liệu được xử lý.
}
// count == 0: non-blocking read có thể chưa có byte.
```

Nếu frame chưa đủ, không nên `clear()` rồi vứt phần byte dở dang. Có thể giữ lại trong state của connection hoặc dùng `compact()` cho phần chưa parse, sau đó tiếp tục đọc. Một pool buffer có thể yêu cầu trả buffer **sau** khi framing/parser thực sự không còn tham chiếu tới các byte đó.

### 7.2. Ghi dữ liệu ra SocketChannel

```java
// Đoạn minh họa: buffer đã flip() và đang ở chế độ đọc.
int count = channel.write(buffer);
if (buffer.hasRemaining()) {
    // Chưa gửi hết: giữ lại buffer và tiếp tục khi writable.
}
// Chỉ trả buffer cho pool khi không còn sử dụng/pending I/O.
```

Ngay cả khi channel nhận direct buffer, lời gọi `write` **không có nghĩa** remote application đã xử lý nội dung; TCP chỉ quản lý vận chuyển, còn tầng ứng dụng cần phản hồi riêng nếu nghiệp vụ yêu cầu. Reuse quá sớm có thể ghi đè phần payload chưa được channel tiêu thụ.

### 7.3. Kết hợp heap và direct trong một hệ thống

Một thiết kế hợp lý có thể dùng:

- **Heap byte[] hoặc heap ByteBuffer** cho parsing, thao tác chuỗi hoặc dữ liệu nhỏ cần Java array API.
- **Direct ByteBuffer** cho những đường I/O lặp lại nhiều với channel, kích thước payload đủ lớn và profile chứng minh được lợi ích.
- **Pool** cho buffer có vòng đời dài/lặp lại, nhất là direct buffer hoặc buffer kích thước lớn. Không pool mọi buffer một cách máy móc.
- **Batched/scatter-gather I/O** (khi phù hợp) để giảm syscall/chi phí xử lý, thay vì chỉ đổi heap sang direct.

Đừng sao chép dữ liệu heap→direct→heap vô điều kiện rồi coi đây là “zero-copy optimization”. Nếu pipeline tạo nội dung trên heap rồi copy sang direct để I/O, phải đo xem copy bổ sung có thật sự bù được overhead của đường I/O không.

### 7.4. Multiple threads và asynchronous I/O

`ByteBuffer` có các chỉ số mutable `position`/`limit`, không được xem là thread-safe. Dùng mẫu **một owner tại một thời điểm**, bàn giao qua queue có rào chắn đồng bộ phù hợp, hoặc dùng object immutable/independent views có quy tắc rõ ràng.

Với `AsynchronousSocketChannel.write`, buffer có thể còn được sử dụng **cho đến khi operation hoàn thành**. Không trả vào pool ngay sau khi gọi write; phải đợi callback/completion và xử lý các trường hợp partial write. Nếu dùng `slice`/`duplicate`, view chia sẻ backing memory cũng phải hết vòng đời trước khi bộ nhớ gốc có thể an toàn ghi đè.

## 8. Làm sao biết cần buffer kích thước bao nhiêu?

Không có một kích thước “chuẩn Java NIO” cho mọi ứng dụng. Nên cân nhắc:

- **Kích thước frame/request**: phần lớn request 200 byte, 4 KiB hay 1 MiB?
- **Số kết nối đồng thời**: mỗi socket giữ một buffer riêng hay buffer có thể mượn theo request?
- **Thời gian một buffer bị giữ (hold time)**: handler có chờ network/DB lâu không? Nếu có, pool sẽ cạn dù số lần read/ghi thấp.
- **Peak workload** và backpressure: nếu pool hết, xử lý tiếp hay trả lỗi tạm thời?
- **Giới hạn process/container**: tổng heap + direct + các vùng native khác phải nằm trong memory budget.
- **Bảo mật**: dữ liệu nhạy cảm có thể lưu lại trong pool sau khi `clear`.

Ví dụ ngân sách tối thiểu: **1.000 buffer × 64 KiB = 62,5 MiB vùng byte**, chưa tính overhead; thêm read + write buffer riêng sẽ tăng phần retained memory. Nếu thiết kế theo “mỗi kết nối một direct buffer 1 MiB” với hàng nghìn kết nối, bộ nhớ giữ lại sẽ rất lớn ngay cả khi đa số kết nối rảnh.

Tối ưu thường bắt đầu bằng đo **distribution** kích thước message, tần suất cấp phát, GC pressure và thời gian buffer bị chiếm, sau đó thử các size class và giới hạn pool hợp lý.

## 9. Đo đạc: tránh kết luận nhanh từ microbenchmark

Một benchmark không tốt thường đo:

```java
// Mã minh họa KHÔNG phải benchmark đáng tin.
long start = System.nanoTime();
ByteBuffer buffer = ByteBuffer.allocateDirect(4096);
long elapsed = System.nanoTime() - start;
```

Phép đo đơn lẻ dễ nhiễu do JIT, warmup, khởi tạo class, scheduling, GC/native allocation, CPU cache và cách JVM tối ưu hóa. Nó cũng không đo đường I/O thực.

Khi so sánh, hãy:

1. Dùng **JMH** (Java Microbenchmark Harness) hoặc benchmark đo toàn ứng dụng; có warmup và nhiều iteration/fork thích hợp.
2. Tách bài đo **allocation-only**, **put/get CPU-only**, **channel read/write**, **heap→direct copy**, và **pool acquire/release**. Đây là những khối chi phí khác nhau.
3. Giữ cùng kích thước payload, cùng buffer lifecycle, cùng số thread, cùng I/O path và chính sách timeout.
4. Với I/O thật, đo throughput, p50/p95/p99 latency, số syscall, CPU, GC pause và memory footprint — không chỉ một con số ns/op.
5. Đo cả đường quá tải, contention, pool exhaustion, số handler đồng thời và thời gian chờ mượn buffer.
6. Kiểm tra phương pháp benchmark không cho JIT loại bỏ công việc, không vô tình tạo buffer khác nhau giữa các nhánh và không đo cả log/console output trong hot path.
7. Lặp lại trên JDK/OS/hardware gần môi trường production vì hiệu quả direct I/O phụ thuộc platform.

### Theo dõi direct buffer qua JVM

JDK có `java.lang.management.BufferPoolMXBean` để quan sát các pool buffer như `direct`. Đây là chỉ số hữu ích về count, capacity, memory used theo API, nhưng không phải phép đo đầy đủ cho **toàn bộ** native memory của process.

```java
// Đoạn minh họa; import java.lang.management.ManagementFactory;
// và java.lang.management.BufferPoolMXBean.
for (BufferPoolMXBean bean
        : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    if ("direct".equals(bean.getName())) {
        System.out.println("Direct buffer count: " + bean.getCount());
        System.out.println("Direct capacity: " + bean.getTotalCapacity());
        System.out.println("Direct memory used: " + bean.getMemoryUsed());
    }
}
```

Với HotSpot, `-XX:NativeMemoryTracking=summary` và `jcmd <pid> VM.native_memory summary` có thể hỗ trợ điều tra **các vùng native memory do JVM theo dõi**, cần bật từ lúc khởi động và lưu ý overhead/độ bao phủ. Theo dõi thêm process RSS và giới hạn container. Không kỳ vọng mọi allocator/JNI/native memory đều hiện đầy đủ dưới một nhãn `direct`.

### Khi nào direct đáng thử trước?

Direct buffer đáng thử khi có **I/O channel lặp lại liên tục**, payload đủ lớn, allocation/GC hoặc copy overhead đáng kể, và có thể quản lý reuse tốt. Heap buffer vẫn có thể phù hợp hơn nếu chủ yếu xử lý Java array, thông điệp nhỏ hoặc vòng đời ngắn, hoặc nếu direct pool gây chiếm RAM không cần thiết. **Lựa chọn cuối cùng phải dựa trên profile của workload thật.**

## 10. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| “Direct luôn nhanh hơn heap.” | Tối ưu sai, tăng allocation/native pressure | Benchmark theo kích thước và đường I/O thực |
| Cấp phát `allocateDirect` cho từng packet nhỏ | Overhead cấp phát/thu hồi lớn | Cân nhắc heap hoặc pool có giới hạn khi đo thấy lợi ích |
| Pool direct không giới hạn | Native memory bùng nổ, OOME | Budget theo số lượng × size class, backpressure |
| Chỉ theo dõi `-Xmx` hoặc heap usage | Bỏ sót direct/native memory và RSS | Đo BufferPoolMXBean, JVM native memory và container |
| Dùng `System.gc()` để “giải phóng buffer ngay” | Không có bảo đảm thời gian thu hồi | Quản lý vòng đời, giới hạn retained buffers |
| Lấy `array()` trên direct buffer | `UnsupportedOperationException` | Kiểm tra `hasArray()`, dùng `get`/`put`/channel |
| Quên `flip()` trước `channel.write` | Gửi vùng sai hoặc không gửi gì | Quản lý position/limit rõ ràng |
| `clear()` khi frame chưa đọc hết | Mất dữ liệu hoặc ghi đè phần chưa xử lý | Dùng `compact()` hoặc state machine cho framing |
| Gọi `clear` để xóa dữ liệu bí mật | Dữ liệu cũ vẫn tồn tại trong backing memory | Zero hóa theo chính sách nếu có yêu cầu bảo mật |
| Trả buffer cho pool trước khi write completion | Payload chưa gửi bị ghi đè | Đợi `hasRemaining()==false` hoặc async completion |
| Một buffer cho hai thread cùng sửa | Race position/limit và corrupt content | Exclusive ownership, handoff có đồng bộ |
| Dùng `slice` rồi trả backing vào pool sớm | View khác đọc dữ liệu bị thay đổi | Theo dõi lifetime của mọi view/alias |
| Pool chặn vô hạn khi cạn | Thread/request treo, cascade latency | Đặt deadline khi borrow và chính sách quá tải |
| Dùng busy loop khi non-blocking write trả `0` | CPU 100% | Chờ writable event/callback qua `Selector` |
| Coi `clear` là giải phóng bộ nhớ | Buffer vẫn chiếm capacity | Trả về pool/giải phóng reference theo lifecycle |
| Cho rằng `FileChannel.transferTo` và direct buffer là một | Nhầm hai cơ chế tối ưu khác nhau | Phân biệt API zero-copy transfer và NIO direct allocation |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `ByteBuffer.allocate(4096)` và `ByteBuffer.allocateDirect(4096)` có cùng `capacity()` không? Có nhất thiết cùng chi phí cấp phát không?

**Trả lời:** Có cùng capacity 4.096 byte, nhưng không nhất thiết cùng chi phí cấp phát. Heap buffer chủ yếu sử dụng Java heap; direct buffer thường quản lý vùng native, có overhead khác và không nên cấp phát liên tục khi không cần.

**Câu 2.** Direct buffer có phải “nằm ngoài mọi cơ chế GC” không?

**Trả lời:** Không. Object wrapper và lifecycle có liên quan đến GC/JVM; vùng dữ liệu thường ngoài Java heap và có cách/quota thu hồi riêng. Không coi `System.gc()` là lời gọi giải phóng tức thì đáng tin.

**Câu 3.** Tại sao `ByteBuffer.allocateDirect(1024).array()` không nên được dùng?

**Trả lời:** Buffer direct do factory tạo không có accessible Java backing array; `hasArray()` là false và gọi `array()` không được hỗ trợ. Dùng API tương đối/tuyệt đối `get`, `put`, view hoặc channel.

**Câu 4.** `clear()` có xóa byte cũ hoặc giảm capacity không?

**Trả lời:** Không. `clear()` chỉ reset position=0, limit=capacity và mark; byte còn đó tới khi ghi đè. Pool phải quan tâm bảo mật, lifetime và quy tắc ownership.

**Câu 5.** `SocketChannel.write(buffer)` trả về 12 nhưng `buffer.remaining()` vẫn còn 30. Có thể trả buffer về pool chưa?

**Trả lời:** Chưa. Vẫn còn byte chưa được channel tiêu thụ. Phải giữ buffer tới khi gửi xong theo chính sách; với non-blocking I/O cần chờ writable/async completion thay vì busy-spin.

**Câu 6.** Một server tạo 1.000 direct buffer, mỗi buffer 64 KiB. Chiếm ít nhất bao nhiêu dữ liệu trực tiếp theo capacity?

**Trả lời:** 1.000 × 64 KiB = 62,5 MiB byte payload. Total native footprint có thể lớn hơn do overhead và các vùng nhớ khác.

**Câu 7.** Nếu chỉ phục vụ request nhỏ và `ByteBuffer.allocate` tạo rất rẻ, có cần pool heap buffer không?

**Trả lời:** Không mặc định. Pooling có thể tăng retained heap/contended queue. Hãy đo allocation rate, GC, latency, overhead acquire/release và độ phức tạp.

**Câu 8.** `slice()` có nhân đôi nội dung buffer không? Có thể trả backing vào pool khi view còn dùng không?

**Trả lời:** `slice()` tạo view dùng chung byte storage, có vị trí riêng; không copy payload. Không được tái sử dụng/ghi đè backing memory nếu view còn đang đọc hoặc ghi.

**Câu 9.** Tại sao dùng direct buffer không đồng nghĩa zero-copy từ JVM tới card mạng?

**Trả lời:** Direct giúp một số đường I/O native tránh copy trung gian; hệ thống có thể vẫn copy qua kernel socket buffer, thực hiện syscall, checksum và các bước của network stack. Zero-copy transfer có điều kiện/API khác.

**Câu 10.** Trong code demo, vì sao kiểm tra `sending == reused` và `position() == 0`?

**Trả lời:** Để chứng minh buffer direct được **tái sử dụng cùng instance** và các chỉ số đã reset, không cấp phát vùng direct mới cho lần mượn thứ hai. Điều này không tự chứng minh pool nhanh hơn mọi cách cấp phát.

## 12. Checklist áp dụng cho Java NIO networking

Trước khi chọn direct buffer và pooling cho một server:

1. Biết kích thước message, số lượng socket/request, số lần copy và call path của channel.
2. Định nghĩa rõ read buffer, write buffer, framing, vòng đời position/limit và khi nào `flip`/`compact`/`clear`.
3. Chọn heap/direct bằng benchmark và profile, không theo suy luận “direct mặc định tốt”.
4. Nếu pool, có budget cho count/bytes, size classes, timeouts, backpressure và metrics.
5. Bảo đảm exclusive ownership; mọi `slice/duplicate` hoặc asynchronous I/O phải hoàn tất trước khi reuse.
6. Theo dõi cả heap, direct/native memory, process RSS, GC và độ trễ tail.
7. Có cleanup cho đường lỗi, timeout, hủy, shutdown; đừng dùng `clear` thay cho giải phóng bộ nhớ hay xóa dữ liệu.
8. Ưu tiên công cụ/thư viện đã có lifecycle quản lý buffer tốt khi phù hợp với stack hiện tại.

**Kết luận:** Heap buffer dễ tích hợp với Java heap và `byte[]`, cấp phát thường rẻ; direct buffer dùng vùng dữ liệu thường ở native memory, có thể hữu ích cho I/O channel nhưng cấp phát/thu hồi và chiếm native memory đắt hơn. Tái sử dụng thông qua pool giảm allocation churn **khi thật sự cần**, đổi lại phải chịu trách nhiệm về bounded memory, thread ownership, timeout và vòng đời buffer. Tốc độ và lợi ích cuối cùng phải được đo từ công việc thực tế, không suy ra chỉ từ `allocateDirect`.

Tài liệu tham khảo: Java SE 17 API `java.nio.ByteBuffer`, `java.nio.Buffer`, `java.nio.channels.SocketChannel`, `java.nio.channels.Pipe`, `java.lang.management.BufferPoolMXBean`; tài liệu HotSpot về direct memory và Native Memory Tracking.
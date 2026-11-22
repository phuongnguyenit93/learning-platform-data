# ByteBuffer: capacity, position, limit và vùng byte còn lại

## 1. Hiểu đúng bốn đại lượng quan trọng nhất

`java.nio.ByteBuffer` là một vùng chứa byte kèm **trạng thái đọc/ghi**. Nó là công cụ cốt lõi khi làm việc với `SocketChannel`, `FileChannel`, xử lý giao thức nhị phân, bộ giải mã và nhiều API Java NIO. Một `ByteBuffer` không chỉ là một `byte[]`: nó theo dõi vùng byte có thể thao tác tiếp bằng **capacity**, **position**, **limit** và **remaining**.

| Thuộc tính/API | Diễn giải | Điều cần nhớ |
|---|---|---|
| `capacity()` | **Dung lượng toàn bộ buffer** tính bằng byte, cố định trong vòng đời đối tượng | Không đổi sau `flip()`, `clear()` hay `compact()` |
| `position()` | **Chỉ số của byte kế tiếp** mà thao tác tương đối (`get()`/`put()`) sẽ đọc/ghi | Thường tăng sau đọc/ghi tương đối thành công |
| `limit()` | **Ranh giới loại trừ**: các thao tác tương đối không được vượt vị trí này | Có thể nhỏ hơn capacity |
| `remaining()` | Số byte từ position đến ngay trước limit, tức **`limit() - position()`** | Số byte còn có thể đọc hoặc ghi trong trạng thái hiện tại |
| `hasRemaining()` | `remaining() > 0` | Không cho biết socket/network đã có thêm byte hay chưa |

**Bất biến:** `0 <= position <= limit <= capacity`. Nếu có mark hợp lệ, còn có `0 <= mark <= position`. Mọi chỉ số trong API đều tính từ **0**, còn `limit` là cận trên **không bao gồm**.

~~~text
ByteBuffer capacity = 8, position = 2, limit = 5

index:       0    1    2    3    4    5    6    7
           +----+----+----+----+----+----+----+----+
contents:  | A  | B  | C  | D  | E  | ?  | ?  | ?  |
           +----+----+----+----+----+----+----+----+
                      ^              ^              ^
                   position         limit         capacity
remaining = limit - position = 5 - 2 = 3 (C, D, E)
~~~

Dấu `?` minh họa vùng không thuộc **dữ liệu đang được dùng** sau `flip()`; nó không khẳng định ô nhớ mang byte gì. Các byte trước `position` cũng vẫn có thể tồn tại vật lý, nhưng đã được tiêu thụ theo quy ước đọc tương đối.

### “Vùng byte còn lại” phụ thuộc giai đoạn

`remaining()` **không có một ý nghĩa nghiệp vụ cố định**:

- Khi buffer đang được **điền bằng `put` hoặc `channel.read(buffer)`**: remaining cho biết **bao nhiêu chỗ còn được phép điền tới limit**.
- Sau `flip()`, khi buffer được **lấy dữ liệu bằng `get` hoặc `channel.write(buffer)`**: remaining cho biết **bao nhiêu byte chưa được tiêu thụ/chuyển ra** trong cửa sổ đọc hiện tại.
- `remaining() == 0` nghĩa **position == limit**, không chứng minh một kết nối TCP đã đóng, đã nhận đủ một message hay đang có EOF.
- Trong một ByteBuffer đã được `clear()`, remaining có thể bằng capacity **ngay cả khi chưa có một byte dữ liệu hợp lệ nào được đọc từ socket**.

Java **không có cờ “read mode” hoặc “write mode”** trong `ByteBuffer`; đó là cách người lập trình diễn giải cùng ba chỉ số position, limit, capacity.

## 2. Hai chu kỳ điển hình: điền dữ liệu và tiêu thụ dữ liệu

Khởi tạo:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
~~~

Trạng thái đầu tiên: `capacity=8, position=0, limit=8, remaining=8`. Mảng được cấp phát và khởi tạo bằng byte 0, nhưng **không có nghĩa buffer đang mang tám byte input từ mạng**.

### 2.1. Đưa năm byte vào buffer

~~~java
buffer.put(new byte[] {'A', 'B', 'C', 'D', 'E'});
~~~

Sau thao tác tương đối `put(byte[])`: `position=5, limit=8, remaining=3`. Năm byte đã đặt ở index 0..4, và còn ba vị trí được phép ghi.

~~~text
WRITE/FILL:
index       0   1   2   3   4   5   6   7
            A   B   C   D   E   .   .   .
                                ^           ^
                           position=5    limit=8
~~~

### 2.2. `flip()` để đọc những byte vừa điền

~~~java
buffer.flip();
~~~

`flip()` thực hiện đúng logic:

~~~java
// Mô tả kết quả trạng thái; không phải cách triển khai nội bộ.
int oldPosition = buffer.position(); // 5
buffer.limit(oldPosition);           // limit = 5
buffer.position(0);                  // position = 0
~~~

Sau `flip`: `capacity=8, position=0, limit=5, remaining=5`. Chỉ những byte `A B C D E` thuộc phạm vi đọc tương đối; ba byte còn lại bên ngoài limit không được đưa ra cùng dữ liệu hợp lệ.

`flip()` không đảo nội dung byte và không gửi dữ liệu qua mạng. Nó chỉ thay đổi **các mốc trạng thái**.

### 2.3. Lấy hai byte bằng `get`

~~~java
byte[] firstTwo = new byte[2];
buffer.get(firstTwo); // A, B
~~~

Sau đó `position=2, limit=5, remaining=3`. Vùng còn lại là `C D E`. Nếu gọi `buffer.get()` thêm ba lần, position sẽ thành 5 và remaining thành 0. Lần tiếp theo ném `BufferUnderflowException`; **không tự chờ socket gửi thêm**.

### 2.4. `compact()` khi vẫn còn byte chưa xử lý

Sau khi đã tiêu thụ `A B` và còn `C D E`:

~~~java
buffer.compact();
~~~

`compact()` **dời mọi byte từ `position` tới `limit - 1` về đầu buffer**, sau đó:

- `position = số byte được giữ lại = oldRemaining = 3`.
- `limit = capacity = 8`.
- `remaining = 8 - 3 = 5`, là dung lượng để điền tiếp dữ liệu mới.
- `mark` bị xóa.

~~~text
BEFORE compact:              AFTER compact:
[A][B][C][D][E][?][?][?]     [C][D][E][?][?][?][?][?]
       ^        ^                     ^                 ^
    pos=2     lim=5                 pos=3             lim=8
~~~

Từ đây có thể `put('F')`, rồi `flip()` và đọc `CDEF`. Điều này hữu ích khi **một message chưa đủ byte** hoặc khi **`SocketChannel.write` chỉ gửi được một phần**.

**Không nhầm `compact()` với `clear()`:** `compact` **giữ các byte chưa tiêu thụ**, còn `clear` chỉ đặt lại chỉ số và cho phép ghi đè toàn bộ vùng.

## 3. Phân biệt `flip()`, `clear()`, `rewind()` và `compact()`

| Phương thức | `position` sau gọi | `limit` sau gọi | Nội dung byte | Dùng khi |
|---|---:|---:|---|---|
| `flip()` | `0` | Position cũ | Không thay byte | Vừa ghi/nhận xong một đợt, chuẩn bị đọc/gửi |
| `clear()` | `0` | `capacity` | **Không xóa byte** | Đã xong mọi dữ liệu cần giữ, chuẩn bị ghi đè |
| `rewind()` | `0` | **Giữ limit cũ** | Không thay byte | Muốn đọc/gửi lại phần đang nằm trong limit |
| `compact()` | Old `remaining` | `capacity` | Di chuyển phần **chưa tiêu thụ** về đầu | Cần giữ dữ liệu dư và tiếp tục điền |
| `mark()` | Giữ nguyên | Giữ nguyên | Không thay byte | Lưu position hiện tại để quay lại |
| `reset()` | Về mark trước đó | Giữ nguyên | Không thay byte | Quay về position đã đánh dấu |

`flip()`, `clear()`, `rewind()` và `compact()` đều loại bỏ mark đang có; `reset()` khi chưa có mark hợp lệ ném `InvalidMarkException`.

Điểm dễ bỏ qua: nếu gọi `flip()` trên buffer có `position=0`, nó sẽ đặt `limit=0`; sau đó `remaining()=0`. Do vậy không gọi `flip` hai lần liên tiếp rồi mong vẫn còn dữ liệu như cũ. Nếu chỉ cần đọc lại dữ liệu của cửa sổ hiện tại, dùng `rewind()`.

### Ví dụ so sánh nhanh

Giả sử ban đầu `capacity=10, position=4, limit=7`:

| Lệnh trên buffer riêng có trạng thái ban đầu này | Kết quả |
|---|---|
| `flip()` | `position=0, limit=4, remaining=4` |
| `clear()` | `position=0, limit=10, remaining=10` |
| `rewind()` | `position=0, limit=7, remaining=7` |
| `compact()` | `position=3, limit=10, remaining=7`; giữ byte ở index 4..6 |

Bảng giả định **mỗi lệnh được thử độc lập trên buffer có cùng trạng thái trước**, không phải gọi nối tiếp bốn lệnh vào một đối tượng.

## 4. Ví dụ Java 17+ chạy được: theo dõi từng thay đổi

Chương trình không dùng network để kết quả có thể lặp lại chính xác. Nó đi qua chu trình ghi → `flip` → đọc một phần → truy cập tuyệt đối → `compact` → ghi tiếp → `flip` → đọc hết, rồi minh họa `rewind`, `clear`, `wrap` và `slice`.

Tạo tệp **`ByteBufferStateDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class ByteBufferStateDemo {
    static void state(String label, ByteBuffer b) {
        System.out.printf("%s cap=%d pos=%d lim=%d rem=%d%n",
                label, b.capacity(), b.position(),
                b.limit(), b.remaining());
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        state("new", b);
        b.put("ABCDE".getBytes(StandardCharsets.US_ASCII));
        state("put5", b);
        b.flip();
        state("flip", b);

        byte[] firstTwo = new byte[2];
        b.get(firstTwo);
        System.out.println("read=" +
                new String(firstTwo, StandardCharsets.US_ASCII));
        state("get2", b);

        System.out.println("absolute=" + (char) b.get(2));
        state("absolute-get", b);

        b.compact();
        state("compact", b);
        b.put((byte) 'F');
        b.flip();

        byte[] remaining = new byte[b.remaining()];
        b.get(remaining);
        System.out.println("result=" +
                new String(remaining, StandardCharsets.US_ASCII));
        state("consumed", b);

        b.rewind();
        state("rewind", b);
        b.clear();
        state("clear", b);

        byte[] source = {10, 20, 30, 40, 50};
        ByteBuffer view = ByteBuffer.wrap(source, 1, 3);
        state("wrap", view);
        ByteBuffer slice = view.slice();
        state("slice", slice);
        slice.put(0, (byte) 99);
        System.out.println("shared=" + source[1]);
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 ByteBufferStateDemo.java
java ByteBufferStateDemo
~~~

**Stdout đã xác minh** bằng biên dịch `--release 17` và chạy trên OpenJDK 24:

~~~text
new cap=8 pos=0 lim=8 rem=8
put5 cap=8 pos=5 lim=8 rem=3
flip cap=8 pos=0 lim=5 rem=5
read=AB
get2 cap=8 pos=2 lim=5 rem=3
absolute=C
absolute-get cap=8 pos=2 lim=5 rem=3
compact cap=8 pos=3 lim=8 rem=5
result=CDEF
consumed cap=8 pos=4 lim=4 rem=0
rewind cap=8 pos=0 lim=4 rem=4
clear cap=8 pos=0 lim=8 rem=8
wrap cap=5 pos=1 lim=4 rem=3
slice cap=3 pos=0 lim=3 rem=3
shared=99
~~~

Giải mã điểm mấu chốt:

- `new`: capacity 8, position 0, limit 8. `remaining=8` nghĩa **có thể ghi tám byte**, không có nghĩa đã nhận tám byte hợp lệ từ mạng.
- `put5`: `position` đi từ 0 đến 5, remaining còn 3.
- `flip`: `limit` trở thành 5, position trở về 0; remaining giờ biểu thị năm byte có thể đọc.
- `get2`: tiêu thụ hai byte `AB`; chỉ `CDE` còn trong cửa sổ.
- `absolute=C`: `get(2)` trả byte ở index 2 mà **không đổi position**; vì vậy dòng `absolute-get` vẫn `pos=2`.
- `compact`: ba byte `CDE` được giữ ở đầu; `pos=3` cho phép ghi ngay `F` vào index 3.
- `result=CDEF`: sau `flip` và đọc hết, `position=limit=4` nên remaining bằng 0, dù capacity vẫn 8.
- `rewind`: position 0 và limit 4, có thể đọc lại `CDEF`.
- `clear`: position 0, limit 8, sẵn sàng **ghi đè**; clear không xóa ký tự CDEF đã nằm trong vùng nhớ.
- `wrap`: với mảng dài 5 và offset 1, length 3, trạng thái **capacity=5, position=1, limit=4**, không phải capacity=3.
- `slice`: lát cắt từ vùng remaining của `view` có capacity=3, position=0, limit=3; ghi tại index 0 làm `source[1]` thành 99 vì hai buffer cùng chia sẻ vùng byte.

## 5. Công thức và các thao tác index: tương đối so với tuyệt đối

### 5.1. Cách tính chính xác

Với ByteBuffer:

~~~text
remaining = limit - position
hasRemaining = remaining > 0
0 <= position <= limit <= capacity
~~~

`remaining()` cho biết số **byte**, vì đây là `ByteBuffer`. Với `CharBuffer` hoặc `IntBuffer`, remaining tính theo **số phần tử loại tương ứng**, không mặc nhiên là byte.

**Không nên** lấy `capacity - position` thay cho remaining trong mọi hoàn cảnh. Sau `flip`, limit thường nhỏ hơn capacity, nên `capacity-position` có thể **bao gồm byte nằm ngoài cửa sổ hợp lệ**.

### 5.2. `get()/put()` tương đối và `get(index)/put(index, value)` tuyệt đối

| API | Trạng thái position | Ràng buộc |
|---|---|---|
| `get()` | Tăng 1 nếu thành công | Cần `remaining() >= 1` |
| `put(byte)` | Tăng 1 nếu thành công | Cần `remaining() >= 1`, buffer phải writable |
| `get(byte[] dst)` | Tăng theo số byte đọc | Số byte yêu cầu không vượt remaining |
| `put(byte[] src)` | Tăng theo số byte ghi | Số byte yêu cầu không vượt remaining |
| `get(index)` | **Không đổi** | `0 <= index < limit` |
| `put(index, byte)` | **Không đổi** | `0 <= index < limit`, buffer writable |
| `getInt()` / `putInt(int)` | Tăng **4 byte** | Cần remaining ít nhất 4 |
| `getInt(index)` / `putInt(index, int)` | **Không đổi** | Bốn byte từ index phải nằm trong limit |

Ví dụ nhỏ:

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.put(new byte[] {10, 20, 30});
b.flip();                          // pos=0, lim=3
byte x = b.get(2);                 // x=30, pos vẫn 0
byte y = b.get();                  // y=10, pos=1
b.put(1, (byte) 99);               // sửa index 1, pos vẫn 1
~~~

Đây là **trích đoạn**; các phép tính trạng thái có thể dự đoán được mà không cần tạo chương trình riêng. `get(index)` không được vượt **limit**, dù vị trí đó vẫn nhỏ hơn capacity. Khi cần thao tác một phần mảng và tránh chuyển position nhiều lần, có thể dùng các overload `get/put` với offset và length, nhưng phải tự kiểm soát bounds của mảng **và** remaining.

### 5.3. Ngoại lệ khi đọc/ghi ngoài cửa sổ

| Tình huống | Ngoại lệ thường gặp | Nguyên nhân |
|---|---|---|
| `get()` khi position == limit | `BufferUnderflowException` | Không còn phần tử cho relative read |
| `put(...)` khi không đủ remaining | `BufferOverflowException` | Không còn đủ chỗ trong cửa sổ ghi |
| `get(index)` với index < 0 hoặc index >= limit | `IndexOutOfBoundsException` | Absolute index sai |
| `put(...)` trên read-only ByteBuffer | `ReadOnlyBufferException` | Vùng nhìn chỉ đọc |
| `reset()` khi mark chưa định nghĩa hoặc đã bị bỏ | `InvalidMarkException` | Mark không hợp lệ |
| `position(n)` với n > limit, `limit(n)` với n > capacity | `IllegalArgumentException` | Vi phạm bất biến |

`BufferUnderflowException` và `BufferOverflowException` là lỗi của **cửa sổ bộ nhớ ByteBuffer**, không phải tín hiệu TCP/UDP đã hết dữ liệu hoặc kết nối mạng mất gói.

## 6. Đổi `position` và `limit` bằng tay, `mark/reset`

Ta có thể thay giới hạn theo protocol, nhưng các mốc phải hợp lệ:

~~~java
ByteBuffer b = ByteBuffer.allocate(10);
b.limit(6);        // cap=10, pos=0, lim=6, rem=6
b.position(2);     // cap=10, pos=2, lim=6, rem=4
b.mark();          // Đánh dấu tại position 2
b.get();           // position=3
b.reset();         // position quay lại 2
~~~

Nếu giảm limit xuống dưới position, Java tự **hạ position về limit mới** để giữ bất biến. Nếu hạ position xuống dưới mark, hoặc hạ limit xuống dưới mark, **mark bị hủy**. Nếu gọi `clear/flip/rewind/compact`, mark cũng bị hủy.

Trong parser, `mark` và `reset` hữu ích khi thử đọc header: nếu payload chưa đủ, khôi phục position về đầu header trước khi `compact()` để giữ **toàn bộ frame chưa hoàn tất**.

**Không xem `mark` là checkpoint vĩnh viễn**: nó chỉ là một index trong buffer hiện tại, bị hủy bởi nhiều thao tác thay đổi trạng thái, và không quản lý transaction hay đồng bộ giữa các thread.

## 7. `allocate`, `allocateDirect`, `wrap`, `slice` và `duplicate`

| Cách tạo | Dữ liệu được lưu ở đâu / chia sẻ thế nào? | Trạng thái ban đầu thường thấy |
|---|---|---|
| `ByteBuffer.allocate(n)` | Heap buffer có backing `byte[]` riêng | cap=n, pos=0, lim=n |
| `ByteBuffer.allocateDirect(n)` | Direct buffer để JVM/I/O tương tác hiệu quả hơn trong một số ngữ cảnh | cap=n, pos=0, lim=n |
| `ByteBuffer.wrap(array)` | **Chia sẻ** `byte[]` đã cho | cap=array.length, pos=0, lim=array.length |
| `ByteBuffer.wrap(array, off, len)` | Chia sẻ nguyên mảng, chọn cửa sổ bằng position/limit | cap=array.length, pos=off, lim=off+len |
| `buffer.slice()` | Cửa sổ mới **chia sẻ byte** của vùng remaining | cap=remaining cũ, pos=0, lim=cap mới |
| `buffer.duplicate()` | View khác **chia sẻ dữ liệu** với buffer gốc, nhưng có position/limit/mark độc lập | Giá trị position/limit/capacity ban đầu bằng bản gốc |
| `buffer.asReadOnlyBuffer()` | View chỉ đọc, **chia sẻ byte**, không được `put` | Không cho ghi qua view |

**Chia sẻ byte không có nghĩa chia sẻ các chỉ số position/limit**. Khi đổi position trong một `slice`, position của buffer mẹ không chạy theo; khi sửa **nội dung byte**, buffer mẹ có thể nhìn thấy thay đổi đó.

### Bẫy `wrap(array, offset, length)`

Ví dụ Java đã chạy ở phần 4:

~~~java
byte[] source = {10, 20, 30, 40, 50};
ByteBuffer view = ByteBuffer.wrap(source, 1, 3);
// capacity=5, position=1, limit=4, remaining=3
ByteBuffer smallView = view.slice();
// capacity=3, position=0, limit=3, remaining=3
~~~

**Sai lầm thường gặp:** nghĩ `wrap(array, 1, 3)` tạo buffer capacity 3, position 0. Theo Javadoc, nó giữ **capacity của toàn mảng** và dùng position/limit để mô tả đoạn con; `slice()` mới tạo view có **capacity đúng bằng vùng remaining** và position 0.

`slice()` **không copy dữ liệu**. Nếu cần bản sao độc lập, cấp phát mảng/buffer riêng và copy chính xác vùng `remaining`. Với direct buffer, `hasArray()` thường false và `array()` có thể ném `UnsupportedOperationException`; với read-only heap buffer, `array()` cũng không nhất thiết cho phép truy cập. Không giả định mọi ByteBuffer đều có `byte[]` truy cập được.

### Khi nào chọn direct buffer?

Direct buffer có thể giúp một số thao tác I/O giảm copy qua heap, nhất là khi tái sử dụng lâu dài. Đổi lại, cấp phát/thu hồi direct buffer có chi phí và ảnh hưởng tới bộ nhớ ngoài heap. **Không có quy tắc "allocateDirect luôn nhanh hơn"**: cần benchmark trên workload, JDK và hệ điều hành cụ thể. Không tạo direct buffer mới cho từng message nhỏ nếu không có lý do hiệu năng được đo đạc.

## 8. Liên hệ với `SocketChannel`: đọc và ghi từng phần

ByteBuffer là đối tác trực tiếp của các API channel. Đây là lý do **`flip` và `compact`** quan trọng trong bài networking.

### 8.1. Đọc từ channel vào buffer

~~~java
// Trích đoạn minh họa; channel là SocketChannel đã mở.
ByteBuffer buf = ByteBuffer.allocate(4096); // pos=0, lim=4096
int n = channel.read(buf);                  // đặt byte vào vị trí pos trở đi
if (n > 0) {
    buf.flip();                             // giới hạn chỉ tại số byte thực nhận
    while (buf.hasRemaining()) {
        byte oneByte = buf.get();
        // Xử lý đúng byte đã nhận, có thể thuộc một phần của message.
    }
    buf.compact();                          // giữ phần chưa xử lý nếu có
} else if (n == -1) {
    // Đã thấy EOF của chiều đọc; cần kiểm tra message dở dang.
} else {
    // n == 0: không có byte nào được chuyển trong lần gọi này.
}
~~~

Đây **không phải chương trình độc lập**. Ở `SocketChannel` cấu hình **non-blocking**, `read` có thể trả 0 vì chưa có byte sẵn. Ở cả mô hình blocking/non-blocking, `read` có thể trả 0 khi buffer không còn remaining. `-1` biểu thị end-of-stream; đó **không phải** giá trị trả về của `ByteBuffer.get()`.

Để đọc một khung thông điệp, code phải có thêm protocol framing (length/delimiter), xử lý byte dở dang, EOF và timeout. `n > 0` **không tự mang nghĩa đã nhận đủ một message**, tương tự cách TCP stream hoạt động.

### 8.2. Ghi buffer ra channel

~~~java
// Trích đoạn minh họa; channel là SocketChannel đã kết nối.
ByteBuffer outgoing = java.nio.charset.StandardCharsets.UTF_8
        .encode("PING\n"); // Đã ở trạng thái có dữ liệu để đọc ra.
while (outgoing.hasRemaining()) {
    int written = channel.write(outgoing);
    if (written == 0) {
        // Với non-blocking channel: chờ tín hiệu OP_WRITE từ Selector
        // thay vì quay CPU liên tục ở vòng lặp thực tế.
        break;
    }
}
~~~

`channel.write(outgoing)` tiêu thụ **tối đa** số byte `outgoing.remaining()` tại thời điểm gọi; nó **có thể ghi ít hơn** số này. `ByteBuffer.position` tăng theo số byte được channel chấp nhận. Nếu buffer vẫn `hasRemaining()`, ứng dụng phải **giữ buffer và ghi tiếp sau khi channel writable**, không được `clear` rồi bỏ byte còn lại. Với non-blocking channel, chỉ cố viết một lần rồi `break` là một **minh họa luồng điều khiển**, cần bổ sung cơ chế selector/event loop để thực sự hoàn tất gửi.

Đây cũng là nơi nhiều bug phát sinh: thấy `channel.write` trả số dương rồi cho rằng toàn bộ buffer đã đi qua socket. Con số trả về là **số byte viết trong lần đó**, không phải xác nhận remote đã đọc hay xử lý.

### 8.3. `compact` khi parser chỉ đọc được một phần frame

Ví dụ một giao thức bắt đầu bằng **4 byte độ dài big-endian**, sau đó là payload. Sau khi `channel.read(buffer)` đặt thêm byte vào buffer đang ở pha điền dữ liệu, parser có thể dùng logic:

~~~java
// Trích đoạn lõi parser, giả định buffer đang ở pha điền,
// channel.read(buffer) đã được xử lý trước đó.
// MAX_FRAME là ngưỡng bảo vệ do ứng dụng đặt, chẳng hạn 4096.
buffer.flip(); // Bắt đầu đọc vùng dữ liệu đã tích lũy.
while (buffer.remaining() >= Integer.BYTES) {
    buffer.mark();                      // Ghi nhớ đầu header
    int length = buffer.getInt();       // 4 byte, BIG_ENDIAN mặc định
    if (length < 0 || length > MAX_FRAME) {
        throw new java.io.IOException("Invalid length");
    }
    if (buffer.remaining() < length) {
        buffer.reset();                 // Giữ cả header còn dang dở
        break;                          // Đợi thêm byte từ lần read sau
    }
    byte[] payload = new byte[length];
    buffer.get(payload);
    handleFrame(payload);
}
buffer.compact(); // Giữ toàn bộ phần chưa parse, chuẩn bị nhận tiếp.
~~~

Đây là **trích đoạn parser**, không phải một chương trình tự chạy: `buffer`, `MAX_FRAME` và `handleFrame` phải được định nghĩa. Nếu **chưa đủ 4 byte header**, vòng lặp không bắt đầu và `compact` giữ tất cả các byte còn lại. Nếu đủ header nhưng thiếu payload, `reset` khôi phục position về đầu header, để `compact` giữ nguyên header và payload dở dang.

Giới hạn quan trọng: nếu **một frame dài hơn sức chứa buffer**, logic này có thể không tiến lên được vì không còn chỗ để nhận tiếp. Production parser phải chọn buffer đủ lớn cho max frame, mở rộng buffer có giới hạn, hoặc xử lý payload theo từng phần mà không giữ cả frame trong một buffer. `compact()` **không tự tăng capacity**.

## 9. Byte order, kiểu dữ liệu nhiều byte và text

`ByteBuffer` có các thao tác đọc/ghi số như `getShort`, `getInt`, `getLong`, `putInt`. Những thao tác này dùng **byte order**. Mặc định một ByteBuffer vừa được tạo có thứ tự **BIG_ENDIAN**, có thể thay đổi bằng:

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.order(java.nio.ByteOrder.LITTLE_ENDIAN);
b.putInt(0x01020304); // Byte bên trong theo thứ tự 04 03 02 01
b.flip();
int n = b.getInt();  // n=0x01020304 với cùng byte order
~~~

Bốn byte của một `int` chiếm **4 đơn vị remaining**. Nếu `remaining() < 4`, `getInt()` ném `BufferUnderflowException` chứ không tự đọc thêm từ network. Với giao thức nhị phân, hai bên phải **thỏa thuận byte order**, signed/unsigned representation và độ dài trường trước khi parse.

**Một byte không nhất thiết là một ký tự.** UTF-8 có ký tự nhiều byte; ranh giới `channel.read(ByteBuffer)` có thể cắt ngang ký tự. Đừng giải mã mỗi chunk thành String độc lập rồi giả định không mất ký tự. Khi xử lý stream text, hãy bảo toàn byte còn thiếu hoặc dùng `CharsetDecoder` với trạng thái phù hợp. Khi chuyển một ByteBuffer thành mảng byte để giải mã, chỉ copy vùng `position..limit` hợp lệ thay vì toàn bộ `capacity`.

Ví dụ:

~~~java
byte[] bytes = new byte[buffer.remaining()];
buffer.get(bytes); // Chỉ lấy vùng remaining, tăng position.
String text = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);
~~~

Đây là cách đúng **nếu** remaining đã tương ứng với một chuỗi UTF-8 hoàn chỉnh theo protocol. Nó không tự sửa được việc bị chia giữa nhiều lần nhận network.

## 10. Những hiểu lầm dễ gây lỗi

| Hiểu lầm | Thực tế | Cách sửa |
|---|---|---|
| `remaining() == capacity - position()` mọi lúc | Chỉ đúng khi limit == capacity | Dùng trực tiếp `remaining()` |
| `capacity()` là số byte đã nhận từ network | Capacity chỉ là dung lượng vùng nhớ | Dùng giá trị `channel.read` và đúng trình tự `flip` |
| `flip()` xóa vùng đệm | Flip chỉ đặt limit=old position, position=0 | Dùng khi chuyển từ điền sang tiêu thụ |
| `clear()` xóa sạch byte vì tên gọi là clear | Clear **không erase nội dung** | Không dùng clear để tẩy dữ liệu nhạy cảm |
| `rewind()` giống `clear()` | Rewind giữ limit, clear đặt limit=capacity | Chọn thao tác phù hợp |
| `compact()` loại bỏ mọi byte đã đọc xong và reset position=0 | Compact chuyển **byte chưa tiêu thụ** về đầu; position=old remaining | Đọc/ghi tiếp sau compact, rồi flip đúng lúc |
| `get(index)` tăng position | Truy cập tuyệt đối giữ nguyên position | Phân biệt relative/absolute |
| `wrap(array, off, len)` tạo buffer capacity=len | Capacity vẫn bằng `array.length` | Dùng `slice` nếu cần view con pos0 cap=len |
| `slice()` tạo bản copy độc lập | Slice chia sẻ byte với parent | Copy dữ liệu nếu cần cô lập |
| `hasRemaining()` cho biết socket đã có byte sẵn để nhận | Chỉ cho biết cửa sổ buffer còn phần tử | Theo dõi readiness/read result của channel |
| `channel.write(buf)` luôn ghi sạch remaining | Có thể ghi một phần, nhất là non-blocking | Giữ buffer và chờ writable để ghi tiếp |
| ByteBuffer từ `allocateDirect` luôn có `array()` | Direct buffer thường không có backing array truy cập được | Kiểm tra `hasArray()` hoặc dùng `get` để copy |
| Mọi buffer được phép `put` | Read-only buffer ném `ReadOnlyBufferException` | Kiểm tra `isReadOnly()` và thiết kế quyền sở hữu |

### Lỗi vòng lặp đọc hoặc ghi

Sai:

~~~java
// Đoạn minh họa lỗi:
ByteBuffer b = ByteBuffer.allocate(1024);
channel.read(b);
handle(b); // SAI: chưa flip, position đang sau dữ liệu vừa đọc.
~~~

Đúng về mặt quản lý state, nhưng `handle` vẫn phải parse frame cẩn thận:

~~~java
// Đoạn minh họa state; không phải chương trình hoàn chỉnh:
ByteBuffer b = ByteBuffer.allocate(1024);
int n = channel.read(b);
if (n > 0) {
    b.flip();
    handle(b);  // Chỉ tiêu thụ dữ liệu đã có trong position..limit.
    b.compact();
}
~~~

Nếu đã xử lý hết buffer và không cần giữ byte nào, `clear()` cũng có thể hợp lý. Nếu cần giữ một phần đầu hoặc tail của frame, phải dùng `compact()` hoặc cơ chế quản lý buffer tương ứng.

### Không dùng buffer chung giữa nhiều thread tùy tiện

`ByteBuffer` và các view của nó có **position/limit độc lập theo object**, nhưng việc nhiều thread cùng thay đổi dữ liệu hoặc state của **một** ByteBuffer mà không đồng bộ có thể tạo race condition. Một số ứng dụng tạo `duplicate` cho mỗi reader để tách position/limit, song nội dung phía dưới vẫn chia sẻ; cần thiết kế ownership và đồng bộ dữ liệu.

Một buffer được truyền tới tác vụ async phải còn sống và không bị caller `clear/compact`/ghi đè trước khi tác vụ hoàn thành. Nếu không, kể cả nhìn thấy remaining đúng ở một thời điểm, dữ liệu có thể bị thay đổi trước lúc gửi.

## 11. Câu hỏi tự kiểm tra

**1. Buffer có capacity=100, position=20, limit=45. remaining bằng bao nhiêu?** **25 byte**, tính bằng `45 - 20`; không phải 80.

**2. Buffer vừa `allocate(1024)`, remaining=1024. Có chắc 1024 byte input hợp lệ?** **Không.** Đó là 1024 byte **có thể được điền** trước limit.

**3. `put` 7 byte vào buffer capacity=10 rồi `flip`. Ba chỉ số ra sao?** `capacity=10, position=0, limit=7`, remaining=7.

**4. Đọc 3 byte sau `flip` trên; còn bao nhiêu?** `position=3, limit=7, remaining=4`.

**5. Tại trạng thái đó `compact()` sẽ ra sao?** Giữ 4 byte chưa đọc, `position=4, limit=10, remaining=6`; có thể tiếp tục put thêm dữ liệu.

**6. `clear()` có bảo đảm byte cũ bị ghi đè bằng 0 không?** **Không.** Nó chỉ đặt lại position/limit/mark.

**7. `rewind()` sau khi đã đọc 3/7 byte có làm limit về capacity không?** **Không.** Position về 0 và limit vẫn 7.

**8. `get(5)` có làm position tăng đến 6 không?** **Không.** Đây là absolute get; position không đổi nếu thao tác thành công.

**9. `SocketChannel.read` trả 0 có nghĩa `buffer.remaining() == 0` chắc chắn?** **Không.** Với non-blocking I/O, có thể không có dữ liệu sẵn; và nếu buffer không còn chỗ, cũng có thể trả 0. Phải xem mode và state.

**10. Lệnh `ByteBuffer.wrap(array, 2, 4)` với mảng dài 10 sẽ có capacity, position, limit, remaining bao nhiêu?** **10, 2, 6, 4**; không phải 4, 0, 4, 4.

**11. Lệnh `compact()` có bảo đảm dữ liệu chưa đọc sẽ được lưu lại?** Với writable buffer và trạng thái hợp lệ, nó chuyển vùng remaining về đầu, không xóa các byte đó. Nếu buffer **read-only**, nó ném exception.

**12. Có thể gọi `flip()` một lần sau mỗi byte đã `get` để tiếp tục đọc?** Thường **không**. Flip chuyển từ giai đoạn điền sang giai đoạn tiêu thụ; gọi lại sai thời điểm có thể làm limit nhỏ đi và mất cửa sổ dữ liệu mong muốn.

## Tài liệu chính thức

- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `wrap`, `slice`, `compact`, relative/absolute get/put và byte order.
- [Java SE 17 – Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): bất biến mark/position/limit/capacity, `remaining()`, `hasRemaining()`, `flip`, `clear`, `rewind`.
- [Java SE 17 – SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): đọc/ghi một phần với ByteBuffer, blocking và non-blocking.
- [Java SE 17 – CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): giải mã text khi byte UTF-8 có thể đi qua nhiều lần nhận.

**Ghi nhớ:** `capacity` là sức chứa **cố định**; `position` là index cho lần thao tác tương đối tiếp theo; `limit` là cận trên **loại trừ**; `remaining = limit - position`. Trên đường đi `fill → flip → consume → compact/clear → fill tiếp`, chính việc cập nhật bốn đại lượng này giúp xử lý đúng các đợt đọc/ghi TCP NIO không đồng nhất với ranh giới message.

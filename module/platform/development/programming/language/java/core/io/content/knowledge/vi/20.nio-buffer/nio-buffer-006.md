# NIO Buffer: get và put tương đối, tuyệt đối trong Java

Trong `java.nio`, **Buffer** là một vùng dữ liệu có trạng thái đọc/ghi: `capacity`, `limit` và `position`. Hai nhóm thao tác cốt lõi là **tương đối (relative)** và **tuyệt đối (absolute)**:

- `get()` và `put(value)` **tương đối** thao tác tại vị trí `position` hiện tại, sau đó **tăng `position`**.
- `get(index)` và `put(index, value)` **tuyệt đối** thao tác trực tiếp tại `index`, **không thay đổi `position`**.

Đây là sự khác nhau nền tảng để đọc lần lượt, ghi tuần tự, nhìn trước dữ liệu (peek), sửa một phần đã biết vị trí và xây parser nhị phân. “Tuyệt đối” ở đây là **chỉ số bên trong buffer**, không phải địa chỉ RAM, byte offset của file hay vị trí của `FileChannel`.

## 1. Nắm chắc trạng thái Buffer trước khi dùng get/put

Mọi `Buffer` đều có ba thuộc tính cốt lõi:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Tổng số phần tử mà buffer có thể chứa; không đổi trong suốt vòng đời buffer đó. |
| `limit()` | Ranh giới **độc quyền** (exclusive) của vùng đang được phép đọc hoặc ghi. |
| `position()` | Chỉ số phần tử tiếp theo cho thao tác **tương đối**. |

Bất biến:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

Các phần tử hợp lệ cho lệnh truy cập tuyệt đối một phần tử có chỉ số **`0` đến `limit - 1`**, không phải cứ nhỏ hơn `capacity` là được. Nếu `limit = 3` và `capacity = 8` thì `get(3)` vẫn vượt biên; bản thân capacity không cho phép vượt limit.

Ví dụ buffer dung lượng 8, đã ghi ba byte theo cách tương đối:

```text
Index:       0    1    2    3    4    5    6    7
Content:    10   20   30    ?    ?    ?    ?    ?
                             ^
position = 3, limit = 8, capacity = 8
```

Khi gọi `flip()`, trạng thái chuyển thành `position = 0, limit = 3, capacity = 8`. Lúc này có ba phần tử đã được ghi và có thể đọc bằng các thao tác tương đối, trong khi `get(3)` hoặc `put(3, value)` tuyệt đối bị từ chối vì `index >= limit`.

**Vùng byte đã được cấp phát không đồng nghĩa dữ liệu hợp lệ.** `ByteBuffer.allocate` khởi tạo bộ nhớ bằng 0, nhưng chương trình vẫn phải xác định phần nào đã được ghi và quản lý `position/limit` cho đúng.

## 2. get/put tương đối: đọc ghi và dịch con trỏ

Các ví dụ sau dùng `ByteBuffer`, với đơn vị chỉ số là **byte**:

```java
ByteBuffer b = ByteBuffer.allocate(5);    // position=0, limit=5
b.put((byte) 10);                         // ghi index 0; position=1
b.put((byte) 20);                         // ghi index 1; position=2
b.put((byte) 30);                         // ghi index 2; position=3
b.flip();                                 // position=0, limit=3
byte a = b.get();                         // a=10; position=1
byte c = b.get();                         // c=20; position=2
```

Đây là snippet minh họa, cần `import java.nio.ByteBuffer;` và đặt trong một phương thức Java hợp lệ.

Với `get()`, buffer cần tối thiểu một phần tử còn lại (`position < limit`). Với `put(value)`, cũng cần còn chỗ trong vùng ghi của buffer. Nếu không:

- `get()` khi `remaining() == 0` ném **`BufferUnderflowException`**.
- `put(value)` khi `remaining() == 0` ném **`BufferOverflowException`**, trừ các ràng buộc khác như buffer chỉ đọc.
- `ByteBuffer.put` trả lại chính buffer để có thể chain `put(...).put(...)`.
- Với `byte`, kết quả `get()` là kiểu có dấu (`-128..127`). Nếu muốn số 0..255, dùng `b.get() & 0xFF`.

Không cần tự gọi `position(position() + 1)` sau một `get/put` tương đối: API đã tiến position. Tự cộng thêm sẽ bỏ sót phần tử.

## 3. get/put tuyệt đối: truy cập index mà giữ nguyên position

Với một `ByteBuffer b` đang mở và ở trạng thái hợp lệ:

```java
byte first = b.get(0);      // Đọc phần tử số 0, position không đổi.
b.put(1, (byte) 99);       // Ghi đè phần tử số 1, position không đổi.
```

Điểm cần nhớ:

1. Chỉ số là **zero-based**, chỉ số âm hoặc `index >= limit` gây **`IndexOutOfBoundsException`** đối với thao tác một phần tử.
2. `get(index)` không tiêu thụ dữ liệu ở position hiện tại. Ví dụ `position = 2`, gọi `get(0)` vẫn để position = 2.
3. `put(index, value)` không ghi thêm một phần tử vào cuối phần “đã xử lý”; nó **ghi đè** phần tử tại index cho trước. Nếu buffer có khả năng ghi và index hợp lệ, dữ liệu cũ tại đó thay đổi.
4. `get(index)` vẫn có thể đọc dù `position == limit`, miễn index nằm trong vùng `[0, limit)`. Vì thao tác tuyệt đối không cần lấy dữ liệu từ position hiện tại.
5. `put(index, value)` không di chuyển `position`, không thay `limit`, và không cập nhật “số byte đã ghi hợp lệ” để `flip()` tự biết.

Điểm 5 dễ gây lỗi nhất:

```java
ByteBuffer b = ByteBuffer.allocate(4); // position=0, limit=4
b.put(2, (byte) 7);                    // position vẫn 0
b.flip();                              // limit trở thành 0!
System.out.println(b.remaining());    // 0
```

Ví dụ cho thấy **`flip()` sử dụng position cũ làm limit**, không tự quét vùng nhớ để phát hiện mọi vị trí đã được ghi bằng `put(index,...)`. Nếu chủ đích lưu một cấu trúc cố định, hãy quản lý vùng hợp lệ rõ ràng (chẳng hạn ghi tuần tự trước, rồi dùng absolute put để vá header) và chỉ `flip` sau khi position phản ánh lượng dữ liệu đã chuẩn bị.

## 4. Ví dụ Java 17+ chạy độc lập: so sánh trực tiếp

Lưu thành **`RelativeAbsoluteBufferDemo.java`**:

```java
import java.nio.BufferUnderflowException;
import java.nio.ByteBuffer;

public class RelativeAbsoluteBufferDemo {
    private static String state(ByteBuffer b) {
        return "pos=" + b.position()
                + " limit=" + b.limit()
                + " capacity=" + b.capacity();
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(6);
        System.out.println("initial: " + state(b));

        // Relative put: tăng position mỗi lần ghi.
        b.put((byte) 10).put((byte) 20).put((byte) 30);
        System.out.println("relative put: " + state(b));

        // Absolute put: ghi đè index 1; position không đổi.
        b.put(1, (byte) 99);
        System.out.println("absolute put: " + state(b));

        // Chuyển từ ghi sang đọc 3 byte đã chuẩn bị.
        b.flip();
        System.out.println("flip: " + state(b));

        // Absolute get: nhìn trước byte thứ hai mà không tiêu thụ.
        System.out.println("peek get(1): " + b.get(1));
        System.out.println("after peek: " + state(b));

        // Relative get: đọc và tăng position.
        System.out.println("consume get(): " + b.get());
        System.out.println("after consume: " + state(b));
        System.out.println("remaining=" + b.remaining());

        // Quay về đọc lại toàn bộ vùng [0, limit).
        b.rewind();
        System.out.println("rewind: " + state(b));
        System.out.println(
                "values=" + b.get() + "," + b.get() + "," + b.get());

        try {
            b.get(); // position == limit, không còn byte để đọc.
        } catch (BufferUnderflowException e) {
            System.out.println("read past limit: BufferUnderflowException");
        }

        b.clear(); // Chỉ reset trạng thái, không xóa byte trong bộ nhớ.
        System.out.println("clear: " + state(b));
        try {
            b.get(6); // index bằng limit là không hợp lệ.
        } catch (IndexOutOfBoundsException e) {
            System.out.println("get(6): IndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy (Java 17 trở lên):

```bash
javac RelativeAbsoluteBufferDemo.java
java RelativeAbsoluteBufferDemo
```

Stdout:

```text
initial: pos=0 limit=6 capacity=6
relative put: pos=3 limit=6 capacity=6
absolute put: pos=3 limit=6 capacity=6
flip: pos=0 limit=3 capacity=6
peek get(1): 99
after peek: pos=0 limit=3 capacity=6
consume get(): 10
after consume: pos=1 limit=3 capacity=6
remaining=2
rewind: pos=0 limit=3 capacity=6
values=10,99,30
read past limit: BufferUnderflowException
clear: pos=0 limit=6 capacity=6
get(6): IndexOutOfBoundsException
```

Diễn giải:

- Ba `put` tương đối ghi lần lượt vào index 0, 1, 2; `position` tiến tới 3.
- `put(1, 99)` đổi byte 20 thành 99, nhưng `position` vẫn là 3; nhờ vậy `flip` giữ đúng `limit = 3`.
- Sau `flip`, `get(1)` trả về 99 mà `position` vẫn bằng 0; `get()` đọc 10 và tăng lên 1.
- `rewind` giữ limit 3 và đặt lại position 0, cho phép đọc lại `10,99,30`.
- Đọc tương đối qua limit gây underflow; đọc tuyệt đối tại index bằng limit gây `IndexOutOfBoundsException`. Đây là **hai lỗi khác nhau**.
- `clear` đưa trạng thái về `position=0, limit=capacity`; không xóa nội dung mảng nhớ, nên không được xem như cách làm sạch dữ liệu nhạy cảm.

## 5. Bảng so sánh chính xác các thao tác

| Nhóm | API `ByteBuffer` | Vị trí đọc/ghi | Sau khi thành công | Vượt biên điển hình |
| --- | --- | --- | --- | --- |
| Relative get | `get()` | `position` hiện tại | `position += 1` | `BufferUnderflowException` |
| Relative put | `put(byte)` | `position` hiện tại | `position += 1` | `BufferOverflowException` |
| Absolute get | `get(int index)` | `index` chỉ định | `position` không đổi | `IndexOutOfBoundsException` |
| Absolute put | `put(int index, byte)` | `index` chỉ định | `position` không đổi | `IndexOutOfBoundsException` |
| Relative typed get | `getInt()` | 4 byte từ `position` | `position += 4` | `BufferUnderflowException` |
| Absolute typed get | `getInt(index)` | 4 byte từ `index` | `position` không đổi | `IndexOutOfBoundsException` |
| Relative typed put | `putInt(value)` | 4 byte từ `position` | `position += 4` | `BufferOverflowException` |
| Absolute typed put | `putInt(index, value)` | 4 byte từ `index` | `position` không đổi | `IndexOutOfBoundsException` |

`getInt(index)` và `putInt(index, value)` cần **cả bốn byte** nằm trước limit, tức `index >= 0` và `index + 4 <= limit`. Tương tự `getLong/putLong` cần 8 byte. Đối với các lệnh ghi, buffer chỉ đọc còn có thể ném `ReadOnlyBufferException`.

Bảng dùng `ByteBuffer` để minh họa; `IntBuffer`, `LongBuffer`, `CharBuffer`, `ShortBuffer`, `FloatBuffer`, `DoubleBuffer` cũng có get/put tương đối và tuyệt đối theo **đơn vị phần tử riêng**. Ví dụ `IntBuffer.get(2)` nghĩa là phần tử `int` thứ ba, không phải byte offset 2.

## 6. Hiểu limit, flip, clear, rewind và compact

Các hàm này **quản lý trạng thái**, không tự chuyển dữ liệu sang một buffer mới:

| Phương thức | Position sau lệnh | Limit sau lệnh | Mục đích |
| --- | --- | --- | --- |
| `flip()` | 0 | Position **trước** lệnh | Chuyển dữ liệu vừa ghi tuần tự sang chế độ đọc. |
| `clear()` | 0 | Capacity | Chuẩn bị ghi từ đầu; **không** xóa các byte cũ. |
| `rewind()` | 0 | Giữ nguyên limit | Đọc lại vùng hiện tại từ đầu. |
| `compact()` | Số phần tử còn lại trước lệnh | Capacity | Dồn phần chưa đọc về đầu rồi chuẩn bị ghi tiếp. |
| `position(n)` | n | Giữ nguyên limit | Đặt con trỏ tương đối trong khoảng hợp lệ. |
| `limit(n)` | Có thể bị hạ xuống n | n | Đổi vùng hợp lệ; position không được lớn hơn limit. |

Ví dụ vòng xử lý khi dữ liệu đến từng đợt:

```text
GHI:
position = số byte đã được đặt vào buffer, limit = capacity
      |
      | flip()
      v
ĐỌC:
position = số byte đã tiêu thụ, limit = số byte có dữ liệu
      |
      | compact() nếu vẫn còn byte chưa đủ tạo một thông điệp
      v
GHI TIẾP:
các byte chưa đọc nằm đầu buffer
position = số byte giữ lại, limit = capacity
```

Một workflow thông thường: `channel.read(buffer)` ghi vào vị trí hiện tại → `buffer.flip()` → xử lý bằng `buffer.get()` → `buffer.compact()` để giữ phần còn dang dở; hoặc `clear()` khi chắc chắn đã tiêu thụ hết. Khi kết thúc luồng, `flip()` và xử lý phần còn lại theo quy tắc giao thức. Nếu data gồm số nguyên 4 byte hoặc chuỗi UTF-8 nhiều byte, không được mặc định mỗi đợt đọc cung cấp đủ một đơn vị; parser cần giữ phần chưa đủ.

**Lưu ý:** `compact()` có thể sao chép bytes giữa các vị trí; mọi absolute index đã lưu từ trước có thể không còn trỏ đúng thông điệp. Tính lại vị trí và giữ lập luận về state.

## 7. Absolute get thường dùng để peek header và sửa byte tại offset

Một parser nhị phân có thể muốn nhìn trước header mà chưa tiêu thụ con trỏ:

```java
// Snippet: giả sử b là ByteBuffer đã flip và còn >= 4 byte.
if (b.remaining() >= Integer.BYTES) {
    int magic = b.getInt(b.position()); // peek: position không đổi
    if (magic == 0x01020304) {
        int consumed = b.getInt();     // relative: tiến thêm 4 byte
        // consumed == magic
    }
}
```

`ByteBuffer` mặc định dùng `ByteOrder.BIG_ENDIAN`. Nếu protocol yêu cầu little-endian, thiết lập `b.order(ByteOrder.LITTLE_ENDIAN)` và phải thống nhất giữa bên ghi và bên đọc. Cả `getInt()` và `getInt(index)` dùng byte order của buffer đó; tính chất relative/absolute **không** quyết định byte order.

Một kỹ thuật thường gặp là để trống header độ dài, ghi payload, rồi quay lại điền header bằng absolute put. Cách này giúp giữ position tại cuối payload:

```java
import java.nio.ByteBuffer;

ByteBuffer b = ByteBuffer.allocate(64);
b.putInt(0);                 // Reserve 4 bytes for length; position=4.
int start = b.position();   // start=4
b.put(new byte[] {7, 8, 9});
int length = b.position() - start; // 3
b.putInt(0, length);        // Patch header; position vẫn = 7.
b.flip();                   // limit=7; sẵn sàng đọc.
int payloadLength = b.getInt(); // 3; position=4.
```

Đây là **snippet** dùng import và các biến trong ngữ cảnh; nó cho thấy cách dùng relative put để xác định phần dữ liệu hợp lệ, sau đó dùng absolute put để ghi đè header. Tuy nhiên, nó không tự tạo framing protocol hoàn chỉnh: bên nhận còn phải kiểm tra `length >= 0`, hạn mức, số byte thực có sẵn trước khi đọc payload.

Chỉ số tuyệt đối thuộc buffer **đang được dùng**. Nếu buffer là slice bắt đầu giữa một buffer khác, `index=0` của slice tương ứng với phần tử đầu slice, chứ không nhất thiết là phần tử số 0 của buffer gốc.

## 8. Bulk get/put: thao tác một nhóm phần tử

Với Java 17+, `ByteBuffer` hỗ trợ cả phương thức bulk tương đối và bulk tuyệt đối:

```java
ByteBuffer b = ByteBuffer.allocate(5);
b.put(new byte[] {11, 22, 33});   // relative: position=3
b.flip();                         // position=0, limit=3

byte[] firstTwo = new byte[2];
b.get(firstTwo);                  // relative: position=2

byte[] peek = new byte[2];
b.get(0, peek);                   // absolute bulk: position vẫn 2
```

`get(byte[])` đọc số phần tử tương ứng độ dài array từ position và tăng position; nếu `remaining()` không đủ sẽ ném underflow. `get(int index, byte[] dst)` đọc từ index cố định, không thay đổi position. Biến thể có offset/length như `get(index, dst, offset, length)` cho phép chọn một lát của array. Các hàm bulk absolute của `ByteBuffer` được hỗ trợ trong Java 17; khi xây thư viện cần tương thích JDK cũ hơn, kiểm tra API version.

Tương tự, `put(byte[])` là ghi bulk tương đối, còn `put(index, src)` là ghi bulk tuyệt đối. Không nhầm **offset trong array nguồn/đích** với **index trong buffer**: đó là hai hệ tọa độ khác nhau.

Nếu cần xử lý byte array rất lớn, tránh đọc tất cả vào RAM; làm việc theo khối, phối hợp `remaining()` và kiểm tra giới hạn định dạng.

## 9. Read-only, duplicate, slice và các vùng nhớ dùng chung

`duplicate()` tạo một buffer có **trạng thái position/limit/mark độc lập** nhưng cùng vùng chứa dữ liệu. `slice()` tạo view bắt đầu tại position hiện tại với capacity bằng `remaining()` tại thời điểm tạo; nó cũng chia sẻ dữ liệu nhưng các chỉ số trong slice tính từ 0.

```java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1); // original: position=1, limit=4

ByteBuffer duplicate = original.duplicate();
ByteBuffer slice = original.slice(); // slice index 0 -> original index 1

slice.put(0, (byte) 99); // Ghi đè original index 1, không đổi position.
System.out.println(original.get(1));  // 99
System.out.println(duplicate.position()); // 1
System.out.println(slice.position());     // 0
```

Đây là snippet; cần `import java.nio.ByteBuffer;`. Sửa nội dung qua slice hay duplicate có thể thấy từ các view khác, nhưng cursor được quản lý độc lập. Điều này đặc biệt quan trọng khi dùng absolute index: index gắn với **view**, không phải vị trí trong file hay tọa độ toàn cục.

`asReadOnlyBuffer()` trả về view chỉ đọc có thể `get` nhưng không thể `put`, dù lệnh ghi là relative hay absolute. Nội dung của read-only view vẫn có thể đổi nếu buffer gốc có quyền ghi chia sẻ cùng vùng nhớ; đây không phải ảnh chụp bất biến.

Không dùng `duplicate` như giải pháp an toàn cho luồng đồng thời: vị trí riêng không làm cho dữ liệu chia sẻ có transaction hoặc synchronization. Đặt chính sách đồng bộ và sở hữu bộ nhớ khi có nhiều thread.

## 10. Những lỗi phổ biến phải phân biệt

| Tình huống | Hành vi / exception | Cách xử lý |
| --- | --- | --- |
| `get()` sau khi `position == limit` | `BufferUnderflowException` | Dùng `hasRemaining()`, `remaining()` hoặc kiểm tra đủ độ dài trước khi đọc. |
| `put(value)` khi hết chỗ | `BufferOverflowException` | Đảm bảo buffer ở pha ghi với dung lượng đủ, xử lý/flush phần cũ. |
| `get(index)` với `index < 0` hoặc `index >= limit` | `IndexOutOfBoundsException` | Kiểm tra theo limit, không chỉ capacity. |
| `put(index, value)` ngoài limit | `IndexOutOfBoundsException` | Không dùng index ngoài vùng hợp lệ, điều chỉnh state có chủ đích. |
| `put` trên read-only buffer | `ReadOnlyBufferException` | Dùng buffer ghi được; không sửa view chỉ đọc. |
| `getInt()` khi chỉ còn 2 byte | `BufferUnderflowException` | Cần `remaining() >= 4` trước khi đọc. |
| `getInt(index)` không đủ 4 byte tới limit | `IndexOutOfBoundsException` | Kiểm tra cả span `[index, index+4)`. |
| `put(index, ...)` rồi `flip()` thấy limit 0 | Position không đổi sau ghi tuyệt đối. | Xác định vùng đã chuẩn bị bằng ghi relative hoặc chủ động thiết lập position trước flip. |
| `clear()` rồi đọc thấy byte cũ | `clear` reset metadata, không xóa nội dung. | Không dùng `clear` như phép wipe hoặc chứng nhận dữ liệu mới. |
| `slice().get(0)` khác `original.get(0)` | Slice có tọa độ index từ đầu view. | Tính lại index theo offset slice. |
| Đọc ra số sai thứ tự byte | Byte order không thống nhất. | Dùng `order(...)` theo schema, kiểm tra dữ liệu mẫu. |

Một lỗi tư duy tinh vi: **position không phải địa chỉ lưu trữ duy nhất của dữ liệu**. Buffer có thể chứa nhiều byte phía trước hoặc sau position, nhưng `limit` mới xác định vùng thao tác hợp lệ; ứng dụng vẫn phải theo dõi byte nào thật sự đại diện cho một trường dữ liệu đã hoàn chỉnh.

## 11. Khi nào dùng tương đối và khi nào dùng tuyệt đối?

**Relative get/put** phù hợp khi:

- Đọc từng phần tử theo thứ tự một stream đã có `flip`.
- Ghi tuần tự bản tin, tệp nhị phân hoặc các khối dữ liệu.
- Tiêu thụ byte trong vòng `while (b.hasRemaining())`.
- Muốn ứng dụng dựa trên `position` để biết đã xử lý đến đâu.

**Absolute get/put** phù hợp khi:

- Peek một header, magic number, length, checksum hoặc tag trước khi quyết định tiêu thụ.
- Cập nhật một trường tại index xác định sau khi đã ghi payload.
- Đọc lại một phần tử cũ mà không làm thay đổi vòng xử lý tương đối.
- Thao tác theo bảng offset của một cấu trúc nhị phân đã được xác thực.

Không nên sử dụng absolute put để thay cho toàn bộ vòng ghi tuần tự nếu vẫn định dùng `flip()` mà không quản lý `position`. Cũng đừng cố thực hiện mọi phép đọc bằng cách tự tăng index khi vòng duyệt tương đối đã diễn đạt đúng ý định.

## 12. Bài tập tự luyện và kiểm chứng

**Bài tập 1 — Đọc trạng thái chính xác.** Khởi tạo `ByteBuffer.allocate(4)`, gọi lần lượt `put((byte)5)`, `put(0,(byte)9)`, `flip()`, `get(0)`, `get()`. Hãy ghi position/limit sau mỗi lệnh. Đáp án: `(1,4)` → `(1,4)` → `(0,1)` → `(0,1)` → `(1,1)`; hai `get` cuối đều trả 9.

**Bài tập 2 — Header length.** Mở rộng snippet vá header: ghi 4-byte length, payload 5 byte, dùng absolute `getInt(0)` để kiểm tra length **mà không đổi position**, rồi đọc bằng `getInt()`. Tại sao hai thao tác trả cùng giá trị nhưng state sau lệnh khác nhau?

**Bài tập 3 — Chẩn đoán ngoại lệ.** Với `ByteBuffer.allocate(4)` đã ghi 2 byte rồi `flip()`, thử `get(2)` và thử gọi `get()` ba lần. Dự đoán chính xác `IndexOutOfBoundsException` so với `BufferUnderflowException`.

**Bài tập 4 — Slice và con trỏ riêng.** Dùng `wrap(new byte[]{1,2,3,4})`, đặt `position(2)`, tạo slice, gọi `slice.put(0,(byte)8)`. Quan sát `original.get(2)` và position của original/slice. Giải thích vì sao hai vị trí độc lập nhưng nội dung đổi chung.

**Bài tập 5 — Byte order.** Tạo `ByteBuffer.allocate(4)`, ghi `putInt(0x01020304)`, `flip()` và đọc lại bằng `getInt()`. Thử đọc từng byte bằng absolute `get(index)`; sau đó áp dụng `order(ByteOrder.LITTLE_ENDIAN)` **trước khi ghi** một buffer mới và so sánh thứ tự byte.

### Tự đánh giá nhanh

- Relative `get` và absolute `get(index)` có cùng cập nhật position không?
- Tại sao absolute index bị ràng buộc bởi limit chứ không chỉ capacity?
- Tại sao `putInt(index, value)` không tự làm cho `flip()` biết đã có dữ liệu?
- Khi đọc một khung gồm 4-byte header, cần bao nhiêu `remaining()` trước `getInt()`?
- Sau `compact()`, các absolute index đã ghi nhớ còn áp dụng nguyên vẹn không?

**Ghi nhớ:** Relative get/put sử dụng rồi dịch `position`, absolute get/put truy cập theo `index` mà giữ nguyên cursor. Cả hai đều tuân thủ `limit` và quyền đọc/ghi của buffer; hãy tổ chức rõ pha ghi → `flip` → đọc → `compact/clear` theo nhu cầu, nhất là khi xử lý dữ liệu nhị phân nhiều đợt.

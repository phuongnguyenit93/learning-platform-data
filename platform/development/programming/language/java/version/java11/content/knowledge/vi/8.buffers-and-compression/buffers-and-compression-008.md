# Byte order, direct buffer và heap buffer trong Java 11

**Chủ đề cha:** Buffer và nén  
**Phạm vi:** Biểu diễn dữ liệu nhị phân nhiều byte, thứ tự byte (endianness), `ByteBuffer` nằm trên heap hoặc direct, trạng thái `position/limit/capacity`, chia sẻ bộ nhớ và lựa chọn buffer phù hợp cho I/O.

`java.nio.ByteBuffer` là kiểu dữ liệu trung tâm khi xử lý byte trong Java NIO. Nó vẫn được sử dụng rộng rãi khi giao tiếp với `FileChannel`/`SocketChannel`, đọc cấu trúc file nhị phân, mã hóa/giải mã khung dữ liệu và làm việc với thư viện native. Các kiến thức trong bài đều có trên Java 11 và còn áp dụng trên những bản Java hiện đại. **Đây không phải tính năng mới ra mắt riêng ở Java 11**: phần lớn API `ByteBuffer` có từ các phiên bản trước, nhưng vẫn là nền tảng cần biết khi phát triển trên Java 11+.

Điều quan trọng cần phân biệt là **byte order mô tả cách sắp xếp byte của một giá trị nhiều byte**, còn **heap/direct mô tả cách cấp phát và truy cập vùng nhớ**. Chúng là hai thuộc tính độc lập: buffer direct có thể là big-endian hoặc little-endian; heap buffer cũng vậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `BIG_ENDIAN`, `LITTLE_ENDIAN` và vì sao đọc cùng bốn byte theo thứ tự khác nhau sẽ tạo ra số `int` khác nhau.
2. Dùng `ByteBuffer.order(ByteOrder)` với `getShort/putShort`, `getInt/putInt`, `getLong/putLong` và các kiểu dữ liệu nhiều byte khác.
3. Phân biệt `ByteBuffer.allocate`, `allocateDirect` và `wrap`; kiểm tra `isDirect()`, `hasArray()` và giới hạn của `array()`.
4. Dùng `position`, `limit`, `capacity`, `flip`, `clear`, `compact` để ghi/đọc đúng số byte, tránh overflow/underflow.
5. Hiểu `duplicate`, `slice`, `asReadOnlyBuffer` và typed view (ví dụ `asIntBuffer`) **chia sẻ dữ liệu**, nhưng có trạng thái vị trí riêng; tránh lỗi mất byte order trong view mới.
6. Lựa chọn direct buffer dựa trên mô hình I/O, chi phí bộ nhớ và phép đo, thay vì mặc định nó luôn nhanh hơn heap buffer.
7. Viết test byte-by-byte cho định dạng nhị phân để chạy nhất quán trên nhiều hệ điều hành và kiến trúc CPU.

## 2. Byte order: cùng một số, thứ tự byte khác nhau

Một `int` của Java có 32 bit, tương đương **4 byte**. Với giá trị hexadecimal `0x12345678`, thứ tự các byte trong vùng lưu trữ phụ thuộc endianness:

| Thứ tự byte | Byte tại offset 0 | Offset 1 | Offset 2 | Offset 3 |
|---|---|---|---|---|
| `ByteOrder.BIG_ENDIAN` | `12` | `34` | `56` | `78` |
| `ByteOrder.LITTLE_ENDIAN` | `78` | `56` | `34` | `12` |

Các giá trị trong bảng được viết theo **hexadecimal**, mỗi ô chứa một byte. Trong big-endian, byte quan trọng nhất đứng trước; trong little-endian, byte ít quan trọng nhất đứng trước.

Ví dụ dạng byte:

```text
Giá trị logic: 0x12345678 (32 bit)

BIG_ENDIAN:
offset    0    1    2    3
byte     12   34   56   78

LITTLE_ENDIAN:
offset    0    1    2    3
byte     78   56   34   12
```

**Lưu ý:** endian không thay đổi giá trị toán học của một số. Nó chỉ quyết định cách **mã hóa số thành byte và diễn giải byte thành số**. Nếu cùng một buffer được ghi theo little-endian nhưng lại đọc theo big-endian, giá trị có thể bị đảo byte ngoài ý muốn.

### 2.1 Giá trị mặc định của Java ByteBuffer

`ByteBuffer.allocate(...)`, `ByteBuffer.allocateDirect(...)` và `ByteBuffer.wrap(...)` đều khởi tạo **byte order mặc định là `BIG_ENDIAN`**. Đây là hợp đồng của `ByteBuffer` và **không phụ thuộc** thứ tự byte native của CPU.

Có thể thay đổi trực tiếp bằng:

```java
ByteBuffer buffer = ByteBuffer.allocate(8)
        .order(ByteOrder.LITTLE_ENDIAN);
```

Đây là **trích đoạn** cần import `java.nio.ByteBuffer` và `java.nio.ByteOrder`. Lệnh `order(...)` đặt cách diễn giải các phép toán **nhiều byte** trên chính buffer này. Thứ tự byte không làm thay đổi hành vi của `put(byte)` hay `get()` từng byte.

`ByteOrder.nativeOrder()` trả thứ tự byte native của phần cứng mà JVM đang chạy. Nó có ích trong một số tối ưu hóa native/direct I/O nhưng **không phải tiêu chuẩn tự động cho dữ liệu file hoặc giao thức**. Định dạng file, wire protocol và tài liệu API mới là nguồn xác định cần BIG_ENDIAN hay LITTLE_ENDIAN.

### 2.2 Ví dụ 1 — ghi và đọc một số int ở hai kiểu endian

Lưu chương trình hoàn chỉnh sau thành **`EndiannessDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class EndiannessDemo {
    static String bytes(ByteBuffer buffer) {
        StringBuilder hex = new StringBuilder();
        for (int i = 0; i < buffer.limit(); i++) {
            if (i > 0) hex.append(" ");
            hex.append(String.format("%02X",
                    Byte.toUnsignedInt(buffer.get(i))));
        }
        return hex.toString();
    }

    public static void main(String[] args) {
        ByteBuffer big = ByteBuffer.allocate(4);
        ByteBuffer little = ByteBuffer.allocate(4)
                .order(ByteOrder.LITTLE_ENDIAN);

        big.putInt(0x12345678).flip();
        little.putInt(0x12345678).flip();

        System.out.println("default-order=" + big.order());
        System.out.println("big-bytes=" + bytes(big));
        System.out.println("little-bytes=" + bytes(little));
        System.out.printf("big-value=%08X%n", big.getInt(0));
        System.out.printf("little-value=%08X%n", little.getInt(0));

        ByteBuffer duplicate = little.duplicate();
        System.out.println("duplicate-order=" + duplicate.order());
        System.out.printf("little-read-as-big=%08X%n",
                duplicate.getInt(0));
    }
}
```

Chạy trên JDK 11 hoặc JDK mới có hỗ trợ `--release 11`:

```bash
javac --release 11 -encoding UTF-8 EndiannessDemo.java
java EndiannessDemo
```

Kết quả đã kiểm tra:

```text
default-order=BIG_ENDIAN
big-bytes=12 34 56 78
little-bytes=78 56 34 12
big-value=12345678
little-value=12345678
duplicate-order=BIG_ENDIAN
little-read-as-big=78563412
```

Giải thích:

- `big` và `little` chứa **cùng giá trị int logic** được mã hóa khác nhau.
- `getInt(0)` đọc **tại offset byte 0** mà không đổi `position`; vì mỗi buffer đọc theo đúng order của chính nó nên đều cho `0x12345678`.
- `little.duplicate()` trên Java 11 chia sẻ cùng dữ liệu nhưng buffer mới có order **`BIG_ENDIAN`**. Nếu đọc mà không đặt lại `LITTLE_ENDIAN`, bốn byte `78 56 34 12` bị diễn giải thành `0x78563412`.
- `Byte.toUnsignedInt(...)` biến byte Java có dấu (từ `-128` đến `127`) thành số 0..255 để in hex chính xác. Không dùng giá trị âm của `byte` làm kết luận rằng byte nhị phân bị sai.

Bài học từ ví dụ: **phía ghi và phía đọc phải thống nhất endian**, và không được giả định một buffer view mới luôn kế thừa byte order bạn đã cấu hình trước đó.

## 3. Byte order chỉ áp dụng khi diễn giải giá trị nhiều byte

`ByteBuffer` có các nhóm API:

| Nhóm API | Ví dụ | Byte order có ảnh hưởng? |
|---|---|---|
| Đọc/ghi một byte | `get()`, `get(index)`, `put(byte)` | Không |
| Đọc/ghi nhiều byte kiểu nguyên | `getShort/putShort`, `getInt/putInt`, `getLong/putLong` | Có |
| Đọc/ghi số thực | `getFloat/putFloat`, `getDouble/putDouble` | Có, với bit biểu diễn số thực |
| Đọc/ghi ký tự Java `char` | `getChar/putChar` | Có, `char` gồm 2 byte |
| Đọc/ghi một đoạn byte thô | `get(byte[])`, `put(byte[])` | Không hoán đổi byte trong mảng |
| Typed view | `asIntBuffer()`, `asLongBuffer()`... | View sử dụng byte order được chốt lúc tạo |

**Index của `getInt(int index)` là vị trí tính theo byte**, không phải “phần tử int thứ index”. Do đó `getInt(4)` đọc bốn byte bắt đầu ở offset byte 4. Với `IntBuffer` tạo bởi `asIntBuffer()`, chỉ số phần tử mới được tính theo các số `int` 4 byte.

Ví dụ đọc một header nhị phân có hai trường:

```java
ByteBuffer header = ByteBuffer.wrap(rawHeader)
        .order(ByteOrder.BIG_ENDIAN);
int signature = Short.toUnsignedInt(header.getShort());
int version = Byte.toUnsignedInt(header.get());
```

Đây là **trích đoạn**, cần import `ByteBuffer` và `ByteOrder` và phải có `rawHeader` là `byte[]` đủ ít nhất 3 byte. `getShort()` tiêu thụ hai byte, `get()` thêm một byte. `Short.toUnsignedInt` cho phép diễn giải trường 16 bit không dấu theo giao thức; Java `short` tự thân là kiểu có dấu. Nếu header được quy định little-endian thì đổi `order(ByteOrder.LITTLE_ENDIAN)` trước khi đọc.

**Không có endianness chung cho “tất cả dữ liệu UTF-8”**: UTF-8 biểu diễn văn bản bằng các byte theo quy tắc mã hóa; không được tự ý đảo byte trong chuỗi UTF-8 như khi đổi thứ tự byte của một `int`. Khi xử lý dữ liệu đã nén (`gzip`, `deflate`...), byte order của các trường metadata phải theo **đặc tả định dạng nén**, còn luồng byte nén không được đổi thứ tự tùy ý. Chủ đề endian trong bài chủ yếu nói về **các trường số nhị phân nhiều byte**.

## 4. Heap buffer và direct buffer khác nhau ở đâu?

`ByteBuffer` có hai dạng lớn: **non-direct** (thường dùng dạng heap) và **direct**.

| Thuộc tính | `ByteBuffer.allocate(n)` — heap | `ByteBuffer.allocateDirect(n)` — direct |
|---|---|---|
| `isDirect()` | `false` | `true` |
| Cấp phát | Có backing `byte[]` trên Java heap | Vùng lưu trữ có thể ở ngoài heap GC thông thường |
| `hasArray()` với buffer gốc đang ghi được | `true` | **Không được giả định**; phải hỏi `hasArray()` |
| `array()` | Có thể lấy backing array khi `hasArray() == true` | Không được gọi khi chưa kiểm tra `hasArray()` |
| Chi phí cấp phát/thu hồi | Thường thấp hơn cho buffer nhỏ, ngắn hạn | Thường cao hơn; quản lý bộ nhớ phức tạp hơn |
| Native I/O | Có thể phải copy qua buffer trung gian | JVM cố gắng tránh một số lần copy trung gian |
| Byte order mặc định | `BIG_ENDIAN` | `BIG_ENDIAN` |
| Tác vụ phù hợp | Xử lý trong bộ nhớ, buffer nhỏ, thao tác trên mảng | I/O native đủ lớn, buffer sống tương đối lâu, có lợi ích đo được |

**Kết luận kỹ thuật:** Direct không đồng nghĩa với “luôn off-heap theo một cơ chế máy ảo cố định” hoặc “luôn zero-copy”. Tài liệu Java chỉ đảm bảo JVM **cố gắng** tận dụng direct buffer cho các thao tác I/O native; chi phí cấp phát, khả năng dùng trực tiếp và mức lợi hiệu năng tùy JDK, OS, loại channel và workload.

### 4.1 Tạo buffer

```java
ByteBuffer heap = ByteBuffer.allocate(8192);
ByteBuffer direct = ByteBuffer.allocateDirect(8192);
ByteBuffer wrapped = ByteBuffer.wrap(new byte[]{1, 2, 3});
```

Đây là **trích đoạn** cần import `java.nio.ByteBuffer`. `allocate` và `allocateDirect` trả buffer mới có `position = 0`, `limit = capacity`, byte ban đầu được khởi tạo bằng 0 và `order = BIG_ENDIAN`. `wrap(byte[])` tạo buffer **dùng chung** với mảng truyền vào; thay nội dung buffer sẽ thay mảng và ngược lại.

Buffer direct **không phải** một kiểu `byte[]` thông thường để truy cập trực tiếp bằng `array()`. Tài liệu Java không bảo đảm `allocateDirect` luôn có backing array truy cập được, nên code tổng quát phải dùng:

```java
if (buffer.hasArray()) {
    byte[] backing = buffer.array();
    int firstRemainingByte = buffer.arrayOffset()
            + buffer.position();
    // Chỉ sử dụng đúng vùng remaining() và kiểm soát việc sửa mảng.
} else {
    // Đọc bằng get(...) hoặc truyền ByteBuffer trực tiếp cho NIO API.
}
```

Đây là **trích đoạn**, `buffer` phải là `ByteBuffer` hợp lệ. `array()` trả toàn bộ backing array, **không tự cắt** theo `position/limit`; phần dữ liệu còn lại bắt đầu tại `arrayOffset() + position()`, dài `remaining()`. Với buffer read-only, `hasArray()` có thể trả `false` dù bản gốc được cấp phát trên heap. Vì vậy `hasArray()` và `isDirect()` là **hai câu hỏi khác nhau**.

### 4.2 Khi nào chọn direct buffer?

Direct buffer thường đáng cân nhắc khi đồng thời có các điều kiện: I/O liên tục qua NIO channel, buffer có kích thước đáng kể và/hoặc được tái sử dụng, đã đo thấy chi phí copy là một nút thắt, và ứng dụng kiểm soát được ngân sách bộ nhớ.

Heap buffer thường phù hợp với dữ liệu nhỏ, ngắn hạn, code có thao tác `byte[]`, bài toán chỉ xử lý trong JVM, hoặc khi benchmark không cho thấy direct mang lại lợi ích.

Direct buffer có thể tăng dấu chân bộ nhớ tiến trình mà metric **heap used** không phản ánh đầy đủ. Không tạo vô hạn direct buffer cho mỗi request rồi kỳ vọng bộ thu gom rác sẽ ngay lập tức trả bộ nhớ; cân nhắc tái sử dụng có giới hạn, giới hạn số lượng/kích thước, quan sát native/direct memory metrics và kiểm tra hành vi trên JDK triển khai. Tránh can thiệp vào cơ chế dọn bộ nhớ nội bộ không được Java API chuẩn bảo đảm.

**Đừng đổi sang direct chỉ vì nghe nói “nhanh hơn”**. Một benchmark tin cậy phải so sánh cùng khối lượng dữ liệu, cách tái sử dụng buffer, loại channel, warm-up JVM, kết quả end-to-end và bộ nhớ tiến trình, không chỉ thời gian của một lệnh `allocateDirect()`.

## 5. Trạng thái buffer: capacity, position, limit và remaining

`ByteBuffer` là một **vùng nhớ cộng với con trỏ trạng thái**. Ba thuộc tính:

- `capacity()`: tổng số byte mà buffer có thể chứa; cố định trong suốt vòng đời của buffer đó.
- `position()`: vị trí thao tác `get()/put()` tương đối tiếp theo.
- `limit()`: biên **không bao gồm** khi đọc hoặc ghi tương đối. Vị trí hợp lệ tuân theo `0 <= position <= limit <= capacity`.
- `remaining()`: bằng `limit - position`; `hasRemaining()` cho biết còn byte trong vùng đang hoạt động.

Các phương thức thay đổi trạng thái rất quan trọng:

| Phương thức | Tác dụng | Khi dùng |
|---|---|---|
| `put(...)` tương đối | Ghi từ `position`, rồi tăng `position` | Đang tạo dữ liệu |
| `get(...)` tương đối | Đọc từ `position`, rồi tăng `position` | Đang tiêu thụ dữ liệu |
| `put(index, ...)` / `get(index)` | Truy cập offset tuyệt đối, **không** đổi `position` | Header ở offset cố định |
| `flip()` | `limit = position`, `position = 0`, hủy mark | Chuyển từ ghi sang đọc số byte vừa ghi |
| `clear()` | `position = 0`, `limit = capacity`, hủy mark | Chuẩn bị ghi lại toàn bộ vùng |
| `rewind()` | `position = 0`, giữ `limit` | Muốn đọc lại vùng đã giới hạn |
| `compact()` | Dồn byte **chưa đọc** về đầu buffer, `position = số byte còn lại`, `limit = capacity` | Tiếp tục ghi thêm khi còn dữ liệu chưa tiêu thụ |
| `mark()` / `reset()` | Lưu và khôi phục vị trí khi cần | Parser cần quay lại trong phạm vi buffer |

**Quan trọng:** `clear()` **không xóa byte** trong vùng lưu trữ. `flip()` cũng không sao chép dữ liệu. Chúng chỉ thay đổi trạng thái để phương thức tiếp theo biết phần nào có thể đọc/ghi. Nếu bạn đọc quá `limit`, có thể gặp `BufferUnderflowException`; ghi quá giới hạn gặp `BufferOverflowException`. Không dùng `capacity()` làm số byte dữ liệu hợp lệ sau khi đã ghi ít hơn capacity.

### Chu trình thường gặp khi gửi dữ liệu qua channel

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(8192);
buffer.put(payload);      // payload là byte[] vừa đủ chỗ
buffer.flip();            // sẵn sàng đọc các byte đã ghi
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
buffer.clear();           // sẵn sàng tái dùng để ghi lần sau
```

Đây là **trích đoạn** trong phương thức, cần `payload` là `byte[]` có độ dài không vượt capacity, `channel` là một channel mở có hàm `write(ByteBuffer)` và xử lý `IOException` phù hợp. Khi ghi qua channel, một lần `write` **có thể tiêu thụ ít hơn** `remaining()`; phải lặp cho đến khi hết hoặc xử lý cơ chế non-blocking nếu channel có thể trả 0. Với `SocketChannel` non-blocking, không được busy-spin khi `write` trả 0; sử dụng cơ chế readiness/selector hoặc scheduling phù hợp.

## 6. Ví dụ 2 — heap/direct, flip và compact

Lưu chương trình sau thành **`BufferLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;

public class BufferLifecycleDemo {
    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(8);
        ByteBuffer direct = ByteBuffer.allocateDirect(8);

        System.out.println("heap-isDirect=" + heap.isDirect());
        System.out.println("heap-hasArray=" + heap.hasArray());
        System.out.println("direct-isDirect=" + direct.isDirect());
        System.out.println("direct-slice-isDirect="
                + direct.slice().isDirect());

        heap.put(new byte[]{10, 20, 30, 40});
        System.out.println("write-position=" + heap.position());
        heap.flip();
        System.out.println("read-limit=" + heap.limit());
        System.out.println("first=" + Byte.toUnsignedInt(heap.get()));
        System.out.println("second=" + Byte.toUnsignedInt(heap.get()));

        heap.compact();
        System.out.println("compact-position=" + heap.position());
        heap.put((byte) 50);
        heap.flip();

        System.out.println("remaining="
                + Byte.toUnsignedInt(heap.get()) + ","
                + Byte.toUnsignedInt(heap.get()) + ","
                + Byte.toUnsignedInt(heap.get()));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 BufferLifecycleDemo.java
java BufferLifecycleDemo
```

Kết quả chính xác:

```text
heap-isDirect=false
heap-hasArray=true
direct-isDirect=true
direct-slice-isDirect=true
write-position=4
read-limit=4
first=10
second=20
compact-position=2
remaining=30,40,50
```

Diễn giải trạng thái:

1. `heap.put` ghi bốn byte `10,20,30,40` nên `position = 4`; `capacity = 8`.
2. `flip()` đặt `limit = 4`, `position = 0`, cho phép đọc đúng bốn byte vừa ghi.
3. Hai lần `get()` tiêu thụ 10 và 20; `position = 2`, còn hai byte `30,40` chưa đọc.
4. `compact()` dồn `30,40` về đầu vùng nhớ; `position = 2` và `limit = 8`, thuận tiện ghi thêm.
5. `put((byte)50)` nối thêm byte 50; `flip()` giúp đọc liên tục `30,40,50`.

**Giới hạn minh họa:** `direct-slice-isDirect=true` là thuộc tính được API bảo đảm: `slice()` của direct buffer cũng direct. Ví dụ không in `direct.hasArray()` vì tài liệu không yêu cầu câu trả lời đồng nhất trên mọi triển khai; nếu cần backing array, kiểm tra `hasArray()` ở runtime.

## 7. slice, duplicate, read-only và typed view: chia sẻ dữ liệu có kiểm soát

Khi tạo buffer view, câu hỏi thiết yếu là: **nội dung được sao chép hay chia sẻ, còn con trỏ trạng thái có độc lập không?**

| API | Bộ nhớ dữ liệu | Position/limit/mark | Byte order của view mới trên Java 11 |
|---|---|---|---|
| `duplicate()` | Chia sẻ toàn bộ nội dung với parent | Giá trị ban đầu tương ứng parent, sau đó độc lập | `BIG_ENDIAN` |
| `slice()` | Chia sẻ phần từ `position` đến `limit` hiện tại của parent | `position = 0`; `limit = capacity = remaining` của parent | `BIG_ENDIAN` |
| `asReadOnlyBuffer()` | Chia sẻ dữ liệu, view không thể ghi | Ban đầu tương ứng parent, sau đó độc lập | `BIG_ENDIAN` |
| `asIntBuffer()` | Chia sẻ dữ liệu dưới dạng các phần tử `int` 4 byte | Trạng thái riêng, index theo `int` | Chốt order của parent **tại lúc tạo view** |

Tài liệu Java 11 xác định các ByteBuffer view `duplicate/slice/asReadOnlyBuffer` khởi tạo order là `BIG_ENDIAN`; nếu cần little-endian, hãy **đặt lại `order(ByteOrder.LITTLE_ENDIAN)` trên view mới** trước khi đọc hoặc ghi giá trị nhiều byte. Typed view như `IntBuffer` ghi nhớ order lúc được tạo; việc đổi `parent.order(...)` sau đó không đổi order đã chốt của typed view.

**Cả ba loại view trên đều không mặc nhiên deep-copy dữ liệu.** Khi sửa parent, view nhìn thấy thay đổi ở vùng dữ liệu chung. Khi sửa view ghi được, parent cũng nhìn thấy. `asReadOnlyBuffer()` chỉ ngăn việc sửa **thông qua view đó**, chứ không làm nội dung backing storage bất biến nếu parent còn có thể sửa.

### Ví dụ 3 — hiệu ứng byte order và chia sẻ nội dung

Lưu thành **`BufferViewsDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;

public class BufferViewsDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.allocate(8)
                .order(ByteOrder.LITTLE_ENDIAN);
        bytes.putInt(0x01020304).putInt(0x05060708);
        bytes.flip();

        IntBuffer ints = bytes.asIntBuffer();
        bytes.order(ByteOrder.BIG_ENDIAN);

        System.out.println("view-order=" + ints.order());
        System.out.printf("view-first=%08X%n", ints.get(0));
        System.out.printf("parent-first-big=%08X%n", bytes.getInt(0));
        System.out.println("parent-position=" + bytes.position());

        bytes.order(ByteOrder.LITTLE_ENDIAN).position(4);
        ByteBuffer slice = bytes.slice();
        ByteBuffer duplicate = bytes.duplicate();

        System.out.println("slice-capacity=" + slice.capacity());
        System.out.println("slice-order=" + slice.order());
        System.out.println("duplicate-order=" + duplicate.order());

        slice.put(0, (byte) 0x7F);
        System.out.printf("shared-byte=%02X%n",
                Byte.toUnsignedInt(bytes.get(4)));
        duplicate.position(0);
        System.out.println("parent-position-after-duplicate="
                + bytes.position());

        ByteBuffer readOnly = bytes.asReadOnlyBuffer();
        System.out.println("read-only=" + readOnly.isReadOnly());
        System.out.println("read-only-has-array=" + readOnly.hasArray());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 BufferViewsDemo.java
java BufferViewsDemo
```

Kết quả đã kiểm chứng:

```text
view-order=LITTLE_ENDIAN
view-first=01020304
parent-first-big=04030201
parent-position=0
slice-capacity=4
slice-order=BIG_ENDIAN
duplicate-order=BIG_ENDIAN
shared-byte=7F
parent-position-after-duplicate=4
read-only=true
read-only-has-array=false
```

**Các điểm cần suy ra:**

- `asIntBuffer()` được tạo khi parent đang LITTLE_ENDIAN, nên view giữ LITTLE_ENDIAN. Sau khi đổi parent sang BIG_ENDIAN, `parent.getInt(0)` đọc cùng bốn byte với thứ tự khác và ra `0x04030201`.
- `getInt(0)` là truy cập tuyệt đối, vì vậy parent vẫn `position = 0` sau thao tác này.
- Đặt parent `position = 4` rồi `slice()` tạo view bốn byte cuối với `capacity = 4`. `slice.put(0, ...)` thực chất sửa byte tại offset 4 của parent.
- Đổi `duplicate.position(0)` không đổi `parent.position()` (vẫn là 4), dù chúng cùng nhìn vào vùng dữ liệu.
- Read-only view có `isReadOnly() = true` và `hasArray() = false` ở ví dụ này. Dù parent là heap buffer, code không thể lấy backing array qua read-only view.

**Cảnh báo chia sẻ:** View có thể giữ vùng backing storage còn sống khi parent không còn được sử dụng. Nếu một view nhỏ tham chiếu buffer lớn, đừng kỳ vọng bộ nhớ lớn được giải phóng sớm. Không cho nhiều thread đọc/ghi chung vùng dữ liệu mutable mà không có cơ chế đồng bộ hoặc phân chia quyền sở hữu rõ ràng.

## 8. Wrap và arrayOffset: khi một buffer không bắt đầu từ đầu mảng

Với `ByteBuffer.wrap(array, offset, length)`, các giá trị khởi tạo rất dễ gây hiểu nhầm:

- `capacity = array.length`, không phải `length`.
- `position = offset`.
- `limit = offset + length`.
- Buffer chia sẻ trực tiếp nội dung với `array`; `arrayOffset()` của wrapper ban đầu là 0.
- Nếu muốn một view có `position = 0` và `capacity = length`, gọi `slice()` từ vùng đã giới hạn. View mới vẫn chia sẻ mảng, nhưng `arrayOffset()` có thể trở thành offset khác 0.

Ví dụ:

```java
byte[] raw = {10, 20, 30, 40, 50};
ByteBuffer region = ByteBuffer.wrap(raw, 1, 3);
System.out.println(region.position());  // 1
System.out.println(region.limit());     // 4
System.out.println(region.capacity());  // 5

ByteBuffer view = region.slice();
System.out.println(view.position());    // 0
System.out.println(view.capacity());    // 3
System.out.println(view.arrayOffset()); // 1
```

Đây là **trích đoạn** cần import `java.nio.ByteBuffer`. Dùng `region.remaining()` để biết có ba byte `20,30,40` sẵn cho hoạt động tương đối. Nếu chuyển `region.array()` cho API khác mà quên offset/length, API đó có thể xử lý **toàn bộ năm byte**, gồm cả vùng không thuộc bản ghi đang quan tâm. Tương tự, nếu bạn lấy `view.array()` mà quên `view.arrayOffset()`, bạn có thể đọc nhầm byte đầu.

Đối với API chấp nhận trực tiếp `ByteBuffer`, ưu tiên truyền buffer với `position/limit` đã được chuẩn bị đúng. Chỉ làm việc với mảng khi `hasArray()` bảo đảm truy cập được và bạn chủ động xử lý `arrayOffset()+position()`/`remaining()`.

## 9. Lựa chọn buffer trong NIO channel và pipeline nhị phân

### 9.1 Trường hợp buffer heap đủ tốt

- File hoặc gói nhỏ được xử lý trong bộ nhớ, dữ liệu đã ở dạng `byte[]`.
- Parser cần thao tác nhiều với mảng; copy dữ liệu không phải nút thắt đo được.
- Nhiều buffer ngắn hạn, cấp phát/thu hồi liên tục.
- Đọc cấu trúc nhị phân trong ứng dụng thông thường, không có yêu cầu native I/O đặc biệt.

### 9.2 Trường hợp cân nhắc direct buffer

- Luồng dữ liệu tương đối lớn đi qua `FileChannel`/`SocketChannel` thường xuyên.
- Buffer được tái sử dụng trong vòng đời rõ ràng thay vì cấp phát trên từng request.
- Profiling và benchmark cho thấy chuyển dữ liệu qua buffer trung gian đang gây chi phí đáng kể.
- Có giám sát bộ nhớ direct/native phù hợp khi chạy trong container hoặc môi trường có quota.

Sử dụng `allocateDirect` không tự thay đổi endian. Nếu binary protocol quy định little-endian, phải tạo:

```java
ByteBuffer packet = ByteBuffer.allocateDirect(4096)
        .order(ByteOrder.LITTLE_ENDIAN);
```

**Đọc từ channel:** `channel.read(buffer)` trả số byte được đọc, hoặc `-1` ở EOF với những channel phù hợp; một lần đọc không bảo đảm đủ cấu trúc gói. Với non-blocking channel, số byte có thể bằng 0. Vì vậy parser phải quản lý trạng thái đủ byte header/body và đọc bổ sung theo giao thức.

**Ghi ra channel:** `channel.write(buffer)` có thể ghi một phần; giữ `position/limit` và tiếp tục khi channel cho phép. `flip` trước khi ghi, `compact` khi có byte chưa xử lý và cần nhận thêm vào vùng đệm.

**Không dựa vào nativeOrder khi viết file:** nếu file format quy định big-endian, hãy ghi big-endian ngay cả trên CPU little-endian. Thay đổi hardware/JVM không được làm thay đổi byte của file hay wire protocol.

### 9.3 Quan hệ với bộ nén dữ liệu

Buffer thường đứng trước hoặc sau một tầng nén:

```text
ByteBuffer chứa payload gốc
   -> codec nén
   -> ByteBuffer/byte[] chứa byte nén
   -> channel hoặc storage
```

Payload nén là **dãy byte theo đặc tả codec**; việc chọn direct hay heap ảnh hưởng bố trí bộ nhớ và cách giao tiếp I/O, còn byte order chỉ ảnh hưởng khi đọc/ghi các **trường số nhị phân nhiều byte** được định nghĩa bởi định dạng. Không tự đảo byte của payload nén khi chuyển BIG_ENDIAN sang LITTLE_ENDIAN.

Nếu thư viện nén chỉ nhận `byte[]`, direct buffer có thể phải copy sang mảng để gọi API đó; không có lý do khẳng định direct sẽ nhanh hơn. Nếu codec API nhận `ByteBuffer`, kiểm tra xem nó có tôn trọng `position/limit` và có yêu cầu direct buffer hay không.

## 10. Kiểm thử thực tế và các lỗi phổ biến

Một bài test binary parser nên xác minh **byte gốc**, **giá trị decode**, **byte order**, **số byte còn lại**, và **các trường hợp thiếu byte**. Ví dụ ma trận:

| Ca | Input / trạng thái | Kỳ vọng |
|---|---|---|
| Endian big | Byte `12 34 56 78`, order BIG | `getInt(0) == 0x12345678` |
| Endian little | Byte `78 56 34 12`, order LITTLE | `getInt(0) == 0x12345678` |
| Đọc sai order | Byte `78 56 34 12`, order BIG | Giá trị `0x78563412` |
| Đủ byte | `remaining() == 4`, gọi `getInt()` | Thành công; `position` tăng 4 |
| Thiếu byte | `remaining() < 4`, gọi `getInt()` | `BufferUnderflowException` |
| Ghi vượt giới hạn | `remaining() < 4`, gọi `putInt(...)` | `BufferOverflowException` |
| Byte âm dưới Java | `buffer.get() == (byte)0xFF` | `Byte.toUnsignedInt(...) == 255` |
| Slice chia sẻ | Đổi `slice.put(0, ...)` | Parent nhìn thấy byte đổi |
| Vị trí độc lập | Đổi `duplicate.position(...)` | Parent position không đổi |
| Read-only | Gọi `put(...)` trên read-only view | `ReadOnlyBufferException` |
| Heap backing | `ByteBuffer.allocate(8).hasArray()` | `true` |
| Direct flag | `ByteBuffer.allocateDirect(8).isDirect()` | `true` |

**Những lỗi hay gặp và hướng sửa:**

1. **Dùng `ByteOrder.nativeOrder()` cho định dạng mạng/file.** Native order tùy nền tảng; phải chọn theo đặc tả dữ liệu.
2. **Ghi little-endian nhưng đọc big-endian.** Giá trị có thể sai mà không ném exception; test bằng chuỗi byte cụ thể như `12 34 56 78`.
3. **Quên `flip()` sau khi ghi.** `position` vẫn ở cuối vùng đã ghi; consumer có thể đọc byte chưa được ghi hoặc thiếu dữ liệu hợp lệ.
4. **Nghĩ `clear()` xóa dữ liệu.** Nó chỉ reset trạng thái; dữ liệu cũ còn trong vùng nhớ và có thể bị lộ nếu serialize vượt phần hợp lệ.
5. **Dùng `capacity()` thay `remaining()`.** Dễ gửi byte thừa hoặc đọc ngoài `limit`; dựa trên `position/limit`.
6. **Dùng `array()` cho mọi buffer.** Direct/read-only có thể không cho truy cập mảng; kiểm tra `hasArray()` và `arrayOffset()`.
7. **Cho rằng `slice/duplicate` deep-copy.** View dùng chung bộ nhớ; cần sao chép chủ động nếu muốn snapshot độc lập.
8. **Quên đặt byte order cho view mới.** Với `duplicate/slice/asReadOnlyBuffer` trên Java 11, đặt lại order khi cần trước phép đọc nhiều byte.
9. **Giả sử direct luôn nhanh hơn heap.** Chi phí cấp phát và vòng đời có thể lớn; đo đúng workload và quản lý ngân sách bộ nhớ.
10. **Ghi thẳng buffer có dữ liệu nhạy cảm vào pool mà không kiểm soát.** `clear` không xóa nội dung; phải có chính sách reset/ghi đè dữ liệu khi tái sử dụng để tránh dữ liệu từ request trước bị đọc lại.
11. **Dùng chung mutable buffer giữa thread.** Position/limit và dữ liệu có thể bị tranh chấp; xác định rõ quyền sở hữu hoặc đồng bộ.
12. **Nghĩ một lệnh `channel.read/write` là đủ cả packet.** Channel có thể đọc/ghi từng phần; kiểm tra `remaining()` và xử lý I/O theo trạng thái thực.

## 11. Câu hỏi tự luyện có đáp án

**1.** `0x01020304` được ghi little-endian thành byte nào?  
**Đáp án:** `04 03 02 01`. Nếu đọc các byte này big-endian, sẽ được `0x04030201`.

**2.** Một direct buffer có byte order mặc định là gì?  
**Đáp án:** `BIG_ENDIAN`, giống heap buffer mới; direct/heap không quyết định endian.

**3.** Tại sao `ByteBuffer.wrap(raw, 2, 4).capacity()` không nhất thiết là 4?  
**Đáp án:** overload này có capacity bằng `raw.length`, `position = 2` và `limit = 6`; dùng `slice()` nếu cần view riêng chỉ gồm bốn byte.

**4.** Vì sao `ByteBuffer.allocateDirect(4096).array()` không phải cách dùng đáng tin?  
**Đáp án:** API không bảo đảm direct buffer có backing array truy cập được. Kiểm tra `hasArray()` hoặc dùng `get/put` và NIO channel trực tiếp.

**5.** `asIntBuffer()` được tạo lúc parent LITTLE_ENDIAN. Sau đó parent đổi sang BIG_ENDIAN. View dùng order nào?  
**Đáp án:** Typed view giữ LITTLE_ENDIAN tại lúc tạo; parent đã đổi sẽ dùng BIG_ENDIAN cho `getInt` của chính nó.

**6.** Sau `put(new byte[]{1,2,3})` vào buffer có capacity 8, điều gì giúp consumer chỉ đọc ba byte?  
**Đáp án:** gọi `flip()` để `limit = 3` và `position = 0`; không đọc tới capacity 8.

**7.** Sau khi tiêu thụ hai byte trong số bốn byte, cần nhận thêm byte mà giữ hai byte chưa xử lý. Dùng gì?  
**Đáp án:** `compact()` dồn hai byte còn lại về đầu, đặt position sau chúng; sau đó tiếp tục `put` và `flip` trước lượt đọc tiếp.

**8.** `asReadOnlyBuffer()` có phải bản sao dữ liệu an toàn khỏi mọi thay đổi?  
**Đáp án:** không; nó chia sẻ vùng nhớ và chỉ chặn ghi thông qua view read-only. Parent vẫn có thể thay đổi nội dung.

**9.** Vì sao số hiển thị `ByteBuffer.get()` có thể âm khi byte nhị phân là `FF`?  
**Đáp án:** kiểu Java `byte` có dấu. Dùng `Byte.toUnsignedInt(buffer.get())` để nhận 255 khi cần diễn giải byte không dấu.

**10.** Trong hệ thống sử dụng nhiều direct buffer ngắn hạn, cần làm gì trước khi thay toàn bộ heap buffer bằng direct?  
**Đáp án:** benchmark cùng workload, đo chi phí cấp phát/thu hồi, I/O throughput/latency, native memory và GC; chỉ chọn direct nếu lợi ích được chứng minh và ngân sách bộ nhớ được kiểm soát.

## 12. Tài liệu API chuẩn để tra cứu

- [Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `allocate`, `allocateDirect`, `wrap`, `order`, `get/put`, `slice`, `duplicate`, typed views, direct vs non-direct.
- [Java SE 11 — ByteOrder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteOrder.html): `BIG_ENDIAN`, `LITTLE_ENDIAN`, `nativeOrder()`.
- [Java SE 11 — Buffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `capacity`, `flip`, `clear`, `rewind`, `remaining`.
- [Java SE 11 — IntBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/IntBuffer.html): typed view và các thao tác trên phần tử int.
- [Java SE 11 — FileChannel](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/channels/FileChannel.html): đọc/ghi các ByteBuffer với I/O qua channel.
- [Java SE 11 — Byte](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Byte.html) và [Short](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Short.html): chuyển kiểu không dấu khi đọc cấu trúc nhị phân.

**Nguyên tắc thực hành:** Xác định **định dạng byte của dữ liệu trước**, sau đó chọn cấu trúc buffer và vòng đời phù hợp. Kiểu endian phải xuất phát từ đặc tả; heap/direct phải xuất phát từ I/O thực tế và phép đo. Khi chia sẻ view, quản lý rõ byte order, vùng hợp lệ và quyền sửa dữ liệu.
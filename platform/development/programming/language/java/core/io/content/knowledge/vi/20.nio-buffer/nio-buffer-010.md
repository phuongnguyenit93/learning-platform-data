# ByteOrder và các view buffer cho kiểu nguyên thủy trong Java NIO

## 1. Vấn đề cần giải quyết

Khi trao đổi dữ liệu nhị phân, một dãy byte có thể biểu diễn các giá trị khác nhau tùy **thứ tự byte (byte order/endian)** và **kiểu dữ liệu** dùng để giải mã. Java NIO cung cấp `ByteBuffer` để chứa byte, `ByteOrder` để quy định cách kết hợp byte thành giá trị nhiều byte, và các **view buffer** như `IntBuffer`, `ShortBuffer`, `FloatBuffer` để đọc/ghi nhiều phần tử cùng kiểu trên chính vùng dữ liệu đó.

Ba câu hỏi cần phân biệt:

1. **Byte order:** một giá trị `int`, `short`, `long`, `float`, `double`, `char` được chuyển thành các byte theo thứ tự nào?
2. **Kiểu nhìn (view):** ta đang đọc vùng nhớ chứa byte như các phần tử kiểu gì và mỗi phần tử chiếm bao nhiêu byte?
3. **Trạng thái buffer:** `position`, `limit`, `capacity` và `mark` của view liên quan thế nào đến buffer nguồn?

Câu trả lời quan trọng: **view chia sẻ nội dung byte, nhưng có trạng thái vị trí độc lập; byte order của view được chốt vào lúc tạo view**.

## 2. Big-endian và little-endian

`java.nio.ByteOrder` có hai hằng:

- `ByteOrder.BIG_ENDIAN`: lưu byte có trọng số cao trước.
- `ByteOrder.LITTLE_ENDIAN`: lưu byte có trọng số thấp trước.

Xét giá trị nguyên 32-bit `0x01020304`:

| Thứ tự byte | Offset 0 | Offset 1 | Offset 2 | Offset 3 |
|---|---|---|---|---|
| Big-endian | `01` | `02` | `03` | `04` |
| Little-endian | `04` | `03` | `02` | `01` |

Đây là **thứ tự lưu trữ byte của cùng một giá trị**, không phải phép đảo các bit bên trong mỗi byte. Endianness chỉ ảnh hưởng đến việc ghép nhiều byte; một thao tác `get()`/`put(byte)` với **một byte** không có khác biệt big/little-endian.

Ví dụ minh họa:

~~~java
ByteBuffer big = ByteBuffer.allocate(4);
big.putInt(0x01020304); // 01 02 03 04

ByteBuffer little = ByteBuffer.allocate(4);
little.order(ByteOrder.LITTLE_ENDIAN);
little.putInt(0x01020304); // 04 03 02 01
~~~

Đây là **đoạn mã minh họa** khi đã import `java.nio.ByteBuffer` và `java.nio.ByteOrder`. Dòng comment nói về nội dung byte, không phải chuỗi được in tự động.

### Mặc định của ByteBuffer

Mọi `ByteBuffer` **mới tạo** có thứ tự byte ban đầu là **`BIG_ENDIAN`** theo hợp đồng Java 17, kể cả được tạo bằng `allocate(...)`, `allocateDirect(...)` hoặc `wrap(...)`.

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
System.out.println(buffer.order()); // BIG_ENDIAN

buffer.order(ByteOrder.LITTLE_ENDIAN);
System.out.println(buffer.order()); // LITTLE_ENDIAN
~~~

`ByteBuffer.order(ByteOrder)` thay đổi cách buffer **đọc/ghi các giá trị nhiều byte từ thời điểm đó**. Lệnh không tự đảo các byte đã lưu. Với cùng bốn byte `01 02 03 04`, `getInt()` theo big-endian đọc là `0x01020304`, theo little-endian đọc là `0x04030201`.

### ByteOrder.nativeOrder() có phải lựa chọn mặc định?

Không. `ByteOrder.nativeOrder()` trả thứ tự byte của nền tảng chạy JVM. Nó hữu ích khi tối ưu thao tác với bộ nhớ hoặc thư viện native, nhưng **không thay đổi mặc định BIG_ENDIAN của ByteBuffer mới tạo** và không phải tiêu chuẩn của file/network protocol.

**Nguyên tắc:** định dạng nhị phân quy định endian nào thì chọn đúng endian đó, bất kể `nativeOrder()` trên máy phát triển là gì. Trong một số giao thức mạng, các trường nhiều byte dùng big-endian; một số định dạng file khác dùng little-endian.

## 3. ByteBuffer đọc/ghi primitive nhiều byte

`ByteBuffer` hỗ trợ thao tác tương ứng với các primitive: `char` (2 byte), `short` (2), `int` (4), `long` (8), `float` (4), `double` (8). Không có `getBoolean()` hay `asBooleanBuffer()` tương ứng.

Ví dụ:

~~~java
ByteBuffer b = ByteBuffer.allocate(12)
        .order(ByteOrder.LITTLE_ENDIAN);
b.putShort((short) 0x1234); // chiếm 2 byte
b.putInt(0x01020304);       // chiếm 4 byte
b.putFloat(1.5f);           // chiếm 4 byte
b.flip();

short s = b.getShort();
int i = b.getInt();
float f = b.getFloat();
~~~

**Lưu ý:** `ByteBuffer.getInt(int index)` dùng chỉ số **theo byte**, nên `getInt(4)` đọc 4 byte bắt đầu tại vị trí byte số 4; đối lập với `IntBuffer.get(4)` đọc **phần tử int thứ 5** của view (offset 16 byte tính từ đầu view).

Hai dạng thao tác thường gặp:

- **Relative:** `getInt()`, `putInt(value)` sử dụng và cập nhật `position` theo số byte đọc/ghi (4 đối với int).
- **Absolute:** `getInt(index)`, `putInt(index, value)` dùng offset byte chỉ định và **không thay đổi position**.

Các thao tác tương tự áp dụng cho short, long, float, double và char. Khi không đủ byte còn lại cho thao tác relative, có thể ném `BufferUnderflowException` hoặc `BufferOverflowException`; thao tác absolute có index không hợp lệ ném `IndexOutOfBoundsException`. Ghi vào read-only buffer ném `ReadOnlyBufferException`.

`flip()` chỉ đặt `limit` thành vị trí ghi hiện tại và đưa `position` về 0, để chuẩn bị đọc. Nó **không tự đổi endian**.

## 4. View buffer cho các primitive là gì?

Một view buffer là một buffer kiểu primitive được tạo **trên nội dung byte đang có** của một `ByteBuffer`, qua:

| Phương thức trên ByteBuffer | Kiểu view | Số byte/phần tử |
|---|---|---:|
| `asCharBuffer()` | `CharBuffer` | 2 |
| `asShortBuffer()` | `ShortBuffer` | 2 |
| `asIntBuffer()` | `IntBuffer` | 4 |
| `asLongBuffer()` | `LongBuffer` | 8 |
| `asFloatBuffer()` | `FloatBuffer` | 4 |
| `asDoubleBuffer()` | `DoubleBuffer` | 8 |

Không có `asByteBuffer()` vì đối tượng gốc vốn đã là `ByteBuffer`; cũng không có view cho boolean.

Một view cung cấp API tiện lợi của kiểu phần tử đó, như `IntBuffer.get()`, `put(int)`, `get(int index)` và bulk operations `get(int[])` / `put(int[])`, thay vì phải tự đọc từng cụm 4 byte. **Tạo view không tự sao chép nội dung:** cả view và buffer byte cùng truy cập một vùng dữ liệu. Thay đổi ở view được quan sát từ buffer gốc và ngược lại.

### Bảng về nội dung và trạng thái

| Thuộc tính | Quan hệ giữa view và ByteBuffer gốc |
|---|---|
| Nội dung byte | **Chia sẻ**; thao tác ghi ảnh hưởng cả hai cách nhìn |
| `position`, `limit`, `mark` | **Độc lập**; đọc/ghi tương đối trên view không đẩy position của ByteBuffer |
| Điểm bắt đầu của view | ByteBuffer.`position()` **tại lúc tạo view** |
| Dung lượng view | `floor(ByteBuffer.remaining() / bytesPerElement)` |
| Position/limit mới | `position=0`, `limit=capacity`; mark chưa được đặt |
| Byte order | Chốt theo `ByteBuffer.order()` tại thời điểm tạo view |
| Direct | View là direct khi và chỉ khi buffer byte gốc direct |
| Read-only | View là read-only khi và chỉ khi buffer byte gốc read-only |

Ví dụ `ByteBuffer` có `position=2`, `limit=13` thì `remaining=11` byte. Tạo `asIntBuffer()` cho `capacity=floor(11/4)=2` số nguyên, dùng 8 byte bắt đầu ở offset 2. **3 byte lẻ còn lại không thuộc view IntBuffer này**; chúng vẫn tồn tại trong ByteBuffer gốc.

Nếu sau khi tạo view bạn di chuyển `position` hoặc `limit` của buffer nguồn, view đã tạo **không tự đổi kích thước hay vị trí bắt đầu**. Nếu muốn view ở vùng khác, hãy chỉnh buffer byte và tạo view mới.

### Byte order của view là cố định

~~~java
ByteBuffer bytes = ByteBuffer.allocate(4);
bytes.order(ByteOrder.LITTLE_ENDIAN);
IntBuffer first = bytes.asIntBuffer();  // cố định LITTLE_ENDIAN

bytes.order(ByteOrder.BIG_ENDIAN);
IntBuffer second = bytes.asIntBuffer(); // cố định BIG_ENDIAN
~~~

Cả `first` và `second` đọc trên cùng 4 byte, nhưng diễn giải các byte theo thứ tự khác nhau. `first.order()` trả `LITTLE_ENDIAN`, `second.order()` trả `BIG_ENDIAN`. Những view primitive này có getter `order()`, **không có setter `order(ByteOrder)`** tương tự ByteBuffer. Muốn một cách đọc khác, hãy cấu hình byte buffer và tạo view mới.

## 5. Minh họa vị trí và chia sẻ bộ nhớ

Giả sử vùng byte là:

~~~text
offset:      0   1   2   3   | 4   5   6   7
byte LE:    04  03  02  01  | 0D  0C  0B  0A
IntBuffer: [      int[0]    |     int[1]     ]
giá trị LE:       01020304  |     0A0B0C0D
giá trị BE:       04030201  |     0D0C0B0A
~~~

Tạo view từ `ByteBuffer.position()==0` và `limit()==8` cho `IntBuffer` có 2 phần tử. Nếu ghi `0x11223344` qua **view LITTLE_ENDIAN** tại index 1, bốn byte thứ hai thành `44 33 22 11`; view BIG_ENDIAN đọc lại cùng vị trí sẽ nhận `0x44332211`.

Dù hai view và ByteBuffer chia sẻ vùng nhớ, việc gọi `little.get(0)` hay `little.put(1, value)` theo **absolute index** không thay đổi bất kỳ `position` nào. Nếu dùng `little.get()` hoặc `little.put(value)` tương đối, chỉ position của `little` thay đổi.

## 6. Ví dụ Java 17+ đầy đủ, chạy được

Ví dụ sau kiểm chứng byte order của hai view, sự chia sẻ dữ liệu, trạng thái position và view từ một vị trí byte không bằng 0.

**Tệp: `ByteOrderViewDemo.java`**

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.ShortBuffer;
import java.util.HexFormat;

public class ByteOrderViewDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.allocate(8)
                .order(ByteOrder.LITTLE_ENDIAN);
        bytes.putInt(0x01020304);
        bytes.putInt(0x0A0B0C0D);
        bytes.flip();

        IntBuffer little = bytes.asIntBuffer();
        System.out.println(HexFormat.of().formatHex(bytes.array()));
        System.out.printf("LE[0]=%08X%n", little.get(0));

        bytes.order(ByteOrder.BIG_ENDIAN);
        IntBuffer big = bytes.asIntBuffer();
        System.out.printf("BE[0]=%08X%n", big.get(0));
        System.out.println("orders=" +
                little.order() + "," + big.order());

        little.put(1, 0x11223344);
        System.out.println(HexFormat.of().formatHex(bytes.array()));
        System.out.printf("BE[1]=%08X%n", big.get(1));

        System.out.println("positions=" + bytes.position()
                + "," + little.position() + "," + big.position());

        bytes.position(2);
        ShortBuffer shorts = bytes.asShortBuffer();
        System.out.println("shortCapacity=" + shorts.capacity());
        System.out.printf("BE short=%04X%n", shorts.get(0) & 0xFFFF);
    }
}
~~~

Biên dịch/chạy (JDK 17+):

~~~bash
javac ByteOrderViewDemo.java
java ByteOrderViewDemo
~~~

Stdout:

~~~text
040302010d0c0b0a
LE[0]=01020304
BE[0]=04030201
orders=LITTLE_ENDIAN,BIG_ENDIAN
0403020144332211
BE[1]=44332211
positions=0,0,0
shortCapacity=3
BE short=0201
~~~

Giải thích chi tiết:

1. `putInt` trong mode little-endian ghi các byte `04 03 02 01 0D 0C 0B 0A`. `HexFormat` dùng để hiển thị byte rõ ràng, không phụ thuộc endian của phần cứng.
2. `little` đọc bốn byte đầu thành `01020304`; `big` được tạo **sau khi đổi order** nên đọc cùng byte thành `04030201`.
3. `little.put(1, 0x11223344)` ghi `44 33 22 11` vào vùng byte thứ hai. Vì nội dung chia sẻ, `big.get(1)` nhận `44332211`.
4. Các lệnh `get(index)`/`put(index, value)` là **absolute**, nên cả ba position vẫn bằng 0.
5. Đổi `bytes.position(2)` rồi gọi `asShortBuffer()` tạo view bắt đầu từ offset byte 2, còn 6 byte ⇒ 3 short. Buffer byte khi ấy đang big-endian; hai byte `02 01` thành `0x0201`.
6. `bytes.array()` hợp lệ trong ví dụ vì `ByteBuffer.allocate(...)` cấp phát heap buffer có mảng có thể truy cập. Với **direct buffer** hoặc **read-only buffer**, không được tự tin gọi `array()`; hãy kiểm tra `hasArray()` hoặc đọc qua API buffer.

Không có bản sao dữ liệu tự động nào được tạo bởi `asIntBuffer()` và `asShortBuffer()` trong ví dụ.

## 7. View khác gì so với các cách dùng buffer gần giống?

### 7.1. `getInt()` khác `asIntBuffer().get()`

Giả sử `ByteBuffer` có 12 byte, position bằng 0:

~~~java
int x = bytes.getInt();           // đọc 4 byte, bytes.position += 4
IntBuffer view = bytes.asIntBuffer(); // bắt đầu ở bytes.position hiện tại (4)
int y = view.get();               // đọc 1 int, view.position += 1
// bytes.position không tăng thêm khi view.get() chạy
~~~

Đây là đoạn minh họa trong một phạm vi đã có biến `bytes` chứa dữ liệu thích hợp. Nếu mục tiêu là view toàn bộ 12 byte, phải đưa ByteBuffer về đúng position và limit trước khi tạo view (chẳng hạn `bytes.position(0)` nếu dữ liệu hợp lệ đang từ byte 0).

Nên dùng các lệnh `getInt`/`putShort`/`getDouble` trực tiếp khi **dữ liệu pha trộn nhiều kiểu theo một schema**; dùng typed view khi **có nhiều phần tử liên tiếp cùng kiểu**, muốn indexing theo phần tử và bulk operations.

### 7.2. `slice()` và `duplicate()` không giống typed view

- `ByteBuffer.slice()` tạo một **ByteBuffer** mới chia sẻ nội dung bắt đầu từ position hiện tại của buffer nguồn, với position mới bằng 0.
- `ByteBuffer.duplicate()` tạo một **ByteBuffer** khác chia sẻ toàn vùng byte, sao chép trạng thái position/limit/mark ban đầu.
- `asIntBuffer()` tạo **IntBuffer** có đơn vị phần tử 4 byte, capacity dựa trên remaining và endian được chốt theo order tại lúc tạo.

**Bẫy dễ gặp trong Java 17:** `ByteBuffer.slice()`, `duplicate()`, `asReadOnlyBuffer()` trả về **ByteBuffer mới có order mặc định BIG_ENDIAN**, ngay cả khi nguồn đang LITTLE_ENDIAN. Vì thế phải đặt lại order nếu mục tiêu là dùng endian của nguồn:

~~~java
ByteBuffer original = ByteBuffer.allocate(8)
        .order(ByteOrder.LITTLE_ENDIAN);

ByteBuffer part = original.slice();
part.order(original.order()); // cần đặt lại theo giao thức

IntBuffer ints = part.asIntBuffer(); // lúc này LITTLE_ENDIAN
~~~

Đây là đoạn minh họa. Đừng kết luận mọi kiểu buffer hoặc mọi bản Java đều sao chép order theo cách intuitively mong đợi: hãy dựa vào hợp đồng phương thức cụ thể.

### 7.3. `asCharBuffer()` không phải bộ giải mã UTF-8

`CharBuffer` nhìn mỗi **2 byte thành một đơn vị mã UTF-16 `char`** theo endian đã chọn. Nếu dữ liệu là UTF-8 (một ký tự có thể dài 1–4 byte), không thể giải mã bằng `asCharBuffer()`.

Để giải mã dữ liệu văn bản, dùng `StandardCharsets.UTF_8.decode(byteBuffer)` hoặc `CharsetDecoder` phù hợp. Typed view giúp **reinterpret dữ liệu nhị phân kiểu cố định**, không thay thế charset decoder.

### 7.4. Native byte order, direct buffer và hiệu năng

View có cùng tính chất **direct** như `ByteBuffer` gốc. `allocateDirect` có thể phù hợp cho I/O native hoặc truy cập bulk hiệu quả nhưng tốn chi phí cấp phát/thu hồi cao hơn trong một số trường hợp. `ByteOrder.nativeOrder()` có thể có lợi cho thao tác native trên direct buffers, nhưng **phải ưu tiên endian của định dạng tệp/giao thức**. Không tự ý chọn nativeOrder chỉ vì muốn nhanh.

Typed view và byte buffer **không thread-safe**. Nếu nhiều luồng thay đổi cùng nội dung qua các view, phải có đồng bộ thích hợp; các position độc lập không bảo đảm an toàn dữ liệu chia sẻ.

## 8. Quy trình xử lý một định dạng binary thực tế

Giả sử giao thức quy định header 2 byte big-endian, sau đó 4 số nguyên little-endian. Có thể đọc rõ ràng bằng:

~~~java
ByteBuffer packet = /* buffer chứa ít nhất 18 byte hợp lệ */;
packet.order(ByteOrder.BIG_ENDIAN);
short header = packet.getShort();

packet.order(ByteOrder.LITTLE_ENDIAN);
IntBuffer values = packet.asIntBuffer(); // bắt đầu sau header
if (values.remaining() < 4) {
    throw new IllegalArgumentException("Thiếu dữ liệu");
}
for (int i = 0; i < 4; i++) {
    int value = values.get();
    // Xử lý value.
}
~~~

**Mã minh họa không độc lập:** biến `packet` cần chứa dữ liệu đã nhận và được cấu hình position/limit đúng. Sau `getShort()`, position của `packet` tăng 2; `asIntBuffer()` nhìn từ vị trí đó theo little-endian, với phần tử rộng 4 byte. Gọi `values.get()` chỉ tăng position của `values`. Nếu muốn `packet` đi tiếp sau 16 byte payload, phải tự cập nhật `packet.position(packet.position() + 16)` sau khi đã kiểm tra giới hạn.

Khi thiết kế parser, nên:

1. Xác nhận byte order và kích thước field từ specification (không dựa vào OS).
2. Chuẩn bị đúng `position`/`limit` trước khi tạo view.
3. Kiểm tra `remaining()` đủ dữ liệu; đối với view, kiểm tra theo **số phần tử**.
4. Tạo view đúng endian cho phần payload đồng nhất kiểu.
5. Quản lý cập nhật position của buffer nguồn và view tách biệt nếu parser có nhiều bước.
6. Tính tới trường hợp buffer read-only hoặc không có backing array dễ truy cập.

## 9. Những lỗi thường gặp

1. **Quên `order(LITTLE_ENDIAN)`:** dữ liệu đọc ngược giá trị vì ByteBuffer mặc định BIG_ENDIAN.
2. **Đổi `bytes.order(...)` rồi nghĩ view cũ đổi theo:** view giữ byte order lúc nó được tạo; muốn order mới, tạo view mới.
3. **Nhầm chỉ số theo byte với theo phần tử:** `bytes.getInt(2)` đọc từ byte offset 2, còn `ints.get(2)` là phần tử thứ ba (thường bắt đầu ở byte offset 8 tương đối tới view).
4. **Cho rằng tạo view làm tăng position nguồn:** `asIntBuffer()` không dịch position của ByteBuffer.
5. **Cho rằng view được tạo từ toàn bộ capacity:** view chỉ nhìn từ **position hiện tại đến limit hiện tại**, capacity bị làm tròn xuống theo kích thước phần tử.
6. **Đọc `array()` của direct hoặc read-only buffer:** có thể không có accessible backing array; dùng `hasArray()` hoặc API đọc byte.
7. **Quên đặt lại order cho `slice()`/`duplicate()`:** trong Java 17, ByteBuffer mới có order BIG_ENDIAN.
8. **Dùng `asCharBuffer()` để giải mã UTF-8:** sai vì đó là view theo đơn vị `char` 2 byte, không phải decoder văn bản.
9. **Dùng `nativeOrder()` cho file format:** dữ liệu cần phù hợp với quy định của file/network protocol.
10. **Tin rằng dùng view là an toàn khi nhiều thread cùng ghi:** chia sẻ memory cần đồng bộ, đặc biệt với thao tác cập nhật giá trị.

## 10. Tự kiểm tra

**Câu 1.** ByteBuffer chứa `01 02 03 04` và đang BIG_ENDIAN. Đọc `getInt(0)` ra gì? Nếu đổi LITTLE_ENDIAN thì sao?

**Đáp án:** `0x01020304` ở BIG_ENDIAN; `0x04030201` ở LITTLE_ENDIAN. Các byte gốc không tự thay đổi chỉ vì đổi `order`.

**Câu 2.** Buffer có 10 byte còn lại, tạo `asIntBuffer()` thì view có bao nhiêu phần tử? Có làm thay đổi ByteBuffer.position không?

**Đáp án:** `floor(10/4)=2` phần tử int; dư 2 byte không vào view; position ByteBuffer không thay đổi.

**Câu 3.** Tạo `IntBuffer` lúc byte order LITTLE_ENDIAN, sau đó đổi ByteBuffer thành BIG_ENDIAN. View cũ dùng endian nào?

**Đáp án:** LITTLE_ENDIAN cố định; muốn BIG_ENDIAN thì tạo view khác sau khi đổi order.

### Tài liệu chính thức

- [Java 17: ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 17: ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html)
- [Java 17: IntBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/IntBuffer.html)
- [Java 17: Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html)
- [Java 17: StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)

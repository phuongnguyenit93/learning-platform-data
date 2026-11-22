# 9.3. Tạo góc nhìn byte[] hoặc ByteBuffer bằng VarHandle và chọn byte order

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Tạo một `VarHandle` đọc/ghi các giá trị kiểu `short`, `char`, `int`, `long`, `float`, `double` trực tiếp trên vùng byte của `byte[]` hoặc `ByteBuffer`, bằng hai factory method trong `MethodHandles`.
- Phân biệt **byte offset** dùng làm tọa độ của VarHandle với **chỉ số phần tử của mảng kiểu lớn hơn byte**.
- Chọn `ByteOrder.BIG_ENDIAN`, `ByteOrder.LITTLE_ENDIAN` hoặc khi thích hợp `ByteOrder.nativeOrder()`; giải thích kết quả đọc cùng dữ liệu với byte order khác nhau.
- Hiểu rằng byte order của VarHandle đã chọn lúc tạo **độc lập** với thuộc tính `ByteBuffer.order()`.
- Nhận diện lỗi về vùng nhớ, giới hạn `limit`, bộ đệm chỉ đọc, kiểu view không được hỗ trợ, điều kiện alignment và những access mode không được bảo đảm.
- Áp dụng vào định dạng dữ liệu nhị phân có nhiều trường và kiểm thử kết quả byte một cách xác định trên Java 17+.

## 1. Bài toán: nhiều byte cùng biểu diễn một giá trị

Một gói tin, header file, bản ghi nhị phân hoặc vùng nhớ native thường là chuỗi byte. Chẳng hạn bốn byte:

~~~text
01 02 03 04
~~~

Ta có thể muốn hiểu bốn byte ấy như một số nguyên 32-bit. Kết quả phụ thuộc **byte order** (endianness):

| Cách sắp xếp | Byte đầu tiên có ý nghĩa gì? | 4 byte lưu cho giá trị `0x01020304` |
| --- | --- | --- |
| **Big-endian** | Byte có trọng số lớn nhất đứng trước | `01 02 03 04` |
| **Little-endian** | Byte có trọng số nhỏ nhất đứng trước | `04 03 02 01` |

Một dãy byte **không tự mang nhãn** “big” hay “little”. Người viết parser/serializer phải biết quy định của định dạng dữ liệu. Nếu lưu theo big-endian mà giải mã như little-endian, kết quả trở thành `0x04030201`; JVM không nhất thiết ném lỗi vì cả hai cách diễn giải đều có thể hợp lệ về mặt byte.

Java có thể làm việc này bằng phép dịch bit và mask, hoặc `ByteBuffer.getInt/putInt`. Với `VarHandle`, ta tạo **góc nhìn kiểu dữ liệu** (view) trên chính vùng byte đã tồn tại:

~~~text
byte[] bytes hoặc ByteBuffer
    |
    +--> VarHandle int, BIG_ENDIAN    -> ghép 4 byte thành int
    |
    +--> VarHandle int, LITTLE_ENDIAN -> ghép 4 byte theo thứ tự ngược
    |
    +--> VarHandle short, BIG_ENDIAN  -> ghép 2 byte thành short
~~~

Các góc nhìn này **không sao chép** dữ liệu sang một mảng `int[]` hoặc `short[]` mới. Một lệnh `set` qua view làm thay đổi chính các byte ở nguồn; `get` đọc chính các byte đó và ghép chúng theo kiểu và byte order của view.

## 2. Hai factory method và chữ ký chính xác

Java 9+ cung cấp:

~~~java
// Trích chữ ký API (minh họa); không phải mã class độc lập:
static VarHandle MethodHandles.byteArrayViewVarHandle(
        Class<?> viewArrayClass, ByteOrder byteOrder);

static VarHandle MethodHandles.byteBufferViewVarHandle(
        Class<?> viewArrayClass, ByteOrder byteOrder);
~~~

Hai lời gọi thông dụng:

~~~java
// Fragment dùng các import java.lang.invoke.* và java.nio.*:
VarHandle arrayIntsBE = MethodHandles.byteArrayViewVarHandle(
        int[].class, ByteOrder.BIG_ENDIAN);

VarHandle bufferIntsLE = MethodHandles.byteBufferViewVarHandle(
        int[].class, ByteOrder.LITTLE_ENDIAN);
~~~

**`int[].class` ở đây chỉ mô tả “muốn nhìn bytes theo kiểu các phần tử int”.** Nó không có nghĩa ta truyền một `int[]` làm nguồn dữ liệu. Nguồn thực tế của factory thứ nhất vẫn là `byte[]`, của factory thứ hai vẫn là `ByteBuffer`.

| Thuộc tính | `byteArrayViewVarHandle` | `byteBufferViewVarHandle` |
| --- | --- | --- |
| Đối tượng chứa bytes | `byte[]` | `ByteBuffer` (heap, direct hoặc view phù hợp) |
| Ví dụ view type | `int[].class` | `int[].class` |
| `varType()` cho ví dụ | `int.class` | `int.class` |
| `coordinateTypes()` | `[byte[].class, int.class]` | `[ByteBuffer.class, int.class]` |
| Tọa độ `int` | **Byte offset** trong mảng `byte[]` | **Byte index** tuyệt đối trong bộ đệm được truyền |
| Giới hạn phạm vi | `byte[].length` | `ByteBuffer.limit()` |
| Lỗi vượt giới hạn | `ArrayIndexOutOfBoundsException` | `IndexOutOfBoundsException` |
| Quy tắc read-only | Mảng byte bình thường có thể ghi | Buffer read-only từ chối write access |
| Byte order | Lúc tạo VarHandle | Lúc tạo VarHandle, **ghi đè `buffer.order()`** |

Cả hai factory chỉ hỗ trợ thành phần kiểu primitive **`short`, `char`, `int`, `long`, `float`, `double`**. Chúng không tạo view cho `boolean[].class` hoặc `byte[].class`. Nếu muốn thao tác từng byte, dùng `bytes[i]`, `ByteBuffer.get(index)/put(index, value)`, hoặc cơ chế VarHandle array element thông thường khi phù hợp.

**Dạng array class phải hợp lệ**: ví dụ `int[].class`, không phải `int.class`. Factory có thể báo `IllegalArgumentException` khi class truyền vào không phải array class, `UnsupportedOperationException` khi primitive component type không nằm trong tập hỗ trợ, và `NullPointerException` nếu một đối số factory bắt buộc là null.

### 2.1. Type của handle được quyết định khi tạo

Ví dụ với `int[].class`:

~~~java
VarHandle vh = MethodHandles.byteArrayViewVarHandle(
        int[].class, ByteOrder.BIG_ENDIAN);
// vh.varType() == int.class
// vh.coordinateTypes().equals(List.of(byte[].class, int.class))
~~~

Đây là fragment (cần import `VarHandle`, `MethodHandles`, `ByteOrder` và `List`). Sau đó thao tác:

~~~java
// Fragment, giả sử byte[] bytes có ít nhất 4 byte và vh như trên:
vh.set(bytes, 0, 0x01020304);
int value = (int) vh.get(bytes, 0);
~~~

`VarHandle.get/set` là các access mode được JVM hỗ trợ như lời gọi có chữ ký đặc biệt. Từ đoạn mã này, JVM biết `get` trả `int` và `set` nhận một giá trị `int` khi VarHandle có variable type là `int`. Truyền sai loại tọa độ hoặc mong kiểu trả về không tương thích có thể gây `WrongMethodTypeException` hoặc lỗi kiểu liên quan ở runtime; không nên coi nó là một parser `Object` tùy ý.

## 3. Tọa độ là byte offset, không phải số thứ tự phần tử int

Giả sử cần ghi `int 0x01020304` vào mảng 10 byte, bắt đầu từ **byte index 1**:

~~~text
byte index:  0  1  2  3  4  5  6  7  8  9
giá trị:   00 01 02 03 04 00 00 00 00 00
                 |----------|
                int từ byte 1, BIG_ENDIAN
~~~

Lệnh là `view.set(bytes, 1, 0x01020304)` và nó dùng **bytes[1] tới bytes[4]**. Nếu bạn đang mô hình hóa các phần tử int liên tiếp có bề rộng 4 byte, offset của phần tử thứ `i` sẽ do code tính: `baseOffset + i * Integer.BYTES`. Factory không tự nhân tọa độ `i` với 4.

Đây là điểm khác với một `int[]` thật: `ints[1]` là phần tử int thứ hai; nhưng `vh.get(bytes, 1)` đọc **bắt đầu ở byte thứ hai**.

Quy tắc cho mỗi view:

| View | Số byte đọc/ghi | Offset cuối hợp lệ trên mảng có độ dài `n` |
| --- | ---: | --- |
| `short[].class`, `char[].class` | 2 | `n - 2` |
| `int[].class`, `float[].class` | 4 | `n - 4` |
| `long[].class`, `double[].class` | 8 | `n - 8` |

Điều kiện chung với một vùng có `size` byte: **`0 <= offset` và `offset <= limit - size`**. Nếu vùng ngắn hơn `size`, không có offset nào hợp lệ. Với `ByteBuffer`, dùng `limit()` hiện tại, không tùy tiện dùng `capacity()`. Đừng chỉ kiểm tra `offset < length`: điều đó chưa bảo đảm có đủ 4 hoặc 8 byte để đọc.

## 4. Byte order được gắn với VarHandle lúc tạo

Hai view cùng variable type `int` nhưng khác `ByteOrder` có thể cho hai kết quả khi đọc cùng bốn byte.

~~~text
Bytes vật lý:                01 02 03 04
BIG_ENDIAN view.get(...)  -> 0x01020304
LITTLE_ENDIAN view.get(...) -> 0x04030201
~~~

Lệnh `set` cũng tương tự: ghi `0x01020304` bằng big-endian sinh `01 02 03 04`; ghi bằng little-endian sinh `04 03 02 01`.

**Không tự động đảo byte order khi truyền từ network sang CPU.** Hãy chọn order theo **định dạng trên dây/on-disk**. Nhiều giao thức quy định big-endian; một số file format, thiết bị hoặc wire protocol có little-endian. “Chạy trên CPU little-endian” không phải lý do để đọc mọi định dạng theo little-endian.

`ByteOrder.nativeOrder()` thể hiện native order của nền tảng. Nó chỉ là lựa chọn đúng khi định dạng dữ liệu của bạn **đã quy định native order**, hoặc khi bạn đang làm việc với giao diện bộ nhớ cụ thể yêu cầu điều đó. Đừng dùng nó cho file/protocol có order cố định, vì kết quả có thể không tương thích giữa nền tảng.

### 4.1. ByteBuffer.order() có điều khiển VarHandle view không?

**Không.** Với `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.BIG_ENDIAN)`, các lần `get/set` của view luôn dùng **BIG_ENDIAN** theo đối số factory. Dù bạn gọi `buffer.order(ByteOrder.LITTLE_ENDIAN)`, điều đó chỉ điều khiển các thao tác ByteBuffer tương ứng như `buffer.getInt(index)` hoặc `buffer.putInt(index, value)`.

Ví dụ đọc cùng bytes `11 22 33 44`:

~~~text
ByteBuffer.order(LITTLE_ENDIAN)
ByteBuffer.getInt(offset)                  -> 0x44332211
VarHandle(BIG_ENDIAN).get(buffer, offset)  -> 0x11223344
~~~

**Hai kết quả khác nhau đều nhất quán**, vì hai API được yêu cầu dùng hai byte order khác nhau.

## 5. Ví dụ đầy đủ 1: byte[] và ByteBuffer, giới hạn và read-only

Lưu file **ViewVarHandleDemo.java** trong thư mục trống:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;
import java.util.HexFormat;

public class ViewVarHandleDemo {
    private static String hex(byte[] value) {
        return HexFormat.of().withUpperCase().formatHex(value);
    }
    private static String hexInt(int value) {
        return String.format("%08X", value);
    }

    public static void main(String[] args) {
        VarHandle bigArray = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.BIG_ENDIAN);
        VarHandle littleArray = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);

        byte[] packet = new byte[10];
        bigArray.set(packet, 1, 0x01020304);
        littleArray.set(packet, 5, 0x0A0B0C0D);
        System.out.println("array.hex=" + hex(packet));
        System.out.println("array.be1=" + hexInt((int) bigArray.get(packet, 1)));
        System.out.println("array.le1=" + hexInt((int) littleArray.get(packet, 1)));
        System.out.println("array.le5=" + hexInt((int) littleArray.get(packet, 5)));
        System.out.println("array.byteIndex="
                + bigArray.coordinateTypes().equals(
                        java.util.List.of(byte[].class, int.class)));
        System.out.println("array.valueType=" + bigArray.varType().getSimpleName());
        try {
            bigArray.get(packet, 7);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("array.bounds=" + ex.getClass().getSimpleName());
        }

        ByteBuffer buffer = ByteBuffer.allocate(8);
        buffer.order(ByteOrder.LITTLE_ENDIAN);
        VarHandle bigBuffer = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.BIG_ENDIAN);
        bigBuffer.set(buffer, 2, 0x11223344);
        System.out.println("buffer.hex=" + hex(buffer.array()));
        System.out.println("buffer.view=" + hexInt((int) bigBuffer.get(buffer, 2)));
        System.out.println("buffer.getInt=" + hexInt(buffer.getInt(2)));
        buffer.position(1);
        int previousPosition = buffer.position();
        bigBuffer.get(buffer, 2);
        System.out.println("buffer.positionUnchanged="
                + (buffer.position() == previousPosition));
        System.out.println("buffer.valueType=" + bigBuffer.varType().getSimpleName());

        ByteBuffer readOnly = buffer.asReadOnlyBuffer();
        System.out.println("readonly.get=" + hexInt((int) bigBuffer.get(readOnly, 2)));
        try {
            bigBuffer.set(readOnly, 2, 0xAABBCCDD);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("readonly.set=" + ex.getClass().getSimpleName());
        }
        buffer.limit(5);
        try {
            bigBuffer.get(buffer, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("buffer.limit=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy bằng **JDK 17+**:

~~~bash
javac -encoding UTF-8 ViewVarHandleDemo.java
java ViewVarHandleDemo
~~~

Stdout chính xác:

~~~text
array.hex=00010203040D0C0B0A00
array.be1=01020304
array.le1=04030201
array.le5=0A0B0C0D
array.byteIndex=true
array.valueType=int
array.bounds=ArrayIndexOutOfBoundsException
buffer.hex=0000112233440000
buffer.view=11223344
buffer.getInt=44332211
buffer.positionUnchanged=true
buffer.valueType=int
readonly.get=11223344
readonly.set=ReadOnlyBufferException
buffer.limit=IndexOutOfBoundsException
~~~

### 5.1. Phân tích kết quả trên byte[]

- `packet` có **10 byte**. `bigArray.set(packet,1,0x01020304)` ghi vào chỉ số 1–4 theo big-endian; `littleArray.set(packet,5,0x0A0B0C0D)` ghi chỉ số 5–8 theo little-endian. Byte 0 và 9 vẫn `00`. Vì vậy hex toàn mảng là `00 01 02 03 04 0D 0C 0B 0A 00`.
- Cùng byte 1–4, big-endian trả `0x01020304`, little-endian trả `0x04030201`. Java không báo lỗi byte order vì cả hai phép đọc đều hợp lệ.
- `array.le5=0A0B0C0D` cho thấy ghi và đọc bằng cùng view little-endian phục hồi đúng giá trị ban đầu.
- `coordinateTypes()` trả danh sách gồm `byte[].class`, `int.class` nên `array.byteIndex=true`; `varType()` là `int`.
- Với `int`, cần 4 byte. Offset 7 trên mảng dài 10 không đủ (chỉ còn byte 7–9), do đó `ArrayIndexOutOfBoundsException`.

Ví dụ cố tình đặt vùng `int` ở **offset 1 và 5** để nhấn mạnh tọa độ **byte** và cho thấy plain `get/set` có thể hoạt động tại offset không phải bội số của 4. Đừng diễn giải thành bảo đảm rằng các access mode atomic/volatile cũng cho phép offset như vậy.

### 5.2. Phân tích kết quả trên ByteBuffer

- `ByteBuffer.allocate(8)` tạo 8 byte trong heap. `bigBuffer.set(buffer,2,0x11223344)` ghi bytes 2–5 là `11 22 33 44`; các byte còn lại là 0. Vì vậy `buffer.hex=0000112233440000`.
- `bigBuffer.get(buffer,2)` đọc theo big-endian cố định: `0x11223344`. `buffer.getInt(2)` đọc cùng vị trí theo **`buffer.order(LITTLE_ENDIAN)`**: `0x44332211`.
- Tọa độ `2` của VarHandle là **absolute byte index**, không tự cộng với `position()`. Lệnh `bigBuffer.get` cũng **không làm tăng position** của buffer.
- Khi chuyển sang `asReadOnlyBuffer()`, read mode `get` vẫn có thể đọc; `set` bị `ReadOnlyBufferException`.
- Khi giảm `buffer.limit(5)`, đọc 4 byte từ offset 2 sẽ cần tới byte 5, vượt giới hạn index cuối được phép (4). Vì thế `get` ném `IndexOutOfBoundsException`, dù `capacity()` vẫn là 8.

**Lưu ý về `buffer.array()`:** Ví dụ dùng heap buffer từ `allocate` nên truy xuất underlying array được. **Direct buffer** và một số buffer khác không cho phép gọi `array()`. Có thể dùng view VarHandle với direct buffer mà không phải gọi `array()`; muốn in bytes của direct buffer, đọc qua các phép `get(index)` hoặc tạo một bản sao để hiển thị.

## 6. Ví dụ đầy đủ 2: một record có trường dùng byte order khác nhau

Trong thực tế, binary schema có thể định nghĩa:

| Byte offset | Trường | Kiểu đọc bằng VarHandle | Byte order | Dung lượng |
| ---: | --- | --- | --- | ---: |
| 0 | `header` | `short` | BIG_ENDIAN | 2 |
| 2 | `length` | `int` | LITTLE_ENDIAN | 4 |
| 6 | `value` | `float` | BIG_ENDIAN | 4 |
| 10 | `reserved` | bytes thô | Không áp dụng | 2 |

Đây là **định dạng minh họa do bài học định nghĩa**, không đại diện một giao thức chuẩn có sẵn. Dữ liệu được lưu trong một `byte[]` dài 12; không cần chuyển nó thành ba mảng kiểu khác nhau.

Tạo file **BinaryPacketDemo.java**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;
import java.util.HexFormat;

public class BinaryPacketDemo {
    public static void main(String[] args) {
        VarHandle shortBE = MethodHandles.byteArrayViewVarHandle(
                short[].class, ByteOrder.BIG_ENDIAN);
        VarHandle intLE = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);
        VarHandle floatBE = MethodHandles.byteArrayViewVarHandle(
                float[].class, ByteOrder.BIG_ENDIAN);

        byte[] frame = new byte[12];
        shortBE.set(frame, 0, (short) 0x1234);
        intLE.set(frame, 2, 0x01020304);
        floatBE.set(frame, 6, 1.5f);

        System.out.println("frame=" + HexFormat.of().withUpperCase().formatHex(frame));
        System.out.println("header=" + String.format("%04X", (short) shortBE.get(frame, 0) & 0xFFFF));
        System.out.println("length=" + String.format("%08X", (int) intLE.get(frame, 2)));
        System.out.println("value=" + (float) floatBE.get(frame, 6));
        System.out.println("tail=" + (frame[10] == 0 && frame[11] == 0));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BinaryPacketDemo.java
java BinaryPacketDemo
~~~

Stdout:

~~~text
frame=1234040302013FC000000000
header=1234
length=01020304
value=1.5
tail=true
~~~

Phân tích dữ liệu:

~~~text
Offset : 00 01 | 02 03 04 05 | 06 07 08 09 | 10 11
Bytes  : 12 34 | 04 03 02 01 | 3F C0 00 00 | 00 00
Trường : header   length         value        reserved
Order  : BIG      LITTLE         BIG          —
~~~

- `shortBE` lưu `0x1234` thành `12 34`.
- `intLE` lưu `0x01020304` thành `04 03 02 01`.
- `floatBE` lưu `1.5f` dưới biểu diễn IEEE 754 của `float`, cho bytes `3F C0 00 00` theo big-endian.
- Hai byte reserved chưa bị ghi nên vẫn bằng 0.
- Khi hiển thị `header`, phép `& 0xFFFF` cho phép xem 16 bit của `short` như số không dấu để định dạng. `VarHandle` vẫn có variable type là primitive `short`, không tự tạo “unsigned short”.

Ví dụ cho thấy một record có thể chứa **nhiều kiểu và byte order khác nhau**, miễn schema xác định đúng offset, kích thước và cách diễn giải. Không được đoán byte order dựa vào tên trường hoặc cấu hình máy đang chạy.

## 7. Độ dài, limit, position và slice: bốn khái niệm khác nhau

### 7.1. Mảng byte

Với `byte[]`, vùng hợp lệ luôn từ offset 0 tới `length-1`. Một `int` view cần cửa sổ 4 byte liên tiếp. Điều kiện nên kiểm tra trước khi gọi (tránh tràn số):

~~~java
// Fragment minh họa: bytes là byte[], offset là int.
int size = Integer.BYTES;
if (offset < 0 || offset > bytes.length - size) {
    throw new IllegalArgumentException("Không đủ byte cho int");
}
int value = (int) intBE.get(bytes, offset);
~~~

Đoạn này cần định nghĩa `intBE` trước và import nếu đặt thành chương trình hoàn chỉnh. Nếu `bytes.length - size` âm thì mọi offset không âm đều bị từ chối, đúng ý nghĩa vùng dữ liệu quá ngắn.

### 7.2. ByteBuffer

`ByteBuffer` phân biệt:

- **capacity:** tổng dung lượng của vùng buffer.
- **limit:** điểm kết thúc logic hiện tại, exclusive; VarHandle view không được đọc/ghi một giá trị vắt qua limit.
- **position:** vị trí của các thao tác tương đối như `get()` và `put(byte)`; VarHandle dùng index tuyệt đối và không di chuyển position.
- **slice:** một `ByteBuffer` mới nhìn vào phần vùng nguồn tương ứng; offset của view được tính từ đầu **slice** mới, không từ offset 0 của buffer gốc.

Ví dụ khái niệm:

~~~java
// Fragment: base là ByteBuffer phù hợp, vh là int-view VarHandle.
base.position(4);
ByteBuffer segment = base.slice();
// segment có index 0 ứng với byte tại position 4 của base.
int value = (int) vh.get(segment, 0);
~~~

Đoạn trên **không chạy độc lập** vì `base`, `vh` chưa khai báo. Các giới hạn của `segment` được áp dụng độc lập. Nếu cần truy cập chính xác các byte của buffer gốc, phải tính đúng offset trước khi tạo slice hoặc giữ bản đồ offset.

**Đối chiếu với view buffer `asIntBuffer()`:** `ByteBuffer.asIntBuffer()` tạo một `IntBuffer` mà chỉ số phần tử được tính theo **int** và vùng ban đầu bắt đầu tại position của ByteBuffer khi tạo view. Trong khi đó, `byteBufferViewVarHandle(int[].class,...).get(buffer,index)` vẫn nhận **byte index** của `ByteBuffer` truyền vào. Không trộn hai hệ tọa độ.

## 8. Alignment và access mode: plain get/set khác thao tác đồng bộ

`VarHandle` không chỉ có `get/set`; nó còn các mode như `getVolatile`, `setVolatile`, `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd` và bitwise atomic updates. Nhưng một view trên vùng byte **không bảo đảm tất cả mode đều hợp lệ ở mọi offset, mọi kiểu và mọi nền tảng**.

Theo hợp đồng của hai factory:

1. **Plain `get` và `set` có thể đọc/ghi ở offset không thẳng hàng** với bề rộng kiểu, miễn đủ số byte và quyền truy cập hợp lệ.
2. Các access mode **khác plain `get/set`** phải chú ý **alignment theo địa chỉ nền** của vùng byte và kích thước kiểu. Nếu truy cập misaligned, API có thể ném `IllegalStateException` cho những mode đó.
3. Một số nhóm atomic update được hỗ trợ đối với `int`, `long`, `float`, `double`; nhóm numeric/bitwise atomic update có tập kiểu hỗ trợ hẹp hơn, chủ yếu `int`, `long`. Cần xem phương thức và platform cụ thể.
4. `isAccessModeSupported(VarHandle.AccessMode.X)` chỉ cho biết một access mode có được hỗ trợ đối với handle **nói chung**; một offset cụ thể vẫn có thể misaligned hoặc vượt giới hạn.
5. Với `ByteBuffer`, **read-only** chặn write mode ngay cả khi buffer có đủ bytes. Với view trên `byte[]`, việc dùng atomic mode cũng đòi alignment phù hợp.

### 8.1. Kiểm tra alignment trên ByteBuffer

Một cách kiểm tra có ý nghĩa cho `int` view:

~~~java
// Fragment: buffer là ByteBuffer đã tạo, index là byte offset.
int byteWidth = Integer.BYTES;
int misalignment = buffer.alignmentOffset(index, byteWidth);
if (misalignment != 0) {
    // Không sử dụng atomic/volatile mode tại offset này.
}
// Plain get/set có hợp đồng riêng; vẫn phải kiểm tra limit.
~~~

`alignmentOffset` xét địa chỉ nền, không chỉ phép chia `index % 4`. Một slice có base address khác, hoặc một heap/direct buffer, có thể khiến phép kiểm tra không đơn giản như dựa riêng vào offset. Với heap buffer, khả năng xác định alignment cho một số giá trị `unitSize` còn phụ thuộc implementation; nếu không xác định được, hãy xử lý giới hạn API thay vì suy đoán.

Với `byte[]`, API chính thức mô tả cách xác định misalignment qua `ByteBuffer.wrap(new byte[0]).alignmentOffset(0, sizeOfT)` kết hợp index và kích thước. Không được suy diễn rằng cứ `index % 4 == 0` là mọi JVM, mọi array base address đều bảo đảm atomic.

### 8.2. Không đánh đồng endianness với memory ordering

**Byte order** trả lời câu hỏi “các byte của một giá trị nhiều byte được sắp xếp theo hướng nào?”. **Memory ordering** (plain, opaque, acquire, release, volatile) trả lời câu hỏi “quan sát đọc/ghi giữa các luồng có những bảo đảm thứ tự và visibility nào?”.

Hai chiều này **khác nhau**:

~~~text
BIG_ENDIAN / LITTLE_ENDIAN   -> cách ghép byte thành giá trị
get / set / getVolatile / ... -> ngữ nghĩa truy cập bộ nhớ
~~~

Chọn `ByteOrder.BIG_ENDIAN` không biến một thao tác `get` plain thành volatile, và chọn `getVolatile` không đổi quy tắc big/little. Nếu dữ liệu được chia sẻ giữa nhiều luồng hoặc thread giao tiếp với thiết bị/native code, phải thiết kế đồng bộ theo đúng đặc tả, không chỉ dựa vào byte order.

### 8.3. Có nên dùng VarHandle này để làm bộ đếm atomic?

Chỉ khi nhu cầu đúng, variable type/mode hỗ trợ, dữ liệu được căn chỉnh hợp lệ và vùng nhớ có mô hình ownership rõ ràng. Không nên xây atomic counter bằng cách chọn bất kỳ vị trí 4 byte trong một packet rồi gọi `getAndAdd`. Định dạng binary thông thường dùng VarHandle chủ yếu để **đọc/ghi có byte order xác định**; nếu mục tiêu là concurrent counter, một field `int/long` có VarHandle tương ứng hoặc atomic class thường dễ lý giải hơn.

## 9. Xử lý lỗi và kiểm tra dữ liệu

| Hành động | Vấn đề | Lỗi hoặc dấu hiệu cần xử lý |
| --- | --- | --- |
| Tạo view với `int.class` thay vì `int[].class` | `viewArrayClass` không phải array class | `IllegalArgumentException` |
| Tạo view với `byte[].class` hoặc `boolean[].class` | Kiểu phần tử không được hỗ trợ cho byte view | `UnsupportedOperationException` |
| Tạo view với `viewArrayClass` hoặc `byteOrder` là `null` | Thiếu đối số factory | `NullPointerException` |
| `get(byte[],offset)` vượt độ dài của kiểu | Không đủ bytes trong array | `ArrayIndexOutOfBoundsException` |
| `get(ByteBuffer,offset)` vượt `limit` hiện tại | Không đủ bytes trong vùng logic | `IndexOutOfBoundsException` |
| `set(readOnlyBuffer,...)` | Buffer chỉ đọc | `ReadOnlyBufferException` |
| Access mode cần alignment nhưng dữ liệu misaligned | Không đáp ứng điều kiện của mode | `IllegalStateException` |
| Access mode không hỗ trợ với view type | Nhầm loại atomic operation | `UnsupportedOperationException` |
| Sai kiểu tọa độ hoặc variable type khi gọi `get/set` | Signature-polymorphic call không tương thích với handle | `WrongMethodTypeException` hoặc lỗi kiểu liên quan |
| Đọc đúng phạm vi nhưng byte order sai | Diễn giải sai dữ liệu | **Thường không có ngoại lệ**: nhận một giá trị khác |

Đừng bắt hết mọi `RuntimeException` rồi trả giá trị 0: làm như vậy sẽ che mất lỗi giới hạn byte, lỗi cấu hình byte order và lỗi dữ liệu. Với file/protocol, hãy kiểm tra header/version/length, xác định byte order từ specification và báo lỗi parse có ngữ cảnh.

### 9.1. Kiểm tra trước khi decode packet

Một parser thực tế nên có contract:

1. Đảm bảo vùng chứa có số byte tối thiểu.
2. Xác định layout và **offset tính theo byte**.
3. Chọn `ByteOrder` **dựa trên specification**; không lấy theo `nativeOrder()` nếu protocol không cho phép.
4. Decode từng field bằng view đúng kiểu, đúng offset.
5. Kiểm tra giá trị đọc được: version, magic, length, range, checksum hoặc quy tắc schema.
6. Khi encode, ghi các trường đúng order và size; test golden bytes (hex) để tránh lỗi không lộ ra khi round-trip cùng một codec sai.

**Golden bytes quan trọng hơn chỉ round-trip**: nếu bạn ghi và đọc đều bằng cùng một order sai, test round-trip vẫn có thể pass. So sánh với chuỗi byte mong đợi theo giao thức mới phát hiện việc đảo order.

## 10. Khi nào chọn byte[] view, ByteBuffer view hoặc API khác?

| Nhu cầu | Lựa chọn thường hợp lý | Cân nhắc |
| --- | --- | --- |
| Binary data đang ở `byte[]`, cần đọc/ghi nhiều giá trị primitive | `byteArrayViewVarHandle` | Không tạo mảng primitive mới; tự quản lý byte offset |
| Data ở `ByteBuffer`, có thể heap/direct/sliced | `byteBufferViewVarHandle` | Giới hạn theo `limit`, read-only và alignment |
| Cần vài lệnh `getInt/putInt` đơn giản trên buffer | `ByteBuffer.order(...).getInt(index)` | Rõ ràng, thường dễ đọc khi chỉ có một byte order |
| Cần nhiều trường với order khác nhau trên cùng vùng byte | Nhiều VarHandle, mỗi cái gắn order/type riêng | Tránh đổi mutable `buffer.order()` qua lại |
| Muốn index theo `int` và bulk operations | `ByteBuffer.asIntBuffer()` | View buffer dùng index phần tử, position/limit riêng; byte order chốt khi tạo view |
| Chỉ xử lý một vài byte đơn lẻ | `bytes[i]` hoặc `ByteBuffer.get(index)` | Không cần multi-byte view |
| Cần giải mã giao thức có trường biến độ dài, bit fields, checksum | Kết hợp byte view + parser rõ schema | VarHandle không tự parse cấu trúc hoặc validate dữ liệu |
| Cần atomic memory access nhiều luồng | VarHandle của field/array element hoặc byte view với mode/alignment được kiểm chứng | Không nhầm byte order với memory ordering |

Điểm mạnh của `VarHandle` ở đây là **góc nhìn có kiểu và order cố định** trên chính vùng byte gốc. Nó không thay thế toàn bộ `ByteBuffer`, không tự xác định schema, cũng không làm dữ liệu binary trở nên an toàn nếu thiếu bounds check.

## 11. Những nhầm lẫn thường gặp

**Nhầm 1: `int[].class` nghĩa là ta có thể truyền `int[]` vào `get`.** Sai. Nó chỉ chọn kiểu phần tử của view; tọa độ đầu tiên vẫn là `byte[]` hoặc `ByteBuffer` tùy factory.

**Nhầm 2: Offset 3 nghĩa là phần tử int thứ tư.** Sai. Đó là **byte offset 3**, bắt đầu đọc bytes 3, 4, 5, 6 nếu đủ phạm vi.

**Nhầm 3: `ByteBuffer.order()` quyết định byte order của mọi VarHandle nhìn vào nó.** Sai. VarHandle dùng byte order truyền lúc tạo, độc lập với `ByteBuffer.order()`.

**Nhầm 4: Gọi `buffer.position(10)` làm `vh.get(buffer,0)` đọc từ byte 10.** Sai. VarHandle byte buffer view dùng byte index tuyệt đối của buffer được truyền. Muốn hệ tọa độ riêng từ vị trí hiện tại, tạo một slice phù hợp và dùng index của slice.

**Nhầm 5: Dữ liệu đọc không báo lỗi tức là byte order đúng.** Sai. Sai order thường vẫn có giá trị hợp lệ về mặt primitive. Kiểm tra bằng golden bytes, magic/version và quy tắc protocol.

**Nhầm 6: View ghi `int` luôn atomic vì bề rộng 4 byte.** Sai. Phải xem access mode, alignment, nền tảng và hướng dẫn API. Plain `get/set` không tự biến thành `getVolatile/setVolatile`.

**Nhầm 7: Dùng `buffer.capacity()` để kiểm tra có đủ byte.** Sai nếu `limit()` đã bị giảm; view truy cập theo limit hiện tại.

**Nhầm 8: `ByteBuffer.array()` luôn có thể lấy mảng.** Sai. Direct buffer hoặc read-only buffer có thể không cung cấp mảng backing thông qua API đó.

**Nhầm 9: `byte[].class` là view type hợp lệ để nhận lại một byte.** Sai. Hai factory multi-byte view hỗ trợ short/char/int/long/float/double; đọc byte riêng bằng API byte thông thường.

**Nhầm 10: `nativeOrder()` luôn cho hiệu năng tốt nhất nên dùng cho dữ liệu mạng.** Không có bảo đảm tổng quát đó; quan trọng hơn, định dạng mạng/file phải được đọc theo byte order đã quy định, dù host có order khác.

## 12. Tự kiểm tra

**Câu 1.** Có bytes `01 02 03 04` và hai `int` VarHandle: một big-endian, một little-endian. Hai giá trị `get` là gì?

**Đáp án:** `0x01020304` và `0x04030201`. Đây là hai cách ghép cùng bốn byte.

**Câu 2.** Muốn ghi `int` thứ ba vào một vùng byte bắt đầu từ offset 6, các int liên tiếp dài 4 byte thì offset của int thứ ba là bao nhiêu?

**Đáp án:** `6 + 2 * 4 = 14` nếu đánh số phần tử từ 0. Tọa độ truyền cho VarHandle là **14 byte**, không phải 2.

**Câu 3.** `byteArrayViewVarHandle(int[].class, BIG_ENDIAN)` có yêu cầu nguồn là `int[]`?

**Đáp án:** Không. Nguồn luôn là `byte[]`; `int[].class` mô tả variable type `int` của view.

**Câu 4.** Nếu `buffer.order(LITTLE_ENDIAN)`, nhưng view được tạo bằng `byteBufferViewVarHandle(int[].class, BIG_ENDIAN)`, `view.get(buffer,index)` đọc theo order nào?

**Đáp án:** BIG_ENDIAN. Thuộc tính order của ByteBuffer không override order của VarHandle.

**Câu 5.** `ByteBuffer.allocate(8)` sau đó `limit(5)`. VarHandle int get tại offset 2 có hợp lệ không?

**Đáp án:** Không. Cần bytes 2, 3, 4, 5, nhưng byte index 5 nằm ngoài limit exclusive 5. Có thể ném `IndexOutOfBoundsException`.

**Câu 6.** Vì sao `set` trên `readOnlyBuffer` không thành công dù offset đúng?

**Đáp án:** Buffer read-only cấm write access; VarHandle view không vượt qua quyền read-only.

**Câu 7.** Plain `get` ở offset 1 trên int view chạy được. Có thể suy ra `getVolatile` hoặc `compareAndSet` ở offset 1 luôn hoạt động không?

**Đáp án:** Không. Các mode khác plain get/set có yêu cầu alignment và phạm vi hỗ trợ khác. Cần kiểm tra alignment và hợp đồng API.

**Câu 8.** Ghi/đọc cùng một record bằng LITTLE_ENDIAN cho ra đúng round-trip. Có chứng minh file tuân thủ một specification BIG_ENDIAN không?

**Đáp án:** Không. Codec có thể cùng ghi và đọc sai order mà round-trip vẫn pass. Cần so byte với vector/golden bytes từ specification.

## Ghi nhớ

- `MethodHandles.byteArrayViewVarHandle(T[].class, order)` tạo view trên **byte[]**; `MethodHandles.byteBufferViewVarHandle(T[].class, order)` tạo view trên **ByteBuffer**.
- Hai tọa độ luôn là **đối tượng chứa byte + byte offset**; offset không tự nhân với `sizeof(T)`.
- Kiểu `T` được hỗ trợ: **short, char, int, long, float, double**. Góc nhìn không tạo mảng `T[]` mới.
- **ByteOrder của VarHandle được chốt lúc tạo**. `ByteBuffer.order()` không thay đổi cách ghép byte của view.
- Kiểm tra **length/limit, read-only, offset, alignment và access mode** trước khi dùng; plain get/set khác atomic access.
- Luôn kiểm chứng **golden bytes của định dạng**; đọc cùng dữ liệu bằng order sai thường vẫn ra một số hợp lệ.

## Tài liệu tra cứu

- Java SE 17, **MethodHandles** — `byteArrayViewVarHandle` và `byteBufferViewVarHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17, **VarHandle** — types, coordinates, access modes, atomicity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html
- Java SE 17, **ByteBuffer** — absolute get/put, position/limit/capacity, slice, alignmentOffset: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, **ByteOrder** — BIG_ENDIAN, LITTLE_ENDIAN, nativeOrder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html

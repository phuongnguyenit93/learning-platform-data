# Phân biệt giá trị số với thứ tự byte khi trao đổi dữ liệu trong Java

Một số nguyên có **giá trị** riêng, ví dụ `0x1234_5678` (thập phân `305_419_896`). Nhưng khi gửi số đó qua mạng hoặc lưu thành tệp nhị phân, các bên phải thống nhất **cách biến giá trị thành các byte** và **thứ tự sắp xếp các byte**. Nếu bên ghi dùng big-endian nhưng bên đọc tự coi dữ liệu là little-endian, cùng bốn byte có thể được giải mã thành một giá trị hoàn toàn khác.

Bài học thuộc chủ đề **Bit và số không dấu**: cần tách bạch ba khái niệm **giá trị số**, **mẫu bit có độ rộng xác định**, và **thứ tự byte (endianness)**. Sau đó mới xét cách Java diễn giải mẫu bit đó như `int` có dấu, `long` hoặc một giá trị không dấu.

## 1. Một giá trị số, nhiều cách biểu diễn

Trong mã nguồn, cùng một giá trị có thể được viết bằng nhiều cơ số:

```java
int decimal = 305_419_896;
int hexadecimal = 0x1234_5678;
int binary = 0b0001_0010_0011_0100_0101_0110_0111_1000;
// Ba biến có cùng giá trị int.
```

Đây là ba khai báo minh họa có thể đặt trong phương thức Java. Dấu `0x` là **cách viết literal** trong mã nguồn, không phải một byte được tự động gửi ra mạng; dấu `_` chỉ giúp đọc dễ hơn. Con số `0x1234_5678` có mẫu bit 32 bit chia thành bốn nhóm tám bit:

```text
Hex:    12       34       56       78
Bit:  00010010 00110100 01010110 01111000
Byte:     1        2        3        4
```

Vì một chữ số hex tương ứng 4 bit, **hai chữ số hex tương ứng một byte**. Đây mới là những nhóm byte logic của mẫu số; khi trao đổi dữ liệu, ta còn phải quyết định **byte nào xuất hiện trước**.

Không nhầm:

- **Cơ số**: cách con người viết/đọc một giá trị bằng thập phân, nhị phân, hex.
- **Độ rộng**: số bit dùng biểu diễn, chẳng hạn `int` 32 bit, `long` 64 bit.
- **Có dấu/không dấu**: cách diễn giải mẫu bit thành giá trị số, nhất là khi bit cao nhất bật.
- **Thứ tự byte**: trật tự đặt các byte của **một giá trị nhiều byte** vào chuỗi byte trong tệp, gói tin hay bộ đệm.

## 2. Big-endian và little-endian

Với giá trị 32 bit `0x12345678`:

| Thứ tự | Byte tại offset 0 | Offset 1 | Offset 2 | Offset 3 |
| --- | --- | --- | --- | --- |
| **Big-endian** | `12` | `34` | `56` | `78` |
| **Little-endian** | `78` | `56` | `34` | `12` |

**Big-endian** đặt **byte có trọng số lớn nhất (most significant byte, MSB)** trước. **Little-endian** đặt **byte có trọng số nhỏ nhất (least significant byte, LSB)** trước. Trong ví dụ, `0x12` chứa các bit trọng số lớn nhất, `0x78` chứa các bit trọng số nhỏ nhất.

Hình dung hai phía:

```text
Giá trị logic: 0x12345678

Big-endian:
offset       0    1    2    3
bytes       12   34   56   78

Little-endian:
offset       0    1    2    3
bytes       78   56   34   12
```

**Không đảo thứ tự bit bên trong từng byte**. Byte `0x12` vẫn là `00010010` ở cả hai dạng; khác biệt nằm ở vị trí các byte trong chuỗi. Không có “bit dấu di chuyển” theo endian: bit có ý nghĩa dấu thuộc vị trí bit của số 32/64 bit **sau khi đã ghép đúng các byte**.

Đối với **một byte đơn lẻ**, không có sự khác biệt về thứ tự byte. Endianness chỉ có ý nghĩa khi chuyển một giá trị nhiều byte thành chuỗi byte hoặc ngược lại.

## 3. Đọc sai thứ tự làm đổi số, dù các byte không đổi

Giả sử nhận được bốn byte liên tiếp:

```text
12 34 56 78
```

Nếu đặc tả quy định big-endian, giá trị là `0x12345678` = `305419896`. Nếu đọc **chính bốn byte đó** như little-endian, ta nhận `0x78563412` = `2018915346`.

Với byte `b0`–`b3` được hiểu là các giá trị **không dấu 0..255**, công thức giải mã là:

```text
Big-endian:
value = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

Little-endian:
value = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
```

Đây là công thức logic trên bốn giá trị byte **đã chuyển thành không dấu**. Trong Java phải cẩn thận nâng kiểu/mask trước khi dịch để không bị mở rộng dấu ngoài ý muốn; phần thực hành bên dưới thể hiện cách làm an toàn.

Nếu hai đầu giao tiếp không thống nhất endian, chương trình có thể vẫn chạy, vẫn nhận đủ bốn byte, nhưng cho giá trị sai **âm thầm**. Đây là lỗi giao thức, không phải lỗi phép cộng hay tình trạng mất gói dữ liệu.

## 4. `int` trong Java có dấu, nhưng dữ liệu trao đổi có thể là unsigned

Java `int` có **32 bit có dấu**, miền `-2_147_483_648` đến `2_147_483_647`. Có những giao thức quy định trường **unsigned 32 bit**, miền `0` đến `4_294_967_295`. Hai miền cùng dùng **bốn byte**; sự khác biệt là cách diễn giải các bit sau khi ghép byte.

Ví dụ mẫu bit `0xFEDCBA98`:

```text
Mẫu 32 bit:                FE DC BA 98
Giá trị int có dấu:        -19088744
Giá trị unsigned 32 bit:   4275878552
```

Nếu bên nhận Java dùng `ByteBuffer.getInt()`, biến nhận `int` là `-19088744`. Điều này **không chứng minh dữ liệu bị sai thứ tự**: mẫu 32 bit vẫn là `FEDCBA98`. Khi giao thức yêu cầu unsigned 32 bit, chuyển cách diễn giải bằng:

```java
int raw = 0xFEDC_BA98;
long unsigned = Integer.toUnsignedLong(raw); // 4275878552L
```

Đây là mảnh mã minh họa trong một phương thức. `Integer.toUnsignedLong` mở rộng bằng số 0 để giữ đúng giá trị **không dấu** 32 bit dưới dạng `long`, thay vì sign-extend. `Integer.toUnsignedString(raw)` có thể biểu diễn kết quả dưới dạng chuỗi.

Cần tránh kết luận “số âm thì endian sai”: **signedness và endianness độc lập**. Luôn kiểm tra đúng thứ tự byte trước, rồi mới diễn giải mẫu bit theo hợp đồng signed/unsigned.

## 5. `byte` Java có dấu: mask `0xFF` trước khi ghép

Một byte trên dây thường được mô tả trong tài liệu giao thức như `0x00`–`0xFF` (0–255). Nhưng kiểu `byte` Java là **8 bit có dấu**, phạm vi -128 đến 127. Ví dụ:

```java
byte b = (byte) 0xFE;
int signed = b;                 // -2: mở rộng dấu sang int.
int unsigned = b & 0xFF;        // 254: giữ tám bit thấp.
int alsoUnsigned = Byte.toUnsignedInt(b); // 254.
```

Khi `byte` được nâng thành `int` để dịch trái, nếu nó âm thì có thể phát sinh bit 1 mở rộng ở phần cao. Vì vậy phải chuẩn hóa mỗi byte bằng `& 0xFF` hoặc `Byte.toUnsignedInt` **trước khi ghép**.

Một hàm đọc unsigned 32-bit big-endian an toàn:

```java
static long readUnsigned32BigEndian(byte[] bytes) {
    if (bytes.length != 4) {
        throw new IllegalArgumentException("expected exactly four bytes");
    }
    return ((long) (bytes[0] & 0xFF) << 24)
            | ((long) (bytes[1] & 0xFF) << 16)
            | ((long) (bytes[2] & 0xFF) << 8)
            | (bytes[3] & 0xFFL);
}
```

Đây là **phương thức trong một lớp Java**, không phải chương trình đầy đủ. Mỗi byte được chuyển thành miền 0–255, ghép theo big-endian, rồi lưu vào `long` để kết quả unsigned 32 bit luôn là số không âm và không bị tràn `int` có dấu. Tránh `return (bytes[0] << 24) | ...` khi không mask byte: Java sign-extend `byte` âm lên `int`.

## 6. Java `ByteBuffer`: ghi và đọc theo thứ tự đã thỏa thuận

Trong `java.nio`, `ByteBuffer` hỗ trợ cấu hình `ByteOrder.BIG_ENDIAN` và `ByteOrder.LITTLE_ENDIAN`:

```java
int value = 0x1234_5678;
byte[] bigEndian = java.nio.ByteBuffer.allocate(4)
        .order(java.nio.ByteOrder.BIG_ENDIAN)
        .putInt(value)
        .array();

byte[] littleEndian = java.nio.ByteBuffer.allocate(4)
        .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .putInt(value)
        .array();
```

Hai mảng byte lần lượt chứa `12 34 56 78` và `78 56 34 12`. **`value` không thay đổi.** `ByteBuffer.putInt` quyết định cách chia mẫu 32 bit thành 4 byte dựa trên thứ tự byte của buffer.

Khi đọc, phải đặt cùng `ByteOrder` theo **hợp đồng dữ liệu**:

```java
int fromBig = java.nio.ByteBuffer.wrap(bigEndian)
        .order(java.nio.ByteOrder.BIG_ENDIAN)
        .getInt(); // 0x12345678

int fromLittle = java.nio.ByteBuffer.wrap(littleEndian)
        .order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .getInt(); // 0x12345678
```

Một `ByteBuffer` mới tạo có **thứ tự mặc định là `BIG_ENDIAN`**. Tuy nhiên, đừng dựa mù quáng vào mặc định của chương trình khi thiết kế giao thức: gọi `.order(...)` tường minh để thể hiện contract và tránh hiểu sai.

Hàm `putInt`/ `getInt` xử lý **đúng bốn byte**; `putShort`/ `getShort` xử lý hai byte; `putLong`/ `getLong` xử lý tám byte. `put`/ `get` cho **một byte** không bị endian làm thay đổi. Khi dùng `ByteBuffer.allocate(4)`, `.putInt(...)` đẩy position tới 4; `.array()` lấy mảng lưu trữ. Nếu chuyển từ ghi sang đọc trên **cùng buffer**, thường phải gọi `flip()` trước `getInt()`. Ở ví dụ `wrap(byte[])`, buffer mới có position = 0 nên đọc được ngay.

Lưu ý `ByteBuffer` có thể direct hoặc read-only và không phải lúc nào cũng có mảng truy cập được bằng `.array()`; ví dụ này chọn buffer heap bằng `allocate(4)` có backing array. Trong ứng dụng thực, có thể ghi vào `ByteBuffer` rồi truyền vùng byte bằng API I/O thay vì giả định luôn gọi được `.array()`.

## 7. Ví dụ hoàn chỉnh Java 17+: cùng số, hai thứ tự byte

Tạo tệp **`ByteOrderDemo.java`** với mã sau:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ByteOrderDemo {
    static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(String.format("%02X", Byte.toUnsignedInt(b)));
        }
        return out.toString();
    }

    static long readUnsigned32BigEndian(byte[] bytes) {
        if (bytes.length != 4) {
            throw new IllegalArgumentException("expected exactly four bytes");
        }
        return ((long) (bytes[0] & 0xFF) << 24)
                | ((long) (bytes[1] & 0xFF) << 16)
                | ((long) (bytes[2] & 0xFF) << 8)
                | (bytes[3] & 0xFFL);
    }

    public static void main(String[] args) {
        int number = 0x1234_5678;
        byte[] big = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(number)
                .array();
        byte[] little = ByteBuffer.allocate(4)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putInt(number)
                .array();

        System.out.println("value=" + String.format("0x%08X", number));
        System.out.println("bigEndian=" + hex(big));
        System.out.println("littleEndian=" + hex(little));
        System.out.println("readBE=" + String.format("0x%08X",
                ByteBuffer.wrap(big).order(ByteOrder.BIG_ENDIAN).getInt()));
        System.out.println("readLE=" + String.format("0x%08X",
                ByteBuffer.wrap(little).order(ByteOrder.LITTLE_ENDIAN).getInt()));
        System.out.println("wrongOrder=" + String.format("0x%08X",
                ByteBuffer.wrap(big).order(ByteOrder.LITTLE_ENDIAN).getInt()));

        int rawBits = 0xFEDC_BA98;
        byte[] payload = ByteBuffer.allocate(4)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(rawBits)
                .array();
        int decoded = ByteBuffer.wrap(payload)
                .order(ByteOrder.BIG_ENDIAN)
                .getInt();
        System.out.println("signedInt=" + decoded);
        System.out.println("unsignedInt=" + Integer.toUnsignedLong(decoded));
        System.out.println("wireBytes=" + hex(payload));
        System.out.println("manualUnsigned=" + readUnsigned32BigEndian(payload));

        byte signedByte = (byte) 0xFE;
        System.out.println("signedByte=" + signedByte);
        System.out.println("unsignedByte=" + Byte.toUnsignedInt(signedByte));
    }
}
```

Chạy tại thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 ByteOrderDemo.java
java ByteOrderDemo
```

Kết quả stdout chính xác:

```text
value=0x12345678
bigEndian=12 34 56 78
littleEndian=78 56 34 12
readBE=0x12345678
readLE=0x12345678
wrongOrder=0x78563412
signedInt=-19088744
unsignedInt=4275878552
wireBytes=FE DC BA 98
manualUnsigned=4275878552
signedByte=-2
unsignedByte=254
```

Ý nghĩa quan trọng:

- Hai dòng `bigEndian` và `littleEndian` khác nhau ở **thứ tự byte**, còn dòng `value` vẫn chỉ một giá trị `0x12345678`.
- `readBE` và `readLE` bằng nhau nếu bên đọc dùng **đúng endian của bên ghi**; `wrongOrder=0x78563412` chứng minh đọc sai endian làm đổi số.
- `signedInt=-19088744` và `unsignedInt=4275878552` có cùng mẫu bit `0xFEDCBA98`. Số âm đến từ cách đọc có dấu, không phải lỗi thứ tự byte.
- `manualUnsigned=4275878552` xác nhận có thể tự ghép dữ liệu theo big-endian với phép dịch/mask đúng.
- `signedByte=-2` và `unsignedByte=254` cho thấy cần xử lý tính có dấu của `byte` trước khi ghép số nguyên nhiều byte.

## 8. Khi giao tiếp qua mạng, điều gì phải thống nhất?

Trong nhiều giao thức mạng truyền thống, các trường số nguyên nhiều byte ở **network byte order (big-endian)**. Ví dụ, nhiều trường của header IPv4/TCP sử dụng big-endian. Nhưng **không phải mọi giao thức trên TCP đều tự động dùng big-endian**: giao thức ứng dụng có thể quy định little-endian, byte-order riêng theo từng trường, hoặc biểu diễn văn bản/biến độ dài.

Một hợp đồng dữ liệu cần nêu rõ:

| Thuộc tính | Ví dụ quy ước |
| --- | --- |
| Kiểu trường | unsigned 32-bit |
| Số byte | Chính xác 4 |
| Byte order | Big-endian |
| Dải hợp lệ | 0 đến 4_294_967_295 |
| Vị trí trong thông điệp | Offset 0–3 sau header |
| Cách xử lý dữ liệu thiếu | Chưa đủ 4 byte thì chưa được giải mã trường |
| Kiểm tra dữ liệu | Từ chối giá trị ngoài phạm vi nghiệp vụ |

Ví dụ field `length` được quy định là **4 byte unsigned big-endian**. Bên gửi phải ghi 4 byte theo đúng thứ tự; bên nhận phải đọc **đủ 4 byte** trước khi tính giá trị `long` không dấu và kiểm tra giới hạn độ dài tối đa chấp nhận được. Không nên cấp phát vùng nhớ theo chiều dài nhận được trước khi xác minh dải, quota và giới hạn dữ liệu.

**TCP chỉ cung cấp luồng byte**, không đánh dấu “đây là một `int`” hoặc bảo đảm mỗi lần gọi `read` trả về trọn một trường. Phần đóng gói thông điệp, xử lý partial read, kiểu số và endian thuộc trách nhiệm thiết kế giao thức.

## 9. `DataInputStream`, `DataOutputStream` và sự khác biệt với `ByteBuffer`

Java `DataOutputStream.writeInt(int)` và `DataInputStream.readInt()` quy định encoding **big-endian** cho giá trị bốn byte. Đây là lựa chọn tiện nếu giao thức của bạn cũng dùng định dạng này.

```java
java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
try (java.io.DataOutputStream out = new java.io.DataOutputStream(buffer)) {
    out.writeInt(0x1234_5678);
}
byte[] bytes = buffer.toByteArray(); // 12 34 56 78
```

Đây là đoạn mã trong một phương thức Java có xử lý ngoại lệ phù hợp; không phải một chương trình độc lập. Nếu giao thức quy định little-endian, **không dùng `DataOutputStream.writeInt` như thể nó tự chuyển endian**; dùng `ByteBuffer.order(LITTLE_ENDIAN)` hoặc viết byte theo thứ tự được yêu cầu.

`ByteBuffer.getInt` và `DataInputStream.readInt` đều trả về **`int` có dấu**. Nếu trường thực tế là unsigned 32 bit, kết quả `int` vẫn chứa đúng 32 bit và có thể dùng `Integer.toUnsignedLong` để đọc giá trị không dấu.

## 10. Nhầm endian với bit order, ký tự, và số được gửi dưới dạng văn bản

Endianness chỉ là **thứ tự byte trong biểu diễn nhiều byte**. Không nên trộn nó với ba khái niệm khác:

**Thứ tự bit:** Có những giao thức mô tả bit cao/thấp được truyền trước trong một byte hoặc một khung; đó là một quy tắc ở mức bit. Thay big-endian thành little-endian **không đảo thứ tự các bit trong từng byte**.

**Mã hóa văn bản:** Khi gửi chuỗi `"305419896"` theo UTF-8, ta gửi **các byte ký tự** (ví dụ byte `0x33` cho ký tự `'3'`), chứ không phải bốn byte nhị phân `12 34 56 78`. Bên nhận phải biết đang nhận chuỗi số hay số nhị phân. Với định dạng JSON, số thường được biểu diễn bằng các ký tự văn bản; byte order của một `int` nhị phân không tự động áp dụng vào đó.

**Thứ tự code unit của UTF-16:** Một số cách mã hóa chuỗi 16-bit có khái niệm endian riêng. Dù có cùng tên big/little endian, quy tắc mã hóa văn bản vẫn phải được xác định thông qua charset và đặc tả văn bản, không suy ngược từ endian của một trường số nhị phân.

**Độ rộng trường:** Gửi số `1` thành một byte `01`, hai byte `00 01` hoặc bốn byte `00 00 00 01` là ba hợp đồng khác nhau. Chọn endian không thay thế việc thống nhất số byte, độ rộng signed/unsigned và cách đánh dấu đầu/cuối trường.

## 11. Lỗi thường gặp khi trao đổi số nhị phân

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Bên gửi ghi big-endian, bên nhận đọc little-endian | `12 34 56 78` thành `0x78563412` | Quy định byte order và cấu hình hai bên tương ứng |
| Cho rằng `int` âm tức dữ liệu bị đảo byte | Nhầm signedness với endian | Kiểm tra mẫu bit và `Integer.toUnsignedLong` |
| Ghép `byte` âm mà không mask | Sign extension làm thay đổi các bit cao | Dùng `& 0xFF` hoặc `Byte.toUnsignedInt` |
| Dùng `byte[]` nhưng không có hợp đồng kiểu | Không xác định được độ dài, signedness và byte order | Định nghĩa schema rõ ràng cho từng trường |
| Gọi `ByteBuffer.getInt()` sau `putInt` mà không `flip()` | Sai position hoặc buffer underflow | `flip()` khi chuyển từ ghi sang đọc cùng buffer |
| Cho rằng `DataOutputStream.writeInt` dùng endian của CPU | Luồng ra không khớp định dạng mong muốn | Biết rõ API này ghi big-endian |
| Dùng `Integer.parseInt` để giải mã bốn byte | Parse nhận chuỗi ký tự số, không phải định dạng nhị phân | Dùng `ByteBuffer`, bit shifts hoặc `DataInputStream` |
| Dùng `0x12345678` trong văn bản như thể đó là byte truyền đi | Nhầm cú pháp literal và payload thực | Chỉ định encoding nhị phân hoặc văn bản |
| Tin rằng TCP `read` luôn nhận đủ bốn byte | Giải mã khi dữ liệu chưa đủ | Đọc theo vòng lặp hoặc API readFully |
| Coi unsigned 32-bit là `int` dương thông thường | Giá trị lớn hơn `Integer.MAX_VALUE` bị hiển thị âm | Dùng `long` và unsigned conversion |

## 12. Checklist khi thiết kế và kiểm thử

Trước khi viết bộ mã hóa/giải mã, xác nhận **mỗi field** có độ rộng 8/16/32/64 bit hoặc kiểu biến độ dài; giá trị signed hay unsigned; big-endian hay little-endian; offset và byte count; dải nghiệp vụ hợp lệ. Với field kiểu unsigned 32-bit, trong Java thường nên dùng `long` làm kiểu API bên ngoài và kiểm tra `0 <= value <= 0xFFFF_FFFFL` trước khi chuyển sang bốn byte.

Một bộ test tối thiểu nên có:

1. **Giá trị dễ nhìn:** `0x12345678` để phát hiện đảo byte. Big-endian `12 34 56 78`; little-endian `78 56 34 12`.
2. **Biên unsigned 32-bit:** `0x00000000`, `0x7FFFFFFF`, `0x80000000`, `0xFFFFFFFF`. Đọc/ghi vẫn phải giữ bit chính xác bất kể `int` tạm thời âm.
3. **Round-trip:** ghi một giá trị rồi đọc lại với byte order tương ứng, so sánh **bit pattern** và giá trị unsigned nếu đặc tả yêu cầu.
4. **Sai endian có chủ ý:** đọc bytes big-endian bằng little-endian để chắc chắn test bắt được thay đổi mong đợi.
5. **Thông điệp thiếu byte:** thử nhận 1–3 byte khi mong đợi 4 byte; bộ giải mã phải chờ đủ hoặc báo thiếu dữ liệu rõ ràng.
6. **Đầu vào ngoài giới hạn:** thử kích thước quá lớn, giá trị vượt hợp đồng và dữ liệu không hợp lệ, bảo đảm không cấp phát/tiến hành xử lý nguy hiểm.

**Câu hỏi tự kiểm tra:**

- Cùng một số `0x12345678`, big-endian và little-endian có giá trị số khác nhau không? **Không**, nếu được giải mã theo đúng quy ước. Chỉ thứ tự bốn byte khi lưu/truyền khác.
- Byte nào xuất hiện trước trong little-endian? **Byte có trọng số thấp nhất**, ở đây là `0x78`.
- Vì sao `ByteBuffer.getInt()` có thể trả số âm cho một field unsigned 32-bit? Vì **Java `int` có dấu**; hãy dùng `Integer.toUnsignedLong` để đọc cách diễn giải unsigned.
- `& 0xFF` dùng để làm gì? Giữ **8 bit thấp** và loại tác động sign extension khi nâng `byte` âm lên kiểu lớn hơn.
- Nếu giao thức dùng little-endian nhưng lập trình viên dùng `DataOutputStream.writeInt`, điều gì xảy ra? Byte trên dây **không đúng quy ước little-endian**, vì API này ghi big-endian.

**Ghi nhớ:** giá trị số không quyết định thứ tự byte của payload. Endianness là một phần của **hợp đồng serialization**, signedness là cách **diễn giải mẫu bit**, còn `byte` Java có dấu nên phải mask khi ghép byte thủ công. Khi hai phía thống nhất độ rộng, endian, signed/unsigned và kiểm thử cùng các chuỗi byte chuẩn, dữ liệu nhị phân sẽ được trao đổi chính xác.

# Mặt nạ bit và chuyển `byte` sang giá trị 0 đến 255 trong Java

## 1. Vấn đề: cùng tám bit nhưng có hai cách hiểu

Trong Java, kiểu nguyên thủy `byte` chứa **8 bit có dấu** và có miền giá trị từ `-128` đến `127`. Tuy nhiên, khi xử lý file nhị phân, màu sắc RGB, dữ liệu mạng, ảnh hoặc giao thức, một byte thường được hiểu như **8 bit không dấu**, tức giá trị từ `0` đến `255`. Cùng một mẫu bit có thể có hai giá trị tùy cách diễn giải.

| Mẫu 8 bit | Hiểu dưới dạng `byte` Java có dấu | Hiểu không dấu |
| --- | ---: | ---: |
| `0000_0000` | 0 | 0 |
| `0000_0001` | 1 | 1 |
| `0111_1111` | 127 | 127 |
| `1000_0000` | -128 | 128 |
| `1010_0101` | -91 | 165 |
| `1111_1111` | -1 | 255 |

Java **không có kiểu nguyên thủy `unsigned byte`**. Khi cần giá trị không dấu từ 0 đến 255, ta lưu mẫu bit ban đầu trong `byte`, rồi chuyển sang một kiểu có miền rộng hơn, thường là `int`, bằng **mặt nạ bit**:

```java
byte value = (byte) 0xA5; // 0xA5 = 165, ngoài miền byte có dấu.
int unsigned = value & 0xFF;

System.out.println(value);    // -91
System.out.println(unsigned); // 165
```

`value & 0xFF` là cách viết phổ biến để lấy **8 bit thấp** của một giá trị nguyên dưới dạng số không dấu. Java 8+ còn cung cấp `Byte.toUnsignedInt(value)` với mục đích tương đương, rõ nghĩa hơn ở nơi cần chuyển `byte` sang `int` không dấu.

## 2. Mặt nạ bit (*bit mask*) là gì?

*Mặt nạ bit* là một giá trị có các bit được chọn là `1`, các bit không cần giữ là `0`. Khi kết hợp với toán tử AND theo bit `&`:

- Bit ở vị trí mặt nạ là `1`: giữ nguyên bit tương ứng của toán hạng.
- Bit ở vị trí mặt nạ là `0`: kết quả tại vị trí đó thành `0`.

Bảng chân trị của phép AND theo bit:

| Bit A | Bit mask | `A & mask` |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |

`0xFF` là số nguyên thập lục phân có giá trị `255`. Ở kiểu `int` 32 bit, nó có dạng:

```text
0x000000FF
00000000 00000000 00000000 11111111
                                ^^^^^^^^
                          giữ tám bit thấp
```

Khi tính `n & 0xFF`, tám bit thấp của `n` được giữ lại; **24 bit cao của kết quả `int` đều bằng 0**. Vì vậy, kết quả luôn nằm trong khoảng `0..255`, bất kể `n` ban đầu dương hay âm.

Ví dụ với một `int` bình thường:

```java
int n = 0x1234;
int lowByte = n & 0xFF; // 0x34 = 52.
```

Nó chỉ giữ tám bit thấp, **không phải kiểm tra xem `n` có thuộc khoảng 0..255 hay không**. Nếu giá trị ban đầu nằm ngoài khoảng đó, dữ liệu bit cao bị bỏ đi. Ta sẽ phân biệt “trích xuất bit” và “kiểm tra miền” ở phần sau.

## 3. Vì sao `byte` âm khi chuyển thẳng sang `int`?

Khi mở rộng một `byte` có dấu sang `int`, Java **giữ nguyên giá trị số có dấu**. Về mặt bit, cách biểu diễn có thể hiểu bằng *sign extension* (mở rộng bit dấu):

```java
byte b = (byte) 0xA5;
int signed = b;
System.out.println(signed); // -91
```

`0xA5` có tám bit `1010_0101`. Bit cao nhất của `byte` là `1`, nên `byte` được hiểu là `-91`. Khi mở rộng sang `int`, phần bit cao được điền bằng `1` để giữ lại giá trị âm:

```text
byte (8 bit):             10100101                  = -91
int sau sign extension:   11111111 11111111 11111111 10100101
                         = 0xFFFFFFA5              = -91

AND 0x000000FF:          00000000 00000000 00000000 10100101
                         = 0x000000A5              = 165
```

Vì sao `& 0xFF` hiệu quả?

1. `byte` được nâng lên `int` khi tham gia phép AND với literal `0xFF` (kiểu `int`).
2. Nếu `byte` âm, quá trình nâng kiểu giữ bit dấu, tạo ra các bit `1` ở phần cao của `int`.
3. AND với `0x000000FF` xóa sạch 24 bit cao; giữ nguyên tám bit dữ liệu gốc.
4. Kết quả là **`int` không âm từ 0 đến 255**, đúng với cách hiểu 8 bit không dấu.

Như vậy `& 0xFF` **không thay đổi bit đang có trong biến `byte`**; nó tạo ra một kết quả `int` mới. Một `byte` có giá trị `-1` vẫn là `-1` sau khi gọi `Byte.toUnsignedInt` hoặc tính mặt nạ; chỉ cách diễn giải tám bit thành `int` mới thay đổi.

## 4. Hai cách chuẩn để chuyển `byte` thành `int` 0..255

### 4.1. Dùng mặt nạ `& 0xFF`

```java
byte b = (byte) 0xFF;
int unsigned = b & 0xFF;
System.out.println(b);        // -1
System.out.println(unsigned); // 255
```

Ưu điểm: ngắn, dễ kết hợp khi phân tích bit, dịch bit và ghép các byte. Nhược điểm: người đọc cần hiểu `0xFF` giữ tám bit thấp.

### 4.2. Dùng `Byte.toUnsignedInt`

```java
byte b = (byte) 0x80;
int unsigned = Byte.toUnsignedInt(b);
System.out.println(b);        // -128
System.out.println(unsigned); // 128
```

`Byte.toUnsignedInt(byte x)` là phương thức tĩnh từ Java 8, trả về `int` chứa giá trị **không dấu của tám bit**. Với mọi giá trị `byte`, nó cho cùng kết quả như `b & 0xFF`.

| Dữ liệu đầu vào `byte` | `b & 0xFF` | `Byte.toUnsignedInt(b)` |
| ---: | ---: | ---: |
| -128 | 128 | 128 |
| -91 | 165 | 165 |
| -1 | 255 | 255 |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 127 | 127 | 127 |

**Nên chọn gì?** Dùng `Byte.toUnsignedInt(b)` khi muốn diễn đạt rõ “đọc byte như một số không dấu”. Dùng `b & 0xFF` khi đang thao tác trực tiếp với mặt nạ, trường bit hoặc ghép các byte trong một biểu thức bitwise. Cả hai đều đúng và đều cho ra kiểu `int`.

## 5. Dấu `&` là phép toán bit, khác `&&`

Với hai toán hạng số nguyên, `&` áp dụng AND cho từng bit. Với toán hạng boolean, `&` cũng có dạng AND logic **không đoản mạch**. Trong khi đó `&&` chỉ dùng cho điều kiện logic, có đoản mạch và không thể dùng để tạo mặt nạ số nguyên.

```java
byte b = (byte) 0xF0;
int unsigned = b & 0xFF; // 240.

// int error = b && 0xFF; // Không biên dịch: && yêu cầu boolean.
```

Mặt nạ không phải phép so sánh kiểu `b >= 0` hay phép lấy giá trị tuyệt đối. Với `b = -1`, `Math.abs(b)` cho `1` khi giá trị được nâng lên `int`; nhưng `b & 0xFF` cho `255`. Hai bài toán hoàn toàn khác nhau.

## 6. Dùng mặt nạ để lấy nibble và ghép nhiều byte

Một *nibble* là bốn bit. Từ một `byte`, có thể trích xuất nibble thấp và nibble cao để xử lý mã màu, header nhị phân hoặc giao thức.

```java
byte b = (byte) 0xAB;      // -85 dưới dạng byte có dấu.
int unsigned = b & 0xFF;  // 171.
int lowNibble = unsigned & 0x0F;       // 11 = 0xB.
int highNibble = unsigned >>> 4;       // 10 = 0xA.

System.out.println(lowNibble);  // 11
System.out.println(highNibble); // 10
```

Ở đây `0x0F` chỉ giữ bốn bit thấp; sau khi đã chuyển sang `unsigned` trong miền 0..255, dịch phải logic `>>> 4` đưa bốn bit cao xuống thấp.

**Bẫy:** nếu dịch trực tiếp `b >>> 4` khi `b` âm, `b` được nâng thành `int` có các bit cao bằng `1`. Dù `>>>` chèn `0` từ trái, kết quả có thể vẫn là một số lớn với các bit cao còn lại. Hãy viết `(b & 0xFF) >>> 4` hoặc `(b >>> 4) & 0x0F` nếu chỉ muốn nibble cao.

### Ghép hai byte thành số nguyên không dấu 16 bit

Giả sử `high` và `low` lần lượt là byte cao, byte thấp của một số được lưu theo thứ tự *big-endian*:

```java
byte high = (byte) 0xFF;
byte low = (byte) 0x80;

int value = (Byte.toUnsignedInt(high) << 8)
        | Byte.toUnsignedInt(low);

System.out.println(value); // 65408 = 0xFF80.
```

Ta lấy giá trị không dấu của từng byte trước khi ghép:

- `Byte.toUnsignedInt(high)` trả `255`; dịch trái 8 bit cho `0xFF00`.
- `Byte.toUnsignedInt(low)` trả `128`; phép OR theo bit `|` tạo `0xFF80`.
- Vì kiểu `int` đủ chứa toàn bộ khoảng 0..65535 nên kết quả `65408` đúng với cách hiểu unsigned 16-bit.

Nếu ghép các byte có dấu mà quên mask, *sign extension* của `high` hoặc `low` có thể làm sai kết quả. Khi ghép nhiều byte, cần quyết định **thứ tự byte (endianness)** và **dấu** theo định dạng dữ liệu trước khi viết phép dịch/OR. Ví dụ trên quy ước byte đầu là phần cao; định dạng *little-endian* sẽ có công thức khác.

## 7. Chuyển ngược số 0..255 về mẫu tám bit trong `byte`

Một số trong khoảng `0..255` có thể được mã hóa thành tám bit bằng cách cast xuống `byte`:

```java
int unsigned = 255;
byte packed = (byte) unsigned;

System.out.println(packed);                   // -1
System.out.println(Byte.toUnsignedInt(packed)); // 255
```

Trong biến `packed`, tám bit đều là `1`; giá trị `byte` của Java là `-1`. Điều này **không có nghĩa dữ liệu 255 đã mất**: tám bit ban đầu vẫn được giữ và có thể đọc trở lại bằng `Byte.toUnsignedInt`.

Tuy nhiên, cast hẹp **không kiểm tra miền**. Ví dụ:

```java
int unexpected = 300;
byte truncated = (byte) unexpected; // 44.
```

`300` có biểu diễn nhị phân dài hơn tám bit; giữ tám bit thấp cho `44`. Khi ứng dụng cần đảm bảo dữ liệu đã đúng miền unsigned byte, phải kiểm tra **trước** khi cast:

```java
static byte packUnsignedByte(int value) {
    if (value < 0 || value > 255) {
        throw new IllegalArgumentException("Expected 0..255");
    }
    return (byte) value;
}
```

Đây là ví dụ một phương thức ứng dụng tự định nghĩa, dùng khi **lỗi vượt miền phải bị phát hiện**. Không dùng `value & 0xFF` như phép kiểm tra đầu vào: biểu thức đó sẽ biến `300` thành `44` mà không cảnh báo.

## 8. `byte[]`, `ByteBuffer` và dữ liệu nhị phân từ file/mạng

### Mảng `byte[]`

Dữ liệu file hoặc mạng thường nằm trong mảng `byte[]`:

```java
byte[] payload = {(byte) 0x00, (byte) 0x80, (byte) 0xFF};

for (byte item : payload) {
    int unsigned = Byte.toUnsignedInt(item);
    System.out.println(unsigned);
}
```

Kết quả:

```text
0
128
255
```

Đối với một phần tử `payload[i]`, `payload[i] & 0xFF` là cách thay thế trực tiếp. Đừng kiểm tra `payload[i] > 127` để tìm các byte “trên 127”: một biến `byte` **không bao giờ lớn hơn 127**. Hãy lấy số không dấu bằng `Byte.toUnsignedInt(payload[i])` trước khi so sánh.

### `ByteBuffer.get()` trả về `byte` có dấu

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.wrap(new byte[] {(byte) 0xFF});
byte item = buffer.get();
int unsigned = Byte.toUnsignedInt(item); // 255.
```

`ByteBuffer.get()` đọc một byte dưới dạng `byte` nguyên thủy. Nếu muốn một giá trị số nguyên không dấu, phải mask hoặc gọi `Byte.toUnsignedInt`. `ByteBuffer` cũng có các phương thức đọc số nhiều byte (`getShort`, `getInt`, …), chịu ảnh hưởng thứ tự byte; cách xử lý unsigned cho nhiều byte không đồng nhất với mask chỉ một byte.

### Khác biệt rất quan trọng: `InputStream.read()` đã trả về `int`

Với `java.io.InputStream.read()`, khi có byte dữ liệu, phương thức **đã trả về `int` từ 0 đến 255**. Giá trị `-1` được dành riêng làm tín hiệu **đã hết luồng (EOF)**.

```java
int next = input.read(); // input là InputStream đã được tạo.
if (next == -1) {
    System.out.println("EOF");
} else {
    System.out.println("Unsigned byte: " + next);
}
```

Đây là đoạn minh họa trong một ngữ cảnh đã có biến `input` kiểu `InputStream`; **không phải chương trình chạy độc lập**.

**Không viết `int value = input.read() & 0xFF` nếu chưa kiểm tra EOF**: khi `read()` trả `-1`, `-1 & 0xFF` thành `255`, che mất tín hiệu kết thúc luồng.

Sự khác biệt cần phân biệt:

| API | Kiểu nhận được | Ý nghĩa của `-1` |
| --- | --- | --- |
| `byte[][index]` | `byte` (-128..127) | Một mẫu bit dữ liệu `0xFF` hợp lệ |
| `ByteBuffer.get()` | `byte` (-128..127) | Một mẫu bit dữ liệu `0xFF` hợp lệ |
| `InputStream.read()` | `int` (0..255 hoặc -1) | **EOF**, không phải byte dữ liệu |
| `DataInputStream.readUnsignedByte()` | `int` (0..255) | Không dùng -1 làm giá trị kết thúc; hết dữ liệu gây `EOFException` |

Khi dùng `InputStream.read(byte[])`, dữ liệu thực tế được đặt trong `byte[]`, nhưng chính giá trị trả về của phương thức là **số byte đã đọc** (hoặc `-1` khi EOF). Không nhầm số byte đã đọc với một byte dữ liệu cụ thể.

## 9. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`UnsignedByteMaskDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.nio.ByteBuffer;

public class UnsignedByteMaskDemo {
    public static void main(String[] args) throws Exception {
        byte b = (byte) 0xA5;

        int signed = b;
        int unsignedMasked = b & 0xFF;
        int unsignedApi = Byte.toUnsignedInt(b);

        System.out.println("signed=" + signed);
        System.out.println("masked=" + unsignedMasked);
        System.out.println("API=" + unsignedApi);
        System.out.println("signed hex=" + Integer.toHexString(signed));
        System.out.println("unsigned hex=" + Integer.toHexString(unsignedMasked));

        int lowNibble = unsignedMasked & 0x0F;
        int highNibble = unsignedMasked >>> 4;
        System.out.println("nibbles=" + highNibble + "," + lowNibble);

        byte high = (byte) 0xFF;
        byte low = (byte) 0x80;
        int combined = (Byte.toUnsignedInt(high) << 8)
                | Byte.toUnsignedInt(low);
        System.out.println("combined=" + combined);

        int packedValue = 255;
        byte packed = (byte) packedValue;
        System.out.println("packed signed=" + packed);
        System.out.println("packed unsigned=" + Byte.toUnsignedInt(packed));

        ByteBuffer buffer = ByteBuffer.wrap(new byte[] {(byte) 0x80});
        System.out.println("buffer unsigned="
                + Byte.toUnsignedInt(buffer.get()));

        try (ByteArrayInputStream stream =
                new ByteArrayInputStream(new byte[] {(byte) 0xFF})) {
            int first = stream.read();
            int eof = stream.read();
            System.out.println("stream data=" + first);
            System.out.println("stream EOF=" + eof);
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac UnsignedByteMaskDemo.java
java UnsignedByteMaskDemo
```

Kết quả:

```text
signed=-91
masked=165
API=165
signed hex=ffffffa5
unsigned hex=a5
nibbles=10,5
combined=65408
packed signed=-1
packed unsigned=255
buffer unsigned=128
stream data=255
stream EOF=-1
```

Kết quả `signed hex=ffffffa5` thể hiện `byte` âm được mở rộng dấu khi chuyển sang `int`. `unsigned hex=a5` thể hiện các bit cao đã bị xóa bởi mặt nạ `0xFF`. Hai dòng cuối xác nhận `InputStream.read()` phân biệt rõ byte `0xFF` (trả `255`) với EOF (trả `-1`).

## 10. Các lỗi thường gặp

1. **Nhầm `byte` là kiểu 0..255.** Trong Java, `byte` là kiểu **có dấu**, từ -128 đến 127. Cần `int` khi muốn lưu giá trị 0..255.
2. **Cho rằng `int u = b;` đã tạo giá trị unsigned.** Lệnh này bảo toàn giá trị có dấu bằng mở rộng dấu; khi `b < 0`, `u` cũng âm. Phải dùng `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`.
3. **Dùng `Math.abs(b)` để chuyển không dấu.** Trị tuyệt đối không chuyển cách diễn giải tám bit, đặc biệt `-1` phải trở thành `255`, không phải `1`.
4. **Dùng `b >>> 4` trực tiếp để lấy nibble cao.** Với `byte` âm, Java mở rộng dấu thành `int` trước khi dịch. Hãy mask trước rồi dịch.
5. **Ghép nhiều byte mà không mask.** Một byte âm khi nâng kiểu có thể đưa các bit `1` lên những vị trí cao ngoài ý muốn. Dùng `Byte.toUnsignedInt` cho từng byte trước khi dịch và OR.
6. **Nghĩ `b & 0xFF` làm `b` thành kiểu unsigned.** Biến `b` không đổi; kết quả biểu thức là `int`.
7. **Nhầm `&` với `&&`.** `&` trên số nguyên là AND từng bit; `&&` dành cho các điều kiện boolean.
8. **Mask `InputStream.read()` trước khi kiểm tra EOF.** `-1` là EOF nhưng `-1 & 0xFF == 255`; thao tác đó có thể biến tín hiệu EOF thành byte dữ liệu giả.
9. **Dùng `value & 0xFF` như phép kiểm tra dữ liệu nhập từ 0..255.** Mask cắt bỏ bit cao; nếu cần bác bỏ số ngoài miền, hãy kiểm tra điều kiện `value < 0 || value > 255` trước khi chuyển sang `byte`.
10. **Cho rằng các giá trị `byte` âm là dữ liệu bị hỏng.** Chúng chỉ là cách nhìn có dấu của một mẫu tám bit. Với dữ liệu nhị phân, phải xem giao thức định nghĩa trường đó là có dấu hay không dấu.

## 11. Quy tắc chọn cách làm trong thực tế

- Nếu đã có **`byte` dữ liệu** và muốn số nguyên không dấu: dùng `Byte.toUnsignedInt(b)` hoặc `b & 0xFF`.
- Nếu đang **trích xuất bit** trong `int`: dùng mặt nạ thích hợp, như `& 0x0F` cho nibble thấp hoặc `& 0xFF` cho byte thấp.
- Nếu cần **tách/ghép nhiều byte**: quy định thứ tự byte trước; chuyển từng phần tử sang kiểu không dấu rồi dịch/OR.
- Nếu có **số nguyên đầu vào** cần đóng gói thành một byte: kiểm tra 0..255 trước khi cast nếu không cho phép cắt bit.
- Nếu đang đọc bằng **`InputStream.read()`**: xử lý `-1` như EOF trước mọi phép mask; `read()` đã trả `0..255` khi đọc thành công.

**Ghi nhớ:** `byte` của Java luôn có dấu, nhưng **mẫu 8 bit của nó vẫn giữ nguyên**. Mặt nạ `& 0xFF` hoặc `Byte.toUnsignedInt(b)` chuyển cách diễn giải mẫu đó thành một `int` từ 0 đến 255. Khi làm việc với file/mạng, luôn phân biệt **giá trị byte dữ liệu** với **giá trị điều khiển như EOF** và kiểm tra miền nếu cần.

**Tài liệu tham khảo:** [Java Language Specification §4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.1); [§5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2); [§15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.22); [Byte.toUnsignedInt API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Byte.html#toUnsignedInt(byte)); [InputStream.read API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html#read()).

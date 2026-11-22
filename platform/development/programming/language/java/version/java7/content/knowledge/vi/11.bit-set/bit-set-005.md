# `BitSet` trong Java: Quy ước thứ tự bit và biểu diễn little-endian

## 1. Mục tiêu: cùng một dãy byte, tại sao người đọc hiểu nhầm vị trí bit?

`java.util.BitSet` là một tập hợp các giá trị boolean được đánh chỉ số bằng số nguyên **không âm**, bắt đầu từ `0`. Nó đặc biệt hữu ích khi cần lưu hoặc thao tác nhiều cờ bật/tắt, tập hợp các chỉ số, hoặc phép toán bit `and`, `or`, `xor`.

Từ Java 7, `BitSet` có các API nhập/xuất mảng byte hoặc long:

- `BitSet.valueOf(byte[])` và `BitSet.valueOf(long[])`: tạo bit set từ **biểu diễn little-endian**.
- `BitSet.valueOf(ByteBuffer)` và `BitSet.valueOf(LongBuffer)`: tạo bit set từ phần tử nằm giữa `position` và `limit` của buffer tương ứng.
- `toByteArray()` và `toLongArray()`: xuất dữ liệu thành **biểu diễn little-endian** với độ dài vừa đủ chứa bit `true` cao nhất.

Dễ mắc lỗi ở ba vấn đề riêng biệt:

1. **Bit index:** `get(0)` là bit có trọng số thấp nhất (*least significant bit*, LSB) của byte đầu tiên, **không phải** ký tự `'1'`/`'0'` ở bên trái khi hiển thị chuỗi nhị phân.
2. **Byte order:** byte có chỉ số `0` mang các bit `0..7`, byte có chỉ số `1` mang các bit `8..15`, tiếp tục từ thấp lên cao. Đó là ý nghĩa little-endian của biểu diễn byte trong `BitSet`.
3. **Độ dài biểu diễn:** `BitSet` không nhớ số lượng byte `0` ở đầu có trọng số cao (phía **cuối** của mảng little-endian). Khi xuất, những byte `0` không cần thiết bị lược bỏ. Vì vậy xuất rồi nhập lại thường giữ **giá trị các bit**, nhưng không nhất thiết giữ **độ dài byte gốc**.

Những quy tắc này còn nguyên giá trị trong Java 17+ và Java hiện đại. Các API chuyển đổi byte/long được thêm từ Java 7, trong khi lớp `BitSet` đã tồn tại trước đó.

## 2. Bit index bắt đầu từ 0: bit thấp nhất của byte đầu tiên

### 2.1. Một byte có tám bit, nhưng cách viết nhị phân thường đi từ bit cao tới bit thấp

Giả sử byte có giá trị hexa `0x05`, dạng nhị phân được viết quen thuộc:

```text
Byte value: 0x05
Cách hiển thị nhị phân (MSB bên trái):
         0 0 0 0 0 1 0 1
Bit số:  7 6 5 4 3 2 1 0
                        ^ bit 0 là cột bên phải
```

Bit mang giá trị `1` ở vị trí **0** và **2**. Nếu đây là byte **đầu tiên** được nạp vào `BitSet`:

```java
BitSet bits = BitSet.valueOf(new byte[]{0x05});

System.out.println(bits);       // {0, 2}
System.out.println(bits.get(0)); // true
System.out.println(bits.get(1)); // false
System.out.println(bits.get(2)); // true
```

Đây là **đoạn minh họa bên trong phương thức** có `import java.util.BitSet;`, không phải tệp Java độc lập.

**Không đọc từ trái sang phải** rồi gán ký tự đầu tiên cho `BitSet.get(0)`. Chuỗi `"00000101"` thường hiển thị **bit 7 trước, bit 0 sau**.

### 2.2. Bước sang byte thứ hai

Với hai byte:

```text
Thứ tự trong byte[]:       bytes[0] = 0x05    bytes[1] = 0x81
Dạng nhị phân MSB→LSB:      00000101          10000001
Bit index trong BitSet:     7 ... 0           15 ... 8
Những bit bằng 1:          {0, 2}            {8, 15}
Toàn bộ BitSet:             {0, 2, 8, 15}
```

`0x81` mang bit thấp nhất và bit cao nhất của chính byte đó. Vì là byte thứ hai (chỉ số 1), hai bit tương ứng trong `BitSet` là **8** và **15**, không phải 0 và 7.

```java
byte[] encoded = {0x05, (byte) 0x81};
BitSet flags = BitSet.valueOf(encoded);

System.out.println(flags);        // {0, 2, 8, 15}
System.out.println(flags.get(8)); // true
System.out.println(flags.get(15));// true
System.out.println(flags.get(7)); // false
```

`(byte) 0x81` cần phép ép kiểu vì `0x81` (129) nằm ngoài phạm vi giá trị `byte` có dấu của Java (−128 đến 127). Khi xét bit, **cùng một mẫu tám bit `10000001`** vẫn được giữ nguyên. Đừng suy ra vị trí bit từ giá trị số âm hiển thị của `byte`.

## 3. Công thức ánh xạ byte ↔ bit được đặc tả chính thức

Với một mảng `byte[] bytes`, bit có chỉ số `n` trong `BitSet.valueOf(bytes)` được xác định bởi:

```java
boolean set = (bytes[n / 8] & (1 << (n % 8))) != 0;
```

Công thức áp dụng cho `0 <= n < 8 * bytes.length`. Nó mô tả chính xác ý nghĩa của `BitSet.valueOf(byte[])` theo tài liệu Java API.

| Thành phần | Vai trò | Ví dụ với `n=15` |
| --- | --- | --- |
| `n / 8` | Vị trí **byte** chứa bit, chia nguyên | `15 / 8 = 1` |
| `n % 8` | Vị trí **bit bên trong byte** (0..7) | `15 % 8 = 7` |
| `1 << (n % 8)` | Mặt nạ chọn bit trong byte | `1 << 7 = 0x80` |
| `bytes[n / 8] & mask` | Kiểm tra bit có bật không | `0x81 & 0x80 != 0` |

Vì vậy, ánh xạ tổng quát từ cặp chỉ số `byteIndex` và `bitWithinByte` là:

```text
globalBitIndex = 8 * byteIndex + bitWithinByte

0 <= bitWithinByte <= 7
```

**Điều cần nhớ:** Trong `BitSet`, byte đầu tiên chứa **các chỉ số bit thấp**, và trong mỗi byte, **bit có trọng số thấp nhất có chỉ số thấp nhất**.

### 3.1. Java `byte` có dấu không làm sai phép kiểm tra bit

`byte` là kiểu có dấu, nên `(byte) 0x81` đọc dưới dạng số nguyên là `-127`. Khi áp dụng phép toán bit, Java thực hiện numeric promotion sang `int`, nhưng phép `&` với một mask của bit thấp phù hợp vẫn cho đúng kết quả.

Để in byte theo hexa hai chữ số, dùng mask rõ ràng:

```java
byte value = (byte) 0x81;
System.out.printf("%02X%n", value & 0xFF); // 81
```

Nếu không có `& 0xFF`, việc format giá trị `byte` đã sign-extend có thể làm kết quả hiển thị không phải dạng hai chữ số mà bạn muốn. Để giao tiếp với API nhị phân, **mẫu bit trên byte** quan trọng hơn việc Java in giá trị signed như thế nào.

### 3.2. `BitSet.set(n)` dùng cùng hệ chỉ số

```java
BitSet bits = new BitSet();
bits.set(0);
bits.set(2);
bits.set(8);
bits.set(15);

System.out.println(bits); // {0, 2, 8, 15}
```

Nếu dùng `bits.toByteArray()`, kết quả về mặt nội dung là `05 81`. Bạn có thể hiểu `set(15)` tương đương bật bit `7` trong byte thứ `1` của một biểu diễn little-endian.

**Đừng đồng nhất biểu diễn `BitSet.toString()` với chuỗi nhị phân.** `toString()` liệt kê **chỉ số các bit `true`**, theo dạng `{0, 2, 8, 15}`, không in ra toàn bộ dãy tám bit của từng byte.

## 4. Little-endian của `byte[]`: byte đầu chứa các bit có trọng số thấp

Giả sử hai byte `34 12` được dùng làm biểu diễn little-endian cho một giá trị 16-bit:

```text
Mảng byte theo thứ tự bộ nhớ:       34 12
Byte thấp nhất / byte index 0:      0x34
Byte tiếp theo / byte index 1:      0x12

Giá trị số nếu coi là unsigned 16-bit: 0x1234
BitSet.valueOf(new byte[]{0x34, 0x12})
Các bit bằng 1: {2, 4, 5, 9, 12}
```

Giải thích:

- `0x34 = 00110100`: các bit bên trong byte đầu tiên bằng `1` tại vị trí `2,4,5`.
- `0x12 = 00010010`: các bit bên trong byte thứ hai bằng `1` tại vị trí `1,4`, nên các chỉ số toàn cục là `9,12`.
- Tập hợp kết quả là `{2,4,5,9,12}`.

Đây chính là nghĩa little-endian khi `BitSet` chuyển giữa **bit indices** và **byte array**. **Không đảo bit trong từng byte** chỉ vì thấy từ little-endian; bit thứ `0` vẫn là bit LSB của byte đầu.

### 4.1. Little-endian không đồng nghĩa “chuỗi bit đọc từ trái sang phải”

Có ít nhất hai khái niệm độc lập cần khai báo khi trao đổi dữ liệu:

1. **Byte order (endianness):** nếu một giá trị trải trên nhiều byte, byte có trọng số thấp nhất xuất hiện ở vị trí nào?
2. **Bit numbering trong byte:** bit được gọi là `0` là LSB hay MSB của byte?
3. **Bit transmission order (nếu có):** trong giao thức truyền nối tiếp, bit nào thực sự được gửi trước?

`BitSet.valueOf(byte[])` xác định rõ **hai quy ước đầu tiên** cho mục đích ánh xạ bit index: byte thứ `0` chứa indices 0..7; trong byte, bit LSB có index nhỏ nhất. Nó **không tự quy định** giao thức vật lý nào truyền byte/bit trước.

Một số chuẩn đặt “bit 0” là MSB của byte đầu, hoặc gán số bit theo network diagram từ trái sang phải. Đó là **quy ước khác**, và không thể trực tiếp dùng `BitSet.get(0)` để chỉ “bit nằm ngoài cùng bên trái” nếu chưa chuyển đổi.

### 4.2. Ví dụ trường hợp MSB-first trong một byte

```java
BitSet bits = BitSet.valueOf(new byte[]{(byte) 0x80});

System.out.println(bits.get(0)); // false
System.out.println(bits.get(7)); // true
```

Bit đầu tiên nhìn thấy khi viết chuỗi nhị phân `10000000` là **bit 7**, không phải bit 0, theo quy ước của `BitSet`.

Nếu định dạng giao thức đánh số bit `0` từ MSB, cần một bước **chuyển đổi số bit trong byte**. Chẳng hạn, với logical index của giao thức `p` từ 0..7, chỉ số tương ứng của `BitSet` trong cùng byte là `7-p`; với byte index `i`, chỉ số toàn cục là `8*i + (7-p)`. Đừng đảo byte order nếu vấn đề thực sự chỉ là quy ước **MSB-first trong từng byte**.

## 5. `toByteArray()`: little-endian và không giữ byte `0` ở cuối

### 5.1. Dữ liệu xuất được rút gọn theo bit cao nhất bằng `true`

Với:

```java
byte[] input = {0x05, (byte) 0x81, 0x00};
BitSet bits = BitSet.valueOf(input);
byte[] output = bits.toByteArray();
```

`BitSet` chứa các bit `{0,2,8,15}`. Mảng input có **ba byte**, nhưng vì byte thứ ba là `0x00` và không mang bit `true`, `output` chỉ có **hai byte**:

```text
input  = 05 81 00
output = 05 81
```

Theo Java API:

```java
output.length == (bits.length() + 7) / 8
```

Ở đây `bits.length() == 16` (bit `true` cao nhất là 15, cộng một), nên `output.length == 2`.

**Không nhầm `BitSet.length()` với số bit đã cấp phát ban đầu.** Nó là `highestSetBit + 1`, hoặc `0` nếu tất cả bit đều false. Với `new BitSet(1000)`, nếu chưa set bit nào, `length()` vẫn là `0`; constructor chỉ có gợi ý về sức chứa khởi tạo, không làm 1000 bit thành `true`.

### 5.2. Ba chỉ số kích thước không giống nhau

| API/giá trị | Diễn giải | Ví dụ `{0,2,8,15}` |
| --- | --- | --- |
| `bits.cardinality()` | Số bit bằng `true` | `4` |
| `bits.length()` | Chỉ số bit `true` cao nhất + 1 | `16` |
| `bits.size()` | Số bit không gian **đang được sử dụng để biểu diễn** theo implementation | Không nên dựa vào giá trị cố định để serialize |
| `bits.toByteArray().length` | Số byte nhỏ nhất cần để chứa bit true cao nhất | `2` |
| `input.length` | Số byte của định dạng hoặc buffer ban đầu | `3` |

`BitSet.size()` có thể liên quan tới chiến lược cấp phát nội bộ và thay đổi khi implementation hoặc trạng thái thay đổi; **không dùng `size()` làm số bit có ý nghĩa của giao thức**.

### 5.3. Giữ độ dài byte cố định khi giao thức yêu cầu

Nếu một protocol cần đúng **ba byte**, hãy lưu độ dài bên ngoài `BitSet` và thêm byte `0` ở phần có trọng số cao (cuối mảng little-endian):

```java
int requiredBytes = 3;
byte[] fixedWidth = Arrays.copyOf(
        bits.toByteArray(), requiredBytes);
```

Ví dụ kết quả: `05 81 00`. Đây là **đoạn minh họa** cần import `java.util.Arrays`.

**Nhớ kiểm tra đủ sức chứa trước khi cắt/gói dữ liệu.** Nếu bit true cao nhất không vừa trong số byte giao thức cho phép, `Arrays.copyOf` với kích thước nhỏ sẽ **cắt mất dữ liệu**, không báo lỗi tự động.

Một helper minh họa an toàn hơn:

```java
static byte[] toFixedWidth(BitSet bits, int byteCount) {
    if (byteCount < 0 || byteCount > Integer.MAX_VALUE / 8) {
        throw new IllegalArgumentException("invalid byte count");
    }
    if (bits.length() > byteCount * 8) {
        throw new IllegalArgumentException("bit set exceeds field width");
    }
    return Arrays.copyOf(bits.toByteArray(), byteCount);
}
```

Đây là phương thức **đặt trong lớp có import BitSet/Arrays**. Nó bảo đảm byteCount hợp lệ và không lặng lẽ làm mất các bit đã set. Trong giao thức có yêu cầu độ dài byte đặc biệt, các ràng buộc đó cần được kiểm tra riêng.

### 5.4. Round-trip bảo đảm giá trị bit, không bảo đảm số byte ban đầu

Đối với một `BitSet` bất kỳ `s`:

```java
BitSet decoded = BitSet.valueOf(s.toByteArray());
System.out.println(decoded.equals(s)); // true
```

Các bit có giá trị `true` được bảo toàn. Nhưng với byte array input có phần byte `0` ở cuối, `Arrays.equals(input, s.toByteArray())` có thể là `false` vì `BitSet` **không lưu độ rộng cố định**.

Với bitset rỗng (không bit nào true), `new BitSet().toByteArray()` trả về **mảng byte rỗng**, không phải một byte `0x00`.

## 6. `long[]`: 64 bit mỗi phần tử, cùng quy ước little-endian

API thứ hai là `BitSet.valueOf(long[])`. Tại đây, một phần tử `long` chứa **64 bit**, và phần tử có chỉ số `0` lưu các bit từ `0` đến `63`.

Công thức đặc tả:

```java
boolean set = (longs[n / 64] & (1L << (n % 64))) != 0;
```

Áp dụng cho `0 <= n < 64 * longs.length`.

| Chỉ số | Nằm trong phần tử long | Bit trong long |
| --- | --- | --- |
| `0` | `longs[0]` | `0` (LSB) |
| `63` | `longs[0]` | `63` (MSB) |
| `64` | `longs[1]` | `0` |
| `65` | `longs[1]` | `1` |
| `127` | `longs[1]` | `63` |

Ví dụ:

```java
BitSet flags = BitSet.valueOf(
        new long[]{Long.MIN_VALUE, 2L});

System.out.println(flags);                     // {63, 65}
System.out.println(flags.toLongArray().length); // 2
```

`Long.MIN_VALUE` mang **bit 63** bằng `1` trong `longs[0]`; `2L` mang **bit 1** trong `longs[1]`, nên index toàn cục là `64 + 1 = 65`.

`toLongArray()` cũng xuất little-endian theo **thứ tự các word 64-bit**, và số word nhỏ nhất cần là:

```java
int words = (flags.length() + 63) / 64;
```

Khi đưa cùng bitset qua `toByteArray()`, các bit `{63,65}` tạo chín byte:

```text
00 00 00 00 00 00 00 80 02
```

Tám byte đầu biểu diễn word `Long.MIN_VALUE` dưới dạng little-endian, và byte thứ chín chứa bit `65` trong nhóm byte có index `8`.

**Phân biệt:** Với `long[]`, “little-endian” nói **thứ tự các long-words trong dãy** và thứ tự các bit trong từng long. Một giá trị `long` của Java không tự có byte order khi nằm trong một phần tử `long[]`; byte order chỉ phát sinh khi bạn encode chính `long` thành các byte bằng một API như `ByteBuffer`.

## 7. `ByteBuffer`, `LongBuffer` và bẫy `ByteOrder`

### 7.1. `BitSet.valueOf(ByteBuffer)` lấy đúng phần dữ liệu còn lại

```java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[]{0x55, 0x02, (byte) 0x80, 0x66});

buffer.position(1);
buffer.limit(3);

BitSet bits = BitSet.valueOf(buffer);
System.out.println(bits);              // {1, 15}
System.out.println(buffer.position()); // 1
```

Ở ví dụ này, `ByteBuffer` có bốn byte nhưng miền còn lại từ `position=1` đến trước `limit=3` chỉ gồm:

```text
02 80
```

`0x02` có bit thấp `1`; `0x80` là byte thứ hai của **miền đang xem**, nên bit `7` của nó thành chỉ số toàn cục `15`. Byte `0x55` ở đầu và `0x66` ở sau giới hạn đều bị bỏ qua.

Theo Java API, `BitSet.valueOf(ByteBuffer)`:

- Đọc từ vị trí `position` đến **trước** `limit` (chỉ số vị trí tương ứng trong buffer).
- Không làm thay đổi `position` hoặc `limit` của buffer được truyền.
- Không giữ tham chiếu tới buffer sau khi tạo bitset: việc sửa nội dung buffer về sau không tự thay đổi BitSet đã tạo.
- Đánh chỉ số bit `0` cho **bit thấp nhất của byte đầu tiên trong vùng còn lại**, không phải bit 0 của toàn bộ buffer gốc.

### 7.2. Vì sao `ByteBuffer.order(BIG_ENDIAN)` không đổi cách `valueOf(ByteBuffer)` diễn giải?

`ByteBuffer.order(ByteOrder.BIG_ENDIAN)` hoặc `LITTLE_ENDIAN` điều khiển cách các thao tác đọc/ghi **kiểu nhiều byte** như `getShort()`, `getInt()` và `getLong()` diễn giải byte.

Nhưng `BitSet.valueOf(ByteBuffer)` được Java API **định nghĩa trực tiếp trên từng byte**:

```java
BitSet.valueOf(bb).get(n) ==
        ((bb.get(bb.position() + n / 8)
                & (1 << (n % 8))) != 0)
```

Vì vậy, nếu **cùng chuỗi byte, cùng position/limit**, việc đặt `bb.order(ByteOrder.BIG_ENDIAN)` rồi đổi sang `LITTLE_ENDIAN` **không làm thay đổi `BitSet` nhận được**. API luôn dùng cách ánh xạ little-endian của riêng `BitSet`.

```java
ByteBuffer buffer = ByteBuffer.wrap(new byte[]{0x02, (byte) 0x80});

buffer.order(ByteOrder.BIG_ENDIAN);
BitSet first = BitSet.valueOf(buffer);

buffer.order(ByteOrder.LITTLE_ENDIAN);
BitSet second = BitSet.valueOf(buffer);

System.out.println(first.equals(second)); // true
```

Đây là đoạn minh họa có import `java.nio.ByteBuffer`, `java.nio.ByteOrder` và `java.util.BitSet`.

**Điểm rất dễ nhầm:** Nếu bạn dùng `ByteBuffer.getLong()`, `ByteBuffer.asLongBuffer()` hoặc một thao tác biến byte thành long **trước khi** gọi `BitSet.valueOf(long[])`, thì `ByteOrder` của bước chuyển đổi byte→long **có thể thay đổi giá trị long**. Quy tắc "đổi order không ảnh hưởng" ở trên chỉ dành cho việc đọc **cùng byte stream** bằng `BitSet.valueOf(ByteBuffer)`, không áp dụng cho mọi pipeline chuyển đổi trung gian.

## 8. Chuyển đổi khi dữ liệu đến từ giao thức big-endian

### 8.1. Nếu giao thức định nghĩa số nguyên big-endian

Giả sử hai byte trên mạng là:

```text
12 34
```

Theo quy ước **big-endian cho unsigned 16-bit integer**, giá trị là `0x1234`. Nhưng truyền trực tiếp:

```java
BitSet wrongForBigEndian = BitSet.valueOf(
        new byte[]{0x12, 0x34});
```

sẽ diễn giải các byte ấy theo quy tắc **little-endian của BitSet**, tương đương việc đặt byte `0x12` ở phần thấp rồi byte `0x34` ở phần cao. Những bit true sẽ là:

```text
{1, 4, 10, 12, 13}
```

Nếu mục đích là tái hiện **các vị trí bit của giá trị số 0x1234** với bit `0` là LSB của số đó, cần đảo thứ tự **hai byte**:

```java
byte[] bigEndian = {0x12, 0x34};
byte[] littleEndian = {bigEndian[1], bigEndian[0]};

BitSet correct = BitSet.valueOf(littleEndian);
System.out.println(correct); // {2, 4, 5, 9, 12}
```

Mã này chuyển **byte order của một giá trị số nhiều byte**. Nó không đảo bit trong từng byte vì quy ước về bit `0` vẫn là LSB của số.

### 8.2. Nếu giao thức đánh số bit theo MSB-first

Một số giao thức đánh số "bit 0" là **MSB của byte đầu**, thay vì LSB của giá trị. Khi đó, **chỉ đảo byte order vẫn không đủ**: bạn còn phải chuyển quy ước **bit numbering**.

Ví dụ một byte `0x80`:

- Theo tài liệu giao thức MSB-first, "bit 0" có thể là bit đang bật.
- Trong `BitSet`, `BitSet.valueOf(new byte[]{(byte) 0x80}).get(7) == true`.
- Để biểu diễn "bit 0" theo cách của giao thức, hoặc dùng công thức chuyển index, hoặc đặt một lớp ánh xạ ở biên dữ liệu. Đừng âm thầm thay đổi cách đánh số ở các tầng khác nhau.

**Hỏi rõ định dạng dữ liệu trước khi chuyển đổi:** byte order, bit numbering, độ dài trường, dấu/không dấu, thứ tự truyền và padding có thể là những thuộc tính độc lập của giao thức.

### 8.3. Có cần `ByteBuffer.order(LITTLE_ENDIAN)` trước khi nạp vào `BitSet` không?

**Không cần** nếu sử dụng trực tiếp `BitSet.valueOf(ByteBuffer)`: phương thức đã định nghĩa cách giải thích byte little-endian. Việc set `ByteOrder` chỉ cần khi bạn **tự đọc/ghi các primitive nhiều byte** hoặc dựng buffer theo định dạng mà giao thức yêu cầu.

Đừng nhầm "byte order" với thứ tự các ký tự trong chuỗi hexa: `34 12` là thứ tự hai byte, mỗi byte `0x34`/`0x12` vẫn được viết bằng hai chữ số hexa theo quy ước ký hiệu thông thường.

## 9. Chương trình Java 17+ đầy đủ: kiểm chứng tất cả quy ước

Chương trình chạy độc lập sau minh họa:

- Bit index của dữ liệu `05 81 00` và danh sách bit true.
- Số byte bị lược khi xuất `toByteArray()`, cách khôi phục độ dài cố định, và round-trip.
- Mảng `long[]` với các bit ở vị trí `63` và `65`.
- `ByteBuffer.position()/limit()` và việc đổi `ByteOrder` không làm đổi `BitSet.valueOf(ByteBuffer)`.
- Chuyển hai byte big-endian thành little-endian để giữ các vị trí bit của số 16-bit.
- Bit MSB trong byte ứng với index `7` của `BitSet`.
- Một vài assertion thật sự bằng `AssertionError` khi hành vi khác mong đợi.

Tạo tệp **`BitSetLittleEndianDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;
import java.util.BitSet;
import java.util.StringJoiner;

public final class BitSetLittleEndianDemo {

    static String hex(byte[] bytes) {
        StringJoiner result = new StringJoiner(" ");
        for (byte value : bytes) {
            result.add(String.format("%02X", value & 0xFF));
        }
        return result.toString();
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        byte[] source = {(byte) 0x05, (byte) 0x81, (byte) 0x00};
        BitSet flags = BitSet.valueOf(source);

        System.out.println("bytes=" + hex(source));
        System.out.println("setBits=" + flags);
        System.out.println("get(2)=" + flags.get(2));
        System.out.println("get(7)=" + flags.get(7));
        System.out.println("get(15)=" + flags.get(15));
        System.out.println("logicalLength=" + flags.length());
        System.out.println("count=" + flags.cardinality());
        System.out.println("serialized=" + hex(flags.toByteArray()));
        System.out.println("serializedBytes="
                + flags.toByteArray().length);
        System.out.println("roundTrip="
                + BitSet.valueOf(flags.toByteArray()).equals(flags));
        System.out.println("fixedWidth="
                + hex(Arrays.copyOf(flags.toByteArray(), source.length)));

        source[0] = 0;
        System.out.println("afterSourceEdit=" + flags);

        BitSet fromLongs = BitSet.valueOf(
                new long[]{Long.MIN_VALUE, 2L});
        System.out.println("longBits=" + fromLongs);
        System.out.println("longWords="
                + fromLongs.toLongArray().length);
        System.out.println("longBytes="
                + hex(fromLongs.toByteArray()));

        ByteBuffer view = ByteBuffer.wrap(
                new byte[]{0x55, 0x02, (byte) 0x80, 0x66});
        view.position(1);
        view.limit(3);
        view.order(ByteOrder.BIG_ENDIAN);

        BitSet fromBuffer = BitSet.valueOf(view);
        System.out.println("bufferBits=" + fromBuffer);
        System.out.println("bufferPos=" + view.position());

        view.order(ByteOrder.LITTLE_ENDIAN);
        System.out.println("bufferOrderIndependent="
                + fromBuffer.equals(BitSet.valueOf(view)));

        byte[] networkBigEndian = {0x12, 0x34};
        System.out.println("bigEndianRaw="
                + BitSet.valueOf(networkBigEndian));
        System.out.println("bigEndianConverted="
                + BitSet.valueOf(new byte[]{
                    networkBigEndian[1], networkBigEndian[0]}));

        System.out.println("msbBit7="
                + BitSet.valueOf(new byte[]{(byte) 0x80}).get(7));
        System.out.println("emptyBytes="
                + new BitSet().toByteArray().length);

        check(flags.get(0) && flags.get(2)
                && flags.get(8) && flags.get(15),
                "bit index mapping");

        check(Arrays.equals(new byte[]{0x05, (byte) 0x81},
                flags.toByteArray()),
                "minimal little-endian output");

        check(fromLongs.get(63) && fromLongs.get(65)
                && !fromLongs.get(64),
                "long word mapping");

        check(view.position() == 1 && view.limit() == 3,
                "ByteBuffer unchanged");

        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc Java mới hơn:

```bash
javac BitSetLittleEndianDemo.java
java BitSetLittleEndianDemo
```

**Stdout chính xác:**

```text
bytes=05 81 00
setBits={0, 2, 8, 15}
get(2)=true
get(7)=false
get(15)=true
logicalLength=16
count=4
serialized=05 81
serializedBytes=2
roundTrip=true
fixedWidth=05 81 00
afterSourceEdit={0, 2, 8, 15}
longBits={63, 65}
longWords=2
longBytes=00 00 00 00 00 00 00 80 02
bufferBits={1, 15}
bufferPos=1
bufferOrderIndependent=true
bigEndianRaw={1, 4, 10, 12, 13}
bigEndianConverted={2, 4, 5, 9, 12}
msbBit7=true
emptyBytes=0
checks=PASS
```

Đây là **chương trình độc lập hoàn chỉnh**, không cần thư viện bên ngoài. Các đoạn code rời ở mục khác chỉ minh họa một quy tắc và phải đặt trong lớp/phương thức hoặc import thích hợp trước khi biên dịch.

### 9.1. Giải thích các kết quả cần nhớ

- `setBits={0, 2, 8, 15}`: hai byte đầu `05 81` mang đúng bốn bit true.
- `get(2)=true`, `get(7)=false`, `get(15)=true`: xác nhận bit index theo LSB và byte offset.
- `logicalLength=16`: bit true cao nhất là `15` nên chiều dài logic là `16`.
- `count=4`: `cardinality()` đếm số bit true, không đếm số byte hay chiều dài logic.
- `serialized=05 81` và `serializedBytes=2`: phần byte `00` ở cuối mảng nguồn không còn trong bản xuất tối thiểu.
- `roundTrip=true`: nội dung bit được bảo toàn khi dùng `BitSet.valueOf(flags.toByteArray())`.
- `fixedWidth=05 81 00`: dùng độ dài ngoài là 3 byte để khôi phục padding theo đúng chiều little-endian.
- `afterSourceEdit={0, 2, 8, 15}`: `BitSet.valueOf(byte[])` tạo trạng thái bitset riêng, không tiếp tục tham chiếu mảng input để nhận thay đổi tự động.
- `longBits={63, 65}`, `longWords=2` và chín byte ở `longBytes`: long word đầu chứa bit 63, word sau chứa bit 65.
- `bufferBits={1, 15}` và `bufferPos=1`: chỉ lấy miền buffer còn lại, không tự dời vị trí buffer của caller.
- `bufferOrderIndependent=true`: cùng nội dung byte, `ByteOrder` của buffer không đổi cách `BitSet.valueOf(ByteBuffer)` suy ra bit.
- `bigEndianRaw` khác `bigEndianConverted`: đảo byte khi nguồn mô tả một giá trị nhiều byte big-endian.
- `msbBit7=true`: bit cao nhất của byte đầu tương ứng `BitSet.get(7)`.
- `emptyBytes=0`: bitset rỗng xuất ra mảng rỗng.
- `checks=PASS`: các khẳng định trong chương trình đều đã kiểm tra thành công; nếu sai, chương trình ném `AssertionError`.

## 10. Quy trình làm việc với dữ liệu nhị phân thật

### Bước 1 — Xác định "bit 0" trong tài liệu dữ liệu

Trước khi dùng `BitSet`, ghi rõ:

- Bit 0 là LSB của toàn bộ số hay MSB của byte đầu?
- Byte đầu là byte có trọng số thấp hay trọng số cao?
- Tổng độ dài trường là bao nhiêu bit hoặc byte?
- Phần còn lại của byte cuối là padding và phải bằng `0`, hay chứa dữ liệu khác?
- Dữ liệu là một **bit field** có nhiều cờ, hay một **số nguyên không dấu** cần giải mã thành một giá trị số?
- Với một protocol, thứ tự truyền bit/byte được quy định ra sao?

Nếu chỉ nói “bit 0” mà không chỉ rõ quy ước, hai thành phần có thể xử lý cùng dữ liệu thành hai bộ cờ khác nhau.

### Bước 2 — Chuyển đổi byte order nếu khác quy ước của `BitSet`

Nếu nguồn đã little-endian và bit numbering LSB-first, có thể dùng trực tiếp `BitSet.valueOf(bytes)`.

Nếu nguồn là số big-endian, cần đảo thứ tự các byte trong **phạm vi trường** hoặc đọc giá trị bằng API có `ByteOrder.BIG_ENDIAN` rồi chuyển sang các bit theo quy ước đã chọn. Với nhiều trường ghép trong một packet, **không đảo toàn bộ packet**; chỉ chuyển những trường cần chuyển, tránh phá vỡ cấu trúc.

Nếu nguồn MSB-first trong mỗi byte, chuyển **index bit trong từng byte** một cách tường minh. Việc đảo byte order và đảo bit order là **hai phép biến đổi khác nhau**.

### Bước 3 — Làm việc trong `BitSet` bằng chỉ số không âm

```java
BitSet flags = new BitSet();
flags.set(0);
flags.set(8);
flags.clear(8);
boolean enabled = flags.get(0);
```

Trong `BitSet`, index là địa chỉ logic ổn định và không phụ thuộc chuỗi hiển thị nhị phân. `set(from, to)` sử dụng đoạn **[from, to)**, tức `from` bao gồm còn `to` loại trừ.

Nên dùng các hằng số tên rõ nghĩa:

```java
static final int FLAG_READ = 0;
static final int FLAG_WRITE = 2;

BitSet permissions = new BitSet();
permissions.set(FLAG_READ);
permissions.set(FLAG_WRITE);
```

Đây là đoạn minh họa trong ngữ cảnh lớp/phương thức. Không dùng phép dịch và mask rải rác nếu đã chọn `BitSet` làm mô hình chính cho bộ cờ.

### Bước 4 — Xuất dữ liệu theo độ dài, padding và endian mà API đích yêu cầu

Sau khi xử lý, `toByteArray()` trả little-endian tối thiểu. Nếu đích cần trường có độ rộng cố định, thêm padding **về phía byte trọng số cao**, đồng thời kiểm tra không có bit true vượt độ dài cho phép.

Nếu đích cần big-endian, chuyển thứ tự byte lại sau khi đã áp dụng độ rộng cố định thích hợp. **Đừng đảo thứ tự trước khi padding**, vì padding là một phần của quy ước kích thước trường và dễ đặt vào sai phía.

Với giao thức MSB-first, còn cần ánh xạ bit numbering phù hợp trước khi serialize; không chỉ dựa vào `ByteBuffer.order()`.

### Bước 5 — Kiểm thử bằng giá trị có bit ở cả hai đầu mỗi byte

Dữ liệu toàn `00` hoặc toàn `FF` **không đủ** để phát hiện nhiều lỗi thứ tự. Ví dụ `05 81` có bit true ở đầu thấp và đầu cao của các byte, giúp phát hiện ánh xạ sai một cách trực quan.

Thêm các ca biên:

- Bit `0`, `7`, `8`, `15` để kiểm tra ranh giới byte.
- Bit `63`, `64`, `65` để kiểm tra ranh giới long word.
- Byte có bit `7` bằng `1` (giá trị signed âm của `byte`).
- Các byte `00` ở phía trọng số cao để kiểm tra padding.
- Buffer có `position != 0` và `limit < capacity`.
- Đầu vào rỗng, toàn bit false và một bit true ở vị trí cao.
- Dữ liệu nguồn theo big-endian và little-endian, thêm trường MSB-first nếu protocol yêu cầu.

**Test đúng phải so cả vị trí bit và chuỗi byte xuất**, không chỉ thấy số lượng bit true khớp.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi ký tự bên trái nhất của `"10000000"` là `BitSet.get(0)` | Đọc sai bit, nhầm index `0` với `7` | Xác định rõ LSB/MSB; `0x80` bật `get(7)` |
| Coi byte đầu là các bit cao nhất | Đảo nghĩa byte order | Với `valueOf(byte[])`, byte đầu là bits `0..7` |
| Dùng `BitSet.valueOf(bigEndianBytes)` trực tiếp cho số big-endian | Byte nhiều trọng số cao bị xem ở vị trí thấp | Đổi thứ tự byte theo phạm vi trường |
| Tưởng `ByteBuffer.order(BIG_ENDIAN)` đổi nghĩa `BitSet.valueOf(buffer)` | Không đổi như mong đợi | Chuyển dữ liệu byte trước hoặc dùng phương thức đọc số phù hợp |
| In Java `byte` âm rồi tưởng bit dữ liệu âm/sai | Hiển thị khó hiểu | Dùng `value & 0xFF` và format `%02X` |
| Dùng `BitSet.size()` làm kích thước bản tin | Phụ thuộc sức chứa nội bộ | Lưu độ dài giao thức riêng |
| Nghĩ `length()` là số bit true | Sai khi bit true thưa | `cardinality()` đếm true bits, `length()` là highest index +1 |
| Trông đợi `toByteArray()` giữ byte `00` cuối input | Mất padding/độ dài cố định | Lưu byteCount ngoài, thêm padding khi xuất |
| Tạo fixed-width bằng `Arrays.copyOf` nhưng không kiểm tra tràn | Cắt mất bit true ở vị trí cao | Kiểm tra `bits.length() <= 8 * byteCount` |
| Dùng `BitSet.toString()` làm bản mã hóa wire | Chuỗi `{0, 2}` không phải bytes | Dùng `toByteArray()` và protocol rõ ràng |
| Cho rằng `valueOf(ByteBuffer)` đọc toàn bộ capacity | Lấy sai vùng dữ liệu | Hiểu `position..limit`, kiểm tra khi cần |
| Cho rằng `valueOf(byte[])` giữ tham chiếu mảng gốc | Dựa vào cập nhật tự lan truyền | API tạo bitset riêng; kiểm thử sau khi sửa input |
| Chỉ đảo bit, không đảo byte cho số big-endian | Ánh xạ sai giá trị nhiều byte | Phân tách byte order và bit numbering |
| Dùng dữ liệu toàn `00`/`FF` để test endian | Không phát hiện đảo thứ tự | Dùng mẫu phân biệt như `05 81`, `12 34` |

## 12. Câu hỏi ôn tập

**Câu 1.** Với `byte[]{0x01, 0x02}`, các bit `true` là những index nào?  
**Đáp án:** `{0, 9}`. Byte đầu bật bit 0, byte thứ hai có bit thấp số 1 nên index toàn cục là `8+1=9`.

**Câu 2.** Với `byte[]{(byte) 0x80}`, `get(0)` và `get(7)` có giá trị gì?  
**Đáp án:** `get(0) == false`, `get(7) == true`. Trong `BitSet`, bit 0 là LSB.

**Câu 3.** `BitSet.valueOf(new byte[]{0x05, (byte)0x81, 0x00}).toByteArray()` có bao nhiêu byte?  
**Đáp án:** `2` byte, nội dung `05 81`. Byte `00` phía có trọng số cao đã bị bỏ vì không mang bit true nào.

**Câu 4.** Thay `ByteBuffer.order(BIG_ENDIAN)` thành `LITTLE_ENDIAN` có làm thay đổi `BitSet.valueOf(ByteBuffer)` của cùng byte sequence không?  
**Đáp án:** Không. API ánh xạ trực tiếp các byte theo quy ước little-endian riêng; `ByteOrder` chỉ ảnh hưởng các thao tác nhiều byte thực hiện trên buffer.

**Câu 5.** `BitSet.valueOf(new long[]{Long.MIN_VALUE, 2L})` bật index nào?  
**Đáp án:** `63` và `65`. Bit cao nhất của word 0 và bit số 1 của word 1.

**Câu 6.** `length()`, `size()` và `cardinality()` có giống nhau không?  
**Đáp án:** Không. `length()` = highest set index +1; `size()` nói về dung lượng biểu diễn theo implementation; `cardinality()` là số bit true.

**Câu 7.** Nếu protocol dùng 16-bit unsigned big-endian `12 34`, cần làm gì để `BitSet` có bit indices của số `0x1234`?  
**Đáp án:** Đổi byte order thành `34 12` (little-endian) trước khi gọi `valueOf(byte[])`. Nếu protocol còn dùng MSB-first cho **tên chỉ số bit**, cần xử lý thêm quy ước đánh số bit.

**Câu 8.** Vì sao `BitSet` không thể tự nhớ một field độ rộng 256 bit khi tất cả bit đều false?  
**Đáp án:** `BitSet` lưu trạng thái các bit, còn `length()` được suy ra từ bit true cao nhất. Khi tất cả đều false, `length()==0` và `toByteArray()` rỗng. Độ rộng 256 là metadata của protocol và phải được giữ riêng.

## 13. Tóm tắt và tài liệu chính thức

**Các nguyên tắc không được nhầm:**

- `BitSet` đánh index **0** cho bit LSB của byte đầu tiên trong biểu diễn byte.
- `valueOf(byte[])` và `toByteArray()` dùng little-endian: `bytes[n/8]` chứa bit index `n`, vị trí trong byte là `n%8`.
- `valueOf(long[])` và `toLongArray()` dùng cùng tinh thần trên word 64-bit: `longs[n/64]`, vị trí `n%64`.
- `ByteBuffer.order()` không thay đổi quy tắc diễn giải trực tiếp từng byte của `BitSet.valueOf(ByteBuffer)`.
- `toByteArray()` không bảo toàn padding zero và độ rộng ban đầu: lưu độ dài fixed-width **bên ngoài**.
- Byte order, bit numbering và wire/transmission order là **các khái niệm tách biệt**; phải đọc đúng đặc tả nguồn dữ liệu trước khi chuyển đổi.

### Nguồn Java API còn hiệu lực

- [Java SE 17 — `java.util.BitSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): `valueOf` với byte/long/buffer, công thức bit index, `toByteArray`, `toLongArray`, `length`, `size` và `cardinality`.
- [Java SE 17 — `java.nio.ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit` và `order` đối với primitive nhiều byte.
- [Java SE 17 — `java.nio.ByteOrder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html): `BIG_ENDIAN` và `LITTLE_ENDIAN`.
- [Java SE 17 — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `copyOf` và các thao tác mảng cho dữ liệu fixed-width.
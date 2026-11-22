# BigInteger: Chuyển sang `byte[]` và vấn đề byte dấu bổ sung

`java.math.BigInteger` biểu diễn số nguyên có dấu, độ chính xác tùy ý. Khi cần lưu hoặc truyền số dưới dạng nhị phân, phương thức **`BigInteger.toByteArray()`** trả một mảng byte, nhưng **không phải mảng các chữ số độ lớn không dấu**. Đây là **biểu diễn bù hai (*two's complement*) có dấu, theo thứ tự byte cao trước (*big-endian*), có độ dài tối thiểu đủ biểu diễn cả dấu**.

Hệ quả dễ gây ngạc nhiên nhất: một số nguyên **dương** như `128` có thể cần thêm byte `0x00` ở đầu. Byte này **không phải một chữ số thừa vô nghĩa do lỗi API**: nó giữ cho bit dấu của biểu diễn bù hai bằng 0.

```java
import java.math.BigInteger;
import java.util.Arrays;

BigInteger number = BigInteger.valueOf(128);
byte[] bytes = number.toByteArray();

System.out.println(Arrays.toString(bytes)); // [0, -128]
System.out.println(new BigInteger(bytes));  // 128
```

Mảng trên gồm `0x00 0x80`. Vì `byte` trong Java có dấu từ `-128` đến `127`, byte `0x80` được in thành `-128` khi dùng `Arrays.toString`. Nhưng ở cấp bit nó vẫn là `1000_0000`; đặt byte `0x00` ở đầu giúp số dương 128 **không** bị đọc nhầm thành −128.

Bài này giải thích đầy đủ dấu, byte bổ sung, trường hợp âm, tạo số lại từ bytes, chuyển sang định dạng unsigned hoặc fixed-width, byte order và cách kiểm thử round trip trong Java 17+.

## 1. Hiểu ba khái niệm trước khi viết code

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Giá trị số nguyên** | Giá trị toán học của đối tượng `BigInteger` | `128` |
| **Biểu diễn bù hai có dấu** | Chuỗi bit quy định số âm/dương, với bit cao nhất của toàn biểu diễn là bit dấu | `00 80` cho `+128`; `80` cho `-128` |
| **Định dạng wire/protocol** | Quy ước của bên gửi và nhận: signed hay unsigned, big-endian hay little-endian, độ dài cố định hay tối thiểu | unsigned uint8 `80` cũng đại diện 128 |

Ba cách nhìn có thể dẫn đến **cùng byte vật lý nhưng khác giá trị**. Với đúng một byte `0x80`:
- Nếu giải mã dưới dạng **signed two's complement 8-bit**, giá trị là **−128**.
- Nếu giải mã dưới dạng **unsigned 8-bit**, giá trị là **128**.

Không có API nào tự suy ra ý nghĩa đó chỉ từ một mảng byte. **Signedness, byte order và width phải được nêu trong hợp đồng dữ liệu**.

### `BigInteger` là immutable nhưng byte array thì không

Đối tượng `BigInteger` không có thao tác thay đổi giá trị tại chỗ. Trong khi đó, `byte[]` là một object mutable của Java:

```java
BigInteger value = BigInteger.valueOf(128);
byte[] exported = value.toByteArray();
exported[0] = 99;

// value vẫn là 128: sửa byte[] đã lấy ra không sửa BigInteger.
```

Tương tự, khi muốn dùng một mảng byte làm input, hãy hiểu constructor đọc **nội dung** của nó để tạo giá trị. Một mảng byte bạn giữ trong ứng dụng không trở thành immutable chỉ vì nó từng dùng để tạo `BigInteger`.

## 2. Hợp đồng chính xác của `BigInteger.toByteArray()`

Chữ ký trong `java.math.BigInteger`:

```java
public byte[] toByteArray()
```

Kết quả có các đặc tính:
1. **Signed two's complement:** biểu diễn giá trị âm/dương bằng bù hai, không dùng một byte riêng chỉ chứa dấu.
2. **Big-endian:** byte có trọng số lớn hơn xuất hiện trước.
3. **Độ dài tối thiểu:** cần **ít nhất một bit dấu** cùng những bit cần biểu diễn giá trị. Phương thức không nhận tham số độ rộng.
4. **Không cố định 1/2/4/8 byte:** kết quả dài ngắn tùy giá trị.
5. **Số 0 không tạo mảng rỗng:** `BigInteger.ZERO.toByteArray()` cho mảng một byte `00`.
6. **Có thể có byte đầu `00` với số dương**, khi bit cao của byte độ lớn đầu tiên bằng 1.
7. **Không tự chọn độ dài giao thức:** nếu protocol yêu cầu chính xác N byte, ứng dụng phải encode theo hợp đồng đó.

Dạng diễn giải bằng hexadecimal, mỗi cặp ký tự là một byte:

```text
Value       BigInteger.toByteArray() hex
0            00
127          7f
128          00 80
255          00 ff
256          01 00
-1           ff
-128         80
-129         ff 7f
-255         ff 01
-256         ff 00
```

Đây là các kết quả thực tế đã kiểm chứng với Java. Không nhầm cột hex với đầu ra mặc định của `Arrays.toString(byte[])`: phương thức đó in các **byte signed dạng thập phân**, ví dụ `[0, -128]` thay cho `00 80`.

## 3. Tại sao 128 lại là hai byte `00 80`?

Xét một byte, tức 8 bit:

```text
Hex byte         0x80
Binary bits      1000 0000
Signed 8-bit     -128
Unsigned 8-bit   +128
```

Trong bù hai có dấu, bit cao nhất của toàn bộ vùng biểu diễn là bit dấu. Nếu dùng duy nhất byte `80`, bit cao là 1 ⇒ theo signed two's complement, giá trị là **−128**.

Muốn mô tả **+128**, cần một biểu diễn có bit dấu bằng 0:

```text
00          80
00000000    10000000
^
bit dấu 0 của toàn biểu diễn 16 bit
```

Vì vậy `BigInteger.valueOf(128).toByteArray()` là `00 80`. Byte `00` ở trước giữ dấu dương và không đổi độ lớn.

Tương tự:
- `127` có bit đầu byte `7f` bằng 0 ⇒ **một byte** đủ.
- `128` có byte độ lớn `80`, bit đầu bằng 1 ⇒ **hai byte** `00 80`.
- `255` có byte độ lớn `ff`, bit đầu bằng 1 ⇒ **hai byte** `00 ff`.
- `256` có hex `01 00`, bit đầu `01` bằng 0 ⇒ **hai byte** là đủ, không thêm byte `00` thứ ba.

**Không phải mọi số dương nhiều byte đều được thêm byte 00.** Byte dấu bổ sung chỉ cần khi biểu diễn độ lớn tối thiểu, theo ranh giới byte, có bit cao đầu bằng 1.

### Biên 127 → 128

```java
byte[] a = BigInteger.valueOf(127).toByteArray();
byte[] b = BigInteger.valueOf(128).toByteArray();

System.out.println(a.length); // 1
System.out.println(b.length); // 2
```

Giá trị chỉ tăng 1, nhưng số byte tăng từ 1 lên 2. Đây là lý do **không dùng độ dài của `toByteArray()` làm độ rộng dữ liệu unsigned một cách máy móc**.

### Biên `0x7fff` → `0x8000`

Số dương 32767 có thể biểu diễn là `7f ff`. Nhưng 32768 cần `00 80 00`: byte đầu `80` của magnitude có bit cao bằng 1, nên phải thêm `00`. Đây chính là nguyên tắc xảy ra tại **mọi ranh giới 7-bit đầu của biểu diễn signed**, không phải trường hợp riêng của 128.

## 4. Với số âm, bù hai hoạt động như thế nào?

Số âm được mã hóa bằng **bù hai**. Trong vùng bit có độ rộng cố định, một cách hình dung là đảo bit của trị tuyệt đối rồi cộng 1. Nhưng với `BigInteger`, độ rộng không cố định; `toByteArray()` chọn độ dài **tối thiểu** để mô tả số có dấu.

```text
-1    -> ff       (11111111)
-128  -> 80       (10000000)
-129  -> ff 7f    (11111111 01111111)
-255  -> ff 01
-256  -> ff 00
```

Vì sao `-128` vừa một byte nhưng `-129` cần hai?

- Với signed 8-bit, miền là **−128 đến +127**.
- `-128` vừa miền, có biểu diễn `80`.
- `-129` nằm ngoài miền, cần 16 bit. Bù hai 16 bit của `-129` là `ff 7f`.
- Byte `ff` đầu mang phần bit dấu mở rộng cần thiết. Bỏ nó đi sẽ còn `7f` tức +127, **không** phải −129.

**Không được xóa mọi byte `0xFF` đầu mảng âm**. Có lúc `ff` là bit dấu mở rộng **cần thiết** (như `-129`). Chỉ một codec có hiểu rõ giá trị, width và bù hai mới có thể rút gọn hoặc kéo dài biểu diễn mà vẫn bảo toàn số.

### Sign extension khi cần độ dài signed cố định

Nếu muốn đưa `-1` từ một byte `ff` vào vùng signed 4 byte, cần mở rộng dấu bằng byte `ff`:

```text
Signed minimal -1:  ff
Signed 32-bit -1:   ff ff ff ff
```

Tương tự, `+1` muốn biểu diễn signed 32-bit sẽ được đệm `00`:

```text
Signed minimal +1: 01
Signed 32-bit +1:  00 00 00 01
```

Vì vậy **padding signed âm** dùng `FF` chứ không phải `00`. Padding unsigned thì theo giao thức số không âm, thường là `00` phía đầu khi big-endian.

## 5. Constructor `new BigInteger(byte[])` đọc signed two's complement

Constructor:

```java
BigInteger(byte[] val)
```

diễn giải mảng input thành **số nguyên có dấu** theo bù hai và thứ tự big-endian, tương thích với `toByteArray()`.

```java
byte[] negativeEncoding = {(byte) 0x80};
BigInteger a = new BigInteger(negativeEncoding);
System.out.println(a); // -128.
```

Nếu dùng `00 80` thay vì `80`:

```java
byte[] positiveEncoding = {0, (byte) 0x80};
BigInteger b = new BigInteger(positiveEncoding);
System.out.println(b); // 128.
```

Hai mảng có byte thấp giống nhau; chỉ khác **byte đầu quyết định bit dấu của vùng signed**.

### Round trip signed

Với một giá trị `BigInteger` hợp lệ, có thể serialize và parse lại theo cặp tương ứng:

```java
BigInteger original = new BigInteger("-129");
byte[] bytes = original.toByteArray();
BigInteger restored = new BigInteger(bytes);

System.out.println(original.equals(restored)); // true
```

Đây là round trip **giá trị số**, không phải cam kết giữ nguyên chiều dài byte của một input signed *không tối thiểu* đã có trước đó. Chẳng hạn constructor có thể nhận `00 00 80` như +128, nhưng `toByteArray()` sẽ dùng biểu diễn signed tối thiểu `00 80`.

**Cảnh báo:** mảng rỗng không đại diện số 0 trong constructor signed này; xử lý đầu vào empty theo chính sách codec (trong Java, constructor signed từ mảng byte độ dài 0 ném `NumberFormatException`).

## 6. Constructor `new BigInteger(signum, magnitude)` cho độ lớn không dấu

Một overload khác:

```java
BigInteger(int signum, byte[] magnitude)
```

cho phép truyền **dấu tách riêng** và **mảng độ lớn không dấu**, big-endian. `signum` chỉ có thể là `-1`, `0` hoặc `1`.

```java
byte[] oneByte = {(byte) 0x80};

BigInteger signed = new BigInteger(oneByte);
BigInteger unsignedMagnitude = new BigInteger(1, oneByte);

System.out.println(signed);            // -128
System.out.println(unsignedMagnitude); // 128
```

Đây là cách đọc đúng **một byte `80` như số dương unsigned 128**. Nó không thêm `00` vào mảng input để “chữa” dấu, mà trao dấu +1 cho constructor.

Các tình huống:
- `new BigInteger(1, bytes)`: magnitude không âm; dùng dấu dương (trừ trường hợp magnitude bằng 0 sẽ ra 0).
- `new BigInteger(-1, bytes)`: giá trị âm theo độ lớn bytes.
- `new BigInteger(0, bytes)`: chỉ hợp lệ nếu magnitude thật sự bằng 0; signum 0 với magnitude khác 0 bị từ chối.
- `signum` ngoài −1/0/1: không hợp lệ.

`new BigInteger(1, bytes)` đặc biệt hữu ích khi hệ thống nhận **unsigned big-endian byte string** như một số dương. Nhưng với giao thức có độ dài cố định, vẫn cần kiểm tra số byte và miền dự kiến.

### Một byte `ff` có thể là −1 hoặc +255

```java
byte[] ff = {(byte) 0xff};
System.out.println(new BigInteger(ff));    // -1
System.out.println(new BigInteger(1, ff)); // 255
```

Không thể xác định đáp án đúng từ hex `ff` nếu schema chưa quy định signed/unsigned.

## 7. Tại sao bit cao nhất của một byte lại ảnh hưởng tổng độ dài?

Độ dài `toByteArray()` không chỉ phụ thuộc số bit của **độ lớn tuyệt đối**, mà còn phải dành **ít nhất một bit dấu** theo signed two's complement.

Bảng các mốc dương:

| Giá trị | Magnitude hex tối thiểu | `toByteArray()` hex | Độ dài |
| ---: | --- | --- | ---: |
| 0 | `00` | `00` | 1 |
| 1 | `01` | `01` | 1 |
| 127 | `7f` | `7f` | 1 |
| 128 | `80` | `00 80` | 2 |
| 255 | `ff` | `00 ff` | 2 |
| 256 | `01 00` | `01 00` | 2 |
| 32767 | `7f ff` | `7f ff` | 2 |
| 32768 | `80 00` | `00 80 00` | 3 |
| 65535 | `ff ff` | `00 ff ff` | 3 |
| 65536 | `01 00 00` | `01 00 00` | 3 |

Từ bảng có thể thấy **thêm byte dấu không phải lúc nào cũng xảy ra mỗi khi tăng độ rộng magnitude**. Quan trọng là bit cao của byte đầu trong biểu diễn magnitude có bị nhầm thành bit dấu âm hay không.

### `bitLength()` không phải số byte wire

`BigInteger.bitLength()` mô tả độ dài bit theo định nghĩa của lớp (không tính bit dấu trong biểu diễn tối thiểu). Nó không tự chuyển thành chiều dài signed `toByteArray()` hay chiều dài unsigned của protocol nếu chưa hiểu cách cộng bit dấu và làm tròn theo byte.

Đối với **số không âm**, số byte magnitude tối thiểu thường được tính bằng làm tròn lên `bitLength/8`, với trường hợp zero cần chính sách riêng. Nhưng dùng `bitLength()` làm một codec tổng quát mà quên zero, số âm, sign byte và giới hạn width dễ tạo lỗi biên. Nếu cần xuất bytes thật, lấy `toByteArray()` rồi áp dụng **chính sách signedness** có kiểm tra.

## 8. BigInteger.toByteArray() không phải một bộ mã hóa unsigned cố định

Giả sử một giao thức yêu cầu trường **unsigned 64-bit big-endian**, đúng **8 byte**. Giá trị tối đa là:

\[
2^{64}-1 = 18446744073709551615
\]

`BigInteger` biểu diễn được giá trị này. Nhưng:

```java
BigInteger maxUnsigned64 =
        BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE);
byte[] signedBytes = maxUnsigned64.toByteArray();
```

`signedBytes` gồm **9 byte**:

```text
00 ff ff ff ff ff ff ff ff
```

Byte `00` là byte dấu bảo đảm số dương khi đọc lại bằng constructor signed. Trong wire format **unsigned 64-bit**, trường hợp này cần đúng **8 byte**:

```text
ff ff ff ff ff ff ff ff
```

Nếu gửi thẳng 9 byte sẽ **vi phạm độ dài giao thức**. Nếu phía nhận đọc 8 byte trên bằng `new BigInteger(bytes)`, nó sẽ thấy −1 thay vì `2^64−1`.

**Cách đúng:** ở bên gửi áp dụng codec **unsigned fixed-width có kiểm tra miền**, ở bên nhận dùng `new BigInteger(1, bytes)` và xác thực độ dài. Không thay đổi signedness chỉ bằng cách đổi tên biến.

### Khi nào được bỏ byte `00` đầu?

Chỉ khi **định dạng đích là unsigned magnitude** và bạn xác định byte `00` thật sự là **byte dấu thêm vào cho biểu diễn dương**, không phải một byte có ý nghĩa của một trường fixed-width dài hơn. Để chuyển **giá trị không âm** từ `toByteArray` sang magnitude không dấu tối thiểu, có thể bỏ **chính xác một** byte `00` đầu nếu mảng có ít nhất hai byte và byte đầu bằng `00`.

```java
byte[] signed = value.toByteArray();
int offset = signed.length > 1 && signed[0] == 0 ? 1 : 0;
```

Điều kiện `signed.length > 1` quan trọng: `BigInteger.ZERO.toByteArray()` là `00`. Nếu xóa byte zero duy nhất, bạn sẽ thu được mảng rỗng; giao thức phải **quy định riêng** cách biểu diễn số 0, không để điều này xảy ra tình cờ.

Không dùng thao tác "bỏ tất cả byte đầu bằng 00" nếu protocol có fixed width và các byte 0 đầu chính là phần padding hợp lệ cần giữ.

## 9. Viết codec unsigned fixed-width an toàn

Phương thức dưới đây nhận:
- `value` phải **không âm**.
- `length` là **số byte của wire field**, lớn hơn 0.
- Giá trị phải vừa miền unsigned `[0, 2^(8*length)-1]`.
- Kết quả là **đúng `length` byte big-endian**.
- Nếu giá trị không vừa, **ném exception thay vì cắt bit cao**.

```java
static byte[] toUnsignedFixed(BigInteger value, int length) {
    if (value.signum() < 0 || length <= 0) {
        throw new IllegalArgumentException(
                "requires nonnegative number and positive length");
    }

    byte[] encoded = value.toByteArray();
    int offset = encoded.length > 1 && encoded[0] == 0 ? 1 : 0;
    int count = encoded.length - offset;

    if (count > length) {
        throw new IllegalArgumentException("does not fit unsigned width");
    }

    byte[] out = new byte[length]; // Tự điền 0 ở các byte cao.
    System.arraycopy(encoded, offset, out, length - count, count);
    return out;
}
```

Đây là **method minh họa**, cần đặt trong class có `import java.math.BigInteger`.

### Vì sao kiểm tra miền rất quan trọng?

Nếu muốn uint8, chỉ có đúng một byte; miền phải là `0..255`.

```java
toUnsignedFixed(BigInteger.valueOf(255), 1); // ff
// toUnsignedFixed(BigInteger.valueOf(256), 1); // IllegalArgumentException.
```

Nếu lặng lẽ lấy byte thấp của 256, bạn sẽ gửi `00` và bên nhận nghĩ số là 0. Lỗi này tương tự cast số nguyên vượt miền nhưng khó phát hiện hơn vì bytes trông vẫn hợp lệ.

### Giải mã unsigned big-endian

```java
byte[] wire = {(byte) 0xff};
BigInteger restored = new BigInteger(1, wire);
System.out.println(restored); // 255.
```

Với **fixed-width**, cần xác thực `wire.length` bằng đúng số byte schema chỉ định trước khi parse; `new BigInteger(1,bytes)` tự nó không bắt buộc một chiều dài field cụ thể.

Có thể so sánh round trip:

```java
BigInteger value = new BigInteger("18446744073709551615");
byte[] wire8 = toUnsignedFixed(value, 8);
BigInteger restored = new BigInteger(1, wire8);
System.out.println(value.equals(restored)); // true.
```

Độ rộng 8 byte ở đây là phần của **schema**, không phải độ dài tự nhiên của `BigInteger.toByteArray()`.

## 10. Codec signed fixed-width: phải sign-extend

Nếu giao thức yêu cầu **signed 16-bit big-endian** (2 byte), miền hợp lệ là `−32768..32767`. Ta không chỉ gọi `toByteArray()` rồi đệm 0 một cách mù quáng, bởi số âm cần **đệm `ff`** để bảo toàn dấu.

Ví dụ:
- `−129` có signed minimal `ff 7f`, vừa đúng 2 byte.
- `−1` có signed minimal `ff`, muốn signed 2 byte phải thành `ff ff`.
- `+128` có signed minimal `00 80`, vừa 2 byte.
- `+32767` có `7f ff`, vừa 2 byte.
- `+32768` không vừa signed 16 bit, cần **báo lỗi**, không lấy hai byte thấp `80 00` rồi biến thành −32768.

Một codec minh họa:

```java
static byte[] toSignedFixed(BigInteger value, int length) {
    // Giới hạn 1000 byte chỉ là quota của ví dụ, không phải luật BigInteger.
    if (length <= 0 || length > 1000) {
        throw new IllegalArgumentException("invalid length");
    }

    int bits = length * 8;
    BigInteger limit = BigInteger.ONE.shiftLeft(bits - 1);
    BigInteger min = limit.negate();
    BigInteger max = limit.subtract(BigInteger.ONE);

    if (value.compareTo(min) < 0 || value.compareTo(max) > 0) {
        throw new IllegalArgumentException("does not fit signed width");
    }

    byte[] raw = value.toByteArray();
    byte[] out = new byte[length];
    Arrays.fill(out, value.signum() < 0 ? (byte) 0xff : 0);
    System.arraycopy(raw, 0, out, length - raw.length, raw.length);
    return out;
}
```

Cần `import java.util.Arrays;`. Phương thức này minh họa signed two's complement theo **big-endian**, dùng giới hạn miền signed và đệm dấu thích hợp. Quota `1000 byte` giúp ví dụ không nhận length vô lý hoặc phép nhân độ rộng tràn `int`. Hệ thống thật phải chọn quota theo schema, nhu cầu và tài nguyên thực tế.

Khi giải mã signed:

```java
byte[] signedTwoBytes = {(byte) 0xff, (byte) 0x7f};
BigInteger n = new BigInteger(signedTwoBytes);
System.out.println(n); // -129.
```

Nếu thử dùng `new BigInteger(1,signedTwoBytes)` cho cùng bytes, kết quả sẽ **dương** (653... theo số byte); đó là **đổi ý nghĩa giao thức** chứ không phải một cách parse signed khác.

## 11. Big-endian khác little-endian

`BigInteger.toByteArray()` và các constructor từ byte array liên quan sử dụng **big-endian**. Ví dụ số dương 256:

```text
BigInteger.toByteArray() of +256:
01 00
^ byte cao trước
```

Một protocol little-endian có thể muốn `00 01`. Nếu gửi `01 00` mà phía nhận tưởng little-endian, nó có thể đọc thành 1 thay vì 256 hoặc thành giá trị khác tùy width.

**Đừng chỉ đảo byte khi chưa biết signedness và width.** Nếu dùng độ dài tự nhiên của `toByteArray()`, byte dấu bổ sung ảnh hưởng số byte phải đảo. Đối với giao thức fixed-width, thường nên:
1. Encode theo **signed/unsigned width đúng** ở big-endian.
2. Nếu protocol dùng little-endian, đảo thứ tự **đúng N byte**.
3. Bên nhận đảo lại đúng N byte rồi tạo `BigInteger` bằng constructor phù hợp.

`ByteBuffer` có thể được cấu hình `ByteOrder.LITTLE_ENDIAN` cho một số phép đọc/ghi primitive 16/32/64 bit, nhưng `BigInteger` **không** có constructor đơn giản nhận `ByteOrder`. Với số tùy ý độ lớn, codec cần nêu rõ thứ tự byte.

### Không nhầm với thứ tự bit trong từng byte

Big-endian/little-endian mô tả **thứ tự byte**, không tự đảo thứ tự các bit bên trong từng byte. Byte `80` vẫn có mẫu bit `1000_0000`; không phải `0000_0001`.

## 12. Những trường hợp quan trọng khi xử lý zero

`BigInteger.ZERO.toByteArray()` trả `00`, không phải mảng rỗng.

```java
byte[] zero = BigInteger.ZERO.toByteArray();
System.out.println(zero.length); // 1.
System.out.println(zero[0]);     // 0.
```

Với signed fixed width 4 byte, zero là `00 00 00 00`. Với unsigned fixed width 4 byte cũng vậy. Nhưng nếu một giao thức định nghĩa magnitude zero bằng **mảng trống**, bạn không thể tự suy điều đó từ `toByteArray()`; phải có quy tắc ngoại lệ.

Tương tự, `new BigInteger(new byte[]{0})` là số 0. Đừng lẫn `BigInteger.ZERO` với `null` (không có đối tượng) hoặc với “chưa có giá trị” trong schema.

**Nên có test riêng cho số 0** vì nhiều hàm “bỏ byte dấu đầu” dễ làm zero thành mảng rỗng, từ đó decode sai hoặc gây exception.

## 13. Sử dụng `Arrays.toString`: byte Java là signed

`Arrays.toString(byte[])` in các phần tử theo `byte` **có dấu**, không phải hex unsigned:

```java
byte[] bytes = {0, (byte) 0x80, (byte) 0xff};
System.out.println(Arrays.toString(bytes)); // [0, -128, -1].
```

Để xem bytes dưới dạng hex, hãy tách từng byte và **mask `& 0xff`** trước khi định dạng:

```java
static String hex(byte[] bytes) {
    StringBuilder b = new StringBuilder();
    for (byte x : bytes) {
        if (b.length() > 0) {
            b.append(" ");
        }
        b.append(String.format(
                java.util.Locale.ROOT, "%02x", x & 0xff));
    }
    return b.toString();
}
```

Đây là helper phục vụ debug/bài học, không phải phương thức mã hóa byte tùy ý lớn tối ưu nhất. `x & 0xff` chuyển byte về **giá trị không dấu 0..255** trước khi format. Không dùng `Integer.toHexString((int)x)` trực tiếp với byte âm rồi bất ngờ nhận chuỗi dài `ffffff80` do sign extension khi mở rộng lên `int`.

### Khi in giá trị BigInteger ở dạng hex

`big.toString(16)` biểu diễn **giá trị có dấu** (chẳng hạn `-80` cho −128), còn `hex(big.toByteArray())` biểu diễn **mẫu byte signed** (chẳng hạn `80` cho −128). Đây là **hai câu hỏi khác nhau**.

Ví dụ:

```java
BigInteger n = BigInteger.valueOf(-1);
System.out.println(n.toString(16));   // -1
System.out.println(hex(n.toByteArray())); // ff
```

Không dùng chuỗi hex của giá trị có dấu thay thế cho hex của byte stream trong giao thức.

## 14. Java 17+: Chương trình chạy đầy đủ

Lưu thành `ByteArraySignDemo.java`:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Locale;

public class ByteArraySignDemo {
    static String hex(byte[] bytes) {
        StringBuilder b = new StringBuilder();
        for (byte x : bytes) {
            if (b.length() > 0) {
                b.append(" ");
            }
            b.append(String.format(Locale.ROOT, "%02x", x & 0xff));
        }
        return b.toString();
    }

    static byte[] toUnsignedFixed(BigInteger n, int length) {
        if (n.signum() < 0 || length <= 0) {
            throw new IllegalArgumentException(
                    "requires nonnegative number and positive length");
        }
        byte[] encoded = n.toByteArray();
        int offset = encoded.length > 1 && encoded[0] == 0 ? 1 : 0;
        int count = encoded.length - offset;
        if (count > length) {
            throw new IllegalArgumentException("does not fit unsigned width");
        }
        byte[] out = new byte[length];
        System.arraycopy(encoded, offset, out, length - count, count);
        return out;
    }

    static byte[] toSignedFixed(BigInteger n, int length) {
        if (length <= 0 || length > 1000) {
            throw new IllegalArgumentException("invalid length");
        }
        int bits = length * 8;
        BigInteger limit = BigInteger.ONE.shiftLeft(bits - 1);
        if (n.compareTo(limit.negate()) < 0
                || n.compareTo(limit.subtract(BigInteger.ONE)) > 0) {
            throw new IllegalArgumentException("does not fit signed width");
        }
        byte[] raw = n.toByteArray();
        byte[] out = new byte[length];
        Arrays.fill(out, n.signum() < 0 ? (byte) 0xff : 0);
        System.arraycopy(raw, 0, out, length - raw.length, raw.length);
        return out;
    }

    public static void main(String[] args) {
        long[] values = {
                0, 127, 128, 255, 256, -1, -128, -129, -255, -256
        };
        for (long n : values) {
            BigInteger x = BigInteger.valueOf(n);
            byte[] b = x.toByteArray();
            System.out.println(n + " -> " + hex(b)
                    + " -> " + new BigInteger(b));
        }

        byte[] one = {(byte) 0x80};
        System.out.println("80 as signed: " + new BigInteger(one));
        System.out.println("80 as unsigned: " + new BigInteger(1, one));
        System.out.println("0080 as signed: "
                + new BigInteger(new byte[] {0, (byte) 0x80}));

        BigInteger max64 =
                BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE);
        System.out.println("2^64-1 signed bytes: "
                + hex(max64.toByteArray()));
        byte[] wire = toUnsignedFixed(max64, 8);
        System.out.println("2^64-1 unsigned 8 bytes: " + hex(wire));
        System.out.println("2^64-1 unsigned decoded: "
                + new BigInteger(1, wire));

        System.out.println("negative -129 signed 2 bytes: "
                + hex(toSignedFixed(BigInteger.valueOf(-129), 2)));
        System.out.println("signed 2 bytes decoded: "
                + new BigInteger(toSignedFixed(
                        BigInteger.valueOf(-129), 2)));

        try {
            toUnsignedFixed(BigInteger.valueOf(-1), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative unsigned: rejected");
        }
        try {
            toUnsignedFixed(BigInteger.valueOf(256), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("256 in uint8: rejected");
        }
        try {
            toSignedFixed(BigInteger.valueOf(128), 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("128 in int8: rejected");
        }

        System.out.println("signed zero bytes: "
                + hex(BigInteger.ZERO.toByteArray()));
        System.out.println("byte[] reused immutable? "
                + BigInteger.valueOf(128).equals(
                    new BigInteger(BigInteger.valueOf(128).toByteArray())));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 ByteArraySignDemo.java
java ByteArraySignDemo
```

Stdout đã kiểm chứng:

```text
0 -> 00 -> 0
127 -> 7f -> 127
128 -> 00 80 -> 128
255 -> 00 ff -> 255
256 -> 01 00 -> 256
-1 -> ff -> -1
-128 -> 80 -> -128
-129 -> ff 7f -> -129
-255 -> ff 01 -> -255
-256 -> ff 00 -> -256
80 as signed: -128
80 as unsigned: 128
0080 as signed: 128
2^64-1 signed bytes: 00 ff ff ff ff ff ff ff ff
2^64-1 unsigned 8 bytes: ff ff ff ff ff ff ff ff
2^64-1 unsigned decoded: 18446744073709551615
negative -129 signed 2 bytes: ff 7f
signed 2 bytes decoded: -129
negative unsigned: rejected
256 in uint8: rejected
128 in int8: rejected
signed zero bytes: 00
byte[] reused immutable? true
```

Phần demo xác nhận signed two's complement tối thiểu, byte `00` bổ sung ở số dương, signed vs unsigned constructor, byte `FF` mở rộng dấu âm, codec fixed-width kiểm tra miền, zero và khả năng round trip. Ví dụ chỉ dùng các kiểu/method có sẵn trên Java 17+.

## 15. Bảng quyết định: dùng API nào?

| Hợp đồng đầu vào/đầu ra | Cách xử lý thích hợp | Cảnh báo |
| --- | --- | --- |
| Muốn round trip `BigInteger` có dấu dưới dạng bytes tối thiểu | `toByteArray()` ↔ `new BigInteger(bytes)` | Signed two's complement, big-endian, length biến đổi |
| Nhận magnitude **không dấu**, big-endian | `new BigInteger(1, bytes)` | Kiểm tra schema độ dài và miền |
| Xuất magnitude **không dấu**, length tự do | `toByteArray()`, bỏ byte dấu `00` đúng điều kiện | Zero cần chính sách rõ |
| Xuất **unsigned N byte** | Codec `toUnsignedFixed` với kiểm tra | Không âm, kiểm tra fit N byte, padding bằng 00 |
| Xuất **signed N byte** | Codec `toSignedFixed` với kiểm tra | Signed range, negative sign extension FF |
| Nhận **signed N byte** big-endian | Xác thực đúng N byte rồi `new BigInteger(bytes)` | Không được loại bỏ sign byte tùy tiện |
| Nhận **unsigned N byte** big-endian | Xác thực đúng N byte rồi `new BigInteger(1,bytes)` | Cùng bytes có thể đọc ra số khác nếu signed |
| Giao thức little-endian | Hoán đổi thứ tự byte sau khi encode đúng width | Không đảo bit; không quên sign byte |
| Cần log bytes theo hex | `hex(bytes)` với `b & 0xff` | `Arrays.toString` in byte signed decimal |
| Cần hiển thị giá trị số hệ 16 | `big.toString(16)` | Không đồng nghĩa raw byte hex |
| Cần độ chính xác toán học nhưng dữ liệu là String decimal | `new BigInteger(decimalText)` | Không parse qua `double` |
| Cần gửi JSON / CSV | Schema text hoặc codec dữ liệu có cấu trúc | Không coi `byte[]` là text, thường cần base64/hex nếu schema yêu cầu |

### Bài toán thực tế: ID 128 bit và digest

Giả sử một hệ thống đưa số định danh **không dấu 128 bit** lên mạng theo 16 byte big-endian. Nếu dùng `BigInteger.toByteArray()` trực tiếp, ID có bit cao nhất bằng 1 có thể tạo **17 byte** vì byte 00 bổ sung. Bên nhận dự kiến đúng 16 byte sẽ báo sai chiều dài.

Ngược lại, nếu vô điều kiện lấy 16 byte cuối của bất kỳ BigInteger, bạn có nguy cơ **cắt bỏ các bit quan trọng** của một giá trị vượt 128 bit. Cách đúng là xác thực `0 <= value < 2^128` rồi serialize **đúng 16 byte không dấu**.

**Phân biệt digest và số:** giá trị hash 16/32 byte trong nhiều giao thức là **chuỗi byte** chứ không phải một số nguyên có dấu. Nếu yêu cầu giữ đúng mọi byte, bao gồm zero đầu, đôi khi tốt hơn là **giữ trực tiếp `byte[]`/`ByteBuffer` hoặc một kiểu wrapper dữ liệu byte**, không chuyển qua `BigInteger` khi không cần số học.

## 16. Các lỗi phổ biến và cách sửa

| Sai lầm | Kết quả sai | Cách đúng |
| --- | --- | --- |
| Cho rằng `toByteArray()` trả magnitude không dấu | `128` thành `00 80` thay vì `80` | Hiểu signed two's complement; chọn unsigned codec khi cần |
| Xóa mọi byte `00` ở đầu | Có thể mất padding hợp lệ và xử lý sai zero | Chỉ bỏ byte dấu bổ sung theo schema |
| Xóa mọi byte `FF` ở đầu số âm | `-129` thành `+127` | Sign extension phải dựa trên signed range |
| Dùng `new BigInteger(new byte[]{(byte)0x80})` để lấy 128 | Nhận −128 | `new BigInteger(1, bytes)` |
| Dùng `new BigInteger(1,bytes)` với bytes signed âm | Nhận số dương lớn thay vì số âm | Constructor signed `new BigInteger(bytes)` |
| Gửi `toByteArray()` vào uint64 field | Có thể phát sinh 9 byte | Codec unsigned 8 byte, kiểm tra miền |
| Cắt byte cao để vừa trường | Âm thầm đổi giá trị | Kiểm tra fit trước khi encode |
| Đệm số âm bằng `00` | Có thể làm sai dấu hoặc số | Đệm `FF` cho signed negative |
| Không kiểm tra zero | Có thể biến `00` thành mảng rỗng | Định nghĩa zero trong schema |
| Nhầm `Arrays.toString` với hex dump | Nhìn thấy `-128` thay vì `80` | Format byte bằng `& 0xff` |
| Nhầm `big.toString(16)` với `hex(big.toByteArray())` | Value hex khác raw byte hex | Chọn đúng ý nghĩa |
| Tưởng `BigInteger` có byte order tùy chọn | Constructor/toByteArray dùng big-endian | Codec đảo byte khi protocol little-endian |
| Sử dụng signed integer cho chuỗi byte hash | Mất nghĩa độ dài và zero đầu | Giữ raw bytes nếu không cần số học |
| Tưởng mọi `BigInteger.toByteArray()` có 8 byte với long-size | Độ dài tự thay đổi theo giá trị | Fixed-width codec theo schema |
| Đo độ dài bằng `bitLength()/8` rồi không xử lý dấu | Sai ở biên 127/128, 0 | Test biên và thêm quy tắc sign |
| Dùng `byte` Java và nghĩ nó không dấu | `(byte)0xff == -1` | Mask `& 0xff` khi cần 0..255 |
| Không validate byte array input độ dài | Bên nhận có thể chấp nhận dữ liệu sai schema | Kiểm tra đúng N byte trước khi tạo BigInteger |

## 17. Bộ kiểm thử và câu hỏi tự đánh giá

### Kiểm thử ranh giới tối thiểu

Một codec đúng nên có các nhóm test:

1. **Zero:** `0` dưới dạng signed minimal, signed fixed, unsigned fixed.
2. **Ngay dưới và ngay trên bit dấu byte:** `127`, `128`, `255`, `256`.
3. **Số âm sát biên signed byte:** `-1`, `-128`, `-129`, `-255`, `-256`.
4. **Ranh giới 16 bit:** `32767`, `32768`, `-32768`, `-32769`.
5. **Ranh giới 64-bit unsigned:** `2^64-1` (vừa uint64), `2^64` (không vừa uint64).
6. **Miền unsigned:** từ chối số âm, từ chối value vượt `8N` bit.
7. **Miền signed:** từ chối `128` trong int8, chấp nhận `-128`, từ chối `-129` trong int8.
8. **Width:** `N=1`, `N=2`, `N=8`; từ chối length 0 hoặc âm.
9. **Byte order:** big-endian và little-endian phải round trip nếu codec tương ứng.
10. **Byte count:** output chính xác N byte khi schema yêu cầu; không tự thay N.
11. **Immutable:** sửa mảng `toByteArray()` đã nhận không đổi giá trị `BigInteger` gốc.
12. **Protocol integrity:** test với mảng đầu `00` và byte có bit cao bằng 1, không mất dữ liệu.

### Câu hỏi tự kiểm tra

1. Vì sao `BigInteger.valueOf(128).toByteArray()` trả `00 80` thay vì `80`?
2. Hai byte `00 80` biểu diễn giá trị gì theo signed big-endian? Một byte `80` biểu diễn gì theo signed và unsigned?
3. Vì sao số `127` chỉ cần một byte, còn `128` cần hai byte trong `toByteArray()`?
4. Vì sao `BigInteger.valueOf(-128).toByteArray()` là `80` nhưng `-129` là `ff 7f`?
5. Tại sao không được xóa mọi byte `ff` đầu mảng âm?
6. `new BigInteger(bytes)` khác `new BigInteger(1,bytes)` ở hợp đồng nào?
7. Giá trị `2^64-1` có `toByteArray()` dài bao nhiêu? Khi truyền uint64, cần bao nhiêu byte?
8. Nếu protocol yêu cầu signed 16-bit, bạn phải kiểm tra khoảng giá trị nào trước khi encode?
9. Tại sao padding `ff` với số âm khác padding `00` với số dương?
10. Vì sao `BigInteger.ZERO.toByteArray()` trả `00` thay vì mảng rỗng? Nếu wire schema quy định zero khác thì phải làm gì?
11. Làm sao bảo đảm byte array round trip giữ **giá trị** và đồng thời giữ **đúng chiều dài N byte**?
12. Vì sao output `Arrays.toString(new byte[]{(byte)0xff})` là `[-1]`? Nếu muốn hex `ff` phải làm sao?
13. `big.toString(16)` có giống hex dump của `big.toByteArray()` cho mọi số âm không?
14. Một protocol little-endian có thể dùng trực tiếp `toByteArray()` không? Những bước codec nào còn thiếu?
15. Với 16 byte digest/ID có zero đầu, có nên tự động chuyển qua `BigInteger` không? Trường hợp nào nên giữ byte array nguyên vẹn?

## 18. Tham khảo chính thức

- [Java SE 17 — `BigInteger.toByteArray()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#toByteArray()): mô tả mảng **big-endian two's complement**, độ dài tối thiểu và bit dấu.
- [Java SE 17 — `BigInteger(byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#%3Cinit%3E(byte%5B%5D)): constructor nhận biểu diễn signed two's complement.
- [Java SE 17 — `BigInteger(int,byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html#%3Cinit%3E(int,byte%5B%5D)): constructor nhận signum và magnitude big-endian.
- [Java SE 17 — `Arrays.toString(byte[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#toString(byte%5B%5D)): in phần tử byte theo giá trị signed.
- [Java Language Specification `4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): kiểu `byte` có dấu 8 bit và miền của các kiểu số nguyên Java.

**Kết luận:** `BigInteger.toByteArray()` biểu diễn số nguyên **có dấu** bằng **bù hai big-endian, độ dài tối thiểu**, nên có thể thêm `00` khi số dương có bit cao của magnitude bằng 1. Với số âm, byte `ff` có thể là **sign extension cần thiết**. Đừng xóa byte dấu hay cắt/pad ngẫu nhiên: hãy xác định **signedness, byte order và fixed width** của định dạng đích, kiểm tra miền, rồi dùng cặp mã hóa/giải mã tương ứng để bảo toàn giá trị và chiều dài dữ liệu.
# BigInteger: Biểu diễn byte bù hai có dấu và constructor sign-magnitude

Trong Java Core, `java.math.BigInteger` là kiểu **số nguyên có dấu với độ chính xác tùy ý**. Khi chuyển giữa `BigInteger` và mảng `byte[]`, cần đặc biệt phân biệt **hai cách giải mã hoàn toàn khác nhau**:

- **Bù hai có dấu (signed two's complement)**: `new BigInteger(byte[] val)` đọc mảng byte như *một số nguyên có dấu*; bit cao nhất của byte đầu tiên là **bit dấu**.
- **Dấu và độ lớn (sign–magnitude)**: `new BigInteger(int signum, byte[] magnitude)` nhận **dấu riêng** (`-1`, `0`, `1`) và coi *toàn bộ mảng byte là độ lớn không dấu*.

Cùng một byte có thể cho hai kết quả trái ngược:

```java
byte[] input = {(byte) 0x80};

BigInteger signed = new BigInteger(input);     // -128
BigInteger unsigned = new BigInteger(1, input); // +128
```

**Vì sao?** Mẫu 8 bit `1000_0000` có giá trị **-128** khi hiểu là số nguyên signed two's complement 8 bit; cùng mẫu đó có giá trị **128** khi hiểu như một *magnitude không dấu* và cung cấp dấu dương bên ngoài.

Đây là kiến thức rất quan trọng khi xử lý **khóa mật mã, giao thức nhị phân, hash, số nguyên độ dài biến đổi và serialization**. Chỉ thiếu một byte `00` bảo vệ dấu cũng đủ làm một số nguyên dương lớn biến thành âm.

## 1. BigInteger lưu số nguyên, không cố định 8/16/32/64 bit

`BigInteger` lưu số nguyên với dấu và độ dài tùy thuộc trị tuyệt đối, không giống `byte`, `short`, `int` hoặc `long` có độ rộng cố định. Với đầu vào dạng chuỗi:

```java
import java.math.BigInteger;

BigInteger p = new BigInteger("255");     // +255
BigInteger n = new BigInteger("-255");    // -255
BigInteger h = new BigInteger("ff", 16);  // +255
```

Các đoạn khai báo ở trên là **mảnh mã** đặt trong một lớp/phương thức phù hợp, không phải chương trình chạy độc lập. Khả năng biểu diễn số lớn **không có nghĩa các constructor byte đều coi dữ liệu là không dấu**. Constructor khác nhau mang **hợp đồng biểu diễn khác nhau**, dù kết quả đều là `BigInteger`.

| Constructor/API | Ý nghĩa | Giá trị ví dụ |
| --- | --- | --- |
| `new BigInteger(byte[] bytes)` | Byte big-endian, **signed two's complement** | `[FF]` → -1 |
| `new BigInteger(1, byte[] magnitude)` | Byte big-endian, **magnitude không dấu**, ép dấu dương | `[FF]` → +255 |
| `new BigInteger(-1, byte[] magnitude)` | Magnitude không dấu, ép dấu âm | `[FF]` → -255 |
| `new BigInteger("ff", 16)` | Parse chuỗi số có cơ số 16 | +255 |
| `big.toByteArray()` | Mảng byte big-endian, **signed two's complement tối thiểu** | +255 → `[00 FF]` |
| `big.signum()` | Trả dấu của **giá trị đã tạo** | -255 → -1 |

`new BigInteger("ff",16)` và `new BigInteger(new byte[]{(byte)0xff})` **không có cùng kết quả**. Cái đầu đọc chữ số hex theo giá trị dương, cái sau đọc byte bit cao bật như số bù hai âm.

## 2. Hai định dạng đều dùng byte lớn trước (big-endian)

Các constructor mảng byte của `BigInteger` dùng **big-endian**: byte **quan trọng nhất ở đầu mảng**. Ví dụ mảng:

```text
Byte 0   Byte 1
0x01     0x00
```

biểu diễn độ lớn `0x0100 = 256`, không phải `0x0001 = 1`. Quy tắc thứ tự byte áp dụng cho cả **signed two's complement** lẫn **sign–magnitude**; sự khác biệt nằm ở **cách hiểu bit dấu**, không phải cách đảo byte.

Với dữ liệu nhị phân little-endian (chẳng hạn một định dạng file hoặc giao thức tự định nghĩa), **không được truyền thẳng** mảng little-endian vào `BigInteger` rồi mong đúng. Cần đảo vị trí byte thành big-endian theo hợp đồng định dạng, đồng thời vẫn phải chọn cách diễn giải signed hay unsigned thích hợp.

Lưu ý: Big-endian nói về **vị trí các byte có ý nghĩa**, không phải cách các ký tự hex được in trên màn hình. Cũng không phụ thuộc CPU của máy đang chạy little-endian hay big-endian: constructor đã quy định thứ tự mảng byte.

## 3. Bù hai có dấu (two's complement) hoạt động ra sao?

Với một mảng `n` byte, ta có độ rộng `w = 8n` bit. Trong **two's complement**:

- Nếu bit cao nhất bằng 0, giá trị là không âm và được đọc như số nguyên nhị phân thông thường.
- Nếu bit cao nhất bằng 1, giá trị là **âm**, bằng giá trị unsigned của toàn bộ mẫu bit **trừ `2^w`**.

Công thức cho mẫu bit có độ rộng cố định:

```text
U = giá trị unsigned của toàn bộ w bit

signedValue =
    U            nếu bit cao nhất = 0
    U - 2^w      nếu bit cao nhất = 1
```

Ví dụ một byte (`w=8`, `2^8=256`):

| Byte hex | Bit nhị phân | Unsigned | Signed two's complement |
| --- | --- | ---: | ---: |
| `00` | `0000_0000` | 0 | 0 |
| `01` | `0000_0001` | 1 | 1 |
| `7F` | `0111_1111` | 127 | 127 |
| `80` | `1000_0000` | 128 | **-128** |
| `FF` | `1111_1111` | 255 | **-1** |

Với hai byte `FF 7F`, trị unsigned là `65407`; `65407 - 65536 = -129`. Vì vậy:

```java
new BigInteger(new byte[]{(byte) 0xff, 0x7f}); // -129
```

Đây là mảng **16 bit bù hai có dấu**. Chỉ cần nhớ bit đầu tiên và số byte là đủ xác định miền có dấu của mảng: với một byte `FF` cho -1, với hai byte `00 FF` lại cho +255.

## 4. Constructor `BigInteger(byte[] val)`: dữ liệu được hiểu là signed

Chữ ký:

```java
public BigInteger(byte[] val)
```

Nhận một mảng byte **big-endian signed two's complement**. Ví dụ:

```java
BigInteger a = new BigInteger(new byte[]{0x7f});          // +127
BigInteger b = new BigInteger(new byte[]{(byte) 0x80});   // -128
BigInteger c = new BigInteger(new byte[]{(byte) 0xff});   // -1
BigInteger d = new BigInteger(new byte[]{0, (byte) 0x80}); // +128
```

Hai byte `00 80` khác mảng `80`: tiền tố `00` khiến **bit dấu toàn mảng bằng 0**, bảo đảm số dương. Byte `80` ở vị trí sau vẫn đóng góp đúng 128 cho độ lớn.

Nếu `val` rỗng (`new byte[0]`), constructor **ném `NumberFormatException`**: signed two's complement không thể biểu diễn một giá trị từ zero byte đầu vào theo hợp đồng này. Muốn tạo số 0, dùng `BigInteger.ZERO` hoặc mảng chứa một byte `00`.

Các giá trị `byte` trong Java tự chúng có dấu khi đọc như số nguyên đơn lẻ (`(byte)0xff == -1`). Tuy nhiên, khi tạo `BigInteger` từ mảng, Java ghép các **mẫu 8 bit** theo thứ tự, rồi diễn giải **dấu của toàn số**. Không được cộng các giá trị `byte` có dấu từng phần để mô phỏng kết quả mảng bù hai.

## 5. Constructor `BigInteger(int signum, byte[] magnitude)`: dấu riêng, độ lớn không dấu

Chữ ký:

```java
public BigInteger(int signum, byte[] magnitude)
```

Trong đó:

- **`signum`** chỉ có thể là `-1` (âm), `0` (zero), `1` (dương).
- **`magnitude`** là mảng byte big-endian chứa **độ lớn không dấu**, ngay cả khi bit cao nhất của byte đầu tiên bằng 1.
- Giá trị được tạo về mặt toán học là **`signum × magnitudeValue`** (với các điều kiện nhất quán đối với zero).

```java
byte[] bits = {(byte)0xff};

BigInteger positive = new BigInteger(1, bits);  // +255
BigInteger negative = new BigInteger(-1, bits); // -255
```

Đây chính là cách tạo số **dương** từ một mảng byte có bit đầu bật mà **không cần thêm byte `00`** vào input.

```java
BigInteger p = new BigInteger(1, new byte[]{(byte)0x80}); // +128
BigInteger n = new BigInteger(-1, new byte[]{(byte)0x80}); // -128
```

**Cảnh báo:** `signum = -1` **không có nghĩa** mảng `magnitude` cũng phải là dạng bù hai của số âm. Với magnitude `FF`, dấu -1 tạo **-255**, không phải -1. Dữ liệu đầu vào phải đúng chuẩn sign–magnitude đã thỏa thuận.

## 6. Zero và quy tắc nhất quán của `signum`

Giá trị zero có độ lớn 0, dù bạn biểu diễn bằng `byte[]{0}`, mảng nhiều byte `00`, hoặc thậm chí mảng magnitude rỗng theo overload sign–magnitude.

| `signum` | Magnitude | Kết quả |
| ---: | --- | --- |
| `0` | `[00]` | 0 |
| `0` | `[00, 00]` | 0 |
| `+1` | `[00]` hoặc rỗng | 0 |
| `-1` | `[00]` | 0 |
| `0` | `[01]` | **`NumberFormatException`** |
| `2` hoặc `-2` | Bất kỳ magnitude | **`NumberFormatException`** |

Quy tắc quan trọng: **không thể yêu cầu dấu 0 nhưng magnitude khác 0**; `new BigInteger(0,new byte[]{1})` bị từ chối. Nếu magnitude thực sự bằng 0 nhưng signum là -1, kết quả BigInteger vẫn là **zero chuẩn hóa**, không có “negative zero” số nguyên.

```java
BigInteger zero = new BigInteger(-1, new byte[]{0, 0});
System.out.println(zero.signum()); // 0
```

Điều này khác floating-point `-0.0`: số nguyên `BigInteger` **không có hai giá trị zero khác dấu**. Khi dùng API sign–magnitude, cần kiểm tra việc gán dấu 0 nhất quán với magnitude để tránh tạo ra ngoại lệ không mong muốn.

Phân biệt thêm: `new BigInteger(new byte[0])` **lỗi** vì constructor signed cần ít nhất một byte; trong khi `new BigInteger(1,new byte[0])` cho giá trị **0**, như chương trình QA bên dưới.

## 7. Bảng đối chiếu từ cùng một mảng byte

| Mảng byte (hex) | `new BigInteger(bytes)` | `new BigInteger(1,bytes)` | `new BigInteger(-1,bytes)` |
| --- | ---: | ---: | ---: |
| `00` | 0 | 0 | 0 |
| `01` | 1 | 1 | -1 |
| `7F` | 127 | 127 | -127 |
| `80` | **-128** | **128** | -128 |
| `FF` | **-1** | **255** | **-255** |
| `00 80` | 128 | 128 | -128 |
| `FF 7F` | -129 | 65407 | -65407 |

Dòng `FF 7F` là ví dụ quan trọng: dưới cách đọc **signed 16 bit** nó là -129; dưới cách đọc **magnitude** nó là `0xFF7F = 65407`, và dấu ngoài quyết định +65407 hoặc -65407. Việc hai constructor cho kết quả **cùng âm** trong trường hợp `80` và signum -1 chỉ là một trùng hợp của giá trị cụ thể, không làm chúng tương đương tổng quát.

Nếu đầu vào đến từ mạng/giao thức, bắt buộc biết rõ trường đó dùng **signed two's complement** hay **unsigned magnitude**. Không thể suy ra cách đọc đúng chỉ từ tên biến `bytes`, số byte hoặc việc chúng được in thành chữ số hex.

## 8. `BigInteger.toByteArray()`: signed two's complement tối thiểu

Để xuất lại `BigInteger` về byte, dùng:

```java
byte[] encoded = bigInteger.toByteArray();
```

API này trả về mảng **big-endian signed two's complement**, **số byte tối thiểu cần thiết** để giữ giá trị và dấu. Nó **không** trả magnitude unsigned đơn thuần và **không** giữ nguyên số byte đã nhập vào constructor trước đó.

Ví dụ:

| BigInteger value | `HexFormat.of().formatHex(value.toByteArray())` | Giải thích |
| ---: | --- | --- |
| 0 | `00` | Zero cần một byte `00` |
| +1 | `01` | Số dương nhỏ |
| +127 | `7f` | Bit cao = 0 |
| **+128** | **`0080`** | Thêm `00` để không bị hiểu -128 |
| **+255** | **`00ff`** | Thêm `00` bảo vệ dấu |
| -1 | `ff` | Bù hai một byte |
| -128 | `80` | Giá trị âm hợp lệ với một byte |
| **-129** | **`ff7f`** | Cần byte `ff` giữ dấu âm |

`toByteArray` đảm bảo *độ dài tối thiểu*, nên đừng coi `value.toByteArray().length == 4` hay 8 là bất biến chỉ vì giá trị được dùng trong một protocol 32/64 bit.

Ví dụ quan trọng:

```java
BigInteger positive = new BigInteger(1, new byte[]{(byte)0xff});
byte[] encoded = positive.toByteArray();
// encoded gồm hai byte [00 FF], không phải một byte [FF].
```

Nếu truyền `encoded` cho `new BigInteger(encoded)`, ta nhận lại +255 chính xác. Nếu tự ý xóa `00` rồi dùng signed constructor, ta lại nhận -1.

## 9. Vì sao cần byte `00` đầu với số dương?

Với signed two's complement, bit cao nhất của byte đầu tiên **quyết định dấu**. Số dương 128 có mẫu nhị phân `1000_0000`; nếu chỉ có một byte thì mẫu bit đó là **-128**. Để giữ dấu dương trong định dạng signed, thêm byte `00` phía trước:

```text
Magnitude 128:              80
Signed two's complement: 00 80  => +128
Signed two's complement:    80  => -128

Magnitude 255:              FF
Signed two's complement: 00 FF  => +255
Signed two's complement:    FF  => -1
```

Byte `00` đầu không phải padding vô nghĩa trong signed encoding; nó có thể là **điều kiện để đọc đúng dấu**. Nhưng khi dữ liệu thực sự là **unsigned magnitude**, byte `00` bảo vệ dấu có thể không được mong đợi; vì thế cùng một mảng được mã hóa theo hai contract khác nhau.

Không nên nghĩ `0x80` “mặc định là -128 trong mọi ngữ cảnh”. Nó là mẫu bit; **ý nghĩa số học tùy cách diễn giải**. Cách diễn giải đó phải được chọn khi tạo `BigInteger`.

## 10. Byte `FF` đầu với số âm và sign extension

Hai's complement có quy tắc **mở rộng dấu** (*sign extension*): để tăng độ rộng mà vẫn giữ một giá trị âm, bổ sung các byte `FF` ở bên trái; với giá trị không âm, bổ sung `00`.

```text
-1 ở 8 bit:          FF
-1 ở 16 bit:      FF FF
-1 ở 32 bit: FF FF FF FF

+255 ở 16 bit:      00 FF
+255 ở 32 bit: 00 00 00 FF
```

`BigInteger.toByteArray()` bỏ các byte mở rộng dấu **thừa**, nhưng giữ byte tối thiểu còn đủ thể hiện dấu. Ví dụ -1 được biểu diễn bằng một byte `FF`, không phải mảng vô hạn byte `FF`. -129 cần hai byte `FF 7F`, vì một byte signed không đủ chứa -129.

Với một hệ thống gửi đúng 4 byte cho signed 32 bit, mảng `FF` phải được **mở rộng thành `FF FF FF FF`** nếu muốn truyền -1. Ngược lại, nếu giao thức dùng unsigned 32 bit, bạn thường cần **zero-extension**; truyền `FF FF FF FF` trong signed BigInteger constructor sẽ cho -1 thay vì unsigned 4294967295.

## 11. `signum` trong constructor không đồng nghĩa với `signum()` của kết quả

`new BigInteger(signum,magnitude)` nhận một **tham số dấu được yêu cầu**. Sau khi tạo, `result.signum()` trả dấu của **giá trị thực sự**, luôn là -1, 0 hoặc 1.

Ví dụ:

```java
BigInteger zero = new BigInteger(-1, new byte[]{0});
System.out.println(zero.signum()); // 0

BigInteger negative = new BigInteger(-1, new byte[]{1});
System.out.println(negative.signum()); // -1
```

Không nên gán `signum` dựa trên một byte có dấu như `(byte)0x80 == -128`, vì constructor chỉ nhận đúng -1, 0, 1; -128 là một **giá trị byte**, không phải dấu hợp lệ của `BigInteger`.

Nếu bạn đang chuyển dữ liệu từ hệ thống có trường `sign` riêng và mảng `magnitude`, hãy ánh xạ `sign` sang -1/0/1 theo format, kiểm tra mismatch zero, rồi gọi constructor. Không dùng bit đầu mảng magnitude để suy đoán dấu nếu contract đã có dấu riêng.

## 12. Các overload có offset và length

Java 17 có overload nhận **một đoạn của mảng**, tránh việc bắt buộc tạo bản sao bằng `Arrays.copyOfRange`:

```java
BigInteger signedPart =
        new BigInteger(byte[] val, int off, int len);

BigInteger magnitudePart =
        new BigInteger(int signum, byte[] magnitude, int off, int len);
```

Hai dòng trên là **chữ ký ý niệm**, không phải cú pháp khai báo biến hợp lệ — chúng dùng để liệt kê hình thức constructor.

Ví dụ runnable khi đặt trong phương thức:

```java
byte[] data = {(byte)0x7e, 0x00, (byte)0x80, 0x7f};

BigInteger signed = new BigInteger(data, 1, 2);
// Đọc [00,80] thành +128 (signed two's complement).

BigInteger magnitude = new BigInteger(1, data, 2, 1);
// Đọc [80] thành +128 (positive magnitude).
```

`off` là **chỉ số bắt đầu**, `len` là **số byte cần đọc**, không phải chỉ số kết thúc. Nếu `off` và `len` vượt mảng, API ném lỗi chỉ số/đoạn. Với signed constructor, đoạn rỗng không hợp lệ vì không có byte biểu diễn; với magnitude constructor, độ lớn rỗng có thể tạo zero nếu dấu hợp lệ.

Giống nguyên lý ở phần đầu, cả hai overload vẫn sử dụng **big-endian** trong phạm vi đoạn đã chọn. Việc truyền slice không thay đổi quy tắc signed hay magnitude, nên cần kiểm tra đúng trường dữ liệu của bản ghi.

## 13. `BigInteger("ff",16)` khác `BigInteger(byte[]{FF})` thế nào?

Một chuỗi chữ số hex có **ngữ nghĩa số học**, không phải một mảng byte signed:

```java
BigInteger byText = new BigInteger("ff", 16); // +255

byte[] oneByte = {(byte)0xff};
BigInteger bySigned = new BigInteger(oneByte); // -1
BigInteger byMagnitude = new BigInteger(1, oneByte); // +255
```

Vì `"ff"` không có dấu `-`, constructor chuỗi hiểu là độ lớn 255. Với constructor mảng signed, byte `FF` là -1. Với sign–magnitude, dấu 1 làm byte `FF` biểu diễn +255.

Đặc biệt trong hệ thống lưu hash, nếu bạn chuyển một mảng byte sang **chuỗi hex** rồi dùng `new BigInteger(hex,16)`, kết quả sẽ là **dương** (trừ khi chuỗi có dấu âm); nếu dùng `new BigInteger(bytes)` trực tiếp, kết quả có thể âm. Đây là lý do phổ biến khiến cùng một digest có hai biểu diễn số nguyên khác nhau.

Nếu format thực chất là **bytes không dấu** chứ không phải số nguyên có dấu, phương thức rõ ý nghĩa là `new BigInteger(1,bytes)`. Dù vậy, hash/identifier có thể cần **giữ nguyên độ dài byte và zero đầu**, trong khi `BigInteger` biểu diễn **giá trị số** và có thể chuẩn hóa mất zero padding khi serialize lại.

## 14. BigInteger là giá trị số, không phải kho byte giữ nguyên định dạng

Giả sử input là ba byte:

```text
00 00 FF
```

Nếu gọi:

```java
BigInteger value =
        new BigInteger(1, new byte[]{0, 0, (byte)0xff});
// value = 255.
```

thì `value.toByteArray()` trả **`00 FF`**, không phải `00 00 FF`. Không có cách nào từ riêng giá trị số 255 biết input ban đầu có bao nhiêu byte `00` đệm trước đó.

Vì vậy, nếu protocol có **trường cố định 16/32 byte**, việc lưu duy nhất dưới dạng `BigInteger` là chưa đủ cho round-trip *byte-for-byte*. Bạn phải lưu **độ dài định dạng** hoặc quy tắc pad/cắt byte, và tái tạo đúng số byte lúc xuất. Nếu format dùng big-endian unsigned 32 byte, cần **zero-pad**, không phải dấu-extend `FF`. Nếu format dùng signed two's complement fixed-width, cần **sign-extend**.

Đừng bỏ byte `00` đầu một cách vô điều kiện: với mảng signed, đó có thể là byte thiết yếu để phân biệt +255 với -1. Chỉ bỏ khi bạn đã chủ động đổi từ signed representation sang **unsigned magnitude** và đích cũng hiểu theo contract đó.

## 15. Cẩn thận khi convert qua primitive `byte`, `int`, `long`

Java `byte` là signed trong phạm vi -128..127. Dù một byte `FF` tương ứng 255 khi xem unsigned, phép đọc trực tiếp:

```java
byte raw = (byte)0xff;
System.out.println(raw);                    // -1
System.out.println(Byte.toUnsignedInt(raw)); // 255
```

`Byte.toUnsignedInt` chỉ chuyển **một byte** thành giá trị 0..255 để quan sát/xử lý; nó không biến `new BigInteger(byte[])` thành unsigned constructor.

Ngoài ra, `BigInteger.intValue()` và `longValue()` có thể **mất các bit cao** với giá trị lớn. Ví dụ:

```java
BigInteger big = new BigInteger(1, new byte[]{
        0x01, 0x00, 0x00, 0x00, 0x00
}); // 2^32.
int lossy = big.intValue(); // 0 vì chỉ giữ 32 bit thấp.
```

Nếu cần chuyển sang primitive **mà không chấp nhận mất dữ liệu**, dùng `intValueExact()` hoặc `longValueExact()` và xử lý `ArithmeticException` khi giá trị ngoài dải. Không nên “sửa” một số âm xuất hiện sai do constructor signed bằng cách ép sang `long`/mask sau đó: trước tiên phải xác định lại **cách diễn giải byte có đúng format hay không**.

## 16. Fixed-width signed encoding: phải tự kiểm tra dải

`BigInteger.toByteArray()` trả **độ dài tối thiểu**, không thể tự bảo đảm tạo đúng 2, 4, 8 hay 32 byte. Với yêu cầu **signed two's complement w byte**, dải chính xác là:

```text
min = -2^(8*w-1)
max =  2^(8*w-1)-1
```

Chẳng hạn signed **một byte** chỉ chứa -128..127. +128 cần ít nhất **hai byte `00 80`**. Không được cắt chuỗi `00 80` thành `80` rồi giải mã signed vì sẽ thành -128.

Một phương thức mẫu (đặt trong lớp có import `java.util.Arrays`, `java.math.BigInteger`) để ghi đúng **w byte signed**:

```java
static byte[] toFixedSigned(BigInteger value, int width) {
    if (width <= 0 || width > Integer.MAX_VALUE / 8) {
        throw new IllegalArgumentException("invalid width");
    }
    int bits = width * 8;
    BigInteger bound = BigInteger.ONE.shiftLeft(bits - 1);
    if (value.compareTo(bound.negate()) < 0
            || value.compareTo(bound.subtract(BigInteger.ONE)) > 0) {
        throw new ArithmeticException("out of signed range");
    }
    byte[] minimal = value.toByteArray();
    byte[] result = new byte[width];
    Arrays.fill(result, value.signum() < 0 ? (byte) 0xff : (byte) 0x00);
    System.arraycopy(minimal, 0, result,
            width - minimal.length, minimal.length);
    return result;
}
```

Ở đây việc kiểm tra dải **trước** bảo đảm mảng `minimal` không dài hơn `width` trong trường hợp hợp lệ; việc copy không cắt byte có nghĩa. Ví dụ:

```text
toFixedSigned(+128, 2) → 00 80
toFixedSigned(-1,   2) → FF FF
toFixedSigned(0,    2) → 00 00
toFixedSigned(+128, 1) → ArithmeticException
```

Đây là **mảnh hàm hỗ trợ**, không được gọi trong chương trình runnable ở phần sau; các ví dụ dự kiến có thể được đưa thành unit test theo contract signed fixed-width của giao thức. Với input không tin cậy, nên đặt **giới hạn độ dài hợp lý** ngoài việc chặn width <= 0 để tránh cấp phát mảng khổng lồ.

Nếu định dạng đích **unsigned**, không dùng bộ kiểm tra dải signed này; unsigned w byte có dải `0..2^(8*w)-1`, phần đệm phải là `00`, và constructor giải mã nên là `new BigInteger(1,bytes)`.

## 17. Zero, sign byte và các sai lầm khi serialize unsigned

Bài toán thường gặp: một giao thức nói rõ trường payload là **unsigned 256-bit integer**. Khi đọc:

```java
byte[] payload = {(byte)0x80, 0x00}; // Ví dụ thu nhỏ.
BigInteger value = new BigInteger(1, payload); // +32768.
```

Nếu sai sót dùng `new BigInteger(payload)`, byte đầu `0x80` đặt bit dấu 1 và kết quả là **-32768** theo signed 16-bit. Do đó **constructor có dấu** là không phù hợp với contract unsigned.

Khi ghi unsigned ra mảng độ rộng cố định, có hai quy tắc quan trọng:

1. **Giá trị phải không âm và vừa đủ w byte không dấu.** Không âm phải kiểm tra `value.signum() >= 0`, giới hạn lớn nhất là `2^(8w)-1`.
2. **Không được nhầm byte `00` đầu của `toByteArray()` với một byte dữ liệu payload bắt buộc.** Khi giá trị dương có bit cao bật, `toByteArray()` có thể thêm `00` để bảo vệ dấu. Trong unsigned fixed-width payload, bạn cần bỏ byte bảo vệ dấu **nếu và chỉ nếu** đã xác nhận giá trị và số byte hợp lệ, rồi zero-pad tới đúng độ dài.

Ví dụ:

```java
BigInteger v = BigInteger.valueOf(255);
byte[] signed = v.toByteArray(); // [00, FF].
byte[] unsignedOneByte = {(byte)0xff}; // [FF], theo contract unsigned.
BigInteger restored = new BigInteger(1, unsignedOneByte); // +255.
```

Nếu `restored` được tạo bằng signed constructor thì lại thành -1. Tính nhất quán **encoder và decoder** là thiết yếu; “byte giống nhau” không đủ để chứng minh “giá trị giống nhau”.

## 18. Chương trình Java 17+ độc lập, kiểm tra đầy đủ hành vi chính

Lưu thành **`BigIntegerBytesDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.HexFormat;

public class BigIntegerBytesDemo {
    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes);
    }

    static String typeOfError(Runnable action) {
        try {
            action.run();
            return "NO_ERROR";
        } catch (NumberFormatException | IndexOutOfBoundsException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        byte[] highBit = {(byte) 0x80};
        byte[] allOnes = {(byte) 0xff};
        System.out.println("signed80=" + new BigInteger(highBit));
        System.out.println("positive80=" + new BigInteger(1, highBit));
        System.out.println("signedFF=" + new BigInteger(allOnes));
        System.out.println("positiveFF=" + new BigInteger(1, allOnes));
        System.out.println("negativeMagnitudeFF=" + new BigInteger(-1, allOnes));
        System.out.println("signed0080=" + new BigInteger(new byte[]{0, (byte) 0x80}));
        System.out.println("signedFF7F=" + new BigInteger(new byte[]{(byte) 0xff, 0x7f}));
        System.out.println("unsignedJavaByte=" + Byte.toUnsignedInt(allOnes[0]));

        System.out.println("int128Bytes=" + hex(BigInteger.valueOf(128).toByteArray()));
        System.out.println("int255Bytes=" + hex(BigInteger.valueOf(255).toByteArray()));
        System.out.println("int127Bytes=" + hex(BigInteger.valueOf(127).toByteArray()));
        System.out.println("intMinus128Bytes=" + hex(BigInteger.valueOf(-128).toByteArray()));
        System.out.println("intMinus129Bytes=" + hex(BigInteger.valueOf(-129).toByteArray()));
        System.out.println("intMinus1Bytes=" + hex(BigInteger.valueOf(-1).toByteArray()));
        System.out.println("intZeroBytes=" + hex(BigInteger.ZERO.toByteArray()));
        System.out.println("positiveInputLeadingZeros="
                + new BigInteger(1, new byte[]{0, 0, (byte) 0xff}));
        System.out.println("normalizedLeadingZeros="
                + hex(new BigInteger(1, new byte[]{0, 0, (byte) 0xff}).toByteArray()));

        System.out.println("signZeroMagnitudeZero="
                + new BigInteger(0, new byte[]{0, 0}));
        System.out.println("signMinusOneMagnitudeZero="
                + new BigInteger(-1, new byte[]{0, 0}));
        System.out.println("signZeroNonzeroError=" + typeOfError(
                () -> new BigInteger(0, new byte[]{1})));
        System.out.println("signOutOfRangeError=" + typeOfError(
                () -> new BigInteger(2, new byte[]{1})));
        System.out.println("signedEmptyError=" + typeOfError(
                () -> new BigInteger(new byte[0])));
        System.out.println("magnitudeEmptyZero=" + new BigInteger(1, new byte[0]));

        byte[] mixed = {(byte) 0x7e, (byte) 0x00, (byte) 0x80, (byte) 0x7f};
        System.out.println("signedSlice=" + new BigInteger(mixed, 1, 2));
        System.out.println("magnitudeSlice=" + new BigInteger(1, mixed, 2, 1));
        System.out.println("hexStringPositive=" + new BigInteger("ff", 16));

        BigInteger[] numbers = {
                BigInteger.ZERO, BigInteger.ONE, BigInteger.valueOf(128),
                BigInteger.valueOf(-129), BigInteger.ONE.shiftLeft(100).negate()
        };
        boolean roundTrip = true;
        for (BigInteger n : numbers) {
            roundTrip &= n.equals(new BigInteger(n.toByteArray()));
        }
        System.out.println("signedRoundTrip=" + roundTrip);
        System.out.println("signumOfNegative="
                + BigInteger.valueOf(-129).signum());
        System.out.println("signumOfZero=" + BigInteger.ZERO.signum());
        System.out.println("sourceArrayUnchanged="
                + Arrays.equals(highBit, new byte[]{(byte)0x80}));
    }
}
```

Chạy trên Java 17:

```bash
javac --release 17 -encoding UTF-8 BigIntegerBytesDemo.java
java BigIntegerBytesDemo
```

Stdout chính xác:

```text
signed80=-128
positive80=128
signedFF=-1
positiveFF=255
negativeMagnitudeFF=-255
signed0080=128
signedFF7F=-129
unsignedJavaByte=255
int128Bytes=0080
int255Bytes=00ff
int127Bytes=7f
intMinus128Bytes=80
intMinus129Bytes=ff7f
intMinus1Bytes=ff
intZeroBytes=00
positiveInputLeadingZeros=255
normalizedLeadingZeros=00ff
signZeroMagnitudeZero=0
signMinusOneMagnitudeZero=0
signZeroNonzeroError=NumberFormatException
signOutOfRangeError=NumberFormatException
signedEmptyError=NumberFormatException
magnitudeEmptyZero=0
signedSlice=128
magnitudeSlice=128
hexStringPositive=255
signedRoundTrip=true
signumOfNegative=-1
signumOfZero=0
sourceArrayUnchanged=true
```

Các nhóm kết quả cần chú ý:

1. **`signed80=-128` vs `positive80=128`** và **`signedFF=-1` vs `positiveFF=255`** chứng minh khác biệt cốt lõi giữa hai constructor.
2. **`negativeMagnitudeFF=-255`** cho thấy sign–magnitude với dấu -1 **không** diễn giải lại byte `FF` thành -1 trước khi đổi dấu.
3. **`signed0080=128`, `signedFF7F=-129`** minh họa byte dẫn đầu quyết định dấu trong two's complement.
4. **`int128Bytes=0080`, `int255Bytes=00ff`** cho thấy `toByteArray()` thêm `00` để bảo vệ dấu; các dòng `intMinus...` cho biết các giá trị âm và sign extension tối thiểu.
5. **`positiveInputLeadingZeros=255`, `normalizedLeadingZeros=00ff`** cho thấy `BigInteger` không nhớ độ dài/padding ban đầu.
6. **`signZeroMagnitudeZero=0`, `signMinusOneMagnitudeZero=0`** cho thấy zero được chuẩn hóa; các dòng `...Error=NumberFormatException` minh họa dấu không hợp lệ hoặc mâu thuẫn với magnitude.
7. **`signedEmptyError` vs `magnitudeEmptyZero`** phân biệt mảng rỗng với hai constructor.
8. **`signedSlice` và `magnitudeSlice`** minh họa lựa chọn một đoạn dữ liệu trong mảng; **`signedRoundTrip=true`** xác minh cặp `toByteArray` → signed constructor giữ lại giá trị `BigInteger` của các ví dụ.
9. **`signumOfNegative=-1`**, **`signumOfZero=0`** cho thấy `signum()` lấy dấu giá trị thực, không sao chép đơn giản tham số signum ban đầu.

Chương trình dùng `HexFormat` (có trong Java 17) để in byte theo hex, tránh nhầm các `byte` có giá trị âm khi in số thập phân bằng `println`.

## 19. Hai phép round-trip khác nhau: theo giá trị và theo bytes

**Round-trip theo giá trị** (value-preserving) với signed constructor:

```java
BigInteger n = new BigInteger("-129");
BigInteger restored = new BigInteger(n.toByteArray());
// n.equals(restored) == true.
```

Đây là đường đi đúng theo hợp đồng của `BigInteger.toByteArray()`, vì cả hai đầu đều dùng signed two's complement big-endian.

**Round-trip theo bytes** (byte-for-byte) lại khác. Chẳng hạn:

```java
byte[] input = {0, 0, (byte) 0xff};
BigInteger value = new BigInteger(1, input);
byte[] output = value.toByteArray();
// output là [00, FF], ngắn hơn input [00, 00, FF].
```

Ta vẫn có **giá trị +255**, nhưng `input` và `output` khác độ dài. Đây **không phải lỗi BigInteger**: lớp biểu diễn giá trị số, không lưu lại cách pad đã dùng ở input.

Nếu cần giữ nguyên bytes của một giao thức, **lưu raw byte[] và metadata format** cùng với BigInteger hoặc áp dụng encoder fixed-width chuyên dụng. Khi so sánh tính đúng, tách điều kiện “đúng giá trị” khỏi điều kiện “đúng byte string”.

## 20. Những lỗi phổ biến và cách sửa

| Nhầm lẫn | Hệ quả | Giải pháp |
| --- | --- | --- |
| Tưởng `new BigInteger(bytes)` luôn đọc unsigned | Byte đầu `80`/ `FF` tạo số âm | Dùng `new BigInteger(1,bytes)` khi contract là unsigned |
| Tưởng `new BigInteger(-1,bytes)` nhận bytes bù hai âm | Magnitude `FF` cho -255, không phải -1 | Truyền **độ lớn không dấu** và dấu riêng |
| Bỏ byte `00` đầu từ signed representation | +255 có thể bị đọc thành -1 | Chỉ bỏ nếu đã đổi sang unsigned format |
| Giữ nguyên `toByteArray()` để gửi đúng 32 byte | Kết quả có độ dài biến thiên | Mã hóa fixed-width với kiểm tra dải/padding |
| Nghĩ `byte` Java âm thì mảng magnitude sẽ âm | Constructor sign–magnitude đọc **mẫu bit unsigned** | Dùng đúng constructor, không cộng giá trị byte có dấu |
| Không biết input big-endian hay little-endian | Mọi byte có thể bị đọc sai thứ tự | Quy định và chuyển byte order đúng |
| Tưởng `signum=0` luôn được chấp nhận | Magnitude khác zero gây NumberFormatException | Kiểm tra tính nhất quán dấu/magnitude |
| Tưởng `signum=-1` với magnitude zero tạo -0 | BigInteger chỉ có zero, không có negative zero | Dựa vào `result.signum()` sau khi tạo |
| Truyền `new byte[0]` cho signed constructor | `NumberFormatException` | Dùng `BigInteger.ZERO` hoặc `{0}` |
| Nghĩ `new BigInteger("ff",16)` giống signed byte `FF` | Text hex là +255, signed byte FF là -1 | Phân biệt parse chuỗi với parse binary |
| Ép `BigInteger` lớn bằng `intValue()` | Có thể mất các bit cao, trả sai số | Dùng `intValueExact()` nếu cần kiểm tra |
| Kiểm thử chỉ với byte đầu dưới `80` | Bỏ sót lỗi sai dấu | Luôn test `7F`, `80`, `FF`, `00 80`, `FF 7F` |

## 21. Câu hỏi tự kiểm tra

1. **`new BigInteger(new byte[]{(byte)0x80})` cho giá trị gì?** -128, vì mảng một byte signed two's complement có bit dấu bằng 1.
2. **Làm thế nào đọc đúng +128 từ mảng `{(byte)0x80}`?** Dùng `new BigInteger(1,bytes)` hoặc truyền signed mảng `{0,(byte)0x80}`.
3. **`new BigInteger(new byte[]{(byte)0xff})` cho gì?** -1.
4. **`new BigInteger(-1,new byte[]{(byte)0xff})` cho gì?** -255, vì mảng được đọc là magnitude 255 và dấu riêng là âm.
5. **Vì sao `BigInteger.valueOf(255).toByteArray()` có hai byte `00 FF`?** Byte `00` giữ bit dấu 0 để signed constructor đọc được +255.
6. **Tại sao `BigInteger.valueOf(-129).toByteArray()` là `FF 7F`?** Một byte signed không đủ lưu -129; cần biểu diễn bù hai 16 bit.
7. **`BigInteger.ZERO.toByteArray()` là mảng rỗng hay `[00]`?** `[00]`; có ít nhất một byte để biểu diễn zero theo signed encoding.
8. **`new BigInteger(0,new byte[]{1})` hợp lệ không?** Không. Nó ném NumberFormatException vì dấu 0 mâu thuẫn magnitude khác 0.
9. **`new BigInteger(-1,new byte[]{0})` có tạo negative zero không?** Không. Giá trị là 0 và `signum()` trả 0.
10. **Constructor signed và sign–magnitude có dùng thứ tự byte khác nhau không?** Không, cả hai đều big-endian; khác ở cách hiểu dấu.
11. **`new BigInteger("ff",16)` có giống `new BigInteger(new byte[]{(byte)0xff})`?** Không. Cái đầu +255, cái sau -1.
12. **Vì sao parse `[00 00 FF]` rồi `toByteArray()` không giữ ba byte?** BigInteger giữ giá trị số; `toByteArray` xuất signed representation tối thiểu.
13. **Nếu giao thức yêu cầu unsigned 32 byte, có nên dùng thẳng `toByteArray()`?** Không. Phải kiểm tra giá trị không âm và nằm trong 256 bit, loại byte dấu bảo vệ nếu cần rồi zero-pad chính xác 32 byte.
14. **Để đọc unsigned hash/digest có bit đầu bật, chọn constructor nào?** `new BigInteger(1,hashBytes)` khi muốn diễn giải hash như độ lớn không dấu, đồng thời giữ bytes/độ dài riêng nếu cần round-trip.

**Ghi nhớ:** `new BigInteger(byte[])` nhận **signed two's complement big-endian**; `new BigInteger(signum,byte[])` nhận **dấu riêng và magnitude unsigned big-endian**. `toByteArray()` luôn trả **signed two's complement tối thiểu**, có thể thêm `00` để giữ số dương hoặc bớt padding so với dữ liệu gốc. Khi làm việc với binary protocol, hãy xác định **signed/unsigned, width và byte order** ngay từ đầu; chọn đúng constructor, kiểm tra biên và chỉ dùng encoder fixed-width nếu định dạng yêu cầu.

# Dấu phân cách, tiền tố và hậu tố của dữ liệu hệ mười sáu trong Java 17

Java cho phép viết số nguyên và số dấu phẩy động theo hệ mười sáu (hexadecimal) ngay trong mã nguồn. Cách viết này thường xuất hiện khi làm việc với byte, bit mask, màu sắc, mã trạng thái, dữ liệu nhị phân, địa chỉ hoặc các giá trị cần biểu diễn rõ từng nhóm bit.

Một literal hệ mười sáu có thể có ba thành phần cần nhận diện:

- **Tiền tố** `0x` hoặc `0X`: cho biết các chữ số tiếp theo được đọc theo hệ 16.
- **Dấu phân cách** `_`: nhóm các chữ số để dễ đọc; không làm thay đổi giá trị.
- **Hậu tố** như `L` đối với số nguyên hoặc `F`/`D` đối với số dấu phẩy động: xác định kiểu literal trong những trường hợp tương ứng.

Bài này tập trung vào cú pháp còn áp dụng trong Java 17, cách đọc giá trị, các giới hạn đặt dấu gạch dưới, sự khác nhau giữa `int` và `long`, hex floating-point, cùng cách chuyển đổi chuỗi hệ 16 khi chương trình chạy.

## 1. Nhận diện chữ số và tiền tố hệ mười sáu

Hệ mười sáu dùng 16 ký hiệu:

| Ký hiệu | Giá trị thập phân | Ký hiệu | Giá trị thập phân |
|---|---:|---|---:|
| `0` | 0 | `8` | 8 |
| `1` | 1 | `9` | 9 |
| `2` | 2 | `A` hoặc `a` | 10 |
| `3` | 3 | `B` hoặc `b` | 11 |
| `4` | 4 | `C` hoặc `c` | 12 |
| `5` | 5 | `D` hoặc `d` | 13 |
| `6` | 6 | `E` hoặc `e` | 14 |
| `7` | 7 | `F` hoặc `f` | 15 |

Mỗi vị trí có trọng số là một lũy thừa của 16. Ví dụ:

```text
0x2A = 2 × 16 + 10 = 42
0x100 = 1 × 16² = 256
0xFF = 15 × 16 + 15 = 255
```

Trong Java, tiền tố hệ mười sáu là:

- `0x` — chữ `x` thường.
- `0X` — chữ `X` hoa.

Ví dụ:

~~~java
int decimal = 42;
int hexLower = 0x2a;
int hexUpper = 0X2A;

System.out.println(decimal); // 42
System.out.println(hexLower); // 42
System.out.println(hexUpper); // 42
~~~

Ba biến có cùng giá trị. Tiền tố `0x` không được lưu vào giá trị số; nó chỉ cho compiler biết cách đọc literal trong mã nguồn.

Không dùng các dạng như `0h2A`, `#2A` hoặc `2Ah` để viết integer literal hệ mười sáu trong Java. Những dạng đó có thể xuất hiện trong một số ngôn ngữ hoặc định dạng khác, nhưng không phải cú pháp integer literal Java.

### 1.1. Phân biệt literal hệ mười sáu với số thập phân

~~~java
int a = 26;    // Hệ 10
int b = 0x1A;  // Hệ 16: 1 × 16 + 10 = 26
int c = 032;   // Hệ 8: 3 × 8 + 2 = 26
int d = 0b11010; // Hệ 2: 16 + 8 + 2 = 26
~~~

Kết quả:

~~~text
a = 26
b = 26
c = 26
d = 26
~~~

Giá trị trong bộ nhớ không mang nhãn “hệ 16” hay “hệ 10”. Hệ cơ số chỉ ảnh hưởng cách viết literal hoặc cách hiển thị/chuyển đổi số.

## 2. Dấu phân cách chữ số bằng dấu gạch dưới

Java cho phép dùng dấu gạch dưới `_` bên trong literal số để chia nhóm chữ số. Điều này hữu ích khi literal dài hoặc có ý nghĩa theo từng byte, từng word.

Ví dụ:

~~~java
int color = 0xFF_33_66;
int flags = 0b1010_0001;
long addressMask = 0x0000_FFFF_FFFF_FFFFL;
~~~

Các literal sau có cùng giá trị tương ứng với dạng không có dấu gạch dưới:

~~~java
int a = 0xFF33;
int b = 0xFF_33;
int c = 0xF_F_3_3;
~~~

Dấu `_` chỉ phục vụ người đọc. Compiler bỏ qua nó khi phân tích literal; nó không tạo thêm bit hay thay đổi giá trị.

### 2.1. Đặt dấu phân cách giữa các chữ số

Các ví dụ hợp lệ:

~~~java
int a = 0xCA_FE;
int b = 0xDEAD_BEEF;
long c = 0x1234_5678_9ABC_DEF0L;
int d = 0x1_0000;
~~~

Có thể dùng nhiều dấu gạch dưới liên tiếp nếu chúng vẫn nằm giữa các chữ số:

~~~java
int value = 0xCA__FE;
~~~

Dù hợp lệ, không nên lạm dụng nhiều dấu liên tiếp vì làm giảm khả năng đọc. Một dấu phân cách giữa các nhóm có ý nghĩa thường rõ ràng hơn.

### 2.2. Những vị trí không được đặt dấu gạch dưới

Dấu gạch dưới phải nằm **giữa các chữ số**. Không đặt nó sát đầu/cuối literal, sát tiền tố hoặc sát hậu tố.

| Cách viết | Hợp lệ? | Lý do |
|---|---|---|
| `0xCA_FE` | Có | Dấu phân cách nằm giữa chữ số |
| `0xDEAD_BEEF` | Có | Nhóm chữ số hợp lệ |
| `0x__CAFE` | Không | Dấu phân cách nằm ngay sau tiền tố |
| `0x_CAFE` | Không | Dấu phân cách nằm ngay sau tiền tố |
| `0xCAFE_` | Không | Literal kết thúc bằng dấu phân cách |
| `0xCAFE_L` | Không | Dấu phân cách nằm ngay trước hậu tố |
| `0xCA.FE` | Không phải integer literal | Dấu chấm không dùng để nhóm chữ số nguyên |

Ví dụ sai:

~~~java
// Các dòng sau không biên dịch được:
int a = 0x_FF;
int b = 0xFF_;
long c = 0xCAFE_L;
~~~

Ví dụ đúng:

~~~java
int a = 0xFF;
long b = 0xCAFEL;
long c = 0xCA_FEL;
~~~

Hậu tố phải đứng sát literal, không có dấu phân cách hoặc khoảng trắng chen giữa. Dấu `L` đứng sau chữ số cuối; dấu `_` chỉ được dùng giữa các chữ số.

### 2.3. Dấu phân cách trong literal có hậu tố

Khi có hậu tố, chữ số cuối phải đứng ngay trước hậu tố; không đặt dấu phân cách giữa chữ số cuối và hậu tố.

~~~java
long a = 0xCA_FE_L; // Sai
~~~

Cách đúng:

~~~java
long value = 0xCA_FEL;
long mask = 0x00FF_FFFFL;
~~~

Trong `0xCA_FEL`, chữ số cuối là `E`, theo sau trực tiếp là hậu tố `L`. Dấu `_` nằm giữa `A` và `F`, nên hợp lệ.

## 3. Hậu tố của integer literal hệ mười sáu

Java có hai kiểu số nguyên phổ biến:

- `int`: số nguyên 32 bit có dấu.
- `long`: số nguyên 64 bit có dấu.

Với integer literal hệ mười sáu, hậu tố `L` hoặc `l` chỉ định kiểu `long`. Nên ưu tiên chữ `L` hoa vì chữ `l` thường dễ bị nhầm với số `1`.

~~~java
int intValue = 0x7FFF;
long longValue = 0x7FFF_FFFFL;
~~~

Không có hậu tố `L`, compiler xác định kiểu `int` hoặc `long` theo quy tắc literal và giá trị có thể biểu diễn. Khi cần chủ động thể hiện giá trị là long, hãy ghi `L`.

### 3.1. Hậu tố L thay đổi kiểu literal

~~~java
int a = 0xFF;
long b = 0xFFL;

System.out.println(a); // 255
System.out.println(b); // 255
~~~

Giá trị số trong hai biến bằng nhau, nhưng kiểu khác nhau:

~~~java
System.out.println(((Object) a).getClass()); // class java.lang.Integer
System.out.println(((Object) b).getClass()); // class java.lang.Long
~~~

Hậu tố `L` không làm số trở thành hệ mười sáu; tiền tố `0x` mới là dấu hiệu hệ cơ số. Hậu tố chỉ xác định kiểu số nguyên của literal.

### 3.2. Khi nào cần hậu tố L?

Ví dụ một giá trị cần hơn 32 bit để biểu diễn nhưng vẫn nằm trong miền `long`; hậu tố `L` thể hiện rõ kiểu mong muốn:

~~~java
long fileSize = 0x1_0000_0000L;
~~~

Giá trị là 4.294.967.296. Nếu literal vượt phạm vi biểu diễn của `int`, compiler có thể chọn kiểu `long` theo quy tắc literal hệ 16 nếu giá trị phù hợp; tuy nhiên thêm `L` làm ý định rõ ràng và tránh nhầm lẫn về cách diễn giải bit.

Dùng `L` khi:

- Literal dùng trong phép toán với `long`.
- Giá trị hoặc mask cần 64 bit.
- Muốn thể hiện rõ kiểu dữ liệu trong API.
- Đang khai báo hằng số kích thước, offset hoặc mask 64 bit.

Ví dụ:

~~~java
long mask64 = 0xFFFF_FFFF_FFFF_FFFFL;
long address = 0x0000_7FFF_FFFF_FFFFL;
~~~

### 3.3. Không có hậu tố U cho integer literal

Java không có hậu tố `U` hoặc `UL` như một số ngôn ngữ để khai báo literal số nguyên unsigned.

Các primitive `byte`, `short`, `int`, `long` là kiểu có dấu. Java cung cấp một số API để diễn giải hoặc thao tác giá trị unsigned, ví dụ:

~~~java
int bits = 0xFFFF_FFFF;

System.out.println(bits); // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toUnsignedLong(bits));   // 4294967295
~~~

Giá trị bit 32 bit vẫn là tất cả các bit bằng 1. Khi đọc theo kiểu `int` có dấu, kết quả là `-1`; khi diễn giải unsigned, giá trị tương ứng là 4.294.967.295.

Không viết `0xFFFF_FFFFU` trong Java; đó không phải cú pháp hợp lệ.

## 4. Cần hiểu cách literal hệ 16 được diễn giải thành int/long

Một điểm quan trọng của literal không phải hệ thập phân là các bit cao có thể tạo thành giá trị âm theo biểu diễn bù hai (*two's complement*).

Ví dụ:

~~~java
int a = 0x7FFF_FFFF;
int b = 0x8000_0000;
int c = 0xFFFF_FFFF;

System.out.println(a); // 2147483647
System.out.println(b); // -2147483648
System.out.println(c); // -1
~~~

Trong 32 bit:

- `0x7FFF_FFFF`: bit cao nhất bằng 0, giá trị dương lớn nhất của `int`.
- `0x8000_0000`: bit cao nhất bằng 1, biểu diễn giá trị âm nhỏ nhất của `int`.
- `0xFFFF_FFFF`: tất cả bit bằng 1, biểu diễn `-1`.

Nếu thêm hậu tố `L`, literal được diễn giải ở độ rộng 64 bit:

~~~java
long a = 0x8000_0000L;
long b = 0xFFFF_FFFFL;

System.out.println(a); // 2147483648
System.out.println(b); // 4294967295
~~~

Điều này rất quan trọng khi đọc dữ liệu nhị phân hoặc mask. Cùng chuỗi chữ số hex, việc chọn kiểu `int` hay `long` có thể làm thay đổi giá trị được diễn giải.

### 4.1. So sánh dạng int và long

| Literal | Kiểu | Giá trị |
|---|---|---:|
| `0x7FFF_FFFF` | `int` | 2.147.483.647 |
| `0x8000_0000` | `int` | -2.147.483.648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0x8000_0000L` | `long` | 2.147.483.648 |
| `0xFFFF_FFFFL` | `long` | 4.294.967.295 |
| `0xFFFF_FFFF_FFFF_FFFFL` | `long` | -1 |

Nếu muốn giữ nguyên bit pattern nhưng in ra theo unsigned, dùng API unsigned thay vì kỳ vọng literal có hậu tố `U`.

### 4.2. Cẩn thận khi gán sang byte hoặc short

Literal hệ 16 thường được dùng để biểu diễn một byte:

~~~java
byte value = (byte) 0xFF;
System.out.println(value); // -1
~~~

`0xFF` là literal kiểu `int` với giá trị 255. Kiểu `byte` chỉ có miền `-128..127`, vì vậy phải ép kiểu tường minh. Sau phép ép, 8 bit thấp được giữ lại và được diễn giải theo kiểu byte có dấu, cho ra `-1`.

Tương tự:

~~~java
short value = (short) 0xFFFF;
System.out.println(value); // -1
~~~

Không nên bỏ qua phép ép kiểu trong ví dụ thao tác bit. Nó thể hiện rõ việc thu hẹp từ 32 bit xuống 8 hoặc 16 bit.

## 5. Hexadecimal floating-point literal

Java cũng hỗ trợ số dấu phẩy động viết theo hệ mười sáu. Khác integer literal, hex floating-point literal cần thành phần exponent dùng chữ `p` hoặc `P`.

Ví dụ:

~~~java
double a = 0x1.0p0;
double b = 0x1.8p1;
double c = 0x1.0p-2;

System.out.println(a); // 1.0
System.out.println(b); // 3.0
System.out.println(c); // 0.25
~~~

Cách đọc:

- `0x`: tiền tố hệ 16.
- `1.8`: phần significand hệ 16.
- `p1`: nhân với lũy thừa 2 mũ 1.
- `p-2`: nhân với lũy thừa 2 mũ -2.

Ví dụ `0x1.8p1`:

```text
1.8 (hệ 16) = 1 + 8/16 = 1.5
p1           = nhân với 2¹ = 2
Kết quả      = 1.5 × 2 = 3.0
```

**Chữ `p` biểu thị exponent cơ số 2**, không phải cơ số 10. Đây là điểm khác biệt quan trọng so với cách viết thập phân như `1.5e1`.

### 5.1. Vì sao hex floating-point cần p/P?

Ví dụ hợp lệ:

~~~java
double a = 0x1p2;
double b = 0x1.8p1;
double c = 0XAp-1;
~~~

Các dạng sau không hợp lệ:

~~~java
// Không có exponent p/P:
double a = 0x1.8;

// Dùng e/E thay cho p/P:
double b = 0x1.8e1;
~~~

Trong hệ 16, ký tự `e` cũng là một chữ số hợp lệ có giá trị 14. Java dùng `p`/`P` để phân định phần exponent của hex floating-point literal.

### 5.2. Hậu tố F và D cho số dấu phẩy động

Hex floating-point literal mặc định có kiểu `double`. Có thể thêm:

- `F` hoặc `f`: kiểu `float`.
- `D` hoặc `d`: kiểu `double`.

~~~java
double precise = 0x1.8p1;
double explicitDouble = 0x1.8p1D;
float singlePrecision = 0x1.8p1F;
~~~

`F`/`D` ở đây là hậu tố kiểu số dấu phẩy động. Đừng nhầm chữ `F` trong một integer literal như `0x1F`: ở vị trí đó, `F` là chữ số hex 15.

### 5.3. Dấu phân cách trong hex floating-point

Dấu gạch dưới cũng có thể nhóm chữ số trong phần significand và exponent, miễn nó nằm giữa các chữ số:

~~~java
double a = 0xA.B_Cp1_0;
float b = 0x1.8p1_0F;
~~~

Không đặt dấu gạch dưới ngay sau `0x`, cạnh dấu chấm, cạnh `p` hoặc ngay trước hậu tố:

~~~java
// Các dạng không hợp lệ:
// double a = 0x_1.0p0;
// double b = 0x1._0p0;
// double c = 0x1.0_p0;
// double d = 0x1.0p_2;
// float e = 0x1.0p2_F;
~~~

## 6. Dấu phân cách, tiền tố và hậu tố: đọc một literal theo thứ tự

Khi gặp một literal dài, hãy đọc từ trái sang phải:

~~~java
long mask = 0x00FF_FF00_1234_ABCDL;
~~~

Phân tích:

1. `0x`: tiền tố cho biết hệ 16.
2. `00FF`, `FF00`, `1234`, `ABCD`: các nhóm chữ số.
3. `_`: dấu phân cách giữa các nhóm, bị bỏ qua khi tính giá trị.
4. `L`: hậu tố xác định kiểu `long`.

Một ví dụ khác:

~~~java
float ratio = 0x1.8p1F;
~~~

Phân tích:

1. `0x`: hệ 16.
2. `1.8`: significand hệ 16.
3. `p1`: nhân với 2 mũ 1.
4. `F`: hậu tố kiểu `float`.

Không phải mọi literal hex đều có đủ ba thành phần. Một integer literal có thể chỉ gồm tiền tố và chữ số; dấu phân cách là tùy chọn, hậu tố `L` chỉ cần khi muốn kiểu long hoặc cần làm rõ kiểu. Hex floating-point cần `p`/`P` exponent.

## 7. Dùng số hex trong bit mask và thao tác bit

Dạng hệ 16 đặc biệt hữu ích khi biểu diễn bit vì mỗi chữ số hex tương ứng đúng 4 bit.

Ví dụ:

~~~java
int flags = 0x2D;
~~~

`0x2D` tương ứng nhị phân:

~~~text
2     D
0010  1101
~~~

Một số mask thường gặp:

| Literal | Nhị phân (nhóm 4 bit) | Ý nghĩa minh họa |
|---|---|---|
| `0x0F` | `0000 1111` | 4 bit thấp |
| `0xF0` | `1111 0000` | 4 bit cao trong một byte |
| `0xFF` | `1111 1111` | Toàn bộ 8 bit |
| `0xFF00` | `1111 1111 0000 0000` | Byte thứ hai trong 16 bit |
| `0xFFFF_0000` | 16 bit 1, rồi 16 bit 0 | Mask nửa trên của int |

Ví dụ lấy byte thấp:

~~~java
int value = 0x12AB;
int lowByte = value & 0xFF;

System.out.printf("0x%02X%n", lowByte); // 0xAB
~~~

Ví dụ lấy byte cao trong 16 bit:

~~~java
int highByte = (value >>> 8) & 0xFF;
System.out.printf("0x%02X%n", highByte); // 0x12
~~~

Dấu phân cách giúp mask dễ đọc:

~~~java
int flags = 0b1010_0101;
int mask = 0xF0;
int upperNibble = flags & mask;
~~~

Ở đây `0xF0` chọn 4 bit cao của một byte. Dạng hex khiến cấu trúc mask gần với cách kỹ sư đọc dữ liệu nhị phân.

## 8. Phân biệt literal hệ 16 với chuỗi chứa số hệ 16

Một literal được viết trực tiếp trong mã nguồn:

~~~java
int value = 0xFF;
~~~

Khác với dữ liệu văn bản nhận từ file, mạng hoặc người dùng:

~~~java
String input = "FF";
int value = Integer.parseInt(input, 16);
~~~

`Integer.parseInt(input, 16)` nhận phần chữ số hex **không có tiền tố `0x`**:

~~~java
int a = Integer.parseInt("FF", 16);   // 255
int b = Integer.parseInt("7f", 16);   // 127
~~~

Nếu chuỗi có tiền tố `0x`, có thể dùng `Integer.decode`:

~~~java
int a = Integer.decode("0xFF");
int b = Integer.decode("0X7f");
~~~

Không nhầm hai API:

~~~java
Integer.parseInt("0xFF", 16); // NumberFormatException
Integer.decode("0xFF");       // 255
~~~

Với chuỗi chứa giá trị vượt miền signed của `int`, cần phân biệt mục đích đọc:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);

System.out.println(bits); // -1 khi in như int có dấu
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
~~~

Nếu cần số nguyên có độ lớn tùy ý, không giới hạn 32/64 bit, có thể dùng `BigInteger`:

~~~java
import java.math.BigInteger;

BigInteger value = new BigInteger("FFFFFFFFFFFFFFFF", 16);
System.out.println(value); // 18446744073709551615
~~~

Đầu vào từ người dùng nên được kiểm tra và xử lý ngoại lệ `NumberFormatException` khi chuỗi không phải số hex hợp lệ.

## 9. Chuyển số thành chuỗi hệ mười sáu

Khi cần hiển thị số dưới dạng hex, có thể dùng các phương thức:

~~~java
int value = 255;

String lower = Integer.toHexString(value);
String upper = Integer.toHexString(value).toUpperCase();

System.out.println(lower); // ff
System.out.println(upper); // FF
~~~

Các phương thức `toHexString` không tự thêm tiền tố `0x` và không tự thêm số 0 ở đầu.

Muốn hiển thị đủ độ rộng, dùng Formatter:

~~~java
int value = 255;

System.out.println("0x%08X".formatted(value)); // 0x000000FF
System.out.println("0x%08x".formatted(value)); // 0x000000ff
~~~

| Format | Ý nghĩa |
|---|---|
| `%x` | Hex chữ thường |
| `%X` | Hex chữ hoa |
| `%08X` | Độ rộng tối thiểu 8 ký tự, đệm 0 bên trái |
| `0x%08X` | Tự thêm tiền tố hiển thị `0x` |

Độ rộng trong Formatter là **độ rộng tối thiểu**, không phải giới hạn tối đa. Nếu số cần nhiều hơn 8 chữ số, Formatter vẫn in đủ.

Với số âm, `Integer.toHexString(-1)` cho `ffffffff`, tức biểu diễn 32 bit của giá trị `int -1`. Nếu muốn biểu diễn một giá trị unsigned, hãy chọn API unsigned phù hợp và hiểu rõ độ rộng bit cần hiển thị.

## 10. Những lỗi thường gặp

| Lỗi | Ví dụ | Cách hiểu/sửa |
|---|---|---|
| Quên tiền tố | `int x = FF;` | `FF` không phải literal; dùng `0xFF` |
| Nhầm tiền tố | `int x = #FF;` | Java dùng `0x` hoặc `0X` |
| Đặt dấu phân cách sai | `0x_FF` | Dấu `_` phải nằm giữa chữ số |
| Đặt dấu phân cách cuối | `0xFF_` | Không kết thúc literal bằng `_` |
| Đặt dấu phân cách sát hậu tố | `0xFF_L` | Viết `0xFFL` |
| Nhầm L với chữ số 1 | `0xFFl` | Dạng chữ thường có thể hợp lệ nhưng khó đọc; ưu tiên `0xFFL` |
| Nghĩ L làm literal unsigned | `0xFFFF_FFFFL` | Đây là `long` có dấu, giá trị 4.294.967.295 |
| Nghĩ Java có hậu tố U | `0xFFU` | Java không hỗ trợ hậu tố unsigned |
| Nhầm F là hậu tố trong mọi trường hợp | `0x1F` | Đây là integer literal 31; F là chữ số hex |
| Quên p/P trong hex float | `0x1.8` | Hex floating-point cần exponent `p`/`P` |
| Dùng e/E cho exponent hex float | `0x1.8e2` | Exponent nhị phân dùng `p`/`P` |
| Gán literal lớn cho byte/short không ép kiểu | `byte b = 0xFF;` | Literal là int 255, ngoài miền byte; dùng cast nếu chủ đích giữ bit |
| Dùng parseInt với chuỗi có prefix | `Integer.parseInt("0xFF", 16)` | Dùng `Integer.decode("0xFF")` hoặc bỏ prefix trước khi parse |

## 11. Ví dụ tổng hợp chạy trên Java 17

Tạo file **`HexLiteralDemo.java`**:

~~~java
import java.math.BigInteger;

public class HexLiteralDemo {
    public static void main(String[] args) {
        // Tiền tố và dấu phân cách.
        int color = 0xFF_33_66;
        int mask = 0x00FF_FF00;

        // Hậu tố L cho literal kiểu long.
        long address = 0x0000_7FFF_FFFF_FFFFL;

        // Hex floating-point.
        double three = 0x1.8p1;
        float quarter = 0x1.0p-2F;

        // Bit pattern int có dấu và cách hiển thị unsigned.
        int allBits = 0xFFFF_FFFF;

        System.out.println(color); // 16724838
        System.out.printf("Mask: 0x%08X%n", mask);
        System.out.printf("Address: 0x%016X%n", address);
        System.out.println(three); // 3.0
        System.out.println(quarter); // 0.25
        System.out.println(allBits); // -1
        System.out.println(Integer.toUnsignedString(allBits)); // 4294967295

        // Parse chuỗi hệ 16.
        int parsed = Integer.parseInt("CAFE", 16);
        System.out.println(parsed); // 51966

        BigInteger large = new BigInteger("FFFFFFFFFFFFFFFF", 16);
        System.out.println(large); // 18446744073709551615
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 HexLiteralDemo.java
java HexLiteralDemo
~~~

Ví dụ này dùng các cú pháp chính thức của Java 17, không cần `--enable-preview`.

## 12. Quy trình đọc và viết literal hệ 16

Khi gặp một literal, hãy phân tích theo thứ tự:

~~~text
0x00FF_FF00_1234_ABCDL
| |              |  |
| |              |  +-- Hậu tố L: kiểu long
| |              +----- Chữ số cuối
| +-------------------- Dấu phân cách giữa nhóm chữ số
+---------------------- Tiền tố 0x: hệ 16
~~~

Sau đó xác định:

1. Đây là integer hay floating-point literal?
2. Tiền tố có phải `0x`/`0X` không?
3. Các dấu `_` có nằm giữa chữ số hợp lệ không?
4. Hậu tố có xác định kiểu mong muốn không?
5. Nếu là integer literal, bit cao nhất có khiến giá trị được diễn giải âm theo bù hai không?
6. Nếu là floating-point literal, exponent có dùng `p`/`P` không?
7. Nếu dữ liệu đến lúc chạy dưới dạng chuỗi, nên dùng `parseInt`, `decode`, `parseUnsignedInt` hay `BigInteger`?

## 13. Bài tập tự luyện

### Bài 1: Đọc giá trị literal

Hãy xác định giá trị thập phân của:

~~~java
int a = 0x2A;
int b = 0xFF;
int c = 0x10_00;
long d = 0x1_0000_0000L;
~~~

**Đáp án:**

- `a = 42`.
- `b = 255`.
- `c = 4096`.
- `d = 4.294.967.296`.

### Bài 2: Phân loại cách viết hợp lệ

Xét các literal:

~~~java
0xCA_FE
0XDEAD_BEEF
0x_FF
0xFF_
0xFFL
0xFF_L
0x1.8p1
0x1.8e1
~~~

**Đáp án gợi ý:**

- Hợp lệ: `0xCA_FE`, `0XDEAD_BEEF`, `0xFFL`, `0x1.8p1`.
- Không hợp lệ: `0x_FF`, `0xFF_`, `0xFF_L`, `0x1.8e1`.

### Bài 3: Vì sao `0xFFFFFFFF` bằng -1?

Giải thích theo độ rộng 32 bit.

**Đáp án:** `0xFFFFFFFF` có 32 bit đều bằng 1. Khi diễn giải theo kiểu `int` signed dùng bù hai, mẫu bit đó có giá trị `-1`. Muốn nhận giá trị unsigned tương ứng 4.294.967.295, dùng `Integer.toUnsignedString` hoặc `Integer.toUnsignedLong`.

### Bài 4: Chọn hậu tố

Hãy viết literal phù hợp cho:

- Giá trị 255 kiểu `int`.
- Giá trị 255 kiểu `long`.
- Giá trị 4.294.967.295 kiểu `long`.
- Giá trị 3.0 kiểu `double` bằng hex floating-point.
- Giá trị 0.25 kiểu `float` bằng hex floating-point.

**Đáp án:**

~~~java
int a = 0xFF;
long b = 0xFFL;
long c = 0xFFFF_FFFFL;
double d = 0x1.8p1;
float e = 0x1.0p-2F;
~~~

### Bài 5: Parse chuỗi hex

Cho `String input = "0xCAFE";`. Hãy chuyển thành số nguyên.

**Đáp án:**

~~~java
int value = Integer.decode(input);
~~~

Hoặc loại bỏ prefix trước rồi gọi:

~~~java
int value = Integer.parseInt(input.substring(2), 16);
~~~

### Bài 6: Biểu diễn byte

Vì sao `byte value = 0xFF;` không biên dịch, trong khi `byte value = (byte) 0xFF;` hợp lệ?

**Đáp án:** `0xFF` là literal `int` có giá trị 255, vượt miền `byte` từ -128 đến 127. Phép ép kiểu tường minh giữ 8 bit thấp; mẫu `11111111` được diễn giải là `-1` theo kiểu byte có dấu.

## 14. Tài liệu tham khảo

- [Java Language Specification 17 — Integer Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.1): cú pháp integer literal, tiền tố, dấu phân cách, hậu tố và quy tắc kiểu.
- [Java Language Specification 17 — Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.2): cú pháp decimal và hexadecimal floating-point literal.
- [Oracle Java SE 17 — Primitive Data Types](https://docs.oracle.com/javase/tutorial/java/nutsandbolts/datatypes.html): độ rộng và miền giá trị của các kiểu nguyên thủy.
- [Oracle Java SE 17 — Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): parse, decode, chuyển đổi và thao tác unsigned với `int`.
- [Oracle Java SE 17 — Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): phương thức chuyển đổi và thao tác unsigned với `long`.
- [Oracle Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): biểu diễn và parse số nguyên độ lớn tùy ý.


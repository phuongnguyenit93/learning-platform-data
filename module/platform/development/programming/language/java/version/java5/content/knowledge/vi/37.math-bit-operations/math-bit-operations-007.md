# Literal số thực hệ mười sáu và biểu diễn nhị phân chính xác

## 1. Vì sao số dấu phẩy động lại cần dạng hệ mười sáu?

`float` và `double` lưu số theo hệ nhị phân. Trong khi đó, mã nguồn thường dùng hệ mười như `0.1`, `3.5` hoặc `1e20`.

Một số phân số thập phân không biểu diễn hữu hạn được trong hệ nhị phân. Vì vậy, chuỗi `0.1` và giá trị nhị phân thực sự được lưu cần được phân biệt.

Literal dấu phẩy động hệ mười sáu cho phép viết phần trị theo hệ 16 và số mũ theo lũy thừa của 2. Mỗi chữ số hệ 16 tương ứng bốn bit, nên cách viết này giúp nhìn rõ cấu trúc nhị phân hơn.

Ví dụ:

```java
double value = 0x1.8p1;
```

Giá trị là `3.0`, vì:

```text
0x1.8 = 1 + 8/16 = 1.5
p1     = nhân với 2^1
1.5 × 2 = 3
```

Nó vẫn là một `double` thông thường. Không có một kiểu số “hex float” riêng ở thời điểm chạy; hệ 16 là cách biểu diễn trong mã nguồn hoặc chuỗi.

## 2. Cú pháp: phần trị hệ 16, số mũ cơ số 2

Dạng thường dùng:

```text
0x<phần trị hệ 16>p<số mũ viết bằng chữ số thập phân><hậu tố tùy chọn>
```

Ví dụ `0x1.fp3` gồm:

| Thành phần | Ý nghĩa |
|---|---|
| `0x` | Mở đầu phần trị hệ mười sáu |
| `1.f` | Phần trị: `1 + 15/16` |
| `p` | Bắt đầu số mũ của cơ số 2 |
| `3` | Số mũ bằng 3 |
| Không có hậu tố | Kiểu `double` |

Giá trị:

```text
(1 + 15/16) × 2^3 = 1.9375 × 8 = 15.5
```

Các quy tắc cú pháp quan trọng:

- `0x` hoặc `0X` mở đầu phần trị.
- `p` hoặc `P` và số mũ là bắt buộc.
- Dấu chấm có thể có hoặc không.
- Phần trị phải có ít nhất một chữ số.
- Số mũ sau `p` được viết bằng các chữ số thập phân, có thể có dấu `+` hoặc `-`.
- Hậu tố `f/F` tạo literal kiểu `float`; không có hậu tố hoặc có `d/D` tạo `double`.

Cú pháp này được quy định trong [JLS §3.10.2: Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.2).

### 2.1. p10 là nhân 2^10

```java
double a = 0x1p10; // 1024.0
double b = 0x1p4;  // 16.0
double c = 0x1p-3; // 0.125
```

Không đọc `p10` thành số mũ hệ 16 bằng 16, cũng không đọc thành nhân `16^10`.

Phần trị dùng cơ số 16, nhưng cơ số của lũy thừa là 2. Đây là điểm dễ nhầm nhất khi mới đọc cú pháp.

### 2.2. Vì sao dùng p thay cho e?

Các chữ `a` đến `f` đã là chữ số hợp lệ trong phần trị hệ 16. Ví dụ:

```java
int integer = 0x1e2;     // 482, literal số nguyên.
double floating = 0x1p2; // 4.0, literal dấu phẩy động.
```

Trong `0x1e2`, chữ `e` là chữ số 14, không mở đầu số mũ thập phân như trong `1e2`.

Tương tự, `0x1f` là số nguyên 31. Muốn một literal dấu phẩy động có phần trị đó, viết `0x1fp0`, bằng `31.0`. Chữ `f` trước `p` thuộc phần trị; `f` sau số mũ, như `0x1p0f`, là hậu tố kiểu.

## 3. Tự giải mã phần lẻ hệ 16

Với một phần trị dạng `A.BC`, mỗi chữ số sau dấu chấm ứng với lũy thừa âm của 16:

```text
0xA.BC = A + B/16 + C/16²
```

Sau đó nhân toàn bộ với `2^e` theo phần `p<e>`.

| Literal | Cách tính | Giá trị |
|---|---|---:|
| `0x1.8p1` | `(1 + 8/16) × 2` | `3.0` |
| `0x1.fp3` | `(1 + 15/16) × 8` | `15.5` |
| `0x1p-3` | `1 × 2^-3` | `0.125` |
| `0x0.1p0` | `1/16 × 1` | `0.0625` |
| `0xcp-2` | `12 × 2^-2` | `3.0` |

Không bắt buộc phần trị trong mã nguồn bắt đầu bằng `1.`. `0xcp-2` và `0x1.8p1` có cùng giá trị.

Khi thư viện in lại bằng `Double.toHexString`, dạng hiển thị được chuẩn hóa theo hợp đồng API, nên nó không nhất thiết giống nguyên văn literal đầu vào.

## 4. Quan hệ trực tiếp giữa chữ số hex và bit

Ví dụ:

```text
0x1.8 = 1.1000 trong nhị phân
0x1.f = 1.1111 trong nhị phân
```

Mỗi chữ số hệ 16 tạo một nhóm bốn bit. Điều này giúp viết các giá trị nằm đúng trên lưới biểu diễn của số dấu phẩy động nhị phân.

Cấu trúc cơ bản của IEEE 754:

| Kiểu | Tổng số bit | Bit dấu | Bit số mũ | Bit phần lẻ được lưu | Precision của số chuẩn hóa |
|---|---:|---:|---:|---:|---:|
| `float` | 32 | 1 | 8 | 23 | 24 bit |
| `double` | 64 | 1 | 11 | 52 | 53 bit |

Với số chuẩn hóa, phần trị có một bit 1 đứng đầu được suy ra, không lưu trong trường phần lẻ. Do đó precision nhiều hơn số bit phần lẻ được lưu một bit.

Một `double` chuẩn hóa có thể viết theo dạng `1.<52 bit phần lẻ> × 2^e`. Vì 52 chia hết cho 4, tối đa 13 chữ số hex sau dấu chấm đủ mô tả trường phần lẻ của dạng chuẩn hóa đó.

Đối với `float`, trường phần lẻ có 23 bit. Sáu chữ số hex tương ứng 24 bit, nên không phải mọi tổ hợp sáu chữ số sau dấu chấm ở dạng `1.x...` đều vừa precision của `float`. Cần xét các bit thực sự cần giữ, không chỉ đếm chữ số hex.

## 5. “Hex” không tự bảo đảm mọi literal đều chính xác

Có hai phát biểu khác nhau:

1. Một giá trị hữu hạn đang được lưu trong `float` hoặc `double` có thể được mô tả chính xác bằng một biểu diễn hex phù hợp.
2. Một literal hex dài tùy ý luôn được lưu chính xác trong kiểu đích.

Phát biểu đầu đúng với các giá trị hữu hạn; phát biểu sau sai. Kiểu đích vẫn chỉ có precision hữu hạn và miền số mũ hữu hạn.

### 5.1. Cùng literal toán học, float và double có thể khác

Xét:

```java
double exact = 0x1.000001p0;
float rounded = 0x1.000001p0f;
```

Phần dư sau 1 là `16^-6 = 2^-24`.

Ở gần 1:

- `double` có đủ precision để giữ bit đó.
- Bước giữa hai `float` kề nhau là `2^-23`.
- Giá trị `1 + 2^-24` nằm đúng giữa `1.0f` và `float` lớn hơn kế tiếp.
- Quy tắc gần nhất, hòa chọn chẵn đưa nó về `1.0f`.

Nếu sau đó mở rộng `rounded` sang `double`, giá trị vẫn là `1.0`. Thêm độ rộng kiểu sau khi đã làm tròn không khôi phục bit đã mất.

### 5.2. double cũng có thể phải làm tròn

Literal:

```java
double rounded = 0x1.00000000000008p0;
```

biểu thị giá trị toán học `1 + 2^-53`, đúng giữa hai `double` kề nhau tại vùng đó. Kết quả lưu là `1.0` theo quy tắc hòa chọn chẵn.

Như vậy, hexadecimal giúp kiểm soát và quan sát các bit, nhưng không tạo một kiểu có precision vô hạn.

### 5.3. Hậu tố quyết định kiểu literal trước khi gán

```java
double a = 0x1.000001p0;  // Literal double, giữ được bit 2^-24.
double b = 0x1.000001p0f; // Literal float đã làm tròn, sau đó mới mở rộng.
```

`a` và `b` khác nhau.

Ngược lại, câu `float x = 0x1.8p1;` không hợp lệ vì literal không có hậu tố là `double`; Java không tự thu hẹp `double` xuống `float` trong phép gán này, dù giá trị 3 biểu diễn được bằng `float`.

Muốn literal kiểu `float`, viết `0x1.8p1f`.

## 6. Quan sát giá trị 0.1 thực sự được lưu

```java
System.out.println(Double.toHexString(0.1));
// 0x1.999999999999ap-4
```

Đây là một biểu diễn chính xác của **giá trị double đã được làm tròn từ literal thập phân `0.1`**. Nó không biến phân số `1/10` thành một phân số nhị phân hữu hạn.

Hai literal dưới đây tạo cùng giá trị nhị phân:

```java
double decimalSpelling = 0.1;
double hexadecimalSpelling = 0x1.999999999999ap-4;

System.out.println(decimalSpelling == hexadecimalSpelling); // true
```

Việc `System.out.println(0.1)` in `0.1` là lựa chọn biểu diễn chuỗi của thư viện, không chứng minh giá trị nhị phân bằng chính xác một phần mười.

Với `float`, kết quả khác:

```java
System.out.println(Float.toHexString(0.1f));
// 0x1.99999ap-4
```

Dạng hex cho thấy rõ precision thấp hơn. Không nên lấy dạng hex của `float`, mở rộng sang `double`, rồi nghĩ đã nhận được giá trị `double` mà literal thập phân gốc sẽ tạo.

## 7. Số chuẩn hóa, số dưới chuẩn và các biên biểu diễn

Với `double`:

| Giá trị | Một literal tương ứng |
|---|---|
| Số dương chuẩn hóa nhỏ nhất | `0x1p-1022` |
| Số dương khác 0 nhỏ nhất | `0x1p-1074` |
| Số dương hữu hạn lớn nhất | `0x1.fffffffffffffp1023` |

Với `float`:

| Giá trị | Một literal tương ứng |
|---|---|
| Số dương chuẩn hóa nhỏ nhất | `0x1p-126f` |
| Số dương khác 0 nhỏ nhất | `0x1p-149f` |
| Số dương hữu hạn lớn nhất | `0x1.fffffep127f` |

Các số dưới chuẩn (subnormal) lấp vùng từ 0 đến ngưỡng chuẩn hóa với độ chính xác tương đối giảm dần. Không có bit 1 ẩn theo cùng cách như số chuẩn hóa.

`Double.toHexString(Double.MIN_VALUE)` in:

```text
0x0.0000000000001p-1022
```

Dạng này bằng đúng `0x1p-1074`:

```text
16^-13 × 2^-1022
= 2^-52 × 2^-1022
= 2^-1074
```

Không đọc số mũ `p-1022` trong chuỗi dưới chuẩn rồi kết luận đó là `Double.MIN_NORMAL`; phải xét cả phần trị đứng trước.

Các dạng chuỗi được quy định trong [Double.toHexString](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#toHexString(double)) và [Float.toHexString](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Float.html#toHexString(float)).

### 7.1. Literal quá lớn hoặc quá nhỏ có thể không biên dịch

Các dòng dưới đây cố ý không hợp lệ:

```java
// Không đưa các dòng này vào chương trình muốn biên dịch thành công:
double tooLarge = 0x1p1024;
double tooSmall = 0x1p-1075;
```

Literal thứ nhất chuyển thành vô cực, literal thứ hai là giá trị khác 0 nhưng làm tròn về 0. Đây là lỗi biên dịch của literal.

Điều đó khác với một **biểu thức** gồm các literal hợp lệ tạo ra vô cực hoặc 0:

```java
double overflow = 0x1p1023 * 2.0;   // Infinity.
double underflow = 0x1p-1074 / 2.0; // 0.0.
```

Không có literal riêng cho `NaN` hoặc vô cực. Dùng các hằng như `Double.NaN`, `Double.POSITIVE_INFINITY` khi cần thể hiện chúng rõ ràng.

## 8. Dạng hex của giá trị khác với dãy bit IEEE 754

Hai cách viết sau có vai trò khác nhau:

```java
double value = 0x1.8p0; // Giá trị số học 1.5.
long bits = 0x3ff8000000000000L; // Một số nguyên 64 bit.
```

Nếu muốn diễn giải `bits` theo cấu trúc IEEE 754 để tạo `double`, gọi:

```java
double decoded = Double.longBitsToDouble(bits); // 1.5.
```

Ép kiểu `(double) bits` sẽ chuyển **giá trị số nguyên** thành một số dấu phẩy động có độ lớn tương ứng. Nó không tái diễn giải dãy bit thành các trường dấu/số mũ/phần lẻ.

Theo chiều ngược lại:

```java
long raw = Double.doubleToRawLongBits(value);
```

Dạng hex `0x1.8p0` đọc được như một biểu thức giá trị. Dạng `0x3ff8000000000000L` là mã hóa các trường của IEEE 754 trong một số nguyên. Cả hai có ích khi kiểm tra số học, nhưng không được dùng thay nhau mà bỏ qua phép chuyển phù hợp.

Với `float`, các API tương ứng là `Float.intBitsToFloat` và `Float.floatToRawIntBits`.

## 9. Số 0 có dấu và giới hạn của round-trip bằng chuỗi

Dấu trừ đứng trước literal là toán tử một ngôi; có thể tạo âm 0:

```java
double negativeZero = -0x0.0p0;
```

`Double.toHexString(negativeZero)` trả `-0x0.0p0`. Dãy bit tương ứng là `0x8000000000000000`.

Đối với các giá trị hữu hạn, có thể chuyển thành chuỗi hex rồi parse lại mà giữ nguyên giá trị và dấu 0:

```java
String text = Double.toHexString(value);
double restored = Double.parseDouble(text);
```

Khi cần xác nhận cả dấu của số 0, so sánh `Double.doubleToRawLongBits` thay vì chỉ dùng `==`.

Tuy nhiên, `toHexString` biểu diễn mọi `NaN` thành chuỗi `"NaN"`; chuỗi đó không lưu được các bit payload khác nhau của NaN. Không dùng nó như định dạng bảo toàn tùy ý mọi mẫu bit 64 bit.

Kết quả `Float.toHexString` không có hậu tố `f`. Nếu chép giá trị hữu hạn đó thành mã nguồn để gán cho `float`, cần thêm hậu tố thích hợp. Nếu parse chuỗi bằng `Float.parseFloat`, kiểu đích đã được xác định bởi API.

## 10. Chương trình chạy đầy đủ

Lưu thành `HexFloatingDemo.java`:

```java
public class HexFloatingDemo {
    private static void show(String label, double value) {
        System.out.println(label + ": decimal=" + value
                + ", hex=" + Double.toHexString(value));
    }

    public static void main(String[] args) {
        show("three", 0x1.8p1);
        show("one eighth", 0x1p-3);
        show("fifteen and half", 0x1.fp3);
        show("hex fraction", 0x0.1p0);
        show("binary exponent ten", 0x1p10);

        System.out.println("decimal 0.1 hex=" + Double.toHexString(0.1));
        System.out.println("same binary value="
                + (0.1 == 0x1.999999999999ap-4));
        System.out.println("float 0.1 hex=" + Float.toHexString(0.1f));

        show("double exact extra bit", 0x1.000001p0);
        float roundedFloat = 0x1.000001p0f;
        System.out.println("float rounded=" + Float.toHexString(roundedFloat));
        show("float then widened", roundedFloat);
        show("double halfway rounded", 0x1.00000000000008p0);

        System.out.println("double min normal="
                + Double.toHexString(0x1p-1022));
        System.out.println("double min positive="
                + Double.toHexString(0x1p-1074));
        System.out.println("double max finite="
                + Double.toHexString(0x1.fffffffffffffp1023));
        System.out.println("float min positive="
                + Float.toHexString(0x1p-149f));

        double negativeZero = -0x0.0p0;
        System.out.println("negative zero=" + Double.toHexString(negativeZero));
        System.out.println("negative zero bits=0x"
                + Long.toHexString(Double.doubleToRawLongBits(negativeZero)));

        double fromBits = Double.longBitsToDouble(0x3ff8000000000000L);
        show("from IEEE bits", fromBits);
        System.out.println("1.5 raw bits=0x"
                + Long.toHexString(Double.doubleToRawLongBits(0x1.8p0)));

        boolean roundTrip = true;
        for (double value : new double[] {
                0x1.8p1, 0.1, Double.MIN_VALUE, Double.MAX_VALUE, negativeZero
        }) {
            double parsed = Double.parseDouble(Double.toHexString(value));
            roundTrip &= Double.doubleToRawLongBits(value)
                    == Double.doubleToRawLongBits(parsed);
        }
        System.out.println("finite bit round trip=" + roundTrip);
        show("source underscores", 0x1_0.8p1_0);

        try {
            Double.parseDouble("0x1_0p0");
        } catch (NumberFormatException exception) {
            System.out.println("parse source underscore=NumberFormatException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HexFloatingDemo.java
java HexFloatingDemo
```

Stdout:

```text
three: decimal=3.0, hex=0x1.8p1
one eighth: decimal=0.125, hex=0x1.0p-3
fifteen and half: decimal=15.5, hex=0x1.fp3
hex fraction: decimal=0.0625, hex=0x1.0p-4
binary exponent ten: decimal=1024.0, hex=0x1.0p10
decimal 0.1 hex=0x1.999999999999ap-4
same binary value=true
float 0.1 hex=0x1.99999ap-4
double exact extra bit: decimal=1.0000000596046448, hex=0x1.000001p0
float rounded=0x1.0p0
float then widened: decimal=1.0, hex=0x1.0p0
double halfway rounded: decimal=1.0, hex=0x1.0p0
double min normal=0x1.0p-1022
double min positive=0x0.0000000000001p-1022
double max finite=0x1.fffffffffffffp1023
float min positive=0x0.000002p-126
negative zero=-0x0.0p0
negative zero bits=0x8000000000000000
from IEEE bits: decimal=1.5, hex=0x1.8p0
1.5 raw bits=0x3ff8000000000000
finite bit round trip=true
source underscores: decimal=16896.0, hex=0x1.08p14
parse source underscore=NumberFormatException
```

Chương trình dùng so sánh bit để kiểm chứng round-trip hữu hạn, không chỉ so sánh các chuỗi hiển thị thập phân.

## 11. Dấu gạch dưới trong mã nguồn không phải cú pháp parse chuỗi

Trong literal Java, có thể dùng dấu `_` giữa các chữ số:

```java
double value = 0x1_0.8p1_0;
```

Nó bằng `0x10.8p10 = 16.5 × 1024 = 16896`.

Dấu `_` không được đặt tùy ý sát tiền tố `0x`, sát dấu chấm, sát `p`, sát dấu của số mũ hoặc sát hậu tố kiểu. Có thể nhớ rằng dấu gạch dưới đóng vai trò ngăn cách các chữ số trong từng phần, không thay thế cấu trúc của literal.

Ngoài ra, bộ phân tích literal của trình biên dịch và `Double.parseDouble` không nhận đúng cùng một ngôn ngữ đầu vào:

```java
double source = 0x1_0p0; // Hợp lệ trong mã nguồn.
double parsed = Double.parseDouble("0x1_0p0"); // NumberFormatException.
```

Chuỗi `"0x10p0"` không có dấu gạch dưới thì parse được. Không lấy quy tắc gạch dưới trong mã nguồn làm bằng chứng rằng dữ liệu văn bản gửi vào API sẽ được chấp nhận.

Các dạng cố ý không hợp lệ khác:

| Mã nguồn | Nguyên nhân |
|---|---|
| `0x1.8` | Thiếu số mũ nhị phân bắt buộc |
| `0x1.8p` | Thiếu chữ số của số mũ |
| `0x1.8pA` | Số mũ không được viết bằng chữ số hex A |
| `0x1_.8p0` | Gạch dưới ở ranh giới không hợp lệ |
| `float x = 0x1.8p1;` | Literal là double; phép gán không tự thu hẹp |

## 12. Khi nào nên dùng và khi nào cần giải thích thêm?

Dạng hex đặc biệt hữu ích khi:

- Viết hằng cần khớp chính xác một giá trị nhị phân đã xác định.
- Tạo dữ liệu kiểm thử ở biên chuẩn hóa/dưới chuẩn.
- Kiểm tra hai giá trị kề nhau hoặc tình huống hòa khi làm tròn.
- Ghi nhận kết quả số học để tái hiện chính xác một đầu vào hữu hạn.
- Đọc mã thư viện số học hoặc thuật toán xử lý trường số mũ/phần trị.

Với các con số nghiệp vụ mang ý nghĩa thập phân, dạng hex không tự sửa vấn đề chọn kiểu dữ liệu. Viết một giá trị xấp xỉ của `0.1` dưới dạng hex vẫn là dùng số dấu phẩy động nhị phân.

Trong mã nguồn có hằng hex dài, nên ghi chú đại lượng toán học hoặc lý do chọn đúng các bit đó. Người đọc cần hiểu vì sao hằng xuất hiện, không chỉ xác nhận nó biên dịch được.

## 13. Bài tập tự kiểm tra

1. Tính giá trị của `0x1.4p2`.
2. `0x1p10` bằng 16 hay 1024? Vì sao?
3. `0x1e2` là literal dấu phẩy động hay số nguyên?
4. Hai biến `double a = 0x1.000001p0;` và `double b = 0x1.000001p0f;` có bằng nhau không?
5. Vì sao `Double.MIN_VALUE` in hex với `p-1022` vẫn có giá trị `2^-1074`?
6. Có thể dùng `(double) 0x3ff8000000000000L` để tái diễn giải dãy bit thành `1.5` không?
7. Round-trip bằng `toHexString` có lưu mọi payload của NaN không?

Đáp án:

1. `(1 + 4/16) × 4 = 5.0`.
2. `1024`; chữ số mũ là số thập phân 10, cơ số lũy thừa là 2.
3. Số nguyên hệ 16, bằng 482.
4. Không. `b` đi qua bước làm tròn về float rồi mới mở rộng thành double.
5. Phần trị là `16^-13 = 2^-52`; nhân với `2^-1022` cho `2^-1074`.
6. Không. Dùng `Double.longBitsToDouble`; ép kiểu là chuyển giá trị số nguyên.
7. Không. Dạng chuỗi `"NaN"` không mã hóa các payload riêng.

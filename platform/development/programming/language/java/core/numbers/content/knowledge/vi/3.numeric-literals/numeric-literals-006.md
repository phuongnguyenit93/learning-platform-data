# Literal số thực, ký hiệu mũ và hậu tố F, D trong Java

## 1. Mục tiêu của bài học

Trong Java, **floating-point literal** là cách viết trực tiếp một giá trị số thực trong mã nguồn. Bài này thuộc nhóm **Literal và cơ số** của Java Core — Numbers. Sau khi học, bạn cần:

- Đọc và viết đúng các dạng literal thập phân như `3.14`, `.5`, `10.`, `6.02e23`.
- Hiểu ký hiệu mũ `e`/`E` là **lũy thừa cơ số 10**, trong khi `p`/`P` của literal thập lục phân biểu diễn **lũy thừa cơ số 2**.
- Biết `f`/`F` tạo literal kiểu `float`; `d`/`D` hoặc không có hậu tố tạo literal kiểu `double`.
- Phân biệt **kiểu của literal**, **kiểu của biến nhận giá trị**, **ép kiểu** và **độ chính xác lưu trữ**.
- Nhận diện quy tắc dấu, dấu chấm, chữ số, dấu gạch dưới, trường hợp sai cú pháp và literal vượt giới hạn biểu diễn.
- Tự đối chiếu Java Language Specification (JLS) và chạy ví dụ bằng JDK 17 trở lên.

**Điểm cốt lõi:** một literal được phân tích và gán kiểu ngay khi biên dịch. Dấu phẩy động trong chương trình Java dùng dấu chấm `.`, không dùng dấu phẩy `,` theo cách ghi số của một số ngôn ngữ tự nhiên.

## 2. Literal số thực là gì?

Hãy bắt đầu bằng những khai báo sau:

```java
int whole = 12;
double fraction = 12.0;
double scientific = 1.2e1;
float small = 12.0F;
```

Cả bốn biến có thể biểu diễn lượng mười hai, nhưng **kiểu và cú pháp nguồn không giống nhau**:

| Cách viết | Loại token/kiểu | Ý nghĩa |
| --- | --- | --- |
| `12` | Literal số nguyên kiểu `int` | Mười hai |
| `12L` | Literal số nguyên kiểu `long` | Mười hai, vẫn là số nguyên |
| `12.0` | Literal số thực kiểu `double` | Mười hai dưới dạng floating point |
| `12.` | Literal số thực kiểu `double` | Tương đương `12.0` |
| `.5` | Literal số thực kiểu `double` | Một nửa |
| `12e0` | Literal số thực kiểu `double` | 12 × 10⁰ |
| `12f`, `12.0F` | Literal số thực kiểu `float` | Mười hai dưới dạng `float` |
| `12d`, `12.0D` | Literal số thực kiểu `double` | Hậu tố `D` ghi rõ kiểu mặc định |
| `0x1.8p3` | Literal số thực kiểu `double`, dạng hex | (1 + 8/16) × 2³ = 12 |

Trong Java, số thực primitive gồm hai kiểu:

- `float`: khuôn dạng IEEE 754 **binary32**, có khoảng 24 bit significand (xấp xỉ 6–9 chữ số thập phân có nghĩa khi biểu diễn/khôi phục).
- `double`: khuôn dạng IEEE 754 **binary64**, có khoảng 53 bit significand (xấp xỉ 15–17 chữ số thập phân có nghĩa khi biểu diễn/khôi phục).

Đó là độ chính xác **nhị phân hữu hạn**, không phải số lượng chữ số sau dấu chấm. Không nên kết luận rằng literal có nhiều chữ số thập phân sẽ được giữ chính xác nguyên vẹn trong `double` hay `float`.

## 3. Bốn dạng cú pháp literal số thực thập phân

Theo JLS `3.10.2, literal thập phân phải có **ít nhất một chữ số**, và phải có **dấu chấm, phần mũ hoặc hậu tố kiểu số thực**. Dưới đây là bốn cách viết tiêu biểu:

| Dạng | Ví dụ hợp lệ | Giải thích |
| --- | --- | --- |
| Chữ số rồi dấu chấm, có hoặc không có phần lẻ | `1.`, `1.25`, `1.25e2` | Có `.` nên là floating-point literal |
| Dấu chấm rồi chữ số | `.25`, `.25F`, `.25e+2` | Được phép bỏ số 0 trước dấu chấm |
| Chữ số rồi phần mũ | `1e3`, `12E-2`, `10e0D` | `e`/`E` đủ để biến thành literal số thực |
| Chữ số rồi hậu tố `F/f/D/d` | `1f`, `20F`, `3d` | Hậu tố nhận diện kiểu ngay cả khi không có `.` |

Cụ thể, các literal sau đều hợp lệ:

```java
double a = 7.0;
double b = 7.;
double c = .7;
double d = 7e2;
double e = 7.0E-2;
float f = 7f;
float g = .7F;
double h = 7D;
```

Ngược lại, `7` là literal số nguyên `int`; việc gán nó vào biến `double` là **widening conversion**, không biến token `7` thành floating-point literal. Đây là khác biệt quan trọng khi phân tích overload, biểu thức và giá trị trung gian.

**Không dùng dấu phẩy trong literal:** `3,14` không tạo ra số thực “ba phẩy mười bốn”. Trong cú pháp Java, dấu phẩy có vai trò phân cách ở một số cấu trúc. Viết `3.14` trong mã nguồn; chỉ dùng định dạng địa phương khi xử lý chuỗi nhập/xuất.

## 4. Ký hiệu mũ thập phân: e và E

Dạng tổng quát dễ nhớ:

```text
phần_trị_số e hoặc E dấu_mũ_tùy_chọn chữ_số_mũ
```

Về toán học, `aeb` có nghĩa là **a × 10ᵇ** khi `a`, `b` là phần trị số và số mũ tương ứng. Chữ `e` là ký hiệu cú pháp, **không phải** hằng số Euler `e ≈ 2.71828...`.

| Literal | Phép tính toán học | Giá trị |
| --- | --- | --- |
| `1e3` | 1 × 10³ | 1000 |
| `2.5E2` | 2.5 × 10² | 250 |
| `6.25e-2` | 6.25 × 10⁻² | 0.0625 |
| `1E+2` | 1 × 10² | 100 |
| `7e0` | 7 × 10⁰ | 7 |
| `.75e+1` | 0.75 × 10¹ | 7.5 |

- `e` và `E` tương đương; `1e3` và `1E3` có cùng kiểu `double` và cùng giá trị.
- Sau `e`/`E` **bắt buộc phải có số mũ nguyên viết bằng chữ số thập phân**.
- Dấu `+`/`-` ngay sau `e`/`E` là phần hợp lệ của phần mũ: `1e+3`, `1e-3`.
- `1e`, `1e+`, `1e-` không có đủ phần mũ và không hợp lệ.
- `1e2.5` không hợp lệ dưới dạng một literal; phần số mũ phải là số nguyên.
- Số mũ không làm literal đổi thành `BigDecimal`; `6.02e23` vẫn là `double` nếu không có hậu tố `F`.

**Lưu ý khi đọc log:** Java có thể tự in `1.0E7` thay vì một chuỗi gồm toàn chữ số. Cách `Double.toString`/`Float.toString` chọn biểu diễn chuỗi là chuyện **xuất giá trị**, tách biệt cú pháp literal nguồn `1e7`.

## 5. Hậu tố F/f và D/d quyết định kiểu của literal

Quy tắc chuẩn của ngôn ngữ:

| Hậu tố | Kiểu literal | Ví dụ |
| --- | --- | --- |
| `f` hoặc `F` | `float` | `3.14f`, `5F`, `2e-3F` |
| `d` hoặc `D` | `double` | `3.14d`, `5D`, `2e-3D` |
| Không có hậu tố | `double` | `3.14`, `5e0`, `0x1p1` |

Hậu tố có thể viết hoa/thường. Nên ưu tiên `F` và `D` khi cần nói rõ kiểu; `D` thường có thể bỏ vì `double` đã là mặc định.

### 5.1. Kiểu literal khác kiểu biến nhận

```java
float a = 1.25F;       // float -> float
double b = 1.25;       // double -> double
double c = 1.25F;      // float -> double, widening
double d = 1.25D;      // double -> double
double e = 1;          // int -> double, widening
```

Trong `double c = 1.25F;`, **giá trị được tạo theo độ chính xác `float` trước**, rồi mới chuyển rộng sang `double`. Chuyển rộng không khôi phục những chữ số đã mất trong `float`.

Ví dụ sau **không biên dịch**:

```java
float wrong = 1.25;
```

Vì `1.25` không có hậu tố nên là literal `double`; Java không tự thu hẹp từ `double` sang `float` trong phép gán như vậy. Sửa thành `float correct = 1.25F;`. Có thể ép kiểu tường minh `(float) 1.25` khi phù hợp, nhưng không nên thay thế hậu tố chỉ để làm mất cảnh báo về chuyển hẹp.

Trường hợp tương tự:

```java
float rate = 1e2F;  // hợp lệ, float
double distance = 1e2; // hợp lệ, double
// float bad = 1e2;    // lỗi biên dịch: double -> float
```

### 5.2. Vì sao 0.1F và 0.1 không “giống hệt” nhau?

`0.1F` được làm tròn sang biểu diễn binary32; `0.1` được làm tròn sang binary64. Khi `float` được mở rộng thành `double` để so sánh hoặc gán, số đã làm tròn ở binary32 vẫn giữ giá trị đó. Do đó **một literal có hậu tố khác có thể dẫn đến khác biệt giá trị**, ngay cả khi chúng có cùng các chữ số thập phân trong mã nguồn.

Chỉ dùng `D` khi nó giúp người đọc hoặc một công cụ sinh mã thấy rõ ý định. Đừng chọn `F` chỉ để tiết kiệm bộ nhớ nếu chưa đánh giá sai số cho bài toán.

### 5.3. F/D không phải ký hiệu chuyển kiểu hay đơn vị

`1.5F` là **một literal `float`**; `(float) 1.5` là **một cast** trên literal `double`. `L` biểu thị literal `long` nguyên, không được gắn vào số thực: `1.5L` hoặc `1e3L` không hợp lệ. Java cũng không có hậu tố built-in kiểu `M` để tạo `BigDecimal` như một số ngôn ngữ khác.

## 6. Literal số thực thập lục phân và ký hiệu p/P

Ngoài số thực thập phân, Java còn cho phép **hexadecimal floating-point literal**. Dạng này bắt đầu bằng `0x` hoặc `0X`, dùng chữ số thập lục phân `0–9` và `A–F/a–f` cho **significand** (phần trị số), rồi **bắt buộc có phần mũ `p`/`P`**.

Khác biệt mấu chốt:

- `1.5e2` = 1.5 × **10²** = 150.
- `0x1.8p2` = (1 + 8/16) × **2²** = 6.
- `0x1.fp2` = (1 + 15/16) × **2²** = 7.75.

Dù hệ chữ số phần trị số là **cơ số 16**, phần mũ `p` vẫn là **lũy thừa cơ số 2**. Các chữ số viết sau `p`/`P` là chữ số **thập phân** của số mũ, không phải hexadecimal.

| Literal hex | Diễn giải | Giá trị thập phân |
| --- | --- | --- |
| `0x1p0` | 1 × 2⁰ | 1 |
| `0x1p3` | 1 × 2³ | 8 |
| `0x1.8p1` | (1 + 8/16) × 2¹ | 3 |
| `0x1.fp2` | (1 + 15/16) × 2² | 7.75 |
| `0x.8p0` | (8/16) × 2⁰ | 0.5 |
| `0x1p-3F` | 1 × 2⁻³, kiểu `float` | 0.125 |
| `0X1.0P+2D` | 1 × 2², kiểu `double` | 4 |

Được phép viết `0x1.p3` hoặc `0x1p3` (sau `0x1` có thể có hoặc không có dấu chấm), miễn là có chữ số significand và có `p`/`P` với số mũ hợp lệ.

**Tại sao dùng hex?** Các giá trị nhị phân như `0x1.8p1` có thể mô tả chính xác bit và lũy thừa 2, thuận lợi khi đọc tài liệu IEEE 754, kiểm tra bit hoặc cần giá trị nhị phân xác định. Chẳng hạn `0x1.0p-3` biểu diễn chính xác `0.125` trong binary32/binary64. Dùng số thực thập phân khi ý nghĩa nghiệp vụ theo hệ 10 dễ đọc hơn.

**Phân biệt với số nguyên hex:** `0x10` là literal nguyên `int` bằng 16; `0x10p0` là literal số thực `double` bằng 16. `0x1.8` không hợp lệ như một floating-point literal vì thiếu `p` và số mũ.

## 7. Dấu âm, dấu dương và ký tự gạch dưới

### 7.1. Dấu trước số và dấu trong phần mũ

Trong `-1.25F`, dấu `-` đứng trước literal là **toán tử một ngôi** tác động lên literal dương `1.25F`; bản thân token floating-point literal không bao gồm dấu âm phía trước. Ngược lại, dấu `-` ở `1e-3` hoặc `0x1p-3` **nằm trong phần số mũ** của literal.

Ví dụ:

```java
double negative = -1.5;
double thousandth = 1e-3;
double tinyPowerTwo = 0x1p-3;
double positive = +.5;
```

Các biến trên lần lượt có giá trị `-1.5`, `0.001`, `0.125` và `0.5`. Không đặt dấu `-` ở sau hậu tố: `1.5F-` không tạo literal âm.

### 7.2. Gạch dưới giữa các chữ số

Dấu `_` cho phép nhóm chữ số trong **phần nguyên, phần lẻ, phần mũ**, không thay đổi giá trị số:

```java
double a = 1_234.5_6;
double b = 1.2_5e+1_0;
float c = 0x1.8_0p+1F;
```

Các dạng này hợp lệ. `_` phải ở **giữa các chữ số của cùng một thành phần**. Những kiểu viết sau không hợp lệ:

```java
// double a = _1.0;    // gạch dưới ở đầu
// double b = 1_.0;    // ngay trước dấu chấm
// double c = 1._0;    // ngay sau dấu chấm
// double d = 1e_3;    // ngay sau e
// double e = 1e+_3;   // ngay sau dấu mũ
// float  f = 1.0_F;   // ngay trước hậu tố
// double g = 0x_1p0;  // ngay sau tiền tố 0x
```

Một literal có thể có nhiều dấu `_` liên tiếp **nếu chúng nằm giữa các chữ số**; dù hợp lệ, hãy ưu tiên nhóm rõ ràng, dễ đọc.

## 8. Độ chính xác và việc biên dịch literal

Khi `javac` gặp một literal hợp lệ, nó chuyển các chữ số nguồn thành giá trị khả biểu diễn của kiểu `float` hoặc `double` theo quy tắc của Java. Hai biểu diễn nguồn trông có vẻ cùng lượng toán học không có nghĩa mọi chữ số đều được giữ nguyên trong binary32/binary64.

### 8.1. 0.1 là trường hợp kinh điển

`0.1` trong hệ thập phân không biểu diễn chính xác bằng một số nhị phân hữu hạn. Do đó:

- `double d = 0.1;` tạo giá trị binary64 gần `0.1`.
- `float f = 0.1F;` tạo giá trị binary32 gần `0.1`.
- `double widened = f;` mở rộng **chính giá trị binary32 đã làm tròn**, không làm nó bằng giá trị binary64 của literal `0.1`.

Điều đáng chú ý là `System.out.println(0.1F)` vẫn có thể in `0.1`: thuật toán chuyển floating point sang chuỗi chọn dạng thập phân ngắn thể hiện lại giá trị đó; nó **không chứng minh** giá trị lưu chính xác bằng 1/10.

### 8.2. Hex có thể biểu diễn chính xác các phân số nhị phân

`0x1p-1` đúng bằng `0.5` và `0x1p-3` đúng bằng `0.125`. Các giá trị là bội/lũy thừa 2 phù hợp miền exponent và precision có thể biểu diễn chính xác ở dạng IEEE 754 nhị phân.

Không suy ra mọi literal hex đều không mất precision. Nếu significand có quá nhiều bit hoặc số mũ đưa giá trị ngoài miền biểu diễn, việc làm tròn hoặc lỗi biên dịch vẫn xảy ra.

### 8.3. Dùng BigDecimal khi yêu cầu thập phân chính xác

Nếu nghiệp vụ cần chính xác số thập phân như `0.1`, có thể tạo:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

Đây là **lời gọi constructor từ một `String`**, không phải một BigDecimal literal. Dùng `new BigDecimal(0.1)` mang giá trị nhị phân gần đúng của `double` vào đối tượng, nên không thay thế được cách tạo từ chuỗi nếu yêu cầu đúng `0.1` trong hệ thập phân.

## 9. Ranh giới: overflow, underflow và số đặc biệt

### 9.1. Literal quá lớn hoặc quá nhỏ

Java phân biệt giữa **floating-point literal ngoài miền biểu diễn** và **phép toán runtime sinh giá trị đặc biệt**.

- Một literal **khác 0** quá lớn đến mức chuyển theo rounding thành vô cực gây **lỗi biên dịch**.
- Một literal **khác 0** quá nhỏ đến mức chuyển theo rounding thành `0.0` cũng gây **lỗi biên dịch**.
- Nếu kết quả nhỏ nhưng vẫn là một **subnormal khác 0**, literal vẫn có thể hợp lệ.

Ví dụ sau cố ý **không biên dịch**:

```java
// double tooLarge = 1e400;   // tràn thành Infinity khi chuyển literal
// float tooLargeF = 1e40F;   // tràn miền float
// double tooTiny = 1e-400;   // literal khác 0 nhưng làm tròn thành zero
// float tooTinyF = 1e-50F;   // tương tự với float
```

Các comment trên để minh họa lỗi nếu bỏ dấu `//`; không nên xóa comment rồi ghép với các ví dụ chạy được.

Những giới hạn tham khảo: `Float.MAX_VALUE` là số `float` hữu hạn dương lớn nhất; `Double.MAX_VALUE` là số `double` hữu hạn dương lớn nhất. `Float.MIN_VALUE` và `Double.MIN_VALUE` là **số dương khác 0 nhỏ nhất (subnormal)** của mỗi kiểu, **không phải số âm nhỏ nhất**. `MIN_NORMAL` là số dương normal nhỏ nhất.

Ví dụ `1.4e-45F` là một dạng thập phân làm tròn thành `Float.MIN_VALUE`, còn `0x1p-149F` biểu diễn chính xác cùng giá trị nhỏ nhất này. Với `double`, `0x1p-1074` là giá trị `Double.MIN_VALUE`.

### 9.2. NaN và Infinity không phải literal từ khóa

Java **không** có cú pháp floating-point literal tên `NaN` hay `Infinity`. Sử dụng:

```java
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;
double notANumber = Double.NaN;

boolean ok = Double.isNaN(notANumber);
```

Phép toán runtime như `1.0 / 0.0` có thể cho `Infinity` và `0.0 / 0.0` có thể cho `NaN` theo phép toán số thực. Khác với `int` chia cho 0, phép chia số thực với 0 không mặc định ném `ArithmeticException`.

### 9.3. Dấu của số 0

`0.0` và `-0.0` được so sánh bằng `==` là `true`, nhưng IEEE 754 có hai mẫu bit khác nhau. Ví dụ `1.0 / 0.0` tạo dương vô cực, `1.0 / -0.0` tạo âm vô cực. Đây là lý do không nên coi `-0.0` hoàn toàn tương đương `0.0` trong mọi phép tính số thực.

## 10. Ví dụ hoàn chỉnh: đọc literal, phần mũ và hậu tố

Lưu toàn bộ nội dung thành **`FloatingLiterals.java`**:

```java
public class FloatingLiterals {
    public static void main(String[] args) {
        double decimal = 12.5;
        double leadingDot = .75;
        double scientific = 1.2e3;
        float asFloat = 1.25F;
        double hexadecimal = 0x1.8p1;
        float binaryExponent = 0x1p-3F;

        System.out.println(decimal);
        System.out.println(leadingDot);
        System.out.println(scientific);
        System.out.println(asFloat);
        System.out.println(hexadecimal);
        System.out.println(binaryExponent);
        System.out.println(Double.toHexString(hexadecimal));
        System.out.println(0.1F == 0.1);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 FloatingLiterals.java
java FloatingLiterals
```

**Stdout chính xác:**

```text
12.5
0.75
1200.0
1.25
3.0
0.125
0x1.8p1
false
```

Giải thích:

1. `12.5` và `.75` dùng cú pháp thập phân; `1.2e3` = 1200.0.
2. `1.25F` có kiểu `float` và được `println` in dưới dạng `1.25`.
3. `0x1.8p1` = (1 + 8/16) × 2 = `3.0`; `0x1p-3F` = 1/8 = `0.125`.
4. `Double.toHexString` tạo chuỗi biểu diễn hex của giá trị `double`; với `3.0`, kết quả `0x1.8p1`.
5. `0.1F == 0.1` là `false` vì toán hạng `float` được chuyển thành `double` để so sánh nhưng vẫn mang sai số làm tròn của binary32; hai toán hạng không chứa cùng giá trị.

## 11. Ví dụ hoàn chỉnh: precision, zero và giá trị đặc biệt

Lưu thành **`LiteralPrecision.java`**:

```java
public class LiteralPrecision {
    public static void main(String[] args) {
        double decimal = 0.1;
        float single = 0.1F;
        double widened = single;

        System.out.println(decimal == widened);
        System.out.println(widened);
        System.out.println(0x1.0p-1 == 0.5);
        System.out.println(Double.doubleToRawLongBits(-0.0)
                == Double.doubleToRawLongBits(0.0));
        System.out.println(Double.isInfinite(1.0 / 0.0));
    }
}
```

Chạy:

```bash
javac --release 17 LiteralPrecision.java
java LiteralPrecision
```

**Stdout chính xác:**

```text
false
0.10000000149011612
true
false
true
```

Diễn giải: chuyển `0.1F` sang `double` hiển thị rõ giá trị binary32 gần đúng; `0x1.0p-1` và `0.5` cùng đúng 1/2; zero dương/âm khác mẫu bit; phép chia `double` dương cho 0.0 tạo vô cực nên `Double.isInfinite` trả về `true`.

## 12. Những ví dụ sai cần nhận ra khi đọc mã

Các dòng sau là **mã cố ý sai** để nhận diện lỗi, không phải đoạn Java độc lập có thể biên dịch:

```java
// double a = 1e;         // phần mũ thiếu chữ số
// double b = 1e+;        // phần mũ thiếu chữ số sau dấu
// double c = 1e2.5;      // mũ không phải số nguyên
// double d = 0x1.8;      // hex float bắt buộc có p/P
// double e = 0x1.8e2;    // e là chữ số hex, không thay cho mũ p
// float  f = 1.25;       // literal double không tự gán vào float
// double g = 1.5L;       // L chỉ dành cho literal nguyên
// double h = 1e3L;       // không thể gắn L sau số thực
// double i = 1.0_M;      // underscore sai chỗ, M không phải hậu tố số thực
// double j = 1e400;      // literal khác 0 tràn thành Infinity
// float  k = 1e-50F;     // literal khác 0 underflow thành zero
```

Một lỗi đọc mã khác: tưởng `2e3F` nghĩa là 2 × 10³ rồi “đổi sang float ở cuối”. Trên thực tế, **toàn bộ token `2e3F`** là literal `float`, và giá trị của nó đã tuân theo quy tắc làm tròn binary32 khi được tạo.

## 13. Bảng quyết định nhanh

| Muốn biểu diễn | Viết | Tránh nhầm |
| --- | --- | --- |
| Số `double` theo thập phân | `2.5` hoặc `2.5D` | `2.5` mặc định đã là `double` |
| Số `float` theo thập phân | `2.5F` | `float x = 2.5;` không hợp lệ |
| Lũy thừa cơ số 10 | `2.5e3` | `e` không phải hằng số Euler |
| Lũy thừa cơ số 10 cho `float` | `2.5e3F` | Phần mũ không thay đổi quy tắc kiểu |
| Biểu diễn nhị phân bằng hex | `0x1.4p2` | Mũ hex dùng `p`, nghĩa là 2² |
| Hex số thực kiểu `float` | `0x1p-3F` | `0x1p-3` không hậu tố là `double` |
| Số nguyên hệ 16 | `0x10` | Đây là `int`, không phải hex float |
| Số thập phân tiền tệ chính xác | `new BigDecimal("2.50")` | Java không có `BigDecimal` literal |
| Vô cực/NaN | `Double.POSITIVE_INFINITY`, `Double.NaN` | `Infinity`/`NaN` không phải token literal |

## 14. Bài luyện tập và đáp án giải thích

**Bài 1 — Xác định kiểu.** Với `3`, `3F`, `3D`, `3.0`, `3e0`, `0x3p0`, `0x3`, hãy tự chia thành `int`/`float`/`double` trước khi xem đáp án.

Đáp án: `3` và `0x3` là `int`; `3F` là `float`; `3D`, `3.0`, `3e0` và `0x3p0` là `double`.

**Bài 2 — Tính giá trị mũ.** Tính bằng tay `1.5e2`, `1.5e-2`, `0x1.8p2` và `0x1p-4`.

Đáp án lần lượt: `150.0`, `0.015`, `6.0` và `0.0625`. Hai dạng đầu nhân lũy thừa 10; hai dạng sau nhân lũy thừa 2.

**Bài 3 — Tìm lỗi.** Các đoạn `float x = 2.5;`, `double y = 1e;`, `double z = 0x1.8;` lỗi ở đâu?

Đáp án: `2.5` mặc định là `double` và không thể tự chuyển hẹp sang `float`; `1e` thiếu số mũ; hex float `0x1.8` thiếu mũ `p`. Cách sửa tương ứng: `2.5F`, `1e0` và `0x1.8p0`.

**Bài 4 — Phân biệt precision.** Giải thích vì sao `double d = 0.1F;` và `double e = 0.1;` có thể khác nhau mặc dù hai biến đều có kiểu `double`.

Đáp án: kiểu **literal** quyết định bước làm tròn đầu tiên. `0.1F` đã làm tròn theo binary32 rồi mới mở rộng; `0.1` làm tròn trực tiếp theo binary64.

**Bài 5 — Đọc dấu.** Trong `-0x1p-3F`, có bao nhiêu dấu âm và vai trò từng dấu?

Đáp án: hai dấu. Dấu đầu là toán tử âm một ngôi tác động lên literal; dấu sau `p` là dấu của số mũ `-3`. Kết quả là `-0.125F`.

**Bài 6 — Phân biệt lỗi lúc biên dịch và runtime.** Tại sao `double x = 1e400;` lỗi biên dịch trong khi `double x = 1.0 / 0.0;` có thể tạo vô cực lúc chạy?

Đáp án: một **literal khác 0** được làm tròn thành vô cực là lỗi biên dịch theo JLS, còn phép chia floating point có quy tắc tạo giá trị IEEE 754 đặc biệt.

## 15. Checklist đã nắm vững

- [ ] Tôi phân biệt `1`, `1.0`, `1e0`, `1F` và `1D` về loại literal.
- [ ] Tôi giải thích được `e/E` nhân lũy thừa 10, `p/P` nhân lũy thừa 2.
- [ ] Tôi tự đổi được `0x1.8p1` sang `3.0` và hiểu vì sao hex float luôn cần phần mũ.
- [ ] Tôi biết literal không hậu tố là `double`; `F/f` là `float`; `D/d` xác nhận `double`.
- [ ] Tôi giải thích được vì sao `float x = 1.2;` lỗi dù giá trị có vẻ nhỏ.
- [ ] Tôi viết được underscore đúng chỗ, phân biệt dấu âm một ngôi với dấu của số mũ.
- [ ] Tôi không nhầm cách hiển thị `0.1F` với độ chính xác lưu trữ.
- [ ] Tôi biết literal quá lớn/quá nhỏ có thể lỗi **biên dịch**, còn `NaN`/`Infinity` là hằng số/API hoặc kết quả phép toán.
- [ ] Tôi chạy được hai ví dụ hoàn chỉnh và tự xác minh stdout.

**Tài liệu tiêu chuẩn để đối chiếu:** [Java Language Specification 17, `3.10.2 Floating-Point Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.2); [JLS 17, `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3); [Java SE 17, Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html); [Java SE 17, Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
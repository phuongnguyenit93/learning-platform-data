# Literal dấu phẩy động thập lục phân trong Java

> **Java core – numbers / Literal và cơ số**  
> Mục tiêu: đọc và tự viết hexadecimal floating-point literals, tính giá trị bằng tay, phân biệt chúng với literal số nguyên hệ 16 và số thực thập phân, hiểu lợi ích của cách viết theo lũy thừa của 2 khi kiểm tra `float`/`double`.

## 1. Khái niệm và động cơ

Java có **literal dấu phẩy động thập lục phân** (*hexadecimal floating-point literal*): viết một giá trị `float` hoặc `double` trong mã nguồn bằng **phần trị hệ 16** và **số mũ hệ 2**. Ví dụ:

```java
double a = 0x1.8p1;   // 3.0
double b = 0x1.0p-2;  // 0.25
float  c = 0x1.Ap2f;  // 6.5f
```

Điểm quan trọng nằm ở chữ **`p`**: nó tách phần trị (*significand*) khỏi số mũ nhị phân. Mặc dù phần trị viết bằng chữ số hệ 16, số mũ sau `p` biểu thị **lũy thừa của 2**, không phải lũy thừa của 16. Cú pháp này được Java hỗ trợ từ Java 5 và vẫn dùng được với Java 17+.

Vì `float` và `double` lưu số theo dạng dấu phẩy động **nhị phân** (IEEE 754), cách ghi hex này đặc biệt hữu ích để:

- mô tả một giá trị nhị phân chính xác và có thể tái lập trong mã nguồn;
- viết các giới hạn, hằng số dạng `2^k` và các giá trị sát nhau ở mức bit;
- kiểm tra phép làm tròn và sự khác nhau giữa giá trị `double` với biểu diễn thập phân trên màn hình;
- đọc kết quả của `Double.toHexString` và `Float.toHexString` khi gỡ lỗi tính toán.

Đây vẫn là literal cho **`float`/`double`**; không liên quan đến bù hai của số nguyên âm, không phải cú pháp `BigDecimal` và không tự tạo một loại số chính xác vô hạn.

## 2. Cú pháp: `0x...p...` và hậu tố kiểu

Một dạng tổng quát dễ nhớ:

```text
[+|-]  0x<hex-significand> p<decimal-exponent> [f|F|d|D]
       └── số hệ 16 ────┘   └──── số mũ 10 chữ số, tính theo cơ số 2 ────┘

Ví dụ: 0x1.8p+1
       |  |  | |
       |  |  | +-- số mũ +1, nghĩa là nhân 2^1
       |  |  +---- p: dấu mở đầu phần số mũ nhị phân
       |  +------- 1.8: phần trị hex, tương đương 1 + 8/16
       +---------- 0x: nhận diện hệ 16
```

Các thành phần:

1. **Tiền tố** `0x` hoặc `0X`: báo hiệu phần trị hệ 16.
2. **Phần trị (*significand*)** gồm chữ số `0–9` và `A–F`/`a–f`; có thể có dấu chấm `.` làm dấu phân cách phần nguyên và phần lẻ trong hệ 16. Cần ít nhất một chữ số hex.
3. **`p` hoặc `P` là bắt buộc** trong literal floating-point hex; ngay sau nó là số mũ thập phân có thể có dấu `+`/`-`. Các chữ số của số mũ phải là `0–9`.
4. **Hậu tố** `f`/`F` làm literal mang kiểu `float`; `d`/`D` hoặc không có hậu tố làm literal mang kiểu `double`.
5. Dấu `-` đầu biểu thức là **toán tử âm đơn ngôi**, không phải một phần chữ số của literal. Điều này ít khi ảnh hưởng đến sử dụng thông thường nhưng quan trọng trong cách Java phân tích cú pháp.

Các cách viết hợp lệ:

```java
double one       = 0x1p0;        // 1.0: không cần dấu chấm
double half      = 0x.8p0;       // 0.5: không cần chữ số trước dấu chấm
double two       = 0x1.p1;       // 2.0: không cần chữ số sau dấu chấm
double six       = 0X1.8P+2D;    // 6.0: viết hoa cũng hợp lệ
float eighth     = 0x1p-3F;     // 0.125f
double sixteen   = 0x1_0p0;     // 16.0: dấu _ nằm giữa các chữ số
```

Chữ `E`/`e` ở phần trị **là chữ số hệ 16 có giá trị 14**, không phải ký hiệu số mũ. Trong `0x1.ep3`, `e` thuộc phần trị, còn `p3` mới là số mũ. Tương tự, hậu tố `F`/`f` chỉ được hiểu là hậu tố kiểu khi nằm **sau toàn bộ số mũ**; `f` nằm trước `p` là chữ số hệ 16 có giá trị 15.

## 3. Công thức tính giá trị

Viết phần trị hệ 16 là `H` và số mũ sau `p` là số nguyên `E`. Giá trị toán học trước khi làm tròn về `float`/`double` là:

\[
\boxed{\text{Giá trị} = H_{16}\times 2^E}
\]

Ví dụ `0x1.8p1`:

- `0x1.8` = `1 + 8/16 = 1.5` (trong hệ thập phân).
- `p1` nghĩa là nhân `2^1 = 2`.
- Kết quả `1.5 × 2 = 3.0`.

Với phần trị có nhiều chữ số sau dấu chấm, chữ số ngay sau dấu chấm mang trọng số `16^(-1)`, chữ số thứ hai mang trọng số `16^(-2)`, tiếp tục như vậy.

Ví dụ `0xA.Cp-2`:

\[
0xA.C=10+\frac{12}{16}=10.75
\]

\[
0xA.Cp-2=10.75\times 2^{-2}=10.75/4=2.6875
\]

Bảng đối chiếu:

| Literal | Phần trị đổi sang thập phân | Hệ số `2^E` | Giá trị |
| --- | ---: | ---: | ---: |
| `0x1p0` | 1 | 1 | 1.0 |
| `0x1.8p1` | 1.5 | 2 | 3.0 |
| `0x1.8p-1` | 1.5 | 0.5 | 0.75 |
| `0x1p-4` | 1 | 1/16 | 0.0625 |
| `0xFp-4` | 15 | 1/16 | 0.9375 |
| `0x1.Ap2` | 1.625 | 4 | 6.5 |
| `0xA.Cp-2` | 10.75 | 1/4 | 2.6875 |
| `0x1.2p3` | 1.125 | 8 | 9.0 |
| `0x1_0.8p+2` | 16.5 | 4 | 66.0 |

**Không nhầm với số mũ của cơ số 16.** Nếu `p1` nghĩa là nhân 16, `0x1.8p1` sẽ thành 24; Java quy định nó bằng **3** vì `p1` là nhân 2.

## 4. Tại sao hệ 16 lại đi kèm lũy thừa của 2?

Một chữ số hex tương ứng đúng **4 bit nhị phân**:

```text
hex:   1   .   8
bits:  0001 . 1000
           = 1 + 1/2 = 1.5

0x1.8p1:
1.1 (nhị phân) × 2^1 = 11.0 (nhị phân) = 3.0
```

Ví dụ khác: số `10.625` trong hệ 10 là `1010.101` trong hệ 2. Ta có thể viết:

```text
10.625 (thập phân)
= 1010.101 (nhị phân)
= 0xA.Ap0  (A + A/16 = 10 + 10/16)
= 0x1.54p3 (1 + 5/16 + 4/256) × 8
```

Cả `0xA.Ap0` và `0x1.54p3` cùng biểu diễn số `10.625`. Dạng `0x1.54p3` có phần trị bắt đầu bằng `1`, gần với cách hiển thị **chuẩn hóa** mà API Java thường tạo cho số dấu phẩy động hữu hạn bình thường (*normal*).

Đối với các số có thể biểu diễn bằng hữu hạn chữ số nhị phân, hệ 16 rất thuận tiện: ví dụ `1/8 = 2^(-3) = 0x1p-3`. Ngược lại, `0.1` trong hệ 10 không thể biểu diễn bằng hữu hạn chữ số nhị phân; muốn ghi **giá trị `double` gần 0.1**, cần một mẫu nhị phân đã được làm tròn.

## 5. Phân biệt literal số nguyên hex và literal floating-point hex

`0x...` tự nó **chưa đủ** để là literal dấu phẩy động. Phần `pE` tạo khác biệt:

| Mã nguồn | Kiểu của literal | Giá trị |
| --- | --- | --- |
| `0x10` | `int` | 16 |
| `0x10L` | `long` | 16 |
| `0x10p0` | `double` | 16.0 |
| `0x10p0f` | `float` | 16.0f |
| `0x1Ap0` | `double` | 26.0 |
| `0x1e3` | `int` | 483 (`0x1E3`) |
| `0x1e3p0` | `double` | 483.0 |
| `0x1.8p1` | `double` | 3.0 |

Điểm tinh tế: `double value = 0x10;` có thể biên dịch vì Java chuyển `int 16` sang `double 16.0` khi gán. **Bản thân `0x10` vẫn là integer literal**. Còn `0x10p0` từ đầu đã là floating-point literal.

Hai cú pháp sai thường gặp:

```java
// KHÔNG biên dịch: phần trị có dấu chấm nhưng thiếu số mũ p...
// double wrong1 = 0x1.8;

// KHÔNG biên dịch: e không thay thế được p trong literal hex
// double wrong2 = 0x1.8e2;

// KHÔNG biên dịch: gán double literal sang float không qua phép chuyển kiểu
// float wrong3 = 0x1.8p1;
```

Cách đúng là `0x1.8p0` cho `1.5`; `0x1.8p1` cho `3.0`; và `0x1.8p1f` cho `float 3.0f`. Khi muốn `float` hãy ghi hậu tố `f`/`F` hoặc thực hiện chuyển kiểu có chủ đích, chú ý khả năng làm tròn.

## 6. Hậu tố, dấu gạch dưới và số mũ âm

Cú pháp hậu tố có cùng ý nghĩa như với literal dấu phẩy động thập phân:

```java
double d1 = 0x1.4p2;   // 5.0, double mặc định
double d2 = 0x1.4p2D;  // 5.0, ghi rõ double
float f1 = 0x1.4p2f;   // 5.0f, float
float f2 = 0X1.4P+2F;  // 5.0f, chữ hoa hợp lệ
```

Số mũ `p-4` có nghĩa nhân với `2^(-4)`, **không** phải “phần trị âm”; dấu của toàn giá trị vẫn phụ thuộc dấu ở đầu biểu thức.

```java
double x = 0x1p-4;   // +0.0625
double y = -0x1p-4;  // -0.0625
```

Dấu `_` được dùng để nhóm chữ số như trong các numeric literal khác, nhưng phải đặt **giữa các chữ số** của phần trị hoặc của số mũ, không đặt ở vị trí tùy ý.

```java
double valid = 0x1_0.8p1_0; // 16.5 × 2^10 = 16896.0

// SAI cú pháp: dấu _ không được đặt ngay sau 0x, bên cạnh
// dấu chấm, ngay sau p hoặc ngay trước hậu tố:
// double a = 0x_1.8p0;
// double b = 0x1_.8p0;
// double c = 0x1.8p_2;
// float  d = 0x1.8p0_f;
```

Đối với cả hai dạng chữ hoa/thường, chữ số của phần số mũ vẫn là **chữ số thập phân**. Ví dụ `0x1p10` mang số mũ mười (nhân `2^10`), **không** phải số mũ 16 vì `10` trông giống hai chữ số hex.

## 7. Quan hệ với IEEE 754 và khả năng biểu diễn chính xác

Một giá trị `double` bình thường hữu hạn theo IEEE 754 có 1 bit dấu, 11 bit số mũ và 52 bit phần phân số (tổng 64 bit). Đối với giá trị **normal** khác 0, phần trị hiệu dụng là `1.<fraction bits>` trong hệ 2 (bit 1 dẫn đầu không lưu tường minh). `float` có tổng 32 bit: 1 bit dấu, 8 bit số mũ và 23 bit phần phân số.

Đây là lý do literal hex thuận tiện: chuỗi chữ số hex mô tả trực tiếp các nhóm bit của phần trị nhị phân. Ví dụ, trong `double`:

```java
double exact = 0x1.8p1;                  // 3.0, đúng tuyệt đối
double oneTenth = 0x1.999999999999ap-4; // giá trị double gần 0.1
```

Giá trị `oneTenth` có cách hiển thị thập phân ngắn thường gặp là `0.1`, nhưng **giá trị nhị phân lưu bên trong không bằng chính xác 1/10**. Cú pháp literal hex ở đây mô tả rõ số `double` đã được làm tròn.

Đừng hiểu rằng “mọi literal hex tự động chính xác tuyệt đối”. Nếu phần trị cung cấp nhiều bit hơn độ chính xác `float`/`double`, hoặc giá trị quá sát một điểm giữa hai số có thể biểu diễn, compiler vẫn áp dụng quy tắc làm tròn của kiểu đích. Ưu điểm của hex là cách ghi tương thích trực tiếp với cơ số 2, đặc biệt khi ghi **giá trị vốn đã biểu diễn được** trong `double`/`float`.

Các giới hạn điển hình có thể ghi bằng hex:

```java
double maxFinite      = 0x1.fffffffffffffp1023; // Double.MAX_VALUE
double minNormal      = 0x1.0p-1022;           // Double.MIN_NORMAL
double minSubnormal   = 0x1p-1074;            // Double.MIN_VALUE

float maxFiniteFloat  = 0x1.fffffep127f;      // Float.MAX_VALUE
float minNormalFloat  = 0x1.0p-126f;          // Float.MIN_NORMAL
float minSubFloat     = 0x1p-149f;            // Float.MIN_VALUE
```

**Phân biệt `MIN_VALUE` và số âm nhỏ nhất:** trong `Double` và `Float`, `MIN_VALUE` là **số dương hữu hạn nhỏ nhất khác 0**, tức số *subnormal*; nó không phải giá trị âm lớn về độ lớn. Số âm hữu hạn có độ lớn lớn nhất là `-Double.MAX_VALUE` hoặc `-Float.MAX_VALUE`.

Literal hữu hạn cũng không thể chỉ cần tăng số mũ vô hạn: các literal khác 0 mà phép làm tròn khiến vượt thành vô cực hoặc thành 0 sẽ bị Java báo lỗi biên dịch. Khi cần tạo `NaN` hoặc các giá trị vô cực, dùng các hằng như `Double.NaN`, `Double.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY`; đó không phải các hexadecimal floating-point literals.

## 8. `Double.toHexString`, `Float.toHexString` và parse

Java có API để **xuất dạng hex của giá trị đã lưu**:

```java
Double.toHexString(3.0);        // "0x1.8p1"
Float.toHexString(3.0f);        // "0x1.8p1"
Double.toHexString(0.1);        // "0x1.999999999999ap-4"
Double.toHexString(-0.0);       // "-0x0.0p0"
```

Không phải mọi giá trị sẽ hiện đúng như dạng bạn gõ. Ví dụ `0xA.Ap0` và `0x1.54p3` đều biểu diễn `10.625`; `Double.toHexString(10.625)` trả dạng chuẩn hóa `"0x1.54p3"`.

- `Double.toHexString` và `Float.toHexString` trả **chuỗi ký tự**, hữu ích khi đối chiếu các giá trị nhị phân.
- `Double.parseDouble`/`Double.valueOf` và `Float.parseFloat`/`Float.valueOf` có thể đọc dạng chuỗi floating-point hex hợp lệ, ví dụ `"0x1.8p1"`.
- Khi kiểm tra bit thô, `Double.doubleToRawLongBits` và `Float.floatToRawIntBits` có vai trò khác: chúng trả **các bit mã hóa IEEE 754** dưới dạng `long`/`int`. Các bit thô này bao gồm cả bit dấu, số mũ thiên lệch và fraction; không phải chính chuỗi hexadecimal literal của giá trị.

Thử nghiệm:

```java
String representation = Double.toHexString(0.1);
double parsed = Double.parseDouble(representation);
System.out.println(representation);                   // 0x1.999999999999ap-4
System.out.println(parsed == 0.1);                    // true
```

Phép so sánh trên có ý nghĩa: sau khi phân tích chuỗi hex, `parsed` và literal decimal `0.1` tạo cùng một **giá trị `double` đã được làm tròn**. Nó **không** chứng minh `double` lưu phân số toán học 1/10 một cách tuyệt đối chính xác.

Các trường hợp `NaN` và vô cực xuất thành chuỗi đặc biệt như `"NaN"`, `"Infinity"` (không phải `0x...p...`); dấu `−0.0` được giữ khi xuất hex.

## 9. Chương trình Java 17+ chạy độc lập

Tạo file **`HexFloatLiteralDemo.java`**:

```java
public class HexFloatLiteralDemo {
    public static void main(String[] args) {
        double a = 0x1.8p1;
        double b = 0xA.Cp-2;
        float c = 0x1.Ap2f;

        int integerHex = 0x10;
        double floatingHex = 0x10p0;
        double normal = 0xA.Ap0;

        System.out.println("0x1.8p1 = " + a);
        System.out.println("0xA.Cp-2 = " + b);
        System.out.println("0x1.Ap2f = " + c);
        System.out.println("integer 0x10 = " + integerHex);
        System.out.println("floating 0x10p0 = " + floatingHex);
        System.out.println("toHexString(10.625) = "
                + Double.toHexString(normal));

        double decimal = 0.1;
        String exactHex = Double.toHexString(decimal);
        double parsed = Double.parseDouble(exactHex);

        System.out.println("decimal double 0.1 as hex = " + exactHex);
        System.out.println("parsed equals original = " + (parsed == decimal));
        System.out.println("negative zero as hex = "
                + Double.toHexString(-0.0));

        System.out.println("Double.MIN_VALUE as hex = "
                + Double.toHexString(Double.MIN_VALUE));
        System.out.println("Float.MIN_VALUE as hex = "
                + Float.toHexString(Float.MIN_VALUE));
    }
}
```

Từ thư mục chứa file:

```bash
javac HexFloatLiteralDemo.java
java HexFloatLiteralDemo
```

**Kết quả dự kiến với Java 17+:**

```text
0x1.8p1 = 3.0
0xA.Cp-2 = 2.6875
0x1.Ap2f = 6.5
integer 0x10 = 16
floating 0x10p0 = 16.0
toHexString(10.625) = 0x1.54p3
decimal double 0.1 as hex = 0x1.999999999999ap-4
parsed equals original = true
negative zero as hex = -0x0.0p0
Double.MIN_VALUE as hex = 0x0.0000000000001p-1022
Float.MIN_VALUE as hex = 0x0.000002p-126
```

Phân tích kết quả:

1. Ba literal đầu biểu diễn lần lượt `3`, `2.6875` và `6.5`; hậu tố `f` của `c` lựa chọn kiểu `float`.
2. `0x10` và `0x10p0` có cùng độ lớn, nhưng kiểu literal khác nhau.
3. `Double.toHexString(10.625)` đưa phần trị về dạng chuẩn hóa `1.54 × 2^3`.
4. Chuỗi cho `double 0.1` thể hiện giá trị nhị phân gần nhất, không phải phân số 1/10 chính xác.
5. `Double.MIN_VALUE`, `Float.MIN_VALUE` là các số **subnormal**. Cách xuất hex của API có phần trị dạng `0.000...` và số mũ tối thiểu cho số bình thường, nên **khác hình thức** literal ngắn `0x1p-1074` hoặc `0x1p-149f` nhưng cùng giá trị. Định dạng này không có nghĩa các hằng ở trên sai.

## 10. Quy trình đọc và chuyển một giá trị sang hex floating-point

Giả sử cần biểu diễn giá trị toán học `13.25` bằng cách chắc chắn mô tả theo cơ số hai.

**Bước 1: Đổi phần nguyên và phần lẻ sang nhị phân.**

- `13 = 1101₂`.
- `0.25 = 0.01₂`.
- `13.25 = 1101.01₂`.

**Bước 2: Nhóm bit theo bốn bit để lấy chữ số hex.**

`1101.0100₂ = D.4₁₆`. Vậy biểu diễn chưa chuẩn hóa là `0xD.4p0`.

**Bước 3: Chuyển về phần trị gần dạng chuẩn hóa `1.x × 2^E` (nếu muốn).**

`1101.01₂ = 1.10101₂ × 2³`. Nhóm fraction thành `1010 1000...₂`, tức `A8₁₆`. Ta có:

```text
13.25₁₀ = 1101.01₂
         = 0xD.4p0
         = 0x1.A8p3
         = (1 + 10/16 + 8/256) × 8
         = (1.65625) × 8
         = 13.25
```

`Double.toHexString(13.25)` trả `"0x1.a8p3"`. Trong dạng chuẩn hóa, số mũ `3` chỉ số vị trí dịch dấu phẩy nhị phân, **không** phụ thuộc bao nhiêu chữ số hex của phần trị.

**Bước 4: Chọn kiểu và hậu tố.** Nếu API cần `double`, `0x1.A8p3` đủ. Nếu cần `float`, viết `0x1.A8p3f`. Vì 13.25 có biểu diễn nhị phân hữu hạn và đủ ngắn, cả hai biểu diễn được chính xác.

## 11. Dùng literal hex ở đâu, tránh ở đâu?

**Nên dùng** khi đề bài gắn với bit, độ chính xác nhị phân hoặc các hằng đặc biệt:

- kiểm thử phép toán bit ở mức `float`/`double` và so sánh với giá trị IEEE 754 dự kiến;
- kiểm thử ranh giới trên/dưới giữa normal và subnormal;
- tái tạo một giá trị `double` đã nhìn thấy từ `Double.toHexString`;
- biểu diễn các số dễ viết bằng lũy thừa 2 như `0x1p-10` (1/1024) hoặc `0x1p20` (1,048,576).

**Ưu tiên literal thập phân** khi giá trị mang ý nghĩa nghiệp vụ theo hệ 10, như cân nặng hiển thị, đơn giá và tỉ lệ phần trăm trong tài liệu mà người đọc mong đợi số thập phân. Nếu bài toán yêu cầu **tính tiền thập phân chính xác và quy tắc làm tròn**, dùng `BigDecimal` từ chuỗi (ví dụ `new BigDecimal("0.1")`) thay vì cố gắng giải quyết bằng `double` viết hex. Literal hex giúp biểu diễn chính xác **một giá trị nhị phân của float/double**, không biến IEEE 754 thành số thập phân chính xác vô hạn.

**Tính dễ đọc:** tên hằng và lời giải thích lý do lựa chọn giúp người đọc hiểu tại sao viết `0x1.0p-1022` thay cho một chuỗi thập phân dài. Với số thông dụng như 3.0, cú pháp `3.0` thường đơn giản hơn `0x1.8p1` nếu không nghiên cứu biểu diễn bit.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả / cách sửa |
| --- | --- |
| Nghĩ `p3` là nhân `16^3` | Phải nhân `2^3` |
| Bỏ `p` vì đã có `0x` | Nếu phần trị có dấu chấm, literal hex floating-point phải có số mũ `p` |
| Dùng `e` làm số mũ hex | Trong phần trị hex, `e` là chữ số 14; phải dùng `p` hoặc `P` |
| Nghĩ `0x1e3` là số thực `1×10³` | Đó là integer literal hệ 16 có giá trị 483 |
| Gán `0x1p0` cho `float` mà không có hậu tố | Literal mặc định `double`; viết `0x1p0f` |
| Dùng dấu `_` cạnh `0x`, `.`, `p`, `f` | Sai quy tắc đặt underscore; chỉ nhóm chữ số |
| Tưởng literal hex không bao giờ làm tròn | Nếu quá nhiều bit hoặc vượt độ chính xác kiểu đích vẫn có làm tròn |
| Tưởng `0x1.999...p-4` là giá trị toán học 1/10 chính xác | Đây là `double` nhị phân gần 0.1 |
| Nhầm `Double.MIN_VALUE` là số âm lớn nhất | Nó là số dương subnormal nhỏ nhất khác 0 |
| Nhầm `Double.toHexString` với raw bits | Chuỗi hex là dạng số `significand × 2^exponent`, không phải 16 chữ số hex của toàn bộ 64 bit |

## 13. Bài tập tự kiểm tra và đáp án

**Bài 1.** Tính `0x1.Cp2` bằng tay.  
**Bài 2.** Phân biệt giá trị và loại literal của `0x10`, `0x10p1` và `0x10p1f`.  
**Bài 3.** Biểu diễn `0.375` thành hexadecimal floating-point literal.  
**Bài 4.** `0x1ep1` có phải giá trị `1 × 10¹` không? Tính kết quả.  
**Bài 5.** `Double.toHexString(0.1)` trả `0x1.999999999999ap-4`. Điều này chứng minh và không chứng minh điều gì?  
**Bài 6.** Viết literal `float` cho `5.5` và literal `double` cho `2^20`.

**Lời giải:**

1. `C₁₆ = 12`, nên `0x1.C = 1+12/16 = 1.75`; nhân `2²=4` cho `7.0`.
2. `0x10` là `int 16`; `0x10p1` là `double 32.0`; `0x10p1f` là `float 32.0f`.
3. `0.375 = 3/8 = 0.011₂ = 0x0.6p0`; cũng có thể viết `0x1.8p-2`.
4. Không. `e` là chữ số 14 nên `0x1e = 30`; `p1` nhân 2, kết quả **60.0**.
5. Nó cho biết chính xác **giá trị nhị phân đã được lưu** cho literal `double 0.1`. Nó không chứng minh rằng `double` lưu chính xác phân số toán học `1/10`.
6. `5.5 = 0x1.6p2f` vì `1.375 × 4 = 5.5`; `2^20 = 0x1p20` (kiểu `double`).

**Ghi nhớ:** Chữ số **hex** ở phần trị, chữ **`p`** đi với số mũ **cơ số 2**, hậu tố **`f`/`F`** để chọn `float` và mặc định là **`double`**. Cách viết này đặc biệt mạnh khi muốn hiểu hoặc tái tạo các giá trị dấu phẩy động nhị phân một cách rõ ràng.

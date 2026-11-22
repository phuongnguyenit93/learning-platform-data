# Dạng thập phân, ký hiệu mũ và dạng hex được API hỗ trợ trong Java

## 1. Đọc chuỗi thành số thực: phải phân biệt cú pháp với giá trị

Trong Java, **Double.parseDouble(String)** và **Float.parseFloat(String)** chuyển biểu diễn văn bản của số thực thành giá trị IEEE 754 tương ứng. Cả hai hỗ trợ dạng thập phân thông thường, ký hiệu mũ cơ số 10 và dạng thập lục phân (hexadecimal floating-point) có số mũ cơ số 2. Chúng cũng nhận một số biểu diễn đặc biệt như NaN và Infinity.

Ví dụ:

~~~java
double a = Double.parseDouble("12.5");     // 12.5
double b = Double.parseDouble("1.25e2");   // 125.0
double c = Double.parseDouble("0x1.8p1");  // 3.0
float d = Float.parseFloat("-2.5E-1");    // -0.25f
~~~

Điểm cần nhớ: **chuỗi truyền vào API** và **literal viết trực tiếp trong mã Java** có cú pháp gần nhau nhưng không đồng nhất. Một chuỗi hợp lệ cho parser chưa chắc được viết y nguyên thành literal không cần kiểu; ngược lại, ký tự gạch dưới phân tách chữ số được phép trong một số literal Java nhưng không được các phương thức parse này chấp nhận.

## 2. Ba nhóm biểu diễn chính

| Nhóm | Ví dụ chuỗi hợp lệ | Ý nghĩa |
| --- | --- | --- |
| Thập phân thông thường | "42", "-3.5", ".75", "8." | Chữ số cơ số 10, có thể có dấu và dấu chấm thập phân |
| Thập phân có mũ | "1e3", "-2.5E-2", "6.02e23" | Phần định trị nhân với 10 lũy thừa của số mũ |
| Hex có mũ nhị phân | "0x1.8p1", "0X1P-2", "-0xA.BP3" | Phần định trị viết ở cơ số 16, nhân với 2 lũy thừa của số mũ sau p/P |

Ở đây, dấu chấm thập phân trong chuỗi luôn là **dấu chấm (.)**, kể cả khi người dùng quen viết dấu phẩy. Dấu cộng/trừ có thể đứng trước toàn bộ số; dấu cộng/trừ cũng có thể đứng trong phần số mũ ngay sau e/E hoặc p/P.

### 2.1. Dạng thập phân

Các ví dụ đều hợp lệ với Double.parseDouble:

~~~text
0
123
+123.0
-0.125
.5
5.
0.000001
12f
12.5D
~~~

**f/F và d/D** là hậu tố kiểu số thực được bộ parse chấp nhận, kể cả khi phương thức trả về kiểu còn lại. Chẳng hạn, Double.parseDouble("12f") vẫn trả về giá trị kiểu double; hậu tố trong chuỗi không đổi kiểu trả về. Trong mã Java, nên ưu tiên chuỗi không có hậu tố khi nhận dữ liệu từ người dùng hoặc hệ thống ngoài.

Không được dùng dấu phân nhóm hàng nghìn trong chuỗi truyền cho Double.parseDouble: "1,000.5" không hợp lệ. Chuỗi "1_000.5" cũng không hợp lệ dù literal 1_000.5 trong *mã nguồn Java* là hợp lệ.

### 2.2. Ký hiệu mũ thập phân: e/E

Cú pháp trực giác là:

~~~text
[+|-]phần_định_trị[e|E][+|-]số_mũ_nguyên
~~~

Phần định trị là số thập phân; số mũ là số nguyên biểu diễn lũy thừa của **10**.

- "1.5e2" = 1.5 × 10² = 150.0.
- "4E-3" = 4 × 10⁻³ = 0.004.
- "-2.5e+1" = -2.5 × 10¹ = -25.0.
- "1e0" = 1.0.

Đã xuất hiện e/E thì phải có số mũ hợp lệ sau đó. "1e", "1e+" và "e3" đều không hợp lệ. Chữ e/E không có nghĩa là hằng số toán học Euler; đây là ký hiệu số mũ thập phân.

### 2.3. Dạng hex: 0x/0X và p/P

Một số thực hex có ba phần: tiền tố **0x hoặc 0X**, phần định trị bằng chữ số hex (0–9, a–f, A–F) có thể kèm dấu chấm, và **p/P cùng số mũ nguyên thập phân**. Về giá trị:

~~~text
(hex_significand) × 2^(exponent)
~~~

Ví dụ "0x1.8p1":

1. Phần nguyên hex **1** có giá trị 1.
2. Chữ số sau dấu chấm **8** ở cơ số 16 có giá trị 8/16 = 0.5.
3. Phần định trị bằng 1.5.
4. p1 nghĩa là nhân 2¹, nên kết quả bằng **3.0**.

Những ví dụ khác:

| Chuỗi | Phép tính | Kết quả |
| --- | --- | --- |
| "0x1p0" | 1 × 2⁰ | 1.0 |
| "0x1p-2" | 1 × 2⁻² | 0.25 |
| "0x1.8p2" | (1 + 8/16) × 2² | 6.0 |
| "0XAp1" | 10 × 2¹ | 20.0 |
| "0xA.Bp-1" | (10 + 11/16) × 2⁻¹ | 5.34375 |

**p/P là bắt buộc trong cú pháp số thực hex**, kể cả với số mũ bằng 0; "0x1" và "0xff" không được Double.parseDouble chấp nhận, còn "0x1p0" và "0xffp0" thì được. Số mũ sau p/P được viết bằng chữ số *thập phân* (ví dụ p10 nghĩa là nhân 2¹⁰); đây không phải số mũ cơ số 16. Chữ e trong phần định trị hex có thể là một chữ số hex nên không thay thế p/P.

Lý do dạng hex hữu ích: nó diễn tả một cách trực tiếp các phân số nhị phân và các lũy thừa của 2. Nhiều giá trị như 0.5, 0.25, 3.0 có thể được biểu diễn chính xác bằng dạng này; dạng thập phân như 0.1 thường phải làm tròn khi đưa về nhị phân.

## 3. Các chuỗi đặc biệt được chấp nhận

Ngoài chuỗi số hữu hạn, hai API còn nhận **"NaN"** (*not a number*) và **"Infinity"**, có thể kèm dấu cho dạng đặc biệt. Tên có phân biệt chữ hoa/chữ thường: "NaN" hợp lệ, "nan" không; "Infinity" hợp lệ, "infinity" không.

- "NaN": giá trị đặc biệt cho kết quả không phải số.
- "Infinity": vô cực dương.
- "-Infinity": vô cực âm.
- "-0.0": số không có bit dấu âm; nó có thể quan trọng trong một số phép toán và thao tác bit.

Không nên suy ra rằng mọi kết quả parse đều hữu hạn chỉ vì không xảy ra NumberFormatException. Khi số quá lớn để biểu diễn, parser có thể trả về Infinity; khi độ lớn quá nhỏ, parser có thể làm tròn về 0.0 hoặc giá trị *subnormal* thay vì ném ngoại lệ.

## 4. Ví dụ hoàn chỉnh: chạy và đối chiếu kết quả

Tạo tệp **FloatingTextFormsDemo.java**:

~~~java
public class FloatingTextFormsDemo {
    public static void main(String[] args) {
        String[] samples = {
                "12.5",
                "6.02e2",
                "0x1.8p1",
                "0x1p-2",
                "-0xA.Bp-1",
                "NaN",
                "Infinity",
                "1_000",
                "0xff",
                "1e"
        };

        for (String sample : samples) {
            try {
                double value = Double.parseDouble(sample);
                System.out.println(sample + " -> " + value);
            } catch (NumberFormatException exception) {
                System.out.println(sample + " -> INVALID");
            }
        }

        System.out.println("Hex form of 3.0: "
                + Double.toHexString(3.0));
        System.out.println("Overflow: "
                + Double.parseDouble("1e309"));
        System.out.println("Underflow: "
                + Double.parseDouble("1e-4000"));
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac FloatingTextFormsDemo.java
java FloatingTextFormsDemo
~~~

Kết quả chuẩn:

~~~text
12.5 -> 12.5
6.02e2 -> 602.0
0x1.8p1 -> 3.0
0x1p-2 -> 0.25
-0xA.Bp-1 -> -5.34375
NaN -> NaN
Infinity -> Infinity
1_000 -> INVALID
0xff -> INVALID
1e -> INVALID
Hex form of 3.0: 0x1.8p1
Overflow: Infinity
Underflow: 0.0
~~~

Chương trình minh họa bốn điều: cả ba cú pháp hợp lệ đều vào chung API; dạng hex có thể được đổi ngược qua Double.toHexString; chuỗi sai cú pháp phát sinh NumberFormatException; còn tràn số và mất độ lớn có thể trả ra giá trị đặc biệt hoặc 0.0.

**Double.toHexString(double)** sinh biểu diễn hex của giá trị double đang có (ví dụ 3.0 thành "0x1.8p1"); đây không phải phương thức phân tích một chuỗi đầu vào. Phép đổi qua lại giúp quan sát giá trị nhị phân đã được lưu nhưng không biến số thực nhị phân thành kiểu số có độ chính xác thập phân tùy ý.

## 5. Cú pháp literal trong mã Java khác cú pháp của chuỗi đưa vào API

Hãy phân biệt ngữ cảnh:

~~~java
double fromLiteral = 1_000.5;                  // Hợp lệ trong mã Java
double fromString = Double.parseDouble("1000.5"); // Hợp lệ
double fromHexLiteral = 0x1.8p1;             // Hợp lệ trong mã Java
double fromHexString = Double.parseDouble("0x1.8p1");
~~~

Không thể dùng cách sau để parse thành công:

~~~java
// Biên dịch được, nhưng lúc chạy ném NumberFormatException:
Double.parseDouble("1_000.5");
Double.parseDouble("0xff");
Double.parseDouble("0b1010");
Double.parseDouble("1,25");
~~~

Sự khác biệt quan trọng:

| Biểu thức hoặc chuỗi | Mã nguồn Java | Double.parseDouble |
| --- | --- | --- |
| 1_000.5 | Literal hợp lệ | Chuỗi "1_000.5" không hợp lệ |
| 0x1.8p1 | Literal double hợp lệ | Chuỗi "0x1.8p1" hợp lệ |
| 0xff | Literal số nguyên hex hợp lệ | Chuỗi "0xff" không hợp lệ dưới dạng số thực hex |
| 0b1010 | Literal số nguyên nhị phân hợp lệ | Chuỗi "0b1010" không hợp lệ |
| 1,25 | Không phải một literal số thực | Chuỗi "1,25" không hợp lệ |

Các ví dụ trong bảng so sánh **ngữ cảnh biên dịch** và **giá trị String lúc chạy**. Không đưa dấu ngoặc kép vào literal số; trong cột API, chúng biểu diễn một chuỗi.

## 6. Những chi tiết quyết định hành vi parser

### 6.1. Không có quy tắc dấu phẩy theo locale

Double.parseDouble và Float.parseFloat không dùng Locale để quyết định dấu thập phân: chuỗi chuẩn cần dấu chấm. Nếu dữ liệu đến từ giao diện người dùng theo vùng địa lý (ví dụ cách viết "1.234,5"), hãy dùng NumberFormat hoặc DecimalFormat với Locale xác định và chính sách kiểm tra phần dư của chuỗi. NumberFormat.parse có quy tắc và kiểu kết quả khác với Double.parseDouble; một số cấu hình có thể chỉ đọc được tiền tố hợp lệ, vì vậy cần kiểm tra vị trí parse khi đòi hỏi toàn chuỗi hợp lệ.

### 6.2. Khoảng trắng ở đầu/cuối và ở giữa

Các phương thức parse số thực chấp nhận một số ký tự điều khiển/khoảng trắng **đầu và cuối** tương ứng với hành vi String.trim() (ký tự có mã không lớn hơn U+0020). Chẳng hạn "  1.5  " hợp lệ. Không được tùy ý đặt khoảng trắng giữa chữ số, dấu chấm, ký hiệu mũ và số mũ: "1 e3" hoặc "0x1.8 p1" không hợp lệ. Không nên giả định mọi khoảng trắng Unicode đều được parser tự bỏ.

### 6.3. Độ chính xác, tràn và giá trị không hữu hạn

- **double** có 64 bit theo IEEE 754, xấp xỉ 15–17 chữ số thập phân có nghĩa; **float** có 32 bit, xấp xỉ 6–9 chữ số có nghĩa.
- Parser nhận dạng cú pháp rồi chuyển sang biểu diễn nhị phân với phép làm tròn phù hợp. Chuỗi hợp lệ không bảo đảm biểu diễn chính xác mọi chữ số thập phân.
- Double.parseDouble("1e309") trả về Infinity; Double.parseDouble("1e-4000") trả về 0.0.
- Float.parseFloat nhận cùng nhóm cú pháp nhưng có phạm vi và độ chính xác hẹp hơn; cùng một chuỗi có thể cho giá trị làm tròn khác với double.
- Nếu dữ liệu nghiệp vụ chỉ cho phép giá trị hữu hạn, kiểm tra bằng Double.isFinite/Float.isFinite sau khi parse. Nếu cần phát hiện mất độ chính xác hoặc ngoài phạm vi, phải xác định quy tắc dữ liệu trước khi chuyển đổi.

Ví dụ hàm tiện ích chỉ nhận số double hữu hạn:

~~~java
public static double parseFiniteDouble(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Gia tri phai huu han");
    }
    return value;
}
~~~

Đây là **đoạn phương thức để đặt vào một class**, không phải chương trình Java độc lập. Hàm chấp nhận mọi cú pháp mà Double.parseDouble chấp nhận, nhưng loại kết quả NaN và Infinity (kể cả Infinity do tràn). Hàm vẫn có thể nhận một số rất nhỏ bị làm tròn thành 0.0; tùy bài toán mà bổ sung bước xác minh.

### 6.4. Ngoại lệ và các phương thức liên quan

- **NumberFormatException**: chuỗi không khớp cú pháp số thực được hỗ trợ, ví dụ "", "1e", "0x1" hoặc "3,14".
- **NullPointerException**: truyền null vào Double.parseDouble/Float.parseFloat; xử lý null riêng nếu đầu vào có thể thiếu.
- **Double.valueOf(String)** và **Float.valueOf(String)** nhận cùng cú pháp và trả về lớp wrapper tương ứng; parseDouble/parseFloat trả về kiểu nguyên thủy.
- **Double.toString** và **Float.toString** cho chuỗi biểu diễn thập phân của giá trị đã lưu; **Double.toHexString** và **Float.toHexString** cho biểu diễn hex của giá trị tương ứng.

Khi hệ thống cần số thập phân chính xác để tính tiền hoặc lưu dữ liệu có quy tắc thập phân, cân nhắc **BigDecimal(String)** với chuỗi thập phân hợp lệ. BigDecimal không thay thế trực tiếp Double.parseDouble: nó không chấp nhận cú pháp số thực hex, NaN hay Infinity, và có ngữ nghĩa độ chính xác khác. Đừng tạo BigDecimal từ một double nếu mục tiêu là giữ nguyên chính xác chuỗi thập phân đầu vào; dùng constructor nhận String.

## 7. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| "1,23" bị từ chối | Dấu phẩy không phải dấu thập phân của parser | Dùng dấu chấm hoặc parser theo Locale |
| "1e" bị từ chối | Thiếu chữ số sau e/E | Bổ sung số mũ, ví dụ "1e0" |
| "0x10" bị từ chối | Dạng số thực hex thiếu p/P và số mũ | Dùng "0x10p0" nếu thực sự là số thực hex |
| "1_000.0" bị từ chối | Dấu gạch dưới chỉ là cú pháp literal trong mã Java | Bỏ dấu gạch dưới trước khi parse nếu dữ liệu cho phép |
| Parse thành công nhưng thành Infinity | Giá trị vượt phạm vi float/double | Kiểm tra isFinite và ràng buộc miền giá trị |
| Parse thành công nhưng thành 0.0 | Giá trị khác 0 quá nhỏ so với kiểu đích | Kiểm tra giới hạn miền và chọn biểu diễn phù hợp |
| Hiển thị đuôi chữ số lẻ | Làm tròn nhị phân của float/double | Không so sánh giá trị thập phân như thể luôn chính xác |

Không nên xử lý mọi NumberFormatException bằng cách âm thầm thay số 0. Việc này làm lẫn dữ liệu sai cú pháp với giá trị 0 hợp lệ. Với đầu vào bên ngoài, quy định rõ chuỗi có thể mang định dạng hex hay NaN/Infinity không; nếu chỉ chấp nhận dạng thập phân hữu hạn, phải thực thi thêm quy tắc kiểm tra đó.

## 8. Tự kiểm tra

1. Tại sao "1.2e3" có giá trị 1200.0 nhưng "0x1.2p3" có giá trị 9.0? Vì e dùng lũy thừa **10**, còn p dùng lũy thừa **2**; phần định trị hex 0x1.2 bằng 1 + 2/16 = 1.125, nhân 2³ bằng 9.0.
2. Double.parseDouble("0x1p-1") trả về gì? **0.5**.
3. Double.parseDouble("0x1e2") thành công không? **Không**: thiếu ký hiệu p/P và số mũ nhị phân. Chữ e nằm trong phần chữ số hex.
4. Double.parseDouble("1e309") có ném NumberFormatException không? **Không**: cú pháp hợp lệ nhưng giá trị vượt phạm vi double, kết quả là Infinity.
5. Muốn nhận số thập phân có phân cách theo ngôn ngữ/vùng và xác minh đã đọc hết đầu vào thì làm gì? Dùng **NumberFormat/DecimalFormat với Locale tường minh** và kiểm tra vị trí kết thúc parse; không mặc định rằng Double.parseDouble sẽ tự xử lý locale.

**Ghi nhớ:** Với API parse số thực chuẩn của Java, e/E biểu thị mũ cơ số 10; 0x...p/P... biểu thị phần định trị hex với mũ cơ số 2; cả hai được Double.parseDouble và Float.parseFloat hỗ trợ. Kiểm tra đồng thời **đúng cú pháp**, **đúng miền giá trị** và **độ chính xác cần thiết**.
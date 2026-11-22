# Unary numeric promotion trong Java

## 1. Khái niệm và mục tiêu

**Unary numeric promotion** (nâng kiểu số một ngôi) là quy tắc chuyển đổi kiểu số mà Java áp dụng cho **một toán hạng tại một thời điểm** trong những ngữ cảnh được Java Language Specification (JLS) quy định. Mục đích là tạo ra kiểu dữ liệu phù hợp để toán tử hay biểu thức có thể thực hiện phép tính.

Điểm cần nhớ: **byte, short và char được nâng thành int** trong unary numeric promotion. Điều này thường khiến kết quả của **+b**, **-s**, **~c** hoặc **b << 1** có kiểu **int**, dù biến ban đầu chỉ là byte, short hay char. Quy tắc cũng có thể **unbox** các kiểu wrapper như **Byte** hoặc **Long**.

Ví dụ:

~~~java
byte b = 5;
int x = +b;       // Hợp lệ: +b có kiểu int và giá trị 5
int y = -b;       // Hợp lệ: -b có kiểu int và giá trị -5
int z = ~b;       // Hợp lệ: ~b tính trên 32 bit kiểu int
// byte bad = +b; // Lỗi biên dịch: kết quả int không tự thu hẹp về byte
~~~

Trong ngữ cảnh trên, dấu **+** là toán tử dương một ngôi, không phải phép cộng hai số. Mọi ví dụ ở bài này dùng quy tắc của **Java 17+**.

## 2. Quy tắc chuyển kiểu

Bảng dưới đây áp dụng khi một toán hạng thực sự nằm trong **ngữ cảnh unary numeric promotion**:

| Kiểu ban đầu của toán hạng | Chuyển đổi | Kiểu sau promotion |
| --- | --- | --- |
| **byte** | Widening primitive conversion | **int** |
| **short** | Widening primitive conversion | **int** |
| **char** | Widening primitive conversion | **int** |
| **int** | Giữ nguyên | **int** |
| **long** | Giữ nguyên | **long** |
| **float** | Giữ nguyên | **float** |
| **double** | Giữ nguyên | **double** |
| **Byte**, **Short**, **Character**, **Integer** | Unboxing, rồi nâng lên int nếu cần | **int** |
| **Long** | Unboxing | **long** |
| **Float** | Unboxing | **float** |
| **Double** | Unboxing | **double** |

**boolean**, **Boolean** và **String** không phải toán hạng số hợp lệ cho unary numeric promotion. Các toán tử còn có ràng buộc riêng: chẳng hạn **~** chỉ chấp nhận kiểu nguyên sau promotion (**int** hoặc **long**), nên **~1.5f** không hợp lệ dù **float** là một kiểu số.

Không phải mọi giá trị được chuyển thành **int**. **long**, **float** và **double** giữ kiểu của mình nếu không có quy tắc khác từ ngữ cảnh bao quanh. Unary numeric promotion cũng **không tự nâng int lên long vì biến nhận kết quả là long**.

### Thứ tự áp dụng

1. Xét kiểu của biểu thức toán hạng tại thời điểm biên dịch.
2. Nếu đó là wrapper số, thực hiện **unboxing**. Khi giá trị wrapper là **null**, thao tác unbox phát sinh **NullPointerException** lúc chạy.
3. Nếu kết quả có kiểu **byte**, **short** hoặc **char**, nâng lên **int**; nếu đã là **int**, **long**, **float**, **double**, giữ nguyên.
4. Thực hiện toán tử hoặc sử dụng biểu thức theo ngữ nghĩa của ngữ cảnh.
5. Sau đó, nếu kết quả được gán cho một biến, áp dụng **quy tắc phép gán** riêng; không tự động đảo ngược bước promotion.

Sơ đồ:

~~~text
byte / short / char -------------> int
int -----------------------------> int
long ----------------------------> long
float ---------------------------> float
double --------------------------> double

Byte / Short / Character / Integer --unboxing--> int
Long ------------------------------unboxing--> long
Float -----------------------------unboxing--> float
Double ----------------------------unboxing--> double
~~~

**Widening** ở bước này không mất giá trị số nguyên của byte/short/char. Tuy nhiên, nếu một phép tính tiếp theo tràn giới hạn **int** hoặc **long**, đó là vấn đề số học sau promotion, không phải mất dữ liệu ngay trong bước mở rộng.

## 3. Các ngữ cảnh áp dụng

Theo JLS, unary numeric promotion xuất hiện trong các trường hợp sau:

| Ngữ cảnh | Ví dụ | Điều quan trọng |
| --- | --- | --- |
| Toán tử dương một ngôi **+** | **+someByte** | Kết quả có kiểu đã promotion |
| Toán tử âm một ngôi **-** | **-someShort** | Đổi dấu sau khi promotion |
| Toán tử bù bit **~** | **~someByte** | Toán hạng phải là int/long sau promotion |
| Toán tử dịch bit **<<**, **>>**, **>>>** | **someByte << distance** | **Mỗi toán hạng được promotion riêng** |
| Biểu thức kích thước khi tạo mảng | **new int[someByte]** | Kích thước phải có kiểu **int** sau promotion |
| Biểu thức chỉ số mảng | **array[someChar]** | Chỉ số phải có kiểu **int** sau promotion |

Các trường hợp tạo/truy cập mảng có kiểm tra bổ sung: **new int[1L]** và **array[1L]** không hợp lệ vì **long** không được tự chuyển thành **int** chỉ để làm kích thước hoặc chỉ số.

Lưu ý rằng một toán tử trông giống “một ngôi” **không nhất thiết** dùng cùng quy tắc. **++**, **--** là các toán tử có ngữ nghĩa cập nhật biến riêng; không được đánh đồng kiểu kết quả của chúng với toán tử **+**, **-**, **~**. Phần 8 giải thích trường hợp này.

## 4. Toán tử dương một ngôi: +x

**+x** tính toán giá trị sau khi promotion và giữ nguyên dấu, độ lớn của nó. Nó có thể **thay đổi kiểu tĩnh** của biểu thức:

~~~java
byte b = 12;
short s = 300;
char c = 'A';

int a = +b;  // 12
int q = +s;  // 300
int r = +c;  // 65 (mã UTF-16 của 'A')
~~~

**+b** và **b** cùng giá trị nhưng khác kiểu biểu thức: **b** là byte, **+b** là int. Điều này ảnh hưởng đến phép gán, overload của phương thức, suy luận kiểu của **var**, và những phép toán tiếp theo.

~~~java
byte b = 12;
var raw = b;        // raw có kiểu byte
var promoted = +b;  // promoted có kiểu int
~~~

Toán tử cộng hai ngôi **a + b** có quy tắc **binary numeric promotion**, khác với **+a** ở đây. Khi có chuỗi ký tự, **"x" + a** lại có thể là phép nối chuỗi, không phải unary numeric promotion.

## 5. Toán tử âm một ngôi: -x

Với **-x**, Java promotion toán hạng trước rồi lấy giá trị đối. Đây là lý do một byte nhỏ nhất có thể đổi dấu mà không bị tràn ở kiểu byte:

~~~java
byte b = -128;
int opposite = -b;  // 128, kiểu int
~~~

Phép trừ trên đã diễn ra trong int nên kết quả **128** hợp lệ. **char** là kiểu nguyên 16 bit không dấu, giá trị từ **0** đến **65535**, nhưng vẫn nâng thành int có dấu:

~~~java
char c = '\uFFFF';   // giá trị số 65535
int value = +c;      // 65535
int negative = -c;   // -65535
~~~

Ở đây không có “mã char âm”: **-c** là **int** âm sau phép tính. Giá trị char gốc không đổi.

### Tràn khi lấy dấu âm của int/long nhỏ nhất

Độ rộng int hoặc long là hữu hạn. Giá trị đối của **Integer.MIN_VALUE** (−2³¹) không biểu diễn được trong int. Java dùng kết quả tràn theo số học bù hai:

~~~java
int x = Integer.MIN_VALUE;
System.out.println(-x); // -2147483648
~~~

**-x** vẫn là int và vẫn bằng **Integer.MIN_VALUE**; không phát sinh ArithmeticException. **-Long.MIN_VALUE** có hiện tượng tương tự với long. Nếu thật sự cần giá trị dương của số int nhỏ nhất, có thể mở rộng **trước khi** lấy dấu âm:

~~~java
long positive = -(long) Integer.MIN_VALUE; // 2147483648L
~~~

Còn **long wide = -Integer.MIN_VALUE;** đã thực hiện phép đổi dấu trong int rồi mới gán sang long, nên nhận giá trị âm, không giải quyết tràn.

Với **float/double**, unary minus có ngữ nghĩa dấu của số chấm động, bao gồm **+0.0** và **-0.0**. Ví dụ **1.0 / -0.0** là **-Infinity**, khác với chia số nguyên cho 0.

## 6. Toán tử bù bit: ~x

**~** đảo từng bit của toán hạng **sau khi** promotion. Kết quả có kiểu **int** hoặc **long**; **~byte**, **~short** và **~char** đều tạo ra int 32 bit.

Với **byte b = -5**, việc nâng từ byte sang int sẽ kéo dài bit dấu:

~~~text
byte -5 (8 bit):          1111 1011
int -5  (32 bit): 11111111 11111111 11111111 11111011
~int -5:          00000000 00000000 00000000 00000100
Giá trị cuối:      4
~~~

Vì vậy **~b** cho ra **4**, không phải một byte âm hay giá trị có 8 bit được giữ nguyên. Với mọi int, đẳng thức số học **~x == -x - 1** đúng theo ngữ nghĩa int 32 bit.

Nếu muốn tính phép đảo trong **8 bit không dấu**, hãy **mask** kết quả trở lại 8 bit:

~~~java
byte b = 5;
int complement32 = ~b;           // -6
int complement8 = (~b) & 0xFF;  // 250 (0xFA)
~~~

Phép **& 0xFF** ở đây dùng toán tử bitwise AND; nó giới hạn mẫu kết quả còn 8 bit. Không nên coi việc này là chuyển kiểu byte có dấu, vì **250** không thuộc phạm vi **byte** của Java.

~~~java
// Hợp lệ
int result = ~((short) 0x00FF);

// Không hợp lệ: ~ yêu cầu kiểu nguyên sau promotion
// float f = ~1.5f;
~~~

## 7. Dịch bit: mỗi toán hạng được promotion độc lập

Java hỗ trợ ba toán tử dịch bit: **<<** (dịch trái), **>>** (dịch phải giữ bit dấu) và **>>>** (dịch phải chèn 0). Với từng biểu thức **left << distance**, **left >> distance**, **left >>> distance**, Java áp dụng unary numeric promotion **riêng cho left và distance**.

- Nếu toán hạng trái là **byte**, **short**, **char** hoặc **int**, kết quả phép dịch có kiểu **int**.
- Nếu toán hạng trái là **long**, kết quả có kiểu **long**.
- Toán hạng phải chỉ định khoảng dịch và có thể là int/long sau promotion. **long ở bên phải không khiến bên trái thành long**.
- Hai toán hạng, sau promotion, bắt buộc là kiểu nguyên; **float** hoặc **double** không hợp lệ để dịch bit.
- Với bên trái kiểu **int**, chỉ 5 bit thấp của khoảng dịch được xét: khoảng thực tế từ 0 đến 31 (**distance & 31**).
- Với bên trái kiểu **long**, chỉ 6 bit thấp của khoảng dịch được xét: khoảng thực tế từ 0 đến 63 (**distance & 63**).

Ví dụ:

~~~java
byte b = 1;
int a = b << 1;         // 2, kiểu int
int c = b << 33L;       // 2, do 33 & 31 == 1
long d = 1L << 33L;     // 8589934592L, kiểu long
long e = b << 33L;      // giá trị 2, int được mở rộng sang long SAU phép dịch
~~~

Đừng suy luận kiểu phép dịch từ biến **long e** ở vế trái dấu bằng: bản thân **b << 33L** vẫn là **int**.

### Dịch phải một byte âm: bẫy sign extension

~~~java
byte b = -5;
int x = b >>> 1;           // 2147483645
int y = (b & 0xFF) >>> 1;  // 125
~~~

Trong phép đầu tiên, **b** được mở rộng dấu từ **0xFB** thành int **0xFFFFFFFB** trước khi dịch phải logic 1 bit, được **0x7FFFFFFD** = **2147483645**. Trong phép thứ hai, **b & 0xFF** tạo ra int **251** (0x000000FB), dịch phải được **125**. Mục tiêu xử lý giá trị byte không dấu cần được nêu rõ và mask trước khi áp dụng phép dịch.

**Lưu ý**: phép **&** trong ví dụ là toán tử hai ngôi có cơ chế numeric promotion riêng; nó tạo ra giá trị int để thao tác tiếp. Còn toán tử dịch áp dụng unary numeric promotion cho từng toán hạng.

## 8. Kích thước và chỉ số mảng

Kích thước trong **new T[size]** và chỉ số trong **array[index]** là các ngữ cảnh sử dụng unary numeric promotion. Vì vậy byte, short, char và các wrapper tương ứng có thể được dùng làm chỉ số hoặc kích thước sau khi chuyển sang int:

~~~java
byte size = 3;
char index = 1;
int[] data = new int[size]; // size được nâng thành int
data[index] = 42;           // index được nâng thành int
~~~

Không nên hiểu là Java cho phép mọi số thực hoặc số nguyên không giới hạn ở đây:

~~~java
// Không biên dịch:
// int[] data = new int[3L];
// int value = data[1L];
// int[] other = new int[2.0];
// int element = data[1.5f];
~~~

Chỉ số phải là **int** sau promotion. Với giá trị nhỏ hơn 0 hoặc vượt độ dài mảng, mã vẫn có thể biên dịch nhưng sẽ thất bại ở lúc chạy (**NegativeArraySizeException** khi tạo mảng với kích thước âm; **ArrayIndexOutOfBoundsException** khi truy cập sai chỉ số).

## 9. Unary promotion khác binary promotion, phép gán và ++/--

Ba cơ chế này liên quan nhau nhưng không thay thế được nhau.

### Unary và binary numeric promotion

~~~java
byte a = 10;
short b = 20;

int first = +a;    // unary promotion: byte -> int
int second = a + b; // binary promotion: byte + short -> int
~~~

Với binary numeric promotion, Java xét hai toán hạng để xác định kiểu phép tính chung; có thể có **double**, **float** hoặc **long** tùy toán hạng. Với unary numeric promotion, Java chuyển **một toán hạng tại một thời điểm**; không có việc tìm kiểu chung giữa hai phía của phép dịch bit.

### Phép gán không tự thu hẹp kết quả int

~~~java
byte b = 10;
int ok = +b;         // Hợp lệ

// Không biên dịch:
// byte invalid1 = +b;
// byte invalid2 = -b;
// byte invalid3 = b << 1;

byte explicit = (byte) (+b); // Có ép kiểu tường minh
~~~

Việc ép kết quả int về byte có thể làm mất các bit cao hoặc khiến số dương thành âm khi vượt giới hạn −128..127. Chỉ cast khi quy tắc miền giá trị đã được xác nhận.

**Ngoại lệ liên quan hằng số:** một biểu thức **constant expression** có kiểu int và giá trị nằm trong phạm vi byte/short/char có thể được gán nhờ **constant narrowing**:

~~~java
byte a = +12;             // Hợp lệ: hằng int 12 nằm trong phạm vi byte
final byte b = 12;
byte c = +b;              // Hợp lệ: +b là constant expression có giá trị 12
byte d = 12;
// byte e = +d;           // Lỗi: d không phải biến hằng final
// byte f = +128;         // Lỗi: hằng 128 vượt phạm vi byte
~~~

Không rút ra kết luận “unary plus giữ kiểu byte” từ ví dụ **byte a = +12**: biểu thức **+12** vẫn có kiểu int, chỉ được phép thu hẹp trong ngữ cảnh gán hằng.

### ++, -- và phép gán kết hợp

Toán tử **++**, **--** làm thay đổi **biến** và có kiểu kết quả bằng kiểu biến đó. Chúng sử dụng quy tắc cập nhật và chuyển kết quả về kiểu của biến, khác với **+b** hoặc **-b** chỉ tạo ra một giá trị mới.

~~~java
byte b = 127;
b++;                     // Hợp lệ; b thành -128 do thu hẹp và tràn
byte after = b;          // Hợp lệ
b += 1;                  // Hợp lệ; phép gán kết hợp tự chuyển kết quả về byte
// b = b + 1;            // Lỗi: b + 1 có kiểu int
~~~

**b++** không phải là “unary numeric promotion khiến byte vẫn là byte”; toán tử cập nhật có đặc tả riêng, phép cộng trung gian và bước thu hẹp khi lưu lại biến. Cần phân biệt **giá trị cũ** của hậu tố **b++** với **giá trị mới** của tiền tố **++b**.

## 10. Wrapper và NullPointerException

Unary numeric promotion có thể thực hiện **unboxing**:

~~~java
Byte b = (byte) 12;
Short s = (short) 3;
Character c = 'A';
Integer i = 20;
Long l = 40L;
Float f = 2.5f;
Double d = 3.5;

int a = +b;  // 12: Byte -> byte -> int
int n = -s;  // -3: Short -> short -> int
int m = +c;  // 65: Character -> char -> int
int p = +i;  // 20: Integer -> int
long q = +l; // 40L: Long -> long
float r = -f;   // -2.5f
double t = -d;  // -3.5
~~~

Nếu wrapper là null, unboxing xảy ra trước khi toán tử có thể tính giá trị:

~~~java
Byte missing = null;
// int x = +missing; // Biên dịch được, khi chạy ném NullPointerException
~~~

Cần làm rõ sự khác biệt giữa **lỗi biên dịch do kiểu không phù hợp** và **lỗi runtime khi unbox null**. Nếu dữ liệu cho phép null, hãy kiểm tra điều kiện hoặc dùng giá trị mặc định phù hợp nghiệp vụ trước phép toán. Đừng mặc nhiên giả sử có giá trị 0.

## 11. Ví dụ tổng hợp Java 17+ có kết quả kiểm chứng

Lưu nguyên văn mã dưới đây thành **UnaryPromotionDemo.java**:

~~~java
public class UnaryPromotionDemo {
    static String type(int value) { return "int"; }
    static String type(long value) { return "long"; }
    static String type(float value) { return "float"; }
    static String type(double value) { return "double"; }

    public static void main(String[] args) {
        byte b = -5;
        short s = 300;
        char c = 'A';
        long l = 8L;
        float f = 1.5f;
        double d = 2.25;

        System.out.println("+byte: " + (+b) + " / " + type(+b));
        System.out.println("-short: " + (-s) + " / " + type(-s));
        System.out.println("-char: " + (-c) + " / " + type(-c));
        System.out.println("~byte: " + (~b) + " / " + type(~b));
        System.out.println("+long: " + (+l) + " / " + type(+l));
        System.out.println("-float: " + (-f) + " / " + type(-f));
        System.out.println("+double: " + (+d) + " / " + type(+d));

        int shifted = b >>> 1;
        int masked = (b & 0xFF) >>> 1;
        int left = ((byte) 1) << 33L;
        long wideLeft = 1L << 33L;
        System.out.println("negative byte >>> 1: " + shifted);
        System.out.println("(byte & 0xFF) >>> 1: " + masked);
        System.out.println("byte << 33L: " + left + " / " + type(left));
        System.out.println("1L << 33L: " + wideLeft + " / " + type(wideLeft));

        byte length = 2;
        char index = 1;
        int[] numbers = new int[length];
        numbers[index] = 99;
        System.out.println("array: length=" + numbers.length + ", a[1]=" + numbers[1]);

        Byte boxed = (byte) 12;
        Long boxedLong = 13L;
        System.out.println("+Byte: " + (+boxed) + " / " + type(+boxed));
        System.out.println("-Long: " + (-boxedLong) + " / " + type(-boxedLong));

        byte edge = 127;
        edge++;
        System.out.println("byte after ++: " + edge);
        System.out.println("-Integer.MIN_VALUE: " + (-Integer.MIN_VALUE));
        System.out.println("1.0 / (-0.0): " + (1.0 / -0.0));
    }
}
~~~

Biên dịch với JDK 17 trở lên:

~~~bash
javac UnaryPromotionDemo.java
java UnaryPromotionDemo
~~~

Kết quả stdout:

~~~text
+byte: -5 / int
-short: -300 / int
-char: -65 / int
~byte: 4 / int
+long: 8 / long
-float: -1.5 / float
+double: 2.25 / double
negative byte >>> 1: 2147483645
(byte & 0xFF) >>> 1: 125
byte << 33L: 2 / int
1L << 33L: 8589934592 / long
array: length=2, a[1]=99
+Byte: 12 / int
-Long: -13 / long
byte after ++: -128
-Integer.MIN_VALUE: -2147483648
1.0 / (-0.0): -Infinity
~~~

Trong ví dụ, các phương thức **type(int)**, **type(long)**, **type(float)**, **type(double)** được overload để cho thấy **kiểu tĩnh** mà trình biên dịch chọn cho kết quả; đây không phải cách kiểm tra kiểu cần dùng trong ứng dụng bình thường. Chuỗi in có dấu **+byte** chỉ là nhãn, còn phép promotion thực sự nằm trong **(+b)**.

Các điểm nên tự giải thích sau khi chạy:

- **-char** cho **-65 / int**, vì char 'A' được nâng thành int 65 trước khi lấy dấu âm.
- **~byte** cho **4 / int**, vì byte -5 được mở rộng dấu lên int trước khi đảo 32 bit.
- **byte << 33L** cho **2 / int**; kiểu long của khoảng dịch không làm bên trái thành long.
- **byte after ++** cho **-128**, vì phép tăng lưu kết quả thu hẹp vào biến byte.
- **-Integer.MIN_VALUE** vẫn là số âm nhỏ nhất của int; phép tính không tự mở rộng thành long.

## 12. Các lỗi phổ biến và cách khắc phục

| Lỗi thường gặp | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gán **+byte**, **-short** hoặc **~char** vào biến cùng kiểu nhỏ | Kết quả expression đã được nâng thành **int** | Dùng biến int hoặc cast có kiểm tra phạm vi |
| Nghĩ **+x** luôn giữ kiểu của **x** | Unary plus thực hiện numeric promotion | Xét kiểu toán hạng trước khi đoán kiểu biểu thức |
| Thấy **byte b = +12** chạy được rồi kết luận **+b** trả byte | Hằng int được thu hẹp nhờ constant narrowing | Phân biệt kiểu biểu thức và phép chuyển đổi khi gán |
| Nghĩ **byte << long** có kết quả long | Hai toán hạng dịch bit được promotion riêng | Xét kiểu toán hạng **bên trái** |
| Dịch phải **>>>** byte âm và gặp số dương rất lớn | Sign extension trước phép dịch 32 bit | Với byte không dấu, cân nhắc **b & 0xFF** |
| Dùng **~byte** và chỉ mong 8 bit | Toán tử bù áp dụng trên **int 32 bit** | Mask **& 0xFF** khi cần mẫu bit 8 bit |
| Truyền long vào kích thước hoặc chỉ số mảng | Quy tắc yêu cầu int sau promotion | Chuyển đổi có kiểm tra giới hạn trước khi truy cập |
| Dùng wrapper null với unary + hoặc - | Unboxing ném **NullPointerException** | Xử lý null trước thao tác số |
| Nghĩ **++byte** luôn trả int như **+byte** | **++** có quy tắc cập nhật biến riêng | Phân biệt phép toán đọc giá trị và phép toán cập nhật |
| Nghĩ **-Integer.MIN_VALUE** là số dương | Tràn trong phạm vi int | Mở rộng sang long **trước** khi đổi dấu |

Khi đọc một biểu thức số, hãy theo thứ tự: **kiểu gốc của từng toán hạng → có unboxing hay promotion không → kiểu phép toán → giá trị phép toán → chuyển đổi trong phép gán**. Cách phân tích này đặc biệt có ích khi gặp lỗi “possible lossy conversion from int to byte” hoặc kết quả dịch bit khác kỳ vọng.

## 13. Bài tập tự kiểm tra (kèm đáp án)

**Bài 1.** Cho **byte b = 100;**. Các biểu thức **+b**, **-b**, **~b** lần lượt có kiểu gì? Giá trị là gì?

Đáp án: đều kiểu **int**; giá trị lần lượt **100**, **-100**, **-101**. Với int, **~100 == -101**.

**Bài 2.** **byte a = 5; byte x = +a;** có biên dịch được không? **byte x = +5;** thì sao?

Đáp án: câu đầu **không**, vì **+a** là int không phải constant expression; câu thứ hai **có**, vì **+5** là hằng int nằm trong miền byte và được thu hẹp khi gán.

**Bài 3.** **short s = 1; long result = s << 32L;** cho giá trị nào?

Đáp án: **1**. Kiểu trái sau promotion là int, nên khoảng dịch thực tế **32 & 31 = 0**; biểu thức trả int 1 rồi mới mở rộng sang long để gán.

**Bài 4.** **char c = '\uFFFF'; int x = -c;** cho giá trị nào?

Đáp án: **-65535**. Char được chuyển thành int 65535 rồi đổi dấu; không có bước diễn giải char như short có dấu.

**Bài 5.** **Byte x = null; int y = +x;** thất bại ở biên dịch hay lúc chạy?

Đáp án: biên dịch **hợp lệ**, lúc chạy ném **NullPointerException** khi unboxing x.

**Bài 6.** Vì sao **byte b = 127; b++;** hợp lệ, còn **b = b + 1;** không?

Đáp án: **++** cập nhật và chuyển kết quả về kiểu byte theo quy tắc riêng; **b + 1** có kiểu int do binary numeric promotion nên phép gán thường vào byte bị từ chối.

## 14. Tài liệu gốc

- [Java Language Specification, Java SE 17 — §5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): định nghĩa unary numeric promotion, unboxing, widening và các ngữ cảnh áp dụng.
- [JLS Java SE 17 — §15.15 Unary Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.15): ngữ nghĩa unary +, -, ~ và sự khác biệt của ++/--.
- [JLS Java SE 17 — §15.19 Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): kiểu kết quả, promotion riêng của hai toán hạng và giới hạn khoảng dịch.
- [JLS Java SE 17 — §5.2 Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): trường hợp gán hằng số int sang byte/short/char.
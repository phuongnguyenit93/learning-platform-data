# Phép gán kết hợp `+=`, `-=`, `*=`, `/=` và `%=` — Java 17+

**Phép gán kết hợp** (*compound assignment*) vừa thực hiện phép toán vừa **gán kết quả trở lại biến hoặc vị trí lưu trữ ở vế trái**. Năm toán tử số học thường gặp là:

| Toán tử | Ý nghĩa | Ví dụ với `x = 10` | Giá trị `x` sau phép gán |
| --- | --- | --- | ---: |
| `+=` | Cộng rồi gán | `x += 5;` | 15 |
| `-=` | Trừ rồi gán | `x -= 3;` | 7 |
| `*=` | Nhân rồi gán | `x *= 2;` | 20 |
| `/=` | Chia rồi gán | `x /= 4;` | 2 nếu `x` là `int` |
| `%=` | Lấy phần dư rồi gán | `x %= 3;` | 1 |

**Lưu ý:** mỗi hàng trong bảng được hiểu là ví dụ độc lập, đều bắt đầu từ `x = 10`. Các toán tử này không tạo một loại biến mới: sau phép gán, **kiểu khai báo của biến vẫn giữ nguyên**.

~~~java
int score = 10;
score += 5;        // score = 15.
score *= 2;        // score = 30.
score -= 4;        // score = 26.
~~~

## 1. Cách hiểu chính xác hơn “viết tắt của phép gán”

Về mặt ý nghĩa, đối với vế trái có kiểu `T`, phép `E1 op= E2` tương ứng với phép tính rồi **chuyển kết quả về `T`**, với hai khác biệt quan trọng so với tự mở rộng cú pháp: **`E1` chỉ được đánh giá một lần**, và **phép gán kết hợp có chuyển kiểu về kiểu vế trái**.

~~~text
E1 op= E2

Gần tương đương về giá trị với:
E1 = (T) ((E1) op (E2))

Ngoại lệ quan trọng: E1 chỉ được đánh giá MỘT lần trong op=.
~~~

Ví dụ:

~~~java
int total = 10;
total += 4; // 14.
~~~

Với `int` đơn giản, kết quả giống `total = total + 4`. Nhưng không nên coi đây là một thao tác thay thế văn bản máy móc cho mọi kiểu và mọi biểu thức vế trái.

**Phép gán kết hợp vẫn là một biểu thức có giá trị**; tuy nhiên, khi không cần giá trị của phép gán, cách viết một câu lệnh riêng thường dễ đọc hơn:

~~~java
int count = 3;
count += 2; // Nen dung khi chi muon cap nhat bien.
~~~

## 2. Chương trình Java 17+ chạy độc lập

Tạo tệp UTF-8 tên **`CompoundAssignmentDemo.java`**:

~~~java
import java.util.Arrays;

public class CompoundAssignmentDemo {
    public static void main(String[] args) {
        int value = 10;
        value += 5;
        System.out.println("plus=" + value);
        value -= 3;
        System.out.println("minus=" + value);
        value *= 2;
        System.out.println("multiply=" + value);
        value /= 5;
        System.out.println("divide=" + value);
        value %= 3;
        System.out.println("remainder=" + value);

        byte small = 120;
        small += 10;
        System.out.println("byteOverflow=" + small);

        short medium = 30_000;
        medium *= 2;
        System.out.println("shortOverflow=" + medium);

        char letter = 'A';
        letter += 1;
        System.out.println("charNext=" + letter);

        int fractional = 3;
        fractional += 2.5;
        System.out.println("fractionalNarrowing=" + fractional);

        int negative = -10;
        negative %= 3;
        System.out.println("negativeRemainder=" + negative);

        int captured = 5;
        captured += (captured = 10);
        System.out.println("capturedOldValue=" + captured);

        int[] data = {10, 20};
        int index = 0;
        data[index++] += 7;
        System.out.println("array=" + Arrays.toString(data)
                + ",index=" + index);

        String message = "Java";
        message += " 17";
        message += ": " + (1 + 2);
        System.out.println("message=" + message);

        int numerator = 12;
        int zero = 0;
        try {
            numerator /= zero;
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }
        System.out.println("unchangedAfterException=" + numerator);

        double floating = 1.0;
        floating /= 0.0;
        System.out.println("floatingDivision=" + floating);

        double floatRemainder = 0.0;
        floatRemainder %= 0.0;
        System.out.println("floatingRemainderNaN="
                + Double.isNaN(floatRemainder));

        int overflowing = Integer.MAX_VALUE;
        overflowing += 1;
        System.out.println("intOverflow=" + overflowing);
    }
}
~~~

Tại thư mục chứa file, mở PowerShell (Windows) hoặc Bash (Linux/macOS), sử dụng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CompoundAssignmentDemo.java
java CompoundAssignmentDemo
~~~

**Expected stdout chính xác** của lệnh `java CompoundAssignmentDemo`:

~~~text
plus=15
minus=12
multiply=24
divide=4
remainder=1
byteOverflow=-126
shortOverflow=-5536
charNext=B
fractionalNarrowing=5
negativeRemainder=-1
capturedOldValue=15
array=[17, 20],index=1
message=Java 17: 3
integerZero=ArithmeticException
unchangedAfterException=12
floatingDivision=Infinity
floatingRemainderNaN=true
intOverflow=-2147483648
~~~

`java -version` và `javac -version` có đầu ra phụ thuộc máy và không thuộc khối expected stdout trên.

## 3. Điểm khác phép gán thông thường: chuyển kiểu ngầm

Khi thực hiện phép gán kết hợp, Java dùng kiểu của các toán hạng để tính phép toán, sau đó **chuyển kết quả về kiểu của biến vế trái** theo quy tắc của compound assignment.

~~~java
byte b = 120;
b += 10; // Hop le, b thanh -126 vi ket qua 130 bi thu hep ve byte.
~~~

Trong khi đó:

~~~java
byte b = 120;
// b = b + 10; // Loi bien dich: b + 10 co kieu int, khong tu gan ve byte.
b = (byte) (b + 10); // Hop le voi cast tuong minh.
~~~

Trong ví dụ trên, `byte` có miền từ `-128` đến `127`. Kết quả toán học 130 không biểu diễn được bằng `byte`; phép chuyển kiểu thu hẹp giữ những bit thấp thích hợp, khiến giá trị thành **-126**. `+=` **không tự kiểm tra overflow**.

Với `short` và `char` cũng cần chú ý việc phép toán số học thường thực hiện qua numeric promotion:

~~~java
short amount = 30_000;
amount *= 2; // 60000 thu hep ve short: -5536.

char ch = 'A';
ch += 1; // 'B'.
~~~

Một trường hợp còn khó nhận ra hơn:

~~~java
int count = 3;
count += 2.5; // Hop le, ket qua int la 5.
// count = count + 2.5; // Loi: double khong tu gan duoc vao int.
~~~

Ở `count += 2.5`, phép cộng tạo `double 5.5`, rồi kết quả được chuyển về `int`, thành **5**. Phép thu hẹp số thực thành số nguyên ở Java **cắt phần thập phân về 0** trong miền giá trị biểu diễn được. Do đó tránh gán kết hợp giữa các kiểu có thể gây mất dữ liệu nếu bài toán yêu cầu chính xác.

| Biểu thức | Có biên dịch? | Diễn giải |
| --- | --- | --- |
| `byte b = 1; b += 1;` | Có | `byte` được cập nhật sau chuyển kiểu |
| `byte b = 1; b = b + 1;` | Không | `b + 1` có kiểu `int` |
| `char c = 'A'; c += 1;` | Có | Ký tự kế tiếp theo đơn vị mã `char` |
| `int x = 3; x += 2.5;` | Có | `double 5.5` bị thu hẹp về `int 5` |
| `int x = 3; x = x + 2.5;` | Không | `double` không tự gán vào `int` |

**Nguyên tắc thực hành:** Khi các toán hạng có kiểu khác nhau, đừng chỉ nhìn vào tính hợp lệ khi biên dịch; hãy kiểm tra **kiểu phép toán trung gian và chuyển kiểu cuối cùng**.

## 4. Vế trái chỉ được đánh giá một lần

Đây là lý do **`a[i++] += 7` không tương đương** với phép thay thế văn bản `a[i++] = a[i++] + 7`.

~~~java
int[] numbers = {10, 20};
int i = 0;
numbers[i++] += 7;
// numbers = [17, 20]; i = 1.
~~~

Phép gán kết hợp trước tiên xác định vị trí `numbers[i++]` đúng một lần, lưu giá trị cũ của phần tử, đánh giá biểu thức bên phải và gán kết quả trở lại **chính vị trí đó**. `i++` chỉ tăng `i` một lần.

Nếu thay thủ công bằng `numbers[i++] = numbers[i++] + 7`, `i++` xuất hiện hai lần: các vị trí đọc/ghi và trạng thái sau phép gán có thể khác. Vì vậy **không tự khai triển `op=` khi vế trái có tác dụng phụ**.

Đối với biến đơn giản, thứ tự đánh giá cũng có thể quan sát được:

~~~java
int n = 5;
n += (n = 10);
System.out.println(n); // 15.
~~~

Giá trị cũ của `n` là **5** được giữ cho phép cộng, rồi vế phải gán `n = 10` và trả giá trị 10; cuối cùng `+=` ghi kết quả **15**. Biểu thức này hợp lệ nhưng **khó đọc**, không nên bắt chước khi mã có thể viết thành nhiều bước.

## 5. `/=`: phân biệt phép chia nguyên và chia số thực

~~~java
int count = 10;
count /= 4;   // 2, vi phep chia int cat phan thap phan.

double rate = 10.0;
rate /= 4;    // 2.5.
~~~

- `int /= int` thực hiện chia nguyên; phần dư thập phân không được giữ lại.
- `double /= int` áp dụng numeric promotion rồi cho kết quả `double`.

**Chia cho 0** có hành vi khác nhau:

~~~java
int x = 12;
int zero = 0;
try {
    x /= zero;
} catch (ArithmeticException ex) {
    System.out.println("division failed");
}
// x van bang 12, do phep gan chua hoan tat binh thuong.

double y = 1.0;
y /= 0.0; // Infinity, khong nem ArithmeticException.
~~~

Với số nguyên, `/= 0` ném `ArithmeticException` và phép gán kết hợp **không ghi kết quả**. Với số thực, `Infinity`/`NaN` tuân theo quy tắc IEEE 754; nếu cần giá trị hữu hạn, phải kiểm tra bằng `Double.isFinite` hoặc `Float.isFinite`.

## 6. `%=`: phần dư không phải lúc nào cũng không âm

~~~java
int n = -10;
n %= 3; // -1.
~~~

Toán tử `%` trên số nguyên dùng thương chia **cắt về 0**. Phần dư khác 0 có **cùng dấu với số bị chia** (toán hạng trái). Đổi dấu số chia không bắt buộc đổi dấu phần dư.

~~~java
int a = 10;
a %= -3; // 1.

int b = -10;
b %= -3; // -1.
~~~

Nếu cần **chỉ số vòng không âm** với modulus dương, `Math.floorMod(value, positiveModulus)` thường đúng ý hơn `value % positiveModulus` khi `value` có thể âm. Đó là phép tính mới, không có toán tử gán kết hợp riêng `floorMod=`.

Với `double`, `0.0 % 0.0` tạo `NaN` chứ không ném `ArithmeticException` như `int % 0`. Phải phân biệt kiểu toán hạng trước khi suy luận kết quả.

## 7. `+=` cũng dùng cho `String`

`+=` có thể **nối chuỗi**, không chỉ cộng số:

~~~java
String label = "Java";
label += " 17";
label += ": " + (1 + 2);
System.out.println(label); // Java 17: 3.
~~~

`String` bất biến: mỗi phép nối tạo giá trị chuỗi kết quả rồi gán lại biến `label`; nó không sửa nội dung của `String` cũ. Với phép nối nhiều lần trong vòng lặp lớn, `StringBuilder` thường thích hợp hơn.

Trong `label += ": " + (1 + 2)`, dấu ngoặc đảm bảo `1 + 2` được cộng số trước khi nối chuỗi. Nếu viết `label += ": " + 1 + 2`, phần nối với chuỗi có thể cho `": 12"` theo cách nhóm của toán tử `+`.

**`-=`, `*=`, `/=` và `%=` không phải toán tử hợp lệ để thao tác `String` theo phép toán số học.**

## 8. Tràn số, chuyển kiểu và giới hạn an toàn

~~~java
int count = Integer.MAX_VALUE;
count += 1; // -2147483648: tran int, khong nem exception.
~~~

Phép gán kết hợp nguyên **không tự phát hiện overflow**. Nếu yêu cầu báo lỗi thay vì cho kết quả bị tràn, dùng phép toán kiểm tra:

~~~java
int count = Integer.MAX_VALUE;
// count = Math.addExact(count, 1);
// Nem ArithmeticException neu vuot mien int.
~~~

Với phép toán số học chính xác hơn, lựa chọn giải pháp theo nhu cầu:

- `Math.addExact`, `subtractExact`, `multiplyExact` dành cho kiểm tra overflow trong phạm vi nguyên thủy tương ứng.
- `BigInteger` dùng cho số nguyên vượt phạm vi `long`.
- `BigDecimal` có thể dùng khi cần phép tính thập phân với chính sách scale/rounding rõ ràng.

Các lớp `BigInteger` và `BigDecimal` không cho dùng `+=` trực tiếp giữa hai đối tượng như primitive; phải gọi phương thức thích hợp và gán lại biến:

~~~java
java.math.BigDecimal total = new java.math.BigDecimal("1.25");
total = total.add(new java.math.BigDecimal("2.50"));
~~~

## 9. Lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`b += 1` giống hệt `b = b + 1` với `byte`.” | `b += 1` cho phép chuyển kiểu thu hẹp; `b = b + 1` không biên dịch |
| “`+=` luôn bảo toàn đầy đủ phần thập phân.” | `int += double` có thể cắt phần thập phân |
| “Vế trái được đánh giá hai lần.” | Compound assignment chỉ đánh giá **vị trí vế trái một lần** |
| “`x /= 4` luôn là phép chia số thực.” | Nếu `x` và `4` là `int`, đây là chia nguyên |
| “`%` luôn cho phần dư không âm.” | Số bị chia âm có thể cho phần dư âm |
| “`+=` trên `String` cộng các giá trị số.” | Khi tham gia nối chuỗi, `+` có thể tạo văn bản |
| “`x += 1` ném lỗi khi `int` tràn.” | Không; dùng `Math.addExact` khi cần kiểm tra |
| “Nếu `x /= 0` ném lỗi, `x` được gán 0.” | Phép gán không hoàn tất; giá trị cũ vẫn giữ |
| “`/ 0.0` và `/ 0` luôn giống nhau.” | Phép chia số thực có thể cho `Infinity`/`NaN` |

## 10. Bài tập tự kiểm tra

1. `int x = 10; x += 3; x *= 2;` cho `x` bằng bao nhiêu?  
   *Đáp án:* **26**.
2. `byte b = 120; b += 10;` cho kết quả gì?  
   *Đáp án:* **-126**, do kết quả 130 bị chuyển về kiểu `byte`.
3. `int n = 3; n += 2.5;` cho `n` bằng bao nhiêu?  
   *Đáp án:* **5**, vì `double 5.5` bị thu hẹp về `int`.
4. `int n = 10; n /= 4;` cho kết quả gì?  
   *Đáp án:* **2**, phép chia nguyên.
5. `int n = -10; n %= 3;` cho kết quả gì?  
   *Đáp án:* **-1**, dấu theo số bị chia.
6. `int[] a = {10, 20}; int i = 0; a[i++] += 7;` thay đổi mảng và `i` ra sao?  
   *Đáp án:* Mảng thành **`[17, 20]`**, `i = 1`; vị trí vế trái chỉ được đánh giá một lần.
7. `int x = 5; x += (x = 10);` cho `x` bằng bao nhiêu?  
   *Đáp án:* **15**, vì toán hạng trái đã lưu giá trị 5.
8. `String s = "A"; s += 1 + 2;` cho chuỗi gì?  
   *Đáp án:* **`"A3"`** vì toàn biểu thức bên phải tính `1 + 2` trước khi nối vào `s`.

## Checklist

- [ ] Phân biệt `+=`, `-=`, `*=`, `/=`, `%=` theo phép toán của từng loại toán hạng.
- [ ] Hiểu phép gán kết hợp **gán lại về cùng kiểu vế trái** và có thể thu hẹp ngầm.
- [ ] Nhớ vế trái `E1` chỉ được đánh giá **một lần**.
- [ ] Với số nguyên, chú ý phép chia cắt phần thập phân và dấu của `%`.
- [ ] Phân biệt chia/lấy dư với số chia zero của số nguyên và số thực.
- [ ] Nhận diện overflow và giá trị bị cắt khi chuyển về `byte`/`short`/`int`.
- [ ] Biết `String +=` là nối chuỗi, không phải phép cộng số.
- [ ] Chọn `Math.*Exact` hoặc lớp số lớn/chính xác nếu yêu cầu vượt khả năng primitive.

**Kết luận:** Phép gán kết hợp trong Java là phép toán **và gán lại**, với hai điểm không thể bỏ qua: **vế trái chỉ được đánh giá một lần**, và **kết quả có thể bị chuyển thu hẹp về kiểu vế trái**. Hiểu các quy tắc đó giúp tránh lỗi với `byte`/`short`, số thực, chỉ số mảng, tràn số và phép nối chuỗi.

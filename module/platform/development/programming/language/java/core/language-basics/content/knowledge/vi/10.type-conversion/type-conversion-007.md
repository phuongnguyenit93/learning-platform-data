# Vì sao phép cộng `byte` hoặc `short` thường cho kết quả `int` trong Java?

> **Java core — language-basics / Chuyển đổi kiểu**  
> **Môi trường:** JDK 17 trở lên; không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu quy tắc *binary numeric promotion* của Java, phân biệt kiểu của **biểu thức cộng** với kiểu của biến đích, nhận diện ngoại lệ hằng số, xử lý `+=`/`++` và dự đoán chính xác kết quả khi ép hẹp.

## 1. Giá trị nhỏ không quyết định kiểu kết quả

Xem đoạn mã:

~~~java
byte left = 10;
byte right = 20;

int sum = left + right; // Hợp lệ, sum = 30.
// byte bad = left + right; // Lỗi biên dịch: int cannot be converted to byte.
~~~

Hai biến nguồn đều là `byte` nhưng biểu thức `left + right` có kiểu **`int`**, kể cả khi giá trị 30 hoàn toàn nằm trong phạm vi `byte`.

Tương tự:

~~~java
short a = 100;
short b = 200;
int total = a + b; // total = 300; biểu thức có kiểu int.
// short bad = a + b; // Lỗi biên dịch.
~~~

**Vì sao?** Java quy định phép cộng số học hai ngôi `+` dùng **binary numeric promotion** (*nâng kiểu số học hai ngôi*) để chọn kiểu chung **trước khi thực hiện phép cộng**. Với kiểu nguyên nhỏ `byte`, `short` hoặc `char`, các toán hạng được nâng lên `int` (trừ khi có toán hạng `long`/`float`/`double` làm kiểu chung rộng hơn).

Kiểu của biểu thức được xác định theo **quy tắc ngôn ngữ và kiểu toán hạng**, không dựa trên việc kết quả chạy thực tế có vừa `byte` hay `short` hay không.

## 2. Vì sao kiểu kết quả là `int`?

Toán tử cộng số `+` sử dụng *binary numeric promotion*. Nếu có toán hạng `double`, `float` hoặc `long`, Java chọn kiểu tương ứng theo thứ tự đó; trong các trường hợp còn lại, các toán hạng số được nâng thành `int`. Vì thế `byte + byte`, `short + short`, `char + byte` đều có kiểu `int`. Quy tắc dựa trên **kiểu khai báo của biểu thức**, không phụ thuộc giá trị tổng tại runtime.

Chú ý: `"x=" + byteValue` là nối chuỗi, còn toán tử `+x` là phép một ngôi có quy tắc nâng kiểu riêng. Các ví dụ dưới đây tập trung vào lỗi gán kết quả cộng số nhỏ về kiểu hẹp và cách xử lý chính xác.
## 3. Vì sao `byte result = a + b;` báo lỗi dù tổng nằm trong miền?

`byte` có miền giá trị **-128 đến 127**; `short` từ **-32768 đến 32767**. Tuy nhiên Java kiểm tra kiểu của phép gán theo **kiểu biểu thức**, không suy đoán giới hạn của biến tại runtime.

~~~java
byte x = 10;
byte y = 20;
// byte z = x + y; // KHÔNG biên dịch: x + y có kiểu int.

int safe = x + y;        // Nên dùng khi xử lý số học.
byte explicit = (byte) (x + y); // Hợp lệ: cast tường minh.
~~~

Với phép ép `(byte)`, Java giữ **8 bit thấp** của `int` rồi diễn giải kết quả như `byte` có dấu. Nếu kết quả số học nằm ngoài miền `byte`, giá trị sẽ đổi theo các bit còn lại.

~~~java
byte a = 120;
byte b = 10;
int correctSum = a + b;       // 130
byte narrowed = (byte) (a + b); // -126
~~~

Với `short`, khi ép hẹp từ `int` Java giữ **16 bit thấp**:

~~~java
short a = 30_000;
short b = 10_000;
int sum = a + b;          // 40000
short narrowed = (short) sum; // -25536
~~~

Bước cộng từ hai `byte` hoặc hai `short` là phép cộng `int` nên **không bị tràn ở kiểu nhỏ trong chính bước đó**. Giá trị âm lạ xuất hiện do **ép hẹp / lưu trở lại kiểu nhỏ**. Với những biểu thức có nhiều phép tính `int`, vẫn phải xét khả năng tràn `int` ở các bước trung gian.

## 4. Vì sao `byte c = 10 + 20;` lại biên dịch được?

Có **ngoại lệ cho một số phép gán hằng số nguyên tại thời điểm biên dịch** (*constant expression narrowing*).

~~~java
byte a = 10 + 20;       // Hợp lệ: biểu thức hằng int = 30, vừa byte.
short b = 1_000 + 200;  // Hợp lệ: hằng 1200 vừa short.

// byte bad = 100 + 30; // Lỗi: 130 vượt miền byte.
~~~

Ở đây phép `10 + 20` **vẫn có kiểu `int`**; Java cho phép **ngầm thu hẹp hằng số int** khi giá trị tính ngay lúc biên dịch vừa miền của `byte`, `short` hoặc `char` trong ngữ cảnh gán phù hợp.

Biến `final` có thể tham gia nếu thật sự là **biến hằng tại thời điểm biên dịch**:

~~~java
final byte x = 10;
final byte y = 20;
byte c = x + y; // Hợp lệ: biểu thức hằng có giá trị 30.

byte p = 10;
byte q = 20;
// byte d = p + q; // KHÔNG hợp lệ: p và q không phải compile-time constants.
~~~

Không suy ra rằng `x + y` ở ví dụ `final` có kiểu `byte`: kiểu biểu thức **vẫn là `int`**. Chỉ riêng quy tắc chuyển hằng khi **gán** cho phép lưu kết quả 30 vào `byte`. Đọc dữ liệu runtime, field không hằng hoặc tham số method không được hưởng ngoại lệ này.

## 5. `+=` và `++`: cú pháp ngắn, có chuyển kiểu ngầm

Với biến `byte`/`short`:

~~~java
byte score = 120;
// score = score + 10; // Lỗi: vế phải có kiểu int.
score += 10;           // Hợp lệ: cộng rồi chuyển ngầm trở lại byte.
System.out.println(score); // -126
~~~

`score += 10` gần tương đương với `score = (byte) (score + 10)`, nhưng biến ở vế trái chỉ được **đánh giá một lần** (quan trọng với biểu thức có tác dụng phụ). Vì có bước chuyển hẹp ngầm nên `+=` **không tự bảo vệ khỏi mất dữ liệu**.

`score++` cũng tăng rồi lưu trở lại kiểu của biến. Ví dụ `byte n = 127; n++;` cho `n == -128`. Đó là quy tắc tràn khi kết quả được lưu về `byte`, không phải phép `+` hai ngôi giữ nguyên kiểu `byte`.

**Khuyến nghị:** Khi yêu cầu bảo toàn giá trị tính toán, giữ kết quả ở `int` hoặc rộng hơn thay vì dùng `+=` trên `byte`/`short` và mặc nhiên coi kết quả an toàn.

## 6. Chương trình Java 17+ chạy được

Tạo tệp **SmallIntegerAdditionDemo.java**:

~~~java
public final class SmallIntegerAdditionDemo {
    public static void main(String[] args) {
        byte a = 10;
        byte b = 20;
        int byteSum = a + b;
        System.out.println("bytePlusByte=" + byteSum);

        short s1 = 20_000;
        short s2 = 20_000;
        int shortSum = s1 + s2;
        System.out.println("shortPlusShort=" + shortSum);

        byte small = 10;
        short middle = 20;
        int mixedSum = small + middle;
        System.out.println("bytePlusShort=" + mixedSum);

        byte high = 120;
        byte extra = 10;
        int expanded = high + extra;
        byte narrowed = (byte) (high + extra);
        System.out.println("expanded=" + expanded);
        System.out.println("narrowedByte=" + narrowed);

        short narrowedShort = (short) shortSum;
        System.out.println("narrowedShort=" + narrowedShort);

        byte constantSum = 10 + 20;
        final byte fa = 10;
        final byte fb = 20;
        byte finalConstantSum = fa + fb;
        System.out.println("constantByte=" + constantSum);
        System.out.println("finalConstantByte=" + finalConstantSum);

        byte compound = 120;
        compound += 10;
        System.out.println("compoundByte=" + compound);

        byte incremented = 127;
        incremented++;
        System.out.println("incrementedByte=" + incremented);

        byte base = 5;
        System.out.println("bytePlusLong=" + (base + 1L));
        System.out.println("bytePlusFloat=" + (base + 1.0f));
        System.out.println("charPlusByte=" + ('A' + (byte) 1));

        byte divisor = 2;
        System.out.println("integerDivision=" + (base / divisor));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 SmallIntegerAdditionDemo.java
java SmallIntegerAdditionDemo
~~~

**Expected output chính xác:**

~~~text
bytePlusByte=30
shortPlusShort=40000
bytePlusShort=30
expanded=130
narrowedByte=-126
narrowedShort=-25536
constantByte=30
finalConstantByte=30
compoundByte=-126
incrementedByte=-128
bytePlusLong=6
bytePlusFloat=6.0
charPlusByte=66
integerDivision=2
~~~

Giải thích nhanh:

- `a + b`, `s1 + s2` và `small + middle` đều có kiểu `int`. `shortSum` là 40.000 dù không thể cất trong `short`.
- `(byte) 130` thành **-126** vì giữ 8 bit thấp; `(short) 40000` thành **-25536** vì giữ 16 bit thấp.
- Hai phép gán hằng biên dịch được nhờ giá trị compile-time nằm trong miền `byte`, **không** làm thay đổi kiểu `int` của phép cộng.
- `compound += 10` và `incremented++` lưu kết quả trở lại `byte`, nên có thể đổi dấu ở biên.
- Khi cộng với `long` hoặc `float`, kiểu chung lần lượt là `long`/`float`. `'A' + (byte) 1` là `int` 66 vì `char` có code unit giá trị 65.
- `base / divisor` là phép chia hai số nguyên đã được nâng thành `int` nên 5 chia 2 cho **2**, không phải 2.5.

## 7. Mẫu viết nên dùng khi làm bài toán thật

| Nhu cầu | Nên viết | Lý do |
| --- | --- | --- |
| Cộng `byte`/`short` để tính toán | `int total = a + b;` | Giữ kết quả không bị cắt về kiểu nhỏ |
| Tổng có thể vượt `int` | `long total = (long) a + b;` | Nâng toán hạng **trước** phép tính khi cần |
| Bắt buộc lưu lại dưới dạng `byte` | Kiểm tra `sum >= Byte.MIN_VALUE && sum <= Byte.MAX_VALUE` trước cast | Không mất giá trị ngoài ý muốn |
| Bắt buộc lưu lại dưới dạng `short` | Kiểm tra `sum` trong miền `Short.MIN_VALUE` … `Short.MAX_VALUE` | Phát hiện out-of-range |
| Dùng `+=` cho bộ đếm nhỏ | Chỉ khi đã chủ động kiểm tra giới hạn | `+=` có chuyển hẹp ngầm |
| Phép chia cần số lẻ | `double ratio = (double) a / b;` | Không chia nguyên trước khi gán `double` |

Ví dụ kiểm tra trước khi ép hẹp:

~~~java
int sum = a + b;
if (sum < Byte.MIN_VALUE || sum > Byte.MAX_VALUE) {
    throw new ArithmeticException("sum out of byte range");
}
byte safe = (byte) sum;
~~~

Đây là cách chọn có chủ đích khi một giao thức/tệp nhị phân yêu cầu đúng **8 bit**; còn trong code tính toán thông thường, giữ `int` cho phép cộng các giá trị nhỏ thường rõ ràng hơn.

## 8. Bài tập tự luyện

**Bài 1.** Cho `byte x = 7, y = 8;`. Vì sao `byte z = x + y;` lỗi biên dịch, dù 15 vừa `byte`? Viết hai cách hợp lệ và phân tích độ an toàn của từng cách.

**Bài 2.** Dự đoán `int total = (short) 30_000 + (short) 10_000;` và `short stored = (short) total;`. Thời điểm nào có mất giá trị?

**Bài 3.** So sánh `byte a = 10 + 20;`, `final byte x = 10, y = 20; byte b = x + y;` và `byte p = 10, q = 20; byte c = p + q;`. Dòng nào biên dịch được? Kiểu biểu thức `+` có khác nhau không?

**Bài 4.** Cho `byte n = 127;`. Thử `n++;` và `n += 1;` ở hai lần chạy riêng. Vì sao hai thao tác có thể đưa `n` về -128?

**Bài 5.** Cho `byte a = 5, b = 2;`. Dự đoán `a / b` và `(double) a / b`. Phân biệt kiểu số học trước phép chia.

### Ghi nhớ

**`byte + byte`, `short + short` và `byte + short` đều cho biểu thức kiểu `int`** vì quy tắc **binary numeric promotion**. Kiểu kết quả không phụ thuộc việc tổng có vừa kiểu nhỏ hay không. Gán một **biểu thức hằng `int`** vừa miền là ngoại lệ của luật chuyển hằng, không thay đổi kiểu phép cộng. Ép kiểu, `+=` và `++` có thể làm mất dữ liệu khi lưu trở lại `byte`/`short`: hãy chủ động kiểm tra giới hạn hoặc giữ kết quả bằng `int`.

# Cộng, trừ, nhân, chia và phép lấy phần dư trong Java

> **Java core — language-basics / Số học**  
> **Yêu cầu:** JDK 17 trở lên; một file Java độc lập, không dùng thư viện ngoài.  
> **Mục tiêu:** Dùng đúng năm toán tử số học `+`, `-`, `*`, `/`, `%`; dự đoán kiểu và kết quả, phân biệt chia nguyên/số thực, hiểu dấu của phần dư, chia cho 0 và những giới hạn của số nguyên/số thực.

## 1. Năm phép toán số học cơ bản

Với `int a = 10, b = 3;`:

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
| --- | --- | --- | ---: |
| `+` | Cộng | `a + b` | 13 |
| `-` | Trừ | `a - b` | 7 |
| `*` | Nhân | `a * b` | 30 |
| `/` | Chia | `a / b` | 3 |
| `%` | Lấy phần dư | `a % b` | 1 |

~~~java
int a = 10;
int b = 3;

int sum = a + b;
int difference = a - b;
int product = a * b;
int quotient = a / b;
int remainder = a % b;
~~~

**Lưu ý quan trọng:** Với hai số nguyên, `10 / 3` cho **3**, không phải 3.333...; `10 % 3` cho **1** vì `10 = 3 * 3 + 1`. Toán tử `%` trả **phần dư của phép chia**, không phải phần trăm.

`+` còn dùng để **nối chuỗi**:

~~~java
System.out.println("sum=" + 10 + 3);   // sum=103
System.out.println("sum=" + (10 + 3)); // sum=13
~~~

Dấu ngoặc phân biệt cộng số trước khi nối chuỗi.

## 2. Kiểu dữ liệu quyết định phép chia

Khi **cả hai toán hạng đều là số nguyên**, `/` là **chia nguyên**: kết quả bỏ phần lẻ theo hướng về 0.

~~~java
int integerResult = 7 / 2;           // 3
double stillThree = 7 / 2;           // 3.0: chia nguyên xảy ra trước khi gán.
double fractional = 7.0 / 2;         // 3.5
double byCast = (double) 7 / 2;      // 3.5
~~~

Muốn có phần lẻ, hãy chuyển **ít nhất một toán hạng** sang `float` hoặc `double` **trước phép chia**. Gán kết quả phép chia nguyên vào biến `double` **không khôi phục** phần thập phân đã bị bỏ.

Với `byte`, `short` và `char`, Java thực hiện *binary numeric promotion*: toán hạng nhỏ được nâng lên `int` nếu không có toán hạng `long`/`float`/`double`. Ví dụ:

~~~java
byte x = 5, y = 2;
var value = x / y; // Kiểu int, giá trị 2.
~~~

Quy tắc kiểu chung của các phép toán số học hai ngôi: có `double` → `double`; nếu không, có `float` → `float`; nếu không, có `long` → `long`; còn lại là `int`.

## 3. Phần dư `%` và số âm

Với số nguyên và số chia khác 0, Java bảo đảm mối quan hệ:

~~~text
a == (a / b) * b + (a % b)
~~~

Phép chia nguyên lấy phần nguyên hướng về 0. **Phần dư mang dấu của số bị chia** (hoặc bằng 0), không phải luôn không âm:

| Biểu thức | Thương `/` | Phần dư `%` |
| --- | ---: | ---: |
| `7 / 3` và `7 % 3` | 2 | 1 |
| `-7 / 3` và `-7 % 3` | -2 | -1 |
| `7 / -3` và `7 % -3` | -2 | 1 |
| `-7 / -3` và `-7 % -3` | 2 | -1 |

Nếu cần **modulo không âm với mẫu số dương**, chẳng hạn chỉ số vòng tròn từ 0 đến `size - 1`, có thể dùng `Math.floorMod(a, positiveSize)`:

~~~java
System.out.println(-7 % 3);           // -1
System.out.println(Math.floorMod(-7, 3)); // 2
~~~

Không nên thay `floorMod` bằng `a % b` mà không xét đầu vào âm. Với toán hạng thực, Java cũng cho phép `%` (ví dụ `7.5 % 2.0` bằng `1.5`); kết quả mang tính **phần dư số thực**, không phải quy tắc modulo luôn không âm.

## 4. Thứ tự ưu tiên và dấu ngoặc

`*`, `/` và `%` có **cùng mức ưu tiên**, cao hơn `+` và `-`. Các toán tử số học hai ngôi trong cùng mức nhóm từ trái sang phải:

~~~java
int first = 2 + 3 * 4;      // 14: 2 + (3 * 4)
int second = (2 + 3) * 4;  // 20
int third = 20 / 5 * 2;    // 8: (20 / 5) * 2
int fourth = 20 / (5 * 2); // 2
~~~

Dấu ngoặc diễn tả rõ cách nhóm. **Độ ưu tiên không đồng nghĩa thứ tự đánh giá toán hạng**: Java đánh giá các toán hạng của phép toán số học thông thường theo thứ tự trái sang phải, ngay cả khi biểu thức được nhóm theo ưu tiên `*`/`/`.

Tránh nhồi nhiều phép tăng/giảm biến hoặc lời gọi có tác dụng phụ vào một biểu thức dài. Tách biến trung gian khi phép tính cần được kiểm toán.

## 5. Chia cho 0, tràn số và độ chính xác

### Số nguyên chia hoặc lấy dư với 0

~~~java
int x = 10;
int zero = 0;
// int q = x / zero; // Ném ArithmeticException lúc chạy.
// int r = x % zero; // Cũng ném ArithmeticException.
~~~

Khi mẫu số nguyên bằng 0, cả `/` và `%` đều gây `ArithmeticException`. Kiểm tra điều kiện mẫu số trước khi tính nếu nó xuất phát từ đầu vào không tin cậy.

### Số thực có cách xử lý 0 khác

~~~java
double zero = 0.0;
double infinity = 1.0 / zero; // Infinity
double notANumber = zero / zero; // NaN
~~~

Các phép này dùng số thực và **không ném `ArithmeticException`**. Nếu ứng dụng chỉ chấp nhận kết quả hữu hạn, sử dụng `Double.isFinite(result)`; đừng coi mọi kết quả `double` đều là một số hữu hạn thông thường.

### Tràn `int` và sai số số thực

~~~java
int overflow = Integer.MAX_VALUE + 1; // -2147483648
long safe = (long) Integer.MAX_VALUE + 1; // 2147483648
~~~

`int` tràn **không tự nâng thành `long`**. Cần đưa một toán hạng lên kiểu rộng **trước phép tính**; với phép cộng nguyên phải chính xác và cần phát hiện tràn, có thể dùng `Math.addExact`.

Số thực nhị phân thường là **xấp xỉ**:

~~~java
double value = 0.1 + 0.2; // In ra 0.30000000000000004.
~~~

Đối với số tiền cần chính xác theo chữ số thập phân, cân nhắc `BigDecimal` tạo từ chuỗi và quy tắc làm tròn rõ ràng. Không tự sửa sai số bằng cách ép về `int` khi cần giữ phần lẻ.

## 6. Chương trình Java 17+ chạy độc lập

Tạo file **ArithmeticOperatorsDemo.java**:

~~~java
public final class ArithmeticOperatorsDemo {
    public static void main(String[] args) {
        int a = 10;
        int b = 3;
        System.out.println("add=" + (a + b));
        System.out.println("subtract=" + (a - b));
        System.out.println("multiply=" + (a * b));
        System.out.println("intDivide=" + (a / b));
        System.out.println("intRemainder=" + (a % b));

        System.out.println("realDivide=" + (7.0 / 2));
        double assignedAfterDivision = 7 / 2;
        System.out.println("assignedAfterDivision="
                + assignedAfterDivision);

        System.out.println("negativeDivide=" + (-7 / 3));
        System.out.println("negativeRemainder=" + (-7 % 3));
        System.out.println("negativeDivisorRemainder=" + (7 % -3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));

        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("floatRemainder=" + (7.5 % 2.0));

        int zero = 0;
        try {
            System.out.println("invalid=" + (a / zero));
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }
        try {
            System.out.println("invalidRemainder=" + (a % zero));
        } catch (ArithmeticException ex) {
            System.out.println("integerRemainderZero=ArithmeticException");
        }

        double realZero = 0.0;
        System.out.println("floatingZero=" + (1.0 / realZero));
        System.out.println("zeroOverZero=" + (realZero / realZero));

        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("widenBeforeAdd="
                + ((long) Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExactOverflow=ArithmeticException");
        }

        System.out.println("decimalApproximation=" + (0.1 + 0.2));
        System.out.println("stringAdd=" + ("sum=" + 10 + 3));
    }
}
~~~

Biên dịch/chạy bằng Bash, PowerShell hoặc Command Prompt tại thư mục chứa file:

~~~bash
javac -encoding UTF-8 ArithmeticOperatorsDemo.java
java ArithmeticOperatorsDemo
~~~

**Expected output chính xác:**

~~~text
add=13
subtract=7
multiply=30
intDivide=3
intRemainder=1
realDivide=3.5
assignedAfterDivision=3.0
negativeDivide=-2
negativeRemainder=-1
negativeDivisorRemainder=1
floorMod=2
precedence=14
parentheses=20
floatRemainder=1.5
integerZero=ArithmeticException
integerRemainderZero=ArithmeticException
floatingZero=Infinity
zeroOverZero=NaN
overflow=-2147483648
widenBeforeAdd=2147483648
addExactOverflow=ArithmeticException
decimalApproximation=0.30000000000000004
stringAdd=sum=103
~~~

**Đọc output:** `intDivide` bỏ phần lẻ; `realDivide` giữ phần lẻ vì có toán hạng `double`; `negativeRemainder` và `floorMod` khác nhau khi số bị chia âm; phép chia nguyên cho 0 ném ngoại lệ, phép chia thực cho 0 có thể ra `Infinity`/`NaN`; `widenBeforeAdd` tránh tràn trước khi tính.

## 7. Khi áp dụng vào bài toán thật

| Tình huống | Cách làm phù hợp |
| --- | --- |
| Tính tổng hoặc tích số nguyên | Chọn `int`/`long` đủ miền; kiểm tra tràn nếu bắt buộc chính xác |
| Tính trung bình hoặc tỉ lệ có phần lẻ | Chuyển toán hạng sang `double` trước `/` |
| Tính thương và số dư số nguyên | Dùng `/` và `%`; ghi rõ chính sách với số âm |
| Tạo chỉ số vòng tròn từ số âm, mẫu số dương | Dùng `Math.floorMod` |
| Mẫu số có thể bằng 0 | Kiểm tra đầu vào trước phép chia/lấy dư |
| Số thực cần hữu hạn | Kiểm tra `Double.isFinite` |
| Tiền tệ theo quy tắc thập phân chính xác | Xem xét `BigDecimal` với scale/rounding tường minh |

**Bài tập 1.** Dự đoán `9 / 4`, `9 % 4` và `9.0 / 4`; giải thích kiểu của mỗi kết quả.

**Bài tập 2.** Tính `-9 / 4`, `-9 % 4` và `Math.floorMod(-9, 4)`. Phân biệt phần dư với modulo không âm.

**Bài tập 3.** Cho `int a = 7, b = 0;`. Viết đoạn kiểm tra để không thực hiện `a / b` khi `b == 0`.

**Bài tập 4.** Vì sao `long result = Integer.MAX_VALUE + 1;` vẫn chứa giá trị âm? Sửa bằng cách chuyển một toán hạng sang `long` trước khi cộng.

**Bài tập 5.** Dự đoán `2 + 3 * 4` và `(2 + 3) * 4`. Giải thích dấu ngoặc thay đổi điều gì.

### Ghi nhớ

**`+`, `-`, `*`, `/`, `%` là năm phép toán số học cơ bản.** Với số nguyên, phép chia bỏ phần lẻ và `%` lấy phần dư có dấu theo số bị chia. Kiểu toán hạng quyết định kiểu phép tính; toán tử ưu tiên và dấu ngoặc quyết định cách nhóm. Hãy xét **0 ở mẫu số, tràn số nguyên và độ chính xác số thực** để tránh kết quả bất ngờ.

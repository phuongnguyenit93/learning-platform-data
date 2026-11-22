# Ép kiểu trước phép chia để nhận kết quả số thực trong Java

> **Java core — language-basics / Số học**  
> **Môi trường:** JDK 17+; ví dụ một file Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Phân biệt phép chia nguyên với phép chia số thực; biết vì sao cần chuyển **toán hạng** sang `double`/`float` **trước dấu chia**, không phải ép kiểu kết quả sau khi phần lẻ đã mất.

## 1. Vì sao `7 / 2` không phải `3.5`?

Khi **hai toán hạng của `/` đều là kiểu số nguyên**, Java thực hiện phép **chia nguyên**, bỏ phần lẻ theo hướng về 0:

~~~java
int a = 7;
int b = 2;
int quotient = a / b; // 3, không phải 3.5.
~~~

Kể cả khi gán vào `double`, phép chia vẫn được thực hiện **trước phép gán**:

~~~java
double misleading = a / b; // 3.0, không phải 3.5.
~~~

Trình tự là: `a / b` có **kiểu `int`**, tính ra `3`; sau đó Java mới mở rộng `int 3` thành `double 3.0` để gán. Kiểu biến đích **không quay ngược lại để đổi phép toán đã xảy ra**.

Với `byte`, `short` hoặc `char`, Java còn nâng toán hạng nhỏ lên `int` qua *binary numeric promotion*, nên `byte / byte` cũng cho kết quả nguyên kiểu `int`.

## 2. Ép kiểu **trước** dấu chia mới giữ được phần lẻ

Muốn `7 / 2` ra `3.5`, hãy đổi **ít nhất một toán hạng** sang kiểu số thực **trước khi toán tử `/` chạy**:

~~~java
int a = 7;
int b = 2;

double r1 = (double) a / b; // 3.5
double r2 = a / (double) b; // 3.5
double r3 = a / 2.0;        // 3.5: literal 2.0 là double.
float  r4 = (float) a / b;  // 3.5f: kiểu biểu thức là float.
~~~

Quy tắc *binary numeric promotion* của toán tử `/` chọn kiểu chung: nếu có toán hạng `double` thì phép chia là `double`; nếu không có `double` nhưng có `float` thì phép chia là `float`; với các toán hạng nguyên, kết quả là `long` nếu có `long`, nếu không là `int`.

**Điểm cốt lõi:** `(double) a / b` biến `a` thành `double` **trước khi chia**. `a / (double) b` tương tự. Chỉ cần một toán hạng là số thực, không cần cast cả hai.

## 3. Ép kiểu **sau** phép chia không khôi phục được phần lẻ

Ba biểu thức trông gần giống nhưng khác kết quả:

| Biểu thức khi `a = 7`, `b = 2` | Kiểu phép chia | Kết quả |
| --- | --- | --- |
| `a / b` | `int` | `3` |
| `double result = a / b;` | `int`, rồi mở rộng khi gán | `3.0` |
| `(double) (a / b)` | `int`, rồi cast kết quả | `3.0` |
| `(double) a / b` | `double` | `3.5` |
| `a / (double) b` | `double` | `3.5` |
| `a / 2.0` | `double` | `3.5` |
| `(float) a / b` | `float` | `3.5f` |

Quan sát vị trí dấu ngoặc:

~~~java
double wrong = (double) (a / b); // Cast sau: 3.0.
double right = ((double) a) / b; // Cast trước: 3.5.
~~~

`(double)(a / b)` không phải “ép kiểu trước phép chia” chỉ vì chữ `(double)` nằm ở đầu dòng: toàn bộ `a / b` nằm **trong ngoặc**, nên bị tính như số nguyên rồi mới cast.

Một bẫy tương tự là thứ tự phép nhân:

~~~java
double wrongAgain = a / b * 1.0; // 3.0: chia nguyên trước.
double rightAgain = a * 1.0 / b; // 3.5: nhân với double trước.
~~~

Dùng `(double) a / b` thường biểu đạt mục đích trực tiếp hơn `a * 1.0 / b`.

## 4. Số âm, `long` và kiểu nguyên nhỏ

Chia nguyên âm vẫn bỏ phần lẻ theo hướng về **0**, không làm tròn xuống âm vô cực:

~~~java
int negative = -7;
System.out.println(negative / 2);           // -3
System.out.println((double) negative / 2);  // -3.5
~~~

Số nguyên `long` cũng là **kiểu nguyên**, nên `9L / 4L` cho **2**, không phải `2.25`:

~~~java
long total = 9L;
long parts = 4L;
double average = (double) total / parts; // 2.25.
~~~

Tương tự:

~~~java
byte small = 5;
byte divisor = 2;
int whole = small / divisor;              // 2 (kiểu int).
double fraction = (double) small / divisor; // 2.5.
~~~

**Lưu ý độ chính xác:** Ép `long` rất lớn sang `double` có thể **làm tròn số nguyên nguồn** trước phép chia (vì `double` chỉ có 53 bit chính xác phần trị). Cast trước giúp tạo kết quả số thực, **không bảo đảm chính xác tuyệt đối** với mọi số lớn.

## 5. Chương trình Java 17+ runnable

Tạo file **CastBeforeDivisionDemo.java**:

~~~java
public final class CastBeforeDivisionDemo {
    public static void main(String[] args) {
        int numerator = 7;
        int denominator = 2;

        System.out.println("integer=" + (numerator / denominator));

        double assigned = numerator / denominator;
        System.out.println("assignedDouble=" + assigned);

        double castAfter = (double) (numerator / denominator);
        double castBeforeLeft = (double) numerator / denominator;
        double castBeforeRight = numerator / (double) denominator;
        double literalDouble = numerator / 2.0;
        float castToFloat = (float) numerator / denominator;

        System.out.println("castAfter=" + castAfter);
        System.out.println("castBeforeLeft=" + castBeforeLeft);
        System.out.println("castBeforeRight=" + castBeforeRight);
        System.out.println("literalDouble=" + literalDouble);
        System.out.println("castToFloat=" + castToFloat);

        System.out.println("multiplyAfter=" +
                (numerator / denominator * 1.0));
        System.out.println("multiplyBefore=" +
                (numerator * 1.0 / denominator));

        int negative = -7;
        System.out.println("negativeInteger=" + (negative / 2));
        System.out.println("negativeReal=" + ((double) negative / 2));

        long big = 9L;
        long four = 4L;
        System.out.println("longInteger=" + (big / four));
        System.out.println("longReal=" + ((double) big / four));

        byte small = 5;
        byte pair = 2;
        System.out.println("byteInteger=" + (small / pair));
        System.out.println("byteReal=" + ((double) small / pair));

        int zero = 0;
        try {
            System.out.println("invalid=" + (numerator / zero));
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }

        System.out.println("floatingZero=" + ((double) numerator / zero));
        System.out.println("zeroOverZero=" + ((double) zero / zero));
        System.out.println("oneThird=" + (1.0 / 3));
    }
}
~~~

Tại thư mục chứa file, chạy bằng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 CastBeforeDivisionDemo.java
java CastBeforeDivisionDemo
~~~

**Expected output chính xác:**

~~~text
integer=3
assignedDouble=3.0
castAfter=3.0
castBeforeLeft=3.5
castBeforeRight=3.5
literalDouble=3.5
castToFloat=3.5
multiplyAfter=3.0
multiplyBefore=3.5
negativeInteger=-3
negativeReal=-3.5
longInteger=2
longReal=2.25
byteInteger=2
byteReal=2.5
integerZero=ArithmeticException
floatingZero=Infinity
zeroOverZero=NaN
oneThird=0.3333333333333333
~~~

Đối chiếu ba dòng quan trọng: `assignedDouble=3.0` và `castAfter=3.0` cho thấy **phần lẻ đã bị loại bỏ trong phép chia nguyên**; `castBeforeLeft=3.5` cho thấy ép kiểu toán hạng trước dấu `/` đã tạo phép chia số thực.

## 6. Mẫu số bằng 0 và giới hạn của `double`

- Với `int`/`long`, chia hoặc lấy dư cho **0** ném `ArithmeticException`. Phải kiểm tra mẫu số nguyên nếu nó có thể bằng 0.
- Với `double`/`float`, phép chia cho **0.0** tuân theo số thực IEEE 754: `7.0 / 0.0` cho `Infinity`, `0.0 / 0.0` cho `NaN`, không ném `ArithmeticException`.
- Nếu hợp đồng yêu cầu giá trị hữu hạn, kiểm tra `Double.isFinite(value)` và quyết định cách xử lý mẫu số 0 theo nghiệp vụ **trước phép chia**.
- `double` có thể biểu diễn **xấp xỉ** kết quả như `1.0 / 3`, không phải mọi phân số đều chính xác trong hệ nhị phân. Dùng `BigDecimal` kèm `RoundingMode` hoặc `MathContext` khi cần quy tắc độ chính xác thập phân rõ ràng.

Ví dụ có guard thay vì chấp nhận `Infinity`:

~~~java
static double ratio(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return (double) numerator / denominator;
}
~~~

Hàm có kết quả số thực khi mẫu số hợp lệ, nhưng vẫn buộc người gọi xử lý điều kiện chia cho 0 một cách có chủ đích.

## 7. Lỗi thường gặp và bài tập

| Sai lầm | Cách sửa |
| --- | --- |
| `double result = a / b;` khi a, b là `int` | `double result = (double) a / b;` |
| `(double) (a / b)` rồi kỳ vọng có phần lẻ | Cast một toán hạng **trước dấu chia** |
| `a / b * 1.0` và nghĩ phép chia sẽ là số thực | Đưa `1.0` vào trước phép chia hoặc dùng cast |
| Nghĩ `long / long` tự ra `double` | `long` vẫn là số nguyên; phải cast một toán hạng |
| Nghĩ cast bảo đảm chính xác mọi số nguyên lớn | `double` vẫn có giới hạn độ chính xác |
| Nghĩ phép chia số thực cho 0 ném `ArithmeticException` | Số thực có thể ra `Infinity`/`NaN`; cần kiểm tra riêng |

**Bài 1.** Cho `int a = 9, b = 4;`. Dự đoán `a / b`, `(double) (a / b)` và `(double) a / b`.

**Bài 2.** Giải thích vì sao `double d = 7 / 2;` cho 3.0 mà `double d = 7 / 2.0;` cho 3.5.

**Bài 3.** Cho `int a = -9, b = 4;`. So sánh chia nguyên `a / b` với `(double) a / b`.

**Bài 4.** Viết hàm tính trung bình từ `int sum` và `int count`, yêu cầu trả `double` và từ chối `count == 0`. Không dùng `(double) (sum / count)`.

**Bài 5.** Cho `long a = 9L, b = 4L;`. Tại sao `double x = a / b;` ra 2.0? Sửa để ra 2.25.

### Ghi nhớ

Muốn phép chia hai số nguyên có kết quả số thực, hãy **ép ít nhất một toán hạng sang `double`/`float` trước toán tử `/`**: `(double) a / b` hoặc `a / (double) b`. Ép kiểu **sau** như `(double) (a / b)` chỉ chuyển kết quả nguyên đã mất phần lẻ thành số thực. Luôn xét mẫu số 0 và độ chính xác số thực khi áp dụng vào chương trình thật.

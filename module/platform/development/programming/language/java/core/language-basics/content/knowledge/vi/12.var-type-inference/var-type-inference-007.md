# Kiểu suy ra từ literal và các phép tính số với `var` trong Java

> **Java core — language-basics / Suy luận với var**  
> **Môi trường:** JDK 17+; một tệp Java độc lập, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Dự đoán chính xác **kiểu tĩnh** được suy ra cho `var` từ literal, phép toán số học, phép ép kiểu và biểu thức điều kiện; tránh lỗi chia nguyên, tràn số trước khi mở rộng và hiểu nhầm rằng `var` tự chọn kiểu nhỏ nhất.

## 1. `var` lấy kiểu của biểu thức, không đoán theo giá trị

Khi khai báo biến cục bộ bằng `var`, trình biên dịch suy luận kiểu từ **biểu thức khởi tạo tại thời điểm biên dịch**:

~~~java
var count = 10;     // int, không phải byte dù 10 rất nhỏ.
var distance = 10L; // long.
var ratio = 2.5;    // double.
var precise = 2.5f; // float.
var symbol = 'A';   // char.
~~~

`var` **không phải kiểu động**. Sau `var count = 10;`, biến `count` có kiểu `int` cố định; `count = 2.5;` không biên dịch vì không thể ngầm chuyển `double` sang `int`.

**Quy tắc thực hành:** Muốn dự đoán `var result = expression;`, trước tiên hãy xác định **kiểu của `expression` theo các quy tắc Java**. Kiểu suy ra chính là kiểu biểu thức đó.

## 2. Kiểu mặc định của literal số

| Literal | Kiểu của literal | Ghi chú |
| --- | --- | --- |
| `10`, `1_000`, `0xFF`, `0b1010` | `int` | Literal số nguyên không hậu tố mặc định là `int` nếu hợp lệ |
| `10L`, `10l` | `long` | Nên viết `L` hoa tránh nhầm `l` với chữ số 1 |
| `2.5`, `2.5d`, `1e3` | `double` | Literal số thực mặc định là `double` |
| `2.5f`, `2.5F` | `float` | Cần hậu tố `f` hoặc `F` để literal là `float` |
| `'A'` | `char` | Literal ký tự không phải `String` hay `int` |
| `(byte) 10`, `(short) 10` | `byte`, `short` | Cast quyết định kiểu của biểu thức khởi tạo |

~~~java
var a = 1_000;        // int.
var b = 1_000L;       // long.
var c = 1e3;          // double (giá trị 1000.0).
var d = 1e3f;         // float.
var e = (byte) 10;    // byte.
~~~

Đừng nhầm **kiểu** với **cách in** hoặc độ lớn giá trị: `1000` và `1000L` có cùng giá trị toán học nhưng khác kiểu. Literal thập phân nguyên lớn ngoài phạm vi `int` cần hậu tố thích hợp như `2147483648L`; viết `var n = 2147483648;` không khiến Java tự đoán thành `long`.

## 3. Phép tính quyết định kiểu của `var` trước khi gán

Với phép toán số học hai ngôi như `+`, `-`, `*`, `/`, `%`, Java áp dụng **binary numeric promotion** cho toán hạng trước khi tính:

1. Có `double` → kết quả kiểu `double`.
2. Nếu không, có `float` → kết quả kiểu `float`.
3. Nếu không, có `long` → kết quả kiểu `long`.
4. Còn lại → kết quả kiểu `int` (kể cả toán hạng `byte`, `short`, `char`).

| Biểu thức khởi tạo | Kiểu suy ra với `var` | Kết quả ví dụ |
| --- | --- | --- |
| `2 + 3` | `int` | `5` |
| `2 + 3L` | `long` | `5` |
| `2 + 3.5f` | `float` | `5.5` |
| `2L + 3.5` | `double` | `5.5` |
| `(byte) 10 + (short) 20` | `int` | `30` |
| `'A' + 1` | `int` | `66` |
| `7 / 2` | `int` | `3` |
| `7 / 2.0` | `double` | `3.5` |

Ví dụ:

~~~java
var sum = (byte) 10 + (short) 20; // int, không phải byte/short.
var afterChar = 'A' + 1;          // int, không phải char.
var mixed = 2 + 3L;               // long.
~~~

`var` không phải nguyên nhân khiến `byte + short` trở thành `int`: **chính quy tắc toán tử** quyết định kiểu đó. `var` chỉ dùng lại kiểu đã được xác định.

## 4. Bẫy chia số nguyên

~~~java
var whole = 7 / 2;       // int: 3, không phải 3.5.
var fraction = 7 / 2.0;  // double: 3.5.
var byCast = (double) 7 / 2; // double: 3.5.
~~~

Khi cả hai toán hạng của `/` là các kiểu số nguyên, Java thực hiện phép chia nguyên, bỏ phần lẻ theo hướng về 0. Khai báo `double result = 7 / 2;` vẫn cho **3.0**: phép chia nguyên **đã xảy ra trước** khi kết quả được chuyển thành `double` để gán.

Muốn chia số thực, đưa **ít nhất một toán hạng** sang kiểu số thực **trước dấu chia**, bằng literal `2.0` hoặc cast `(double) 7`.

Không dùng mẹo `var` để kỳ vọng Java tự tìm kiểu “đủ giữ phần lẻ”: `var` giữ đúng kiểu biểu thức, không sửa phép tính.

## 5. Bẫy tràn số trước khi mở rộng

Ngay cả khi biến đích là `long`, phép tính bằng `int` có thể tràn **trước lúc gán**:

~~~java
var overflow = Integer.MAX_VALUE + 1;    // int: -2147483648.
var exact = (long) Integer.MAX_VALUE + 1; // long: 2147483648.
var lateCast = (long) (Integer.MAX_VALUE + 1); // long: -2147483648.
~~~

- `Integer.MAX_VALUE + 1`: hai toán hạng đều `int`, phép cộng kiểu `int` bị tràn rồi `var` suy ra `int`.
- `(long) Integer.MAX_VALUE + 1`: cast làm **toán hạng** đầu thành `long` trước phép cộng; kết quả kiểu `long` không tràn.
- `(long) (Integer.MAX_VALUE + 1)`: phép cộng đã tràn trong ngoặc, sau đó mới cast giá trị sai sang `long`.

**Ghi nhớ:** Nếu cần kiểu rộng, làm một toán hạng rộng lên **trước phép tính**, không chỉ chuyển kết quả đã tính.

## 6. Biểu thức điều kiện và phép ép kiểu

Kiểu của phép ba ngôi `condition ? a : b` phụ thuộc quy tắc chọn kiểu của hai nhánh:

~~~java
var mixedConditional = true ? 1 : 2.0; // double, giá trị 1.0.
var castFirst = (float) 3;             // float, giá trị 3.0f.
~~~

Trong ví dụ đầu, hai nhánh `int` và `double` làm biểu thức có kiểu `double`, dù điều kiện luôn chọn nhánh `1`. `var` suy ra `double` **từ kiểu của biểu thức**, không suy từ nhánh được chạy.

**Lưu ý:** Java có quy tắc bổ sung cho biểu thức điều kiện số học (đặc biệt với literal hằng/kiểu nhỏ), nên không được áp dụng máy móc bảng phép cộng cho **mọi** dấu `?:`. Với biểu thức phức tạp, hãy xét quy tắc kiểu riêng của `?:` hoặc viết kiểu/cast tường minh nếu tính chính xác quan trọng.

## 7. Chương trình Java 17+ chạy được

Tạo tệp **VarNumericInferenceDemo.java**:

~~~java
public final class VarNumericInferenceDemo {
    private static String kind(byte x)   { return "byte"; }
    private static String kind(short x)  { return "short"; }
    private static String kind(char x)   { return "char"; }
    private static String kind(int x)    { return "int"; }
    private static String kind(long x)   { return "long"; }
    private static String kind(float x)  { return "float"; }
    private static String kind(double x) { return "double"; }

    public static void main(String[] args) {
        var integer = 12;
        var bigInteger = 12L;
        var singlePrecision = 1.25f;
        var doublePrecision = 1.25;
        var letter = 'A';

        System.out.println("literals=" + kind(integer)
                + "," + kind(bigInteger)
                + "," + kind(singlePrecision)
                + "," + kind(doublePrecision)
                + "," + kind(letter));

        var bytes = (byte) 10 + (short) 20;
        var afterChar = 'A' + 1;
        var longSum = 2 + 3L;
        var floatSum = 2 + 3.5f;
        var doubleSum = 2L + 3.5;

        System.out.println("smallSum=" + bytes + ":" + kind(bytes));
        System.out.println("charSum=" + afterChar + ":" + kind(afterChar));
        System.out.println("mixedKinds=" + kind(longSum)
                + "," + kind(floatSum) + "," + kind(doubleSum));

        var integerDivision = 7 / 2;
        var realDivision = 7 / 2.0;
        System.out.println("division=" + integerDivision
                + ":" + kind(integerDivision) + ","
                + realDivision + ":" + kind(realDivision));

        var overflow = Integer.MAX_VALUE + 1;
        var exact = (long) Integer.MAX_VALUE + 1;
        var lateCast = (long) (Integer.MAX_VALUE + 1);
        System.out.println("overflow=" + overflow + ":"
                + kind(overflow));
        System.out.println("exact=" + exact + ":" + kind(exact));
        System.out.println("lateCast=" + lateCast + ":" + kind(lateCast));

        var conditional = true ? 1 : 2.0;
        var narrow = (byte) 10;
        System.out.println("conditional=" + conditional + ":"
                + kind(conditional));
        System.out.println("explicitCast=" + narrow + ":"
                + kind(narrow));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 VarNumericInferenceDemo.java
java VarNumericInferenceDemo
~~~

**Expected output chính xác:**

~~~text
literals=int,long,float,double,char
smallSum=30:int
charSum=66:int
mixedKinds=long,float,double
division=3:int,3.5:double
overflow=-2147483648:int
exact=2147483648:long
lateCast=-2147483648:long
conditional=1.0:double
explicitCast=10:byte
~~~

Các overload `kind(...)` giúp chương trình in **kiểu mà trình biên dịch chọn**, không suy luận kiểu qua `toString()` hay cách in số. Từ output có thể kiểm tra riêng kiểu biểu thức và giá trị thực tế.

## 8. Thói quen tốt và bài tập

| Điều cần quyết định | Gợi ý |
| --- | --- |
| Muốn `long` ngay từ literal | Viết hậu tố `L`, ví dụ `var n = 10L;` |
| Muốn `float` ngay từ literal | Dùng `f`/`F`, ví dụ `var f = 1.5f;` |
| Muốn phép chia có phần lẻ | Đổi toán hạng sang `double` trước phép chia |
| Muốn tổng không tràn `int` | Đưa toán hạng lên `long` trước phép cộng/nhân |
| Kiểu suy ra khó nhìn từ initializer | Dùng kiểu khai báo rõ ràng hoặc cast có chủ đích |
| So sánh các kết quả số thực | Xem xét độ chính xác và quy tắc làm tròn, đừng chỉ dựa vào hình thức literal |

**Bài 1.** Dự đoán kiểu của `var a = 7;`, `var b = 7L;`, `var c = 7f;` và `var d = 7.0;`. Mỗi biến có giá trị số học giống nhau không? Kiểu có giống nhau không?

**Bài 2.** Cho `var a = (byte) 5 + (short) 6;`. Kiểu của `a` là gì và vì sao không phải `byte`/`short`?

**Bài 3.** Tính `var quotient = 9 / 4;` và `var preciseQuotient = 9.0 / 4;`. Hai biến có kiểu và giá trị thế nào?

**Bài 4.** So sánh `var a = Integer.MAX_VALUE + 1;`, `var b = (long) Integer.MAX_VALUE + 1;` và `var c = (long) (Integer.MAX_VALUE + 1);`. Hãy chỉ rõ chỗ tràn xảy ra.

**Bài 5.** Cho `var result = false ? 1 : 2.0;`. Kiểu của `result` là gì? Có phụ thuộc nhánh nào chạy không?

### Ghi nhớ

**`var` không thay đổi luật tính số của Java: nó chỉ suy ra kiểu tĩnh từ biểu thức khởi tạo.** Literal mặc định `int` hoặc `double` nếu không có hậu tố; phép toán áp dụng numeric promotion; chia nguyên và tràn số xảy ra **trước khi** giá trị được gán. Khi cần chính xác, hãy chọn literal, cast và toán hạng đúng **trước phép tính**, thay vì trông chờ `var` tự chọn kiểu phù hợp.

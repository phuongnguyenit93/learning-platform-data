# Thực hành: Viết bảng kiểm chứng kiểu kết quả của các biểu thức số trong Java

## 1. Mục tiêu thực hành

Khi đọc một biểu thức Java như `byte + short`, `int / int`, `long + float` hoặc `1 << 33`, ta cần trả lời **hai câu hỏi khác nhau**:

1. **Kiểu của biểu thức tại thời điểm biên dịch (*compile-time type*) là gì?**
2. **Giá trị khi chạy (*runtime value*) là bao nhiêu**, và có khả năng mất dữ liệu, làm tròn hoặc tràn số không?

Java không tự động giữ kiểu nhỏ nhất của các toán hạng. Nhiều phép toán trên `byte`, `short` hoặc `char` tạo kết quả `int`. Một phép chia số nguyên không bỗng trở thành số thực vì kết quả toán học có phần dư. Phép cộng có `float` và `long` có thể cho ra `float`, dù `long` chứa nhiều chữ số hơn. Việc hiểu chính xác **quy tắc suy ra kiểu** sẽ giúp bạn tránh lỗi biên dịch, chọn phép ép kiểu hợp lý và phát hiện bug số học.

Bài thực hành này có:

- Quy trình lập bảng kiểm chứng theo từng biểu thức.
- Bảng tham chiếu các quy tắc numeric promotion và ngoại lệ thường gặp.
- Chương trình **Java 17+ chạy độc lập**, trong đó mỗi kết quả được gán cho biến có **kiểu khai báo tường minh**, để trình biên dịch kiểm chứng.
- Các biểu thức **không biên dịch**, phân tích lý do và cách sửa.
- Bài tập tự điền bảng, kèm đáp án về cả kiểu lẫn giá trị.

## 2. Định nghĩa bảng kiểm chứng

Một bảng hữu ích cần ít nhất các cột:

| Biểu thức | Kiểu toán hạng | Quy tắc áp dụng | Kiểu kết quả | Giá trị khi chạy / lưu ý |
| --- | --- | --- | --- | --- |
| `a + b` | `byte` + `short` | Binary numeric promotion | `int` | Tùy giá trị `a`, `b` |
| `a / b` | `int` / `int` | Chia nguyên | `int` | Bỏ phần lẻ theo hướng về 0 |
| `a + b` | `long` + `float` | Binary numeric promotion | `float` | Có thể mất chính xác khi chuyển `long` sang `float` |

Không suy ra kiểu từ cách `System.out.println` hiển thị. Ví dụ giá trị in ra `3` có thể đến từ `byte`, `int`, `long`, `float` hoặc `double` (với dạng hiển thị khác nhau ở một số trường hợp). Hãy dựa vào **cú pháp biểu thức và quy tắc kiểu**; kết quả runtime chỉ là bước kiểm chứng bổ sung.

Với `var`, Java cũng xác định một kiểu cụ thể lúc biên dịch. `var` không phải kiểu số động, và không khiến kết quả chọn kiểu dựa theo độ lớn giá trị lúc chạy.

## 3. Quy tắc số 1: kiểu của literal và biến

| Cú pháp | Kiểu | Giải thích |
| --- | --- | --- |
| `123` | `int` | Literal nguyên không hậu tố mặc định là `int` nếu hợp lệ |
| `123L` | `long` | Hậu tố `L` hoặc `l`; ưu tiên `L` để dễ đọc |
| `1.5` | `double` | Literal có dấu thập phân mặc định là `double` |
| `1.5f` | `float` | Hậu tố `f` hoặc `F` |
| `1.5d` | `double` | Hậu tố `d` hoặc `D` |
| `1e3` | `double` | Ký pháp số mũ của literal floating point |
| `'A'` | `char` | Literal ký tự; giá trị số Unicode code unit của `'A'` là 65 |
| `true` | `boolean` | Không phải kiểu số |
| `"123"` | `String` | Chuỗi, không phải số |

Dấu `-` ở `-123` là **toán tử một ngôi** áp dụng lên literal, không phải là một phần của literal nguyên thông thường. Hai giá trị đặc biệt `-2147483648` và `-9223372036854775808L` được ngôn ngữ hỗ trợ theo quy tắc về literal thập phân và unary minus; không suy luận rằng mọi số nguyên ngoài miền đều hợp lệ.

Ví dụ:

~~~java
int whole = 12;
long large = 12L;
float measure = 12.5f;
double ratio = 12.5;

var inferredWhole = 10 / 4;  // int, giá trị 2
var inferredRatio = 10 / 4.0; // double, giá trị 2.5
~~~

`var` được suy ra **`int`** và **`double`** ở hai câu lệnh cuối. Không có phép chuyển đổi tự động theo giá trị kết quả.

## 4. Quy tắc số 2: binary numeric promotion

Đối với các toán tử số học nhị phân thường gặp như `+`, `-`, `*`, `/` và `%`, Java dùng *binary numeric promotion*. Sau unboxing (nếu cần), quy tắc khái quát là:

1. Nếu có toán hạng `double` → kết quả thuộc kiểu `double`.
2. Nếu không có `double` nhưng có `float` → kết quả thuộc kiểu `float`.
3. Nếu không có hai kiểu trên nhưng có `long` → kết quả thuộc kiểu `long`.
4. Nếu còn lại các kiểu nguyên nhỏ, kết quả thuộc kiểu **`int`**.

| Toán hạng trái | Toán hạng phải | Kiểu của `left + right` |
| --- | --- | --- |
| `byte` | `byte` | `int` |
| `byte` | `short` | `int` |
| `char` | `int` | `int` |
| `int` | `int` | `int` |
| `int` | `long` | `long` |
| `long` | `float` | `float` |
| `float` | `double` | `double` |
| `long` | `double` | `double` |

Một chỗ dễ nhầm: **`long + float` trả `float`**, không phải `long` và cũng không nhất thiết là `double`. `float` là floating point 32-bit, có thể không giữ được tất cả chữ số của một `long` lớn. Kiểu kết quả do **quy tắc promotion**, không do việc kiểu nào “chứa nhiều số hơn”.

Đối với `byte`, `short`, `char`, kết quả cộng thường là `int`:

~~~java
byte b = 10;
short s = 20;
char c = 'A';

int sum = b + s;    // int, giá trị 30
int next = c + 1;   // int, giá trị 66
~~~

Câu lệnh `byte bad = b + s;` không biên dịch nếu không có cast: kết quả là `int`, không thể gán ngầm vào `byte`.

## 5. Quy tắc số 3: unary promotion, bitwise và shift

Các toán tử một ngôi `+`, `-`, `~` thực hiện **unary numeric promotion**. Với `byte`, `short` hoặc `char`, toán hạng được nâng thành `int`:

~~~java
byte b = 10;

int positive = +b; // 10
int negative = -b; // -10
int bits = ~b;     // -11
~~~

Toán tử shift (`<<`, `>>`, `>>>`) không sử dụng binary numeric promotion như phép cộng. Nó nâng kiểu từng toán hạng theo quy tắc riêng; **kiểu kết quả bằng kiểu toán hạng trái sau unary promotion**:

| Biểu thức | Kiểu kết quả | Giá trị |
| --- | --- | --- |
| `(byte) 3 << 1` | `int` | `6` |
| `1 << 3` | `int` | `8` |
| `1L << 3` | `long` | `8` |
| `1 << 33` | `int` | `2` |
| `1L << 33` | `long` | `8589934592` |
| `~(short) 0` | `int` | `-1` |

Với kiểu `int`, Java chỉ sử dụng **5 bit thấp** của khoảng dịch; vì thế `1 << 33` tương đương `1 << 1`, kết quả là `2`. Với kiểu `long`, dùng **6 bit thấp** của khoảng dịch, nên `1L << 33` là `8589934592`.

Đừng suy ra kiểu shift bằng kiểu toán hạng phải: `1 << 3L` vẫn có kiểu `int` vì toán hạng trái là `int`. Tuy nhiên, tốt nhất chỉ dùng khoảng dịch hợp lệ với thiết kế nghiệp vụ, không dựa vào việc Java bỏ qua các bit cao để làm *validation*.

## 6. Quy tắc số 4: phép chia nguyên và cách tạo số thực

| Biểu thức | Kiểu | Kết quả |
| --- | --- | --- |
| `7 / 2` | `int` | `3` |
| `-7 / 2` | `int` | `-3` |
| `7L / 2` | `long` | `3` |
| `7 / 2.0` | `double` | `3.5` |
| `7 / 2.0f` | `float` | `3.5` |
| `(double) 7 / 2` | `double` | `3.5` |
| `(double) (7 / 2)` | `double` | `3.0` |

Điểm khác biệt ở hai dòng cuối là **thứ tự đánh giá**:

~~~java
int numerator = 7;
int denominator = 2;

double right = (double) numerator / denominator; // 3.5
double tooLate = (double) (numerator / denominator); // 3.0
~~~

Ở `tooLate`, `numerator / denominator` đã chia nguyên và ra 3 **trước khi cast**. Phép cast từ `3` thành `double` chỉ tạo `3.0`, không phục hồi phần dư.

Phép chia nguyên cho 0 ném `ArithmeticException` tại runtime. Phép chia floating point cho 0 có thể trả vô cực hoặc `NaN` theo ngữ nghĩa floating point; đừng coi hai trường hợp như nhau.

## 7. Quy tắc số 5: so sánh, điều kiện và toán tử ba ngôi

Toán tử so sánh số học như `<`, `<=`, `>`, `>=` và `==` áp dụng các quy tắc chuyển đổi toán hạng cần thiết, nhưng **kiểu kết quả là `boolean`**.

~~~java
int i = 7;
long l = 9L;
boolean smaller = i < l;  // true
boolean equal = i == l;   // false
~~~

Toán tử điều kiện `condition ? left : right` có nhiều quy tắc, **không phải lúc nào cũng áp dụng máy móc bảng binary numeric promotion**.

| Biểu thức | Kiểu kết quả | Vì sao |
| --- | --- | --- |
| `true ? 7 : 0.5` | `double` | Hai nhánh có `int` và `double` |
| `true ? 7 : 9L` | `long` | Hai nhánh có `int` và `long` |
| `true ? (byte) 1 : 2` | `byte` | Quy tắc đặc biệt: literal `int` 2 là constant expression biểu diễn được trong `byte` |
| `true ? 1 : 2.0f` | `float` | Hai nhánh có `int` và `float` |

Quy tắc nhánh `byte` và literal `int` có thể khiến kết quả trở thành `byte`, không phải `int`; đây là lý do cần học quy tắc riêng cho conditional expression thay vì áp dụng bảng promotion của `+`.

Cũng phải phân biệt **kiểu của biểu thức** với **nhánh được đánh giá**: `condition` quyết định nhánh chạy, nhưng kiểu biểu thức được xác định ngay khi biên dịch từ kiểu hai nhánh và quy tắc của `?:`.

## 8. Ngoại lệ quan trọng: assignment, compound assignment, ++ và --

Bản thân phép gán có kiểu tương ứng với kiểu biến bên trái nếu hợp lệ. Một số cú pháp còn có **narrowing conversion ngầm** mà phép cộng bình thường không có.

~~~java
byte b = 127;
b += 1; // Biên dịch; b trở thành -128 (overflow kiểu byte).
~~~

Đối với phép gán hợp thành, `b += 1` có ngữ nghĩa tương tự `b = (byte) (b + 1)`, ngoại trừ vế trái chỉ được đánh giá một lần. Vì thế:

~~~java
byte b = 100;

// byte wrong = b + 1; // Không biên dịch: b + 1 là int.
b += 1;                // Biên dịch, giá trị b là 101.
b++;                   // Biên dịch, tăng b thêm 1.
~~~

Tương tự, với một biến `byte`, biểu thức `b++` có **kiểu `byte`** (kết quả hậu tố là giá trị cũ) dù phép cộng số học trung gian được thực hiện theo quy tắc nâng kiểu.

| Cú pháp | Kiểu của biểu thức / hành vi |
| --- | --- |
| `b + 1` với `b` là `byte` | `int` |
| `b += 1` với `b` là `byte` | Phép gán hợp thành hợp lệ, kết quả có kiểu `byte` |
| `b++` với `b` là `byte` | Kiểu `byte`, trả giá trị cũ rồi cập nhật |
| `++b` với `b` là `byte` | Kiểu `byte`, trả giá trị mới |
| `byte k = 1 + 2;` | Có thể biên dịch nhờ constant expression bằng 3 nằm trong miền `byte` |
| `byte k = b + 2;` | Không biên dịch vì `b` là biến, biểu thức có kiểu `int` |

Không nên nghĩ `b += 1` kiểm tra tràn. Khi chạy quá `Byte.MAX_VALUE`, kết quả có thể wrap. Nếu nghiệp vụ yêu cầu phát hiện tràn, thiết kế kiểm tra/biểu diễn rộng hơn trước khi thu hẹp kiểu.

## 9. Autoboxing, unboxing và kiểu đối tượng số

Java có các wrapper class như `Integer`, `Long`, `Float` và `Double`. Với toán tử số học, wrapper có thể bị **unbox** thành primitive trước khi promotion:

~~~java
Integer boxed = 5;
int result = boxed + 1; // int, giá trị 6
~~~

**Không** kết luận `Integer + int` tạo ra `Integer`; biểu thức cộng có kiểu `int`. Nếu một wrapper bằng `null`, biểu thức cần unboxing có thể ném `NullPointerException`:

~~~java
Integer missing = null;
try {
    int result = missing + 1;
    System.out.println(result);
} catch (NullPointerException ex) {
    System.out.println("null unboxing");
}
~~~

Chuỗi `String` là trường hợp khác: toán tử `+` nối chuỗi khi một toán hạng được dùng trong string concatenation.

~~~java
String message = "count=" + 7; // "count=7", kiểu String
~~~

Không dùng toán tử `+` trực tiếp giữa hai `BigDecimal` hoặc hai `BigInteger`. Đây là **đối tượng**, không phải primitive numeric:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

BigDecimal decimal = new BigDecimal("0.1")
        .add(new BigDecimal("0.2")); // BigDecimal, đúng 0.3

BigInteger integer = BigInteger.ONE.add(
        BigInteger.valueOf(2)
); // BigInteger, giá trị 3
~~~

Kiểu của lời gọi `decimal.add(...)` do **chữ ký method** quyết định; không áp dụng binary numeric promotion cho hai object đó.

## 10. Bảng kiểm chứng hoàn chỉnh: kiểu + giá trị cụ thể

Giả định các biến ban đầu:

~~~java
byte b = 10;
short s = 20;
char c = 'A';
int i = 7;
long l = 9L;
float f = 2.5f;
double d = 0.5;
Integer boxed = 5;
~~~

Bảng điền sẵn:

| Biểu thức | Kiểu kết quả | Giá trị | Lý do ngắn |
| --- | --- | --- | --- |
| `b + s` | `int` | `30` | `byte` và `short` nâng lên `int` |
| `c + 1` | `int` | `66` | `char` nâng lên `int` |
| `i + l` | `long` | `16` | Có `long` |
| `l + f` | `float` | `11.5` | Có `float`, không có `double` |
| `f + d` | `double` | `3.0` | Có `double` |
| `-b` | `int` | `-10` | Unary numeric promotion |
| `~b` | `int` | `-11` | Bitwise complement của `int` 10 |
| `b << 1` | `int` | `20` | Shift dùng kiểu toán hạng trái sau promotion |
| `1 << 33` | `int` | `2` | Khoảng shift `int` chỉ xét 5 bit thấp |
| `1L << 33` | `long` | `8589934592` | Toán hạng trái là `long` |
| `i / 2` | `int` | `3` | Chia nguyên |
| `i / 2.0` | `double` | `3.5` | Có `double` |
| `i < l` | `boolean` | `true` | So sánh |
| `true ? i : d` | `double` | `7.0` | Hai nhánh `int` và `double` |
| `true ? (byte) 1 : 2` | `byte` | `1` | Trường hợp đặc biệt của `?:` |
| `Math.round(2.6f)` | `int` | `3` | Overload nhận `float` trả `int` |
| `Math.round(2.6d)` | `long` | `3` | Overload nhận `double` trả `long` |
| `"n=" + i` | `String` | `n=7` | Nối chuỗi |
| `boxed + 1` | `int` | `6` | Unboxing rồi cộng |
| `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `BigDecimal` | `0.3` | Method `add` trả `BigDecimal` |

Giá trị và kiểu được xác định bằng ngữ nghĩa Java, không phải vì bảng liệt kê trùng tên wrapper. Phần kế tiếp có chương trình **biên dịch được**, dùng biến khai báo tường minh để buộc compiler kiểm chứng các kiểu trên.

## 11. Chương trình Java 17+ chạy độc lập để xác nhận bảng

Tạo file `NumericExpressionTypeTable.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericExpressionTypeTable {
    static void row(String expression, String resultType, Object value) {
        System.out.println(expression + " | " + resultType + " | " + value);
    }

    public static void main(String[] args) {
        byte b = 10;
        short s = 20;
        char c = 'A';
        int i = 7;
        long l = 9L;
        float f = 2.5f;
        double d = 0.5;
        Integer boxed = 5;

        // Kiểu được kiểm tra thực sự khi javac gán kết quả cho biến.
        int sumSmall = b + s;
        int sumChar = c + 1;
        long sumLong = i + l;
        float sumFloat = l + f;
        double sumDouble = f + d;
        int unaryMinus = -b;
        int bitComplement = ~b;
        int shifted = b << 1;
        int maskedShift = 1 << 33;
        long longShift = 1L << 33;
        int integerDivision = i / 2;
        double realDivision = i / 2.0;
        boolean compare = i < l;
        double conditional = true ? i : d;
        byte specialConditional = true ? (byte) 1 : 2;
        int roundedFloat = Math.round(2.6f);
        long roundedDouble = Math.round(2.6d);
        String concatenated = "n=" + i;
        int unboxed = boxed + 1;
        BigDecimal exactDecimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        BigInteger exactInteger = BigInteger.ONE
                .add(BigInteger.valueOf(2));

        row("b + s", "int", sumSmall);
        row("c + 1", "int", sumChar);
        row("i + l", "long", sumLong);
        row("l + f", "float", sumFloat);
        row("f + d", "double", sumDouble);
        row("-b", "int", unaryMinus);
        row("~b", "int", bitComplement);
        row("b << 1", "int", shifted);
        row("1 << 33", "int", maskedShift);
        row("1L << 33", "long", longShift);
        row("i / 2", "int", integerDivision);
        row("i / 2.0", "double", realDivision);
        row("i < l", "boolean", compare);
        row("true ? i : d", "double", conditional);
        row("true ? (byte) 1 : 2", "byte", specialConditional);
        row("Math.round(2.6f)", "int", roundedFloat);
        row("Math.round(2.6d)", "long", roundedDouble);
        row("\"n=\" + i", "String", concatenated);
        row("boxed + 1", "int", unboxed);
        row("BigDecimal.add", "BigDecimal", exactDecimal);
        row("BigInteger.add", "BigInteger", exactInteger);

        byte nearLimit = 127;
        byte before = nearLimit++;
        row("nearLimit++ (old)", "byte", before);
        row("nearLimit (new)", "byte", nearLimit);
    }
}
~~~

Chạy:

~~~bash
javac NumericExpressionTypeTable.java
java NumericExpressionTypeTable
~~~

Stdout:

~~~text
b + s | int | 30
c + 1 | int | 66
i + l | long | 16
l + f | float | 11.5
f + d | double | 3.0
-b | int | -10
~b | int | -11
b << 1 | int | 20
1 << 33 | int | 2
1L << 33 | long | 8589934592
i / 2 | int | 3
i / 2.0 | double | 3.5
i < l | boolean | true
true ? i : d | double | 7.0
true ? (byte) 1 : 2 | byte | 1
Math.round(2.6f) | int | 3
Math.round(2.6d) | long | 3
"n=" + i | String | n=7
boxed + 1 | int | 6
BigDecimal.add | BigDecimal | 0.3
BigInteger.add | BigInteger | 3
nearLimit++ (old) | byte | 127
nearLimit (new) | byte | -128
~~~

### Tại sao chương trình kiểm chứng được kiểu?

Mỗi biến có kiểu tường minh như `long sumLong = i + l;`, `float sumFloat = l + f;` hoặc `byte specialConditional = true ? (byte) 1 : 2;`. Trình biên dịch bảo đảm **kết quả có thể gán** cho kiểu khai báo đó, còn quy tắc biểu thức xác định kiểu thật sự. Để phân biệt kiểu biểu thức với những chuyển đổi gán ngầm được phép (`int` sang `long` chẳng hạn), cần tiếp tục phân tích theo quy tắc trong các mục 3–9, không chỉ dựa trên việc lệnh gán biên dịch thành công.

Việc truyền biến primitive vào tham số `Object value` của `row` khiến nó được **boxing** để in. Vì vậy, nếu đổi hàm sang in `value.getClass()`, bạn đang xem **lớp wrapper sau boxing**, không phải cơ chế suy ra kiểu primitive gốc. Cột kiểu ở đây được viết tường minh theo phân tích compile-time.

## 12. Các trường hợp không biên dịch và cách sửa

Những ví dụ sau **cố ý sai**, không dán chung vào chương trình `NumericExpressionTypeTable.java`:

~~~java
byte b = 10;
short s = 20;

byte sum = b + s;
// ERROR: b + s có kiểu int, không thể chuyển ngầm về byte.

float f = 2.5;
// ERROR: literal 2.5 là double, không chuyển ngầm về float.

int whole = 3 / 2.0;
// ERROR: biểu thức có kiểu double, không chuyển ngầm về int.

BigDecimal decimal =
        new BigDecimal("1") + new BigDecimal("2");
// ERROR: toán tử + không hỗ trợ hai BigDecimal.
~~~

Cách sửa:

~~~java
byte b = 10;
short s = 20;

int sum = b + s;                     // Tránh cast hẹp nếu không cần.
float f = 2.5f;                      // Literal float.
double quotient = 3 / 2.0;          // Giữ phần thập phân.

BigDecimal decimal = new BigDecimal("1")
        .add(new BigDecimal("2"));   // Dùng phương thức add.
~~~

Đây là đoạn mã minh họa; cần đặt trong method/lớp phù hợp và thêm `import java.math.BigDecimal;` nếu dùng độc lập.

Một cast như `byte sum = (byte) (b + s);` sẽ giúp biên dịch, nhưng **không đảm bảo** tổng nằm trong phạm vi `byte`. Nếu điều quan trọng là giữ nguyên tổng, dùng kiểu rộng hơn (`int`); nếu điều quan trọng là giới hạn miền, kiểm tra trước khi cast.

## 13. Những góc khuất nâng cao khi xác định kiểu

### `Math` có nhiều overload

`Math.round(float)` trả `int`, `Math.round(double)` trả `long`. Vì thế hậu tố của literal làm khác kiểu kết quả:

~~~java
int a = Math.round(2.6f);
long b = Math.round(2.6);
~~~

`Math.pow(2, 3)` trả `double` vì overload của `Math.pow` nhận hai `double` và trả `double`, dù các literal đầu vào có kiểu `int`. Cần tra **chữ ký method** thay vì tự áp dụng quy tắc toán tử số học.

### Overflow không tự nâng kiểu

~~~java
int overflowed = Integer.MAX_VALUE + 1;
System.out.println(overflowed); // -2147483648

long preserved = (long) Integer.MAX_VALUE + 1;
System.out.println(preserved);  // 2147483648
~~~

Trong phép cộng đầu tiên, hai toán hạng đều kiểu `int`, nên phép toán vẫn trả `int` và wrap. Việc **gán** kết quả của `Integer.MAX_VALUE + 1` sang biến `long` cũng không sửa được lỗi nếu phép cộng đã thực hiện ở `int`. Muốn thực hiện phép cộng với kiểu rộng hơn, phải chuyển ít nhất một toán hạng **trước phép cộng**.

### Loss of precision khi kiểu kết quả là floating point

~~~java
long exact = 9_007_199_254_740_993L;
float changed = exact + 0.0f;
System.out.println(changed); // một xấp xỉ float, không giữ toàn bộ chữ số
~~~

Quy tắc kiểu vẫn là `float`. `float` không thể giữ mọi số nguyên lớn biểu diễn được bằng `long`. Cũng không nên kết luận toán hạng nào “rộng” hơn chỉ từ số bit lưu trữ: floating point có phạm vi độ lớn rộng nhưng độ chính xác nguyên hữu hạn.

### `var` không chữa phép toán sai

~~~java
var quotient = 7 / 2;       // int, giá trị 3
var precise = 7 / 2.0;      // double, giá trị 3.5
var joined = "n=" + 7;      // String
~~~

`var` chỉ bỏ phần viết tên kiểu của biến local; các quy tắc kiểu của biểu thức vẫn không đổi.

### Constant expression có thể thu hẹp khi gán

~~~java
byte a = 1 + 2;   // Hợp lệ: biểu thức hằng int có giá trị 3.

int n = 1;
 // byte b = n + 2; // Không hợp lệ: n không phải constant variable.
~~~

Quy tắc narrowing ngầm cho constant expression còn phụ thuộc dạng phép gán và miền giá trị. Nó **không đổi kiểu của biểu thức** `1 + 2` từ `int` thành `byte`; chỉ có nghĩa trình biên dịch cho phép chuyển kết quả hằng sang `byte` ở ngữ cảnh cụ thể.

## 14. Cách tự tạo bảng để chẩn đoán lỗi thật

Thực hiện theo quy trình:

1. **Ghi kiểu của từng operand**: literal nguyên, literal thực, biến primitive, wrapper hay object?
2. **Khoanh toán tử hoặc lời gọi method**: phép toán nhị phân, unary, shift, so sánh, `?:`, phép gán, hay overloaded method?
3. **Áp dụng đúng quy tắc**: đừng dùng bảng `+` cho toán tử shift hay `?:`; đừng dùng numeric promotion cho `BigDecimal.add`.
4. **Ghi kiểu compile-time** *trước khi* tính giá trị.
5. **Tính giá trị** với quy tắc chia nguyên, overflow, cast, thứ tự đánh giá và giới hạn floating point.
6. **Kiểm tra bằng mã biên dịch**: dùng assignment typed, tìm lỗi conversion không hợp lệ và dùng output để kiểm tra giá trị.
7. **Ghi cảnh báo** khi phép tính có thể mất chữ số, overflow, unboxing null hoặc kết quả khác biểu thức toán học mong đợi.

Ví dụ mẫu:

| Biểu thức | Nhận diện | Kiểu | Giá trị | Cảnh báo |
| --- | --- | --- | --- | --- |
| `(double) (7 / 2)` | Chia `int` trước, cast sau | `double` | `3.0` | Phần thập phân đã mất |
| `(double) 7 / 2` | `double` chia `int` | `double` | `3.5` | Không bị chia nguyên |
| `Integer.MAX_VALUE + 1` | `int + int` | `int` | `-2147483648` | Overflow |
| `Math.round(2.6f)` | Overload `float` | `int` | `3` | Không trả `float` |

## 15. Bài tập: tự điền bảng kiểu và giá trị

Hãy xác định **kiểu của biểu thức** trước, sau đó mới tính giá trị. Giả sử:

~~~java
byte b = 4;
short s = 6;
char c = 'B';        // 66
int i = 9;
long l = 5L;
float f = 0.5f;
double d = 2.0;
Integer boxed = 3;
~~~

| STT | Biểu thức | Kiểu bạn dự đoán | Giá trị bạn dự đoán |
| ---: | --- | --- | --- |
| 1 | `b + s` | ? | ? |
| 2 | `c - 1` | ? | ? |
| 3 | `i / 2` | ? | ? |
| 4 | `i / 2.0f` | ? | ? |
| 5 | `l + f` | ? | ? |
| 6 | `f + d` | ? | ? |
| 7 | `~b` | ? | ? |
| 8 | `b << 2` | ? | ? |
| 9 | `1L << 5` | ? | ? |
| 10 | `i > l` | ? | ? |
| 11 | `true ? b : 2.0` | ? | ? |
| 12 | `boxed * 2` | ? | ? |
| 13 | `"value=" + i` | ? | ? |
| 14 | `Math.round(3.6f)` | ? | ? |
| 15 | `Math.pow(2, 3)` | ? | ? |

Đáp án:

| STT | Kiểu đúng | Giá trị | Quy tắc |
| ---: | --- | --- | --- |
| 1 | `int` | `10` | `byte + short` nâng lên `int` |
| 2 | `int` | `65` | `char` nâng lên `int` |
| 3 | `int` | `4` | Chia nguyên 9/2 |
| 4 | `float` | `4.5` | Có toán hạng `float` |
| 5 | `float` | `5.5` | `long + float` ra `float` |
| 6 | `double` | `2.5` | Có `double` |
| 7 | `int` | `-5` | Unary ~ trên `int` 4 |
| 8 | `int` | `16` | Shift operand trái nâng thành `int` |
| 9 | `long` | `32` | Dịch trái trên `long` |
| 10 | `boolean` | `true` | So sánh `9 > 5` |
| 11 | `double` | `4.0` | Hai nhánh `byte` và `double` |
| 12 | `int` | `6` | Unbox `Integer` rồi nhân |
| 13 | `String` | `value=9` | Nối chuỗi |
| 14 | `int` | `4` | `Math.round(float)` trả `int` |
| 15 | `double` | `8.0` | `Math.pow(double, double)` trả `double` |

### Thử thay đổi để hiểu sâu hơn

- Thay `l = 5L` bằng một số `long` rất lớn, thử `l + f` và quan sát sai số do `float`.
- Thay `i / 2` bằng `(double) i / 2`, so sánh kiểu và giá trị.
- Thay `b + s` bằng `b += s` và dự đoán kiểu biểu thức lẫn nguy cơ overflow.
- Thay `Math.round(3.6f)` bằng `Math.round(3.6)`: giá trị vẫn là 4 nhưng **kiểu trả về đổi từ `int` sang `long`**.
- Thử một wrapper `Integer` bằng `null` trong phép `boxed + 1` và giải thích ngoại lệ runtime.

**Kết luận:** để kiểm chứng biểu thức số trong Java, luôn bắt đầu từ **kiểu của toán hạng và quy tắc của từng toán tử**, sau đó mới tính giá trị và đánh giá nguy cơ overflow/loss of precision. Bảng kết quả cần phân biệt rõ compile-time type, giá trị runtime và cách gán, để tránh suy ra kiểu từ một dòng output.

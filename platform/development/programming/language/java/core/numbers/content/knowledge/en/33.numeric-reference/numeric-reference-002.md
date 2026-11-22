# Bảng widening, narrowing và numeric promotion trong Java

## 1. Ba khái niệm cần phân biệt

Khi dùng các kiểu số nguyên thủy của Java, không chỉ có chuyện “số nhỏ gán cho số lớn”. Cần xác định **kiểu của từng toán hạng**, **kiểu phép toán được thực hiện**, và **kiểu của biến nhận kết quả**:

- **Widening primitive conversion**: chuyển sang một kiểu được phép mở rộng ngầm, ví dụ `int → long`. Không nhất thiết chính xác tuyệt đối khi kiểu đích là `float` hoặc `double`.
- **Narrowing primitive conversion**: chuyển sang kiểu có thể mất miền giá trị/chữ số, ví dụ `int → byte` hoặc `double → int`. Thường phải cast tường minh.
- **Numeric promotion**: tự nâng kiểu toán hạng trước khi tính, ví dụ `byte + byte` được tính bằng `int`.

Bài học là tài liệu tra cứu cho `byte`, `short`, `char`, `int`, `long`, `float`, `double` trong Java 17+, gồm bảng chuyển đổi, các ngoại lệ, phép tính số nguyên và số thực, ví dụ chương trình độc lập, lỗi thường gặp và bài tập. `boolean` **không chuyển thành số hoặc ngược lại** theo cơ chế này.

## 2. Bảng widening primitive conversion

Các phép gán sau hợp lệ mà **không cần cast**:

| Từ kiểu | Có thể widening sang |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có kiểu số nguyên thủy rộng hơn |
| `boolean` | Không tham gia chuyển đổi số |

Sơ đồ gợi nhớ:

~~~text
byte → short → int → long → float → double
               ↑
char ──────────┘
~~~

**Không có widening `byte → char` hay `short → char`.** `char` là kiểu **không dấu 16 bit**, lưu mã UTF-16 code unit từ 0 đến 65535; `short` là kiểu **có dấu 16 bit**, từ -32768 đến 32767. Cùng độ rộng bit không có nghĩa hai kiểu tự chuyển đổi ngầm qua lại.

### Widening có luôn giữ nguyên giá trị không?

**Không.** Các widening giữa những kiểu nguyên phù hợp (`byte → short/int/long`, `short → int/long`, `char → int/long`, `int → long`) đều giữ chính xác giá trị. `int → double` cũng giữ chính xác mọi int, vì double có 53 bit significand, nhiều hơn 32 bit của int. `float → double` giữ chính xác *giá trị nhị phân float đang lưu* nhưng không khôi phục số decimal đã bị làm tròn trước đó.

Ngược lại, `int → float`, `long → float` và `long → double` có thể mất các bit có nghĩa do kiểu đích không đủ độ chính xác. Trình biên dịch vẫn cho phép widening; nó không đảm bảo làm tròn sẽ không xảy ra.

### Ví dụ Java 17: widening mất precision

Tạo tệp `WideningDemo.java`:

~~~java
public class WideningDemo {
    public static void main(String[] args) {
        byte source = 100;
        short s = source;
        long exact = s;
        double d = exact;

        System.out.println("long = " + exact);
        System.out.println("double = " + d);

        int largeInt = 16_777_217;
        float f = largeInt;
        System.out.println("int = " + largeInt);
        System.out.println("float = " + f);
        System.out.println("float back = " + (int) f);

        long largeLong = 9_007_199_254_740_993L;
        double rounded = largeLong;
        System.out.println("long back = " + (long) rounded);
    }
}
~~~

~~~bash
javac WideningDemo.java
java WideningDemo
~~~

Kết quả:

~~~text
long = 100
double = 100.0
int = 16777217
float = 1.6777216E7
float back = 16777216
long back = 9007199254740992
~~~

`float` có 24 bit significand nên không thể biểu diễn chính xác mọi `int` trên mốc `2^24`. `double` không thể biểu diễn chính xác mọi `long` trên mốc `2^53`. Widening có thể an toàn về **kiểu** mà không an toàn về **precision**.

## 3. Bảng narrowing primitive conversion

Đường narrowing cần cast trong phần lớn tình huống:

| Từ | Các đích narrowing tiêu biểu | Hậu quả cần xét |
| --- | --- | --- |
| `short` | `byte`, `char` | Mất bit cao, có thể đổi dấu |
| `char` | `byte`, `short` | Mất bit hoặc đổi cách diễn giải dấu |
| `int` | `byte`, `short`, `char` | Giữ các bit thấp theo độ rộng đích |
| `long` | `byte`, `short`, `char`, `int` | Bỏ các bit cao |
| `double` | `float` | Có thể làm tròn, underflow thành zero, overflow thành infinity |
| `float/double` | `int`, `long` và các kiểu nguyên nhỏ hơn | Loại phần thập phân, có quy tắc riêng cho NaN/vượt miền |

Các kiểu nguyên có dấu sử dụng biểu diễn bù hai. Với narrowing từ `int` sang `byte`, Java giữ 8 bit thấp rồi diễn giải thành byte có dấu. Vì vậy `(byte) 130` bằng `-126`, không phải 127 và không ném exception. `(char) -1` giữ 16 bit thấp và thành code unit số `65535`.

### Cast từ float/double sang nguyên không phải rounding gần nhất

`(int) 3.99` là `3`; `(int) -3.99` là `-3`. Quy tắc loại phần thập phân **về 0**. Với `NaN`, chuyển sang `int`/`long` cho 0. Với giá trị vượt miền int/long, quá trình chuyển sang chính kiểu đó cho biên min/max theo hướng tương ứng; với `byte`/`short`/`char` còn có bước thu hẹp nguyên tiếp theo nên kết quả **không đơn giản là chặn tại biên kiểu nhỏ**.

### Ví dụ Java 17: narrowing và giá trị đặc biệt

Tạo tệp `NarrowingDemo.java`:

~~~java
public class NarrowingDemo {
    public static void main(String[] args) {
        int n = 130;
        byte b = (byte) n;
        char c = (char) -1;

        System.out.println("byte = " + b);
        System.out.println("char code = " + (int) c);
        System.out.println("3.99 -> int = " + (int) 3.99);
        System.out.println("-3.99 -> int = " + (int) -3.99);
        System.out.println("NaN -> int = " + (int) Double.NaN);
        System.out.println("infinity -> int = "
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("1000 -> byte = " + (byte) 1000);
    }
}
~~~

~~~bash
javac NarrowingDemo.java
java NarrowingDemo
~~~

Kết quả:

~~~text
byte = -126
char code = 65535
3.99 -> int = 3
-3.99 -> int = -3
NaN -> int = 0
infinity -> int = 2147483647
1000 -> byte = -24
~~~

Khi cần làm tròn thực sự, sử dụng `Math.round` hoặc `BigDecimal.setScale` cùng rounding mode thích hợp; đừng thay bằng cast và kỳ vọng quy tắc giống nhau. Cũng không dùng cast để kiểm tra an toàn miền giá trị vì Java không tự ném lỗi khi các bit bị bỏ.

## 4. Unary numeric promotion

Các toán tử một ngôi số học `+x`, `-x` và toán tử bù bit `~x` (cho kiểu nguyên) áp dụng **unary numeric promotion**:

| Kiểu ban đầu | Kiểu sau promotion |
| --- | --- |
| `byte`, `short`, `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |

Ví dụ `byte x = 5; int y = -x;` hợp lệ, vì `-x` có kiểu int. `byte y = -x;` không hợp lệ nếu `x` là biến byte runtime và không cast, dù giá trị `-5` có thể vừa byte.

`~charValue` cũng có kiểu int. Toán tử logic `!` áp dụng lên boolean, không phải numeric promotion. Tương tự, `boolean` không chuyển thành 0 hoặc 1 khi tính toán số học.

## 5. Binary numeric promotion: bảng chọn kiểu hai toán hạng

Trong các phép toán hai ngôi số học như `+`, `-`, `*`, `/`, `%`, Java chọn kiểu tính toán theo thứ tự:

1. Có `double` → dùng `double`.
2. Không có double, có `float` → dùng `float`.
3. Không có double/float, có `long` → dùng `long`.
4. Còn lại → dùng `int`.

| Biểu thức | Kiểu tính toán/kết quả |
| --- | --- |
| `byte + byte` | `int` |
| `byte + short` | `int` |
| `short + char` | `int` |
| `int + long` | `long` |
| `long + float` | `float` |
| `float + double` | `double` |
| `int / int` | `int` |
| `int / double` | `double` |
| `char * byte` | `int` |

Các toán tử so sánh số như `<` và `>=` cũng dùng numeric promotion để so, nhưng **kết quả của phép so sánh là boolean**. Đừng áp dụng bảng “kiểu kết quả số học” lên mọi toán tử một cách máy móc. Với phép nối chuỗi, toán tử `+` còn có ngữ nghĩa nối chuỗi khác phép cộng số.

### Ví dụ Java 17: chia nguyên và kiểu của biểu thức

Tạo tệp `NumericPromotionDemo.java`:

~~~java
public class NumericPromotionDemo {
    public static void main(String[] args) {
        byte a = 10;
        short b = 20;
        int sum = a + b;
        char letter = 'A';
        int nextCode = letter + 1;
        float mixed = 1L + 0.5f;

        System.out.println("byte + short = " + sum);
        System.out.println("char + int = " + nextCode);
        System.out.println("long + float = " + mixed);
        System.out.println("5 / 2 = " + (5 / 2));
        System.out.println("assigned double = " + (double) (5 / 2));
        System.out.println("5 / 2.0 = " + (5 / 2.0));
    }
}
~~~

~~~bash
javac NumericPromotionDemo.java
java NumericPromotionDemo
~~~

Kết quả:

~~~text
byte + short = 30
char + int = 66
long + float = 1.5
5 / 2 = 2
assigned double = 2.0
5 / 2.0 = 2.5
~~~

**Kiểu biến nhận kết quả không sửa kiểu của phép toán đã xảy ra.** `double d = 5 / 2;` thực hiện chia nguyên trước (cho 2), rồi widening từ int thành double (2.0). Muốn kết quả 2.5, chuyển **toán hạng trước phép chia**: `5 / 2.0` hoặc `(double) 5 / 2`.

## 6. Overflow trước khi widening sang biến đích

Một bẫy:

~~~java
// Đoạn minh họa: kết quả đã tràn int trước khi gán.
long wrong = 50_000 * 50_000;
~~~

Cả hai literal là `int`, nên `50_000 * 50_000` là phép nhân int, overflow trước khi được chuyển sang long. Để tránh, dùng literal long `50_000L * 50_000`, hoặc cast một toán hạng **trước khi nhân**.

### Ví dụ Java 17: overflow do kiểu toán hạng

Tạo tệp `OverflowDemo.java`:

~~~java
public class OverflowDemo {
    public static void main(String[] args) {
        long wrong = 50_000 * 50_000;
        long correct = 50_000L * 50_000;

        System.out.println("int first = " + wrong);
        System.out.println("long first = " + correct);

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
~~~

~~~bash
javac OverflowDemo.java
java OverflowDemo
~~~

Kết quả:

~~~text
int first = -1794967296
long first = 2500000000
overflow detected
~~~

Phép `+`, `-`, `*` với `int`/`long` thường không ném lỗi overflow; kết quả bù hai quay vòng theo số bit. Khi không được phép tràn âm thầm, `Math.addExact`, `subtractExact`, `multiplyExact` giúp phát hiện lỗi đối với int/long.

## 7. Phép dịch bit dùng quy tắc riêng

Toán tử dịch bit `<<`, `>>`, `>>>` không dùng binary numeric promotion như phép cộng. **Từng toán hạng được unary numeric promotion** và kiểu kết quả theo toán hạng bên trái sau promotion (`int` hoặc `long`).

- `byte b = 1; b << 8` cho kết quả kiểu int = 256.
- `1L << 40` dịch long và cho 1099511627776.
- `1 << 32` bằng `1 << 0` vì chỉ 5 bit thấp của khoảng dịch được dùng cho int.
- `1L << 64` bằng `1L << 0` vì chỉ 6 bit thấp được dùng cho long.

### Ví dụ Java 17: shift và promotion

Tạo tệp `ShiftDemo.java`:

~~~java
public class ShiftDemo {
    public static void main(String[] args) {
        byte x = 1;
        int result = x << 8;
        long wide = 1L << 40;

        System.out.println("byte shift = " + result);
        System.out.println("long shift = " + wide);
        System.out.println("1 << 32 = " + (1 << 32));
        System.out.println("-1 >>> 1 = " + (-1 >>> 1));
    }
}
~~~

~~~bash
javac ShiftDemo.java
java ShiftDemo
~~~

Kết quả:

~~~text
byte shift = 256
long shift = 1099511627776
1 << 32 = 1
-1 >>> 1 = 2147483647
~~~

Các toán tử bitwise `&`, `|`, `^` giữa các số nguyên tuân quy tắc numeric promotion riêng phù hợp; khi hai toán hạng là boolean, chúng cũng có dạng toán tử boolean, **không có chuyển boolean sang int**.

## 8. Ngoại lệ: narrowing hằng int trong assignment

Trong **assignment conversion**, một *biểu thức hằng* có kiểu int có thể gán ngầm vào `byte`, `short` hoặc `char` nếu **giá trị hằng nằm trong miền** của kiểu đích:

~~~java
// Minh họa cú pháp hợp lệ, không phải chương trình độc lập.
byte max = 127;
short s = 1 + 2;
char latinA = 65;
final int LIMIT = 100;
byte fromConstant = LIMIT;
~~~

Nhưng:

~~~java
// Minh họa lỗi biên dịch, không được chạy nguyên khối này.
byte invalid = 128;      // Hằng vượt miền byte
int value = 127;
byte fromValue = value;   // value không phải constant expression
byte x = 10;
byte result = x + 1;     // x + 1 có kiểu int
~~~

Một `final int` khởi tạo bằng biểu thức hằng phù hợp có thể tham gia quy tắc này; biến `int` thông thường không được narrowing ngầm chỉ vì giá trị lúc chạy đang vừa miền byte.

### Ví dụ Java 17: hằng vừa miền và cast biến

Tạo tệp `ConstantAssignmentDemo.java`:

~~~java
public class ConstantAssignmentDemo {
    public static void main(String[] args) {
        byte max = 127;
        short computed = 1 + 2;
        char ascii = 65;
        final int LIMIT = 100;
        byte fromConstant = LIMIT;

        int runtime = 127;
        byte explicit = (byte) runtime;

        System.out.println("byte = " + max);
        System.out.println("short = " + computed);
        System.out.println("char code = " + (int) ascii);
        System.out.println("final constant = " + fromConstant);
        System.out.println("cast variable = " + explicit);
    }
}
~~~

~~~bash
javac ConstantAssignmentDemo.java
java ConstantAssignmentDemo
~~~

Kết quả:

~~~text
byte = 127
short = 3
char code = 65
final constant = 100
cast variable = 127
~~~

**Ngoại lệ gán hằng không áp dụng tự động cho method invocation.** Với phương thức `takeByte(byte x)`, gọi `takeByte(1)` không hợp lệ nếu đó là overload duy nhất; phải dùng `takeByte((byte) 1)` hoặc truyền biến byte.

## 9. Compound assignment và ++ có narrowing ngầm

`byte b = 120; b += 10;` hợp lệ, dù biểu thức `b + 10` có kiểu int. Compound assignment có ngữ nghĩa gần giống `b = (byte) (b + 10)`, khác ở chỗ toán hạng trái chỉ được đánh giá một lần. Điều này cho phép **narrowing ngầm** và có thể tạo overflow. `++`, `--` với các kiểu số nguyên nhỏ cũng có thể đưa giá trị quay vòng.

### Ví dụ Java 17: += không bảo đảm an toàn miền

Tạo tệp `CompoundAssignmentDemo.java`:

~~~java
public class CompoundAssignmentDemo {
    public static void main(String[] args) {
        byte b = 120;
        b += 10;

        short s = 32767;
        s++;

        int i = Integer.MAX_VALUE;
        i += 1L;

        System.out.println("byte += = " + b);
        System.out.println("short++ = " + s);
        System.out.println("int += long = " + i);
    }
}
~~~

~~~bash
javac CompoundAssignmentDemo.java
java CompoundAssignmentDemo
~~~

Kết quả:

~~~text
byte += = -126
short++ = -32768
int += long = -2147483648
~~~

Ngược lại, `b = b + 10` báo lỗi biên dịch nếu b là biến byte vì gán `int` runtime vào byte thiếu cast. Việc cú pháp `+=` biên dịch được không đồng nghĩa kết quả ở trong miền. Với dữ liệu cần an toàn, tính trên kiểu rộng và kiểm tra giới hạn trước khi cast.

## 10. Method invocation, overload, boxing và toán tử ba ngôi

**Method invocation conversion** cho phép widening primitive hợp lệ, nhưng **không áp dụng ngoại lệ narrowing hằng int trong assignment**. Phân giải overload còn phụ thuộc các quy tắc ưu tiên giữa phương thức có thể gọi, boxing/unboxing, varargs và mức độ cụ thể của chữ ký.

### Ví dụ Java 17: widening khi chọn overload

Tạo tệp `OverloadDemo.java`:

~~~java
public class OverloadDemo {
    static String choose(long x) {
        return "long";
    }
    static String choose(float x) {
        return "float";
    }
    static String choose(double x) {
        return "double";
    }

    public static void main(String[] args) {
        System.out.println("int -> " + choose(5));
        System.out.println("float -> " + choose(5.0f));
        System.out.println("double -> " + choose(5.0));
    }
}
~~~

~~~bash
javac OverloadDemo.java
java OverloadDemo
~~~

Kết quả:

~~~text
int -> long
float -> float
double -> double
~~~

`choose(5)` có thể widening int sang long, float, double; trong các overload này long là lựa chọn cụ thể hơn. `Integer`, `Long`, `Double` là **wrapper reference types**, không phải primitive; có quy tắc boxing/unboxing riêng. Ví dụ `Integer i = 10; long x = i;` hợp lệ do unboxing int rồi widening long, nhưng `Long l = Integer.valueOf(10);` không phải widening giữa hai wrapper. Unboxing một wrapper `null` có thể ném `NullPointerException`.

Toán tử ba ngôi `condition ? a : b` có quy tắc **numeric conditional expressions** riêng, với ngoại lệ liên quan byte/short/char và hằng int vừa miền. Vì vậy không thể áp dụng mù quáng bảng `a + b` cho tất cả toán tử ba ngôi. Hãy kiểm tra loại từng nhánh, các trường hợp hằng và phiên bản JLS khi cần suy luận kiểu kết quả chính xác.

## 11. BigDecimal không tự tham gia numeric promotion

`BigDecimal` là **lớp**, không thuộc hệ primitive promotion:

- `0.1 + 0.2` là phép tính double, không phải phép cộng decimal chính xác.
- `new BigDecimal("0.1").add(new BigDecimal("0.2"))` thực hiện phép cộng BigDecimal thập phân.
- Java không tự cho phép toán tử `BigDecimal + int`. Dùng `add` và tạo toán hạng BigDecimal tường minh.
- Java cũng không tự chuyển một phép int/long bị overflow sang BigInteger hoặc BigDecimal.
- `new BigDecimal(0.1)` giữ đúng giá trị double nhị phân gần đúng đã nhận, có thể khác số decimal 0.1 người dùng mong muốn; ưu tiên constructor chuỗi decimal chính xác khi bài toán cần điều đó.

Với tiền hoặc các giá trị decimal đòi độ chính xác, chọn kiểu số thích hợp **trước khi thực hiện phép toán**, không chờ mất dữ liệu rồi mới ép kiểu kết quả.

## 12. Bảng quyết định nhanh

| Code hoặc tình huống | Kết quả/quy tắc |
| --- | --- |
| `long l = someInt;` | Widening int→long, giữ nguyên giá trị |
| `float f = someInt;` | Widening hợp lệ, có thể mất precision |
| `byte b = 127;` | Hợp lệ do ngoại lệ hằng int trong assignment |
| `byte b = 128;` | Lỗi compile: ngoài miền |
| `int i = someLong;` | Lỗi compile nếu không cast |
| `byte a = 1, b = 2; int c = a+b;` | Phép cộng dùng int |
| `double d = 5/2;` | 2.0, vì chia int trước |
| `double d = 5/2.0;` | 2.5, vì có toán hạng double |
| `long r = 50000*50000;` | Tràn int trước khi widening sang long |
| `long r = 50000L*50000;` | Nhân long, kết quả 2500000000 |
| `byte b = 120; b += 10;` | Kết quả -126 do narrowing ngầm |
| `int i = (int)3.99;` | 3, bỏ phần lẻ hướng về 0 |
| `char c = (char)-1;` | Mã char = 65535 |
| `int s = 1 << 32;` | 1 do chỉ dùng 5 bit thấp khoảng dịch |
| `boolean b = (boolean)1;` | Không hợp lệ, boolean không tham gia chuyển đổi số |

Bảng áp dụng trực tiếp cho kiểu primitive. Những trường hợp boxing, wrapper, generic, overload, toán tử ba ngôi và hằng đặc biệt phải xét thêm quy tắc tương ứng.

## 13. Sai lầm thường gặp

1. **“Widening luôn chính xác.”** Không đúng với int→float hoặc long→double cho số lớn.
2. **“Biến long nhận kết quả sẽ ép phép toán sang long.”** Không: int có thể tràn trước khi gán.
3. **“byte + byte là byte.”** Không: binary promotion thành int.
4. **“char tương đương short.”** Không: char không dấu, short có dấu.
5. **“Cast double sang int làm tròn gần nhất.”** Không: cắt phần thập phân về 0.
6. **“Cast narrowing tự kiểm tra vượt miền.”** Không: số nguyên có thể bị cắt các bit cao.
7. **“`+=` an toàn hơn `= a+b`.”** Không: có narrowing ngầm.
8. **“Hằng số int vừa miền được narrowing trong mọi ngữ cảnh.”** Ngoại lệ assignment không áp dụng với method invocation thông thường.
9. **“Dịch bit dùng binary promotion như cộng.”** Không: kiểu kết quả dựa vào toán hạng trái đã unary promotion.
10. **“Boolean có thể cast sang int.”** Java không hỗ trợ.
11. **“Wrapper có thể chuyển ngầm như primitive.”** Boxing/unboxing và widening reference có quy tắc riêng.
12. **“BigDecimal được Java tự chọn khi có số decimal.”** Không: phải dùng API BigDecimal tường minh.

## 14. Bài tập và đáp án

**Câu 1.** `int i = 16_777_217; float f = i;` có cho cùng giá trị không?

**Đáp án:** Không. Float có thể biểu diễn 16.777.216 mà không giữ chính xác 16.777.217.

**Câu 2.** Vì sao `byte x=10, y=20; byte sum=x+y;` không biên dịch?

**Đáp án:** `x+y` có kiểu int; dùng `int sum=x+y` hoặc cast sau khi xác minh miền.

**Câu 3.** `double result=5/2;` bằng bao nhiêu và sửa thế nào?

**Đáp án:** 2.0; dùng `5/2.0` hoặc `(double)5/2` để được 2.5.

**Câu 4.** `(byte)130`, `(char)-1` và `(int)-3.99` cho kết quả gì?

**Đáp án:** -126, char code 65535 và -3.

**Câu 5.** `byte b=120; b+=10;` và `short s=32767; s++;` cho giá trị gì?

**Đáp án:** b là -126, s là -32768; compound assignment/increment có thể narrowing.

**Câu 6.** `long p=50_000*50_000;` có bằng `2_500_000_000L` không?

**Đáp án:** Không; phép nhân int tràn trước. Dùng `50_000L*50_000`.

**Câu 7.** Tại sao `byte b=127;` hợp lệ nhưng `int n=127; byte b=n;` không?

**Đáp án:** Biểu thức hằng int vừa miền có ngoại lệ gán, còn biến int thông thường cần cast.

**Câu 8.** `1 << 32` cho số nào?

**Đáp án:** 1, vì dịch int chỉ xem 5 bit thấp của khoảng dịch, nên 32 tương đương 0.

## 15. Ghi nhớ

- **Widening** được phép ngầm nhưng có thể mất precision khi từ số nguyên lớn sang floating-point.
- **Narrowing** thường cần cast; số nguyên bỏ bit cao, dấu phẩy động sang nguyên bỏ phần lẻ hướng về 0 và có quy tắc biên.
- **Unary promotion** nâng byte/short/char lên int; **binary promotion** ưu tiên double, float, long rồi int trước phép tính.
- **Kiểu toán hạng quyết định phép toán trước khi gán**, nên double nhận phép chia nguyên hoặc long nhận phép nhân int đã tràn vẫn giữ lỗi trung gian.
- **Constant narrowing trong assignment**, compound assignment, toán tử dịch, overload, toán tử ba ngôi và boxing/unboxing là các ngoại lệ cần tra cứu riêng.
- Với số học decimal chính xác hoặc số nguyên vượt long, dùng BigDecimal/BigInteger chủ động qua API, không mong primitive promotion tự giải quyết.

Tài liệu chuẩn: Java Language Specification cho Java SE 17 — `5.1.2 Widening Primitive Conversion`, `5.1.3 Narrowing Primitive Conversion`, `5.2 Assignment Contexts`, `5.6 Numeric Contexts`, `15.15 Unary Operators`, `15.17 Multiplicative Operators`, `15.18 Additive Operators`, `15.19 Shift Operators`, `15.25 Conditional Operator` và `15.26 Assignment Operators`.
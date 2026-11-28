# Kiểm tra giá trị biên, mất độ chính xác, NaN và giá trị null khi có boxing

## Mục tiêu bài học

Primitive type patterns mở rộng pattern matching để một giá trị có thể được kiểm tra và chuyển đổi an toàn sang kiểu nguyên thủy như `byte`, `int`, `long`, `float` hoặc `double`. Điểm quan trọng là pattern không chấp nhận một phép chuyển đổi chỉ vì Java có thể thực hiện phép cast đó. Pattern chỉ khớp khi phép chuyển đổi tại thời điểm chạy **không làm mất thông tin và không phát sinh exception**.

Ví dụ, một `int` có thể cast sang `byte`, nhưng giá trị ngoài khoảng -128 đến 127 sẽ bị cắt bớt bit. Primitive type pattern từ chối trường hợp mất dữ liệu đó:

~~~java
int value = 1000;

if (value instanceof byte b) {
    System.out.println("byte: " + b);
} else {
    System.out.println("Không thể chuyển chính xác sang byte");
}
~~~

Kết quả là nhánh `else`, vì cast thông thường `(byte) 1000` cho ra `-24`, làm thay đổi giá trị.

Bài **Kiểm tra giá trị biên, mất độ chính xác, NaN và giá trị null khi có boxing** thuộc chương **Mẫu kiểu nguyên thủy** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào phép chuyển đổi kiểm tra (testing conversion), tính chính xác (exactness), miền giá trị, floating-point và quá trình boxing/unboxing.

Sau bài này, bạn có thể:

1. Giải thích vì sao primitive type pattern chỉ khớp khi phép chuyển đổi là exact.
2. Kiểm tra các giá trị sát biên khi chuyển giữa `int`, `byte`, `short`, `char` và `long`.
3. Nhận biết mất độ chính xác khi chuyển giữa số nguyên và `float`/`double`.
4. Xử lý `NaN`, vô cực, `+0.0` và `-0.0` đúng theo quy tắc IEEE 754 và JLS.
5. Phân biệt boxing từ primitive sang wrapper với unboxing từ wrapper sang primitive trong pattern matching.
6. Xử lý wrapper `null` mà không vô tình gây `NullPointerException`.
7. Dùng `instanceof` và `switch` để kiểm tra chuyển đổi an toàn mà không làm tròn, cắt bit hoặc âm thầm đổi giá trị.
8. Biên dịch và chạy đúng phiên bản preview tương ứng với JDK đang dùng.

> **Trạng thái tính năng tại thời điểm hiện tại:** Primitive Types in Patterns, `instanceof`, and `switch` vẫn là preview trong JDK 27 theo JEP 532 (Fifth Preview). Trong JDK 25, tính năng này là JEP 507 (Third Preview); JDK 26 là JEP 530 (Fourth Preview). Đây chưa phải tính năng ngôn ngữ permanent. Ví dụ chính trong bài bám theo JDK 27 hiện hành; khi thử trên JDK 25, phải dùng chính JDK 25 và bật preview của release đó.

## 1. Cốt lõi: pattern kiểm tra phép chuyển đổi có an toàn không

Trong Java truyền thống, một cast primitive có thể làm thay đổi giá trị mà không ném exception:

~~~java
int source = 1000;
byte result = (byte) source;

System.out.println(result); // -24
~~~

Đây là hành vi hợp lệ của narrowing primitive conversion. Java bỏ các bit cao không thể chứa trong kiểu đích. Điều này có thể làm thay đổi độ lớn và thậm chí cả dấu của giá trị.

Primitive type pattern dùng một quy tắc khác:

~~~java
int source = 1000;

if (source instanceof byte value) {
    System.out.println("Giá trị byte: " + value);
} else {
    System.out.println("Chuyển đổi sẽ làm mất dữ liệu");
}
~~~

Pattern chỉ khớp nếu phép chuyển đổi từ giá trị nguồn sang kiểu đích là **exact**. Nếu phép chuyển đổi không exact, kết quả kiểm tra là `false`; pattern variable không được khởi tạo và phần thân nhánh không chạy.

### 1.1. Testing conversion khác với cast thông thường

| Tình huống | Cast thông thường | Primitive type pattern |
|---|---|---|
| Chuyển `int 10` sang `byte` | Kết quả là 10 | Khớp, pattern variable nhận 10 |
| Chuyển `int 1000` sang `byte` | Kết quả là -24 | Không khớp |
| Chuyển `double 12.5` sang `int` | Kết quả là 12 | Không khớp |
| Chuyển `double NaN` sang `int` | Kết quả là 0 | Không khớp |
| Unbox `Integer null` sang `int` | Ném `NullPointerException` | Không khớp, không làm exception thoát ra |

Một testing conversion có thể được phép về mặt kiểu dữ liệu nhưng vẫn không exact với một giá trị cụ thể. Ví dụ, `int` có thể được kiểm tra với pattern `byte`, nhưng chỉ những giá trị biểu diễn chính xác bằng `byte` mới khớp.

### 1.2. Quy tắc exactness

Theo JLS, một testing conversion là exact khi nó tạo ra kết quả mà **không mất thông tin và không ném exception**. Nếu có mất thông tin hoặc có exception, phép chuyển đổi là inexact.

Các dạng mất thông tin thường gặp:

- **Mất độ lớn (magnitude):** giá trị sau chuyển đổi cách số 0 ít hoặc nhiều hơn giá trị gốc.
- **Mất độ chính xác (precision):** các bit có nghĩa thấp bị làm tròn hoặc loại bỏ.
- **Mất miền biểu diễn (range):** giá trị vượt khỏi `MIN_VALUE`/`MAX_VALUE` của kiểu đích.
- **Mất dấu (sign):** giá trị đổi dấu hoặc mất dấu, ví dụ `-0.0` thành số nguyên 0.

Nếu testing conversion gồm nhiều bước, tất cả các bước phải exact. Ví dụ, kiểm tra một wrapper bằng primitive pattern có thể gồm kiểm tra kiểu tham chiếu, unboxing và widening primitive conversion.

**Hệ quả:** pattern matching không phải cú pháp viết tắt cho cast. Nó là phép kiểm tra trước khi cho phép sử dụng giá trị đã chuyển đổi.

## 2. Kiểm tra biên khi thu hẹp kiểu số nguyên

Các kiểu nguyên thủy có miền giá trị khác nhau:

| Kiểu | Miền giá trị |
|---|---|
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `char` | 0 đến 65.535 |
| `int` | -2³¹ đến 2³¹ - 1 |
| `long` | -2⁶³ đến 2⁶³ - 1 |

Khi kiểm tra một giá trị `int` với pattern `byte`, chỉ giá trị nằm trong miền của `byte` mới được chuyển đổi chính xác.

~~~java
public final class IntegerBoundaryDemo {

    static void checkByte(int value) {
        if (value instanceof byte b) {
            System.out.println(value + " -> byte " + b);
        } else {
            System.out.println(value + " nằm ngoài miền byte");
        }
    }

    public static void main(String[] args) {
        checkByte(-129);
        checkByte(-128);
        checkByte(0);
        checkByte(127);
        checkByte(128);
    }
}
~~~

Kết quả mong đợi:

~~~text
-129 nằm ngoài miền byte
-128 -> byte -128
0 -> byte 0
127 -> byte 127
128 nằm ngoài miền byte
~~~

Giá trị ngay tại hai biên vẫn khớp vì không mất thông tin. Giá trị lệch ra ngoài dù chỉ một đơn vị cũng không khớp.

### 2.1. Kiểm tra các kiểu đích khác

Có thể dùng cùng một cách cho `short`, `char` và `int`:

~~~java
static void inspectInteger(int value) {
    if (value instanceof byte b) {
        System.out.println("byte: " + b);
    } else if (value instanceof short s) {
        System.out.println("short: " + s);
    } else if (value instanceof char c) {
        System.out.println("char code: " + (int) c);
    } else {
        System.out.println("Không khớp byte, short hoặc char");
    }
}
~~~

Thứ tự trên có ý nghĩa vì một giá trị nhỏ có thể biểu diễn chính xác bằng nhiều kiểu đích. Ví dụ `int 65` có thể chuyển exact sang `byte`, `short` và `char`; nhánh đầu tiên khớp sẽ được thực thi.

Với `char`, cần nhớ đây là kiểu số nguyên 16-bit **không dấu**. Vì vậy:

- `int 0` và `int 65535` có thể chuyển exact sang `char`.
- `int -1` không thể chuyển exact sang `char`.
- `int 65536` không thể chuyển exact sang `char`.

### 2.2. Không nhầm exact conversion với kiểm tra miền bằng cast vòng lại

Một cách kiểm tra cũ thường thấy là cast sang kiểu nhỏ rồi cast ngược lại:

~~~java
int value = 1000;
boolean looksSafe = (int) (byte) value == value;
~~~

Cách này không phải quy tắc tổng quát để kiểm tra exactness. Một số phép chuyển đổi kép có thể che lấp việc mất thông tin ở bước đầu.

Ví dụ đáng chú ý là `Integer.MAX_VALUE` sang `float`: giá trị này không biểu diễn chính xác được bằng `float`. Khi cast ngược từ kết quả `float` về `int`, quy tắc bão hòa của narrowing floating-to-integral conversion có thể trả lại `Integer.MAX_VALUE`. So sánh vòng lại có thể cho cảm giác giá trị không đổi dù bước chuyển đầu tiên đã mất độ chính xác.

Primitive type pattern sử dụng quy tắc exactness của JLS, không dựa vào phép cast vòng lại do ứng dụng tự viết.

## 3. Mất độ chính xác khi chuyển số nguyên sang float hoặc double

Một phép widening không phải lúc nào cũng bảo toàn mọi bit. Tên gọi “widening” mô tả miền biểu diễn rộng hơn, nhưng không bảo đảm mọi giá trị nguyên đều được biểu diễn chính xác trong định dạng floating-point.

### 3.1. int sang float

`float` có 24 bit độ chính xác significand (bao gồm bit ẩn). Vì vậy, tất cả số nguyên liên tiếp chỉ được biểu diễn chính xác đến \(2^{24}\). Ở phía trên ngưỡng này, một số số nguyên vẫn exact, nhưng các giá trị nằm giữa những điểm biểu diễn sẽ bị làm tròn.

~~~java
public final class IntToFloatDemo {

    static void inspect(int value) {
        if (value instanceof float f) {
            System.out.println(value + " biểu diễn exact bằng float: " + f);
        } else {
            System.out.println(value + " bị mất độ chính xác khi đổi sang float");
        }
    }

    public static void main(String[] args) {
        inspect(16_777_216);
        inspect(16_777_217);
        inspect(16_777_218);
    }
}
~~~

Kết quả mong đợi:

~~~text
16777216 biểu diễn exact bằng float: 1.6777216E7
16777217 bị mất độ chính xác khi đổi sang float
16777218 biểu diễn exact bằng float: 1.6777218E7
~~~

Điểm cần nhớ là không nên viết quy tắc đơn giản “mọi số lớn hơn 16.777.216 đều mất chính xác”. Từ ngưỡng đó, khoảng cách giữa các giá trị `float` biểu diễn được tăng dần; những số phù hợp với bước biểu diễn vẫn có thể exact.

### 3.2. long sang double

`double` có 53 bit độ chính xác significand. Mọi số nguyên trong khoảng \([-2^{53}, 2^{53}]\) đều biểu diễn chính xác. Ngoài khoảng này, một số giá trị vẫn exact, nhưng không phải mọi số nguyên liên tiếp.

~~~java
public final class LongToDoubleDemo {

    static void inspect(long value) {
        if (value instanceof double d) {
            System.out.println(value + " -> double exact: " + d);
        } else {
            System.out.println(value + " không biểu diễn exact bằng double");
        }
    }

    public static void main(String[] args) {
        inspect(9_007_199_254_740_992L);
        inspect(9_007_199_254_740_993L);
        inspect(9_007_199_254_740_994L);
    }
}
~~~

Giá trị \(2^{53}+1\) không biểu diễn chính xác bằng `double`; giá trị \(2^{53}+2\) có thể biểu diễn chính xác vì nó nằm đúng trên một điểm biểu diễn.

### 3.3. Những widening primitive conversion luôn exact

Một số phép widening được xác định là exact với mọi giá trị của kiểu nguồn:

| Kiểu nguồn | Kiểu đích | Exact với mọi giá trị? |
|---|---|---|
| `byte` | `short`, `int`, `long` | Có |
| `short` | `int`, `long` | Có |
| `char` | `int`, `long` | Có |
| `int` | `long` | Có |
| `float` | `double` | Có |
| `int` | `float` | Không |
| `long` | `float` | Không |
| `long` | `double` | Không |

Ví dụ `float` sang `double` luôn exact, nhưng giá trị `double` thu được phản ánh đúng giá trị nhị phân mà `float` đang giữ, không tự khôi phục số thập phân ban đầu.

~~~java
float f = 1000.01f;

if (f instanceof double d) {
    System.out.println(d);
}
~~~

Kết quả gần như:

~~~text
1000.010009765625
~~~

Đây là phép widening exact: `double` biểu diễn chính xác giá trị nhị phân của `float`. Sai số đã xuất hiện khi số thập phân ban đầu được làm tròn thành `float`, trước khi pattern chạy.

## 4. Kiểm tra floating-point khi thu hẹp kiểu

Khi chuyển `double` sang `float`, có ba tình huống thường gặp:

- Giá trị biểu diễn chính xác được bằng `float`: pattern khớp.
- Giá trị phải làm tròn hoặc vượt/thiếu miền biểu diễn: pattern không khớp.
- Giá trị là NaN, vô cực hoặc số 0: có quy tắc exactness riêng.

~~~java
public final class DoubleToFloatDemo {

    static void inspect(double value) {
        if (value instanceof float f) {
            System.out.println(value + " -> float exact: " + f);
        } else {
            System.out.println(value + " không thể chuyển exact sang float");
        }
    }

    public static void main(String[] args) {
        inspect(0.5d);
        inspect(0.1d);
        inspect(1.0e100);
        inspect(1.0e-100);
    }
}
~~~

Kết quả theo nguyên tắc:

| Giá trị nguồn | Có khớp `float`? | Lý do |
|---|---|---|
| `0.5d` | Có | Biểu diễn chính xác trong binary32 |
| `0.1d` | Không | Giá trị double không bằng chính xác giá trị float sau làm tròn |
| `1.0e100` | Không | Chuyển sang float sẽ thành dương vô cực |
| `1.0e-100` | Không | Chuyển sang float sẽ underflow thành 0 |

Không nên đánh giá exactness bằng cách nhìn số chữ số thập phân in ra. So sánh phải dựa trên giá trị nhị phân thực tế theo quy tắc của JLS.

## 5. NaN, vô cực và signed zero

IEEE 754 có các giá trị đặc biệt mà phép cast thông thường xử lý theo quy tắc riêng. Primitive type pattern áp dụng kiểm tra exactness nên không chấp nhận những phép chuyển đổi làm mất thông tin.

### 5.1. NaN sang kiểu nguyên

Khi cast một NaN sang kiểu nguyên, Java cho kết quả 0:

~~~java
int value = (int) Double.NaN;
System.out.println(value); // 0
~~~

Nhưng `NaN` không có giá trị nguyên tương đương. Pattern từ chối phép chuyển đổi:

~~~java
double value = Double.NaN;

if (value instanceof int i) {
    System.out.println("int: " + i);
} else {
    System.out.println("NaN không thể chuyển exact sang int");
}
~~~

Kết quả là nhánh `else`.

### 5.2. NaN giữa hai kiểu floating-point

Khi nguồn và đích đều là kiểu floating-point, JLS coi phép chuyển đổi của NaN là exact. Vì vậy, `double NaN` có thể khớp pattern `float`:

~~~java
double value = Double.NaN;

if (value instanceof float f) {
    System.out.println(Float.isNaN(f)); // true
}
~~~

Điều này không có nghĩa NaN có thể so sánh bằng toán tử `==`. Theo IEEE 754, `NaN == NaN` vẫn là `false`. Hãy dùng `Float.isNaN` hoặc `Double.isNaN` để kiểm tra NaN.

### 5.3. Infinity

| Chuyển đổi | Exact? | Giải thích |
|---|---|---|
| `double +Infinity` sang `float` | Có | Dương vô cực vẫn là dương vô cực |
| `double -Infinity` sang `float` | Có | Âm vô cực vẫn là âm vô cực |
| `double +Infinity` sang `int` | Không | Cast cho `Integer.MAX_VALUE`, mất thông tin |
| `double -Infinity` sang `long` | Không | Cast cho `Long.MIN_VALUE`, mất thông tin |

### 5.4. +0.0 và -0.0

Floating-point phân biệt số dương 0 và âm 0. Chúng so sánh bằng nhau với `==`, nhưng có bit biểu diễn khác nhau và có thể tạo kết quả khác trong một số phép toán.

~~~java
static void inspectZero(double value) {
    if (value instanceof int i) {
        System.out.println("exact int zero: " + i);
    } else {
        System.out.println("Không exact khi chuyển sang int");
    }
}

public static void main(String[] args) {
    inspectZero(+0.0d);
    inspectZero(-0.0d);
}
~~~

- `+0.0d` sang `int 0` là exact.
- `-0.0d` sang `int 0` là inexact vì mất dấu âm.

Nếu cần phân biệt signed zero:

~~~java
static String describe(double value) {
    if (Double.isNaN(value)) {
        return "NaN";
    }
    if (value == 0.0d
            && Double.doubleToRawLongBits(value) == Long.MIN_VALUE) {
        return "negative zero";
    }
    if (value == 0.0d) {
        return "positive zero";
    }
    if (Double.isInfinite(value)) {
        return value > 0 ? "positive infinity" : "negative infinity";
    }
    return "finite non-zero";
}
~~~

Không dùng `value == 0.0d` một mình để kết luận đó là dương 0, vì cả `+0.0` và `-0.0` đều cho kết quả `true`.

## 6. Kiểm tra null khi có boxing và unboxing

Primitive type pattern có thể tham gia các phép chuyển đổi giữa primitive và wrapper reference. Cần phân biệt hai hướng:

- **Boxing:** chuyển primitive thành wrapper tương ứng, ví dụ `int` thành `Integer`.
- **Unboxing:** lấy primitive từ wrapper, ví dụ `Integer` thành `int`.

### 6.1. Boxing từ primitive sang wrapper

Một primitive có thể được box sang wrapper tương ứng. Ví dụ:

~~~java
int value = 42;

if (value instanceof Integer boxed) {
    System.out.println(boxed); // 42
}

if (value instanceof Number number) {
    System.out.println(number.getClass().getSimpleName()); // Integer
}
~~~

Pattern `Integer boxed` khớp vì boxing `int` tạo ra `Integer`. Pattern `Number number` cũng khớp vì sau boxing, `Integer` có thể widening reference conversion sang `Number`.

Boxing không tự chuyển `int` thành `Long`. Việc đổi primitive type rồi mới boxing là một chuỗi chuyển đổi khác; không được suy luận rằng `int` có thể match mọi wrapper chứa kiểu số tương thích.

### 6.2. Unboxing từ wrapper sang primitive

Khi kiểm tra wrapper bằng primitive pattern, runtime có thể thực hiện unboxing. Với wrapper có giá trị hợp lệ:

~~~java
Integer boxed = Integer.valueOf(42);

if (boxed instanceof int value) {
    System.out.println("int: " + value);
}
~~~

Pattern khớp vì unboxing `Integer` thành `int` không mất thông tin và không ném exception.

Nếu nguồn là một reference tổng quát như `Object` hoặc `Number`, testing conversion còn phải kiểm tra object thực tế có phải wrapper phù hợp hay không:

~~~java
static void inspectNumber(Number value) {
    if (value instanceof int i) {
        System.out.println("Integer được unbox: " + i);
    } else {
        System.out.println("Không phải Integer có thể unbox thành int");
    }
}
~~~

Với `Number` đang tham chiếu tới `Integer`, pattern `int i` có thể khớp. Nếu object thực tế là `Double` hoặc `Long`, phép kiểm tra kiểu wrapper tương ứng không thành công. Pattern không tự chuyển mọi loại `Number` sang `int`.

### 6.3. Wrapper null không làm pattern ném NullPointerException

Unboxing trực tiếp một wrapper null sẽ ném `NullPointerException`:

~~~java
Integer boxed = null;
int value = boxed; // NullPointerException
~~~

Trong testing context của pattern matching, nếu unboxing ném exception thì phép chuyển đổi được xem là inexact và không được chấp nhận. Do đó:

~~~java
Integer boxed = null;

if (boxed instanceof int value) {
    System.out.println("int: " + value);
} else {
    System.out.println("Không có giá trị Integer để unbox");
}
~~~

Kết quả là nhánh `else`; pattern không làm `NullPointerException` thoát ra.

Quy tắc này áp dụng cho phép kiểm tra pattern. Nó không thay đổi hành vi unboxing thông thường ở phép gán, phép toán hoặc lời gọi method.

### 6.4. null không phải là một primitive value

Một reference `null` không thuộc miền giá trị của bất kỳ primitive type nào. Vì vậy:

- `null instanceof int i` không khớp.
- `null instanceof double d` không khớp.
- `null instanceof Integer i` cũng không khớp với type pattern thông thường.
- Nếu cần xử lý null trong `switch` có selector là reference type, phải khai báo `case null`.

Ví dụ:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case int i -> "Integer unboxed exact: " + i;
        default -> "Giá trị khác";
    };
}
~~~

Nếu bỏ `case null` và selector là null, switch sẽ ném `NullPointerException` như quy tắc switch hiện hành. Primitive type pattern không thay thế nhãn `case null`.

## 7. Phân biệt pattern với kiểm tra wrapper class thông thường

Một lỗi thiết kế là cho rằng primitive pattern thực hiện chuyển đổi số học giữa các wrapper. Thực tế, pattern kiểm tra một testing conversion được JLS cho phép.

| Giá trị runtime | Pattern | Kết quả | Lý do |
|---|---|---|---|
| `Integer.valueOf(42)` | `int i` | Khớp | Unbox Integer thành int |
| `Integer.valueOf(42)` | `long l` | Có thể khớp khi static source type cho phép unboxing rồi widening | int có thể widening exact sang long |
| `Long.valueOf(42L)` | `int i` | Không khớp qua chuyển đổi wrapper | Không có phép unbox Long rồi narrowing sang int trong testing conversion này |
| `Double.valueOf(42.0)` | `int i` | Không khớp qua chuyển đổi wrapper | Không tự unbox double rồi narrowing sang int |
| `Integer.valueOf(1000)` | `byte b` | Không khớp nếu nguồn primitive int phải narrowing ngoài miền | 1000 không biểu diễn được bằng byte |
| `null` | `int i` | Không khớp | Unboxing null là inexact |

Khi làm việc với reference có static type `Number` hoặc `Object`, kiểm tra conversion còn có thể gồm checked narrowing reference conversion tới wrapper phù hợp. Do đó, cần xét cả **static type của expression** và **runtime class của object**, không chỉ nhìn giá trị số được in ra.

## 8. Dùng switch để phân loại giá trị theo conversion safety

Primitive type patterns cũng có thể dùng trong `switch`. Ví dụ sau nhận một `double`, rồi thử xem giá trị có thể được biểu diễn exact bằng `float` hay không:

~~~java
static String classifyDoubleAsFloat(double value) {
    return switch (value) {
        case float f -> "Có thể biểu diễn exact bằng float: " + f;
        default -> "Chuyển sang float sẽ làm mất thông tin";
    };
}
~~~

Pattern `float f` chỉ khớp nếu phép chuyển `double` sang `float` là exact. Các giá trị như `0.5d`, NaN, vô cực và signed zero có thể khớp theo quy tắc exactness tương ứng; một giá trị như `0.1d` thường không khớp vì giá trị double không được biểu diễn chính xác bằng float.

### 8.1. Guard để phân loại NaN và infinity

Có thể dùng `when` để kiểm tra giá trị sau khi đã khớp primitive type pattern:

~~~java
static String describe(double value) {
    return switch (value) {
        case double d when Double.isNaN(d) -> "NaN";
        case double d when Double.isInfinite(d) ->
                d > 0 ? "positive infinity" : "negative infinity";
        case double d when d == 0.0d
                && Double.doubleToRawLongBits(d) == Long.MIN_VALUE ->
                "negative zero";
        case double d when d == 0.0d -> "positive zero";
        default -> "finite non-zero";
    };
}
~~~

Ví dụ này dùng pattern `double d` cùng guard để phân loại giá trị. Pattern `double d` là cùng kiểu với selector nên phép chuyển đổi không mất thông tin; guard mới quyết định nhánh cụ thể.

### 8.2. Thứ tự và dominance của switch labels

Compiler kiểm tra một nhãn có bị nhãn đứng trước bao phủ hay không (dominance). Một pattern có thể unconditional đối với kiểu của pattern khác nếu phép chuyển đổi luôn exact.

Ví dụ, với selector `float`, mọi giá trị `float` đều có thể chuyển exact sang `double`. Vì vậy, `case double d` có thể bao phủ các pattern phía sau mà nó luôn match. Đừng đặt một pattern rộng/unconditional trước các nhãn cần xử lý riêng.

Trong các bản preview JDK 26 và JDK 27, quy tắc unconditional exactness và dominance đã được tinh chỉnh. Hãy biên dịch bằng đúng JDK đích và đọc lỗi compiler thay vì sao chép thứ tự case từ một bản preview cũ.

## 9. Cách biên dịch và chạy theo JDK

Primitive type patterns vẫn là preview trong JDK 27. Preview feature phải được bật ở cả compiler và runtime.

### 9.1. Dùng JDK 27 hiện hành

~~~bash
javac --enable-preview --release 27 PrimitivePatternDemo.java
java --enable-preview PrimitivePatternDemo
~~~

### 9.2. Thử trên JDK 25

JDK 25 dùng JEP 507 (Third Preview). Cần dùng compiler và runtime JDK 25:

~~~bash
javac --enable-preview --release 25 PrimitivePatternDemo.java
java --enable-preview PrimitivePatternDemo
~~~

Không compile preview bằng JDK 25 rồi mặc định rằng class file đó sẽ chạy như preview feature của JDK 27. Oracle quy định preview code cần được biên dịch và chạy bằng release tương ứng; preview feature của một release cũ không được bảo đảm sẽ tiếp tục compile/run ở release mới.

### 9.3. Lịch sử các lần preview

| Release | JEP | Trạng thái |
|---|---|---|
| JDK 23 | JEP 455 | Preview lần đầu |
| JDK 24 | JEP 488 | Second Preview |
| JDK 25 | JEP 507 | Third Preview |
| JDK 26 | JEP 530 | Fourth Preview; tinh chỉnh unconditional exactness và dominance |
| JDK 27 | JEP 532 | Fifth Preview; không có thay đổi ngữ nghĩa đáng kể theo tài liệu release |

Không viết tài liệu production với giả định cú pháp đã final. Khi feature còn preview, cần kiểm tra JEP và release notes của JDK mà dự án triển khai.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `int instanceof byte b` không khớp với giá trị 1000 | Narrowing conversion làm mất thông tin | Kiểm tra miền `byte` hoặc xử lý nhánh không khớp |
| `int instanceof float f` không khớp ở một số giá trị lớn | Widening sang float có thể mất precision | Dùng pattern để chỉ nhận giá trị exact |
| `double instanceof int i` không khớp với 12.5 | Phần thập phân bị loại bỏ nếu cast | Không dùng cast nếu nghiệp vụ yêu cầu giữ nguyên giá trị |
| NaN không match `int` | NaN sang integer tạo 0 và mất thông tin | Kiểm tra NaN riêng bằng `Double.isNaN` |
| NaN match `float` từ `double` | NaN giữa hai kiểu floating-point được xem là exact | Dùng `isNaN` để phân biệt với số hữu hạn |
| `-0.0` không match `int` | Chuyển sang 0 làm mất dấu âm | Dùng `doubleToRawLongBits` nếu cần phân biệt |
| `Integer null` không match `int` | Unboxing null sẽ ném exception, nên testing conversion inexact | Kiểm tra null hoặc dùng nhánh không khớp |
| `switch(null)` ném NPE | Không có `case null` cho reference selector | Thêm `case null` khi null là input hợp lệ |
| `Long` không match `int` dù giá trị nhỏ | Wrapper không tự chuyển qua wrapper số khác | Kiểm tra đúng wrapper và chuyển đổi được phép |
| Compile error vì preview disabled | Chưa bật preview ở compiler/runtime | Dùng `--enable-preview` với đúng JDK release |
| Switch báo dominated label | Pattern trước unconditional hoặc bao phủ pattern sau | Sắp xếp case và kiểm tra exactness/dominance |
| Preview code cũ không compile ở JDK mới | Quy tắc preview đã thay đổi | Dùng code phù hợp JEP của release đích |

## 11. Ma trận kiểm thử giá trị biên

Dùng ma trận này để kiểm tra chương trình xử lý số, parser, API nhận dữ liệu và các lớp chuyển đổi:

| Mã | Giá trị nguồn | Pattern đích | Kết quả mong đợi |
|---|---|---|---|
| P1 | `int -128` | `byte b` | Khớp |
| P2 | `int 127` | `byte b` | Khớp |
| P3 | `int -129` | `byte b` | Không khớp |
| P4 | `int 128` | `byte b` | Không khớp |
| P5 | `int 65535` | `char c` | Khớp |
| P6 | `int -1` | `char c` | Không khớp |
| P7 | `int 16_777_216` | `float f` | Khớp |
| P8 | `int 16_777_217` | `float f` | Không khớp |
| P9 | `long 2^53` | `double d` | Khớp |
| P10 | `long 2^53 + 1` | `double d` | Không khớp |
| P11 | `double 0.5` | `float f` | Khớp |
| P12 | `double 0.1` | `float f` | Không khớp |
| P13 | `double NaN` | `int i` | Không khớp |
| P14 | `double NaN` | `float f` | Khớp |
| P15 | `double +Infinity` | `float f` | Khớp |
| P16 | `double +Infinity` | `int i` | Không khớp |
| P17 | `double +0.0` | `int i` | Khớp |
| P18 | `double -0.0` | `int i` | Không khớp |
| P19 | `Integer.valueOf(42)` | `int i` | Khớp |
| P20 | `Integer null` | `int i` | Không khớp, không ném NPE |

Các kết quả trên mô tả exactness của testing conversion. Với switch, còn cần kiểm tra tính exhaustive và dominance của toàn bộ tập nhãn.

## 12. Bài thực hành tổng hợp

Xây dựng một lớp `SafeNumericClassifier` nhận dữ liệu số từ API có thể chứa primitive, wrapper, NaN, vô cực hoặc null.

Thực hiện:

1. Viết method nhận `int` và thử pattern `byte`, `short`, `char`.
2. Kiểm tra các giá trị sát biên của từng kiểu đích.
3. Viết method nhận `long` và thử pattern `double`; kiểm tra \(2^{53}-1\), \(2^{53}\), \(2^{53}+1\), \(2^{53}+2\).
4. Viết method nhận `double` và thử pattern `float`, `int`, `long`.
5. Phân biệt `NaN`, positive/negative infinity, positive/negative zero.
6. Nhận `Number` và kiểm tra pattern `int`; thử lần lượt `Integer`, `Long`, `Double` và null.
7. Nhận `Object` và viết switch có `case null`, primitive pattern và `default`.
8. So sánh kết quả pattern với cast thông thường để nhận diện các trường hợp cast làm mất dữ liệu.
9. Biên dịch và chạy bằng JDK 27 preview; nếu cần hỗ trợ JDK 25, chạy riêng bằng JDK 25 preview.
10. Viết test cho toàn bộ ma trận P1–P20.

**Sản phẩm nghiệm thu:** mã nguồn classifier, bảng kết quả P1–P20, lệnh compile/run theo JDK, giải thích vì sao từng giá trị khớp hoặc không khớp và một báo cáo ngắn về các trường hợp null/NaN/signed zero.

## 13. Checklist khi dùng primitive type patterns

- Kiểm tra feature đang ở preview hay permanent trong JDK đích.
- Dùng compiler và runtime cùng release khi bật preview.
- Hiểu rõ static type của expression và runtime type của wrapper.
- Kiểm tra miền giá trị trước khi chuyển kiểu hẹp.
- Không giả định widening sang floating-point luôn exact.
- Dùng primitive pattern thay cho cast khi muốn kiểm tra an toàn trước khi sử dụng giá trị.
- Nhớ NaN/infinity không chuyển exact sang integer.
- Nhớ negative zero mất dấu khi chuyển sang integer.
- Dùng `Double.isNaN`/`Float.isNaN`, không dùng `==` để phát hiện NaN.
- Phân biệt boxing với unboxing; wrapper null không match primitive pattern.
- Thêm `case null` cho switch có reference selector nếu null là input hợp lệ.
- Kiểm tra switch dominance và exhaustiveness bằng compiler của release đích.
- Không dùng kết quả preview làm cam kết tương thích lâu dài khi chưa final.

## Tài liệu tham khảo chính thức

- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532): trạng thái preview hiện hành trong JDK 27.
- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530): thay đổi trong JDK 26 về unconditional exactness và dominance.
- [JEP 507 — Primitive Types in Patterns, instanceof, and switch (Third Preview)](https://openjdk.org/jeps/507): phiên bản preview của JDK 25.
- [JEP 455 — Primitive Types in Patterns, instanceof, and switch](https://openjdk.org/jeps/455): lần preview đầu tiên trong JDK 23.
- [Oracle Java SE 27 — Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html): tổng quan các ngữ cảnh pattern, instanceof và switch.
- [Oracle Java SE 27 — Type Patterns](https://docs.oracle.com/en/java/javase/27/language/type-patterns.html): ví dụ primitive type patterns và giá trị floating-point.
- [Oracle Java SE 27 — Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/27/language/safe-casting-instanceof-switch.html): cách kiểm tra chuyển đổi an toàn và ví dụ giá trị biên.
- [Java Language Specification, Java SE 27 — Fifth Preview specification](https://docs.oracle.com/javase/specs/jls/se27/preview/specs/primitive-types-in-patterns-instanceof-switch-jls.html): testing contexts, exactness, NaN, signed zero, null và pattern matching.
- [Oracle Java SE 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): cách bật preview khi compile và run.
- [Oracle Java SE 25 — Type Patterns](https://docs.oracle.com/en/java/javase/25/language/type-patterns.html): ví dụ và trạng thái JEP 507 trong JDK 25.
- [Oracle Java SE 25 — Primitive Types in Patterns, instanceof, and switch (Third Preview JLS)](https://docs.oracle.com/en/java/javase/25/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html): đặc tả preview đúng release Java 25.

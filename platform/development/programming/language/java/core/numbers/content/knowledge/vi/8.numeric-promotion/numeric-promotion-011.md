# Số trong switch và giới hạn theo phiên bản ngôn ngữ (Java)

## 1. Mục tiêu

Bài này tập trung vào **kiểu của biểu thức điều kiện trong `switch`**, những kiểu số được Java hỗ trợ ở từng phiên bản, và tác động của **nâng kiểu số (numeric promotion)** lên tính hợp lệ của `switch`/`case`. Sau bài học, bạn có thể:

- Chọn kiểu `byte`, `short`, `char`, `int` hoặc lớp bọc tương ứng cho `switch` ổn định trên Java 17.
- Giải thích vì sao `byte + byte` tạo `int`, vì sao `case` phải là hằng hợp lệ và tại sao `long`/`double` không được dùng trực tiếp làm selector trên Java 17/21.
- Phân biệt `switch` statement và expression, kể cả quy tắc `break`, `yield` và tính đầy đủ của các nhánh.
- Đọc đúng giới hạn lịch sử: `String`/`enum`, pattern matching từ Java 21 và mở rộng selector primitive ở các bản Java 23–27 dưới dạng **preview**.
- Tránh ép kiểu làm tràn hoặc mất độ chính xác chỉ để dùng `switch`.

**Phạm vi mã chạy chính:** Java 17 trở lên, không cần preview. Những ví dụ dùng tính năng của Java 21 hoặc preview Java 27 được ghi rõ và tách riêng.

## 2. Selector là gì? Những kiểu được chấp nhận trên Java 17

Trong `switch (expression) { ... }`, `expression` gọi là **selector**. Trước khi xét các nhánh `case`, trình biên dịch kiểm tra *kiểu của toàn bộ biểu thức selector*. Nó không chỉ nhìn kiểu của một biến xuất hiện bên trong biểu thức.

Với Java 17 và các bản Java 21 ở phần switch số nguyên cổ điển, các selector số primitive được hỗ trợ ổn định là:

| Selector | Java 17 | Ghi chú |
| --- | --- | --- |
| `byte` | Có | Giá trị −128..127 |
| `short` | Có | Giá trị −32768..32767 |
| `char` | Có | Giá trị 0..65535 |
| `int` | Có | Giá trị −2³¹..2³¹−1 |
| `Byte`, `Short`, `Character`, `Integer` | Có | Lớp bọc được xử lý qua unboxing; `null` có thể gây `NullPointerException` |
| `long` | Không | Kể cả literal `1L` và kết quả `int + long` |
| `float`, `double` | Không | Không được mặc định làm tròn để so khớp `case` |
| `boolean` | Không | Không phải selector của `switch` số nguyên cổ điển |

`enum` cũng được hỗ trợ kể từ Java 5, `String` kể từ Java 7, nhưng chúng không phải kiểu số. Java 21 còn hỗ trợ **selector có kiểu tham chiếu** khi sử dụng pattern matching cho `switch`; chi tiết ở phần 9. Bản Java 27 có tính năng **preview** cho primitive selector rộng hơn; xem phần 10.

Ví dụ hợp lệ trên Java 17:

~~~java
byte b = 2;
short s = 300;
char c = 'A';
int i = 10;
Integer boxed = 2;

String a = switch (b) { case 2 -> "byte"; default -> "?"; };
String d = switch (s) { case 300 -> "short"; default -> "?"; };
String e = switch (c) { case 'A' -> "char"; default -> "?"; };
String f = switch (i) { case 10 -> "int"; default -> "?"; };
String g = switch (boxed) { case 2 -> "Integer"; default -> "?"; };
~~~

Đây là các câu lệnh minh họa *bên trong một phương thức*. Chúng không khai báo chương trình Java hoàn chỉnh; chương trình đầy đủ có tại phần 8.

## 3. Nâng kiểu biểu thức: byte + byte không còn là byte

Java áp dụng **binary numeric promotion** cho nhiều toán tử số học, bao gồm `+`, `-`, `*`, `/`, `%`. Khi cả hai toán hạng là `byte`, `short` hoặc `char`, chúng thường được nâng lên `int` trước khi phép toán diễn ra; kết quả có kiểu `int`.

~~~java
byte left = 4;
byte right = 3;

int sum = left + right;      // kiểu của (left + right) là int
// byte impossible = left + right; // lỗi biên dịch: int không tự thu hẹp thành byte

String text = switch (left + right) {
    case 7 -> "seven";
    default -> "other";
};
System.out.println(text); // seven
~~~

`switch (left + right)` **hợp lệ**, vì selector có kiểu `int`, cũng là kiểu được Java 17 hỗ trợ. Không cần ép về `byte` để dùng `switch`.

Nếu một toán hạng là `long`, biểu thức cộng sẽ được nâng lên `long` (trừ trường hợp có `float`/`double` với cấp cao hơn) và không dùng trực tiếp làm selector Java 17:

~~~java
int count = 2;
long offset = 1L;

// Không biên dịch trên Java 17 hoặc Java 21:
// switch (count + offset) {
//     case 3L -> System.out.println("three");
// }
~~~

Cùng logic đó, `switch (a * b)` với `int` hay `byte` được chấp nhận về *kiểu*, nhưng phép toán có thể **tràn** theo số học Java trước khi so khớp `case`. Chỉ vì selector hợp lệ không có nghĩa giá trị tính toán nằm trong miền dự kiến.

### Toán tử một ngôi và chuyển đổi tự động

`+b`, `-b` và `~b` với `b` kiểu `byte` cũng có kết quả `int` (unary numeric promotion):

~~~java
byte b = 1;
int negated = -b;
int inverted = ~b;

System.out.println(negated); // -1
System.out.println(inverted); // -2
~~~

Điều cần xem khi viết `switch` là **kiểu tĩnh sau khi áp dụng các quy tắc biểu thức**, không phải trực giác từ kiểu khai báo của toán hạng ban đầu.

## 4. Case phải là hằng hợp lệ và nằm trong miền kiểu selector

Trong `switch` hằng số truyền thống (Java 17), `case` cho selector số nguyên phải là **biểu thức hằng tại thời điểm biên dịch** và phải tương thích gán với kiểu selector; một hằng `int` được phép thu hẹp sang `byte`, `short` hoặc `char` khi giá trị nằm trong miền có thể biểu diễn.

~~~java
byte level = 100;
final int FIRST = 50;    // compile-time constant variable
final int SECOND = 50 + 50;

String category = switch (level) {
    case FIRST -> "first";
    case SECOND -> "second";
    default -> "other";
};
System.out.println(category); // second
~~~

`FIRST`/`SECOND` là `final int` được gán bằng biểu thức hằng. Chúng vẫn dùng được với `byte` vì 50 và 100 nằm trong khoảng −128..127.

Ngược lại:

~~~java
byte b = 1;

// Không biên dịch Java 17:
// String x = switch (b) {
//     case 128 -> "too large"; // 128 không biểu diễn được bởi byte
//     default -> "other";
// };

// Không biên dịch Java 17:
// int dynamic = Integer.parseInt("1");
// String y = switch (b) {
//     case dynamic -> "one";    // dynamic không phải compile-time constant
//     default -> "other";
// };
~~~

Các hằng số có cùng giá trị không được lặp lại giữa các nhánh của cùng một `switch`:

~~~java
int n = 2;

// Không biên dịch: trùng giá trị case
// switch (n) {
//     case 2 -> System.out.println("two");
//     case 1 + 1 -> System.out.println("also two");
//     default -> System.out.println("other");
// }
~~~

`case 1 + 1` là một biểu thức hằng **có giá trị 2** nên trùng `case 2`. Lỗi này được phát hiện lúc biên dịch.

### Khác biệt giữa kiểu hằng và kiểu giá trị runtime

Một biến `int` thường, dù có giá trị 7 lúc chạy, không trở thành hằng `case`. `final` cũng chưa đủ nếu giá trị được tính bằng lời gọi phương thức. Ví dụ `final int x = Integer.parseInt("7")` vẫn **không** phải *constant variable* theo đặc tả Java.

Khi cần phân loại theo phạm vi động (ví dụ `n >= min && n <= max`), dùng `if/else` trên Java 17, hoặc pattern/guard khi dùng Java 21+ đúng ngữ cảnh. Không nên cố nhồi điều kiện runtime vào nhãn `case` hằng số.

## 5. Char là số nguyên không dấu 16 bit, nhưng case có quy tắc miền giá trị

`char` có thể xuất hiện trong `switch` và đại diện một đơn vị mã UTF-16 từ 0 đến 65535. Một hằng ký tự như `'A'` có giá trị 65; Java cho phép viết `case 'A'` hoặc `case 65` khi selector là `char`:

~~~java
char letter = 'A';

String result = switch (letter) {
    case 65 -> "Latin capital A";
    default -> "another code unit";
};
System.out.println(result); // Latin capital A
~~~

Nhưng `case -1` hoặc `case 65536` không hợp lệ cho selector `char`: các hằng đó ngoài miền 0..65535.

`char` không biểu diễn mọi ký tự Unicode thành **một** giá trị duy nhất: ký tự bổ sung nằm ngoài BMP dùng cặp surrogate UTF-16. Nếu yêu cầu phân loại **code point** Unicode, hãy lấy giá trị `int` code point (ví dụ `String.codePointAt(...)`), rồi dùng `switch (intCodePoint)`. Không nên coi mọi ký tự Unicode đều là một `char`.

## 6. Switch statement, switch expression và các nhánh số

### Statement với dấu hai chấm (cú pháp truyền thống)

~~~java
int code = 2;
switch (code) {
    case 1:
        System.out.println("one");
        break;
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
~~~

Đoạn trên in `two`. Với dạng `case ...:`, nếu thiếu `break`, luồng chạy có thể **fall through** sang các nhánh tiếp theo. Đây là hành vi của câu lệnh, không liên quan đến tự động chuyển đổi kiểu số.

### Switch rule với mũi tên

Từ Java 14, dạng `case ... ->` là cú pháp ổn định; không fall through:

~~~java
int code = 2;
switch (code) {
    case 1 -> System.out.println("one");
    case 2, 3 -> System.out.println("two or three");
    default -> System.out.println("other");
}
~~~

Dạng này in `two or three`. Trong **switch statement**, biểu thức ngay sau mũi tên phải là statement expression, khối lệnh hoặc `throw`; không thể viết bừa một biểu thức số không có tác dụng và coi nó là câu lệnh hợp lệ.

### Switch expression tạo ra giá trị

`switch` **expression** là tính năng chuẩn từ Java 14. Nó phải tạo ra một giá trị cho mọi khả năng có thể đi đến nhánh và cần **exhaustive**; với selector `int` thường thêm `default`.

~~~java
int level = 3;

int score = switch (level) {
    case 1, 2 -> 10;
    case 3 -> {
        int bonus = 5;
        yield 20 + bonus; // 25
    }
    default -> 0;
};

System.out.println(score); // 25
~~~

Trong khối `case 3 -> { ... }`, từ khóa `yield` chuyển **giá trị kết quả của switch expression** ra ngoài. `break` trong switch statement truyền thống chỉ thoát khỏi câu lệnh; không dùng `break value` để trả giá trị trong cú pháp Java 17. 

Ngoài ra, **kiểu của kết quả switch expression** là vấn đề riêng so với **kiểu của selector**. Các nhánh trả kết quả phải tương thích với ngữ cảnh gán/return; đừng suy rằng vì selector là `byte` nên kết quả luôn có kiểu `byte`.

## 7. Wrapper, unboxing, null và giới hạn của kiểu Number

Java 17 hỗ trợ `Byte`, `Short`, `Character` và `Integer` làm selector bằng cách unbox. Giá trị trong wrapper hợp lệ, nhưng **đối tượng null không thể unbox**.

~~~java
Integer status = Integer.valueOf(2);
String message = switch (status) {
    case 1 -> "created";
    case 2 -> "accepted";
    default -> "unknown";
};
System.out.println(message); // accepted
~~~

Nếu `status = null`, `switch (status)` theo dạng hằng số Java 17 sẽ ném `NullPointerException` trước khi chọn nhánh. `default` **không** phải cơ chế xử lý `null`.

`Long`, `Float`, `Double` và `Number` **không** phải selector cho switch theo hằng số truyền thống của Java 17. Ví dụ:

~~~java
Number numeric = Integer.valueOf(2);
// Không biên dịch trên Java 17:
// switch (numeric) {
//     case 2 -> System.out.println("two");
// }
~~~

Nếu hợp đồng API bảo đảm đầu vào đúng `Integer`, có thể lấy `numeric.intValue()` sau khi xác nhận kiểu/miền; nhưng nếu `numeric` là `Long` rất lớn hoặc `BigDecimal` có phần lẻ, `intValue()` có thể làm mất dữ liệu. Trường hợp tổng quát nên dùng cách phân loại khác hoặc tận dụng pattern matching trên Java 21+.

## 8. Chương trình Java 17+ hoàn chỉnh và output

Lưu thành tệp `NumericSwitchDemo.java`:

~~~java
public class NumericSwitchDemo {
    private static String byteLabel(byte code) {
        return switch (code) {
            case -1 -> "sentinel";
            case 0 -> "zero";
            case 127 -> "maximum byte";
            default -> "other";
        };
    }

    private static int score(int code) {
        return switch (code) {
            case 1, 2 -> 10;
            case 3 -> {
                int base = 20;
                yield base + 5;
            }
            default -> 0;
        };
    }

    public static void main(String[] args) {
        byte left = 4;
        byte right = 3;
        int sum = left + right; // binary numeric promotion: byte + byte -> int

        String sumLabel = switch (sum) {
            case 7 -> "seven";
            default -> "other";
        };
        System.out.println("sum=" + sum + ", label=" + sumLabel);

        System.out.println("byte -1=" + byteLabel((byte) -1));

        char letter = 'A';
        String charLabel = switch (letter) {
            case 65 -> "capital A";
            default -> "other";
        };
        System.out.println("char A=" + charLabel);

        Integer boxed = 2;
        System.out.println("boxed 2 score=" + score(boxed));

        System.out.println("code 3 score=" + score(3));

        long outsideInt = 2_147_483_648L;
        try {
            int exact = Math.toIntExact(outsideInt);
            System.out.println("exact=" + exact);
        } catch (ArithmeticException ex) {
            System.out.println("outside int range");
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 NumericSwitchDemo.java
java NumericSwitchDemo
~~~

Stdout chính xác:

~~~text
sum=7, label=seven
byte -1=sentinel
char A=capital A
boxed 2 score=10
code 3 score=25
outside int range
~~~

Giải thích:

1. `left + right` có kiểu `int`, nên `switch (sum)` hợp lệ.
2. `byteLabel((byte) -1)` so khớp `case -1` hợp lệ trong miền `byte`.
3. Selector `char` so khớp hằng số nguyên `65` vì giá trị có thể biểu diễn bởi `char`.
4. `Integer boxed` tự unbox thành `int` khi truyền cho `score(int)`; giá trị 2 nhận 10 điểm.
5. Nhánh `case 3` dùng `yield` để trả 25 điểm.
6. `Math.toIntExact` phát hiện 2.147.483.648 vượt miền `int`. Không có phép ép ngầm nguy hiểm từ `long` xuống `int`.

## 9. Hạn chế theo phiên bản: Java 21 mở rộng switch theo kiểu tham chiếu

**Java 21** đưa *pattern matching for switch* thành tính năng chuẩn. Điều này mở rộng `switch` cho các **kiểu tham chiếu** như `Object`, `Number` hoặc `Long` khi dùng pattern hợp lệ trong `case`. Nó **không** làm cho `long`, `float`, `double`, `boolean` dạng primitive trở thành selector hợp lệ trực tiếp trong Java 21.

Ví dụ dưới đây yêu cầu JDK 21+, không dùng preview:

~~~java
public class ReferenceNumberSwitch {
    static String describe(Number value) {
        return switch (value) {
            case null -> "missing";
            case Integer i -> "int " + i;
            case Long l -> "long " + l;
            default -> "other number";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Long.valueOf(42)));
        System.out.println(describe(null));
        System.out.println(describe(Double.valueOf(1.5)));
    }
}
~~~

Biên dịch/chạy bằng JDK 21 hoặc mới hơn:

~~~bash
javac --release 21 ReferenceNumberSwitch.java
java ReferenceNumberSwitch
~~~

Stdout:

~~~text
long 42
missing
other number
~~~

`case Long l` là **type pattern** áp dụng cho một đối tượng `Long`, không phải hằng `case 42L` cho primitive `long`. `case null` xuất hiện trong switch pattern hiện đại, cho phép xử lý null có chủ đích; Java 17 ổn định không hỗ trợ cùng cú pháp đó. Phân biệt **selector tham chiếu `Long`** với **selector primitive `long`** là then chốt khi đọc code đa phiên bản.

Trong Java 21, có thể thêm guard `when`:

~~~java
static String classify(Number n) {
    return switch (n) {
        case null -> "missing";
        case Integer i when i > 0 -> "positive int";
        case Integer i -> "other int";
        default -> "other number";
    };
}
~~~

Đây là một *phương thức minh họa* dành cho Java 21+, chưa phải chương trình độc lập. Guard là điều kiện runtime của **pattern case**, khác với yêu cầu nhãn `case` số truyền thống phải là hằng tại thời điểm biên dịch.

## 10. Từ Java 23 đến Java 27: các selector primitive mới đang ở preview

Lịch sử phát triển quan trọng:

| Phiên bản | Thay đổi đáng nhớ |
| --- | --- |
| Java 1.0 | `switch` trên `byte`, `short`, `char`, `int` |
| Java 5 | Thêm enum và các wrapper `Byte`, `Short`, `Character`, `Integer` |
| Java 7 | `String` làm selector |
| Java 12–13 | `switch expression` và rule `->` thử nghiệm (preview) |
| Java 14 | `switch expression` và rule `->` trở thành chuẩn |
| Java 17 | Các kiểu selector số truyền thống vẫn giới hạn đến `int`; pattern switch chỉ là preview, không phải cú pháp chuẩn |
| Java 21 | Pattern matching cho `switch` trở thành chuẩn; mở rộng selector sang kiểu tham chiếu |
| Java 23 | *Primitive Types in Patterns, instanceof, and switch*: preview lần đầu |
| Java 24 | Preview lần hai |
| Java 25 | Preview lần ba (JEP 507) |
| Java 26 | Preview lần bốn (JEP 530) |
| Java 27 | Preview lần năm (JEP 532); **chưa phải tính năng ngôn ngữ chuẩn** |

Trong phiên bản Java 27 có bật preview, phạm vi selector primitive được mở rộng, bao gồm `long` và các kiểu primitive trước đó không dùng trực tiếp được. Ví dụ **chỉ dành cho JDK 27 preview**:

~~~java
public class PreviewLongSwitch {
    public static void main(String[] args) {
        long amount = 5_000_000_000L;
        String label = switch (amount) {
            case 0L -> "zero";
            case 5_000_000_000L -> "five billion";
            default -> "other";
        };
        System.out.println(label);
    }
}
~~~

Chỉ khi môi trường đã cài đúng **JDK 27** có hỗ trợ tính năng preview tương ứng, biên dịch/chạy bằng:

~~~bash
javac --enable-preview --release 27 PreviewLongSwitch.java
java --enable-preview PreviewLongSwitch
~~~

Dự kiến stdout:

~~~text
five billion
~~~

**Không** dùng ví dụ preview làm bằng chứng rằng `switch (long)` chạy được dưới `--release 17` hoặc `--release 21`. Preview phụ thuộc **đúng phiên bản JDK và cờ biên dịch/chạy**; hành vi/cú pháp có thể thay đổi hoặc chưa bao giờ trở thành tính năng chuẩn. Đối với module Java 17 hoặc hệ thống cần chạy lâu dài, nên giữ các ví dụ chính ở phạm vi `switch` ổn định.

## 11. Cách giải quyết khi đầu vào thật sự là long, double hoặc số lớn

### 11.1. long nhưng miền giá trị chắc chắn thuộc int

Nếu dữ liệu luôn nằm trong miền `int`, hãy **kiểm tra** trước khi chuyển:

~~~java
static String classifyLongSafely(long value) {
    int small = Math.toIntExact(value); // ném ArithmeticException nếu ngoài int
    return switch (small) {
        case 0 -> "zero";
        case 1 -> "one";
        default -> "other int";
    };
}
~~~

Đây là phương thức minh họa cho Java 17. Không dùng ép kiểu mù `(int) value` nếu ngoài miền: ví dụ `(int) 4_294_967_296L` là `0`, dễ bị nhầm thành giá trị `case 0` dù dữ liệu đầu vào khác xa số 0.

### 11.2. long có miền lớn hơn int

Nếu ứng dụng chạy Java 17/21 với primitive `long` tùy ý, có thể dùng `if/else if` trực tiếp:

~~~java
static String classifyLargeLong(long value) {
    if (value == 5_000_000_000L) {
        return "five billion";
    }
    if (value == 0L) {
        return "zero";
    }
    return "other";
}
~~~

Không cần chuyển qua `String` rồi `switch` chỉ để lách kiểm tra kiểu; cách đó dễ tạo chi phí chuyển đổi và có thể làm mờ ý nghĩa dữ liệu. Nếu đã xử lý một giao thức chuỗi hoặc có enum trạng thái, `switch` trên chuỗi/enum có thể phù hợp vì hợp đồng dữ liệu vốn là loại đó.

### 11.3. double và vấn đề độ chính xác

Trên Java 17/21, `switch (double)` không được hỗ trợ. Không dùng ép sang `int` để phân loại số thực khi phần thập phân còn có ý nghĩa: `(int) 2.9` cho 2, khiến 2.9 vô tình trùng nhánh của 2.0.

Nếu dữ liệu là phép đo, chọn logic phạm vi hoặc ngưỡng sai số đã được định nghĩa cho nghiệp vụ:

~~~java
static String temperatureBand(double celsius) {
    if (Double.isNaN(celsius)) {
        return "unknown";
    }
    if (celsius < 0.0) {
        return "freezing";
    }
    if (celsius < 30.0) {
        return "moderate";
    }
    return "hot";
}
~~~

Đây là một phương thức Java 17 minh họa. Ngưỡng chỉ để trình bày kỹ thuật; ứng dụng thực phải đặt giới hạn theo nghiệp vụ. `NaN` cần kiểm tra riêng vì mọi so sánh thứ tự với `NaN` đều false; `+Infinity` ở ví dụ trên đi vào nhánh `hot` và `-Infinity` vào `freezing`, nên hãy quy định chính sách dữ liệu vô hạn nếu đầu vào có thể gặp các giá trị này.

### 11.4. BigInteger, BigDecimal và Number

Các lớp số lớn có thể được so sánh bằng `BigInteger.compareTo`, `BigDecimal.compareTo` hoặc bằng API kiểu miền cụ thể. Với Java 21+, type pattern `switch (Number n)` giúp **phân loại lớp đối tượng**, nhưng không biến một `BigInteger` bất kỳ thành hằng `case 123`. Nếu muốn phân nhánh theo giá trị, hãy kiểm tra/so sánh giá trị hoặc đổi sang kiểu nhỏ hơn **sau khi xác nhận miền và độ chính xác**.

## 12. Lỗi hay gặp

| Cách viết hoặc suy nghĩ | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `switch (byteValue + byteValue2)` luôn là switch của byte | Phép cộng nâng thành `int` | Đọc kiểu của toàn biểu thức; case theo miền `int` |
| `switch (longValue)` trên Java 17 | Lỗi biên dịch selector type | `Math.toIntExact` nếu bảo đảm miền; nếu không dùng `if/else` |
| `switch (doubleValue)` trên Java 17 | Lỗi biên dịch | Dùng điều kiện theo miền, tránh làm mất phần thập phân |
| `case 128` với selector `byte` | Hằng ngoài miền byte | Dùng hằng thuộc miền hoặc đổi mô hình selector |
| `case variable` với biến runtime | Không phải constant expression | Dùng hằng tại compile time; điều kiện động qua `if` hoặc guard ở Java 21+ |
| `case 2` và `case 1 + 1` | Nhãn trùng giá trị | Loại bỏ nhãn trùng |
| `switch ((int) hugeLong)` | Có thể tràn thu hẹp | Kiểm tra bằng `Math.toIntExact` trước |
| `default` sẽ bắt được wrapper null | Java 17 ném `NullPointerException` | Kiểm tra null trước; hoặc `case null` với Java 21+ phù hợp |
| Switch expression chỉ có vài `case` của `int`, không có `default` | Không exhaustive | Thêm `default` hoặc các nhánh đầy đủ |
| Lấy code Java 27 preview dùng với Java 21 | Cú pháp không được hỗ trợ | Dùng API chuẩn của phiên bản mục tiêu |

## 13. Bài tập tự kiểm tra

**Bài 1.** Đoạn sau hợp lệ hay không trên Java 17?

~~~java
byte x = 10, y = 20;
String label = switch (x + y) {
    case 30 -> "thirty";
    default -> "other";
};
~~~

**Đáp án:** Hợp lệ. `x + y` là `int` do binary numeric promotion, và `case 30` là hằng `int` hợp lệ. Giá trị `label` bằng `"thirty"`.

**Bài 2.** Vì sao `case 500` không hợp lệ trong `switch (short s)`?

**Đáp án:** Thực ra **hợp lệ**: 500 nằm trong miền `short`. `case 40000` mới không hợp lệ vì vượt 32767. Cần kiểm tra đúng miền của **kiểu selector**, không suy từ cách viết literal `int`.

**Bài 3.** Vì sao khai báo `final int id = Integer.parseInt("2")` vẫn không cho phép `case id`?

**Đáp án:** `parseInt` là lời gọi phương thức, không phải biểu thức hằng theo Java Language Specification. `final` chỉ ngăn gán lại biến; không tự biến kết quả runtime thành hằng lúc biên dịch.

**Bài 4.** Mã Java 21 `switch (Number n) { case Long l -> ... }` có chứng tỏ `switch (long l)` đã được hỗ trợ không?

**Đáp án:** Không. Trường hợp đầu là **pattern matching theo kiểu tham chiếu** `Long`, còn trường hợp sau dùng **primitive** `long`. Mở rộng selector primitive là một preview riêng ở các JDK mới hơn.

**Bài 5.** Khi có `long value = 4_294_967_296L`, điều gì nguy hiểm trong `switch ((int) value)`?

**Đáp án:** `(int) value` bằng 0 do lấy 32 bit thấp, nên `case 0` có thể khớp sai ý định. Nếu giá trị phải thuộc miền `int`, `Math.toIntExact(value)` sẽ báo lỗi thay vì lặng lẽ đổi thành 0.

## 14. Nguồn tham khảo và điểm cần nhớ

- [Java Language Specification, Java SE 17 — switch statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11) và [switch expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): quy tắc selector, nhãn case, tính exhaustive, kết quả biểu thức.
- [Dev.java — Using preview features](https://dev.java/learn/first-steps/using-preview/): `switch expression` thành tính năng chuẩn trong Java 14.
- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): kiểu tham chiếu và nhánh pattern.
- [Java SE 27 — Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/27/language/primitive-types-patterns-instanceof-switch.html): JEP 532, preview lần năm.

**Ghi nhớ:** Trước hết xét **kiểu tĩnh của selector sau numeric promotion**. Với Java 17, switch số nguyên truyền thống nhận `byte`/`short`/`char`/`int` và bốn wrapper tương ứng; case là hằng compile time tương thích miền. Java 21 mở rộng switch theo **kiểu tham chiếu** bằng pattern, còn mở rộng trực tiếp `switch (long/float/double/boolean)` vẫn là **preview trong Java 27**. Khi ép kiểu để dùng switch, luôn xác minh miền và sự chính xác của giá trị.

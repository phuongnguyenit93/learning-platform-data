# Type pattern với kiểu nguyên thủy

*Tình trạng phiên bản tại ngày 27/11/2026.*

Java 26 mở rộng pattern matching để type pattern có thể khai báo biến thuộc kiểu nguyên thủy như `int`, `double` hoặc `boolean`. Nhờ vậy, `instanceof` và `switch` có thể kiểm tra một giá trị có chuyển đổi chính xác sang kiểu đích hay không, đồng thời gán kết quả vào pattern variable. Tính năng này được đặc tả trong **JEP 530 – Primitive Types in Patterns, instanceof, and switch (Fourth Preview)**.

Đây vẫn là tính năng ngôn ngữ preview của Java 26, không phải cú pháp ổn định của Java SE. Java 27 tiếp tục preview lần thứ năm dưới JEP 532; tài liệu Oracle ghi nhận không có thay đổi ngữ nghĩa đáng kể so với bản Java 26. Vì vậy, cần ghi rõ JDK dùng để biên dịch và chạy mọi ví dụ có primitive type pattern.

## 1. Type pattern nguyên thủy là gì?

Một type pattern gồm một kiểu và một biến mẫu. Khi giá trị khớp với pattern, Java khởi tạo biến mẫu bằng giá trị đã chuyển đổi sang kiểu được khai báo.

Với kiểu tham chiếu, cú pháp quen thuộc là:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Java 26 cho phép dùng kiểu nguyên thủy trong type pattern:

```java
float value = 1000.01f;

if (value instanceof float f) {
    System.out.println("float: " + f);
}

if (value instanceof double d) {
    System.out.println("double: " + d);
}

if (value instanceof int i) {
    System.out.println("int: " + i);
}
```

Kết quả:

```text
float: 1000.01
double: 1000.010009765625
```

Pattern `float f` khớp vì giá trị đã là `float`. Pattern `double d` cũng khớp vì chuyển đổi từ `float` sang `double` bảo toàn chính xác giá trị nhị phân của `float`. Pattern `int i` không khớp vì chuyển đổi từ `float` sang `int` sẽ bỏ phần thập phân.

Lưu ý rằng `1000.01f` đã được làm tròn theo định dạng `float` khi khởi tạo biến. Việc chuyển giá trị `float` đó sang `double` không khôi phục lại số thập phân ban đầu; nó chỉ biểu diễn chính xác giá trị nhị phân mà biến `float` đang lưu.

Các kiểu nguyên thủy có thể xuất hiện trong type pattern gồm:

| Kiểu | Ý nghĩa |
|---|---|
| `boolean` | Giá trị đúng hoặc sai |
| `byte` | Số nguyên có dấu 8 bit |
| `short` | Số nguyên có dấu 16 bit |
| `char` | Ký tự mã UTF-16, giá trị không dấu 16 bit |
| `int` | Số nguyên có dấu 32 bit |
| `long` | Số nguyên có dấu 64 bit |
| `float` | Số thực dấu phẩy động 32 bit |
| `double` | Số thực dấu phẩy động 64 bit |

Type pattern nguyên thủy không phải là kiểm tra lớp runtime của một object như `instanceof String s`. Với giá trị nguyên thủy, Java kiểm tra khả năng chuyển đổi giá trị sang kiểu đích và chỉ khớp khi chuyển đổi đó chính xác.

## 2. Quy tắc khớp: chuyển đổi phải chính xác

Một giá trị khớp với type pattern khi có thể chuyển đổi sang kiểu được khai báo mà không mất thông tin và không phát sinh ngoại lệ. Đây là điểm quan trọng nhất khi dùng primitive type pattern.

Ví dụ với narrowing conversion từ `int` sang `byte`:

```java
static void printByteIfSafe(int value) {
    if (value instanceof byte b) {
        System.out.println("Giá trị byte: " + b);
    } else {
        System.out.println("Ngoài miền byte hoặc không chuyển đổi chính xác");
    }
}

public static void main(String[] args) {
    printByteIfSafe(42);
    printByteIfSafe(2345323);
}
```

Kết quả:

```text
Giá trị byte: 42
Ngoài miền byte hoặc không chuyển đổi chính xác
```

Số `42` biểu diễn được chính xác bằng `byte` nên pattern khớp. Số `2345323` nằm ngoài miền `byte` nên pattern không khớp. Không có phép ép kiểu làm tràn số âm thầm như khi viết `(byte) value`.

Điều này khác với cast thông thường:

```java
int value = 2345323;

byte narrowed = (byte) value;
System.out.println(narrowed); // 107
```

Cast primitive vẫn có thể làm mất thông tin mà không ném `ClassCastException`. Primitive type pattern giúp kiểm tra trước rằng giá trị có thể chuyển đổi chính xác hay không, rồi mới cung cấp biến mẫu đã chuyển đổi.

### Ví dụ với số thực

Một số phép chuyển đổi được phân loại là widening nhưng vẫn có thể mất độ chính xác. Ví dụ `int` sang `float` không bảo toàn chính xác mọi giá trị `int`:

```java
static void checkFloat(int value) {
    if (value instanceof float f) {
        System.out.println("Chuyển đổi chính xác: " + f);
    } else {
        System.out.println("Không thể biểu diễn chính xác bằng float");
    }
}

public static void main(String[] args) {
    checkFloat(1234);
    checkFloat(1234567890);
}
```

Giá trị `1234` có thể biểu diễn chính xác bằng `float` nên khớp. Giá trị `1234567890` không thể được biểu diễn chính xác bằng `float` nên pattern không khớp. Từ khóa *widening* chỉ nói về miền giá trị theo quy tắc chuyển đổi của Java; nó không đảm bảo mọi bit có nghĩa đều được giữ nguyên.

Một số trường hợp thường gặp:

| Chuyển đổi | Điều kiện để pattern khớp |
|---|---|
| `int` sang `long` | Luôn chính xác |
| `float` sang `double` | Luôn chính xác đối với giá trị `float` đã có |
| `int` sang `float` | Chỉ khi giá trị cụ thể biểu diễn chính xác bằng `float` |
| `double` sang `float` | Chỉ khi giá trị cụ thể không mất độ chính xác hoặc miền giá trị |
| `int` sang `byte` | Chỉ khi giá trị nằm trong miền `byte` |
| `float` sang `int` | Chỉ khi chuyển đổi không làm mất phần lẻ, miền giá trị hoặc thông tin khác |

Không nên chỉ dựa vào tên widening/narrowing để dự đoán kết quả. Quy tắc pattern dựa trên tính chính xác của chuyển đổi đối với giá trị thực tế.

## 3. Dùng primitive type pattern với instanceof

Trước Java 26, `instanceof` chủ yếu kiểm tra quan hệ tương thích giữa các kiểu tham chiếu. Với JEP 530, toán tử này có thể kiểm tra chuyển đổi giữa các kiểu nguyên thủy và pattern matching có thể khai báo biến mẫu nguyên thủy.

Ví dụ kiểm tra một phép chuyển đổi an toàn:

```java
static void printIfNarrowingIsSafe(int value) {
    if (value instanceof byte b) {
        System.out.println("byte = " + b);
    }
}
```

Ở đây `instanceof byte b` thực hiện hai việc:

1. Kiểm tra giá trị `value` có chuyển đổi chính xác sang `byte` không.
2. Nếu có, khởi tạo biến mẫu `b` có kiểu `byte` để dùng trong nhánh đúng.

Có thể dùng nhiều pattern để phân loại theo khả năng biểu diễn:

```java
static String smallestIntegralType(int value) {
    if (value instanceof byte b) {
        return "byte: " + b;
    }

    if (value instanceof short s) {
        return "short: " + s;
    }

    if (value instanceof char c) {
        return "char: " + (int) c;
    }

    return "int: " + value;
}
```

Thứ tự kiểm tra có ý nghĩa vì các miền kiểu có phần giao nhau. Ví dụ một giá trị nhỏ có thể chuyển đổi chính xác sang cả `byte`, `short`, `char` và `int`. Khi kiểm tra từ kiểu hẹp hơn trước, chương trình chọn cách biểu diễn hẹp nhất trong các trường hợp được liệt kê. Nếu muốn phân loại theo quy tắc nghiệp vụ khác, hãy sắp xếp pattern tương ứng và giải thích rõ tiêu chí.

### Phân biệt type comparison và pattern matching

Java 26 cũng cho phép dùng `instanceof` với kiểu nguyên thủy ở dạng chỉ kiểm tra:

```java
int value = 42;

if (value instanceof byte) {
    System.out.println("Có thể chuyển đổi chính xác sang byte");
}
```

Dạng `value instanceof byte` chỉ trả về boolean. Nó không tạo biến `byte` và không thực hiện phép chuyển đổi để cung cấp kết quả cho phần thân. Nếu cần dùng giá trị đã chuyển đổi, dùng type pattern:

```java
if (value instanceof byte b) {
    System.out.println("Giá trị sau kiểm tra: " + b);
}
```

Dạng thứ hai giúp tránh lặp lại cast và gắn việc sử dụng giá trị đã chuyển đổi với điều kiện kiểm tra an toàn.

## 4. Pattern variable và phạm vi sử dụng

Pattern variable chỉ được khởi tạo khi pattern khớp. Java áp dụng quy tắc flow scoping: biến mẫu chỉ có thể được tham chiếu ở những vị trí mà trình biên dịch chứng minh rằng pattern đã khớp.

Ví dụ:

```java
int value = 100;

if (value instanceof byte b) {
    // b chỉ tồn tại trong nhánh này
    System.out.println(b);
}

// Không thể tham chiếu b ở đây.
```

Có thể kết hợp với toán tử điều kiện ngắn mạch:

```java
int value = 100;

if (value instanceof byte b && b > 0) {
    System.out.println("Byte dương: " + b);
}
```

Nếu pattern không khớp, vế phải của `&&` không được đánh giá nên `b` không thể bị dùng khi chưa được khởi tạo. Với `||`, cần chú ý flow scoping: không thể sử dụng biến mẫu ở nhánh mà pattern có thể thất bại.

Đặt tên biến mẫu theo ý nghĩa nghiệp vụ, ví dụ `port`, `smallValue` hoặc `exactFloat`. Tránh đặt tên quá chung khiến người đọc không biết biến đang mang kiểu gốc hay kiểu sau chuyển đổi.

## 5. Kết hợp type pattern nguyên thủy với switch

JEP 530 mở rộng `switch` để selector có thể là kiểu nguyên thủy, gồm cả `long`, `float`, `double` và `boolean`. Type pattern có thể chuyển đổi selector sang một kiểu khác nếu chuyển đổi chính xác.

Ví dụ phân loại một giá trị `double` theo kiểu nguyên thủy có thể biểu diễn chính xác nó:

```java
static String classify(double value) {
    return switch (value) {
        case byte b  -> "byte: " + b;
        case short s -> "short: " + s;
        case int i   -> "int: " + i;
        case long l  -> "long: " + l;
        case float f -> "float: " + f;
        case double d -> "double: " + d;
    };
}
```

Các pattern hẹp hơn đứng trước vì chúng chỉ khớp với một tập con các giá trị có thể biểu diễn chính xác. Pattern `double d` ở cuối là pattern bao phủ toàn bộ giá trị của selector `double`, nên nó đảm bảo switch expression exhaustive. Với giá trị `42.0d`, pattern `byte b` có thể khớp trước; với `42.5d`, các kiểu nguyên và `float` chỉ khớp nếu chuyển đổi tương ứng giữ nguyên giá trị chính xác. Nếu không có kiểu hẹp nào khớp, `double d` nhận giá trị.

Một ví dụ khác dùng guard `when` để phân loại số thực:

```java
static String describe(float value) {
    return switch (value) {
        case float f when Float.isNaN(f) -> "NaN";
        case float f when f < 0.0f -> "negative";
        case 0.0f -> "zero";
        case float f -> "positive";
    };
}
```

Pattern `float f` khớp mọi giá trị của selector `float`. Hai nhánh đầu dùng guard để kiểm tra điều kiện bổ sung. Pattern cuối cùng bắt các giá trị còn lại, làm switch expression đầy đủ. Các nhánh có guard không tự bao phủ toàn bộ miền giá trị vì điều kiện `when` có thể sai.

## 6. Wrapper type, unboxing và null

Primitive type pattern cũng hữu ích khi làm việc với wrapper. Ví dụ, một giá trị `Integer` có thể được unbox để kiểm tra và khởi tạo pattern variable kiểu `int` nếu chuyển đổi chính xác:

```java
Integer boxed = 42;

if (boxed instanceof int value) {
    System.out.println(value + 1);
}
```

Khi nguồn là reference type, chuyển đổi cần thiết có thể bao gồm kiểm tra kiểu tham chiếu và unboxing. Nếu reference là `null`, pattern primitive không khớp; nhánh `if` không chạy. Không có việc tự unbox `null` thành primitive gây `NullPointerException` trong quá trình pattern matching.

Ví dụ xử lý dữ liệu wrapper có thể null:

```java
Integer boxed = readOptionalInteger();

if (boxed instanceof int value) {
    process(value);
} else {
    handleMissingOrWrongValue();
}
```

Nếu kiểu tĩnh của biến là wrapper cụ thể, trình biên dịch biết phép unboxing cần thiết. Nếu nguồn có kiểu `Object`, việc kiểm tra còn phụ thuộc liệu giá trị runtime có thể chuyển đổi an toàn qua kiểu wrapper tương ứng hay không. Luôn đọc kiểu tĩnh của biểu thức nguồn khi phân tích một pattern, nhất là với generic type và type erasure.

## 7. Những thay đổi và giới hạn cần nhớ trong Java 26

JEP 530 là lần preview thứ tư của tính năng, sau các lần preview ở Java 23, Java 24 và Java 25. Java 26 có các điều chỉnh quan trọng liên quan đến tính chính xác vô điều kiện và quy tắc dominance trong `switch`.

- **Exact testing conversion:** phép chuyển đổi được kiểm tra tại runtime chỉ được xem là khớp nếu kết quả không mất thông tin. Điều này áp dụng cả chuyển đổi widening có thể mất độ chính xác lẫn narrowing.
- **Unconditionally exact conversion:** một số chuyển đổi được chứng minh là chính xác với mọi giá trị của kiểu nguồn; một số chuyển đổi khác chỉ chính xác với một constant expression cụ thể. Khái niệm này ảnh hưởng đến tính exhaustive và dominance của switch.
- **Dominance:** một pattern đứng trước không được làm cho pattern đứng sau trở nên không thể đạt tới. Vì một pattern primitive có thể khớp với một tập giá trị rộng hơn hoặc hẹp hơn tùy chuyển đổi, cần kiểm tra thứ tự case và các quy tắc dominance của JLS.
- **Primitive và reference không đồng nhất:** pattern nguyên thủy kiểm tra chuyển đổi giá trị; pattern tham chiếu kiểm tra đối tượng và kiểu runtime. Không suy diễn rằng quy tắc pattern của `String s` áp dụng y hệt cho `int i`.

Tại Java 27, tính năng tiếp tục là preview lần thứ năm (JEP 532), và tài liệu Oracle ghi nhận không có thay đổi ngữ nghĩa đáng kể so với Java 26. Dù vậy, code preview vẫn phải biên dịch và chạy với đúng JDK của release tương ứng.

## 8. Biên dịch và chạy đúng JDK

Vì primitive type pattern vẫn là preview, cần bật preview ở cả compiler và runtime. Ví dụ dưới đây dùng JDK 26:

```bash
javac --enable-preview --release 26 -d out PrimitivePatternDemo.java
java --enable-preview -cp out PrimitivePatternDemo
```

Nếu thử trên JDK 27, phải biên dịch và chạy bằng JDK 27:

```bash
javac --enable-preview --release 27 -d out27 PrimitivePatternDemo.java
java --enable-preview -cp out27 PrimitivePatternDemo
```

Không dùng class file được biên dịch với preview của JDK 26 để chạy bằng JDK 27 hoặc ngược lại. `--enable-preview` không phải công tắc để chạy preview cũ trên runtime mới; preview được ràng buộc với release cụ thể.

Các lưu ý khi cấu hình IDE và pipeline:

- Đặt language level và compiler JDK đúng release mục tiêu.
- Bật preview features cho cả compile và run configuration.
- Với Maven, Gradle hoặc IDE, kiểm tra cấu hình tương ứng có truyền cờ preview đến cả compiler và JVM chạy test.
- Không bật preview cho toàn bộ sản phẩm chỉ vì một ví dụ học tập cần nó; cô lập code thử nghiệm và xác định kế hoạch thay thế khi tính năng đổi.
- Khi tính năng trở thành final trong một JDK tương lai, kiểm tra lại JLS và loại bỏ cờ preview theo hướng dẫn của release đó. Không giả định cú pháp preview tự động ổn định mà không cần kiểm tra.

## 9. Khi nào nên dùng?

Primitive type pattern phù hợp khi chương trình cần xác minh một chuyển đổi số an toàn trước khi dùng giá trị đã chuyển đổi, đặc biệt ở ranh giới dữ liệu, bộ giải mã, bộ phân loại giá trị hoặc logic chọn kiểu lưu trữ.

Ví dụ, khi nhận một số nguyên từ nguồn dữ liệu và muốn chọn kiểu nhỏ nhất mà vẫn giữ nguyên giá trị, pattern giúp tránh cast làm tràn:

```java
static Object compactNumber(int value) {
    if (value instanceof byte b) {
        return b;
    }
    if (value instanceof short s) {
        return s;
    }
    if (value instanceof char c && value >= 0) {
        return c;
    }
    return value;
}
```

Ví dụ này chỉ minh họa kỹ thuật chọn kiểu; trong ứng dụng thật, cần cân nhắc `char` có phù hợp với ý nghĩa dữ liệu không. `char` là đơn vị mã UTF-16 không dấu, không phải kiểu số nguyên tổng quát để thay thế `short`.

Không cần dùng primitive pattern cho phép chuyển đổi đơn giản đã được chứng minh an toàn ở compile time, chẳng hạn gán `int` sang `long`. Nó hữu ích nhất khi kết quả phụ thuộc giá trị runtime và khi việc kiểm tra cùng chuyển đổi cần được biểu đạt trong một cấu trúc rõ ràng.

## Tài liệu tham chiếu

1. [JEP 530 – Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
2. [Oracle Java SE 26 – Type Patterns with Primitive Types](https://docs.oracle.com/en/java/javase/26/language/type-patterns.html)
3. [Oracle Java SE 26 – Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html)
4. [Oracle Java SE 26 – Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
5. [Java Language Specification, Java SE 26 – Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
6. [Oracle Java Language Changes by Release – Java SE 27 (Fifth Preview)](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
7. [JEP 532 – Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532)


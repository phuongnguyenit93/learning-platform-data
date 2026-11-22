# Hành vi của `instanceof` khi giá trị được kiểm tra là `null`

## 1. Kết luận cốt lõi

Với `instanceof`, **giá trị tham chiếu `null` luôn làm phép kiểm tra kiểu trả về `false`**. Quy tắc này áp dụng cho cả cú pháp kiểm tra kiểu thông thường lẫn cú pháp so khớp mẫu kiểu (type pattern):

```java
Object value = null;

boolean oldStyle = value instanceof String;        // false
boolean withPattern = value instanceof String text; // false
boolean asObject = value instanceof Object;        // false
```

Ba biểu thức trên đều đánh giá thành `false`; **bản thân phép `instanceof` không ném `NullPointerException` vì toán hạng trái là `null`**. Khi kiểm tra bằng mẫu `String text`, vì phép kiểm tra không khớp nên **không có biến mẫu `text` được gán cho đường đi thành công**.

Đây là hành vi vẫn còn đúng trong Java hiện đại. Pattern matching cho `instanceof` được giới thiệu ở Java 14 dưới dạng preview và **được chuẩn hóa từ Java 16**. Các ví dụ chạy độc lập ở bài này sử dụng Java 17+ và không yêu cầu bật bất cứ tính năng preview cũ nào.

**Mục tiêu:** hiểu chính xác cách `null` tương tác với `instanceof`, nhận biết khi nào biến mẫu được dùng, tránh hiểu nhầm `NullPointerException` và thiết kế nhánh xử lý `null` rõ ràng.

## 2. Vì sao `null` không khớp một kiểu?

`instanceof` kiểm tra liệu một tham chiếu **khác `null`** có trỏ đến một đối tượng tương thích với kiểu hoặc mẫu ở bên phải hay không.

Với cú pháp truyền thống:

```java
Object candidate = null;
System.out.println(candidate instanceof CharSequence); // false
System.out.println(candidate instanceof Object);       // false
```

`null` không đại diện cho một đối tượng có kiểu thực tế ở runtime. Biến `candidate` **được khai báo kiểu `Object`** chỉ cho biết biến này *có thể chứa* tham chiếu đến đối tượng `Object`; nó không làm `null` trở thành một đối tượng `Object`.

Với mẫu kiểu:

```java
Object candidate = null;

if (candidate instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String khác null");
}
```

Điều kiện sai, chương trình đi vào `else`, in:

```text
Không phải String khác null
```

Biến `text` được **giới thiệu bởi mẫu**, nhưng chỉ được gán và chỉ được phép sử dụng ở những vị trí mà trình biên dịch chứng minh việc khớp mẫu đã thành công. Trong nhánh `else` trên, `text` không khả dụng. Không có giá trị mặc định kiểu `null` nào được tự động gán cho nó khi so khớp thất bại.

### Quy tắc đánh giá của đặc tả Java

Theo JLS `15.20.2, đối với hai hình thức:

- `expression instanceof ReferenceType` — phép kiểm tra kiểu.
- `expression instanceof Pattern` — phép so khớp mẫu.

Nếu **giá trị đã đánh giá** của `expression` là tham chiếu `null`, kết quả phép `instanceof` là `false`. Nếu giá trị khác `null`, Java tiếp tục kiểm tra khả năng tương thích kiểu hoặc so khớp mẫu. Kết quả thành công của mẫu mới gắn giá trị với các biến mẫu tương ứng.

Cần phân biệt **kiểu tĩnh** của biểu thức (được kiểm tra lúc biên dịch) với **giá trị runtime** là `null`. Một cú pháp `instanceof` có kiểu tĩnh không hợp lệ vẫn bị từ chối lúc biên dịch; việc bạn định gán `null` khi chạy không làm mã không hợp lệ trở nên hợp lệ.

## 3. `false` không có nghĩa “chắc chắn sai kiểu”

Điều kiện `value instanceof String text` trả về `false` trong **ít nhất hai tình huống khác nhau**:

1. `value == null`.
2. `value` khác `null`, nhưng đối tượng không tương thích với `String`.

Ví dụ:

```java
Object first = null;
Object second = Integer.valueOf(42);

System.out.println(first instanceof String);  // false
System.out.println(second instanceof String); // false
```

Từ kết quả `false` **không thể kết luận** rằng đầu vào khác `null` hoặc nhất thiết thuộc một kiểu đối tượng khác. Nếu chức năng cần phân biệt *thiếu dữ liệu* với *sai kiểu*, hãy kiểm tra `null` tường minh:

```java
static String describe(Object value) {
    if (value == null) {
        return "thiếu giá trị";
    }
    if (value instanceof String text) {
        return "chuỗi: " + text;
    }
    return "kiểu khác";
}
```

Đoạn trên là **phương thức minh họa**, cần đặt bên trong một lớp để biên dịch. Thứ tự ưu tiên này có ý nghĩa: nhánh đầu xử lý riêng trường hợp `null`; nhánh thứ hai xử lý đối tượng `String` thực sự; nhánh cuối xử lý đối tượng không phải chuỗi.

Nếu nghiệp vụ chỉ cần biết “đây có phải `String` hợp lệ không”, `if (value instanceof String text)` là đủ; không bắt buộc phải viết `value != null && ...` vì `instanceof` đã loại `null`.

## 4. Toán tử `&&` và tính an toàn của biến mẫu

Mẫu `instanceof` thường được kết hợp với toán tử AND ngắn mạch (`&&`):

```java
Object value = null;

if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

Đây là mã **hợp lệ và an toàn khi `value == null`**, bởi vì:

1. Java đánh giá `value instanceof String text` trước.
2. Với `null`, điều kiện bên trái là `false`.
3. `&&` **không đánh giá** vế phải khi vế trái là `false`.
4. Vì vậy `text.isBlank()` không chạy, không có thao tác dereference nào trên giá trị `null`.
5. Trình biên dịch cho phép dùng `text` trong vế phải vì đến được vị trí đó thì phép so khớp bên trái đã thành công.

Tương tự, khi `value` là một `String` khác `null`, biến mẫu `text` đã tham chiếu đến đối tượng đó và có thể gọi `isBlank()` an toàn.

### Không dùng `||` theo cách tương tự

Đoạn sau **không biên dịch được**; đây chỉ là minh họa lỗi:

```java
Object value = null;

if (value instanceof String text || text.isBlank()) {
    // Sai: text không nằm trong phạm vi được bảo đảm ở vế phải.
}
```

Với OR ngắn mạch (`||`), vế phải được đánh giá **khi vế trái sai**. Khi đó mẫu có thể chưa khớp, nên biến `text` không được gán chắc chắn và không thể sử dụng ở vế phải. Đây là lỗi **phạm vi và gán biến mẫu lúc biên dịch**, chứ không phải `NullPointerException` lúc chạy.

Nếu muốn xử lý `null` hoặc chuỗi trống:

```java
if (value == null || (value instanceof String text && text.isBlank())) {
    System.out.println("Thiếu giá trị hoặc chuỗi trắng");
}
```

Ở đây, nhánh `null` được xử lý riêng bởi `value == null`; khi cần kiểm tra `text.isBlank()`, Java chỉ đi tới đó nếu mẫu `String text` đã khớp. Cả hai điều kiện đều nằm trong phạm vi an toàn.

## 5. Phạm vi của biến mẫu khi phép kiểm tra thất bại

Biến mẫu khác với biến cục bộ được khai báo trước câu lệnh `if`. Phạm vi của nó phụ thuộc **luồng điều khiển**: trình biên dịch chỉ cho dùng biến khi chắc chắn phép so khớp đã thành công.

### 5.1. Trong nhánh `if` đúng

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // hợp lệ
} else {
    // Không thể dùng text ở đây.
}
```

Đối với `null`, chương trình đi vào `else`; không thể coi `text` là biến có giá trị `null` tại đây.

### 5.2. Đảo điều kiện bằng `!` và kết thúc sớm

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "not a String";
    }

    return text.strip();
}
```

Mẫu này hợp lệ vì sau `if` chỉ còn những đường đi đã **khớp `String`**. Nếu `value == null`, biểu thức `instanceof` sai, dấu `!` làm điều kiện đúng và phương thức trả `"not a String"` ngay; dòng `text.strip()` không bao giờ chạy trong trường hợp đó.

Nếu bỏ lệnh `return` ra khỏi nhánh thất bại, compiler không thể mặc nhiên coi `text` đã được gán ở lệnh tiếp theo. Phạm vi biến mẫu phụ thuộc cả phép khớp lẫn việc nhánh thất bại có tiếp tục đến lệnh sau hay không.

### 5.3. Không sử dụng biến mẫu ở đường đi không khớp

Đoạn sau **không biên dịch được**:

```java
Object value = null;
if (value instanceof String text) {
    System.out.println(text);
} else {
    System.out.println(text); // Lỗi: biến mẫu không khả dụng.
}
```

Để xử lý `null`, sử dụng biến gốc `value` trong nhánh `else` hoặc kiểm tra `value == null`. Đừng cố khởi tạo hay dùng `text` sau một lần so khớp thất bại.

## 6. `instanceof` an toàn với `null`, nhưng biểu thức bên trái vẫn có thể ném lỗi

**Quan trọng:** Quy tắc “`instanceof` trả `false` khi toán hạng trái có giá trị `null`” áp dụng **sau khi Java đánh giá xong biểu thức bên trái**. Nếu quá trình đánh giá đó đã ném ngoại lệ, phép `instanceof` chưa có cơ hội xử lý `null`.

Đúng:

```java
String input = null;

boolean result = input instanceof CharSequence; // false
boolean fromCall = getValue() instanceof String; // false, nếu getValue() trả null
```

Lệnh `getValue()` ở trên là **phương thức giả định** chỉ để diễn tả thứ tự đánh giá, không phải chương trình chạy độc lập. Nếu `getValue()` ném ngoại lệ trước khi trả về, ngoại lệ vẫn được truyền đi.

Sai khi `input == null`:

```java
String input = null;

boolean result = input.trim() instanceof String;
```

Ở đây `input.trim()` cố gọi phương thức qua tham chiếu `null` và ném `NullPointerException` **trước khi** phép `instanceof` được thực hiện. Thêm `instanceof` ở cuối không bảo vệ thao tác gọi phương thức đã xảy ra trước đó.

### Ép kiểu tham chiếu `null` có khác không?

```java
Object input = null;
String converted = (String) input; // hợp lệ: converted vẫn null
// converted.length();             // nếu chạy sẽ ném NullPointerException
```

Ép một tham chiếu `null` sang kiểu tham chiếu tương thích vẫn cho kết quả `null`. Nguy cơ phát sinh khi chương trình **truy cập thành viên** qua tham chiếu `null`. Mẫu `instanceof` giúp tránh việc ép kiểu thủ công sau kiểm tra kiểu thành công.

### `Class.isInstance(null)`

`String.class.isInstance(null)` cũng trả `false`. Phương thức này hữu ích khi đối tượng `Class<?>` là dữ liệu được truyền vào, nhưng không khai báo biến mẫu. Nó là API khác với toán tử `instanceof` và **không tự cung cấp cơ chế flow scoping**.

## 7. Chương trình Java 17+ hoàn chỉnh và đầu ra chính xác

Lưu vào tệp **`NullInstanceofDemo.java`**:

```java
import java.util.Locale;

public class NullInstanceofDemo {

    static String describe(Object value) {
        if (value == null) {
            return "missing";
        }

        if (value instanceof String text) {
            if (text.isBlank()) {
                return "blank";
            }
            return "text:" + text.strip().toUpperCase(Locale.ROOT);
        }

        if (value instanceof Integer number) {
            return "integer:" + number;
        }

        return "other:" + value.getClass().getSimpleName();
    }

    static int lengthIfNonBlank(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.length();
        }
        return -1;
    }

    static String negativeGuard(Object value) {
        if (!(value instanceof String text)) {
            return "not String";
        }
        return text.toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Object candidate = null;

        System.out.println("nullTraditional=" +
                (candidate instanceof String));

        boolean patternResult = candidate instanceof String text;
        System.out.println("nullPattern=" + patternResult);

        System.out.println("nullObject=" +
                (candidate instanceof Object));
        System.out.println("classIsInstance=" +
                String.class.isInstance(candidate));

        System.out.println("describeNull=" + describe(candidate));
        System.out.println("describeText=" + describe(" java "));
        System.out.println("describeBlank=" + describe("   "));
        System.out.println("describeInteger=" + describe(7));

        System.out.println("andNull=" + lengthIfNonBlank(null));
        System.out.println("andText=" + lengthIfNonBlank("abc"));

        System.out.println("guardNull=" + negativeGuard(null));
        System.out.println("guardText=" + negativeGuard("Hi"));

        String casted = (String) candidate;
        System.out.println("castedNull=" + (casted == null));

        try {
            candidate.toString();
        } catch (NullPointerException ignored) {
            System.out.println("dereference=NPE");
        }
    }
}
```

Dùng JDK 17 trở lên, biên dịch và chạy:

```bash
javac NullInstanceofDemo.java
java NullInstanceofDemo
```

Đầu ra:

```text
nullTraditional=false
nullPattern=false
nullObject=false
classIsInstance=false
describeNull=missing
describeText=text:JAVA
describeBlank=blank
describeInteger=integer:7
andNull=-1
andText=3
guardNull=not String
guardText=hi
castedNull=true
dereference=NPE
```

**Phân tích kết quả:**

1. Bốn dòng đầu cho thấy `null` không khớp với kiểu `String`, kiểu `Object` hay mẫu kiểu; `Class.isInstance` cũng trả `false`.
2. `describe(null)` dùng kiểm tra `null` tường minh để phân biệt thiếu dữ liệu với kiểu đối tượng khác.
3. Với `" java "`, mẫu `String text` thành công. `strip()` bỏ khoảng trắng biên và `toUpperCase(Locale.ROOT)` tạo `"JAVA"`.
4. `"   "` là chuỗi hợp lệ về **kiểu**, nhưng `isBlank()` đúng nên được phân loại `blank`. **Khớp kiểu không đồng nghĩa dữ liệu đã đáp ứng quy tắc nghiệp vụ.**
5. `lengthIfNonBlank(null)` trả `-1` nhờ `&&` ngắn mạch; không có lời gọi `text.isBlank()` trên `null`.
6. `negativeGuard(null)` trả sớm, nên dòng `text.toLowerCase(...)` sau đó chỉ chạy với một đối tượng `String` thật.
7. Ép kiểu tham chiếu `null` được phép, nên `castedNull=true`; lời gọi `candidate.toString()` mới ném `NullPointerException` và được bắt để in `dereference=NPE`.

Ví dụ cố ý **không sử dụng bất kỳ cú pháp preview nào** và không cần thư viện ngoài JDK.

## 8. `null` với các dạng mẫu khác trong Java mới

Quy tắc của **toán tử `instanceof`** không thay đổi chỉ vì phiên bản Java bổ sung nhiều loại mẫu hơn. Ví dụ Java 21 có *record patterns*:

```java
record Point(int x, int y) {}

Object value = null;
boolean matched = value instanceof Point(int x, int y); // false
```

Đây là **minh họa cú pháp Java 21** (không phải mã Java 17), và `null` **không khớp mẫu record**. Trong phạm vi bài này, luôn nhớ: **`null` ở vế trái của `instanceof` làm phép kiểm tra trả `false`**.

Không nhầm điều đó với **pattern matching for `switch`**, được chuẩn hóa ở Java 21: một `switch` có thể có nhãn `case null` để xử lý `null` tường minh. Ví dụ Java 21:

```java
static String show(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
```

Hàm `show` chỉ là **phương thức minh họa** cần đặt trong lớp hợp lệ. `case null` thuộc quy tắc của `switch`, không có nghĩa `null instanceof String text` sẽ trả `true`. Vì đề bài là `instanceof`, chỉ cần biết khác biệt này để tránh suy luận sai giữa hai cấu trúc điều khiển.

## 9. Những lỗi thường gặp

| Hiểu nhầm / lỗi | Điều thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| “`null instanceof String` ném `NullPointerException`” | `instanceof` trả `false` khi toán hạng trái là `null` | Để `instanceof` trực tiếp kiểm tra tham chiếu |
| “Biến khai báo kiểu `Object` thì `null instanceof Object` phải đúng” | Kiểu khai báo không biến `null` thành đối tượng | Hiểu kiểm tra runtime cần tham chiếu khác `null` |
| “Mẫu `String text` thất bại thì `text == null`” | Biến mẫu không được gán cho đường đi thất bại và không khả dụng tại đó | Dùng biến gốc và kiểm tra `value == null` |
| “Không cần kiểm tra `null` ở nơi nào nữa” | Khi cần phân biệt thiếu dữ liệu với sai kiểu, `false` chưa đủ | Xử lý `value == null` bằng nhánh riêng |
| Dùng `value instanceof String text || text.isBlank()` | Vế phải có thể chạy lúc mẫu chưa khớp; lỗi phạm vi biến mẫu | Dùng `&&` trong phần cần truy cập `text` |
| Gọi `value.toString() instanceof String` khi `value == null` | Gọi `toString()` ném lỗi trước `instanceof` | Kiểm tra `value` trực tiếp hoặc `null` trước |
| Cho rằng `String.class.isInstance(null)` là `true` | API này cũng trả `false` | Dùng `value == null` nếu muốn nhận diện null |
| Cho rằng `instanceof String text` có thể bắt `null` như `switch case null` | Đây là hai cấu trúc với luật khác nhau | Dùng kiểm tra `null` riêng trong `if` |
| Cho rằng khớp mẫu `String` bảo đảm chuỗi không rỗng | Kiểm tra kiểu không kiểm tra quy tắc nghiệp vụ | Kiểm tra `isBlank()`, độ dài hoặc ràng buộc khác sau khi khớp |

## 10. Thực hành tự kiểm tra

**Câu 1.** Khi `Object x = null;`, biểu thức `x instanceof Object` là `true` hay `false`?  
**Đáp án:** `false`, vì không có đối tượng runtime được tham chiếu.

**Câu 2.** Khi `x == null`, đoạn `if (x instanceof String s) { System.out.println(s.length()); }` có gây `NullPointerException` không?  
**Đáp án:** Không. Nhánh `if` không được thực hiện vì phép kiểm tra trả `false`.

**Câu 3.** `if (x instanceof String s && s.length() > 2)` có an toàn với `null` không?  
**Đáp án:** Có. Vế phải của `&&` chỉ chạy sau khi `instanceof` trả `true`.

**Câu 4.** Có thể dùng `s` trong nhánh `else` của `if (x instanceof String s)` không?  
**Đáp án:** Không. Nhánh `else` nằm trên đường đi mà mẫu chưa được chứng minh đã khớp.

**Câu 5.** `((String) x).length()` với `x == null` có khác `x instanceof String s` không?  
**Đáp án:** Có. Phép ép kiểu tham chiếu `null` không tự ném lỗi, nhưng gọi `length()` qua kết quả `null` gây `NullPointerException`. Còn `instanceof` trả `false`.

**Câu 6.** `x instanceof String s` trả `false`; có suy ra chắc chắn `x` là `Integer` không?  
**Đáp án:** Không. `x` có thể là `null` hoặc thuộc bất kỳ kiểu không khớp nào.

**Câu 7.** Trong Java 21, `switch` có `case null` có làm `null instanceof Point(int x, int y)` thành `true` không?  
**Đáp án:** Không. Hai cấu trúc có ngữ nghĩa riêng; `instanceof` vẫn trả `false` khi toán hạng trái là `null`.

## 11. Ghi nhớ và nguồn chuẩn

Đối với `instanceof`:

- **`null` không khớp bất kỳ kiểu hoặc mẫu nào ở vế phải**, nên kết quả là `false`.
- **Không có biến mẫu thành công** nếu kiểm tra thất bại; phạm vi biến mẫu phụ thuộc luồng điều khiển.
- **`&&` có thể bảo vệ việc gọi phương thức trên biến mẫu**, vì vế phải chỉ chạy khi khớp thành công.
- **Phân biệt việc phép `instanceof` xử lý `null` với ngoại lệ phát sinh khi tính toán hạng bên trái**.
- Nếu cần phân biệt **thiếu giá trị** và **sai kiểu**, viết nhánh `value == null` riêng.
- Những quy tắc này vẫn có hiệu lực với pattern matching cho `instanceof` đã chuẩn hóa và Java hiện đại.

Tài liệu chính thức:

- [JLS Java SE 21 `15.20.2 — The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): mô tả cả phép kiểm tra kiểu và so khớp mẫu, bao gồm trường hợp giá trị là `null`.
- [Oracle Java SE 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): biến mẫu, phạm vi theo luồng điều khiển và `&&`/`||`.
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): tính năng được chuẩn hóa trong Java 16.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ghi rõ `null` không khớp record pattern.

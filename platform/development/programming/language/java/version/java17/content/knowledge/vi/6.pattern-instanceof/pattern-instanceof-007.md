# Pattern matching cho `instanceof` trong Java 17: `null`, kiểu không tương thích và trường hợp không khớp

Trong Java 17, **pattern matching cho `instanceof`** giúp kiểm tra kiểu của một đối tượng và, khi kiểm tra thành công, lấy đối tượng đó qua một biến có kiểu phù hợp. Tuy nhiên, câu lệnh này thường bị hiểu nhầm ở ba tình huống: đối tượng là **`null`**, đối tượng thuộc **kiểu runtime khác kiểu được kiểm tra**, hoặc **hai kiểu đã không thể tương thích ngay từ lúc biên dịch**. Hiểu sự khác biệt giữa các tình huống này giúp xử lý dữ liệu đầu vào an toàn, viết nhánh dự phòng đúng và tránh lỗi compile.

Bài học tập trung vào hành vi trong **Java 17**, nơi pattern matching cho `instanceof` đã là tính năng chính thức (JEP 394), không yêu cầu `--enable-preview`.

## 1. Cú pháp và ý nghĩa của phép kiểm tra

Ví dụ cơ bản:

```java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

Biểu thức `value instanceof String text` bao gồm:

| Thành phần | Vai trò |
| --- | --- |
| `value` | Biểu thức được kiểm tra. Giá trị lúc chạy có thể thuộc nhiều kiểu tham chiếu, hoặc `null`. |
| `String` | Kiểu tham chiếu mà đối tượng phải tương thích ở runtime để khớp pattern. |
| `text` | **Pattern variable** chỉ được gán và dùng ở nơi trình biên dịch xác định phép kiểm tra đã khớp. |
| `instanceof` | Trả về `boolean`: `true` khi pattern khớp; `false` khi không khớp. Một biểu thức không hợp lệ về kiểu thì bị báo lỗi **trong lúc biên dịch**. |

Về ý nghĩa, đoạn trên tương đương với dạng kiểm tra kiểu và ép kiểu thủ công:

```java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Ưu điểm là Java chỉ tạo biến `text` khi phép kiểm tra thành công, tránh viết lại phép ép kiểu trong nhánh hợp lệ.

### Ba tình huống cần phân biệt

| Tình huống | Ví dụ | Kết quả |
| --- | --- | --- |
| Giá trị là `null` | `Object x = null; x instanceof String s` | **`false`**. |
| Kiểu khai báo có thể tương thích nhưng đối tượng thực tế không khớp | `Object x = 42; x instanceof String s` | **`false`**. |
| Hai kiểu không thể tương thích theo quy tắc ngôn ngữ | `String x = "a"; x instanceof Integer n` | **Lỗi biên dịch**. |

Phân biệt **`false` ở runtime** với **lỗi kiểu lúc compile-time** là trọng tâm của bài này.

## 2. Khi đối tượng là `null`: pattern không khớp

Với một **type pattern** như `String text`, giá trị `null` luôn làm `instanceof` trả về `false`:

```java
public class NullPatternDemo {
    public static void main(String[] args) {
        Object value = null;

        if (value instanceof String text) {
            System.out.println("Chuỗi có " + text.length() + " ký tự");
        } else {
            System.out.println("Không khớp String");
        }
    }
}
```

Kết quả:

```text
Không khớp String
```

Ở đây không xảy ra `NullPointerException` chỉ vì `value` là `null`: toán tử `instanceof` kiểm tra và trả về `false`. Biến `text` không được sử dụng trong nhánh `if` vì nhánh đó không chạy.

### 2.1. Không bắt buộc kiểm tra `null` trước `instanceof`

Đoạn sau là hợp lệ và an toàn đối với giá trị `null`:

```java
static int stringLengthOrZero(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Nếu `value` là `null`, phương thức trả về `0`. Trong nhánh khớp, `text` chắc chắn là một tham chiếu **không null**, vì `null` không khớp type pattern này.

Tuy vậy, nếu ứng dụng cần phân biệt **`null`** với **đối tượng có kiểu khác**, hãy tách rõ nhánh:

```java
static String describe(Object value) {
    if (value == null) {
        return "Chưa có dữ liệu";
    }

    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }

    return "Đối tượng thuộc kiểu khác";
}
```

Nếu chỉ có `else`, cả `null`, `Integer`, `List<?>` và những đối tượng không phải `String` đều vào chung một nhánh. Điều đó có thể đúng cho một số bài toán, nhưng không phải lúc nào cũng diễn đạt được ý nghĩa nghiệp vụ.

### 2.2. `instanceof` không bảo vệ những thao tác khác khỏi `null`

```java
Object value = null;

System.out.println(value instanceof String); // false

// Dòng dưới ném NullPointerException khi được thực thi:
// System.out.println(((Object) value.toString()) instanceof String text);
```

Ở dòng bị chú thích, Java phải gọi `value.toString()` **trước** khi có giá trị để đưa vào `instanceof`. Việc truy cập phương thức trên tham chiếu `null` gây lỗi từ bước đánh giá biểu thức bên trái, không phải do bản thân phép kiểm tra kiểu.

Tương tự, `if (value instanceof String text && text.length() > 0)` là an toàn với `null` nhờ cơ chế ngắn mạch, nhưng `if (value.toString() instanceof String text)` thì không.

## 3. Khi kiểu runtime không khớp: trả về `false`, không tự ép kiểu

Một biến kiểu `Object` có thể chứa tham chiếu tới nhiều loại đối tượng:

```java
Object value = Integer.valueOf(25);

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Không phải String");
}
```

Kết quả:

```text
Không phải String
```

Về **kiểu tĩnh** (`Object`), phép kiểm tra có thể hợp lệ: một biến `Object` có thể trỏ tới `String`. Nhưng tại **thời điểm chạy**, đối tượng hiện tại là `Integer`, nên pattern `String text` không khớp.

Điều này cũng áp dụng cho các kiểu kế thừa và interface:

```java
Object first = new java.util.ArrayList<String>();
Object second = "Hello";

System.out.println(first instanceof java.util.List<?>);  // true
System.out.println(second instanceof java.util.List<?>); // false
```

`instanceof` chỉ kiểm tra khả năng đối tượng thuộc kiểu mong muốn; nó **không chuyển đổi** dữ liệu sang kiểu đó. Ví dụ, chuỗi `"25"` không tự chuyển thành `Integer`:

```java
Object value = "25";

if (value instanceof Integer number) {
    System.out.println(number + 1);
} else {
    System.out.println("Không phải Integer");
}
```

Muốn chuyển một chuỗi có nội dung số thành số nguyên, cần xử lý riêng, chẳng hạn `Integer.parseInt(text)` sau khi đã khớp `String`, và xử lý trường hợp nội dung không hợp lệ:

```java
static Integer tryParseInteger(Object value) {
    if (!(value instanceof String text)) {
        return null;
    }

    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return null;
    }
}
```

`null` ở kết quả phương thức trên biểu thị không chuyển đổi được theo thiết kế ví dụ; trong ứng dụng thực tế có thể chọn `OptionalInt`, một kiểu kết quả riêng, hoặc cách báo lỗi khác để phân biệt đầu vào không phải chuỗi với chuỗi không hợp lệ.

## 4. Kiểu không tương thích ngay từ lúc biên dịch

Trong Java 17, compiler kiểm tra liệu biểu thức và type pattern có thể có một quan hệ kiểu hợp lệ hay không. Nếu xác định **không có khả năng khớp**, chương trình bị báo lỗi **trước khi chạy**.

### 4.1. Hai class không thể chuyển đổi kiểu cho nhau

Ví dụ **cố ý không biên dịch được**:

```java
String text = "hello";

// Lỗi compile: String không thể là một Integer.
if (text instanceof Integer number) {
    System.out.println(number);
}
```

`String` và `Integer` đều là class cụ thể không có quan hệ kế thừa phù hợp. Một đối tượng kiểu `String` không thể đồng thời là đối tượng kiểu `Integer`, vì vậy không có tình huống runtime để pattern này thành công.

So sánh với đoạn hợp lệ:

```java
Object value = "hello";

if (value instanceof Integer number) {
    System.out.println(number);
} else {
    System.out.println("Không khớp Integer");
}
```

Đoạn thứ hai biên dịch được vì giá trị của một biến có **kiểu tĩnh `Object`** có thể là `Integer` ở những lần gọi khác; chỉ riêng lần này, đối tượng thực tế là `String`, nên kết quả là `false`.

> **Không nên dùng cách đổi toàn bộ biến thành `Object` chỉ để lách lỗi kiểu.** Kiểu khai báo giàu thông tin giúp compiler phát hiện nhầm lẫn trong mô hình. Khi có lỗi “inconvertible types”, hãy xem lại kiểu mong muốn và đường đi của dữ liệu trước.

### 4.2. Pattern thừa vì kiểu tĩnh đã là kiểu con

Java 17 còn phát hiện kiểu kiểm tra **luôn đúng đối với mọi giá trị không null** của biểu thức theo quan hệ subtype. Ví dụ sau cũng là **lỗi compile**:

```java
String text = "hello";

// Lỗi compile: kiểu tĩnh String đã là subtype của String.
if (text instanceof String matched) {
    System.out.println(matched);
}
```

Ví dụ khác:

```java
Integer number = 7;

// Lỗi compile: Integer đã là subtype của Number.
if (number instanceof Number matched) {
    System.out.println(matched);
}
```

Lý do: type pattern trong cú pháp Java 17 được thiết kế để **kiểm tra và tinh chỉnh một kiểu chưa chắc chắn**, không phải tạo tên mới cho một kiểu đã biết chắc. Vẫn có khả năng biểu thức là `null`, nhưng sự tồn tại của `null` không làm các type pattern trên trở thành một phép kiểm tra hợp lệ trong ngữ cảnh này.

Thay thế bằng kiểm tra đúng mục đích:

```java
String text = getText();

if (text != null) {
    System.out.println(text.length());
}
```

Ở đây `getText()` tượng trưng cho một phương thức trả về `String`; ví dụ tập trung vào cách kiểm tra `null`. Nếu muốn đặt tên mới cho biến, có thể gán biến thông thường trong phạm vi phù hợp.

### 4.3. Không dùng primitive trực tiếp làm đối tượng cần kiểm tra

Ví dụ cố ý sai:

```java
int number = 10;

// Lỗi compile: toán hạng bên trái không phải kiểu tham chiếu.
if (number instanceof Integer boxed) {
    System.out.println(boxed);
}
```

`int` là primitive, không phải tham chiếu tới `Integer`. Pattern matching cho `instanceof` trong Java 17 hoạt động với **reference types**; Java không tự boxing một toán hạng primitive chỉ để hợp thức hóa phép kiểm tra này.

Nếu cần xử lý một đối tượng có thể là wrapper `Integer`, hãy bắt đầu từ tham chiếu:

```java
Object value = Integer.valueOf(10);

if (value instanceof Integer number) {
    System.out.println(number + 1);
}
```

Khi cần so sánh hoặc xử lý một biến đã là `int`, hãy dùng trực tiếp các phép toán trên `int` thay vì kiểm tra `instanceof`.

### 4.4. Không kiểm tra tùy tiện tham số generic bị xóa kiểu

Java dùng **type erasure** cho generics. Vì vậy, không thể dùng type pattern có kiểu generic không thể kiểm tra đầy đủ ở runtime như sau:

```java
Object value = java.util.List.of("a", "b");

// Lỗi compile: không thể kiểm tra List<String> bằng instanceof.
if (value instanceof java.util.List<String> items) {
    System.out.println(items);
}
```

Trong Java 17, cách phù hợp là kiểm tra kiểu có thể kiểm tra ở runtime, ví dụ `List<?>`:

```java
Object value = java.util.List.of("a", "b");

if (value instanceof java.util.List<?> items) {
    System.out.println("Số phần tử: " + items.size());
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        } else {
            System.out.println("Phần tử không phải String");
        }
    }
}
```

`List<?>` nói rằng giá trị là một list, **không khẳng định kiểu phần tử**. Nếu nghiệp vụ cần mọi phần tử là `String`, phải kiểm tra chúng bằng logic phù hợp. Lưu ý kiểm tra từng phần tử và xử lý phần tử `null` hoặc phần tử khác kiểu tùy hợp đồng đầu vào.

## 5. Không khớp pattern thì điều gì xảy ra?

Khi biểu thức `value instanceof String text` trả về `false`:

- Phần thân `if` tương ứng **không chạy**.
- Pattern variable `text` **không được xem là đã khớp**; không thể dùng nó ở nơi compiler không chứng minh được kết quả `true`.
- Nếu có `else`, chương trình thực hiện nhánh `else`.
- Nếu không có `else`, luồng chương trình tiếp tục sau câu `if`.
- Bản thân một phép `instanceof` không khớp **không ném `ClassCastException`**.

Ví dụ:

```java
static void printAsString(Object value) {
    if (value instanceof String text) {
        System.out.println("Chuỗi: " + text);
    } else {
        System.out.println("Đầu vào không phải chuỗi");
    }

    System.out.println("Tiếp tục xử lý");
}
```

Đầu vào `null`, `Integer`, `List` đều vào `else`, rồi in dòng `Tiếp tục xử lý`. Không có lỗi ép kiểu vì việc truy cập `text` chỉ diễn ra khi pattern khớp.

### 5.1. Dùng nhánh mặc định cho đầu vào đa hình

Giả sử một API nhận `Object`:

```java
static String format(Object value) {
    if (value == null) {
        return "<null>";
    }

    if (value instanceof String text) {
        return "String(" + text.length() + "): " + text;
    }

    if (value instanceof Integer number) {
        return "Integer: " + number;
    }

    return "Không hỗ trợ kiểu: " + value.getClass().getSimpleName();
}
```

Hàm phân biệt ba trường hợp: `null`, kiểu đã hỗ trợ, và kiểu chưa hỗ trợ. Dòng `value.getClass()` được đặt **sau** nhánh xử lý `null`, nên an toàn trong ví dụ này.

Nếu dữ liệu sai kiểu phải bị từ chối, có thể `throw new IllegalArgumentException(...)` ở nhánh cuối thay vì trả chuỗi. Nếu một kiểu không khớp là tình huống hợp lệ, trả kết quả mặc định cũng là lựa chọn hợp lý. `instanceof` chỉ cung cấp thông tin khớp/không khớp, còn ý nghĩa nghiệp vụ của kết quả `false` do bạn quyết định.

### 5.2. Phân biệt kiểm tra kiểu với ép kiểu cưỡng bức

```java
Object value = Integer.valueOf(7);

if (value instanceof String text) {
    // Không vào đây.
}

// Ví dụ cố ý sai ở runtime nếu thực thi:
// String text = (String) value;  // ClassCastException
```

`instanceof` không khớp chỉ cho kết quả `false`. Ép kiểu `(String) value` mà không kiểm tra sẽ có thể phát sinh `ClassCastException` khi đối tượng thực tế không phải `String`. Vì thế, pattern matching thường giúp giảm nguy cơ ép kiểu sai khi xử lý dữ liệu có nhiều kiểu.

## 6. Phạm vi pattern variable khi điều kiện đúng hoặc sai

Java 17 áp dụng cơ chế **flow scoping**: pattern variable chỉ được sử dụng tại những vị trí mà luồng chương trình bảo đảm phép kiểm tra đã thành công. Không nên nghĩ nó có phạm vi đơn giản bằng toàn bộ dấu `{}` hoặc toàn bộ phương thức.

### 6.1. Trong nhánh `if` khi kiểm tra thành công

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    } else {
        // System.out.println(text); // Lỗi compile: chưa có bảo đảm pattern khớp
    }

    // System.out.println(text); // Lỗi compile trong luồng này
}
```

Nhánh `else` được chọn **vì** pattern không khớp, nên không thể dùng `text` như một giá trị `String` tại đó.

### 6.2. `&&` hoạt động đúng nhờ đánh giá ngắn mạch

```java
static boolean isNonBlankString(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Biểu thức bên phải `&&` chỉ được đánh giá khi bên trái là `true`. Vì vậy, tại `!text.isBlank()`, compiler biết `text` đã được gán bằng một `String` hợp lệ. Với `null` hoặc kiểu khác, vế trái là `false`, vế phải không chạy và toàn biểu thức trả về `false`.

### 6.3. `||` không bảo đảm pattern đã khớp

Ví dụ cố ý không biên dịch được:

```java
Object value = "hello";

// Lỗi compile: nếu vế trái false, vế phải vẫn chạy khi text chưa khớp.
if (value instanceof String text || text.isBlank()) {
    System.out.println("...");
}
```

Với `||`, khi vế trái **sai**, Java phải đánh giá vế phải để xác định kết quả. Nhưng lúc đó pattern variable `text` chưa được thiết lập. Compiler từ chối truy cập `text` tại vị trí không an toàn.

Hãy dùng `&&` khi vế phải cần dữ liệu từ một phép khớp ở vế trái:

```java
if (value instanceof String text && text.isBlank()) {
    System.out.println("Chuỗi rỗng hoặc chỉ gồm khoảng trắng");
}
```

Nếu muốn xử lý thêm trường hợp **không khớp**, hãy viết nhánh riêng cho dễ hiểu:

```java
if (value instanceof String text) {
    if (text.isBlank()) {
        System.out.println("Chuỗi trống");
    }
} else {
    System.out.println("Không phải String hoặc là null");
}
```

### 6.4. Khi phủ định điều kiện và thoát sớm

Pattern variable có thể được dùng **sau `if`** nếu nhánh không khớp chắc chắn thoát khỏi phương thức:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }

    // Đi được tới đây nghĩa là pattern đã khớp.
    return text.length();
}
```

Đây là **guard clause** hữu ích khi cần từ chối ngay `null` hoặc đối tượng sai kiểu. Lưu ý dấu `!` phủ định kết quả của toàn biểu thức `instanceof`, còn biến `text` vẫn chỉ có giá trị tại nơi pattern đã khớp.

Ngược lại, nếu nhánh kiểm tra không khớp **không thoát** mà chỉ in log rồi tiếp tục, bạn không thể mặc định dùng `text` bên ngoài `if`.

## 7. Kiểm tra nhiều kiểu: thứ tự nhánh và trường hợp không khớp

Trong ứng dụng thực tế, nhiều kiểu có thể liên quan theo quan hệ kế thừa. Chẳng hạn `Integer` và `Double` đều là `Number`.

```java
static String numberKind(Object value) {
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    if (value instanceof Double decimal) {
        return "Double: " + decimal;
    }
    if (value instanceof Number number) {
        return "Number khác: " + number;
    }
    return "Không phải số";
}
```

Ở đây kiểm tra **kiểu cụ thể trước**, kiểu cha `Number` sau. Nếu đặt `value instanceof Number number` lên đầu, mọi `Integer` và `Double` sẽ vào nhánh `Number`, khiến các nhánh cụ thể phía sau không được thực hiện theo luồng `if` có `return` này.

Đây là vấn đề **thứ tự xử lý** chứ không phải bản thân pattern có lỗi: một đối tượng `Integer` thực sự khớp cả pattern `Integer` và `Number` khi được kiểm tra từ một biểu thức có kiểu tĩnh đủ tổng quát như `Object`.

Với một kiểu không phải số, ví dụ `"12"`, tất cả điều kiện đều trả về `false` và hàm trả `Không phải số`. Không có quá trình chuyển chuỗi thành số ngầm định.

## 8. Chương trình Java 17 hoàn chỉnh: phân loại `null`, khớp và không khớp

Tạo tệp `InstanceofCases.java`:

```java
public class InstanceofCases {
    public static void main(String[] args) {
        inspect(null);
        inspect("  Java 17  ");
        inspect(21);
        inspect(7L);
        inspect(new Object());
        inspect("   ");
    }

    static void inspect(Object value) {
        if (value == null) {
            System.out.println("Giá trị null");
        } else if (value instanceof String text && !text.isBlank()) {
            System.out.println("Chuỗi: " + text.strip());
        } else if (value instanceof String blankText) {
            System.out.println("Chuỗi trống: dài " + blankText.length());
        } else if (value instanceof Integer number) {
            System.out.println("Số nguyên Integer: " + number);
        } else if (value instanceof Number number) {
            System.out.println("Number khác: " + number);
        } else {
            System.out.println("Không khớp: "
                    + value.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac InstanceofCases.java
java InstanceofCases
```

Kết quả:

```text
Giá trị null
Chuỗi: Java 17
Số nguyên Integer: 21
Number khác: 7
Không khớp: Object
Chuỗi trống: dài 3
```

Những điểm đáng chú ý:

1. `null` đi vào nhánh `value == null`. Nếu không có nhánh đó, mọi type pattern đều không khớp và chương trình có thể đi đến nhánh mặc định.
2. Chuỗi có nội dung khớp `String text && !text.isBlank()` nên được xử lý sau khi cắt khoảng trắng hai đầu bằng `strip()`.
3. `21` được autobox thành đối tượng `Integer` khi truyền vào tham số `Object`, sau đó khớp `Integer number`.
4. `7L` được autobox thành `Long`, không khớp `Integer`, nhưng khớp `Number`.
5. `new Object()` không khớp các kiểu chuyên biệt nên đến nhánh cuối.
6. Chuỗi chỉ chứa khoảng trắng không khớp vế `!text.isBlank()` của điều kiện đầu, nhưng vẫn khớp type pattern `String blankText` ở nhánh tiếp theo; biến `blankText` được gán lại qua một **phép kiểm tra độc lập**.

Trong một API nhận dữ liệu từ nhiều nguồn, mẫu kiểm tra này giúp xử lý rõ ràng dữ liệu chưa có, dữ liệu đúng loại, và dữ liệu ngoài phạm vi hỗ trợ.

## 9. `instanceof` với interface và kiểu tổng quát

Không nhất thiết phải kiểm tra class cụ thể. Một pattern có thể kiểm tra interface mà đối tượng triển khai:

```java
interface Printable {
    String printText();
}

class Invoice implements Printable {
    @Override
    public String printText() {
        return "Hóa đơn";
    }
}

class OtherValue {
}

public class InterfacePatternDemo {
    public static void main(String[] args) {
        printIfPossible(new Invoice());
        printIfPossible(new OtherValue());
        printIfPossible(null);
    }

    static void printIfPossible(Object value) {
        if (value instanceof Printable printable) {
            System.out.println(printable.printText());
        } else {
            System.out.println("Không hỗ trợ in");
        }
    }
}
```

Kết quả:

```text
Hóa đơn
Không hỗ trợ in
Không hỗ trợ in
```

Một kiểu có thể không nằm cùng nhánh class với interface được kiểm tra nhưng vẫn **có thể** triển khai interface đó; Java cho phép nhiều quan hệ kiểu hợp lệ thông qua interface. Vì vậy, việc đánh giá tính tương thích khi compile không chỉ là so tên class, mà dựa trên **quy tắc chuyển đổi kiểu tham chiếu** của Java 17.

Khi một interface đại diện cho năng lực, ví dụ `Printable`, kiểm tra interface thường linh hoạt hơn liệt kê từng class cụ thể. Một class triển khai mới sau này vẫn được hỗ trợ mà không cần thay đổi câu `instanceof Printable printable`.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `instanceof` trả `false` khi biến là `null` | `null` không khớp type pattern Java 17. | Nếu cần thông báo riêng, dùng `value == null` trước. |
| `false` dù nhìn thấy dữ liệu giống nhau | Kiểu runtime khác kiểu được kiểm tra; `instanceof` không so sánh nội dung hay chuyển đổi giá trị. | Phân biệt kiểm tra kiểu với so sánh bằng `equals` hoặc parse dữ liệu. |
| Compiler báo `inconvertible types` | Kiểu tĩnh và kiểu pattern không thể có quan hệ hợp lệ. | Kiểm tra lại mô hình dữ liệu và kiểu được khai báo. |
| Compiler báo kiểm tra pattern thừa / kiểu biểu thức đã là subtype | Pattern không được dùng để kiểm tra một kiểu mà compiler đã biết là kiểu con. | Dùng trực tiếp biến hoặc `!= null` khi chỉ muốn kiểm tra `null`. |
| Compiler báo không tìm thấy pattern variable trong `else` | Variable chỉ chắc chắn được gán khi pattern khớp. | Chỉ dùng trong nhánh đúng hoặc tại nơi flow scoping cho phép. |
| Compiler báo không thấy biến ở vế phải `||` | Vế phải có thể chạy khi pattern bên trái `false`. | Dùng `&&` cho điều kiện cần truy cập biến đã khớp, hoặc chia nhánh. |
| Compiler không chấp nhận `List<String>` trong `instanceof` | Tham số generic không kiểm tra đầy đủ được ở runtime. | Dùng `List<?>`, rồi kiểm tra phần tử nếu cần. |
| Đầu vào `"12"` không khớp `Integer` | Đó là `String`, không phải wrapper `Integer`. | Kiểm tra `String` rồi parse số bằng API thích hợp. |
| Một nhánh tổng quát bắt hết các đối tượng | Kiểm tra superclass/interface trước nhánh cụ thể trong chuỗi `if/else if`. | Xử lý nhánh cụ thể trước hoặc thiết kế xử lý đa hình bằng interface. |
| `NullPointerException` xuất hiện ở biểu thức chứa `instanceof` | Một thao tác trước phép kiểm tra đã dereference `null`. | Đảm bảo biểu thức bên trái được đánh giá an toàn, không gọi phương thức trên `null`. |

Lưu ý thông báo lỗi biên dịch cụ thể có thể khác nhau giữa `javac`, IDE và từng bản cập nhật JDK; phần quan trọng là xác định được **lỗi kiểu khi compile** hay **pattern không khớp khi chạy**.

## 11. Bài tập tự luyện

### Bài tập 1 — Kết quả với `null`

```java
Object input = null;

if (input instanceof String text && text.length() > 2) {
    System.out.println("A");
} else {
    System.out.println("B");
}
```

**Câu hỏi:** Chương trình in gì? Có ném `NullPointerException` không?

**Đáp án:** In `B`, không ném ngoại lệ. Vế `input instanceof String text` là `false`, nên `text.length()` không được đánh giá.

### Bài tập 2 — Kiểu tĩnh và kiểu runtime

```java
Object a = "42";
Object b = Integer.valueOf(42);

System.out.println(a instanceof Integer);
System.out.println(b instanceof Integer);
```

**Đáp án:** `false` rồi `true`. `"42"` là chuỗi; `42` được bọc trong `Integer`. Hai biến đều khai báo kiểu tĩnh `Object` nên cả hai phép kiểm tra đều hợp lệ ở compile-time.

### Bài tập 3 — Phát hiện lỗi compile

```java
String message = "hello";

// A
if (message instanceof Integer n) {
    System.out.println(n);
}

// B
if (message instanceof String text) {
    System.out.println(text);
}
```

**Đáp án:** Cả A và B đều bị từ chối trong Java 17. A có kiểu không tương thích; B kiểm tra pattern thừa vì kiểu tĩnh `String` đã là subtype của kiểu được kiểm tra. Để kiểm tra đối tượng có phải `String` hay không, dùng biến có kiểu tĩnh phù hợp như `Object`. Nếu chỉ muốn biết `message` có `null` không, dùng `message != null`.

### Bài tập 4 — Sửa lỗi phạm vi biến

```java
static boolean longText(Object value) {
    // Hãy sửa điều kiện này:
    // return value instanceof String text || text.length() > 5;
    return value instanceof String text && text.length() > 5;
}
```

**Đáp án:** Đổi `||` thành `&&`. Phép kiểm tra bên trái phải đúng thì mới được phép đọc `text` ở vế phải, đồng thời hàm trả `false` khi `value` là `null` hoặc không phải `String`.

### Bài tập 5 — Xử lý dữ liệu ngoài phạm vi hỗ trợ

Viết phương thức `read(Object value)` theo yêu cầu: `null` trả `"missing"`, `String` trả nội dung được `strip()`, `Integer` trả chuỗi biểu diễn số, còn kiểu khác trả `"unsupported"`. Áp dụng pattern matching cho `instanceof` và không ép kiểu thủ công.

Gợi ý:

```java
static String read(Object value) {
    if (value == null) {
        return "missing";
    }
    if (value instanceof String text) {
        return text.strip();
    }
    if (value instanceof Integer number) {
        return number.toString();
    }
    return "unsupported";
}
```

Hãy thử với `null`, `" abc "`, `12`, `12L` và `new Object()` để thấy sự khác nhau giữa **khớp**, **không khớp**, và **trường hợp cần nhánh mặc định**.

## 12. Tổng kết cách ra quyết định

Khi gặp một biểu thức `value instanceof T variable` trong Java 17, hãy suy nghĩ theo thứ tự:

1. **Biểu thức có hợp lệ về kiểu tại compile-time không?** Nếu kiểu tĩnh không thể chuyển đổi sang `T`, hoặc type pattern là phép kiểm tra thừa vì kiểu tĩnh đã là subtype của `T`, compiler từ chối.
2. **Giá trị runtime có phải `null` không?** Nếu có, type pattern không khớp và kết quả là `false`.
3. **Đối tượng runtime có thuộc `T` không?** Nếu có, pattern khớp và biến được sử dụng ở những vị trí được flow scoping cho phép. Nếu không, biểu thức trả về `false`.
4. **Khi không khớp cần làm gì?** Tùy hợp đồng API, chọn nhánh `else`, giá trị mặc định, thông báo lỗi, hoặc `throw` ngoại lệ; đừng dùng pattern variable ở nơi không được bảo đảm đã khớp.

Đây là cơ sở để khai thác pattern matching cho `instanceof` an toàn: không cần ép kiểu thủ công, vẫn kiểm soát được `null`, kiểu dữ liệu không mong đợi, và luồng xử lý sau mỗi kết quả kiểm tra.

### Tài liệu tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394) — đề xuất trở thành tính năng chính thức của Java 16 và có trong Java 17.
- [Java Language Specification SE 17 — §15.20.2 Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — quy tắc kiểu, kết quả runtime và type pattern.
- [Java Language Specification SE 17 — §6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) — phạm vi và flow scoping của pattern variables.
- [Java Language Specification SE 17 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30) — cú pháp và ý nghĩa của type pattern.

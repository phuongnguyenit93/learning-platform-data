# Gộp kiểm tra kiểu, chuyển kiểu và khai báo biến bằng mẫu instanceof

## Mục tiêu

Trong Java hiện đại, **type pattern cho toán tử `instanceof`** cho phép gom ba thao tác thường phải viết riêng — kiểm tra kiểu, ép kiểu và khai báo biến có kiểu cụ thể — thành một biểu thức dễ đọc và được trình biên dịch kiểm tra.

Sau bài này bạn có thể:

- Viết đúng cú pháp `expression instanceof Type variable` và sử dụng pattern variable khi phép thử khớp.
- Hiểu vì sao pattern variable chỉ hợp lệ tại nơi compiler **biết chắc kiểm tra kiểu thành công**, tức *flow scoping / definite matching*.
- Kết hợp đúng với `if/else`, `&&`, `||`, phủ định `!` và guard clause.
- Xác định cách `null`, generics, kiểu tham chiếu và type erasure tác động đến `instanceof`.
- Biên dịch/chạy chương trình Java 17+ và kiểm chứng các ca đúng kiểu, sai kiểu, chuỗi rỗng, `null`, điều kiện ngắn mạch.

**Tương thích phiên bản:** Pattern matching for `instanceof` là tính năng **chính thức từ Java 16** và tiếp tục được hỗ trợ trong Java hiện đại. Các ví dụ chạy trên **JDK 17 trở lên**, không dùng `--enable-preview` hay cú pháp thử nghiệm của Java 14. Đây là kiến thức vẫn đang được áp dụng.

## 1. Bài toán: kiểm tra kiểu, cast, khai báo biến

Khi một giá trị được khai báo là `Object`, lúc chạy nó có thể là `String`:

```java
Object value = "Hello";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Cách viết trên **vẫn hợp lệ** trong Java, nhưng phải lặp lại `String` và biểu thức `value`:

1. `value instanceof String` kiểm tra đối tượng có tương thích với `String` hay không.
2. `(String) value` là phép ép kiểu tham chiếu sau khi đã biết kiểm tra đúng.
3. `String text` tạo biến cục bộ để sử dụng các phương thức của chuỗi.

Với **type pattern**, ba việc này được gộp:

```java
Object value = "Hello";
if (value instanceof String text) {
    System.out.println(text.length()); // 5
}
```

Cú pháp `value instanceof String text` gồm:

- `value`: biểu thức được kiểm tra.
- `String`: kiểu tham chiếu mục tiêu.
- `text`: **pattern variable** nhận chính tham chiếu đã khớp và có kiểu `String` trong những phạm vi hợp lệ.

Nếu biểu thức kiểm tra đúng, trình biên dịch cho phép dùng `text.length()` mà không phải viết cast `(String)`. Java **không tạo một chuỗi mới** vì pattern khớp; nó ràng buộc cùng tham chiếu dưới kiểu đã kiểm tra. Kiểu khai báo gốc của `value` vẫn là `Object`.

Type pattern không phải một phép chuyển đổi dữ liệu tùy ý. Ví dụ, `String` không tự biến thành `Integer` và một chuỗi số không tự được parse thành số. Nó cũng không loại bỏ nhu cầu xác thực dữ liệu nghiệp vụ sau khi kiểm tra kiểu thành công.

## 2. Ý nghĩa runtime, tính an toàn và null

Xét phương thức minh họa (phải đặt trong một class để biên dịch):

```java
static String describeKind(Object input) {
    if (input instanceof String text) {
        return "TEXT:" + text.length();
    }
    if (input instanceof Integer number) {
        return "INTEGER:" + number.intValue();
    }
    return input == null ? "NULL" : "OTHER";
}
```

Mỗi nhánh đúng có một pattern variable với **kiểu cụ thể** tương ứng. `Integer` ở đây là wrapper class của `int`; `instanceof Integer number` kiểm tra một kiểu tham chiếu, không phải mẫu primitive `int`. Nếu đầu vào là `Long`, nó không khớp với `Integer` chỉ vì cả hai là số.

**Null không khớp type pattern**:

```java
Object value = null;
if (value instanceof String text) {
    System.out.println(text.length()); // Không chạy.
}
```

Phép thử trên trả `false`, không tự ném `NullPointerException`. Nhưng nếu bạn gọi `value.toString()` **trước** phép thử thì vẫn có thể bị NPE. Khi cần phân biệt null và đối tượng sai kiểu, thêm nhánh `value == null` phù hợp.

Phép cast tường minh `(String) value` có thể ném `ClassCastException` nếu kiểu runtime không phù hợp. Type pattern cung cấp chứng cứ từ phép thử, nên code trong nhánh khớp không cần một phép cast lặp lại. Điều đó giảm nguy cơ cast nhầm, nhất là khi xử lý dữ liệu đầu vào không đồng nhất.

## 3. Flow scoping: biến pattern có phạm vi theo đường chạy

Pattern variable **không mặc nhiên tồn tại từ nơi khai báo cho đến cuối method**. Compiler xác định vị trí nào đã *definitely matched*: mọi đường thực thi đến vị trí đó đều phải chứng minh pattern đã khớp.

### 3.1. Nhánh đúng của if

```java
Object item = "Java";
if (item instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: 4.
} else {
    System.out.println("not a String");
}
// Không dùng text ở đây; nhánh không khớp cũng có thể đi tới đây.
```

Trong nhánh `if` đúng, `text` đã được ràng buộc. Trong `else` hoặc sau `if` không có loại trừ đường sai, compiler không thể giả định rằng biến này tồn tại.

### 3.2. Kết hợp an toàn bằng &&

```java
if (item instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase(java.util.Locale.ROOT));
}
```

`&&` sử dụng **short-circuit evaluation**: vế phải chỉ được đánh giá khi vế trái đúng. Vì vậy khi vế phải gọi `text.length()`, pattern đã khớp và `text` chắc chắn có kiểu `String`.

Nếu muốn kiểm tra **độ dài sau khi bỏ khoảng trắng**, cần chủ động dùng `text.strip().length()`, không mặc định rằng điều kiện `text.length()` đã làm sạch đầu vào.

### 3.3. Cú pháp sai với ||

```java
// MÃ CỐ Ý SAI (KHÔNG BIÊN DỊCH):
if (item instanceof String text || text.isBlank()) {
    System.out.println("checked");
}
```

`||` chỉ cần đánh giá vế phải khi vế trái **sai**; đó chính là lúc type pattern **không khớp**, nên `text` không có phạm vi hợp lệ bên vế phải.

Tuy nhiên, **không phải mọi lần dùng `||` với pattern đều sai**. Với điều kiện phủ định:

```java
if (!(item instanceof String text) || text.isBlank()) {
    System.out.println("not a usable string");
}
```

Đây là **đoạn mã hợp lệ**: để tới `text.isBlank()`, vế trái phủ định phải là `false`, tức `item instanceof String text` đã đúng. Quy tắc thực tế là **biến chỉ được dùng ở đường đã khớp**, không phải cấm một toán tử theo tên.

### 3.4. Guard clause với phủ định

```java
static String normalize(Object item) {
    if (!(item instanceof String text)) {
        return "-";
    }
    return text.strip();
}
```

Với `normalize("  Java ")`, kết quả là `"Java"`; với `normalize(7)`, kết quả là `"-"`. Dù `text` xuất hiện **sau** câu `if`, code vẫn hợp lệ: đường mà pattern không khớp đã kết thúc method bằng `return`. Mọi đường còn chạy đến `text.strip()` đều có bằng chứng pattern đã khớp. Đây là một **guard clause** giúp tránh lồng nhiều tầng.

Ngược lại:

```java
// MÃ CỐ Ý SAI:
if (item instanceof String text) {
    System.out.println(text.length());
}
System.out.println(text); // Có thể đi tới mà pattern chưa khớp.
```

Dòng cuối bị từ chối bởi compiler vì không đủ điều kiện flow scoping. Không thể giải quyết chỉ bằng việc đổi độ thụt dòng hoặc đặt thêm ngoặc nhọn quanh một vùng không có bảo đảm khớp.

## 4. Chương trình Java 17+ hoàn chỉnh, chạy được

Lưu nguyên văn mã sau thành **`InstanceofPatternDemo.java`**:

```java
import java.util.Locale;

public final class InstanceofPatternDemo {
    private InstanceofPatternDemo() {
    }

    static String describe(Object value) {
        if (value instanceof String text) {
            String cleaned = text.strip();
            if (cleaned.isEmpty()) {
                return "BLANK";
            }
            return "TEXT:" + cleaned.toUpperCase(Locale.ROOT);
        }

        if (value instanceof Integer number) {
            return "INT:" + (number.intValue() * 2);
        }

        if (value == null) {
            return "NULL";
        }

        return "OTHER:" + value.getClass().getSimpleName();
    }

    static String longEnough(Object candidate) {
        if (candidate instanceof String text && text.length() >= 4) {
            return "LONG:" + text.length();
        }
        return "SHORT_OR_OTHER";
    }

    static String normalizedOrDash(Object candidate) {
        if (!(candidate instanceof String text)) {
            return "-";
        }
        String cleaned = text.strip();
        return cleaned.isEmpty() ? "-" : cleaned;
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Object[] values = {
                "  Java  ",
                Integer.valueOf(42),
                "",
                null,
                new StringBuilder("builder"),
                "  "
        };

        String[] expected = {
                "TEXT:JAVA",
                "INT:84",
                "BLANK",
                "NULL",
                "OTHER:StringBuilder",
                "BLANK"
        };

        for (int i = 0; i < values.length; i++) {
            String actual = describe(values[i]);
            check(expected[i].equals(actual), "case " + i);
            System.out.println(actual);
        }

        check(longEnough("Java").equals("LONG:4"), "and true");
        check(longEnough("Hi").equals("SHORT_OR_OTHER"),
                "and false");
        check(normalizedOrDash("  Clean  ").equals("Clean"),
                "guard matched");
        check(normalizedOrDash(10).equals("-"),
                "guard unmatched");

        System.out.println("and Java = " + longEnough("Java"));
        System.out.println("and Hi = " + longEnough("Hi"));
        System.out.println("guard = " + normalizedOrDash("  Clean  "));
        System.out.println("guard number = " + normalizedOrDash(10));
    }
}
```

Chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac --release 17 InstanceofPatternDemo.java
java InstanceofPatternDemo
```

**Stdout mong đợi chính xác:**

```text
TEXT:JAVA
INT:84
BLANK
NULL
OTHER:StringBuilder
BLANK
and Java = LONG:4
and Hi = SHORT_OR_OTHER
guard = Clean
guard number = -
```

**Giải thích kết quả:**

1. `"  Java  "` khớp `String text`, được `strip()` thành `"Java"` rồi `toUpperCase(Locale.ROOT)` thành `"JAVA"`. `value` vẫn có kiểu khai báo `Object`; `text` có kiểu cụ thể `String` tại nhánh khớp.
2. `Integer.valueOf(42)` không khớp `String` nhưng khớp `Integer number`, kết quả `42 * 2 = 84`. Ví dụ này không ngụ ý phép nhân `int` luôn an toàn khi đầu vào lớn; đây chỉ là ca kiểm chứng có kiểm soát.
3. `""` và `"  "` đều **khớp kiểu String**, nhưng sau chuẩn hóa là chuỗi rỗng, nên `BLANK`. Kiểm tra kiểu khác với kiểm tra tính hợp lệ nghiệp vụ.
4. `null` không khớp pattern nào, được xử lý riêng trước `getClass()` để không gây NPE.
5. `StringBuilder("builder")` không khớp `String` hay `Integer`, trả `OTHER:StringBuilder`. `getSimpleName()` chỉ phục vụ hiển thị tình huống mẫu.
6. `longEnough` minh họa vế phải của `&&` sử dụng pattern variable hợp lệ, kiểm tra cả trường hợp đạt độ dài và không đạt.
7. `normalizedOrDash` minh họa guard clause phủ định: đường không khớp đã `return`, còn đường tiếp tục dùng được `text` an toàn.
8. `check` ném `AssertionError` nếu kết quả khác kỳ vọng. Bởi vậy chương trình có những kiểm chứng nội bộ, không chỉ in các dòng không được xác nhận.

`--release 17` yêu cầu ngôn ngữ và API tương thích với Java 17 khi dùng compiler hỗ trợ cờ này. Nếu cần bảo đảm môi trường triển khai, phải chạy chương trình bằng chính runtime phù hợp.

## 5. Bảng xác định phạm vi biến từ điều kiện

| Vị trí dùng biến | Hợp lệ? | Vì sao |
| --- | --- | --- |
| Nhánh đúng của `if (obj instanceof String s)` | **Có** | Pattern đã khớp khi vào nhánh |
| Vế phải của `obj instanceof String s && s.length() > 0` | **Có** | `&&` chỉ đánh giá khi vế trái đúng |
| Vế phải của `obj instanceof String s || s.isEmpty()` | **Không** | `||` có thể đánh giá khi pattern sai |
| Vế phải của `!(obj instanceof String s) || s.isEmpty()` | **Có** | Đi đến vế phải chứng minh pattern gốc đúng |
| Sau `if (!(obj instanceof String s)) return;` | **Có** | Đường không khớp không đi tiếp |
| Sau `if (obj instanceof String s) { ... }` thông thường | **Không được giả định** | Nhánh không khớp vẫn có thể đi tiếp |
| Trong `else` của `if (obj instanceof String s)` | **Không** | Đó là đường pattern không khớp |
| Trong nhánh có điều kiện ngắn mạch phức tạp | **Tùy luồng** | Cần chứng minh pattern chắc chắn đã khớp |

**Mẹo đọc code:** Đừng hỏi “biến này có nằm trong cùng một cặp ngoặc nhọn không?”; hãy hỏi “liệu có đường chạy nào đến dòng này mà pattern chưa khớp không?”. Nếu có, không được sử dụng pattern variable tại đó.

## 6. Generic type, kiểu tham chiếu và ràng buộc compiler

### 6.1. Kiểu generic có tham số chưa được chứng minh bởi instanceof

Ví dụ **hợp lệ trong một method**:

```java
Object candidate = java.util.List.of("a", "b");
if (candidate instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
```

Type pattern với `List<?>` chỉ cho biết đối tượng là một `List` với **kiểu phần tử không xác định**. Nó không chứng minh mỗi phần tử đều là `String`. Nếu muốn xử lý phần tử an toàn:

```java
if (candidate instanceof java.util.List<?> items) {
    for (Object element : items) {
        if (element instanceof String word) {
            System.out.println(word.toUpperCase(
                    java.util.Locale.ROOT));
        }
    }
}
```

Ngược lại, mã sau **cố ý sai khi biên dịch** với một `Object` bất kỳ:

```java
// CỐ Ý SAI:
if (candidate instanceof java.util.List<String> words) {
    System.out.println(words.size());
}
```

Tham số kiểu `String` bị xóa ở runtime theo cơ chế *type erasure*; `instanceof` không thể tự xác minh `List<String>` theo cách này. Dùng `List<?>` rồi kiểm tra phần tử nếu contract cần kiểu cụ thể.

### 6.2. Không phải bất kỳ cặp kiểu nào cũng hợp lệ

```java
Integer number = 42;
// if (number instanceof String text) { ... } // CỐ Ý SAI.
```

Hai kiểu không có quan hệ phù hợp cho phép kiểm tra theo kiểu pattern này. Compiler có thể xác định kiểm tra bất khả thi từ **kiểu tĩnh** của biểu thức và từ chối, ngay trước runtime. Khi một giá trị khai báo là `Object` hoặc interface chung, nhiều phép kiểm tra runtime subtype phù hợp có thể được viết.

### 6.3. Không phải công cụ chuyển primitive hoặc parse dữ liệu

`Object value = 42;` chứa một `Integer` do boxing; kiểm tra `value instanceof Integer number` phù hợp. Trong chương trình biên dịch với `--release 17`, `value instanceof int n` **không** là type pattern tham chiếu hợp lệ. Muốn chuyển `"42"` thành số, cần `Integer.parseInt` với contract và xử lý `NumberFormatException` riêng, không thể dùng `instanceof` để thực hiện chuyển văn bản thành số.

## 7. Các lỗi thường gặp

### Lỗi 1 — Dùng pattern variable ngoài phạm vi ràng buộc

```java
// CỐ Ý SAI:
if (value instanceof String s) {
    System.out.println(s.length());
}
System.out.println(s);
```

Sau `if`, vẫn có đường không khớp đi đến dòng cuối. Hãy chuyển logic cần biến vào nhánh đúng hoặc dùng guard clause phù hợp.

### Lỗi 2 — Dùng || theo chiều sai

```java
// CỐ Ý SAI:
if (value instanceof String s || s.length() == 0) {
    // ...
}
```

Khi vế phải chạy, vế trái `instanceof` đã sai; `s` chưa được ràng buộc. Dùng `&&` nếu vế phải chỉ có nghĩa với `String`, hoặc điều kiện phủ định thích hợp nếu muốn xét dữ liệu không đúng kiểu.

### Lỗi 3 — Đặt tên trùng biến đang có

```java
// CỐ Ý SAI:
String text = "old";
Object input = "new";
if (input instanceof String text) {
    System.out.println(text);
}
```

Tên biến pattern xung đột với biến cục bộ `text` có phạm vi đang bao quanh. Đổi thành `matchedText` hoặc tổ chức lại phạm vi; flow scoping không vô hiệu các quy tắc trùng tên của Java.

### Lỗi 4 — Tưởng null sẽ khớp mẫu String

```java
Object value = null;
if (value instanceof String s) {
    System.out.println(s);
}
```

Mã này **hợp lệ nhưng không in gì**. `null` không khớp. Xử lý trường hợp null bằng nhánh rõ ràng nếu cần.

### Lỗi 5 — Viết lại cast sau khi đã có biến pattern

```java
if (value instanceof String s) {
    System.out.println(((String) value).length());
}
```

Mã này có thể chạy nhưng lặp phép cast không cần thiết. `s.length()` rõ ý định hơn, và không cần lặp biểu thức nguồn nếu biểu thức nguồn phức tạp.

### Lỗi 6 — Nhầm kiểm tra kiểu với xác thực dữ liệu

`input instanceof String s` không chứng minh chuỗi đã chuẩn hóa, không rỗng, đúng mẫu mã sản phẩm hay có độ dài hợp lệ. Sau khi khớp, vẫn phải làm validation thích hợp, ví dụ `!s.isBlank()` hoặc kiểm tra miền giá trị.

### Lỗi 7 — Lạm dụng instanceof thay cho đa hình

Nếu kiểu chung có interface mô tả hành vi cần dùng, gọi polymorphic method thường dễ mở rộng hơn một chuỗi nhiều `if (x instanceof A a)`. Pattern hữu ích khi ranh giới dữ liệu thực sự chứa những loại tham chiếu khác nhau hoặc khi xử lý theo từng kiểu có chủ ý.

## 8. Cách áp dụng và kiểm thử thực tế

**Khi dùng `Object` hoặc API không đồng nhất:** Type pattern phân loại an toàn và truy cập phương thức của kiểu đã biết mà không lạm dụng cast.

**Khi có điều kiện dựa trên kiểu:** `if (input instanceof String s && !s.isBlank())` gắn việc kiểm tra kiểu và ràng buộc nghiệp vụ trong một điều kiện ngắn mạch rõ ràng. Với logic dài, nên tách thành guard clause hoặc method riêng để hạn chế nhầm phạm vi.

**Khi cần từ chối đầu vào sớm:** `if (!(input instanceof String s)) return "INVALID";` cho phép phần tiếp theo xử lý dữ liệu đã đúng kiểu, giảm độ sâu lồng `if`.

**Khi đặt tên:** Dùng tên phản ánh vai trò (`text`, `number`, `items`) và tránh xung đột biến cục bộ. Java hiện đại cho phép các thao tác gán lại pattern variable trong một số trường hợp, nhưng code thường dễ theo dõi hơn nếu bạn dùng một tên rõ nghĩa và tạo biến mới khi cần giá trị được chuẩn hóa.

**Khi kiểm thử:** Có cả ca đúng kiểu, sai kiểu, `null`, chuỗi rỗng/trắng, độ dài sát ngưỡng của vế phải `&&`. Cần kiểm tra cả đường mà vế phải **không được đánh giá**, không chỉ đường khớp hoàn toàn.

## 9. Bài tự thực hành

Viết `static String normalizeIdentifier(Object input)` với contract:

1. Nếu đầu vào **không phải `String`**, trả `"INVALID_TYPE"`; `null` cũng trả `"INVALID_TYPE"`.
2. Nếu là `String`, dùng `strip()` bỏ khoảng trắng hai đầu. Nếu kết quả rỗng, trả `"EMPTY"`.
3. Nếu chuỗi sau chuẩn hóa dài **ít hơn 3** ký tự, trả `"TOO_SHORT"`.
4. Còn lại trả chuỗi chữ hoa bằng `toUpperCase(Locale.ROOT)`.
5. Không viết cast `(String)`; chỉ dùng một type pattern và guard clause.

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `"  java  "` | `"JAVA"` |
| `"ab"` | `"TOO_SHORT"` |
| `""` và `"  "` | `"EMPTY"` |
| `42`, `new Object()` | `"INVALID_TYPE"` |
| `null` | `"INVALID_TYPE"` |

Sau đó thử thay `if (input instanceof String text && text.length() >= 3)` bằng `if (input instanceof String text || text.length() >= 3)`. Dự đoán lỗi biên dịch và lý giải đường chạy khiến `text` chưa có giá trị hợp lệ. Viết tiếp phiên bản `if (!(input instanceof String text)) return "INVALID_TYPE";` rồi dùng `text` ở phần còn lại của method. Tự giải thích vì sao ví dụ thứ hai hợp lệ.

**Tiêu chí hoàn thành:** Bạn có thể chỉ ra rõ ba vai trò **kiểm tra kiểu – cast an toàn – khai báo biến ràng buộc**, và có thể xác định chính xác **phạm vi biến theo luồng** trong cả code hợp lệ lẫn code cố ý sai.

## Tài liệu đối chiếu

- [Oracle Java SE 17 — Pattern Matching for the instanceof Operator](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof-operator.html): cú pháp, flow scoping, `&&`, `||`.
- [Java Language Specification, Java SE 25 — `15.20.2 Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2): kiểm tra kiểu của `instanceof`.
- [Java Language Specification, Java SE 25 — Scope of a Pattern Variable](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): quy tắc phạm vi biến pattern.

**Kết luận:** `obj instanceof Type variable` gộp việc thử kiểu và ràng buộc tham chiếu đã kiểm tra thành biến có kiểu cụ thể. Bước cast thủ công trở nên không cần thiết ở đường khớp; còn **flow scoping** quyết định những nơi được phép dùng biến. Hãy luôn phân tích đường chạy, không chỉ nhìn độ thụt dòng hay toán tử.
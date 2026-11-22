# Type pattern và biến pattern trong `instanceof` — Java 17

## 1. Mục đích của bài học

Trong Java, một biến có kiểu khai báo rộng như `Object` hoặc một interface có thể đang tham chiếu đến đối tượng thuộc một kiểu cụ thể hơn lúc chạy. Trước khi sử dụng các phương thức riêng của kiểu cụ thể đó, chương trình cần xác định đối tượng có đúng kiểu hay không.

Java 17 hỗ trợ **pattern matching for `instanceof`** dưới dạng ổn định. Cú pháp này cho phép **kiểm tra kiểu và khai báo biến đã có kiểu phù hợp trong cùng một biểu thức**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Trong ví dụ:

- `value` là biểu thức cần kiểm tra, có thể có kiểu khai báo `Object`.
- `String` là **kiểu đích** của type pattern.
- `text` là **biến pattern** (*pattern variable*), được gắn với đối tượng khi kiểm tra thành công.
- `text.length()` hợp lệ trong nhánh mà trình biên dịch biết `text` đã được gắn giá trị.

Đây là hai khái niệm khác nhau: **type pattern** mô tả “một giá trị thuộc kiểu `String`, đặt tên là `text`”, còn **biến pattern** là tên có thể được sử dụng tại những vị trí mà kết quả kiểm tra đã bảo đảm thành công.

Tính năng này được hoàn thiện từ **Java 16 (JEP 394)** và sử dụng trực tiếp trong **Java 17**, không cần `--enable-preview`. Bài học chỉ sử dụng cú pháp đã ổn định ở Java 17.

## 2. `instanceof` kiểm tra điều gì?

Biểu thức `instanceof` kiểm tra quan hệ kiểu tại thời điểm chạy. Với một tham chiếu không phải `null`, kiểm tra thành công nếu đối tượng tương thích với kiểu đích theo quy tắc của Java.

```java
Object value = "Java 17";

System.out.println(value instanceof String); // true
System.out.println(value instanceof Number); // false
```

Kiểu khai báo của `value` là `Object`, nhưng đối tượng thật được tham chiếu là một `String`. `instanceof` dựa trên **kiểu của đối tượng thực tế**, không chỉ dựa vào kiểu khai báo của biến.

Khi đối tượng không phù hợp, kết quả là `false`. Khi giá trị là `null`, cả kiểm tra kiểu thông thường và type pattern cũng trả về `false`:

```java
Object nothing = null;

System.out.println(nothing instanceof String); // false
System.out.println(nothing instanceof String s); // false
```

Vì thế, trong nhánh `if (value instanceof String text)`, `text` đã được xác định là tham chiếu tới một `String` không phải `null`.

### Kiểm tra kiểu và lấy biến cùng lúc

Chỉ kiểm tra kiểu:

```java
Object input = "abc";

if (input instanceof String) {
    // Kiểm tra thành công, nhưng chưa khai báo biến String riêng.
}
```

Dùng type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

`text` có kiểu tĩnh là `String`, nên compiler chấp nhận `toUpperCase()`. Biến gốc `input` vẫn có kiểu khai báo `Object`; khai báo pattern **không thay đổi kiểu của biến gốc**.

## 3. Cú pháp của type pattern

Cấu trúc cơ bản trong Java 17:

```java
expression instanceof ReferenceType variableName
```

Ví dụ:

```java
Object item = Integer.valueOf(42);

if (item instanceof Integer number) {
    System.out.println(number.intValue() + 1);
}
```

Biến `number` được khai báo ngay trong type pattern. Trong nhánh đúng, nó tham chiếu đến chính đối tượng mà `item` đang tham chiếu tới; đây không phải thao tác tạo ra một đối tượng `Integer` mới.

Một số type pattern hợp lệ:

```java
Object data = "hello";

if (data instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

```java
Object data = java.util.List.of("A", "B");

if (data instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

`ReferenceType` là kiểu tham chiếu phù hợp. Không thể sử dụng primitive type trực tiếp như `instanceof int value`. Đối với giá trị dạng số có thể chứa trong `Object`, thường kiểm tra wrapper tương ứng (`Integer`, `Long`...) hoặc interface/class cha như `Number`.

Tên biến pattern phải tuân theo quy tắc đặt tên và tránh xung đột với những biến đã ở trong phạm vi tương ứng. Nên đặt tên thể hiện đối tượng sau khi kiểm tra, chẳng hạn `text`, `number`, `request`, `task`, thay vì một tên chỉ có một ký tự trong logic dài.

## 4. Khác biệt giữa type pattern và cách ép kiểu tường minh

Để hiểu vấn đề mà pattern giải quyết, có thể so sánh với cách viết kiểm tra kiểu rồi ép kiểu thành hai bước:

```java
static int lengthIfString(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.length();
    }
    return 0;
}
```

Với Java 17, phần kiểm tra và gắn biến diễn đạt trong một chỗ:

```java
static int lengthIfString(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

| Điểm so sánh | Kiểm tra + cast tường minh | Type pattern trong Java 17 |
|---|---|---|
| Kiểm tra đối tượng | `value instanceof String` | `value instanceof String text` |
| Lấy tham chiếu có kiểu `String` | Viết thêm `(String) value` | Biến `text` được binding khi kiểm tra đúng |
| Khả năng dùng biến | Phụ thuộc phạm vi biến tự khai báo | Phụ thuộc kết quả phân tích luồng điều khiển |
| Nguy cơ dùng sai biến/cast lặp | Dễ phát sinh khi khối mã dài | Giảm lặp và gắn đúng biến với kiểm tra |
| Tương thích Java 17 | Có | Có, là cú pháp ổn định |

Type pattern không biến mọi cast thành thừa. Cast tường minh vẫn hữu ích khi quan hệ kiểu đã chắc chắn theo hợp đồng khác, hoặc khi cần yêu cầu lỗi nếu không tương thích. Nhưng với tình huống **“nếu thuộc kiểu này thì xử lý như kiểu này”**, type pattern thường truyền đạt ý định rõ ràng hơn.

## 5. Biến pattern tồn tại ở đâu? Flow scoping

Điểm quan trọng nhất khi học pattern variable là **phạm vi của nó được xác định theo luồng điều khiển** (*flow scoping*). Compiler chỉ cho dùng biến ở nơi có thể kết luận rằng pattern đã khớp và biến đã được gắn giá trị.

Trong ví dụ thông thường:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Hợp lệ.
    } else {
        System.out.println("Not a String");
        // System.out.println(text);       // Lỗi biên dịch.
    }

    // System.out.println(text);           // Không hợp lệ ở đây.
}
```

Khi điều kiện đúng, `text` tồn tại trong nhánh `if`. Khi điều kiện sai, Java không có một `String` được binding cho `text`. Sau toàn bộ `if` trên, luồng chương trình có thể đi đến từ cả nhánh đúng lẫn nhánh sai, nên không thể dùng `text` một cách an toàn.

**Flow scoping không có nghĩa biến pattern luôn chỉ sống trong cặp ngoặc nhọn đầu tiên.** Nếu luồng điều khiển chứng minh pattern chắc chắn khớp tại vị trí phía sau, biến vẫn có thể được sử dụng.

### 5.1. Phạm vi trong nhánh `if`

```java
static String show(Object obj) {
    if (obj instanceof String s) {
        return "Length = " + s.length();
    }
    return "Different type";
}
```

`s` hợp lệ trong nhánh `if` bởi nhánh này chỉ chạy khi `obj instanceof String s` trả về `true`.

### 5.2. Nhánh thoát sớm và phạm vi phía sau

```java
static String normalize(Object obj) {
    if (!(obj instanceof String text)) {
        return "Not a String";
    }

    // Chỉ có thể đi đến đây nếu pattern String text đã khớp.
    return text.strip();
}
```

Trong trường hợp này, nhánh không khớp đã `return`, nên mọi đường đi còn lại đều đi qua tình huống pattern thành công. Compiler cho phép dùng `text` **sau câu lệnh `if`**.

Điều tương tự áp dụng cho việc ném ngoại lệ:

```java
static String requireString(Object obj) {
    if (!(obj instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text;
}
```

Đây là kiểu kiểm tra đầu vào hữu ích trong các hàm xử lý nhiều nhánh: kiểm tra điều kiện thất bại trước, thoát sớm, rồi xử lý phần chính với biến đã có kiểu phù hợp.

### 5.3. Bảng tình huống về phạm vi

| Biểu thức hoặc luồng | Biến pattern dùng được ở đâu? | Lý do |
|---|---|---|
| `if (o instanceof String s) { ... }` | Trong nhánh đúng | Nhánh đúng bảo đảm `s` đã binding |
| `if (o instanceof String s) { ... } else { ... }` | Không dùng `s` trong nhánh `else` | Nhánh sai không tạo binding |
| `if (o instanceof String s && s.length() > 0)` | Vế phải của `&&` và thân nhánh đúng | Vế phải chỉ chạy khi vế trái đúng |
| `if (o instanceof String s || condition)` | Không thể tùy ý dùng `s` ở vế phải hoặc trong thân `if` | Nhánh có thể đúng do `condition` dù pattern không khớp |
| `if (!(o instanceof String s)) return; ...` | Sau `if` khi đường đi thất bại đã kết thúc | Mọi đường đi còn lại bảo đảm pattern thành công |

## 6. Kết hợp type pattern với `&&`, `||` và `!`

### 6.1. `&&` với điều kiện bổ sung

Đây là một trong những ứng dụng tự nhiên nhất:

```java
static boolean hasLongName(Object obj) {
    return obj instanceof String name && name.length() >= 8;
}
```

Toán tử `&&` đánh giá từ trái sang phải và *short-circuit*: nếu vế trái sai, vế phải không được chạy. Vì vế phải chỉ có thể chạy khi pattern đã khớp, `name.length()` là hợp lệ và an toàn.

Có thể thêm nhiều điều kiện:

```java
static boolean isUsefulLabel(Object obj) {
    return obj instanceof String label
            && !label.isBlank()
            && label.length() <= 50;
}
```

Không cần kiểm tra `label != null` trong chuỗi điều kiện này, vì một pattern `String label` không khớp với `null`.

### 6.2. Vì sao không thể thay `&&` bằng `||`?

```java
static boolean incorrect(Object obj) {
    // LỖI BIÊN DỊCH — không dùng đoạn này trong ứng dụng.
    return obj instanceof String text || text.length() > 3;
}
```

Với `||`, vế phải chỉ được đánh giá khi vế trái **sai**. Đúng lúc đó `text` chưa có binding, nên compiler không cho sử dụng nó.

Mã hợp lệ tương ứng với ý định “là chuỗi và có ít nhất bốn ký tự” là:

```java
static boolean correct(Object obj) {
    return obj instanceof String text && text.length() > 3;
}
```

Ngay cả khi dùng `if (obj instanceof String text || someOtherCondition)`, trong thân `if` vẫn có thể xảy ra tình huống `someOtherCondition` đúng và pattern thất bại; vì vậy không thể coi `text` luôn đã được gắn.

### 6.3. Phủ định pattern bằng `!`

```java
static String trimmedOrDefault(Object obj) {
    if (!(obj instanceof String text)) {
        return "<not text>";
    }
    return text.strip();
}
```

`!(obj instanceof String text)` là phép phủ định của một phép kiểm tra pattern. Khi điều kiện phủ định **sai**, pattern gốc đã **đúng**. Chỉ sau khi đã loại trừ nhánh sai bằng `return` hoặc `throw`, ta mới dùng `text` ở phía sau.

Một ví dụ **không hợp lệ**:

```java
static void bad(Object obj) {
    if (!(obj instanceof String text)) {
        // System.out.println(text); // Lỗi: tại đây pattern không khớp.
    }
}
```

Hãy đọc chiều logic thật của biểu thức, thay vì đoán phạm vi biến chỉ theo vị trí của từ khóa `if`.

## 7. Type pattern kết hợp với nhiều nhánh xử lý

Một phương thức đôi khi nhận các giá trị thuộc một số kiểu xác định. Type pattern giúp mỗi nhánh sử dụng biến đúng kiểu:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String length: " + text.length();
    } else if (value instanceof Integer number) {
        return "Integer doubled: " + (number * 2);
    } else if (value instanceof java.time.LocalDate date) {
        return "Year: " + date.getYear();
    }
    return "Unsupported";
}
```

Trong mỗi nhánh:

- `text` chỉ đại diện cho một `String`.
- `number` chỉ đại diện cho một `Integer`.
- `date` chỉ đại diện cho một `LocalDate`.

Khi đã dùng `return` trong từng nhánh, luồng xử lý kết thúc ngay khi tìm được một kiểu phù hợp.

**Lưu ý thiết kế:** nếu tất cả các lớp đều do ứng dụng kiểm soát và đều cần cùng một hành vi, đôi khi **interface và đa hình** thích hợp hơn chuỗi `instanceof` dài. Pattern matching hữu ích đặc biệt ở ranh giới tích hợp, khi phải nhận kiểu rộng (`Object`), khi phân loại giá trị từ thư viện, hoặc khi kiểu cụ thể không thể thay đổi thiết kế.

## 8. Ranh giới kiểu tĩnh và các lỗi biên dịch thường gặp

### 8.1. Kiểu bên trái phải tương thích với kiểu cần kiểm tra

Đây là ví dụ thường dùng:

```java
Object value = "ok";
if (value instanceof String text) {
    System.out.println(text);
}
```

Nhưng mọi cặp kiểu đều không thể kiểm tra được:

```java
Integer number = 10;
// if (number instanceof String text) {} // Không tương thích kiểu.
```

Giữa `Integer` và `String` không có quan hệ tham chiếu cho phép phép chuyển kiểu như biểu thức trên. Trình biên dịch có thể phát hiện sai ngay, thay vì đợi đến runtime.

### 8.2. Không dùng type pattern khi kiểu đã hiển nhiên theo biểu thức

Trong Java 17, một type pattern bị coi là **unconditional** nếu kiểu tĩnh bên trái đã là subtype của kiểu đích; việc dùng nó trong `instanceof` như sau là không hợp lệ:

```java
String text = "hello";
// if (text instanceof String sameText) {} // Lỗi trong Java 17.
```

Vì `text` đã có kiểu `String`, ta chỉ cần trực tiếp dùng `text`. Nếu điều quan tâm là dữ liệu trống hay không, hãy kiểm tra `text != null` hoặc `!text.isBlank()` theo hợp đồng thực tế.

Trường hợp kiểm tra meaningful là khi **kiểu khai báo rộng hơn kiểu cần thao tác**:

```java
CharSequence sequence = "hello";
if (sequence instanceof String actualString) {
    System.out.println(actualString.toUpperCase());
}
```

### 8.3. Không có type pattern cho primitive

```java
Object value = 17;
// if (value instanceof int n) {} // Không hợp lệ.

if (value instanceof Integer number) {
    System.out.println(number + 1);
}
```

Giá trị literal `17` được boxing thành `Integer` khi gán vào biến `Object`. Đây là lý do có thể so sánh với kiểu `Integer`, nhưng không dùng `int` như một reference type pattern.

### 8.4. Kiểu generic và type erasure

Một đối tượng có thể là `List<String>` hoặc `List<Integer>` ở compile time, nhưng tham số kiểu không phải lúc nào cũng kiểm tra được ở runtime vì **type erasure**.

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> items) {
    System.out.println("Size: " + items.size());
}
```

`List<?>` là lựa chọn hợp lệ khi cần xác nhận đối tượng là một `List` mà chưa biết kiểu phần tử.

Ngược lại:

```java
Object value = java.util.List.of("A", "B");
// if (value instanceof java.util.List<String> strings) {}
// Không hợp lệ với biểu thức kiểu Object: không thể kiểm tra
// tham số String của List theo cách này ở runtime.
```

Khi cần xác thực phần tử, kiểm tra từng giá trị theo hợp đồng:

```java
static boolean allStrings(Object candidate) {
    if (!(candidate instanceof java.util.List<?> items)) {
        return false;
    }
    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Kiểm tra trên chỉ xác thực **những phần tử hiện có**. Nó không chứng minh type parameter khai báo tại nơi tạo danh sách và cũng không tự bảo vệ danh sách mutable khỏi việc được bổ sung phần tử khác về sau.

### 8.5. Tên biến trùng và phạm vi thật

Không nên khai báo một biến pattern có cùng tên với biến cục bộ đang nằm trong phạm vi:

```java
static void print(Object value) {
    String text = "fallback";
    // if (value instanceof String text) {} // Trùng tên biến cục bộ.

    if (value instanceof String candidate) {
        System.out.println(candidate);
    } else {
        System.out.println(text);
    }
}
```

Biến pattern chịu quy tắc tên và phạm vi của Java. Đặt tên rõ ràng giảm nhầm lẫn khi có nhiều nhánh và nhiều kiểu được kiểm tra.

### 8.6. Biến pattern không bắt buộc là `final`

Trong Java 17, pattern variable không mặc nhiên là `final`. Tuy nhiên, việc gán một giá trị khác cho biến vừa được binding có thể khiến người đọc không còn biết biến đang đại diện cho đối tượng được kiểm tra hay một giá trị mới.

Thông thường nên coi biến pattern là **tham chiếu đã được xác nhận kiểu** để đọc hoặc gọi phương thức, và tạo một biến mới nếu cần kết quả biến đổi:

```java
if (value instanceof String text) {
    String normalized = text.strip().toLowerCase(java.util.Locale.ROOT);
    System.out.println(normalized);
}
```

Biến pattern vẫn tuân theo quy tắc của Java đối với lambda capture: nếu được sử dụng trong lambda, nó phải là `final` hoặc *effectively final* tại ngữ cảnh đó.

## 9. Pattern `instanceof` với record, interface và kế thừa

Type pattern dùng được với nhiều reference type, bao gồm interface và record. Điều quan trọng là **pattern đang kiểm tra kiểu đối tượng**, không tự tách các trường bên trong đối tượng.

Ví dụ record trong Java 17:

```java
record Point(int x, int y) {}

static String format(Object value) {
    if (value instanceof Point point) {
        return "(" + point.x() + ", " + point.y() + ")";
    }
    return "Not a point";
}
```

Khi pattern `Point point` khớp, ta dùng accessor `point.x()` và `point.y()` để đọc component.

Không nhầm cú pháp trên với **record pattern** dạng `Point(int x, int y)`. Record patterns được hoàn thiện ở Java 21 và **không phải cú pháp ổn định sẵn có trong Java 17**. Trong mục tiêu Java 17, cách chuẩn là binding `Point point` rồi truy cập component.

Với interface, type pattern có thể kiểm tra một đối tượng có triển khai interface hay không:

```java
interface Named {
    String name();
}

record Employee(String name) implements Named {}

static String display(Object value) {
    if (value instanceof Named person) {
        return person.name();
    }
    return "Unnamed";
}
```

`person` có kiểu tĩnh `Named`, nên chỉ những phương thức interface này công bố mới có thể gọi trực tiếp. Java không tự suy luận `person` là `Employee` chỉ vì một implementation cụ thể được dùng ở đâu đó.

### Thứ tự của các phép kiểm tra có ảnh hưởng

```java
static String categorize(Object value) {
    if (value instanceof Number number) {
        return "Number: " + number;
    }
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    return "Other";
}
```

Đoạn mã này hợp lệ, nhưng nếu `value` là `Integer` thì nhánh `Number` đã khớp trước, nên nhánh `Integer` ở sau không được chạy. Muốn xử lý riêng `Integer`, hãy kiểm tra nó **trước** `Number`:

```java
static String categorize(Object value) {
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    if (value instanceof Number number) {
        return "Number: " + number;
    }
    return "Other";
}
```

Kỹ thuật này áp dụng cho các quan hệ subtype/supertype và khi kiểm tra nhiều interface có thể cùng được một đối tượng triển khai.

## 10. Ví dụ tổng hợp chạy trên Java 17

Chương trình sau nhận dữ liệu qua tham số `Object` và dùng type pattern để xử lý từng kiểu. Record `Ticket` được dùng để minh họa việc binding record như một đối tượng bình thường.

Tạo file `Main.java`:

```java
import java.util.List;

public class Main {
    record Ticket(String code, int priority) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text (" + text.length() + "): " + text;
        }

        if (value instanceof Ticket ticket) {
            return "Ticket " + ticket.code()
                    + ", priority=" + ticket.priority();
        }

        if (value instanceof List<?> items) {
            return "List size: " + items.size();
        }

        if (value == null) {
            return "No value";
        }

        return "Other: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new Ticket("T-42", 2)));
        System.out.println(describe(List.of(10, 20, 30)));
        System.out.println(describe(null));
        System.out.println(describe(""));
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Kết quả dự kiến:

```text
Text (4): Java
Ticket T-42, priority=2
List size: 3
No value
Other: String
```

Phân tích:

1. `"Java"` khớp `String text`, rồi `!text.isBlank()` đúng; nhánh đầu có thể dùng `text.length()`.
2. `new Ticket(...)` không phải `String`, nhưng khớp `Ticket ticket`; phương thức `ticket.code()` là accessor của record.
3. `List.of(...)` khớp `List<?> items`; ta sử dụng thao tác chung của `List` mà không giả định kiểu phần tử.
4. `null` không khớp bất kỳ type pattern nào, được xử lý bởi kiểm tra `value == null`.
5. Chuỗi rỗng vẫn là `String` nhưng `!text.isBlank()` sai, nên rơi đến nhánh cuối. Ví dụ này giúp thấy rõ **khớp kiểu** và **thỏa điều kiện bổ sung** là hai bước logic khác nhau.

Lưu ý: nếu muốn mọi `String` đều đi vào cùng nhánh, nên tách kiểm tra `isBlank()` vào bên trong nhánh `if (value instanceof String text)`, thay vì ghép ở điều kiện `&&`.

## 11. Các tình huống phù hợp trong mã thực tế

### 11.1. Kiểm tra kết quả trả về ở ranh giới API

Khi một API hoặc bộ xử lý plugin trả về `Object`, type pattern giúp kiểm tra trước khi gọi phương thức chuyên biệt:

```java
static int resultCount(Object response) {
    if (response instanceof java.util.Collection<?> collection) {
        return collection.size();
    }
    throw new IllegalArgumentException("Expected a collection");
}
```

Thay vì ép kiểu vô điều kiện và chờ `ClassCastException`, phương thức đưa ra lỗi với ý nghĩa phù hợp hơn với hợp đồng đầu vào.

### 11.2. Xử lý sự kiện nhiều kiểu

```java
interface Event {}
record Connected(String clientId) implements Event {}
record Disconnected(String clientId) implements Event {}

static String eventMessage(Event event) {
    if (event instanceof Connected connected) {
        return "Connected: " + connected.clientId();
    }
    if (event instanceof Disconnected disconnected) {
        return "Disconnected: " + disconnected.clientId();
    }
    return "Unknown event";
}
```

Đây là cách dùng đơn giản khi phải phân loại vài kiểu sự kiện. Nếu API do dự án thiết kế và hành vi nên nằm trong từng loại sự kiện, vẫn nên cân nhắc đa hình hoặc mô hình sealed phù hợp để tránh tập trung quá nhiều nhánh vào một phương thức.

### 11.3. Tránh xử lý bất an toàn với `null`

```java
static String title(Object candidate) {
    if (candidate instanceof CharSequence text && text.length() > 0) {
        return text.toString();
    }
    return "Untitled";
}
```

Nhánh `CharSequence text` chỉ chạy với một đối tượng tương thích không null. Điều này giúp tránh kiểm tra `null` lặp trong chính nhánh đó. Tuy nhiên, nếu logic cần phân biệt riêng giữa `null` và “không đúng kiểu”, vẫn phải kiểm tra rõ từng trường hợp.

## 12. Những hiểu nhầm dễ gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`instanceof String s` đổi kiểu khai báo của biến gốc.” | Biến gốc giữ nguyên kiểu tĩnh; biến pattern `s` có kiểu `String` ở nơi binding hợp lệ. |
| “Dùng `s` được ở mọi nơi sau khi viết pattern.” | Scope phụ thuộc luồng điều khiển: chỉ nơi chắc chắn pattern khớp. |
| “`&&` và `||` cho cùng phạm vi với biến pattern.” | `&&` đánh giá vế phải khi vế trái đúng, còn `||` đánh giá vế phải khi vế trái sai; phạm vi khác nhau. |
| “`instanceof` có thể khớp `null` với type pattern.” | Type pattern `T t` trả về false với `null`. |
| “Có thể kiểm tra `List<String>` từ một `Object` bất kỳ.” | Type erasure ngăn kiểm tra tham số kiểu trong tình huống này; thường dùng `List<?>`, rồi xác thực phần tử khi cần. |
| “Một type pattern có thể dùng primitive `int`.” | Type pattern `instanceof` của Java 17 nhận reference type, như `Integer`, không phải primitive. |
| “Pattern `instanceof` và pattern `switch` hoàn toàn giống nhau trong Java 17.” | Type pattern trong `instanceof` là tính năng ổn định; pattern matching cho `switch` vẫn là preview ở Java 17. |
| “Type pattern tự tách component của record.” | `obj instanceof Point p` chỉ binding biến `p`; đọc component bằng accessor như `p.x()`. |

## 13. Bài tập thực hành có lời giải

### Bài 1 — Dự đoán kết quả

```java
static String inspect(Object value) {
    if (value instanceof String text && text.length() > 2) {
        return "LONG: " + text;
    }
    return "OTHER";
}
```

Dự đoán kết quả cho:

```java
inspect("AB")
inspect("ABC")
inspect(null)
inspect(Integer.valueOf(5))
```

**Đáp án:** lần lượt là `OTHER`, `LONG: ABC`, `OTHER`, `OTHER`. Pattern chỉ gắn biến khi giá trị thực sự là `String`; điều kiện `length() > 2` được kiểm tra sau đó.

### Bài 2 — Xác định chỗ dùng biến pattern sai

```java
static String bad(Object obj) {
    if (obj instanceof String text) {
        return text.toUpperCase();
    }
    return text;
}
```

Dòng `return text;` cuối cùng không hợp lệ: đó là đường đi mà `obj instanceof String text` **không khớp**, nên `text` không được binding. Sửa như sau:

```java
static String fixed(Object obj) {
    if (obj instanceof String text) {
        return text.toUpperCase();
    }
    return "Not text";
}
```

### Bài 3 — Viết điều kiện ngắn và an toàn

Yêu cầu: `true` chỉ khi `value` là `String`, không trắng và dài không quá 20 ký tự.

```java
static boolean validLabel(Object value) {
    return value instanceof String label
            && !label.isBlank()
            && label.length() <= 20;
}
```

Lời giải kết hợp kiểm tra kiểu và điều kiện bổ sung, không gọi method trên tham chiếu `null`.

### Bài 4 — Kiểm tra kiểu rồi thoát sớm

Viết phương thức nhận `Object`, trả về một bản chuẩn hóa của chuỗi sau khi xóa khoảng trắng đầu/cuối; ném `IllegalArgumentException` nếu dữ liệu không phải chuỗi.

```java
static String normalizeOrFail(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected text");
    }
    return text.strip();
}
```

`text` được phép dùng sau câu lệnh `if` do nhánh pattern thất bại đã kết thúc bằng `throw`.

### Bài 5 — Phân biệt `List<?>` với `List<String>`

Hãy viết phương thức nhận `Object` và đếm số phần tử là chuỗi không trắng khi giá trị đó là một `List`; nếu không phải `List`, trả về 0.

```java
static long countNonBlankStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        return 0;
    }
    return items.stream()
            .filter(item -> item instanceof String text && !text.isBlank())
            .count();
}
```

Chú ý: `List<?>` không khẳng định kiểu từng phần tử. Type pattern `String text` được đánh giá riêng cho từng phần tử trong predicate của `filter`.

## 14. Tiêu chí hoàn thành bài học

Người học hiểu **type pattern và biến pattern trong `instanceof`** khi có thể:

1. Giải thích rõ ba phần `expression instanceof Type variable`, phân biệt type pattern với biến pattern.
2. Dự đoán hành vi khi đối tượng có kiểu phù hợp, không phù hợp hoặc bằng `null`.
3. Viết `if (obj instanceof SomeType x)` và sử dụng `x` không cần cast lại.
4. Giải thích tại sao `x` hợp lệ trong nhánh đúng, trong vế phải `&&`, và sau nhánh phủ định kết thúc bằng `return`/`throw`.
5. Chỉ ra lỗi phạm vi trong các ví dụ dùng `||`, nhánh `else` và mã nằm ngoài vùng binding.
6. Nhận biết ràng buộc kiểu tĩnh, primitive và giới hạn type erasure với generic.
7. Áp dụng type pattern vào tình huống có interface, record hoặc kiểu dữ liệu trả về rộng.
8. Biên dịch ví dụ với `javac --release 17`, không dùng cú pháp preview hoặc cú pháp chỉ hoàn thiện ở phiên bản mới hơn.

## 15. Tài liệu chính thức

- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): mô tả mục tiêu, cách binding và flow scoping của pattern variable.
- [Java Language Specification, Java SE 17 — `instanceof` Operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): quy tắc của biểu thức `instanceof`.
- [Java Language Specification, Java SE 17 — Scope of Pattern Variables (§6.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi theo luồng điều khiển.
- [Java Language Specification, Java SE 17 — Patterns (§14.30)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): ngữ pháp và ngữ nghĩa của type pattern.

Điều cốt lõi là nhớ **`instanceof` xác nhận kiểu của đối tượng; type pattern đồng thời gắn một biến có kiểu phù hợp; compiler chỉ cho sử dụng biến khi luồng điều khiển bảo đảm pattern đã khớp**. Hiểu quy tắc này giúp viết điều kiện gọn và an toàn trên Java 17, đồng thời tránh lỗi phạm vi biến khi kết hợp các toán tử logic.

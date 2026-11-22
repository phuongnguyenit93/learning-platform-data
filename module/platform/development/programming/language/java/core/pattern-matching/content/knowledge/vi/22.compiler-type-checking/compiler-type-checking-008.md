# Lỗi do selector type không phù hợp trong Java Pattern Matching

## 1. Selector type là gì và vì sao compiler báo lỗi?

Trong biểu thức hoặc câu lệnh `switch (selector)`, **selector** là biểu thức nằm trong dấu ngoặc tròn. **Selector type** là **kiểu tĩnh (compile-time type)** của biểu thức đó: kiểu mà compiler biết khi biên dịch, không phải kiểu runtime của một đối tượng được gán vào biến.

Ví dụ:

```java
Object value = "Java";
String result = switch (value) {
    case String s -> "text:" + s;
    case Integer n -> "number:" + n;
    case null -> "null";
    default -> "other";
};
```

Selector `value` có **kiểu tĩnh `Object`**, còn giá trị đang chứa lúc chạy là một `String`. Cả pattern `String s` lẫn `Integer n` đều có thể được thử đối với `Object`; trường hợp thực tế chọn nhánh `String`.

Ngược lại:

```java
String value = "Java";

// KHÔNG BIÊN DỊCH:
// String result = switch (value) {
//     case Integer n -> "number:" + n;
//     default -> "other";
// };
```

Compiler thấy selector chắc chắn là `String`, trong khi `Integer` là một kiểu không tương thích với `String`. Không có giá trị hợp lệ của biến `String` có thể là `Integer`, nên nhãn pattern này **không áp dụng được**. Trình biên dịch báo lỗi trước khi chương trình chạy; thêm `default` không chữa lỗi kiểu của nhãn `case`.

Trong Java Pattern Matching, có ít nhất ba tình huống cần phân biệt:

1. **Kiểu của chính selector không được hỗ trợ** bởi `switch` trong phiên bản Java đang dùng.
2. **Kiểu selector được hỗ trợ, nhưng nhãn `case` không tương thích** với kiểu tĩnh selector.
3. **Kiểu selector và nhãn `case` hợp lệ, nhưng còn lỗi khác** như nhánh bị bao phủ (dominated), không exhaustive, generic type không kiểm tra được hoặc kiểu kết quả của switch expression không phù hợp.

Bài này tập trung vào hai nhóm đầu và chỉ ra cách phân biệt với các lỗi liên quan.

## 2. Quy tắc selector type trong Java 21

Từ Java 21, nhờ *pattern matching for switch* (JEP 441), `switch` có thể dùng **mọi reference type** làm selector, ngoài các kiểu nguyên thủy vốn đã được phép.

Các kiểu selector hợp lệ trong **Java 21**:

| Kiểu selector | Hỗ trợ? | Ghi chú |
| --- | --- | --- |
| `byte`, `short`, `char`, `int` | Có | Có thể dùng nhãn hằng tương thích; chú ý giá trị và kiểu hằng. |
| `Byte`, `Short`, `Character`, `Integer` | Có | Các wrapper là reference type; cần xem null. |
| `String` | Có | Thường dùng `case "literal"` hoặc pattern áp dụng được. |
| `enum` | Có | Nhãn enum phải phù hợp enum được xét. |
| `Object`, `Number`, record, sealed interface, class, array, `List<?>`, v.v. | Có | Reference selector phù hợp cho type/record patterns. |
| `long`, `float`, `double`, `boolean` | **Không** trong Java 21 | Đây là giới hạn ngôn ngữ Java 21 đối với selector primitive. |

**Ranh giới phiên bản:** Một số JDK mới có tính năng *preview* về primitive patterns và `switch` trên thêm nhiều kiểu nguyên thủy. Khi dạy hoặc biên dịch theo Java 21, phải dựa vào quy tắc Java 21; đừng suy từ một preview ở JDK mới rằng `switch(long)`/`switch(boolean)` được hỗ trợ ở Java 21.

Ví dụ **không biên dịch trong Java 21**:

```java
long orderId = 5L;

// Sai với --release 21: long không phải kiểu selector hợp lệ.
// String label = switch (orderId) {
//     case 5L -> "five";
//     default -> "other";
// };

boolean enabled = true;

// Sai với --release 21: boolean không phải kiểu selector hợp lệ.
// String label = switch (enabled) {
//     case true -> "yes";
//     default -> "no";
// };
```

Cách sửa tùy mục tiêu:

- Với `boolean` chỉ có hai trạng thái, dùng `if/else` hoặc toán tử ba ngôi: `enabled ? "yes" : "no"`.
- Với `long`, dùng `if/else` hoặc cấu trúc phù hợp. Nếu chắc chắn toàn bộ giá trị nằm trong miền `int`, có thể kiểm tra giới hạn rồi chuyển sang `int`; **không ép kiểu tùy tiện**, vì cắt bớt bit sẽ làm sai giá trị lớn.
- Nếu API trả về `Long` thay vì `long`, `Long` là reference type và có thể làm selector trong Java 21 khi sử dụng các pattern hợp lệ, ví dụ `case Long n -> ...`. Tuy vậy `case 5L` không tương đương với type pattern `case Long n when n == 5L`: nhãn hằng chịu các quy tắc riêng.

## 3. Nhãn pattern phải áp dụng được với selector

Với `case T variable`, kiểu pattern `T` phải **applicable** ở kiểu tĩnh của selector. Nói đơn giản, trình biên dịch cần thấy một khả năng chuyển kiểu hợp lệ theo quy tắc pattern matching; không thể viết một pattern cho hai kiểu loại trừ nhau.

### Trường hợp A: `String` không thể khớp `Integer`

```java
String text = "hello";

// KHÔNG BIÊN DỊCH:
// String kind = switch (text) {
//     case Integer n -> "integer";
//     default -> "other";
// };
```

Thông báo điển hình: `String cannot be converted to Integer` hoặc `incompatible types`.

**Cách sửa đúng mục đích:** Nếu dữ liệu chỉ có thể là `String`, dùng nhánh hằng chuỗi/`String` thay cho `Integer`:

```java
String kind = switch (text) {
    case "hello" -> "greeting";
    default -> "another string";
};
```

Nếu bài toán thực sự cần xử lý nhiều kiểu runtime khác nhau, khai báo tham số nhận **`Object`** rồi phân loại bằng type pattern:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string:" + s;
        case Integer n -> "integer:" + n;
        case null -> "null";
        default -> "other";
    };
}
```

Chỉ mở rộng kiểu đầu vào lên `Object` khi API thật sự phải chấp nhận dữ liệu khác kiểu; không đổi chữ ký chỉ để che lỗi thiết kế dữ liệu.

### Trường hợp B: `Number` không thể khớp `String`

```java
Number number = Integer.valueOf(12);

// KHÔNG BIÊN DỊCH:
// String output = switch (number) {
//     case String s -> s;
//     default -> "not string";
// };
```

`String` không phải kiểu con của `Number`, và không có phép kiểm tra kiểu hợp lệ cho pattern này từ selector `Number`.

Cách sửa để phân loại **các kiểu số**:

```java
String output = switch (number) {
    case Integer i -> "int:" + i;
    case Double d -> "double:" + d;
    case null -> "null number";
    default -> "another number";
};
```

`Integer` và `Double` đều thuộc phân cấp `Number`. `default` vẫn cần thiết trong ví dụ vì `Number` còn có những kiểu con khác (ví dụ `Long`, `Float`, `BigDecimal`).

### Trường hợp C: component của generic record không tương thích

Có thể selector là record nhưng pattern lồng ở component lại sai kiểu:

```java
record Box<T>(T value) {}

Box<String> strings = new Box<>("abc");

// KHÔNG BIÊN DỊCH:
// String kind = switch (strings) {
//     case Box(Integer n) -> "integer";
//     default -> "other";
// };
```

Với `Box<String>`, compiler biết component `value` có kiểu `String`, nên `Integer n` không thể khớp. Đây là lỗi **component pattern**, dù thông báo vẫn nhắc đến incompatible types.

Sửa bằng kiểu component chính xác hoặc `var`:

```java
String kind = switch (strings) {
    case Box(String s) -> "text:" + s;
};
```

`Box(var s)` cũng suy luận được `s` thành `String` từ kiểu tĩnh `Box<String>`.

## 4. Nhãn hằng khác nhãn pattern: `case 1` với `Object`

Đây là một bẫy phổ biến sau khi `switch` hỗ trợ `Object` trong Java 21.

```java
Object value = 1;

// KHÔNG BIÊN DỊCH trong Java 21:
// String result = switch (value) {
//     case 1 -> "one";
//     default -> "other";
// };
```

Dù giá trị runtime là `Integer(1)`, **nhãn hằng** `case 1` không tương thích với selector có kiểu `Object` theo quy tắc switch label. Lỗi điển hình: `constant label of type int is not compatible with switch selector type Object`.

Cách sửa khi muốn phân loại `Object` theo giá trị số:

```java
String result = switch (value) {
    case Integer n when n == 1 -> "one";
    case Integer n -> "another int:" + n;
    case null -> "null";
    default -> "other";
};
```

Đây là **type pattern `Integer n`** kèm guard `when n == 1`, khác nhãn hằng `case 1`.

Nếu đầu vào vốn đã được bảo đảm là `int`, giữ selector kiểu `int` và dùng nhãn hằng:

```java
int valueAsInt = 1;

String result = switch (valueAsInt) {
    case 1 -> "one";
    default -> "other";
};
```

**Quy tắc thực hành:** Với selector `Object` hoặc interface/lớp rộng, dùng type/record patterns để nhận diện kiểu runtime. Đừng bê nguyên `case 1` hay `case "A"` từ một switch trên `int`/`String` sang switch trên `Object` mà không kiểm tra quy tắc tương thích của constant label.

## 5. Ví dụ chạy đầy đủ: chọn selector type và case phù hợp

Lưu mã thành **`SelectorTypeDemo.java`**. Chương trình Java 21+ dưới đây phân loại `Object`, `Number`, `String` và dùng sealed record patterns.

```java
public class SelectorTypeDemo {
    sealed interface Result permits Success, Failure {}

    record Success(String message) implements Result {}
    record Failure(int code) implements Result {}

    static String classify(Object selector) {
        return switch (selector) {
            case String text -> "text:" + text;

            case Integer n when n > 0 -> "positive-int:" + n;
            case Integer n -> "other-int:" + n;

            case Success(var message) -> "success:" + message;
            case Failure(int code) -> "failure:" + code;

            case null -> "null";
            default -> "other:"
                    + selector.getClass().getSimpleName();
        };
    }

    static String classifyNumber(Number selector) {
        return switch (selector) {
            case Integer n -> "int:" + n;
            case Double d -> "double:" + d;
            case null -> "null number";
            default -> "another number";
        };
    }

    static boolean nonBlankText(Object selector) {
        return selector instanceof String s && !s.isBlank();
    }

    static String classifyString(String selector) {
        return switch (selector) {
            case "A" -> "letter A";
            case "B" -> "letter B";
            case null -> "null string";
            default -> "other string";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("hello"));
        System.out.println(classify(7));
        System.out.println(classify(-2));
        System.out.println(classify(new Success("OK")));
        System.out.println(classify(new Failure(404)));
        System.out.println(classify(2.5));
        System.out.println(classify(null));

        System.out.println(classifyNumber(4));
        System.out.println(classifyNumber(2.5));
        System.out.println(classifyNumber(null));

        System.out.println(nonBlankText("Java"));
        System.out.println(nonBlankText(" "));
        System.out.println(classifyString("A"));
    }
}
```

Biên dịch bằng JDK 21 hoặc mới hơn, nhưng **dùng đúng quy tắc Java 21**:

```bash
javac --release 21 SelectorTypeDemo.java
java SelectorTypeDemo
```

Kết quả:

```text
text:hello
positive-int:7
other-int:-2
success:OK
failure:404
other:Double
null
int:4
double:2.5
null number
true
false
letter A
```

**Tại sao chương trình chạy?**

1. `classify(Object)` có selector tĩnh `Object`, nên các pattern `String`, `Integer`, `Success`, `Failure` đều có thể được kiểm tra.
2. `Integer n when n > 0` cần đứng trước `Integer n` tổng quát. Nếu đặt nhánh tổng quát lên trước, nhánh có guard có thể bị compiler báo **dominated**.
3. `Success(var message)` và `Failure(int code)` là record patterns; mỗi kiểu record là một biến thể hợp lệ của sealed interface `Result`, nhưng tham số `Object` vẫn cho phép các kiểu khác. Vì thế `default` còn cần cho `Object`.
4. `classifyNumber(Number)` chỉ có các pattern tương thích phân cấp `Number`. `String` sẽ sai, trong khi `Integer` và `Double` hợp lệ.
5. `classifyString(String)` dùng các nhãn hằng chuỗi hợp lệ cho selector `String`.
6. `case null` tách biệt selector null; nếu bỏ nhánh phù hợp, pattern switch không mặc nhiên đưa null vào `default`.

## 6. Generics và type erasure: nhầm kiểu selector với generic argument

Một selector `Object` có thể giữ một `List<String>` ở runtime, nhưng JVM thường không giữ tham số kiểu `String` để kiểm tra bằng `instanceof`/type pattern.

```java
Object source = java.util.List.of("a", "b");

// KHÔNG BIÊN DỊCH:
// String result = switch (source) {
//     case java.util.List<String> list -> "texts";
//     default -> "other";
// };
```

Lỗi dạng `Object cannot be safely cast to List<String>` liên quan **generic type không reifiable**, chứ không phải chỉ thiếu một nhánh `default`.

Sửa bằng wildcard reifiable:

```java
String result = switch (source) {
    case java.util.List<?> list ->
            "size=" + list.size();
    case null -> "null";
    default -> "other";
};
```

Nếu thật sự cần phần tử là `String`, duyệt và kiểm tra từng phần tử hoặc giữ thông tin generic ở chữ ký API từ đầu:

```java
static String joinUpper(java.util.List<String> values) {
    return values.stream()
            .map(String::toUpperCase)
            .collect(java.util.stream.Collectors.joining(","));
}
```

`List<?>` đảm bảo đối tượng là List, **không** chứng minh tất cả phần tử là String. Tương tự, đừng tự thay `Box<?>` bằng `Box<String>` nếu đầu vào chỉ có kiểu `Object`.

## 7. Các lỗi gần giống nhưng không phải selector type mismatch

### 7.1. Nhánh bị dominated

```java
Object input = "Java";

// KHÔNG BIÊN DỊCH:
// String answer = switch (input) {
//     case Object any -> "any";
//     case String s -> "text"; // dominated
// };
```

Ở đây `String` là kiểu pattern **hợp lệ** cho selector `Object`. Lỗi xuất hiện vì nhánh `Object` không guard đã bao phủ nhánh `String` sau nó. Cách sửa là đặt pattern cụ thể trước pattern rộng.

### 7.2. Switch expression chưa exhaustive

```java
Object input = 1;

// KHÔNG BIÊN DỊCH:
// String answer = switch (input) {
//     case String s -> "text";
// };
```

`String s` áp dụng được cho `Object`, nhưng không bao phủ giá trị `Integer`, record, null, v.v. Switch expression yêu cầu đủ nhánh; thêm `default` hoặc các pattern bao phủ phù hợp. Với sealed hierarchy, compiler có thể suy ra exhaustiveness từ các subtype được cho phép.

### 7.3. Kiểu giá trị trả về của switch expression không phù hợp

```java
// KHÔNG BIÊN DỊCH:
// String answer = switch (1) {
//     case 1 -> 100;
//     default -> 200;
// };
```

Selector `1` kiểu `int` là **hợp lệ**; lỗi nằm ở việc nhánh trả số nguyên trong khi biến nhận cần `String`. Sửa thành `"100"`/`"200"` hoặc đổi kiểu biến nhận thành `int`.

### 7.4. Scope biến pattern/guard sai

```java
Object input = 10;

// KHÔNG BIÊN DỊCH:
// if (input instanceof Integer n || n > 0) {
//     System.out.println(n);
// }
```

Vế phải `||` có thể chạy khi `instanceof` sai, nên `n` chưa được ràng buộc. Dùng `&&` nếu muốn xét điều kiện bổ sung sau khi pattern khớp:

```java
if (input instanceof Integer n && n > 0) {
    System.out.println(n);
}
```

Lỗi flow scoping này xảy ra ngoài `switch`, không phải do selector type.

### 7.5. Null: hợp lệ về kiểu nhưng lỗi lúc chạy

Một reference selector có thể có giá trị `null`. Pattern `case Integer n` không khớp selector null; nếu không có nhánh null phù hợp, chương trình có thể ném `NullPointerException` thay vì chọn `default`. Điều đó là lỗi runtime riêng, không phải lỗi tương thích kiểu lúc biên dịch.

## 8. Cách chẩn đoán và sửa nhanh

Khi thấy thông báo `incompatible types`, `cannot be converted to`, `constant label ... is not compatible` hoặc `selector type ... is not allowed`, kiểm tra theo thứ tự:

1. **Xác định phiên bản và flags biên dịch.** Với bài này dùng `javac --release 21`. Một tính năng preview của JDK mới không thuộc ngữ nghĩa Java 21.
2. **Ghi rõ kiểu tĩnh của biểu thức trong `switch (...)`.** Đừng nhìn mỗi đối tượng được tạo bằng `new` ở dòng trước. Nếu selector được khai báo `Object`, compiler không coi đó là `String` chỉ vì đang chứa chuỗi.
3. **Kiểm tra selector có được phép không.** `long`, `float`, `double`, `boolean` primitive không phải kiểu selector hợp lệ của Java 21.
4. **Xác định nhãn là constant hay pattern.** `case 1` có quy tắc khác `case Integer n when n == 1`. Đừng dựa vào autoboxing để coi mọi nhãn hằng là hợp lệ cho `Object`.
5. **Đối chiếu kiểu pattern với selector.** `String` không thể khớp `Integer`; `Number` không thể khớp `String`; nhưng `Object` có thể khớp cả hai. Với record pattern, xét tiếp từng component.
6. **Nếu có generic, xét type erasure.** `List<String>` không kiểm tra an toàn được từ `Object`; `List<?>` hợp lệ để kiểm tra kiểu thô của container.
7. **Nếu mọi kiểu đều phù hợp, kiểm tra thứ tự nhánh, exhaustiveness, null và kiểu kết quả.** Những lỗi này có thông báo gần giống nhưng nguyên nhân khác nhau.

**Không nên chữa bằng ép kiểu vô điều kiện.** Đổi `(Integer) input` có thể chuyển một lỗi biên dịch thành `ClassCastException` lúc chạy nếu input không thật sự là Integer. Ưu tiên giữ API đúng kiểu, dùng pattern khả dụng và xử lý giá trị không khớp rõ ràng.

## 9. Bài tập tự kiểm tra

**Bài 1.** Đoạn sau sai vì đâu?

```java
Object raw = 10;
// String out = switch (raw) {
//     case 10 -> "ten";
//     default -> "other";
// };
```

Đáp án: `case 10` là constant label kiểu `int`, không tương thích với selector `Object` theo quy tắc Java 21. Sửa thành `case Integer n when n == 10 -> "ten"`, và bổ sung các nhánh phù hợp.

**Bài 2.** Với `Number number = 2.5;`, có thể dùng `case Double d` không?

Có. `Double` là một kiểu con của `Number`, nên pattern áp dụng được. `case String s` trong switch trên `Number` thì không.

**Bài 3.** Với `Box<String> box`, muốn lấy chuỗi trong component thì dùng gì?

Dùng `Box(String s)` hoặc `Box(var s)`; compiler biết component là String. `Box(Integer n)` không hợp lệ trong ngữ cảnh đó.

**Bài 4.** Một switch expression trên `Object` có `case String s` và `default` nhưng thiếu `case null` thì sao?

Nhánh `String` không nhận null, và `default` thông thường không xử lý null selector trong pattern switch; khi selector null có thể ném `NullPointerException`. Thêm `case null` hoặc cấu trúc xử lý null tường minh nếu null là đầu vào hợp lệ.

## 10. Ghi nhớ

**Selector type quyết định loại nhãn `case` mà compiler cho phép.** Java 21 hỗ trợ `char`, `byte`, `short`, `int` và mọi reference type làm selector; primitive `long`, `float`, `double`, `boolean` chưa được hỗ trợ. Pattern phải có khả năng khớp giá trị thuộc kiểu tĩnh selector, còn constant label chịu các quy tắc tương thích hằng số riêng. Khi gặp lỗi, xác định đúng lớp sai: **kiểu selector, kiểu nhãn, component/generic, domination, exhaustiveness hay kiểu kết quả** rồi sửa ngay tại nguyên nhân.

### Tài liệu tham khảo

- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11, `14.30.3: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440

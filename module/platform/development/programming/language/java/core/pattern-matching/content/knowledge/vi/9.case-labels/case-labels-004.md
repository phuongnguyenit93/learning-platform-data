# Nhãn `case` hằng số và pattern trong Java

## 1. Vì sao có hai loại nhãn `case`?

Nhãn `case` chỉ định trường hợp mà một `switch` chọn để thực thi. Trong Java truyền thống, các nhãn phổ biến là **hằng số**, chẳng hạn `case 0`, `case "OK"` hoặc tên hằng của `enum`. Kể từ **Java 21**, *pattern matching for switch* trở thành tính năng chính thức (JEP 441), cho phép dùng **pattern** trong nhãn: `case String text`, `case Integer n`, `case Number n when n > 0`...

Hai hình thức có mục đích khác nhau:

- **Nhãn hằng số**: kiểm tra một giá trị **cụ thể** bằng quy tắc so sánh được Java định nghĩa cho loại `switch` tương ứng. Ví dụ `case 0` chỉ áp dụng cho giá trị số 0; `case "OK"` chỉ áp dụng cho chuỗi bằng `"OK"`.
- **Nhãn pattern**: kiểm tra giá trị có **khớp kiểu hoặc cấu trúc** hay không. Ví dụ `case Integer n` khớp mọi giá trị runtime thuộc `Integer`, rồi khởi tạo biến pattern `n` để phần nhánh sử dụng. Một pattern có thể có điều kiện bổ sung `when`.

Ví dụ kết hợp hằng số và pattern với selector kiểu `Integer`:

```java
static String describe(Integer value) {
    return switch (value) {
        case null -> "missing";
        case 0 -> "zero";
        case 1, 2 -> "one or two";
        case Integer n when n < 0 -> "negative: " + n;
        case Integer n -> "another integer: " + n;
    };
}
```

Với `0`, Java chọn nhãn hằng `case 0`. Với `-7`, Java kiểm tra `case Integer n when n < 0` và chọn rule này. Với `9`, Java chọn rule cuối. Ở hai rule pattern, biến `n` **chỉ dùng được trong guard và RHS của chính rule khai báo nó**.

Trong ví dụ, không có `default` vì `case Integer n` là pattern không điều kiện bao phủ mọi `Integer` khác `null`; `case null` xử lý riêng `null`. Java 21 cho phép viết switch expression như vậy.

## 2. Nhãn hằng số: giá trị cố định, không khai báo biến mới

Nhãn hằng số có dạng:

```java
case 10 -> ...
case "OPEN" -> ...
case MONDAY -> ...
case 1, 2, 3 -> ...
```

Đây là **mảnh cú pháp** phải đặt bên trong switch có kiểu selector tương thích. `case 1, 2, 3` gộp nhiều **hằng số** vào một nhãn và dùng chung phần thân; không giống các khai báo pattern.

### 2.1. Hằng số được chấp nhận như thế nào?

Trong Java 21, `case` có thể sử dụng:

- **Constant expression** thích hợp, như `3`, `2 + 3`, `'A'`, `"READY"`.
- **Constant variable** với kiểu và giá trị phù hợp (ví dụ `static final int LIMIT = 10;`, trong đó giá trị là một biểu thức hằng khi khai báo).
- **Hằng `enum`** trong switch của enum tương thích, như `case PENDING`, `case DONE`.

Không phải biến nào có `final` cũng là hằng số compile time:

```java
final int constant = 2 + 3;     // Constant variable: hợp lệ làm case.
final int runtime = Math.abs(-5); // Giá trị tính bằng lời gọi hàm.

// Trong switch của một int:
case 5 -> System.out.println("five");
// case constant -> ...         // Trùng giá trị với case 5: lỗi nếu đặt chung.
// case runtime -> ...          // LỖI: không phải constant expression.
```

Các dòng `case` ở trên chỉ minh họa trong một ngữ cảnh switch của `int`. Một switch không thể có **hai case hằng số cùng giá trị**, dù được viết bằng hai biểu thức khác nhau. `case 2 + 3` và `case 5` có giá trị giống nhau nên bị coi là trùng nhãn.

### 2.2. Điều kiện tương thích của selector

**Java 21 không cho phép đặt hằng số tùy ý vào mọi `switch(Object)`**. Với case hằng số là constant expression, JLS 21 yêu cầu selector có một trong các kiểu: `char`, `byte`, `short`, `int`, các wrapper tương ứng (`Character`, `Byte`, `Short`, `Integer`) hoặc `String`, đồng thời hằng số phải tương thích theo phép gán với kiểu selector. Hằng `enum` phải tương thích với enum selector tương ứng.

Ví dụ **không biên dịch** trong Java 21:

```java
static String wrong(Object x) {
    return switch (x) {
        // case "YES" -> "known";  // LỖI: hằng String không hợp lệ với selector Object.
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

Sửa bằng cách dùng `switch` với selector **`String`** khi cần `case "YES"`, hoặc dùng `case String s when s.equals("YES")` khi selector phải là **`Object`**:

```java
static String fromObject(Object x) {
    return switch (x) {
        case String s when s.equals("YES") -> "known";
        case String s -> "text: " + s;
        case null -> "null";
        default -> "other";
    };
}
```

Trường hợp selector `String` có thể dùng đồng thời các hằng chuỗi và type pattern `String s`, miễn thứ tự nhãn và quy tắc che nhãn hợp lệ.

### 2.3. So sánh chuỗi và số

Với `switch(String)` và `case "OK"`, Java dùng so sánh nội dung theo `String.equals`, **không** đòi hai tham chiếu trỏ cùng một chuỗi như phép `==` giữa hai đối tượng.

Với selector là `int`/các kiểu số nguyên nhỏ hoặc wrapper tương ứng, Java áp dụng quy tắc chọn nhãn hằng số số học của switch. Với wrapper như `Integer`, một giá trị khác `null` có thể được so sánh với hằng kiểu `int`; `null` phải được xử lý riêng nếu được phép hoặc switch sẽ ném `NullPointerException`.

Một nhãn hằng số **không tạo pattern variable**. Trong `case "OK" -> ...`, biến cục bộ tên `s` không tự xuất hiện; muốn có biến được kiểm tra kiểu, cần pattern như `case String s`.

## 3. Nhãn pattern: kiểm tra kiểu, tạo biến và có thể thêm `when`

Ví dụ trong Java 21:

```java
static String kind(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String length: " + text.length();
        case Integer number -> "Integer: " + number;
        case Number number -> "Other Number: " + number;
        default -> "Other";
    };
}
```

Những điều cần nhớ:

1. `case String text` khớp nếu selector tham chiếu tới một `String`; khi khớp, `text` có **kiểu tĩnh `String`**, dùng được `length()` mà không phải cast.
2. `case Integer number` khớp các `Integer`; `case Number number` khớp các subclass khác của `Number`, ví dụ `Double`.
3. Các pattern variables có thể **trùng tên giữa các rule độc lập**. Trong ví dụ, `number` của nhánh `Integer` và `number` của nhánh `Number` là hai biến khác nhau.
4. `case null` là nhãn **đặc biệt**, không phải type pattern và không khai báo biến.
5. `default` xử lý các kiểu còn lại, nhưng không mặc nhiên xử lý `null` nếu thiếu `case null`.

### 3.1. `when`: điều kiện phụ chỉ dùng với nhãn pattern

```java
static String size(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 5 -> "long: " + s;
        case String s -> "short: " + s;
        case null -> "null";
        default -> "not text";
    };
}
```

`String s` phải khớp trước, sau đó Java mới đánh giá điều kiện `when s.isBlank()` hoặc `when s.length() >= 5`. `s` có phạm vi **ngay trong guard của chính case** và trong RHS của rule đó. Nếu pattern không khớp hoặc guard trả `false`, Java tiếp tục thử nhãn còn lại.

**Không** viết `case "OK" when condition -> ...` trên Java 21: một nhãn chỉ gồm hằng số **không được gắn `when`**. Nếu muốn kết hợp hằng và điều kiện phụ, hãy:

- Đặt `case "OK" -> ...` để xử lý hằng trước;
- Hoặc chuyển sang `case String s when s.equals("OK") && ... -> ...` nếu điều kiện phụ thực sự cần thiết và selector phù hợp.

Một ngoại lệ quan trọng về thứ tự: `case String s` không guard bắt tất cả chuỗi còn lại; nếu đặt nó trước `case String s when ...`, nhãn có guard bị che và Java báo lỗi biên dịch.

### 3.2. Pattern trên record (Java 21+)

Ngoài type pattern, Java 21 còn có **record patterns**, dùng để kiểm tra và trích xuất thành phần:

```java
record Point(int x, int y) {}

static String pointKind(Object input) {
    return switch (input) {
        case Point(int x, int y) when x == y -> "diagonal";
        case Point(int x, int y) -> "point: " + x + "," + y;
        case null -> "null";
        default -> "other";
    };
}
```

Các biến `x`, `y` trong mỗi rule được khai báo bởi **record pattern**, không phải biến truyền từ nhánh trước. Guard `when x == y` có thể dùng chúng vì việc giải cấu trúc đã khớp trước khi guard được đánh giá.

**Khác nhãn hằng số:** `case new Point(1, 2) -> ...` không phải một nhãn constant expression hợp lệ; muốn phân loại record theo nội dung, dùng record pattern với `when`, hoặc pattern biến `Point p when ...`.

## 4. Kết hợp hằng số và pattern trong một switch: quy tắc thứ tự

Đây là nguyên tắc thực hành quan trọng nhất:

> **Đặt case hằng số chuyên biệt trước pattern tổng quát**, rồi các pattern có guard trước pattern cùng kiểu không guard.

Xét selector `Integer`:

```java
static String score(Integer value) {
    return switch (value) {
        case null -> "null";
        case 0 -> "zero";
        case 1, 2 -> "one-or-two";
        case Integer n when n < 0 -> "negative";
        case Integer n -> "other integer";
    };
}
```

Với `0`, Java chọn hằng số 0. Với `2`, Java chọn nhóm hằng số 1 hoặc 2. Với `-5`, rule có guard `n < 0` được chọn. Với `8`, rule tổng quát `case Integer n` xử lý.

### 4.1. Dominance: nhãn đến sau bị bao phủ hoàn toàn

Java kiểm tra **dominance** khi biên dịch để tránh các nhãn không thể được chọn do một nhãn trước đã bao phủ chúng.

Ví dụ **không hợp lệ**:

```java
// Trong switch(Integer value):
case Integer n -> System.out.println("any integer");
case 42 -> System.out.println("special 42"); // LỖI: bị case Integer n che.
```

Ở đây `case Integer n` là pattern không guard, khớp mọi giá trị `Integer` khác `null`; hằng `42` không còn cơ hội được chọn. Đổi thứ tự là hợp lệ:

```java
case 42 -> System.out.println("special 42");
case Integer n -> System.out.println("other integer " + n);
```

Một ví dụ che nhánh pattern:

```java
// Trong switch(Object value):
case Number n -> System.out.println(n);
case Integer i -> System.out.println(i); // LỖI: Integer là subtype của Number.
```

Phải đặt `Integer` trước `Number` nếu muốn xử lý chuyên biệt.

**Tinh tế:** Java không cố giải mọi biểu thức `when` bằng suy luận toán học. Ví dụ `case Integer n when n < 10` trước `case 5` có thể không bị từ chối vì dominance, nhưng khi `5` xuất hiện, rule có guard đã nhận nó trước; nhãn hằng 5 sẽ không được chạy. Do đó vẫn nên đưa **hằng số trước guard** để tránh hành vi bất ngờ, ngay cả khi mã có thể biên dịch.

### 4.2. Pattern “bao phủ hết” và `default`

Trong `switch(Integer value)`, pattern `case Integer n` là **unconditional pattern** cho mọi giá trị `Integer` khác `null`. Khi nó đã hiện diện, không đặt thêm `default` trong cùng switch block: có thể dẫn đến lỗi vì hai nhãn đều mang ý nghĩa bao phủ toàn bộ kiểu selector.

Cách hoàn chỉnh:

```java
return switch (value) {
    case null -> "missing";
    case 42 -> "answer";
    case Integer n -> "integer " + n;
};
```

Nếu selector là `Object`, có thể viết các type patterns chuyên biệt rồi `default` để bao phủ kiểu còn lại:

```java
return switch (value) {
    case null -> "missing";
    case String s -> "text: " + s;
    case Integer n -> "integer: " + n;
    default -> "other";
};
```

Ở ví dụ thứ hai, không thể thay `case String s` bằng `case "hello"` trực tiếp vì selector đang có kiểu tĩnh `Object`.

## 5. `case null`, `default` và nhóm nhãn

### 5.1. `null` không giống hằng số thường

Trong Java 21, selector là kiểu tham chiếu có thể dùng `case null`. Đây là trường hợp đặc biệt:

```java
static String label(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "text";
        default -> "other";
    };
}
```

`case String s` không khớp `null`; `default` thông thường cũng không tự bắt `null`. Nếu selector bằng `null` mà **không** có nhãn xử lý `null`, switch thường ném `NullPointerException`.

Java 21 còn cho phép cú pháp đặc biệt:

```java
static String labelOrOther(Object value) {
    return switch (value) {
        case String s -> "text";
        case null, default -> "not text (including null)";
    };
}
```

`case null, default` là trường hợp kết hợp **được phép rõ ràng**, khác với việc tùy ý gộp `null` và một pattern có biến.

**Không hợp lệ:**

```java
// case null, String s -> System.out.println(s); // LỖI trong Java 21.
// case 0, Integer n -> System.out.println(n);   // LỖI trong Java 21.
```

Đối với Java 21, một nhãn `case` thông thường chứa **danh sách hằng số**, **một `null` đặc biệt**, hoặc **một pattern** (có thể có `when`). Không thể trộn những loại này tùy ý trong cùng danh sách phân tách bằng dấu phẩy. Riêng `case null, default` là cú pháp đặc biệt.

### 5.2. Nhóm hằng số khác nhóm pattern

**Hợp lệ** nếu tất cả đều là constant expressions tương thích:

```java
switch (code) {                // code có kiểu int
    case 200, 201, 202 -> System.out.println("success");
    case 400, 404 -> System.out.println("client error");
    default -> System.out.println("other");
}
```

Ngược lại, `case String s, Integer n -> ...` **không phải cú pháp Java 21 ổn định**. Khi cần xử lý chung hai kiểu, dùng các rule riêng gọi cùng phương thức trợ giúp, hoặc một pattern tổng quát hơn phù hợp với selector.

Với cú pháp dấu hai chấm `case ...:`, Java có các nhóm lệnh và khả năng fall-through; nhưng nếu đi vào một nhóm có **pattern variable chưa được khởi tạo**, compiler sẽ từ chối. Dạng `case ... ->` tránh phần lớn sự nhầm lẫn này vì không tự fall through.

## 6. Switch statement, switch expression và tính bao phủ (*exhaustiveness*)

Cả hai hình thức `switch` đều có thể chứa hằng số lẫn pattern:

- **Switch statement**: thực thi lệnh, ví dụ `System.out.println(...)`; không tự tạo kết quả cho biểu thức bao quanh.
- **Switch expression**: tạo một giá trị; mỗi rule có RHS là một biểu thức giá trị, một block dùng `yield`, hoặc một lệnh `throw`.

Ví dụ switch statement:

```java
static void announce(Integer value) {
    switch (value) {
        case null -> System.out.println("null");
        case 42 -> System.out.println("answer");
        case Integer n -> System.out.println("other: " + n);
    }
}
```

Ví dụ switch expression:

```java
static String category(Integer value) {
    return switch (value) {
        case null -> "null";
        case 42 -> "answer";
        case Integer n -> "other: " + n;
    };
}
```

Lưu ý: `case 42` xuất hiện **trước** `case Integer n`. Trong cả hai ví dụ, các giá trị `Integer` không `null` đều khớp một trong hai rule; `null` được xử lý riêng.

Trong Java 21, **switch expression luôn phải exhaustive**. Một **enhanced switch statement** (ví dụ switch statement dùng case pattern hoặc `case null`, hay selector có kiểu không thuộc nhóm truyền thống) cũng phải exhaustive. Với selector là `Integer`, nếu chỉ liệt kê `case 0` và `case 1` mà vẫn dùng pattern hoặc `case null`, thường cần thêm `default` hoặc một pattern tổng quát bao phủ phần còn lại.

Một **switch statement truyền thống** chỉ dùng các case hằng số trên kiểu selector cổ điển có thể không cần `default` vì tương thích ngược. Đừng nhầm tính chất này với enhanced switch statement.

Với enum, các hằng có thể tự bao phủ đủ tập giá trị không `null`:

```java
enum Stage { TODO, DOING, DONE }

static String stageName(Stage stage) {
    return switch (stage) {
        case null -> "missing";
        case TODO -> "To do";
        case DOING -> "In progress";
        case DONE -> "Done";
    };
}
```

Đây là switch expression exhaustive vì đã xử lý cả ba enum constants, và có nhãn riêng cho `null`. Không cần `default`. Khi enum được mở rộng thêm giá trị, mã switch có thể cần cập nhật tương ứng để bảo toàn tính bao phủ.

## 7. Chương trình Java 21 chạy đầy đủ: hằng số và pattern cùng tồn tại

Lưu đúng tên file **`CaseConstantPatternDemo.java`**:

```java
public class CaseConstantPatternDemo {
    enum Stage { TODO, DOING, DONE }

    static String classifyNumber(Integer value) {
        return switch (value) {
            case null -> "null number";
            case 0 -> "zero";
            case 1, 2 -> "one/two: " + value;
            case Integer n when n < 0 -> "negative: " + n;
            case Integer n when n % 2 == 0 -> "even: " + n;
            case Integer n -> "odd: " + n;
        };
    }

    static String classifyText(String value) {
        return switch (value) {
            case null -> "null text";
            case "" -> "empty text";
            case "OK", "YES" -> "approved: " + value;
            case String s when s.isBlank() -> "blank text";
            case String s when s.length() >= 5 -> "long text: " + s;
            case String s -> "short text: " + s;
        };
    }

    static String classifyObject(Object value) {
        return switch (value) {
            case null -> "null object";
            case String s -> "String length: " + s.length();
            case Number n when n.doubleValue() < 0 -> "negative Number";
            case Number n -> "Number: " + n;
            default -> "other";
        };
    }

    static String stageName(Stage stage) {
        return switch (stage) {
            case null -> "missing";
            case TODO -> "To do";
            case DOING -> "In progress";
            case DONE -> "Done";
        };
    }

    static void announce(Integer value) {
        switch (value) {
            case null -> System.out.println("ANNOUNCE null");
            case 42 -> System.out.println("ANNOUNCE answer");
            case Integer n when n > 100 ->
                    System.out.println("ANNOUNCE large " + n);
            case Integer n -> System.out.println("ANNOUNCE other " + n);
        }
    }

    public static void main(String[] args) {
        System.out.println(classifyNumber(null));
        System.out.println(classifyNumber(0));
        System.out.println(classifyNumber(2));
        System.out.println(classifyNumber(-3));
        System.out.println(classifyNumber(8));
        System.out.println(classifyNumber(7));

        System.out.println(classifyText(null));
        System.out.println(classifyText(""));
        System.out.println(classifyText("OK"));
        System.out.println(classifyText("  "));
        System.out.println(classifyText("hello"));
        System.out.println(classifyText("Hi"));

        System.out.println(classifyObject("X"));
        System.out.println(classifyObject(-2.5));
        System.out.println(classifyObject(3.5));
        System.out.println(classifyObject(true));

        System.out.println(stageName(Stage.DOING));

        announce(42);
        announce(150);
        announce(9);
        announce(null);
    }
}
```

**Biên dịch và chạy với JDK 21 trở lên** (pattern matching cho switch đã là tính năng chính thức, không cần preview):

```bash
javac CaseConstantPatternDemo.java
java CaseConstantPatternDemo
```

**Đầu ra chính xác:**

```text
null number
zero
one/two: 2
negative: -3
even: 8
odd: 7
null text
empty text
approved: OK
blank text
long text: hello
short text: Hi
String length: 1
negative Number
Number: 3.5
other
In progress
ANNOUNCE answer
ANNOUNCE large 150
ANNOUNCE other 9
ANNOUNCE null
```

**Diễn giải:**

1. `classifyNumber` nhận `Integer`: các hằng số `0`, `1`, `2` được kiểm tra trước; sau đó pattern `Integer n` có guard xét số âm, số chẵn và cuối cùng là số lẻ. Vì `n` luôn thuộc `Integer` khi pattern khớp, phép tính `n % 2` và so sánh `n < 0` hợp lệ trong guard.
2. `classifyText` nhận `String`: hằng `""` và nhóm hằng `"OK", "YES"` được xử lý trước. Các chuỗi khác được xét tiếp theo các type pattern có guard. `"  "` trắng nên nhánh `isBlank()` được chọn; `"hello"` có độ dài 5, khớp guard `length() >= 5`.
3. `classifyObject` nhận `Object`: ở đây chỉ có type patterns, `case null` và `default`; **không đặt hằng chuỗi/số** trực tiếp trong switch của `Object`. `-2.5` và `3.5` được boxing thành `Double` khi truyền vào, và đều là `Number`. Guard chọn trường hợp âm.
4. `stageName` dùng hằng enum đúng kiểu, bao phủ toàn bộ ba hằng đã khai báo cùng với trường hợp `null`.
5. `announce` là **switch statement**, không phải switch expression: mỗi nhánh thực hiện `println`. `case 42` đứng trước pattern `Integer n` nên không bị nhánh tổng quát che.

Chương trình dùng một file, một lớp public và một enum lồng để thuận tiện biên dịch lại nguyên ví dụ.

## 8. Bảng so sánh các nhãn `case`

| Loại nhãn | Ví dụ | Kiểm tra | Có biến pattern mới? |
| --- | --- | --- | --- |
| Hằng số nguyên | `case 42` | Giá trị số tương ứng bằng 42 | Không |
| Hằng `String` | `case "OK"` | Chuỗi có nội dung bằng `"OK"` | Không |
| Nhóm hằng | `case 1, 2` | Một trong các giá trị đã liệt kê | Không |
| Hằng enum | `case DONE` | Đúng hằng enum `DONE` | Không |
| Type pattern | `case String s` | Giá trị có kiểu runtime phù hợp `String` | Có: `s` |
| Type pattern có guard | `case Integer n when n < 0` | Khớp `Integer` **và** `n < 0` | Có: `n` |
| Record pattern | `case Point(int x, int y)` | Khớp record và giải cấu trúc thành phần | Có: `x`, `y` |
| `null` | `case null` | Selector bằng `null` | Không |
| Nhãn dự phòng | `default` | Các giá trị không `null` chưa được xử lý | Không |
| Nhãn đặc biệt | `case null, default` | Xử lý cả `null` và các giá trị còn lại | Không |

**Ghi chú phiên bản:** Các type/record patterns trong switch, `when` và xử lý `null` theo cú pháp ở bài là các tính năng chính thức của **Java 21**. Dạng switch chỉ dùng hằng số đã xuất hiện từ những phiên bản Java trước.

## 9. Lỗi biên dịch và hiểu nhầm thường gặp

### 9.1. Cho rằng `case "A"` hợp lệ với selector kiểu `Object`

Trong Java 21, không được đặt case hằng `String` trong một switch có selector tĩnh là `Object`. Hãy đổi selector sang `String` nếu nghiệp vụ cho phép, hoặc dùng `case String s when s.equals("A")` cho `Object`.

### 9.2. Đặt pattern tổng quát trước hằng số

`case Integer n` trước `case 42` là lỗi dominance. Đặt hằng `42` trước pattern. Tương tự, `case Number n` trước `case Integer i` che nhánh Integer.

### 9.3. Dùng `when` với case hằng số

`case 10 when flag` không phải cú pháp Java 21. `when` đi kèm **case pattern**. Muốn điều kiện phụ, dùng guarded pattern hoặc kiểm tra `if` ở trong block của nhánh hằng số.

### 9.4. Trộn pattern và hằng trong cùng nhãn

`case 1, Integer n` và `case null, String s` đều không hợp lệ trong Java 21. Dùng các rule riêng; không nhầm với `case null, default`.

### 9.5. Hai hằng cho cùng một giá trị

`case 5` và `case 2 + 3` trong cùng switch gây lỗi vì cả hai có giá trị 5. Tên constant variable hoặc cách viết biểu thức khác không tạo nhãn mới nếu giá trị trùng.

### 9.6. Cho rằng `default` tự bắt `null`

Không có `case null`, selector `null` có thể ném `NullPointerException` ngay cả khi có `default`. Nếu muốn gộp nhánh dự phòng bao gồm `null`, dùng `case null, default` khi phù hợp.

### 9.7. Đem biến pattern ra khỏi rule khai báo

Biến của `case String s` chỉ dùng được trong guard và RHS của rule tương ứng, không dùng trong nhánh hằng, `default` hoặc sau switch. Nếu cần giá trị tổng hợp, hãy lấy kết quả switch expression hoặc gán một biến đã khai báo ngoài switch statement.

### 9.8. Nhầm yêu cầu exhaustiveness

Một enhanced switch statement có pattern/`case null` phải exhaustive. Với selector `Object`, các pattern `String` và `Integer` thường cần `default` để xử lý những kiểu khác. Với selector `Integer`, `case Integer n` có thể bao phủ các giá trị không null còn lại; `case null` xử lý null.

### 9.9. Quên quy tắc không fall-through của `->`

Một rule `case 1 -> ...` không tự chạy sang `case Integer n -> ...`. Với cú pháp `case ...:`, có thể fall through, nhưng không được nhảy vào đoạn dùng pattern variable chưa khởi tạo; dùng `break` hoặc chuyển sang `->`.

### 9.10. Dùng Java 17 như thể đã hỗ trợ pattern matching switch ổn định

Pattern matching cho `instanceof` đã chính thức trong Java 16, nhưng **pattern matching cho switch** là tính năng chính thức từ Java 21. Hãy biên dịch các ví dụ kết hợp nhãn hằng số và pattern ở đây bằng JDK 21+.

## 10. Bài tập vận dụng

1. **Hằng trước pattern:** Viết `switch(Integer status)` với `case null`, `case 200`, `case 404`, `case Integer n when n >= 500`, và `case Integer n` cuối cùng. Trả về nhãn `"missing"`, `"OK"`, `"not found"`, `"server error"` hoặc `"other"`; giải thích thứ tự từng rule.
2. **Hằng `String` so với Object:** Viết `switch(String command)` có `case "START", "GO"`, `case "STOP"`, một guarded `case String s when s.isBlank()` và `case String s`. Sau đó thử thay selector thành `Object` và quan sát lỗi hằng số; sửa bằng guarded type pattern.
3. **Dominance:** Trong `switch(Integer code)`, đặt `case Integer n` trước `case 42`. Giải thích lỗi biên dịch; đảo thứ tự để sửa. Thử `case Integer n when n < 100` trước `case 42`, xem nhánh nào được chọn với giá trị 42 và tại sao.
4. **Trùng hằng:** Tạo `static final int TARGET = 5;` rồi đặt `case TARGET` và `case 2 + 3` trong cùng switch. Đoán thông báo compiler và sửa để không trùng nhãn.
5. **Null:** Viết `switch(Object x)` có `case String s` và `case null, default` để xử lý mọi đầu vào. So sánh với `default` đơn lẻ khi selector bằng `null`.
6. **Record pattern:** Tạo `record Pair(int a, int b)`; viết hai nhánh pattern: `case Pair(int a, int b) when a == b` và `case Pair(int a, int b)`. Dùng `when` để phân biệt cặp hai số bằng nhau.
7. **Enum:** Tạo enum `Mode { AUTO, MANUAL, OFF }`, viết switch expression với ba case hằng và `case null`. Không dùng `default`; giải thích vì sao biểu thức đã exhaustive.
8. **Phạm vi biến:** Đặt `case String s -> ...` và `case Integer n -> ...` trong một switch. Thử tham chiếu `s` ở nhánh `Integer`, sau đó sửa bằng cách chuyển xử lý chung ra một phương thức nhận tham số.
9. **Statement vs expression:** Chuyển một switch expression trả về `String` thành switch statement chỉ in kết quả. Kiểm tra sự khác nhau giữa RHS là biểu thức giá trị và RHS là lời gọi `println`.

**Tóm tắt:** Hằng số trong `case` phân loại **giá trị cụ thể**; pattern phân loại **kiểu/cấu trúc** và tạo biến cục bộ theo luồng khớp. Khi kết hợp trong Java 21, hãy bảo đảm kiểu selector phù hợp với hằng số, đặt **hằng chuyên biệt trước pattern có guard và pattern tổng quát**, xử lý `null` rõ ràng, và kiểm tra dominance cùng exhaustiveness.

## Tài liệu tham khảo

- [Java Language Specification 21, §14.11 — Switch Statements, Case Labels và Switch Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21, §6.3.3 — Scope of Pattern Variables in Case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).

# Phạm vi pattern variable trong guard, nhánh và khối lệnh

Trong pattern switch của Java 21, một pattern variable chỉ được sử dụng tại những vị trí mà trình biên dịch bảo đảm pattern đã khớp. Phạm vi đó bao gồm guard `when` và phần thân của nhánh `case` tương ứng. Pattern variable không tự động trở thành biến dùng được sau khi kết thúc nhánh hoặc sau toàn bộ câu lệnh `switch`.

Quy tắc này áp dụng cho cả `switch` expression và `switch` statement. Java 21 đã chuẩn hóa pattern matching for `switch` qua [JEP 441](https://openjdk.org/jeps/441), vì vậy cú pháp `case ... when ...` và các quy tắc phạm vi dưới đây có thể dùng trong mã nguồn Java 21 mà không cần bật preview.

## 1. Pattern variable được khai báo trong nhãn `case`

Một nhãn `case` có thể khai báo pattern variable bằng type pattern hoặc record pattern. Khi giá trị selector khớp pattern, biến được khởi tạo và có thể dùng trong guard (nếu có) cũng như phần thân của nhánh đó.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String: " + text.toUpperCase();
        case Integer number -> "Integer: " + number;
        default -> "Other type";
    };
}
```

Trong nhánh `case String text`, biến `text` có kiểu `String` và dùng được ở biểu thức bên phải `->`. Tương tự, `number` chỉ có hiệu lực trong nhánh `Integer` tương ứng. Không thể tham chiếu `text` hoặc `number` sau dấu `};` kết thúc switch expression.

Với switch rule có block, pattern variable dùng được trong toàn bộ block và các block con:

```java
static void printValue(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String text -> {
            int length = text.length();
            System.out.println(text.toUpperCase());
            System.out.println("Length: " + length);
        }
        case Integer number -> {
            System.out.println(number.intValue());
        }
        default -> System.out.println("Unsupported value");
    }
}
```

Biến `text` được bảo đảm đã khớp khi block của rule bắt đầu chạy. Biến cục bộ `length` được khai báo trong block nên chỉ có phạm vi trong block đó; `text` vẫn là pattern variable của nhãn `case` và có thể được dùng ở các block con bên trong.

## 2. Phạm vi của pattern variable trong guard `when`

Guard là biểu thức boolean đặt sau pattern trong nhãn `case`. Java chỉ đánh giá guard sau khi giá trị selector đã khớp pattern. Vì vậy, pattern variable do pattern khai báo đã được khởi tạo và có thể dùng trực tiếp trong guard.

```java
static String classify(String value) {
    return switch (value) {
        case String text when !text.isBlank() && text.length() >= 5 ->
            "Long text: " + text;
        case String text -> "Other string";
        case null -> "No value";
    };
}
```

Trong guard `!text.isBlank() && text.length() >= 5`, `text` được lấy từ pattern `String text`. Guard chỉ được đánh giá nếu selector là một `String`. Nếu guard trả về `false`, phần thân của nhánh đầu không chạy và Java tiếp tục xét nhãn `case` tiếp theo. Pattern variable `text` của nhãn đầu không được mang sang nhãn thứ hai; nhãn thứ hai khai báo một pattern variable riêng cũng tên `text`.

Guard phải có kiểu `boolean` hoặc `Boolean`. Mọi biến cục bộ, tham số hoặc exception parameter được guard sử dụng nhưng không được khai báo ngay trong guard phải là `final` hoặc effectively final. Vì vậy, nếu pattern variable của nhãn `case` được dùng trong guard, không gán lại biến đó trong guard.

### Pattern variable được khai báo ngay trong guard

Một guard cũng có thể chứa pattern khác. Nếu pattern variable được khai báo trong guard và guard cho kết quả `true`, biến đó được giới thiệu cho phần thân của nhánh `case`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case Object candidate when candidate instanceof String text
                && !text.isBlank() -> "Text: " + text.toUpperCase();
        default -> "Not a non-blank string";
    };
}
```

`candidate` được khai báo bởi pattern của nhãn `case` và có hiệu lực trong guard. Biến `text` được khai báo bởi `instanceof String text` bên trong guard. Nhờ toán tử `&&`, `text` được bảo đảm đã khớp khi đánh giá `!text.isBlank()`. Nếu toàn bộ guard là `true`, `text` cũng được bảo đảm đã khớp trong phần thân nhánh, nên biểu thức `"Text: " + text.toUpperCase()` hợp lệ.

Một biến được khai báo trong guard chỉ có hiệu lực theo luồng điều khiển mà pattern của nó đã khớp. Ví dụ, với biểu thức `candidate instanceof String text && text.length() > 0`, biến `text` có hiệu lực ở vế phải của `&&` và trong phần thân nhánh nếu guard thành công. Không thể dùng `text` ở một nhánh khác khi guard không thành công.

## 3. Phạm vi trong switch rule dùng `->`

Java 21 cho phép switch block dùng switch rules với `->`. Với dạng này, pattern variable được bảo đảm đã khớp trong đúng phần thân được gắn với nhãn: biểu thức, block hoặc câu lệnh `throw`.

```java
static int sizeOf(Object value) {
    return switch (value) {
        case String text -> text.length();
        case java.util.List<?> items -> items.size();
        case null -> 0;
        default -> -1;
    };
}
```

Ở đây, `text` chỉ dùng trong biểu thức của rule `String`; `items` chỉ dùng trong biểu thức của rule `List<?>`. Hai rule độc lập nên có thể khai báo cùng một tên biến nếu kiểu của pattern khác nhau:

```java
static void print(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case String item -> System.out.println(item.toUpperCase());
        case Integer item -> System.out.println(item + 1);
        default -> System.out.println("Other");
    }
}
```

Hai biến `item` thuộc hai nhãn `case` khác nhau và không có một điểm nào mà cả hai cùng có hiệu lực. Vì thế, dùng lại tên biến ở các switch rule riêng biệt là hợp lệ và thường giúp mã nguồn dễ đọc.

Không thể dùng pattern variable sau switch để thay thế cho kết quả của nhánh. Nếu cần giữ lại một giá trị, hãy trả về từ switch expression hoặc gán kết quả vào một biến bên ngoài:

```java
static String normalized(Object value) {
    String result = switch (value) {
        case String text -> text.trim().toLowerCase();
        case null -> "";
        default -> value.toString();
    };

    // result có phạm vi bên ngoài switch; text thì không.
    return result;
}
```

## 4. Phạm vi trong switch labeled statement group dùng `:`

Switch block cũng có thể dùng nhãn `case` với dấu `:`. Khi đó, các câu lệnh từ nhãn hiện tại đến trước nhãn tiếp theo tạo thành một switch labeled statement group. Pattern variable được khai báo bởi nhãn có hiệu lực trong tất cả câu lệnh thuộc group tương ứng.

```java
static void print(Object value) {
    switch (value) {
        case String text:
            System.out.println(text.toUpperCase());
            System.out.println(text.length());
            break;
        case Integer number:
            System.out.println(number + 1);
            break;
        default:
            System.out.println("Other");
    }
}
```

Trong group đầu tiên, `text` có hiệu lực ở cả hai câu lệnh `println`. `break` kết thúc group để luồng điều khiển không rơi tiếp vào nhãn `case Integer number`.

Khi một switch block dùng `:` và nhãn `case` khai báo pattern variable, Java có hai ràng buộc quan trọng để bảo đảm biến luôn được khởi tạo đúng:

- Câu lệnh ngay trước nhãn `case` pattern trong switch block không được có khả năng hoàn tất bình thường. Nếu không, luồng điều khiển có thể rơi vào group mà không khớp pattern và không khởi tạo biến.
- Một statement group khai báo pattern variable không được có nhiều nhãn switch cùng áp dụng cho group đó. Nếu nhiều nhãn dẫn đến cùng một group, không thể bảo đảm pattern variable của nhãn nào đã được khởi tạo.

Ví dụ sau không hợp lệ vì group `case String text` có thể hoàn tất bình thường và rơi vào group kế tiếp:

```java
static void invalidFallThrough(Object value) {
    switch (value) {
        case String text:
            System.out.println(text);
            // Thiếu break, throw hoặc cách kết thúc abrupt khác.
        case Integer number: // Compile-time error
            System.out.println(number + 1);
            break;
        default:
            break;
    }
}
```

Ví dụ sau cũng không hợp lệ vì hai nhãn dẫn đến cùng một statement group, trong khi mỗi nhãn khai báo một pattern variable khác nhau:

```java
static void invalidSharedGroup(Object value) {
    switch (value) {
        case String text:
        case Integer number: // Compile-time error
            System.out.println(number);
            break;
        default:
            break;
    }
}
```

Nếu cần nhiều nhánh pattern có phần xử lý chung, dùng switch rule `->` rồi gọi một phương thức chung, hoặc viết các nhánh riêng và kết thúc mỗi group bằng `break`, `return` hay `throw` phù hợp. Không dựa vào fall-through để chia sẻ một pattern variable.

## 5. Flow scoping bên trong phần thân của nhánh

Pattern variable từ nhãn `case` có hiệu lực trong phần thân nhánh, nhưng các pattern lồng trong điều kiện `if`, `while` hoặc biểu thức boolean vẫn tuân theo quy tắc flow scoping riêng. Một biến được khai báo bởi `instanceof` chỉ dùng được tại những vị trí mà trình biên dịch biết phép kiểm tra đã thành công.

```java
record User(String name, boolean active) {}

static void handle(Object value) {
    switch (value) {
        case null -> System.out.println("null");
        case User user -> {
            Object detail = user;

            if (detail instanceof User current && current.active()) {
                System.out.println("Active user: " + current.name());
            }

            // current không còn trong phạm vi tại đây.
            System.out.println("Handled: " + user.name());
        }
        default -> System.out.println("Not a user");
    }
}
```

`user` được khai báo ở nhãn `case`, vì vậy có hiệu lực trong block của rule. `current` được khai báo trong biểu thức `instanceof`; nó có hiệu lực ở vế phải của `&&` và trong nhánh `if`, nhưng không có hiệu lực ở câu lệnh sau `if`.

Có thể dùng quy tắc flow scoping để thoát sớm và tiếp tục sử dụng pattern variable sau `if`:

```java
static void printName(Object detail) {
    if (!(detail instanceof User user)) {
        return;
    }

    // Chỉ có thể tới đây nếu pattern đã khớp.
    System.out.println(user.name());
}
```

Đây là quy tắc flow scoping của pattern variable nói chung, không phải phạm vi đặc biệt chỉ dành cho switch. Nó hữu ích khi xử lý dữ liệu bên trong một switch rule và muốn tránh lồng nhiều cấp `if`.

## 6. Trùng tên, shadowing và giới hạn phạm vi

Có thể tái sử dụng tên pattern variable ở các nhãn `case` độc lập, nhưng không được khai báo một biến mới trùng tên với biến cục bộ hoặc tham số đang nằm trong phạm vi của nó.

```java
static void invalidShadowing(Object value) {
    String text = "outer";

    switch (value) {
        case String text -> System.out.println(text); // Compile-time error
        default -> System.out.println(text);
    }
}
```

Biến cục bộ `text` đã nằm trong phạm vi của switch block. Pattern variable `text` không thể khai báo để shadow biến cục bộ đó. Hãy chọn tên khác, ví dụ `case String matchedText -> ...`.

Một pattern variable cũng không thể được khai báo lặp lại cùng tên trong cùng cấu trúc pattern. Với record pattern, mỗi component pattern cần tên riêng nếu khai báo biến:

```java
record Pair(String first, String second) {}

static void inspect(Object value) {
    switch (value) {
        case Pair(String first, String second) ->
            System.out.println(first + " / " + second);
        default -> System.out.println("Not a pair");
    }
}
```

Nếu cần so sánh hai component có bằng nhau hay không, hãy thực hiện phép so sánh trong guard hoặc phần thân nhánh. Pattern variable là tên cho giá trị component; tên biến không phải điều kiện ràng buộc hai component bằng nhau.

## 7. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng biến của một `case` trong nhánh khác | Mỗi nhãn có phạm vi pattern variable riêng. | Đưa xử lý cần dùng chung vào phương thức hoặc tính kết quả trong từng nhánh. |
| Dùng pattern variable sau switch | Biến chỉ có hiệu lực trong guard và phần thân của nhánh tương ứng. | Trả kết quả từ switch expression hoặc gán vào biến bên ngoài. |
| Guard không truy cập được biến của pattern | Pattern chưa được khai báo trong nhãn hoặc tên biến bị viết sai. | Khai báo biến ngay trong pattern của `case`, ví dụ `case String text when text.length() > 3`. |
| Dùng biến khai báo trong guard ở nhánh khác | Biến của guard chỉ được giới thiệu khi guard thành công và chỉ thuộc nhánh đó. | Khai báo pattern phù hợp trong nhãn khác hoặc kiểm tra lại giá trị ở nhánh đó. |
| Compiler báo lỗi khi dùng `:` với pattern variable | Có thể có fall-through từ group trước hoặc nhiều nhãn cùng dẫn tới group khai báo biến. | Kết thúc group trước bằng `break`, `return` hoặc `throw`; tách các nhãn có biến thành các group riêng. |
| Selector là `null` dù switch có `default` | Nhãn `default` không khớp với `null`. | Thêm `case null` nếu cần xử lý giá trị null; nếu không, selector null sẽ làm switch ném `NullPointerException`. |
| Pattern variable trùng tên tham số hoặc local variable | Quy tắc shadowing không cho phép khai báo biến mới trong phạm vi tên đã được dùng. | Đổi tên pattern variable để tránh xung đột. |
| Dùng biến `instanceof` sau `if` | Luồng điều khiển không bảo đảm pattern đã khớp tại vị trí đó. | Dùng biến bên trong nhánh `if`, hoặc đảo điều kiện và `return`/`throw` khi pattern không khớp. |

## 8. Cách kiểm tra phạm vi trước khi viết switch

Khi một nhánh switch có nhiều pattern và guard, hãy kiểm tra theo thứ tự sau:

1. Xác định pattern nào khai báo biến và ghi rõ tên cùng kiểu của từng biến.
2. Với guard `when`, xác định biến nào đến từ pattern của nhãn và biến nào được khai báo bên trong guard.
3. Chỉ dùng biến trong phần guard hoặc phần thân mà Java bảo đảm pattern đã khớp.
4. Với switch rule `->`, coi biểu thức, block hoặc câu lệnh `throw` sau mũi tên là phần thân của nhãn đó.
5. Với switch labeled statement group `:`, bảo đảm không có fall-through vào nhãn pattern và không gộp nhiều nhãn vào một group có khai báo pattern variable.
6. Kiểm tra trùng tên với biến cục bộ, tham số và các pattern khác trong cùng phạm vi.
7. Nếu cần giữ dữ liệu sau switch, trả kết quả từ switch expression hoặc dùng biến cục bộ bên ngoài có kiểu phù hợp.

## 9. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 21 — §6.3.1.6 `switch` Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.1.6): phạm vi pattern variable trong switch expression.
- [Java Language Specification, Java SE 21 — §6.3.2.6 `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.2.6): phạm vi trong switch rules và switch labeled statement groups.
- [Java Language Specification, Java SE 21 — §6.3.3 Scope for Pattern Variables in `case` Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3): biến được khai báo trong pattern hoặc guard và phạm vi liên quan.
- [Java Language Specification, Java SE 21 — §6.4 Shadowing](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.4): giới hạn khai báo trùng tên và shadowing.
- [Java Language Specification, Java SE 21 — §14.11.1 Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): switch rules, labeled statement groups, guard, fall-through và các lỗi biên dịch liên quan.
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ guard `when`, pattern label và cách tổ chức nhánh switch.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): đặc tả tính năng pattern matching for switch được hoàn thiện trong Java 21.

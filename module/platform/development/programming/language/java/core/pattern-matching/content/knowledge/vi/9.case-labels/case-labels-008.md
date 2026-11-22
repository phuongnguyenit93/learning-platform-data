# Khai báo biến ở case label trong Java Pattern Matching for switch

## 1. Khi nào một `case` có thể khai báo biến?

Từ **Java 21**, tính năng *Pattern Matching for switch* (JEP 441) chính thức cho phép viết **case pattern**: nhánh `case` vừa kiểm tra kiểu của đối tượng, vừa khai báo biến để sử dụng ngay trong nhánh đã khớp. Ví dụ:

```java
static String describe(Object value) {
    return switch (value) {
        case String text  -> "Chuỗi dài " + text.length();
        case Integer n    -> "Số " + n;
        case null         -> "Không có dữ liệu";
        default           -> "Kiểu khác";
    };
}
```

Trong `case String text`:

- `String` là kiểu cần kiểm tra ở thời điểm chạy.
- `text` là **pattern variable** được **khai báo ngay trong case label**. Nếu giá trị selector thực sự là `String`, biến `text` tham chiếu đến đối tượng đã khớp, với **kiểu tĩnh `String`**.
- Phần bên phải `->` của nhánh được chọn có thể dùng `text.length()` mà không cần ép kiểu `(String) value`.

Tương tự, `case Integer n` khai báo biến `n` có kiểu `Integer`. Một nhánh **không khớp** sẽ không khởi tạo biến của nhánh đó và không chạy phần xử lý đi kèm.

Khác với hai nhánh trên, **`case null` và `default` không khai báo pattern variable**. Chúng dùng để phân loại đầu vào `null` và các giá trị còn lại.

Đây là trọng tâm của bài học: **cú pháp khai báo biến trong `case`, điều kiện để biến được khởi tạo, phạm vi có hiệu lực, và những lỗi thường gặp khi sử dụng case label**.

**Phiên bản Java:** `instanceof String text` đã được chuẩn hóa từ Java 16, nhưng **type pattern trong `switch`** được chuẩn hóa từ **Java 21**. Mọi chương trình hoàn chỉnh trong bài sử dụng Java 21 trở lên và không cần `--enable-preview`. Java 17 chỉ có tính năng switch pattern ở dạng preview, không nên dùng làm chuẩn biên dịch cho các ví dụ Java 21 bên dưới.

## 2. Phân biệt case constant và case pattern

Không phải mọi nhánh `case` đều khai báo biến. Hãy phân biệt rõ:

| Case label | Loại | Có khai báo biến mới? | Ý nghĩa |
| --- | --- | --- | --- |
| `case 1` | Hằng số | Không | Khớp giá trị nguyên `1` trong ngữ cảnh cho phép |
| `case "ready"` | Hằng chuỗi | Không | Khớp chuỗi bằng quy tắc tương ứng của switch |
| `case Status.ACTIVE` | Hằng enum | Không | Khớp đúng hằng `ACTIVE` của `Status` |
| `case null` | Nhãn `null` | Không | Nhận giá trị selector `null` |
| `default` | Nhãn mặc định | Không | Xử lý giá trị không thuộc case khác, theo quy tắc switch |
| `case String text` | **Type pattern** | **Có: `text`** | Khớp giá trị thuộc `String` và gắn biến |
| `case Number number` | **Type pattern** | **Có: `number`** | Khớp giá trị thuộc `Number` và gắn biến |
| `case Point(int x, int y)` | **Record pattern** | **Có: `x` và `y`** | Tách các thành phần của record `Point` |
| `case String s when !s.isBlank()` | Type pattern kèm guard | **Có: `s`** | Khớp kiểu trước, đánh giá điều kiện bổ sung sau |

Các ví dụ trong bảng là **mảnh cú pháp minh họa**, chỉ hợp lệ nếu kiểu selector tương thích với các nhánh được dùng và cấu trúc switch thỏa các quy tắc khác như dominance, exhaustiveness.

Cú pháp khai báo biến ở case label không có dấu `=`:

```java
case String text -> text.toUpperCase();
```

Không viết thành:

```java
// SAI: không phải cú pháp case pattern.
// case String text = value -> text.toUpperCase();
```

Trình biên dịch thực hiện việc kiểm tra kiểu và ràng buộc biến tự động. **Biến `text` không phải là phép ép kiểu thủ công**, cũng không phải tham số hàm hay biến toàn cục.

## 3. Cơ chế khớp và khởi tạo biến pattern

Giả sử một phương thức nhận đối tượng qua `Object value`:

```java
static String kind(Object value) {
    return switch (value) {
        case String text -> "String:" + text.length();
        case Integer n   -> "Integer:" + n;
        case null        -> "NULL";
        default          -> "OTHER";
    };
}
```

Quá trình chọn case có thể hiểu theo các bước:

1. Tính **selector** `value` một lần.
2. Nếu giá trị là `null`, `case null` được chọn.
3. Với giá trị khác `null`, Java xét case phù hợp theo các quy tắc switch; nếu giá trị là `String`, mẫu `String text` khớp và `text` được gắn với giá trị đó.
4. Nếu không phải `String` nhưng thuộc `Integer`, `Integer n` khớp và `n` được gắn với giá trị tương ứng.
5. Nếu không case nào trước đó áp dụng, nhánh `default` xử lý giá trị còn lại.

Cả `kind("Java")` và `kind(7)` đều biên dịch vì tham số có kiểu tĩnh `Object`. Ở runtime, đối tượng có kiểu khác nhau nên case được chọn khác nhau.

Biến pattern **chỉ được khởi tạo khi pattern đã khớp thành công**. Chẳng hạn `kind(7)` không tạo ra một biến `text` dùng được ở case `Integer`; biến `n` của case `Integer` mới là biến dành cho đường đi đó.

### Kiểu của biến lấy từ pattern, không phải kiểu selector

Với `Object value`, ta không thể trực tiếp gọi `value.length()`, vì `Object` không có phương thức `length()`. Trong nhánh:

```java
case String text -> text.length();
```

`text` được khai báo là `String`, nên gọi `length()` là hợp lệ. **Không có việc đổi kiểu khai báo của biến `value` từ `Object` thành `String`**. Khi cần API chuyên biệt, hãy dùng chính biến pattern.

### Pattern khác với kiểm tra kiểu và ép kiểu thủ công

Cách cũ:

```java
static String before(Object value) {
    if (value instanceof String) {
        String s = (String) value;
        return s.strip();
    }
    return "OTHER";
}
```

Với Java 21, có thể dùng case pattern:

```java
static String after(Object value) {
    return switch (value) {
        case String s -> s.strip();
        default       -> "OTHER";
    };
}
```

Điều khác biệt là `s` được khai báo ở **case label**, chứ không khai báo bằng một câu lệnh riêng sau kiểm tra. Tuy nhiên, đây chỉ là hai cách tổ chức cùng phép phân loại đơn giản; không nhất thiết chuyển mọi chuỗi `if` thành switch.

## 4. Phạm vi của biến khi dùng `case ... ->`

Với cú pháp **switch rule** sử dụng `->`, pattern variable có hiệu lực ở **phần xử lý của đúng rule đó**: biểu thức, block hoặc câu lệnh `throw` phía sau dấu mũi tên.

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "TEXT:" + text.strip();
        case Integer n   -> "NUMBER:" + n;
        default          -> "OTHER";
    };
}
```

Trong nhánh `String`, `text` có kiểu `String` và hợp lệ; trong nhánh `Integer`, `n` có kiểu `Integer` và hợp lệ. **`text` không được sử dụng tại rule `Integer` hoặc `default`**, vì các nhánh đó có thể chạy khi mẫu `String` chưa khớp.

### 4.1. Biến có hiệu lực trong block sau `->`

```java
static String summarize(Object value) {
    return switch (value) {
        case String text -> {
            String clean = text.strip();

            if (clean.isEmpty()) {
                yield "EMPTY_TEXT";
            }

            yield "TEXT:" + clean.length();
        }
        case Integer n -> {
            int doubled = n * 2;
            yield "INT:" + doubled;
        }
        default -> "OTHER";
    };
}
```

Nhánh `String` là một **block** gồm nhiều câu lệnh. `text` được dùng trong block này, kể cả các block con của nó, vì case đã khớp trước khi block được thực thi. Biến cục bộ `clean` được khai báo *bên trong* block và cũng không xuất hiện ở các nhánh khác.

Do đây là **switch expression** (có giá trị trả về), các block sử dụng `yield` để cung cấp giá trị cho biểu thức. `yield` không phải `return` của phương thức. Trong rule `case Integer n -> { ... }`, `n` chỉ có hiệu lực trong block đó.

### 4.2. Biến không tự lan ra sau switch

```java
static void printInfo(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        case Integer n   -> System.out.println(n);
        default          -> System.out.println("other");
    }

    // KHÔNG HỢP LỆ nếu bỏ chú thích:
    // System.out.println(text);
    // System.out.println(n);
}
```

Sau khi hoàn thành switch, không có bảo đảm rằng nhánh `String` hay nhánh `Integer` đã khớp. Biến của từng case không phải biến cục bộ chung của phương thức.

### 4.3. Có thể dùng lại tên giữa các case độc lập

```java
static String sameName(Object value) {
    return switch (value) {
        case String item  -> "TEXT:" + item;
        case Integer item -> "INT:" + item;
        default           -> "OTHER";
    };
}
```

Đoạn này hợp lệ: mỗi `item` là một pattern variable **riêng** trong rule của chính nó. Ở nhánh thứ nhất `item` là `String`, ở nhánh thứ hai là `Integer`; hai phạm vi không chồng lấn.

Để dễ đọc, khi nghiệp vụ phức tạp, tên riêng như `text`, `count`, `order` thường rõ nghĩa hơn.

## 5. Biến pattern dùng được trong `when` guard

Java 21 cho phép thêm **guard** bằng `when` để kiểm tra điều kiện bổ sung sau khi type pattern khớp:

```java
static String check(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "BLANK";
        case String text                     -> "TEXT:" + text.strip();
        default                              -> "OTHER";
    };
}
```

Có hai giai đoạn:

1. `value` phải khớp `String text`. Nếu không khớp, guard `text.isBlank()` **không được đánh giá**.
2. Nếu khớp, biến `text` đã có kiểu `String` và được dùng trong guard. Chỉ khi guard trả về `true`, Java mới chọn rule đó.

Một chuỗi khác `null` và không rỗng như `"Java"` sẽ không chọn nhánh đầu vì `isBlank()` trả `false`; nó tiếp tục khớp nhánh `case String text` không guard. Cả hai nhánh đều có thể dùng tên `text` vì đó là hai khai báo riêng biệt.

### Đặt nhánh có guard trước nhánh tổng quát

```java
static String lengthKind(Object value) {
    return switch (value) {
        case String s when s.length() >= 5 -> "LONG";
        case String s                      -> "SHORT";
        default                            -> "NOT_STRING";
    };
}
```

Thứ tự trên hợp lệ và hữu ích:

- Trước tiên nhận chuỗi dài ít nhất 5 ký tự.
- Nếu vẫn là `String` nhưng không thỏa guard, nhánh thứ hai xử lý.
- Các kiểu còn lại đi vào `default`.

**Đảo thứ tự sẽ gây lỗi domination:**

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case String s                      -> "ANY_STRING";
//     case String s when s.length() >= 5 -> "LONG";
//     default                            -> "OTHER";
// };
```

`case String s` không guard đã bao phủ mọi `String` khác `null`. Nhánh có guard sau đó không bao giờ được chọn.

### `when` không phải nơi khai báo một biến kiểu mới bất kỳ

Cú pháp khai báo biến pattern nằm ở `case String s`; `when` là **biểu thức boolean** kiểm tra thêm điều kiện. Không thể viết:

```java
// KHÔNG HỢP LỆ:
// case String s when s.length() -> "text";
```

Vì `s.length()` trả về `int`, không phải `boolean` hoặc `Boolean`. Cách hợp lệ:

```java
case String s when s.length() > 0 -> "non-empty";
```

Dòng trên chỉ là **một rule minh họa**; khi đặt vào switch hoàn chỉnh, cần thêm các rule thích hợp cho những kiểu khác và bảo đảm tính exhaustiveness.

### Guard và `null`

Nếu `value` là `null`, `case String text when text.isBlank()` không khớp, nên không gọi `isBlank()` trên `null`. Trong Java 21, nếu cần xử lý `null`, viết riêng `case null`. **`default` không tự bắt `null`** theo cách thường kỳ vọng từ phép `if`; nếu thiếu `case null`, selector `null` thường gây `NullPointerException`.

## 6. Khai báo nhiều biến qua record pattern trong case label

Ngoài type pattern, Java 21 còn chuẩn hóa **record patterns** (JEP 440), cho phép khai báo biến từ các thành phần của record ngay ở case label.

Giả sử:

```java
record Point(int x, int y) {}
```

Với selector kiểu `Object`, ta có thể viết:

```java
static String pointInfo(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "POINT:" + x + "," + y;
        default                 -> "OTHER";
    };
}
```

Điều gì xảy ra với `new Point(2, 5)`?

1. Record pattern `Point(int x, int y)` kiểm tra selector có phải một `Point` hay không.
2. Nếu khớp, hai thành phần record được trích xuất và ràng buộc vào **hai pattern variables `x` và `y`**, đều có kiểu `int`.
3. Phần bên phải `->` có thể dùng trực tiếp `x` và `y`, không cần gọi `point.x()`, `point.y()` nếu không cần giữ cả đối tượng.

Phân biệt với:

```java
case Point point -> "POINT:" + point.x() + "," + point.y();
```

Đây là **type pattern** `Point point`, khai báo đúng một biến `point` có kiểu `Point`; nó **không** trực tiếp tạo biến `x`, `y`. Ngược lại, record pattern `Point(int x, int y)` tạo hai biến thành phần, không tạo biến `point` trong ví dụ này.

### Record pattern với guard

```java
static String position(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == y -> "DIAGONAL";
        case Point(int x, int y)             -> "GENERAL_POINT";
        default                              -> "OTHER";
    };
}
```

Ở nhánh đầu, cả `x` và `y` **đã được ràng buộc** trước khi kiểm tra `x == y`. Nếu hai tọa độ không bằng nhau, Java xét nhánh record pattern kế tiếp. Hai lần viết `x`, `y` thuộc các case khác nhau, nên là các biến khác nhau.

### Tên `var` trong record pattern

Có thể để trình biên dịch suy ra kiểu của thành phần:

```java
case Point(var x, var y) -> "POINT:" + x + "," + y;
```

Với `record Point(int x, int y)`, `x` và `y` được suy ra kiểu `int`. Đây là **`var` trong nested type patterns của record pattern**. Không nên nhầm với việc viết một case pattern độc lập `case var x` như cách áp dụng máy móc cú pháp này; bài học dùng các dạng chuẩn hóa được minh họa cho Java 21.

### Đặt tên biến có nghĩa và tránh trùng trong cùng record pattern

```java
// KHÔNG BIÊN DỊCH vì một record pattern
// khai báo hai biến trùng tên:
// case Point(int x, int x) -> "SAME";
```

Nếu muốn kiểm tra hai tọa độ bằng nhau, dùng **hai biến khác tên** và một guard:

```java
case Point(int x, int y) when x == y -> "SAME";
```

Như vậy vừa đúng cú pháp, vừa diễn đạt rõ điều kiện nghiệp vụ.

## 7. Dấu `:` so với dấu `->`: tránh fall-through khi có biến pattern

Java vẫn hỗ trợ **switch statement dạng truyền thống**, sử dụng dấu `:` và các nhóm câu lệnh. Pattern variable cũng có thể được khai báo bằng case label ở dạng này:

```java
static String oldStyle(Object value) {
    switch (value) {
        case String text:
            return "STRING:" + text.length();

        case Integer n:
            return "INTEGER:" + n;

        case null:
            return "NULL";

        default:
            return "OTHER";
    }
}
```

Đây là **một phương thức hợp lệ của Java 21**. `text` có hiệu lực trong các câu lệnh của **nhóm lệnh** được gắn với `case String text:`; `n` có hiệu lực trong nhóm của `case Integer n:`. Do mỗi nhóm đều `return`, không có đường đi từ nhóm trước sang nhóm sau.

### Vì sao fall-through có thể gây lỗi biên dịch?

Xem mã **cố ý không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case String text:
//         System.out.println(text);  // Không có break/return.
//     case Integer number:
//         System.out.println(number.intValue());
//     default:
//         System.out.println("OTHER");
// }
```

Nếu nhánh `String text` chạy rồi **rơi tiếp** sang nhánh `Integer number` mà không thoát, chương trình có thể truy cập `number` khi pattern `Integer` chưa hề khớp. Java 21 từ chối cấu trúc đó để tránh đọc một pattern variable chưa được khởi tạo.

Một nhóm lệnh gắn với case pattern khai báo biến cũng không được ghép nhiều nhãn theo cách khiến cùng một lệnh có thể được gọi mà không khởi tạo biến cần thiết:

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case String text:
//     case Integer number:
//         System.out.println(number);
//         break;
//     default:
//         break;
// }
```

Nếu vào từ `case String text`, `number` không khớp, nên nhánh chung không thể dùng `number` như đã được khởi tạo.

**Cách sửa dễ bảo trì:** ưu tiên `case ... ->` khi pattern matching, hoặc bảo đảm mỗi nhóm dấu `:` có đường thoát phù hợp (`break`, `return` hoặc `throw`) và không dùng một pattern variable trong nhóm có thể được vào từ nhãn khác.

### Không nhầm với nhóm nhiều hằng

Ví dụ dưới đây hợp lệ với case constants:

```java
enum Status { NEW, ACTIVE, DONE }

static boolean finished(Status s) {
    return switch (s) {
        case NEW, ACTIVE -> false;
        case DONE        -> true;
    };
}
```

`case NEW, ACTIVE` gồm hai **hằng**, không khai báo biến pattern. Nó không phải ví dụ về “hai pattern variables trong một case label”.

Ở Java 21, một **case label dạng pattern** có dạng `case Pattern [when Guard]`; do đó cách viết như `case String s, Integer n -> ...` không phải cú pháp để tạo hai biến cho một rule. Viết hai rule riêng hoặc trích xuất phần xử lý chung vào phương thức nếu cần.

## 8. Quy tắc tên biến, trùng tên và scope

### 8.1. Không khai báo tên trùng với biến cục bộ đã trong phạm vi

```java
// KHÔNG BIÊN DỊCH:
// static String bad(Object value) {
//     String text = "existing";
//     return switch (value) {
//         case String text -> text;
//         default          -> "other";
//     };
// }
```

Biến cục bộ `text` đã được khai báo trong phạm vi của phương thức. Trình biên dịch không cho phép case pattern khai báo một biến cục bộ khác trùng tên đang trong phạm vi đó.

**Sửa bằng tên khác:**

```java
static String good(Object value) {
    String fallback = "existing";
    return switch (value) {
        case String text -> text;
        default          -> fallback;
    };
}
```

### 8.2. Dùng lại tên ở hai rule khác nhau thì được

```java
static String reused(Object value) {
    return switch (value) {
        case String v  -> "S:" + v;
        case Integer v -> "I:" + v;
        default        -> "OTHER";
    };
}
```

Hai `v` thuộc các phạm vi khác nhau của các rule riêng. Chúng không làm cho giá trị được chia sẻ giữa các case.

### 8.3. Biến pattern không phải thành viên của đối tượng

```java
// Trong một phương thức nhận Object value:
switch (value) {
    case String text -> System.out.println(text);
    default          -> System.out.println("other");
}

// Ở đây không có biến text được khai báo cho phương thức.
// Không thể gọi text.toUpperCase() sau switch.
```

Pattern variable không “ghi nhớ” một kết quả khớp để dùng lâu dài. Nếu cần sử dụng dữ liệu đã chuẩn hóa ở phía sau, hãy **trả kết quả từ switch expression**:

```java
static String normalized(Object value) {
    String result = switch (value) {
        case String s -> s.strip();
        case null     -> "";
        default       -> value.toString();
    };
    return result;
}
```

Ở đây biến `result` là biến cục bộ thông thường, được khai báo **ngoài switch expression**, nhận giá trị của biểu thức. Đây mới là biến có thể tiếp tục sử dụng phía sau.

### 8.4. Lambda bắt biến pattern

Trong một case rule, có thể dùng biến pattern trong lambda nếu đáp ứng quy tắc biến cục bộ được bắt (*captured variable*) là `final` hoặc *effectively final*:

```java
// Chỉ là mảnh minh họa trong switch statement:
case String text -> {
    Runnable action = () -> System.out.println(text.toUpperCase());
    action.run();
}
```

Nếu gán lại `text` rồi vẫn muốn lambda bắt `text`, trình biên dịch có thể từ chối vì biến không còn *effectively final*. Đây là quy tắc chung khi lambda sử dụng biến cục bộ, không phải một ngoại lệ của switch pattern.

## 9. Dominance: khi case rộng che khuất case hẹp

Đây là lỗi quan trọng khi khai báo biến ở case label. Giả sử selector là `Object value`:

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case Number number -> "NUMBER";
//     case Integer n     -> "INTEGER"; // Bị Number che khuất.
//     default            -> "OTHER";
// };
```

`case Number number` không guard đã khớp tất cả giá trị `Integer`, vì `Integer` là một lớp con của `Number`. Khi đó `case Integer n` ở phía sau không thể là nhánh đầu tiên áp dụng, nên Java báo lỗi **dominated case label**.

**Cách đúng: case chuyên biệt trước:**

```java
static String numberKind(Object value) {
    return switch (value) {
        case Integer n    -> "INTEGER:" + n;
        case Number other -> "NUMBER:" + other;
        default           -> "OTHER";
    };
}
```

Ở đây `numberKind(3)` trả `"INTEGER:3"`; `numberKind(2.5)` trả `"NUMBER:2.5"`. Không có nhánh bất khả thi.

### Guard giúp đặt trường hợp đặc biệt trước trường hợp tổng quát

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "NEGATIVE";
        case Integer n            -> "INTEGER";
        default                   -> "OTHER";
    };
}
```

Vì guard không luôn đúng, nhánh thứ nhất **không che khuất** nhánh thứ hai. Ngược lại, nhánh `case Integer n` không guard đứng trước sẽ che khuất nhánh có guard phía sau.

### Catch-all pattern và `default`

Trên selector `Object`:

```java
static String everything(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OTHER_OBJECT";
    };
}
```

`case Object o` là type pattern bao quát các đối tượng khác `null` còn lại, và nó tạo biến `o`. Với kiểu selector `Object`, rule này được xem là **unconditional pattern** cho trường hợp đối tượng; không thêm `default` sau đó vì sẽ xung đột với nhánh bao quát.

**Chú ý:** `case Object o` không thay thế nhu cầu xử lý `null` theo ý định riêng. Trong ví dụ trên `case null` đã tách rõ trường hợp đó.

## 10. Exhaustiveness và `null` khi khai báo biến ở case label

Một **switch expression** phải có khả năng tạo giá trị cho mọi trường hợp hợp lệ theo kiểm tra exhaustiveness của Java. Với kiểu `Object`, thường dùng `default` hoặc một unconditional pattern phù hợp:

```java
static int score(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer n   -> n;
        default          -> 0;
    };
}
```

`default` làm switch expression bao phủ các kiểu không phải `String` hoặc `Integer`. Nhưng nếu truyền `null` và không có `case null`, switch thường ném `NullPointerException` thay vì tự chạy `default`. Khi muốn `null` trả `0`, viết:

```java
static int safeScore(Object value) {
    return switch (value) {
        case null        -> 0;
        case String text -> text.length();
        case Integer n   -> n;
        default          -> 0;
    };
}
```

`null` không phải “đối tượng của mọi kiểu”, nên không được ràng buộc vào `String text` hoặc `Integer n` trong ví dụ trên.

### Trường hợp sealed hierarchy

Với các kiểu được giới hạn bởi `sealed`, trình biên dịch có thể biết các loại cần bao phủ:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static String shapeLabel(Shape shape) {
    return switch (shape) {
        case Circle(double r)          -> "CIRCLE:" + r;
        case Rectangle(double w, double h) -> "RECT:" + w + "x" + h;
    };
}
```

Đoạn trên **minh họa phương thức** nằm trong một lớp cùng với các khai báo `Shape`, `Circle`, `Rectangle` phù hợp (các khai báo có thể là các member types). Java 21 có thể chứng minh switch expression bao phủ toàn bộ các kiểu con trực tiếp được `Shape` cho phép, nên không cần `default` cho những đối tượng `Shape` khác `null`.

Tuy nhiên, nếu `shape == null`, thiếu `case null` vẫn dẫn đến `NullPointerException`. Tính exhaustive theo các kiểu con không tự đồng nghĩa với việc `null` được xử lý.

**Điểm liên quan đến khai báo biến:** `case Circle(double r)` khai báo `r`, còn `case Rectangle(double w, double h)` khai báo `w`, `h`. Các tên này chỉ dùng trong nhánh tương ứng, không được truy cập chéo giữa các nhánh.

## 11. Ví dụ Java 21 hoàn chỉnh: case type pattern, record pattern, guard và scope

Tạo tệp có tên **`CaseLabelBindingDemo.java`** với nội dung sau. Các type `Point` và `State` được khai báo bên trong lớp để ví dụ có thể biên dịch trong một tệp duy nhất.

```java
public class CaseLabelBindingDemo {

    record Point(int x, int y) {}

    enum State {
        OPEN, CLOSED
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";

            case String text when text.isBlank() -> "BLANK";
            case String text -> "TEXT:" + text.strip();

            case Integer n when n < 0 -> "NEG:" + n;
            case Integer n -> "INT:" + n;

            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y) -> "POINT:" + x + "," + y;

            default -> "OTHER";
        };
    }

    static String colonStyle(Object value) {
        switch (value) {
            case String text:
                return "COLON-S:" + text.length();

            case Integer n:
                return "COLON-I:" + n;

            case null:
                return "COLON-NULL";

            default:
                return "COLON-OTHER";
        }
    }

    static String stateLabel(Object value) {
        return switch (value) {
            case State.OPEN -> "OPEN";
            case State state -> "STATE:" + state.name();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("  Java  "));
        System.out.println(classify("   "));
        System.out.println(classify(-3));
        System.out.println(classify(7));
        System.out.println(classify(new Point(4, 4)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(true));
        System.out.println(classify(null));

        System.out.println(colonStyle("Cat"));
        System.out.println(colonStyle(12));
        System.out.println(colonStyle(null));

        System.out.println(stateLabel(State.OPEN));
        System.out.println(stateLabel(State.CLOSED));
    }
}
```

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 CaseLabelBindingDemo.java
java CaseLabelBindingDemo
```

**Kết quả chuẩn:**

```text
TEXT:Java
BLANK
NEG:-3
INT:7
DIAGONAL:4
POINT:2,5
OTHER
NULL
COLON-S:3
COLON-I:12
COLON-NULL
OPEN
STATE:CLOSED
```

### Giải thích đầu ra

1. `classify("  Java  ")`: khớp `String text`; `isBlank()` sai, nhánh `String text` phía sau dùng `strip()` và trả `TEXT:Java`.
2. `classify("   ")`: guard `text.isBlank()` đúng, trả `BLANK`.
3. `classify(-3)`: giá trị `int` được đóng hộp thành `Integer` khi truyền cho `Object`. Guard `n < 0` đúng nên trả `NEG:-3`; với `7`, guard sai và nhánh `Integer n` tổng quát trả `INT:7`.
4. Hai giá trị `Point` được kiểm tra bằng record pattern. `Point(4, 4)` khớp guard `x == y`; `Point(2, 5)` đi tới nhánh `Point(int x, int y)` còn lại.
5. `true` được đóng hộp thành `Boolean` và không khớp `String`, `Integer`, `Point`, nên trả `OTHER`. `null` được bắt bởi `case null`.
6. `colonStyle` dùng cú pháp dấu `:`; từng nhánh đều `return`, tránh fall-through và chỉ sử dụng biến pattern ở nhóm lệnh phù hợp.
7. `stateLabel(State.OPEN)` khớp đúng **case constant** `State.OPEN`, không tạo biến. `stateLabel(State.CLOSED)` khớp **type pattern** `State state`, nên có thể gọi `state.name()` và trả `STATE:CLOSED`.

Toàn bộ các tính năng được dùng trong chương trình đã được chuẩn hóa ở Java 21; không yêu cầu preview. Nếu IDE đang đặt Java language level thấp hơn 21, hãy nâng cấu hình dự án khi chạy ví dụ này.

## 12. Lỗi biên dịch thường gặp và cách sửa

### Lỗi 1: khai báo biến như biến cục bộ ngay sau từ khóa `case`

```java
// SAI:
// case String text = (String) value -> text.length();
```

**Sửa:** viết `case String text -> ...`. Đây là type pattern, không phải câu lệnh khai báo biến có phép gán.

### Lỗi 2: dùng biến pattern ở case khác

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case String text -> text.length();
//     case Integer n -> text.length(); // text ngoài phạm vi
//     default -> 0;
// };
```

**Sửa:** dùng `n` trong nhánh `Integer`, hoặc viết logic chung ở một phương thức ngoài switch với tham số riêng khi thật sự cần.

### Lỗi 3: gộp các type patterns có biến vào một case list

```java
// KHÔNG BIÊN DỊCH trên Java 21:
// case String s, Integer n -> "MATCHED";
```

**Sửa:** dùng hai rule riêng biệt hoặc gom các hằng thật sự vào case list; không lẫn case pattern với danh sách case constants trong cú pháp Java 21.

### Lỗi 4: trùng tên với biến đang ở phạm vi bao ngoài

```java
// KHÔNG BIÊN DỊCH:
// String text = "outer";
// switch (value) {
//     case String text -> System.out.println(text);
//     default -> {}
// }
```

**Sửa:** đổi tên pattern variable như `case String matchedText`.

### Lỗi 5: guard được viết trước khi có biến

```java
// KHÔNG HỢP LỆ:
// case when text.isBlank() String text -> "BLANK";
```

**Sửa:** khai báo pattern trước rồi mới đặt guard: `case String text when text.isBlank() -> ...`.

### Lỗi 6: `case null` bị hiểu là một type pattern

```java
// Không tồn tại biến nullValue chỉ vì nhánh này:
// case null -> System.out.println(nullValue);
```

**Sửa:** xử lý `null` trực tiếp theo nghiệp vụ, chẳng hạn `case null -> "MISSING"`; không cố truy cập một biến pattern không được khai báo.

### Lỗi 7: fall-through vào nhánh khai báo biến

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case String s:
//         System.out.println(s);
//     case Integer n:
//         System.out.println(n);
//     default:
//         break;
// }
```

**Sửa:** dùng `case String s -> ...` và `case Integer n -> ...`; hoặc tách các nhóm dấu `:` và bảo đảm không có đường đi rơi vào nhóm có biến chưa khớp.

### Lỗi 8: đặt pattern tổng quát trước pattern chuyên biệt

```java
// KHÔNG BIÊN DỊCH:
// case Number n -> "NUMBER";
// case Integer n -> "INTEGER";
```

**Sửa:** đặt `case Integer n` trước `case Number n`. Các biến cùng tên ở hai rule độc lập được phép; vấn đề thật sự ở ví dụ là **dominance**.

## 13. Bài tập tự đánh giá

### Bài 1: nhận diện biến được khai báo

Cho các nhãn:

```java
case "OK" -> "ok";
case String s -> s.strip();
case Point(int x, int y) -> x + "," + y;
case null -> "missing";
```

**Câu hỏi:** Các nhãn nào khai báo biến? Các đoạn trên chỉ là các mảnh cú pháp, không mặc nhiên là một switch hoàn chỉnh hợp lệ.

**Đáp án:** `case String s` khai báo `s`; `case Point(int x, int y)` khai báo `x` và `y`. `case "OK"` và `case null` không khai báo biến.

### Bài 2: phân tích guard

```java
static String test(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
```

Dự đoán:

- `test("Java")` → `"LONG"`.
- `test("Go")` → `"SHORT"`.
- `test(100)` → `"OTHER"`.

Giải thích: guard chỉ được đánh giá sau khi mẫu `String s` khớp; các rule có `s` là các phạm vi tách biệt. Lưu ý phương thức chưa có `case null`; nếu truyền `null`, không được kết luận rằng `default` tự xử lý `null`.

### Bài 3: sửa switch sai thứ tự

Đoạn sau không biên dịch:

```java
// return switch (value) {
//     case Number n -> "NUMBER";
//     case Double d -> "DOUBLE";
//     default -> "OTHER";
// };
```

**Đáp án:** `Number n` thống trị nhánh `Double d` phía sau. Sửa thành `case Double d -> "DOUBLE";` trước `case Number n -> "NUMBER";`.

### Bài 4: dùng record pattern

Cho `record Size(int width, int height) {}`. Viết switch expression nhận `Object` và trả `"SQUARE"` nếu `width == height`, `"RECTANGLE"` cho các `Size` còn lại, `"OTHER"` cho mọi kiểu khác.

**Gợi ý:**

```java
static String kind(Object value) {
    return switch (value) {
        case Size(int w, int h) when w == h -> "SQUARE";
        case Size(int w, int h) -> "RECTANGLE";
        default -> "OTHER";
    };
}
```

Đoạn này giả định `Size` đã được khai báo phù hợp trong phạm vi. Các biến `w`, `h` của nhánh đầu **không phải** cùng khai báo với `w`, `h` của nhánh sau.

### Bài 5: chọn dấu `:` hay `->`

Bạn đang viết switch nhận `Object` với nhiều type patterns, trong đó mỗi nhánh có biến riêng và logic phức tạp. Hãy giải thích vì sao cách viết `case T t -> { ... }` thường dễ bảo trì hơn `case T t: ...`.

**Đáp án gợi ý:** `->` tạo rule với phạm vi xử lý rõ ràng và không có fall-through sang rule khác; giúp tránh đường đi truy cập pattern variable chưa được khởi tạo. Dấu `:` vẫn hợp lệ trong Java 21, nhưng phải đặc biệt cẩn thận với nhóm lệnh và `break`, `return`, `throw`.

## 14. Checklist và ghi nhớ

Trước khi đưa code dùng pattern switch vào dự án, tự kiểm tra:

1. **Phiên bản ngôn ngữ:** dùng Java 21+ cho tính năng pattern switch ổn định.
2. **Selector:** có kiểu tương thích với từng case pattern (đặc biệt trong hệ kế thừa và generic).
3. **Khai báo biến:** `case T name` khai báo biến `name`; `case CONSTANT`, `case null`, `default` không khai báo.
4. **Guard:** `when` đứng **sau pattern**, trả boolean và được phép dùng biến pattern đã khớp.
5. **Phạm vi:** chỉ dùng pattern variable trong rule hoặc nhóm câu lệnh gắn với case đó, và trong guard tương ứng; không dùng ở case khác hay sau switch.
6. **Thứ tự:** pattern chuyên biệt hoặc có guard trước pattern tổng quát để tránh dominance.
7. **Fall-through:** nếu dùng dấu `:`, tránh đường đi không khởi tạo biến pattern; ưu tiên `->` khi phù hợp.
8. **Exhaustiveness:** switch expression và enhanced switch statement cần bao phủ đủ các trường hợp; dùng `default`, unconditional pattern hoặc sealed hierarchy phù hợp.
9. **Null:** nếu cần xử lý `null`, dùng `case null` tường minh; không hiểu `default` là bao trùm null.
10. **Tên biến:** tránh trùng với local variable đã trong phạm vi; đặt tên có ý nghĩa để code dễ đọc.

**Tóm tắt:** Biến ở case label là kết quả của **pattern matching**, không phải một biến được tạo cho mọi nhánh. `case String text` chỉ ràng buộc `text` khi selector khớp `String`; Java bảo đảm biến đã được khởi tạo trong guard và phần xử lý của nhánh tương ứng. Khi dùng đúng phạm vi, case pattern giúp loại bỏ ép kiểu lặp lại và làm cho các nhánh phân loại đối tượng rõ ràng, an toàn hơn.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification §6.3.3 — Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3)
- [Java SE 21 Language Specification §14.11 — Switch Statement and Case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)

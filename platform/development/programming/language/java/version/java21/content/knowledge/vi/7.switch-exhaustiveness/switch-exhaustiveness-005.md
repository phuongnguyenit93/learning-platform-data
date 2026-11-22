# Exhaustiveness với record pattern lồng nhau và record generic

## Mục tiêu

Trong Java 21, compiler có thể kiểm tra tính đầy đủ (*exhaustiveness*) của switch expression có pattern. Khi viết switch trên sealed hierarchy hoặc record, việc kiểm tra này có thể đi sâu vào record pattern lồng nhau để xác định một nhánh đã bao phủ toàn bộ trường hợp của kiểu dữ liệu hay chưa.

Với record generic, compiler còn cần xét kiểu tĩnh của selector và suy luận kiểu component khi record pattern không ghi tường minh type argument. Vì vậy, một switch có vẻ đã liệt kê đủ các kiểu record vẫn có thể chưa exhaustive nếu pattern lồng nhau chỉ khớp một phần dữ liệu.

Bài học này tập trung vào cách xác định pattern nào bao phủ toàn bộ giá trị, cách kết hợp nested record patterns với sealed types và cách dùng generic record patterns trong switch expression Java 21.

## 1. Exhaustiveness là gì?

Một switch expression phải xử lý mọi trường hợp mà compiler xem là có thể xảy ra đối với kiểu selector. Nếu thiếu trường hợp, compiler báo lỗi ngay khi biên dịch. Ví dụ switch trên một sealed interface:

```java
sealed interface Payment permits CashPayment, CardPayment {
}

record CashPayment(int amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

class PaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case CashPayment cash -> "Tiền mặt: " + cash.amount();
            case CardPayment card -> "Thẻ: " + card.lastFourDigits();
        };
    }
}
```

`Payment` là sealed interface và chỉ cho phép hai kiểu triển khai đã khai báo. Hai nhãn `case` bao phủ cả `CashPayment` và `CardPayment`, nên switch expression đầy đủ mà không cần `default`.

Nếu thêm một kiểu triển khai mới vào danh sách `permits`, switch này phải được xem xét lại. Khi biên dịch lại, compiler có thể báo thiếu nhánh cho kiểu mới. Đây là lợi ích quan trọng của sealed hierarchy kết hợp với switch: thay đổi mô hình dữ liệu có thể được phát hiện ngay trong quá trình biên dịch.

## 2. Record pattern có thể bao phủ toàn bộ một record

Một record pattern kiểm tra kiểu record và tiếp tục matching các component theo thứ tự khai báo. Pattern chỉ bao phủ toàn bộ record khi các component pattern bên trong đều bao phủ mọi giá trị có thể của component tương ứng.

Ví dụ:

```java
record Point(int x, int y) {
}

class PointDescription {
    static String describe(Point point) {
        return switch (point) {
            case Point(var x, var y) -> "(" + x + ", " + y + ")";
        };
    }
}
```

`Point(var x, var y)` deconstruct cả hai component. `var` pattern nhận mọi giá trị của component tương ứng, vì vậy pattern này bao phủ toàn bộ các giá trị `Point` không-null. Switch expression chỉ có một nhánh nhưng vẫn exhaustive đối với kiểu selector `Point`.

Có thể dùng type pattern cho component nếu muốn giới hạn trường hợp khớp. Tuy nhiên, một pattern giới hạn như vậy không nhất thiết bao phủ toàn bộ record. Ví dụ, với component tham chiếu có thể là `null`, type pattern `String text` không khớp giá trị `null`.

```java
record Message(String text) {
}

class MessageDescription {
    static String describe(Message message) {
        return switch (message) {
            case Message(String text) -> "Nội dung: " + text;
            case Message(var text) -> text == null ? "Không có nội dung" : text;
        };
    }
}
```

Nhánh đầu xử lý component `text` là chuỗi không-null. Nhánh sau dùng `var` để bao phủ phần còn lại, bao gồm trường hợp component là `null`. Vì thế, hai pattern kết hợp bao phủ toàn bộ các giá trị `Message` không-null.

Lưu ý: `case null` của switch xử lý selector là `null`; `Message(var text)` xử lý một đối tượng `Message` không-null có component `text` là `null`. Đây là hai vị trí khác nhau trong đồ thị dữ liệu.

## 3. Exhaustiveness phải xét cả nested record pattern

Khi record chứa một record khác, compiler cần xét pattern ở từng cấp. Việc bao phủ record ngoài chưa đủ nếu pattern lồng bên trong chỉ khớp một phần component.

```java
record Point(int x, int y) {
}

record Rectangle(Point topLeft, Point bottomRight) {
}
```

Pattern sau chỉ khớp với `Rectangle` có cả hai component là `Point`:

```java
case Rectangle(
        Point(var leftX, var topY),
        Point(var rightX, var bottomY)) -> "Hình chữ nhật";
```

Nếu `topLeft` hoặc `bottomRight` là `null`, nested `Point(...)` không khớp. Do đó, không thể chỉ nhìn thấy tên `Rectangle` ở nhãn `case` rồi kết luận pattern đó bao phủ mọi `Rectangle`.

Nếu cần xử lý riêng trường hợp cả hai component đều là `Point`, đồng thời vẫn bao phủ mọi `Rectangle`, có thể thêm một record pattern tổng quát hơn:

```java
class RectangleDescription {
    static String describe(Rectangle rectangle) {
        return switch (rectangle) {
            case Rectangle(
                    Point(var leftX, var topY),
                    Point(var rightX, var bottomY)) ->
                    "Tọa độ: " + leftX + ", " + topY + " đến "
                            + rightX + ", " + bottomY;
            case Rectangle(var topLeft, var bottomRight) ->
                    "Rectangle có component chưa đủ dữ liệu Point";
        };
    }
}
```

Pattern đầu xử lý trường hợp cụ thể. Pattern thứ hai dùng `var` cho hai component nên bao phủ các trường hợp `Rectangle` còn lại, kể cả khi một trong hai component là `null`. Nhờ đó switch expression đầy đủ cho kiểu selector `Rectangle`.

## 4. Kết hợp nested record patterns với sealed hierarchy

Một sealed hierarchy có thể gồm các record chứa những kiểu dữ liệu khác. Để switch expression exhaustive, cần bao phủ mọi subtype được phép và bảo đảm các record pattern cho từng subtype không bỏ sót trường hợp.

```java
import java.util.Objects;

sealed interface Expression permits Literal, Addition {
}

record Literal(int value) implements Expression {
}

record Addition(Expression left, Expression right) implements Expression {
    Addition {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
    }
}

class ExpressionEvaluator {
    static int evaluate(Expression expression) {
        return switch (expression) {
            case Literal(var value) -> value;
            case Addition(
                    Literal(var left),
                    Literal(var right)) -> left + right;
            case Addition(var left, var right) -> evaluate(left) + evaluate(right);
        };
    }
}
```

Switch trên `Expression` bao phủ hai subtype được phép:

- `Literal(var value)` là record pattern tổng quát cho `Literal`.
- `Addition(Literal(...), Literal(...))` xử lý trường hợp hai toán hạng đều là literal.
- `Addition(var left, var right)` xử lý mọi trường hợp `Addition` còn lại, bao gồm các biểu thức lồng nhau.

Hai component `left` và `right` được kiểm tra không-null trong compact constructor của `Addition`, phù hợp với giả định của hàm `evaluate`. Nếu mô hình cho phép component null, cần quy định cách xử lý null trong logic nghiệp vụ; tính exhaustive của switch trên kiểu selector không thay thế cho việc xác thực dữ liệu bên trong record.

Ví dụ trên cũng cho thấy nested record pattern có thể giúp tối ưu một trường hợp cấu trúc cụ thể, trong khi pattern tổng quát hơn giữ cho switch đầy đủ.

## 5. Pattern có guard không tự bao phủ toàn bộ kiểu

Guard `when` bổ sung điều kiện sau khi pattern khớp. Một pattern có guard chỉ bao phủ các giá trị thỏa điều kiện guard, nên không thể mặc định coi nó là pattern tổng quát cho kiểu đó.

```java
record Score(int value) {
}

class ScoreDescription {
    static String describe(Score score) {
        return switch (score) {
            case Score(var value) when value >= 50 -> "Đạt";
            case Score(var value) -> "Chưa đạt";
        };
    }
}
```

Pattern `Score(var value)` đầu tiên có guard chỉ xử lý điểm từ 50 trở lên. Khi guard trả về `false`, switch xét nhánh tiếp theo. Nhánh thứ hai không có guard nên bao phủ mọi `Score` còn lại và làm switch exhaustive.

Nếu chỉ có nhánh `case Score(var value) when value >= 50`, switch expression vẫn thiếu các trường hợp điểm dưới 50. Compiler không thể giả định guard luôn đúng, ngay cả khi điều kiện có vẻ đơn giản.

Khi một guard chứa logic phức tạp hoặc gọi method, càng cần một nhánh không guard hoặc một `default` thích hợp để bảo đảm mọi trường hợp đều được xử lý.

## 6. Record generic và suy luận kiểu component

Record có thể khai báo type parameter như class thông thường:

```java
record Box<T>(T value) {
}
```

Khi selector có kiểu `Box<String>`, compiler có thể suy luận kiểu component từ kiểu tĩnh của selector. Ví dụ:

```java
class GenericRecordPattern {
    static String describe(Box<String> box) {
        return switch (box) {
            case Box(var value) ->
                    value == null ? "Không có nội dung" : value.toUpperCase();
        };
    }
}
```

Trong method này, kiểu component `T` được suy luận là `String`, vì selector có kiểu `Box<String>`. Do đó, biến `value` có thể gọi `toUpperCase()` mà không cần ép kiểu. `var` pattern cũng nhận trường hợp component là `null`, nên một nhánh này bao phủ mọi giá trị `Box<String>` không-null.

Với record có nhiều type parameter, việc suy luận được thực hiện cho từng component:

```java
record Pair<L, R>(L left, R right) {
}

class GenericPairPattern {
    static String describe(Pair<String, Integer> pair) {
        return switch (pair) {
            case Pair(var left, var right) ->
                    left + " có số lượng " + right;
        };
    }
}
```

Trong ví dụ, `left` có kiểu tĩnh `String`, còn `right` có kiểu tĩnh `Integer`, dựa trên kiểu tham số của selector. Record pattern không cần lặp lại type argument nếu compiler có đủ thông tin để suy luận.

## 7. Type erasure và giới hạn khi kiểm tra generic ở runtime

Java dùng type erasure cho generic. Thông tin tham số kiểu như `String` hoặc `Integer` không được giữ như một kiểu runtime riêng cho từng đối tượng `Box<T>`. Vì vậy, không thể dùng type pattern thông thường để kiểm tra một đối tượng bất kỳ có chính xác kiểu generic `Box<String>` chỉ dựa trên runtime type.

Ví dụ, khi nhận `Object`, pattern `Box(var value)` có thể xác định đối tượng là một `Box` và lấy component, nhưng không tự chứng minh component đó là `String`:

```java
class UnknownGenericRecord {
    static String describe(Object candidate) {
        return switch (candidate) {
            case Box(var value) -> String.valueOf(value);
            case null -> "null";
            default -> "Không phải Box";
        };
    }
}
```

Trong ngữ cảnh selector là `Object`, không nên giả định `value` có kiểu `String`. Nếu nghiệp vụ cần dữ liệu chuỗi, hãy kiểm tra component sau khi deconstruct:

```java
class ValidateGenericRecord {
    static String describe(Object candidate) {
        return switch (candidate) {
            case Box(var value) when value instanceof String text ->
                    "Chuỗi: " + text;
            case Box(var value) -> "Giá trị khác: " + value;
            case null -> "null";
            default -> "Không phải Box";
        };
    }
}
```

Guard `when` kiểm tra kiểu component ở runtime và chỉ dùng biến `text` sau khi điều kiện `instanceof` thành công. Nhánh `Box(var value)` tiếp theo xử lý các component khác. Đây là cách tách biệt giữa suy luận kiểu tĩnh của generic record và xác thực dữ liệu thực tế nhận từ nguồn không tin cậy.

Không nên dùng raw type như `Box` trong thiết kế mới nếu có thể giữ được thông tin generic. Raw type làm mất lợi ích kiểm tra kiểu ở compile time và thường khiến code phải ép kiểu hoặc xác thực lại nhiều hơn.

## 8. Generic record lồng nhau

Một record generic có thể chứa record generic khác. Khi pattern lồng nhau, compiler suy luận kiểu theo kiểu tĩnh của selector và cấu trúc component:

```java
record Box<T>(T value) {
}

record Pair<L, R>(L left, R right) {
}

class NestedGenericRecordPattern {
    static String describe(Pair<Box<String>, Box<Integer>> pair) {
        return switch (pair) {
            case Pair(Box(var name), Box(var count)) ->
                    (name == null ? "(không tên)" : name)
                            + ": " + count;
        };
    }
}
```

Kiểu tĩnh của selector cho biết component `left` là `Box<String>` và `right` là `Box<Integer>`. Các nested record pattern tiếp tục deconstruct từng `Box`; vì vậy `name` có kiểu `String` và `count` có kiểu `Integer`.

`var` được dùng ở component bên trong để chấp nhận cả giá trị null của component. Nếu thay bằng type pattern như `String name`, pattern lồng nhau chỉ khớp khi component tương ứng không-null và có kiểu tương thích. Khi đó, cần thêm pattern bao phủ trường hợp còn lại nếu muốn switch exhaustive.

## 9. Null ở selector và null trong component

Có hai tình huống cần phân biệt:

| Vị trí null | Ví dụ | Cách xử lý |
|---|---|---|
| Selector của switch | `box == null` | Dùng `case null` nếu muốn switch xử lý giá trị null; nếu không, switch trên reference selector null sẽ ném `NullPointerException` |
| Component của record | `new Box<String>(null)` | Dùng `var` pattern để bind component, hoặc thêm nhánh phù hợp nếu nested type pattern không khớp null |

Ví dụ:

```java
class NullLocations {
    static String describe(Box<String> box) {
        return switch (box) {
            case null -> "Selector null";
            case Box(String text) -> "Component: " + text;
            case Box(var value) -> "Component null: " + value;
        };
    }
}
```

`case null` xử lý khi chính `box` không tồn tại. `case Box(String text)` chỉ xử lý `Box` không-null có component chuỗi không-null. `case Box(var value)` xử lý `Box` còn lại, bao gồm trường hợp component null. Như vậy, switch thể hiện rõ hai tầng null khác nhau.

## 10. Exhaustiveness khi sealed hierarchy thay đổi

Compiler xác định các subtype được phép của sealed hierarchy dựa trên khai báo mà nó nhìn thấy khi biên dịch. Một switch exhaustive không có `default` có thể được biên dịch thành bytecode với nhánh dự phòng ném `MatchException` nếu khi chạy xuất hiện subtype mà bản biên dịch chưa biết.

Tình huống này có thể xảy ra khi thư viện định nghĩa sealed hierarchy được cập nhật độc lập với ứng dụng sử dụng nó. Sau khi thư viện thêm một permitted subtype, ứng dụng cần được biên dịch và kiểm tra lại để xử lý subtype mới. Nhánh dự phòng của compiler giúp chương trình thất bại rõ ràng thay vì tiếp tục với một trường hợp không được xử lý.

Với API sealed thuộc quyền kiểm soát của ứng dụng, nên biên dịch lại các module phụ thuộc sau khi thay đổi danh sách `permits`. Nếu cần một fallback nghiệp vụ ổn định khi kiểu mới xuất hiện, có thể thêm `default`, nhưng điều đó làm compiler không còn buộc người viết liệt kê từng subtype mới.

`MatchException` là tình huống khác với `NullPointerException`: trường hợp đầu biểu thị switch được xem là exhaustive khi biên dịch nhưng không có nhánh phù hợp lúc chạy; trường hợp sau thường xảy ra khi selector là null mà không có `case null`.

## 11. Checklist thiết kế switch exhaustive

Khi viết switch expression có record pattern, hãy kiểm tra:

1. Selector có phải sealed hierarchy hoặc record type mà compiler có thể xác định các trường hợp cần bao phủ không?
2. Với sealed hierarchy, mọi permitted subtype có nhánh tương ứng chưa?
3. Với mỗi record pattern, các component pattern có bao phủ mọi giá trị của component tương ứng không?
4. Nested record pattern có thể thất bại khi component là null hoặc có subtype khác không?
5. Các pattern có guard `when` đã có nhánh không guard hoặc fallback cho trường hợp guard trả về false chưa?
6. Với generic record, selector có giữ đủ thông tin type argument để compiler suy luận kiểu component không?
7. Có đang giả định type erasure cho phép kiểm tra `Box<String>` trực tiếp ở runtime không?
8. Selector null và component null đã được phân biệt và xử lý theo hợp đồng dữ liệu chưa?
9. Khi sealed hierarchy thay đổi, các module phụ thuộc có được biên dịch và kiểm tra lại không?

## Kết luận

Exhaustiveness của switch trong Java 21 phụ thuộc vào khả năng bao phủ toàn bộ các trường hợp của selector. Với sealed hierarchy, cần xử lý mọi permitted subtype; với record pattern, cần xét cả từng component và pattern lồng nhau. `var` pattern thường hữu ích khi cần một nhánh tổng quát bao phủ component, kể cả null. Với generic record, compiler suy luận kiểu component từ kiểu tĩnh của selector, trong khi type erasure giới hạn việc kiểm tra tham số generic ở runtime. Hãy phân biệt null ở selector với null trong component và bổ sung fallback phù hợp để switch vừa exhaustive vừa phản ánh đúng hợp đồng dữ liệu.

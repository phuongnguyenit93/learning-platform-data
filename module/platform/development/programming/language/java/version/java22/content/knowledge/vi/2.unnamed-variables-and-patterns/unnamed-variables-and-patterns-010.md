# Tính bao phủ, thứ tự nhánh và xử lý null khi kết hợp mẫu không tên với switch

Unnamed Variables & Patterns được chuẩn hóa trong Java 22 qua JEP 456. Khi kết hợp với pattern matching for `switch` đã chính thức từ Java 21, tính năng này giúp viết nhánh xử lý ngắn gọn mà vẫn thể hiện rõ loại dữ liệu hoặc thành phần nào cần được kiểm tra và thành phần nào được bỏ qua.

Để dùng đúng, cần phân biệt ba vấn đề: **tính bao phủ** xác định switch đã xử lý hết những trường hợp cần thiết hay chưa; **thứ tự nhánh** quyết định nhánh nào được chọn khi nhiều pattern có thể khớp; và **null** có quy tắc riêng, không tự động được xử lý bởi `default`.

## 1. Hai cách dùng dấu gạch dưới trong pattern

Trong ngôn ngữ Java, `_` là từ khóa dành riêng. Nó không tạo ra một biến có thể được tham chiếu trong thân nhánh.

Có hai cách dùng cần phân biệt:

| Cú pháp | Ý nghĩa |
|---|---|
| `case String _` | Type pattern kiểm tra giá trị là `String`, nhưng khai báo một **unnamed pattern variable** vì không cần dùng biến. |
| `case Point(int x, _)` | Record pattern lấy thành phần `x` và dùng **unnamed pattern** `_` để bỏ qua thành phần còn lại. |

Ví dụ đầu tiên không phải là một unnamed pattern độc lập: `_` thay cho tên biến trong type pattern. Unnamed pattern `_` chỉ xuất hiện ở vị trí thành phần của record pattern. Vì vậy, không thể viết `case _ -> ...` như một nhánh bắt mọi giá trị; hãy dùng `default` hoặc một pattern có kiểu phù hợp.

```java
record Point(int x, int y) {}

static String describe(Object value) {
    return switch (value) {
        case Point(int x, _) -> "Point có hoành độ " + x;
        case String _ -> "Một chuỗi";
        case null -> "Không có giá trị";
        default -> "Kiểu dữ liệu khác";
    };
}
```

Ở đây, `Point(int x, _)` chỉ khớp với một đối tượng `Point`; `x` được đưa vào biến để sử dụng, còn `y` không được đặt tên. `String _` kiểm tra kiểu của giá trị nhưng không tạo biến chuỗi để dùng trong nhánh.

## 2. Tính bao phủ của switch

Một switch được xem là exhaustive (đầy đủ nhánh) khi các nhãn `case` bao phủ các trường hợp mà kiểu của biểu thức selector có thể cung cấp. Đây là yêu cầu quan trọng của `switch` expression và của enhanced `switch` statement có pattern hoặc nhãn `null`.

Các cách phổ biến để tạo tính bao phủ:

- Dùng `default` để xử lý những giá trị không khớp các nhánh cụ thể.
- Liệt kê toàn bộ hằng enum khi selector là một kiểu enum.
- Với sealed class hoặc sealed interface, xử lý mọi kiểu con được phép bằng pattern tương ứng.
- Với record, dùng record pattern có các component pattern bao phủ kiểu của từng thành phần. `_` là lựa chọn hữu ích khi thành phần đó không cần được đọc.

Ví dụ sealed hierarchy:

```java
sealed interface PaymentResult permits Approved, Rejected {}

record Approved(String transactionId, long amount) implements PaymentResult {}
record Rejected(String code, String reason) implements PaymentResult {}

static String message(PaymentResult result) {
    return switch (result) {
        case Approved(String transactionId, _) -> "Đã duyệt: " + transactionId;
        case Rejected(String code, _) -> "Bị từ chối: " + code;
        case null -> "Chưa có kết quả";
    };
}
```

`PaymentResult` chỉ cho phép hai kiểu con là `Approved` và `Rejected`. Hai record pattern bao phủ hai kiểu đó; `_` bỏ qua `amount` và `reason`. Nhánh `null` xử lý trường hợp selector không tham chiếu tới đối tượng nào. Vì đã liệt kê đủ hai kiểu con và có nhánh null, switch expression không cần `default`.

Với một kiểu mở như `Object`, thường cần `default` để xử lý các kiểu không được liệt kê:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String _ -> "chuỗi";
        case Number _ -> "số";
        default -> "kiểu khác";
    };
}
```

Lưu ý rằng tính bao phủ khi biên dịch và xử lý null là hai câu hỏi riêng. Một nhánh `default` có thể làm switch exhaustive về mặt kiểu dữ liệu, nhưng nó không được chọn khi selector là `null`.

## 3. Thứ tự nhánh và quy tắc dominance

Khi selector khác null, Java xét các nhãn `case` theo thứ tự xuất hiện và chọn nhãn đầu tiên khớp pattern, đồng thời thỏa điều kiện `when` nếu có. Vì thế, thứ tự nhánh ảnh hưởng trực tiếp đến kết quả.

Compiler cũng kiểm tra **pattern dominance** (pattern đứng trước bao trùm pattern đứng sau). Nếu mọi giá trị khớp với pattern phía sau đều đã khớp với một pattern không có guard ở phía trước, nhánh sau không thể được chọn và chương trình bị lỗi biên dịch.

### Đặt kiểu cụ thể trước kiểu tổng quát

`String` là kiểu con của `CharSequence`. Nếu đặt `CharSequence _` trước `String _`, mọi chuỗi đã được nhánh đầu xử lý nên nhánh `String` trở thành unreachable:

```java
// Không biên dịch: CharSequence bao phủ String.
static String invalidOrder(Object value) {
    return switch (value) {
        case CharSequence _ -> "chuỗi ký tự";
        case String _ -> "String"; // Bị dominance
        default -> "khác";
    };
}
```

Thứ tự hợp lệ là đặt kiểu cụ thể trước:

```java
static String validOrder(Object value) {
    return switch (value) {
        case String _ -> "String";
        case CharSequence _ -> "kiểu chuỗi khác";
        case null -> "null";
        default -> "khác";
    };
}
```

Nhánh `String` nhận mọi chuỗi trước; nhánh `CharSequence` tiếp nhận những đối tượng triển khai interface này nhưng không phải `String`.

### Đặt hằng cụ thể trước type pattern bao phủ nó

Một type pattern không có guard có thể bao phủ cả nhánh hằng xuất hiện phía sau. Ví dụ, `Integer _` bao phủ giá trị `0`, do đó thứ tự sau không hợp lệ:

```java
// Không biên dịch: Integer _ bao phủ hằng 0.
static String invalidNumberOrder(Integer value) {
    return switch (value) {
        case Integer _ -> "số nguyên";
        case 0 -> "số không"; // Bị dominance
        case null -> "null";
    };
}
```

Hãy đặt hằng cụ thể trước pattern tổng quát:

```java
static String numberLabel(Integer value) {
    return switch (value) {
        case null -> "null";
        case 0 -> "số không";
        case Integer _ -> "số nguyên khác không";
    };
}
```

### Dùng guard để chia một kiểu thành nhiều trường hợp

Mệnh đề `when` bổ sung điều kiện cho pattern. Nếu pattern khớp nhưng guard trả về `false`, Java tiếp tục xét các nhánh sau. Vì vậy, có thể đặt trường hợp hẹp trước rồi dùng unnamed pattern làm nhánh tổng quát:

```java
static String describeText(String value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "chuỗi rỗng hoặc chỉ có khoảng trắng";
        case String _ -> "chuỗi có nội dung";
    };
}
```

Nhánh đầu tiên nhận chuỗi rỗng hoặc chỉ chứa khoảng trắng. Nếu `String` khớp nhưng guard sai, nhánh `String _` phía sau nhận các chuỗi còn lại. Nếu đặt `String _` lên trước, nhánh guard phía sau sẽ bị dominance vì nhánh tổng quát đã bao phủ mọi `String`.

Một guard là hằng `true` được xem như pattern không có guard khi xét dominance. Với guard phụ thuộc dữ liệu như `text.isBlank()`, compiler không thể chứng minh trước mọi giá trị mà guard sẽ nhận; do đó cần tự sắp xếp nhánh sao cho trường hợp cụ thể đứng trước.

## 4. `default` không xử lý selector null

Đây là quy tắc dễ gây lỗi nhất khi viết pattern switch. Nếu selector là `null`, Java tìm nhãn `case null`. Nếu không có nhãn đó, switch ném `NullPointerException`, kể cả khi đã có `default`.

```java
static String unsafe(Object value) {
    return switch (value) {
        case String _ -> "chuỗi";
        default -> "kiểu khác";
    };
}
```

`unsafe(null)` ném `NullPointerException`. `default` chỉ nhận các giá trị khác null không khớp nhãn nào phía trên.

Để xử lý null một cách tường minh, thêm `case null`:

```java
static String safe(Object value) {
    return switch (value) {
        case null -> "không có giá trị";
        case String _ -> "chuỗi";
        default -> "kiểu khác";
    };
}
```

Nếu null và mọi giá trị còn lại có cùng cách xử lý, có thể dùng nhãn kết hợp `case null, default`:

```java
static String fallback(Object value) {
    return switch (value) {
        case String _ -> "chuỗi";
        case null, default -> "không phải chuỗi hoặc null";
    };
}
```

Nhãn `case null, default` khớp mọi giá trị, bao gồm null, và phải đặt cuối switch. Không đặt thêm nhánh nào sau nhãn kết hợp này.

## 5. Null bên trong record pattern

Cần phân biệt selector null với một thành phần record có giá trị null:

- Một **record pattern ở cấp ngoài** không khớp khi chính đối tượng selector là null. Muốn xử lý trường hợp đó, cần `case null` hoặc `case null, default`.
- Unnamed pattern `_` trong danh sách thành phần record khớp mọi giá trị của thành phần tương ứng, bao gồm null.

Ví dụ:

```java
record Envelope(String payload) {}

static String inspect(Envelope envelope) {
    return switch (envelope) {
        case null -> "không có envelope";
        case Envelope(_) -> "có envelope";
    };
}
```

`new Envelope(null)` khớp `Envelope(_)`, bởi vì đối tượng `Envelope` tồn tại và `_` chấp nhận cả thành phần `payload` đang null. Nhưng nếu `envelope` chính là null, record pattern không khớp và nhánh `case null` được chọn.

Sự khác biệt này hữu ích khi một thành phần chỉ không liên quan tới phép xử lý hiện tại. Nếu cần phân biệt null với các giá trị khác, không nên bỏ qua thành phần bằng `_`; hãy đặt tên hoặc dùng pattern phù hợp để kiểm tra nó.

## 6. Quy tắc sắp xếp nhánh dễ áp dụng

Với pattern switch dùng arrow rules (`->`), có thể áp dụng trình tự sau:

1. Đặt `case null` sớm nếu null có hành vi riêng.
2. Đặt các hằng cụ thể trước type pattern có thể bao phủ chúng.
3. Đặt pattern của kiểu con trước pattern của kiểu cha hoặc interface tổng quát.
4. Đặt các pattern có guard `when` trước pattern không có guard của cùng phạm vi kiểu.
5. Đặt pattern tổng quát và `default` ở cuối; nếu dùng `case null, default`, nhãn này phải là nhãn cuối cùng.

Arrow rules không tự động rơi xuống nhánh tiếp theo như cách viết `case ...:` truyền thống. Mỗi nhánh arrow kết thúc độc lập, giúp tránh lỗi fall-through và làm thứ tự lựa chọn dễ đọc hơn.

## 7. Kiểm tra tính bao phủ khi thiết kế switch expression

Khi viết switch expression, hãy tự kiểm tra các câu hỏi sau:

| Câu hỏi | Cách xác minh |
|---|---|
| Đã bao phủ mọi kiểu con của sealed type chưa? | Liệt kê tất cả permitted direct subclasses/subinterfaces hoặc thêm `default`. |
| Record pattern có bao phủ mọi thành phần không? | Kiểm tra từng component; dùng `_` nếu thành phần không cần được sử dụng. |
| Có pattern tổng quát đứng trước pattern cụ thể không? | Kiểm tra quan hệ subtype và các pattern không có guard để tránh dominance. |
| Guard sai thì nhánh nào xử lý tiếp? | Đặt một pattern tổng quát phía sau guard để nhận các giá trị còn lại. |
| Selector null được xử lý thế nào? | Thêm `case null`, hoặc dùng `case null, default` nếu cùng fallback. |
| `default` có nằm cuối không? | Đưa `default` xuống cuối; không đặt nhánh pattern hoặc null sau nó. |

`switch` expression luôn phải exhaustive. Enhanced `switch` statement có pattern hoặc nhãn `null` cũng phải exhaustive. Dù compiler chấp nhận một switch có `default`, điều đó không có nghĩa là null đã được xử lý; hãy xem null như một trường hợp đầu vào riêng.

## 8. Kết luận

Unnamed variables và patterns giúp loại bỏ tên không cần thiết, còn pattern switch giúp biểu diễn nhiều nhánh xử lý theo kiểu dữ liệu và cấu trúc record. Khi kết hợp chúng, hãy nhớ:

- `String _` là type pattern có unnamed pattern variable; `_` trong `Point(int x, _)` là unnamed pattern ở vị trí component.
- Nhãn được xét theo thứ tự; pattern không guard ở trước có thể làm nhánh cụ thể phía sau bị dominance.
- Guard `when` cho phép chia một kiểu thành các trường hợp hẹp trước nhánh tổng quát.
- `default` không nhận selector null. Dùng `case null` hoặc `case null, default` khi cần xử lý null.
- Record pattern không khớp với selector null, nhưng unnamed component pattern `_` vẫn khớp thành phần record có giá trị null.

Các quy tắc này thuộc cú pháp Java hiện hành: pattern matching for `switch` đã chính thức từ Java 21, còn unnamed variables và patterns chính thức từ Java 22. Không cần bật preview để dùng các ví dụ trong bài.

## Tài liệu tham khảo

- [JEP 456 – Unnamed Variables & Patterns (Java 22)](https://openjdk.org/jeps/456)
- [JEP 441 – Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Pattern Matching with switch – Java SE 25 Language Guide](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html)
- [Java Language Specification, Java SE 25 – §14.11 switch statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11)
- [Java Language Specification, Java SE 25 – §14.30 patterns](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.30)

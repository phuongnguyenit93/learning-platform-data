# Phân biệt default, pattern bao phủ toàn bộ kiểu và xử lý null

Trong Java 21, `switch` có thể kiểm tra kiểu thực tế của một đối tượng bằng pattern. Khi viết switch expression hoặc enhanced switch statement, cần bảo đảm các nhãn `case` bao phủ miền giá trị mà compiler yêu cầu. Ba khái niệm dễ nhầm là `default`, pattern bao phủ toàn bộ kiểu (*unconditional pattern*) và nhãn `case null`.

`default` là nhánh dự phòng cho các giá trị chưa được nhãn trước xử lý. Một pattern unconditional có thể bao phủ mọi giá trị thuộc kiểu selector và còn cho phép đặt tên biến để sử dụng. Cả hai đều có thể giúp switch exhaustive theo kiểu, nhưng không tự xử lý selector `null`.

## 1. Khi nào switch phải exhaustive?

Một switch được xem là *exhaustive* khi các nhãn của nó bao phủ mọi giá trị mà kiểu selector có thể cung cấp theo quy tắc của Java. Đây là yêu cầu ở thời điểm biên dịch, giúp phát hiện nhánh còn thiếu trước khi chương trình chạy.

Trong Java 21:

- **Switch expression** luôn phải exhaustive vì nó phải tạo ra một giá trị hoặc kết thúc bằng exception ở mọi đường thực thi.
- **Enhanced switch statement** phải exhaustive. Một switch statement thuộc nhóm này nếu sử dụng pattern label hoặc `null` label, hoặc selector không thuộc nhóm kiểu switch truyền thống: `char`, `byte`, `short`, `int`, `Character`, `Byte`, `Short`, `Integer`, `String` và enum.
- **Traditional switch statement** chỉ dùng các nhãn hằng trên nhóm kiểu truyền thống vẫn có thể không có `default` và không cần liệt kê mọi giá trị. Quy tắc này được giữ để tương thích với mã Java cũ.

Ví dụ, switch expression với selector `Object` thiếu nhánh cho nhiều kiểu đối tượng nên không exhaustive:

```java
static int sizeOf(Object value) {
    return switch (value) { // Lỗi biên dịch: chưa exhaustive
        case String text -> text.length();
        case Integer number -> number;
    };
}
```

Switch statement có pattern label cũng phải exhaustive, dù phần thân chỉ thực hiện thao tác và không trả về giá trị:

```java
static void printValue(Object value) {
    switch (value) { // Lỗi biên dịch: enhanced switch statement chưa exhaustive
        case String text -> System.out.println(text);
        case Integer number -> System.out.println(number);
    }
}
```

Thêm nhánh `default` để bao phủ các kiểu còn lại:

```java
static void printValue(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        case Integer number -> System.out.println(number);
        default -> System.out.println("Kiểu khác");
    }
}
```

## 2. `default` và pattern bao phủ toàn bộ kiểu

Compiler kiểm tra *type coverage* (độ bao phủ kiểu) của các nhãn `case`. Với một selector kiểu tham chiếu, hai cách viết sau thường được dùng để bao phủ mọi giá trị khác `null`:

```java
static String withDefault(Object value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        default -> "Giá trị thuộc kiểu khác";
    };
}

static String withTotalPattern(Object value) {
    return switch (value) {
        case Object object -> "Giá trị: " + object;
    };
}
```

`default` có độ bao phủ kiểu là tất cả các kiểu. Nó nhận những giá trị chưa được các nhãn trước xử lý và không khai báo biến pattern. Pattern `Object object` là *unconditional* đối với selector có kiểu tĩnh `Object`: mọi giá trị không null thuộc kiểu đó đều phù hợp với pattern, và biến `object` được gán giá trị đã khớp.

Hai cách viết khác nhau ở mục đích sử dụng:

| Nhãn | Ý nghĩa | Có biến pattern? | Có xử lý selector null? |
|---|---|---|---|
| `default -> ...` | Nhánh dự phòng cho mọi giá trị chưa khớp trước đó | Không | Không |
| `case Object object -> ...` với selector `Object` | Pattern unconditional cho kiểu `Object` | Có | Không |
| `case String text -> ...` với selector `Object` | Chỉ khớp các giá trị là `String` | Có | Không |
| `case null -> ...` | Khớp riêng giá trị null | Không | Có |
| `case null, default -> ...` | Gộp null và các giá trị còn lại | Không | Có |

Pattern unconditional phụ thuộc vào kiểu selector. Chẳng hạn, `case CharSequence chars` là unconditional nếu selector có kiểu `CharSequence`, nhưng chỉ bao phủ một phần nếu selector có kiểu `Object`. Tương tự, `case String text` không bao phủ toàn bộ `Object`.

Một pattern có guard không tự động bao phủ toàn bộ kiểu. Ví dụ `case String text when text.isBlank()` chỉ nhận chuỗi thỏa điều kiện. Khi cần xử lý tất cả chuỗi, thêm pattern `case String text` không guard hoặc một nhánh dự phòng thích hợp.

## 3. Type coverage từ enum và sealed hierarchy

Không phải switch nào cũng cần `default`. Compiler có thể chứng minh tính exhaustive từ danh sách enum constants hoặc các kiểu con được phép của một sealed type.

### Enum: liệt kê đủ các constant

Với switch expression, có thể bỏ `default` nếu đã liệt kê mọi enum constant:

```java
enum OrderStatus {
    NEW, PROCESSING, COMPLETED
}

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Mới tạo";
        case PROCESSING -> "Đang xử lý";
        case COMPLETED -> "Hoàn tất";
    };
}
```

Compiler biết ba constant trên là toàn bộ giá trị enum được khai báo tại thời điểm biên dịch, nên switch expression exhaustive. Nếu thêm constant mới rồi biên dịch lại mã này, compiler sẽ yêu cầu xử lý constant mới hoặc thêm `default`.

Việc liệt kê đủ enum constants không xử lý giá trị selector null. Nếu `status` có thể null, cần thêm `case null`; nếu không, switch vẫn ném `NullPointerException` khi nhận null.

Với enum selector, switch statement truyền thống chỉ dùng các constant label vẫn có thể không liệt kê hết constant và không có `default`. Nếu switch statement dùng `case null` hoặc pattern label, nó trở thành enhanced switch statement và phải exhaustive.

### Sealed type: bao phủ các permitted subtype

Với sealed class hoặc sealed interface, compiler biết tập kiểu con được phép. Nếu các nhánh bao phủ toàn bộ tập đó, switch expression không cần `default`:

```java
sealed interface PaymentResult permits Paid, Rejected {}

record Paid(String transactionId) implements PaymentResult {}
record Rejected(String reason) implements PaymentResult {}

static String describe(PaymentResult result) {
    return switch (result) {
        case Paid paid -> "Đã thanh toán: " + paid.transactionId();
        case Rejected rejected -> "Bị từ chối: " + rejected.reason();
    };
}
```

`Paid` và `Rejected` là toàn bộ các kiểu con được khai báo trong `permits`, vì vậy hai pattern bao phủ miền kiểu `PaymentResult`. Nếu một permitted subtype khác là sealed, compiler có thể xét tiếp các kiểu con được phép của nó. Nếu một subtype là `non-sealed`, pattern cho subtype đó có thể bao phủ cả các lớp con tương lai của nó.

Ví dụ trên exhaustive theo miền kiểu `PaymentResult`; nếu `result` là null, switch vẫn ném `NullPointerException` vì chưa có `case null`.

Compiler cũng xét tham số kiểu của generic sealed hierarchy. Một permitted subtype có thể không tương thích với cách tham số hóa cụ thể của selector, nên không phải lúc nào cũng cần một nhánh cho mọi subtype được liệt kê trong `permits`.

## 4. Nhãn `default` không thay thế `case null`

Với selector kiểu tham chiếu, `null` được xử lý riêng. Nếu selector là `null` và switch không có nhãn `case null`, Java ném `NullPointerException`. Điều này vẫn đúng khi switch có `default` hoặc một pattern unconditional như `case Object object`.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        default -> "Giá trị khác";
    };
}
```

Đoạn code trên exhaustive theo kiểu vì có `default`, nhưng gọi `describe(null)` vẫn ném `NullPointerException`. Để xử lý null, thêm nhãn riêng:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text -> "Chuỗi: " + text;
        default -> "Giá trị khác";
    };
}
```

Nếu muốn gộp null với mọi giá trị chưa khớp, Java 21 cho phép `case null, default`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        case null, default -> "Null hoặc kiểu khác";
    };
}
```

Trong Java 21, nhãn `null` chỉ có thể kết hợp với `default`, không kết hợp trực tiếp với một pattern khác. Nhãn `case null, default` là nhánh dự phòng cuối cùng. Nếu cần xử lý null riêng, đặt `case null` thành nhánh riêng và dùng `default` cho các giá trị còn lại.

## 5. Record pattern và null ở component lồng nhau

Tính exhaustive theo kiểu không có nghĩa mọi cấu trúc dữ liệu runtime đều khớp với nested record pattern. Một record pattern có thể được xem là unconditional cho kiểu record bên ngoài, dù nested record pattern bên trong không khớp khi component tương ứng là `null`.

```java
record Detail(String text) {}
record Envelope(Detail detail) {}

static String extract(Envelope envelope) {
    return switch (envelope) {
        case null -> "Không có Envelope";
        case Envelope(Detail(var text)) -> String.valueOf(text);
    };
}
```

Switch trên được xem là exhaustive theo kiểu `Envelope`. Tuy nhiên:

- `extract(null)` khớp `case null`.
- `extract(new Envelope(new Detail(null)))` khớp nested pattern; `var text` nhận `null`.
- `extract(new Envelope(null))` không khớp nested pattern `Detail(...)` và có thể ném `MatchException` vì compiler đã xem switch là exhaustive.

Nếu component `detail` có thể null theo nghiệp vụ, hãy bắt component ở tầng ngoài và xử lý null rõ ràng trước khi phân rã tiếp:

```java
static String extractSafely(Envelope envelope) {
    return switch (envelope) {
        case null -> "Không có Envelope";
        case Envelope(var detail) when detail == null -> "Chưa có Detail";
        case Envelope(Detail(var text)) ->
                String.valueOf(text);
    };
}
```

Guard `when detail == null` xử lý trường hợp component null. Nhánh nested record pattern còn lại xử lý `Detail` đã tồn tại. Cách viết này giúp tránh việc giả định rằng pattern bao phủ toàn bộ kiểu đồng nghĩa với mọi component lồng nhau đều khác null.

## 6. Khi nào MatchException có thể xuất hiện?

`MatchException` là runtime exception được bổ sung trong Java 21 để báo hiệu quá trình pattern matching thất bại ngoài dự kiến. Một số trường hợp quan trọng:

1. **Sealed hierarchy thay đổi sau khi biên dịch:** switch được biên dịch khi sealed type chỉ có các subtype A và B; sau đó thư viện được biên dịch lại với subtype C nhưng class chứa switch không được biên dịch lại. Giá trị C có thể không khớp nhánh nào và dẫn đến `MatchException`.
2. **Enum thay đổi sau separate compilation:** enum runtime có thêm constant mà mã switch đã biên dịch chưa biết đến. Nếu không có nhánh fallback phù hợp, switch exhaustive lúc biên dịch có thể ném `MatchException`.
3. **Nested pattern gặp component null:** các nested record pattern có thể được xem là bao phủ toàn bộ kiểu bên ngoài, nhưng không khớp nếu một component record cần phân rã lại là null.
4. **Record accessor ném exception:** record pattern gọi accessor để lấy component. Nếu accessor tùy biến ném exception, quá trình khớp pattern kết thúc bất thường và được bọc trong `MatchException`.

Phân biệt hai trường hợp null: selector bên ngoài là null mà không có `case null` sẽ ném `NullPointerException`; component lồng nhau là null khiến nested record pattern không khớp trong một switch đã được xem là exhaustive có thể dẫn đến `MatchException`.

Khi thay đổi sealed hierarchy hoặc enum trong các module được biên dịch riêng, hãy biên dịch lại những module chứa switch phụ thuộc vào hierarchy đó.

## 7. Guard, dominance và thứ tự nhãn

Các nhãn `case` được xét theo thứ tự. Compiler báo lỗi nếu một nhãn không thể được chọn vì nhãn trước đã bao phủ mọi giá trị của nó (*dominance*).

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String";
        case CharSequence chars -> "CharSequence khác String";
        default -> "Kiểu khác";
    };
}
```

Thứ tự trên hợp lệ vì `String` hẹp hơn `CharSequence`. Nếu đặt `CharSequence` trước `String`, nhánh `String` bị dominate vì mọi `String` đều là `CharSequence`.

Guard giúp chia một kiểu thành các trường hợp nhỏ hơn:

```java
static String classify(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Chuỗi trống";
        case String text -> "Chuỗi có nội dung";
        default -> "Không phải chuỗi";
    };
}
```

Pattern có guard tùy ý không được xem là bao phủ toàn bộ kiểu khi kiểm tra exhaustive. Vì vậy, nhánh có guard thường đi trước nhánh không guard cùng kiểu; nhánh không guard đảm nhận phần giá trị còn lại.

## 8. Checklist chọn nhãn phù hợp

- [ ] Switch expression đã exhaustive.
- [ ] Enhanced switch statement (có pattern/null label hoặc selector ngoài nhóm legacy) đã exhaustive.
- [ ] Đã xác định `default` có phù hợp hay có thể liệt kê đầy đủ enum constants hoặc permitted subtype.
- [ ] Nếu dùng pattern unconditional, pattern thực sự bao phủ kiểu tĩnh của selector.
- [ ] Không nhầm `case Object object` với `case null`; pattern này không khớp null.
- [ ] Đã thêm `case null` nếu selector reference có thể null và cần xử lý rõ ràng.
- [ ] Đã kiểm tra các component nullable trước khi dùng nested record pattern.
- [ ] Không dùng guard tùy ý như bằng chứng bao phủ toàn bộ kiểu.
- [ ] Pattern cụ thể đứng trước pattern tổng quát để tránh dominance.
- [ ] Đã biên dịch lại module phụ thuộc khi sealed hierarchy hoặc enum thay đổi.

## Tài liệu tham khảo

- [Pattern Matching for switch Expressions and Statements — Java SE 21](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): type coverage, sealed hierarchy, guard, dominance, null label và `MatchException` khi switch exhaustive không khớp lúc runtime.
- [Switch Expressions and Statements — Java SE 21](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): yêu cầu exhaustive của switch expression và enhanced switch statement; ngoại lệ cho traditional switch statement.
- [Java Language Specification, Java SE 21 — §14.11 Switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): exhaustive switch block, type coverage và quy tắc thực thi switch.
- [MatchException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): các trường hợp runtime có thể phát sinh `MatchException`, bao gồm hierarchy thay đổi, nested pattern gặp null và accessor ném exception.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế và phạm vi tính năng Pattern Matching for `switch` được hoàn thiện trong Java 21.

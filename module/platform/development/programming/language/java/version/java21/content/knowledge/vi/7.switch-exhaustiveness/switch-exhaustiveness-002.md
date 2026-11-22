# Phân biệt yêu cầu exhaustive của switch statement và expression

Trong Java 21, mọi `switch expression` đều phải exhaustive (bao phủ đầy đủ các trường hợp theo quy tắc của ngôn ngữ). `switch statement` chỉ bắt buộc exhaustive khi nó là *enhanced switch statement* — chẳng hạn dùng pattern, dùng nhãn `case null`, hoặc có selector thuộc nhóm kiểu không nằm trong tập kiểu switch truyền thống.

Sự khác biệt này quan trọng khi đọc code cũ, thiết kế pattern switch mới và quyết định có cần `default` hay không. Bài này tập trung vào quy tắc Java 21 đã chính thức hóa; Record Patterns và Pattern Matching for `switch` trong Java 21 không cần bật preview feature.

## 1. Exhaustive nghĩa là gì?

Một switch block exhaustive khi các nhãn `case` của nó bao phủ kiểu selector theo quy tắc của Java. Nói đơn giản, với một giá trị đầu vào hợp lệ, switch có một nhãn có thể áp dụng.

Compiler kiểm tra tính exhaustive tại thời điểm biên dịch. Việc kiểm tra dựa trên kiểu selector và các nhãn `case`, không phải dựa trên việc chương trình đã thử mọi giá trị thực tế.

Một switch có thể đạt tính exhaustive theo nhiều cách:

- Có nhãn `default`, bao phủ mọi giá trị khác `null`.
- Có nhãn `case null, default`, bao phủ cả `null` và mọi giá trị còn lại.
- Liệt kê tất cả enum constant của kiểu selector.
- Liệt kê tất cả permitted subtype của một sealed class/interface.
- Dùng pattern có type coverage phù hợp; với record pattern, compiler có thể phân tích các component pattern để xác định độ bao phủ.

Lưu ý: `default` đơn lẻ không khớp với `null`. Nếu selector là `null` và không có `case null`, switch vẫn ném `NullPointerException`, kể cả khi compiler đã chấp nhận switch là exhaustive.

## 2. Switch expression luôn phải exhaustive

`switch expression` tạo ra một giá trị, vì vậy compiler phải bảo đảm rằng mọi luồng lựa chọn đều có thể tạo ra kết quả hoặc kết thúc bằng exception. Nếu thiếu nhánh bao phủ, code không biên dịch.

Ví dụ với enum:

~~~java
enum OrderStatus {
    NEW, CONFIRMED, CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case NEW       -> "Mới tạo";
        case CONFIRMED -> "Đã xác nhận";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Không cần `default` vì ba nhãn đã bao phủ tất cả constant của `OrderStatus` tại thời điểm biên dịch.

Nếu bỏ một constant, chẳng hạn `CANCELLED`, compiler báo switch expression không exhaustive. Một cách khác để hoàn tất switch là thêm `default`:

~~~java
static String label(OrderStatus status) {
    return switch (status) {
        case NEW       -> "Mới tạo";
        case CONFIRMED -> "Đã xác nhận";
        default        -> "Trạng thái khác";
    };
}
~~~

Với `default`, mọi giá trị khác `null` đều có nhánh xử lý. Nếu `status` có thể là `null`, hãy thêm nhánh riêng:

~~~java
static String label(OrderStatus status) {
    return switch (status) {
        case null      -> "Chưa có trạng thái";
        case NEW       -> "Mới tạo";
        case CONFIRMED -> "Đã xác nhận";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Một `switch expression` cũng có thể dùng `case null, default` khi muốn gom `null` và mọi giá trị khác vào cùng một nhánh:

~~~java
String description = switch (status) {
    case NEW -> "Mới";
    case null, default -> "Chưa xác định hoặc không có trạng thái";
};
~~~

## 3. Switch statement chỉ exhaustive trong một số trường hợp

Java 21 phân biệt *enhanced switch statement* với switch statement không enhanced.

Một switch statement là enhanced nếu thỏa ít nhất một điều kiện:

1. Kiểu selector không thuộc tập `char`, `byte`, `short`, `int`, `Character`, `Byte`, `Short`, `Integer`, `String` hoặc một kiểu enum.
2. Switch block có nhãn `case` pattern.
3. Switch block có nhãn `case null`.

Enhanced switch statement phải exhaustive. Nếu thiếu độ bao phủ, compiler báo lỗi.

### Switch statement dùng pattern

Ví dụ sau không exhaustive vì selector có kiểu `Object`, nhưng chỉ xử lý `String` và `Integer`:

~~~java
static void printValue(Object value) {
    switch (value) {
        case String s  -> System.out.println("Chuỗi: " + s);
        case Integer i -> System.out.println("Số nguyên: " + i);
    }
}
~~~

Compiler báo lỗi vì `Object` còn có thể chứa các kiểu khác. Bổ sung `default` để hoàn tất:

~~~java
static void printValue(Object value) {
    switch (value) {
        case String s  -> System.out.println("Chuỗi: " + s);
        case Integer i -> System.out.println("Số nguyên: " + i);
        default        -> System.out.println("Kiểu dữ liệu khác");
    }
}
~~~

### Switch statement dùng sealed hierarchy

Khi selector là sealed interface, compiler có thể xác định tập subtype được phép. Nếu các nhánh pattern bao phủ tất cả subtype, switch statement exhaustive mà không cần `default`:

~~~java
sealed interface Payment permits Cash, Card {}

record Cash(int amount) implements Payment {}
record Card(String lastFour) implements Payment {}

static void printPayment(Payment payment) {
    switch (payment) {
        case Cash cash -> System.out.println("Tiền mặt: " + cash.amount());
        case Card card -> System.out.println("Thẻ: " + card.lastFour());
    }
}
~~~

Nếu bổ sung một permitted subtype mới, chẳng hạn `BankTransfer`, rồi biên dịch lại class chứa switch, compiler sẽ yêu cầu bổ sung nhánh để tiếp tục exhaustive hoặc thêm `default`.

### Switch statement có selector kiểu truyền thống và chỉ dùng constant labels

Với selector thuộc nhóm kiểu truyền thống (`char`, `byte`, `short`, `int`, các wrapper tương ứng, `String`, enum) và chỉ dùng constant labels, switch statement không bắt buộc exhaustive. Đây là quy tắc tương thích của Java; arrow rule (`->`) tự nó không làm switch trở thành enhanced.

Ví dụ enum statement sau vẫn biên dịch dù thiếu `CANCELLED`:

~~~java
enum OrderStatus {
    NEW, CONFIRMED, CANCELLED
}

static void logStatus(OrderStatus status) {
    switch (status) {
        case NEW       -> System.out.println("Mới tạo");
        case CONFIRMED -> System.out.println("Đã xác nhận");
    }
}
~~~

Nếu `status` là `CANCELLED`, không có nhãn nào áp dụng và switch statement kết thúc bình thường mà không chạy nhánh nào. Đây là khác biệt quan trọng so với switch expression: statement có thể không làm gì khi không có nhãn khớp, còn expression phải tạo ra giá trị hoặc ném exception.

Nếu thêm `case null` vào switch statement này, nó trở thành enhanced switch và phải exhaustive đối với các giá trị còn lại. Chỉ thêm `case null` không làm các enum constant bị bỏ sót tự động được bao phủ.

## 4. Bảng so sánh hai loại switch

| Trường hợp | Có bắt buộc exhaustive khi biên dịch? | Khi không có nhãn áp dụng ở runtime |
|---|---|---|
| Mọi `switch expression` | Có | Giá trị khác `null`: `MatchException`; `null` không có `case null`: `NullPointerException` |
| Enhanced `switch statement` | Có | Giá trị khác `null`: `MatchException`; `null` không có `case null`: `NullPointerException` |
| Switch statement với selector truyền thống và chỉ constant labels | Không | Giá trị khác `null`: statement kết thúc bình thường; `null`: `NullPointerException` |
| Switch statement có `case null` hoặc pattern | Có, vì trở thành enhanced | Như enhanced switch statement |

Không nên xác định loại switch chỉ bằng cú pháp `case ... ->` hay `case ...:`. Cần xét kiểu selector và loại nhãn được dùng.

## 5. Enum: vì sao expression và statement có thể khác nhau?

Với enum, switch expression có thể exhaustive khi liệt kê tất cả constant đã biết:

~~~java
enum Priority {
    LOW, NORMAL, HIGH
}

static int weight(Priority priority) {
    return switch (priority) {
        case LOW    -> 1;
        case NORMAL -> 2;
        case HIGH   -> 3;
    };
}
~~~

Compiler không yêu cầu `default` trong ví dụ này. Để bảo vệ trường hợp enum được nâng cấp độc lập sau khi consumer đã biên dịch, compiler tạo nhánh mặc định tổng hợp cho switch expression. Nếu một constant mới xuất hiện lúc chạy mà bytecode cũ chưa có nhãn tương ứng, Java ném `MatchException`.

Một switch statement dùng các enum constant thông thường không có yêu cầu exhaustive tương tự. Nếu một constant mới xuất hiện và không có nhãn phù hợp trong bytecode cũ, statement có thể kết thúc bình thường mà không chạy nhánh nào.

Nếu switch statement trên enum có pattern hoặc `case null`, nó trở thành enhanced switch statement và phải exhaustive. Khi enum được mở rộng sau khi biên dịch, enhanced switch cũ có thể ném `MatchException` nếu không tìm được nhãn áp dụng.

Khi thay đổi enum được dùng trong switch, hãy biên dịch lại các module consumer liên quan và triển khai các artifact tương thích cùng nhau.

## 6. Guarded pattern không tự tạo ra độ bao phủ đầy đủ

Một pattern có `when` là guarded pattern. Để xác định tính exhaustive, Java dựa trên các case element trong nhãn không guard. Vì vậy, một nhánh chỉ xử lý một phần giá trị của kiểu pattern không đủ để bao phủ toàn bộ kiểu đó.

Ví dụ với selector `Object`:

~~~java
static void describe(Object value) {
    switch (value) {
        case String s when !s.isBlank() ->
            System.out.println("Chuỗi có nội dung");
        case Integer i ->
            System.out.println("Số nguyên");
        default ->
            System.out.println("Giá trị khác hoặc chuỗi rỗng");
    }
}
~~~

`default` bảo đảm các trường hợp không được hai nhánh đầu xử lý vẫn có nhãn áp dụng. Nếu muốn xử lý các chuỗi rỗng bằng một nhánh riêng, có thể thêm pattern `String` không guard sau nhánh có guard:

~~~java
static void describe(Object value) {
    switch (value) {
        case String s when !s.isBlank() ->
            System.out.println("Chuỗi có nội dung");
        case String s ->
            System.out.println("Chuỗi rỗng hoặc chỉ có khoảng trắng");
        case Integer i ->
            System.out.println("Số nguyên");
        default ->
            System.out.println("Kiểu dữ liệu khác");
    }
}
~~~

Nhánh không guard `case String s` bao phủ những chuỗi không được nhánh guard đầu tiên xử lý. Cách viết này giúp thể hiện rõ cả điều kiện ưu tiên và nhánh bao phủ tổng quát.

## 7. Record pattern và sealed hierarchy

Compiler có thể phân tích độ bao phủ của record pattern, kể cả khi các pattern được lồng nhau. Tuy nhiên, không thể kết luận exhaustive chỉ bằng cách nhìn thấy mọi subtype xuất hiện đâu đó trong switch; tổ hợp component pattern phải bao phủ mọi cấu trúc giá trị thuộc record selector.

Ví dụ này exhaustive vì component `Shape` được chia thành đầy đủ hai subtype được phép:

~~~java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

record Drawing(Shape shape) {}

static String describe(Drawing drawing) {
    return switch (drawing) {
        case Drawing(Circle c) ->
            "Hình tròn bán kính " + c.radius();
        case Drawing(Rectangle r) ->
            "Hình chữ nhật " + r.width() + " x " + r.height();
    };
}
~~~

Nếu một record có nhiều component, cần bao phủ các tổ hợp giá trị có thể có. Ví dụ, hai pattern chỉ xử lý `Pair(A, A)` và `Pair(B, B)` không bao phủ `Pair(A, B)` hoặc `Pair(B, A)`. Compiler kiểm tra độ bao phủ theo quy tắc type coverage, không chỉ đếm số subtype được nhắc đến.

Với dữ liệu có thể chứa `null` trong component lồng nhau, hãy kiểm tra chính sách null riêng. Tính exhaustive theo type coverage không đồng nghĩa switch đã xử lý mọi giá trị `null`.

## 8. Default, null và lựa chọn thiết kế

Có hai quyết định thiết kế thường gặp:

- **Liệt kê toàn bộ enum hoặc sealed subtype, không thêm `default`:** phù hợp khi muốn compiler báo lỗi nếu mô hình miền thay đổi. Cách này giúp các module phụ thuộc được cập nhật khi thêm subtype hoặc enum constant.
- **Thêm `default`:** phù hợp khi ứng dụng phải tiếp nhận giá trị mới hoặc chưa biết, ví dụ dữ liệu đến từ plugin, message broker hoặc thư viện được nâng cấp độc lập. Hãy chọn hành vi fallback có ý nghĩa như ghi log, trả trạng thái chưa hỗ trợ hoặc ném exception nghiệp vụ.

Nếu `null` là đầu vào hợp lệ, thêm `case null` rõ ràng. Nếu muốn gom null vào fallback, dùng `case null, default`. Đừng kỳ vọng `default` đơn lẻ sẽ xử lý null.

Không nên thêm `default` một cách máy móc vào mọi switch trên sealed hierarchy hoặc enum. Một fallback tổng quát có thể khiến compiler không còn cảnh báo khi một subtype mới cần được xử lý theo nghiệp vụ riêng.

## 9. MatchException khi exhaustive ở compile time nhưng không còn exhaustive lúc chạy

Compiler kiểm tra switch dựa trên các kiểu và subtype nhìn thấy tại thời điểm biên dịch. Nếu sealed hierarchy hoặc enum thay đổi sau đó nhưng class chứa switch vẫn là bytecode cũ, giá trị mới có thể không khớp nhãn nào.

Ví dụ, consumer được biên dịch khi `Payment` chỉ có `Cash` và `Card`. Sau đó thư viện thêm `BankTransfer` và chỉ thư viện được biên dịch lại. Nếu consumer cũ nhận một `BankTransfer`, switch exhaustive có thể ném `MatchException`.

Điều này có thể xảy ra với:

- `switch expression` đã exhaustive theo enum hoặc sealed hierarchy.
- Enhanced `switch statement` đã exhaustive theo sealed hierarchy hoặc enum.
- Pattern switch có record pattern và cấu trúc type coverage đã thay đổi giữa compile time và runtime.

Cách khắc phục là biên dịch lại class chứa switch theo hierarchy mới và triển khai các artifact tương thích. Nếu phải duy trì khả năng chạy cùng phiên bản thư viện mới, thiết kế `default` để xử lý giá trị chưa biết một cách có chủ đích.

Cần phân biệt lỗi này với `NullPointerException`: selector là `null` mà không có `case null` sẽ ném `NullPointerException`, kể cả khi switch exhaustive về mặt type coverage.

## 10. Checklist khi thiết kế hoặc review switch

- [ ] Xác định đây là switch expression hay switch statement.
- [ ] Với switch statement, xác định nó có phải enhanced switch hay không.
- [ ] Kiểm tra toàn bộ enum constant hoặc permitted subtype đã được bao phủ khi không dùng `default`.
- [ ] Không dùng guarded pattern làm nhánh bao phủ duy nhất cho một kiểu.
- [ ] Quyết định rõ `null` có được chấp nhận hay phải bị từ chối.
- [ ] Dùng `default` khi cần fallback cho giá trị chưa biết; bỏ `default` khi muốn compiler buộc xử lý từng subtype đã biết.
- [ ] Khi enum hoặc sealed hierarchy thay đổi, build lại consumer và kiểm thử với các artifact sẽ triển khai.
- [ ] Kiểm tra các nhánh có thể kết thúc bằng giá trị hoặc exception theo đúng loại switch.

## Tài liệu tham khảo chính thức

- [Java Language Specification 21 — 14.11.1.1 Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java Language Specification 21 — 14.11.2 The Switch Block of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Java Language Specification 21 — 14.11.3 Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3)
- [Java Language Specification 21 — 15.28.1 The Switch Block of a switch Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.1)
- [Java Language Specification 21 — 15.28.2 Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2)
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441)


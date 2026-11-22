# Type coverage và điều kiện exhaustive của switch có pattern

Trong Java 21, một switch có pattern phải được kiểm tra để bảo đảm mọi giá trị thuộc phạm vi kiểu của selector đều có nhánh xử lý. Trình biên dịch thực hiện việc này bằng khái niệm **type coverage**: xác định những kiểu nào đã được các nhãn case bao phủ, rồi so sánh với kiểu tĩnh của biểu thức selector.

Pattern matching for switch là tính năng ngôn ngữ chuẩn từ Java 21, không cần bật preview flag khi biên dịch với release 21.

Quy tắc này đặc biệt hữu ích với sealed hierarchy. Khi một sealed type có tập kiểu con được khai báo hữu hạn, trình biên dịch có thể xác nhận switch đã xử lý tất cả nhánh. Với kiểu mở, hoặc khi pattern chỉ khớp một phần giá trị, cần bổ sung nhánh bao quát như default.

## 1. Exhaustive switch là gì?

Một switch được xem là exhaustive (đầy đủ) khi các nhãn của nó bao phủ mọi trường hợp mà quy tắc ngôn ngữ yêu cầu đối với kiểu selector. Đây là kiểm tra tĩnh tại thời điểm biên dịch, giúp tránh trường hợp một giá trị hợp lệ đi vào switch nhưng không có nhánh phù hợp.

Java 21 yêu cầu:

- **Switch expression** phải exhaustive vì biểu thức phải tạo ra một giá trị cho mọi trường hợp được phép.
- **Switch statement có sử dụng pattern label** cũng phải exhaustive.
- **Switch statement kiểu truyền thống** chỉ dùng các hằng số như số nguyên hoặc enum vẫn có thể không exhaustive; nếu không có nhãn phù hợp, statement đơn giản là không thực hiện nhánh nào.

Ví dụ một switch expression không đầy đủ:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
    };
}
~~~

Selector có kiểu Object, nên nó có thể chứa một đối tượng không phải String. Chỉ có pattern String không bao phủ mọi giá trị của Object; trình biên dịch báo lỗi vì switch expression chưa exhaustive.

Có thể hoàn thiện bằng default:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
        default -> "another type";
    };
}
~~~

## 2. Type coverage của case label

Type coverage mô tả tập kiểu mà một nhãn case có thể bao phủ. Khi xác định switch có exhaustive hay không, trình biên dịch xét kiểu tĩnh của selector và coverage của toàn bộ nhãn.

| Dạng nhãn | Coverage và ý nghĩa |
|---|---|
| case String text | Bao phủ các giá trị không null có kiểu String hoặc kiểu con phù hợp |
| case Object object | Bao phủ mọi giá trị không null thuộc Object |
| case Point(var x, var y) | Bao phủ mọi Point vì các component pattern var đều khớp mọi giá trị component |
| case Point(0, var y) | Chỉ khớp Point có component x bằng 0; không bao phủ toàn bộ kiểu Point |
| case String text when !text.isBlank() | Chỉ khớp chuỗi thỏa điều kiện guard; không thể dùng để chứng minh đã bao phủ mọi String |
| default | Bao phủ các trường hợp kiểu còn lại; không bao gồm null |
| case null | Xử lý riêng giá trị null, không bổ sung type coverage cho các kiểu tham chiếu |

Type pattern T t bao phủ các giá trị không null có kiểu tương thích với T, kể cả đối tượng thuộc lớp con của T. Vì vậy, nếu selector có kiểu Object, case String text chỉ bao phủ phần giá trị là chuỗi; các kiểu khác vẫn cần nhánh.

### Record pattern có thể bao phủ toàn bộ kiểu record

Một record pattern chỉ bao phủ toàn bộ kiểu record khi các component pattern bên trong cũng bao phủ toàn bộ giá trị có thể có của component tương ứng.

~~~java
record Point(int x, int y) {}

static String describe(Point point) {
    return switch (point) {
        case Point(var x, var y) -> x + ", " + y;
    };
}
~~~

var pattern khớp mọi giá trị của component, nên Point(var x, var y) bao phủ toàn bộ Point.

Ngược lại, pattern sau chỉ khớp một phần các đối tượng:

~~~java
case Point(0, var y) -> "on the y-axis";
~~~

Những Point có x khác 0 không khớp nhãn này. Nếu selector có kiểu Point, cần thêm pattern bao phủ phần còn lại hoặc một nhãn default.

Với record lồng nhau, quy tắc được áp dụng đệ quy. Một component pattern lồng nhau có thể chỉ khớp một phần giá trị của component đó; khi ấy record pattern bên ngoài cũng không được xem là bao phủ toàn bộ kiểu record.

## 3. Guard và ảnh hưởng đến coverage

Guard được viết bằng từ khóa when để bổ sung điều kiện cho một pattern:

~~~java
static String classify(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "non-blank text";
        case String text -> "blank text";
        default -> "not a string";
    };
}
~~~

Nhãn đầu tiên chỉ xử lý chuỗi không rỗng theo nghĩa isBlank() == false. Vì guard có thể sai, nhãn đó không bao phủ mọi giá trị String. Nhãn case String text tiếp theo xử lý những chuỗi còn lại, do đó toàn bộ kiểu String được bao phủ.

Với guard là biểu thức hằng có giá trị true, quy tắc coverage có thể xem pattern như không có guard. Trong trường hợp thông thường, hãy coi một guard có thể trả về false là điều kiện làm giảm tập giá trị được nhãn xử lý.

Không nên dựa vào guard để thay thế một nhánh bao quát. Nếu mọi nhãn đều có điều kiện riêng, hãy kiểm tra xem còn giá trị nào không thỏa bất kỳ điều kiện nào hay không và bổ sung nhánh phù hợp.

## 4. Sealed hierarchy giúp chứng minh switch exhaustive

Sealed class hoặc sealed interface giới hạn các kiểu con trực tiếp bằng mệnh đề permits (hoặc danh sách kiểu con được suy ra khi khai báo cùng compilation unit). Trình biên dịch có thể dựa vào danh sách này để xác định các nhánh kiểu có thể xuất hiện.

~~~java
sealed interface Payment permits Cash, Card {}

record Cash(int cents) implements Payment {}
record Card(String lastFour) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case Cash(var cents) -> "cash: " + cents;
        case Card(var lastFour) -> "card ending " + lastFour;
    };
}
~~~

Switch expression trên exhaustive vì:

1. Kiểu selector là Payment.
2. Payment chỉ cho phép hai kiểu con trực tiếp là Cash và Card.
3. Cash(var cents) bao phủ toàn bộ Cash; Card(var lastFour) bao phủ toàn bộ Card.
4. Hợp coverage của hai nhãn bao phủ mọi trường hợp thuộc Payment.

Không cần thêm default chỉ để làm switch này exhaustive. Việc liệt kê các kiểu con đã biết cũng giúp trình biên dịch báo lỗi nếu hierarchy được thay đổi và mã nguồn được biên dịch lại nhưng switch chưa xử lý kiểu con mới.

### Sealed hierarchy nhiều cấp

Quá trình kiểm tra có thể đi qua nhiều cấp sealed type. Ví dụ:

~~~java
sealed interface Expr permits Literal, BinaryExpr {}
record Literal(int value) implements Expr {}

sealed interface BinaryExpr extends Expr permits Add, Multiply {}
record Add(Expr left, Expr right) implements BinaryExpr {}
record Multiply(Expr left, Expr right) implements BinaryExpr {}
~~~

Switch sau bao phủ các kiểu lá có thể xuất hiện:

~~~java
static int evaluate(Expr expr) {
    return switch (expr) {
        case Literal(var value) -> value;
        case Add(var left, var right) -> evaluate(left) + evaluate(right);
        case Multiply(var left, var right) -> evaluate(left) * evaluate(right);
    };
}
~~~

BinaryExpr là sealed và chỉ cho phép Add cùng Multiply. Khi cả Literal, Add và Multiply đều được bao phủ, type coverage bao phủ toàn bộ Expr.

### Nhánh non-sealed trong hierarchy

Một permitted subtype có thể được khai báo non-sealed. Khi đó, các lớp khác có thể tiếp tục kế thừa nhánh này. Pattern cho chính kiểu non-sealed vẫn bao phủ các instance của nó và các kiểu con:

~~~java
sealed interface Message permits TextMessage, ExtensionMessage {}
record TextMessage(String text) implements Message {}
non-sealed class ExtensionMessage implements Message {}

static String route(Message message) {
    return switch (message) {
        case TextMessage(var text) -> text;
        case ExtensionMessage extension -> "extension";
    };
}
~~~

Hai nhãn bao phủ hai permitted subtype trực tiếp. Nhãn ExtensionMessage extension cũng bao phủ các lớp dẫn xuất hợp lệ từ nhánh non-sealed đó.

## 5. Kiểu mở cần nhánh bao quát

Với một interface hoặc class không sealed, trình biên dịch không thể biết toàn bộ kiểu con có thể tồn tại. Chỉ liệt kê một vài implementation hiện tại không đủ để chứng minh exhaustive:

~~~java
interface Payment {}
record Cash(int cents) implements Payment {}
record Card(String lastFour) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case Cash(var cents) -> "cash: " + cents;
        case Card(var lastFour) -> "card: " + lastFour;
        default -> "other payment";
    };
}
~~~

Payment là interface mở, vì vậy một module khác có thể bổ sung implementation. default xử lý những kiểu không được liệt kê.

Nếu miền dữ liệu thực sự cần đóng và muốn trình biên dịch kiểm tra mọi kiểu con, hãy cân nhắc sealed hierarchy. Nếu API được thiết kế để mở rộng bởi module bên ngoài, default thường là lựa chọn thích hợp cho hành vi dự phòng.

## 6. null được xử lý riêng

Type coverage và exhaustiveness của pattern switch không đồng nghĩa với việc null đã được xử lý. Type pattern không khớp null, và nhãn default cũng không bắt giá trị này. Nếu selector là null mà không có nhãn null, switch ném NullPointerException.

Có thể thêm nhánh null riêng:

~~~java
static String describe(Payment payment) {
    return switch (payment) {
        case null -> "no payment";
        case Cash(var cents) -> "cash: " + cents;
        case Card(var lastFour) -> "card: " + lastFour;
    };
}
~~~

Hoặc gộp xử lý null với nhánh mặc định:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
        case null, default -> "no text";
    };
}
~~~

Trong ví dụ thứ hai, case null, default xử lý cả giá trị null lẫn mọi kiểu không phải String. Nếu muốn phân biệt hai tình huống, hãy viết case null và default thành hai nhãn riêng.

## 7. Dominance: nhãn rộng có thể làm nhãn sau không thể đạt tới

Một switch không chỉ cần exhaustive; các nhãn cũng phải có khả năng được chọn. Nếu nhãn trước đã bao phủ toàn bộ trường hợp của nhãn sau, nhãn sau bị xem là dominated và trình biên dịch báo lỗi.

Ví dụ không hợp lệ:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Object object -> "some object";
        case String text -> text;
    };
}
~~~

case Object object đã khớp mọi giá trị không null, bao gồm mọi String. Vì vậy, case String text phía sau không thể được chọn. Có thể sửa bằng cách đặt nhãn cụ thể trước:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
        case Object object -> "some object";
    };
}
~~~

Tương tự, hãy đặt pattern record cụ thể trước pattern bao phủ toàn bộ record đó. Nhãn default cũng nên đặt cuối vì nó xử lý các trường hợp kiểu còn lại.

## 8. Exhaustiveness với enum và thay đổi kiểu theo thời gian

Với enum, switch expression có thể exhaustive khi liệt kê đủ các hằng số của enum:

~~~java
enum Status {
    NEW, RUNNING, DONE
}

static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
~~~

Nếu thêm một hằng số enum rồi biên dịch lại, compiler sẽ yêu cầu cập nhật switch expression chưa có nhánh cho hằng số mới (hoặc thêm default). Với sealed hierarchy, thay đổi danh sách permitted subtype cũng có thể làm switch không còn exhaustive khi biên dịch lại.

Exhaustiveness là bảo đảm dựa trên khai báo kiểu mà compiler nhìn thấy lúc biên dịch. Khi chạy các binary được biên dịch ở những thời điểm khác nhau, một enum hoặc sealed hierarchy có thể đã thay đổi; switch cũ vẫn cần có chiến lược xử lý tương thích phù hợp. Nếu cần hành vi dự phòng cho giá trị mới từ thư viện được nâng cấp độc lập, cân nhắc thêm default có chủ đích.

## 9. Checklist khi thiết kế pattern switch

- [ ] Xác định kiểu tĩnh của selector; coverage được đánh giá theo kiểu này.
- [ ] Kiểm tra switch expression và switch statement có pattern label đã exhaustive.
- [ ] Với sealed type, kiểm tra mọi permitted subtype; nếu subtype tiếp tục sealed, xét các nhánh con của nó.
- [ ] Với nhánh non-sealed, dùng pattern cho chính nhánh đó nếu muốn bao phủ cả các lớp dẫn xuất.
- [ ] Đảm bảo record pattern dùng component pattern toàn phần nếu muốn bao phủ toàn bộ record type.
- [ ] Không dùng guard có thể false làm bằng chứng rằng toàn bộ kiểu đã được bao phủ.
- [ ] Xử lý null riêng nếu nghiệp vụ cần; default không xử lý null.
- [ ] Sắp xếp pattern cụ thể trước pattern tổng quát để tránh dominance.
- [ ] Cân nhắc default khi selector thuộc API mở hoặc cần hành vi dự phòng khi kiểu mở rộng.

Type coverage giúp chuyển câu hỏi “switch đã xử lý đủ chưa?” thành một kiểm tra dựa trên kiểu tĩnh và cấu trúc pattern. Với sealed hierarchy, compiler có thể chứng minh coverage từ danh sách kiểu con; với kiểu mở, guard hoặc record pattern chỉ khớp một phần dữ liệu, cần thiết kế thêm nhánh bao quát để switch hoạt động đầy đủ.

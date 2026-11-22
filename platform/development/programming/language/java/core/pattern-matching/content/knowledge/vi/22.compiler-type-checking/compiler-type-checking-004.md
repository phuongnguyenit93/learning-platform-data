# Exhaustiveness analysis trong Java Pattern Matching

**Chủ đề:** Compiler và type checking — Java Core Pattern Matching. Bài dùng **Java 21 trở lên**, khi pattern matching for switch (JEP 441) và record patterns (JEP 440) đã được chuẩn hóa. Các ví dụ không cần bật preview.

## 1. Exhaustiveness analysis là gì?

**Exhaustiveness** (tính bao phủ đầy đủ) nghĩa là một phép phân nhánh bằng **switch** có nhánh xử lý cho **mọi trường hợp có thể xảy ra theo kiểu tĩnh của biểu thức selector**. Trình biên dịch Java kiểm tra các nhãn case và thông tin kiểu để kết luận phép phân nhánh có đầy đủ hay không.

Ví dụ, một biến kiểu **enum** có hai giá trị LOW và HIGH. Nếu switch expression có case cho cả LOW lẫn HIGH, trình biên dịch biết mọi giá trị enum không null đều được xử lý dù không có default. Tương tự, khi selector có kiểu **sealed interface**, trình biên dịch có thể dựa vào tập các nhánh được phép để chứng minh một switch expression đã bao phủ mọi subtype.

Đây là một phần của **kiểm tra kiểu tĩnh**, có các lợi ích cụ thể:

1. Phát hiện **thiếu nhánh** ngay khi biên dịch, thay vì chờ đầu vào hiếm xảy ra ở runtime.
2. Buộc người viết code xem lại logic khi thêm một giá trị enum hoặc một subtype mới vào miền kiểu đóng.
3. Cho phép viết switch expression **không cần default** nếu các nhánh cụ thể đã đầy đủ.
4. Làm rõ hợp đồng xử lý: mỗi trường hợp có ý nghĩa được mô tả bằng một nhánh riêng.

**Exhaustiveness không có nghĩa dữ liệu hợp lệ về nghiệp vụ.** Compiler chứng minh tính bao phủ dựa trên kiểu và mẫu, nhưng không tự chứng minh chuỗi không rỗng, số dương hoặc các guard động sẽ luôn đúng.

## 2. Switch nào bắt buộc phải exhaustive?

Cần phân biệt ba trường hợp thường gặp:

| Dạng switch | Quy tắc bao phủ trong Java 21 |
| --- | --- |
| **switch expression** trả về giá trị | **Bắt buộc exhaustive**, nếu không sẽ lỗi biên dịch |
| **switch statement sử dụng pattern** | **Bắt buộc exhaustive** theo pattern matching for switch |
| **switch statement truyền thống** không có pattern | Có thể **không exhaustive**; không khớp case nào thì kết thúc switch mà không thực thi nhánh nào |

Ví dụ switch statement truyền thống hợp lệ dù không có default:

~~~java
static void logNumber(int number) {
    switch (number) {
        case 1 -> System.out.println("one");
    }
}
~~~

Nếu number khác 1, không case nào chạy. Nhưng đổi sang **switch expression**:

~~~java
// KHÔNG BIÊN DỊCH: thiếu các giá trị int khác 1.
static String labelNumber(int number) {
    return switch (number) {
        case 1 -> "one";
    };
}
~~~

Trình biên dịch không thể chứng minh mọi số nguyên đều được bao phủ. Có thể thêm **default** hoặc một tập case phù hợp với miền selector. Với miền int tổng quát, default thường là giải pháp.

Một **pattern switch statement** với selector Object mà chỉ có **case String s** cũng sẽ không biên dịch nếu không có nhánh bao phủ các Object còn lại. Điều này khác với statement truyền thống không sử dụng pattern.

## 3. Exhaustiveness với enum

Giả sử enum chỉ có hai hằng số:

~~~java
enum Priority { LOW, HIGH }

static String label(Priority priority) {
    return switch (priority) {
        case LOW -> "low";
        case HIGH -> "high";
    };
}
~~~

Mẫu switch expression này exhaustive đối với **hai giá trị enum không null**. Khi thêm **MEDIUM** vào Priority nhưng chưa thêm case tương ứng, code được biên dịch lại sẽ phải xử lý trường hợp thiếu nhánh hoặc chọn chính sách default mới.

Nếu viết:

~~~java
return switch (priority) {
    case LOW -> "low";
    default -> "other";
};
~~~

switch vẫn đầy đủ, nhưng khi enum được mở rộng, phần lớn giá trị mới tự động đi vào default. Điều đó có thể phù hợp nếu nghiệp vụ thật sự có nhóm “other”; nếu mong muốn xem xét từng giá trị mới, hãy ưu tiên case tường minh và tránh default.

**Lưu ý null:** Priority là kiểu tham chiếu, nên biến priority có thể là null. Tính bao phủ enum không đồng nghĩa có case xử lý null: nếu switch nhận null mà không có case null phù hợp, nó có thể ném **NullPointerException** ở runtime. Viết **case null** khi hợp đồng cho phép và muốn xử lý giá trị đó một cách có chủ đích.

## 4. Exhaustiveness với sealed class hoặc sealed interface

Sealed hierarchy cho phép compiler biết các kiểu con trực tiếp hợp lệ.

~~~java
sealed interface Outcome permits Success, Failure {}

record Success(String value) implements Outcome {}

record Failure(int code) implements Outcome {}
~~~

Đoạn trên minh họa một hierarchy khai báo trong cùng phạm vi hợp lệ. **Outcome** chỉ cho phép **Success** và **Failure** trực tiếp triển khai. Hai record là final theo bản chất, nên không có các subclass tiếp theo của chúng.

Một switch expression có thể liệt kê các subtype:

~~~java
static String simpleLabel(Outcome outcome) {
    return switch (outcome) {
        case Success s -> "success";
        case Failure f -> "failure";
    };
}
~~~

Đây là switch **exhaustive đối với mọi Outcome khác null**. Compiler biết mỗi Outcome hiện có thể là Success hoặc Failure. **case Success s** là type pattern, bao phủ toàn bộ các đối tượng Success; **case Failure f** bao phủ các Failure.

Không bắt buộc dùng record pattern để có tính exhaustive: một **type pattern** đủ rộng cũng có thể bao phủ toàn bộ subtype. Record pattern được dùng khi nhánh cần giải cấu trúc các component, ví dụ **Success(var value)** hoặc **Failure(int code)**.

### Khi hierarchy thay đổi

Nếu bổ sung:

~~~java
// Minh họa thay đổi khai báo; không chép đồng thời hai phiên bản Outcome.
sealed interface Outcome permits Success, Failure, Pending {}

record Pending(String id) implements Outcome {}
~~~

thì switch không có default ở trên thiếu cách xử lý Pending. Khi biên dịch lại các nguồn liên quan, compiler sẽ phát hiện switch expression không exhaustive. Cách sửa mang tính nghiệp vụ là bổ sung **case Pending p**, không vội thêm default chỉ để bỏ cảnh báo.

Một điểm quan trọng: sealed chỉ giới hạn **subtype trực tiếp**. Nếu một nhánh trực tiếp được khai báo **non-sealed**, nhánh đó vẫn có thể được mở rộng:

~~~java
sealed interface Event permits Created, OtherEvent {}
record Created(String id) implements Event {}
non-sealed interface OtherEvent extends Event {}

static String eventName(Event event) {
    return switch (event) {
        case Created(var id) -> "created " + id;
        case OtherEvent e -> "other event";
        case null -> "no event";
    };
}
~~~

Type pattern **OtherEvent e** bao phủ cả các lớp triển khai interface OtherEvent được thêm hợp lệ sau này. Vì thế switch vẫn đầy đủ đối với hierarchy này. Nếu muốn compiler nhắc cập nhật mỗi khi thêm từng loại sự kiện cụ thể, có thể cần thiết kế các nhánh bên dưới cũng là sealed thay vì non-sealed.

## 5. Record patterns: nhắc tên một subtype chưa chắc đã bao phủ nó

Một record pattern có thể đặt các mẫu con vào component. Điều đó khiến nhánh case **hẹp hơn** so với type pattern chỉ kiểm tra subtype.

Ví dụ:

~~~java
record Point(int x, int y) {}
record Route(Point origin) {}
~~~

Với selector kiểu Route:

~~~java
// Mẫu minh họa: cần nhánh còn lại.
static String describeRoute(Route route) {
    return switch (route) {
        case Route(Point(int x, int y)) -> x + "," + y;
        case Route(var origin) -> "missing origin";
        case null -> "null route";
    };
}
~~~

Nhánh **Route(Point(int x, int y))** chỉ khớp nếu component origin là một Point không null. Một **Route(null)** không khớp mẫu lồng Point(...). Nhánh **Route(var origin)** không đòi hỏi origin có nội dung khác null, nên bao phủ các Route còn lại.

Nếu bỏ nhánh **Route(var origin)**, một switch expression chỉ còn mẫu lồng Point(...) có thể không exhaustive vì vẫn tồn tại Route có origin là null. Compiler phân tích **phạm vi thực sự của mẫu**, không chỉ xem tên Route đã xuất hiện trong case.

Các mẫu component có kiểu khớp **unconditional** (ví dụ var dùng cho component tương ứng) có thể bao gồm cả giá trị null của component tham chiếu. Nhưng một **record pattern lồng cụ thể** lại yêu cầu có đối tượng record để giải cấu trúc. Vì vậy phải hiểu loại mẫu con đang dùng trước khi kết luận case bao phủ toàn bộ subtype.

## 6. Guard khi dùng when: tính đầy đủ không đến từ điều kiện động

Guard **when** làm cho case chỉ áp dụng khi **pattern đã khớp** và điều kiện bổ sung trả về true:

~~~java
case Failure(int code) when code >= 500 -> "server error";
~~~

Case này **không bao phủ** mọi Failure, vì code có thể nhỏ hơn 500. Nếu chỉ có case guard này mà không có case không guard hoặc một mẫu tổng quát tương đương, switch có thể thiếu nhánh.

Cách viết rõ ràng:

~~~java
case Failure(int code) when code >= 500 -> "server error";
case Failure(int code) -> "other error";
~~~

Nhánh thứ hai bao phủ tất cả Failure còn lại.

Không nên giả định compiler dùng suy luận logic tổng quát để chứng minh một nhóm guard bất kỳ sẽ luôn bao phủ mọi giá trị. Ví dụ, dù con người có thể thấy **code >= 500** và **code < 500** là hai điều kiện bù nhau, Java không thực hiện phân tích định lý tùy ý trên mọi biểu thức guard để bảo đảm exhaustiveness. Dùng một case không guard khi cần điểm bao phủ tổng quát.

Đặt nhánh cụ thể có guard **trước** nhánh tổng quát. Nếu đặt Failure không guard trước Failure có guard, nhánh sau bị **dominated** (bị che phủ), một vấn đề khác với tính thiếu nhánh.

## 7. Chương trình Java 21 hoàn chỉnh

Ví dụ bên dưới kết hợp sealed interface, record pattern, guard, enum và case null. Các switch expression **không có default nhưng vẫn exhaustive**.

Lưu tệp **ExhaustivenessAnalysisDemo.java**:

~~~java
public class ExhaustivenessAnalysisDemo {
    sealed interface Outcome permits Success, Failure {}

    record Success(String value) implements Outcome {}

    record Failure(int code) implements Outcome {}

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(var value)
                    when value != null && !value.isBlank() ->
                    "SUCCESS: " + value;

            case Success(var value) -> "SUCCESS: empty";

            case Failure(int code) when code >= 500 ->
                    "SERVER ERROR: " + code;

            case Failure(int code) -> "ERROR: " + code;

            case null -> "NO OUTCOME";
        };
    }

    enum Priority { LOW, HIGH }

    static String priorityLabel(Priority priority) {
        return switch (priority) {
            case LOW -> "low";
            case HIGH -> "high";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("ready")));
        System.out.println(describe(new Success("")));
        System.out.println(describe(new Success(null)));
        System.out.println(describe(new Failure(503)));
        System.out.println(describe(new Failure(404)));
        System.out.println(describe(null));
        System.out.println(priorityLabel(Priority.HIGH));
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac ExhaustivenessAnalysisDemo.java
java ExhaustivenessAnalysisDemo
~~~

Đầu ra:

~~~text
SUCCESS: ready
SUCCESS: empty
SUCCESS: empty
SERVER ERROR: 503
ERROR: 404
NO OUTCOME
high
~~~

**Giải thích tính bao phủ của describe():**

1. **Success với value khác null và không rỗng** khớp case đầu; đây là nhánh cụ thể có guard.
2. **Success còn lại**, gồm chuỗi rỗng hoặc component value null, khớp case Success không guard.
3. **Failure có code từ 500** khớp case Failure đầu tiên.
4. **Failure còn lại** khớp case Failure thứ hai.
5. **null** được xử lý bằng case null.

Vì Outcome chỉ có hai subtype Success và Failure, cả hai được bao phủ hoàn toàn, và null cũng có nhánh rõ ràng, switch expression hợp lệ mà không cần default. Tương tự, Priority chỉ có LOW và HIGH, nên priorityLabel() không cần default; tuy nhiên nó chưa xử lý selector null và sẽ ném NullPointerException nếu nhận null.

Record pattern với component **var value** có thể ràng buộc giá trị null. Guard **value != null && !value.isBlank()** vừa tránh lỗi dereference null, vừa thể hiện quy tắc chấp nhận dữ liệu của nhánh đầu. Exhaustiveness chỉ yêu cầu có nhánh cho mọi kiểu/trạng thái cấu trúc, không tự xác thực văn bản value.

## 8. Ví dụ lỗi biên dịch và cách sửa

Đoạn sau là **mã không hợp lệ, dùng để quan sát lỗi compiler**, không ghép vào chương trình đã chạy ở trên:

~~~java
sealed interface State permits Good, Bad {}
record Good(int amount) implements State {}
record Bad(String reason) implements State {}

static String guardedOnly(State state) {
    return switch (state) {
        case Good(int amount) when amount > 0 -> "positive";
        case Bad(var reason) -> "bad";
    };
}
~~~

**Vì sao lỗi?** Một giá trị **Good(0)** hoặc **Good(-1)** không khớp nhánh Good có guard. Bad có case nhưng Good chưa được bao phủ toàn bộ. Compiler báo switch expression không bao phủ tất cả giá trị đầu vào, có thể diễn đạt:

~~~text
the switch expression does not cover all possible input values
~~~

Có thể sửa bằng cách thêm case tổng quát sau case có guard:

~~~java
case Good(int amount) -> "non-positive";
~~~

Chú ý đây là **thêm nhánh xử lý hợp lệ về ý nghĩa**, không phải thêm một case giả chỉ để qua kiểm tra. Khi ý nghĩa nghiệp vụ phân biệt Good dương và không dương, hai case là cần thiết.

### Dominance và exhaustiveness là hai phép kiểm tra khác nhau

- **Exhaustiveness** hỏi: Có giá trị hợp lệ nào **không** được nhánh nào bao phủ không?
- **Dominance** hỏi: Có case phía sau nào **không thể được chọn** vì case phía trước đã bao phủ trường hợp của nó không?

Ví dụ, nếu đặt **case Good(var amount)** trước **case Good(int amount) when amount > 0**, nhánh thứ hai bị case tổng quát chiếm hết và có thể gây lỗi biên dịch. Một switch có thể exhaustive mà vẫn mắc lỗi dominance; cần thỏa **cả hai**.

## 9. Trình biên dịch thực sự biết điều gì, không biết điều gì?

Compiler có thể suy luận theo những thông tin tĩnh:

- **Kiểu selector:** một enum, một sealed hierarchy, hoặc kiểu rộng như Object.
- **Nhãn case:** hằng số enum, type pattern, record pattern, nhánh tổng quát, default và case null.
- **Quan hệ subtype và permits:** kiểu nào bị đóng, kiểu nào còn mở rộng, kiểu nào được một pattern bao phủ.
- **Mẫu record con:** sự tương thích và tính toàn phần của deconstruction đối với component, gồm các trường hợp không khớp.
- **Guard:** một case có guard tùy ý không được mặc nhiên xem là bao phủ mọi giá trị của pattern.

Compiler **không** thay thế kiểm tra các điều kiện miền như chuỗi hợp lệ, kích thước dương, hoặc thứ tự nghiệp vụ; những điều đó phải do code đảm bảo. Compiler cũng không thể dự đoán mọi tình huống thay đổi class ở runtime sau khi biên dịch.

Nếu dùng **case default** cho selector kiểu Object, đó là cách bao phủ các kiểu không được những pattern khác xử lý. Với một sealed hierarchy đóng hoàn toàn, không có default có thể là một lợi thế vì khi thêm subtype mới và biên dịch lại, thiếu nhánh sẽ trở thành lỗi rõ ràng.

## 10. Exhaustiveness và null

**Null không phải subtype của sealed interface hoặc enum.** Vì vậy một switch exhaustive theo tập subtype vẫn có thể ném NullPointerException khi selector null nếu không có case null phù hợp. Đừng nhầm “bao phủ mọi subtype” với “chấp nhận mọi reference value gồm null”.

Đặt chiến lược null tại ranh giới API:

- Nếu null **không hợp lệ**, có thể dùng Objects.requireNonNull() tại đầu phương thức hoặc chấp nhận lỗi switch khi gặp null và ghi rõ hợp đồng.
- Nếu null có ý nghĩa như “không có kết quả”, viết **case null** tường minh và quy định giá trị trả về.
- Nếu đầu vào là record có **component con null**, đó là chuyện khác với selector null. Một record pattern lồng sâu có thể không khớp, dù record cha vẫn khác null; thêm một nhánh bao phủ record cha khi cần.

Không dùng default như một cách ngầm bảo đảm null được xử lý: với pattern switch, default thông thường không thay thế case null cho selector null.

## 11. Exhaustiveness khi thay đổi phiên bản hoặc biên dịch riêng lẻ

Exhaustiveness được phân tích **tại thời điểm biên dịch**, dựa trên định nghĩa kiểu mà compiler nhìn thấy. Điều này rất hữu ích cho việc bảo trì:

1. Thêm enum constant hoặc subtype permitted.
2. Biên dịch lại các lớp chứa switch liên quan.
3. Nếu switch thiếu case, compiler chỉ ra vị trí cần đánh giá nghiệp vụ.
4. Cập nhật nhánh và kiểm thử tất cả trường hợp.

Tuy nhiên, với triển khai nhiều module hoặc class được biên dịch ở các thời điểm khác nhau, một switch từng được coi là exhaustive có thể đối diện một giá trị mới mà bytecode cũ không dự kiến. Các cơ chế runtime của Java có thể báo lỗi như **MatchException** trong những tình huống một exhaustive switch không thể tìm được nhánh tương ứng. Đây không phải lời hứa rằng compile-time analysis tự bảo vệ khỏi mọi thay đổi binary không đồng bộ.

Nên biên dịch và triển khai các thành phần có quan hệ kiểu nhất quán, bổ sung test cho subtype mới, và quan sát lỗi runtime khi có thay đổi hierarchy. Không dựa vào default để che sai khác phiên bản nếu yêu cầu là phải xem lại từng trường hợp.

## 12. Các lỗi phổ biến khi đánh giá exhaustiveness

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ viết case có **when** cho một subtype | Không bao phủ subtype khi guard false | Thêm case không guard phù hợp |
| Tưởng có tên record trong một case là đủ | Mẫu record lồng có thể bỏ sót record con null | Thêm nhánh cho phần còn lại của record |
| Thêm default từ đầu cho sealed hierarchy | Không nhận cảnh báo khi subtype mới xuất hiện | Ưu tiên case cụ thể nếu cần buộc review |
| Đặt case rộng trước case hẹp | Case hẹp bị dominated | Chuyển case có guard lên trước |
| Quên null | Switch có thể ném NullPointerException | Quy định rõ hợp đồng và dùng case null nếu cần |
| Tưởng mọi switch statement đều cần exhaustive | Nhầm quy tắc với statement truyền thống | Phân biệt switch expression, pattern switch statement và traditional switch statement |
| Tưởng sealed đóng toàn bộ các nhánh vô hạn cấp | Một nhánh non-sealed vẫn có descendants mới | Dùng pattern bao phủ nhánh non-sealed hoặc thiết kế hierarchy khác |
| Tưởng exhaustiveness chứng minh validation | Dữ liệu có thể sai nghiệp vụ dù có nhánh | Viết guard/validation riêng |
| Chỉ biên dịch một phần sau khi đổi kiểu | Binary cũ có thể gặp runtime mismatch | Biên dịch và kiểm thử nhất quán các phụ thuộc |

## 13. Checklist thực hành

Khi review một switch, hãy đi theo trình tự:

1. **Xác định kiểu selector** và switch expression hay statement.
2. **Liệt kê miền kiểu hợp lệ**: constants của enum, permitted descendants của sealed hierarchy, hoặc miền mở như Object.
3. **Đánh giá mỗi case**: pattern đó bao phủ toàn bộ subtype hay chỉ một phần vì guard/mẫu lồng?
4. **Tìm lỗ hổng**: các giá trị chưa có case, đặc biệt guard false, record con null hoặc subtype mới.
5. **Kiểm tra dominance**: nhánh nào trở nên không thể tới vì bị nhánh rộng đứng trước?
6. **Xác định chính sách null**: có case null hoặc hợp đồng từ chối null rõ ràng?
7. **Thử mở rộng miền kiểu** khi phù hợp: thêm một enum constant hoặc subtype trong bài thử rồi xác nhận compiler phát hiện những switch cần sửa.
8. **Chạy test hành vi** cho từng nhánh, các giá trị biên guard, null và những thay đổi binary quan trọng.

**Ghi nhớ:** Exhaustiveness analysis là khả năng của compiler để chứng minh một switch **bao phủ đủ các dạng giá trị theo kiểu và pattern**. Sealed type và enum cung cấp miền kiểu có thể phân tích; record pattern và type pattern mô tả nhánh; guard có thể thu hẹp nhánh; case tổng quát hoặc default lấp phần còn lại khi được thiết kế đúng. Hãy để compiler phát hiện thiếu nhánh và giữ validation nghiệp vụ minh bạch trong code.
# Tách lỗi dữ liệu khỏi lỗi điều khiển khi dùng Pattern Matching (Java 21+)

## 1. Vì sao cần tách hai loại lỗi?

Trong luồng nhận và xử lý lệnh, một yêu cầu có thể thất bại vì **dữ liệu không hợp lệ**, hoặc vì **luồng điều khiển không cho phép thao tác đó**. Hai tình huống có thể cùng khiến hệ thống trả về “không thành công”, nhưng nguyên nhân và cách khắc phục khác nhau.

Ví dụ, ứng dụng xử lý lệnh thanh toán `Pay(orderId, cents)` và lệnh hủy `Cancel(orderId)`:

- `Pay(null, 100)`: thiếu mã đơn hàng — **lỗi dữ liệu**.
- `Pay("O1", -1)`: số tiền không hợp lệ — **lỗi dữ liệu**.
- `Pay("O1", 100)` khi quy trình đã `CLOSED`: dữ liệu tự nó hợp lệ, nhưng **thao tác không được phép trong trạng thái hiện tại**.
- `raw = "PAY"` khi bộ xử lý chỉ nhận đối tượng lệnh `Pay` hoặc `Cancel`: loại thông điệp không thuộc giao thức mong đợi — trong ví dụ này được coi là **lỗi định tuyến/điều khiển**.
- `null` là request đầu vào: ví dụ quy ước đó là **thiếu dữ liệu**; nếu `stage == null`, ví dụ coi là **lỗi ngữ cảnh xử lý**.

Đây là **chính sách phân loại của domain minh họa**, không phải bộ quy tắc mặc định của Java. Trong một API công khai, một thông điệp không đúng loại có thể được phân loại là lỗi dữ liệu người gọi; trong một luồng nội bộ, nó có thể là lỗi định tuyến. Điều quan trọng là **chọn chính sách rõ ràng, nhất quán**, không để kết quả phụ thuộc tình cờ vào `ClassCastException`, `NullPointerException` hoặc một nhánh `default` quá rộng.

Pattern matching phù hợp để thể hiện các đường đi khác nhau bằng một `switch` có các mẫu cụ thể, `when` guard và kết quả có kiểu rõ ràng.

## 2. Ba tầng phân loại cần phân biệt

Để không trộn các tình huống có cách xử lý khác nhau, nên nhìn ít nhất ba tầng:

| Tầng | Ví dụ | Bản chất | Phản ứng thường hợp lý |
| --- | --- | --- | --- |
| Lỗi dữ liệu (*DataProblem*) | `orderId` null/trắng, `cents <= 0` | Payload không thỏa hợp đồng | Trả lỗi validation, chỉ rõ field; người gọi sửa dữ liệu |
| Lỗi điều khiển (*FlowProblem*) | Thanh toán ở trạng thái `CLOSED`, loại lệnh nội bộ không được hỗ trợ | Thao tác hoặc route không phù hợp trạng thái/giao thức | Từ chối thao tác, kiểm tra luồng gọi hoặc chuyển trạng thái |
| Lỗi lập trình/hạ tầng | `NullPointerException` ngoài dự kiến, cấu hình sai, I/O thất bại | Bug hoặc phụ thuộc hệ thống lỗi | Ghi log, chẩn đoán, xử lý ở ranh giới phù hợp; không giả làm validation |

Bài tập trung vào **hai loại kết quả dự kiến trong nghiệp vụ**, nhưng phải phân biệt chúng với **ngoại lệ bất ngờ**. Không nên bắt mọi `RuntimeException` rồi trả về “dữ liệu sai”: làm vậy che mất lỗi lập trình và khiến vận hành khó xác định nguyên nhân thật.

Một hệ thống có thể dùng thêm loại kết quả riêng cho hạ tầng hoặc phát tán exception tới lớp xử lý tập trung. Quyết định đó tùy kiến trúc; không ép mọi thứ vào `DataProblem` hay `FlowProblem`.

## 3. Anti-pattern: dùng exception để quyết định lỗi dữ liệu

Ví dụ thường gặp:

~~~java
// CỐ Ý KHÔNG KHUYẾN NGHỊ:
static String bad(Object raw) {
    try {
        Pay pay = (Pay) raw;
        return pay.orderId().toUpperCase();
    } catch (RuntimeException ex) {
        return "INVALID_DATA";
    }
}
~~~

Đây là **đoạn minh họa** có kiểu `Pay` giả định đã được khai báo, không phải chương trình độc lập. Nó gộp nhiều nguyên nhân không liên quan:

- `raw` không phải `Pay`: có thể ném `ClassCastException`.
- `raw == null`: ép kiểu tham chiếu null không tự làm null thành đối tượng; lời gọi `pay.orderId()` gây `NullPointerException`.
- `orderId == null`: `orderId().toUpperCase()` gây `NullPointerException`.
- Một lỗi lập trình bất ngờ khác cũng là `RuntimeException` sẽ bị đổi thành `"INVALID_DATA"`.

Không phải mọi exception đều là input lỗi. Thay vì suy luận loại lỗi từ một catch rộng, hãy **kiểm tra cấu trúc dữ liệu bằng pattern**, **kiểm tra giá trị bằng guard**, rồi **kiểm tra trạng thái điều khiển** ở bước tương ứng.

Cách tiếp cận được khuyến nghị không phủ nhận hoàn toàn việc dùng exception. Exception vẫn có vai trò cho lỗi lập trình, vi phạm invariant nghiêm trọng hoặc lỗi hạ tầng. Vấn đề là **không dùng một catch tổng quát như bộ phân loại nghiệp vụ**.

## 4. Mô hình dữ liệu và mô hình kết quả

Định nghĩa hai loại lệnh:

~~~java
sealed interface Command permits Pay, Cancel {}

record Pay(String orderId, int cents) implements Command {}
record Cancel(String orderId) implements Command {}

enum Stage { OPEN, CLOSED }
~~~

Đây là **các khai báo minh họa** sẽ được đặt chung trong lớp `ErrorSeparationDemo` ở mục 9.

Chọn `sealed interface` vì hệ thống minh họa có đúng hai lệnh hợp lệ về mặt giao thức: `Pay` và `Cancel`. Mỗi record mang đúng dữ liệu của nó. Việc một bản ghi là `Pay` **không có nghĩa payload hợp lệ**: `Pay(null, -1)` vẫn tạo được vì các record đầu vào ở ví dụ **cố ý chưa validate trong constructor** để bộ xử lý có thể phân loại lỗi dữ liệu.

Chọn một kiểu kết quả có ba biến thể rõ ràng:

~~~java
sealed interface Outcome permits Done, DataProblem, FlowProblem {}

record Done(String message) implements Outcome {}
record DataProblem(String field, String reason) implements Outcome {}
record FlowProblem(String reason) implements Outcome {}
~~~

Cách tổ chức này cho phép mã gọi phân biệt ba trường hợp bằng **kiểu**, thay vì phân tích một chuỗi thông báo tự do.

- `Done`: thao tác hợp lệ và được chấp nhận.
- `DataProblem`: dữ liệu thiếu hoặc không đạt validation; giữ tên field và lý do.
- `FlowProblem`: không đúng trạng thái hoặc giao thức xử lý; giữ lý do.

Ở hệ thống thật, có thể thêm mã lỗi ổn định (`enum ErrorCode`) và dữ liệu phục vụ client, tránh phụ thuộc trực tiếp vào chuỗi ngôn ngữ tự nhiên.

## 5. Bước đầu: kiểm tra cấu trúc bằng record pattern

Với đầu vào kiểu tĩnh `Object`, câu lệnh truyền thống thường là nhiều `if` và ép kiểu. Java 21 cho phép phân rã payload ngay trong `switch`:

~~~java
return switch (raw) {
    case Pay(var orderId, var cents) -> /* xử lý Pay */;
    case Cancel(var orderId) -> /* xử lý Cancel */;
    case null -> /* thiếu request */;
    default -> /* loại lệnh khác */;
};
~~~

Đây là **khung minh họa** (các comment thay biểu thức kết quả nên không thể biên dịch nguyên trạng). Trong chương trình hoàn chỉnh ở mục 9, mỗi nhánh sẽ trả về một `Outcome` cụ thể.

Vì sao cấu trúc này hữu ích?

1. `case Pay(...)` cho biết nhánh chỉ xử lý một `Pay` và lấy được `orderId`, `cents` mà không ép kiểu.
2. `case Cancel(...)` xử lý payload của lệnh hủy theo cấu trúc riêng.
3. `case null` có ý nghĩa khác `default`. Trong pattern `switch` Java 21, **`default` không tự xử lý selector null**; thiếu nhánh null hoặc bước kiểm tra trước có thể làm `switch` ném `NullPointerException`.
4. `default` ở đây biểu diễn **kiểu thông điệp không thuộc giao thức**. Đây là một quyết định phân loại có chủ đích; trong các giao diện nhận dữ liệu từ bên ngoài, đội phát triển phải quyết định nó là validation hay lỗi định tuyến.

**Cẩn thận:** biến tạo bởi `var orderId` có kiểu tĩnh `String` nhưng vẫn có thể giữ giá trị `null`. Record pattern **không thay thế** kiểm tra non-null và quy tắc nghiệp vụ.

## 6. Bước thứ hai: kiểm tra lỗi dữ liệu trước

Định nghĩa hàm validation ngắn gọn:

~~~java
static boolean blank(String value) {
    return value == null || value.isBlank();
}
~~~

`||` đánh giá từ trái sang phải. Khi `value == null` đúng, Java không gọi `value.isBlank()`, vì thế tránh `NullPointerException`.

Khi xử lý thanh toán, các nhánh dữ liệu đứng trước nhánh điều khiển:

~~~java
case Pay(var id, var cents) when blank(id) ->
        new DataProblem("orderId", "missing");

case Pay(var id, var cents) when cents <= 0 ->
        new DataProblem("cents", "must be positive");
~~~

Hai guard mô tả **dữ liệu sai** mà không cần tạo exception. Một `Pay` có `orderId` trống bị từ chối với field `orderId`; lệnh có `cents <= 0` bị từ chối với field `cents`.

Đối với `Cancel`:

~~~java
case Cancel(var id) when blank(id) ->
        new DataProblem("orderId", "missing");
~~~

Đây là các **nhánh minh họa** nằm trong `switch` của mục 9, không phải câu lệnh Java độc lập.

### Vì sao validation phải đứng trước kiểm tra trạng thái?

Giả sử lệnh `Pay(" ", 0)` đến khi trạng thái đã `CLOSED`. Cả dữ liệu lẫn trạng thái đều không hợp lệ. Ví dụ này chọn **ưu tiên báo lỗi dữ liệu trước** để người gọi biết payload đang sai, rồi mới xem xét tính hợp lệ của thao tác trong ngữ cảnh xử lý.

Không có thứ tự ưu tiên đúng cho mọi sản phẩm. Một hệ thống bảo mật có thể cố tình kiểm tra quyền hoặc trạng thái trước khi tiết lộ lý do validation; quy tắc ưu tiên phải được thiết kế theo hợp đồng API và yêu cầu an toàn. Điều cần tránh là vô tình thay đổi thứ tự khi refactor các `case` và khiến cùng một input trả lỗi khác.

## 7. Bước thứ ba: kiểm tra trạng thái điều khiển

Chỉ sau khi payload đã qua các điều kiện dữ liệu, mới xét khả năng thực hiện thao tác:

~~~java
case Pay(var id, var cents) when stage == Stage.CLOSED ->
        new FlowProblem("payment blocked in CLOSED");

case Pay(var id, var cents) ->
        new Done("paid:" + id + ":" + cents);

case Cancel(var id) when stage == Stage.CLOSED ->
        new FlowProblem("cancel blocked in CLOSED");

case Cancel(var id) ->
        new Done("cancelled:" + id);
~~~

Thứ tự các nhánh là một phần của logic:

- Các nhánh `when` cụ thể về validation phải đứng trước nhánh cùng loại lệnh nhưng rộng hơn.
- Sau validation, trạng thái `CLOSED` được phân loại là **không cho phép thực thi**.
- Nhánh `Pay(...)` hoặc `Cancel(...)` không có guard ở cuối là đường **thành công** sau khi các điều kiện trên đã loại các ca thất bại.

Nếu đặt nhánh `case Pay(...)` không có guard lên trước các nhánh `Pay(...) when ...`, những nhánh cụ thể phía sau có thể bị compiler báo *dominated* (bị che khuất). Việc sắp xếp theo **cụ thể trước, tổng quát sau** giúp Java kiểm tra và giúp người đọc theo dõi quyết định.

### Lỗi điều khiển và lỗi lập trình không nhất thiết giống nhau

Lệnh thanh toán ở trạng thái `CLOSED` có thể là một phản hồi nghiệp vụ dự kiến (*conflict*), nên ví dụ trả `FlowProblem`. Nhưng nếu code chạy vào một trạng thái vốn **không thể có theo invariant nội bộ**, đó có thể là bug và đáng ném `IllegalStateException` hoặc báo lỗi nội bộ thay vì xem là từ chối nghiệp vụ bình thường.

Tương tự, `stage == null` trong ví dụ bị phân loại là `FlowProblem("stage missing")` vì nó là ngữ cảnh bắt buộc do bộ gọi cung cấp. Ứng dụng khác có thể coi đó là lỗi lập trình và dùng `Objects.requireNonNull(stage)`. **Điều quan trọng là làm rõ nguồn của giá trị và ai chịu trách nhiệm sửa nó**.

## 8. Tách kết quả khỏi ngoại lệ và giữ exhaustive switch

Một nơi xử lý kết quả có thể dùng `switch expression` trên `Outcome`:

~~~java
static String describe(Outcome outcome) {
    return switch (outcome) {
        case Done(var message) -> "OK:" + message;
        case DataProblem(var field, var reason) ->
                "DATA:" + field + ":" + reason;
        case FlowProblem(var reason) -> "FLOW:" + reason;
    };
}
~~~

Vì `Outcome` là `sealed interface` và ba subtype đều là record (final), compiler kiểm tra được rằng ba nhánh bao phủ tất cả các subtype được phép **khác null**. Không cần `default` trong ví dụ. Nếu thêm subtype mới, biểu thức có thể yêu cầu cập nhật nhánh, giúp phát hiện việc quên xử lý loại kết quả.

Hàm trên coi `outcome` là không null theo hợp đồng. Nếu một caller truyền null, đó không tự trở thành `DataProblem`; ứng dụng nên xác định có từ chối null ở ranh giới này hay không. Tránh lấy tính exhaustive của kiểu làm lý do để quên khả năng null.

Một hàm khác có thể phân loại tập lệnh hợp lệ:

~~~java
static String kind(Command command) {
    java.util.Objects.requireNonNull(command, "command");

    return switch (command) {
        case Pay pay -> "PAY";
        case Cancel cancel -> "CANCEL";
    };
}
~~~

Khác với `handle(Object raw, Stage stage)` ở ranh giới vào, hàm `kind(Command)` chỉ nhận một `Command` hợp lệ về **kiểu**, vì vậy không cần `default` để bắt chuỗi hoặc số nguyên. Sự khác nhau này phản ánh một quyết định kiến trúc: **kiểm tra kiểu và dữ liệu ở ranh giới**, sau đó chuyển vào domain bằng kiểu chặt hơn.

## 9. Chương trình Java 21 hoàn chỉnh, 19 ca kiểm thử

Lưu mã dưới đây trong tệp **`ErrorSeparationDemo.java`**. Chương trình không cần thư viện ngoài JDK.

~~~java
public class ErrorSeparationDemo {
    sealed interface Command permits Pay, Cancel {}
    record Pay(String orderId, int cents) implements Command {}
    record Cancel(String orderId) implements Command {}
    enum Stage { OPEN, CLOSED }

    sealed interface Outcome permits Done, DataProblem, FlowProblem {}
    record Done(String message) implements Outcome {}
    record DataProblem(String field, String reason) implements Outcome {}
    record FlowProblem(String reason) implements Outcome {}

    private static int passed = 0;

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static Outcome handle(Object raw, Stage stage) {
        if (stage == null) {
            return new FlowProblem("stage missing");
        }

        return switch (raw) {
            case null -> new DataProblem("request", "missing");

            case Pay(var id, var cents) when blank(id) ->
                new DataProblem("orderId", "missing");
            case Pay(var id, var cents) when cents <= 0 ->
                new DataProblem("cents", "must be positive");
            case Pay(var id, var cents) when stage == Stage.CLOSED ->
                new FlowProblem("payment blocked in CLOSED");
            case Pay(var id, var cents) ->
                new Done("paid:" + id + ":" + cents);

            case Cancel(var id) when blank(id) ->
                new DataProblem("orderId", "missing");
            case Cancel(var id) when stage == Stage.CLOSED ->
                new FlowProblem("cancel blocked in CLOSED");
            case Cancel(var id) ->
                new Done("cancelled:" + id);

            default -> new FlowProblem("unsupported command type");
        };
    }

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Done(var message) -> "OK:" + message;
            case DataProblem(var field, var reason) ->
                "DATA:" + field + ":" + reason;
            case FlowProblem(var reason) -> "FLOW:" + reason;
        };
    }

    static String kind(Command command) {
        java.util.Objects.requireNonNull(command, "command");
        return switch (command) {
            case Pay pay -> "PAY";
            case Cancel cancel -> "CANCEL";
        };
    }

    static void check(
            String label, Object raw, Stage stage, Outcome expected) {
        Outcome actual = handle(raw, stage);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + ", actual " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + describe(actual));
    }

    static void checkKind(
            String label, Command command, String expected) {
        String actual = kind(command);
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("pay-ok", new Pay("O1", 120), Stage.OPEN,
                new Done("paid:O1:120"));
        check("cancel-ok", new Cancel("O1"), Stage.OPEN,
                new Done("cancelled:O1"));
        check("missing-request", null, Stage.OPEN,
                new DataProblem("request", "missing"));
        check("missing-stage", new Pay("O1", 120), null,
                new FlowProblem("stage missing"));

        check("pay-null-id", new Pay(null, 120), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("pay-blank-id", new Pay("  ", 120), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("pay-zero", new Pay("O1", 0), Stage.OPEN,
                new DataProblem("cents", "must be positive"));
        check("pay-negative", new Pay("O1", -1), Stage.OPEN,
                new DataProblem("cents", "must be positive"));
        check("data-before-stage", new Pay(" ", 0), Stage.CLOSED,
                new DataProblem("orderId", "missing"));
        check("pay-closed", new Pay("O1", 120), Stage.CLOSED,
                new FlowProblem("payment blocked in CLOSED"));

        check("cancel-null-id", new Cancel(null), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("cancel-blank-id", new Cancel(" "), Stage.OPEN,
                new DataProblem("orderId", "missing"));
        check("cancel-closed", new Cancel("O1"), Stage.CLOSED,
                new FlowProblem("cancel blocked in CLOSED"));
        check("unsupported-string", "PAY", Stage.OPEN,
                new FlowProblem("unsupported command type"));
        check("unsupported-integer", 7, Stage.OPEN,
                new FlowProblem("unsupported command type"));
        check("pay-min-positive", new Pay("O2", 1), Stage.OPEN,
                new Done("paid:O2:1"));
        check("cancel-missing-stage", new Cancel("O1"), null,
                new FlowProblem("stage missing"));
        checkKind("sealed-pay", new Pay("O1", 1), "PAY");
        checkKind("sealed-cancel", new Cancel("O1"), "CANCEL");

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch và chạy trên JDK 21 trở lên:

~~~bash
javac --release 21 ErrorSeparationDemo.java
java ErrorSeparationDemo
~~~

**Kết quả dự kiến:**

~~~text
PASS pay-ok -> OK:paid:O1:120
PASS cancel-ok -> OK:cancelled:O1
PASS missing-request -> DATA:request:missing
PASS missing-stage -> FLOW:stage missing
PASS pay-null-id -> DATA:orderId:missing
PASS pay-blank-id -> DATA:orderId:missing
PASS pay-zero -> DATA:cents:must be positive
PASS pay-negative -> DATA:cents:must be positive
PASS data-before-stage -> DATA:orderId:missing
PASS pay-closed -> FLOW:payment blocked in CLOSED
PASS cancel-null-id -> DATA:orderId:missing
PASS cancel-blank-id -> DATA:orderId:missing
PASS cancel-closed -> FLOW:cancel blocked in CLOSED
PASS unsupported-string -> FLOW:unsupported command type
PASS unsupported-integer -> FLOW:unsupported command type
PASS pay-min-positive -> OK:paid:O2:1
PASS cancel-missing-stage -> FLOW:stage missing
PASS sealed-pay -> PAY
PASS sealed-cancel -> CANCEL
ALL PASSED: 19
~~~

### Đọc kết quả kiểm thử

- **`pay-ok`, `cancel-ok`, `pay-min-positive`** xác minh luồng thành công và giá trị biên `cents == 1`.
- **`missing-request`** xác nhận `case null` trả lỗi dữ liệu thay vì gây NPE.
- **`pay-null-id`, `pay-blank-id`, `pay-zero`, `pay-negative` và các ca `cancel` thiếu mã** xác nhận validation trả `DataProblem`.
- **`data-before-stage`** xác nhận chính sách **ưu tiên lỗi dữ liệu** khi một payload vừa thiếu mã vừa gặp stage `CLOSED`. Nhánh kiểm tra `orderId` xuất hiện trước nhánh stage.
- **`pay-closed` và `cancel-closed`** trả `FlowProblem` khi payload hợp lệ nhưng thao tác không được phép trong trạng thái hiện tại.
- **`missing-stage`, `cancel-missing-stage`** trả `FlowProblem` vì ngữ cảnh điều khiển không được cung cấp.
- **`unsupported-string` và `unsupported-integer`** xác nhận kiểu lệnh không thuộc tập cho phép đi vào `default`, theo chính sách phân loại của ví dụ.
- **`sealed-pay` và `sealed-cancel`** chứng minh `switch` exhaustive trên `Command` xử lý cả hai subtype trực tiếp mà không cần `default`.

Hàm `check` đối chiếu chính **đối tượng kết quả** bằng `equals` của record, chứ không chỉ kiểm tra một phần chuỗi hiển thị. Nếu kết quả sai, nó ném `AssertionError` ngay. Vì thế, `ALL PASSED: 19` chỉ xuất hiện sau khi toàn bộ ca được xác nhận.

Đây là mô hình **phân loại và trả kết quả**; mã không thực sự gọi dịch vụ thanh toán hoặc thay đổi trạng thái đơn hàng. Khi tích hợp với hệ thống thật, hành động có side effect phải được thực thi trong tầng ứng dụng phù hợp và xử lý các lỗi hạ tầng riêng.

## 10. Từ bản minh họa tới kiến trúc thực tế

Một quy trình thường có các bước:

1. **Nhận dữ liệu ở biên** (HTTP, message queue, CLI, file). Đây là nơi dữ liệu có thể thiếu trường, sai kiểu, sai định dạng hoặc null.
2. **Parse và validate** để chuyển dữ liệu chưa đáng tin thành đối tượng hợp lệ. Ghi nhận lỗi dữ liệu bằng cấu trúc cụ thể như `DataProblem(field, code)`.
3. **Kiểm tra điều kiện thực thi** như trạng thái đơn hàng, quyền thao tác, quy tắc luồng. Trả phản hồi nghiệp vụ phù hợp nếu thao tác chưa được phép.
4. **Thực thi hành vi** khi mọi điều kiện thỏa; ở hệ thống có state/concurrency, cần bảo vệ tính nhất quán khi thay đổi trạng thái.
5. **Đổi kết quả ra giao thức ngoài**: ví dụ phản hồi API, thông điệp hoặc log. Phân biệt lỗi validation, conflict nghiệp vụ và lỗi hệ thống.

Pattern matching hữu ích ở **điểm phân nhánh theo kiểu**, nhưng nên tránh biến một `switch` thành nơi thực thi toàn bộ nghiệp vụ. Nếu kiểm tra validation hoặc chuyển trạng thái phức tạp, hãy trích thành hàm có tên rõ ràng để nhánh `case` diễn đạt ý nghĩa hơn là chứa hàng chục biểu thức.

### Mapping ra API là quyết định của ứng dụng

Ví dụ trong API HTTP, `DataProblem` có thể dẫn đến phản hồi 400 hoặc 422 tùy hợp đồng; `FlowProblem` do trạng thái không cho phép có thể dẫn đến 409, 403 hoặc một phản hồi nghiệp vụ riêng. **Không tồn tại ánh xạ HTTP bắt buộc của Java pattern matching**. Một lỗi hạ tầng hoặc bug không nên bị trả thành 400 chỉ vì nằm trong cùng `catch` với lỗi dữ liệu.

Nên ghi log có thông tin chẩn đoán về lỗi điều khiển/hạ tầng, nhưng không lộ stack trace hoặc thông tin nhạy cảm của hệ thống vào thông báo gửi cho người dùng.

## 11. Exception vẫn có vai trò, nhưng phải đúng tầng

Không có quy tắc “mọi lỗi đều phải là record kết quả”. Hãy phân biệt:

- **Validation đã dự đoán trước**: dùng `DataProblem` hoặc loại lỗi nghiệp vụ có cấu trúc giúp người gọi sửa input; có thể dùng exception validation riêng nếu đó là hợp đồng thống nhất của dự án.
- **Thao tác không hợp lệ theo trạng thái**: dùng `FlowProblem`, conflict hoặc domain exception theo giao thức, không trộn thành lỗi định dạng dữ liệu.
- **Bug và invariant nội bộ bị phá**: có thể dùng `IllegalStateException` hoặc exception phù hợp và để cơ chế xử lý lỗi tập trung ghi nhận. Đừng đổi thành `DataProblem` khiến hệ thống bỏ qua một bug.
- **Lỗi I/O, timeout, database, mạng**: phân loại theo tầng hạ tầng, có chiến lược retry/circuit breaker/observability khi phù hợp. Không suy ra payload sai chỉ từ một lỗi kết nối.
- **`NullPointerException` ngoài dự kiến**: thường là dấu hiệu đường code thiếu hợp đồng null hoặc vi phạm invariant. Không bắt toàn bộ rồi trả “thiếu dữ liệu” nếu chưa xác minh null thực sự đến từ request.

Ví dụ anti-pattern trong tầng xử lý:

~~~java
try {
    // Xử lý, gọi dịch vụ, thao tác object ...
} catch (Exception ex) {
    // SAI: mọi loại lỗi đều bị coi là payload sai.
    return new DataProblem("request", "invalid");
}
~~~

Đây là **mã giả minh họa**; không thể biên dịch độc lập do thiếu ngữ cảnh method. Nó che mất cả lỗi điều khiển, bug và hạ tầng. Thay vào đó, validate dữ liệu có chủ đích; catch chỉ **những ngoại lệ mà tầng này thực sự biết cách xử lý**, để ngoại lệ bất ngờ được ghi nhận đúng tầng.

## 12. Lỗi thường gặp khi kết hợp pattern với phân loại lỗi

**Lỗi 1 — dùng `default` để nuốt mọi lỗi.** Trong một `switch` trên `Object`, `default` có thể là nơi nhận loại lệnh không hỗ trợ, nhưng không phải bộ bắt tất cả exception và cũng không tự xử lý null selector. Hãy có `case null` hoặc bước kiểm tra null riêng.

**Lỗi 2 — gom lỗi thiếu field, sai trạng thái và lỗi hệ thống vào cùng thông báo “invalid”.** Người gọi không biết nên sửa payload hay thay đổi hành động. Tạo loại kết quả riêng và có mã lỗi rõ ràng.

**Lỗi 3 — đặt nhánh thành công trước nhánh guarded.** `case Pay(...)` bao quát đứng trước `case Pay(...) when ...` có thể che các nhánh validation và gây lỗi dominated hoặc logic không đến được.

**Lỗi 4 — nghĩ `var` là non-null.** `case Pay(var id, ...)` có thể tạo `id == null`. Hàm `blank(id)` trong ví dụ xử lý cả null và chuỗi trắng.

**Lỗi 5 — xem mọi loại thông điệp sai là lỗi luồng.** Ví dụ chọn như vậy vì đang mô phỏng protocol nội bộ. Trong một API nhận JSON thô, sai kiểu request có thể là lỗi dữ liệu. Phải xác định ranh giới và hợp đồng trước khi ánh xạ loại lỗi.

**Lỗi 6 — đổi `IllegalStateException` thành `DataProblem` khi catch rộng.** Vi phạm invariant nội bộ có thể là bug nghiêm trọng, không nên làm người dùng nghĩ họ gửi thiếu field.

**Lỗi 7 — trộn thứ tự ưu tiên lỗi mà không có test.** Với input vừa có payload sai vừa sai trạng thái, nhánh đứng trước quyết định kết quả. Test đa lỗi làm rõ chính sách ưu tiên.

**Lỗi 8 — dùng exception làm luồng bình thường của validation.** Không phải lúc nào cũng sai, nhưng có thể gây code khó theo dõi khi try/catch trải dài. Với lỗi đầu vào dự kiến và phổ biến, một kết quả typed thường dễ kiểm thử và vận hành hơn.

**Lỗi 9 — cho rằng `sealed` kiểm tra giá trị field.** `sealed Command` giới hạn subtype, nhưng không tự cấm `Pay(null, -1)`. Constructor, factory hoặc bước validation phải bảo vệ invariant dữ liệu.

**Lỗi 10 — quên cập nhật logic khi thêm subtype.** Với `switch` exhaustive không có `default`, compiler giúp phát hiện thiếu nhánh. Nhưng `switch` trên `Object` có `default` rộng có thể âm thầm nhận subtype mới dưới nhãn unsupported. Khi mở rộng giao thức, cần kiểm thử cả ranh giới đầu vào.

## 13. Checklist code review và bài tập

### Checklist

1. Mã có phân biệt **payload sai**, **thao tác/route sai trạng thái** và **lỗi ngoài dự kiến** không?
2. Giá trị `null` ở selector được xử lý theo hợp đồng hay chỉ tình cờ ném NPE?
3. Những field từ `var` hoặc record pattern có được kiểm tra null trước khi dereference?
4. Các nhánh `when` kiểm tra dữ liệu có đứng trước nhánh thành công tổng quát?
5. Nếu nhiều điều kiện cùng sai, **thứ tự ưu tiên lỗi** có được xác định và kiểm thử?
6. Có sử dụng catch quá rộng, vô tình biến bug và lỗi mạng thành lỗi dữ liệu?
7. Kết quả có kiểu rõ ràng, có thể phân biệt mà không phải parse chuỗi thông báo?
8. Những tình huống “unsupported type” đã được phân loại theo đúng ranh giới (public API hay protocol nội bộ)?
9. Tập subtype `sealed` có được cập nhật khi thêm variant mới và các `switch` exhaustive có được kiểm tra?
10. Có test cho null, chuỗi trắng, số biên, trạng thái cấm, kiểu lệnh khác và trường hợp nhiều lỗi đồng thời?

### Bài tập

- Thêm subtype `Refund(String orderId, int cents)` vào `Command`. Quan sát `kind(Command)` cần cập nhật nhánh nào để tiếp tục exhaustive, và xác định `handle(Object, Stage)` sẽ xử lý như thế nào trước khi bổ sung nhánh `Refund`.
- Đổi chính sách để **kiểm tra stage trước validation** đối với `Pay`. Cập nhật test `data-before-stage` thành kết quả mới và giải thích tác động tới thông tin lỗi người gọi nhận.
- Thêm `DataProblem("orderId", "too long")` khi mã đơn dài hơn 20 ký tự. Đặt guard ở đâu để không gọi `length()` trên null?
- Thử truyền `null` cho `kind(Command)`; so sánh cách từ chối tường minh bằng `Objects.requireNonNull` với `case null` khi muốn coi null là một kết quả nghiệp vụ.
- Viết một adapter trả mã lỗi riêng cho `DataProblem`, `FlowProblem` và exception ngoài dự kiến, không tạo ra `catch (Exception)` chung để đổi tất cả thành validation.

**Ghi nhớ:** Pattern matching giúp xác định **đây là loại lệnh nào**, guard giúp xác nhận **dữ liệu có hợp lệ không**, còn điều kiện trạng thái trả lời **lệnh có được phép chạy ở thời điểm này không**. Hãy biểu diễn các lý do thất bại bằng kiểu kết quả tách bạch, giữ thứ tự kiểm tra có chủ đích và không che lỗi lập trình/hạ tầng bằng một catch quá rộng.
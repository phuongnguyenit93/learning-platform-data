# Khi nào `sealed` phù hợp để mô hình hóa các loại giá trị trong Java 17+

## 1. Vấn đề thiết kế: một giá trị có thể thuộc một trong vài hình dạng

Không phải mọi dữ liệu đều có cùng một bộ trường. Kết quả thanh toán thành công có thể mang mã giao dịch; thất bại mang lý do từ chối; kết quả chờ xử lý mang thời điểm hẹn. Nếu cố đặt tất cả vào một class có nhiều trường nullable như `success`, `receiptId`, `error`, `retryAt`, bạn dễ tạo những trạng thái không hợp lệ: vừa có mã giao dịch vừa có lý do thất bại, hoặc `success=true` nhưng mã giao dịch lại null.

Một cách diễn đạt tốt hơn là: **một giá trị thuộc đúng một trong những biến thể có cấu trúc riêng**.

~~~java
sealed interface PaymentResult permits Approved, Declined {
}

record Approved(String receiptId) implements PaymentResult {
}

record Declined(String reason) implements PaymentResult {
}
~~~

Đây là ba **khai báo Java 17 hợp lệ**, không phải một chương trình có `main`. `PaymentResult` là kiểu chung; `Approved` và `Declined` là những **direct permitted implementations**. Mỗi biến thể có dữ liệu riêng và có thể được phân biệt bằng `instanceof` hoặc hành vi đa hình.

**`sealed` phù hợp khi tập các loại giá trị trực tiếp là một phần quan trọng của hợp đồng miền nghiệp vụ và bạn muốn chính thư viện/module sở hữu danh sách ấy.** Cần đặc biệt chú ý chữ **trực tiếp**: một nhánh `non-sealed` có thể mở lại việc mở rộng gián tiếp.

Bài thuộc **Java core – class-object**, nhóm **Lớp sealed**, mục **Khi nào sealed phù hợp để mô hình hóa các loại giá trị**. Nội dung tập trung vào **tiêu chí lựa chọn thiết kế**, không chỉ học thuộc cú pháp. Mọi chương trình độc lập bên dưới dùng **Java 17 trở lên**, không dùng tính năng preview; mã không hợp lệ được gắn nhãn riêng.

## 2. Mục tiêu học tập

Sau bài bạn sẽ:

1. Giải thích vì sao một kiểu tổng quát với nhiều trường nullable thường kém an toàn hơn các kiểu biến thể rõ ràng.
2. Xác định những dấu hiệu nên dùng **sealed interface + record variants**.
3. Phân biệt giới hạn **direct permitted subtypes** với việc đóng toàn bộ descendants.
4. Nhận biết khi `enum` đơn giản hơn `sealed`.
5. Chọn `sealed abstract class` nếu cần chia sẻ state, constructor hoặc implementation, thay vì bắt record extends class.
6. Chọn interface mở hoặc một `non-sealed` nhánh khi cần plugin/extension.
7. Mô hình hóa trạng thái, kết quả, lệnh, event hoặc cây cú pháp bằng các biến thể typed.
8. Biết trade-off khi thêm biến thể mới trong một API public.
9. Áp dụng `instanceof` type patterns trong Java 17, không nhầm với pattern `switch` được chuẩn hóa ở Java 21.
10. Hiểu rằng sealed không tự đảm bảo dữ liệu bất biến sâu, không-null, bảo mật hay tính đầy đủ của chuỗi `if`.
11. Thiết kế kiểm thử cho các variants, chuyển trạng thái và validation.
12. Lựa chọn giữa polymorphic method, visitor và type-dispatch theo nhu cầu.

## 3. Quy tắc ra quyết định ngắn gọn

Bạn có thể dùng bốn câu hỏi liên tiếp:

**A. Tập giá trị có ít loại và được kiểm soát từ cùng một domain/module không?** Nếu có, đây là dấu hiệu nghiêng về sealed. Nếu mọi bên ngoài đều cần tạo loại mới, một interface mở thường phù hợp hơn.

**B. Các loại có cấu trúc dữ liệu khác nhau không?** Nếu có `Success(data)`, `Failure(error)`, `Pending(retryAt)`, sealed interface + records giúp giữ mỗi payload đúng với loại. Nếu chỉ là một tập tên hằng `RED`, `GREEN`, `BLUE`, enum thường dễ hơn.

**C. Bạn có muốn callers buộc xử lý những biến thể đã biết không?** Closed hierarchy có thể giúp mô tả danh sách types rõ ràng; tuy nhiên **Java 17 không tự kiểm tra tính exhaustive của mọi chuỗi `if instanceof`**, và pattern matching `switch` cho hierarchy này chưa là tính năng ổn định không-preview ở Java 17.

**D. Có thật sự cần chia sẻ inheritance/state không?** Nếu các variants chủ yếu là payload records, chọn sealed interface. Nếu mỗi variant kế thừa logic và constructor base class, cân nhắc sealed class. Nếu chỉ cần chia sẻ hành vi thông thường mà không đóng mở rộng, interface bình thường có thể đủ.

Một dấu hiệu tốt của thiết kế là **ý nghĩa domain được nêu bằng tên type**, chứ không phải suy ra từ một cặp flag và nhiều field null.

## 4. Giá trị “một trong nhiều kiểu” và tổng kiểu (sum type)

Nhiều tài liệu gọi cách mô hình hóa trên là một kiểu gần với **algebraic data type — sum type**. Một `PaymentResult` có thể là `Approved` **hoặc** `Declined`; mỗi lựa chọn lại có trường riêng.

~~~text
PaymentResult
├── Approved(receiptId: String)
└── Declined(reason: String)
~~~

Không có biến thể `Approved` nhưng mang `reason` thay cho `receiptId` trừ khi bạn cố ý thiết kế type ấy như vậy. Những giá trị sai dạng có thể bị chặn ngay ở quá trình biên dịch hoặc constructor validation.

**Giới hạn chính xác:** một `sealed interface` chỉ xác định tập direct subtypes. Nếu một permitted child là `non-sealed`, một lượng không giới hạn hậu duệ gián tiếp có thể phát triển bên dưới nó. Để mô hình **đóng toàn bộ concrete variants**, hãy chọn leaf variants `final` (bao gồm records implicitly final) hoặc tiếp tục seal mọi nhánh cho tới leaves, và đừng thêm nhánh `non-sealed`.

## 5. Chương trình 1 — kết quả thanh toán có dữ liệu khác nhau

Tệp **`PaymentResultDemo.java`**:

~~~java
sealed interface PaymentResult permits Approved, Declined {
}

record Approved(String receiptId) implements PaymentResult {
    Approved {
        if (receiptId == null || receiptId.isBlank()) {
            throw new IllegalArgumentException("receiptId");
        }
    }
}

record Declined(String reason) implements PaymentResult {
    Declined {
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason");
        }
    }
}

public class PaymentResultDemo {
    static String explain(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "OK:" + approved.receiptId();
        }
        if (result instanceof Declined declined) {
            return "NO:" + declined.reason();
        }
        throw new IllegalArgumentException("unknown result");
    }

    public static void main(String[] args) {
        PaymentResult success = new Approved("TX-7");
        PaymentResult failure = new Declined("insufficient funds");
        System.out.println(explain(success));
        System.out.println(explain(failure));
        System.out.println("success type="
                + success.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PaymentResultDemo.java
java PaymentResultDemo
~~~

**Stdout:**

~~~text
OK:TX-7
NO:insufficient funds
success type=Approved
~~~

Ở biến thể Approved, constructor chỉ kiểm tra mã giao dịch. Ở Declined, constructor chỉ kiểm tra lý do thất bại. Chúng không phải giữ những field không áp dụng cho mình.

`instanceof Approved approved` là **pattern matching for instanceof** đã hoàn thiện trong Java 16, dùng ổn định trong Java 17. Nhánh `throw` nêu chính sách nếu có giá trị không được dự kiến, kể cả null. Compiler Java 17 không chứng minh chuỗi if này exhaustive chỉ nhờ `sealed`.

## 6. So sánh với “một class có thật nhiều trường nullable”

Thiết kế kém rõ:

~~~java
class PaymentResponse {
    boolean successful;
    String receiptId;
    String error;
}
~~~

Đây là class minh họa hợp lệ. Nó cho phép các trạng thái trái ý nghĩa:

- `successful=true` nhưng `receiptId=null`.
- `successful=false` nhưng `receiptId="TX-7"`.
- `successful=true` đồng thời `error="DECLINED"`.

Bạn có thể thêm constructor validation và factory methods để giảm lỗi; **sealed không phải cách duy nhất**. Tuy nhiên khi variants thực sự có **bộ fields khác nhau**, subtype riêng nói trực tiếp hợp đồng mà không cần quá nhiều quan hệ null/flag chéo.

| Câu hỏi | Một class có flags/null fields | Sealed với records |
| --- | --- | --- |
| Biến thể biểu diễn ở đâu? | Một field/flag | Kiểu concrete |
| Payload cho từng nhánh | Nhiều fields tùy chọn | Components của từng variant |
| Trạng thái sai dễ tạo không? | Có nếu thiếu invariant | Giảm mạnh lỗi sai dạng; vẫn cần validate |
| Mở rộng variants | Thường thêm flag và fields | Thêm permitted type, cập nhật consumers |
| Kiểu API | Một class | Interface/abstract class chung |
| Có hỗ trợ đa hình? | Có thể viết methods thủ công | Có thể áp dụng tự nhiên |
| Phù hợp với hệ thống mở cho plugin? | Tùy API | Sealed toàn bộ thường không thích hợp |

Quan trọng: `record` tự động cấp fields final nhưng **không tự từ chối null hoặc nội dung không hợp lệ**. Validation ở từng canonical constructor vẫn cần khi domain yêu cầu.

## 7. Khi chỉ là một tập giá trị tên cố định: chọn `enum`

Nếu trạng thái chỉ có vài hằng tên và **không cần payload riêng theo từng variant**, `enum` thường ngắn gọn hơn:

~~~java
enum OrderPhase {
    CREATED, PACKED, SHIPPED, DELIVERED
}
~~~

Enum cung cấp các constant instances, `values()`, `valueOf(...)` và hỗ trợ `switch` trên enum ổn định trong Java 17. So cùng hằng enum bằng `==`.

Một sealed hierarchy cho mỗi `Created`, `Packed`, `Shipped` dưới dạng empty record có thể là overengineering nếu mỗi biến thể **chỉ là một nhãn** và không có hành vi/payload khác biệt.

Ngược lại, nếu `Shipped` luôn cần `trackingCode` và `Delivered` cần `deliveredAt`, sealed variants có thể diễn đạt cấu trúc tốt hơn, vì enum constants không chứa những component values **riêng cho từng lần phát sinh sự kiện** theo cách record instances làm được.

Đừng coi enum và sealed là hai tính năng loại trừ nhau: một enum có thể là **một permitted direct implementor** của sealed interface khi mô hình cần.

## 8. Chương trình 2 — enum cho hằng, sealed cho kết quả có payload

Tệp **`EnumOrSealedDemo.java`**:

~~~java
enum JobStage {
    QUEUED, RUNNING, FINISHED
}

sealed interface UploadResult permits Uploaded, UploadFailed {
}

record Uploaded(String fileId, int size)
        implements UploadResult {
}

record UploadFailed(String reason)
        implements UploadResult {
}

public class EnumOrSealedDemo {
    public static void main(String[] args) {
        JobStage stage = JobStage.RUNNING;
        UploadResult result = new Uploaded("file-1", 12);

        System.out.println("stage=" + stage);
        System.out.println("is running="
                + (stage == JobStage.RUNNING));
        System.out.println("result=" + result);
        System.out.println("failed="
                + (result instanceof UploadFailed));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumOrSealedDemo.java
java EnumOrSealedDemo
~~~

**Stdout:**

~~~text
stage=RUNNING
is running=true
result=Uploaded[fileId=file-1, size=12]
failed=false
~~~

`JobStage` biểu diễn tên trạng thái cố định. `Uploaded` là một **object riêng của lần upload cụ thể**, mang file ID và size. Không nên ép các dữ liệu đó vào global enum instance rồi mutate fields vì enum constants tồn tại như các đối tượng được chia sẻ.

## 9. Các biến thể có payload khác kiểu là tín hiệu mạnh của sealed

Nhiều hệ thống có cùng “loại kết quả chung” nhưng payload khác:

- `Authenticated(userId)` hoặc `Unauthorized(reason)`.
- `Found(value)` hoặc `NotFound(key)`.
- `FileCreated(path, bytes)` hoặc `FileRejected(code)`.
- `Circle(radius)` hoặc `Rectangle(width, height)`.
- `Add(left, right)` hoặc `Literal(value)` trong AST.

Ở đây việc có nhiều constructors cùng các tham số khác nhau **không tự động tạo subtype rõ**. Nếu tất cả đều vào một class, callers có thể phải kiểm tra `kind` trước khi đọc fields và phải xử lý những field không áp dụng.

Sealed variants làm kiểu của từng payload cụ thể hơn. Điều này đặc biệt có ích khi giá trị đi qua nhiều layers: controller → service → processor → renderer.

**Nhưng** nếu API chỉ cần một field `status` và mọi payload đều có cùng cấu trúc, không cần sealed bằng mọi giá. Dùng record thường hoặc enum cho điều đơn giản.

## 10. Chương trình 3 — thông báo khác payload theo kênh

Tệp **`NotificationVariantsDemo.java`**:

~~~java
sealed interface Notification permits EmailNotice, SmsNotice {
}

record EmailNotice(String email, String subject)
        implements Notification {
    EmailNotice {
        if (email == null || subject == null) {
            throw new IllegalArgumentException("missing email data");
        }
    }
}

record SmsNotice(String number, String text)
        implements Notification {
    SmsNotice {
        if (number == null || text == null) {
            throw new IllegalArgumentException("missing sms data");
        }
    }
}

public class NotificationVariantsDemo {
    static String route(Notification item) {
        if (item instanceof EmailNotice email) {
            return "email:" + email.email()
                    + ":" + email.subject();
        }
        if (item instanceof SmsNotice sms) {
            return "sms:" + sms.number()
                    + ":" + sms.text();
        }
        throw new IllegalArgumentException("unsupported");
    }

    public static void main(String[] args) {
        Notification a =
                new EmailNotice("a@example.test", "Hello");
        Notification b = new SmsNotice("123", "Ready");
        System.out.println(route(a));
        System.out.println(route(b));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NotificationVariantsDemo.java
java NotificationVariantsDemo
~~~

**Stdout:**

~~~text
email:a@example.test:Hello
sms:123:Ready
~~~

Mỗi record chỉ có fields cần cho kênh của nó. Validation tránh null trong ví dụ nhưng không tuyên bố email/phone format đã được xác thực. Các rules validation thực tế là domain-specific.

**Cân nhắc:** nếu Notification là một plugin framework mà bên thứ ba phải tự thêm kênh mới, sealed toàn bộ có thể trở thành trở ngại. Trong trường hợp ấy, interface mở hoặc một extension branch là lựa chọn đúng hơn.

## 11. Khi danh sách trực tiếp cần được sở hữu và kiểm soát

Một trong những lý do quan trọng nhất của sealed là **ai được quyền mở rộng tập biến thể**.

~~~java
sealed interface DomainEvent permits CreatedEvent, DeletedEvent {
}

record CreatedEvent(String id) implements DomainEvent {
}

record DeletedEvent(String id) implements DomainEvent {
}
~~~

Các declarations hợp lệ. Đây là hợp đồng cho phép chỉ hai kiểu **trực tiếp** triển khai DomainEvent. Một module bên ngoài không thể tự ý `implements DomainEvent` để tạo direct subtype mới ngoài danh sách.

Điều này phù hợp khi danh sách biến thể phải được review cùng với **schema, validation, serialization và xử lý downstream**. Nó không phù hợp khi mục tiêu của DomainEvent là cung cấp một hook mà khách hàng tùy ý định nghĩa kiểu mới.

Một sealed hierarchy là một quyết định **governance đối với type system**, không đơn thuần là cú pháp ngắn. Quyền kiểm soát direct types nằm ở nơi định nghĩa sealed type và các permitted types của nó theo giới hạn module/package.

## 12. “Đóng các con trực tiếp” khác “đóng mọi hậu duệ”

Ví dụ:

~~~java
sealed interface Task permits BuiltInTask, PluginTask {
}

record BuiltInTask(String name) implements Task {
}

non-sealed interface PluginTask extends Task {
}
~~~

`BuiltInTask` là record implicitly final. `PluginTask` là permitted subinterface nhưng **non-sealed**, nghĩa là những implementation khác của PluginTask có thể được khai báo theo luật Java thông thường.

Nếu `SpecialTask implements PluginTask`, nó là subtype gián tiếp của Task, **không cần** xuất hiện trong `Task permits ...`.

~~~text
          Task (sealed)
           /         \
 BuiltInTask      PluginTask (non-sealed)
    (final)             |
                     SpecialTask
                        |
                      ...mở...
~~~

Khi bạn muốn “mọi giá trị Task chỉ có hai dạng concrete tuyệt đối”, `non-sealed` branch sẽ làm **mất tính đóng đó**. Khi bạn muốn “hai họ Task trực tiếp, trong đó có một họ dành cho plugin”, non-sealed lại là một công cụ hữu ích.

## 13. Chương trình 4 — mô hình vừa đóng vừa mở có chủ đích

Tệp **`ExtensionPointDemo.java`**:

~~~java
sealed interface ReportItem permits TextItem, ExternalItem {
    String render();
}

record TextItem(String text) implements ReportItem {
    @Override
    public String render() {
        return "text:" + text;
    }
}

non-sealed interface ExternalItem extends ReportItem {
}

final class PluginItem implements ExternalItem {
    @Override
    public String render() {
        return "plugin";
    }
}

public class ExtensionPointDemo {
    public static void main(String[] args) {
        ReportItem first = new TextItem("core");
        ReportItem second = new PluginItem();

        System.out.println(first.render());
        System.out.println(second.render());
        System.out.println("plugin is ReportItem="
                + (second instanceof ReportItem));
        System.out.println("plugin directly implements="
                + PluginItem.class.getInterfaces()[0]
                        .getSimpleName());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ExtensionPointDemo.java
java ExtensionPointDemo
~~~

**Stdout:**

~~~text
text:core
plugin
plugin is ReportItem=true
plugin directly implements=ExternalItem
~~~

`ReportItem` chỉ permits hai direct subtypes: TextItem và ExternalItem. PluginItem không trực tiếp implements ReportItem, mà trực tiếp implements ExternalItem.

**Ứng dụng:** sealed root vẫn công khai rằng giá trị là built-in text hoặc thuộc họ external extension. Nhưng bạn không còn được giả định **chỉ có hai concrete runtime classes**.

## 14. Khi có cây các biểu thức, lệnh hoặc node AST

Sealed đặc biệt phù hợp với một **abstract syntax tree (AST)** hoặc cấu trúc dữ liệu đệ quy có tập loại node được định nghĩa trong một ngôn ngữ nhỏ:

~~~text
Expression (sealed)
├── NumberLiteral(value)
├── Addition(left, right)
└── Multiplication(left, right)
~~~

Mỗi node có components khác nhau; tất cả cùng là Expression. Các node lại có thể chứa những Expression khác, tạo cây nhiều tầng.

Tập direct permitted node types có thể tương đối ổn định do grammar kiểm soát. Dạng sealed + record giúp code parser, evaluator, pretty printer và unit tests phân biệt rõ node kinds.

Nếu grammar do plugin authors mở rộng tự do, một sealed root đóng toàn bộ có thể gây khó khăn. Khi đó hãy cân nhắc extension AST API hoặc định nghĩa thêm một non-sealed extension node family.

## 15. Chương trình 5 — AST dùng sealed và records

Tệp **`ExpressionTreeDemo.java`**:

~~~java
sealed interface Expr permits Num, Add, Multiply {
    int eval();
}

record Num(int value) implements Expr {
    @Override
    public int eval() {
        return value;
    }
}

record Add(Expr left, Expr right) implements Expr {
    @Override
    public int eval() {
        return left.eval() + right.eval();
    }
}

record Multiply(Expr left, Expr right) implements Expr {
    @Override
    public int eval() {
        return left.eval() * right.eval();
    }
}

public class ExpressionTreeDemo {
    public static void main(String[] args) {
        Expr tree = new Multiply(
                new Add(new Num(2), new Num(3)),
                new Num(4));

        System.out.println("value=" + tree.eval());
        System.out.println("is Multiply="
                + (tree instanceof Multiply));
        System.out.println("left is Add="
                + (((Multiply) tree).left() instanceof Add));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExpressionTreeDemo.java
java ExpressionTreeDemo
~~~

**Stdout:**

~~~text
value=20
is Multiply=true
left is Add=true
~~~

Sealed giữ tập node types trực tiếp, record mô tả fields theo từng node, còn `eval()` dùng dynamic dispatch. Không cần một `switch` trên kiểu runtime để tính toán vì behavior đã được đặt đúng trong mỗi variant.

Vì records có component references `left`/`right`, cần validation riêng nếu AST không chấp nhận null. Chương trình giả định cây đầu vào được tạo đúng; sealed **không tự bảo vệ against null children hoặc vòng tham chiếu** trong một mô hình có mutable references.

## 16. Sealed interface + record là cặp phù hợp cho value variants

**Sealed interface** chỉ định “những loại giá trị nào được công nhận”; **record** chỉ định “mỗi loại mang những components nào”.

Ví dụ:

~~~java
sealed interface ValidationResult permits Valid, Invalid {
}

record Valid(String normalizedValue)
        implements ValidationResult {
}

record Invalid(String message)
        implements ValidationResult {
}
~~~

Records là implicitly final, nên không cần khai `final record` (cú pháp này cũng không phải cách viết dành cho records). Họ không thể extends một custom sealed class, vì record **luôn extends `java.lang.Record`**. Do đó kết hợp **sealed interface** thường linh hoạt nhất.

Records tự cung cấp canonical constructor, accessors, equality, hash và toString theo components. Nhưng bạn vẫn phải kiểm tra null/range, có thể dùng compact constructor để normalize/copy inputs.

**Không đồng nhất records với deep immutability:** nếu record giữ `List<MutableItem>`, các objects reachable bên trong vẫn có thể thay đổi trừ khi bạn thiết kế defensive copying.

## 17. Chương trình 6 — kết quả tìm kiếm có hoặc không có dữ liệu

Tệp **`LookupResultDemo.java`**:

~~~java
sealed interface LookupResult permits Found, NotFound, LookupError {
}

record Found(String value) implements LookupResult {
    Found {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
    }
}

record NotFound() implements LookupResult {
}

record LookupError(String reason) implements LookupResult {
}

public class LookupResultDemo {
    static String text(LookupResult result) {
        if (result instanceof Found found) {
            return "found:" + found.value();
        }
        if (result instanceof NotFound) {
            return "missing";
        }
        if (result instanceof LookupError error) {
            return "error:" + error.reason();
        }
        throw new IllegalArgumentException("unsupported");
    }

    public static void main(String[] args) {
        System.out.println(text(new Found("Java")));
        System.out.println(text(new NotFound()));
        System.out.println(text(new LookupError("timeout")));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LookupResultDemo.java
java LookupResultDemo
~~~

**Stdout:**

~~~text
found:Java
missing
error:timeout
~~~

`NotFound()` là một **record không có components**, hợp lệ khi kiểu dữ liệu chỉ cần báo một biến thể. `LookupError` mang lý do lỗi; `Found` mang dữ liệu đã tìm thấy. Thiết kế tránh việc `null` đại diện đồng thời cho “không tìm thấy” lẫn “lỗi”.

Nếu API trả `Optional<T>` chỉ để mô tả có/không có một value và không có trường hợp lỗi domain riêng, Optional có thể đơn giản hơn cả sealed hierarchy.

## 18. Khi nên dùng `Optional<T>` thay vì sealed

`Optional<T>` mô tả một kết quả có **giá trị hoặc không có giá trị**, không phải một hệ thống phân loại lỗi chi tiết.

- Nếu tìm key trong cache và không tìm thấy là tình huống bình thường, `Optional<Value>` có thể hợp lý.
- Nếu cần phân biệt NotFound, PermissionDenied, TemporarilyUnavailable và Found(payload), một sealed result hierarchy thể hiện nhiều outcomes chính xác hơn.
- Nếu method có thể ném một exception bất thường, không nhất thiết cần đưa mọi checked/unchecked exception vào sealed results; còn phụ thuộc API convention.
- Nếu code đã dùng `null` có mục đích khác với “vắng mặt”, cần thống nhất semantics trước khi đổi thiết kế.

Chọn dựa trên **số outcome mang ý nghĩa**, không dựa vào độ phức tạp hình thức. `Optional` không phải thay thế đầy đủ của mọi result type, còn sealed không phải bắt buộc cho một phép lookup đơn giản.

## 19. Khi một biến thể cần logic hoặc state chung từ superclass

Sealed interface phù hợp với records, nhưng đôi khi các variants cần một **constructor base**, fields chung, protected helpers hoặc shared implementation. Khi ấy, một `sealed abstract class` là lựa chọn khả thi:

~~~java
abstract sealed class Shape permits Square, Rectangle {
    private final String label;

    Shape(String label) {
        this.label = label;
    }

    final String label() {
        return label;
    }

    abstract int areaUnits();
}
~~~

Hai subclasses `Square` và `Rectangle` sẽ phải extends Shape và chọn `final`/`sealed`/`non-sealed`. Trái lại, records **không được** extends Shape vì record có superclass cố định là Record.

Nếu shared state chỉ là dữ liệu mà mỗi variant có thể lưu riêng trong record components, sealed interface có thể ít inheritance coupling hơn. Đừng xây abstract superclass chỉ để tiết kiệm hai dòng khai báo field nếu điều đó làm domain phức tạp.

## 20. Chương trình 7 — sealed abstract class có shared constructor

Tệp **`SealedShapeDemo.java`**:

~~~java
abstract sealed class Shape permits Square, Rectangle {
    private final String label;

    Shape(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label");
        }
        this.label = label;
    }

    final String label() {
        return label;
    }

    abstract int areaUnits();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        super("square");
        if (side <= 0) {
            throw new IllegalArgumentException("side");
        }
        this.side = side;
    }

    @Override
    int areaUnits() {
        return side * side;
    }
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        super("rectangle");
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    int areaUnits() {
        return width * height;
    }
}

public class SealedShapeDemo {
    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 4);

        System.out.println(a.label() + "=" + a.areaUnits());
        System.out.println(b.label() + "=" + b.areaUnits());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SealedShapeDemo.java
java SealedShapeDemo
~~~

**Stdout:**

~~~text
square=9
rectangle=8
~~~

Base class chứa invariant cho label; mỗi subclass có dữ liệu và validation riêng. Sealed kiểm soát tập subclasses trực tiếp, còn `abstract` cấm tạo object Shape không thuộc một variant cụ thể.

**Lưu ý:** một `sealed class` **không mặc nhiên abstract**. Nếu base concrete và constructor accessible, `new Base()` có thể hợp lệ. Hãy thêm abstract khi bạn thực sự cần cấm instance trực tiếp của khái niệm tổng quát.

## 21. Trạng thái workflow: sealed tốt khi các trạng thái mang dữ liệu riêng

Một trạng thái công việc đơn giản như `CREATED`, `RUNNING`, `DONE` có thể chỉ cần enum. Nhưng nếu:

- `CartOpen` mang danh sách mặt hàng;
- `AwaitingPayment` mang mã yêu cầu và số tiền;
- `Completed` mang mã hóa đơn;
- `Cancelled` mang lý do;

thì sealed variants giúp mỗi trạng thái bắt buộc mang payload tương ứng.

Một lợi ích là **không còn “đọc sai field”**: `Completed` có `receiptId()`, còn `CartOpen` không có method đó. Java compiler yêu cầu kiểm tra hoặc chuyển kiểu khi cần truy cập thông tin riêng từng variant.

Tuy nhiên, sealed **không tự quản lý transitions**. Bạn vẫn phải thiết kế method chuyển trạng thái phù hợp và kiểm tra transition hợp lệ. Một caller vẫn có thể trực tiếp tạo `Completed` nếu constructor được công bố; nếu domain đòi bảo vệ lifecycle nghiêm ngặt, cần kiểm soát factory/service, visibility và authentication riêng.

## 22. Chương trình 8 — biến thể trạng thái với transition rõ ràng

Tệp **`CheckoutStateDemo.java`**:

~~~java
sealed interface CheckoutState
        permits CartOpen, AwaitingPayment, Completed, Cancelled {
}

record CartOpen(int items) implements CheckoutState {
    CartOpen {
        if (items < 0) {
            throw new IllegalArgumentException("items");
        }
    }
}

record AwaitingPayment(String orderId)
        implements CheckoutState {
}

record Completed(String receiptId) implements CheckoutState {
}

record Cancelled(String reason) implements CheckoutState {
}

public class CheckoutStateDemo {
    static CheckoutState requestPayment(CheckoutState current) {
        if (current instanceof CartOpen cart && cart.items() > 0) {
            return new AwaitingPayment("ORD-1");
        }
        throw new IllegalStateException("cannot request payment");
    }

    static CheckoutState confirm(CheckoutState current) {
        if (current instanceof AwaitingPayment) {
            return new Completed("R-1");
        }
        throw new IllegalStateException("cannot confirm");
    }

    public static void main(String[] args) {
        CheckoutState current = new CartOpen(2);
        System.out.println("start=" + current);

        current = requestPayment(current);
        System.out.println("pending=" + current);

        current = confirm(current);
        System.out.println("done=" + current);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CheckoutStateDemo.java
java CheckoutStateDemo
~~~

**Stdout:**

~~~text
start=CartOpen[items=2]
pending=AwaitingPayment[orderId=ORD-1]
done=Completed[receiptId=R-1]
~~~

Transition methods chỉ chấp nhận những runtime variants có ý nghĩa. Sealed làm các loại trạng thái rõ ràng, nhưng việc quyết định **ai được chuyển** và **khi nào chuyển** vẫn thuộc business logic. Trong code production, các identifiers không nên cố định như ví dụ; dữ liệu giao dịch và concurrency phải được quản lý đúng domain.

## 23. `final`, `sealed`, `non-sealed` quyết định mức đóng của cây

Direct permitted subtype phải xác định hướng mở rộng:

| Kiểu con được phép | Kết quả |
| --- | --- |
| `final class Leaf extends Parent` | Không cho subclass của Leaf |
| `record Leaf(...) implements Parent` | Record implicitly final |
| `sealed class Branch extends Parent permits ...` | Tiếp tục kiểm soát direct children của Branch |
| `sealed interface Branch extends Parent permits ...` | Tiếp tục kiểm soát direct subtypes của Branch |
| `non-sealed class Branch extends Parent` | Mở lại subclassing dưới Branch |
| `non-sealed interface Branch extends Parent` | Mở lại extension dưới Branch |

Một direct permitted child thông thường **không được** chỉ viết `class Child extends SealedParent` và bỏ hết ba lựa chọn này. Compiler yêu cầu quyết định mở rộng rõ.

`non-sealed` cũng **không** phải modifier áp cho class tùy ý; nó chỉ hợp lệ trong quan hệ với một sealed direct supertype tương ứng.

Nếu mọi concrete leaves là final và mọi intermediate branches tiếp tục sealed, hierarchy mới đúng nghĩa là **closed collection of concrete variants**. Nếu một nhánh non-sealed xuất hiện, chỉ danh sách direct children ở cha vẫn đóng, còn descendants ở nhánh kia có thể mở.

## 24. Cây nhiều cấp và variants có phân nhóm

Một domain có thể cần chia làm các họ:

~~~text
Event (sealed)
├── UserEvent (sealed)
│   ├── UserCreated (record)
│   └── UserDeleted (record)
└── SystemEvent (sealed)
    ├── Started (record)
    └── Stopped (record)
~~~

Nếu `Event` trực tiếp permits `UserEvent` và `SystemEvent`, nó **không cần** permits từng leaf. Mỗi subtype `UserCreated` phải trực tiếp implements `UserEvent` (và như vậy gián tiếp là Event) theo mã khai báo.

Đây là cách tổ chức tốt khi phân nhóm phản ánh khái niệm thật; nhưng cũng tăng số levels của model. Với ba variants đơn giản, một sealed interface trực tiếp permits ba records thường dễ đọc hơn.

**Nguyên tắc:** không xây nhiều tầng chỉ để “khóa tất cả”. Mỗi tầng nên có ích cho API, hành vi hoặc cấu trúc domain.

## 25. Chương trình 9 — hierarchy hai tầng

Tệp **`EventFamiliesDemo.java`**:

~~~java
sealed interface Event permits UserEvent, SystemEvent {
}

sealed interface UserEvent extends Event
        permits UserCreated, UserDeleted {
}

sealed interface SystemEvent extends Event
        permits Started, Stopped {
}

record UserCreated(String id) implements UserEvent {
}

record UserDeleted(String id) implements UserEvent {
}

record Started() implements SystemEvent {
}

record Stopped() implements SystemEvent {
}

public class EventFamiliesDemo {
    static String family(Event event) {
        if (event instanceof UserEvent) {
            return "user";
        }
        if (event instanceof SystemEvent) {
            return "system";
        }
        throw new IllegalArgumentException("unknown");
    }

    public static void main(String[] args) {
        Event a = new UserCreated("U1");
        Event b = new Started();

        System.out.println("a=" + family(a));
        System.out.println("b=" + family(b));
        System.out.println("a UserEvent="
                + (a instanceof UserEvent));
        System.out.println("b SystemEvent="
                + (b instanceof SystemEvent));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EventFamiliesDemo.java
java EventFamiliesDemo
~~~

**Stdout:**

~~~text
a=user
b=system
a UserEvent=true
b SystemEvent=true
~~~

`Event` chỉ permits hai subinterfaces trực tiếp; từng subinterface giới hạn leaf records riêng. Java 17 cho phép `instanceof` đối với interface hierarchy này mà không bật preview.

Mô hình nhiều tầng phù hợp khi consumers cần thường xuyên hỏi “user-related hay system-related” trước khi xử lý subtype cụ thể.

## 26. Quy tắc vị trí: named module và unnamed module

Sealed hierarchy bị ràng buộc bởi boundary Java:

- Trong một **named module**, mọi direct permitted subclasses/subinterfaces của sealed type phải nằm trong **cùng named module**. Chúng có thể ở những packages khác nhau trong module nếu Java accessibility và dependencies cho phép.
- Trong **unnamed module**, các permitted direct subtypes phải nằm trong **cùng package**.
- Nếu không ghi `permits`, compiler chỉ có thể suy ra permitted direct subtypes từ **cùng compilation unit** theo điều kiện JLS.
- Khai `permits` tường minh thường dễ bảo trì khi type hierarchy trải nhiều files.

Tất cả ví dụ runnable ở đây đặt các declarations cùng một file, không có package, để đơn giản hóa `javac`. Đây không phải chỉ dẫn rằng mọi dự án phải tổ chức một hierarchy trong một file.

Sealed **không cho phép một plugin ở module khác trực tiếp implement root** chỉ vì root là public. Nếu API cần extension từ bên ngoài, cân nhắc interface mở hoặc một permitted non-sealed extension point.

## 27. Khả năng tiến hóa API: thêm một variant là thay đổi có ý nghĩa

Giả sử ban đầu có `sealed interface Outcome permits Success, Failure`. Khi bạn thêm một `Pending` vào permits:

- Những callers đã được viết theo giả định “chỉ Success hoặc Failure” phải được rà soát.
- Serializer/JSON polymorphic mapping có thể phải hiểu discriminator mới.
- Các policies, metrics, logs hoặc UI có thể cần xử lý Pending.
- Các unit tests và integration tests phải cập nhật.
- Nếu clients dùng Java 17 và chuỗi `if instanceof`, compiler không tự bắt tất cả call sites bỏ sót một nhánh.
- Với API được dùng giữa các modules/libraries, cần xem xét binary/source compatibility và quy trình rebuild.

Nếu domain thực sự có tập variant được quản trị tập trung, việc buộc một thay đổi rõ như vậy là **lợi ích của sealed**. Nếu những variants mới xuất hiện liên tục do người dùng bên ngoài sáng tạo, sealed lại gây chi phí không cần thiết.

**Không sử dụng `default` hoặc nhánh `else` chỉ để “nuốt” mọi variant lạ** nếu hệ thống bắt buộc xử lý chính xác từng biến thể. Khi chưa hỗ trợ loại mới, fail-fast có thể an toàn hơn một kết quả mặc định sai nghiệp vụ.

## 28. Xử lý variants trong Java 17: đa hình trước, type tests khi cần

Có hai phong cách cơ bản:

**Đa hình:** đặt một method chung trên sealed interface và triển khai tại mỗi variant.

~~~java
sealed interface Message permits PlainText, ImportantText {
    String display();
}
~~~

Mỗi variant có `display()`, caller chỉ gọi `message.display()`. Lợi ích: nếu thêm một permitted type mới, class đó phải hiện thực các abstract methods của interface để biên dịch; loại bỏ bớt type-dispatch ở consumers.

**Type tests:** callers cần logic riêng theo ngữ cảnh, chẳng hạn UI và audit có cách diễn giải khác nhau:

~~~java
if (message instanceof PlainText text) {
    // xử lý payload của PlainText trong ngữ cảnh này
}
~~~

Đây là snippet hợp lệ với biến message kiểu Message và record PlainText phù hợp.

Không nên cố ép mọi behavior lên variant types nếu phụ thuộc dữ liệu/service của tầng ứng dụng: đôi khi visitor hoặc service renderer bên ngoài tốt hơn. Ngược lại, không cần viết 15 chuỗi instanceof giống nhau nếu polymorphic method đã thể hiện đúng ý nghĩa.

## 29. Chương trình 10 — polymorphism loại bỏ type-switch

Tệp **`SealedBehaviorDemo.java`**:

~~~java
sealed interface Message permits PlainText, ImportantText {
    String display();
}

record PlainText(String value) implements Message {
    @Override
    public String display() {
        return value;
    }
}

record ImportantText(String value) implements Message {
    @Override
    public String display() {
        return "IMPORTANT:" + value;
    }
}

public class SealedBehaviorDemo {
    public static void main(String[] args) {
        Message a = new PlainText("hello");
        Message b = new ImportantText("save");

        System.out.println(a.display());
        System.out.println(b.display());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedBehaviorDemo.java
java SealedBehaviorDemo
~~~

**Stdout:**

~~~text
hello
IMPORTANT:save
~~~

Cả hai implementations là records implicitly final. Caller không cần biết biến Message đang giữ runtime variant nào; dynamic dispatch chọn method phù hợp.

Đây là giải pháp tốt khi method là **hành vi nội tại của variant**, không có dependency vào resource bên ngoài.

## 30. Pattern switch trong Java 17: phân biệt tính năng ổn định và preview

Java 17 đã có **pattern matching for `instanceof`** dưới dạng chuẩn:

~~~java
if (result instanceof Approved approved) {
    System.out.println(approved.receiptId());
}
~~~

Đoạn này hợp lệ trong method có result kiểu PaymentResult từ ví dụ.

Nhưng cú pháp kiểu:

~~~java
// KHÔNG PHẢI mã không-preview ổn định trong Java 17:
// return switch (result) {
//     case Approved a -> a.receiptId();
//     case Declined d -> d.reason();
// };
~~~

không được sử dụng như tính năng chuẩn không-preview của Java 17. Pattern matching for switch trải qua các bản preview và trở thành tính năng chính thức trong **Java 21 (JEP 441)**.

**Vì vậy:**
- Học/viết code Java 17 mặc định: dùng `if instanceof`, polymorphism hoặc visitor.
- Không quảng bá `switch` trên sealed interface như cú pháp tiêu chuẩn của Java 17.
- Nếu dự án dùng release có hỗ trợ pattern switch ổn định, có thể tận dụng exhaustiveness trên sealed hierarchies theo rules của release đó.
- Đừng suy rằng Java 17 compiler tự kiểm tra exhaustive cho bất kỳ chuỗi `if instanceof` nào.

Thận trọng phiên bản là một phần của thiết kế library lâu dài, nhất là khi build target vẫn là Java 17.

## 31. Với nhiều thao tác độc lập, cân nhắc visitor

Nếu variants ổn định nhưng có nhiều phép xử lý mới xuất hiện (render, serialize, metrics, validation...), một **visitor** có thể tập trung các overloads theo variant mà không phải đặt mọi business method vào records.

Ví dụ giao diện ý tưởng:

~~~java
interface OutcomeVisitor<R> {
    R onApproved(Approved value);
    R onDeclined(Declined value);
}
~~~

Các loại Approved/Declined giả định là records từ ví dụ đầu. Một method `accept` do interface/variants tự triển khai có thể gọi đúng overload, giúp tránh duplicate instanceof chains trong consumers.

Trade-off:
- Thêm **phép xử lý** mới dễ bằng một visitor implementation mới.
- Thêm **variant** mới khiến các visitor interfaces/implementations cần cập nhật.
- Với 2 variants, một lần xử lý, visitor có thể rườm rà.
- Với 20 variants và nhiều thao tác riêng, visitor có thể giúp các đường code được tổ chức rõ.

Đây là lựa chọn API design, không phải một yêu cầu của `sealed`.

## 32. Chương trình 11 — visitor cho sealed value variants

Tệp **`SealedVisitorDemo.java`**:

~~~java
interface ResultVisitor<R> {
    R success(Success value);
    R failure(Failure value);
}

sealed interface Result permits Success, Failure {
    <R> R accept(ResultVisitor<R> visitor);
}

record Success(String text) implements Result {
    @Override
    public <R> R accept(ResultVisitor<R> visitor) {
        return visitor.success(this);
    }
}

record Failure(String message) implements Result {
    @Override
    public <R> R accept(ResultVisitor<R> visitor) {
        return visitor.failure(this);
    }
}

public class SealedVisitorDemo {
    public static void main(String[] args) {
        ResultVisitor<String> renderer =
                new ResultVisitor<>() {
                    @Override
                    public String success(Success value) {
                        return "OK:" + value.text();
                    }

                    @Override
                    public String failure(Failure value) {
                        return "NO:" + value.message();
                    }
                };

        Result a = new Success("saved");
        Result b = new Failure("denied");
        System.out.println(a.accept(renderer));
        System.out.println(b.accept(renderer));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedVisitorDemo.java
java SealedVisitorDemo
~~~

**Stdout:**

~~~text
OK:saved
NO:denied
~~~

Visitor định nghĩa hai methods tách biệt cho hai variants; mỗi record gọi đúng method trong `accept`. `Result` là sealed interface, nhưng **không phải functional interface**, nên bạn không thể trực tiếp gán một lambda cho Result.

Chú ý Java generic method `<R> R accept(...)` là hợp lệ trong interface và được override bởi records; Java 17 không cần preview.

## 33. Vì sao sealed interface không dùng trực tiếp làm lambda target?

Một `sealed interface` với một abstract method **không được xem là functional interface** theo JLS 17.

~~~java
sealed interface Operation permits NamedOperation {
    void execute();
}

final class NamedOperation implements Operation {
    @Override
    public void execute() {
        System.out.println("named");
    }
}
~~~

Các khai báo hợp lệ. Đoạn dưới đây **cố ý không biên dịch** nếu đặt trong method:

~~~java
// Operation op = () -> System.out.println("lambda");
~~~

Vì Operation là sealed, `lambda` không phải permitted direct implementing class được khai báo. Java cố ý loại sealed interface khỏi các kiểu target functional interface.

Nếu ứng dụng cần callbacks có thể do callers tạo tùy ý, dùng một interface `@FunctionalInterface` không sealed riêng, như `Runnable`, `Consumer<T>`, `Function<T,R>`. Chỉ sealed các domain value types nếu tập biến thể thực sự được chủ sở hữu kiểm soát.

Điểm này là một tiêu chí **“không nên dùng sealed”** rất thực tế.

## 34. Tính bất biến và hợp đồng dữ liệu: sealed không đủ

`sealed` không làm variants bất biến. Kể cả `record` cũng chỉ bảo đảm component fields final, không deep freeze object graph:

~~~java
sealed interface CatalogResult permits Items, CatalogError {
}

record Items(java.util.List<String> values)
        implements CatalogResult {
}

record CatalogError(String reason)
        implements CatalogResult {
}
~~~

Đây là các declarations hợp lệ. Nếu Items nhận một `ArrayList<String>` mutable, caller có thể tiếp tục sửa list qua reference ban đầu hoặc `items.values()`.

Nếu API hứa value snapshot, hãy copy trong compact canonical constructor:

~~~java
record Items(java.util.List<String> values)
        implements CatalogResult {
    Items {
        values = java.util.List.copyOf(values);
    }
}
~~~

Đây là **phiên bản thay thế** cho khai báo Items phía trên, không ghép hai versions vào cùng compilation unit.

`List.copyOf` tạo unmodifiable structural snapshot nhưng không deep-copy mutable elements. Do đó sealed + record + copyOf chỉ bảo đảm một mức bất biến phù hợp với **kiểu elements** và **mức graph được thiết kế**.

## 35. Chương trình 12 — sealed với record snapshot

Tệp **`SealedSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

sealed interface CatalogResult permits Items, CatalogError {
}

record Items(List<String> values) implements CatalogResult {
    Items {
        values = List.copyOf(values);
    }
}

record CatalogError(String reason) implements CatalogResult {
}

public class SealedSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        CatalogResult result = new Items(source);
        source.add("B");

        if (result instanceof Items items) {
            System.out.println("stored=" + items.values());
            try {
                items.values().add("C");
            } catch (UnsupportedOperationException ex) {
                System.out.println("unmodifiable=true");
            }
        }

        System.out.println("source=" + source);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SealedSnapshotDemo.java
java SealedSnapshotDemo
~~~

**Stdout:**

~~~text
stored=[A]
unmodifiable=true
source=[A, B]
~~~

Sealed bảo đảm loại result trực tiếp hợp lệ; record mô tả payload; `List.copyOf` bảo đảm snapshot list structure. Ba trách nhiệm **khác nhau** phối hợp, không nên đánh đồng.

Ở ví dụ này elements là Strings immutable nên record Items hoạt động như value snapshot ổn định ở graph đang xét.

## 36. Generic results: có thể dùng sealed cùng type parameter

Một API muốn `Result<User>`, `Result<Order>`, `Result<String>` có thể dùng generic sealed interface:

~~~java
sealed interface Result<T> permits Ok, Err {
}

record Ok<T>(T value) implements Result<T> {
}

record Err<T>(String message) implements Result<T> {
}
~~~

Các declarations hợp lệ trong cùng compilation unit. `Result<T>` giữ kiểu của payload success; error variant vẫn mang message.

Có thể dùng:

~~~java
Result<Integer> answer = new Ok<>(42);
Result<Integer> failure = new Err<>("missing");
~~~

Đây là snippet hợp lệ trong method. Những variants cùng generic contract giúp API không phải trả `Object` và ép kiểu một cách thiếu kiểm soát.

**Nhưng** generic sealed hierarchy không tự thay thế exception management, null policy hay validation. Bạn cần quyết định liệu `Ok<>(null)` có được phép không, error string có cấu trúc đủ không, và client nên xử lý như thế nào.

## 37. Chương trình 13 — generic sealed result

Tệp **`GenericResultDemo.java`**:

~~~java
sealed interface Result<T> permits Ok, Err {
}

record Ok<T>(T value) implements Result<T> {
}

record Err<T>(String message) implements Result<T> {
}

public class GenericResultDemo {
    static <T> String describe(Result<T> result) {
        if (result instanceof Ok<?> ok) {
            return "ok:" + ok.value();
        }
        if (result instanceof Err<?> err) {
            return "err:" + err.message();
        }
        throw new IllegalArgumentException("unknown");
    }

    public static void main(String[] args) {
        Result<Integer> success = new Ok<>(42);
        Result<Integer> failure = new Err<>("missing");

        System.out.println(describe(success));
        System.out.println(describe(failure));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 GenericResultDemo.java
java GenericResultDemo
~~~

**Stdout:**

~~~text
ok:42
err:missing
~~~

Generic parameter giúp những callers biết rằng success payload thuộc kiểu Integer ở đây. Trong Java 17, pattern `instanceof Ok<?> ok` hợp lệ do không kiểm tra một concrete generic type argument đã bị type erasure làm mất ở runtime.

## 38. Reflection: chỉ quan sát direct permitted types

Java 17 có:

- `Class.isSealed()` để kiểm tra runtime class/interface có sealed không.
- `Class.getPermittedSubclasses()` để đọc các **direct permitted classes/interfaces**, không phải mọi hậu duệ.

Ví dụ với:

~~~text
Result (sealed)
├── Success (final)
└── ExtensionResult (non-sealed)
    └── ThirdPartyResult
~~~

Reflection trên Result trả Success và ExtensionResult, **không tự liệt kê ThirdPartyResult**.

Không nên dùng reflection để thường xuyên phân nhánh business logic trong một model nhỏ; dùng interface methods hoặc `instanceof` sẽ rõ hơn. Reflection hữu ích hơn cho tooling, diagnostics và kiểm tra cấu trúc hierarchy.

Thứ tự trả về từ reflection không nên bị xem là ranking nghiệp vụ; nếu in danh sách trong test, nên sort trước để stdout ổn định.

## 39. Chương trình 14 — kiểm tra danh sách direct variants

Tệp **`PermittedVariantsDemo.java`**:

~~~java
import java.util.Arrays;

sealed interface Action permits CreateAction, DeleteAction {
}

record CreateAction(String id) implements Action {
}

record DeleteAction(String id) implements Action {
}

public class PermittedVariantsDemo {
    public static void main(String[] args) {
        System.out.println("sealed=" + Action.class.isSealed());

        String[] names = Arrays.stream(
                    Action.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println("permitted="
                + Arrays.toString(names));
        System.out.println("record final="
                + java.lang.reflect.Modifier.isFinal(
                        CreateAction.class.getModifiers()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PermittedVariantsDemo.java
java PermittedVariantsDemo
~~~

**Stdout:**

~~~text
sealed=true
permitted=[CreateAction, DeleteAction]
record final=true
~~~

`CreateAction` và `DeleteAction` đều là records implicitly final. Sort làm kết quả in ra không phụ thuộc thứ tự API trả về. Code không dùng reflection để phân loại một runtime Action instance; chỉ minh họa metadata của type hierarchy.

## 40. Sealed không phải kiểm soát an ninh hay tính hợp lệ của dữ liệu

Những điều `sealed` **không tự bảo đảm**:

- Caller được quyền tạo hoặc thực thi một value.
- Một request đã được xác thực/ủy quyền.
- Các record components không null hoặc có định dạng chính xác.
- JSON từ bên ngoài an toàn trước dữ liệu độc hại.
- List/Map/array bên trong biến thể bất biến sâu.
- Các methods đều không có side effects.
- Các trạng thái workflow chỉ được tạo qua transition hợp lệ.
- Mọi case handling trong chuỗi `if instanceof` Java 17 đều exhaustive.
- Các API tích hợp được cập nhật khi thêm một variant mới.

Ví dụ, `record DeleteUser(String userId) implements Command` là một type hợp lệ nhưng **không chứng minh** người gửi lệnh có quyền xóa tài khoản. Service vẫn phải kiểm tra quyền, validate dữ liệu và thực hiện thay đổi an toàn.

Đừng dùng type name như cơ chế security boundary. Sealed là **ràng buộc subtype trong ngôn ngữ Java**, không phải authentication hoặc authorization.

## 41. Những trường hợp không nên áp dụng sealed

**A. Plugin system:** interface `Plugin` phải được third parties implement ở các modules riêng. Một root sealed toàn bộ không phù hợp; xem interface mở hoặc non-sealed extension point.

**B. Một loại value duy nhất:** `record Coordinate(int x, int y)` không cần sealed root nếu không có alternatives.

**C. Tập hằng đơn giản:** `enum Priority { LOW, MEDIUM, HIGH }` thường trực tiếp và dễ đọc hơn ba empty records.

**D. Chỉ hai trạng thái “có hoặc không”:** `Optional<T>` có thể đủ nếu không có payload lỗi hoặc chính sách bổ sung.

**E. Dữ liệu đa hình nhưng contract cố tình mở:** một interface thư viện như `Comparator<T>` hoặc `Runnable` phục vụ sự linh hoạt của caller. Sealing các loại callback như thế đi ngược mục đích.

**F. Các kiểu thường xuyên sinh thêm bởi code generator bên ngoài module:** `permits` và module boundaries gây chi phí bảo trì, không có ích nếu chưa có tập variants thực sự đóng.

**G. Hệ thống chỉ cần phân nhóm dữ liệu theo một enum field:** thêm sealed hierarchy phức tạp có thể không đem lại invariant mới.

Sealed nên được lựa chọn vì **hợp đồng tập biến thể**, không phải vì “mới hơn class thường”.

## 42. Bảng lựa chọn nhanh

| Tình huống | Lựa chọn đáng cân nhắc | Lý do |
| --- | --- | --- |
| Status chỉ có tên, không payload riêng | Enum | Ít boilerplate, switch tốt ở Java 17 |
| Value có cùng bộ fields | Record đơn | Không cần nhiều runtime types |
| Một trong vài outcomes, payload khác nhau | Sealed interface + records | Types phân biệt chính xác từng payload |
| AST với nodes khác nhau và cây đệ quy | Sealed interface + records/classes | Grammar đóng, behavior rõ |
| Cùng base state/constructor logic | Abstract sealed class + final children | Chia sẻ implementation |
| Có/không có giá trị đơn giản | `Optional<T>` | API nhẹ |
| Callback chức năng từ bên ngoài | Functional interface mở | Cho lambda và implementations tùy ý |
| Plugin do bên thứ ba viết | Interface mở hoặc non-sealed branch | Chủ động cho extension |
| Domain hierarchy có một số họ mở | Sealed root + non-sealed direct child | Đóng họ trực tiếp, mở một nhánh |
| Domain value với nhiều mutable components | Record + defensive copies/invariants | Sealed không thay immutability |
| Mô hình state machine có transitions phức tạp | Sealed variants + domain service | Loại trạng thái rõ, transitions được kiểm soát riêng |

Lựa chọn trên là **hướng thiết kế**, không phải một quy định tuyệt đối. Sự khác biệt lớn nằm ở ngữ nghĩa của giá trị và phạm vi mở rộng.

## 43. Refactor từng bước từ model có `kind` và nhiều fields

Giả sử tồn tại model cũ:

~~~java
class ProcessResult {
    String kind;
    String value;
    String error;
}
~~~

Nên refactor theo các bước có kiểm soát:

1. **Liệt kê trạng thái hợp lệ thực sự:** success mang value; error mang error; có Pending hay không?
2. **Xác định states không hợp lệ:** `kind="SUCCESS"` nhưng value null, hoặc cả value/error cùng tồn tại.
3. **Đặt tên variants:** `Processed`, `Failed`, `Pending` tương ứng domain, không đặt `Type1`, `Type2`.
4. **Chọn root:** `sealed interface ProcessOutcome permits ...` nếu chủ sở hữu kiểm soát các variants.
5. **Khai records:** mỗi record chỉ có payload của mình và compact constructor validation nếu cần.
6. **Tạo adapter ở ranh giới cũ:** parse kind một lần, chuyển input thành variant typed.
7. **Chuyển call sites:** dùng polymorphism hoặc instanceof patterns của Java 17.
8. **Định nghĩa null/error policy:** không dùng null để biểu diễn nhiều ý nghĩa khác nhau.
9. **Giữ tương thích external API:** nếu JSON discriminator trước đây là string, quyết định mapping/versioning.
10. **Test migration:** mọi trạng thái cũ hợp lệ chuyển thành variant đúng; trạng thái không hợp lệ bị từ chối.
11. **Đánh giá tần suất thêm loại mới:** nếu biến thể không đóng, điều chỉnh root/extension strategy trước khi public API ổn định.

Không thay đổi toàn bộ hệ thống chỉ vì syntax mới. Nên chứng minh refactor **loại bỏ trạng thái sai và cải thiện ranh giới ownership**.

## 44. Bài tập tự luyện

**Câu 1.** Một `Result` có hai outcomes: Success(value) và Failure(reason). Tại sao sealed interface + records có thể tốt hơn một class với `boolean success`, `String value`, `String reason`?

**Câu 2.** Một enum Color chỉ có RED, GREEN, BLUE. Có nên mặc định đổi thành ba record variants không?

**Câu 3.** Nếu trạng thái SHIPPED cần tracking code riêng cho từng đơn hàng, enum instance có phù hợp làm nơi lưu mutable tracking code không?

**Câu 4.** `sealed` kiểm soát direct children hay mọi descendants?

**Câu 5.** Nếu một direct child khai `non-sealed`, class cháu có cần nằm trong `permits` của root không?

**Câu 6.** Nếu một model cần đóng **mọi concrete variants**, một non-sealed branch có nguy cơ gì?

**Câu 7.** Vì sao record thường implements sealed interface thay vì extends sealed class?

**Câu 8.** Một permitted record có phải thêm `final` tường minh không?

**Câu 9.** `sealed abstract class` thích hợp hơn sealed interface trong hoàn cảnh nào?

**Câu 10.** Với một plugin API mà bên thứ ba phải trực tiếp implement interface ở module khác, sealed root hoàn toàn có phù hợp không?

**Câu 11.** Trong Java 17, dùng `instanceof Success success` có cần preview không?

**Câu 12.** Trong Java 17 không-preview, có thể switch pattern trực tiếp qua mọi record variants của sealed interface như Java 21 không?

**Câu 13.** Chuỗi `if/else instanceof` trên sealed value types của Java 17 có tự được compiler kiểm tra exhaustive không?

**Câu 14.** Nếu interface sealed chỉ có một abstract method, có thể gán lambda trực tiếp cho nó không?

**Câu 15.** Khi nào dùng polymorphic method `value.display()` có thể tốt hơn nhiều instanceof branches?

**Câu 16.** Visitor giúp tổ chức code thế nào nếu phải có nhiều phép xử lý khác nhau cho cùng tập variants?

**Câu 17.** Một `Items(List<String>)` record tự làm List immutable sâu không?

**Câu 18.** `List.copyOf` trong compact constructor có deep-copy mọi mutable elements không?

**Câu 19.** Sealed có tự validate null components của record không?

**Câu 20.** Sealed có tự bảo đảm transition hợp lệ từ CartOpen sang Completed không?

**Câu 21.** Thêm Pending vào một sealed Result đã public cần rà soát những phần nào?

**Câu 22.** Nếu các variants nằm trong unnamed module, direct permitted subtypes phải cùng package hay chỉ cần cùng project?

**Câu 23.** Nếu nằm trong named module, permitted direct subtype có được nằm ở package khác cùng module không?

**Câu 24.** Nếu bỏ `permits` thì Java có tự tìm mọi subclass ở toàn repository không?

**Câu 25.** `Class.getPermittedSubclasses()` có liệt kê mọi hậu duệ gián tiếp dưới non-sealed branch không?

**Câu 26.** Nếu chỉ cần giá trị có/không có, có nên cân nhắc Optional trước sealed hierarchy không?

**Câu 27.** Sealed có thay cho authorization ở method DeleteUser không?

**Câu 28.** Nêu ba câu hỏi cần trả lời trước khi thêm sealed vào một domain model.

### Đáp án có giải thích

1. Mỗi variant chỉ mang payload tương ứng và giảm các tổ hợp trạng thái sai vì field không áp dụng.
2. Không; enum phù hợp hơn với tập tên hằng không cần payload khác nhau.
3. Không; enum constant là object dùng chung, nên mutable dữ liệu của một đơn hàng ở đó là thiết kế sai. Có thể dùng record variant chứa tracking code.
4. Direct permitted subtypes của **chính nút sealed**.
5. Không, vì cháu trực tiếp extends/implements non-sealed child.
6. Nhánh ấy cho phép descendants mới, nên tập mọi concrete variants không còn đóng.
7. Record có superclass cố định là `java.lang.Record`; nó có thể implements interface.
8. Không; records implicitly final.
9. Khi variants cần kế thừa state/constructor/shared implementation của superclass.
10. Thường không; chọn interface mở hoặc thiết kế non-sealed extension point.
11. Không. Pattern matching for instanceof là tính năng chuẩn của Java 17.
12. Không, pattern matching for switch chỉ ổn định ở Java 21; Java 17 có preview khác nhưng không phải mặc định.
13. Không; cần kiểm thử, visitor hoặc chính sách fallback rõ.
14. Không; sealed interface không được xem là functional interface.
15. Khi hành vi nội tại của biến thể được gọi thống nhất và không cần phân biệt kiểu ở caller.
16. Các method visitor phân biệt variants để bổ sung một phép xử lý mới mà không rải instanceof khắp nơi.
17. Không; record fields final, nhưng List mutable vẫn có thể bị sửa qua aliases/accessor.
18. Không; chỉ snapshot cấu trúc list và references tới elements.
19. Không; cần constructor validation riêng.
20. Không; business service/factory/state-transition logic vẫn phải kiểm tra.
21. Consumers, serializers, versioning, UI, rules, tests, null/fallback policy và docs.
22. Cùng package theo quy tắc unnamed module.
23. Có, nếu cùng named module và accessibility hợp lệ.
24. Không; chỉ được suy ra từ cùng compilation unit khi đáp ứng quy tắc.
25. Không; chỉ direct permitted types của sealed root.
26. Có; Optional<T> có thể đơn giản hơn nếu chỉ mang nghĩa có/không.
27. Không; authorization phải dựa trên danh tính người dùng và chính sách quyền thực tế.
28. Tập variants có thật sự đóng không? Payload mỗi variant có khác nhau không? API cần extension từ bên ngoài không?

## 45. Checklist dùng khi review thiết kế

- [ ] Các loại giá trị có thực sự là những **biến thể domain** khác nhau?
- [ ] Tập direct variants có được biết và được quản trị bởi cùng package/module?
- [ ] Mỗi variant có fields/invariant riêng đủ để xứng đáng có type?
- [ ] Nếu chỉ là named constants, đã cân nhắc enum?
- [ ] Nếu chỉ là một shape dữ liệu, đã cân nhắc một record?
- [ ] Nếu chỉ có/không có, đã cân nhắc Optional<T>?
- [ ] Root là sealed class hay sealed interface đúng với nhu cầu inheritance?
- [ ] `permits` chứa đúng direct implementing/extended types?
- [ ] Mọi permitted children có trạng thái final/sealed/non-sealed phù hợp?
- [ ] Có tránh non-sealed branch nếu model phải đóng toàn bộ concrete variants?
- [ ] Nếu có non-sealed branch, đã công khai đây là extension point?
- [ ] Variants record không cố extends superclass ngoài `Record`?
- [ ] Có validation null/range/format ở constructors khi domain cần?
- [ ] Có defensive copy với mutable record components khi công bố value snapshot?
- [ ] Có chọn polymorphism/visitor thay vì sao chép instanceof chain nếu thích hợp?
- [ ] Trong Java 17, không dùng pattern switch Java 21 như code không-preview?
- [ ] Có test null, unsupported variant và fallback behavior?
- [ ] Có xem tập variants là hợp đồng API khi thêm variant mới?
- [ ] Có kiểm tra module/package restrictions của Java sealed?
- [ ] Có tránh nhầm security/permissions với type hierarchy restrictions?
- [ ] Có chọn định dạng serialization và versioning rõ cho external messages?
- [ ] Các chương trình test có stdout và hành vi xác định?
- [ ] Tên variants mô tả đúng nghiệp vụ, không chỉ là TypeA/TypeB?
- [ ] Việc dùng sealed giảm trạng thái sai thay vì tăng boilerplate?

## 46. Tài liệu Java 17 chính thức

- [JLS Java SE 17 §8.1.1.2 — `sealed`, `non-sealed` và `final`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): các lựa chọn class modifiers.
- [JLS Java SE 17 §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): danh sách `permits` của sealed class.
- [JLS Java SE 17 §9.1.1.4 — `sealed` và `non-sealed` interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): lựa chọn trong interface hierarchies.
- [JLS Java SE 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): sealed interface trực tiếp kiểm soát types nào.
- [JLS Java SE 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): sealed interface không là functional interface.
- [JLS Java SE 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records và record components.
- [JLS Java SE 17 §15.20.2 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests và pattern variable.
- [Java SE 17 API — `Class.isSealed`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): reflection kiểm tra sealed.
- [Java SE 17 API — `Class.getPermittedSubclasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): reflection đọc direct types.
- [Java SE 17 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot of list structure.
- [Java SE 17 API — `Optional`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): trường hợp có hoặc không có giá trị.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): động cơ thiết kế, closed hierarchies và kiểm soát subtype.
- [JEP 395 — Records](https://openjdk.org/jeps/395): record payload variants.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): hoàn thiện ở Java 21, không phải cú pháp ổn định không-preview của Java 17.

## 47. Tổng kết: chọn sealed vì một hợp đồng miền thật sự cần đóng

**Sealed đặc biệt phù hợp khi một giá trị có thể thuộc một trong vài loại được quản trị tập trung, và mỗi loại có cấu trúc hoặc ý nghĩa riêng.** Kết hợp **sealed interface + record** thường hiệu quả cho results, commands, states, events và AST nodes: sealed nói *loại nào được phép*, còn record nói *mỗi loại chứa dữ liệu gì*.

Nhưng `sealed` **không thay thế** enum khi chỉ có named constants, Optional khi chỉ có absent/present, interface mở khi cần plugin, hoặc constructor validation khi cần invariant. `sealed` giới hạn **direct subtypes**, không tự ngăn descendants qua non-sealed branch. Nó cũng không tự cho exhaustive `if instanceof` trong Java 17 và không phải cơ chế bảo mật.

Trước khi áp dụng hãy hỏi: **(1) tập biến thể có thực sự đóng và thuộc quyền kiểm soát của module không; (2) payload/hành vi của mỗi biến thể có khác nhau đủ để cần type riêng không; (3) ta có muốn và có khả năng duy trì hợp đồng variants khi API tiến hóa không?** Khi cả ba câu trả lời phù hợp, sealed giúp type system bảo vệ thiết kế, làm code dễ hiểu và giảm những trạng thái dữ liệu sai dạng.

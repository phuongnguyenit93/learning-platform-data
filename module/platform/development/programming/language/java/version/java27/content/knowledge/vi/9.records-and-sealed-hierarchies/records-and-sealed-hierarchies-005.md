# Final, sealed và non-sealed trong hệ phân cấp kiểu

Khi thiết kế hệ phân cấp lớp và giao diện trong Java 27, câu hỏi quan trọng là: **ai được phép tạo kiểu con và phạm vi mở rộng cần dừng ở đâu?** Java cung cấp ba cách kiểm soát trực tiếp: `final` để kết thúc kế thừa, `sealed` để giới hạn các kiểu con trực tiếp được cho phép, và `non-sealed` để chủ động mở lại khả năng mở rộng ở một nhánh của hệ phân cấp.

Các cơ chế này đặc biệt hữu ích khi mô hình hóa tập trạng thái, loại sự kiện, kết quả xử lý hoặc cây biểu thức bằng lớp, giao diện và record. Chúng cũng phối hợp với pattern matching trong `switch` để trình biên dịch kiểm tra những trường hợp mà chương trình cần xử lý.

Bài này sử dụng các tính năng đã ổn định trong Java hiện đại và tiếp tục phù hợp với phạm vi học Java 27. Những ví dụ không yêu cầu bật preview.

## 1. Vì sao cần kiểm soát kế thừa?

Giả sử chương trình có giao diện kết quả xử lý:

~~~java
interface PaymentResult {
}
~~~

Nếu giao diện được công khai và không có giới hạn khác, các lớp ở nơi khác có thể tạo thêm kiểu triển khai:

~~~java
class Accepted implements PaymentResult {
}

class Rejected implements PaymentResult {
}

class UnknownResult implements PaymentResult {
}
~~~

Đây là thiết kế phù hợp khi ứng dụng muốn cho phép bên ngoài bổ sung kiểu mới. Nhưng nếu miền nghiệp vụ quy định chính xác chỉ có những trường hợp nhất định, việc mở hoàn toàn khiến trình biên dịch không thể biết hết các biến thể cần được xử lý.

Dùng `sealed`, ta có thể khai báo rõ danh sách kiểu con trực tiếp được chấp nhận:

~~~java
sealed interface PaymentResult permits Accepted, Rejected {
}

final class Accepted implements PaymentResult {
}

final class Rejected implements PaymentResult {
}
~~~

Giờ một lớp thứ ba không được liệt kê không thể trực tiếp `implements PaymentResult` theo các quy tắc Java thông thường. Hệ phân cấp được kiểm soát ngay tại khai báo của kiểu cha.

Lưu ý: `sealed` giới hạn **các kiểu con trực tiếp**. Một nhánh có thể tiếp tục mở rộng nếu kiểu con được cho phép khai báo `non-sealed`; phần sau sẽ phân tích điều này.

## 2. Phân biệt final, sealed và non-sealed

| Từ khóa | Ý nghĩa đối với hệ phân cấp | Có thể có kiểu con trực tiếp mới? | Khi nào dùng |
|---|---|---|---|
| `final` | Lớp là điểm kết thúc kế thừa | Không | Loại dữ liệu hoặc hành vi không muốn cho kế thừa tiếp |
| `sealed` | Lớp/giao diện chỉ chấp nhận các kiểu con trực tiếp được cho phép | Chỉ các kiểu trong `permits` hoặc được suy luận hợp lệ | Miền nghiệp vụ có danh sách loại được kiểm soát |
| `non-sealed` | Một nhánh trực tiếp của kiểu `sealed` được mở lại | Có, theo các quy tắc kế thừa thông thường | Giữ phần lõi đóng nhưng cho phép một nhánh mở rộng |

Quan hệ có thể hình dung:

~~~text
                  sealed Shape
                  /     |     \
                 /      |      \
          final Circle  sealed Polygon  non-sealed CustomShape
                         /     \                 |
                final Triangle final Square     +-- PartnerShape
                                                 +-- AnotherShape
~~~

`Shape` giới hạn ba kiểu con trực tiếp: `Circle`, `Polygon` và `CustomShape`. `Polygon` tiếp tục giới hạn những kiểu con của chính nó. `CustomShape` mở rộng được, nên những kiểu sâu hơn dưới nhánh này không cần xuất hiện trong `permits` của `Shape`.

Điểm khác biệt nằm ở **quyền kế thừa** của từng nhánh, không phải số lượng đối tượng có thể tạo. Một lớp `final` vẫn có thể tạo nhiều instance, và một lớp `sealed` vẫn có thể chứa trạng thái và hành vi thông thường.

## 3. final: điểm kết thúc của một nhánh kế thừa

### 3.1. final class

Khai báo `final class` ngăn lớp khác kế thừa nó:

~~~java
public final class CurrencyCode {
    private final String value;

    public CurrencyCode(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public String value() {
        return value;
    }
}
~~~

Mã sau không hợp lệ:

~~~java
// Lỗi biên dịch: CurrencyCode là final
// class SpecialCurrencyCode extends CurrencyCode { }
~~~

Một lớp `final` vẫn có thể triển khai các giao diện:

~~~java
interface Printable {
    String print();
}

final class Receipt implements Printable {
    @Override
    public String print() {
        return "Biên nhận";
    }
}
~~~

Nhưng lớp `Receipt` không thể có lớp con.

### 3.2. final method không đồng nghĩa final class

Một lớp thông thường có thể cho phép kế thừa nhưng cấm ghi đè một số phương thức:

~~~java
class BaseService {
    public final String protocolVersion() {
        return "v1";
    }

    public String handle() {
        return "base";
    }
}

class CustomService extends BaseService {
    @Override
    public String handle() {
        return "custom";
    }

    // Không thể override protocolVersion():
    // public String protocolVersion() { return "v2"; }
}
~~~

`final` trên phương thức chặn việc override phương thức đó. Các phương thức instance khác không phải `final` vẫn có thể được override nếu quy tắc truy cập và kế thừa cho phép.

### 3.3. final variable không đồng nghĩa đối tượng bất biến

~~~java
final StringBuilder builder = new StringBuilder("Java");

builder.append(" 27");                 // Hợp lệ
System.out.println(builder);          // Java 27
// builder = new StringBuilder();     // Lỗi: không được gán lại biến final
~~~

`final` trên biến tham chiếu chỉ ngăn gán lại biến; trạng thái của đối tượng có thể vẫn thay đổi. Vì thế cần phân biệt `final class`, `final method` và `final variable`.

Một lớp không thể đồng thời `abstract` và `final` vì lớp trừu tượng cần có khả năng được hoàn thiện bằng kiểu con, trong khi `final` cấm điều đó. Giao diện không thể khai báo `final interface`; muốn kiểm soát kiểu triển khai, hãy dùng `sealed interface`.

## 4. sealed: khai báo các kiểu con được phép

### 4.1. Cú pháp sealed class

~~~java
abstract sealed class Document permits Invoice, Note {
}

final class Invoice extends Document {
}

non-sealed class Note extends Document {
}
~~~

Trong ví dụ:

- `Document` là lớp trừu tượng, giới hạn các lớp con trực tiếp thành `Invoice` và `Note`.
- `Invoice` kết thúc nhánh bằng `final`.
- `Note` mở lại quyền kế thừa bằng `non-sealed`.
- Một lớp mới không thể trực tiếp `extends Document` trừ khi được cho phép bởi khai báo của `Document`.

Lớp `sealed` **không bắt buộc** phải là `abstract`. Một `sealed class` cụ thể vẫn có thể được khởi tạo nếu constructor và quyền truy cập cho phép. Điều này cần được lưu ý khi viết `switch` nhằm bao phủ mọi giá trị của kiểu cha.

### 4.2. Cú pháp sealed interface

Giao diện có thể giới hạn cả lớp triển khai và giao diện con:

~~~java
sealed interface Message permits TextMessage, MediaMessage {
}

record TextMessage(String text) implements Message {
}

non-sealed interface MediaMessage extends Message {
}
~~~

`TextMessage` là record và mặc nhiên `final`, nên không cần viết thêm modifier. `MediaMessage` là giao diện con mở; các lớp khác có thể triển khai `MediaMessage` mà không phải xuất hiện trong `permits` của `Message`.

Một giao diện con trực tiếp của `sealed interface` thường cần `sealed` hoặc `non-sealed`. Không có khái niệm `final interface`.

### 4.3. permits chỉ liệt kê kiểu con trực tiếp

~~~java
sealed interface Root permits Branch {
}

non-sealed interface Branch extends Root {
}

final class Leaf implements Branch {
}
~~~

`Leaf` là kiểu con gián tiếp của `Root` thông qua `Branch`. `Leaf` không cần và cũng không được liệt kê trong `permits` của `Root` với tư cách kiểu con trực tiếp.

Cách kiểm tra nhanh là nhìn vào mệnh đề `extends` hoặc `implements` của kiểu được liệt kê: nó phải trực tiếp khai báo quan hệ với kiểu `sealed` tương ứng.

## 5. Những quy tắc bắt buộc của kiểu con trực tiếp

Khi một lớp/giao diện trực tiếp mở rộng hoặc triển khai một kiểu `sealed`, Java yêu cầu kiểu đó xác định rõ hướng đi tiếp theo của hệ phân cấp.

Đối với **lớp thông thường** là kiểu con trực tiếp, phải chọn đúng một trong ba trạng thái:

- `final`: không có lớp con.
- `sealed`: tiếp tục giới hạn các lớp con trực tiếp.
- `non-sealed`: mở quyền kế thừa theo quy tắc thông thường.

Đối với **giao diện con trực tiếp**, chọn `sealed` hoặc `non-sealed`. Một **record** được phép trực tiếp triển khai giao diện `sealed` vì record mặc nhiên `final`. Enum cũng có quy tắc final/sealed riêng trong đặc tả, nhưng trong ví dụ dữ liệu mới, record thường dễ hiểu và gọn hơn.

Ví dụ không hợp lệ vì lớp triển khai chưa xác định trạng thái:

~~~java
sealed interface Command permits Start {
}

// Lỗi biên dịch: thiếu final, sealed hoặc non-sealed
// class Start implements Command {
// }
~~~

Sửa thành:

~~~java
sealed interface Command permits Start {
}

final class Start implements Command {
}
~~~

Không thể khai báo `final sealed class` hay `sealed non-sealed class` vì các modifier này mô tả những hướng kế thừa loại trừ nhau.

## 6. non-sealed: chủ động mở lại một nhánh

`non-sealed` có nghĩa là **bỏ giới hạn tập con trực tiếp ở nhánh hiện tại**. Nó chỉ hợp lệ khi lớp/giao diện đó có ít nhất một kiểu cha hoặc giao diện cha trực tiếp mang modifier `sealed`.

~~~java
sealed interface PluginEvent permits BuiltInEvent, ExtensionEvent {
}

record BuiltInEvent(String code) implements PluginEvent {
}

non-sealed interface ExtensionEvent extends PluginEvent {
}

final class ThirdPartyEvent implements ExtensionEvent {
}
~~~

`ThirdPartyEvent` hợp lệ dù không được liệt kê trong `PluginEvent`, vì nó đi qua nhánh `ExtensionEvent` đã mở. Các lớp từ bên ngoài có thể tiếp tục triển khai `ExtensionEvent` nếu quyền truy cập/module cho phép.

Ngược lại, khai báo sau là lỗi:

~~~java
// Lỗi biên dịch: không có sealed direct superclass/superinterface
// non-sealed class OrdinaryClass {
// }
~~~

Một lớp kế thừa **trực tiếp từ lớp non-sealed** đã trở lại quy tắc kế thừa thông thường. Nó không tự động mang modifier `non-sealed` và cũng không được dùng modifier này nếu không có một kiểu cha trực tiếp `sealed` khác.

`non-sealed` chỉ nói về khả năng mở rộng kiểu. Nó không bỏ qua quyền truy cập constructor, `private`, `package-private`, `final method` hoặc các ràng buộc khác của Java.

## 7. Kết hợp sealed theo nhiều cấp

Một hệ phân cấp có thể có nhiều tầng kiểm soát:

~~~java
sealed interface Expression permits Literal, Operation {
}

record Literal(int value) implements Expression {
}

sealed interface Operation extends Expression
        permits Add, Multiply {
}

record Add(Expression left, Expression right)
        implements Operation {
}

record Multiply(Expression left, Expression right)
        implements Operation {
}
~~~

Sơ đồ:

~~~text
sealed Expression
├── Literal                  (record, implicitly final)
└── sealed Operation
    ├── Add                  (record, implicitly final)
    └── Multiply             (record, implicitly final)
~~~

`Expression` chỉ biết hai kiểu con trực tiếp là `Literal` và `Operation`. `Operation` lại quy định hai kiểu con trực tiếp của chính nó.

Lợi ích của cấu trúc nhiều cấp:

- Mỗi cấp diễn đạt rõ ranh giới của một nhóm khái niệm.
- Có thể xử lý tổng quát `Operation` hoặc phân biệt `Add`, `Multiply` khi cần.
- Khi bổ sung một phép toán mới, thay đổi tập `permits` tại cấp sở hữu phép toán; các nơi sử dụng `switch` có thể được trình biên dịch nhắc cập nhật.

Không nên tạo quá nhiều tầng `sealed` chỉ để giảm số dòng `switch`. Hệ phân cấp nên phản ánh quan hệ miền nghiệp vụ có ý nghĩa.

## 8. Records và hệ phân cấp sealed

Record là một lớp chuyên dùng cho dữ liệu. Một khai báo record tạo các trường component riêng tư và `final`, accessor, constructor thích hợp cùng các phương thức như `equals`, `hashCode` và `toString` theo quy tắc của ngôn ngữ.

Ví dụ:

~~~java
sealed interface Response permits Success, Failure {
}

record Success(String body) implements Response {
}

record Failure(int statusCode, String reason) implements Response {
}
~~~

Đây là một cách gọn để mô hình hóa các biến thể dữ liệu:

- `Response` giới hạn tập biến thể được hỗ trợ.
- `Success` và `Failure` mang dữ liệu tương ứng với từng biến thể.
- Record mặc nhiên `final`; không cần khai báo `final record`.
- Trình biên dịch có thể xác định rằng những instance hợp lệ của `Response` thuộc các biến thể được cấp phép.

### 8.1. Vì sao record không dùng sealed hay non-sealed?

Record mặc nhiên là một lớp `final`, nên không thể làm lớp cha cho các lớp khác. Các khai báo `sealed record` và `non-sealed record` đều không hợp lệ. Record cũng không được tùy ý kế thừa một lớp do lập trình viên định nghĩa: nó kế thừa `java.lang.Record`.

Vì vậy, khi muốn kết hợp record với hệ phân cấp kiểu, hãy thường đặt **giao diện sealed** ở gốc, rồi để các record `implements` giao diện đó.

~~~java
sealed interface TaskState permits Queued, Running, Completed {
}

record Queued() implements TaskState {
}

record Running(int percent) implements TaskState {
}

record Completed(String result) implements TaskState {
}
~~~

Nếu miền nghiệp vụ cần một nhánh cho phép tiếp tục kế thừa lớp, dùng một lớp thông thường với modifier phù hợp thay cho record tại nhánh đó.

### 8.2. final không bảo đảm deep immutability

Record có các trường component `final` nhưng một component có thể tham chiếu đến đối tượng mutable. Ví dụ:

~~~java
record Batch(java.util.List<String> items) {
}

var items = new java.util.ArrayList<String>();
items.add("A");
Batch batch = new Batch(items);

items.add("B");
System.out.println(batch.items()); // [A, B]
~~~

Nếu cần bảo vệ trạng thái, thiết kế record phải sao chép phòng vệ hoặc sử dụng thành phần bất biến theo yêu cầu. Việc record mặc nhiên `final` chỉ kiểm soát kế thừa và khả năng gán lại trường component.

## 9. Phạm vi package, module và quy tắc permits

Java không cho phép một hệ phân cấp `sealed` phân tán tùy ý qua các module không liên quan.

| Ngữ cảnh | Vị trí được phép của các kiểu con trực tiếp |
|---|---|
| Kiểu sealed thuộc **named module** | Các kiểu con trực tiếp phải thuộc **cùng named module**; có thể ở các package khác nhau khi quyền truy cập cho phép |
| Kiểu sealed thuộc **unnamed module** | Các kiểu con trực tiếp phải thuộc **cùng package** |

Ví dụ các file trong cùng package:

~~~text
src/
└── example/
    └── model/
        ├── Shape.java
        ├── Circle.java
        └── Rectangle.java
~~~

Nội dung `Shape.java`:

~~~java
package example.model;

public sealed interface Shape permits Circle, Rectangle {
}
~~~

Nội dung `Circle.java`:

~~~java
package example.model;

public record Circle(double radius) implements Shape {
}
~~~

Nội dung `Rectangle.java`:

~~~java
package example.model;

public record Rectangle(double width, double height)
        implements Shape {
}
~~~

Đây là cấu trúc hợp lệ khi biên dịch các file cùng package. Trong dự án sử dụng named module, các kiểu con trực tiếp có thể nằm ở package khác nhưng vẫn phải thuộc cùng module, đồng thời bảo đảm chúng có thể truy cập nhau theo quy tắc Java.

### 9.1. Khi nào được bỏ permits?

Nếu những kiểu con trực tiếp hợp lệ được khai báo **trong cùng một đơn vị biên dịch (compilation unit, tức file nguồn)** với kiểu `sealed`, trình biên dịch có thể suy luận danh sách được phép từ các khai báo đó.

~~~java
sealed interface Token {
}

record Word(String text) implements Token {
}

record End() implements Token {
}
~~~

Cả ba khai báo ở cùng một file nên không cần `permits Word, End`. Những kiểu được suy luận phải có tên canonical hợp lệ; lớp local hoặc anonymous không tham gia danh sách suy luận này.

Đối với hệ phân cấp trải trên nhiều file, nên khai báo `permits` rõ ràng. **Cùng package không đồng nghĩa có thể bỏ `permits` nếu các lớp nằm ở file nguồn khác nhau.**

### 9.2. Các tên trong permits phải hợp lệ

Danh sách `permits`:

- Chỉ chứa các kiểu truy cập được theo ngữ cảnh khai báo.
- Không chứa cùng một kiểu nhiều lần.
- Mỗi kiểu phải thực sự là kiểu con trực tiếp của kiểu `sealed`.
- Phải tuân thủ quy tắc cùng named module hoặc cùng package trong unnamed module.

Ví dụ `sealed interface A permits C` nhưng `C` chỉ gián tiếp triển khai `A` là không hợp lệ. Khi dùng các file tách biệt, hãy kiểm tra cả mệnh đề `permits` của cha và `implements`/`extends` của con.

## 10. Kết hợp sealed với pattern matching trong switch

Một lợi ích lớn của hệ phân cấp `sealed` là khả năng kiểm tra **tính bao phủ đầy đủ** (exhaustiveness) khi dùng `switch`.

Với hệ phân cấp:

~~~java
sealed interface Outcome permits Ok, Error {
}

record Ok(String value) implements Outcome {
}

record Error(String message) implements Outcome {
}
~~~

Có thể xử lý:

~~~java
static String describe(Outcome outcome) {
    return switch (outcome) {
        case Ok ok -> "Thành công: " + ok.value();
        case Error error -> "Thất bại: " + error.message();
    };
}
~~~

`switch` expression bao phủ hai kiểu con trực tiếp của giao diện `Outcome`, nên không cần `default`. Nếu bổ sung một biến thể mới vào `permits`, trình biên dịch sẽ phát hiện những biểu thức `switch` không còn bao phủ đủ kiểu khi biên dịch lại.

Điều này giúp mã xử lý trạng thái rõ ràng hơn vì mỗi biến thể có nhánh riêng.

### 10.1. Điều gì xảy ra với nhánh non-sealed?

Giả sử một nhánh được khai báo `non-sealed`:

~~~java
sealed interface Notice permits InternalNotice, ExternalNotice {
}

record InternalNotice(String text) implements Notice {
}

non-sealed interface ExternalNotice extends Notice {
}
~~~

Bất kỳ lớp nào triển khai `ExternalNotice` cũng là một `Notice`. Khi dùng `switch`, một nhánh `case ExternalNotice external` có thể bao phủ toàn bộ các triển khai của giao diện đó:

~~~java
static String category(Notice notice) {
    return switch (notice) {
        case InternalNotice internal -> "Nội bộ";
        case ExternalNotice external -> "Bên ngoài";
    };
}
~~~

Việc `switch` được xem là exhaustive không có nghĩa trình biên dịch biết hết **các lớp cụ thể** dưới `ExternalNotice`. Nó chỉ biết nhánh `case ExternalNotice` sẽ xử lý được mọi instance của các lớp đó.

### 10.2. null được xử lý như thế nào?

`null` không phải một lớp con của bất kỳ kiểu `sealed` nào. Một `switch` dùng tham chiếu `null` thường ném `NullPointerException` nếu không có nhánh xử lý `case null`.

Ví dụ xử lý tường minh:

~~~java
static String describeNullable(Outcome outcome) {
    return switch (outcome) {
        case null -> "Chưa có kết quả";
        case Ok ok -> "Thành công: " + ok.value();
        case Error error -> "Thất bại: " + error.message();
    };
}
~~~

Hoặc, nếu `null` là đầu vào không hợp lệ, dùng `Objects.requireNonNull(outcome)` trước `switch`.

Cần xác định chính sách null theo ý nghĩa dữ liệu; `sealed` không tự biến tham chiếu thành non-null.

### 10.3. Khi phát triển thêm biến thể

Nếu mã khách hàng được biên dịch theo tập con cũ nhưng tập `permits` đã thay đổi ở runtime, một `switch` từng được xác định exhaustive tại thời điểm biên dịch có thể gặp `MatchException` trong một số trường hợp không khớp khi chạy. Vì vậy, khi mở rộng sealed hierarchy được dùng trong `switch`, cần biên dịch lại và kiểm tra các consumer liên quan.

Không nên thêm `default` chỉ để che đi việc bỏ sót các biến thể đã biết nếu mục tiêu là để trình biên dịch nhắc cập nhật logic. Một `default` có ý nghĩa nghiệp vụ thật sự vẫn là lựa chọn hợp lệ.

## 11. Ví dụ hoàn chỉnh: hệ phân cấp thông báo

Ví dụ sau đặt mọi khai báo trong một file `NotificationDemo.java`. Nó minh họa cả ba hướng `final`, `sealed` và `non-sealed`, record cùng pattern matching `switch`.

~~~java
import java.util.Objects;

public class NotificationDemo {
    sealed interface Notification
            permits Email, Push, PartnerNotification {
    }

    // Record được ngầm định là final.
    record Email(String address) implements Notification {
        Email {
            Objects.requireNonNull(address, "address");
        }
    }

    record Push(String token) implements Notification {
        Push {
            Objects.requireNonNull(token, "token");
        }
    }

    // Nhánh cho phép đối tác tạo kiểu con.
    static non-sealed class PartnerNotification implements Notification {
        private final String source;

        PartnerNotification(String source) {
            this.source = Objects.requireNonNull(source, "source");
        }

        String source() {
            return source;
        }
    }

    static final class MarketplaceNotification
            extends PartnerNotification {
        MarketplaceNotification() {
            super("Marketplace");
        }
    }

    static String summarize(Notification notification) {
        Objects.requireNonNull(notification, "notification");

        return switch (notification) {
            case Email email ->
                    "Email tới: " + email.address();
            case Push push ->
                    "Push token: " + push.token();
            case PartnerNotification partner ->
                    "Đối tác: " + partner.source();
        };
    }

    public static void main(String[] args) {
        Notification email = new Email("an@example.test");
        Notification partner = new MarketplaceNotification();

        System.out.println(summarize(email));
        System.out.println(summarize(partner));
    }
}
~~~

Kết quả:

~~~text
Email tới: an@example.test
Đối tác: Marketplace
~~~

Phân tích:

1. `Notification` là kiểu `sealed`, liệt kê đúng ba kiểu con trực tiếp.
2. `Email` và `Push` là record, tự kết thúc kế thừa.
3. `PartnerNotification` được khai báo `non-sealed` vì miền ứng dụng cho phép tạo các lớp thông báo đối tác khác.
4. `MarketplaceNotification` kế thừa `PartnerNotification`, không cần nằm trong `permits` của `Notification`.
5. `summarize` có nhánh xử lý đầy đủ các kiểu mà giao diện gốc cho phép, kể cả các lớp nằm dưới nhánh `PartnerNotification`.
6. `Objects.requireNonNull` làm rõ hợp đồng: đầu vào của phương thức không được là `null`.

Chạy ví dụ tại thư mục chứa file:

~~~shell
javac -encoding UTF-8 NotificationDemo.java
java NotificationDemo
~~~

Ví dụ chỉ sử dụng cú pháp và API Java hiện hành; không cần cấu hình preview.

## 12. Khi nào nên dùng từng modifier?

| Nhu cầu thiết kế | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Kiểu dữ liệu hoàn chỉnh, không cần cho kế thừa | `final class` hoặc `record` | Ngăn tạo lớp con |
| Một tập biến thể miền nghiệp vụ hữu hạn, có thể diễn đạt bằng các loại dữ liệu | `sealed interface` + các record | Giới hạn biến thể, dễ dùng `switch` |
| Một lớp cha cần chia sẻ trạng thái/triển khai với một tập lớp con được kiểm soát | `abstract sealed class` | Kiểm soát kế thừa và tái sử dụng mã |
| Một nhánh tiếp tục được giới hạn thành các kiểu con xác định | `sealed` trên nhánh đó | Quản lý cấu trúc phân cấp nhiều cấp |
| Phần lõi đóng nhưng một nhánh dành cho mở rộng | `non-sealed` tại nhánh trực tiếp | Cho phép bên ngoài phát triển kiểu con ở điểm mở |
| API plugin công khai cho bên thứ ba cài thêm loại triển khai | Giao diện thông thường hoặc nhánh `non-sealed` | Không cần cập nhật danh sách `permits` cho mọi plugin |
| Chỉ muốn cấm override một phương thức | `final method` | Không cần đóng cả lớp |
| Muốn biến tham chiếu không thể gán lại | `final variable` | Không liên quan đến quyền kế thừa của kiểu |

Một hệ phân cấp nên dùng `sealed` khi tập biến thể được kiểm soát bởi nhóm sở hữu API. Nếu mục tiêu là một điểm mở rộng cho plugin bên ngoài, cần chủ động chừa một nhánh `non-sealed` hoặc một interface thông thường.

Không nên xem `sealed` là cơ chế bảo mật thay thế kiểm soát quyền truy cập, xác thực hoặc phân quyền. Nó là ràng buộc của hệ thống kiểu và quá trình nạp/liên kết lớp trong mô hình Java.

## 13. Các lỗi biên dịch thường gặp

### 13.1. Quên modifier của kiểu con trực tiếp

~~~java
sealed interface State permits Ready {
}

// Sai:
// class Ready implements State {}

// Đúng:
final class Ready implements State {
}
~~~

### 13.2. Kiểu con không nằm trong permits

~~~java
sealed interface Channel permits Sms {
}

record Sms(String number) implements Channel {
}

// Sai: Email không được Channel cho phép.
// record Email(String address) implements Channel { }
~~~

Muốn bổ sung `Email`, phải cập nhật danh sách `permits` của `Channel` và khai báo một subtype hợp lệ.

### 13.3. Ghi non-sealed ở nơi không hợp lệ

~~~java
class Base {
}

// Sai: Base không sealed.
// non-sealed class Derived extends Base { }
~~~

`non-sealed` dành cho lớp hoặc giao diện có ít nhất một kiểu cha trực tiếp được khai báo `sealed`. Một lớp con dưới nhánh đã mở thường dùng khai báo `class` bình thường, hoặc tự chọn `final`/`sealed` nếu cần.

### 13.4. Thử kế thừa record hoặc final class

~~~java
record UserId(long value) {
}

// Sai: record ngầm định final.
// class SpecialUserId extends UserId { }
~~~

Khi cần biểu diễn các trường hợp khác nhau với record, tạo một giao diện `sealed` và để nhiều record triển khai giao diện đó.

### 13.5. Dùng sealed hierarchy qua nhiều package trong unnamed module

Nếu `Shape` nằm trong package `a` còn `Circle` trong package `b` và ứng dụng thuộc unnamed module, không thể khai báo `Circle` là kiểu con được phép trực tiếp của `Shape`. Cùng package là yêu cầu bắt buộc trong trường hợp này.

Trong named module, có thể đặt các kiểu con trực tiếp ở package khác nhau **trong cùng module**, với quyền truy cập phù hợp.

### 13.6. Hiểu nhầm về exhaustiveness

Nếu một `sealed class` là **concrete** và có thể khởi tạo trực tiếp, những instance có kiểu chính lớp gốc vẫn phải được xử lý. Việc chỉ liệt kê các kiểu con ở `case` không nhất thiết bao phủ giá trị của lớp gốc.

Dùng `abstract sealed class` khi kiểu gốc chỉ là một khái niệm trừu tượng và không nên được khởi tạo, hoặc bổ sung nhánh xử lý phù hợp khi gốc là lớp concrete.

## 14. Lưu ý khi thiết kế và phát triển API

### 14.1. Một tập biến thể được kiểm soát không có nghĩa sẽ không thay đổi

`sealed` cho phép thay đổi danh sách biến thể bằng cách sửa mã nguồn và biên dịch lại. Nó không đóng băng vĩnh viễn hợp đồng API.

Khi thêm một subtype mới:

- Xác định kiểu con trực tiếp nào phải được thêm vào `permits`.
- Kiểm tra mọi `switch` xử lý kiểu cha và cập nhật các nhánh tương ứng.
- Kiểm tra serialization, mapping, dữ liệu lưu trữ hoặc giao thức truyền nhận nếu chúng phụ thuộc vào danh sách biến thể.
- Biên dịch và thử nghiệm lại các thành phần sử dụng API, đặc biệt nếu được phát hành thành các thư viện riêng.

### 14.2. Tránh dùng non-sealed khi không thực sự có điểm mở rộng

Một nhánh `non-sealed` có thể chứa số kiểu con không giới hạn về mặt mô hình. Điều này làm giảm khả năng liệt kê chính xác các kiểu lá của hệ phân cấp.

Nếu miền nghiệp vụ cần một tập biến thể hữu hạn và được kiểm soát hoàn toàn, hãy dùng `final` hoặc `sealed` tiếp ở nhánh tương ứng. Nếu có nhu cầu mở rộng bên ngoài rõ ràng, dùng `non-sealed` và định nghĩa hợp đồng hành vi cho nhánh đó.

### 14.3. Ưu tiên mô hình dữ liệu rõ ràng

Với các trạng thái không cần quan hệ kế thừa hành vi phức tạp, `sealed interface` kết hợp record thường đơn giản hơn một cây các lớp kế thừa nhiều tầng. Dùng `abstract sealed class` khi có lý do cụ thể để chia sẻ logic hoặc trạng thái mà record không thể kế thừa.

Cũng không cần dùng hệ phân cấp `sealed` cho mọi kiểu dữ liệu. Nếu chỉ có một tập hằng số không mang cấu trúc dữ liệu khác nhau, `enum` có thể phù hợp và dễ quản lý hơn.

## 15. Bài tập thực hành

### Bài tập 1: Phân loại mức truy cập

Thiết kế giao diện `AccessDecision` với hai biến thể:

- `Allowed(String role)`
- `Denied(String reason)`

Yêu cầu: dùng một giao diện `sealed`, hai record, và phương thức `message` sử dụng `switch` expression bao phủ cả hai trường hợp, không thêm `default` khi không cần.

### Bài tập 2: Mở một nhánh đặc biệt

Mở rộng mô hình với `ExternalDecision` để đối tác có thể bổ sung các loại quyết định truy cập mới.

Yêu cầu: xác định modifier cần dùng cho `ExternalDecision`, thêm nó vào `permits` của kiểu cha và cập nhật `switch` để mọi loại `ExternalDecision` được xử lý.

### Bài tập 3: Nhận diện lỗi

Cho đoạn mã:

~~~java
sealed interface Job permits LocalJob {
}

class LocalJob implements Job {
}

non-sealed class RemoteJob {
}
~~~

Câu hỏi:

1. Vì sao `LocalJob` không hợp lệ?
2. Vì sao `RemoteJob` không hợp lệ?
3. Nếu muốn `RemoteJob` là một kiểu trực tiếp của `Job` và cho phép kế thừa tiếp, cần thay đổi những khai báo nào?

Gợi ý: kiểu con trực tiếp của `sealed` phải xác định hướng kế thừa; `non-sealed` phải có cha trực tiếp `sealed`.

## 16. Ghi nhớ nhanh

- `final class`: kết thúc quyền kế thừa của lớp.
- `sealed class/interface`: kiểm soát các kiểu con **trực tiếp**, thường bằng `permits`.
- `non-sealed class/interface`: mở lại quyền kế thừa tại một nhánh trực tiếp của kiểu `sealed`.
- Kiểu con trực tiếp của `sealed` phải chọn trạng thái hợp lệ; record mặc nhiên `final`.
- Record có thể `implements sealed interface` nhưng không thể `extends` lớp do người dùng định nghĩa.
- Trong named module, các kiểu con trực tiếp phải ở cùng module; trong unnamed module, chúng phải ở cùng package.
- Có thể bỏ `permits` khi các kiểu con trực tiếp đủ điều kiện được khai báo trong cùng compilation unit và trình biên dịch suy luận được danh sách.
- Pattern matching `switch` có thể kiểm tra bao phủ các biến thể của một hệ phân cấp `sealed`, kể cả một nhánh `non-sealed` được bao phủ bằng kiểu cha của nhánh đó.
- `sealed` không tự xử lý `null`, không tự làm đối tượng bất biến và không thay thế thiết kế quyền truy cập của API.
- Khi thay đổi danh sách kiểu được phép, cần kiểm tra và biên dịch lại những thành phần xử lý các biến thể.

## Tài liệu tham khảo

Các quy tắc trong bài dựa trên đặc tả và hướng dẫn Oracle Java hiện hành, vốn áp dụng cho các tính năng `final`, `sealed`, `non-sealed` và record đã ổn định:

- [Java Language Specification — Class Modifiers, Sealed Classes, Permitted Subclasses (Java SE 26)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html)
- [Java Language Specification — Interfaces (Java SE 26)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html)
- [Java Language Specification — Switch Exhaustiveness (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html)
- [Oracle Java Language Guide — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/language/sealed-classes-interfaces.html)
- [Oracle Java Language Guide — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/26/language/pattern-matching-switch.html)
- [Oracle Java Language Guide — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html)

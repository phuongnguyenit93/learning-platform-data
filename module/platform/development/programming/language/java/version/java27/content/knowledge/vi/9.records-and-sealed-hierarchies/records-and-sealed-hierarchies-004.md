# Sealed class, sealed interface và danh sách `permits` trong Java 27

Trong nhiều ứng dụng, ta biết trước những dạng dữ liệu có thể xảy ra. Kết quả xử lý một khoản thanh toán có thể là thành công, thất bại hoặc chờ xác nhận; một nút trong cây biểu thức có thể là hằng số, phép cộng hoặc phép nhân. Nếu chỉ dùng interface thông thường, các thư viện hoặc thành phần khác vẫn có thể tạo thêm implementation không nằm trong mô hình ban đầu.

**Sealed class** và **sealed interface** cho phép tác giả API công bố những **kiểu con trực tiếp** được phép kế thừa hoặc triển khai một kiểu cha. Mệnh đề **`permits`** chính là danh sách các nhánh trực tiếp ấy. Các nhánh tiếp tục quyết định có đóng hoàn toàn, đóng có kiểm soát hay mở rộng tự do.

Đây là tính năng Java đã chính thức từ Java 17 và tiếp tục được hỗ trợ trong **Java 27**. Các cú pháp sealed, record và pattern matching trong `switch` được dùng trong bài đều là tính năng ổn định, không cần bật preview. Bài viết dựa trên đặc tả [JLS 27, chương 8: Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html), [chương 9: Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html) và [chương 14: Switch và Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html).

## 1. Phân biệt `sealed`, `final` và kiểu thông thường

| Khai báo | Khả năng mở rộng | Dùng khi |
| --- | --- | --- |
| `class` thông thường | Có thể kế thừa nếu đáp ứng quyền truy cập và các quy tắc Java | Muốn cho phép các lớp ngoài tiếp tục mở rộng |
| `interface` thông thường | Có thể được triển khai/kế thừa bởi kiểu khác | Thiết kế hợp đồng mở cho nhiều thành phần |
| `final class` | Không lớp nào được kế thừa | Lớp đã hoàn chỉnh, không cần lớp con |
| `sealed class` | Chỉ những **class** được cho phép mới trực tiếp kế thừa | Hệ phân cấp lớp có các nhánh đã biết |
| `sealed interface` | Chỉ những **class hoặc interface** được cho phép mới trực tiếp triển khai/kế thừa | Tập biến thể kết quả, sự kiện, AST |
| `non-sealed class/interface` | Mở lại một nhánh của sealed parent | Muốn kiểm soát cấp đầu nhưng mở rộng một nhánh cụ thể |

Sealed không đồng nghĩa với final: sealed vẫn có thể có kiểu con. Sealed cũng không đồng nghĩa với bất biến: một kiểu con hoàn toàn có thể giữ trạng thái thay đổi được. Nó giới hạn **hệ phân cấp kiểu**, không giới hạn số lượng đối tượng hay tự động kiểm tra dữ liệu của từng đối tượng.

Trong một mô hình kiểu cha chỉ đại diện cho khái niệm chung, thường dùng `abstract sealed class` hoặc `sealed interface`. Nhưng một `sealed class` vẫn có thể không phải abstract và có thể được khởi tạo trực tiếp nếu constructor của nó cho phép.

## 2. Khai báo sealed interface với `permits`

Xét ba trạng thái của một đơn hàng:

~~~~java
sealed interface OrderStatus permits Created, Shipped, Cancelled {
}

record Created(String orderId) implements OrderStatus {
}

record Shipped(String orderId, String trackingCode) implements OrderStatus {
}

record Cancelled(String orderId, String reason) implements OrderStatus {
}
~~~~

Các thành phần của khai báo:

1. `sealed interface OrderStatus` định nghĩa kiểu cha với danh sách implementation có kiểm soát.
2. `permits Created, Shipped, Cancelled` nêu tên **mọi nhánh trực tiếp được phép**.
3. Mỗi record có `implements OrderStatus` để xác nhận quan hệ trực tiếp.
4. Record **ngầm là final**, nên các nhánh trên không thể tiếp tục có subclass.

Đây là mô hình một giá trị thuộc **một trong ba dạng**. Người gọi làm việc với biến kiểu `OrderStatus`, nhưng mỗi dạng chứa dữ liệu thích hợp với nó.

Một kiểu mới không có trong danh sách sẽ bị compiler từ chối:

~~~~java
// VÍ DỤ SAI: Không có Unknown trong OrderStatus.permits.
final class Unknown implements OrderStatus {
}
~~~~

Không thể khắc phục bằng cách chỉ thêm `final`; phải chủ động chỉnh danh sách `permits` ở kiểu cha nếu đây thực sự là biến thể hợp lệ của miền nghiệp vụ.

## 3. Khai báo sealed class

Khi các nhánh cần kế thừa trạng thái và hành vi chung từ một lớp, có thể dùng sealed class:

~~~~java
import java.util.Objects;

abstract sealed class DeliveryFailure
        permits InvalidAddress, CarrierUnavailable {

    private final String message;

    protected DeliveryFailure(String message) {
        this.message = Objects.requireNonNull(message, "message");
    }

    public String message() {
        return message;
    }
}

final class InvalidAddress extends DeliveryFailure {
    InvalidAddress(String message) {
        super(message);
    }
}

final class CarrierUnavailable extends DeliveryFailure {
    CarrierUnavailable(String message) {
        super(message);
    }
}
~~~~

`DeliveryFailure` là `abstract` vì không có ý nghĩa tạo lỗi chung trực tiếp; `sealed` đảm bảo chỉ có hai class được phép trực tiếp kế thừa. Hai class con chọn `final` để đóng nhánh của mình.

**Khác biệt quan trọng:** một record không thể `extends` một sealed class do record đã kế thừa `java.lang.Record`. Muốn các biến thể là record, hãy dùng một sealed **interface** làm kiểu cha.

## 4. Quy tắc của `permits`

### 4.1. `permits` chỉ xuất hiện cùng `sealed`

~~~~java
// SAI: thiếu sealed nhưng lại có permits.
interface Response permits Ok, Error {
}
~~~~

Mệnh đề `permits` không thay thế `extends` hoặc `implements`. Nó chỉ công bố các kiểu **được quyền** tham gia hệ phân cấp; chính các kiểu con vẫn phải khai báo quan hệ kế thừa.

### 4.2. Các tên được liệt kê phải là kiểu con trực tiếp

Với sealed class, mỗi mục trong `permits` phải là một class **trực tiếp extends** lớp sealed. Với sealed interface, mỗi mục phải là một class **trực tiếp implements** hoặc interface **trực tiếp extends** sealed interface ấy.

~~~~java
sealed interface Message permits TextMessage, MediaMessage {
}

record TextMessage(String text) implements Message {
}

sealed interface MediaMessage extends Message permits PhotoMessage {
}

record PhotoMessage(String url) implements MediaMessage {
}
~~~~

Mối quan hệ:

~~~~text
Message (sealed interface)
├── TextMessage (record, implicit final)
└── MediaMessage (sealed interface)
    └── PhotoMessage (record, implicit final)
~~~~

`PhotoMessage` là **con gián tiếp** của `Message`, vì vậy nó xuất hiện trong `MediaMessage.permits`, không nằm trong `Message.permits`. Nếu liệt kê `PhotoMessage` trong `Message.permits` mà không có quan hệ trực tiếp, compiler sẽ báo lỗi.

Mỗi tên trong `permits` phải chỉ tới một kiểu truy cập được và không được lặp, kể cả khi cùng một kiểu được viết theo hai cách tên khác nhau. Thứ tự liệt kê không tạo ra thứ tự xử lý nghiệp vụ.

### 4.3. Hai phía của quan hệ phải khớp nhau

~~~~java
// SAI: B có trong permits nhưng không trực tiếp extends A.
sealed class A permits B {
}

final class B {
}
~~~~

Khai báo trên sai vì `B` không khai báo `extends A`. Ngược lại, một class trực tiếp `extends A` nhưng không nằm trong danh sách cho phép cũng không hợp lệ.

### 4.4. Giới hạn về module và package

Đặc tả Java 27 yêu cầu các nhánh sealed trực tiếp nằm trong cùng phạm vi quản lý:

| Cách tổ chức | Yêu cầu |
| --- | --- |
| Sealed parent nằm trong **named module** | Mọi kiểu con trực tiếp được `permits` cho phép phải thuộc **cùng named module** với parent |
| Sealed parent nằm trong **unnamed module** (thường gặp với classpath) | Mọi kiểu con trực tiếp phải thuộc **cùng package** với parent |

Trong named module, các kiểu con có thể ở các package khác nhau nếu vẫn cùng module và đáp ứng quyền truy cập. Trong unnamed module, chỉ cùng module là chưa đủ: chúng phải cùng package. Không thể đưa một implementation ở module hoàn toàn khác vào danh sách kiểu con trực tiếp bằng cách thêm tên của nó vào `permits`.

Sealed parent và các kiểu con cần tham chiếu qua lại trong `permits` và `extends`/`implements`. Vì vậy, Java yêu cầu chúng thuộc cùng phạm vi có thể quản lý và biên dịch với nhau.

### 4.5. Khi nào có thể bỏ `permits`?

Java cho phép **suy luận** danh sách kiểu con trực tiếp nếu chúng được khai báo trong **cùng compilation unit** (thường cùng tệp `.java`), có canonical name và thực sự trực tiếp kế thừa/triển khai kiểu cha.

~~~~java
// Toàn bộ ví dụ nằm trong TokenDemo.java.
sealed interface Token {
}

record IdentifierToken(String text) implements Token {
}

record NumberToken(int value) implements Token {
}

public class TokenDemo {
    public static void main(String[] args) {
        Token token = new NumberToken(42);
        System.out.println(token);
    }
}
~~~~

Compiler suy luận `Token` cho phép `IdentifierToken` và `NumberToken`. Không có `permits` tường minh vẫn hợp lệ.

**Điều kiện là cùng compilation unit, không phải chỉ cùng package.** Nếu tách các record sang tệp riêng, nên khai báo `permits IdentifierToken, NumberToken` tại interface cha. Các local class hoặc anonymous class không được tính là kiểu con suy luận qua cơ chế này vì chúng không có canonical name thích hợp. Nếu không có `permits` và cũng không có kiểu con trực tiếp hợp lệ để suy luận, khai báo sealed bị lỗi biên dịch.

## 5. Mỗi kiểu con trực tiếp phải chọn cách mở rộng

Java yêu cầu một class trực tiếp mở rộng sealed parent thể hiện rõ quyết định cho tương lai của nhánh:

| Modifier ở class con | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| `final` | Kết thúc nhánh | Không có subclass tiếp theo |
| `sealed` | Chia tiếp có kiểm soát | Phải cho biết hoặc suy luận các kiểu con trực tiếp của nhánh |
| `non-sealed` | Mở lại nhánh | Các kiểu khác có thể kế thừa theo quyền truy cập thông thường |

Đối với **interface con trực tiếp**, chỉ có hai lựa chọn `sealed` và `non-sealed`; interface không thể khai báo `final`. Đối với **record**, tính `final` đã có ngầm; đối với **enum** triển khai sealed interface, trạng thái đóng kế thừa được xác định ngầm bởi quy tắc enum.

### 5.1. `final` kết thúc nhánh

~~~~java
sealed interface UserEvent permits LoginEvent, LogoutEvent {
}

record LoginEvent(String userId) implements UserEvent {
}

final class LogoutEvent implements UserEvent {
    private final String userId;

    LogoutEvent(String userId) {
        this.userId = userId;
    }
}
~~~~

`LoginEvent` ngầm final do là record. `LogoutEvent` là class thường nên ghi final tường minh.

### 5.2. `sealed` tiếp tục chia nhánh có kiểm soát

~~~~java
sealed interface Command permits ReadCommand, WriteCommand {
}

record ReadCommand(String key) implements Command {
}

sealed interface WriteCommand extends Command
        permits CreateCommand, DeleteCommand {
}

record CreateCommand(String key, String value)
        implements WriteCommand {
}

record DeleteCommand(String key) implements WriteCommand {
}
~~~~

Ở cấp `Command`, các nhánh trực tiếp chỉ là `ReadCommand` và `WriteCommand`. Ở cấp `WriteCommand`, chúng là `CreateCommand` và `DeleteCommand`. Mỗi cấp quản lý danh sách `permits` riêng của mình.

### 5.3. `non-sealed` mở lại một nhánh cụ thể

~~~~java
sealed interface Notification
        permits EmailNotification, ExternalNotification {
}

record EmailNotification(String recipient, String body)
        implements Notification {
}

non-sealed interface ExternalNotification extends Notification {
}

record ChatNotification(String channel, String body)
        implements ExternalNotification {
}

final class PushNotification implements ExternalNotification {
}
~~~~

`ChatNotification` và `PushNotification` không phải kiểu con **trực tiếp** của `Notification`, nên không cần nằm trong `Notification.permits`. Chúng chỉ triển khai nhánh `ExternalNotification` đã được mở lại. Các implementation khác có thể tiếp tục xuất hiện nếu có quyền truy cập phù hợp.

Hệ quả: một parent sealed không bảo đảm có **số lượng lớp lá hữu hạn** nếu chứa nhánh `non-sealed`. Nó bảo đảm một tập **nhánh trực tiếp** có kiểm soát.

`non-sealed` chỉ hợp lệ khi class/interface có sealed superclass hoặc sealed superinterface **trực tiếp**. Không thể tùy ý đặt `non-sealed` lên kiểu thông thường không có sealed parent rồi mong nó có ý nghĩa.

## 6. Chọn sealed + record hay enum?

Khi những biến thể mang dữ liệu khác nhau, sealed interface kết hợp record thường biểu đạt chính xác hơn enum:

~~~~java
sealed interface PaymentOutcome permits Paid, Declined, Pending {
}

record Paid(String transactionId) implements PaymentOutcome {
}

record Declined(String reason) implements PaymentOutcome {
}

record Pending(long estimatedSeconds) implements PaymentOutcome {
}
~~~~

Mỗi dạng là một kiểu riêng với dữ liệu riêng. Trái lại, nếu cần một tập tên hằng và không có cấu trúc dữ liệu khác nhau cho từng trường hợp, enum vẫn đơn giản:

~~~~java
enum PaymentState {
    PAID,
    DECLINED,
    PENDING
}
~~~~

Enum cũng có thể trực tiếp triển khai một sealed interface nếu được liệt kê trong `permits`:

~~~~java
sealed interface ProcessingResult permits Finished, Aborted {
}

record Finished(int processedCount) implements ProcessingResult {
}

enum Aborted implements ProcessingResult {
    CANCELLED_BY_USER,
    TIMEOUT
}
~~~~

Không ghi `final enum`; Java xác định trạng thái kế thừa của enum một cách ngầm định. Với record cũng không ghi `final record`.

## 7. Sealed hỗ trợ xử lý đầy đủ bằng `switch`

Trong Java 27, pattern matching cho `switch` là tính năng ổn định. Với sealed interface có các nhánh đóng, compiler kiểm tra liệu `switch expression` đã bao phủ toàn bộ trường hợp hay chưa.

Đây là chương trình hoàn chỉnh có thể lưu thành `PaymentExample.java`:

~~~~java
import java.util.Objects;

sealed interface PaymentOutcome permits Paid, Declined, Pending {
}

record Paid(String transactionId) implements PaymentOutcome {
}

record Declined(String reason) implements PaymentOutcome {
}

record Pending(long estimatedSeconds) implements PaymentOutcome {
}

public class PaymentExample {
    static String describe(PaymentOutcome outcome) {
        return switch (Objects.requireNonNull(outcome, "outcome")) {
            case Paid paid ->
                    "Đã thanh toán: " + paid.transactionId();
            case Declined declined ->
                    "Bị từ chối: " + declined.reason();
            case Pending pending ->
                    "Đang xử lý, dự kiến " + pending.estimatedSeconds() + " giây";
        };
    }

    public static void main(String[] args) {
        PaymentOutcome result = new Paid("TX-1001");
        System.out.println(describe(result));
    }
}
~~~~

Không cần `default`, vì ba nhánh `Paid`, `Declined`, `Pending` đã bao phủ toàn bộ tập kiểu con được phép và đều không thể có subclass.

Nếu sau này thêm biến thể `Refunded` vào `PaymentOutcome.permits`, các `switch expression` chưa xử lý biến thể này sẽ không còn đầy đủ khi được biên dịch lại. Nhờ đó compiler giúp phát hiện những nhánh nghiệp vụ còn thiếu.

### 7.1. Khi có nhánh `non-sealed`

Một nhánh `non-sealed` cho phép thêm các kiểu con chưa biết trước. Tuy nhiên, pattern mang kiểu của **cả nhánh mở** vẫn có thể bao phủ tất cả các lớp con của nhánh:

~~~~java
sealed interface Result permits Success, ExtensionFailure {
}

record Success(String value) implements Result {
}

non-sealed interface ExtensionFailure extends Result {
    String message();
}

record RemoteFailure(String message) implements ExtensionFailure {
}

class ResultFormatter {
    static String format(Result result) {
        return switch (result) {
            case Success success -> success.value();
            case ExtensionFailure failure -> failure.message();
        };
    }
}
~~~~

`case ExtensionFailure failure` xử lý mọi implementation hiện tại hoặc sau này của `ExtensionFailure`. Compiler vẫn thấy `switch` đầy đủ với kiểu cha `Result`.

### 7.2. Xử lý `null` và guard

Sealed không khiến `null` trở thành một subtype. Mặc định, khi selector của `switch` là null mà không có nhãn xử lý null thích hợp, Java ném `NullPointerException`. Nếu hợp đồng chấp nhận null, có thể thêm:

~~~~java
static String describeNullable(PaymentOutcome outcome) {
    return switch (outcome) {
        case null -> "Chưa có kết quả";
        case Paid paid -> "Đã thanh toán: " + paid.transactionId();
        case Declined declined -> "Bị từ chối: " + declined.reason();
        case Pending pending -> "Đang xử lý";
    };
}
~~~~

Nếu đầu vào null bị cấm, dùng `Objects.requireNonNull` ở biên phương thức như ví dụ chính.

Guard dạng `case SomeType value when condition ->` chỉ nhận những giá trị thỏa mãn **cả kiểu và điều kiện**. Do đó một case có guard không mặc nhiên bao phủ toàn bộ subtype; cần đọc quy tắc exhaustiveness của `switch` khi dùng các guard.

### 7.3. Thay đổi hệ phân cấp sau khi đã biên dịch

Compiler xác nhận tính đầy đủ dựa trên các subtype đã biết **lúc biên dịch**. Nếu thư viện chứa sealed type được cập nhật nhưng chương trình phụ thuộc không được biên dịch lại, có thể xảy ra lỗi khi chạy hoặc vấn đề tương thích nhị phân. Khi đổi danh sách `permits` trong API được nhiều nơi sử dụng, hãy xây dựng và kiểm tra lại các thành phần phụ thuộc.

Không nên thêm `default` vào mọi `switch` trên tập nhánh khép kín chỉ để tránh sửa các case sau này. Làm vậy có thể che đi chính cảnh báo hữu ích khi bổ sung một biến thể mới. Với hệ mở một phần, hãy dùng một case bao phủ nhánh mở hoặc fallback đã được thiết kế có chủ đích.

## 8. Reflection: kiểm tra các subtype được phép

API `java.lang.Class` cung cấp:

- `Class.isSealed()`: cho biết class/interface có sealed hay không.
- `Class.getPermittedSubclasses()`: trả về những kiểu con **trực tiếp** được phép mà runtime có thể lấy được.

Ví dụ hoàn chỉnh, lưu thành `SealedReflectionDemo.java`:

~~~~java
import java.util.Arrays;

sealed interface Event permits Started, Stopped {
}

record Started(long atMillis) implements Event {
}

record Stopped(long atMillis) implements Event {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        Class<Event> type = Event.class;
        System.out.println(type.isSealed()); // true

        Class<?>[] direct = type.getPermittedSubclasses();
        String[] names = Arrays.stream(direct)
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);
        System.out.println(Arrays.toString(names));
        // [Started, Stopped]

        System.out.println(Started.class.isSealed()); // false
    }
}
~~~~

API **không bảo đảm thứ tự** kết quả `getPermittedSubclasses()`. Với kiểu không sealed, phương thức trả về **null**, không phải mảng rỗng. Với kiểu sealed, nó trả về mảng khác null, nhưng có thể không chứa một subtype nếu class loader không lấy được Class tương ứng. Nên kiểm tra `isSealed()` trước khi dùng.

Reflection phục vụ công cụ kiểm tra cấu trúc, sinh tài liệu hoặc phân tích hệ kiểu. Đối với xử lý nghiệp vụ thông thường, hãy ưu tiên compiler kiểm tra kiểu và `switch` tĩnh khi phù hợp.

## 9. Những lỗi thiết kế và lỗi biên dịch thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Subclass báo không được phép kế thừa | Không nằm trong `permits` của parent trực tiếp | Cập nhật danh sách đúng cấp nếu nghiệp vụ cho phép |
| Đã có trong `permits` mà vẫn lỗi | Thiếu quan hệ `extends`/`implements` trực tiếp | Khai báo đúng quan hệ hoặc bỏ tên không hợp lệ |
| Class con trực tiếp thiếu modifier | Chưa chọn `final`, `sealed` hoặc `non-sealed` | Quyết định và công bố cách mở rộng của nhánh |
| Interface con trực tiếp thiếu modifier | Chưa chọn `sealed` hay `non-sealed` | Khai báo một trong hai |
| `permits` xuất hiện ở kiểu thông thường | Chưa khai báo `sealed` | Thêm `sealed` hoặc bỏ `permits` |
| `non-sealed` báo lỗi | Không có sealed parent trực tiếp | Bỏ modifier hoặc sửa thiết kế hệ phân cấp |
| Subtype ở named module khác | Vi phạm giới hạn cùng module | Tổ chức hệ sealed trong cùng named module |
| Subtype khác package trong unnamed module | Vi phạm giới hạn cùng package | Đặt lại đúng package hoặc tổ chức named module phù hợp |
| Bỏ `permits` rồi tách subtype ra tệp khác | Compiler không thể suy luận từ compilation unit hiện tại | Viết `permits` tường minh |
| `switch expression` thiếu case | Chưa bao phủ hết nhánh sealed | Bổ sung các case và biên dịch lại |
| `switch` lỗi null | Không có nhánh xử lý null | Dùng `case null` hoặc từ chối null theo hợp đồng |
| Cố khai báo record extends sealed class | Record đã kế thừa `java.lang.Record` | Dùng sealed interface hoặc class thông thường |

### Sealed không thay thế mọi giới hạn thiết kế

Sealed không tự kiểm tra dữ liệu đầu vào, không biến đối tượng thành bất biến, không ngăn tác dụng phụ và không thay thế các quy tắc truy cập. Một class được `permits` vẫn có thể nhận tham số không hợp lệ nếu constructor của nó không kiểm tra. Một class `final` vẫn có thể thay đổi trạng thái bên trong.

Đặc biệt, sealed không thích hợp nếu mục đích chính của API là để các plugin **ngoài module** trực tiếp triển khai một interface mới. Khi cần extension point, hãy dùng interface mở hoặc thiết kế một nhánh `non-sealed` được công bố có chủ đích.

## 10. Tiêu chí lựa chọn trong dự án Java 27

| Trường hợp | Cách biểu diễn phù hợp |
| --- | --- |
| Tập hằng đơn giản, không có dữ liệu riêng cho từng hằng | `enum` |
| Một vài loại kết quả mang dữ liệu khác nhau | `sealed interface` kết hợp `record` |
| Các lớp con cần chung trạng thái/hành vi từ lớp cha | `abstract sealed class` và các class con |
| Phân cấp cần kiểm soát nhiều cấp | Nhiều tầng `sealed` với `permits` riêng |
| Muốn chừa một nhánh mở cho phần mở rộng | `non-sealed` tại đúng nhánh trực tiếp |
| Interface dành cho nhà phát triển plugin ngoài dự án | Interface thường hoặc nhánh mở có chủ đích |

Khi phát triển sealed API, hãy xem việc thêm, xóa hoặc đổi tên subtype được phép là **thay đổi hợp đồng**. Một biến thể mới có thể làm các switch và logic xử lý của client cần cập nhật. Nên biên dịch lại các module phụ thuộc, kiểm tra xử lý nhánh còn thiếu và công bố sự thay đổi trong tài liệu API.

Checklist trước khi hoàn thành thiết kế:

- [ ] Kiểu cha là `sealed class` hoặc `sealed interface` đúng với mục đích và khả năng kế thừa.
- [ ] `permits` liệt kê đúng những **kiểu con trực tiếp**, không trùng lặp.
- [ ] Các kiểu con có quan hệ `extends`/`implements` tương ứng.
- [ ] Các kiểu nằm cùng named module, hoặc cùng package nếu ở unnamed module.
- [ ] Class trực tiếp chọn `final`, `sealed` hoặc `non-sealed`; record/enum theo quy tắc ngầm.
- [ ] Interface con trực tiếp chọn `sealed` hoặc `non-sealed`.
- [ ] Nếu bỏ `permits`, các subtype trực tiếp đủ điều kiện suy luận trong **cùng compilation unit**.
- [ ] `switch` xử lý đủ subtype, cả chính sách null nếu có.
- [ ] Dữ liệu của từng subtype được kiểm tra và bảo vệ bất biến khi cần.
- [ ] Các thành phần phụ thuộc được biên dịch và kiểm tra lại nếu hệ sealed thay đổi.

## Tài liệu tham khảo

- [JLS Java SE 27, mục 8.1.1.2 và 8.1.6 – Sealed Classes và Permitted Direct Subclasses](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.1.6).
- [JLS Java SE 27, mục 9.1.1.4 và 9.1.4 – Sealed Interfaces và Permitted Direct Subinterfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.1.4).
- [JLS Java SE 27, mục 14.11.1 – Exhaustive Switch Blocks](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.11.1).
- [Java SE 27 API: Class.isSealed() và Class.getPermittedSubclasses()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html).

Sealed class và sealed interface xác định ranh giới cho một hệ phân cấp kiểu mà tác giả muốn kiểm soát. **`permits` chỉ liệt kê các nhánh trực tiếp**, còn `final`, `sealed` và `non-sealed` quyết định cách những nhánh đó có thể phát triển tiếp. Hiểu đúng mối quan hệ này giúp thiết kế mô hình dữ liệu chặt chẽ, kết hợp record thuận lợi và khai thác khả năng kiểm tra tính đầy đủ của compiler trong Java 27.

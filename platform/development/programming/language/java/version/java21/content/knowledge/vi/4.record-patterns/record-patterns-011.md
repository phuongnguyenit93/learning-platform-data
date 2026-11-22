# Xử lý MatchException khi quá trình matching không hoàn tất bình thường

Trong Java 21, pattern matching có thể kết thúc theo hai cách khác nhau: một giá trị không khớp pattern theo cách bình thường, hoặc quá trình matching bị gián đoạn bởi một lỗi. Trường hợp thứ hai có thể phát sinh `MatchException`. Ngoài ra, một `switch` đã được compiler xác định là exhaustive vẫn có thể gặp `MatchException` nếu các kiểu dữ liệu thực tế lúc chạy khác với những kiểu đã dùng khi biên dịch.

Bài này giải thích các tình huống đó, cách phân biệt `MatchException` với một lần không khớp pattern thông thường và cách xử lý lỗi ở đúng ranh giới của ứng dụng. Các ví dụ dùng cú pháp Record Patterns và Pattern Matching for `switch` đã trở thành tính năng chính thức trong Java 21; không cần bật preview feature.

## 1. MatchException là gì?

`java.lang.MatchException` là một lớp `final` kế thừa `RuntimeException`, được bổ sung từ Java 21. Nó biểu thị một lỗi bất ngờ trong quá trình pattern matching.

Có hai nhóm tình huống chính:

- Một record pattern cần gọi accessor để lấy giá trị component, nhưng accessor ném exception. Java kết thúc quá trình matching bằng `MatchException` và đặt exception ban đầu vào `getCause()`.
- Một enhanced `switch` hoặc `switch` expression được xem là exhaustive khi biên dịch, nhưng lúc chạy không có case label nào áp dụng cho giá trị đầu vào. Trường hợp này có thể xuất hiện khi kiểu dữ liệu thay đổi sau khi class chứa `switch` đã được biên dịch, hoặc khi các nested pattern không khớp với dữ liệu thực tế.

Không phải mọi lần pattern không khớp đều tạo ra `MatchException`. Nếu đối tượng sai kiểu, hoặc một component không thỏa pattern, quá trình matching có thể chỉ trả về kết quả không khớp để chương trình xét nhánh tiếp theo. `MatchException` dành cho trường hợp matching bị gián đoạn hoặc một `switch` exhaustive không tìm được nhánh tại runtime.

## 2. Accessor của record ném exception

Khi Java kiểm tra một record pattern, runtime gọi accessor tương ứng của từng record component để lấy giá trị. Ví dụ pattern `SensorReading(int celsius)` cần gọi `celsius()` trên đối tượng `SensorReading`.

Accessor có thể được viết tường minh trong record. Nếu accessor đó ném exception, quá trình matching hoàn tất bất thường và Java ném `MatchException`. Exception gốc được giữ trong `cause`.

~~~java
record SensorReading(int celsius) {
    public int celsius() {
        if (celsius < -273) {
            throw new IllegalStateException("Giá trị thấp hơn giới hạn hợp lệ");
        }
        return celsius;
    }
}

static String describe(Object value) {
    return switch (value) {
        case SensorReading(int celsius) -> celsius + " °C";
        default -> "Không phải SensorReading";
    };
}
~~~

Khi gọi `describe(new SensorReading(-300))`, Java phải gọi `celsius()` để lấy component. Accessor ném `IllegalStateException`, vì vậy lời gọi `describe` kết thúc bằng `MatchException` có cause là `IllegalStateException`.

Nhánh `default` không xử lý được lỗi này. `default` chỉ được xét khi quá trình xác định case label diễn ra bình thường và không có pattern nào khớp. Nếu accessor ném exception trong lúc Java đang thử một record pattern, quá trình chọn case đã kết thúc bất thường; Java không tiếp tục thử `default`.

Quy tắc này cũng áp dụng khi record pattern được dùng trong `instanceof`. Một lần kiểm tra `instanceof` thông thường có thể trả về `false`, nhưng nếu accessor của record pattern ném exception thì lời gọi có thể kết thúc bằng `MatchException`.

## 3. Switch exhaustive không tìm thấy nhánh lúc runtime

Java 21 cho phép compiler xác định tính exhaustive của pattern switch dựa trên kiểu selector, các nhánh pattern và tập subtype của sealed hierarchy. Với enum, compiler cũng có thể xác định tính đầy đủ từ các enum constant đã biết.

Ví dụ:

~~~java
sealed interface Payment permits Cash, Card {}

record Cash(int amount) implements Payment {}
record Card(String lastFour) implements Payment {}

static String describe(Payment payment) {
    return switch (payment) {
        case Cash(int amount) -> "Tiền mặt: " + amount;
        case Card(String lastFour) -> "Thẻ kết thúc bằng " + lastFour;
    };
}
~~~

Ở thời điểm biên dịch, hai record `Cash` và `Card` bao phủ toàn bộ subtype được khai báo trong `Payment`, nên switch expression là exhaustive và không cần `default`.

Giả sử một phiên bản thư viện mới bổ sung `BankTransfer` vào sealed hierarchy:

~~~java
sealed interface Payment permits Cash, Card, BankTransfer {}

record Cash(int amount) implements Payment {}
record Card(String lastFour) implements Payment {}
record BankTransfer(String reference) implements Payment {}
~~~

Nếu ứng dụng chỉ biên dịch lại thư viện chứa `Payment` và `BankTransfer`, nhưng vẫn chạy class cũ chứa phương thức `describe`, đối tượng `BankTransfer` có thể đi vào switch mà không khớp hai nhánh đã biên dịch. Khi đó Java ném `MatchException`.

Tình huống tương tự có thể xảy ra khi một enum được bổ sung constant mới nhưng class chứa switch expression exhaustive vẫn là bytecode cũ. Đây là vấn đề không đồng bộ phiên bản giữa các class được biên dịch riêng, không phải lỗi cú pháp của pattern switch.

Cách xử lý:

- Khi thay đổi sealed hierarchy hoặc enum, biên dịch lại các module có switch phụ thuộc vào kiểu đó.
- Đảm bảo các artifact được triển khai đồng bộ, tránh ghép một thư viện mới với consumer còn bytecode cũ.
- Nếu ứng dụng cần tiếp tục chạy khi gặp subtype hoặc enum constant mới, thêm nhánh `default` với hành vi fallback được xác định rõ. Đổi lại, compiler không còn buộc người viết switch liệt kê mọi subtype đã biết.

Nên giữ switch exhaustive khi muốn compiler phát hiện thay đổi của mô hình dữ liệu trong quá trình build. Chỉ dùng `default` khi khả năng tiếp nhận giá trị chưa biết là một yêu cầu tương thích có chủ đích.

## 4. Null trong nested record pattern

Một record pattern không khớp với chính giá trị `null`. Với nested record pattern, một component có thể là `null` dù compiler đã xác định các pattern bao phủ đầy đủ các subtype có thể có.

Xét mô hình:

~~~java
sealed interface Delivery permits EmailDelivery, SmsDelivery {}

record EmailDelivery(String address) implements Delivery {}
record SmsDelivery(String number) implements Delivery {}
record Envelope(Delivery delivery) {}

static String route(Envelope envelope) {
    return switch (envelope) {
        case Envelope(EmailDelivery email) -> "Email: " + email.address();
        case Envelope(SmsDelivery sms) -> "SMS: " + sms.number();
    };
}
~~~

Hai nhánh bao phủ các subtype được phép của `Delivery`. Tuy nhiên, nếu đầu vào là `new Envelope(null)`, component `delivery` không khớp `EmailDelivery` cũng không khớp `SmsDelivery`. Vì switch được xem là exhaustive khi biên dịch nhưng không tìm được nhánh phù hợp lúc chạy, Java ném `MatchException`.

Nếu `null` là trạng thái hợp lệ của mô hình, hãy xử lý rõ ràng:

~~~java
static String route(Envelope envelope) {
    return switch (envelope) {
        case null -> "Envelope không tồn tại";
        case Envelope(Delivery delivery) -> {
            if (delivery == null) {
                yield "Chưa có phương thức giao hàng";
            }
            yield switch (delivery) {
                case EmailDelivery email -> "Email: " + email.address();
                case SmsDelivery sms -> "SMS: " + sms.number();
            };
        }
    };
}
~~~

Ở vị trí component pattern, type pattern không điều kiện đối với chính kiểu component (ở đây là `Delivery delivery`) có thể khớp cả `null` khi nó xuất hiện trực tiếp trong record pattern. Vì vậy ví dụ có thể lấy component ra, kiểm tra `delivery == null`, rồi mới thực hiện switch bên trong.

Cần phân biệt hai vị trí của `null`:

- `envelope == null`: selector của switch là `null`. Nếu không có `case null`, Java ném `NullPointerException`.
- `envelope` khác `null` nhưng `envelope.delivery() == null`: outer record pattern có thể được kiểm tra, nhưng nested pattern không khớp component. Với switch exhaustive như ví dụ trước, Java có thể ném `MatchException`.

Tương tự, với nested record pattern như `Customer(Address(var city))`, nếu `Customer` tồn tại nhưng component `address` là `null`, pattern lồng bên trong không khớp. Nếu switch được compiler xem là exhaustive, tình huống này có thể dẫn đến `MatchException`. Nếu `null` không được phép, hãy xác thực dữ liệu khi tạo record; nếu được phép, hãy tạo nhánh xử lý riêng.

## 5. Phân biệt MatchException với các kết quả khác

| Tình huống | Kết quả thường gặp |
|---|---|
| Giá trị không thuộc kiểu của type pattern | Pattern không khớp; `instanceof` trả về `false` hoặc switch xét case tiếp theo |
| Một component không thỏa component pattern | Record pattern không khớp; switch xét case tiếp theo |
| Accessor của record component ném exception | `MatchException`; exception gốc nằm trong `getCause()` |
| Switch expression hoặc enhanced switch không có case phù hợp với selector khác `null` | `MatchException` |
| Selector của switch là `null` và không có `case null` | `NullPointerException` |
| Nested record pattern không khớp vì component lồng bên trong là `null`, trong khi switch được xem là exhaustive | Có thể phát sinh `MatchException` |

Bảng này giúp tránh một cách xử lý sai thường gặp: bắt `MatchException` cho mọi lần pattern không khớp. Hãy để các trường hợp không khớp bình thường đi theo luồng điều khiển của pattern matching; chỉ xử lý exception khi quá trình matching thực sự kết thúc bất thường.

## 6. Bắt và xử lý MatchException

Vì `MatchException` là unchecked exception, phương thức không cần khai báo `throws`. Hãy bắt nó ở ranh giới có đủ ngữ cảnh để ghi log, chuyển đổi lỗi hoặc quyết định có thể tiếp tục xử lý hay không.

~~~java
static String safeDescribe(Object value) {
    try {
        return describe(value);
    } catch (MatchException ex) {
        Throwable cause = ex.getCause();

        if (cause instanceof IllegalStateException) {
            throw new IllegalArgumentException(
                "Không thể đọc component của SensorReading",
                cause
            );
        }

        // Trường hợp không xác định được nguyên nhân: giữ nguyên lỗi.
        throw ex;
    }
}
~~~

Một số nguyên tắc khi xử lý:

- Kiểm tra `getCause()` để tìm exception gốc nếu lỗi phát sinh từ accessor. Không giả định cause luôn khác `null`, vì `MatchException` cũng có thể phát sinh do switch không tìm được nhánh.
- Giữ lại cause khi chuyển đổi sang exception của tầng nghiệp vụ. Điều này giúp truy vết lỗi ban đầu.
- Ghi nhận stack trace của `MatchException` và cause. Theo API Java 21, trường hợp accessor ném exception không ghi exception vào danh sách suppressed của `MatchException`.
- Chỉ chuyển đổi hoặc phục hồi khi biết nguyên nhân và có hành vi thay thế hợp lệ. Không bắt rồi bỏ qua lỗi, cũng không retry mù quáng.
- Tránh bắt `RuntimeException` quá rộng nếu chỉ muốn xử lý lỗi pattern matching; bắt đúng `MatchException` giúp giữ nguyên ý nghĩa của các lỗi runtime khác.

Không nên phụ thuộc vào nội dung message của `MatchException` để quyết định nghiệp vụ. Hãy dựa vào loại exception, cause, stack trace và trạng thái dữ liệu thực tế.

## 7. Ngăn ngừa lỗi từ thiết kế record và quy trình build

### Giữ accessor đơn giản

Record accessor thường chỉ nên trả về component tương ứng. Tránh đưa I/O, truy vấn cơ sở dữ liệu, gọi dịch vụ mạng hoặc thay đổi trạng thái vào accessor. Record pattern có thể gọi accessor trong lúc kiểm tra pattern, vì vậy một accessor có side effect hoặc phụ thuộc môi trường bên ngoài sẽ làm matching khó dự đoán.

Nếu cần bảo vệ bất biến dữ liệu, hãy kiểm tra ở canonical constructor:

~~~java
record SensorReading(int celsius) {
    SensorReading {
        if (celsius < -273) {
            throw new IllegalArgumentException("Nhiệt độ không hợp lệ");
        }
    }
}
~~~

Khi dữ liệu sai, lỗi được phát hiện lúc tạo record. Accessor được sinh tự động có thể trả component mà không cần kiểm tra lại hoặc thực hiện công việc có thể thất bại.

### Xác định chính sách null

Nếu component bắt buộc phải có giá trị, kiểm tra điều kiện đó trong constructor, chẳng hạn dùng `Objects.requireNonNull`. Nếu `null` có ý nghĩa nghiệp vụ, hãy thể hiện nó trong các nhánh pattern hoặc xử lý trước khi thực hiện nested matching.

Đừng chỉ dựa vào việc compiler chấp nhận một switch là exhaustive để suy ra mọi tổ hợp dữ liệu runtime đều hợp lệ. Tính exhaustive của nested pattern có thể dựa trên tập kiểu, trong khi dữ liệu component vẫn có thể chứa `null`.

### Đồng bộ binary khi thay đổi mô hình

Khi thêm subtype vào sealed hierarchy hoặc thêm enum constant, hãy build lại các module phụ thuộc và kiểm thử ứng dụng với đúng tập artifact sẽ triển khai. Nếu thư viện và consumer được phát hành riêng, cần có quy trình nâng phiên bản consumer tương ứng.

Nếu cần tương thích với giá trị mới từ thư viện được nâng cấp độc lập, thiết kế nhánh `default` để xử lý trạng thái chưa biết và ghi log đủ thông tin để nhóm có thể cập nhật sau đó.

## 8. Checklist chẩn đoán

Khi gặp `MatchException`, kiểm tra theo thứ tự:

1. Xác định exception xảy ra tại record pattern hay tại điểm kết thúc của switch.
2. Đọc stack trace để tìm switch hoặc biểu thức pattern đang được đánh giá.
3. Kiểm tra `getCause()`. Nếu cause có giá trị, xác định accessor nào đã ném exception và vì sao.
4. Nếu không có cause, kiểm tra xem switch exhaustive có đang chạy với subtype, enum constant hoặc dữ liệu nested `null` chưa được tính đến hay không.
5. Đối chiếu phiên bản class chứa switch với phiên bản sealed hierarchy, enum và record đang được nạp ở runtime.
6. Kiểm tra lại chính sách null ở selector và từng record component.
7. Tạo test cho accessor có thể lỗi, component null và các subtype hợp lệ; sau khi thay đổi hierarchy, build lại toàn bộ consumer liên quan.

## Tài liệu tham khảo chính thức

- [Java SE 21 API: MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [Java Language Specification 21 — 14.30.2 Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java Language Specification 21 — 14.11.3 Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3)
- [Java Language Specification 21 — 15.28.2 Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441)


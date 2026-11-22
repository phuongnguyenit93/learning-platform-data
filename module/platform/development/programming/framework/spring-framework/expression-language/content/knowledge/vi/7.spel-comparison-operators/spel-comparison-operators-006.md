# Toán tử instanceof và kiểm tra kiểu

Trong Java, một biến có thể được khai báo bằng kiểu tổng quát như Object, một lớp cha hoặc một interface, trong khi đối tượng thực tế tại thời điểm chạy thuộc về một lớp cụ thể. Khi quy tắc cần xử lý khác nhau tùy loại đối tượng, ứng dụng phải kiểm tra kiểu thực tế trước khi chọn nhánh xử lý.

SpEL cung cấp toán tử instanceof để kiểm tra một giá trị có phải là thể hiện của một kiểu hay không. Kết quả là Boolean: true nếu đối tượng thuộc kiểu được chỉ định hoặc một kiểu con tương thích; false nếu không phù hợp. Toán tử này hữu ích khi biểu thức nhận dữ liệu đa hình, nhưng cần hiểu cách khai báo kiểu, cách context phân giải kiểu và giới hạn của kiểm tra kiểu ở runtime.

## 1. Vì sao cần kiểm tra kiểu?

Giả sử hệ thống nhận nhiều loại sự kiện thông qua cùng một interface:

    public interface DomainEvent {
    }

    public class OrderCreatedEvent implements DomainEvent {
        private final String orderId;

        public OrderCreatedEvent(String orderId) {
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public class PaymentFailedEvent implements DomainEvent {
        private final String paymentId;
        private final String reason;

        public PaymentFailedEvent(String paymentId, String reason) {
            this.paymentId = paymentId;
            this.reason = reason;
        }

        public String getPaymentId() {
            return paymentId;
        }

        public String getReason() {
            return reason;
        }
    }

Một luồng xử lý có thể nhận DomainEvent, nhưng cần áp dụng quy tắc riêng cho sự kiện tạo đơn hàng và sự kiện thanh toán thất bại. Kiểu khai báo của biến chỉ cho biết nó là DomainEvent; kiểu runtime mới cho biết đối tượng cụ thể là OrderCreatedEvent hay PaymentFailedEvent.

Trong Java, phép kiểm tra quen thuộc là:

    if (event instanceof OrderCreatedEvent) {
        // xử lý sự kiện tạo đơn hàng
    }

SpEL có toán tử cùng tên để đưa điều kiện kiểm tra kiểu vào một biểu thức. Điều này hữu ích khi một rule được lưu dưới dạng biểu thức hoặc khi cấu hình Spring cần lựa chọn theo loại đối tượng.

## 2. Cú pháp instanceof trong SpEL

Cú pháp cơ bản có dạng:

    expression instanceof T(type-name)

Vế trái là biểu thức tạo ra đối tượng cần kiểm tra. Vế phải dùng toán tử T(...) để tham chiếu đến một kiểu Java.

Ví dụ kiểm tra một giá trị có phải chuỗi hay không:

    #value instanceof T(java.lang.String)

Một số kiểu trong package java.lang có thể được viết ngắn hơn:

    #value instanceof T(String)

Với kiểu thuộc package khác, nên ghi tên đầy đủ để tránh nhầm lẫn:

    #event instanceof T(com.example.events.OrderCreatedEvent)

Không đặt tên kiểu trong dấu nháy. Biểu thức sau chỉ so sánh với một chuỗi literal và không phải phép kiểm tra kiểu:

    #value instanceof 'java.lang.String'

Tương tự, viết tên lớp trực tiếp mà không có T(...) không tạo ra type reference:

    #value instanceof String

Hãy dùng T(...) ở vế phải để SpEL có thể phân giải tên lớp thành đối tượng Class.

## 3. Type reference T(...) được phân giải như thế nào?

T(...) là toán tử tham chiếu kiểu của SpEL. Nó yêu cầu EvaluationContext phân giải tên kiểu thông qua TypeLocator. Với StandardEvaluationContext mặc định, Spring dùng StandardTypeLocator; các kiểu trong java.lang được đăng ký sẵn, còn kiểu ở package khác thường cần tên đầy đủ.

Ví dụ:

    T(String)
    T(java.time.LocalDate)
    T(com.example.events.OrderCreatedEvent)

Type reference không chỉ xuất hiện với instanceof. SpEL còn dùng nó để truy cập thành viên static:

    T(java.lang.Math).max(10, 20)

Biểu thức trên gọi phương thức static max của Math. Điều này cho thấy T(...) mở ra khả năng tham chiếu đến lớp và thành viên của lớp, nên context có quyền type lookup rộng phải được quản lý cẩn thận.

Không phải context nào cũng hỗ trợ T(...). SimpleEvaluationContext được thiết kế cho một tập con an toàn hơn của SpEL và mặc định không hỗ trợ type references, constructor references hoặc bean references. Khi biểu thức cần instanceof với T(...), ví dụ bên dưới dùng StandardEvaluationContext. Nếu ứng dụng chỉ cần đọc property thông thường và không cần type reference, SimpleEvaluationContext vẫn là lựa chọn giới hạn quyền phù hợp.

## 4. Ví dụ đánh giá instanceof bằng Java

Giả sử biến payload có thể chứa nhiều loại đối tượng. Ứng dụng tạo context, đăng ký biến rồi đánh giá biểu thức:

    Object payload = "payment received";

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("payload", payload);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#payload instanceof T(java.lang.String)");

    Boolean isText = expression.getValue(context, Boolean.class);

Ở đây:

1. payload là dữ liệu thực tế được đưa vào context dưới tên biến payload.
2. #payload lấy giá trị của biến đó trong biểu thức.
3. T(java.lang.String) tham chiếu đến lớp String.
4. instanceof so sánh kiểu runtime của đối tượng với kiểu đích.
5. getValue(..., Boolean.class) yêu cầu kết quả Boolean.

Với giá trị chuỗi ở ví dụ trên, kết quả là true. Nếu thay payload bằng một đối tượng Integer, kết quả sẽ là false. Biểu thức chỉ kiểm tra kiểu; nó không chuyển đổi đối tượng thành kiểu được yêu cầu.

## 5. Kiểm tra lớp cha và interface

instanceof kiểm tra khả năng gán kiểu (assignability), không chỉ kiểm tra tên lớp có trùng khớp hay không. Nếu một lớp kế thừa lớp khác hoặc triển khai interface, đối tượng của lớp con cũng thỏa điều kiện kiểm tra với lớp cha hoặc interface đó.

Ví dụ:

    #event instanceof T(com.example.events.DomainEvent)

Biểu thức trên trả về true với cả OrderCreatedEvent và PaymentFailedEvent vì hai lớp đều triển khai DomainEvent.

Kiểm tra một lớp cụ thể:

    #event instanceof T(com.example.events.OrderCreatedEvent)

Biểu thức chỉ đúng với OrderCreatedEvent và các lớp con của nó. Một PaymentFailedEvent độc lập sẽ không thỏa điều kiện.

Có thể kiểm tra interface để diễn đạt khả năng mà đối tượng hỗ trợ:

    #handler instanceof T(com.example.spi.Retryable)

Điều này thường bền vững hơn khi rule quan tâm đến hành vi hoặc hợp đồng chung. Nếu nhiều lớp khác nhau cùng triển khai Retryable, một biểu thức kiểm tra interface có thể áp dụng cho tất cả mà không cần liệt kê từng lớp cụ thể.

Bảng minh họa với cấu trúc lớp ở trên:

| Đối tượng runtime | instanceof DomainEvent | instanceof OrderCreatedEvent |
|---|---:|---:|
| OrderCreatedEvent | true | true |
| PaymentFailedEvent | true | false |
| Một lớp không triển khai DomainEvent | false | false |
| null | false | false |

## 6. Giá trị null và sự khác nhau giữa kiểm tra kiểu với kiểm tra null

Nếu vế trái là null, instanceof trả về false. Đây là hành vi phù hợp với phép kiểm tra kiểu của Java: null không phải thể hiện của bất kỳ lớp nào.

Ví dụ:

    #payload instanceof T(java.lang.String)

Nếu payload là null, kết quả là false. Tuy nhiên, điều đó không cho biết giá trị null hay chỉ đơn giản là một đối tượng thuộc kiểu khác.

Nếu nghiệp vụ cần phân biệt hai trường hợp, hãy kiểm tra null riêng:

    #payload == null

Hoặc kết hợp trong một biểu thức:

    #payload != null and
        #payload instanceof T(java.lang.String)

Toán tử and có cơ chế short-circuit: khi vế trái đã false, vế phải không cần được đánh giá. Dù vậy, với riêng instanceof, kiểm tra null trước thường chỉ cần thiết khi biểu thức tiếp theo sẽ truy cập thuộc tính hoặc gọi phương thức của đối tượng.

Không dùng instanceof như một phép kiểm tra dữ liệu đầy đủ. Một đối tượng đúng kiểu vẫn có thể chứa thuộc tính null, giá trị sai định dạng hoặc trạng thái nghiệp vụ không hợp lệ. Những điều kiện đó phải được kiểm tra riêng.

## 7. Kiểm tra kiểu chính xác và kiểm tra kiểu tương thích

Cần phân biệt hai ý định:

- **Kiểm tra tương thích kiểu:** đối tượng có thuộc kiểu đã chỉ định hoặc một kiểu con hay không. Dùng instanceof.
- **Kiểm tra đúng chính xác một lớp:** lớp runtime của đối tượng có đúng bằng lớp được chỉ định hay không.

Ví dụ với instanceof:

    #payload instanceof T(java.lang.Number)

Biểu thức trả về true cho Integer, Long, Double và các lớp con khác của Number.

Nếu nghiệp vụ thật sự yêu cầu chỉ chấp nhận đúng Integer, có thể so sánh lớp runtime:

    #payload != null and
        #payload.getClass() == T(java.lang.Integer)

Cách so sánh này chỉ đúng khi lớp runtime chính xác là Integer. Một giá trị Long hoặc Double dù cũng thuộc Number vẫn không thỏa điều kiện.

Không nên dùng kiểm tra lớp chính xác chỉ vì muốn viết điều kiện chặt hơn. Trong thiết kế hướng interface hoặc kế thừa, kiểm tra bằng instanceof thường phù hợp hơn vì nó chấp nhận các implementation và subclass tương thích. Chỉ chọn exact-class check khi quy tắc nghiệp vụ thực sự phụ thuộc vào danh tính lớp cụ thể.

## 8. Kiểm tra kiểu không phải là chuyển đổi kiểu

instanceof chỉ trả lời câu hỏi “đối tượng hiện tại có thuộc kiểu này không?”. Nó không chuyển đổi giá trị, không phân tích chuỗi và không tạo một đối tượng mới.

Ví dụ, một chuỗi chứa chữ số:

    Object value = "42";

không trở thành Integer chỉ vì kiểm tra:

    #value instanceof T(java.lang.Integer)

Kết quả vẫn là false, bởi đối tượng runtime vẫn là String.

Spring có cơ chế TypeConverter để chuyển đổi giá trị trong những tình huống mà tính năng SpEL hoặc Spring cần chuyển kiểu, chẳng hạn khi gán giá trị cho property hoặc khớp kiểu tham số phương thức. Cơ chế chuyển đổi này là một bước riêng; không được suy luận rằng instanceof sẽ tự gọi TypeConverter.

Nếu cần phân tích dữ liệu đầu vào, hãy chuyển đổi rõ ràng ở tầng Java hoặc dùng cơ chế chuyển đổi được kiểm soát, sau đó mới kiểm tra và đánh giá rule. Việc này giúp xử lý lỗi định dạng và giới hạn đầu vào ở đúng nơi.

## 9. Giới hạn với generic và collection

Java sử dụng type erasure cho generic. Ở runtime, đối tượng ArrayList<String> và ArrayList<Integer> đều có lớp runtime là ArrayList. Vì vậy, SpEL có thể kiểm tra một đối tượng có phải List hay không:

    #items instanceof T(java.util.List)

Nhưng không thể dùng instanceof để phân biệt trực tiếp List<String> với List<Integer>:

    #items instanceof T(java.util.List<java.lang.String>)

Đây không phải một type reference hợp lệ để kiểm tra tham số generic như kiểu compile-time. Thông tin tham số kiểu của generic không còn được lưu đầy đủ trong lớp runtime của collection.

Nếu cần xác nhận từng phần tử đều là chuỗi, hãy kiểm tra nội dung collection. Có thể dùng selection để lấy những phần tử không phải String:

    #items.?[!(#this instanceof T(java.lang.String))]

Kết quả là danh sách các phần tử không thỏa điều kiện kiểu. Nếu danh sách kết quả rỗng, mọi phần tử đã kiểm tra đều là String. Trong ứng dụng thực tế, kiểm tra collection ở Java thường dễ đọc và dễ báo lỗi chi tiết hơn khi cần xử lý dữ liệu lớn hoặc nhiều cấp lồng nhau.

## 10. Kết hợp instanceof với toán tử điều kiện

Khi cần chọn nhánh theo loại đối tượng, có thể kết hợp instanceof với toán tử ba ngôi:

    #event instanceof T(com.example.events.OrderCreatedEvent)
        ? 'ORDER_CREATED'
        : 'OTHER_EVENT'

Nếu cần lấy thuộc tính chỉ có trên một lớp cụ thể, có thể đặt truy cập thuộc tính ở nhánh true:

    #event instanceof T(com.example.events.PaymentFailedEvent)
        ? #event.reason
        : 'No payment failure'

Điều kiện giúp chỉ đánh giá nhánh phù hợp. Tuy nhiên, một biểu thức có nhiều nhánh và nhiều lớp cụ thể sẽ nhanh chóng trở nên khó bảo trì. Nếu mỗi loại sự kiện có quy trình riêng, hãy cân nhắc dùng polymorphism, handler registry hoặc dispatch trong Java thay vì dồn toàn bộ logic vào một chuỗi SpEL.

instanceof phù hợp để biểu đạt một điều kiện kiểu ngắn gọn. Nó không thay thế thiết kế đa hình của Java.

## 11. Kiểm soát quyền truy cập khi đánh giá biểu thức

StandardEvaluationContext hỗ trợ nhiều tính năng của SpEL, trong đó có type references, method invocation, property access và bean references khi được cấu hình. Những khả năng này hữu ích cho ứng dụng, nhưng cũng tạo ra ranh giới bảo mật.

Không nên lấy một chuỗi biểu thức tùy ý từ người dùng bên ngoài rồi đánh giá trực tiếp bằng StandardEvaluationContext có quyền rộng. Một biểu thức không chỉ kiểm tra instanceof; nó có thể dùng T(...) để tham chiếu lớp khác hoặc gọi phương thức static, tùy quyền mà context cho phép.

Một số nguyên tắc nên áp dụng:

- Chỉ đánh giá các rule do ứng dụng hoặc nguồn quản trị đáng tin cậy cung cấp.
- Chỉ đưa những biến và đối tượng đầu vào cần thiết vào context.
- Khi rule chỉ cần một số kiểu cụ thể, cấu hình TypeLocator theo allowlist thay vì cho phép phân giải mọi lớp trong classpath.
- Hạn chế method resolver, property accessor và bean resolver theo đúng nhu cầu.
- Kiểm tra cú pháp và kiểu kết quả của rule trước khi đưa vào luồng xử lý quan trọng.
- Ghi nhận mã rule và lỗi đánh giá để truy vết; tránh ghi toàn bộ dữ liệu nhạy cảm vào log.

Nếu không cần type reference hoặc các tính năng nâng cao, ưu tiên SimpleEvaluationContext với tập tính năng tối thiểu. Nếu bắt buộc dùng instanceof với T(...), hãy chọn StandardEvaluationContext và chủ động giới hạn các quyền truy cập phù hợp với nguồn biểu thức.

## 12. Kiểm thử biểu thức theo các trường hợp kiểu

Một rule kiểm tra kiểu nên được thử với các trường hợp đại diện, không chỉ một đối tượng đúng kiểu.

| Dữ liệu đầu vào | Kết quả mong đợi với kiểm tra String |
|---|---|
| Chuỗi thông thường | true |
| Một lớp khác như Integer | false |
| Một lớp con của kiểu đích (nếu kiểu đích cho phép kế thừa) | true |
| null | false |
| Collection chứa các phần tử không đồng nhất | Kiểm tra List là true; cần kiểm tra từng phần tử riêng |

Khi kiểm thử, hãy xác nhận cả ba phần: chuỗi biểu thức có parse được không, context có phân giải được kiểu hay không, và kết quả runtime có đúng với dữ liệu đầu vào không. Nếu lỗi xảy ra ở bước parse hoặc type lookup, đó là lỗi cấu hình/biểu thức. Nếu biểu thức chạy được nhưng trả về false, đó có thể chỉ là kết quả hợp lệ của dữ liệu hiện tại.

## Kết luận

Toán tử instanceof của SpEL kiểm tra kiểu runtime của một giá trị bằng cách so sánh nó với type reference được tạo qua T(...). Nó hỗ trợ kiểm tra lớp cụ thể, lớp cha và interface; trả về false với null; và không thực hiện chuyển đổi kiểu hay kiểm tra tham số generic đã bị type erasure.

Để dùng đúng, cần chọn context có hỗ trợ type reference, hiểu khác biệt giữa kiểm tra tương thích và kiểm tra lớp chính xác, đồng thời giới hạn quyền của biểu thức. Khi rule chỉ cần lựa chọn theo loại đối tượng, instanceof là công cụ gọn và rõ. Khi logic bắt đầu phân nhánh theo nhiều lớp hoặc thực hiện nhiều hành động, hãy chuyển phần điều phối sang Java và giữ SpEL ở vai trò biểu đạt điều kiện nhỏ.
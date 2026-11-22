# Ủy quyền công việc cho đối tượng khác trong Java OOP

Khi một đối tượng nhận một yêu cầu, nó có thể **giữ trách nhiệm với quy trình**, nhưng nhờ đối tượng khác thực hiện những bước chuyên môn. Đó là **delegation (ủy quyền)**. Java không có từ khóa riêng cho delegation: kỹ thuật này được thể hiện bằng **lời gọi phương thức tới collaborator**.

Ví dụ, một bộ điều phối yêu cầu hỗ trợ kỹ thuật nhận phiếu từ khách hàng. Nó không nhất thiết phải tự phân loại mức độ và tự lưu phiếu vào hàng chờ:

- `TicketRouter` kiểm tra đầu vào, quyết định **thứ tự xử lý** và trả kết quả cuối.
- `TicketClassifier` phân loại phiếu theo một bộ quy tắc.
- `AssignmentPort` ghi nhận phiếu vào hàng đợi đã chọn.
- Client chỉ cần gọi `router.route(ticket)` và nhận một `Assignment`.

Bài này đi sâu vào **ai giao việc cho ai, dữ liệu đi qua những ranh giới nào, ai chịu trách nhiệm về thành công/thất bại**, để tách delegation khỏi khái niệm ghép đối tượng nói chung.

## 1. Đọc đúng một luồng ủy quyền

~~~mermaid
sequenceDiagram
    actor Caller
    participant R as TicketRouter
    participant C as TicketClassifier
    participant P as AssignmentPort
    Caller->>R: route(ticket)
    R->>R: validate ticket
    R->>C: classify(ticket)
    C-->>R: Queue
    R->>P: assign(ticket.id, queue)
    P-->>R: Assignment
    R-->>Caller: Assignment
~~~

Trong sơ đồ, `TicketRouter` là **delegator** vì nó nhận trách nhiệm điều phối từ caller. `TicketClassifier` và `AssignmentPort` là **delegates** đối với các bước được giao. Một collaborator có thể tiếp tục ủy quyền cho đối tượng khác ở bên trong; “delegator/delegate” là **vai trò theo lời gọi**, không phải một loại class trong Java.

Ba ranh giới cần nhận diện:

| Bước | Ai chịu trách nhiệm? | Điều phải giữ rõ |
| --- | --- | --- |
| Nhận yêu cầu | `TicketRouter` | Input hợp lệ và trình tự xử lý |
| Xác định hàng đợi | `TicketClassifier` | Quy tắc phân loại và mã `Queue` |
| Ghi nhận phân công | `AssignmentPort` | Kết quả phân công, lỗi, ý nghĩa “đã nhận” |
| Trả kết quả cho client | `TicketRouter` | Không tự bịa kết quả nếu delegate thất bại |

**Ủy quyền không đồng nghĩa từ bỏ trách nhiệm.** Router vẫn chịu trách nhiệm gọi đúng bước, xử lý hoặc lan truyền lỗi phù hợp và không phát ra kết quả giả. Nó chỉ không ôm thuật toán phân loại hay cơ chế lưu hàng chờ.

## 2. Chương trình độc lập: thay delegate nhưng giữ router

Lưu thành `TicketDelegationDemo.java` (Java 17 trở lên). Đây là mô hình hàng chờ **trong bộ nhớ**; không sử dụng cơ sở dữ liệu hay dịch vụ từ xa.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class TicketDelegationDemo {
    enum Queue { STANDARD, URGENT, BILLING }

    record Ticket(String id, String summary, int severity) {
        Ticket {
            if (id == null || id.isBlank()
                    || summary == null || summary.isBlank()) {
                throw new IllegalArgumentException("Thiếu thông tin phiếu");
            }
            if (severity < 1 || severity > 5) {
                throw new IllegalArgumentException("Severity phải từ 1 đến 5");
            }
        }
    }

    record Assignment(String ticketId, Queue queue) {
        Assignment {
            if (ticketId == null || ticketId.isBlank()) {
                throw new IllegalArgumentException("Thiếu mã phiếu");
            }
            Objects.requireNonNull(queue, "queue");
        }
    }

    interface TicketClassifier {
        Queue classify(Ticket ticket);
    }

    interface AssignmentPort {
        // Chỉ mô tả hành vi "ghi nhận"; chưa cam kết lưu bền vững.
        Assignment assign(String ticketId, Queue queue);
    }

    static final class SeverityClassifier implements TicketClassifier {
        @Override
        public Queue classify(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");
            return ticket.severity() >= 4 ? Queue.URGENT : Queue.STANDARD;
        }
    }

    static final class BillingKeywordClassifier
            implements TicketClassifier {
        @Override
        public Queue classify(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");
            return ticket.summary()
                    .toLowerCase(Locale.ROOT)
                    .contains("thanh toán")
                    ? Queue.BILLING : Queue.STANDARD;
        }
    }

    static final class MemoryAssignmentPort implements AssignmentPort {
        private final List<Assignment> history = new ArrayList<>();

        @Override
        public Assignment assign(String ticketId, Queue queue) {
            Assignment result = new Assignment(ticketId, queue);
            history.add(result);
            return result;
        }

        List<Assignment> history() {
            return List.copyOf(history);
        }
    }

    static final class TicketRouter {
        private final TicketClassifier classifier;
        private final AssignmentPort assignments;

        TicketRouter(TicketClassifier classifier,
                     AssignmentPort assignments) {
            this.classifier =
                    Objects.requireNonNull(classifier, "classifier");
            this.assignments =
                    Objects.requireNonNull(assignments, "assignments");
        }

        Assignment route(Ticket ticket) {
            Objects.requireNonNull(ticket, "ticket");

            Queue queue = Objects.requireNonNull(
                    classifier.classify(ticket),
                    "Classifier không được trả null"
            );

            return Objects.requireNonNull(
                    assignments.assign(ticket.id(), queue),
                    "AssignmentPort không được trả null"
            );
        }
    }

    public static void main(String[] args) {
        MemoryAssignmentPort sharedPort = new MemoryAssignmentPort();

        TicketRouter bySeverity = new TicketRouter(
                new SeverityClassifier(), sharedPort
        );
        TicketRouter byTopic = new TicketRouter(
                new BillingKeywordClassifier(), sharedPort
        );

        Assignment first = bySeverity.route(
                new Ticket("T-17", "Không đăng nhập", 2)
        );
        Assignment second = byTopic.route(
                new Ticket("T-18", "Thanh toán lỗi", 5)
        );

        System.out.println(first);
        System.out.println(second);
        System.out.println("Số phân công: " + sharedPort.history().size());
    }
}
~~~

Chạy:

~~~bash
javac TicketDelegationDemo.java
java TicketDelegationDemo
~~~

Kết quả:

~~~text
Assignment[ticketId=T-17, queue=STANDARD]
Assignment[ticketId=T-18, queue=BILLING]
Số phân công: 2
~~~

**Diễn biến cụ thể:**

1. `bySeverity` nhận phiếu `T-17` mức 2. Nó **giao việc phân loại** cho `SeverityClassifier`; kết quả `STANDARD` được đưa vào `MemoryAssignmentPort`.
2. `byTopic` nhận phiếu `T-18` mức 5, nhưng dùng một bộ phân loại **theo chủ đề**. Chuỗi “Thanh toán lỗi” khớp từ khóa, nên trả `BILLING`. Đây không phải lỗi: hợp đồng cho phép các chiến lược phân loại có chính sách riêng.
3. Hai router cùng sử dụng **một instance** `sharedPort` do nơi tạo ứng dụng cung cấp. Vì thế lịch sử trong bộ nhớ có đúng hai bản ghi.
4. Không có đối tượng nào gửi email hoặc tạo ticket thật. `Assignment` chỉ xác nhận **adapter bộ nhớ trong ví dụ đã ghi nhận yêu cầu**, không đại diện một SLA xử lý hỗ trợ thực tế.

Lưu ý: `BillingKeywordClassifier` cố ý không xem `severity`. Nếu yêu cầu thực tế nói “mọi phiếu mức 5 bắt buộc vào URGENT”, đây sẽ là một **quy tắc chung cần công bố trong hợp đồng** và mọi implementation phải tuân thủ hoặc cần thêm tầng ưu tiên. Không được suy ra quy tắc ấy từ tên trường mà chưa có đặc tả.

## 3. Đối tượng được ghép và lời gọi được ủy quyền là hai câu hỏi khác nhau

~~~java
private final TicketClassifier classifier;
private final AssignmentPort assignments;
~~~

Hai field cho thấy router **giữ tham chiếu** tới hai collaborator. Đó là cấu trúc liên kết/ghép đối tượng (*has-a / uses-a*). Delegation thực sự chỉ diễn ra khi router gọi:

~~~java
Queue queue = classifier.classify(ticket);
Assignment result = assignments.assign(ticket.id(), queue);
~~~

| Khái niệm | Câu hỏi chính | Quan sát trong ví dụ |
| --- | --- | --- |
| Composition / association | Router sử dụng những object nào? | Hai field nhận từ constructor |
| Delegation | Phần nào chuyển cho object khác? | Phân loại và phân công |
| Polymorphism | Cùng lời gọi chạy cách thực hiện nào? | Classifier theo mức hay từ khóa |
| Dependency injection | Ai cung cấp collaborator? | `main` tạo và truyền qua constructor |
| Encapsulation | Ai được sửa lịch sử phân công? | `MemoryAssignmentPort` giữ danh sách private |

Một trường tham chiếu có thể chỉ phục vụ tra cứu hoặc quan sát mà không ủy quyền công việc thuộc API công khai; không nên gọi mọi field là một “pattern delegation”. Ngược lại, phương thức cũng có thể **nhận delegate như một tham số tại lúc gọi**, không cần lưu thành field.

~~~java
static Queue classifyOnce(
        Ticket ticket, TicketClassifier temporaryClassifier) {
    Objects.requireNonNull(temporaryClassifier, "temporaryClassifier");
    return temporaryClassifier.classify(
            Objects.requireNonNull(ticket, "ticket"));
}
~~~

Đoạn này là method bổ sung minh họa: đặt trong `TicketDelegationDemo` sẽ dùng được các kiểu của ví dụ. Nó cho thấy ủy quyền **không bắt buộc constructor injection**, dù constructor injection phù hợp khi router cần hai collaborator trong suốt vòng đời.

## 4. Hợp đồng delegate là điều router dựa vào

Java chỉ kiểm tra chữ ký `classify(Ticket)` và `assign(String, Queue)`; không tự xác nhận hành vi của từng implementation.

| Hợp đồng cần ghi rõ | Ý nghĩa với router |
| --- | --- |
| `TicketClassifier` trả `Queue` không null với ticket hợp lệ | Có thể chuyển kết quả sang adapter |
| Phương thức phân loại không tự ghi/chỉnh ticket | Dễ test, không tạo side effect ngầm |
| `AssignmentPort` trả `Assignment` có ticketId/queue đúng hoặc báo lỗi | Caller biết phiếu được xử lý bởi adapter nào |
| Lỗi không được đổi thành “đã phân công” giả | Giữ đúng kết quả nghiệp vụ |
| Độ bền/timeout/thread safety | Phải xác định theo implementation và nhu cầu thực |

Ví dụ `TicketClassifier` bị lỗi:

~~~java
static final class BrokenClassifier implements TicketClassifier {
    @Override
    public Queue classify(Ticket ticket) {
        return null;
    }
}
~~~

Lớp này **biên dịch** nhưng vi phạm cam kết non-null. `TicketRouter` từ chối kết quả ấy với `NullPointerException` có thông điệp rõ. Tuy nhiên, kiểm tra ở router không thay thế được contract tests cho mọi classifier.

**Điều kiện lỗi theo thứ tự:** nếu constructor `Ticket` từ chối input thì chưa có lời gọi tới router. Nếu classifier ném lỗi, adapter chưa được gọi. Nếu adapter lỗi **sau khi ghi một phần**, router không tự rollback bộ nhớ, file hay giao dịch bên ngoài. Hợp đồng cần nói rõ failure semantics của adapter thật.

## 5. Delegation và forwarding: khi nào một tầng trung gian có giá trị?

Xét kiểu chuyển tiếp thuần túy:

~~~java
class BareRouter {
    private final AssignmentPort port;

    BareRouter(AssignmentPort port) {
        this.port = port;
    }

    Assignment assign(String id, Queue queue) {
        return port.assign(id, queue);
    }
}
~~~

Nếu `BareRouter` không thêm hợp đồng, validation, kiểm soát quyền hoặc cách ly phụ thuộc, lớp này có thể chỉ làm luồng code dài thêm. Không phải cứ gọi phương thức đối tượng khác là phải tạo một lớp mới.

`TicketRouter` chính trong bài có lý do tồn tại: nó **điều phối hai khả năng chuyên biệt**, buộc thứ tự “phân loại trước → ghi nhận sau” và công bố một API `route(Ticket)` mà caller không phải tự gọi từng thành phần.

Một tầng ủy quyền thường hữu ích khi nó:

- Định nghĩa **trách nhiệm nghiệp vụ** rõ ràng với caller.
- Gom validation hoặc orchestration ở đúng ranh giới.
- Giấu chi tiết hạ tầng mà caller không cần hiểu.
- Cho phép **thay implementation** mà không sửa logic điều phối.
- Giúp kiểm thử riêng một ranh giới thay vì khởi động cả hệ thống.

Ngược lại, nhiều lớp mỗi lớp chỉ gọi tiếp một method y hệt có thể trở thành **pass-through layers** không cần thiết. Hãy kiểm tra giá trị của từng tầng trước khi thêm.

## 6. Đổi delegate không nhất thiết phải dùng inheritance

Nếu router tự kế thừa bộ phân loại chỉ để dùng thuật toán của nó:

~~~java
// Thiết kế sai ý nghĩa trách nhiệm:
// class TicketRouter extends SeverityClassifier { ... }
~~~

ta đang nói “router là một loại bộ phân loại”. Nhưng router **sử dụng một bộ phân loại**, còn trách nhiệm của router là điều phối. Quan hệ này hợp với **has-a / uses-a**.

Trong ví dụ thực, `SeverityClassifier` được đánh dấu `final` nên không thể kế thừa ngay cả ở mức cú pháp. Dòng trên cố ý được comment để chỉ ra mô hình sai, không phải mã hợp lệ của demo.

~~~mermaid
classDiagram
    class TicketRouter {
        -TicketClassifier classifier
        -AssignmentPort assignments
        +route(Ticket) Assignment
    }
    class TicketClassifier {
        <<interface>>
        +classify(Ticket) Queue
    }
    class AssignmentPort {
        <<interface>>
        +assign(String, Queue) Assignment
    }
    class SeverityClassifier
    class BillingKeywordClassifier
    class MemoryAssignmentPort
    TicketRouter --> TicketClassifier : classify
    TicketRouter --> AssignmentPort : assign
    TicketClassifier <|.. SeverityClassifier
    TicketClassifier <|.. BillingKeywordClassifier
    AssignmentPort <|.. MemoryAssignmentPort
~~~

**Kế thừa vẫn phù hợp** khi lớp con thật sự là một subtype của lớp cha và giữ đúng hợp đồng. Delegation chỉ là một kỹ thuật thay thế khi ta cần dùng **khả năng** mà không có quan hệ is-a thật. Bài so sánh tái sử dụng giữa kế thừa và kết hợp có thể phân tích sâu thêm trường hợp nhiều chiều biến thiên độc lập.

## 7. Phân biệt delegation với những pattern liên quan

Delegation là cơ chế nền của nhiều mẫu thiết kế, nhưng mục đích của từng mẫu khác nhau:

| Kỹ thuật/mẫu | Mục đích chính | Cách áp dụng trong miền ticket |
| --- | --- | --- |
| **Strategy** | Chọn thuật toán có thể thay thế | `SeverityClassifier` hoặc `BillingKeywordClassifier` |
| **Adapter** | Chuyển hợp đồng ứng dụng sang API công nghệ khác | `AssignmentPort` → một SDK quản lý công việc |
| **Decorator** | Bọc object cùng interface để thêm hành vi | Ghi log trước/sau `assign` |
| **Proxy** | Kiểm soát truy cập, lazy loading, remote invocation | Chặn phân công nếu caller thiếu quyền |
| **Facade** | Cho client một API gọn cho nhiều thành phần | `TicketRouter.route` điều phối các bước |

Ví dụ decorator, đặt thành lớp lồng trong `TicketDelegationDemo`:

~~~java
static final class LoggingAssignmentPort implements AssignmentPort {
    private final AssignmentPort delegate;

    LoggingAssignmentPort(AssignmentPort delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public Assignment assign(String ticketId, Queue queue) {
        System.out.println("Gọi phân công: " + ticketId);
        Assignment result = delegate.assign(ticketId, queue);
        System.out.println("Adapter đã trả kết quả");
        return result;
    }
}
~~~

Decorator này **không hứa** rằng dữ liệu đã tồn tại bền vững chỉ vì delegate trả về. Nó cũng không tự quản lý transaction. Tránh tự động dùng tên pattern khi chỉ cần một field và một lời gọi đơn giản.

## 8. Kiểm thử đúng sự cộng tác và đường lỗi

Có thể thêm một fake ghi nhận lời gọi làm lớp lồng trong demo:

~~~java
static final class RecordingAssignments implements AssignmentPort {
    int calls;
    String lastTicketId;
    Queue lastQueue;

    @Override
    public Assignment assign(String id, Queue queue) {
        calls++;
        lastTicketId = id;
        lastQueue = queue;
        return new Assignment(id, queue);
    }
}
~~~

Rồi thêm đoạn sau vào `main` của demo:

~~~java
RecordingAssignments recorder = new RecordingAssignments();
TicketRouter router = new TicketRouter(new SeverityClassifier(), recorder);
Assignment result = router.route(new Ticket("T-99", "Lỗi đăng nhập", 5));

if (recorder.calls != 1 || recorder.lastQueue != Queue.URGENT
        || !"T-99".equals(recorder.lastTicketId)
        || result.queue() != Queue.URGENT) {
    throw new AssertionError("Ủy quyền không đúng");
}
~~~

Test này xác nhận router chuyển đúng mã và hàng đợi, gọi adapter **một lần**, trả lại kết quả từ adapter. Bên cạnh test delegator, cần:

- **Test classifier:** kiểm tra từng chiến lược với mức độ/từ khóa đầu vào xác định.
- **Contract test:** xác minh mọi implementation trả non-null và đúng kết quả được phép, không tự sửa ticket.
- **Integration test:** adapter HTTP/database thật có ghi đúng, báo lỗi chính xác, đóng tài nguyên đúng không.
- **Failure test:** classifier lỗi thì adapter không được gọi; adapter lỗi thì router không được trả thành công giả.

Không cần mock framework cho những thử nghiệm ngắn này. Fake hỗ trợ cô lập ranh giới, nhưng không chứng minh hệ thống bên ngoài thực sự vận hành đúng.

## 9. Vòng đời, đồng thời và kết quả giao việc

Cả hai router trong `main` đều giữ `sharedPort`. Việc cùng giữ tham chiếu không trao **quyền sở hữu độc quyền** cho router nào. Nếu port có socket/database client, bên tạo nó thường cần quản lý vòng đời, hoặc phải có hợp đồng chuyển giao quyền sở hữu rõ.

`MemoryAssignmentPort` sử dụng `ArrayList` và **không thread-safe**. Hai request song song gọi `assign` trên cùng port có thể gây race condition. Field `final` trong router chỉ cố định tham chiếu, không làm danh sách mutable của port trở nên an toàn.

Đối với adapter thực, cũng cần tách:

1. **Đã chấp nhận yêu cầu** hay **đã ghi bền vững**?
2. Đã gọi xong API hay **đã phân công thực tế** cho người phụ trách?
3. Khi thất bại và retry, có nguy cơ **phân công trùng** không?
4. Khi classifier và port đọc dữ liệu khác thời điểm, có cần **phiên bản quy tắc** hay transaction?
5. Khi thay delegate, request cũ còn sử dụng port/classifier cũ hay đã được chuyển sang mới?

Nếu hệ thống yêu cầu idempotency, auditing hoặc transaction, chúng phải được thiết kế và kiểm thử riêng. Delegation **chỉ tổ chức trách nhiệm và đường gọi**; nó không tự tạo những bảo đảm vận hành này.

## 10. Bài tập tự kiểm tra

**1. Ai là delegator?** Trong `TicketRouter.route`, thành phần nào thực hiện phân loại, thành phần nào ghi nhận?

**Đáp án:** Router là delegator. `TicketClassifier` phân loại; `AssignmentPort` ghi nhận. Router vẫn kiểm soát thứ tự và trả kết quả.

**2. Hai router dùng chung một `MemoryAssignmentPort` có hai lịch sử hay một?**

**Đáp án:** Một lịch sử trong cùng instance. Cấp hai port khác nhau nếu cần tách trạng thái, hoặc định nghĩa cơ chế chia sẻ an toàn nếu muốn dùng chung đồng thời.

**3. Nếu classifier trả `null`, router có được tiếp tục gọi `assign` không?**

**Đáp án:** Không theo chương trình minh họa. `Objects.requireNonNull` dừng trước bước gửi, nên không có phân công mới.

**4. Nếu thay `SeverityClassifier` bằng `BillingKeywordClassifier`, vì sao không cần sửa `TicketRouter`?**

**Đáp án:** Router chỉ phụ thuộc vào `TicketClassifier.classify`. Đây là đa hình theo hợp đồng, được cấp qua constructor.

**5. Có thể ủy quyền mà không có field tham chiếu không?**

**Đáp án:** Có. Nhận một classifier bằng tham số của phương thức rồi gọi nó cũng là delegation nếu đang chuyển phần việc chuyên môn.

**6. Nếu `AssignmentPort.assign` lưu dữ liệu một phần rồi ném lỗi, router có tự rollback không?**

**Đáp án:** Không. Lỗi và side effect phải được thiết kế ở adapter hoặc ranh giới transaction; tránh trả kết quả thành công giả.

**7. Delegation luôn làm thiết kế tốt hơn?**

**Đáp án:** Không. Một tầng wrapper không thêm ranh giới, kiểm tra hay trách nhiệm có thể chỉ làm code khó đọc. Tạo delegate khi có sự phân công vai trò thật.

**Ghi nhớ:** Ủy quyền là quyết định **chuyển đúng một phần công việc tới đối tượng biết làm công việc đó**. Đối tượng điều phối giữ trách nhiệm đối với luồng và kết quả, collaborator thực hiện bước chuyên môn. Thiết kế tốt cần hợp đồng rõ, kết quả có nghĩa, đường lỗi và vòng đời được kiểm soát; không chỉ đơn giản gọi thêm một method trên field.
# Phân biệt lỗi tạm thời có thể thử lại với lỗi nghiệp vụ

Trong ứng dụng Spring Data Neo4j (SDN), hai request có thể đồng thời cập nhật cùng node hoặc relationship. Một transaction có thể thất bại vì tranh chấp khóa, deadlock hoặc sự cố kết nối tạm thời. Một transaction khác có thể thất bại vì dữ liệu không hợp lệ, vi phạm constraint hoặc quy tắc nghiệp vụ không cho phép thao tác. Hai nhóm lỗi này cần cách xử lý khác nhau.

Retry chỉ phù hợp khi nguyên nhân có khả năng tự biến mất sau một khoảng chờ và thao tác có thể được thực hiện lại an toàn. Lỗi nghiệp vụ cần được trả về hoặc xử lý theo quy tắc domain; lặp lại cùng một request thường chỉ tạo thêm tải và không làm kết quả hợp lệ hơn.

Bài học này trình bày cách phân loại lỗi, giới hạn số lần thử, đặt retry bên ngoài ranh giới transaction, bảo vệ thao tác ghi bằng idempotency và phân biệt transient failure với optimistic locking conflict trong ứng dụng Spring Data Neo4j.

## 1. Hai nhóm lỗi có ý nghĩa khác nhau

Hãy bắt đầu bằng câu hỏi: nếu thực hiện lại cùng thao tác sau một khoảng chờ ngắn, liệu điều kiện khiến nó thất bại có thể tự biến mất không?

| Nhóm lỗi | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Lỗi hạ tầng tạm thời | Neo4j tạm thời không khả dụng, mất kết nối ngắn hạn, leader/routing thay đổi | Retry có giới hạn nếu thao tác an toàn |
| Tranh chấp tài nguyên tạm thời | Deadlock hoặc lock contention trong transaction đồng thời | Rollback transaction hiện tại rồi retry toàn bộ nghiệp vụ |
| Xung đột optimistic locking | Entity đang lưu có version cũ hơn version trong graph | Tải lại, hợp nhất hoặc từ chối theo nghiệp vụ; không retry mù |
| Lỗi dữ liệu | Vi phạm uniqueness constraint, dữ liệu sai kiểu hoặc thiếu property bắt buộc | Trả lỗi dữ liệu hoặc xử lý xung đột |
| Lỗi nghiệp vụ | Không đủ hàng, tài khoản bị khóa, khóa học đã đóng | Trả kết quả nghiệp vụ; không retry cùng điều kiện |
| Lỗi lập trình hoặc truy vấn | Cypher sai cú pháp, tham số thiếu, lỗi chuyển đổi | Sửa code hoặc dữ liệu đầu vào; không retry |

Một deadlock có thể biến mất khi transaction khác kết thúc. Ngược lại, nếu số lượng hàng tồn kho bằng không, gửi lại cùng lệnh đặt hàng ngay lập tức không làm hàng hóa xuất hiện. Phân loại đúng giúp hệ thống không retry những lỗi cần được giải quyết ở tầng nghiệp vụ.

## 2. Nhận diện transient failure trong Neo4j và Spring

Neo4j phân loại lỗi bằng error code. Nhóm mã có tiền tố Neo.TransientError biểu thị lỗi tạm thời theo phân loại của server. Ví dụ, deadlock trong transaction là một tình huống có thể được báo bằng mã thuộc nhóm transient transaction error.

Khi dùng Neo4j Java Driver trực tiếp, các lỗi server được biểu diễn bằng các exception của Driver, trong đó có nhóm TransientException. Khi đi qua SDN, Spring có thể dịch exception của Driver sang hệ DataAccessException. Những exception thuộc TransientDataAccessException biểu thị nhóm lỗi mà tầng persistence xem là tạm thời.

Không nên xem mọi DataAccessException là retryable. Đây là lớp cha rộng, bao gồm cả lỗi dữ liệu và lỗi không thể giải quyết bằng cách thử lại. Cần phân loại theo subtype hoặc error code thực tế và kiểm tra cause chain khi Spring đã bọc exception của Driver.

Ví dụ phân loại ở mức khái niệm:

~~~java
import org.neo4j.driver.exceptions.Neo4jException;
import org.neo4j.driver.exceptions.TransientException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessException;

public boolean isTransientFailure(Throwable failure) {
    boolean transientFound = false;

    for (Throwable cause = failure;
         cause != null;
         cause = cause.getCause()) {

        if (cause instanceof OptimisticLockingFailureException) {
            return false;
        }

        if (cause instanceof TransientDataAccessException
                || cause instanceof TransientException) {
            transientFound = true;
        }

        if (cause instanceof Neo4jException neo4jException) {
            String code = neo4jException.code();
            if (code != null && code.startsWith("Neo.TransientError.")) {
                transientFound = true;
            }
        }
    }

    return transientFound;
}
~~~

Đây là ví dụ classifier để minh họa việc kiểm tra subtype và error code. Trong ứng dụng thực tế, cần đối chiếu các exception được phiên bản SDN/Driver đang dùng dịch ra, tránh retry chỉ dựa vào thông điệp lỗi dạng text vì thông điệp có thể thay đổi theo phiên bản hoặc ngôn ngữ.

Một số lỗi kết nối có thể xảy ra trước khi server xác nhận transaction đã commit hay chưa. Khi client mất kết nối ở thời điểm nhận phản hồi commit, trạng thái kết quả có thể chưa rõ ràng. Trong tình huống này, idempotency là điều kiện quan trọng trước khi gửi lại lệnh ghi.

## 3. Phân biệt lỗi nghiệp vụ và lỗi dữ liệu

Lỗi nghiệp vụ biểu thị thao tác không hợp lệ theo trạng thái domain. Ví dụ:

~~~java
public class InsufficientStockException extends RuntimeException {
    public InsufficientStockException(String message) {
        super(message);
    }
}

public void validateOrder(OrderCommand command, Inventory inventory) {
    if (inventory.availableQuantity() < command.quantity()) {
        throw new InsufficientStockException("Không đủ hàng trong kho");
    }
}
~~~

Nếu số lượng tồn kho không đủ, retry cùng command với cùng quantity không giải quyết được nguyên nhân. API nên trả lỗi nghiệp vụ phù hợp, chẳng hạn conflict hoặc unprocessable request tùy hợp đồng của ứng dụng.

Lỗi dữ liệu thường gồm vi phạm uniqueness constraint, property không đáp ứng ràng buộc hoặc giá trị đầu vào không thể chuyển đổi. Ví dụ một node Person đã tồn tại với cùng email duy nhất. Retry cùng email sẽ tiếp tục vi phạm constraint.

| Lỗi | Có nên retry tự động? | Lý do |
| --- | --- | --- |
| Deadlock transient | Có thể, có giới hạn | Transaction cạnh tranh có thể đã kết thúc |
| Server tạm thời unavailable | Có thể, có giới hạn và idempotency | Hạ tầng có thể phục hồi; kết quả commit có thể chưa rõ |
| Thiếu hàng | Không | Điều kiện nghiệp vụ chưa thay đổi |
| Email đã được sử dụng | Không | Constraint vẫn còn hiệu lực |
| Cypher syntax error | Không | Lỗi truy vấn không tự biến mất |
| Thiếu tham số bắt buộc | Không | Cần sửa request hoặc code |
| Optimistic locking failure | Không retry mù | Entity đầu vào đã cũ; phải tải lại và đánh giá lại thay đổi |

Không retry validation exception, authorization failure hoặc lỗi nghiệp vụ chỉ vì chúng kế thừa RuntimeException. Mặc định rollback và retry là hai quyết định riêng: một lỗi có thể cần rollback transaction nhưng không được thử lại.

## 4. Optimistic locking là xung đột cần giải quyết

SDN hỗ trợ optimistic locking bằng property Version. Khi hai request cùng đọc một entity ở version 4, request đầu có thể lưu thành công và tăng version lên 5. Request thứ hai vẫn mang version 4 nên thao tác lưu bị từ chối.

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Account")
public class Account {

    @Id
    private String id;

    private String displayName;

    @Version
    private Long version;

    public void rename(String newName) {
        this.displayName = newName;
    }
}
~~~

Lỗi optimistic locking không giống một deadlock. Nó cho biết entity mà request đang giữ đã cũ so với graph hiện tại. Nếu tự động retry cùng object cũ, lần thử tiếp theo vẫn dùng version cũ và tiếp tục thất bại.

Cách xử lý đúng phụ thuộc nghiệp vụ:

1. Tải lại entity mới nhất.
2. Kiểm tra thay đổi của request có còn hợp lệ trên trạng thái mới không.
3. Hợp nhất thay đổi nếu không xung đột về ý nghĩa.
4. Nếu hai thay đổi mâu thuẫn, trả conflict để caller quyết định.
5. Chỉ thực hiện lại lệnh lưu sau khi đã tạo trạng thái domain mới hợp lệ.

Vì OptimisticLockingFailureException là một dạng concurrency failure trong hệ exception Spring, nó có thể nằm dưới nhóm TransientDataAccessException. Nếu retry policy dùng nhóm cha này, hãy loại optimistic locking ra khỏi retry tự động hoặc xử lý nó bằng một policy riêng có bước reload/merge.

## 5. Retry toàn bộ transaction, không tiếp tục transaction đã lỗi

Khi deadlock hoặc lỗi transient làm transaction thất bại, transaction đó có thể đã bị rollback hoặc không còn dùng được. Không nên bắt lỗi rồi chạy lại riêng câu lệnh cuối trong cùng transaction.

Luồng retry an toàn thường là:

~~~mermaid
flowchart TD
    A["Nhận command"] --> B["Bắt đầu một transaction mới"]
    B --> C["Đọc và kiểm tra trạng thái graph"]
    C --> D["Thực hiện các thay đổi node/relationship"]
    D --> E{"Transaction thành công?"}
    E -->|Có| F["Commit và trả kết quả"]
    E -->|Không| G{"Lỗi transient và còn lượt?"}
    G -->|Có| H["Chờ backoff"]
    H --> B
    G -->|Không| I["Trả lỗi hoặc phục hồi"]
~~~

Mỗi lần thử phải chạy lại từ đầu trong transaction mới. Như vậy, dữ liệu được đọc lại theo trạng thái graph hiện tại và các thao tác persistence không tiếp tục sử dụng transaction đã bị đánh dấu rollback-only.

## 6. Đặt retry bên ngoài ranh giới Transactional

Với Spring Retry, một cách rõ ràng là tách facade retry và service transaction thành hai bean. Facade không mở transaction; mỗi lần gọi service transaction sẽ đi qua proxy và tạo một transaction riêng.

Cấu hình bật Spring Retry:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.annotation.EnableRetry;

@Configuration
@EnableRetry
public class RetryConfiguration {
}
~~~

Facade chịu trách nhiệm retry:

~~~java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class OrderRetryFacade {

    private final OrderTransactionService transactionService;

    public OrderRetryFacade(OrderTransactionService transactionService) {
        this.transactionService = transactionService;
    }

    @Retryable(
        retryFor = TransientDataAccessException.class,
        noRetryFor = OptimisticLockingFailureException.class,
        maxAttempts = 3,
        backoff = @Backoff(
            delay = 200,
            multiplier = 2.0,
            maxDelay = 2000,
            random = true
        )
    )
    public OrderResult place(PlaceOrderCommand command) {
        return transactionService.place(command);
    }

    @Recover
    public OrderResult recover(
            TransientDataAccessException exception,
            PlaceOrderCommand command) {
        throw new OrderTemporarilyUnavailableException(
            "Neo4j tạm thời không xử lý được yêu cầu",
            exception
        );
    }
}
~~~

Service transaction thực hiện một lần thử:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderTransactionService {

    private final OrderRepository orderRepository;

    public OrderTransactionService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderResult place(PlaceOrderCommand command) {
        // Đọc trạng thái hiện tại, kiểm tra quy tắc nghiệp vụ,
        // tạo/cập nhật node và relationship.
        Order order = orderRepository.createFor(command);
        return OrderResult.from(order);
    }
}
~~~

Ở ví dụ này, maxAttempts = 3 nghĩa là tối đa ba lần thực hiện, bao gồm lần đầu tiên. Backoff tăng thời gian chờ giữa các lần thử và random = true thêm yếu tố ngẫu nhiên để nhiều instance không đồng loạt retry cùng một thời điểm.

noRetryFor giúp loại optimistic locking failure khỏi nhóm transient chung. Nếu dự án dùng phiên bản Spring Retry cũ chưa có thuộc tính này, cần cấu hình classifier tương đương bằng API retry policy phù hợp với phiên bản đang dùng.

Tách bean giúp mỗi lần gọi transactionService.place(...) đi qua transaction proxy. Tránh đặt Retryable và Transactional trên cùng một method rồi dựa vào thứ tự interceptor mặc định; nếu transaction bao ngoài toàn bộ retry, các lần thử có thể vẫn dùng chung một transaction.

Facade retry cũng cần được gọi từ ngoài một transaction đang mở. Nếu caller đã mở transaction với propagation REQUIRED, transaction của OrderTransactionService có thể tham gia transaction bên ngoài và các lần thử không còn độc lập. Hãy đặt retry facade ở ranh giới use case không có transaction bao ngoài, hoặc thiết kế propagation riêng sau khi đánh giá rõ tác động commit/rollback.

Spring Retry là thư viện cần được thêm vào dự án nếu ứng dụng chưa sử dụng. Nó không phải thành phần tự động được bật chỉ vì đã thêm Spring Data Neo4j.

## 7. Bảo đảm idempotency trước khi retry thao tác ghi

Retry có thể gọi cùng một nghiệp vụ nhiều lần. Nếu mỗi lần đều tạo node hoặc relationship mới, hệ thống có thể sinh dữ liệu trùng.

Ví dụ, một request tạo đơn hàng nên có request ID ổn định do caller hoặc service tạo trước lần thử đầu tiên. Neo4j có thể bảo vệ request ID bằng uniqueness constraint:

~~~cypher
CREATE CONSTRAINT order_request_id_unique IF NOT EXISTS
FOR (order:Order)
REQUIRE order.requestId IS UNIQUE
~~~

Lệnh ghi dùng cùng request ID trong mọi lần thử:

~~~cypher
MERGE (order:Order {requestId: $requestId})
ON CREATE SET
    order.customerId = $customerId,
    order.status = "CREATED",
    order.createdAt = datetime()
RETURN order
~~~

Cần kiểm tra rằng request ID được gắn với cùng payload nghiệp vụ. Nếu một request ID đã tồn tại nhưng payload mới khác payload ban đầu, service phải phát hiện xung đột thay vì âm thầm coi đó là cùng một yêu cầu.

Với relationship, xác định rõ một quan hệ là duy nhất theo cặp node hay mỗi lần phát sinh là một sự kiện riêng. Nếu nghiệp vụ chỉ cho phép một membership cho mỗi cặp team/person, có thể dùng pattern MERGE và constraint phù hợp cho các node định danh. Nếu mỗi lần tham gia cần lịch sử riêng, hãy dùng một node hoặc relationship event có khóa nghiệp vụ riêng thay vì gộp tất cả vào cùng một edge.

Idempotency không chỉ là dùng MERGE. Nó là hợp đồng đảm bảo thực hiện lại cùng một command không tạo thêm hiệu ứng ngoài ý muốn.

## 8. Không lặp lại side effect bên ngoài transaction

Một retry có thể chạy lại toàn bộ method. Nếu method gửi email, gọi thanh toán hoặc publish message ngay bên trong, các side effect đó cũng có thể bị lặp dù transaction Neo4j đã rollback.

~~~java
@Retryable(retryFor = TransientDataAccessException.class, maxAttempts = 3)
public void createOrderAndNotify(PlaceOrderCommand command) {
    transactionService.createOrder(command);
    emailGateway.sendConfirmation(command.customerEmail());
}
~~~

Ví dụ trên không an toàn nếu retry facade lặp lại cả method sau khi email đã gửi nhưng một thao tác khác báo lỗi. Hãy để transaction service chỉ thực hiện công việc trong Neo4j và ghi một outbox event trong cùng transaction. Một worker riêng đọc outbox sau commit, gửi thông báo với idempotency key và đánh dấu event đã xử lý.

Nếu phải gọi hệ thống ngoài trong cùng quy trình, cần thiết kế idempotency hoặc cơ chế bù trừ cho hệ thống đó. Rollback Neo4j không thể thu hồi một email hoặc thanh toán đã được chấp nhận.

## 9. Neo4j Driver managed retry và Spring transaction

Neo4j Java Driver có managed transaction functions như executeRead và executeWrite. Driver có thể tự retry transaction function khi nhận lỗi transient phù hợp trong phạm vi retry time đã cấu hình. Callback có thể được thực thi nhiều lần, vì vậy callback phải an toàn khi chạy lặp.

Đây là cơ chế của Driver khi ứng dụng trực tiếp dùng managed transaction function. SDN imperative thông thường tích hợp transaction thông qua Spring Neo4jTransactionManager và Transactional; không nên mặc định rằng mọi method repository có annotation sẽ tự động nhận cơ chế retry của executeWrite.

Không lồng managed transaction function của Driver vào transaction Spring đang quản lý cho cùng một nghiệp vụ. Hãy chọn một ranh giới transaction rõ ràng:

| Cách tiếp cận | Ai quản lý transaction? | Retry |
| --- | --- | --- |
| SDN repository/Neo4jTemplate với Transactional | Spring Neo4jTransactionManager | Cấu hình retry ở tầng service bên ngoài transaction |
| Neo4jClient trong Spring transaction | Spring transaction manager dùng chung Driver | Theo retry policy ở tầng ứng dụng |
| Driver executeWrite/executeRead trực tiếp | Neo4j Driver managed transaction | Driver tự retry lỗi transient theo cấu hình |
| Reactive SDN | Reactive transaction infrastructure | Dùng cơ chế retry reactive phù hợp; không áp dụng ví dụ imperative này nguyên xi |

Khi dùng Driver managed transaction, không gửi email hoặc thực hiện side effect ngoài database bên trong callback vì callback có thể được gọi lại.

## 10. Thiết kế retry có giới hạn

Retry không nên kéo dài vô hạn. Một policy thực tế cần xác định:

- **Nhóm exception:** chỉ retry các transient error đã được nhận diện.
- **Số lần thử:** đặt số lần tối đa phù hợp với độ trễ API.
- **Backoff:** tăng thời gian chờ giữa các lần thử.
- **Jitter:** thêm ngẫu nhiên để giảm hiện tượng nhiều instance cùng retry.
- **Thời hạn tổng:** không vượt quá timeout của request hoặc nghiệp vụ.
- **Idempotency:** bảo vệ thao tác ghi trước khi cho phép chạy lại.
- **Fallback:** khi hết lượt, trả lỗi tạm thời và ghi nhận nguyên nhân.

Ví dụ với ba lần thử, thời gian chờ có thể tăng khoảng 200 ms, 400 ms rồi tối đa 2 giây tùy backoff và jitter. Đây chỉ là cấu hình minh họa; cần đo độ trễ thực tế và giới hạn thời gian mà caller chấp nhận.

Không đặt retry nhiều tầng mà không tính tổng số lần thử. Ví dụ service retry ba lần, HTTP client retry ba lần và gateway retry ba lần có thể khiến một command được thực thi đến 27 lần. Hãy xác định một tầng sở hữu retry chính hoặc tính tổng retry budget xuyên suốt hệ thống.

## 11. Ghi log và quan sát retry

Mỗi lần retry nên có thông tin đủ để phân tích mà không làm lộ dữ liệu nhạy cảm:

| Trường log/metric | Mục đích |
| --- | --- |
| Tên use case | Biết nghiệp vụ nào đang retry |
| Attempt number | Biết đang ở lần thử thứ mấy |
| Exception class và Neo4j error code | Phân loại nguyên nhân |
| Thời gian chờ | Kiểm tra backoff có hoạt động |
| Tổng thời gian transaction | Đo ảnh hưởng tới latency |
| Kết quả cuối | Thành công, hết lượt hoặc lỗi không retry |

Theo dõi tỷ lệ retry, tỷ lệ retry thành công, số lần hết retry budget và thời gian chờ trung bình. Nếu retry tăng đột biến, đó có thể là dấu hiệu deadlock, lock contention, database quá tải hoặc lỗi mạng. Không nên chỉ tăng maxAttempts để che giấu vấn đề gốc.

Không ghi toàn bộ parameter map, token hoặc thông tin cá nhân vào log. Có thể dùng request ID đã được làm sạch hoặc correlation ID để liên kết các lần thử của cùng một command.

## 12. Kiểm thử phân loại và retry

Nên kiểm thử cả quyết định retry lẫn trạng thái graph sau các lần thử:

1. **Transient failure rồi thành công:** lần đầu ném transient exception, lần sau thành công; xác nhận service transaction được gọi lại.
2. **Hết số lần thử:** mọi lần đều ném transient exception; xác nhận số lần gọi không vượt maxAttempts và fallback được gọi.
3. **Lỗi nghiệp vụ:** ném InsufficientStockException; xác nhận chỉ chạy một lần.
4. **Constraint violation:** xác nhận lỗi không bị retry như transient.
5. **Optimistic locking:** xác nhận policy không lặp lại entity cũ; use case reload/merge phải được kiểm thử riêng.
6. **Idempotency:** gửi cùng request ID nhiều lần; xác nhận không tạo đơn hàng trùng.
7. **Transaction boundary:** xác nhận mỗi attempt mở transaction mới và transaction thất bại không để lại thay đổi dở dang.
8. **Side effect:** xác nhận email hoặc message không bị gửi lặp khi database retry.

Một unit test có thể dùng mock để kiểm tra số lần gọi, nhưng cần integration test với Neo4j để xác minh transaction rollback và constraint thực tế. Không dựa riêng vào mock để kết luận database đã rollback.

## 13. Quy trình quyết định có retry hay không

Khi nhận exception từ một thao tác Neo4j, xử lý theo trình tự:

1. Kiểm tra exception type và cause chain.
2. Nếu có Neo4j error code, xác định nó có thuộc nhóm transient hay không.
3. Nếu là lỗi nghiệp vụ hoặc dữ liệu, trả lỗi phù hợp và dừng retry.
4. Nếu là optimistic locking, tải lại trạng thái và đánh giá xung đột theo domain.
5. Nếu là transient, xác nhận transaction hiện tại đã kết thúc hoặc rollback.
6. Kiểm tra command có idempotent và side effect ngoài database có được bảo vệ.
7. Nếu còn retry budget, chờ backoff rồi chạy lại toàn bộ transaction mới.
8. Nếu hết lượt, trả lỗi tạm thời và ghi nhận metric/log.

Đừng retry một exception chỉ vì nó xảy ra trong lúc có tải cao. Cần xác định nguyên nhân và bảo đảm lặp lại command không tạo thêm hiệu ứng ngoài dự kiến.

## 14. Bài tập tự kiểm tra

1. Khác biệt cốt lõi giữa deadlock transient và lỗi thiếu hàng là gì?
2. Vì sao không nên retry mọi DataAccessException?
3. Optimistic locking failure khác deadlock như thế nào và vì sao không nên retry cùng entity cũ?
4. Vì sao mỗi lần retry cần một transaction mới?
5. maxAttempts = 3 trong Spring Retry có nghĩa là ba lần retry hay ba lần thực hiện tổng cộng?
6. Vì sao retry một thao tác tạo node cần request ID hoặc idempotency key?
7. Vì sao không nên gửi email trong một method có thể được Spring Retry gọi lại?
8. Neo4j Driver executeWrite khác Spring Transactional trong SDN ở ranh giới retry như thế nào?
9. Những metric nào giúp phát hiện retry đang che giấu vấn đề contention hoặc hạ tầng?

Khi hoàn thành bài học, bạn cần phân biệt được lỗi transient, xung đột optimistic locking, lỗi dữ liệu và lỗi nghiệp vụ; biết đặt retry có giới hạn bên ngoài transaction; đồng thời bảo đảm command có thể chạy lại an toàn. Đây là nền tảng để xử lý tranh chấp đồng thời trong Spring Data Neo4j mà không tạo thêm dữ liệu trùng hoặc lặp side effect.

## Tài liệu tham khảo

- [Spring Framework – Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Spring Retry – Reference Documentation](https://github.com/spring-projects/spring-retry)
- [Neo4j Java Driver – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j – Status Codes](https://neo4j.com/docs/status-codes/current/)
- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)


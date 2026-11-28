# Rollback, rollbackFor và xử lý exception

Trong Spring Data Neo4j (SDN), các thao tác repository, Neo4jTemplate và Neo4jClient đồng bộ có thể tham gia một transaction do Spring quản lý. Khi lỗi xảy ra giữa chừng, transaction cần quyết định commit hay rollback để graph không được lưu ở trạng thái nghiệp vụ dở dang.

Spring quyết định rollback dựa trên loại exception thoát khỏi ranh giới transactional và các rollback rule được khai báo. Mặc định, RuntimeException và Error làm transaction rollback; checked exception không tự động làm rollback. Annotation @Transactional cho phép thay đổi quy tắc này bằng rollbackFor và noRollbackFor.

Bài học tập trung vào transaction đồng bộ trong ứng dụng Spring Data Neo4j: cách chọn rollback rule, ảnh hưởng của try/catch, rollback-only, exception lồng nhau và các giới hạn cần hiểu khi xử lý lỗi.

## 1. Transaction đồng bộ trong Spring Data Neo4j

Một service thường điều phối nhiều thao tác graph trong cùng một nghiệp vụ. Ví dụ, khi tạo đơn hàng, ứng dụng tạo node Order, liên kết với Customer và ghi một node audit. Nếu một thao tác thất bại, các thay đổi thuộc cùng transaction cần được rollback.

~~~mermaid
flowchart TD
    A["Service method có @Transactional"] --> B["Ghi Order"]
    B --> C["Tạo relationship tới Customer"]
    C --> D["Ghi Audit"]
    D --> E{"Có exception cần rollback?"}
    E -->|Không| F["Commit transaction"]
    E -->|Có| G["Rollback transaction"]
~~~

Trong ứng dụng imperative, Spring thường dùng Neo4jTransactionManager cùng Neo4j Java Driver để quản lý transaction. Spring Boot có thể tự cấu hình transaction manager khi dùng starter SDN. Repository, Neo4jTemplate và Neo4jClient cần dùng cùng cấu hình Driver/transaction manager để tham gia cùng transaction.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            CustomerRepository customerRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Order createOrder(String customerId, Order order) {
        Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

        order.assignCustomer(customer);
        Order saved = orderRepository.save(order);

        auditRepository.recordOrderCreated(saved.getId());

        return saved;
    }
}
~~~

Nếu exception phù hợp với rollback rule thoát khỏi phương thức transactional, các thao tác graph tham gia transaction sẽ không được commit. Rollback chỉ áp dụng cho thao tác database tham gia transaction đó; nó không tự hoàn tác email đã gửi, HTTP request tới dịch vụ khác hoặc ghi file bên ngoài.

## 2. Quy tắc rollback mặc định

Mặc định của Spring transaction declarative:

| Loại exception thoát khỏi phương thức | Hành vi mặc định |
| --- | --- |
| RuntimeException | Rollback |
| Lớp con của RuntimeException | Rollback |
| Error | Rollback |
| Checked exception, ví dụ IOException | Không tự động rollback |
| Exception được catch và không ném ra ngoài | Không kích hoạt rollback rule của interceptor bên ngoài |

Ví dụ unchecked exception:

~~~java
@Transactional
public void transferMembership(String teamId, String personId) {
    teamRepository.addMember(teamId, personId);

    if (!personRepository.existsById(personId)) {
        throw new IllegalStateException("Person không tồn tại");
    }
}
~~~

IllegalStateException là RuntimeException. Nếu nó thoát khỏi phương thức transactional, Spring đánh dấu transaction để rollback. Thao tác addMember sẽ không được commit.

Quy tắc này dựa trên loại exception thực tế được ném ra, không dựa vào tên method hoặc việc method có khai báo throws hay không. Một checked exception có thể được khai báo trong chữ ký method nhưng vẫn không rollback theo mặc định nếu không có rollback rule bổ sung.

## 3. Checked exception và rollbackFor

Checked exception thường biểu thị lỗi mà Java yêu cầu caller xử lý hoặc khai báo. Spring không tự rollback với checked exception theo quy tắc mặc định. Nếu checked exception thể hiện một thất bại khiến mọi thay đổi database phải bị hủy, hãy khai báo rollbackFor.

~~~java
public class InventoryUnavailableException extends Exception {

    public InventoryUnavailableException(String message) {
        super(message);
    }
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = InventoryUnavailableException.class)
public Order placeOrder(String customerId, Order order)
        throws InventoryUnavailableException {

    Customer customer = customerRepository.findById(customerId)
        .orElseThrow();

    Order saved = orderRepository.save(order);

    if (!inventoryService.reserve(order)) {
        throw new InventoryUnavailableException("Không đủ hàng");
    }

    saved.assignCustomer(customer);
    return orderRepository.save(saved);
}
~~~

Khi InventoryUnavailableException thoát khỏi phương thức, Spring rollback transaction dù exception là checked. Các thay đổi đã thực hiện trong transaction Neo4j chưa được commit.

Có thể khai báo nhiều loại exception:

~~~java
@Transactional(rollbackFor = {
    InventoryUnavailableException.class,
    IOException.class
})
public void processOrder() throws InventoryUnavailableException, IOException {
    // Các thao tác persistence.
}
~~~

Nếu mọi exception thuộc một nhánh type cụ thể đều cần rollback, có thể dùng lớp cha phù hợp, ví dụ rollbackFor = Exception.class. Hãy chọn phạm vi hẹp nhất đáp ứng nghiệp vụ để tránh rollback ngoài dự kiến.

## 4. noRollbackFor: Exception vẫn được ném nhưng transaction được commit

Đôi khi một exception biểu thị kết quả nghiệp vụ mà ứng dụng muốn thông báo cho caller, nhưng các thay đổi đã ghi vẫn cần được giữ lại. Khi đó có thể dùng noRollbackFor.

Ví dụ hệ thống lưu lại một lần từ chối đăng ký rồi ném exception để tầng API trả thông báo phù hợp:

~~~java
public class EnrollmentRejectedException extends RuntimeException {

    public EnrollmentRejectedException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional(noRollbackFor = EnrollmentRejectedException.class)
public void enroll(String studentId, String courseId) {
    enrollmentAuditRepository.recordRejectedAttempt(
        studentId,
        courseId,
        "COURSE_CLOSED"
    );

    throw new EnrollmentRejectedException("Khóa học đã đóng đăng ký");
}
~~~

Trong ví dụ này, nếu EnrollmentRejectedException là exception duy nhất thoát khỏi transaction và transaction chưa bị đánh dấu rollback-only ở nơi khác, Spring commit bản ghi audit rồi truyền exception cho caller.

noRollbackFor không có nghĩa là Spring bỏ qua mọi lỗi. Những exception khác vẫn áp dụng rollback rule tương ứng. Hãy dùng ngoại lệ này có chủ đích vì caller nhận lỗi trong khi dữ liệu transaction vẫn được commit.

Không dùng noRollbackFor cho exception thể hiện dữ liệu graph đã ở trạng thái không nhất quán. Nếu nghiệp vụ yêu cầu hủy toàn bộ thay đổi khi gặp lỗi, hãy để rollback xảy ra.

## 5. Chọn rollback rule theo kiểu exception

@Transactional hỗ trợ các thuộc tính chính:

| Thuộc tính | Mục đích |
| --- | --- |
| rollbackFor | Chỉ định exception type làm rollback |
| rollbackForClassName | Chỉ định pattern tên lớp exception làm rollback |
| noRollbackFor | Chỉ định exception type không làm rollback |
| noRollbackForClassName | Chỉ định pattern tên lớp exception không làm rollback |

Ưu tiên rollbackFor và noRollbackFor dùng class literal vì an toàn kiểu và dễ refactor:

~~~java
@Transactional(
    rollbackFor = PaymentDeclinedException.class,
    noRollbackFor = AuditRecordedException.class
)
public void processPayment() throws PaymentDeclinedException {
    // Thực hiện nghiệp vụ.
}
~~~

Các thuộc tính dạng ClassName dùng pattern tên lớp, không phải biểu thức regex. Pattern có thể khớp theo chuỗi con trong tên đầy đủ của exception; điều này có thể vô tình khớp một lớp khác có tên tương tự. Chỉ dùng pattern khi không thể tham chiếu trực tiếp class, và chọn tên đủ cụ thể.

Nếu một exception khớp nhiều rollback rule, Spring áp dụng rule cụ thể nhất theo độ gần của kiểu exception. Vì vậy, tránh khai báo các rule chồng chéo khó hiểu. Hãy viết một bộ rule nhỏ, có thể giải thích bằng ngôn ngữ nghiệp vụ và được kiểm thử.

## 6. Điều gì xảy ra khi exception bị catch?

Rollback rule được transaction interceptor áp dụng khi exception thoát khỏi phương thức transactional. Nếu code bắt exception rồi trả về bình thường, interceptor không nhìn thấy exception đó và có thể commit transaction.

Ví dụ dưới đây không tự rollback chỉ vì save ném exception đã được catch:

~~~java
@Transactional
public OperationResult updatePerson(String personId, String newName) {
    try {
        personRepository.updateName(personId, newName);
        return OperationResult.success();
    } catch (DataAccessException exception) {
        return OperationResult.failure("Không thể cập nhật");
    }
}
~~~

Nếu muốn rollback và vẫn trả về một kết quả thay vì ném exception, có thể đánh dấu transaction hiện tại rollback-only:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public OperationResult updatePerson(String personId, String newName) {
    try {
        personRepository.updateName(personId, newName);
        return OperationResult.success();
    } catch (DataAccessException exception) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return OperationResult.failure("Không thể cập nhật");
    }
}
~~~

setRollbackOnly() yêu cầu transaction rollback khi kết thúc, dù phương thức trả về bình thường. Chỉ gọi nó bên trong transaction được quản lý bởi Spring. Cách này hữu ích khi cần chuyển lỗi thành kết quả nghiệp vụ nhưng vẫn muốn hủy mọi thay đổi database.

Một cách khác là ghi log rồi ném lại exception hoặc chuyển thành unchecked exception:

~~~java
@Transactional
public void updatePerson(String personId, String newName) {
    try {
        personRepository.updateName(personId, newName);
    } catch (DataAccessException exception) {
        log.error("Cập nhật Person thất bại", exception);
        throw new PersonUpdateException("Không thể cập nhật hồ sơ", exception);
    }
}
~~~

Vì PersonUpdateException là unchecked exception, nó làm rollback theo mặc định. Luôn giữ exception gốc làm cause để không mất thông tin chẩn đoán.

## 7. Rollback-only và UnexpectedRollbackException

Một tình huống dễ gây bất ngờ xuất hiện khi nhiều phương thức transactional tham gia cùng một transaction bằng propagation mặc định REQUIRED.

Giả sử phương thức ngoài gọi phương thức trong qua Spring proxy. Phương thức trong ném unchecked exception; interceptor của phương thức trong đánh dấu transaction dùng chung là rollback-only. Phương thức ngoài bắt exception và tiếp tục, nhưng transaction không thể commit nữa.

~~~java
@Service
public class InnerService {

    @Transactional
    public void writeThenFail() {
        auditRepository.recordAttempt();
        throw new IllegalStateException("Lỗi trong thao tác con");
    }
}
~~~

~~~java
@Service
public class OuterService {

    private final InnerService innerService;

    public OuterService(InnerService innerService) {
        this.innerService = innerService;
    }

    @Transactional
    public void runWorkflow() {
        try {
            innerService.writeThenFail();
        } catch (IllegalStateException exception) {
            // Đã xử lý lỗi để tiếp tục logic khác.
        }

        // Transaction dùng chung vẫn có thể đã bị đánh dấu rollback-only.
    }
}
~~~

Khi runWorkflow() kết thúc, Spring thử commit nhưng phát hiện transaction đã rollback-only. Kết quả có thể là UnexpectedRollbackException ở ranh giới commit của phương thức ngoài. Bản ghi audit không được commit.

Điểm cần phân biệt:

- Nếu exception chỉ được ném và catch bên trong cùng một phương thức, không có interceptor transactional lồng nhau nhìn thấy exception, transaction không tự rollback chỉ vì exception từng được ném.
- Nếu một lời gọi transactional qua proxy đã đánh dấu transaction dùng chung rollback-only, việc catch exception ở bên ngoài không xóa trạng thái rollback-only.
- Nếu phương thức trong dùng transaction độc lập như REQUIRES_NEW, kết quả commit/rollback của nó có vòng đời riêng; chỉ dùng khi nghiệp vụ thực sự cần đơn vị transaction độc lập.

Không nên catch exception rồi giả định transaction có thể tiếp tục commit. Khi transaction đã rollback-only, hãy kết thúc luồng nghiệp vụ và để rollback diễn ra.

## 8. Ranh giới proxy và self-invocation

Trong chế độ proxy mặc định của Spring, @Transactional được áp dụng khi lời gọi đi qua Spring proxy. Gọi một phương thức transactional khác từ chính object bằng this không đi qua proxy, nên annotation ở phương thức được gọi nội bộ có thể không được áp dụng như mong đợi.

~~~java
@Service
public class PersonService {

    public void update() {
        this.updateInTransaction(); // Self-invocation: không đi qua proxy.
    }

    @Transactional
    public void updateInTransaction() {
        // Không nên giả định lời gọi nội bộ này mở transaction.
    }
}
~~~

Cách rõ ràng hơn là đặt ranh giới transaction ở phương thức public được gọi từ bean khác, hoặc tách phần transactional sang một service riêng và inject qua constructor. Điều này giúp transaction interceptor quan sát exception và áp dụng rollback rule đúng thời điểm.

Ngoài ra, không đưa thao tác đồng bộ sang một thread mới rồi mong transaction context tự truyền sang thread đó. Transaction đồng bộ của Spring thường gắn với thread hiện tại. Nếu cần xử lý bất đồng bộ, hãy thiết kế transaction riêng ở phía worker hoặc dùng cơ chế phù hợp với mô hình thực thi.

## 9. Exception từ Spring Data Neo4j

Các lỗi persistence thường được Spring dịch sang hệ exception DataAccessException, là unchecked exception. Khi exception này thoát khỏi phương thức @Transactional, rollback xảy ra theo mặc định.

Một số nhóm lỗi có thể gặp:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy dữ liệu | Không có node theo ID | Dùng Optional, kiểm tra nghiệp vụ trước khi ghi |
| Vi phạm constraint | Trùng giá trị duy nhất | Kiểm tra dữ liệu đầu vào và xử lý xung đột |
| Lỗi truy vấn | Cypher sai cú pháp hoặc tham số | Kiểm tra query, alias và bind parameter |
| Lỗi kết nối | Server không sẵn sàng hoặc kết nối bị ngắt | Xử lý lỗi hạ tầng, retry có giới hạn nếu thao tác an toàn |
| Optimistic locking | Version không còn khớp | Tải lại dữ liệu và xử lý xung đột theo nghiệp vụ |

Không nên catch tất cả DataAccessException rồi bỏ qua. Một lỗi constraint hoặc lỗi query thường có nghĩa thao tác nghiệp vụ không hoàn tất. Nếu chuyển exception thành response, hãy quyết định rõ transaction phải rollback hay commit.

## 10. Phạm vi rollback và tác động bên ngoài Neo4j

Rollback chỉ hoàn tác thay đổi thuộc transaction Neo4j. Ví dụ, nếu service ghi node rồi gửi email, sau đó transaction rollback, email đã gửi không tự biến mất.

~~~java
@Transactional
public void createAccount(Account account) {
    accountRepository.save(account);
    emailGateway.sendWelcomeEmail(account.getEmail());
    throw new IllegalStateException("Lỗi sau khi gửi email");
}
~~~

Database có thể rollback nhưng email đã gửi ra ngoài. Với tác vụ cần đồng bộ trạng thái database và side effect bên ngoài, cân nhắc Transactional Outbox: ghi một event/outbox record trong cùng transaction Neo4j, sau khi commit một worker riêng đọc record và gửi thông điệp/email. Worker cần cơ chế retry và idempotency phù hợp.

Không dùng rollback database như một cơ chế hoàn tác các hành động trên hệ thống khác.

## 11. Kiểm thử rollback rule

Nên có integration test xác minh trạng thái graph sau khi phương thức transactional hoàn tất hoặc ném exception. Ví dụ kiểm tra checked exception có rollback:

~~~java
@Test
void rollsBackWhenCheckedExceptionMatchesRule() {
    assertThatThrownBy(() ->
        orderService.placeOrderWithFailure("customer-1")
    ).isInstanceOf(InventoryUnavailableException.class);

    assertThat(orderRepository.findById("order-1")).isEmpty();
}
~~~

Và kiểm tra noRollbackFor giữ lại audit record:

~~~java
@Test
void commitsAuditWhenRejectionIsConfiguredAsNoRollback() {
    assertThatThrownBy(() ->
        enrollmentService.enrollClosedCourse("student-1", "course-1")
    ).isInstanceOf(EnrollmentRejectedException.class);

    assertThat(auditRepository.existsRejectedAttempt(
        "student-1", "course-1"
    )).isTrue();
}
~~~

Các ví dụ giả định fixture và test service tạo đúng ID tương ứng. Khi viết integration test, cần gọi service thông qua Spring bean được inject để transaction proxy thực sự tham gia. Gọi trực tiếp new Service(...) không kiểm tra được annotation transaction.

Các trường hợp nên kiểm thử:

1. RuntimeException làm rollback theo mặc định.
2. Checked exception không rollback nếu không có rule bổ sung.
3. Checked exception rollback khi khớp rollbackFor.
4. Exception được khai báo noRollbackFor vẫn được ném nhưng transaction commit.
5. Exception bị catch không đánh dấu rollback-only thì transaction có thể commit.
6. Exception bị catch sau khi transaction đã được đánh dấu rollback-only dẫn đến rollback và có thể phát sinh UnexpectedRollbackException.
7. Thao tác graph và repository cùng transaction được rollback đồng bộ.

## 12. Quy trình chọn cách xử lý exception

Khi thiết kế một transactional service, hãy lần lượt xác định:

1. Exception nào có thể xuất hiện trong use case?
2. Exception nào có nghĩa là toàn bộ thay đổi graph phải bị hủy?
3. Exception nào chỉ là tín hiệu nghiệp vụ nhưng dữ liệu audit vẫn cần commit?
4. Exception có bị catch trong cùng phương thức hay thoát qua transaction proxy?
5. Có lời gọi transactional lồng nhau nào đã đánh dấu transaction rollback-only không?
6. Có side effect ngoài Neo4j cần outbox hoặc cơ chế bù trừ không?
7. Integration test đã xác minh trạng thái graph sau commit và rollback chưa?

Hãy ưu tiên để exception phản ánh đúng ý nghĩa nghiệp vụ, khai báo rollback rule cụ thể và xử lý exception ở tầng phù hợp. Tránh dùng rollbackFor = Exception.class hoặc noRollbackFor = RuntimeException.class một cách máy móc nếu chưa đánh giá ảnh hưởng tới toàn bộ lỗi có thể phát sinh.

## 13. Bài tập tự kiểm tra

1. Spring mặc định rollback với RuntimeException và Error như thế nào?
2. Vì sao checked exception không tự rollback theo mặc định?
3. Khi nào cần dùng rollbackFor?
4. noRollbackFor có ý nghĩa gì nếu exception vẫn thoát khỏi phương thức?
5. Vì sao catch exception rồi trả kết quả bình thường có thể khiến transaction commit?
6. setRollbackOnly() thay đổi kết quả transaction như thế nào?
7. Vì sao outer method có thể gặp UnexpectedRollbackException sau khi đã catch exception từ inner method?
8. Self-invocation ảnh hưởng ra sao đến @Transactional trong proxy mode?
9. Rollback Neo4j có hoàn tác email đã gửi hoặc HTTP request đã thực hiện không?

Khi hoàn thành bài học, bạn cần dự đoán được transaction sẽ commit hay rollback theo loại exception, biết cấu hình rollbackFor/noRollbackFor, xử lý đúng exception bị catch và hiểu trạng thái rollback-only. Những quy tắc này giúp các thao tác node, relationship và repository trong Spring Data Neo4j giữ tính nhất quán khi nghiệp vụ gặp lỗi.

## Tài liệu tham khảo

- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)


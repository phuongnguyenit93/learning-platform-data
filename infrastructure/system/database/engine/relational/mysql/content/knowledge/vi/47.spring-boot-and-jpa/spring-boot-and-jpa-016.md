# Lỗi mất kết nối, retry có giới hạn và chống ghi trùng nghiệp vụ

Trong ứng dụng Spring Boot dùng JPA để ghi dữ liệu MySQL, mất kết nối không đồng nghĩa với transaction đã rollback. Nếu mạng đứt sau khi ứng dụng gửi COMMIT nhưng trước khi nhận phản hồi, MySQL có thể đã commit thành công trong khi ứng dụng chỉ nhận được lỗi. Gửi lại yêu cầu mà không kiểm tra có thể tạo đơn hàng, thanh toán hoặc bản ghi nghiệp vụ trùng lặp.

Muốn phục hồi an toàn, ứng dụng phải kết hợp ba cơ chế: phân loại lỗi theo nguyên nhân và thời điểm phát sinh, thực hiện retry có giới hạn với transaction mới, và bảo vệ thao tác ghi bằng idempotency key. Bài học thuộc module **DATABASE_MYSQL**, tập trung vào vận hành MySQL từ ứng dụng Java/Spring Boot/JPA, xử lý kết nối chập chờn, transaction, connection pool và tính đúng đắn của nghiệp vụ.

## 1. Hiểu đúng lỗi mất kết nối

Một request từ ứng dụng đến MySQL đi qua nhiều thành phần:

~~~text
HTTP client
    |
Spring Controller
    |
Application Service
    |
Spring Transaction Manager
    |
JPA / Hibernate / EntityManager
    |
JDBC / MySQL Connector/J
    |
Connection Pool
    |
Network / Proxy / Load Balancer
    |
MySQL Server
~~~

Lỗi có thể phát sinh ở bất kỳ tầng nào. Ví dụ:

- Connection pool cấp một connection đã bị MySQL hoặc firewall đóng.
- DNS, route hoặc firewall làm ứng dụng không thể mở kết nối mới.
- MySQL restart hoặc failover trong lúc request đang chạy.
- Proxy đóng connection idle theo thời hạn riêng.
- Socket timeout xảy ra khi server đang thực thi truy vấn.
- Client mất phản hồi sau khi server đã commit transaction.

Điểm quan trọng là ứng dụng chỉ quan sát được việc không nhận được phản hồi. Nó không phải lúc nào cũng biết server đã nhận câu lệnh, đã thực thi hay đã commit hay chưa.

### Ba trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Chắc chắn chưa gửi thao tác | Kết nối thất bại trước khi request được gửi đến server | Có thể tạo connection mới và thử lại nếu request còn hạn |
| Thao tác đã thất bại rõ ràng | Server trả lỗi xác định và transaction được rollback | Phân loại mã lỗi; có thể retry nếu lỗi tạm thời |
| Kết quả chưa xác định | Mất kết nối khi gửi, thực thi hoặc chờ phản hồi COMMIT | Tra cứu trạng thái nghiệp vụ bằng request key trước khi gửi lại |

Không được coi mọi **CommunicationsException**, socket timeout hoặc lỗi lớp SQLState 08 là bằng chứng transaction chưa commit. Đây là sai lầm dễ gây ghi trùng nhất.

## 2. Transaction JPA và ranh giới retry

Trong Spring, **@Transactional** thường được triển khai qua proxy và transaction manager. Khi method được gọi qua proxy, Spring bắt đầu transaction, liên kết EntityManager với transaction, rồi commit hoặc rollback khi method kết thúc.

Một phương thức nghiệp vụ điển hình:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Order order = Order.from(command);
        return orderRepository.save(order);
    }
}
~~~

Nếu kết nối mất trong lúc transaction đang commit, exception có thể chỉ xuất hiện khi proxy hoàn tất lời gọi method. Phần thân method có thể đã chạy đến dòng cuối nhưng transaction vẫn chưa được xác nhận thành công với client.

Theo mặc định, Spring đánh dấu rollback khi method transactional ném **RuntimeException** hoặc **Error**. Checked exception không tự động làm transaction rollback trong cấu hình mặc định. Nếu nghiệp vụ dùng checked exception để báo lỗi, khai báo **rollbackFor** phù hợp hoặc chuyển lỗi thành runtime exception theo quy ước của ứng dụng. Trước khi retry, phải chắc chắn transaction trước đã rollback và không còn trạng thái ghi dở.

### Vì sao không retry bên trong cùng transaction?

Khi transaction bị rollback hoặc connection bị hỏng:

- Transaction hiện tại không còn là môi trường an toàn để tiếp tục.
- EntityManager có thể đang giữ persistence context với entity và trạng thái không còn phù hợp.
- Một số exception khiến transaction bị đánh dấu rollback-only.
- Các câu lệnh đã chạy trong transaction có thể đã bị rollback; chạy lại riêng câu lệnh cuối không tái tạo đầy đủ logic.

Retry phải bắt đầu một transaction mới, đọc lại dữ liệu cần thiết và kiểm tra lại điều kiện nghiệp vụ. Không tái sử dụng entity đã được load trong persistence context cũ để quyết định ghi lần tiếp theo.

### Lưu ý về Open EntityManager in View

Nếu ứng dụng bật **Open EntityManager in View**, Spring có thể giữ một EntityManager gắn với request web trong suốt vòng đời request. Vì vậy, một transaction mới không phải lúc nào cũng đồng nghĩa với một persistence context mới. Sau rollback hoặc lỗi kết nối, không giữ managed entity từ lần thử trước rồi dùng lại ở lần sau. Hãy đọc lại dữ liệu trong transaction mới, cân nhắc tắt Open EntityManager in View cho luồng ghi cần retry, hoặc thiết kế ranh giới persistence context rõ ràng theo cấu hình JPA của ứng dụng.

### Tránh self-invocation với proxy

Trong cùng một bean, lời gọi từ method này sang method khác qua **this** thường không đi qua Spring proxy. Vì vậy, cấu trúc như sau có thể không tạo được transaction mới ở mỗi lần thử:

~~~java
public void retryOperation() {
    for (int i = 0; i < 3; i++) {
        this.writeInTransaction();
    }
}

@Transactional
public void writeInTransaction() {
    // ...
}
~~~

Hãy đặt phần thực thi transaction trong một bean riêng hoặc dùng **TransactionTemplate** để điều khiển ranh giới transaction một cách tường minh.

## 3. Phân loại lỗi Spring/JPA/MySQL

Spring thường chuyển SQLException hoặc exception của JPA/Hibernate thành hệ thống **DataAccessException**. Lớp exception ở ngoài cùng có thể khác nhau tùy driver, provider và tầng phát sinh lỗi. Vì vậy, không nên chỉ bắt một tên exception rồi giả định mọi lỗi cùng loại có thể retry.

### Các lỗi thường gặp

| Lỗi hoặc nhóm lỗi | Ví dụ | Định hướng xử lý |
|---|---|---|
| Deadlock | MySQL 1213, SQLState 40001 | Rollback toàn transaction và có thể retry từ đầu |
| Lock wait timeout | MySQL 1205, thường SQLState HY000 | Rollback toàn transaction ở ứng dụng, xem blocker rồi cân nhắc retry |
| Communications failure | Connector/J CommunicationsException, client code 2006/2013 | Connection mới; nếu commit chưa rõ thì tra cứu idempotency |
| Không tạo được connection | CannotGetJdbcConnectionException hoặc lỗi tài nguyên | Kiểm tra pool, endpoint và hạ tầng; retry chỉ khi lỗi tạm thời và còn deadline |
| Optimistic lock conflict | OptimisticLockingFailureException hoặc OptimisticLockException | Đọc lại dữ liệu và thử lại toàn bộ use case nếu nghiệp vụ cho phép |
| Pessimistic lock conflict | CannotAcquireLockException hoặc PessimisticLockingFailureException | Có thể retry có giới hạn sau rollback |
| Trùng khóa | MySQL 1062, DataIntegrityViolationException | Kiểm tra nghiệp vụ/idempotency; không retry mù |
| Sai SQL hoặc schema | MySQL 1054, 1064 | Sửa code hoặc schema; không retry |
| Sai quyền/xác thực | MySQL 1045, 1142 | Sửa cấu hình hoặc grant; không retry liên tục |

### Phân biệt transient và non-transient

Spring có các nhóm exception như:

- **TransientDataAccessException:** lỗi có thể tạm thời và có khả năng phục hồi sau khi thử lại.
- **NonTransientDataAccessException:** thử lại nguyên trạng thường không giải quyết được nguyên nhân.
- **ConcurrencyFailureException:** lỗi cạnh tranh transaction, ví dụ optimistic locking conflict.
- **DataIntegrityViolationException:** dữ liệu vi phạm constraint như unique key hoặc foreign key.
- **DataAccessResourceFailureException:** tài nguyên truy cập database gặp lỗi; không tự động đồng nghĩa với một lỗi transient.

Không retry mọi **DataAccessException**. Một exception về dữ liệu sai, thiếu quyền hoặc sai schema sẽ tiếp tục thất bại nếu gửi lại cùng request. Ngược lại, một lỗi kết nối có thể cần thay connection và xác minh transaction thay vì chỉ lặp lại method.

### Đọc nguyên nhân gốc

Khi chẩn đoán, ghi nhận:

- Loại exception ngoài cùng.
- Cause chain và SQLException chain.
- SQLState và vendor error code nếu có.
- Tên thao tác đang thực hiện: lấy connection, execute, flush, commit hay rollback.
- Transaction có thể đã commit hay chưa.

Với Hibernate, lỗi có thể được bọc trong exception của JPA hoặc Spring. Hãy duyệt nguyên nhân gốc thay vì chỉ dựa vào tên exception ở controller.

## 4. Retry có giới hạn và backoff

Retry có ích với lỗi cạnh tranh hoặc lỗi tài nguyên tạm thời. Nhưng retry liên tục có thể khuếch đại sự cố: database đang quá tải, nhiều request đồng loạt thử lại sẽ tạo thêm kết nối, truy vấn và transaction.

Một chính sách retry cần có:

1. Danh sách lỗi được phép retry.
2. Số lần thử tối đa.
3. Khoảng chờ tăng dần và jitter.
4. Deadline tổng thể của request.
5. Điều kiện bắt đầu transaction mới.
6. Cơ chế idempotency cho thao tác ghi.
7. Metric về retry và số lần thất bại cuối cùng.

### Exponential backoff và jitter

Công thức tham khảo:

**delay = min(maxDelay, baseDelay × 2^(attempt - 1)) + randomJitter**

Ví dụ:

| Lần thử tiếp theo | Backoff cơ sở | Jitter minh họa | Tổng thời gian chờ |
|---:|---:|---:|---:|
| 2 | 50 ms | 12 ms | 62 ms |
| 3 | 100 ms | 25 ms | 125 ms |
| 4 | 200 ms | 18 ms | 218 ms |

Jitter giúp phân tán các request đang cùng retry, tránh hiện tượng nhiều instance đồng loạt gửi lại tại cùng thời điểm. Giá trị thực tế phải phù hợp latency mục tiêu và thời gian còn lại của request.

Không chờ backoff trong khi transaction vẫn mở. Rollback và giải phóng connection trước, sau đó mới chờ và bắt đầu transaction tiếp theo.

## 5. Retry bằng TransactionTemplate

**TransactionTemplate** cho phép bao mỗi lần thử trong một transaction riêng. Đây là cách rõ ràng để bảo đảm exception lúc commit được ném ra bên ngoài vòng lặp retry.

Ví dụ cấu hình:

~~~java
@Configuration
public class TransactionRetryConfig {
    @Bean
    TransactionTemplate retryTransactionTemplate(
            PlatformTransactionManager transactionManager) {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setTimeout(5);
        return template;
    }
}
~~~

Bean thực hiện nghiệp vụ:

~~~java
@Service
public class OrderWriter {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderWriter(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public OrderResult place(CreateOrderCommand command) {
        int changed = inventory.reserve(
                command.sku(), command.quantity());

        if (changed != 1) {
            throw new OutOfStockException(command.sku());
        }

        Order order = Order.create(
                command.requestId(),
                command.customerId(),
                command.sku(),
                command.quantity());

        orders.save(order);
        return OrderResult.from(order);
    }
}
~~~

Facade retry nằm ngoài transaction:

~~~java
@Service
public class RetryingOrderService {
    private final TransactionTemplate transactionTemplate;
    private final OrderWriter orderWriter;

    public RetryingOrderService(
            TransactionTemplate transactionTemplate,
            OrderWriter orderWriter) {
        this.transactionTemplate = transactionTemplate;
        this.orderWriter = orderWriter;
    }

    public OrderResult place(CreateOrderCommand command) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return transactionTemplate.execute(
                        status -> orderWriter.place(command));
            } catch (RuntimeException error) {
                if (!RetryDecider.isRetryableTransactionError(error)
                        || attempt == maxAttempts) {
                    throw error;
                }

                RetryDelay.sleepWithJitter(attempt);
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
~~~

Các lớp **RetryDecider**, **RetryDelay**, **CreateOrderCommand** và repository là thành phần minh họa cần triển khai theo ứng dụng. Cấu hình **REQUIRES_NEW** giúp mỗi lần gọi tạo transaction mới; facade nên được gọi từ một luồng không nằm trong transaction nghiệp vụ khác. Nếu có transaction bên ngoài, nó sẽ bị suspend nhưng vẫn có thể giữ tài nguyên hoặc khóa, làm retry bên trong phức tạp.

Điểm quan trọng: lời gọi **transactionTemplate.execute(...)** chỉ trả kết quả sau khi transaction callback và bước commit hoàn tất. Nếu commit ném exception, vòng lặp bên ngoài mới nhận được lỗi. Không đặt vòng retry bên trong callback vì khi đó các lần thử có thể dùng chung transaction.

## 6. Dùng @Retryable và @Transactional đúng thứ tự

Có thể dùng Spring Retry hoặc cơ chế retry của framework đang được dự án quản lý. Tuy nhiên, thứ tự interceptor/proxy rất quan trọng.

Mô hình mong muốn:

~~~text
Retry interceptor
    |
    +-- Transaction interceptor: begin transaction 1
    |       execute use case
    |       commit / rollback
    |
    +-- Transaction interceptor: begin transaction 2
    |       execute use case again
    |       commit / rollback
    |
    +-- Transaction interceptor: begin transaction 3
            execute use case again
            commit / rollback
~~~

Mỗi lần thử phải tạo một transaction độc lập. Nếu transaction interceptor nằm ngoài retry interceptor, vòng retry có thể chạy bên trong một transaction duy nhất. Khi transaction đã rollback-only, các lần thử tiếp theo không còn ý nghĩa và có thể dẫn đến **UnexpectedRollbackException**.

Để tránh vấn đề proxy:

- Đặt method retry và method transactional ở hai bean khác nhau.
- Không gọi method transactional bằng self-invocation.
- Xác nhận retry interceptor bao ngoài transaction interceptor.
- Kiểm thử rằng mỗi lần thử có transaction ID hoặc connection/transaction mới.
- Ưu tiên TransactionTemplate nếu thứ tự annotation khó kiểm soát.

Không bắt tất cả exception bằng **@Retryable**. Chỉ cấu hình các loại lỗi tạm thời đã xác định; không retry validation error, constraint violation, lỗi quyền hoặc sai schema.

## 7. Chống ghi trùng bằng idempotency key

Idempotency có nghĩa một yêu cầu nghiệp vụ có thể được gửi lại nhiều lần nhưng kết quả nghiệp vụ chỉ được tạo một lần. Đây là lớp bảo vệ quan trọng khi client không biết transaction trước đã commit hay chưa.

Mỗi request tạo một mã ổn định, ví dụ:

- ID do client sinh và gửi trong header.
- Mã yêu cầu thanh toán từ hệ thống điều phối.
- UUID được tạo một lần ở đầu luồng nghiệp vụ và được giữ nguyên qua mọi lần retry.

Không tạo idempotency key mới ở mỗi lần thử. Nếu key thay đổi, database sẽ coi mỗi lần gửi là một yêu cầu khác.

### Thiết kế bảng

~~~sql
CREATE TABLE idempotency_request (
    request_key VARCHAR(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (request_key)
) ENGINE=InnoDB;
~~~

Các trường:

- **request_key:** khóa duy nhất của yêu cầu nghiệp vụ.
- **request_hash:** hash của payload đã chuẩn hóa, giúp phát hiện cùng key nhưng nội dung khác.
- **status:** trạng thái xử lý, ví dụ COMPLETED.
- **response_json:** kết quả đã lưu để trả lại cho lần gửi lại.
- **created_at/updated_at:** hỗ trợ kiểm tra và chính sách lưu giữ.

Nếu hệ thống đa tenant và request key chỉ duy nhất trong phạm vi tenant, hãy đưa tenant ID vào khóa duy nhất, ví dụ UNIQUE(tenant_id, request_key). Payload hash nên được tính từ biểu diễn chuẩn hóa của dữ liệu nghiệp vụ để tránh cùng một nội dung nhưng khác thứ tự field tạo ra hash khác nhau.

### Ghi idempotency trong cùng transaction

Trong một transaction:

1. Thử insert request key cùng request hash.
2. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
3. Lưu kết quả và cập nhật trạng thái COMPLETED.
4. Commit tất cả thay đổi cùng nhau.

Nếu transaction rollback, bản ghi idempotency và thay đổi nghiệp vụ cùng rollback. Nếu commit thành công nhưng phản hồi bị mất, lần gọi lại cùng key sẽ gặp duplicate key và có thể đọc kết quả đã lưu.

### Xử lý request trùng đồng thời

Unique primary key trên request key là điểm đồng bộ giữa các request. Khi hai instance cùng xử lý một key:

- Một transaction insert key trước.
- Transaction còn lại chờ kiểm tra unique constraint.
- Nếu transaction đầu commit, transaction sau nhận duplicate key.
- Nếu transaction đầu rollback, transaction sau có thể insert thành công.

Khi gặp duplicate key, không trả lỗi chung ngay. Mở transaction đọc bản ghi idempotency đã commit, so sánh request hash và trả lại response đã lưu nếu payload trùng. Nếu cùng key nhưng payload khác, trả lỗi conflict nghiệp vụ.

Không lưu trạng thái IN_PROGRESS ở một transaction riêng rồi mới thực hiện nghiệp vụ ở transaction khác nếu chưa thiết kế lease, timeout và cơ chế khôi phục. Cách đó có thể để lại request ở trạng thái đang xử lý dù worker đã chết. Với luồng đồng bộ đơn giản, lưu key, nghiệp vụ và response trong cùng transaction thường dễ bảo đảm tính nguyên tử hơn.

### Thời hạn lưu idempotency key

Không xóa bản ghi idempotency ngay sau khi trả response. Thời gian lưu cần dài hơn cửa sổ retry của client, thời gian xử lý sự cố và khoảng thời gian nghiệp vụ có thể nhận lại cùng yêu cầu. Nếu xóa key quá sớm, một request cũ được gửi lại có thể bị coi là yêu cầu mới và tạo giao dịch lần nữa. Chính sách dọn dẹp nên có retention rõ ràng, chạy theo batch và bảo đảm không xóa request còn đang được tra cứu hoặc đối soát.

## 8. Ví dụ luồng xử lý idempotent với JPA

Một cách triển khai là tạo một service transactional chuyên trách:

~~~java
@Service
public class IdempotentOrderWriter {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;

    public IdempotentOrderWriter(
            IdempotencyRepository idempotency,
            OrderRepository orders) {
        this.idempotency = idempotency;
        this.orders = orders;
    }

    @Transactional
    public OrderResult execute(CreateOrderCommand command) {
        IdempotencyRequest request = IdempotencyRequest.started(
                command.requestId(),
                command.payloadHash());

        idempotency.saveAndFlush(request);

        Order order = Order.create(command);
        orders.save(order);

        OrderResult result = OrderResult.from(order);
        request.complete(result.toJson());
        return result;
    }
}
~~~

**saveAndFlush** buộc Hibernate gửi INSERT idempotency xuống database sớm để phát hiện duplicate key trong transaction hiện tại. Nó không commit transaction. Bản ghi idempotency, đơn hàng và response vẫn được commit hoặc rollback cùng nhau.

Facade bên ngoài xử lý trường hợp request key đã tồn tại:

~~~java
public OrderResult handle(CreateOrderCommand command) {
    try {
        return writer.execute(command);
    } catch (DataIntegrityViolationException duplicate) {
        return lookupCompletedRequest(command);
    }
}
~~~

Ví dụ trên cần thu hẹp việc bắt lỗi: chỉ coi duplicate của constraint trên **request_key** là idempotency collision. Không được biến mọi DataIntegrityViolationException thành thành công vì lỗi có thể đến từ unique constraint khác, foreign key hoặc NOT NULL.

Sau khi bắt lỗi constraint, transaction đã có thể bị đánh dấu rollback-only. Việc tra cứu bản ghi đã commit nên thực hiện qua một service/transaction mới, bên ngoài transaction vừa thất bại. Kiểm tra request hash trước khi trả response.

## 9. Xử lý kết quả COMMIT chưa xác định

Khi Connector/J báo communications failure trong lúc commit, không thể dùng chính connection đó để hỏi xem transaction đã commit hay chưa. Hãy:

1. Đóng connection lỗi và để pool loại bỏ nó.
2. Lấy connection mới.
3. Tra cứu idempotency key hoặc mã nghiệp vụ ổn định.
4. Nếu đã có kết quả COMPLETED với payload hash khớp, trả kết quả đã lưu.
5. Nếu chưa có bản ghi, có thể thử thực hiện lại với cùng request key.
6. Nếu trạng thái không rõ do transaction đầu vẫn đang kết thúc hoặc hệ thống đang failover, chờ một khoảng ngắn rồi tra cứu lại trong deadline.

Không tạo request key mới để né duplicate key. Không tự suy luận rằng connection reset đồng nghĩa server rollback.

### Đối với request đọc

Truy vấn đọc thuần túy thường dễ retry hơn nếu có thể chạy lại mà không tạo tác dụng phụ. Tuy nhiên, kết quả đọc ở lần sau có thể khác do dữ liệu đã thay đổi. Nếu request cần snapshot nhất quán hoặc có pagination, hãy giữ semantics nghiệp vụ rõ ràng.

### Đối với request ghi

Request ghi cần idempotency hoặc một cách xác minh kết quả khác trước khi gửi lại. Các thao tác như tạo đơn hàng, trừ tồn kho, thu tiền, phát hành hóa đơn hoặc cấp quyền đều phải có mã nghiệp vụ ổn định.

## 10. Transactional outbox cho tác dụng phụ bên ngoài

Database transaction không thể tự rollback email đã gửi, lệnh thanh toán đã gọi qua HTTP hoặc message đã publish lên broker.

Không nên làm như sau:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    orderRepository.save(Order.create(command));
    paymentClient.charge(command.payment());
    emailClient.sendConfirmation(command.email());
}
~~~

Nếu transaction database bị rollback sau khi dịch vụ ngoài đã thực hiện, hệ thống sẽ không còn nhất quán. Nếu retry toàn method, thanh toán hoặc email có thể bị lặp.

Dùng transactional outbox:

1. Trong cùng transaction, ghi đơn hàng và một event vào bảng outbox.
2. Commit database.
3. Worker đọc event chưa gửi và publish hoặc gọi dịch vụ ngoài.
4. Ghi nhận kết quả gửi và retry worker theo event ID.
5. Consumer dùng event ID để chống xử lý lặp.

Ví dụ schema rút gọn:

~~~sql
CREATE TABLE outbox_event (
    event_id BINARY(16) PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
) ENGINE=InnoDB;
~~~

Outbox bảo đảm việc tạo event cùng commit với dữ liệu nghiệp vụ. Nó không bảo đảm broker chỉ nhận message đúng một lần; worker có thể gửi lại nếu mất phản hồi sau publish. Consumer vẫn cần idempotency theo event ID.

## 11. Connection pool và timeout trong Spring Boot

Spring Boot thường cấu hình một DataSource và connection pool như HikariCP. Pool giúp tái sử dụng connection, nhưng connection có thể hết hạn bởi MySQL, proxy, firewall hoặc load balancer.

Các thuộc tính cần đánh giá:

| Thuộc tính | Tầng | Vai trò |
|---|---|---|
| connectionTimeout | Pool | Thời gian tối đa chờ lấy connection từ pool |
| maxLifetime | Pool | Tuổi tối đa của connection trước khi pool thay mới |
| idleTimeout | Pool | Thời gian connection idle trước khi có thể bị loại bỏ |
| keepaliveTime | Pool | Kiểm tra/duy trì connection idle nếu phiên bản hỗ trợ |
| connectTimeout | Connector/J | Thời gian mở kết nối mạng |
| socketTimeout | Connector/J | Thời gian chờ dữ liệu trên socket |
| innodb_lock_wait_timeout | MySQL/InnoDB | Thời gian chờ khóa InnoDB |
| Transaction timeout | Spring | Giới hạn thời gian của transaction |

Đặt **maxLifetime** thấp hơn giới hạn tuổi connection của proxy hoặc database có thể giảm nguy cơ pool cấp lại connection đã bị hạ tầng đóng. Không đặt timeout bằng một con số ngẫu nhiên; đo thời gian query, thời hạn idle của proxy và chính sách server trước khi điều chỉnh.

### Cấu hình minh họa

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.com:3306/app?sslMode=VERIFY_IDENTITY
    username: DB_USER_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      connection-timeout: 3000
      max-lifetime: 1500000
      idle-timeout: 300000
      validation-timeout: 1000
~~~

Các giá trị trên chỉ là ví dụ, không phải khuyến nghị mặc định cho mọi hệ thống. Đặc biệt, socketTimeout và transaction timeout phải được chọn theo SLA, thời gian truy vấn hợp lệ và cơ chế hủy truy vấn của hệ thống.

Không nhúng mật khẩu vào source control hoặc URL được ghi log. Dùng secret manager hoặc biến môi trường được quản lý an toàn.

## 12. Không retry các lỗi nghiệp vụ và lỗi cấu hình

Các lỗi sau thường không thể khắc phục bằng retry nguyên trạng:

- Vi phạm unique key do dữ liệu đầu vào hoặc yêu cầu trùng.
- Vi phạm foreign key hoặc NOT NULL.
- SQL sai cú pháp hoặc tham chiếu cột không tồn tại.
- Thiếu quyền SELECT/INSERT/UPDATE.
- Sai mật khẩu hoặc authentication plugin không tương thích.
- Payload không hợp lệ hoặc không chuyển đổi được kiểu dữ liệu.
- Trạng thái nghiệp vụ không cho phép thao tác, ví dụ tồn kho bằng 0.

Retry các lỗi này chỉ làm tăng tải và tạo log nhiễu. Hãy trả lỗi nghiệp vụ rõ ràng hoặc sửa cấu hình/code.

### Chú ý lỗi optimistic locking

Với entity có **@Version**, Hibernate có thể phát hiện một transaction khác đã cập nhật bản ghi. Ứng dụng có thể retry nếu use case cho phép đọc lại trạng thái mới và tính toán lại kết quả. Không chỉ bỏ qua OptimisticLockException rồi ghi entity cũ lần nữa; điều đó có thể ghi đè thay đổi của người khác.

## 13. Kiểm thử retry và mất kết nối

Không thể chứng minh retry an toàn chỉ bằng unit test cho một vòng lặp. Cần integration test với MySQL thật hoặc môi trường tương đương production.

Các tình huống nên kiểm thử:

1. Deadlock 1213: transaction bị rollback và lần thử sau đọc lại dữ liệu.
2. Lock wait timeout 1205: ứng dụng rollback toàn transaction trước khi thử lại.
3. MySQL restart trước khi request được gửi: request được thực hiện lại khi server sẵn sàng.
4. Connection bị đóng khi đang đọc kết quả: connection lỗi bị loại khỏi pool.
5. Mất phản hồi sau COMMIT: gửi lại cùng request key và chỉ có một đơn hàng.
6. Hai instance nhận đồng thời cùng request key: unique constraint chỉ cho một kết quả nghiệp vụ.
7. Cùng request key nhưng payload khác: hệ thống trả conflict.
8. Worker outbox publish message rồi mất phản hồi: consumer không xử lý event hai lần.
9. Retry hết số lần: ứng dụng trả lỗi có kiểm soát và ghi nhận correlation ID.

Để mô phỏng mất phản hồi sau commit, cần môi trường thử nghiệm có thể cắt kết nối tại thời điểm phù hợp, chẳng hạn proxy hoặc network fault injection. Chỉ restart database ngẫu nhiên không bảo đảm đã kiểm tra đúng cửa sổ commit chưa xác định.

## 14. Quan sát và cảnh báo

Log và metric nên giúp trả lời:

- Lỗi xảy ra ở bước lấy connection, thực thi SQL, flush hay commit?
- SQLState, vendor code và root cause là gì?
- Request đã có idempotency key chưa?
- Lần thử hiện tại là lần thứ mấy?
- Bao nhiêu request đã hết retry?
- Có bao nhiêu request đang ở trạng thái commit chưa xác định?
- Pool có cạn connection hoặc tạo connection mới liên tục không?
- MySQL có deadlock, lock wait timeout, restart hoặc failover không?

Metric nên theo dõi:

- Số lỗi theo SQLState class và MySQL error code.
- Số communications failure theo datasource/endpoint.
- Tỷ lệ retry và retry exhaustion.
- Thời gian backoff và latency tổng của request.
- Số duplicate idempotency key và số payload hash mismatch.
- Active, idle, pending connection và connection creation rate.
- Deadlock, lock wait timeout và transaction duration.
- Số outbox event tồn đọng và tuổi event lâu nhất.

Không log mật khẩu, access token, dữ liệu cá nhân hoặc toàn bộ bind parameter nhạy cảm. Dùng request ID/correlation ID để nối log giữa API, transaction, worker và hệ thống ngoài.

## 15. Quy trình xử lý sự cố

Khi ứng dụng báo lỗi mất kết nối:

1. Xác định endpoint, instance, thời điểm và thành phần mạng liên quan.
2. Đọc SQLState, vendor code, exception class và cause chain.
3. Xác định lỗi xảy ra trước execute, trong execute, khi flush hay lúc commit.
4. Đóng connection lỗi và kiểm tra trạng thái pool.
5. Nếu transaction bị rollback rõ ràng và lỗi thuộc nhóm retry được, chạy lại toàn bộ use case trong transaction mới.
6. Nếu commit chưa xác định, tra cứu idempotency key trên connection mới.
7. Nếu đã có kết quả COMPLETED với payload hash khớp, trả kết quả đã lưu.
8. Nếu chưa có kết quả và còn trong deadline, thực hiện lại cùng request key.
9. Nếu trạng thái vẫn không rõ, trả trạng thái xử lý chưa xác định hoặc yêu cầu client tra cứu theo request ID; không tạo key mới.
10. Kiểm tra database, proxy, network và connection pool để xử lý nguyên nhân gốc.

## 16. Checklist triển khai

**Transaction**

- [ ] Retry nằm ngoài ranh giới transaction.
- [ ] Mỗi lần thử tạo transaction mới và persistence context phù hợp.
- [ ] Không retry qua self-invocation làm mất tác dụng proxy.
- [ ] Transaction được rollback trước khi chờ backoff.

**Retry**

- [ ] Chỉ retry lỗi tạm thời đã xác định.
- [ ] Có số lần thử tối đa, jitter và deadline.
- [ ] Không retry mù communications failure lúc commit.
- [ ] Lỗi dữ liệu, quyền và schema không bị retry tự động.

**Idempotency**

- [ ] Mỗi request ghi có request key ổn định.
- [ ] Request key có unique constraint trong database.
- [ ] Key, thay đổi nghiệp vụ và response được ghi cùng transaction.
- [ ] Payload hash được kiểm tra khi key đã tồn tại.
- [ ] Retention của idempotency key dài hơn cửa sổ retry và replay nghiệp vụ.
- [ ] Tác dụng phụ ngoài database dùng outbox hoặc cơ chế idempotent.

**Vận hành**

- [ ] Connection lỗi được loại khỏi pool.
- [ ] Timeout được chọn theo SLA và giới hạn hạ tầng.
- [ ] Có metric retry, communications failure và pool saturation.
- [ ] Đã kiểm thử mất phản hồi sau COMMIT và request trùng đồng thời.
- [ ] Có quy trình tra cứu kết quả bằng request ID.

## Tài liệu tham khảo

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [MySQL Reference Manual — InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-error-handling.html)
- [MySQL Connector/J — Exception Handling](https://dev.mysql.com/doc/connector-j/en/connector-j-exceptions.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)

## Kết luận

Lỗi mất kết nối trong Spring Boot/JPA cần được xử lý theo thời điểm phát sinh và trạng thái transaction. Deadlock hoặc lock timeout có thể được retry sau khi rollback toàn transaction; communications failure lúc COMMIT phải được coi là kết quả chưa xác định cho đến khi tra cứu nghiệp vụ. Đặt retry ngoài transaction, tạo transaction mới cho mỗi lần thử, giới hạn số lần và dùng backoff có jitter. Idempotency key bảo vệ thao tác ghi khỏi bị thực hiện trùng, còn transactional outbox giúp tách tác dụng phụ bên ngoài khỏi transaction database. Khi kết hợp các cơ chế này với giám sát connection pool và kiểm thử lỗi mạng, ứng dụng có thể phục hồi mà vẫn giữ tính đúng đắn nghiệp vụ.

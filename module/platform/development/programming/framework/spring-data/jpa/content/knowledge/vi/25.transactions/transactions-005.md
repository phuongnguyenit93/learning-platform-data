# Propagation REQUIRED, REQUIRES_NEW và giới hạn NESTED với JPA

## 1. Mục tiêu và bối cảnh

Trong Spring, transaction propagation (cách truyền tiếp giao dịch) quyết định một phương thức được gọi sẽ tham gia giao dịch đang tồn tại, tạo giao dịch độc lập hay tạo một điểm lưu để có thể hoàn tác một phần. Nó trả lời câu hỏi **phương thức được gọi liên kết với transaction của bên gọi như thế nào**.

Ba giá trị thường gặp là:

- **REQUIRED**: tham gia transaction hiện tại; nếu chưa có thì tạo transaction mới.
- **REQUIRES_NEW**: tạm dừng transaction hiện tại và luôn tạo một transaction độc lập.
- **NESTED**: tạo savepoint bên trong transaction hiện tại để có thể rollback về savepoint; đây là cơ chế dựa trên JDBC và có giới hạn rõ rệt khi dùng JPA.

Cần phân biệt hai khái niệm:

- **Physical transaction** là transaction thực sự do database/resource quản lý, có lần commit hoặc rollback cuối cùng.
- **Logical transaction scope** là phạm vi phương thức được Spring áp dụng thuộc tính transaction. Nhiều scope có thể cùng tham gia một physical transaction.

Ví dụ, service gọi hai repository trong cùng một phương thức @Transactional thường chỉ sử dụng một physical transaction. Mỗi lời gọi repository không tự tạo một lần commit riêng.

Để sử dụng propagation của Spring, import annotation và enum sau:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
```

Dùng annotation **org.springframework.transaction.annotation.Transactional** khi cần khai báo **Propagation.NESTED**. Annotation **jakarta.transaction.Transactional** có các kiểu transaction chuẩn JTA nhưng không có kiểu NESTED.

Ứng dụng cần có transaction manager phù hợp và bật quản lý transaction bằng annotation. Spring Boot thường tự cấu hình phần này khi có starter và datasource phù hợp; trong cấu hình Spring thủ công, có thể dùng **@EnableTransactionManagement** cùng một bean **PlatformTransactionManager**.

Mặc định, **@Transactional** dùng **Propagation.REQUIRED**, isolation **DEFAULT**, transaction read-write. Spring thường rollback khi phương thức thoát ra bằng **RuntimeException** hoặc **Error**; checked exception không tự động làm rollback theo mặc định. Có thể khai báo **rollbackFor** hoặc **noRollbackFor** để thay đổi quy tắc.

Trong chế độ proxy mặc định, Spring chỉ áp dụng transaction khi lời gọi đi qua proxy của bean. Một phương thức gọi trực tiếp phương thức khác trong cùng instance (self-invocation) sẽ không đi qua proxy; annotation trên phương thức được gọi vì thế không tạo propagation boundary mới. Đặt hai nghiệp vụ cần propagation khác nhau ở hai Spring bean riêng là cách triển khai dễ kiểm soát.

## 2. So sánh ba propagation

| Tiêu chí | REQUIRED | REQUIRES_NEW | NESTED |
|---|---|---|---|
| Không có transaction hiện tại | Tạo transaction mới | Tạo transaction mới | Tạo transaction mới nếu transaction manager hỗ trợ |
| Đã có transaction hiện tại | Tham gia transaction đó | Tạm dừng transaction ngoài, tạo transaction mới | Dùng transaction ngoài và tạo savepoint |
| Physical transaction | Dùng chung với bên gọi | Độc lập với bên gọi | Dùng chung với bên gọi |
| Rollback phạm vi bên trong | Có thể đánh dấu transaction chung là rollback-only | Chỉ rollback transaction bên trong | Rollback về savepoint; transaction ngoài có thể tiếp tục |
| Commit | Chỉ commit khi physical transaction chung kết thúc | Có thể commit độc lập trước khi transaction ngoài kết thúc | Không commit độc lập; commit cuối cùng vẫn phụ thuộc transaction ngoài |
| Phù hợp với JPA | Có | Có | Không nên dùng để rollback thao tác qua EntityManager |

**Điểm phân biệt quan trọng:** **REQUIRES_NEW** tạo transaction vật lý thứ hai. **NESTED** chỉ tạo điểm quay lui trong transaction vật lý hiện tại. Một savepoint không phải là một transaction độc lập.

## 3. PROPAGATION_REQUIRED

### Cách hoạt động

**REQUIRED** là propagation mặc định của **@Transactional**.

- Nếu chưa có transaction, Spring bắt đầu một physical transaction.
- Nếu đã có transaction, phương thức được gọi tham gia transaction đó.
- Các thay đổi của service và repository cùng được commit hoặc rollback theo transaction chung.

Ví dụ, **OrderService** lưu đơn hàng rồi gọi **StockService** để giảm tồn kho. Cả hai phương thức dùng **REQUIRED**, vì vậy việc lưu đơn hàng và cập nhật tồn kho thuộc cùng một transaction.

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final StockService stockService;

    public OrderService(
            OrderRepository orderRepository,
            StockService stockService) {
        this.orderRepository = orderRepository;
        this.stockService = stockService;
    }

    @Transactional // REQUIRED là mặc định
    public void placeOrder(Order order) {
        orderRepository.save(order);
        stockService.decrease(order.getProductId());
    }
}

@Service
public class StockService {

    private final ProductRepository productRepository;

    public StockService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void decrease(long productId) {
        Product product = productRepository.findById(productId)
                .orElseThrow();
        product.decreaseStock(1);
    }
}
```

Đây là đoạn mã minh họa các service và repository; các entity, repository interface và cấu hình ứng dụng được lược bỏ. Hai service phải là các bean riêng để lời gọi **stockService.decrease()** đi qua Spring proxy.

Nếu **decrease()** gặp lỗi làm transaction rollback, transaction lưu đơn hàng cũng rollback. Database không giữ lại đơn hàng đã lưu dở dang trong khi tồn kho chưa được cập nhật.

### Rollback-only và UnexpectedRollbackException

Các scope **REQUIRED** tham gia cùng một physical transaction. Nếu phương thức bên trong thoát ra bằng exception thuộc quy tắc rollback, Spring đánh dấu transaction chung là **rollback-only**.

Một tình huống dễ gây nhầm lẫn:

1. Phương thức bên ngoài bắt đầu transaction.
2. Phương thức **REQUIRED** bên trong gặp **RuntimeException**; interceptor đánh dấu transaction chung rollback-only.
3. Phương thức bên ngoài bắt exception và tiếp tục chạy.
4. Phương thức bên ngoài kết thúc bình thường và yêu cầu commit.
5. Spring rollback transaction và thông báo cho bên gọi bằng **UnexpectedRollbackException**.

Việc bắt exception trong phương thức bên ngoài không xóa cờ rollback-only đã được đặt bởi scope bên trong. Điều này giúp bên gọi không hiểu nhầm rằng transaction đã commit thành công.

Quy tắc này áp dụng khi exception đi qua transaction interceptor và kích hoạt rollback rule. Nếu lỗi được xử lý hoàn toàn bên trong phương thức trước khi thoát khỏi interceptor, Spring không tự biết rằng cần rollback.

### Thuộc tính transaction khi tham gia transaction ngoài

Khi một scope **REQUIRED** tham gia transaction đã có, transaction ngoài quyết định các thuộc tính thực tế. Theo mặc định, isolation, timeout và read-only được khai báo ở scope bên trong sẽ bị bỏ qua. Có thể bật **validateExistingTransaction** trên transaction manager để phát hiện một số cấu hình isolation hoặc read-only không tương thích và từ chối tham gia.

**Nên dùng REQUIRED khi:**

- Nhiều thao tác phải thành công hoặc thất bại cùng nhau.
- Một use case của service gọi nhiều repository.
- Cần giữ tính nhất quán giữa đơn hàng, chi tiết đơn hàng, tồn kho hoặc dữ liệu liên quan.

## 4. PROPAGATION_REQUIRES_NEW

### Cách hoạt động

**REQUIRES_NEW** luôn tạo một physical transaction mới. Nếu transaction ngoài đang chạy, Spring tạm dừng nó trong thời gian transaction bên trong thực hiện.

Khi phương thức bên trong kết thúc:

- Nếu thành công, transaction bên trong commit độc lập.
- Nếu thất bại theo rollback rule, transaction bên trong rollback độc lập.
- Spring khôi phục transaction ngoài để phương thức bên ngoài tiếp tục.

Transaction bên trong không dùng chung kết quả commit/rollback với transaction ngoài. Vì vậy, transaction bên trong đã commit vẫn được giữ lại ngay cả khi transaction ngoài rollback sau đó.

### Ví dụ: ghi nhật ký thất bại độc lập

Giả sử nghiệp vụ tạo đơn hàng thất bại và transaction tạo đơn hàng phải rollback, nhưng hệ thống vẫn muốn lưu lại một bản ghi audit về lỗi. Có thể dùng một bean audit riêng với **REQUIRES_NEW**.

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String orderCode, String reason) {
        auditRepository.save(new AuditLog(orderCode, reason));
    }
}

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditService auditService;
    private final PaymentGateway paymentGateway;

    public OrderService(
            OrderRepository orderRepository,
            AuditService auditService,
            PaymentGateway paymentGateway) {
        this.orderRepository = orderRepository;
        this.auditService = auditService;
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public void placeOrder(Order order) {
        orderRepository.save(order);

        try {
            paymentGateway.charge(order);
        } catch (PaymentRejectedException ex) {
            auditService.recordFailure(
                    order.getOrderCode(), ex.getMessage());
            throw ex;
        }
    }
}
```

**PaymentRejectedException** trong ví dụ là exception nghiệp vụ kế thừa **RuntimeException**; **PaymentGateway**, các lớp domain và repository được lược bỏ. **AuditService** là bean khác nên lời gọi đi qua proxy và tạo transaction mới.

Khi **recordFailure()** lưu audit thành công, nó commit trước khi exception được ném lại. Exception tiếp tục thoát khỏi **placeOrder()**, khiến transaction tạo đơn hàng rollback theo quy tắc mặc định; bản ghi audit vẫn tồn tại.

Ví dụ dùng **orderCode** làm mã tham chiếu audit. Nếu transaction ngoài vừa tạo một hàng đơn hàng chưa commit và transaction audit mới cần tham chiếu hàng đó bằng khóa ngoại, transaction mới có thể không nhìn thấy hàng chưa commit hoặc bị chặn bởi ràng buộc khóa ngoại. Hãy thiết kế quan hệ dữ liệu cho phù hợp với tính độc lập của hai transaction.

### Tài nguyên và rủi ro

Khi transaction ngoài bị tạm dừng, tài nguyên của nó, chẳng hạn connection, vẫn có thể được giữ. Transaction **REQUIRES_NEW** cần tài nguyên riêng, thường là một database connection khác.

Nếu nhiều luồng cùng giữ connection của transaction ngoài rồi chờ connection cho transaction bên trong, connection pool có thể cạn và gây chờ đợi hoặc deadlock. Tài liệu Spring khuyến nghị pool phải có dung lượng vượt số luồng đồng thời ít nhất một connection khi dùng mô hình này; hệ thống có nhiều tầng **REQUIRES_NEW** cần tính thêm mức tiêu thụ tài nguyên.

Transaction mới cũng không thể tự do đọc các thay đổi chưa commit của transaction ngoài. Nếu nó truy cập hàng đang bị transaction ngoài khóa, nó có thể phải chờ. Vì vậy, không nên gọi **REQUIRES_NEW** một cách máy móc trong vòng lặp hoặc trên mọi thao tác repository.

**Nên dùng REQUIRES_NEW khi:**

- Cần ghi audit hoặc trạng thái phụ phải tồn tại độc lập với kết quả nghiệp vụ chính.
- Một thao tác phụ cần isolation, timeout hoặc read-only riêng.
- Chấp nhận việc transaction phụ commit ngay cả khi transaction chính thất bại.

Không nên dùng **REQUIRES_NEW** cho mọi bản ghi outbox cần đồng bộ nguyên tử với dữ liệu nghiệp vụ. Với transactional outbox, thông thường bản ghi nghiệp vụ và outbox phải commit trong cùng transaction **REQUIRED**; nếu tách ra, có thể xuất hiện dữ liệu nghiệp vụ đã rollback nhưng sự kiện vẫn được phát đi, hoặc ngược lại.

## 5. PROPAGATION_NESTED và giới hạn với JPA

### Savepoint hoạt động như thế nào?

**NESTED** dùng một physical transaction duy nhất nhưng tạo savepoint tại ranh giới của scope bên trong.

Giả sử transaction ngoài thực hiện A, gọi scope nested thực hiện B và sau đó thực hiện C:

1. Transaction ngoài bắt đầu và thực hiện A.
2. Spring tạo savepoint.
3. Scope nested thực hiện B.
4. Nếu scope nested rollback, database quay về savepoint: B bị hoàn tác, A vẫn nằm trong transaction.
5. Transaction ngoài tiếp tục thực hiện C.
6. Khi transaction ngoài commit, A và C được commit cùng nhau.

Nếu scope nested thành công, savepoint được giải phóng; dữ liệu vẫn chờ transaction ngoài commit. Vì vậy, **NESTED** không có khả năng commit độc lập như **REQUIRES_NEW**.

Cơ chế này thường được ánh xạ sang JDBC savepoint. Nó chỉ hoạt động khi transaction manager, resource và JDBC driver hỗ trợ savepoint.

### Vì sao NESTED không tương đương nested transaction trong JPA?

JPA không định nghĩa nested transaction. **EntityManager** quản lý persistence context, gồm các entity đang được quản lý và trạng thái trong bộ nhớ. Rollback một JDBC savepoint không tự khôi phục trạng thái các entity trong persistence context về thời điểm savepoint được tạo.

Với **JpaTransactionManager**:

- **nestedTransactionAllowed** mặc định là **false**.
- Có thể bật tùy chọn này để dùng savepoint cho phần JDBC truy cập cùng transaction, nếu driver hỗ trợ.
- Savepoint chỉ điều khiển JDBC connection; nó không cung cấp rollback một phần có ngữ nghĩa đầy đủ cho các thay đổi do JPA **EntityManager** quản lý.
- Không nên giả định rằng entity đã thay đổi trong scope nested sẽ tự trở về trạng thái cũ sau rollback savepoint.

Điểm cuối rất quan trọng: trạng thái object trong persistence context có thể không còn đồng bộ với trạng thái database sau rollback savepoint. Một lần flush tiếp theo có thể khiến ứng dụng ghi lại trạng thái không mong muốn. Việc bật **nestedTransactionAllowed** không biến JPA thành hệ thống hỗ trợ nested transaction.

### Ví dụ savepoint chỉ dành cho JDBC

Ví dụ sau minh họa cơ chế JDBC, không phải cách rollback một phần thao tác JPA. **BatchService** và **NestedJdbcWriter** phải là hai Spring bean riêng. Transaction manager phải hỗ trợ savepoint và cả hai thao tác phải dùng cùng JDBC resource.

```java
@Service
public class NestedJdbcWriter {

    private final JdbcTemplate jdbcTemplate;

    public NestedJdbcWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void insertOptionalRow(String value) {
        jdbcTemplate.update(
                "insert into import_item(value) values (?)", value);
        throw new InvalidRowException("Dữ liệu không hợp lệ");
    }
}

@Service
public class BatchService {

    private final JdbcTemplate jdbcTemplate;
    private final NestedJdbcWriter nestedJdbcWriter;

    public BatchService(
            JdbcTemplate jdbcTemplate,
            NestedJdbcWriter nestedJdbcWriter) {
        this.jdbcTemplate = jdbcTemplate;
        this.nestedJdbcWriter = nestedJdbcWriter;
    }

    @Transactional
    public void importBatch() {
        jdbcTemplate.update(
                "insert into import_log(message) values (?)", "Bắt đầu");

        try {
            nestedJdbcWriter.insertOptionalRow("row-1");
        } catch (InvalidRowException ex) {
            // Phần JDBC bên trong đã rollback về savepoint.
            // Transaction ngoài vẫn có thể tiếp tục.
        }

        jdbcTemplate.update(
                "insert into import_log(message) values (?)", "Tiếp tục");
    }
}
```

Đây là đoạn mã minh họa; cần có bảng, exception **InvalidRowException**, datasource và cấu hình transaction manager phù hợp. Với **DataSourceTransactionManager**, cần driver hỗ trợ JDBC savepoint. Nếu dùng **JpaTransactionManager**, chỉ bật nested cho JDBC khi đã hiểu rõ giới hạn persistence context; không dùng ví dụ này để suy ra rằng thao tác qua repository hoặc **EntityManager** cũng được rollback một phần an toàn.

### Nên làm gì khi ứng dụng dùng Spring Data JPA?

- Dùng **REQUIRED** nếu tất cả thay đổi entity trong use case phải commit hoặc rollback cùng nhau.
- Dùng **REQUIRES_NEW** nếu cần một transaction JPA độc lập thực sự, chẳng hạn ghi audit tách biệt.
- Nếu chỉ muốn bỏ qua một phần tử lỗi trong lô dữ liệu, cân nhắc tách từng phần tử thành transaction độc lập bằng **REQUIRES_NEW**, hoặc xử lý từng phần tử ở ranh giới transaction riêng. Đánh giá rõ tác động của việc commit từng phần tử.
- Nếu yêu cầu là rollback một phần bằng savepoint, giới hạn phần đó vào JDBC và kiểm tra transaction manager, datasource cùng driver. Không dựa vào trạng thái entity đang được JPA quản lý để đạt hành vi này.
- Nếu cần hoàn tác nghiệp vụ đã commit, thiết kế thao tác bù (compensation) hoặc quy trình saga phù hợp; savepoint không thể đảo ngược một transaction độc lập đã commit.

## 6. Chọn propagation theo yêu cầu nghiệp vụ

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Lưu đơn hàng và trừ tồn kho phải cùng thành công | REQUIRED | Cùng một physical transaction |
| Service gọi nhiều repository trong một use case | REQUIRED | Giữ ranh giới transaction ở tầng service |
| Ghi audit vẫn phải tồn tại khi nghiệp vụ chính rollback | REQUIRES_NEW | Transaction audit commit độc lập |
| Ghi một dữ liệu phụ có thể thất bại mà không rollback transaction ngoài | REQUIRES_NEW hoặc NESTED JDBC | Chọn theo yêu cầu độc lập commit hay rollback về savepoint |
| Muốn rollback một phần các thay đổi qua JPA EntityManager | Không dựa vào NESTED | JPA không hỗ trợ nested transaction |
| Muốn ghi outbox nguyên tử cùng dữ liệu nghiệp vụ | REQUIRED | Hai loại dữ liệu cần cùng commit hoặc rollback |

Trước khi chọn, hãy trả lời ba câu hỏi:

1. Nếu phương thức bên trong thất bại, dữ liệu của phương thức bên ngoài có phải rollback không?
2. Nếu phương thức bên trong thành công, nó có được phép commit ngay cả khi phương thức bên ngoài rollback không?
3. Yêu cầu rollback một phần có áp dụng cho JDBC savepoint hay cho entity được JPA quản lý?

Nếu câu trả lời cho câu 1 là “có”, thường chọn **REQUIRED**. Nếu câu trả lời cho câu 2 là “có”, xem xét **REQUIRES_NEW**. Nếu cần hành vi savepoint, xác định rõ phần việc là JDBC và transaction manager có hỗ trợ hay không trước khi dùng **NESTED**.

## 7. Spring Data JPA và ranh giới transaction

Spring Data JPA cung cấp cấu hình transaction mặc định cho các phương thức CRUD kế thừa từ **CrudRepository**/**JpaRepository** thông qua **SimpleJpaRepository**:

- Các thao tác đọc thường được cấu hình **readOnly = true**.
- Các thao tác ghi dùng **@Transactional** với cấu hình mặc định.
- Các query method tự khai báo không tự động có transaction configuration; cần khai báo **@Transactional** nếu phương thức cần transaction.

Trong nghiệp vụ gồm nhiều thao tác repository, nên đặt ranh giới transaction tại service. Ví dụ, service **placeOrder()** có thể gọi lưu đơn hàng, lưu chi tiết và giảm tồn kho trong cùng một **REQUIRED** transaction. Khi đã có transaction ngoài, thuộc tính của transaction ngoài quyết định transaction thực tế mà các repository tham gia.

**readOnly = true** là một gợi ý cho transaction manager/JDBC/JPA provider để tối ưu đọc, không phải cơ chế bảo đảm mọi lệnh ghi đều bị chặn. Một số database có thể từ chối lệnh ghi trong read-only transaction, nhưng không nên dựa vào thuộc tính này như một hàng rào phân quyền dữ liệu.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Annotation **REQUIRES_NEW** không tạo transaction mới | Gọi nội bộ cùng class, bỏ qua proxy | Chuyển phương thức sang bean khác và gọi qua bean được inject |
| Bắt exception rồi vẫn gặp **UnexpectedRollbackException** | Scope **REQUIRED** bên trong đã đánh dấu transaction chung rollback-only | Kiểm tra exception đi qua interceptor và rollback rule; thiết kế lại ranh giới transaction |
| Audit bị mất khi đơn hàng rollback | Audit đang tham gia **REQUIRED** cùng transaction ngoài | Dùng **REQUIRES_NEW** nếu audit phải tồn tại độc lập |
| Hệ thống cạn connection khi dùng **REQUIRES_NEW** | Transaction ngoài vẫn giữ connection trong khi transaction trong cần connection mới | Đánh giá kích thước pool, số luồng đồng thời và số tầng transaction mới |
| **NESTED** không chạy với JPA | Transaction manager không hỗ trợ savepoint hoặc nested chưa được bật | Kiểm tra transaction manager và driver; chỉ dùng nested cho JDBC khi phù hợp |
| Database rollback nhưng object Java vẫn mang giá trị đã sửa | Persistence context không được khôi phục theo JDBC savepoint | Không tiếp tục dùng trạng thái entity đó như thể nó đã được rollback; làm mới/đọc lại hoặc thiết kế transaction khác |
| Query method không có transaction như mong đợi | Query method tự khai báo không có transaction mặc định | Đặt **@Transactional** ở service hoặc repository phù hợp |

Các kiểm tra tích hợp nên xác minh trạng thái database sau commit/rollback, không chỉ kiểm tra lời gọi repository bằng mock:

1. Với **REQUIRED**, gây lỗi trong scope bên trong, bắt lỗi ở bên ngoài và xác minh transaction chung không commit; kiểm tra **UnexpectedRollbackException** ở ranh giới commit.
2. Với **REQUIRES_NEW**, để transaction bên trong ghi audit thành công rồi làm transaction ngoài rollback; xác minh audit còn tồn tại.
3. Với **NESTED**, kiểm tra savepoint bằng JDBC trên transaction manager và driver thực tế; không dùng kết quả JDBC để kết luận rằng entity JPA được khôi phục.
4. Đảm bảo lời gọi đi qua Spring proxy trong các bài kiểm thử propagation.

## 9. Ghi nhớ

- **REQUIRED**: tham gia transaction hiện tại hoặc tạo mới; phù hợp với nghiệp vụ cần tính nguyên tử.
- **REQUIRES_NEW**: tạm dừng transaction ngoài và tạo transaction vật lý độc lập; commit/rollback độc lập nhưng tiêu tốn thêm tài nguyên.
- **NESTED**: dùng savepoint trong cùng transaction; rollback một phần chỉ có ý nghĩa khi transaction manager và JDBC resource hỗ trợ.
- **NESTED không phải nested transaction của JPA**. **JpaTransactionManager** mặc định không bật nested; ngay cả khi bật, savepoint chỉ kiểm soát JDBC connection chứ không hoàn nguyên persistence context.
- **@Transactional** trong proxy mode cần lời gọi qua proxy; self-invocation không kích hoạt propagation như mong đợi.

## 10. Tài liệu tham khảo

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — JpaTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)

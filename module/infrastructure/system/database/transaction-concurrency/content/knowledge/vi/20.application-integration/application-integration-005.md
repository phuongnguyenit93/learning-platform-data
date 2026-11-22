# Phân biệt giao dịch độc lập, tham gia giao dịch và SAVEPOINT

Khi một ứng dụng gọi nhiều service hoặc nhiều hàm cùng thao tác database, câu hỏi quan trọng không chỉ là "có transaction hay không", mà còn là **mỗi phần công việc đang dùng chung transaction nào và rollback sẽ ảnh hưởng đến phạm vi nào**.

Có ba cách tổ chức thường gặp:

- **Tham gia giao dịch hiện có (participating transaction):** phần xử lý bên trong dùng chung transaction vật lý với phần gọi bên ngoài. Trong Spring, đây là hành vi mặc định của PROPAGATION_REQUIRED.
- **Giao dịch độc lập (independent transaction):** phần xử lý bên trong tạm tách khỏi transaction bên ngoài và mở transaction vật lý mới. Trong Spring, PROPAGATION_REQUIRES_NEW thường biểu diễn cách này.
- **SAVEPOINT hoặc giao dịch lồng theo savepoint:** phần xử lý bên trong tạo một mốc trong transaction hiện tại. Nếu phần đó thất bại, có thể rollback về mốc và giữ lại công việc trước mốc. Trong Spring, PROPAGATION_NESTED thường dùng cơ chế này khi transaction manager hỗ trợ.

Ba cách này khác nhau về thời điểm commit, phạm vi rollback, khả năng nhìn thấy dữ liệu và tài nguyên database cần giữ. Chọn sai có thể khiến dữ liệu phụ được commit dù nghiệp vụ chính thất bại, hoặc khiến một lỗi nhỏ làm rollback toàn bộ công việc.

## 1. Transaction vật lý và phạm vi logic trong ứng dụng

Một transaction database vật lý thường bắt đầu khi connection chuyển sang chế độ quản lý transaction, thực hiện các câu SQL rồi kết thúc bằng COMMIT hoặc ROLLBACK. Database dùng transaction đó để bảo đảm tính nguyên tử và nhất quán cho các thay đổi thuộc phạm vi của nó.

Ở tầng ứng dụng, một thao tác nghiệp vụ có thể đi qua nhiều phương thức:

~~~text
OrderService.placeOrder()
    |
    +--> InventoryService.reserve()
    |
    +--> PaymentRecordService.createAttempt()
    |
    +--> AuditService.record()
~~~

Mỗi phương thức có thể khai báo ranh giới transaction riêng. Nhưng việc có nhiều annotation hoặc nhiều lời gọi service không có nghĩa database tự tạo nhiều transaction độc lập. Hành vi thực tế phụ thuộc propagation (quy tắc truyền transaction) của framework và transaction manager.

Cần phân biệt:

- **Logical transaction scope:** phạm vi phương thức hoặc đơn vị công việc mà ứng dụng xem như một transaction.
- **Physical transaction:** transaction thực sự được database quản lý trên connection.
- **Savepoint:** một mốc rollback nằm bên trong physical transaction hiện có.

Nhiều logical scope có thể cùng tham gia một physical transaction. Ngược lại, một phương thức được gọi từ bên trong transaction có thể tạm mở một physical transaction mới nếu propagation yêu cầu.

## 2. Tham gia transaction hiện có: REQUIRED

Trong Spring, PROPAGATION_REQUIRED là propagation mặc định của @Transactional. Nếu chưa có transaction, framework tạo một transaction mới. Nếu đã có transaction trên luồng thực thi hiện tại, phương thức được gọi tham gia vào transaction đó.

~~~text
Caller
  BEGIN physical transaction T1
      |
      +--> Service A
      |      UPDATE Order
      |
      +--> Service B (REQUIRED)
             UPDATE Inventory
             cùng transaction T1
      |
  COMMIT hoặc ROLLBACK T1
~~~

Cả hai service dùng cùng physical transaction. Service B không tự COMMIT độc lập khi phương thức của nó kết thúc. Thay đổi trong B chỉ được commit khi transaction T1 ở bên ngoài commit thành công.

### 2.1. Ví dụ Spring

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public OrderService(
            InventoryService inventoryService,
            OrderRepository orderRepository) {
        this.inventoryService = inventoryService;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void placeOrder(Long productId, int quantity) {
        orderRepository.createPendingOrder(productId, quantity);

        inventoryService.reserve(productId, quantity);

        orderRepository.markReady(productId);
    }
}

@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(Long productId, int quantity) {
        // UPDATE inventory trong transaction của OrderService.
    }
}
~~~

Nếu OrderService đã mở transaction, reserve() tham gia transaction đó. Nếu reserve() ném exception khiến transaction bị rollback và exception được truyền ra ngoài, thay đổi tạo đơn hàng cũng rollback cùng.

Đây thường là lựa chọn đúng khi các thao tác cùng tạo thành một đơn vị nghiệp vụ: hoặc tất cả cùng thành công, hoặc tất cả cùng thất bại.

### 2.2. Inner scope có thể đánh dấu transaction rollback-only

Một chi tiết dễ gây nhầm lẫn: phương thức tham gia transaction không có quyền tự commit transaction chung. Nhưng nó có thể khiến transaction chung bị đánh dấu rollback-only khi có lỗi theo quy tắc rollback của framework.

Ví dụ:

~~~java
@Transactional
public void placeOrder() {
    orderRepository.createOrder();

    try {
        inventoryService.reserve();
    } catch (InventoryException ex) {
        // Ứng dụng bắt exception và tiếp tục.
    }

    auditRepository.writeAttempt();
}
~~~

Giả sử reserve() tham gia cùng transaction và một runtime exception làm transaction bị đánh dấu rollback-only. OrderService bắt exception nên Java tiếp tục chạy, nhưng trạng thái transaction đã không còn được phép commit.

Khi phương thức ngoài kết thúc, Spring cố commit nhưng transaction manager phát hiện rollback-only và rollback toàn bộ transaction. Caller có thể nhận UnexpectedRollbackException để biết rằng lời gọi commit đã không thể thành công.

Vì vậy, **bắt exception trong Java không tự xóa trạng thái rollback-only**. Nếu một phần công việc được phép thất bại mà phần còn lại vẫn commit, cần chọn ranh giới transaction phù hợp hoặc savepoint thay vì chỉ bắt exception.

### 2.3. Cấu hình transaction bên trong thường không ghi đè transaction bên ngoài

Khi một phương thức REQUIRED tham gia transaction hiện có, nó thường kế thừa transaction vật lý của caller. Những thuộc tính như isolation, timeout hoặc readOnly được khai báo ở phương thức bên trong có thể không được áp dụng như một transaction mới.

Ví dụ, nếu caller mở transaction READ COMMITTED, phương thức bên trong khai báo SERIALIZABLE nhưng dùng REQUIRED thì không có nghĩa database tự nâng transaction đang chạy lên SERIALIZABLE. Muốn phát hiện cấu hình không tương thích, Spring có tùy chọn validateExistingTransaction trên transaction manager.

Nên đặt isolation level và timeout ở ranh giới bắt đầu physical transaction, thường là service điều phối cấp cao nhất.

## 3. Giao dịch độc lập: REQUIRES_NEW

PROPAGATION_REQUIRES_NEW luôn yêu cầu một physical transaction riêng. Nếu đang có transaction bên ngoài, Spring tạm suspend transaction đó, mở transaction mới cho phương thức bên trong, rồi khôi phục transaction bên ngoài sau khi transaction mới kết thúc.

~~~text
Caller
  BEGIN T1
  UPDATE Order
      |
      +--> Service B (REQUIRES_NEW)
      |       Suspend T1
      |       BEGIN T2
      |       INSERT AuditRecord
      |       COMMIT hoặc ROLLBACK T2
      |       Resume T1
      |
  COMMIT hoặc ROLLBACK T1
~~~

T1 và T2 có kết quả commit độc lập. Nếu T2 commit thành công, sau đó T1 rollback thì dữ liệu do T2 ghi vẫn tồn tại. Đây là điểm khác biệt lớn nhất so với REQUIRED và SAVEPOINT.

### 3.1. Ví dụ: ghi nhận lần thử xử lý độc lập

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId, String action) {
        // INSERT audit record và commit trong transaction riêng.
    }
}

@Service
public class OrderService {

    private final AuditService auditService;

    public OrderService(AuditService auditService) {
        this.auditService = auditService;
    }

    @Transactional
    public void approve(Long orderId) {
        auditService.recordAttempt(orderId, "APPROVE");

        // Kiểm tra và cập nhật đơn hàng.
        // Nếu bước này thất bại, transaction Order có thể rollback.
    }
}
~~~

Nếu recordAttempt() đã commit T2, sau đó approve() rollback T1, bản ghi audit vẫn còn. Điều này có thể phù hợp nếu ý nghĩa audit là "đã có một lần thử phê duyệt", kể cả khi nghiệp vụ phê duyệt không thành công.

Nhưng nếu audit record mang ý nghĩa "đơn hàng đã được phê duyệt thành công", ghi nó trong REQUIRES_NEW trước khi T1 commit sẽ tạo dữ liệu sai: audit báo thành công trong khi đơn hàng cuối cùng rollback.

Hãy xác định ý nghĩa sự kiện trước khi chọn transaction độc lập. Dữ liệu ghi trong T2 có thể tồn tại dù nghiệp vụ chính trong T1 thất bại.

### 3.2. Transaction độc lập không nhìn thấy dữ liệu chưa commit của transaction ngoài

T2 là một physical transaction khác. Nó không thể mặc định đọc các thay đổi chưa commit mà T1 đang giữ.

Ví dụ:

1. T1 cập nhật Order.Status thành APPROVING nhưng chưa commit.
2. T1 gọi service REQUIRES_NEW.
3. T2 đọc Order.
4. T2 thường chỉ thấy trạng thái đã commit trước đó, chẳng hạn PENDING, chứ không thấy APPROVING.

Nếu T2 cố cập nhật cùng dòng mà T1 đang khóa, T2 có thể bị block chờ T1. Nhưng T1 đang suspend và chờ T2 kết thúc, nên hai phía có thể tạo ra tình huống tự chờ đến timeout.

Đây là lỗi thiết kế thường gặp: outer transaction giữ khóa trên dòng mà inner REQUIRES_NEW cần truy cập. Vì outer chưa thể tiếp tục để commit hoặc rollback, inner transaction không thể lấy khóa.

### 3.3. REQUIRES_NEW cần thêm connection

Trong môi trường JDBC/Spring thông thường, transaction bên ngoài đang giữ connection của nó. Khi mở REQUIRES_NEW, transaction manager thường cần một connection khác cho physical transaction mới.

Nếu nhiều request đồng thời đều giữ transaction ngoài rồi gọi REQUIRES_NEW:

~~~text
Connection pool có 10 connection

10 request:
  mỗi request giữ 1 connection cho T1
  mỗi request gọi REQUIRES_NEW và cần connection thứ hai

Pool không còn connection trống.
Các request chờ connection mới.
Các T1 vẫn giữ connection và chờ T2 hoàn tất.
~~~

Có thể xảy ra connection pool starvation hoặc deadlock ở tầng pool. Cần tính pool size theo concurrency và số transaction lồng độc lập, đồng thời tránh giữ outer transaction lâu. Tăng pool size không thay thế việc xem lại thiết kế vì tải có thể tăng và database vẫn có giới hạn tài nguyên.

### 3.4. Khi nào nên dùng REQUIRES_NEW?

Có thể cân nhắc khi phần công việc thật sự cần tồn tại độc lập với kết quả transaction ngoài, ví dụ:

- Ghi nhận lần thử hoặc sự kiện thất bại mà nghiệp vụ yêu cầu lưu dù transaction chính rollback.
- Lưu một checkpoint độc lập cho một quy trình có thiết kế phục hồi rõ ràng.
- Ghi một bản ghi kỹ thuật không phụ thuộc vào dữ liệu chưa commit của transaction ngoài.

Không nên dùng chỉ để "tránh rollback" cho một bước quan trọng của cùng nghiệp vụ. Nếu bước đó phải thành công hoặc thất bại cùng đơn hàng, nó nên tham gia transaction chính.

Với sự kiện cần phát ra sau khi transaction chính commit, Transactional Outbox thường phù hợp hơn: ghi event trong cùng transaction với dữ liệu nghiệp vụ, sau đó publisher gửi event khi đã commit. REQUIRES_NEW không tự bảo đảm sự kiện phản ánh trạng thái đã commit của T1.

## 4. SAVEPOINT: rollback một phần trong cùng transaction

SAVEPOINT tạo một mốc bên trong transaction đang mở. Nếu một phần công việc thất bại, ứng dụng có thể rollback về mốc đó, loại bỏ thay đổi sau mốc nhưng giữ thay đổi trước mốc.

~~~text
Physical transaction T1
BEGIN
  UPDATE Order
  SAVEPOINT S1
      |
      +--> INSERT OptionalDetail
      +--> UPDATE OptionalCounter
      |
      +--> Có lỗi
           ROLLBACK TO S1
           Bỏ các thay đổi sau S1
  Tiếp tục các thao tác khác
COMMIT T1
~~~

SAVEPOINT không tạo physical transaction mới và không commit độc lập. Toàn bộ công việc còn lại vẫn thuộc transaction T1.

Nếu T1 cuối cùng rollback, cả thay đổi trước và sau savepoint đều bị hủy. Nếu T1 commit, những thay đổi còn lại sau khi xử lý savepoint được commit cùng nhau.

### 4.1. Ví dụ SQL

Cú pháp PostgreSQL:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

SAVEPOINT optional_step;

INSERT INTO order_optional_detail(order_id, note)
VALUES (1001, 'Special handling');

-- Nếu phần tùy chọn thất bại:
ROLLBACK TO SAVEPOINT optional_step;

-- Transaction vẫn hoạt động; có thể tiếp tục.
UPDATE orders
SET processed_at = CURRENT_TIMESTAMP
WHERE order_id = 1001;

RELEASE SAVEPOINT optional_step;

COMMIT;
~~~

ROLLBACK TO SAVEPOINT chỉ hoàn tác các thay đổi sau mốc. Transaction vẫn mở và caller có thể tiếp tục nếu lỗi được xử lý phù hợp.

RELEASE SAVEPOINT xóa tên mốc khi không cần rollback về đó nữa. Việc release không commit transaction. COMMIT cuối cùng mới kết thúc transaction vật lý.

Nếu có nhiều savepoint, chúng tạo thành các mốc theo thứ tự. Rollback về một savepoint sẽ bỏ các thao tác sau mốc đó; các savepoint được tạo sau mốc cũng không còn dùng được.

### 4.2. Ví dụ JDBC

JDBC cung cấp API Savepoint trên Connection:

~~~java
Connection connection = dataSource.getConnection();

try {
    connection.setAutoCommit(false);

    updateOrder(connection, orderId);

    Savepoint savepoint =
        connection.setSavepoint("before_optional_step");

    try {
        insertOptionalDetail(connection, orderId);
        updateOptionalCounter(connection, orderId);

        connection.releaseSavepoint(savepoint);
    } catch (SQLException optionalFailure) {
        connection.rollback(savepoint);

        // Xử lý phần tùy chọn thất bại.
        // Transaction bên ngoài vẫn mở.
    }

    updateOrderCompletion(connection, orderId);
    connection.commit();

} catch (Exception failure) {
    connection.rollback();
    throw failure;
} finally {
    connection.close();
}
~~~

Ví dụ giả định driver và database hỗ trợ savepoint. Trong ứng dụng Spring, không nên tự lấy một connection khác từ DataSource để tạo savepoint nếu muốn nó thuộc transaction đang quản lý. Hãy dùng transaction manager hoặc connection đã được bind vào transaction hiện tại, nếu không savepoint có thể nằm trên một connection/transaction khác.

Khi dùng Spring JDBC, JdbcTemplate và transaction manager phù hợp thường giúp lấy đúng connection đang tham gia transaction.

### 4.3. SAVEPOINT không phải transaction độc lập

| Thuộc tính | SAVEPOINT | REQUIRES_NEW |
|---|---|---|
| Physical transaction | Dùng transaction hiện có | Tạo transaction mới |
| Connection | Thường dùng cùng connection | Thường cần connection riêng |
| Rollback phần bên trong | Có thể rollback về savepoint | Rollback transaction bên trong |
| Commit phần bên trong | Không thể commit riêng | Có thể commit độc lập |
| Outer rollback | Hủy cả thay đổi trước và sau savepoint còn trong T1 | Không hủy thay đổi đã commit trong T2 |
| Khóa và tài nguyên | Thuộc cùng transaction | Transaction riêng, outer có thể vẫn giữ khóa |
| Mục đích | Cho phép một bước tùy chọn thất bại mà transaction chung tiếp tục | Ghi công việc có vòng đời commit độc lập |

Nếu cần dữ liệu tồn tại sau khi transaction ngoài rollback, SAVEPOINT không đáp ứng yêu cầu đó. Nếu chỉ muốn bỏ một phần thao tác rồi tiếp tục transaction chung, REQUIRES_NEW có thể tạo semantics quá độc lập và thêm chi phí không cần thiết.

## 5. Spring propagation: đối chiếu các lựa chọn

Spring cung cấp nhiều propagation mode. Ba mode thường cần phân biệt nhất là REQUIRED, REQUIRES_NEW và NESTED.

| Propagation | Có transaction hiện tại | Chưa có transaction hiện tại |
|---|---|---|
| REQUIRED | Tham gia transaction hiện có | Tạo transaction mới |
| REQUIRES_NEW | Suspend transaction hiện có, tạo transaction mới | Tạo transaction mới |
| NESTED | Tạo savepoint trong transaction hiện có nếu được hỗ trợ | Tạo transaction mới |
| SUPPORTS | Tham gia nếu có; nếu không thì chạy không transaction | Chạy không transaction |
| MANDATORY | Bắt buộc phải có transaction, nếu không báo lỗi | Báo lỗi |
| NOT_SUPPORTED | Suspend transaction hiện có và chạy không transaction | Chạy không transaction |
| NEVER | Báo lỗi nếu đang có transaction | Chạy không transaction |

NESTED không phải lúc nào cũng khả dụng. Nó phụ thuộc transaction manager và khả năng savepoint của resource. Nếu không có transaction hiện tại, NESTED thường hoạt động như REQUIRED và mở transaction mới.

### 5.1. REQUIRED: cùng commit, cùng rollback

Dùng khi các service là các bước của cùng một nghiệp vụ và phải có kết quả nguyên tử. Cần lưu ý lỗi ở inner scope có thể đánh dấu rollback-only cho transaction chung.

### 5.2. REQUIRES_NEW: commit độc lập

Dùng khi dữ liệu bên trong có ý nghĩa riêng và cần tồn tại dù transaction ngoài rollback. Phải cân nhắc connection pool, khóa outer đang giữ và việc transaction trong không thấy dữ liệu chưa commit của outer.

### 5.3. NESTED: rollback một phần

Dùng khi transaction ngoài vẫn phải tiếp tục nếu một bước con thất bại, và database/transaction manager hỗ trợ savepoint. Không dùng nếu bước con phải commit độc lập.

## 6. Spring NESTED và giới hạn của transaction manager

PROPAGATION_NESTED thường được triển khai bằng JDBC savepoint trong cùng physical transaction. Hành vi cụ thể phụ thuộc transaction manager:

- DataSourceTransactionManager hỗ trợ nested transaction dựa trên JDBC savepoint khi driver/database hỗ trợ.
- JpaTransactionManager không hỗ trợ nested transaction theo mặc định. Nếu bật savepoint, savepoint chỉ kiểm soát trạng thái JDBC connection; persistence context của JPA/Hibernate không nhất thiết được khôi phục tương ứng. Vì vậy, không nên giả định rollback savepoint sẽ hoàn nguyên mọi entity đang được quản lý trong EntityManager.
- JTA transaction manager thường không cung cấp nested transaction theo nghĩa savepoint thông qua propagation NESTED. Cần kiểm tra implementation cụ thể.

Ví dụ khai báo:

~~~java
@Service
public class OptionalDetailService {

    @Transactional(propagation = Propagation.NESTED)
    public void addOptionalDetail(Long orderId) {
        // Các câu SQL trong savepoint scope.
    }
}
~~~

Nếu được gọi khi OrderService đang có transaction, Spring tạo savepoint trước phần xử lý nested. Nếu nested method thất bại và exception được xử lý ở caller, transaction ngoài có thể tiếp tục sau khi phần nested được rollback về savepoint.

Nếu exception tiếp tục truyền ra khỏi phương thức ngoài và làm outer transaction rollback, toàn bộ transaction vẫn thất bại như bình thường. Savepoint không buộc outer transaction phải commit.

### 6.1. NESTED và JPA persistence context

JPA/Hibernate duy trì trạng thái entity trong persistence context. Một JDBC savepoint chỉ là mốc trên database connection. Khi rollback về savepoint, trạng thái object trong bộ nhớ có thể vẫn chứa thay đổi đã bị database hoàn tác.

Ví dụ:

1. Entity Order được load vào EntityManager.
2. Nested scope thay đổi entity và flush SQL.
3. Nested scope rollback về savepoint.
4. Database trở về trạng thái trước savepoint.
5. Entity object trong persistence context có thể vẫn mang giá trị đã sửa.

Nếu tiếp tục dùng entity đó, lần flush sau có thể ghi lại thay đổi hoặc tạo trạng thái không đồng bộ giữa bộ nhớ và database.

Với JPA, hãy thận trọng khi dùng NESTED. Có thể cần clear/refresh persistence context hoặc tổ chức phần savepoint bằng JDBC thuần trong một ranh giới được kiểm soát. Không nên coi NESTED là rollback một phần đầy đủ của toàn bộ trạng thái ứng dụng.

## 7. Exception, rollback rules và cách xử lý lỗi

Propagation quyết định transaction được chia sẻ hay tách riêng. Rollback rules quyết định lỗi nào khiến transaction bị rollback. Hai vấn đề này liên quan nhưng không giống nhau.

Trong Spring, mặc định @Transactional thường rollback với RuntimeException và Error; checked exception không tự động làm rollback nếu không cấu hình rollbackFor phù hợp.

Ví dụ:

~~~java
@Transactional(rollbackFor = PaymentException.class)
public void processOrder() throws PaymentException {
    // ...
}
~~~

Nếu một exception bị bắt và không truyền qua transaction interceptor, framework có thể không thấy exception để áp dụng rollback rule. Nhưng transaction vẫn có thể đã bị đánh dấu rollback-only bởi một scope tham gia khác.

Một số nguyên tắc:

- Đừng bắt exception rồi giả định transaction chắc chắn còn commit được.
- Kiểm tra xem exception đến từ REQUIRED, REQUIRES_NEW hay NESTED scope.
- Với REQUIRED, lỗi ở inner scope có thể làm transaction chung rollback-only.
- Với REQUIRES_NEW, inner transaction có thể rollback riêng; outer transaction có thể tiếp tục nếu caller xử lý lỗi.
- Với NESTED, rollback về savepoint có thể cho phép outer tiếp tục, nhưng chỉ khi exception được xử lý và trạng thái transaction ngoài còn hợp lệ.
- Nếu database đã đánh dấu transaction không thể commit, savepoint không tự phục hồi nó.

Trong JDBC, sau một số lỗi SQL, trạng thái transaction phụ thuộc DBMS. PostgreSQL chẳng hạn đánh dấu transaction hiện tại là aborted sau lỗi SQL cho đến khi rollback hoặc rollback về savepoint hợp lệ. Vì vậy, nếu muốn tiếp tục sau lỗi ở bước con, cần đặt savepoint trước bước có thể lỗi và rollback về savepoint theo đúng quy tắc.

## 8. Các tình huống dễ chọn sai propagation

### 8.1. Ghi audit trong REQUIRES_NEW nhưng audit lại tuyên bố nghiệp vụ thành công

Nếu audit được commit trước khi outer transaction commit, audit có thể tồn tại trong khi thay đổi chính rollback. Hãy phân biệt "đã thử" với "đã hoàn tất". Nếu event chỉ được phát sau khi nghiệp vụ commit, ghi outbox trong transaction chính rồi publish sau commit.

### 8.2. Dùng REQUIRES_NEW để né rollback-only

Một inner service dùng REQUIRES_NEW có thể commit độc lập, nhưng điều đó không có nghĩa toàn bộ nghiệp vụ đã an toàn. Nếu inner ghi trạng thái phụ thuộc vào dữ liệu outer chưa commit, nó có thể đọc trạng thái cũ hoặc chờ khóa do outer giữ.

### 8.3. Dùng NESTED nhưng mong inner commit tồn tại sau outer rollback

Savepoint không tạo commit độc lập. Khi outer rollback, mọi thay đổi trong cùng physical transaction đều rollback, kể cả phần inner đã qua savepoint.

### 8.4. Dùng REQUIRED nhưng mong lỗi inner không ảnh hưởng outer

Nếu inner scope tham gia transaction chung và đánh dấu rollback-only, việc bắt exception ở outer không làm transaction trở lại trạng thái commit được. Nếu bước con thực sự tùy chọn, cân nhắc NESTED với savepoint hoặc tách nghiệp vụ theo trạng thái phù hợp.

### 8.5. Gọi phương thức transactional nội bộ cùng object

Trong cấu hình Spring proxy mặc định, lời gọi từ một phương thức đến phương thức khác trong cùng instance (self-invocation) không đi qua proxy. Vì vậy, annotation @Transactional ở phương thức được gọi nội bộ có thể không được áp dụng; propagation REQUIRES_NEW hoặc NESTED có thể không xảy ra như mong đợi.

Ví dụ:

~~~java
@Service
public class OrderService {

    public void process() {
        this.writeAudit(); // Self-invocation
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit() {
        // Annotation có thể không được kích hoạt qua proxy.
    }
}
~~~

Có thể chuyển phần xử lý transactional sang một Spring bean khác và gọi qua proxy, hoặc dùng cách tổ chức transaction programmatic phù hợp. Không dựa vào annotation nếu lời gọi không đi qua cơ chế quản lý transaction.

## 9. Transaction gắn với thread và ranh giới bất đồng bộ

Trong mô hình Spring imperative thông thường, transaction context được bind với thread hiện tại. Một tác vụ chạy qua @Async, executor hoặc thread mới không tự động tham gia transaction của thread gọi nó.

~~~text
Thread A
  BEGIN T1
  gọi async task
  COMMIT T1

Thread B
  chạy async task
  không tự động tham gia T1
~~~

Nếu async task cần transaction, nó phải mở transaction riêng ở thread thực thi hoặc dùng một cơ chế phối hợp khác. Không thể giả định transaction ngoài sẽ đợi task hoàn tất hoặc rollback cùng task chỉ vì lời gọi được tạo trong một phương thức @Transactional.

Với Spring reactive, transaction context được truyền qua Reactor Context thay vì dựa trên ThreadLocal theo cách imperative. Không nên áp dụng nguyên xi các giả định về thread-bound transaction cho reactive pipeline; hãy dùng reactive transaction manager và API tương ứng.

## 10. Chọn cơ chế theo mục đích nghiệp vụ

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Tạo Order và trừ Inventory phải cùng thành công | REQUIRED | Cùng physical transaction, rollback đồng thời |
| Một bước tùy chọn có thể thất bại nhưng phần trước vẫn tiếp tục | NESTED/SAVEPOINT nếu resource hỗ trợ | Rollback phần sau savepoint, outer có thể tiếp tục |
| Ghi nhận lần thử dù nghiệp vụ chính rollback | REQUIRES_NEW | Bản ghi phụ có thể commit độc lập |
| Ghi event chỉ được phát khi nghiệp vụ chính commit | REQUIRED + Outbox | Event và thay đổi nghiệp vụ cùng commit |
| Inner cần đọc thay đổi chưa commit của outer | REQUIRED | Cùng transaction nhìn thấy thay đổi của chính transaction |
| Inner phải commit riêng nhưng cần dữ liệu outer vừa sửa | Xem lại thiết kế | REQUIRES_NEW không thấy dữ liệu chưa commit và có thể block trên khóa outer |
| Một thao tác có thể chạy không transaction khi caller không có transaction | SUPPORTS | Tham gia nếu có, nếu không thì chạy không transaction |
| Bắt buộc caller phải cung cấp transaction | MANDATORY | Phát hiện sớm khi ranh giới gọi sai |
| Tạm chạy ngoài transaction đang có | NOT_SUPPORTED | Suspend transaction hiện tại trong phạm vi phương thức |

Quyết định nên dựa trên câu hỏi: nếu bước con thành công rồi bước ngoài thất bại, dữ liệu bước con có được phép tồn tại không? Nếu câu trả lời là không, thường cần cùng transaction hoặc savepoint. Nếu có, REQUIRES_NEW có thể phù hợp, nhưng phải bảo đảm bước con không dựa vào thay đổi chưa commit của outer.

## 11. Ví dụ tổng hợp: xử lý đơn hàng với bước tùy chọn

Giả sử quy trình tạo đơn hàng có ba phần:

1. Tạo Order và giữ Inventory: bắt buộc cùng thành công.
2. Ghi chi tiết đóng gói đặc biệt: tùy chọn, có thể bỏ qua nếu không hợp lệ.
3. Ghi nhận lần thử gửi thông báo: cần lưu riêng để phục vụ vận hành.

Có thể thiết kế:

~~~text
OrderService (REQUIRED, T1)
  |
  +--> INSERT Order
  |
  +--> InventoryService (REQUIRED, T1)
  |      UPDATE Inventory
  |
  +--> PackagingService (NESTED, savepoint S1)
  |      INSERT PackagingDetail
  |      Nếu lỗi: rollback về S1
  |      Outer tiếp tục nếu nghiệp vụ cho phép
  |
  +--> NotificationAttemptService (REQUIRES_NEW, T2)
         INSERT NotificationAttempt
         COMMIT T2

OrderService COMMIT hoặc ROLLBACK T1
~~~

Cần kiểm tra ý nghĩa của NotificationAttempt. Nếu nó ghi "đã thử gửi", việc tồn tại dù Order rollback có thể hợp lệ. Nếu nó ghi "đơn hàng đã được gửi thành công", nên ghi nhận sự kiện sau commit hoặc dùng Outbox để tránh trạng thái sai.

Nếu PackagingService dùng JPA và transaction manager không hỗ trợ nested savepoint đúng cách, hãy thiết kế lại phần tùy chọn: lưu trạng thái cần xử lý sau, dùng constraint hoặc một transaction nghiệp vụ riêng có semantics rõ. Không giả định NESTED luôn có thể rollback một phần mọi loại trạng thái trong persistence context.

## 12. Các nguyên tắc cần ghi nhớ

- Nhiều phương thức @Transactional có thể cùng tham gia một physical transaction; annotation không tự tạo transaction mới.
- REQUIRED tham gia transaction hiện có hoặc tạo mới nếu chưa có; các thay đổi commit/rollback cùng transaction vật lý.
- Một inner REQUIRED scope có thể đánh dấu transaction chung rollback-only; bắt exception không tự xóa trạng thái này.
- REQUIRES_NEW suspend transaction ngoài và mở transaction vật lý riêng; inner có thể commit dù outer rollback.
- REQUIRES_NEW thường cần connection riêng và có thể bị block bởi khóa mà outer đang giữ.
- SAVEPOINT tạo mốc rollback trong cùng transaction; nó không commit độc lập.
- NESTED thường dùng savepoint nếu transaction manager và resource hỗ trợ; nếu chưa có transaction, nó thường mở transaction mới.
- Rollback outer sẽ hủy mọi thay đổi còn trong cùng physical transaction, kể cả phần trước hoặc sau savepoint.
- JpaTransactionManager không hỗ trợ nested transaction theo mặc định; savepoint trên JDBC connection cũng không tự khôi phục persistence context.
- Rollback rules phụ thuộc loại exception và cấu hình; phải hiểu transaction đang ở trạng thái nào sau lỗi.
- Self-invocation trong Spring proxy mode có thể khiến @Transactional và propagation ở phương thức nội bộ không được áp dụng.
- Transaction imperative thông thường gắn với thread; tác vụ async không tự động tham gia transaction của thread gọi.
- Dùng REQUIRED cho một đơn vị nghiệp vụ nguyên tử, NESTED cho rollback một phần có kiểm soát và REQUIRES_NEW chỉ khi phần việc cần vòng đời commit độc lập.

Tham gia giao dịch, mở giao dịch độc lập và tạo SAVEPOINT đều giúp chia công việc ở tầng ứng dụng, nhưng chúng tạo ra ba phạm vi rollback khác nhau. Hãy xác định dữ liệu nào phải sống cùng nhau, dữ liệu nào được phép tồn tại độc lập và phần nào có thể bỏ qua trước khi chọn propagation. Khi ranh giới đó khớp với ý nghĩa nghiệp vụ, hành vi commit và rollback sẽ dễ dự đoán hơn.


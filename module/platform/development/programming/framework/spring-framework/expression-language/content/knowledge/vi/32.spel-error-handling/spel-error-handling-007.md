# Giữ nguyên nguyên nhân khi bọc lỗi ở tầng Spring

Trong ứng dụng Spring, một lỗi thường đi qua nhiều tầng trước khi đến nơi xử lý cuối cùng. Ví dụ, driver JDBC có thể ném SQLException, tầng repository chuyển lỗi thành DataAccessException, rồi tầng service bổ sung ngữ cảnh nghiệp vụ trước khi trả lỗi cho controller.

Khi một tầng bắt exception và tạo exception mới, cần giữ exception ban đầu làm **cause**. Cause lưu lại nguyên nhân kỹ thuật và stack trace gốc, giúp xác định lỗi bắt đầu ở đâu. Nếu chỉ tạo exception mới với một thông báo mà không truyền cause, chuỗi nguyên nhân bị đứt và thông tin quan trọng có thể mất.

Nguyên tắc cốt lõi là: khi cần dịch loại exception hoặc bổ sung ngữ cảnh ở ranh giới một tầng, hãy tạo exception mới với cause là exception đã bắt được. Nếu không cần thay đổi loại lỗi hoặc bổ sung thông tin, có thể ném lại chính exception ban đầu.

## 1. Exception wrapping và cause trong Java

Java hỗ trợ exception chaining thông qua thuộc tính cause của Throwable. Một exception mới có thể giữ exception cũ làm nguyên nhân:

~~~java
try {
    repository.save(order);
} catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order " + order.getId(),
        ex
    );
}
~~~

Constructor của exception tùy chỉnh:

~~~java
public class OrderPersistenceException extends RuntimeException {

    public OrderPersistenceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Ở đây:

- OrderPersistenceException là lỗi ở tầng persistence mà tầng gọi hiểu được.
- SQLException là nguyên nhân kỹ thuật ban đầu.
- Thông báo mới bổ sung mã đơn hàng để việc chẩn đoán có ngữ cảnh.
- Stack trace của cause vẫn có thể được truy xuất và hiển thị.

Throwable cung cấp các constructor nhận cả message và cause. Đây là cách nên dùng khi tạo exception wrapper.

## 2. Vì sao cần giữ nguyên cause?

Một exception thường chứa nhiều thông tin hơn message:

- Loại lỗi ban đầu, ví dụ SQLException, IOException hoặc lỗi từ thư viện persistence.
- Stack trace tại nơi lỗi thực sự phát sinh.
- Cause tiếp theo nếu lỗi đã được bọc qua nhiều tầng.
- Mã lỗi, SQLState, vendor code hoặc dữ liệu chẩn đoán riêng của exception gốc.
- Thông tin bổ sung trong các subclass của framework hoặc thư viện.

Nếu chỉ giữ message, tầng trên có thể biết thao tác thất bại nhưng không biết nguyên nhân cụ thể. Điều này làm việc phân biệt lỗi dữ liệu, lỗi kết nối, lỗi cấu hình và lỗi lập trình khó hơn.

Ví dụ không nên dùng:

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order: " + ex.getMessage()
    );
}
~~~

Cách này tạo exception mới nhưng không liên kết nó với SQLException. Stack trace mới chỉ cho thấy nơi wrapper được tạo; thông tin exception gốc không còn nằm trong cause chain.

Cách giữ nguyên nguyên nhân:

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot persist order " + orderId,
        ex
    );
}
~~~

Thông báo cung cấp ngữ cảnh nghiệp vụ, còn cause giữ lại nguyên nhân kỹ thuật.

## 3. Cause chain hoạt động như thế nào?

Một lỗi có thể được bọc qua nhiều tầng:

~~~text
Database driver
    |
    v
SQLException
    |
    v
DataAccessException
    |
    v
OrderPersistenceException
    |
    v
OrderServiceException
    |
    v
Exception handler
~~~

Mỗi wrapper giữ exception ở tầng dưới làm cause. Khi xem stack trace hoặc gọi getCause(), có thể lần theo chuỗi từ lỗi cấp cao đến lỗi ban đầu.

Ví dụ:

~~~java
try {
    jdbcOperation();
} catch (SQLException ex) {
    DataAccessException dataAccess =
        new DataAccessResourceFailureException(
            "Database operation failed",
            ex
        );

    throw new OrderPersistenceException(
        "Unable to save order",
        dataAccess
    );
}
~~~

Chuỗi cause có dạng:

~~~text
OrderPersistenceException
  cause -> DataAccessResourceFailureException
              cause -> SQLException
~~~

Trong thực tế, không nhất thiết phải bọc exception ở mọi tầng. Chỉ nên tạo wrapper khi tầng đó cần chuyển đổi abstraction hoặc thêm ngữ cảnh có giá trị.

## 4. Dùng constructor nhận cause thay vì chỉ nhận message

Khi tạo exception tùy chỉnh, nên cung cấp constructor nhận cả message và cause:

~~~java
public class OrderServiceException extends RuntimeException {

    public OrderServiceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Nếu cần hỗ trợ trường hợp không có cause, có thể bổ sung constructor khác:

~~~java
public OrderServiceException(String message) {
    super(message);
}
~~~

Sau đó, ở nơi bắt lỗi:

~~~java
try {
    orderRepository.save(order);
} catch (DataAccessException ex) {
    throw new OrderServiceException(
        "Could not save order " + order.getId(),
        ex
    );
}
~~~

Không nên bỏ qua cause chỉ vì exception mới đã có message dễ đọc. Message và cause phục vụ hai mục đích khác nhau: message giải thích ngữ cảnh của tầng hiện tại; cause giải thích nguyên nhân của lỗi trước đó.

## 5. Khi nào nên ném lại exception ban đầu?

Không phải mọi catch đều cần tạo wrapper. Nếu tầng hiện tại không có thông tin mới, không cần đổi loại exception và không cần thực hiện xử lý phục hồi, có thể ném lại chính exception:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    if (shouldRetry(ex)) {
        retryLater();
    } else {
        throw ex;
    }
}
~~~

Ném lại cùng đối tượng exception giữ nguyên loại, cause chain và stack trace ban đầu.

Một số nguyên tắc:

- **Ném lại exception ban đầu:** khi không cần chuyển abstraction hoặc bổ sung ngữ cảnh.
- **Bọc với cause:** khi tầng hiện tại cần cung cấp loại exception phù hợp hơn hoặc bổ sung thông tin hữu ích.
- **Xử lý và không ném tiếp:** chỉ khi lỗi đã được xử lý đầy đủ theo hợp đồng của ứng dụng.
- **Không nuốt lỗi:** tránh catch rồi bỏ qua hoặc trả về giá trị mặc định khiến lỗi bị che giấu.

Nếu chỉ muốn ghi log và tiếp tục ném lại, hãy dùng \`throw ex\` trong cùng catch. Tránh tạo wrapper không cần thiết chỉ để thêm một dòng log.

## 6. Dùng initCause khi không có constructor phù hợp

Throwable cung cấp phương thức \`initCause(Throwable cause)\` để thiết lập cause sau khi tạo exception.

~~~java
SQLException original = obtainSQLException();

OrderPersistenceException wrapped =
    new OrderPersistenceException("Cannot save order");

wrapped.initCause(original);

throw wrapped;
~~~

Cách này hữu ích với một số lớp exception cũ không có constructor nhận cause. Tuy nhiên, nếu có thể thiết kế exception tùy chỉnh, nên ưu tiên constructor:

~~~java
new OrderPersistenceException("Cannot save order", original)
~~~

Cause chỉ có thể được thiết lập theo quy tắc của Throwable; gọi initCause khi cause đã được khởi tạo hoặc đã thiết lập có thể gây IllegalStateException. Không nên gọi initCause theo thói quen nếu constructor đã nhận cause.

## 7. Spring có sẵn các exception hỗ trợ cause

Nhiều exception trong Spring được thiết kế để giữ nguyên nguyên nhân thông qua constructor nhận Throwable.

Ví dụ, hệ thống Spring DAO dùng DataAccessException làm lớp cơ sở cho các lỗi truy cập dữ liệu. Lớp này thuộc hệ thống exception runtime của Spring và có constructor nhận message cùng cause.

Một số subclass thường gặp:

- DataAccessResourceFailureException: lỗi truy cập tài nguyên dữ liệu.
- DataIntegrityViolationException: vi phạm ràng buộc hoặc tính toàn vẹn dữ liệu.
- DuplicateKeyException: xung đột khóa trùng.
- InvalidDataAccessApiUsageException: cách sử dụng API truy cập dữ liệu không hợp lệ.

Ví dụ tạo exception theo abstraction Spring:

~~~java
throw new DataAccessResourceFailureException(
    "Cannot reach the reporting database",
    sqlException
);
~~~

Nếu đang dùng exception phù hợp của Spring, hãy truyền cause vào constructor thay vì tạo một RuntimeException chung chỉ chứa message.

## 8. Exception translation ở tầng Spring DAO

Một mục tiêu quan trọng của Spring DAO là chuyển exception đặc thù của công nghệ persistence thành hệ thống DataAccessException nhất quán.

Ví dụ, JDBC driver ném SQLException. JdbcTemplate sử dụng cơ chế exception translation để chuyển lỗi này thành một subclass phù hợp của DataAccessException.

~~~java
@Repository
public class JdbcOrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void save(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.getId(),
            order.getStatus()
        );
    }
}
~~~

Khi thao tác JDBC thất bại, JdbcTemplate thực hiện translation theo SQLExceptionTranslator. Exception được ném lên thuộc hệ thống DataAccessException; exception JDBC gốc thường được giữ trong cause chain.

Nhờ vậy, tầng service có thể xử lý theo abstraction Spring mà không phải phụ thuộc trực tiếp vào từng loại exception của JDBC driver.

Không nên tự bắt SQLException rồi tạo DataAccessException chỉ chứa message nếu framework đã có cơ chế translation phù hợp. Dùng JdbcTemplate và các abstraction tương ứng giúp giữ cách phân loại lỗi nhất quán.

## 9. Exception translation với @Repository

Spring hỗ trợ dịch exception từ công nghệ persistence tại bean được đánh dấu @Repository thông qua hạ tầng persistence exception translation khi được cấu hình.

Ví dụ:

~~~java
@Repository
public class JpaOrderRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public void save(Order order) {
        entityManager.persist(order);
    }
}
~~~

Khi PersistenceExceptionTranslationPostProcessor được đăng ký, Spring có thể áp dụng interceptor để dịch một số exception persistence sang DataAccessException.

Việc dịch lỗi phụ thuộc translator được cấu hình và loại exception mà provider ném ra. Một translation tốt giữ exception gốc làm cause để mã phía trên có thể xử lý theo abstraction Spring và vẫn điều tra được nguyên nhân kỹ thuật.

Lưu ý: annotation @Repository tự nó không phải là một câu lệnh catch. Exception translation cần hạ tầng Spring tương ứng được bật và bean phải đi qua cơ chế proxy/interceptor của nó.

## 10. Bọc lỗi khi chuyển từ repository sang service

Repository và service có thể dùng hai abstraction khác nhau.

- Repository biết chi tiết persistence và có thể ném DataAccessException.
- Service hiểu ý nghĩa nghiệp vụ của thao tác và có thể cung cấp OrderServiceException.
- Controller hoặc exception handler quyết định cách ánh xạ lỗi thành phản hồi cho client.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public void placeOrder(Order order) {
        try {
            repository.save(order);
        } catch (DataAccessException ex) {
            throw new OrderServiceException(
                "Could not place order " + order.getId(),
                ex
            );
        }
    }
}
~~~

Tầng service thêm thông tin về hành động nghiệp vụ là place order và mã đơn hàng. Cause vẫn là DataAccessException, trong đó có thể tiếp tục giữ exception của driver hoặc persistence provider.

Nếu service không có abstraction riêng hoặc không thêm ngữ cảnh hữu ích, có thể để DataAccessException truyền lên thay vì bọc thêm một lớp.

## 11. Không làm mất cause khi tạo exception ở tầng cấu hình hoặc bean

Spring cũng dùng exception wrapper để thêm thông tin về bean, resource hoặc cấu hình.

Ví dụ, BeanCreationException có các constructor hỗ trợ thông tin bean và cause:

~~~java
try {
    initializeClient();
} catch (IOException ex) {
    throw new BeanCreationException(
        "paymentClient",
        "Failed to initialize payment client",
        ex
    );
}
~~~

Wrapper cho biết bean nào không khởi tạo được, còn IOException vẫn là cause.

Tương tự, khi tạo exception tùy chỉnh trong BeanFactoryPostProcessor, FactoryBean hoặc thành phần cấu hình, hãy truyền exception gốc nếu đang chuyển lỗi sang abstraction của Spring.

Điều này đặc biệt hữu ích vì một lỗi khởi tạo bean có thể được bọc thêm bởi các lớp container khác trước khi đến log cuối cùng. Cause chain giúp tìm ra lỗi ban đầu thay vì chỉ thấy thông báo bean không tạo được.

## 12. Cause chain và các phương thức của NestedRuntimeException

Spring Core có lớp NestedRuntimeException làm nền cho nhiều exception trong framework. Lớp này cung cấp một số phương thức tiện ích để làm việc với chuỗi cause:

- \`getCause()\`: phương thức chuẩn của Throwable, trả cause trực tiếp.
- \`getRootCause()\`: trả nguyên nhân sâu nhất được tìm thấy trong chuỗi lồng nhau, hoặc null nếu không có cause.
- \`getMostSpecificCause()\`: trả root cause nếu có, nếu không trả chính exception hiện tại.
- \`contains(Class<?> exType)\`: kiểm tra chuỗi exception lồng nhau có chứa loại exception được yêu cầu hay không.

Ví dụ:

~~~java
try {
    service.perform();
} catch (NestedRuntimeException ex) {
    Throwable root = ex.getRootCause();
    Throwable mostSpecific = ex.getMostSpecificCause();

    if (ex.contains(SQLException.class)) {
        // Cause chain có chứa SQLException.
    }
}
~~~

Các phương thức này tiện cho chẩn đoán. Tuy nhiên, khi cần kiểm tra loại lỗi để quyết định nghiệp vụ, hãy cân nhắc bắt hoặc phân loại exception theo abstraction phù hợp thay vì chỉ kiểm tra tên lớp của root cause.

## 13. Không thay cause bằng một exception mới không liên quan

Một lỗi phổ biến là bắt exception rồi tạo một exception khác mà không truyền cause:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new IllegalStateException(
        "Gateway unavailable"
    );
}
~~~

Đoạn mã trên làm mất liên kết đến IOException. Khi log, người vận hành chỉ thấy IllegalStateException được tạo tại tầng hiện tại.

Sửa bằng cách truyền cause:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new IllegalStateException(
        "Gateway unavailable",
        ex
    );
}
~~~

Nếu có exception nghiệp vụ riêng, hãy dùng nó:

~~~java
try {
    gateway.call();
} catch (IOException ex) {
    throw new PaymentGatewayException(
        "Payment gateway call failed",
        ex
    );
}
~~~

Tên exception mới nên thể hiện abstraction hoặc ngữ cảnh của tầng đang xử lý, còn cause giữ lại lỗi kỹ thuật ban đầu.

## 14. Không chỉ nối message của exception gốc

Có thể thêm message của exception gốc vào message mới, nhưng cách đó không thay thế cause.

~~~java
catch (SQLException ex) {
    throw new OrderPersistenceException(
        "Cannot save order: " + ex.getMessage(),
        ex
    );
}
~~~

Ở đây cả hai thông tin đều có ích:

- Message mới giúp người đọc hiểu thao tác nghiệp vụ thất bại.
- Message của cause có thể hiển thị trong stack trace.
- Cause giữ loại exception, stack trace và metadata riêng của nó.

Nếu chỉ nối ex.getMessage() mà không truyền ex, ứng dụng vẫn mất chuỗi nguyên nhân.

Cũng không nên đưa toàn bộ message kỹ thuật ra phản hồi công khai cho người dùng cuối. Message nội bộ và thông tin phản hồi client cần được thiết kế theo mục tiêu riêng.

## 15. Logging exception đúng cách

Khi log một exception, hãy truyền chính đối tượng Throwable cho logger để framework logging có thể ghi stack trace và cause chain.

~~~java
try {
    orderService.placeOrder(order);
} catch (OrderServiceException ex) {
    log.error(
        "Failed to place order id={}",
        order.getId(),
        ex
    );
    throw ex;
}
~~~

Tránh chỉ ghi message:

~~~java
log.error("Failed to place order: {}", ex.getMessage());
~~~

Cách thứ hai thường không in stack trace và cause chain, khiến việc điều tra khó hơn.

Không cần log lại toàn bộ stack trace ở mọi tầng. Nếu repository, service, controller và global handler đều log cùng một exception, hệ thống có thể tạo nhiều bản ghi trùng lặp. Hãy chọn một ranh giới xử lý phù hợp để ghi log đầy đủ; những tầng khác có thể bổ sung context bằng wrapper hoặc truyền exception tiếp.

## 16. Giữ cause nhưng không tiết lộ chi tiết nội bộ cho client

Preserve cause là yêu cầu chẩn đoán nội bộ. Điều đó không có nghĩa phải trả toàn bộ cause chain cho HTTP client hoặc người dùng.

Ví dụ, một SQLException có thể chứa tên bảng, câu SQL, địa chỉ máy chủ hoặc thông tin cấu trúc hệ thống. Những chi tiết này có thể hữu ích trong log nội bộ nhưng không nên tự động xuất hiện trong response công khai.

Một exception handler có thể tạo phản hồi an toàn:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderServiceException.class)
    public ResponseEntity<ProblemDetail> handle(
            OrderServiceException ex) {

        ProblemDetail problem =
            ProblemDetail.forStatus(
                HttpStatus.INTERNAL_SERVER_ERROR
            );

        problem.setTitle("Unable to place order");
        problem.setDetail(
            "The order could not be processed."
        );

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(problem);
    }
}
~~~

Cause vẫn tồn tại trong exception để logging hoặc observability nội bộ sử dụng. Response chỉ chứa thông tin đã được chọn lọc cho client.

Không nên trả ex.getCause().getMessage() một cách mặc định, đặc biệt với lỗi persistence, kết nối hoặc lỗi từ thư viện bên ngoài.

## 17. Cause khác với suppressed exception

Java có hai cơ chế thường xuất hiện trong stack trace:

- **Cause:** nguyên nhân khiến exception hiện tại được tạo hoặc ném ra; truy cập bằng getCause().
- **Suppressed exception:** lỗi phụ phát sinh trong lúc xử lý hoặc đóng tài nguyên khi một exception khác đã xảy ra; truy cập bằng getSuppressed().

Ví dụ try-with-resources:

~~~java
try (InputStream input = openFile()) {
    process(input);
}
~~~

Nếu process ném IOException và close() cũng ném IOException, lỗi trong process thường là exception chính; lỗi khi đóng tài nguyên được gắn dưới dạng suppressed exception.

Khi bọc exception chính, hãy giữ chính exception đó làm cause. Suppressed exceptions của nó vẫn có thể được truy cập qua getSuppressed().

Không nên nhầm việc giữ cause với việc tự gom mọi exception phụ thành cause. Hai quan hệ này có ý nghĩa khác nhau.

## 18. Cause chain và quy tắc rollback của transaction

Trong Spring transaction, loại exception được ném ra có thể ảnh hưởng đến quyết định rollback.

Theo quy tắc mặc định phổ biến của @Transactional:

- RuntimeException và Error làm transaction rollback.
- Checked exception không tự động kích hoạt rollback theo mặc định.

Ví dụ:

~~~java
@Transactional
public void placeOrder(Order order) {
    try {
        repository.save(order);
    } catch (SQLException ex) {
        throw new OrderServiceException(
            "Cannot place order",
            ex
        );
    }
}
~~~

OrderServiceException ở ví dụ là RuntimeException, nên transaction thường được rollback theo mặc định.

Nếu wrapper là checked exception, cần xem xét rollback rules:

~~~java
@Transactional(rollbackFor = OrderCheckedException.class)
public void placeOrder(Order order)
        throws OrderCheckedException {
    // ...
}
~~~

Giữ cause không tự quyết định rollback. Spring transaction interceptor chủ yếu xét loại exception được ném ra và rollback rules được cấu hình; cause chain giúp chẩn đoán nguyên nhân nhưng không thay thế quy tắc đó.

Khi đổi loại exception ở ranh giới service, hãy kiểm tra xem thay đổi đó có làm thay đổi hành vi rollback mà ứng dụng mong muốn hay không.

## 19. Tránh bọc lặp lại mà không thêm giá trị

Một chuỗi wrapper quá dài có thể làm stack trace khó đọc nếu mỗi tầng chỉ thay message mà không thêm ngữ cảnh có ích.

Ví dụ không cần thiết:

~~~text
RuntimeException
  -> RuntimeException
      -> RuntimeException
          -> SQLException
~~~

Nếu các tầng đều dùng cùng một loại exception chung, người đọc khó xác định abstraction nào thực sự quan trọng.

Nên bọc khi có lý do cụ thể:

- Chuyển từ exception công nghệ sang abstraction của Spring.
- Chuyển từ persistence sang lỗi nghiệp vụ.
- Bổ sung mã tài nguyên, bean, thao tác hoặc request có ích.
- Chuẩn hóa lỗi theo hợp đồng của module.

Nếu không có giá trị mới, truyền tiếp exception ban đầu. Một cause chain ngắn, có ý nghĩa thường dễ bảo trì hơn nhiều lớp wrapper chung chung.

## 20. Ví dụ hoàn chỉnh: giữ nguyên cause qua repository và service

Định nghĩa exception ở tầng service:

~~~java
public class OrderServiceException extends RuntimeException {

    public OrderServiceException(
            String message,
            Throwable cause) {
        super(message, cause);
    }
}
~~~

Repository dùng JdbcTemplate:

~~~java
@Repository
public class JdbcOrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.getId(),
            order.getStatus()
        );
    }
}
~~~

Service bổ sung ngữ cảnh nghiệp vụ:

~~~java
@Service
public class OrderService {

    private final JdbcOrderRepository repository;

    public OrderService(JdbcOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void placeOrder(Order order) {
        try {
            repository.insert(order);
        } catch (DataAccessException ex) {
            throw new OrderServiceException(
                "Failed to place order " + order.getId(),
                ex
            );
        }
    }
}
~~~

Nếu JDBC gặp lỗi, JdbcTemplate dịch exception sang DataAccessException. Service tiếp tục bọc lỗi đó thành OrderServiceException và giữ DataAccessException làm cause.

Khi xử lý ở tầng ngoài:

~~~java
try {
    orderService.placeOrder(order);
} catch (OrderServiceException ex) {
    log.error(
        "Order processing failed, orderId={}",
        order.getId(),
        ex
    );
}
~~~

Log chứa stack trace của OrderServiceException và cause chain bên dưới. Tầng API có thể ánh xạ OrderServiceException sang response an toàn mà không tiết lộ chi tiết database.

## 21. Checklist điều tra khi cause bị mất

Khi stack trace chỉ còn wrapper ở tầng Spring, hãy kiểm tra:

1. Constructor của exception mới có nhận Throwable cause không?
2. Lệnh tạo exception có truyền exception bắt được làm đối số thứ hai không?
3. Có đoạn code nào chỉ nối ex.getMessage() vào message mới không?
4. Một tầng trung gian có bắt exception rồi ném exception khác mà bỏ cause không?
5. Có framework translator hoặc adapter tùy chỉnh nào tạo exception mới mà không giữ exception gốc không?
6. Logger có nhận đối tượng Throwable hay chỉ nhận message?
7. Có exception phụ trong getSuppressed() cần được xem riêng không?
8. Loại wrapper mới có làm thay đổi rollback rule hoặc exception handler được kích hoạt không?

Có thể kiểm tra cause trực tiếp trong mã:

~~~java
Throwable cause = wrappedException.getCause();

if (cause != null) {
    log.debug(
        "Underlying exception type: {}",
        cause.getClass().getName()
    );
}
~~~

Khi kiểm thử exception translation, nên xác nhận cả loại wrapper, message ngữ cảnh và cause được giữ đúng object hoặc đúng loại exception mong đợi.

## 22. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Chỉ cần đưa message của lỗi gốc vào message mới là đủ.**  
Message không thay thế cause. Hãy truyền exception gốc vào constructor nhận Throwable.

**Nhầm lẫn 2: Mỗi tầng Spring đều phải tạo một wrapper mới.**  
Chỉ bọc khi cần đổi abstraction hoặc thêm ngữ cảnh hữu ích. Nếu không, có thể ném lại exception ban đầu.

**Nhầm lẫn 3: Cause chain quyết định transaction rollback.**  
Rollback mặc định chủ yếu dựa vào loại exception được ném ra và rollback rules; cause hỗ trợ chẩn đoán.

**Nhầm lẫn 4: @Repository tự nó bắt mọi exception.**  
Exception translation cần hạ tầng Spring tương ứng. JdbcTemplate và persistence translation có cơ chế riêng để dịch lỗi.

**Nhầm lẫn 5: Log message là đủ để điều tra.**  
Nên truyền Throwable cho logger để giữ stack trace, cause chain và thông tin suppressed.

**Nhầm lẫn 6: Giữ cause đồng nghĩa phải trả cause cho client.**  
Cause phục vụ chẩn đoán nội bộ. API nên trả thông tin an toàn và phù hợp với người dùng.

**Nhầm lẫn 7: Suppressed exception chính là cause.**  
Cause là nguyên nhân của wrapper; suppressed exception là lỗi phụ được gắn riêng, thường trong quá trình đóng tài nguyên.

## 23. Ghi nhớ

- Exception wrapping dùng để chuyển abstraction hoặc bổ sung ngữ cảnh khi lỗi đi qua các tầng.
- Constructor \`Throwable(message, cause)\` là cách rõ ràng để giữ exception gốc.
- Nếu không cần đổi loại lỗi hoặc thêm ngữ cảnh, hãy ném lại exception ban đầu.
- Không tạo wrapper chỉ chứa message hoặc chỉ nối getMessage() mà bỏ cause.
- Nhiều exception Spring hỗ trợ constructor nhận cause; DataAccessException và các subclass là ví dụ quan trọng ở tầng DAO.
- JdbcTemplate và persistence exception translation giúp chuẩn hóa lỗi công nghệ thành abstraction Spring; hãy giữ cause khi tự viết translator hoặc wrapper.
- NestedRuntimeException cung cấp getRootCause(), getMostSpecificCause() và contains() để hỗ trợ chẩn đoán.
- Logging nên nhận Throwable để ghi stack trace và cause chain.
- Cause chain khác suppressed exceptions.
- Không tiết lộ chi tiết cause nội bộ trong response công khai nếu chúng chứa thông tin kỹ thuật nhạy cảm.
- Khi đổi loại exception trong service có @Transactional, hãy kiểm tra rollback rules vì loại wrapper có thể ảnh hưởng hành vi rollback.
- Tránh bọc lặp lại nếu mỗi tầng không thêm thông tin hoặc abstraction có giá trị.

Khi bọc lỗi ở tầng Spring, hãy chọn exception thể hiện đúng abstraction của tầng hiện tại, bổ sung ngữ cảnh có ích và luôn truyền exception đã bắt được làm cause. Sau đó kiểm tra log, exception handler và transaction rules để bảo đảm nguyên nhân gốc vẫn truy vết được trong toàn bộ luồng xử lý.

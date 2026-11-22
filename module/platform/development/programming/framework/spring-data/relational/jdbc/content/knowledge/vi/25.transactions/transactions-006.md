# Rollback, checked exception và rollbackFor

## 1. Vì sao checked exception có thể làm dữ liệu vẫn được commit?

Khi một service Spring thực hiện nhiều thao tác ghi trong cùng transaction, ta thường mong muốn tất cả thao tác cùng thành công hoặc cùng bị hoàn tác. Ví dụ, một use case nhập hàng có thể:

1. Tạo phiếu nhập.
2. Thêm các dòng hàng vào phiếu.
3. Cập nhật số lượng tồn kho.
4. Ghi một bản ghi audit.

Nếu bước thứ ba hoặc thứ tư thất bại, các thay đổi trước đó có thể cần rollback để database không lưu trạng thái dở dang.

Spring transaction có quy tắc rollback mặc định. Quy tắc này phân biệt **unchecked exception** với **checked exception**:

- Với **RuntimeException** và **Error**, Spring mặc định đánh dấu transaction rollback.
- Với checked exception, Spring mặc định không rollback chỉ vì exception đó được ném ra. Transaction có thể commit nếu exception thoát khỏi phương thức transactional mà không có rollback rule phù hợp.

Điều này thường gây bất ngờ khi ứng dụng định nghĩa exception nghiệp vụ bằng cách kế thừa **Exception**. Một lỗi nghiệp vụ có thể thoát khỏi service, caller nhận được lỗi, nhưng các câu lệnh SQL trước đó vẫn được commit.

Thuộc tính **rollbackFor** cho phép khai báo rõ kiểu exception nào phải làm transaction rollback. Bài này giải thích quy tắc mặc định, cách cấu hình **rollbackFor** và **noRollbackFor**, ảnh hưởng của việc bắt exception, cách kiểm thử và cách chọn chính sách phù hợp cho Spring Data JDBC.

## 2. Checked và unchecked exception trong Java

Java chia exception thành hai nhóm thường gặp:

| Nhóm | Đặc điểm | Ví dụ |
| --- | --- | --- |
| Checked exception | Là exception phải được khai báo bằng throws hoặc xử lý bằng try/catch theo quy tắc của Java compiler | IOException, exception nghiệp vụ kế thừa trực tiếp Exception |
| Unchecked exception | Kế thừa RuntimeException; không bắt buộc khai báo hoặc bắt | IllegalArgumentException, IllegalStateException, NullPointerException |

Ví dụ checked exception:

~~~java
public class ImportValidationException extends Exception {

    public ImportValidationException(String message) {
        super(message);
    }
}
~~~

Ví dụ unchecked exception:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String message) {
        super(message);
    }
}
~~~

Một exception không trở thành checked hay unchecked theo ý nghĩa nghiệp vụ hoặc tên gọi của nó. Quyết định nằm ở kiểu cha trong hệ thống class:

- Kế thừa Exception nhưng không kế thừa RuntimeException: checked.
- Kế thừa RuntimeException: unchecked.

## 3. Quy tắc rollback mặc định của Spring

Với cấu hình transaction mặc định phổ biến của Spring:

| Exception thoát khỏi transactional method | Kết quả mặc định |
| --- | --- |
| RuntimeException | Rollback |
| Lớp con của RuntimeException | Rollback |
| Error | Rollback |
| Checked exception, ví dụ IOException | Không tự động rollback |
| Lớp con của checked exception | Không tự động rollback |

Ví dụ:

~~~java
@Transactional
public void createOrder() {
    orders.save(new PurchaseOrder(...));

    throw new IllegalStateException("Cannot continue");
}
~~~

IllegalStateException là unchecked exception. Khi nó thoát khỏi phương thức qua transaction interceptor, Spring mặc định rollback transaction.

Ngược lại:

~~~java
@Transactional
public void importOrder() throws ImportValidationException {
    orders.save(new PurchaseOrder(...));

    throw new ImportValidationException("Invalid import row");
}
~~~

ImportValidationException là checked exception. Nếu không có rollback rule khác, Spring mặc định không rollback chỉ vì exception này. Tùy transaction manager và trạng thái transaction, thay đổi trước đó có thể được commit dù caller nhận exception.

Đây là lý do cần thiết kế loại exception và rollback policy cùng nhau. Không nên cho rằng mọi exception đều có cùng hành vi.

## 4. Dùng rollbackFor để rollback khi có checked exception

Thuộc tính rollbackFor nhận một hoặc nhiều kiểu exception. Khi exception phù hợp thoát khỏi phương thức transactional, Spring đánh dấu transaction rollback.

Ví dụ:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importOrder() throws ImportValidationException {
    orders.save(new PurchaseOrder(...));
    inventory.increase(...);

    throw new ImportValidationException("Invalid import row");
}
~~~

Trong ví dụ này:

1. Repository lưu đơn hàng.
2. Một thao tác khác cập nhật tồn kho.
3. Checked exception được ném ra.
4. Transaction interceptor nhận exception và áp dụng rollback rule.
5. Cả hai thay đổi database trong transaction được rollback.

Có thể khai báo nhiều kiểu:

~~~java
@Transactional(
        rollbackFor = {
                ImportValidationException.class,
                IOException.class
        }
)
public void importFile() throws ImportValidationException, IOException {
    // Đọc và ghi dữ liệu.
}
~~~

Với Spring, có thể dùng rollbackFor = Exception.class nếu chính sách của use case là mọi exception đều phải rollback:

~~~java
@Transactional(rollbackFor = Exception.class)
public void process() throws Exception {
    // Mọi checked exception thuộc Exception và unchecked exception
    // đều được bao phủ bởi rule này.
}
~~~

Tuy nhiên, không nên thêm rollbackFor = Exception.class theo thói quen cho mọi method. Hãy chọn chính sách theo ý nghĩa nghiệp vụ: có những checked exception chỉ biểu thị một kết quả dự kiến mà ứng dụng vẫn muốn commit một phần trạng thái hợp lệ.

## 5. Ví dụ Spring Data JDBC: nhập hàng và rollback khi validation thất bại

Giả sử một use case nhập hàng cần lưu phiếu nhập và cập nhật tồn kho. Nếu dữ liệu dòng hàng không hợp lệ, cả hai thay đổi phải được hủy.

### 5.1. Định nghĩa checked exception

~~~java
public class ImportValidationException extends Exception {

    public ImportValidationException(String message) {
        super(message);
    }
}
~~~

### 5.2. Repository

~~~java
public interface GoodsReceiptRepository
        extends CrudRepository<GoodsReceipt, Long> {
}

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {
}
~~~

### 5.3. Service có rollbackFor

~~~java
@Service
public class GoodsReceiptService {

    private final GoodsReceiptRepository receipts;
    private final InventoryRepository inventory;

    public GoodsReceiptService(
            GoodsReceiptRepository receipts,
            InventoryRepository inventory
    ) {
        this.receipts = receipts;
        this.inventory = inventory;
    }

    @Transactional(rollbackFor = ImportValidationException.class)
    public Long importReceipt(GoodsReceipt receipt)
            throws ImportValidationException {

        GoodsReceipt saved = receipts.save(receipt);

        for (ReceiptLine line : saved.lines()) {
            if (line.quantity() <= 0) {
                throw new ImportValidationException(
                        "Quantity must be positive for SKU " + line.sku()
                );
            }

            Inventory stock = inventory.findById(line.inventoryId())
                    .orElseThrow();

            inventory.save(stock.increase(line.quantity()));
        }

        return saved.id();
    }
}
~~~

Đây là ví dụ minh họa ranh giới transaction; model và phương thức increase cần được định nghĩa theo domain của ứng dụng. Nếu exception được ném sau khi đã lưu phiếu hoặc cập nhật một số dòng, rollbackFor giúp hoàn tác các thao tác đó trong cùng transaction.

### 5.4. Vì sao transaction phải đặt ở service?

Repository chỉ biết thao tác persistence của nó. Service mới biết use case nhập hàng gồm nhiều bước và những bước nào phải cùng thành công.

Nếu chỉ đặt transaction riêng trên từng repository method, có thể mỗi lời gọi kết thúc và commit độc lập khi không có transaction bao ngoài. Khi đó, lỗi ở dòng hàng thứ ba không thể hoàn tác các bước đã commit trước đó.

Đặt @Transactional ở service giúp tất cả repository method tham gia cùng transaction nếu chúng dùng chung DataSource và transaction manager phù hợp.

## 6. rollbackFor và noRollbackFor

Spring cung cấp hai hướng cấu hình:

- **rollbackFor:** các exception phù hợp phải rollback.
- **noRollbackFor:** các exception phù hợp không làm rollback theo rule đó.

Ví dụ:

~~~java
@Transactional(
        rollbackFor = ImportValidationException.class,
        noRollbackFor = DuplicateReferenceException.class
)
public void importReceipt() throws ImportValidationException {
    // Thực hiện thao tác ghi.
}
~~~

Ở đây, ImportValidationException yêu cầu rollback, còn DuplicateReferenceException được cấu hình không rollback. noRollbackFor thường chỉ nên dùng khi ứng dụng có chủ đích commit trạng thái dù một exception cụ thể được ném ra.

Ví dụ một use case ghi nhận lần thử xử lý:

~~~java
@Transactional(noRollbackFor = AlreadyProcessedException.class)
public void recordAttempt(Command command) throws AlreadyProcessedException {
    attempts.save(Attempt.started(command.id()));

    if (alreadyProcessed(command.id())) {
        throw new AlreadyProcessedException(command.id());
    }
}
~~~

Đây chỉ là ví dụ về ý nghĩa chính sách. Nếu exception báo rằng nghiệp vụ đã được xử lý, hãy cân nhắc liệu có cần ghi attempt trước khi kiểm tra hay không; đôi khi kiểm tra trước và trả về kết quả bình thường sẽ rõ hơn việc dùng exception để điều khiển commit.

### 6.1. Rule cụ thể và rule tổng quát

Nếu nhiều rule cùng khớp một exception, Spring áp dụng rule cụ thể nhất, tức rule có mức khớp gần nhất với kiểu exception thực tế.

Ví dụ:

~~~java
@Transactional(
        rollbackFor = Exception.class,
        noRollbackFor = DuplicateReferenceException.class
)
public void execute() throws Exception {
    // ...
}
~~~

Rule noRollbackFor cụ thể cho DuplicateReferenceException thắng rule tổng quát rollbackFor = Exception.class đối với exception đó. Các checked exception khác vẫn được rule tổng quát bao phủ.

Đừng khai báo các rule chồng chéo nếu không có lý do rõ ràng. Một chính sách đơn giản, cụ thể thường dễ đọc và kiểm thử hơn.

## 7. rollbackForClassName và vì sao nên ưu tiên kiểu class

@Transactional còn có các thuộc tính dạng tên lớp như rollbackForClassName và noRollbackForClassName. Chúng cho phép khai báo rule bằng tên exception dưới dạng chuỗi.

Ví dụ:

~~~java
@Transactional(rollbackForClassName = "com.example.ImportValidationException")
public void importData() throws ImportValidationException {
    // ...
}
~~~

Trong phần lớn code Java, nên ưu tiên:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
~~~

Lý do:

- Compiler kiểm tra được kiểu class.
- Refactor package/class an toàn hơn.
- Tránh lỗi chính tả trong chuỗi.
- Dễ đọc và IDE hỗ trợ điều hướng tốt hơn.

Rule theo tên lớp có thể sử dụng pattern khớp tên exception. Pattern không nhất thiết là phép so khớp chính xác toàn bộ tên; một pattern rộng có thể khớp những exception ngoài dự kiến. Vì vậy, tránh dùng chuỗi ngắn như Exception hoặc Validation làm rule nếu không hiểu phạm vi khớp.

## 8. Điều gì xảy ra khi bắt exception bên trong phương thức transactional?

Rollback rule được áp dụng khi transaction interceptor quan sát được exception thoát khỏi lời gọi transactional. Nếu code bắt exception và không ném lại, interceptor có thể chỉ thấy phương thức kết thúc bình thường.

Ví dụ:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importData() {
    receipts.save(new GoodsReceipt(...));

    try {
        validate();
    } catch (ImportValidationException ex) {
        log.warn("Import rejected: {}", ex.getMessage());
        // Không ném lại exception.
    }
}
~~~

Ở đây, ImportValidationException bị bắt và không thoát khỏi phương thức. Chỉ khai báo rollbackFor không có nghĩa Spring sẽ tự rollback khi code đã nuốt exception. Nếu method kết thúc bình thường và transaction chưa bị đánh dấu rollback-only, transaction có thể commit.

### 8.1. Cách 1: ném lại exception

Nếu lỗi phải hủy toàn bộ use case, cách rõ nhất là ném exception ra ngoài:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importData() throws ImportValidationException {
    receipts.save(new GoodsReceipt(...));
    validate(); // Exception thoát khỏi method.
}
~~~

### 8.2. Cách 2: đánh dấu rollback-only

Nếu cần bắt exception để ghi log hoặc chuyển đổi kết quả, nhưng vẫn muốn rollback:

~~~java
@Transactional
public ImportResult importData() {
    receipts.save(new GoodsReceipt(...));

    try {
        validate();
        return ImportResult.success();
    } catch (ImportValidationException ex) {
        log.warn("Import rejected", ex);
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return ImportResult.rejected(ex.getMessage());
    }
}
~~~

setRollbackOnly() đánh dấu transaction hiện tại phải rollback khi kết thúc. Cách này phù hợp khi contract của service muốn trả về một kết quả thay vì ném exception, nhưng vẫn phải hủy thay đổi database.

Để dùng API trên, import:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;
~~~

Chỉ gọi currentTransactionStatus() trong phạm vi có transaction được quản lý bởi Spring. Nếu không có transaction phù hợp, thao tác có thể thất bại.

### 8.3. Cách 3: chuyển checked exception thành unchecked exception

Có thể bọc checked exception thành runtime exception:

~~~java
try {
    validate();
} catch (ImportValidationException ex) {
    throw new IllegalStateException("Import failed", ex);
}
~~~

Do IllegalStateException là unchecked, rollback mặc định được áp dụng khi exception thoát khỏi transactional method. Tuy nhiên, chỉ nên bọc khi kiểu exception mới diễn đạt đúng abstraction của lỗi. Không biến mọi lỗi nghiệp vụ thành RuntimeException chỉ để né cấu hình rollback.

## 9. Inner transaction, REQUIRED và UnexpectedRollbackException

Một trường hợp tinh tế xảy ra khi một transactional method gọi method transactional khác với propagation mặc định REQUIRED.

~~~java
@Service
public class ImportCoordinator {

    private final ImportWorker worker;

    public ImportCoordinator(ImportWorker worker) {
        this.worker = worker;
    }

    @Transactional
    public void run() {
        try {
            worker.processOne();
        } catch (IllegalStateException ex) {
            log.warn("One item failed", ex);
        }

        // Caller có thể muốn tiếp tục, nhưng transaction đã rollback-only.
    }
}

@Service
public class ImportWorker {

    @Transactional
    public void processOne() {
        throw new IllegalStateException("Cannot process item");
    }
}
~~~

Nếu processOne() được gọi qua proxy và tham gia transaction đang có, unchecked exception có thể khiến transaction được đánh dấu rollback-only. ImportCoordinator bắt exception, nhưng trạng thái rollback-only vẫn còn. Khi transaction ngoài kết thúc, Spring có thể ném UnexpectedRollbackException thay vì commit.

Điểm cần nhớ:

- Bắt exception không tự xóa trạng thái rollback-only.
- REQUIRED dùng chung transaction, nên lỗi ở phần tham gia có thể ảnh hưởng transaction ngoài.
- Nếu mỗi item cần commit/rollback độc lập, phải thiết kế transaction boundary riêng, chẳng hạn một bean xử lý từng item với REQUIRES_NEW, đồng thời hiểu rõ chi phí và semantics.

Không dùng REQUIRES_NEW chỉ để tránh UnexpectedRollbackException. Hãy xác định liệu nghiệp vụ thật sự cho phép một item commit độc lập với các item khác hay không.

## 10. Propagation ảnh hưởng rollback thế nào?

| Propagation | Ảnh hưởng khái quát |
| --- | --- |
| REQUIRED | Tham gia transaction hiện tại hoặc tạo mới. Rollback-only trong transaction chung có thể khiến toàn bộ use case rollback. |
| REQUIRES_NEW | Dùng transaction độc lập. Transaction trong có thể commit dù transaction ngoài rollback, và ngược lại. |
| NESTED | Có thể dùng savepoint nếu transaction manager hỗ trợ; rollback phần nested không nhất thiết hủy toàn bộ transaction ngoài. |
| SUPPORTS | Tham gia transaction nếu có; nếu không, không tự tạo transaction mới. |
| MANDATORY | Yêu cầu caller có transaction; nếu không có, lời gọi thất bại. |
| NOT_SUPPORTED | Tạm treo transaction hiện có và chạy ngoài transaction. |
| NEVER | Không cho phép có transaction hiện tại. |

Ví dụ audit độc lập:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordFailureAttempt(ImportAttempt attempt) {
    attempts.save(attempt);
}
~~~

Một audit attempt có thể cần tồn tại ngay cả khi transaction nghiệp vụ chính rollback. Nhưng nếu audit biểu thị rằng nghiệp vụ đã thành công, commit độc lập có thể tạo thông tin sai. Quyết định phải dựa trên ý nghĩa dữ liệu.

## 11. Database exception và checked exception không giống nhau

Khi dùng Spring JDBC, lỗi từ JDBC thường được chuyển đổi thành hệ exception của Spring, chẳng hạn các lớp kế thừa DataAccessException. DataAccessException là unchecked exception.

Ví dụ:

~~~java
@Transactional
public void saveCustomer(Customer customer) {
    customers.save(customer);
    // Lỗi constraint từ Spring JDBC thường được chuyển thành
    // một DataAccessException thuộc RuntimeException.
}
~~~

Vì vậy, nhiều lỗi persistence thông thường đã kích hoạt rollback theo quy tắc mặc định. rollbackFor thường cần thiết hơn với checked exception do ứng dụng tự định nghĩa, lỗi đọc file, lỗi validation hoặc API thư viện bên ngoài.

Không nên bắt một DataAccessException, log rồi tiếp tục như thể transaction vẫn có thể commit an toàn. Database hoặc transaction manager có thể đã đánh dấu transaction rollback-only, đặc biệt khi lỗi xảy ra trong một transaction đang tham gia.

## 12. Chọn checked exception hay unchecked exception cho lỗi nghiệp vụ?

Cả hai loại đều có thể hợp lý. Hãy chọn theo contract của API và cách caller xử lý:

| Tình huống | Cách thiết kế có thể phù hợp |
| --- | --- |
| Lỗi đầu vào dự kiến, caller cần xử lý như một kết quả nghiệp vụ | Checked exception hoặc result type rõ ràng |
| Vi phạm trạng thái bất hợp lệ trong lập trình hoặc invariant bị phá vỡ | Unchecked exception |
| Lỗi I/O từ thư viện | Checked exception gốc; quyết định rollback bằng rollbackFor nếu cần |
| Lỗi persistence do Spring JDBC | Thường là unchecked DataAccessException |
| Một lỗi nghiệp vụ phải hủy toàn bộ transaction | Chọn exception và cấu hình rollback rule tường minh |

Đừng chọn checked exception chỉ vì muốn buộc caller xử lý; cũng đừng chọn unchecked chỉ để transaction tự rollback. Loại exception nên thể hiện contract của tầng ứng dụng, còn rollback policy thể hiện tác động mong muốn lên transaction.

## 13. Kiểm thử rollbackFor

Một integration test nên xác nhận dữ liệu thực tế sau khi transactional method ném checked exception. Quan trọng là đọc lại dữ liệu sau khi transaction của service đã kết thúc.

### 13.1. Service minh họa

~~~java
public class ImportRejectedException extends Exception {
    public ImportRejectedException(String message) {
        super(message);
    }
}

@Service
public class DemoImportService {

    private final JdbcTemplate jdbc;

    public DemoImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void insertThenThrowWithoutRule() throws ImportRejectedException {
        jdbc.update(
                "INSERT INTO import_marker(marker) VALUES (?)",
                "default-rule"
        );
        throw new ImportRejectedException("Rejected");
    }

    @Transactional(rollbackFor = ImportRejectedException.class)
    public void insertThenThrowWithRule() throws ImportRejectedException {
        jdbc.update(
                "INSERT INTO import_marker(marker) VALUES (?)",
                "rollback-rule"
        );
        throw new ImportRejectedException("Rejected");
    }
}
~~~

Giả sử bảng import_marker đã được tạo và mỗi test dùng dữ liệu độc lập.

### 13.2. Kiểm tra mặc định và rollbackFor

~~~java
@SpringBootTest
class RollbackRuleIntegrationTest {

    @Autowired
    DemoImportService service;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void checkedExceptionDoesNotRollbackByDefault() {
        assertThatThrownBy(service::insertThenThrowWithoutRule)
                .isInstanceOf(ImportRejectedException.class);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM import_marker WHERE marker = ?",
                Integer.class,
                "default-rule"
        );

        assertThat(count).isEqualTo(1);
    }

    @Test
    void rollbackForRollsBackCheckedException() {
        assertThatThrownBy(service::insertThenThrowWithRule)
                .isInstanceOf(ImportRejectedException.class);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM import_marker WHERE marker = ?",
                Integer.class,
                "rollback-rule"
        );

        assertThat(count).isZero();
    }
}
~~~

Đây là ví dụ minh họa hành vi mặc định của Spring transaction; test cần dependency AssertJ/JUnit, schema và transaction manager thực tế của dự án. Hai test không nên bị bao trong một test transaction ngoài nếu mục tiêu là quan sát commit/rollback của service. Nếu test class hoặc test method có @Transactional, transaction của test có thể làm thay đổi cách quan sát kết quả và thời điểm commit.

### 13.3. Những điều nên kiểm tra thêm

- Exception thật sự được ném ra ngoài transactional proxy.
- Method được gọi qua Spring bean/proxy, không phải self-invocation.
- Repository và JdbcTemplate dùng cùng DataSource/transaction manager nếu cần cùng transaction.
- Không có catch block nuốt exception.
- Không có noRollbackFor hoặc rule cụ thể khác làm thay đổi kết quả.
- Test đọc lại dữ liệu sau khi service transaction kết thúc.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Checked exception thoát ra nhưng dữ liệu vẫn tồn tại | Spring mặc định không rollback checked exception | Thêm rollbackFor cho kiểu exception cần rollback. |
| Đã khai báo rollbackFor nhưng dữ liệu vẫn commit | Exception bị catch và nuốt trước khi thoát khỏi transactional method | Ném lại exception hoặc đánh dấu rollback-only. |
| rollbackFor = Exception.class nhưng một lỗi vẫn không rollback | Có noRollbackFor cụ thể hơn hoặc transaction đã kết thúc trước khi lỗi xảy ra | Kiểm tra rule precedence và transaction boundary. |
| Inner method lỗi, outer method bắt lỗi nhưng commit thất bại | Transaction chung đã bị đánh dấu rollback-only | Hiểu propagation REQUIRED; chọn transaction độc lập chỉ khi nghiệp vụ cho phép. |
| UnexpectedRollbackException ở cuối method | Một participant đã đánh dấu transaction chung rollback-only | Tìm exception ban đầu và ranh giới transactional lồng nhau. |
| Lỗi I/O không làm rollback | Checked exception không có rollback rule | Khai báo rollbackFor = IOException.class hoặc kiểu exception cụ thể. |
| Database exception rollback dù không khai báo rollbackFor | Spring JDBC thường chuyển lỗi thành unchecked DataAccessException | Đây là hành vi mặc định; không nuốt lỗi nếu cần rollback. |
| Test cho kết quả khác production | Test có transaction bao ngoài hoặc dùng database khác | Kiểm thử service transaction độc lập trên database gần production. |

## 15. Quy trình thiết kế rollback policy

Khi một service có thể ném exception, hãy xác định:

1. **Exception là checked hay unchecked?** Kiểm tra hệ thống kế thừa của class.
2. **Exception có thoát khỏi transactional method không?** Kiểm tra catch/rethrow và proxy.
3. **Nếu exception xảy ra, dữ liệu đã ghi phải được giữ hay hủy?** Quyết định theo nghiệp vụ.
4. **Rule mặc định có đáp ứng không?** RuntimeException và Error mặc định rollback; checked exception thì không.
5. **Có cần rollbackFor không?** Ưu tiên kiểu class cụ thể.
6. **Có noRollbackFor không?** Chỉ khai báo nếu chủ đích commit khi exception đó xảy ra.
7. **Có transaction tham gia/lồng nhau không?** Kiểm tra propagation và rollback-only.
8. **Có thao tác ngoài database không?** @Transactional không tự rollback file, email, HTTP hoặc message broker.
9. **Đã kiểm thử trạng thái sau commit/rollback chưa?** Đọc dữ liệu sau khi transaction thực sự kết thúc.

## 16. Bài tập tự thực hành

**Bài tập 1 — Quan sát mặc định.** Tạo một checked exception kế thừa Exception. Trong một method @Transactional, insert một hàng rồi ném exception. Đọc lại hàng sau khi method kết thúc và giải thích kết quả.

**Bài tập 2 — Thêm rollbackFor.** Thêm rollbackFor = YourCheckedException.class vào method. Chạy lại test và xác nhận hàng đã insert bị rollback.

**Bài tập 3 — Nhiều rollback rule.** Khai báo rollbackFor = Exception.class và noRollbackFor cho một exception cụ thể. Kiểm tra exception cụ thể và một checked exception khác.

**Bài tập 4 — Bắt exception.** Bắt checked exception bên trong transactional method rồi trả về bình thường. Quan sát dữ liệu và thử thêm setRollbackOnly().

**Bài tập 5 — REQUIRED lồng nhau.** Tạo hai service bean, cả hai dùng @Transactional. Inner service ném runtime exception; outer service bắt exception. Quan sát UnexpectedRollbackException.

**Bài tập 6 — REQUIRES_NEW.** Thử ghi một audit attempt trong transaction riêng rồi làm transaction ngoài rollback. Giải thích dữ liệu nào còn lại và tại sao.

**Bài tập 7 — Lỗi I/O.** Đọc một file trong use case ghi database. Khi IOException xảy ra, cấu hình rollback phù hợp và xác nhận database không lưu dữ liệu dở dang.

## 17. Ghi nhớ

Spring mặc định rollback khi RuntimeException hoặc Error thoát khỏi transactional method. Checked exception như IOException hoặc exception nghiệp vụ kế thừa Exception không tự động làm rollback. Nếu checked exception phải hủy các thao tác database trong use case, khai báo rollbackFor cho kiểu exception phù hợp.

rollbackFor chỉ có tác dụng khi exception đi tới transaction interceptor hoặc transaction được đánh dấu rollback-only. Nếu code bắt và nuốt exception, method có thể kết thúc bình thường và transaction commit. Khi các method tham gia cùng transaction bằng REQUIRED, lỗi ở một participant có thể đánh dấu transaction chung rollback-only dù caller bên ngoài đã bắt exception.

Chọn exception type theo contract của ứng dụng, chọn rollback rule theo ý nghĩa nghiệp vụ, và kiểm thử trạng thái database sau khi transaction kết thúc. Đừng dùng một cấu hình rộng cho mọi method nếu mỗi use case có chính sách commit/rollback khác nhau.

### Tài liệu tham khảo

- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Java 21 – Exception](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html)
- [Java 21 – RuntimeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/RuntimeException.html)

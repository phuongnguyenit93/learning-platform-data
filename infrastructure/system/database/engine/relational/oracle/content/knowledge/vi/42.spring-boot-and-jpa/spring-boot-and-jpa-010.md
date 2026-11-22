# @Transactional, propagation và ranh giới giao dịch qua proxy

Trong Spring Boot và JPA, annotation **@Transactional** mô tả cách một lời gọi phương thức tham gia vào transaction. Annotation này không tự biến mọi dòng code trong phương thức thành một giao dịch. Ở chế độ mặc định của Spring, một **proxy** đứng trước bean sẽ chặn lời gọi từ bên ngoài, đọc metadata của @Transactional, mở hoặc tham gia transaction, gọi phương thức thật, rồi commit hoặc rollback khi phương thức kết thúc.

Điểm mấu chốt là **ranh giới transaction được tạo tại lời gọi đi qua proxy**. Nếu một phương thức gọi phương thức khác trong cùng object bằng this, lời gọi nội bộ thường không đi qua proxy; annotation ở phương thức được gọi có thể không được áp dụng. Hiểu đúng ranh giới này giúp tránh các lỗi như REQUIRES_NEW không chạy, rollback không xảy ra như mong đợi, transaction kết thúc quá sớm hoặc một thao tác tưởng độc lập lại bị rollback cùng thao tác bên ngoài.

Bài học trình bày cách Spring proxy áp dụng @Transactional, ý nghĩa từng propagation mode, cách transaction manager và JPA persistence context tham gia, quy tắc rollback, tương tác với Oracle Database, kiểm thử và các mẫu thiết kế phù hợp.

## 1. Transaction trong ứng dụng Spring là gì?

Transaction là một đơn vị công việc cần được xử lý theo các thuộc tính ACID:

- **Atomicity**: hoặc toàn bộ thay đổi được commit, hoặc thay đổi chưa commit bị rollback.
- **Consistency**: transaction phải giữ các quy tắc và constraint của dữ liệu.
- **Isolation**: transaction đồng thời không được nhìn thấy trạng thái trung gian trái với mức isolation đã chọn.
- **Durability**: sau khi commit thành công, dữ liệu đã commit được database bảo đảm lưu bền vững theo cơ chế của database.

Ví dụ, xử lý đơn hàng có thể gồm:
1. Tạo bản ghi ORDER.
2. Tạo ORDER_ITEM.
3. Giảm số lượng tồn kho.
4. Ghi nhận thanh toán nội bộ.
5. Ghi sự kiện cần gửi sang hệ thống khác.

Nếu bước 3 thất bại, các thay đổi database ở bước 1 và 2 thường cần rollback cùng nhau. Một transaction ở service layer có thể bao bọc các repository call để thực hiện điều đó.

### 1.1. Transaction boundary

Transaction boundary xác định thời điểm bắt đầu và kết thúc một transaction. Trong Spring declarative transaction, boundary thường nằm quanh một lần gọi method đã được proxy intercept:

~~~text
Caller
  |
  v
Spring proxy
  |
  +--> đọc @Transactional
  |
  +--> bắt đầu hoặc tham gia transaction
  |
  +--> gọi method thật trên target bean
  |
  +--> commit hoặc rollback
  |
  v
Caller nhận kết quả hoặc exception
~~~

Commit xảy ra sau khi method target trả về thành công và trước khi lời gọi qua proxy trả kết quả cho caller. Nếu commit/flush phát sinh lỗi, caller vẫn có thể nhận exception dù code trong method đã chạy đến dòng return.

### 1.2. Transaction boundary nên đặt ở đâu?

Thông thường, đặt transaction boundary tại service method đại diện cho một use case nghiệp vụ:

- Tạo đơn hàng.
- Chốt hóa đơn.
- Chuyển trạng thái thanh toán.
- Phân bổ tồn kho.
- Hủy đăng ký.
- Cập nhật nhiều aggregate có quan hệ nhất quán.

Repository thường tập trung thao tác dữ liệu. Một transaction có thể gọi nhiều repository và giữ các thay đổi trong cùng một đơn vị nghiệp vụ.

Không nên tạo transaction quá rộng quanh toàn bộ request nếu request còn gọi HTTP, gửi email, chờ người dùng hoặc xử lý file lớn. Transaction dài giữ connection và lock lâu, làm tăng contention và nguy cơ timeout.

## 2. Spring áp dụng @Transactional bằng proxy

Trong Spring Boot, transaction annotation thường được thực thi qua Spring AOP proxy. Proxy là object được inject vào caller; target là object chứa code nghiệp vụ.

### 2.1. Lời gọi qua proxy

Giả sử bean OrderService được Spring quản lý và caller inject OrderService:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder(Long orderId) {
        // đọc và cập nhật dữ liệu
    }
}
~~~

Khi một bean khác gọi orderService.placeOrder(...), lời gọi đi qua proxy. Proxy kiểm tra transaction metadata và điều phối transaction manager trước/sau khi gọi target method.

### 2.2. Self-invocation không đi qua proxy

Ví dụ dễ gây nhầm:

~~~java
@Service
public class ReportService {

    public void generateAll() {
        generateOne(); // lời gọi nội bộ qua this
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void generateOne() {
        // ghi dữ liệu báo cáo
    }
}
~~~

Khi caller gọi generateAll() qua proxy, proxy chỉ intercept generateAll. Bên trong target object, lời gọi generateOne() là lời gọi trực tiếp trên this. Nó không quay lại proxy, nên REQUIRES_NEW trên generateOne() không được áp dụng theo proxy mode mặc định.

Hệ quả: generateOne() có thể chạy không có transaction mới, hoặc chạy trong transaction đã có do generateAll() được gọi qua một transaction boundary khác. Không thể dựa vào annotation trên generateOne() để kết luận hành vi.

### 2.3. Cách sửa self-invocation

**Cách ưu tiên: tách transaction boundary sang bean khác.**

~~~java
@Service
public class ReportItemService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void generateOne(Long reportId) {
        // ghi một phần báo cáo trong transaction riêng
    }
}

@Service
public class ReportService {

    private final ReportItemService reportItemService;

    public ReportService(ReportItemService reportItemService) {
        this.reportItemService = reportItemService;
    }

    public void generateAll(List<Long> reportIds) {
        for (Long id : reportIds) {
            reportItemService.generateOne(id);
        }
    }
}
~~~

ReportService gọi một bean khác đã được proxy, vì vậy lời gọi generateOne() đi qua proxy.

Các lựa chọn khác:
- Dùng TransactionTemplate khi cần ranh giới transaction tường minh trong cùng một class.
- Dùng một bean tự tham chiếu qua proxy trong trường hợp đặc biệt, nhưng dễ làm code khó hiểu và có thể tạo vòng phụ thuộc.
- Dùng AspectJ weaving nếu dự án chủ động chọn cơ chế đó; AspectJ có thể intercept self-invocation, nhưng cần cấu hình và vận hành weaving riêng.

Không nên mặc định dùng AopContext.currentProxy() để giải quyết mọi self-invocation. Cách đó cần expose proxy và làm code phụ thuộc trực tiếp vào AOP context.

### 2.4. JDK dynamic proxy và CGLIB

Spring có thể tạo:
- **JDK dynamic proxy** dựa trên interface.
- **Class-based proxy (CGLIB)** tạo subclass của class mục tiêu.

Với JDK proxy, caller thường truy cập bean qua interface; method cần intercept phải có trên interface. Với class-based proxy, Spring tạo subclass, do đó không thể override/intercept private hoặc final method; class final cũng không thể được subclass theo cách này.

Để hành vi rõ ràng và ít phụ thuộc loại proxy, đặt @Transactional trên public service method được gọi từ bean khác. Kiểm tra loại proxy và cấu hình AOP của ứng dụng nếu có method visibility đặc biệt.

### 2.5. Những cách gọi thường bypass proxy

Các trường hợp sau cần chú ý:
- Một method gọi method khác trong cùng instance bằng this.
- Tự tạo object bằng new thay vì lấy bean từ Spring container.
- Gọi method trong constructor hoặc quá trình khởi tạo trước khi proxy sẵn sàng.
- Gọi private/final method không thể intercept theo class proxy.
- Caller giữ reference tới target object thay vì proxy.

Annotation hiện diện trong source code không chứng minh lời gọi runtime đã đi qua interceptor.

## 3. Cấu hình transaction trong Spring Boot và JPA

Spring Boot thường tự cấu hình transaction manager khi có Spring Data JPA, EntityManagerFactory và datasource phù hợp.

### 3.1. Các thành phần chính

- **@Transactional**: khai báo metadata cho transaction boundary.
- **TransactionInterceptor**: interceptor thực thi metadata.
- **PlatformTransactionManager**: điều phối transaction imperative.
- **JpaTransactionManager**: tích hợp transaction Spring với JPA EntityManager.
- **EntityManager**: quản lý persistence context và thay đổi entity.
- **JDBC Connection**: kết nối vật lý tới Oracle Database.
- **TransactionSynchronizationManager**: giữ thông tin transaction/resource gắn với thread trong mô hình imperative thông thường.

Khi transaction bắt đầu, JpaTransactionManager phối hợp với EntityManagerFactory và datasource để gắn EntityManager/connection phù hợp vào transaction context. Repository dùng cùng EntityManagerFactory và datasource có thể tham gia transaction hiện tại.

### 3.2. Ví dụ service layer

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void placeOrder(Long orderId, Long productId, int quantity) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        Inventory inventory = inventoryRepository.findByProductId(productId)
            .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        inventory.reserve(quantity);
        order.confirm();
    }
}
~~~

Nếu cả hai repository tham gia cùng JpaTransactionManager, thay đổi entity được quản lý trong cùng transaction. Nếu một thao tác ném exception thuộc rollback rule, transaction sẽ rollback.

### 3.3. Khi nào cần @EnableTransactionManagement?

Trong ứng dụng Spring Boot dùng auto-configuration tiêu chuẩn, transaction management thường được bật tự động theo cấu hình và dependency. Ứng dụng Spring thuần hoặc cấu hình đặc biệt có thể cần @EnableTransactionManagement.

Không thêm annotation này một cách máy móc nếu Boot đã cấu hình transaction infrastructure. Quan trọng là xác nhận có transaction manager và proxy thực sự được tạo.

### 3.4. Chọn transaction manager khi có nhiều datasource

Nếu ứng dụng có nhiều datasource hoặc nhiều EntityManagerFactory, cần chỉ rõ transaction manager:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder() {
    // thao tác với orders database
}
~~~

Tên qualifier phải trùng bean transaction manager được cấu hình. Nếu không chỉ rõ, Spring phải chọn manager mặc định hoặc có thể báo lỗi do không xác định được manager.

Một transaction manager JPA không tự động làm cho hai database độc lập commit nguyên tử cùng nhau. Muốn giao dịch phân tán cần giải pháp JTA/XA được cấu hình đúng; trong nhiều hệ thống, outbox/saga phù hợp hơn.

## 4. Propagation là gì?

Propagation mô tả cách một method có @Transactional tham gia khi caller đã có transaction hoặc chưa có transaction.

Propagation không quyết định proxy có intercept lời gọi hay không. Trước hết lời gọi phải đến transaction interceptor; sau đó propagation mới được áp dụng.

Spring định nghĩa các mode:
- REQUIRED
- REQUIRES_NEW
- SUPPORTS
- NOT_SUPPORTED
- MANDATORY
- NEVER
- NESTED

Mặc định của @Transactional là REQUIRED.

## 5. REQUIRED — tham gia transaction hiện có hoặc tạo transaction mới

REQUIRED là propagation mặc định và thường phù hợp với một use case nghiệp vụ.

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void createOrder() {
    // công việc nghiệp vụ
}
~~~

Hành vi:
- Nếu chưa có transaction: tạo transaction mới.
- Nếu đã có transaction tương thích: tham gia transaction hiện có.
- Method con không tạo physical transaction riêng khi join transaction bên ngoài.

### 5.1. Hai method REQUIRED cùng tham gia một transaction

~~~java
@Service
public class OrderService {

    private final InventoryService inventoryService;

    @Transactional
    public void placeOrder() {
        // transaction T1 bắt đầu
        inventoryService.reserve();
        // transaction T1 commit khi placeOrder kết thúc thành công
    }
}

@Service
public class InventoryService {

    @Transactional
    public void reserve() {
        // tham gia T1, không tạo T2
    }
}
~~~

Nếu reserve() thất bại theo rollback rule, transaction T1 có thể bị đánh dấu rollback-only. Dù OrderService bắt exception và tiếp tục, T1 vẫn có thể không commit được.

### 5.2. REQUIRED tạo logical scope, không nhất thiết tạo physical transaction mới

Mỗi method được intercept có thể có logical transaction scope riêng, nhưng các scope REQUIRED thường cùng tham gia một physical transaction. Vì vậy, rollback-only được đánh dấu trong scope con có thể ảnh hưởng toàn bộ physical transaction.

Đây là lý do một method ngoài bắt exception không bảo đảm transaction còn có thể commit.

### 5.3. Khi nào dùng REQUIRED?

Dùng khi nhiều bước cần thành công hoặc thất bại cùng nhau:
- Tạo order và order items.
- Trừ tồn kho cùng cập nhật trạng thái order.
- Ghi invoice và các dòng invoice.
- Cập nhật nhiều bảng thuộc một use case.
- Gọi nhiều repository cần cùng một commit.

## 6. REQUIRES_NEW — luôn tạo physical transaction mới

REQUIRES_NEW yêu cầu Spring tạo transaction độc lập. Nếu caller đã có transaction, transaction bên ngoài được suspend trong thời gian transaction mới chạy.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    // transaction độc lập
}
~~~

### 6.1. Sơ đồ

~~~text
Outer method
  |
  +--> Outer transaction T1 active
          |
          +--> call inner bean through proxy
                  |
                  +--> suspend T1
                  |
                  +--> begin T2
                  |
                  +--> execute inner method
                  |
                  +--> commit/rollback T2
                  |
                  +--> resume T1
  |
  +--> continue T1
  |
  +--> commit/rollback T1
~~~

### 6.2. T2 có thể commit dù T1 rollback

Ví dụ:
- T1 tạo order.
- T2 ghi audit record bằng REQUIRES_NEW và commit.
- Sau đó T1 gặp lỗi và rollback.

Audit record của T2 vẫn tồn tại vì nó đã commit độc lập. Đây là hành vi phù hợp nếu audit cần ghi nhận cả việc xử lý thất bại, nhưng không phù hợp nếu audit phải tồn tại đúng khi order được commit.

### 6.3. Connection pool có thể bị thiếu connection

Khi T1 đang giữ connection và bị suspend, T2 có thể cần một connection khác. Nếu nhiều thread đồng thời đều giữ connection T1 rồi cùng chờ connection thứ hai cho REQUIRES_NEW, pool có thể cạn connection.

Ví dụ, pool có 10 connection và 10 request đều đang ở outer transaction. Nếu cả 10 request đều gọi inner REQUIRES_NEW và cần thêm connection, chúng có thể chờ nhau tới timeout. Đặt pool size và concurrency theo số transaction lồng nhau, hoặc thiết kế lại boundary.

### 6.4. Lock conflict giữa T1 và T2

T1 có thể đang giữ row lock. Nếu T2 cố cập nhật chính row mà T1 đã khóa, T2 phải chờ T1 kết thúc. Nhưng T1 đang chờ T2 hoàn tất để tiếp tục. Kết quả có thể là chờ tới lock timeout hoặc tình huống tự chặn theo thiết kế.

Không dùng REQUIRES_NEW cho thao tác cập nhật cùng dữ liệu mà outer transaction đang giữ lock.

### 6.5. Persistence context của JPA

Transaction mới có persistence context/transactional resource được quản lý theo transaction manager. Khi T2 commit, dữ liệu database đã thay đổi độc lập; entity mà T1 đang giữ trong persistence context có thể trở nên stale. Sau khi T1 được resume, không giả định managed entity trong T1 tự cập nhật theo thay đổi của T2.

Nếu cần dữ liệu mới, cân nhắc refresh entity, clear/reload hoặc thiết kế để T1 không giữ trạng thái xung đột.

### 6.6. Khi nào dùng REQUIRES_NEW?

Phù hợp cho một số thao tác thực sự độc lập:
- Ghi audit độc lập với kết quả nghiệp vụ.
- Lưu trạng thái retry/failure cần tồn tại dù transaction ngoài rollback.
- Ghi nhận một đơn vị công việc độc lập trong batch.
- Cập nhật metric/bản ghi kỹ thuật mà yêu cầu commit riêng đã được xác định.

Không dùng chỉ để “chắc chắn commit”. Tách transaction làm thay đổi semantics nhất quán và có thể tạo bản ghi phụ tồn tại khi dữ liệu chính rollback.

## 7. NESTED — savepoint bên trong physical transaction

NESTED biểu diễn một transaction scope lồng nhau dựa trên savepoint nếu transaction manager hỗ trợ. Nó không giống REQUIRES_NEW.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalPart() {
    // có thể rollback về savepoint
}
~~~

### 7.1. Khác biệt chính

- NESTED thường dùng cùng physical transaction và tạo savepoint.
- REQUIRES_NEW suspend transaction ngoài và tạo physical transaction riêng.
- Rollback nested scope có thể quay về savepoint mà vẫn cho outer transaction tiếp tục.
- Commit nested scope không độc lập với outer commit; outer rollback vẫn rollback mọi thay đổi trong physical transaction.

### 7.2. Hỗ trợ phụ thuộc transaction manager

Không phải transaction manager nào cũng hỗ trợ nested transaction. DataSourceTransactionManager có thể hỗ trợ savepoint cho JDBC. JpaTransactionManager không cung cấp nested JPA persistence-context semantics đầy đủ; hỗ trợ savepoint cần cấu hình và thường chỉ có ý nghĩa với JDBC access trên connection.

Với JPA entity đã được thay đổi trong persistence context, rollback về JDBC savepoint không tự khôi phục trạng thái object Java trong EntityManager. Điều này có thể làm persistence context và database lệch nhau.

Vì vậy, không mặc định NESTED hoạt động như nested transaction đầy đủ trong JPA. Kiểm tra transaction manager, nestedTransactionAllowed, JDBC access và cách entity được quản lý trước khi dùng.

### 7.3. Khi nào cân nhắc NESTED?

- Dùng JDBC và cần rollback một phần về savepoint.
- Transaction manager được xác nhận hỗ trợ savepoint.
- Ứng dụng hiểu rõ phần thay đổi trong persistence context.
- Có test chứng minh trạng thái sau nested rollback.

Nếu chỉ cần một đơn vị commit độc lập, NESTED không thay thế REQUIRES_NEW.

## 8. SUPPORTS — tham gia nếu có transaction

SUPPORTS cho phép method tham gia transaction hiện có, nhưng không yêu cầu tạo transaction mới nếu chưa có.

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public List<Order> findOrders() {
    return orderRepository.findRecentOrders();
}
~~~

Hành vi:
- Có transaction bên ngoài: tham gia transaction đó.
- Không có transaction: chạy không có transaction thực sự; một số transaction synchronization có thể vẫn được bật tùy manager/configuration.

SUPPORTS thường dùng cho thao tác đọc có thể chạy trong hoặc ngoài transaction. Không dựa vào nó để bảo đảm atomicity cho các thao tác ghi khi caller không có transaction.

Nếu method cần một transaction mới để bảo đảm nhiều câu SQL nhất quán, dùng REQUIRED.

## 9. NOT_SUPPORTED — tạm suspend transaction hiện có

NOT_SUPPORTED yêu cầu method chạy ngoài transaction. Nếu caller có transaction, Spring suspend transaction đó trong thời gian method chạy.

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void exportLargeReport() {
    // chạy không có transaction bao quanh
}
~~~

Có thể dùng cho công việc:
- Xuất báo cáo lớn không cần một transaction database dài.
- Thực hiện một thao tác không nên giữ lock của transaction bên ngoài.
- Gọi một bước độc lập không cần tham gia transaction hiện tại.

Lưu ý: các repository call bên trong method vẫn có thể tự tạo transaction nếu chính repository/service được gọi có boundary riêng. NOT_SUPPORTED không có nghĩa mọi code downstream bị cấm tạo transaction.

Khi method kết thúc, transaction bên ngoài được resume.

## 10. MANDATORY — bắt buộc caller đã có transaction

MANDATORY yêu cầu phải có transaction hiện tại. Nếu không có, Spring ném IllegalTransactionStateException.

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void updateWithinUseCase() {
    // phải được gọi trong transaction đã có
}
~~~

Hữu ích cho một helper/service method chỉ có ý nghĩa khi là một phần của use case transaction lớn. Nó giúp phát hiện caller quên mở transaction.

Không dùng MANDATORY cho một service API được phép gọi độc lập từ nhiều nơi.

## 11. NEVER — cấm chạy khi có transaction

NEVER yêu cầu không có transaction hiện tại. Nếu caller đang có transaction, Spring ném IllegalTransactionStateException.

~~~java
@Transactional(propagation = Propagation.NEVER)
public void runOutsideTransaction() {
    // chỉ được gọi khi không có transaction
}
~~~

NEVER khác NOT_SUPPORTED:
- NEVER từ chối nếu caller có transaction.
- NOT_SUPPORTED suspend transaction caller và chạy không có transaction.

NEVER có thể hữu ích khi một thao tác không được phép chạy bên trong transaction theo thiết kế. Tuy nhiên, phải hiểu mọi caller và đường gọi trước khi áp dụng.

## 12. Bảng tổng hợp propagation

| Propagation | Có transaction hiện tại | Chưa có transaction |
| --- | --- | --- |
| REQUIRED | Tham gia transaction hiện tại | Tạo transaction mới |
| REQUIRES_NEW | Suspend transaction hiện tại, tạo transaction mới | Tạo transaction mới |
| NESTED | Tạo nested scope/savepoint nếu được hỗ trợ | Thường tạo transaction mới |
| SUPPORTS | Tham gia transaction hiện tại | Chạy không có transaction |
| NOT_SUPPORTED | Suspend transaction hiện tại, chạy ngoài transaction | Chạy ngoài transaction |
| MANDATORY | Tham gia transaction hiện tại | Ném exception |
| NEVER | Ném exception | Chạy ngoài transaction |

Bảng mô tả semantics tổng quát. Hành vi savepoint của NESTED và một số chi tiết synchronization phụ thuộc transaction manager.

## 13. Rollback rule mặc định

Trong Spring declarative transaction, mặc định:
- RuntimeException và subclass của nó: rollback.
- Error: rollback.
- Checked exception: không rollback theo mặc định.

Điều này thường gây ngạc nhiên vì Java cho phép method khai báo throws Exception nhưng Spring không tự hiểu mọi checked exception đều yêu cầu rollback.

### 13.1. Ví dụ checked exception

~~~java
@Transactional
public void importOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("File format invalid");
}
~~~

Theo rollback rule mặc định, IOException là checked exception nên transaction không nhất thiết rollback chỉ vì exception này. Nếu exception đi ra ngoài proxy, transaction có thể commit trước khi caller nhận exception.

### 13.2. Dùng rollbackFor

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    orderRepository.save(...);
    throw new IOException("File format invalid");
}
~~~

Hoặc với một checked business exception:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void capturePayment() throws PaymentRejectedException {
    // thao tác cần rollback khi payment bị từ chối
}
~~~

### 13.3. Dùng noRollbackFor

Nếu một exception cụ thể biểu thị kết quả nghiệp vụ mà vẫn muốn commit:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public void registerNotification() {
    // xử lý theo semantics đã định nghĩa
}
~~~

Chỉ dùng noRollbackFor khi dữ liệu sau exception vẫn nhất quán và việc commit là có chủ đích. Không vô hiệu hóa rollback chỉ để tránh lỗi.

### 13.4. Quy tắc mạnh nhất

Nếu có nhiều rollback rule cùng khớp, Spring chọn rule cụ thể/ưu tiên mạnh hơn theo quy tắc của transaction attribute. Nên khai báo class exception cụ thể thay vì dùng pattern string rộng, vì pattern có thể khớp ngoài ý muốn.

## 14. Bắt exception bên trong transaction

Việc bắt exception làm thay đổi điều kiện mà interceptor nhìn thấy.

### 14.1. Bắt exception và không ném lại

~~~java
@Transactional
public void processOrder() {
    try {
        repository.save(...);
        paymentService.record(...);
    } catch (RuntimeException ex) {
        log.error("Processing failed", ex);
    }
}
~~~

Nếu exception bị bắt và method trả về bình thường, interceptor có thể xem method thành công và commit. Nếu một nested REQUIRED scope đã đánh dấu transaction rollback-only, commit vẫn có thể thất bại.

### 14.2. Ném lại exception

~~~java
@Transactional
public void processOrder() {
    repository.save(...);
    paymentService.record(...);
}
~~~

Nếu RuntimeException đi ra khỏi method qua proxy, transaction interceptor áp dụng rollback rule mặc định.

### 14.3. Đánh dấu rollback-only

Trong một số trường hợp cần bắt exception để chuyển thành kết quả hoặc ghi log, nhưng vẫn muốn transaction rollback:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result processOrder() {
    try {
        repository.save(...);
        return Result.success();
    } catch (RuntimeException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return Result.failure(ex.getMessage());
    }
}
~~~

Đây là cách imperative gắn với transaction status hiện tại. Chỉ gọi khi đang ở transaction boundary được quản lý; không dùng nó để thay thế thiết kế exception rõ ràng.

### 14.4. UnexpectedRollbackException

Tình huống:
1. Outer method mở T1.
2. Inner REQUIRED method tham gia T1.
3. Inner method gặp RuntimeException và transaction bị đánh dấu rollback-only.
4. Outer method bắt exception, không ném tiếp.
5. Outer method kết thúc bình thường.
6. Spring thử commit T1 nhưng transaction đã rollback-only.

Caller có thể nhận UnexpectedRollbackException. Exception này báo rằng outer scope tưởng có thể commit nhưng physical transaction đã bị đánh dấu rollback-only từ trước.

Không cố bắt và bỏ qua UnexpectedRollbackException. Hãy xác định scope nào đánh dấu rollback-only và quyết định semantics đúng.

## 15. Transaction timeout, readOnly và isolation

Ngoài propagation, @Transactional có các thuộc tính điều khiển transaction.

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 30,
    readOnly = true
)
public List<Order> findRecentOrders() {
    return orderRepository.findRecentOrders();
}
~~~

### 15.1. Isolation

Isolation xác định cách transaction nhìn thấy thay đổi từ transaction khác. Với Oracle Database, các mức thường được dùng là READ COMMITTED và SERIALIZABLE. Oracle cung cấp read consistency theo statement ở READ COMMITTED; SERIALIZABLE cung cấp transaction-level consistency với các quy tắc riêng.

Spring isolation attribute thường chỉ có hiệu lực khi bắt đầu physical transaction mới. Nếu method tham gia transaction đã tồn tại, isolation được chọn ban đầu của transaction bên ngoài thường chi phối.

Có thể cấu hình validateExistingTransaction để từ chối một số trường hợp inner scope yêu cầu isolation/read-only khác transaction hiện tại, thay vì âm thầm bỏ qua khác biệt.

### 15.2. Timeout

Timeout là giới hạn thời gian transaction theo hỗ trợ của transaction manager và resource. Timeout không thay thế query timeout hoặc socket timeout. Một câu SQL có thể cần cấu hình timeout riêng ở JDBC/JPA.

Khi method join transaction hiện có, timeout của inner scope không tự tạo một bộ đếm transaction độc lập.

### 15.3. Read-only

readOnly=true là hint cho transaction manager/provider. Hibernate có thể tối ưu flush behavior hoặc giảm dirty checking trong một số cấu hình. Nó không phải lúc nào cũng là một hàng rào bảo mật ngăn mọi lệnh ghi ở database.

Nếu cần cấm ghi ở mức database, dùng quyền database hoặc cơ chế read-only được hỗ trợ và kiểm thử riêng.

### 15.4. Thuộc tính ở class và method

Có thể đặt @Transactional ở class để làm mặc định cho các method, rồi override ở method cụ thể. Method-level metadata có độ ưu tiên cao hơn class-level metadata tương ứng.

Nên ghi rõ propagation ở các method có semantics khác REQUIRED mặc định, đặc biệt là REQUIRES_NEW, NOT_SUPPORTED và MANDATORY.

## 16. JPA persistence context, flush và commit

JPA quản lý entity trong persistence context. Thay đổi object Java không nhất thiết được gửi ngay tới Oracle.

### 16.1. Dirty checking

Ví dụ:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
}
~~~

Entity đang managed. Khi flush, Hibernate/JPA phát hiện thay đổi và gửi SQL UPDATE. Không nhất thiết phải gọi repository.save(customer) cho entity managed.

### 16.2. Flush không phải commit

Flush đồng bộ thay đổi của persistence context xuống database connection. Nó không kết thúc transaction và không làm dữ liệu trở nên visible cho transaction khác như một commit.

~~~java
@Transactional
public void updateAndFlush(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName("New name");
    entityManager.flush(); // SQL được gửi, transaction vẫn mở
    // commit xảy ra khi method kết thúc qua proxy
}
~~~

Nếu sau flush có RuntimeException và transaction rollback, thay đổi SQL đã gửi vẫn có thể rollback.

### 16.3. Commit có thể phát hiện lỗi muộn

Constraint violation, deadlock hoặc lỗi ghi có thể xuất hiện ở flush/commit thay vì dòng save(). Vì interceptor commit sau khi method target trả về, exception có thể phát sinh khi caller tưởng method đã hoàn tất.

### 16.4. Persistence context và transaction

Persistence context có thể sống lâu hơn một câu SQL nhưng transaction boundary cần được thiết kế rõ. Tránh giữ entity managed qua nhiều request hoặc giữ transaction mở trong lúc xử lý chậm.

## 17. Transaction với Oracle Database

Spring điều phối transaction ở application layer; Oracle Database thực thi commit, rollback, lock và consistency ở server.

### 17.1. READ COMMITTED mặc định của Oracle

Oracle Database mặc định sử dụng READ COMMITTED. Mỗi câu SQL nhìn thấy dữ liệu đã commit tại thời điểm câu lệnh bắt đầu, cùng với các thay đổi của transaction hiện tại. Một transaction có thể thấy kết quả khác giữa hai câu SELECT nếu transaction khác commit xen giữa.

Điều này là read consistency theo statement, không phải một snapshot cố định cho toàn transaction.

### 17.2. Row lock được giữ tới kết thúc transaction

Các câu UPDATE/DELETE hoặc SELECT FOR UPDATE có thể giữ row lock cho tới commit hoặc rollback. Transaction dài làm lock tồn tại lâu, tăng nguy cơ blocking và deadlock.

Ví dụ:
- T1 cập nhật inventory row và chưa commit.
- T2 muốn cập nhật cùng row nên phải chờ.
- Nếu T1 gọi một dịch vụ chậm hoặc chờ HTTP trước commit, T2 bị block lâu hơn cần thiết.

Không gọi external API hoặc chờ thao tác người dùng trong khi đang giữ database transaction nếu có thể tránh.

### 17.3. DDL và implicit commit

Oracle DDL có semantics implicit commit. Các lệnh như CREATE, ALTER, DROP có thể commit transaction hiện tại theo quy tắc Oracle. Vì vậy, @Transactional không làm cho DDL trở thành thao tác có thể rollback cùng DML thông thường.

Không đặt schema migration hoặc DDL tùy tiện trong service method nghiệp vụ và kỳ vọng rollback hoàn toàn.

### 17.4. Connection phải thuộc cùng transaction manager

Nếu JPA và JdbcTemplate cùng dùng một DataSource và được tích hợp với transaction manager phù hợp, JDBC call có thể tham gia cùng transaction. Nếu tạo DriverManager connection riêng hoặc dùng datasource khác, call đó có thể nằm ngoài transaction JPA.

Không tự mở connection bằng DriverManager bên trong @Transactional rồi kỳ vọng nó tự join transaction của Spring.

## 18. Ranh giới transaction và external side effects

Transaction database chỉ bảo đảm atomicity cho resource được transaction manager điều phối. Nó không tự rollback:
- HTTP request tới payment provider.
- Email đã gửi.
- Message đã publish tới broker.
- File đã ghi ra filesystem.
- Lệnh gọi tới một microservice khác.

### 18.1. Vấn đề gửi message trước commit

Nếu service ghi order rồi gửi message trước khi commit:
- Message có thể được consumer xử lý.
- Sau đó database transaction rollback.
- Consumer nhìn thấy sự kiện cho order không tồn tại.

Nếu commit trước rồi gửi message:
- Database commit thành công.
- Ứng dụng crash trước khi gửi message.
- Sự kiện bị mất.

### 18.2. Transactional outbox

Một mẫu phổ biến:
1. Trong cùng database transaction, ghi business data và một outbox row.
2. Commit cả hai cùng nhau.
3. Worker đọc outbox và publish message.
4. Đánh dấu outbox row đã gửi.
5. Consumer xử lý idempotent để chịu được duplicate.

Outbox giữ việc tạo sự kiện nguyên tử với dữ liệu nghiệp vụ. Việc gửi message vẫn là eventual delivery và cần retry/idempotency.

### 18.3. AFTER_COMMIT event

Spring có @TransactionalEventListener với phase AFTER_COMMIT để xử lý một số side effect sau commit:

~~~java
@Component
public class OrderEventListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        // gửi notification sau khi transaction đã commit
    }
}
~~~

Listener AFTER_COMMIT tránh gửi notification trước khi transaction commit. Tuy nhiên, process có thể crash sau commit nhưng trước khi listener hoàn tất; nếu cần độ tin cậy cao, outbox thường phù hợp hơn.

Nếu listener cần ghi database trong transaction mới sau commit, có thể gọi một bean khác với REQUIRES_NEW. Phải bảo đảm lời gọi qua proxy và xử lý retry nếu side effect thất bại.

## 19. Transaction trong async và thread khác

Trong mô hình imperative thông thường, Spring gắn transaction resources với thread hiện tại. Transaction không tự động chuyển sang thread khác.

### 19.1. @Async không kế thừa transaction

~~~java
@Service
public class ImportService {

    @Transactional
    public void importBatch() {
        asyncWorker.processAsync();
    }
}

@Service
public class AsyncWorker {

    @Async
    public void processAsync() {
        // chạy trên thread khác
    }
}
~~~

Transaction của importBatch() không tự bao bọc processAsync(). Nếu async worker cần transaction, khai báo boundary ở method worker:

~~~java
@Async
@Transactional
public void processAsync() {
    // transaction riêng trên worker thread
}
~~~

### 19.2. CompletableFuture

Nếu method imperative mở transaction rồi trả về CompletableFuture, transaction thường kết thúc khi method trả về future, không chờ toàn bộ công việc async hoàn tất. Không coi transaction đã mở trên thread gọi là transaction của callback.

### 19.3. Reactive transaction

Reactive transaction manager thường giữ transaction context trong Reactor Context thay vì ThreadLocal. Dùng reactive transaction support và reactive database driver phù hợp; không trộn JPA imperative EntityManager với reactive transaction và kỳ vọng cùng transaction context.

## 20. Chọn propagation theo use case

| Nhu cầu | Lựa chọn thường xem xét | Lưu ý |
| --- | --- | --- |
| Nhiều bước nghiệp vụ phải commit/rollback cùng nhau | REQUIRED | Lựa chọn mặc định |
| Ghi audit độc lập dù transaction chính rollback | REQUIRES_NEW | Tốn connection riêng; cân nhắc outbox/audit policy |
| Một phần JDBC cần rollback về savepoint | NESTED | Cần transaction manager hỗ trợ; JPA persistence context có giới hạn |
| Đọc có thể tham gia transaction caller nhưng không bắt buộc tạo transaction | SUPPORTS | Không bảo đảm atomicity khi chạy độc lập |
| Chạy ngoài transaction hiện có | NOT_SUPPORTED | Transaction caller bị suspend |
| Helper bắt buộc caller đã mở transaction | MANDATORY | Báo lỗi sớm nếu caller quên boundary |
| Cấm gọi trong transaction | NEVER | Ném exception nếu có transaction |

Không chọn propagation chỉ dựa trên mong muốn “method này chạy riêng”. Hãy xác định:
- Dữ liệu nào phải commit cùng nhau?
- Khi outer transaction rollback, dữ liệu inner có được giữ không?
- Inner cần đọc dữ liệu outer chưa commit hay không?
- Có lock nào outer đang giữ không?
- Có đủ connection cho transaction lồng nhau không?
- Lời gọi có thực sự đi qua proxy không?

## 21. Ví dụ hoàn chỉnh: REQUIRED và REQUIRES_NEW

Giả sử hệ thống tạo order và ghi audit. Order phải rollback nếu inventory không đủ; audit failure có thể cần tồn tại để hỗ trợ điều tra.

~~~java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(Long orderId, String reason) {
        auditRepository.save(new AuditRecord(orderId, reason));
    }
}

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;
    private final AuditService auditService;

    public CheckoutService(
            OrderRepository orderRepository,
            InventoryService inventoryService,
            AuditService auditService) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
        this.auditService = auditService;
    }

    @Transactional
    public void checkout(Long orderId, Long productId, int quantity) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        try {
            inventoryService.reserve(productId, quantity);
            order.confirm();
        } catch (InsufficientInventoryException ex) {
            auditService.recordFailure(orderId, ex.getMessage());
            throw ex;
        }
    }
}
~~~

Trong ví dụ:
- checkout() mở T1 qua proxy.
- inventoryService.reserve() nếu REQUIRED sẽ tham gia T1.
- Nếu thiếu hàng, exception đi vào catch.
- auditService.recordFailure() đi qua bean proxy, suspend T1 và chạy T2.
- T2 commit audit record.
- Exception được ném lại, T1 rollback.
- Audit record T2 vẫn còn.

Đây là một semantics cụ thể. Nếu audit phải chỉ xuất hiện khi order commit hoặc cần đảm bảo gửi sự kiện bền vững, hãy dùng mô hình audit/outbox phù hợp thay vì mặc định REQUIRES_NEW.

## 22. Những lỗi thiết kế thường gặp

### 22.1. Đặt @Transactional trên private method

Proxy không thể intercept private method theo cơ chế proxy thông thường. Đặt annotation trên private method không tạo boundary độc lập như mong đợi.

### 22.2. Self-invocation với REQUIRES_NEW

Method cùng class gọi nhau bằng this. Annotation trên inner method không được proxy áp dụng. Tách bean hoặc dùng TransactionTemplate.

### 22.3. Bắt exception rồi nghĩ transaction đã rollback

Nếu exception bị bắt và method trả bình thường, transaction có thể commit. Quyết định rõ rethrow, setRollbackOnly hoặc chuyển thành kết quả nghiệp vụ có chủ đích.

### 22.4. Checked exception không rollback

IOException hoặc checked business exception không tự rollback theo mặc định. Dùng rollbackFor phù hợp.

### 22.5. REQUIRES_NEW quá nhiều

Có thể tiêu thụ connection thứ hai cho mỗi outer transaction, tăng tải database và gây lock conflict. Chỉ dùng khi thật sự cần commit độc lập.

### 22.6. NESTED với JPA nhưng kỳ vọng object tự quay lại trạng thái cũ

Rollback JDBC savepoint không tự undo thay đổi trong object Java đang managed. Cần hiểu giới hạn EntityManager/persistence context.

### 22.7. Transaction mở quá lâu

Giữ connection, row lock và undo lâu. Không đặt HTTP call, sleep, xử lý file lớn hoặc chờ user bên trong transaction nếu có thể tách.

### 22.8. Gọi database khác nhưng tưởng cùng transaction

Một datasource/transaction manager khác không tự tham gia transaction hiện tại. Cần JTA/XA hoặc pattern phân tán phù hợp.

### 22.9. Gọi method từ object được tạo bằng new

Object không do Spring quản lý không có transactional proxy. Annotation không tự có hiệu lực.

### 22.10. Kết luận transaction đã commit vì repository.save() trả về

JPA có thể trì hoãn SQL tới flush/commit. Lỗi constraint hoặc I/O có thể xuất hiện ở cuối transaction.

## 23. Kiểm thử transaction đúng cách

Test có thể che giấu lỗi transaction nếu chính test method cũng được đánh dấu @Transactional.

### 23.1. Test slice thường rollback transaction của test

@DataJpaTest thường chạy test trong transaction và rollback sau test. Nếu service method dùng REQUIRED, nó có thể join transaction của test. Test kết thúc rollback nên không chứng minh service đã commit độc lập.

### 23.2. Flush và clear khi kiểm tra JPA

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsOrder() {
        Order order = new Order();
        entityManager.persist(order);
        entityManager.flush();
        entityManager.clear();

        Order reloaded = orderRepository.findById(order.getId())
            .orElseThrow();

        assertThat(reloaded.getId()).isEqualTo(order.getId());
    }
}
~~~

flush gửi SQL xuống database; clear loại entity khỏi persistence context để lần đọc sau phải load lại. Tuy vậy, transaction test vẫn có thể rollback khi test kết thúc.

### 23.3. Kiểm tra commit thật

Nếu cần kiểm tra dữ liệu đã commit và có thể nhìn thấy từ transaction khác, có thể:
- Dùng test không chạy trong transaction để service mở/commit transaction riêng.
- Dùng TransactionTemplate và kết thúc transaction trước khi đọc từ connection khác.
- Dùng TestTransaction để kết thúc transaction test có kiểm soát.
- Mở transaction/connection mới để kiểm tra visibility.

Không chỉ gọi find() lần nữa trên cùng persistence context vì có thể đọc entity đang được cache trong first-level cache.

### 23.4. Test self-invocation

Viết test gọi method bên ngoài proxy và xác nhận inner REQUIRES_NEW có/không commit theo thiết kế. Kiểm tra bean được inject từ Spring context, không tự new target object.

### 23.5. Test rollback rule

Tạo các test riêng cho:
- RuntimeException.
- Checked exception không có rollbackFor.
- Checked exception có rollbackFor.
- Exception bị catch.
- Inner REQUIRED đánh dấu rollback-only.
- REQUIRES_NEW commit rồi outer rollback.
- NESTED savepoint nếu transaction manager hỗ trợ.

## 24. Dùng TransactionTemplate khi cần ranh giới tường minh

TransactionTemplate phù hợp khi:
- Cần nhiều transaction độc lập trong một method.
- Muốn boundary rõ ràng trong vòng lặp.
- Self-invocation làm proxy không phù hợp.
- Muốn kiểm soát chính xác đoạn code nằm trong transaction.

Ví dụ:

~~~java
@Service
public class BatchService {

    private final TransactionTemplate transactionTemplate;
    private final OrderRepository orderRepository;

    public BatchService(
            PlatformTransactionManager transactionManager,
            OrderRepository orderRepository) {
        this.transactionTemplate =
            new TransactionTemplate(transactionManager);
        this.orderRepository = orderRepository;
    }

    public void processBatch(List<Long> ids) {
        for (Long id : ids) {
            transactionTemplate.execute(status -> {
                Order order = orderRepository.findById(id)
                    .orElseThrow();
                order.process();
                return null;
            });
        }
    }
}
~~~

Mỗi lần execute tạo transaction theo propagation/isolation/timeout được cấu hình trên template. Có thể tạo template riêng và đặt propagation REQUIRES_NEW nếu batch cần transaction độc lập từng item.

Không dùng programmatic transaction chỉ vì annotation khó hiểu. Chọn cách biểu diễn boundary rõ ràng nhất cho use case.

## 25. Transaction trong batch và vòng lặp

Một transaction bao trùm batch lớn có thể:
- Giữ connection lâu.
- Giữ lock và undo lâu.
- Tạo persistence context lớn.
- Làm rollback tốn kém.
- Khi lỗi cuối batch, phải làm lại toàn bộ.

Có thể chia batch thành từng chunk hoặc từng item transaction nếu nghiệp vụ cho phép. Nhưng chia transaction thay đổi atomicity: một số item có thể commit trong khi item sau thất bại. Cần thiết kế checkpoint, retry, idempotency và trạng thái batch.

Ví dụ chunk transaction:
- Đọc danh sách ID theo page.
- Mỗi chunk đi qua một bean method có REQUIRED và được gọi từ bean bên ngoài.
- Commit chunk sau khi xử lý xong.
- Lưu progress/checkpoint trong transaction phù hợp.

Đừng gọi một method REQUIRES_NEW nội bộ cùng class để giả lập chunk transaction; proxy có thể bị bypass.

## 26. Quan sát transaction khi ứng dụng chạy

Để chẩn đoán, cần biết method nào đang mở transaction, transaction manager nào được chọn và SQL nào thực sự chạy trong boundary.

Có thể bật log có chọn lọc cho:
- org.springframework.transaction.interceptor
- org.springframework.orm.jpa
- org.springframework.jdbc.datasource
- org.hibernate.SQL
- org.hibernate.resource.transaction

Không bật SQL bind parameter logging chứa dữ liệu nhạy cảm trong production nếu chưa có chính sách bảo vệ log.

### 26.1. Kiểm tra transaction synchronization

Spring cung cấp TransactionSynchronizationManager cho một số chẩn đoán imperative:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
~~~

Đây là thông tin runtime hữu ích nhưng không nên dùng làm business logic phụ thuộc vào implementation detail. Reactive transaction có context khác.

### 26.2. Đọc trạng thái ở Oracle

DBA có thể quan sát session, SQL, lock và transaction từ các dynamic performance views như V$SESSION, V$TRANSACTION, V$LOCK và GV$SESSION trong RAC. Việc truy vấn cần quyền phù hợp.

Khi điều tra blocking:
- Xác định blocker và waiter.
- Xem SQL_ID, module, action và thời gian transaction.
- Kiểm tra ứng dụng có giữ transaction qua external call không.
- Xác định transaction nào cần commit/rollback theo nghiệp vụ.

## 27. Checklist thiết kế @Transactional

Trước khi thêm annotation, trả lời:

1. Use case cần atomicity nào?
2. Boundary nên đặt tại service method nào?
3. Lời gọi có đi qua Spring proxy không?
4. Method được gọi từ bean khác hay self-invocation?
5. Transaction manager nào quản lý resource?
6. Có nhiều datasource không?
7. Propagation có cần khác REQUIRED không?
8. Nếu inner method lỗi, outer transaction cần rollback hay tiếp tục?
9. Checked exception có cần rollbackFor không?
10. Exception có bị catch và nuốt không?
11. Có cần savepoint hay transaction độc lập?
12. REQUIRES_NEW có cần connection thứ hai không?
13. Có lock conflict với outer transaction không?
14. Có gọi HTTP, message broker hoặc filesystem trong transaction không?
15. Có chạy async hoặc đổi thread không?
16. Persistence context có thể giữ entity stale không?
17. Timeout/isolation/readOnly có đúng use case không?
18. Transaction có đủ ngắn không?
19. Test có thực sự kiểm tra commit/rollback không?
20. Có kiểm tra được trạng thái ở database khi cần không?

## 28. Bài tập tự luyện

1. Giải thích transaction boundary trong Spring.
2. Proxy làm gì trước và sau khi gọi target method?
3. Vì sao self-invocation bỏ qua transactional proxy?
4. Phân biệt JDK dynamic proxy và CGLIB proxy.
5. Vì sao private/final method không phù hợp làm transactional boundary qua class proxy?
6. Nêu vai trò của PlatformTransactionManager và JpaTransactionManager.
7. Vì sao service layer thường là nơi đặt transaction boundary?
8. Giải thích REQUIRED khi caller chưa có transaction.
9. Giải thích REQUIRED khi caller đã có transaction.
10. Vì sao inner REQUIRED có thể làm outer transaction rollback-only?
11. Phân biệt REQUIRES_NEW và NESTED.
12. Vì sao REQUIRES_NEW có thể cần connection thứ hai?
13. Mô tả lock conflict khi inner REQUIRES_NEW cập nhật row mà outer đang khóa.
14. Vì sao entity trong persistence context outer có thể stale sau inner commit?
15. Nêu điều kiện để NESTED hoạt động bằng savepoint.
16. Vì sao NESTED không đồng nghĩa nested JPA persistence context?
17. Phân biệt SUPPORTS và REQUIRED.
18. Phân biệt NOT_SUPPORTED và NEVER.
19. MANDATORY hữu ích trong trường hợp nào?
20. Spring rollback theo mặc định với loại exception nào?
21. Vì sao checked exception không tự rollback?
22. Viết ví dụ rollbackFor cho checked business exception.
23. Điều gì xảy ra nếu exception bị catch và không rethrow?
24. Giải thích UnexpectedRollbackException.
25. Isolation attribute có luôn áp dụng khi join transaction hiện có không?
26. readOnly=true có phải cơ chế bảo mật cấm ghi không?
27. Phân biệt JPA flush và database commit.
28. Vì sao Oracle DDL không rollback như DML?
29. Vì sao @Async không kế thừa imperative transaction của caller?
30. Thiết kế test chứng minh REQUIRES_NEW commit dù outer transaction rollback.

**@Transactional chỉ có hiệu lực khi lời gọi đi qua transaction interceptor; propagation sau đó quyết định method tham gia, tạo mới, suspend hay từ chối transaction hiện có.** Hãy đặt boundary tại service method đại diện cho use case, phân biệt REQUIRED với REQUIRES_NEW và NESTED, khai báo rollback rule theo exception nghiệp vụ, đồng thời kiểm tra self-invocation, connection pool, persistence context và external side effects. Với JPA trên Oracle, nhớ rằng flush không phải commit, lock được giữ tới khi transaction kết thúc và DDL có implicit commit.  


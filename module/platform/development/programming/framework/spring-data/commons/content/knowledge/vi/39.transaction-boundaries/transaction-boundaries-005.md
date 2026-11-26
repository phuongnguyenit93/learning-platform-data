# Proxy, self-invocation và phạm vi interceptor

## 1. Annotation không tự bao quanh mọi lần gọi phương thức

Trong chương **Ranh giới giao dịch** của **SPRING_DATA_COMMONS**, cần phân biệt abstraction repository, cơ chế transaction của Spring và khả năng giao dịch của từng store. Repository cung cấp cách truy cập dữ liệu; **@Transactional** cung cấp metadata để hạ tầng transaction xử lý. Việc có annotation trên mã nguồn chưa chứng minh lời gọi thực tế đã được interceptor xử lý.

Bài này xét **transaction theo Spring AOP proxy**. Trong mô hình đó, lời gọi phải đi qua proxy phù hợp và phương thức phải thuộc phạm vi có thể được chặn.

~~~text
Caller → Service proxy → TransactionInterceptor → Service đích
                                                       ↓
                                                Repository proxy
                                                       ↓
                                                  Store cụ thể
~~~

Một service tự gọi phương thức khác qua **this** sẽ không quay lại proxy của chính nó. Điều này giải thích nhiều trường hợp propagation hoặc rollback được khai báo nhưng không có hành vi như dự kiến.

Sau bài học, bạn cần phân biệt được:

- Lời gọi qua proxy với lời gọi trực tiếp trên target.
- Transaction bên ngoài đang tồn tại với metadata của phương thức tự gọi.
- Ranh giới use case ở service với ranh giới từng thao tác repository.
- Các giới hạn đến từ loại proxy, phương thức, thread và store.

## 2. Proxy, target và interceptor

### Target thực thi nghiệp vụ

Target là đối tượng chứa thân phương thức, chẳng hạn checkout, validateOrder và recordAttempt. Các phương thức này vẫn thực thi như mã Java thông thường.

### Proxy tiếp nhận lời gọi từ bên ngoài

Khi hạ tầng AOP được cấu hình phù hợp, Spring có thể cung cấp một proxy ở vị trí dependency mà thành phần khác sử dụng. Proxy áp dụng các advice tương ứng trước khi chuyển lời gọi tới target.

Nếu ứng dụng tự tạo service bằng **new**, đối tượng đó không tự trở thành một bean đã được áp dụng transaction advice.

### Interceptor quản lý phạm vi giao dịch

Với lời gọi đồng bộ, có thể hình dung hoạt động của TransactionInterceptor như sau:

~~~text
1. Xác định phương thức và metadata transaction hiệu lực.
2. Chọn transaction manager.
3. Bắt đầu, tham gia, tạm ngưng hoặc từ chối transaction theo propagation.
4. Gọi phương thức đích.
5. Xử lý kết quả hoặc exception theo quy tắc transaction.
6. Hoàn tất phạm vi transaction rồi trả kết quả cho caller.
~~~

Bước 3 không phải lúc nào cũng mở một transaction vật lý mới. REQUIRED có thể tham gia transaction hiện có; SUPPORTS có thể chạy mà không tạo transaction khi chưa có transaction phù hợp.

Một repository proxy có thể chứa nhiều interceptor phục vụ truy vấn và các tính năng khác. Việc thấy repository là proxy không chứng minh mọi store đều có cùng chính sách transaction mặc định.

## 3. Hai đường gọi phải phân biệt

### Gọi qua proxy

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant P as Service proxy
    participant I as TransactionInterceptor
    participant T as Service đích
    C->>P: checkout(...)
    P->>I: xử lý lời gọi
    I->>I: xác định transaction
    I->>T: checkout(...)
    T-->>I: kết quả hoặc exception
    I->>I: hoàn tất phạm vi transaction
    I-->>C: trả kết quả hoặc ném lỗi
~~~

Ở đây, interceptor có cơ hội áp dụng metadata của checkout trước khi thân phương thức chạy.

### Tự gọi trong target

~~~text
Caller
  → Proxy CheckoutService
    → Interceptor của checkout
      → CheckoutService đích
        → this.recordAttempt(...)
~~~

Lần gọi recordAttempt nằm bên trong target, không đi qua proxy của CheckoutService. Metadata trên recordAttempt không tự tạo thêm một lần xử lý transaction.

**Bỏ qua interceptor của phương thức tự gọi không có nghĩa transaction bên ngoài biến mất.** Nếu checkout đang chạy trong một transaction, các thao tác bên trong vẫn có thể dùng tài nguyên đang gắn với transaction đó.

## 4. Ví dụ: REQUIRES_NEW không được kích hoạt do self-invocation

Giả sử ứng dụng có hai repository:

~~~java
import org.springframework.data.repository.CrudRepository;

interface OrderRepository extends CrudRepository<PurchaseOrder, Long> {
}

interface AuditRepository extends CrudRepository<AuditEntry, Long> {
}
~~~

PurchaseOrder và AuditEntry là domain type đã được mapping theo store cụ thể. Các ví dụ trong bài tập trung vào đường gọi, không trình bày toàn bộ entity, schema và cấu hình ứng dụng.

Giả định minh họa: quản lý transaction đã được bật; service là Spring bean; repository được cấu hình đúng; các thao tác dùng tài nguyên do transaction manager phù hợp quản lý.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final AuditRepository audits;

    public CheckoutService(
            OrderRepository orders,
            AuditRepository audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public void checkout(PurchaseOrder order, AuditEntry attempt) {
        orders.save(order);
        recordAttempt(attempt);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(AuditEntry attempt) {
        audits.save(attempt);
    }
}
~~~

Kỳ vọng thường gặp là đơn hàng có một transaction, audit có transaction độc lập. Nhưng recordAttempt được tự gọi nên metadata REQUIRES_NEW của nó không được áp dụng trên đường gọi này.

Nếu caller gọi checkout qua proxy:

1. Interceptor của checkout thiết lập phạm vi transaction ngoài.
2. orders.save đi qua repository tương ứng.
3. recordAttempt chạy bằng một lời gọi Java nội bộ, tương đương this.recordAttempt.
4. Không có lần interceptor nội bộ để tạm ngưng transaction ngoài và mở transaction mới.
5. Nếu audits tham gia cùng tài nguyên transaction, việc ghi audit có thể nằm trong transaction của checkout.

Không nên mô tả kết quả là “self-invocation làm mất mọi transaction”. Điều bị bỏ qua là **ranh giới transaction khai báo cho phương thức nội bộ**.

### Nếu checkout không có transaction thì sao?

Bỏ annotation khỏi checkout vẫn không làm metadata trên recordAttempt được kích hoạt. Tuy nhiên, lời gọi audits.save vẫn có thể đi qua repository proxy riêng.

Tùy module và cấu hình, từng thao tác repository có thể có transaction riêng hoặc không có transaction như bạn dự kiến. Dù thế nào, không thể suy ra rằng toàn bộ use case đã được bao trong một transaction chỉ vì các phương thức repository đều chạy thành công.

## 5. Metadata nào bị bỏ qua trên lời gọi nội bộ?

| Khai báo trên phương thức được tự gọi | Kỳ vọng | Điều không tự xảy ra qua this |
| --- | --- | --- |
| REQUIRES_NEW | Mở transaction độc lập | Không tự tạm ngưng transaction ngoài để tạo ranh giới mới |
| NOT_SUPPORTED | Chạy ngoài transaction | Không tự tạm ngưng transaction đang có |
| MANDATORY | Bắt buộc phải có transaction | Không tự thực hiện kiểm tra propagation này |
| NEVER | Cấm có transaction | Không tự thực hiện kiểm tra propagation này |
| readOnly | Áp dụng cấu hình đọc | Không thiết lập phạm vi read-only mới từ annotation nội bộ |
| timeout hoặc isolation | Áp dụng thuộc tính của ranh giới thích hợp | Không được áp dụng chỉ nhờ lời gọi nội bộ |
| rollbackFor | Áp dụng chính sách rollback riêng | Không có interceptor nội bộ để xử lý exception theo metadata đó |

Ngay cả khi đi qua proxy, không phải mọi thuộc tính đều thay đổi được transaction đang tồn tại. Propagation, transaction manager, quy tắc kiểm tra cấu hình và store quyết định thuộc tính nào thực sự có tác dụng.

Read-only cũng không phải cam kết chung rằng mọi store sẽ cấm mọi lệnh ghi. Cách diễn giải và thực thi phụ thuộc hạ tầng dữ liệu.

### Exception vẫn có thể làm transaction ngoài rollback

Nếu recordAttempt được tự gọi rồi ném IllegalStateException thoát ra khỏi checkout, interceptor của checkout vẫn nhận exception đó và áp dụng chính sách rollback của **checkout**.

Đây không phải bằng chứng annotation trên recordAttempt đã hoạt động. Interceptor ở ranh giới ngoài đang xử lý exception thoát khỏi phương thức ngoài.

Nếu checkout bắt exception rồi trả về bình thường, interceptor ngoài không còn quan sát được exception đó theo cùng cách. Tuy nhiên, tài nguyên hoặc một lời gọi qua proxy khác có thể đã đánh dấu transaction rollback-only. Bắt exception không bảo đảm transaction vẫn commit được.

## 6. Loại proxy và phương thức quyết định phạm vi chặn

Spring có thể sử dụng proxy dựa trên interface hoặc proxy dựa trên class. Không nên suy ra loại proxy thực tế chỉ từ tên service hoặc việc class có annotation.

| Trường hợp | Giới hạn cần hiểu |
| --- | --- |
| Proxy dựa trên interface | Điểm vào phải thuộc interface mà proxy cung cấp |
| Proxy dựa trên class | Cơ chế subclass cần có khả năng ghi đè phương thức để áp dụng advice |
| Phương thức private | Không phải điểm vào được chặn bằng proxy AOP thông thường |
| Phương thức static | Không được áp dụng transaction advice như một lời gọi instance qua proxy |
| Phương thức final | Proxy dựa trên class không thể ghi đè để chặn phương thức đó |
| Class final | Không thể tạo proxy bằng cách kế thừa class; proxy interface là trường hợp khác |
| Protected hoặc package-private | Mức hỗ trợ phụ thuộc loại proxy và phiên bản/cấu hình; cần kiểm tra môi trường |

Lựa chọn dễ kiểm soát là đặt ranh giới transaction trên phương thức nghiệp vụ **public** của concrete Spring bean và gọi qua dependency được inject. Nếu dùng interface proxy, phương thức đó cần nằm trong interface được expose.

Đổi helper từ private thành public không sửa được self-invocation nếu lời gọi vẫn nằm trong cùng target.

### Vị trí đặt annotation

Đặt cấu hình transaction rõ trên implementation giúp việc đọc code và xác định ranh giới dễ hơn. Không nên giả định mọi kiểu proxy hoặc weaving đều xử lý annotation ở interface giống nhau.

Annotation cấp class có thể cung cấp mặc định; annotation ở phương thức có thể khai báo cấu hình cụ thể hơn cho phương thức thuộc phạm vi hỗ trợ. Cả hai cách đều không khiến lời gọi this tự quay lại proxy.

## 7. Sửa bằng cách tách ranh giới sang bean khác

Nếu audit thực sự cần transaction độc lập, có thể tách trách nhiệm sang AuditService.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final AuditRepository audits;

    public AuditService(AuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(AuditEntry attempt) {
        audits.save(attempt);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final AuditService auditService;

    public CheckoutService(
            OrderRepository orders,
            AuditService auditService) {
        this.orders = orders;
        this.auditService = auditService;
    }

    @Transactional
    public void checkout(PurchaseOrder order, AuditEntry attempt) {
        orders.save(order);
        auditService.recordAttempt(attempt);
    }
}
~~~

Khi auditService là bean được inject với proxy phù hợp, lời gọi đi qua proxy của AuditService và interceptor có cơ hội áp dụng REQUIRES_NEW.

~~~text
Proxy CheckoutService
  → Transaction ngoài
    → CheckoutService đích
      → Proxy AuditService
        → Interceptor của recordAttempt
          → Transaction audit độc lập nếu được hỗ trợ
~~~

### Transaction độc lập thay đổi ý nghĩa nghiệp vụ

REQUIRES_NEW không chỉ là một cách làm annotation “có tác dụng”. Nó thay đổi quan hệ commit:

- Audit có thể commit rồi đơn hàng rollback.
- Exception từ audit truyền ra ngoài vẫn có thể làm transaction đơn hàng rollback theo chính sách ngoài.
- Audit có thể không đọc được đơn hàng chưa commit.
- Khóa ngoại từ audit đến đơn hàng chưa commit có thể gây lỗi hoặc chờ theo hành vi của store.
- Transaction ngoài có thể vẫn giữ tài nguyên trong khi transaction trong cần tài nguyên khác, làm tăng nhu cầu kết nối và nguy cơ chờ.

Trong ví dụ, attempt nên biểu diễn một lần thử có định danh độc lập, không mặc định phụ thuộc vào bản ghi đơn hàng chưa commit.

Nếu audit phải xác nhận một đơn hàng **đã commit**, cần thiết kế cơ chế sau commit hoặc outbox phù hợp. Audit được ghi bằng transaction độc lập không tự chứng minh giao dịch đơn hàng đã thành công.

Nếu yêu cầu là cả đơn hàng và audit phải rollback cùng nhau, một transaction ngoài và helper nội bộ có thể chính là thiết kế đúng. Không chọn REQUIRES_NEW chỉ để tránh self-invocation.

## 8. Khi self-invocation là cách tổ chức hợp lý

Self-invocation chỉ gây vấn đề khi bạn trông chờ metadata riêng trên phương thức nội bộ được interceptor áp dụng.

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;

    public CheckoutService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void checkout(PurchaseOrder order) {
        validate(order);
        persist(order);
    }

    private void validate(PurchaseOrder order) {
        // Kiểm tra nghiệp vụ thuần Java.
    }

    private void persist(PurchaseOrder order) {
        orders.save(order);
    }
}
~~~

Validate và persist ở đây chỉ là các bước triển khai use case, không yêu cầu interceptor riêng. Thao tác repository có thể tham gia transaction ngoài theo cấu hình store và tài nguyên.

Ranh giới được diễn đạt rõ: một lời gọi nghiệp vụ công khai tương ứng với phạm vi nhất quán mong muốn. Không cần gắn annotation lên mọi helper.

## 9. Quản lý transaction theo chương trình

Khi cần một ranh giới ngay trong thuật toán, có thể dùng TransactionTemplate thay cho việc dựa vào method interception.

Ví dụ imperative sau cần PlatformTransactionManager phù hợp. Nếu có nhiều manager, phải chọn đúng manager bằng cấu hình hoặc qualifier.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class AuditWriter {

    private final AuditRepository audits;
    private final TransactionTemplate auditTransaction;

    public AuditWriter(
            AuditRepository audits,
            PlatformTransactionManager transactionManager) {
        this.audits = audits;
        this.auditTransaction = new TransactionTemplate(transactionManager);
        this.auditTransaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public void recordAttempt(AuditEntry attempt) {
        auditTransaction.executeWithoutResult(status -> {
            audits.save(attempt);
        });
    }
}
~~~

Ranh giới được thiết lập khi template thực thi callback, không phụ thuộc recordAttempt có được transaction advice chặn hay không. Một helper nội bộ cũng có thể dùng template nếu đó là cấu trúc chương trình phù hợp.

Template vẫn chịu giới hạn của manager và store. Nó không tự tạo transaction phân tán hoặc khiến hai tài nguyên khác nhau trở nên nguyên tử.

| Cách tiếp cận | Trường hợp phù hợp | Điều cần kiểm soát |
| --- | --- | --- |
| Một transaction ở phương thức service ngoài | Một use case cần cùng commit/rollback | Tài nguyên và repository phải tham gia phù hợp |
| Tách bean | Có trách nhiệm riêng cần interceptor riêng | Propagation phải phản ánh đúng nghiệp vụ |
| TransactionTemplate | Cần chỉ rõ một khối mã có transaction | Code phụ thuộc trực tiếp hơn vào API transaction |
| AspectJ weaving | Hệ thống chủ động sử dụng weaving | Cần hạ tầng weaving và cách kiểm chứng tương ứng |

AspectJ weaving có thể áp dụng advice ở những đường gọi khác với proxy AOP, bao gồm self-invocation khi được cấu hình đúng. Gắn annotation thông thường không có nghĩa ứng dụng đã dùng weaving.

Tự inject chính bean hoặc truy xuất proxy hiện hành có thể xuất hiện trong một số thiết kế, nhưng tăng phụ thuộc vào chi tiết AOP. Trước khi dùng, hãy xác định ranh giới đó có thể được diễn đạt rõ bằng service riêng hoặc template hay không.

## 10. Repository proxy không thay thế ranh giới use case

Trong Spring Data Commons, cần giữ rõ các vai trò:

~~~text
Service:     điều phối use case và phạm vi nhất quán mong muốn.
Repository:  truy cập aggregate hoặc dữ liệu theo abstraction của module.
Store:       quyết định khả năng transaction và quy tắc dữ liệu thực tế.
~~~

Xét một use case:

~~~text
1. Đọc khách hàng.
2. Tạo đơn hàng.
3. Cập nhật trạng thái liên quan.
~~~

Nếu mỗi thao tác repository có transaction riêng, bước 2 có thể đã commit trước khi bước 3 thất bại. Không có gì bảo đảm toàn bộ chuỗi là một đơn vị nguyên tử nếu thiếu transaction ngoài phù hợp.

Đặt transaction ở service giúp diễn đạt ranh giới, nhưng cần kiểm tra thêm:

- Module repository có tham gia loại transaction được chọn không.
- Repository dùng đúng datasource, session hoặc resource mà manager quản lý không.
- Có nhiều store hoặc nhiều manager trong cùng đường gọi không.
- Isolation và cơ chế khóa có đáp ứng yêu cầu cạnh tranh không.

Ngay cả một transaction bao quanh cả ba bước cũng không tự loại bỏ mọi race condition hoặc bảo đảm mọi quy tắc nghiệp vụ.

Hành vi mặc định của repository JPA không phải hợp đồng chung cho mọi repository document, graph hoặc reactive chỉ vì chúng cùng dùng abstraction Spring Data.

## 11. Phạm vi thời gian: thân phương thức kết thúc trước bước commit

Với transaction do proxy mở cho phương thức ngoài, thân phương thức có thể đã trả về bình thường nhưng caller vẫn nhận exception khi interceptor thực hiện commit.

~~~text
checkout bắt đầu
  → gọi repository.save
  → chạy đến cuối thân checkout
  → interceptor hoàn tất transaction
  → commit có thể phát sinh lỗi
  → caller nhận kết quả hoặc exception
~~~

Một try/catch đặt quanh save bên trong service có thể không bắt được lỗi chỉ xuất hiện ở commit sau khi phương thức đích trả về.

Log “thành công” ở cuối thân phương thức không đủ để chứng minh dữ liệu đã commit. Cần quan sát kết quả lời gọi qua proxy và hành vi transaction thực tế.

### Hai phạm vi logical tham gia cùng transaction

Xét đường gọi qua **hai bean và hai proxy**:

~~~text
OuterService.outer [REQUIRED]
  → InnerService.inner [REQUIRED]
      → ném RuntimeException
  → outer bắt exception và tiếp tục
~~~

Trong cấu hình tham gia transaction chung thông thường, interceptor của inner có thể đánh dấu transaction chung là rollback-only. Khi outer đến commit, caller có thể nhận UnexpectedRollbackException theo cơ chế manager vì transaction không thể commit bình thường.

Điều này khác với outer tự gọi helper cùng class: khi self-invocation, không có interceptor nội bộ để áp dụng metadata của helper. Tuy nhiên, tài nguyên vẫn có thể chuyển sang trạng thái lỗi, nên không được suy ra rằng bắt exception luôn cứu được transaction.

Theo chính sách rollback mặc định thường dùng của Spring, RuntimeException và Error dẫn đến rollback; checked exception cần quy tắc phù hợp nếu muốn rollback. Annotation, cấu hình chung và manager có thể làm chính sách hiệu lực khác đi.

## 12. Thread, async và reactive làm thay đổi phạm vi ngữ cảnh

### Imperative transaction thường gắn với thread

Trong mô hình imperative thông thường, ngữ cảnh transaction liên kết với thread. Chuyển việc sang executor không tự truyền transaction hiện tại.

~~~java
@Transactional
public void checkout(PurchaseOrder order) {
    orders.save(order);

    executor.execute(() -> {
        // Không tự kế thừa transaction của checkout.
        processLater(order);
    });
}
~~~

Lambda gọi helper cùng target cũng không tự đi qua proxy. Nếu công việc nền cần transaction, cần một điểm vào được quản lý hoặc API transaction theo chương trình phù hợp.

Ngoài ranh giới transaction, phải xác định dữ liệu đã commit hay chưa. Công việc nền có thể bắt đầu trước khi transaction của caller hoàn tất.

Nếu dùng @Async, còn phải xem lời gọi có đi qua async proxy không và advice được cấu hình thế nào. Hai annotation đặt cạnh nhau chưa đủ chứng minh đường gọi thực tế.

### Reactive transaction dùng ngữ cảnh của pipeline

Reactive transaction dùng ngữ cảnh reactive và manager tương ứng thay vì thread-local theo cách imperative. Một phương thức trả publisher cần được đánh giá cùng thời điểm subscription và pipeline thực sự được thực thi.

Self-invocation vẫn ảnh hưởng việc metadata có đi qua proxy hay không. Tuy nhiên, đi qua proxy chỉ là một phần: công việc còn phải thuộc pipeline và phạm vi reactive transaction phù hợp.

Không tạo subscription rời rạc bên trong service rồi giả định mọi thao tác đều thuộc cùng transaction. TransactionTemplate imperative cũng không phải công cụ thay thế tương đương cho quản lý transaction reactive.

## 13. Những điểm vào dễ bị hiểu nhầm

| Tình huống | Nguyên nhân dễ sai | Hướng xử lý |
| --- | --- | --- |
| Tự new service rồi gọi | Đối tượng không tự có transaction proxy | Gọi bean được quản lý hoặc chủ động dùng API transaction |
| Annotation trên helper private | Proxy AOP không chặn helper đó | Đặt ranh giới ở phương thức public hoặc dùng template |
| Đổi helper thành public | Self-invocation vẫn không qua proxy | Thay đổi đường gọi nếu cần interceptor riêng |
| Đổi inner() thành this.inner() | Hai cách đều là lời gọi nội bộ | Không coi thay đổi cú pháp là thay đổi ranh giới |
| Gọi transactional helper từ @PostConstruct cùng bean | Callback khởi tạo không phải điểm vào thông thường qua proxy hoàn chỉnh | Dùng tác vụ sau khởi tạo gọi sang bean transactional phù hợp |
| Có annotation nhưng thiếu hạ tầng transaction | Metadata không tự cấu hình manager | Kiểm tra cơ chế kích hoạt và manager được chọn |
| Có proxy nhưng không có metadata hiệu lực | Proxy có thể phục vụ tính năng khác | Kiểm tra advisor và method thực sự được gọi |
| Dùng manager của store A để ghi store B | Không cùng resource transaction chỉ vì ở cùng service | Đối chiếu manager với tài nguyên của từng repository |

@EnableTransactionManagement có thể bật hạ tầng annotation-driven trong ứng dụng cấu hình tường minh; một số môi trường có cơ chế cấu hình tự động. Trong cả hai trường hợp vẫn phải có manager phù hợp và khả năng tham gia transaction của store.

## 14. Xác minh ranh giới bằng đường gọi và dữ liệu

Khi cần đánh giá một trường hợp cụ thể:

1. Xác định caller nhận bean từ Spring hay tự tạo đối tượng.
2. Vẽ đường gọi, đánh dấu service proxy, repository proxy và self-invocation.
3. Kiểm tra method có thuộc interface và phạm vi có thể được proxy chặn không.
4. Xác định metadata hiệu lực, propagation và manager.
5. Đối chiếu manager với tài nguyên mà repository sử dụng.
6. Quan sát begin, join, suspend, rollback và commit bằng log hạ tầng thích hợp.
7. Kiểm tra dữ liệu sau khi lời gọi đã hoàn tất, thay vì chỉ kiểm tra thân phương thức.

Các tình huống kiểm chứng có ý nghĩa:

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Gọi từ bean khác qua proxy | Interceptor tham gia đúng điểm vào |
| Tự gọi method gắn REQUIRES_NEW | Không có transaction độc lập chỉ nhờ metadata nội bộ |
| Chuyển lời gọi sang bean khác | Propagation được áp dụng đúng theo manager và yêu cầu |
| Ném lỗi sau thao tác lưu | Dữ liệu rollback hoặc còn lại đúng theo ranh giới |
| Lỗi khi commit | Caller nhận thất bại dù thân phương thức đã kết thúc |
| Chuyển việc qua executor | Không nhầm transaction của caller với transaction công việc nền |

Khi viết integration test, tránh để transaction của chính test vô tình cung cấp ngữ cảnh mà production không có. Test gọi trực tiếp target hoặc bao toàn bộ trường hợp trong transaction có thể che mất lỗi proxy hoặc ranh giới service.

Phép kiểm chứng cần phản ánh cả đường gọi và thời điểm xác nhận dữ liệu của tình huống thực tế. Không nên dùng một kiểm tra “transaction đang active” làm bằng chứng duy nhất rằng propagation độc lập đã hoạt động.

## 15. Bài tập áp dụng

Cho use case tạo đơn hàng, ghi audit về một lần thử và cập nhật dữ liệu liên quan:

1. Vẽ đường gọi hiện tại, phân biệt proxy và target.
2. Chỉ ra metadata nào được interceptor xử lý và metadata nào nằm trên self-invocation.
3. Xác định audit phải commit cùng đơn hàng hay được phép tồn tại sau khi đơn hàng rollback.
4. Chọn một transaction ngoài, service riêng hoặc template theo yêu cầu đó.
5. Giải thích kết quả khi audit lỗi, đơn hàng lỗi và commit lỗi.
6. Xác định manager, repository và resource của từng bước.
7. Nếu có công việc bất đồng bộ, xác định transaction riêng và điều kiện dữ liệu sẵn sàng.

Thiết kế đúng cần giải thích được cả đường gọi lẫn kết quả commit/rollback. Annotation thể hiện ý định cấu hình; hiệu lực thực tế cần interceptor xử lý đúng lời gọi và store hỗ trợ phạm vi transaction đã chọn.

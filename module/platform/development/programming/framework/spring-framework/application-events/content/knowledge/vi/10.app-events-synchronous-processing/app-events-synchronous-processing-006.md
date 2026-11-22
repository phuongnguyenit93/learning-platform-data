# Khi đồng bộ là lựa chọn đúng trong Spring Framework Application Events

## 1. Đồng bộ có ý nghĩa gì khi phát Application Event?

Trong Spring Framework, **ApplicationEventPublisher.publishEvent(event)** gửi một sự kiện đến cơ chế phân phối **ApplicationEventMulticaster** của **ApplicationContext**. Các bean nhận sự kiện có thể dùng **@EventListener**, hoặc triển khai **ApplicationListener**.

Với cấu hình mặc định của **SimpleApplicationEventMulticaster**, listener chạy **đồng bộ trên chính thread gọi publishEvent(...)**. Điều này có ba hệ quả quan trọng:

1. Thread phát sự kiện phải chờ listener đồng bộ hiện tại chạy xong rồi mới tiếp tục; khi **publishEvent(...)** trả về bình thường, các listener đồng bộ đã được gọi và hoàn tất theo cơ chế phân phối đó.
2. Listener có thể nhìn thấy thread context của publisher, bao gồm một transaction gắn với thread khi có transaction đang hoạt động và không bị chuyển sang luồng khác.
3. Nếu listener ném exception chưa được xử lý, mặc định exception quay về publisher; quá trình phân phối hiện tại có thể dừng trước khi gọi listener tiếp theo.

**Lưu ý về hợp đồng API:** bản thân giao diện **ApplicationEventPublisher** không cam kết mọi implementation phải chạy đồng bộ. Các nhận định trên áp dụng cho **SimpleApplicationEventMulticaster mặc định** với listener không dùng **@Async**, không gắn executor bất đồng bộ và không cài **ErrorHandler** thay đổi cách lan truyền lỗi. Khi tự cấu hình multicaster, phải đánh giá lại hành vi thực tế.

Đồng bộ là một *cách phối hợp thực thi*: nó không tự bảo đảm giao dịch, không tự retry, không tự bảo đảm dữ liệu được commit và cũng không biến một lời gọi HTTP hay gửi email thành thao tác có thể rollback.

## 2. Dấu hiệu cho thấy nên chọn xử lý đồng bộ

### 2.1. Phải trả lời thành công hay thất bại ngay tại chỗ

Đây là tiêu chí mạnh nhất. Nếu một listener kiểm tra điều kiện bắt buộc và lỗi của nó phải làm thao tác hiện tại thất bại, chạy đồng bộ giúp caller nhận exception ngay.

Ví dụ:

- Yêu cầu duyệt hóa đơn phải bị từ chối nếu vượt hạn mức.
- Yêu cầu kích hoạt tài khoản phải bị từ chối nếu thiếu điều kiện pháp lý bắt buộc.
- Một thay đổi cấu hình nội bộ phải kiểm tra đầy đủ các bất biến trước khi công bố là đã áp dụng.

Đường đi mong muốn:

~~~text
Caller
  -> service xử lý yêu cầu
     -> publishEvent(CheckRequested)
        -> listener kiểm tra (đồng bộ)
           -> hợp lệ: return
           -> không hợp lệ: throw
     -> tiếp tục hoặc xử lý lỗi ngay trong cùng call stack
~~~

Nếu listener được đưa sang executor với **@Async**, caller có thể tiếp tục trước khi kiểm tra hoàn tất. Exception trong listener bất đồng bộ không tự quay về lời gọi **publishEvent(...)**, khiến nghiệp vụ có nguy cơ báo thành công quá sớm.

**Giới hạn thiết kế:** nếu bước kiểm tra là điều kiện cốt lõi của nghiệp vụ, thường nên gọi **validationService.validate(...)** trực tiếp trước khi phát event. Listener đồng bộ hợp lý hơn khi có nhu cầu tách các thành phần quan sát cùng một sự kiện nhưng vẫn cần phản hồi lỗi ngay và có hợp đồng lỗi rõ ràng.

### 2.2. Cần cùng transaction để duy trì tính nhất quán cục bộ

Một **@EventListener** đồng bộ được gọi khi thread phát event vẫn đang ở bên trong phương thức **@Transactional** sẽ chạy trong cùng thread context. Khi listener dùng cùng transaction manager, cùng tài nguyên dữ liệu và cách lan truyền phù hợp, các thao tác DB có thể cùng tham gia giao dịch hiện tại.

Ví dụ: service tạo một bản ghi nghiệp vụ và listener thêm một bản ghi audit **bắt buộc ở cùng cơ sở dữ liệu**. Nếu audit ghi không thành công, nghiệp vụ không được commit. Listener đồng bộ cho phép lỗi đó lan về transaction boundary.

Tuy nhiên, chỉ cùng thread chưa đủ để bảo đảm atomicity: transaction phải thật sự đang hoạt động; lời gọi repository phải được cấu hình tham gia transaction; và loại exception phải dẫn tới rollback theo quy tắc đang áp dụng. Mặc định **@Transactional** rollback với **RuntimeException** và **Error**; checked exception cần cấu hình phù hợp như **rollbackFor** nếu muốn rollback.

Nếu caller bắt exception rồi trả về bình thường ngay trong transaction, giao dịch có thể vẫn commit. Vì vậy, không được “nuốt” lỗi của listener bắt buộc.

### 2.3. Kết quả phải được quan sát trước bước kế tiếp

Một số side effect **nhanh, nội bộ và xác định** phải hoàn tất trước khi đọc dữ liệu hoặc phát một sự kiện tiếp theo.

Ví dụ:

- Cập nhật một cấu trúc tra cứu trong bộ nhớ theo yêu cầu nghiệp vụ trước khi service truy vấn nó.
- Gửi thông báo nội bộ đến nhiều thành phần để kiểm tra cấu hình mới; caller chỉ tiếp tục khi tất cả thành phần đồng bộ cần thiết đã hoàn tất.
- Ghi một audit record bắt buộc cùng transaction trước khi phương thức nghiệp vụ trả về.

Với mô hình này, **@Order** có thể diễn đạt thứ tự *gọi* các listener của cùng event, nhưng khi B thực sự phụ thuộc giá trị trả về của A, dùng chuỗi gọi service trực tiếp thường dễ kiểm soát hơn. Event không phù hợp để truyền kết quả tuần tự giữa các listener như một pipeline có đầu ra bắt buộc.

### 2.4. Công việc nhỏ, có giới hạn thời gian và phụ thuộc thấp

Đồng bộ là lựa chọn hợp lý khi listener làm việc nhanh và có thời gian chạy dự kiến ổn định: kiểm tra điều kiện tại chỗ, cập nhật trạng thái cục bộ hoặc ghi dữ liệu nhỏ trong cùng transaction.

Ngược lại, công việc I/O không đoán trước như gửi email, gọi API bên ngoài, truy vấn dịch vụ chậm hay chạy một báo cáo dài dễ kéo dài thời gian giữ transaction/lock và tăng độ trễ phản hồi. Dùng đồng bộ cho chúng chỉ khi caller thực sự cần chờ kết quả và đã có chính sách timeout, retry, idempotency và kiểm soát lỗi rõ ràng.

## 3. Bảng chọn nhanh giữa ba cách thực hiện

| Nhu cầu | Cách nên cân nhắc | Lý do |
| --- | --- | --- |
| Phải có kết quả kiểm tra để quyết định có thực hiện nghiệp vụ hay không | Gọi service đồng bộ trực tiếp | Luồng điều khiển, dữ liệu trả về và exception rõ ràng |
| Nhiều thành phần cùng phản ứng với event; mọi phản ứng là điều kiện để thao tác thành công | **@EventListener** đồng bộ, hợp đồng lỗi rõ | Publisher chờ hoàn tất và nhận exception theo cấu hình mặc định |
| Một phản ứng cục bộ phải ghi trong cùng DB transaction | Listener đồng bộ hoặc gọi service trực tiếp bên trong transaction | Có thể chia sẻ transaction khi cấu hình đúng |
| Chỉ được gửi thông báo khi transaction commit thành công | **@TransactionalEventListener(AFTER_COMMIT)** | Tránh phản ứng với thay đổi cuối cùng bị rollback |
| Thông báo không cần hoàn tất trước phản hồi | AFTER_COMMIT kết hợp **@Async** hoặc worker riêng | Tách độ trễ xử lý phụ ra khỏi đường trả lời chính |
| Không được làm mất công việc dù tiến trình chết | **Transactional outbox** + worker/queue | Spring event trong bộ nhớ không phải hàng đợi bền vững |
| Bước B phụ thuộc dữ liệu trả về trực tiếp của bước A | Gọi A rồi B trong service | **@Order** chỉ điều khiển thứ tự gọi listener, không trao đổi kết quả |
| Cần phản hồi nhanh, listener có thể mất vài giây hoặc gọi dịch vụ ngoài | Xem xét bất đồng bộ/saga/job có trạng thái | Tránh giữ request thread hoặc transaction quá lâu |

Đừng dùng quy tắc đơn giản “quan trọng thì đồng bộ, không quan trọng thì bất đồng bộ”. Một việc **phải hoàn thành về sau** nhưng không cần xong trước phản hồi vẫn là việc quan trọng; nó cần lưu bền vững, retry và kiểm tra kết quả thay vì chỉ dùng **@Async**.

## 4. Ví dụ Java 17+: lỗi của listener được trả về publisher

Ví dụ dùng **Spring Framework 6.2.9** với cấu hình mặc định, không cài executor tùy biến, không dùng **@Async** và không mở database transaction. Mục đích là chứng minh chính xác: listener chạy trước khi **publishEvent(...)** trả về; listener có order sớm hơn ném lỗi sẽ ngăn listener đến sau trong lần phân phối đó.

Cấu trúc dự án:

~~~text
sync-event-demo/
  build.gradle
  src/main/java/demo/SyncDecisionDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.SyncDecisionDemo'
}
~~~

**src/main/java/demo/SyncDecisionDemo.java**:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class SyncDecisionDemo {

    public record InvoiceApprovalRequested(String invoiceId, int amount) {}

    public static class LimitGuard {
        @EventListener
        @Order(10)
        public void validate(InvoiceApprovalRequested event) {
            System.out.println("guard: " + event.invoiceId());
            if (event.amount() > 1_000) {
                throw new IllegalArgumentException("exceeded demo limit");
            }
        }
    }

    public static class LocalAudit {
        @EventListener
        @Order(20)
        public void record(InvoiceApprovalRequested event) {
            System.out.println("audit: " + event.invoiceId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        LimitGuard limitGuard() {
            return new LimitGuard();
        }

        @Bean
        LocalAudit localAudit() {
            return new LocalAudit();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("caller: begin INV-1");
            context.publishEvent(new InvoiceApprovalRequested("INV-1", 500));
            System.out.println("caller: completed INV-1");

            System.out.println("caller: begin INV-2");
            try {
                context.publishEvent(new InvoiceApprovalRequested("INV-2", 1_200));
                System.out.println("caller: completed INV-2");
            } catch (IllegalArgumentException ex) {
                System.out.println("caller: rejected INV-2: " + ex.getMessage());
            }
        }
    }
}
~~~

Với **JDK 17+** và **Gradle 8.x**, chạy trong thư mục **sync-event-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình in ra**:

~~~text
caller: begin INV-1
guard: INV-1
audit: INV-1
caller: completed INV-1
caller: begin INV-2
guard: INV-2
caller: rejected INV-2: exceeded demo limit
~~~

Phân tích:

- **INV-1**: **@Order(10)** làm guard được gọi trước audit **@Order(20)**. Cả hai trả về bình thường; sau đó dòng **caller: completed INV-1** mới xuất hiện.
- **INV-2**: guard ném **IllegalArgumentException**. Exception truyền về **publishEvent(...)** và bị catch trong **main**. **LocalAudit** không được gọi cho INV-2 trong cấu hình mặc định này.
- **@Order** diễn đạt thứ tự gọi; **@Order** không thay thế một transaction và không tự xác nhận nghiệp vụ thành công.
- Chương trình demo **không dùng transaction**. Dòng audit là **System.out.println(...)**, không chứng minh rollback; nếu listener đã ghi hệ thống bên ngoài trước khi exception xuất hiện, thao tác đó sẽ không được tự hoàn tác.

Dấu hiệu nhận biết đồng bộ ngay trong ví dụ là dòng **caller: completed INV-1** xuất hiện **sau** hai dòng listener. Nếu bật **@Async** hoặc thay đổi multicaster để dispatch qua executor, không được giữ nguyên kết luận này mà không kiểm thử cấu hình thực tế.

## 5. Đồng bộ khi đang có transaction: điều phải kiểm tra

Một dạng sử dụng thường gặp là service phát event bên trong transaction, rồi listener thực hiện thao tác bắt buộc tại cùng dữ liệu nghiệp vụ.

Ví dụ sau **chỉ minh họa tích hợp**; các class **Order**, **OrderRepository**, **AuditRepository** và cấu hình transaction manager cần được cung cấp trong dự án thực tế, nên đoạn này không phải chương trình độc lập như mục 4:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void approve(long id) {
        Order order = orders.loadForApproval(id);
        order.approve();
        events.publishEvent(new OrderApproved(id));
        // Nếu listener bắt buộc ném RuntimeException ra ngoài,
        // transaction interceptor mặc định sẽ đánh dấu rollback.
    }
}

public record OrderApproved(long orderId) {}

@Component
public class RequiredAuditListener {
    private final AuditRepository audit;

    public RequiredAuditListener(AuditRepository audit) {
        this.audit = audit;
    }

    @EventListener
    public void on(OrderApproved event) {
        audit.insertRequiredEntry(event.orderId());
    }
}
~~~

Các import chính: **org.springframework.stereotype.Service**, **org.springframework.stereotype.Component**, **org.springframework.transaction.annotation.Transactional**, **org.springframework.context.ApplicationEventPublisher** và **org.springframework.context.event.EventListener**.

### 5.1. Khi nào cùng một transaction?

Nếu **approve(...)** thực sự đi qua Spring transaction proxy, transaction manager quản lý đúng nguồn dữ liệu và repository của audit tham gia cùng transaction hiện tại, dữ liệu Order và audit có thể commit/rollback cùng nhau. Nếu listener ném RuntimeException và exception tiếp tục đi qua ranh giới **@Transactional**, mặc định transaction được rollback.

Những trường hợp làm thay đổi kết luận:

- **approve(...)** được gọi bằng self-invocation trong cùng instance khiến proxy **@Transactional** không có hiệu lực theo cơ chế proxy mặc định.
- Service xử lý/nuốt exception trước khi ra khỏi transaction boundary; giao dịch có thể commit nếu không được đánh dấu rollback-only.
- Listener mở **REQUIRES_NEW** hoặc dùng data source/transaction manager khác, nên không còn cùng transaction.
- Listener dùng thread khác thông qua **@Async** hoặc executor; transaction gắn thread không tự được truyền đi.
- Listener làm việc với email, message broker hoặc API ngoài DB mà không có giao thức phối hợp transaction; rollback DB không thể thu hồi hiệu ứng đã xảy ra.

**Kết luận cho transaction:** synchronous event là một cơ chế *giữ callback trong luồng thực thi*; tính nguyên tử cần được bảo đảm bằng transaction thực tế và kiến trúc lưu trữ.

### 5.2. Khác nhau giữa @EventListener và @TransactionalEventListener

| Loại listener | Thời điểm hoạt động | Quan hệ với kết quả commit |
| --- | --- | --- |
| **@EventListener** đồng bộ | Thường chạy ngay khi **publishEvent(...)** dispatch event | Có thể chạy *trước khi commit* và có thể khiến transaction rollback nếu lỗi lan ra |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Đăng ký xử lý gắn với giai đoạn trước commit | Dùng cho công việc phải xảy ra trước khi commit; lỗi có thể khiến commit không thành công |
| **@TransactionalEventListener(AFTER_COMMIT)** | Callback sau khi commit thành công | Không làm lần commit đã hoàn tất quay lại trạng thái chưa commit |
| **@TransactionalEventListener(AFTER_ROLLBACK)** | Callback khi transaction rollback | Phù hợp cho theo dõi hoặc xử lý trường hợp thất bại |
| **@TransactionalEventListener(AFTER_COMPLETION)** | Callback sau transaction kết thúc theo bất kỳ kết quả nào | Phù hợp cho cleanup và quan sát cả hai trạng thái |

Mặc định **@TransactionalEventListener** dùng pha **AFTER_COMMIT**. Khi không có transaction đang hoạt động, listener loại này **không chạy**, trừ khi cấu hình **fallbackExecution = true**; cần cân nhắc kỹ trước khi bật vì nó làm thay đổi cam kết “chỉ sau commit”.

**Điểm quan trọng:** callback transaction-bound có thể chạy trên thread đồng bộ của transaction nhưng *không nhất thiết chạy ngay bên trong lời gọi publishEvent(...)*. Ví dụ, **AFTER_COMMIT** thường đợi đến khi transaction commit sau này. Do đó, không thể dùng **@TransactionalEventListener(AFTER_COMMIT)** làm một bước validation bắt buộc phải xong **trước khi publishEvent(...) trả về**.

Nếu listener **AFTER_COMMIT** cần tạo một bản ghi DB mới, thường nên gọi một Spring-managed service có **@Transactional(propagation = Propagation.REQUIRES_NEW)**; không kỳ vọng transaction cũ còn khả năng commit thêm thay đổi sau pha hoàn tất.

## 6. Kiểm soát thứ tự và hành vi lỗi

### 6.1. Thứ tự gọi không đồng nghĩa chuỗi nghiệp vụ có đầu ra

Với nhiều **@EventListener** đồng bộ nhận cùng loại event, **@Order** quyết định ưu tiên gọi: **@Order(10)** được gọi trước **@Order(20)**. Nếu có các listener cùng order hoặc không khai báo order, không nên xây logic nghiệp vụ phụ thuộc thứ tự ngầm định giữa chúng.

**Chọn đồng bộ khi** các listener độc lập về đầu vào nhưng caller cần chờ chúng hoàn tất và thấy lỗi. **Chọn gọi hàm trực tiếp khi** từng bước cần kết quả trả về của bước trước hoặc có trình tự nghiệp vụ chặt chẽ: ví dụ **reserveStock(...)** phải trả về reservation ID trước khi **chargePayment(...)**.

### 6.2. Chính sách exception là một phần hợp đồng nghiệp vụ

Trong **SimpleApplicationEventMulticaster** mặc định, không có **ErrorHandler**, một exception từ listener đồng bộ truyền về publisher và dừng vòng multicast hiện tại. Điều này phù hợp với listener bắt buộc, nhưng có thể gây bất ngờ nếu listener chỉ làm việc phụ như metric.

Có thể cấu hình **ErrorHandler** để log/suppress lỗi hoặc xử lý theo chính sách khác; khi suppress exception, publisher sẽ không nhận lỗi đó. Cũng có thể xử lý lỗi phụ ngay trong listener để tránh làm hỏng thao tác chính. Trước khi làm vậy, phải phân định chính xác listener nào *được phép thất bại mà nghiệp vụ chính vẫn thành công*.

Thận trọng với cả **Error** và RuntimeException: việc bắt mọi **Throwable** chỉ để tiếp tục xử lý có thể che lỗi nghiêm trọng. Nên bắt các lỗi nghiệp vụ và hạ tầng có thể phục hồi theo chính sách cụ thể.

### 6.3. Một listener chậm khiến caller chậm theo

Giả sử trong một request có ba listener đồng bộ chạy liên tiếp, mỗi listener mất khoảng 20 ms, 30 ms và 50 ms. Chỉ riêng thời gian listener đã góp khoảng 100 ms vào độ trễ request, chưa kể DB, serialization và mạng. Nếu listener chờ API ngoài 10 giây, publisher cũng có thể bị chặn tương ứng; transaction và lock có thể bị giữ lâu.

Do đó, dù lựa chọn đồng bộ là đúng về mặt nghiệp vụ, vẫn cần:

- Đo p95/p99 latency của toàn bộ luồng publish và từng listener.
- Giới hạn I/O, timeout và số lần retry đồng bộ.
- Tránh giữ khóa DB khi thực hiện thao tác mạng lâu.
- Giới hạn việc phát event lồng nhau để tránh call stack sâu hoặc vòng lặp event.
- Thiết lập logging, trace/correlation ID và metric để xác định listener làm chậm hệ thống.
- Nếu độ trễ không còn chấp nhận được, cân nhắc đổi cơ chế phản ứng nhưng vẫn giữ đúng bảo đảm nghiệp vụ ban đầu.

## 7. Ba tình huống thực tế

### Tình huống A — Kiểm tra trước khi lưu: nên đồng bộ, thường gọi service trực tiếp

Người dùng gửi yêu cầu chuyển quyền sở hữu tài nguyên. Hệ thống phải xác minh vai trò và điều kiện trước khi ghi DB.

~~~text
Controller -> ApplicationService
              -> permissionService.requireTransferAllowed(...)
              -> repository.transfer(...)
              -> publishEvent(TransferCompleted)
              -> return success
~~~

Ở đây validation phải đồng bộ. Nhưng vì đây là tiền điều kiện bắt buộc, lời gọi service trực tiếp thường rõ nghĩa hơn một event **TransferRequested** với listener có thể được thêm/bớt mà làm thay đổi quyết định. Event **TransferCompleted** dùng để báo cho các thành phần khác rằng thay đổi đã thực hiện.

### Tình huống B — Audit bắt buộc trong cùng DB transaction: đồng bộ phù hợp

Một thao tác thay đổi mức phê duyệt cần tạo audit record cùng transaction. Nếu audit ghi lỗi, toàn bộ thay đổi phải rollback.

~~~text
@Transactional service
  -> cập nhật bản ghi
  -> publishEvent(LevelChanged)
     -> @EventListener audit DB (đồng bộ)
  -> commit Order + audit cùng DB transaction
~~~

Đây là trường hợp event đồng bộ có ý nghĩa nếu listener audit là thành phần được quản lý rõ và transaction tham gia chính xác. Với nghiệp vụ có yêu cầu nhất quán cực nghiêm ngặt hoặc auditing được coi là một phần bất biến dữ liệu, gọi **auditService.record(...)** trực tiếp trong transaction cũng là lựa chọn tốt, dễ phát hiện phụ thuộc khi đọc code.

### Tình huống C — Gửi email hoặc cập nhật hệ thống khác: thường không nên giữ đồng bộ

Duyệt hóa đơn đã commit và cần gửi email. Email server chậm hoặc lỗi tạm thời không nên làm quá trình duyệt bị thất bại một cách khó hiểu. Đặt **@TransactionalEventListener(AFTER_COMMIT)** để không gửi email cho giao dịch rollback. Nếu việc gửi chỉ là best effort, có thể chuyển xử lý sang executor có theo dõi; nếu yêu cầu **chắc chắn cuối cùng phải gửi**, dùng outbox và worker có retry/idempotency.

Lưu ý: **@Async** không tạo hàng đợi bền vững. JVM có thể dừng ngay sau commit nhưng trước khi công việc được thực thi; request đã trả thành công vẫn có thể mất email nếu không có outbox hoặc cơ chế bảo đảm tương đương.

## 8. Kiểm thử những gì khi chọn đồng bộ?

Không chỉ kiểm tra “listener có chạy” mà phải kiểm tra **hợp đồng đồng bộ**:

1. **Thread và blocking:** dùng listener test có cổng đồng bộ (ví dụ CountDownLatch) để xác nhận publisher chưa trả về trước khi listener hoàn tất; tránh dùng sleep cố định làm bằng chứng.
2. **Hành vi lỗi:** listener bắt buộc ném RuntimeException; kiểm tra caller nhận đúng lỗi và listener order sau không được gọi trong cấu hình mặc định.
3. **Thứ tự:** gắn **@Order** khác nhau và ghi danh sách lời gọi; xác nhận thứ tự mong muốn thay vì dựa vào thứ tự khai báo bean.
4. **Transaction rollback:** integration test với transaction manager và database thật/sát thực tế; listener ghi vào cùng DB rồi cố ý ném RuntimeException; xác nhận dữ liệu chính lẫn audit rollback khi đúng cấu hình.
5. **Bắt lỗi sai chỗ:** kiểm tra trường hợp service bắt exception nhưng không rethrow; xác nhận xử lý rollback-only hoặc hợp đồng nghiệp vụ mong muốn.
6. **Cấu hình multicaster:** xác nhận có hoặc không có executor toàn cục, **ErrorHandler** hoặc **@Async**; mỗi thay đổi này có thể làm đảo ngược kỳ vọng.
7. **Không có transaction:** đối với **@TransactionalEventListener**, xác nhận listener không chạy khi không có transaction, trừ khi chủ động bật fallback.
8. **Độ trễ:** đo listener chậm, giới hạn timeout và khả năng tránh deadlock khi cùng transaction giữ khóa.

Một kiểm thử đơn vị gọi trực tiếp method **on(event)** chỉ kiểm tra logic method; nó **không chứng minh** cơ chế dispatch, **@Order**, **@Async**, transaction propagation hay exception lan về publisher. Các bảo đảm đó cần test thông qua **ApplicationContext** và môi trường giao dịch phù hợp.

## 9. Những sai lầm dễ gặp

- **Cho rằng Spring Application Events luôn đồng bộ:** đây là mặc định phổ biến, nhưng có thể thay đổi bởi multicaster hoặc annotation bất đồng bộ.
- **Đưa kiểm tra bắt buộc sang @Async:** caller có thể trả thành công khi kiểm tra chưa hoàn tất.
- **Đồng nhất publishEvent(...) trả về với database commit:** khi gọi trong **@Transactional**, commit thường diễn ra sau khi phương thức nghiệp vụ kết thúc.
- **Mặc định có transaction chỉ vì chạy cùng thread:** phải có transaction thực, transaction manager và các tài nguyên tham gia đúng.
- **Nuốt exception bắt buộc bằng try/catch hoặc ErrorHandler:** hệ thống mất tín hiệu thất bại, có thể commit sai.
- **Lạm dụng @Order thay orchestration:** thứ tự listener không tạo dữ liệu trả về, transaction boundary hoặc hợp đồng bắt buộc rõ như gọi service trực tiếp.
- **Chạy I/O ngoài trong transaction đồng bộ:** tăng độ trễ, thời gian giữ lock và nguy cơ lỗi khó khôi phục.
- **Dùng @TransactionalEventListener(AFTER_COMMIT) để validation tức thời:** callback thuộc pha commit, không phải lúc event được publish.
- **Nhầm đồng bộ với bền vững:** event trong bộ nhớ không tồn tại sau khi JVM chết, kể cả trước/sau commit.
- **Giả định rollback DB hoàn tác gửi email hay HTTP:** các side effect này cần cơ chế bù trừ, idempotency hoặc outbox phù hợp.

## 10. Checklist quyết định trước khi triển khai

Trả lời lần lượt các câu hỏi sau:

1. **Caller có thật sự cần biết kết quả listener ngay không?** Nếu có, ưu tiên đồng bộ. Nếu không, xác định thời điểm an toàn để làm sau.
2. **Sai ở listener có phải làm tác vụ chính thất bại không?** Nếu có, giữ đường truyền exception/rollback rõ ràng; cân nhắc gọi service trực tiếp khi đây là validation cốt lõi.
3. **Tác vụ có cần cùng DB transaction không?** Xác minh transaction hiện hữu, propagation, data source và loại exception.
4. **Tác vụ có nhanh và có giới hạn thời gian không?** Nếu không, đánh giá ảnh hưởng lên request thread và transaction/lock.
5. **Kết quả phụ chỉ hợp lệ sau commit hay không?** Nếu có, dùng AFTER_COMMIT thay vì listener thường chạy ngay.
6. **Việc phải hoàn tất ngay hay chỉ cuối cùng nhất định phải hoàn tất?** Nếu có thể hoàn tất sau nhưng không được mất, cần lưu bền vững + retry + idempotency.
7. **Cấu hình đang dùng có thực sự đồng bộ không?** Kiểm tra **@Async**, **@EnableAsync**, cấu hình **applicationEventMulticaster**, executor và **ErrorHandler**.
8. **Đã kiểm thử từ publisher đến listener và transaction chưa?** Xác nhận thứ tự, lỗi, rollback và thời gian xử lý bằng integration test.

**Nguyên tắc nhớ nhanh:** Chọn listener đồng bộ khi phản ứng nhanh, cục bộ và kết quả hoặc lỗi của nó phải được nhận biết **trước khi publisher tiếp tục**. Với điều kiện nghiệp vụ cốt lõi, gọi service trực tiếp thường diễn đạt trách nhiệm rõ hơn. Dùng listener sau commit cho hiệu ứng phụ phụ thuộc commit; dùng outbox/queue cho công việc phải bền vững.

### Tài liệu tham khảo chính thức

- Spring Framework Reference, *Application Events, Asynchronous Listeners and Ordering Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.2.9 Javadoc, *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc, *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference, *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html

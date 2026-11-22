# TransactionSynchronizationFactory trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một flow có thể bắt đầu từ polling consumer, đọc message qua channel, thực hiện cập nhật cơ sở dữ liệu, gọi endpoint và cuối cùng đưa kết quả sang hệ thống khác. Việc DB commit thành công **chưa đồng nghĩa** toàn bộ hành động ngoài DB đã xảy ra; ngược lại, khi DB rollback, đôi khi cần chuyển file nguồn vào thư mục lỗi hoặc ghi lại thông tin để xử lý sau.

**TransactionSynchronizationFactory** là điểm mở rộng của Spring Integration cho phép đăng ký những hành động theo **kết cục transaction** của lần poll. Nó đặc biệt hữu ích khi muốn xử lý nguồn message sau khi flow đồng bộ hoàn tất, chẳng hạn đánh dấu file đã xử lý, chuyển thông báo đến channel thành công hoặc thất bại, và giữ lại thông tin message gốc khi phát sinh lỗi.

Sau bài học, bạn có thể:

- Hiểu quan hệ giữa **TransactionSynchronizationFactory**, **TransactionSynchronization**, **TransactionSynchronizationProcessor** và **IntegrationResourceHolder**.
- Phân biệt chính xác ba thời điểm **beforeCommit**, **afterCommit** và **afterRollback**.
- Cấu hình synchronization cho **transactional poller**, bằng XML namespace hoặc Spring JavaConfig.
- Biết được khi nào cần **DefaultTransactionSynchronizationFactory**, **PassThroughTransactionSynchronizationFactory** hoặc **PseudoTransactionManager**.
- Chẩn đoán tác động của **DirectChannel, ExecutorChannel, poller, transaction advice, retry, errorChannel, MessageStore** và correlation.
- Không nhầm synchronization với transaction phân tán hoặc bảo đảm gửi sự kiện **exactly once**.

## 1. Bài toán thực tế: xử lý file và cập nhật DB

Giả sử ứng dụng quét thư mục chứa file đơn hàng:

~~~text
/inbox/order-42.json
    ↓ File inbound adapter + transactional poller
    ↓ DirectChannel
    ↓ JSON transformer
    ↓ Service activator
    ↓ Ghi DB đơn hàng và các dòng sản phẩm
    ├─ COMMIT   → chuyển file sang /processed/
    └─ ROLLBACK → chuyển file sang /failed/ hoặc để lại để retry
~~~

Nếu handler vừa ghi DB vừa di chuyển file ngay trong code:

~~~java
void process(File file) {
    saveOrderToDatabase(file);  // Có thể thuộc transaction DB.
    moveFile(file, processedDir); // File system không thuộc transaction DB.
}
~~~

thì việc gọi **moveFile** trước khi DB commit xong có thể gây ra tình huống file đã được chuyển nhưng transaction bị rollback. Khi đó lần polling tiếp theo không còn thấy file, dù DB chưa có đơn hàng.

**Transaction synchronization** cho phép dời hành động theo trạng thái transaction:

- Nếu transaction kết thúc bằng commit, thực hiện bước **afterCommit**.
- Nếu transaction rollback, thực hiện bước **afterRollback**.
- Nếu cần kiểm tra một điều kiện ngay trước khi commit, thực hiện **beforeCommit**.

Nhưng có một giới hạn quan trọng: **điều phối theo thời điểm khác với atomicity**. File system, HTTP API hoặc message broker không tự động trở thành tài nguyên chung transaction với DB chỉ vì được gọi trong callback. Nếu app chết ngay sau DB commit nhưng trước khi chuyển file, vẫn có thể phải phục hồi bằng cơ chế khác.

## 2. TransactionSynchronizationFactory là gì?

Trong package **org.springframework.integration.transaction**, interface cốt lõi có hợp đồng khái quát:

~~~java
public interface TransactionSynchronizationFactory {
    TransactionSynchronization create(Object key);
}
~~~

Factory tạo một đối tượng **TransactionSynchronization** dùng cho ngữ cảnh transaction tương ứng. **Tham số key là khóa ngữ cảnh do framework truyền**, không nên tự giả định nó là payload, message ID hay business key. Khi cần message gốc, dùng cơ chế **IntegrationResourceHolder** mà Spring Integration hỗ trợ.

Spring Integration cung cấp:

| Thành phần | Vai trò |
| --- | --- |
| **TransactionSynchronizationFactory** | Strategy tạo synchronization cho một ngữ cảnh xử lý |
| **DefaultTransactionSynchronizationFactory** | Implementation có sẵn, nhận một **TransactionSynchronizationProcessor** và tạo synchronization chuyển các callback tới processor |
| **TransactionSynchronizationProcessor** | Hợp đồng gồm **processBeforeCommit**, **processAfterCommit**, **processAfterRollback** |
| **ExpressionEvaluatingTransactionSynchronizationProcessor** | Processor có sẵn, thực thi biểu thức **SpEL** ở các pha trước commit, sau commit, sau rollback; có thể gửi kết quả ra channel |
| **IntegrationResourceHolder** | Giữ tham chiếu tới Spring Message đang được poll và resource/attributes liên quan; cung cấp **getMessage()** |
| **PassThroughTransactionSynchronizationFactory** | Synchronization tối giản, chủ yếu liên kết message được poll với ngữ cảnh transaction để hỗ trợ chẩn đoán lỗi |
| **PseudoTransactionManager** | Tạo ngữ nghĩa callback commit/rollback khi không có tài nguyên transaction thực sự; **không** rollback thao tác ngoài như file hoặc FTP |

Hợp đồng của processor:

~~~java
public interface TransactionSynchronizationProcessor {
    void processBeforeCommit(IntegrationResourceHolder holder);
    void processAfterCommit(IntegrationResourceHolder holder);
    void processAfterRollback(IntegrationResourceHolder holder);
}
~~~

Trong code thực tế, các interface này nằm trong package của Spring Integration; **TransactionSynchronization** đến từ cơ chế transaction của Spring Framework. Factory không tạo một transaction manager mới và cũng không chủ động bắt đầu transaction. Nó kết hợp với transaction/transaction advice **đã được cấu hình ở poller**.

### Factory khác @Transactional thế nào?

**@Transactional** hoặc **TransactionInterceptor** kiểm soát **khi nào bắt đầu, commit hoặc rollback transaction**, dựa vào lời gọi được advice bao quanh và rollback rules. **TransactionSynchronizationFactory** đăng ký các callback **theo vòng đời transaction đó**. Hai cơ chế bổ sung cho nhau; một factory không tự làm phần xử lý dữ liệu trở thành transactional.

Ví dụ:

~~~text
TransactionInterceptor:
  bắt đầu transaction → poll message → chạy flow → commit/rollback

TransactionSynchronizationFactory:
  tạo synchronization theo message/resource đã poll
  → beforeCommit / afterCommit / afterRollback tại thời điểm phù hợp
~~~

## 3. Trình tự thực thi trong một transactional poller

Đối với flow vẫn ở cùng thread, mô hình tổng quát:

~~~mermaid
flowchart TD
    P["Poller được scheduler kích hoạt"] --> TX["TransactionInterceptor<br/>bắt đầu transaction"]
    TX --> R["MessageSource.receive() / nhận message"]
    R --> B["Gắn message/resource vào<br/>transaction synchronization"]
    B --> F["Flow đồng bộ qua DirectChannel<br/>transformer / handler / DB"]
    F --> OK{"Flow và transaction<br/>có thể commit?"}
    OK -- "Có" --> BC["beforeCommit"]
    BC --> COM{"beforeCommit thành công?"}
    COM -- "Có" --> DB["Commit transaction"]
    DB --> AC["afterCommit"]
    AC --> DONE["Hoàn tất / cleanup"]
    COM -- "Không" --> RB["Rollback transaction"]
    OK -- "Không" --> RB
    RB --> AR["afterRollback"]
    AR --> FIN["Hoàn tất / cleanup"]
~~~

Đây là **sơ đồ logic rút gọn**. Thực tế Spring Framework có thêm các callback trong vòng đời transaction, cơ chế tài nguyên và xử lý exception/cleanup. Việc **beforeCommit** thành công không bảo đảm commit chắc chắn thành công; DB vẫn có thể lỗi ở bước commit.

### Các pha và hệ quả

| Pha | Transaction đã commit chưa? | Ví dụ phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **beforeCommit** | **Chưa** | Kiểm tra điều kiện trước commit, gọi logic có khả năng báo lỗi để transaction rollback | Đừng phát ngoại tác không thể hoàn tác; dù pha này thành công, commit vẫn có thể thất bại |
| **afterCommit** | **Đã commit** | Phát tín hiệu hoàn tất, chuyển file vào thư mục thành công, khởi động bước hậu xử lý | Nếu callback thất bại, DB đã commit; không thể rollback lại DB bằng cách ném exception |
| **afterRollback** | Transaction đã rollback | Ghi nhận thất bại, chuyển file sang vùng kiểm tra, đưa vào retry có kiểm soát | Không đảo ngược tác dụng đã xảy ra ngoài DB; không phải mọi trường hợp kết thúc bất thường đều là rollback được xác định |

**beforeCommit** có thể làm transaction rollback nếu biểu thức hoặc downstream processing ở pha này ném exception. Nhưng nếu bạn ghi event ra mạng trong beforeCommit rồi DB rollback, event có thể đã được gửi. **afterCommit** giảm một dạng sai thứ tự như vậy nhưng vẫn có khoảng hở giữa commit DB và gửi event; dùng **transactional outbox** khi yêu cầu phát sự kiện bền vững.

## 4. Cấu hình XML cho transactional poller

Tài liệu Spring Integration minh họa synchronization trên **file inbound adapter**. Sau đây là đoạn cấu hình namespace tiêu biểu; giả định các bean/channel **transactionManager**, **fileFilter**, **orders**, **committedFiles** và **rolledBackFiles** đã được khai báo trong application context:

~~~xml
<int-file:inbound-channel-adapter
        id="orderFileInbound"
        directory="/data/inbox"
        filter="fileFilter"
        channel="orders">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"
                synchronization-factory="orderSyncFactory"/>
    </int:poller>
</int-file:inbound-channel-adapter>

<int:transaction-synchronization-factory id="orderSyncFactory">
    <int:after-commit
            expression="payload"
            channel="committedFiles"/>
    <int:after-rollback
            expression="payload"
            channel="rolledBackFiles"/>
</int:transaction-synchronization-factory>
~~~

**Chú thích:**

1. Poller mở transaction nhờ **int:transactional** và transaction manager đã cấu hình. Factory được nối bằng **synchronization-factory**.
2. **orders** là channel để service activator/transformer xử lý file. Chuỗi xử lý đồng bộ có thể sử dụng cùng transaction DB khi cấu hình đúng.
3. **expression="payload"** trả về payload của message **đã poll ban đầu**. Kết quả được gửi tới **committedFiles** hoặc **rolledBackFiles**, vì vậy ở ví dụ này các subscriber có thể nhận **File** và quyết định di chuyển file, log hoặc quarantine.
4. Chỉ định **expression** có kết quả khác null và **channel** sẽ tạo một message chứa kết quả biểu thức. Nếu không chỉ định biểu thức mà chỉ có channel, Spring Integration có thể chuyển **message được nhận** tới channel đó.
5. File adapter, filter, transaction manager, các channel và handlers cần được lắp đầy đủ vào flow thực tế. Đây là đoạn XML minh họa **phần liên quan đến synchronization**, không phải dự án có thể chạy ngay khi sao chép riêng.
6. Trong flow thật, nên kiểm tra chính sách tránh file bị poll nhiều lần, tên file trùng, thư mục lỗi không khả dụng và hành vi khi di chuyển file thất bại.

### Biểu thức SpEL thấy dữ liệu nào?

Với **ExpressionEvaluatingTransactionSynchronizationProcessor**, **#root** là Spring Message gốc đã poll. Vì thế:

~~~text
payload
    → payload của message ban đầu

headers['correlationId']
    → giá trị correlationId của message ban đầu (nếu có)

payload.name
    → tên File nếu payload đúng là java.io.File
~~~

Tùy **MessageSource**, framework có thể cung cấp biến SpEL bổ sung. Tài liệu chính thức lấy ví dụ **#mongoTemplate** với MongoDB message source hoặc **#store** với Redis store message source. Không nên dùng các biến đó cho một adapter khác nếu message source không công bố chúng.

### Đổi file ở callback: kết quả không phải message nghiệp vụ

Ví dụ thường gặp trong tài liệu:

~~~xml
<int:transaction-synchronization-factory id="moveFilesSyncFactory">
    <int:after-commit
        expression="payload.renameTo(new java.io.File('/data/processed/' + payload.name))"
        channel="moveSuccessResults"/>
    <int:after-rollback
        expression="payload.renameTo(new java.io.File('/data/failed/' + payload.name))"
        channel="moveFailureResults"/>
</int:transaction-synchronization-factory>
~~~

Đây là **ví dụ thao tác file**, không phải transaction file system. Biểu thức **File.renameTo()** trả về **boolean**; message gửi tới hai channel trên mang **true/false**, **không phải File**. Giá trị false phải được xử lý, bởi hàm có thể không ném exception khi thất bại. Các chi tiết như chuyển file qua hai phân vùng, quyền ghi, race giữa poller và retry cần được thiết kế riêng.

Nếu downstream cần toàn bộ payload hoặc correlation, nên gửi **payload/message ban đầu** vào handler chuyên dụng, tại đó thực thi thao tác có kiểm soát, ghi kết quả, cảnh báo khi lỗi và bảo đảm idempotency. Với khối lượng lớn hoặc yêu cầu audit, tách thành lệnh xử lý bền vững thay vì phụ thuộc hoàn toàn vào callback in-memory.

## 5. Tạo factory từ JavaConfig

Không bắt buộc dùng XML để khai báo processor. Các API hiện đại cho phép tạo **ExpressionEvaluatingTransactionSynchronizationProcessor** và bọc bằng **DefaultTransactionSynchronizationFactory**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.ExpressionEvaluatingTransactionSynchronizationProcessor;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderSynchronizationConfiguration {

    @Bean
    TransactionSynchronizationFactory orderSynchronizationFactory(
            @Qualifier("committedFiles") MessageChannel committedFiles,
            @Qualifier("rolledBackFiles") MessageChannel rolledBackFiles) {
        SpelExpressionParser parser = new SpelExpressionParser();

        ExpressionEvaluatingTransactionSynchronizationProcessor processor =
                new ExpressionEvaluatingTransactionSynchronizationProcessor();

        processor.setAfterCommitExpression(
                parser.parseExpression("payload"));
        processor.setAfterCommitChannel(committedFiles);

        processor.setAfterRollbackExpression(
                parser.parseExpression("payload"));
        processor.setAfterRollbackChannel(rolledBackFiles);

        return new DefaultTransactionSynchronizationFactory(processor);
    }
}
~~~

Đoạn này chỉ tạo bean factory; **cần tham chiếu bean đó từ cấu hình transactional poller**. Các phiên bản Spring Integration cũng có **TransactionSynchronizationFactoryBean**, hỗ trợ khai báo biểu thức/channel từ JavaConfig theo hướng builder. Việc chọn cách khai báo không thay đổi bản chất transaction.

Không dùng biểu thức SpEL do user đầu vào trực tiếp quyết định. Biểu thức có quyền truy cập đối tượng/message trong runtime; cần là cấu hình đáng tin cậy, được kiểm thử và có kiểm soát quyền truy cập.

### Tự viết processor khi cần logic đặc thù

Khi chỉ chuyển message sang một channel, processor có sẵn thường đủ. Với yêu cầu đặc thù, có thể triển khai **TransactionSynchronizationProcessor**:

~~~java
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.integration.transaction.TransactionSynchronizationProcessor;
import org.springframework.messaging.Message;

class AuditSynchronizationProcessor
        implements TransactionSynchronizationProcessor {

    private final AuditRecorder recorder;

    AuditSynchronizationProcessor(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public void processBeforeCommit(IntegrationResourceHolder holder) {
        // Không phát tác dụng ngoài transaction ở đây nếu không cần thiết.
    }

    @Override
    public void processAfterCommit(IntegrationResourceHolder holder) {
        Message<?> polledMessage = holder.getMessage();
        recorder.recordCommitted(
                String.valueOf(polledMessage.getHeaders().get("requestId")));
    }

    @Override
    public void processAfterRollback(IntegrationResourceHolder holder) {
        Message<?> polledMessage = holder.getMessage();
        recorder.recordRolledBack(
                String.valueOf(polledMessage.getHeaders().get("requestId")));
    }
}

interface AuditRecorder {
    void recordCommitted(String requestId);
    void recordRolledBack(String requestId);
}
~~~

Đây là **mã minh họa contract**, chưa phải cơ chế audit đáng tin cậy: header **requestId** cần được kiểm tra null/giá trị, **recorder** cần idempotency và xử lý lỗi riêng. Việc gọi DB trong **afterCommit** không mặc định thuộc một transaction mới; nếu muốn ghi trạng thái bền vững sau commit, cần xác định transaction mới và xử lý trường hợp callback chết trước khi ghi.

Khi tự tạo **TransactionSynchronizationFactory** và synchronization hoàn toàn mới, phải quản lý đúng lifecycle resource đã bind vào transaction. Spring Integration nêu rõ custom factory có trách nhiệm **unbind resource** khi transaction hoàn tất; mặc định framework sử dụng implementation dựa trên **ResourceHolderSynchronization** để tránh leak tài nguyên giữa các lần poll trên cùng thread.

## 6. PassThroughTransactionSynchronizationFactory và ErrorMessage

Không phải flow nào cũng cần callback success/failure do bạn khai báo. Nhưng khi poller chạy dưới transaction advice, điều quan trọng là giữ được **message đã poll** để chẩn đoán exception.

Từ **Spring Integration 5.0**, khi polling endpoint có **TransactionInterceptor** trong advice chain nhưng không khai báo factory riêng, framework thường dùng **PassThroughTransactionSynchronizationFactory** theo mặc định. Nó có nhiệm vụ liên kết message đã poll với ngữ cảnh transaction, giúp khi exception xảy ra ở phần downstream sau transaction advice, lỗi có thể được bọc thành **MessagingException** có **failedMessage**.

~~~text
Poller
  → transaction advice
  → message A (headers: requestId, correlationId)
  → handler ném lỗi
  → MessagingException
       ├─ failedMessage = message A
       └─ cause = lỗi gốc
  → ErrorMessage trên errorChannel (theo cơ chế endpoint)
~~~

Lợi ích: một error consumer có thể truy được **payload, requestId, correlationId** của message thay vì chỉ nhìn thấy stack trace. Nếu dùng custom transaction advice **không phải TransactionInterceptor**, có thể phải cấu hình **PassThroughTransactionSynchronizationFactory** rõ ràng để có hành vi tương tự.

**Không hiểu nhầm:** Factory pass-through không có nghĩa nó đã cấu hình **afterCommit/afterRollback business action**. Khi muốn phát message sang channel sau commit hoặc rollback, cần cấu hình processor phù hợp.

Với error flow, kiểm tra cả **ErrorMessage.getOriginalMessage()** (nếu có) và **MessagingException.getFailedMessage()**; không giả định ErrorMessage headers luôn tự mang business correlation. Lỗi phát sinh **trước khi poll nhận được message** cũng có thể không có failedMessage.

## 7. PseudoTransactionManager: callback mà không có DB transaction

Một flow chỉ xử lý file và gửi FTP có thể không sử dụng tài nguyên transactional như JDBC hay JMS. Dù vậy, vẫn có nhu cầu “nếu flow chạy xong thì chuyển file sang processed; nếu lỗi thì chuyển sang failed”.

**PseudoTransactionManager** cho phép thực thi các callback dựa vào trạng thái hoàn thành của flow, mặc dù không có transaction thực sự trên file hay FTP:

~~~xml
<bean id="transactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager"/>
~~~

Khi gắn pseudo transaction manager vào transactional poller cùng factory:

- Flow kết thúc thành công → **beforeCommit** và **afterCommit** có thể chạy.
- Flow thất bại/rollback → **afterRollback** được gọi.
- **Không có commit hoặc rollback tài nguyên thật** đối với file, SMTP, FTP hay HTTP. File đã upload không được “tự thu hồi” khi flow báo lỗi.

Điều này phù hợp với workflow phối hợp theo kết quả xử lý, **không** phù hợp khi nghiệp vụ đòi hỏi atomicity giữa những hệ thống độc lập. Với yêu cầu phục hồi mạnh, dùng audit bền vững, idempotency, retry có kiểm soát và cơ chế đối soát/bù trừ.

## 8. Ranh giới thread: transaction kết thúc ở đâu?

Spring transaction truyền thống gắn với **thread**. Nếu một poller mở transaction và mọi channel/handler tiếp theo chạy đồng bộ trên cùng thread, các tài nguyên tương thích có thể tham gia cùng ngữ cảnh đó.

~~~mermaid
flowchart LR
    P["Poller + transaction"] --> D["DirectChannel"]
    D --> H["Handler DB"]
    H --> C["Commit / rollback"]
    C --> S["Sync callback"]
~~~

Nhưng nếu flow qua **ExecutorChannel** hoặc một pollable channel dẫn sang consumer khác:

~~~mermaid
flowchart LR
    P["Poller + transaction A"] --> E["ExecutorChannel"]
    E --> ACK["Handoff thành công"]
    ACK --> CA["Commit A<br/>sync afterCommit"]
    E -. "Thread khác" .-> H["Handler DB / HTTP"]
    H --> B["Transaction B nếu cấu hình"]
~~~

**Transaction A không tự lan qua thread mới.** Callback afterCommit của A có thể xảy ra khi handler bất đồng bộ còn đang chạy hoặc chưa hoàn tất. Do đó một “afterCommit message” ở poller **không thể được hiểu là toàn bộ downstream async đã thành công**.

| Thành phần | Tác động đến transaction từ poller |
| --- | --- |
| **DirectChannel** | Gọi handler đồng bộ trên thread hiện tại; thường giữ cùng transaction context |
| **ExecutorChannel** | Chuyển sang thread pool; transaction/ThreadLocal của sender không mặc định truyền sang |
| **QueueChannel + polling consumer khác** | Handoff message, transaction của poller trước kết thúc; consumer phía sau cần transaction riêng |
| **Gateway đồng bộ** | Có thể tham gia cùng thread/transaction nếu flow không có async boundary |
| **Broker/HTTP adapter** | Việc giao message cho hệ thống ngoài không tạo một transaction phân tán cùng JDBC theo mặc định |

Nếu cần giữ message qua ranh giới async, cân nhắc **transactional message store, broker transaction** hoặc outbox, nhưng phải xác định rõ **transaction của từng phía**. Việc đặt callback lên poller không làm quá trình downstream async nhập lại transaction cũ.

## 9. Callback không thay thế idempotency hoặc outbox

Ví dụ nghiệp vụ yêu cầu “ghi đơn vào DB, rồi phát event OrderCreated”. Nếu phát event trong handler **trước commit**, có rủi ro event tới consumer khi DB còn chưa commit hoặc cuối cùng rollback.

Nếu phát event ở **afterCommit**, tránh được trường hợp gửi sớm, nhưng vẫn tồn tại rủi ro:

~~~text
T0: DB commit thành công.
T1: Ứng dụng crash trước khi afterCommit gửi event.
T2: DB có đơn hàng, nhưng event chưa được phát.
~~~

Trường hợp khác:

~~~text
T0: DB commit thành công.
T1: afterCommit gửi event ra broker.
T2: Broker nhận event, response bị mất.
T3: Callback báo lỗi hoặc ứng dụng restart, replay có thể gửi event lần nữa.
~~~

Do đó, **afterCommit là callback theo thời điểm**, không phải bảo đảm exactly-once giữa DB và broker. Khi event là bắt buộc, nên xem xét **transactional outbox**:

~~~mermaid
flowchart LR
    H["Handler"] --> DB[("DB transaction<br/>Order + OutboxEvent")]
    DB -->|commit| W["Outbox publisher"]
    W --> Q["Broker"]
    Q --> C["Consumer idempotent"]
~~~

Outbox event được ghi **trong cùng transaction DB** với đơn hàng; publisher đọc và phát lại khi cần. Consumer phải có cơ chế chống duplicate. Có thể vẫn dùng TransactionSynchronizationFactory để **đánh thức publisher sau commit** nhằm giảm độ trễ, nhưng outbox/polling đảm bảo vẫn phát được nếu callback bị mất.

### Việc di chuyển file cũng cần idempotency

Với file inbound adapter:

- Tạo khóa nghiệp vụ ổn định từ **file ID/checksum + source**, hoặc từ ID bên trong payload.
- Cấu hình file filter và lưu state đã xử lý phù hợp khi restart.
- Nếu chuyển file afterCommit thất bại, DB có thể đã commit; lần poll sau không được tạo thêm cùng đơn hàng.
- Nếu afterRollback di chuyển file vào failed, phải có workflow phục hồi/quarantine và hạn chế retry vô hạn.
- Nếu file đã chuyển nhưng process chết trước khi ghi audit, cần có cách **đối soát thư mục và DB**.

## 10. Retry, error handling và correlation

TransactionSynchronizationFactory quan sát **kết quả của transaction đang bao quanh lần poll**, chứ không tự định nghĩa chính sách retry. Khi flow có **RequestHandlerRetryAdvice**, broker redelivery và transaction rollback, cần xem tầng nào đang retry.

Ví dụ một handler lỗi hai lần rồi lần thứ ba thành công:

~~~text
Poll message A (requestId=O-42)
  → RetryAdvice: attempt 1 throws
  → RetryAdvice: attempt 2 throws
  → RetryAdvice: attempt 3 succeeds
  → transaction commit
  → afterCommit chạy cho transaction
~~~

Ngược lại, nếu retry hết và exception được ném ra:

~~~text
Poll message A
  → retry exhausted
  → transaction rollback
  → afterRollback chạy
  → nguồn có thể redeliver theo chính sách receive/ack/adapter
~~~

**Một số bẫy cần tránh:**

1. Handler **bắt exception rồi chỉ log** → flow coi như thành công; transaction có thể commit và **afterCommit** được gọi dù nghiệp vụ đã thất bại.
2. Recovery callback **nuốt exception** sau khi cạn retry → transaction phía ngoài có thể commit nếu không được đánh dấu rollback-only; cần mô hình hóa kết quả recovery rõ ràng.
3. Retry đặt **bên trong một transaction đã bị đánh dấu rollback-only** → attempt sau có thể thất bại dù logic đã xử lý xong; cần xem lại thứ tự retry/transaction advice.
4. Transaction được commit ở poller trước khi async downstream kết thúc → **afterCommit không có nghĩa async business work đã xong**.
5. afterRollback phát message trực tiếp vào hệ thống không idempotent → khi rollback xảy ra nhiều lần, thông báo hoặc side effect cũng có thể bị lặp.

Để theo dõi lỗi, cần giữ **correlationId**, **requestId/idempotency key**, business key và source metadata của message. Với callback đánh giá trên message gốc, chỉ những header **đã có tại thời điểm poll** mới được truy cập như một phần của message gốc; thông tin được tạo ở handler phía sau cần được ghi vào store hoặc event bền vững theo thiết kế, không suy luận callback tự nhìn thấy mọi payload đã biến đổi.

## 11. MessageStore, restart và lifecycle IntegrationFlow

Một transaction synchronization thường được đăng ký **trong bộ nhớ của thread/process đang xử lý transaction**. Nó không phải một hàng đợi bền vững tự khôi phục sau crash. Do đó:

- Ứng dụng chết **trước commit**: transaction của DB thường rollback theo semantics của resource/connection; callback Java trong process chết **không có cơ hội chạy**.
- Ứng dụng chết **sau commit** nhưng **trước/sau callback**: DB đã commit, nhưng trạng thái callback có thể chưa được ghi nhận hoặc side effect đã thực thi một phần.
- **MessageStore** persistent có thể giữ message/aggregator group qua restart, nhưng không mặc định lưu lại hoặc phát lại callback đã bỏ lỡ.
- Stop/start **IntegrationFlow** thay đổi lifecycle consumer/poller; các message đang in-flight và transaction dở dang cần được đánh giá theo timeout, shutdown và transaction manager.
- Khi có nhiều instance cùng poll nguồn, cần xét **locking/claim-check**, duplicate, atomic read, thứ tự và state phối hợp; synchronization ở JVM này không khóa được nguồn bên JVM khác.

Với yêu cầu khôi phục, phải xác định **nguồn sự thật**: DB/outbox, message store bền vững, broker hoặc trạng thái file có thể đối soát. Callback chỉ là một bước trong workflow đó.

## 12. Chẩn đoán khi beforeCommit/afterCommit/afterRollback không chạy như mong đợi

Một checklist điều tra theo thứ tự:

| Triệu chứng | Câu hỏi kiểm tra |
| --- | --- |
| Không có callback | Poller có transaction advice và factory đúng không? MessageSource có trả message trong lần poll này không? |
| afterCommit chạy dù handler thất bại | Handler có catch rồi bỏ exception, recovery trả về bình thường hoặc lỗi xảy ra **sau async boundary** không? |
| afterRollback không chạy | Transaction có thực sự rollback, hay exception đã được chuyển thành kết quả bình thường? Lỗi có xảy ra ngoài transaction không? |
| afterCommit không gửi message | SpEL có trả **null/void** không? Channel có được khai báo và subscriber có tồn tại không? |
| Channel nhận kiểu payload lạ | Biểu thức trả **Boolean**, **File**, object khác; consumer đang mong kiểu gì? |
| Event mất dù DB commit | App có crash giữa commit và callback? Có outbox hoặc audit bền vững không? |
| Lỗi thiếu correlation | Message được poll có correlationId không? SpEL/handler có tạo message mới làm rơi header không? |
| Hết retry vẫn lặp | Broker/poller có redelivery riêng? afterRollback có di chuyển file hay nguồn vẫn nhận lại liên tục? |
| Hết thread hoặc giảm throughput | Callback có làm I/O chậm trên thread poller? Có await HTTP hoặc lock kéo dài không? |

### Quan sát tối thiểu

Gắn vào log/trace các trường:

~~~text
flow=orderImport
endpoint=orderFileInbound
requestId=O-42
correlationId=import-batch-2026-11
thread=order-poller-1
transactionPhase=AFTER_COMMIT
businessOutcome=COMPLETED
callbackOutcome=FILE_MOVE_FAILED
~~~

Phân biệt **businessOutcome**, **transactionOutcome** và **callbackOutcome**. Ví dụ DB commit thành công nhưng move file thất bại là sự cố hậu xử lý sau commit, không nên gộp thành “DB rollback”.

Metric hữu ích:

- Số lần poll, message được nhận, message không nhận được, transaction commit/rollback.
- Số callback theo pha, độ trễ callback, số lần callback lỗi và số event cần đối soát.
- Kích thước queue, executor saturation, poller duration và độ trễ transaction.
- Message thiếu requestId/correlationId, số file chưa được chuyển, DLQ/quarantine tồn đọng.
- Số message duplicate hoặc outbox event chưa được publisher xác nhận.

## 13. Kiểm thử hành vi transaction synchronization

Khi kiểm thử, cần dùng **transaction manager đúng với nguồn đang kiểm soát**; test có H2/JDBC sẽ khác test chỉ dùng file/FTP. Tránh kết luận dựa trên việc tự gọi processor methods — cách đó chỉ kiểm tra handler, **không kiểm tra transaction lifecycle thực**.

### A. Happy path: commit

1. Cho poller nhận một message có requestId cố định.
2. Handler thực thi một insert/update DB trong transaction đang mở.
3. Chờ transaction kết thúc, xác minh DB **đã commit**.
4. Xác minh **afterCommit** nhận message gốc đúng requestId; **afterRollback** không nhận.
5. Nếu callback chuyển file, kiểm tra file thực sự nằm ở thư mục đích; không chỉ kiểm tra expression đã được gọi.

### B. Failure path: rollback

1. Làm handler cố ý ném **RuntimeException** sau khi DB update.
2. Xác minh DB rollback, **afterRollback** được gọi và afterCommit không chạy.
3. Xác minh correlation/requestId còn đủ để truy ra message lỗi.
4. Kiểm tra nguồn poller có phát lại message không và điều đó có đúng kỳ vọng vận hành hay không.

### C. beforeCommit thất bại

Cho **beforeCommit** ném exception khi kiểm tra điều kiện. Xác minh transaction rollback theo policy và không chạy afterCommit. Kiểm tra external side effect không bị thực thi trước commit.

### D. afterCommit thất bại

Cho handler/channel của afterCommit ném exception hoặc thao tác chuyển file trả false. Xác minh DB **vẫn đã commit** và hệ thống có **cơ chế phát hiện/phục hồi hậu xử lý**. Không viết test yêu cầu DB rollback sau khi commit đã hoàn tất.

### E. Async boundary

Chèn **ExecutorChannel** trước handler downstream có thể thất bại. Xác minh callback của poller dựa trên kết quả **handoff đồng bộ**, không dựa trên kết quả xử lý async chạy muộn. Nếu nghiệp vụ cần success sau async, phải thiết kế một điểm ghi trạng thái/transaction riêng ở consumer.

### F. Crash/restart

Mô phỏng ngắt process giữa DB commit và bước hậu xử lý (theo cơ chế kiểm thử tích hợp phù hợp). Xác minh tiến trình mới có thể **đối soát và hoàn tất** bằng outbox/audit/nguồn dữ liệu, thay vì kỳ vọng callback cũ sẽ chạy lại.

## 14. Bài thực hành: thiết kế flow nhập đơn hàng đáng tin cậy

**Đề bài:** Mỗi phút poll 100 file đơn hàng, ghi DB, chuyển file đã xử lý, phát event cho hệ thống downstream. Các file đôi khi có JSON sai; hệ thống có hai application instance chạy song song và có thể restart khi triển khai phiên bản mới.

**Thiết kế tối thiểu nên xem xét:**

1. **Inbound/poller:** Có filter/locking để tránh hai instance xử lý cùng file; xác định số poller task, timeout và chính sách transaction.
2. **Handler:** Validate message, ghi đơn theo **unique business key**, ném exception khi thực sự thất bại; giữ requestId/correlationId.
3. **DB transaction:** Insert đơn và ghi **outbox event** trong cùng transaction; định nghĩa rõ rollback rules.
4. **Synchronization:** afterCommit phát tín hiệu để worker chuyển file hoặc thức dậy outbox publisher; afterRollback chuyển trạng thái sang quarantine/retry tùy loại lỗi.
5. **Recovery:** Nếu app crash giữa DB commit và move file, worker đối soát DB/file; không tạo thêm đơn hàng khi xử lý lại.
6. **Error handling:** JSON sai đi quarantine; lỗi DB tạm thời dùng retry có giới hạn; event downstream có consumer idempotent.
7. **Observability:** Phân biệt trạng thái DB, outbox, file và callback; log correlation xuyên suốt.

### Hai câu hỏi kiểm tra hiểu biết

**Câu 1:** afterCommit gửi HTTP request nhưng server nhận được rồi phản hồi timeout. Transaction DB có bị rollback không?

**Giải thích:** **Không**, DB đã commit trước khi afterCommit chạy. Cần idempotency key, truy vấn trạng thái hoặc đối soát vì HTTP request có thể đã có tác dụng.

**Câu 2:** Poller có transaction, handler phía sau ExecutorChannel lỗi sau 5 giây. afterRollback của poller có tự chạy do lỗi đó không?

**Giải thích:** **Không tự động**. Việc chuyển thread đã cắt ranh giới transaction của poller; nếu handoff thành công, poller có thể commit và gọi afterCommit trước khi lỗi async xuất hiện. Consumer phía sau cần cơ chế transaction và error handling của chính nó.

## 15. Checklist trước khi đưa vào production

- Có **transaction manager thực sự** hay đang dùng **PseudoTransactionManager**? Tài nguyên nào được transaction bảo vệ?
- Transaction bắt đầu ở **poller** hay ở handler? Advice chain và rollback rules đã được kiểm thử chưa?
- Factory được gắn vào **poller đang hoạt động** hay mới chỉ khai báo bean?
- Có xác định rõ semantics của **beforeCommit, afterCommit, afterRollback** không?
- SpEL trả **File/Boolean/message** nào? Channel có consumer phù hợp và cơ chế ghi lỗi khi callback thất bại không?
- Có **ExecutorChannel/QueueChannel** cắt transaction boundary không?
- Handler có nuốt exception khiến afterCommit chạy sai nghĩa nghiệp vụ không?
- Có giữ **failedMessage, correlationId và requestId** ở error path không?
- Có retry/redelivery ở nhiều tầng gây duplicate, và idempotency key ổn định qua các lần thử không?
- Có xử lý khoảng hở **DB commit → callback → event/file move**, bằng outbox, audit hoặc đối soát bền vững không?
- Khi stop/restart/multiple instances, có kiểm soát file đang xử lý, message store và callback bị bỏ lỡ không?
- Có test commit, rollback, beforeCommit failure, afterCommit failure, async boundary, crash/restart và duplicate không?

## Kết luận

**TransactionSynchronizationFactory** là cơ chế của Spring Integration để phối hợp hành động **theo kết cục transaction khi polling message**. Nó tạo synchronization, có thể dùng **ExpressionEvaluatingTransactionSynchronizationProcessor** để chạy SpEL và gửi message ở các pha **beforeCommit**, **afterCommit**, **afterRollback**. Cơ chế này giúp tách xử lý chính và hậu xử lý, giữ ngữ cảnh message cho chẩn đoán, và hỗ trợ flow kết hợp DB với nguồn không transactional.

Để dùng đúng ở runtime, phải nhìn toàn bộ **thread boundary, transaction manager, retry/recovery, message store, error flow và correlation**. Synchronization không làm file, HTTP, broker thành một transaction duy nhất và không tự bảo đảm callback sống qua crash. Với thao tác cần chắc chắn phát sinh sau commit, hãy kết hợp nguồn sự thật bền vững, idempotency và outbox/reconciliation thay vì dựa duy nhất vào callback.

## Tài liệu tham khảo

- [Spring Integration Reference — Transaction Support và Transaction Synchronization](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration API — DefaultTransactionSynchronizationFactory](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/DefaultTransactionSynchronizationFactory.html)
- [Spring Integration API — ExpressionEvaluatingTransactionSynchronizationProcessor](https://docs.spring.io/spring-integration/docs/6.4.6/api/org/springframework/integration/transaction/ExpressionEvaluatingTransactionSynchronizationProcessor.html)
- [Spring Integration API — IntegrationResourceHolder](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/IntegrationResourceHolder.html)
- [Spring Integration API — TransactionSynchronizationFactoryBean](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/TransactionSynchronizationFactoryBean.html)
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)

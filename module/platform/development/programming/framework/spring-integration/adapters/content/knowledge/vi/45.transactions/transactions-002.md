# TransactionSynchronizationFactory

**Chương:** Transactions  
**Bài học:** TransactionSynchronizationFactory  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Ngôn ngữ:** Tiếng Việt  
**Bối cảnh:** Tích hợp các hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; liên hệ xử lý File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC, chú trọng hợp đồng message, lỗi, giao dịch, tài nguyên và vòng đời kết nối.

> **Điểm cần nhớ:** `TransactionSynchronizationFactory` kết nối **vòng đời transaction** với **hành động phụ thuộc kết quả** của một polling flow: làm gì trước commit, làm gì sau commit và làm gì sau rollback. Nó **không** biến thao tác file, HTTP, SFTP hoặc publish đến broker khác thành một phần của giao dịch database. Muốn đạt độ tin cậy cần hiểu rõ transaction boundary, message được bind vào transaction, lỗi của callback, retry và khả năng đối soát.

## 1. Bài toán: xử lý file xong mới chuyển thư mục

Giả sử một ứng dụng dùng **File inbound channel adapter** đọc tệp CSV từ thư mục `inbox/`, parser tạo Spring Messages, một service activator ghi dữ liệu vào JDBC và sau đó muốn chuyển tệp:

- **Ghi DB commit thành công:** Đưa file vào `processed/`.
- **DB rollback vì lỗi:** Đưa file vào `failed/` hoặc giữ lại nguồn theo chính sách retry.
- **Đang xử lý:** Không để một poller khác lấy lại cùng tệp.

Một cách lập trình ngây thơ:

~~~text
read file
insert database rows
move file to processed/
commit database
~~~

Cách này có thể **chuyển file thành công nhưng DB commit thất bại**. Lần poll tiếp theo không còn thấy file ở `inbox/`, khiến nghiệp vụ bị bỏ sót.

Ta muốn gắn hành động move vào **kết quả transaction**:

~~~mermaid
flowchart TD
    POLL["File inbound poller"] --> TX["Begin JDBC transaction"]
    TX --> READ["Receive File message"]
    READ --> DB["Parse + update database"]
    DB --> DEC{"Transaction outcome?"}
    DEC -->|Commit success| AC["afterCommit: chuyển processed / publish audit"]
    DEC -->|Rollback| AR["afterRollback: chuyển failed / giữ retry"]
    AC --> VERIFY["Kiểm tra kết quả move và log audit"]
    AR --> VERIFY
~~~

Trong Spring Integration, **`TransactionSynchronizationFactory`** là một cơ chế để đăng ký những callback như vậy theo **transaction của poller**. Nhưng phải phân biệt **transaction DB đã commit** với **file move đã thành công**. Nếu file move lỗi trong `afterCommit`, DB không thể tự động rollback trở lại.

### 1.1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò `TransactionSynchronizationFactory`, `TransactionSynchronization`, `TransactionSynchronizationProcessor` và `IntegrationResourceHolder`.
2. Phân biệt `beforeCommit`, `afterCommit`, `afterRollback` và hậu quả khi callback ném exception.
3. Dùng `DefaultTransactionSynchronizationFactory` cùng `ExpressionEvaluatingTransactionSynchronizationProcessor` trong ví dụ Java/XML.
4. Cấu hình synchronization trên **transactional poller**, hiểu `TransactionInterceptor` và `PseudoTransactionManager`.
5. Nhận diện các điểm ngắt transaction khi qua `ExecutorChannel`, `QueueChannel`, một thread khác hoặc API ngoài.
6. Thiết kế file/archive, SFTP, JDBC, HTTP và broker adapters mà không hứa sai về atomicity.
7. Kiểm thử crash windows, retry, idempotency, lỗi của callback, cleanup tài nguyên và vận hành.

## 2. Vị trí của TransactionSynchronizationFactory trong Spring Integration

Spring Integration tổ chức luồng theo **Message**, **MessageChannel**, **MessageHandler** và **MessageSource**. Một poller có thể lấy message từ `MessageSource.receive()`, đưa vào channel rồi chạy các handler phía sau.

Spring Framework có transaction manager và `TransactionSynchronizationManager` để quản lý các synchronization gắn với transaction/thread hiện tại. Spring Integration tận dụng cơ chế đó để gắn **message vừa poll** với các callback.

~~~mermaid
flowchart LR
    SRC["MessageSource/File/JDBC"] --> POLLER["SourcePollingChannelAdapter / poller"]
    POLLER --> INT["TransactionInterceptor"]
    INT --> CH["DirectChannel"]
    CH --> H["Service Activator / JDBC handler"]
    INT --> TSF["TransactionSynchronizationFactory"]
    TSF --> SYNC["TransactionSynchronization"]
    SYNC --> BEFORE["beforeCommit"]
    SYNC --> AFTER["afterCommit"]
    SYNC --> ROLLBACK["afterRollback"]
~~~

**Cần hiểu rõ:** `TransactionSynchronizationFactory` không tự gọi poller, không tự tạo giao dịch và không phải annotation `@Transactional`. Nó tạo synchronization khi polling endpoint đã được cấu hình transaction advice phù hợp.

### 2.1. Những thành phần nền tảng

| Thành phần | Trách nhiệm | Không tự bảo đảm |
| --- | --- | --- |
| `PlatformTransactionManager` | Bắt đầu/commit/rollback transaction do manager quản lý | Không gom tất cả hệ thống ngoài vào một transaction |
| `TransactionInterceptor` | Áp transaction advice lên poll task hoặc method | Không giữ transaction qua thread khác |
| `TransactionSynchronizationFactory` | Tạo `TransactionSynchronization` cho key/resource cụ thể | Không tự quyết định DB hoặc file đã thành công |
| `DefaultTransactionSynchronizationFactory` | Factory mặc định nhận một processor và tạo synchronization | Không mặc nhiên có action phù hợp nghiệp vụ |
| `TransactionSynchronizationProcessor` | Xử lý trước commit, sau commit và sau rollback | Không làm hành động file/SFTP/HTTP trở thành transactional |
| `ExpressionEvaluatingTransactionSynchronizationProcessor` | Thực thi SpEL/đưa kết quả tới channel theo từng phase | Không tự bảo đảm một expression side effect thành công |
| `IntegrationResourceHolder` | Giữ message và tài nguyên/metadata gắn với transaction | Không phải persistent failure store |
| `PassThroughTransactionSynchronizationFactory` | Gắn message được poll vào context hỗ trợ error reporting | Không thực hiện business compensations |
| `PseudoTransactionManager` | Tạo tín hiệu success/failure cho synchronization khi không có resource transactional | Không rollback file/remote request |

### 2.2. Khi nào dùng?

Phù hợp:

- Poll file, ghi DB; **afterCommit** chuyển file thành công.
- Poll JDBC, đồng bộ trạng thái/metrics sau transaction outcome.
- Gọi FTP/SFTP ngoài transaction và muốn **phân nhánh thao tác hậu xử lý** theo success/failure của flow đồng bộ.
- Muốn sau rollback đưa message vào recovery/quarantine đã thiết kế.
- Muốn có original message trong error report khi poller transaction advice ném lỗi.

Không nên dùng làm giải pháp duy nhất cho:

- **Exactly-once xuyên DB và Kafka/RabbitMQ/HTTP**.
- Giao dịch distributed transaction giữa nhiều broker khác loại.
- Callback cần bảo đảm được chạy sau khi process bị kill/crash.
- Retry bền vững kéo dài hàng giờ sau restart.
- Xử lý nghiệp vụ liên quan thao tác đã commit ở remote API.

Những tình huống này cần thêm **idempotency, outbox/inbox, persistent state, retry queue và reconciliation**.

## 3. Hợp đồng API cốt lõi

Giao diện chính có dạng:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;

public interface TransactionSynchronizationFactory {
    TransactionSynchronization create(Object key);
}
~~~

`key` là đối tượng do cơ chế transaction synchronization dùng để liên kết resource; không nên tự giả định `key` luôn chính là payload hoặc business ID. Thông tin Spring Message được truy cập thông qua `IntegrationResourceHolder` trong processor.

`TransactionSynchronizationProcessor` có ba hook:

~~~java
public interface TransactionSynchronizationProcessor {
    void processBeforeCommit(IntegrationResourceHolder holder);
    void processAfterCommit(IntegrationResourceHolder holder);
    void processAfterRollback(IntegrationResourceHolder holder);
}
~~~

Đây là **mô tả giao diện rút gọn** để học API. Trong triển khai thực tế, imports lấy từ `org.springframework.integration.transaction`, còn `TransactionSynchronization` thuộc Spring Framework.

### 3.1. Quan hệ Factory → Synchronization → Processor

~~~mermaid
sequenceDiagram
    participant P as Poller + TransactionInterceptor
    participant F as TransactionSynchronizationFactory
    participant S as TransactionSynchronization
    participant X as TransactionSynchronizationProcessor
    participant D as JDBC/DataSource
    P->>F: create(key)
    F-->>P: synchronization
    P->>S: register / bind resource
    P->>D: poll + handler updates
    alt Commit
        P->>S: beforeCommit
        S->>X: processBeforeCommit(holder)
        P->>D: commit
        P->>S: afterCommit
        S->>X: processAfterCommit(holder)
    else Rollback
        P->>D: rollback
        P->>S: afterCompletion(rolled back)
        S->>X: processAfterRollback(holder)
    end
    P->>S: completion / cleanup
~~~

Sơ đồ mô tả thứ tự logic. Chi tiết callback `beforeCompletion`/`afterCompletion` và lifecycle gắn transaction Spring Framework được quản lý bởi framework; không viết custom code phụ thuộc vào giả định thứ tự giữa các synchronization có cùng order mà chưa kiểm chứng.

### 3.2. DefaultTransactionSynchronizationFactory

Đây là implementation thông dụng: nhận một `TransactionSynchronizationProcessor`, rồi tạo synchronization sẽ gọi processor theo phase.

~~~java
TransactionSynchronizationProcessor processor = /* ứng dụng cấu hình */;
TransactionSynchronizationFactory factory =
        new DefaultTransactionSynchronizationFactory(processor);
~~~

Với lựa chọn mặc định, resource synchronization được xây theo cơ chế cleanup/unbind của Spring Integration. Nếu tự viết factory và synchronization mới, **người triển khai chịu trách nhiệm unbind resource đúng khi transaction hoàn tất**, tránh memory leaks hoặc message context của poll trước bị lẫn sang poll sau.

### 3.3. IntegrationResourceHolder

`IntegrationResourceHolder` chứa Spring Message được poll và các attributes do source/framework đưa vào transaction context.

~~~java
// Trong TransactionSynchronizationProcessor tùy biến:
Message<?> originalMessage = holder.getMessage(); // có thể null tùy ngữ cảnh
Map<String, Object> attributes = holder.getAttributes();
~~~

Không lầm holder với `MessageStore` bền vững. Holder phục vụ **transaction context của thread hiện tại**; sau khi transaction kết thúc nó phải được dọn đúng.

## 4. Ba phase: trước commit, sau commit, sau rollback

| Phase | Thời điểm | Điều phù hợp | Rủi ro phải test |
| --- | --- | --- | --- |
| **beforeCommit** | Trước khi resource transaction được commit | Validate final invariant; phát hiện lỗi để rollback | Side effect bên ngoài đã xảy ra không tự undo |
| **afterCommit** | Sau khi DB/transaction manager thông báo commit thành công | Archive file, publish audit/signal best effort, schedule post-commit job | Callback lỗi **không đảo ngược commit** |
| **afterRollback** | Sau khi rollback được xác nhận qua completion | Quarantine/đánh dấu thất bại, alert, chuẩn bị retry | Action này cũng có thể lỗi; không giả rằng rollback file đã diễn ra |

### 4.1. beforeCommit khác afterCommit

**`beforeCommit`** còn ở trong lifecycle có thể khiến giao dịch bị rollback nếu callback ném exception phù hợp. Nó hữu ích để validate **invariant** trước khi hoàn tất.

**`afterCommit`** chạy khi transaction DB đã commit. Nếu callback chuyển file không thành công, **không thể biến JDBC transaction vừa commit thành rollback** chỉ bằng ném exception từ callback. Cần compensating action hoặc retry từ failure state.

### 4.2. afterRollback không phải rollback filesystem

Khi transaction DB rollback, callback `afterRollback` có thể thực hiện `Files.move(...)` hay publish error message. Chính các tác vụ này **không nằm trong một rollback tương ứng của filesystem**.

Nếu chuyển file vào `failed/` không thành công, ứng dụng phải ghi log/alert và giữ đường retry rõ. Với source filter accept-once hoặc SFTP download metadata, một lần rollback JDBC **không đảm bảo** filter/source đã cho phép file được đọc lại.

### 4.3. Callback luôn chạy khi process bị kill?

Không. Nếu JVM bị kill -9, máy chủ crash, pod bị terminate đột ngột hoặc process mất điện, in-memory callback chưa chạy **có thể không bao giờ chạy**.

~~~text
JDBC COMMIT thành công
   |
   +-- JVM crash trước afterCommit(file.move)
   |
   +-- File vẫn nằm ở inbox, DB đã có dữ liệu.
~~~

Do đó cần **startup reconciliation**, idempotent file handling và database evidence. Đối với nghiệp vụ quan trọng, đừng phụ thuộc callback hậu commit là **cơ chế duy nhất** cho công việc bắt buộc phải được làm.

## 5. Transaction boundary: thread quyết định hiệu lực

Trong Spring Framework, transaction context thường gắn với **thread** đang chạy. Một polling flow với `DirectChannel` giữ same-thread sẽ cho phép nhiều handler tham gia cùng transaction khi dùng transaction manager/resource phù hợp.

~~~text
Thread poller:
  TransactionInterceptor begins
    MessageSource.receive()
    DirectChannel.send(message)
      transformer
      service activator
      JDBC update
  beforeCommit
  JDBC commit
  afterCommit
~~~

### 5.1. ExecutorChannel phá boundary

~~~text
Thread A (poller transaction):
    MessageSource.receive()
    ExecutorChannel.send(message)
    send() returns after scheduling
    JDBC transaction A commits
    afterCommit runs

Thread B (worker):
    handler starts later
    JDBC update throws
~~~

`afterCommit` ở thread A có thể đã chuyển file sang `processed/` trong khi handler trên thread B vẫn chưa xong. Đây là một **lỗi kiến trúc**, không phải do callback “chạy sớm”.

### 5.2. Các ranh giới cần đánh dấu trên sơ đồ

| Cơ chế | Transaction có tự đi qua không? |
| --- | --- |
| `DirectChannel` đồng bộ | Thường giữ same-thread transaction context |
| `ExecutorChannel` | **Không** tự truyền transaction thread-local |
| `QueueChannel` với một poller tiêu thụ sau | Tạo boundary mới; cần transaction/handoff riêng |
| Scheduled/async task `@Async` | Transaction riêng nếu được khai báo |
| JMS/AMQP/Kafka outbound publish | Transaction DB không tự bao trùm broker |
| HTTP/SFTP outbound | Không tự rollback theo JDBC |
| Reactive flow | Phụ thuộc reactive transaction context/manager, không suy từ thread-local truyền thống |

**Nguyên tắc:** Vẽ ranh giới tại thời điểm message được handoff sang thread/resource khác. Chỉ gắn hành động `afterCommit` với những tác vụ **thực sự nằm trong transaction được giám sát**.

### 5.3. Timeout và long-running transaction

Đưa một HTTP call kéo dài 30 giây vào handler cùng thread poller có thể giữ DB transaction/connection và lock trong suốt thời gian chờ. Khi downstream thường xuyên chậm, cân nhắc tách:

1. DB transaction ngắn để claim input và ghi outbox.
2. Commit cùng trạng thái bền.
3. Outbound worker gửi HTTP/Kafka độc lập.
4. Dùng retries/idempotency/reconciliation, không giữ JDBC transaction dài.

## 6. XML: cấu hình synchronization theo ví dụ chuẩn

Spring Integration hỗ trợ namespace XML cho transaction synchronization ở poller. Ví dụ mô tả việc poll file, xử lý đồng bộ và phân nhánh theo transaction:

~~~xml
<!-- Chỉ là mảnh cấu hình: cần namespace, beans, file filter,
     database transaction manager và channels trong ứng dụng thật. -->
<int-file:inbound-channel-adapter
        id="inputDirPoller"
        channel="processFileChannel"
        directory="/var/app/inbox"
        filter="fileFilter">
    <int:poller fixed-rate="5000" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"
                synchronization-factory="fileSyncFactory" />
    </int:poller>
</int-file:inbound-channel-adapter>

<int:transaction-synchronization-factory id="fileSyncFactory">
    <int:after-commit
            expression="payload.renameTo(new java.io.File('/var/app/processed/' + payload.name))"
            channel="fileCommitResultChannel" />
    <int:after-rollback
            expression="payload.renameTo(new java.io.File('/var/app/failed/' + payload.name))"
            channel="fileRollbackResultChannel" />
</int:transaction-synchronization-factory>
~~~

**Quan trọng về kết quả expression:** `java.io.File.renameTo()` trả về **Boolean**. Với `expression` và `channel`, channel nhận **kết quả expression** làm payload, không mặc nhiên nhận File gốc. `Boolean.FALSE` nghĩa là việc rename **đã thất bại**, nhưng có thể **không có exception** nào được ném.

### 6.1. Tại sao ví dụ XML chưa đủ cho production?

Nó chưa giải quyết:

- Cross-filesystem move, destination đã tồn tại, permission, path traversal.
- File đang được poll bởi nhiều instances, accept-once metadata và khóa file.
- Khi rollback, file bị move vào `failed/` có còn đường retry được phê duyệt không?
- Khi `afterCommit` chưa chạy vì crash, có job đối soát file/DB không?
- Nếu một file chứa nhiều records, khi nào cả file thực sự hoàn tất?
- Kết quả rename `false` được alert/ghi failure ở đâu?
- Idempotency của DB khi đọc lại file và có trùng bản ghi.

### 6.2. Muốn gửi message gốc thay vì Boolean?

Theo semantics của expression processor, nếu chỉ cấu hình **channel** mà không có expression thì message được nhận có thể được gửi tới channel đó; nếu dùng expression `payload`, payload được đánh giá là payload gốc, không phải kết quả rename.

~~~xml
<int:transaction-synchronization-factory id="auditSyncFactory">
    <int:after-commit channel="afterCommitAuditChannel" />
    <int:after-rollback channel="afterRollbackAuditChannel" />
</int:transaction-synchronization-factory>
~~~

Đây là **một lựa chọn cấu hình độc lập**. Đừng đồng thời xem `Boolean` do rename sinh ra là Spring Message gốc trong consumer; hãy kiểm tra type và headers thật bằng test.

### 6.3. before-commit

~~~xml
<int:transaction-synchronization-factory id="validatedSyncFactory">
    <int:before-commit
            expression="@fileAuditValidator.validate(payload)"
            channel="beforeCommitAuditChannel" />
    <int:after-commit channel="committedChannel" />
    <int:after-rollback channel="rolledBackChannel" />
</int:transaction-synchronization-factory>
~~~

`fileAuditValidator` là bean **do ứng dụng định nghĩa**. Nếu validation cần bảo đảm rollback, bean nên **ném exception** khi không hợp lệ, thay vì chỉ trả `false` và hy vọng framework tự rollback. Không dùng `beforeCommit` để gọi một API có side effect không thể undo trừ khi nghiệp vụ đã chấp nhận rủi ro.

## 7. Java config: tạo factory bằng processor

Có thể tự cấu hình `DefaultTransactionSynchronizationFactory` và `ExpressionEvaluatingTransactionSynchronizationProcessor` bằng Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.ExpressionEvaluatingTransactionSynchronizationProcessor;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class FileSynchronizationConfig {

    @Bean
    TransactionSynchronizationFactory fileSyncFactory(
            MessageChannel afterCommitFileChannel,
            MessageChannel afterRollbackFileChannel) {

        var parser = new SpelExpressionParser();
        var processor =
                new ExpressionEvaluatingTransactionSynchronizationProcessor();

        // Expression dùng original Message làm evaluation root.
        processor.setAfterCommitExpression(
                parser.parseExpression("payload"));
        processor.setAfterCommitChannel(afterCommitFileChannel);

        processor.setAfterRollbackExpression(
                parser.parseExpression("payload"));
        processor.setAfterRollbackChannel(afterRollbackFileChannel);

        return new DefaultTransactionSynchronizationFactory(processor);
    }
}
~~~

Mã tạo factory/processor **không tự gắn vào poller**. Phải cấu hình transactional poller sử dụng factory này, ví dụ thông qua `synchronization-factory` trong XML hoặc khả năng tương ứng của Java DSL/endpoint API theo **Spring Integration version** dự án.

`afterCommitFileChannel` và `afterRollbackFileChannel` phải là các **MessageChannel beans hợp lệ** có consumer. Tham số injection có thể cần `@Qualifier` khi trong context có nhiều bean cùng kiểu.

### 7.1. Chọn action theo channel thay vì side effect trong SpEL

Một chiến lược dễ kiểm thử hơn:

~~~text
Transaction callback
  -> publish original File message to afterCommitFileChannel
  -> FileLifecycleHandler
  -> Files.move(verifiedSource, verifiedDestination)
  -> persist file move outcome + metrics
~~~

Nhưng một `MessageChannel` **trong bộ nhớ** vẫn không tạo durability cho callback. Nếu thao tác chuyển file là bắt buộc, sau JDBC commit cần có **bản ghi công việc hậu commit bền** hoặc startup reconciliation để không bỏ sót.

### 7.2. Side effect trong SpEL không phải default tốt

Expression `payload.renameTo(...)` ngắn gọn, tiện minh họa. Trong ứng dụng lớn:

- Business rules/path validation nên nằm trong một service có unit tests.
- Mọi move phải kiểm tra kết quả, không chỉ log "afterCommit called".
- File operation nên dùng `java.nio.file.Files.move` với xử lý lỗi rõ và chiến lược atomic move/cross-filesystem.
- Service có thể ghi failure record, nhưng failure record của action post-commit phải **không tự nhận mình thuộc transaction DB đã hoàn thành**.

## 8. Processor tùy biến: kiểm soát callback bằng Java

`ExpressionEvaluatingTransactionSynchronizationProcessor` phù hợp với một số tác vụ SpEL đơn giản. Nếu cần business rule, logging có cấu trúc, idempotency, file path validation hoặc nhiều nhánh trạng thái, có thể cài đặt `TransactionSynchronizationProcessor`.

### 8.1. Ví dụ custom processor

~~~java
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.integration.transaction.TransactionSynchronizationProcessor;
import org.springframework.messaging.Message;

final class AuditedFileSynchronizationProcessor
        implements TransactionSynchronizationProcessor {

    private final FileLifecycleService fileLifecycleService;

    AuditedFileSynchronizationProcessor(
            FileLifecycleService fileLifecycleService) {
        this.fileLifecycleService = fileLifecycleService;
    }

    @Override
    public void processBeforeCommit(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.validateBeforeCommit(message);
    }

    @Override
    public void processAfterCommit(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.onDatabaseCommitted(message);
    }

    @Override
    public void processAfterRollback(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.onDatabaseRolledBack(message);
    }

    private static Message<?> requireMessage(IntegrationResourceHolder holder) {
        Message<?> message = holder.getMessage();
        if (message == null) {
            throw new IllegalStateException(
                    "Transaction synchronization message is missing");
        }
        return message;
    }
}
~~~

`FileLifecycleService` là **interface/service tự viết** trong application; không phải một API của Spring Integration. Tách service giúp kiểm thử độc lập SpEL và lưu kết quả hậu commit vào nơi được quản trị.

### 8.2. Đưa processor vào factory

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;

@Configuration
class CustomSynchronizationConfig {

    @Bean
    TransactionSynchronizationFactory auditedSynchronizationFactory(
            FileLifecycleService fileLifecycleService) {

        return new DefaultTransactionSynchronizationFactory(
                new AuditedFileSynchronizationProcessor(fileLifecycleService));
    }
}
~~~

Thay processor là một chuyện; **chọn transaction manager, cấu hình poller và gắn factory vào poller** là chuyện khác. Nếu poller không có transaction advice phù hợp, đừng chờ callback hoạt động.

### 8.3. Lựa chọn xử lý ngoại lệ của service

`validateBeforeCommit` có thể ném exception nhằm ngăn DB commit. Nhưng:

- `onDatabaseCommitted` ném exception **không đảo ngược DB commit**.
- `onDatabaseRolledBack` ném exception không làm rollback lần thứ hai; có thể che lấp lỗi gốc nếu không kiểm soát.
- Nếu callback side effect thất bại, cần ghi signal/error độc lập và cơ chế retry phục hồi.
- Không dùng `catch (Exception ignored)` cho bước mà nghiệp vụ yêu cầu hoàn tất bắt buộc.

Giới hạn callback cũng áp dụng cho processor tùy biến: **crash trước khi hook chạy thì hook có thể không chạy**.

## 9. Tự triển khai TransactionSynchronizationFactory: khi nào cần?

Giao diện factory cho phép:

~~~java
TransactionSynchronization create(Object key);
~~~

Trong phần lớn tình huống, **`DefaultTransactionSynchronizationFactory` + processor** đã đủ. Tự cài đặt factory chỉ nên cân nhắc nếu cần synchronization đặc biệt mà framework mặc định không đáp ứng, ví dụ lifecycle tài nguyên nguồn rất riêng.

### 9.1. Trách nhiệm bổ sung của factory tùy biến

1. Tạo đúng `TransactionSynchronization` cho key/resource tương ứng.
2. Gắn, truy xuất và unbind `IntegrationResourceHolder` đúng lúc.
3. Thực hiện cleanup khi commit, rollback, exception và completion.
4. Tránh dùng shared mutable holder giữa các polling threads.
5. Không rò message/payload/connection qua `ThreadLocal`.
6. Tôn trọng thứ tự callbacks và transaction completion semantics.
7. Không thay đổi business outcome bằng cách nuốt một exception cần rollback.
8. Viết test cho concurrent pollers và restart/error scenarios.

### 9.2. Vì sao unbind rất quan trọng?

Nếu một custom synchronization quên unbind resource, thread trong pool có thể được tái sử dụng cho **message kế tiếp** nhưng vẫn mang metadata của message trước. Kết quả có thể là:

- `afterCommit` chuyển nhầm file.
- `ErrorMessage` tham chiếu nhầm `failedMessage`.
- Memory leak khi giữ payload lớn.
- Dữ liệu tenant A bị ghi log trong hoạt động tenant B.

Framework mặc định dùng cơ chế resource synchronization để dọn bound resource, với `shouldUnbindAtCompletion()` thích hợp. Đừng thay mặc định bằng custom code khi chưa có nhu cầu thực sự và test tương ứng.

## 10. Poller transaction và sự khác nhau với @Transactional

Spring Integration có nhiều điểm khởi tạo flow:

- **User-initiated:** Controller gọi gateway, service gọi `channel.send()`.
- **Daemon-initiated:** Scheduler hoặc **poller** gọi `MessageSource.receive()` định kỳ.
- **Message-driven adapter:** Broker/listener gọi vào flow khi có delivery.

Với user-initiated flow, một Spring service có `@Transactional` có thể xác định transaction boundary. Với poller, **polling task** không được caller bên ngoài bao bằng transaction sẵn; Spring Integration cho phép gắn transaction advice vào poller để bao luôn bước `receive()` (khi source là tài nguyên có khả năng transaction).

### 10.1. Phân biệt poller transaction và handler transaction

| Tiêu chí | Transaction của poller | `@Transactional` trên handler |
| --- | --- | --- |
| Bắt đầu | Trước/bao quanh poll task | Khi proxy gọi method |
| Có bao `receive()`? | Có thể có | Thường **không** |
| Gắn message source metadata | Cơ chế poller/synchronization | Không tự có |
| Xử lý nhiều handlers cùng thread | Có thể trong cùng transaction | Tùy propagation và proxy |
| Đổi thread | Boundary kết thúc ở handoff | Context không tự chuyển theo |
| File/SFTP rollback | Không tự transactional | Cũng không tự transactional |

### 10.2. Không nên lồng transaction mù quáng

Nếu poller đã dùng `DataSourceTransactionManager` và handler gọi service `@Transactional(propagation = REQUIRES_NEW)`, service có thể commit một transaction **khác**. Khi poller transaction sau đó rollback, bản ghi trong transaction mới có thể vẫn tồn tại.

Do đó **afterRollback của poller không có nghĩa toàn bộ downstream DB writes đã rollback** nếu handler tự mở transaction mới hoặc dùng datasource/manager khác.

### 10.3. Transaction advice trong advice-chain

Khi cần thêm advice (rate-limit, retry, metrics), Spring Integration có thể dùng `<advice-chain>` với transaction advice trong poller. **Thứ tự advice** quyết định phần nào được bao transaction và callback quan sát outcome nào.

~~~text
TX advice bao Retry advice:
    một transaction có thể bao toàn bộ attempts;
    một lỗi có thể đánh dấu rollback-only.

Retry advice bao TX advice:
    từng attempt có thể có transaction riêng.
~~~

Đây là sơ đồ **ý nghĩa thường gặp của advice nesting**, không khẳng định mọi cấu hình tương đương. Đặc biệt với JDBC, một transaction đã bị mark rollback-only không thể “chữa lành” chỉ bằng retry trong cùng transaction. Phải test thứ tự thực tế và `UnexpectedRollbackException`.

## 11. PseudoTransactionManager: tín hiệu có, rollback tài nguyên không có

Spring Integration cung cấp `PseudoTransactionManager` cho trường hợp **không có transactional resource thật**, nhưng vẫn muốn sử dụng callbacks theo kết quả flow.

Ví dụ:

~~~text
File inbound -> validate -> SFTP outbound
    Success: chuyển local file sang sent/
    Failure: chuyển local file sang retry/ hoặc failed/
~~~

File system và SFTP server không tự tham gia JDBC transaction; `PseudoTransactionManager` cung cấp mô hình **begin/success/failure** để chạy hooks.

### 11.1. XML bean minh họa

~~~xml
<bean id="pseudoTransactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager" />

<int-file:inbound-channel-adapter
        id="filesForUpload"
        directory="/var/app/to-send"
        channel="uploadChannel">
    <int:poller fixed-delay="1000">
        <int:transactional
                transaction-manager="pseudoTransactionManager"
                synchronization-factory="fileSyncFactory" />
    </int:poller>
</int-file:inbound-channel-adapter>
~~~

### 11.2. Ý nghĩa thật của pseudo transaction

| Sự kiện | PseudoTransactionManager làm gì? |
| --- | --- |
| Flow đồng bộ trả thành công | Truyền tín hiệu lifecycle cho commit callbacks |
| Flow đồng bộ ném lỗi theo rollback rule | Truyền tín hiệu rollback callbacks |
| Đã upload file SFTP rồi callback khác lỗi | **Không** undo upload |
| JVM crash trong khi upload | Không có rollback/cleanup tự động được bảo đảm |
| Network timeout sau remote success | Không biết remote đã ghi file hay chưa |

**Không được** giải thích "đã dùng pseudo transaction nên File/SFTP/HTTP an toàn như JDBC". Một pseudo transaction là **cơ chế đồng bộ hóa callbacks**, không phải XA hay transactional filesystem.

### 11.3. Giải pháp bổ sung cho file transfer

- Upload tệp tới **temporary remote name**, rồi rename khi đã hoàn tất truyền và kiểm tra checksum/quy ước.
- Dùng stable transfer ID để phát hiện upload trùng sau timeout.
- Ghi **transfer manifest** bền vững hoặc trạng thái công việc để đối soát restart.
- Chỉ archive local source khi có bằng chứng upload theo contract.
- Quản lý cleanup tệp tạm và remote file lifecycle riêng.

Không nên dựa hoàn toàn vào `afterCommit` để xác nhận tệp remote đã hoàn chỉnh; cần kiểm tra API/protocol và vận hành thực tế.

## 12. PassThroughTransactionSynchronizationFactory

Từ Spring Integration 5.0, khi polling endpoint có `TransactionInterceptor` trong advice chain nhưng không khai báo `TransactionSynchronizationFactory`, framework có thể tự áp `PassThroughTransactionSynchronizationFactory` để bind message đã poll vào transaction context.

### 12.1. Nó giải quyết vấn đề gì?

Khi transaction advice ném exception sau khi message đã được poll, error flow có thể nhận `MessagingException` mang **`failedMessage`**, từ đó biết **message nào gây ra lỗi**, thay vì chỉ thấy một raw exception không có input context.

~~~text
Poller receives Message M
 -> transaction advice / handler fails
 -> MessagingException with failedMessage=M
 -> ErrorMessage(payload=MessagingException)
 -> errorChannel / failure handler
~~~

Đường truyền exception/error channel còn phụ thuộc poller error handler và endpoint configuration; sơ đồ là **một đường khả dĩ được framework hỗ trợ**, không phải mọi message đều đi global error channel.

### 12.2. Nó không làm gì?

`PassThroughTransactionSynchronizationFactory` **không thay** `DefaultTransactionSynchronizationFactory` với custom before/after action khi bạn cần move file hoặc gọi audit service. Nó chủ yếu phục vụ **liên kết resource context**, không tự archive hoặc quarantine message.

### 12.3. Điều cần test

- Nếu advice có `TransactionInterceptor`, `failedMessage` được giữ khi lỗi.
- Với custom transaction advice **không phải** `TransactionInterceptor`, có thể cần cấu hình pass-through factory theo tài liệu phiên bản.
- Khi exception xảy ra trước khi có message được poll, `failedMessage` có thể null.
- Không dùng raw `failedMessage.toString()` để log dữ liệu nhạy cảm.

## 13. File inbound: kết hợp JDBC transaction và file lifecycle

Đây là tình huống sử dụng nổi bật của transaction synchronization. Một file chứa danh sách đơn hàng được poll, DB là **transactional resource chính**, còn file move là một **synchronized side effect**.

### 13.1. Các trạng thái tệp cần phân biệt

~~~text
DISCOVERED
   -> CLAIMED
   -> PARSING
   -> DATABASE_COMMITTING
   -> DATABASE_COMMITTED
   -> ARCHIVE_PENDING
   -> ARCHIVED

Nếu lỗi:
   -> DATABASE_ROLLED_BACK
   -> RETRY_PENDING / QUARANTINED
~~~

`ARCHIVE_PENDING` hữu ích: nó nói DB đã commit nhưng file có thể chưa chuyển. Nếu app crash trong khoảng này, một **reconciliation job** dựa DB evidence và file metadata có thể hoàn tất archive mà không tạo bản ghi nghiệp vụ trùng.

### 13.2. Tại sao không move file trước commit?

~~~text
T0: FileSource poll file F
T1: parser tạo records
T2: JDBC INSERT records
T3: file move to processed/
T4: JDBC commit fails

Kết quả:
    file không còn ở inbox
    data chưa commit
    không có nguồn xử lý lại nếu thiếu recovery
~~~

Dùng `afterCommit` giảm một cửa sổ lỗi, nhưng lại tạo cửa sổ ngược:

~~~text
T0: JDBC commit succeeds
T1: JVM crash
T2: afterCommit file move not run

Kết quả:
    DB đã có data
    file vẫn ở inbox
    poll lại có thể sinh duplicate
~~~

**Do đó cần cả hai:** callback có thời điểm hợp lý **và** idempotency/reconciliation.

### 13.3. File.renameTo so với Files.move

`File.renameTo()` có thể thất bại và trả `false` mà không ném exception; behavior khi cross-device phụ thuộc filesystem. Trong production, `Files.move` với options phù hợp cho phép xử lý exceptions rõ hơn.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class SafeFileMover {

    void moveAfterCommit(Path source, Path destination) throws IOException {
        Path normalizedSource = source.toAbsolutePath().normalize();
        Path normalizedDest = destination.toAbsolutePath().normalize();

        // Policy khác phải xác minh trusted root, file owner và scope.
        Files.createDirectories(normalizedDest.getParent());
        Files.move(normalizedSource, normalizedDest,
                StandardCopyOption.ATOMIC_MOVE);
    }
}
~~~

`ATOMIC_MOVE` có thể bị filesystem từ chối (`AtomicMoveNotSupportedException`) hoặc behavior khác theo provider; cần fallback có kiểm soát. **Ví dụ chỉ minh họa API**: production phải chống path traversal/symlink, collision, cross-filesystem, xử lý source/destination tồn tại và idempotent recovery.

### 13.4. Một file chứa nhiều records

Nếu splitter phát 100 messages, trong đó 99 thành công và 1 thất bại, transaction của **một polled File message** có thể khác transaction của **từng record** sau splitter hoặc thread boundary.

Đừng chỉ dùng callback archive toàn file dựa trên kết quả một handler. Cần quy định:

- **All-or-nothing file:** Chỉ archive khi cả 100 records commit trong transaction/processing boundary phù hợp.
- **Per-record processing:** Theo dõi từng record outcome bằng key/line ID; archive file khi đã có bằng chứng tất cả records hoàn tất hoặc vào quarantine.
- **Out-of-order processing:** Không dùng một high-watermark đơn giản nếu records có thể lỗi và đến sai thứ tự.

## 14. SFTP inbound và remote file lifecycle

SFTP adapter có thể **download remote file về local directory** hoặc cung cấp streaming message tùy loại endpoint. Vì vậy kiểu payload và metadata không giống `File` inbound adapter trong mọi trường hợp.

### 14.1. Không giả định SpEL payload là java.io.File

~~~text
File inbound:
    payload có thể là java.io.File.

SFTP inbound download:
    có thể nhận local File; remote metadata phụ thuộc adapter/header.

SFTP streaming inbound:
    có thể nhận stream / session-related resource.
~~~

Nếu copy nguyên `payload.renameTo(...)` từ file adapter sang streaming SFTP handler, expression có thể **không hợp lệ** hoặc không quản lý remote file mà người học mong muốn.

### 14.2. Remote rename/move có transaction không?

Không tự động. `TransactionSynchronizationFactory` có thể gọi service dùng SFTP remote rename **sau khi một transaction khác commit**, nhưng remote operation không được rollback tự động nếu bước tiếp theo lỗi.

Ví dụ remote file đã rename sang `archived/` nhưng DB callback sau đó lỗi; hoặc rename timeout trong khi server đã thực hiện. Cần remote file ID, checksum, trạng thái và reconciliation.

### 14.3. Session lifecycle

SFTP streaming phải đóng/giải phóng stream và session theo contract của adapter/consumer, cả success và error. Không giữ session mở suốt thời gian một JDBC transaction dài chỉ để chờ remote chuyển file.

Test:

1. Stream/session có đóng khi handler trả về?
2. Nếu callback afterRollback ném lỗi, session có được cleanup?
3. Có bị duplicate download khi restart hoặc filter metadata reset không?
4. Có tệp tạm chưa hoàn tất sau timeout không?
5. Có khả năng replay remote file nếu source đã bị xóa/move không?

## 15. JDBC inbound polling và transaction đồng bộ

Một JDBC inbound adapter thường poll rows với query `SELECT` và có thể cập nhật status/claim trong cùng transaction nếu cấu hình datasource/transaction manager phù hợp.

~~~text
Poll JDBC rows (NEW)
  -> claim rows (PROCESSING)
  -> DirectChannel
  -> business validation/upsert
  -> beforeCommit checks
  -> DB commit
  -> afterCommit signal/metrics
~~~

### 15.1. beforeCommit để kiểm tra invariant

Một custom processor có thể kiểm tra các điều kiện đã ở trạng thái hợp lệ trước commit, ví dụ batch không còn record `INVALID` bị coi hoàn tất. Nếu không thỏa, ném exception để Spring transaction rollback.

Không lạm dụng `beforeCommit` để thực hiện HTTP POST không có khả năng rollback. Nếu gọi API ngoài thành công nhưng DB commit thất bại, API **vẫn đã thực hiện side effect**.

### 15.2. Row claim và concurrency

Với nhiều pollers, **transaction synchronization không thay thế database locking/unique constraint**:

- `SELECT ... FOR UPDATE` hoặc cơ chế claim được DB hỗ trợ.
- Optimistic version hoặc `UPDATE ... WHERE status='NEW'`.
- Unique business operation key để chống duplicate.
- Lease/timeout cho `PROCESSING` bị kẹt.
- Isolation level theo yêu cầu thực tế.

### 15.3. Ví dụ transaction status table

~~~sql
-- Lược đồ nghiệp vụ minh họa, không phải schema bắt buộc của Spring.
CREATE TABLE inbound_jobs (
    job_id           VARCHAR(128) PRIMARY KEY,
    business_key     VARCHAR(240) NOT NULL,
    input_reference  VARCHAR(400) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    processing_owner VARCHAR(120),
    updated_at       TIMESTAMP NOT NULL,
    UNIQUE (business_key)
);
~~~

Giả sử một job đã commit nhưng `afterCommit` publish message thất bại, status table cho phép reconcile từ **business evidence**, thay vì suy đoán `afterCommit` đã làm xong.

## 16. JMS, AMQP, Kafka: factory có thay transaction broker không?

**Không.** Transaction synchronization ở poller không làm JMS, RabbitMQ hoặc Kafka tự tham gia cùng JDBC transaction nếu không có cơ chế phối hợp được cấu hình và chứng minh.

| Nguồn/đích | Ranh giới cần kiểm tra | Vai trò có thể có của synchronization |
| --- | --- | --- |
| JMS message-driven inbound | JMS session ACK/rollback, container transaction | Theo dõi/đăng ký callback nếu endpoint hỗ trợ; không thay session semantics |
| JMS polling | `receive()` có thể tham gia JMS transaction theo config | Đồng bộ hành động phụ theo transaction poller thích hợp |
| RabbitMQ inbound | ACK/NACK/requeue, listener container transaction | Không tự điều khiển broker DLX chỉ bằng callback |
| RabbitMQ outbound | Publisher confirm/return, routing | AfterCommit có thể kích hoạt publish, nhưng lỗi hậu commit cần recovery |
| Kafka inbound | Offset commit, ack mode, consumer transaction | Factory của polling endpoint không tự quản lý offset container |
| Kafka outbound | Producer ack/future, Kafka transactions | AfterCommit kích hoạt send không đồng nghĩa record đã confirmed |
| JDBC | Local DB commit/rollback theo tx manager | Dùng before/after callbacks gắn đúng transaction DB |

### 16.1. Vì sao afterCommit publish Kafka dễ sai?

~~~text
JDBC transaction commits
    -> afterCommit calls KafkaTemplate.send(event)
    -> send returns future immediately
    -> callback ends
    -> Kafka publish later fails
~~~

DB **đã commit**, event Kafka **chưa có**. Nếu không có outbox, không còn bản ghi công việc bền để retry.

Một cách mạnh hơn là ghi **outbox row trong cùng JDBC transaction**, rồi một worker khác publish Kafka/RabbitMQ và mark SENT sau khi nhận kết quả.

### 16.2. JMS/AMQP source acknowledgment

Sau khi một inbound message-driven adapter giao message vào flow, container sẽ quyết định ACK/rollback theo transaction/config. Nếu một `afterCommit` callback của DB lỗi, không nên tự suy rằng source broker sẽ redeliver: **DB commit và JMS/Rabbit ACK là hai lifecycle riêng**.

Với message-driven adapters, test nên xác nhận nguồn thực sự được ACK/NACK khi flow và callback lỗi. Không kết luận từ một unit test chỉ dùng `DirectChannel`.

### 16.3. Kafka offset và at-least-once

Khi consumer xử lý DB thành công nhưng offset commit thất bại, Kafka có thể redeliver record. Dùng **idempotent receiver** hoặc unique constraint trên business key để không tạo side effect trùng.

Ngược lại, nếu offset commit trước khi có durable handoff vào DB/outbox, crash có thể làm mất event nghiệp vụ. `TransactionSynchronizationFactory` không tự đồng bộ hóa hai commit độc lập thành một atomic operation.

## 17. HTTP inbound/outbound: afterCommit có nghĩa gì?

HTTP API không tham gia JDBC transaction chỉ vì được gọi từ một handler trong transaction. Có hai kịch bản:

### 17.1. HTTP inbound gateway

Một HTTP request đến, service mở JDBC transaction, ghi dữ liệu và trả HTTP response. `@Transactional` ở service xác định transaction của DB; synchronization của poller **không phải** cơ chế chính cho request này vì HTTP inbound là message-driven/request-driven.

Nếu muốn trả response **chỉ sau khi DB commit** hoặc phát event sau commit, cần transaction boundary/response contract thích hợp. Không sử dụng một poller `TransactionSynchronizationFactory` để giải quyết chung mọi HTTP gateway.

### 17.2. HTTP outbound trong polling flow

Nếu poll file → HTTP POST → DB update, thứ tự gọi API/DB và retry có thể gây duplicate:

~~~text
HTTP POST sent and partner commits
Response times out
JDBC transaction rolls back
afterRollback runs
File is retried
HTTP POST sent again
~~~

**Giải pháp:** Stable idempotency key, status query/reconciliation với đối tác, outbox hoặc một state machine theo nghiệp vụ. Một transaction callback không thể "undo HTTP POST" đã commit ở server.

### 17.3. beforeCommit để gọi HTTP?

Thường **không phải** lựa chọn tốt cho thao tác có side effect. Nếu API thành công trước khi DB commit, transaction DB có thể rollback sau đó, gây mismatch. Nếu API thất bại và callback ném lỗi, DB rollback được, nhưng không bảo đảm API chưa commit ở remote.

Với nghiệp vụ quan trọng, nên **commit dữ liệu và outbox local** trước, rồi gửi HTTP ở worker có idempotency/retry.

## 18. Khi callback lỗi: trước commit khác sau commit

Một cấu hình synchronization phải định nghĩa **callback cũng là điểm có thể lỗi**.

### 18.1. beforeCommit ném exception

~~~text
JDBC updates chưa commit
    -> beforeCommit callback validate
    -> callback throws IllegalStateException
    -> transaction rolls back theo cơ chế Spring
    -> afterRollback path có thể thực hiện nếu được đăng ký/hoàn tất phù hợp
~~~

Đây là tình huống **DB transaction vẫn còn khả năng rollback**. Cần kiểm tra exception có được framework propagate và transaction status có rollback hay không, thay vì chỉ nhìn callback đã được gọi.

### 18.2. afterCommit ném exception

~~~text
JDBC commit succeeded
    -> afterCommit callback tries file move
    -> file move throws IOException/IllegalStateException
    -> JDBC data remains COMMITTED
    -> recovery must reconcile file/archive state
~~~

Lỗi trong `afterCommit` có thể được báo tới caller hoặc error handler theo transaction synchronization và endpoint configuration, nhưng **không đảo ngược commit đã hoàn thành**.

**Rủi ro thứ cấp:** Nếu upstream broker nhìn exception này và redeliver trong khi DB đã commit, có thể nhận một message nghiệp vụ **trùng**. Tầng DB phải có idempotency/unique key để xử lý.

### 18.3. afterRollback ném exception

~~~text
JDBC rolls back
    -> afterRollback callback tries file quarantine
    -> destination disk full / permission denied
    -> callback fails
    -> original DB rollback still happened
    -> file needs separate recovery or retry
~~~

Cần giữ **thông tin lỗi gốc** và **lỗi cleanup** một cách phân biệt. Nếu error handler chỉ log stack trace cuối, nguyên nhân nghiệp vụ ban đầu có thể bị che.

### 18.4. Viết lại DB trong afterCommit có an toàn không?

Không nên giả định. Khi `afterCommit` chạy, resource transaction cũ có thể vẫn còn thread-bound trong giai đoạn completion, nhưng **đã không còn commit tiếp cho transaction đó**.

Với thao tác DB hậu commit cần tính bền vững:

- Ưu tiên ghi **outbox row trong transaction chính**, không chờ afterCommit để tạo.
- Nếu thực sự cần một transaction độc lập, dùng một service/proxy có `REQUIRES_NEW` và test failure/retry.
- Không dựa vào một JDBC write trong afterCommit mà thiếu transaction mới rồi cho rằng record đã được commit.

### 18.5. Callback nào không được dùng cho thao tác bắt buộc?

Nếu ứng dụng bắt buộc phải gửi một sự kiện cho một hệ thống đối tác **kể cả khi JVM crash**, `afterCommit` chạy trong memory **không phải hàng đợi công việc bền**. Hãy lưu một bản ghi outbox trong transaction chính, rồi worker phát sau.

## 19. ErrorChannel, ErrorMessage và failedMessage

Spring Integration xử lý lỗi bằng `ErrorMessage`, `errorChannel`, error handler của poller và cơ chế retry/recovery theo endpoint.

### 19.1. Một lỗi có thể xuất hiện ở đâu?

| Ranh giới | Đường lỗi thường gặp |
| --- | --- |
| `DirectChannel` synchronous | Exception lan về caller/poller trong cùng thread |
| Poller task | Error handler có thể publish `ErrorMessage` |
| `ExecutorChannel`/async | Lỗi xảy ra trên thread khác, cần async error handling |
| `TransactionInterceptor` | Exception có thể kích hoạt rollback theo rollback rules |
| `beforeCommit` | Có thể ngăn DB commit bằng exception |
| `afterCommit` | DB đã commit; callback error cần recovery riêng |
| `afterRollback` | DB đã rollback; cleanup failure cần báo riêng |
| Broker listener | Container ACK/rollback/nack phụ thuộc config nguồn |

### 19.2. Original message quan trọng thế nào?

Khi một poll task thất bại, error handler cần biết:

- File nào, row nào hoặc source record nào gây lỗi?
- Message có correlation ID/business operation ID nào?
- Transaction trước đó đã commit hay rollback?
- Có thể replay đúng dữ liệu gốc không?

`PassThroughTransactionSynchronizationFactory` hoặc các out-of-the-box factory phù hợp giúp giữ message trong transactional resource context để một `MessagingException` mang `failedMessage` phục vụ error reporting.

`ErrorMessage` payload có thể là `MessagingException` và `getFailedMessage()` có giá trị khi message đã được bind; **không mặc định lúc nào cũng hiện diện**.

### 19.3. Phân biệt error channel và afterRollback channel

`afterRollbackChannel` trong expression processor phục vụ **notification về transaction completion** theo cấu hình. Nó **không tự** là:

- Hàng đợi bền.
- Broker DLQ.
- Nơi có đủ exception cause nếu expression chỉ trả File hoặc Boolean.
- Cơ chế chỉ huy broker redelivery.

Muốn dead-letter, cần một **error/recovery flow** thực sự persist failure, có owner, retention và replay logic.

### 19.4. Không log raw payload trong callback

Spring Message có thể mang dữ liệu đơn hàng, thông tin cá nhân, token hoặc tài liệu lớn. `Message.toString()` và stack trace ở error handler có thể làm lộ dữ liệu.

Sử dụng:

~~~json
{
  "event": "file.transaction.after_commit.failed",
  "flow": "file-to-jdbc",
  "fileReference": "file-20261123-42",
  "businessOperationId": "batch-T42-971",
  "databaseOutcome": "COMMITTED",
  "fileArchiveOutcome": "FAILED_RETRYABLE",
  "errorCategory": "FILE_MOVE_IO_ERROR",
  "correlationId": "trace-84021"
}
~~~

Schema này là **log do ứng dụng định nghĩa**, không phải output Spring Integration mặc định. Không ghi raw payload hoặc credentials.

## 20. Retry và redelivery: callback có chạy mấy lần?

Đây là câu hỏi quan trọng khi vừa có `TransactionInterceptor` vừa có retry advice/container redelivery.

### 20.1. Một business operation có thể chạy nhiều transaction

~~~text
Source message K
  -> attempt 1, transaction 1 -> rollback -> afterRollback
  -> attempt 2, transaction 2 -> rollback -> afterRollback
  -> attempt 3, transaction 3 -> commit   -> afterCommit
~~~

Đây là một **trường hợp có thể xảy ra** khi retry/transaction được bố trí mỗi attempt một transaction. Không suy rằng một retry policy bất kỳ sẽ tự sinh ba transaction độc lập; nó phụ thuộc thứ tự advice và listener/poller config.

### 20.2. Hệ quả cho callback

- `afterRollback` có thể được gọi **nhiều lần** cho cùng business key qua nhiều attempts.
- `afterCommit` có thể chạy hơn một lần nếu source redeliver sau commit do ACK fail.
- Nếu callback gửi alert mỗi rollback, có thể tạo **alert storm**.
- Nếu callback rename file ngay lần rollback đầu, lần retry thứ hai có thể không còn thấy file.
- Nếu callback tạo event mới với UUID mới mỗi lần, downstream dedupe rất khó.

### 20.3. Idempotent callback

Một callback tốt nên dùng stable operation key:

~~~text
businessKey = tenant + sourceFileGeneration + recordId

afterCommit archive:
    if already archived for businessKey:
        verify checksum/result; return idempotently
    else:
        move safely and persist archive outcome

afterRollback handling:
    record attempt failure with unique attemptId
    preserve businessKey for next retry
~~~

Không dùng `MessageHeaders.ID` làm stable key nếu mỗi redelivery có Spring Message ID khác.

### 20.4. Retry budget tổng

Nếu source broker redeliver 4 deliveries và handler retry 3 attempts trong mỗi delivery, side effect có thể bị gọi **12 lần**, chưa kể retry của HTTP SDK. Bài test phải đếm số request tới **hệ thống ngoài**, không chỉ số callback được gọi.

### 20.5. Lỗi không retry được

Invalid schema, vi phạm quyền truy cập hoặc thiếu business key thường cần **quarantine/alert** thay vì retry vô hạn. Một callback `afterRollback` chỉ nên ghi **trạng thái cần xử lý**; không tự đẩy message quay lại cùng handler vô hạn.

## 21. Idempotency và transactional inbox/outbox

### 21.1. Vì sao TransactionSynchronizationFactory chưa đủ?

Xét hai sự kiện:

1. DB commit thành công nhưng `afterCommit` chưa chạy do crash.
2. `afterCommit` gọi API thành công nhưng response bị mất, sau đó callback retry.

Trong cả hai, không thể khẳng định tính đúng đắn bằng **chỉ một hook**. Cần một cách trả lời "nghiệp vụ đã xảy ra chưa?" bằng **business state bền vững**.

### 21.2. Mẫu transactional inbox

~~~text
Receive message K
    -> trong JDBC transaction:
         insert inbox(K) với unique constraint nếu chưa có
         apply business change
         mark inbox(K, COMPLETED)
    -> commit transaction
    -> source redelivery K:
         read COMPLETED -> không apply lần nữa
~~~

Nếu handler lỗi trước commit, transaction rollback cả inbox và business state theo thiết kế. Không chỉ ghi một marker `seen` ở Redis rồi coi như hoàn tất.

### 21.3. Mẫu transactional outbox

~~~text
Trong JDBC transaction:
    update orders
    insert outbox(eventId, payloadRef, status=PENDING)
commit

Outbox worker:
    read PENDING event
    publish to Kafka/Rabbit/HTTP
    wait for target outcome/confirm theo contract
    mark SENT hoặc RETRY_PENDING/UNKNOWN
~~~

`afterCommit` có thể dùng làm **tín hiệu đánh thức outbox worker** để giảm latency, nhưng **outbox row** mới là nguồn công việc bền qua crash. Nếu tín hiệu đánh thức bị mất, worker vẫn có thể poll outbox.

### 21.4. Schema minh họa

~~~sql
CREATE TABLE inbound_inbox (
    operation_key       VARCHAR(220) PRIMARY KEY,
    payload_fingerprint VARCHAR(128) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    result_reference    VARCHAR(240),
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE outbound_outbox (
    event_id            VARCHAR(220) PRIMARY KEY,
    aggregate_id        VARCHAR(220) NOT NULL,
    destination         VARCHAR(160) NOT NULL,
    payload_reference   VARCHAR(400) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    attempts            INT NOT NULL DEFAULT 0,
    updated_at          TIMESTAMP NOT NULL
);
~~~

Đây là lược đồ **nghiệp vụ minh họa**: cần indexes, locking, cleanup, payload encryption và transaction isolation theo sản phẩm. Nếu cùng event gửi nhiều destinations, khóa unique có thể phải bao `destination`.

### 21.5. Không đồng nhất "sau commit" với "exactly once"

Ngay cả khi outbox được ghi atomically cùng business data, publisher có thể gửi lại sau khi target nhận nhưng trước khi mark `SENT`. Downstream phải có **stable event ID và idempotent receiver**.

## 22. Tình huống thực hành: File → JDBC → Kafka

Hệ thống nhận file doanh thu qua thư mục local được sync từ SFTP. File có nhiều records, cần cập nhật database và phát event Kafka sau khi dữ liệu được xác nhận.

### 22.1. Thiết kế ban đầu (có lỗi)

~~~mermaid
flowchart LR
    F["File poller"] --> DB["JDBC transaction"]
    DB --> COM["Commit"]
    COM --> HOOK["afterCommit"]
    HOOK --> K["Kafka producer send"]
    K --> D["Kafka topic"]
~~~

Nếu callback gọi `send` bất đồng bộ rồi process crash, Kafka có thể chưa nhận record. DB đã commit. Không có outbox, ứng dụng không biết cần gửi lại event.

### 22.2. Thiết kế cải tiến

~~~mermaid
flowchart TD
    FILE["File inbound adapter"] --> POLL["Transactional poller"]
    POLL --> PARSE["Parse/validate"]
    PARSE --> TX["JDBC transaction"]
    TX --> DATA["Upsert business rows"]
    TX --> OB["Insert outbox events"]
    DATA --> COMMIT["DB commit"]
    OB --> COMMIT
    COMMIT --> AC["afterCommit: signal archive worker"]
    AC --> ARCH["Archive file + audit"]
    OB --> WORK["Independent outbox publisher"]
    WORK --> KAFKA["Kafka topic"]
    KAFKA --> CONF["Producer result"]
    CONF --> MARK["Update outbox SENT / UNKNOWN"]
    ARCH --> REC["Startup reconciliation"]
    MARK --> REC
~~~

Điểm khác biệt:

1. **Business rows và outbox được commit cùng transaction DB**.
2. `afterCommit` chỉ hỗ trợ giảm latency của archive/signal; hệ thống có thể **tự rà soát trạng thái sau restart**.
3. Kafka publish do worker riêng đảm nhiệm, kiểm tra result/confirm.
4. Consumer Kafka tiếp nhận bằng idempotent key để chấp nhận redelivery.
5. File được archive với trạng thái bền và có quy trình xử lý khi move fail.

### 22.3. Message contract

~~~yaml
# Hợp đồng ứng dụng minh họa; không phải Spring Integration YAML mặc định.
fileGeneration: "sales-20261123-sha256-example"
batchId: "batch-T42-971"
businessKey: "sales-import:T42:971"
source:
  adapter: "file-from-sftp"
  fileName: "sales-2026-11-23.csv"
database:
  state: "COMMITTED"
fileLifecycle:
  state: "ARCHIVE_PENDING"
kafka:
  outboxEventId: "sales-imported:T42:971"
  state: "PENDING"
~~~

Không nhét toàn bộ các field trên vào một metadata store string rồi tự xem là đã được framework bảo đảm. Đây là **business state machine** do ứng dụng duy trì.

### 22.4. Kịch bản A: xử lý thành công

~~~text
T0  Poll file F
T1  Begin JDBC TX
T2  Parse + validate all rows
T3  Upsert business rows + insert outbox
T4  beforeCommit validation PASS
T5  DB commit succeeds
T6  afterCommit signals archive
T7  Archive file succeeds
T8  Outbox worker publishes Kafka and records outcome
~~~

Điều cần xác minh: data DB, outbox row, file archive, Kafka record, correlation và log/metrics.

### 22.5. Kịch bản B: validation fail

~~~text
T0 Poll file F
T1 Begin JDBC TX
T2 Validate row 42 -> INVALID_SCHEMA
T3 Throw exception
T4 DB rollback
T5 afterRollback -> quarantine or record retry
~~~

Nếu quarantine move lỗi, không xem đó là rollback DB lỗi; cần ghi **secondary failure** và giữ khả năng xử lý lại. Nếu file có dữ liệu cần sửa, cần owner và quy trình correction rõ.

### 22.6. Kịch bản C: crash sau commit

~~~text
T0 DB commit succeeds
T1 JVM crashes before afterCommit
T2 Application restarts
T3 Reconciliation job finds batch DB COMMITTED, file still in inbox
T4 Job archives file idempotently; outbox worker publishes Kafka
~~~

Đây là ca bắt buộc trong thiết kế dựa vào hậu commit. Không nên coi "hook đã được đăng ký" là cam kết hook luôn chạy.

### 22.7. Kịch bản D: Kafka publish đã xảy ra, result mất

~~~text
Kafka broker accepted event
Producer callback/future result lost
Outbox row remains IN_FLIGHT/UNKNOWN
Worker retries with same eventId
Target consumer ignores duplicate business effect
~~~

Không sửa `eventId` mỗi lần retry; nếu làm vậy mất tác dụng dedupe.

## 23. Transaction synchronization và file accept-once filters

File inbound adapters thường dùng **accept-once** hoặc persistent file filters để tránh poll lại cùng file. Filter source có thể ghi nhận file **đã được chọn**, không biết transaction DB ở downstream đã commit hay chưa.

### 23.1. Cửa sổ lỗi

~~~text
File F accepted by persistent filter
JDBC transaction fails
afterRollback executes
File remains in source directory

Next poll:
    file filter says already accepted
    -> F may not be emitted again
~~~

Chỉ cấu hình `afterRollback` không tự reset state của mọi file filter. Nếu cần retry file, phải biết **filter metadata rollback/removal** theo implementation và lựa chọn recovery được kiểm chứng.

### 23.2. Các lựa chọn thiết kế

| Cách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Dùng persistent filter và reset key khi rollback theo contract | Retry lại cùng file | Reset sai làm duplicate hoặc nhiều workers nhận cùng file |
| Chuyển file lỗi vào quarantine | Không làm poller lặp vô hạn | Cần job sửa/replay có owner |
| Lưu per-file processing state trong DB | Có evidence sau restart | Phức tạp hơn, cần transaction/unique key |
| Dùng staging + claim/lease | Giảm competing polls | Phải xử lý stale lease/crash |
| Dùng per-record inbox | Phục hồi từng dòng khi file đã tải | Cần stable record keys và lifecycle file rõ |

Không dùng `Files.move` bất kỳ để “giải phóng filter” khi chưa hiểu remote/local file semantics.

## 24. Các lỗi SpEL và cách phân tích

### 24.1. Sai kiểu payload

Expression:

~~~text
payload.renameTo(new java.io.File('/processed/' + payload.name))
~~~

Chỉ hợp lý khi payload thực sự là `java.io.File`. Với SFTP stream, Kafka ConsumerRecord, HTTP DTO hoặc JDBC Map payload, expression này có thể lỗi kiểu.

Giải pháp: log/inspect **class name an toàn** và test contract mỗi adapter, không ép kiểu dựa vào tên channel.

### 24.2. Expression trả `false` không phải exception

Với `File.renameTo`, result `Boolean.FALSE` có thể vẫn được publish tới afterCommit channel bình thường.

~~~text
afterCommit expression evaluated -> false
channel receives payload=false
no exception thrown
DB already COMMITTED
~~~

Consumer của channel phải **kiểm tra boolean** và phát alert/recovery; test không chỉ assert "message được nhận".

### 24.3. Expression trả null/void

Theo contract của `ExpressionEvaluatingTransactionSynchronizationProcessor`, nếu expression đánh giá thành null/void, **có thể không có message được gửi ra channel** khi đi theo nhánh publish kết quả expression.

Nếu chỉ muốn chuyển message đã nhận tới channel, cấu hình **channel mà không có expression** theo API/namespace hỗ trợ. Test cần soạn rõ payload/headers kỳ vọng.

### 24.4. Sai tên bean trong SpEL

~~~text
@fileLifecycleService.archive(payload)
~~~

Bean name phải tồn tại trong ApplicationContext/EvaluationContext phù hợp; method cũng phải cho phép invocation. Tránh cài SpEL từ input không tin cậy, vì đây là **mã biểu thức có khả năng gọi phương thức/bean**.

### 24.5. Thiếu original message

Khi poller chưa nhận được message hoặc transaction context chưa được bind, `holder.getMessage()` có thể null. Một custom processor không nên tự bịa business key. Hãy:

- Ghi error category `MISSING_POLLED_MESSAGE_CONTEXT`.
- Có fallback nguồn metadata/trace đáng tin nếu được thiết kế.
- Bảo đảm không ACK/quarantine nhầm message khác.
- Kiểm tra resource cleanup của custom factory.

## 25. Kiểm thử đơn vị cho processor tùy biến

Để kiểm tra logic callback, có thể test `TransactionSynchronizationProcessor` độc lập với poller. Ví dụ dùng Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.mockito.Mockito.*;

class AuditedFileSynchronizationProcessorTest {

    @Test
    void callsAfterCommitServiceWithOriginalMessage() {
        FileLifecycleService service = mock(FileLifecycleService.class);
        var processor = new AuditedFileSynchronizationProcessor(service);

        Message<String> message = MessageBuilder
                .withPayload("file-reference-123")
                .setHeader("businessOperationId", "batch:T42:971")
                .build();
        IntegrationResourceHolder holder = new IntegrationResourceHolder();
        holder.setMessage(message);

        processor.processAfterCommit(holder);

        verify(service).onDatabaseCommitted(message);
        verify(service, never()).onDatabaseRolledBack(any());
    }

    @Test
    void callsRollbackServiceWithOriginalMessage() {
        FileLifecycleService service = mock(FileLifecycleService.class);
        var processor = new AuditedFileSynchronizationProcessor(service);

        Message<String> message = MessageBuilder.withPayload("file-ref")
                .build();
        IntegrationResourceHolder holder = new IntegrationResourceHolder();
        holder.setMessage(message);

        processor.processAfterRollback(holder);

        verify(service).onDatabaseRolledBack(message);
        verify(service, never()).onDatabaseCommitted(any());
    }
}
~~~

`FileLifecycleService` là interface/service **do ứng dụng định nghĩa** như trong ví dụ trước. Mockito/JUnit cần dependencies test thích hợp.

**Giới hạn của test:** Gọi trực tiếp `processAfterCommit()` **không chứng minh transaction thật đã commit** hoặc framework đã đăng ký callback đúng. Muốn kiểm tra transaction lifecycle phải chạy **integration test với poller + transaction manager thật**.

### 25.1. Test validation trước commit

~~~java
FileLifecycleService service = mock(FileLifecycleService.class);
doThrow(new IllegalStateException("file contract invalid"))
        .when(service).validateBeforeCommit(any());

assertThrows(IllegalStateException.class,
        () -> processor.processBeforeCommit(holder));
~~~

Bài test này chứng minh processor propagate lỗi. Test tích hợp cần chứng minh **JDBC transaction rollback** theo đúng config/proxy.

### 25.2. Không mock message chứa toàn bộ dữ liệu nhạy cảm

Tạo fixture chỉ có payload reference và headers tối thiểu. Test xác nhận error logs không ghi raw PII, access token, file content hay SQL credentials.

## 26. Integration test: transaction thật và file thật

Một bộ kiểm thử chất lượng cần chứng minh rằng **poller transaction thực sự đăng ký synchronization**, và callback chạy **đúng phase sau JDBC commit/rollback**.

### 26.1. Test environment

Các thành phần:

- Spring Test/JUnit 5, một context riêng cho test.
- `FileReadingMessageSource` hoặc file inbound adapter thật trỏ vào temporary directory.
- Poller có `TransactionInterceptor` và `TransactionSynchronizationFactory` được cấu hình.
- `DataSourceTransactionManager` cùng H2 hoặc database test.
- `DirectChannel` trong phần flow muốn nằm cùng transaction.
- Fake business service có thể throw exception ở điểm chọn.
- `afterCommit`/`afterRollback` handler ghi trạng thái quan sát được.
- Bounded wait thay vì sleep cố định.

Nếu dùng embedded database chỉ để test logic, cần hiểu **H2 không tái hiện tất cả semantics** của PostgreSQL/Oracle/MySQL về lock/isolation và crash recovery. Đối với concurrency quan trọng, thêm integration test database thật qua container.

### 26.2. Test case T1: commit thành công

~~~text
Given:
    temp file F.csv hợp lệ
    DB trống
    transactional poller + synchronization factory active

When:
    poller nhận F
    service writes DB rows
    transaction commits

Then:
    DB rows tồn tại
    afterCommit chạy theo thiết kế
    afterRollback không chạy
    file archive được xác minh
    metadata/correlation nhất quán
~~~

Không chỉ verify `afterCommit` method được gọi: kiểm tra file thực sự ở destination và source không còn (hoặc đúng trạng thái khi dùng copy+archive).

### 26.3. Test case T2: business lỗi trước commit

~~~text
Given:
    temp file F.csv
    service writes first row then throws RuntimeException

When:
    poller chạy trong JDBC transaction

Then:
    JDBC row count như trước transaction
    afterRollback được xử lý theo cấu hình
    afterCommit không chạy
    source file có thể recover/replay
~~~

### 26.4. Test case T3: beforeCommit fail

~~~text
Given:
    JDBC handler chạy thành công
    beforeCommit validator throws

Then:
    JDBC transaction rolls back
    afterCommit not executed
    failed message context available when configured
    failure handling has durable record or safe source retention
~~~

### 26.5. Test case T4: afterCommit fail

~~~text
Given:
    JDBC commit succeeds
    Files.move throws IOException

Then:
    JDBC rows remain committed
    file archive state remains pending/failed
    alert/reconciliation exists
    no false rollback claim
~~~

Đây là **test phân biệt hai sự thật**: DB commit đã thành công và file archive chưa xong.

### 26.6. Test case T5: crash sau commit

Với container/process riêng:

1. Commit DB và ghi `ARCHIVE_PENDING`.
2. Dừng process trước khi callback file move.
3. Khởi động lại bridge.
4. Chạy reconciliation.
5. Xác nhận file được archive **mà không insert DB trùng**.

Không thể mô phỏng chính xác crash bằng cách ném exception trong callback: lúc đó JVM còn sống và lifecycle callbacks có thể tiếp tục chạy. Cần ít nhất một **restart/failure-injection test** trong môi trường cách ly cho guarantee quan trọng.

## 27. Test matrix theo adapter

| Adapter | Thất bại cần thử | Điều phải xác minh |
| --- | --- | --- |
| File inbound | DB rollback, file move fail, crash sau commit | File lifecycle, accept-once filter, idempotency |
| SFTP inbound | Remote timeout, download incomplete, stream close fail | Không mất source/không leak session, replay được |
| HTTP outbound | Remote commit rồi mất response | Outcome unknown, reconciliation trước retry |
| JMS inbound | Listener rollback, ACK fail sau commit | Redelivery không gây duplicate business |
| AMQP inbound | NACK/requeue, DLX route sai | Không vô hạn poison loop, DLQ thật có record |
| Kafka inbound | Rebalance/offset commit fail, DLT publisher fail | Idempotency, correct offset/replay |
| JDBC inbound | Row claim cạnh tranh, exception trước commit | Transaction rollback, row state nhất quán |
| Poller async | `ExecutorChannel` xử lý lỗi sau callback | Callback không bị hiểu nhầm là toàn flow success |
| Pseudo transaction | SFTP upload thành công rồi lỗi callback | Không khẳng định remote rollback |
| Multiple instances | Hai pollers cùng file/key | Claim/lock/dedupe đúng theo topology |

### 27.1. Assertion cho failedMessage

Với poller có pass-through/default synchronization thích hợp và transaction advice:

~~~text
Simulate handler failure after poller received message M.
Read errorMessage from configured error channel.
Find MessagingException if published by the error handler.
Assert:
    failedMessage matches M by safe business key/correlation.
    root cause is expected exception.
    no raw PII/credentials leaked to logs.
~~~

Đây là một **assertion plan**, không phải lời khẳng định `failedMessage` tồn tại ở mọi exception path.

### 27.2. Kiểm tra type của channel result

Khi expression trả `Boolean.FALSE`, `afterCommitChannel` có thể nhận message payload Boolean. Nếu consumer mong đợi `File`, test sẽ phát hiện contract mismatch.

Test:

- Expression `payload` → payload có type gốc.
- Expression `payload.renameTo(...)` → payload là Boolean.
- Chỉ channel, không expression → message gốc được chuyển theo contract.
- Expression null/void → không có result message theo behavior của processor.

### 27.3. Test transaction advice ordering

Cho handler fail transient một lần rồi thành công. Thử hai cấu hình advice ordering được dự án cho phép:

- Mỗi attempt một transaction mới.
- Một transaction bao nhiều attempts.

Đo:

1. Số lần `beforeCommit/afterRollback/afterCommit`.
2. Số JDBC commits và rollbacks.
3. Message có mark rollback-only không?
4. Source poller có redeliver không?

Kết quả phải phù hợp với **guarantee dự án muốn**, không chỉ phù hợp con số attempts.

## 28. Failure-injection matrix theo thời điểm

| Mốc | Kết quả có thể xảy ra | Chiến lược phục hồi |
| --- | --- | --- |
| F1. Trước poll `receive()` | Source còn message/file | Poll lại bình thường |
| F2. Sau poll, trước JDBC write | File đã qua filter nhưng DB chưa thay đổi | Source state hoặc job retry phải giữ responsibility |
| F3. Sau JDBC write, trước commit | DB rollback được | Redelivery/retry; kiểm tra filter |
| F4. Trong `beforeCommit` | Transaction có thể rollback | Quarantine lỗi invariant, evidence |
| F5. Sau commit, trước `afterCommit` | DB thành công, hậu xử lý chưa chạy | Reconciliation/ARCHIVE_PENDING |
| F6. `afterCommit` move trả false | DB commit, file chưa archive | Kiểm tra result và retry an toàn |
| F7. Sau archive, trước mark archived | File đã chuyển, DB status vẫn pending | Idempotent path+checksum reconciliation |
| F8. `afterRollback` failure | DB đã rollback, quarantine chưa hoàn tất | Cảnh báo secondary failure, giữ source |
| F9. Sau HTTP remote commit, trước response | Outcome remote UNKNOWN | Idempotency key + remote status query |
| F10. Kafka publish success, outbox mark fail | Event có thể được phát lại | Stable event ID ở consumer |
| F11. Source broker ACK fail sau DB commit | Redelivery | Transactional inbox/unique constraint |
| F12. Instance restart hoặc scale-out | Duplicate/contended claim | Shared store, locking, startup reconciliation |

Mỗi row nên có **test ID**, owner, loại adapter, mức ưu tiên và evidence gắn với version runtime. Một thiết kế quan trọng chưa có F5/F6/F11 test thường vẫn có lỗ hổng ngay cả khi happy-path tests xanh.

## 29. Observability: đo sự thật commit và callback riêng

### 29.1. Các metric gợi ý

| Metric | Vai trò |
| --- | --- |
| `poller_transaction_started_total` | Số polling transactions bắt đầu |
| `poller_transaction_committed_total` | Số commits quan sát được |
| `poller_transaction_rolled_back_total` | Số rollbacks quan sát được |
| `transaction_sync_before_commit_total` | Lượt callback trước commit |
| `transaction_sync_after_commit_total` | Lượt callback sau commit |
| `transaction_sync_after_rollback_total` | Lượt callback rollback |
| `transaction_sync_callback_failed_total` | Lỗi khi thực hiện callback |
| `file_archive_pending` | File đã commit DB nhưng chưa archive |
| `file_archive_failed_total` | Lỗi archive |
| `inbox_pending_oldest_age` | Tuổi công việc chưa được xác nhận |
| `outbox_pending_oldest_age` | Tuổi sự kiện chưa publish được |
| `poller_source_lag` | Độ trễ đầu vào |
| `error_flow_persist_failed_total` | Lỗi lưu failure store |
| `reconciliation_recovered_total` | Số trường hợp phục hồi sau crash |

Đây là **gợi ý metric của application**, không phải bộ metric Spring Integration mặc định. Chọn tags cardinality thấp như `flow`, `adapter`, `phase`, `result`; không dùng mỗi `filePath`, `tenantId` hoặc `operationId` làm metric label.

### 29.2. Trace theo phase

~~~text
Trace businessOperationId=batch-T42-971
  -> poll.receive
  -> transaction.begin
  -> parse.validate
  -> jdbc.update
  -> transaction.before_commit
  -> transaction.commit
  -> transaction.after_commit
  -> file.archive
  -> outbox.publish (worker khác)
  -> reconciliation
~~~

Không phải toàn bộ các span cùng transaction/trace thread. Với async/outbox, truyền **business correlation ID** và tạo tracing context phù hợp, không lầm trace span với bảo đảm commit.

### 29.3. Những cảnh báo nên có

- `file_archive_pending` tăng trong khi JDBC commits vẫn đều.
- `afterCommit` callback lỗi liên tục do filesystem permission.
- Source files được poll lại dù DB đã có bản ghi.
- `afterRollback` chuyển file thất bại hoặc quarantine đầy.
- Số `failedMessage` thiếu business key tăng.
- Transaction timeout/deadlock/connection pool saturation.
- JDBC commits tăng nhưng Kafka outbox SENT không tăng.
- Cleanup resource sau callback thất bại, tăng session/thread usage.
- Restart/rebalance khiến retry attempts tăng bất thường.

## 30. Security và dữ liệu nhạy cảm

Transaction synchronization thường được cấu hình gần source file, DB và các beans có quyền cao. Vì vậy cần giới hạn:

1. **SpEL input:** Không đưa expression tùy ý từ người dùng/remote payload để thực thi.
2. **Bean access:** Callback service chỉ có quyền cần thiết, không dùng admin DB/file account.
3. **File paths:** Chỉ move trong approved directories, chống path traversal và symlink attacks.
4. **Multi-tenant:** Không cho một tenant chọn destination khác bằng header chưa xác thực.
5. **Sensitive payload:** Không log đầy đủ `Message` hoặc SQL params/Authorization headers.
6. **Outbox/failure store:** Mã hóa payload references hoặc data khi cần, retention đúng chính sách.
7. **SFTP credentials:** Quản lý secret rotation và session timeout, không ghi password vào failure envelope.
8. **Audit:** Ghi ai thay transaction/poller/factory configuration, thay destination hoặc xóa metadata.
9. **Replay authorization:** Chỉ owner/operator được phép replay các tác vụ có side effect.

### 30.1. Ví dụ path handling

~~~text
BAD:
  targetPath = "/var/app/processed/" + message.header("fileName")
  // header có thể là "../../etc/..."

BETTER:
  fileId = validatedSourceMetadata.fileId
  targetPath = approvedRoot.resolve(safeGeneratedName(fileId))
  verify targetPath.normalize().startsWith(approvedRoot.normalize())
~~~

Đây là pseudocode về **kiểm soát đầu vào**. `normalize` chưa đủ để bảo vệ hoàn toàn khỏi symlink race; cần kiểm soát filesystem permissions và thao tác trusted directory theo threat model.

## 31. Runbook khi afterCommit không archive file

**Tình huống:** Giao dịch JDBC commit rồi nhưng file vẫn còn ở `inbox/`; dashboard báo `file_archive_pending` tăng.

### 31.1. Triage

1. Xác nhận DB transaction có **COMMITTED thật** qua business record/transaction log.
2. Xem file source path, file generation/checksum, business key và thời điểm poll.
3. Kiểm tra `afterCommit` có được đăng ký và thực thi không.
4. Nếu callback chạy: xem kết quả `renameTo` Boolean hoặc `Files.move` exception.
5. Kiểm tra file permission, destination tồn tại, filesystem full/cross-device, file lock.
6. Xem source file filter/accept-once metadata có cho file được poll lại không.
7. Kiểm tra app restart/kill/timeouts trước callback và thread boundary.
8. Kiểm tra outbox/Kafka event đã được gửi chưa để tránh tạo side effect trùng.

### 31.2. Đối soát trước thao tác thủ công

| Evidence | Hành động |
| --- | --- |
| DB COMMITTED, file chưa archive | Archive idempotently với file ID/checksum đã xác minh |
| DB ROLLED_BACK, file còn inbox | Retry/reprocess theo policy nếu source filter cho phép |
| DB ROLLED_BACK, file ở failed/ | Quarantine review rồi replay có kiểm soát |
| DB UNKNOWN, file moved processed/ | Điều tra commit logs/inbox trước khi replay |
| File mất, DB không có record | Incident dữ liệu; tìm backup/original SFTP/failure store |
| File archived, outbox PENDING | Cho outbox worker tiếp tục; không đọc lại file chỉ để publish |
| Remote API outcome UNKNOWN | Tra cứu theo stable operation key, không POST lại mù |

### 31.3. Khắc phục và đóng incident

- Không xóa toàn bộ accept-once metadata hoặc flush Redis để "làm cho poller chạy".
- Không move file ra/vào inbox nhiều lần khi chưa biết business outcome.
- Khôi phục DB/file state dựa trên stable key, hạn chế concurrency khi replay.
- Ghi before/after evidence, owner/approval và kết quả.
- Chỉ đóng khi **DB, file lifecycle, source filter, outbox, error records** nhất quán hoặc ngoại lệ còn lại có owner/deadline.

## 32. Các anti-pattern phổ biến

| Anti-pattern | Vì sao sai | Giải pháp |
| --- | --- | --- |
| Tin rằng TransactionSynchronizationFactory mở transaction | Factory chỉ tạo synchronization | Cấu hình transaction manager/advice trên poller |
| Dùng afterCommit để rollback file | File operation không transactional | Compensation/reconciliation |
| Gọi Kafka/HTTP trong afterCommit và không có outbox | Crash có thể mất event | Outbox bền + worker |
| Dùng beforeCommit gọi API side effect | DB rollback không undo API | Chuyển sang outbox/idempotency |
| Cho `ExecutorChannel` rồi nghĩ mọi handler cùng TX | Transaction thread-local bị ngắt | Ranh giới TX rõ + durable handoff |
| `renameTo` trả `false` nhưng vẫn ghi ARCHIVED | Silent archive failure | Verify Boolean/FIles.move + alert |
| Đổi afterRollback vào failed/ ở retry đầu | Mất source cho retry tiếp | Retry policy và file lifecycle thống nhất |
| `PseudoTransactionManager` được coi là XA | Không rollback file/SFTP | Nêu đúng guarantee, reconcile |
| Tự làm factory nhưng quên unbind | Lẫn message/tenant, leak memory | Dùng default factory hoặc test cleanup |
| Chỉ coi afterCommit callback được gọi là success | Side effect có thể thất bại | Kiểm tra trạng thái target thực |
| Bỏ qua accept-once filter state | File không được poll lại sau rollback | Transaction-aware source recovery |
| Không dùng stable business key | Redelivery tạo duplicate | Inbox/unique constraint |
| Retry nhiều lớp không có ngân sách | Retry storm và latency | Retry budget tổng |
| Log raw `failedMessage` | Lộ PII/secrets | Correlation, redaction và payload reference |
| Coi errorChannel là DLQ bền | Message lỗi vẫn có thể mất | Durable failure store/broker DLQ |
| Dùng transaction REQUIRES_NEW không đánh giá | Một phần DB commit dù poller rollback | Thiết kế propagation và test |
| Không test kill giữa commit và callback | Bỏ sót cửa sổ lỗi quan trọng | Restart/reconciliation test |
| Dùng high-watermark để bỏ file record chưa commit | Mất dữ liệu | Per-record state/gap tracking |
| Không phân biệt Kafka offset và JDBC commit | Sai at-least-once assumptions | Idempotent consumer và commit ordering |
| Sau incident xóa toàn bộ metadata | Replay hàng loạt side effects trùng | Scoped metadata changes, approval |

## 33. Câu hỏi tự kiểm tra

### Câu 1. Factory có tự bắt đầu transaction không?

**Đáp án:** Không. `TransactionSynchronizationFactory` tạo synchronization; poller phải có transaction advice/manager phù hợp để gắn lifecycle.

### Câu 2. afterCommit ném exception thì JDBC có rollback không?

**Đáp án:** Không thể rollback giao dịch đã commit chỉ vì callback hậu commit thất bại. Cần lưu trạng thái hậu xử lý và recovery/reconciliation độc lập.

### Câu 3. beforeCommit dùng để làm gì?

**Đáp án:** Kiểm tra điều kiện, thực hiện công việc cần xảy ra trước resource commit. Callback có thể khiến transaction rollback nếu ném exception đúng cơ chế. Không nên thực hiện side effect remote khó undo.

### Câu 4. afterRollback có undo SFTP upload không?

**Đáp án:** Không. Nó có thể chạy compensating action nếu được viết, nhưng remote upload đã xảy ra thì cần xử lý riêng và không có atomic rollback tự nhiên.

### Câu 5. PseudoTransactionManager có vai trò gì?

**Đáp án:** Tạo lifecycle success/failure cho synchronization trong flow không có tài nguyên transaction thật; không biến filesystem, FTP/SFTP/HTTP thành transactional resource.

### Câu 6. Vì sao ExecutorChannel nguy hiểm?

**Đáp án:** Nó tách thread; poller transaction có thể commit và chạy afterCommit trước khi worker async hoàn tất. Cần durable handoff/transaction khác.

### Câu 7. File.renameTo trả `false` thì channel nhận gì?

**Đáp án:** Nếu expression rename và channel được cấu hình, result Boolean có thể là payload gửi vào channel; `false` là thất bại phải xử lý, không phải exception mặc định.

### Câu 8. Dùng PassThrough factory để làm gì?

**Đáp án:** Giữ message được poll trong transaction context để lỗi từ advice có thể gắn `failedMessage`, hỗ trợ error reporting; nó không tự archive hoặc tạo business result.

### Câu 9. DB commit rồi nhưng file còn inbox sau restart, phải làm gì?

**Đáp án:** Dựa vào business key/DB evidence và file generation/checksum để reconcile, archive an toàn; không chạy lại toàn bộ DB inserts một cách mù quáng.

### Câu 10. afterCommit gửi Kafka có bảo đảm exactly-once không?

**Đáp án:** Không. Producer send có thể async/fail hoặc publish thành công trước crash. Cần transactional outbox, stable event ID, producer confirm và idempotent target.

### Câu 11. afterRollback có luôn chạy khi app bị kill -9 không?

**Đáp án:** Không. Callback trong process không được bảo đảm chạy khi process chết đột ngột; cần nguồn công việc bền và startup reconciliation.

### Câu 12. Vì sao một file chứa nhiều records làm khó callback?

**Đáp án:** Transaction của một polled file message không mặc nhiên bao toàn bộ records nếu flow tách threads hoặc commit per-record. Phải có định nghĩa hoàn tất toàn file/per-record rõ.

## 34. Checklist triển khai TransactionSynchronizationFactory

1. **Đúng use case:** Cần phối hợp callback với transaction outcome của poller, không lạm dụng làm distributed transaction.
2. **Chọn transaction manager thật:** `DataSourceTransactionManager` với JDBC hoặc manager phù hợp source; xác minh datasource/connection.
3. **Pseudo transaction có chủ đích:** Chỉ khi cần success/failure hooks không có transactional resource.
4. **Gắn factory đúng poller:** Không chỉ khai báo bean mà chờ tự hoạt động.
5. **Đúng thread boundary:** Kiểm tra Direct/Executor/Queue channels.
6. **Đúng advice ordering:** Transaction vs retry vs custom advice và `@Transactional` propagation.
7. **beforeCommit không làm remote effect khó undo** nếu cần DB atomicity.
8. **afterCommit không được coi là durable job queue**; thêm reconciliation hoặc outbox nếu bắt buộc.
9. **afterRollback có error handling** và nguồn replay rõ.
10. **Factory mặc định trước custom:** `DefaultTransactionSynchronizationFactory` + processor khi phù hợp.
11. **Resource cleanup:** Custom factory phải unbind holder đúng completion.
12. **Original message:** Kiểm tra holder/failedMessage và correlation theo đường lỗi thật.
13. **File type:** Không copy biểu thức File sang SFTP stream/JDBC DTO.
14. **File move result:** Kiểm tra Boolean hoặc xử lý IOException, collision/cross-filesystem.
15. **File filter state:** Rollback không được suy là reset accept-once filter.
16. **Per-record semantics:** Có status/commit evidence cho mỗi record nếu cần.
17. **Source ack/offset:** JMS/AMQP/Kafka thử với container/broker thật; không suy từ callback.
18. **HTTP idempotency:** Timeout có thể xảy ra sau remote commit.
19. **Outbox:** Ghi cùng DB transaction khi cần bảo đảm publish event hậu commit.
20. **Retry budget:** Đếm attempts qua handler, SDK, container, broker.
21. **Durability:** Test restart/crash ở trước/sau commit và callback.
22. **Observability:** DB commit, callback, file archive, outbox và replay là các trạng thái riêng.
23. **Security:** Restrict SpEL/bean access, safe paths, tenant boundaries, redact secrets.
24. **Failure store:** Có owner, retention, audit, replay có kiểm soát.
25. **Runbook:** Có cách reconcile DB đã commit nhưng callback chưa chạy.
26. **Kiểm thử phiên bản:** Đối chiếu namespace XML/Java DSL/APIs với Spring Integration BOM dự án.

## 35. Tài liệu tham khảo

Tài liệu chính thức để hiểu API và kiểm tra cấu hình theo phiên bản thực tế:

1. **Spring Integration — Transaction Support:**  
   https://docs.spring.io/spring-integration/reference/transactions.html
2. **Spring Integration — DefaultTransactionSynchronizationFactory Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/DefaultTransactionSynchronizationFactory.html
3. **Spring Integration — ExpressionEvaluatingTransactionSynchronizationProcessor Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/ExpressionEvaluatingTransactionSynchronizationProcessor.html
4. **Spring Integration — IntegrationResourceHolder Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/IntegrationResourceHolder.html
5. **Spring Integration — File Support:**  
   https://docs.spring.io/spring-integration/reference/file.html
6. **Spring Integration — SFTP Support:**  
   https://docs.spring.io/spring-integration/reference/sftp.html
7. **Spring Integration — JDBC Support:**  
   https://docs.spring.io/spring-integration/reference/jdbc.html
8. **Spring Framework — Transaction Synchronization:**  
   https://docs.spring.io/spring-framework/reference/data-access/transaction.html

**Ghi chú về ví dụ:** XML, Java, SQL, YAML và các sơ đồ trong bài minh họa các hợp đồng API và failure scenarios. Tên bean như `FileLifecycleService`, schema database và các kênh audit là thành phần **do ứng dụng tự xây dựng**. Cần đối chiếu phiên bản Spring Integration/Spring Boot đang dùng, biên dịch và thực hiện integration tests trước khi đưa ví dụ vào production. Phạm vi bài học này **chưa thực hiện build hoặc chạy test tại repository**.

## 36. Tổng kết

`TransactionSynchronizationFactory` là cầu nối giữa **transaction outcome** và **các hành động được đồng bộ hóa theo vòng đời transaction** trong Spring Integration. Factory tạo `TransactionSynchronization` và thường dùng `DefaultTransactionSynchronizationFactory` với `TransactionSynchronizationProcessor` hoặc `ExpressionEvaluatingTransactionSynchronizationProcessor` để chạy `beforeCommit`, `afterCommit`, `afterRollback`. `IntegrationResourceHolder` liên kết message với transaction context; `PassThroughTransactionSynchronizationFactory` hỗ trợ giữ failedMessage cho error reporting; `PseudoTransactionManager` cho phép success/failure hooks khi không có resource transaction thật.

Nhưng **synchronization không đồng nghĩa atomicity xuyên mọi adapter**. JDBC transaction có thể rollback dữ liệu DB, còn File/SFTP/HTTP/Kafka/JMS/AMQP có ACK, publish và side effect theo giao thức riêng. `afterCommit` thất bại không làm DB uncommit; một `ExecutorChannel` có thể khiến callback chạy trước khi business processing async kết thúc; file accept-once filter và broker offset cũng không tự khớp với transaction của handler.

Một thiết kế vững chắc cần kết hợp **transaction boundary rõ, original message/correlation đầy đủ, callback idempotent, kiểm tra file move, error/retry policy hữu hạn, transactional inbox/outbox, startup reconciliation và test các crash windows**. Chỉ có thể coi luồng File/SFTP → JDBC → broker được xử lý an toàn khi **kết quả nghiệp vụ có bằng chứng bền vững**, mọi thao tác hậu commit còn thiếu có thể được phục hồi, và không làm mất hoặc nhân đôi message ngoài hợp đồng đã chọn.




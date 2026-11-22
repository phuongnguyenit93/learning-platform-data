# Xử lý OptimisticLockException và xung đột cập nhật trong Spring Data JPA

Khi hai request cùng đọc một entity rồi cập nhật gần như đồng thời, request ghi sau có thể vô tình ghi đè dữ liệu mà request trước vừa lưu. Đây là lost update. Spring Data JPA và JPA provider hỗ trợ optimistic locking để phát hiện tình huống này bằng thuộc tính phiên bản `@Version`.

Khi phiên bản trong database đã thay đổi kể từ lúc entity được đọc, thao tác cập nhật hoặc xóa dùng phiên bản cũ sẽ không khớp hàng nào. Provider ném `OptimisticLockException` và transaction hiện tại phải rollback. Spring có thể chuyển lỗi đó thành nhóm `OptimisticLockingFailureException` của `org.springframework.dao`.

Xử lý đúng không chỉ là bắt exception. Ứng dụng cần xác định xung đột xảy ra ở đâu, kết thúc transaction lỗi, tải trạng thái mới trong transaction khác và quyết định có thể tự tính lại thao tác hay phải yêu cầu người dùng giải quyết. Bài này trình bày cơ chế `@Version`, lỗi khi update/merge/delete, xử lý ở ranh giới service/API, retry an toàn, pessimistic locking và cách kiểm thử hai transaction cạnh tranh.

## 1. Lost update xảy ra như thế nào?

Giả sử tài liệu có tiêu đề ban đầu là `"Draft"` và hai người dùng cùng mở trang chỉnh sửa.

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| T1 | Đọc tiêu đề Draft | |
| T2 | | Đọc tiêu đề Draft |
| T3 | Đổi tiêu đề thành Approved | |
| T4 | Commit Approved | |
| T5 | | Đổi tiêu đề thành Review |
| T6 | | Commit Review |

Nếu không có kiểm tra đồng thời, giá trị Review ghi đè Approved. Transaction B không biết dữ liệu nó đọc đã cũ.

Đây là lost update. Tình huống tương tự có thể xảy ra với số dư, số lượng tồn kho, trạng thái đơn hàng, nội dung bài viết hoặc bất kỳ entity nào được nhiều request cập nhật.

### 1.1. Optimistic locking hoạt động theo nguyên tắc nào?

Optimistic locking giả định xung đột không xảy ra thường xuyên. Các transaction được phép đọc và làm việc đồng thời. Khi ghi, provider kiểm tra xem phiên bản của hàng còn đúng với phiên bản mà entity đã đọc hay không.

Nếu cả hai transaction đọc version 7:

1. Transaction A cập nhật hàng với điều kiện version vẫn bằng 7 và ghi version mới là 8.
2. Transaction B cố cập nhật hàng với điều kiện version bằng 7.
3. Database không tìm thấy hàng nào còn version 7.
4. Provider nhận biết số hàng cập nhật bằng 0 và báo optimistic lock conflict.
5. Transaction B rollback thay vì âm thầm ghi đè A.

Optimistic locking không giữ một khóa độc quyền từ lúc đọc đến lúc người dùng bấm Save. Nó phát hiện xung đột ở giai đoạn kiểm tra/ghi. Cách này thường phù hợp khi số lần đọc lớn hơn nhiều số lần ghi và xung đột tương đối hiếm.

## 2. Khai báo @Version trong entity

JPA dùng annotation `@Version` để đánh dấu trường phiên bản. Provider quản lý giá trị này; ứng dụng không được tự tăng hoặc gán version.

Ví dụ entity `Document`:

~~~java
package com.example.documents;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Version
    private Long version;

    protected Document() {
    }

    public Document(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String title) {
        this.title = title;
    }
}
~~~

Những điểm cần nhớ:

- Mỗi entity có tối đa một version attribute.
- Version thường dùng kiểu số như `int`, `Integer`, `short`, `Short`, `long` hoặc `Long`. Jakarta Persistence cũng quy định một số kiểu thời gian hợp lệ; kiểu số nguyên thường dễ quan sát và truyền qua API.
- Version field/property phải được đặt theo quy tắc mapping JPA, thường ở root entity hoặc mapped superclass và primary table.
- Provider tự gán giá trị khi insert và tự cập nhật khi entity được ghi.
- Không nhận version từ client rồi gọi setter để ghi đè trường `@Version`.
- Nếu entity không có version, JPA không cung cấp cơ chế optimistic version check portable cho entity đó.

Dùng `Long` giúp trường version của entity mới ban đầu là `null`; sau khi insert, provider gán giá trị ban đầu. Không nên tự đặt version bằng 0 hoặc 1 trong constructor.

## 3. SQL provider dùng để phát hiện xung đột

Giả sử entity đang có:

- `id = 42`
- `title = "Draft"`
- `version = 7`

Khi entity thay đổi, provider có thể sinh SQL tương đương:

~~~sql
UPDATE documents
SET title = ?, version = 8
WHERE id = 42
  AND version = 7;
~~~

Nếu chỉ có một transaction ghi version 7, câu lệnh cập nhật một hàng. Nếu transaction khác đã cập nhật version thành 8, câu lệnh dùng version 7 cập nhật 0 hàng.

Provider dựa vào số hàng bị ảnh hưởng để nhận biết trạng thái cũ. SQL thực tế, cách bind tham số và thời điểm tăng version phụ thuộc JPA provider, database và mapping; ví dụ trên minh họa nguyên tắc.

Với thao tác xóa entity managed, provider cũng có thể đưa version cũ vào điều kiện DELETE. Nếu hàng đã bị cập nhật hoặc xóa bởi transaction khác, thao tác xóa có thể thất bại vì version không còn khớp.

### 3.1. Version check được thực hiện khi nào?

Không phải lúc nào exception cũng xuất hiện ngay tại dòng gọi `repository.save()`.

Provider có thể phát hiện xung đột khi:

- Gọi `EntityManager.merge()` với entity detached có version cũ.
- Gọi `flush()` hoặc `repository.flush()`.
- Transaction commit và provider đồng bộ các thay đổi còn pending.

Vì vậy, đoạn code:

~~~java
repository.save(document);
return "updated";
~~~

không có nghĩa database chắc chắn đã commit thành công trước khi method trả kết quả nếu chưa xét transaction boundary. Với `@Transactional` qua Spring proxy, việc commit diễn ra khi lời gọi đi qua proxy kết thúc; lỗi lúc commit vẫn được trả về caller bên ngoài.

Nếu muốn phát hiện lỗi sớm trong thân service, có thể gọi `repository.flush()` hoặc `EntityManager.flush()` sau khi thay đổi. Điều đó làm provider gửi SQL và thực hiện version check sớm hơn, nhưng transaction vẫn có thể gặp lỗi khác khi commit.

## 4. Cập nhật entity managed đúng cách

Mẫu phổ biến là tải entity trong transaction, kiểm tra dữ liệu đầu vào, thay đổi các trường được phép và để JPA quản lý version.

Repository:

~~~java
public interface DocumentRepository
        extends JpaRepository<Document, Long> {
}
~~~

Command nhận từ client:

~~~java
public record UpdateDocumentCommand(
        Long expectedVersion,
        String title) {
}
~~~

DTO response:

~~~java
public record DocumentView(
        Long id,
        String title,
        Long version) {
}
~~~

Service:

~~~java
@Service
public class DocumentService {

    private final DocumentRepository documents;
    private final EntityManager entityManager;

    public DocumentService(
            DocumentRepository documents,
            EntityManager entityManager) {
        this.documents = documents;
        this.entityManager = entityManager;
    }

    @Transactional
    public DocumentView update(
            Long id,
            UpdateDocumentCommand command) {

        Objects.requireNonNull(command.expectedVersion(),
                "expectedVersion is required");

        Document document = documents.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Document not found"));

        if (!Objects.equals(
                command.expectedVersion(),
                document.getVersion())) {
            throw new StaleDocumentVersionException(id);
        }

        document.rename(command.title());

        entityManager.flush();

        return new DocumentView(
                document.getId(),
                document.getTitle(),
                document.getVersion()
        );
    }
}
~~~

Custom exception:

~~~java
public class StaleDocumentVersionException
        extends RuntimeException {

    public StaleDocumentVersionException(Long id) {
        super("Document " + id + " has changed since it was read");
    }
}
~~~

Có hai lớp bảo vệ trong ví dụ:

1. So sánh `expectedVersion` với version hiện tại để phát hiện form/API request đã cũ từ trước khi transaction mới bắt đầu.
2. `@Version` bảo vệ khoảng thời gian từ lúc service đọc entity đến lúc nó flush/commit. Nếu transaction khác ghi trong khoảng này, provider phát hiện xung đột.

Không gán `command.expectedVersion()` vào trường `document.version`. Version chỉ được dùng để so sánh và phản hồi cho client; provider là thành phần cập nhật version trong database.

### 4.1. Vì sao phải so sánh version do client gửi?

Giả sử người dùng mở tài liệu khi version là 7. Sau đó người khác lưu version 8. Người dùng đầu tiên bấm Save và server bắt đầu một transaction mới.

Nếu service chỉ tải entity mới nhất từ database, nó nhận version 8. Nếu service không kiểm tra version 7 trong request, nó có thể áp dụng nội dung cũ của người dùng lên entity version 8 rồi ghi version 9 thành công.

Trong trường hợp đó, `@Version` không phát hiện xung đột vì transaction hiện tại đã đọc version mới nhất là 8. Khoảng thời gian từ lần người dùng mở form đến lần gửi request nằm ngoài transaction này.

Do đó, ứng dụng chỉnh sửa dữ liệu qua nhiều request nên đưa version đã đọc vào command, response hoặc HTTP ETag. So sánh expected version với current version để bảo vệ khoảng thời gian người dùng suy nghĩ.

### 4.2. Dùng flush để phát hiện lỗi trước khi tạo response

`entityManager.flush()` trong service buộc provider đồng bộ các thay đổi đang chờ xuống database. Với optimistic locking, nó thường làm version check xảy ra tại vị trí đó.

Sau flush thành công, getter version thường phản ánh version mới do provider cập nhật. Tuy nhiên, không được bắt lỗi flush rồi tiếp tục sử dụng transaction đã bị đánh dấu rollback-only.

Nếu không gọi flush tường minh, Spring vẫn flush khi commit. Exception có thể xuất hiện khi transaction interceptor hoàn tất method, nghĩa là caller nhận lỗi dù thân method đã chạy hết.

## 5. OptimisticLockException và exception translation của Spring

Ở tầng JPA, exception tiêu chuẩn là:

`jakarta.persistence.OptimisticLockException`

Nó báo rằng kiểm tra version hoặc optimistic lock thất bại. Theo Jakarta Persistence, provider phải đánh dấu transaction hiện tại để rollback khi phát hiện optimistic locking conflict.

Khi dùng Spring Data repository và cơ chế exception translation, lỗi persistence có thể được chuyển thành các kiểu trong `org.springframework.dao`:

- `OptimisticLockingFailureException`: kiểu cơ sở của Spring cho optimistic locking failure.
- `ObjectOptimisticLockingFailureException`: cung cấp thêm thông tin entity class và identifier.
- `JpaOptimisticLockingFailureException`: biến thể dành cho JPA.

Tùy đường gọi, provider và lớp exception translation, code có thể nhìn thấy exception JPA, exception Spring hoặc exception transaction bao ngoài. Nếu custom DAO gọi trực tiếp provider API mà không qua translator, đừng giả định mọi lỗi đều đã được đổi sang Spring DAO exception.

### 5.1. Không chỉ bắt exception quanh repository.save()

Đoạn sau không đủ an toàn:

~~~java
try {
    repository.save(document);
} catch (OptimisticLockingFailureException ex) {
    return "conflict";
}
~~~

Lý do:

- `save()` có thể chưa flush.
- Xung đột có thể xuất hiện khi flush hoặc commit.
- Transaction có thể đã bị đánh dấu rollback-only.
- Trả response thành công từ transaction rollback-only có thể dẫn đến lỗi khi transaction kết thúc.

Hãy để exception thoát khỏi transaction boundary. Xử lý nó ở tầng gọi bên ngoài sau khi transaction đã rollback.

## 6. Xử lý conflict ở service boundary và REST API

Không nên bắt `OptimisticLockException` bên trong method `@Transactional` rồi tiếp tục query, cập nhật hoặc trả kết quả bình thường. Transaction đã được đánh dấu rollback-only; persistence context có thể chứa trạng thái không còn đáng tin cậy.

Một cách tổ chức dễ kiểm soát là để service ném lỗi và dùng `@RestControllerAdvice` chuyển thành HTTP conflict.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler({
        OptimisticLockingFailureException.class,
        OptimisticLockException.class,
        StaleDocumentVersionException.class
    })
    public ResponseEntity<ProblemDetail> handleOptimisticConflict(
            RuntimeException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Dữ liệu đã được cập nhật bởi một thao tác khác. "
                        + "Hãy tải lại dữ liệu và xác nhận thay đổi."
        );

        problem.setTitle("Update conflict");

        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(problem);
    }
}
~~~

Import cần có:

~~~java
import jakarta.persistence.OptimisticLockException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
~~~

`@RestControllerAdvice` xử lý lỗi sau khi lời gọi service đi qua transaction proxy và transaction thất bại. Trong một số ứng dụng, exception có thể được bọc trong `RollbackException` hoặc exception transaction khác; hãy kiểm tra cause chain thực tế và exception translation của stack đang dùng.

Không trả stack trace, SQL, tên bảng hoặc chi tiết nội bộ database cho client. Response nên cung cấp mã lỗi ổn định và hướng dẫn người dùng tải lại dữ liệu.

### 6.1. Vì sao thường trả HTTP 409 Conflict?

`409 Conflict` biểu thị request không thể hoàn tất do xung đột với trạng thái hiện tại của resource. Đây là lựa chọn phù hợp khi client gửi version trong body hoặc command và server phát hiện trạng thái đã thay đổi.

Nếu API dùng HTTP conditional request với `ETag` và header `If-Match`, khi điều kiện precondition không còn đúng, `412 Precondition Failed` thường phù hợp hơn. Hãy chọn một hợp đồng API nhất quán và ghi rõ cách client gửi version.

### 6.2. Ví dụ response version

Khi đọc tài liệu, trả version:

~~~json
{
  "id": 42,
  "title": "Draft",
  "version": 7
}
~~~

Khi cập nhật, client gửi version đã đọc:

~~~json
{
  "expectedVersion": 7,
  "title": "Approved"
}
~~~

Nếu database đã ở version 8, server trả conflict. Client có thể tải dữ liệu mới, so sánh thay đổi và gửi lại một command mới dựa trên version hiện tại.

## 7. Xử lý detached entity và merge

`EntityManager.merge(detachedEntity)` sao chép trạng thái của entity detached vào một instance managed trong persistence context hiện tại. Đối tượng trả về từ merge là instance managed; đối tượng truyền vào vẫn là detached.

Nếu detached entity giữ version cũ, provider phải kiểm tra version khi merge. Tùy provider, lỗi có thể xuất hiện ngay lúc gọi merge, lúc flush hoặc lúc commit.

Ví dụ tình huống:

1. Request A tải Document version 4.
2. Entity được detach sau khi transaction kết thúc.
3. Request B cập nhật Document thành version 5.
4. Request A gửi lại entity detached có version 4.
5. Merge entity cũ phải phát hiện stale revision thay vì ghi đè version 5.

### 7.1. Tránh map toàn bộ request thành entity rồi merge

Mẫu dễ gây lỗi nghiệp vụ:

~~~java
Document detached = mapper.toEntity(request);
detached.setId(id);
repository.save(detached);
~~~

Nếu mapper tạo một entity có nhiều trường null/default, merge có thể sao chép cả những trường client không có ý định thay đổi. Điều này gây mất dữ liệu ngoài ý muốn ngay cả khi version check không thất bại.

Thường nên:

1. Nhận command/DTO chỉ chứa trường được phép thay đổi và expected version.
2. Tải entity managed trong transaction.
3. So sánh expected version.
4. Áp dụng từng thay đổi được phép lên entity managed.
5. Để provider kiểm tra version khi flush.

Nếu thật sự cần merge detached graph, phải hiểu đầy đủ semantics của merge, cascade MERGE và cách provider kiểm tra version cho từng entity trong graph.

### 7.2. Không sửa version của entity detached

Không dùng setter để ép version detached thành version mới nhất. Làm vậy có thể vô hiệu hóa ý nghĩa của snapshot mà client đã đọc và khiến request cũ ghi đè dữ liệu mới.

Nếu client gửi version 4, server phải giữ nguyên thông tin expected version đó để kiểm tra. Provider tự quản lý version của entity managed.

## 8. Retry sau optimistic locking conflict

Không phải conflict nào cũng nên tự động retry.

### 8.1. Khi nào không nên retry tự động?

Với form chỉnh sửa do người dùng nhập, hai người có thể thay đổi cùng một trường theo hai ý định khác nhau. Tự tải bản mới rồi áp dụng lại toàn bộ nội dung cũ sẽ biến lost update thành hành vi ghi đè có chủ đích của code.

Trong trường hợp này:

- Trả HTTP 409 hoặc 412 theo hợp đồng API.
- Cho client tải bản mới.
- Hiển thị các trường đã thay đổi.
- Yêu cầu người dùng chọn giữ nội dung nào hoặc hợp nhất.
- Gửi command mới với expected version mới.

Không tự động retry một request mang dữ liệu người dùng cũ chỉ vì muốn giảm số lỗi hiển thị.

### 8.2. Khi nào retry có thể phù hợp?

Retry có thể hữu ích khi thao tác có thể tính lại từ trạng thái mới, ví dụ:

- Tăng một bộ đếm.
- Cập nhật một giá trị tổng hợp có quy tắc xác định.
- Ghi một trạng thái dẫn xuất từ dữ liệu mới nhất.
- Thực hiện một thao tác nội bộ có tính idempotent và không có side effect ngoài database trước khi commit.

Mỗi lần retry phải tải entity mới trong một transaction mới, tính lại thao tác trên trạng thái mới và giới hạn số lần thử.

### 8.3. Retry phải tạo transaction mới

Transaction bị optimistic lock failure phải rollback. Không tái sử dụng transaction hoặc persistence context đã thất bại.

Một coordinator có thể dùng `TransactionTemplate` để mỗi lần thử có transaction riêng:

~~~java
@Service
public class CounterRetryService {

    private static final int MAX_ATTEMPTS = 3;

    private final TransactionTemplate transactionTemplate;
    private final AccountRepository accounts;
    private final EntityManager entityManager;

    public CounterRetryService(
            PlatformTransactionManager transactionManager,
            AccountRepository accounts,
            EntityManager entityManager) {
        this.transactionTemplate =
                new TransactionTemplate(transactionManager);
        this.accounts = accounts;
        this.entityManager = entityManager;
    }

    // Gọi method này bên ngoài một transaction đang hoạt động.
    public AccountView increment(Long accountId) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return transactionTemplate.execute(status -> {
                    Account account = accounts.findById(accountId)
                            .orElseThrow();

                    account.incrementCounter();

                    entityManager.flush();

                    return new AccountView(
                            account.getId(),
                            account.getCounter(),
                            account.getVersion()
                    );
                });
            } catch (OptimisticLockingFailureException exception) {
                if (attempt == MAX_ATTEMPTS) {
                    throw exception;
                }
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
~~~

DTO và entity trong ví dụ:

~~~java
public record AccountView(
        Long id,
        long counter,
        Long version) {
}
~~~

~~~java
@Entity
public class Account {

    @Id
    private Long id;

    private long counter;

    @Version
    private Long version;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public long getCounter() {
        return counter;
    }

    public Long getVersion() {
        return version;
    }

    public void incrementCounter() {
        counter++;
    }
}
~~~

Ví dụ minh họa retry một thao tác tăng bộ đếm. `TransactionTemplate.execute` hoàn tất transaction (bao gồm commit) trước khi trả kết quả; nếu commit thất bại do version conflict, exception được bắt ở vòng lặp. Lần thử kế tiếp đọc lại trạng thái mới.

Coordinator phải được gọi ngoài transaction đang hoạt động để mỗi lần `execute` thực sự tạo một transaction mới. Không đặt `@Transactional` bao trọn vòng retry. Trong ứng dụng thật, có thể thêm backoff/jitter có giới hạn để giảm việc nhiều request cùng va chạm liên tục.

### 8.4. Không lặp side effect ngoài database

Không gửi email, gọi cổng thanh toán hoặc phát message trực tiếp trong mỗi lần retry. Nếu transaction rollback nhưng email đã gửi, lần thử tiếp theo có thể gửi trùng.

Dùng transactional outbox hoặc ghi sự kiện trong cùng transaction rồi publish sau commit. Nếu thao tác ngoài database phải retry, dùng idempotency key và thiết kế rõ khả năng thực hiện lặp.

### 8.5. Giới hạn số lần thử

Retry vô hạn có thể làm hệ thống quá tải khi nhiều request liên tục tranh chấp cùng một hàng. Hãy:

- Đặt số lần thử nhỏ và hữu hạn.
- Chỉ retry lỗi optimistic conflict có thể giải quyết bằng cách tính lại.
- Không retry lỗi validation hoặc lỗi nghiệp vụ.
- Theo dõi tỷ lệ conflict và retry.
- Chuyển sang pessimistic locking hoặc thiết kế lại luồng nếu contention cao kéo dài.

## 9. Dùng optimistic lock để kiểm tra một thao tác chỉ đọc

Entity có version không tự động được kiểm tra lại chỉ vì transaction đọc entity rồi kết thúc mà không thay đổi nó.

Nếu nghiệp vụ phụ thuộc vào việc dữ liệu vẫn giữ nguyên trong suốt transaction, có thể yêu cầu explicit optimistic lock:

~~~java
entityManager.lock(
        document,
        LockModeType.OPTIMISTIC
);
~~~

`LockModeType.OPTIMISTIC` yêu cầu provider xác thực version của entity trước khi transaction hoàn tất. Nó hữu ích khi transaction đã đọc dữ liệu và cần chắc rằng dữ liệu không đổi trước khi một quyết định liên quan được commit.

Nếu cần tăng version dù entity không có trường business nào thay đổi, có thể dùng:

~~~java
entityManager.lock(
        document,
        LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

Force increment hữu ích để phối hợp thay đổi ở cấp aggregate root hoặc báo cho transaction khác biết rằng trạng thái được bảo vệ đã thay đổi.

Chỉ dùng explicit optimistic lock khi có lý do nghiệp vụ. Việc kiểm tra version ở cuối transaction có thể làm rollback công việc đã thực hiện nếu phát hiện xung đột.

## 10. Khi nào dùng pessimistic locking?

Optimistic locking phù hợp khi xung đột hiếm. Nếu nhiều transaction thường xuyên cập nhật cùng một hàng, retry liên tục có thể tốn tài nguyên. Khi đó, pessimistic locking có thể phù hợp hơn.

Spring Data JPA cho phép đặt lock mode bằng `@Lock`:

~~~java
public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from Document d where d.id = :id")
    Optional<Document> findByIdForUpdate(@Param("id") Long id);
}
~~~

Service gọi method này bên trong transaction:

~~~java
@Transactional
public DocumentView updateWithDatabaseLock(
        Long id,
        String newTitle) {

    Document document = documents.findByIdForUpdate(id)
            .orElseThrow();

    document.rename(newTitle);

    return new DocumentView(
            document.getId(),
            document.getTitle(),
            document.getVersion()
    );
}
~~~

`PESSIMISTIC_WRITE` yêu cầu database khóa hàng để các transaction cạnh tranh phải chờ hoặc thất bại tùy database và lock timeout. Transaction cần được giữ ngắn vì lock tồn tại trong thời gian transaction.

### 10.1. So sánh hai chiến lược

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Thời điểm phát hiện/ngăn conflict | Kiểm tra khi ghi hoặc xác thực version | Khóa database được lấy trước khi thao tác |
| Phù hợp | Xung đột ít, đọc nhiều | Xung đột thường xuyên trên cùng hàng |
| Chi phí khi có conflict | Transaction phải rollback, có thể retry | Transaction có thể chờ lock hoặc timeout |
| Tác động concurrency | Ít giữ lock trong giai đoạn đọc | Transaction khác có thể bị chặn |
| Nguy cơ vận hành | Retry storm khi contention cao | Deadlock, lock timeout và hàng chờ |
| Yêu cầu mapping | Entity cần version cho optimistic check portable | Pessimistic lock có thể dùng cả entity không version, tùy API/provider |

Pessimistic locking không phải cách chữa mọi conflict. Nó có thể giảm throughput nếu transaction làm nhiều công việc hoặc gọi dịch vụ ngoài trong lúc giữ lock.

### 10.2. Lock timeout và deadlock

Khi không lấy được pessimistic lock, provider có thể ném `PessimisticLockException` hoặc `LockTimeoutException` tùy phạm vi rollback mà database/provider báo cáo. Deadlock cũng có thể khiến transaction thất bại.

Không dùng chung logic xử lý cho mọi exception concurrency. Optimistic conflict thường cần reload/merge; lock timeout có thể cần retry transaction ngắn với backoff; deadlock cần xem lại thứ tự truy cập tài nguyên và transaction design.

## 11. Version chỉ bảo vệ entity được version hóa

`@Version` bảo vệ state của entity theo quy tắc JPA. Nó không tự động tạo một version chung cho mọi entity liên quan.

Ví dụ Order có nhiều OrderLine. Nếu hai transaction cập nhật các dòng khác nhau, version của từng OrderLine có thể thay đổi riêng. Version của Order root không nhất thiết tăng nếu chỉ một entity con được cập nhật và không có thay đổi state thuộc Order.

Nếu invariant nghiệp vụ phụ thuộc toàn bộ aggregate, cần thiết kế cơ chế phối hợp:

- Mọi thao tác làm thay đổi aggregate đều tăng version của root.
- Dùng `OPTIMISTIC_FORCE_INCREMENT` khi cần xác thực root.
- Hoặc dùng pessimistic lock trên root theo một protocol mà tất cả writer tuân thủ.
- Dùng constraint ở database cho invariant có thể biểu diễn bằng constraint.
- Kiểm tra lại toàn bộ điều kiện nghiệp vụ trong transaction trước khi commit.

Khóa root không tự động khóa hoặc version hóa mọi entity con. Tất cả luồng ghi phải tuân thủ cùng một protocol thì root mới thực sự đóng vai trò điểm điều phối.

## 12. Bulk update/delete có bypass optimistic locking không?

Có. JPQL bulk update/delete, CriteriaUpdate/CriteriaDelete và native SQL thao tác trực tiếp trên tập hàng ở database. Chúng không tải từng entity và không chạy version check như thao tác update/delete entity managed thông thường.

Hệ quả:

- Bulk UPDATE không tự động kiểm tra version cũ của từng entity.
- Bulk UPDATE thông thường không tự động tăng version theo cơ chế entity lifecycle.
- Bulk DELETE không tự động xác thực version như xóa từng entity.
- Persistence context không tự đồng bộ với kết quả bulk operation.
- Database foreign key với `ON DELETE CASCADE` vẫn có thể xóa hàng con theo constraint; đó là hành vi của database, không phải JPA optimistic locking hay cascade callback.

Nếu cần compare-and-set cho bulk update, đưa version dự kiến vào WHERE và tăng version trong chính câu lệnh. Ví dụ SQL minh họa cho bảng inventory:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND available >= :quantity;
~~~

Diễn giải số hàng bị ảnh hưởng:

- `1`: thao tác thành công; version đã được tăng.
- `0`: không có hàng khớp. Có thể do version đã đổi, hàng không tồn tại hoặc số lượng không đủ; cần query bổ sung nếu API phải phân biệt các nguyên nhân.

Sau bulk operation, flush trước nếu còn thay đổi pending và clear/refresh persistence context phù hợp. Không tiếp tục dùng entity instance cũ như thể chúng đã được đồng bộ.

Nếu cần lifecycle callback, cascade hoặc optimistic locking theo từng entity, dùng thao tác entity managed thay vì bulk update/delete.

## 13. Xung đột khi cập nhật cùng một field và khác field

Optimistic locking theo version thường bảo vệ toàn bộ state được version hóa của entity. Hai transaction thay đổi hai field khác nhau trên cùng entity vẫn có thể conflict nếu cùng đọc một version.

Ví dụ:

- Transaction A đổi title.
- Transaction B đổi description.
- Cả hai cùng đọc version 10.
- A commit và version thành 11.
- B cố ghi bằng version 10 và bị conflict.

Đây là hành vi bảo thủ giúp tránh mất cập nhật khi entity được xem như một đơn vị nhất quán.

Nếu nghiệp vụ muốn hai thay đổi độc lập có thể cùng thành công, cân nhắc:

- Tách state thành entity riêng có vòng đời và version riêng.
- Dùng command chuyên biệt cập nhật đúng một field với điều kiện rõ ràng.
- Dùng atomic database update cho phép cộng/trừ hoặc cập nhật độc lập.
- Xác định invariant nào thật sự cần bảo vệ ở cấp aggregate.

Không tắt versioning chỉ để giảm conflict nếu chưa đánh giá nguy cơ lost update.

## 14. Kiểm thử optimistic locking bằng hai transaction độc lập

Một test tốt phải tạo hai persistence context/transaction riêng. Nếu cả hai thao tác chạy trong cùng một transaction và cùng persistence context, test không mô phỏng được stale entity từ hai request.

Ví dụ với Spring Boot integration test và `TransactionTemplate`:

~~~java
@SpringBootTest
class DocumentOptimisticLockingTest {

    private final TransactionTemplate transactions;
    private final DocumentRepository documents;

    DocumentOptimisticLockingTest(
            PlatformTransactionManager transactionManager,
            DocumentRepository documents) {
        this.transactions =
                new TransactionTemplate(transactionManager);
        this.documents = documents;
    }

    @Test
    void staleDetachedEntityCannotOverwriteNewerCommit() {
        Long id = transactions.execute(status ->
                documents.saveAndFlush(
                        new Document("Initial")
                ).getId()
        );

        Document snapshotA = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        Document snapshotB = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        assertThat(snapshotA.getVersion())
                .isEqualTo(snapshotB.getVersion());

        transactions.executeWithoutResult(status -> {
            Document current = documents.findById(id).orElseThrow();
            current.rename("Winner");
            documents.flush();
        });

        assertThatThrownBy(() ->
                transactions.executeWithoutResult(status -> {
                    documents.save(snapshotB);
                    documents.flush();
                })
        ).isInstanceOf(OptimisticLockingFailureException.class);

        Document persisted = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        assertThat(persisted.getTitle()).isEqualTo("Winner");
    }
}
~~~

Các transaction trong test lần lượt hoàn tất trước khi transaction tiếp theo bắt đầu. Hai snapshot A/B được tải trong hai transaction riêng và trở thành detached sau commit. Transaction cập nhật winner commit trước; khi snapshot B cũ được merge và flush, version không còn khớp nên thao tác thất bại.

Test này không được đặt trong một transaction ngoài bao trọn toàn bộ method. Nếu dùng `@DataJpaTest`, cần tắt transaction mặc định của test hoặc cấu hình transaction độc lập; nếu không, các `TransactionTemplate` mặc định có thể tham gia cùng transaction test và làm sai mô phỏng.

`saveAndFlush()` và `flush()` giúp đẩy SQL trong phạm vi test. Exception vẫn có thể được phát hiện khi transaction commit; vì vậy assertion bao quanh toàn bộ `transactions.execute`, không chỉ một dòng gọi save.

### 14.1. Kiểm thử expectedVersion từ client

Ngoài test race giữa hai transaction, cần test request stale:

1. Tạo document version 1.
2. Cập nhật document lên version 2.
3. Gửi command có expectedVersion 1.
4. Xác nhận service từ chối trước khi thay đổi nội dung.
5. Đọc lại và xác nhận dữ liệu version 2 không bị ghi đè.

Test này bảo vệ khoảng thời gian giữa lần client đọc dữ liệu và lần gửi lệnh cập nhật, vốn không nằm trong một transaction database duy nhất.

### 14.2. Kiểm thử exception tại commit

Nếu service không flush tường minh, test cần bao quanh lời gọi qua Spring proxy hoặc transaction template để bắt lỗi ở thời điểm commit. Chỉ assert rằng method body đã chạy không đủ để kết luận transaction thành công.

### 14.3. Dùng database gần production

Optimistic version check cơ bản thường có thể kiểm thử trên database embedded, nhưng locking, timeout, isolation và deadlock phụ thuộc database. Với hành vi concurrency quan trọng, nên chạy integration test bằng Testcontainers với engine và phiên bản gần production.

## 15. Quan sát conflict trong production

Theo dõi số lần optimistic conflict để biết chiến lược hiện tại có còn phù hợp.

Các metric hữu ích:

- Số `OptimisticLockException` hoặc `OptimisticLockingFailureException` theo entity/use case.
- Tỷ lệ conflict trên tổng số update.
- Số lần retry trung bình và tỷ lệ retry thành công.
- Số request trả 409/412.
- Thời gian transaction và thời gian chờ lock.
- Các entity ID hoặc aggregate thường xuyên bị tranh chấp, theo cách log đã ẩn thông tin nhạy cảm.

Nếu một loại entity có conflict tăng đột biến, kiểm tra:

- Nhiều request đang cập nhật cùng một hàng.
- Transaction kéo dài không cần thiết.
- Client giữ form quá lâu trước khi Save.
- Job nền và request tương tác cùng ghi một aggregate.
- Bulk update hoặc native SQL đang bỏ qua version.
- Version root chưa được tăng khi invariant phụ thuộc nhiều entity con.

Không log toàn bộ entity payload hoặc dữ liệu cá nhân chỉ để chẩn đoán conflict. Log ID kỹ thuật, loại thao tác, version dự kiến/hiện tại khi phù hợp và correlation ID theo chính sách bảo mật.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dữ liệu cũ ghi đè dữ liệu mới | Entity không có @Version hoặc code bỏ qua version | Thêm version và kiểm tra mọi đường ghi |
| Exception xuất hiện ở commit, không phải save | Provider trì hoãn version check đến flush/commit | Xử lý ở ranh giới transaction |
| Bắt exception nhưng transaction vẫn rollback | Transaction đã bị đánh dấu rollback-only | Để exception thoát khỏi transaction; xử lý ở caller |
| Người dùng gửi form cũ nhưng không có exception | Service tải version mới rồi áp dụng payload cũ | Gửi expectedVersion/ETag và so sánh |
| Merge ghi đè nhiều field | Map toàn bộ DTO thành detached entity | Load entity managed rồi áp dụng field được phép |
| Retry vẫn lỗi liên tục | Dùng lại stale object hoặc transaction cũ | Tải lại entity trong transaction mới |
| Retry gửi email/message nhiều lần | Side effect nằm trong transaction retry | Dùng outbox và idempotency key |
| Version không đổi sau bulk update | Bulk DML bypass version lifecycle | Dùng compare-and-set và tăng version tường minh |
| Hai entity con thay đổi mà root không conflict | Version chỉ bảo vệ entity được version hóa | Tăng version root hoặc dùng lock protocol |
| Pessimistic lock gây request chờ lâu | Transaction giữ lock quá lâu | Rút ngắn transaction, timeout và xem lại contention |
| Test không tái hiện conflict | Hai thao tác dùng chung transaction/persistence context | Dùng hai transaction độc lập |
| Tắt @Version để tránh lỗi | Conflict bị che và lost update có thể quay lại | Tách aggregate hoặc thiết kế command update phù hợp |

## 17. Checklist xử lý optimistic locking

- [ ] Entity được truy cập đồng thời có trường `@Version` phù hợp.
- [ ] Ứng dụng không tự sửa giá trị version.
- [ ] DTO/response trả version để client có thể gửi expected version khi cần.
- [ ] Service kiểm tra expectedVersion để phát hiện form/request stale.
- [ ] Transaction để provider kiểm tra race giữa load và flush/commit.
- [ ] Đã hiểu exception có thể xuất hiện tại merge, flush hoặc commit.
- [ ] Không bắt lỗi rồi tiếp tục dùng transaction đã rollback-only.
- [ ] Spring exception translation được cấu hình và kiểm tra.
- [ ] API có hợp đồng 409 hoặc 412 rõ ràng.
- [ ] Merge detached entity không làm ghi đè trường ngoài ý muốn.
- [ ] Retry chỉ áp dụng cho thao tác có thể tính lại an toàn.
- [ ] Mỗi lần retry dùng transaction và persistence context mới.
- [ ] Retry có giới hạn và có backoff phù hợp.
- [ ] Side effect ngoài database không lặp khi retry.
- [ ] Bulk DML có compare-and-set/version handling riêng.
- [ ] Aggregate invariant được bảo vệ ở đúng root hoặc bằng database constraint.
- [ ] Có test stale request và test hai transaction cạnh tranh.
- [ ] Test bắt exception quanh cả transaction commit.
- [ ] Theo dõi conflict rate, retry rate và transaction duration.

## 18. Tài liệu tham khảo

- [Jakarta Persistence 3.2 — Optimistic Locking](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html) — version attributes, merge, version checks và yêu cầu rollback khi optimistic lock thất bại.
- [Jakarta Persistence — Version API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/version) — annotation `@Version` và kiểu dữ liệu version được hỗ trợ.
- [Hibernate ORM 8 — Locking](https://docs.hibernate.org/orm/8.0/userguide/html_single/#locking) — versioned optimistic locking, lock modes, bulk update/delete và stale state.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html) — dùng `@Lock` để đặt LockModeType cho query method và CRUD method.
- [Spring Framework — DAO Support and Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html) — chuyển exception JPA/Hibernate sang hệ thống `DataAccessException` của Spring.
- [Spring Framework — ObjectOptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/ObjectOptimisticLockingFailureException.html) — exception Spring cung cấp thông tin entity và identifier khi optimistic locking thất bại.

Optimistic locking giúp phát hiện cập nhật dựa trên phiên bản cũ và ngăn lost update. Để xử lý đúng, hãy bảo vệ cả khoảng thời gian transaction bằng `@Version` lẫn khoảng thời gian người dùng giữ dữ liệu bằng expectedVersion/ETag. Khi conflict xảy ra, để transaction lỗi rollback, tải trạng thái mới trong transaction khác và chỉ retry khi nghiệp vụ có thể tính lại an toàn. Với contention cao hoặc invariant phức tạp, cân nhắc lock mode và thiết kế lại ranh giới aggregate.

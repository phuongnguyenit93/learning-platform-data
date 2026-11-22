# Khôi phục khi một lô thất bại và thiết kế xử lý lặp an toàn

## Mục tiêu

Xử lý hàng loạt thường chia dữ liệu thành nhiều lô nhỏ (chunk) để giới hạn bộ nhớ, thời gian transaction và kích thước batch SQL. Một lô có thể thất bại vì dữ liệu không hợp lệ, vi phạm ràng buộc, xung đột đồng thời, deadlock, timeout hoặc sự cố kết nối. Ứng dụng cần biết phần nào đã commit, phần nào đã rollback và có thể chạy lại mà không tạo dữ liệu trùng hoặc áp dụng nghiệp vụ hai lần.

Sau bài này, bạn có thể:

- Phân biệt rollback của một transaction với tiến độ của toàn bộ batch job.
- Thiết kế ranh giới transaction theo lô và chủ động flush để phát hiện lỗi.
- Phân loại lỗi có thể retry và lỗi cần xử lý dữ liệu.
- Retry một lô bằng transaction mới, có giới hạn và backoff.
- Lưu checkpoint để tiếp tục job sau khi tiến trình dừng.
- Thiết kế thao tác idempotent bằng khóa nghiệp vụ, idempotency key và unique constraint.
- Xử lý an toàn trường hợp không biết chắc transaction đã commit hay chưa.
- Bảo vệ side effect bên ngoài cơ sở dữ liệu bằng transactional outbox và consumer idempotent.

## 1. Xác định chính xác phạm vi thất bại

Giả sử một job nhập 10.000 dòng và chia thành 100 lô, mỗi lô 100 dòng. Nếu mỗi lô chạy trong transaction riêng, tiến trình có thể có trạng thái:

| Lô | Kết quả | Trạng thái dữ liệu |
|---|---|---|
| 1–35 | Commit | Đã lưu bền vững |
| 36 | Thất bại | Các thay đổi trong transaction lô 36 được rollback |
| 37–100 | Chưa chạy | Chưa được xử lý |

Trong thiết kế này, lỗi ở lô 36 không tự động rollback 35 lô đã commit trước đó. Khi khởi động lại, job có thể tiếp tục từ lô 36 nếu checkpoint và dữ liệu đầu vào cho phép.

Nếu toàn bộ 10.000 dòng nằm trong một transaction duy nhất, một lỗi làm transaction rollback sẽ hủy toàn bộ thay đổi thuộc transaction đó. Cách này phù hợp khi nghiệp vụ yêu cầu tất cả hoặc không có gì, nhưng transaction lớn có thể giữ nhiều entity trong persistence context, giữ khóa lâu và tạo áp lực lên log giao dịch.

Cần phân biệt ba khái niệm:

- **Batch job:** toàn bộ công việc nhập hoặc cập nhật dữ liệu.
- **Chunk:** một nhóm bản ghi được xử lý như một đơn vị tiến độ.
- **Transaction:** ranh giới commit hoặc rollback của các thao tác cơ sở dữ liệu.

Một chunk có thể tương ứng với một transaction, nhưng đó là quyết định thiết kế. Trước khi viết cơ chế retry, hãy xác định rõ đơn vị nào phải thành công cùng nhau.

## 2. Flush, rollback và trạng thái persistence context

JPA có thể trì hoãn SQL cho đến lúc flush hoặc commit. Vì vậy, một lệnh **save()** trả về thành công chưa chứng minh dữ liệu đã được ghi thành công xuống cơ sở dữ liệu.

Ví dụ:

~~~java
@Transactional
public void importChunk(List<Product> products) {
    productRepository.saveAll(products);
    productRepository.flush();
}
~~~

**saveAll()** yêu cầu lưu các entity; **flush()** yêu cầu persistence context đồng bộ thay đổi xuống cơ sở dữ liệu. Việc flush giúp phát hiện sớm một số lỗi SQL, chẳng hạn vi phạm unique constraint hoặc lỗi cập nhật. Tuy nhiên, flush **không commit transaction**. Transaction vẫn có thể thất bại ở một câu lệnh tiếp theo hoặc lúc commit.

Khi một lỗi persistence xảy ra, transaction có thể bị đánh dấu rollback-only. Không nên bắt một **PersistenceException** rồi tiếp tục xử lý các entity trong cùng transaction như thể chưa có gì xảy ra. Hãy để lỗi thoát ra khỏi ranh giới transaction để transaction rollback, sau đó quyết định retry hoặc ghi nhận lỗi ở bên ngoài.

Với chunk lớn, có thể flush rồi clear persistence context theo từng nhóm:

~~~java
@Transactional
public void importChunk(List<Product> products) {
    int count = 0;

    for (Product product : products) {
        entityManager.persist(product);
        count++;

        if (count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

**flush()** gửi các thay đổi đang chờ xuống cơ sở dữ liệu; **clear()** tách toàn bộ entity khỏi persistence context để giảm bộ nhớ. Sau **clear()**, các đối tượng Java cũ không còn được quản lý. Nếu cần sửa tiếp một entity, hãy tải lại hoặc quản lý lại nó theo đúng vòng đời.

Đoạn code trên chỉ minh họa kiểm soát persistence context trong một transaction. Nếu transaction thất bại ở cuối, các thao tác đã flush trong transaction đó vẫn rollback cùng nhau. Flush từng 50 entity không có nghĩa là đã commit từng nhóm 50 entity.

## 3. Chọn ranh giới transaction cho từng chunk

Với job cần tiếp tục từ phần đã hoàn thành, thường nên dùng một transaction riêng cho mỗi chunk. Một service riêng thực hiện ghi dữ liệu:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChunkWriter {

    private final ProductRepository productRepository;

    public ChunkWriter(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(List<Product> products) {
        productRepository.saveAll(products);
        productRepository.flush();
    }
}
~~~

**REQUIRES_NEW** yêu cầu Spring mở transaction độc lập cho lời gọi này. Khi phương thức được gọi qua Spring proxy và trả về bình thường, transaction của chunk đã hoàn tất commit; khi lỗi thoát ra, transaction đó rollback.

Bộ điều phối gọi service theo từng chunk:

~~~java
@Service
public class BatchRunner {

    private final ChunkWriter chunkWriter;

    public BatchRunner(ChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void run(List<List<Product>> chunks) {
        for (List<Product> chunk : chunks) {
            chunkWriter.write(chunk);
        }
    }
}
~~~

Trong ví dụ, **BatchRunner** không mở một transaction bao trùm toàn bộ job. Mỗi lời gọi **chunkWriter.write()** đi qua bean proxy khác nên ranh giới **REQUIRES_NEW** được áp dụng.

Một lưu ý quan trọng: gọi một phương thức **@Transactional** khác bằng **this.write(...)** bên trong cùng bean là self-invocation. Lời gọi nội bộ đó không đi qua proxy mặc định của Spring, vì vậy propagation có thể không được áp dụng như mong muốn. Hãy đặt worker transaction ở bean riêng hoặc dùng cơ chế quản lý transaction tường minh như **TransactionTemplate**.

Chọn **REQUIRES_NEW** khi mỗi chunk cần commit độc lập, kể cả khi có transaction bên ngoài. Nếu không có transaction bên ngoài, **REQUIRED** trên bean worker cũng có thể tạo transaction riêng cho mỗi lần gọi. Điều quan trọng là bộ điều phối không vô tình gom tất cả chunk vào một transaction.

## 4. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể giải quyết bằng cách chạy lại cùng dữ liệu.

| Nhóm lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Tạm thời | Deadlock, lock timeout, một số lỗi kết nối hoặc lỗi tài nguyên tạm thời | Retry có giới hạn, backoff và transaction mới |
| Xung đột dữ liệu | Optimistic locking thất bại vì entity đã được cập nhật | Tải lại dữ liệu, tính lại nghiệp vụ rồi mới retry |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng, giá trị vượt giới hạn | Đánh dấu bản ghi lỗi, sửa dữ liệu hoặc đưa vào khu vực cách ly |
| Vi phạm quy tắc | Unique constraint, foreign key, check constraint | Xác định là bản ghi trùng hợp lệ hay lỗi nghiệp vụ; không retry mù quáng |
| Lỗi lập trình hoặc cấu hình | Sai mapping, câu JPQL không hợp lệ, thiếu cột schema | Sửa code hoặc cấu hình; retry không giải quyết nguyên nhân |

Spring cung cấp các nhóm exception như **TransientDataAccessException**, **DataIntegrityViolationException** và **OptimisticLockingFailureException**. Việc chuyển đổi exception cụ thể phụ thuộc Spring, JPA provider, driver và hệ quản trị cơ sở dữ liệu. Hãy phân loại dựa trên nguyên nhân thực tế và cấu hình ứng dụng.

Với optimistic locking, retry cùng một entity đã cũ thường chỉ thất bại lần nữa. Phải tải lại entity trong transaction mới và tính lại thay đổi từ trạng thái mới. Với deadlock hoặc lỗi tài nguyên tạm thời, có thể thử lại toàn bộ chunk nếu các thao tác trong chunk đã được thiết kế an toàn khi chạy lặp.

## 5. Retry bằng transaction mới và có giới hạn

Một retry an toàn cần có:

1. Giới hạn số lần thử.
2. Khoảng chờ tăng dần (backoff), có thể thêm jitter để tránh nhiều worker cùng thử lại một lúc.
3. Transaction mới cho mỗi lần thử.
4. Chỉ retry các lỗi được xác định là tạm thời.
5. Ghi log hoặc metric về số lần thử, chunk, nguyên nhân và kết quả cuối.
6. Dừng và chuyển sang xử lý lỗi khi hết số lần thử.

Ví dụ bộ điều phối retry chunk:

~~~java
import java.util.List;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class RetryingBatchRunner {

    private final ChunkWriter chunkWriter;

    public RetryingBatchRunner(ChunkWriter chunkWriter) {
        this.chunkWriter = chunkWriter;
    }

    public void writeWithRetry(List<Product> chunk) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                chunkWriter.write(chunk);
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                try {
                    Thread.sleep(100L * attempt);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                        "Retry was interrupted", interrupted);
                }
            }
        }
    }
}
~~~

Trong ví dụ, mỗi lần gọi **chunkWriter.write()** là một lần đi qua proxy và mở transaction mới. Exception chỉ được bắt sau khi lời gọi worker kết thúc và transaction đã rollback. Không bắt lỗi bên trong worker rồi tiếp tục dùng transaction đã hỏng.

Đây là ví dụ tối giản với backoff tuyến tính. Hệ thống thực tế nên dùng backoff có giới hạn và jitter, cấu hình timeout hợp lý, ghi nhận metric và tránh giữ tài nguyên trong lúc chờ. Không nên retry vô hạn vì một dependency đang hỏng có thể khiến hàng đợi ngày càng lớn.

**TransientDataAccessException** là một nhóm rộng. Trong production, hãy thu hẹp loại lỗi được retry theo hệ quản trị cơ sở dữ liệu và chính sách của ứng dụng. Không đưa **DataIntegrityViolationException** vào danh sách retry mặc định. Nếu retry một chunk chứa cập nhật entity có version, worker phải tải lại dữ liệu mới bên trong mỗi transaction thay vì giữ các entity stale từ trước vòng lặp.

Ví dụ **ChunkWriter** ở trên nhận danh sách entity để minh họa ranh giới transaction. Với job cập nhật bản ghi đã tồn tại, nên truyền DTO hoặc ID từ đầu vào bất biến, sau đó tải lại entity bên trong mỗi lần gọi worker. Không tái sử dụng entity đã bị detach sau rollback hoặc entity mang version cũ.

## 6. Checkpoint và khả năng tiếp tục job

Checkpoint ghi nhận tiến độ đã hoàn thành để job có thể tiếp tục sau khi tiến trình dừng hoặc máy chủ khởi động lại.

Một bảng trạng thái job có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| job_id | Định danh một lần chạy logic của job |
| chunk_no | Số thứ tự chunk |
| status | PENDING, RUNNING, COMPLETED hoặc FAILED |
| attempt_count | Số lần thử |
| started_at, completed_at | Thời điểm bắt đầu và hoàn tất |
| error_code, error_message | Thông tin lỗi có thể dùng để điều tra |

**Checkpoint phải phản ánh dữ liệu đã commit.** Nếu ghi trạng thái COMPLETED trước khi dữ liệu chunk commit, tiến trình có thể dừng sau khi cập nhật checkpoint nhưng trước commit dữ liệu. Khi chạy lại, job bỏ qua chunk và dữ liệu bị thiếu.

Có hai cách tổ chức phổ biến:

- **Cùng transaction:** ghi dữ liệu của chunk và đánh dấu chunk COMPLETED trong cùng transaction. Nếu transaction rollback, cả dữ liệu và checkpoint đều rollback; nếu commit, cả hai cùng bền vững.
- **Checkpoint sau commit:** worker commit dữ liệu trước, sau đó một transaction khác cập nhật checkpoint. Nếu tiến trình dừng giữa hai bước, chunk có thể được chạy lại. Cách này cần thao tác idempotent hoặc một bản ghi hoàn tất chunk có khóa duy nhất để lần chạy lại nhận ra công việc đã xong.

Không thể chỉ dựa vào số thứ tự chunk nếu tập dữ liệu nguồn có thể thay đổi trong lúc job chạy. Hãy cố định phạm vi đầu vào bằng snapshot, thời điểm tạo job, phiên bản file hoặc danh sách ID đã được lưu. Khi resume, dùng cùng job_id và cùng tập đầu vào để chunk không bị lệch.

Với dữ liệu được phân trang, nên có thứ tự ổn định, chẳng hạn theo ID tăng dần, và lưu khóa cuối cùng đã xử lý. Tránh dựa vào offset trên một tập dữ liệu liên tục thay đổi vì các bản ghi được thêm hoặc xóa có thể làm vị trí trang dịch chuyển.

## 7. Idempotency: chạy lặp nhưng kết quả không bị nhân đôi

Một thao tác là **idempotent** nếu thực hiện một lần hay nhiều lần với cùng định danh và cùng dữ liệu đều dẫn đến cùng một trạng thái nghiệp vụ.

Ví dụ:

- Đặt trạng thái đơn hàng thành **PAID** có thể idempotent nếu chuyển trạng thái được kiểm soát và không phát sinh side effect lặp.
- Trừ 100 đơn vị khỏi số dư mỗi lần gọi không idempotent: gọi hai lần sẽ trừ 200.
- Ghi nhận một giao dịch nhập hàng theo mã tham chiếu duy nhất có thể idempotent nếu cơ sở dữ liệu ngăn mã đó được áp dụng hai lần.

Một câu lệnh **save()** không tự làm cho nghiệp vụ idempotent. Nếu cùng request được gửi lại sau timeout, ứng dụng cần nhận ra đó là cùng một yêu cầu logic.

### 7.1. Dùng idempotency key

Mỗi yêu cầu hoặc mỗi phần tử đầu vào cần một khóa ổn định, ví dụ:

- **client-request-id** do bên gọi tạo.
- Mã giao dịch từ hệ thống nguồn.
- Cặp **(job_id, source_record_id)** cho một dòng nhập dữ liệu.
- Cặp **(job_id, chunk_no)** cho một chunk.

Khóa phải được giữ nguyên qua các lần retry. Không tạo UUID mới ở mỗi lần thử, vì khi đó cơ sở dữ liệu sẽ coi mỗi lần thử là một thao tác mới.

Nên lưu thêm hash hoặc phiên bản payload. Nếu cùng idempotency key nhưng payload khác, hãy trả lỗi xung đột thay vì âm thầm coi yêu cầu mới là bản sao của yêu cầu cũ.

### 7.2. Bảo vệ khóa bằng unique constraint

Một cách triển khai là lưu mỗi command đã xử lý trong một bảng có khóa chính là idempotency key:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "processed_command")
public class ProcessedCommand {

    @Id
    @Column(name = "idempotency_key", nullable = false, updatable = false)
    private String idempotencyKey;

    @Column(name = "payload_hash", nullable = false, updatable = false)
    private String payloadHash;

    protected ProcessedCommand() {
    }

    public ProcessedCommand(String idempotencyKey, String payloadHash) {
        this.idempotencyKey = idempotencyKey;
        this.payloadHash = payloadHash;
    }

    public String getPayloadHash() {
        return payloadHash;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProcessedCommandRepository
        extends JpaRepository<ProcessedCommand, String> {
}
~~~

Service xử lý command và thay đổi dữ liệu nghiệp vụ trong cùng transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CommandProcessor {

    private final ProcessedCommandRepository processedCommands;
    private final AccountRepository accountRepository;

    public CommandProcessor(
            ProcessedCommandRepository processedCommands,
            AccountRepository accountRepository) {
        this.processedCommands = processedCommands;
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void apply(
            String key,
            String payloadHash,
            Long accountId,
            long amount) {

        processedCommands.saveAndFlush(
            new ProcessedCommand(key, payloadHash));

        Account account = accountRepository.findById(accountId)
            .orElseThrow(() ->
                new IllegalArgumentException("Account not found"));

        account.debit(amount);
    }
}
~~~

Ví dụ giả định **Account** có phương thức **debit(long)** kiểm tra quy tắc số dư và **AccountRepository** là Spring Data repository. **saveAndFlush()** buộc kiểm tra khóa trùng sớm. Bản ghi processed command và thay đổi Account nằm trong cùng transaction: nếu cập nhật Account thất bại, bản ghi idempotency cũng rollback; nếu commit, cả hai cùng được lưu.

Nếu hai request cùng key chạy đồng thời, unique constraint ở cơ sở dữ liệu là hàng rào cuối cùng. Một transaction có thể chờ transaction kia; sau khi transaction đầu commit, transaction còn lại không thể chèn cùng key. Không dựa vào mẫu **findById()** rồi mới **save()** như một cơ chế khóa, vì hai request có thể cùng thấy chưa tồn tại trước khi cả hai ghi.

### 7.3. Xử lý yêu cầu trùng bên ngoài transaction

Khi **saveAndFlush()** phát hiện khóa đã tồn tại, transaction hiện tại phải rollback. Hãy bắt lỗi ở tầng gọi nằm ngoài transaction của **CommandProcessor**, rồi đọc bản ghi đã được commit:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

@Service
public class IdempotentCommandFacade {

    private final CommandProcessor processor;
    private final ProcessedCommandRepository processedCommands;

    public IdempotentCommandFacade(
            CommandProcessor processor,
            ProcessedCommandRepository processedCommands) {
        this.processor = processor;
        this.processedCommands = processedCommands;
    }

    public void execute(
            String key,
            String payloadHash,
            Long accountId,
            long amount) {

        try {
            processor.apply(key, payloadHash, accountId, amount);
        } catch (DataIntegrityViolationException ex) {
            ProcessedCommand existing =
                processedCommands.findById(key).orElse(null);

            if (existing == null) {
                throw ex;
            }

            if (!existing.getPayloadHash().equals(payloadHash)) {
                throw new IllegalArgumentException(
                    "Idempotency key was reused with a different payload", ex);
            }

            // Cùng key và cùng payload: yêu cầu đã được áp dụng.
        }
    }
}
~~~

Facade không có **@Transactional**, nên exception rời khỏi proxy của **CommandProcessor** sau khi transaction thất bại. Lệnh đọc **findById()** được thực hiện sau đó trong transaction đọc của repository. Nếu lỗi ràng buộc đến từ một nguyên nhân khác và không có command tương ứng đã commit, facade ném lại exception ban đầu.

Trong ứng dụng thực tế, hãy giới hạn việc coi lỗi là duplicate vào đúng constraint idempotency key. Có thể kiểm tra tên constraint hoặc mã lỗi đặc thù của hệ quản trị. Ví dụ trên kiểm tra thêm bản ghi và payload hash để tránh nuốt một lỗi toàn vẹn dữ liệu không liên quan.

Không dùng cơ chế này nếu command còn thực hiện side effect ngoài cơ sở dữ liệu trước khi commit. Email, HTTP call hoặc thao tác trên hệ thống khác không tự rollback cùng transaction JPA.

## 8. Xử lý side effect bằng transactional outbox

Giả sử một command cập nhật đơn hàng và cần gửi sự kiện **OrderPaid** đến message broker. Nếu ứng dụng commit đơn hàng rồi gửi message thất bại, hệ thống khác không nhận được sự kiện. Nếu gửi message trước rồi transaction cơ sở dữ liệu rollback, hệ thống khác lại nhận một sự kiện cho thay đổi chưa tồn tại.

Transactional outbox giải quyết khoảng trống này:

1. Trong cùng transaction JPA, cập nhật dữ liệu nghiệp vụ và thêm một bản ghi outbox.
2. Commit transaction. Dữ liệu nghiệp vụ và sự kiện chờ gửi cùng tồn tại hoặc cùng rollback.
3. Một worker đọc các bản ghi outbox chưa gửi và publish đến broker.
4. Sau khi publish thành công, worker đánh dấu bản ghi đã gửi hoặc lưu trạng thái giao nhận.
5. Nếu worker dừng sau khi publish nhưng trước khi đánh dấu, message có thể được gửi lại.

Vì bước cuối vẫn có thể lặp, consumer phải idempotent. Ví dụ consumer lưu **event_id** với unique constraint và chỉ áp dụng thay đổi nghiệp vụ khi event_id chưa được xử lý. Cách thiết kế này thường đạt giao nhận at-least-once với xử lý trùng an toàn; không nên tuyên bố hệ thống có exactly-once end-to-end chỉ vì đã dùng outbox.

Outbox phù hợp với sự kiện cần được phát đi sau commit, chẳng hạn thông báo đơn hàng, đồng bộ dữ liệu hoặc cập nhật hệ thống khác. Với email hoặc API bên ngoài, cũng nên dùng một hàng đợi công việc bền vững và khóa idempotency của nhà cung cấp nếu có.

## 9. Thiết kế lại dữ liệu lỗi và dead-letter

Một batch job cần phân biệt lỗi của một bản ghi với lỗi làm hỏng toàn bộ chunk.

Nếu một dòng có dữ liệu sai định dạng, có thể lưu thông tin lỗi và tiếp tục các dòng khác khi nghiệp vụ cho phép. Nếu lỗi là deadlock hoặc mất kết nối, nên rollback chunk và thử lại toàn bộ đơn vị transaction. Không tiếp tục sau lỗi persistence trong cùng transaction đã bị đánh dấu rollback-only.

Một mô hình vận hành hữu ích:

- **PENDING:** chưa xử lý.
- **PROCESSING:** đang được worker nhận xử lý; cần lease hoặc timeout để phục hồi khi worker chết.
- **COMPLETED:** đã commit kết quả.
- **RETRY_WAIT:** lỗi tạm thời, chờ thời điểm thử lại.
- **FAILED_PERMANENT:** lỗi không thể giải quyết bằng retry tự động.
- **DEAD_LETTER:** vượt số lần thử hoặc cần người vận hành kiểm tra.

Ghi lại mã lỗi, thông điệp đã làm sạch, source record ID, job ID, chunk number, attempt count và thời điểm. Tránh ghi thông tin bí mật hoặc payload nhạy cảm vào log không được bảo vệ.

Một dead-letter record cần đủ thông tin để sửa và phát lại có chủ đích. Khi phát lại, giữ nguyên khóa nghiệp vụ hoặc idempotency key nếu vẫn là cùng một thao tác logic. Nếu người vận hành đã sửa payload và đó là một thao tác mới, hãy tạo phiên bản hoặc định danh mới theo quy tắc nghiệp vụ, đồng thời giữ liên kết đến lần xử lý cũ để truy vết.

## 10. Kiểm thử phục hồi và tính idempotent

Không chỉ kiểm thử trường hợp batch chạy thành công. Hãy kiểm thử các điểm dừng và lỗi có thể xảy ra:

1. **Lỗi giữa chunk:** tạo dữ liệu khiến một câu lệnh trong chunk vi phạm constraint; xác nhận toàn bộ chunk rollback.
2. **Lỗi sau commit nhưng trước checkpoint:** mô phỏng tiến trình dừng sau khi chunk commit; chạy lại và xác nhận không tạo dữ liệu hoặc side effect trùng.
3. **Retry deadlock hoặc timeout:** giả lập lỗi tạm thời; xác nhận mỗi lần thử dùng transaction mới và số lần thử không vượt giới hạn.
4. **Lỗi dữ liệu vĩnh viễn:** xác nhận bản ghi được đánh dấu FAILED_PERMANENT hoặc chuyển sang dead-letter, không retry liên tục.
5. **Hai request cùng idempotency key:** chạy đồng thời; xác nhận chỉ một lần thay đổi nghiệp vụ được áp dụng.
6. **Cùng key, payload khác:** xác nhận request thứ hai bị từ chối như một xung đột.
7. **Outbox gửi lặp:** publish cùng event nhiều lần; xác nhận consumer chỉ áp dụng hiệu ứng nghiệp vụ một lần.
8. **Resume job:** dừng sau một số chunk đã commit, khởi động lại cùng job_id và xác nhận các chunk đã hoàn tất không bị áp dụng lần nữa.

Dùng transaction và thread độc lập trong integration test để tái hiện tranh chấp thật. Kiểm tra trạng thái cuối cùng bằng một transaction mới, không chỉ kiểm tra entity còn nằm trong persistence context của test. Nên chạy các test khóa, deadlock và batch với cùng hệ quản trị cơ sở dữ liệu mà ứng dụng triển khai.

## 11. Checklist thiết kế trước khi triển khai

- Xác định toàn bộ job cần atomic hay chỉ từng chunk cần atomic.
- Chọn kích thước chunk theo bộ nhớ, thời gian transaction, batch SQL và khả năng phục hồi.
- Flush có chủ đích để phát hiện lỗi; clear khi cần giảm persistence context.
- Dùng transaction riêng cho mỗi chunk nếu cần commit tiến độ độc lập.
- Chỉ retry lỗi tạm thời; đặt giới hạn, backoff và jitter.
- Tải lại entity và tính lại nghiệp vụ sau optimistic locking conflict.
- Lưu checkpoint cùng transaction với dữ liệu khi có thể; nếu checkpoint tách rời, bảo đảm replay an toàn.
- Dùng idempotency key ổn định và unique constraint ở cơ sở dữ liệu.
- Kiểm tra payload hash để phát hiện cùng key nhưng khác nội dung.
- Đưa side effect bên ngoài vào transactional outbox và làm consumer idempotent.
- Lưu trạng thái lỗi, số lần thử và thông tin đủ để điều tra hoặc phát lại.
- Kiểm thử rollback, retry, crash giữa commit và checkpoint, request trùng và resume job.

Một batch job đáng tin cậy phải trả lời được ba câu hỏi: dữ liệu nào đã commit, dữ liệu nào cần xử lý lại và làm sao bảo đảm lần chạy lại không áp dụng nghiệp vụ thêm lần nữa. Ranh giới transaction, checkpoint và idempotency cần được thiết kế cùng nhau để việc phục hồi luôn có kết quả xác định.
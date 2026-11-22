# Nhập dữ liệu lớn với chia lô, flush và phục hồi lỗi

Khi nhập hàng chục nghìn hoặc hàng triệu bản ghi bằng Spring Data JPA, cách xử lý từng Entity trong một transaction lớn thường gây áp lực lên heap, persistence context, connection, lock và transaction log. Cách tiếp cận phổ biến là chia dữ liệu thành các chunk có kích thước kiểm soát, ghi theo JDBC batch, flush/clear persistence context định kỳ và xác định rõ chunk nào được commit độc lập.

Ba khái niệm cần tách biệt:

- **JDBC batch size:** số câu lệnh SQL cùng loại được gom để gửi theo batch xuống database.
- **Flush/clear interval:** số Entity xử lý trước khi đồng bộ persistence context xuống database rồi giải phóng các Entity đang managed.
- **Transaction chunk size:** số bản ghi thuộc một transaction và cùng commit hoặc rollback.

Ba giá trị này có liên quan nhưng không bắt buộc bằng nhau. Có thể flush nhiều lần trong một transaction chunk, nhưng transaction chỉ commit khi phương thức transactional kết thúc thành công.

## 1. Vì sao cần chia lô khi nhập dữ liệu lớn?

Giả sử cần nhập 500.000 dòng CSV. Nếu đọc và lưu toàn bộ trong một transaction:

~~~java
@Transactional
public void importAll(List<ImportRow> rows) {
    for (ImportRow row : rows) {
        repository.save(toEntity(row));
    }
}
~~~

Cách làm này có thể gặp các vấn đề:

- Persistence context giữ rất nhiều Entity managed.
- Hibernate phải theo dõi thay đổi và dirty checking trên một tập đối tượng lớn.
- Bộ nhớ heap tăng và garbage collection tốn thời gian.
- Transaction giữ connection lâu.
- Lock có thể tồn tại lâu và làm các transaction khác phải chờ.
- Nếu lỗi ở dòng cuối, toàn bộ công việc trước đó có thể rollback.
- Retry toàn bộ file gây lặp lại lượng công việc lớn.
- Việc xác định chính xác dòng lỗi và tiếp tục từ điểm đã xử lý trở nên khó khăn.

Chia dữ liệu thành các chunk nhỏ giúp giới hạn bộ nhớ, thời gian transaction và phạm vi phục hồi. Ví dụ 500.000 dòng có thể được xử lý thành nhiều chunk, mỗi chunk 500 hoặc 1.000 dòng tùy workload và database.

Không có một chunk size tối ưu cho mọi hệ thống. Cần đo trên dữ liệu và database gần production.

## 2. Phân biệt chunk, flush và commit

Một luồng nhập dữ liệu thường có ba tầng:

~~~text
File / nguồn dữ liệu
        |
        v
Đọc một transaction chunk
        |
        v
Xử lý các nhóm Entity nhỏ
        |
        +--> persist/update Entity
        +--> flush theo interval
        +--> clear persistence context
        |
        v
Cập nhật checkpoint trong cùng transaction
        |
        v
COMMIT transaction chunk
        |
        v
Đọc chunk tiếp theo
~~~

Ví dụ transaction chunk có 1.000 dòng và flush interval là 100:

- Xử lý 100 dòng rồi flush/clear.
- Xử lý 100 dòng tiếp theo rồi flush/clear.
- Lặp lại cho đến hết 1.000 dòng.
- Cập nhật checkpoint.
- Transaction commit một lần cho cả 1.000 dòng.

Nếu lỗi xảy ra ở dòng 950, toàn bộ 1.000 dòng trong transaction chunk đó vẫn rollback, kể cả các nhóm 100 dòng đã flush trước đó. Flush gửi SQL xuống database trong transaction hiện tại; nó không commit.

## 3. Persistence context và dirty checking

Entity được load hoặc persist trong transaction thường trở thành managed. Hibernate theo dõi trạng thái của các Entity managed để phát hiện thay đổi và tạo SQL khi flush.

Ví dụ:

~~~java
@Transactional
public void updateCustomer(Long id) {
    Customer customer = repository.findById(id).orElseThrow();
    customer.changeName("New name");
    // Không cần gọi save() lại để dirty checking nhận thay đổi.
}
~~~

Trong batch, nếu mỗi lần persist thêm hàng nghìn Entity mà không clear, persistence context có thể giữ tất cả object đến cuối transaction.

EntityManager.clear() detach toàn bộ Entity đang managed trong persistence context hiện tại. Sau clear:
- Các Entity trước đó không còn được dirty checking theo dõi.
- Không được tiếp tục thay đổi object cũ rồi mong JPA tự lưu.
- Các object cần cập nhật tiếp phải được load lại hoặc merge có chủ đích.
- Các Entity mới được persist sau clear sẽ lại trở thành managed.

Với dữ liệu import dạng DTO/record, thường chỉ cần chuyển từng dòng thành Entity, persist, flush và clear; không cần giữ Entity cũ trong bộ nhớ.

## 4. flush() không phải commit

EntityManager.flush() yêu cầu persistence provider đồng bộ các thay đổi đang chờ trong persistence context xuống database.

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

Sau flush:
- SQL có thể đã được thực thi.
- Constraint, unique violation hoặc lỗi SQL có thể xuất hiện.
- Database vẫn đang ở trong transaction hiện tại.
- Transaction vẫn có thể rollback.

Commit chỉ xảy ra ở ranh giới transaction do transaction manager quản lý, thường khi phương thức @Transactional kết thúc bình thường.

Ví dụ:

~~~java
@Transactional
public void saveBatch(List<ImportRow> rows) {
    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
    }

    entityManager.flush();

    if (shouldFailForDemo()) {
        throw new ImportException("Simulated failure");
    }
}
~~~

Nếu ImportException là RuntimeException và thoát khỏi phương thức, transaction rollback dù flush đã chạy. Các INSERT đã gửi xuống database trong transaction đó không được commit.

## 5. clear() giúp giới hạn bộ nhớ

Kết hợp flush và clear theo interval:

~~~java
@Transactional
public void persistChunk(List<ImportRow> rows) {
    int count = 0;

    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
        count++;

        if (count % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Flush trước clear để các thay đổi đang chờ được đồng bộ xuống database. Sau đó clear để persistence context không tiếp tục giữ các Entity vừa xử lý.

Không clear trước flush nếu các thay đổi cần được lưu chưa được đồng bộ. Clear sẽ detach Entity; các thay đổi chưa flush trên chúng có thể không được ghi.

Ví dụ trên giả định mỗi dòng tạo Entity mới. Nếu cần cập nhật Entity đã load, phải bảo đảm mọi thay đổi được flush trước clear. Không tiếp tục dùng các reference đã detach như thể chúng còn managed.

## 6. Cấu hình JDBC batching của Hibernate

Flush/clear kiểm soát persistence context, còn JDBC batching kiểm soát cách Hibernate gửi câu lệnh SQL.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
          batch_versioned_data: true
        order_inserts: true
        order_updates: true
~~~

Ý nghĩa:
- hibernate.jdbc.batch_size: kích thước batch JDBC tối đa cho các statement phù hợp.
- hibernate.order_inserts: sắp xếp INSERT để tăng khả năng gom statement cùng loại.
- hibernate.order_updates: sắp xếp UPDATE để cải thiện batching và có thể giảm deadlock trong một số workload.
- hibernate.jdbc.batch_versioned_data: cho phép batching các update có version nếu driver/provider hỗ trợ kiểm tra số dòng cập nhật phù hợp.

Các thuộc tính và mặc định phụ thuộc phiên bản Hibernate. Hãy kiểm tra cấu hình được hỗ trợ trong phiên bản dự án.

JDBC batch size 50 không có nghĩa Hibernate tạo một câu INSERT gồm 50 dòng. Thông thường driver nhận một batch gồm nhiều lần thực thi cùng prepared statement. SQL log có thể hiển thị khác với số round trip thực tế; dùng thống kê driver/database hoặc công cụ quan sát phù hợp để xác nhận batching.

## 7. Lưu ý về IDENTITY và JDBC insert batching

Chiến lược sinh ID ảnh hưởng đến khả năng batching. Với Hibernate, dùng GenerationType.IDENTITY thường vô hiệu hóa JDBC insert batching cho Entity sử dụng identity generator vì Hibernate cần thực thi INSERT để lấy khóa chính được database sinh.

Ví dụ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Nếu workload nhập lớn phụ thuộc insert batching, hãy xem xét sequence generator hoặc cơ chế ID phù hợp với database/provider:

~~~java
@Id
@GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "import_record_seq"
)
@SequenceGenerator(
        name = "import_record_seq",
        sequenceName = "import_record_seq",
        allocationSize = 50
)
private Long id;
~~~

Đây là ví dụ dùng database hỗ trợ sequence. Không phải mọi database đều hỗ trợ cùng chiến lược. Sequence allocation có thể giảm số lần lấy ID và cho phép batching tốt hơn, nhưng phải kiểm tra schema, increment/allocation size và cấu hình Hibernate thực tế.

Không đổi ID strategy chỉ để tối ưu batch nếu hệ thống có yêu cầu tương thích hoặc dữ liệu hiện tại không cho phép. Hãy đo và chọn theo database.

## 8. saveAll() không đồng nghĩa với một bulk INSERT

JpaRepository.saveAll() tiện lợi để lưu một collection:

~~~java
repository.saveAll(entities);
~~~

Nhưng không nên hiểu rằng phương thức này luôn tạo một câu INSERT duy nhất. Spring Data thường lặp qua Entity và gọi save cho từng phần tử; Hibernate có thể gom SQL tương thích thành JDBC batch nếu cấu hình và ID strategy cho phép.

Với Entity mới, newness detection của Spring Data quyết định persist hay merge. Nếu ID được gán trước hoặc trạng thái newness không rõ, saveAll có thể đi theo nhánh merge và phát sinh chi phí đọc/đồng bộ không cần thiết.

Với import Entity mới, hãy thiết kế ID/newness strategy đúng. Nếu cần kiểm soát rõ từng lần persist và flush/clear, có thể dùng EntityManager trực tiếp trong custom repository/service chuyên trách.

## 9. Chọn ba kích thước độc lập

Ba tham số nên được cân nhắc riêng:

| Tham số | Ví dụ | Tác động chính |
|---|---:|---|
| JDBC batch size | 50 | Số statement được gom khi gửi qua JDBC |
| Flush/clear interval | 100 | Kích thước persistence context và thời điểm đồng bộ SQL |
| Transaction chunk size | 1.000 | Số dòng commit/rollback cùng nhau |

Ví dụ một transaction chunk 1.000 dòng có thể thực hiện 10 lần flush/clear, mỗi lần 100 dòng, trong khi JDBC batch size là 50.

Nếu flush interval nhỏ hơn JDBC batch size, có thể không tạo đủ statement cùng loại cho batch tối đa. Nếu flush interval quá lớn, persistence context giữ nhiều Entity hơn và lượng SQL chờ đồng bộ cũng tăng.

Nếu transaction chunk quá lớn, thời gian transaction và phạm vi rollback tăng. Nếu quá nhỏ, chi phí bắt đầu/commit transaction và checkpoint tăng. Cần benchmark các giá trị khác nhau.

## 10. Đặt transaction ở worker xử lý từng chunk

Muốn mỗi chunk commit độc lập, cần đặt ranh giới transaction ở phương thức worker được gọi qua Spring proxy.

Ví dụ coordinator không có transaction bao ngoài:

~~~java
@Service
public class ImportCoordinator {

    private final ImportBatchWorker worker;

    public ImportCoordinator(ImportBatchWorker worker) {
        this.worker = worker;
    }

    public void importAll(List<List<ImportRow>> chunks) {
        for (List<ImportRow> chunk : chunks) {
            worker.persistChunk(chunk);
        }
    }
}
~~~

Worker:

~~~java
@Service
public class ImportBatchWorker {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void persistChunk(List<ImportRow> rows) {
        int count = 0;

        for (ImportRow row : rows) {
            entityManager.persist(toEntity(row));

            if (++count % 100 == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

Coordinator không có transaction nên mỗi lần gọi persistChunk() qua proxy sẽ bắt đầu transaction mới theo REQUIRED mặc định; transaction commit khi method đó kết thúc thành công. Nếu chunk lỗi, chunk đó rollback và exception truyền về coordinator.

Đây là điểm quan trọng: nếu coordinator cũng có @Transactional và worker dùng REQUIRED mặc định, worker sẽ tham gia transaction đang có. Các chunk sẽ không commit độc lập; tất cả có thể cùng commit ở cuối coordinator.

## 11. Khi nào cần REQUIRES_NEW?

Nếu caller đang có transaction nhưng mỗi chunk bắt buộc phải commit độc lập, có thể dùng:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void persistChunk(List<ImportRow> rows) {
    // Persist, flush và clear một chunk.
}
~~~

REQUIRES_NEW tạm ngưng transaction ngoài và mở transaction độc lập cho worker. Khi worker commit, kết quả của chunk tồn tại ngay cả khi transaction ngoài sau đó rollback.

Tradeoff:
- Transaction ngoài có thể giữ connection trong lúc transaction mới cần thêm connection.
- Connection pool cần đủ capacity.
- Lock do transaction ngoài giữ có thể ảnh hưởng transaction chunk.
- Kết quả chunk đã commit không thể rollback cùng transaction ngoài.
- Logic điều phối và retry phức tạp hơn.

Nếu coordinator không cần transaction, để coordinator non-transactional và worker dùng REQUIRED thường đơn giản hơn. Chỉ dùng REQUIRES_NEW khi cần bảo đảm độc lập với một transaction caller có sẵn.

## 12. Tránh self-invocation làm mất transaction boundary

Spring transaction thông thường được áp dụng qua proxy. Lời gọi nội bộ bằng this không đi qua proxy:

~~~java
@Service
public class ImportService {

    public void importAll(List<List<ImportRow>> chunks) {
        for (List<ImportRow> chunk : chunks) {
            this.persistChunk(chunk);
        }
    }

    @Transactional
    public void persistChunk(List<ImportRow> chunk) {
        // Có thể không nhận transaction mới như mong đợi.
    }
}
~~~

Tách coordinator và worker thành hai bean như ví dụ trước giúp lời gọi đi qua proxy. Không dựa vào self-invocation để tạo transaction riêng cho mỗi chunk.

Cũng cần kiểm tra method visibility và proxy mode theo cấu hình Spring. Trong proxy mode thông thường, method được gọi từ bên ngoài bean mới đi qua interceptor transaction.

## 13. Ghi checkpoint cùng transaction với dữ liệu

Nếu job bị dừng giữa chừng, checkpoint giúp xác định vị trí cần tiếp tục. Checkpoint nên được cập nhật trong cùng transaction với các bản ghi của chunk.

Ví dụ:

~~~java
@Transactional
public void persistChunk(
        String jobId,
        long lastSourceSequence,
        List<ImportRow> rows) {

    for (ImportRow row : rows) {
        entityManager.persist(toEntity(row));
    }

    ImportCheckpoint checkpoint =
            checkpointRepository.findById(jobId).orElseThrow();

    checkpoint.advanceTo(lastSourceSequence);

    entityManager.flush();
    entityManager.clear();
}
~~~

Nếu các Entity nhập và checkpoint dùng cùng transaction manager/resource:
- Khi chunk commit, dữ liệu và checkpoint cùng commit.
- Khi chunk rollback, cả dữ liệu và checkpoint đều rollback.
- Khi tiến trình khởi động lại, đọc checkpoint để tiếp tục sau vị trí đã commit.

Không cập nhật checkpoint ở một transaction riêng trước khi dữ liệu chunk commit. Nếu checkpoint tiến lên nhưng dữ liệu rollback, lần chạy sau có thể bỏ qua các dòng chưa được lưu.

Cũng không ghi checkpoint sau commit bằng một thao tác không được bảo vệ rồi giả định không có crash window. Nếu tiến trình chết sau khi dữ liệu commit nhưng trước khi checkpoint cập nhật, chunk có thể được chạy lại. Cách chắc chắn là ghi dữ liệu và checkpoint trong cùng transaction.

## 14. Thiết kế import idempotent

Ngay cả khi checkpoint cùng transaction, job vẫn có thể nhận lại input hoặc được chạy lại do retry, operator restart hay message giao trùng. Hãy thiết kế thao tác import có thể thực hiện lặp an toàn.

Các cách thường dùng:
- Lưu source ID hoặc external key có unique constraint.
- Dùng upsert theo khóa nghiệp vụ nếu database hỗ trợ và semantics phù hợp.
- Ghi nhận job ID và source sequence để phát hiện dòng đã xử lý.
- Không tạo side effect ngoài database trước khi chunk commit.
- Dùng outbox nếu cần phát message sau commit.
- Xác định rõ bản ghi trùng là bỏ qua, cập nhật hay báo lỗi.

Ví dụ Entity lưu khóa nguồn:

~~~java
@Entity
@Table(
    name = "imported_record",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_imported_record_source",
        columnNames = {"source_system", "source_id"}
    )
)
public class ImportedRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String sourceSystem;

    @Column(nullable = false)
    private String sourceId;
}
~~~

Unique constraint bảo vệ dữ liệu kể cả khi hai worker vô tình xử lý cùng một dòng. Ứng dụng vẫn cần xử lý lỗi duplicate theo chính sách đã chọn; không dựa riêng vào kiểm tra “đã tồn tại” trước INSERT vì hai transaction đồng thời vẫn có thể cùng vượt qua bước kiểm tra.

## 15. Phục hồi khi một chunk thất bại

Khi worker ném exception và transaction rollback, coordinator có thể ghi nhận chunk lỗi ở ngoài transaction đó:

~~~java
public void importAll(List<List<ImportRow>> chunks) {
    for (int index = 0; index < chunks.size(); index++) {
        try {
            worker.persistChunk(chunks.get(index));
        } catch (RuntimeException exception) {
            failureRecorder.record(index, exception);
            throw exception;
        }
    }
}
~~~

Ví dụ chỉ minh họa vị trí bắt lỗi. Nếu coordinator ghi failure record vào cùng transaction đã rollback thì record đó cũng rollback. failureRecorder cần chạy sau khi worker transaction đã kết thúc và dùng transaction riêng nếu cần lưu trạng thái lỗi bền vững.

Có thể chọn một trong các chính sách:

- **Fail fast:** dừng job ở chunk lỗi; operator sửa dữ liệu rồi resume.
- **Retry transient failure:** thử lại chunk với backoff cho deadlock, timeout hoặc lỗi mạng tạm thời.
- **Quarantine row:** chuyển dòng dữ liệu không hợp lệ sang bảng lỗi/dead-letter và tiếp tục nếu nghiệp vụ cho phép bỏ qua.
- **Split chunk:** chia chunk lỗi thành các phần nhỏ để cô lập nhóm dòng gây lỗi.
- **Manual review:** giữ trạng thái job và lỗi để người vận hành quyết định.

Không bắt mọi exception rồi tiếp tục như thể chunk thành công. Điều đó có thể làm checkpoint tiến lên hoặc tạo dữ liệu thiếu.

## 16. Phân biệt lỗi transient và lỗi dữ liệu

Không phải lỗi nào cũng nên retry:

| Loại lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Transient database failure | Deadlock, lock timeout, connection reset | Retry có giới hạn và backoff trong transaction mới |
| Constraint violation | Unique, FK, NOT NULL | Kiểm tra dữ liệu hoặc xử lý duplicate theo nghiệp vụ |
| Mapping/type error | Chuỗi không chuyển được sang số/ngày | Sửa/quarantine dòng dữ liệu |
| Optimistic locking | Version thay đổi đồng thời | Đọc lại và quyết định retry theo nghiệp vụ |
| Resource exhaustion | Hết heap, connection pool cạn | Giảm chunk/concurrency, xử lý nguyên nhân vận hành |
| Procedure/external failure | Hệ thống phụ trợ không phản hồi | Retry theo idempotency và timeout phù hợp |

Retry phải chạy trong transaction mới sau khi transaction trước đã rollback. Không tiếp tục chạy các câu lệnh trên transaction đã bị đánh dấu rollback-only.

Nếu dùng Spring Retry hoặc RetryTemplate, hãy đặt retry ở lớp gọi worker transactional qua proxy, hoặc cấu hình thứ tự advisor rõ ràng để mỗi lần thử có transaction mới. Kiểm thử thứ tự retry/transaction với cấu hình thực tế; không giả định annotation tự tạo transaction mới khi self-invocation.

## 17. Không nuốt exception trong worker transactional

Ví dụ không an toàn:

~~~java
@Transactional
public void persistChunk(List<ImportRow> rows) {
    try {
        // Ghi dữ liệu.
    } catch (DataIntegrityViolationException exception) {
        log.error("Import failed", exception);
        // Trả về bình thường.
    }
}
~~~

Nếu exception bị bắt và không ném lại, proxy có thể thấy method kết thúc bình thường và cố commit. Một số lỗi database/provider đã đánh dấu transaction rollback-only; khi đó commit có thể ném UnexpectedRollbackException.

Nếu chunk phải thất bại toàn bộ, hãy ném lại exception phù hợp:

~~~java
catch (DataIntegrityViolationException exception) {
    throw new ImportChunkException("Chunk is invalid", exception);
}
~~~

Nếu muốn bỏ qua một dòng lỗi và tiếp tục, cần thiết kế ranh giới xử lý lỗi cho từng dòng hoặc nhóm dòng một cách tường minh. Không dùng try/catch chung để che lỗi rồi vẫn đánh dấu checkpoint thành công.

## 18. Xử lý dòng lỗi mà vẫn giữ các dòng hợp lệ

Nếu nghiệp vụ cho phép import một phần, có thể validate dữ liệu trước khi ghi:

1. Parse và validate định dạng.
2. Phân loại dòng hợp lệ/không hợp lệ.
3. Ghi các dòng hợp lệ theo chunk.
4. Ghi lỗi dòng vào bảng quarantine hoặc file kết quả.
5. Cập nhật checkpoint và thống kê trong cùng transaction thích hợp.

Ví dụ:

~~~java
List<ImportRow> validRows = new ArrayList<>();
List<RowError> invalidRows = new ArrayList<>();

for (ImportRow row : inputRows) {
    ValidationResult result = validator.validate(row);

    if (result.isValid()) {
        validRows.add(row);
    } else {
        invalidRows.add(new RowError(
                row.sourceSequence(),
                result.message()
        ));
    }
}

worker.persistChunk(jobId, validRows, invalidRows);
~~~

Worker có thể ghi dữ liệu hợp lệ, lỗi và checkpoint cùng một transaction nếu chính sách yêu cầu một chunk được ghi nhận hoàn chỉnh. Nếu lỗi được ghi ở transaction riêng, cần xác định rõ checkpoint phản ánh trạng thái nào.

Với constraint chỉ phát hiện ở database, validation trước không thay thế constraint. Unique/FK có thể thay đổi đồng thời; worker vẫn phải xử lý lỗi khi flush/commit.

## 19. Bulk DML có thể phù hợp hơn Entity batching

Nếu chỉ cần cập nhật cùng một giá trị cho nhiều dòng, JPQL bulk update có thể hiệu quả hơn load từng Entity rồi sửa:

~~~java
@Modifying
@Query("""
    update Customer c
       set c.active = false
     where c.lastLoginAt < :cutoff
    """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

Bulk DML chạy trực tiếp trên database, không cần hydrate từng Entity. Nhưng nó bỏ qua lifecycle callback của từng Entity, dirty checking và cascade theo cách thao tác Entity thông thường. Persistence context có thể giữ trạng thái cũ sau bulk update.

Có thể dùng:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
~~~

để yêu cầu flush trước và clear persistence context sau bulk operation theo cấu hình Spring Data. Cần hiểu tác động đến các Entity managed đang có thay đổi.

Chọn Entity batching khi cần lifecycle callback, auditing, validation/domain behavior hoặc cascade. Chọn bulk DML khi thao tác set-based đơn giản, có thể biểu diễn trực tiếp và đã xử lý rõ version, auditing và persistence-context synchronization.

## 20. Đọc dữ liệu lớn mà không giữ toàn bộ trong heap

Không chỉ ghi, đọc toàn bộ file hoặc toàn bộ Entity vào List trước khi xử lý cũng gây áp lực bộ nhớ.

Các lựa chọn:
- Đọc file theo từng dòng và gom thành chunk DTO.
- Dùng Pageable để đọc từng trang.
- Dùng keyset/scrolling khi offset sâu gây tốn kém.
- Dùng JDBC cursor/fetch size khi provider và driver hỗ trợ.
- Dùng projection để chỉ đọc các cột cần thiết.

Ví dụ đọc từng trang:

~~~java
int pageNumber = 0;
Page<SourceRecord> page;

do {
    page = sourceRepository.findAll(
            PageRequest.of(pageNumber, 500, Sort.by("id").ascending())
    );

    process(page.getContent());
    pageNumber++;
} while (page.hasNext());
~~~

Offset pagination có thể chậm ở trang sâu và nhạy với insert/delete trong lúc đọc. Với tập dữ liệu lớn, sort ổn định và keyset cursor thường phù hợp hơn.

Repository trả Stream<T> không tự bảo đảm driver/database fetch từng dòng. Stream có thể giữ ResultSet, Statement và connection mở; cần transaction phù hợp và đóng bằng try-with-resources. Kiểm tra fetch size và behavior của driver thực tế.

## 21. Tránh N+1 và giữ dữ liệu đầu vào gọn

Trong import, nếu mỗi dòng cần tra cứu một Entity tham chiếu, gọi Repository cho từng dòng có thể tạo N+1 query.

Ví dụ kém hiệu quả:

~~~java
for (ImportRow row : rows) {
    Category category = categoryRepository.findByCode(row.categoryCode())
            .orElseThrow();
    entityManager.persist(toEntity(row, category));
}
~~~

Có thể gom mã category của chunk, đọc một lần rồi tạo map:

~~~java
Set<String> codes = rows.stream()
        .map(ImportRow::categoryCode)
        .collect(Collectors.toSet());

Map<String, Category> categories =
        categoryRepository.findByCodeIn(codes).stream()
                .collect(Collectors.toMap(
                        Category::getCode,
                        Function.identity()
                ));
~~~

Sau đó map từng dòng với Category tương ứng. Nếu danh mục rất lớn, cache/reference map có thể cần giới hạn kích thước và freshness policy.

Không giữ map chứa toàn bộ bảng tham chiếu trong heap nếu dữ liệu quá lớn. Chỉ tải những khóa cần cho chunk hiện tại hoặc dùng một cache có giới hạn.

## 22. Theo dõi tiến độ và hiệu năng

Một batch job nên ghi nhận các chỉ số đủ để vận hành và phục hồi:

| Chỉ số | Mục đích |
|---|---|
| Rows read | Số dòng đã đọc từ nguồn |
| Rows valid/invalid | Số dòng qua hoặc không qua validation |
| Rows persisted | Số dòng đã ghi thành công |
| Chunks committed | Số transaction chunk đã commit |
| Chunk duration | Thời gian xử lý từng chunk |
| Flush duration | Chi phí đồng bộ persistence context |
| Retry count | Số lần retry và nguyên nhân |
| Failed row/chunk | Vị trí và lỗi để phục hồi |
| JDBC batch metrics | Batch có thực sự được sử dụng không |
| Heap/GC | Phát hiện giữ quá nhiều object |
| DB latency/lock wait | Phát hiện nghẽn database |
| Connection pool usage | Phát hiện transaction giữ connection lâu |

Log job ID, chunk number, source sequence range và error code để truy vết. Tránh log toàn bộ dòng dữ liệu có thông tin cá nhân hoặc bí mật.

Tăng chunk size có thể giảm overhead transaction nhưng làm tăng memory, lock duration và phạm vi rollback. Tăng JDBC batch size có thể giảm round trip nhưng không tự giải quyết persistence context quá lớn. Điều chỉnh từng tham số dựa trên metric.

## 23. Kiểm thử batch và phục hồi lỗi

Integration test cần chứng minh cả việc ghi thành công, rollback trong chunk và commit độc lập giữa các chunk.

Các trường hợp nên có:
1. Chunk hợp lệ: toàn bộ dòng được lưu.
2. Lỗi ở giữa chunk: tất cả thay đổi database của chunk rollback.
3. Chunk trước đã commit: lỗi ở chunk sau không làm mất chunk trước nếu thiết kế commit độc lập.
4. Checkpoint chỉ tiến lên khi dữ liệu chunk commit.
5. Khởi động lại từ checkpoint không bỏ sót dữ liệu.
6. Chạy lại cùng input không tạo duplicate ngoài ý muốn.
7. Unique/FK/NOT NULL violation được phân loại đúng.
8. Retry transient failure chạy trên transaction mới.
9. Flush/clear không làm mất dữ liệu cần lưu.
10. Persistence context không tăng vô hạn trong batch dài.
11. JDBC batching thực sự hoạt động trên database/driver mục tiêu.
12. Bulk DML không để Entity managed giữ trạng thái cũ.

Ví dụ kiểm thử rollback khi flush:

~~~java
@SpringBootTest
class ImportBatchIntegrationTest {

    @Autowired
    private ImportBatchWorker worker;

    @Autowired
    private ImportedRecordRepository repository;

    @Test
    void failedChunkRollsBackAllItsRows() {
        List<ImportRow> rows = List.of(
                new ImportRow("source-1", "A"),
                new ImportRow("source-2", "B"),
                new ImportRow("source-3", "C")
        );

        assertThrows(
                ImportChunkException.class,
                () -> worker.persistChunkWithFailure(rows, 2)
        );

        assertEquals(0, repository.count());
    }
}
~~~

Đây là cấu trúc minh họa; persistChunkWithFailure là hook test hoặc một worker test fixture cố ý ném lỗi sau khi flush. Test method không nên tự có transaction bao ngoài nếu mục tiêu là quan sát transaction worker đã rollback độc lập. Nếu dùng @DataJpaTest vốn có transaction cho test, hãy hiểu rõ transaction test và dùng transaction mới/clear context khi kiểm tra trạng thái đã commit.

Test chunk commit độc lập:

~~~java
@Test
void firstChunkRemainsCommittedWhenSecondChunkFails() {
    coordinator.importChunksWithFailureAfterFirstChunk();

    assertEquals(100, repository.count());
}
~~~

Ví dụ này giả định coordinator gọi mỗi chunk qua worker proxy, chunk đầu commit, chunk thứ hai rollback và lỗi được coordinator xử lý. Hãy kiểm tra trạng thái bằng transaction/read context mới, không dựa vào Entity đang managed từ trước.

Dùng Testcontainers với database engine và phiên bản gần production để kiểm tra JDBC batching, identity/sequence, constraint, lock và SQL dialect. H2 không chứng minh mọi behavior giống MySQL, PostgreSQL, SQL Server hoặc Oracle.

## 24. Những lỗi thường gặp

**Nghĩ saveAll() tự tạo một bulk INSERT**

saveAll thường lặp qua save; JDBC batching phụ thuộc Hibernate, driver, ID strategy và cấu hình.

**Chỉ flush mà không clear trong batch dài**

SQL được gửi xuống database nhưng persistence context vẫn giữ Entity managed. Bộ nhớ có thể tiếp tục tăng.

**Clear trước flush**

Các thay đổi chưa đồng bộ có thể bị mất khỏi persistence context. Flush trước rồi mới clear.

**Nhầm flush với commit**

Flush không kết thúc transaction. Các thay đổi đã flush vẫn rollback được.

**Đặt @Transactional ở coordinator khiến chunk không commit độc lập**

Worker dùng REQUIRED sẽ tham gia transaction ngoài. Dùng coordinator không transaction hoặc REQUIRES_NEW có chủ đích.

**Gọi worker bằng self-invocation**

Lời gọi nội bộ không qua proxy thông thường, nên transaction boundary có thể không được áp dụng.

**Retry trong transaction đã rollback-only**

Retry phải mở transaction mới. Đặt retry bên ngoài lời gọi transactional qua proxy.

**Cập nhật checkpoint trước dữ liệu**

Crash có thể khiến job bỏ qua các dòng chưa commit. Ghi checkpoint cùng transaction với chunk data.

**Không idempotent khi chạy lại**

Job restart/retry có thể tạo duplicate. Dùng source key, unique constraint và chính sách upsert/duplicate rõ ràng.

**Dùng IDENTITY rồi kỳ vọng JDBC insert batching**

Hibernate thường không batch INSERT cho Entity dùng IDENTITY. Xem xét sequence hoặc chiến lược ID phù hợp.

**Một chunk quá lớn**

Transaction kéo dài, rollback tốn kém và giữ nhiều tài nguyên. Đo và giảm chunk khi cần.

**Một chunk quá nhỏ**

Transaction overhead và checkpoint overhead tăng. Benchmark thay vì chọn tùy ý.

**Bắt exception rồi tiếp tục mà không ghi trạng thái lỗi**

Job có thể đánh dấu tiến độ sai hoặc bỏ sót dữ liệu. Phân loại lỗi và ghi nhận failure sau rollback.

**Bulk update nhưng không clear persistence context**

Entity managed có thể chứa dữ liệu cũ. Flush/clear/refresh theo đúng phạm vi.

## 25. Quy trình triển khai nhập dữ liệu lớn

Khi xây dựng batch import với Spring Data JPA:

1. Xác định dữ liệu đầu vào, khóa nguồn và yêu cầu idempotency.
2. Chọn transaction chunk size theo thời gian xử lý, lock và phạm vi rollback chấp nhận được.
3. Chọn flush/clear interval để giới hạn persistence context.
4. Cấu hình JDBC batch size và kiểm tra ID generation strategy.
5. Đưa transaction vào worker bean được gọi qua proxy.
6. Giữ coordinator không transaction nếu mỗi worker call phải commit độc lập; dùng REQUIRES_NEW khi cần tách khỏi transaction caller.
7. Flush định kỳ rồi clear để giới hạn bộ nhớ.
8. Ghi checkpoint cùng transaction với dữ liệu chunk.
9. Xác định chính sách fail-fast, retry, quarantine hoặc split chunk.
10. Retry transient error trong transaction mới với backoff và giới hạn số lần.
11. Bảo đảm thao tác import idempotent để hỗ trợ restart.
12. Tránh gọi HTTP/message broker trực tiếp trong transaction dài; dùng outbox cho side effect cần bền vững.
13. Đo heap, GC, JDBC batching, DB latency, lock wait và thời gian chunk.
14. Integration test rollback, commit độc lập, checkpoint, duplicate và restart trên database mục tiêu.

## 26. Kết luận

Nhập dữ liệu lớn với Spring Data JPA cần kiểm soát riêng JDBC batch size, flush/clear interval và transaction chunk size. JDBC batching giảm round trip khi driver/provider hỗ trợ; flush đồng bộ SQL nhưng không commit; clear giải phóng các Entity khỏi persistence context. Muốn mỗi chunk commit độc lập, đặt transaction ở worker được gọi qua proxy và bảo đảm không có transaction ngoài REQUIRED bao trùm toàn bộ job, hoặc dùng REQUIRES_NEW khi thực sự cần.

Để phục hồi an toàn, ghi checkpoint cùng transaction với dữ liệu chunk, thiết kế import idempotent, phân biệt lỗi transient với lỗi dữ liệu và retry trên transaction mới. Kiểm thử cả rollback trong chunk, commit của chunk trước, restart từ checkpoint, batching thực tế và tính đúng của dữ liệu trên database production-like. Không coi saveAll là bulk INSERT, không nhầm flush với commit và không tăng chunk size khi chưa đo tác động lên heap, lock, connection và thời gian phục hồi.

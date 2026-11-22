# Nuốt ngoại lệ giao dịch rồi tiếp tục dùng Session đã lỗi

Một lỗi thường gặp trong ứng dụng Hibernate là bắt ngoại lệ khi ghi dữ liệu, ghi log rồi tiếp tục dùng cùng Session hoặc EntityManager như thể thao tác vừa rồi chưa xảy ra. Ví dụ, một lần flush bị lỗi do vi phạm unique constraint; code catch PersistenceException, bỏ qua bản ghi lỗi và tiếp tục persist bản ghi kế tiếp trong cùng transaction. Kết quả có thể là transaction đã bị đánh dấu rollback-only, JDBC transaction đã ở trạng thái lỗi, persistence context không còn nhất quán với database, hoặc lỗi ban đầu bị che bởi một exception khác ở cuối request.

**Sau một exception phát sinh từ Hibernate Session trong lúc thao tác persistence, hãy rollback transaction và loại bỏ Session đó.** Không tiếp tục dùng Session đã ném lỗi để chạy query, persist, merge, flush hoặc commit. Nếu nghiệp vụ cần tiếp tục xử lý công việc khác, hãy bắt đầu một transaction và persistence context mới theo ranh giới rõ ràng.

Bài học này giải thích:

- Vì sao Session có thể không còn an toàn sau persistence exception.
- Phân biệt lỗi nghiệp vụ trước khi chạm persistence với lỗi Hibernate/JDBC trong transaction.
- Vì sao flush có thể ném lỗi dù code trước đó trông bình thường.
- Transaction bị rollback-only và trạng thái lỗi ở database.
- Cách xử lý đúng trong Hibernate thuần và Spring @Transactional.
- Cách retry bằng transaction/session mới và xử lý batch từng phần tử.
- Những anti-pattern như catch rồi tiếp tục, commit sau khi flush fail, hoặc tự clear Session để chữa lỗi.
- Cách kiểm thử rollback, exception propagation và transaction boundaries.

## 1. Session là một đơn vị làm việc, không phải một connection wrapper đơn giản

Hibernate Session quản lý persistence context: identity map, trạng thái managed/detached/removed, snapshots phục vụ dirty checking, collection state, action queue và tương tác với JDBC.

Một transaction thường có chuỗi hoạt động:

```text
Begin transaction
       |
       v
Load / persist / merge / remove entities
       |
       v
Modify managed state
       |
       v
Flush pending actions
       |
       v
Database executes SQL
       |
       v
Commit transaction
       |
       v
Session/context ends
```

Trong suốt quá trình này, Hibernate phải giữ cho state trong persistence context và state database có thể được đồng bộ theo semantics của transaction.

Nếu một thao tác persistence ném exception, một phần SQL có thể đã được gửi xuống database, một số action có thể đã thực thi, một số action khác chưa thực thi, transaction có thể đã bị database đánh dấu lỗi và internal state của Session có thể không còn đáng tin để tiếp tục.

Vì vậy, khi Session ném exception, cần rollback transaction và đóng/discard Session. Không nên cố gắng phục hồi Session bằng cách tiếp tục dùng nó.

## 2. Vì sao một exception có thể làm Session không còn sử dụng được?

Ví dụ:

```java
Session session = sessionFactory.openSession();
Transaction tx = session.beginTransaction();

try {
    Product product = new Product("SKU-100");
    session.persist(product);

    // Có thể phát sinh constraint violation tại đây.
    session.flush();

    tx.commit();
} catch (RuntimeException ex) {
    // Không tiếp tục dùng session sau khi persistence operation lỗi.
}
```

Có nhiều lớp trạng thái liên quan:

1. **Persistence context:** Hibernate đã thay đổi trạng thái entity và ghi nhận actions trong unit of work.
2. **Action queue:** một số SQL actions có thể đã được thực thi, một số chưa.
3. **JDBC connection:** driver/database có thể đã báo lỗi hoặc transaction đang ở trạng thái failed.
4. **Database transaction:** DBMS có thể yêu cầu rollback trước khi chạy statement tiếp theo.
5. **Transaction coordinator:** Hibernate/Spring có thể đã đánh dấu transaction rollback-only.
6. **Application state:** object Java vẫn tồn tại và có thể trông như đã được lưu dù database chưa commit.

Một exception không đảm bảo mọi thao tác trước đó đã được hoàn tác ngay tại thời điểm catch. Rollback mới là thao tác kết thúc transaction theo cách phù hợp. Sau rollback, không dùng lại Session đã gặp lỗi để tiếp tục unit of work.

## 3. Phân biệt lỗi nghiệp vụ và lỗi persistence

Không phải mọi exception trong service đều làm Session bị hỏng.

Ví dụ lỗi kiểm tra dữ liệu trước khi truy cập database:

```java
if (request.quantity() <= 0) {
    throw new InvalidQuantityException();
}
```

Nếu exception này xảy ra trước khi Hibernate thực hiện thao tác persistence, Session chưa chắc đã gặp lỗi. Đây là lỗi nghiệp vụ có thể được xử lý theo contract của service.

Ngược lại:

```java
entityManager.persist(order);
entityManager.flush(); // Constraint violation
```

Exception từ Hibernate/JDBC trong quá trình flush là một dấu hiệu khác. Transaction có thể đã thất bại và persistence context không còn an toàn.

| Tình huống | Có thể tiếp tục cùng Session? | Hướng xử lý |
|---|---|---|
| Validate input trước persistence | Có thể, nếu không có persistence failure | Trả validation error hoặc xử lý business flow |
| Domain exception do business rule | Tùy transaction policy và trạng thái persistence | Xác định rõ rollback semantics |
| Hibernate/JDBC exception khi persist/flush | Không | Rollback và discard Session |
| Constraint violation lúc commit/flush | Không | Rollback; transaction mới nếu cần |
| Optimistic lock failure | Không tiếp tục unit of work cũ | Rollback, reload trong transaction mới |
| Connection failure/database unavailable | Không | Rollback/close; retry theo policy ở transaction mới |
| Exception trong code Java sau khi DB đã flush nhưng trước commit | Transaction vẫn cần xử lý theo lỗi | Rollback nếu operation thất bại |

Điểm quan trọng là xác định exception đến từ đâu và Session/transaction đã đi qua thao tác persistence nào. Nếu không chắc một persistence exception đã xảy ra, chọn đường an toàn: rollback và kết thúc unit of work hiện tại.

## 4. Constraint violation thường chỉ xuất hiện lúc flush

Developer có thể viết:

```java
Product first = new Product("SKU-100");
Product second = new Product("SKU-100");

entityManager.persist(first);
entityManager.persist(second);
```

Cả hai lời gọi persist có thể chỉ cập nhật persistence context/action queue. Vi phạm unique constraint có thể chỉ xuất hiện khi Hibernate gửi INSERT xuống database.

Những điểm flush phổ biến:

- Gọi entityManager.flush() hoặc session.flush().
- Commit transaction, vì Hibernate thường flush trước commit.
- Một query cần auto-flush pending changes để bảo đảm query thấy state nhất quán.
- Một số operations hoặc ID generation strategies cần SQL sớm hơn.
- Transaction manager/provider thực hiện synchronization trước commit.

Vì vậy, code có thể catch exception ở một dòng khác với nơi nguyên nhân được tạo ra. Ví dụ, lỗi do entity persist trước đó có thể xuất hiện khi chạy một JPQL query kích hoạt auto-flush.

## 5. Auto-flush khiến exception xuất hiện ở một query tưởng như chỉ đọc

Ví dụ:

```java
entityManager.persist(new Product("SKU-100"));
entityManager.persist(new Product("SKU-100"));

// Developer nghĩ đây chỉ là SELECT.
long count = entityManager.createQuery(
    "select count(p) from Product p",
    Long.class
).getSingleResult();
```

Với flush mode phù hợp, Hibernate có thể flush pending changes trước query. Unique constraint violation do INSERT có thể được ném tại getSingleResult().

Không kết luận query SELECT là nguyên nhân chỉ vì stack trace chỉ vào dòng query. Hãy xem SQL log và pending changes trước đó.

Sau khi exception này xảy ra, không catch rồi chạy query khác trong cùng Session để “xem database đang có gì”. Rollback và mở persistence context mới để kiểm tra.

## 6. Database transaction có thể ở trạng thái failed

Một số DBMS, điển hình PostgreSQL, sau một statement error trong transaction, transaction chuyển sang trạng thái aborted. Những statement tiếp theo trong cùng transaction sẽ bị từ chối cho tới khi rollback hoặc rollback về savepoint hợp lệ.

Ví dụ minh họa:

```sql
begin;

insert into products(sku) values ('SKU-100');

-- Lần INSERT tiếp theo vi phạm unique constraint.
insert into products(sku) values ('SKU-100');

-- Transaction đang failed.
select * from products;

rollback;
```

Statement SELECT sau lỗi có thể nhận thông báo transaction đang aborted. Không thể chữa bằng cách tạo một query mới trên cùng connection mà bỏ qua rollback.

Các DBMS khác có semantics transaction/statement failure khác nhau. Nhưng điều đó không thay đổi nguyên tắc phía Hibernate: sau persistence exception, rollback và discard Session. Không suy ra Session an toàn chỉ vì một DBMS cho phép statement tiếp theo chạy trong một số trường hợp.

## 7. Transaction rollback-only là gì?

Một transaction có thể bị đánh dấu **rollback-only**. Điều này có nghĩa transaction không còn được phép commit thành công, dù application code vẫn chạy tiếp.

Ví dụ:

```java
try {
    repository.save(product);
    entityManager.flush();
} catch (PersistenceException ex) {
    log.warn("Could not save product", ex);
}

// Code vẫn chạy tới đây, nhưng transaction có thể đã rollback-only.
doMoreWork();
```

Khi transaction manager thực hiện commit, nó có thể rollback và báo UnexpectedRollbackException hoặc exception tương ứng.

Cần phân biệt:

- **Rollback-only flag:** trạng thái của transaction coordinator/transaction manager.
- **Session state:** persistence context và Session sau persistence exception.

Chỉ đánh dấu rollback-only không làm Session trở lại trạng thái có thể sử dụng. Nó bảo đảm transaction không commit; nó không phải công cụ sửa chữa persistence context.

## 8. Anti-pattern: catch rồi tiếp tục persist

Đây là ví dụ cần tránh:

```java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    for (ProductInput input : inputs) {
        try {
            Product product = map(input);
            entityManager.persist(product);
            entityManager.flush();
        } catch (PersistenceException ex) {
            log.warn("Skip invalid product {}", input.sku(), ex);
        }
    }
}
```

Vấn đề:

1. Flush của một phần tử có thể làm transaction lỗi.
2. Persistence context không còn đáng tin.
3. Transaction có thể đã rollback-only.
4. Database transaction có thể ở trạng thái aborted.
5. Vòng lặp tiếp tục dùng cùng EntityManager/Session.
6. Lỗi kế tiếp có thể chỉ là hậu quả của lỗi đầu tiên.
7. Cuối method có thể nhận thêm exception khi commit.
8. Log có thể ghi “skip” nhưng toàn bộ transaction cuối cùng rollback.

Catch exception không làm cho thao tác persistence thất bại trở thành một savepoint tự động. Nếu muốn bỏ qua một record lỗi và tiếp tục record khác, cần thiết kế transaction boundary riêng.

## 9. Anti-pattern: gọi clear() rồi tiếp tục sau persistence exception

Một cách sửa sai thường gặp:

```java
try {
    entityManager.flush();
} catch (PersistenceException ex) {
    entityManager.clear();
    // Tiếp tục persist entity khác.
}
```

clear() chỉ detach các managed entities khỏi persistence context. Nó không:

- Rollback database transaction.
- Gỡ rollback-only flag.
- Khôi phục JDBC connection khỏi trạng thái aborted.
- Đảo ngược SQL đã thực thi.
- Khôi phục các invariants nội bộ sau persistence failure.
- Biến Session đã ném exception thành một Session mới.

Sau persistence exception, không dùng clear() như cơ chế phục hồi. Hãy rollback transaction và đóng/discard Session; thao tác tiếp theo cần Session/transaction mới.

## 10. Anti-pattern: catch rồi commit

```java
try {
    session.flush();
} catch (RuntimeException ex) {
    log.error("Flush failed", ex);
}

tx.commit(); // Không được giả định commit sẽ thành công.
```

Nếu flush thất bại, transaction có thể rollback-only hoặc DB transaction đã aborted. Gọi commit có thể ném thêm exception hoặc kết thúc bằng rollback.

Không commit transaction sau khi persistence operation đã thất bại chỉ vì code đã catch exception. Rollback là hành động cần thực hiện.

## 11. Anti-pattern: bỏ qua exception ở repository rồi trả success

```java
public void createOrder(OrderRequest request) {
    try {
        orderRepository.save(map(request));
    } catch (DataIntegrityViolationException ex) {
        log.warn("Order was not saved", ex);
    }

    // Trả HTTP 200 dù transaction có thể đã thất bại.
}
```

Điều này tạo ra response không phản ánh trạng thái commit. Một transaction có thể đã rollback-only và sẽ thất bại khi interceptor commit sau khi method trả về.

Nếu lỗi có nghĩa request không được ghi nhận, hãy để exception thoát khỏi transaction boundary hoặc chuyển nó thành kết quả lỗi ở tầng bên ngoài transaction sau khi rollback đã hoàn tất.

Không biến persistence exception thành “thành công có cảnh báo” khi database chưa commit.

## 12. Session và transaction nên có vòng đời rõ ràng

```text
Một unit of work
   |
   +-- Một transaction
   |
   +-- Một Session / persistence context
   |
   +-- Thành công: flush + commit + close
   |
   +-- Persistence failure: rollback + close/discard
                                  |
                                  v
                       Transaction mới nếu cần
                       Session/persistence context mới
```

Session không phải object dùng chung cho nhiều threads hoặc tái sử dụng qua nhiều transaction tùy ý. Session có stateful lifecycle. Dùng Session mới cho một unit of work mới giúp cô lập state và giảm nguy cơ dùng lại persistence context đã lỗi.

Trong ứng dụng có container-managed EntityManager, transaction manager/framework quản lý lifecycle. Không tự đóng EntityManager được inject theo cơ chế shared proxy; hãy để transaction boundary kết thúc và tạo transaction/persistence context mới qua framework.

## 13. Xử lý đúng trong Hibernate thuần

Với Hibernate native API, pattern tổng quát là:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        session.persist(new Product("SKU-100"));
        session.flush();

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Điểm quan trọng:

- Catch ở ranh giới unit of work.
- Nếu transaction còn active, rollback.
- Rethrow để caller biết thao tác thất bại.
- Try-with-resources đóng Session.
- Không tiếp tục dùng Session sau catch.
- Nếu retry, retry bên ngoài block này để lần sau mở Session mới.

Có thể bổ sung logging hoặc chuyển exception sang domain/application exception ở tầng thích hợp, nhưng phải giữ nguyên transaction failure semantics.

### Không che mất exception gốc bằng rollback exception

Rollback/close cũng có thể ném lỗi. Trong code thực tế, cần giữ exception ban đầu làm nguyên nhân chính và ghi nhận lỗi cleanup như suppressed/secondary exception theo cơ chế của framework. Đừng để rollback exception thay thế hoàn toàn lỗi constraint/connection ban đầu trong logs.

## 14. Dùng try-with-resources cho Session

Session của Hibernate implements AutoCloseable trong các phiên bản hiện đại, vì vậy try-with-resources giúp bảo đảm close ngay cả khi exception xảy ra.

```java
try (Session session = sessionFactory.openSession()) {
    // Một unit of work.
}
```

Đóng Session không đồng nghĩa commit. Transaction cần được commit hoặc rollback rõ ràng theo contract.

Nếu code dùng getCurrentSession() với contextual session managed bởi framework, không tự áp dụng try-with-resources một cách máy móc; framework/container có thể quản lý lifecycle. Hãy theo đúng cách bootstrap/session context của ứng dụng.

## 15. Xử lý đúng trong Spring @Transactional

Với Spring:

```java
@Service
public class ProductService {

    @Transactional
    public void create(ProductInput input) {
        Product product = map(input);
        repository.save(product);

        // Có thể flush sớm để phát hiện constraint violation
        // trong method này.
        repository.flush();
    }
}
```

Nếu exception thoát khỏi method qua Spring transaction interceptor, transaction manager có thể rollback theo rollback rules.

Mặc định, Spring thường rollback với RuntimeException và Error; checked exceptions mặc định không nhất thiết kích hoạt rollback trừ khi có rollbackFor/cấu hình tương ứng. Cần xác nhận rule trong dự án.

Ví dụ:

```java
@Transactional(rollbackFor = Exception.class)
public void create(ProductInput input) throws Exception {
    // ...
}
```

Nhưng dù rollback rule thế nào, **không catch persistence exception rồi tiếp tục dùng cùng EntityManager trong method**.

## 16. Spring @Transactional: catch bên trong method khác với catch bên ngoài

Trường hợp A — exception thoát khỏi method transactional:

```java
@Transactional
public void create(ProductInput input) {
    repository.save(map(input));
    repository.flush(); // Ném exception ra ngoài.
}
```

Spring interceptor nhìn thấy exception và áp dụng rollback rules.

Trường hợp B — exception bị bắt trong cùng method:

```java
@Transactional
public void create(ProductInput input) {
    try {
        repository.save(map(input));
        repository.flush();
    } catch (DataIntegrityViolationException ex) {
        log.warn("Persistence failed", ex);
    }

    // Không nên tiếp tục dùng persistence context này.
}
```

Vì exception không thoát khỏi method, interceptor có thể không nhìn thấy exception để áp dụng default rollback rule. Tuy nhiên transaction có thể đã được đánh dấu rollback-only bởi Hibernate/JPA/transaction manager. Kết quả có thể là UnexpectedRollbackException ở lúc commit.

Đừng dựa vào việc catch exception để điều khiển transaction. Nếu lỗi persistence xảy ra, hãy kết thúc transaction thất bại và xử lý lỗi ở caller bên ngoài boundary đó.

## 17. Chuyển exception thành HTTP response ở ngoài transaction

Một cấu trúc rõ ràng:

```java
@Service
public class ProductService {

    @Transactional
    public void create(ProductInput input) {
        repository.save(map(input));
        repository.flush();
    }
}
```

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiError> handleConstraint(
            DataIntegrityViolationException ex) {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(new ApiError("PRODUCT_CONFLICT"));
    }
}
```

Transaction boundary nằm ở service. Khi persistence exception thoát khỏi service, interceptor rollback trước khi exception đến exception handler ở tầng web. Exception handler chỉ chuyển lỗi đã thất bại thành response phù hợp.

Nếu bắt exception trong service rồi trả object lỗi như kết quả bình thường, hãy đặc biệt cẩn thận: transaction interceptor có thể commit hoặc báo rollback-only sau khi method trả về. Phân tách application result và transaction outcome.

## 18. noRollbackFor không chữa được Session đã lỗi

Ví dụ:

```java
@Transactional(noRollbackFor = DataIntegrityViolationException.class)
public void create(ProductInput input) {
    repository.save(map(input));
    repository.flush();
}
```

Cấu hình này thay đổi rollback rule của Spring đối với exception được chỉ định. Nó không bảo đảm:

- Hibernate Session còn dùng được.
- JDBC transaction có thể tiếp tục.
- Database transaction chưa bị aborted.
- Persistence context có state nhất quán.
- Commit sẽ thành công.

Không dùng noRollbackFor để bỏ qua persistence exception và tiếp tục transaction. Nó chỉ phù hợp với exception mà application thực sự muốn commit despite exception và transaction resource vẫn ở trạng thái hợp lệ theo thiết kế. Persistence failure thường không thuộc nhóm đó.

## 19. Đánh dấu rollback-only khi cần xử lý exception tại chỗ

Có lúc application cần ghi nhận/log thông tin rồi trả kết quả điều khiển cho caller, nhưng transaction vẫn phải rollback.

Với Spring:

```java
@Transactional
public ImportResult importOne(ProductInput input) {
    try {
        repository.save(map(input));
        repository.flush();
        return ImportResult.success();
    } catch (DataIntegrityViolationException ex) {
        TransactionAspectSupport
            .currentTransactionStatus()
            .setRollbackOnly();

        return ImportResult.failure("CONSTRAINT_VIOLATION");
    }
}
```

Đây là cách đánh dấu transaction rollback-only, nhưng cần hiểu giới hạn:

- Method có thể trả ImportResult.failure.
- Transaction không được commit.
- Caller phải biết transaction đã thất bại/rollback.
- Không tiếp tục dùng EntityManager/Session bị persistence exception trong method.
- Nếu cần xử lý record tiếp theo, thực hiện ngoài transaction này với transaction/persistence context mới.

Một lựa chọn thường rõ hơn là để exception thoát khỏi transactional service rồi chuyển thành kết quả ở tầng orchestration không nằm trong transaction đó.

## 20. Retry phải dùng transaction và Session mới

Một lỗi transient có thể được retry, nhưng retry phải tạo unit of work mới.

Sai:

```java
@Transactional
public void saveWithRetry(Product product) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            entityManager.persist(product);
            entityManager.flush();
            return;
        } catch (PersistenceException ex) {
            // Sai: cùng EntityManager/session tiếp tục vòng lặp.
        }
    }
}
```

Đúng về mặt cấu trúc:

```java
public void saveWithRetry(ProductInput input) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            productWriter.saveInNewTransaction(input);
            return;
        } catch (TransientDataAccessException ex) {
            if (attempt == 3) {
                throw ex;
            }
            backoff(attempt);
        }
    }
}
```

```java
@Service
public class ProductWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInNewTransaction(ProductInput input) {
        repository.save(map(input));
        repository.flush();
    }
}
```

ProductWriter là bean riêng để lời gọi đi qua Spring proxy. REQUIRES_NEW tạo transaction riêng và thường dùng persistence context gắn với transaction mới theo cấu hình transaction manager.

Retry chỉ đúng khi exception có thể transient và thao tác idempotent hoặc có idempotency key. Unique constraint violation do dữ liệu trùng thường không tự hết khi retry; retry chỉ lặp lại cùng lỗi.

## 21. Lưu ý self-invocation trong Spring

Ví dụ dễ gây hiểu nhầm:

```java
@Service
public class ProductService {

    public void retry(ProductInput input) {
        saveInNewTransaction(input); // Gọi nội bộ
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInNewTransaction(ProductInput input) {
        // ...
    }
}
```

Trong proxy-based Spring transaction management, lời gọi method nội bộ trên cùng object thường không đi qua proxy. Vì vậy annotation REQUIRES_NEW có thể không được áp dụng như mong đợi.

Dùng một bean collaborator riêng hoặc TransactionTemplate để tạo boundary rõ ràng. Không cho rằng chỉ đặt annotation là đủ.

## 22. Dùng TransactionTemplate để tách từng transaction

Nếu muốn xử lý nhiều records và tiếp tục sau một record thất bại, TransactionTemplate giúp xác định boundary bằng code:

```java
@Service
public class ProductImporter {

    private final TransactionTemplate transactionTemplate;
    private final ProductRepository repository;

    public ProductImporter(
            TransactionTemplate transactionTemplate,
            ProductRepository repository) {
        this.transactionTemplate = transactionTemplate;
        this.repository = repository;
    }

    public List<ImportResult> importAll(
            List<ProductInput> inputs) {

        List<ImportResult> results = new ArrayList<>();

        for (ProductInput input : inputs) {
            try {
                transactionTemplate.executeWithoutResult(status -> {
                    Product product = map(input);
                    repository.save(product);
                    repository.flush();
                });

                results.add(ImportResult.success(input.sku()));
            } catch (DataIntegrityViolationException ex) {
                results.add(
                    ImportResult.failure(
                        input.sku(),
                        "CONSTRAINT_VIOLATION"
                    )
                );
            }
        }

        return results;
    }
}
```

Mỗi lần gọi executeWithoutResult tạo một transaction boundary. Khi callback ném exception, transaction template rollback transaction đó trước khi exception được catch ở vòng lặp bên ngoài. Lần lặp tiếp theo sử dụng transaction mới.

Cấu hình transaction manager/JPA integration phải bảo đảm mỗi callback nhận transaction-scoped persistence context phù hợp. Không tự giữ một Session/EntityManager mở từ ngoài rồi truyền nó vào tất cả callbacks.

## 23. Batch import: transaction theo file hay theo record?

Có hai mô hình khác nhau:

**Một transaction cho toàn file:**

- Tất cả records commit cùng nhau.
- Một record lỗi có thể rollback toàn bộ file.
- Phù hợp khi tính atomicity của file là requirement.
- Không thể đơn giản catch một persistence exception rồi tiếp tục trong cùng Session.

**Một transaction cho mỗi record/chunk:**

- Record hoặc chunk thành công có thể commit độc lập.
- Một record lỗi không nhất thiết rollback các record trước.
- Cần quản lý partial success, ordering và idempotency.
- Mỗi unit of work cần transaction/persistence context riêng.

| Tiêu chí | Toàn file | Theo record/chunk |
|---|---|---|
| Atomicity | Toàn bộ file | Từng record/chunk |
| Rollback khi một row lỗi | Có thể rollback cả file | Chỉ rollback unit lỗi |
| Số transaction | Ít | Nhiều hơn |
| Memory persistence context | Có thể tăng lớn | Có thể giới hạn |
| Tiếp tục sau lỗi | Thường không trong transaction đã lỗi | Có, từ transaction mới |
| Phù hợp | Import all-or-nothing | Partial acceptance/reconciliation |

Chọn theo business contract trước khi chọn cách tối ưu throughput.

## 24. Batch processing với chunk boundaries

Nếu transaction cho từng row quá tốn overhead, có thể chia thành chunks:

```text
Input file: 100,000 rows
      |
      +--> Chunk 1: rows 1..500
      |       transaction + Session A
      |       commit or rollback whole chunk
      |
      +--> Chunk 2: rows 501..1000
      |       transaction + Session B
      |       commit or rollback whole chunk
      |
      +--> ...
```

Trong mỗi chunk, nếu một persistence exception xảy ra, rollback/discard Session của chunk đó. Nếu policy cho phép tiếp tục, cần xác định lại chunk:

- Retry cả chunk với Session mới.
- Chia nhỏ chunk để cô lập row lỗi.
- Chuyển row lỗi vào error report/quarantine.
- Xử lý các rows còn lại trong transactions mới.

Không tiếp tục vòng lặp trong Session vừa ném persistence exception.

## 25. Retry không phải giải pháp cho mọi exception

Phân loại lỗi trước khi retry:

| Loại lỗi | Retry tự động? | Lý do |
|---|---|---|
| Deadlock victim | Có thể | DBMS có thể rollback một transaction cạnh tranh |
| Serialization failure | Có thể | Thử lại toàn bộ transaction với snapshot mới |
| Temporary connection failure | Có thể theo policy | Cần connection mới và backoff |
| Lock timeout | Có thể có điều kiện | Phải kiểm soát tải và giới hạn retries |
| Unique constraint violation | Thường không | Input/business conflict không tự biến mất |
| NOT NULL/FK violation | Thường không | Dữ liệu hoặc thứ tự thao tác sai |
| Optimistic lock conflict | Có thể theo nghiệp vụ | Cần reload và giải quyết xung đột |
| Mapping/SQL syntax error | Không | Lỗi cấu hình/code |
| Unsupported operation | Không | Cần sửa implementation |

Retry nên áp dụng cho transient failures theo SQLState/vendor code hoặc exception translation đáng tin cậy. Không retry mọi PersistenceException.

## 26. Retry toàn bộ transaction, không chỉ câu SQL cuối

Serialization failure/deadlock thường có nghĩa transaction logic cần chạy lại với state mới.

```text
Attempt 1:
  New transaction + Session
  Read current state
  Apply business operation
  Flush/commit -> transient failure
  Rollback + discard Session

Attempt 2:
  New transaction + Session
  Read current state again
  Re-evaluate business operation
  Flush/commit
```

Không tái sử dụng entity instance detached từ attempt thất bại như thể nó là state mới nhất. Load lại dữ liệu cần thiết trong transaction mới, đánh giá lại business invariants và thực thi operation từ đầu.

## 27. Optimistic locking exception cũng kết thúc unit of work

Ví dụ entity có version:

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private long version;

    private int available;
}
```

Hai transactions cùng load version 5. Transaction A commit version 6; transaction B cố update version 5 và nhận optimistic lock failure.

Không catch rồi tiếp tục sửa object managed của transaction B. Transaction B cần rollback. Nếu nghiệp vụ cho phép retry:

1. Kết thúc transaction thất bại.
2. Mở transaction/session mới.
3. Load InventoryItem mới nhất.
4. Tính lại quantity và business rule.
5. Thử update lại.
6. Giới hạn số lần retry.

Không tự tăng version trong object để bỏ qua conflict.

## 28. Không giữ entity managed qua transaction thất bại

Một entity object vẫn là Java object sau rollback, nhưng trạng thái trong memory có thể không phản ánh database.

Ví dụ:

```java
Product product = new Product("SKU-100");
session.persist(product);
session.flush(); // Lỗi
// product vẫn tồn tại trong heap.
```

Sau rollback, không suy ra object này đã được lưu hoặc có thể tiếp tục dùng với Session khác mà không kiểm tra. Generated ID có thể đã được cấp; field values/snapshots có thể không còn phản ánh database.

Nếu cần retry, tạo entity mới từ input/domain command hoặc reload state từ database trong Session mới. Không dựa vào việc rollback tự khôi phục mọi field của object Java.

## 29. Exception khi commit có thể xảy ra sau khi method hoàn tất

Với declarative transaction, code trong method có thể kết thúc bình thường nhưng transaction interceptor thực hiện flush/commit sau khi method return.

Ví dụ:

```java
@Transactional
public void create(ProductInput input) {
    repository.save(map(input));
    // Không gọi flush ở đây.
}
```

Constraint violation có thể chỉ xuất hiện khi Spring commit transaction sau khi method return. Do đó caller có thể nhận exception dù dòng save() không ném lỗi.

Nếu cần phát hiện constraint failure ngay trong service method, có thể flush rõ ràng. Nhưng flush sớm không loại bỏ nhu cầu rollback khi lỗi xảy ra.

Không catch exception chỉ quanh repository.save() rồi giả định đã bao hết persistence errors.

## 30. Vì sao save() trả entity không chứng minh đã commit?

Spring Data JPA save() thường gọi persist hoặc merge theo trạng thái entity. Nó không nhất thiết flush và commit ngay tại thời điểm method return.

```text
repository.save(entity)
       |
       v
Entity becomes managed / merge state copied
       |
       v
Method returns
       |
       v
Transaction interceptor flushes
       |
       v
Database constraint check
       |
       v
Commit or rollback
```

Một response success được tạo trước khi transaction thực sự commit có thể không phản ánh kết quả cuối. Nếu API cần trả về sau khi commit, đặt transaction boundary đúng và để exception commit propagate tới caller/handler.

## 31. Checked exception và rollback rules

Spring mặc định thường rollback với RuntimeException và Error, nhưng checked exception không mặc định rollback trong mọi cấu hình.

Ví dụ:

```java
@Transactional
public void importOne(ProductInput input)
        throws IOException {
    repository.save(map(input));
    throw new IOException("file read failed");
}
```

Tùy rollback rules, transaction có thể commit dù checked exception thoát ra. Có thể cấu hình:

```java
@Transactional(rollbackFor = IOException.class)
public void importOne(ProductInput input)
        throws IOException {
    // ...
}
```

Rollback rules chỉ quyết định transaction outcome khi interceptor xử lý. Chúng không làm cho Session phục hồi sau Hibernate/JDBC exception.

Với persistence exception đã xảy ra, rollback và discard Session bất kể code có bắt nó hay không.

## 32. UnexpectedRollbackException thường là triệu chứng, không phải nguyên nhân gốc

Một flow:

```text
Outer @Transactional method
       |
       v
Inner repository operation
       |
       v
Persistence exception
       |
       v
Exception caught/swallowed
       |
       v
Transaction marked rollback-only
       |
       v
Outer method returns normally
       |
       v
Spring attempts commit
       |
       v
UnexpectedRollbackException
```

Khi thấy UnexpectedRollbackException, tìm exception đầu tiên trong transaction, không chỉ nhìn exception cuối. Nó có thể đã bị catch/log ở một tầng sâu hơn.

Cách điều tra:

- Tìm stack trace đầu tiên của Hibernate/JDBC.
- Xác định SQL và bind parameters.
- Kiểm tra constraint/database state.
- Xem transaction marked rollback-only ở đâu.
- Xác định exception có bị catch không.
- Kiểm tra nested @Transactional propagation.
- Kiểm tra commit/flush boundary.

Không sửa bằng cách tắt rollback-only hoặc dùng noRollbackFor khi root cause là persistence failure.

## 33. Nested transaction không tự tạo Session mới

Spring propagation có các semantics khác nhau:

| Propagation | Hành vi khái quát |
|---|---|
| REQUIRED | Tham gia transaction hiện tại hoặc tạo mới |
| REQUIRES_NEW | Suspend transaction hiện tại và tạo transaction mới |
| NESTED | Dùng savepoint nếu transaction manager/resource hỗ trợ |
| SUPPORTS | Tham gia nếu có, nếu không thì chạy không transaction |
| NOT_SUPPORTED | Suspend transaction hiện tại |
| NEVER | Yêu cầu không có transaction |
| MANDATORY | Yêu cầu transaction đã tồn tại |

REQUIRED không tạo unit of work mới nếu đã có transaction. Một method con được annotate @Transactional mặc định có thể dùng chung transaction và persistence context với caller.

NESTED thường dựa trên savepoint và không đồng nghĩa một Hibernate Session mới. JPA persistence context vẫn có thể chứa state không phù hợp sau exception. Không dùng nested/savepoint như cơ chế phục hồi Session đã ném persistence exception.

Nếu cần tiếp tục độc lập, dùng transaction/persistence context mới theo thiết kế rõ ràng và catch lỗi sau khi boundary thất bại đã kết thúc.

## 34. REQUIRES_NEW có giới hạn gì?

REQUIRES_NEW có thể tạo transaction mới trong khi suspend transaction hiện tại. Tuy nhiên:

- Phải đi qua Spring proxy hoặc TransactionTemplate đúng cách.
- Outer transaction vẫn tồn tại và có thể đang rollback-only.
- Outer persistence context không tự được sửa.
- Outer Session đã lỗi vẫn không được dùng tiếp.
- Connection pool cần đủ capacity cho transaction lồng nhau.
- Inner transaction commit có thể tồn tại dù outer transaction rollback.

Nếu một persistence exception đã xảy ra trong outer transaction, đừng bắt rồi gọi inner REQUIRES_NEW để tiếp tục dùng outer Session sau đó. Hãy kết thúc outer transaction và xử lý tiếp ở orchestration layer bên ngoài.

## 35. Savepoint có thay thế rollback và Session mới không?

Một số JDBC/database workflows hỗ trợ savepoints. Có thể rollback một phần transaction về savepoint trong SQL/JDBC thuần nếu driver/database và transaction manager hỗ trợ.

Nhưng savepoint không tự đồng bộ lại Hibernate persistence context/action queue. Hibernate Session có thể đã nắm state không tương ứng với database sau rollback-to-savepoint. JPA không cung cấp một cơ chế portable để phục hồi mọi internal state trong tình huống này.

Không dùng savepoint như lời giải mặc định cho “catch persistence exception rồi tiếp tục cùng Session”. Nếu cần partial success, thiết kế mỗi phần tử/chunk thành transaction/persistence context độc lập, hoặc dùng một cơ chế database/JDBC chuyên biệt không trộn với managed Session.

## 36. Open Session in View không cho phép tiếp tục Session sau lỗi

Open Session in View (OSIV) có thể giữ EntityManager/Session mở qua tầng web để hỗ trợ lazy loading khi render response. Điều đó không có nghĩa Session có thể được dùng tiếp sau persistence exception.

Nếu một service flush lỗi và exception bị bắt ở controller, OSIV filter có thể vẫn giữ Session mở cho phần còn lại của request. Nhưng Session đó không trở lại trạng thái khỏe mạnh chỉ vì nó chưa được close.

Sau persistence failure:

- Để transaction rollback.
- Không thực hiện thêm lazy loads/queries trên Session đó.
- Không render entity graph dựa vào persistence context đã lỗi.
- Chuyển response bằng DTO/error object độc lập.
- Kết thúc request/session lifecycle theo framework.

OSIV quản lý thời gian sống Session, không phải cơ chế phục hồi transaction.

## 37. Không thực hiện query chẩn đoán trên Session đã lỗi

Anti-pattern:

```java
try {
    entityManager.flush();
} catch (PersistenceException ex) {
    log.error("Save failed", ex);

    // Sai: query trên persistence context vừa lỗi.
    Long count = entityManager.createQuery(
        "select count(p) from Product p",
        Long.class
    ).getSingleResult();
}
```

Query có thể gặp transaction aborted, rollback-only, connection error, Session state error hoặc auto-flush lại pending actions.

Nếu cần điều tra database state, thực hiện sau khi rollback/transaction boundary kết thúc, bằng transaction/session mới hoặc công cụ đọc độc lập. Không dùng Session đã lỗi để xác minh hậu quả.

## 38. Logging cần giữ root cause và transaction context

Một log hữu ích nên ghi:

- Operation/business correlation ID.
- Entity type và identifier nếu đã có.
- Transaction boundary/attempt number.
- SQLState/vendor error code nếu có.
- Hibernate exception type.
- Root cause chain.
- Tenant/database context nếu phù hợp và không lộ dữ liệu.
- Có rollback thành công hay rollback gặp lỗi.
- Retry có xảy ra hay không.

Tránh log raw entity toString() nếu nó có thể dereference lazy associations hoặc chứa PII. Tránh log bind parameters nhạy cảm ở production.

Không chỉ ghi “skip record” khi transaction thực tế đã rollback cả batch.

## 39. Không gửi external side effects trước khi transaction commit

Một transaction có thể persist dữ liệu, sau đó phát message/email trước commit:

```java
@Transactional
public void createOrder(OrderRequest request) {
    PurchaseOrder order = map(request);
    repository.save(order);

    eventPublisher.publishEvent(
        new OrderCreated(order.getId())
    );

    repository.flush(); // Có thể lỗi sau khi event đã phát.
}
```

Nếu event được gửi ra ngoài trước khi DB commit, consumer có thể thấy event cho một Order chưa tồn tại hoặc transaction cuối cùng rollback.

Persistence exception càng làm rõ rủi ro này. Dùng:

- Transactional event listener ở phase after-commit nếu semantics phù hợp.
- Transactional outbox để lưu event trong cùng DB transaction rồi publish sau.
- Idempotent consumers.
- Retry/outbox status rõ ràng.

Không cho rằng rollback database tự thu hồi email, HTTP call hoặc message đã gửi.

## 40. Test chứng minh Session không được dùng lại sau persistence exception

Một integration test có thể cố tình gây constraint violation:

```java
@Test
void persistenceFailureEndsCurrentUnitOfWork() {
    Session session = sessionFactory.openSession();
    Transaction tx = session.beginTransaction();

    try {
        session.persist(new Product("DUPLICATE"));
        session.persist(new Product("DUPLICATE"));

        assertThrows(
            PersistenceException.class,
            session::flush
        );

        if (tx.isActive()) {
            tx.rollback();
        }
    } finally {
        session.close();
    }

    // Chỉ mở Session mới sau khi unit of work cũ đã kết thúc.
    try (Session fresh = sessionFactory.openSession()) {
        Transaction freshTx = fresh.beginTransaction();

        long count = fresh.createQuery(
            "select count(p) from Product p where p.sku = :sku",
            Long.class
        ).setParameter("sku", "DUPLICATE")
         .getSingleResult();

        freshTx.commit();
        assertEquals(0L, count);
    }
}
```

Exception cụ thể có thể được bọc bởi Hibernate/JPA/driver. Trong test thực tế, chọn exception assertion phù hợp DBMS/version và kiểm tra root cause SQLState.

Test này xác nhận transaction thất bại không commit dữ liệu và query kiểm tra chạy trong Session mới.

## 41. Test Spring rollback khi exception được propagate

Ví dụ integration test:

```java
@SpringBootTest
class ProductTransactionTest {

    @Autowired ProductService service;
    @Autowired ProductRepository repository;
    @Autowired JdbcTemplate jdbc;

    @Test
    void constraintFailureRollsBackTransaction() {
        assertThrows(
            DataIntegrityViolationException.class,
            () -> service.createDuplicateProduct()
        );

        Integer count = jdbc.queryForObject(
            "select count(*) from products where sku = ?",
            Integer.class,
            "DUPLICATE"
        );

        assertEquals(0, count);
    }
}
```

Đảm bảo test không bị bọc trong một transaction test ngoài cùng làm thay đổi semantics cần kiểm tra. Nếu DataJpaTest hoặc Transactional ở test class tự mở transaction, hãy thiết kế test transaction boundaries có chủ đích.

## 42. Test exception bị nuốt và rollback-only

Một test có thể chứng minh việc catch exception không bảo đảm commit:

```java
@Transactional
public void badImport() {
    try {
        repository.save(duplicateProduct());
        repository.flush();
    } catch (DataIntegrityViolationException ex) {
        // Cố tình nuốt để minh họa anti-pattern.
    }
}
```

Test gọi method qua Spring proxy và xác nhận commit boundary có thể báo UnexpectedRollbackException hoặc rollback tương ứng theo provider/transaction manager.

Không viết test mong muốn badImport() hoạt động thành công. Đây là test minh họa để ngăn regression của anti-pattern, hoặc tốt hơn là loại bỏ method sai khỏi production code.

## 43. Test batch: một record lỗi, record sau dùng transaction mới

Nếu policy là partial success:

```java
@Test
void importerContinuesAfterFailedRecordInNewTransaction() {
    List<ImportResult> results = importer.importAll(List.of(
        validInput("SKU-1"),
        duplicateInput("SKU-1"),
        validInput("SKU-2")
    ));

    assertEquals(3, results.size());
    assertTrue(results.get(0).success());
    assertFalse(results.get(1).success());
    assertTrue(results.get(2).success());

    assertTrue(productExists("SKU-1"));
    assertTrue(productExists("SKU-2"));
}
```

Điều kiện quan trọng: importer bắt exception **bên ngoài transaction callback đã rollback**, không catch bên trong transaction của từng record rồi tiếp tục dùng cùng persistence context.

Test này kiểm tra business partial-success contract chứ không chỉ test Hibernate API.

## 44. Test optimistic locking với hai transactions

Để kiểm tra concurrent failure:

1. Mở hai EntityManagers.
2. Transaction A và B cùng load một row/version.
3. A update và commit.
4. B update rồi flush/commit.
5. B nhận optimistic lock failure.
6. Rollback/close B.
7. Transaction mới đọc version và state cuối.
8. Nếu có retry, retry từ transaction mới và kiểm tra business rule được tính lại.

Dùng latches/barriers để đồng bộ hai threads; không dựa vào Thread.sleep() vì timing không ổn định.

Test phải chạy trên DBMS phù hợp với production isolation/locking.

## 45. Test database state bằng connection mới

Sau rollback, kiểm tra database bằng transaction/session mới:

- Parent row còn hay không.
- Child rows có còn không.
- Unique key đã được giải phóng chưa.
- Audit revisions của transaction thất bại có tồn tại không.
- Sequence/identity có gap không.
- Outbox/event rows có bị rollback cùng không.

Đừng assert ID sequence liên tiếp; DBMS có thể cấp sequence value dù transaction rollback.

Nếu kiểm tra qua JDBC, đảm bảo connection mới không tham gia transaction cũ hoặc đọc state chưa commit. Dùng transaction boundary riêng và isolation phù hợp.

## 46. Batch Hibernate và JDBC batching không làm exception an toàn hơn

Hibernate JDBC batching có thể gom nhiều INSERT/UPDATE vào batch. Khi flush batch lỗi, driver có thể báo lỗi cho một statement hoặc cả batch; một số update count có thể không rõ hoặc batch có thể chỉ thực thi một phần tùy driver/database.

Điều này làm cho việc cố tiếp tục Session sau batch exception càng nguy hiểm.

Cần:

- Rollback transaction khi batch persistence exception.
- Discard Session.
- Không suy ra mọi rows trong batch đã/không được ghi chỉ từ exception message.
- Dùng transaction mới cho retry.
- Thiết kế batch idempotent.
- Test với JDBC driver/database thật.

Bật hibernate.jdbc.batch_size là tối ưu throughput, không phải cơ chế partial rollback tự động cho từng entity.

## 47. Bulk DML và native SQL cũng cần transaction boundary rõ

Bulk JPQL/native SQL có thể không cập nhật persistence context đồng bộ như entity operations. Nếu bulk statement lỗi, transaction cũng có thể thất bại.

Sau bulk DML thành công, cần cân nhắc clear/refresh cache/persistence context theo semantics. Sau bulk DML thất bại, rollback và kết thúc transaction; không dùng cùng Session để chạy bulk statement tiếp theo.

Không nhầm vấn đề stale state sau bulk DML thành lý do để bỏ qua persistence exception.

## 48. Entity listener/callback không phải nơi để nuốt persistence failure

Nếu callback hoặc listener gọi repository/Session và bắt exception:

```java
@PreUpdate
void beforeUpdate() {
    try {
        // Persistence work lồng bên trong callback.
    } catch (RuntimeException ex) {
        // Nuốt exception.
    }
}
```

Điều này có thể tạo reentrant persistence operations, transaction state khó hiểu và exception bị che. Entity lifecycle callbacks nên giữ phạm vi nhỏ, tránh gọi thêm persistence operations không cần thiết và không nuốt exception từ database.

Nếu callback cần validation, ưu tiên domain validation trước persistence. Nếu cần side effect, dùng application service/outbox theo transaction lifecycle.

## 49. Transaction timeout và connection failure

Một transaction timeout hoặc connection failure có thể xảy ra khi:

- Query chạy quá lâu.
- Lock wait vượt timeout.
- Connection bị network reset.
- Database failover.
- Pool phát connection đã stale.
- Driver phát hiện socket timeout.

Sau lỗi kiểu này, không dùng lại Session/connection của unit of work cũ. Rollback/close theo khả năng framework, để pool loại connection hỏng theo driver/provider semantics, rồi chỉ retry với transaction mới nếu lỗi được phân loại transient.

Không retry vô hạn. Dùng exponential backoff có jitter, giới hạn attempts và bảo đảm operation idempotent.

## 50. Cẩn thận khi transaction rollback thất bại

Rollback cũng có thể lỗi vì connection đã mất hoặc database không còn reachable. Khi đó:

- Giữ exception persistence ban đầu.
- Ghi rollback failure như suppressed/secondary cause.
- Đóng/discard Session.
- Để connection pool xử lý connection invalid theo integration.
- Không tái sử dụng connection thủ công.
- Không giả định database đã rollback thành công nếu client mất kết nối đúng lúc commit/rollback.

Một network failure quanh commit có thể tạo **uncertain outcome**: client không biết transaction đã commit hay chưa. Không retry mù quáng một lệnh không idempotent. Cần idempotency key hoặc truy vấn reconciliation trong transaction mới để xác định kết quả.

## 51. Idempotency khi retry

Ví dụ API tạo payment/order:

- Request gửi đi.
- Database commit có thể thành công.
- Network đứt trước khi client nhận response.
- Client retry.
- Nếu không có idempotency key, hệ thống có thể tạo duplicate.

Dùng unique idempotency key được lưu bền vững trong cùng transaction với kết quả nghiệp vụ. Khi retry, transaction mới kiểm tra key và trả kết quả đã commit nếu tồn tại.

Đây là vấn đề khác với retry sau constraint violation, nhưng cùng một nguyên tắc: mỗi attempt dùng transaction mới và phải xử lý uncertain outcome theo business contract.

## 52. Không giữ transaction mở trong lúc chờ/backoff

Sai:

```java
@Transactional
public void retryOperation() {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            doDatabaseWork();
            return;
        } catch (TransientException ex) {
            sleep(backoff(attempt));
        }
    }
}
```

Nếu exception xảy ra trong persistence operation, transaction/Session có thể đã lỗi; sleeping không phục hồi nó. Giữ transaction mở trong lúc backoff còn chiếm connection/locks/resources.

Retry orchestration nên nằm ngoài transactional method:

```java
public void retryOperation() {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            writer.executeInNewTransaction();
            return;
        } catch (TransientDataAccessException ex) {
            if (attempt == 3) throw ex;
            backoff(attempt);
        }
    }
}
```

Mỗi lần gọi writer kết thúc transaction trước khi retry delay bắt đầu.

## 53. Logging không được biến catch thành continue

Một pattern an toàn:

```java
try {
    writer.saveInNewTransaction(input);
} catch (DataIntegrityViolationException ex) {
    log.warn(
        "Import item rejected: correlationId={}, sku={}, cause={}",
        correlationId,
        input.sku(),
        rootCauseCode(ex)
    );

    results.add(ImportResult.failure(input.sku()));
}
```

Ở đây writer.saveInNewTransaction đã kết thúc/rollback transaction trước khi exception đến caller. Caller không giữ Session của writer để tiếp tục dùng.

Chỉ log dữ liệu cần thiết; tránh raw entity hoặc bind values nhạy cảm. Nếu lỗi là fatal cho toàn batch, hãy dừng batch theo policy thay vì tiếp tục.

## 54. Checklist chẩn đoán khi thấy Session exception

Khi log có thông báo kiểu “Session is closed”, “transaction is marked rollback-only”, “current transaction is aborted” hoặc lỗi persistence tiếp theo sau một exception đầu tiên, hãy tìm root cause:

1. Exception đầu tiên là gì?
2. Nó phát sinh ở persist, merge, flush, auto-flush hay commit?
3. SQL statement nào vừa chạy?
4. SQLState/vendor error code là gì?
5. Database transaction có bị aborted không?
6. Hibernate/JPA/Spring đã mark rollback-only ở đâu?
7. Exception có bị catch và nuốt trong transaction không?
8. Code có tiếp tục dùng cùng EntityManager/Session không?
9. Có nested REQUIRED method chia sẻ transaction không?
10. Có REQUIRES_NEW nhưng bị self-invocation không?
11. Có retry bên trong cùng transaction không?
12. Có bulk/native SQL hoặc callbacks gây thêm side effects không?
13. Rollback có hoàn tất không?
14. Có Session/transaction mới trước lần thử tiếp theo không?
15. Commit outcome có uncertain do network failure không?

Đừng chỉ sửa exception cuối cùng. Tìm lỗi đầu tiên làm unit of work thất bại.

## 55. Quy tắc xử lý exception theo tầng

```text
HTTP/controller or batch orchestrator
    |
    +-- validate request
    |
    +-- call transactional service
            |
            +-- begin transaction + persistence context
            |
            +-- perform ORM operations
            |
            +-- flush/commit
            |
            +-- success -> return result
            |
            +-- persistence exception
                    |
                    +-- rollback + close/discard context
                    |
                    +-- exception propagates
    |
    +-- map error / record failed item
    |
    +-- if retry/continue:
            call a NEW transactional unit of work
```

Tầng transactional service chịu trách nhiệm một unit of work. Tầng orchestration chịu trách nhiệm quyết định dừng, retry hay tiếp tục. Tầng web chuyển application exception thành HTTP response. Không trộn cả ba trách nhiệm trong một method bắt exception rồi tiếp tục dùng cùng Session.

## 56. Những câu hỏi phải trả lời trước khi thiết kế partial success

Nếu yêu cầu là “import 10.000 rows, bỏ qua row lỗi và lưu row còn lại”, hãy xác định:

- Một row hay một chunk là atomic unit?
- Row thành công trước đó có được commit nếu row sau lỗi?
- Duplicate key được xử lý như lỗi hay update/upsert?
- Một lỗi DB transient có retry không?
- Có thứ tự phụ thuộc giữa rows không?
- Có foreign keys tham chiếu rows khác trong cùng file không?
- Audit history cần phản ánh từng row hay toàn batch?
- Có error report và khả năng resume không?
- Có idempotency key để tránh duplicate khi retry không?
- Connection/transaction throughput có đủ cho per-row transactions không?

Khi đã rõ, chọn transaction boundary và persistence context lifetime tương ứng. Không dùng catch-and-continue trong một Session làm thay thế cho thiết kế batch.

## 57. Bảng quyết định nhanh

| Bạn gặp | Đừng làm | Nên làm |
|---|---|---|
| Unique constraint khi flush | Catch rồi persist row kế tiếp trong cùng Session | Rollback/close; xử lý row tiếp theo trong transaction mới |
| UnexpectedRollbackException | Tắt rollback-only để ép commit | Tìm persistence exception đầu tiên và nơi bị nuốt |
| PostgreSQL “current transaction is aborted” | Chạy SELECT tiếp trên cùng connection | Rollback transaction |
| Optimistic lock failure | Sửa version trong object cũ | Rollback, reload và tính lại trong transaction mới |
| Batch insert failure | Tiếp tục flush batch/session cũ | Rollback/discard; retry hoặc chia chunk mới |
| Spring method catch exception | Nghĩ transaction đã khỏe lại | Để rollback và kết thúc boundary |
| Cần partial success | Dùng một transaction cho tất cả rồi nuốt lỗi | Transaction/session riêng theo row hoặc chunk |
| Cần retry | Lặp trong cùng @Transactional method | Retry ngoài boundary với Session mới |
| Cần kiểm tra DB sau lỗi | Query trên Session vừa ném exception | Mở transaction/session mới |
| Rollback gặp network error | Giả định chắc chắn chưa commit | Xử lý uncertain outcome bằng idempotency/reconciliation |

## 58. Kết luận

Nuốt một persistence exception rồi tiếp tục dùng cùng Hibernate Session là một lỗi về transaction lifecycle. Sau khi Session ném exception trong lúc thao tác persistence, persistence context có thể không còn nhất quán, transaction có thể rollback-only và database transaction có thể đã ở trạng thái failed.

Những nguyên tắc cần giữ:

1. **Phân biệt business validation trước persistence với exception từ Hibernate/JDBC.**
2. **Nhớ rằng lỗi có thể chỉ xuất hiện ở flush, auto-flush hoặc commit**, không nhất thiết tại lời gọi persist/save.
3. **Sau persistence exception, rollback transaction và close/discard Session.**
4. **Không dùng clear() hoặc query mới để cố phục hồi Session đã lỗi.**
5. **Không catch rồi commit, nuốt exception hoặc tiếp tục vòng lặp trên cùng persistence context.**
6. **Trong Spring, exception bị catch bên trong @Transactional có thể không đến interceptor; transaction vẫn có thể rollback-only.**
7. **noRollbackFor, NESTED và savepoint không phải cách sửa chữa Session đã lỗi.**
8. **Retry toàn bộ unit of work trong transaction và Session mới**, chỉ với lỗi transient và operation có semantics retry an toàn.
9. **Muốn partial success, tách transaction theo record/chunk** và catch lỗi ở bên ngoài boundary đã rollback.
10. **Kiểm thử trên database tương thích production**, bao gồm flush failure, rollback, optimistic locking, batch, Envers/cache nếu liên quan và uncertain commit outcome.

Một Session đại diện cho một persistence context có state. Khi persistence operation làm Session rơi vào trạng thái không còn đáng tin, hãy kết thúc unit of work đó. Bắt đầu lại bằng transaction và Session mới giúp ứng dụng có một trạng thái rõ ràng để tiếp tục, retry hoặc báo lỗi mà không che giấu dữ liệu chưa commit.

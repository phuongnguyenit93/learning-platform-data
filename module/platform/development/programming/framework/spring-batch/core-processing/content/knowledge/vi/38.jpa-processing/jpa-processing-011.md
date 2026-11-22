# Entity state sau rollback

Khi Spring Batch ghi dữ liệu bằng JPA, mỗi chunk thường chạy trong một transaction. Nếu writer flush dữ liệu rồi một thao tác khác trong chunk thất bại, transaction có thể rollback. Database hoàn tác các thay đổi thuộc transaction đó, nhưng **các Java object trong bộ nhớ không tự quay về trạng thái trước transaction**.

Đây là điểm dễ gây lỗi khi retry hoặc restart. Một entity có thể vẫn giữ field đã bị thay đổi, ID do provider cấp hoặc giá trị `@Version` đã được tăng trong lúc flush, dù row tương ứng không được commit. Sau rollback, không nên tiếp tục xem các object cũ là nguồn dữ liệu đáng tin cậy. Cần hiểu trạng thái managed/detached, loại bỏ persistence context không còn phù hợp và nạp lại trạng thái từ database trong transaction mới khi cần.

## 1. Các trạng thái entity trong JPA

JPA mô tả vòng đời entity qua các trạng thái chính:

| Trạng thái | Ý nghĩa | Có được persistence context theo dõi? |
|---|---|---:|
| New / transient | Object mới được tạo bằng `new`, chưa được persist hoặc merge. | Không. |
| Managed / persistent | Entity đang thuộc persistence context. JPA theo dõi thay đổi của nó. | Có. |
| Removed | Entity managed đã được đánh dấu xóa bằng `remove()`. | Có, cho tới khi thay đổi được đồng bộ và context kết thúc. |
| Detached | Entity từng được managed nhưng không còn thuộc persistence context. | Không. |

Ví dụ:

```java
Customer customer = new Customer("C001", "Nguyen An"); // New

entityManager.persist(customer);                         // Managed
customer.setName("An Nguyen");                          // Vẫn managed

entityManager.detach(customer);                         // Detached
```

Một entity detached vẫn là object Java bình thường. Các field và quan hệ đã được nạp vẫn còn trong bộ nhớ, nhưng JPA không còn tự động dirty checking những thay đổi mới trên object đó.

## 2. Rollback tác động thế nào đến entity?

Rollback hoàn tác thay đổi database của transaction. Nó không phải thao tác khôi phục object graph trong heap.

Ví dụ, entity đang có trạng thái trong database:

```text
Database trước transaction:
  customer C001, name = "Nguyen An", status = READY

Trong transaction:
  entity.setName("An Nguyen")
  entity.setStatus(PROCESSED)
  entityManager.flush()

Transaction rollback:
  Database vẫn là name = "Nguyen An", status = READY
  Java object có thể vẫn là name = "An Nguyen", status = PROCESSED
```

Sau rollback, các entity tham gia persistence context không còn là nguồn trạng thái đáng tin cậy. Theo lifecycle JPA, rollback làm các entity đã được quản lý trong persistence context trở thành detached; trạng thái field trong Java không được phục hồi về snapshot đầu transaction. Ứng dụng nên bỏ các instance đó hoặc nạp lại dữ liệu trong một persistence context/transaction mới.

Điểm quan trọng:

- Database rollback không đồng nghĩa với Java object rollback.
- `clear()` detach entity nhưng cũng không khôi phục field đã thay đổi.
- Một entity detached có thể chứa dữ liệu khác database.
- Muốn có trạng thái hiện tại từ database, hãy `find()`/query lại trong transaction mới.

## 3. Phân biệt rollback, flush và clear

Ba thao tác này giải quyết các vấn đề khác nhau:

| Thao tác | Tác động tới database | Tác động tới entity trong bộ nhớ |
|---|---|---|
| `flush()` | Gửi SQL của thay đổi đang chờ trong persistence context trong transaction hiện tại. | Entity vẫn managed; field không bị khôi phục. |
| `clear()` | Không tự gửi SQL hoặc commit. | Detach tất cả entity khỏi persistence context. Field của object vẫn giữ nguyên. |
| `rollback()` | Hoàn tác thay đổi database của transaction. | Không khôi phục field Java; các entity trong persistence context bị rollback có thể detached và không còn đáng tin cậy. |
| `commit()` | Xác nhận transaction nếu không có lỗi. | Các entity vẫn chịu lifecycle của persistence context; transaction-scoped context kết thúc theo transaction. |

Ví dụ:

```java
entity.setStatus(Status.PROCESSED);
entityManager.flush();

// SQL đã được gửi, nhưng transaction vẫn có thể rollback.
```

`flush()` không phải commit. Nếu một constraint violation hoặc exception xảy ra sau flush nhưng trước commit, database vẫn có thể rollback SQL đã gửi.

## 4. Ví dụ entity bị thay đổi nhưng database rollback

Giả sử một service thay đổi customer rồi cố tình ném lỗi:

```java
@Transactional
public void updateCustomerThenFail(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setStatus(Status.PROCESSED);

    entityManager.flush();

    throw new IllegalStateException("Force rollback");
}
```

Sau khi exception thoát khỏi transaction boundary và transaction rollback:

- Row trong database giữ status cũ.
- Object `customer` từng được dùng có thể vẫn chứa `PROCESSED`.
- Không được giữ object đó trong cache rồi giả định nó đại diện cho database.
- Lần xử lý sau cần nạp entity mới trong transaction mới.

Ví dụ đọc lại bằng transaction mới:

```java
Customer current = transactionTemplate.execute(status ->
        entityManager.find(Customer.class, customerId));
```

Đoạn code trên minh họa nguyên tắc. Trong ứng dụng thực tế, cần bảo đảm `TransactionTemplate` dùng transaction manager JPA tương thích và `EntityManager` là proxy do Spring quản lý.

## 5. Generated ID có thể vẫn còn sau rollback

Một tình huống dễ gây nhầm lẫn là entity được persist trong transaction bị rollback nhưng object Java vẫn giữ ID.

Ví dụ:

```java
Customer customer = new Customer("C999", "Temporary");
entityManager.persist(customer);
entityManager.flush();

Long generatedId = customer.getId();
// Sau đó transaction rollback.
```

Tùy chiến lược sinh ID và provider, ID có thể được gán trước commit. Với sequence, database sequence thường không rollback cùng transaction; một giá trị đã lấy có thể bị bỏ trống. Với `IDENTITY`, insert có thể phải được thực hiện sớm để lấy ID. Vì vậy, object có thể giữ ID dù row không tồn tại sau rollback.

Không được suy luận rằng “ID khác null” có nghĩa entity đã commit thành công. Sau rollback, hãy kiểm tra database trong transaction mới nếu cần xác định row có tồn tại hay không.

Không nên tái sử dụng object vừa persist thất bại như một entity mới chỉ vì row đã rollback. Tùy ID strategy/provider, object có thể còn identifier và trạng thái lifecycle không phù hợp để persist lại. Tạo entity instance mới từ dữ liệu đầu vào hoặc nạp lại theo khóa nghiệp vụ.

## 6. Giá trị @Version sau rollback

Với optimistic locking, JPA/provider quản lý field `@Version`. Khi update được flush, version trong entity có thể được tăng để phản ánh lần cập nhật dự kiến.

Ví dụ:

```java
@Entity
class Customer {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;
}
```

Giả sử database có `version = 4`. Trong transaction, entity đổi status và flush; provider có thể cập nhật object lên `version = 5`. Nếu transaction rollback, database vẫn có thể giữ `version = 4`, trong khi object Java vẫn giữ `5`.

Nếu dùng object cũ cho lần cập nhật sau, optimistic locking có thể báo stale state hoặc gây hành vi khó hiểu. Hãy nạp lại entity trong persistence context mới để lấy version hiện tại.

Không tự giảm version trong Java object để “khớp” database. Version là cơ chế concurrency của JPA/provider; chỉ database state trong transaction mới là nguồn xác thực.

## 7. Entity mới, managed và removed khi rollback

Các tình huống thường gặp:

| Trước rollback | Việc đã xảy ra trong transaction | Database sau rollback | Cách xử lý object |
|---|---|---|---|
| New | `persist()` và flush insert | Không có row mới nếu insert thuộc transaction bị rollback. | Bỏ object cũ; tạo instance mới nếu cần thử lại. |
| Managed | Sửa field và flush update | Row giữ giá trị trước transaction. | Nạp lại entity mới; không dùng field cũ làm trạng thái hiện tại. |
| Managed | `remove()` và flush delete | Row vẫn tồn tại nếu delete bị rollback. | Nạp lại entity trong transaction mới. |
| Detached | `merge()` tạo/cập nhật managed copy rồi rollback | Database giữ trạng thái trước transaction. | Object đầu vào vốn detached; managed copy không còn đáng tin cậy. Nạp lại dữ liệu. |

Rollback không tạo một object graph mới thay thế các object cũ trong biến Java. Các reference mà code đang giữ vẫn trỏ tới đúng object đó, với field hiện có.

## 8. merge() không làm object đầu vào trở thành managed

`EntityManager.merge(detached)` copy state của object đầu vào sang một instance managed và trả về instance đó. Object được truyền vào không tự trở thành managed.

```java
Customer detached = loadEarlier();
detached.setName("Updated");

Customer managedCopy = entityManager.merge(detached);
```

Trong ví dụ:

- `detached` vẫn là object detached.
- `managedCopy` là instance managed trong persistence context hiện tại.
- Các thay đổi trên `managedCopy` được JPA theo dõi.

Nếu transaction rollback, đừng tiếp tục dùng `managedCopy` như entity managed của transaction mới. Object `detached` ban đầu cũng có thể vẫn giữ các field đã sửa. Hãy nạp lại trạng thái từ database và quyết định rõ dữ liệu nào cần áp dụng lại.

## 9. Persistence context sau rollback

Ứng dụng nên coi persistence context đã tham gia transaction rollback là không còn phù hợp để tiếp tục xử lý nghiệp vụ dựa trên các entity cũ.

Trong Spring, một `EntityManager` được inject bằng `@PersistenceContext` thường là proxy lấy EntityManager gắn với transaction hiện tại. Khi transaction kết thúc/rollback, transaction-scoped EntityManager được quản lý theo lifecycle của Spring/JPA. Lần transaction tiếp theo có thể nhận một persistence context mới.

Nếu ứng dụng tự tạo `EntityManager` bằng `EntityManagerFactory.createEntityManager()`, ứng dụng phải tự quản lý lifecycle của nó. Sau rollback, nên đóng và bỏ EntityManager đó theo đúng contract, rồi tạo context mới cho công việc tiếp theo. Không giữ một EntityManager thủ công đã tham gia transaction lỗi để tiếp tục xử lý.

Với extended persistence context hoặc cấu hình đặc biệt, chi tiết lifecycle có thể khác theo container/provider. Quy tắc an toàn vẫn là không dựa vào trạng thái entity trong context đã rollback; nạp lại trong context sạch.

## 10. Retry trong Spring Batch có thể gặp object đã bị thay đổi

Trong chunk-oriented step, một chunk thường gồm:

```text
BEGIN transaction
  read items
  process items
  writer ghi dữ liệu
  update checkpoint
COMMIT
```

Nếu writer hoặc một thao tác trong chunk ném exception, transaction rollback. Spring Batch có thể retry theo cấu hình fault tolerance, hoặc step thất bại và được restart sau đó.

Database state và in-memory item state có vòng đời khác nhau:

- Database rollback các thay đổi trong transaction.
- Item Java có thể đã bị processor sửa trực tiếp.
- Entity đã merge/persist có thể đã nhận ID hoặc version mới trong bộ nhớ.
- Các object trong persistence context không được phục hồi về trạng thái ban đầu.
- Cách framework giữ, cache hoặc đọc lại item phụ thuộc reader, retry policy và cấu hình step.

Vì vậy, processor và writer nên được thiết kế để có thể chạy lại an toàn. Không giả định lần retry luôn nhận một object mới hoàn toàn hoặc một entity có state đã được reset.

## 11. Tránh mutate trực tiếp entity đầu vào trong processor

Nếu processor sửa trực tiếp entity do reader trả về, lần retry có thể gặp object đã mang thay đổi từ lần xử lý trước.

Ví dụ dễ gây nhầm lẫn:

```java
@Bean
ItemProcessor<Customer, Customer> processor() {
    return customer -> {
        customer.setStatus(Status.PROCESSED);
        customer.setName(customer.getName().trim());
        return customer;
    };
}
```

Nếu `customer` là entity managed hoặc được giữ lại giữa các lần gọi, thay đổi trên object xảy ra ngay trong heap trước khi transaction commit. Rollback database không hoàn tác các lệnh setter.

Một cách dễ kiểm soát hơn là dùng DTO bất biến làm input, tạo output mới:

```java
@Bean
ItemProcessor<CustomerInput, CustomerUpdate> processor() {
    return input -> new CustomerUpdate(
            input.customerId(),
            input.name().trim(),
            Status.PROCESSED);
}
```

Writer sau đó load entity hiện tại trong transaction của chunk và áp dụng `CustomerUpdate`. Cách này tách dữ liệu đọc khỏi entity managed và làm retry dễ dự đoán hơn.

## 12. Reader trả về entity detached hay managed?

Không phải mọi JPA reader đều trả về entity ở cùng trạng thái:

- `JpaPagingItemReader` có lifecycle EntityManager riêng cho việc đọc page; entity có thể được detach khi reader clear context/page hoàn tất.
- Một custom reader có thể trả entity từ transaction-scoped EntityManager của chunk, tùy cách inject và transaction configuration.
- JDBC reader thường trả DTO/entity object không được JPA quản lý.
- Reader dùng projection thường không trả entity managed.

Hãy xác định trạng thái thực tế của item trước khi thiết kế processor/writer. Không giả định entity do reader trả về luôn managed trong transaction của writer.

Nếu reader trả entity detached, writer có thể dùng merge để áp dụng state, nhưng cần cẩn trọng với stale data và optimistic locking. Nếu chỉ cần một số field, DTO/projection thường đơn giản hơn.

## 13. JpaItemWriter và rollback

`JpaItemWriter` ghi các item trong chunk bằng JPA. Tùy cấu hình, writer dùng `merge()` hoặc `persist()`, sau đó flush và có thể clear persistence context.

Ví dụ:

```java
@Bean
JpaItemWriter<Customer> customerWriter(EntityManagerFactory emf) {
    JpaItemWriter<Customer> writer = new JpaItemWriter<>();
    writer.setEntityManagerFactory(emf);
    writer.setUsePersist(false);
    writer.setClearPersistenceContext(true);
    return writer;
}
```

Nếu `JpaItemWriter` flush thành công nhưng một listener hoặc thao tác khác khiến chunk rollback:

- Database hoàn tác các insert/update trong transaction.
- Clear (nếu đã được gọi) chỉ detach entity, không reset field Java.
- Entity input có thể giữ ID/version hoặc field đã thay đổi.
- Lần retry/restart cần dựa trên checkpoint và trạng thái database mới, không dựa vào việc object cũ tự quay lại trạng thái trước ghi.

`clearPersistenceContext` không phải cơ chế khôi phục entity sau rollback. Nó là thao tác quản lý bộ nhớ và trạng thái managed sau khi writer xử lý chunk.

## 14. Đừng tái sử dụng EntityManager sau rollback như thể chưa có gì xảy ra

Khi transaction rollback, persistence context và entity state có thể không còn nhất quán. Đừng tiếp tục chạy nhiều thao tác trên cùng context với các entity cũ mà không xác định rõ lifecycle.

Với Spring-managed EntityManager:

- Để Spring transaction manager kết thúc transaction.
- Không gọi `EntityTransaction.rollback()` thủ công trên shared EntityManager proxy.
- Bắt đầu transaction mới cho lần xử lý tiếp theo.
- Nạp lại entity cần dùng trong transaction mới.

Với application-managed EntityManager:

- Kết thúc transaction theo đúng API.
- Đóng EntityManager nếu lifecycle yêu cầu hoặc context không còn phù hợp.
- Không chia sẻ EntityManager thủ công giữa thread/transaction.
- Tạo context mới cho lần thử tiếp theo.

Nếu transaction đã đánh dấu rollback-only, bắt exception rồi tiếp tục ghi trong cùng transaction không làm transaction trở lại trạng thái hợp lệ. Phải để transaction kết thúc và bắt đầu transaction mới.

## 15. Refresh và reload sau rollback

`refresh(entity)` nạp lại trạng thái database vào một entity **đang managed**. Nó không phải cách chung để cứu một entity đã detached sau rollback.

Nếu entity vẫn managed trong context hợp lệ, `refresh()` có thể dùng để ghi đè state hiện tại bằng state database. Nhưng sau rollback, nên ưu tiên transaction/persistence context mới và query lại entity:

```java
Customer current = entityManager.find(Customer.class, customerId);
```

Nếu object cũ đã detached và cần merge, hãy nhớ `merge()` trả về instance managed mới:

```java
Customer managed = entityManager.merge(detachedCustomer);
```

Không tiếp tục thao tác trên `detachedCustomer` với kỳ vọng các thay đổi sau merge sẽ được dirty checking. Dùng `managed` nếu cần làm việc trong context hiện tại.

Tuy nhiên, merge toàn bộ detached entity có thể ghi đè field mới hơn trong database bằng dữ liệu stale từ object cũ. Với retry sau rollback, load lại theo ID rồi áp dụng lại thay đổi nghiệp vụ cần thiết thường an toàn hơn merge mù quáng.

## 16. Optimistic locking và retry sau rollback

Nếu hai transaction cùng cập nhật một entity, `@Version` giúp phát hiện stale update. Sau rollback, entity cũ có thể mang version không còn khớp database.

Ví dụ:

```text
Database ban đầu: id=10, version=3, status=READY

Transaction A:
  load version 3
  update status
  flush -> version trong DB transaction dự kiến thành 4
  rollback

Database sau rollback:
  id=10, version=3, status=READY

Object A trong heap:
  có thể vẫn mang version 4 và status đã sửa
```

Nếu một transaction khác đã commit thay đổi version 4 sau đó, object A càng stale. Lần thử lại nên load entity mới, kiểm tra trạng thái hiện tại và quyết định có thể áp dụng nghiệp vụ hay cần conflict handling.

Không tự retry vô hạn `OptimisticLockException`. Retry chỉ có ý nghĩa nếu có chiến lược reload, kiểm tra lại điều kiện nghiệp vụ và giới hạn số lần thử.

## 17. Rollback trong chunk và checkpoint của reader

Spring Batch lưu checkpoint cùng transaction/chunk theo lifecycle của step. Khi chunk rollback, checkpoint của chunk chưa commit không được coi là đã hoàn tất; lần retry hoặc restart có thể đọc lại item thuộc chunk đó.

Ví dụ:

```text
Chunk 1: item 1-100 -> commit thành công
Chunk 2: item 101-200 -> writer flush, sau đó lỗi -> rollback

Database:
  thay đổi chunk 1 được giữ
  thay đổi chunk 2 bị rollback

Checkpoint:
  giữ vị trí đã commit sau chunk 1

Retry/restart:
  xử lý lại item thuộc chunk 2 theo semantics của reader
```

Điều này không có nghĩa object Java trong chunk 2 được reset. Reader có thể đọc lại item từ nguồn hoặc framework có thể dùng cơ chế cache cho retry; hành vi cụ thể phụ thuộc reader và fault-tolerance configuration.

Vì vậy, không dùng mutable entity instance làm nơi lưu tiến độ batch. Tiến độ cần nằm trong `ExecutionContext`/JobRepository hoặc một store có transaction semantics rõ ràng.

## 18. Retry, skip và entity state

Retry và skip có thể khiến cùng một item được xử lý qua nhiều lần attempt. Cần phân biệt:

| Hành vi | Ý nghĩa |
|---|---|
| Retry | Thử lại thao tác thất bại theo policy; transaction của attempt trước có thể đã rollback. |
| Skip | Chấp nhận bỏ item lỗi theo skip policy sau khi framework xử lý transaction/error semantics. |
| Restart | Tạo JobExecution mới cho cùng JobInstance và khôi phục từ checkpoint đã commit. |

Nếu processor mutate input entity, retry có thể gặp object với field đã đổi. Nếu writer merge một entity có ID/version đã được cập nhật trong attempt trước, retry có thể gây stale state hoặc conflict.

Thiết kế an toàn:

- Processor càng ít side effect càng tốt.
- Ưu tiên DTO bất biến hoặc tạo output object mới.
- Writer load lại entity theo business key trong transaction hiện tại khi cần cập nhật.
- Dùng optimistic locking để phát hiện xung đột thay vì ghi đè âm thầm.
- Đặt retry policy cho lỗi có khả năng phục hồi; không retry lỗi dữ liệu vĩnh viễn.
- Dùng skip listener/rejected record store để audit item bị loại.

## 19. External side effect không tự rollback cùng JPA

Rollback database chỉ hoàn tác resource tham gia transaction đó. Nếu processor/writer đã gửi email, gọi HTTP API, publish message hoặc ghi file ngoài transaction, side effect có thể vẫn tồn tại sau khi database rollback.

Ví dụ:

```text
Chunk transaction:
  update Order trong database
  gọi payment API thành công
  ghi database tiếp theo bị lỗi
  transaction rollback

Kết quả:
  database không giữ update Order
  payment API có thể vẫn đã xử lý thanh toán
```

Không đặt side effect không idempotent trong processor rồi giả định rollback sẽ hoàn tác nó. Các lựa chọn thường dùng:

- Transactional outbox: ghi event vào cùng database transaction, publisher gửi sau commit.
- Idempotency key: gửi một khóa ổn định để đích nhận nhận diện request lặp.
- Reconciliation: đối soát trạng thái giữa database và hệ thống ngoài.
- Staging/publish: ghi file tạm và công bố sau khi transaction/job hoàn tất.

Entity state sau rollback và side effect ngoài transaction là hai vấn đề liên quan nhưng khác nhau; cả hai đều cần được thiết kế cho retry/restart.

## 20. Transaction manager và JPA rollback

Trong Spring Batch, step nên dùng transaction manager tương thích với `EntityManagerFactory` để JPA writer tham gia đúng chunk transaction.

Ví dụ:

```java
@Bean
JpaTransactionManager jpaTransactionManager(EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}

@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        JpaTransactionManager jpaTransactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        JpaItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(200, jpaTransactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Trong ứng dụng có nhiều datasource hoặc nhiều transaction manager, cần chỉ rõ manager nào điều khiển step và tài nguyên nào thực sự tham gia transaction. Không mặc định một JDBC transaction manager bất kỳ sẽ đồng bộ persistence context JPA.

## 21. Đừng bắt exception rồi tiếp tục trong transaction đã rollback-only

Một lỗi persistence có thể đánh dấu transaction rollback-only. Nếu code bắt exception bên trong cùng transaction rồi tiếp tục ghi, commit cuối cùng vẫn có thể thất bại hoặc transaction manager báo `UnexpectedRollbackException`.

Ví dụ anti-pattern:

```java
@Transactional
public void process(Customer customer) {
    try {
        repository.save(customer);
        entityManager.flush();
    } catch (PersistenceException exception) {
        log.warn("Write failed", exception);
        // Tiếp tục làm việc trong transaction có thể đã rollback-only.
    }
}
```

Hãy để exception đi tới transaction boundary để rollback rõ ràng, rồi xử lý retry/recovery trong transaction mới. Nếu cần bắt lỗi để chuyển sang nhánh nghiệp vụ khác, phải thiết kế transaction propagation và rollback rules cụ thể, không dùng một catch chung.

## 22. Entity graph và quan hệ sau rollback

Rollback không tái tạo lại trạng thái của cả object graph. Nếu processor thay đổi cả hai phía của quan hệ trong bộ nhớ:

```java
order.setCustomer(customer);
customer.getOrders().add(order);
```

database có thể rollback thay đổi foreign key, nhưng các collection/reference Java vẫn giữ quan hệ vừa thêm. Khi dùng object cũ, code có thể nhìn thấy một quan hệ không tồn tại trong database.

Với quan hệ hai chiều, application thường phải duy trì cả owning side và inverse side đúng khi transaction thành công. Sau rollback, đừng dùng object graph cũ để quyết định trạng thái database. Nạp lại aggregate hoặc các entity liên quan trong persistence context mới.

Đối với lazy collection, entity detached có thể không tải được dữ liệu chưa được khởi tạo. Hãy query/fetch đúng dữ liệu cần thiết trong transaction mới thay vì cố truy cập proxy cũ.

## 23. Entity state khi dùng savepoint hoặc nested transaction

Một số database/transaction manager hỗ trợ savepoint hoặc nested transaction ở mức JDBC. Tuy nhiên, JPA persistence context không nhất thiết có semantics rollback từng phần tương ứng với savepoint.

Nếu một phần SQL bị rollback về savepoint nhưng persistence context vẫn chứa entity đã thay đổi, state trong memory có thể không khớp database. Không nên giả định savepoint tự khôi phục entity field hoặc version.

Khi cần nested/partial rollback:

- Kiểm tra transaction manager/provider có hỗ trợ mô hình đó không.
- Xác định persistence context được đồng bộ/clear thế nào sau rollback về savepoint.
- Nạp lại entity cần dùng nếu state không còn chắc chắn.
- Viết integration test trên database thực tế.

Trong batch, thường đơn giản và an toàn hơn khi dùng chunk transaction rõ ràng, skip/retry policy của Spring Batch và một transaction boundary cho từng chunk thay vì tự quản lý savepoint bên trong writer.

## 24. Xử lý entity sau rollback trong service

Một service có thể cần thực hiện hành động bù hoặc ghi nhận lỗi sau rollback. Hãy tách phần đó sang transaction mới:

```java
@Service
public class CustomerRecoveryService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String customerId, String reason) {
        // Ghi audit/recovery record trong transaction mới.
    }
}
```

`REQUIRES_NEW` tạo transaction độc lập khi được gọi qua Spring proxy. Cần cân nhắc connection pool, lock và việc audit transaction có thể commit dù transaction batch bên ngoài rollback.

Không truyền entity managed/detached cũ vào recovery service rồi giả định nó có trạng thái chính xác. Truyền business key và dữ liệu lỗi cần thiết; nếu recovery cần trạng thái hiện tại, query lại trong transaction mới.

## 25. Kiểm thử entity state sau rollback

Test nên chứng minh hai kết quả độc lập:

1. Database không giữ thay đổi của transaction rollback.
2. Java object không tự quay về giá trị ban đầu.

Ví dụ test với `TransactionTemplate`:

```java
@Test
void rollbackDoesNotRestoreJavaObjectFields() {
    Customer customer = new Customer("C001", "Nguyen An");

    assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
        entityManager.persist(customer);
        entityManager.flush();

        customer.setName("Changed in memory");
        entityManager.flush();

        throw new IllegalStateException("Force rollback");
    }));

    // Object Java vẫn có thể giữ giá trị đã thay đổi.
    assertThat(customer.getName()).isEqualTo("Changed in memory");

    // Query trong transaction mới để xác nhận database state.
    String databaseName = transactionTemplate.execute(status ->
            entityManager.createQuery(
                    "select c.name from Customer c where c.customerId = :id",
                    String.class)
                    .setParameter("id", "C001")
                    .getResultStream()
                    .findFirst()
                    .orElse(null));

    assertThat(databaseName).isNull();
}
```

Ví dụ giả định `customerId` có unique constraint và EntityManager được inject qua Spring. Trong test thực tế, không dùng cùng transaction đã rollback để query kết quả; query xác nhận phải chạy trong transaction mới.

## 26. Kiểm thử generated ID và version

Nếu ứng dụng phụ thuộc ID/version, test trên database/provider thực tế:

- Persist entity mới và flush để provider gán ID.
- Cố tình rollback transaction.
- Xác nhận row không tồn tại trong transaction mới.
- Quan sát object Java có còn ID hay không, nhưng không coi đó là hợp đồng reset.
- Update entity có `@Version`, flush rồi rollback.
- Xác nhận database version giữ giá trị trước transaction.
- Xác nhận lần load mới nhận version database, không dùng field version của object cũ.

Các chiến lược ID khác nhau có thể tạo hành vi khác nhau. Đừng viết test yêu cầu mọi provider phải reset ID về null sau rollback nếu JPA/provider không bảo đảm điều đó.

## 27. Kiểm thử Spring Batch retry sau rollback

Integration test nên tạo một step có nhiều chunk và một writer/processor có thể thất bại có kiểm soát:

1. Reader trả item có business key ổn định.
2. Processor tạo output mới hoặc writer load entity trong transaction của chunk.
3. Writer ghi một số entity rồi ném exception ở lần đầu.
4. Xác nhận transaction chunk rollback và database không có thay đổi chưa commit.
5. Cho retry hoặc restart theo cấu hình.
6. Xác nhận item được xử lý lại đúng semantics.
7. Xác nhận không có ID/version stale gây ghi sai.
8. Xác nhận không mất hoặc nhân đôi dữ liệu.

Test không nên chỉ kiểm tra job cuối cùng `COMPLETED`. Hãy kiểm tra business key, row count, version và số lần side effect được gọi.

## 28. Kiểm thử processor không mutate input

Với DTO/entity input, có thể kiểm tra processor tạo output mới mà không sửa input:

```java
@Test
void processorCreatesOutputWithoutMutatingInput() throws Exception {
    CustomerInput input = new CustomerInput(
            "C001", "  Nguyen An  ", Status.READY);

    CustomerUpdate output = processor.process(input);

    assertThat(input.name()).isEqualTo("  Nguyen An  ");
    assertThat(output.name()).isEqualTo("Nguyen An");
}
```

Với entity mutable, test tương tự có thể xác nhận processor không gọi setter trên input. Đây là cách giảm rủi ro retry gặp object đã bị thay đổi từ attempt trước.

## 29. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Database rollback nhưng object vẫn có giá trị mới | JPA không khôi phục field Java khi transaction rollback. | Bỏ object cũ và load lại trong transaction mới. |
| ID khác null nhưng không tìm thấy row | ID được cấp trước commit; transaction đã rollback. | Không dùng ID đơn lẻ làm bằng chứng commit; query lại database. |
| Optimistic locking lỗi khi retry | Object giữ `@Version` cũ hoặc version đã tăng trong memory. | Reload entity và đánh giá lại thay đổi trong transaction mới. |
| Entity cũ vẫn được xem là managed | Persistence context đã rollback nhưng code tiếp tục dùng reference cũ. | Xem entity là detached/không đáng tin cậy; dùng context mới. |
| `merge()` xong vẫn sửa nhầm object | Code tiếp tục sửa object đầu vào thay vì instance merge trả về. | Dùng managed instance được trả về từ `merge()`. |
| Retry ghi dữ liệu lặp | Processor/writer có side effect ngoài transaction hoặc không idempotent. | Dùng idempotency key, unique constraint hoặc outbox. |
| Quan hệ Java không khớp database | Rollback không phục hồi hai phía của object graph. | Nạp lại aggregate trong persistence context mới. |
| Lazy loading lỗi sau rollback | Entity detached hoặc context đã đóng/clear. | Fetch lại dữ liệu cần thiết trong transaction mới. |
| `UnexpectedRollbackException` | Exception bị bắt nhưng transaction đã rollback-only. | Để exception đi tới boundary và xử lý trong transaction mới. |
| Dữ liệu stale bị merge ghi đè | Merge toàn bộ detached object sau khi database đã thay đổi. | Reload rồi áp dụng thay đổi nghiệp vụ có chọn lọc. |
| File/API đã thay đổi dù chunk rollback | Side effect không tham gia transaction database. | Dùng staging, outbox, idempotency và reconciliation. |

## 30. Quy trình xử lý entity sau rollback

Khi một chunk hoặc transaction JPA thất bại, hãy xử lý theo thứ tự:

1. **Để transaction kết thúc:** không tiếp tục ghi trong transaction đã rollback-only.
2. **Phân biệt database state và Java state:** xác nhận rollback đã hoàn tác những thay đổi nào.
3. **Loại bỏ reference cũ khi cần:** không dùng entity instance của transaction lỗi làm nguồn dữ liệu hiện tại.
4. **Bắt đầu transaction/persistence context mới:** dùng transaction manager Spring quản lý.
5. **Reload theo business key/ID:** lấy state mới nhất từ database.
6. **Kiểm tra version và điều kiện nghiệp vụ:** quyết định có thể áp dụng lại thay đổi hay đã có xung đột.
7. **Tạo lại output:** ưu tiên DTO/command mới thay vì mutate entity cũ.
8. **Thực hiện lại có giới hạn:** retry lỗi tạm thời, không retry lỗi dữ liệu vĩnh viễn.
9. **Kiểm soát side effect:** dùng outbox/idempotency cho API, message và file.
10. **Kiểm thử restart:** xác nhận checkpoint và database state đồng bộ, không mất/lặp item.

## 31. Những điểm cần ghi nhớ

- JPA entity có các trạng thái new, managed, removed và detached.
- Rollback hoàn tác database transaction, không phục hồi các field của Java object về giá trị trước transaction.
- Entity thuộc persistence context tham gia rollback trở thành detached theo lifecycle JPA; không dựa vào state cũ để tiếp tục nghiệp vụ.
- `flush()` gửi SQL nhưng không commit; SQL đã flush vẫn có thể bị rollback.
- `clear()` detach entity nhưng không reset field, ID hoặc version trong object.
- Generated ID có thể vẫn còn sau rollback; sequence/identity strategy có thể để lại khoảng trống.
- Field `@Version` trong object có thể khác version đang lưu trong database sau rollback.
- `merge()` trả về instance managed mới; object truyền vào vẫn detached.
- Sau rollback, bắt đầu transaction mới và load lại entity nếu cần trạng thái database hiện tại.
- Không giả định Spring Batch retry luôn tạo object mới hoặc reset object cũ; thiết kế processor/writer để chạy lại an toàn.
- Ưu tiên DTO bất biến và processor không mutate input; writer load/apply thay đổi trong transaction hiện tại.
- Entity graph và lazy association trong object cũ có thể không phản ánh database sau rollback.
- Side effect ngoài database transaction không tự rollback; dùng outbox, idempotency hoặc reconciliation.
- Kiểm thử riêng database state, Java object state, generated ID/version và retry/restart của chunk.

Entity state sau rollback cần được xem như một trạng thái bộ nhớ riêng biệt với trạng thái database. Spring Batch có thể đọc lại item sau khi chunk rollback, nhưng JPA không tự hoàn nguyên object đã bị sửa trong attempt trước. Hãy kết thúc transaction lỗi, bỏ hoặc không tin cậy entity cũ, nạp lại dữ liệu trong persistence context mới và áp dụng thay đổi theo cách idempotent. Cách tiếp cận này giúp retry/restart không dựa vào state stale và giữ kết quả batch nhất quán với database.

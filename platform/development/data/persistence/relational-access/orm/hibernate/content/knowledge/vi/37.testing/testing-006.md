# Kiểm thử persist, merge, detach, refresh và trạng thái sau rollback trong Hibernate ORM

Kiểm thử Hibernate/JPA không chỉ là gọi repository rồi assert object trả về. Các thao tác `persist()`, `merge()`, `detach()`, `refresh()` và rollback tác động khác nhau đến entity, persistence context và database transaction. Nếu không tách ba lớp này, test có thể “pass” vì first-level cache trả object đang giữ state trong memory, dù database chưa commit; hoặc test hiểu nhầm object detached đã được merge thành managed.

Bài học này giải thích lifecycle của entity, hợp đồng từng thao tác, flush so với commit, trạng thái Java sau rollback, cascade, lazy associations, optimistic locking và cách viết integration tests có transaction boundary rõ ràng với Spring/JUnit.

Mỗi test nên trả lời ba câu hỏi độc lập:

1. Object Java đang ở trạng thái nào: new, managed, detached hay removed?
2. Thay đổi database đã flush, commit hay rollback?
3. Assertion đang đọc từ persistence context hiện tại, cache hay một context mới?

## 1. Entity lifecycle và persistence context

JPA quản lý entity thông qua persistence context. Với Hibernate, persistence context thường gắn với một `Session`; trong JPA, ứng dụng thao tác qua `EntityManager`.

| Trạng thái | Ý nghĩa | Có được context quản lý? |
|---|---|---|
| New / transient | Object vừa tạo bằng `new`, chưa persist | Không |
| Managed / persistent | Entity được quản lý trong persistence context hiện tại | Có |
| Detached | Entity từng managed nhưng đã detach/clear/close hoặc context kết thúc | Không |
| Removed | Entity managed đã được đánh dấu xóa, chờ flush | Có |

```text
new object
   |
   | persist(entity)
   v
managed entity
   | \
   |  +-- remove(entity) ------> removed
   |
   +----- detach(entity) ------> detached
   |
   +----- clear()/close() -----> detached

detached entity
   |
   | merge(entity)
   v
managed COPY (returned value)
   |
   +---- flush / commit -------> database changes
```

### 1.1. Persistence context là identity map

Trong cùng persistence context, một entity type và primary key thường có một managed instance đại diện:

```java
Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 10L);

assertSame(first, second);
```

Lần find thứ hai có thể trả object từ first-level cache mà không chạy SELECT. Vì thế:

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("New name");

Customer again = em.find(Customer.class, 10L);
assertEquals("New name", again.getName());
```

Assertion chỉ chứng minh object managed đang giữ giá trị mới. Nó **không chứng minh database đã UPDATE hoặc transaction đã commit**.

### 1.2. Ba lớp cần tách

- **Java object state:** các field trong heap hiện có giá trị gì.
- **Persistence-context state:** entity còn managed và được dirty-check hay không.
- **Database transaction state:** SQL đã flush chưa, transaction commit hay rollback.

Các thao tác lifecycle phải được test bằng đúng lớp cần xác minh.

## 2. Flush, commit và rollback

`flush()` yêu cầu Hibernate đồng bộ pending changes trong persistence context xuống database bằng SQL. Nó không kết thúc transaction.

`commit()` hoàn tất transaction. `rollback()` hủy những thay đổi transactional của transaction đó theo semantics database.

```text
managed entity changed
        |
        v
dirty checking
        |
        v
flush -> SQL INSERT / UPDATE / DELETE
        |
        +---- commit   -> transaction succeeds
        |
        +---- rollback -> database changes are undone

Java object in memory:
  may still contain changed values after rollback
```

Ví dụ:

```java
@Transactional
public void rename(Long id, String name) {
    Customer customer = em.find(Customer.class, id);
    customer.rename(name);

    em.flush(); // SQL có thể đã chạy, transaction chưa commit.
}
```

Nếu transaction rollback sau flush, database hoàn tác UPDATE. Nhưng object Java có thể vẫn chứa tên mới.

### 2.1. Vì sao cần flush trong test?

Nhiều lỗi chỉ xuất hiện khi Hibernate gửi SQL:

- NOT NULL, unique hoặc foreign-key violation.
- SQL type/conversion error.
- Optimistic locking conflict.
- Batch execution failure.

Nếu chỉ assert object trước flush, test có thể chưa kích hoạt bất kỳ kiểm tra nào ở database.

### 2.2. Flush có thể tự động xảy ra

Hibernate có thể flush trước query hoặc khi transaction hoàn tất tùy flush mode và query spaces. Vì vậy thời điểm exception/SQL trong test phụ thuộc mapping, generator và provider version.

## 3. persist(): quản lý entity mới

`EntityManager.persist(entity)` đưa entity mới vào persistence context.

```java
Customer customer = new Customer("An");

em.persist(customer);

assertTrue(em.contains(customer));
```

Sau persist:

- Chính instance truyền vào trở thành managed.
- Hibernate theo dõi dirty changes.
- INSERT có thể chờ flush/commit.
- Cascade `PERSIST` có thể lan sang associations.
- Identifier có thể được cấp ngay hoặc muộn hơn, tùy generator/dialect.

### 3.1. Không giả định INSERT luôn chạy tại persist()

Với sequence/table/pooled generators, Hibernate có thể lấy ID và trì hoãn INSERT. Với `IDENTITY`, provider thường phải INSERT sớm hơn để nhận generated key. Test chỉ nên khóa thời điểm SQL nếu đó là hành vi cần kiểm tra.

Nếu muốn kích hoạt constraint, gọi `flush()`:

```java
em.persist(customer);
em.flush(); // Constraint/SQL errors có thể xuất hiện tại đây.
```

### 3.2. Test persist cơ bản

```java
@Test
void persistMakesEntityManaged() {
    Customer customer = new Customer("An");

    em.persist(customer);

    assertThat(em.contains(customer)).isTrue();

    em.flush();

    assertThat(customer.getId()).isNotNull();
}
```

Test này kiểm tra managed state và flush. Nó chưa chứng minh commit bền vững.

### 3.3. Xác minh sau commit

Để chứng minh dữ liệu đã commit:

1. Persist trong transaction A.
2. Commit và kết thúc context A.
3. Mở transaction/EntityManager B.
4. Load theo ID.
5. Assert giá trị từ context mới.

Đừng dùng một `find()` ngay sau persist trong cùng context làm bằng chứng database đã lưu.

### 3.4. Persist detached entity

`persist()` dành cho entity mới. Truyền entity detached đã có identity có thể dẫn tới `EntityExistsException` hoặc exception provider-specific ở thời điểm gọi/flush. Không dùng persist để cập nhật detached state; hãy xác định đúng use case merge hoặc load managed entity rồi update.

### 3.5. Cascade PERSIST

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.PERSIST
)
private List<Address> addresses = new ArrayList<>();
```

Persist Customer có thể persist Address mới theo cascade. Với association hai chiều, phải set owning side để FK được ghi đúng:

```java
public void addAddress(Address address) {
    addresses.add(address);
    address.setCustomer(this);
}
```

Test nên flush rồi kiểm tra child row trong context mới, không chỉ assert collection Java chứa Address.

## 4. merge(): hợp nhất state vào managed instance

Điểm quan trọng nhất của `merge()`:

**`merge(detached)` trả về một managed instance có state được hợp nhất. Object đầu vào vẫn detached.**

```java
Customer detached = loadCustomerInPreviousContext(10L);
detached.rename("Updated");

Customer managed = em.merge(detached);

assertThat(em.contains(managed)).isTrue();
assertThat(em.contains(detached)).isFalse();
assertThat(managed).isNotSameAs(detached);
```

### 4.1. Luôn dùng giá trị trả về

Sai:

```java
em.merge(detached);
detached.rename("Another value");
```

Object detached không được context mới dirty-check.

Đúng:

```java
Customer managed = em.merge(detached);
managed.rename("Another value");
```

### 4.2. Test identity và state

```java
@Test
void mergeReturnsManagedCopy() {
    Customer detached = loadDetachedCustomer();
    detached.rename("New name");

    Customer merged = em.merge(detached);

    assertThat(em.contains(merged)).isTrue();
    assertThat(em.contains(detached)).isFalse();
    assertThat(merged).isNotSameAs(detached);
    assertThat(merged.getName()).isEqualTo("New name");
}
```

Nếu cần kiểm tra DB, flush/commit rồi load bằng context mới.

### 4.3. Merge entity mới

Với transient entity, `merge()` có thể tạo managed copy mới tương ứng. Input vẫn không trở thành managed instance được trả về. Không dùng merge một cách mù quáng cho mọi loại object.

### 4.4. Merge không phải PATCH an toàn

Giả sử entity có name, email và phone. Client chỉ gửi name nhưng mapper tạo detached entity với email/phone null. Merge có thể copy null lên managed state và ghi đè dữ liệu đang có.

Một pattern an toàn hơn:

```java
@Transactional
public void updateCustomer(
        Long id,
        UpdateCustomerRequest request) {

    Customer customer = em.find(Customer.class, id);

    if (request.name() != null) {
        customer.rename(request.name());
    }

    if (request.phoneProvided()) {
        customer.changePhone(request.phone());
    }
}
```

Cần phân biệt field bị bỏ qua với field được gửi rõ ràng là null. DTO không nên được coi là detached entity đầy đủ.

### 4.5. Cascade MERGE

`CascadeType.MERGE` có thể lan merge qua associations. Kiểm thử:

- Child detached có được merge đúng identity?
- Association thiếu phần tử có tương tác với orphan removal không?
- Có cascade vào reference data dùng chung không?
- Lazy association chưa initialized được xử lý thế nào?
- User có quyền thay đổi tất cả objects trong graph không?

Không merge toàn graph từ client nếu graph chứa associations ngoài quyền cập nhật của caller.
## 5. detach(): ngừng dirty checking

`EntityManager.detach(entity)` loại một entity khỏi persistence context:

```java
Customer customer = em.find(Customer.class, 10L);

assertThat(em.contains(customer)).isTrue();

em.detach(customer);

assertThat(em.contains(customer)).isFalse();
```

Sau detach, object Java vẫn tồn tại và giữ field values, nhưng thay đổi tiếp theo không tự được dirty-check trong context đó. SQL đã flush trước detach vẫn thuộc transaction và có thể commit. Thay đổi chưa flush sau detach không tự được context đó ghi. Lazy proxy/collection chưa initialized có thể không còn tải được sau khi context đóng.

### 5.1. Test detach ngăn dirty checking

```java
@Test
void detachedChangesAreNotAutomaticallyPersisted() {
    Customer customer = em.find(Customer.class, 10L);

    em.detach(customer);
    customer.rename("Memory only");

    em.flush();
    em.clear();

    Customer reloaded = em.find(Customer.class, 10L);

    assertThat(reloaded.getName()).isNotEqualTo("Memory only");
}
```

Test cần fixture phù hợp và context mới để tránh L1 state. Nếu L2 cache bật, kiểm soát cache khi mục tiêu là xác minh DB tuyệt đối.

### 5.2. Phân biệt thay đổi trước và sau detach

```java
customer.rename("Before detach");
em.flush();

em.detach(customer);

customer.rename("After detach");
```

Giá trị trước detach đã flush vẫn thuộc transaction. Giá trị sau detach không tự được dirty-check. Commit có thể lưu giá trị trước detach; rollback sẽ hoàn tác SQL đã flush.

### 5.3. detach() khác clear()

```java
em.detach(customer); // Một entity
em.clear();          // Toàn bộ managed entities
```

`clear()` không xóa rows, không rollback transaction và không evict L2 cache.

### 5.4. Cascade DETACH

Nếu association khai báo `CascadeType.DETACH`, detach owner có thể detach các entities liên quan. Test nên kiểm tra `em.contains` trên từng instance quan trọng.

### 5.5. Lazy loading sau detach

Nếu collection chưa initialized, gọi `size()` sau khi context đóng thường có thể ném `LazyInitializationException`. Nếu collection đã initialized, dữ liệu đã có trong memory có thể đọc.

Đừng để debugger, logger, `toString()` hoặc recursive assertions vô tình initialize proxy trước khi test.
## 6. refresh(): đồng bộ managed state từ database

`EntityManager.refresh(entity)` tải lại state của một entity managed từ database mà transaction hiện tại nhìn thấy.

```java
Customer customer = em.find(Customer.class, 10L);
String databaseName = customer.getName();

customer.rename("Unsaved local change");

em.refresh(customer);

assertThat(customer.getName()).isEqualTo(databaseName);
```

Refresh thường yêu cầu entity managed, có thể phát sinh SELECT và ghi đè các thay đổi local chưa flush.

### 6.1. Refresh không phải merge

- Merge đưa state từ object detached vào managed instance.
- Refresh lấy state từ database và ghi đè managed instance.

Nếu user có local edits cần giữ, không gọi refresh như thao tác “reload an toàn”.

### 6.2. Test sau external update

Một kịch bản dùng JDBC:

```java
Customer customer = em.find(Customer.class, id);

jdbcTemplate.update(
    "update customers set name = ? where id = ?",
    "JDBC value",
    id
);

em.refresh(customer);

assertThat(customer.getName()).isEqualTo("JDBC value");
```

Điều kiện: JDBC và JPA phải dùng cùng transaction manager/DataSource và transaction-bound connection thích hợp nếu muốn cùng transaction nhìn thấy update. Nếu dùng transaction B riêng, commit B trước; transaction A phải có isolation cho phép nhìn thấy commit đó.

### 6.3. Isolation level ảnh hưởng refresh

Trong READ COMMITTED, statement tiếp theo thường có thể nhìn thấy commit mới của transaction khác. Trong REPEATABLE READ/snapshot isolation, transaction hiện tại có thể tiếp tục nhìn thấy snapshot cũ. Refresh không vượt qua isolation semantics của database.

Nếu mục tiêu là xác minh state mới nhất sau transaction khác, kết thúc transaction hiện tại và đọc trong transaction mới là cách rõ ràng hơn.
### 6.4. Refresh detached entity

Refresh yêu cầu managed entity. Gọi refresh trên detached entity có thể ném `IllegalArgumentException` theo JPA contract. Không dùng refresh để “reattach” object.

### 6.5. Cascade REFRESH và cache

`CascadeType.REFRESH` có thể lan operation tới associations. Refresh một entity không đồng nghĩa invalidate toàn bộ L1/L2/query cache, Redis hoặc search index. Kiểm tra behavior cache cụ thể theo provider/version.
## 7. Rollback: database state khác Java object state

Ví dụ service:

```java
@Transactional
public void changeThenFail(Long id) {
    Customer customer = em.find(Customer.class, id);

    customer.rename("Changed");
    em.flush();

    throw new IllegalStateException("Failure");
}
```

Spring mặc định rollback transaction với unchecked exception như `IllegalStateException`. Database UPDATE đã flush nhưng chưa commit sẽ được rollback. Object `customer` trong memory có thể vẫn giữ "Changed".
### 7.1. Rollback không undo Java object graph

Sau rollback:

- Database transaction changes được hoàn tác.
- Object Java có thể vẫn giữ field values mới.
- Persistence context có thể bị đóng/clear hoặc không còn thích hợp để tiếp tục dùng, tùy provider/integration.
- Lazy proxies có thể không còn Session.
- Generated identifiers/sequence values không nhất thiết quay lại.
- External effects không tự rollback.

Sau rollback hoặc flush failure, kết thúc context theo transaction manager và mở transaction mới để xác minh dữ liệu.

### 7.2. Không assert object tự quay về state cũ

Không viết test kiểu:

```java
customer.rename("Changed");
em.flush();

rollbackTransaction();

assertThat(customer.getName()).isEqualTo("Original");
```

JPA không bảo đảm object trong heap được khôi phục. Assert database state bằng một EntityManager mới.

### 7.3. Rollback trước và sau flush

Test cả hai tình huống:

- Exception trước flush: SQL có thể chưa được gửi.
- Exception sau flush: SQL đã gửi nhưng transaction rollback.

Cả hai có thể cho database state cuối giống nhau, nhưng giúp xác nhận flush timing và constraint behavior.
## 8. Spring rollback rules

Spring `@Transactional` mặc định rollback với unchecked exceptions (`RuntimeException`) và `Error`. Checked exceptions không mặc định trigger rollback nếu không có rule phù hợp.

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // ...
    throw new IOException("Import failed");
}
```

Nếu test kỳ vọng checked exception rollback, phải xác định `rollbackFor` hoặc transaction rules đang áp dụng.

### 8.1. Exception bị catch

```java
@Transactional
public void updateButCatch(Long id) {
    try {
        doSomethingThatFails(id);
    } catch (RuntimeException ex) {
        log.warn("Ignored", ex);
    }
}
```

Nếu exception bị bắt và method kết thúc bình thường, transaction interceptor có thể không rollback chỉ vì đã từng có exception. Tuy nhiên inner transaction scope có thể đã đánh dấu rollback-only; commit cuối cùng có thể ném `UnexpectedRollbackException`.

Test cần gọi qua transaction boundary thật và bắt kết quả ở bên ngoài boundary.
### 8.2. REQUIRED và rollback-only

Inner method propagation REQUIRED tham gia transaction ngoài. Nếu inner scope đánh dấu rollback-only, outer method có thể kết thúc bình thường nhưng transaction cuối vẫn rollback. Không chỉ assert exception đã được catch bên trong.
## 9. Kiểm thử persist và commit với transaction boundary rõ

`@DataJpaTest` thường chạy test trong transaction và rollback khi kết thúc. Điều này tốt cho isolation nhưng không tự chứng minh dữ liệu đã commit.

Có thể dùng `TransactionTemplate` để kiểm soát:

```java
@Autowired
PlatformTransactionManager transactionManager;

@Autowired
CustomerRepository repository;

@Test
void committedEntityIsVisibleInNewTransaction() {
    TransactionTemplate tx =
        new TransactionTemplate(transactionManager);

    Long id = tx.execute(status -> {
        Customer customer = new Customer("An");
        repository.save(customer);
        return customer.getId();
    });

    String name = tx.execute(status ->
        repository.findById(id)
            .orElseThrow()
            .getName()
    );

    assertThat(name).isEqualTo("An");
}
```

Đây là skeleton minh họa. Nếu repository/service đã quản lý transaction, dùng đúng Spring proxy và transaction manager của persistence unit. Tránh tự tạo EntityManager không tham gia transaction-bound context ngoài ý muốn.

### 9.1. Dùng ID thay entity qua transaction boundary

Lưu ID trước khi transaction kết thúc. Entity trả ra từ transaction cũ trở thành detached; dùng ID để load lại trong transaction mới.

### 9.2. Không đọc lại bằng EntityManager cũ

Nếu context vẫn quản lý object, find có thể trả L1 instance. Context mới giúp test kiểm tra trạng thái sau commit.

Nếu L2 cache bật và mục tiêu là database state tuyệt đối, disable/evict cache trong test hoặc dùng JDBC connection phù hợp để xác minh.

## 10. Kiểm thử merge với hai persistence contexts

Một test merge cần một entity detached từ context cũ:

```java
Customer detached = loadCustomerAndDetach(id);
detached.rename("Merged name");

Customer managed = transactionTemplate.execute(status -> {
    Customer result = em.merge(detached);

    assertThat(em.contains(result)).isTrue();
    assertThat(em.contains(detached)).isFalse();

    em.flush();
    return result;
});
```

Đây là pseudo-code: `loadCustomerAndDetach` phải thực sự kết thúc/detach context trước; `em` phải là transaction-bound EntityManager trong transaction callback phù hợp.

Sau commit, mở transaction mới và xác minh persisted value.

### 10.1. Kiểm tra optimistic locking

Nếu entity có `@Version`, detached state cũ được merge sau khi transaction khác cập nhật có thể gây optimistic locking failure lúc merge/flush/commit. Bắt lỗi quanh toàn transaction boundary, sau đó xác minh winner state từ context mới.

### 10.2. Merge không phải giải pháp cho partial update

Nếu DTO thiếu field, mapper có thể tạo null values và merge ghi đè state. Với API PATCH, load managed entity và apply chính xác fields được gửi, có authorization và validation.

## 11. Kiểm thử optimistic locking với hai contexts

Entity có optimistic version:

```java
@Version
private long version;
```

Kịch bản:

```text
T1 loads Customer(version=1)
T2 loads Customer(version=1)
T1 changes and commits -> version=2
T2 changes stale copy -> version conflict
T2 rolls back
T3 loads final state -> sees T1's committed value
```

Hai lần find trong cùng EntityManager không mô phỏng hai transactions; chúng có thể trả cùng managed object. Dùng hai EntityManagers và transaction boundaries độc lập, rồi verify bằng context thứ ba.

### 11.1. Exception có thể xuất hiện ở flush hoặc commit

Optimistic locking failure có thể được phát hiện khi Hibernate gửi UPDATE với version predicate. Nếu flush xảy ra lúc commit, exception có thể xuất hiện tại transaction completion. Test nên bao trọn transaction execution và assert ở boundary phù hợp.

### 11.2. Kiểm tra state thắng bằng context mới

Sau khi transaction thua rollback, mở transaction thứ ba, load entity và xác nhận giá trị/version của transaction thắng. Không dùng detached object của transaction thất bại làm nguồn sự thật.

## 12. Kiểm thử collection changes và orphanRemoval

Mapping:

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<Address> addresses = new ArrayList<>();
```

Xóa child khỏi managed collection có thể đánh dấu orphan để xóa khi flush. Test cần:

1. Persist parent/child và commit.
2. Mở context mới, load parent và collection.
3. Remove child, flush.
4. Commit.
5. Đọc DB trong context mới và xác nhận row đã xóa.
6. Lặp lại với rollback và xác nhận row vẫn còn.

Collection Java có thể đã mất child ngay cả khi transaction rollback; không assert memory state thay cho DB state.

### 12.1. Owning side vẫn quan trọng

Với bidirectional OneToMany, collection thường là inverse side còn ManyToOne child là owning side. Khi remove/add child, cập nhật helper method ở cả hai phía để object graph và FK không lệch nhau.

### 12.2. Cascade REMOVE và orphanRemoval không giống nhau

Cascade REMOVE lan lệnh remove từ parent sang child khi parent bị xóa. Orphan removal đánh dấu child bị loại khỏi relationship là orphan theo mapping. Test hai behavior riêng và xác minh rows sau flush/commit/rollback.

## 13. Kiểm thử bulk DML và native SQL riêng

Bulk HQL/JPQL UPDATE/DELETE và native SQL không đi qua per-entity dirty checking giống managed entity changes.

```java
int changed = em.createQuery("""
    update Customer c
    set c.active = false
    where c.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
```

Không dùng `entityUpdateCount` hoặc callback expectations của managed updates để kết luận bulk DML đã được audit như từng entity. Bulk DML có thể làm persistence context stale; flush trước và clear/refresh sau bulk theo chủ đích. Test native/JDBC path riêng nếu ứng dụng sử dụng.

### 13.1. Verify row count và context state

Assert giá trị trả về từ `executeUpdate()` theo contract của query, rồi mở/clear persistence context trước khi đọc entity lại. Một managed instance đã được load trước bulk update có thể vẫn chứa state cũ.

### 13.2. Rollback bulk mutation

Thực hiện bulk DML trong transaction rồi đánh dấu rollback. Sau transaction boundary, query trong context mới để xác nhận database state không thay đổi.
## 14. Kiểm thử constraint violation tại flush

Ví dụ hai rows vi phạm unique constraint:

```java
repository.save(new Customer("same@example.com"));
repository.save(new Customer("same@example.com"));

em.flush();
```

Exception có thể được wrap bởi Hibernate/Spring và transaction có thể ở trạng thái failed/rollback-only. Kết thúc transaction trước khi query tiếp; không reuse persistence context như thể chỉ một statement thất bại riêng lẻ.

Test nên:

- Tạo fixture trước trong transaction riêng.
- Thực hiện mutation gây vi phạm.
- Flush ở vị trí muốn quan sát lỗi.
- Bắt exception quanh transaction boundary.
- Mở transaction mới và xác minh không có rows được commit.

## 15. Rollback và generated identifiers

Sequence allocation thường không transactional giống row data. Một transaction rollback có thể để lại ID gap. Hibernate pooled optimizers có thể cấp block IDs và khiến gap lớn hơn.

**Không test rằng ID tiếp theo phải bằng ID vừa rollback cộng một.** Test uniqueness, row existence và identity semantics phù hợp.

## 16. Rollback không hoàn tác external side effects

Một service có thể update DB rồi gửi email, publish Kafka message, gọi HTTP service hoặc ghi object storage. Database rollback không thu hồi các side effects đó.

Nếu side effect chỉ được phép xảy ra sau commit, dùng transaction synchronization/after-commit listener hoặc transactional outbox để ghi event cùng DB transaction rồi publish với retry/idempotency.

Test rollback cần xác minh cả DB state lẫn side effects theo thiết kế ứng dụng.
## 17. Spring @DataJpaTest và transaction test-managed

`@DataJpaTest` thường:

- Tạo JPA test slice.
- Dùng embedded DB nếu dependencies/configuration cho phép.
- Chạy test trong transaction.
- Rollback transaction test khi kết thúc.
- Cung cấp `TestEntityManager` trong cấu hình Spring Boot tương ứng.

Ví dụ:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    TestEntityManager testEntityManager;

    @Autowired
    CustomerRepository repository;

    @Test
    void persistFlushFind() {
        Customer customer = new Customer("An");

        Customer result =
            testEntityManager.persistFlushFind(customer);

        assertThat(result.getName()).isEqualTo("An");
    }
}
```

`persistFlushFind` giúp persist, flush và tìm lại theo tiện ích TestEntityManager. Test vẫn nằm trong transaction test-managed và thường rollback khi kết thúc; nó không tự chứng minh commit bền vững.

### 17.1. Khi cần kiểm thử commit thật

Có thể dùng `TransactionTemplate` với transaction boundary riêng, `TestTransaction.flagForCommit()/end()` trong Spring Test, hoặc một test không có transaction ngoài gọi service transaction qua Spring proxy.

Không thêm `@Commit` vào mọi test chỉ để assertion qua được; commit có thể làm test data leak và ảnh hưởng tests sau.

### 17.2. TestTransaction

```java
Long id = customer.getId();

TestTransaction.flagForCommit();
TestTransaction.end();

TestTransaction.start();

Customer reloaded = em.find(Customer.class, id);
assertThat(reloaded.getName()).isEqualTo("An");
```

Đây là mẫu minh họa. Lưu scalar ID trước khi kết thúc transaction, bảo đảm context mới phù hợp và không tiếp tục dùng entity cũ.

### 17.3. @Commit và @Rollback(false)

Có thể commit test transaction bằng `@Commit`/`@Rollback(false)`, nhưng cần cleanup dữ liệu. Nếu test không cần commit thật, rollback mặc định giúp isolation tốt hơn.

## 18. TransactionTemplate và propagation

`TransactionTemplate` giúp tạo ranh giới transaction tường minh. Tuy nhiên nếu test đã có transaction và template dùng REQUIRED, nó có thể tham gia transaction ngoài. Phải biết test đang chạy trong transaction nào.

Một pattern:

1. Test không có outer transaction.
2. TransactionTemplate thực hiện mutation.
3. Callback hoàn tất commit/rollback.
4. TransactionTemplate thứ hai mở context mới để verify.

Ví dụ rollback chủ động:

```java
transactionTemplate.executeWithoutResult(status -> {
    Customer customer = repository.findById(id)
        .orElseThrow();

    customer.rename("Temporary");
    em.flush();

    status.setRollbackOnly();
});
```

Sau callback, mở transaction mới và xác nhận database vẫn giữ giá trị cũ.

### 18.1. Không trộn transaction ngoài mà không chủ ý

Nếu test method đã có `@Transactional`, TransactionTemplate mặc định REQUIRED có thể tham gia transaction test thay vì tạo boundary độc lập. Dùng test không transactional hoặc propagation được lựa chọn có chủ đích.

### 18.2. Gọi service qua Spring proxy

Nếu test cần kiểm tra `@Transactional` trên service, inject bean Spring thật và gọi qua proxy. Tự tạo object bằng `new` hoặc gọi nội bộ trong cùng bean có thể bỏ qua proxy interception.

### 18.3. REQUIRES_NEW và self-invocation

```java
@Service
public class ImportService {

    public void importAll() {
        saveOne(); // self-invocation
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOne() {
        // ...
    }
}
```

Với proxy-based Spring AOP, lời gọi nội bộ thường không đi qua proxy; REQUIRES_NEW có thể không được áp dụng như mong đợi. Đặt boundary ở bean khác hoặc cấu trúc phù hợp và test public call path.

## 19. Kiểm thử transaction rollback trong Spring service

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final EntityManager em;

    @Transactional
    public void renameThenFail(Long id) {
        Customer customer = repository.findById(id)
            .orElseThrow();

        customer.rename("Changed");
        em.flush();

        throw new IllegalStateException("force rollback");
    }
}
```

Test gọi qua Spring bean:

```java
@Test
void serviceFailureRollsBackDatabaseChange() {
    assertThatThrownBy(
        () -> customerService.renameThenFail(10L)
    ).isInstanceOf(IllegalStateException.class);

    String name = transactionTemplate.execute(status ->
        repository.findById(10L)
            .orElseThrow()
            .getName()
    );

    assertThat(name).isEqualTo("Original");
}
```

### 19.1. Tránh outer transaction che kết quả

Nếu test method có `@Transactional`, service REQUIRED có thể tham gia transaction ngoài. Khi service ném exception, transaction test có thể rollback-only; query verification trong cùng context không chứng minh state sau commit.

Thiết kế test không có transaction ngoài, hoặc chủ động kết thúc transaction trước khi verify trong context mới.

### 19.2. Exception ở commit boundary

Một số lỗi chỉ xuất hiện lúc commit như deferred constraints, serialization failures hoặc optimistic lock conflict. Assertion phải bao trọn transaction completion, không chỉ thân method trước khi proxy commit.

## 20. L1/L2 cache khi xác minh

- **L1 cache:** thuộc EntityManager/Session; find lại có thể trả cùng object.
- **L2 cache:** có thể cung cấp entity state cho EntityManager mới.
- **Query cache:** cache kết quả query cacheable theo Hibernate configuration.

```java
em.clear(); // detach managed entities
```

không evict L2. `Statistics.clear()` reset counters, cũng không clear persistence context/cache.

Nếu test cần xác minh DB state tuyệt đối, kiểm soát cache (disable/evict) hoặc đọc bằng JDBC connection phù hợp. Không dùng một EntityManager cũ làm nguồn sự thật sau rollback.

### 20.1. Refresh và cache ngoài ORM

Refresh một entity managed không tự invalidate Redis, HTTP cache, search index hoặc read model. Nếu ứng dụng có các tầng cache khác, test invalidation/synchronization theo transaction commit riêng.

## 21. Test lazy proxy và association sau detach

```java
Customer customer = em.find(Customer.class, id);
Department department = customer.getDepartment();

assertThat(Hibernate.isInitialized(department)).isFalse();

em.detach(customer);
```

Nếu proxy chưa initialized và không còn Session, gọi getter cần tải dữ liệu có thể ném `LazyInitializationException`. Nếu đã initialized, state trong memory có thể đọc được.

Debugger evaluation, logging, `toString()` hoặc recursive assertions có thể tự initialize association và làm test sai mục tiêu.

OSIV có thể giữ Session tới lúc render HTTP response, che lazy-loading problems. Xác định cấu hình OSIV và ưu tiên DTO mapping trong transaction service khi phù hợp.

## 22. Test bulk DML và native SQL riêng

Bulk HQL/JPQL UPDATE/DELETE và native SQL không đi qua per-entity dirty checking giống managed entity changes.

```java
int changed = em.createQuery("""
    update Customer c
    set c.active = false
    where c.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
```

Không dùng `entityUpdateCount` hoặc callback expectations của managed updates để kết luận bulk DML đã được audit như từng entity. Bulk DML có thể làm persistence context stale; flush trước và clear/refresh sau bulk theo chủ đích. Test native/JDBC path riêng nếu ứng dụng sử dụng.

### 22.1. Verify row count và context state

Assert giá trị trả về từ `executeUpdate()` theo contract của query, rồi mở/clear persistence context trước khi đọc entity lại. Một managed instance đã được load trước bulk update có thể vẫn chứa state cũ.

### 22.2. Rollback bulk mutation

Thực hiện bulk DML trong transaction rồi đánh dấu rollback. Sau transaction boundary, query trong context mới để xác nhận database state không thay đổi.
## 23. Những điều không nên assert

Không dựa vào các giả định sau:

- INSERT luôn chạy ngay ở `persist()`.
- `merge()` trả đúng object input.
- Object detached trở thành managed sau merge.
- `detach()` undo SQL đã flush.
- `clear()` rollback transaction.
- `refresh()` thấy commit của transaction khác bất kể isolation.
- Rollback tự khôi phục Java fields.
- Sequence ID không có gap sau rollback.
- L2 cache luôn bị xóa bởi refresh.
- Mọi constraint error xuất hiện tại persist thay vì flush/commit.
- Optimistic locking error luôn xuất hiện đúng ở một dòng cụ thể.
- `@DataJpaTest` mặc định chứng minh commit.
- EntityManager luôn có thể dùng tiếp sau rollback/flush failure.

Assert các hợp đồng JPA, transaction outcome và database state mà use case cần.

## 24. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách kiểm tra |
|---|---|---|
| Assert object sau persist là DB đã ghi | Object vẫn có thể chỉ ở L1 | Commit và load context mới |
| Bỏ qua return value của merge | Input vẫn detached | Dùng managed copy |
| Merge DTO thiếu fields | Null có thể overwrite state | Load managed entity và apply patch |
| Persist detached entity | Sai lifecycle operation | Chọn merge hoặc load/update |
| Nghĩ detach undo flush | SQL đã thuộc transaction | Tách detach khỏi rollback |
| Nghĩ clear rollback | Clear chỉ detach objects | Rollback qua transaction manager |
| Refresh detached object | Refresh yêu cầu managed | Load context mới hoặc merge đúng use case |
| Refresh rồi giữ local edits | Refresh có thể overwrite | Xác định source of truth |
| Nghĩ rollback undo Java heap | Database và object memory khác nhau | Query DB trong context mới |
| Assert ID liên tiếp | Sequence allocation có thể gap | Assert identity/row existence |
| Test chỉ có outer @Transactional | Chưa commit thật | Boundary riêng |
| Catch lỗi rồi query cùng transaction | Transaction có thể failed/rollback-only | Kết thúc transaction trước |
| Không flush constraint test | Lỗi chưa xảy ra | Flush có chủ đích |
| Find lại cùng EntityManager | Có thể hit L1 | Clear/new EntityManager |
| Bỏ qua L2 cache | Context mới vẫn có thể cache hit | Evict/disable hoặc JDBC verify |
| Không kiểm tra lazy initialized | Test vô tình tải association | Hibernate.isInitialized |
| Gọi transactional method qua self-invocation | Có thể bypass proxy | Gọi qua Spring bean proxy |
| Gửi email trước commit | Rollback không thu hồi email | Outbox/after-commit |
| Dùng embedded DB cho locking test | Semantics khác production | Test DB tương đương |
| Dùng entityUpdateCount cho bulk rows | Bulk bypass lifecycle | Dùng executeUpdate/DB metrics |
## 25. Bài tập thực hành

### Bài tập 1: persist và flush

```java
Customer customer = new Customer("An");
em.persist(customer);
assertThat(em.contains(customer)).isTrue();
em.flush();
```

**Câu hỏi:** Sau flush transaction đã commit chưa?

**Đáp án:** Chưa. SQL có thể đã gửi nhưng transaction vẫn rollback được. Commit và đọc từ context mới để chứng minh persistence bền vững.

### Bài tập 2: merge return value

```java
Customer detached = loadDetached();
detached.rename("New");
em.merge(detached);
assertThat(em.contains(detached)).isTrue();
```

**Câu hỏi:** Assertion cuối đúng không?

**Đáp án:** Không. Dùng giá trị trả về của merge; input vẫn detached.

### Bài tập 3: detach sau flush

```java
customer.rename("A");
em.flush();
em.detach(customer);
customer.rename("B");
```

**Câu hỏi:** Nếu transaction commit, giá trị nào được lưu?

**Đáp án:** "A" đã flush thuộc transaction; "B" sau detach không tự dirty-check. Nếu rollback, "A" cũng không được commit.

### Bài tập 4: refresh

```java
customer.rename("Local");
em.refresh(customer);
```

**Câu hỏi:** Có giữ "Local" không?

**Đáp án:** Không nên kỳ vọng. Refresh ghi đè managed state bằng dữ liệu database mà transaction hiện tại nhìn thấy.

### Bài tập 5: rollback sau flush

```java
customer.rename("Changed");
em.flush();
throw new IllegalStateException();
```

**Câu hỏi:** Java object có chắc quay về tên cũ?

**Đáp án:** Không. Database rollback, object trong heap có thể vẫn là "Changed". Mở context mới để xác minh.

### Bài tập 6: checked exception

Một `@Transactional` method persist entity rồi ném `IOException`.

**Câu hỏi:** Spring mặc định rollback không?

**Đáp án:** Mặc định rollback với unchecked exceptions và Error. Checked exception cần rollback rule như `rollbackFor` nếu muốn rollback.

### Bài tập 7: lazy collection sau detach

Load Customer nhưng không initialize `addresses`, đóng context rồi gọi `addresses.size()`.

**Đáp án:** Hibernate thường ném `LazyInitializationException` vì collection cần Session để tải. Nếu đã initialized, state trong memory vẫn có thể đọc.

### Bài tập 8: sequence sau rollback

Persist entity có sequence ID, flush rồi rollback. Test yêu cầu ID tiếp theo bằng ID vừa rollback + 1.

**Đáp án:** Assertion không hợp lệ. Sequence allocation có thể không rollback và Hibernate optimizer có thể cấp block IDs.
## 26. Checklist kiểm thử lifecycle và transaction

1. Entity đang new, managed, detached hay removed?
2. EntityManager/Session nào đang quản lý nó?
3. Merge return value đã được dùng chưa?
4. Persist chỉ áp dụng cho entity mới?
5. Cascade operation nào đang được cấu hình?
6. Owning side của association có được cập nhật?
7. Test cần flush tại thời điểm nào?
8. Mục tiêu cần commit thật hay chỉ test trong transaction?
9. Rollback có được verify bằng context mới?
10. Có tránh giả định rollback undo Java object graph?
11. Detach và clear có được phân biệt?
12. Refresh target còn managed không?
13. Refresh có thể ghi đè local changes không?
14. DTO partial update có thể overwrite fields khi merge?
15. Lazy proxy/collection đã initialized chưa?
16. L1 cache có che database read không?
17. L2/query cache có cần disable/evict?
18. Constraint test đã flush chưa?
19. Sau lỗi, transaction có được kết thúc trước query tiếp?
20. Checked/unchecked rollback rules có rõ?
21. Propagation REQUIRED/REQUIRES_NEW có đúng?
22. Test gọi Spring bean qua proxy khi cần?
23. Test-managed transaction có rollback cuối test?
24. Commit verification dùng transaction mới?
25. Generated IDs có tránh giả định không có gaps?
26. Optimistic locking dùng hai persistence contexts?
27. Bulk/native DML có được test riêng?
28. External side effects có được xử lý sau commit/outbox?
29. Database test có tương đương production khi cần?
30. Cleanup có xử lý dữ liệu commit trong test?

## 27. Ghi nhớ

- **`persist()`** đưa entity mới vào persistence context; INSERT có thể chờ flush/commit, tùy identifier strategy.
- **`merge()`** copy state vào managed instance và trả instance đó; input vẫn detached.
- Dùng **return value của merge()**, không dùng detached request object như managed entity.
- **`detach()`** ngừng dirty checking; không undo SQL đã flush.
- **`clear()`** detach mọi managed entity; không rollback transaction và không evict L2 cache.
- **`refresh()`** reload state của managed entity theo dữ liệu database mà transaction hiện tại nhìn thấy; local edits có thể bị ghi đè.
- **`flush()` khác commit**; SQL có thể đã chạy nhưng transaction vẫn rollback.
- **Rollback khôi phục database transaction, không bảo đảm khôi phục Java object graph** trong memory.
- Sau rollback hoặc flush failure, kết thúc context phù hợp và verify bằng transaction mới.
- Spring mặc định rollback unchecked exceptions/Error; checked exceptions cần rule thích hợp.
- Cascade PERSIST/MERGE/DETACH/REFRESH/REMOVE phải được test theo association; cascade không thay owning-side mapping.
- Lazy proxy/collection chưa initialized có thể không truy cập được sau detach/close.
- Test cùng EntityManager dễ bị L1 cache che; dùng flush/clear hoặc context mới.
- `@DataJpaTest` thường rollback test transaction cuối test; không tự chứng minh commit.
- `TransactionTemplate`/`TestTransaction` giúp điều khiển transaction boundaries; hiểu propagation nếu test có outer transaction.
- Optimistic locking cần hai transactions/contexts độc lập và verify winner state từ context mới.
- Sequence/ID allocation có thể có gaps sau rollback.
- Database rollback không thu hồi email, messages, HTTP calls hoặc cache ngoài transaction; dùng after-commit/outbox khi cần.

**Kết luận:** Kiểm thử Hibernate lifecycle đáng tin khi tách rõ **trạng thái object, persistence context và kết quả transaction trong database**. `persist` quản lý entity mới; `merge` trả managed copy; `detach` ngừng dirty checking; `refresh` ghi đè managed state theo database; rollback hoàn tác transaction nhưng không quay ngược Java heap. Dùng flush để kích hoạt SQL/constraints đúng thời điểm, đọc lại bằng context mới để xác minh commit/rollback, và kiểm thử qua transaction boundaries thật của Spring.

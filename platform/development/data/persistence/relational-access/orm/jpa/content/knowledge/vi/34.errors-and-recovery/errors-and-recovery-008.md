# Không tiếp tục dùng ngữ cảnh lỗi khi chưa xác định trạng thái an toàn trong JPA

Trong **Jakarta Persistence (JPA)**, một lần gọi `EntityManager.persist()`, `flush()`, `createQuery()` hoặc transaction `commit()` có thể ném exception. Khi đó câu hỏi không chỉ là **“lỗi gì?”**, mà còn là:

> **“Persistence context, transaction và những entity objects đang giữ có còn ở trạng thái đủ tin cậy để tiếp tục hay không?”**

Đây là điểm dễ gây lỗi dây chuyền. Một ứng dụng có thể bắt `PersistenceException`, ghi log và tiếp tục gọi `em.find()` hoặc `repository.save()` trong **cùng transaction**. Tuy nhiên transaction có thể đã bị đánh dấu **rollback-only**, JDBC connection đang ở trạng thái lỗi, provider đã thực hiện một phần thao tác trong persistence context, hoặc entity trong Java đã mang ID/version/field values không còn phản ánh database sau rollback.

Ví dụ:

```java
try {
    entityManager.flush();
} catch (PersistenceException ex) {
    log.warn("Lưu thất bại", ex);
}

// Rủi ro: transaction/context có thể không còn an toàn.
entityManager.persist(anotherEntity);
```

Chỉ vì biến `entityManager` chưa bị `null`, hoặc `entityManager.isOpen()` vẫn trả `true`, **không có nghĩa đơn vị công việc đang lỗi có thể tiếp tục ghi như chưa có chuyện gì**.

Bài thuộc chương **Lỗi và phục hồi**, chủ đề **Data Persistence Relational Access ORM JPA**, với đề bài trực tiếp **“Không tiếp tục dùng ngữ cảnh lỗi khi chưa xác định trạng thái an toàn”**.

Bài sẽ phân tích:

- Các tầng cần đánh giá sau lỗi: transaction, persistence context, entity instances và JDBC resources.
- Khi nào ngoại lệ chỉ mang nghĩa kết quả truy vấn, khi nào giao dịch phải rollback.
- Sự khác nhau giữa `isOpen()`, `isActive()`, `contains()` và **trạng thái an toàn**.
- Vì sao `clear()`, `detach()`, `refresh()` và `merge()` không phải lệnh “chữa” transaction đã hỏng.
- Cách kết thúc đơn vị công việc ở JPA resource-local, Jakarta Transactions/JTA và Spring.
- Cách retry **bằng transaction/context mới**, với idempotency và giới hạn rõ.
- Các tình huống `UNIQUE`, foreign key, optimistic/pessimistic locks, flush failure và commit outcome không xác định.
- Ví dụ code, integration test, sơ đồ ra quyết định và bài tập có lời giải.

**Nguyên tắc cốt lõi:** *Khi xảy ra lỗi persistence có thể ảnh hưởng giao dịch, hãy dừng thay đổi, xác định outcome, rollback nếu cần, không tái sử dụng context/managed state của attempt đã lỗi, rồi mới quyết định có khởi tạo đơn vị công việc mới để phục hồi hay không.*

---

## 1. Persistence context không phải một kết nối SQL đơn thuần

Một thao tác JPA liên quan ít nhất bốn lớp:

```text
Application code
      |
      v
EntityManager API
      |
      v
Persistence context
  - identity map
  - managed entities
  - pending changes
  - snapshots / versions
      |
      v
Transaction coordination
  - active / rollback-only
  - flush / commit / rollback
      |
      v
JDBC provider / connection / database
  - SQL statements
  - constraints and locks
  - committed or uncommitted rows
```

Khi gặp lỗi, **không thể chỉ nhìn một lớp**.

Ví dụ:

1. Entity `PurchaseOrder` đã chuyển từ `DRAFT` sang `CONFIRMED` trong Java.
2. `flush()` gửi SQL `UPDATE` và có thể cập nhật version/snapshot theo provider.
3. Một câu SQL khác thất bại vì foreign key.
4. Transaction rollback.
5. Java object vẫn có thể hiển thị `CONFIRMED` hoặc generated state khác database.
6. Sử dụng tiếp object đó cho một nghiệp vụ mới có thể gây quyết định sai.

### 1.1. Bốn câu hỏi bắt buộc

| Lớp | Câu hỏi sau lỗi |
| --- | --- |
| Giao dịch | Còn active không? Có rollback-only không? Commit có chắc thành công không? |
| Persistence context | Còn được quản lý không? Có pending changes/snapshots đáng tin không? |
| Entity object | ID/version/field values có còn đúng với database không? |
| Database/JDBC | Statement bị rollback hay toàn transaction? Connection có usable không? |

Một lời gọi thành công như `isOpen()` chỉ trả lời **một phần rất nhỏ** của các câu hỏi trên.

### 1.2. “Ngữ cảnh lỗi” là gì?

Trong bài này, *ngữ cảnh lỗi* là một **persistence context hoặc đơn vị công việc đang chịu ảnh hưởng của một failure mà transaction/state chưa được xác nhận an toàn**.

Không có một JPA API portable duy nhất tên `isPersistenceContextSafe()` để xác nhận tất cả các điều kiện. Vì vậy, với các lỗi persistence nghiêm trọng, phương án thiết kế rõ ràng thường là:

```text
Failure
   |
   v
Stop current unit of work
   |
   v
Rollback if required/possible
   |
   v
Release/discard affected persistence context
   |
   v
Start a NEW transaction and NEW persistence context
   |
   v
Reload current database state
   |
   v
Re-evaluate business operation
```

---

## 2. EntityManager.isOpen() không chứng minh transaction khỏe

Một EntityManager application-managed có thể còn mở sau khi transaction thất bại:

```java
boolean open = em.isOpen();
```

Giá trị `true` có nghĩa EntityManager chưa bị `close()` theo lifecycle API tương ứng. Nó **không có nghĩa**:

- Transaction còn hợp lệ để commit.
- JDBC connection còn sử dụng được.
- Database đã hoàn tác mọi thứ trong Java heap.
- Managed entities đã được refresh.
- Pending changes không còn.
- Persistence context có thể tái sử dụng an toàn cho cùng nghiệp vụ.
- Lần `flush()` tiếp theo sẽ thành công.

### 2.1. EntityManager còn mở nhưng giao dịch rollback-only

```text
EntityManager.isOpen() -> true
Transaction marked rollback-only
EntityManager.flush() -> có thể tiếp tục báo lỗi
Transaction.commit() -> sẽ không commit thành công
```

Không nên xem EntityManager mở là dấu hiệu cần **thử tiếp một lần nữa trong cùng transaction**.

### 2.2. isActive() không đủ

Với RESOURCE_LOCAL:

```java
boolean active =
    em.getTransaction().isActive();
```

Một transaction có thể vẫn active về mặt API nhưng đang **rollback-only**.

JPA `EntityTransaction` có:

```java
em.getTransaction().getRollbackOnly();
```

Khi transaction đã được đánh dấu rollback-only, không tiếp tục business write và mong `commit()` thành công.

### 2.3. contains() cũng không đủ

```java
boolean managed = em.contains(order);
```

Lời gọi kiểm tra instance có đang được context quản lý hay không. Nó **không chứng minh state đó đúng với database** hoặc transaction đang có thể commit.

### 2.4. Một bảng kiểm tra đúng ý nghĩa

| API/quan sát | Trả lời được gì? | Không trả lời được gì? |
| --- | --- | --- |
| `em.isOpen()` | EM chưa đóng theo lifecycle | Transaction/persistence state an toàn |
| `tx.isActive()` | Transaction resource-local đang active | Có rollback-only hay không |
| `tx.getRollbackOnly()` | Transaction bị đánh dấu rollback-only | Managed objects đã nhất quán với DB hay chưa |
| `em.contains(entity)` | Membership trong context | Field/version còn đúng sau failure |
| `em.find(...)` trả object | Có object phù hợp identity | Object là dữ liệu mới nhất |
| `flush()` thành công | Pending SQL được đồng bộ ở mốc đó | Transaction đã commit bền vững |
| `commit()` trả thành công | Transaction hoàn tất theo contract | External side effect cũng đã giao thành công |

Không kết hợp các phép kiểm tra trên để phát minh một định nghĩa “ngữ cảnh chắc chắn an toàn” cho mọi provider sau SQL failure.

---

## 3. Phân loại ngoại lệ trước khi quyết định có tiếp tục

Không phải **mọi** exception từ JPA đều tự động làm hỏng toàn transaction. Cần phân loại có ngữ cảnh.

### 3.1. Những ngoại lệ truy vấn thường mang nghĩa kết quả

```java
jakarta.persistence.NoResultException
jakarta.persistence.NonUniqueResultException
```

Theo semantics JPA, những exception này thông thường **không khiến transaction bị đánh dấu rollback chỉ bởi bản thân chúng**.

Ví dụ:

```java
try {
    PurchaseOrder order = em.createQuery(
        """
        SELECT o FROM PurchaseOrder o
        WHERE o.orderCode = :code
        """,
        PurchaseOrder.class
    )
    .setParameter("code", "UNKNOWN")
    .getSingleResult();

} catch (NoResultException ex) {
    // Không có bản ghi: có thể là tình huống nghiệp vụ.
}
```

Nếu ứng dụng dự kiến “không tìm thấy”, nên cân nhắc `getResultList()`, `Optional` hoặc API `getSingleResultOrNull()` khi phiên bản Jakarta Persistence hỗ trợ.

**Cần phân biệt JPA contract với Spring rollback rules:** một unchecked exception thoát khỏi phương thức `@Transactional` có thể làm Spring đánh dấu transaction rollback theo chính sách mặc định, dù JPA exception riêng lẻ không yêu cầu điều đó.

### 3.2. QueryTimeoutException và LockTimeoutException

```java
jakarta.persistence.QueryTimeoutException
jakarta.persistence.LockTimeoutException
```

Theo JPA semantics, các exception này được sử dụng cho tình huống **statement-level rollback**, khi transaction không bị đánh dấu rollback chỉ vì thất bại tại statement đó.

Tuy nhiên:

- Framework có thể áp rollback policy riêng.
- Provider/DB có thể bọc lỗi khác nếu toàn transaction cần rollback.
- Một database có thể ở trạng thái không thể thực hiện statement tiếp nếu SQL exception đã làm transaction aborted.
- Không nên suy luận chỉ từ class name mà bỏ qua status và cause chain.

### 3.3. Lỗi cần coi transaction đã hỏng hoặc phải kết thúc

Ví dụ:

- `OptimisticLockException`.
- `PessimisticLockException` theo semantics transaction-level failure.
- SQL constraint violation dẫn tới statement/transaction failure.
- Deadlock hoặc serialization failure.
- `RollbackException`.
- Persistence error khi flush/commit.
- DB connection failure.
- Transaction đã rollback-only.
- Commit outcome không xác định.

Với các lỗi này, mặc định an toàn là **không tiếp tục dùng unit of work đang lỗi**.

### 3.4. Bảng quyết định ban đầu

| Lỗi | Có luôn cần bỏ mọi context? | Hành động thực tế |
| --- | --- | --- |
| `NoResultException` | Không theo JPA chỉ vì exception này | Xử lý not-found, kiểm tra framework transaction policy |
| `NonUniqueResultException` | Không theo JPA chỉ vì exception này | Sửa query/cardinality/invariant |
| `IllegalArgumentException` do query parameter | Tùy thao tác; thường bug lập trình | Sửa code, đừng retry mù |
| `QueryTimeoutException` | Cần xác minh statement/tx status | Dừng/rollback nếu policy yêu cầu |
| `LockTimeoutException` | Cần xác minh statement/tx status | Kiểm tra lock, rollback/retry có điều kiện |
| `OptimisticLockException` | **Không dùng tiếp transaction lỗi** | Rollback, transaction/context mới |
| `PessimisticLockException` | **Không dùng tiếp transaction lỗi** | Rollback, phân tích lock |
| `ConstraintViolationException` từ DB | Thường không an toàn để tiếp tục | Rollback, phân loại constraint |
| Deadlock/serialization failure | **Transaction attempt đã thất bại** | Rollback, retry unit of work mới nếu an toàn |
| `RollbackException` lúc commit | **Không coi attempt đã commit** | Xác minh outcome, không reuse state |
| Mất kết nối khi commit | Có thể không xác định commit outcome | Idempotency + reconciliation |

**Ngoại lệ có thể không đánh dấu rollback** không đồng nghĩa mọi subsequent write trong mọi runtime đều an toàn. Quyết định vẫn phải tính đến transaction manager và DB driver.

---

## 4. Persistence context theo transaction và application-managed context

Phạm vi của persistence context ảnh hưởng cách cleanup sau failure.

### 4.1. Transaction-scoped context

Trong Jakarta EE:

```java
@PersistenceContext(
    type = PersistenceContextType.TRANSACTION
)
private EntityManager em;
```

Context thường được gắn với transaction. Khi transaction kết thúc, context transaction-scoped đó kết thúc.

Trong Spring JPA, EntityManager được inject thường là **proxy** điều phối tới transaction-bound EntityManager/context, không phải một persistence context singleton toàn ứng dụng.

Khi một transaction fail và Spring/JTA rollback, framework chịu trách nhiệm giải phóng transaction-bound resources theo lifecycle của nó.

### 4.2. Application-managed context

Java SE/RESOURCE_LOCAL:

```java
EntityManager em = emf.createEntityManager();
```

EntityManager được ứng dụng tạo và phải được close. Một EntityManager application-managed có thể tồn tại qua các transactions trong tình huống bình thường, **nhưng không nên xem đó là lý do để tái sử dụng sau failure nghiêm trọng**.

### 4.3. Extended persistence context

Extended context có thể giữ managed state qua nhiều transactions, ví dụ trong một stateful Jakarta EE component.

Điều này càng đòi hỏi chiến lược xử lý lỗi rõ ràng: sau rollback, những entity objects và state được giữ qua nhiều bước có thể không còn phù hợp với database. Phải hiểu container/provider semantics của transaction rollback, không tiếp tục wizard dài chỉ vì bean vẫn còn sống.

### 4.4. Không dùng cùng giải pháp close cho mọi EntityManager

| Context ownership | Ai quản lý lifecycle? | Khi lỗi |
| --- | --- | --- |
| Application-managed `emf.createEntityManager()` | Application | Rollback khi cần, `close()` trong `finally`, tạo EM mới nếu retry |
| Spring-injected `@PersistenceContext` proxy | Spring | Để transaction infrastructure rollback/cleanup, không tự `close()` proxy |
| Container-managed JTA EM | Container | Transaction manager quản lý; không tự đóng container-managed EM |
| Extended PC | Container/component lifecycle | Cần chiến lược phục hồi hoặc kết thúc conversation theo semantics container |

---

## 5. Entity object trong Java có thể khác database sau rollback

Giả sử database đang có:

```text
Order#101: status=DRAFT, version=3
```

Java code:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 101L);

order.confirm();
em.flush();
```

Sau flush:

```text
Java object:
  status=CONFIRMED
  version có thể đã được điều chỉnh theo provider

Database transaction (chưa commit):
  UPDATE status=CONFIRMED

Database committed state từ transaction khác:
  vẫn có thể là DRAFT
```

Sau đó một constraint failure xảy ra ở thao tác khác và transaction rollback.

```text
Database committed state:
  status=DRAFT, version=3

Java reference "order":
  có thể vẫn hiển thị CONFIRMED
  và version/generated state khác DB
```

### 5.1. Rollback không tua ngược Java heap

Database rollback hoàn tác các thay đổi transactional trong DB, **không tự chạy một cơ chế Java “undo mọi setter”** để đưa từng object về giá trị ban đầu.

Do đó không được viết:

```java
catch (RuntimeException ex) {
    tx.rollback();

    // Sai nếu tin object này tự khôi phục như DB.
    if (order.getStatus() == OrderStatus.CONFIRMED) {
        sendConfirmation(order);
    }
}
```

### 5.2. ID được sinh trước rollback

Với `GenerationType.IDENTITY`, provider có thể INSERT sớm để lấy ID. Sau rollback, object Java có thể vẫn giữ generated ID nhưng database không có row tương ứng.

```java
em.persist(newOrder);
em.flush();

Long generatedId = newOrder.getId();

em.getTransaction().rollback();

// generatedId có thể không trỏ tới row committed.
```

Không dùng object giữ ID vừa rollback như chứng cứ rằng insert đã thành công.

### 5.3. Version/snapshot sau failure không còn là nguồn quyết định

Nếu update thất bại vì optimistic conflict, object đang giữ version cũ. Nếu UPDATE đã chạy rồi transaction rollback vì lỗi khác, object có thể mang version đã thay đổi trong Java. Cả hai trường hợp đều cần **re-read từ DB trong unit of work mới** trước khi tiếp tục.

### 5.4. Giữ DTO input thay vì giữ failed managed instance

Để retry, giữ **ý định nghiệp vụ**:

```java
public record ConfirmOrderCommand(
    Long orderId,
    String requestId
) {
}
```

Không giữ managed `PurchaseOrder` từ transaction thất bại làm tham số cho attempt mới.

---

## 6. `clear()` không chữa transaction bị rollback-only

Một phản xạ dễ gặp là:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    em.clear();
    em.persist(anotherEntity);
}
```

`em.clear()` detach managed entities khỏi persistence context. Nó **không**:

- Hủy trạng thái rollback-only.
- Gỡ transaction aborted của database.
- Rollback SQL đã gửi trong transaction.
- Phục hồi JDBC connection hỏng.
- Bảo đảm EntityManager đang ở trạng thái nhất quán sau mọi provider exception.
- Làm commit chắc chắn thành công.

### 6.1. `clear()` trước rollback còn có thể bỏ pending changes

Trong một transaction đang bình thường:

```java
order.confirm();
em.clear();
em.getTransaction().commit();
```

Nếu chưa flush, thay đổi có thể không được ghi vì entity đã detached. Khi transaction đã lỗi, dùng `clear()` càng không phải chiến lược sửa đồng bộ trạng thái.

### 6.2. `clear()` hữu ích ở tình huống khác

`clear()` phù hợp với batch processing được thiết kế chủ động:

```java
em.flush();
em.clear();
```

để giải phóng managed references theo batch, **khi transaction/context đang hoạt động hợp lệ**. Không lấy pattern batch này làm “phương thuốc” cho SQL failure.

---

## 7. `refresh()` không phải nút Reset sau lỗi

`em.refresh(entity)` dùng để nạp lại state của **managed entity** từ database theo semantics JPA.

```java
em.refresh(order);
```

Nhưng nếu transaction đã bị aborted/rollback-only:

- Refresh có thể phát SQL và tiếp tục thất bại.
- Entity có thể đã detached.
- DB transaction snapshot có thể không cho thấy phiên bản mới nhất.
- Pending changes có thể bị ghi đè.
- Provider/context sau failed flush có thể không còn an toàn để tiếp tục.

### 7.1. Khi nào refresh phù hợp?

Một persistence context **đang hợp lệ**, entity đang managed, ứng dụng có chủ đích bỏ thay đổi chưa flush và muốn đọc lại DB state.

Đó là thao tác **đồng bộ dữ liệu trong một context lành mạnh**, không phải cách chữa một transaction đã abort.

### 7.2. Refresh sau rollback không giải quyết mọi chuyện

An toàn hơn sau failure nghiêm trọng:

```text
rollback -> discard context -> create new context
         -> find entity again -> re-evaluate
```

Không tạo một quy tắc “sau mọi exception cứ refresh là xong”.

---

## 8. `detach()` và `merge()` không khôi phục transaction

`em.detach(entity)` chỉ làm một object không còn managed trong context đó. Nó không sửa transaction/DB state.

`em.merge(detached)` sao chép state từ một detached object vào managed instance trong context thích hợp. Nếu object bị detach sau rollback và mang giá trị stale/ID/version đáng ngờ, **merge có thể cố ghi lại state sai**.

Sai:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    em.getTransaction().rollback();

    // Không nên tự coi object lỗi là dữ liệu cần ghi lại.
    EntityManager next = emf.createEntityManager();
    next.merge(order);
}
```

Đoạn code còn thiếu transaction phù hợp và có thể làm mất thay đổi từ transaction khác.

### 8.1. Merge không phải retry domain logic

Một retry an toàn nên:

1. Nhận command chứa identifiers và business intent.
2. Mở transaction/context mới.
3. Tải current entity state.
4. Kiểm tra lại business invariants.
5. Áp command lên managed entity mới.
6. Commit.
7. Chỉ retry khi failure class và operation cho phép.

**Không đồng nhất “copy Java fields lại bằng merge” với “thực hiện lại nghiệp vụ trên dữ liệu mới”.**

---

## 9. `close()` và factory lifecycle

Với application-managed EntityManager:

```java
EntityManager em = emf.createEntityManager();

try {
    // Thao tác.
} finally {
    em.close();
}
```

Sau failed unit of work, thường nên rollback nếu còn active và close EntityManager.

`EntityManagerFactory` có scope rộng hơn và thường vẫn usable sau một lỗi SQL ở một transaction cụ thể. **Không cần đóng toàn bộ factory sau mọi constraint violation**.

Ngược lại, nếu lỗi do config/bootstrap, database outage diện rộng hoặc factory không còn hoạt động, phải xử lý ở cấp hạ tầng theo lifecycle của ứng dụng.

### 9.1. Không đóng Spring-managed proxy

Trong Spring:

```java
@PersistenceContext
private EntityManager em;
```

Không gọi `em.close()` để “reset” request. Framework/transaction manager quản lý lifecycle của EntityManager thực phía sau proxy.

### 9.2. Không tự đóng container-managed JTA EM

Trong Jakarta EE, container-managed EntityManager chịu trách nhiệm lifecycle bởi container. Nếu transaction lỗi, hãy để JTA quản lý rollback và resource cleanup.

---

# Phần I — Các kịch bản lỗi cần dừng unit of work

## 10. UNIQUE violation: transaction có thể không còn dùng được

Giả sử DB có:

```sql
CONSTRAINT uk_orders_tenant_code
    UNIQUE (tenant_id, order_code)
```

Ứng dụng:

```java
em.persist(new PurchaseOrder(
    tenantId,
    "PO-100",
    customer
));

em.flush();
```

Nếu `(tenantId, "PO-100")` đã có, database sẽ từ chối theo semantics constraint.

### 10.1. Sai lầm: catch rồi đổi orderCode trong transaction cũ

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    order.setOrderCode("PO-101");
    em.flush();
}
```

Điều này rủi ro vì:

- Transaction có thể rollback-only.
- PostgreSQL sau SQL error có thể ở trạng thái transaction aborted.
- Provider có thể đã giữ pending insert/flush actions không phù hợp.
- Lỗi có thể phát ở commit, không phải flush.
- Việc tự đổi code có thể sai ý định người dùng.

### 10.2. Cách xử lý

- Rollback attempt lỗi.
- Phân loại UNIQUE theo constraint name/SQLSTATE.
- Trả business conflict nếu code do người dùng chọn.
- Nếu code do server sinh và policy cho phép retry, tạo **mã mới trong transaction/context mới**.
- Giới hạn số attempt và đảm bảo idempotency.

### 10.3. Pre-check không thay UNIQUE

Hai transactions có thể cùng chạy `existsByCode()` và nhận false. UNIQUE tại DB vẫn là hàng rào cuối. Không dùng một pre-check mới trong transaction đã aborted để “xác nhận nguyên nhân”.

---

## 11. Foreign key failure: không tiếp tục ghép entity cũ

Nếu database từ chối `customer_id` vì không có parent row:

```text
SQLSTATE 23503 (PostgreSQL): foreign_key_violation
```

Đừng tiếp tục:

```java
catch (PersistenceException ex) {
    customer = em.find(Customer.class, anotherId);
    order.setCustomer(customer);
    em.flush();
}
```

trong cùng transaction đã lỗi.

Hãy rollback, xác định dữ liệu tham chiếu/tenant/transaction ordering trong unit of work mới và quyết định đúng nghiệp vụ.

### 11.1. Foreign key lỗi có thể là bug logic, không phải input sai

Ví dụ:

- Parent entity chưa được persist do thiếu cascade.
- `@JoinColumn` trỏ sai key.
- Bulk delete parent chạy đồng thời.
- User cung cấp customer ID không tồn tại.
- Customer ở tenant khác nhưng application không kiểm soát đúng.
- Migration schema/constraint sai.

Cần phân loại root cause trước khi quyết định trả HTTP 400/404/409 hay 500.

---

## 12. NOT NULL/CHECK/Bean Validation: sửa input trong attempt mới

Nếu DB từ chối:

```text
23502 not_null_violation
23514 check_violation
```

hoặc Bean Validation từ chối:

```java
jakarta.validation.ConstraintViolationException
```

cần xác định:

- Lỗi giá trị do client gửi?
- Domain validation đã bỏ sót?
- Mapping và schema có thống nhất?
- Có đường native/bulk SQL bỏ qua validation?
- Có thuộc một field được set sai trong Java code?

Nếu lỗi chỉ là validation **trước khi tham gia persistence transaction** và không ảnh hưởng context, có thể báo ngay cho client. Nhưng nếu nó xuất hiện **trong flush** và transaction đã lỗi, phải rollback theo chính sách.

### 12.1. Không trả cùng một mã lỗi cho mọi constraint

`org.springframework.dao.DataIntegrityViolationException` có thể bọc UNIQUE, FK, NOT NULL hoặc CHECK. Một exception class rộng không đủ để phân loại.

---

## 13. OptimisticLockException: phải đọc lại trạng thái mới

Entity:

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private int quantity;

    // ...
}
```

Kịch bản:

```text
T1 đọc Item#101 version=4, quantity=10
T2 đọc Item#101 version=4, quantity=10

T1 cập nhật quantity=9, COMMIT -> version=5

T2 cập nhật từ version=4
  -> UPDATE ... WHERE id=101 AND version=4
  -> 0 rows affected
  -> OptimisticLockException
```

### 13.1. Không “sửa version” bằng tay

Sai:

```java
catch (OptimisticLockException ex) {
    item.setVersion(item.getVersion() + 1);
    em.flush();
}
```

Version do provider quản lý và transaction đã bị ảnh hưởng. Việc tự tăng version có thể phá optimistic locking và ghi đè thay đổi của transaction khác.

### 13.2. Retry đúng nghĩa nghiệp vụ

Đối với command “giảm quantity đi 1”:

```text
Attempt 1:
  read quantity=10, version=4
  attempt update -> optimistic conflict
  rollback/close

Attempt 2:
  new transaction/context
  read quantity=9, version=5
  check quantity >= 1
  apply decrement -> quantity=8
  commit
```

Tức là **tính toán lại trên state hiện tại**, không merge object cũ với quantity=9 và tự nghĩ rằng đó là “giảm một lần nữa”.

### 13.3. Đôi khi retry không đúng

Nếu người dùng đang chỉnh sửa một tài liệu và có concurrent edit, tự động retry có thể ghi đè quyết định của người kia. Hợp đồng tốt hơn là báo conflict và yêu cầu user reconcile.

---

## 14. Deadlock và serialization failure

PostgreSQL ví dụ:

```text
40P01 = deadlock_detected
40001 = serialization_failure
```

Database có thể hủy một transaction để giải quyết deadlock hoặc đảm bảo isolation.

### 14.1. Retry statement trong transaction cũ là sai

```text
BEGIN
  UPDATE A
  UPDATE B -> deadlock
  catch
  UPDATE B again in same transaction  // Không an toàn
```

Transaction đã thất bại hoặc bị đánh dấu abort. Cần rollback.

### 14.2. Retry toàn đơn vị công việc

```text
Attempt 1
  BEGIN
  read -> business logic -> write
  deadlock
  ROLLBACK / close

Backoff bounded + jitter

Attempt 2
  BEGIN mới
  read state mới -> business logic lại -> write
  COMMIT
```

### 14.3. Vì sao phải đọc lại?

Giữa hai attempts, state có thể đã được transaction khác thay đổi. Thực thi lại một UPDATE từ snapshot cũ có thể sai dù không còn deadlock.

### 14.4. Sắp xếp thứ tự khóa

Để giảm deadlock:

- Khóa entities theo thứ tự xác định (ví dụ ID tăng dần).
- Giữ transaction ngắn.
- Tránh HTTP calls trong transaction.
- Chỉ tải và khóa rows thật sự cần.
- Dùng index phù hợp cho predicates.
- Đo lock wait và deadlock rate.

Retry là biện pháp phục hồi có giới hạn, không thay việc thiết kế locking hợp lý.

---

## 15. Pessimistic lock failure và lock timeout

Một transaction có thể yêu cầu:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

JPA có:

```java
jakarta.persistence.PessimisticLockException
jakarta.persistence.LockTimeoutException
```

### 15.1. Phân biệt outcome

Theo JPA contract:

- `PessimisticLockException` mang ý nghĩa lock failure khiến transaction rollback.
- `LockTimeoutException` dành cho trường hợp statement bị rollback nhưng transaction không bị đánh dấu rollback chỉ vì exception đó.

Dù vậy, cần xem provider, DB, transaction manager và Spring rollback rules. Không dùng tên exception để bỏ qua kiểm tra transaction state.

### 15.2. Thời gian chờ lock là một phần của contract

Nếu người dùng đặt hàng cần xử lý nhanh, lock timeout có thể được trả như lỗi tạm thời với hướng retry. Nhưng nếu request đã hết deadline, đừng retry chỉ để tăng tải database.

### 15.3. Retry với context mới khi transaction đã rollback-only

Nếu lỗi khiến rollback-only, không dùng cùng `EntityManager` và same managed entity. Mở unit of work mới và kiểm tra lại business conditions.

---

## 16. Query timeout không bảo đảm transaction vẫn dùng được

Ví dụ:

```java
query.setHint(
    "jakarta.persistence.query.timeout",
    2_000
);
```

Provider có thể hỗ trợ hint theo version. Nếu query timeout, kiểm tra:

- JPA exception type.
- DB SQLSTATE/error code.
- Transaction status.
- Spring rollback rules.
- Lock/query contention.
- Statement có DML hay read-only?
- Request deadline.

Một `QueryTimeoutException` theo JPA có statement-level semantics, nhưng **không phải lời hứa mọi DB hoặc framework vẫn cho phép tiếp tục ghi an toàn sau mọi timeout thực tế**.

### 16.1. Không retry mãi một query chậm

Nếu SQL thiếu index hoặc fetch graph quá rộng, cùng query sẽ timeout nhiều lần. Cần plan optimization, pagination, index, query shape và SLA phù hợp.

---

## 17. TransactionRequiredException: lỗi ranh giới transaction

Trong RESOURCE_LOCAL:

```java
EntityManager em = emf.createEntityManager();

PurchaseOrder order =
    em.find(PurchaseOrder.class, id);

order.confirm();

em.flush(); // Không có active transaction phù hợp.
```

Có thể nhận:

```java
jakarta.persistence.TransactionRequiredException
```

Đây thường là lỗi **transaction boundary**, không phải sự cố tạm thời để retry với đúng code.

### 17.1. Cách sửa

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    PurchaseOrder order =
        em.find(PurchaseOrder.class, id);

    order.confirm();

    em.getTransaction().commit();

} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Với Spring/JTA, transaction được framework/container quản lý. Không gọi `getTransaction()` trên container-managed EntityManager.

### 17.2. Không dùng `@Transactional` mà không kiểm tra proxy

Trong Spring proxy-based mode, self-invocation:

```java
this.confirmOrder(id);
```

có thể không áp dụng `@Transactional` của method được gọi. Phải tổ chức service qua proxy hoặc dùng transaction API phù hợp.

---

# Phần II — Thiết kế phục hồi an toàn

## 18. Resource-local: một EntityManager cho một attempt

Một pattern rõ ràng:

```java
public final class OrderCommandExecutor {

    private final EntityManagerFactory emf;

    public OrderCommandExecutor(
            EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void confirm(Long orderId) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            PurchaseOrder order =
                em.find(PurchaseOrder.class, orderId);

            if (order == null) {
                throw new OrderNotFoundException(orderId);
            }

            order.confirm();

            // Có thể bắt lỗi SQL/optimistic lock tại flush.
            em.flush();

            // Cũng có thể lỗi tại commit.
            em.getTransaction().commit();

        } catch (RuntimeException ex) {
            try {
                if (em.getTransaction().isActive()) {
                    em.getTransaction().rollback();
                }
            } catch (RuntimeException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }

            throw ex;

        } finally {
            em.close();
        }
    }
}
```

Domain exception minh họa:

```java
public class OrderNotFoundException
        extends RuntimeException {

    public OrderNotFoundException(Long id) {
        super("Order not found: " + id);
    }
}
```

### 18.1. Vì sao mỗi attempt dùng EM riêng?

- Tách pending changes/snapshots của attempt cũ.
- Không giữ entity object stale từ rollback.
- Có rollback/close ownership rõ ràng.
- Không chia sẻ EntityManager giữa threads.
- Retry có thể re-read business state.

### 18.2. Rollback cũng có thể thất bại

Khi connection đã mất, `rollback()` có thể ném thêm exception. Không để rollback failure vô tình che mất nguyên nhân ban đầu. Có thể gắn `addSuppressed` hoặc log chi tiết có kiểm soát.

### 18.3. Close cũng phải được quản lý

Với application-managed EM, phải `close()` trong `finally`. Nếu `close` thất bại và cần giữ nguyên root cause, có thể dùng một utility cleanup ghi suppressed exceptions hoặc logging phù hợp. Ví dụ ngắn trên chưa bao phủ mọi tổ hợp cleanup failure.

### 18.4. Không rollback một transaction đã commit thành công

Chỉ rollback khi transaction còn active theo API. Sau commit success, các lỗi xảy ra ở notification ngoài database phải được xử lý riêng, không “rollback lại” DB.

---

## 19. Nâng cấp pattern để bảo toàn primary exception

Một helper có thể làm cleanup có kiểm soát:

```java
private static void rollbackIfActive(
        EntityManager em,
        RuntimeException primary) {

    try {
        if (em.isOpen() &&
                em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
    } catch (RuntimeException rollbackError) {
        primary.addSuppressed(rollbackError);
    }
}
```

Và:

```java
private static void closeSafely(
        EntityManager em,
        RuntimeException primary) {

    try {
        if (em.isOpen()) {
            em.close();
        }
    } catch (RuntimeException closeError) {
        primary.addSuppressed(closeError);
    }
}
```

Đây là helpers cho **application-managed RESOURCE_LOCAL**; chúng không có nghĩa application nên tự close Spring/JTA-managed EM.

### 19.1. Không chỉ catch PersistenceException

Code application có thể ném `IllegalStateException`, `IllegalArgumentException`, validation runtime exception hoặc domain exception trong transaction. Nếu cần rollback toàn attempt, `catch (RuntimeException)` ở unit-of-work boundary thường bao phủ những trường hợp Java runtime thông thường.

Error-level failures (`OutOfMemoryError`...) cần chiến lược lifecycle riêng và không nên được “nuốt để retry”.

### 19.2. Không biến mọi RuntimeException thành retryable

`RuntimeException` phù hợp để đảm bảo rollback/cleanup, **không phù hợp làm điều kiện retry chung**. Phân loại retry phải hẹp hơn nhiều.

---

## 20. JTA: dùng transaction manager, không điều khiển EM bằng getTransaction

Trong Jakarta EE:

```java
@Stateless
public class OrderJtaService {

    @PersistenceContext
    private EntityManager em;

    public void confirm(Long orderId) {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new OrderNotFoundException(orderId);
        }

        order.confirm();
    }
}
```

Transaction thường được điều phối bởi container theo cấu hình component. Khi gặp persistence failure, để container/JTA xử lý rollback.

### 20.1. Đánh dấu rollback-only khi cần

Trong một component JTA có access tới transaction facilities thích hợp, application có thể yêu cầu rollback:

```java
@Resource
private jakarta.transaction.TransactionSynchronizationRegistry registry;

public void failTransaction() {
    registry.setRollbackOnly();
}
```

Cần đang có transaction thích hợp; ví dụ chỉ minh họa API. `setRollbackOnly()` không phục hồi transaction, mà yêu cầu transaction không được commit.

### 20.2. Không tự `em.close()`

`@PersistenceContext` container-managed EntityManager không thuộc quyền lifecycle close thủ công của application.

### 20.3. Extended persistence context cần thiết kế đặc biệt

Với extended PC, một workflow dài có thể giữ entity objects qua nhiều transactions. Sau rollback hoặc state inconsistency, không đơn giản tiếp tục bước tiếp theo như không có lỗi. Có thể cần hủy conversation/stateful component, reload toàn bộ state hoặc bắt đầu workflow mới theo semantics container.

---

## 21. Spring @Transactional: để framework kết thúc attempt lỗi

Ví dụ Spring Data JPA:

```java
@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;

    public OrderCommandService(
            PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order =
            orders.findById(orderId)
                .orElseThrow(
                    () -> new OrderNotFoundException(orderId)
                );

        order.confirm();
    }
}
```

Với một exception được Spring rollback policy áp dụng, transaction interceptor rollback khi method thoát ra ngoài và transaction thuộc quyền điều phối của nó.

### 21.1. Đừng giữ EntityManager qua nhiều request

Một singleton service được inject EntityManager proxy, không đồng nghĩa mỗi request dùng chung một persistence context. Proxy có thể điều phối tới context gắn transaction/thread hiện tại.

Không lưu reference tới một EntityManager application-managed trong singleton và cho nhiều requests/threads cùng truy cập; EntityManager không thread-safe.

### 21.2. Đừng catch SQL exception rồi tiếp tục trong `@Transactional`

Sai:

```java
@Transactional
public void importBatch(List<ItemInput> items) {
    for (ItemInput input : items) {
        try {
            repository.saveAndFlush(
                toEntity(input)
            );
        } catch (DataIntegrityViolationException ex) {
            // Nguy hiểm: transaction có thể rollback-only/aborted.
            continue;
        }
    }
}
```

### 21.3. Phải thay chiến lược batch nếu muốn bỏ qua item lỗi

Một số lựa chọn theo use case:

- Một transaction riêng cho mỗi item/chunk.
- Stage dữ liệu rồi validate/merge trong database.
- Native `ON CONFLICT` theo database nếu business semantics cho phép.
- Savepoint/nested transactions **chỉ khi transaction manager/driver/provider hỗ trợ và behavior được test**.
- Ghi lỗi từng item vào một kết quả độc lập.
- Không tái sử dụng context lỗi giữa các items.

---

## 22. `UnexpectedRollbackException`: outer transaction không thể “cứu” inner failure

Ví dụ:

```java
@Transactional
public void process() {
    try {
        innerService.updateSomething();
    } catch (RuntimeException ex) {
        log.warn("Inner failed", ex);
    }

    // Caller tưởng đang tiếp tục bình thường.
    repository.save(otherEntity);
}
```

Nếu inner service đã khiến shared transaction bị đánh dấu rollback-only, outer `process()` không thể commit dù đã catch exception.

Khi Spring cố commit:

```text
UnexpectedRollbackException
```

### 22.1. Phân biệt hai trường hợp

- **Exception chưa ảnh hưởng transaction**: có thể xử lý branch trong cùng transaction nếu JPA/DB/framework semantics cho phép.
- **Transaction đã rollback-only**: không được tiếp tục như thể có thể commit.

### 22.2. Không giải quyết bằng `noRollbackFor` vô điều kiện

Có thể cấu hình rollback rules cho **một số domain exceptions không làm hỏng transaction**, nhưng nếu database đã rollback-only hoặc transaction aborted, `noRollbackFor` không làm nó khỏe trở lại.

### 22.3. Không gọi REQUIRES_NEW qua `this.method()`

Trong Spring proxy-based mode, self-invocation có thể bypass transaction advice. Muốn tách transaction, dùng bean khác/proxy hoặc `TransactionTemplate` và test boundary thật.

---

## 23. Spring TransactionTemplate cho retry với transaction mới

Khi cần retry các lỗi đã được xác định là transient, `TransactionTemplate` có thể điều phối từng attempt:

```java
@Service
public class InventoryAdjustService {

    private final TransactionTemplate transactions;
    private final InventoryRepository items;

    public InventoryAdjustService(
            PlatformTransactionManager manager,
            InventoryRepository items) {

        this.transactions = new TransactionTemplate(manager);
        this.items = items;
    }

    public void decrement(Long itemId) {
        RuntimeException last = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                transactions.executeWithoutResult(status -> {
                    InventoryItem item = items.findById(itemId)
                        .orElseThrow();

                    item.decrementOne();
                });

                return;

            } catch (RuntimeException ex) {
                if (!RetryClassifier.isRetryable(ex)) {
                    throw ex;
                }

                last = ex;

                if (attempt == 3) {
                    throw ex;
                }

                backoff(attempt);
            }
        }

        throw last;
    }

    private static void backoff(int attempt) {
        // Placeholder: thực tế cần bounded exponential backoff
        // với jitter, deadline và handling interruption.
    }
}
```

Đây là một **khung minh họa**: `InventoryRepository`, `InventoryItem.decrementOne()` và `RetryClassifier` cần được định nghĩa trong project.

### 23.1. Điều kiện trước khi dùng khung này

- Caller **không được mở một outer transaction** vô tình khiến mỗi lần `execute` tham gia chung transaction. Nếu cần đảm bảo tách biệt, cấu hình propagation phù hợp (ví dụ `REQUIRES_NEW`) với những đánh đổi tương ứng.
- Retry classifier phải chỉ cho phép một tập lỗi transient **đã kiểm chứng**.
- Không gửi email/payment ở giữa attempt.
- Mỗi transaction có persistence context/managed state thích hợp.
- Deadline và resource limits được áp.
- Không biến “retry 3 lần” thành quy tắc cho mọi endpoint.

### 23.2. Vì sao retry wrapper nên ở ngoài transaction?

Để mỗi attempt có cơ hội:

```text
start tx -> work -> fail -> rollback/cleanup
           |
           v
       backoff outside tx
           |
           v
start new tx -> reload -> work -> commit
```

Backoff **bên trong transaction** sẽ giữ connection/locks/resources lâu hơn và không giải quyết trạng thái lỗi.

---

## 24. Retry phải có kiểm tra idempotency

Một nghiệp vụ có thể làm nhiều việc:

```text
1. Decrement stock
2. Create order
3. Call payment gateway
4. Commit database
```

Nếu gặp lỗi ở bước 4 và retry toàn bộ, payment gateway có thể bị gọi lại.

### 24.1. Giải pháp thường dùng

- Lưu `requestId` hoặc idempotency key có UNIQUE constraint.
- Ghi trạng thái request trong database.
- Đặt external effects ở một workflow riêng phù hợp.
- Dùng transactional outbox để lưu event intent cùng transaction.
- Consumer deduplicate bằng event ID.
- Reconcile outcome khi mất kết nối quanh commit.

### 24.2. UNIQUE conflict không nhất thiết là retryable

Nếu hai requests dùng cùng idempotency key, một request được xử lý thành công, request sau có thể nhận conflict khi cố INSERT. Thay vì retry INSERT vô hạn, application nên tra cứu request state theo idempotency contract.

### 24.3. Transactional outbox khác callback sau commit

`@TransactionalEventListener(AFTER_COMMIT)` hoặc JTA `afterCompletion(COMMITTED)` giúp tránh phát sự kiện khi rollback, nhưng một process crash sau DB commit vẫn có thể làm mất in-memory notification.

Outbox lưu event intent **trong cùng transaction** với business state, sau đó worker giao event với retry/idempotency.

---

# Phần III — Những tình huống khó sau lỗi

## 25. Flush đã chạy nhưng commit sau đó rollback

Một ví dụ:

```java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.confirm();

em.flush(); // UPDATE đã gửi trong transaction.

// Một thao tác khác gây CHECK/FOREIGN KEY violation.
em.persist(invalidEntity);
em.flush(); // Exception.

em.getTransaction().rollback();
```

Sau rollback:

- DB không giữ thay đổi `order.confirm()`.
- Java `order` có thể vẫn có `status=CONFIRMED`.
- Version/generated values không được xem là bằng chứng DB đã commit.
- Một attempt mới phải re-read entity.

### 25.1. Không phát business event dựa trên object state

Không làm:

```java
if (order.getStatus() == OrderStatus.CONFIRMED) {
    publisher.publishEvent(new OrderConfirmed(orderId));
}
```

sau failed attempt. State Java không nói commit outcome.

### 25.2. Lifecycle callback không chứng minh commit

`@PostPersist`, `@PostUpdate`, `@PostRemove` có thể chạy ở flush trước commit. Nếu transaction rollback, callback có thể đã chạy nhưng dữ liệu không committed.

Side effects cần transaction-aware mechanism/outbox, không gửi email quan trọng ngay trong JPA callbacks.

---

## 26. Failed bulk JPQL/native DML

Ví dụ:

```java
em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = i.quantity - :amount
    WHERE i.id = :id
    """
)
.setParameter("amount", amount)
.setParameter("id", id)
.executeUpdate();
```

Bulk DML thường bypass managed entity dirty checking, khiến L1 entities stale dù SQL thành công. Nếu DML **thất bại**, transaction còn có thể rollback-only/aborted.

### 26.1. Không chữa stale L1 bằng `refresh` sau failed transaction

Sau bulk failure:

```text
rollback -> discard context -> new transaction/context
         -> reload state
```

### 26.2. Bulk success cũng cần đồng bộ plan

Nếu DML thành công nhưng context đang giữ entity cùng ID, `em.find(id)` có thể trả state cũ. Khi transaction còn lành mạnh, ứng dụng cần `refresh`, `clear` hoặc context mới theo kế hoạch.

Phân biệt **stale state sau successful bulk update** với **failed context do SQL error**; chiến lược phục hồi không giống nhau.

---

## 27. Failed query nhưng transaction vẫn chưa chắc phải bỏ

Một số query errors không phá transaction:

```java
try {
    em.createQuery(
        """
        SELECT o FROM PurchaseOrder o
        WHERE o.orderCode = :code
        """,
        PurchaseOrder.class
    )
    .setParameter("code", "UNKNOWN")
    .getSingleResult();

} catch (NoResultException ex) {
    // Có thể xử lý như không tìm thấy.
}
```

Trong code thuần JPA, ngoại lệ not-found không đồng nghĩa transaction hỏng.

### 27.1. Vẫn cần xem tầng Spring

Nếu exception bị ném ra ngoài một method Spring `@Transactional`, default rollback rules cho unchecked exceptions có thể thay đổi transaction outcome. Nếu application muốn mô tả not-found bằng một kết quả thay vì exception, nên trả Optional/DTO phù hợp.

### 27.2. Không so sánh với SQL errors

`NoResultException` khác một `SQLException` đến từ database. Sau SQL error, đặc biệt PostgreSQL, transaction có thể aborted. Đừng dùng “query cũng là exception nhưng có thể catch” để suy ra flush failure có thể bỏ qua.

---

## 28. L1 cache có thể che dữ liệu sau rollback

Giả sử trước khi transaction lỗi:

```java
InventoryItem item =
    em.find(InventoryItem.class, id);

item.changeQuantity(0);
```

Sau rollback, một object reference có thể vẫn giữ `quantity=0`. Nếu application lấy nó từ một cache tự quản hoặc một long-lived state holder, UI có thể hiển thị dữ liệu chưa từng commit.

### 28.1. EntityManager không phải application cache

Không dùng EntityManager singleton toàn ứng dụng hoặc chia sẻ managed entities giữa threads. Persistence context có scope rõ và EntityManager không thread-safe.

### 28.2. DTO cũng có thể stale nhưng không nguy hiểm theo cùng cách

Một DTO được tạo từ failed managed state có thể chứa dữ liệu sai như bất kỳ Java object nào; tuy nhiên nó không tự dirty-check hoặc ghi DB. Đừng trả DTO thành “success response” nếu transaction rollback.

### 28.3. Evict L2 không reset L1 failed state

```java
emf.getCache().evict(InventoryItem.class, id);
```

tác động shared cache, **không xóa Java managed instance trong L1**. Nó cũng không sửa aborted transaction.

---

## 29. Commit outcome không rõ: không được giả định rollback

Kịch bản:

```text
Application sends COMMIT
          |
          v
Database may commit
          |
          X  connection lost
          |
          v
Application did not receive success response
```

Khi mất connection ở ranh giới commit, có thể không chắc DB đã commit hay chưa.

### 29.1. Cần phân biệt ba trạng thái

1. **Committed đã xác nhận**: chỉ thực hiện logic thành công.
2. **Rolled back đã xác nhận**: có thể quyết định attempt mới theo chính sách.
3. **Outcome unknown**: cần reconciliation/idempotency, không retry create/payment mù quáng.

### 29.2. Ví dụ idempotency key

```sql
CREATE TABLE command_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    operation VARCHAR(100) NOT NULL,
    outcome VARCHAR(32) NOT NULL
);
```

Lưu record idempotency và business update theo một transaction khi phù hợp. Nếu commit response bị mất, caller có thể truy vấn `request_id` để đối chiếu.

### 29.3. Không nghĩ “rollback() sau mất kết nối là undo chắc chắn”

Nếu database đã commit, gọi rollback trên một connection mới hoặc connection đã mất **không thể đảo ngược commit cũ**. Đây là lý do các lệnh có external effects cần idempotency và cơ chế reconcile.

---

# Phần IV — Quan sát và kiểm thử

## 30. Đọc root cause trước khi ra quyết định

Một exception chain có thể là:

```text
TransactionSystemException
    -> RollbackException
        -> PersistenceException
            -> Hibernate ConstraintViolationException
                -> SQLException SQLSTATE=23505
```

Nếu chỉ nhìn ngoài cùng, dễ phân loại thành “transaction bị lỗi, thử lại”. Nhưng root cause là UNIQUE duplicate, retry cùng key thường không giúp.

### 30.1. Helper duyệt cause chain

```java
public final class Causes {

    private Causes() {
    }

    public static <T extends Throwable> T findCause(
            Throwable error,
            Class<T> type) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (type.isInstance(current)) {
                return type.cast(current);
            }
        }

        return null;
    }
}
```

Ví dụ:

```java
SQLException sql = Causes.findCause(
    error, SQLException.class
);

if (sql != null) {
    String sqlState = sql.getSQLState();
    int vendorCode = sql.getErrorCode();
}
```

### 30.2. SQLException.nextException có thể quan trọng

Một JDBC batch failure có thể nối thêm exceptions qua `SQLException.getNextException()`, không chỉ `Throwable.getCause()`. Bộ phân loại production có thể cần duyệt cả hai chuỗi một cách an toàn.

### 30.3. PostgreSQL SQLSTATE tham khảo

| SQLSTATE | Loại | Hướng xử lý |
| --- | --- | --- |
| `23505` | UNIQUE violation | Business conflict, rollback |
| `23503` | FOREIGN KEY violation | Kiểm tra reference |
| `23502` | NOT NULL violation | Input/mapping |
| `23514` | CHECK violation | Invariant/validation |
| `40001` | Serialization failure | Retry transaction mới nếu an toàn |
| `40P01` | Deadlock detected | Retry transaction mới có giới hạn |
| `42P01` | Undefined table | Sửa migration/schema |
| `42703` | Undefined column | Sửa mapping/migration |
| Class `08` | Connection exception | Xác định phase/commit outcome |

Những mã này **đặc thù PostgreSQL**, không nên dùng nguyên bảng để phân loại MySQL/Oracle/SQL Server.

---

## 31. Log để điều tra ngữ cảnh lỗi

Một log entry hữu ích có thể chứa:

```text
operation=confirmOrder
requestId=...
attempt=1
transactionPhase=flush
exceptionClass=...
rootCauseClass=...
sqlState=23505
constraint=uk_orders_tenant_code
rollbackAttempted=true
retryAllowed=false
```

Nên ghi:

- Correlation/request ID.
- Operation name.
- Transaction phase: query, flush, commit, rollback.
- Exception class/cause chain.
- SQLSTATE/vendor code nếu có.
- Constraint name nếu có.
- Retry attempt count.
- Đã xác nhận commit/rollback hay outcome unknown.
- Entity type và business ID khi chính sách cho phép.

Không mặc định log toàn bộ raw SQL/bind values chứa email, tokens hoặc dữ liệu thanh toán.

### 31.1. `isOpen=true` không phải health metric

Nếu sau exception:

```text
EntityManager.isOpen=true
```

không được dùng làm telemetry kết luận context safe. Ghi nhận transaction status và cause/outcome mới quan trọng hơn.

### 31.2. Đừng log “saved successfully” trước commit

`persist()` hoặc `flush()` chưa bảo đảm commit. Log thành công nghiệp vụ cần phát sau committed outcome, hoặc dùng outbox/audit cùng transaction tùy nhu cầu.

---

## 32. Integration test: rollback không khôi phục Java object

Test RESOURCE_LOCAL với database thực:

```java
@Test
void rollbackDoesNotUndoJavaFieldMutations() {
    Long id = createDraftOrderFixture();

    EntityManager em = emf.createEntityManager();
    PurchaseOrder order;

    try {
        em.getTransaction().begin();

        order = em.find(PurchaseOrder.class, id);
        order.confirm();

        // Bắt đầu thao tác nhưng quyết định rollback.
        em.getTransaction().rollback();

        // Chỉ quan sát Java state; không dùng để suy
        // luận database đã commit.
        assertEquals(
            OrderStatus.CONFIRMED,
            order.getStatus()
        );

    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        PurchaseOrder persisted =
            verify.find(PurchaseOrder.class, id);

        assertEquals(
            OrderStatus.DRAFT,
            persisted.getStatus()
        );

    } finally {
        verify.close();
    }
}
```

`createDraftOrderFixture()` là helper test tạo một order ở trạng thái `DRAFT`, commit trong transaction riêng và trả ID. EntityManager của fixture phải được đóng trước test.

**Điểm cần chứng minh:** thay đổi Java object không tự biến mất khi DB rollback; state committed phải được xác minh ở context mới.

---

## 33. Integration test: SQL UNIQUE failure rồi rollback

Giả sử entity Customer có unique key `(tenant_id, normalized_email)`.

### 33.1. Fixture

```java
private static Long createCustomerFixture(
        EntityManagerFactory emf,
        Long tenantId,
        String normalizedEmail) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Customer customer = new Customer(
            tenantId,
            normalizedEmail,
            "Example User"
        );

        em.persist(customer);
        em.flush();

        Long id = customer.getId();

        em.getTransaction().commit();
        return id;

    } catch (RuntimeException ex) {
        rollbackIfActive(em);
        throw ex;

    } finally {
        em.close();
    }
}

private static void rollbackIfActive(EntityManager em) {
    if (em.isOpen() &&
            em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
}
```

### 33.2. Test behavior

```java
@Test
void failedUniqueInsertDoesNotBecomeSecondCommittedRow() {
    Long tenantId = 20L;
    String email =
        "duplicate-" + UUID.randomUUID() + "@example.test";

    createCustomerFixture(emf, tenantId, email);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        RuntimeException error = assertThrows(
            RuntimeException.class,
            () -> {
                em.persist(new Customer(
                    tenantId, email, "Duplicate"
                ));

                em.flush();
                em.getTransaction().commit();
            }
        );

        assertTrue(isPostgresUniqueViolation(error));

    } finally {
        rollbackIfActive(em);
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        Long count = verify.createQuery(
            """
            SELECT COUNT(c)
            FROM Customer c
            WHERE c.tenantId = :tenant
              AND c.normalizedEmail = :email
            """,
            Long.class
        )
        .setParameter("tenant", tenantId)
        .setParameter("email", email)
        .getSingleResult();

        assertEquals(1L, count);

    } finally {
        verify.close();
    }
}
```

### 33.3. PostgreSQL classifier

```java
private static boolean isPostgresUniqueViolation(
        Throwable error) {

    SQLException sql = Causes.findCause(
        error, SQLException.class
    );

    return sql != null &&
        "23505".equals(sql.getSQLState());
}
```

Test này phụ thuộc PostgreSQL SQLSTATE. Hành vi exception timing có thể khác giữa ID generation/flush/commit; vì thế `assertThrows` bao cả ba thao tác.

### 33.4. Điều test không nên làm

Không cố chạy `em.persist()` một lần nữa **trong failed transaction** để thử “cứu” nó. Hãy rollback/close rồi xác minh database bằng EntityManager mới.

---

## 34. Integration test: optimistic conflict và context mới

Kịch bản:

```text
EM A đọc Order#101 version=1
EM B đọc Order#101 version=1
EM A confirm, commit -> version=2
EM B confirm, flush -> optimistic conflict
EM B rollback/close
EM C đọc -> state committed của A
```

Test skeleton:

```java
@Test
void optimisticFailureMustNotReuseStaleInstance() {
    Long orderId = createDraftOrderFixture();

    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    PurchaseOrder stale;

    try {
        emA.getTransaction().begin();
        emB.getTransaction().begin();

        PurchaseOrder winner =
            emA.find(PurchaseOrder.class, orderId);

        stale = emB.find(PurchaseOrder.class, orderId);

        winner.confirm();
        emA.getTransaction().commit();

        stale.confirm();

        RuntimeException conflict = assertThrows(
            RuntimeException.class,
            () -> {
                emB.flush();
                emB.getTransaction().commit();
            }
        );

        assertTrue(isOptimisticFailure(conflict));

    } finally {
        rollbackIfActive(emB);
        rollbackIfActive(emA);
        emB.close();
        emA.close();
    }

    EntityManager fresh = emf.createEntityManager();

    try {
        PurchaseOrder current =
            fresh.find(PurchaseOrder.class, orderId);

        assertEquals(
            OrderStatus.CONFIRMED,
            current.getStatus()
        );

    } finally {
        fresh.close();
    }
}
```

Trong đó:

- `createDraftOrderFixture()` tạo order hợp lệ và commit trước test.
- `isOptimisticFailure()` là classifier test dựa trên `OptimisticLockException`/provider-specific cause chain.
- Test cần chạy trên JPA provider/DB mục tiêu; một số isolation/locking configurations có thể thay outcome giữa hai transactions.
- Không tự retry bằng `merge(stale)`. Command mới phải re-read và re-evaluate.

---

## 35. Integration test: Spring rollback-only sau inner error

Một Spring integration test có thể xác minh:

```text
Transaction outer bắt đầu
    |
    v
Inner @Transactional REQUIRED tham gia
    |
    v
Inner ném RuntimeException
    |
    v
Spring đánh dấu rollback-only
    |
    v
Outer catch exception và return normally
    |
    v
Outer commit -> UnexpectedRollbackException
```

### 35.1. Điều kiện test

- Outer/inner đi qua Spring proxies thật.
- Inner dùng propagation `REQUIRED`.
- Exception được Spring rollback policy áp dụng.
- Test method không có outer `@Transactional` làm thay transaction boundary.
- Quan sát state DB bằng một transaction/context mới.

### 35.2. Không xem lỗi này là vấn đề JDBC connection đơn thuần

Lỗi báo ở commit nhưng nguyên nhân là một component đã khiến transaction rollback-only. Cần truy ngược **exception đầu tiên** và flow propagation.

---

## 36. Test query exception không luôn làm hỏng transaction

Trong một JPA RESOURCE_LOCAL transaction lành mạnh, `NoResultException` có thể được xử lý như kết quả không tìm thấy:

```java
@Test
void noResultDoesNotAutomaticallyMeanBrokenTransaction() {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        assertThrows(
            NoResultException.class,
            () -> em.createQuery(
                """
                SELECT o
                FROM PurchaseOrder o
                WHERE o.orderCode = :code
                """,
                PurchaseOrder.class
            )
            .setParameter("code", "UNKNOWN-" + UUID.randomUUID())
            .getSingleResult()
        );

        // Theo JPA contract, NoResultException tự nó
        // không đánh dấu transaction rollback.
        assertFalse(
            em.getTransaction().getRollbackOnly()
        );

        em.getTransaction().rollback();

    } finally {
        em.close();
    }
}
```

Test này chứng minh **không nên áp quy tắc “mọi exception từ JPA đều phá transaction”**.

### 36.1. Vì sao test vẫn rollback?

Đây là lựa chọn cleanup fixture/test, không phải vì `NoResultException` bắt buộc hủy transaction. Phân biệt semantics exception với chính sách test.

### 36.2. Spring có rollback policy khác

Khi exception unchecked thoát khỏi `@Transactional` method, Spring có thể rollback dù JPA exception đó tự nó không bắt buộc. Integration test cần xét transaction framework thực.

---

## 37. Test lỗi và phục hồi với SQLSTATE

Khi DB báo deadlock hoặc serialization failure:

```text
Attempt 1:
  SQLSTATE 40P01 / 40001
  rollback/close

Attempt 2:
  new EntityManager
  new transaction
  reload current state
  business operation
  commit
```

Một test có thể dùng phối hợp locks/threads/latches để tạo deadlock cụ thể, nhưng test deadlock dễ phụ thuộc database/transaction schedule. Đừng dùng `Thread.sleep()` và kỳ vọng scheduler luôn tạo cùng outcome.

Đối với test logic retry, có thể mock **retry classifier** và transaction executor để kiểm tra number-of-attempts; còn tính đúng transaction boundaries cần integration test riêng.

### 37.1. Kiểm tra số lần retry có giới hạn

Test cần xác minh:

- Chỉ retry lỗi được allowlist.
- Không retry UNIQUE/mapping/validation.
- Mỗi attempt dùng context/transaction mới.
- Không có side effect lặp.
- Dừng khi hết deadline/attempt budget.
- Trả đúng lỗi cuối cùng khi thất bại.

---

# Phần V — Quy tắc thiết kế production

## 38. Phân biệt application failure với infrastructure failure

| Lỗi | Có thể phục hồi trong cùng transaction? | Chiến lược |
| --- | --- | --- |
| Not-found được xử lý như branch | Có thể, theo JPA/transaction policy | Trả Optional/404 |
| Query parameter typo | Không cần “phục hồi”; sửa code | Fail fast |
| Mapping/bootstrap invalid | Không | Sửa metadata/configuration |
| DB UNIQUE violation | Không nên tiếp tục failed transaction | Rollback, conflict |
| FK/CHECK/NOT NULL violation | Không nên tiếp tục failed transaction | Rollback, sửa input/model |
| Optimistic lock conflict | Không | Rollback, re-read/reconcile |
| Deadlock/serialization failure | Không | Rollback, new tx retry bounded |
| Query timeout | Cần xác minh status | Query plan/timeout policy |
| Lock timeout | Cần xác minh status | Reduce contention/retry |
| Connection loss during commit | Không biết outcome | Idempotency/reconcile |
| Transaction rollback-only | Không thể commit attempt này | Kết thúc bằng rollback |
| Spring inner REQUIRED failure | Không thể “nuốt” rollback-only | Sửa propagation/control flow |

### 38.1. Trạng thái an toàn không được suy đoán

Nếu không biết failure có tác động gì lên persistence context, **đừng tiếp tục mutate/flush với context đó**.

### 38.2. Không dùng “catch Exception rồi continue” làm retry policy

Pattern này bỏ qua rollback, DB state và business invariants. Cần unit-of-work boundary có ownership rõ.

### 38.3. Tách exception classification khỏi transaction orchestration

Một classifier có thể nói:

```text
class = DUPLICATE_KEY
retryable = false
http = 409
```

Còn transaction executor phải đảm bảo rollback/cleanup. Không nên trộn việc duyệt exception chain với các câu lệnh `em.persist()` mới ngay trong cùng catch block.

---

## 39. Checklist trước khi quyết định tái sử dụng hoặc retry

1. Exception đến từ JPA API, provider, JDBC hay Spring wrapper?
2. Có root cause rõ ràng không?
3. SQLSTATE/vendor code là gì?
4. Lỗi xảy ra lúc query, flush hay commit?
5. Transaction có rollback-only không?
6. Database đã xác nhận rollback/commit chưa?
7. Nếu connection mất ở commit, outcome có unknown không?
8. Có SQL error làm transaction aborted không?
9. EntityManager còn mở có ý nghĩa gì trong tình huống này?
10. Managed objects có field/ID/version được sửa trước rollback không?
11. Có pending changes chưa flush không?
12. Có dùng `clear` như cách che SQL error không?
13. Có định gọi `refresh` khi transaction chưa phục hồi không?
14. Có định `merge` detached entity từ failed attempt không?
15. Có thể rollback và đóng application-managed EM không?
16. Với Spring/JTA, ai sở hữu lifecycle EntityManager?
17. Có phải extended persistence context cần reset conversation không?
18. Exception có thuộc nhóm `NoResultException`/cardinality không?
19. Framework `@Transactional` có đánh dấu rollback riêng không?
20. Có optimistic version conflict không?
21. Có pessimistic lock/deadlock/serialization failure không?
22. Có retry classifier theo allowlist không?
23. Có giới hạn attempts/deadline/backoff không?
24. Retry có dùng new transaction/context không?
25. Retry có reload current state không?
26. Business operation có thể idempotent không?
27. Có external email/payment/message đã gửi ở attempt cũ không?
28. Có cần outbox/inbox/idempotency key không?
29. Có log operation/correlation/phase/outcome không?
30. Có kiểm thử rollback và committed state bằng context mới không?
31. Có test thất bại ở flush và commit không?
32. Có đảm bảo không lộ raw SQL/bind values qua API không?
33. Có test trên provider/database thực tế không?
34. Có thể giải thích rõ **vì sao** continuation an toàn, hay nên dừng?

---

## 40. Những ngộ nhận phổ biến

### “EntityManager.isOpen() trả true nên tiếp tục được”

Sai. `isOpen` không xác nhận transaction, JDBC state hoặc pending managed state.

### “isActive() nghĩa là transaction commit được”

Sai. Transaction active vẫn có thể rollback-only.

### “Rollback sẽ tự undo tất cả setter Java”

Sai. Database rollback không tự tua ngược Java heap.

### “clear() sửa được mọi lỗi persistence context”

Sai. `clear()` detach entities, không reset transaction rollback-only hoặc SQL transaction aborted.

### “refresh() giải quyết mọi trường hợp stale sau rollback”

Sai. Refresh có thể phát SQL, đòi managed instance và context hợp lệ; không sửa transaction lỗi.

### “merge() là retry an toàn cho detached entity”

Sai. Merge có thể sao chép stale state vào managed entity mới và ghi đè thay đổi của transaction khác.

### “Đóng EntityManagerFactory sau bất kỳ SQL exception nào”

Sai. Factory thường sống lâu; một constraint violation ở một transaction không đồng nghĩa toàn factory hỏng.

### “Spring @PersistenceContext proxy phải được close thủ công”

Sai. Spring quản lý lifecycle; không close proxy như application-managed EM.

### “NoResultException luôn rollback toàn transaction”

Không theo JPA exception contract riêng. Nhưng Spring rollback rules có thể khác nếu unchecked exception thoát khỏi transactional method.

### “QueryTimeoutException luôn an toàn để tiếp tục”

Sai nếu chưa kiểm tra DB/driver/framework transaction status.

### “OptimisticLockException có thể sửa bằng tự tăng @Version”

Sai. Version do provider quản lý và cần business reconciliation.

### “Sau deadlock retry cùng statement trong cùng transaction”

Sai. Failed transaction phải được rollback; attempt mới phải có context/transaction mới.

### “Mất kết nối lúc commit nghĩa là rollback”

Không chắc. Commit outcome có thể unknown.

### “Nếu transaction đã commit, email sau commit thất bại có thể rollback lại”

Sai. DB commit đã hoàn tất, side effect failure là một workflow khác; cần retry/outbox.

### “Mọi PersistenceException đều retryable”

Sai. Có bug mapping/schema/SQL/validation cố định không thể sửa bằng retry.

---

## 41. Bài tập tình huống có lời giải

### Bài 1. EM vẫn mở sau UNIQUE violation

**Tình huống:** `em.flush()` báo UNIQUE violation, `em.isOpen()` vẫn true.

**Đáp án:** Không kết luận context an toàn. Rollback/close application-managed EM và phân loại business conflict. Không cố INSERT tiếp trong cùng transaction lỗi.

### Bài 2. Entity đã có ID nhưng transaction rollback

**Đáp án:** ID được sinh trước commit không chứng minh row committed. Kiểm tra database bằng context mới; không dùng object đó như một persisted entity chắc chắn tồn tại.

### Bài 3. `em.clear()` sau SQLException

**Đáp án:** Clear không reset DB aborted state hoặc transaction rollback-only. Cần rollback/cleanup.

### Bài 4. `em.refresh(order)` sau failed flush

**Đáp án:** Không phải phép chữa phổ quát. Transaction có thể không thực hiện SQL được; dùng new context sau rollback.

### Bài 5. `em.merge(detached)` sau optimistic conflict

**Đáp án:** Có thể ghi stale state. Mở transaction mới, load state hiện tại và re-evaluate command.

### Bài 6. `NoResultException` trong JPA RESOURCE_LOCAL

**Đáp án:** Thông thường exception này tự nó không đánh dấu rollback. Xử lý not-found theo contract, phân biệt với transaction policy của framework.

### Bài 7. Spring `@Transactional` method ném `NoResultException` ra ngoài

**Đáp án:** Spring default rollback rules cho unchecked exception có thể đánh dấu rollback. JPA contract không tự phủ định Spring behavior.

### Bài 8. Lock timeout trong Spring

**Đáp án:** Không suy từ JPA class name rằng transaction chắc chắn khỏe. Kiểm tra transaction manager/DB state; rollback/retry theo policy nếu cần.

### Bài 9. Optimistic conflict

**Đáp án:** Rollback, context mới, re-read version/state và reconcile. Không tự sửa version.

### Bài 10. Deadlock SQLSTATE 40P01

**Đáp án:** Retry toàn transaction bằng context mới có giới hạn, sau rollback.

### Bài 11. Serialization failure 40001

**Đáp án:** Có thể retry toàn transaction, bao gồm bước đọc và quyết định nghiệp vụ. Không retry chỉ statement cuối.

### Bài 12. Outer `@Transactional` catch inner RuntimeException

**Đáp án:** Transaction có thể rollback-only. Catch không làm nó commit được; tìm lỗi đầu tiên và sửa propagation/flow.

### Bài 13. Spring self-invocation `REQUIRES_NEW`

**Đáp án:** Có thể không đi qua proxy. Dùng bean/proxy khác hoặc TransactionTemplate.

### Bài 14. DB commit outcome unknown

**Đáp án:** Không retry create/payment mù. Sử dụng idempotency key và reconciliation.

### Bài 15. `@PostUpdate` đã chạy nhưng rollback

**Đáp án:** Callback không chứng minh transaction committed; không phát success notification trực tiếp từ đó.

### Bài 16. L1 object có state CONFIRMED sau rollback

**Đáp án:** Java state có thể khác DB. Context mới mới cho state committed để quyết định.

### Bài 17. `emf.getCache().evict()` sau failed transaction

**Đáp án:** Evict L2 không reset L1 hoặc transaction lỗi. Không thay rollback/close.

### Bài 18. Spring injected EntityManager gặp lỗi

**Đáp án:** Không tự close proxy. Để Spring transaction infrastructure rollback/cleanup và khởi tạo transaction mới cho request sau.

### Bài 19. Batch import catch DataIntegrityViolationException và continue

**Đáp án:** Có thể tiếp tục trong aborted/rollback-only transaction. Thiết kế per-item/chunk transaction hoặc upsert/staging phù hợp.

### Bài 20. Transaction đang rollback-only nhưng `isActive()` true

**Đáp án:** Active không có nghĩa committable; kiểm tra rollback-only và kết thúc transaction bằng rollback.

### Bài 21. Query timeout vì thiếu index

**Đáp án:** Retry liên tục không sửa performance. Tối ưu query/index và deadline.

### Bài 22. FK violation lúc flush

**Đáp án:** Rollback context lỗi, phân loại reference/mapping/tenant/flush ordering. Không tiếp tục ghép entity trong cùng failed transaction.

### Bài 23. SQLSTATE 23505

**Đáp án:** PostgreSQL unique violation; cần constraint name nếu muốn xác định business field cụ thể.

### Bài 24. Mất kết nối trước query

**Đáp án:** Có thể retry sau khi xác định transaction chưa commit và operation idempotent. Không nhầm với mất kết nối ở commit boundary.

### Bài 25. Retry gửi email hai lần

**Đáp án:** External effect cần idempotency hoặc outbox/worker. Transaction rollback không thu hồi email đã gửi.

### Bài 26. Test chỉ kiểm tra exception được ném

**Đáp án:** Chưa đủ. Cần test transaction rollback, state DB cuối và resource cleanup/context mới.

### Bài 27. RESOURCE_LOCAL rollback rồi tái sử dụng EM cũ

**Đáp án:** Dù lifecycle API có thể cho phép application-managed EM tồn tại qua transactions thông thường, sau failure nghiêm trọng nên discard context và tạo EM mới để tránh stale/undefined state.

### Bài 28. Extended context sau lỗi

**Đáp án:** Cần hiểu lifecycle/rollback semantics của container, có thể phải hủy workflow/stateful component và tải lại state thay vì tiếp tục conversation mù quáng.

### Bài 29. SQL exception trong JDBC batch

**Đáp án:** Đọc cả cause chain và `SQLException.getNextException()`; rollback và không tiếp tục dùng context lỗi.

### Bài 30. `commit()` thành công nhưng notification thất bại

**Đáp án:** Không retry DB create một cách tự động chỉ để gửi notification. Tách delivery và dùng outbox/idempotency nếu cần bền vững.

---

## 42. Sơ đồ quyết định phục hồi

```text
                    JPA exception occurred
                               |
                               v
                   Identify error category
                               |
             +-----------------+-------------------+
             |                 |                   |
             v                 v                   v
        No-result /       Persistence SQL       Commit outcome
       benign result      / lock / flush         uncertain
             |                 |                   |
             v                 v                   v
      Check JPA and       Stop current work      Do NOT assume
      Spring policy       Rollback if needed     transaction failed
             |                 |                   |
             v                 v                   v
      Continue only       Discard affected       Reconcile via
      if tx/context       context/entities       idempotency key
      demonstrably safe         |                or durable state
                               v
                     Classify retryability
                               |
                     +---------+---------+
                     |                   |
                     v                   v
                 Not retryable       Retry allowed
                     |                   |
                     v                   v
                 Return/fix          Backoff bounded
                 root cause               |
                                          v
                                  NEW transaction
                                  NEW context
                                  reload fresh state
                                  re-evaluate business
```

Điểm quyết định không nằm ở một cờ `isOpen`, mà ở **hợp đồng exception, trạng thái transaction, state của persistence context, outcome commit và tính an toàn của nghiệp vụ khi thực hiện lại**.

## 43. Kết luận

Không tiếp tục dùng ngữ cảnh lỗi khi chưa xác định trạng thái an toàn là một **nguyên tắc kiểm soát hỏng hóc và bảo toàn tính đúng đắn** trong JPA, không chỉ là một mẹo tránh exception tiếp theo.

Tổng kết:

- **`EntityManager.isOpen()` không chứng minh context an toàn**, `EntityTransaction.isActive()` cũng không chứng minh transaction có thể commit.
- **Rollback không tự hoàn tác field changes, IDs và version values trong Java objects**.
- **`clear()`, `refresh()`, `detach()`, `merge()` không phải công cụ phục hồi transaction bị abort hoặc rollback-only**.
- Với SQL/flush/optimistic/commit failures, **dừng current unit of work, rollback nếu cần, discard affected context và dùng context/transaction mới** nếu có lý do retry.
- **Không áp một quy tắc cứng cho mọi exception**: `NoResultException` và một số statement-level exceptions có semantics khác transaction-fatal errors; Spring rollback rules cũng phải được xét.
- **Không retry nguyên thao tác vô hạn**: phân loại transient errors, dùng bounded backoff và tải lại business state.
- **Commit outcome có thể không xác định khi mất kết nối**; idempotency/reconciliation quan trọng hơn việc thử lại mù quáng.
- **External side effects không tự rollback cùng DB**; dùng outbox hoặc workflow idempotent khi cần.
- **Resource ownership khác giữa RESOURCE_LOCAL, JTA, Spring và extended persistence contexts**; chỉ application-managed EM mới được application tự close theo lifecycle.
- **Integration tests cần xác minh rollback/commit từ context mới**, không chỉ assert exception hoặc đọc object cũ.

**Khi một persistence operation thất bại, việc đầu tiên không phải “làm sao chạy tiếp?”, mà là “transaction đã kết thúc ra sao và state nào còn đáng tin?”. Chỉ sau khi trả lời được câu đó mới bắt đầu một đơn vị công việc mới hoặc tiếp tục một đường xử lý đã được chứng minh an toàn.**

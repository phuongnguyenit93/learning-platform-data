# Nhận diện API cũ như save, update, saveOrUpdate và Criteria Hibernate đời trước

## 1. Vì sao cần nhận diện API Hibernate đời trước?

Trong một dự án Java lâu năm, bạn có thể gặp những đoạn code như:

```java
session.save(order);
session.update(order);
session.saveOrUpdate(order);

Criteria criteria = session.createCriteria(PurchaseOrder.class);
criteria.add(Restrictions.eq("status", "PAID"));
criteria.addOrder(Order.desc("createdAt"));
List<?> orders = criteria.list();
```

Những API này từng rất phổ biến trong Hibernate native API. Khi nâng cấp Hibernate hoặc chuyển code sang JPA, chúng thường xuất hiện trong service, DAO, repository tự viết và test cũ.

Vấn đề là các tên method nghe có vẻ tương đương API mới, nhưng **semantics của chúng không giống nhau hoàn toàn**:

- Hibernate native save() không giống hoàn toàn JPA persist().
- update() đời trước gắn một detached instance vào Session; merge() sao chép trạng thái sang một managed instance.
- saveOrUpdate() dựa vào việc Hibernate nhận diện transient/detached theo identifier, version và unsaved-value mapping; nó không phải database UPSERT.
- org.hibernate.Criteria là API riêng của Hibernate, khác hẳn JPA Criteria API.
- Legacy Hibernate Criteria API đã bị loại bỏ trong Hibernate ORM 6.0; JPA Criteria vẫn tồn tại và được hỗ trợ.

Bài này giúp nhận diện code cũ, hiểu hành vi và chọn cách thay thế đúng. Mục tiêu khi migration là giữ nguyên **ý định nghiệp vụ và persistence semantics**, không chỉ đổi tên method để code biên dịch.

## 2. Phân biệt Hibernate native API và JPA API

Hibernate cung cấp Session API riêng, đồng thời triển khai chuẩn Jakarta Persistence/JPA qua EntityManager.

| Hibernate native API | JPA API | Mục đích |
|---|---|---|
| Session | EntityManager | Quản lý persistence context/unit of work |
| Session.persist() | EntityManager.persist() | Đưa entity mới vào trạng thái managed |
| Session.merge() | EntityManager.merge() | Copy state của entity vào managed instance |
| Session.remove() | EntityManager.remove() | Đánh dấu managed entity để xóa |
| Session.get()/find() tùy version | EntityManager.find() | Tải entity theo primary key |
| Session.createQuery() | EntityManager.createQuery() | HQL/JPQL query |
| Session.createCriteria() đời cũ | JPA CriteriaBuilder/CriteriaQuery | API truy vấn kiểu criteria; hai API không cùng một loại |

Ví dụ lấy Session từ EntityManager:

```java
Session session = entityManager.unwrap(Session.class);
```

Một dự án có thể dùng cả hai API, nhưng nên thống nhất ranh giới và hiểu rõ method đang gọi thuộc contract nào. Nếu code cần portable JPA, ưu tiên EntityManager và JPA Criteria. Nếu cần tính năng Hibernate-specific, dùng Session API có chủ đích.

## 3. Entity state là nền tảng để hiểu các method cũ

Trước khi đọc save, update hay saveOrUpdate, cần hiểu vòng đời entity:

| Trạng thái | Ý nghĩa |
|---|---|
| Transient/new | Object Java mới, chưa được Persistence Context quản lý và chưa có persistent identity trong DB |
| Managed/persistent | Entity thuộc Persistence Context hiện tại; Hibernate theo dõi thay đổi |
| Detached | Entity từng managed nhưng không còn thuộc Persistence Context hiện tại |
| Removed | Entity managed đã được đánh dấu xóa; DELETE sẽ được đồng bộ khi flush |

Sơ đồ:

```text
new object
   |
   | persist()
   v
managed entity
   |
   | clear() / detach() / close Session
   v
detached entity
   |
   | merge()
   v
managed copy (object khác có thể được trả về)
   |
   | remove()
   v
removed entity
```

Một ID có giá trị không tự chứng minh entity đang managed hoặc chắc chắn đã tồn tại trong database. Với assigned IDs, ứng dụng có thể tạo object mới nhưng đã gán ID trước khi persist.

## 4. Hibernate Session.save() là gì?

Legacy Hibernate native API:

```java
Serializable id = session.save(order);
```

save() được dùng để lưu một transient object. Nó trả về identifier (kiểu Serializable trong API cũ), thay vì void như JPA persist().

Ví dụ đời trước:

```java
PurchaseOrder order = new PurchaseOrder();
order.setStatus("NEW");

Serializable id = session.save(order);
```

Trong JPA:

```java
PurchaseOrder order = new PurchaseOrder();
order.setStatus("NEW");

entityManager.persist(order);
Long id = order.getId();
```

### Khác biệt cần nhớ

| Đặc điểm | Hibernate save() đời trước | JPA persist() |
|---|---|---|
| API | Hibernate-specific | Chuẩn JPA |
| Return | Identifier (Serializable) | void |
| Mục đích | Lưu transient instance | Làm transient instance thành managed |
| Có phải commit? | Không | Không |
| Có đảm bảo SQL chạy ngay? | Phụ thuộc ID strategy/flush timing | Phụ thuộc ID strategy/flush timing |
| Portable giữa JPA providers? | Không | Có theo chuẩn |

Không hiểu save() là “ghi và commit”. Transaction vẫn cần commit; SQL có thể được phát khi flush hoặc sớm hơn nếu ID generation cần.

## 5. Thay save() bằng persist() khi nào?

Nếu code cũ chỉ tạo một entity mới:

```java
Long id = (Long) session.save(order);
```

Thường có thể chuyển thành:

```java
entityManager.persist(order);
```

Sau đó lấy ID từ entity:

```java
entityManager.persist(order);
entityManager.flush(); // Nếu cần bảo đảm INSERT đã được đồng bộ tại đây.
Long id = order.getId();
```

Không phải mọi ID strategy đều cần explicit flush để lấy ID. Với sequence, ID có thể được cấp trước INSERT; với IDENTITY, provider thường phải INSERT để nhận generated key. Chỉ gọi flush khi cần mốc SQL/constraint rõ ràng, không thêm flush tùy tiện sau mọi persist.

### persist() không nhận detached object như một object mới

JPA persist() dành cho new/transient entity. Nếu truyền detached entity, provider có thể ném EntityExistsException hoặc persistence exception tại thời điểm persist/flush tùy mapping và provider.

Nếu object đến từ request/DTO hoặc một Session cũ, không gọi persist chỉ vì muốn “lưu lại”. Trước hết xác định đó là tạo mới hay cập nhật entity đã có.

## 6. Session.update() đời trước đã làm gì?

Hibernate native API cũ có:

```java
session.update(detachedOrder);
```

update() được dùng để reattach một detached instance vào Session hiện tại. Hibernate xem object đó là instance managed để theo dõi state và ghi thay đổi khi flush.

Ví dụ:

```java
Session firstSession = sessionFactory.openSession();
PurchaseOrder order =
    firstSession.get(PurchaseOrder.class, 100L);
firstSession.close(); // order trở thành detached.

order.setStatus("PAID");

Session secondSession = sessionFactory.openSession();
Transaction tx = secondSession.beginTransaction();
secondSession.update(order);
tx.commit();
secondSession.close();
```

Sau khi Session đầu đóng, order là detached. Legacy update() cố gắng gắn chính object này vào Session thứ hai.

### Xung đột với object cùng ID đã managed

Giả sử Session thứ hai đã tải một instance:

```java
PurchaseOrder managed =
    secondSession.get(PurchaseOrder.class, 100L);

secondSession.update(detachedOrder);
```

Nếu managed và detachedOrder là hai Java objects khác nhau nhưng cùng entity type/identifier, Hibernate không thể quản lý cả hai instance như cùng một identity trong một Persistence Context. Legacy update() thường dẫn tới NonUniqueObjectException.

Đây là một trong các lý do không nên xem update() là thao tác thay thế phổ quát cho mọi “save existing”.

## 7. merge() khác update() như thế nào?

JPA có:

```java
PurchaseOrder managed = entityManager.merge(detachedOrder);
```

merge() copy state của object nguồn vào một managed instance tương ứng trong Persistence Context hiện tại. **Object truyền vào không được biến thành managed chỉ vì gọi merge.** Giá trị trả về mới là managed instance mà ứng dụng nên tiếp tục sử dụng.

Ví dụ:

```java
PurchaseOrder detached = loadAndDetachOrder();
detached.setStatus("PAID");

PurchaseOrder managed = entityManager.merge(detached);

assertThat(entityManager.contains(managed)).isTrue();
assertThat(entityManager.contains(detached)).isFalse();
```

Nếu có entity cùng ID đã managed, merge copy state vào instance đó thay vì cố quản lý hai instance riêng.

### Quy tắc quan trọng: dùng giá trị trả về

Code dễ sai:

```java
entityManager.merge(detachedOrder);
detachedOrder.setStatus("SHIPPED");
```

detachedOrder vẫn detached; thay đổi sau merge không tự được dirty checking theo dõi.

Đúng hơn:

```java
PurchaseOrder managedOrder =
    entityManager.merge(detachedOrder);

managedOrder.setStatus("SHIPPED");
```

Tuy vậy, không nên lạm dụng merge cho mọi update. Phần sau trình bày cách cập nhật entity managed thường an toàn hơn.

## 8. Bảng so sánh save, persist, update và merge

| API | Đầu vào điển hình | Kết quả | Persistence Context |
|---|---|---|---|
| Hibernate save() cũ | Transient entity | Identifier | Entity được đưa vào trạng thái persistent theo Hibernate |
| JPA persist() | Transient entity | Không trả object | Chính instance trở thành managed |
| Hibernate update() cũ | Detached entity | Không trả object | Cố reattach chính instance; có thể xung đột identity |
| JPA merge() | Detached hoặc new entity | Managed copy | Copy state vào instance managed; object nguồn vẫn detached |

Không thể viết một phép thay tên cơ học:

- save() thường gần với ý định persist().
- update() có thể gần với merge() nếu mục tiêu là copy state từ detached object.
- Nhưng nếu mục tiêu là cập nhật một bản ghi hiện có trong business service, **load managed entity rồi thay đổi các field được phép** thường là cách rõ ràng hơn.

## 9. Vì sao merge() không phải lúc nào cũng là cách update tốt nhất?

Một request gửi DTO:

```json
{
  "id": 100,
  "status": "PAID"
}
```

Nếu map DTO thành một entity object mới rồi merge:

```java
PurchaseOrder detached = new PurchaseOrder();
detached.setId(100L);
detached.setStatus("PAID");

PurchaseOrder managed = entityManager.merge(detached);
```

Các field không được gửi có thể đang là null, 0 hoặc default Java value. Merge copy state theo entity mapping, có nguy cơ ghi đè dữ liệu hiện có bằng những giá trị không được cung cấp trong request.

Ví dụ entity có:

```text
id = 100
status = NEW
totalAmount = 250.00
shippingAddress = "12 Example Street"
```

DTO chỉ có id và status. Nếu tạo entity detached với totalAmount = null và shippingAddress = null, merge có thể đưa những giá trị đó vào managed state và sinh UPDATE tương ứng.

### Cách cập nhật thường an toàn hơn

```java
@Transactional
public void changeOrderStatus(long id, ChangeStatusCommand command) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);

    if (order == null) {
        throw new OrderNotFoundException(id);
    }

    order.changeStatus(command.status());
}
```

Entity được tải trong transaction là managed. Chỉ những thay đổi được domain method cho phép mới được dirty checking ghi xuống DB.

## 10. saveOrUpdate() đời trước là gì?

Hibernate native API cũ có:

```java
session.saveOrUpdate(order);
```

Ý định của method là xử lý entity theo trạng thái:

- Nếu Hibernate nhận diện object là transient/new, nó thực hiện semantics gần save().
- Nếu nhận diện object là detached/existing, nó thực hiện semantics gần update().

Đây là một tiện ích của Hibernate native API, không phải method JPA chuẩn.

### Nó không phải UPSERT ở database

saveOrUpdate() không tương đương:

```sql
INSERT ...
ON CONFLICT (...) DO UPDATE ...
```

Nó không phải một atomic database upsert chống race condition. Việc xác định transient hay detached thường dựa vào identifier, version và unsaved-value mapping; sau đó Hibernate thực hiện persistence operations theo lifecycle của Session.

Hai transactions đồng thời có thể cùng nhận định một object là mới rồi cùng INSERT, dẫn đến unique/primary-key violation. Nếu cần atomic upsert theo database, hãy dùng cơ chế DB-specific hoặc thiết kế concurrency/constraint phù hợp.

## 11. Hibernate nhận diện transient và detached như thế nào?

Với entity có generated identifier:

```java
@Id
@GeneratedValue
private Long id;
```

id == null thường là dấu hiệu entity mới, nhưng không nên xem đây là quy tắc tổng quát cho mọi mapping.

Với assigned identifier:

```java
@Id
private String code;
```

Một object mới có thể đã có code trước khi được persist. Chỉ nhìn ID khác null không thể phân biệt chắc chắn transient với detached.

Hibernate có các khái niệm như:

- Unsaved-value.
- Version property.
- Identifier generator strategy.
- Entity persister metadata.
- Interceptor/unsaved-value customization ở các mapping đời cũ.

Điều này làm saveOrUpdate() tiện dụng nhưng cũng khiến behavior phụ thuộc mapping và cách khởi tạo object.

### Ví dụ assigned ID gây mơ hồ

```java
Customer customer = new Customer();
customer.setCode("C-100");
customer.setName("New customer");

session.saveOrUpdate(customer);
```

Hibernate cần xác định C-100 là một identifier mới hay object detached của row đã tồn tại. Nếu mapping/unsaved-value không thể phân biệt rõ, ứng dụng có thể gặp SELECT kiểm tra tồn tại, INSERT/UPDATE không như mong đợi hoặc exception.

Không viết logic nghiệp vụ dựa vào phỏng đoán “ID khác null chắc chắn là update”.

## 12. Thay saveOrUpdate() bằng logic tường minh

Không có một method JPA duy nhất thay thế mọi semantics của saveOrUpdate(). Chọn hành vi theo ý định.

### Trường hợp A: luôn tạo mới

```java
entityManager.persist(newOrder);
```

Dùng khi command là create và database/business key uniqueness được kiểm soát.

### Trường hợp B: cập nhật một entity đã tồn tại

```java
PurchaseOrder managed =
    entityManager.find(PurchaseOrder.class, id);

if (managed == null) {
    throw new OrderNotFoundException(id);
}

managed.changeStatus(newStatus);
```

Dùng khi API là update; kiểm tra quyền và domain invariants trên entity managed.

### Trường hợp C: nhận một detached aggregate hoàn chỉnh

```java
PurchaseOrder managed = entityManager.merge(detachedOrder);
```

Chỉ dùng khi semantics copy toàn bộ state detached vào context là chủ đích, dữ liệu đầu vào đầy đủ và cascade MERGE được hiểu rõ.

### Trường hợp D: create-or-update theo business key

```java
PurchaseOrder existing = repository
    .findByTenantIdAndExternalReference(tenantId, externalReference)
    .orElse(null);

if (existing == null) {
    entityManager.persist(createNewOrder(command));
} else {
    applyAllowedChanges(existing, command);
}
```

Đây là read-then-write pattern. Nếu nhiều transactions có thể tạo cùng business key đồng thời, cần unique constraint và xử lý conflict/retry; không coi đoạn code này là atomic UPSERT.

## 13. Spring Data repository save() không phải Hibernate Session.save()

Đây là nhầm lẫn phổ biến vì hai API có cùng tên:

```java
session.save(entity);       // Hibernate legacy native API
repository.save(entity);    // Spring Data repository API
```

JpaRepository.save() thường chọn EntityManager.persist() hoặc EntityManager.merge() dựa trên cơ chế xác định entity mới của Spring Data.

Ở dạng khái quát:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}
return entityManager.merge(entity);
```

Đây là mô tả ý tưởng, không phải cam kết toàn bộ implementation nội bộ giống hệt giữa mọi Spring Data version.

### Spring Data xác định entity mới ra sao?

Thông thường nó có thể xét:

- Một nullable @Version property nếu có.
- Identifier property.
- Persistable.isNew() nếu entity tự cung cấp trạng thái new.

Với assigned IDs hoặc domain có ID được tạo trước persist, kiểm tra “ID null” có thể không phản ánh đúng trạng thái new. Khi đó cần hiểu EntityInformation/Persistable strategy của Spring Data version đang dùng.

### save() trả về giá trị nào?

Với đường merge, repository thường trả về managed copy. Hãy dùng object được trả về:

```java
PurchaseOrder saved = repository.save(detachedOrder);
```

Đừng bỏ qua return value nếu entity có thể được merge.

### saveAndFlush() cũng không phải commit

```java
PurchaseOrder saved = repository.saveAndFlush(order);
```

Method này save rồi yêu cầu flush. Transaction có thể vẫn rollback sau đó; method không tự commit một transaction do caller quản lý.

## 14. @Version và detached update

Một entity có optimistic locking:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private long version;

    private String status;
}
```

Khi detached object được gửi lại sau một thời gian, database có thể đã thay đổi bởi transaction khác.

Merge/update cần kiểm soát version để tránh ghi đè âm thầm. Nếu version cũ không còn khớp, Hibernate/JPA có thể phát hiện optimistic locking conflict tại merge, flush hoặc commit tùy provider/timing.

### Ví dụ

```text
Transaction A reads version 4
Transaction B reads version 4

A updates -> version 5, commits
B merges stale version 4 -> optimistic conflict
```

Đừng bỏ @Version chỉ để làm test merge hết lỗi. Conflict có thể là tín hiệu đúng để ứng dụng yêu cầu client tải lại dữ liệu hoặc thực hiện conflict resolution.

## 15. Cascade PERSIST và MERGE có ý nghĩa khác nhau

Ví dụ aggregate:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

- CascadeType.PERSIST: persist parent có thể cascade persist đến children theo mapping.
- CascadeType.MERGE: merge parent có thể cascade merge state đến children.

Nếu migration từ saveOrUpdate() sang persist() hoặc merge(), cascade configuration ảnh hưởng kết quả. Không thêm CascadeType.ALL chỉ để thay thế một API cũ; cascade phải phản ánh lifecycle ownership.

### Detached graph không đầy đủ

Nếu merge một parent với collection chỉ chứa một phần children, state collection được copy theo mapping/provider semantics. Có thể phát sinh inserts/updates/deletes ngoài ý định, nhất là khi orphanRemoval=true.

Đối với REST partial updates, nên tải aggregate managed và áp dụng command rõ ràng thay vì merge một object graph dựng từ JSON.

## 16. Old Hibernate Criteria API là gì?

Hibernate từng cung cấp một query API riêng:

- org.hibernate.Criteria
- Session.createCriteria(...)
- Restrictions
- Order
- Projections
- Criterion
- DetachedCriteria
- createAlias() và setFetchMode()

Ví dụ Hibernate đời trước:

```java
Criteria criteria =
    session.createCriteria(PurchaseOrder.class);

criteria.add(Restrictions.eq("status", "PAID"));
criteria.add(Restrictions.ge("totalAmount", new BigDecimal("100")));
criteria.addOrder(Order.desc("createdAt"));
criteria.setFirstResult(0);
criteria.setMaxResults(20);

List<?> results = criteria.list();
```

Đây là **Hibernate native Criteria**, không phải JPA Criteria API.

Legacy API này từng hữu ích để xây query động mà không nối chuỗi HQL. Nhưng nó là API proprietary, gắn với Hibernate-specific abstractions và đã bị deprecated trước khi bị loại bỏ trong Hibernate ORM 6.0.

## 17. Mốc phiên bản của Hibernate Criteria đời trước

| Dòng Hibernate | Legacy org.hibernate.Criteria |
|---|---|
| Hibernate 4.x | Được sử dụng phổ biến |
| Hibernate 5.0–5.1 | Vẫn có |
| Hibernate 5.2–5.6 | Deprecated; nên migration sang JPA Criteria hoặc HQL/JPQL |
| Hibernate 6.0+ | Legacy Criteria API đã bị loại bỏ |

Khi nâng từ 5.x lên 6.x, code gọi Session.createCriteria(), Restrictions hoặc org.hibernate.Criteria có thể không compile vì API đã biến mất.

Không nhầm việc loại bỏ legacy Criteria với việc loại bỏ **JPA Criteria API**. JPA Criteria là API chuẩn và tiếp tục tồn tại trong Hibernate 6/7 với package jakarta.persistence.criteria.

## 18. JPA Criteria API là gì?

JPA Criteria API là API chuẩn để xây dựng query bằng object model thay vì nối chuỗi JPQL.

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| CriteriaBuilder | Tạo predicates, expressions, ordering và query |
| CriteriaQuery<T> | Định nghĩa SELECT query trả về kiểu T |
| Root<T> | Đại diện entity root trong FROM |
| Join<X,Y> | Biểu diễn join tới association |
| Predicate | Điều kiện WHERE/HAVING |
| Path<T> | Truy cập thuộc tính |
| Order | Thứ tự sắp xếp |
| TypedQuery<T> | Query đã được tạo từ CriteriaQuery |

Ví dụ:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

Predicate paid = cb.equal(root.get("status"), "PAID");
Predicate minimumAmount = cb.greaterThanOrEqualTo(
    root.get("totalAmount"),
    new BigDecimal("100")
);

cq.select(root)
  .where(cb.and(paid, minimumAmount))
  .orderBy(cb.desc(root.get("createdAt")));

List<PurchaseOrder> results = entityManager
    .createQuery(cq)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Hibernate 6/7 dùng Jakarta Persistence, vì vậy imports thường bắt đầu bằng jakarta.persistence.criteria.*. Dự án JPA cũ hơn có thể dùng javax.persistence.criteria.*; không trộn hai namespace trong cùng application.

## 19. Chuyển Restrictions sang JPA Predicate

| Hibernate legacy Criteria | JPA Criteria |
|---|---|
| Restrictions.eq("status", value) | cb.equal(root.get("status"), value) |
| Restrictions.ne(...) | cb.notEqual(...) |
| Restrictions.gt(...) | cb.greaterThan(...) |
| Restrictions.ge(...) | cb.greaterThanOrEqualTo(...) |
| Restrictions.lt(...) | cb.lessThan(...) |
| Restrictions.le(...) | cb.lessThanOrEqualTo(...) |
| Restrictions.between(...) | cb.between(...) |
| Restrictions.like(...) | cb.like(...) |
| Restrictions.isNull(...) | cb.isNull(...) |
| Restrictions.isNotNull(...) | cb.isNotNull(...) |
| Restrictions.in(...) | path.in(values) |
| Restrictions.and(a,b) | cb.and(a,b) |
| Restrictions.or(a,b) | cb.or(a,b) |
| Restrictions.not(a) | cb.not(a) |

Ví dụ:

```java
Predicate byStatus = cb.equal(root.get("status"), status);
Predicate byDate = cb.between(root.get("createdAt"), from, to);
Predicate byIds = root.get("id").in(ids);

cq.where(cb.and(byStatus, byDate, byIds));
```

Đây là mapping khái niệm. Kiểu generic của Path và Expression nên được khai báo rõ khi compiler cần type inference chính xác.

## 20. Chuyển Order, Projections và row count

Legacy:

```java
criteria.addOrder(Order.desc("createdAt"));
criteria.setProjection(Projections.rowCount());
```

JPA Criteria:

```java
cq.orderBy(cb.desc(root.get("createdAt")));
```

Query count:

```java
CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery.select(cb.count(countRoot))
          .where(cb.equal(countRoot.get("status"), "PAID"));

Long count = entityManager.createQuery(countQuery)
    .getSingleResult();
```

Nếu cần count distinct:

```java
countQuery.select(cb.countDistinct(countRoot));
```

Nếu cần projection nhiều cột, có thể dùng cb.construct(Dto.class, ...), Tuple query hoặc JPQL constructor projection.

Ví dụ:

```java
CriteriaQuery<OrderSummary> summaryQuery =
    cb.createQuery(OrderSummary.class);
Root<PurchaseOrder> orderRoot =
    summaryQuery.from(PurchaseOrder.class);

summaryQuery.select(cb.construct(
    OrderSummary.class,
    orderRoot.get("id"),
    orderRoot.get("status"),
    orderRoot.get("totalAmount")
));
```

Không cố chuyển mọi ResultTransformer đời cũ bằng một API duy nhất. Trước hết xác định output shape: entity, DTO, tuple, map hay grouped result.

## 21. Chuyển createAlias() sang Join

Legacy:

```java
criteria.createAlias("customer", "c");
criteria.add(Restrictions.eq("c.region", region));
```

JPA Criteria:

```java
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.INNER);

cq.where(cb.equal(customer.get("region"), region));
```

Có thể dùng LEFT join:

```java
Join<PurchaseOrder, Customer> customer =
    order.join("customer", JoinType.LEFT);
```

Điểm quan trọng là join type có ý nghĩa kết quả. INNER JOIN có thể loại root rows không có association phù hợp; LEFT JOIN giữ root row và cho target null khi không match.

Nếu query legacy có alias reuse, nested alias hoặc multiple joins, cần tái tạo đúng join graph và predicate placement, không chỉ đổi createAlias thành join.

## 22. Chuyển DetachedCriteria và query động

Legacy API có DetachedCriteria để dựng criteria tách khỏi Session rồi gắn vào execution context theo cách Hibernate cũ hỗ trợ.

JPA Criteria không có cùng abstraction DetachedCriteria theo đúng contract đó. Thay thế thường là:

- Viết helper nhận CriteriaBuilder, Root<T> và trả Predicate.
- Dùng Spring Data Specification<T>.
- Dùng QueryDSL hoặc query builder được dự án lựa chọn.
- Dùng JPQL/HQL nếu query có cấu trúc tương đối cố định.

Ví dụ helper:

```java
static Predicate statusPredicate(
        CriteriaBuilder cb,
        Root<PurchaseOrder> root,
        OrderStatus status) {

    if (status == null) {
        return cb.conjunction();
    }

    return cb.equal(root.get("status"), status);
}
```

Khi dựng query:

```java
List<Predicate> predicates = new ArrayList<>();
predicates.add(statusPredicate(cb, root, status));
predicates.add(cb.equal(root.get("tenantId"), tenantId));

cq.where(cb.and(predicates.toArray(Predicate[]::new)));
```

Helper nên giữ logic domain/query nhỏ, có kiểu dữ liệu rõ và không tạo một framework criteria riêng quá phức tạp.

## 23. Spring Data Specification là một lựa chọn cho query động

Nếu ứng dụng dùng Spring Data JPA, Specification<T> có thể gom điều kiện query có thể kết hợp.

Ví dụ:

```java
public static Specification<PurchaseOrder> hasStatus(
        OrderStatus status) {

    return (root, query, cb) -> status == null
        ? cb.conjunction()
        : cb.equal(root.get("status"), status);
}

public static Specification<PurchaseOrder> belongsToTenant(
        String tenantId) {

    return (root, query, cb) ->
        cb.equal(root.get("tenantId"), tenantId);
}
```

Kết hợp:

```java
Specification<PurchaseOrder> specification =
    belongsToTenant(tenantId).and(hasStatus(status));

Page<PurchaseOrder> page =
    repository.findAll(specification, pageable);
```

Repository cần mở rộng JpaSpecificationExecutor<PurchaseOrder>.

Specification phù hợp với filter/search động; không phải lý do để chuyển mọi HQL query sang criteria. Nếu query phức tạp và ít thay đổi, JPQL/HQL rõ ràng có thể dễ bảo trì hơn.

## 24. Static metamodel giúp giảm lỗi tên thuộc tính

JPA Criteria ví dụ dùng string:

```java
root.get("createdAt")
```

Nếu rename field mà không sửa string, lỗi có thể chỉ xuất hiện khi chạy query.

Static metamodel cho phép:

```java
root.get(PurchaseOrder_.createdAt)
```

Metamodel class thường được sinh bởi annotation processor phù hợp với Jakarta Persistence version. Cấu hình build cần khớp namespace jakarta hay javax.

Lợi ích:

- Compiler kiểm tra thuộc tính.
- IDE refactor tốt hơn.
- Giảm typo trong query động.

Đừng thêm metamodel generation vào migration chỉ để thay vài query nhỏ nếu dự án chưa có nhu cầu; chọn cách nhất quán với codebase.

## 25. Legacy Criteria và HQL/JPQL: không phải lúc nào Criteria cũng tốt hơn

Ví dụ query cố định:

```java
select o
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
order by o.createdAt desc
```

JPQL/HQL thường ngắn và dễ đọc:

```java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select o
    from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.status = :status
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setParameter("tenantId", tenantId)
    .setParameter("status", status)
    .getResultList();
```

Criteria phù hợp khi query structure thực sự được lắp ghép động từ nhiều optional filters, joins và expressions.

| Tình huống | Thường phù hợp |
|---|---|
| Query cố định, dễ đọc | JPQL/HQL |
| Nhiều điều kiện optional | JPA Criteria/Specification |
| DTO read model đơn giản | JPQL constructor projection |
| SQL đặc thù DB | Native SQL có chủ đích |
| Query type-safe phức tạp | JPA metamodel hoặc QueryDSL theo convention dự án |

## 26. Legacy createCriteria() bị loại bỏ: nhận diện lỗi compile khi nâng Hibernate 6

Sau khi nâng dependency từ Hibernate 5.x lên 6.x, code:

```java
session.createCriteria(PurchaseOrder.class);
```

có thể báo không tìm thấy method. Import:

```java
import org.hibernate.Criteria;
import org.hibernate.criterion.Restrictions;
```

cũng không còn hợp lệ vì legacy Criteria package/API đã bị loại bỏ.

### Cách xử lý

1. Tìm mọi import org.hibernate.Criteria, org.hibernate.criterion.*.
2. Tìm Session.createCriteria, DetachedCriteria, Restrictions, Projections.
3. Phân loại query: cố định hay động, entity hay projection, joins/pagination/count.
4. Chọn JPQL/HQL, JPA Criteria hoặc Spring Data Specification.
5. Viết test so sánh result semantics trên DB thật.

Không thêm lại một dependency Hibernate cũ để code compile trong khi application đã chạy Hibernate 6. Trộn Hibernate core versions hoặc cố giữ API đã bị loại bỏ có thể gây incompatibility sâu hơn.

## 27. Nhận diện import cũ và namespace javax/jakarta

Hibernate 6 chuyển sang Jakarta Persistence namespace.

Code cũ:

```java
import javax.persistence.EntityManager;
import javax.persistence.criteria.CriteriaBuilder;
```

Code Hibernate 6+:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
```

Đây là migration namespace rộng hơn Criteria. Cần đồng bộ JPA annotations, EntityManager/EntityTransaction, Criteria API, persistence exceptions, AttributeConverter và integration libraries.

Không import đồng thời javax.persistence.* và jakarta.persistence.* cho cùng model. Chúng là hai package khác nhau, dù tên class giống nhau.

## 28. Các API đời cũ khác có thể gặp cùng lúc

Trong một migration Hibernate 5 → 6, ngoài nhóm API chính, hãy nhận diện:

| Legacy API/convention | Hướng thay thế cần xem xét |
|---|---|
| Session.save() | persist() cho create |
| Session.update() | merge() hoặc load managed entity rồi mutate |
| Session.saveOrUpdate() | Quyết định create/update rõ ràng; không có một phép thay thế duy nhất |
| Session.delete() | remove() với managed entity |
| Session.load() | getReference()/find() theo semantics cần thiết |
| Session.get() | find() nếu cần JPA semantics |
| Session.createCriteria() | JPA Criteria/HQL/Specification |
| org.hibernate.Query cũ | org.hibernate.query.Query/JPA Query tùy API |
| createSQLQuery() | createNativeQuery() |
| setResultTransformer() | Tuple/constructor projection hoặc transformer API phù hợp version |
| javax.persistence.* | jakarta.persistence.* |

Không phải mọi mục trong bảng đều bị loại bỏ cùng thời điểm hoặc có semantics hoàn toàn tương đương. Dùng bảng như danh sách nhận diện, rồi tra Javadocs/migration guide đúng phiên bản.

## 29. Vì sao không nên thay mọi update bằng merge?

Một service update rõ ràng:

```java
@Transactional
public void renameCustomer(long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    if (customer == null) {
        throw new CustomerNotFoundException(id);
    }
    customer.rename(newName);
}
```

Ưu điểm:

- Entity managed nằm trong transaction hiện tại.
- Chỉ thay field được phép.
- Không cần tạo detached graph.
- Dirty checking theo dõi thay đổi.
- Có thể kiểm tra authorization/domain invariants trước khi mutation.
- Dễ phối hợp @Version.

Merge phù hợp khi cần copy state của detached entity theo đúng semantics. Với API update từ DTO, load managed entity rồi apply patch thường dễ kiểm soát hơn.

## 30. Migration save/update cần xét identifier strategy

Ví dụ generated ID:

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
```

Với object mới, persist là ý định rõ ràng.

Với assigned ID:

```java
@Id
private String externalCode;
```

object mới có thể có ID trước persist. Không thể suy luận new/existing chỉ từ id != null.

Các cách:

- Dùng command create/update tách biệt.
- Dùng nullable @Version nếu phù hợp domain và Spring Data new detection.
- Dùng Persistable.isNew() trong Spring Data khi cần custom new-state detection.
- Dùng repository lookup theo business key và unique constraint.
- Tránh tự viết heuristic dựa trên giá trị ID nếu mapping phức tạp.

## 31. Merge và associations: kiểm tra cascade, orphanRemoval, lazy state

Detached graph có thể không chứa tất cả associations đã tồn tại. Merge sẽ copy state theo mapping và cascade MERGE; behavior của collection có thể làm thay đổi children.

Trước khi thay update() bằng merge():

1. Xem cascade trên từng association.
2. Xem owning side và inverse side.
3. Xem orphanRemoval.
4. Xem collection có đầy đủ hay chỉ là subset từ API payload.
5. Xem optimistic version.
6. Xem lazy attributes có bị serialize/copy ngoài ý muốn không.

Không merge một entity graph được dựng từ DTO thiếu fields rồi mong Hibernate tự hiểu field nào “không được gửi”.

## 32. Criteria migration phải giữ nguyên semantics của query

Một query cũ có thể gồm:

```java
criteria.createAlias("customer", "c");
criteria.add(Restrictions.eq("c.region", region));
criteria.add(Restrictions.or(
    Restrictions.eq("status", "NEW"),
    Restrictions.eq("status", "PAID")
));
criteria.addOrder(Order.desc("createdAt"));
criteria.setFirstResult(offset);
criteria.setMaxResults(pageSize);
```

Khi chuyển sang JPA Criteria, phải giữ:

- INNER hay LEFT join.
- Predicate nằm ở WHERE hay join ON.
- OR/AND grouping.
- Null semantics.
- Sort direction và tie-breaker.
- Pagination offset/limit.
- Distinct behavior nếu join collection.
- Projection/result shape.

Chỉ làm cho query compile không chứng minh query mới trả cùng tập kết quả.

## 33. Criteria join và pagination có thể tạo duplicate roots

Nếu join từ Order sang nhiều Lines, một Order có thể xuất hiện nhiều SQL rows. Criteria query có thể cần:

```java
cq.distinct(true);
```

Nhưng distinct ở entity result không phải lúc nào cũng loại bỏ toàn bộ chi phí row multiplication tại database.

Nếu phân trang trên to-many join, cần kiểm tra:

- Kết quả có duplicate/thiếu root entities không?
- Count query có đúng không?
- DB phải sort bao nhiêu rows?
- Hibernate có cảnh báo hoặc thực hiện pagination trong memory không?

Với page root entities, có thể lấy IDs theo page trước rồi fetch associations cho các IDs đó trong query thứ hai.

## 34. Dynamic predicates và null handling

Legacy Criteria thường được dùng để thêm condition nếu request có filter:

```java
if (status != null) {
    criteria.add(Restrictions.eq("status", status));
}
```

JPA Criteria:

```java
List<Predicate> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(cb.equal(root.get("status"), status));
}

if (from != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        root.get("createdAt"), from
    ));
}

if (to != null) {
    predicates.add(cb.lessThan(
        root.get("createdAt"), to
    ));
}

cq.where(predicates.toArray(Predicate[]::new));
```

Nếu list predicates rỗng, không gọi điều kiện tùy tiện như status = null; để query không có WHERE hoặc dùng cb.conjunction() tùy mục đích.

Đặc biệt, IS NULL và = NULL không giống nhau trong SQL. Dùng cb.isNull(path) khi muốn lọc null.

## 35. Query parameters vẫn phải được bind

Không nối user input vào JPQL/HQL/SQL string:

```java
// Tránh:
String hql = "from PurchaseOrder o where o.status = '" + status + "'";
```

Dùng parameter:

```java
entityManager.createQuery(
    "from PurchaseOrder o where o.status = :status",
    PurchaseOrder.class
).setParameter("status", status);
```

Criteria API cũng dùng typed parameters hoặc expressions, giúp tránh string concatenation và hỗ trợ type checking.

## 36. Đừng thay Hibernate Criteria bằng native SQL nếu không cần

Legacy Criteria thường được dùng vì query động. Khi migration, có thể có cám dỗ viết native SQL để tránh học JPA Criteria.

Native SQL phù hợp khi cần DB-specific feature, query cần window functions/CTE/vendor syntax không được ORM biểu diễn tốt, hoặc cần tối ưu query đã đo được bottleneck.

Nhưng native SQL cần quản lý mapping result columns, parameter binding, tenant predicates/security, pagination syntax, portability và Persistence Context synchronization với native DML.

Không chuyển mọi Criteria query sang native SQL chỉ để giữ cách ghép chuỗi cũ.

## 37. Migration theo từng bước

### Bước 1: inventory

Tìm:

```text
session.save(
session.update(
session.saveOrUpdate(
session.delete(
session.createCriteria(
createCriteria(
DetachedCriteria
Restrictions.
Projections.
org.hibernate.criterion
setResultTransformer(
```

Tìm cả import static và DAO wrappers:

```bash
rg -n "saveOrUpdate|createCriteria|Restrictions|ResultTransformer" .
```

Phân loại vị trí gọi, entity type, transaction boundary và mục đích.

### Bước 2: xác định entity lifecycle intent

Với từng call site, hỏi:

- Tạo mới?
- Cập nhật entity đã có?
- Nhận detached graph?
- Đồng bộ theo business key?
- Xóa entity?

Không thay bằng một API chung khi ý định khác nhau.

### Bước 3: migrate write operations

- Create: persist().
- Update: load managed entity rồi mutate.
- Detached full-state copy: merge() và dùng return value.
- Delete: load managed entity rồi remove().
- Create-or-update: logic rõ ràng + unique constraint/concurrency handling.

### Bước 4: migrate query operations

- Query cố định: JPQL/HQL.
- Query động: JPA Criteria/Specification.
- Projection: DTO constructor/Tuple.
- DB-specific: native SQL có chủ đích.

### Bước 5: kiểm tra associations và concurrency

Review cascade, orphanRemoval, owning side, version, assigned IDs và lazy state.

### Bước 6: test trước/sau

So sánh result set, SQL behavior, transaction semantics và exception paths trên database mục tiêu.

## 38. Tìm legacy API trong codebase

Có thể dùng ripgrep:

```bash
rg -n "session\\.(save|update|saveOrUpdate|delete|createCriteria)\\(" src
rg -n "org\\.hibernate\\.criterion|DetachedCriteria|Restrictions\\.|Projections\\." src
rg -n "javax\\.persistence" src
```

Search results cần được phân loại thủ công:

- Có thể method tên save thuộc Spring Data repository, không phải Hibernate Session.
- Có thể Criteria là JPA Criteria hoặc một API khác.
- Có thể code trong test/legacy module không nằm trong runtime path.

Đừng xóa hoặc sửa hàng loạt dựa trên tên method mà chưa xác định type của receiver/import.

## 39. Ma trận migration theo ý định

| Code cũ | Ý định thực | Hướng mới |
|---|---|---|
| session.save(newEntity) | Tạo entity mới | entityManager.persist(newEntity) |
| session.update(detached) | Reattach detached state | merge(detached) nếu copy state là ý định; nếu không, load managed rồi mutate |
| session.saveOrUpdate(x) | Tự chọn insert/update | Phân biệt create/update rõ; không có thay thế một dòng chung |
| session.delete(managed) | Xóa entity managed | entityManager.remove(managed) |
| createCriteria(...).add(Restrictions...) | Query động | JPA Criteria/Specification |
| Projections.rowCount() | Đếm rows | cb.count(root) |
| createAlias() | Join association | root.join(...) |
| setResultTransformer() | Biến đổi result | DTO constructor, Tuple hoặc projection phù hợp |
| DetachedCriteria | Tái sử dụng điều kiện query | Predicate helper/Specification/JPQL |

## 40. Kiểm thử migration cho save/persist

Với create:

```java
entityManager.persist(order);
entityManager.flush();
Long id = order.getId();

entityManager.clear();

PurchaseOrder actual =
    entityManager.find(PurchaseOrder.class, id);

assertThat(actual).isNotNull();
assertThat(actual.getStatus()).isEqualTo("NEW");
```

Kiểm tra row có được tạo, ID có đúng strategy, cascade children có được persist, unique constraints có hoạt động và transaction rollback/commit đúng.

## 41. Kiểm thử migration cho merge

Một test:

```java
PurchaseOrder original = entityManager.find(PurchaseOrder.class, id);
entityManager.detach(original);

original.setStatus("PAID");

PurchaseOrder managed = entityManager.merge(original);

assertThat(entityManager.contains(original)).isFalse();
assertThat(entityManager.contains(managed)).isTrue();

entityManager.flush();
entityManager.clear();

PurchaseOrder actual =
    entityManager.find(PurchaseOrder.class, id);
assertThat(actual.getStatus()).isEqualTo("PAID");
```

Test này làm rõ merge return semantics. Bổ sung tests cho ID không tồn tại, detached entity stale version, association cascade MERGE, collection partial state/orphan removal và object managed cùng ID đã có trong context.

## 42. Kiểm thử Criteria migration bằng result equivalence

Với cùng dataset:

1. Chạy query legacy trên Hibernate version còn hỗ trợ.
2. Lưu kết quả IDs và thứ tự.
3. Chạy query JPA Criteria mới.
4. So sánh IDs, ordering, pagination và count.
5. Test null values, empty filters, duplicate join rows.
6. Test tenant scope và authorization predicates.

Nếu không thể chạy hai versions song song, tạo fixture xác định và expected results từ business rules. Không dùng snapshot từ legacy query như chân lý nếu query cũ vốn có bug.

## 43. Bài thực hành 1: save() và persist()

1. Tạo entity mới với generated ID.
2. Lưu bằng Hibernate Session API cũ trong một project version phù hợp.
3. Ghi nhận return type/ID timing.
4. Chuyển sang JPA persist.
5. Flush và reload.
6. So sánh lifecycle và transaction behavior.

Giải thích vì sao persist() không trả identifier và vì sao cả hai đều không commit transaction.

## 44. Bài thực hành 2: update() và merge()

1. Load entity trong Session A.
2. Đóng Session A để tạo detached object.
3. Thay đổi detached object.
4. Thử legacy update() trong Session B.
5. Load cùng ID trước khi update để quan sát identity conflict.
6. Chuyển sang merge().
7. Assert object nguồn detached, object trả về managed.
8. Thử thay đổi object nguồn sau merge và so sánh với managed return value.

## 45. Bài thực hành 3: saveOrUpdate() và assigned identifier

1. Tạo entity có assigned ID.
2. Thử lưu object mới với ID đã gán.
3. Thử detached object có cùng ID.
4. Quan sát transient/detached detection theo mapping/version.
5. Thay bằng explicit create/update commands.
6. Thêm unique constraint và concurrent create test.

Giải thích vì sao saveOrUpdate() không phải atomic database UPSERT.

## 46. Bài thực hành 4: chuyển Hibernate Criteria sang JPA Criteria

Legacy query dùng:

```java
criteria.add(Restrictions.eq("status", "PAID"));
criteria.addOrder(Order.desc("createdAt"));
criteria.setMaxResults(20);
```

Chuyển thành CriteriaBuilder/CriteriaQuery:

1. Tạo root.
2. Tạo status predicate.
3. Tạo ordering.
4. Set pagination.
5. Chạy trên cùng dataset.
6. So sánh result IDs/order/count.

## 47. Bài thực hành 5: join, projection và dynamic filters

1. Tạo legacy alias/customer region criteria.
2. Chuyển thành root.join("customer").
3. Chuyển Projections.rowCount() thành cb.count.
4. Chuyển projection thành DTO constructor.
5. Thêm optional predicates.
6. Test INNER/LEFT join, nulls và to-many duplicates.

## 48. Câu hỏi tự kiểm tra

1. Hibernate Session.save() khác EntityManager.persist() thế nào?
2. Vì sao save() không đồng nghĩa commit?
3. Entity transient, managed, detached và removed khác nhau ra sao?
4. Legacy update() làm gì với detached entity?
5. Vì sao update() có thể ném NonUniqueObjectException?
6. merge() copy state vào object nào?
7. Vì sao phải dùng object trả về từ merge()?
8. Merge một entity dựng từ DTO thiếu fields có rủi ro gì?
9. Khi nào load managed entity rồi mutate tốt hơn merge?
10. saveOrUpdate() quyết định insert/update dựa trên thông tin nào?
11. Vì sao saveOrUpdate() không phải SQL UPSERT?
12. Assigned ID làm transient detection khó thế nào?
13. Spring Data repository.save() có phải Hibernate Session.save() không?
14. Spring Data xác định entity mới bằng những cách nào?
15. saveAndFlush() có commit không?
16. Cascade PERSIST khác Cascade MERGE thế nào?
17. Vì sao detached collection không đầy đủ nguy hiểm với orphanRemoval?
18. Legacy Hibernate Criteria khác JPA Criteria ở điểm nào?
19. Legacy org.hibernate.Criteria bị loại bỏ từ Hibernate major version nào?
20. Hibernate 6 dùng javax hay jakarta persistence namespace?
21. Restrictions.eq() chuyển sang JPA Criteria thế nào?
22. createAlias() chuyển sang API nào?
23. Projections.rowCount() chuyển thành gì?
24. Vì sao INNER JOIN và LEFT JOIN không thể thay thế tùy tiện?
25. Khi nào JPQL/HQL dễ bảo trì hơn Criteria?
26. Vì sao bulk query/criteria migration cần test result equivalence?
27. Vì sao @Version quan trọng khi merge detached state?
28. Những call sites nào cần tìm trước khi nâng Hibernate 5 lên 6?

**Gợi ý:** (1) native Hibernate, trả ID, so với JPA void; (2) transaction chưa kết thúc; (3) các lifecycle states; (4) reattach chính object; (5) hai instance cùng identity trong một context; (6) managed instance; (7) object nguồn vẫn detached; (8) null/default có thể ghi đè; (9) partial update/domain rules; (10) ID/version/unsaved-value; (11) không atomic DB statement; (12) ID khác null không nói lên trạng thái; (13) không; (14) version/id hoặc Persistable; (15) không; (16) cascade create vs copy state; (17) có thể xóa child ngoài ý muốn; (18) proprietary vs JPA standard; (19) 6.0; (20) jakarta; (21) cb.equal; (22) root.join; (23) cb.count; (24) ảnh hưởng root rows; (25) query cố định; (26) giữ semantics; (27) phát hiện stale writes; (28) save/update/saveOrUpdate/createCriteria/Restrictions/Projections/DetachedCriteria/transformers/javax imports.

## 49. Nguyên tắc cần ghi nhớ

1. **Hibernate Session.save() là legacy native API; JPA persist() là API chuẩn và không trả identifier.**
2. **persist() dành cho entity mới.** Đừng dùng nó như một lệnh update detached object.
3. **Legacy update() cố reattach chính detached instance.** Nó có thể xung đột với instance cùng ID đã managed.
4. **merge() copy state sang managed instance và trả instance đó.** Object truyền vào vẫn detached; luôn dùng return value.
5. **Load managed entity rồi mutate thường phù hợp với business updates/partial DTOs**, vì chỉ thay đổi field được phép.
6. **saveOrUpdate() không phải atomic database UPSERT.** Nó dùng entity-state detection dựa trên identifier/version/unsaved-value và mapping.
7. **Assigned IDs làm việc xác định transient/detached khó hơn.** Đừng suy luận chỉ từ ID khác null.
8. **Spring Data repository.save() khác Session.save().** Spring Data có thể chọn persist hoặc merge; dùng return value và hiểu new-entity detection.
9. **saveAndFlush() flush nhưng không commit.**
10. **Cascade PERSIST và MERGE là hai lifecycle semantics khác nhau.** Kiểm tra mapping thay vì thêm ALL một cách máy móc.
11. **Legacy org.hibernate.Criteria khác JPA Criteria.** Legacy API deprecated từ Hibernate 5.2 và bị loại bỏ trong Hibernate 6.0; JPA Criteria vẫn được hỗ trợ.
12. **Hibernate 6 chuyển từ javax.persistence sang jakarta.persistence.** Đồng bộ annotations, imports và dependencies.
13. **Criteria migration phải giữ join type, predicates, null semantics, projection, ordering, pagination và count.**
14. **JPQL/HQL thường rõ hơn cho query cố định; JPA Criteria/Specification hữu ích cho query động.**
15. **Migration thành công cần tests về lifecycle, concurrency, associations và result equivalence**, không chỉ compile thành công.

Khi nâng cấp một dự án Hibernate, điều quan trọng là xác định code cũ đang muốn **tạo entity, reattach detached state, cập nhật entity hiện có hay xây query động**. Những ý định đó có thể từng được gói trong save, update, saveOrUpdate và createCriteria, nhưng API mới yêu cầu diễn đạt rõ hơn. Chọn persist, merge, managed-entity mutation, JPQL hoặc JPA Criteria theo đúng semantics sẽ giúp migration ít lỗi dữ liệu và dễ bảo trì hơn.

### Tài liệu tham khảo chính thức

- [Hibernate ORM 5.6 Javadocs — Session](https://docs.hibernate.org/orm/5.6/javadocs/org/hibernate/Session.html)
- [Hibernate ORM 6.0 Javadocs — Session](https://docs.hibernate.org/orm/6.0/javadocs/org/hibernate/Session.html)
- [Hibernate ORM 6.0 Migration Guide](https://docs.hibernate.org/orm/6.0/migration-guide/)
- [Hibernate ORM 6.6 User Guide — Entity states and persistence context](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 6.6 Javadocs — Session](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Session.html)
- [Jakarta Persistence API — EntityManager](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Spring Data JPA Reference — Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Spring Data JPA Reference — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Hibernate ORM User Guide — HQL](https://docs.hibernate.org/orm/current/querylanguage/html_single/)
